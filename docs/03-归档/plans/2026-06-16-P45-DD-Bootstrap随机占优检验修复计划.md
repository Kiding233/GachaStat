<!-- META: P45 | module:panels/策略比较 | status:completed | last:2026-06-16 -->
# P45 DD Bootstrap 随机占优检验修复计划

> 日期：2026-06-13 | 更新：2026-06-16（R1 计划审查——FIXME-1 子任务扩充 + FIXME-2 方向修正 + FIXME-4 文档清单扩展；R2 Fixer 修复——ISSUE-001 参数透传 + ISSUE-002 v1 回退警示 + ISSUE-003 注释修正 + ISSUE-004 dominates 移除 + ISSUE-005 图例切换；R3 Fixer 修复——ISSUE-036 跨阶种子差异化 + ISSUE-037 rng_seed 透传链 + ISSUE-038 复合标签颜色判定；R4 Fixer 修复——GATE-1 任务 2a/2b 进一步拆分为 2a1/2a2/2b1/2b2 四个 ≤0.6h 子任务（纯逻辑/UI 分离 + v1 路径/布局分离）；GATE-6 测试文件创建职责分派（core 测试→任务 1b 脚手架，GUI 测试→任务 2a2 脚手架，任务 5 限执行+补齐））
> 触发：实际使用中 FSD/SSD/TSD 三阶双向（A→B 和 B→A）p 值均 <0.05，失去区分能力
> 关联：P19 §效应量专项设计 · P18（BootstrapEngine 改进，不重叠——DD 实现独立于 BootstrapEngine）
> 调研报告：[stochastic-dominance-methods-survey-2026-06-14.md](../04-收件箱/stochastic-dominance-methods-survey-2026-06-14.md)
> 校准脚本：`tools/calibrate_pysdtest.py`

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

### FIXME-0 ✅ 已完成 (2026-06-15)：方法论选型 + 校准实验

**结论：路径 A 通过，PySDTest `test_sd_SR` 验证有效。** 校准脚本 `tools/calibrate_pysdtest.py`，30 reps × 3 样本量 × 4 场景，总耗时 87 分钟。

**方向约定（重要）：**

PySDTest 采用经济学惯例——「值更高 = 占优」。大部分 GDR 是「更高更好」，方向天然一致。少数（-）GDR（成本型指标）需在送入检验前对数据取负号，映射规则：

| GDR 类型 | 处理 |
|----------|------|
| 正向 GDR（成功率、收益等，更高更好） | 直接送入 PySDTest，无需变换 |
| 负向 GDR（成本、miss_rate 等，更低更好） | `samples = -samples` 取负号后送入 |

在分类裁决矩阵中：「A ≻ B」统一解读为「A 在该 GDR 上优于 B」（正向 GDR 值更高 / 负向 GDR 值更低）。

**校准实验 S1-S4 结果（方向修正后）：**

| 场景 | n=100 | n=500 | n=2000 | 目标 | 通过 |
|------|-------|-------|--------|------|------|
| S1 严格占优 | B≻A 100% | B≻A 100% | B≻A 100% | 检出率>90% | ✅ |
| S2 交叉 | × 100% | × 100% | × 100% | 识别率>80% | ✅ |
| S3 几乎相等 | = 93.3% | = 90.0% | = 83.3% | 识别率>80% | ✅ |
| S4 弱 SSD | FSD 无误报 | FSD 无误报 | FSD 无误报 | 双向显著<10% | ✅ |

**S4 的 SSD 预判修正：** P45 原预期「A χ²(5) SSD 占优 B χ²(6)」——这在 Barrett-Donald「高值 = 占优」框架下是错误的。χ²(6) 均值 6 > χ²(5) 均值 5，严格 B 占优 A，检验行为完全正确。χ²(5) vs χ²(6) 的 CDF 理论交叉点在极左尾 (x<1)，实际样本 n=2000 亦不可检测。S4 的 FSD 交叉预判已在原始计划中移除，替代为「FSD 双向显著率 <10%」——该指标在所有样本量下均为 0%，合格。

<!-- REVIEW-R2-FIX: ISSUE-003 --><!-- REVIEW-R5-FIX: AUDIT-BREAK-7 —— 已核验：此修复（任务 0.5）正确处置了审计发现的第404行 `self.status_label` AttributeError。任务 0.5 在 FIXME-1 之前执行（依赖链：0.5 → 1a → 1b → 1c），符合审计建议的 "先行修复以降低后续调试难度"。无需额外修改。 --> **实施前序修复（独立 bug，应在 FIXME-1/2 前完成）：**

`comparison_analysis_panel.py:404` 的 `except` 块调用 `self.status_label.setText(...)`，但 `ComparisonAnalysisPanel.__init__` 从未定义 `status_label` 属性（仅定义了 `self._loading_label`，第156行）。若任何更新步骤抛出异常，错误处理器会因 `AttributeError` 二次崩溃，掩盖原始异常。

**修复：** 将第404行 `self.status_label.setText(...)` 替换为 `self._loading_label.setText("✗ 结果展示失败，请查看控制台")`——复用已存在的 `_loading_label`。一行改动，独立于 FIXME-1/2，建议先行修复以降低后续调试难度。

> 触发风险：FIXME-1（PySDTest ImportError 传播、新返回值形状适配失败）和 FIXME-2（`_update_l2` 大规模重写）显著增加了触发此异常路径的概率。

### FIXME-1：替换中心化 Bootstrap 为约束 Bootstrap

**文件：** `core/comparison_analyzer.py` → `dd_bootstrap_test()`

**目标：** Bootstrap DGP 正确施加 H₀: A 不 j 阶占优 B（即积分 CDF 在至少一处接触）。**子任务范围（R1 审查后扩充）：** PySDTest 适配器 + 阶内 BH FDR + V1/V2 派发 + `core/__init__.py` 导入同步 + `compute_integrated_cdf` 公共函数提取 + `pyproject.toml` 依赖声明 + n_bootstrap 统一 + ImportError 兜底。<!-- REVIEW-R1-FIX: ISSUE-003,004,005,007,008 -->

**首选方案（2026-06-14 更新，2026-06-15 修订）：集成 PySDTest `test_sd_SR`**

PySDTest v0.0.21 的 `test_sd_SR` 类已正确实现 Donald & Hsu (2016) 选择性重中心化：

```python
# gacha_simulator/core/comparison_analyzer.py 集成方案

import numpy as np

try:
    from pysdtest import test_sd_SR
    _PYSDTEST_AVAILABLE = True
except ImportError:
    _PYSDTEST_AVAILABLE = False


def dd_bootstrap_test_v2(samples_a, samples_b, n_bootstrap=500,
                          ngrid=100, seed=None,
                          orders: Optional[List[int]] = None):
    """使用 PySDTest Donald-Hsu 2016 选择性重中心化替换原始实现。

    注意：PySDTest 的 H₀ = A 占优 B（BD 传统），
    p < 0.05 → 拒绝占优 → A 不占优 B。
    FIXME-2 分类判定规则已据此方向调整。

    方向约定：统一「更高值 = 占优」。调用方（compute_dominance_matrix_v2）
    负责在传入前对 (-)GDR 样本取负号（samples = -samples）。

    Args:
        orders: 需计算的阶数列表，默认 None 表示全三阶 [1,2,3]。
                ComparisonWorker 逐阶循环时应传入 orders=[order] 以消除 3x 冗余
                （否则每阶调用内部重复计算全部三阶）。
                <!-- REVIEW-R2-FIX: ISSUE-001 —— orders参数消除外循环×内循环的3x冗余 -->
    """
    if not _PYSDTEST_AVAILABLE:
        raise ImportError(
            "PySDTest 未安装。请执行: pip install pysdtest\n"
            "或回退使用 dd_bootstrap_test (等式中心化，精度较低)"
        )

    if seed is not None:
        np.random.seed(seed)

    if orders is None:
        orders = [1, 2, 3]

    results = {}
    for s in orders:
        try:
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
        except Exception as e:
            # <!-- REVIEW-R5-FIX: AUDIT-BREAK-2 —— PySDTest 内部异常（如数值不稳定、网格退化）
            #      会导致 test.testing() 抛异常或 test.result 缺少必要键。
            #      捕获后返回 None 标记该对检验失败，由上游 compute_dominance_matrix_v2()
            #      在阶段 1 收集原始 p 值时统一处理 None（记录为 None、不参与 BH FDR）。 -->
            results[s] = {
                'p_value': None,
                'test_stat': None,
                'critical_val': None,
                'error': str(e)
            }
    return results
```

<!-- REVIEW-R2-FIX: ISSUE-001 --> **3x 冗余消除架构（重要）：**

`ComparisonWorker.run()`（第65-69行）以逐阶循环调用 `compute_dominance_matrix(order=1/2/3)`，而 `dd_bootstrap_test_v2` 默认计算全部三阶——导致每对策略执行 9 次 PySDTest（应为 3 次），性能退化为预估的 3 倍。

**消除方案：** `compute_dominance_matrix_v2()` 向下传递 `orders=[order]`，`dd_bootstrap_test_v2` 仅计算请求的阶数。

```
Worker.run()                            dd_bootstrap_test_v2
┌──────────────────────┐              ┌─────────────────────┐
│ for order in [1,2,3] │              │ orders=[order]      │
│   compute_dom(order) │──────────────▶│ → 仅 1 次 PySDTest │
│   → 仅触发 1 阶计算   │              │ (非全三阶重复)       │
└──────────────────────┘              └─────────────────────┘
每对策略: 3 次调用 × 1 次 PySDTest = 3 次 (消除 3x 冗余)
```

> **实施检查：** 实施 FIXME-1 后验证——N=3 策略下 `dd_bootstrap_test_v2` 的 PySDTest 调用次数应为 18（非 54），单次 `test_sd_SR` 的 `s` 参数等于传入的 `order`。

<!-- REVIEW-R1-FIX: ISSUE-003 --> **`compute_dominance_matrix_v2()` 返回值形状定义：**

```python
def compute_dominance_matrix_v2(
    values_list: List[np.ndarray],
    names: List[str],
    order: int = 1,
    n_bootstrap: int = 500,
    ngrid: int = 100,
    rng_seed: int = 42,
    lower_is_better: bool = False,
) -> Dict[str, Any]:
```

返回 `Dict[str, Any]`，键与 v1 的 `compute_dominance_matrix()` 兼容但扩展：

| 键 | 类型 | 说明 |
|----|------|------|
| `matrix` | `List[List[Optional[float]]]` | n×n 阶内 BH FDR 校正后 p 值矩阵（与 v1 同名键兼容——`_update_l2()` 第 534 行 `dom['matrix'][i][j]` 无需修改） |
| `matrix_raw` | `List[List[Optional[float]]]` | n×n 原始 p 值矩阵（PySDTest 直接输出，校正前） |
| `dominates` | `None` | <!-- REVIEW-R2-FIX: ISSUE-004 --> 已移除（远期预留）。原为 n×n 布尔矩阵——阶段 4 构建，因与 FIXME-2 `_classify_dominance()` 综合分类标签存在判定逻辑不一致风险（详见 ISSUE-004 处置说明），当前无消费者故移除。远期需求时基于 `_classify_dominance()` 产出重建 |
| `classification` | `List[List[str]]` | n×n **单阶显著性标记**矩阵（`'sig'`/`'ns'`/`'err'`/`'—'`），标记该阶内 p_ij 是否显著（BH 校正后 p<0.05）。<!-- REVIEW-R5-FIX: AUDIT-BREAK-2 —— 新增 'err' 值：PySDTest 内部异常导致 p_value=None 的单元格标记为 'err'，渲染时以特殊颜色（暗红色/禁用态）展示，不参与后续 _classify_dominance() 综合判定。 -->**注意：此为 per-order significance flag，非综合分类标签**——综合分类（≻/≺/×/=）由 FIXME-2 `_classify_dominance()` 消费三阶信息后统一产出，避免双重分类源冲突。对角线为 `'—'`。<!-- REVIEW-R2-FIX: ISSUE-005 —— classification降级为per-order significance flag，综合分类由GUI侧全权负责 --> |
| `names` | `List[str]` | 策略名列表（与 v1 同） |
| `order` | `int` | 阶数（与 v1 同） |
| `lower_is_better` | `bool` | 透传至 UI（控制方向提示行显隐） |

