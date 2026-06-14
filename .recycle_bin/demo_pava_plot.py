#!/usr/bin/env python3
"""PAVA 脆弱区间可视化演示。

数据生成：模拟 gacha 产出——离散格点 + 偏态分布 + 真实 DGP。
变更点 CI：在原始箱边界上进行非参数 bootstrap（不对齐问题修复）。
"""
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy.stats import norm

# ============================================================
# 1. 生成模拟数据（模仿 gacha 产出特征）
# ============================================================
np.random.seed(42)
n = 800
cost = 160  # 单抽消耗

# 资源分布：偏态的——大多数模拟在低资源端集中，高资源端稀疏
# 用 Gamma 分布模拟剩余资源（shape=2, scale=1500 → 正偏态）
r_raw = np.random.gamma(shape=2.0, scale=1500, size=n)
r_raw = np.clip(r_raw, 50, 10000)

# 离散化为 cost 的倍数（gacha 真实特征）
r = (r_raw / cost).round() * cost
r = np.clip(r, cost, 10000)

# 真实 DGP：失败概率随资源递减（logistic）
theta_true = 1.0 / (1.0 + np.exp((r - 2500) / 600))
y = (np.random.random(n) < theta_true).astype(int)

print(f"资源分布: min={r.min():.0f}, median={np.median(r):.0f}, max={r.max():.0f}")
print(f"不同资源值数: {len(np.unique(r))} (理论最大: {int(r.max()/cost)})")
print(f"每格点平均观测: {n / len(np.unique(r)):.1f}")

# ============================================================
# 2. binsglm 分位数分箱
# ============================================================
from binsreg import binsglm
import warnings
warnings.filterwarnings('ignore')

result = binsglm(y, r, dist="Binomial", noplot=True, ci=False, cb=False)
dp = result.data_plot[0]
dots = dp.dots
data_bin = dp.data_bin

J = len(dots)
p_hat = dots["fit"].values.astype(float)
N_j = dots["n"].values.astype(int)
x_center = dots["x"].values.astype(float)
x_left = data_bin["left_endpoint"].values.astype(float)
x_right = data_bin["right.endpoint"].values.astype(float)
K_j = (p_hat * N_j).round().astype(int)

# ============================================================
# 3. PAVA
# ============================================================
def pava(p, w):
    p = np.asarray(p, dtype=float)
    w = np.asarray(w, dtype=float)
    blocks = [[i] for i in range(len(p))]
    current_p = p.copy()
    current_w = w.copy()
    changed = True
    while changed:
        changed = False
        i = 1
        while i < len(current_p):
            if current_p[i - 1] < current_p[i]:
                K_pool = current_p[i - 1] * current_w[i - 1] + current_p[i] * current_w[i]
                w_pool = current_w[i - 1] + current_w[i]
                p_pool = K_pool / w_pool
                current_p[i - 1] = p_pool
                current_w[i - 1] = w_pool
                blocks[i - 1].extend(blocks[i])
                current_p = np.delete(current_p, i)
                current_w = np.delete(current_w, i)
                del blocks[i]
                changed = True
                break
            i += 1
    return current_p, current_w, blocks


theta_tilde, w_tilde, blocks = pava(p_hat, N_j)
theta_tilde_per_bin = np.zeros(J)
for b_idx, blk in enumerate(blocks):
    for j in blk:
        theta_tilde_per_bin[j] = theta_tilde[b_idx]

# ============================================================
# 4. 变更点 ĵ* 及 Bootstrap CI（在固定箱边界下）
# ============================================================
alpha = 0.5

# ĵ* = 最后一个保序估计 > α 的箱索引
j_star = max((j for j in range(J) if theta_tilde_per_bin[j] > alpha), default=None)

# Bootstrap：重采样原始 (r_i, y_i) 对，在固定箱边界上重新计数 + PAVA
# 箱边界不变 → 索引可比
n_boot = 500
j_star_boot = []
rng = np.random.default_rng(12345)

for b in range(n_boot):
    idx = rng.choice(n, size=n, replace=True)
    r_b, y_b = r[idx], y[idx]
    # 在固定箱边界上手工分箱
    p_b = np.zeros(J)
    for j in range(J):
        mask = (r_b >= x_left[j]) & (r_b < x_right[j])
        if j == J - 1:
            mask = (r_b >= x_left[j])
        n_j = mask.sum()
        k_j = y_b[mask].sum()
        p_b[j] = k_j / n_j if n_j > 0 else 0.0
    # PAVA
    theta_t_b, _, blocks_b = pava(p_b, N_j)
    theta_t_per_bin_b = np.zeros(J)
    for bi, blk in enumerate(blocks_b):
        for jj in blk:
            theta_t_per_bin_b[jj] = theta_t_b[bi]
    js_b = max((jj for jj in range(J) if theta_t_per_bin_b[jj] > alpha), default=None)
    if js_b is not None:
        j_star_boot.append(js_b)

if j_star_boot:
    j_star_lo = int(np.percentile(j_star_boot, 2.5))
    j_star_hi = int(np.percentile(j_star_boot, 97.5))
    x_star_lo = x_left[max(0, j_star_lo)]
    x_star_hi = x_right[min(J - 1, j_star_hi)]
    x_star_pt = x_right[j_star] if j_star is not None else 0
else:
    j_star_lo = j_star_hi = 0
    x_star_lo = x_star_hi = 0
    x_star_pt = 0

# ============================================================
# 5. 画图
# ============================================================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), height_ratios=[2, 1])

# ----- 上图：PAVA 台阶 + 原始比例 + 变更点置信区间 -----
# PAVA 台阶
for b_idx, blk in enumerate(blocks):
    left = x_left[blk[0]]
    right = x_right[blk[-1]]
    ax1.hlines(theta_tilde[b_idx], left, right,
               colors="#e74c3c" if theta_tilde[b_idx] > alpha else "#2c3e50",
               linewidths=2.5, zorder=3)

