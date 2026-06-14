#!/usr/bin/env python3
"""
P26 理论改进计划——实际抽卡模拟器集成测试

与 verify_p26_claims.py（解析函数实验）互补——本脚本加载实际配置文件，
运行完整 GachaService 模拟，测量二分搜索在实际噪声结构下的行为。

实验:
  9  — 实际配置二分搜索基线（偏差/方差/决策正确率）
  11 — 实际跳跃幅度测量（精细资源网格扫描，检测硬保底跳跃）
  12 — 前进/后退路径分歧度（不同 desire/miss_cost 权重）

预计总耗时: 1–3 小时（取决于配置复杂度和并行度）

用法:
  python scripts/verify_p26_integration.py            # 运行全部
  python scripts/verify_p26_integration.py --exp 9    # 仅运行实验 9
  python scripts/verify_p26_integration.py --exp 9,11 # 运行实验 9 和 11
  python scripts/verify_p26_integration.py --n-runs 50  # 自定义重复次数

生成时间: 2026-06-09
依赖: gacha_simulator 核心模块 + 实际配置文件
"""

import sys
import os
import time
import json
import argparse
import zlib
from typing import Dict, List, Tuple, Optional, Callable
from dataclasses import dataclass, field

import numpy as np

# 将项目根目录加入路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def load_config(config_dir: str = None):
    """加载默认配置。"""
    if config_dir is None:
        config_dir = os.path.join(PROJECT_ROOT, 'gacha_simulator', 'config')
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.core.config_store import ConfigStore
    store = ConfigStore()
    return load_toml(os.path.join(config_dir, 'config.toml'), store)


