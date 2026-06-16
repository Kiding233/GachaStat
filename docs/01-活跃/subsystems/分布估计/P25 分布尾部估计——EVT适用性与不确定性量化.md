<!-- META: P25 | module:subsystems/分布估计 | status:in_progress | last:2026-06-13 -->
# P25 分布尾部估计——EVT 适用性与不确定性量化

> 创建日期：2026-06-13（合并 P25 原版 + P32）
> 来源：
> - `P25 EVT改进——离散型与退化分布处理.md`（2026-05-28，940 行）
> - `P32 分布尾部估计改进计划.md`（2026-05-29，137 行）
> 前置：P24 EVT 尾部拟合（已完成）
> 关联：P18（Bootstrap 引擎——跨模块项 B2.8/B2.9/P32阶段二 已提取到综合计划）
> 涉及文件：`distribution.py`、`evt_tail.py`、`risk_analysis.py`、`gui/about_dialog.py`、`gui/analysis_panel.py`

---

## 合并说明

P25 回答了「EVT 何时适用」（离散退化检测、GDR 分类），P32 回答了「尾部估计有多不确定」（Bootstrap SE、缺陷修复）。两者共用 `distribution.py`，合并后形成「分布尾部估计」的完整文档。

**已提取到综合计划（Bootstrap-EVT 统一与尾部 CI 实施计划）的跨模块项：**
- B2.8：`_bootstrap_tail_gpd()` 委托 `evt_tail`（消除重复 GPD 拟合）
- B2.9：GPD-param Bootstrap 百分位法 → TIB（CI 覆盖率修复）
- P32 阶段二：`cvar()`/`quantile()` 的 `return_se` + GPD 尾部委托

本计划聚焦于 `distribution.py`/`evt_tail.py` 层面的改进，不包含跨 `bootstrap.py` 的胶水代码。但对 Bootstrap 的依赖分析（当前两套独立 GPD 拟合的问题诊断）保留在 §七，作为综合计划的理论前置。

---

## 一、理论基础：离散分布与极值理论

### 1.1 长尾条件是 EVT 的必要前提

极值理论的核心定理——Pickands-Balkema-de Haan 定理（Balkema & de Haan 1974; Pickands 1975）——要求底层分布属于某个极值分布的吸引域（Maximum Domain of Attraction, MDA）。而 MDA 的一个**必要条件**是分布为**长尾分布**（long-tailed）：

\[
\lim_{x \to \infty} \frac{\overline{F}(x + c)}{\overline{F}(x)} = 1, \quad \forall c > 0
\]

其中 \(\overline{F}(x) = 1 - F(x)\) 为生存函数。对于**取值为整数的离散分布**，长尾性质等价于：

\[
\lim_{n \to \infty} \frac{\overline{F}(n+1)}{\overline{F}(n)} = 1
\]

即相邻整数格点的尾部概率比值趋于 1。

### 1.2 Anderson (1970)：离散化系统性破坏长尾性

Anderson (1970) 的经典论文 *"Extreme value theory for a class of discrete distributions with applications to some stochastic processes"*（*Journal of Applied Probability*, Vol. 7, No. 1, pp. 99–113）研究了整数格点分布的极值渐近行为，识别出三种根本不同的体制：

| 尾部比值极限 | Anderson 分类 | 极值行为 | 代表性分布 |
|-------------|-------------|---------|-----------|
| r = 1 | 长尾 | 经典 MDA *可能*成立 | 亚指数分布（离散化后） |
| r ∈ (0, 1) | **Anderson 类 Dα** | 最大值**不收敛**到单一极值分布，而是在上下两个**偏移 Gumbel 分布**间振荡：exp(-r^{-(x-1)}) ≤ liminf ≤ limsup ≤ exp(-r^{-x}) | **几何分布**、**负二项分布** |
| r = 0 | 远离任何吸引域 | 最大值几乎必然在两个连续整数间**振荡** | **Poisson 分布** |

**Anderson (1970) 的核心结论**：最常见的离散分布——Poisson、几何、负二项——**全都不属于任何经典极值吸引域**。连续分布的 MDA 成员资格在离散化过程中被破坏。

**关键反例**：设 \(X \sim \text{Exp}(\lambda)\) 是连续指数分布，则 \(Y = \lfloor X \rfloor \sim \text{Geom}(p)\) 是几何分布（其中 \(p = 1 - e^{-\lambda}\)）。指数分布**属于** Gumbel 吸引域（ξ=0，超额分布精确为指数 = GPD(ξ=0)），而几何分布——仅仅是将其取整——就**丧失了** MDA 成员资格（Shimura 2012）：

\[
\frac{\overline{F}_{\text{Geom}}(n+1)}{\overline{F}_{\text{Geom}}(n)} = 1-p = e^{-\lambda} < 1
\]

离散化使得尾部比值从连续极限 1 变为常数 r < 1，长尾性质被破坏。Anderson 类 Dα 的最大值行为——在偏移 Gumbel 分布间振荡——意味着**不存在唯一的极值吸引域**。

### 1.3 抽卡模拟的缓解因素：独立加和的中心极限效应

以上分析针对的是**单一离散随机变量**（如单次抽卡的出货抽数）。但实际 GDR 指标（如 `resource_remaining`、`weighted_satisfaction`）是**大量独立随机变量的加和**。由中心极限定理（CLT），加和的分布趋近正态分布，而正态分布属于 Gumbel 吸引域（ξ = 0）。

具体来说：
- 单次出货等待抽数 ~ Geom(p)，尾部分类为 Anderson Dα，理论上有 MDA 振荡
- 5000 次模拟的 `resource_remaining` = Σ(单次资源消耗)，是 5000 个随机变量的加和
- 加和分布趋近正态，属于 Gumbel 吸引域，对 POT-GPD 的收敛速度 μ(n) 随 n 增大
- 5000 次模拟 + 5000 个不同取值 = 连续性近似优秀

这就是为什么**在实践中**，连续 GPD 对高模拟次数下的 GDR 分布工作良好——即使单个过程的离散性在理论上与 MDA 条件冲突，大量独立加和后的分布已足够连续。

---

## 二、连续 GPD 应用于离散数据的可靠性：δ/σ 分层

### 2.1 分层评估

基于以上文献，对连续 GPD 在抽卡模拟离散数据上的可靠性进行分层评估：

| GDR 类别 | 示例指标 | 不同取值数 | 离散化间距 δ | 典型尺度 σ | δ/σ | 连续 GPD 可靠性 |
|----------|---------|-----------|------------|-----------|-----|---------------|
| **A 类（大值域）** | `resource_remaining` | 数百~数千 | 1 | 500~3000 | <0.002 | ✅ **高**——Deidda & Puliga (2009) 确认此比值下所有估计器无显著偏差 |
| **A 类（连续值）** | `weighted_satisfaction` | 数百~数千 | ~0 | 10~100 | ~0 | ✅ **高**——浮点连续值，无离散化问题 |
| **B 类（中等格点）** | `target_achievement` (N=50) | 51 | 1/50=0.02 | 0.2~0.5 | 0.04~0.10 | ✅ **可接受**——δ/σ ≈ 0.05-0.10，在 Deidda & Puliga 的「可忽略」范围内 |
| **B 类（边际格点）** | `target_collection` (K=6) | 7 | 1/6≈0.167 | 0.2~0.5 | 0.3~0.8 | ⚠️ **边际**——δ/σ 接近 Deidda & Puliga 的「退化」区域；Hitz et al. 建议在此类存在大量 ties 的数据上使用 D-GPD |
| **C 类（退化）** | `all_targets` | 2 | 1 | 0.4~0.6 | 1.7~2.5 | ❌ **不可靠**——δ/σ > 1，所有估计器崩溃；应回退经验分位数 |

