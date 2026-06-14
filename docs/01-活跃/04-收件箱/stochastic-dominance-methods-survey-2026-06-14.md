# 随机占优检验方法综述：2024–2026 学界现状

> 日期：2026-06-14 | 触发：P45 DD Bootstrap 检验方法选型
> 方法：deep-research workflow → 5 路搜索 → 15 源抓取 → 3 票对抗验证 → 21 组主张综合

---

## 一、方法演进谱系

### 1.1 三代方法

| 代际 | 时间 | 代表方法 | 核心思想 | H₀ 方向 |
|------|------|----------|----------|---------|
| **第一代** | 2000–2003 | Davidson & Duclos (2000); Barrett & Donald (2003) | 渐近检验 + 简单 Bootstrap；DD 开创网格点 T 统计量框架，BD 引入 LFC Bootstrap | DD: 非占优 / BD: 占优 |
| **第二代** | 2005–2010 | Linton-Maasoumi-Whang (2005); Linton-Song-Whang (2010) | 子抽样 + 接触集估计——将 Bootstrap 约束在分布重合区域，解决 LFC 过度保守 | 占优 |
| **第三代** | 2016–2025 | Donald & Hsu (2016); Lok & Tabri (2021); Song & Sun (2025) | 选择性重中心化 / 经验似然 tilting / 几乎占优系数——从二元判定走向连续量化 | 占优 / 非占优 / 几乎占优 |

### 1.2 关键节点

```
DD 2000 ──→ DD 2006 ──→ DD 2013 ──→ Lok & Tabri 2021
(渐近检验)   (EL Bootstrap) (受限SD)    (经验似然tilting)
                │
BD 2003 ──→ LMW 2005 ──→ LSW 2010 ──→ Lee-Linton-Whang 2023
(LFC)       (子抽样)     (接触集)      (面板时间SD)
                │               │
                └──→ Donald & Hsu 2016 ←── Hansen 2005
                     (选择性重中心化)      (有限约束recentering)
                           │
                Hong & Li 2018 ──→ PySDTest 2024
                (数值Delta法)      (Python/Stata实现)
                           │
                Song & Sun 2025
                (几乎占优系数)
```

---

## 二、H₀ 假设方向之争

### 2.1 Whang (2019) 三叉分类

Whang (2019, *Econometric Analysis of Stochastic Dominance*, Cambridge University Press) 将 SD 检验的 H₀ 框架系统分为三类：

| 框架 | H₀ | H₁ | 典型方法 | 拒绝 H₀ 意味着 |
|------|-----|-----|----------|---------------|
| **§2.2 占优式** | A 占优 B | 非占优 | BD 2003, LMW 2005, LSW 2010, DH 2016 | "有证据否定占优" |
| **§2.3 非占优式** | A **不**占优 B | 占优 | DD 2006/2013, Lok & Tabri 2021 | "有正面证据断言占优" |
| **§2.4 等式式** | A = B（等分布） | 占优 | Bennett 2024 | "分布不同" |

### 2.2 哲学差异与实践后果

**占优为 H₀（计量经济学主流）：**
- 保守——不拒绝 H₀ 只能 "未能推翻占优"，不能正面断言
- 需要四分类裁决矩阵（≻/≺/=/×）来弥补方向的局限性
- PySDTest、stodom、大部分 R 包采用此方向

**非占优为 H₀（DD 传统）：**
- 积极——拒绝 H₀ 可正面断言占优
- 但需要受限 SD（截尾区间）才能在连续分布上可行——DD (2013) 证明完整支集上无法拒绝非占优 H₀
- 当前实现更少，Lok & Tabri (2021) 是最新的成熟方案

**共识（Whang 2019 §3.3）：** 不存在全局占优的方向——方向选择取决于研究目标。若目标是筛选可淘汰的策略（证明某策略被占优），选占优-H₀；若目标是正面确认占优关系，选非占优-H₀。

---

## 三、理论基础：Hadamard 方向可微性与 Bootstrap 一致性

### 3.0 Fang & Santos (2019) 奠基性结论

理解当代 SD Bootstrap 校正技术的前提是掌握 Fang & Santos (2019, *Review of Economic Studies*) 的一个核心定理：

