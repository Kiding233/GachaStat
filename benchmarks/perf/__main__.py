"""命令入口薄壳（§3.1 第三层「调用面」）。

暴露 **G1 的单条命令**：

```bash
python -m benchmarks.perf run --plan <plan.json> --baseline <name>
python -m benchmarks.perf run --plan <plan.json> --baseline <name> --register
```

**本层不含任何测量逻辑**（受 §3.2 约束 A 约束）：测量全在 `plan` / `record` /
`stage` / `adapters` / `report` 的产物里，这里只做参数解析、`Plan.from_dict()` 读入
与结果格式化。

`plan.json` 的规格由 `Plan.from_dict()` 定义（§3.1 的输入契约）：**缺省键取字段
默认值，未知键与非法值报错退出**——薄壳**不自行定义输入规格**。

退出码：`0` 正常；`2` 用法错误 / `plan.json` 非法 / 安全协议拒绝 / 缺基线；
`3` 该路径在本环境不可用；`4` 适配器运行失败。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from benchmarks.perf.adapters.base import AdapterError, AdapterUnavailable, get_adapter
from benchmarks.perf.plan import Plan
from benchmarks.perf.record import RunResult
from benchmarks.perf.report import (
    BaselineGateError,
    compare,
    format_comparison,
    load_baseline,
    register_baseline,
)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3
EXIT_RUN_FAILED = 4

PROG = 'python -m benchmarks.perf'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description='性能分析平台的命令入口（P83 §3.1 第三层）。'
                    '回答「配置 X 在路径 P 上对比基线 B 的比值是多少」。',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    run = sub.add_parser('run', help='跑一条 plan；默认与基线比对，--register 时登记为基线')
    run.add_argument('--plan', required=True, metavar='PATH',
                     help='plan.json 路径（Plan.to_dict 的形态，§3.1 输入契约）')
    run.add_argument('--baseline', default=None, metavar='NAME',
                     help='基线名（登记与比对都用它）')
    run.add_argument('--register', action='store_true',
                     help='把本次结果登记为基线（建基线须 repeats >= 3，否则拒绝入库）')
    run.add_argument('--quiet', action='store_true', help='只打印比值行')
    return parser


def _load_plan(path: str) -> Plan:
    """读入 `plan.json`。规格由 `Plan.from_dict()` 定义，薄壳不另定规格。"""
    target = Path(path)
    try:
        with target.open(encoding='utf-8') as handle:
            payload = json.load(handle)
    except OSError as exc:
        raise ValueError(f'读不到 plan.json（{path}）：{exc}') from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f'plan.json 不是合法 JSON（{path}）：{exc}') from exc
    return Plan.from_dict(payload)


def _print_record(result: RunResult, plan_path: str) -> None:
    repeats = result.repeats
    downgraded = '（已降级）' if result.repeats_downgraded else ''
    print(f'本次记录：path={result.path} / n={result.plan.n} / workers={result.plan.workers} / '
          f'seed={result.plan.seed} / strategy={result.plan.strategy_key}')
    print(f'  配置：{result.plan.config_path}（plan.json: {plan_path}）')
    print(f'  墙钟中位数：{result.wall_median:.3f}s（repeats={repeats}{downgraded}，'
          f'样本 {len(result.wall_samples)} 个）')
    machine = result.fingerprint.machine_class
    print(f'  机器类别：{machine} / QT_QPA_PLATFORM={result.fingerprint.qt_qpa_platform}')
    if result.stages:
        print('  阶段：' + '，'.join(f'{k}={v:.3f}s' for k, v in result.stages.items()))
    if result.warnings:
        print(f'  ⚠ {len(result.warnings)} 条告警：')
        for warning in result.warnings:
            print(f'    - {warning}')


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        plan = _load_plan(args.plan)
    except ValueError as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return EXIT_USAGE

    try:
        adapter = get_adapter(plan.path)
    except AdapterError as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return EXIT_USAGE

    if not adapter.available():
        print(f'错误：路径 {plan.path!r} 在本环境不可用（适配器 available() 为 False）',
              file=sys.stderr)
        return EXIT_UNAVAILABLE

    try:
        result = adapter.run(plan)
    except AdapterUnavailable as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return EXIT_UNAVAILABLE
    except AdapterError as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return EXIT_RUN_FAILED

    if not args.quiet:
        _print_record(result, args.plan)

    if args.register:
        if not args.baseline:
            print('错误：--register 需要同时给出 --baseline <name>', file=sys.stderr)
            return EXIT_USAGE
        try:
            path = register_baseline(args.baseline, result)
        except BaselineGateError as exc:
            print(f'错误：{exc}', file=sys.stderr)
            return EXIT_USAGE
        print(f'已登记基线 {args.baseline!r} → {path}')
        return EXIT_OK

    if not args.baseline:
        print('错误：需要 --baseline <name> 才能比对；'
              '首次建基线请加 --register', file=sys.stderr)
        return EXIT_USAGE

    try:
        baseline = load_baseline(args.baseline, result.fingerprint)
    except FileNotFoundError as exc:
        print(f'错误：{exc}', file=sys.stderr)
        return EXIT_USAGE

    comparison = compare(result, baseline)
    print()
    print(format_comparison(comparison, current=result, baseline=baseline,
                            baseline_label=args.baseline))
    if comparison.comparable and comparison.wall_ratio is not None:
        print()
        print(f'结论：配置 {plan.config_path} 在路径 {plan.path} 上对比基线 '
              f'{args.baseline} 的总墙钟比值 = {comparison.wall_ratio:.3f}')
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == 'run':
        return _cmd_run(args)
    return EXIT_USAGE  # pragma: no cover - argparse 的 required=True 已挡住


if __name__ == '__main__':
    sys.exit(main())