### 2.2 阈值 < 20 的理论验证

当前方案选择 distinct < 20 作为跳过 EVT 的阈值。从 δ/σ 角度看：

- 对于值域 [0, 1] 的有理数格点 GDR（如 `target_collection`），distinct=20 意味着格点间距 δ = 1/19 ≈ 0.053
- GDR 的典型标准差 σ ~ 0.15-0.30
- δ/σ ≈ 0.18-0.35 → 接近 Deidda & Puliga (2009) 的「显著偏差」区域
- 因此 distinct < 20 作为跳过阈值在文献上是**合理的**，甚至是保守的（已在 δ/σ 开始有影响的区域就回退了）

### 2.3 与 Hitz et al. (2024) 的一致性

当前方案的核心设计原则——「ties 多时回退经验分位数，ties 少时使用连续 GPD」——与 Hitz et al. (2024) 的最核心发现完全一致：

> *"Both methods [D-GPD and GZD] outperform the continuous GPD when there are many tied observations; otherwise results are similar."*

当不同取值数 ≥ 20 时，数据中 ties 的比例通常 < 5%（5000 个样本分布在 20+ 个格点上），连续 GPD 的偏差可忽略。当不同取值数 < 20 时，ties 比例可能 > 25%，此时经验分位数本身就是精确的（格点间距就是分辨率上限）。

### 2.4 MLE-IC 对极端分位数估计稳定性的提升——机制与边界

**核心问题**：MLE-IC 修正了似然函数，但这是否转化为更稳定的极端分位数估计？

**提升机制（三重）**：

1. **形状参数 ξ 的偏差校正 → VaR 偏差的乘数级缩减**

   极端分位数对 ξ 极为敏感。VaR(q) ∝ (1-q)^{-ξ} 的关系意味着：即使 ξ 的偏差只有 0.05，当外推到 q=0.01 时，VaR 的相对偏差会被放大 10-50 倍。MLE-IC 通过消除离散化导致的似然函数系统偏差，直接校正 ξ 的估计偏差——这是 MLE-IC 对极端分位数稳定性最重要的贡献。

2. **更多超额样本被保留**

   Ma et al. (2024) 的实际数据应用发现：MLE-IC 能在 9/18 个站点成功选择阈值，而 naive MLE 仅在 2/18 个站点成功。较低的阈值意味着更多的超额样本（n_exc ↑），GPD 拟合的方差 ∝ 1/√(n_exc)，直接转化为更窄的置信区间。报告结果：MLE-IC 的置信区间宽度在某些站点仅为 naive MLE 的 **1/10**。

3. **正确的 Fisher 信息矩阵 → 校准的渐近方差**

   区间删失似然的二阶导数（Hessian）正确反映了离散观测的实际信息含量。如果观测被舍入到 δ，则观测中包含的关于底层连续参数的信息确实少于连续似然所假设的——MLE-IC 正确地「知道」这一点，而 naive MLE 过度自信。

**边界与限制**：

1. **He et al. (2014) 的基本限制**（*Statistics and Its Interface*, Vol. 7, pp. 389–404）：

   > *"Better parameter estimation does not necessarily lead to better extreme quantile estimation."*

   即使 ξ 和 σ 被完美估计，极端分位数本身的抽样变异性仍然很大——特别是对 ξ ≥ 0.5（非常重尾）或 ξ < -0.5（非常短尾，接近有界支撑）的情况。MLE-IC 改进参数估计，但不能消除极端分位数估计的固有统计困难。

2. **离散化间距的硬天花板**

   Deidda & Puliga (2009) 的 Monte Carlo 模拟表明：当 δ/σ ≳ 0.5 时，**所有估计器**——包括理论上无偏的估计器——都严重退化。MLE-IC 只是修正了离散化偏差，并没有增加数据的信息含量。如果 δ 太大，数据本身就没有足够的信息来区分不同的参数值，任何方法都无济于事。

3. **阈值选择的连锁效应**

   MLE-IC 倾向于选择更低的阈值（保留更多超额样本），这通常有利——但阈值过低会引入非尾部数据，违反 GPD 的渐近假设。Ma et al. (2024) 的框架包含了拟合优度检验以验证阈值选择，但实践中这一环节容易被忽略。

**对抽卡模拟的结论**：

| GDR 类别 | δ/σ | MLE-IC 稳定性提升 |
|----------|-----|------------------|
| A 类（resource_remaining 等） | < 0.002 | **可忽略**（naive MLE 已接近无偏） |
| B 类边际（target_collection, K=6） | 0.3~0.8 | **显著**——ξ 偏差校正 + 置信区间收窄 |
| C 类（all_targets） | 1.7~2.5 | **仍不可靠**——δ/σ 超过任何方法的可用上限 |

**关键结论**：MLE-IC 在 δ/σ 大时（粗离散化网格）对极端分位数估计稳定性有**显著提升**，但在抽卡模拟的主流场景（模拟次数多、δ/σ 极小）中，这种提升可以忽略。MLE-IC 最有价值的应用场景是 B 类边际 GDR（target_collection 等有限格点但 ≥ 20 不同取值的指标）。

### 2.5 MLE-IC 与 Bootstrap 的兼容性

#### A. 参数 Bootstrap + MLE-IC（完全兼容，推荐方案）

数据生成模型为：连续潜变量 → 离散化 → 观测。Bootstrap 精确复制此过程：

```
Step 1: 对原始离散数据拟合 MLE-IC → (ξ̂, σ̂)
Step 2: for b = 1..B:
  (a) 从连续 GPD(ξ̂, σ̂) 抽样 n 个值
  (b) 按原始数据的精度离散化（取整 / 舍入到格点）  ← 关键步骤
  (c) 对离散化后的 resample 拟合 MLE-IC → (ξ̂_b, σ̂_b)
  (d) 从 (ξ̂_b, σ̂_b) 计算 VaR_b
Step 3: VaR_b 的经验分位数 → 置信区间
```

与现有 `BootstrapEngine._bootstrap_tail_gpd()` 的结构完全一致（仅替换 naive MLE 为 MLE-IC，并加入离散化步骤）。

#### B. 非参数 Bootstrap + MLE-IC（兼容但次优）

技术上完全可行——MLE-IC 只是一个似然函数，接受任何数据。但每个重抽样中 ties 的模式与原始数据不同，某些重抽样可能触发退化检测。

**更严重的问题**：Schendel & Thongwichian (2017)（*Advances in Water Resources*, Vol. 99, pp. 53–59）系统比较了三种 GPD POT 置信区间方法：

