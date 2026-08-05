<!-- META: P72 | module:panels/统计分析 | status:draft | last:2026-08-05 | depends:P61✅,P58✅ | priority:medium -->
# P72 每池分析语义界定——banner 与 pool 双层结构的组合与拆分模式

> 日期：2026-08-05 | 更新：2026-08-05 | 状态：占位（设计待启动）| 优先级：中
> 来源：P58 第 3 轮核查暴露——「每池」分析在 banner/pool 双层结构下语义未界定，导致消费点键层级混乱（N1/N2/N3 均为其具体表现）
> 背景：P61 引入 Banner（内含多 Pool）后，「每池」到底指什么没有统一裁决——部分消费方按 banner 级、部分按 pool 级，系统性错配

---

## 1. 占位说明

本计划为**占位计划**——登记编号、梳理问题面。核心主题是 **banner/pool 双层架构下「每池」分析语义如何界定**：分析单元是「组合模式」（banner 内所有 pool 合为一个分析单元）还是「拆分模式」（每个 pool 单独一个分析单元）？还是两者并存、按场景选择？键层级错配只是该语义未界定后的技术表象。转变分析/累积快照/每池分析是承载该语义的具体功能。

## 2. 问题面

### 2.1 双层结构现状

P61 后配置单位为 Banner（`[[banner]]`，内含多 Pool + Lifecycle）。运行时一个 Banner 内可含多个 pool（生命周期切换、复合池）。因此「池」存在**两个层级**：

- **banner 级**：一个完整 Banner（可能含多个 pool），有独立的时间窗口（`available_from/until`）、生命周期、结束语义
- **pool 级**：Banner 内的单个池（`b1.main`/`b1.step1`），有独立的抽卡分布、成本、保底配置

### 2.2 「每池」分析的语义困境（本计划的核心设计问题）

「每池 xxx」（每池抽卡数/目标卡数/保底数/成功率/转变分析/截止每池 GDR）中的「每池」到底指哪个层级？候选模式：

**组合模式（banner 聚合）**：一个 Banner 内所有 pool 合为一个「分析单元」。
- 语义：以 Banner 为粒度，回答「这个卡池活动整体表现如何」
- 适合：玩家视角（玩家面对的是「这个池子」抽 300 发）；时间窗口/结束语义是 banner 级
- 现实现象：`pool_end_times`/`cumulative_snapshots` 已用 banner 键，本质是组合模式

**拆分模式（pool 独立）**：每个 pool 单独一个「分析单元」。
- 语义：以单个 pool 为粒度，回答「每个具体池的抽卡分布/保底表现」
- 适合：池子设计评估（每个 pool 的分布/成本/保底独立，值得单独看）
- 现实现象：`pool_card_counts`/`pool_draw_counts` 已用全限定 pool 键，本质是拆分模式

**关键问题**：
1. 两种模式是否**并存**？还是统一为一种？
2. 若并存，哪些分析该用组合、哪些该用拆分？按什么原则分配？
3. 「截止每池的 GDR」「转变分析」「成功率 per-pool」这类**按时间分段**的分析，天然是「组合模式下的分段」还是「拆分模式下的单池」？——这是 N1/N2/N3 纠缠的核心

### 2.3 键层级混乱（语义未界定的技术表现）

**键空间基准（P58 第 3 轮核查核实）：**

| 数据源 | 键空间 | 反映的模式 |
|--------|--------|-----------|
| `pool_end_times` | banner_id（`b1`） | 组合模式（banner 结束语义） |
| `cumulative_snapshots`（streaming） | banner_id | 组合模式（按 banner 分段） |
| `pool_card_counts`/`pool_draw_counts`/`pool_pity_counts` | 全限定（`b1.main`） | 拆分模式（每 pool 独立） |
| `draw_pool_ids`/`bonus_events[].pool_id` | 全限定 | 拆分模式（每 pool 独立） |

**错配消费点（未裁决语义 → 拿错层级键）：**

