<!-- META: Ps01 | module:模拟服务层 | status:待办 | last:2026-08-02 -->

# Ps01 运行时真实缺陷修复：future_resource_gains 崩溃与脆弱性保底快照

> 日期：2026-08-02 | 状态：待办
> 触发：兼容性痕迹扫描（子 agent）发现两处「因旧结构假设导致但从不在测试路径暴露」的运行时真实缺陷，与「无历史包袱原则」清理方向一致
> 性质：小清理计划（两个独立缺陷，各可独立提交）

## 一、问题

### 缺陷 1：`future_resource_gains` 崩溃（P69 引入，带排期配置必现）

- **位置**：`core/strategy_context_builder.py:69-77` 遍历 `schedule_mgr.get_future_schedules()` 返回的条目，访问 `entry.day` / `entry.gains`
- **结构错位**：`core/schedule.py:6-16` 的 `PoolSchedule` 只有 `pool_id / available_from / available_until / rerun_of`，无 `day` / `gains` 属性 → AttributeError
- **根源**：P69 作者把「资源日程」（`resource_gain.py` 的 `ScheduleResourceGain.schedule = {day: {resource_id: amount}}`）与「池子排期」（`PoolSchedule`）两个概念混淆。P30/P69 计划声称「从 schedule_mgr 计算未来每日资源收入，已有全部数据，仅需聚合」，但 `schedule_mgr` 只管理池子开放窗口、不含任何资源信息
- **影响**：带排期（schedule）配置的批量模拟（CLI/GUI 主路径）每轮 `build_strategy_context` 必抛 AttributeError，被 `batch_simulator.py:250-253` 的 `except Exception` 吞掉记入 `n_failed`。现象是「模拟有失败样本」而非崩溃，容易被当统计噪声
- **无测试覆盖**：P69 计划写了 SC-01/SC-02 行为用例但未落地，tests 全库对 `future_resource_gains` 零引用

### 缺陷 2：`vulnerability.py` 保底快照永远为空

- **位置**：`core/vulnerability.py:754` 直接 `pes[pool_id].get('counters', {})` 按旧格式读保底状态；真实数据 `pool_end_pity_states` 是 `{'data': ...}`（`PityState.to_dict()` 新格式）
- **不一致**：同文件 `vulnerability.py:612` 用 `PityState.from_dict(pes[pool_id])`（正确新格式路径），两处读取方式冲突
- **影响**：主分析路径的保底快照在真实运行中永远收集不到数据（`get('counters', {})` 恒返回空 dict）
- **测试空洞**：`tests/core/test_vulnerability.py:216` 用旧格式 `'counters'` mock，让测试「空洞通过」，掩盖了真实缺陷

## 二、目标

1. 消除缺陷 1 的崩溃：`future_resource_gains` 从错误的 `PoolScheduleManager` 数据源改为复用抽卡资源增量同一函数 `resource_gain.compute()`
2. 修复缺陷 2 的数据读取：`vulnerability.py` 保底快照按 `PityState.from_dict` 新格式读取，真实数据非空
3. 补齐缺失测试（P69 SC-01/SC-02 落地 + 两个回归），防止回归

## 三、方案

### 3.1 缺陷 1：`future_resource_gains` 复用 `resource_gain.compute()`

**为何复用**：抽卡/等待时资源增量走 `GachaService._resource_gain.compute(elapsed_time, state)`（`gacha_service.py:377`）。`future_resource_gains` 的语义「未来 lookahead 天的资源收入」恰等于 `compute(lookahead * DAY, state)`。`compute()` 内部按 `state.real_time` 跨天查日程，天然处理天数/秒的单位换算，且与抽卡资源增量同一数据源（单一真相源）。

**方案比较（2026-08-02 定稿）**：候选三案逐一比较后选定 A——

- **A 复用 compute**（选定）：`future_resource_gains = resource_gain.compute(lookahead * DAY, state)`。对 5 种 `ResourceGainFunction` 全通用（schedule 查日程、linear/periodic/step 算增量、Composite 自动组合）；单一真相源（与模拟结算同一函数，配置改动自动生效）；compute 内部 `real_time // DAY` 自动处理天数/秒换算，顺带修掉原逻辑 `entry.day` 与 `real_time` 直接比较的单位错乱。
- **B 暴露日程字典 `{day: {resource_id: amount}}` 按 day 聚合**（否决）：**只覆盖 Schedule 型**。真实 `resource_gain` 是 `CompositeResourceGain`（batch_simulator.py:782，schedule + linear 混合），linear 等类型的未来资源会被漏算，结果不完整；且需 `SimulationEnv` 新增字段、传递链变长（约 50 行）。
- **C 新增前瞻专用方法 `future_gains(lookahead, state)`**（否决）：每个实现（5 类）各写一份，本质是 compute 换皮重复，成本高收益低。