| 方法 | 覆盖率 | 表现 |
|------|--------|------|
| 百分位 Bootstrap | **严重低估**上下界 | ❌ 不推荐 |
| 剖面似然 | 类似但较温和的低估 | ⚠️ 边际 |
| **检验反演 Bootstrap（TIB）** | **合理覆盖，即使在大回归期** | ✅ 最佳 |

百分位 Bootstrap 低估的原因是：它未正确建模 POT 的**双域结构**——超额发生次数（Poisson 过程）和超额幅度（GPD）的变异性被混淆了。这一发现直接挑战了当前 `BootstrapEngine._bootstrap_tail_gpd()` 使用的百分位法。

#### C. 检验反演 Bootstrap（TIB）+ MLE-IC（最严谨，但实现复杂）

Schendel & Thongwichian (2017) 的 TIB 算法：

```
对候选 VaR 值 y*，定义 H₀: VaR(q) = y*
在 H₀ 约束下，GPD 参数被约束为 σ = σ(ξ, y*)（由 VaR 公式反解）
从受限模型生成 Bootstrap 样本
计算检验统计量（Bootstrap VaR 估计）
比较观测统计量与 Bootstrap 分布 → 接受/拒绝 H₀
数值求根搜索 CI 端点
```

**优势**：覆盖率最优（Schendel & Thongwichian 2017）
**劣势**：双层循环（外层求根 + 内层 Bootstrap），B² 次 MLE-IC 拟合，计算成本高

#### 对现有 Bootstrap 计划的影响

当前 `_bootstrap_tail_gpd()` 使用百分位法 CI，Schendel & Thongwichian (2017) 的发现表明这是一个**方法论级别的缺陷**——百分位法在 GPD POT 设定下系统性低估 CI 宽度：

1. **短期修复**：在文档中标注百分位法的已知限制，用户应知悉 GPD-param Bootstrap 的 CI **实际覆盖率低于名义水平**
2. **中期改进**：实现 TIB（检验反演 Bootstrap）替代百分位法。这需要 ~100 行新代码 + 修改 Bootstrap 的 CI 提取逻辑（**已提取到综合计划 B2.9**）
3. **MLE-IC 集成**：仅在 δ/σ 大的场景（B 类边际 GDR）中有价值——对 A 类（δ/σ < 0.002），MLE-IC ≈ naive MLE，集成收益为零

**推荐优先级**：
1. 🔴 **修复百分位法 → TIB**（影响所有 GPD-param Bootstrap CI 的覆盖率）
2. 🟡 **实施 MLE-IC**（仅显著改善 B 类边际 GDR，对 A 类无影响）
3. 🔴 **TIB + MLE-IC 联合**（两个改进正交，可独立实施后组合）

### 2.6 δ/σ 比值在何种池子配置下足够大——场景分析

上述分析的结论是：MLE-IC 仅在 δ/σ > 0.1 时提供有意义的改善。本节分析在何种池子配置下这一条件会被满足。

**关键概念澄清**：
- δ = 离散化间距（整数型 GDR 为 1，有理数比值型 GDR 为 1/分母）
- σ = GPD 尾部尺度参数 β（不是全分布的标准差）
- δ/β 决定离散化偏差的严重程度（Deidda & Puliga 2009）
- **反直觉效应**：模拟次数越多 → 分布越集中 → **δ/β 可能越大**（尾部更「紧」→ 格点间距相对更大）→ 离散化问题更显著

#### 整数型 GDR（A 类主流）

| GDR | δ | 典型 β（尾部尺度） | δ/β | 结论 |
|-----|---|-------------------|------|------|
| `resource_remaining` | 1 | 300~3000 | < 0.003 | **始终可忽略** |
| `resource_consumed` | 1 | 300~3000 | < 0.003 | **始终可忽略** |
| `non_pity_draws` | 1 | 200~2000 | < 0.005 | **始终可忽略** |
| `extra_target` | 1 | 1~5 | 0.2~1.0 | ⚠️ **大**——但 distinct 通常 < 20，EVT 已被跳过 |
| `target_card_draws` | 1 | 5~30 | 0.03~0.2 | **边际**——高值配置时 δ/β 可能 > 0.1 |

**结论**：主流 A 类整数型 GDR（`resource_remaining` 等）的 δ/β < 0.005，**MLE-IC 无实际收益**。唯一的例外是 `target_card_draws`（抽取目标卡的次数）——其尾部尺度较小，在高目标数配置中 δ/β 可能达到 ~0.2。

#### 有理数比值型 GDR（B 类 + C 类）

以 `target_achievement` 为例（值域 k/N，步长 1/N）：

| 目标总量 N | distinct = N+1 | δ = 1/N | 典型尾部 β | δ/β | EVT 状态 | MLE-IC 收益 |
|-----------|---------------|---------|-----------|------|---------|------------|
| N=5 | 6 | 0.200 | 0.08~0.15 | 1.3~2.5 | ❌ 跳过（distinct < 20） | N/A |
| N=10 | 11 | 0.100 | 0.06~0.12 | 0.8~1.7 | ❌ 跳过（distinct < 20） | N/A |
| N=15 | 16 | 0.067 | 0.05~0.10 | 0.7~1.3 | ❌ 跳过（distinct < 20） | N/A |
| **N=20** | **21** | **0.050** | 0.04~0.08 | **0.6~1.3** | ✅ **启用**（distinct ≥ 20） | **显著** |
| **N=30** | **31** | **0.033** | 0.03~0.07 | **0.5~1.1** | ✅ 启用 | **显著** |
| N=50 | 51 | 0.020 | 0.03~0.06 | 0.3~0.7 | ✅ 启用 | 中等 |
| N=100 | 101 | 0.010 | 0.02~0.05 | 0.2~0.5 | ✅ 启用 | 轻微-中等 |

对于其他比值型 GDR：

| GDR | 分母 | δ | 典型场景 | δ/β（distinct ≥ 20） | MLE-IC 收益 |
|-----|------|---|---------|---------------------|------------|
| `target_collection` | K（目标种类数） | 1/K | K=3~10 典型 | K≤10 → δ/β 大但 distinct < 20，EVT 跳过；K≥20 不常见 | 通常 N/A |
| `ssr_collection` | M（SSR 种类数） | 1/M | M=5~20 典型 | M≥20 → distinct=21，δ/β≈0.4-0.8 | **显著**（M≥20 时） |
| `target_achievement` | N（总需求数） | 1/N | N=20~50 常见 | δ/β≈0.3-1.3 | **显著**（N=20-50 时） |

#### 配置场景速查

| 池子配置 | target_achievement 的 N | δ/β 级别 | 建议 |
|---------|------------------------|---------|------|
| 5 目标 × 1 张 | N=5 | N/A（跳过 EVT） | 经验分位数 ✓ |
| 5 目标 × 4 张 | N=20 | **大**（δ/β≈0.6-1.3） | **MLE-IC 推荐** |
| 5 目标 × 7 张 | N=35 | 大（δ/β≈0.4-0.9） | MLE-IC 推荐 |
| 5 目标 × 10 张 | N=50 | 中等（δ/β≈0.3-0.7） | MLE-IC 可选 |
| 10 目标 × 2 张 | N=20 | **大**（δ/β≈0.6-1.3） | **MLE-IC 推荐** |
| 3 目标 × 5 张 | N=15 | N/A（跳过 EVT） | 经验分位数 ✓ |
| 20 SSR × 1 张 | M=20 (ssr_collection) | 大（δ/β≈0.4-0.8） | **MLE-IC 推荐** |

