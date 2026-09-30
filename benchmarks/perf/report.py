"""基线登记与比值比对。

存储切分（§3.6）：`baselines/` **入库**（被选择、少量、必须跨时间可追溯），
`runs/` 不入库（过程数据，体积与数量不可控）。基线按**机器类别**分组：

```
benchmarks/baselines/<机器类别>/<name>.json     机器类别 = 核数区间 + OS 版本
```

**同组内比比值，跨组只比阶段占比（相对结构）。** 绝对耗时受频率 / 负载 / 调度影响，
跨机器不可比；若实际只有一台基准机，则在基线文件中显式写明适用范围，而不是假装
跨机器可比。

**两条来自独立审查的硬约束（AUDIT-BREAK-2 / AUDIT-BREAK-4）：**

1. **建基线强制 `repeats >= 3`**，且**缺字段不得与整数比较**。`repeats` 为 `None`
   时 `None < 3` 在 Python 3 中直接抛 `TypeError`，故本模块一律先判 `None` 再判大小，
   并把「缺失」与「不足」报成两条不同的信息。
2. **可比性维度过滤**：比对键含 `path` / `subject` / `return_compact` / 机器类别 /
   `qt_qpa_platform`。任一维度**取值不同**或**任一侧为 `None`**（未记录）即记不可比
   并写明成因——**不得静默判不等**。「未记录」与「确实不同」是两回事。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from benchmarks.perf.record import EnvFingerprint, RunResult

__all__ = [
    'BASELINE_MIN_REPEATS',
    'BaselineGateError',
    'Comparison',
    'baselines_root',
    'baseline_path',
    'register_baseline',
    'find_baseline',
    'load_baseline',
    'compare',
    'format_comparison',
]

#: 建基线的重复次数下限（§3.5）。**不允许降级**：降级过的记录连登记都进不去。
BASELINE_MIN_REPEATS = 3


class BaselineGateError(ValueError):
    """建基线的门禁拒绝。"""


def baselines_root(root: Optional[Path] = None) -> Path:
    """`benchmarks/baselines/`。"""
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parents[1] / 'baselines'


def baseline_path(name: str, machine_class: str, root: Optional[Path] = None) -> Path:
    """`<root>/<机器类别>/<name>.json`。"""
    return baselines_root(root) / machine_class / f'{name}.json'


def register_baseline(name: str, result: RunResult, *, root: Optional[Path] = None) -> Path:
    """登记一条基线。**本模块是唯一写 `baselines/` 的地方，故门禁设在此处。**

    拒绝两种记录（分别报出，不合并成一句）：

    - `repeats` **缺失**（`None`）——「未记录」；直接与 `3` 比较会抛 `TypeError`
    - `repeats` **不足** `BASELINE_MIN_REPEATS`

    两者都拒绝入库：基线是后续所有比值判据的分母，一条单次测量（尤其 `repeats`
    被降级的那些）当基线会把噪声固化下来。
    """
    repeats = result.repeats
    if repeats is None:
        raise BaselineGateError(
            f'基线 {name!r} 拒绝入库：该记录的 repeats 字段缺失（None）——「未记录」不是'
            f'「0 次」，无从判断它是否满足建基线须 repeats >= {BASELINE_MIN_REPEATS}。'
            '请用一条完整记录的 RunResult。'
        )
    if repeats < BASELINE_MIN_REPEATS:
        extra = '（该记录标注了 repeats_downgraded：预估墙钟超 30s 时降为 1 次）' \
            if result.repeats_downgraded else ''
        raise BaselineGateError(
            f'基线 {name!r} 拒绝入库：建基线须 repeats >= {BASELINE_MIN_REPEATS}，'
            f'该记录 repeats={repeats}{extra}。请在内存允许范围内增大 repeats 后重跑，'
            '或把该记录仅作参考、不入基线。'
        )

    target = baseline_path(name, result.fingerprint.machine_class, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'name': name,
        'machine_class': result.fingerprint.machine_class,
        'record': result.to_dict(),
        # 适用范围显式写进文件——只有一台基准机时，不得假装跨机器可比（§3.5）
        'scope_note': (
            f'本基线在机器类别 {result.fingerprint.machine_class} 上采集'
            f'（cpu={result.fingerprint.cpu} / cores={result.fingerprint.cores} / '
            f'python={result.fingerprint.python} / 代码版本={result.fingerprint.code_version}）。'
            '跨机器类别只比阶段占比，不比绝对比值。'
        ),
    }
    with target.open('w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return target


def find_baseline(name: str, fingerprint: EnvFingerprint, *,
                  root: Optional[Path] = None) -> Optional[Path]:
    """按机器类别找基线文件。找不到即 `None`（不报错——「尚无基线」是正常起点）。"""
    candidate = baseline_path(name, fingerprint.machine_class, root)
    return candidate if candidate.is_file() else None


def load_baseline(name: str, fingerprint: EnvFingerprint, *,
                  root: Optional[Path] = None) -> RunResult:
    """读入基线记录。文件不存在即报错并给出期待的路径。"""
    path = find_baseline(name, fingerprint, root=root)
    if path is None:
        raise FileNotFoundError(
            f'找不到基线 {name!r}（机器类别 {fingerprint.machine_class}）：'
            f'期待 {baseline_path(name, fingerprint.machine_class, root)}'
        )
    with path.open(encoding='utf-8') as handle:
        payload = json.load(handle)
    return RunResult.from_dict(payload['record'])


# ── 比对 ─────────────────────────────────────────────────


@dataclass
class Comparison:
    """一次「本次 vs 基线」的比对结果。"""

    comparable: bool
    reasons: List[str] = field(default_factory=list)
    """不可比的成因（逐条写明维度与两侧取值）。"""

    wall_ratio: Optional[float] = None
    byte_ratio: Optional[float] = None
    stage_ratios: Dict[str, float] = field(default_factory=dict)
    current_stage_shares: Dict[str, float] = field(default_factory=dict)
    baseline_stage_shares: Dict[str, float] = field(default_factory=dict)
    excluded: List[str] = field(default_factory=list)
    """被排除出比值的项（`not_comparable` 记录、`None` 读数）。"""

    warnings: List[str] = field(default_factory=list)


def _dimension_mismatch(label: str, current: Any, baseline: Any,
                        reasons: List[str]) -> bool:
    """比一个可比性维度。返回是否「确定不可比」。

    三种情形分开报：**任一侧未记录（`None`）**、**两侧取值不同**、两侧一致。
    前两种都判不可比，但成因文案不同——「未记录」不是「不同」，静默判不等会让
    读报告的人去查一个根本不存在的差异。
    """
    if current is None or baseline is None:
        side = '本次' if current is None else '基线'
        reasons.append(f'{label}：{side}未记录（None）——按不可比处理，不判不等')
        return True
    if current != baseline:
        reasons.append(f'{label}：本次={current!r} 基线={baseline!r}——取值不同，不可比')
        return True
    return False


def compare(current: RunResult, baseline: RunResult) -> Comparison:
    """本次记录与基线的比值比对。

    **先过滤可比性维度，再算比值。** 维度不过关时不产出任何比值——产出一个
    「算了但别信」的数字比不产出更坏。
    """
    comparison = Comparison(comparable=True)

    # ① 可比性维度（AUDIT-BREAK-4）
    _dimension_mismatch('path（路径）', current.path, baseline.path, comparison.reasons)
    _dimension_mismatch('subject（测量对象）', current.plan.subject, baseline.plan.subject,
                        comparison.reasons)
    _dimension_mismatch('return_compact', current.return_compact, baseline.return_compact,
                        comparison.reasons)
    _dimension_mismatch('qt_qpa_platform', current.fingerprint.qt_qpa_platform,
                        baseline.fingerprint.qt_qpa_platform, comparison.reasons)

    same_machine = current.fingerprint.machine_class == baseline.fingerprint.machine_class
    if not same_machine:
        comparison.reasons.append(
            f'机器类别：本次={current.fingerprint.machine_class!r} '
            f'基线={baseline.fingerprint.machine_class!r}——跨组不比绝对比值，只比阶段占比'
        )

    # ② 缺字段降级（AUDIT-BREAK-2）：repeats 缺失不得与整数比较
    for label, value in (('本次', current.repeats), ('基线', baseline.repeats)):
        if value is None:
            comparison.warnings.append(
                f'{label}记录的 repeats 缺失（None）——按不可比处理，不参与门禁判定'
            )

    # ③ not_comparable 记录的排除（§3.8 D6）
    for label, record in (('本次', current), ('基线', baseline)):
        if record.not_comparable:
            comparison.excluded.append(f'{label}记录的 wall_median（not_comparable=True）')

    comparison.comparable = same_machine and not comparison.reasons

    # ④ 比值——**只在整体可比时产出**。任一维度不过关就一个比值都不给：
    # 产出一个「算了但别信」的数字，比不产出更坏。
    if comparison.comparable:
        wall_a, wall_b = current.wall_median, baseline.wall_median
        if wall_a is None or wall_b is None:
            comparison.excluded.append('wall_median（一侧未记录）')
        elif wall_b == 0:
            comparison.excluded.append('wall_median（基线为 0，比值无定义）')
        elif any(r.not_comparable for r in (current, baseline)):
            pass  # 已在 excluded 里，不产比值
        else:
            comparison.wall_ratio = wall_a / wall_b

        byte_a = current.resources.bytes
        byte_b = baseline.resources.bytes
        if byte_a is None or byte_b is None:
            comparison.excluded.append('resources.bytes（一侧未记录/本路径不可得）')
        elif byte_b == 0:
            comparison.excluded.append('resources.bytes（基线为 0，比值无定义）')
        else:
            # 字节数只在 return_compact 一致时可比（§3.5）——维度已在 ① 过滤
            comparison.byte_ratio = byte_a / byte_b

    # ⑤ 阶段比值与占比
    shared = sorted(set(current.stages) & set(baseline.stages))
    missing_current = sorted(set(baseline.stages) - set(current.stages))
    missing_baseline = sorted(set(current.stages) - set(baseline.stages))
    for name in missing_current:
        comparison.warnings.append(f'阶段 {name}：本次未产出（基线有）——该段不参与比值')
    for name in missing_baseline:
        comparison.warnings.append(f'阶段 {name}：基线未产出（本次有）——该段不参与比值')

    if comparison.comparable:
        for name in shared:
            base_value = baseline.stages[name]
            if base_value > 0:
                comparison.stage_ratios[name] = current.stages[name] / base_value
            else:
                comparison.excluded.append(f'阶段 {name}（基线为 0，比值无定义）')

    # 阶段占比（相对结构）不受可比性门控——跨机器类别时它是**唯一**可比的量
    comparison.current_stage_shares = _stage_shares(current.stages)
    comparison.baseline_stage_shares = _stage_shares(baseline.stages)
    return comparison


def _stage_shares(stages: Dict[str, float]) -> Dict[str, float]:
    """阶段占比（相对结构）——跨机器类别时唯一可比的量。"""
    total = sum(stages.values())
    if total <= 0:
        return {}
    return {name: value / total for name, value in stages.items()}


def _fmt(value: Optional[float], digits: int = 3) -> str:
    return '—' if value is None else f'{value:.{digits}f}'


def format_comparison(comparison: Comparison, *, current: RunResult,
                      baseline: RunResult, baseline_label: str = '') -> str:
    """把比对结果格式化为可读报告（`1k` 的命令入口用它打印）。"""
    lines: List[str] = []
    head = f'本次（{current.path} / {current.fingerprint.machine_class}）'
    tail = f'基线 {baseline_label}' if baseline_label else '基线'
    lines.append(f'{head} vs {tail}：')

    if not comparison.comparable and comparison.reasons:
        lines.append('  ⚠ 不可比（未产出比值）：')
        lines.extend(f'    - {reason}' for reason in comparison.reasons)

    if comparison.wall_ratio is not None:
        lines.append(f'  总墙钟比值（本次 / 基线）：{_fmt(comparison.wall_ratio)}')
    if comparison.byte_ratio is not None:
        lines.append(f'  三元组字节数比值：{_fmt(comparison.byte_ratio)}'
                     '（代理指标，当回归判据用、不当绝对开销读）')

    if comparison.stage_ratios:
        # 段值口径（2026-10-01 选项 A）：段值取首次运行的单次采样，`repeats` 只压总墙钟。
        # 与 `wall_median` 不是同一次测量，读比值须自留噪声余量（`04-问题.md` 该条已处置）。
        lines.append('  阶段比值（段值取首次运行的单次采样，repeats 只压总墙钟；'
                     '读比值须自留噪声余量）：')
        for name, ratio in sorted(comparison.stage_ratios.items()):
            lines.append(f'    {name:<12} {_fmt(ratio)}')
    if comparison.current_stage_shares:
        lines.append('  阶段占比（本次 / 基线）：')
        for name in sorted(comparison.current_stage_shares):
            cur = _fmt(comparison.current_stage_shares[name])
            base = _fmt(comparison.baseline_stage_shares.get(name))
            lines.append(f'    {name:<12} {cur} / {base}')

    if comparison.excluded:
        lines.append('  已排除：' + '；'.join(comparison.excluded))
    if comparison.warnings:
        lines.extend(f'  ⚠ {warning}' for warning in comparison.warnings)
    return '\n'.join(lines)
