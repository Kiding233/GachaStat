#!/usr/bin/env python3
"""GachaStat 命令行版本"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')

sys.path.insert(0, str(Path(__file__).parent))

from gacha_simulator.core.config_toml import load_toml  # noqa: E402
from gacha_simulator.core.strategy import create_strategy  # noqa: E402
from gacha_simulator.core.stop_condition import AllPoolsEndCondition  # noqa: E402
from gacha_simulator.service import GachaService  # noqa: E402
from gacha_simulator.service.batch_simulator import SimulationEnvBuilder  # noqa: E402
from multiprocessing import Pool as MPPool  # noqa: E402
from gacha_simulator.paths import get_config_dir  # noqa: E402


DAY = 86400


def run_single_sim(args):
    import random
    store, resources, end_day, seed = args
    random.seed(seed)

    env = SimulationEnvBuilder.from_config_store(store)
    strategy = create_strategy('smart', {})
    stop_cond = AllPoolsEndCondition(end_day * DAY)

    # 构造 TargetCardSet
    from gacha_simulator.core.target_card import TargetCard, TargetCardSet
    targets = []
    for tc in store.target_cards:
        targets.append(TargetCard(card_id=tc.card_id, pool_ids=list(tc.pool_ids),
                                  quantity_needed=tc.quantity))
    target_set = TargetCardSet(targets) if targets else TargetCardSet([])

    service = GachaService(
        env.pools, strategy, stop_cond, target_set,
        schedule_manager=env.schedule_mgr,
        pity_engine=env.pity_engine,
        resource_gain=env.resource_gain,
        ssr_ids=env.ssr_ids,
        card_defs=env.card_defs,
    )
    from gacha_simulator.core import GachaState
    state = GachaState(resources=dict(resources) if resources else {})
    return service.run_simulation_compact(state)


def main():
    parser = argparse.ArgumentParser(description='GachaStat CLI')
    parser.add_argument('-c', '--config', default=None,
                        help='TOML 配置文件路径（默认：打包 config.toml）')
    parser.add_argument('-n', '--num-simulations', type=int, default=1000,
                        help='Number of simulations')
    parser.add_argument('-w', '--workers', type=int, default=4,
                        help='Number of parallel workers')
    parser.add_argument('-s', '--seed', type=int, default=42, help='Random seed')
    parser.add_argument('-o', '--output', default='results.json', help='Output file')
    parser.add_argument('--no-pity', action='store_true', help='Disable pity system')

    args = parser.parse_args()

    if args.config:
        # 用户指定 TOML 路径
        store = load_toml(args.config)
    else:
        # 无参数 → 加载打包默认 config.toml
        default_toml = os.path.join(get_config_dir(), 'config.toml')
        store = load_toml(default_toml)

    # 为 output_data 构造 config 元数据 dict（替代旧 JSON config）
    config_meta = {
        'path': str(args.config) if args.config else default_toml,
        'num_pools': len(store.pools),
        'num_cards': len(store.card_defs),
        'pity_enabled': store.pity.enabled,
        'num_targets': len(store.target_cards),
    }

    if args.no_pity:
        store.pity.enabled = False

    SimulationEnvBuilder.from_config_store(store)
    end_day = max(p.end_day for p in store.pools) if store.pools else 365

    print("=" * 50)
    print("GachaStat CLI")
    print("=" * 50)
    print(f"Simulations: {args.num_simulations}")
    print(f"Workers: {args.workers}")
    print(f"Seed: {args.seed}")
    print(f"Pity: {'Enabled' if store.pity.enabled else 'Disabled'}")
    if store.pity.enabled and store.pity.pities:
        p0 = store.pity.pities[0]
        start = p0.params.get('start', '74')
        end = p0.params.get('end', '90')
        print(f"  Type: {p0.btype}")
        print(f"  Range: {start}-{end}")
    print("=" * 50)

    resources = dict(store.initial_resources)

    args_list = [
        (store, resources, end_day, args.seed + i)
        for i in range(args.num_simulations)
    ]

    print(f"\nRunning {args.num_simulations} simulations...")
    start_time = time.time()

    with MPPool(processes=args.workers) as mp_pool:
        results = mp_pool.map(run_single_sim, args_list,
                              chunksize=max(1, args.num_simulations // 100))

    elapsed = time.time() - start_time

    print(f"Completed in {elapsed:.2f}s ({args.num_simulations/elapsed:.1f} sim/s)")

    actual_target_ids = [t.card_id for t in store.target_cards]
    if not actual_target_ids and store.pools:
        actual_target_ids = [f"{store.pools[0].pool_id}_ssr"]
    total_targets = len(actual_target_ids)

    total_draws = []
    ssr_counts = []
    gdr_percents = []

    for r in results:
        draws = r.get('total_draws', 0)
        total_draws.append(draws)
        cc = r.get('card_counts', {})
        ssr = sum(cc.get(tid, 0) for tid in actual_target_ids)
        ssr_counts.append(ssr)
        gdr_percents.append((ssr / max(total_targets, 1)) * 100)

    import numpy as np

    print("\n" + "=" * 50)
    print("Results Summary")
    print("=" * 50)
    print(f"Total Simulations: {len(results)}")
    print("\nTotal Draws:")
    print(f"  Mean: {np.mean(total_draws):.1f}")
    print(f"  Median: {np.median(total_draws):.1f}")
    print(f"  Std: {np.std(total_draws):.1f}")

    print("\nSSR Count:")
    print(f"  Mean: {np.mean(ssr_counts):.2f}")
    print(f"  Median: {np.median(ssr_counts):.1f}")

    print("\nGDR (Target Card %):")
    print(f"  Mean: {np.mean(gdr_percents):.2f}%")
    print(f"  Median: {np.median(gdr_percents):.2f}%")
    print(f"  25th percentile: {np.percentile(gdr_percents, 25):.2f}%")
    print(f"  75th percentile: {np.percentile(gdr_percents, 75):.2f}%")

    output_data = {
        'config': config_meta,
        'num_simulations': args.num_simulations,
        'elapsed_time': elapsed,
        'summary': {
            'total_draws': {'mean': float(np.mean(total_draws)),
                            'median': float(np.median(total_draws))},
            'ssr_counts': {'mean': float(np.mean(ssr_counts)),
                           'median': float(np.median(ssr_counts))},
            'gdr_percent': {
                'mean': float(np.mean(gdr_percents)),
                'median': float(np.median(gdr_percents)),
                'p25': float(np.percentile(gdr_percents, 25)),
                'p75': float(np.percentile(gdr_percents, 75))
            }
        }
    }

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\nResults saved to: {args.output}")
    print("=" * 50)


if __name__ == '__main__':
    main()
