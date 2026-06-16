"""P45 校准实验 —— 验证 PySDTest test_sd_SR 在已知 ground truth 下的表现。

纯外部脚本，不 import 任何 gacha_simulator 模块，不修改任何项目代码。
"""

import sys
import numpy as np
import time
from pysdtest import test_sd_SR

# 强制无缓冲输出 —— 后台运行时确保实时可见
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

# ============================================================
# 配置
# ============================================================
N_SIZES = [100, 500, 2000]     # 样本量
N_REPS = 30                      # 每样本量重复次数 (快速验证, 全量100后补)
N_BOOT = 200                    # Bootstrap 次数 (PySDTest 默认)
N_GRID = 100                    # 网格点数
ALPHA = 0.05                    # 显著性水平

# P45 通过标准
TARGET_S1_DETECT = 0.90        # S1: A≻B 检出率 >90%
TARGET_S1_FP = 0.05            # S1: B≻A 误报率 <5%
TARGET_S2_CROSS = 0.80         # S2: × 识别率 >80%
TARGET_S3_EQUAL = 0.80         # S3: = 识别率 >80%
TARGET_S4_SSD = 0.80           # S4: SSD 检出率 >80%
TARGET_S4_FSD_BIDIR = 0.10     # S4: FSD 双向显著率 <10%


def classify_bd(p_ab, p_ba):
    """Barrett-Donald 框架下的四分类。

    H₀ = A dominates B (PySDTest / BD 传统)
    p_ab: test_sd_SR(A, B) 的 p 值 —— H₀: A 占优 B
    p_ba: test_sd_SR(B, A) 的 p 值 —— H₀: B 占优 A

    分类逻辑:
    - p_ab < 0.05 → 拒绝 "A 占优 B" → A 不占优 B
    - p_ba < 0.05 → 拒绝 "B 占优 A" → B 不占优 A
    """
    reject_ab = p_ab < ALPHA  # A 不占优 B
    reject_ba = p_ba < ALPHA  # B 不占优 A

    if reject_ab and reject_ba:
        return "×"           # 互相拒绝 → 交叉
    elif reject_ab and not reject_ba:
        return "B≻A"         # 拒绝 A 占优 B, 不拒绝 B 占优 A → B 占优 A
    elif not reject_ab and reject_ba:
        return "A≻B"         # 不拒绝 A 占优 B, 拒绝 B 占优 A → A 占优 B
    else:
        return "="           # 都不拒绝 → 无法区分


def run_bidirectional(samples_a, samples_b, s, nboot, ngrid, seed):
    """跑一对双向检验, 返回 (p_ab, p_ba, p_ab_ssd, p_ba_ssd) 等。"""
    results = {}
    for order in [1, 2, 3]:
        # A → B: H₀ = A 占优 B
        np.random.seed(seed)
        t_ab = test_sd_SR(samples_a, samples_b, ngrid=ngrid, s=order,
                          resampling='bootstrap', nboot=nboot, a=0.1, quiet=True)
        t_ab.testing()

        # B → A: H₀ = B 占优 A
        np.random.seed(seed + 1)
        t_ba = test_sd_SR(samples_b, samples_a, ngrid=ngrid, s=order,
                          resampling='bootstrap', nboot=nboot, a=0.1, quiet=True)
        t_ba.testing()

        results[order] = {
            'p_ab': float(t_ab.result['p_val']),
            'p_ba': float(t_ba.result['p_val']),
        }
    return results


def run_scenario(name, gen_a, gen_b, n_sizes, n_reps, nboot, ngrid):
    """跑一个场景的全部实验。"""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

    all_results = {}
    for n in n_sizes:
        t0 = time.time()
        counts = {"A≻B": 0, "B≻A": 0, "×": 0, "=": 0}
        fsd_bidir = 0  # FSD 双向都显著
        ssd_a_dom_b = 0  # SSD 判定 A≻B
        total = n_reps

        for rep in range(n_reps):
            seed = rep * 100
            a = gen_a(n, seed)
            b = gen_b(n, seed)
            res = run_bidirectional(a, b, s=None, nboot=nboot, ngrid=ngrid, seed=seed)

            # FSD 分类
            fsd_cls = classify_bd(res[1]['p_ab'], res[1]['p_ba'])
            counts[fsd_cls] += 1

            # FSD 双向显著
            if res[1]['p_ab'] < ALPHA and res[1]['p_ba'] < ALPHA:
                fsd_bidir += 1

            # SSD 分类
            ssd_cls = classify_bd(res[2]['p_ab'], res[2]['p_ba'])
            if ssd_cls == "A≻B":
                ssd_a_dom_b += 1

        elapsed = time.time() - t0
        print(f"\n  n={n:5d} | {n_reps} reps | {elapsed:.1f}s")
        print(f"    FSD 分类: A≻B={counts['A≻B']:3d}  B≻A={counts['B≻A']:3d}  ×={counts['×']:3d}  ={counts['=']:3d}")
        print(f"    FSD 双向显著率: {fsd_bidir/total:.3f}")
        print(f"    SSD A≻B 检出率: {ssd_a_dom_b/total:.3f}")

        all_results[n] = {
            'fsd_counts': counts.copy(),
            'fsd_bidir_rate': fsd_bidir / total,
            'ssd_a_dom_b_rate': ssd_a_dom_b / total,
        }
    return all_results