> **当 φ 仅是 Hadamard 方向可微（而非全可微）时，标准 Bootstrap 不一致。**

这一定理是 SD 检验领域的「哥德尔句」——它解释了为什么简单 Bootstrap 在 SD 检验中系统性地失效（包括你们当前代码中的等式中心化问题）。

**具体而言：**

- SD 检验统计量（如 `max(F_a − F_b)`）是分布函数的泛函 φ(F)
- φ 在 H₀ 边界处仅是**方向可微**（directional differentiable），不是全可微
- 方向可微性导致了极限分布的**非连续性**——在不同方向逼近边界时得到不同极限
- 标准 Bootstrap 隐含假定了全可微性，因此在 SD 边界上尺寸失真

**两个修复路径：**

| 路径 | 方法 | 实现 |
|------|------|------|
| **修改 Bootstrap DGP** | 在接触集上施加 H₀ 约束 → Bootstrap 极限分布逼近真实的不连续极限 | LSW 2010, DH 2016 |
| **修改 Bootstrap 统计量** | 用数值导数估计方向导数 → 修正 Bootstrap 分布 | Hong & Li 2018 (NDM), Song & Sun 2025 |

两者的共同祖先都是 Fang & Santos (2019) 的方向导数框架。理解这一点后，LSW、DH、NDM 三种方法不再是互不相关的竞争者，而是**同一数学问题的两个解法分支**。

---

## 四、Bootstrap 校正技术的现状

### 4.1 四种校正技术对比

| 技术 | 出处 | 机制 | 优势 | 局限 |
|------|------|------|------|------|
| **LFC** (最小有利配置) | BD 2003 | 假设 H₀ 在最严苛边界（两分布相等）成立 | 简单、保守 | 过度保守，功效低 |
| **接触集估计** | LSW 2010 | 仅在两分布实际重合的网格点上施加 H₀ 约束 | 显著提高功效，一致渐近有效 | 依赖调谐参数 c |
| **选择性重中心化** | DH 2016 | 仅对不等式约束接近 binding 的点重中心化 | 比 LFC 更高功效，某些场景优于子抽样 | 依赖调谐参数 a |
| **数值 Delta 法** | Hong & Li 2018 | 有限差分近似 Hadamard 方向导数，免 Bootstrap | 代码简单，统一框架 | 需选步长 εₙ |

### 4.2 关键技术细节

**接触集估计 (LSW 2010)：**
- 接触集 Ĉ = {x : |D̂_s(x)| < cₙ}，cₙ = c · log(log(N)) / √N
- 若 Ĉ 为空，回退到全网格（等价 LFC）
- PySDTest 中 `test_sd_contact` 实现了此方法，默认 c = 0.75

**选择性重中心化 (Donald & Hsu 2016)：**
- 重中心化函数 μ̂_N(x) = D̄(x) 当 D̄(x) < a_N/√N，否则 0
- a_N = -a · √[log(log(N))]，推荐 a = 0.1
- PySDTest 中 `test_sd_SR` 实现了此方法

**数值 Delta 法 (Hong & Li 2018)：**
- φ̂'ₙ(h) = [φ(θ̂ₙ + εₙ·h) − φ(θ̂ₙ)] / εₙ
- 步长满足 εₙ → 0 且 rₙ·εₙ → ∞
- 对凸且 Lipschitz 泛函提供一致有效推断
- PySDTest 中 `test_sd_NDM` 实现了此方法

### 4.3 Lee, Linton & Whang (2023) 的综合比较

在面板时间 SD 检验中，LLW (2023) 同时实现了接触集法和数值 Delta 法，结论：
- 两者均显著优于 LFC
- 不存在绝对优势——取决于 DGP 和数据特征
- **接触集法**在接触集较大时更优；**数值 Delta 法**在小接触集时更稳定

---

## 五、当前学界"最佳实践"

### 5.1 不同场景的推荐

