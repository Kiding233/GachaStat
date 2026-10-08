"""P88 差分布的 Omega 比率演示图。

画 D = B - A 的 Omega 曲线 `Ω(θ) = E[(D−θ)⁺] / E[(θ−D)⁺]`，用作 P88 计划
阶段 2 呈现层的形态参考。两个预置数据对：

  balanced  draw_target vs pool_quota —— 两策略在该配置下等价（E[D] = 0），
            Ω(0) = 1 恰落在盈亏平衡点，曲线形态标准，适合当读图示例。
  skewed    smart vs pity_reserve —— 策略权衡（保底预留牺牲达成率换资源剩余），
            D 的分布完全单边，Ω(0) 退化为 0 或无穷，展示偏移与退化两种形态。

读图：横轴 θ 是阈值，纵轴 Ω(θ) 是「超出 θ 的平均幅度 ÷ 低于 θ 的平均幅度」。
曲线与 Ω = 1 的交点 θ* 即盈亏平衡阈值（恒等于 E[D]，见 P88 §3.4）。

用法：
    python scripts/p88_omega_demo.py                  # 两张都画
    python scripts/p88_omega_demo.py --pair skewed    # 只画偏移版
    python scripts/p88_omega_demo.py -n 300 --seed 7

输出：output/p88_omega_demo.png（balanced）与 output/p88_omega_skewed.png（skewed）。
"""

import argparse
import math
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import matplotlib  # noqa: E402

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

from gacha_simulator.core.config_toml import load_toml  # noqa: E402
from gacha_simulator.core.gdr import compute_gdr_from_compact  # noqa: E402
from gacha_simulator.service.batch_simulator import (  # noqa: E402
    SimulationEnvBuilder, run_batch_parallel)
from gacha_simulator.visualization.font_config import configure_chinese_font  # noqa: E402

configure_chinese_font()

ZH = {
    'target_achievement': '目标达成率', 'resource_remaining': '资源剩余',
    'non_pity_draws': '非保底抽数', 'resource_consumed': '资源消耗',
    'resource_efficiency': '资源转化效率', 'pity_draws': '保底触发数',
    'total_card_value': '卡牌总价值', 'resource_per_card': '每目标卡资源',
    'weighted_satisfaction': '加权满意度',
}

PAIRS = {
    'balanced': dict(
        a='draw_target', b='pool_quota', out='p88_omega_demo.png',
        title='D = 指定池配额 − 目标池抽卡',
        keys=['target_achievement', 'non_pity_draws', 'resource_efficiency', 'pity_draws']),
    'skewed': dict(
        a='smart', b='pity_reserve', out='p88_omega_skewed.png',
        title='D = 保底预留 − 按需追卡（单边偏移）',
        keys=['target_achievement', 'resource_remaining', 'non_pity_draws', 'resource_consumed']),
}


def run_one(store, specs, strategy, n, seed):
    env = SimulationEnvBuilder.from_config_store(store)
    r = run_batch_parallel(
        env=env, target_specs=specs, initial_resources=env.initial_resources,
        num_simulations=n, max_workers=8, seed=seed, strategy_key=strategy)
    return r.results


def gdr_values(compacts, key, specs):
    out = []
    for c in compacts:
        v = compute_gdr_from_compact(c, target_specs=specs, gdr_key=key)
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            continue
        out.append(float(v))
    return np.array(out)


def diff_dist(a, b):
    """D = B − A 的经验分布：唯一值压缩 + 唯一值对枚举（P88 §3.1）。"""
    uA, cA = np.unique(a, return_counts=True)
    uB, cB = np.unique(b, return_counts=True)
    d = (uB[None, :] - uA[:, None]).ravel()
    w = (cB[None, :] * cA[:, None]).ravel()
    u, inv = np.unique(d, return_inverse=True)
    c = np.zeros(len(u))
    np.add.at(c, inv, w)
    return u, c / c.sum()