> **兼容性保证：** `matrix`、`names`、`order` 三个键与 v1 返回值语义完全兼容——`_update_l2()` 第 518 行 `dom['matrix'][i][j]` 和第 534 行 `dom['matrix'][i][j]` 无需任何修改即可工作。`dominates` 键仅单向显著时兼容——v2 在双向显著时采用行优先任意裁决（`dominates[i][j]=True, dominates[j][i]=False`），与 v1 的对称清零（双方均 `False`）语义不同（<!-- REVIEW-R1-FIX: ISSUE-014 —— dominates 兼容性声明修正 -->）。当前 GUI 不读取 `dominates` 矩阵，无实际影响。新增的 `classification` 键供 FIXME-2 分类矩阵消费，`matrix_raw` 键供调试面板消费。
>
> <!-- REVIEW-R2-FIX: ISSUE-004 --> **ISSUE-004 处置——dominates 矩阵双重判定结构维护风险：**
>
> 计划中存在两处独立的随机占优方向判定：(A) `compute_dominance_matrix_v2()` 阶段 4 基于 per-order significance flag 构建布尔 `dominates` 矩阵；(B) FIXME-2 的 `_classify_dominance()` 基于三阶双向 p 值综合判定五分类标签。两者在「FSD 双向显著」场景下结论矛盾——判定 A 行优先裁决为 `dominates[i][j]=True`（声称行占优列），判定 B 产出 `×(FSD)`（声称交叉）。`_check_higher_order_consensus()` 触发的 `×?(FSD)` 降级也会产生同样的 dominates/分类标签不一致。
>
> **处置方案：从 `compute_dominance_matrix_v2()` 中移除阶段 4（dominates 矩阵构建）。** 理由：(1) 当前 GUI 不消费 `dominates` 矩阵——移除无功能退化；(2) 保留徒增维护负担与未来 bug 源（若后续 GUI 开始消费 dominates 矩阵，不一致性将沉淀为线上 bug）；(3) `dominates` 的「行优先任意裁决」（双向显著→随机选胜者）在学术上脆弱——更好的做法是由 FIXME-2 的 `_classify_dominance()` 基于三阶信息综合判定，而非在 per-order 层面提前裁决。`dominates` 键保留于返回值字典中但值为 `None`（或直接移除键），以备远期需求时重新实现——届时应使 dominates 与 `_classify_dominance()` 产出一致。
>
> **实施变更清单：**
> - `compute_dominance_matrix_v2()` 返回值字典中 `'dominates': None`（替代阶段 4 的实际矩阵构建）
> - 阶段 4 伪代码从 `compute_dominance_matrix_v2()` 实现体中删除，以 `# 阶段 4: dominates 矩阵构建已移除——当前无消费者，远期需求时基于 _classify_dominance() 产出重建` 注释替代
> - 返回值形状表中 `dominates` 键标注为「已移除（远期预留）」

<!-- REVIEW-R2-FIX: ISSUE-005 —— compute_dominance_matrix_v2 实现体伪代码（n×n 循环 + BH FDR 收集/校正/回填） -->
**`compute_dominance_matrix_v2()` 实现体伪代码：**

```python
def compute_dominance_matrix_v2(values_list, names, order=1, n_bootstrap=500,
                                ngrid=100, rng_seed=42, lower_is_better=False):
    n = len(values_list)
    # <!-- REVIEW-R1-FIX: ISSUE-012 —— 在入口处一次性设置 PRNG 种子，使各配对从同一 PRNG 流中顺序消费随机数，获得自然独立的 Bootstrap 序列。避免每对调用均重置 np.random.seed(42)，导致 n×(n-1) 对检验共享完全相同的重抽样索引。 -->
    np.random.seed(rng_seed)
    # 阶段 1: n×n 双重循环——收集原始 p 值
    matrix_raw = [[None] * n for _ in range(n)]
    all_pairs = []  # [(i, j, p_raw)]
    
    for i in range(n):
        for j in range(n):
            if i == j:
                continue  # 对角线跳过
            # 对 (-)GDR 取负号
            a = -values_list[i] if lower_is_better else values_list[i]
            b = -values_list[j] if lower_is_better else values_list[j]
            result = dd_bootstrap_test_v2(a, b, orders=[order],
                                          n_bootstrap=n_bootstrap,
                                          ngrid=ngrid, seed=None)
            p_raw = result[order]['p_value']
            # <!-- REVIEW-R5-FIX: AUDIT-BREAK-2 —— p_raw 可能为 None（PySDTest 内部异常被捕获后
            #      dd_bootstrap_test_v2 返回 {'p_value': None, ...}）。
            #      None 值不参与 BH FDR 校正（从 all_pairs 中排除），
            #      matrix_raw[i][j] 保留为 None，matrix[i][j] 亦为 None，
            #      classification[i][j] 标记为 'err'（而非 'sig'/'ns'）。 -->
            matrix_raw[i][j] = p_raw
            if p_raw is not None:
                all_pairs.append((i, j, p_raw))

    # 阶段 2: 阶内 BH FDR 校正
    p_values = [p for _, _, p in all_pairs]
    <!-- REVIEW-R1-FIX: ISSUE-011 —— benjamini_hochberg 不接受 alpha 参数，BH 校正后的 q 值与 alpha=0.05 的阈值比较在阶段 3 处理 -->
    corrected = benjamini_hochberg(p_values)
    p_map = {(i, j): corr for (i, j, _), corr in zip(all_pairs, corrected)}

    # 阶段 3: 回填校正后 p 值矩阵 + 构建 classification 矩阵
    matrix = [[None] * n for _ in range(n)]
    classification = [['—'] * n for _ in range(n)]
    
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            p_corr = p_map.get((i, j))  # <!-- REVIEW-R5-FIX: AUDIT-BREAK-2 —— None 对不参与 BH，不在 p_map 中 -->
            matrix[i][j] = p_corr
            if p_corr is None:
                classification[i][j] = 'err'  # PySDTest 检验失败（异常/不收敛）
            else:
                classification[i][j] = 'sig' if p_corr < 0.05 else 'ns'
    
<!-- REVIEW-R2-FIX: ISSUE-003 --> # 阶段 4: dominates 矩阵构建已移除——当前无消费者。远期需求时基于 _classify_dominance() 产出重建，以确保与综合分类标签一致。
    # 参见 ISSUE-004（dominates 矩阵与 _classify_dominance() 双重判定结构维护风险）
    dominates = None

    return {
        'matrix': matrix,
        'matrix_raw': matrix_raw,
        'dominates': dominates,
        'classification': classification,
        'names': names,
        'order': order,
        'lower_is_better': lower_is_better,
    }
```

> **实施提示：** 阶段 1-2 的数据流（先收集再批量校正再回填）是非平凡的——不可在循环内逐对调用 BH 校正（那会丢失全局 p 值分布）。<!-- REVIEW-R2-FIX: ISSUE-004 -->阶段 4（dominates 矩阵构建）已在 R2 审查中移除——当前无消费者，保留徒增与 `_classify_dominance()` 的双重判定不一致风险。远期若需 dominates 矩阵，应基于 `_classify_dominance()` 的统一产出重建以确保一致性。
>
> <!-- REVIEW-R1-FIX: ISSUE-012 —— PRNG 种子设计决策 --> **PRNG 种子设计决策：** 在 `compute_dominance_matrix_v2()` 入口处一次性调用 `np.random.seed(rng_seed)`，随后向 `dd_bootstrap_test_v2(a, b, ..., seed=None)` 传入 `seed=None`——`dd_bootstrap_test_v2` 内部检测 `seed is None` 时跳过 `np.random.seed()` 调用，各配对从同一 PRNG 流中顺序消费随机数，自然获得独立序列。备选方案——对每对 (i,j) 使用递增种子 `seed=rng_seed + i * n + j`——可提供确定性复现性（单对复现），但 PRNG 序列本身已足够独立，主要方案更简洁。**实施时需同时修改 `dd_bootstrap_test_v2` 内部逻辑使其尊重 `seed=None`（跳过种子设置）。**
> <!-- REVIEW-R3-FIX: ISSUE-036 —— 跨阶种子管理标注 --> **注意：** 此设计仅覆盖单次 `compute_dominance_matrix_v2()` 调用内的**跨配对**种子管理（避免每对重置PRNG）。**跨阶**种子管理（FSD/SSD/TSD 三次独立调用 `compute_dominance_matrix()` 的种子差异化）由调用方 `ComparisonWorker.run()` 负责——传入 `rng_seed=42+order` 使三阶获得不同PRNG起点。详见上文 ISSUE-036 修复说明。

<!-- REVIEW-R1-FIX: ISSUE-004 --> **V1/V2 函数派发机制：**

采用对调用方透明的**内部自动检测方案**——改造 `compute_dominance_matrix()` 使其在内部自动选择引擎：

```python
def compute_dominance_matrix(
    values_list, names, order=1, n_bootstrap=500, rng_seed=42,
    engine: str = 'auto',  # 'auto' | 'pysdtest' | 'bootstrap'
    lower_is_better: bool = False,
    **kwargs,  # 透传 ngrid 等 PySDTest 参数
):
    if engine == 'auto':
        engine = 'pysdtest' if _PYSDTEST_AVAILABLE else 'bootstrap'

    if engine == 'pysdtest':
        return compute_dominance_matrix_v2(
            values_list, names, order=order, n_bootstrap=n_bootstrap,
            rng_seed=rng_seed, lower_is_better=lower_is_better, **kwargs,
        )
    else:
        return _compute_dominance_matrix_v1(
            values_list, names, order=order, n_bootstrap=n_bootstrap,
            rng_seed=rng_seed,
        )
```

<!-- REVIEW-R2-FIX: ISSUE-001 --> **选择此方案的理由：**
- (a) ~~`ComparisonWorker.run()` 第 67 行无需修改~~ **（R2 审查修正——此声明不成立）** `compute_dominance_matrix()` 签名向后兼容`order`/`n_bootstrap`/`rng_seed`参数，但`lower_is_better`参数必须从`ComparisonWorker.run()`显式透传——否则所有负向GDR的数据取反静默失效。需在`ComparisonWorker.run()`第67行调用处追加`lower_is_better=lower_is_better`（该变量已在第45行从`compute_gdr_values_for_datasets()`获取）。详见下方「ISSUE-001修复指令」。
- (b) 仅新增 `engine` 关键字参数，默认 `'auto'`，除`lower_is_better`外现有调用零改动即可使用 PySDTest
- (c) `ComparisonWorker.__init__` 无需新增参数，控制栏无需立即加引擎选择器（远期可在 UI 中暴露 `engine` 选项）
- (d) PySDTest 不可用时自动回退 v1，用户无感知降级

<!-- REVIEW-R5-FIX: AUDIT-BREAK-1 --> **类型断裂防护——`lower_is_better` 必须被派发器过滤，不可透传至 v1 路径：**

以上派发器伪代码（第 348-351 行）仅向 `_compute_dominance_matrix_v1()` 传递 `values_list`/`names`/`order`/`n_bootstrap`/`rng_seed` 五个参数，已正确将 `lower_is_better` 和 `**kwargs`（如 `ngrid`）排除在外。**实施时必须严格遵守此过滤规则：**

