# peer-review — P63 溢出卡资源转换计划

> 审查日期：2026-07-28 | 流水线：plan-review 五阶段对抗验证
> 计划文件：`subsystems/模拟服务层/P63 溢出卡资源转换——收敛到state.add_card()的统一溢出管道.md`
> 结论：✅ 通过（R2-fixed），建议实施

---

## 流水线执行

| 阶段 | 结果 | 产出 |
|------|:---:|------|
| 0 分类 | ✅ | complex / evolutionary / 5 维度 / 10 预估缺陷 |
| 1 影响面扇出 | ✅ | 5 agent 并行（核心引擎·配置解析·模拟服务层·GUI·测试），21 条发现 |
| 2 对抗循环 | ✅ | 6 轮 Find→Fix→Verify，25 个 ISSUE 全部 PASS（收敛） |
| 3 可行性门控 | ✅ | 3 PASS / 1 NEEDS_SPLIT (E6/E7a) / 2 NEEDS_CLARIFY (回滚路径·测试策略) |
| 4 代码审计 | ✅ | 3 个 GATE 问题修复：E6/E7a 拆分为 15 子阶段 + §7.A 回滚策略 + 35 个测试用例 |
| 5 矩阵同步 | ✅ | 手动完成（agent 僵死后恢复） |

## 发现分类

### 虚构符号名（2 项）
- `_build_store()` → `_build_card_overflow_map(store)`——`config_toml.py` 中无此函数，正确插入点为 `load_toml()` 内 `_backfill_card_pools()` 之后
- `SimulationEnvBuilder.build()` → `SimulationEnvBuilder.from_config_store()`——实际静态方法名

### 遗漏波及范围（6 项）
- `config_panel.py` 两处 `PoolDistEntry()` 构造传入三 bonus 字段——E6 移除后 `TypeError`
- `DistributionDialog`「额外资源」列（第 5 列）+ `_bonus_to_text`/`_parse_bonus_text`——E6 后死代码
- `test_p60_gacha_state.py::test_add_card_increments`——断言 `add_card() == 1`（int），新签名返回 `dict`
- `SimulationEnv` / `SimulationEnvBuilder` / `_run_single`——`card_overflow_map` 四环节数据流链路缺失
- `save_toml()` 卡片序列化不写 `overflow_bands`——手写配置静默丢弃
- `CLAUDE.md`——新增模块 + API 变更未登记

### 边界覆盖（5 项）
- `ConfigStore.clear()` 未覆盖 `rarity_defaults` / `card_overflow_map`——跨 `load_toml` 调用残留旧值
- `GachaState.clone()` 未拷贝 `acquired_by_path`——策略分支评估时路径记录丢失
- `SimulationEnvBuilder.from_dict()` 不含 `card_overflow_map`——`worst_impact.py` 场景溢出静默不生效
- 稀有度键名大小写——`rarity_defaults` 用 `.lower()` 存储但 `rarity_rank` 用 `.upper()`，跨映射查找方向错误
- `add_card()` 用 `assert` 校验 `initial_counts`——Python `-O` 剥离，改为 `ValueError` 显式检查

### 逻辑闭合（3 项）
- 验收标准 #17 依赖未完成的 P58——拆分为 P63 接口 + P58 联动两个子项
- E5/E6 分阶段提交——E5 后 `compute_bonus_resources` 导入未使用，ruff F401 阻断 commit
- `overflow_bands` 序列化格式策略未决定——默认 bands 数组，可选语法糖反向还原

### 文档错误（2 项）
- `.lower()` 与 `.upper()`「方向一致」→「方向互补」（用途不同：TOML 段查找 vs 展示排序）
- `collector.on_bonus()` 断言语气 → 设计意图语气（API 不存在，属未来预留）

### GATE 修复（3 项）
- **GATE-1 变更粒度**：E6→E6a/b/c/d 四个子阶段，E7a→E7a-1/2/3 三个子阶段，全部 ≤1h
- **GATE-5 回滚路径**：新增 §7.A——逐阶段独立 commit + 级联退避表 + 15 阶段回滚验证命令 + 3 种紧急恢复流程
- **GATE-6 测试策略**：验收标准重组为 A-F 六子类，新增 35 个具体输入→期望输出测试用例

## 计划质量

| 维度 | 评级 | 说明 |
|------|:---:|------|
| 根因深度 | ⭐⭐⭐⭐⭐ | 从症状（TOML 管道断裂）追溯到架构层修复（state.add_card() 统一溢出入口） |
| 逻辑闭合 | ⭐⭐⭐⭐☆ | 15 阶段·11 文件·560 行·28 风险·接口契约明确 |
| 波及准确性 | ⭐⭐⭐⭐☆ | 审查前遗漏 6 处，审查后全部补全 |
| 测试覆盖 | ⭐⭐⭐⭐⭐ | 35 用例覆盖边界/等价性/端到端/GUI 交互/回归 |
| 可回滚性 | ⭐⭐⭐⭐☆ | 审查中补全 §7.A——逐阶段 revert 验证表 + 紧急恢复流程 |

## 遗留问题

**无。** 全部 28 项 ISSUE 在对抗循环中修复并通过验证。

---

## E1 交叉验证

> 待 E1 下次运行时交叉验证本报告发现与 eval 发现的一致性。