**总结**：MLE-IC **仅在特定池子配置中有显著收益**——主要是 B 类边际 GDR（ratio 型，distinct 刚好 ≥ 20，即 N=20~50 的 `target_achievement` 或 M≥20 的 `ssr_collection`）。对于 A 类主流 GDR，δ/β < 0.005，MLE-IC 无实际价值。**大多数实际配置（5-10 目标类型 × 1-3 副本 = N=5-30）中，target_achievement 的 N 通常 < 20，EVT 已被跳过，所以 MLE-IC 在典型配置下的适用范围进一步缩小。**

*参考文献：Anderson (1970) J. Appl. Prob.; Balkema & de Haan (1974) Ann. Probab.; Pickands (1975) Ann. Statist.; Coles (2001) Springer; Deidda & Puliga (2009) Phys. Chem. Earth; Hitz et al. (2024) J. Data Sci.; Ma et al. (2024); Schendel & Thongwichian (2017) Adv. Water Resour.; Shimura (2012); He et al. (2014) Stat. Interface*

---

## 三、GDR 全量分类与 EVT 适用性

### 3.1 分类维度

| 维度 | 说明 |
|------|------|
| **值域** | 取值区间 |
| **值类型** | 整数 / 有理数 / 实数值 |
| **不同取值数** | 5000 次模拟中预期的不同取值个数（决定 GPD 连续近似的质量） |
| **尾部特征** | 有界 / 指数衰减 / 正态尾 |

### 3.2 A 类：EVT 完全适用（值域广、近似连续）

| # | GDR key | 值域 | 值类型 | 不同取值数 | 尾部特征 |
|---|---------|------|--------|-----------|---------|
| 1 | `resource_remaining` | [0, +∞) | 整数 | 数百~数千 | 有下界，上尾近似正态 |
| 2 | `resource_consumed` | [0, +∞) | 整数 | 数百~数千 | 有下界，上尾近似正态 |
| 3 | `non_pity_draws` | [0, +∞) | 整数 | 数百~数千 | 有下界，上尾近似正态 |
| 4 | `pity_draws` | [0, +∞) | 整数 | 数十~数百 | 混合分布，上尾有界（保底截断） |
| 5 | `resource_efficiency` | [0, 1/成本] | 连续值 | 数百~数千 | 有界 |
| 6 | `resource_per_card` | [0, +∞) | 连续值 | 数百~数千 | 右偏，上尾近似正态 |
| 7 | `weighted_satisfaction` | (-∞, +∞) | 连续值 | 数百~数千 | 近似正态 |
| 8 | `total_card_value` | [0, +∞) | 连续值 | 数百~数千 | 近似正态 |
| 9 | `draw_conversion_efficiency` | [0, +∞) | 连续值 | 数百~数千 | 右偏 |

**处置**：EVT 正常启用。

### 3.3 B 类：EVT 边际适用（有限格点，但有一定分辨率）

| # | GDR key | 值域 | 值类型 | 不同取值数 | 尾部特征 |
|---|---------|------|--------|-----------|---------|
| 10 | `target_achievement` | [0, 1] | 有理数 k/N | 11~101（取决于 N=Σtarget_qty） | 有界 [0,1] |
| 11 | `target_collection` | [0, 1] | 有理数 k/K | K+1（K=目标种类数，通常 3~10） | 有界 [0,1] |
| 12 | `ssr_collection` | [0, 1] | 有理数 k/M | M+1（M=SSR 种类数，通常 5~20） | 有界 [0,1] |
| 13 | `extra_target` | {0,1,2,...} | 整数 | 10~50 | 有下界，上尾衰减 |
| 14 | `target_card_draws` | {0,1,2,...} | 整数 | ~Σtarget_qty | 有下界，上尾衰减 |
| 15 | `per_pool_draw_rate` | [0, +∞) | 有理数 | 数十~数百 | 右偏 |

**处置**：由 `_count_distinct()` 自动判定——≥20 启用 EVT，<20 跳过。对于 `target_achievement`，N = Σ target_specs.values()：
- N=5（5 张 × 1 需求）→ 6 个不同取值 → 跳过 EVT
- N=35（5 张 × 7 需求）→ 36 个不同取值 → EVT 启用
- 典型配置（5-10 张 × 1-3 需求 = N=5-30）→ N≤30 时不同取值数≤31，N≤19 时跳过

### 3.4 C 类：EVT 完全不适用（退化/近退化）

| # | GDR key | 值域 | 不同取值数 | 原因 |
|---|---------|------|-----------|------|
| 16 | `all_targets` | {0, 1} | 2 | 二元 Bernoulli，GPD 拟合无意义 |
| 17 | `weapon_character_ratio` | {0}（当前） | 1 | 配置缺失导致恒为 0，完全退化 |

**处置**：必须跳过 EVT。`weapon_character_ratio` 未来有配置入口后可能不再退化，届时自动检测会重新启用。

### 3.5 已知截断场景（已处理）

`WorstImpactAnalyzer` 资源类 GDR + `condition='success'` 时跳过 EVT（P24 §2.1.1 方案 B）。此逻辑不变。

---

## 四、退化检测与跳过机制

### 4.1 当前已实现的 EVT 跳过条件

当前 `EmpiricalDistribution` 中 EVT 跳过条件分散在多处：

| 检查位置 | 条件 | 跳过行为 |
|----------|------|---------|
| `quantile()` | `use_evt=False` | 直接走经验分位数 |
| `quantile()` | `n < 100` | 不触发 EVT |
| `quantile()` | `p ∈ (0.1, 0.9)` | 非极端分位数，走经验分位数 |
| `_evt_quantile()` | `distinct < 20` | 退化数据，回退经验分位数 |
| `_evt_cvar()` | `distinct < 20` | 退化数据，回退经验 CVaR |
| `fit_gpd_upper()` | `n < 100` | 样本不足，返回 None |
| `fit_gpd_upper()` | `n_exc < 10` | 超额样本不足，返回 None |
| `_fit_gpd()` | `n_exc < 10` | 超额样本不足，返回 None |
| `_fit_gpd()` | ξ < -1 | MLE 不存在（Smith 1985），返回 None |
| `_fit_gpd()` | ξ < -0.5 | MLE 渐近性质不成立，仅警告，点估计仍可用 |
| `evt_var_right()` | `tail_prob > φ` | q 在阈值覆盖范围内，无需外推，返回 None |
| `evt_var_right()` | `var ≥ endpoint`（ξ < 0 有界支撑） | 外推越界，返回 None |

### 4.2 待实施：统一 EVT 适用性判定方法

当前跳过逻辑分散在 4 个方法中（`quantile` / `_evt_quantile` / `_evt_cvar` / `_fit_gpd`），不利于维护和 UI 查询。建议抽取统一的判定方法：