1. `lower_is_better` 是 `compute_dominance_matrix()` 的**命名参数**（非 `**kwargs` 成员），若派发器使用 `**kwargs` 透传模式（如 `_compute_dominance_matrix_v1(values_list, names, order=order, n_bootstrap=n_bootstrap, rng_seed=rng_seed, **kwargs)`），则 `lower_is_better` 不会进入 `**kwargs` 字典（Python 会将命名参数绑定到显式形参而非 `**kwargs`）——反而不会导致 TypeError。但若 v1 调用处意外以位置参数方式传入 `lower_is_better` 的值，将触发 `TypeError: _compute_dominance_matrix_v1() got unexpected keyword argument 'lower_is_better'`。
2. **唯一安全做法：** v1 调用处仅传入 v1 函数签名中声明的那五个参数——不采用 `**kwargs` 透传，不依赖参数名匹配。这正是当前伪代码采用的方式。实施时若修改此模式，必须同步验证 v1 路径的 `TypeError` 风险。
3. 任务 1c 的验收标准已覆盖此场景：`pip uninstall pysdtest -y` 后运行 GUI——v1 回退路径不应崩溃。

备选方案 (b) 和 (c) 见原始问题讨论，当前选择 (a) 以最小化 GUI 改动。

<!-- REVIEW-R2-FIX: ISSUE-002 —— v1 回退路径 p 值语义差异与 UI 警示 --><!-- REVIEW-R5-FIX: AUDIT-BREAK-5(b) —— v1/v2 分类判定不可比性：此为有意设计，通过横幅告知用户。v1 路径因无 FDR 校正且等式中心化过度敏感，分类结论系统性偏向「显著」——同一数据集在 v1/v2 路径下看到不同分类是预期行为，不是 bug。横幅的作用正是警示用户「当前结论可能过度乐观」。若远期要求 v1/v2 结论可比，唯一正确方案是在 v1 路径也实现 BH FDR + 接触集重中心化——但那等价于实现 v2 子集，背离 v1 作为轻量回退的定位。 --> **v1 回退路径的 p 值语义差异（重要——v1 与 v2 的 `matrix` 键不可比）：**

`compute_dominance_matrix()` 引擎派发机制在 PySDTest 不可用时自动回退至 `_compute_dominance_matrix_v1()`。v1 返回的 `matrix` 键存储**原始 p 值**（`dd_bootstrap_test()` 直接输出），v2 返回的 `matrix` 键存储**阶内 BH FDR 校正后的 q 值**（`compute_dominance_matrix_v2()` 阶段 2-3）。两者在 `_update_l2()` 阶段 0 的 `_classify_dominance(p_ij, p_ji)` 中以同一阈值 `p < 0.05` 判定显著性——导致以下后果：

| 后果 | 描述 |
|------|------|
| 分类结论不一致 | v1 路径因无 FDR 校正，更多单元格被判为「显著」→ 更激进的 ≻/≺ 标记，更少的 = 标记。同一数据集在 PySDTest 已安装/未安装环境下看到不同的分类结论。 |
| 假阳性放大 | v1 本身已存在「双向过度显著」问题（§1.2 根因），叠加无 FDR 校正后，分类矩阵的假阳性率进一步放大——`dd_bootstrap_test` 中 `p_value < 0.05` 直接判决的 `dominates` 布尔值（第268行）在 n×(n-1) 次检验中预期产生 5%×(n²-n) 个虚假显著对。 |
| 图例标签误导 | §ISSUE-005 图例统一标注「p<0.05」，掩盖 v1/v2 两路径在统计严谨性上的差异（详见 ISSUE-005 修复）。 |

**选择方案 (b)——v1 回退激活时在 UI 中展示明确警示：** 不修改 v1 的 `_compute_dominance_matrix_v1()` 内部逻辑（保持其作为轻量回退的简洁性），但在 `_update_l2()` 阶段 0 或阶段 1 检测当前引擎路径，若为 v1 回退则在分类矩阵上方渲染横幅：

```
⚠️ PySDTest 不可用，当前使用等式中心化 Bootstrap（v1 回退）。
   检验 p 值未经多重比较校正（无阶内 BH FDR），分类结论可能过度乐观。
   建议执行 `pip install pysdtest` 以获得正确的 Donald-Hsu 2016 选择性重中心化检验。
```

检测机制：`dom_results[1]` 是否含 `matrix_raw` 键（v2 独有）→ 若无则为 v1 回退路径。横幅实现：在阶段 0 分类矩阵 HTML 之前拼接 `<div style="background:#fff3cd;border:1px solid #ffc107;...">...</div>`。此改动为纯 UI 层，不影响 v1/v2 核心计算逻辑。

> **为什么不选方案 (a)（在 v1 中追加 BH FDR）：** `_compute_dominance_matrix_v1()` 的内部结构（`dd_bootstrap_test()` 直接返回单对 p 值，无全局对收集/批量校正/回填流程）与 BH FDR 所需的「先收集所有对 p 值→再批量校正」范式不兼容。为其追加 FDR 需要重构 v1 的 `compute_dominance_matrix()` 加入与 v2 相同的阶段 1-2 流程——此项工作等于实现 v2 的子集，背离 v1 作为「轻量回退」的设计定位。警示横幅是成本最低的降级告知方案。

<!-- REVIEW-R2-FIX: ISSUE-001 —— ISSUE-001修复指令（阻塞性） -->
> **ISSUE-001修复指令（阻塞性，必须在FIXME-1实施时同步完成）：**
>
> `ComparisonWorker.run()` 第67行当前调用：
> ```python
> dom = compute_dominance_matrix(values_list, names, order=order,
>                                n_bootstrap=1000)
> ```
> 必须修改为：
> ```python
> dom = compute_dominance_matrix(values_list, names, order=order,
>                                n_bootstrap=500,          # 同步统一为500（§FIXME-1 n_bootstrap统一）
>                                lower_is_better=lower_is_better,
>                                rng_seed=42 + order)      # 跨阶种子差异化：FSD=43, SSD=44, TSD=45
> ```
> `lower_is_better` 变量已在 `ComparisonWorker.run()` 第45行从 `compute_gdr_values_for_datasets()` 获取，无需新增变量声明。此改动同时解决 FIXME-2 子任务 2d 的方向提示行永远不会显示的问题（原本 `lower_is_better` 始终为 `False` 不会触发提示行渲染）。若不修改此调用，`compute_dominance_matrix_v2()` 内部的 `a = -values_list[i] if lower_is_better else values_list[i]`（第270行）对负向GDR的取反操作将静默跳过——所有成本型指标（miss_rate、resource_efficiency等）的PySDTest H₀方向错误，导致「更差（更高值）」的策略被误判为「占优」。

<!-- REVIEW-R5-FIX: AUDIT-BREAK-4 —— Worker 线程至 UI 信号链权限安全（已核验，无修复项） -->
> **AUDIT-BREAK-4 核验（Worker → finished → _on_analysis_finished 信号链）：** 审计确认此链路无权限断裂。`ComparisonWorker` 在 QThread 中运行，仅通过 `pyqtSignal(dict)` 跨线程传递数据——信号序列化机制保证 dict 安全跨越线程边界。`_on_analysis_finished` 在主线程事件循环中执行，所有 UI 更新（`_update_l1`/`_update_l2`/`_update_l3`）均在主线程。信号签名始终为 dict——无论 v1 或 v2 路径返回的 `dom_results` 均打包为同一 dict 结构，`_on_analysis_finished` 的解包逻辑不变。此链路与本计划修改无交叉——无需修复项。
>
> <!-- REVIEW-R3-FIX: ISSUE-036 --> **跨阶PRNG种子差异化（阻塞性——必须在FIXME-1实施时同步完成）：**
>
> `ComparisonWorker.run()` 以逐阶循环（order=1/2/3）三次调用 `compute_dominance_matrix()`。若三次调用均使用相同默认值 `rng_seed=42`，`compute_dominance_matrix_v2()` 入口处的 `np.random.seed(42)` 将三次重置全局PRNG至完全相同起点，导致 FSD/SSD/TSD 三阶检验共享完全相同的 Bootstrap 重抽样索引序列。虽然不同阶数计算不同的积分CDF（`test_sd_SR` 的 `s` 参数不同），统计量取值不同，但随机变异的共享破坏了各阶检验间的统计独立性——若某次调用因种子处于PRNG序列的「不幸运」区域（例如低质量的bootstrap分布），三阶结论将同时受影响。
>
> **修复方式：** `ComparisonWorker.run()` 第67行调用处传入 `rng_seed=42 + order`，使三阶分别获得不同的PRNG序列起点（FSD=43, SSD=44, TSD=45）。此为一行动改动（追加参数），不修改core层接口（`compute_dominance_matrix` 已有 `rng_seed` 参数，默认值42）。注意：§FIXME-1 的 PRNG 种子设计决策（第325-326行 `np.random.seed(rng_seed)` 入口一次性设置+传入`seed=None`）仅覆盖单次 `compute_dominance_matrix_v2()` 调用内的跨配对种子管理（避免每对重置 `np.random.seed(42)`），未覆盖 `ComparisonWorker.run()` 外层循环的跨阶种子重用——本修复填补这一遗漏。
>
> **Interaction with §ISSUE-037（rng_seed 基础种子透传）：** 若同时实施 ISSUE-037（`ComparisonWorker.__init__` 新增 `_rng_seed` 成员），调用处改为 `rng_seed=self._rng_seed + order`。基础种子仍为42，远期UI添加种子控件时仅修改 `self._rng_seed` 赋值来源即可。
>
> <!-- REVIEW-R3-FIX: ISSUE-037 --> **rng_seed 参数透传链构建（建议性——远期种子控件前置工作）：**
>
> 当前 `ComparisonWorker.run()` 第67行调用 `compute_dominance_matrix()` 时仅传入 `values_list`/`names`/`order`/`n_bootstrap` 四个参数（计划 ISSUE-001 修复指令追加了 `lower_is_better` 和 `rng_seed`），但 `ComparisonWorker.__init__` 参数列表中无 `rng_seed` 相关字段。若远期UI添加种子控件（例如调试面板——将种子暴露为可选项以复现特定分析），从滑块到Worker再到core层的完整参数传递链尚未构建。
>
> **修复方式：**
> 1. `ComparisonWorker.__init__`（第27-40行）参数列表追加 `rng_seed=42`，赋值 `self._rng_seed = rng_seed`
> 2. `ComparisonWorker.run()` 第67行调用处传入 `rng_seed=self._rng_seed + order`
> 3. 基础种子默认值42保证确定性复现；`+order` 实现跨阶差异化（ISSUE-036）
> 4. 远期添加种子控件时，仅需修改 `ComparisonWorker` 实例化时 `rng_seed` 参数的赋值来源即可，传递链完整
>
> 当前默认值42可保证基本功能，此修复为非阻塞性——若不实施，FIXME-1 的硬编码 `rng_seed=42+order` 已足够。但在计划中记录此透传链设计可避免远期种子控件实施时的接口返工。

<!-- REVIEW-R1-FIX: ISSUE-005, ISSUE-016 --> **`core/__init__.py` 导入同步（必做子步骤）：**

在 FIXME-1 实施时同步更新 `gacha_simulator/core/__init__.py`：
- 第 65-68 行 import 块追加 `dd_bootstrap_test_v2, compute_dominance_matrix_v2, compute_integrated_cdf`
- 第 132-134 行 `__all__` 列表追加 `'dd_bootstrap_test_v2', 'compute_dominance_matrix_v2', 'compute_integrated_cdf'`
- `_PYSDTEST_AVAILABLE` 仅为模块内部标志，不加入 import 块或 `__all__`
- `compute_integrated_cdf` 是 FIXME-3 `_render_l2_chart()` 的前置依赖（参见第 416 行），必须与 v2 函数一同导出

