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
