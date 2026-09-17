# 回收站归档说明

本目录存放废弃/临时文件（非删除，按项目文件删除规则移入）。已迁移资产登记如下，可安全清理。

## 已迁至 tests/ 的资产

| 文件 | 迁移去向 | 说明 |
|------|---------|------|
| `test_p72_key_repairs.py` | `tests/gui/test_p72_key_repairs.py` | P72 键层级修复回归（2026-08-08 正式登记，含路线 A 修正与补测）。本回收站副本可清理。 |

## P81 代码清理专项归档（2026-09-16）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| `2026-09-16-p81-archived-tests/test_batch_service.py` | 测试对象在代码库中零定义，且整文件被模块级 `pytest.skip` 永久跳过 | 见 [P81 代码清理专项 §4.1-1](../docs/02-待办/P81%20代码清理专项.md)。该文件测的 `BatchService` / `BatchConfig` / `SimulationVariant` / `ConditionGenerator` 四符号生产代码零命中（实现被 `run_batch_parallel()` 这一函数式入口取代，`service/batch_service.py` 从未创建）；L45 另断言已于 P60 删除的 `GachaState.pity_counters` 字段，取消跳过亦必失败。归档前基线 `pytest -q` = 1573 passed / 1 skipped。P57、P4 的测试落点已改指 `tests/service/test_batch_simulator.py`。 |

## P81 §4.1-7 归档（2026-09-16）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| `2026-09-16-p81-archived-config/gacha_simulator-pyproject.toml` | 根 `pyproject.toml` 的陈旧副本，全库零引用 | 见 [P81 代码清理专项 §4.1-7](../docs/02-待办/P81%20代码清理专项.md)。原为早期「包内独立 pyproject」布局遗留：version 与根同为 `1.6.0`、依赖表缺 `scipy`/`binsreg`/`tomli`/`tomli-w`、把 `PyQt6` 列为基础依赖。已复查 `*.spec`/`*.toml`/`*.cfg`/`*.yml`/`*.py`/`*.in` 均无引用。**同类事实**：本仓库从未安装过该包（`pip show` 无结果、无 `*.egg-info`），打包路径在开发中不被走到。 |

## P81 §三 C1 归档（2026-09-17）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| `2026-09-17-p81-archived-panels/strategy_panel.py`（682 行） | P8 面板合并后被 `plan_search_panel` 取代，且从未在 `main_window` 注册 | 见 [P81 代码清理专项](../docs/02-待办/P81%20代码清理专项.md) §三 C1。三种搜索模式（最多目标卡 / 最少资源 / 退路分析）均已并入活面板 `plan_search_panel`。 |
| `2026-09-17-p81-archived-panels/resource_search_panel.py`（646 行） | 同上 | 同上 |
| `2026-09-17-p81-archived-panels/retreat_search_panel.py`（549 行） | 同上 | 同上 |
| `2026-09-17-p81-archived-panels/test_strategy_search_panels_p79.py` | **随被测面板一并归档** | P79 5f2 落点，断言「两个死面板自建 env 不继承用户停止条件」这一**负面性质**。其被测对象已归档，故该断言不再有意义；**非覆盖度损失**（它不覆盖任何活行为）。P79 的 8.2 结论（搜索由硬边界收口）在活面板上仍成立，落点为 `plan_search_panel` 经 `retreat_search._build_env`。 |

**连带改动**：`tests/gui/test_gui_imports.py` 的 `GUI_MODULES` 去掉 `strategy_panel` 一项；`batch_simulator.py` 的模块 docstring 不再声称服务于两个已归档面板（改列为 cli / gacha_panel / webui / core 搜索分析模块）。P18 两条验收项 + P22 相关条目 + 验收清单三节 + 搁置计划记录本项的 savefig 范围，均已标注作废/收窄。

