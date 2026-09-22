"""`cProfile` 在 worker 侧的注入原语（`6b`）。

父进程侧的合并（`6c`）将作为同模块的另一个函数加入——本项只交付 worker 侧的开闭窗口。

**全平台唯一改动模拟热路径默认行为的地方**就在这里——它落在 `_wk_run_single` 内，
而 `_wk_run_single` 是 MPPool 路径上每次模拟的必经之处。

**三条不可回退的约束（§3.8）：**

1. **不改三元组 arity。** `_wk_run_single` 的 docstring 用 ⚠ 明确警告「四条 return
   的 arity 必须一致为 3」，父进程侧有 `len(result) == 3` 守卫。剖面结果**走文件**，
   不走返回通道
2. **不动 `CompactResult`、不动 `_RESULT_VERSION`。** 副产品：两者的形态完全不参与
3. **不在 `_wk_init` 里做进程级 `enable()`。** 实证依据（本机 Python 3.12.5 源码核验）：
   `run_batch_parallel` 用的是 `with MPPool(...) as mp_pool`，而
   `multiprocessing.pool.Pool.__exit__` 的实现是 `self.terminate()`——worker 被强杀，
   **`atexit` 处理器不会执行**，进程级 enable 的收尾本就不可靠

**开闭窗口围绕单次 `_run_single` 调用**（§3.8 D2）而不是进程级，理由两条：① 进程级
enable 会把父进程的循环、`CompactResult` 装配、`pstats` 写入全部采进剖面（兜底路径
下 `_run_single` 就在父进程内联执行），得到一份描述框架而非描述模拟的剖面；
② 收尾不可靠（见上）。

**覆盖边界（D2.1）：只有 MPPool 路径经过 `_wk_run_single`。** 单进程内联
（`max_workers <= 1`）与 `mp_failed` 兜底两条路径直接在父进程调 `_run_single`，
开闭窗口不生效、**不产出任何 profile 文件**。这不是缺陷而是边界——已由
`Plan.validate()` 的 D2.1 拒绝规则（`grain='function'` 且 `workers <= 1`）挡在构造期。
"""

from __future__ import annotations

import cProfile
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

__all__ = [
    'WorkerProfiler',
    'PROFILE_FILE_SUFFIX',
]

#: profile 文件后缀。文件名含 pid——同机多 worker 各自落盘，不含 pid 会互相覆盖。
PROFILE_FILE_SUFFIX = '.prof'


class WorkerProfiler:
    """一个 worker 进程的采样窗口控制器。**每个 worker 一个实例，各自从零计数。**

    `profile_count` 是 per-worker 语义（§3.8 D1）：该对象随 `env` 被 pickle 到每个
    worker，而注入点在 worker 侧，故每个 worker 各自采 `count` 次。一次
    `run_batch_parallel(N, W)` 实际被插桩的样本数是 `count × W`。
    """

    def __init__(self, *, profile_dir: str, skip: int = 2, count: int = 50,
                 label: str = 'worker') -> None:
        self.profile_dir = str(profile_dir or '')
        self.skip = max(0, int(skip))
        self.count = max(1, int(count))
        self.label = label
        self.seen = 0
        self._profiler: Optional[cProfile.Profile] = None
        self._dumped_files = 0
        self._disabled_reason: Optional[str] = None

    # ── 判定 ─────────────────────────────────────────────

    @property
    def path(self) -> str:
        """本 worker **当前**要写的落盘路径（含 pid 与调用序号）。

        **含 pid**：同机多 worker 不撞名；**含序号**：同一 worker 的多次采样各写各的，
        不互相覆盖。
        """
        return os.path.join(
            self.profile_dir,
            f'{self.label}-{os.getpid()}-{self.seen}{PROFILE_FILE_SUFFIX}',
        )

    @property
    def disabled_reason(self) -> Optional[str]:
        """软降级成因（`None` 表示未降级）。"""
        return self._disabled_reason

    @property
    def dumped(self) -> int:
        """已落盘的剖面文件数——`6c` 合并时的输入条数，也是 T4 的断言对象。"""
        return self._dumped_files

    def _in_window(self, index: int) -> bool:
        """第 `index` 次调用（0 起）是否落在采样窗口内。

        窗口是 `[skip, skip + count)`——**闭开区间**。跳过的前 `skip` 次是 warmup
        （§3.8 D4）：第 1 次调用含 `_run_single` 的懒加载 import 开销——`_wk_init`
        刻意不预导入 `core` / `service`，避免 Windows spawn 下各 worker 同时加载
        scipy 大 DLL。
        """
        if self._disabled_reason:
            return False
        return self.skip <= index < self.skip + self.count

    def should_sample(self) -> bool:
        """**下一次**调用是否会被采样（按当前计数器判定）。

        与 `window()` 内的判定共用 `_in_window`，口径只有一处。
        """
        return self._in_window(self.seen)

    # ── 窗口 ─────────────────────────────────────────────

    @contextmanager
    def window(self) -> Iterator[None]:
        """围绕**单次** `_run_single` 调用的开闭窗口。

        **失败一律软降级**（D7）：`enable` / `dump_stats` 抛错时记成因并从此不再采样，
        **绝不让剖析失败冒泡到模拟**——测量工具不得伤及被测对象。
        """
        index = self.seen
        self.seen += 1

        if not self._in_window(index):
            yield
            return

        profiler = cProfile.Profile()
        try:
            profiler.enable()
        except Exception as exc:  # pragma: no cover - cProfile 极少不可用
            self._disabled_reason = f'cProfile 不可用：{exc}'
            logger.warning('cProfile enable 失败，已停用剖析：%s', exc)
            yield
            return

        try:
            yield
        finally:
            try:
                profiler.disable()
            except Exception as exc:  # pragma: no cover
                self._disabled_reason = f'cProfile disable 失败：{exc}'
                return
            self._profiler = profiler
            # **每个采样调用各自落盘**，不是在「达上限」时一次性落盘。理由：worker
            # 处理的模拟次数常常小于 `count`（`n=100 / workers=18` 时每个 worker 只有
            # 几次），若攒到上限才写，**绝大多数运行会一个文件都不产**；而且
            # `Pool.__exit__` 走 `terminate()` 强杀 worker，攒到最后那次很可能根本
            # 没有机会执行（§3.8 D2 的实证依据）。逐次落盘同时把这两种失效都消掉——
            # 已完成的部分已经在磁盘上。采样上限（`count`）仍由 `_in_window` 约束。
            self._dump(index)

    def _dump(self, index: int) -> None:
        """把一个采样调用的剖面落盘（D3：结果走文件，不走返回通道）。"""
        profiler = self._profiler
        if profiler is None:
            return
        target = os.path.join(
            self.profile_dir,
            f'{self.label}-{os.getpid()}-{index}{PROFILE_FILE_SUFFIX}',
        )
        try:
            Path(self.profile_dir).mkdir(parents=True, exist_ok=True)
            profiler.dump_stats(target)
        except (OSError, ValueError) as exc:
            self._disabled_reason = f'profile 落盘失败（{target}）：{exc}'
            logger.warning('profile 落盘失败，已停用剖析：%s', exc)
            return
        self._dumped_files += 1
        self._profiler = None