# ============================================================
# 数据生成器
# ============================================================

def gen_s1_a(n, seed):
    rng = np.random.RandomState(seed)
    return rng.normal(70, 10, n)

def gen_s1_b(n, seed):
    rng = np.random.RandomState(seed + 1)
    return rng.normal(80, 10, n)

def gen_s2_a(n, seed):
    rng = np.random.RandomState(seed)
    return rng.normal(75, 5, n)

def gen_s2_b(n, seed):
    rng = np.random.RandomState(seed + 1)
    return rng.normal(75, 15, n)

def gen_s3_a(n, seed):
    rng = np.random.RandomState(seed)
    return rng.normal(75, 10, n)

def gen_s3_b(n, seed):
    rng = np.random.RandomState(seed + 1)
    return rng.normal(75.1, 10, n)

def gen_s4_a(n, seed):
    rng = np.random.RandomState(seed)
    return rng.chisquare(5, n)

def gen_s4_b(n, seed):
    rng = np.random.RandomState(seed + 1)
    return rng.chisquare(6, n)


# ============================================================
# 主流程
# ============================================================
if __name__ == '__main__':
    print("P45 校准实验 —— PySDTest test_sd_SR (Donald-Hsu 2016)")
    print(f"样本量: {N_SIZES} | 重复: {N_REPS} | Bootstrap: {N_BOOT} | α={ALPHA}")
    print(f"开始时间: {time.strftime('%H:%M:%S')}")

    total_start = time.time()

    # S1: 严格占优
    s1 = run_scenario("S1: 严格占优  A~N(70,10) vs B~N(80,10)  [lower_is_better → A优于B]",
                      gen_s1_a, gen_s1_b, N_SIZES, N_REPS, N_BOOT, N_GRID)

    # S2: 交叉
    s2 = run_scenario("S2: 交叉  A~N(75,5) vs B~N(75,15)  [方差不同, CDF交叉]",
                      gen_s2_a, gen_s2_b, N_SIZES, N_REPS, N_BOOT, N_GRID)

    # S3: 几乎相等
    s3 = run_scenario("S3: 几乎相等  A~N(75,10) vs B~N(75.1,10)  [微小差异]",
                      gen_s3_a, gen_s3_b, N_SIZES, N_REPS, N_BOOT, N_GRID)

    # S4: 弱 SSD 占优
    s4 = run_scenario("S4: 弱SSD  A~χ²(5) vs B~χ²(6)  [方差更小, FSD交叉但SSD可能成立]",
                      gen_s4_a, gen_s4_b, N_SIZES, N_REPS, N_BOOT, N_GRID)

    total_elapsed = time.time() - total_start

    # ============================================================
    # 汇总报告
    # ============================================================
    print(f"\n\n{'='*60}")
    print("  汇总报告")
    print(f"{'='*60}")
    print(f"总耗时: {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)")

    def check(results, n, scenario, metric, value, target, direction=">"):
        """检查是否通过。"""
        if direction == ">":
            passed = value > target
        elif direction == "<":
            passed = value < target
        else:
            raise ValueError(f"Unknown direction: {direction}")
        symbol = "✅" if passed else "❌"
        return f"{symbol} {scenario} n={n}: {metric}={value:.3f} (目标: {direction} {target})"

    checks = []
    for n in N_SIZES:
        r = s1[n]
        checks.append(check(r, n, "S1", "FSD A≻B检出率",
                          r['fsd_counts']['A≻B'] / N_REPS, TARGET_S1_DETECT, ">"))
        checks.append(check(r, n, "S1", "FSD B≻A误报率",
                          r['fsd_counts']['B≻A'] / N_REPS, TARGET_S1_FP, "<"))

        r = s2[n]
        checks.append(check(r, n, "S2", "× 识别率",
                          r['fsd_counts']['×'] / N_REPS, TARGET_S2_CROSS, ">"))

        r = s3[n]
        checks.append(check(r, n, "S3", "= 识别率",
                          r['fsd_counts']['='] / N_REPS, TARGET_S3_EQUAL, ">"))

        r = s4[n]
        checks.append(check(r, n, "S4", "SSD A≻B检出率",
                          r['ssd_a_dom_b_rate'], TARGET_S4_SSD, ">"))
        checks.append(check(r, n, "S4", "FSD双向显著率",
                          r['fsd_bidir_rate'], TARGET_S4_FSD_BIDIR, "<"))

    print()
    for c in checks:
        print(f"  {c}")

    n_pass = sum(1 for c in checks if "✅" in c)
    n_total = len(checks)
    print(f"\n  通过率: {n_pass}/{n_total} ({100*n_pass/n_total:.0f}%)")

    # 门控 G1: S1-S4 全部通过率 >80%
    all_pass = [c for c in checks if "✅" in c]
    g1_passed = len(all_pass) / n_total > 0.80
    print(f"\n  G1 门控: {'✅ 通过' if g1_passed else '❌ 未通过'} (要求 >80%, 实际 {100*len(all_pass)/n_total:.0f}%)")
