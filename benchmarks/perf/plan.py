"""测量规格：`Plan`（标量规格） + `PlanGrid`（因子多值容器）。

**本模块是 `Plan` 形态的唯一真值源**（P83 §6.0 `1b`）：`02-实施.md` §3 与
`01-理论.md` §4 均为其摘要，冲突以本模块为准。

安全协议的全部拒绝规则在 `Plan.validate()` 内实现（**构造期**，经
`__post_init__` 调用）——各条数值的唯一口径是 `P83 §3.4` 与 `§3.8`：

| 规则 | 拒绝条件 |
|---|---|
| 1 | `collector=False` 且 `n > 1000` |
| 4 | `collector=True` 且 `n > 1600` |
| 5 | 可用物理内存 < `max(2.0, workers × 0.75)` GB（`gui-qt` 按 `workers=1` 计并另加 0.5 GB） |
| D8 | `profile_count > 500`（per-worker 上限） |
| D2.1 | `grain='function'` 且 `workers <= 1`（只有 MPPool 路径经过 `_wk_run_single`） |
| §3.3 | `grain='single'`——本期未实现，声明即调用方编程错误 |
| §3.11 | `subject='startup'` 落到本期无落点的路径 / 档位（`3e`，见下） |

规则 1 与规则 4 的上限**互不包含**：若规则 1 沿用规则 4 的 1600，其拒绝集合会
成为规则 4 的真子集，而事故量级（60000 无收集器）恰好落在放行区间内。

`subject='startup'` 时 `STARTUP_IGNORED_FIELDS`（`n` / `workers` / `chunksize` /
`strategy_key` / `seed`）一律被忽略，故**规则 1 与规则 4 不适用**（决策 34）；
**规则 5 与 D8 仍然适用**——启动测量驱动的正是 `gui-qt` 冷进程，是四条路径中最
吃内存的形态。

**`startup` 的落点边界（`3e`，2026-09-22 定）：** 「被忽略」是一回事，「被忽略之后
还有没有人认领」是另一回事。`subject` 在三轴模型里与 `path` / `grain` 正交，故
`startup × cli` 一类组合在字段层面是可构造的；而本期只有 `3f-1` 认领了
`startup × gui-qt`（§3.11「适用范围：首个交付覆盖 `gui-qt`」，且 `cli` / `webui` 的
启动测量被明写为**两个独立增量**、不在本计划内）。若放行，入口薄壳会按 `plan.path`
派发到 `CliAdapter` 并**照常产出一条带 `subject='startup'` 的记录**——报告会把一次
普通的 cli 模拟说成启动测量，这是「报告说谎」，比拒绝更坏。故按 `grain='single'`
的同一处置（声明了平台不实现的组合即调用方编程错误）在 `validate()` 内拒绝。
"""

from __future__ import annotations

import json
import types
from contextlib import contextmanager
from dataclasses import MISSING, asdict, dataclass, fields, replace
from itertools import product
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

__all__ = [
    'Plan',
    'PlanGrid',
    'PLAN_FIELD_NAMES',
    'SafetyRuleError',
    'MemoryProbeUnavailable',
    'set_memory_query',
    'get_memory_query',
    'injected_memory_query',
    'suspended_memory_check',
    'N_MAX_NO_COLLECTOR',
    'N_MAX_WITH_COLLECTOR',
    'MEM_BASE_GB',
    'MEM_PER_WORKER_GB',
    'MEM_GUI_QT_EXTRA_GB',
    'PROFILE_COUNT_MAX',
    'STARTUP_IGNORED_FIELDS',
    'STARTUP_PATHS',
]

# ── 枚举域 ────────────────────────────────────────────────

SUBJECTS = ('simulation', 'startup')
PATHS = ('cli', 'gui-qt', 'webui', 'inline')
GRAINS = ('batch', 'stage', 'function')
#: 已在档位表中声明、但本期无任何子任务承接的粒度（P83 §3.3）。
NOT_IMPLEMENTED_GRAINS = ('single',)