## P81 §三 D3 归档（2026-09-17）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| `2026-09-17-p81-archived-p61-scaffold/migrate_config_p61_ph4b.py`（140 行） | P61 Ph4b 一次性配置改写器，`[[pools]]` → `[[banner]]` | 见 [P81 代码清理专项](../docs/02-待办/P81%20代码清理专项.md) §三 D3。唯一输入形态（`[[pools]]`）已退役，`config.toml` 早已是新格式，再跑它是迁移一份已迁移过的文件。 |
| `2026-09-17-p81-archived-p61-scaffold/p61_verify.py`（204 行） | P61 专用等价对照脚本 | 自带 P61 专属归一化规则（`{pid}.main`→裸 pid、`pool_end_resources`→`banner_end_resources`、时间窗口字段不参与）。与 `baseline_pool_golden.json` **配对归档**——它的 `GOLDEN_PATH` 指向该 fixture，留着会成「读不存在文件」的坏工具。 |
| `2026-09-17-p81-archived-p61-scaffold/baseline_pool_golden.json`（67KB） | golden 快照（`meta` + `single` 8 个逐抽数组 + `batch_aggregate`） | 由 **P61 之前的旧代码 + 旧 `[[pools]]` 配置**产生，**不可复现**，故不能用于将来对照。其历史价值（证明 P61 等价）已由 P61 归档计划与提交记录承载，归档后仍可从 git 取回。 |

**协议范例的接替**：P61 这套「基线固化 + 等价对照」的范例角色，现由 **P79 的在线版本**承担——`scripts/p79_baseline.py` / `scripts/p79_verify.py` / `tests/fixtures/p79_golden/`（9 组策略快照）被活测试 `tests/test_p79_stop_condition_baseline.py` 消费，属常驻无回归护栏（可复现、有消费者），与 P61 这套一次性脚手架性质不同。

## P81 §三 批 A 归档（2026-09-17）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| `2026-09-17-p81-archived-legacy-services/config_service.py`（22 行） | 零调用方；其服务的「一配置一 JSON」模型已被 P53 的单一 config.toml 取代 | 见 [P81 代码清理专项](../docs/02-待办/P81%20代码清理专项.md) §三 B1 |
| `2026-09-17-p81-archived-legacy-services/analysis_service.py`（78 行） | 旧 GDR 计算器家族的服务层门面；同族其余两文件一并归档 | §三 B2。**注意**：与 `gacha_simulator/webui/analysis_service.py`（P74 新增同名无关类）**不同物**，勿混 |
| `2026-09-17-p81-archived-legacy-services/gdr_analysis.py`（228 行） | 旧 GDR 计算器（`SuccessProbabilityAnalyzer` / `LegacyGDRCalculator`，自标 DEPRECATED）；所在家族被 `UNIFIED_GDR_REGISTRY` + `GDRCalculator` 取代 | §三 B2 |
| `2026-09-17-p81-archived-legacy-services/generalized_drop_rate.py`（193 行） | 时间索引模型 `GDR(t)` 的 ABC 与 8 个指标类；统一后改为「不依赖时刻 t 的终局口径」 | §三 B2 |

**导出清理**：`core/__init__.py` 两个导入块 + 两段 `__all__`；`service/__init__.py` 现仅 `GachaService`。

## P81 §三 批 B 归档（2026-09-17）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| （无整文件归档） | — | 批 B 是**代码内删除**而非文件归档，故本表无新增文件。涉及文件：`core/gdr.py`（删 A6 旧注册表族全块 + D1 四符号）、`core/strategy.py`（删 `CompositeStrategy`）、`core/per_pool_analysis.py`（删 `compute_transition_matrices` + 两处失效导入）、`core/__init__.py`（六处导出名移除）。 |

## P81 A1–A4 批（2026-09-17）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| （无整文件归档） | — | 保底旧路径四项均为**代码内删除**，无文件移入本回收站。涉及文件：`core/pity.py`（`HardPityBehavior` 旧接口、`create_behavior` 的 `params` 旧路径、`PityEngine` 旧签名与 P75 守卫、`PityDefParsed`、`_parse_target_distribution`）、`core/config_store.py`（一处注释）、`core/__init__.py`（导出）、`tests/core/test_pity_rebind.py`（删 `TestLegacyRebind`）。行为等价性由 P79 在线护栏（`tests/test_p79_stop_condition_baseline.py`，14 passed 不变）实证。 |

