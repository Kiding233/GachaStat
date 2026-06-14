<!-- META: P48 | module:subsystems/Bootstrap引擎 | status:shelved | last:2026-06-14 -->

# P48 Bootstrap UI 集成——整体搁置

> ⚠️ **本计划已整体搁置（2026-06-14）。** Bootstrap UI 集成的正确路径是等 P18 B2.8/B2.9（GPD 参数 Bootstrap）就绪后，为尾部估计和保守资源指标提供 CI——而非在现有面板上机械叠加 Bootstrap。

**搁置理由摘要：**
- **方案搜索面板（T5-T8）：** 趋势图每点是二项比例，应用 Wilson CI（已有）而非 Bootstrap。且 N≥500 时 MC 误差在图表上不可见。
- **脆弱性面板（T9-T10）：** 核心输出是回归曲线和山脊线图，均无 CI 的合理场景。附属状态栏汇总比例不值得单独立项。
- **最差影响面板（T11-T12）：** Bootstrap 前提不成立——保守资源通过新模拟+插值计算，非已有样本重抽样。正确方案在 P18 B2.8/B2.9。
- **数据模型改动（T1-T4）：** 添加 `success_flags` 和 `bootstrap_conditional_quantile()` 为 Bootstrap CI 服务，但所有 Bootstrap CI 场景均被搁置，无消费者。

**关联：** [P18 引擎修复计划](P18 Bootstrap稳定性分析改进计划.md)（B2.8/B2.9 是尾部 CI 的正确方案）

---

## 〇、2026-06-14 评估——原 P48（13 Task）缩减为 0 Task

2026-06-14 结合四个面板的业务逻辑（`plan_search_panel.py` / `retreat_panel.py` / `worst_impact_panel.py` / `analysis_panel.py`）和 `retreat_search.py` / `worst_impact.py` / `bootstrap.py` 的模拟数据流，对原 P48 13 个 Task 做了系统性理论严谨性与必要性评估。

### 核心发现：Bootstrap 不适用于二项比例

方案搜索面板（T5-T8）和脆弱性面板（T9）中涉及的指标本质是**二项比例**（k 次成功 / N 次模拟）。二项比例的置信区间有精确的解析解——**Wilson score interval**——它在有限样本下的覆盖概率**优于** Bootstrap 百分位法：

- Wilson CI：O(1) 解析公式，覆盖概率最接近名义水平，代码库已在 P43 成功率分析中使用（`analysis_panel.py:1339`）
- Bootstrap BCa：对二项比例无优势，计算成本 O(B·N)，B=1000 时比 Wilson 慢 ~1000 倍，且离散型数据的 BCa 校正有已知问题（Efron 1987 §6）

**结论：** 涉及二项比例的 CI 应全部使用 Wilson CI，不应使用 Bootstrap。这影响了原 T5-T9 的方法选择。

### Task 逐条判定

| 原 Task | 判定 | 理由 |
|---------|------|------|
| T1-T2 (数据模型加 `success_flags`) | **搁置** | 原为 Bootstrap CI 服务。改用 Wilson CI 后不需要保存个体 bool——Wilson 只需要 `(success_count, total)` 即可 |
| T3 (`bootstrap_conditional_quantile`) | **搁置** | 原为 T9/T11 服务。T9 改用 Wilson、T11 搁置后，此方法无消费者 |
| T4 (Phase A 验证) | **搁置** | 随 T1-T3 搁置 |
| T5-T7 (模拟层保存 flags) | **搁置** | 同 T1-T2 |
| T8 (方案搜索趋势图 CI 阴影带) | **搁置** | ① 每个点的成功率是二项比例，应用 Wilson 而非 Bootstrap；② N≥500 时 MC 误差在图表上几乎不可见（最大 SE≈2.2pp）；③ 趋势图的 X 轴为不同目标集，CI 只能量化 MC 误差而非真实不确定性，易误导 |
| T9 (脆弱性面板 CI) | **改为 Wilson CI** | `overall_failure_rate` 是二项比例，Wilson CI 成本 O(1) 且覆盖概率优于 Bootstrap。当前 GUI 仅显示点估计，添加 CI 有明确信息增益 |
| T10 (KDE 阴影带) | **搁置** | ① 百分位 Bootstrap 对 KDE 有已知覆盖不足（Hall 1992），边界处实际覆盖远低于名义水平；② 计算成本 O(B·N·grid) ≈ O(10⁹)，即使降级也远超合理范围；③ 正确替代——渐近正态带基于 `f(x)/(N·h)` 解析公式，O(grid_size)，大样本性质等价 |
| T11 (保守资源 CI) | **搁置** | Bootstrap 前提不成立——`worst_resource` 不是从已有样本计算的，而是通过新模拟 + 插值得到的。正确方案在 P18 B2.8/B2.9（GPD 参数 Bootstrap） |
| T12 (池子数 CI) | **搁置** | 同 T11 |
| T13 (收尾) | **保留（缩减）** | 仅验证 Wilson CI 改动 |