```python
class EmpiricalDistribution:
    _EVT_MIN_SAMPLES = 100       # 触发 EVT 的最小样本数
    _EVT_MIN_DISTINCT = 20       # 触发 EVT 的最小不同取值数
    _EVT_EXTREME_LOW = 0.1       # 下尾极端分位数阈值
    _EVT_EXTREME_HIGH = 0.9      # 上尾极端分位数阈值

    def _evt_applicable(self, p: float) -> Tuple[bool, str]:
        """统一的 EVT 适用性判定。

        Returns:
            (applicable, reason) —— applicable=False 时 reason 说明跳过原因
        """
        if self._n < self._EVT_MIN_SAMPLES:
            return False, f"样本不足（n={self._n} < {self._EVT_MIN_SAMPLES}）"
        if not (p <= self._EVT_EXTREME_LOW or p >= self._EVT_EXTREME_HIGH):
            return False, f"非极端分位数（p={p}）"
        if self._count_distinct() < self._EVT_MIN_DISTINCT:
            return False, f"退化数据（distinct={self._distinct_count} < {self._EVT_MIN_DISTINCT}）"
        return True, "OK"

    @property
    def evt_status(self) -> dict:
        """EVT 状态快照——供 UI 查询。

        Returns:
            {'sample_size': int, 'distinct_count': int,
             'evt_available': bool, 'lower_fitted': bool, 'upper_fitted': bool}
        """
        return {
            'sample_size': self._n,
            'distinct_count': self._count_distinct(),
            'evt_available': self._n >= 100 and self._count_distinct() >= 20,
            'lower_fitted': self._evt_lower is not None,
            'upper_fitted': self._evt_upper is not None,
        }
```

然后在 `_evt_quantile()` 和 `_evt_cvar()` 中统一调用 `_evt_applicable(p)`，消除分散的重复检查。

**改动量**：`distribution.py` ~40 行。

### 4.3 退化检测阈值 < 20 的理论依据

1. **GPD MLE 最小超额样本数**：Hosking & Wallis (1987) 建议至少 20–30 个超额样本。如果整个数据集只有不到 20 个不同取值，尾部 5% 只覆盖 1–2 个不同取值，GPD 拟合完全无意义
2. **经验分位数的精确性**：当不同取值数 < 20 时，格点间距就是分辨率上限。线性插值在两个相邻格点之间内插，并不能提供比格点本身更多的信息——此时经验分位数本身就是精确的
3. **scipy 默认行为**：`scipy.stats.genpareto.fit()` 在超额样本 < 10 时数值不稳定，我们的 `_fit_gpd()` 已设置此下限。不同取值数 < 20 意味着即使全部数据都作为"超额"也不够

### 4.4 已排除的检测方法

| 方法 | 排除理由 |
|------|---------|
| 按 GDR key 逐个标记 | 不如数据驱动检测稳健——不依赖调用方传递正确的 key，新 GDR 自动受益 |
| 基于方差/熵的检测 | 二元数据（如 all_targets {0,1}）方差可能很大（p≈0.5 时），不能有效区分退化 |
| 基于唯一值比例的检测 | 与 `_count_distinct()` 等价但计算更复杂 |
| 直方图分箱数检测 | 依赖分箱参数选择，不稳定 |

---

## 五、EVT 使用状态的 UI 显示

### 5.1 三层显示方案

| 层级 | 位置 | 内容 | 改动量 | 优先级 |
|------|------|------|--------|--------|
| 第一层 | `about_dialog.py` | EVT 说明中追加退化分布自动跳过信息 | ~3 行 | 🔴 立即 |
| 第二层A | `analysis_panel.py` GDR 表格 | VaR/CVaR 被跳过时追加 `†` 标记 + 注脚 | ~10 行 | 🟡 短期 |
| 第二层B | `analysis_panel.py` Tooltip | 鼠标悬停显示 EVT 详细诊断 | ~50 行 | 🟢 按需 |
| 第三层 | 独立 EVT 诊断面板 | 各 GDR 的 EVT 拟合状态矩阵 | 新面板 | ⬜ 暂不实施 |

### 5.2 第一层具体内容

```html
<li><b>退化分布自动跳过</b>：当数据不同取值数 &lt; 20 时（如二元指标 all_targets、
    有限格点指标 target_collection），自动跳过 GPD 拟合，使用经验分位数——
    此时经验分位数本身已精确，EVT 外推无额外收益</li>
```

### 5.3 第二层方案A：VaR/CVaR 单元格标记

- EVT 正常使用：无额外标记（默认行为，用户无需关心）
- EVT 被跳过：值后追加 `†` 符号，表尾注脚说明「† 该指标数据不足或取值过少，VaR/CVaR 使用经验分位数，未经 EVT 外推」

### 5.4 第二层方案B：Tooltip 详细诊断（后续）

鼠标悬停 VaR/CVaR 单元格时显示：
- `"GPD 外推 (ξ=-0.12, n_exc=250)"` — EVT 正常
- `"经验分位数 (distinct=6, 跳过 EVT)"` — 退化跳过
- `"经验分位数 (n=50, 样本不足)"` — 样本不足跳过

---

## 六、尾部估计缺陷（原 P32）

> 来源：`补充模块理论严谨性审查.md` 缺陷 B1/B2/B5/B6

### 6.1 缺陷总览

| # | 缺陷 | 严重度 | 核心问题 |
|---|------|--------|---------|
| B2 | 经验分位数在尾部的不稳定性未被量化 | 🔴 严重 | VaR/CVaR 估计误差可达 ±20%，用户无感知 |
| B1 | BestCaseAnalysis 缺乏理论基础与对称性论证 | 🟡 中等 | 「最好情形」无风险度量文献中的公理化框架对应 |
| B5 | RiskAnalyzer.full_report 同步阻塞 | 🟢 低等 | 不在主流 GUI 路径中使用，实际影响有限 |
| B6 | BestCaseAnalysis 条件顶部无样本量下限 | 🟢 低等 | n<20 时 conditional_top 返回空分布 |

### 6.2 缺陷 B2：经验分位数在尾部的不稳定性未被量化（严重）

**现状**：`WorstCaseAnalysis.cvar(alpha=0.05)` 和 `BestCaseAnalysis.upper_quantile(alpha=0.05)` 直接使用排序样本的经验分位数，无标准误、无 CI。

**理论背景**：经验分位数的渐近方差为：

\[
\text{Var}(quantile(p)) \approx \frac{p(1-p)}{n \cdot f(F^{-1}(p))^2}
\]

其中 f 是密度函数。在尾部（p 接近 0 或 1），f(F⁻¹(p)) 通常较小——分布密度在尾部递减——方差远大于中位数。

**具体影响**（n=1000）：
- α=0.05 → 50 个尾部样本 → CVaR 的 MC 标准误约为 σ_tail/√50 ≈ 0.14 × σ_tail
- α=0.01 → 仅 10 个样本 → CVaR 标准误约为 σ_tail/√10 ≈ 0.32 × σ_tail
- 极端的 CVaR(0.001) → n=1000 时仅 1 个样本——估计完全不可靠

**推荐方案**：

| 层级 | 方案 | 实施位置 |
|------|------|---------|
| 短期 | Bootstrap SE：`cvar()`/`quantile()` 增加可选的 `return_se=True` 参数 | **已提取到综合计划** |
| 中期 | EVT 尾部外推（P24 已完成基础设施） | P24 已集成在 `quantile()`/`cvar()` 中 |
| UI | VaR/CVaR 数值旁显示 CI 或标准误 | **已提取到综合计划** |