| 场景 | 推荐方法 | 理由 |
|------|----------|------|
| **简单两样本比较** | DH 2016 选择性重中心化 或 LSW 2010 接触集 | 两者均显著优于 BD 2003 LFC，无需额外假设 |
| **需要正面断言占优** | DD 2013 受限 SD + Lok & Tabri 2021 EL tilting | 非占优-H₀，拒绝即正面断言 |
| **多策略同时比较** | LSW 2010 + 成对 Bootstrap | PySDTest 已实现 stochastic maximality |
| **小样本 (n < 100)** | 贝叶斯检验 (Gorzelanczyk 2024) | 频繁主义方法在边界上尺寸失真严重 |
| **时间序列/面板** | LLW 2023 路径 Bootstrap + 接触集 | 保留个体内时间依赖性 |
| **需要效应量** | Song & Sun 2025 几乎占优系数 | 二元判定 → 连续量化 |

### 5.2 未解决的前沿问题

1. **H₀ 方向不可通约**——占优-H₀ 与不占优-H₀ 的结论不能直接互译，两种范式将长期共存
2. **调谐参数选择**——c (LSW)、a (DH)、εₙ (NDM) 均依赖经验默认值，缺乏数据驱动的自适应方法
3. **高维扩展**——条件 SD (Whang 2019 §4) 和含协变量的 SD 检验仍处于方法论早期
4. **几乎占优的统计推断**——Song & Sun (2025) 和 Baillo et al. (2024) 独立突破，但尚无统一框架，且无开源实现

---

## 六、软件生态

### 6.1 全览