**纯函数前提澄清**：compute 的契约是「给定 elapsed_time 和 state 返回该跨度的资源增量」，正确实现必然只依赖 `elapsed_time`/`state`/构造配置（否则模拟结算本身出错）。故复用做前瞻查询依赖的「compute 正确」是合理假设，非脆弱依赖。**当天边界**：schedule 从 `current_day+1` 起（排除当天）与 linear 含当天起算，是各类型固有语义差异，非复用引入，且与 P69 SC-01（聚合未到达未来资源）一致。

**改动**：

| 文件 | 改动 |
|------|------|
| `core/strategy_context_builder.py` | `build_strategy_context` 新增 `resource_gain: Optional[ResourceGainFunction] = None` 参数；删除 L69-77 的 `entry.day`/`entry.gains` 聚合块；改为 `if resource_gain is not None and lookahead: future_resource_gains = resource_gain.compute(lookahead * DAY, state) or {}` |
| `service/gacha_service.py` | `build_strategy_context` 调用处补传 `resource_gain=_resource_gain`（`_resource_gain` 已有，L204） |
| `core/strategy.py` | `future_resource_gains: Dict[str, float]` 字段与类型不变，无需改 |

`schedule_mgr` 参数**保留**（`future_schedules` 字段仍依赖它，L66-67）。

### 3.2 缺陷 2：`vulnerability.py` 保底快照改 from_dict

**改动**：

| 文件 | 改动 |
|------|------|
| `core/vulnerability.py:754` | `pes[pool_id].get('counters', {})` 改为与 L612 一致的 `PityState.from_dict(pes[pool_id])` 后读取（`ps.get('counter', 0)` 或等价访问） |
| `tests/core/test_vulnerability.py:216` | mock 从旧格式 `'counters'` 改为新格式 `'data'`（`PityState.to_dict()` 产出格式） |
| `core/pity.py:1149-1152` | `PityState.from_dict` 的 `'counters'` 旧格式升级分支：本轮**保留**（防御读取，成本极低）；待确认全库无旧格式生产者后随死代码清理移除 |

## 四、实施阶段

| 阶段 | 内容 | 文件 | 预估 |
|------|------|------|------|
| R1 | `future_resource_gains` 修复：builder 换数据源 + gacha_service 传参 + SC-01/SC-02 用例落地 + 带 schedule 批量模拟不崩溃回归 | `strategy_context_builder.py` / `gacha_service.py` / `tests/core/test_p69_strategy.py` 或新建测试 | ~45行 |
| R2 | `vulnerability` 保底快照修复：L754 改 from_dict + 测试 mock 改新格式 + 回归 | `vulnerability.py` / `test_vulnerability.py` | ~10行 |

两阶段各自独立可运行、独立 commit。R1 与 R2 互不依赖。

## 五、验收标准

- [ ] 带 schedule 配置的批量模拟 `n_failed = 0`（不再抛 AttributeError）
- [ ] `build_strategy_context` 的 `future_resource_gains` 正确聚合：lookahead 内未到达的日程资源计入、已到达不计（P69 SC-01/SC-02 用例，含天数/秒单位换算正确）
- [ ] 不传 `resource_gain` / `lookahead` 时 `future_resource_gains` 为空 dict 而非 None（策略 `ctx.future_resource_gains.get('gem', 0.0)` 正常工作）
- [ ] `vulnerability` 逐池保底快照从真实数据非空（`PityState.from_dict` 路径）
- [ ] `test_vulnerability.py` mock 已改新格式 `'data'`，旧格式 `'counters'` 不再被测试使用
- [ ] `pytest -q` 全量通过

## 六、备注

- 缺陷 1 非「兼容旧格式」，而是「概念错位 + 假功能」：`future_resource_gains` 字段从 P69 起从未真正工作过（带 schedule 时模拟失败、不带时恒为空）。修复方案经三类方案比较确定为「复用 compute」（见 §3.1），使其真正可用，为未来资源目标搜索策略（P26 方向）铺路
- 后续清理候选（不在本计划范围）：pity.py 旧签名/旧路径死兼容约 130 行、GDR 旧子系统 4 文件、三个废弃 GUI 面板等（见兼容性痕迹扫描结果，可另立计划）