#: `subject='startup'` 下**一律被忽略**的字段（P83 §3.11、决策 34）。
#:
#: **本常量是这条语义的唯一真值源**：`validate()` 的分支、`memory_requirement_gb()`
#: 的取值、以及 `ignored_fields()` 全部读它，避免「文档说五个、代码认三个」这类
#: 漂移。启动测量的被测对象是**一次冷进程启动**，与配置里的模拟规模、进程池宽度、
#: 随机种子、策略选择都无关——这五项因此不参与该次测量。
#:
#: `strategy_key` 虽被忽略，**仍是必填字段**（`Plan.from_dict()` 只对带默认值的键
#: 允许缺省）。填什么不影响读数，但填了不等于它生效——这是刻意的：把「必填」与
#: 「生效」两件事分开，胜过让一个被忽略的字段悄悄变成可选而无人察觉。
STARTUP_IGNORED_FIELDS = ('n', 'workers', 'chunksize', 'strategy_key', 'seed')

#: `subject='startup'` 在本期**有落点**的路径（P83 §3.11「适用范围：首个交付覆盖
#: `gui-qt`」）。`cli` / `webui` 的启动测量是独立增量、不在本计划 43 项内，故不在
#: 此列；组合落在列外时 `validate()` 拒绝，理由见模块 docstring 末段。
STARTUP_PATHS = ('gui-qt',)

# ── 安全协议数值（唯一口径 P83 §3.4「规则 1 / 4 / 5 的具体数值」） ──
#
# 性质：**初始值，不是测量结论**。若被实测证伪（例如某台机器 2.0 GB 余量下
# 仍 OOM），允许修订，但须在 `02-实施.md` 记录修订理由与原值，不得静默放宽。

N_MAX_NO_COLLECTOR = 1000
"""规则 1：无收集器时的独立 N 上限。父进程持有全部 `n` 份 `CompactResult`
与全部 `n` 份提取包（合计约 1996 KB/模拟，1000 份约 1.9 GB）。"""

N_MAX_WITH_COLLECTOR = 1600
"""规则 4：带收集器时的 N 上限。收集器只省下 `results` 列表，**提取包仍逐模拟
累积**（三条执行路径皆然），故父进程保留量仍与 `n` 线性相关。"""

MEM_BASE_GB = 2.0
"""规则 5：内存余量下限。"""

MEM_PER_WORKER_GB = 0.75
"""规则 5：每个 worker 的增量。"""

MEM_GUI_QT_EXTRA_GB = 0.5
"""规则 5：`gui-qt` 路径的额外增量（`MainWindow` 显示后 412 MB + 10 个
Chromium 子进程）。"""

PROFILE_COUNT_MAX = 500
"""D8 的硬上限，**per-worker** 语义（见 §3.8 D1）。"""


class SafetyRuleError(ValueError):
    """安全协议的拒绝。

    继承 `ValueError`：§3.9 T2 要求拒绝的形态是「构造期抛 `ValueError`」，
    而调用方（如 `1k` 的薄壳）需要把「安全协议拒绝」与「非法值」区分开来
    给出不同的退出信息，故保留独立类型。
    """


class MemoryProbeUnavailable(SafetyRuleError):
    """规则 5 读不到可用物理内存（缺 `psutil`）。

    §3.4「降级口径」第 1 条：**拒绝，不静默跳过**——内存阈值是防 OOM 的硬
    规则，读不到就不放行。**不得**降级为「读不到就跳过规则 5」。
    """


# ── 内存查询（规则 5 的可注入点） ──────────────────────────

_MEMORY_QUERY: Optional[Callable[[], float]] = None


def _default_memory_query() -> float:
    """默认实现：读真实系统内存，返回**可用物理内存**（GB）。

    口径是 `psutil.virtual_memory().available`——**非 `total`、非 `used`**。
    """
    try:
        import psutil
    except ImportError as exc:  # pragma: no cover - 取决于环境
        raise MemoryProbeUnavailable(
            '规则 5 需要 psutil 才能读取可用物理内存：缺 psutil，请安装 [dev] extras'
            '（`pip install -e ".[dev]"`）'
        ) from exc
    return psutil.virtual_memory().available / (1024 ** 3)


