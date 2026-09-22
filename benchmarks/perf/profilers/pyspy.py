"""`py-spy` 调用封装——外部采样式现场剖析。

**分工（§6）**：`cProfile` 是插桩（调用次数精确、2-5x 开销、仅覆盖被插桩的进程），
`py-spy` 是外部采样（默认 100/s 读栈、通常 <5% 开销、`--subprocesses` 可覆盖子进程）。
**进基线的必须是确定性量，故用 `cProfile`；`py-spy` 用于阶段计时与 `cProfile` 都指不出
所以然时的现场勘查**（主进程串行段、IPC 等待、Qt 事件循环）。

**依赖边界**：`py-spy` 是独立可执行文件（`pip install py-spy`，但**不可 `import`**），
只进开发依赖，**不进发布产物**（附二决策 5）。

**失败一律软降级**（同 §3.8 D7 的方向）：可执行文件不存在、进程中途退出、超时——
一律返回带 `warnings` 的降级结果，**不抛异常**。现场勘查通常发生在用户正在使用的
机器上、对着一个跑着的进程，让剖析工具的失败把排查本身搞挂没有任何道理。

**本模块管「调用与解析」的调用侧**（`4a`）；speedscope 的解析在同模块下方（`4b`）。
**采样质量不属本平台职责、不在测试中断言**（§3.9 T5）。
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

__all__ = [
    'BINARY_NAME',
    'DEFAULT_RATE_HZ',
    'PySpyResult',
    'resolve_binary',
    'record',
    'dump',
]

logger = logging.getLogger(__name__)

BINARY_NAME = 'py-spy'
#: 默认采样频率（Hz）。100 是 py-spy 的默认值，也是「通常 <5% 开销」那一档。
DEFAULT_RATE_HZ = 100


@dataclass
class PySpyResult:
    """一次调用的结果。**四项状态分开表达**，不压成一个布尔值。"""

    available: bool
    """可执行文件是否找得到。`False` 即「本环境没有 py-spy」，属能力缺失而非错误。"""

    ok: bool
    """命令是否成功执行。`available=False` 时恒为 `False`。"""

    command: List[str] = field(default_factory=list)
    """实际执行的 argv（降级时可能为空，或含占位）。**记下来才能复盘**。"""

    output_path: Optional[str] = None
    stdout: str = ''
    stderr: str = ''
    duration: Optional[float] = None
    warnings: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.available and self.ok


def resolve_binary(explicit: Optional[str] = None) -> Optional[str]:
    """定位 `py-spy` 可执行文件；找不到返回 `None`。

    `explicit` 用于**注入不存在的路径**以测软降级（§3.9 T5）——显式给出却不存在时
    同样返回 `None`，不抛异常。
    """
    if explicit:
        return explicit if shutil.which(explicit) else None
    return shutil.which(BINARY_NAME)


def _degraded(reason: str, *, command: Optional[Sequence[str]] = None,
              available: bool = True) -> PySpyResult:
    return PySpyResult(available=available, ok=False,
                       command=list(command or []), warnings=[reason])


def _run(argv: Sequence[str], *, timeout: float) -> PySpyResult:
    """执行并软降级。**任何失败路径都不抛异常。**"""
    try:
        completed = subprocess.run(
            list(argv), capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return PySpyResult(
            available=True, ok=False, command=list(argv),
            warnings=[f'py-spy 调用超过超时 {timeout:.0f}s，已终止'],
        )
    except OSError as exc:
        return _degraded(f'py-spy 调用失败：{exc}', command=argv)

    result = PySpyResult(
        available=True, ok=completed.returncode == 0, command=list(argv),
        stdout=completed.stdout or '', stderr=completed.stderr or '',
    )
    if not result.ok:
        tail = (result.stderr or result.stdout or '').strip().splitlines()[-4:]
        result.warnings.append(
            f'py-spy 退出码 {completed.returncode}：' + ' | '.join(tail)
        )
    return result


def record(
    pid: int,
    *,
    duration: float,
    output: Optional[str] = None,
    subprocesses: bool = True,
    rate: Optional[int] = None,
    idle: bool = False,
    binary: Optional[str] = None,
    timeout: Optional[float] = None,
) -> PySpyResult:
    """`py-spy record`——采样式 profile，默认产出 speedscope 格式。

    `subprocesses=True` 覆盖子进程：本项目的计算主体在 `multiprocessing.Pool` 的 worker
    里，不覆盖子进程就只能采到父进程主线程的空等（实测父进程空等在
    `multiprocessing/pool.py:861`）。

    可执行文件不存在时返回 `available=False` 的降级结果，**不抛异常**。
    """
    resolved = resolve_binary(binary)
    if resolved is None:
        return _degraded(
            f'未找到 {BINARY_NAME} 可执行文件（它不可 import，须 `pip install py-spy` 后可用）；'
            '本次不做采样',
            available=False,
        )

    argv: List[str] = [resolved, 'record', '--pid', str(pid), '--format', 'speedscope']
    if subprocesses:
        argv.append('--subprocesses')
    if idle:
        argv.append('--idle')
    if rate:
        argv += ['--rate', str(rate)]
    if output:
        argv += ['--output', output]
    # `--duration` 让 record 自行收口；不设则须外部发信号停止（无人值守场景下不可靠）
    argv += ['--duration', str(duration)]

    result = _run(argv, timeout=timeout if timeout is not None else duration + 30.0)
    if output:
        result.output_path = output
    return result


def dump(pid: int, *, binary: Optional[str] = None, timeout: float = 60.0,
         subprocesses: bool = False) -> PySpyResult:
    """`py-spy dump`——当前调用栈的快照（文本形态，用于「这一刻卡在哪」）。

    与 `record` 的区别：不产出 profile 文件，只给一次快照。适合「进程卡住了，先看一眼」。
    """
    resolved = resolve_binary(binary)
    if resolved is None:
        return _degraded(
            f'未找到 {BINARY_NAME} 可执行文件；本次不做快照',
            available=False,
        )

    argv: List[str] = [resolved, 'dump', '--pid', str(pid)]
    if subprocesses:
        argv.append('--subprocesses')
    return _run(argv, timeout=timeout)


def self_test(binary: Optional[str] = None) -> PySpyResult:
    """跑一次 `--version`，回答「本环境能不能用 py-spy」。

    与 `record` / `dump` 同型的降级语义——`4c` 的「缺失时软降级」断言也走这条。
    """
    resolved = resolve_binary(binary)
    if resolved is None:
        return _degraded(f'未找到 {BINARY_NAME} 可执行文件', available=False)
    return _run([resolved, '--version'], timeout=30.0)
