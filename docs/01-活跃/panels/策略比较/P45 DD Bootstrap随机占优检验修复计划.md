<!-- META: P45 | module:panels/策略比较 | status:in_progress | last:2026-06-14 -->
# P45 DD Bootstrap 随机占优检验修复计划

> 日期：2026-06-13 | 更新：2026-06-14（方法选型调研完成）
> 触发：实际使用中 FSD/SSD/TSD 三阶双向（A→B 和 B→A）p 值均 <0.05，失去区分能力
> 关联：P19 §效应量专项设计 · P18（BootstrapEngine 改进，不重叠——DD 实现独立于 BootstrapEngine）
> 调研报告：[stochastic-dominance-methods-survey-2026-06-14.md](../04-收件箱/stochastic-dominance-methods-survey-2026-06-14.md)

---

## 一、问题诊断

### 1.1 用户报告

比较分析面板 L2 随机占优中，对于任意两个策略，**FSD/SSD/TSD 三个阶数的 A→B 和 B→A 双向检验 p 值均 <0.05**（3×2=6 个检验全部显著）。用户无法从结果中区分「占优」「交叉」「无差异」。

### 1.2 根因：中心化 Bootstrap 未正确施加非占优零假设

**代码位置：** [comparison_analyzer.py:248-258](gacha_simulator/core/comparison_analyzer.py#L248-L258)

```python
# 当前实现 —— 简单中心化
F_a_centered = F_a - np.mean(F_a)
F_b_centered = F_b - np.mean(F_b)

for b in range(n_bootstrap):
    idx_a = rng.integers(0, n_a, size=n_a)
    idx_b = rng.integers(0, n_b, size=n_b)
    boot_a = integrated_cdf(samples_a[idx_a], grid, order) - F_a_centered
    boot_b = integrated_cdf(samples_b[idx_b], grid, order) - F_b_centered
    bootstrap_maxes[b] = np.max(boot_a - boot_b)

p_value = np.mean(bootstrap_maxes >= observed_max)
```

**问题链条：**

1. `F - mean(F)` 中心化使两个积分 CDF 的均值均为零，构建的 Bootstrap 零分布对应 H₀：「积分 CDF 形状相同」——即 **CDF 相等性检验**
2. 随机占优检验的正确 H₀ 应为「A **不** j 阶占优 B」——一个**单向**约束（max(F_a − F_b) ≤ 0）
3. 在 CDF 相等性零分布下，只要两个策略的积分 CDF 有任何差异（包括交叉），max(F_a − F_b) 和 max(F_b − F_a) 均落在 Bootstrap 分布的右尾 → 双向 p 值均 <0.05
4. 大样本量（N ≥ 500）使 Bootstrap 分布极度集中，**放大了这一效应**——微小差异也可被检测

**学术依据（详见下文 §文献）：**

- Davidson & Duclos (2006) 开发了 Empirical Likelihood 约束 Bootstrap 以**正确施加非占优零假设**——约束 Bootstrap DGP 处于非占优前沿面（积分 CDF 在接触点相等）
- Donald & Hsu (2016) 独立证明：未在接触集上重中心化的 Bootstrap 对随机占优检验的尺寸控制差
- 当前简单中心化等价于 DD (2000) 的渐近检验——DD (2006) 已证明其「**严重尺寸不足**」（seriously undersized）

### 1.3 次要问题：双向裁决被 UI 隐藏

**代码位置：** [comparison_analyzer.py:307-312](gacha_simulator/core/comparison_analyzer.py#L307-L312) + [comparison_analysis_panel.py:530-535](gacha_simulator/gui/comparison_analysis_panel.py#L530-L535)

```python
# compute_dominance_matrix() 中 —— 双向裁决
if dominates[i][j] and dominates[j][i]:
    dominates[i][j] = False
    dominates[j][i] = False  # ← 裁决后 dominates 矩阵正确

# _update_l2() 中 —— 但 UI 从不读取 dominates 矩阵
p = dom['matrix'][i][j]       # ← 读取的是原始 p 值，非裁决后分类
color = '#2e7d32' if p < 0.05 else '#666'
```

UI 展示的是 `dom['matrix']`（原始 p 值），而非 `dom['dominates']`（双向裁决后的分类）。即使 p 值本身可靠，用户在 UI 中看到的 p<0.05 绿色高亮与实际 `dominates=False`（裁决后）**不一致**。

### 1.4 次要问题：FSD⇒SSD⇒TSD 层次嵌套未被传达

三个阶数作为三个独立 HTML 表格并排展示，制造了「三次独立验证」的错觉。实际上 FSD ⟹ SSD ⟹ TSD 是数学定理（Davidson & Duclos, 2000, Theorem 1），FSD 显著时 SSD/TSD 的信息增量为零。

### 1.5 方法论背景更新 (2026-06-14)

**Fang & Santos (2019) 奠基性结论：**

SD 检验统计量（如 `max(F_a − F_b)`）是分布函数的泛函，该泛函在 H₀ 边界处仅是 **Hadamard 方向可微**（非全可微）。Fang & Santos (2019, *Review of Economic Studies*) 证明：**当 φ 仅是方向可微时，标准 Bootstrap 不一致。** 这是本计划 §1.2 根因分析的理论根基——等式中心化的本质是 Bootstrap 隐含假定了全可微性。

**学界现状：LFC 已淘汰，三足鼎立：**

| 校正技术 | 出处 | 机制 | 实现 |
|----------|------|------|------|
| 接触集估计 | Linton-Song-Whang (2010) | 仅在分布重合的网格点施加 H₀ | PySDTest `test_sd_contact` |
| 选择性重中心化 | Donald-Hsu (2016) | 仅在约束接近 binding 的点重中心化 | **PySDTest `test_sd_SR`** ← 与 FIXME-1 方法论一致 |
| 数值 Delta 法 | Hong-Li (2018) | 有限差分近似方向导数，免 Bootstrap | PySDTest `test_sd_NDM` |

**关键发现：PySDTest `test_sd_SR` 是 Donald-Hsu 2016 的参考实现。**

经源码审查（[评估报告](stochastic-dominance-methods-survey-2026-06-14.md) §六），PySDTest v0.0.21（9.4 KB，仅 numpy+matplotlib 依赖）的 `test_sd_SR` 类正确实现了 Donald & Hsu (2016) 的选择性重中心化逻辑——包括 `selective_recentering()` 方法（`selected_set = (√n₂ · D_s) < -a · √[log(log(N))]`）。其 `test_sd` 类（BD 2003）与当前代码同病（等式中心化），但 `test_sd_SR` 正确。

**H₀ 方向差异：**

| | 当前实现 + P45 计划 | PySDTest `test_sd_SR` |
|---|---|---|
| 方法论传统 | Davidson & Duclos (2000/2006) | Barrett & Donald (2003) → Donald & Hsu (2016) |
| H₀ | **不**占优 | **占优** |
| p < 0.05 含义 | 拒绝不占优 → **正面断言占优** | 拒绝占优 → **排除占优** |
| 学界立场 | DD 传统（Whang 2019 §2.3） | 计量经济学主流（Whang 2019 §2.2） |

这不影响 FIXME-1 的校准实验设计——接触集重中心化的数学在两种 H₀ 方向下均适用。但若直接使用 PySDTest，FIXME-2（分类裁决矩阵）需要根据 H₀ 方向调整判定规则。

---

## 二、FIXME 清单

### FIXME-0 (新增 2026-06-14)：方法论选型前置决策

在实施 FIXME-1 前，先确认实现路径：

| 路径 | 方案 | H₀ | 工作量 | 风险 |
|------|------|-----|--------|------|
| **A（推荐）** | `pip install PySDTest` → 用 `test_sd_SR` 替换 | 占优 | 1-2h + 适配器 | H₀ 方向需在 FIXME-2 中调整 |
| **B** | 从 PySDTest 移植 `selective_recentering()` 到 DD 框架 | 不占优 | 3-4h + S1-S4 | 手写易引入新 bug |
| **C** | 按原计划从零实现接触集重中心化 | 不占优 | 3-4h + S1-S4 | 需独立编码 + 调试 |

**推荐路径 A**，理由：
- PySDTest `test_sd_SR` 的 `selective_recentering()` 由论文作者团队实现，正确性有保障
- 9.4 KB 纯 Python，零编译依赖，集成成本极低
- 先用 S1-S4 校准实验验证效果（1h），若不满意再切换到路径 B
- H₀ 方向差异在策略比较场景中影响有限——用户关心的是「哪个策略更好」的相对排序，而非绝对占优断言

### FIXME-1：替换中心化 Bootstrap 为约束 Bootstrap

**文件：** `core/comparison_analyzer.py` → `dd_bootstrap_test()`

**目标：** Bootstrap DGP 正确施加 H₀: A 不 j 阶占优 B（即积分 CDF 在至少一处接触）

**首选方案（2026-06-14 更新）：集成 PySDTest `test_sd_SR`**

PySDTest v0.0.21 的 `test_sd_SR` 类已正确实现 Donald & Hsu (2016) 选择性重中心化：

```python
# gacha_simulator/core/comparison_analyzer.py 集成方案

from pysdtest import test_sd_SR
import numpy as np

def dd_bootstrap_test_v2(samples_a, samples_b, n_bootstrap=2000,
                          ngrid=100, seed=None):
    """使用 PySDTest Donald-Hsu 2016 选择性重中心化替换原始实现。
    
    注意：PySDTest 的 H₀ = A 占优 B（BD 传统），
    p < 0.05 → 拒绝占优 → A 不占优 B。
    """
    if seed is not None:
        np.random.seed(seed)
    
    results = {}
    for s in [1, 2, 3]:
        test = test_sd_SR(
            samples_a, samples_b, ngrid=ngrid, s=s,
            resampling='bootstrap', nboot=n_bootstrap,
            a=0.1, quiet=True
        )
        test.testing()
        results[s] = {
            'p_value': float(test.result['p_val']),
            'test_stat': float(test.result['test_stat']),
            'critical_val': float(test.result['critical_val'])
        }
    return results
```

**备选方案（若 PySDTest 校准实验不通过）：Donald-Hsu 2016 风格手写重中心化**

| 子任务 | 描述 |
|--------|------|
| 1a | 估计**接触集** Ĉ = {网格点 x : \|F_a(x) − F_b(x)\| ≤ 1.96 × SÊ(x)}。其中 `SÊ(x) = sqrt(F_a·(1−F_a)/n_a + F_b·(1−F_b)/n_b)`——经验 CDF 在 x 处的二项标准误（两独立样本合并）。1.96 为渐近正态 95% 临界值 |
| 1b | 仅在接触集上计算重中心化偏移量：`offset_a = mean_{x∈Ĉ}[F_a(x)]`, `offset_b = mean_{x∈Ĉ}[F_b(x)]`。Bootstrap 复制时使用 `boot_a = bootstrap_integrated_cdf_a − F_a + offset_a`（即仅在接触集层面保留原始均值差异，消除非接触区域的虚假偏移） |
| 1c | Bootstrap 仍独立重抽样 A 和 B，但构建统计量的差值使用接触集重中心化版本 |
| 1d | 统计量**保持** `max(F_a − F_b)`。方向推导：H₀ 为真（A 不占优 B）→ ∃x 使 F_a(x) > F_b(x) → max > 0 → p 大 → 不拒绝 ✓；H₀ 为假（A 占优 B）→ ∀x: F_a(x) ≤ F_b(x) → max ≤ 0 → p 小 → 拒绝 ✓ |
| 1e | p 值 = `P(bootstrap_max ≥ observed_max)` |
| 1f | **回退策略**：若 Ĉ 为空（两分布差异极大，所有网格点 \|F_a−F_b\| 远超 1.96×SÊ），取 argmin \|F_a−F_b\| 的 k 个网格点作为伪接触集，其中 k = max(3, n_grid/20) |

**备选方案（若接触集估计效果不佳）：** Davidson & Duclos (2006) 完整 Empirical Likelihood 约束。Lok & Tabri (2021, *Journal of Econometrics*) 在此基础上加入了 EL tilting 改进——在接触集上对经验分布进行 tilting，最大化检验功效。FSD 有解析解（加权使 min 接触点处等概率），SSD/TSD 需要 Newton 法数值优化（实现复杂度高 3-5 倍）。备选触发条件：接触集重中心化后，若校准实验仍有 >20% 的双向过度显著率，则升级为完整 EL。

### FIXME-2：UI 展示分类矩阵而非原始 p 值

**文件：** `gui/comparison_analysis_panel.py` → `_update_l2()`

**前置依赖：** FIXME-0（若选路径 A，PySDTest 的 H₀ 方向为「占优」，分类判定规则需对应调整）

**目标：** 将三个独立 HTML p 值矩阵合并为一个分类矩阵

| 子任务 | 描述 |
|--------|------|
| 2a | 新增 `_classify_dominance(fsd, ssd, tsd)` 函数：基于三阶的双向 p 值输出单一分类（≻/≺/=/×/~）。返回值含 `effect_size_slot: Optional[str]` 字段——初始为 `None`，供后续效应量专项（P19 §效应量）填入如 `d=0.42` 或 `CLES=0.53` |
| 2b | 替换 `_update_l2()` 为单一 HTML 表格，显示分类矩阵 + 最低有效阶数标注 |
| 2c | 新增图例：≻ (FSD) / ≻ (SSD) / ≻ (TSD) / × (交叉) / = (无差异) / ~ (边界) |
| 2d | 「高级」折叠面板——保留原始 FSD/SSD/TSD p 值矩阵供调试/审查 |

**分类判定规则（合并三阶双向信息）：**

```
对每对 (i, j)：

  边界定义：p ∈ [0.03, 0.07] 为「边界区」——不强制归类

  1. 若 FSD(i→j) 显著 (p<0.05) 且 FSD(j→i) 不显著 (p≥0.05)
     → "≻ (FSD)"  [若对侧 p∈[0.03,0.07]，降级为 "~≻ (FSD)"]
  2. 若 FSD 双向不显著或边界，但 SSD(i→j) 显著 且 SSD(j→i) 不显著
     → "≻ (SSD)"
  3. 若 FSD+SSD 双向不显著或边界，但 TSD(i→j) 显著 且 TSD(j→i) 不显著
     → "≻ (TSD)"
  4. 若某阶双向均显著 (双方 p<0.05)
     → "×"（交叉），标注最低出现双向显著的阶数，如 "×(FSD)" / "×(SSD)" / "×(TSD)"
     例外：若该阶双向显著但更高阶一致单向显著，降级为 "×?(FSD)"（提示 FSD 交叉可能为噪声）
  5. 若所有阶双向均不显著
     → "="（无显著差异）
     例外：若所有阶 p 均 >0.07 → "=" ；若存在 p∈[0.03,0.07] → "~"（边界——无显著差异但接近）
```

### FIXME-3：新增集成 CDF 差异可视化

**文件：** `gui/comparison_analysis_panel.py` → 新增方法 `_render_l2_chart()`

**目标：** 在分类矩阵下方添加 Plotly 图，显示积分 CDF 曲线及差异区域

| 子任务 | 描述 |
|--------|------|
| 3a | 用户点击分类矩阵中某个 (i, j) 单元格 → 在下方面板渲染 F_a, F_b 的 1/2/3 阶积分 CDF 曲线 |
| 3b | 阴影标注 max(F_a − F_b) 和 max(F_b − F_a) 区域（双向差异可视化） |
| 3c | 标注接触集（若有）和占优/交叉判定依据 |

### FIXME-4：更新文档与计划体系

| 子任务 | 描述 |
|--------|------|
| 4a | 更新 [01-理论.md](docs/01-活跃/panels/策略比较/01-理论.md) §3.2——补充 DD Bootstrap 实现细节、非占优零假设说明、FSD⇒SSD⇒TSD 层次 |
| 4b | 更新 [04-问题.md](docs/01-活跃/panels/策略比较/04-问题.md)——新增 P1 条目：「DD Bootstrap 双向过度显著——中心化未正确施加非占优约束」 |
| 4c | 更新 [P19 未完成清单.md](docs/01-活跃/panels/策略比较/P19 未完成清单.md)——从 Phase 3 暂缓中移除旧「效应量热力图」条目（已被 P45 FIXME-2 取代） |
| 4d | 更新 [模块状态矩阵.md](docs/00-meta/模块状态矩阵.md)——注册 P45 |

---

## 三、校准实验设计

在实施修复前，先设计校准实验以量化当前实现的问题严重程度，并建立修复后的通过标准。

### 3.1 Ground Truth 场景

每个场景在 **3 个样本量**（n = 100 / 500 / 2000）下测试，**每组参数重复 100 次独立实验**（随机种子 0–99），报告双向显著率的均值和 95% CI。

| 场景 | 描述 | 期望 DD 输出 |
|------|------|-------------|
| **S1: 严格占优** | A ∼ N(μ=70, σ=10), B ∼ N(μ=80, σ=10)（lower_is_better → A 优于 B） | FSD: A≻B 显著, B≻A 不显著 |
| **S2: 均值同·方差异（交叉）** | A ∼ N(μ=75, σ=5), B ∼ N(μ=75, σ=15) | FSD: ×（交叉——A CDF 在左侧更低、右侧交叉） |
| **S3: 几乎相等** | A ∼ N(μ=75, σ=10), B ∼ N(μ=75.1, σ=10) | =（无显著差异） |
| **S4: 弱 SSD 占优** | A ∼ χ²(df=5), B ∼ χ²(df=6)（A 方差更小，FSD 交叉但 SSD 可能成立） | SSD: A≻B 显著 |

### 3.2 通过标准

| 指标 | 当前预期（目测） | 修复后目标 |
|------|-----------------|-----------|
| S1 双向显著率 | >50%（过度显著） | FSD A≻B 检出率 >90%，B≻A 误报率 <5%（100 次重复均值） |
| S2 被识别为交叉 | ≈0%（被双向显著淹没） | >80% 分类为 ×（100 次重复均值） |
| S3 被识别为相等 | ≈0%（微小差异被放大） | >80% 分类为 =（100 次重复均值） |
| S4 SSD 正确检出 | 不可靠（FSD 双向噪声干扰） | SSD A≻B 检出率 >80%，FSD 双向显著率 <10% |

### 3.3 完成门控

| 门控 | 条件 | 验证方式 |
|------|------|---------|
| **G1 统计** | S1–S4 全部通过率 >80%（100 次重复 × 3 样本量 = 1200 次实验） | 校准脚本输出 CI 矩阵 |
| **G2 性能** | 3 策略 × N=1000, B=1000 时 L2 总耗时 <5s（当前约 2s，接触集估计不应显著增加开销） | 计时装饰器 |
| **G3 回归** | `analysis_panel` 不受影响——现有测试全部通过，`BootstrapEngine` 行为不变 | `pytest -q --cov` |
| **G4 UI** | 3 人非统计背景试用，>2 人能正确解释 ×（交叉）和 ≻（占优）的含义 | 内部试用反馈 |

---

## 四、文献依据

### 理论基础

**Fang, Z., & Santos, A. (2019).** Inference on directionally differentiable functions. *Review of Economic Studies*, *86*(1), 377–412. https://doi.org/10.1093/restud/rdy049
- **奠基性结论：当 φ 仅是 Hadamard 方向可微（非全可微）时，标准 Bootstrap 不一致。** SD 检验统计量是方向可微泛函——这从根源上解释了 §1.2 的等式中心化 bug。
- 两个修复路径：(a) 修改 Bootstrap DGP（→ DH 2016, LSW 2010），(b) 修改 Bootstrap 统计量（→ NDM 2018）
- 是理解 LSW/DH/NDM 三者关系的理论框架

### 核心方法论

**Davidson, R., & Duclos, J.-Y. (2000).** Statistical inference for stochastic dominance and for the measurement of poverty and inequality. *Econometrica*, *68*(6), 1435–1464. https://doi.org/10.1111/1468-0262.00167
- 奠定 DD 渐近检验框架——网格点 T 统计量 + SMM 临界值
- 证明 FSD ⟹ SSD ⟹ TSD 嵌套定理（Theorem 1）
- 指出渐近检验「严重尺寸不足」(seriously undersized)

**Davidson, R., & Duclos, J.-Y. (2006).** Testing for restricted stochastic dominance. IZA Discussion Paper No. 2047. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=894061
- 将 H₀ 反转为**非占优**（拒绝 → 占优），通过 EL 约束将 Bootstrap DGP 置于前沿面
- 证明 EL Bootstrap 大幅改善尺寸和效力
- FSD 有解析加权解，SSD/TSD 需 Newton 法

**Donald, S. G., & Hsu, Y.-C. (2016).** Improving the power of tests of stochastic dominance. *Econometric Reviews*, *35*(4), 553–585. https://doi.org/10.1080/07474938.2013.833813
- Hansen (2005) 重中心化方法应用于连续不等式约束
- 在接触集上重中心化 → 比 Barrett-Donald (2003) LFC 方法更不保守、更 powerful
- FIXME-1 的方法论参考。**PySDTest `test_sd_SR` 为此方法的参考实现**

**Linton, O., Song, K., & Whang, Y.-J. (2010).** An improved bootstrap test of stochastic dominance. *Journal of Econometrics*, *154*(2), 186–202.
- 接触集估计方法——Bootstrap 重抽样仅在估计的接触集上施加 H₀
- 证明了渐近 size 一致有效（uniform asymptotic validity）
- 与 DH 2016 选择性重中心化并列为两大 LFC 替代方案

### 软件与实现

**Lee, K., & Whang, Y.-J. (2024).** PySDTest: A Python/Stata package for stochastic dominance tests. arXiv:2307.10694. https://arxiv.org/abs/2307.10694
- 实现了 BD (2003)、LMW (2005)、LSW (2010)、DH (2016)、NDM (2018) 五种方法
- `test_sd_SR` 类 = DH 2016 选择性重中心化（FIXME-1 首选方案）
- `test_sd` 类 = BD 2003 LFC（⚠️ 与当前代码同病——等式中心化）
- 9.4 KB 纯 Python，仅 numpy+matplotlib 依赖

### 综述

**Whang, Y.-J. (2019).** *Econometric analysis of stochastic dominance: Concepts, methods, tools, and applications*. Cambridge University Press.
- **领域标准参考书。** 将 H₀ 系统分为三类（§2.2 占优式 / §2.3 非占优式 / §2.4 等式式）
- 附录 B 提供完整 MATLAB 代码（McFadden / Barrett-Donald / LMW / Donald-Hsu / Hall-Yatchew）

### 辅助文献

**Barrett, G. F., & Donald, S. G. (2003).** Consistent tests for stochastic dominance. *Econometrica*, *71*(1), 71–104.
- KS 型统计量 + 四分类矩阵（≻/≺/=/×）——FIXME-2 的 UI 设计参考

**Bennett, C. J. (2024).** On a bidirectional test for stochastic dominance. Vanderbilt University Working Paper.
- 两阶段序贯检验（Equality → Dominance/Crossing），Bootstrap 不施加 H₀ 约束（激进新方向）
- 工作论文（未经同行评审），P45 引用为备选思路，不推荐作为主方案

**Linton, O., Maasoumi, E., & Whang, Y.-J. (2005).** Consistent testing for stochastic dominance under general sampling schemes. *Review of Economic Studies*, *72*(3), 735–765.
- 子抽样方法，验证了简单 Bootstrap 在 SD 边界上的尺寸失真

**Hong, H., & Li, J. (2018).** The numerical delta method. *Journal of Econometrics*, *206*(2), 379–394.
- 数值 Delta 法——有限差分近似 Hadamard 方向导数，免 Bootstrap
- PySDTest `test_sd_NDM` 实现，可作为备选交叉验证手段

**Lok, T. M., & Tabri, R. V. (2021).** An improved bootstrap test for restricted stochastic dominance. *Journal of Econometrics*, *224*(2), 371–393.
- 在 DH 2016 基础上加入经验似然 tilting——最大化检验功效
- 非占优-H₀ 框架（DD 传统），与本计划方向一致，但实现复杂度高（EL 优化）

---

## 五、任务暂估

| # | 内容 | 预估 | 依赖 |
|---|------|------|------|
| 0 | **FIXME-0 (新增)**：`pip install PySDTest` + S1-S4 校准实验 | 1.5h | — |
| 1 | FIXME-1：PySDTest `test_sd_SR` 适配器集成 | 1h | 0 (校准通过) |
| 2 | FIXME-2：UI 分类矩阵（含 H₀ 方向适配） | 2h | 1 |
| 3 | FIXME-3：集成 CDF 可视化 | 1.5h | 1 |
| 4 | FIXME-4：文档更新 | 1h | 1-3 |
| 5 | 回归测试（analysis_panel 不受影响） | 0.5h | 1-3 |
| ↳ | **若 FIXME-0 校准不通过 → 路径 B 手写实现** | +3-4h | 0 |

**总计（路径 A）：** 7-8h | **总计（路径 B，若校准失败）：** 10-12h

---

## 六、与现有计划的关系

| 计划 | 关系 | 说明 |
|------|------|------|
| **P19** | 互补 | P19 是策略比较面板的总重构计划；P45 是其中一个具体统计缺陷的修复。P19 §效应量（2026-06-12 新增）为 L2 补充效应量，P45 修复 L2 的核心检验方法——两者可并行 |
| **P18** | 无重叠 | P18 改进 `BootstrapEngine`（BCa/GPD/Hill），P45 改进 `dd_bootstrap_test()`（SD 专属 Bootstrap），两者零代码交集 |
| **效应量专项** | 协同 | P19 §效应量（CLES/Hedges' g/RD）与 P45 的分类矩阵共享 n×n 显示框架——效应量可直接嵌入分类矩阵单元格。Song & Sun (2025) 几乎占优系数可作为远期效应量参考 |
| **调研报告** | 前置输入 | [stochastic-dominance-methods-survey-2026-06-14.md](../../04-收件箱/stochastic-dominance-methods-survey-2026-06-14.md) — 21 组已验证主张，覆盖 7 种方法论 + 5 个软件包 |

---

## 七、参考资料

- 实现代码：`gacha_simulator/core/comparison_analyzer.py` (413行) · `gacha_simulator/gui/comparison_analysis_panel.py` (~380行)
- 文档：`docs/01-活跃/panels/策略比较/01-理论.md` §3.2 · `docs/01-活跃/panels/策略比较/P19 未完成清单.md`
- 模块状态矩阵：`docs/00-meta/模块状态矩阵.md`
- 调研报告：`docs/01-活跃/04-收件箱/stochastic-dominance-methods-survey-2026-06-14.md`
