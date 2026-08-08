<!-- META: P72 | module:panels/统计分析 | status:done | last:2026-08-08 | depends:P61✅,P58✅ | priority:medium -->
# P72 每池分析语义界定——banner 与 pool 双层结构的组合与拆分模式

> 日期：2026-08-05 | 更新：2026-08-07 | 状态：设计已裁决（转变分析暂时方案 A）| 优先级：中
> 来源：P58 第 3 轮核查暴露——「每池」分析在 banner/pool 双层结构下语义未界定，导致消费点键层级混乱（N1/N2/N3 均为其具体表现）
> 背景：P61 引入 Banner（内含多 Pool）后，「每池」到底指什么没有统一裁决——部分消费方按 banner 级、部分按 pool 级，系统性错配

---

## 1. 裁决摘要（2026-08-06 更新）

本计划已完成第一轮设计裁决。核心结论如下。

### 1.1 分析单元：跨活动边界 + 活动内分域（两个独立问题，分开裁决）

「分析单元」一词掩盖了两个不同的问题，需分开裁决：

**问题甲：跨活动边界。** 共享保底的多个活动（如复刻 banner），统计时合为一个单元还是各自独立？**裁决：各自独立，单元 = banner（活动实例）。** 共享保底是配置维度（`PityDef.pools` 可跨 banner 绑定），不改变活动边界。此裁决与 P61「GDR 以 banner 为单位」（P61 文档 §3.8）一脉相承。

**问题乙：活动内部。** 一个 banner 内的多个 pool，按什么粒度统计？**裁决：分域决定，不全局统一。**
- **归属域分析**（每池抽卡/出率/成功率/事件分类）：自然单元 = **pool**（分类就是 pool，banner 只是加总视图，不改变统计本身）
- **时间域分析**（转变分析/截止每池 GDR）：单元 = **banner**（当前）。注意这是**数据现状**而非语义不可能——pool 的开放区间数据当前不存在（`switch_to` 不记录切换时刻），pool 做时间域单元（阶段转变、截止每阶段）在语义上完全成立，属演进路径 A' 领域

> 2026-08-06 修正：初版 §1.1 将「问题甲」的裁决（banner）错误推广为所有分析的单元，现拆分为甲/乙两条。

### 1.2 归属域 vs 时间域（本计划最本质的判据）

一次模拟 = 一条事件流，每个事件携带（时间 t、池归属 p、卡 c、资源 r）。所有「per 某」统计都是对事件流的过滤 + 聚合，但过滤条件分两类不同性质：

| 维度 | 切法 | 特性 | 例子 |
|------|------|------|------|
| **归属域** | 按「事件属于哪个 pool」分类 | banner/pool 是父子分类，组合 = 加总，**天然两级展示**；不依赖跨池状态 | `pool_card_counts`、每池抽卡数/出率/成功率 |
| **时间域** | 按「事件落在哪个时刻区间」切分 | 边界 = 语义本身，累计截止点 vs 区间两端是两个不同问题；区间切换**切断跨池共享状态**（保底/资源延续），**天然单一边界** | `cumulative_snapshots`、截止每池 GDR、转变分析 |

**裁决判据**：该统计是否依赖跨池累积状态？
- 依赖 → 时间域统计（单一边界，边界一选即锁死语义）
- 不依赖 → 归属域统计（两级展示，组合是加总不是切换）

归属域统计的组合模式不是「另一种模式」，而是「分类标签向上加粗」，两级口径一致、零信息损失、同时存在。时间域统计的「另一模式」不是可选项，而是不同分析目标或语义空转（累计窗口吞掉状态反转、单池窗口切断跨池状态）。

### 1.3 三参数正交，无通用切换机制

「per 某」不是单一维度，而是三个正交参数的组合：

| 参数 | 取值 |
|------|------|
| 聚合键 | banner / pool |
| 统计域 | 局部（区间增量）/ 累计（起点到边界）|
| 二次统计 | 无 / 转变矩阵（段间关系）|

**每个消费点钉死三参数，不提供「组合/拆分」切换开关。** 原因：另一模式不是同分析的可切换参数，而是不同分析目标（聚合统计类）或语义空转（时间线类）。「可切换」会把两个不同目标硬塞进一个函数，正是 N1/N3 出错的历史土壤。

### 1.4 消费点归属盘点

| 消费点 | 聚合键 | 统计域 | 二次统计 | 类别 | 处置 |
|--------|--------|--------|---------|------|------|
| 每池抽卡/目标/保底/出率 | pool（全限定）| 局部 | 无 | 归属域 | 两级展示，键已对齐，无需改 |
| 每池成功率 | pool | 局部 | 无 | 归属域 | 第k池累积 scope 键已对齐；第k池单池 scope 与转变分析同根因（N3），挂起（<!-- REVIEW-FIX-PREV: ISSUE-102 --> 见 §2.3/§5）|
| 过程分析（infer_events / 池成败 / 事件分类）| pool | 局部 | 无 | 归属域 | 键已对齐（全限定），无需改 |
| 截止每池 GDR / 累积快照 | banner | 累计 | 无 | 时间域 | 单一边界，现状正确 |
| 转变分析 | banner | 累计 | 有（矩阵）| 时间域 | 暂时方案 A（见 §1.5），修 bug |
| 脆弱性基准资源 | banner | 累计 | 无 | 时间域 | 消费端键错配，统一键空间 |

> <!-- REVIEW-FIX-PREV: ISSUE-009 --> **两级展示核实（2026-08-07）**：本表与 §2.4 中「天然两级展示」为归属域统计的语义特性（分类标签向上加粗），但展示层实现现状需核实：analysis_panel 归属域图表（per_pool_draws/per_pool_target_rate/per_pool_pity_rate，L1054-1085，bar 图 `labels=short_ids`）用 pool_id 作内部键 + `_strip_pid` 显示名（`pool_ids` 来自 `stats.keys()`，全限定键，正确），为单级（pool 维度）展示，未见 banner 聚合（上级视图）的图表实现；L1137 的 `pid_banner` 仅用于基线取数而非聚合展示。**banner 聚合展示不属本次修复范围**，登记为归属域分析的待建展示项（演进路径 A' 之后另行立项），「键已对齐，无需改」的结论不掩盖此展示层缺口。<!-- REVIEW-FIX-PREV: ISSUE-701 --> **行归属勘误（2026-08-07）**：原注误引 L1145-1151 为「每池图表（per_pool_draws 等）」——该区间实为 cumulative_by_pool 山脊块（L1145「P51: 使用 pool_id 作为内部键」注释、L1147 `ridge_labels`、L1151 `ridge_labels[pid] = _strip_pid(pid)`），per_pool_draws 等归属域图在 L1054-1085。正因该错位，山脊块的 banner 键显示名回退缺陷（banner 键查 `pool_names` 全限定键表恒 miss、退化裸 banner id）被漏检，已登记为 ISSUE-701 在 §4.1 项 3 修复。

### 1.5 转变分析：暂时方案 A

**暂时保持 banner 序列 + 累计窗口（现状语义），只修 bug 不重构。** 吸收态问题（累计达成后 AB/BA 恒 0，转变矩阵退化为单调爬升）标注为已知限制。演进方向 A'（banner 局部窗口，真转变）见 §6，待用户后续裁决。

**边界原则（2026-08-06 第二次更新）：方向正确的现状不改，能修的 bug 都修。**
- **方向正确不改**：累计窗口（原设计）；draw-only 减赠卡（成败口径属 P71 维度 3 的领域，P72 不拍板）；脆弱性分析用 banner 键（时间域正确）；累积快照用 banner 键（时间域正确）
- **能修则修**：确定性键错配 bug（导致恒空 / 匹配不到的功能失效）
- **挂起**：N1/N2（draw-only 口径执行细节，等 P71 定口径）；single_pool 分支 + N3（绑定 §5.1 待决子项）；局部窗口（演进 A'）

详见 §4。

---

## 2. 问题面

### 2.1 双层结构现状

P61 后配置单位为 Banner（`[[banner]]`，内含多 Pool + Lifecycle）。运行时一个 Banner 内可含多个 pool（生命周期切换、复合池）。因此「池」存在**两个层级**：

- **banner 级**：一个完整 Banner（可能含多个 pool），有独立的时间窗口（`available_from/until`）、生命周期、结束语义
- **pool 级**：Banner 内的单个池（`b1.main`/`b1.step1`），有独立的抽卡分布、成本、保底配置

P61 的实质是新增了一个语义层（banner = 活动），把「活动」从「阶段」中分离。数据层键已全限定化（`pool_end_times`→banner 级、逐池键→全限定），但分析层每个消费点按各自历史习惯取键，键空间分裂，这是混乱的直接来源。

### 2.2 「每池」分析的语义困境

「每池 xxx」（每池抽卡数/目标卡数/保底数/成功率/转变分析/截止每池 GDR）中的「每池」到底指哪个层级？候选模式：

**组合模式（banner 聚合）**：一个 Banner 内所有 pool 合为一个「分析单元」。
- 语义：以 Banner 为粒度，回答「这个卡池活动整体表现如何」
- 适合：玩家视角（玩家面对的是「这个池子」抽 300 发）；时间窗口/结束语义是 banner 级
- 现实现象：`pool_end_times`/`cumulative_snapshots` 已用 banner 键，本质是组合模式

**拆分模式（pool 独立）**：每个 pool 单独一个「分析单元」。
- 语义：以单个 pool 为粒度，回答「每个具体池的抽卡分布/保底表现」
- 适合：池子设计评估（每个 pool 的分布/成本/保底独立，值得单独看）
- 现实现象：`pool_card_counts`/`pool_draw_counts` 已用全限定 pool 键，本质是拆分模式

**裁决（2026-08-06）：** 「组合/拆分」不是二选一的模式，而是两个正交维度（聚合键 × 统计域）。按 §1.2 判据逐个消费点归属：归属域统计（每池抽卡/目标/保底/成功率）天然两级展示；时间域统计（截止每池 GDR、转变分析）单一边界。无通用切换机制。

### 2.3 键层级混乱（语义未界定的技术表现）

**键空间基准（P58 第 3 轮核查核实）：**

| 数据源 | 键空间 | 反映的类别 |
|--------|--------|-----------|
| `pool_end_times` | banner_id（`b1`） | 时间域（banner 结束语义）|
| `cumulative_snapshots`（streaming）| banner_id | 时间域（按 banner 分段）|
| `banner_end_resources`/`banner_end_pity_states` | banner_id（`b1`）| 时间域（banner 结束快照，ISSUE-003）|
| `pool_card_counts`/`pool_draw_counts`/`pool_pity_counts` | 全限定（`b1.main`）| 归属域（每 pool 独立）|
| `draw_pool_ids`/`bonus_events[].pool_id` | 全限定 | 归属域（每 pool 独立）|

**错配消费点（未裁决语义 → 拿错层级键）：**

| 消费点 | 现状 | 问题 |
|--------|------|------|
| 转变分析 `compute_transition_flags_from_gdr` | `pool_ids_ordered` 来自 `pool_end_times`（banner 键），但 single_pool 分支用其查 `pool_card_counts`（全限定）| 跨层级查，恒空（N3）|
| 转变分析 single_pool 减赠卡 | 改 `agg['card_counts']`，下游读 `pool_card_counts[pool_id]` | 减错字段（N1）|
| 每池成功率「第k池单池」scope | <!-- REVIEW-FIX-PREV: ISSUE-102 --> `pool_ids_ordered` 来自 `pool_end_times`（banner 键，analysis_panel L1266-1268），scope=single_pool 走 `compute_transition_flags_from_gdr`（L1293-1303）→ per_pool_analysis single_pool 分支 → `compute_pool_gdr_single_pool`（process_trace.py L279-317）用 banner 键查全限定表 `pool_card_counts` | 跨层级查，恒判失败，成功率恒 0%（N3，与转变分析同根因）|
| streaming `_check_success_draw_only`/`_update_transition` | 用**全累计表 cum_cards** 判「池子成败」，赠卡只减当前 banner | 跨 banner 赠卡残留（N2）|
| 截止每池 GDR（`cumulative_by_pool`）| `pool_ids = cumulative_snapshots.keys()`（banner 键）| 实际是「截止每 banner」，命名误导，语义本身正确；<!-- REVIEW-FIX-PREV: ISSUE-701 --> 且山脊图/转变矩阵标题的显示名用 banner 键查 `_get_pool_names`（L1613-1635）全限定键表恒 miss、退化裸 banner id（见 §4.1 项 3）|
| process_analysis_panel 累积模式 | `_cumulative_snapshots.get(pool_id)`（pool_events 全限定键 查 banner 键表）| 跨层级查，错配 |
| 脆弱性分析 + 方案搜索链路 | `banner_end_resources`（banner 键）→ 脆弱性结果 pool_id（banner 键）→ `plan_search_panel._find_vulnerability_pool` 用 store.pools 全限定键匹配 | 跨层级查，恒空——基准资源 VI 预设/保底水位读不到；<!-- REVIEW-FIX-PREV: ISSUE-001 --> 且 `set_vulnerability_result`（L1284-1288）追加项的显示名经 `_get_pool_name`（L1290-1297）查全限定键表恒 miss、退化裸 banner id，与 `set_store` 项的 banner.name 标签不一致（同根因第三实例，见 §4.1 项 1 追加项）|
| 脆弱性分析 + 脆弱性面板（retreat_panel）| <!-- REVIEW-FIX-PREV: ISSUE-001 --> 脆弱性结果 pool_id（banner 键）→ `retreat_panel._get_pool_names`（L260-265）从 store.pools 构建全限定键表（`pool_id={banner_id}.{pool_id}`）→ `pool_names.get(pr.pool_id)`（L102-103）| 跨层级查，恒取不到，山脊线图与单池图池名退化为裸 banner_id（非 banner.name）|

**正确消费点（直接读全限定表，验证性）：** 每池抽卡数/目标卡数/保底数、每池下池出卡率、`infer_events`——从全限定表取数，天然正确。

### 2.4 归属域 vs 时间域（详细论证）

见 §1.2。补充两点：

