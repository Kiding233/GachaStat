"""P79 等价对照——新代码同种子重跑 vs 改动前 golden 基线（P79 §8.3 / §11.5）。

对照口径：

1. ``generated_at`` 时间戳不参与对比
2. 全局允许变化的字段：``iterations`` / ``warnings`` / ``result_version``
   （阶段 3 新增两字段 + 版本号 2→3，属 8.3「有意变更」白名单）
3. ``fixed_count`` / ``stop_on_target`` 两组**整组豁免**（1c 的失效形态修复：
   其 ``final_time`` / ``final_resources`` / ``total_waits`` / ``wait_durations``
   / ``banner_end_*`` 均按 8.3「有意变更」表变化），但须显式核对新值——
   ``final_time`` 必须收敛到 ``env.end_time``
4. 其余 7 组（含插件策略）**逐字段严格一致**

用法：python scripts/p79_verify.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gacha_simulator.core.config_toml import load_toml  # noqa: E402
from gacha_simulator.core.strategy_loader import load_plugin_strategies  # noqa: E402
from gacha_simulator.service.batch_simulator import (  # noqa: E402
    SimulationEnvBuilder,
    _build_target_set,
    _run_single,
)

GOLDEN_DIR = 'tests/fixtures/p79_golden'
CONFIG = 'gacha_simulator/config/config.toml'
SEED = 42

BUILTIN_KEYS = [
    'smart', 'pool_quota', 'pity_reserve', 'stop_on_target',
    'fixed_count', 'target_hunting', 'no_draw', 'draw_target',
]
PLUGIN_KEYS = ['plugin/example_phased']

# 全局允许变化的字段（8.3「有意变更」白名单——阶段 3 的产物）
GLOBAL_ALLOWED = {'iterations', 'warnings', 'result_version'}
# 不参与对比（时间戳）
SKIP_FIELDS = {'generated_at'}
# 整组豁免的策略（1c 修复了其时间冻结失效形态，全字段按白名单变化）
EXEMPT_STRATEGIES = {'fixed_count', 'stop_on_target'}


def snapshot_name(strategy_key: str) -> str:
    return strategy_key.replace('/', '__') + '.json'


def main():
    golden_dir = Path(GOLDEN_DIR)
    if not golden_dir.is_dir():
        print(f'基线目录不存在: {GOLDEN_DIR}', file=sys.stderr)
        sys.exit(1)

    load_plugin_strategies()
    store = load_toml(CONFIG)
    env = SimulationEnvBuilder.from_config_store(store)
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    target_set = _build_target_set(env.card_defs, specs)

    print(f'config: {CONFIG} | pools={len(env.pools)} end_time={env.end_time} seed={SEED}')

    failures = []
    for key in BUILTIN_KEYS + PLUGIN_KEYS:
        path = golden_dir / snapshot_name(key)
        if not path.exists():
            failures.append((key, ['<缺少基线快照>']))
            print(f'  FAIL {key:26s} 缺少基线快照 {path}')
            continue

        baseline = json.load(open(path, encoding='utf-8'))['compact']
        env.strategy_key = key
        env.strategy_params = {}
        current = _run_single(env, target_set, SEED, env.initial_resources)
        if current is None:
            failures.append((key, ['<模拟失败>']))
            print(f'  FAIL {key:26s} 模拟失败')
            continue
        current = current.to_dict()

        diff = {k for k in set(baseline) | set(current)
                if k not in SKIP_FIELDS and baseline.get(k) != current.get(k)}

        if key in EXEMPT_STRATEGIES:
            # 整组豁免，但新值必须是「有意变更」描述的那个
            ok = current['final_time'] == env.end_time
            note = (f'final_time={current["final_time"]:.0f}（== end_time ✓）'
                    if ok else f'final_time={current["final_time"]:.0f} != end_time ✗')
            print(f'  {"OK  " if ok else "FAIL"} {key:26s} 整组豁免（{len(diff)} 字段变化）；{note}')
            if not ok:
                failures.append((key, ['final_time 未收敛到 env.end_time']))
            continue

        unexpected = diff - GLOBAL_ALLOWED
        if unexpected:
            failures.append((key, sorted(unexpected)))
            print(f'  FAIL {key:26s} 计划外变化: {sorted(unexpected)}')
        else:
            print(f'  OK   {key:26s} 逐字段一致（仅 {sorted(diff) or "无"} 变化）')

    ok = not failures
    print(f'\n等价对照结果：{"PASS" if ok else "FAIL"}')
    if not ok:
        for key, fields in failures:
            print(f'  {key}: {fields}')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
