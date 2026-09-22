"""记录类型：`RunResult` + `EnvFingerprint` + 四个子记录。

**本模块的字段表是唯一真值源**（P83 §6.0 `1c`，2026-09-21 定死）：`02-实施.md`
§4 的两段字段表须按本表逐项同步；其后若有分歧，一律以本模块为准。

字段清单与来源：

| 记录类型 | 字段 | 来源 |
|---|---|---|
| `RunResult` | `run_id` / `timestamp` / `path` / `is_user_path` / `fingerprint` / `plan` | 基础记录 |
| | `repeats` / `wall_median` / `wall_samples` / `repeats_downgraded` | §3.5 的 repeats 四项政策（提供者 `1e-1`、门禁 `1f`） |
| | `stages` / `single` / `functions` / `resources` | 测量产出 |
| | `return_compact` | §3.5 的可比性维度（AUDIT-BREAK-4） |
| | `samples_meta` / `not_comparable` / `warnings` | 标注与软降级 |
| `EnvFingerprint` | `cpu` / `cores` / `os` / `python` / `code_version` / `qt_qpa_platform` | §3.11 要求记录本次 `QT_QPA_PLATFORM` 取值 |

**两条硬约束（AUDIT-BREAK-2 / AUDIT-BREAK-4）：**

1. **`repeats` 缺失是硬失败而非降级**。字段为 `None` 时与 `3` 比较即抛
   `TypeError`（Python 3 中 `None < int` 无定义）。故 `repeats` 在本模块声明为
   `Optional[int]` 且默认 `None`，**消费方（`1f`）必须按「字段缺失或 `None` →
   按不可比处理并记 `warnings`」实现，不得直接比较**。`None` 的语义是「未记录」，
   不是「0 次」。
2. **`return_compact` 与 `qt_qpa_platform` 是可比性维度而非普通读数**。两者的
   `None` 都表示「未记录」，比对侧须按不可比处理（**不得静默判不等**）。
   `return_compact=False` 时三元组首分量为 `None`，`packet_bytes` 因而不含
   `compact`，故 `gui-qt` / `webui` 的字节数**天然小于** `cli`，
   **跨路径不可直接比较**。
"""

from __future__ import annotations

import os
import platform
import types
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from benchmarks.perf.plan import Plan, suspended_memory_check

__all__ = [
    'RunResult',
    'EnvFingerprint',
    'FuncStat',
    'ResourceStats',
    'SamplesMeta',
    'SingleStats',
]


# ── 子记录 ───────────────────────────────────────────────


@dataclass(frozen=True)
class FuncStat:
    """`cProfile` 的一条函数级统计。"""

    name: str
    ncalls: int
    tottime: float
    cumtime: float


@dataclass
class ResourceStats:
    """资源计数。两项都**可以是 `None`**，且 `None` 有两种不同成因，报告中须区分。

    - `bytes`：三元组序列化长度（`len(pickle.dumps((compact, extraction, warnings)))`）。
      **只有具备回传通道的路径采**（`cli` 经 opt-in `--perf-json`）；其余路径记
      `None` 并在 `warnings` 标注「本路径不可得」。**当回归判据用，不当绝对开销读。**
    - `rss_peak_mb`：`subject='startup'` 下取启动完成时刻的峰值（规则 11）；
      `subject='simulation'` 下**本期不采集**，恒为 `None` 属定义如此，不是缺失
      （§3.3）。缺 `psutil` 也是 `None`，但成因不同。
    """

    bytes: Optional[int] = None
    rss_peak_mb: Optional[float] = None


@dataclass
class SamplesMeta:
    """`py-spy` 采样的元信息。

    `profiles` 是 2026-09-22 由 `4b` 补入的：该行要求解析产出含「profile 数」，而
    本类此前只有 duration / samples / errors 三项。补入后 `02-实施.md` §4 的
    `samples_meta` 一行须同步（已回写）。py-spy 正常只写一个 profile，故默认 1；
    **`0` 表示「没有任何可解析的 sampled profile」**，与默认值不同义。
    """

    duration: Optional[float] = None
    samples: Optional[int] = None
    errors: List[str] = field(default_factory=list)
    profiles: int = 1