def load_default_targets(store) -> Dict[str, int]:
    """从配置中读取默认目标卡（store 已通过 load_toml 加载）。"""
    # 主路径：store.target_cards 已由 load_store_from_directory 填充
    if hasattr(store, 'target_cards') and store.target_cards:
        targets = {}
        for tc in store.target_cards:
            targets[tc.card_id] = getattr(tc, 'quantity', 1)
        return targets
    # 回退：尝试直接读取 targets.txt
    config_dir = os.path.join(PROJECT_ROOT, 'gacha_simulator', 'config')
    targets_path = os.path.join(config_dir, 'targets.txt')
    if os.path.exists(targets_path):
        targets = {}
        with open(targets_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split(':')
                if len(parts) >= 2:
                    targets[parts[0].strip()] = int(parts[1].strip())
        return targets
    # 最终回退：硬编码简单目标
    print("[警告] 未找到目标卡配置，使用回退目标配置")
    return {'character_5star': 1}


@dataclass
class SearchRun:
    """单次二分搜索运行记录。"""
    estimate: float
    min_resource: float
    final_prob: float
    success: bool
    n_iterations: int
    n_simulations: int
    binary_steps: List[dict] = field(default_factory=list)


def run_single_binary_search(
    store, target_specs: Dict[str, int],
    success_threshold: float = 0.95,
    gdr_key: str = 'all_targets',
    num_simulations: int = 500,
    upper_bound: float = 55000.0,
    max_workers: int = 4,
    seed_offset: int = 0,
) -> SearchRun:
    """执行一次完整的二分搜索，返回 SearchRun。"""
    from gacha_simulator.core.retreat_search import PlanSearchEngine

    steps_log = []
    progress_msgs = []

    def progress_cb(msg: str, pct: int):
        progress_msgs.append((msg, pct))

    engine = PlanSearchEngine(
        config_store=store,
        from_pool_id=None,
        base_resource=0.0,
        success_threshold=success_threshold,
        gdr_key=gdr_key,
        num_simulations=num_simulations,
        max_workers=max_workers,
        upper_bound=upper_bound,
        progress_callback=progress_cb,
    )

    result = engine.search_min_resource(target_specs)

    # 提取步骤详情
    steps = []
    for s in getattr(result, 'binary_steps', []):
        steps.append({
            'iteration': getattr(s, 'iteration', 0),
            'resource_value': getattr(s, 'resource_value', 0.0),
            'success_probability': getattr(s, 'success_probability', 0.0),
            'phase': getattr(s, 'phase', ''),
        })

    return SearchRun(
        estimate=getattr(result, 'min_resource', 0.0) - getattr(result, 'base_resource', 0.0),
        min_resource=getattr(result, 'min_resource', 0.0),
        final_prob=getattr(result, 'final_success_probability', 0.0),
        success=getattr(result, 'success', False),
        n_iterations=getattr(result, 'total_iterations', 0),
        n_simulations=num_simulations * getattr(result, 'total_iterations', 0),
        binary_steps=steps,
    )


def run_simulation_at_resource(
    store, target_specs: Dict[str, int],
    resource_value: float,
    gdr_key: str = 'all_targets',
    gdr_threshold: float = 1.0,
    num_simulations: int = 500,
    max_workers: int = 4,
    seed: int = 0,
) -> float:
    """在给定资源水平运行 N 次模拟，返回成功率。"""
    from gacha_simulator.service.batch_simulator import (
        SimulationEnvBuilder, run_batch_parallel,
    )
    from gacha_simulator.core.gdr import compute_success_probability

    env = SimulationEnvBuilder.from_config_store(store)
    ir = dict(env.initial_resources)
    ir['draw_resource'] = resource_value

    histories = run_batch_parallel(
        env=env,
        target_specs=target_specs,
        initial_resources=ir,
        num_simulations=num_simulations,
        max_workers=max_workers,
        seed=seed,
        strategy_name='smart',
    )
    return compute_success_probability(histories, target_specs, gdr_key, gdr_threshold)


# ═══════════════════════════════════════════════════════════════════════════════
# 实验 9: 实际配置二分搜索基线
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_9_real_config_baseline(
    store, target_specs: Dict[str, int],
    n_runs: int = 50,
    num_simulations: int = 500,
    success_threshold: float = 0.95,
    gdr_key: str = 'all_targets',
    max_workers: int = 4,
    checkpoint_path: Optional[str] = None,
):
    """核验：实际配置上二分搜索的偏差、方差、决策正确率。

    对比解析函数实验 2（logistic, k=0.0005）的结果，判断实际噪声结构
    是更接近平滑 logistic 还是有额外复杂性（保底跳跃、多池交互等）。

    每 10 次搜索自动保存中间检查点，崩溃后可从此恢复。
    """
    print("\n" + "=" * 70)
    print("实验 9: 实际配置二分搜索基线")
    print("=" * 70)

    print(f"\n参数: N={num_simulations}/步, theta={success_threshold}, "
          f"GDR={gdr_key}, {n_runs}次独立搜索")
    print(f"目标卡: {target_specs}")

    # 如果没有指定检查点路径，自动生成
    if checkpoint_path is None:
        output_dir = os.path.join(PROJECT_ROOT, 'output')
        os.makedirs(output_dir, exist_ok=True)
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        checkpoint_path = os.path.join(output_dir, f'p26_exp9_checkpoint_{timestamp}.json')

    start_time = time.time()
    runs: List[SearchRun] = []
    checkpoint_interval = 10  # 每 10 次搜索保存一次

    for i in range(n_runs):
        if i % 10 == 0 or i == n_runs - 1:
            elapsed = time.time() - start_time
            eta = (elapsed / max(i, 1)) * (n_runs - i) if i > 0 else float('nan')
            print(f"  进度: {i}/{n_runs} ({i/n_runs:.0%}), "
                  f"已耗时 {elapsed:.0f}s, 预计剩余 {eta:.0f}s")

        run = run_single_binary_search(
            store, target_specs,
            success_threshold=success_threshold,
            gdr_key=gdr_key,
            num_simulations=num_simulations,
            max_workers=max_workers,
            seed_offset=i * 1000,
        )
        runs.append(run)

        # 中间检查点：每 checkpoint_interval 次搜索保存一次
        if (i + 1) % checkpoint_interval == 0 or i == n_runs - 1:
            estimates_sofar = [r.estimate for r in runs]
            checkpoint_data = {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'completed': i + 1,
                'total': n_runs,
                'elapsed_s': time.time() - start_time,
                'estimates_sofar': estimates_sofar,
                'mean_sofar': float(np.mean(estimates_sofar)),
                'std_sofar': float(np.std(estimates_sofar)),
                'n_success_sofar': sum(1 for r in runs if r.success),
                'runs_summary': [
                    {'estimate': r.estimate, 'final_prob': r.final_prob,
                     'success': r.success, 'n_iterations': r.n_iterations}
                    for r in runs
                ],
            }
            try:
                with open(checkpoint_path, 'w', encoding='utf-8') as f:
                    json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)
            except OSError as e:
                print(f"  [警告] 检查点保存失败: {e}")

    total_time = time.time() - start_time
    estimates = np.array([r.estimate for r in runs])
    final_probs = np.array([r.final_prob for r in runs])

    # 计算统计量
    mean_est = estimates.mean()
    median_est = np.median(estimates)
    std_est = estimates.std()
    cv_est = std_est / mean_est if mean_est > 0 else float('nan')

    # 决策正确率：按照二分搜索每一步的决策
    # （实际配置没有 ground truth，用收敛一致性作为代理）
    n_success = sum(1 for r in runs if r.success)
    mean_iters = np.mean([r.n_iterations for r in runs])
    mean_sims = np.mean([r.n_simulations for r in runs])

    print(f"\n结果 ({n_runs} 次独立搜索, 总耗时 {total_time:.0f}s = {total_time/60:.1f}min):")
    print(f"  估计均值: {mean_est:.0f} 资源")
    print(f"  估计中位数: {median_est:.0f} 资源")
    print(f"  标准差: {std_est:.0f} 资源")
    print(f"  变异系数 (CV): {cv_est:.2%}")
    print(f"  成功率: {n_success}/{n_runs} ({n_success/n_runs:.1%})")
    print(f"  平均迭代次数: {mean_iters:.1f}")
    print(f"  平均总模拟次数: {mean_sims:.0f}")
    print(f"  最终成功率均值: {final_probs.mean():.4f} ± {final_probs.std():.4f}")

    # 分布特征
    pct_5, pct_25, pct_75, pct_95 = np.percentile(estimates, [5, 25, 75, 95])
    print(f"  估计分布: [5%={pct_5:.0f}, 25%={pct_25:.0f}, "
          f"75%={pct_75:.0f}, 95%={pct_95:.0f}]")
    print(f"  四分位距 (IQR): {pct_75 - pct_25:.0f}")

    # 与解析函数基线对比
    print(f"\n与解析函数基线对比 (logistic k=0.0005, 实验 2):")
    print(f"  解析 std: 291, 实际 std: {std_est:.0f}")
    if std_est > 291 * 1.5:
        print(f"  [注意] 实际噪声显著大于解析基线 (x{std_est/291:.1f})——"
              f"可能受保底跳跃或多池交互影响")
    elif std_est < 291 * 0.5:
        print(f"  [注意] 实际噪声显著小于解析基线 (x{std_est/291:.1f})——"
              f"实际 p(r) 可能更陡峭")
    else:
        print(f"  [通过] 实际噪声与解析基线可比 (x{std_est/291:.1f})")

    return {
        'n_runs': n_runs,
        'mean': float(mean_est),
        'median': float(median_est),
        'std': float(std_est),
        'cv': float(cv_est),
        'n_success': n_success,
        'success_rate': n_success / n_runs,
        'mean_iters': float(mean_iters),
        'mean_sims': float(mean_sims),
        'mean_final_prob': float(final_probs.mean()),
        'std_final_prob': float(final_probs.std()),
        'total_time_s': total_time,
        'estimates': estimates.tolist(),
        'checkpoint_path': checkpoint_path,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 实验 11: 实际跳跃幅度测量
# ═══════════════════════════════════════════════════════════════════════════════

def estimate_cost_per_draw(store) -> float:
    """从配置中估算每抽成本。"""
    if hasattr(store, 'pools') and store.pools:
        for pe in store.pools:
            cost_str = getattr(pe, 'cost', 'draw_resource:160')
            if cost_str:
                try:
                    # 格式: "draw_resource:160" 或 "resource:100, resource2:50"
                    parts = cost_str.split(',')[0].strip()
                    value = float(parts.split(':')[-1].strip())
                    return value
                except (ValueError, IndexError):
                    pass
    return 160.0  # 默认


def experiment_11_jump_magnitude_measurement(
    store, target_specs: Dict[str, int],
    gdr_key: str = 'all_targets',
    gdr_threshold: float = 1.0,
    num_simulations: int = 500,
    max_workers: int = 4,
    r_min: float = 0.0,
    r_max: float = 200000.0,
    n_points: int = 60,
    convergence_hint: float = None,
):
    """核验：在实际配置上测量 p(r) 曲线，检测硬保底跳跃。

    以 cost_per_draw 的整数倍为步长扫描资源范围，
    每个点运行 num_simulations 次模拟，
    检测 Deltap > 3xSE 的跳跃位置和幅度。
    """
    print("\n" + "=" * 70)
    print("实验 11: 实际 p(r) 曲线扫描——硬保底跳跃幅度测量")
    print("=" * 70)

    cost_per_draw = estimate_cost_per_draw(store)
    se_ref = np.sqrt(0.95 * 0.05 / num_simulations)  # 参考 SE

    # 自适应网格：在低资源区稀疏，在高资源区（可能接近阈值）加密
    # 这里使用对数间隔以覆盖宽资源范围
    r_grid = np.unique(np.geomspace(
        max(r_min, cost_per_draw), r_max, n_points
    ).astype(int).astype(float))

    print(f"\n参数: N={num_simulations}/点, SE~{se_ref:.4f}, "
          f"每抽成本~{cost_per_draw:.0f}")
    print(f"资源网格: {len(r_grid)} 点, 范围 [{r_grid[0]:.0f}, {r_grid[-1]:.0f}]")
    print(f"目标卡: {target_specs}")
    print(f"预计耗时: ~{len(r_grid) * 5:.0f}–{len(r_grid) * 15:.0f} 秒")

    start_time = time.time()

    # 逐点测量 p(r)
    probs = []
    for i, r in enumerate(r_grid):
        if i % 10 == 0:
            elapsed = time.time() - start_time
            eta = (elapsed / max(i, 1)) * (len(r_grid) - i)
            print(f"  进度: {i}/{len(r_grid):.0f}, r={r:.0f}, "
                  f"已耗时 {elapsed:.0f}s, ETA {eta:.0f}s")

        p = run_simulation_at_resource(
            store, target_specs, r,
            gdr_key=gdr_key,
            gdr_threshold=gdr_threshold,
            num_simulations=num_simulations,
            max_workers=max_workers,
            seed=hash(str(r)) % (2**31),
        )
        probs.append(p)

    probs = np.array(probs)
    total_time = time.time() - start_time

    # 检测跳跃：连续点之间的 Deltap
    delta_p = np.diff(probs)
    # 每个点的 SE: sqrt(p*(1-p)/N)
    se_per_point = np.sqrt(probs * (1 - probs) / num_simulations)

    # 检测显著跳跃 (> 3xSE)
    jumps = []
    for i in range(len(delta_p)):
        se_avg = (se_per_point[i] + se_per_point[i + 1]) / 2.0
        se_avg = max(se_avg, 1e-6)
        ratio = abs(delta_p[i]) / se_avg
        if ratio > 3.0 and abs(delta_p[i]) > 0.01:
            jumps.append({
                'r_from': float(r_grid[i]),
                'r_to': float(r_grid[i + 1]),
                'p_from': float(probs[i]),
                'p_to': float(probs[i + 1]),
                'delta_p': float(delta_p[i]),
                'se_ratio': float(ratio),
                'direction': 'up' if delta_p[i] > 0 else 'down',
            })

    # 查找阈值交叉点 (p 首次超过 success_threshold=0.95)
    cross_idx = None
    for i in range(len(probs)):
        if probs[i] >= 0.95:
            cross_idx = i
            break

    print(f"\n结果 (总耗时 {total_time:.0f}s = {total_time/60:.1f}min):")
    print(f"  检测到 {len(jumps)} 个显著跳跃 (> 3xSE):")
    if jumps:
        for j in jumps:
            direction = "UP" if j['direction'] == 'up' else "DOWN"
            print(f"    r in [{j['r_from']:.0f}, {j['r_to']:.0f}]: "
                  f"p {j['p_from']:.3f}→{j['p_to']:.3f} "
                  f"(Deltap={j['delta_p']:+.4f}, {j['se_ratio']:.1f}xSE {direction})")
            if j['se_ratio'] >= 6.0:
                print(f"      [[!!] 高锚定风险] 跳跃/SE >= 6——二分搜索可能受几何锚定影响")
            elif j['se_ratio'] >= 3.0:
                print(f"      [低风险] 跳跃/SE in [3, 6)——二分搜索应跨跳跃点搜索")
    else:
        print(f"    (无)——实际 p(r) 曲线无显著跳跃")

    print(f"\n  阈值交叉: p 首次 >= 0.95 在 r ~ "
          f"{r_grid[cross_idx]:.0f}" if cross_idx else "  未达到 0.95 阈值")

    # k 值估计：在 p in [0.6, 0.95] 区间拟合 logistic
    mask = (probs >= 0.6) & (probs <= 0.95)
    k_estimate = None
    if mask.sum() >= 4:
        r_fit = r_grid[mask]
        p_fit = probs[mask]
        # logit(p) = k*(r - r₀)，线性拟合 logit(p) ~ r
        logit_p = np.log(np.clip(p_fit, 1e-6, 1 - 1e-6) / (1 - np.clip(p_fit, 1e-6, 1 - 1e-6)))
        try:
            slope, intercept = np.polyfit(r_fit, logit_p, 1)
            k_estimate = slope
            r0_estimate = -intercept / slope if slope != 0 else float('nan')
            print(f"  logistic 拟合: k ~ {k_estimate:.6f}, r₀ ~ {r0_estimate:.0f}")
            # 与解析实验的 k 范围对比
            if k_estimate and k_estimate < 0.0002:
                print(f"  [[!!] 平坦] k={k_estimate:.6f} < 0.0002——临界区比例高，"
                      f"二分搜索方差可能较大")
            elif k_estimate and k_estimate > 0.001:
                print(f"  [[OK] 陡峭] k={k_estimate:.6f} > 0.001——临界区比例低，"
                      f"二分搜索判别力好")
        except Exception as e:
            print(f"  logistic 拟合失败: {e}")

    # 最大跳跃信息
    if jumps:
        max_jump = max(jumps, key=lambda j: j['se_ratio'])
        print(f"\n  最大跳跃: {max_jump['se_ratio']:.1f}xSE "
              f"({max_jump['delta_p']:+.4f}) "
              f"在 r~{max_jump['r_from']:.0f}–{max_jump['r_to']:.0f}")

    return {
        'r_grid': r_grid.tolist(),
        'probs': probs.tolist(),
        'delta_p': delta_p.tolist(),
        'jumps': jumps,
        'cross_idx': cross_idx,
        'k_estimate': float(k_estimate) if k_estimate else None,
        'total_time_s': total_time,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 实验 12: 前进/后退路径分歧度
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_12_path_divergence(
    store, target_specs: Dict[str, int],
    gdr_key: str = 'weighted_satisfaction',
    gdr_threshold: float = 0.5,
    num_simulations: int = 500,
    max_workers: int = 4,
):
    """核验：不同 desire/miss_cost 权重配置下，前进法 vs 后退法的分歧度。

    使用 weighted_satisfaction GDR（需要 desire_weights 和 miss_cost_weights），
    构造两个权重配置：
      A: desire >> miss_cost（极端偏好达成目标，不关心错过代价）
      B: desire << miss_cost（极端偏好避免错失代价）
    分别运行前进法和后退法，测量 Jaccard 距离。
    """
    print("\n" + "=" * 70)
    print("实验 12: 前进/后退路径分歧度")
    print("=" * 70)

    from gacha_simulator.core.retreat_search import PlanSearchEngine

    # 权重配置
    card_ids = list(target_specs.keys())

    # 配置 A: 所有卡等权 desire，低 miss_cost
    desire_a = {cid: 1.0 for cid in card_ids}
    miss_a = {cid: 0.1 for cid in card_ids}

    # 配置 B: 低 desire，高 miss_cost
    desire_b = {cid: 0.1 for cid in card_ids}
    miss_b = {cid: 1.0 for cid in card_ids}

    configs = [
        ('desire>>miss (A)', desire_a, miss_a),
        ('desire<<miss (B)', desire_b, miss_b),
    ]

    results = {}
    for label, desire, miss in configs:
        print(f"\n配置 {label}:")
        print(f"  add_order: {desire}")
        print(f"  remove_order: {miss}")

        # 前进法: search_max_targets_forward
        engine_fwd = PlanSearchEngine(
            config_store=store,
            from_pool_id=None,
            base_resource=0.0,
            add_order=desire,
            remove_order=miss,
            gdr_key=gdr_key,
            gdr_threshold=gdr_threshold,
            num_simulations=num_simulations,
            max_workers=max_workers,
        )
        result_fwd = engine_fwd.search_max_targets_forward(target_specs)
        fwd_points = getattr(result_fwd, 'points', [])
        fwd_specs = {(tuple(sorted(p.target_specs.items())), p.extra_resource)
                     for p in fwd_points}

        # 后退法: search_max_targets（逐张移除，即"后退"）
        engine_bwd = PlanSearchEngine(
            config_store=store,
            from_pool_id=None,
            base_resource=0.0,
            add_order=desire,
            remove_order=miss,
            gdr_key=gdr_key,
            gdr_threshold=gdr_threshold,
            num_simulations=num_simulations,
            max_workers=max_workers,
        )
        result_bwd = engine_bwd.search_max_targets(target_specs)
        bwd_points = getattr(result_bwd, 'points', [])
        bwd_specs = {(tuple(sorted(p.target_specs.items())), p.extra_resource)
                     for p in bwd_points}

        # Jaccard 距离: 1 - |交集| / |并集|
        intersection = fwd_specs & bwd_specs
        union = fwd_specs | bwd_specs
        jaccard = len(intersection) / max(len(union), 1)
        jaccard_dist = 1 - jaccard

        print(f"  前进法点数: {len(fwd_specs)}")
        print(f"  后退法点数: {len(bwd_specs)}")
        print(f"  交集: {len(intersection)}, 并集: {len(union)}")
        print(f"  Jaccard 相似度: {jaccard:.3f}, 距离: {jaccard_dist:.3f}")

        # 列出仅在前进或仅在后退中的点
        only_fwd = fwd_specs - bwd_specs
        only_bwd = bwd_specs - fwd_specs
        if only_fwd:
            print(f"  仅在前进中: {len(only_fwd)} 点")
        if only_bwd:
            print(f"  仅在后退中: {len(only_bwd)} 点")

        results[label] = {
            'n_fwd': len(fwd_specs),
            'n_bwd': len(bwd_specs),
            'intersection': len(intersection),
            'union': len(union),
            'jaccard': float(jaccard),
            'jaccard_distance': float(jaccard_dist),
        }

    # 跨配置比较
    print("\n跨配置比较:")
    for label, r in results.items():
        print(f"  {label}: Jaccard 距离 = {r['jaccard_distance']:.3f}")
    if len(results) == 2:
        a_dist = results[list(results.keys())[0]]['jaccard_distance']
        b_dist = results[list(results.keys())[1]]['jaccard_distance']
        print(f"  分歧度差异: {abs(a_dist - b_dist):.3f}")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 实验 14: 多 GDR 类型 p(r) 形状对比
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_14_multi_gdr_comparison(
    store, target_specs: Dict[str, int],
    gdr_configs: List[Tuple[str, float, str]] = None,
    num_simulations: int = 300,
    max_workers: int = 4,
    r_max: float = 200000.0,
    n_points: int = 40,
):
    """核验：不同 GDR 类型下 p(r) 曲线形状是否一致为阶跃函数。

    对比至少 3 种 GDR：
      - all_targets (二值)：成功=全部获得
      - target_achievement (连续)：成功=加权达成率 >= 阈值
      - resource_efficiency (连续, lower_is_better=false)：效率指标
    """
    if gdr_configs is None:
        gdr_configs = [
            ('all_targets', 1.0, '二值：全部目标卡获得'),
            ('target_achievement', 0.8, '连续：加权目标达成率 >= 0.8'),
            ('resource_efficiency', 0.3, '连续：资源效率 >= 0.3'),
        ]

    from gacha_simulator.core.retreat_search import PlanSearchEngine

    print("\n" + "=" * 70)
    print("实验 14: 多 GDR 类型 p(r) 曲线形状对比")
    print("=" * 70)

    cost_per_draw = estimate_cost_per_draw(store)

    all_results = {}
    for gdr_key, gdr_threshold, description in gdr_configs:
        print(f"\n--- GDR: {gdr_key} (阈值={gdr_threshold}, {description}) ---")

        # 小规模二分搜索先找收敛点，用于确定扫描范围
        print("  先搜索收敛点以确定扫描范围...")
        engine = PlanSearchEngine(
            config_store=store,
            from_pool_id=None,
            base_resource=0.0,
            gdr_key=gdr_key,
            gdr_threshold=gdr_threshold,
            num_simulations=num_simulations,
            max_workers=max_workers,
            upper_bound=r_max,
        )
        result = engine.search_min_resource(target_specs)
        conv_point = getattr(result, 'min_resource', r_max)
        conv_prob = getattr(result, 'final_success_probability', 0.0)
        conv_success = getattr(result, 'success', False)
        print(f"  收敛点: r={conv_point:.0f}, p={conv_prob:.4f}, "
              f"success={conv_success}, iters={getattr(result, 'total_iterations', 0)}")

        # 扫描范围：从 0 到 1.5x收敛点（至少 r_max/4）
        scan_max = max(conv_point * 1.5, r_max / 4) if conv_success else r_max
        r_grid = np.unique(np.geomspace(
            max(cost_per_draw, 100.0), scan_max, n_points
        ).astype(int).astype(float))

        print(f"  扫描: {len(r_grid)} 点, 范围 [{r_grid[0]:.0f}, {r_grid[-1]:.0f}]")

        probs = []
        start_time = time.time()
        for i, r in enumerate(r_grid):
            if i % 10 == 0 and i > 0:
                elapsed = time.time() - start_time
                eta = (elapsed / i) * (len(r_grid) - i)
                print(f"    进度: {i}/{len(r_grid)}, r={r:.0f}, "
                      f"已耗时 {elapsed:.0f}s, ETA {eta:.0f}s")

            p = run_simulation_at_resource(
                store, target_specs, r,
                gdr_key=gdr_key,
                gdr_threshold=gdr_threshold,
                num_simulations=num_simulations,
                max_workers=max_workers,
                seed=hash(f"{gdr_key}_{r}") % (2**31),
            )
            probs.append(p)

        probs = np.array(probs)
        total_time = time.time() - start_time

        # 检测跳跃
        delta_p = np.diff(probs)
        se_per_point = np.sqrt(np.clip(probs * (1 - probs) / num_simulations, 1e-10, None))
        jumps = []
        for j in range(len(delta_p)):
            se_avg = max((se_per_point[j] + se_per_point[j + 1]) / 2.0, 1e-6)
            ratio = abs(delta_p[j]) / se_avg
            if ratio > 3.0 and abs(delta_p[j]) > 0.01:
                jumps.append({
                    'r_from': float(r_grid[j]),
                    'r_to': float(r_grid[j + 1]),
                    'p_from': float(probs[j]),
                    'p_to': float(probs[j + 1]),
                    'delta_p': float(delta_p[j]),
                    'se_ratio': float(ratio),
                })

        # 估计 k 值
        mask = (probs >= 0.3) & (probs <= 0.95)
        k_estimate = None
        r0_estimate = None
        if mask.sum() >= 4:
            r_fit = r_grid[mask]
            p_fit = np.clip(probs[mask], 1e-6, 1 - 1e-6)
            logit_p = np.log(p_fit / (1 - p_fit))
            try:
                slope, intercept = np.polyfit(r_fit, logit_p, 1)
                k_estimate = slope
                r0_estimate = -intercept / slope if slope != 0 else float('nan')
            except Exception:
                pass

        # 阶跃判断
        cross_idx = None
        for j in range(len(probs)):
            if probs[j] >= 0.95:
                cross_idx = j
                break
        is_step = False
        if cross_idx is not None and cross_idx > 0 and cross_idx < len(probs) - 1:
            # 阶跃：交叉点附近 p 从 <0.1 跳到 >0.9 在 3 个格点内
            for j in range(max(0, cross_idx - 3), cross_idx + 1):
                if probs[j] < 0.1:
                    is_step = True
                    break

        print(f"  结果 ({total_time:.0f}s):")
        print(f"    收敛点: r={conv_point:.0f}")
        print(f"    跳跃数: {len(jumps)}")
        if k_estimate:
            print(f"    k ~ {k_estimate:.8f}, r₀ ~ {r0_estimate:.0f}")
            print(f"    临界区宽度 (10%→90%): ~{2.2 / k_estimate:.0f} 资源")
        print(f"    阶跃特征: {'是' if is_step else '否'}")

        all_results[gdr_key] = {
            'description': description,
            'threshold': gdr_threshold,
            'convergence_point': float(conv_point),
            'convergence_prob': float(conv_prob),
            'convergence_success': conv_success,
            'r_grid': r_grid.tolist(),
            'probs': probs.tolist(),
            'jumps': jumps,
            'k_estimate': float(k_estimate) if k_estimate else None,
            'r0_estimate': float(r0_estimate) if r0_estimate else None,
            'is_step_function': is_step,
            'total_time_s': total_time,
        }

    # 跨 GDR 对比
    print("\n跨 GDR 对比:")
    gdr_keys = list(all_results.keys())
    for key in gdr_keys:
        r = all_results[key]
        k_str = f"k={r['k_estimate']:.8f}" if r['k_estimate'] else "k=N/A"
        step_str = "阶跃" if r['is_step_function'] else "连续"
        print(f"  {key}: 收敛={r['convergence_point']:.0f}, {k_str}, {step_str}")

    return all_results


# ═══════════════════════════════════════════════════════════════════════════════
# 实验 15: 简化配置——验证阶跃普适性
# ═══════════════════════════════════════════════════════════════════════════════

def experiment_15_simple_config(
    store, target_specs: Dict[str, int],
    n_runs: int = 30,
    num_simulations: int = 300,
    gdr_key: str = 'all_targets',
    max_workers: int = 4,
):
    """核验：简化目标配置（1-2 张卡）下二分搜索行为是否仍为阶跃。

    选择配置中的前 1-2 张目标卡，独立运行二分搜索，测量 std。
    与完整 6 卡配置对比，判断阶跃行为是否依赖于目标卡数量。
    """
    print("\n" + "=" * 70)
    print("实验 15: 简化配置——阶跃普适性验证")
    print("=" * 70)

    card_ids = list(target_specs.keys())
    results = {}

    for n_cards in [1, 2]:
        subset = {cid: target_specs[cid] for cid in card_ids[:n_cards]}
        label = f"{n_cards}卡"
        print(f"\n--- {label}: {subset} ---")

        runs = []
        start_time = time.time()
        for i in range(n_runs):
            if i % 10 == 0 and i > 0:
                elapsed = time.time() - start_time
                eta = (elapsed / i) * (n_runs - i)
                print(f"  进度: {i}/{n_runs}, 已耗时 {elapsed:.0f}s, ETA {eta:.0f}s")

            run = run_single_binary_search(
                store, subset,
                success_threshold=0.95,
                gdr_key=gdr_key,
                num_simulations=num_simulations,
                max_workers=max_workers,
                seed_offset=i * 1000 + n_cards * 10000,
            )
            runs.append(run)

        total_time = time.time() - start_time
        estimates = np.array([r.estimate for r in runs])
        mean_est = estimates.mean()
        std_est = estimates.std()
        n_success = sum(1 for r in runs if r.success)

        print(f"  {label} 结果 ({total_time:.0f}s):")
        print(f"    估计均值: {mean_est:.0f}")
        print(f"    标准差: {std_est:.0f}")
        print(f"    成功率: {n_success}/{n_runs}")
        print(f"    收敛值列表: {sorted(set(estimates.astype(int)))}")
        if std_est == 0:
            print(f"    → 阶跃函数（std=0）")
        else:
            print(f"    → 非阶跃（std={std_est:.0f}, CV={std_est/mean_est:.2%}）")

        results[label] = {
            'n_cards': n_cards,
            'subset': subset,
            'mean': float(mean_est),
            'std': float(std_est),
            'cv': float(std_est / mean_est) if mean_est > 0 else None,
            'n_success': n_success,
            'success_rate': n_success / n_runs,
            'unique_estimates': sorted(set(int(e) for e in estimates)),
            'total_time_s': total_time,
        }

    # 与完整配置对比
    print("\n与完整配置对比 (实验 9 quick: 6卡, std=0):")
    for label, r in results.items():
        print(f"  {label}: std={r['std']:.0f}, 成功率={r['success_rate']:.1%}")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='P26 集成测试——实际抽卡模拟器实验',
    )
    parser.add_argument(
        '--exp', type=str, default='9,11,14',
        help='要运行的实验编号（逗号分隔），默认: 9,11,14',
    )
    parser.add_argument(
        '--n-runs', type=int, default=50,
        help='实验 9 的独立搜索次数（默认 50，全量 200 需 ~2h）',
    )
    parser.add_argument(
        '--n-sims', type=int, default=500,
        help='每次评估的模拟次数（默认 500）',
    )
    parser.add_argument(
        '--n-grid', type=int, default=40,
        help='实验 11/14 资源网格点数（默认 40）',
    )
    parser.add_argument(
        '--r-max', type=float, default=200000.0,
        help='实验 11/14 资源扫描上限（默认 200000）',
    )
    parser.add_argument(
        '--gdr', type=str, default='all_targets',
        help='GDR 键名（默认: all_targets）',
    )
    parser.add_argument(
        '--workers', '-w', type=int, default=4,
        help='并行工作进程数（默认 4）',
    )
    parser.add_argument(
        '--quick', action='store_true',
        help='快速模式：n-runs=20, n-sims=200, n-grid=20',
    )
    parser.add_argument(
        '--output', type=str, default=None,
        help='结果输出 JSON 文件路径',
    )

    args = parser.parse_args()

    if args.quick:
        args.n_runs = 20
        args.n_sims = 200
        args.n_grid = 20
        args.r_max = 150000.0
        print("[快速模式] 降低参数以减少耗时")

    # 加载配置
    print("加载配置文件...")
    try:
        store = load_config()
        print(f"  加载成功: {len(store.pools) if hasattr(store, 'pools') else '?'} 个池子")
    except Exception as e:
        print(f"  加载失败: {e}")
        print("  请确认 gacha_simulator/config/ 目录存在且格式正确")
        sys.exit(1)

    # 加载目标卡
    target_specs = load_default_targets(store)
    print(f"  目标卡: {target_specs}")

    # 解析要运行的实验
    exp_list = [int(x.strip()) for x in args.exp.split(',')]
    all_results = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'params': {
            'n_runs': args.n_runs,
            'n_sims': args.n_sims,
            'n_grid': args.n_grid,
            'gdr': args.gdr,
            'workers': args.workers,
            'target_specs': target_specs,
        },
    }

    total_start = time.time()

    for exp_num in exp_list:
        if exp_num == 9:
            all_results['exp9'] = experiment_9_real_config_baseline(
                store, target_specs,
                n_runs=args.n_runs,
                num_simulations=args.n_sims,
                gdr_key=args.gdr,
                max_workers=args.workers,
            )
        elif exp_num == 11:
            all_results['exp11'] = experiment_11_jump_magnitude_measurement(
                store, target_specs,
                gdr_key=args.gdr,
                num_simulations=args.n_sims,
                max_workers=args.workers,
                n_points=args.n_grid,
            )
        elif exp_num == 12:
            all_results['exp12'] = experiment_12_path_divergence(
                store, target_specs,
                num_simulations=args.n_sims,
                max_workers=args.workers,
            )
        elif exp_num == 14:
            all_results['exp14'] = experiment_14_multi_gdr_comparison(
                store, target_specs,
                num_simulations=args.n_sims,
                max_workers=args.workers,
                r_max=args.r_max,
                n_points=args.n_grid,
            )
        elif exp_num == 15:
            all_results['exp15'] = experiment_15_simple_config(
                store, target_specs,
                n_runs=args.n_runs,
                num_simulations=args.n_sims,
                gdr_key=args.gdr,
                max_workers=args.workers,
            )
        else:
            print(f"[跳过] 未知实验编号: {exp_num}")

    total_time = time.time() - total_start
    all_results['total_time_s'] = total_time

    print(f"\n{'=' * 70}")
    print(f"全部实验完成。总耗时: {total_time:.0f}s = {total_time/60:.1f}min")

    # 保存结果
    if args.output:
        output_path = args.output
    else:
        output_dir = os.path.join(PROJECT_ROOT, 'output')
        os.makedirs(output_dir, exist_ok=True)
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        output_path = os.path.join(output_dir, f'p26_integration_{timestamp}.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
    print(f"结果已保存到: {output_path}")

    return all_results


if __name__ == '__main__':
    main()
