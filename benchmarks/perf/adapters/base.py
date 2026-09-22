"""适配器契约与公共层。

**契约形态以本模块为唯一口径**（P83 §6.0 `1e-1`）：`2d`（`inline`）/ `3a`（`gui-qt`）
/ `5a`（`webui`）均消费本模块。

三层分工：

1. **本模块（公共层）**：`run(plan)` 的重复测量循环与中位数归一
2. **各适配器**：实现 `_run_once(plan)` 这一条**单次驱动**——建起路径环境、把
   `Plan` 翻译成该路径的输入、在正确的进程/线程边界上挂计时、以该路径自己的
   方式等待结束、归一成 `SingleRun`
3. **内核**（`plan` / `record` / `stage`）：只管「测什么、怎么算」

**约束 A：适配器不得新写驱动，只能修复或包装已有入口。** 判别式：任何一个适配器
如果需要「先写个脚本来跑」，说明它设计错了。

`collector` 是**如实申报**字段（§3.4）：它记录本适配器**是否真的**向
`run_batch_parallel` 传 `on_result`，平台不因它改变驱动方式。填错不会让路径真的
带上收集器，只会让报告说谎——故它是适配器契约，由 T3 契约测试断言。
"""

from __future__ import annotations

import logging
import os
import statistics
import subprocess
import tempfile
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import ClassVar, Dict, List, Optional, Tuple, Type

from benchmarks.perf.plan import Plan
from benchmarks.perf.record import (
    EnvFingerprint,
    FuncStat,
    ResourceStats,
    RunResult,
    SamplesMeta,
)

__all__ = [
    'Adapter',
    'SingleRun',
    'AdapterUnavailable',
    'AdapterError',
    'ADAPTERS',
    'register_adapter',
    'get_adapter',
    'load_adapters',
    'new_run_id',
    'utc_timestamp',
    'DOWNGRADE_THRESHOLD_SECONDS',
    'kill_process_tree',
]

logger = logging.getLogger(__name__)

#: 预估墙钟超过该值即降为 1 次重复并置 `repeats_downgraded`（§3.5）。
#:
#: **2026-09-22 由 30.0 修订为 60.0**（`1j` 执行时实测证伪，按 §3.4 的数值纪律记录
#: 原值与理由，非静默放宽）：
#:
#: 原值 30.0 与基线门禁（`register_baseline` 要求 `repeats >= 3`）在**平台自己定死的
#: 参数下互斥**。实测 `n=1000, workers=4` 单次墙钟 14.2s（`simulate` 12.3s），
#: `repeats=3` 的预估 42.7s > 30 → 必然降级 → 必然被基线门禁拒绝。后果不只是
#: `1j` 建不出基线（而 §3.13 要求 `sleep_ctl` 由基线反解），而是**平台无法为自己
#: 的头号配置建任何基线**：原值把「可建基线的单次墙钟」压到 10s 以下，而 `n=1000`
#: 本身就超过它。
#:
#: 60.0 的含义是「一次测量最多花一分钟」，仍是**有界的交互预算**；`n` 填错的那类
#: 风险（事故量级是分钟到小时）照样被挡住——单次超过 20s 仍会降级。
#:
#: **残留限制（未处置）：** 比本机慢一倍的机器上 `n=1000` 单次仍可能超 20s，届时
#: 依旧建不了基线。通用解是「预算由调用方给」（`Plan` 加字段），属 `1b` 的改动面，
#: 不在本轮范围内——已登记 `04-问题.md`。
DOWNGRADE_THRESHOLD_SECONDS = 60.0


def kill_process_tree(pid: int) -> None:
    """杀掉整棵进程树（规则 3）。

    **Windows 上杀父不杀子**：`multiprocessing` 的 worker、QtWebEngine 的
    Chromium 子进程都会在父进程死后残留，故必须经 `taskkill /T` 递归。本函数是
    `cli` 与 `gui-qt` 共用的收尾动作，置此以免两份实现悄悄漂移（两处漏一处就是
    一台机器上残留一堆进程，且只在超时路径上偶发）。

    **幂等**：进程已退出时 `taskkill` 返回非零，此处吞掉——收尾动作不该让整次
    测量失败（同 §3.8 D7 的方向）。
    """
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                       capture_output=True, check=False)
        return
    import signal  # pragma: no cover - 本项目只在 Windows 上跑

    try:  # pragma: no cover - 同上
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except OSError:
        pass