# 块间竖线
for b_idx in range(len(blocks) - 1):
    x_sep = x_right[blocks[b_idx][-1]]
    ax1.axvline(x_sep, color="#bdc3c7", linewidth=0.8, linestyle="--", alpha=0.5)

# 原始 p̂_j 散点（灰点）
for j in range(J):
    ax1.scatter(x_center[j], p_hat[j], s=np.clip(N_j[j] * 0.6, 10, 120),
                c="#7f8c8d", edgecolors="white", linewidth=0.3, zorder=4, alpha=0.5)

# α 参考线
ax1.axhline(alpha, color="#e74c3c", linewidth=1.2, linestyle="--", alpha=0.7)

# 脆弱区间着色（保守端：从 0 到 ĵ* CI 上界）
if j_star is not None:
    ax1.axvspan(0, x_star_hi, alpha=0.08, color="#e74c3c", zorder=1)
    # ĵ* 点估计
    ax1.axvline(x_star_pt, color="#e74c3c", linewidth=1.0, linestyle=":", alpha=0.6)

# 变更点置信区间：在图底部 α 线附近画红色条带
if j_star_boot and j_star_lo != j_star_hi:
    ax1.axvspan(x_star_lo, x_star_hi, ymin=0.015, ymax=0.055,
                facecolor="#c0392b", alpha=0.7, zorder=5, clip_on=False)
    ax1.annotate(
        f"ĵ* 95% CI\n[{x_star_lo:.0f}, {x_star_hi:.0f}]",
        xy=(x_star_pt, 0.0), xytext=(x_star_pt, 0.16),
        fontsize=9, fontweight="bold", color="#c0392b", ha="center",
        arrowprops=dict(arrowstyle="->", color="#c0392b", lw=1.2),
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#e74c3c", alpha=0.9),
    )

ax1.set_xlim(0, max(x_right) * 1.02)
ax1.set_ylim(-0.05, 1.1)
ax1.set_ylabel("P(失败 | 资源 ∈ 箱)", fontsize=13)
ax1.set_title("脆弱性分析 — PAVA 保序估计 + 变更点置信区间 (γ=0.05)", fontsize=15, fontweight="bold")
ax1.grid(axis="y", alpha=0.3)

legend_elements = [
    mpatches.Patch(facecolor="#e74c3c", alpha=0.08, label=f"脆弱区间 (保守端)"),
    mpatches.Patch(facecolor="#c0392b", alpha=0.7, label=f"ĵ* 95% CI"),
    plt.Line2D([0], [0], color="#e74c3c", linewidth=2.5, label="PAVA 保序 (脆弱)"),
    plt.Line2D([0], [0], color="#2c3e50", linewidth=2.5, label="PAVA 保序 (安全)"),
    plt.Line2D([0], [0], marker="o", color="#7f8c8d", markersize=6, markeredgecolor="white",
               linewidth=0, label="原始箱比例 (大小 ∝ N_j)"),
    plt.Line2D([0], [0], color="#e74c3c", linewidth=1.0, linestyle=":", label=f"ĵ* 点估计"),
]
ax1.legend(handles=legend_elements, loc="upper right", fontsize=9, framealpha=0.9)

# ----- 下图：样本量分布（无缝柱状图）-----
bar_colors = ["#e74c3c" if v > alpha else "#2c3e50" for v in theta_tilde_per_bin]
ax2.bar(x_left, N_j, width=x_right - x_left, align="edge",
        color=bar_colors, alpha=0.7, edgecolor="white", linewidth=0.3)
ax2.set_xlabel("资源剩余量 (draw_resource)", fontsize=13)
ax2.set_ylabel("每箱模拟次数 N_j", fontsize=13)
ax2.set_title("各箱样本量分布（分位数分箱 —— 每箱 ≈ n/J 次观测，箱宽自适应数据密度）", fontsize=13)
ax2.set_xlim(0, max(x_right) * 1.02)
ax2.grid(axis="y", alpha=0.3)

# 标注分箱信息
ax2.text(0.98, 0.95,
         f"分箱数: J={J}\nPAVA块数: L={len(blocks)}\n"
         f"ĵ* 点估计: 箱{j_star+1}\nĵ* 95% CI: 箱{j_star_lo+1}–{j_star_hi+1}\n"
         f"最小N_j: {min(N_j)}, 最大N_j: {max(N_j)}",
         transform=ax2.transAxes, fontsize=9, verticalalignment="top",
         horizontalalignment="right", fontfamily="monospace",
         bbox=dict(boxstyle="round,pad=0.5", facecolor="#f9f9f9", edgecolor="#ddd"))

plt.tight_layout()
plt.savefig("pava_demo.png", dpi=150, bbox_inches="tight")
print(f"\n已保存 pava_demo.png")
print(f"ĵ* 点估计: 箱{j_star+1} (右界={x_star_pt:.0f})")
print(f"ĵ* 95% CI: 箱{j_star_lo+1}–{j_star_hi+1} (资源 [{x_star_lo:.0f}, {x_star_hi:.0f}])")
print(f"脆弱区间（保守端）: [0, {x_star_hi:.0f}]")
for b_idx, blk in enumerate(blocks):
    vuln = "◉" if theta_tilde[b_idx] > alpha else "○"
    print(f"  {vuln} 块{b_idx+1}: 箱{blk[0]+1}–{blk[-1]+1}, "
          f"θ̃={theta_tilde[b_idx]:.3f}, N_total={sum(N_j[j] for j in blk)}, "
          f"范围=[{x_left[blk[0]]:.0f}, {x_right[blk[-1]]:.0f}]")