> **注**：短期方案（Bootstrap SE）和 UI 展示（CI）已提取到综合计划——它们需要 Bootstrap 引擎的 EVT 路径统一（B2.8）和 TIB（B2.9）作为前置。

*文献：Embrechts, Klüppelberg & Mikosch (1997), *Modelling Extremal Events*; Coles (2001), *An Introduction to Statistical Modeling of Extreme Values*; Serfling (1980), *Approximation Theorems of Mathematical Statistics*; Schendel & Thongwichian (2017)*

### 6.3 缺陷 B1：BestCaseAnalysis 缺乏理论基础（中等）

**现状**：`BestCaseAnalysis` 简单地取 `quantile(1-alpha)` 作为「最好情形」分位数——这只是上分位数的另一个名称。

**理论背景**：
- 下尾风险度量有 VaR/CVaR 的公理化框架支撑（Artzner et al., 1999; Rockafellar & Uryasev, 2000）
- 上尾（高收益侧）缺乏对偶的公理化框架
- 上下尾的统计性质不对称——分布偏度导致同一置信水平下估计精度不同

**推荐方案**：
1. **UI 措辞降级**：将「最好情形分析」改为「乐观情形分析」——「最好」暗示客观最优，「乐观」承认这是基于上分位数的乐观估计
2. **文档补充**：在 `BestCaseAnalysis` 类 docstring 中说明其公理化地位——此分析基于经验上分位数，缺乏下尾 VaR/CVaR 的公理化基础；上分位数的估计方差在偏态分布中可能与同 α 水平的下分位数不对称
3. **长期方向**：若未来有需要，可参考 Prospect Theory 的「收益侧价值函数」（凹的，风险规避）构建更严谨的「乐观情形」度量

*文献：Artzner et al. (1999), *Mathematical Finance*; Rockafellar & Uryasev (2000), *Journal of Risk*; Kahneman & Tversky (1979), *Econometrica* (Prospect Theory)*

### 6.4 缺陷 B5：RiskAnalyzer.full_report 同步阻塞（低等）

`full_report()` 在 GUI 线程中同步计算所有分布的 VaR、CVaR，对 n>5000 可能卡顿 UI。但该函数不在主流 GUI 路径中使用（主流路径使用 QThread Worker）。

**推荐方案**：添加 docstring 警告「此方法同步阻塞，不建议在 GUI 线程调用」。不改变实现。

### 6.5 缺陷 B6：条件顶部无样本量下限（低等）

`conditional_top_alpha(alpha=0.05)` 在 n<20 时返回空分布。n=1000 时仅 50 个样本，在长尾分布中极不稳定。

**推荐方案**：添加 `_low_sample` 标记——若条件子集的样本量 < 50，在返回的 `EmpiricalDistribution` 中标记 `low_sample=True`，UI 可据此显示「低样本量（n=X）」警告。

---

## 七、Bootstrap 对 EVT 的依赖分析

> 本节记录当前两套独立 GPD 拟合的问题诊断，为综合计划 B2.8/B2.9 提供理论前置。
> 具体代码改动方案已提取到综合计划，此处仅保留问题陈述与数据流设计。

### 7.1 当前状态：两套独立的 GPD 拟合

Bootstrap 和 EVT 各自维护了独立的 GPD 拟合代码路径：

| 组件 | 文件 | GPD 拟合方式 | 退化检测 |
|------|------|-------------|---------|
| EVT 核心 | `evt_tail.py` | `scipy.stats.genpareto.fit()` + MLE 正则性检查 | 无（依赖调用方的 `_count_distinct()` 守卫） |
| Bootstrap GPD | `bootstrap.py:205-236` | 直接 `genpareto.fit(-excess, floc=0)` | 仅 `len(excess) < 20` 检查 |
| EmpiricalDistribution | `distribution.py` | 委托给 `evt_tail.py` | `_count_distinct() < 20` |

**问题**：

1. **重复实现**：`_bootstrap_tail_gpd()` 重新实现了 GPD 拟合逻辑（`genpareto.fit(-excess, floc=0)`），而不是复用 `evt_tail.fit_gpd_lower()`
2. **退化检测不一致**：Bootstrap 的 GPD 路径没有 `_count_distinct()` 检查，只检查了超额样本数。binary 数据的 Bootstrap 重抽样可能产生全是 0 或全是 1 的 resample，GPD 拟合在这些退化 resample 上会静默失败
3. **ξ<-1 正则性检查缺失**：Bootstrap 路径没有 `evt_tail._fit_gpd()` 中的 Smith (1985) MLE 正则性条件检查
4. **阈值策略不同**：EVT 核心使用自适应阈值（100-500 超额样本），Bootstrap 使用固定 q=0.2 阈值——不一致的阈值可能导致 VaR 点估计和 Bootstrap CI 的系统性偏差

### 7.2 统一后的数据流设计

```
BootstrapEngine._bootstrap_tail_gpd(data, q=0.05)
  │
  ├─ EmpiricalDistribution._count_distinct()  ← 退化检测（本计划 §四）
  │   └─ distinct < 20 → 回退标准百分位法 Bootstrap
  │
  └─ for b in 1..B:
       ├─ resample = data[rng.choice(n, n)]
       │
       ├─ evt_tail.fit_gpd_lower(resample)    ← 统一 GPD 拟合（P24）
       │   ├─ _fit_gpd(exceedances)            ← MLE + 正则性检查
       │   └─ 失败 → 回退该 resample 的经验分位数
       │
       ├─ evt_tail.evt_var_right(q_Y, ξ, β, u_Y, φ)  ← 统一 VaR 公式（P24）
       └─ VaR_X = -VaR_Y
```

### 7.3 对 Bootstrap 计划的影响

基于以上分析，原 P25 提出 B2.8（EVT 拟合路径统一）和 B2.9（TIB 替代百分位法 CI）两个新增条目。这两个条目已提取到综合计划。另外 B3.0（VaR CI 从「待实现」升级为可用）也一并提取——P24 已实现 EVT 核心，B2.8 完成后 VaR 的参数 GPD Bootstrap CI 即可正式启用（附带百分位法已知限制的警告）。

---

## 八、DGPD「几十行代码」可行性评估

### 8.1 背景与数学定义

有人声称「使用 DGPD 只需要几十行代码」。本节评估这一声称的真实性。

离散广义 Pareto 分布（DGPD）通过离散化连续 GPD 构造：

\[
P(X = k) = F_{\text{GPD}}(k+1; \xi, \sigma) - F_{\text{GPD}}(k; \xi, \sigma)
\]

其中 \(F_{\text{GPD}}(x) = 1 - (1 + \xi x/\sigma)_{+}^{-1/\xi}\) 是连续 GPD 的 CDF。

### 8.2 最小可行实现（~25 行）

使用 `scipy.stats.genpareto.cdf()` + `scipy.optimize.minimize()` 确实可以在 ~25 行内实现 DGPD 的 MLE 拟合：

