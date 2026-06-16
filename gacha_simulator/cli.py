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
from gacha_simulator.service.batch_simulator import SimulationEnvBuilder, run_batch_parallel  # noqa: E402
from gacha_simulator.paths import get_config_dir  # noqa: E402


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
    parser.add_argument('--strategy', default=None,
        choices=['smart', 'pool_quota', 'pity_reserve', 'target_hunting',
                 'stop_on_target', 'fixed_count', 'draw_target'],
        help='抽卡策略（默认：使用 config.toml 中指定的策略，回退 smart）')
    parser.add_argument('--strategy-params', default=None,
        help='策略参数，JSON 字符串。例：\'{"desire_weights": {"A": 1.5}, "miss_cost": 0.8}\' '
             '（仅当 --strategy 显式指定时生效；若未指定，使用 config.toml 中的策略参数）')
    parser.add_argument('--output-format', default='simple',
        choices=['simple', 'full'],
        help='输出格式：simple=基础统计JSON, full=含extraction完整数据')
    parser.add_argument('--no-progress', action='store_true',
        help='禁用进度条输出')

    args = parser.parse_args()

    if args.config:
        # 用户指定 TOML 路径
        store = load_toml(args.config)
    else:
        # 无参数 → 加载打包默认 config.toml
        default_toml = os.path.join(get_config_dir(), 'config.toml')
        store = load_toml(default_toml)

    if args.no_pity:
        store.pity.enabled = False

    # 为 output_data 构造 config 元数据 dict（替代旧 JSON config）
    config_meta = {
        'path': str(args.config) if args.config else default_toml,
        'num_pools': len(store.pools),
        'num_cards': len(store.card_defs),
        'pity_enabled': store.pity.enabled,
        'num_targets': len(store.target_cards),
    }

    # 策略覆盖逻辑
    if args.strategy:
        strategy_name = args.strategy  # CLI 参数优先
        if args.strategy_params:
            try:
                strategy_params = json.loads(args.strategy_params)
            except json.JSONDecodeError as e:
                print(f"错误：--strategy-params JSON 解析失败: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            strategy_params = store.strategy_params  # 回退 TOML 配置
    else:
        strategy_name = getattr(store, 'strategy_name', 'smart') or 'smart'
        strategy_params = store.strategy_params

    env = SimulationEnvBuilder.from_config_store(store)

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

    target_specs = {tc.card_id: getattr(tc, 'quantity', 1)
                    for tc in store.target_cards}

    def _cli_progress(done, total):
        if done % max(1, total // 10) == 0 or done >= total:
            print(f"\r  进度: {done}/{total} ({100*done//total}%)", end='', flush=True)

    print(f"\nRunning {args.num_simulations} simulations...")
    start_time = time.time()

    batch_result = run_batch_parallel(
        env=env,
        target_specs=target_specs,
        initial_resources=env.initial_resources,
        num_simulations=args.num_simulations,
        max_workers=args.workers,
        seed=args.seed,
        progress_callback=_cli_progress if not args.no_progress else None,
        strategy_name=strategy_name,
        strategy_params=strategy_params,
    )
    print()  # progress line 换行

    elapsed = time.time() - start_time

    print(f"Completed in {elapsed:.2f}s ({args.num_simulations/elapsed:.1f} sim/s)")

    actual_target_ids = [t.card_id for t in store.target_cards]
    if not actual_target_ids and store.pools:
        actual_target_ids = [f"{store.pools[0].pool_id}_ssr"]
    total_targets = len(actual_target_ids)

    total_draws = []
    ssr_counts = []
    gdr_percents = []

    for r in batch_result:
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
    print(f"Total Simulations: {len(batch_result)}")
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
                            'median': float(np.median(total_draws)),
                            'std': float(np.std(total_draws))},
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

    if args.output_format == 'full' and batch_result.extraction:
        output_data['extraction'] = {
            'n_results': batch_result.extraction.get('n_results', 0),
            'aggregates_count': len(
                batch_result.extraction.get('aggregates', [])),
            'kept_sequences_count': len(
                batch_result.extraction.get('kept_sequences', [])),
            'cumulative_snapshots_pools': list(
                batch_result.extraction.get('cumulative_snapshots', {}).keys()),
            'transition_flags_count': len(
                batch_result.extraction.get('transition_flags', [])),
        }

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\nResults saved to: {args.output}")
    print("=" * 50)


if __name__ == '__main__':
    main()