### 搁置项的后续路径

| 搁置项 | 正确方案 | 阻塞前提 |
|--------|---------|---------|
| 方案搜索趋势图 CI | Wilson CI（需先保存个体 `success_flags` 以供 Wilson 聚合） | 确认需求——N≥500 时 MC 误差在图表上不可见，视觉增量可能为负 |
| KDE 阴影带 | 渐近正态带 `f(x) / (N·h)` 解析公式 | 需独立评估必要性 |
| 保守资源 CI | P18 B2.8/B2.9 GPD 参数 Bootstrap | P18 B2.8 实施 |

---

## 文件结构

| 文件 | 职责 | 改动类型 |
|------|------|---------|
| `gui/retreat_panel.py` | 在 `_on_finished` 中追加 Wilson CI 到状态栏 | ~8 行新增 |

**不波及：** 所有 core 模块 · 所有其他 GUI 面板 · 数据模型

---

## Task 1: 脆弱性面板——总体失败率 Wilson CI

**Files:**
- Modify: `gacha_simulator/gui/retreat_panel.py:337-342`（`_on_finished` 方法中 summary 行）

### 业务背景

`RetreatWorker.run()` → `compute_vulnerability_analysis()` → `VulnerabilityAnalysis`，其中：
- `overall_failure_rate`: float——GDR 未达阈值的模拟占比（二项比例）
- `n_simulations`: int——总模拟次数

当前 GUI 仅展示：
```python
summary = (
    f"总体失败率: {analysis.overall_failure_rate:.1%}  |  "
    f"模拟次数: {analysis.n_simulations}  |  "
    f"α = {analysis.alpha}"
)
self.status_label.setText(summary)
```

用户无法区分「30% ± 0.8%（N=10000）」和「30% ± 15%（N=100）」。

### 理论依据

Wilson score interval 是二项比例的最优区间估计（Agresti & Coull 1998），覆盖概率在所有 p 值下都接近名义水平——优于 Wald CI（常用 `±1.96·SE`）和 Clopper-Pearson（保守），与 Bootstrap BCa 在 N≥200 时几乎一致，但计算成本 O(1)。

代码库已有 `wilson_ci()` 函数（`core/process_analysis.py`），被 P43 成功率分析使用。

- [ ] **Step 1: 确认 `wilson_ci` 接口**

```bash
python -c "from gacha_simulator.core.process_analysis import wilson_ci; help(wilson_ci)"
```

Expected: `wilson_ci(success: int, total: int, conf_level: float) -> Tuple[float, float]`

- [ ] **Step 2: 实现——修改 `_on_finished` 方法**

在 `gacha_simulator/gui/retreat_panel.py:337-342` 处，将原有 summary 行替换为：