```python
import numpy as np
from scipy.stats import genpareto
from scipy.optimize import minimize

def _dgpd_nll(params, excesses):
    """DGPD 负对数似然。"""
    xi, sigma = params
    if sigma <= 0:
        return np.inf
    cdf_hi = genpareto.cdf(excesses + 1, xi, scale=sigma)
    cdf_lo = genpareto.cdf(excesses, xi, scale=sigma)
    pmf = cdf_hi - cdf_lo
    pmf = np.clip(pmf, 1e-300, None)
    return -np.sum(np.log(pmf))

def fit_dgpd(excesses):
    """拟合 DGPD(ξ, σ) 到整数超额值。"""
    shape_init, _, scale_init = genpareto.fit(excesses, floc=0)
    res = minimize(
        _dgpd_nll, x0=[shape_init, scale_init],
        args=(excesses,), method='Nelder-Mead',
        bounds=[(-2.0, 5.0), (1e-6, None)],
    )
    if res.success:
        return res.x[0], res.x[1]
    return None
```

**行数**：~25 行（含空行和注释）。声称「几十行代码」在技术上是正确的。

### 8.3 成熟库调查

| 库/语言 | DGPD 支持 | 说明 |
|---------|----------|------|
| **scipy** (Python) | ❌ 无 | 仅有连续 `genpareto`，无离散版本 |
| **scipy.stats** 全部离散分布 | ❌ 无 | 含 Poisson/NB/ZIP 等 30+ 离散分布，无 DGPD |
| **statsmodels** (Python) | ❌ 无 | 含离散选择模型、计数回归，无 EVT 离散分布 |
| **R `mev` 包** | ⚠️ 边际 | 含 GPD 拟合工具，无独立 DGPD 函数 |
| **R `extRemes`** | ❌ 无 | 极值分析主流 R 包，无 DGPD |
| **R `VGAM`** (Vector GLM) | ⚠️ 可能 | 通过自定义族函数可能间接支持，但无现成 DGPD 族 |

**结论：Python 生态中没有任何成熟库提供 DGPD 的 MLE 拟合或分布函数。R 生态中也没有独立、成熟的 DGPD 包。**

### 8.4 隐藏的复杂性与风险

上述 25 行「最小可行实现」与生产级代码之间存在显著差距：

| 问题 | 最小实现 | 生产级需求 |
|------|---------|-----------|
| **数值稳定性** | `np.clip(pmf, 1e-300, None)` 粗暴截断 | 需 log-space 计算：`log(F(k+1) - F(k))` 通过 `log1p` / `logsumexp` 避免灾难性抵消 |
| **MLE 收敛** | 单起点 Nelder-Mead | 需多起点（~5 个不同初始值）+ BFGS/L-BFGS-B 梯度方法，避免局部最优 |
| **边界 ξ 的 MLE 行为** | 无处理 | ξ < -1 时 MLE 不存在（Smith 1985） |
| **标准误计算** | 无 | 需 Hessian 逆矩阵或 Bootstrap 计算参数不确定性 |
| **拟合优度检验** | 无 | 需 χ² 或离散 KS 检验判断 DGPD 是否适合数据 |
| **小样本行为** | 未知 | n < 30 时 MLE 偏差大，需偏差校正或贝叶斯方法 |
| **VaR/CVaR 反演** | 无 | 从 DGPD 参数反演 VaR 需要求根（DGPD 的 CDF 无解析逆函数） |

**保守估计**：一个可靠的 DGPD 实现（含数值安全 + 多起点优化 + 正则性检查 + 拟合优度 + VaR 反演）需要 **150-250 行**，且需要深入的 EVT 领域知识进行验证。

### 8.5 连续性校正替代方案

对于值域较大（≥20 不同取值）的离散数据，更实用的方案是加**连续性校正**，而非实现完整 DGPD：

```python
def _evt_var_discrete(q, xi, beta, u, phi):
    """带连续性校正的离散 EVT VaR。"""
    var_continuous = evt_var_right(q, xi, beta, u, phi)
    if var_continuous is None:
        return None
    return np.floor(var_continuous + 0.5)
```

但即使是这个方案，**在当前场景下的收益也极微**——不同取值数 ≥ 20 时，连续 GPD 的近似误差已小于 Bootstrap CI 宽度；不同取值数 < 20 时，经验分位数本身就是精确的。

### 8.6 三种方案最终对比

| | 连续 GPD + 回退（当前） | D-GPD | MLE-IC |
|---|---|---|---|
| 理论严谨性 | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 数值性能 | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 可实现性 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| 与现有代码兼容 | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐ |

### 8.7 结论与建议

| 维度 | 评估 |
|------|------|
| 「几十行代码」声称 | **技术上正确**——~25 行可实现基本 DGPD MLE |
| 成熟 Python 库 | **不存在**——scipy/statsmodels 均无 DGPD 支持 |
| 生产级可靠性 | **不可行**——需要 150-250 行 + 深入领域知识 |
| 对当前项目的收益 | **极低**——distinct <20 时经验分位数已精确，≥20 时连续 GPD 近似已足够 |
| 可维护性成本 | **高**——团队需维护一个无社区参考实现的非标准统计方法 |

**决策**：
1. **不引入 DGPD**——当前「distinct < 20 跳过 EVT + distinct ≥ 20 连续 GPD」策略在理论和工程上足够稳健
2. **不引入连续性校正**——同理，收益不足以覆盖新增代码的维护成本
3. **不实施 MLE-IC**——仅在 B 类边际 GDR（N=20~50 的 `target_achievement`、M≥20 的 `ssr_collection`）中有显著收益，且当前这些场景的 distinct < 20 时 EVT 已被跳过
4. **如果未来有明确的用户反馈**（如某个 GDR 的 VaR EVT 估计与经验分位数偏差显著且无法用 Bootstrap 解释），再重新评估

*参考文献：Hitz et al. (2024) J. Data Sci.; Krishna & Pundir (2009); Prieto et al. (2014); Ma et al. (2024); Smith (1985) Biometrika*

---

## 九、与 P24 的关系

| 维度 | P24（已实现） | 本计划 |
|------|-------------|--------|
| 目标 | EVT 尾部拟合基础集成 | 修正 EVT 对退化/离散分布的错误适用 + UI 显示 + 尾部缺陷修复 + Bootstrap 路径诊断 |
| 改动范围 | `core/evt_tail.py`（新建）+ `distribution.py` + `worst_impact.py` | `distribution.py`（+40 行 `_evt_applicable` + ~15 行 low_sample）+ `risk_analysis.py`（~3 行）+ `gui/about_dialog.py`（~3 行）+ `gui/analysis_panel.py`（~12 行） |
| 测试 | 30 项（test_evt_tail + test_distribution） | 已有 7 项退化检测测试 + 新增 `_evt_applicable` 测试 + low_sample 测试 |
| 风险 | 低（回退机制完善） | 低（仅增加回退条件 + UI 标注，不改变已启用 EVT 的核心逻辑） |

---

## 十、实施路线

### 10.1 已实施 ✅

- [x] `_count_distinct()` 惰性计算 + 缓存
- [x] `_evt_quantile()` 和 `_evt_cvar()` 中 distinct < 20 守卫
- [x] EVT 核心（`evt_tail.py` 全量 + `EmpiricalDistribution` 集成）
- [x] 30 项 EVT 测试 + 7 项退化检测测试