<!-- REVIEW-R1-FIX: ISSUE-010 --> **`a=0.1` 参数选择依据：**

Donald-Hsu 2016 选择性重中心化中，参数 `a` 控制选中重中心化网格点的阈值：
`selected_set = (√n₂ · D_s) < -a · √[log(log(N))]`。a 越大 → 选中点越少 → 检验越保守（尺寸控制越好但功效越低）。

经校准实验 S1-S4 在 a=0.1 下全部通过（30 reps × 3 样本量），确认此值在尺寸控制与功效之间取得可接受平衡。DH 2016 原文推荐范围 a ∈ [0.05, 0.2]，PySDTest 默认 a=0.1。远期可在 nboot 滑块旁预留 a 参数微调控件，当前硬编码以降低 UI 复杂度。

<!-- REVIEW-R2-FIX: ISSUE-007 --> **`ngrid=100` 参数选择依据：**

`ngrid` 决定积分 CDF 的网格分辨率——网格过粗则检验精度下降（接触集估计偏差增大），网格过细则计算时间线性增长。

选择 `ngrid=100` 的依据：(1) PySDTest 源码默认值为 100，校准实验 S1-S4 在此值下全部通过（S1-S3 命中率 >80%，S4 无误报），证实了 100 个网格点在 n∈[100,2000] 范围提供足够分辨率；(2) DD (2000) 原文附录建议网格数在 50-200 之间，100 是典型的平衡值；(3) 当前 v1 的自适应网格 `min(200, n_a + n_b)` 在 n=500 时给出 200 个网格点，v2 固定 100 略低于此值——但网格质量不仅取决于点数，更取决于选择性重中心化算法本身的优越性（DH 2016 在接触集上校正，对网格密度敏感度低于 v1 的等式中心化）。

**自适应考虑（远期）：** 当前硬编码 100 在极端场景可能不足（n > 10000 的大样本可能需要 200 个网格点以捕捉接触集的精细结构；n < 50 的小样本中 100 个网格点浪费且可能过度拟合）。远期可在 nboot 滑块旁增加 ngrid 微调控件（50/100/200），当前阶段在代码注释中说明选择依据即可。

> **对比 v1 自适应网格：** v1 使用 `n_grid = min(200, n_a + n_b)`（comparison_analyzer.py:224），在 n=100 时 100 个网格点、n=500 时 200 个网格点。v2 固定 100 个网格点在中等样本量（n~500）下略少，但 DH 2016 选择性重中心化的精度优势预期可弥补网格密度差异。

**`lower_is_better` 处理（简化方案）：** 适配器不做数据变换——统一「更高 = 占优」。对 (-)GDR（成本型，更低更好），在送入 PySDTest 前对样本取负号（`samples = -samples`）后送入。`compute_dominance_matrix_v2()` 接收 `lower_is_better` 参数用于控制数据变换，同时透传给 UI 用于显示分类矩阵上方的方向提示（如「⚠️ 当前 GDR 为 (-) 成本型指标，"≻"=更低更好」）。

