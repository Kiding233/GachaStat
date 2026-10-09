# -*- coding: utf-8 -*-
"""示意：脆弱性分析三行子图 与 敏感性分析（拟）的语法对照。
纯示意数据，不来自真实模拟。
"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from gacha_simulator.visualization import configure_chinese_font
configure_chinese_font()

rng = np.random.default_rng(7)

fig = plt.figure(figsize=(15.5, 9.2))
gs = GridSpec(3, 2, height_ratios=[0.26, 0.47, 0.27],
              hspace=0.120, wspace=0.16,
              left=0.062, right=0.985, top=0.875, bottom=0.145)

fig.suptitle('图：脆弱性三行子图 与 敏感性分析的语法对照（示意数据）',
             fontsize=14, y=0.972)
fig.text(0.27, 0.938, '脆弱性分析（现状，core/vulnerability.py::plot_vulnerability）',
         ha='center', fontsize=11.5, color='#1f4e79')
fig.text(0.755, 0.938, '敏感性分析（拟）—— 同一套图形语法，x 轴语义不同',
         ha='center', fontsize=11.5, color='#7d3c00')

C_LINE, C_BAND, C_THR, C_DOM, C_CP = '#1f77b4', '#9ecae1', '#d62728', '#2ca02c', '#8c564b'

# ══════════════════════ 左列：脆弱性分析 ══════════════════════
res = rng.normal(9000, 2600, 4000).clip(500, 20000)

ax1 = fig.add_subplot(gs[0, 0])
ax1.hist(res, bins=40, color=C_LINE, alpha=0.85)
ax1.axvline(res.mean(), ls='--', lw=1.2, color=C_THR, alpha=0.6)
ax1.set_ylabel('频次', fontsize=9)
ax1.tick_params(labelbottom=False, labelsize=8)
ax1.set_title('① 等距直方图：样本在 x 轴上的支撑', fontsize=9.5, loc='left', color='#333')

# 行 2：PAVA 台阶 + p̂ 散点 + α 线 + 脆弱区间 + 变更点 CI
ax2 = fig.add_subplot(gs[1, 0])
xe = np.linspace(500, 20000, 26)
xc = (xe[:-1] + xe[1:]) / 2
p_true = 1.0 / (1.0 + np.exp((xc - 8000) / 1600))
Nj = np.maximum((np.exp(-((xc - 9000) / 4000) ** 2) * 220).astype(int), 6)
phat = np.clip(p_true + rng.normal(0, 0.035, len(xc)), 0, 1)
# 保序（递减）
blocks, cur, out = [], [0], np.zeros(len(phat))
for i in range(1, len(phat) + 1):
    if i == len(phat) or phat[i] > phat[cur[-1]]:
        w = Nj[cur].sum()
        v = (phat[cur] * Nj[cur]).sum() / w
        for j in cur:
            out[j] = v
        cur = [i] if i < len(phat) else []
    else:
        cur.append(i)
ALPHA = 0.5
x_star, x_lo, x_hi = 8300, 7100, 9500
ax2.axvspan(500, x_star, color=C_DOM, alpha=0.10)
ax2.axvspan(x_lo, x_hi, color=C_CP, alpha=0.16)
ax2.axhline(ALPHA, ls=':', lw=1.4, color=C_THR)
ax2.scatter(xc, phat, s=np.maximum(4, 55 * Nj / Nj.max()), color='gray', alpha=0.55, zorder=2,
            label='$\\hat{p}_j$ 散点（大小 ∝ $N_j$）')
ax2.step(xe[:-1], out, where='post', color='darkred', lw=2.2, zorder=3, label='PAVA 保序台阶 $\\tilde{\\theta}$')
ax2.axvline(x_star, color=C_CP, lw=1.6)
ax2.plot([x_star], [ALPHA], marker='v', ms=9, color=C_CP, zorder=5)
ax2.set_ylabel('失败率 $\\hat{p}$', fontsize=9)
ax2.tick_params(labelbottom=False, labelsize=8)
ax2.set_ylim(-0.03, 1.03)
ax2.legend(fontsize=7.6, loc='upper right', framealpha=0.9)
ax2.set_title('② 推断主图：阈值线 α + 脆弱区间着色 + 变更点 $\\hat{x}^*$ 及其 CI 带',
              fontsize=9.5, loc='left', color='#333')
ax2.annotate('$\\alpha$=0.5 阈值', xy=(19500, ALPHA), xytext=(19500, ALPHA + 0.10),
             fontsize=7.6, color=C_THR, ha='right')
ax2.annotate('变更点 $\\hat{x}^*$\\nCI 带 [$\\hat{x}^*_{lo}$, $\\hat{x}^*_{hi}$]',
             xy=(x_star, 0.62), xytext=(12500, 0.72), fontsize=7.8, color=C_CP,
             arrowprops=dict(arrowstyle='->', color=C_CP, lw=0.9))

ax3 = fig.add_subplot(gs[2, 0])
ax3.bar(xc, Nj, width=np.diff(xe) * 0.86,
        color=[C_DOM if v > ALPHA else '#c9c9c9' for v in out], alpha=0.85)
ax3.set_ylabel('$N_j$', fontsize=9)
ax3.set_xlabel('资源剩余（x 轴：样本内变量，每条模拟结果自带一个值）', fontsize=9)
ax3.tick_params(labelsize=8)
ax3.set_title('③ 每箱样本量：每个 x 点的估计有多可靠', fontsize=9.5, loc='left', color='#333')

# ══════════════════════ 右列：敏感性分析 ══════════════════════
theta = np.linspace(0.80, 0.99, 13)          # 扫描点
resp_true = 1.06 - 0.30 / (1 + np.exp(-(theta - 0.905) / 0.028))
se = 0.012 + 0.030 * np.exp(-((theta - 0.90) / 0.06) ** 2)
resp = resp_true + rng.normal(0, se * 0.5, len(theta))
lo, hi = resp - 1.96 * se, resp + 1.96 * se
TAU = 0.85
flip, flo, fhi = 0.912, 0.892, 0.935

ax4 = fig.add_subplot(gs[0, 1])
ax4.plot(theta, np.zeros_like(theta), '|', ms=14, color='#555', mew=1.6)
ax4.set_ylim(-1.6, 1.0)
ax4.set_yticks([])
ax4.tick_params(labelbottom=False, labelsize=8)
ax4.set_title('① 扫描点在 θ 轴上的位置与间距（第一版均匀采样，此行无信息量）',
              fontsize=9.5, loc='left', color='#333')
ax4.text(0.895, -0.95, 'x 轴 = 被扫描参数 θ（数据集间的标签）\n每个刻度 = 一个独立的数据集',
         fontsize=8.2, color='#555', ha='center')

ax5 = fig.add_subplot(gs[1, 1])
ax5.axvspan(theta[0], flip, color=C_DOM, alpha=0.10)
ax5.axvspan(flo, fhi, color=C_CP, alpha=0.18)
ax5.axhline(TAU, ls=':', lw=1.4, color=C_THR)
ax5.fill_between(theta, lo, hi, color=C_BAND, alpha=0.55,
                 label='各扫描点的 95% CI（误差带）')
ax5.plot(theta, resp, '-o', color=C_LINE, lw=2.0, ms=5, zorder=4, label='响应曲线 $\\hat{s}(θ)$')
ax5.axvline(flip, color=C_CP, lw=1.6)
ax5.plot([flip], [TAU], marker='v', ms=9, color=C_CP, zorder=5)
ax5.set_ylabel('$\\hat{s}(θ)$', fontsize=9)
ax5.tick_params(labelbottom=False, labelsize=8)
ax5.set_ylim(0.72, 1.10)
ax5.legend(fontsize=7.4, loc='lower right', framealpha=0.92)
ax5.set_title('② 推断主图：同样的语法 —— 阈值线 τ + 结论成立域着色 + 翻转区间 [$θ^*_{lo}$, $θ^*_{hi}$]',
              fontsize=9.5, loc='left', color='#333')
ax5.annotate('结论成立域\n$\\hat{s}(θ) \\geq τ$', xy=(0.845, 1.02), fontsize=7.8, color=C_DOM, ha='center')
ax5.annotate('$τ$=0.85 判据线', xy=(0.985, TAU), xytext=(0.985, TAU - 0.075),
             fontsize=7.6, color=C_THR, ha='right')
ax5.annotate('翻转区间 [$θ^*_{lo}$, $θ^*_{hi}$]\n带内结论「说不准」',
             xy=(flip, 0.79), xytext=(0.833, 0.745), fontsize=7.8, color=C_CP,
             arrowprops=dict(arrowstyle='->', color=C_CP, lw=0.9))

ax6 = fig.add_subplot(gs[2, 1])
ax6.bar(theta, 1.96 * se, width=0.010, color='#c9c9c9', alpha=0.9)
ax6.set_ylabel('CI 半宽', fontsize=9)
ax6.set_xlabel('被扫描参数 θ（x 轴：数据集间标签，每个点一个独立数据集）', fontsize=9)
ax6.tick_params(labelsize=8)
ax6.set_title('③ 每点 CI 宽度：哪一段 θ 上的估计最不稳（替代脆弱性的 $N_j$）',
              fontsize=9.5, loc='left', color='#333')

fig.text(0.265, 0.055,
         '行的语义对应：① 支撑情况 → ② 推断主图 → ③ 每点可靠性',
         ha='center', fontsize=9.5, color='#1f4e79')
fig.text(0.755, 0.055,
         '第②行是主体，语法完全同构；①③ 的对应是「语义」层面的，不是逐元素照搬',
         ha='center', fontsize=9.5, color='#7d3c00')

out = 'docs/01-活跃/panels/敏感性分析/三行子图对照示意.png'
fig.savefig(out, dpi=125, facecolor='white')
print('已保存:', out)
