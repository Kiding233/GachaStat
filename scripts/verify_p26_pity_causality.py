#!/usr/bin/env python3
"""
P26 保底机制因果验证——阶梯函数成因实测

核验主张：
  A) 无保底 → p(r) 平滑（阶梯函数依赖保底机制）
  B) reset=never → 阶梯数减少（reset=featured_ssr 创造多级阶梯）
  C) 阶梯数与目标卡数正相关（每张目标卡需要一个保底周期）
  D) 硬保底 vs 软保底 → 跳跃形状差异

方法：创建临时配置目录，修改 pity.txt，运行 p(r) 扫描，检测跳跃结构。

用法:
  python scripts/verify_p26_pity_causality.py
  python scripts/verify_p26_pity_causality.py --quick  # 快速模式（N=100, 15点）
"""

import sys
import os
import time
import json
import shutil
import tempfile
import argparse
from typing import Dict, List, Tuple, Optional

import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

CONFIG_SRC = os.path.join(PROJECT_ROOT, 'gacha_simulator', 'config')


def create_temp_config(modifications: Dict[str, Optional[str]]) -> str:
    """创建临时配置目录，复制所有配置文件，并对 pity.txt 应用修改。

    modifications: {'pity.txt': new_content_or_None}
        若值为 None → 不复制该文件（模拟无保底）
        若值为 str  → 用该内容替换原文件
    """
    tmpdir = tempfile.mkdtemp(prefix='p26_pity_')
    for fname in os.listdir(CONFIG_SRC):
        src = os.path.join(CONFIG_SRC, fname)
        dst = os.path.join(tmpdir, fname)
        if fname in modifications:
            if modifications[fname] is None:
                continue  # 跳过——模拟该文件不存在
            with open(dst, 'w', encoding='utf-8') as f:
                f.write(modifications[fname])
        else:
            if os.path.isfile(src):
                shutil.copy2(src, dst)
            elif os.path.isdir(src):
                shutil.copytree(src, dst)
    return tmpdir


def load_config_from_dir(config_dir: str):
    """从指定目录加载配置。"""
    from gacha_simulator.core.config_io import load_store_from_directory
    from gacha_simulator.core.config_store import ConfigStore
    store = ConfigStore()
    return load_store_from_directory(config_dir, store)


def run_p_scan(store, target_specs: Dict[str, int],
               gdr_key: str = 'all_targets',
               gdr_threshold: float = 1.0,
               num_simulations: int = 200,
               max_workers: int = 4,
               r_min: float = 160.0,
               r_max: float = 200000.0,
               n_points: int = 20) -> dict:
    """扫描 p(r) 曲线，返回概率序列和检测到的跳跃。"""
    from gacha_simulator.service.batch_simulator import (
        SimulationEnvBuilder, run_batch_parallel,
    )
    from gacha_simulator.core.gdr import compute_success_probability

    r_grid = np.unique(np.geomspace(r_min, r_max, n_points)).tolist()
    probs = []
    start = time.time()

    for r in r_grid:
        env = SimulationEnvBuilder.from_config_store(store)
        ir = dict(env.initial_resources)
        ir['draw_resource'] = float(r)

        histories = run_batch_parallel(
            env=env, target_specs=target_specs,
            initial_resources=ir, num_simulations=num_simulations,
            max_workers=max_workers,
            seed=hash(str(r)) % (2**31),
            strategy_name='smart',
        )
        p = compute_success_probability(histories, target_specs, gdr_key, gdr_threshold)
        probs.append(p)

    probs = np.array(probs)
    elapsed = time.time() - start

    # 跳跃检测
    delta_p = np.diff(probs)
    se = np.sqrt(np.clip(probs * (1 - probs) / num_simulations, 1e-10, None))
    jumps = []
    for i in range(len(delta_p)):
        se_avg = max((se[i] + se[i+1]) / 2.0, 1e-6)
        ratio = abs(delta_p[i]) / se_avg
        if ratio > 3.0 and abs(delta_p[i]) > 0.01:
            jumps.append({
                'r_from': float(r_grid[i]), 'r_to': float(r_grid[i+1]),
                'p_from': float(probs[i]), 'p_to': float(probs[i+1]),
                'delta_p': float(delta_p[i]), 'se_ratio': float(ratio),
            })

    # 阈值交叉点
    cross_r = None
    for i, p in enumerate(probs):
        if p >= 0.95:
            cross_r = float(r_grid[i])
            break

    # 判断是否为阶跃函数
    is_step = len(jumps) >= 1 and any(j['se_ratio'] > 10 for j in jumps)

    return {
        'r_grid': r_grid, 'probs': probs.tolist(),
        'jumps': jumps, 'n_jumps': len(jumps),
        'cross_r': cross_r, 'is_step': is_step,
        'elapsed_s': elapsed,
    }