class AdapterError(RuntimeError):
    """适配器运行失败。"""


class AdapterUnavailable(AdapterError):
    """本环境跑不了这条路径（如无 PyQt6）。

    **不是错误，是能力缺失**——调用方应跳过而非报错（§二 G2：四条路径各有适配器
    即可，不要求每条都在每个环境里可跑）。
    """


@dataclass
class SingleRun:
    """一次单次驱动产出的全部读数。

    不含 `repeats` / `wall_median` / `wall_samples` / `repeats_downgraded` 四项——
    那是重复测量循环的产物，由公共层填（§3.5 的政策归属 `1e-1` 的公共层）。
    """

    wall: float
    stages: Dict[str, float] = field(default_factory=dict)
    resources: ResourceStats = field(default_factory=ResourceStats)
    functions: Optional[List[FuncStat]] = None
    samples_meta: Optional[SamplesMeta] = None
    return_compact: Optional[bool] = None
    not_comparable: bool = False
    run_id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    qt_qpa_platform: Optional[str] = None
    """本次运行的 `QT_QPA_PLATFORM` 取值，**由适配器显式报出**（`3f-1` 加入）。

    `None` = 由公共层的 `_qt_qpa_platform()` 决定（默认空串，Qt 路径覆写）。
    设了值则直接写进 `EnvFingerprint`。

    为何需要这个字段：启动测量驱动的是**独立冷子进程**，平台是父进程通过
    `Popen(env=...)` 给它的（`startup` 跑真实 `windows`、`simulation` 跑
    `offscreen`），父进程的 `os.environ` 里根本没有这个变量——若沿用「读本进程
    环境变量」的取法，`startup` 的记录会报出一个与本机实况无关的值。
    """


@contextmanager
def _profile_parent(profile_dir: str):
    """给出第二趟用的 profile 父目录：plan 给了就用它，没给就配一个临时目录。

    临时目录在本方法退出时清理。**清理的是系统临时目录，不是仓库里的任何东西**——
    与「禁止擅自删除文件」那条规则无关（那条管的是仓库产物）。
    """
    if profile_dir:
        yield profile_dir
        return
    with tempfile.TemporaryDirectory(prefix='p83-function-') as tmp:
        yield tmp


def new_run_id() -> str:
    """本次 run 的标识。

    §3.8 D3 要求 `profile_dir` 落到 `<profile_dir>/<run_id>/`，以隔离同一进程内
    多次 `run_batch_parallel` 调用（no_draw 基线重跑不得混入主模拟的剖面）。
    """
    return uuid.uuid4().hex[:12]