| 消费点 | 现状 | 问题 |
|--------|------|------|
| 转变分析 `compute_transition_flags_from_gdr` | `pool_ids_ordered` 来自 `pool_end_times`（banner 键），但 single_pool 分支用其查 `pool_card_counts`（全限定） | 跨层级查，恒空（N3） |
| 转变分析 single_pool 减赠卡 | 改 `agg['card_counts']`，下游读 `pool_card_counts[pool_id]` | 减错字段（N1） |
| streaming `_check_success_draw_only`/`_update_transition` | 用**全累计表 cum_cards** 判「池子成败」，赠卡只减当前 banner | 跨 banner 赠卡残留（N2） |
| 截止每池 GDR（`cumulative_by_pool`） | `pool_ids = cumulative_snapshots.keys()`（banner 键） | 实际是「截止每 banner」 |
| process_analysis_panel 累积模式 | `_cumulative_snapshots.get(pool_id)`（pool_events 全限定键 查 banner 键表） | 跨层级查，错配 |

**正确消费点（直接读全限定表，验证性）：** 每池抽卡数/目标卡数/保底数、每池下池出卡率、`infer_events`——从全限定表取数，天然正确。

### 2.4 直接显现的三个问题（N1/N2/N3）如何在本计划自然解决

**N1（single_pool 减错字段）**：这是「拆分模式」下 draw-only 的实现错误——在拆分模式语义下，`compute_pool_gdr_single_pool` 应读 `pool_card_counts[全限定键]` 并在此减赠卡。语义界定后，修复方向即确定（N3 一并解决）。

**N2（全累计判池成败的跨 banner 残留）**：这是「组合模式 vs 拆分模式」未裁决的直接后果：
- 若转变分析采用**拆分模式**（每个 pool/时段独立判定）→ 用每段增量而非全累计表，天然无跨 banner 残留
- 若采用**组合模式**（全累计）→ 赠卡须全减（含跨 banner），且需明确「全累计判池成败」是否本就是错误语义
- 语义裁决后，N2 修法随之确定

**N3（pool_ids_ordered banner 键查全限定表）**：这是「每池」语义未界定导致 `pool_ids_ordered` 携带错误层级键。语义裁决后，`pool_ids_ordered` 应统一为「分析单元键」——组合模式下用 banner 键、拆分模式下用全限定键，并匹配对应的表。

## 3. 涉及范围（初步）

- `core/per_pool_analysis.py`（`compute_transition_flags_from_gdr` / `compute_pool_gdr_single_pool` / `compute_cumulative_snapshots`）
- `core/streaming.py`（`cumulative_snapshots` 键 / `_check_success_draw_only` / `_update_transition`）
- `core/process_trace.py`（`compute_pool_gdr_single_pool`）
- `gui/analysis_panel.py`（`cumulative_by_pool` / `transition_analysis` 的 `pool_ids_ordered` 来源）
- `gui/process_analysis_panel.py`（累积模式 GDR 键匹配）
- 测试（`tests/` 转变分析 / 累积 / 每池用例扩展——含混合抽卡与跨 banner 场景）

## 4. 后续动作

1. **裁决「每池」语义**：组合模式 / 拆分模式 / 并存按场景——这是本计划的第一步，需先定
2. 盘点全部「每池」消费点的模式归属（组合还是拆分）
3. 统一分析单元键（组合 → banner 键；拆分 → 全限定键），修复 N1/N2/N3 + 截止每池 GDR + process_analysis 累积模式
4. 补转变分析/累积/每池的混合抽卡与跨 banner 测试
5. 与 P71（事件系统重构）协调「池子成败判定」的粒度与赠卡口径

## 5. 与直接显现问题的关系（P58 第 3 轮核查）

- **N1（single_pool 减错字段）** → §2.4 自然解决（拆分模式语义下减到正确字段）
- **N2（跨 banner 赠卡残留）** → §2.4 自然解决（模式裁决后确定用增量还是全减）
- **N3（pool_ids_ordered 键层级错配）** → §2.4 自然解决（分析单元键统一）
- **截止每池 GDR / process_analysis 累积模式的同类错配** → 同属「每池语义未界定」的技术表现，一并修复
