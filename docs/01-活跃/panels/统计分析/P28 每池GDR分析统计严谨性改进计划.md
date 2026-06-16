<!-- META: P28 | module:panels/统计分析 | status:in_progress | last:2026-06-11 -->
# P28 每池GDR分析统计严谨性改进计划

> 日期：2026-05-29 | 版本：v1
> 来源：[全模块理论严谨性系统性审查](reports/全模块理论严谨性系统性审查.md) 缺陷 17（部分）+ [补充模块理论严谨性审查](reports/补充模块理论严谨性审查.md) 缺陷 P1-P6（原 P2 已删除——无全局指标展示，Simpson 悖论不适用）
> 状态：**设计中，未实施**
> 涉及文件：`process_trace.py`、`process_analysis.py`、`per_pool_analysis.py`、`gdr.py`

---

## 一、问题概述

每池GDR分析将全局 GDR 分解到每个卡池级别，计算每池事件类型、GDR 值、成功判定，并进行 AA/BB/AB/BA 交叉分析。补充审查发现 7 项缺陷，其中 2 项严重、3 项中等、2 项低等（含 1 项已在主体审查中记录）。

### 1.1 缺陷总览

| # | 缺陷 | 严重度 | 核心问题 |
|---|------|--------|---------|
| P1 | 每池成功率无 CI——单一数值报告，用户无法区分信号与噪声 | 🔴 严重 | n=50 时 SE≈7%，噪声可能被误读为差异 |
| P2 | 单池 GDR 的 pseudo_compact 构造不完整 | 🟡 中等 | ⏳ 搁置——当前无 GDR 使用缺失字段，新 GDR 添加时再补 |
| P3 | pool_target_map 回退路径有已知缺陷（已知，主体审查缺陷 16） | 🟢 低等 | 已在 P2 中修复，需确认回退路径覆盖 |
| P4 | 资源池/兑换池在成败分析中的特殊处理不一致 | 🟢 低等 | ⏳ 搁置——相关理论不清晰，当前处理够用 |

### 1.2 涉及文件

| 文件 | 角色 |
|------|------|
| `core/process_trace.py` | PoolEvent/SampleTrace/infer_events/compute_pool_gdr |
| `core/process_analysis.py` | compute_aa/bb/ab/ba 交叉分析 |
| `core/per_pool_analysis.py` | PoolSnapshot/CumulativeSnapshot/汇总函数 |
| `core/gdr.py` | per_pool_draw_rate/target_card_draws/GDRContext |

---

## 二、缺陷详解与改进方案

### 2.1 缺陷 P1：每池成功率无不确定性量化（严重）

**现状**：对 K 个池各自计算 GDR 值 → 与全局阈值比较 → K 个布尔成功判定 → 汇总为每池成功率（`success_count / N`）。纯描述统计，未检验假设、未计算 p 值——因此不存在多重比较校正问题。真正的问题是：**成功率以单一数值报告，无置信区间**。n=50 时 SE≈7%，用户可能把噪声当信号。

各池成功率之间存在负相关（早期池高消耗损害后续池），但 CI 无需为此校正——CI 描述的是单池估计精度，非跨池比较。

**推荐方案**：
1. **Wilson 得分区间**：每池成功率附加 95% Wilson CI。边界处（p≈0 或 p≈1）优于 Wald 区间，Wald 在 n=100 且 p=0.95 时下界可达 0.91，Wilson 为 0.89（更保守、更准确）
2. **低样本量标注**：n<30 时标注「低样本量，CI 可能不可靠」
3. **在每池分析面板标注**：「此为探索性分析——各池成功率来自同一模拟批次的相互依赖观测。CI 仅反映单池估计精度，不控制跨池比较的族错误率」

**文献**：Wilson (1927, *JASA*); Brown, Cai & DasGupta (2001, *Statistical Science*)

---

### 2.2 缺陷 P2：单池 GDR 的 pseudo_compact 构造不完整（中等）