def set_memory_query(fn: Optional[Callable[[], float]]) -> None:
    """设置内存查询实现；传 `None` 还原为默认实现（`psutil`）。

    供测试注入桩使用。**测试请优先用 `injected_memory_query()` 上下文管理器**
    ——裸调用会在用例失败时泄漏注入，污染后续用例（这正是 §3.8 D1 否决
    环境变量那条理由：进程全局隐式状态会泄漏）。
    """
    global _MEMORY_QUERY
    _MEMORY_QUERY = fn


def get_memory_query() -> Callable[[], float]:
    """返回当前生效的内存查询实现（默认 `psutil`）。"""
    return _MEMORY_QUERY or _default_memory_query


@contextmanager
def injected_memory_query(fn: Callable[[], float]) -> Iterator[None]:
    """临时注入内存查询实现，退出即还原（异常路径同样还原）。"""
    global _MEMORY_QUERY
    previous = _MEMORY_QUERY
    _MEMORY_QUERY = fn
    try:
        yield
    finally:
        _MEMORY_QUERY = previous


@contextmanager
def suspended_memory_check() -> Iterator[None]:
    """临时让规则 5 放行——**仅用于重建历史记录里的 `Plan`**。

    读一条历史 `RunResult` 需要重建它携带的 `Plan`，而规则 5 判的是「**现在**
    这台机器能不能跑」，与「**当时**跑了什么」无关。低内存时读不了历史基线是
    荒谬的，且会让 `1f` 的比值比对随机器负载随机失败。

    故为记录读取提供这个**显式命名**的逃生口。除记录重建外不得使用——它绕过
    的是防 OOM 的硬规则，误用即等于取消规则 5。
    """
    with injected_memory_query(lambda: float('inf')):
        yield