### 10.2 阶段一：UI 透明化 + 低等缺陷修复（预计 0.5 天）

| # | 任务 | 文件 | 行数 |
|---|------|------|------|
| 1.1 | BestCase→乐观情形 措辞 | `analysis_panel.py` | ~2 |
| 1.2 | BestCaseAnalysis docstring 公理化地位说明 | `distribution.py` | ~10 |
| 1.3 | full_report docstring 同步阻塞警告 | `risk_analysis.py` | ~3 |
| 1.4 | conditional_top/conditional_tail `low_sample` 标记 | `distribution.py` | ~15 |
| 1.5 | about_dialog EVT 退化跳过说明（§五.2） | `about_dialog.py` | ~3 |
| 1.6 | GDR 表格 VaR 退化标记 `†` + 注脚（§五.3） | `analysis_panel.py` | ~10 |

**改动量**：~45 行，分散在 4 个文件。

### 10.3 阶段二：统一 EVT 适用性判定（预计 1 天）

| # | 任务 | 文件 | 行数 |
|---|------|------|------|
| 2.1 | `_evt_applicable(p)` 方法 | `distribution.py` | ~20 |
| 2.2 | `evt_status` property | `distribution.py` | ~15 |
| 2.3 | `_evt_quantile()`/`_evt_cvar()` 改为调用 `_evt_applicable()` | `distribution.py` | ~10 |
| 2.4 | 更新/新增测试 | `test_distribution.py` | ~20 |

**改动量**：~65 行。

### 10.4 已提取到综合计划

以下项涉及 `bootstrap.py` 的跨模块改动，已提取到「Bootstrap-EVT 统一与尾部 CI 实施计划」：

| 原项 | 内容 | 理由 |
|------|------|------|
| P25 B2.8 | `_bootstrap_tail_gpd()` 委托 `evt_tail`（~30 行） | 跨 `bootstrap.py` ↔ `evt_tail.py` |
| P25 B2.9 | 百分位法 → TIB CI 构造（~120 行） | 纯 `bootstrap.py` 改动，依赖 B2.8 |
| P32 阶段二 | `cvar()`/`quantile()` 的 `return_se` + GPD 尾部委托（~60 行） | 需要 Bootstrap 引擎稳定 |

### 10.5 不实施

- [ ] DGPD 实现（理由见 §八.7）
- [ ] 连续性校正（理由见 §八.5）
- [ ] MLE-IC 拟合路径（仅在 B 类边际 GDR 中有收益，δ/σ<0.002 场景无价值，见 §二.4-§二.6）
- [ ] 独立 EVT 诊断面板（优先级低，暂不实施）
- [ ] 第二层方案B Tooltip 详细诊断（按需，暂不实施）

---

## 十一、测试策略

### 11.1 退化检测（已有）

| 测试 | 说明 |
|------|------|
| `all_targets`（二元）→ `quantile(0.05)` 走经验分位数 | 验证 distinct=2 跳过 EVT |
| `weapon_character_ratio`（退化）→ 不走 EVT | 验证 distinct=1 跳过 EVT |
| `target_collection`（<20 distinct）→ 不走 EVT | 验证有限格点跳过 |
| `resource_remaining`（≥20 distinct）→ 正常走 EVT | 验证正常路径不受影响 |
| 不同取值数惰性计算 + 缓存 | 验证不重复遍历 |

### 11.2 EVT 适用性判定（阶段二新增）

| 测试 | 说明 |
|------|------|
| `_evt_applicable(p)` 各跳过条件 | 验证 n<100 / 非极端 p / distinct<20 三种跳过 |
| `evt_status` property 正确性 | 验证各字段与实际状态一致 |
| `_evt_quantile()` 统一走 `_evt_applicable()` | 回归——已有退化检测行为不变 |

### 11.3 尾部缺陷修复（阶段一新增）

| 测试 | 说明 |
|------|------|
| `low_sample` 标记触发 | n=5/20/50/100 的 conditional_top 标记正确性 |
| BestCaseAnalysis docstring | 目视确认公理化说明 |
| full_report docstring | 目视确认阻塞警告 |

### 11.4 Bootstrap SE + GPD 尾部委托（已提取到综合计划）

| 测试 | 说明 |
|------|------|
| Bootstrap SE 正确性 | 已知分布（正态/指数）的 cvar SE 与解析值对比 |
| GPD 尾部委托 | 厚尾分布（Pareto）的极端分位数精度对比（经验 vs GPD） |
| 退化分布跳过 EVT | 利用本计划的退化检测 |

---

## 十二、验收标准

### 退化检测（已有）
- [ ] `all_targets`（二元）分布上调用 `quantile(0.05, use_evt=True)` → 走经验分位数，不走 EVT
- [ ] `weapon_character_ratio`（退化）分布 → 不走 EVT
- [ ] `target_collection`（< 20 不同取值）分布 → 不走 EVT
- [ ] `resource_remaining`（> 20 不同取值）分布 → 正常走 EVT
- [ ] 不同取值数检查惰性计算 + 缓存，不重复遍历

### EVT 适用性判定（阶段二）
- [ ] `_evt_applicable(p)` 统一返回 `(bool, reason)`
- [ ] `evt_status` property 提供完整 EVT 状态快照
- [ ] `_evt_quantile()` 和 `_evt_cvar()` 通过 `_evt_applicable()` 而非分散检查

### UI 透明化（阶段一）
- [ ] BestCase→乐观情形 措辞更新
- [ ] BestCaseAnalysis docstring 含公理化地位说明
- [ ] full_report docstring 含同步阻塞警告
- [ ] `low_sample` 标记在条件子集 n<50 时触发
- [ ] about_dialog EVT 说明含退化分布自动跳过信息
- [ ] GDR 表格退化指标 VaR 值附带 `†` 标记 + 注脚

### Bootstrap 统一（已提取到综合计划，此处仅记录）
- [ ] 本计划 §七 的问题诊断与数据流设计被综合计划引用
- [ ] MLE-IC + TIB 的理论分析（§二.4-§二.5）被综合计划引用

### 回归
- [ ] 全部已有测试保持绿色
- [ ] EVT 30 项 + 退化检测 7 项测试通过

---

## 更新记录

| 日期 | 变更 |
|------|------|
| 2026-06-13 | **合并 P25+P32**：统一 EVT 适用性理论 + 尾部估计缺陷修复为单一文档。保留全部文献审查、δ/σ 分层分析、MLE-IC/Bootstrap 兼容性分析、DGPD 评估。提取 B2.8/B2.9/P32阶段二到综合计划。重写实施路线为两阶段。 |
| 2026-05-28 | P25 原版 v4：理论严谨性审查——Anderson (1970) 离散化破坏 MDA + Hitz et al. (2024) D-GPD vs GZD vs 连续 GPD + Deidda & Puliga (2009) 舍入偏差 Monte Carlo + Ma et al. (2024) MLE-IC；三层方案对比；δ/σ 分层可靠性评估；DGPD 代码可行性评估 |
| 2026-05-29 | P32 原版：补充模块理论严谨性审查——4 项理论缺陷（B1/B2/B5/B6）+ 两阶段实施路线 |
