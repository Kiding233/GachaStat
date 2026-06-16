#!/usr/bin/env python3
"""验证混合方案：binsglm 分箱 + Wilson CI + Sidak 校正。

P51 T2 Step 1 最终验证——CCFF IMSE 最优分箱 + 手工精确推断。
"""
import numpy as np
from binsreg import binsglm
import warnings
warnings.filterwarnings('ignore')


def wilson_ci(n_success, n_total, level=0.95):
    """Wilson score interval for binomial proportion.

    Returns (lower, upper). Does NOT collapse to 0 at p=0.
    """
    import scipy.stats as st
    if n_total == 0:
        return 0.0, 1.0
    p = n_success / n_total
    z = st.norm.ppf(1 - (1 - level) / 2)
    denom = 1 + z**2 / n_total
    center = (p + z**2 / (2 * n_total)) / denom
    margin = z * np.sqrt(p * (1 - p) / n_total + z**2 / (4 * n_total**2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def detect_vulnerability_binsglm(x, y, alpha=0.5, fwer=0.05):
    """用 binsglm 分箱 + Wilson CI 检测脆弱区间。

    Returns:
        vulnerability_intervals: [(lower_x, upper_x), ...]
        dots: DataFrame with bin info
        ci_df: DataFrame with CI per bin
    """
    # Step 1: binsglm 获取 IMSE 最优分箱 + 箱级比例
    result = binsglm(y, x, dist='Binomial', noplot=True, ci=False, cb=False)
    dp = result.data_plot[0]
    dots = dp.dots
    data_bin = dp.data_bin

    J = len(dots)
    sidak_level = (1 - fwer) ** (1 / J)  # Sidak 校正

    ci_data = []
    vuln_intervals = []

    for i in range(J):
        n_j = int(dots['n'].values[i])
        p_j = dots['fit'].values[i]
        n_success = int(round(p_j * n_j))

        ci_l, ci_u = wilson_ci(n_success, n_j, level=sidak_level)
        bin_left = data_bin['left_endpoint'].values[i]
        bin_right = data_bin['right.endpoint'].values[i]
        bin_center = dots['x'].values[i]

        ci_data.append({
            'bin_center': bin_center,
            'bin_left': bin_left,
            'bin_right': bin_right,
            'p_hat': p_j,
            'n': n_j,
            'ci_l': ci_l,
            'ci_u': ci_u,
            'vulnerable': ci_l > alpha,
        })

    # 合并连续脆弱箱
    in_vuln = False
    current_start = None
    for ci in ci_data:
        if ci['vulnerable'] and not in_vuln:
            in_vuln = True
            current_start = ci['bin_left']
        elif not ci['vulnerable'] and in_vuln:
            in_vuln = False
            vuln_intervals.append((current_start, ci['bin_left']))
    if in_vuln:
        vuln_intervals.append((current_start, ci_data[-1]['bin_right']))

    return vuln_intervals, dots, ci_data


# ============================================================
# 场景1: 有明显脆弱区间（低资源时失败概率高）
# ============================================================
print("="*60)
print("场景1: 明显脆弱区间 (P(fail) 在低资源时 > 0.5)")
np.random.seed(42)
n = 500
x1 = np.random.uniform(100, 5000, n)
# 低资源 → 高失败概率
prob1 = 1.0 / (1.0 + np.exp((x1 - 1500) / 400))
y1 = (np.random.random(n) < prob1).astype(float)
print(f"实际 P(fail) 在 r=100: {1/(1+np.exp((100-1500)/400)):.3f}")
print(f"实际 P(fail) 在 r=2000: {1/(1+np.exp((2000-1500)/400)):.3f}")

vuln1, dots1, ci1 = detect_vulnerability_binsglm(x1, y1, alpha=0.5, fwer=0.05)
print(f"箱数: {len(ci1)}")
print(f"脆弱区间: {vuln1}")
for d in ci1[:5]:
    print(f"  x={d['bin_center']:.0f} p={d['p_hat']:.3f} ci=[{d['ci_l']:.3f}, {d['ci_u']:.3f}] n={d['n']} vuln={d['vulnerable']}")
print("...")
print()


# ============================================================
# 场景2: 无脆弱区间（大部分样本成功）
# ============================================================
print("="*60)
print("场景2: 无脆弱区间")
np.random.seed(99)
x2 = np.random.uniform(100, 5000, n)
prob2 = 1.0 / (1.0 + np.exp((x2 - 500) / 200))
y2 = (np.random.random(n) < prob2).astype(float)

vuln2, dots2, ci2 = detect_vulnerability_binsglm(x2, y2, alpha=0.5, fwer=0.05)
print(f"箱数: {len(ci2)}")
print(f"脆弱区间: {vuln2} (应为空)")
for d in ci2[:5]:
    print(f"  x={d['bin_center']:.0f} p={d['p_hat']:.3f} ci=[{d['ci_l']:.3f}, {d['ci_u']:.3f}] n={d['n']} vuln={d['vulnerable']}")
print()


# ============================================================
# 场景3: 固定箱边界（多池山脊图对齐）——手工分箱 + Wilson CI
# ============================================================
print("="*60)
print("场景3: 固定箱边界——两池复用相同边界（手工分箱+Wilson CI）")
np.random.seed(111)
x3a = np.random.uniform(100, 5000, 300)
prob3a = 1.0 / (1.0 + np.exp((x3a - 1500) / 300))
y3a = (np.random.random(300) < prob3a).astype(float)

x3b = np.random.uniform(200, 4800, 250)
prob3b = 1.0 / (1.0 + np.exp((x3b - 2000) / 500))
y3b = (np.random.random(250) < prob3b).astype(float)

# Step 1: 用合并数据确定 IMSE 最优公共箱边界
x_all = np.concatenate([x3a, x3b])
y_all = np.concatenate([y3a, y3b])
r_all = binsglm(y_all, x_all, dist='Binomial', noplot=True, ci=False, cb=False)
dp_all = r_all.data_plot[0]
bin_edges = dp_all.data_bin[['left_endpoint', 'right.endpoint']].values
knots = [float(bin_edges[0, 0])] + [float(b) for b in bin_edges[:, 1]]
J = len(knots) - 1
print(f"合并数据 → IMSE 最优 J={J}")

# Step 2: 手工分箱 + Wilson CI（两池共用边界）
def manual_bin_wilson(x, y, knots, sidak_level):
    """手工分箱 + Wilson CI"""
    results = []
    for j in range(len(knots) - 1):
        left, right = knots[j], knots[j+1]
        mask = (x >= left) & (x < right)
        if j == len(knots) - 2:  # 最后一箱包含右边界
            mask = (x >= left) & (x <= right)
        n_j = mask.sum()
        n_success = int(y[mask].sum()) if n_j > 0 else 0
        p_j = n_success / n_j if n_j > 0 else 0.0
        ci_l, ci_u = wilson_ci(n_success, n_j, level=sidak_level)
        center = (left + right) / 2
        results.append({
            'bin_center': center, 'bin_left': left, 'bin_right': right,
            'p_hat': p_j, 'n': n_j, 'ci_l': ci_l, 'ci_u': ci_u,
        })
    return results

sidak_level = (1 - 0.05) ** (1 / J)
ci3a = manual_bin_wilson(x3a, y3a, knots, sidak_level)
ci3b = manual_bin_wilson(x3b, y3b, knots, sidak_level)

# 验证边界一致
print(f"池A 前3边界: [{ci3a[0]['bin_left']:.1f}, {ci3a[0]['bin_right']:.1f}], "
      f"[{ci3a[1]['bin_left']:.1f}, {ci3a[1]['bin_right']:.1f}]")
print(f"池B 前3边界: [{ci3b[0]['bin_left']:.1f}, {ci3b[0]['bin_right']:.1f}], "
      f"[{ci3b[1]['bin_left']:.1f}, {ci3b[1]['bin_right']:.1f}]")

# 数值验证边界一致
for a, b in zip(ci3a, ci3b):
    assert abs(a['bin_left'] - b['bin_left']) < 1e-10
    assert abs(a['bin_right'] - b['bin_right']) < 1e-10
print("✓ 固定箱边界复用成功——两池完全对齐")
print(f"  池A 脆弱箱: {sum(1 for c in ci3a if c['ci_l'] > 0.5)}/{J}")
print(f"  池B 脆弱箱: {sum(1 for c in ci3b if c['ci_l'] > 0.5)}/{J}")
print()


# ============================================================
# 场景4: 覆盖概率验证
# ============================================================
print("="*60)
print("场景4: Wilson CI 覆盖概率验证")
n_sims = 200
np.random.seed(777)
covered = 0
total = 0
fwer = 0.05

for sim in range(n_sims):
    seed = 3000 + sim
    np.random.seed(seed)
    x_s = np.random.uniform(100, 5000, 200)
    prob_s = 1.0 / (1.0 + np.exp((x_s - 2000) / 500))
    y_s = (np.random.random(200) < prob_s).astype(float)

    vuln, _, ci_data = detect_vulnerability_binsglm(x_s, y_s, alpha=0.5, fwer=fwer)

    for ci in ci_data:
        # 真实箱级失败概率（蒙特卡洛近似）
        bin_mask = (x_s >= ci['bin_left']) & (x_s < ci['bin_right'])
        if bin_mask.sum() > 0:
            true_p = prob_s[bin_mask].mean()
            if ci['ci_l'] <= true_p <= ci['ci_u']:
                covered += 1
            total += 1

print(f"单个 CI 覆盖: {covered}/{total} = {covered/total:.3f} (期望 ≥ 1-{fwer:.3f})")

# 族系错误率：任意 CI 未覆盖
fwer_count = 0
for sim in range(n_sims):
    seed = 3000 + sim
    np.random.seed(seed)
    x_s = np.random.uniform(100, 5000, 200)
    prob_s = 1.0 / (1.0 + np.exp((x_s - 2000) / 500))
    y_s = (np.random.random(200) < prob_s).astype(float)

    _, _, ci_data = detect_vulnerability_binsglm(x_s, y_s, alpha=0.5, fwer=fwer)

    all_covered = True
    for ci in ci_data:
        bin_mask = (x_s >= ci['bin_left']) & (x_s < ci['bin_right'])
        if bin_mask.sum() > 0:
            true_p = prob_s[bin_mask].mean()
            if not (ci['ci_l'] <= true_p <= ci['ci_u']):
                all_covered = False
                break

    if not all_covered:
        fwer_count += 1

print(f"族系错误率: {fwer_count}/{n_sims} = {fwer_count/n_sims:.3f} (期望 ≤ {fwer})")
print()

print("="*60)
print("验证完成")