def utc_timestamp() -> str:
    """记录用时间戳（UTC，秒精度）。"""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Adapter(ABC):
    """一条测量路径。"""

    #: 路径标识，写入每条 `RunResult.path`（§3.2 约束 C：路径是一等维度）。
    name: ClassVar[str] = ''

    #: 是否用户真实走的路径（`inline` 为 `False`，其余为 `True`）。
    is_user_path: ClassVar[bool] = True

    #: 如实申报：本适配器是否真的向 `run_batch_parallel` 传 `on_result`（§3.4）。
    collector: ClassVar[bool] = False

    #: 本路径**结构上不产出**的段（§3.5 末表：`cli` 无分发器）。
    #: 传给 `normalize_stages(..., absent_by_design=...)`，使其与「应收未收」可区分。
    absent_stages: ClassVar[Tuple[str, ...]] = ()

    #: 硬超时（秒）。**绝不无超时等待**（§3.10 判定边界第 3 条）。
    timeout_seconds: ClassVar[float] = 3600.0

    @abstractmethod
    def available(self) -> bool:
        """本环境能否跑这条路径。**缺依赖时返回 `False` 而非报错。**"""

    @abstractmethod
    def _run_once(self, plan: Plan) -> SingleRun:
        """单次驱动。各适配器实现本方法，只此一处体现路径差异。"""

    # ── 公共层：重复测量 ─────────────────────────────────

    def run(self, plan: Plan) -> RunResult:
        """按 `Plan.repeats` 重复单次驱动，归一为一条 `RunResult`。

        政策（§3.5）：

        - 收集各次原始墙钟到 `wall_samples`，取**中位数**写 `wall_median`
        - **预估墙钟超 `DOWNGRADE_THRESHOLD_SECONDS` 时降为 1 次**并把
          `repeats_downgraded` 置 `True`（该阈值的取值与两次修订理由见其定义处）
          （首次运行兼任试跑，用它的墙钟乘 `repeats` 作预估）
        - 阶段分解与资源计数取**首次**运行的产出——它们是确定性量、零噪声，
          重复测量只为压墙钟噪声，对确定性量没有意义（§3.5）

        `grain='function'` 走**两趟**（§3.8 D6），见 `_run_two_pass`。
        """
        if not self.available():
            raise AdapterUnavailable(f'{self.name} 适配器在本环境不可用（available() 为 False）')

        if plan.grain == 'function':
            return self._run_two_pass(plan)

        return self._measure(plan)

    def _measure(self, plan: Plan, *, extra_warnings: Optional[List[str]] = None) -> RunResult:
        """重复测量本体。`_run_two_pass` 复用它跑耗时那一趟。"""
        planned = max(1, int(plan.repeats))
        first = self._run_once(plan)
        samples: List[float] = [first.wall]
        downgraded = False

        # `subject='startup'` **不参与自动降级**（2026-09-22 定）。三条理由：
        # ① 启动的单次代价是固定成本（冷进程 + 10 个 Chromium 子进程，实测 8-10s），
        #    `repeats` 缩不了它，降级省不下什么；
        # ② 该启发式防的是「`n` 填大了导致一条 plan 跑很久」，而 `startup` 下 `n` /
        #    `workers` 本就**被忽略**（`plan.STARTUP_IGNORED_FIELDS`），这条风险不存在；
        # ③ 一旦降级，`register_baseline` 的 `repeats >= 3` 会拒绝入库——**启动测量
        #    将永远无法建立基线**，而「启动有没有变慢」正是 G6 要回答的问题。
        # 重复次数仍由调用方经 `Plan.repeats` 显式控制，不因此失控。
        # **豁免的是「降级」这一动作，不是整个重复循环**——外层的 `planned > 1` 仍须
        # 照常跑满 repeats，否则豁免会变成「静默只跑一次」。
        exempt_from_downgrade = plan.subject == 'startup'
        if planned > 1:
            over_budget = (not exempt_from_downgrade
                           and first.wall * planned > DOWNGRADE_THRESHOLD_SECONDS)
            if over_budget:
                downgraded = True
                logger.info(
                    '%s：预估墙钟 %.1fs 超过 %.0fs，repeats 由 %d 降为 1',
                    self.name, first.wall * planned, DOWNGRADE_THRESHOLD_SECONDS, planned,
                )
            else:
                for _ in range(planned - 1):
                    samples.append(self._run_once(plan).wall)

        warnings = list(first.warnings)
        if downgraded:
            warnings.append(
                f'repeats 由 {planned} 降为 1：预估墙钟 {first.wall * planned:.1f}s 超过 '
                f'{DOWNGRADE_THRESHOLD_SECONDS:.0f}s（§3.5）。该记录不得作为基线'
                '（建基线强制 repeats >= 3）。'
            )
        warnings.extend(extra_warnings or [])

        return RunResult(
            run_id=first.run_id or new_run_id(),
            timestamp=utc_timestamp(),
            path=self.name,
            is_user_path=self.is_user_path,
            fingerprint=EnvFingerprint.capture(
                first.qt_qpa_platform if first.qt_qpa_platform is not None
                else self._qt_qpa_platform(first)
            ),
            plan=plan,
            repeats=len(samples),
            wall_median=statistics.median(samples),
            wall_samples=list(samples),
            repeats_downgraded=downgraded,
            stages=dict(first.stages),
            single=None,  # grain='single' 本期未实现（§3.3）
            functions=first.functions,
            resources=first.resources,
            return_compact=first.return_compact,
            samples_meta=first.samples_meta,
            not_comparable=first.not_comparable or plan.grain == 'function',
            warnings=warnings,
        )

    def _run_two_pass(self, plan: Plan) -> RunResult:
        """`grain='function'` 的**两趟跑**（§3.8 D6）。

        cProfile 有 2-5x 插桩开销（§3.8 D3 的验证记录实测 +124%），**同一次运行里既采
        剖面又报耗时是不诚实的**——耗时数字被插桩放大了一倍以上。故：

        1. 第一趟：`grain='stage'` 且**关掉剖析** → 取可信的耗时
        2. 第二趟：带 profiler → 取函数级统计
        3. 合并为一条记录，并把 `not_comparable` 置 `True`

        `not_comparable` 的消费者是 `1f` 的比值比对（它据此把 `wall_median` 排除出
        比值，`excluded` 里写明成因）——语义的提供者与消费者在此对齐。

        第二趟需要的 `profile_dir` 若 plan 未给，**自动配一个临时父目录**并在本方法
        返回前清理：否则 `grain='function'` 必须由调用方额外设置 `profile_dir` 才可能
        有用，那是个容易踩空的隐性前置条件。
        """
        timing_plan = replace(plan, grain='stage', profile_enabled=False)
        result = self._measure(timing_plan, extra_warnings=[
            'function 档走两趟（§3.8 D6）：耗时取自**不带插桩**的第一趟，函数统计取自'
            '第二趟——两者不是同一次运行的产物。故 wall_median 标注 not_comparable'
            '并被基线比值排除。'
        ])

        warnings = list(result.warnings)
        with _profile_parent(plan.profile_dir) as parent:
            profiled_plan = replace(plan, profile_enabled=True, repeats=1,
                                    profile_dir=parent, grain='function')
            profiled = self._run_once(profiled_plan)
            functions = profiled.functions
        warnings.extend(w for w in profiled.warnings if w not in warnings)

        if functions is None:
            warnings.append(
                '第二趟未产出任何函数级统计（成因见上方剖析告警）；'
                'RunResult.functions 为 None，但读的人能从告警看出是哪种成因'
            )
        return replace(result, functions=functions, not_comparable=True, warnings=warnings)

    def _qt_qpa_platform(self, run: SingleRun) -> Optional[str]:
        """本次运行的 `QT_QPA_PLATFORM` 取值（§3.11）。

        **默认返回空串，表示「本路径不适用」**——`cli` / `inline` 不是 Qt 路径，没有
        这个变量。这里**不能返回 `None`**：`None` 的语义是「未记录」，比对侧据此判
        不可比，而 `qt_qpa_platform` 是可比性维度之一，于是 `cli` 基线会**永久不可比**、
        G1（回答「这次改动有没有变慢」）直接失效。空串是一个确定值，同路径内恒相等。

        Qt 路径的适配器（`gui-qt` / 启动测量）覆写本方法，报出真实平台。
        """
        return ''