# ── Plan ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Plan:
    """一次测量的标量规格。

    因子的多值扫描**不进本类**，由 `PlanGrid` 承载（P83 §3.3「`Plan` 自身只
    承载标量规格」）。

    `collector` 是**如实申报 + 校验**字段，不是运行期开关：适配器必须按本路径
    的真实驱动填写，平台不因它改变驱动方式。**默认取 `False` 而非 `True`
    （fail-safe）**——三条产品入口（`cli` / `gui-qt` / `webui`）实际都不传
    `on_result`，只有 `inline` 传；默认 `False` 使漏填时落入**更严**的规则 1，
    而非静默放宽到规则 4 的上限。
    """

    # —— 模拟规格 ——
    config_path: str
    strategy_key: str
    strategy_params: Dict[str, Any]
    n: int
    workers: int
    seed: int
    chunksize: Optional[int] = None

    # —— 三轴 ——
    subject: str = 'simulation'
    """测什么：`'simulation'` 是一次批量模拟，`'startup'` 是一次冷进程启动。

    取 `'startup'` 时 `STARTUP_IGNORED_FIELDS` 五个字段一律被忽略
    （`ignored_fields()` 可查），且只在本期有落点的路径上可构造——边界与理由见
    模块 docstring 末段与 `_validate_startup()`。
    """

    path: str = 'cli'
    grain: str = 'stage'

    # —— 测量政策 ——
    repeats: int = 3
    """重复测量次数，取中位数。**建基线时强制 ≥ 3**（门禁点在 `1f`：
    它是唯一写 `baselines/` 的地方）。"""

    collector: bool = False
    py_spy: bool = False

    # —— 阶段 6 的四个触发字段（§3.8 D1）——
    #
    # 注入点是「调用方在拿到 `env` 之后直接赋值」，**不经 `SimulationEnvBuilder`
    # 的显式 keyword 表**（两张表内均无 `profile_*`）。顺序是硬要求：先设字段、
    # 再调 `run_batch_parallel`——在 `run_batch_parallel` 内部设置无效，彼时
    # `env` 已 pickle 给 worker。
    profile_enabled: bool = False
    """总开关。"""

    profile_dir: str = ''
    """**run 级父目录**；实际落盘在 `<profile_dir>/<run_id>/`（§3.8 D3）。
    空则不落盘。"""

    profile_skip: int = 2
    """前 N 次调用不采样（warmup）。第 1 次调用含懒加载 import 开销，从第 1 次
    开始采样会把 import 算成热点。"""

    profile_count: int = 50
    """**每个 worker 进程各自**采样多少次后关闭（per-worker，非本次 plan 的
    总量）。真实插桩比例是 `profile_count × workers / n`，不是
    `profile_count / n`。"""

    note: str = ''

    # ── 构造期校验 ────────────────────────────────────────

    def __post_init__(self) -> None:
        self.validate()

    def validate(self, *, memory_query: Optional[Callable[[], float]] = None) -> None:
        """安全协议的拒绝规则。构造期由 `__post_init__` 自动调用。

        `memory_query` 显式传入时优先于全局注入点，便于单点覆盖。
        """
        self._validate_shape()
        self._validate_startup()
        self._validate_profile_rules()
        self._validate_n_limits()
        self._validate_memory(memory_query)

    # 形态与枚举（非法值一律报错退出，不静默取默认——「参数键名即契约」）
    def _validate_shape(self) -> None:
        for name in ('n', 'workers', 'seed'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f'Plan.{name} 必须是 int，收到 {value!r}')
        if self.n <= 0:
            raise ValueError(f'Plan.n 必须为正整数，收到 {self.n}')
        if self.workers <= 0:
            raise ValueError(f'Plan.workers 必须为正整数，收到 {self.workers}')
        if self.chunksize is not None:
            if isinstance(self.chunksize, bool) or not isinstance(self.chunksize, int):
                raise ValueError(f'Plan.chunksize 必须是 int 或 None，收到 {self.chunksize!r}')
            if self.chunksize <= 0:
                raise ValueError(f'Plan.chunksize 必须为正整数，收到 {self.chunksize}')
        if not isinstance(self.strategy_params, Mapping):
            raise ValueError(f'Plan.strategy_params 必须是对象，收到 {type(self.strategy_params).__name__}')
        if self.subject not in SUBJECTS:
            raise ValueError(f'Plan.subject 必须是 {SUBJECTS} 之一，收到 {self.subject!r}')
        if self.path not in PATHS:
            raise ValueError(f'Plan.path 必须是 {PATHS} 之一，收到 {self.path!r}')
        if self.grain in NOT_IMPLEMENTED_GRAINS:
            raise ValueError(
                f"Plan.grain='{self.grain}' 本期未实现（P83 §3.3）：该档在 43 项子任务中"
                '无任何承接、也无采集通道，声明一个平台不实现的粒度属调用方编程错误。'
                '实现该档须先定义「逐次模拟时长」的采集通道后再删除本条拒绝规则。'
            )
        if self.grain not in GRAINS:
            raise ValueError(f'Plan.grain 必须是 {GRAINS} 之一，收到 {self.grain!r}')
        if self.repeats < 1:
            raise ValueError(f'Plan.repeats 必须 >= 1，收到 {self.repeats}')
        if self.profile_skip < 0:
            raise ValueError(f'Plan.profile_skip 必须 >= 0，收到 {self.profile_skip}')

    # `subject='startup'` 的语义与落点边界（`3e`）
    def ignored_fields(self) -> tuple:
        """本次 plan 下**被忽略**的字段名（`subject='startup'` 时为
        `STARTUP_IGNORED_FIELDS`，否则为空）。

        供消费者（`3f-1` 的适配器、报告格式化）在**不重抄规则**的前提下知道
        「哪些因子对本条记录无意义」——例如因子扫描在 `startup` 下扫 `n`，产出的
        各格读数必然相同，读的人需要能看出这一点而不是以为扫描生效了。
        """
        return STARTUP_IGNORED_FIELDS if self.subject == 'startup' else ()

    def _validate_startup(self) -> None:
        """`startup` 变体的落点边界（`3e`）。

        只拒**本期无落点**的组合，不拒有落点的：`startup × gui-qt × stage`
        （`3f-1`）与 `startup × gui-qt × batch`（只要总墙钟）都放行。
        """
        if self.subject != 'startup':
            return
        if self.path not in STARTUP_PATHS:
            raise ValueError(
                f"Plan.subject='startup' 本期只在路径 {STARTUP_PATHS} 上有落点，"
                f'收到 path={self.path!r}（P83 §3.11「适用范围」：首个交付覆盖 gui-qt；'
                'cli / webui 的启动测量是独立增量、不在本计划 43 项内）。'
                '放行本条会让入口薄壳按 plan.path 派发到该路径的适配器并照常产出一条'
                "带 subject='startup' 的记录——报告会把一次普通模拟说成启动测量。"
                '补上该路径须先定义它自己的启动分段并登记到 §四。'
            )
        if self.grain == 'function':
            raise ValueError(
                "Plan.subject='startup' 不支持 grain='function'：function 档的落点是"
                '「围绕单次 _run_single 的开闭窗口」（§3.8 D2），而启动测量测的是一次'
                '冷进程启动，进程内没有 worker 池、也没有 _wk_run_single 调用点。'
                '该组合本期无任何采集落点，声明即调用方编程错误。'
            )
        if self.profile_enabled:
            raise ValueError(
                "Plan.subject='startup' 不支持 profile_enabled=True：§3.8 D1 的四字段"
                '注入通道落在 run_batch_parallel 的 worker 路径上，而 main.py 的冷'
                '子进程根本不经过它。该组合本期无任何采集落点；要测启动期热点须先'
                '定义它自己的采集通道（§3.11 的 8 段只有计时，无函数级统计）。'
            )

    # D8 / D2.1
    def _validate_profile_rules(self) -> None:
        if self.profile_count < 1:
            raise ValueError(f'Plan.profile_count 必须 >= 1，收到 {self.profile_count}')
        if self.profile_count > PROFILE_COUNT_MAX:
            raise SafetyRuleError(
                f'§3.8 D8：Plan.profile_count={self.profile_count} 超过硬上限 '
                f'{PROFILE_COUNT_MAX}（per-worker 语义——workers 个进程各自最多驻留 '
                '该数量次调用的剖面统计，内存估算须按 workers x profile_count 计）'
            )
        if self.grain == 'function' and self.workers <= 1:
            raise SafetyRuleError(
                f"§3.8 D2.1：grain='function' 要求 workers >= 2，收到 workers={self.workers}。"
                '三条执行路径中只有 MPPool 路径经过 _wk_run_single，单进程内联与 mp_failed '
                '兜底路径的开闭窗口不生效、不产出任何 profile 文件。'
            )

    # 规则 1 / 4
    def _validate_n_limits(self) -> None:
        if self.subject == 'startup':
            # 决策 34：startup 下 n / workers 被忽略（STARTUP_IGNORED_FIELDS），
            # 规则 1 与 4 的对象不存在。
            return
        if self.collector:
            if self.n > N_MAX_WITH_COLLECTOR:
                raise SafetyRuleError(
                    f'§3.4 规则 4：collector=True 时 n 上限为 {N_MAX_WITH_COLLECTOR}，'
                    f'收到 n={self.n}。更长的扫描须拆成多条 plan。'
                )
        else:
            if self.n > N_MAX_NO_COLLECTOR:
                raise SafetyRuleError(
                    f'§3.4 规则 1：无收集器时 n 上限为 {N_MAX_NO_COLLECTOR}，收到 n={self.n}。'
                    '无收集器时父进程持有全部 n 份 CompactResult 与全部 n 份提取包（约 '
                    '1996 KB/模拟）。'
                )

    # 规则 5
    def memory_requirement_gb(self) -> float:
        """本次 plan 的内存余量下限（GB）。

        两条特例都由「本形态必然驱动一个 GUI 冷进程」推出，故合并为一个谓词：

        - `gui-qt` 路径：`MainWindow` 显示后 412 MB + 10 个 Chromium 子进程
        - `subject='startup'`：它驱动的**正是** `gui-qt` 冷进程（§3.11），
          `n` / `workers` 被忽略并不意味着内存需求变小——实测那次启动 RSS 峰值
          368 MB、10 个 Chromium 子进程，是四条路径中最吃内存的形态。豁免它
          等于在唯一需要该防线的场景关掉防线。

        两者都按 `workers = 1` 计并另加 `MEM_GUI_QT_EXTRA_GB`。
        """
        gui_like = self.subject == 'startup' or self.path == 'gui-qt'
        effective_workers = 1 if gui_like else self.workers
        required = max(MEM_BASE_GB, effective_workers * MEM_PER_WORKER_GB)
        if gui_like:
            required += MEM_GUI_QT_EXTRA_GB
        return required

    def _validate_memory(self, memory_query: Optional[Callable[[], float]]) -> None:
        query = memory_query or get_memory_query()
        available = query()
        required = self.memory_requirement_gb()
        if available < required:
            raise SafetyRuleError(
                f'§3.4 规则 5：可用物理内存 {available:.2f} GB 低于本次 plan 的下限 '
                f'{required:.2f} GB（path={self.path} / workers={self.workers}'
                f'{" / subject=startup" if self.subject == "startup" else ""}）。'
                '请等待内存释放或调小 workers。'
            )

    # ── 序列化（`plan.json` 的唯一读取器，AUDIT-BREAK-1） ──

    def canonical(self) -> str:
        """规范化 JSON 串，用于去重与哈希。键序稳定故同一 Plan 恒得同一串。"""
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    def __hash__(self) -> int:
        return hash(self.canonical())

    def to_dict(self) -> Dict[str, Any]:
        """`plan.json` 的形态：顶层对象，键名与字段一一对应。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> 'Plan':
        """读入 `plan.json`。

        规格（P83 §3.1 输入契约）：**缺省键取字段默认值；未知键与非法值报错**
        ——不静默忽略，「参数键名即契约」是本库一贯口径。`None` 只允许出现在
        可为 `None` 的字段上（当前仅 `chunksize`）。
        """
        if not isinstance(data, Mapping):
            raise ValueError(f'plan.json 顶层必须是对象，收到 {type(data).__name__}')

        declared = {f.name: f for f in fields(cls)}
        hints = _resolve_hints()
        unknown = sorted(set(data) - set(declared))
        if unknown:
            raise ValueError(f'plan.json 含未知键 {unknown}；合法键为 {sorted(declared)}')

        kwargs: Dict[str, Any] = {}
        for name, f in declared.items():
            if name in data:
                kwargs[name] = _coerce_field(name, data[name], hints[name])
            elif f.default is MISSING and f.default_factory is MISSING:  # type: ignore[misc]
                raise ValueError(f'plan.json 缺必填键 {name!r}')
        return cls(**kwargs)


_HINTS: Optional[Dict[str, Any]] = None


def _resolve_hints() -> Dict[str, Any]:
    """解析 `Plan` 的注解为真实类型对象（本模块用了 `from __future__ import
    annotations`，`Field.type` 是字符串，不能直接拿来做类型判定）。"""
    global _HINTS
    if _HINTS is None:
        _HINTS = get_type_hints(Plan)
    return _HINTS


def _allows_none(hint: Any) -> bool:
    if hint is type(None):
        return True
    if get_origin(hint) in (Union, types.UnionType):
        return type(None) in get_args(hint)
    return False


def _unwrap_optional(hint: Any) -> Any:
    """把 `Optional[X]` / `X | None` 解包为 `X`（多成员 `Union` 原样返回）。

    不解包则 `hint is int` 一类的判定会全部落空——`Optional[int]` 既不是 `int`
    也不是 `bool`，于是 `chunksize` 的类型校验会静默退化为「照单全收」。
    """
    if get_origin(hint) in (Union, types.UnionType):
        args = tuple(a for a in get_args(hint) if a is not type(None))
        if len(args) == 1:
            return args[0]
    return hint


def _coerce_field(name: str, value: Any, hint: Any) -> Any:
    """按**解析后的真实类型**校验。非法值报错，不做隐式转换。"""
    if value is None:
        if _allows_none(hint):
            return None
        raise ValueError(f'Plan.{name} 不接受 None（字段类型 {hint}）')

    hint = _unwrap_optional(hint)
    origin = get_origin(hint)
    if origin in (dict, Dict):
        if not isinstance(value, Mapping):
            raise ValueError(f'Plan.{name} 必须是对象，收到 {value!r}')
        return dict(value)

    # bool 必须先于 int 判：`isinstance(True, int)` 为真，写反会放行 1/0 冒充布尔值
    if hint is bool:
        if not isinstance(value, bool):
            raise ValueError(f'Plan.{name} 必须是布尔值，收到 {value!r}')
        return value

    if hint is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f'Plan.{name} 必须是整数，收到 {value!r}')
        return value

    if hint is str:
        if not isinstance(value, str):
            raise ValueError(f'Plan.{name} 必须是字符串，收到 {value!r}')
        return value

    return value


PLAN_FIELD_NAMES = tuple(f.name for f in fields(Plan))
"""可用于因子扫描的字段名（只读投影，供 `PlanGrid` 校验与文档使用）。"""


# ── PlanGrid ─────────────────────────────────────────────


@dataclass(frozen=True)
class PlanGrid:
    """因子的多值容器：`expand()` 产出笛卡尔积。

    §3.3「一个 plan 展开为因子的笛卡尔积，每格一条记录」的形态落定——展开的
    **输入**是 `PlanGrid`，**输出**是 `List[Plan]`。因子的多值因此不塞进 `Plan`
    字段（否则 `n ∈ {100, 1000}` 这类扫描无处安放）。

    每格经 `dataclasses.replace()` 构造，故**逐格重新跑 `validate()`**：因子把
    `n` 推出规则 1 / 4 的上限时，该格就地拒绝，不会被静默纳入扫描。
    """

    base: Plan
    factors: Dict[str, Sequence[Any]]

    def expand(self) -> List[Plan]:
        """笛卡尔积展开并按 `Plan.canonical()` 去重，保持因子声明顺序。"""
        unknown = sorted(set(self.factors) - set(PLAN_FIELD_NAMES))
        if unknown:
            raise ValueError(
                f'PlanGrid.factors 含未知字段 {unknown}；合法字段为 {list(PLAN_FIELD_NAMES)}'
            )
        ignored = sorted(set(self.factors) & set(self.base.ignored_fields()))
        if ignored:
            # `startup` 下扫被忽略的字段，展开出的每一格读数必然相同（它们不参与
            # 这次测量），但每格都要真起一次冷进程——扫描看起来生效了、实际只是
            # 把同一次测量重复 N 遍。这与 `single` 档同属「声明了不生效的东西」，
            # 故同样在入口处拒绝而不是产出一堆相同读数等人去发现。
            raise ValueError(
                f'PlanGrid.factors 含 {ignored}，而这些字段在 subject='
                f'{self.base.subject!r} 下被忽略（{STARTUP_IGNORED_FIELDS}）——'
                '展开出的各格读数必然相同，扫描看起来生效、实际只是重复同一次测量。'
                '请从 factors 中去掉这些字段。'
            )
        for name, values in self.factors.items():
            if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
                raise ValueError(f'PlanGrid.factors[{name!r}] 必须是序列，收到 {type(values).__name__}')
            if not values:
                raise ValueError(f'PlanGrid.factors[{name!r}] 为空——空因子不会产出任何记录')

        names = list(self.factors)
        expanded: List[Plan] = []
        seen: set = set()
        for combination in product(*(self.factors[name] for name in names)):
            plan = replace(self.base, **dict(zip(names, combination)))
            key = plan.canonical()
            if key not in seen:
                seen.add(key)
                expanded.append(plan)
        return expanded
