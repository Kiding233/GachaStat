"""`cProfile` 层：worker 侧注入原语（`6b`） + 父进程侧合并（`6c`）。

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
from typing import Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    'WorkerProfiler',
    'PROFILE_FILE_SUFFIX',
    'merge_profiles',
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


# ── 父进程侧合并（`6c`） ──────────────────────────────────


def merge_profiles(profile_dir: str) -> Tuple[Optional[List[tuple]], List[str]]:
    """扫描**本 run 的 profile 目录**并把 `pstats` 合并为函数级统计。

    返回 `(functions, warnings)`：`functions` 为
    `[(name, ncalls, tottime, cumtime), …]`（调用方转成 `FuncStat`），
    扫描不到或解析失败时返回 `(None, [成因])`。

    **只扫传入的那一个目录**——即 `<profile_dir>/<run_id>/`。不要扫父目录：产品路径上
    `gui-qt` 与 `webui` 在每次主模拟之后都会再跑一次 `run_batch_parallel` 抽不卡基线，
    共用父目录会把那些调用的调用链混进本次剖面（§3.8 D3）。

    **须在「运行 `run_batch_parallel` 的那一个进程」内调用**（AUDIT-BREAK-8②）：
    `cli` 路径上 `run_id` 由被测子进程生成，适配器进程既不知道目录名也扫不到它，
    故合并结果只能经 `--perf-json` 回传。

    三条软降级成因**彼此可区分**（D7 四条「剖析故障」 + 文件缺失一条）：
    目录不存在 / 目录内无 `.prof` 文件（worker 可能被 `terminate()` 提前终止）/
    单个文件解析失败（记为 warning，其余继续合并）。
    """
    import pstats

    warnings: List[str] = []
    if not profile_dir:
        return None, ['未指定 profile 目录——本次不做合并']

    directory = Path(profile_dir)
    if not directory.is_dir():
        return None, [f'profile 目录不存在（{profile_dir}）——本次不做合并']

    files = sorted(directory.glob(f'*{PROFILE_FILE_SUFFIX}'))
    if not files:
        return None, [
            f'profile 目录内没有任何 {PROFILE_FILE_SUFFIX} 文件（{profile_dir}）——'
            'worker 可能在采样窗口结束前被 terminate() 提前终止，剖面不可得（§3.8 D7）'
        ]

    stats = None
    for path in files:
        try:
            if stats is None:
                stats = pstats.Stats(str(path))
            else:
                stats.add(str(path))
        except Exception as exc:
            warnings.append(f'pstats 解析或合并失败（{path.name}）：{exc}（§3.8 D7）')

    if stats is None:
        return None, warnings or ['所有 profile 文件都解析失败（§3.8 D7）']

    rows: List[tuple] = []
    for (filename, line, func), (cc, nc, tt, ct, _callers) in stats.stats.items():
        rows.append((f'{filename}:{line}({func})', int(nc), float(tt), float(ct)))
    rows.sort(key=lambda row: (-row[2], row[0]))
    if not rows:
        warnings.append('合并后的 pstats 内没有任何函数条目（§3.8 D7）')
    return rows, warnings