**多重比较校正（阶内 BH FDR）：** 三阶嵌套非独立，不做跨阶校正。对每阶单独提取 `n×(n-1)` 个原始 p 值 → `benjamini_hochberg()`（[已有实现](gacha_simulator/core/comparison_analyzer.py#L383)）→ 校正后 p 值送入分类判定。改动 ~10 行，在 `compute_dominance_matrix_v2()` 内完成。

<!-- REVIEW-R2-FIX: ISSUE-004 --> **`n_bootstrap` 统一为 500（首屏默认值）：** 需同步修改 [comparison_analysis_panel.py:68](gacha_simulator/gui/comparison_analysis_panel.py#L68) 中 `ComparisonWorker.run()` 的硬编码 `n_bootstrap=1000` → `500`——与 §五 性能测算附录的「首屏默认 nboot=500」保持一致（3 策略 ~54s，用户可接受）。由于派发机制采用方案 (a)（内部自动检测），此改动仅需改数字，无需改函数名。

> **远期：** nboot 滑块（P45-IMPACT-06）引入后，Worker 将读取滑块值替代硬编码值。滑块默认值 500，选项 200/500/1000/2000。硬编码值作为滑块未初始化时的 fallback。

<!-- REVIEW-R1-FIX: ISSUE-007 --> **积分 CDF 公共函数提取（FIXME-3 前置依赖）：**

PySDTest `test_sd_SR` 不保证暴露内部积分 CDF 曲线数据（`grid`、`integrated_cdf` 值），FIXME-3 的 Click-to-expand CDF 曲线渲染需要独立的数据源。因此 FIXME-1 实施时需从 `dd_bootstrap_test()` 提取现有闭包逻辑为公共函数：

```python
# 新增公共函数（从 dd_bootstrap_test:229-238 提取）
def compute_integrated_cdf(
    samples: np.ndarray,
    grid: np.ndarray,
    order: int,
) -> np.ndarray:
    """计算样本在指定网格点上的 j 阶积分 CDF。
    
    order=1 → 经验 CDF, order=2 → 一阶积分 CDF (SSD 的 F), order=3 → 二阶积分 CDF (TSD 的 F)
    """
    # NumPy 2.0+ 兼容：np.trapz 已弃用，优先使用 np.trapezoid
    # <!-- REVIEW-R2-FIX: ISSUE-007 —— np.trapz→np.trapezoid 兼容 -->
    _trapz = np.trapezoid if hasattr(np, 'trapezoid') else np.trapz
    
    def ecdf(s, x):
        return np.mean(s <= x)
    
    F = np.array([ecdf(samples, xi) for xi in grid])
    for _ in range(order - 1):
        F = np.array([_trapz(F[:k+1], grid[:k+1]) for k in range(len(grid))])
    return F
```

此函数在 `core/comparison_analyzer.py` 中导出（加入 `core/__init__.py` import 块和 `__all__`），供 FIXME-3 的 `_render_l2_chart()` 调用——用户点击 (i,j) 格 → 对 `values_list[i]` 和 `values_list[j]` 分别计算 1/2/3 阶积分 CDF → 渲染 Plotly 曲线。备选方案：若实施时确认 PySDTest result 对象包含 `grid`/`F_a`/`F_b` 字段，则直接从 PySDTest 提取，无需额外计算。

<!-- REVIEW-R2-FIX: ISSUE-004 —— PySDTest内部网格一致性验证 --> **网格一致性验证（FIXME-1 实施时必做）：** `compute_integrated_cdf` 使用 `np.linspace(min, max, n_grid)` 独立生成网格，而 PySDTest `test_sd_SR` 内部也生成自己的网格用于选择性重中心化。若两个网格端点或分辨率不同，用户看到的 CDF 曲线可能不在检验实际比较的域上——造成可视化与检验结论的表述不一致。实施时的验证步骤：(1) 用 `dir(test.result)` 或查看 PySDTest 源码确认 result 对象是否暴露 `grid`/`F_a`/`F_b`；(2) 若暴露则直接使用 PySDTest 网格（保证可视化与检验同域）；(3) 若不暴露，使用 `np.linspace` 生成网格并在代码注释中说明「可视化网格与 PySDTest 内部 grid=ngrid 等距网格一致」，减少用户困惑。此条同时加入 FIXME-1 的完成门控项。

**备选方案（若 PySDTest 不可用）：** 保留原 `dd_bootstrap_test()` 作为回退（等式中心化，已知局限——双向过度显著）。若需不依赖 PySDTest 的正确实现，可参考 Donald & Hsu (2016) §3 选择性重中心化流程自实现（接触集估计 + 重中心化偏移），详细公式见计划文件初版（v1）或 DH 2016 原文。

<!-- REVIEW-R2-FIX: ISSUE-007 —— v1 回退的 np.trapz 也应在实施时同步替换为 _trapz 兼容层 -->
<!-- REVIEW-R5-FIX: AUDIT-BREAK-3 —— v1 闭包 np.trapz 前向断裂：阻塞性，已升级为任务 1a 显式交付项 -->
> **v1 回退路径 `np.trapz` 兼容层同步（阻塞性——已从隐性建议升级为任务 1a 显式交付）：**
>
> `dd_bootstrap_test()` 第 237 行内部 `integrated_cdf` 闭包直接调用 `np.trapz()`。当前 NumPy 2.2.6 保留此函数（弃用但未移除），但 NumPy 2.x 后续版本将彻底移除 → v1 回退路径触发 `AttributeError`。任务 1a 中新增的 `compute_integrated_cdf()` 公共函数已包含 `_trapz = np.trapezoid if hasattr(np, 'trapezoid') else np.trapz` 兼容层，但 v1 内部闭包未被同步重构。
>
> **修复指令（纳入任务 1a 交付清单）：** `dd_bootstrap_test()` 内部的 `integrated_cdf` 闭包同样添加兼容层：
> ```python
> _trapz = np.trapezoid if hasattr(np, 'trapezoid') else np.trapz
> ```
> 并将闭包中 `np.trapz(...)` 调用替换为 `_trapz(...)`。此改动与提取 `compute_integrated_cdf` 公共函数独立——甚至应**先于**公共函数提取完成（避免公共函数就绪前 v1 路径因 NumPy 升级崩溃）。两处改动均为同一兼容层模式，合计 +2 行。
>
> **当前环境非阻塞**（NumPy 2.2.6 仍保留 `np.trapz`），但属前向兼容性债务——NumPy 3.0 预期彻底移除。此修复在任务 1a 的 1.0h 预估内已包含（两行兼容层 + 闭包内替换 < 5 分钟）。验收标准：v1 回退路径下 `grep 'np\.trapz(' gacha_simulator/core/comparison_analyzer.py` 返回空（两处均已替换为 `_trapz` 变量调用）。

<!-- REVIEW-R1-FIX: ISSUE-008 --> **PySDTest 依赖声明（FIXME-1 实施时必须同步）：**

1. 在 `pyproject.toml` 的 `[project.optional-dependencies]` 新增 `analysis` 组：
   ```toml
   analysis = [
       "pysdtest>=0.0.21,<0.1",
   ]
   ```
2. 同时将 `pysdtest` 加入 `gui` extras（用户安装 `pip install -e ".[gui]"` 时应自动获得 PySDTest）：
   ```toml
   gui = [
       "PyQt6>=6.0",
       "PyQt6-WebEngine>=6.0",
       "pysdtest>=0.0.21,<0.1",
   ]
   ```
3. PySDTest 设为**可选依赖**而非强制核心依赖——`_PYSDTEST_AVAILABLE` 检测 + 自动回退 v1 确保 headless/CLI 场景无 PySDTest 仍可工作。
4. 版本约束：`>=0.0.21`（已知 API 兼容的最低版本），`<0.1`（预防破坏性变更）。PySDTest 仅 numpy+matplotlib 依赖，9.4 KB，无额外供应链风险。

> **为什么不加入 `[project.dependencies]`：** PySDTest 仅被 L2 随机占优使用，CLI/headless 模拟场景不需要。作为可选依赖可避免污染核心安装。

### FIXME-2：新增分类裁决矩阵（p 值矩阵保持不动）

**文件：** `gui/comparison_analysis_panel.py` → `_update_l2()`

**前置依赖：** FIXME-1（PySDTest 的 H₀ 方向为「占优」，分类判定规则需对应调整）

**目标：** 在现有三张 p 值矩阵**之上**新增一张分类裁决矩阵作为摘要。p 值矩阵保持不动（供详细审查），分类矩阵提供直观的一眼结论。

| 子任务 | 描述 |
|--------|------|
| 2a1 | <!-- REVIEW-R5-FIX: AUDIT-BREAK-5 —— _classify_dominance 必须处理稀疏 dict（缺失阶）和 None 值 -->新增 `@dataclass(frozen=False) class ClassificationResult: label: str; effect_size_slot: Optional[str] = None` 和 `_classify_dominance(p_ij: Dict[int, float], p_ji: Dict[int, float]) -> ClassificationResult` 函数——**逐对调用**（与现有 `_update_l2` 双重循环模式一致）。入参 `p_ij` 为 `{1: FSD(i→j) BH校正p, 2: SSD(i→j) BH校正p, 3: TSD(i→j) BH校正p}`——**可能为稀疏 dict**（某些阶因 PySDTest 异常返回 None，被上游 `_update_l2` 阶段 0 过滤后缺失该键），`p_ji` 为其对称双向 p 值。`_classify_dominance` 内部处理缺失阶——将缺失阶视为「不显著」（该阶不能提供判定依据，由其余阶裁决）。基于三阶双向校正 p 值输出单一分类符号（`≻`/`≺`/`=`/`×`/`err`——`err` 仅当所有阶均缺失时返回）。`ClassificationResult.label` 为分类标签字符串，`ClassificationResult.effect_size_slot: Optional[str]` 字段——初始值为 `None`，供后续效应量专项（P19 §效应量）填入（`result.effect_size_slot = "CLES=0.62"`，调用方无需修改解包逻辑）。<!-- REVIEW-R2-FIX: ISSUE-001 —— NamedTuple不可变无法后赋值，改用@dataclass(frozen=False)支持result.effect_size_slot后赋值 --><!-- REVIEW-R2-FIX: ISSUE-002 —— @dataclass替代str+属性；ISSUE-006 --> |
| 2b | 在 `_update_l2()` 中，三张 p 值 HTML 表**之前**新增一个分类矩阵 HTML 表（同为 n×n，每格为分类符号） |
| 2c | 新增图例：≻ (行占优列, FSD/SSD/TSD) / ≺ (行被列占优, FSD/SSD/TSD) / × (交叉) / = (无差异) |
| 2d | 对 (-)GDR，在分类矩阵上方添加方向提示：「⚠️ 当前 GDR 为 (-) 成本型指标，占优应反向解读」 |
| <!-- REVIEW-R1-FIX: ISSUE-013 —— _render_classification_matrix 签名与职责定义，作为 FIXME-2 的必须交付项 -->2e | 新增 `_render_classification_matrix(self, classification: List[List[str]], names: List[str]) -> None` ——使用 QTableWidget（`self._classification_table`）渲染分类矩阵（理由见 FIXME-3 方案 (a)（第 605 行）——`cellClicked(row, col)` 支持 FIXME-3 的点击交互）。单元格背景：对角线 `'—'` → 灰色禁用态（`setFlags(Qt.NoItemFlags)`）；`'≻'` → 绿色背景；`'≺'` → 红色背景；`'×'`/`'×?'` → 橙色背景；`'='` → 灰色；`'err'` → 暗红色禁用态（`setFlags(Qt.NoItemFlags)` + 文字提示「检验失败」）。<!-- REVIEW-R5-FIX: AUDIT-BREAK-2,AUDIT-BREAK-5 —— 新增 'err' 标签渲染规则 -->同步在 `_setup_ui()` L2 布局变更中新增 `self._classification_table = QTableWidget()` 实例化 + 布局插入（置于 p 值矩阵 QLabel 之前）。<!-- REVIEW-R3-FIX: ISSUE-038 —— 复合标签颜色判定解析 -->**复合标签颜色判定规则：** `_classify_dominance()` 产出的标签是复合字符串（如 `'≻ (FSD)'`、`'≺ (SSD)'`、`'×(FSD)'`、`'×?(FSD)'` 等），包含阶数标注后缀；或简单字符串（`'err'`、`'—'`）。`_render_classification_matrix()` 在设定单元格背景色时需从复合标签中提取基础符号。**采用 `label[0]` 首字符方案：** 取标签第一个字符作为颜色判定键——字典 `COLOR_MAP = {'≻': '#2e7d32', '≺': '#c62828', '×': '#ef6c00', '=': '#757575', '—': '#e0e0e0', 'e': '#8b0000'}`（`'err'` 首字符 `'e'` 映射暗红色）。`label[0]` 方案简洁无需正则匹配，且覆盖所有已定义标签（`'×(FSD)'` 和 `'×?(FSD)'` 均以 `'×'` 为首字符，统一为橙色背景，区分标注由文字内容本身传达）。**注意：** `'err'` 单元格应禁用交互（`setFlags(Qt.NoItemFlags)`），点击不触发 `_render_l2_chart`——因为没有有效的检验结果可可视化。 |

**L2 区最终布局（从上到下）：**

```
┌─────────────────────────────────────────────┐
│  ⚠️ (-)GDR 方向提示（仅当 lower_is_better 时显示）│
├─────────────────────────────────────────────┤
│  分类裁决矩阵 (新增)                           │
│  ┌────┬────┬────┬────┐                       │
│  │    │ A  │ B  │ C  │                       │
│  ├────┼────┼────┼────┤                       │
│  │ A  │ —  │≺FSD│  = │                       │
│  │ B  │≻FSD│ —  │≻SSD│                       │
│  │ C  │  = │≺SSD│ —  │                       │
│  └────┴────┴────┴────┘                       │
├─────────────────────────────────────────────┤
│  FSD p 值矩阵 (保持不动)                       │
│  SSD p 值矩阵 (保持不动)                       │
│  TSD p 值矩阵 (保持不动)                       │
└─────────────────────────────────────────────┘
```

<!-- REVIEW-R2-FIX: ISSUE-006 —— _update_l2() 两阶段控制流（先跨三阶组装分类矩阵，再逐阶渲染 p 值矩阵） -->
**`_update_l2()` 两阶段控制流（重要——当前逐阶循环结构不支持新布局）：**

当前 `_update_l2()`（原 L517 `labels_map.items()` for 循环）对 `dom_results` 逐阶循环——每阶独立渲染其 p 值矩阵 HTML 到对应 QLabel。但分类判定函数 `_classify_dominance(p_ij, p_ji)` 需要同时消费三阶 p 值（`p_ij = {1: dom_results[1]['matrix'][i][j], 2: dom_results[2]['matrix'][i][j], 3: dom_results[3]['matrix'][i][j]}`）——这意味着分类矩阵必须在逐阶循环**之前**完成。实施时 `_update_l2()` 应改为两阶段结构：

```python
<!-- REVIEW-R1-FIX: ISSUE-015 —— lower_is_better 用于控制方向提示行显隐 -->
def _update_l2(self, dom_results: Dict[int, Dict], names: List[str], lower_is_better: bool = False):
    n = len(names)
    
    # == 阶段 0：分类矩阵构建（必须最先——消费三阶 p 值）==
    classification = [['—'] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            p_ij = {1: dom_results[1]['matrix'][i][j],
                    2: dom_results[2]['matrix'][i][j],
                    3: dom_results[3]['matrix'][i][j]}
            p_ji = {1: dom_results[1]['matrix'][j][i],
                    2: dom_results[2]['matrix'][j][i],
                    3: dom_results[3]['matrix'][j][i]}
            # <!-- REVIEW-R5-FIX: AUDIT-BREAK-5 —— p_ij/p_ji 值可能为 None（PySDTest 异常返回、
            #      v2 阶段 2 排除的空值对、或其他上游失败）。
            #      _classify_dominance() 内部必须在比较 p < 0.05 之前逐阶检查 None：
            #      - 若某阶的 p_ij 或 p_ji 为 None，该阶视为「不显著」（跳过判定）
            #      - 若所有三阶的 p_ij 和 p_ji 均为 None，返回 ClassificationResult(label='err')
            #      - 不可直接使用 None < 0.05 导致 TypeError -->
            p_ij_clean = {k: v for k, v in p_ij.items() if v is not None}
            p_ji_clean = {k: v for k, v in p_ji.items() if v is not None}
            if not p_ij_clean and not p_ji_clean:
                classification[i][j] = 'err'  # 全部检验失败
            else:
                result = _classify_dominance(p_ij_clean, p_ji_clean)
                classification[i][j] = result.label
    
    # 渲染分类矩阵 HTML/TableWidget
    self._render_classification_matrix(classification, names)
    
    # == 阶段 1：逐阶 p 值矩阵（现有循环，保持不变）==
    labels_map = {1: (self._fsd_label, 'FSD'), 2: (self._ssd_label, 'SSD'),
                  3: (self._tsd_label, 'TSD')}
    for order, (label_widget, title) in labels_map.items():
        dom = dom_results[order]
        # ... 现有 p 值矩阵渲染逻辑 ...
        # <!-- REVIEW-R2-FIX: ISSUE-005 —— 图例文字条件切换 -->
        # v2 路径（dom 含 'matrix_raw' 键）：图例标注「FDR q&lt;0.05」或「校正后 p&lt;0.05」
        #    并增加 tooltip: "使用 Benjamini-Hochberg 阶内 FDR 校正"
        # v1 回退路径（dom 不含 'matrix_raw' 键）：图例保持「p&lt;0.05」
        # 切换逻辑：检测 dom_results[1] 是否含 'matrix_raw' 键（v2 独有）
```

> **实施要点：** 若 FIXME-2 采用 QTableWidget 渲染分类矩阵（参见 FIXME-3 点击交互方案），阶段 0 应将 `classification[i][j]` 写入 `self._classification_table` 的对应单元格而非构建 HTML 字符串。`_render_classification_matrix()` 可封装为独立方法，供初始渲染和后续数据更新复用。
>
> <!-- REVIEW-R1-FIX: ISSUE-015 —— 调用点同步更新 --> **调用点同步更新（必须）：** `_on_analysis_finished`（或等效的结果回调）中原调用 `self._update_l2(results['dom_results'], names)` 需改为 `self._update_l2(results['dom_results'], names, results.get('lower_is_better', False))`——确保 `lower_is_better` 参数从结果字典透传至 `_update_l2()` 用于控制方向提示行显隐。

<!-- REVIEW-R1-FIX: ISSUE-001 --> 分类判定规则——与 calibrate_pysdtest.py classify_bd() 方向一致。-->

**分类判定规则（合并三阶双向信息，p 值均已阶内 BH FDR 校正）：**

> **PySDTest H₀ 方向提醒：** PySDTest 采用 Barrett-Donald 传统，H₀ =「行 i 占优列 j」（更高值 = 占优）。p<0.05 → 拒绝 H₀ → 行 i **不**占优列 j。
>
> 因此：`FSD(i→j) 显著` = 拒绝「i 占优 j」= **i 不占优 j**。分类裁决需反转解读方向——
> FSD(i→j) 显著且 FSD(j→i) 不显著 → i 不占优 j, j 可能占优 i → **j ≻ i**（列占优行）。
>
> 对于 (-)GDR（成本型指标），数据在送入 PySDTest 前已取负号（`samples = -samples`），
> 检验仍以「更高 = 占优」运行，分类规则不受影响。UI 中「≻」统一解读为「更优方」。

```
对每对 (i, j)（行 i, 列 j）：

  1. 若 FSD(i→j) 显著 (p<0.05) 且 FSD(j→i) 不显著 (p≥0.05)
     → i 不占优 j, j 可能占优 i → "≺ (FSD)"（行被列占优）
  2. 若 FSD(i→j) 不显著 且 FSD(j→i) 显著
     → i 可能占优 j, j 不占优 i → "≻ (FSD)"（行占优列）
  3. 若 FSD 双向均不显著，但 SSD(i→j) 不显著且 SSD(j→i) 显著
     → "≻ (SSD)"；反之 SSD(i→j) 显著且 SSD(j→i) 不显著 → "≺ (SSD)"
  4. 若 FSD+SSD 双向均不显著，TSD 单向显著 → 同逻辑输出 "≻ (TSD)" / "≺ (TSD)"
  5. 若某阶双向均显著 (双方 p<0.05)
     → "×"（交叉），标注最低出现双向显著的阶数，如 "×(FSD)" / "×(SSD)" / "×(TSD)"
     例外：若该阶双向显著但更高阶一致单向显著，降级为 "×?(FSD)"（提示 FSD 交叉可能为噪声）
     <!-- REVIEW-R2-FIX: ISSUE-006 —— 降级决策表与精确定义 -->
     
     **「更高阶一致单向显著」降级决策表：**
     
     以 FSD 双向显著为例（SSD/TSD 双向显著时类推），检查 SSD 和 TSD 的 (i→j) 和 (j→i) 显著性：
     
     | SSD(i→j) | SSD(j→i) | TSD(i→j) | TSD(j→i) | 裁决 | 逻辑 |
     |-----------|-----------|-----------|-----------|------|------|
     | 显著 | 不显著 | 显著 | 不显著 | **降级 ×?(FSD)** | SSD+TSD 一致指向 i 不占优 j、j 可能占优 i |
     | 不显著 | 显著 | 不显著 | 显著 | **降级 ×?(FSD)** | SSD+TSD 一致指向 j 不占优 i、i 可能占优 j |
     | 显著 | 不显著 | 双向不显著 | — | **降级 ×?(FSD)** | 至少 SSD 提供单向信号，TSD 未反对 |
     | 不显著 | 显著 | 双向不显著 | — | **降级 ×?(FSD)** | 同上（反向） |
     | 双向不显著 | — | 显著 | 不显著 | **降级 ×?(FSD)** | TSD 提供单向信号 |
     | 双向不显著 | — | 不显著 | 显著 | **降级 ×?(FSD)** | 同上（反向） |
     | 显著 | 显著 | — | — | **保留 ×(FSD)** | SSD 双向显著——更高阶亦交叉 |
     | 双向不显著 | — | 显著 | 显著 | **保留 ×(FSD)** | TSD 双向显著——更高阶交叉 |
     | 显著 | 不显著 | 不显著 | 显著 | **保留 ×(FSD)** | SSD 与 TSD 方向矛盾——高层未提供一致信号 |
     | 不显著 | 显著 | 显著 | 不显著 | **保留 ×(FSD)** | 同上（反向矛盾） |
     | 双向不显著 | — | 双向不显著 | — | **保留 ×(FSD)** | 更高阶无任何信号 |
     
     **伪代码实现：**
     ```python
     def _check_higher_order_consensus(p_ij, p_ji, cross_order):
         """cross_order 为出现双向显著的阶数 (1=FSD, 2=SSD, 3=TSD)。
         返回 True 表示应降级为 ×?。"""
         higher = [o for o in [1,2,3] if o > cross_order]
         sig_ij = [o for o in higher if p_ij[o] < 0.05]  # i→j 显著 = 拒绝i占优j
         sig_ji = [o for o in higher if p_ji[o] < 0.05]  # j→i 显著
         
         # 至少一个更高阶有单向显著信号
         any_sig = bool(sig_ij or sig_ji)
         # 且所有有信号的更高阶方向一致
         consistent = not (sig_ij and sig_ji)
         
         if not any_sig:
             return False  # 更高阶无信号 → 保留 ×
         if consistent:
             return True   # 所有信号一致单向 → 降级 ×?
         else:
             return False  # 信号矛盾 → 保留 ×
     ```
  6. 若所有阶双向均不显著
     → "="（无显著差异，双方均无法拒绝对方占优的零假设）
```

> **与 calibrate_pysdtest.py classify_bd() 对应关系验证：**
> - `reject_ab and not reject_ba → "B≻A"` ≡ `FSD(A→B)显著, FSD(B→A)不显著 → B≻A` ≡ 规则 1
> - `not reject_ab and reject_ba → "A≻B"` ≡ `FSD(B→A)显著, FSD(A→B)不显著 → A≻B` ≡ 规则 2
> - 校准实验 S1-S4 全部通过，确认此方向正确。

<!-- REVIEW-R1-FIX: ISSUE-002 --> **与旧版一致：** 维持 p&lt;0.05 显著/不显著二值判定（与当前 `comparison_analysis_panel.py:530-537` 逻辑相同，当前代码中未存在过边界模糊带）。多重比较校正（阶内 BH FDR）和双向裁决在最上游提供假阳性保护——对比旧版仅靠单边 p 值阈值，新版在统计推断层面更严谨。

### FIXME-3：新增集成 CDF 差异可视化

**文件：** `gui/comparison_analysis_panel.py` → 新增方法 `_render_l2_chart()`

**前置依赖：** FIXME-1（`compute_integrated_cdf` 公共函数） + FIXME-2（分类矩阵 widget 就绪后方可接入点击事件）。<!-- REVIEW-R2-FIX: ISSUE-003 —— 原仅标注依赖FIXME-1，但分类矩阵由FIXME-2构建，实际需等待FIXME-2 -->

**目标：** 在分类矩阵下方添加 Plotly 图，显示积分 CDF 曲线及差异区域

**点击交互方案（FIXME-3 核心设计，必须在 FIXME-2 阶段确定渲染方案后方可实施）：**<!-- REVIEW-R2-FIX: ISSUE-003 —— 单元格点击交互机制设计 -->

当前 L2 区域使用三个 QLabel（`_fsd_label`/`_ssd_label`/`_tsd_label`）渲染 HTML 表格——QLabel 的 RichText 模式不提供逐单元格点击检测。代码中无 `linkActivated` 信号连接、无 `QTableWidget.itemClicked` 使用先例。FIXME-2 新增的分类矩阵是点击交互的入口，其渲染方案直接决定 FIXME-3 的事件接入方式。

**推荐方案 (a)：分类矩阵使用 QTableWidget。** 参考 L3 `_pvalue_table` 的现有模式，通过 `cellClicked(row, col)` 信号触发 `_render_l2_chart(i, j)`。与 L3 模式一致，可复用项目既有的 QTableWidget 样式和交互约定。`_setup_ui()` 中新增 `self._classification_table = QTableWidget()` 替代 QLabel 占位符，设置 `setSelectionBehavior(SelectRows)` / `setEditTriggers(NoEditTriggers)`，渲染时逐格填入分类符号 + 背景色。

**备选方案 (b)：若坚持 QLabel 渲染。** 在 HTML 中为每单元格嵌入 `<a href='cell://{i}/{j}'>` 锚点，连接 QLabel 的 `linkActivated` 信号解析坐标。但此方案使样式控制（对齐、padding、hover 反馈）退化为 CSS inline style，且与 L3 的 QTableWidget 模式不一致。

**建议在 FIXME-2 的 `_setup_ui` 布局变更中即为分类矩阵分配 QTableWidget**，P45-IMPACT-03（`_update_l2` 重写）一并实施 widget 创建与布局。FIXME-3 实施时仅需连接信号 `cellClicked` → `_render_l2_chart()`。

| 子任务 | 描述 |
|--------|------|
| 3a | 用户点击分类矩阵（QTableWidget）中某个 (i, j) 单元格 → `cellClicked(row, col)` 信号触发 `_render_l2_chart(i, j)`，在下方面板渲染 F_a, F_b 的 1/2/3 阶积分 CDF 曲线。点击逻辑忽略对角线（`i == j` 不响应）。<!-- REVIEW-R5-FIX: AUDIT-BREAK-6 —— 阻塞性 None 守卫：`_render_l2_chart` 方法首行必须加 `if self._last_results is None: return`。原因：`set_datasets()` 第325行将 `self._last_results = None`，至 `_on_analysis_finished()` 第390行恢复赋值之间存在时间窗口——若用户在此期间点击仍显示旧数据的分类矩阵单元格，`self._last_results['values_list']` 导致 `AttributeError: 'NoneType' object has no attribute '__getitem__'`。此守卫是方法首行（比 `if i == j` 对角跳过更早），一行改动，阻塞性。同时连接 `cellClicked` 信号时，对于 `classification[i][j] == 'err'` 的单元格也应跳过（无有效检验结果）。 -->**数据来源：** 调用 FIXME-1 中提取的公共函数 `compute_integrated_cdf(values_list[i], grid, order)` 和 `compute_integrated_cdf(values_list[j], grid, order)`——通过 `self._last_results['values_list']` 获取原始样本数组。若实施时确认 PySDTest result 对象直接暴露 `grid`/`F_a`/`F_b`，可替代为直接提取。（<!-- REVIEW-R1-FIX: ISSUE-007 -->）<!-- REVIEW-R2-FIX: ISSUE-003 —— 明确QTableWidget + cellClicked方案 --> |
| 3b | 阴影标注 max(F_a − F_b) 和 max(F_b − F_a) 区域（双向差异可视化） |
| 3c | 标注接触集（若有）和占优/交叉判定依据 |

### FIXME-4：更新文档与计划体系

| 子任务 | 描述 | 状态 |
|--------|------|------|
| 4a | 更新 [01-理论.md](docs/01-活跃/panels/策略比较/01-理论.md) §3.2——补充 DD Bootstrap 实现细节、非占优零假设说明、FSD⇒SSD⇒TSD 层次 | |
| 4b | 更新 [04-问题.md](docs/01-活跃/panels/策略比较/04-问题.md)——新增 P1 条目：「DD Bootstrap 双向过度显著——中心化未正确施加非占优约束」 | |
| 4c | 更新 [P19 未完成清单.md](docs/01-活跃/panels/策略比较/P19 未完成清单.md)——从 Phase 3 暂缓中移除旧「效应量热力图」条目（已被 P45 FIXME-2 取代） | |
| 4d | ~~更新 [模块状态矩阵.md](docs/00-meta/模块状态矩阵.md)——注册 P45~~ | ✅ 已完成（矩阵中已有 P45 行） |
<!-- REVIEW-R1-FIX: ISSUE-009 --> | 4e | 更新 [CLAUDE.md](CLAUDE.md)——在技术栈部分添加 PySDTest v0.0.21 为 L2 随机占优可选依赖；在扩展指南表格确认 `comparison_analyzer` 条目是否需要补充 `dd_bootstrap_test_v2` / `compute_dominance_matrix_v2` 行 | |
<!-- REVIEW-R1-FIX: ISSUE-008 --> | 4f | 更新打包文档 `docs/01-活跃/subsystems/应用打包/02-实施.md`——在 hiddenimports 列表追加 `pysdtest`（若适用） | |

---

## 三、校准实验

### 3.1 实验结果 (2026-06-15 完成)

校准脚本 `tools/calibrate_pysdtest.py`，30 次重复 × 3 样本量 (100/500/2000) × 4 场景，PySDTest `test_sd_SR` (nboot=200, a=0.1)，总耗时 87 分钟。

**方向约定：** PySDTest 采用「值更高 = 占优」经济学惯例。正向 GDR 直接送入；负向（-）GDR 取负号后送入。分类中「A ≻ B」统一解读为「A 优于 B」。

**S1-S4 全量结果（方向修正后）：**

| 场景 | 描述 | n=100 | n=500 | n=2000 | 目标 | 判定 |
|------|------|-------|-------|--------|------|------|
| S1 | A~N(70,10) vs B~N(80,10) —— B 严格占优 A | B≻A 100% | B≻A 100% | B≻A 100% | >90% | ✅ |
| S2 | A~N(75,5) vs B~N(75,15) —— CDF 交叉 | × 100% | × 100% | × 100% | >80% | ✅ |
| S3 | A~N(75,10) vs B~N(75.1,10) —— 几乎相等 | = 93.3% | = 90.0% | = 83.3% | >80% | ✅ |
| S4 | A~χ²(5) vs B~χ²(6) —— B 值更高，FSD 无误报 | 双向 0% | 双向 0% | 双向 0% | <10% | ✅ |

**S4 的 SSD 预判修正：** 原预期「A χ²(5) SSD 占优 B χ²(6)」在 Barrett-Donald「高值 = 占优」框架下不成立——B 均值 6 > A 均值 5，严格 B 占优 A。检验在所有样本量下一致判定 B≻A，行为正确。另 χ²(5) vs χ²(6) 的 CDF 理论交叉点在极左尾 (x<1)，实际样本不可检测——原始「FSD 交叉」预判已移除。

### 3.2 完成门控（更新）

<!-- REVIEW-R3-FIX: ISSUE-GATE-6 —— G3/G4/FIXME-3 验收标准/边界覆盖均补充具体输入、期望输出与操作步骤 -->

| 门控 | 条件 | 状态 |
|------|------|------|
| **G0 校准** | S1-S4 方向修正后全部通过（校准实验已完成） | ✅ |
| **G2 性能** | 3 策略 nboot=500 首屏 < 30s；5 策略 nboot=500 < 90s。提供 nboot 滑块（200/500/1000/2000）供用户权衡速度/精度 | 待测 |
| **G3 回归** | 现有面板功能不受影响。<!-- REVIEW-R4-FIX: GATE-6-测试策略 —— 测试文件创建职责与分阶段验收 -->**测试文件创建分派：** `tests/core/test_comparison_analyzer.py` 由任务 1b 在实现 `compute_dominance_matrix_v2()` 时同步脚手架（含 3 个基础用例：`test_dd_bootstrap_v2_basic`/`test_dominance_matrix_v2_shape`/`test_benjamini_hochberg_preserves_order`）；`tests/gui/test_comparison_analysis_panel.py` 由任务 2a2 在实现 `_render_classification_matrix()` 时同步脚手架（含 `test_classify_dominance_smoke`/`test_classification_result_smoke`）。**分阶段验收：** 任务 1b 完成时执行 `pytest tests/core/test_comparison_analyzer.py -q`（仅 core 层）；任务 2a2 完成时追加执行 `pytest tests/gui/test_comparison_analysis_panel.py -q`（GUI 层）。**全量回归命令**（任务 5 执行）：`pytest tests/core/test_comparison_analyzer.py tests/gui/test_comparison_analysis_panel.py tests/service/test_batch_service.py -q --cov=gacha_simulator/core/comparison_analyzer --cov=gacha_simulator/gui/comparison_analysis_panel`，所有用例通过。关键测试用例及期望：① `test_dd_bootstrap_v2_basic`——两正态样本 n=200，返回 dict 含 `p_value`/`test_stat`/`critical_val` 且 `0 <= p_value <= 1`；② `test_dominance_matrix_v2_shape`——3 策略输入返回 3×3 矩阵，对角为 None；③ `test_benjamini_hochberg_preserves_order`——含极显著+不显著混合 p 值列表，校正后显著项 q<0.05，且校正后排序与原始 p 值排序一致（BH 保序性） | 待测 |
| **G4 UI** | 用户理解度测试——协议如下：① 使用项目中 2-3 个真实策略对比场景的数据（或 S1-S4 校准场景数据），每组至少含一个占优场景（如 S1）、一个交叉场景（如 S2）、一个无差异场景（如 S3）；② 每位用户独立完成测试——先观察分类矩阵（不提供任何提示），口头解释 2-3 个单元格含义（如「为什么这个格是 ≻(FSD)」「× 是什么意思」「= 代表什么」）；③ 通过标准：3 人均正确解释至少 2/3 的测试单元格（单纯猜测概率 <5%）；④ 若未达标，记录误解模式作为后续标签文案或图例改进依据；⑤ 问卷提纲记录每位用户对以下问题的回答：（a）能否区分 ≻ 和 ≺ 的方向？（b）× 和 = 的区别是否清晰？（c）图例是否足够帮助理解？ | 待测 |
| **G5 FIXME-3 视觉** | 积分 CDF 曲线渲染正确——检查清单：(a) 选择 S1 严格占优场景（如 A~N(70,10) vs B~N(80,10)），点击分类矩阵中 (A,B) 格，确认 F_a 积分 CDF 完全在 F_b 之上，`max(F_a−F_b)` 差异区域阴影（红色半透明）正确标注在曲线间且边界准确；(b) 选择 S2 交叉场景（如 A~N(75,5) vs B~N(75,15)），确认两条积分 CDF 曲线在网格中部交叉，`max(F_a−F_b)` 和 `max(F_b−F_a)` 标注点分别位于交叉点两侧，差异区域着色切换正确；(c) 选择 S3 几乎相等场景（如 A~N(75,10) vs B~N(75.1,10)），确认两条曲线几乎重叠、阴影区域极小（肉眼近不可见）；(d) 切换 1/2/3 阶 tab 或子图，确认阶数越高曲线越平滑（高阶积分累积效应）；(e) 点击对角线 (i,i) 格不触发渲染、无错误。 | 待测 |
| **G6 边界覆盖** | 执行边界验证脚本（建议新建 `tests/core/test_comparison_boundary.py` 或追加至现有测试文件）：① **n=2 最简场景**——2 策略输入，分类矩阵应为 2×2，验证 `_classify_dominance()` 产出标签非空且对角线为 `—`，FSD/SSD/TSD p 值矩阵维度正确；② **全相等分布**——同一数据复制为两个策略（`np.random.seed(42); data = np.random.normal(0,1,500); values_list = [data, data.copy()]`），预期分类为 `=`（无差异），验证非 `×` 或 `≻`/`≺`（允许少数样本量导致 `=` 降级为其他标签——此时记录降级率，确保不是系统性错误分类）；③ **(-)GDR 方向正确性**——使用已知成本型 GDR（如 miss_rate 原始数据：A 均值 0.1, B 均值 0.3，B 更差），传入 `lower_is_better=True`，验证：分类矩阵上方出现方向提示横幅；`≻` 标签指向真实更优方（A 优于 B，因为 A 的 miss_rate 更低）；数据取反逻辑未静默跳过（可通过检查 `compute_dominance_matrix_v2` 内部 `a = -values_list[i]` 是否确实被执行）；④ **BH FDR 校正不改变排序**——验证 `matrix_raw` 中原始 p 值排序与 `matrix` 中校正后 q 值排序一致（BH 保序性）；⑤ **种子复现性**——固定 `rng_seed=42`，连续两次运行 `compute_dominance_matrix_v2()`，验证 `matrix` 数值完全一致（逐元素 `np.allclose`）。 | 待测 |

> **G2 性能分析详见 §五末尾 [性能测算附录](#性能测算附录)。** 简言之：校准实验实测单次 `test_sd_SR`(nboot=200) ≈1.4s；nboot=2000 线性外推 ≈14s/次。3 策略 18 次调用 nboot=200 耗时 ~25s。原 <5s 门控与实测差一个数量级，已修正为现实值。首屏默认 nboot=500（≈3s/次，3 策略 ~54s），用户可调滑块。

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

<!-- REVIEW-R3-FIX: ISSUE-GATE-1 —— 顶层任务拆分为 ≤1h 子任务，确保实施时每小时有检查点 -->
**总计时（剩余）：** 7.7h | **已完成：** 1.5h (FIXME-0) + 0.1h (FIXME-0.5 pending)

### 任务 0（已完成）

| 子任务 | 内容 | 预估 | 状态 |
|--------|------|------|------|
| 0 | `pip install PySDTest` + S1-S4 校准实验 | 1.5h | ✅ 完成 (2026-06-15) |
| 0.5 | `comparison_analysis_panel.py:404` `self.status_label` → `self._loading_label` 修复（一行改动，降低后续调试障碍）<!-- REVIEW-R2-FIX: ISSUE-002 --> | 0.1h | 🔜 下一步（FIXME-1 之前） |

### 任务 1：核心检验替换 + 数据流重构（FIXME-1，总计 2.8h）

<!-- REVIEW-R3-FIX: ISSUE-GATE-1 —— 拆为 1a/1b/1c 三个 ≤1h 子任务 -->

| 子任务 | 内容 | 预估 | 依赖 |
|--------|------|------|------|
| **1a** | PySDTest 适配器 (`dd_bootstrap_test_v2`) + ImportError 兜底 (`_PYSDTEST_AVAILABLE`) + `np.trapz`→`np.trapezoid` 兼容层（**两处：** `compute_integrated_cdf` 公共函数 + `dd_bootstrap_test()` v1 回退闭包——详见 AUDIT-BREAK-3 修复指令）+ `ngrid=100` 硬编码依据注释 + `a=0.1` 硬编码依据注释 + PySDTest 异常捕获 try/except（AUDIT-BREAK-2：`dd_bootstrap_test_v2` 内部 `test.testing()` 异常 → 返回 `p_value=None`）。<!-- REVIEW-R5-FIX: AUDIT-BREAK-2, AUDIT-BREAK-3 —— 异常安全 + np.trapz 兼容列入显式交付 -->**产出：** `dd_bootstrap_test_v2` 函数可独立调用，PySDTest 不可用时抛清晰 ImportError；`dd_bootstrap_test()` v1 闭包 `np.trapz` 已替换为 `_trapz` 兼容层。**验收：** `from gacha_simulator.core.comparison_analyzer import dd_bootstrap_test_v2` 成功；无 PySDTest 环境抛 `ImportError("PySDTest 未安装...")`；`grep 'np\.trapz(' gacha_simulator/core/comparison_analyzer.py` 返回空。 | **1.0h** | 任务 0.5 |
| **1b** | BH FDR 校正 + `compute_dominance_matrix_v2` 伪代码实现（阶段 1-3 循环：n×n 原始 p 值收集 → `benjamini_hochberg()` 批量校正 → 回填 `matrix`/`classification` 矩阵）+ `lower_is_better` 取反逻辑 + PRNG 种子入口一次性设置（`np.random.seed(rng_seed)` 后 `seed=None` 透传，每对顺序消费不重置）。<!-- REVIEW-R4-FIX: GATE-6-测试策略 —— 同步脚手架 core 测试文件 -->**同步产出：** 创建 `tests/core/test_comparison_analyzer.py`，含 3 个基础用例——`test_dd_bootstrap_v2_basic`（两正态样本 n=200，验证返回值结构）、`test_dominance_matrix_v2_shape`（3 策略 → 3×3 矩阵，对角 None）、`test_benjamini_hochberg_preserves_order`（校正后排序与原始 p 值排序一致）。**产出：** `compute_dominance_matrix_v2()` 函数可独立调用，返回形状符合 §FIXME-1 返回值形状表。**验收：** `result = compute_dominance_matrix_v2(values, names)` 的 `result['matrix']` 为 BH 校正后 p 值矩阵，`result['classification']` 为 per-order sig/ns 标记矩阵；`pytest tests/core/test_comparison_analyzer.py -q` 3 个用例全部通过 | **1.0h** | 任务 1a |
| **1c** | V1/V2 派发 (`compute_dominance_matrix` + `engine='auto'` 自动检测) + `core/__init__.py` 导入同步 (`dd_bootstrap_test_v2`, `compute_dominance_matrix_v2`, `compute_integrated_cdf`) + `compute_integrated_cdf` 公共函数提取（从 `dd_bootstrap_test:229-238` 闭包提取为模块级函数，FIXME-3 前置依赖）+ `pyproject.toml` 依赖声明（`analysis` + `gui` extras）+ `ComparisonWorker.run()` 第67行 `n_bootstrap=500` 统一 + **ISSUE-001 `lower_is_better` 参数透传**（`ComparisonWorker.run()` 第67行追加 `lower_is_better=lower_is_better`）+ **ISSUE-004 dominates 矩阵移除**（阶段 4 代码删除，`'dominates': None`）+ **ISSUE-036 跨阶种子差异化**（`rng_seed=42+order`）+ **ISSUE-037 rng_seed 透传链**（`ComparisonWorker.__init__` 追加 `rng_seed=42`）。**产出：** 完整调用链 `ComparisonWorker.run() → compute_dominance_matrix(engine='auto') → compute_dominance_matrix_v2()` 可运行。**验收：** GUI L2 刷新后看到 v2 路径结果（分类矩阵含 `matrix_raw` 键）；`pip install -e ".[gui]"` 自动安装 PySDTest。<!-- REVIEW-R1-FIX: ISSUE-003,004,005,007,008,016 --><!-- REVIEW-R2-FIX: ISSUE-001,004 --><!-- REVIEW-R3-FIX: ISSUE-036,037 --> | **0.8h** | 任务 1b |

### 任务 2：UI 分类矩阵 + 警示横幅（FIXME-2，总计 2.3h）

<!-- REVIEW-R3-FIX: ISSUE-GATE-1 —— 拆为 2a/2b 两个 ≤1.2h 子任务 --><!-- REVIEW-R4-FIX: GATE-1-变更粒度 —— 进一步拆为 2a1/2a2/2b1/2b2 四个子任务（均 ≤0.6h），纯逻辑/UI 分离 + v1 路径/布局分离，确保实施时每小时有检查点 -->

| 子任务 | 内容 | 预估 | 依赖 |
|--------|------|------|------|
| **2a1** | `_classify_dominance(p_ij: Dict[int, float], p_ji: Dict[int, float]) -> ClassificationResult` 函数实现——含 6 条判定规则 + `_check_higher_order_consensus(p_ij, p_ji, cross_order) -> bool` 降级决策表三状态逻辑（保留 × / 降级 ×? / 矛盾保留 ×）+ `ClassificationResult` @dataclass（`frozen=False`，`label: str` + `effect_size_slot: Optional[str] = None`）。**纯逻辑模块——不依赖 PyQt6/QTableWidget，可独立单元测试。产出：** `_classify_dominance()` 函数可独立调用，返回 `ClassificationResult` 对象。**验收：** 使用 S1-S4 校准场景的已知 p 值矩阵（从 `calibrate_pysdtest.py` 提取三阶双向 p 值），验证分类标签与预期一致——S1→≻/≺, S2→×(FSD), S3→=, S4→≻。<!-- REVIEW-R1-FIX: ISSUE-001,002 --><!-- REVIEW-R2-FIX: ISSUE-001,002,006 --><!-- REVIEW-R4-FIX: GATE-1-变更粒度 --> | **0.6h** | 任务 1c |
| **2a2** | `_update_l2()` 两阶段控制流重写（阶段 0 分类矩阵构建——调用 `_classify_dominance()` 消费三阶双向 p 值 → 阶段 1 逐阶 p 值矩阵渲染——保持现有 HTML 渲染逻辑）+ `self._classification_table = QTableWidget()` 实例化（`_setup_ui()` L2 布局中新增）+ `_render_classification_matrix(self, classification: List[List[str]], names: List[str]) -> None` 渲染方法（逐格填入分类符号 + `COLOR_MAP` 背景色 + 对角线 `setFlags(Qt.NoItemFlags)`）+ ISSUE-038 复合标签颜色判定——`label[0]` 首字符方案，`COLOR_MAP = {'≻': '#2e7d32', '≺': '#c62828', '×': '#ef6c00', '=': '#757575', '—': '#e0e0e0'}`。**产出：** `_update_l2()` 可产出分类矩阵并写入 `self._classification_table`，`cellClicked(int, int)` 信号已连接占位方法（为 FIXME-3 预留）。**验收：** 运行任意策略对比 GUI，分类矩阵非空且单元格颜色与标签一致（`≻`绿/`≺`红/`×`橙/`=`灰/`—`禁用灰）。<!-- REVIEW-R1-FIX: ISSUE-013,015 --><!-- REVIEW-R2-FIX: ISSUE-001,002,006 --><!-- REVIEW-R3-FIX: ISSUE-038 --><!-- REVIEW-R4-FIX: GATE-1-变更粒度 --> | **0.6h** | 任务 2a1 |
| **2b1** | v1 回退警示横幅——在 `_update_l2()` 阶段 0 检测 `dom_results[1]` 是否含 `matrix_raw` 键（v2 独有），不含则判定为 v1 回退路径，在分类矩阵上方渲染黄色警示 `<div>`：「⚠️ PySDTest 不可用，当前使用等式中心化 Bootstrap（v1 回退）。检验 p 值未经多重比较校正（无阶内 BH FDR），分类结论可能过度乐观。建议执行 `pip install pysdtest` 以获得正确的 Donald-Hsu 2016 选择性重中心化检验。」+ v1 回退路径 `BootstrapEngine` 行为不变性验证（确认 `dd_bootstrap_test()` 在 v1 路径下仍可正常运行——无回归引入的崩溃）+ ISSUE-005 p 值矩阵图例文字条件切换——v2 路径（`dom` 含 `matrix_raw` 键）图例标注「FDR q<0.05」+ tooltip: "使用 Benjamini-Hochberg 阶内 FDR 校正"；v1 回退路径（`dom` 不含 `matrix_raw` 键）图例保持「p<0.05」。**产出：** v1/v2 路径的图例文字自动切换 + v1 回退警示横幅。**验收：** `pip uninstall pysdtest -y` 后启动 GUI 运行策略对比，分类矩阵上方出现黄色警示横幅 + p 值矩阵图例显示「p<0.05」；`pip install pysdtest` 后横幅消失 + 图例显示「FDR q<0.05」。<!-- REVIEW-R2-FIX: ISSUE-002,005 --><!-- REVIEW-R4-FIX: GATE-1-变更粒度 --> | **0.6h** | 任务 2a2 |
| **2b2** | (-)GDR 方向提示行——`lower_is_better` 为 True 时，在分类矩阵上方渲染提示：「⚠️ 当前 GDR 为 (-) 成本型指标，"≻" = 更低更好」+ L2 最终布局调整——垂直排列：方向提示行（条件）→ 分类矩阵 QTableWidget → v1 回退警示横幅（条件）→ p 值矩阵 QLabel 三张（FSD/SSD/TSD）+ 各 QLabel 垂直间距微调确保可读性。**产出：** 完整的 L2 区域最终布局，所有条件性元素（方向提示/回退横幅）按触发条件正确显隐。**验收：** 切换正向/负向 GDR 后刷新 L2，(-)GDR 下方向提示行正确显示、正向 GDR 下隐藏；卸载 PySDTest 后 v1 回退横幅 + (-)GDR 方向提示两行同时显示时布局无重叠/溢出。<!-- REVIEW-R2-FIX: ISSUE-005 --><!-- REVIEW-R4-FIX: GATE-1-变更粒度 --> | **0.5h** | 任务 2b1 |

### 任务 3：集成 CDF 可视化（FIXME-3，总计 1.5h）

<!-- REVIEW-R3-FIX: ISSUE-GATE-1 —— 拆为 3a/3b 两个 ≤0.8h 子任务 -->

| 子任务 | 内容 | 预估 | 依赖 |
|--------|------|------|------|
| **3a** | QTableWidget `cellClicked(int, int)` 信号连接 + `_render_l2_chart(i, j)` 方法骨架——**参数校验顺序：** (1) 首行 `if self._last_results is None: return`（<!-- REVIEW-R5-FIX: AUDIT-BREAK-6 —— 阻塞性 None 守卫，防止 set_datasets()→_on_analysis_finished 时间窗口内点击崩溃 -->）；(2) `if i == j: return` 对角线跳过；(3) `if classification[i][j] == 'err': return` 失败检验跳过 + PySDTest 网格一致性验证——优先从 `test.result` 提取 `grid`/`F_a`/`F_b`，不可用时使用 `compute_integrated_cdf` 独立计算 + Plotly FigureWidget 创建 + ChartWebView 嵌入（参考 L1 `_chart_view` 模式）。**产出：** 点击分类矩阵 (i,j) 格，下方出现 Plotly 容器（空图或占位文本），控制台无错误。**验收：** 点击 (0,1) 格触发 `_render_l2_chart(0,1)`，Plotly 容器可见；点击对角线 (0,0) 不触发；正在运行新分析时点击旧单元格不崩溃。<!-- REVIEW-R1-FIX: ISSUE-007 --><!-- REVIEW-R2-FIX: ISSUE-003,004 --> | **0.8h** | 任务 2b2 |
| **3b** | 积分 CDF 曲线渲染（1/2/3 阶三条子图或 tab 切换）+ max(F_a−F_b) 和 max(F_b−F_a) 差异区域着色（`fill_between` 红色/蓝色半透明阴影）+ 接触集标注（若可从 PySDTest 提取）+ 交互说明 tooltip。**产出：** 完整的 Click-to-expand 交互可视化。**验收：** 见下方 G7 视觉验收检查清单。 | **0.7h** | 任务 3a |

### 任务 4-5：文档与测试（总计 1.0h）

| 子任务 | 内容 | 预估 | 依赖 |
|--------|------|------|------|
| 4 | FIXME-4：文档更新（4a-4f，4d 已完成） | 0.5h | 任务 1c+2b2+3b |
| 5 | <!-- REVIEW-R4-FIX: GATE-6-测试策略 —— 明确任务5范围：执行全量回归 + G6 边界验证（非从零编写） -->回归测试——执行 G3 全量门控命令（`pytest tests/core/test_comparison_analyzer.py tests/gui/test_comparison_analysis_panel.py tests/service/test_batch_service.py -q --cov`）+ G6 边界验证（§3.2 G6 六项边界用例——n=2 最简/全相等分布/(-)GDR 方向/BH 保序性/种子复现性/对角空值，追加至 `tests/core/test_comparison_boundary.py`）+ 门控汇总。注意：`test_comparison_analyzer.py` 和 `test_comparison_analysis_panel.py` 的基础用例已在任务 1b/2a2 中脚手架——本任务仅执行全量命令、追加 G6 边界用例、修复发现的回归问题。若 1b/2a2 中脚手架未完成，本任务包含补齐缺失用例的时间（上限 0.2h） | 0.5h | 任务 1c+2b2+3b |

---

### 性能测算附录

**校准实验实测数据（PySDTest `test_sd_SR`, nboot=200, n=500, 30 reps）：**

| 场景 | 6 次调用总耗时 | 单次 |
|------|---------------|------|
| S1 | 248.8s | ~1.4s |
| S2 | 252.8s | ~1.4s |
| S3 | 244.4s | ~1.4s |
| S4 | 284.4s | ~1.6s |

**按 nboot 线性外推（单次调用）：**

| nboot | 单次耗时 | 3 策略 (18 次) | 5 策略 (60 次) | 8 策略 (168 次) |
|-------|---------|---------------|---------------|----------------|
| 200 | ~1.4s | ~25s | ~84s | ~235s |
| 500 | ~3.5s | ~63s | ~210s | ~588s |
| 1000 | ~7s | ~126s | ~420s | ~1176s |
| 2000 | ~14s | ~252s | ~840s | ~2352s |

**结论：** 原 G2 门控「3 策略 <5s」与实测差 1-2 个数量级。首屏默认 `nboot=500`（3 策略 ~1 分钟），UI 提供 nboot 滑块（200/500/1000/2000）供用户自行调节。PySDTest 内部纯 Python 循环，无并行——可能的远期优化方向（`multiprocessing` 并行化各对检验，利用现有 11-worker 基础设施）。

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

---

## ⚠️ 自动化审查阻塞项

> 原因：6 轮对抗循环未收敛。

**未解决问题：** 0 个

**详情：** []

---

## 自动化审查记录

### 第 1 次审查（2026-06-11）——P38 工作流自动化

- 复杂度: complex | 变更性质: evolutionary
- 阶段 1 影响面: 20 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 38 个