```python
# gui/retreat_panel.py — _on_finished() 方法

# 原代码（替换）：
# summary = (
#     f"总体失败率: {analysis.overall_failure_rate:.1%}  |  "
#     f"模拟次数: {analysis.n_simulations}  |  "
#     f"α = {analysis.alpha}"
# )

# 新代码：
from gacha_simulator.core.process_analysis import wilson_ci

n_total = analysis.n_simulations
n_failures = int(round(analysis.overall_failure_rate * n_total))
if n_total >= 10 and 0 < n_failures < n_total:
    try:
        ci_lo, ci_hi = wilson_ci(n_failures, n_total, conf_level=0.95)
        summary = (
            f"总体失败率: {analysis.overall_failure_rate:.1%} "
            f"[{ci_lo:.1%}, {ci_hi:.1%}]  |  "
            f"模拟次数: {n_total}  |  "
            f"α = {analysis.alpha}"
        )
    except Exception:
        summary = (
            f"总体失败率: {analysis.overall_failure_rate:.1%}  |  "
            f"模拟次数: {n_total}  |  "
            f"α = {analysis.alpha}"
        )
else:
    summary = (
        f"总体失败率: {analysis.overall_failure_rate:.1%}  |  "
        f"模拟次数: {n_total}  |  "
        f"α = {analysis.alpha}"
    )
```

> **边界条件处理：**
> - `n_total < 10`：不计算 CI（样本过小，CI 无意义）
> - `n_failures == 0` 或 `n_failures == n_total`：Wilson CI 的边界情况，公式仍有效但区间极宽——依赖 `wilson_ci` 内部实现，不再额外守卫
> - `try/except`：`wilson_ci` 内部如有除零等问题，静默回退到不带 CI 的原文案

- [ ] **Step 3: 手动验证——启动 GUI**

```bash
python -m gacha_simulator.main
```

操作：
1. 配置面板 → 加载/创建配置 → 设置目标卡
2. 批量模拟面板 → 运行模拟（建议 N=500+）
3. 切换到脆弱性分析面板 → 运行脆弱性分析
4. 检查状态栏是否显示 `总体失败率: XX% [XX%, XX%]`

- [ ] **Step 4: 提交**

```bash
git add gacha_simulator/gui/retreat_panel.py
git commit -m "feat: 脆弱性面板总体失败率添加 Wilson CI 显示"
```

---

## 依赖关系

```
Task 1: 脆弱性面板 Wilson CI（独立，无前置依赖）
```

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| `wilson_ci` 接口与假设不符（参数名/返回值格式变化） | Step 1 先 `help()` 确认接口 |
| `overall_failure_rate` 精度不足以反推 `n_failures` | `int(round(rate * total))` 在 N≤100000 时误差 ≤1 条，CI 对 ±1 条不敏感 |
| Wilson CI 在极端比例（0% 或 100%）下行为异常 | `if 0 < n_failures < n_total` 守卫——边界情况不计算 CI，保持原文案 |

---

## 验收标准

- [x] ~~analysis_panel GDR 统计表格显示 Bootstrap CI（3A，已完成）~~
- [ ] retreat_panel：总体失败率后显示 Wilson CI，格式 `XX% [XX%, XX%]`
- [ ] N < 10 或 failure_rate=0%/100% 时不显示 CI（静默回退）
- [ ] `wilson_ci` 调用包裹 try/except，失败时优雅降级为不带 CI 的原文案
- [ ] 全部已有测试保持绿色
- [ ] 手动目视：脆弱性面板运行后状态栏 CI 信息正确渲染

---

## 更新记录

| 日期 | 变更 |
|------|------|
| 2026-06-13 | 从 P18 §七 提取 UI 集成部分，创建设计文档 |
| 2026-06-13 | 扩展重构为实施计划——13 个 Task，五阶段，含精确代码引用和测试用例 |
| 2026-06-14 | 评估缩减——原 13 Task 缩减为 1 Task（Wilson CI）。§〇 记录逐 Task 判定理由 |
| 2026-06-14 | 整体搁置——确认脆弱性面板三个输出（回归曲线/山脊线图/附属汇总比例）均无 CI 合理场景。正确路径等 P18 B2.8/B2.9 |
