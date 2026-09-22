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

from benchmarks.perf.record import SamplesMeta

__all__ = [
    'BINARY_NAME',
    'DEFAULT_RATE_HZ',
    'PySpyResult',
    'Hotspot',
    'SpeedscopeSummary',
    'resolve_binary',
    'record',
    'dump',
    'self_test',
    'parse_speedscope',
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


# ── speedscope 解析（`4b`） ───────────────────────────────
#
# 实测格式（py-spy 0.4.2，本机录制）：
#   {"$schema", "shared": {"frames": [{"name","file","line"}]},
#    "profiles": [{"type": "sampled", "unit": "seconds", "startValue", "endValue",
#                  "samples": [[帧索引…按 root→leaf 排列], …],
#                  "weights": [每个样本的时长（秒）]}],
#    "exporter": "py-spy@0.4.2", "name", "activeProfileIndex"}
#
# **自耗时**（self time）= 该帧作为**样本栈叶节点**出现的那些样本的权重之和；
# **总耗时**（total time）= 该帧出现在栈中任意位置的那些样本的权重之和。
# 这个区分是热点排序的关键——只看总耗时永远排在最外层框架上，指不出热点。


@dataclass
class Hotspot:
    """一个函数在采样剖面中的占比。"""

    name: str
    self_time: float
    total_time: float
    self_share: float
    """自耗时 / 采样总时长。**按它排序**。"""
    samples: int
    file: str = ''
    line: Optional[int] = None


@dataclass
class SpeedscopeSummary:
    """一次解析的产出。`meta` 直接可填进 `RunResult.samples_meta`。"""

    meta: SamplesMeta
    profile_count: int
    frame_count: int
    hotspots: List[Hotspot] = field(default_factory=list)
    path: Optional[str] = None

    def top(self, n: int = 10) -> List[Hotspot]:
        return self.hotspots[:n]


def parse_speedscope(source: object) -> SpeedscopeSummary:
    """解析 speedscope JSON（路径 / 已解析的 dict / JSON 文本皆可）。

    **解析失败不抛异常**——把成因记进 `SamplesMeta.errors` 并返回空热点列表，与
    `record` / `dump` 的软降级同一方向。一份读不了的剖面不该让整个排查中断。
    """
    import json as _json
    from pathlib import Path as _Path

    errors: List[str] = []
    path: Optional[str] = None
    payload: object = source

    # 三种输入分开认：`Path`、**存在的文件路径字符串**、JSON 文本字符串；dict 直接用。
    # 不能把「所有 str」都当路径——那样 JSON 文本会被拿去 open()，报出的成因会是
    # 「文件不存在」而非「JSON 非法」。也不能反过来全当文本：那样一个写错的**路径**
    # 会报成「JSON 非法」，读的人会去查一段根本不存在的 JSON。
    # 判据是「听起来像不像 JSON」——以 `{` / `[` 开头才算文本。
    looks_like_json = isinstance(source, str) and source.lstrip()[:1] in ('{', '[')
    if isinstance(source, _Path) or (isinstance(source, str) and not looks_like_json):
        path = str(source)
        try:
            payload = _json.loads(_Path(source).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            return SpeedscopeSummary(
                meta=SamplesMeta(samples=None, profiles=0,
                                 errors=[f'读不到或解析不了 speedscope 文件（{source}）：{exc}']),
                profile_count=0, frame_count=0, path=path,
            )
    elif isinstance(source, str):
        path = f'<文本 {len(source)} 字符>'
        try:
            payload = _json.loads(source)
        except ValueError as exc:
            return SpeedscopeSummary(
                meta=SamplesMeta(samples=None, profiles=0,
                                 errors=[f'speedscope 文本不是合法 JSON：{exc}']),
                profile_count=0, frame_count=0, path=path,
            )

    if not isinstance(payload, dict):
        return SpeedscopeSummary(
            meta=SamplesMeta(samples=None, profiles=0,
                             errors=[f'speedscope 顶层必须是对象，收到 {type(payload).__name__}']),
            profile_count=0, frame_count=0, path=path,
        )

    shared = payload.get('shared') or {}
    frames = shared.get('frames') or []
    profiles = payload.get('profiles') or []
    if not isinstance(frames, list) or not isinstance(profiles, list):
        return SpeedscopeSummary(
            meta=SamplesMeta(samples=None, profiles=0,
                             errors=['speedscope 的 shared.frames / profiles 必须是数组']),
            profile_count=0, frame_count=0, path=path,
        )

    # **按函数名聚合，不按帧索引**：py-spy 为同一函数的每个「行号」各建一帧
    # （实测：inner_loop 在两个行号上各得一条），若按帧索引统计，一个函数会被拆成
    # 多条热点、排名被摊薄。热点列表要回答的是「哪个函数占得多」，故按 name 聚合，
    # 并保留**贡献自耗时最多的那一帧**的 file/line 作为代表位置。
    self_time: dict = {}
    total_time: dict = {}
    sample_counts: dict = {}
    location: dict = {}
    total_duration = 0.0
    total_samples = 0
    sampled_profiles = 0

    def _frame_of(index: object) -> dict:
        if isinstance(index, int) and 0 <= index < len(frames) and isinstance(frames[index], dict):
            return frames[index]
        return {}

    for index, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            errors.append(f'profiles[{index}] 不是对象，已跳过')
            continue
        if profile.get('type') != 'sampled':
            # py-spy 只产出 sampled；evented 形态本解析器不支持，如实记录而非猜
            errors.append(f"profiles[{index}] 的 type={profile.get('type')!r} 非 'sampled'，已跳过")
            continue
        samples = profile.get('samples') or []
        weights = profile.get('weights')
        if not isinstance(samples, list):
            errors.append(f'profiles[{index}].samples 不是数组，已跳过')
            continue
        if weights is None:
            weights = [1.0] * len(samples)
            errors.append(f'profiles[{index}] 无 weights，按等权 1.0 计时')
        if len(weights) != len(samples):
            errors.append(
                f'profiles[{index}] 的 samples({len(samples)}) 与 weights({len(weights)}) 长度不一致，'
                '按较短者对齐'
            )
            count = min(len(samples), len(weights))
            samples, weights = samples[:count], weights[:count]

        sampled_profiles += 1
        start_value = profile.get('startValue') or 0
        end_value = profile.get('endValue')
        if isinstance(end_value, (int, float)):
            total_duration += float(end_value) - float(start_value)

        for stack, weight in zip(samples, weights):
            if not isinstance(stack, list) or not stack:
                continue
            try:
                duration = float(weight)
            except (TypeError, ValueError):
                errors.append(f'profiles[{index}] 的权重 {weight!r} 不是数值，该样本已跳过')
                continue
            total_samples += 1
            names_in_stack = set()
            for frame_index in stack:
                name = str(_frame_of(frame_index).get('name') or f'<frame {frame_index}>')
                names_in_stack.add(name)
            for name in names_in_stack:
                total_time[name] = total_time.get(name, 0.0) + duration

            leaf = _frame_of(stack[-1])
            leaf_name = str(leaf.get('name') or f'<frame {stack[-1]}>')
            self_time[leaf_name] = self_time.get(leaf_name, 0.0) + duration
            sample_counts[leaf_name] = sample_counts.get(leaf_name, 0) + 1
            previous = location.get(leaf_name)
            if previous is None or duration > previous[0]:
                location[leaf_name] = (duration, str(leaf.get('file') or ''),
                                       leaf.get('line') if isinstance(leaf.get('line'), int) else None)

    hotspots = []
    for name, own in self_time.items():
        _, file_name, line = location.get(name, (0.0, '', None))
        hotspots.append(Hotspot(
            name=name,
            self_time=own,
            total_time=total_time.get(name, own),
            self_share=(own / total_duration) if total_duration > 0 else 0.0,
            samples=sample_counts.get(name, 0),
            file=file_name,
            line=line,
        ))
    hotspots.sort(key=lambda h: (-h.self_time, h.name))

    if not sampled_profiles:
        errors.append('没有任何可解析的 sampled profile')

    return SpeedscopeSummary(
        meta=SamplesMeta(
            duration=total_duration or None,
            samples=total_samples or None,
            errors=errors,
        ),
        profile_count=sampled_profiles,
        frame_count=len(frames),
        hotspots=hotspots,
        path=path,
    )
