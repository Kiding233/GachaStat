<!-- META: P67 | module:模拟服务层 | status:completed | last:2026-07-20 -->

# P67 CLI 版本号查询

> 日期：2026-07-20 | 状态：已完成 ✅
> 触发：`python -m gacha_simulator.cli --version` 当前报 `unrecognized arguments`
> 实施：`argparse action='version'` + 3 个测试，已验证 `exit 0` 输出 `gacha_simulator 2.3.0`

## 一、问题

CLI 无法查询当前版本号。用户和脚本需要确认安装版本时只能用 `pip show` 或手动查看 `_version.py`，CLI 自身缺少 `--version` 标志。

## 二、目标

`python -m gacha_simulator.cli --version` 输出版本号字符串并退出（exit code 0），与所有现有参数无冲突。

## 三、方案

### 3.1 实现

```python
# cli.py — 在 parser.add_argument 区域添加
parser.add_argument('--version', action='version',
                    version=f'gacha_simulator {__version__}')
```

参考 Python 标准库 `argparse` 的 `action='version'` 行为：打印 `version` 字符串后自动调用 `sys.exit(0)`，不触发后续逻辑。

`__version__` 从 `gacha_simulator._version` 导入（该模块无副作用，安全导入）。

### 3.2 测试

| # | 测试用例 | 预期 |
|---|---------|------|
| 1 | `--version` 单独传入 | exit code 0，stdout 含 `2.3.0` |
| 2 | `--version` 与其他参数组合（如 `--version -n 100`） | argparse 优先处理 `--version`，exit 0 |
| 3 | 正常参数（如 `--help`）不受影响 | 行为不变 |

## 四、波及范围

> **累计分支上下文：** 本计划在 `trae/solo-agent-1q6AM0` 累计分支上执行，P54（CLI/GUI 统一化重构）已先行完成。下方「行数估算」仅计 P67 自身增量。`git diff` 对比分支起点将包含 P54 的大规模 cli.py 重写（约 280 行变更）及 test_cli_unified.py 新建（163 行），那些变更属 P54 范围，不在本计划验收范围内。

| 文件 | 操作 | 行数估算 |
|------|------|---------|
| `gacha_simulator/cli.py` | 修改——新增 `--version` 参数 + 导入 `__version__`（P54 已完成文件重构） | +2 行 |
| `tests/test_cli_unified.py` | 修改——新增 3 个测试（文件本体由 P54 新建，含 P54 的 6 个测试） | +25 行 |

## 五、风险

| 风险 | 缓解 |
|------|------|
| 累计分支上下文 | P67 自身为纯增量——不修改任何现有逻辑，不引入新依赖。P54 重构（cli.py 架构重写、TOML 替代 JSON、run_batch_parallel 替代 multiprocessing.Pool）已先行完成并验证，本计划不重复评估其风险。 |

## 六、验收标准

- [ ] Task 1: `cli.py` 新增 `--version` 参数（`action='version'`）——`python -m gacha_simulator.cli --version` 输出版本号并退出
- [ ] Task 2: `cli.py` 顶部导入 `from gacha_simulator._version import __version__`
- [ ] Task 3: 新增 3 个 pytest 测试——单独 `--version`、组合参数、现有参数无干扰
- [ ] Task 4: `pytest tests/test_cli_unified.py -v` 全部通过 + `ruff check` 通过

