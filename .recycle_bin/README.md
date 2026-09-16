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