@dataclass
class SingleStats:
    """`grain='single'` 的单次模拟分布。

    **本期预留、未实现**（P83 §3.3）：`Plan.validate()` 对 `grain='single'` 构造期
    抛 `ValueError`，故 `RunResult.single` 恒为 `None`。类型与字段保留不删，以便
    将来实现该档时不必改动记录格式。
    """

    min: float
    median: float
    max: float


# ── 环境指纹 ─────────────────────────────────────────────


@dataclass
class EnvFingerprint:
    """本次测量的环境指纹。

    基线按「核数区间 + OS 版本」分组，同组内比比值、跨组只比阶段占比；本记录
    提供分组所需的原始读数。**只有一台基准机时，须在基线文件中显式写明适用范围，
    而不是假装跨机器可比。**
    """

    cpu: str = ''
    cores: int = 0
    os: str = ''
    python: str = ''
    code_version: str = ''
    qt_qpa_platform: Optional[str] = None
    """本次 `QT_QPA_PLATFORM` 取值（§3.11）。**可比性维度**，三种状态各有含义：

    - 具体取值（`'offscreen'` / `'windows'`）——Qt 路径的实际平台。`simulation` 用
      `offscreen`、`startup` 用真实 `windows`，两者不可混比
    - `''`（空串）——**本路径不适用**：`cli` / `inline` 不是 Qt 路径，没有这个变量。
      必须是一个**确定值**：若用 `None` 表示「不适用」，比对侧会把它读成「未记录」
      从而判不可比，`cli` 基线将**永久不可比**，G1 直接失效
    - `None`——**未记录**（该字段出现之前的老记录，或捕获失败）
    """

    @classmethod
    def capture(cls, qt_qpa_platform: Optional[str] = None) -> 'EnvFingerprint':
        """读取当前环境。`qt_qpa_platform` 取不到时由调用方传 `None`。"""
        from gacha_simulator._version import __version__

        return cls(
            cpu=platform.processor() or platform.machine(),
            cores=os.cpu_count() or 0,
            os=f'{platform.system()} {platform.release()}',
            python=platform.python_version(),
            code_version=__version__,
            qt_qpa_platform=qt_qpa_platform,
        )

    @property
    def machine_class(self) -> str:
        """机器类别标签（核数区间 + OS 版本）——基线分组键。

        **必须是路径安全的**：该值直接用作 `baselines/<机器类别>/` 的目录名
        （§3.6），故分隔符取 `_` 而非 `/`——用 `/` 会把单层目录变成两层嵌套，
        与「按机器类别分组」的单层结构不符。
        """
        if self.cores <= 4:
            band = '1-4'
        elif self.cores <= 8:
            band = '5-8'
        elif self.cores <= 16:
            band = '9-16'
        else:
            band = '17+'
        return f'{band}cores_{self.os}'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> 'EnvFingerprint':
        return _read(cls, data)


# ── RunResult ────────────────────────────────────────────


@dataclass
class RunResult:
    """一次测量的完整记录。字段表见模块 docstring。"""

    run_id: str
    timestamp: str
    path: str
    is_user_path: bool
    fingerprint: EnvFingerprint
    plan: Plan

    repeats: Optional[int] = None
    """实跑次数。**建基线时强制 ≥ 3**（门禁点在 `1f`）。`None` = 未记录。"""

    wall_median: Optional[float] = None
    wall_samples: List[float] = field(default_factory=list)
    """各次原始值。**必须保留**，不能只留中位数——否则无从判断方差。"""

    repeats_downgraded: bool = False
    """预估墙钟超 30 秒时降为 1 次并置 `True`。"""

    stages: Dict[str, float] = field(default_factory=dict)
    single: Optional[SingleStats] = None
    """**预留恒 `None`**（`grain='single'` 本期未实现）。"""

    functions: Optional[List[FuncStat]] = None
    """`cProfile` 合并结果。`None` 有三种成因，报告须区分：路径不可达
    （`gui-qt` / `webui`）、路径降级（§3.8 D9）、剖析故障（§3.8 D7）。"""

    resources: ResourceStats = field(default_factory=ResourceStats)
    return_compact: Optional[bool] = None
    samples_meta: Optional[SamplesMeta] = None
    not_comparable: bool = False
    """`function` 档为 `True`（§3.8 D6）——插桩开销 2-5x 使耗时不可信，**不参与
    基线比值**。"""

    warnings: List[str] = field(default_factory=list)

    # ── 序列化 ────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """记录形态。嵌套的 `fingerprint` / `plan` / 子记录一并展开为对象。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> 'RunResult':
        """读入一条记录。

        **容忍 `None` 字段与浮点**（§3.1 输入契约）：`None` 只允许出现在
        `Optional` 字段上，浮点按浮点读，不隐式取整。

        与 `plan.json` 一致，**未知键报错而非静默忽略**——记录里出现未知键意味着
        读写两侧版本不一致，此时任何比值比对都在比不可比的东西，早失败优于出一份
        看着正常的错报告。
        """
        return _read(cls, data)


