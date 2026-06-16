#!/usr/bin/env python3
"""测试多进程模拟路径"""
import sys, os, random, time
sys.path.insert(0, '.')

from gacha_simulator.core.config_toml import load_toml
from gacha_simulator.service.batch_simulator import SimulationEnvBuilder, run_batch_parallel, _run_single
from gacha_simulator.core import TargetCard, TargetCardSet
from gacha_simulator.paths import get_config_dir

def main():
    path = os.path.join(get_config_dir(), 'config.toml')
    store = load_toml(path)
    env = SimulationEnvBuilder.from_config_store(store)
    env.strategy_name = 'smart'
    env.strategy_params = {}
    env.return_compact = False  # 跟 GUI 一致

    target_specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    targets = [TargetCard(card_id=tc.card_id, pool_ids=list(tc.pool_ids), quantity_needed=tc.quantity) for tc in store.target_cards]
    target_set = TargetCardSet(targets)

    print(f'env.initial_resources: {env.initial_resources}')
    print(f'env.resource_gain type: {type(env.resource_gain).__name__}')
    print(f'env.pools count: {len(env.pools)}')
    for p in env.pools[:2]:
        print(f'  pool {p.id}: cost={p.cost} rewards={len(p.rewards)} avail={p.available_from}-{p.available_until}')

    # 测试1: 直接单进程
    random.seed(42)
    compact = _run_single(env, target_set, 42, env.initial_resources)
    print(f'\n[单进程] total_draws={compact.total_draws} consumed={compact.total_consumed}')

    # 测试2: 多进程 4 workers
    print(f'\n[多进程 4 workers] 启动...')
    start = time.time()
    batch = run_batch_parallel(
        env=env, target_specs=target_specs,
        initial_resources=env.initial_resources,
        num_simulations=10, max_workers=4, seed=42,
    )
    elapsed = time.time() - start
    ext = getattr(batch, 'extraction', None)
    raw = getattr(batch, 'results', [])
    print(f'  耗时: {elapsed:.1f}s')
    print(f'  raw results: {len(raw)}')
    print(f'  extraction: {"有" if ext else "无"}')
    if ext:
        agg_list = ext.get('aggregates', [])
        print(f'  aggregates: {len(agg_list)}')
        if agg_list:
            first = agg_list[0]
            print(f'  首条 total_draws: {first.get("total_draws", "?")}')
            print(f'  首条 pool_draw_counts: {first.get("pool_draw_counts", "?")}')
            print(f'  首条 total_consumed: {first.get("total_consumed", "?")}')
    else:
        print(f'  ⚠️ extraction 为 None!')

    # 测试3: max_workers=1 (单进程回退路径)
    print(f'\n[max_workers=1 回退路径] 启动...')
    batch2 = run_batch_parallel(
        env=env, target_specs=target_specs,
        initial_resources=env.initial_resources,
        num_simulations=5, max_workers=1, seed=42,
    )
    ext2 = getattr(batch2, 'extraction', None)
    raw2 = getattr(batch2, 'results', [])
    print(f'  raw results: {len(raw2)}')
    print(f'  extraction: {"有" if ext2 else "无"}')
    if raw2:
        first = raw2[0]
        print(f'  首条 total_draws: {first.total_draws}')
        print(f'  首条 pool_draw_counts: {dict(first.pool_draw_counts)}')

if __name__ == '__main__':
    main()