## P81 §十 块 4 归档（2026-09-17）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| `2026-09-17-p81-archived-risk-analysis/risk_analysis.py`（97 行） | 全库零调用方；其输入类型（每局一整个明细列表）随 InfoVector 明细路径一并消失 | 见 [P81 代码清理专项](../docs/02-待办/P81%20代码清理专项.md) §十 / §0.4-4。GUI 的 `risk_worst_case`/`risk_best_case` 由 `analysis_panel.py:406-670` 自建、WebUI 由 `analysis_service.py:470-509` 的 `_risk_tail` 自建，两条路都不经它；`tests/`、`scripts/`、`gui/`、`webui/` 零引用；`GachaStat.spec` 的 hiddenimports 条目同批清除。**它是块 4b 的强制前置**：其 `:3` 的模块级 `from .gdr import resource_remaining` 会让删除 O(T) 族之后的 `import gacha_simulator.core` 直接失败 |

**连带清除（均为代码内删除，无文件移入）**

- `core/gdr.py`：`GDRDefinition.compute_from_history` 字段 + `UNIFIED_GDR_REGISTRY` 的 13 处实参 + 22 个以 `history` 为首参的顶层函数（213 行）
- `core/distribution.py`：`WorstCaseAnalysis`(L284) / `BestCaseAnalysis`(L316)（唯一消费者即 `RiskAnalyzer`）+ `EmpiricalDistribution.from_gdr`/`from_resource_remaining`/`from_batch`（零调用方），共 67 行
- `core/__init__.py`：按名清 4 处（`:55` 的两个类、`:56` 整行、`:146` 与 `:147` 的 `__all__` 条目）
- `GachaStat.spec`：清 `core.risk_analysis` 一行，并同批清 `core.gdr_analysis`（批 A 归档时漏改的同一清单条目）

**验证**：P79 在线护栏 14 passed 不变；全量 `pytest -q` 1563 → 1563 passed；`ruff check` 全绿；`import gacha_simulator.core, gacha_simulator.service` 通过。

## P81 §十 块 1/2/3/5/7 归档（2026-09-17，第 2 次提交）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| `2026-09-17-p81-archived-info-vector/info_vector.py`（58 行） | InfoVector 明细路径的最后载体；其唯一生产者 `InfoVectorCollector` 同批删除 | 见 [P81 代码清理专项](../docs/02-待办/P81%20代码清理专项.md) §十 / §10.11 第 2 次提交。生产管线全部经 `run_simulation_compact` → `CompactCollector`，该路径自 P12 起即记为「仅 collector=None 时触发」，从未被生产代码走到。其 `__reduce__` pickle 协议只为跨进程传递而存在，而该收集器从不在 worker 内运行，故协议本身也是死的 |

**连带清除（均为代码内删除与改写）**

- `core/collector.py`：删 `InfoVectorCollector`（40 行）+ `TYPE_CHECKING` 的 `InfoVector` 导入 + 重写 `on_bonus` 基类 docstring（原「`InfoVectorCollector` 继承空实现 → 历史路径静默丢弃 milestone 产出」随路径消失）
- `service/gacha_service.py`：**收拢 `_is_compact` 门控族**（1 处赋值 + 5 处条件初值 + 1 处注释 + 5 处 `if`，其中 1 处带 `else` 子句），删 `lightweight` 形参 / `self.session_id` / `import uuid` / `_EMPTY_DICT` / 去条件后不可达的尾部 `return collector.get_result()`，返回类型收为 `CompactResult`，`collector=None` 的默认构造改为 `CompactCollector()`；`_settle_resource_expiry` 的两处 `if total_consumed is not None:` 保护随之删除（收拢后恒真）
- `core/per_pool_analysis.py`：删 InfoVector 形状读取族 6 个顶层块（`CumulativeSnapshot` + `compute_per_pool_snapshots` / `compute_cumulative_snapshots` / 两个 `_batch` 包装 / `cumulative_gdr_at_pool_ends`），保留 `PoolSnapshot` / `per_pool_summary_stats` / `TransitionMatrix` / `compute_transition_matrices_from_flags` / `compute_transition_flags_from_gdr`
- `gui/gacha_panel.py`：删 `_calculate_quick_stats` 中按 InfoVector 形状访问元素的 `else` 分支（406-414，经复核三轮证实不可达）
- `core/__init__.py`：按名清 `InfoVector` / `InfoVectorCollector` / `CumulativeSnapshot` / 4 个 `compute_*` / `cumulative_gdr_at_pool_ends`
- **测试**：删 `TestNonCompactPath`（1 个用例）与 `TestPerPoolAnalysisBannerKeys`（2 个用例）。P72 的「键为 banner 级」约定仍由同文件的 `test_parallel_vs_single_thread_snapshot_equiv`（活跃抽取路径）守护

