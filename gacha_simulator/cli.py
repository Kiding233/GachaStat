#!/usr/bin/env python3
"""GachaStat 命令行版本"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')

sys.path.insert(0, str(Path(__file__).parent))

from gacha_simulator.core.config_store import (  # noqa: E402
    ConfigStore, PoolEntry, PoolDistEntry,
    PityDef, GainRule, TargetCardEntry,
)
from gacha_simulator.core.strategy import create_strategy  # noqa: E402
from gacha_simulator.core.stop_condition import AllPoolsEndCondition  # noqa: E402
from gacha_simulator.service import GachaService  # noqa: E402
from gacha_simulator.service.batch_simulator import SimulationEnvBuilder  # noqa: E402
from multiprocessing import Pool as MPPool  # noqa: E402


DAY = 86400


def json_config_to_store(config: dict, store: ConfigStore) -> None:
    """将 CLI JSON 配置桥接到 ConfigStore 字段。

    映射关系：
    - config['pools'] → PoolEntry 列表
    - config['pity'] → PityConfig + PityDef
    - config['targets'] → TargetCardEntry
    - config['gains'] → GainRule
    - config['resources'] → resource_defs + initial_resources
    """
    # 1. pools → PoolEntry
    pools_config = config.get('pools')
    if not pools_config:
        raise ValueError("配置文件中缺少 'pools' 字段或为空")

    for p in pools_config:
        start = p.get('start_day', 0)
        dur = p.get('duration', 21)
        ssr_r = p.get('ssr_rate', 0.006)
        sr_r = p.get('sr_rate', 0.051)
        entry = PoolEntry(
            pool_id=p['id'],
            name=p.get('name', p['id']),
            start_day=start,
            end_day=start + dur,
            cost=f"draw_resource:{p.get('cost', 160)}",
            pool_type=p.get('pool_type', ''),
            distribution=[
                PoolDistEntry(
                    card_id=f"{p['id']}_ssr",
                    probability=ssr_r * 100, rarity='SSR', featured=True,
                ),
                PoolDistEntry(
                    card_id=f"{p['id']}_sr",
                    probability=sr_r * 100, rarity='SR',
                ),
                PoolDistEntry(
                    card_id=f"{p['id']}_r",
                    probability=max(0.0, 100 - ssr_r * 100 - sr_r * 100), rarity='R',
                ),
            ],
        )
        store.pools.append(entry)

    # 2. pity → PityConfig + PityDef
    pity_config = config.get('pity', {})
    store.pity.enabled = pity_config.get('enabled', True)
    pities_raw = pity_config.get('pities', [])
    if not pities_raw and pity_config.get('type'):
        # shorthand 格式——从顶层字段构造单个 PityDef
        pities_raw = [pity_config]
    for p in pities_raw:
        params = p.get('params', {})
        if not params and p.get('type'):
            params = {
                'start': str(p.get('start', '74')),
                'end': str(p.get('end', '90')),
                'func': p.get('func', 'linear'),
                'threshold': str(p.get('threshold', '90')),
            }
        pdef = PityDef(
            name=p.get('name', 'default_pity'),
            btype=p.get('type', 'soft'),
            params=params,
            target_distribution=p.get('target_distribution', {}),
            reset_condition=p.get('reset', 'any_ssr'),
            pools=p.get('pools', '*'),
        )
        store.pity.pities.append(pdef)

    # 3. targets → TargetCardEntry
    for t in config.get('targets', []):
        store.target_cards.append(TargetCardEntry(
            card_id=t['card_id'],
            quantity=t.get('quantity', 1),
            pool_ids=t.get('pool_ids', []),
        ))

    # 4. gains → GainRule
    for g in config.get('gains', []):
        store.gain_rules.append(GainRule(
            rule_type=g.get('rule_type', 'every_n_days'),
            param=g.get('param', '1'),
            gains=g.get('gains', {}),
        ))

    # 5. resources → resource_defs + initial_resources
    resources = config.get('resources', {})
    for res_name, res_val in resources.items():
        if res_name not in store.resource_defs:
            store.resource_defs[res_name] = res_name
        if isinstance(res_val, (int, float)) and res_val > 0:
            store.initial_resources[res_name] = float(res_val)

    # 6. initial_resources 显式覆盖
    for res_name, amount in config.get('initial_resources', {}).items():
        store.initial_resources[res_name] = float(amount)


def run_single_sim(args):
    import random
    store, resources, end_day, seed = args
    random.seed(seed)

    env = SimulationEnvBuilder.from_config_store(store)
    strategy = create_strategy('smart', {})
    stop_cond = AllPoolsEndCondition(end_day * DAY)
    service = GachaService(
        env.pools, strategy, stop_cond, env.target_cards,
        schedule_manager=env.schedule_manager,
        pity_engine=env.pity_engine,
    )
    from gacha_simulator.core import GachaState
    state = GachaState(resources=dict(resources) if resources else {})
    return service.run_simulation_compact(state)


def main():
    parser = argparse.ArgumentParser(description='GachaStat CLI')
    parser.add_argument('-c', '--config', default='default_config.json', help='Config file path')
    parser.add_argument('-n', '--num-simulations', type=int, default=1000, help='Number of simulations')
    parser.add_argument('-w', '--workers', type=int, default=4, help='Number of parallel workers')
    parser.add_argument('-s', '--seed', type=int, default=42, help='Random seed')
    parser.add_argument('-o', '--output', default='results.json', help='Output file')
    parser.add_argument('--no-pity', action='store_true', help='Disable pity system')
    parser.add_argument('--no-json', action='store_true',
                        help='Use pure text-file config mode (ignore JSON)')
    parser.add_argument('--data-dir', default=None,
                        help='Text-file config directory (加载为基线后 JSON 覆盖)')

    args = parser.parse_args()

    if not args.no_json:
        import warnings
        warnings.warn(
            "JSON 配置文件格式已弃用，将在后续版本移除。"
            "请迁移到文本文件格式（config/ 目录）。",
            DeprecationWarning,
        )

    store = ConfigStore()

    # 1. 文本文件基线（若提供 --data-dir）
    if args.data_dir:
        from gacha_simulator.core.config_io import load_store_from_directory
        load_store_from_directory(args.data_dir, store)

    # 2. JSON 覆盖层（若 -c 传入）
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
        json_config_to_store(config, store)
    elif not args.data_dir:
        # 既无 JSON 也无 data-dir → 使用默认配置
        config = {
            'pools': [
                {'id': f'pool_{i}', 'name': f'池子{i}', 'start_day': i*7, 'duration': 21,
                 'cost': 160, 'ssr_rate': 0.015 if i < 4 else 0.007}
                for i in range(8)
            ],
            'pity': {'enabled': not args.no_pity, 'type': 'soft', 'start': 80, 'end': 90},
            'resources': {'draw_resource': 50000}
        }
        json_config_to_store(config, store)

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
        results = mp_pool.map(run_single_sim, args_list, chunksize=max(1, args.num_simulations // 100))
    
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
        'config': config,
        'num_simulations': args.num_simulations,
        'elapsed_time': elapsed,
        'summary': {
            'total_draws': {'mean': float(np.mean(total_draws)), 'median': float(np.median(total_draws))},
            'ssr_counts': {'mean': float(np.mean(ssr_counts)), 'median': float(np.median(ssr_counts))},
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