# ── 通用读取器 ────────────────────────────────────────────

_HINT_CACHE: Dict[type, Dict[str, Any]] = {}


def _hints_of(cls: type) -> Dict[str, Any]:
    if cls not in _HINT_CACHE:
        _HINT_CACHE[cls] = get_type_hints(cls)
    return _HINT_CACHE[cls]


def _allows_none(hint: Any) -> bool:
    if hint is type(None):
        return True
    if get_origin(hint) in (Union, types.UnionType):
        return type(None) in get_args(hint)
    return False


def _unwrap_optional(hint: Any) -> Any:
    """把 `Optional[X]` / `X | None` 解包为 `X`。

    不解包则 `hint is int` 一类的判定会全部落空（`Optional[int]` 既不是 `int`
    也不是 `bool`），类型校验形同虚设。多成员 `Union` 无唯一解，原样返回。
    """
    if get_origin(hint) in (Union, types.UnionType):
        args = tuple(a for a in get_args(hint) if a is not type(None))
        if len(args) == 1:
            return args[0]
    return hint


def _read(cls: type, data: Mapping[str, Any]) -> Any:
    """按声明字段读取一个 dataclass。缺省键取默认值；未知键报错。"""
    if not isinstance(data, Mapping):
        raise ValueError(f'{cls.__name__} 记录必须是对象，收到 {type(data).__name__}')

    declared = {f.name: f for f in fields(cls)}
    unknown = sorted(set(data) - set(declared))
    if unknown:
        raise ValueError(f'{cls.__name__} 记录含未知键 {unknown}；合法键为 {sorted(declared)}')

    hints = _hints_of(cls)
    kwargs = {name: _decode(name, data[name], hints[name]) for name in declared if name in data}
    return cls(**kwargs)


def _decode(name: str, value: Any, hint: Any) -> Any:
    if value is None:
        if _allows_none(hint):
            return None
        raise ValueError(f'{name} 不接受 None（字段类型 {hint}）')

    hint = _unwrap_optional(hint)
    origin = get_origin(hint)

    if isinstance(hint, type) and is_dataclass(hint):
        if hint is Plan:
            # 重建历史记录里的 Plan 时须挂起规则 5：它判的是「现在能不能跑」，
            # 与「当时跑了什么」无关（见 plan.suspended_memory_check）。
            with suspended_memory_check():
                return Plan.from_dict(value)
        return _read(hint, value)

    if origin is list:
        (item_hint,) = get_args(hint) or (Any,)
        if not isinstance(value, (list, tuple)):
            raise ValueError(f'{name} 必须是数组，收到 {value!r}')
        return [_decode(f'{name}[]', item, item_hint) for item in value]

    if origin in (dict, Dict):
        args = get_args(hint)
        value_hint = args[1] if len(args) == 2 else Any
        if not isinstance(value, Mapping):
            raise ValueError(f'{name} 必须是对象，收到 {value!r}')
        return {k: _decode(f'{name}.{k}', v, value_hint) for k, v in value.items()}

    # bool 必须先于 int 判（isinstance(True, int) 为真）
    if hint is bool:
        if not isinstance(value, bool):
            raise ValueError(f'{name} 必须是布尔值，收到 {value!r}')
        return value
    if hint is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'{name} 必须是整数，收到 {value!r}')
        return value
    if hint is float:
        # 浮点字段接受 int（如 12 → 12.0），JSON 里整数是常见的写法
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'{name} 必须是数值，收到 {value!r}')
        return float(value)
    if hint is str:
        if not isinstance(value, str):
            raise ValueError(f'{name} 必须是字符串，收到 {value!r}')
        return value

    return value