**现状**：`compute_pool_gdr_single_pool` 构造伪 `compact` 字典传给 `compute_gdr_from_compact`，但缺少多个字段：`no_draw_resources`、`strategy_name`、`result_version`、各池资源的完整初始值和增益。

当前所有 GDR 指标不使用缺失字段——但未来新增 GDR 若依赖它们，单池模式会静默失败。

**推荐方案**：
1. 补全 `pseudo_compact` 中所有可获取的字段
2. 在 `GDRContext` 中添加 `available_fields` 元数据——GDR 计算函数声明所需字段
3. 若 `pseudo_compact` 缺少某 GDR 所需的字段，跳过该 GDR 并记录警告日志（而非返回 None/错误值）

---

### 2.3 缺陷 P3：pool_target_map 回退路径（低等，已知）

已在 P2 中修复主路径，但回退路径仍可能触发旧缺陷。需确认 `_infer_from_draw_sequence` 和 `_infer_from_aggregate` 两路径在 `pool_target_map=None` 时的行为，确保 skip/ignore 判定修正覆盖所有路径。

---

### 2.4 缺陷 P4：资源池/兑换池的特殊处理不一致（低等）

资源池和兑换池被赋予特殊事件类型，但在 AB/BA/BB 交叉分析中始终被排除。当前不影响核心分析——兑换池和资源池通常不被视为影响策略成功的主要因素。若未来需纳入兑换/资源池的经济影响，需统一处理。

**推荐方案**：在代码注释中明确标注此设计决策和未来扩展路径，避免后人误用。

---

## 三、实施路线

### 阶段一：Simpson 诊断 + Wilson CI + inf 修复（预计 1-2 天）

| 任务 | 涉及文件 | 修复内容 |
|------|---------|---------|
| 每池成功率 Wilson CI | `per_pool_analysis.py` | `PoolSnapshot` 新增 `ci_lower`/`ci_upper` 字段 |
| UI CI 展示 | `analysis_panel.py`, `process_analysis_panel.py` | 成功率旁显示 CI + n<30 低样本量标注 |
| 面板标注 | `process_analysis_panel.py` | 「此为探索性分析...」说明文字 |

### 阶段二：pseudo_compact 补全（预计 1-2 天）

| 任务 | 涉及文件 | 修复内容 |
|------|---------|---------|
| pseudo_compact 补全 | `process_trace.py` | 补全可获取字段 + GDR 依赖声明 |

### 阶段三：可选深化（后续评估）

| 任务 | 说明 |
|------|------|
| 层次贝叶斯模型 | 完整的事件类型协方差建模（Gelman et al., 2013） |
| 资源池/兑换池统一 | 在 AB/BA/BB 中纳入兑换/资源池的经济影响 |

---

## 四、与现有计划的关系

- **P2（过程分析续）**：P2 已实现裸比例 + Wilson CI + low_sample 标记 + skip/ignore 修正。本计划在此基础上补充 inf 修复和 pseudo_compact。
- **P27（转变分析严谨性）**：P27 的 Wilson CI 实现可复用至本计划的每池成功率 CI。

---

## 五、测试策略

| 测试 | 说明 |
|------|------|
| Wilson CI 边界测试 | p=0/0.5/1.0 极端情况 + n=10/100/1000 |
| 经验贝叶斯测试 | Beta MLE 先验拟合 + 不同 n 下的收缩行为 |
| pseudo_compact 补全测试 | 新 GDR 指标依赖声明 + 缺失字段警告 |
| BA inf→NaN 测试 | 分母为 0/非零的返回值验证 |

---

*本计划覆盖 4 项理论缺陷（1 项严重、1 项中等、2 项低等）。原 P2（Simpson）删除——无全局指标。原 P3（Laplace）已由 P2 修复。原 P4（BA inf）已返回 None，非 inf。建议优先实施 Wilson CI 方案。*