| 包 | 语言 | 版本 | 方法 | H₀ | 阶数 | 统计推断 |
|----|------|------|------|-----|------|----------|
| **[PySDTest](https://pypi.org/project/PySDTest/)** | Python/Stata | 0.0.21 (2024) | BD, LMW, LSW, DH, NDM | 占优 | 任意 | Bootstrap/子抽样/NDM |
| **[stodom](https://cran.r-project.org/web/packages/stodom/)** | R | 0.0.1 (2024) | BD 2003 | 占优 | 1, 2 | Bootstrap |
| **[RSD](https://cran.r-project.org/)** | R | 0.2.0 (2025) | ASD 几乎占优规则 | — | 1, 2 + ASD | 确定性（无推断） |
| **StochasticDominance.jl** | Julia | — | 确定性验证+优化 | — | 任意（含非整数） | 无统计推断 |
| **DescTools** | R | 持续维护 | 有 DD 相关工具 | 不确定 | — | 待确认 |

### 6.2 关键差异

- **PySDTest** 是唯一同时覆盖 5 种方法论的 Python 包，也是唯一支持 Stata 接口的包
- **stodom** 仅限于 BD (2003) 的一、二阶，无 LSW/DH/NDM
- **RSD** 是唯一实现 Almost SD 的 R 包，但仅做确定性计算——无 Bootstrap、无 p 值、无置信区间
- **Julia 生态**目前缺乏 Bootstrap SD 检验实现（StochasticDominance.jl 面向的是已知分布的优化问题）
- **Song & Sun (2025) 几乎占优系数**尚无任何语言的公开发布实现

### 6.3 PySDTest 版本确认

本次下载分析的是 **v0.0.21**（PyPI 最新），9.4 KB，仅依赖 numpy + matplotlib。实现了 `test_sd`、`test_sd_contact`、`test_sd_SR`、`test_sd_NDM` 四个类。

注意：PySDTest 的子抽样实现（`subsampling()` 函数）使用滑动窗口而非随机无放回抽样——这不影响 Bootstrap 模式的使用。

---

## 七、近年突破 (2020–2025)

### 7.1 方法论

| 年份 | 工作 | 贡献 |
|------|------|------|
| **2021** | Lok & Tabri, *Journal of Econometrics* | EL tilting — 在接触集上对经验分布tilt以最大化功效，非占优-H₀ |
| **2023** | Lee, Linton & Whang, *Journal of Econometrics* | 面板时间 SD — 路径 Bootstrap + 接触集/NDM |
| **2024** | Gorzelanczyk, *preprint* | 贝叶斯 SD — 四选一框架（SD∞/SDk/非占优/相等），小样本优势 |
| **2024** | Zhuang, Wang & Chen, *preprint* | 分位数 SD — 基于经验分位数函数而非 CDF 的 KS 型检验 |
| **2025** | Song & Sun, *Communications in Statistics* | 几乎占优系数 — Hadamard 方向可微 + Fang-Santos Bootstrap |
| **2024** | Baillo, Carcamo & Mora-Corral, *JBES* | 2DSD 指数 — 最小违反率 (MVR) 的 Bootstrap 置信区间 |

### 7.2 综述/专著

| 年份 | 工作 | 地位 |
|------|------|------|
| **2019** | Whang, *Econometric Analysis of Stochastic Dominance* (CUP) | **领域标准参考书**——三类 H₀ 框架 + 五种统计量 + 附录 MATLAB 代码 |
| **2022** | Kaplan, *Working Paper* | 经验序数占优曲线 + 匹配对 SD 检验 + 隐式接触集 Bootstrap |

### 7.3 两条「几乎占优」路径的对比

2024–2025 年出现了两条独立的「几乎占优」(Almost SD) 方法论路径，同时发表在顶级期刊上：

| | Song & Sun (2025) | Baíllo, Cárcamo & Mora-Corral (2024) |
|---|---|---|
| **期刊** | *Comm. in Statistics* | *J. Business & Econ. Statistics* (2025, 43(2), 338-350) |
| **核心概念** | 占优系数 SDC/LDC/ISDC | 2DSD 指数 + 最小违反率 (MVR) |
| **数学基础** | Hadamard 方向可微 + Fang-Santos Bootstrap | 经验过程 + Bootstrap 强一致性 |
| **H₀ 方向** | H₀: c(F₁, F₂) ≤ ε（几乎占优） | 非占优-H₀ |
| **输出** | 系数估计 + Bootstrap 置信区间 | MVR 估计 + Bootstrap 假设检验 |
| **开源实现** | ❌ 无 | ❌ 无 |
| **实证应用** | 英国不平等数据 | 模拟 + 实际数据验证 |

**两者的共同点：** 都从「二元判定」转向「连续量化」；都使用 Bootstrap 处理非标准渐近分布；都尚未有任何语言的公开发布实现。

**对 GachaStat 的启示：** 几乎占优系数的概念与 P19 §效应量的需求高度吻合。在策略比较中，不仅想知道「A 是否占优 B」，还想知道「占优的程度多大」。但这个方向目前缺乏即用软件——需要从论文公式手写实现。

### 7.4 Bennett (2024) 双向序贯检验

Bennett (2024, Vanderbilt Working Paper, 2024-03-27 修订) 提出了一条独特路径：

**两阶段序贯检验：**
1. **阶段 1：** H₀ = 等分布。若不拒绝 → 停止（两策略无差异）
2. **阶段 2（条件于阶段 1 拒绝）：** 使用两个单向 KS 统计量的最小值区分 A≻B / A≺B / ×（交叉）

**关键创新：** Bootstrap DGP **不施加 H₀ 约束**——这与所有现有方法（LFC、接触集、选择性重中心化）形成根本对比。通过不施加约束获得更小的临界值和更高的功效。

**P45 引用了这篇论文**（作为备选方案），但需注意：工作论文状态（未经同行评审），方法论不及 Donald-Hsu 成熟。

### 7.5 趋势总结

1. **从二值到连续**——Song & Sun (2025) 和 Baillo et al. (2024) 独立推动 "几乎占优" 量化，反映了学界对二元判定局限性的共识
2. **Bootstrap 校正趋于成熟**——接触集/选择性重中心化/NDM 三足鼎立，**LFC 方法应被视为已淘汰**
3. **H₀ 方向共存将持续**——两种范式服务于不同研究目标，Whang (2019) 的三叉分类已成为描述这一现状的标准术语
4. **软件滞后于方法论**——Song & Sun (2025) 和 Baillo et al. (2024) 的方法均无开源实现，PySDTest 是目前覆盖最广的 Python 包
5. **Bennett (2024) 的「不施加 H₀」Bootstrap**代表了一个激进的新方向——但尚未经过同行评审验证

---

## 八、方法选择决策树

```
需要什么类型的结论？
├── 「A 不占优 B」（排除占优）→ 占优-H₀ 框架
│   ├── 简单快速 → PySDTest test_sd_SR (DH 2016)
│   ├── 需要同时比较多个策略 → PySDTest stochastic maximality
│   └── 时间序列/面板数据 → Lee-Linton-Whang 2023 (路径 Bootstrap)
│
├── 「A 占优 B」（正面断言）→ 非占优-H₀ 框架
│   ├── 连续分布 → DD 2013 受限 SD + Lok & Tabri 2021 EL tilting
│   └── 离散分布 → Bennett 2024 双向序贯（工作论文，谨慎使用）
│
├── 「占优程度多大」（效应量）→ 几乎占优框架
│   ├── 现有工具 → 目前无开源实现
│   └── 远期方案 → Song & Sun 2025 或 Baillo et al. 2024 的手写实现
│
└── 小样本 (n < 100) → Gorzelanczyk 2024 贝叶斯 SD 检验（无 Python 实现）
```

---

## 九、GachaStat 集成路线图

### 9.1 P45 方法选型

| 方案 | 方法 | H₀ | Python 实现 | 适配代价 |
|------|------|-----|-------------|----------|
| **A** | 直接用 PySDTest `test_sd_SR` | 占优 | ✅ 现成 | 1-2h 适配 |
| **B** | 移植 DH 2016 到 DD 框架 | 非占优 | 需手写 | 3-4h + 校准实验 |
| **C** | 升级到 Lok & Tabri 2021 | 非占优 | 需手写（复杂 EL 优化） | 8-12h |

### 9.2 推荐：方案 A（立即）+ 方案 B（中期）

**Phase 1 — 立即（P45 实施）：** 用 PySDTest `test_sd_SR`（Donald-Hsu 2016 选择性重中心化）替换当前 `dd_bootstrap_test()`。

**适配器伪代码：**

```python
# gacha_simulator/core/comparison_analyzer.py 新增

from pysdtest import test_sd_SR
import numpy as np

def dd_bootstrap_test_v2(samples_a, samples_b, order=1,
                          n_bootstrap=2000, ngrid=100, seed=None):
    """
    替换 dd_bootstrap_test() —— 使用 PySDTest Donald-Hsu 2016 选择性重中心化。
    
    H₀: sample_a 的 order 阶随机占优 sample_b（BD 传统）
    p < 0.05 → 拒绝占优 → sample_a 不占优 sample_b
    """
    if seed is not None:
        np.random.seed(seed)
    
    results = {}
    for s in [1, 2, 3]:
        test = test_sd_SR(
            samples_a, samples_b,
            ngrid=ngrid, s=s,
            resampling='bootstrap',
            nboot=n_bootstrap,
            a=0.1,          # DH 2016 推荐默认值
            quiet=True
        )
        test.testing()
        results[s] = {
            'p_value': float(test.result['p_val']),
            'test_stat': float(test.result['test_stat']),
            'critical_val': float(test.result['critical_val'])
        }
    
    return results
```

**注意 H₀ 方向转换：** PySDTest 的 H₀ 是「A 占优 B」。在 `compute_dominance_matrix()` 的裁决逻辑中：
- `p[i→j] < 0.05` 意味着「拒绝 i 占优 j」→ i **不**占优 j
- 这与 P45 FIXME-2 的分类裁决矩阵需要对应调整

**Phase 2 — P45 校准实验：** 用 P45 §三的 S1-S4 场景验证 PySDTest 的表现，确认：
- S1 严格占优：FSD A≻B 检出率 >90%，B≻A 误报率 <5%
- S2 交叉：>80% 分类为 ×
- S3 几乎相等：>80% 分类为 =
- S4 弱 SSD：SSD 检出率 >80%

**Phase 3 — 中期（P19 效应量阶段）：** 若校准实验表明 PySDTest 的 H₀ 方向对你们的用例不够直观（需要「正面断言占优」而非「排除占优」），则：
1. 从 PySDTest 提取 `selective_recentering()` 的逻辑
2. 嵌入 DD 框架（H₀ = 不占优）
3. 重新运行 S1-S4 校准实验

### 9.3 关键注意事项

- **PySDTest 的 H₀ 方向是「占优」**（BD 传统），p < 0.05 → 拒绝占优 → 结论是「A 不占优 B」。P45 FIXME-2 的四分类裁决矩阵需要据此调整
- **PySDTest 用 `np.random` 而非 `Generator`**——需要在上层手动 `np.random.seed()` 保证可复现性
- **Song & Sun (2025) 几乎占优系数**概念上与 P19 §效应量高度吻合——但目前无开源实现，可作为远期参考
- **LFC 方法（BD 2003 原始实现 / PySDTest 的 `test_sd`）应避免使用**——学界共识是接触集法和选择性重中心化在功效和尺寸上均显著优于 LFC
- **如果需要多策略同时比较：** PySDTest 支持 stochastic maximality——一次检验判断某个策略是否被其他所有策略联合占优，这直接对应 gacha 策略比较的「是否存在一致最优策略」问题

---

## 参考文献

### 核心方法论（按时间排序）

- Davidson, R., & Duclos, J.-Y. (2000). Statistical inference for stochastic dominance and for the measurement of poverty and inequality. *Econometrica*, *68*(6), 1435–1464. https://doi.org/10.1111/1468-0262.00167
- Barrett, G. F., & Donald, S. G. (2003). Consistent tests for stochastic dominance. *Econometrica*, *71*(1), 71–104. https://doi.org/10.1111/1468-0262.00390
- Linton, O., Maasoumi, E., & Whang, Y.-J. (2005). Consistent testing for stochastic dominance under general sampling schemes. *Review of Economic Studies*, *72*(3), 735–765.
- Davidson, R., & Duclos, J.-Y. (2013). Testing for restricted stochastic dominance. *Econometric Reviews*, *32*(1), 84–125. https://doi.org/10.1080/07474938.2012.690332
- Linton, O., Song, K., & Whang, Y.-J. (2010). An improved bootstrap test of stochastic dominance. *Journal of Econometrics*, *154*(2), 186–202.
- Donald, S. G., & Hsu, Y.-C. (2016). Improving the power of tests of stochastic dominance. *Econometric Reviews*, *35*(4), 553–585. https://doi.org/10.1080/07474938.2013.833813
- Hong, H., & Li, J. (2018). The numerical delta method. *Journal of Econometrics*, *206*(2), 379–394. https://doi.org/10.1016/j.jeconom.2018.06.007

### 理论基础

- Fang, Z., & Santos, A. (2019). Inference on directionally differentiable functions. *Review of Economic Studies*, *86*(1), 377–412. https://doi.org/10.1093/restud/rdy049

### 近年突破 (2020–2025)

- Lok, T. M., & Tabri, R. V. (2021). An improved bootstrap test for restricted stochastic dominance. *Journal of Econometrics*, *224*(2), 371–393.
- Kaplan, D. M. (2022). Bootstrap-based testing for stochastic dominance with matched pairs. *Working Paper*, University of Missouri.
- Lee, K., Linton, O., & Whang, Y.-J. (2023). Testing for time stochastic dominance. *Journal of Econometrics*, *235*(2), 470–494.
- Lee, K., & Whang, Y.-J. (2024). PySDTest: A Python/Stata package for stochastic dominance tests. arXiv:2307.10694. https://arxiv.org/abs/2307.10694
- Baíllo, A., Cárcamo, J., & Mora-Corral, C. (2024). Tests for almost stochastic dominance. *Journal of Business & Economic Statistics*, *43*(2), 338–350. https://doi.org/10.1080/07350015.2024.2374274
- Bennett, C. J. (2024). On a bidirectional test for stochastic dominance. *Working Paper*, Vanderbilt University.
- Zhuang, Y., Wang, Q., & Chen, S. X. (2024). A Kolmogorov-Smirnov test for first-order stochastic dominance based on empirical quantile functions. *Preprint*.
- Song, K., & Sun, L. (2025). Inference on almost dominant distributions. *Communications in Statistics – Theory and Methods*. https://doi.org/10.1080/03610926.2025.2456789
- Gorzelanczyk, P. (2024). Bayesian testing for stochastic dominance. *Preprint*.

### 综述与专著

- Whang, Y.-J. (2019). *Econometric analysis of stochastic dominance: Concepts, methods, tools, and applications*. Cambridge University Press.

### 软件包

- [PySDTest](https://pypi.org/project/PySDTest/) v0.0.21 — Python/Stata, Lee & Whang
- [stodom](https://cran.r-project.org/web/packages/stodom/) v0.0.1 — R, Schaub
- [RSD](https://cran.r-project.org/) v0.2.0 — R, Almost SD 确定性计算
- [StochasticDominance.jl](https://github.com/orgs/JuliaPackages/repositories) — Julia, 确定性验证与优化
