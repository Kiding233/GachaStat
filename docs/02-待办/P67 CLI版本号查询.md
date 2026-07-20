<!-- META: P67 | module:模拟服务层 | status:planning | last:2026-07-20 -->

# P67 CLI 版本号查询

> 日期：2026-07-20 | 状态：规划中
> 触发：`python -m gacha_simulator.cli --version` 当前报 `unrecognized arguments`

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