**为什么时间域统计不能归属化：** 玩家体验由跨池累积状态决定，状态属于时间流，不属于池。`b1.step1` 出的目标卡可能靠 `b1.main` 垫刀垫出来的保底。归属域能数「卡属于哪个池」，数不出「这张卡靠什么状态出的」。归属域化不是换算法，是换问题（从「我整体进度如何」变成「这个池子单看如何」）。

**为什么归属域统计天然两级：** 归属切分里 banner ⊇ pool，合并是分类标签向上走一级，纯加法、零信息损失、不切断状态。像人口按省/按国家统计，都是「人口」这个量，两视图同时存在。

### 2.5 与 P71 的耦合

P71（过程事件系统重构）的 `infer_events` 消费 `pool_card_counts`（全限定键，已正确），判定每池事件类型与成败。注意**两个「池成败」语义在不同域**，需分开定义：

- **infer_events 池成败 = 归属域**：该 pool 自身抽出的目标卡（局部，[process_trace.py:98-174](gacha_simulator/core/process_trace.py#L98-L174)，只看该池产出，不依赖时间累计）
- **转变分析成败 = 时间域**：截止该 banner 结束时累计达成全部目标（累计）

两者共享的只是「draw-only」（赠卡不算）这层口径，**判定基准完全不同**。P71 重构「池子成败」时，须明确定义的是归属域成败（局部、按池）还是时间域成败（累计、按 banner），两者是不同语义，不得混用。P72 对转变分析的裁决（时间域、banner 单元）不约束 infer_events 的归属域成败。

## 3. 涉及范围（方案 A）

> <!-- REVIEW-FIX-PREV: ISSUE-004 --> 2026-08-07 范围声明收敛：本次交付（§4.1）全部落在 **GUI 消费端**（确定性键错配修复），`per_pool_analysis.py`/`process_trace.py` 的 single_pool 分支单元化与 `compute_pool_gdr_single_pool` 均不属本次交付（挂起，绑定 §5.1 待决子项）。实施者请勿在 core 内找本次修改点。`compute_pool_gdr_single_pool` 定义于 `core/process_trace.py`（L279-317，实际消费 `pool_card_counts` 等全限定表），`per_pool_analysis.py` L305 仅 import——此处标注归属防误找。

- `core/vulnerability.py`（`compute_vulnerability_analysis` 的 pool_id 键 = banner 级，方案搜索消费——2026-08-06 登记）+ `PoolVulnerabilityResult` 键契约注释（R1，ISSUE-006）
- `gui/plan_search_panel.py`（`set_vulnerability_result` / `_find_vulnerability_pool` 全限定键 vs banner 键匹配——2026-08-06 登记）
- `gui/retreat_panel.py`（`_get_pool_names` 键错配，与 plan_search_panel 同根因——R1，ISSUE-001）
- `gui/analysis_panel.py`（`cumulative_by_pool` 命名；banner 键消费方显示名查找适配——<!-- REVIEW-FIX-PREV: ISSUE-701 --> `_get_pool_names` 补 banner→name 映射 + `_banner_label` 辅助，供山脊图 `ridge_labels` 与转变矩阵标题 `_pool_label` 使用，见 §4.1 项 3；`transition_analysis` 的 `pool_ids_ordered` 来源，<!-- REVIEW-FIX-PREV: ISSUE-101 --> **确认不改（N3 挂起，绑定 §5.1）**：L1353-1354 该来源（`pool_end_times` 键，banner 级）在时间域语义下方向正确（§1.5 边界原则），N3 挂起、本计划不修改此来源；实施者勿动此段代码（不得「顺手修正」为全限定键），与 ISSUE-004 对 core 层的「实施者请勿在 core 内找本次修改点」声明对称）
- `gui/process_analysis_panel.py`（累积模式 GDR 键匹配 + 命名/列头语义澄清——R1，ISSUE-005）
- `gui/utils.py`（<!-- REVIEW-R1-FIX: ISSUE-117 --> **新建模块文件**——`banner_of` 统一键辅助的落点，多面板共用（plan_search_panel/retreat_panel/analysis_panel/process_analysis_panel 共 4 消费点），见 §4.1 项 5；当前 `gui/` 目录无 utils.py，本文件为新建，`banner_of` 为其首个成员）
- `core/streaming.py`（`_check_success_draw_only` / `_update_transition` 的赠卡口径——N1/N2，挂起等 P71，见 §4.2）
- `core/per_pool_analysis.py` / `core/process_trace.py`（single_pool 分支单元化 / `compute_pool_gdr_single_pool`——挂起，绑定 §5.1，见 §4.2）
- 测试（`tests/` 转变分析 / 累积 / 每池用例扩展——含混合抽卡与跨 banner 场景）
- <!-- REVIEW-R1-FIX: ISSUE-104 --> `webui/analysis_service.py` + `webui/vuln_service.py`（**遗留层，本期不改名，登记口径分叉**）：webui 是与 GUI 并行的消费链——`analysis_service.py` L163 暴露 API 方法键 `'cumulative_by_pool': self._cumulative_by_pool`、L97 `self.pool_names = {}`、L608 `labels[pid] = self.pool_names.get(pid, pid)`（池名查全限定键表恒退化）、L657 `pool_names.get` 同退化；`vuln_service.py` L124 `labels[pr.pool_id] = pr.pool_id`（裸 banner 显示名）。这些为 **web API 契约键 / web 侧独立键空间**，与 PyQt 侧 chart key 前缀（`cumulative_by_pool_`）是不同键空间。与 ISSUE-004「§4.1 交付全落 GUI 消费端」边界一致，**本期不随 PyQt 侧改名**（避免破坏 web API 契约），但须在文档记录口径分叉：PyQt 侧 chart key 改 `cumulative_by_banner` 后，webui API 键保持 `cumulative_by_pool` 不变，未来 webui 消费端立项时一并处理。<!-- REVIEW-R1-FIX: ISSUE-120 --> **POC 路由键与 webui API 方法键为同一键空间（校正「不同键空间」论断的误判部分，收敛 POC 处置）**：前述「不同键空间」只对 **PyQt 侧 chart key 前缀**（`cumulative_by_pool_`，analysis_panel 产键侧）成立；POC 路由键是**另一段**——methodDefs.js L195 `type: 'cumulative_by_pool'` 经 `api.runAnalysis(datasetId, block.type, params)` 的 method 参数直达 webui 分发器 `analysis_service.py` L166-168 `handlers.get(method)`（L163 仅注册 `'cumulative_by_pool'`），**POC methodDefs type 与 webui API 方法键是同一 wire 上的同一个键**。据此收敛：**POC 侧（methodDefs.js type + DatasetWorkbench.vue L186 ANALYSIS_API 路由键）保持 `cumulative_by_pool` 不改**，与 webui API 键保留一致（POC 为 UI 对比原型且其消费链依赖 webui 后端，改写不产生收益；若改 type 而 webui 未注册 `cumulative_by_banner` handler，pywebview 生产模式 run_analysis 必返「未知分析方法」，静默失效）。POC 键不改的连带登记：3c 同步清单对 POC 的条目由「同步替换」降级为「legacy 豁免登记」（见 §4.1 项 3 的 ISSUE-101 收敛），methodDefs.js L195 label 与 L201 result title 一并保持「截止每池」不改（ISSUE-113/ISSUE-119 据此处置）。`vuln_service.py` L124 裸 banner 显示名与 §4.1 项 1c 路线 A 的 banner 键改动同根因（banner 键显示名缺失），登记为遗留显示名缺口（不属本次修复，防实施者误把它当 plan_search_panel 的同类项顺手改入本次范围）。<!-- REVIEW-R1-FIX: ISSUE-122 --> **vuln_service 兜底消费方补登记（RetreatConfigBuilder ISSUE-101 兜底的第二个消费方）**：`vuln_service.generate_retreat_config`（L257-274）把脆弱性分析产出的 banner 键 `from_pool_id`（`_config_options` L235-253 的 `from_pools.pool_id` 同源，均来自 vulnerability.py L541-545 的 `banner_end_resources` 键空间）直接传给 `RetreatConfigBuilder.build`，走 ISSUE-101 兜底（retreat_config.py L26-32，`'.' not in from_pool_id` 时遍历序首个前缀匹配池）——与 plan_search_panel 路线 A 共享同一兜底语义的**第二个消费方**。该依赖为既有行为（脆弱性结果 pool_id 本就是 banner 键，非本次修复引入，vuln_service 一直走兜底），登记为 **webui 遗留接受项**（本期不改）；ISSUE-109 兜底回归（§4.3，`tests/core/test_retreat_config.py`）的断言对象是 `RetreatConfigBuilder.build` 公共函数本身，天然覆盖此调用方的兜底命中语义，无需为 webui 单独加回归，实施者不得因「webui 不在测试范围」而跳过 ISSUE-109 兜底回归。

## 4. 后续动作（2026-08-06 第二次更新：按边界原则收窄）

### 4.1 本计划修复（确定性键错配 bug）

<!-- REVIEW-FIX-PREV: GATE-1-change-granularity -->
**任务粒度拆解（2026-08-07 补充）：** 以下五项均为「修复块」粒度，实施前按下表拆为 ≤1h 子任务并标注预计耗时与决策依赖。决策无关子任务先行执行；决策依赖子任务须先经「⚠ 自动化审查阻塞项」裁决（或按推荐路线执行、替代路线登记为接受项）。子任务编号对应下方各条内的具体修复内容。<!-- REVIEW-R1-FIX: ISSUE-118 --> **grep 定位按类区分（防误改同名方法）**：`config_panel.py` 与 `plan_search_panel.py` 存在同名方法 `set_store`——`config_panel.set_store`（L374）仅存 store 引用，`plan_search_panel.set_store`（L1258-1261）为路线 A 修改目标，且 main_window 中两者均被调用（config_panel.set_store 于 L109、plan_search_panel.set_store 于 L112）；此外 config_panel 另有 `get_config`/`validate_banners`/`apply_to_store`/`refresh_from_store` 与各面板同名方法并存。**实施者以 grep 全量定位修改点时须按类区分**：`config_panel` 不在本计划修改范围（§3 范围 + §4.1 项 1-5 全部落在 analysis_panel/plan_search_panel/retreat_panel/process_analysis_panel/chart_webview/gui.utils），其同名方法不得改动；定位 `set_store` 修改点时以 `plan_search_panel.set_store` 为唯一目标。

**项 1（脆弱性→方案搜索链路，总约 3h）拆解：**

| 子任务 | 内容 | 耗时 | 决策 |
|--------|------|------|------|
| 1a | retreat_panel `_get_pool_names` 补 banner→name 映射（`pid.split('.')[0]` 查 banner 名）+ charts 字典键唯一性（ISSUE-121——banner.name 仅作显示标签，charts 存储键保持 banner_id，防同名 banner 图互相覆盖，见 ISSUE-001 追加项）<!-- REVIEW-R1-FIX: ISSUE-126 --> **enabled 过滤保留声明**：现 `_get_pool_names`（L260-265）含 `if pe.enabled:`（L263）只收集 enabled pool 键条目，改 banner 映射时**保留该过滤**——vulnerability 产出的 `pool_results` 键来自模拟结果 `banner_end_resources`（vulnerability.py L541-544，键空间仅含模拟参与的 banner），过滤后 enabled banner 仍命中、行为无退化；disabled banner 的脆弱性结果显示名退化裸 banner id 登记为**接受项**（与 plan_search_panel 侧 ISSUE-116 disabled banner 追加项场景对称，本处不额外为 enabled 外键扩表）| ~30min | 无关 |
| 1b | plan_search_panel `_find_vulnerability_pool` banner 匹配 + falsy 守卫（ISSUE-702 双保险；falsy 守卫在此落地一次，见项 5 边界）| ~1h | 无关（依赖项 5 提供 `banner_of`，实施顺序上项 5 先行）|
| 1c | ISSUE-002 路线 A 落地：`set_store` 按 banner 去重（每 banner 一项）+ 兜底命中验证（接受项：起始粒度 = banner，命中首个池）<!-- REVIEW-R1-FIX: ISSUE-128 --> **`_get_pool_names`（L1269-1274）处置（唯一调用点 = set_store L1257，防死代码/键退化）**：路线 A 下 `set_store` 改按 banner_id 去重、display 取 banner.name（store.pools 展平后 `pe.name` 即 banner 级名）后，全限定键表 `pool_names.get(pe.pool_id, ...)`（L1260）对 banner 键恒 miss、退化裸 id；且 ISSUE-001 追加项仅点名修 `_get_pool_name`（L1290-1297）、未点名本 helper（对比 retreat_panel 1a 与 analysis_panel 3d 的同名 helper 均已点名改造，唯 plan_search 侧遗漏）。**推荐处置：随 set_store 改造移除 `_get_pool_names`**（仅 L1257 一处调用，改后无消费方，防死代码残留）；或保留但改造为 banner_id→banner.name 映射（与 `_get_pool_name` 补层同构，`banner_id = pe.pool_id.split('.')[0] if '.' in pe.pool_id else pe.pool_id`）。二选一须在拆分记录显式写明所选项，实施者不得按计划字面「display 取 banner.name」直接用 pe.name 绕过该表却遗留未处置的死代码或退化查表| ~1h | ✅ 已裁决（路线 A）|
| 1d | PoolVulnerabilityResult 键契约注释（ISSUE-006）| ~10min | 无关 |

**项 2（process_analysis 累积模式，总约 3-4h）拆解：**

| 子任务 | 内容 | 耗时 | 决策 |
|--------|------|------|------|
| 2a | `_compute_pool_gdr` 累积模式改 banner 段取数（ISSUE-005 主改）| ~1h | 无关 |
| 2b | 列头/图表副标「截止该 banner 段」口径标注（ISSUE-005）| ~30min | 无关 |
| 2c | 未达边界 None/空快照处理（ISSUE-103/703，core 空快照返 None）| ~1h | ✅ 已裁决（路线 a，登记项 4 例外）|
| 2d-1 | 未触达投影口径声明（ISSUE-003 最小改法：纯展示层注明「该 banner 段未触达，GDR/成败系 sim 终点投影」，不改变数据与判定）| ~30min | 无关，可先行 |
| 2d-2 | 未触达识别机制（ISSUE-003）| **不做**（D5 语义 A：继承态合理，只做 2d-1 展示口径）| ✅ 已裁决（语义 A）|

**项 3（cumulative_by_pool 重命名，总约 3.5-4.5h）拆解：**

| 子任务 | 内容 | 耗时 | 决策 |
|--------|------|------|------|
| 3a-1 | analysis_panel 代码内 chart key 字符串替换（`cumulative_by_pool_` → `cumulative_by_banner_`）+ 勾选 key 构造（L1931/L1948）+ 条件收集 `startswith('cumulative_by_pool_')` **与 `== 'cumulative_by_pool'` 等值分支**（L2138-2139 整行，ISSUE-123——等值分支未同步则 `_get_conditions_for_key('cumulative_by_banner')` 永不写入 `cond['cumulative_by_pool_selections']`，`_computed_conditions['cumulative_by_banner']` 缺该键后 `_needs_computation` 对指标勾选变化恒判「不需重算」、勾选变更后图表静默不更新，与 L1089 漏改同类静默失效）+ `_chart_specs_cache` 旧前缀 prune（<!-- REVIEW-R1-FIX: ISSUE-105 --> 删除所有 `cumulative_by_pool_` 前缀条目，见下方边界注）| ~45min | 无关 |
| 3a-2 | `_get_ordered_charts` 前缀匹配适配（L2412-2435：`_CHART_DISPLAY_ORDER` 的 base_key + '_' 前缀段，改 chart key 前缀后 base_key 须同步）| ~30min | 无关 |
| 3b | ChartWebView `has_chart`/`update_chart`/`set_charts` 缓存与增量更新同步（chart_webview.py L321/L355/L291，旧前缀缓存 miss 重建）| ~30min | 无关 |
| 3c | 非代码引用同步（02-实施.md/00-档案.md/ResultChart.vue/methodDefs.js）<!-- REVIEW-R1-FIX: ISSUE-112 --> 同步范围仅限活跃文档与活跃 POC 代码；`docs/03-归档/` 与 `docs/00-meta/模块状态矩阵.md` 中的 `cumulative_by_pool` 为历史记录，显式排除不同步（见下方「不同步」声明）| ~30min | 无关 |
| 3d | 显示名适配（`_get_pool_names` 补 banner 映射 + ridge_labels/_pool_label 消费）。多池 banner 取值规则：banner 映射值取 `getattr(pe, 'name', pe.pool_id)`——store.pools 展平后 pe.name 即 banner 级名，同 banner 内多 pe 的 name 相同（现 `_get_pool_names` L1629 单池时 `names[pe.pool_id] = name`、多池时拼 `f"{name}.{pool_part}"`，新 banner 映射为 banner_id→banner.name 一级，与单池规则对齐；同一 banner 内多 pe 取值一致，无「取首个还是任一」分歧）<!-- REVIEW-R1-FIX: ISSUE-125 --> **辅助落点（修复必读，防 panel/worker 错位）**：消费点 `ridge_labels`（L1151）与 `_pool_label`（L1394）位于 AnalysisWorker（L145）的 `_run_impl` 方法内，而 `_get_pool_names`（L1613）为 AnalysisPanel 方法，两者仅经 L2173（`pool_names = self._get_pool_names()`）→ L2207（`pool_names=pool_names` 构造参数）→ L183（`self.pool_names = pool_names or {}`）的 dict 传递链耦合，且该传递在 worker 构造时快照。**推荐实现：banner 映射直接作为 `_get_pool_names` 返回 dict 的 banner_id 键条目**（键 'b1'→banner.name，与全限定键 'b1.main' 条目并存），随全量 pool_names 传入 worker 后，`_strip_pid`/`_pool_label`（均 `self.pool_names.get(pid, pid)`）对 banner 键天然命中，**无需独立 `_banner_label` 辅助**；若保留独立辅助，必须定义为 `_run_impl` 内部嵌套 def（与 `_strip_pid` 同层），**不得**实现为 AnalysisPanel 方法（worker 侧无法调用，显示名适配目标落空、山脊图仍显裸 banner id）| ~1h | 无关 |
| 3e | process_analysis_panel 下拉标签（L100）| ~10min | 无关 |

> **3a-2 与 3b 边界（同链防重复改缓存）**：chart key 前缀贯穿「analysis_panel 生成侧 → ChartWebView 消费侧」，两子任务同链但归属不同模块——**3a-2** 只改 analysis_panel 内 `_get_ordered_charts`（L2412-2435）对 `_CHART_DISPLAY_ORDER` 的 base_key/前缀收集段（生成侧收集逻辑，改 key 前缀后此处才 collect 到新 key）；**3b** 只改 chart_webview.py 的缓存与增量更新机制（`has_chart` L355 / `update_chart` L321 / `set_charts` L291，消费侧对 key miss 的重建与旧缓存清理），不改 analysis_panel。两者边界以「文件归属」划清：analysis_panel 内的 key 生成/收集归 3a-1/3a-2，chart_webview.py 内的缓存命中/重建归 3b，不得在任一子任务内跨文件重复改另一侧的缓存逻辑。若实施中发现前缀判断点遗漏，以 grep 全量确认清单为准（见项 3 详述），新增适配点按文件归属归入对应子任务。

> <!-- REVIEW-R1-FIX: ISSUE-105 --> **`_chart_specs_cache` 旧前缀键 prune（追加适配点，归 3a-1）**：analysis_panel 的 `_chart_specs_cache`（L1461 初始化；L2264/L2267 仅 `.update()` 合并新增、**无按前缀清理**；L2404 单键写入）在 chart key 改名 `cumulative_by_pool_` → `cumulative_by_banner_` 后，若同进程内存在旧前缀缓存键（长驻会话/热更新），旧键残留并经 `_get_ordered_charts`（L2432-2434）以「未匹配键」形式排在图表尾部、呈无名图表。**适配要求（归 3a-1）**：改 key 前缀处对 `_chart_specs_cache` 按旧前缀 prune（删除所有 `cumulative_by_pool_` 前缀条目），或复用 L2487 的全量 clear 时机（「清除所有结果」路径，同一次清理覆盖新旧前缀）。不得仅依赖 ChartWebView 侧的旧缓存 miss 重建——消费侧重建不等价于产键侧清理，旧前缀键仍会经 `_get_ordered_charts` 尾部兜底出现。回滚侧说明见 §4.4 (a)。

**项 4（吸收态标注，约 1h）**：文档落点（01-理论.md 转变分析章节）+ GUI 帮助文本新建载体（ISSUE-103 要求新建 QLabel/tooltip），决策无关。
**项 5（banner_of 统一键辅助，约 1h）**：落 GUI 层私有辅助（ISSUE-704，多面板共用 → **新建 `gui/utils.py` 模块文件**——该文件当前不存在，banner_of 为其首个成员；单面板私有则落面板模块内私有函数）+ 三态守卫契约（ISSUE-702）。<!-- REVIEW-R1-FIX: ISSUE-117 --> **落位预收敛：二选一收敛为「多面板共用落 `gui/utils.py`」**：消费点已达 4 个面板（plan_search_panel 1b / retreat_panel 1a / analysis_panel 3d / process_analysis_panel 2a），明显满足「多面板共用」分支——**按本计划裁决落 `gui/utils.py`（新建模块文件），不再留「单面板私有复制」选项**（四面板各持一份实现将承受本计划自己点名的口径漂移风险：'.' 判断是否一致、是否区分裸键）；§3 涉及范围清单已登记 `gui/utils.py` 为新建文件，拆分记录须显式写明「多面板共用落 `gui/utils.py`」。**与项 1b 边界（防重叠实现）**：1b 为 `_find_vulnerability_pool` 消费端改造（banner 匹配 + falsy 守卫，改 plan_search_panel L871-878）；项 5 为 `banner_of` 工具函数提供（含 None/空串→None 契约）。falsy 守卫仅在 1b 落地一次，项 5 不重复加守卫、只保证 `banner_of` 自身对 None/空串安全；两者共享 ISSUE-702 的「不崩溃」契约。决策无关。

> 实施顺序：决策无关组（1a/1b/1d、2a/2b、2d-1、3a-1/3a-2/3b/3c/3d/3e、4、5）先行；决策依赖组（1c、ISSUE-001 追加项、2c、2d-2）等裁决或按推荐路线执行。回滚边界见 §4.4。

1. **脆弱性 → 方案搜索链路**：`compute_vulnerability_analysis` 产出 pool_id = banner 键是**正确**的（时间域），修消费端匹配。统一到 banner 匹配。
   - `plan_search_panel._find_vulnerability_pool`：当前用 `store.pools` 全限定键精确匹配（恒空），改为 banner 匹配
   - <!-- REVIEW-FIX-PREV: ISSUE-001 --> **`retreat_panel`（同根因扩展）**：`_get_pool_names`（L260-265）从 `store.pools` 构建全限定键表（`pool_id={banner_id}.{pool_id}`），而脆弱性结果 `pr.pool_id` 是 banner 键（`banner_end_resources` 键，vulnerability.py L542-543），`pool_names.get(pr.pool_id)`（L102-103）恒取不到，山脊线图（`plot_vulnerability_ridge`）与单池图（`plot_vulnerability(pool_name=pname)`）池名均退化为裸 banner_id（如 b1）而非 banner.name。修复：pool_names 改为 `banner_id → banner.name` 映射（store.pools 展平后 `name=banner.name` 恰为 banner 级，`pool_names.get(pid.split('.')[0])` 即可）<!-- REVIEW-R1-FIX: ISSUE-121 --> **charts 字典键唯一性要求（追加登记，修复必读）**：`_get_pool_names` 改为 banner→name 映射后，`_on_finished` 的 L360 `pname = pool_names.get(pr.pool_id, pr.pool_id)` 由「恒 miss」变「命中」，L365 `charts[pname] = combined_fig` 以 banner.name 作字典键——修复前该键是裸 banner id（pr.pool_id miss 后原样返回，不同 banner 必唯一），修复后两个同名 banner（如两个「角色UP」）的图以相同键写入 charts，**后者覆盖前者、一个山脊图静默丢失**（此键唯一性退化本计划此前未点名）。**处置（保守方案）**：charts 字典键保持唯一键（banner_id = pr.pool_id 本身），banner.name 仅用于显示标签（构造 fig 标题/图例时解析显示名）；或显示名映射对同名 banner 追加去重后缀（如「角色UP (b1)」）。实施时按其中一种收敛并在 1a 拆分记录显式写明所选项；`_get_pool_names` 的显示映射本身仍可为 banner.name（查找表语义），但**不得以显示名作 charts 存储键**
   - <!-- REVIEW-FIX-PREV: ISSUE-002 --> **`from_pool_id` 键语义变化验证**：`pool_combo` 存在两个键空间写入点——`set_store`（L1258-1261 填全限定键）与 `set_vulnerability_result`（L1284-1288 填 banner 键）。统一键空间的方案缺口与兜底遍历序依赖在本条闭环（ISSUE-001/ISSUE-002）：
     - <!-- REVIEW-FIX-PREV: ISSUE-001 --> **`set_store` 填充侧改法（统一为 banner 键时的去重要求）**：`set_store`（L1258-1261）现逐 pool `addItem(display=pool_names.get(pe.pool_id), data=pe.pool_id)`。若只把键来源换成 banner 键而不去重，同 banner 多 pool 会逐 pool addItem 完全相同内容（display=banner.name、data=banner_id 均相同），下拉出现 N 个重复项——`set_vulnerability_result` 的 `current_ids` 去重（L1283-1288）只防追加侧重复，对写端自身不生效（阶段 1 P72-PSP-2 已指出 current_ids 去重对跨键空间失效，但未覆盖 set_store 侧同键重复项）。**改法：统一为 banner 键时按 banner_id 去重，每 banner 仅 addItem 一项**（display 取 banner.name、data 取 banner_id）。⚠ 待人工裁决（**已裁决 2026-08-07：路线 A**）：与 ISSUE-002 的截断起点担忧存在张力，两条路线选一——**路线 A**（写端去重统一 banner 键，键空间干净，但 `from_pool_id` 变 banner 键触发兜底漂移）/ **路线 B**（写端不动保留全限定键，仅读端 `_find_vulnerability_pool` 用 `banner_of()` 匹配做 banner 化，截断语义不变但下拉两键空间混存未根治）。推荐路线 B（符合「只修 bug 不重构」边界、行为等价性最强）；选路线 A 须接受并验证下述兜底漂移【**裁决：选路线 A**——起始粒度 = banner（新体系分析单元），兜底命中首个池 = 从活动起点开始，登记为接受项；路线 B 记为备选】
     - <!-- REVIEW-FIX-PREV: ISSUE-001 --> **`plan_search_panel._get_pool_name` 显示名缺口（追加项——REVIEW 发现的与既有 ISSUE-001 retreat_panel / ISSUE-701 analysis_panel 同根因的第三实例，此前未被任何修复项覆盖）**：路线 B（推荐）下写端保留全限定键，`set_vulnerability_result`（L1284-1288）追加的脆弱性池项 data = banner 键（pr.pool_id，来自 `banner_end_resources`），显示名经 `_get_pool_name`（L1290-1297）对 store.pools 全限定键表（`pe.pool_id` = `b1.main`）精确匹配，banner 键 'b1' 恒 miss、回退裸 'b1'；而同一下拉中 `set_store`（L1258-1261）填写的配置池项显示 banner.name（store.pools 展平后 pe.name 恰为 banner 级名）。结果同一 banner 在下拉中以「banner.name（data='b1.main'）」与「b1（data='b1'）」两种不一致标签并存。**修复（与 ISSUE-701 同构）**：`_get_pool_name` 在现有全限定键表之上补一层 `banner_id → banner.name` 映射（`banner_id = pe.pool_id.split('.')[0] if '.' in pe.pool_id else pe.pool_id`，name 取 `getattr(pe, 'name', pe.pool_id)`），先查 banner 映射再查全限定表，仍 miss 才回退原 id，使 `set_vulnerability_result` 追加项与 `set_store` 项标签一致；若裁决不修，则显式登记该缺口为路线 B 的**接受项**（非遗漏项），与「下拉两键空间混存未根治」一并声明。⚠ 待人工裁决（**已裁决 2026-08-07：修**）：本缺口为纯显示名（不改变 `_find_vulnerability_pool` 匹配与截断语义），「修」属 §4.1 GUI 消费端修复（与 ISSUE-004 边界一致），「不修」须按接受项登记<!-- REVIEW-R1-FIX: ISSUE-116 --> **路线 A 下本追加项的实际触发场景（表述澄清，消除「路线 B 语境 vs 路线 A 裁决」张力）**：本条文字语境为「路线 B（推荐）下写端保留全限定键」，但最终裁决为路线 A（`set_store` 按 banner 键去重）。路线 A 下 `set_store` 已写 banner 键项，`set_vulnerability_result`（L1283-1288）的 `current_ids` 去重（L1285 `if pr.pool_id not in current_ids`）会阻止与 set_store 项 data 相同的 banner 追加——即**脆弱性结果 banner 与 store enabled banner 一致时追加项根本不触发**。**本修复的实际生效场景**：脆弱性结果含 store 未列出项时——disabled banner（store 中该 banner 无 enabled pool 故 `set_store` 未写入，但脆弱性分析产出了其结果）或 store 变更后残留结果（结果对应旧 store 的 banner，新 store 不再列出）。此时 `set_vulnerability_result` 追加项触发、显示名经 `_get_pool_name` 查全限定表恒 miss 退化裸 id，`_get_pool_name` 修复仍必要。实施者按此理解：路线 A 主路径（结果与 store 一致）不触发追加项、不因修复改变行为；修复覆盖的是「脆弱性结果与 store 不完全一致」的残留/disabled 场景，评审不应质疑该追加项在路线 A 下的必要性。
     - <!-- REVIEW-FIX-PREV: ISSUE-002 --> **兜底命中 = 遍历序第一个匹配池（确定性语义）**：统一为 banner 键后 `_on_run_clicked`（L1040）传入的 `from_pool_id` 变为 banner 键，`RetreatConfigBuilder.build` 走 ISSUE-101 兜底（retreat_config.py L26-32，`'.' not in from_pool_id` 时）。该兜底**并非「banner 前缀匹配同一个池」**——它取 `original_store.pools` 遍历序第一个 `pool_id.split('.')[0] == from_pool_id` 的池（break）。多 pool banner（如 b1.main 在前、b1.step1 在后）下，用户原选 b1.step1 修复后实际命中 b1.main，`offset_day`（L39-41，取该池 end_day / start_day+21）的截断窗口整体平移，基准资源/保底初始化与修复前不等价。**行为等价性验证项须覆盖多 pool banner 场景**：明确兜底命中哪个 pool、offset_day 取值、截断平移是否影响基准资源/保底水位；若不可接受，改走路线 B（下拉除「(从头开始)」外保留全限定键传递精确 from_pool_id、仅匹配链路做 banner 化），使截断起点语义不变【**已裁决：路线 A**，接受「兜底命中首个池 = 从活动起点开始」语义，等价性验证须覆盖多 pool banner 场景确认命中首个池与 offset_day 取值】<!-- REVIEW-R1-FIX: ISSUE-110 --> **min_resource（最少资源搜索）模式显式纳入等价性验证**：`search_min_resource`（retreat_search.py L261）与退路搜索共用 `_build_env`（L118-141）截断路径——`from_pool_id` 非 None 时同样走 `RetreatConfigBuilder.build`，路线 A 下 `from_pool_id` 变 banner 键同样触发 ISSUE-101 兜底，多 pool banner 场景下基准资源/保底初始化截断窗口与修复前不等价；且结果显示链的「起始池」文案由全限定键退化裸 banner id（`plan_search_panel` 显示名修复 ISSUE-001 追加项与 ISSUE-701 均未点名该模式）。**落点勘误**：「起始池」文案位于 **Pareto 结果页**（ParetoResultPage.display，plan_search_panel.py L460，直接打印 `result.from_pool_id` 原值），该结果页内部经 `search_min_resource` 联动；min_resource 自身的 ResourceResultPage（page 0，plan_search_panel.py L209）不显示「起始池」文案，不得按「min_resource 结果页」找落点。**显示名处置（闭合：登记为路线 A 接受项）**：banner 键即新分析单元，Pareto 结果页显示裸 banner 键（如「起始池: b1」）可接受——该显示链不经 `_get_pool_name`（L1290-1297，仅覆盖下拉项与图表标签链）且 ParetoResultPage 无 store 引用，纳入 §4.1 项 1 修复须新增显示名解析装配、扩大修复面，纯文案收益低于「只修 bug 不重构」边界下的修复成本，与 ISSUE-002「起始粒度 = banner」接受项同一语义逻辑；此登记不影响任何匹配/截断语义。**等价性验证清单显式加入 min_resource 模式**：多 pool banner 场景确认兜底命中池与 offset_day（§4.3 ISSUE-109 已配套断言，见该条目），显示名接受项不改变验证内容。
   - <!-- REVIEW-FIX-PREV: ISSUE-006 --> **键契约注释**：在 `PoolVulnerabilityResult` dataclass 或 `compute_vulnerability_analysis` docstring 固化 `pool_id=banner_id` 契约说明（注释级改动，随本条一并落地），防未来新增 GUI 消费端再次用 store.pools 全限定键匹配而恒空
2. **process_analysis 累积模式**：`_cumulative_snapshots` 键 = banner 是**正确**的（时间域），修消费端 `_compute_pool_gdr` 累积模式的 pool_id 来源（当前用 pool_events 全限定键查 banner 表，恒空）。改为取 banner 段。<!-- REVIEW-FIX-PREV: ISSUE-005 --> 修复后同一 banner 内多个 pool 命中同一 banner 段快照，`_build_traces` 的 `pool_gdr_values[pid]` 对同 banner 各 pool 取值相同，`_show_trace_detail`（L878-917）「池GDR值」「池成败」两列会显示同 banner 多行完全相同——需在列头/图表副标注明「截止该 banner 段」，防用户误读为单池独立 GDR。<!-- REVIEW-FIX-PREV: AUDIT-TGAP-04 --> **同根因缺口补充（代码审计 4a）**：`pool_success`（L479-496）在 `_build_traces` 按 pid 计算后随 SampleTrace 进入两处消费：(1) `_show_trace_detail` 池成败列（L913，已在上条覆盖）；(2) **成败统计 tab 的 bb_table**（process_analysis_panel.py L60/L603 `_fill_bb_table`，`pool_success_rates` 取自 `bb_results` L608）——修复 2a 后同 banner 多 pool 的 `pool_success` 相同，bb_table 的 `pool_success_rates`（成败统计明细）同样显示同 banner 多行相同。**须一并标注口径**：bb_table 的 pool_success_rates 明细加同类「截止该 banner 段」标注（或与 `_show_trace_detail` 共用一个口径说明），防用户在两处看到不一致的呈现。归 2b 子任务。<!-- REVIEW-FIX-PREV: ISSUE-103 --> **未达 banner 段的成败语义（修复后显性化的边界，须一并声明口径）**：`_compute_pool_gdr`（L512-522）的 `if sample_idx < len(pool_snaps):` 守卫在修复后成为可见逻辑。快照列表长度与模拟数不一致时（<!-- REVIEW-FIX-PREV: ISSUE-002 --> **触发机制校正（追加项）**：该边界仅由「整键缺失」触发——常规来源为 result_store L150 旧数据集 `d.get('cumulative_snapshots', {})` 默认空字典；活体模拟下不存在「部分 sim 因停止条件未达到晚开 banner 段 → 快照长度不满」的按 sim 粒度缺失：`WorkerLocalExtractor.process` 主循环后的回退循环 streaming.py L364-381 无条件为剩余全部 pool/banner 追加当前累计状态快照（`cumulative_card_counts=cum_cards` 等），`DrawSequenceExtractor._update_cumulative`（L614）同样遍历全部 pool_end_times，`merge_extraction_packets`（L457-461）按 pid 聚合后 len(cumulative_snapshots[pid]) == n_sims 恒成立；「未触达 banner」的真实行为是 sim 最终状态投影，见下条 ISSUE-003），未达 sim 返回 None → `_build_traces`（L490-492）`pool_success[pid] = False`、池GDR 显示 0.0，与 infer_events 的 skip/ignore（未涉及/跳过）事件语义混淆，误显为「真失败」。修复前该边界被恒空掩蔽（pool_events 全限定键查 banner 表恒空 → 全部 None），修复后转为显性，属修复直接暴露的展示语义缺口。**口径声明**：在列头/图表副标注明「该 sim 未达到该 banner 段时池成败计为失败（数据缺失，非真失败）」，区分「未涉及」与「真失败」；若语义上「未涉及」更贴切，需评估将 None 显示为空态标记而非 False/0.0 的展示改动（登记为展示层细化，不属键错配修复本身）。
     - <!-- REVIEW-FIX-PREV: ISSUE-703 --> **同一边界在 analysis_panel success_rate「第k池累积」scope 的处理机制不同（须一并声明口径）**：ISSUE-103 的未达边界存在第二条路径且处理机制不一致——process_analysis 路径（`_compute_pool_gdr`）未达 sim 返回 None → 显式失败 + 口径标注；而 analysis_panel 每池成功率「第k池累积」scope 走 `compute_transition_flags_from_gdr` 累积分支（analysis_panel L1293-1303 → per_pool_analysis L348-358），其未达处理是另一机制：`snap = snaps[sim_idx] if sim_idx < len(snaps) else {}`（per_pool_analysis L350）→ `if snap:` 为 False → 仍调 `compute_pool_gdr_cumulative({}, ...)`（process_trace.py L267-276）→ `compute_gdr_from_cumulative({})` 构造全空 pseudo_compact → `compute_gdr_from_compact`（gdr.py L948，签名返回 `float`，空数据返回数值如 0.0 而非 None）→ per_pool_analysis L369 `if val is None:` 不触发 → L371-374 按阈值判定，未达 sim 被静默判成败（higher-is-better 类指标下 0.0 判「失败」、lower_is_better 类指标下 0.0 反而判「成功」）混入成功率分子分母，既无「数据缺失」口径也无 None 守卫。**口径声明扩展**：累积分支对 `snap={}` 显式返回 None（per_pool_analysis L350-358 加 `if not snap: val = None` 短路，或 `compute_pool_gdr_cumulative` 对空快照返回 None），与 process_analysis 路径统一「未达 vs 真失败」语义，消费侧对 None 计 False 且注明「该 sim 未达到该 banner 段（数据缺失，非真失败）」；§4.3 补 success_rate 路径的未达回归（见 §4.3 ISSUE-703 条目）。⚠ 待人工裁决（**已裁决 2026-08-07：路线 (a)，登记 §4.1 项 4 例外**）：该改法触碰 `core/per_pool_analysis.py`/`core/process_trace.py`（每池分析核心逻辑），与 ISSUE-004「§4.1 交付全落 GUI 消费端」边界冲突——路线 **(a)** 落 core 改（推荐：与 process_analysis 机制统一，一处声明统一语义；须同步 §4.1 项 4 的「无 core API 变更」声明登记此例外，见 ISSUE-703 例外登记）；路线 **(b)** 纯 GUI 层（analysis_panel 消费侧对 flags 与快照长度不一致的 sim 做未达标注，不动 core，但两路径语义仍分裂，且 lower_is_better 误判「成功」在消费侧无法修复）<!-- REVIEW-R1-FIX: ISSUE-114 --> **路线 (a) 落点锁定（任务拆解时定，推荐 per_pool_analysis L350-358 短路）**：路线 (a) 在 core 侧的具体落点二选一，两落点对公共契约影响不同——**落点 1**：per_pool_analysis L350-358 加 `if not snap: val = None` 短路（`compute_pool_gdr_cumulative` 对非空快照行为不变，**公共函数契约不变**，只影响 `compute_transition_flags_from_gdr` 累积分支，process_analysis_panel 等其他调用方不受影响）；**落点 2**：process_trace.py `compute_pool_gdr_cumulative`（L267-276）对空快照返回 None（改变 `core/__init__.py` 导出函数的行为契约——从返回数值改为可返回 None，影响**所有**调用方）。**裁决：任务拆解时锁定落点 1**（短路落在 per_pool_analysis 消费侧，不动导出函数契约，避免影响 process_analysis_panel 等其他调用方），并将所选落点写入拆分记录；§4.3 ISSUE-703 用例按所选落点指明断言对象——落点 1 断言「analysis_panel 累积分支消费到 None（未达 sim 不混入成功率、不误判）」、落点 2 断言「`compute_pool_gdr_cumulative({}, ...)` 返回 None」。若实施时改选落点 2，须同步评估所有调用方并扩大回归面。<!-- REVIEW-R1-FIX: AUDIT-TGAP-06 --> **webui 消费方补登记（代码审计 4a，2026-08-08）**：落点 1 的「process_analysis_panel 等其他调用方不受影响」声明未覆盖另一 cumulative scope 调用方——`webui/analysis_service.py` L633 `_transition_analysis` 调用 `compute_transition_flags_from_gdr(..., gdr_key='all_targets', scope='cumulative')`。实际影响小：webui 硬编码 `all_targets`（higher-is-better），空快照下现状 `0.0→False` 与修复后 `None→False` 结果一致、行为等价；但该声明不应被误当全量结论（若 webui 未来改 lower_is_better 指标则空快照误判成功被修复，行为改变）。登记为 2c 的低影响消费方，实施记录须引用，§4.3 无需为 webui 单独加回归（行为等价，由 ISSUE-114 断言覆盖）。
     - <!-- REVIEW-FIX-PREV: ISSUE-003 --> **第三种口径：未触达 banner 段 = sim 最终状态投影（追加项——ISSUE-103/703 的 None/空快照分支之外的真实边界，独立声明并覆盖两处消费点）**：活体模拟下未触达 banner 段并非快照缺失，而是被回退循环填入 sim 终点的最终累计状态（streaming.py L364-381：`cumulative_card_counts=cum_cards`、`transition_flags.append(_check_success_draw_only(cum_cards, compact, pid))`）。该快照携带 sim 终点状态，而 `pool_end_time`（banner 打开/结束时间）可能晚于 sim 终点——「截止该 banner 段」的 GDR 与成败判定实际是对「sim 终止后继续运行」的投影，语义错误（如全部目标 day 3 达成、banner day 10 才打开，快照将判该 banner 成功）。**两处消费点**：(1) process_analysis 累积模式——按 ISSUE-005 修复后 `_compute_pool_gdr`（L512-522）以 banner 键取快照，未触达 banner 显示基于最终状态的 GDR 与成败，可能误判真失败或真成功；(2) analysis_panel 转变分析主路径 L1357 `if self.transition_flags:` 直接消费回退循环生成的 flags，未触达 banner 同样被投影标记并计入矩阵。<!-- REVIEW-FIX-PREV: D1-裁决 --> **该消费点已随 D1 裁决移交 P76**（转变分析整体挪出本计划），本计划不再覆盖此消费点的未触达识别。ISSUE-103/703 的口径声明与修复仅针对 None/空快照分支，未覆盖本投影边界。**口径声明**：在 ISSUE-103/703 之外新增第三种状态「未触达 banner 段」——GDR/成败系 sim 终止时点的投影，非截止该 banner 段的真成败；消费端识别方式评估：比较快照 `pool_end_time` 与 sim 终点时间，对 sim 终止早于 banner 打开的快照打「未触达」标记（展示为空态/注明投影口径，不判真成败），两处消费点均适用。§4.3 补对应回归用例（见 ISSUE-003 条目）。⚠ 待人工裁决（**已裁决 2026-08-07：语义 A（继承态）——2d-1 展示口径、2d-2 不做**）：未触达识别需暴露 sim 终点时间或经 flags/快照推断，涉及数据面与消费端改动幅度，与 ISSUE-004「§4.1 交付全落 GUI 消费端」边界的关系待评估；最小改法为纯展示层注明投影口径，不改变数据与判定（对应子任务 2d-1，可先行；识别机制对应 2d-2，依赖 D5）。<!-- REVIEW-FIX-PREV: AUDIT-TGAP-05 --> **实现降级要求（代码审计 4a）**：2d-2 未触达识别依赖比较快照 `pool_end_time` 与 sim 终点时间，但 `pool_end_time` 键**仅并行路径产出**（streaming.py L348-358 快照含 `pool_end_time`；单线程 `DrawSequenceExtractor._update_cumulative` L640-648 快照**无该键**）。单线程数据下 `get('pool_end_time', 0)` 全落 0，未触达识别失真。<!-- REVIEW-R1-FIX: ISSUE-102 --> **ISSUE-104 测试断言口径校正**：原「ISSUE-104 测试仅验证两路径快照字段集合一致」与 §4.3 项 2 承认的「两路径字段集本就不同」（并行含 `pool_id`/`pool_end_time`、单线程无）自相矛盾——按字段集合相等写断言测试必失败。**统一口径**：ISSUE-104 测试断言的是「累积模式消费端（`process_analysis_panel._compute_pool_gdr` 累积分支等）在并行与单线程两条快照路径下**行为等价**」，即断言消费端对字段集的依赖被 banner_of/防御读取代，而非断言两条路径字段集合相等（见 §4.3 ISSUE-104 条目）。**2d-2 实现仍须显式处理单线程路径缺 `pool_end_time` 的降级**（如单线程快照以 `pool_end_times` 表回填 `pool_end_time`，或识别逻辑对缺键快照走保守分支），不得默认 `get(...,0)`。【**D5 语义 A 下 2d-2 不做，本条降级为不处理**；改回退循环/快照补 sim 终点时间的数据层根治方案登记 P76 待决清单】
3. **命名澄清**：`cumulative_by_pool`（实际是「截止每 banner」）在 GUI 中改为 `cumulative_by_banner`。<!-- REVIEW-FIX-PREV: ISSUE-101 --> **改动范围排除项**：本条仅改 `cumulative_by_pool` 命名相关引用；`transition_analysis` 的 `pool_ids_ordered` 来源（L1353-1354）**不在本条改动范围**（时间域方向正确，N3 挂起，见 §3 范围行标注）。<!-- REVIEW-FIX-PREV: ISSUE-003 --> **改动路径定为「改 chart key」全链同步**：「仅加副标」与命名澄清目标不符（只改 `_cum_title`（L1171-1173）与显示名，chart key 前缀 L1180 仍是 `cumulative_by_pool_{metric_name}`，勾选 key 与 chart key 脱节）。改 chart key 时 `cumulative_by_pool_` 前缀进入 ChartWebView 的 HTML div id 与缓存/增量更新机制（阶段 1 P72-AP-1 登记项），须全链同步以下适配点：`ANALYSIS_CATEGORIES` 显示名（L17/L43/L237）、<!-- REVIEW-R1-FIX: ISSUE-111 --> **图表标题 `_cum_title`（L1171-1173，`f'{metric_name} (截止每池)'` 与 `f'{metric_name} (抽, 截止每池)'`）**：中文文案「截止每池」不命中 grep 'cumulative_by_pool'，实施者按 grep 清单执行会漏改；两处改「截止每 banner」，与 ANALYSIS_CATEGORIES 显示名同步——否则 chart key 已改名但用户可见标题仍是旧粒度语义，命名澄清目标部分落空、`_EXPANDABLE_KEYS`（L49）、勾选 key 构造（L1931/L1948）与条件收集 `startswith('cumulative_by_pool_')`（L2138-2139）、`_get_ordered_charts` 前缀匹配（L2412-2435，`_CHART_DISPLAY_ORDER` 的 base_key + '_' 前缀段）、ChartWebView 缓存与增量更新（`has_chart`/`update_chart`，chart_webview.py L321/L355）及 `set_charts` 全量重建（L2268/L2408）。遗漏任一前缀判断点会导致勾选 key 与 chart key 脱节、分析静默不渲染或旧缓存残留。实施时以 grep 全量确认 `cumulative_by_pool` 字符串引用清单作为最终适配清单（注意中文文案与 grep 键空间正交：`_cum_title`/`ANALYSIS_CATEGORIES` 显示名等中文文案不命中键 grep，须按 L1171-1173/L17/L43/L237 行号清单人工核对，不能只依赖 grep）。<!-- REVIEW-R1-FIX: ISSUE-124 --> **进度/完成文案（追加点名）**：同属「不命中 grep 的中文文案」还有三处进度提示——L1090 `self._emit('生成截止每池的GDR分布...', ...)`、L1092 与 L1189 的 `step_done('截止每池的GDR分布')`（已实际读取确认）。这三处与 ISSUE-111 补的 `_cum_title`（L1171-1173）同类：不改则重命名后进度提示文案与图表标题口径不一致，用户界面残留旧粒度语义。**处置**：并入人工核对行号清单（L1090/L1092/L1189），与 `_cum_title` 同批改「截止每 banner」，实施者按行号清单人工核对时须覆盖这三处，不得只改图表标题而漏进度提示。<!-- REVIEW-FIX-PREV: AUDIT-TGAP-01/02/03 --> **代码审计 4a 传递缺口补充（2026-08-07）**：前述清单为 grep 枚举，审计 4a 核实 3 处未点名的 `cumulative_by_pool` 引用，全部属 3a-1 子任务适配范围：
   - **L2275-2276 `_needs_computation` 前缀判断**：`any(k.startswith('cumulative_by_pool_') for k in charts)` 与 `self._computed_conditions['cumulative_by_pool'] = ...`（L2276）。改 key 前缀为 `cumulative_by_banner_` 而不同步此判断，`_needs_computation` 对累积分析恒 True，每次运行分析都无条件重算（性能退化，不崩）。
   - **L1089/L1097 选中判断与属性引用**：`if 'cumulative_by_pool' in self.selected and self.cumulative_by_pool_selections and self.pool_end_times:`（L1089）与 `for metric_name in self.cumulative_by_pool_selections:`（L1097）。item key 改为 `cumulative_by_banner` 而不同步，累积分析勾选了也永不执行（静默失效，比性能问题更隐蔽）。
   - **内部属性名连带改名风险**：`cumulative_by_pool_selections`（L150/L166/L1089/L1097/L2139/L2195）、`_cumulative_by_pool_checks`（L1611/L1726/L1948）、`_get_cumulative_by_pool_selections`（L2104-2105/L2139/L2195）。这些是内部一致性命名，改 key 时可不改名（功能不受影响）；若实施者「顺手」改为 `_banner` 版本，则必须全链同步上述 7 处，漏一处 AttributeError。**裁决**：3a-1 内部属性名保持旧名不改（避免无谓同步面扩大），仅改 chart key 与显示名；如实施中改名，须以上述 7 处为同步依据。<!-- REVIEW-FIX-PREV: ISSUE-102 --> **非代码引用同步清单（grep 全量确认的补充点名，非代码位置易漏）**：`docs/01-活跃/panels/统计分析/02-实施.md`（L89 章节名、L114 `charts['cumulative_by_pool_*']` 山脊图键）、`docs/01-活跃/panels/统计分析/00-档案.md`（L61 `cumulative_by_pool | 截止每池的GDR分布`）、`tools/poc_webview/ui_compare/src/panels/workbench/DatasetWorkbench.vue`（L186 路由键映射 `cumulative_by_pool: 'runAnalysis'`）与 `methodDefs.js`（L195 `type: 'cumulative_by_pool'`）。<!-- REVIEW-R1-FIX: ISSUE-113 --> <!-- REVIEW-R1-FIX: ISSUE-119 --> **methodDefs.js L195 的 `label` 字段与 L201 result `title`（追加点名）**：`type: 'cumulative_by_pool'` 同行的 `label: '截止每池 GDR 分布'`（methodDefs.js L195 为 type + label 同行结构）与同方法块 result 数组 L201 的 `{ key: 'chart', title: '截止每池 GDR 分布', desc: '多池累积分布' }` 均为用户可见中文文案，不命中 grep 'cumulative_by_pool'，与 GUI `ANALYSIS_CATEGORIES` 显示名「截止每池的GDR分布」（3a-1 适配清单点名）对应——GUI 侧改为「截止每 banner」而 POC label/title 保留「截止每池」时原型展示名与实现口径脱节（ISSUE-119 核实 L201 title 已实际读取确认，同 ISSUE-111 担心的漏改场景同类）。**处置随 ISSUE-120 收敛（2026-08-08）**：ISSUE-120 裁决 POC 侧（methodDefs type + DatasetWorkbench 路由键）保持 `cumulative_by_pool` 不改（与 webui 遗留层 API 键一致），故 label 与 L201 title **一并保持「截止每池」不改**，不得按「与 type 键同批改」执行——三处（L195 type / L195 label / L201 title）统一登记为 POC legacy 接受项（见 §3 ISSUE-120 登记与项 3 的 ISSUE-101 收敛）。实施者执行 3c 时不得把 POC label/title 当同步目标误改；本补点名的作用是「显式登记不改」，与 ISSUE-112 归档排除边界同类。<!-- REVIEW-R1-FIX: ISSUE-112 --> **「不同步」排除边界（显式声明）**：本同步清单**仅限活跃文档与活跃 POC 代码**；`docs/03-归档/`（含 `plans/2026-06-14-P52-cumulative_by_pool统一到GDR注册表.md`、`P62 可达目标卡筛选——GDR分母区分全量与池子开放子集.md`、P43/gdr-unification 等历史计划文档）与 `docs/00-meta/模块状态矩阵.md`（L165 P52 历史计划描述）中的 `cumulative_by_pool` 是**过去计划的名称与描述（历史事实记录），重命名后保留当时名称不替换**。实施者按「grep 全量确认字符串引用清单作为最终适配清单」机械执行时，须跳过上述归档/历史文档（误改历史文档会产生伪史改写的追溯混淆）。<!-- REVIEW-R1-FIX: ISSUE-101 --> **POC 消费端点名校正（2026-08-08）**：原清单点名 `ResultChart.vue`（L66 `case 'cumulative_by_pool':`），经 grep 全量确认 **ResultChart.vue 全文件零处 `cumulative_by_pool` 引用、不存在 L66 的 case 分支**，真正消费端为 `DatasetWorkbench.vue` L186 的 API 路由键映射（stage-1 原记 L191 亦有偏差，实际 L186）。按旧清单执行会把不存在的引用当同步目标、漏掉真实路由键，改名后 POC 前端路由键将失效。**methodDefs.js 同步约束**：methodDefs.js L195 的 `type: 'cumulative_by_pool'` 与 DatasetWorkbench.vue L186 路由表为同一消费链（methodDefs type → DatasetWorkbench 路由映射），methodDefs type 键若改 `cumulative_by_banner`，DatasetWorkbench.vue 路由键表须同步改。这四处（面板三文件制文档 ×2 + POC 原型 ×2）均以 `cumulative_by_pool` 为 chart key 硬编码，若 chart key 前缀改为 `cumulative_by_banner`，文档与原型将遗留过期 key 与实现脱节。处理二选一：**(a)** 随重命名一并同步替换（推荐，保持文档/原型口径与实现一致）；**(b)** POC 原型标注 legacy 豁免同步，但模块文档 02-实施.md/00-档案.md 必须同步（它们是该面板实现口径的正式文档）。<!-- REVIEW-R1-FIX: ISSUE-120 --> **收敛裁决（ISSUE-120 同键空间校正后，POC 走 (b) legacy 豁免）**：ISSUE-120 校正 POC methodDefs type 与 webui API 方法键为同一键空间后，POC 消费链依赖 webui 遗留层（analysis_service.py 仅注册 `'cumulative_by_pool'` handler），**methodDefs type 与 DatasetWorkbench 路由键保持 `cumulative_by_pool` 不改**——选项 (a)「同步替换」会使 POC `run_analysis('cumulative_by_banner')` 命中不到 handler、返回「未知分析方法」（pywebview 生产模式静默失效），故 (a) 作废；选项 (b) 采用，但豁免理由改为「POC 消费链与 webui 遗留层键一致、本期不改名」，非「弃用演示件」。POC 侧保持不改的连带登记：methodDefs.js L195 `label` 与 L201 result `title`（「截止每池 GDR 分布」）一并不改（ISSUE-113/ISSUE-119 据此处置），POC 展示文案与 GUI「截止每 banner」口径脱节登记为 POC legacy 接受项；模块文档 02-实施.md/00-档案.md 仍须同步改（与 GUI 实现口径一致）。<!-- REVIEW-R1-FIX: ISSUE-104 --> **webui 后端同步边界（追加登记，勿纳入 3c）**：webui `analysis_service.py` 的 API 方法键 `'cumulative_by_pool'`（L163）为 **web API 契约键**，与 PyQt 侧 chart key 前缀是不同键空间——本期不改名（遗留层登记见 §3），勿把 webui 键加入本同步清单；`vuln_service.py` L124 裸 banner 显示名缺口同期登记（见 §3），实施者不得按 plan_search_panel 同类项顺手改入本次范围。<!-- REVIEW-FIX-PREV: ISSUE-005 --> **process_analysis_panel 同步**：`pool_gdr_mode` 下拉标签「截止到该池（累积）」（L100）改为「截止到该 banner（累积）」，与修复后语义（截止到该 banner 段）一致
   - <!-- REVIEW-FIX-PREV: ISSUE-701 --> **显示名查找适配（banner 键消费方，否则命名澄清目标落空）**：`_get_pool_names`（L1613-1635）以全限定 pool_id（b1.main）为键构建 name 映射，但两个时间域消费点用 banner 键查该表恒取不到、回退显示裸 id：(1) cumulative_by_pool 山脊图 L1094 `pool_ids = sorted(self.cumulative_snapshots.keys())`（banner 键）→ L1151 `ridge_labels[pid] = _strip_pid(pid)`（L209-211 `pool_names.get(pid, pid)`）→ 恒落 fallback，标签显示 'b1' 而非 banner.name；(2) 转变分析矩阵标题 L1394/L1430 `_pool_label` 同样用 `pool_end_times` 的 banner 键查全限定表 → 标题显示 'b1→b2'。**修复**：`_get_pool_names` 在现有全限定表之上补一层 `banner_id → banner.name` 映射（`banner_id = pe.pool_id.split('.')[0] if '.' in pe.pool_id else pe.pool_id`，name 取 `getattr(pe, 'name', pe.pool_id)`——store.pools 展平后 pe.name 即 banner 级名），并新增 banner 键查询辅助（如 `_banner_label(banner_id)`：先查 banner 映射、fallback `_strip_pid`）<!-- REVIEW-R1-FIX: ISSUE-125 --> **辅助落点裁决（随 3d 拆分记录）**：banner 映射即此补层（返回 dict 的 banner_id 键条目），`_strip_pid`/`_pool_label`（均 `self.pool_names.get(pid, pid)`）对 banner 键天然命中，**无需独立 `_banner_label` 辅助**——若仍保留独立辅助，必须定义在 AnalysisWorker `_run_impl` 内嵌 def（与 `_strip_pid` 同层，L209-211），不得实现为 AnalysisPanel 方法（worker 侧无法调用、显示名适配目标落空）；两个消费点 `ridge_labels`（L1151）/`_pool_label`（L1394/L1430）改为经 banner 映射解析。**与项 5 的 `banner_of` 分工**：`banner_of` 管键匹配（全限定→banner），本条管显示名（banner→banner.name），配套使用。**为何必须修**：若只 rename 为 `cumulative_by_banner` 而不适配显示名，图表仍显示裸 banner id，「截止每 banner 应显示 banner 名」的命名澄清目标落空。本条与 ISSUE-001 的 retreat_panel `_get_pool_names` 键错配同根因（banner 键 vs 全限定键查找），但 analysis_panel 这一实例此前未被任何修复项覆盖（详见 §1.4 核实注的 ISSUE-701 行归属勘误）
   - <!-- REVIEW-FIX-PREV: ISSUE-004 --> **core 层命名错位注释（与 GUI 命名澄清对称）**：`per_pool_analysis.py` 的 `cumulative_gdr_at_pool_ends`（L155）与 `compute_cumulative_snapshots`（L56）函数名暗示 pool 级，但键实际来自 `pool_end_times` 的 banner 键（时间域），与 GUI 命名澄清同源（阶段 1 P72-PPA-03，此前未在任何 REVIEW-R1-FIX 响应）。两函数经 `core/__init__.py` 导出，未来新增消费端仍可能按函数名误判为 pool 级键。**注释级动作**：两函数 docstring 标注「键为 banner 级（pool_end_times 键，时间域）」，与 ISSUE-006 对 `PoolVulnerabilityResult` 的键契约注释对称。此为纯注释改动（§4.1 边界声明的注释级例外），不触分析逻辑
4. **吸收态标注**：转变分析累计窗口的 AB/BA 恒 0 限制写入 GUI 帮助文本与文档。<!-- REVIEW-FIX-PREV: D1-裁决 --> **已按 D1 裁决移交 P76（2026-08-07）**：转变分析整体留待 P76 重构，吸收态标注随之挪出本计划，本条不再实施。<!-- REVIEW-FIX-PREV: ISSUE-005 --> **文档落点指明 + CLAUDE.md 同步确认**：文档落点为 `docs/01-活跃/panels/统计分析/01-理论.md` 的转变分析章节（§1.2/§三 马尔可夫假设处，说明累计窗口下吸收态限制及与演进路径 A' 局部窗口的区别），并交叉引用 P27 计划；GUI 帮助文本落在 analysis_panel 转变分析面板帮助区域。<!-- REVIEW-FIX-PREV: ISSUE-103 --> **GUI 落点需新建载体**：transition_analysis 配置区（L1874-1879）仅有 `success_criteria_combo` 一个控件，无既有 QLabel 帮助文本或 tooltip 机制，「帮助区域」为待新建而非既有位置。实施时新增 QLabel 说明（或对 `success_criteria_combo` 加 setToolTip）承载累计窗口 AB/BA 恒 0 的吸收态限制说明，勿因找不到现成区域而遗漏该项。同时显式登记：**本计划无 core API 变更（§4.1 交付全落 GUI 消费端），CLAUDE.md 的 per_pool_analysis/streaming/vulnerability 描述无需改动**——实施者不得因文档任务误改 core 文档，也不得遗漏此确认。<!-- REVIEW-FIX-PREV: ISSUE-704 --> **落位确认**：§4.1 项 5 的 `banner_of` 统一键转换辅助按 ISSUE-704 裁决落 GUI 层私有辅助（不写入 `core/`、不经 `core/__init__.py` 导出），本声明不受其影响。<!-- REVIEW-FIX-PREV: ISSUE-703 --> **例外登记（待人工裁决）**：若 §4.1 项 2 的 ISSUE-703 裁决走路线 (a)（core 侧对空快照返回 None，触碰 `per_pool_analysis.py`/`process_trace.py`），本声明登记该显式例外（其余 §4.1 交付仍全落 GUI 消费端）；走路线 (b) 则本声明无例外。
5. <!-- REVIEW-FIX-PREV: ISSUE-007 --> **统一键转换辅助**：全限定→banner 键转换在本计划多个修复点重复（本条 1 的 retreat_panel、本条 2 的 process_analysis、analysis_panel L1137 既有防御性实现 `pid.split('.')[0] if '.' in pid else pid`）。提取统一辅助 `banner_of(pool_id)`，三处共用，避免各点口径漂移（'\.' 判断是否一致、是否区分裸 banner 键）造成新的键错配。在「只修 bug 不重构」边界下为轻量收敛，不触碰分析核心逻辑<!-- REVIEW-R1-FIX: ISSUE-127 --> **core 层第 4 处内联实现登记（banner_of 收拢范围外，勿改 core）**：`core/per_pool_analysis.py` `_draw_only_card_counts`（L330-343）已有同类键转换 `pid_banner = pid.split('.')[0] if pid else ''`（L331，含空值守卫，与 banner_of 全限定取前缀语义同构）。该处因 ISSUE-704 裁决 banner_of 落 GUI 层、不写入 core 而**保留内联，登记保留**——不属 banner_of 收拢范围，实施者不得将其改为 banner_of 调用（跨层依赖、破坏「banner_of 不落 core」边界），也不得按「三处共用」断言误认为全量收拢完成；未来 banner_of 契约演进（如多段键）时 core 侧此内联不跟随，属已知口径分叉，登记为演进提示（与项 5「避免各点口径漂移」目标的部分背离已显式声明）
   - <!-- REVIEW-FIX-PREV: ISSUE-704 --> **落位裁决：GUI 层私有辅助，不落 core**：`banner_of` 定义为 GUI 层辅助（多面板共用落 `gui/utils.py` 模块函数，单面板私有落面板模块内私有函数），**不写入 `core/`、不经 `core/__init__.py` 导出**。⚠ **`gui/utils.py` 当前不存在**（gui 目录现有 20 个 .py 模块，无 utils.py），本计划涉及的多面板共用场景（plan_search_panel / retreat_panel / analysis_panel / process_analysis_panel）选择「多面板共用落 `gui/utils.py`」时，须**新建该模块文件**，`banner_of` 为其首个成员，不得误以为已有模块可挂载；若评估后落面板模块内私有函数（每面板复制实现），则无新建文件动作但需接受多处实现口径漂移风险——二选一由实施者在任务拆解时按消费点数量裁定，并在拆分记录中显式写明所选项。理由：§4.1 项 4 声明「本计划无 core API 变更（§4.1 交付全落 GUI 消费端）」——若 `banner_of` 落 core 即新增公共 API，破坏该项边界并连带产生 CLAUDE.md/文档同步义务，两处声明互相矛盾。实施者按本裁决落位，项 4 的「无 core API 变更」声明保持成立（项 4 已登记本确认）
   - <!-- REVIEW-FIX-PREV: ISSUE-702 --> **None/空串守卫契约（契约三态）**：`banner_of(pool_id)` 首行处理 `pool_id is None or pool_id == ''` → 返回 None（不抛异常）；裸 banner 键（无 `.`）→ 原样返回；全限定键 → 取 `.` 前缀。既有防御式 `pid.split('.')[0] if '.' in pid else pid` 对 None 执行 `'.' in None` 抛 TypeError，而消费端存在 None 合法输入——plan_search_panel `pool_combo` 含 data=None 的「(从头开始)」项（L1255），`_on_pool_changed`（L857-858）与 `_get_selected_resource`（L924-927）均直接 `currentData()` 传给 `_find_vulnerability_pool`（当前实现 `pr.pool_id == pool_id` 对 None 天然不匹配、安全返回 None；引入 `banner_of` 后若不走守卫即崩溃）。**双保险**：`_find_vulnerability_pool`（L871-878）首行加 `if not pool_id: return None`（falsy 守卫）。**守卫落地归属（边界，防与 1b 重叠）**：本契约描述 `_find_vulnerability_pool` 的 falsy 守卫，其**代码落地在项 1 子任务 1b**（消费端改造）；项 5 本身只保证 `banner_of` 工具函数对 None/空串安全（三态契约），不在 1b 之外再重复加守卫。回归用例：选择「(从头开始)」时下拉/预设更新不崩溃（`_on_pool_changed` 走 else 分支清保底表并恢复通用资源预设，L862-869）

### 4.2 挂起（不属 P72 或待前置裁决）

- **N1 / N2（赠卡相关）**：draw-only 口径的执行细节，成败口径方向由 **P71 维度 3**（可配置：draw-only / 含累抽得 / 全获得）裁决。P72 不拍板「减不减赠卡」。挂起等 P71。<!-- REVIEW-FIX-PREV: ISSUE-008 --> **激活条件**：P71 当前为 draft 占位（文件头注明「占位（设计待启动）」，维度 3 未裁决），N1/N2 的激活触发 = P71 维度 3 裁决落地。两计划均未登记跨计划依赖跟进机制，若 P71 长期不推进，N1/N2 将无限期挂起且无自动提醒——建议在模块状态矩阵标注该跨计划依赖（P72 N1/N2 依赖 P71 维度 3），供 C5/P38 类评审检查挂起未激活项
- **single_pool 分支 + N3**：绑定 §5.1 待决子项（GUI 成功判据 `per_pool_target` 去向）。挂起
- **局部窗口（A'）**：演进路径，待用户裁决是否启动。挂起

### 4.3 补测试

- 确定性修复（脆弱性链路 / process_analysis 累积模式）的混合抽卡与跨 banner 回归测试
- <!-- REVIEW-R1-FIX: ISSUE-115 --> **GUI 展示口径用例的测试策略（§4.3 前置说明）**：本清单多处用例断言 GUI 展示行为（ISSUE-103「UI 明确注明数据缺失非真失败」、ISSUE-003 投影口径声明、ISSUE-006 空态提示），隐含面板方法调用能力；但 `tests/gui` 现有行为测试仅覆盖 ConfigPanel（QApplication fixture 模式）与 comparison_analysis_panel（纯逻辑 smoke，无 QApplication），retreat_panel / plan_search_panel / analysis_panel / process_analysis_panel 均无行为测试先例（仅 `test_gui_imports.py` 冒烟导入）。**测试策略**：展示口径断言优先走**纯逻辑断言**——把口径字符串生成逻辑提取为可测的模块级函数/类方法（或复用 `.recycle_bin/test_p72_key_repairs.py` 展示的 `__new__` 绕过 QApplication 直测纯逻辑方法模式，见 ISSUE-107 条目），不实例化 QMainWindow 全栈；确需面板实例时**新建共享 QApplication fixture** 作为基础设施扩展（conftest 层 session 级 fixture 实例化四面板，与 ConfigPanel 既有 fixture 模式一致）。实施时先确认断言对象可经纯逻辑路径构造，再决定是否扩展 fixture，避免落地时才发现无法构造面板实例。
- <!-- REVIEW-FIX-PREV: ISSUE-103 --> **未达 banner 段成败边界（构造路径校正）**：构造累积模式下快照列表长度 < 模拟数的场景（result_store 加载无该 banner 快照的数据集——「整键缺失」是活体模拟下该边界唯一触发方式；原构造「多 banner 配置 + 部分 sim 因停止条件未达到晚开 banner 段」不成立，两条提取路径均恒为全部 banner 补齐快照，见 §4.1 项 2 机制校正），断言未达 sim 池成败显示 ✗、池GDR 显示 0.0，且 UI 明确注明「数据缺失，非真失败」口径，避免与 infer_events skip/ignore 语义混淆。此用例与 §4.3 下一条 ISSUE-006 的 result_store 边界共用构造路径，可合并为一条参数化测试
- <!-- REVIEW-FIX-PREV: ISSUE-703 --> **success_rate「第k池累积」未达边界**：与 ISSUE-103 用例共用构造路径（快照列表长度 < 模拟数，经 ISSUE-002 校正后为 result_store 旧数据集整键缺失构造），断言 analysis_panel 每池成功率「第k池累积」scope（`compute_transition_flags_from_gdr` 累积分支）下未达 sim 不混入成功率——与 process_analysis 路径同口径：计失败 + 「数据缺失，非真失败」标注；并验证 ISSUE-703 修复后（空快照 → None）空快照不再对 lower_is_better 类指标误判「成功」。<!-- REVIEW-R1-FIX: ISSUE-114 --> **断言对象按落点锁定（§4.1 项 2 ISSUE-114 已裁决路线 (a) 落点 1：per_pool_analysis L350-358 `if not snap: val = None` 短路，不动 `compute_pool_gdr_cumulative` 导出契约）**：本用例断言对象为 **analysis_panel 累积分支消费到 None**（未达 sim 不混入成功率、不误判），**非** `compute_pool_gdr_cumulative` 的返回语义；若实施时改选落点 2（导出函数返回 None），本用例改断言 `compute_pool_gdr_cumulative({}, ...)` 返回值并同步扩大调用方回归面。原「若 ISSUE-703 裁决走路线 (b)（纯 GUI 层）本用例改断言消费侧未达标注」分支已随路线 (a) 裁决作废，不再适用。
- <!-- REVIEW-FIX-PREV: ISSUE-003 --> **未触达 banner 段的投影边界回归（追加项）**：构造活体模拟场景——多 banner 配置 + 停止条件使 sim 在晚开 banner 打开前终止（如全部目标 day 3 达成、banner day 10 才打开），断言：(1) process_analysis 累积模式下未触达 banner 的 GDR/池成败显示「未触达/投影」口径（按 §4.1 项 2 评估的识别方式），而非基于最终状态投影误判真成败；(2) analysis_panel 转变分析主路径（L1357 `if self.transition_flags:`）未触达 banner 的转变标记同样标注投影、不混入真成败矩阵。本用例与 ISSUE-103/703 的 None 边界用例（result_store 整键缺失）为两条独立构造路径，不得合并
- <!-- REVIEW-FIX-PREV: ISSUE-006 --> **result_store 旧数据集加载边界**：累积模式存在第二条数据路径——main_window L550-558 从 result_store 加载数据集（`ds.cumulative_snapshots` / `ds.pool_end_times`）调 `update_results`。result_store L150 `d.get('cumulative_snapshots', {})` 对无该字段的旧数据集（P61 前产物/字段名不符）静默给空 dict → §4.1 第 2 条修复后 `_cumulative_snapshots.get(banner_id, [])` 恒空 → `_compute_pool_gdr`（L508-525）累积模式返 None、池GDR 显示 0.0/空、池成败全 False，静默退化（CLAUDE.md 无历史包袱原则缓解配置迁移风险，但 result_store 为运行时持久化、跨版本数据集可能留存）。**补测用例**：构造无 `cumulative_snapshots` 字段的数据集走 result_store 加载路径并切累积模式，断言不崩溃且 UI 给出明确空态（加载时校验字段缺失禁用累积模式并提示，或空态文案），避免旧数据静默输出 0.0 误导用户
- <!-- REVIEW-FIX-PREV: ISSUE-104 --> <!-- REVIEW-R1-FIX: ISSUE-102 --> **双提取路径快照行为等价（断言口径校正：不断言字段集合相等）**：累积模式消费端依赖 `_cumulative_snapshots` 快照字段（cumulative_card_counts/cumulative_draws/cumulative_pity_draws/cumulative_consumed/cumulative_gained/banner_end_resource/banner_end_resources），该快照由两条路径分别产出且**结构不同**：并行路径 `WorkerLocalExtractor.process`（streaming.py L348-357）产出 list 元素、含内层 `pool_id`/`pool_end_time` 字段；单线程路径 `DrawSequenceExtractor._update_cumulative`（L640-648）按 pool_id 分桶存 `_cumulative_snapshots[pool_id]`、dict 无内层 pool_id 键。**断言口径（与 AUDIT-TGAP-05 统一，见 §4.1 项 2）**：两路径快照**字段集本就不相等**（并行含 `pool_id`/`pool_end_time`，单线程无），本用例**不断言两条路径字段集合相等**（按字段集合相等写断言必失败），只断言累积模式消费端（`_compute_pool_gdr` banner 段取数）对字段集的依赖被 banner_of/防御读取代、在两条路径下**行为等价**。消费端若对两条路径的组织结构与字段集合假设一致而漂移，仅经单一路径构造回归数据时测试不会发现，故必须双路径构造。**补测用例**：分别经 batch_simulator 并行入口（WorkerLocalExtractor + merge_extraction_packets 路径）与单线程 DrawSequenceExtractor 路径构造累积快照，断言累积模式消费端（`_compute_pool_gdr` banner 段取数）在两条路径下行为一致。<!-- REVIEW-R1-FIX: ISSUE-130 --> **单线程路径构造方式（本条此前未指明，防实施时因构造成本跳过单线程分支）**：单线程路径构造入口 = `tests/core/test_transition.py` 既有 DrawSequenceExtractor 夹具模式（L123/L215/L261/L284）——实例化 `streaming.DrawSequenceExtractor(pool_end_times=..., ...)` 后逐 sim 喂构造 compact dict（compact 须含 `pool_end_times`/`banner_end_resources` 等键，经 `on_result`/`process` 触发 `_update_cumulative` L604-648，快照写入 `self._cumulative_snapshots[pool_id]` 按 pool_id 分桶）；数据夹具来源 = 复用 `tests/core/test_transition.py` 既有 compact 构造辅助或固定种子 `run_simulation` 产出 compact（`to_dict()` 后切片喂入），**不得与并行路径共用同一构造路径**。**断言对比基准（防「不断言字段集合相等」落空）**：单线程路径快照无内层 `pool_id`/`pool_end_time` 键（L640-648），并行路径有（L348-357）——断言对象不是字段集合相等，而是「`_compute_pool_gdr` banner 段取数在两条路径产出快照下均命中同 banner 段、同字段读取路径（banner_of/防御读）且取值一致」；若实施时因单线程构造成本高而跳过该分支，则「消费端对字段集依赖被 banner_of/防御读取代」的断言目标落空，故本条单线程分支**不得跳过**。
- <!-- REVIEW-R1-FIX: ISSUE-103 --> **`banner_of` 三态契约参数化单测（stage-1 P72-utils-1/T2 落点）**：`banner_of`（§4.1 项 5）是后续所有消费端（retreat_panel 1a、plan_search_panel 1b、process_analysis_panel 2a、analysis_panel 3d）复用的地基函数，其三态契约（None/空串→None、裸 banner 键（无'.'）→原样返回、含'.'的全限定键→取 '.' 前缀段）此前仅靠 §4.1 项 2 文字定义与 plan_search_panel「选择(从头开始)不崩溃」集成场景覆盖，**无纯函数单测**——空值/裸键/全限定键三类输入的回归无机器保护。**补测用例**：参数化单测覆盖 None / '' / 裸键（'b1'）/ 含多 '.' 的全限定键（'b1.main'）四类输入，断言返回值与契约一致；测试文件落 `tests/gui/`（如 `test_banner_of.py`，或并入既有 gui 测试）。**配套登记（stage-1 P72-utils-2）**：若按 §4.1 项 5 裁决落 `gui/utils.py`（新建模块），须同步把 `gacha_simulator.gui.utils` 加入 `tests/gui/test_gui_imports.py` 的 `GUI_MODULES` 清单（当前清单 13 项无此模块），防新模块 import 回归。
- <!-- REVIEW-R1-FIX: ISSUE-106 --> **键空间契约可执行断言（升级注释级契约为运行期断言，ISSUE-006/PPA-3 落点）**：ISSUE-006/PPA-3 的键空间契约修复目前是「消费端防御读 + docstring/契约注释」，核心产键方（`compute_vulnerability_analysis` 的 `pool_results.pool_id` 为 banner 键——vulnerability.py L542-545 取自 `banner_end_resources` 键空间；`per_pool_analysis.compute_cumulative_snapshots`/`cumulative_gdr_at_pool_ends` 键来自 `pool_end_times` 的 banner 键）均无运行期断言。契约只存在于注释时，任一消费端或产键方改动都可重新引入 banner/全限定不匹配而无声回归（与 ISSUE-002/ISSUE-703 本轮修复根因同源）。**补测用例**：固定种子跑真实模拟（走 `run_batch_parallel` 统一入口）后断言 (1) `compute_vulnerability_analysis` 产出的 `pool_results` 各 `pool_id` 均不含 '.'（banner 级）、与 `banner_end_resources` 键空间一致；(2) `compute_cumulative_snapshots` / `cumulative_gdr_at_pool_ends` 返回键均为 banner 级（与 `pool_end_times` 键空间一致）。该断言把「注释级契约」升级为「机器可查」，防止产键方/消费端两侧未来改动重引入键层级错配。
- <!-- REVIEW-R1-FIX: ISSUE-107 --> **回收站既有断言资产登记（`.recycle_bin/test_p72_key_repairs.py`，stage-1 P72-T1 高风险项落点）**：该文件已含 7 条 P72 键修复回归测试（`TestFindVulnerabilityPool`×4：`_find_vulnerability_pool('b1.main')` 命中 banner 键 / 裸键命中 / 无结果返 None / 空键返 None；`TestProcessAnalysisCumulativeKey`×3：`_compute_pool_gdr('b1.main')` 累积模式非 None、同 banner 多 pool 共享快照、缺 banner 快照返 None），断言点与 §4.3 目标（§4.1 项 1/2 确定性修复回归）重叠，但计划此前未登记/引用该资产。**登记与处置**：实施 §4.3 补测时先核对本文件断言点，与新补测**合并去重**（本文件已覆盖的断言点无需重写，迁移至 `tests/` 目录正式登记；未覆盖的按 §4.3 条目补）。**保护要求**：本文件位于 `.recycle_bin/`，按项目文件删除规则存在被 C4 回收站清理误删的风险——迁移完成前不得作为唯一修复断言资产存放（须保留备份），迁移后在回收站登记归档说明（如 `.recycle_bin/README.md` 注明「已迁至 tests/，可清理」），避免修复验证资产丢失。
- <!-- REVIEW-R1-FIX: ISSUE-108 --> **cumulative_by_banner 重命名全链运行期回归（阶段 1 P72-T4 补）**：重命名（项 3）的缺陷模式是**静默失效**（勾选 key 与 chart key 脱节 → 勾选不渲染、`_needs_computation` 恒 True、旧缓存残留），不崩、无报错，3a-1 的「grep 全量确认」静态清单无法捕获运行期 key 脱节。**补测用例**：勾选累积分析（`cumulative_by_banner`）后断言：(1) 生成的 chart key 前缀为 `cumulative_by_banner_`（不是旧前缀 `cumulative_by_pool_`，analysis_panel L1180 产键侧）；(2) `_needs_computation` 对该 key 非恒 True（重命名后同条件重算应命中已计算状态，analysis_panel L2275-2276 条件收集侧）；<!-- REVIEW-R1-FIX: ISSUE-123 --> **补充断言：勾选指标变化必须触发重算（防恒 False 静默不更新）**——L2138 等值分支（`key == 'cumulative_by_pool'`）漏改后 `_get_conditions_for_key('cumulative_by_banner')` 永不写入 `cond['cumulative_by_pool_selections']`、`_computed_conditions['cumulative_by_banner']` 缺该键，`_needs_computation` 对指标勾选变化恒判「不需重算」（**恒 False**）；该缺陷模式与现有断言 (2) 要防的「恒 True」相反，且恒 False 也满足「非恒 True」断言，现有断言测不出此缺陷。**追加定向断言 (2')**：变更累积指标勾选（如切换 GDR 指标选择）后 `_needs_computation` 返回 **True**（触发重算），与 (2) 的非恒 True 并存（(2) 防恒重算、(2') 防恒不重算，两个方向都锁）；(3) ChartWebView `has_chart`/`update_chart` 命中新前缀、旧前缀缓存不残留（chart_webview.py L321/L355 消费侧，3b 边界）。断言对象按 3a-1/3a-2/3b 的文件归属分别落 `tests/gui/`，捕获任一适配点漏改导致的不渲染/恒重算/缓存残留。
- <!-- REVIEW-R1-FIX: ISSUE-109 --> **RetreatConfigBuilder ISSUE-101 兜底命中独立回归（§4.1 项 1 ISSUE-002 的机器可查断言）**：`tests/core/test_retreat_config.py` 现有用例全部传全限定键（pool_2/perm.main/early.main），无「裸 banner 键 from_pool_id 触发 L26-32 兜底命中遍历序首个池」的断言；§4.4 的 golden 快照对照是运行时人工对照、非机器可查。路线 A 是已裁决的不可逆语义变化（§4.4 自述不承诺恢复等价行为），最需要回归锁定。**补测用例（`tests/core/test_retreat_config.py`）**：多 pool banner（b1.main 在 b1.step1 前）下传 `from_pool_id='b1'`，断言：(1) 兜底命中 b1.main（`original_store.pools` 遍历序第一个 `pool_id.split('.')[0] == 'b1'` 的池）；(2) `offset_day` 取 b1.main 的 `end_day`（非 None 且 >0 时）否则 `start_day+21`，截断窗口整体平移；(3) 基准资源/保底水位初始化与传全限定键（'b1.main'）时的差异符合路线 A 裁决语义（命中首个池 = 从活动起点开始），并配套断言 min_resource 模式（`search_min_resource` 共用 `_build_env` 截断路径，见 §4.1 项 1 ISSUE-110 条目）。<!-- REVIEW-R1-FIX: ISSUE-110 --> **显示名不纳入断言（接受项登记同步）**：§4.1 项 1 ISSUE-110 已将 Pareto 结果页「起始池」显示名退化（plan_search_panel.py L460，显示链不经 `_get_pool_name`）登记为路线 A 接受项，本断言仅覆盖截断窗口/offset_day 语义，不含显示名校验。<!-- REVIEW-R1-FIX: ISSUE-129 --> **from_pool_id=None/空串 边界断言（同一回归文件补边界用例，避免裸 TypeError 泄漏）**：`build` 的 L26 `if from_pool is None and '.' not in from_pool_id:` 对 `from_pool_id=None` 执行 `'.' in None` 裸抛 `TypeError: argument of type 'NoneType' is not iterable`（非本计划兜底语义声明的错误路径）；`RetreatConfigBuilder` 为 `core/__init__.py` 导出的公共 builder，None 输入边界行为未声明，未来新增调用方误传 None 时错误信息不明确。**修复 + 断言（随 ISSUE-109 回归一并落地）**：`build` 首行加 falsy 守卫（`if not from_pool_id: raise ValueError(f"Pool '{from_pool_id}' not found in config")`，与既有「Pool ... not found」统一错误路径，注：既有错误路径现位于 L40，原 L35 引用为审查时行号），补测三条用例——传 None / 传 '' / 传空白串（'  '），断言统一抛 `ValueError` 且消息含「Pool ... not found」，不得泄漏裸 TypeError；守卫不影响现有用例（现有 `tests/core/test_retreat_config.py` 用例全部传非空键，行为不变），亦不改变 ISSUE-101 兜底命中语义（非空裸 banner 键仍走 L26-32 前缀匹配）。

### 4.4 回滚策略

<!-- REVIEW-FIX-PREV: GATE-5-rollback-path -->

**总则：** 每 §4.1 项独立 commit，`git revert <commit>` 可独立回滚，项与项之间无提交顺序依赖、互不牵连。§4.1 拆解后的子任务（见项 1-5 拆解表）同粒度独立 commit，回滚粒度 ≤1h 子任务。

**确定性键错配修复（项 1/2）的基线对照：** 按 CLAUDE.md「基线固化 + 等价对照」原则，修复前对固定种子固化 CompactResult golden 快照（含 `pool_end_times`/`cumulative_snapshots`/`banner_end_resources` 等键空间），修复后同种子重跑逐字段对照；回滚即恢复旧快照基线。项 1 若走路线 A（统一 banner 键）会改变截断起点语义（ISSUE-002 兜底漂移），须在 golden 对照中显式记录该差异并声明为**不可逆语义变化**，回滚策略对路线 A 不承诺恢复修复前等价行为。

**项 3 重命名的回滚与缓存降级：** rename 为 `cumulative_by_banner` 后，旧 `cumulative_by_pool_` 前缀 chart key 不再被 `_get_ordered_charts` 前缀匹配收集，ChartWebView 历史缓存项将静默不渲染。实施时二选一并写入项 3：
- **(a)** 重命名时主动清 ChartWebView 旧前缀缓存（`has_chart`/`update_chart` 对旧 key miss 即重建，`set_charts` 全量重建时自然覆盖）——推荐，与命名澄清目标一致；回滚后旧缓存已被清空、需重跑模拟重建图表，属预期行为。<!-- REVIEW-R1-FIX: ISSUE-105 --> **Python 侧缓存旧键清理补充**：与 ChartWebView 侧同步，重命名时对 analysis_panel `_chart_specs_cache` 做旧 `cumulative_by_pool_` 前缀 prune（见 §4.1 项 3 的 3a-1 适配点），否则旧前缀键残留在 Python 侧缓存、经 `_get_ordered_charts`（L2432-2434）尾部兜底呈现无名图表；回滚后同样需重跑模拟重建图表，属预期行为。
- **(b)** `_get_ordered_charts` 前缀匹配兼容新旧两前缀——不推荐（旧前缀残留与命名澄清目标冲突），但回滚无缓存残留成本

**挂起项回滚边界：** N1/N2（等 P71）、single_pool 分支 + N3（等 §5.1 裁决）、局部窗口（A'）等挂起项（§4.2）不在本计划改动范围内，回滚策略不覆盖、实施者也**不得**回滚这些路径（防止实现者误认为挂起修改在回滚范围内）。

## 5. 与直接显现问题的关系（P58 第 3 轮核查，2026-08-06 更新处置）

| 问题 | 处置 | 状态 |
|------|------|------|
| N1（single_pool 减错字段）| draw-only 口径执行细节，方向由 P71 维度 3 裁决 | 挂起（等 P71）|
| N2（跨 banner 赠卡残留）| 同 N1，累计窗口下赠卡扣减细节 | 挂起（等 P71）|
| N3（pool_ids_ordered 键层级错配）| 绑定 single_pool 分支去向（§5.1）；受影响消费方含转变分析 single_pool scope 与每池成功率「第k池单池」scope（<!-- REVIEW-FIX-PREV: ISSUE-102 --> 见 §2.3，§5.1 裁决激活 N3 修复时须一并覆盖此入口，防漏改）| 挂起（等 §5.1 裁决）|
| process_analysis 累积模式错配 | 累积模式取 banner 段（数据源键正确，修消费端）+ 列头/下拉标签语义标注（R1，ISSUE-005）| 本计划修 |
| 脆弱性 → 方案搜索链路错配 | 消费端统一匹配键（脆弱性产出 banner 键正确）；retreat_panel `_get_pool_names` 同根因一并修（R1，ISSUE-001）| 本计划修 |
| 截止每池 GDR 命名 | `cumulative_by_pool` → `cumulative_by_banner`；process_analysis_panel 下拉标签同步（R1，ISSUE-005）| 本计划修 |

### 5.1 待决子项：`per_pool_target` 成功判据去向

GUI 成功判据「每池至少一张目标卡」（`per_pool_target` → scope=single_pool）语义上要求 pool 级判定，但方案 A 转变分析单元是 banner。候选：
1. **banner 化**：改为「每 banner 至少一张目标卡」，读 banner 前缀聚合的全限定表，与方案 A 一致
2. **保留 pool 级**：作为独立的下钻视图分析，与主转变分析（banner）分开，需要 pool 级数据基础（属演进路径 A' 领域）
3. **移除**：暂时去掉该判据，待 A' 落地再恢复

待用户裁决，不在此擅自决定。

> <!-- REVIEW-FIX-PREV: D1-裁决 --> **D1 已裁决（2026-08-07）**：本计划**暂时放弃转变分析**（含 §1.5 方案 A 的转变矩阵展示、per_pool_target 去向、吸收态标注 §4.1 项 4、N3 完善、演进 A'），全部移交 **P76（转变分析重构专题，占位，2026-08-07 创建）**。本计划仍保留：转变分析依赖的**确定性键错配修复**（键空间统一，使现状按方案 A 语义至少正确运行），即 §4.1 项 1/2/3/5 中与转变分析共享的键空间修复（如 `banner_of`、累积快照 banner 段）；§5.1 候选 1/2/3 不再由本计划裁决，转入 P76 待决清单。实施者注意：转变分析相关 GUI（success_criteria 下拉、转变矩阵、吸收态标注）**不在本计划改动范围**，仅保留键错配修复使其现状语义正确。

> <!-- REVIEW-FIX-PREV: ISSUE-003 --> **现状说明（2026-08-07）**：该判据当前在转变分析中**未产生有效判定**。但「恒判失败」结论仅对回退路径成立，主路径为「被旁路」，两条路径事实不同。<!-- REVIEW-FIX-PREV: ISSUE-101 --> 完整事实分述如下：
> - **主路径（transition_flags 非空，正常批量模拟）**：analysis_panel L1357 `if self.transition_flags:` 直接使用 streaming 提取器预计算的 transition_flags（每 sim 一组按 pool_end_times 排序的 bool），**完全不查询 success_criteria_combo 与 criteria_map**。此分支下 success_criteria 下拉（全部目标/至少SSR/每池至少一张目标卡）是静默 no-op。选 any_ssr 或 per_pool_target 得到的结果与 all_targets 完全相同，per_pool_target 既非「失效」也非「生效」而是「从未被咨询」。且 `_get_conditions_for_key('transition_analysis')`（L2118 `cond['success_criteria']`）把 success_criteria 纳入条件组合，用户切换判据时 combo 变动触发重算但输出不变（假变化）。streaming 提取器的 `_check_success_draw_only`（streaming.py:392-419）硬编码 draw-only all_targets 语义（L406 无 target_specs 返 False，L416 遍历 target_specs 全量达成才 True）。
> - **回退路径（transition_flags 为空，如 result_store 旧数据集加载）**：才走 criteria_map（L1360-1364）+ `compute_transition_flags_from_gdr`。此路径下 `per_pool_target` → `('target_card_draws','single_pool',1.0)`，single_pool 分支（per_pool_analysis L359-368）把 banner 键 `pool_ids_ordered` 传给 `compute_pool_gdr_single_pool`，其 L292 `pool_card_counts.get(banner键)` 恒空 → card_counts 空 → target_card_draws=0 < 1.0 → 全部 sim 判失败（N3 键错配，此即「恒判失败」结论的成立范围）。
>
> **对 §5.1 候选裁决的影响（ISSUE-101）**：候选 1（banner 化）若仅在回退路径改 criteria_map **无法让主路径生效**。主路径由 streaming 提取器硬编码 all_targets，还需让 streaming 提取器或转变分析分支（L1357-1377）遵守所选判据；候选 3（移除）须知情：移除的是主路径下「被旁路」、回退路径下「恒判失败」的判据，两路径下均无有效行为。用户裁决时须知情：候选 3 是移除一个**当前两路径下均未产生有效判定**的判据而非正常功能；候选 2（保留 pool 级）不应高估其当前可用性。**若裁决保留该判据**，登记后续改动点：让 streaming 提取器 `_check_success_draw_only` 或转变分析分支尊重所选 success_criteria（现主路径旁路处 L1357-1358），并同步 `_get_conditions_for_key` 的 combo 参与（避免假变化触发重算）。

## 6. 演进路径 A'（待后续裁决，非本次范围）

方案 A 的已知限制是「累计窗口吸收态，转变矩阵测不出真转变」。演进方向 A'：

- **序列**：保持 banner
- **窗口**：从累计改为**局部**（相邻 banner 结束点之间的区间增量）
- **数据基础**：齐备（相邻 `pool_end_times` 之间即区间，无需新增数据）
- **判据**：局部窗口下「全部目标卡达成」语义不成立（单活动通常凑不齐全部目标），需改为局部化判据（如「该活动期间出了目标卡/SSR」）
- **效果**：AB/BA 非零，转变矩阵恢复「活动间转运/翻车」的语义

A' 与方案 A 的差异只在 streaming 判成败的统计窗口（累计 → 局部），键空间/赠卡修复与 A 共用，可平滑升级。B 方案（pool 级阶段转变）因缺 pool 开放区间数据（`switch_to` 不记录切换时刻、并行复合池无法定义区间）暂不采纳，登记为后续可选。

## 实施任务清单（plan-execute 消费）

> 2026-08-08 由 plan-execute 前置补记——把 §4.1 修复项 + §4.3 补测转为 checkbox 任务清单（依赖序：项 5 banner_of 先行 → 项 1 → 项 2 → 项 3 → 测试）。项 4 已移交 P76 不实施。
> ✅ **2026-08-08 全部 9 项实施完成**：11 个提交（Task 1-9 + Fidelity 修复），246 passed 回归（tests/gui 全量 + core 相关子集），Fidelity 独立审查闭环（无 critical，6 条偏离已修）。

- [x] Task 1: 项 5 `banner_of` 统一键辅助（新建 `gui/utils.py` + None/空串/裸键/全限定四态契约 + `tests/gui/test_banner_of.py` 参数化单测 + `test_gui_imports.py` GUI_MODULES 同步）
- [x] Task 2: 项 1a/1d `retreat_panel._get_pool_names` 补 banner→name 映射 + `PoolVulnerabilityResult` 键契约注释（ISSUE-006）
- [x] Task 3: 项 1b/1c `plan_search_panel` 路线 A（`set_store` 按 banner 去重 + `_find_vulnerability_pool` 匹配 + falsy 守卫 + `_get_pool_name` banner 映射，D3）
- [x] Task 4: 项 2a/2b `process_analysis_panel._compute_pool_gdr` 累积模式 banner 段取数 + 列头/副标「截止该 banner 段」口径标注（含 bb_table）
- [x] Task 5: 项 2c 空快照返 None（`per_pool_analysis` 累积分支短路，core 例外登记）+ 2d-1 未触达继承态展示口径
- [x] Task 6: 项 3a/3b/3e analysis_panel chart key `cumulative_by_pool`→`cumulative_by_banner` 全链替换（含 `_chart_specs_cache` prune、`_get_ordered_charts`）+ ChartWebView 缓存 + `pool_gdr_mode` 下拉标签
- [x] Task 7: 项 3d 显示名 banner 映射（`_get_pool_names` 补 banner 层 + `_banner_label`，供山脊图/转变矩阵标题）
- [x] Task 8: 项 3c 非代码引用同步（`02-实施.md`/`00-档案.md` 改 `cumulative_by_banner`；POC DatasetWorkbench/methodDefs 走 legacy 豁免登记不改）
- [x] Task 9: §4.3 补测试（键空间契约运行期断言 + 未达边界 + 双路径快照行为等价 + result_store 加载边界 + 脆弱性链路混合抽卡回归）

## 自动化审查记录

<details>
<summary>第 N-1 次审查（上次）</summary>

- 复杂度: complex | 变更性质: evolutionary
- 阶段 1 影响面: 25 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 29 个

</details>

<details>
<summary>第 N 次审查（2026-06-11）——P38 工作流自动化</summary>

- 复杂度: complex | 变更性质: evolutionary
- 阶段 1 影响面: 65 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 31 个

</details>

## ⚠ 自动化审查阻塞项

未解决问题：0 个

详情: []

标注原因：6 轮对抗循环未收敛