def experiment_no_pity(target_specs, num_simulations=200, max_workers=4):
    """实验 A：无保底 → p(r) 是否变为平滑曲线。"""
    print("\n" + "=" * 70)
    print("实验 A: 无保底配置 —— p(r) 形状验证")
    print("=" * 70)
    print("假设：若无保底机制，p(r) 应为平滑 S 形曲线，无离散跳跃。")

    tmpdir = create_temp_config({'pity.txt': None})  # 不复制 pity.txt
    try:
        store = load_config_from_dir(tmpdir)
        result = run_p_scan(store, target_specs,
                           num_simulations=num_simulations,
                           max_workers=max_workers,
                           n_points=25)  # 更多点以观察平滑性
    finally:
        shutil.rmtree(tmpdir)

    print(f"\n结果 ({result['elapsed_s']:.0f}s):")
    print(f"  跳跃数: {result['n_jumps']}")
    print(f"  阈值交叉 r: {result['cross_r']}")
    print(f"  阶跃判断: {'是' if result['is_step'] else '否（平滑）'}")
    print(f"  p(r) 序列: {[f'{p:.3f}' for p in result['probs']]}")

    if result['n_jumps'] > 0:
        for j in result['jumps']:
            print(f"    跳: r [{j['r_from']:.0f}, {j['r_to']:.0f}] "
                  f"p {j['p_from']:.3f}→{j['p_to']:.3f} ({j['se_ratio']:.1f}×SE)")

    return result


def experiment_reset_never(target_specs, num_simulations=200, max_workers=4):
    """实验 B：reset=never → 阶梯数是否减少。"""
    print("\n" + "=" * 70)
    print("实验 B: reset=never —— 阶梯数验证")
    print("=" * 70)
    print("假设：不重置保底计数器 → 一旦触发软保底 (90抽)，后续所有抽卡均为100%限定SSR，")
    print("      因此阶梯数应显著减少（预期 1 跳而非 3 跳）。")

    # 读取原 pity.txt，修改 reset=featured_ssr → reset=never
    src_pity = os.path.join(CONFIG_SRC, 'pity.txt')
    with open(src_pity, 'r', encoding='utf-8') as f:
        content = f.read()
    modified = content.replace('reset=featured_ssr', 'reset=never')

    tmpdir = create_temp_config({'pity.txt': modified})
    try:
        store = load_config_from_dir(tmpdir)
        result = run_p_scan(store, target_specs,
                           num_simulations=num_simulations,
                           max_workers=max_workers,
                           n_points=25)
    finally:
        shutil.rmtree(tmpdir)

    print(f"\n结果 ({result['elapsed_s']:.0f}s):")
    print(f"  跳跃数: {result['n_jumps']}")
    print(f"  阈值交叉 r: {result['cross_r']}")
    print(f"  阶跃判断: {'是' if result['is_step'] else '否'}")
    print(f"  p(r) 序列: {[f'{p:.3f}' for p in result['probs']]}")
    if result['jumps']:
        for j in result['jumps']:
            print(f"    跳: r [{j['r_from']:.0f}, {j['r_to']:.0f}] "
                  f"p {j['p_from']:.3f}→{j['p_to']:.3f} ({j['se_ratio']:.1f}×SE)")

    return result


def experiment_hard_pity(target_specs, num_simulations=200, max_workers=4):
    """实验 D：硬保底 vs 软保底 —— 跳跃形状差异。"""
    print("\n" + "=" * 70)
    print("实验 D: 硬保底配置 —— 跳跃形状对比")
    print("=" * 70)
    print("假设：硬保底在 threshold=90 处概率直接跳至 100%（不经过 80-90 的渐进区间），")
    print("      跳跃应更尖锐、位置更精确地在 90×cost 的整数倍处。")

    # 将软保底替换为硬保底
    hard_pity_content = """# Pity Configuration — 硬保底变体（实验用）
#
pity: ssr_hard | type=hard | threshold=90 | target=limited_ssr:100 | reset=featured_ssr | pools=pool_c*
"""
    tmpdir = create_temp_config({'pity.txt': hard_pity_content})
    try:
        store = load_config_from_dir(tmpdir)
        result = run_p_scan(store, target_specs,
                           num_simulations=num_simulations,
                           max_workers=max_workers,
                           n_points=25)
    finally:
        shutil.rmtree(tmpdir)

    print(f"\n结果 ({result['elapsed_s']:.0f}s):")
    print(f"  跳跃数: {result['n_jumps']}")
    print(f"  阈值交叉 r: {result['cross_r']}")
    print(f"  阶跃判断: {'是' if result['is_step'] else '否'}")
    print(f"  p(r) 序列: {[f'{p:.3f}' for p in result['probs']]}")
    if result['jumps']:
        for j in result['jumps']:
            print(f"    跳: r [{j['r_from']:.0f}, {j['r_to']:.0f}] "
                  f"p {j['p_from']:.3f}→{j['p_to']:.3f} ({j['se_ratio']:.1f}×SE)")

    return result


