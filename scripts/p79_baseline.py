"""P79 改动前 golden 基线固化。

在阶段 1 动工前，用当前（未改造）代码 + 默认配置 + 固定种子，把 9 组策略的
CompactResult 逐字段序列化固化到 tests/fixtures/p79_golden/。后续任一子任务改动或
回滚后，以同一种子重跑并逐字段比对（P79 8.3 / 11.5）。

9 组 = STRATEGY_REGISTRY 的 8 个内置策略 + 已自动加载的插件策略
plugin/example_phased。插件策略参与默认运行，且其内部组合 PityReserveStrategy +
DrawSegmentStrategy 的兜底（core/strategy.py 的 WaitAction(duration=0)）正是阶段 1
的改造对象，不覆盖则该插件的行为无基线可对照。

文件名规则：策略 key 中的 "/" 转义为 "__"（插件 key 含 "/"，不能直接作文件名）。

用法：python scripts/p79_baseline.py [--config PATH] [--seed 42] [--out DIR]
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gacha_simulator.core.config_toml import load_toml  # noqa: E402
from gacha_simulator.core.strategy import STRATEGY_REGISTRY  # noqa: E402
from gacha_simulator.core.strategy_loader import load_plugin_strategies  # noqa: E402
from gacha_simulator.service.batch_simulator import (  # noqa: E402
    SimulationEnvBuilder,
    _build_target_set,
    _run_single,
)

# 8 个内置策略（顺序固定，保证产物可复现）
BUILTIN_KEYS = [
    'smart', 'pool_quota', 'pity_reserve', 'stop_on_target',
    'fixed_count', 'target_hunting', 'no_draw', 'draw_target',
]
# 插件策略（由 load_plugin_strategies 注册）
PLUGIN_KEYS = ['plugin/example_phased']


def snapshot_name(strategy_key: str) -> str:
    """策略 key → 快照文件名（"/" 转义为 "__"）。"""
    return strategy_key.replace('/', '__') + '.json'


def main():
    parser = argparse.ArgumentParser(description='P79 改动前 golden 基线固化')
    parser.add_argument('--config', default='gacha_simulator/config/config.toml')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--out', default='tests/fixtures/p79_golden')
    args = parser.parse_args()

    # 插件策略参与默认运行，须先加载才会进入 STRATEGY_REGISTRY
    n_loaded = load_plugin_strategies()
    print(f'插件加载: {n_loaded} 个')

    keys = BUILTIN_KEYS + PLUGIN_KEYS
    missing = [k for k in keys if k not in STRATEGY_REGISTRY]
    if missing:
        print(f'策略未注册: {missing}', file=sys.stderr)
        sys.exit(1)

    store = load_toml(args.config)
    env = SimulationEnvBuilder.from_config_store(store)
    target_specs = {tc.card_id: getattr(tc, 'quantity', 1) for tc in store.target_cards}
    # 复用生产构造：_build_target_set 把 card_defs.pools 的全限定键
    # {banner}.{pool} 截为 banner 级，与 _pool_needs_target 的 banner.id 匹配口径
    # 恒同；自建 TargetCard 会漏掉这一步，使 smart / stop_on_target 认不到目标卡。
    target_set = _build_target_set(env.card_defs, target_specs)

    print(f'config: {args.config} | pools={len(env.pools)} '
          f'end_time={env.end_time} seed={args.seed}')
    print(f'目标卡: {len(target_set.targets)} 个')

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    for key in keys:
        env.strategy_key = key
        # 参数取各策略的注册表默认值（create_strategy 内部合并），
        # 不继承配置文件中为其他策略填的参数
        env.strategy_params = {}

        t0 = time.time()
        compact = _run_single(env, target_set, args.seed, env.initial_resources)
        elapsed = time.time() - t0
        if compact is None:
            print(f'  {key}: 模拟失败（返回 None）', file=sys.stderr)
            sys.exit(1)

        payload = {
            'meta': {
                'plan': 'P79',
                'strategy_key': key,
                'config_path': str(args.config),
                'seed': args.seed,
                'end_time': env.end_time,
                'num_pools': len(env.pools),
                'generated_at': time.time(),
                'note': 'P79 改动前基线（阶段 1-3 之前）；本快照无 iterations / warnings 字段',
            },
            'compact': compact.to_dict(),
        }
        (out_dir / snapshot_name(key)).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  {key:26s} {elapsed:6.2f}s draws={compact.total_draws:6d} '
              f'waits={compact.total_waits:6d} final_time={compact.final_time:.1f}')

    print(f'已固化 {len(keys)} 组 → {out_dir}')


if __name__ == '__main__':
    main()
