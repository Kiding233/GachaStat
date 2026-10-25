# GachaStat

> 抽卡机制的概率模拟与统计分析系统

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt)](https://www.riverbankcomputing.com/software/pyqt/)
[![Tests](https://img.shields.io/badge/Tests-3085_passed-success)](./tests/)
[![Version](https://img.shields.io/badge/Version-2.5.0-blue)](./gacha_simulator/_version.py)
[![License](https://img.shields.io/badge/License-GPLv3-blue)](./LICENSE)

GachaStat 是一个抽卡机制的概率模拟与统计分析系统，用 Python 实现，由三部分组成。

**模拟内核** 把配置描述的卡池机制、资源与策略转成抽卡时间线，执行并行批量模拟，产出统一的结果对象。机制建模覆盖基础概率、保底、资源与时间规则、溢出、里程碑与复刻；未等价支持的机制统一登记在配置手册的功能缺口表与模块状态矩阵中。

**分析方法** 只依赖结果对象，计算分布、统计量、评价函数与检验，包括资源分布、出卡间隔、广义出率（GDR）、风险度量、过程分析、脆弱性、最差影响、方案搜索与策略比较。

**界面** 以 PyQt6 桌面界面为主，使用 Plotly 交互式绘图与数据驱动控件；新 WebUI 与新交互逻辑正在设计中，CLI 面向自动化脚本。

所有分析的输入都是模拟过程中产生的信息。系统不接入游戏客户端，不读取账号数据。

---

## 目录

- [适用场景](#适用场景)
- [快速开始](#快速开始)
- [一、模拟内核](#一模拟内核)
- [二、分析项及其原理](#二分析项及其原理)
- [三、配置模型](#三配置模型)
- [四、架构与数据流](#四架构与数据流)
- [五、扩展指南](#五扩展指南)
- [六、开发与测试](#六开发与测试)
- [七、版本与许可](#七版本与许可)

---

## 适用场景

| 问题 | 支撑能力 | 状态 |
|------|----------|------|
| 按当前配置，抽齐目标卡的概率是多少？ | 目标达成类 GDR + 成功概率（Wilson 区间） | 稳定 |
| 同样资源，换一种抽法结果差多少？ | 策略系统 + 比较分析（L1 至 L4） | 稳定 |
| 运气最差时，剩余资源还够抽几次大保底？ | 最差影响分析（虚拟池 + 覆盖倍数 + CVaR） | 已实现，剩余缺陷在办 |
| 哪个参数最影响结论，会不会翻盘？ | 敏感性分析（参数扫描 + 翻转区间） | 设计中 |

---

## 快速开始

### 使用打包版（推荐）

打包产物是 PyInstaller onedir 目录，目录内 `GachaStat.exe` 为桌面 GUI 入口。解压后直接运行，不需要安装 Python 或配置环境。

- 首次启动使用内置 `config.toml`，按「配置 → 批量模拟 → 分析」的顺序使用。
- 用户数据与输出写入 `%APPDATA%/GachaStat/`。
- 自行构建：`pyinstaller GachaStat.spec`，产物在 `dist/GachaStat/`。

WebUI 版随后续界面计划提供打包入口。当前开发版通过源码启动：

```bash
python -m gacha_simulator.main_webview
```

### 从源码运行（开发用）

```bash
pip install -e ".[gui,dev]"     # GUI + 开发依赖
python -m gacha_simulator.main  # 桌面界面
```

### 命令行（面向自动化，非默认使用方式）

```bash
python -m gacha_simulator.cli -n 1000 -w 4 -s 42
```

常用参数：`-c` 配置文件、`-n` 模拟次数、`-w` 并行进程数、`-s` 随机种子、`-o` 输出文件、`--strategy` 策略键、`--output-format` 输出格式。完整说明见 `--help`。`--migrate` 仅兼容旧调用保留，旧格式迁移能力已移除。

---

## 一、模拟内核

### 1.1 理论模型与契约

```
假设层：有哪些池子、机制是否确定
        ↓
机制层：卡池机制、资源与时间规则
        ↓
行动层：行动空间 → 策略（当前可知信息 → 这一步行动）
        ↓
轨道层：一条时间线 = 离散时间随机过程的一条样本轨道
        │  样本轨道是向量值函数：t 取非负整数，每个 t 对应一个结果向量
        ↓
摘要层：结果对象 CompactResult（逐抽事件、汇总统计、池快照）
        ↓
分析层：分布、统计量、评价函数（GDR 等）、检验、决策
```

- 假设层：池子集合与机制参数由配置给定。
- 机制层：卡池机制（基础概率分布与保底修正算子）以及资源、时间、溢出、里程碑规则。
- 行动层：行动空间决定可选动作；策略是输入当前可知信息、输出这一步行动的函数。
- 轨道层：一条时间线是样本轨道；t 取非负整数，每个 t 对应一个结果向量，编码该时刻的全部状态信息。
- 摘要层：样本轨道压缩为结果对象，分析只读摘要。
- 分析层：GDR 是样本轨道上的泛函；分布、统计量与检验在摘要上计算。

结果对象是模拟与分析的唯一契约：内核不暴露内部状态，分析层也不读内核对象。

### 1.2 机制建模

**Banner 与池子。** 一个 Banner 被视为一个卡池，包含一组池子（`[[banner]]` 下挂 `[[banner.pool]]`），用于建模卡池内强制送抽、step 池等特殊机制。每个池子有消耗与奖励列表（`[[banner.pool.reward]]`），奖励按卡牌、概率、稀有度、是否 UP 描述，基础概率分布由池内奖励概率给出。

**保底。** 保底是概率修正算子，不是特判，由三族零件组合：

| 零件 | 职责 |
|------|------|
| Tracker | 记录状态：计数器、保底标志、连续命中、定轨进度 |
| Modifier | 修改分布：加增量、设阈值、换目标集 |
| Lifecycle | 控制生效范围：常驻、有限、依赖其他保底 |

三族零件组合出 13 种保底行为（`BEHAVIOR_REGISTRY`）。概率管道按卡级增量一次到底，归一化由框架统一完成，每个组合都按概率行为、状态转移、边界条件逐项验证。

**其他机制。** 溢出转换用分段表（`OverflowBand`）统一在 `add_card()` 里匹配区间并返回溢出资源；里程碑奖励是独立计数器引擎（`MilestoneEngine`），支持阈值、重复、交替奖励；资源生命周期按到期时刻转换或清零；复刻通过 `rerun_of` 标签表达。

### 1.3 行动空间与策略

池子按产出分三类：随机出卡池、确定性出卡池（兑换池，100% 产出指定卡）、资源产出池。兑换与商店不引入独立动作类型，而是通过这三类特殊池加抽卡动作表达：兑换是确定性出卡池，商店是随时间开放的资源池或兑换池，消耗用 `cost` 的多资源与 OR/AND 语法描述（如 `draw_resource:160 > exchange_currency:5`）。策略的输出是一个动作；兑换与商店都通过 `DrawAction` 表达，不区分池类型。

行动空间另有等待（`WaitAction`）与非抽卡动作（`NonDrawAction`：切换定轨目标、取消定轨路径）。策略是输入当前可知信息、输出这一步行动的函数，注册 8 种内置策略，支持插件目录扫描与启停；停止条件与策略分离，注册 7 种，支持 TOML 条件树与表达式编辑。

### 1.4 结果数据结构与流式分析

`CompactResult` 包含三类内容：逐抽事件（卡牌、时间、池子、保底标记、资源消耗与获取）、汇总统计（资源总量、持有、成功判定、池快照）、元数据（策略、版本、随机种子）。整个对象可序列化、可并行合并，内存为 O(1)。

流式分析是这一层的架构优化：`SharedResultCollector` 与 worker 侧提取器在模拟过程中增量计算部分分布统计，合并后仍写入同一结果对象；逐抽明细路径已删除，内存与模拟次数无关。分析阶段看到的数据结构与是否启用流式提取无关。

### 1.5 模拟执行与正确性

所有批量与并行模拟都必须经过 `service/batch_simulator.py` 的 `run_batch_parallel()`，CLI、GUI、WebUI、测试共用这一入口。并行用 `multiprocessing.Pool` + worker initializer 模式，策略与配置在子进程中重建；模拟过程中的事件通过 notifier 分发给里程碑引擎等订阅者。

内核的正确性靠三层机制保证：

- **等价性对比**：新实现与旧实现跑固定种子，逐字段对比概率行为与状态转移，任何差异都要解释或登记到缺口表。
- **不变式校验**：`InvariantChecker` 可选项运行时检查四层不变式（状态键、概率归一、生命周期、跨池一致性），生产默认关闭。
- **配置闸门**：重名校验、scope 白名单、参数键契约、停止条件形态检查，把「配置写了但运行时静默失效」提前到加载期报错。

---

## 二、分析项及其原理

### 2.1 结果对象与可分析量

所有分析项的输入都是模拟过程中产生的信息。实现中，这些信息经 `CompactResult` 压缩为四类字段：

| 来源字段 | 可计算的量 |
|----------|-----------|
| 逐抽事件 | 出卡间隔、事件序列、每池抽数与消耗、保底触发分布 |
| 资源账本 | 资源剩余、资源消耗、每池资源轨迹、收入与支出 |
| 持有与目标 | 目标达成率、收集率、重复次数、加权满意度 |
| 池快照与元数据 | 每池成败、池间转移、策略标签、可比性指纹 |

GDR 是其中一类评价函数，不是唯一产出；间隔分布、资源分布、事件分布同样由这些字段定义。

### 2.2 分布分析

**资源分布。** 对每次模拟结束时的资源剩余做经验分布，给出直方图、分位数与风险度量。这是最直接的结果视图。

**出卡间隔分布。** 对同一张目标卡的两次获得之间、或每次稀有卡之间的抽取间隔做分布，回答「多久出一张」。它不是 GDR，但与目标达成同样重要；当前为设计阶段，可视化方案已成型，尚未接入。

**GDR 分布。** 对某个 GDR 指标的 N 个取值做分布，是后续风险度量与比较分析的输入。

**每池分布。** 逐池统计抽数、消耗、出卡与是否达成，用于定位是哪个池子拖累了整体。

### 2.3 评价函数：GDR 指标族

**回答的问题**：一次抽卡尝试好不好，好到什么程度。

**原理**：GDR 是定义在样本轨道上的泛函，并约定函数值具有自然、有意义的大小关系。它把无法直接比较的轨道压成一个可比较的数，随机过程复合 GDR 后成为随机变量。

按构造，GDR 可分为计数型、比率型、二值函数族、联合构造（多个 GDR 取 min）、保证型（在某个 GDR 达标的前提下再优化另一个）。计数型是最重要的一类：资源剩余、资源消耗、出卡数、抽数都是计数型，权重可以取 1，也可以按卡牌或资源价值加权；比率型由计数相除得到，如资源转化效率、每目标卡资源消耗。

当前注册 21 种，按语义可分为目标达成（`target_achievement`、`target_collection`、`all_targets`、`ssr_collection`）、资源效率（`resource_remaining`、`resource_efficiency`、`resource_per_card`、`resource_consumed`、`extra_target`、`non_pity_draws`、`pity_draws`、`draw_conversion_efficiency`）、加权综合（`weighted_satisfaction`、`total_card_value`、`per_pool_draw_rate`、`weapon_character_ratio`、`target_card_draws`）三类，另有 4 个 `_obtainable` 变体：分母只统计模拟期间已开放池子里的可达目标卡，避免不可达卡造成虚降。

**产出**：每条时间线一个实数；配合成功阈值得到成功概率 P（GDR ≥ c）。

**状态**：稳定。21 种指标都满足「样本轨道 → 实数」，其中部分是否满足「自然大小关系」仍需逐项判断，属于广义用法。GDR 的选择有主观性，部分指标在策略比较中会退化（几乎不随策略变化），需要实际验证。

### 2.4 统计推断与风险度量

**描述统计与风险。** 对某个量的 N 个取值计算均值、中位数、标准差、偏度、峰度、下 α 分位数（VaR）、尾部条件期望（CVaR）、成功率与极值。VaR 回答「有 α 的概率比这个数更差」，CVaR 回答「最差 α 部分的平均有多差」。

**Bootstrap 与 BCa。** 对已有结果做有放回重采样，重复估计统计量，得到经验抽样分布；BCa（偏差校正与加速）修正偏差和偏度，给出更可靠的置信区间。Bootstrap 同时用于稳定性评估。

**极值理论。** 对超过阈值的超额值拟合广义帕累托分布（GPD，POT 法），外推更远的分位数与 CVaR；下尾用统一取负法转成上尾处理；阈值稳定性诊断检查形状参数是否随阈值剧烈变化。稀有事件采样不足时，这是尾部估计的主要手段。

**状态**：稳定。EVT 在离散分布上会退化，退化条件已登记。

### 2.5 过程分析

**回答的问题**：不是只看最终成败，过程里发生了什么。

**原理**：对每条时间线逐池推断事件：普通池有 pity_hit、early_hit、miss、skip、ignore，兑换池有 exchange、no_exchange，资源池有 resource_draw、resource_ignore。事件序列与池子成败做四类交叉统计（AA 事件×事件、BB 成败×成败、AB 事件×成败、BA 成败×事件），并支持事件组合模式与自定义约束。比例估计用 Wilson 区间。

**产出**：事件分布、交叉统计表、事件模式。

**状态**：核心稳定，事件细化在办。

### 2.6 脆弱性分析

**回答的问题**：在什么资源水平上，失败风险会突然升高。

**原理**：按池子结束时的资源分箱，比较全部样本与失败样本的失败率；用 binsglm 分箱后做 PAVA 保序回归，强制失败率随资源单调，再用 m-out-of-n Bootstrap 估计变更点（失败率显著抬升的位置）的置信区间。校准曲线与变更点一起构成脆弱区间。

**产出**：失败率曲线、脆弱区间、变更点置信区间。

**状态**：稳定。binsglm 不可用时回退局部逻辑回归。

### 2.7 最差影响

**回答的问题**：这一轮抽完之后，最差还能撑多久。

**原理**：从当前结果出发，构造后续虚拟池序列，估计剩余资源在连续池子推进下的最差水平；用覆盖倍数（剩余资源能覆盖几倍大保底所需资源）与 CVaR 量化风险。虚拟池的卡集合按池内真实 id 生成，保底才真正生效；匹配现有池子用 fnmatch。

**产出**：覆盖倍数、最差资源分布、反事实路径。

**状态**：已实现，剩余缺陷在办（逻辑跳跃、虚拟池同质、池数上限、无资源收入）。

### 2.8 方案搜索

**回答的问题**：目标定多了还是定少了，最少需要多少资源。

**原理**：前进法按抽取意愿排序依次加入目标卡，后退法按错失代价排序依次删去目标卡，每次重算成功概率；最少资源搜索用二分找达到目标成功率所需的最少额外资源；Pareto 前沿给出「资源」与「目标数」两个维度上的非支配解集。

**产出**：退路方案、最少资源、Pareto 前沿。

**状态**：稳定，理论改进在办。

### 2.9 比较分析（L1 至 L4）

**回答的问题**：两个策略或两份配置，差别是否真实存在。

**原理**：四层递进。

| 层 | 方法 | 回答什么 |
|----|------|----------|
| L1 | 描述统计 | 各自的均值、中位数、分位数、偏度、CVaR、成功率 |
| L2 | DD Bootstrap | 两条分布之差（差异分布的 bootstrap）是否有系统性偏移 |
| L3 | 假设检验 | Mann-Whitney U、随机占优（Donald-Hsu 2016 选择性重中心化，依赖可选包 PySDTest） |
| L4 | 帕累托前沿 | 多指标同时比较时的非支配解集 |

**产出**：比较摘要、差异分布、检验结论、前沿。

**状态**：L1 至 L3 稳定，L4 可用；B 减 A 的完整差分布设计中。

### 2.10 敏感性分析

**回答的问题**：参数动一下，结论会不会翻。

**原理**：沿参数维度扫描，记录关心的量如何变化，给出翻转区间与裕度。参数按「模拟器读不读它」分四类：口径参数、策略参数、机制参数、精度参数。扫描规格三种：数值栅格、离散枚举、互斥分支。翻转点用「均匀采样 + 细化」定位，不纯用二分，避免遇跳变失效。

**产出**：响应曲线、翻转区间、成立域。

**状态**：设计中，界面为占位页。

---

## 三、配置模型

配置文件是单个 TOML 文件，由 GUI 生成或手写。核心结构是 Banner：一个 Banner 被视为一个卡池，包含一组池子，用于建模卡池内强制送抽、step 池等特殊机制；池子与奖励挂在 Banner 下；保底、里程碑、资源生命周期是顶层规则，通过作用域或 banner 字段与 Banner 关联。

```toml
[[banner]]
id = "b1"
name = "示例卡池"
start_day = 0
end_day = 21

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "limited_ssr_1"
probability = 0.006
rarity = "ssr"
featured = true

[[pity]]
name = "ssr_soft"
type = "soft_interval"
scope = "ssr"
reset = "featured"
start = 80
end = 90
```

| 段 | 说明 |
|----|------|
| `[[banner]]` | Banner 定义：一个卡池，包含一组池子 |
| `[[banner.pool]]` | 池子：id 与消耗方式 |
| `[[banner.pool.reward]]` | 池内每个奖励：卡牌、概率、稀有度、是否 UP |
| `[[pity]]` | 保底规则：类型、作用域、重置方式、阈值或区间 |
| `[[milestone]]` | 累抽奖励：阈值、重复、最大触发次数 |
| `[[targets]]` | 目标卡与数量 |
| `[strategy]` | 策略键与参数 |
| `[rarities]` | 稀有度排序 |
| `[resources]` | 资源定义、收入日历、初始值、生命周期 |

字段级说明见 GUI 的「帮助 → 关于 → 配置文件指南」。

---

## 四、架构与数据流

```
gacha_simulator/
├── core/            # 引擎层，无 GUI 依赖（42 个模块）
│   ├── pool.py, banner.py          # 卡池与 Banner
│   ├── pity*.py                    # 保底：Tracker / Modifier / Lifecycle
│   ├── overflow.py, milestone.py   # 溢出、累抽奖励
│   ├── action.py, state.py         # 行动与状态
│   ├── strategy.py, stop_condition.py
│   ├── result_types.py, collector.py # 结果数据结构
│   ├── gdr.py, bootstrap.py, evt_tail.py, distribution.py
│   ├── vulnerability.py, worst_impact.py, retreat_search.py
│   ├── comparison_analyzer.py, process_trace.py, streaming.py
│   └── config_store.py, config_toml.py
├── service/         # 服务层：单次调度与并行批量入口
├── gui/             # PyQt6 界面（17 个模块）
├── webui/           # WebUI 后端（7 个模块）
├── strategies/      # 8 个内置策略 + 插件示例
├── config/          # 默认 config.toml
├── visualization/   # ChartSpec 与 Plotly 渲染
├── main.py / main_webview.py / cli.py / run.py
└── paths.py
```

仓库根目录另有 `tests/`（102 个测试文件）、`docs/`（文档体系）、`benchmarks/`（性能测量资产，不进发布产物）、`tools/refcheck/`（文档与代码互引工具）。

```text
ConfigStore → SimulationEnvBuilder → SimulationEnv
    → GachaService(banners, strategy, stop_condition)
    → run_simulation(CompactCollector) → CompactResult
    → SharedResultCollector / ResultStore
    → 分析面板（GUI / WebUI）或 CLI 输出
```

### 4.1 交互式绘图

图表是可缩放的 Plotly 交互图，嵌在 `QWebEngineView` 里（`gui/chart_webview.py`）。实现上有四个设计点：

- 一个面板共用一个 HTML 与一个 WebView，图表切换用 JS 的 display 控制，切换无延迟。
- 增量更新单个图表：新数据通过 `runJavaScript` 原地重建，不重载页面。
- 防闪烁：初始化时预加载骨架页（含 plotly.js 与重建函数），首次与后续更新都走原地重建；预加载未完成时把图表挂起。
- ChartSpec 中间表示：图表先描述成与绘图库无关的规格，再由 Plotly 渲染器产出，GUI 与 WebUI 共用同一套图表语义。

### 4.2 交互与控件

策略参数、停止条件参数由 `ParamDescriptor` 声明，`gui/param_renderer.py` 按类型自动分派 Qt 控件；新增策略或停止条件时不需要改面板代码。

两个 Qt 层面的细节：`gui/wheel_blocker.py` 用全局事件过滤器拦截下拉框与数值框的滚轮并转发给外层滚动区，避免页面滚不动；`gui/slot_guard.py` 用全局 excepthook 与 `@guarded_slot` 保护槽函数，避免 PyQt6 在槽内异常时直接终止进程且不留 traceback。

分析结果以结果单元卡片组织，数据由 `ResultStore` 保存、加载、比较、导出；每次结果带可比性指纹，记录影响结果可比性的配置维度，指纹不一致的数据集在比较时会被明确拦下。

### 4.3 WebUI

`main_webview.py` 用 PyWebView 加载前端，与桌面 GUI 平行，共用 core 与 `config.toml`。前端技术栈为 Vue 3 + Vite + ECharts，组件库仍在选型。当前为开发版，打包入口随后续界面计划提供。

---

## 五、扩展指南

| 扩展目标 | 入口 |
|----------|------|
| 新 GDR 指标 | `core/gdr.py` → `UNIFIED_GDR_REGISTRY` 注册 `GDRDefinition` |
| 新保底行为 | `core/pity.py` → `BEHAVIOR_REGISTRY` 注册 preset |
| 新策略 | `strategies/builtin/*.py` 或插件目录 → `@register_strategy` 装饰器 |
| 新停止条件 | `core/stop_condition.py` → `STOP_CONDITION_REGISTRY`，并声明 TOML 形态 |
| 新 GUI 面板 | `gui/` 创建 → `MainWindow._setup_ui()` 注册 Tab |
| 新 Banner 生命周期规则 | `[[banner.lifecycle]]` TOML 段 |
| 新资源生命周期规则 | `core/resource_lifecycle.py` + `[resources.lifecycle]` |
| 新里程碑 | `core/milestone.py` + `[[milestone]]` 段 |
| 新卡片维度 | `CardDefEntry.tags` / `list_tags`，TOML 中加一行即可 |
| 新配置项 | `ConfigStore` → `config_toml.py` → `config_panel.py` → `SimulationEnvBuilder` |

---

## 六、开发与测试

```bash
python -m pytest -q                      # 3085 passed, 35 skipped
ruff check gacha_simulator/              # 代码风格
python tools/refcheck/refcheck.py manual # 文档互引工具说明书
```

Windows 控制台默认 GBK，跑 CLI 子进程相关测试前建议设置 `PYTHONIOENCODING=utf-8`，否则中文输出会导致解码失败。

---

## 七、版本与许可

当前版本 2.5.0。版本历史见 `gacha_simulator/_version.py` 的 `VERSION_HISTORY`。

本项目以 GNU General Public License v3.0 发布。依赖中的 PyQt6 与 binsreg 同为 GPLv3 组件，打包分发时整体受 GPLv3 约束。详见 [LICENSE](./LICENSE)。
