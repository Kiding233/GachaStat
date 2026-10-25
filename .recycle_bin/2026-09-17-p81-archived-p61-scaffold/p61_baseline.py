"""P61 Ph1-base 基线固化。

用当前旧代码 + 现有 [[pools]] 配置跑固定种子模拟，把 CompactResult 序列化固化到
tests/fixtures/baseline_pool_golden.json。后续任何删字段/改键/迁移阶段，同种子重跑并
逐字段对比该 golden（P61 §3.12 Ph1-base）。

锚点：
- single：seed=42 单次 CompactResult 完整 to_dict（逐字段对比主锚点）
- batch：seed=42 起 N 次批量的聚合摘要（total_draws / pool_draw_counts / card_counts 求和）

用法：python scripts/p61_baseline.py [--config PATH] [--seed 42] [--n 1000]
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gacha_simulator.core.config_toml import load_toml  # noqa: E402
from gacha_simulator.service.batch_simulator import (  # noqa: E402
    SimulationEnvBuilder,
    _run_single,
    run_batch_parallel,
)
from gacha_simulator.core import TargetCard, TargetCardSet  # noqa: E402


def build_target_set(env, store):
    card_def_map = {c['card_id']: c for c in env.card_defs}
    targets = [
        TargetCard(
            card_id=tc.card_id,
            pool_ids=card_def_map.get(tc.card_id, {}).get('pools', []),
            quantity_needed=getattr(tc, 'quantity', 1),
        )
        for tc in store.target_cards
    ]
    return TargetCardSet(targets)


def aggregate_batch(results):
    n = len(results)
    total_draws = [r.total_draws for r in results]
    pool_draw_counts = {}
    card_counts = {}
    pity_triggers = 0
    for r in results:
        for pid, cnt in r.pool_draw_counts.items():
            pool_draw_counts[pid] = pool_draw_counts.get(pid, 0) + cnt
        for cid, cnt in r.card_counts.items():
            card_counts[cid] = card_counts.get(cid, 0) + cnt
        pity_triggers += r.pity_triggers
    return {
        'n': n,
        'total_draws_mean': sum(total_draws) / n if n else 0.0,
        'total_draws_min': min(total_draws) if n else 0,
        'total_draws_max': max(total_draws) if n else 0,
        'pool_draw_counts_sum': pool_draw_counts,
        'card_counts_sum': card_counts,
        'pity_triggers_sum': pity_triggers,
    }


def main():
    parser = argparse.ArgumentParser(description='P61 Ph1-base 基线固化')
    parser.add_argument('--config', default='gacha_simulator/config/config.toml')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--n', type=int, default=1000, help='批量模拟次数')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--out', default='tests/fixtures/baseline_pool_golden.json')
    args = parser.parse_args()

    store = load_toml(args.config)
    env = SimulationEnvBuilder.from_config_store(store)
    target_set = build_target_set(env, store)
    target_specs = {tc.card_id: getattr(tc, 'quantity', 1) for tc in store.target_cards}

    print(f'config: {args.config} | pools={len(env.pools)} end_time={env.end_time}')
    print(f'单次 seed={args.seed} 模拟…')
    compact = _run_single(env, target_set, args.seed, env.initial_resources)
    if compact is None:
        print('单次模拟失败（返回 None）', file=sys.stderr)
        sys.exit(1)

    print(f'批量 n={args.n} seed={args.seed}…')
    batch = run_batch_parallel(
        env=env,
        target_specs=target_specs,
        initial_resources=env.initial_resources,
        num_simulations=args.n,
        max_workers=args.workers,
        seed=args.seed,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'meta': {
            'config_path': str(args.config),
            'seed': args.seed,
            'batch_n': args.n,
            'generated_at': time.time(),
            'num_pools': len(env.pools),
            'end_time': env.end_time,
            'strategy_key': env.strategy_key,
        },
        'single': compact.to_dict(),
        'batch_aggregate': aggregate_batch(batch.results),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'已固化 golden → {out_path}')
    print(f'  single total_draws={compact.total_draws}')
    print(f'  batch total_draws_mean={payload["batch_aggregate"]["total_draws_mean"]:.1f}')


if __name__ == '__main__':
    main()