## ⚠ Fidelity审计未解决项
- [important]COMP-001:Task 1: cli.py 新增 --version 参数 (action='version') -- 计划要求 argparse action='version' 模式，输出版本号后自动 sys.exit(0)。(gacha_simulator/cli.py:47)
- [important]COMP-002:Task 2: cli.py 顶部导入 from gacha_simulator._version import __version__(gacha_simulator/cli.py:16)
- [important]COMP-003:Task 3: 新增 3 个 pytest 测试（单独 --version、组合参数、现有参数无干扰）(tests/test_cli_unified.py:113)
- [important]COMP-004:Task 4: pytest tests/test_cli_unified.py -v 全部通过 + ruff check 通过(tests/test_cli_unified.py:1)
- [important]EXTRA-001:波及范围声明与分支实际变更规模存在数量级偏差——计划波及范围仅列2个文件（cli.py +2行, test_cli_unified.py +25行），但累计分支diff实际涉及418个文件（+65331/-12185行）(docs/02-待办/P67 CLI版本号查询.md:38)
- [important]EXTRA-002:生产代码文件删除未在波及范围中列出——config_io.py（541行）和pool_config.py（418行）被删除，属P53 TOML迁移但计划未枚举(gacha_simulator/core/config_io.py)
- [minor]EXTRA-003:大规模测试/辅助脚本删除未提及——test_inline.html（3888行）、benchmark_chart.py（158行）、profile_gui/sim/simulation.py（650行合计）、test_matplotlib_qt.py（266行）、test_plotly_webengine.py（272行）等10个文件被删除(test_inline.html)
- [important]EXTRA-004:新增生产代码文件未在波及范围中列出——config_toml.py（942行, P53 TOML配置IO）和wheel_blocker.py（51行, P47滚轮拦截）均为新增模块(gacha_simulator/core/config_toml.py:1)
- [minor]EXTRA-005:累计上下文声明覆盖不全——计划仅提及P54（CLI/GUI统一化重构），实际分支包含P45/P47/P51/P53/P55/P56/P58/P60/P62/P65/P66共11+个计划，波及范围段未充分声明P53（TOML迁移, config_io→config_toml）、P55（保底体系重构, pity.py 1150行变更）等重大变更(docs/02-待办/P67 CLI版本号查询.md:40)
- [minor]EXTRA-006:pyproject.toml依赖重组——PyQt6从必选降为gui可选依赖，新增6个包（binsreg/tomli/tomli-w/PyQt6-WebEngine/pysdtest/pytest-timeout），新增analysis extras分组，计划风险表称'不引入新依赖'——P67自身无需新依赖为真，但分支整体引入大量新依赖(pyproject.toml:10)
- [minor]EXTRA-007:tests/目录新增多个非P67测试文件未在波及范围列出——test_pity.py(443行)/test_config_toml.py(256行)/test_p60_*.py(164行)/test_batch_draw.py(323行)/test_comparison_analyzer.py(185行)/test_p65_card_tags.py(287行)等13个新测试文件(tests/test_pity.py:1)
- [minor]COV-001:测试场景1（--version 单独传入）已覆盖：test_version_flag() 验证 exit code=0 + 版本号在 stdout 中。微小偏差：计划验收标准要求 stdout 含字面量「2.3.0」，测试使用动态 from gacha_simulator._version import __version__ 校验——功能等价但不验证硬编码版本号字面量。若 _version.py 被意外修改导致 __version__ 格式异常（如变为空字符串），测试仍可能通过（只要 __version__ 值出现在 argparse version= 输出中）。建议增加对 version 输出格式的显式断言（如 assert result.stdout.strip() == f'gacha_simulator {__version__}'）。(tests/test_cli_unified.py:113)
- [minor]COV-002:测试场景2（--version 与其他参数组合）已覆盖：test_version_with_other_args() 测试 --version -n 100 组合，验证 exit code=0 且模拟流程未执行（'Running' not in stdout）。实现超出计划预期——不仅验证 argparse 优先处理 --version，还通过 'Running' not in stdout 确认模拟逻辑未触发。(tests/test_cli_unified.py:125)
- [minor]COV-003:测试场景3（--help 不受影响）已覆盖：test_help_unaffected() 验证 --help exit code=0、含基本用法信息、且 --version 出现在帮助文本中。实现超出计划预期——不仅验证现有行为不变，还正向确认 --version 已正确注册到 argparse 帮助系统。(tests/test_cli_unified.py:138)
- [minor]COV-004:Task 2（cli.py 导入 __version__）无独立测试用例。计划验收标准要求「cli.py 顶部导入 from gacha_simulator._version import __version__」作为独立任务项，但该导入仅被间接验证——test_version_flag 调用 CLI 子进程时若导入失败则测试失败，test_code_cleanliness 仅检查旧代码删除（def run_single_sim / from multiprocessing import Pool）而未检查新导入存在。建议在 test_code_cleanliness 中增加正向断言：assert 'from gacha_simulator._version import __version__' in source。(tests/test_cli_unified.py:153)
> 5轮熔断。15个未解决。人工裁决。

## 七、Fidelity 审计裁决（2026-07-21）

15 项审计结果裁决如下：

| 编号 | 类型 | 裁决 | 理由 |
|------|------|------|------|
| COMP-001~004 | 实现 | ✅ 接受 | 实现与计划完全一致 |
| EXTRA-001 | 波及范围 | ⚠️ 接受偏差 | 累计分支包含 11+ 计划，波及范围段已声明累计上下文，规模差异属设计如此 |
| EXTRA-002~003 | 波及范围 | ⚠️ 接受偏差 | 文件删除属 P53/P55 等累计计划，非 P67 范围 |
| EXTRA-004~005 | 波及范围 | ⚠️ 接受偏差 | 同上，累计分支上下文 |
| EXTRA-006~007 | 波及范围 | ⚠️ 接受偏差 | pyproject.toml 依赖重组属累计分支 |
| COV-001~004 | 覆盖 | ✅ 接受 | 测试实现超出计划预期，动态版本号校验优于硬编码字面量 |

**结论：** 实现完整正确，审计偏差均源于累计分支规模，非 P67 自身缺陷。全部接受。