# ── 适配器注册表 ─────────────────────────────────────────

ADAPTERS: Dict[str, Type[Adapter]] = {}


def register_adapter(cls: Type[Adapter]) -> Type[Adapter]:
    """注册一个适配器类（按 `cls.name` 索引）。重名即报错。"""
    if not cls.name:
        raise ValueError(f'{cls.__name__} 未声明 name')
    existing = ADAPTERS.get(cls.name)
    if existing is not None and existing is not cls:
        raise ValueError(f'适配器名 {cls.name!r} 已被 {existing.__name__} 占用')
    ADAPTERS[cls.name] = cls
    return cls


def get_adapter(name: str) -> Adapter:
    """按路径名取适配器实例。未注册即报错并列出已注册者。"""
    load_adapters()
    try:
        return ADAPTERS[name]()
    except KeyError:
        raise AdapterError(
            f'未注册的路径 {name!r}；已注册：{sorted(ADAPTERS)}'
        ) from None


def load_adapters() -> Dict[str, Type[Adapter]]:
    """导入四条路径的适配器模块（已导入过的为 no-op）。

    四个模块随阶段 1 / 2 / 3 / 5 先后落地，故此处对**尚不存在的模块**静默跳过：
    它服务的是「阶段 1 只有 `cli` 一条路径」这一中间态。缺失情况由调用方按需
    检查（`get_adapter` 对未注册的路径会报错并列出已注册者），不是静默容忍。
    """
    for module in (
        'benchmarks.perf.adapters.cli',
        'benchmarks.perf.adapters.inline',
        'benchmarks.perf.adapters.gui_qt',
        'benchmarks.perf.adapters.webui',
    ):
        try:
            __import__(module)
        except ImportError as exc:  # 该阶段的适配器尚未落地
            logger.debug('适配器模块 %s 尚不可导入：%s', module, exc)
    return ADAPTERS
