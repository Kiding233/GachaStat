"""阶段计时与资源计数的**解析与归一**。

**本模块不含任何采集动作、不引入任何记录点或采样点。** 两个采集主体各自在册：

| 读数 | 采集主体 | 位置 |
|---|---|---|
| 三段计时（`pool_start` / `simulate` / `extract`） | **产品侧** `run_batch_parallel`，受 `collect_perf` 门控 | `BatchResult.stage_times` |
| 三元组序列化字节数 | **产品侧**，同一门控 | `BatchResult.packet_bytes` |
| RSS 峰值（`subject='startup'`） | `3f-1` 的启动适配器（§3.11 规则 11） | 启动完成时刻的采样 |
| 配置加载 / env 构建两段 | `cli` 适配器自身（`cli.py` 的 `main()` 是这两个边界的唯一观察者） | `1e-1` |

故 revert 本模块不影响产品默认行为。

**字节数是代理指标**（§3.5）：量的是整个三元组
`len(pickle.dumps((compact, extraction, warnings)))`，**当回归判据用，不当绝对开销读**。
同配置同种子下它完全确定、零噪声，任何变化必然由代码改动引起；但它同时受 pickle
实现与队列分帧影响，**不是**「传输耗时」的等价物。另：**不可把各分量的字节数相加
当总量**——实测分项之和 1996 KB > 整体 1688 KB（118%），pickle 的 memo 在同一次
序列化内共享重复对象引用，分项各自序列化则各记一份。

**阶段词汇表是六段**（§3.3）：配置加载 / env 构建 / 进程池启动 / 模拟 /
extractor 合并 / 分发。**不是每条路径都有同一个六段全集**——`cli` 没有分发器，
故它的 `dispatch` 段缺失属事实而非缺口；报告须**显式标注**「本路径不产出该段」，
**不得留空静默跳过**（同 §3.13 短段豁免的处置口径）。
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from benchmarks.perf.record import ResourceStats

__all__ = [
    'STAGES',
    'STAGE_LABELS',
    'PRODUCT_STAGE_KEYS',
    'WARN_BYTES_UNAVAILABLE',
    'WARN_RSS_NOT_COLLECTED',
    'WARN_RSS_UNAVAILABLE',
    'WARN_STAGES_NOT_COLLECTED',
    'stage_label',
    'normalize_stages',
    'normalize_resources',
]


#: 六段阶段词汇表（§3.3），顺序即报告中的呈现顺序。
STAGES: Tuple[str, ...] = (
    'config_load',
    'env_build',
    'pool_start',
    'simulate',
    'extract',
    'dispatch',
)

STAGE_LABELS: Dict[str, str] = {
    'config_load': '配置加载',
    'env_build': 'env 构建',
    'pool_start': '进程池启动',
    'simulate': '模拟',
    'extract': 'extractor 合并',
    'dispatch': '分发',
}

#: 产品侧 `BatchResult.stage_times` 使用的键 → 本词汇表。三者同名，但显式列出
#: 以免将来单侧改名时无人察觉（「参数键名即契约」）。
PRODUCT_STAGE_KEYS: Dict[str, str] = {
    'pool_start': 'pool_start',
    'simulate': 'simulate',
    'extract': 'extract',
}

# ── 告警文案（常量，供报告与测试断言；两种降级成因不得共用同一句话） ──

WARN_BYTES_UNAVAILABLE = '本路径不可得：三元组序列化字节数（该路径无回传通道）'
"""`gui-qt` / `webui` 侧恒为此因——它们没有 `--perf-json` 那样的通道。"""

WARN_RSS_NOT_COLLECTED = '本期不采集：subject=simulation 的 RSS 峰值（P83 §3.3）'
"""**定义如此，不是缺失。** 模拟路径没有固定的、可归属的采样时刻。"""

WARN_RSS_UNAVAILABLE = '本指标不可得：缺 psutil，RSS 峰值无法读取'
"""与上一条**成因不同**，报告中须区分：一个是「本期不采」，一个是「设施缺失」。"""

WARN_STAGE_ABSENT = '本路径不产出该段：{stage}'
"""结构性缺失（如 `cli` 无分发器）。"""

WARN_STAGE_MISSING = '该段未采集：{stage}'
"""非结构性缺失——本应收数却没收到，须排查。"""

WARN_STAGES_NOT_COLLECTED = '本路径未采集阶段计时（collect_perf=False 或该路径无回传通道）'
"""整份 stage_times 缺失。**不假装六段都在**，也不逐段报缺失。"""


def stage_label(stage: str) -> str:
    """段的显示名（中文），未登记的段名回退为原名。"""
    return STAGE_LABELS.get(stage, stage)


# ── 阶段计时归一 ─────────────────────────────────────────


def normalize_stages(
    raw: Optional[Mapping[str, float]],
    *,
    absent_by_design: Sequence[str] = (),
) -> Tuple[Dict[str, float], List[str]]:
    """把路径侧收集到的原始阶段计时归一为 `RunResult.stages`。

    `raw` 的键必须是 `PRODUCT_STAGE_KEYS` 或六段词汇表内的名字——**未知键报错**，
    不静默丢弃（键名即契约；静默丢弃会让一段计时悄悄消失而报告照常产出）。

    `absent_by_design` 声明**本路径结构上不产出**的段（如 `cli` 传
    `('dispatch',)`）。这类缺失记为 `WARN_STAGE_ABSENT`；其余缺失记为
    `WARN_STAGE_MISSING`——两种成因可区分，读数据的人才知道该不该去排查。

    `raw` 为 `None`（未采集，如 `collect_perf=False`）时返回空 stages 与一条
    按路径归因的告警：**不假装六段都在**。
    """
    warnings: List[str] = []

    if raw is None:
        return {}, [WARN_STAGES_NOT_COLLECTED]

    unknown = sorted(set(raw) - set(STAGES))
    if unknown:
        raise ValueError(
            f'阶段计时含未知段名 {unknown}；合法段名为 {list(STAGES)}'
            '（产品侧 stage_times 的键须先经 PRODUCT_STAGE_KEYS 映射）'
        )

    negative = sorted(name for name, value in raw.items() if value < 0)
    if negative:
        raise ValueError(f'阶段计时出现负值 {negative}——计时口径有误')

    stages = {name: float(raw[name]) for name in STAGES if name in raw}

    declared_absent = set(absent_by_design)
    undeclared = sorted(set(STAGES) - set(stages) - declared_absent)
    for name in sorted(declared_absent & (set(STAGES) - set(stages))):
        warnings.append(WARN_STAGE_ABSENT.format(stage=f'{name}（{stage_label(name)}）'))
    for name in undeclared:
        warnings.append(WARN_STAGE_MISSING.format(stage=f'{name}（{stage_label(name)}）'))

    return stages, warnings


def map_product_stage_times(raw: Optional[Mapping[str, Any]]) -> Optional[Dict[str, float]]:
    """把产品侧 `BatchResult.stage_times` 的键映射到六段词汇表。

    未知键报错（同上）。`raw` 为空 dict（`collect_perf=False` 时槽保持空）视同
    **未采集**，返回 `None`——空 dict 与「六段都采到了但都是 0」不是一回事。
    """
    if raw is None or len(raw) == 0:
        return None
    unknown = sorted(set(raw) - set(PRODUCT_STAGE_KEYS))
    if unknown:
        raise ValueError(f'产品侧 stage_times 含未知键 {unknown}；已知键为 {sorted(PRODUCT_STAGE_KEYS)}')
    return {PRODUCT_STAGE_KEYS[key]: float(value) for key, value in raw.items()}


# ── 资源计数归一 ─────────────────────────────────────────


def normalize_resources(
    *,
    packet_bytes: Optional[Sequence[int]] = None,
    rss_peak_mb: Optional[float] = None,
    subject: str = 'simulation',
) -> Tuple[ResourceStats, List[str]]:
    """归一资源计数。

    **两项的 `None` 语义不同，报告须区分成因：**

    - `bytes`：取本次 run 中**每次模拟**的三元组序列化长度的**中位数**。
      取 per-simulation 值而非总和，是因为总和随 `n` 增长——而 `n` 本身就是
      被测因子，用总和会让不同 `n` 的两次测量**不可比**。中位数与 §3.5 对
      `wall_median` 的取法一致。
      空序列／未采集 → `None` + `WARN_BYTES_UNAVAILABLE`。
    - `rss_peak_mb`：`subject='simulation'` 下**恒为 `None`**（本期不采集，§3.3），
      记 `WARN_RSS_NOT_COLLECTED`；`subject='startup'` 下取 `3f-1` 的采样值，
      读不到时记 `WARN_RSS_UNAVAILABLE`。
    """
    warnings: List[str] = []

    if packet_bytes:
        values = [int(value) for value in packet_bytes]
        if any(value < 0 for value in values):
            raise ValueError('packet_bytes 出现负值——字节数口径有误')
        byte_stat: Optional[int] = int(statistics.median(values))
    else:
        byte_stat = None
        warnings.append(WARN_BYTES_UNAVAILABLE)

    if subject == 'simulation':
        rss: Optional[float] = None
        warnings.append(WARN_RSS_NOT_COLLECTED)
    elif rss_peak_mb is None:
        rss = None
        warnings.append(WARN_RSS_UNAVAILABLE)
    else:
        rss = float(rss_peak_mb)

    return ResourceStats(bytes=byte_stat, rss_peak_mb=rss), warnings