**验证**：P79 在线护栏 14 passed 不变；全量 `pytest -q` **1563 → 1560 passed**（−3 = 上述三个用例，与「预期 −1」的差额系块 7 裁决新增的 2 个）；`ruff check` 全绿；`import gacha_simulator.core / service / cli` 通过。

## P81 distribution.py 孤儿方法清理（2026-09-17）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| （无整文件归档） | — | 本批为**代码内删除**：删 `core/distribution.py` 的 13 个零调用方法与 `DistributionSummary` 类（唯一构造点是已删的 `summary()`），`core/__init__.py` 按名清两处导出。核验：AST 全库扫描零引用、无子类化、无动态属性钩子、`getattr` 字面名零命中、插件零引用。**注**：同批曾一度把 `DistributionSummary` 的 `@dataclass` 装饰器遗留在 `JointSamples` 上（致其不可哈希、`==` 恒真），已由 2026-09-17 收尾审查发现并修复 |

## P81 §12.5.2 generator 包归档（2026-09-18）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| `2026-09-18-p81-archived-generator/generator/`（`__init__.py` / `schedule_generator.py` / `target_generator.py`，共 101 行） | 整包零生产消费者 | 见 [P81 代码清理专项](../docs/02-待办/P81%20代码清理专项.md) §12.5.2。P53 把配置迁到单一 TOML 后，「程序化生成排期／目标」被「在 TOML 里写出来」取代；全库 import 只有它自己的 `__init__.py` 与两个测试，`core/`／`service/`／`gui/`／`webui/`／`cli.py`／`scripts/`／`tools/` 均无引用。**未损坏**（依赖的 `PoolSchedule`／`TargetCard` 字段未变），性质是「无人调用」而非「已失效」 |
| `2026-09-18-p81-archived-generator/tests/`（`__init__.py` / `test_schedule_generator.py` / `test_target_generator.py`） | 随被测包一并归档 | 两个用例断言的是生成器自身行为，非活行为覆盖。**非覆盖度损失** |
| `2026-09-18-p81-archived-generator/empty-dir-*` 与 `pycache-snapshots/` | 空目录会被 Python 3 当作命名空间包 | 移走文件后 `import gacha_simulator.generator` 仍会成功（返回 `_NamespacePath`），故连空目录与残留 `__pycache__` 一并移入（`rmdir` 被 H2 门控拦下，改用 `mv`）。**仅本地存在、未纳入 git**：空目录无法被 git 跟踪，`.pyc` 属构建产物 |

**连带清理五处**：`GachaStat.spec` 的两行 hiddenimports ＋ `docs/01-活跃/subsystems/应用打包/02-实施.md` 的同一清单副本 ＋ `docs/01-活跃/subsystems/测试体系/02-实施.md` 的测试树。**其中两处注释的依据经核查不成立**（spec 称「动态/惰性导入」、文档副本称「GUI 可能通过配置面板引用」，实际全库零引用），已一并移除。

## P81 §12.5.1 `to_html` 删除（2026-09-18）

| 文件 | 归档原因 | 说明 |
|------|---------|------|
| （无整文件归档） | — | **代码内删除**：`gacha_simulator/visualization/plotly_charts.py` 删 `to_html`（24 行）与它独占的 `_HTML_TEMPLATE`（125 行），`tests/visualization/test_plotly_charts.py` 删 `TestToHtml`（3 用例）。**注意 `PlotlyRenderer` 本身未动**：`to_figure` 被 `gui/chart_webview.py:306/328` 调用、`_build_*` 经 f-string `getattr` 派发，均为活代码。`to_html` 的能力（把图表导成独立 HTML）在项目里已有两个更好做法：活的 WebView 路径，以及 `scripts/benchmark_chart.py` 用的 plotly 自带 `to_html`；且 P74 实施清单已写明「PlotlyRenderer 退役，ChartSpec IR 保留」 |
