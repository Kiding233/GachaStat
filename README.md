# GachaStat

> 灵活的抽卡概率模拟与统计决策分析系统

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-41CD52?logo=qt)](https://www.riverbankcomputing.com/software/pyqt/)
[![Tests](https://img.shields.io/badge/Tests-770_passed-success)](./tests/)
[![Version](https://img.shields.io/badge/Version-2.3.0-blue)](./gacha_simulator/_version.py)
[![License](https://img.shields.io/badge/License-GPLv3-blue)](./LICENSE)

**GachaStat** 是一款面向游戏抽卡机制的概率模拟与统计分析工具。旨在通过蒙特卡洛模拟对抽取概率、卡池机制、广义出率指标（GDR）及策略选择进行精确建模，帮助玩家与策划人员在不确定条件下做出基于数据的决策。

---

## 目录

- [核心功能](#核心功能)
- [安装](#安装)
- [快速上手](#快速上手)
- [架构概览](#架构概览)
- [功能详解](#功能详解)
  - [概率引擎](#概率引擎)
  - [策略系统](#策略系统)
  - [分析面板](#分析面板)
  - [CLI 工具](#cli-工具)
- [配置系统](#配置系统)
- [开发](#开发)
- [项目结构](#项目结构)
- [版本历史](#版本历史)
- [许可](#许可)

---

## 核心功能

| 功能 | 说明 |
|------|------|
| **概率模拟** | 多池子、多稀有度、保底（软/硬/轮换/捕获明光/定轨）全参数可配置 |
| **批量仿真** | 多进程并行 Monte Carlo 仿真，支持自定义策略与停止条件 |
| **广义出率 (GDR)** | 21 种 GDR 指标：目标达成率、资源效率、加权满意度、可达过滤等 |
| **过程分析** | 逐抽事件推断（7 种事件类型）、交叉统计（AA/BB/AB/BA）、事件模式 |
| **Bootstrap 分析** | BCa 置信区间、GPD 尾部估计、Hill 估计器、稳定性评估 |
| **流式分析** | 边模拟边提取边丢弃，O(1) 内存，10 万次仿真热力图仅 ~128 KB |
| **脆弱性分析** | PAVA 保序回归、Bootstrap 变更点 CI、决策风险量化 |
| **方案搜索** | Pareto 前沿、退路搜索、资源-目标联立优化 |
| **比较分析** | L1-L4 递进分析（统计摘要 → 分布比较 → 随机占优 → Bootstrap） |
| **GUI 界面** | PyQt6 原生桌面应用，10 个分析面板，Plotly 交互图表 |

---

## 安装

```bash
# 克隆仓库
git clone <repo-url>
cd gacha_simulator

# CLI / 无头模式安装
pip install -e ".[dev]"

# GUI 模式安装（含 PyQt6）
pip install -e ".[gui,dev]"
```

**依赖项：** Python 3.10+ · PyQt6 · numpy · scipy · matplotlib · Plotly (WebEngine) · binsreg · PySDTest（L2 随机占优，可选）

---

## 快速上手

### GUI 启动

```bash
python -m gacha_simulator.main
```

启动后通过「配置」面板设置卡池参数与保底规则，在「批量模拟」面板执行仿真，切换至各分析面板查看结果。

### CLI 批量仿真

```bash
python -m gacha_simulator.cli -n 1000 -w 4 -s 42
```

| 参数 | 说明 |
|------|------|
| `-c, --config` | TOML 配置文件路径（默认使用内置 config.toml） |
| `-n, --num-simulations` | 模拟次数（默认 1000） |
| `-w, --workers` | 并行进程数（默认 4） |
| `-s, --seed` | 随机种子（默认 42） |
| `-o, --output` | 结果输出文件（JSON） |
| `--strategy` | 策略选择：`smart` / `pool_quota` / `pity_reserve` / `target_hunting` / `stop_on_target` / `fixed_count` / `draw_target` |
| `--strategy-params` | 策略参数（JSON 字符串） |
| `--output-format` | 输出格式：`simple` / `full` |
| `--migrate` | 迁移旧格式 TOML 至新格式 |
| `--version` | 显示版本号 |

---

## 架构概览

```
gacha_simulator/
├── core/           # 引擎层（无 GUI 依赖）
│   ├── pool.py          — 卡池定义与抽卡逻辑
│   ├── pity.py          — 保底系统（10 种行为类型）
│   ├── state.py         — 模拟状态（资源/持有/时间）
│   ├── strategy.py      — 策略注册表（7 种策略）
│   ├── stop_condition.py— 停止条件（6 种）
│   ├── gdr.py           — 广义出率注册表（21 种指标）
│   ├── streaming.py     — 流式分析（O(1) 内存）
│   ├── bootstrap.py     — Bootstrap 稳定性引擎
│   ├── vulnerability.py — 脆弱性分析（PAVA 保序回归）
│   ├── process_trace.py — 过程追踪与事件推断
│   ├── comparison_analyzer.py — 比较分析（随机占优）
│   ├── config_store.py  — 配置数据模型
│   └── config_toml.py   — TOML 读写
├── service/        # 服务层
│   ├── gacha_service.py    — 单次模拟调度
│   └── batch_simulator.py  — 并行批量模拟入口
├── gui/            # GUI 层（PyQt6，10 个面板）
│   ├── config_panel.py         — 配置编辑
│   ├── gacha_panel.py          — 批量模拟
│   ├── data_manager_panel.py   — 数据管理
│   ├── analysis_panel.py       — 统计分析
│   ├── process_analysis_panel.py — 过程分析
│   ├── plan_search_panel.py    — 方案搜索
│   ├── retreat_panel.py        — 脆弱性分析
│   ├── worst_impact_panel.py   — 最差影响
│   ├── comparison_analysis_panel.py — 比较分析
│   └── wheel_blocker.py        — 全局滚轮拦截
├── config/         # 默认配置（TOML）
├── visualization/  # matplotlib 中文字体
├── tests/          # 测试（pytest + cov）
└── resources/      # 图标等静态资源
```

**核心数据流：**

```
ConfigStore → SimulationEnvBuilder → SimulationEnv
    → GachaService(pools, strategy, stop_cond)
    → run_simulation(CompactCollector) → CompactResult
    → SharedResultCollector
```

`CompactResult` 为 O(1) 内存的结果格式，支持 JSON 序列化（`to_dict`/`from_dict`）。所有批量模拟必须通过 `service/batch_simulator.py` 的 `run_batch_parallel()` 执行。

---

## 功能详解

### 概率引擎

**保底系统 (`core/pity.py`)** 支持 10 种保底行为类型：

| 类型 | 驱动方式 | 说明 |
|------|---------|------|
| `soft_step` | Counter | RLE deltas 驱动软保底 |
| `soft_interval` | Counter | 区间语法糖（自动展开为 deltas） |
| `soft_additive` | Counter | 叠加语法糖 |
| `hard` | Counter | 阈值触发 100% 保底 |
| `rotating` | Event | 纯净大小保底（guaranteed flag 二态翻转） |
| `rotating_soft` | Event | 轮换保底 + 软保底混入 |
| `rotating_cr` | Event | 捕获明光（cr_counter + cr_state_probs） |
| `rotating_cr_soft` | Event | 捕获明光 + 软保底 |
| `targeted` | Event | 定轨（selected_card + fate_points） |
| `targeted_soft` | Event | 定轨 + 软保底 |

### 策略系统

`STRATEGY_REGISTRY` 注册 7 种抽卡策略，统一接口 `select_action(ctx) → Action`：

| 策略 | 说明 |
|------|------|
| `smart` | 智能策略——综合目标卡价值、池子效率与资源约束 |
| `pool_quota` | 池子配额——每个池子分配抽数上限 |
| `pity_reserve` | 保底预留——为未开放保底池预留资源 |
| `stop_on_target` | 达成即停——获取目标卡后停止 |
| `target_hunting` | 目标狩猎——专注单一目标卡 |
| `fixed_count` | 固定抽数——均匀分配预算 |
| `draw_target` | 指定目标——按 desire 权重排序抽卡 |

策略支持非抽卡动作（`NonDrawAction`）：切换定轨目标（`switch_epitomized_target`）与取消定轨路径（`cancel_epitomized_path`）。

### 分析面板

| 面板 | 分析方法 |
|------|---------|
| **统计分析** | GDR 汇总、经验分布、直方图、风险分析、成功率 Wilson CI |
| **过程分析** | 每池 7 种事件推断、4 种交叉统计（AA/BB/AB/BA）、5 种事件组合模式 |
| **方案搜索** | 退路搜索、资源目标搜索、Pareto 前沿（三合一面板） |
| **脆弱性分析** | PAVA 保序回归 + Bootstrap 变更点 CI + 三行子图 |
| **最差影响** | 虚拟池匹配（fnmatch）、反事实路径、CVaR 风险度量 |
| **比较分析** | L1-L4 递进（统计摘要 → 分布比较 → SD 随机占优 → Bootstrap） |
| **数据管理** | 数据集保存/加载/比较/导出（ComparabilityFingerprint 相容性校验） |
| **敏感度分析** | 单参数变化 + GDR 折线图（开发中） |

### CLI 工具

除仿真外，CLI 还支持：

```bash
# 迁移旧格式配置
python -m gacha_simulator.cli --migrate

# 完整输出（含 extraction 数据）
python -m gacha_simulator.cli -n 500 --output-format full -o full_results.json
```

---

## 配置系统

配置文件为单一 TOML 文件（`config.toml`），包含以下段：

| 段 | 说明 |
|---|------|
| `[simulation]` | 全局仿真参数（初始资源、起始时间、随机种子） |
| `[[pool]]` | 卡池定义（名称、稀有度概率、开放时间、批次大小） |
| `[[card]]` | 卡牌定义（名称、稀有度、权重、标签） |
| `[[pity]]` | 保底规则（类型、作用域、阈值、delta 序列） |
| `[strategy]` | 策略参数（目标卡、权重、desire weights） |
| `[resources]` | 资源定义 |
| `[gains]` | 资源日历（每日/每周固定收入） |
| `[weights]` | 卡片价值权重（稀有度权重、卡片价值、资源价值） |

---

## 开发

```bash
# 运行测试套件
pytest --cov=gacha_simulator

# 代码风格检查
ruff check

# 单模块测试
pytest tests/test_pity.py -v
```

**测试规模：** 770 项测试通过，1 项跳过。

### 扩展指南

| 扩展目标 | 入口 |
|---------|------|
| 新 GDR 指标 | `core/gdr.py` → `UNIFIED_GDR_REGISTRY` 注册 `GDRDefinition` |
| 新策略 | `core/strategy.py` → `STRATEGY_REGISTRY` 注册 |
| 新停止条件 | `core/stop_condition.py` → `STOP_CONDITION_REGISTRY` 注册 |
| 新保底行为 | `core/pity.py` → `BEHAVIOR_REGISTRY` 注册 + 实现 `CounterBasedBehavior` 或 `PityBehavior` 子类 |
| 新 GUI 面板 | `gui/` 目录 → `MainWindow._setup_ui()` 注册 Tab |
| 新卡片维度 | `CardDefEntry.tags`（单值）/ `CardDefEntry.list_tags`（多值）——TOML 中 `[card.tags]` 加一行即可 |
| 新配置项 | `ConfigStore` → `config_toml.py` → `config_panel.py` → `SimulationEnvBuilder` |
| 新脆弱性方法 | `core/vulnerability.py` 新增私有函数，通过 `_fit_vulnerability_pava` 集成 |
| 新随机占优检验 | `core/comparison_analyzer.py` → `compute_dominance_matrix()` 派发器 |

---

## 项目结构

```
抽卡模拟与分析程序/
├── gacha_simulator/
│   ├── _version.py          # 版本号（Pride Versioning: MAJOR=PROUD/MINOR=DEFAULT/PATCH=SHAME）
│   ├── paths.py             # 路径工具（开发/打包环境自适应）
│   ├── main.py              # GUI 入口
│   ├── cli.py               # CLI 入口
│   ├── core/                # 引擎层（34 个模块）
│   ├── service/             # 服务层
│   ├── gui/                 # GUI 层（18 个模块）
│   ├── config/              # 默认配置文件
│   ├── visualization/       # matplotlib 字体
│   └── resources/           # 静态资源
├── tests/                   # 测试套件
├── docs/                    # 文档体系
│   ├── 00-meta/             # 全局约定、术语表、验收清单
│   ├── 01-活跃/             # 活跃计划文档（面板/子系统级别）
│   ├── 02-待办/             # 待办事项
│   └── 03-归档/             # 已完成的计划与面板文档
├── pyproject.toml           # 项目元数据与依赖
└── README.md
```

---

## 版本历史

采用 **Pride Versioning**（`PROUD.DEFAULT.SHAME`）：

| 版本 | 日期 | 里程碑 |
|------|------|--------|
| **2.3.0** | 2026-07-20 | P65 卡片标签系统——CardDefEntry tags/list_tags + TOML 段名单数化 |
| **2.2.0** | 2026-06-14 | P44 池子批次抽卡（十连强制）——Pool/PoolConfig/PoolEntry 三级 batch_size |
| **2.1.0** | 2026-06-12 | P37 资源日历增强 + Harness 基础设施完善 + 全仓库 lint |
| **2.0.0** | 2026-06-09 | 预发布版——面板合并、数据管理层、比较分析、应用打包、文档重构 |
| **1.10.0** | 2026-05-26 | 文档体系重构、优先级路线图、Bootstrap 计划合并 |
| 1.9.x 系列 | 2026-05-20~26 | Bootstrap 引擎、GDR 扩展、策略重构、过程分析、流式分析 |
| 1.0.0 | 2026-05-07 | 初始版本——核心模拟引擎、GUI、配置系统 |

完整版本历史见 `gacha_simulator/_version.py` 中的 `VERSION_HISTORY`。

---

## 许可

本项目以 [GNU General Public License v3.0](./LICENSE) 发布。

> **说明：** 项目依赖中包含 GPLv3 许可的组件（PyQt6、binsreg），在 PyInstaller 打包分发时构成组合分发，整体受 GPLv3 约束。详见 [LICENSE](./LICENSE) 文件。