def omega_curve(u, p, thetas):
    out = np.empty(len(thetas))
    for i, t in enumerate(thetas):
        up = float(np.sum(p * np.maximum(u - t, 0.0)))
        dn = float(np.sum(p * np.maximum(t - u, 0.0)))
        out[i] = up / dn if dn > 0 else np.inf
    return out


def plot_pair(store, specs, cfg, n, seed):
    ca = run_one(store, specs, cfg['a'], n, seed)
    cb = run_one(store, specs, cfg['b'], n, seed)
    keys = []
    for key in cfg['keys']:
        a = gdr_values(ca, key, specs)
        b = gdr_values(cb, key, specs)
        if len(diff_dist(a, b)[0]) > 1:
            keys.append((key, a, b))
    keys = keys[:4]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9.5))
    for k, (key, a, b) in enumerate(keys):
        row, col = divmod(k, 2)
        ax = axes[row][col]
        u, p = diff_dist(a, b)
        lo, hi = float(u.min()), float(u.max())
        pad = (hi - lo) * 1e-6 if hi > lo else 1e-9
        ts = np.linspace(lo + pad, hi - pad, 500)
        om = omega_curve(u, p, ts)

        ax.plot(ts, om, color='#E45756', lw=2.4, label='Ω(θ)')
        ax.axhline(1.0, color='#333', lw=1.2, ls='--', label='Ω = 1（盈亏平衡）')
        ax.axvline(0, color='#888', lw=1.2, ls=':')
        fin = np.isfinite(om) & (om > 0)
        if fin.any():
            ax.set_yscale('log')
            ax.set_ylim(max(np.nanmin(om[fin]), 1e-3), min(np.nanmax(om[fin]), 1e5))
            idx = np.where(np.diff(np.sign(om - 1.0)) != 0)[0]
            if len(idx):
                tstar = ts[idx[0]]
                ax.plot([tstar], [1.0], 'o', color='#54A24B', ms=9, zorder=5)
                ax.annotate('θ* = %.4g' % tstar, xy=(tstar, 1.0), xytext=(0.06, 0.16),
                            textcoords='axes fraction', fontsize=11,
                            arrowprops=dict(arrowstyle='->', color='#54A24B'),
                            bbox=dict(fc='#eaf7ea', ec='#54A24B'))
        om0 = float(omega_curve(u, p, np.array([0.0]))[0])
        om0_s = '∞' if not np.isfinite(om0) else '%.3g' % om0
        ax.set_title(
            '%s　E[D]=%.4g　Ω(0)=%s\nP(D<0)=%.3f　P(D=0)=%.3f　P(D>0)=%.3f'
            % (ZH.get(key, key), float(np.sum(u * p)), om0_s,
               float(p[u < 0].sum()), float(p[u == 0].sum()), float(p[u > 0].sum())),
            fontsize=10.5)
        ax.set_xlabel('θ（阈值，单位同该 GDR）')
        ax.set_ylabel('Ω(θ)')
        ax.grid(alpha=0.3, which='both')
        ax.legend(fontsize=8.5, loc='upper right')

    fig.suptitle('%s 的 Omega 曲线（各 %d 次模拟，seed=%d）' % (cfg['title'], n, seed),
                 fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = _ROOT / 'output' / cfg['out']
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    print('saved:', out)


def main():
    ap = argparse.ArgumentParser(description='P88 Omega 比率演示图')
    ap.add_argument('--pair', choices=['balanced', 'skewed', 'both'], default='both')
    ap.add_argument('-n', '--num-simulations', type=int, default=200)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--config', default=str(_ROOT / 'gacha_simulator' / 'config' / 'config.toml'))
    args = ap.parse_args()

    store = load_toml(args.config)
    specs = {tc.card_id: getattr(tc, 'quantity', 1) for tc in store.target_cards}
    targets = list(PAIRS) if args.pair == 'both' else [args.pair]
    for name in targets:
        plot_pair(store, specs, PAIRS[name], args.num_simulations, args.seed)


if __name__ == '__main__':
    main()