def experiment_target_count_variation(all_target_specs, num_simulations=200, max_workers=4):
    """实验 C：2/3/4/5 张目标卡 → 阶梯数与目标卡数的关系。"""
    print("\n" + "=" * 70)
    print("实验 C: 目标卡数量变化 —— 阶梯数 vs 目标卡数")
    print("=" * 70)
    print("假设：每张目标卡需要一个保底周期（~80-90抽），阶梯数应与目标卡数正相关。")

    card_ids = list(all_target_specs.keys())
    results = {}

    for n in [2, 3, 4, 5, 6]:
        subset = {cid: all_target_specs[cid] for cid in card_ids[:n]}
        label = f"{n}卡"

        store = load_config_from_dir(CONFIG_SRC)
        result = run_p_scan(store, subset,
                           num_simulations=num_simulations,
                           max_workers=max_workers,
                           r_max=250000.0,
                           n_points=25)
        results[label] = result

        print(f"\n  {label}: {result['n_jumps']} 跳, "
              f"交叉 r={result['cross_r']}, "
              f"阶跃={'是' if result['is_step'] else '否'}")
        if result['jumps']:
            for j in result['jumps']:
                print(f"    跳: r [{j['r_from']:.0f}, {j['r_to']:.0f}] "
                      f"p {j['p_from']:.3f}→{j['p_to']:.3f} ({j['se_ratio']:.1f}×SE)")

    # 汇总
    print("\n汇总: 阶梯数与目标卡数的关系")
    for label, r in results.items():
        print(f"  {label}: {r['n_jumps']} 跳, 交叉 r={r['cross_r']}")

    # 计算阶梯数与目标卡数的相关性
    ns = [2, 3, 4, 5, 6]
    jump_counts = [results[f"{n}卡"]['n_jumps'] for n in ns]
    if len(set(jump_counts)) > 1:
        corr = np.corrcoef(ns, jump_counts)[0, 1]
        print(f"  相关系数 (n_cards vs n_jumps): {corr:.3f}")

    return results


def main():
    parser = argparse.ArgumentParser(description='P26 保底机制因果验证')
    parser.add_argument('--quick', action='store_true', help='快速模式 (N=100, 15点)')
    parser.add_argument('--exp', type=str, default='A,B,C,D',
                       help='要运行的实验 (逗号分隔), 默认全部')
    parser.add_argument('--workers', '-w', type=int, default=4)
    args = parser.parse_args()

    n_sims = 100 if args.quick else 200
    n_points = 15 if args.quick else 25
    print(f"参数: N={n_sims}/点, workers={args.workers}")
    if args.quick:
        print("[快速模式]")

    # 加载默认配置获取目标卡
    store = load_config_from_dir(CONFIG_SRC)
    all_targets = {}
    for tc in store.target_cards:
        all_targets[tc.card_id] = getattr(tc, 'quantity', 1)
    print(f"目标卡: {all_targets}")

    exp_list = [e.strip().upper() for e in args.exp.split(',')]
    all_results = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'params': {'n_sims': n_sims, 'n_points': n_points, 'targets': all_targets},
    }

    total_start = time.time()

    if 'A' in exp_list:
        all_results['expA_no_pity'] = experiment_no_pity(all_targets, n_sims, args.workers)
    if 'B' in exp_list:
        all_results['expB_reset_never'] = experiment_reset_never(all_targets, n_sims, args.workers)
    if 'C' in exp_list:
        all_results['expC_target_count'] = experiment_target_count_variation(all_targets, n_sims, args.workers)
    if 'D' in exp_list:
        all_results['expD_hard_pity'] = experiment_hard_pity(all_targets, n_sims, args.workers)

    total_time = time.time() - total_start
    all_results['total_time_s'] = total_time

    # 保存结果
    output_dir = os.path.join(PROJECT_ROOT, 'output')
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    output_path = os.path.join(output_dir, f'p26_pity_causality_{timestamp}.json')

    # 清理不可序列化的 numpy 类型
    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(clean(all_results), f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 70}")
    print(f"全部实验完成。总耗时: {total_time:.0f}s = {total_time/60:.1f}min")
    print(f"结果: {output_path}")

    # 综合结论
    print(f"\n{'=' * 70}")
    print("综合结论:")
    print("─" * 50)

    expA = all_results.get('expA_no_pity', {})
    expB = all_results.get('expB_reset_never', {})
    expD = all_results.get('expD_hard_pity', {})
    expC = all_results.get('expC_target_count', {})

    print(f"A) 无保底: {expA.get('n_jumps', '?')} 跳, "
          f"阶跃={'是' if expA.get('is_step') else '否（平滑）'} → "
          f"{'阶梯函数依赖保底机制' if not expA.get('is_step') else '阶梯函数不依赖保底（意外！）'}")

    print(f"B) reset=never: {expB.get('n_jumps', '?')} 跳 vs "
          f"默认 reset=featured_ssr: 3 跳 → "
          f"{'reset=featured_ssr 创造多级阶梯' if expB.get('n_jumps', 99) < 3 else 'reset 不影响阶梯数（意外！）'}")

    if expC:
        jump_by_n = {k: v['n_jumps'] for k, v in expC.items()}
        print(f"C) 阶梯数 vs 目标卡数: {jump_by_n}")

    print(f"D) 硬保底: {expD.get('n_jumps', '?')} 跳 (软保底: 3 跳)")

    return all_results


if __name__ == '__main__':
    main()
