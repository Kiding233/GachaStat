<!-- META: P64 | module:保底系统 | status:designing | last:2026-09-27 | depends:P55,P56 -->

# P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构

> 日期：2026-08-24（2026-09-16 补三条强制约束 + §3.1.5 形式化 + target_featured 反例；**2026-09-18 事实同步**：全量行号刷新至 P81 清理后的代码 + GUI 两处事实修正 + legacy 迁移描述更新；**同日裁决 P82 并入的三项**：接线 / 保留 priority / 顺序两层定性，见 §1.5；**2026-09-21 概率操作乘法化 + 状态可见性裁决**：§3.1.5 重写为乘性因子版 + §3.1.2 D20 分布空间归属 + §3.9 S8 实施方案 + §3.10 状态可见性与 G3 真实建模 + S8/S9 子块；跨保底读状态裁决为不纳入；G15 按「精确建模原则」重估为缺口；**同日增补三项架构改进**：§3.11 表达能力与边界、§3.12 组合正确性验收、§3.13 不变式运行时校验 + S10/S11 子块；**§3.14 条件外置**（条件提为独立对象 + ConditionalModifier 包装器；三方案比较与 R/F 等价性实测）+ S12 子块；**2026-09-22 GATE 加里程碑划分**：M1（S1–S7 + S10 + S11，口径「与旧类逐场一致」）/ M2（S8 + S9 + S12，口径「与 M1 产物容差一致」），M1 结束为暂停与交付点，计划文件不拆分；**同日第四轮（Fixer）**：**S12 由 M2 前移进 M1**（排在 S2 之后、S3/S4 之前，ISSUE-101，里程碑边界与 M2 回滚单元同步调整）、三个 `_soft` 复合类型的 M4 差异登记与方向更正（ISSUE-102）、`PityContext.state` 类型注记与 `ctx.state` 读取纪律（ISSUE-103）、Tracker 契约表签名回写定稿形态（ISSUE-104）、`rotating_inverse` 的类型集合与排序键取值（ISSUE-105）） | 状态：设计中（2026-08-23 初版 → 2026-08-24 双层纯函数重建）；**2026-09-22 审查修复轮**：新增 §3.1.6 模块归属与依赖方向（叶子原语层 `pity_primitives.py`）、骨架补 `is_soft`/`is_hard` 推导与 view 重建与「退役先于 commit」、preset 统一为工厂函数 + registry `class` 置 None、跨进程 pickle 约束、配置透传链（`priority`/`reads`）、`worst_impact` 卡集合对齐、外部状态填充点改 `GachaService` 与 `owns` 含初始持有、归一性断言改 scope 感知、`scope` 键缺失边界、文档同步面（CLAUDE.md / 模块状态矩阵），逐处标记 `ISSUE-xxx`；**同日第二轮**：`§3.14.2` 示例改 `.get(scope, ())`（ISSUE-020/016）、`§3.9.2` 归一化论证前提修正（ISSUE-021）、`factor_redistribute` 签名统一为 4 参（ISSUE-022）、`_soft` 族双命名空间与 S1–S5 快照口径对齐（ISSUE-023）、三类型集合随叶子层升为模块级常量（ISSUE-024）、`core/__init__.py` 10 个旧行为类导出面（ISSUE-025）、`compute_scope_mappings` 的改造归属 `pity.py`（ISSUE-026）、`Banner.draw` 送达路径定稿（ISSUE-027）、子系统 01-理论/02-实施 与手册路径入文档同步面（ISSUE-028）；**同日第三轮（Fixer，2026-09-22）**：`pity_primitives.py` 行补记三个类型集合常量与 `PityContext.external`（ISSUE-024 / ISSUE-034）、Tracker / Modifier / Lifecycle 三族 `rebind` 接口显式定义 + `ConditionalModifier` 转发（ISSUE-029）、preset 工厂签名定稿为 `preset(pdef)` 并补取值来源表（ISSUE-030）、§3.2 / §3.3 正文同步条件外置形态与「组装时的条件」列（ISSUE-031）、`OnceActive` 声明为「无配置对应物、本期只实现类」（ISSUE-032）、`reads` 并集来源与 `get_reads_for_pool()` 访问器（ISSUE-033）；**同日第五轮（Fixer，2026-09-22）**：Lifecycle 协议补第五个方法 `initialize` 并同步 §3.1.4 骨架 / §四 行 / §3.13 不变式行 / §六 断言（`_active` 的构造期写入自此有归属，ISSUE-202）、§3.6 M3 的 `priority` 透传机制统一为构造形参 `Pity(..., priority=pdef.priority)`（ISSUE-203）、`worst_impact` 卡集合断言改为 `{r.id for r, _ in pool.rewards}`（`Pool.rewards` 元素是 `(Reward, prob)` 二元组，ISSUE-201）、`PityEngine.__init__` 构造期 `except Exception` 静默吞异常的处置定稿为抛 `ConfigError` 并补 §六 断言（ISSUE-204）；**同日第六轮（Fixer，2026-09-22）**：`deactivate_on_early_hit` / `depends_on` 到 Lifecycle 对象的构造来源全链补齐——§3.1.3 新增唯一转换点 `build_lifecycle(pdef)` 与旧路径逐行对照表、§3.2 取值来源表补 `lifecycle=` 行 + registry 校验与 `create_behavior` 的 `ConfigError` 防线 + 四份 preset 代码块补该键、§3.1.6 与 §四 四行登记、§五 风险行、§六 断言、§七 S1/S4 任务项；`LifecycleConfig` 去留定稿为「保留、角色改为 Lifecycle 构造参数袋」（ISSUE-301）；**同日第七轮（Fixer，2026-09-22）三 GATE 问题处置**：① `ISSUE-GATE-granularity` — §七 主线 12 步细分为 26 子块（S1a 至 S1d / S2a 至 S2b / S12 / S3 / S4-1 至 S4-5 / S4b / S5a 至 S5c / S6a 至 S6c / S7a 至 S7c / S10-1 至 S10-2 / S11），逐块补目标文件 + 人时预算 + 验收命令，进度合计由「~10 人时」修正为「约 16.4 人时」，并把「每块独立 commit」写入 GATE-1 与 GATE-5（回滚单元 = 任务单元）；② `ISSUE-GATE-file-list` — 五处行号与计数事实修正（`_EVENT_DRIVEN_TYPES` `:114-115`、`_build_activation_graph` `:1205-1229`、`ctx = PityContext(...)` `:1335`、测试文件 6 改 5、`pentry` 26 键改 24 键）并补齐 S3 / S5 / S10 / S11 四处缺失的目标文件（`core/invariants.py` 独立新模块登记 + 两个新测试文件行）；③ `ISSUE-GATE-dependency-order` — Modifier 方法名定稿为 `apply(ctx, view, dist, readonly)`（`factor` 自 S8 引入，§3.1.4 骨架据此）、`StateView` 由「S9 独占」改为「S3 落薄版 / S9 收紧」、`PityDef.reads` 字段与解析归 S9 而 `Pity.reads` 形参归 S3、`_soft` 族 view 命名空间分配定稿（软计数留 `X`、`X_soft` 只承 `_active`，§3.10.3）；**2026-09-22 第八轮（Fixer 定稿，GATE 五项）**：GATE-1 粒度（S1b / S3 / S12 各细分、M2 补逐子项预算与目标文件、S8-4 与 S8-5 分立）、GATE-3 依赖序（`priority` 字段定义前移至 S4b 且置于 S4-2 之前、`_pools` 由 S1a 改归 S3-1、registry `class` 置 `None` 后旧类改由 harness 直接 import 且回滚改 `git revert`）、GATE-4 风险（快照面取 ①统一写入、ISSUE-102 不加 hit 门控、ISSUE-032 维持只验类不接线，三项均已登记为 §五 风险行）、GATE-5 回滚（主线 29 块逐块回滚、M2 按子项回滚 + 依赖闭包规则）、GATE-6 测试（S11 补专属测试文件、验收命令与 §六 断言），五项定稿的落点见 §七 粒度裁定 / GATE-5 / §六「S10 / S11（保障层）」段 / 文末「自动化审查阻塞项」。**2026-09-22 第九轮（Fixer，GATE-3 / GATE-5 复核）**：① `build_lifecycle(pdef)` 的**定义自 S4-4 移入 S1d**（其依赖 S1a 的 `LifecycleConfig` 与 S1d 的三个 Lifecycle 类此时齐备），S4-4 只留 `lifecycle` 键的 `ConfigError` 防线与旧 `lifecycle_kwargs` 段删除（删除时机须待 10 个 preset 全部落地）——preset 工厂（S4-2 / S4-3）返回 dict 已写 `lifecycle=build_lifecycle(pdef)`，名字在调用时解析，留到 S4-4 才定义则 S4-3 的验收即 `NameError`；② 「`apply()` 保留为默认实现」落成**公共基类 `Modifier`**（§3.9.2 补默认 `apply` = `_apply_factor(dist, self.factor(...) or {})`，§3.2 / §3.14.2 的 Modifier 示例统一改为继承它，§3.14.2 的 `apply` 转发自此有承载处；备选「S8 删除 `apply`」已否决），§六 断言补「**实际调用一次**不抛 `AttributeError`」（纯存在性断言捕获不到该缺口）；③ S9-1 措辞改为「签名沿用 S8-1 定稿的 `factor` 形态」，改名不再记在本步；④ GATE-5 补 **M1 的依赖闭包回退规则**（向消费方闭包，逐块列出连带范围）与「低层块回退 = 部分回退，须重跑受影响验收」强制条。**2026-09-22 第十轮（Fixer，GATE 复核）**：① 文件清单（`ISSUE-GATE-FAIL-2`）——S10-2 补目标文件（唯一未标步）、§四 补 `core/worst_impact.py` 与 `tests/core/test_pity_condition.py` 两行缺失文件、`PityEngine.__init__` 构造兜底的行号由 `:1166-1172` 修正为 `:1164-1172`；② 测试策略（`ISSUE-GATE-FAIL-6`）——S4-2 / S4-5 / S5c / S7a / S7b / S10-1 / S10-2 七块补「验收命令」（S7b 目标文件由泛写 `tests/` 具体化），顺带补 M2 的 S8-6 / S9-4 两个验收子项，M1 的 29 子块自此**逐块**具备「目标文件 + 人时预算 + 验收命令」（落点见文末「自动化审查阻塞项」）。**2026-09-22 第十一轮（Fixer，代码审计 9 项 AUDIT-BREAK-1 至 AUDIT-BREAK-9）**：字段枚举透传升级为「同 commit 同步 + dataclass 驱动 + 字段往返守卫测试」（三处透传点行级表，AUDIT-BREAK-1）；`create_behavior` 的 `target_featured` / `reset` 注入限定旧类分支（AUDIT-BREAK-2）；preset 返回 dict 按键集恰五键定稿并新增 `flags` / `counters` 消费端（AUDIT-BREAK-3）；`gacha_service.py` 四处同源改动改为端到端非抽卡动作断言（AUDIT-BREAK-4）；新增 S8 跨文件同步清单 A/B/C 三段与 `grep` / `__all__` 两道验收（AUDIT-BREAK-5 / 6 / 8）；「S4-3 后收集期即 ImportError」经核实不成立，改按真实断裂点设 **S7d**（M1）与 **S8-7**（M2）两块（AUDIT-BREAK-7，M1 由 29 块 / 16.4 人时改为 30 块 / 16.9 人时，M2 的 S8 由 3.1 改为 3.5、M2 由 5.5 改为 5.9 人时）；`reads` 双通道（管道 vs 策略查询）各自独立验收（AUDIT-BREAK-9）；其中 AUDIT-BREAK-2 / 3 各存一条 veto 备选（落点见 §3.1.4 与文末「自动化审查阻塞项」）。
> 触发：P56 审查发现的「触发器 × 选择器 × 拓扑 × 效果」四维抽象 + 组合爆炸。**2026-08-24 设计重建**：用户追问「最优雅架构」，从领域本质重新理解保底 → 提出 Tracker + Modifier + Lifecycle 三元组纯函数架构；用户裁决命名 Tracker+Modifier。
> 依赖：P55✅（counter 驱动正交分解 + deltas 展开）+ P56✅（6 个事件驱动类 + Flag/Counter/_redistribute_scope + LifecycleConfig，作为等价性基准）
> 合并：**P82（保底管道顺序接通）于 2026-09-16 并入本计划**，见 §1.5；其结论直接影响 §1.3 的 G5 项与 §3.6 的 priority 设计，P82 文件已归档
> 命名：Tracker（追踪器，状态转移）+ Modifier（概率修正器）+ Lifecycle（生命周期）

## 〇、演进定位——为什么现在重建是合理的

P55 和 P56 **不是被否定，是被提炼**。它们把散的逻辑收敛到可组合的零件，为重建凑齐了输入。

| 阶段 | 解决的问题 | 交付的零件 |
|------|-----------|-----------|
| P55 | counter 驱动内部混乱（soft 三套写法、hard 另起炉灶） | CounterBasedBehavior 基类、SoftStepBehavior 唯一 soft 实现、deltas 展开、PityDef 扁平字段、_resolve_order 排序 |
| P56 | 事件驱动从无到有 | Flag/Counter 状态原语、_redistribute_scope 概率工具、LifecycleConfig、DrawInfo/PityContext 管道、6 个事件驱动类 |
| 共同选择 | 分类式扩张——counter 驱动 vs 事件驱动两类，每类内部再细分 | 新机制 = 新类，rotating_soft 靠 SoftPityMixin 拼 |

**分类本身成了包袱**：counter 驱动难道不是事件驱动吗。每抽一次计数加一、出了 SSR 清零，这不就是事件驱动的状态机。soft 的记忆是无条件递增，rotating 是歪中翻转，targeted 是命中定轨清零——只是事件分支不同。两类本质是同一种东西。

**新方案对 P55/P56 的继承**（零件保留，分类维度重建）：

| 基础设施 | P55/P56 已交付 | P64 如何复用 |
|---------|---------------|-------------|
| 状态容器 | PityState 三层嵌套、_build_pity_state_init、P75 rebind 纪律 | 完全保留，Tracker 读写同一个 PityState，Pity 统一 rebind |
| 上下文管道 | DrawInfo/PityContext（含 scope_cards/card_to_slot） | 完全保留，Tracker 和 Modifier 都消费同一个 PityContext |
| 概率工具 | _redistribute_scope 按基础权重分配 | 完全保留，所有 Modifier 最终落点都是它 |
| 注册与调度 | BEHAVIOR_REGISTRY、_resolve_order、_validate_behaviors、PityEngine 调度 | 接口保留，registry 条目从 class 指向 preset 工厂，调度层加 priority |
| 配置层 | PityDef 扁平字段、TOML 解析 | 字段保留，新增 priority，preset 工厂消费已有字段（签名为 `preset(pdef)`，逐条可配字段由工厂取出，见 §3.2） |
| 测试资产 | 10 个类型的现有测试 | 全部转为等价性测试的基准真值来源 |

## 一、问题

### 1.1 组合爆炸（核心问题）

现有 [pity.py](gacha_simulator/core/pity.py) **全量 10 类**的正交组合已现裂痕（P55/P56 各自交付时各管一类，组合靠硬编码）：

```
rotating × soft = RotatingSoftBehavior          （SoftPityMixin 拼）
rotating × cr = RotatingCRBehavior              （继承 rotating 再叠加）
rotating × cr × soft = RotatingCRSoftBehavior   （mixin + 继承三层）
targeted × soft = TargetedSoftBehavior           （mixin 拼）
```

[`SoftPityMixin`](gacha_simulator/core/pity.py#L509) 缓解了 soft 维度，但 cr 是 RotatingBehavior 子类（[pity.py:556](gacha_simulator/core/pity.py#L556)）、targeted 是独立类（[pity.py:615](gacha_simulator/core/pity.py#L615)）。新增任意拓扑维度（如 inverse 必歪），将与每个现有维度再组合。每类重复实现 `_scope_total_prob`/`_featured_slots`/`_is_trigger_rarity` 骨架（[pity.py:490-498](gacha_simulator/core/pity.py#L490-L498)、[pity.py:694-698](gacha_simulator/core/pity.py#L694-L698) 等多处），after_draw（状态更新）与 before_draw（概率修正）硬编码耦合在各类的 if/else 里。**counter 驱动的 soft/hard 另起一套基类，与事件驱动完全不通**。

### 1.2 剩余缺口盘点（2026-08-24 核实，含双信源）

| 缺口 | 现状核实 | P64 角色 |
|------|---------|---------|
| G1 幻塔连中后必歪 | 真缺口——rotating 只支持「歪→必中」，不支持「中→必歪」 | 新增 `ForceNonFeatured` Modifier + inverse preset |
| G16 幻塔完全不重置 | 单行——[`_should_reset`](gacha_simulator/core/pity.py#L200-L203) 加 `reset="never"` 分支 | **独立先行**（独立 commit，不并 P64） |
| G19 尘白禁区不歪池 | **✅ 矛盾已解决（2026-09-18 独立调研）**：确认真实机制为「每次出金 100% 为当期 UP」。依据：三个相互独立信源直述同一规则（snowbreak.gg / Steam 社区 / Stage1st）+ 期望值数学自洽（不歪池综合出金率 1.24% 时拿 UP 期望约 80.6 抽，与米池的 80.65 抽相等；若提前出金仅 50% 为 UP，期望应约 121 抽，与三方实测数据冲突）+ 官方对米池必写「占出率 50%」而对特选池从不写该条款的对比。手册已据此修正：§15.3 配置由 `hard(target_featured=true)` 改为 `targeted(fate_threshold=0)` 加 `selected_card_init`；§15.4「165 箱当前无此机制」改为「P58 已覆盖」；§21 G19 行同步 | **已处置**；顺带发现手册全部 `targeted` 配置均缺 `selected_card`（见下方注） |

> **2026-09-18 顺带发现（手册层面，P64 范围外）**：手册的 `targeted` 配置除本次修正的尘白 2 处外，其余 **7 处**均未配 `selected_card_init`：绝区零 `epitomized_weapon`（定轨武器，`fate_threshold=1`）与 `bangboo_select`（邦布池，`=0`）；鸣潮 `wengine_targeted`（定轨武器，`=1`）、`ww_standard_weapon_select`（常驻武器，`=0`）、`ww_beginner_select`（新手池，`=0`）；§十四 `lds_mixed_select`（`=1`）；异环 `yihuan_wp_targeted`（武器定轨，`=1`）。**这不是配置缺陷**——`selected_card` 是运行时状态，定轨类玩法本就由策略层经 `switch_epitomized_target`（[gacha_service.py:292](gacha_simulator/service/gacha_service.py#L292)）在模拟中设定目标，把目标写死在 TOML 里反而与机制不符。但手册原先未说明这一点，读者照抄且不配策略时会遇到保底不生效且无任何提示。**已处置**：手册 §〇「保底 type 速查」补说明，列出两条设置途径与静默退化的行为。实测依据：`targeted` 的必中分支条件为 `self._guaranteed.is_set() or (selected and ...)`（[pity.py:652](gacha_simulator/core/pity.py#L652)），只判 `selected` 是否非空（实测填不存在的卡 ID 与填真实卡 ID 效果相同，均使概率由 0.001/0.001 变为 0.002/0.0）；`after_draw` 在 `selected is None` 时直接 return，命定值不累积。

### 1.3 保底相关缺口完整盘点（2026-08-24 逐条核实，双信源纪律）

> 信源纪律：两个以上不同信源一致且无矛盾才能确定为机制，否则标注「待确认」。见 [feedback-search-report-discipline](../../../.claude/projects/d--Users-DELL-Desktop-gacha-simulator----------/memory/feedback-search-report-discipline.md)。

| 缺口 | 语义 | 归属 |
|------|------|------|
| G13 战双新手首次 40 | `hard.threshold` 首次特殊值（[手册:2304](docs/主流抽卡游戏卡池机制配置转换手册.md#L2304)，40 vs 60） | 🟢 配置即可（2026-08-24 双信源确认：[caoteng951](https://www.caoteng951.cn/tengzx01/4662.html) + [9game](https://www.9game.cn/zspms/4456638.html)）：`hard(threshold=60, counter_init=20)`，首次 40 触发、归零后续 60 |
| G2 阴阳师神眷阈值 | 神眷 = 「出 SSR/SP 概率掉落 + 累抽 450/800 必定获得」（[手册:2284](docs/主流抽卡游戏卡池机制配置转换手册.md#L2284)，机制双信源确认 2026-08-24：[17173 2023](http://news.17173.com/z/yys/content/01112023/111739115.shtml) + [9game 2023](https://www.9game.cn/yys/9780872.html)） | 🟡 **milestone 层扩展（2026-08-24 归属修正）**：神眷是兑换道具（资源），「必定获得」本质是累抽奖励（milestone at=动态 threshold），非保底概率；450/800 依赖全图鉴状态（跨系统状态）。与 G14（pity 动态 threshold）分属两系统，P64 范围外 |
| G14 战双命运池浮动 | 每次保底周期随机 T∈[80,100]、非保底出 S 1.5%、出 S 重置重抽 T（[手册:2305](docs/主流抽卡游戏卡池机制配置转换手册.md#L2305)，机制双信源确认 2026-08-24：[doyo](https://www.doyo.cn/news/26839.html) + [taptap 数学分析](https://www.taptap.cn/moment/15230243631530325)） | 🟡 后续扩展方向：T 分布未公布（U13）；确认后 P64 条件谓词可表达「counter ≥ 随机 T」 |
| G5 绝区零执行顺序 | 福利保底（`hard(max_triggers=1)`——**ISSUE-032：`max_triggers` 已纳入本期配置接线——`PityDef.max_triggers` + `config_toml` 解析 + GUI 控件（2026-09-27 裁决），见 §3.1.3**）应先于 targeted——当前 `_BTYPE_ORDER` hard=1 < targeted=3 已满足（[手册:554](docs/主流抽卡游戏卡池机制配置转换手册.md#L554) 描述过时，2026-08-24 核实） | ✅ **纳入 P64 主线**：显式化现有隐式顺序 + 提供覆盖能力（调度层 `priority`），见 §3.6 |
| G15 pjsk 加权抽数 | 付费石双倍天井进度（[手册:2306](docs/主流抽卡游戏卡池机制配置转换手册.md#L2306)，付费 +1 / 免费 +0.5） | 🔴 **缺口（2026-09-21 重估）**：原记「🟢 近似可配」（`reward.resources_gained` 每抽按池注入 + exchange pool 兑换 50/100 档），但按「精确建模原则」（CLAUDE.md §二）近似不计入已覆盖。该近似有语义打折（卡附带产出 vs 动作进度）与配置脆性（全 reward 需配）两处偏差，严格语义需 milestone `weight_by_pool`（milestone 层，P64 范围外） |
| G3 崩坏3 UP 保护排除已拥有 | 精准补给每 50 抽必出 UP 装备，但**已获得的装备从 UP 组中排除**（[手册:963](docs/主流抽卡游戏卡池机制配置转换手册.md#L963)） | ✅ **归本计划**（2026-09-21 裁决）：做**真实建模**，需 S8 卡级管道（子集定向）+ S9 状态可见性（读 `acquired`），方案见 §3.10.4。原记「pool 层过滤」属近似（会让普通抽卡也不出已拥有装备），已按「精确建模原则」否决 |

> **关键洞察**：G14（战双命运池）是 pity 层「hard 触发条件的动态化」（threshold 每次重置随机 T）：P64 的「条件谓词 → 概率修正」抽象若延伸到 counter 驱动型可统一表达（hard 本身即「counter ≥ threshold → ForceFeatured」特例），记为后续扩展方向。G2（阴阳师神眷）是 milestone 层「累抽奖励动态 threshold」（450/800 按全图鉴状态，2026-08-24 归属修正），非 pity 层。G13 已由 `counter_init=20` 配置即可表达（2026-08-24 双信源确认），非扩展方向。

### 1.5 P82 并入：保底管道执行顺序（2026-09-16 实测完成）

**合并说明**：P82（保底管道顺序接通）于 2026-09-16 并入本计划，P82 文件归档。其结论直接影响 §1.3 的 G5 项与 §3.6 的 priority 设计，**已于 2026-09-18 裁决，见本节末的裁决结论**。

**P82 的问题**：`_resolve_order()`（[pity.py:916](gacha_simulator/core/pity.py#L916)）会计算排序（稀有度 rank → type 顺序 → name），但其结果**只写入 `self._behavior_list`**，而三个调度入口（`get_probabilities` / `before_draw` / `after_draw`）走的是 `get_behaviors_for_pool()` → `spec.pity_names`，后者由 `batch_simulator.py:173-177` 按 **TOML 定义顺序**构造。即排序算了但未接入概率管道，`P30 #11` 的「顺序由定义顺序决定」在代码上仍成立。

**P82 的实测结论（2026-09-16）**：

| 配置场景 | 顺序是否影响结果 |
|---------|----------------|
| soft + soft（同 / 异目标槽位） | 否。概率变换数学可交换（手算 + 95 抽序列对比双重验证） |
| soft + hard | 否。hard 触发时覆盖一切，未触发时无作用 |
| rotating / targeted / hard 的各类组合 | 否 |
| **跨 scope（保 ssr + 保 sr）** | 否。层级保护使低稀有度保底不改变高稀有度保底的可窃取总量 |
| **含 `rotating_cr` 的组合** | **是**。46 组随机扫描中 12 组敏感，最大差异 30/95 抽 |

`rotating_cr` 敏感的根因是它**消费全局 `random`**（`before_draw` 内 `random.random() < cr_base_rate`），顺序改变导致随机流错位，属随机源共享的副作用，非概率语义上的顺序依赖。

**对 G5 / §3.6 priority 设计的影响（重要）**：

G5 的原设计是「`_resolve_order` 排序 key 加 `priority`」。P82 实测表明**单靠排序键无法表达顺序语义**：多数保底组合本就顺序无关（可交换），因此加 `priority` 后即使排序生效，也不会改变任何概率输出，仅对齐含 `rotating_cr` 配置的随机流。

实施 P64 时需先裁决以下三项（**已于 2026-09-18 裁决，结论见本节末**）：

| # | 待裁决 | 说明 |
|---|-------|------|
| 1 | `_resolve_order()` 存废 | 接线（让排序生效）/ 废弃（删除或标注未接通）/ 暂缓。P82 实测倾向废弃，因收益近零而引入「含 `rotating_cr` 配置结果会变」的语义成本 |
| 2 | `priority` 是否仍需引入 | 若裁决 1 为废弃，G5 的 priority 设计失去落脚点；若保留，需说明它要解决什么实际问题（当前 `_BTYPE_ORDER` hard=1 < targeted=3 已满足绝区零需求，[§1.3](#) 已核实）。**2026-09-16 补**：§3.1.5.5 的反例表明顺序并非普遍无关（`target_featured=True` 的 soft 与 hard 共存时结果不同），但该敏感性来自组合本身而非排序键，priority 能否覆盖它取决于裁决 1 的取向 |
| 3 | 新架构下顺序语义的归属 | 若 Tracker+Modifier 让 Modifier 变得可自由组合，需明确「组合顺序」是语义的一部分还是实现细节；P82 的实测数据（多数组合可交换）可作为该判定的依据 |

**P82 全文**：`docs/03-归档/P82 保底管道顺序接通——_resolve_order 未接入概率管道.md`（含完整机制链路、五种候选方案的取舍、四条风险分析、验收标准）

**裁决结论（2026-09-18，用户裁决）**

| # | 裁决 | 连带 |
|---|------|------|
| 1 | **接线**：让 `_resolve_order()` 的排序结果成为概率管道的实际执行顺序（P82 方案 A） | 见下方「接线实施方案」 |
| 2 | **保留 `priority`**：接线后「TOML 书写顺序」不再是可用的顺序控制手段，`priority` 成为唯一的覆盖入口；G5 原设计即含它，能力保留 | PityDef `priority` 字段 + `_resolve_order` 排序键插入 + GUI 控件（§3.6 M3） |
| 3 | **分两层定性**：保底**之间**的顺序由排序键决定，属语义的一部分（配置者经 `priority` 干预）；保底**内部**的 Modifier 链顺序由 preset 固定，属实现细节，不对外配置 | 文档中两处「顺序」须分开表述，避免混为一谈 |

**接线实施方案（2026-09-18 拟定）**

- **核心改动点**：`PityEngine.get_behaviors_for_pool()`（[pity.py:1189-1200](gacha_simulator/core/pity.py#L1189-L1200)）的输出顺序，三个调度入口共用它，改此处即改管道。
- **实现取向（推荐：独立排序视图）**：`PityEngine.__init__` 在 behavior 全部构造完成后，为每个 pool 预计算排序后的保底名列表（如 `self._pool_order: Dict[str, List[str]]`），`get_behaviors_for_pool()` 消费该视图；`PoolPitySpec.pity_names` **保持 TOML 顺序不动**。
  - 理由：`pity_names` 兼有第二职责——[banner.py:261](gacha_simulator/core/banner.py#L261) 用 `','.join(pity_spec.pity_names)` 生成 `draw_pity_names` 输出串，下游（[process_trace.py:123-125](gacha_simulator/core/process_trace.py#L123-L125)、[streaming.py:174-176](gacha_simulator/core/streaming.py#L174-L176)）以 `split(',')` + set 消费，**语义与顺序无关**，但字面顺序会进 golden 快照。独立视图使输出串保持不变，把行为变更面收窄到「概率管道顺序」一处。
- **排序键**：`(rarity rank, _BTYPE_ORDER, name)`（P55 既定），接线后 `_BTYPE_ORDER` 真正生效；`priority` 插入位置为 rank 之后、type order 之前（§3.6 M3）。
- **行为变更面**：仅「同一池内、书写顺序与排序键不一致」的配置受影响。已实测（P82 §六 + §3.1.5.5）敏感集合为两类：含 `rotating_cr` 者（随机流错位）、`target_featured=True` 的 soft 与 hard 共存者（真实概率语义）；其余组合数学可交换，接线不改变其输出。**2026-09-18 补第三类（实测新发现）**：跨 type 顺序发生反转且存在 `depends_on` 时，依赖方的状态键**创建时机**会变（旧顺序在源触发当轮就执行依赖方 `after_draw` 并创建其 `counter` 键；新顺序下该轮依赖方仍未激活、键延后到下次 `before_draw` 才创建）。实测（rotating 源 + hard 依赖，`pity_names` 由 `(source, dependent)` 反转为 `(dependent, source)`）：依赖方 `_active` 最终值不变（均为 True），但 `PityState` 快照的键存在性有差异。该差异只在 `depends_on` 配置中出现，当前 `config.toml` 无此配置。当前 `config.toml` 示例仅一条保底定义，不受影响。
- **验证要求（基线固化 + 等价对照）**：接线前用固定种子跑 `config.toml` 与既有测试配置，固化 `CompactResult` 快照；接线后同种子重跑逐字段对比，差异必须逐一归因到上述三类，否则视为回归。`tests/core/test_pity_integration.py::TestDependsOnIntegration` 与 `TestMultiPityCoordination` 两组用例是该验证的重点观察对象（前者的 `pity_names=('source', 'dependent')` 接线后会反转，断言仍应通过；后者 `('rot', 'hard90')` 同样反转，概率断言应不变）。
- **排期建议：独立先行**（同 G16 模式，独立 commit）。理由：与 P64 主线的重构正交、可独立验收；`_resolve_order`/`_validate_behaviors` 在 P64 §3.2 中的「逻辑零改动」结论不受影响。排期最终以用户裁决为准。

### 1.4 为什么旧分类掩盖了统一性（2026-08-24 新增）

counter 驱动难道不是事件驱动吗。每抽一次计数加一、出了 SSR 清零，这不就是事件驱动的状态机。soft 的记忆是无条件递增，rotating 是歪中翻转，targeted 是命中定轨清零——只是事件分支不同。两类本质是同一种东西，**记忆的不同形态**。

三个统一性被分类掩盖：

1. **状态原语统一**：P56 提炼的 Flag/Counter 已是通用原语，但被关在事件驱动一侧，counter 驱动另起一套计数逻辑，本可以是同一个 CounterTracker。
2. **生命周期统一**：`deactivate_on_early_hit`/`depends_on` 在 P55 只给 counter 驱动用，P64 计划想给事件驱动补上——说明它本就与驱动类型无关，是正交包装层。
3. **概率解读统一**：`SoftStepBehavior._compute_probabilities` 和 `RotatingBehavior.before_draw` 都在做「读状态算概率」，但因分属两类各写各的。

## 二、目标

- **用 Tracker + Modifier + Lifecycle 三元组重建全部保底类型**（不再分 counter 驱动 vs 事件驱动两类），现有 10 个类型退化为 **preset**（三元组的具名组合）
- 新机制 = 新增 Tracker 或 Modifier 零件，**不再写新类**；任意 Tracker × 任意 Modifier 自由组合
- **等价性保证（P64 验收核心）**：同配置下旧类 vs 新引擎，固定种子逐场对比概率分布 + 状态快照完全一致（全部类型，含 counter 驱动）
- 覆盖 G1（inverse preset）+ G16（独立先行 `reset="never"`）+ G5（调度层**接线** + `priority` 显式排序，2026-09-18 裁决，见 §1.5）+ G3（UP 保护排除已拥有，真实建模，2026-09-21 裁决，见 §3.10.4）
- PityEngine 调度层接口签名兼容（`_resolve_order` 加 `priority` 排序优先级，新增行为全 0 时与现状一致），GUI 参数描述（params/ui_params）不变

## 三、方案

### 3.0 领域本质——保底是什么

退回领域本质，忘掉现有 10 个类的名字。保底是一个数学对象：`P(本次出什么 | 历史)`。所有保底机制都在回答同一个问题——在给定历史下如何修改基础概率分布。历史只有两种形态，**计数**（抽了多少次没出）和**标记**（上次歪了还是中了）。概率修改也只有两种形态，**连续提升**和**离散强制**。

保底由三件独立的事组成：

```
历史 ──[Tracker 追踪]──→ 状态 ──[Modifier 修正]──→ 概率
                          ↑                       ↓
                        事件                     分布
                          └──[Lifecycle 生命周期]──┘  正交包装层
```

| 概念 | 职责 | 纯函数签名 | 中文 |
|------|------|-----------|------|
| Tracker | 看到什么事件，如何更新状态 | `(State, Event) -> State` | 追踪器 |
| Modifier | 当前是什么状态，如何修正概率 | `(State, BaseDistribution) -> Distribution` | 修正器 |
| Lifecycle | 这个机制什么时候活着 | 包装层（Always/Once/Dependent） | 生命周期 |

三件完全独立：Tracker 不管概率怎么算，Modifier 不管状态怎么来，Lifecycle 不管前两者是什么。一个保底机制就是三件的组合：`Pity = Tracker(s) + Modifier(s) + Lifecycle`。

**与旧分类的对比**：旧版把领域切成 counter 驱动 vs 事件驱动两类，每类内部再细分。新版按 Tracker/Modifier/Lifecycle 三个正交维度切，任意 Tracker × 任意 Modifier 自由组合。

### 3.1 抽象层（新建 `core/pity_tracker.py` + `core/pity_modifier.py`）

#### 3.1.1 Tracker（追踪器）—— `(State, Event) -> State`

Tracker 是 pure 函数：给定旧状态和本次抽卡事件，返回新状态。事件 = `PityContext`（含 `DrawInfo.reward_rarity/is_featured/reward_id` + `PityState`）。每个 Tracker 读写 `PityState` 中自己声明的键。

| Tracker（**签名以 §3.2 / §3.3 / §3.14.2 的定稿代码为准**，ISSUE-104） | 语义 | 对应现有 | 状态键 |
|---------|------|---------|--------|
| `CounterTracker(scope, reset_on, init)` | 每抽 +1；出金重置：`reset_on="scope"`（出触发稀有度即重置）、`"featured"`（仅 featured 重置）、`"never"`（永不重置，G16）。`init` 为计数初值，取值 `pdef.counter_init`（§3.2 取值来源表） | CounterBasedBehavior 计数逻辑 | `counter` |
| `FlagTracker(judge, hit, miss, flag)` | 出 scope 时，judge 命中取 `hit` / 未命中取 `miss`（`"set"` / `"clear"`），写 `flag` 指定的标记键。**四关键字参**，preset 实例：`FlagTracker(judge="featured", hit="clear", miss="set", flag="guaranteed")`（rotating）/ `... hit="set", miss="clear", flag="forced_loss"`（G1 rotating_inverse，§3.3） | RotatingBehavior guaranteed | 由 `flag` 形参指定（`guaranteed` / `forced_loss` 等） |
| `StreakTracker(judge, threshold, base_rate, state_probs)` | 连续未命中计数，未命中 +1、命中清零；叠加随机拦截（CR）；含 `was_guaranteed` 守卫（仅抽前 guaranteed 未置位时更新，§3.2 rotating_cr 行）。`threshold` / `base_rate` / `state_probs` 取值 `pdef.cr_counter_threshold` / `cr_base_rate` / `cr_state_probs` | RotatingCRBehavior cr_counter | `cr_counter` |
| `FateTracker(judge, hit, miss, keys)` | 出 scope 时，命中定轨对 `keys` 集清零/未命中累积。`keys` 即多键集：`fate_points` / `losses` / `guaranteed` / `lost_rotating`（§3.2 targeted 行；`hit` / `miss` 由 S1 定稿，形参名同 `FlagTracker` 口径）。另**读**外部注入的 `selected_card`，见 L4 | TargetedBehavior fate/losses | `fate_points`, `losses`, `guaranteed`, `lost_rotating`（另**读** `selected_card`） |

<!-- REVIEW-R1-FIX: ISSUE-104 -->
> **签名不一致已被消除（ISSUE-104，2026-09-22）**：原表把 `FlagTracker` 写成 `FlagTracker(judge, inverse)` 两参、`FateTracker` 写成 `FateTracker(judge)` 单参、`CounterTracker` 写成 `(scope, reset_on)` 两参，与 §3.2 / §3.3 / §3.14.2 的 preset 代码**三处三种写法**；且 `FlagTracker` 无 `flag` 形参，无法表达「标记名」（rotating 用 `guaranteed`、G1 用 `forced_loss`），`CounterTracker` 缺 `init`。实施者按原表落笔即与全部 preset 代码不兼容。现按**定稿代码**回写（上表），并明确：`FlagTracker(judge="featured")` 这类单参简写形态**不是**可实施的签名，§3.2 preset 表的对应单元格已同步为定稿形态。

> **G16 自然落位**：`CounterTracker(reset_on="never")` 去掉重置规则即可，无需特殊分支。
> **G13 自然落位**：`CounterTracker(scope=…, reset_on=…, init=20)` + `CounterCondition('counter', 60)` 首次 40。**阈值属条件、不属 Tracker**——原稿写 `CounterTracker(init=20, threshold=60)`，而 `threshold` 不是 Tracker 形参（§3.2 preset 表：`hard` 的 τ 由 `CounterCondition` 承载，§3.14.2）。<!-- REVIEW-R1-FIX: ISSUE-104 -->
> **G14 自然落位**（后续扩展）：`RandomThresholdTracker(range=(80,100))` 每次重置随机阈值。

**Tracker 协议（强制；`rebind` 为 2026-09-22 补全的公开接口名，ISSUE-029）**：Tracker 的契约由四个方法构成，`Pity`（§3.1.4）按 N1 相位与 M4 语义调用它们。

| 方法 | 语义 |
|------|------|
| `rebind(state, name)` | **P75 纪律**：把本 Tracker 内部的 `Counter` / `Flag` 遥控器重绑到 per-call `state`（纯重定向，不复制旧值）。`Pity._rebind_state` 对其**无条件**调用，故**方法必须存在**；无自身状态键的零件可写空实现，但不得省略 |
| `advance(ctx, state, name, readonly)` | 见下方 N1 相位表 |
| `commit(ctx, state, name, skip_reset=False)` | 见下方 N1 相位表 |
| `did_reset(ctx, state, name)` | M4 统一语义（「本次抽卡是否让本保底回到初始状态」） |

<!-- REVIEW-R1-FIX: ISSUE-029 -->
**为什么必须显式定义（ISSUE-029）**：现有代码的对应物是**私有**方法 `PityBehavior._rebind_state`（[pity.py:90](gacha_simulator/core/pity.py#L90)、[pity.py:147](gacha_simulator/core/pity.py#L147)），由 `PityEngine._rebind_state` 经 `hasattr(bh, '_rebind_state')` **守卫**调用（[pity.py:1233](gacha_simulator/core/pity.py#L1233) 起）。新架构用的是**无守卫的公开名 `rebind`**，调用点也从「每轮模拟首调度」变为「每次抽卡的调度入口」。故不得靠「旧代码里有就先当它存在」推断——协议不写、实现不加，首次抽卡即 `AttributeError`，等价于全部保底不可用。

**计数器相位（N1，强制，2026-09-16 定稿）**

问题：旧 `CounterBasedBehavior.before_draw`（[pity.py:179-187](gacha_simulator/core/pity.py#L179-L187)）与 `SoftPityMixin.before_draw`（[pity.py:529-533](gacha_simulator/core/pity.py#L529-L533)）都是**先自增、再用自增后的值算概率**，实测 `hard(threshold=90)` 首次 100% 出现在**第 90 抽**。若把递增放到 `after_draw`，第 90 抽读到 89、首次触发落到第 91 抽。总次数两者相同，差的是**读相位**，故「每抽加一次」的表述覆盖不了它。

**方案（计数型 Tracker 分两段，非计数型只在 after 侧）**。「计数型」的界定必须**显式列出**：`CounterTracker.counter` 属计数型（旧 `before_draw` 推进）；`StreakTracker.cr_counter` **不属**（旧实现只在 `after_draw` 累加与清零，[pity.py:590-600](gacha_simulator/core/pity.py#L590-L600)），若按「计数器」字面把它划入计数型，`advance` 会每抽多推进一次。

| 方法 | 调用点 | 计数型 Tracker | 非计数型 Tracker |
|------|-------|---------------|-----------------|
| `advance(ctx, state, name, readonly)` | `Pity.before_draw` 首段 | `readonly=True` 只读不写；否则 `counter += 1` | no-op |
| `commit(ctx, state, name)` | `Pity.after_draw` | 命中时 `counter ← 0` | 置位/清位/累积 |

与旧实现结构同构（旧代码本就是 before 侧 `incr()`、after 侧 `reset()`），故在未触发下述例外时，`state` 中的计数值与旧实现逐位相同，「状态快照逐场一致」这条验收无需适配。

**例外（`deactivate_on_early_hit`，2026-09-16 补）**：旧 `CounterBasedBehavior.after_draw`（[pity.py:189-198](gacha_simulator/core/pity.py#L189-L198)）在 `_on_reset(ctx)` 返回 True 时**提前 return，跳过 `_counter().reset()`**；而 `SoftStepBehavior._on_reset` / `HardPityBehavior._on_reset`（[pity.py:329-337](gacha_simulator/core/pity.py#L329-L337)、[pity.py:405-413](gacha_simulator/core/pity.py#L405-L413)）恰在 `deactivate_on_early_hit=True` 时清 `_active` 并返回 True。实测：`hard(threshold=90, deactivate_on_early_hit=True)` 在第 5 抽命中后 counter 仍为 5（未重置），无该配置时归 0（概率流不受影响，差异只落在状态快照与 `get_counter()`）。故 `commit` 的语义须是「**Lifecycle 退役动作与重置同序判定，退役则跳过重置**」，不能写成无条件的「命中即归零」。

**已排除的替代方案**：把 `counter_init` 与重置值都改成 1，使 after 侧递增也能对齐读数。数学上可对齐，但 `state` 中的值会整体偏移 1（抽完第 1 抽后 counter 为 2，而旧实现为 1），连带快照对比、`get_counter()` 查询、GUI 展示、`counter_init` 的用户含义（G13 的 `counter_init=20` 表示「已垫 20 抽」）全部平移，把一处相位约定扩散成全局数字偏移。

**不选「读时虚拟 +1」**：那会让「Modifier 读到的值」与「state 中的值」相差 1，任何读 counter 的下游代码都要区分用途，是长期负债。

**测试断言**：`hard(threshold=90)` 首次 100% 出现在第 90 抽；`soft` 的 boost 起始抽数；`readonly=True` 查询不推进计数。


**did_fire 统一语义（M4，强制，2026-09-16 裁决）**：`Pity.did_fire` 供 `PityEngine.after_draw` 的 depends_on 激活传播使用（[pity.py:1340](gacha_simulator/core/pity.py#L1340)，全代码唯一调用点）。**统一语义 = 「本次抽卡是否让本保底回到初始状态」**，由各 Tracker 的 `did_reset(ctx, state, name)` 提供，`Pity.did_fire = any(tr.did_reset(...))`。

现状并不一致（**六类，其中三类方向相反**），`did_reset` 需把 rotating/targeted 收严、并**显式接受三个 `_soft` 复合类型的放宽**：

| 旧类 | 现状 did_fire | 统一后 `did_reset` | 变化 |
|------|--------------|-------------------|------|
| counter 驱动（soft/hard） | `_should_reset(ctx)`，按 `reset` 配置（[pity.py:200-206](gacha_simulator/core/pity.py#L200-L206)） | 同左（`scope`→出该稀有度；`featured`→出 featured，**无 scope 门控**） | 无 |
| rotating | `ctx.draw.is_featured`（[pity.py:500-503](gacha_simulator/core/pity.py#L500-L503)） | 出 scope ∧ is_featured | **加 scope 门控（收严）** |
| targeted | `_is_hit(ctx)`，即 `reward_id == selected`（[pity.py:699-701](gacha_simulator/core/pity.py#L699-L701)） | 出 scope ∧ reward_id == selected | **加 scope 门控（收严）** |
| **`rotating_soft`** | 经 MRO 落到 `RotatingBehavior.did_fire` = **「出 scope ∧ is_featured」**（`SoftPityMixin` **不定义** `did_fire`，[pity.py:509-537](gacha_simulator/core/pity.py#L509-L537) 只有 `before_draw` / `after_draw` / `_rebind_state`） | **「出 scope」**——该族 preset 的 CounterTracker 是「触发稀有度重置抽数 counter」，**hit/miss 两分支都 ResetCounter**（§3.2 preset 表，对齐 [pity.py:534-537](gacha_simulator/core/pity.py#L534-L537)），故 `did_reset = (reward_rarity == scope)` | **放宽（激活更宽）** |
| **`rotating_cr_soft`** | 同上（`RotatingCRBehavior` 为 `RotatingBehavior` 子类且无覆写） | **「出 scope」**（同 rotating_soft） | **放宽（激活更宽）** |
| **`targeted_soft`** | 经 MRO 落到 `TargetedBehavior.did_fire` = **「出 scope ∧ 命中定轨」** | **「出 scope」**（同族 CounterTracker 的 reset 条件） | **放宽（激活更宽）** |

<!-- REVIEW-R1-FIX: ISSUE-102 -->
> **为何三个 `_soft` 复合类型会放宽（ISSUE-102，2026-09-22 补）**：骨架的 `Pity.did_fire = any(tr.did_reset(...))` 取**任一** Tracker 的重置，而这三个类型的 preset 里同时有「事件驱动 Tracker（命中才翻转）+ 触发稀有度 counter Tracker（出 scope 即重置）」。旧实现只有前者参与 `did_fire`（后者在 mixin 里，且 mixin 不定义 `did_fire`），新实现多算了后者。**后果**：`depends_on` 依赖方在「出 scope 但未命中 UP / 未命中定轨」时被**提前激活**——方向与本表上方三行的收严相反。
>
> **覆盖缺口（修复前）**：本表的 M4 三行、§六 的「三类的 `did_fire`」断言、§七 S5 的「M4 did_fire 三类语义」三处**均未包含**这三个类型，而 §3.1.3 附近的等价性排除条款（「事件驱动型 + `depends_on` 须显式排除」）又把它们挡在等价性测试之外——放宽既不被测试捕获、也未登记为差异。**三处已同步补入**。
>
> **裁定（原为 ⚠ 待人工裁决，2026-09-22 第八轮定稿，ISSUE-GATE-risk-mitigation）**：可选方案本是让该族 CounterTracker 的 `did_reset` 只认「出 scope ∧ 命中」，把「触发稀有度即重置 counter」（N1 相位，决定 counter 何时归零）与「本次是否回到初始状态」（M4，决定 `depends_on` 传播）**分离**为两个语义。**裁定：不采纳 hit 门控**，该族 `did_reset` 一律按「出 scope」。理由：该族 CounterTracker 的重置条件本就与旧 `CounterBasedBehavior.after_draw` 的命中 / 未命中两分支同源，人为加门控会让「同一个 counter 的归零条件」与「本次是否回到初始状态」出现两套口径，反而引入新的静默不一致；放宽方向已按 §3.1.1 M4 表六行、§六 断言、§七 S5c 三处登记，并写入 §五 风险行。**「既不登记差异、又不加门控」的中间态仍禁止**。<!-- REVIEW-R1-FIX: ISSUE-GATE-risk-mitigation -->

> **2026-09-18 注**：上表「现状 did_fire」列记录的是 2026-09-16 统一**之前**的行为，所引行号已随该次修改指向统一**之后**的代码（其中 rotating/targeted 两行现已含 scope 门控）。该列仅作历史对照，勿据以判断当前实现。

**理由**：现状的 rotating/targeted 在「出非 scope 稀有度的 UP」时 `did_fire` 为真，但其状态并未翻转（`after_draw` 的 scope 门控把它们挡在外面），`depends_on` 依赖方因此被提前激活。统一后 `did_fire` 与 `after_draw` 里的重置分支**严格同条件**。

**影响面（行为变更，分两类，方向相反——ISSUE-102 更正）**：

- **收严类**（counter 驱动 / rotating / targeted）：激活只会更严格、不会更宽。现有 `config.toml` 无 `depends_on`；`tests/core/test_pity_integration.py` 的被依赖方为 rotating、抽到的是 SSR featured，两种语义下同为 True。
- **放宽类**（`rotating_soft` / `rotating_cr_soft` / `targeted_soft`）：出 scope 但未命中时依赖方被**提前激活**，与上一类方向相反。**修复前本行原写「激活只会更严格、不会更宽」，对这三个类型不成立**——原表述只覆盖到表中前三行，已按六行重述。该三类**不在等价性范围内**（§3.1.3 的排除条款「事件驱动型 + `depends_on`」已覆盖；且三个 `_soft` 类型本身即事件驱动型），须按「行为变更」单独验收并登记差异归因。

**✅ 已于 2026-09-16 独立落地**（早于 P64 主线）：`RotatingBehavior.did_fire` 与 `TargetedBehavior.did_fire` 各加 scope 门控，`RotatingCRBehavior` 的冗余覆写删除。验证方式为「用改动前的 `pity.py` 跑新增测试」，`TestDidFireUnified` 5 例中 3 例失败（正是测 scope 门控的 3 例），确认测试有效；落地后全量 `pytest` 1573 passed，确认无隐藏依赖。P64 实施时应按此语义写 `did_reset`，勿回退。

**三点须显式声明（2026-09-16 补）**：

1. **`never` 行是新增后的语义，不是现状**：现有 `_should_reset` **没有** `never` 分支，恒 False 只是「稀有度字符串永不等于 `'never'`」的偶然结果。该分支由 §3.8 的 G16 独立先行新增。
2. **`featured` 的不对称是有意保留**：counter 驱动型的 `featured` 分支只看 `is_featured`、无 scope 门控（[pity.py:201-202](gacha_simulator/core/pity.py#L201-L202)），与 rotating/targeted 统一后带 scope 门控的语义不同。它属 `reset` 配置的既有语义，不在本次统一范围内；但须写明，否则「did_fire 统一」会被误读为三类完全同构。
3. **`reset` 取值无白名单，未知值静默永不重置（P64 范围外）**：`create_behavior` 仅在 `pdef.reset` 为 truthy 时透传该参数（[pity.py:879-880](gacha_simulator/core/pity.py#L879-L880)，故空串回退 `scope`）；一旦传入非空值，`_should_reset` 便对其做 `reward_rarity == reset` 比较（[pity.py:200-203](gacha_simulator/core/pity.py#L200-L203)），故任何既非 `'featured'` 又不等于稀有度名的值（如 legacy 值 `'featured_ssr'`）恒 False（永不重置）。**2026-09-18 更新**：原描述的触达路径已随 P81 B11 消失——`_migrate_legacy_pity`（旧 TOML 自动迁移）整函数删除，改为 `_check_pity_format()` 对旧格式显式抛 `ConfigError`（[config_toml.py:385-421](gacha_simulator/core/config_toml.py#L385-L421)）；`tests/test_config_toml.py` 中守护该值的 `TestMigrateLegacyPity`/`test_reset_preserved` 亦被 `TestRejectLegacyPityFormat` 整类替换。**缺陷本体不变**——新格式 TOML 的 `reset` 仍无取值白名单（[config_toml.py:687](gacha_simulator/core/config_toml.py#L687) 直接透传），手写 `reset = "featured_ssr"` 仍恒 False。已独立登记为保底系统 [03-审计.md](docs/01-活跃/subsystems/保底系统/03-审计.md) 异常 6（状态：待裁决）。

**键集语义（L4，等价性前提）**：Tracker 声明的键**仅当初始值为 truthy 时才预建 state 键**（`if init: set()`），与旧 `_build_pity_state_init`（[pity.py:987-1023](gacha_simulator/core/pity.py#L987-L1023)）在 `guaranteed_init=False`、`counter_init=0`、`fate_points_init=0` 时不预建键的行为一致。

**两个例外（实现不得套用 truthy 规则）**：

1. `selected_card` 是**无条件注入**（同函数内 `state.set(pdef.name, "selected_card", sc)`，`sc` 为 None 也写），targeted 家族的初始快照里必然有该键。若新实现按 truthy 规则处理，`to_dict()` 比对会少该键。
2. `selected_card` 的**写入者不是 Tracker**，而是策略层的 `NonDrawAction`（[gacha_service.py:292](gacha_simulator/service/gacha_service.py#L292)、[gacha_service.py:294](gacha_simulator/service/gacha_service.py#L294)），`FateTracker` 只读它。故 Tracker 允许读「不由自己声明的键」，`selected_card` 的初始化路径独立于 Tracker 声明。

#### 3.1.2 Modifier（修正器）—— `(State, BaseDistribution) -> Distribution`

> **2026-09-21 修订**：本表已由 **§3.14** 修订（**条件外置**：触发条件从各 Modifier 内部提出为独立的 Condition 对象，效果实现不变）。本表保留作历史形态与术语索引，实施以 §3.14 为准。
>
> **S2 与 S12 的先后（ISSUE-101 补，强制）**：**S2 按本表形态实现**（触发条件写在 Modifier 内部），**S12 随即外置**为 §3.14.2 的 `ConditionalModifier` 形态——S12 已前移进 M1、排在 S2 之后、S4 之前（§七）。故本表不是「永不实施的死稿」，而是 **M1 内 S2 阶段的有效实现形态**；S12 之后以 §3.14 为准。S4 的 preset 工厂与 S5 的等价性测试一律消费**外置后**的形态（§3.2 / §3.3 / §3.14.2 的代码即该形态）。
>
> **Modifier 方法名定稿（ISSUE-GATE-dependency-order，2026-09-22）**：M1（S2 起至 S7）期间的 Modifier 方法名一律为 **`apply(ctx, view, dist, readonly) -> 分布`**（骨架 §3.1.4 按此调用），`ConditionalModifier` 也实现 `apply` 并转发到内层；**`factor(...) -> 因子向量` 自 S8 引入**（§3.9.2 定稿），此后骨架改调 `factor`、`apply` 保留为默认实现。全篇三处（本表 / §3.1.4 骨架 / §3.14.2 包装器）以本条统一，见 §3.9.2 的「与 §3.1.4 骨架的关系」段与 §3.14.2 的 `apply` 转发实现。

Modifier 是 pure 函数（除 InterceptModifier 显式依赖 RNG）：给定当前状态和基础分布，返回修正后分布。**实现形态为乘性因子向量**（§3.1.5.1）：每个 Modifier 产出一个因子 `m`，链式应用即逐元素相乘再归一化。「列表顺序」因此退化为**因子求值的先后**，不再是可交换性的来源（可交换性由 §3.1.5.5 的判据决定）。语义上全部复用 `_redistribute_scope` 的「scope 内重分配」。

| Modifier | 语义 | 对应现有 | 触发条件 |
|----------|------|---------|---------|
| `BoostModifier(deltas, scope)` | 读 counter 算 boost% 提概率（连续提升） | SoftStepBehavior._compute_probabilities | Always（计数驱动） |
| `ForceFeaturedModifier(flag, scope)` | 标记置位 → 目标组 100% | rotating/CR guaranteed 分支 | `state[flag] == True` |
| `ForceNonFeaturedModifier(flag, scope)` | 标记置位 → 非 UP 100%（**G1 新增**） | 幻塔必歪 | `state[flag] == True` |
| `ForceSelectedModifier(flag, card)` | 标记/阈值满足 → 定轨卡（或子集）100% | targeted _resolve_selected_slots | `state[flag] or fate_ready` |
| `InterceptModifier(probs, base_rate)` | 读 streak 计数 + 掷随机数决定是否拦截为 100% UP | CR before_draw 随机分支 | 计数+随机 |
| `ThresholdForceModifier(threshold, scope)` | 计数 ≥ threshold → 强制 100% | HardPityBehavior | `counter >= threshold` |
| `BaseRatioModifier(scope)` | 按当前比例 redistribute（兜底） | rotating/targeted 默认分支 | Always |

**Modifier 链契约（强制）**：Pity 的 `before_draw` 按 `modifiers` 列表**顺序应用、非短路**，每个 Modifier 在前一个的输出上操作（因子逐元素相乘）。覆盖型 Modifier（ForceFeatured 把非目标槽位置 0）以因子 0 吸收前序调整，这正是 §3.1.5.5 吸收引理的实现对应。soft 抬高的 scope 总量在 guaranteed 下全部流入 featured，与旧 SoftPityMixin「先 soft 后事件」等价。

**分布空间归属（D20，2026-09-21 新增）**：Modifier 的输入输出是**卡级**分布（真实分布）。「槽位」是操作内部的临时聚合表示，由操作自行聚合与还原（还原即对单卡概率施加统一缩放，语义为「保持组内当前比例」）。管道不再以槽位级向量作为传输格式，`banner.py` 的 `scale_factors` 还原段随之删除。收益有三：① **单卡定向**成为可能（双 UP 池定轨、G3 的「UP 组排除已拥有」，二者本受同一约束制约）；② 消除聚合与还原的往返；③ 让 §3.1.5 的乘性算子形式直接覆盖实现。代价见 §3.1.5.4 的让步声明与 §六 的等价性口径放宽。**实施方案（改哪些函数、接口怎么变、边界怎么处理）见 §3.9**。

**InterceptModifier 随机数消耗协议（H4，强制，2026-09-16 补短路条件）**：rotating_cr 旧类 before_draw 用模块级 `random.random()`（[pity.py:576](gacha_simulator/core/pity.py#L576)、[pity.py:583](gacha_simulator/core/pity.py#L583)）做条件分支，消耗次数随分支而定。`InterceptModifier` 必须在**完全相同的条件与顺序**下消耗相同数量的随机数，否则固定种子轨迹即刻分叉。实现为**单决策 Modifier**：guaranteed 或 readonly 时不触发（返回 None）；非 guaranteed 时按 cr_base_rate / cr_state_probs 判定，命中返回 ForceFeatured 分布、未命中返回 None。等价性测试必须含 `cr_state_probs` 含 (0,1) 中间值的用例。

**短路条件（不可省略）**：旧实现两处消费均带前置短路，`self._cr_base_rate > 0 and random.random() < ...` 与 `state_prob > 0 and random.random() < state_prob`。故 `cr_base_rate == 0` 或 `state_prob == 0` 时**不消耗**随机数，`state_prob >= 1.0` 分支同样**不消耗**。若 `InterceptModifier` 写成 `if random.random() < rate`（省去 `> 0`），配 0 的场合会多消耗一个随机数、随机流整体后移。现状代码在这一点上是正确的，本条仅为实施约束。

**另三条须逐位复刻的协议内容（2026-09-16 补）**：

1. **下标裁剪**：`idx = min(cr_counter.value(), len(cr_state_probs) - 1)`（[pity.py:578](gacha_simulator/core/pity.py#L578)）须原样保留，取值下标是裁剪后的 `idx`，不是 `cr_counter` 本身。
2. **空表分支不消耗**：`cr_state_probs` 为空列表时 `idx = -1`、`if idx >= 0` 为假（[pity.py:579](gacha_simulator/core/pity.py#L579)），整段 state_prob 检查被跳过、**不消耗**随机数。这是第三条不消耗路径，短路枚举须含它。
3. **链中位置固定**：旧实现的 CR 判定发生在 soft（mixin 先算，[pity.py:529-533](gacha_simulator/core/pity.py#L529-L533)）之后、父类 `R_r` 之前，故 `InterceptModifier` 在 Modifier 链中的位置必须固定在 `BoostModifier` 之后，否则随机流位置改变。

#### 3.1.3 Lifecycle（生命周期）—— 正交包装层
| Lifecycle | 语义 | 激活维 / 退役维 | 配置来源 |
|-----------|------|---------------|---------|
| `AlwaysActive` | 永远生效 | Always / Never | 默认（两者都未配） |
| `OnceActive(max_triggers=N)` | 触发 N 次后退役（福利保底） | Always / AfterN(N) | `PityDef.max_triggers > 0` |
| `DependentActive` | 依赖另一个 Pity 激活 | Dependent / Never | `PityDef.depends_on` 非空 |
| `DependentOnceActive(max_triggers=N)` | 被激活后，触发 N 次退役 | Dependent / AfterN(N) | `depends_on` 与 `max_triggers` 同时配置 |

**两个维度正交（2026-09-28 修正）**：`activation`（`Always` / `Dependent`）× `retirement`（`Never` / `AfterN`）各二值，**四个组合全部合法**——「被谁激活」与「触发几次后退役」是两件独立的事，不存在覆盖关系。上表四个具名类是这四个组合的现成写法（维度固定为二，故不构成组合爆炸）。除 `AlwaysActive` 外，其余三个均为 P64 新增或本期接线。

Lifecycle 独立于 Tracker/Modifier，只管 `is_active` 判定和 `deactivate_on_early_hit` 统一（P64 增量能力，使事件驱动型也可用；**必须同步移除 [config_toml.py:652-660](gacha_simulator/core/config_toml.py#L652-L660) 的拒绝分支 H3**）。

<!-- REVIEW-R1-FIX: ISSUE-029 -->
<!-- REVIEW-R1-FIX: ISSUE-032 -->
<!-- REVIEW-R1-FIX: ISSUE-202 -->
**Lifecycle 协议（强制；ISSUE-029 补 `rebind`；ISSUE-202 补 `initialize`）**：`Pity` 骨架调用以下**五个**方法——`initialize(state, name)`（**构造期**写入初始 `_active`，归属论证见下段 ISSUE-202 专段）、`is_active(state, name)`（`before_draw` / `after_draw` 首行早退）、`should_deactivate(ctx, state, name)`（退役判定，**先于** `commit`，见 §3.1.4 的 ISSUE-018）、`deactivate(state, name)`（清 `_active`）、`rebind(state, name)`（重绑本生命周期持有的 `_active` Flag 到 per-call `state`；与 Tracker / Modifier 同名同义，`Pity._rebind_state` 无条件调用）。另须暴露 `deactivate_on_early_hit` 属性供 `Pity.after_draw` 判定「本次退役是否跳过重置」。三个内置 Lifecycle 均须实现这**五**个方法（无状态可空实现），`rebind` 尤其不可省——`Pity` 不设守卫。

<!-- REVIEW-R1-FIX: ISSUE-301 -->
**生命周期字段到 Lifecycle 对象的构造来源（ISSUE-301，2026-09-22 定稿，强制）**

`pdef.deactivate_on_early_hit` / `pdef.depends_on` 是两个**跨 type 共享**的字段（§1.4 第 2 条：与驱动类型无关的正交包装层，P55 只给 counter 驱动用，P64 要补到全部类型）。旧代码里它们的唯一转换点是 `create_behavior` 末尾的 `lifecycle_kwargs` 段（[pity.py:893-900](gacha_simulator/core/pity.py#L893-L900)：`params['lifecycle'] = LifecycleConfig(**lifecycle_kwargs)`），而新架构的 `Pity` 形参类型是 **Lifecycle 对象**（§3.1.4 骨架 `lifecycle: Lifecycle = AlwaysActive()`）。因此必须有且只有一处定义「参数袋 → 哪个 Lifecycle 类」的分工。若缺，实施者极易「preset 不写 `lifecycle` + 旧 `LifecycleConfig` 构造段又不删」两处各留一半，后果是**全部 `deactivate_on_early_hit` 与全部 `depends_on` 配置静默失效**——前者使 §六 的 N1 例外断言与「事件驱动型退役」断言双双不可达，后者使激活传播与「`depends_on` 引用不存在名」的 `ConfigError` 一并消失；且旧类已退役，没有任何旧实现可作对照发现。

**定稿：转换点唯一，位于 `core/pity.py` 的模块级 helper。** **落地步骤（ISSUE-GATE-3-dependency-order，2026-09-22）**：本 helper 的**定义随 S1d** 写入 `core/pity.py`（即 `AlwaysActive` / `OnceActive` / `DependentActive` 与 `LifecycleConfig` 参数袋同批落地的那一块——其依赖 S1a 的 `LifecycleConfig` 与 S1d 的三个 Lifecycle 类此时已全部就位），**S4-4 不再定义它**、只留 `lifecycle` 键的校验防线与旧 `lifecycle_kwargs` 段清理（§七 S1d / S4-4）。**不可留到 S4-4 才定义**：§3.2 / §3.3 / §3.14.2 的 preset 工厂返回 dict 已写 `lifecycle=build_lifecycle(pdef)`，而 S4-2 / S4-3 排在 S4-4 之前，S4-3 的验收命令「全部 10 个 preset 构造成功」会**实际调用**工厂（模块级名字在调用时解析），晚定义即 `NameError`。<!-- REVIEW-R1-FIX: ISSUE-GATE-3-dependency-order -->

```python
def build_lifecycle(pdef) -> Lifecycle:
    """把 PityDef 的两个生命周期字段转成 Lifecycle 对象——全库唯一转换点。"""
    cfg = LifecycleConfig(
        deactivate_on_early_hit=bool(getattr(pdef, 'deactivate_on_early_hit', False)),
        depends_on=getattr(pdef, 'depends_on', None),
    )
    # 两维独立取值（2026-09-28 修正：非「depends_on 优先」）
    _dep, _n = cfg.depends_on, getattr(pdef, 'max_triggers', 0) or 0
    if _dep and _n > 0:
        return DependentOnceActive(cfg, max_triggers=_n)
    if _dep:
        return DependentActive(cfg)
    if _n > 0:
        return OnceActive(cfg, max_triggers=_n)
    return AlwaysActive(cfg)
```

| `pdef.depends_on` | `deactivate_on_early_hit` | `build_lifecycle` 产出 | 旧路径对照（[pity.py:893-900](gacha_simulator/core/pity.py#L893-L900)） |
|---|---|---|---|
| 空 / None | False | `AlwaysActive(LifecycleConfig())` | 无 `lifecycle_kwargs`，`params` 不带 `lifecycle` 键 → behavior 落到默认 `LifecycleConfig()` |
| 空 / None | True | `AlwaysActive(LifecycleConfig(deactivate_on_early_hit=True))` | `LifecycleConfig(deactivate_on_early_hit=True)` |
| 非空 | 任意 | `DependentActive(LifecycleConfig(depends_on=…, deactivate_on_early_hit=…))` | `LifecycleConfig(depends_on=…, …)` |

三条配套纪律：

1. **`LifecycleConfig` 的去留定稿 = 保留，角色改为「Lifecycle 对象的构造参数袋」**。三个 Lifecycle 实现共用一个基类 `Lifecycle`（住 `pity_tracker.py`），基类持有 `self._cfg`；`deactivate_on_early_hit` 属性由 `self._cfg` 代理（协议要求暴露该属性，见上段），`depends_on` 由 `DependentActive` 从同一 `cfg` 读出。`core/__init__.py` 的导出面**不变**（ISSUE-025 的保留清单已含 `LifecycleConfig`），`core/pity_primitives.py` 仍承载其定义（§3.1.6 叶子层）。**旧 `create_behavior` 的 `lifecycle_kwargs` 段（:893-900）随之删除**——同一转换不得留两处。
2. **`OnceActive` / `DependentOnceActive` 的产出条件**：由 `build_lifecycle` 按两维独立取值（激活维看 `depends_on`、退役维看 `max_triggers > 0`），**两维同时配置时两者都生效**（产出 `DependentOnceActive`）。2026-09-28 修正：原稿写「`depends_on` 非空时以 `DependentActive` 优先、`max_triggers` 被忽略」——该写法把一个二维空间压成了一维三选一，与两维正交的设计相悖。
3. **调用点**：每个 preset 工厂的返回 dict 一律含 `lifecycle=build_lifecycle(pdef)`（§3.2 取值来源表已补该行；§3.2 / §3.3 / §3.14.2 的四份 preset 代码块已同步写入）。§3.1.4 骨架的 `lifecycle: Lifecycle = AlwaysActive()` 只是**兜底默认值**，不是正常路径。**三处落点的步骤分工（ISSUE-GATE-3-dependency-order）**：helper 定义在 **S1d**、`lifecycle=` 键由 **S4-2 / S4-3** 的工厂写入、旧 `lifecycle_kwargs` 段的删除与 `lifecycle` 键防线留在 **S4-4**——删除时机不可前移，S4-2 / S4-3 期间未迁移的类型仍走 `create_behavior` 旧类兼容路径、仍需该段注入 `LifecycleConfig`，提前删除会让这些类型的 `deactivate_on_early_hit` / `depends_on` 静默失效（§七 S4-4）。

**防线（禁止静默回退）**：`create_behavior` 在 `preset(pdef)` 之后**校验返回 dict 含 `lifecycle` 键**，缺失即抛 `ConfigError`（与 preset 构造失败的处置同层，§四 `core/pity.py` 行 / ISSUE-204）。若改成「缺失时静默取骨架默认 `AlwaysActive()`」，任何忘了写该键的 preset 都会让该类保底的 `deactivate_on_early_hit` / `depends_on` 全部失效且无任何报错——这正是本条要消除的失效模式。§六 已补对应断言。

<!-- REVIEW-R1-FIX: ISSUE-202 -->
**`_active` 的构造期写入归属（ISSUE-202，2026-09-22 定稿，强制）**

旧实现的这一动作在 `CounterBasedBehavior.__init__`（[pity.py:128-130](gacha_simulator/core/pity.py#L128-L130)）：

```python
self._active = Flag(state, name, "_active")
if self._lifecycle.depends_on is None:
    self._active.set()
```

新骨架若不承接它，非 `depends_on` 保底的 `_active` 恒为默认 `False`（`PityEngine.is_active` 的默认值就是 `False`，[pity.py:1369-1373](gacha_simulator/core/pity.py#L1369-L1373)），而 `_active=True` 本就靠「构造期 set + 阶段 3 快照」承载——后果是 `before_draw` / `after_draw` 首行**双双早退**，**全部计数型保底静默失效**（M1 等价性会报错，但定位成本高，且 §3.1.3 的协议表会被当成权威依据）。

**归属定稿**：写入动作由 **Lifecycle 协议新增的 `initialize(state, name)`** 承担，而不是留在 `Pity.__init__`——`_active` Flag 本就由 Lifecycle 持有（`rebind` 重绑它、`deactivate` 清它），构造期写入归同一持有者，`Pity` 不必按 `btype` 分叉。

| Lifecycle | `initialize(state, name)` |
|-----------|---------------------------|
| `AlwaysActive` | 写 `_active = True`（对应旧 `depends_on is None` 分支） |
| `OnceActive(max_triggers=N)` | 写 `_active = True`（首触发前生效，与 `AlwaysActive` 同） |
| `DependentActive(depends_on=…)` | 空实现（激活由引擎的 `depends_on` 传播写入，[pity.py:1342](gacha_simulator/core/pity.py#L1342)） |

`Pity.__init__` 在创建 `_view` **之前**调用 `self._lifecycle.initialize(state, self._name)`（§3.1.4 骨架那行注释已改写为真实调用）。

**快照面的裁决（2026-09-22 第八轮定稿，原为 ⚠ 待人工裁决）**：旧实现中事件驱动型（`rotating` / `targeted` / `rotating_cr` 及两个 `_soft` 复合）**不写** `_active`，统一写入后其命名空间会**新增一个 `_active: True` 键**。这与 §六 主线「状态快照与旧类逐场完全一致」的字面口径冲突，两条路线择一。**取路线 ①（原推荐项）**：

1. **统一写入（采用）**：保留 `initialize` 的统一写入，并把「事件驱动型命名空间多一个 `_active: True` 键」登记为 S1 至 S5 的**已知差异**。理由：与 §3.5「`deactivate_on_early_hit` 对事件驱动型可用」的能力目标一致，且 §六 已有同型的 `_soft` 命名空间先例。对应断言与风险行已分别落在 §六 与 §五。<!-- REVIEW-R1-FIX: ISSUE-GATE-risk-mitigation -->
2. ~~备选：`initialize` 改为**仅计数驱动型**写入（`AlwaysActive` 须按 `btype` 判定）~~（**已否决**）：代价是把分类分支重新引入 Lifecycle、与「统一骨架」的取向相悖，且会让「事件驱动型的 `deactivate_on_early_hit`」失去 `_active` 载体，与 §3.5 的增量能力目标直接冲突。

**实施者按 ① 落笔，S3 开工前不再需要二次决策**；§六 对应断言的备选分支已删除。

**`OnceActive` 的配置层落点（ISSUE-032，2026-09-27 用户裁决：本期接线）**：`OnceActive(max_triggers=N)` 的配置接线**纳入本期范围**（原 2026-09-22 第八轮定稿为「只实现类、不做配置接线」，2026-09-27 用户否决该定稿）。

**为什么它本该有配置**：`max_triggers`（触发 N 次后退役）是 Lifecycle 的**基本能力**——旧实现里 `deactivate_on_early_hit` 就是它在 N=1 时的特例（[pity.py:329-337](gacha_simulator/core/pity.py#L329-L337) 与 [pity.py:405-413](gacha_simulator/core/pity.py#L405-L413) 两处 `_active.clear()` 后返回 True、跳过 counter 重置）。把次数上限做成可配置的 N 是能力完备性的自然要求；只实现类而不给配置入口，等于该能力对用户不可见。手册 G5 的 `hard(max_triggers=1)`（[手册:554](docs/主流抽卡游戏卡池机制配置转换手册.md#L554)）正是它的真实用例，当前只是散写、无字段承载。

**连带改动（四处，均已登记进 §四 与 §七）**：

1. **`PityDef` 新增 `max_triggers: int = 0`**（0 = 不限，与 `MilestoneDef.max_triggers` 的零值约定一致）——`core/config_store.py`
2. **`config_toml` 解析与该键 round-trip**（`_build_pity` 读取 + `_pitydef_to_toml` 写回）；范围校验：负值抛 `ConfigError`（防「写了 -1 却静默当 0」）
3. **`build_lifecycle(pdef)` 按两个正交维度独立取值**：激活维 = `depends_on` 非空 ? `Dependent` : `Always`；退役维 = `max_triggers > 0` ? `AfterN(n)` : `Never`。**两维同时配置时两者都生效**（产出 `DependentOnceActive`）。配置来源：激活维取 `PityDef.depends_on`、退役维取 `PityDef.max_triggers`（0 = 不限）。**2026-09-28 修正**：原稿写「`depends_on` 优先、`max_triggers` 被忽略」是错的——「被谁激活」与「触发几次后退役」互不干涉，不存在覆盖关系
4. **`gui/config_panel.py` 新增「触发次数上限」数值控件**（0 = 不限），与既有 pity 编辑区同列；`_apply_pity_edit` 与 load/save 路径同步该键

**验收**见 §六 与 §七（`PityDef(max_triggers=2)` 经 `build_lifecycle` 产出 `OnceActive`；TOML round-trip 保留；GUI 编辑→保存→重载一致；触发 N 次后 `is_active` 为假；`depends_on` 优先；负值抛 `ConfigError`）。<!-- REVIEW-R1-FIX: ISSUE-032 -->

**`is_active` 早退对事件驱动型是行为变更（2026-09-16 补，须与等价性范围显式隔离）**：旧实现中只有 `CounterBasedBehavior` 读写 `_active`（[pity.py:180](gacha_simulator/core/pity.py#L180)、[pity.py:190](gacha_simulator/core/pity.py#L190)），`RotatingBehavior` / `TargetedBehavior` **完全不读它**；而引擎的 depends_on 传播会**写** `_active`（[pity.py:1342](gacha_simulator/core/pity.py#L1342)）。即旧实现里「事件驱动型配了 `depends_on`」是**惰性**的：标志被写入但无人读，`before_draw` / `after_draw` 照常执行。

§3.1.4 骨架在 `before_draw` / `after_draw` 首行统一做 `is_active` 早退，会让这类配置**真正生效**（未激活前不改分布、不更新状态）。这是概率流改变，不是「只收严」，故：

- 属 P64 增量能力，须**单独验收**（判据：配 `depends_on` 的事件驱动型，激活前 `before_draw` 返回原分布、`after_draw` 不更新状态）
- 等价性验收须**显式排除**「事件驱动型 + `depends_on`」这类配置，否则与 N1/M4 的等价性主张冲突

#### 3.1.4 统一 Pity 骨架

<!-- REVIEW-R1-FIX: ISSUE-001 -->
<!-- REVIEW-R1-FIX: ISSUE-004 -->
<!-- REVIEW-R1-FIX: ISSUE-018 -->
<!-- REVIEW-R1-FIX: ISSUE-019 -->
<!-- REVIEW-R1-FIX: ISSUE-024 -->
<!-- REVIEW-R1-FIX: ISSUE-029 -->
<!-- REVIEW-R1-FIX: ISSUE-033 -->
<!-- REVIEW-R1-FIX: ISSUE-202 -->
```python
class Pity(PityBehavior):
    """统一保底骨架——Tracker + Modifier + Lifecycle 三元组。"""
    def __init__(self, *, name, state, scope, btype,
                 trackers: List[Tracker],
                 modifiers: List[Modifier],
                 lifecycle: Lifecycle = AlwaysActive(),
                 priority: int = 0,
                 pools: tuple = ('*',),         # ← ISSUE-019：供 _build_activation_graph 池交集校验
                 reads: tuple = (),             # ← ISSUE-033：由 PityDef.reads 注入，供
                                                #   PityEngine.get_reads_for_pool() 汇总（§3.10.2）
                 flags: Optional[dict] = None,  # ← AUDIT-BREAK-3：preset 返回 dict 的 `flags` 键在此
                 counters: Optional[dict] = None):  # 消费；`counters` 同理（键集与写入规则见下）
        self._name = name; self._state = state
        self._reads = reads
        self._scope = scope; self._btype = btype
        self._priority = priority
        self._pools = pools
        self._trackers = trackers; self._modifiers = modifiers
        self._lifecycle = lifecycle
        # ← ISSUE-001：**不得写死 is_event_driven**。三个分类标志继续由 btype 推导，
        #   与 CounterBasedBehavior.__init__（pity.py:132-137）同源。写死会让
        #   _validate_behaviors（pity.py:933-985）的规则 2/3/4（is_hard → is_event_driven
        #   → is_soft 的 elif 链）全部落到「事件驱动型」分支：soft_interval + soft_additive
        #   同 scope 由「通过」变「抛 ConfigError」，rotating + hard 同 scope 被拒
        #   （正是 G5 绝区零 hard(max_triggers=1) 与 targeted 同 scope 的形态），
        #   规则 2「同 scope 两硬保底互斥」同时静默失效。§3.2 的「逻辑零改动」以此为前提。
        # ← ISSUE-024：`_SOFT_TYPES` / `_HARD_TYPES` / `_EVENT_DRIVEN_TYPES` 现状是
        #   CounterBasedBehavior 的**类属性**（实测 [pity.py:114-115](gacha_simulator/core/pity.py#L114-L115)，
        #   `_SOFT_TYPES` / `_HARD_TYPES` 分别在 :112 / :113），模块级无同名对象；
        #   `Pity(PityBehavior)` 不继承该基类，写裸名会立即 NameError。
        #   归属定稿：三个集合随叶子原语层迁至 pity_primitives.py 成为**模块级常量**，
        #   由 pity_primitives 导入（§3.1.6 表已登记，§四 `core/pity_primitives.py` 行已补）。
        self.is_soft = btype in _SOFT_TYPES
        self.is_hard = btype in _HARD_TYPES
        self.is_event_driven = btype in _EVENT_DRIVEN_TYPES
        # 状态键由各 Tracker 声明，Pity 统一创建 Flag/Counter 遥控器
        # ← ISSUE-202：构造期写入 _active 有归属方法，不得只留注释。
        #   AlwaysActive / OnceActive 在其中写 _active = True，DependentActive 为空实现
        #   （激活由引擎 depends_on 传播写）。漏掉即非 depends_on 保底 _active 恒 False、
        #   before_draw / after_draw 首行双双早退，全部计数型保底静默失效（§3.1.3）。
        self._lifecycle.initialize(state, name)   # ← ISSUE-202，须先于 _view 创建
        # ← ISSUE-004：随 state 重建，见 _rebind_state。
        # ← ISSUE-GATE-dependency-order：StateView **自 S3 起**即在本文件落一个薄版
        #   （get 直取 state.data.get(name, {})，定义见 §3.10.3），S9 才把 name 之外的读取
        #   切断并接入 Modifier 的 view 形参——故本行不是「引用未定义符号」。
        #   声明了 `namespace` 的零件由 Pity 另建 view（§3.10.3 定稿），本行是**默认 view**。
        self._view = StateView(state, name)
        # ← AUDIT-BREAK-3：preset 返回 dict 的 `flags` / `counters` 两键由此处**消费**
        #   （此前全计划无任何消费者：原样 `**preset` 展开进 Pity(...) 即 TypeError，
        #   不展开则两键成死代码，并与 _build_pity_state_init 并存为第二初始值机制）。
        #   写入规则与 §3.1.1 的 L4 键集语义一致——**仅 truthy 才预建键**（对齐
        #   _build_pity_state_init 的 `if cv:`，[pity.py:1005-1011]），故与引擎侧的
        #   env.pity_state_init 快照（阶段 3）幂等同值，不引入第二套初值口径。
        #   写入点必须在 _lifecycle.initialize 之后（_active 由 Lifecycle 负责，不在此列）。
        for _k, _v in (flags or {}).items():
            if _v:
                state.set(name, _k, _v)
        for _k, _v in (counters or {}).items():
            if _v:
                state.set(name, _k, _v)

    def _rebind_state(self, state):          # P75 纪律——统一实现
        self._state = state
        for tr in self._trackers: tr.rebind(state, self._name)
        for mod in self._modifiers: mod.rebind(state, self._name)
        self._lifecycle.rebind(state, self._name)
        # ← ISSUE-004：view 必须随 state 重建。worker 内同一 engine 被 N 次模拟复用，
        #   跨模拟隔离唯一靠 rebind；view 若只在构造期建一次，第 2..N 场读的仍是旧账本。
        self._view = StateView(state, self._name)   # 默认 view；零件命名空间 view 同批重建（§3.10.3）

    def before_draw(self, ctx, readonly=False):
        if not self._lifecycle.is_active(self._state, self._name):
            return ctx.current.copy()
        for tr in self._trackers:            # N1：计数型先在 before 侧推进
            tr.advance(ctx, self._state, self._name, readonly=readonly)
        out = ctx.current.copy()
        for mod in self._modifiers:
            nxt = mod.apply(ctx, self._view, out, readonly)
            if nxt is not None:
                out = nxt                    # 链式应用（非短路）；S8 后即因子逐元素相乘
        return out

    def after_draw(self, ctx):
        if not self._lifecycle.is_active(self._state, self._name):
            return
        # ← ISSUE-018：退役判定必须【先于】commit。旧实现在 after_draw 里先判
        #   _should_reset，再调 _on_reset（deactivate_on_early_hit 时清 _active 并
        #   return True），命中则提前 return 跳过 _counter().reset()
        #   （pity.py:189-198 与 :329-337 / :405-413）。若写成「先 commit 后 deactivate」，
        #   counter 会被无条件归零，与 §3.1.1 的例外段、§六 的 N1 例外断言三者相悖。
        retire = self._lifecycle.should_deactivate(ctx, self._state, self._name)
        if retire:
            self._lifecycle.deactivate(self._state, self._name)
        # 仅 deactivate_on_early_hit 触发的退役跳过重置；其余退役动作（如触发次数用尽）
        # 不改变 commit 语义，counter 照常归零。
        skip_reset = retire and self._lifecycle.deactivate_on_early_hit
        for tr in self._trackers:            # N1：此处只落重置/翻转/累积
            tr.commit(ctx, self._state, self._name, skip_reset=skip_reset)

    def did_fire(self, ctx):
        # M4：统一为「本次抽卡是否让本保底回到初始状态」
        return any(tr.did_reset(ctx, self._state, self._name) for tr in self._trackers)
```

<!-- REVIEW-R1-FIX: AUDIT-BREAK-2 -->
**骨架形参与 `create_behavior` 两处注入点的接口对齐（AUDIT-BREAK-2，强制，⚠ 待人工裁决：备选方案见末条）**

问题：`create_behavior` 现有两条注入——`if getattr(pdef,'target_featured',False): params['target_featured']=True`（[pity.py:877-878](gacha_simulator/core/pity.py#L877-L878)）与 `if getattr(pdef,'reset',None): params['reset']=pdef.reset`（[pity.py:879-880](gacha_simulator/core/pity.py#L879-L880)），末行以 `cls(name=…, state=…, scope=…, **params)`（[pity.py:902](gacha_simulator/core/pity.py#L902)）落构造。本骨架的 `Pity.__init__` 是 keyword-only 且**不含 `target_featured` / `reset` 形参**，preset 分支若沿同一调用形式即 `TypeError: unexpected keyword argument`——而该异常恰好被 S4-5 的构造兜底包住（§3.1 附近的 `try/except` → 改抛 `ConfigError` 前为 `logger.warning` 后跳过），后果是**保底静默缺失**而非崩溃，与 ISSUE-204 同一失效面。

定稿（保守方案 = 分支隔离，不改骨架签名）：

1. **preset 分支不得走 `cls(**params)`**。两处注入**只服务于旧类兼容分支**——旧基类 `CounterBasedBehavior.__init__` 有 `reset` / `target_featured` 形参（[pity.py:130-131](gacha_simulator/core/pity.py#L130-L131)），preset 分支按 §3.2 的「三必需键 + 两可选键」显式构造，**不传 `params`**（§3.2 已补构造代码与键集校验）。
2. **这两个配置值在 preset 路径的消费点在工厂内部**：`CounterTracker(reset_on=pdef.reset or pdef.scope)`（§3.2 取值来源表）、`target_featured` 决定 `judge="featured"`（§3.2 rotating 行）。故「删除注入」不丢能力，语义完全由工厂承接。
3. **旧类兼容分支与其 `params` 组装段随「发布前一次性移除旧类」一并删除**（GATE-5 末条）；届时 `params` dict 整体消失，本条的接口面收窄为「preset 分支唯一构造点」。S4-1 落地时须在两处注入外加注释标明「仅旧类分支」，避免后来者按 `cls(**params)` 复制到 preset 分支。
4. **§六 断言行**（已补）：preset 化的 type 经 `create_behavior(PityDef(name='x', btype='hard', reset='never'), state)` 返回 `Pity` 且**不抛 TypeError**；断言 `Pity.__init__` 不接受 `target_featured` / `reset`（`inspect.signature` 检查），使「有人把注入点接回 preset 分支」在测试期即失败。

**⚠ 待人工裁决（备选，未采用）**：在 `Pity.__init__` 保留 `target_featured: bool = False` / `reset: Optional[str] = None` 两个形参并吸收注入。否决理由：这两个值在 Tracker/Modifier 分解后已无骨架级语义（重置规则属 `CounterTracker.reset_on`，featured 判定属 `judge`），保留即为「收了不用的死形参」，且与 ISSUE-030「逐条可配值一律取自 `pdef`、由工厂消费」的口径冲突。若人工改选本备选，须同步 §3.2 取值来源表与 S4-2 的构造代码。

<!-- REVIEW-R1-FIX: AUDIT-BREAK-3 -->
**preset 返回 dict 的键集与其消费者（AUDIT-BREAK-3，强制，⚠ 待人工裁决：备选方案见末条）**

原稿缺陷：§3.2 / §3.3 / §3.14.2 的 preset 示例返回含 `flags={...}` / `counters={...}`（[行 693](#)/[706](#)/[720](#)/[763](#)/[1402](#)），但 `Pity.__init__` 无对应形参、全计划也**无任何声明的消费者**——原样 `**preset` 展开即 `TypeError`；不展开则两键成死代码，并与 `_build_pity_state_init` 并存为**第二初始值机制**。更隐蔽的是：S4-2 的验收断言是 `{'trackers','modifiers','lifecycle'} <= set(x)` 的**子集**判断（§七），不拒绝多余键，故该缺陷在 S4-2 / S4-3 的验收命令下**完全不可见**。

定稿（保守方案 = 保留键 + 就地定义消费者，与「初值走状态声明（H2）」的原设计一致）：

1. **键集 = 恰好 5 键**：`trackers` / `modifiers` / `lifecycle`（**必需**）+ `flags` / `counters`（**可选**，缺省 `{}`）。§3.2 的示例代码保持原样（`flags={"guaranteed": pdef.guaranteed_init}` 等），不再删除——它们的消费者就是本骨架新增的 `flags` / `counters` 形参。
2. **消费者 = `Pity.__init__` 的 `flags` / `counters` 形参**（本骨架代码已写入），构造期按 **L4 truthy 规则**写入 `state`（仅 truthy 才 `state.set`），与 `_build_pity_state_init` 的 `if cv:` 口径同源、幂等同值。
3. **构造形式 = 按名取键，禁止 `**` 直展开**（S4-1 落地）：`create_behavior` 从 preset 返回 dict 中显式取这 5 个键传给 `Pity`，**未声明的键抛 `ConfigError`**。这条同时是防「未来新增键静默成死代码」的闸门——它与 `_validate_registry()` 的必需键校验（ISSUE-301）是**两道不同的校验**，前者查漏（必需键缺）、后者查多（未知键）。
4. **验收口径修正**（§七 S4-2 / S4-3 与 §六 已同步）：断言由子集判断改为**恰好键集** `set(x) == {'trackers','modifiers','lifecycle','flags','counters'}`（缺省时后两键可以是缺省而非显式空 dict，故实现可写 `{'trackers','modifiers','lifecycle'} <= set(x) <= 五键全集`），并**追加一条消费者断言**：`guaranteed_init=True` / `counter_init=5` 的配置经 preset 构造后，`state.get(name,'guaranteed')` / `state.get(name,'counter')` 已按 truthy 规则写入（否则「声明了初值但没人读」这一失效模式仍然不可见）。

**⚠ 待人工裁决（备选，未采用）**：删除 preset 返回 dict 的 `flags` / `counters` 两键，初值一律由 `CounterTracker(init=…)` 承载、`guaranteed` 初值改由 `FlagTracker` 加 `init=` 形参承载。否决理由：`FlagTracker` 定稿签名是四参 `(judge, hit, miss, flag)`（§3.1.1 ISSUE-104），加 `init=` 属签名扩张；且 §3.1.1 已把「初值」定义为**状态声明**而非 Tracker 形参（`_preset_rotating` 的注释「初值走状态声明（H2），不加 Tracker 形参」即此意）。若人工改选本备选，须同步 §3.1.1 的 Tracker 签名表、§3.2 的三个示例与取值来源表。

### 3.1.5 形式化：表达力与顺序判据（2026-09-21 乘法因子版重写）

> **本节定位**：描述 **S8 完成后**架构的数学形态（卡级分布 + 乘性因子向量）。S1–S5 期间的 Modifier 内部实现沿用槽位法（与旧类逐位一致，等价性由 §六 实测保证）；S8 把算子实现切换为因子法后，本节直接覆盖实现。
>
> **重写理由（2026-09-21）**：原版以槽位空间上的三个基本算子 `{B, R, F}` 为基底，与「概率操作统一为卡级乘性因子」这一目标形态不同构；原引理 2.1/2.2/2.3 描述的多是槽位结构的偶然性质（如「单槽位使组内重写退化」），在卡级管道下不再成立。乘法版把可交换性判据压缩为一条复合律加一条吸收引理，判据从「逐条引理」变为「逐元素比较因子」。

#### 3.1.5.1 定义：乘性算子

一次抽卡有 n 个互斥结果（实现里即池中的卡，或等价地槽位）。所有概率分布构成单纯形

```
Δⁿ⁻¹ = { p ∈ Rⁿ : pᵢ ≥ 0, Σᵢ pᵢ = 1 }
```

**乘性算子**由一个因子向量 m ∈ Rⁿ（m ≥ 0 逐元素）定义：

```
Φ_m(p) = (m ⊙ p) / ⟨m, p⟩,     其中  ⟨m, p⟩ = Σᵢ mᵢ pᵢ
```

即「逐元素乘因子，再归一化」。它把「概率操作」从『分布到分布的任意映射』收缩为『用一个非负向量调制分布』，这是本节全部论证的基础。

**性质 1（对数坐标）**：log Φ_m(p) = log p + log m − log⟨m,p⟩。乘性算子在 log 空间是**加性平移再归一化**，即指数族的自然参数平移。

**性质 2（良定义条件）**：⟨m, p⟩ > 0 当且仅当 m 在 p 的支撑上不全为零。这是本形式化唯一的边界来源，见 3.1.5.6。

#### 3.1.5.2 三个基本算子的因子形式

记 scope 为 S，目标集 T ⊆ S，`p(A) = Σ_{c∈A} p_c`，`P = p(S)`。

| 算子 | 语义 | 因子 m_c |
|------|------|---------|
| `R_r(T)` | scope 内重分配，使 T 占 scope 总量的比例恰为 r，scope 总量不变 | c ∈ T：`rP / p(T)`；c ∈ S\T：`(1−r)P / (P − p(T))`；其余：1 |
| `F(T)` | **全池置零**后 T 占满 scope，**更高稀有度槽位还原原值** | c ∈ T：`P / p(T)`；c ∈ S\T：0；**更高稀有度槽：1**（还原）；**更低稀有度槽：0** |
| `B_β(T; Q)` | 从源集 Q 取比例 β，按 p 比例转给 T | c ∈ T：`1 + β·p(Q)/p(T)`；c ∈ Q：`1 − β`；其余：1 |

**归一化系数 ⟨m,p⟩ 的取值（逐项验算，2026-09-21 独立审查修正）**：`R_r` 与 `B_β` 在 `T ⊊ S`、`T ∩ Q = ∅` 时恒为 1；`F` 恒为 `P + p(更高稀有度)`，仅当 scope 为最高稀有度时等于 1（这正是 `HardPityBehavior` 保留高层级槽位的效果）。

三者都只需 `Φ_m` 的归一化即可正确落地，故 ⟨m,p⟩ 是否等于 1 **不影响正确性**；但「复合时无须归一化、可直接相乘」这一便利只在 ⟨m,p⟩ = 1 时成立。旧算子的 ⟨m,p⟩ = 1 主要源于其设计本就保持全局概率和为 1。

**与旧实现的对应**：`R_r` 由 `_redistribute_scope(ctx, r, ...)` 实现；`F` 由 `HardPityBehavior._compute_probabilities` 实现；`B_β` 由 `SoftStepBehavior._compute_probabilities` 实现。

**基底的完备性**：还须计入恒等元 `id`（m ≡ 1）。所有早退路径（`counter < τ`、`pool <= 0`、`scope_slots` 为空、featured 槽位为空等）返回的都是恒等元。

**组内比例的语义（关键）**：`R_r(T)` 的因子在 T 内**是常数**（T 内所有 c 乘同一个数），等价于「**保持组内当前比例**」。而旧实现在目标槽内按**基础权重 w** 重写。两者在「组内比例 = 基础权重比例」时数值相同，一旦存在卡级定向（如 targeted 锁定单卡）就分开。S8 采用**保持当前比例**语义，理由见 3.1.5.3 与 3.1.5.4。

#### 3.1.5.3 复合律与顺序敏感的两类来源

**复合律**：

```
Φ_{m₂}(Φ_{m₁}(p)) = (m₁ ⊙ m₂ ⊙ p) / ⟨m₁ ⊙ m₂, p⟩      （m₂ 在 Φ_{m₁}(p) 处取值）
```

**判据的正确用法（2026-09-21 审查修正）**：可交换性**不能**由「因子是否依赖分布」直接判定——`B_β` 的因子含 `p(Q)/p(T)`（依赖当前分布），却与同类可交换（§3.1.5.5 推论表第 1 行）。唯一可用的判据是**逐元素比较两种顺序下的因子乘积**（吸收引理为其特例）。因子依赖分布只是「**可能**不可交换」的来源：它使 `m₂` 的求值点随顺序改变，是否真的改变乘积须逐元素验证。

**顺序敏感的两类来源（2026-09-21 定性）**：

| 类型 | 例子 | 性质 |
|------|------|------|
| **约束冲突（语义）** | `soft(target_featured=True)` 与 `hard` 共存 | 两个算子对同一 scope 的约束无法同时满足，顺序即裁决方式。**这是语义正确的表现**，不是缺陷 |
| **随机数消费（实现）** | 含 `rotating_cr` 的配置 | 因子本身可交换，但 `InterceptModifier` 消费全局 `random`，换序导致随机流错位。数学上若随机源独立则无影响，它只影响固定种子下的可复现性与样本路径。**这是实现绑定的副作用** |

对第一类，正规处置是**显式定义组合语义**（当前为顺序执行 + §1.5 裁决的 `priority` 覆盖），而非消除敏感。另有一种理论上可行的替代语义是**约束求解**（把每个保底写成对分布的约束，求解满足全部约束的分布），它能彻底消除顺序敏感且冲突时较严约束自然胜出，代价是每个算子都须能写成约束形式（带随机拦截的 `rotating_cr` 写不了），且求解远比顺序应用昂贵。当前采用顺序执行是工程上的取舍。

#### 3.1.5.4 定理 1（表达力包含）

**命题**：在组内比例不变式

```
p_c / p(C_s) = w_c / w(C_s)      （对每个槽 s 及其卡集 C_s）
```

成立的前提下，旧 10 类的每个概率算子都等价于三个基本乘性算子的有限复合；每个状态转移 T 都是条件赋值语句的有限复合。

**证明**（构造性）：

| 类型 | 概率算子 | 状态转移 T |
|------|---------|-----------|
| `soft_step` | `B_β(T)` | 出 scope 时 `counter ← 0` |
| `hard` | `F(T)`（触发时），否则 `id` | 同上 |
| `rotating` | `R_r(S_f)`，r = 1 若 guaranteed，否则 `p(S_f)/p(S_c)` | 出 scope 时 `guaranteed ← is_featured` |
| `rotating_cr` | 命中 ? `R_1(S_f)` : `R_r(S_f)` | 父类 + 出 scope 且 ¬was_g 时 `cr ← is_featured ? 0 : cr+1` |
| `targeted` | （guaranteed 或 fate 就绪）? `R_1(T_sel)` : `R_r(S_f)` | 命中定轨卡时四键清零，否则四键累积 |
| 各 `_soft` | 父算子 ∘ `B_β` | 父类 T 加 counter 清零 |

每个算子长度不超过 2；每个 T 只含条件赋值，无循环、无跨调用内存。

**唯一须显式声明的让步**：旧算子在目标组内按**基础权重**重写，乘性算子在目标组内按**当前比例**缩放，两者仅在不变量成立时数值相同。故本定理是「**不变式下包含**」，而非原版的「严格包含」。代价换来的是 3.1.5.3 的复合律，以及卡级定向（targeted 锁定单卡、G3 从 UP 组排除已拥有）的表达能力。

> **`rotating_cr` 的命中分支是 `R_1` 而非 `F`**（2026-09-16 核对结论，乘法版沿用）：它由 `_force_featured`（[pity.py:586-589](gacha_simulator/core/pity.py#L586-L589)）实现，内部调 `_redistribute_scope(ctx, 1.0, ...)`，只把 scope 内总量给 featured、scope 外原样保留。实测同一输入（0.5 / 0.5 / 0.08 / 0.9）下 `_force_featured` 得 {ssr_featured: 0.02, ssr: 0, sr: 0.08, r: 0.9}，`F(S_f)` 得 {ssr_featured: 1.0, ssr: 0, sr: 0, r: 0}。结论不因此改变（`R_1 ∈ {R}`），但构造表须按 `R_1` 记。

**效力**：本定理证的是**表达力包含**（存在一个 preset 表达旧行为），不保证实现出的 preset 与旧代码位级一致（浮点运算顺序差异），后者由等价性测试承担。

#### 3.1.5.5 定理 2（可交换性判据）

由 3.1.5.3 的复合律，可交换性判定归结为**逐元素比较两个顺序下的因子乘积**；实践中只需一条引理：

**吸收引理**：若算子 `Φ_m` 在某集合 U 上取 `m|_U = 0`，则任何**先于**它作用的算子在 U 上的因子都被吸收（乘 0 得 0），故复合在 U 上可交换且结果恒为 0。

**推论表**（重算版）：

| 组合 | 可交换 | 依据 |
|------|-------|------|
| soft + soft（同 scope，同目标集） | 是 | `B_β` 的因子在源集上为常数 `1−β`，相乘可交换；复合等价于 `B_{1−(1−β₁)(1−β₂)}` |
| soft + soft（同 scope，异目标集） | 是 | 实测 200 组无反例。两算子目标集不同，但不互相写入对方的源集，逐元素相乘顺序无关 |
| soft + soft（异 scope） | 是 | 低稀有度算子的源集与目标集都落在高稀有度算子的源集之内 |
| soft(T_soft = S) + hard | 是 | **2026-09-21 审查修正**：soft 的目标集等于整个 scope 时其源集为空（[pity.py:299-300](gacha_simulator/core/pity.py#L299-L300) 的 `if not non_target: return result`），`B` 退化为恒等，可交换性**平凡成立**。原论证「`F` 在源集 Q 上取 0，由吸收引理」中的 T 只能是 hard 的目标集，与行标签的 T（soft 的目标集）不是同一个集合，属指代冲突 |
| **soft(target_featured=True) + hard** | **否** | `F` 的零点集是 `S \ T`，而 T 收窄为 featured 后该集合**仍然有量**（非 featured 的 standard 槽），`B` 在那里仍能取量，吸收引理前提不满足 |
| 含 `rotating_cr` 的组合 | 否 | 非代数问题：因子本身可交换，但 `InterceptModifier` 消费全局 `random`，换序导致 ω 消费位置改变、样本路径分叉 |

**反例实测（2026-09-16，对 P82 §六 结论的修正；乘法版结论不变）**：soft(`target_featured=True`，deltas 使第 6 抽起 boost) + hard(threshold=8)，两种 `pity_names` 顺序，12 抽概率序列对比：

```
target_featured=False  顺序敏感抽数 = []                    （与 P82 结论一致）
target_featured=True   顺序敏感抽数 = [8, 9, 10, 11, 12]     （反例）

第 8 抽（hard 触发那一抽）：
  [soft, hard] = {'sr': 0.0, 'ssr': 0.5, 'ssr_featured': 0.5}
  [hard, soft] = {'sr': 0.0, 'ssr': 0.2, 'ssr_featured': 0.8}
```

**故 P82 的「仅含 `rotating_cr` 的配置会变」应修正为「含 `rotating_cr`，或 `target_featured=True` 的 soft 与 hard 共存的配置会变」。**

**原引理 2.3 的处置**：原版引理 2.3 称「在当前槽位结构下，参数取『保持当前比例』的 `R` 是恒等映射，原因是单槽位使组内重写退化」。乘法版下该引理**不再需要**：`R_r(T)` 的因子在 T 内是常数、在 `S\T` 内也是常数，当 r 取「当前比例」时两个常数均为 1，恒等性直接由因子读出，无须借助槽位结构。

#### 3.1.5.6 未覆盖（边界）

| 项 | 为何只能测 / 说明 |
|----|-----------|
| 位级一致 | 定理 1 保证构造存在，不保证浮点运算顺序一致；卡级管道下聚合次数随算子数增加，差异量级仍在 1e-16，但 §六 的等价性口径须由「完全一致」放宽为「容差内一致」 |
| 随机数消费次数 | 可证，但需先把 H4 的短路条件写死，再把 ω 显式化为消费序列逐位比对 |
| 全配置组合 | 组合空间过大，采样测试只覆盖有限点；本节的判据用于缩小「必须实测」的范围 |
| **因子在 p 的支撑上全为零** | 由性质 2，此时 `Φ_m` 未定义（⟨m,p⟩ = 0）。语义上这是「提升一个概率为零的集合」，物理上不应发生（保底不作用于零概率组）。实现约定：返回原分布，与现行早退路径一致 |
| **`p(T) = 0`（目标组当前无概率）** | 因子 `P/p(T)` 除零**发散**——与上一行方向相反（不是全零而是无穷），`F` 与 `R` 均受影响，实测抛 `ZeroDivisionError`。由 §3.9.5 的 `T == 0` 分支处理（返回恒等） |
| **`T = S` 且 `r < 1`** | `S\T` 为空，⟨m,p⟩ = 1 − (1−r)·P ≠ 1。§3.1.5.5 推论表的 `soft(T = S)` 一行即此情形，其可交换性论证须按此重述 |
| **`B_β` 的 `T ∩ Q ≠ ∅`** | 因子的三项推导依赖 T 与源集不交；当前实现源集取「非目标集」故不交成立（[pity.py:295-302](gacha_simulator/core/pity.py#L295-L302)），但这是**隐含前提**，须显式声明 |
| 约束求解语义 | 3.1.5.3 提到的替代组合语义未实现，其表达力与代价未评估 |

<!-- REVIEW-R1-FIX: ISSUE-002 -->
#### 3.1.6 模块归属与依赖方向（ISSUE-002，强制）

三个新模块（`pity_tracker.py` / `pity_modifier.py` / `pity_condition.py`）必须消费 `Counter` / `Flag`（[pity.py:41-79](gacha_simulator/core/pity.py#L41-L79)）、`PityState`（[pity.py:1085](gacha_simulator/core/pity.py#L1085)）、`PityContext` / `DrawInfo`（[pity.py:31](gacha_simulator/core/pity.py#L31) / [pity.py:14](gacha_simulator/core/pity.py#L14)）、`LifecycleConfig`（[pity.py:80](gacha_simulator/core/pity.py#L80)）；而 `pity.py` 又必须反向依赖新模块（Pity 骨架、preset 工厂、registry 条目、`create_behavior` 双路径）。**直接的双向模块级 import 会构成循环导入**，故指定依赖方向如下（否则 S1 一开工就要临场改架构）：

| 层 | 模块 | 承载 | 依赖方向 |
|----|------|------|---------|
| **叶子（原语层）** | `core/pity_primitives.py`（**新增**） | `Counter` / `Flag` / `PityState` / `DrawInfo` / `PityContext` / `LifecycleConfig` + 卡级重分配原语 `factor_redistribute`（§3.9.4）+ **类型集合常量 `_SOFT_TYPES` / `_HARD_TYPES` / `_EVENT_DRIVEN_TYPES`**（ISSUE-024：自 `CounterBasedBehavior` 的类属性升为模块级常量，供 §3.1.4 骨架的 `Pity` 使用；**ISSUE-105：`_EVENT_DRIVEN_TYPES` 的内容须追加 `rotating_inverse`，不是原样迁移**） | 仅依赖标准库 | <!-- REVIEW-R1-FIX: ISSUE-024 -->
| 实现层 | `core/pity_tracker.py` / `core/pity_modifier.py` / `core/pity_condition.py` | Tracker 家族 + Lifecycle / Modifier 家族 / Condition 家族 | **单向**依赖 `pity_primitives`，不 import `pity` |
| 编排层 | `core/pity.py` | `Pity` 骨架、`PityEngine`、`BEHAVIOR_REGISTRY`、preset 工厂、`build_lifecycle`（**ISSUE-301**：`PityDef` → Lifecycle 对象的唯一转换点，与 preset 工厂同住一处，见 §3.1.3）、`create_behavior`、`StateView`（**S3 落薄版 / S9 收紧**，定义见 §3.10.3；**ISSUE-034：本行是其归属登记**，`Pity` 骨架与 `PityEngine` 的 `reads` 访问器同住此处） | 依赖 `pity_primitives` + 三个实现层模块 | <!-- REVIEW-R1-FIX: ISSUE-034 --> <!-- REVIEW-R1-FIX: ISSUE-301 -->

- **既有导入路径不变**：`pity.py` 顶部 `from .pity_primitives import Counter, Flag, PityState, DrawInfo, PityContext, LifecycleConfig`（re-export），故 `from gacha_simulator.core.pity import PityState` 等既有写法继续可用，`core/__init__.py` 的导出亦不变。这是本节与「PityState/DrawInfo/PityContext 完全保留」（§四「不受影响」）的关系：**语义与接口完全保留，仅换存放文件**。
- **`factor_redistribute` 归属**：现址 `pity.py:418` 的 `_redistribute_scope` 在 S8 被替换为卡级 `factor_redistribute`（§3.9.3 / §3.9.4），而 §3.9.4 又把该函数定位为「所有组级 Modifier 的公共落点」。它住在 `pity_primitives.py`（叶子层），Modifier 层单向依赖它——**不得放在 `pity_modifier.py` 内**（否则 Tracker 侧与 `pity.py` 侧复用时会再次形成循环）。
- **过渡期（S1–S5）**：`_redistribute_scope`（槽位级）暂留 `pity.py`；S8 一次性迁为 `pity_primitives.factor_redistribute` 并删除旧函数（§3.9.3 组件处置表）。
- §四的文件清单已按本条补齐 `core/pity_primitives.py`。

---

### 3.2 preset 映射（现有 10 类 → preset，含 counter 驱动统一）

<!-- REVIEW-R1-FIX: ISSUE-015 -->
<!-- REVIEW-R1-FIX: ISSUE-005 -->
registry（[pity.py:714](gacha_simulator/core/pity.py#L714)）条目新增 `preset` 字段（**工厂函数**），10 个条目的 `class` 字段**一律置 `None`**（ISSUE-015：原稿「条目从 class 指向 preset 工厂」与「事件驱动型置空、counter 驱动型保留旧类名」两处写法互相矛盾，且若把 `class` 指向工厂函数，[pity.py:817-834](gacha_simulator/core/pity.py#L817-L834) 的 `_validate_registry()` 在**模块导入期**即抛 `TypeError`，属全库级崩溃）。配套两处改造，并加一条**等价性装置与回滚的纪律**（见本段末，GATE-3(c) 定稿）：

- `_validate_registry()` 的校验对象由 `issubclass(cls, PityBehavior)` 改为「`preset` 可调用且返回含 `trackers` / `modifiers` / `lifecycle` 的 dict」（**`lifecycle` 为 ISSUE-301 新增的必需键**，理由见 §3.1.3）；
- `create_behavior`（[pity.py:836-892](gacha_simulator/core/pity.py#L836-L892)）的 `cls = entry["class"]` / `if cls is None: raise ValueError` 分支改为「`preset = entry.get("preset")`，无 preset 且 class 为 None 时报未实现」，并**校验 preset 返回 dict 含 `lifecycle` 键**（缺失抛 `ConfigError`，不得静默取骨架默认值——ISSUE-301）。两处均须进 §四。

<!-- REVIEW-R1-FIX: AUDIT-BREAK-3 -->
**preset 返回 dict 的键集契约与 `create_behavior` 的构造形态（AUDIT-BREAK-3，强制）**

preset 工厂返回的 dict 键集**恰好五键**：`trackers` / `modifiers` / `lifecycle`（必需）+ `flags` / `counters`（可选，缺省视为 `{}`）。后两键的消费者是 `Pity.__init__` 新增的 `flags` / `counters` 形参（§3.1.4 骨架，构造期按 L4 truthy 规则写 `state`）。`create_behavior` 的 preset 分支**按名取键**，**禁止 `**preset(pdef)` 直展开**——直展开会让未知键在 `Pity(...)` 处抛 `TypeError`（键多余）或静默落成死代码（键无人读）：

```python
# preset 分支（S4-1 落地；旧类兼容分支保留到发布前，见 GATE-5）
built = preset(pdef)
_unknown = set(built) - {'trackers', 'modifiers', 'lifecycle', 'flags', 'counters'}
if _unknown:
    raise ConfigError(f"preset '{pdef.btype}' 返回未声明键 {sorted(_unknown)}")   # 查多
if 'lifecycle' not in built:
    raise ConfigError(f"preset '{pdef.btype}' 缺少必需键 'lifecycle'")            # 查漏（ISSUE-301）
return Pity(
    name=pdef.name, state=state, scope=scope, btype=pdef.btype,
    priority=getattr(pdef, 'priority', 0),
    pools=tuple(getattr(pdef, 'pools', ('*',))),
    reads=tuple(getattr(pdef, 'reads', ())),
    trackers=built['trackers'], modifiers=built['modifiers'], lifecycle=built['lifecycle'],
    flags=built.get('flags'), counters=built.get('counters'),
)
```

两点配套（缺一则本条无效）：① **不得传旧类分支的 `params` dict**（`target_featured` / `reset` 注入的接口冲突见 §3.1.4 AUDIT-BREAK-2 条）；② 未知键校验与 `_validate_registry()` 的必需键校验是**两道互补校验**，不得合并成一道（前者查多、后者查漏，合并后两类问题互相掩盖）。

<!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
**旧类构造路径与 registry 回退（GATE-3(c) 定稿，强制）**

`class` 字段全部置 `None` 之后旧类在 registry 上**已无入口**，故两处声称依赖旧类的机制必须各自落实，否则一开工即发现无处可依（实测现状：`BEHAVIOR_REGISTRY` 每条都持有真实类对象，如 [pity.py:716-718](gacha_simulator/core/pity.py#L716-L718) 的 `class: SoftStepBehavior`）：

1. **等价性装置的「旧」侧：直接 import 旧类并以显式实参构造，不经 registry**。S5a 的 harness 从 `gacha_simulator.core.pity` 取 `SoftStepBehavior` / `HardPityBehavior` / `RotatingBehavior` / `RotatingCRBehavior` / `TargetedBehavior` / `RotatingSoftBehavior` / `RotatingCRSoftBehavior` / `TargetedSoftBehavior` 等类对象并手动传参构造（旧类在发布前一次性移除之前一直存在，见 GATE-5）。**不得**经 `create_behavior` 或 registry 取旧类（S4-1 落地后那条路径已指向 preset）。
2. **回滚路径：改为 `git revert` 子块 commit，不依赖 registry 保留旧类**（见 GATE-5）。原稿「回退 registry 到该 preset 指向旧类」在 `class: None` 之后不可执行，已一并改写。

**已评估并否决的备选**：在 registry 条目中加过渡字段 `legacy_class`（S4-1 写入旧类、发布前删除）。否决理由：它与 ISSUE-015 要消除的「条目同时持有 `class` 与 `preset` 两套指向」属同一类歧义，且 `_validate_registry()` 要额外维护该字段的生命周期；harness 直接 import 更简单，也不引入新状态。

<!-- REVIEW-R1-FIX: ISSUE-301 -->

**preset 必须是工厂函数，不是模块级常量实例（ISSUE-005，强制纪律）**：preset 定义一律写成 `def _preset_xxx(pdef): return dict(...)`（形参见下方 ISSUE-030 签名定稿），**不得写 `_preset_xxx = dict(trackers=[FlagTracker(...)], ...)`**。模块级赋值会把 Tracker / Modifier / Condition 实例化在模块命名空间里，`create_behavior` 每次拿回的是**同一批对象**：同进程内所有用该 preset 的保底共享同一 Tracker / Flag / Counter 遥控器，`_rebind_state` 会把它们的 `_state` 重绑到最后调度的保底，多个保底的计数写进同一账本。并行维度暴露最彻底——worker 内同一 engine 连跑 N 次模拟、`mp_failed` 单进程兜底与 `max_workers=1` 的测试路径都复用同一 engine，串扰既跨保底又跨模拟，固定种子结果随 worker 数变化。配套测试：「同 type 两条保底状态互不影响」（§六）。

<!-- REVIEW-R1-FIX: ISSUE-030 -->
**工厂签名与调用约定（ISSUE-030，2026-09-22 定稿，强制）**

preset 工厂**接受一个形参 `pdef`**（`PityDef` 实例），签名统一为 `def _preset_xxx(pdef) -> dict`；`create_behavior` 的调用形式为 `preset(pdef)`（`pdef` 已在手，registry 条目无须另存默认值）。**「零参工厂」是错的**：照零参示例施工会把逐条可配字段退化成常量，M1 的「与旧类逐场一致」只在**默认配置**下成立，任何非默认 `threshold` / `scope` / `counter_init` / `guaranteed_init` / `deltas` 都会静默退回常量值。**必须走 `pdef` 的值**（逐条可配，[config_store.py:159-186](gacha_simulator/core/config_store.py#L159-L186)）：

| 目标位置 | 取值来源 | 依据 |
|---------|---------|------|
| `Tracker(scope=…)` / `Modifier(scope=…)` | `pdef.scope` | `create_behavior` 的 `scope = (getattr(pdef,'scope',None) or _default_scope).lower()`（[pity.py:856](gacha_simulator/core/pity.py#L856)）；CLAUDE.md 记 2026-09-16 已接线 `PityDef.scope` |
| `ThresholdForceModifier` 的阈值 τ | `pdef.threshold`，`None` 时回退 **90** | 与 `HardPityBehavior` 默认 `threshold: int = 90`（[pity.py:351](gacha_simulator/core/pity.py#L351)）及 `ui_params` 默认值（[pity.py:752](gacha_simulator/core/pity.py#L752)）一致；`create_behavior` 只在 `threshold is not None` 时透传（[pity.py:875-876](gacha_simulator/core/pity.py#L875-L876)），故缺省必须由 preset 或 Modifier 兜底 |
| `CounterTracker(init=…)` / `counters` 初值 | `pdef.counter_init` | 对齐 `_build_pity_state_init` 的 truthy 规则（[pity.py:1005-1011](gacha_simulator/core/pity.py#L1005-L1011)，`if cv:` 才预建键） |
| `FlagTracker` / `flags` 初值 | `pdef.guaranteed_init` | 同上（[pity.py:1013-1015](gacha_simulator/core/pity.py#L1013-L1015)） |
| `BoostModifier(deltas=…)` | `pdef.deltas`，缺省时由 `soft_start` / `soft_end` / `soft_increment` 经 `_expand_soft_to_deltas()` 展开 | M6：展开职责搬入工厂，依赖 `create_behavior` 已透传的 `soft_*` 参数（[pity.py:866-874](gacha_simulator/core/pity.py#L866-L874)） |
| `CounterTracker(reset_on=…)` | `pdef.reset or pdef.scope` | 对齐 `create_behavior` 的 `if pdef.reset:` 透传口径（[pity.py:879-880](gacha_simulator/core/pity.py#L879-L880)） |
| `FateTracker` / `StreakTracker` 参数 | `pdef.fate_threshold` / `fate_points_init` / `cr_counter_threshold` / `cr_base_rate` / `cr_state_probs` | 同 `create_behavior` 的 P56 透传清单（[pity.py:883-885](gacha_simulator/core/pity.py#L883-L885)） |
| **`lifecycle=`**（preset 返回 dict 的必需键，**不写即静默失效**） | 由 `core/pity.py` 的 `build_lifecycle(pdef)` 按**两个正交维度**产出：激活维 = `pdef.depends_on` 非空 ? `Dependent` : `Always`；退役维 = `pdef.max_triggers > 0` ? `AfterN(n)` : `Never`（四组合：`AlwaysActive` / `OnceActive` / `DependentActive` / `DependentOnceActive`）——**工厂不自行拼装** | **旧 `create_behavior` 的 `lifecycle_kwargs` 段（[pity.py:893-900](gacha_simulator/core/pity.py#L893-L900)）是这两个字段唯一的转换点**；preset 化后必须由工厂承接**且旧段须同步删除**。定稿与三条配套纪律见 §3.1.3；`create_behavior` 对缺失该键有 `ConfigError` 防线、§六 有断言 | <!-- REVIEW-R1-FIX: ISSUE-301 --> |

preset 自身只保留**语义固定项**（如 `judge="featured"` / `hit="clear"` / `miss="set"` 这类由机制语义决定的匹配面）。§六 已补「非默认 threshold / scope / counter_init 下 preset 与旧类逐场一致」的断言。

`create_behavior` 检测 `entry.get("preset")` 走新路径。

```python
def _preset_rotating(pdef):          # ISSUE-030：形参 pdef，逐条可配值一律取自它
    return dict(
        lifecycle=build_lifecycle(pdef),         # ISSUE-301：生命周期唯一转换点（§3.1.3）
        trackers=[FlagTracker(judge="featured", hit="clear", miss="set", flag="guaranteed")],
        modifiers=[
            ConditionalModifier(ForceFeaturedModifier(pdef.scope), FlagCondition("guaranteed")),
            BaseRatioModifier(pdef.scope),          # 无条件
        ],
        flags={"guaranteed": pdef.guaranteed_init},  # 初值走状态声明（H2），不加 Tracker 形参
    )

def _preset_hard(pdef):
    tau = pdef.threshold if pdef.threshold is not None else 90    # 缺省对齐 pity.py:351 / :752
    return dict(
        lifecycle=build_lifecycle(pdef),         # ISSUE-301
        trackers=[CounterTracker(scope=pdef.scope, reset_on=pdef.reset or pdef.scope,
                                 init=pdef.counter_init)],
        modifiers=[
            ConditionalModifier(ThresholdForceModifier(pdef.scope), CounterCondition("counter", tau)),
            BaseRatioModifier(pdef.scope),
        ],
        counters={"counter": pdef.counter_init},
    )

def _preset_soft_step(pdef):
    deltas = pdef.deltas if pdef.deltas is not None else _expand_soft_to_deltas(   # M6
        pdef.btype, pdef.soft_start, pdef.soft_end, pdef.soft_increment)
    return dict(
        lifecycle=build_lifecycle(pdef),         # ISSUE-301
        trackers=[CounterTracker(scope=pdef.scope, reset_on=pdef.reset or pdef.scope,
                                 init=pdef.counter_init)],
        modifiers=[
            ConditionalModifier(BoostModifier(deltas), Always()),   # 计数驱动，条件恒真
            BaseRatioModifier(pdef.scope),
        ],
        counters={"counter": pdef.counter_init},
    )
```
<!-- REVIEW-R1-FIX: ISSUE-030 -->
<!-- REVIEW-R1-FIX: ISSUE-031 -->
<!-- REVIEW-R1-FIX: ISSUE-301 -->
> **形态以 §3.14.2 为准（ISSUE-031）**：上例的三处 `modifiers` 已按 **§3.14 的条件外置**定稿——Modifier 只算因子、**不带 `flag` 形参**，触发条件由 `ConditionalModifier` 的第二个实参承载。**该形态自 S12 起可用，而 S12 已前移进 M1、排在 S4 之前（ISSUE-101，§七）**，故 S4 开工时 `core/pity_condition.py` 与 `ConditionalModifier` 均已存在——本节与 §3.3 / §3.14.2 是本计划**唯一**的 preset 代码形态，不存在「S12 之前另有一版 preset」的过渡稿。原稿的 `ForceFeaturedModifier(flag="guaranteed")` / `ForceNonFeaturedModifier(flag="forced_loss")` 形态**已废弃**（按原样构造会 `TypeError`：定稿的 `ForceFeaturedModifier.__init__(self, scope)` 无 `flag` 形参，§3.14.2）。同理 `ThresholdForceModifier` 的 `threshold` 已外置到 `CounterCondition('counter', τ)`（§3.14.2 的重组列表），构造只保留 `scope`（F 语义需要它判定「更高稀有度豁免」）；其**因子计算仍是 F 语义**，不得改为 `factor_redistribute`（§3.14.3）。`InterceptModifier` 是唯一例外（保持内部判断，其「条件」消费随机数，§3.14.2 末段）。

| 现有 type | preset 三元组（含完整状态声明，H2 补全） | 组装时的条件（§3.14.2；ISSUE-031 补列） |
|-----------|------------------------------------------|-----------------------------------|
| hard | Tracker: CounterTracker(scope=pdef.scope, reset_on=pdef.reset or pdef.scope)；Modifier: [ThresholdForce(pdef.scope), BaseRatio(pdef.scope)]；counter 初值 = pdef.counter_init | `CounterCondition('counter', pdef.threshold or 90)`——**τ 由条件承载，不再进 Modifier**（F 语义的因子计算保留，§3.14.3） |
| soft_step | Tracker: CounterTracker(scope=pdef.scope, reset_on=…)；Modifier: [BoostModifier(deltas), BaseRatio(pdef.scope)] | `Always()`（计数驱动，恒真） |
| soft_interval/soft_additive | 同 soft_step，deltas 由 preset 工厂展开（M6：`_SOFT_SUFFIX_TYPES` 展开职责从 `SoftPityMixin._init_soft_pity` 移入工厂；显式 `pdef.deltas` 优先） | `Always()` |
| rotating | Tracker: `FlagTracker(judge="featured", hit="clear", miss="set", flag="guaranteed")`（**ISSUE-104 统一为定稿形态**，原写 `FlagTracker(judge="featured")` 单参简写）；Modifier: [ForceFeatured(pdef.scope), BaseRatio(pdef.scope)]；Flag: guaranteed（**初值** = `pdef.guaranteed_init`，走 `flags` 状态声明，不加 Tracker 形参——但**标记名经 `flag=` 传入**） | `FlagCondition('guaranteed')`；BaseRatio 无条件 |
| rotating_soft | rotating + CounterTracker + [BoostModifier, ForceFeatured, BaseRatio]（含 **触发稀有度重置抽数 counter**：hit/miss 两分支都 ResetCounter，对齐 [pity.py:534-537](gacha_simulator/core/pity.py#L534-L537)） | ForceFeatured → `FlagCondition('guaranteed')`；Boost → `Always()`；BaseRatio 无条件 |
| rotating_cr | rotating + StreakTracker(judge="featured", **was_guaranteed 守卫**：仅抽前 guaranteed 未置位时更新，对齐 [pity.py:590-600](gacha_simulator/core/pity.py#L590-L600))；Modifier: [ForceFeatured(guaranteed), InterceptModifier, BaseRatio] | ForceFeatured → `FlagCondition('guaranteed')`；**InterceptModifier 为唯一例外**（保持内部判断，其「条件」消费全局 `random`）；BaseRatio 无条件 |
| rotating_cr_soft | rotating_cr + BoostModifier（含 counter 重置 + was_guaranteed 守卫） | 同 rotating_cr；Boost → `Always()` |
| targeted | Tracker: `FateTracker(judge="selected", hit="clear", miss="accumulate", keys=("fate_points", "losses", "guaranteed", "lost_rotating"))`（**ISSUE-104 统一为定稿形态**：原写 `FateTracker(judge="selected")`，未表达多键集；`keys` 即 [pity.py:666-669](gacha_simulator/core/pity.py#L666-L669)、[pity.py:672-675](gacha_simulator/core/pity.py#L672-L675) 的**补全后的四键**，`hit`/`miss` 形参名与 `FlagTracker` 同口径、由 S1 定稿）；Modifier: [ForceSelected(guaranteed_or_fate_ready), BaseRatio]；Flags: guaranteed, lost_rotating；Counters: fate_points, losses | `Or(FlagCondition('guaranteed'), FateReadyCondition(pdef.fate_threshold))`；BaseRatio 无条件 |
| targeted_soft | targeted + BoostModifier（含 counter 重置） | 同 targeted；Boost → `Always()` |

<!-- REVIEW-R1-FIX: ISSUE-301 -->
> **表中 10 行的 Lifecycle 组件统一为 `build_lifecycle(pdef)`（ISSUE-301，强制）**：上表「preset 三元组」列只列 Tracker 与 Modifier 两项，**不逐行重复 Lifecycle**——10 行的 Lifecycle 一律由 `build_lifecycle(pdef)` 产出并作为返回 dict 的 `lifecycle=` 键（§3.1.3 定稿的三路取值：`pdef.depends_on` 非空 → `DependentActive`；否则 `pdef.max_triggers > 0` → `OnceActive`；否则 `AlwaysActive`；`deactivate_on_early_hit` 三路都带入）。**漏写该键即全部 `deactivate_on_early_hit` / `depends_on` / `max_triggers` 配置静默失效**，故 `create_behavior` 对此设 `ConfigError` 防线（§3.2 首段）、§六 设断言。

<!-- REVIEW-R1-FIX: ISSUE-001 -->
**「零改动」的前提（ISSUE-001）**：`Pity` 必须继续由 `btype` 推导 `is_soft` / `is_hard` / `is_event_driven` 三个标志（§3.1.4 骨架已按此写入，删除了「统一后不再区分 counter/event」的写死行）。`_validate_behaviors`（[pity.py:933-985](gacha_simulator/core/pity.py#L933-L985)）按 `is_hard` → `is_event_driven` → `is_soft` 的 `elif` 链分派规则 2/3/4，标志缺失会让三个规则全部错判（实测：只打 `is_event_driven=True` 后，soft_interval + soft_additive 同 scope 由「通过」变抛 `ConfigError`，rotating + hard 同 scope 被拒，规则 2 静默失效）。若将来确要废掉这三个标志，必须与 §3.12.2 的合法组合判据**合并重写**分派逻辑并在 §六 补相应断言，不得只删标志。

`_btype` 保留，故 `_resolve_order`（[pity.py:916](gacha_simulator/core/pity.py#L916)）/ `_validate_behaviors`（[pity.py:933](gacha_simulator/core/pity.py#L933)）排序校验逻辑零改动（**2026-09-18**：P82 接线独立先行后，排序结果被 `get_behaviors_for_pool()` 消费；P64 主线不改其排序逻辑，仅经 M3 新增 `priority` 键）。`params`/`ui_params` 保留，GUI 参数控件零改动。

### 3.3 G1 inverse preset（新增）

幻塔连中必歪：出 UP 后下一次 SSR 必非 UP。与 rotating 对偶：

```python
def _preset_rotating_inverse(pdef):          # ISSUE-030：形参 pdef；ISSUE-031：条件外置形态
    return dict(
        lifecycle=build_lifecycle(pdef),         # ISSUE-301
        trackers=[FlagTracker(judge="featured", hit="set", miss="clear", flag="forced_loss")],
        modifiers=[
            ConditionalModifier(ForceNonFeaturedModifier(pdef.scope), FlagCondition("forced_loss")),
            BaseRatioModifier(pdef.scope),
        ],
        # forced_loss 是 preset 内部标志，PityDef 无对应初始值字段（区别于 rotating 的
        # guaranteed_init），故初值恒为 False——与旧实现（无该机制）一致。scope 取自 pdef。
        flags={"forced_loss": False},
    )
```
<!-- REVIEW-R1-FIX: ISSUE-030 -->
<!-- REVIEW-R1-FIX: ISSUE-031 -->
<!-- REVIEW-R1-FIX: ISSUE-301 -->

注册为 `rotating_inverse`（display_name「反向轮换保底（连中必歪）」）。`ForceNonFeaturedModifier` 复用 `_redistribute_scope` 反向调用。**形态以 §3.14.2 为准**——`ForceNonFeaturedModifier` 本身**无 `flag` 形参**，触发条件由外层 `ConditionalModifier` 承载（§3.14.6 的修订范围已如此声明，此处正文同步）。

<!-- REVIEW-R1-FIX: ISSUE-105 -->
**三处类型注册（ISSUE-105，强制，2026-09-22 补）**：`rotating_inverse` 不只是「多一个 registry 条目」，它必须同时进入**两个类型集合**与**一个排序表**，缺任一处即静默失效：

| 落点 | 取值 / 内容 | 不做的后果 |
|------|------------|-----------|
| `_BTYPE_ORDER`（[pity.py:908-914](gacha_simulator/core/pity.py#L908-L914)，现状 10 项、**无该键**） | 加 `'rotating_inverse': 3`（与 `rotating` / `targeted` / `targeted_soft` 同族档位） | `_resolve_order` 用 `_BTYPE_ORDER.get(btype, 99)`（[pity.py:928](gacha_simulator/core/pity.py#L928)），缺键落到 **99**（排在全部已知类型之后）。接线后（P82 使排序键成为管道顺序的唯一来源，§1.5）会改变它与同 scope 其它保底的先后 |
| `_EVENT_DRIVEN_TYPES`（[pity.py:114-115](gacha_simulator/core/pity.py#L114-L115)，现状 6 项） | 追加 `'rotating_inverse'`（该集合升为模块级常量后同样须含它） | `_btype` 推导出的 `is_soft` / `is_hard` / `is_event_driven` **全为 False** → `_validate_behaviors`（[pity.py:933-985](gacha_simulator/core/pity.py#L933-L985)）规则 2/3/4 全部跳过，**同 scope 的 `rotating` + `rotating_inverse` 可共存而不报错**（规则 3 即「同 scope 两个事件驱动型互斥」），正是本计划反复强调的静默失效模式；该集合还决定 `is_active` 早退是否作用于该类型（§3.1.3） |
| `_SOFT_TYPES` / `_HARD_TYPES` | **不加**（rotating_inverse 既非 soft 也非 hard） | — |

§四 的 `core/pity.py` 重构行原只写「`_BTYPE_ORDER` 加 `rotating_inverse`」而未给取值，已补；S1 的「三个集合升为模块级常量」任务项已注明「**常量内容需追加 `rotating_inverse`**」——不得按「原样迁移」理解。§六 已补对应断言。


### 3.4 软保底统一（不再分阶段二）

新架构下 soft 不再是 mixin，而是 `CounterTracker + BoostModifier`。**无需分阶段**，全部 10 个类型在同一阶段 preset 化：

- `SoftStepBehavior`/`HardPityBehavior` 同步退役为 preset（CounterTracker + 对应 Modifier）
- `SoftPityMixin` + 3 个 `_soft` 类同步退役
- **deltas 展开职责移交（M6）**：`SoftPityMixin._init_soft_pity` 唯一做 `soft_start/soft_end/soft_increment → deltas` 展开（[pity.py:511-528](gacha_simulator/core/pity.py#L511-L528)），退役后该展开移入 preset 工厂（依赖 create_behavior 已透传的 soft_* 参数，[pity.py:864-874](gacha_simulator/core/pity.py#L864-L874)）

`rotating_soft` = rotating 的 Tracker/Modifier 各加一项，`_SOFT_SUFFIX_TYPES` 处理移除；任意 Tracker × 任意 Modifier 自由组合，不再需要每组合一个类。

### 3.5 Lifecycle 统一（P64 增量能力）

`deactivate_on_early_hit` 目前只在 counter 驱动型（[pity.py:334-336](gacha_simulator/core/pity.py#L334-L336)、[pity.py:410-412](gacha_simulator/core/pity.py#L410-L412)）实现，且 config_toml 对事件驱动型配置该参数直接抛 ConfigError（[config_toml.py:652-660](gacha_simulator/core/config_toml.py#L652-L660)）。P64 统一进 Lifecycle 包装层，使全部类型可用。**必须同步移除 config_toml 的拒绝分支（H3）**，否则增量能力无法配置。**此为增量能力（旧事件驱动类无此能力），不在等价性范围内**。覆盖手册 §16.6 终末地 80/120 协调「若 120 用 rotating 表达」的场景。

### 3.6 与引擎/配置/GUI 对接

- **PityEngine**（[pity.py:1124](gacha_simulator/core/pity.py#L1124)）：调度层接口签名不变，`before_draw`/`after_draw`/`get_probabilities` 调用链不变，P75 rebind 由 Pity 统一实现。**G5 priority（2026-09-18 裁决：保留并实施，与接线配套）**：`_resolve_order`（[pity.py:916](gacha_simulator/core/pity.py#L916)）排序 key 加 `priority` 优先级（位于稀有度 rank 之后、type order 之前）。**透传（M3）**：`PityDef` 新增 `priority: int = 0`，`create_behavior` 以 **构造形参 `Pity(..., priority=pdef.priority)`** 传入（**ISSUE-203**：原稿写的「`create_behavior` 构造后设置 `pity._priority` 属性」与 §3.1.4 骨架已定稿的 `priority: int = 0` 构造形参 + `self._priority = priority` **互斥**，同一份计划对同一个值给了两条替代机制；现以骨架为准，**「构造后设属性」写法废弃**。`create_behavior` **自身**签名不改——它本就是 `Pity(...)` 的唯一构造点，直接多传一个关键字实参即可）——priority 全 0 时排序结果与现状完全一致，显式 priority 覆盖 type 顺序。<!-- REVIEW-R1-FIX: ISSUE-203 -->**论证**：接线（§1.5 裁决 1）使排序键成为管道顺序的唯一来源，配置者不再能靠「TOML 书写顺序」控制优先级，`priority` 因此成为唯一的顺序覆盖入口；当前 `_BTYPE_ORDER` hard=1 < targeted=3 已满足绝区零 G5 需求，priority 的价值是「显式化现有隐式顺序 + 提供未来场景覆盖」。**接线本身建议独立先行（§1.5 实施方案），本项随主线实施**
- **PityDef/TOML**：现有 type 名继续有效（preset 别名）；`rotating_inverse` 新 type 无需新字段；`PityDef.priority` 新增；参数透传（[pity.py:864-892](gacha_simulator/core/pity.py#L864-L892)）逻辑保留，目标从具体类变 preset 工厂（**工厂签名 `preset(pdef)`，逐条可配字段由工厂消费——ISSUE-030，见 §3.2**）

<!-- REVIEW-R1-FIX: AUDIT-BREAK-1 -->
**PityDef 字段级透传纪律（AUDIT-BREAK-1，强制，2026-09-22 补）**

问题：从 `ConfigStore` 到运行期引擎之间是**枚举式透传**，共三处（实测）：

| # | 位置 | 现状 | 漏写的后果 |
|---|------|------|-----------|
| 1 | `batch_simulator.from_config_store` 的 `pentry` dict（[batch_simulator.py:899-925](gacha_simulator/service/batch_simulator.py#L899-L925)，**24 键**，已含 `reset`） | 逐字段 `getattr(pd, 'x', 默认)` | 该字段在 GUI / 批处理路径**恒为默认值**，配置层看不出任何异常 |
| 2 | `_build_pity_engine_from_gui` 的 `_PityDef(...)` 重建（[batch_simulator.py:179-204](gacha_simulator/service/batch_simulator.py#L179-L204)） | 逐字段 `p.get('x', 默认)` | 同上（`_PityDef` 是 `PityDef` 的别名，[batch_simulator.py:163](gacha_simulator/service/batch_simulator.py#L163)） |
| 3 | `retreat_config` 的浅拷贝（[retreat_config.py:123-142](gacha_simulator/core/retreat_config.py#L123-L142)，24 个显式字段） | 逐字段复制 | 同 1 |

已定：`priority`（S4b）与 `reads`（S9-2）各自随字段定义同步补齐三处（§七两步的目标文件已含这三处）。**但「逐个字段补」的写法会随字段新增反复断裂**——例如 `max_triggers` 本期按 §七「本轮处置表」第 3 项**不接线**（只验类语义），一旦将来接线就必须记得改三处，否则又是一个静默失效点。

强制纪律（三条）：

1. **同 commit 纪律**：任何 `PityDef` 新增字段（含 `priority` / `reads` / 将来的 `max_triggers`）**必须在引入该字段的同一子块内**同步三处透传点，不得留到后续子块；三处透传点与该字段的定义/解析**同一 commit 落地**。
2. **改造成 dataclass 驱动（S4b 落地，原写「建议」现升为强制）**：三处一律改为由 `dataclasses.fields(PityDef)` 驱动（`pentry = {f.name: getattr(pd, f.name) for f in fields(pd)}` / `_PityDef(**{f.name: p[f.name] ...})` / 浅拷贝同式），使「新字段」在结构上不可能被漏掉。逐字段枚举与 `pentry` 的 24 键清单**一经改造即删除**，不得与新写法并存（并存即第二真相源）。
3. **防回归断言（S4b 落地）**：新增一条**字段全量 round-trip** 测试——`for f in fields(PityDef)`，用非默认值构造 `PityDef`，经 TOML round-trip → `ConfigStore` → `pentry` → `_PityDef` 后逐字段断言等值；并断言 `pentry` 的键集 `== {f.name for f in fields(PityDef)}`（键集相等而非包含，防漏也防多）。该断言使「第 N+1 个字段漏透传」在 CI 期即失败，不再依赖人工记忆。落点见 §七 S4b 与 §六。

- **GUI config_panel**：**2026-09-18 事实修正（两处）**——① 保底 type 下拉**不是** registry 驱动，而是硬编码列表 `_PITY_TYPES`（[config_panel.py:2019-2031](gacha_simulator/gui/config_panel.py#L2019-L2031)，10 项；[config_panel.py:2084](gacha_simulator/gui/config_panel.py#L2084) 处 `addItems`），新增 `rotating_inverse` 须**手工追加**该列表，否则 GUI 不可选（由 registry 驱动的是**参数控件**，[config_panel.py:2765-2772](gacha_simulator/gui/config_panel.py#L2765-L2772)，该部分「零改动」成立）；② **GUI 现无 reset 控件**，`_apply_pity_edit` 不写 `pd['reset']`，`reset` 仅在 load/save 路径透传（[config_panel.py:6349](gacha_simulator/gui/config_panel.py#L6349)、[config_panel.py:7190](gacha_simulator/gui/config_panel.py#L7190)），故 G16 的 GUI 部分是**新建控件**而非「下拉加一项」；③ priority 编辑控件（G5）同为新建；参数控件零改动
- **config/config.toml**：新增幻塔 `rotating_inverse` + G16 示例配置
- **GachaService 定轨识别（H1，强制）**：[gacha_service.py:275](gacha_simulator/service/gacha_service.py#L275) 用 `isinstance(bh, TargetedBehavior)` 识别定轨保底（`switch_epitomized_target`/`cancel_epitomized_path` 两条 NonDrawAction 流程）。targeted preset 化后 bh 变为 `Pity` 实例，isinstance 恒 False → 定轨流程整体失效。须改为 `getattr(bh, '_btype', '') in ('targeted', 'targeted_soft')`（或 Pity 加 `_is_targeted` 标记），波及范围表补 `service/gacha_service.py`。<!-- REVIEW-R1-FIX: AUDIT-BREAK-4 --> **本条含一处「不报错但必崩」的补充（AUDIT-BREAK-4，强制）**：同一函数首行的**函数局部 import** `from ..core.pity import TargetedBehavior`（[gacha_service.py:253](gacha_simulator/service/gacha_service.py#L253)）必须一并删除/改写——`S4-3` 之后该符号在**发布前移除旧类**时消失，而**局部 import 只在函数被调用时执行**，故 ruff / H7 与导入期均不报错，仅当策略真的返回 `NonDrawAction`（`switch_epitomized_target` / `cancel_epitomized_path`）时才抛 `ImportError`——`NoneDrawAction` 全库唯一构造点是策略层，测试若只覆盖 `DrawAction` 路径则 CI 全绿。**S6c 的目标面因此是四处而非一处**：`:253` 局部 import、`:275` isinstance 判定、`:292`/`:294` 两处写 `selected_card`（其 `targeted_name` 变量由 :275 的循环体赋值，判定口径与 :275 **必须同源同改**，否则定位到 0 条或定位错保底时 :292/:294 会把 `selected_card` 写进错误命名空间）。**验收命令同步追加一条「策略返回 `NonDrawAction` 的端到端用例」**（§七 S6c / §六），仅断言 `isinstance` 替换不足以覆盖 `:253`。
- **G14 动态 threshold（后续扩展）**：`RandomThresholdTracker(range=(80,100))` 每次重置随机阈值，`ThresholdForceModifier` 读随机阈值判定，与 G16 同属 Tracker 维度扩展，无需新 Modifier

### 3.7 范围边界（不建模）

- **G2 阴阳师神眷动态 threshold**：属 milestone 层累抽奖励（见 §1.3），P64 范围外
- **`switch_allowed`/`switch_resets_progress`（定轨切换规则）**属 GachaService 策略层职责（P56 NonDrawAction），切换逻辑 P64 不改；**定轨识别方式须适配 preset 化**（§3.6 H1，isinstance → `_btype` 判断），否则 P56 定轨流程失效
- **槽位粒度约束（S8 前的既有边界，2026-09-21 实测）**：`compute_scope_mappings` 对每个稀有度只生成一个 featured 槽，故同一稀有度下的多张 featured 卡**共享一个槽位**，槽内各卡的相对比例恒等于基础权重比例（槽位级算子只做统一缩放，无机制可改组内比例）。后果是**双 UP 池的定轨失真**：`targeted` 锁定其中一张后，必中触发时该槽位按基础权重平摊（实测 `up_a` = `up_b` = 50%），目标卡拿不到 100%。此约束继承自 P56，P64 §3.1.5 亦未解除；由 **S8 的卡级管道**解决（目标集合可细到单卡）。另注：崩坏3 的 G3（UP 组排除已拥有）受同一约束制约，手册原将其归为 pool 层是架构约束下的权宜。**2026-09-21 裁决：G3 做真实建模**（依 CLAUDE.md §二「精确建模原则」，不接受 pool 层近似），需 S8 的卡级管道加上 §3.10 的状态可见性，方案见 §3.10.4
- **G15 pjsk 加权抽数**：**2026-09-21 重估**——原记「🟢 近似可配（reward 注入 + 兑换池）」，但按「精确建模原则」（CLAUDE.md §二）近似不计入已覆盖，本条改为**待消除的缺口**；严格语义需 milestone `weight_by_pool`（milestone 层，P64 范围外）
- **跨保底状态读取**：**不纳入**（2026-09-21 裁决，依手册全量查证「零真实需求」），且由 §3.10.3 的 `StateView` 在架构上关闭。关联需求走 `depends_on`（声明式依赖边）或状态合并
- **`type="custom"` 完全声明式 TOML 状态机不实现**（用户裁决，过度设计）——如需「组合内置片段」，在 preset 数据化之上小步扩展（阶段三预留，不承诺）

### 3.8 G16 独立先行（`reset="never"`）

幻塔「出金不重置」单行改动，**独立 commit 先行**，不并 P64 主线（counter 驱动与事件驱动在新架构下本就统一为 Tracker 维度，但 G16 作为单行能力独立可先交付）：

```python
# 新架构：CounterTracker(reset_on="never") 即永不重置，无特殊分支
# 旧架构兼容（G16 先行阶段，P64 主线前）：
def _should_reset(self, ctx):                       # pity.py:200
    if self._reset == "featured":
        return ctx.draw.is_featured
    if self._reset == "never":
        return False                                # 新增：永不重置
    return ctx.draw.reward_rarity == self._reset
```

配套：PityDef/config_toml 的 reset 枚举加 `"never"`、GUI **新建 reset 输入控件**并加「永不重置」选项（现无该控件，见 §3.6 事实修正）、一条测试、手册 G16 从「🔵 待 P64」改「✅ 已覆盖」。P64 主线落地后该分支由 `CounterTracker(reset_on="never")` 自然承载。

### 3.9 概率操作路径重构（S8 实施方案，2026-09-21 新增）

> §3.1.2 的 D20 是**声明**（分布空间归属改为卡级），§3.1.5 是**数学形式**（乘性算子），本节是**实施方案**（改哪些函数、接口怎么变、边界怎么处理）。三者配套，缺一则 S8 不可执行。
>
> **过渡期纪律**：S1–S5 期间本节内容全部**不实施**，Modifier 内部沿用槽位法，以保证与旧类位级一致（§六 S1–S5 口径）。S8 一次性切换，验收对 S5 产物取 1e-12 容差。

#### 3.9.1 现状路径与目标路径

**现状**（[banner.py:226-248](gacha_simulator/core/banner.py#L226-L248)，卡级与槽位级往返四次）：

```
probabilities = {r.id: p for r, p in pool.rewards}              # 卡级
rarity_probs  = aggregate_probs_by_rarity(pool, pity_spec)      # 卡级 → 槽位级（聚合）
adjusted      = pity_engine.before_draw(key, state, rarity_probs)   # 槽位级管道
if rarity_probs != adjusted:
    scale_factors = {slot: new / old for slot, new in adjusted.items()}   # 算缩放
    for rwd_id in probabilities:                                # 槽位 → 卡级（还原）
        slot = f'{infer_rarity_from_spec(rwd_id, spec) or "ssr"}_featured' 或稀有度名
        if slot in scale_factors:
            probabilities[rwd_id] *= scale_factors[slot]
pool._apply_probabilities(probabilities)
```

**目标**（S8 后，往返全部消失）：

```
probabilities = {r.id: p for r, p in pool.rewards}              # 卡级
adjusted      = pity_engine.before_draw(key, state, probabilities)   # 卡级管道
pool._apply_probabilities(adjusted)
```

净删除：`aggregate_probs_by_rarity` 的调用（banner 侧）、`scale_factors` 段（11 行）、`infer_rarity_from_spec` 的槽位反查用途。

#### 3.9.2 Modifier 接口：产出因子，引擎做归一化

**接口变更**（S8）：Modifier 从「返回修正后的分布」改为「返回因子向量」，归一化收到引擎层统一做。

```python
class Modifier:
    def factor(self, ctx, view, dist, readonly) -> Optional[Dict[str, float]]:
        """返回因子向量 {card_id: m}；未列出的卡默认 m = 1；None 表示恒等。

        view：状态视图。S8 期间是 PityState 的薄包装（可读全部命名空间），
              S9 后收紧为「只含自身命名空间」的 StateView（§3.10.3）。
              签名按最终形态定型，避免两阶段各改一次。
        """

    def rebind(self, state, name) -> None:      # ISSUE-029：P75 纪律的统一接口
        """把本 Modifier 内部持有的 Counter / Flag 重绑到 per-call state（纯重定向）。
        Pity._rebind_state 无条件调用它，故方法必须存在；无状态零件可 pass，不得省略。"""

    def apply(self, ctx, view, dist, readonly):
        """**默认实现**（ISSUE-GATE-3-dependency-order，2026-09-22 定稿）：把本 Modifier 的因子向量
        作用到分布并归一化。`apply` 自此**不是**每个 Modifier 的必写方法——各 Modifier 覆写的是
        `factor()`，`apply()` 由本基类提供。两期分工：**M1（S2 起至 S7）** 各 Modifier 直接实现 `apply`
        （§3.1.2 历史形态，返回分布）并覆写掉本默认实现；**S8 起** 各 Modifier 改实现 `factor()`，
        骨架逐项调用 `factor`，本默认实现成为唯一的 `apply` 定义。

        **这是「`apply()` 保留为默认实现」的承载处**（§3.1.2 / §3.9.2 原稿只写该句、未指明它住哪）：
        `ConditionalModifier.apply`（§3.14.2）转发 `self._mod.apply(...)`，被包裹的 Modifier 在 S8 之后
        只写 `factor`——没有本基类即 `AttributeError: 内层对象无 apply`，而该调用点在每个抽卡的调度
        入口，后果是全部保底不可用（§六 的存在性断言不触发调用，捕获不到该缺口，故本条必须落成代码）。"""
        return _apply_factor(dist, self.factor(ctx, view, dist, readonly) or {})

# Pity 骨架
for mod in self._modifiers:
    m = mod.factor(ctx, self._view, out, readonly)
    if m is not None:
        out = _apply_factor(out, m)      # (m ⊙ out) / ⟨m, out⟩

def _apply_factor(dist, m):
    out = {c: dist[c] * m.get(c, 1.0) for c in dist}
    total = sum(out.values())
    return dist if total <= 0 else {c: v / total for c, v in out.items()}
```

<!-- REVIEW-R1-FIX: ISSUE-029 -->
> **`Modifier` 是全部 Modifier 的公共基类（ISSUE-GATE-3-dependency-order 定稿，2026-09-22）**：`rebind`（空实现，供无状态零件继承、有状态者覆写）与 `apply`（由 `factor` 导出，见上方代码）两个**默认实现都住在本基类**；`factor` 是各 Modifier 唯一必写的那个。**§3.2 / §3.14.2 的每个 Modifier 示例一律写成 `class XxxModifier(Modifier):`**——原稿为裸类、无基类，使「`apply()` 保留为默认实现」无承载处，S8 之后 `ConditionalModifier.apply` 的转发目标会落成 `AttributeError`；`ConditionalModifier` 同样继承本基类并覆写 `apply` / `factor` / `rebind` 三个转发。**备选（S8 一并删除 `apply` 与 `ConditionalModifier.apply`）已否决**：它与 §3.1.2 的「`apply` 保留为默认实现」互斥，还要同步改 §六 的 M1 断言口径，改动面更大且无额外收益。<!-- REVIEW-R1-FIX: ISSUE-GATE-3-dependency-order -->
> **`rebind` 是 S8 之前就需要的接口（ISSUE-029）**：`Pity._rebind_state`（§3.1.4）自 S1 起就无条件调用 `mod.rebind(state, name)`，而本节的 `factor()` 是 **S8** 才引入——两者不可混为一谈，别把 `rebind` 当成 S8 的附属接口。各 Modifier 是否持有状态零件（Counter / Flag）不同，恒等零件可直接 `pass`。**另注意 S12 的连带影响**：S12 落地后 preset 里的 Modifier 一律被 `ConditionalModifier` 包裹（§3.14.2），该包装器**必须转发 `rebind`**，否则 S12 一落地、首次抽卡即抛 `AttributeError: 'ConditionalModifier' object has no attribute 'rebind'`。该调用位于每个抽卡的调度入口，后果是全部保底不可用，而非局部退化。

> **与 §3.1.4 骨架的关系（ISSUE-GATE-dependency-order 定稿，2026-09-22）**：S1–S5 期间 Modifier 的方法名是 **`apply(ctx, view, dist, readonly)`**（返回修正后的分布，§3.1.2 历史形态），骨架按此调用、本节的内循环不实施；S8 引入 **`factor(...)`** 返回因子向量，内循环改为 `mod.factor(...)` + `_apply_factor`，`apply()` 保留为默认实现、`factor()` 缺省时回退到它。
>
> **包装器的转发义务（缺一头即每个抽卡入口 `AttributeError`）**：`ConditionalModifier` **必须同时转发三个方法**——`rebind(state, name)`（自 S12 起，§3.14.2）、`apply(ctx, view, dist, readonly)`（自 S12 起，M1 骨架调用它）与 `factor(...)`（自 S8 起）。骨架对 `modifiers` 列表**逐项无守卫**调用，被包裹的 Modifier 缺任一名字即整条保底链不可用。§3.14.2 的代码块与 §六 的断言已按下述形态写死；**原稿「§3.14.2 只实现 `factor` + `rebind`」的形态与骨架的 `mod.apply(...)` 互斥**，按本段统一。

<!-- REVIEW-R1-FIX: ISSUE-004 -->
> **`self._view` 的生命周期（ISSUE-004，强制）**：`self._view` 是 `Pity` 的成员，**每次 `_rebind_state` 必须重建**（§3.1.4 骨架已写），且 `StateView` 自身**不得在构造期缓存命名空间 dict**（§3.10.3 已改为每次 `get` 现取）。两条缺一：worker 内同一 engine 连跑 N 场模拟，第 2..N 场读的是第 1 场的账本；若 view 建于命名空间尚未创建之时（`depends_on` 依赖方构造期不写 `_active`），`state.data.get(name, {})` 会拿到一个与 state 脱联的空 dict，此后引擎 `state.set` 新建的命名空间与该 view 无关，所有读取恒返回 default 且不报错。此条同时是 §五 风险表「Pity 统一实现 Trackers/Modifiers/Lifecycle 的 rebind 委托」的落地条件。

**为什么归一化放引擎层（ISSUE-021，2026-09-22 修正论证前提）**：原稿称「§3.1.5.2 已证三个基本算子的 ⟨m,p⟩ 恒为 1，归一化是恒等操作」，与 §3.9.5 / §3.9.4 自相矛盾——⟨m,p⟩ = 1 只在两类情形成立：① `R_r` / `B_β` 且 `T ⊊ S`、`T ∩ Q = ∅`；② `F` 作用于**最高稀有度**的 scope（§3.1.5.2 的验算段）。`F` 作用于低于最高稀有度的 scope 时 ⟨m,p⟩ = P + p(更高稀有度) ≠ 1（§3.9.5 实测 `ssr` 0.009 → 0.008919）；`R` 的 `ratio = 1` 分支更须靠「源侧显式写 0 因子」才使 ⟨m,p⟩ = 1（§3.9.4 docstring 整段在讲这一点）。故归一化**不是恒等化简，而是必需的正确性步骤**——删掉它，目标组只能拿到 `P/(1+P−T)` 而非 100%。把它集中在引擎层有两个好处：① Modifier 只负责「算出调制系数」，职责单一；② 边界（⟨m,p⟩ = 0）只需在一处处理。`dist` 参数保留在 `factor()` 中，因为因子依赖当前分布（`R_r` 的因子含 `p(T)`，见 §3.1.5.2 表）。

**因子向量按稀疏给出**：Modifier 只需列出被改动的卡，其余默认 1。组级操作给出整组的因子，单卡定向给出单张的因子，两者是同一种东西（这正是 §3.1.5 与「槽位收回操作内部」合流之处）。

#### 3.9.3 组件处置表

| 组件 | 处置 | 说明 |
|------|------|------|
| `PoolPitySpec.scope_cards` / `featured_cards` | **保留** | 卡集合，是分组的真相源；Modifier 据此确定 scope 与 target |
| `PoolPitySpec.scope_slots` / `featured_slots` / `card_to_slot` | **删除** | 槽位名与卡→槽位映射在卡级管道下无消费者。`_resolve_selected_slots` 的目标定位改为直接给出卡集合 `(selected,)` |
| `compute_scope_mappings` | **改造** | 只产出 `scope_cards` / `featured_cards`（及其反向索引），不再生成槽位名 |
| `aggregate_probs_by_rarity` | **删除** | 唯一调用点在 [banner.py:227](gacha_simulator/core/banner.py#L227)；同时清 `core/__init__.py` 的导出 |
| `_redistribute_scope(ctx, ratio, total, target_slots, scope)` | **替换** | 改为卡级版 `factor_redistribute(dist, scope_cards, target_cards, ratio)`（**4 参，定稿签名以 §3.9.4 的定义为准**；无 `base_weights`——组内按「当前比例」而非基础权重，理由见 §3.9.4 的三点差别 ②），产出因子向量而非新分布。**ISSUE-022**：原稿此表写 5 参（多 `base_weights`）、§3.9.4 写 4 参、§3.14.3 写关键字 `scope=`，三处互不兼容，已统一为 4 参 | <!-- REVIEW-R1-FIX: ISSUE-022 -->
| `infer_rarity_from_spec` | **保留**（用途收窄） | 2026-09-21 审查修正：其调用者中，pool.py:270/275 在 `aggregate_probs_by_rarity` 内、banner.py:242/244 与 :209 在 `scale_factors` 段内，**均在 S8 的删除范围内**；`_infer_rarity`（[pity.py:1344](gacha_simulator/core/pity.py#L1344)）用的是 `spec.ssr_ids` / `scope_cards` 而非本函数。故 S8 后其**唯一消费者**是 `banner.py` 的同一段——须在 S8 时确认是否还有保留价值 |
| `DrawInfo.scope_slots` / `featured_slots` / `card_to_slot` | **删除** | 随 `PoolPitySpec` 同步；`DrawInfo.base_probabilities` 语义由「槽位级」改为「卡级」 |
| `service/batch_simulator.py` | **改造** | [batch_simulator.py:183-192](gacha_simulator/service/batch_simulator.py#L183-L192) 解包 `compute_scope_mappings` 的五元组并构造含槽位字段的 `PoolPitySpec`——与 worst_impact 同属构造点，须同步改造。**2026-09-21 审查补** |
| `core/__init__.py` | **改造** | 除 `aggregate_probs_by_rarity` 外，`_redistribute_scope` 的导出（[core/\_\_init\_\_.py:20](gacha_simulator/core/__init__.py#L20)、`:117`）在 S8 替换后亦须一并处理。**2026-09-21 审查补**。**ISSUE-025（2026-09-22）**：同一 import 块（[core/\_\_init\_\_.py:9-20](gacha_simulator/core/__init__.py#L9-L20)）还导入并在 `:107-117` 的 `__all__` 中逐项导出 **10 个旧行为类**（`SoftStepBehavior` / `CounterBasedBehavior` / `HardPityBehavior` / `RotatingBehavior` / `RotatingSoftBehavior` / `RotatingCRBehavior` / `RotatingCRSoftBehavior` / `TargetedBehavior` / `TargetedSoftBehavior` / `SoftPityMixin`）——preset 化后这些符号退役，须同步删除其 import 与 `__all__` 条目，否则 ImportError 或留下指向已删符号的 re-export | <!-- REVIEW-R1-FIX: ISSUE-025 -->
| `tests/` | **改造** | **5 个文件**直接消费槽位结构（实测全库命中 5 个，原写「6 个」）：`tests/core/test_pity_rotating.py`（import 并调用 `_redistribute_scope`）、`tests/core/test_pity_integration.py` / `tests/test_pity.py` / `tests/core/test_pity_lifecycle.py` / `tests/core/test_pity_targeted.py`（构造带槽位字段的 `PoolPitySpec`）。**2026-09-21 审查补**；**2026-09-22 计数修正（ISSUE-GATE-file-list）** |
| `core/worst_impact.py` | **改造** | 第二处 `PoolPitySpec` 构造点（[worst_impact.py:506-548](gacha_simulator/core/worst_impact.py#L506-L548)），其中含**硬编码槽位名**（`{'ssr': ('ssr', 'ssr_featured')}`、`card_to_slot[cid] = 'ssr_featured'` 等回退分支）。S8 后只构造卡集合字段（`scope_cards` / `featured_cards` / `featured_ids` / `ssr_ids`）。**ISSUE-006（强制）：卡集合必须与该 spec 所属池的 reward id 对齐**——见下方专项 |
| `Pool._apply_probabilities` | **保留** | 接收卡级分布，语义不变 |
| `CompactResult` 输出字段 | **不受影响** | 已核对：无槽位相关字段（`draw_pity_names` 等均为池/保底名，非槽位名） |

<!-- REVIEW-R1-FIX: AUDIT-BREAK-5 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-6 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-8 -->
**跨文件同步清单（AUDIT-BREAK-5 / 6 / 8，强制，2026-09-22 补）**

上表的删除项在多处有并列的消费面，**只改「主调用点」即漏改**——漏改的失败形态是 `ImportError`（导入期或首次调用期），不是因为「没人用」而静默。逐处列明（行号为 2026-09-22 实测）：

**A. `aggregate_probs_by_rarity` / `infer_rarity_from_spec` 的删除面（S8，三处同步，缺一即 ImportError）**

| # | 位置 | 现状 | 处置 |
|---|------|------|------|
| 1 | [banner.py:209](gacha_simulator/core/banner.py#L209) | `draw()` 内**函数局部** import 两符号 | 随 `scale_factors` 段一并删除（局部 import 只在 `draw` 被调时执行，导入期不报错——漏改在首次抽卡时崩） |
| 2 | [banner.py:227](gacha_simulator/core/banner.py#L227)（调用）/ :229-246（`scale_factors` 段）/ :242、:244（slot 推导用 `infer_rarity_from_spec`）/ :257（`after_draw`） | 聚合 + 还原四件套 | §3.9.1 的「净删除」三件 + 改传卡级分布；:257 的 `after_draw` 调用**保留**（与概率管道无关，勿误删） |
| 3 | [pool.py:244](gacha_simulator/core/pool.py#L244)（`aggregate_probs_by_rarity` 定义）/ :270、:275（其内部对 `infer_rarity_from_spec` 的消费） | 函数定义与内部调用 | 删除该函数定义；`infer_rarity_from_spec` **保留**（§3.9.3 处置表已定），其 S8 后的唯一消费者需在 S8-2 落地时复核 |
| 4 | [core/\_\_init\_\_.py:3](gacha_simulator/core/__init__.py#L3) | `from .pool import … aggregate_probs_by_rarity, infer_rarity_from_spec` | 删除 `aggregate_probs_by_rarity` 的 import；**`infer_rarity_from_spec` 是否保留导出**取决于第 3 行的复核结论（若已无外部消费者则一并删除） |
| 5 | [core/\_\_init\_\_.py](gacha_simulator/core/__init__.py) 的 `__all__`（`'aggregate_probs_by_rarity'` 条目） | 逐项导出 | 同步删除条目；**`__all__` 与 import 块必须同批改**——只删 import 会留 `NameError`，只删 `__all__` 会留下对已删符号的 re-export |

**B. 槽位字段的第二个构造点（S8-5，`core/worst_impact.py`）**：[worst_impact.py:540-548](gacha_simulator/core/worst_impact.py#L540-L548) 构造 `PoolPitySpec`，并**硬编码槽位表** `scope_slots={'ssr': ('ssr','ssr_featured')}`（:512）与 `card_to_slot[cid]='ssr_featured'`（:515）。S8 删除槽位三字段后该处按 8 字段构造即 `TypeError`，且硬编码槽位表**语义须整体重写**。该构造点位于 `ref_pool = getattr(self,'_ref_pool',None)` 的**死分支**内（§3.9.3 ISSUE-006 专项已实测恒不执行），故失败形态是「S8 落地后一旦有人复活 `_ref_pool` 路径即崩」——**不能因为它是死分支而不改**。

**C. `core/__init__.py` 是 S8 与 S4-3 的**双目标文件**（AUDIT-BREAK-8）**：除 A 项第 4/5 行外，[core/\_\_init\_\_.py:9-20](gacha_simulator/core/__init__.py#L9-L20) 还从 `pity` 导入并在 `__all__` 中逐项导出 **10 个旧行为类 + `SoftPityMixin` + `_redistribute_scope`**（`SoftStepBehavior` / `CounterBasedBehavior` / `HardPityBehavior` / `RotatingBehavior` / `RotatingSoftBehavior` / `RotatingCRBehavior` / `RotatingCRSoftBehavior` / `TargetedBehavior` / `TargetedSoftBehavior` / `SoftPityMixin` / `_redistribute_scope`，ISSUE-025 已登记）。**须分别在不同子块处置**：`_redistribute_scope` 的导出随 **S8-4** 删（它是 S8 的替换对象）；10 个旧类与 `SoftPityMixin` 的 re-export 随 **S4-3**（preset 化完成、旧类在本包公共面上退役）删——**不随「发布前一次性移除旧类」才删**，否则从 S4-3 到发布前这段窗口里 `import gacha_simulator.core` 会带着一批已无 registry 入口的符号，诱惑新代码继续用旧类。删除 `__all__` 条目时须确认无 `from gacha_simulator.core import HardPityBehavior` 形态的调用方（`from gacha_simulator.core.pity import …` 不受影响，旧类本体保留到发布前）。

<!-- REVIEW-R1-FIX: ISSUE-006 -->
**ISSUE-006 专项：`worst_impact` 的卡集合必须与池内 reward id 对齐（强制）**

现状不一致（实测）：[worst_impact.py:508](gacha_simulator/core/worst_impact.py#L508) 用参考池的**原始卡 id** 生成 `scope_cards` / `featured_cards`，而同一 spec 的 `featured_ids` / `ssr_ids` 是**重命名后**的 `_wi_featured_{i}`，池子 `rewards` 的 id 也是 `_wi_featured_{i}`（[worst_impact.py:538-539](gacha_simulator/core/worst_impact.py#L538-L539)）——原始 id 根本不在分布里。

- **当前为何不崩**：槽位级管道下 `aggregate_probs_by_rarity` 只把 `scope_cards` 当加速缓存用（取不到时回退 `infer_rarity_from_spec` → `spec.ssr_ids`，后者恰含 `_wi_featured_0`）。
- **S8 后为何崩或静默归零**：`scope_cards` / `featured_cards` 成为管道**唯一真相源**（§3.9.4 的 `factor_redistribute` 直接 `sum(dist[c] for c in scope_cards)`）。实测该式对原始 id 抛 `KeyError`；若实现改用 `.get` 兜底，则所有保底调整**静默归零**。
- **顺带实测的死代码**：[worst_impact.py:504](gacha_simulator/core/worst_impact.py#L504) 的 `ref_pool = getattr(self, '_ref_pool', None)` 分支恒不执行（全库只有 `_ref_pool_entry`（[worst_impact.py:83](gacha_simulator/core/worst_impact.py#L83)、:373），无 `_ref_pool` 赋值点），即「用 `compute_scope_mappings` 在池上重建映射」这条**本可自愈的路径根本不走**。
- **改造口径**：S8 时按池重建卡集合（优先复活 `_ref_pool_entry` 路径，或统一把原始 id 重命名为池内 id），并**断言 `set(scope_cards[scope]) ⊆ {r.id for r, _ in pool.rewards}`**（**ISSUE-201**：`Pool.rewards` 的类型是 `List[Tuple[Reward, float]]`（[pool.py:152](gacha_simulator/core/pool.py#L152)），迭代元素是 `(Reward, prob)` 二元组——原稿写的 `{r.id for r in …}` 单变量解包形式（把元素当成 `Reward`）会立即抛 `AttributeError: 'tuple' object has no attribute 'id'`；同文件 [:162](gacha_simulator/core/pool.py#L162) / [:181](gacha_simulator/core/pool.py#L181) 的消费方式与 §3.9.1 的 `{r.id: p for r, p in pool.rewards}` 均按二元组解包，本处与之一致）。<!-- REVIEW-R1-FIX: ISSUE-201 -->
- **差异归因**：本改造会**改变最差影响分析的数值**（超出「与 M1 产物容差 1e-12 一致」的口径），须写入 §六 的差异归因清单，不得当作回归。

#### 3.9.4 卡级版重分配辅助

`_redistribute_scope` 的卡级对应物，是所有组级 Modifier 的公共落点：

```python
def factor_redistribute(dist, scope_cards, target_cards, ratio):
    """把 scope 内总量按 ratio 分给 target 组；两侧都写因子，故 ⟨m,p⟩ 恒为 1。

    关键：ratio >= 1（目标占满 scope）时，源侧必须**显式写 0 因子**而非跳过。
    跳过会让 ⟨m,p⟩ = 1 + (P − T) ≠ 1，归一化不再是恒等操作，目标组只能拿到
    P/(1+P−T) —— 实测 ratio=1、T/P=0.3 时目标仅占 scope 的 58.8% 而非 100%，
    直接破坏所有 Force 型路径（ForceFeatured / ForceSelected / G3）。
    """
    P = sum(dist[c] for c in scope_cards)
    T = sum(dist[c] for c in target_cards)
    tset = set(target_cards)
    m = {}
    if T > 0 and ratio > 0:
        k = ratio * P / T
        for c in target_cards:
            m[c] = k
    if P - T > 0:
        if ratio >= 1:
            for c in scope_cards:
                if c not in tset:
                    m[c] = 0.0
        else:
            k2 = (1 - ratio) * P / (P - T)
            for c in scope_cards:
                if c not in tset:
                    m[c] = k2
    return m or None
```

三处与现状的差别：① 目标与源都是**卡集合**而非槽位名；② 组内按**当前比例**（因子在组内是常数）而非基础权重，语义理由见 §3.1.5.2「组内比例的语义」；③ 返回因子而非分布。

**单卡定向的写法**：`target_cards = (selected,)`，`T` 即该卡当前概率，因子 `k = ratio * P / T` 把它抬到 ratio·P。这就是 S8 解决双 UP 定轨失真（§3.7）与 G3（UP 组排除已拥有）的机制：前者传单卡，后者传「未拥有的 UP 子集」。

#### 3.9.5 边界处理

| 情形 | 处理 | 依据 |
|------|------|------|
| `T == 0`（`target_cards` 非空但组内当前概率为 0） | 目标因子跳过；`ratio < 1` 时**源侧仍会写因子**（源侧被缩放、目标不动） | 语义上是「提升一个概率为零的集合」，物理上不应发生（§3.1.5.6）。**2026-09-21 审查修正**：原稿称「与现行早退路径一致」属**引用错位**——`total <= 0` 的早退在 `SoftStepBehavior`/`HardPityBehavior` 内（[pity.py:278-279](gacha_simulator/core/pity.py#L278-L279) 等），不在 `_redistribute_scope` 调用链上；且现码在此情形走 `f_total_w > 0` 的 else 分支（按槽位均分兜底，[pity.py:427-430](gacha_simulator/core/pity.py#L427-L430)），与 S8 的行为不同 |
| `P == 0`（scope 内全零） | 同上 | 同上 |
| `P - T == 0`（目标占满 scope） | 只给目标加因子，源侧写 0 因子（`ratio >= 1` 分支），不跳过 | **2026-09-21 审查修正**：原稿称「现状已有等价分支」不成立——`_redistribute_scope` 的保护对象是**基础权重和 `Σw`**（[pity.py:425](gacha_simulator/core/pity.py#L425)、[pity.py:436](gacha_simulator/core/pity.py#L436)），不是 `P − T`。实测 `dist={a:0.5, b:0.0, c:0.5}`、`scope={a,b}`、`target={a}`、`ratio=0.5` 时，现码把零概率槽 `b` 从 0 造到 0.25，卡级版保持 0——两者**不等价**，须在 S8 验收中专项覆盖 |
| **scope 键缺失**（如 `featured_cards` 无该稀有度键） | 一律用 `.get(scope, ())` 取集合，**空集合时返回 `None`（恒等）**；**禁止 `ctx.draw.scope_cards[self._scope]` 直接下标**。`compute_scope_mappings` 只对池中实际出现的稀有度建键、`featured_cards` 只对**有 featured 卡**的稀有度建键（实测 `scope_cards={'ssr':…,'sr':…}` 而 `featured_cards={'ssr':…}`，下标 `['sr']` 抛 `KeyError 'sr'`）。因 `PityDef.pools` 默认 `('*',)`，任何新增的无 featured 卡池（标准池等）都会让绑定该池的 `target_featured` / `rotating` / `targeted` 保底从「静默 no-op」变成**整场模拟崩溃**（ISSUE-016） | 旧实现统一 `.get(self._scope, ())` 并在为空时早退返回原分布（[pity.py:470-474](gacha_simulator/core/pity.py#L470-L474)、:507、:683） | <!-- REVIEW-R1-FIX: ISSUE-016 --> <!-- REVIEW-R1-FIX: ISSUE-012 -->
| **`⟨m,p⟩ ≠ 1`**（F 作用于 scope 低于最高稀有度时） | `_apply_factor` 的归一化**不是恒等操作**：它会把被 F 豁免的更高稀有度槽位整体缩放（实测 `ssr` 0.009 → 0.008919，偏差约 1%）。故 S8 与 S5 的产物**不是逐位可比**——S5 输出 Σ = 1.009、S8 输出 Σ = 1（ISSUE-012）。**缓解面（勿误判为回归）**：`pool.draw` 按 `_adjusted_total_weight` 抽样（[pool.py:207-226](gacha_simulator/core/pool.py#L207-L226)）隐含归一化，抽样分布本身可能不变；受影响的是管道内可见绝对值与消费 `before_draw` 原始输出的下游（`PityEngine.get_probabilities` 供策略层与 GUI，`_pity_cache` 亦缓存该 dict） | §3.1.5.2 验算段、§3.14.3 |
| 归一化后总量 ≤ 0 | 返回原分布 | `_apply_factor` 内的退化保护 |

#### 3.9.6 对只读查询的影响

`PityEngine.get_probabilities(pool_id, state, base)` 与 `before_draw` 走同一路径，S8 后同样改为卡级进出。`readonly=True` 时 Modifier 不推进计数（N1 纪律），但**因子照算**——否则「查询」与「抽卡前」会给出不同分布，破坏 P16 的查询/修改分离语义。

**接线（§1.5）与 S8 的交互**：接线引入的 `_pool_order` 独立排序视图作用于「按哪个顺序遍历保底」，与本节改造的「单个保底内部如何算概率」是正交的两层，互不影响。

---

### 3.10 状态可见性与 G3 真实建模（2026-09-21 裁决）

#### 3.10.1 四类状态的处置

Modifier 在 `factor(ctx, ...)` 中能读到什么，是表达力的一个独立维度（与分布空间正交）。裁决如下：

| 状态 | 真实需求 | 裁决 | 依据 |
|------|---------|------|------|
| 本保底的状态 | 大量 | 保持 | 计数、标志、命定值等 |
| **其他保底的状态** | **零** | **不纳入**，且架构上关闭（3.10.3） | 手册全量查证（2026-09-21）：所有「清零 / 重置 / 联动 / 互斥」描述均属三类——保底自身计数被重置、同名保底跨池共享、资源生命周期（P77）；**无一处需读其他保底状态** |
| **GachaState**（持有 / 资源） | G3 一处 | **开放**，经 `reads` 显式声明（3.10.2） | CLAUDE.md §二「精确建模原则」：G3 不接受 pool 层近似 |
| 时间 | 零 | 不开放 | 时间型机制属 Banner lifecycle 层，P61 已覆盖 |

两处最像「跨保底读取」的机制已逐一排除：

- **绝区零 G5**：`hard(max_triggers=1)` 与 `targeted` 同时作用于同 scope（[手册:560](docs/主流抽卡游戏卡池机制配置转换手册.md#L560)）——这是**执行顺序**问题，由 §1.5 裁决的 `priority` 处理，不涉及状态读取。**ISSUE-032 注**：`max_triggers` 是手册的散写，`PityDef` **无该字段**（见 §3.1.3），此处引用的是「福利保底与 targeted 同 scope 共存」这一**形态**，不代表该配置键已存在
- **终末地计数器 3**：「获得首个 UP 后 240 抽」看似依赖另一保底的触发事件，实为**自身 Flag 门控**（出 UP 时置位，计数器仅在置位后推进），单保底内即可表达

#### 3.10.2 `reads` 声明机制

外部状态经配置**显式声明**才可读，避免隐式耦合。

```toml
[[pity]]
name = "bh3_precision_up"
type = "hard"
scope = "ssr"
target_featured = true
threshold = 50
reads = ["acquired"]        # 声明：本保底需要读「玩家持有」
```

```python
@dataclass
class PityContext:
    draw: DrawInfo
    current: Dict[str, float]
    state: 'PityState'                           # ← ISSUE-103：仍是原始 PityState，不是 StateView
    external: Optional['ExternalView'] = None    # 按 PityDef.reads 填充；未声明则为 None

class ExternalView:
    """外部状态的只读视图——只暴露查询方法，不暴露可变对象。"""
    def owns(self, card_id: str) -> int: ...          # 该卡持有张数
    def balance(self, resource_id: str) -> float: ...
```
<!-- REVIEW-R1-FIX: ISSUE-103 -->
**`PityContext.state` 保持 `PityState`（ISSUE-103，强制，2026-09-22 修复）**：命名空间隔离**只由 `view` 形参承担**（骨架的 `mod.apply(ctx, self._view, out, readonly)` / `mod.factor(ctx, self._view, out, readonly)`，§3.1.4 / §3.9.2），`ctx.state` 仍是原始 `PityState`。原稿该字段注记为 `'StateView'`，与骨架的实际传参、与三处闭合性互相矛盾。三条理由：

1. **叶子层依赖方向**：`PityContext` 已迁入 `pity_primitives.py`（§3.1.6 叶子层，「仅依赖标准库」「不 import `pity`」），而 `StateView` 是 §四 登记在 `core/pity.py`（编排层，S9）的符号。叶子层 dataclass 的字段注记指向编排层类，等于让叶子层的类型契约反向依赖编排层。
2. **构造点**：`PityContext` 由 `PityEngine` **每池构造一次并复用**（[pity.py:1274](gacha_simulator/core/pity.py#L1274) / [:1303](gacha_simulator/core/pity.py#L1303) / [:1335](gacha_simulator/core/pity.py#L1335) 均为 `PityContext(draw=draw_info, current=…, state=state)`）。单一每池 ctx 无法承载「每保底一个命名空间」的 StateView；若坚持该字段为 StateView，须把 ctx 的构造主体从 `PityEngine` 改到 `Pity`（每保底一 ctx），并把该构造点登记进 §四 与 §3.9.2。
3. **闭合性**：`ctx.state` 只是**同一份账本的另一条通道**，跨保底读取须靠纪律关闭（§3.10.3 已补）。

选 1+2+3 中代价最小且不动架构的一条：**保留字段为 `PityState`、隔离全部由 `view` 承担、`ctx.state` 的读取用纪律禁止**（迁移项见 §3.10.3）。

**校验（第三道防线的同类）**：`reads` 中的名称必须是已知状态源（`acquired` / `resources`），否则 `config_toml._build_pity()` 抛 `ConfigError`。**`time` 不列入白名单**——时间型机制属 Banner lifecycle 层（P61 已覆盖），保底层不需要读时间（§3.10.1）。**2026-09-21 审查修正：原稿 `ExternalView` 含 `now()`、白名单含 `time`，与 §3.10.1 的裁决自相矛盾**理由与 `scope` 白名单相同——**防止拼写错误导致保底静默失效**。

**填充通路（2026-09-21 审查补）**：`GachaState` 位于 `Banner.draw(state, ...)` 与服务层，而 `PityEngine` 目前只接收 `PityState`。S9 的取值方式为**给调度入口加可选参数**：

```python
PityEngine.before_draw(pool_id, state, base_probabilities, external=None)
PityEngine.get_probabilities(pool_id, state, base_probabilities, external=None)
```

既有调用方不传即保持原行为，故 §六 的「调度层接口签名不变」应理解为**既有调用形式不变**，而非参数列表冻结。

<!-- REVIEW-R1-FIX: ISSUE-009 -->
<!-- REVIEW-R1-FIX: ISSUE-010 -->
<!-- REVIEW-R1-FIX: ISSUE-013 -->
**填充者改由 `GachaService` 担任（ISSUE-010，2026-09-22 修复）**：原稿指定 `Banner.draw`，但已核 `Banner.draw` 的签名为 `draw(self, state, pity_engine, pity_state, pool=None)`（[banner.py:195](gacha_simulator/core/banner.py#L195)），它虽同时持有 `GachaState` 与 `PityState`，却**既无 `card_defs` 也无 `initial_counts`**（`banner.py` / `pool.py` 全文无这些字段），拿不到构造 `ExternalView` 所需的全部数据。故填充点上移到 `GachaService`（同时持有 `self.card_defs` 与现场汇总的 `_initial_counts`，见下方 ISSUE-009），按该池各保底 `reads` 的并集构造 `ExternalView` 后再送达调度入口。

> **2026-09-28 重梳后本条已作废**：其前提「`Banner.draw` 拿不到 `card_defs` / `initial_counts`」随 `initial_counts` 提升为 `GachaState` 字段而消失——视图的全部材料现都在 state 上，故填充点**就地**（两条通道各调 `state.external_view()`）。保留本段作历史记录。

<!-- REVIEW-R1-FIX: ISSUE-033 -->
**并集的来源：`reads` 的运行期落点与引擎访问器（ISSUE-033，2026-09-22 补齐；ISSUE-010 只解决了「谁填」，未解决「从哪取」）**

`GachaService` 在 [gacha_service.py:467](gacha_simulator/service/gacha_service.py#L467) 手上只有 `_pity_engine` / `qualified_key` / `_initial_counts` / `card_defs`，**缺一个「取某池全部保底 `reads` 并集」的入口**；`Pity.__init__` 原稿也没有 `reads` 形参。补齐如下：

- **承载**：`Pity` 新增 `reads` 形参并存 `self._reads`（§3.1.4 骨架已写，**归 S3**：只是构造形参，S3 阶段无人写入）——由 `PityDef.reads` 经 `create_behavior` 注入（**归 S9**），与 `priority` / `pools` 同一透传口径。**字段与解析的步骤**：`PityDef.reads` + `config_toml` 解析 + `batch_simulator` / `retreat_config` 三处透传**整体归 S9**（原稿把透传放在 M1 的 S4b，而字段定义在 M2 的 S9，实施时字段不存在）。
- **汇总接口**：`PityEngine` 新增只读访问器 `get_reads_for_pool(pool_key) -> tuple[str, ...]`，内部取该池的保底列表（与 `get_behaviors_for_pool()` **同一来源**，P82 接线后即独立排序视图）后对其 `reads` 取**并集**（去重，顺序按该池保底顺序稳定）。**`GachaService` 只调这一个接口**，不再自行遍历保底列表——否则「谁填」又退化为服务层复制调度层的池路由职责。
- **空并集语义**：该池所有保底都未声明 `reads` 时返回 `()`，`GachaService` 据此**不构造** `ExternalView`（保持 `external=None`），与「未声明 `reads`」路径语义一致。
- **归属登记**：两项均在**编排层** `core/pity.py`——§3.1.6 编排层行与 §四 `core/pity.py` 行已登记；`PityDef.reads` 的字段与解析仍在 `config_store.py` / `config_toml.py`（§四 原有两行不变）。
- **§六 已补对应 S9 断言**（「`reads` 并集来源」条）。

**送达路径定稿（ISSUE-027，2026-09-28 重梳）**：`ExternalView` 要抵达 Modifier，经 `PityContext.external`。原稿的两难（「经 `Banner.draw` 传」与「不改 `Banner.draw` 签名」互斥）源于一处**归属错位**：`ExternalView` 的构造材料之一 `_initial_counts` 被放在 `GachaService` 的**局部作用域**，而不是 `GachaState` 上。

**修正：把 `initial_counts` 提升为 `GachaState` 的字段。** 它语义上就是「本场模拟的初始持有」，属模拟状态一等公民；当前它以参数形式在四处传递（`add_card` / `total_holding` / milestone 闭包捕获 / 服务层局部变量），既冗余，又把「视图构造点」绑死在持有该局部变量的那一层。

**修正后的路径（两层，且不扩张 `Banner.draw` 的签名）**：

1. **`GachaState.external_view() -> ExternalView`**（新增方法）：视图的材料全在 state 上（`acquired` + `initial_counts` + `resources`），构造成本 O(1)。
2. **两条通道各自就地构造**（见下方 AUDIT-BREAK-9 表）：
   - 通道 A：`Banner.draw` 手上**已有** `state`（[banner.py:195](gacha_simulator/core/banner.py#L195)），直接 `pity_engine.before_draw(..., external=state.external_view())`
   - 通道 B：`StrategyContext.state` 即同一 `GachaState`（[strategy.py:96](gacha_simulator/core/strategy.py#L96)），`get_pity_probabilities` 同样补 `external=self.state.external_view()`
3. **调度入口加可选参**：`PityEngine.before_draw(pool_id, state, base, external=None)` 与 `PityEngine.get_probabilities(...)` 同形（既有调用不传即保持原行为，与 §六「既有调用形式不变」相容）。
4. **`reads` 门控下移到 `Pity`**：调用方**总是**传 view（成本可忽略），由 `Pity` 按自身 Modifier 的 `reads` 声明决定「是否把它暴露给 Modifier」——未声明则传 `None`。于是 `get_reads_for_pool()` 的并集查询从「两个填充点的前置条件」降为「`Pity` 内部的一次判断」，**显式性约束不变**（未声明 `reads` 的保底仍拿不到 `external`）。

**为什么优于原方案 (a)**：原方案设了两个填充点（A 走 `Banner.draw` 新增形参、B 在 `StrategyContext` 内自行构造），但**通道 B 的 `_initial_counts` 来源在计划中从未定过**——`StrategyContext` 只持有 `GachaState`，拿不到 `GachaService` 的局部变量；同时「两条通道口径一致」只能靠约定维持。修正后两条通道用的是**同一个 state 上的同一个方法**，口径一致由构造保证而非约定，且省掉了 `Banner.draw` 的形参扩张与两处并集查询。

**架构论证：这不是给 `GachaState` 加异类，而是补齐对称性（2026-09-28）**

项目里三类初始值，改造前只有一类没有归宿：

| 初始值 | 配置来源 | 归宿 | 传递方式 |
|--------|---------|------|---------|
| 资源 | `ConfigStore.initial_resources` | `GachaState.resources` | 构造时传 |
| **卡持有** | `CardDefEntry.initial_count` | **无归宿** | 局部变量 + 四处传参 |
| 保底状态 | `PityDef` 的四个 `*_init` | `PityState` | 专用构造器 `_build_pity_state_init()` |

`resources` 与 `acquired` 在语义上对称——两者都等于「配置给出的初始值 + 模拟中的变化」：`当前资源 = initial_resources + 收支变化`、`当前持有 = initial_counts + 获得变化`。`initial_resources` 同样是配置派生值，却从无「不该进 state」的争议。故本次改造不是引入异类，而是**让 `acquired` 与 `resources` 形式对称**；保底状态由 `PityState` 承载、有专用构造器，本就独立，不受影响。

**已评估并否决的替代方案**：

| 方案 | 否决理由 |
|------|---------|
| 引擎持有 provider | 引入「保底引擎依赖服务层」的倒置依赖；provider 还需动态取「当前 state」，时序复杂 |
| 两条通道各自从 `GachaService` 取 | 改动面为两处（`Banner.draw` 加形参 + `StrategyContext` 加字段），且两处必须保持同步——**把「初始持有」复制到两个位置、靠约定维持一致**，比方案 A 更零散 |
| `ExternalView` 改收查询函数 | 构造点问题原封不动（仍要有人构造该函数） |

方案 A 是唯一「一处改动、两条通道自动覆盖」的：两条通道都持有 `GachaState`，视图的全部材料就在其上。原 (b) 方案（绕开 `Banner.draw`）仍不采用，理由不变（复制调度职责、与单一入口冲突）。

**`owns()` 的持有口径 = 含初始持有（ISSUE-009，2026-09-22 裁决）**：`GachaState.acquired` 明确**不含**初始持有（[state.py:142](gacha_simulator/core/state.py#L142) 的 docstring 写「模拟中获得的该卡数量（不含初始持有）」，只有 `total_holding(card_id, initial_counts)`（[state.py:146-148](gacha_simulator/core/state.py#L146-L148)）含初始持有）。而 `initial_count` 是 `CardDefEntry` 字段（[config_store.py:257](gacha_simulator/core/config_store.py#L257)），由 `GachaService.run_simulation` 汇总为局部变量 `_initial_counts`（[gacha_service.py:310-315](gacha_simulator/service/gacha_service.py#L310-L315)），并行路径同样现场构造（[batch_simulator.py:398-408](gacha_simulator/service/batch_simulator.py#L398-L408)）——两处都**没有挂到 `GachaState` 上**（`GachaState` 构造只传 `resources`）。故：

- `ExternalView.owns(card_id)` 的语义定为 **`total_holding` 口径（含初始持有）**。理由：G3 的机制是「**已获得的装备**从 UP 组中排除」，玩家开局就持有的装备同样属「已获得」；若只算模拟内获得，配置了 `initial_count` 的 UP 装备会被判为「未拥有」，G3 在这些卡上静默失效且无任何报错，正是 CLAUDE.md §二「精确建模原则」反对的语义打折。
- 实现上 `owns` 内部执行 `state.initial_counts.get(c, 0) + state.acquired.get(c, 0)`（`initial_counts` 已是 `GachaState` 字段，2026-09-28 重梳前为「送到 `GachaService` 填充点」）。
- §六 的 G3 专项须加一条**带 `initial_count` 的用例**。

**`ctx.external is None` 的兜底与策略层查询路径（ISSUE-013，2026-09-22 修复）**：`external` 缺省为 `None` 的既有路径至少有一条——[strategy.py:178](gacha_simulator/core/strategy.py#L178) 的 `StrategyContext.get_pity_probabilities` → `PityEngine.get_probabilities(pool_id, state, probs)`。两条处置同时落地：

1. **硬性兜底**：Modifier 内**必须先判 `ctx.external is None` 再读外部状态**，为 `None` 时退化恒等（语义与「未声明 `reads`」一致）。否则任何配了 `reads` 的保底（G3 崩坏3 精准补给）在策略层查询路径上是 `AttributeError` 崩溃，而不是「保持原行为」。
2. **策略层填充**：`StrategyContext` 本身持有 `GachaState`（[strategy.py:100](gacha_simulator/core/strategy.py#L100)，`acquired` 属性在 :113），S9 时由 `StrategyContext` 自行构造 `ExternalView` 并填入该次查询调用（与 `GachaService` 同一构造口径）。若实施时选择不做，则必须登记为**已知差异**（策略层看到的概率与真实抽卡管道不一致，破坏 §3.9.6 强调的查询/修改分离语义 P16），不得默默留空。

§四 的波及范围须相应补 `core/strategy.py`（S9）。

<!-- REVIEW-R1-FIX: AUDIT-BREAK-9 -->
**两条送达通道必须都填（AUDIT-BREAK-9，强制，2026-09-22 补）**

`ExternalView` 要抵达 Modifier，必须同时走通**两条互不重叠的通道**——只做 `Banner.draw` 那一条，S9 的验收（GDR 数值变化）不可达：

| # | 通道 | 调用链 | 填充点 | 现状（实测） |
|---|------|--------|--------|-------------|
| A | 抽卡管道 | `GachaService` → [`banner.draw(state, _pity_engine, pity_state, pool)`](gacha_simulator/service/gacha_service.py#L467) → `PityEngine.before_draw` | **就地**：`Banner.draw` 调 `state.external_view()` | 2026-09-28 重梳：原定「`GachaService` 填充 + `Banner.draw` 末位加 `external=None` 形参」，现改为就地构造（`Banner.draw` 本就持有 `state`），**不再新增形参** |
| B | **独立概率查询** | `StrategyContext.get_pity_probabilities`（[strategy.py:161-179](gacha_simulator/core/strategy.py#L161-L179)，结果缓存于 `_pity_cache`）→ `PityEngine.get_probabilities(pool_id, self._pity_state, probs)` | **就地**：同为 `self.state.external_view()` | **完全不经过 `Banner.draw`**。2026-09-28 重梳：原方案下本通道的 `_initial_counts` **来源未定**（`StrategyContext` 拿不到服务层局部变量），提升为 state 字段后此缺口闭合 |

要点（三条）：

1. **通道 B 是真实消费面而非旁支**：`strategies/builtin/pity_reserve.py:52` 的 SSR 概率阈值判定即经 `ctx.get_pity_probabilities(qualified_key)` 取分布（[pity_reserve.py:52](gacha_simulator/strategies/builtin/pity_reserve.py#L52)）。通道 B 不填 `ExternalView` 时，任何配 `reads` 的保底在该路径上恒走「退化恒等」分支——**S9 的 G3 与 GDR 数值验收全部只经过通道 A 时仍会通过**，缺陷在验收盲区（这正是本条必须写成「强制两条都填」而不是「登记已知差异」的原因）。
2. **口径同一**：两条通道构造 `ExternalView` 必须用同一份 `GachaState` 与同一份 `_initial_counts`（`owns()` 口径 = `initial_counts.get(c,0) + acquired.get(c,0)`，ISSUE-009）。`StrategyContext` 逐轮重建（[gacha_service.py:412](gacha_simulator/service/gacha_service.py#L412)）、`_pity_cache` 的生命周期因此是**单轮**——但同一轮内 `ctx` 的构建时刻**早于**该轮的批次抽卡，故通道 B 反映的是「本轮开始时的持有」，通道 A 反映的是「该抽发生时的持有」。这是**采样时刻差异、不是口径差异**，不得据此认为两通道不一致；但 §六 的「查询与抽卡前分布一致」断言（§3.9.6 / P16）须限定在**同一时刻**比较（同一 `ctx` 构建时刻下的 `get_probabilities` 与紧随其后的 `before_draw`），否则会误判为回归。
3. **`reads` 并集（ISSUE-033）同为其前置**：通道 B 的填充者 `StrategyContext` 同样需要「某池全部保底 `reads` 的并集」来判定是否构造 `ExternalView`——它**必须经 `PityEngine.get_reads_for_pool(pool_key)`**（ISSUE-033 已定 `GachaService` 如此），不得自行遍历 `_pity_engine.behaviors`。空并集时保持 `external=None`，与「未声明 `reads`」路径语义一致。

配套（§七 / §六 已同步）：S9-2 的目标文件补 `core/strategy.py` + `service/gacha_service.py`；S9-4 的验收命令须**两条通道各一条**用例——通道 A 用既有 `tests/service/test_gacha_service.py -k external`，通道 B 新增 `tests/core/test_pity_integration.py -k "reads and strategy"`（配 `reads` 的池经 `ctx.get_pity_probabilities` 取到的分布与同刻 `before_draw` 一致，且**不是**退化恒等）。

**在形式化中的位置**：资产是历史的确定函数 `w_t = W(h_t)`，读它只是读历史的一个摘要，故**不扩大 §3.1.5 的表达类**（仍是计数器自动机可计算的因果函数）。它扩大的是**方便性**（无须把资产编码进 PityState）与**显式性**（依赖进配置、进快照、可校验）。

#### 3.10.3 关闭跨保底读取（StateView）

现状有一个**无守卫的口子**：`PityState` 全局共享，Modifier 拿到的是整个对象，`state.get('别的保底名', 'key', 0)` 今天就能跑通且不报错。既然真实需求为零（3.10.1），处置是**架构上关闭**，而非把它正规化。

<!-- REVIEW-R1-FIX: ISSUE-004 -->
```python
class StateView:
    """限定在单个保底命名空间内的只读视图。

    ISSUE-004（2026-09-22 修复）：**不得在构造期缓存命名空间 dict**。
    PityState.data 是惰性创建的——构造期 `data.get(name, {})` 若该命名空间尚不存在
    （depends_on 依赖方在构造期不写 _active），会拿到一个与 state 脱联的空 dict，
    此后引擎 `state.set` 新建的命名空间与该 view 无关，所有读取恒返回 default 且不报错。
    故 get() 每次现取；配合 Pity._rebind_state 重建 view（§3.1.4），
    worker 内同一 engine 连跑 N 场模拟时每场读到的都是当场的账本。
    """
    def __init__(self, state: 'PityState', name: str):
        self._state = state
        self._name = name
    def get(self, key, default=None):
        return self._state.data.get(self._name, {}).get(key, default)
```

Modifier 的 **state 形参**（即骨架里的第二个实参 `view`，与 `ctx.state` 不是同一个通道，见下）由 `PityState` 改为 `StateView`，读他人键天然返回 default。「跨保底读」由「靠纪律禁止」变为「架构上做不到」，且**不破坏任何现有机制**（真实需求为零；2026-09-21 独立审查已全库枚举 `PityState` 读取点：Modifier 内的读取全部落在自身命名空间，Modifier 外的读取不经 `state` 参数，不受影响）。

<!-- REVIEW-R1-FIX: ISSUE-103 -->
**`ctx.state` 是同一份账本的另一条通道，须显式关闭（ISSUE-103，强制）**：`PityContext.state` 仍是原始 `PityState`（§3.10.2 的字段注记已改回），故 Modifier 若写 `ctx.state.get('别人的保底名', 'key', 0)` 今日依旧跑通——**「架构上做不到」只对 `view` 形参成立，对 `ctx.state` 不成立**，后者靠纪律关闭。三条落地项：

- **纪律**：Modifier **只经 `view` 读状态**，禁止经 `ctx.state` 读任何状态键（**含自身命名空间**——自身也走 `view`，避免两套读法并存后难以审计）。写入侧不受影响：Tracker 的 `commit(ctx, state, name, …)` 接收的仍是原始 `state`（§3.1.1 协议表）。
- **三处存量迁移（S9 必改项）**：`TargetedBehavior` 的三处 `ctx.state.get(self._name, "selected_card")`（[pity.py:651](gacha_simulator/core/pity.py#L651) / [:663](gacha_simulator/core/pity.py#L663) / [:677](gacha_simulator/core/pity.py#L677)）——targeted preset 化后改由 `ForceSelectedModifier` 经 `view.get("selected_card")` 读取（`selected_card` 由策略层 `NonDrawAction` 写入**自身**命名空间，`view` 看得见，跨保底读仍被关闭）。另 [pity.py:532](gacha_simulator/core/pity.py#L532) 的 `PityContext(draw=ctx.draw, current=modified, state=ctx.state)`（`SoftPityMixin.before_draw` 的 fork）随 mixin 退役一并消失，不构成迁移项。
- **登记**：S9-1 任务项、§四 `core/pity.py` 行、§六 S9 口径均同步本条。

**命名空间绑定已定稿（2026-09-21 审查补；2026-09-22 定稿，见下方「view 按零件命名空间分配」段）**：组合型 `_soft` 族存在**两个**命名空间——`SoftPityMixin._init_soft_pity` 以 `name + '_soft'` 构造内部 `SoftStepBehavior`（[pity.py:527](gacha_simulator/core/pity.py#L527)），而 mixin 自身的 `_counter` 在 `name` 下（[pity.py:528](gacha_simulator/core/pity.py#L528)，`before_draw` 的 `v = self._counter.incr()` 即被 `SoftStepBehavior` 消费的软计数）。`StateView` 的 `name` 取哪个**不再留到 S9 临场决定**，否则「读自己」也会返回 default，落进本文反复强调的静默失效模式。

<!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
**定稿：view 按「默认 + 零件命名空间」两级分配（ISSUE-GATE-dependency-order，2026-09-22，强制）**

| 层 | 命名空间 | 承载 |
|----|---------|------|
| **默认 view** | `self._name` | 未声明 `namespace` 的零件一律用它；**soft 族的软计数在此**（对齐旧 mixin 的 `X.counter`，[pity.py:528](gacha_simulator/core/pity.py#L528)），故 `BoostModifier` 读软计数不经额外 view |
| **零件命名空间 view** | `part.namespace` | 声明了 `namespace` 的零件（Tracker / Modifier / Lifecycle）由 `Pity` 按 `StateView(state, part.namespace)` 建独立 view，调用该零件时传**它自己的 view** |

三条配套定稿：

1. **`_soft` 族保留 `X_soft` 命名空间**：该族 preset 声明一个命名空间载体 Tracker（`namespace=f'{name}_soft'`，无计数语义、不影响概率），使 `X_soft` 命名空间存在并与 ISSUE-023 的快照口径一致（旧实现该空间只有 `_active` 一个键，[pity.py:118-121](gacha_simulator/core/pity.py#L118-L121)）。
2. **`_active` 写入的作用域推广**：`Lifecycle.initialize` 的写入对象由「本保底命名空间」推广为「**本保底声明的全部命名空间**」（非 `depends_on` 时都写 `True`），否则 `X_soft: {_active: True}` 无处产生，ISSUE-023 的快照断言与「统一 `_active` 写入」互相牵制。
3. **`_view` 的语义不变**：§3.1.4 骨架的 `self._view` 是**默认 view**（`self._name`）；`_rebind_state` 重建默认 view 的同时按同一 state 重建各零件命名空间 view（否则 worker 内连跑 N 场模拟时零件 view 指向旧账本，与 ISSUE-004 同一失效模式）。

> **为何不给「soft 计数并入 `X` 单命名空间」留口子**：ISSUE-023 已论证 `X_soft` 必须原样保留（快照逐场一致的前提），两种写法择一写死，本计划取上表方案；实施时不得既合并命名空间、又保留原断言。

**两个命名空间必须原样保留（ISSUE-023，强制）**：这不只是 S9 的读取侧命名问题，它同时是 **S1–S5 等价性验收的前提**——§六 S1–S5 要求「新引擎输出的状态快照与旧类**逐场完全一致**」，而 `PityState.to_dict()` 输出**全部**命名空间。代码事实：内部引擎 `SoftStepBehavior(name + '_soft', state, …)` 经 `CounterBasedBehavior.__init__` 写 `_active` Flag（[pity.py:118-121](gacha_simulator/core/pity.py#L118-L121)），故旧实现在 `X_soft` 命名空间里留下 `{_active: True}`，加上 mixin 自身在 `X` 下的 `counter`，快照共含**两个**命名空间。因此 `_soft` 族 preset 化时须**原样保留 `X_soft` 命名空间及其中的 `_active` 键**（内部 soft Tracker 的命名空间名取 `f'{name}_soft'`），**不得**把 soft 计数合并进单一命名空间、也不得改名。若实施时确要合并，必须**先把该快照差异登记进 §六 的差异归因清单并相应放宽 S1–S5 的「完全一致」断言**——两条路择一，不得既合并又保留原断言。

**不影响 `depends_on`**：激活传播由引擎在 `PityEngine.after_draw` 中执行（`state.set(dep_name, "_active", True)`），不经过 Modifier，故不受 StateView 影响。

#### 3.10.4 G3 真实建模（崩坏3 精准补给）

机制（[手册 §7.3](docs/主流抽卡游戏卡池机制配置转换手册.md#L959)）：精准补给每 50 抽必出 UP 装备，但**已获得的装备从 UP 组中排除**。

**为什么不能沿用 pool 层近似**：pool 层过滤（把已拥有的卡从 reward 列表移除）会让**每次抽卡**都不出它们，而真实机制只作用于「50 抽 UP 保护」这一个触发点——普通抽卡仍可产出已拥有的装备。按「精确建模原则」这是语义打折，不接受。手册原先将其归为 pool 层，是架构约束下的权宜。

**实现**：新增 Modifier 零件 `ForceNotOwnedModifier`，即 §3.1.2 表中 `ForceSelectedModifier` 的**动态目标**变体：

<!-- REVIEW-R1-FIX: ISSUE-016 -->
<!-- REVIEW-R1-FIX: ISSUE-013 -->
<!-- REVIEW-R1-FIX: ISSUE-GATE-3-dependency-order -->
```python
class ForceNotOwnedModifier(Modifier):       # ISSUE-GATE-3-dependency-order：继承公共基类
    """把 scope 内总量强制导向「未拥有的目标卡」子集（G3）。"""
    def __init__(self, scope, field='featured_cards'):
        self._scope = scope
        self._field = field

    def factor(self, ctx, view, dist, readonly):
        # ISSUE-013：external 缺省为 None 的既有路径（策略层 get_probabilities）必须先兜底，
        # 否则 AttributeError 崩溃；为 None 时退化恒等（语义与「未声明 reads」一致）。
        if ctx.external is None:
            return None
        pool_cards = getattr(ctx.draw, self._field).get(self._scope, ())
        if not pool_cards:
            return None            # scope 键缺失——空集合，返恒等（ISSUE-016，§3.9.5）
        target = tuple(c for c in pool_cards if ctx.external.owns(c) == 0)
        if not target:
            return None            # 全部已拥有——退化，返回恒等（§3.1.5.6）
        # ISSUE-016：一律 .get(scope, ())，禁止直接下标（无 featured 卡的池无该键，会 KeyError）
        return factor_redistribute(dist, ctx.draw.scope_cards.get(self._scope, ()), target, 1.0)
```

配套：配置加 `reads = ["acquired"]`；`BEHAVIOR_REGISTRY` 注册新 preset（或作为 `hard` preset 的可替换末位 Modifier——**待 S9 实施时定**）。

**「全部已拥有」的退化分支：待确认（2026-09-21 审查修正）**。手册 §7.1 / §7.3 / §21 均未描述该情形，**无信源**。当前拟定为「返回恒等」（无可导向目标），但这意味着该次 50 抽的「必出 UP」不发生，与手册「每 50 抽必 UP 装备」的字面表述可能冲突。按「不凭空断言」纪律标为**待确认**，实施前需查证游戏机制或由用户裁定。原稿直接判「合理选择」并为其设验收，属越权断言。

**与 §3.7 槽位粒度约束的关系**：G3 同时需要 S8（子集定向）与本节（状态可见性），两者都到位才可表达。

---

### 3.11 架构的表达能力与边界（2026-09-21 新增）

> **为什么单列一节**：P64 的定位是「通用保底引擎」，其价值取决于「能表达什么、不能表达什么」是否清晰可判。此前的边界信息散落在 §3.1.5.6（数学边界）、§3.7（范围边界）、§3.9.5（实现边界）、§3.10.1（状态裁决）四处，遇到新机制时判定成本高、且容易误判（本轮审查即发现 `F` 算子的定义被写错）。本节把三类信息集中，并给出**判定方法**而非仅列清单。

#### 3.11.1 表达能力（三层，互相正交）

| 维度 | 能力 | 形式化位置 |
|------|------|-----------|
| **状态空间** | `Z^k × {0,1}^m`：k 个计数器 + m 个标志，数量由 preset 静态声明 | §3.1.5.1 |
| **分布空间** | **卡级**任意子集上的乘性因子调制（S8 前为槽位级） | §3.1.5.2、§3.1.2 D20 |
| **状态可见性** | 本保底状态 + `reads` 声明的外部状态（`acquired` / `resources`）；**不含**其他保底状态 | §3.10 |
| 抽样模型 | 从分布独立抽样（`ξ ~ p`） | §3.1.5.1 |

**判定方法**：给定一个新机制，问三个问题——
1. 它的历史依赖能否用**有限个计数器/标志**声明？（能 → 状态空间够）
2. 它的概率操作能否写成**因子向量**？（能 → 分布空间够；注意因子可依赖当前分布）
3. 它需要读的信息是否在**本保底状态或 `reads` 白名单**内？（是 → 状态可见性够）

三问皆「是」则可表达，且实现方式是「新增 Tracker 或 Modifier 零件，不改架构」（§二目标）。

#### 3.11.2 边界（三类，各附判定依据）

| 边界 | 内容 | 依据 |
|------|------|------|
| **非抽样型抽卡** | 结果不是「从分布独立抽样」的机制（如异环棋盘：掷骰前进、落点由当前位置决定，属马尔可夫转移）。入口在 **pool 层**（`pool.draw`）而非 pity 层 | [手册 §20.2](docs/主流抽卡游戏卡池机制配置转换手册.md#L2039) |
| **跨保底状态耦合** | 「A 触发后修改 B 的状态」不能表达（`StateView` 架构上关闭，§3.10.3）。替代：`depends_on`（激活传播）、状态合并、或同名共享 | §3.10.1 裁决；手册全量查证「零真实需求」 |
| **求值顺序敏感** | 因子依赖当前分布时，换序一般改变结果（§3.1.5.3）。这是**语义属性**（约束冲突），非实现缺陷；处置方式为 §1.5 裁决的接线 + `priority` | §3.1.5.5 推论表 |

**另有一条数学边界**（`⟨m,p⟩ = 0` 等退化情形）见 §3.1.5.6，属实现层约定，不影响能力判定。

#### 3.11.3 不复用的邻近能力（避免误判）

- **时间型机制**（开池后 N 天概率提升等）属 Banner lifecycle 层（P61），不属保底
- **累抽奖励**（里程碑、补偿箱）属 milestone 层（P58），旁路注入而非改概率
- **池子可用性 / 切换**属 Banner lifecycle；**资源到期**属 `[resources.lifecycle]`（P77）
- **已获装备过滤**（G3）**属保底层**（2026-09-21 归属更正，见 §3.10.4）——它与 pool 层的 reward 分发相邻但不同：后者影响每次抽卡，前者只影响保底触发点

---

### 3.12 组合正确性验收（2026-09-21 新增）

> **问题**：P64 的核心承诺是「任意 Tracker × 任意 Modifier 自由组合，不再写新类」，但 §六 的验收全是**等价性**——验证 10 个 preset 与旧类一致。这只是「旧能力没有退化」，**完全没有验证新能力**。一个 `soft + rotating_cr + targeted` 三重组合在旧架构下没有对应的类，新架构声称能表达，却无任何测试证明它能正确工作。
>
> 组合空间无限，用例测试覆盖不了，必须换方法。

**3.12.1 不变式断言（性质测试）**

对随机生成的零件组合，断言以下性质恒成立：

| 不变式 | 内容 |
|--------|------|
| 归一性 | `Σ p = 1`（容差 1e-12）。**例外（ISSUE-011，2026-09-22 修复）**：当参与本次 `before_draw` 的算子含 scope **低于最高稀有度**的 `F` 型（hard）时，其语义为「全池置零 + 更高稀有度槽位还原原值」（§3.1.5.2），此时恒有 `Σp = 1 + p(被豁免的更高稀有度槽位) ≠ 1`（实测 `hard(scope='sr')` 输出 `{ssr:0.006, ssr_featured:0.003, sr:1.0, r:0.0}`，Σ = 1.009）。而 scope 取值只要在 `[rarities].ranks` 内即合法（config_toml 白名单只查这个），故 M1 槽位级管道下**对合法配置直接断言 `Σp = 1` 会抛假警报**。该断言须按 scope 感知重述：`Σp = 1 + Σp(被 F 豁免的高稀有度槽位)`；无 F 参与时退化为 `Σp = 1` | <!-- REVIEW-R1-FIX: ISSUE-011 -->
| 非负性 | 所有卡的概率 ≥ 0 |
| 因子合法性 | 所有因子 ≥ 0；因子在 p 的支撑上不全为 0 |
| 状态键合法 | Tracker 写入的键在其声明集内（`StateView` 保证读，写侧需另查） |
| 确定性 | 同种子 + 同配置 → 逐位相同 |

**3.12.2 合法组合判据**

不是所有组合都有意义，需要定义「合法」并在构造期检查（与 `_validate_behaviors` 的四条规则同层）：

- 同一键被两个 Tracker 声明的冲突（如两个 `CounterTracker` 都写 `counter`）
- Modifier 引用了不存在的状态键
- Lifecycle 依赖图成环（**现状：无成环检测**；`_build_activation_graph`（[pity.py:1205-1229](gacha_simulator/core/pity.py#L1205-L1229)）只建图 + 校验 `depends_on` 指向存在的名字，**不做环检测**）
<!-- REVIEW-R1-FIX: ISSUE-019 -->
<!-- REVIEW-R1-FIX: ISSUE-001 -->
<!-- REVIEW-R1-FIX: ISSUE-015 -->
- **池交集校验当前不可用（ISSUE-019，2026-09-22 修复）**：原稿称「现有 `_build_activation_graph` 已部分覆盖」，实测其第二段校验**恒为假阳性**——它用 `getattr(bh, '_pools', ())` 取双方池集合，而全库没有任何 behavior 设置 `_pools`（grep 只命中 [pity.py:1224-1227](gacha_simulator/core/pity.py#L1224-L1227) 这三行读取点）。故 `src_pools` / `dst_pools` 恒为空集，`'*' not in ()` 为真、交集为空为真，`warnings.warn` 对**每一条** `depends_on` 配置无条件触发。处置（**已定稿，2026-09-22 第八轮**）：由 **S3-1** 给 `Pity.__init__` 设 `self._pools = pools`（由 `PityDef.pools` 注入，§3.1.4 骨架已含 `pools` 形参）使该警告恢复语义。**原稿写「S1/S3」二选一，现写死为 S3-1**：`Pity` 类要到 S3 才新建，S1a 阶段无处可补（该任务项已自 S1a 移出，见 §七 S1a / S3-1）。**「删除这段恒真分支」的备选已否决**：该警告对 `depends_on` 跨池错配的运维价值高于其误报成本，删除等于放弃唯一一处跨池一致性检查。**已知过渡态**：S1a 至 S2b 期间（`Pity` 尚未落地）该警告仍对每条 `depends_on` 恒真触发，属预期行为、不是回归；S3-1 落地后恢复语义，§六 有对应断言。<!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
- **标志分派前提（ISSUE-001）**：本节的构造期检查与 `_validate_behaviors`（[pity.py:933-985](gacha_simulator/core/pity.py#L933-L985)）同层，后者依赖 `is_soft` / `is_hard` / `is_event_driven` 三个由 `btype` 推导的标志（§3.2 首段）。若将来重构该分派，须与本节判据合并设计，不得单独改动其一

**3.12.3 与等价性验收的分工**

| | 验证什么 | 方法 |
|---|---|---|
| 等价性（§六 主线） | 旧能力未退化 | 与旧类逐场对比 |
| 组合正确性（本节） | 新能力可用且自洽 | 性质测试 + 合法组合判据 |

两者互补：等价性是「守」，组合正确性是「攻」。

---

### 3.13 不变式运行时校验（2026-09-21 新增）

> **问题**：架构里有一批**隐式不变式**（分布归一、组内比例关系、因子非负、Tracker 只读自己的键、计数相位），**破坏了不会报错**。§五 风险表自己承认：「两者共同点是均不报错、只让结果静默偏移」。
>
> 「静默失效」在本系统反复出现：scope 写错、`reset` 取值非法、`targeted` 缺 `selected_card`、CR 短路条件写错——每一次都靠人肉排查。

**设计**：加一层**可开关**的校验（调试模式或测试模式下启用，生产关闭），在每次 `before_draw` / `after_draw` 后断言关键性质，破坏时立即抛出并指明位置（保底名 + 键 + 期望/实际）。

```python
class InvariantChecker:
    """可开关的不变式校验——仅在 debug/test 模式启用。"""
    def check_after_before_draw(self, pool_id, dist, engine): ...
    def check_after_after_draw(self, pool_id, state, engine): ...
```

**校验项**（初版）：

| 层 | 项 |
|----|-----|
| 分布 | `Σp = 1 + Σp(被 F 豁免的高稀有度槽位)`；所有 `p ≥ 0`。**ISSUE-011（2026-09-22 修复）**：原稿写死 `Σp = 1`，但 scope 低于最高稀有度的 `F` 型（hard）语义上就保留更高稀有度槽位原值（实测 `hard(scope='sr')` Σ = 1.009），且该 scope 合法。若保持原样，checker 一旦启用即对**合法配置**抛假警报，而 M1 的交付定义又要求 S11 到位 | <!-- REVIEW-R1-FIX: ISSUE-011 -->
| 状态 | Tracker 写入的键在声明集内；计数型计数器的值单调（除重置外） |
| 因子 | 非负；在 p 的支撑上不全为 0 |
| 生命周期 | `_active` 只由**构造期 `Lifecycle.initialize` 的初始写入**、引擎的激活传播与本保底的退役动作写入（**ISSUE-202**：构造期写入若不列入白名单，该不变式会对**每条**非 `depends_on` 保底在构造期写 `_active=True` 报假警报） | <!-- REVIEW-R1-FIX: ISSUE-202 -->

**与性能的关系**：校验只在开关打开时运行，且检查项为 O(卡数)，对生产路径无影响。§五 风险表的相关条目可据此更新缓解手段。

---

### 3.14 条件外置（2026-09-21 新增）

> **本节是对 §3.1.2 Modifier 表的修订**：把「条件」从各 Modifier 内部提出来成为独立对象，**效果部分保持不变**。§3.1.2 的表格保留作历史形态与术语索引，实施以本节为准。
>
> **方案取舍**：本轮在三种方案中选定「只拆条件」。另两种（保持现状、彻底骨架化）的比较见 3.14.5。

#### 3.14.1 问题：条件散落在 Modifier 内部

§3.1.2 表里 Modifier 的「触发条件」列各不相同（`state[flag] == True` / `counter >= threshold` / `fate 就绪` / 恒真），且都写在类的 `factor` 方法里。后果有三：

- **条件不可组合**：要表达「两个前提同时成立才触发」必须写新类
- **条件不可单测**：测判断逻辑要构造完整 Modifier 与上下文
- **G14 要写新类**：战双命运池的「counter ≥ 随机阈值 T」与「counter ≥ 常数」形状不同，按现状须新增一个 Modifier

而 §3.1.5.4 的构造表早已把结构写成三元表达式（`hard` 的算子 = `c ≥ τ ? F : id`），那个条件部分就是这里要提出来的东西。

#### 3.14.2 设计：条件作为包装器

**不改 Modifier 的效果实现**，只把内部的 `if` 换成一层包装：

```python
class ConditionalModifier(Modifier):        # ISSUE-GATE-3-dependency-order：继承 §3.9.2 的公共基类
    """给内层 Modifier 加触发条件；条件不成立时返回 None（恒等）。"""
    def __init__(self, modifier, condition):
        self._mod, self._cond = modifier, condition

    def factor(self, ctx, view, dist, readonly):
        if not self._cond.test(ctx, view, dist):
            return None
        return self._mod.factor(ctx, view, dist, readonly)

    def apply(self, ctx, view, dist, readonly):
        # ISSUE-GATE-dependency-order：M1（S12 起至 S7）骨架调 `apply`（§3.1.4 骨架 /
        # §3.1.2 历史形态），S8 之后骨架改调 `factor`。**两个名字都必须转发**——
        # 骨架对 modifiers 列表逐项无守卫调用，缺任一即每个抽卡入口 AttributeError，
        # 等价于全部保底不可用（与 rebind 同一失效模式）。
        # 转发目标不会落空：内层 Modifier 自 S8 起只写 `factor`，其 `apply` 由公共基类
        # `Modifier` 的默认实现提供（§3.9.2），故本转发在 S8 之后仍有定义。
        return self._mod.apply(ctx, view, dist, readonly)

    def rebind(self, state, name):           # ISSUE-029：**必须转发**，不得吞掉
        """S12 后 preset 里的 Modifier 一律被本类包裹，`Pity._rebind_state` 对
        `modifiers` 列表逐项无守卫调用 `rebind`——不转发则首次抽卡即
        `AttributeError: 'ConditionalModifier' object has no attribute 'rebind'`，
        发生在每个抽卡的调度入口，等价于全部保底不可用。"""
        self._mod.rebind(state, name)
```
<!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
> **本类的转发面（定稿）**：`apply`（M1 骨架调用）/ `rebind`（P75 纪律）/ `factor`（S8 起骨架调用，本类须新增同名转发）三者**缺一不可**；`factor` 的转发在 S8 落地时随接口一起加，不得只改内层 Modifier 而漏掉包装器。
>
> **内层 `apply` 的承载处（ISSUE-GATE-3-dependency-order，2026-09-22）**：`self._mod.apply(...)` 的目标**不是**「内层对象必须自己写 `apply`」，而是**公共基类 `Modifier` 的默认实现**（§3.9.2，由 `factor` 导出）——S8 之后内层只写 `factor`、`apply` 由基类提供，故本类**无须**在 S8 时删掉 `apply` 转发（备选「S8 删除 `apply`」已否决）。**同步纪律**：§3.2 / §3.14.2 的 Modifier 示例一律继承 `Modifier`，裸类形态会让该转发在 S8 之后落空。<!-- REVIEW-R1-FIX: ISSUE-GATE-3-dependency-order -->
<!-- REVIEW-R1-FIX: ISSUE-029 -->

各 Modifier 去掉内部判断，只剩因子计算。以 `ForceFeaturedModifier` 为例：

```python
class ForceFeaturedModifier(Modifier):      # ISSUE-GATE-3-dependency-order：继承公共基类——
                                            # apply / rebind 由其默认实现提供（§3.9.2）
    """把 scope 内总量占满 featured 组。何时生效由外层条件决定。"""
    def __init__(self, scope):
        self._scope = scope

    def factor(self, ctx, view, dist, readonly):
        # ISSUE-016 / ISSUE-020：一律 .get(scope, ())，禁止 ctx.draw.scope_cards[self._scope]
        # 直接下标（§3.9.5 全局禁止规则）。compute_scope_mappings 只对池中实际出现的稀有度建
        # scope_cards 键、只对「有 featured 卡」的稀有度建 featured_cards 键，无 featured 卡的池
        # （新增标准池、无 UP 的稀有度）该键不存在，直接下标抛 KeyError → 整场模拟崩溃。
        return factor_redistribute(dist, ctx.draw.scope_cards.get(self._scope, ()),
                                   ctx.draw.featured_cards.get(self._scope, ()), 1.0)
```

> **空集合的语义（ISSUE-016 / ISSUE-020）**：`scope_cards` / `featured_cards` 取不到该 scope 键时返回 `()`，`factor_redistribute` 在目标集为空时返回 `None`（退化恒等，见 §3.1.5.6 与 §3.9.4 的 `return m or None`）。口径与 §3.9.2 的 G3 代码块、§3.9.5 的「scope 键缺失」边界行、§六 的 S8 边界断言三处一致。

preset 组装时套上条件：

<!-- REVIEW-R1-FIX: ISSUE-005 -->
```python
def _preset_rotating(pdef):                      # ISSUE-005：必须是工厂函数（带 pdef 形参），不得模块级赋值
    return dict(                                 # ISSUE-030：逐条可配字段一律取自 pdef，硬编码即等于把配置退化成常量
        lifecycle=build_lifecycle(pdef),         # ISSUE-301：生命周期唯一转换点（§3.1.3）
        trackers=[FlagTracker(judge="featured", hit="clear", miss="set", flag="guaranteed")],
        modifiers=[
            ConditionalModifier(ForceFeaturedModifier(pdef.scope), FlagCondition("guaranteed")),
            BaseRatioModifier(pdef.scope),                # 无条件
        ],
        flags={"guaranteed": pdef.guaranteed_init},       # 初值走状态声明（H2），不加 Tracker 形参
    )
```
<!-- REVIEW-R1-FIX: ISSUE-030 -->
<!-- REVIEW-R1-FIX: ISSUE-031 -->
<!-- REVIEW-R1-FIX: ISSUE-301 -->

> **形态纪律（ISSUE-005，强制）**：本节与 §3.2 的 preset 写法**统一为工厂函数**。原稿此处写模块级赋值 `_preset_rotating = dict(...)`、§3.2 写 `def _preset_rotating(): return dict(...)`，而本节开头又声明「实施以本节为准」，三者不一致，且模块级赋值会引入跨保底 / 跨模拟的状态串扰（理由见 §3.2 对应段落）。以工厂函数形态实施。**签名以 §3.2 定稿为准（ISSUE-030）**：一律 `def _preset_xxx(pdef)`，`pdef` 的逐条可配字段（`scope` / `threshold` / `counter_init` / `guaranteed_init` / `deltas` / `fate_*` / `cr_*` / `reset` 等）由工厂消费，preset 只保留真正的常量（如 `judge` / `hit` / `miss` 这类语义固定项）。

| Modifier（保留） | 因子计算 | 组装时的条件 |
|---|---|---|
| `ForceFeaturedModifier` | 占满 featured 组 | `FlagCondition('guaranteed')` |
| `ForceNonFeaturedModifier`（G1） | 占满非 UP 组 | `FlagCondition('forced_loss')` |
| `ForceSelectedModifier` | 占满定轨卡 / 子集 | `Or(FlagCondition('guaranteed'), FateReadyCondition(τ))` |
| `ForceNotOwnedModifier`（G3） | 占满「UP ∩ 未拥有」 | `Always()` |
| `ThresholdForceModifier`（hard） | **F 语义**（见 3.14.3） | `CounterCondition('counter', τ)` |
| `BoostModifier`（soft） | `factor_redistribute(dist, 源集∪目标集, 目标集 T, ratio=(T+βQ)/(T+Q))`——**ISSUE-022**：统一为 §3.9.4 的 4 位置参形态（原稿写关键字 `scope=`，与形参名 `scope_cards` 不匹配且缺 `dist` / `target_cards`，照抄即 TypeError）。语义：源集 Q = scope \ T，故 `scope_cards = Q ∪ T`、`P = T + Q`，目标占 scope 比例 `ratio = (T+βQ)/(T+Q)` 即「从 Q 取比例 β 转给 T」 | `Always()` | <!-- REVIEW-R1-FIX: ISSUE-022 -->
| `BaseRatioModifier` | 按当前比例（恒等） | `Always()` |
| `InterceptModifier`（CR） | 随机拦截 | **例外，见下** |

> **本表与 S8 的时序（ISSUE-101 补）**：本表「因子计算」列中的 `factor_redistribute` 是 **S8 之后**的卡级形态。S12 现排在 S8 **之前**（同属 M1，§七），故 S12 只交付**条件包装**这一层，`BoostModifier` 等内层 Modifier 的因子计算在 M1 内仍沿用槽位法（§3.9 的过渡期纪律：S1–S5 期间本节内容全部不实施）。「组装时的条件」一列与 S8 无关，S12 起即生效。

**Condition 类族**（纯读，无副作用）：`Always` / `Flag` / `Counter`（≥ 阈值）/ `FateReady` / `Ratio`（某组占比 ≥ r）/ `Owned`（持有数 == n）/ `RandomThreshold`（G14：counter ≥ 随机阈值）；组合子 `And` / `Or` / `Not`（与 `stop_condition` 的树形结构同构）。

**`InterceptModifier` 是唯一例外**：它的「条件」要消费全局 `random`（H4 协议：`cr_base_rate` 与 `cr_state_probs` 两处掷骰），而 `ConditionalModifier` 要求条件纯读。故它保持内部判断并单列，理由写入实现注释。

**不进 TOML**：Condition 作为代码级 building block，与 P69 的复合策略同构（`_strategy_key = None` 哨兵）。依据是 §3.7 已裁决的「`type="custom"` 完全声明式 TOML 状态机不实现（过度设计）」。

#### 3.14.3 等价性依据（2026-09-21 实跑）

本方案**不改任何因子的计算路径**，只改「何时调用它」（判断从类内部移到包装器，求值时机相同）。故等价性是结构性保证，以下是 `factor_redistribute` 的正确性实测，供 S8 与本节共用。

**R 类（单槽目标）：与现行逐卡一致，无需附加前提。**

```
场景：scope=(ssr, ssr_featured)，featured=(up)，base=(0.005, 0.004, 0.05, 0.941)
对比：现行（_redistribute_scope 槽位级 + banner 的 scale_factors 还原） vs 卡级 factor_redistribute

ratio=1.0 : 现行 {ssr_featured:0.009, ssr:0.0, sr:0.05, r:0.941}      新 同  ✓
ratio=0.5 : 现行 {ssr_featured:0.0045, ssr:0.0045, ...}               新 同  ✓
ratio=0.25: 现行 {ssr_featured:0.00225, ssr:0.00675, ...}             新 同  ✓
（逐卡差异 < 1e-15）
```

原因：R 类的目标恒为**单槽**（`compute_scope_mappings` 每稀有度只生成一个 featured 槽；`_resolve_selected_slots` 亦返回单槽元组）。单槽时不存在「槽间分配」这一层，槽内无论按基础权重还是按当前比例都退化为同一个式子。

**F 类（hard）：与 R 不等价，其因子计算不可复用 `factor_redistribute`。**

```
hard(scope='ssr') 触发时，现行输出 {ssr_featured: 1.0, ssr: 0.0, sr: 0.0, r: 0.0}
若改用 R_1                         →  {ssr_featured: 0.009, ssr: 0.0, sr: 0.05, r: 0.941}
```

差 100 倍，非精度问题：`R_1` 只让 **scope 内部**重新分配（SSR 总量仍 0.9%），`hard` 要求**全局占满**（SSR 占 100%）。按比例抽样下前者根本不是「必出」。

F 另有两点与 R 不同（§3.1.5.2 的表已按实现记录）：① 范围是**全池置零 + 更高稀有度豁免**（`hard(scope='sr')` 实测 Σ=1.009 ≠ 1，SSR 原值被保留）；② **槽间**按基础权重分配（`target_featured=False` 时目标含两个槽），而 R 类在卡级下按当前比例。第 ② 点在「槽间比例 = 基础权重比例」时与旧实现一致，但该不变量会被 R 操作破坏（如 `R_1(featured)` 把非 featured 槽清零），故不能依赖。

**结论**：`ThresholdForceModifier` 保留自己的 F 语义实现，不改为 `factor_redistribute` 调用。这是本方案与「彻底骨架化」的关键差别（3.14.5）。

#### 3.14.4 Condition 与 EventMatch 的分工（命名区分）

系统里有两处判断，**不合并**，且在命名上分开以免被误读为「同一概念的两份实现」：

| | **Condition**（本节的） | **EventMatch**（Tracker 侧，不新增抽象） |
|---|---|---|
| 位置 | Modifier 内，`before_draw` | Tracker 的 `commit`，`after_draw` |
| 输入 | 状态 + 当前分布 | 本次抽卡的结果（出了哪张卡） |
| 作用 | 决定「要不要改概率」 | 决定「状态怎么转移」 |

不可合并的技术原因：抽后那一刻 `PityContext.current` 是空字典（[pity.py:1335](gacha_simulator/core/pity.py#L1335) 构造时传 `current={}`），分布参数在抽后无意义。强行统一会得到 `test(ctx, view, dist=None, event=None)` 的万能谓词，读者须先判断时机才知道哪些参数有效。

#### 3.14.5 方案取舍：为什么只拆条件

本轮在三种方案间比较（第四种「拆到最碎」因概念数超过收益未纳入）：

| 维度 | A 保持现状 | **B 只拆条件（选中）** | C 彻底骨架化 |
|------|-----------|----------------------|-------------|
| 代码单元 | 7 类 | 7 类 + 条件族 + 1 包装器 | 3 骨架 + 条件族 |
| 读者需理解的概念 | 1（Modifier） | 2（Modifier、Condition） | 3（+ 四参数） |
| 新增机制成本 | 写一个新类 | 写一个类**或**一个条件 | 给一组参数 |
| **等价性风险** | 无 | **低**（因子代码一行不动） | 中（因子代码重写，需逐类重验） |
| 条件的可组合 / 可单测 | ✗ | ✓ | ✓ |
| G14 落位 | 要写新类 | 换一个 Condition | 换一个 Condition |
| preset 声明长度 | 短 | 中 | 长 |
| 声明可读性 | 类名即语义 | 好（类名 + 条件） | 中（须查参数表） |
| 消除「仅 target 不同」的类间重复 | ✗ | ✗ | ✓ |

**B 与 C 的收益差距只在最后一行**：`ForceFeatured` / `ForceNonFeatured` / `BaseRatio` 三者只差一个 target，C 会合并它们，B 保留。而这一重复是**既有的**，非拆条件所引入。

**C 的代价**在「等价性风险」一行：它要重写每类的因子计算并逐类重验。2026-09-21 的审查已证明这类重写容易引入静默错误（`factor_redistribute` 的 `ratio=1` 分支即为实例，且未被既有测试捕获）。

**选 B 的理由**：收益 ÷ 风险最优。它拿到了条件外置的全部实质收益（G14 可扩展、条件可组合可单测、触发时机显式化），代价仅一层包装器，且因子路径不动、无需重验。

**不封死 C**：将来若「仅 target 不同」的重复确实碍事，可在条件已外置的基础上再合并内层，那时只动一件事。

#### 3.14.6 修订范围

| 位置 | 改动 |
|------|------|
| §3.1.2 | Modifier 表标注「已由 §3.14 修订」；新增 Condition 类族清单；各 Modifier 去掉内部条件判断 |
| §3.2 | preset 映射表补「组装时的条件」一列（**已落正文**，ISSUE-031；同时按 ISSUE-030 补 `pdef` 形参与取值来源表） |
| §3.3 | G1 inverse preset 用 `ConditionalModifier(ForceNonFeatured, FlagCondition('forced_loss'))`（**已落正文**，ISSUE-031；同时按 ISSUE-030 补 `pdef` 形参） |
| §3.4 | 软保底去掉内部条件（`Always`），ratio 仍按 3.14.2 表 |
| §3.10.4 | G3 用 `ConditionalModifier(ForceNotOwned, Always())` |
| §四 | 新增 `core/pity_condition.py`（Condition 类族，~80 行） |
| §七 | GATE 加 S12（**M1 内，排在 S2 之后、S4 之前**——ISSUE-101；M2 因此收窄为 S8 + S9） |

**风险**：① Condition 必须纯读无副作用（由 §3.13 的不变式校验覆盖）；② `RandomThresholdCondition`（G14）需在状态中持久化随机阈值，属 Tracker 侧的扩展，与条件本身正交；③ 包装器多一层对象，preset 声明变长（见 3.14.5 的可读性行）。

---

## 四、波及范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/pity_primitives.py` | **新增**（**S1a** + **S8** + **S9**） | **叶子原语层**（§3.1.6）：`Counter` / `Flag` / `PityState` / `DrawInfo` / `PityContext` / `LifecycleConfig`（自 `pity.py` 迁出）+ **类型集合常量 `_SOFT_TYPES` / `_HARD_TYPES` / `_EVENT_DRIVEN_TYPES`**（自 `CounterBasedBehavior` 的**类属性**升为**模块级常量**，[pity.py:114-115](gacha_simulator/core/pity.py#L114-L115)（`_SOFT_TYPES` / `_HARD_TYPES` 在 :112 / :113）；§3.1.4 骨架的 `Pity(PityBehavior)` 不继承该基类，裸名引用即 `NameError`，故三者必须随叶子层落在此文件）+ `factor_redistribute`（S8 起）。**S9（ISSUE-034）**：`PityContext` 加 `external` 字段——`PityContext`（[pity.py:31](gacha_simulator/core/pity.py#L31)）已迁至本文件，该字段的定义与编辑点**在此行**，不在 `core/pity.py`。`pity.py` 保留 re-export，既有导入路径不变。**ISSUE-301**：`LifecycleConfig` **保留**（不是删除项），角色由「`PityBehavior` 的 `lifecycle` 形参类型」改为「Lifecycle 对象的构造参数袋」，由三个 Lifecycle 实现的基类持有（§3.1.3） | <!-- REVIEW-R1-FIX: ISSUE-002 --> <!-- REVIEW-R1-FIX: ISSUE-301 --> <!-- REVIEW-R1-FIX: ISSUE-024 --> <!-- REVIEW-R1-FIX: ISSUE-034 -->
| `core/pity_tracker.py` | **新增**（**S1b** + **S1c** + **S1d**，逐块独立 commit） | Tracker 家族（CounterTracker/FlagTracker/StreakTracker/FateTracker）+ Lifecycle（四类：`AlwaysActive` / `OnceActive` / `DependentActive` / `DependentOnceActive`——**两个正交维度的四个组合**，2026-09-28 修正，~140 行）。**ISSUE-202**：Lifecycle 的协议为**五方法**——`initialize` / `is_active` / `should_deactivate` / `deactivate` / `rebind`；`initialize(state, name)` 承担 `_active` 的构造期写入（`Always` 维写 `_active=True`，`Dependent` 维空实现），由 `Pity.__init__` 在创建 `_view` 前调用（§3.1.3 专段 / §3.1.4 骨架）。**ISSUE-301**：Lifecycle 以 `LifecycleConfig` 为构造参数袋（共用基类持 `self._cfg`）——`deactivate_on_early_hit` 属性由 `cfg` 代理、`depends_on` 由 `Dependent` 维同源读出 | <!-- REVIEW-R1-FIX: ISSUE-202 --> <!-- REVIEW-R1-FIX: ISSUE-301 --> |
| `core/pity_condition.py` | **新增**（**S12**，**落在 M1 内**——排在 S2 之后、S4 之前，ISSUE-101 / §七） | Condition 类族（7 个内置 + 3 个组合子），纯读无副作用；配套 `ConditionalModifier` 包装器（~80 行）。**为何必须在 M1**：S4 的 preset 工厂（§3.2 / §3.3 / §3.14.2）与 S5 的等价性测试一律消费 `ConditionalModifier` / `FlagCondition` / `CounterCondition` / `Always`，本模块留在 M2 会让 M1 唯一可照抄的 preset 代码引用不存在的模块，S4/S5 无法闭合 | <!-- REVIEW-R1-FIX: ISSUE-101 --> |
| `core/pity_modifier.py` | **新增**（**S2a** + **S2b**，逐块独立 commit） | Modifier 家族（BoostModifier/ForceFeaturedModifier/ForceNonFeaturedModifier/ForceSelectedModifier/InterceptModifier/ThresholdForceModifier/BaseRatioModifier）（~150 行）。**S8**：实现形态切换为乘性因子向量（§3.1.5.1） |
| `core/invariants.py` | **新增**（**S11**） | `InvariantChecker`（可开关的不变式运行时校验，§3.13）：`check_after_before_draw(pool_id, dist, engine)` / `check_after_after_draw(pool_id, state, engine)`，覆盖分布 / 状态 / 因子 / 生命周期四层；生产关闭。**2026-09-22 补登记（ISSUE-GATE-file-list）**：原稿只在 §3.13 给类名、§四 无任何落点行，实施者无从判断该新建模块还是并入 `core/pity.py`；现定稿为**独立新模块**（与 `Pity` 骨架解耦，便于生产关闭时零开销） | <!-- REVIEW-R1-FIX: ISSUE-GATE-file-list -->
| `core/pool.py` | 修改（**S8**） | 删除 `aggregate_probs_by_rarity`（[pool.py:244](gacha_simulator/core/pool.py#L244)，唯一调用点在 banner）+ `core/__init__.py` 导出行。**ISSUE-026（2026-09-22 修正文件名）**：原稿把「`compute_scope_mappings` 改造为只产出卡集合」记在本行，但该函数**定义在** [pity.py:1040](gacha_simulator/core/pity.py#L1040)，`pool.py` 只有 `infer_rarity_from_spec` / `aggregate_probs_by_rarity`——本行不含该函数的改造，改造点见下方 `core/pity.py` 行 | <!-- REVIEW-R1-FIX: ISSUE-026 -->
| `core/__init__.py` | 修改（**S8**） | **ISSUE-025**：删除 `aggregate_probs_by_rarity`（[core/\_\_init\_\_.py:3](gacha_simulator/core/__init__.py#L3)、`:101`）与 `_redistribute_scope`（`:20`、`:117`）的导出，**并删除 10 个旧行为类的 import 与 `__all__` 条目**（[core/\_\_init\_\_.py:9-20](gacha_simulator/core/__init__.py#L9-L20) / `:107-117`：`SoftStepBehavior` / `CounterBasedBehavior` / `HardPityBehavior` / `RotatingBehavior` / `RotatingSoftBehavior` / `RotatingCRBehavior` / `RotatingCRSoftBehavior` / `TargetedBehavior` / `TargetedSoftBehavior` / `SoftPityMixin`）。**保留**仍在的对外符号：`PityBehavior` / `PoolPitySpec` / `PityState` / `PityEngine` / `DrawInfo` / `PityContext` / `Counter` / `Flag` / `LifecycleConfig`（**ISSUE-301：保留，角色改为 Lifecycle 构造参数袋，不是退役项**） / `BEHAVIOR_REGISTRY` / `create_behavior` / `compute_scope_mappings`。**待定**：preset 化后是否新增对外符号（如 `Pity` / Tracker 家族 / `StateView`），实施时登记 | <!-- REVIEW-R1-FIX: ISSUE-025 --> <!-- REVIEW-R1-FIX: ISSUE-301 -->
| `core/state.py` | 修改（**S9**，2026-09-28 重梳） | ① 新增 `initial_counts: Dict[str, int]` 字段（本场模拟的初始持有）——原为 `GachaService.run_simulation` 的局部变量与四处传参；② `add_card` / `total_holding` 的 `initial_counts` 形参改为**可选**（缺省取 `self.initial_counts`，既有调用保持兼容）；③ 新增 `ExternalView` 类（只读查询视图，暴露 `owns` / `balance`；`now()` 已于 §3.10.2 删除，`time` 不在白名单）与 `GachaState.external_view() -> ExternalView`（O(1) 包装）。**ISSUE-009：`owns()` 口径为「含初始持有」**——`state.initial_counts.get(c,0) + state.acquired.get(c,0)`，两者同为一个 state 的字段，口径一致由构造保证。**行为等价的三条判据（2026-09-28 查证）**：① **`clone()` 必须带该字段**（**独立验收项见 §六**）——`run_simulation` 首行即 `initial_state.clone()`，漏带则初始持有在克隆时丢失、P63 溢出分档静默出错；② **真实构造点唯一且每场新建**——[batch_simulator.py:430](gacha_simulator/service/batch_simulator.py#L430)（其上方注释已要求跨模拟隔离、每场新建 GachaState），与 `_initial_counts` 的「每场从 `card_defs` 现算」语义等价；③ **两个 `add_card` 调用点**（[milestone.py:211](gacha_simulator/core/milestone.py#L211)、[gacha_service.py:481](gacha_simulator/service/gacha_service.py#L481)）继续传参即行为不变，仅缺省值改为 `self.initial_counts`。另注：`total_holding` 目前**全库无调用点**（grep 仅命中定义），其签名变化零风险 |
| `core/config_store.py` | 修改（**S9**） | `PityDef` 新增 `reads: tuple[str, ...] = ()`。**归属（ISSUE-GATE-dependency-order）**：字段定义 + 解析 + 透传链**整体归 S9（M2）**，S4b 不再触碰 `reads`（M1 内无任何消费者） | <!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
| `core/config_store.py` | 修改（**S4-4**） | `PityDef` 新增 `max_triggers: int = 0`（0 = 不限）——`OnceActive` 的配置接线（ISSUE-032，2026-09-27 裁决） |
| `core/config_toml.py` | 修改（**S4-4**） | `max_triggers` 解析（`_build_pity`）+ round-trip 写回（`_pitydef_to_toml`）+ 负值抛 `ConfigError` |
| `gui/config_panel.py` | 修改（**S7a**） | 新增「触发次数上限」数值控件（0 = 不限），`_apply_pity_edit` 与 load/save 路径同步该键 |
| `core/config_toml.py` | 修改（**S9**） | `reads` 的解析 + 状态源白名单校验（未知名称抛 `ConfigError`）、round-trip 写回 |
| `core/pity.py` | 修改（**S9**） | `StateView` 限定 Modifier 的状态视野（**ISSUE-034：`StateView` 是 S9 在本文件新增的符号，定义见 §3.10.3，归属登记见 §3.1.6 编排层行**）；**`PityContext.external` 的编辑点不在此行**——`PityContext` 已迁至 `pity_primitives.py`，见上表该行（ISSUE-034）。**ISSUE-103**：`PityContext.state` 的字段注记**保持 `PityState`**（隔离只由 `view` 承担）；本行为 `TargetedBehavior` 三处 `ctx.state.get(self._name, "selected_card")` 的迁移点（改为 `view.get`）。新增 `ForceNotOwnedModifier` 零件。**ISSUE-033 追加 / 归属修正（2026-09-22，ISSUE-GATE-dependency-order）**：`Pity` 增加 `reads` 形参归 **S3**（骨架构造形参，默认 `()`，与 `priority` / `pools` 同口径，**不消费任何字段**）；`PityDef.reads` 注入 + `PityEngine.get_reads_for_pool()` 访问器归 **S9**（定义见 §3.10.2）——原稿把两者整体标 S9，与 S3 任务行「`Pity` 增加 `reads` 形参」冲突。**`StateView` 落地时点**：自 **S3** 起在本文件落**薄版**（`get` 直取 `state.data.get(name, {})`，定义见 §3.10.3），S9 才把 `name` 之外的读取切断并接入 Modifier 的 `view` 形参（骨架 §3.1.4 的 `self._view = StateView(state, name)` 因此不是引用未定义符号）。**view 的按零件命名空间分配（§3.10.3 定稿）同在本文件落地（S3 默认 view + 零件 view 框架，S9 收紧）**。**ISSUE-026 追加（S8）**：`compute_scope_mappings`（[pity.py:1040](gacha_simulator/core/pity.py#L1040)）改造为只产出卡集合（`scope_cards` / `featured_cards` 及其反向索引），不再生成槽位名——**改造点在本文件，不在 `core/pool.py`** | <!-- REVIEW-R1-FIX: ISSUE-026 --> <!-- REVIEW-R1-FIX: ISSUE-034 --> <!-- REVIEW-R1-FIX: ISSUE-033 -->
| `core/banner.py` | 修改（**S8 + S9**） | **S8**：删除 `scale_factors` 聚合/还原段（[banner.py:229-246](gacha_simulator/core/banner.py#L229-L246)），概率管道改传卡级分布；`aggregate_probs_by_rarity` 的调用点随之移除。**2026-09-21 审查修正：原写 `service/banner.py` 路径不存在**。**S9（ISSUE-027，2026-09-28 重梳）**：**不新增形参**——`Banner.draw` 本就持有 `state`，通道 A 直接传 `pity_engine.before_draw(..., external=state.external_view())`（[banner.py:195](gacha_simulator/core/banner.py#L195)） | <!-- REVIEW-R1-FIX: ISSUE-027 -->
| `core/pity.py` | **重构**（**S1d** `build_lifecycle` / **S3** 骨架 / **S4-1…S4-5** preset 与 registry / **S6a·S6b** 排序与 priority） | **S3 的目标文件即本行**（统一 Pity 骨架 + `Pity._rebind_state` + `StateView` 薄版）。统一 Pity 骨架 + 10 个类型改造为 registry preset + `_BTYPE_ORDER` 加 `rotating_inverse`（**取值 `3`**，与 `rotating` / `targeted` 同档）+ **`_EVENT_DRIVEN_TYPES` 追加 `rotating_inverse`**（ISSUE-105：只登记排序表而不登记类型集合，会让 `_validate_behaviors` 规则 3 的互斥校验与 `is_active` 早退**双双静默失效**，见 §3.3）+ `_resolve_order` 加 `priority` 排序（G5）。**G16 独立先行（不混入本行重构，§3.8）**：`_should_reset` 加 `never` 分支。**P82 接线独立先行（§1.5 裁决 1）**：`PityEngine` 独立排序视图 + `get_behaviors_for_pool()` 改消费它。**ISSUE-204（强制，2026-09-22 补登记）**：`PityEngine.__init__` 的 `try / except Exception` + `logger.warning` 构造兜底（[pity.py:1164-1172](gacha_simulator/core/pity.py#L1164-L1172)；**ISSUE-GATE-FAIL-2 行号修正（2026-09-22）**：原写 `:1166-1172`，实测 `try:` 起于 `:1164`、`except Exception:` 在 `:1167`、`logger.warning` 在 `:1168-1172`，原范围漏掉 `try:` 与 `create_behavior` 调用行）须**同步改掉**——改为抛 `ConfigError`（preset 构造失败属配置错误，与 `_validate_behaviors` 的校验失败同层），使 `_resolve_order` / `_validate_behaviors` 在**完整**列表上执行。preset 化后该分支风险放大：导入期的 `_validate_registry()` 只校验「`preset` 可调用且返回含 `trackers`/`modifiers`/`lifecycle` 的 dict」、**并不实际调用 preset**（§3.2），故 preset 体内的失败（三个类型集合常量未随叶子层落地致 `NameError`、Modifier 构造签名与 §3.14.2 定稿形态不符致 `TypeError`、缺 `rebind`）在导入期不报错，只在此处被吞成一条日志。若确要保留跳过语义，则须至少补 §六 的「10 个 preset 全部构造成功」断言并把告警升级为加载期可见（写入 `load_warnings`）。**ISSUE-301（强制）**：新增模块级 helper `build_lifecycle(pdef)`（`pdef.depends_on` 非空 → `DependentActive`，否则 `AlwaysActive`，`deactivate_on_early_hit` 一并带入 `LifecycleConfig`），10 个 preset 工厂的返回 dict **一律含 `lifecycle=` 键**；`create_behavior` 在 `preset(pdef)` 之后校验该键存在、缺失抛 `ConfigError`（**旧 `lifecycle_kwargs` 段（:893-900）随之删除**，不得两处并存）。**不做的后果**：全部 `deactivate_on_early_hit` / `depends_on` 配置静默失效且无对照实现可发现（§3.1.3） | <!-- REVIEW-R1-FIX: ISSUE-204 --> <!-- REVIEW-R1-FIX: ISSUE-301 -->
| `core/config_toml.py` | 修改（**G16-1 / S6a / S6c**） | reset 枚举 `never`（G16 独立先行）+ `rotating_inverse` 校验放行（S6a）+ **移除事件驱动型 deactivate_on_early_hit 拒绝分支（H3）**（S6c） |
| `core/config_store.py` | 修改（**S4b**，字段定义） | PityDef 新增 `priority` 字段（G5）。**字段定义与 `config_toml` 解析随 S4b 落地**（2026-09-22 第八轮前移：原归 S6b，但 S4-2 的 `Pity(..., priority=pdef.priority)` 与 S4b 的三处透传都排在 S6b 之前，而实测 `PityDef`（[config_store.py:150-186](gacha_simulator/core/config_store.py#L150-L186)）当前确无该字段，照原序施工即 `AttributeError`，改用 `getattr` 兜底则退化为恒 0 的静默空转）；S6b 只留 `_resolve_order` 排序键与 GUI 控件。新序：**S4-1 → S4b → S4-2** | <!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
| `gui/config_panel.py` | 修改（**G16-1 / S6a / S6b**；**S7a** 验收） | **新建 reset 控件**并加「永不重置」（G16 独立先行，现无该控件）；`_PITY_TYPES` 硬编码列表手工追加 `rotating_inverse`（S6a；type 下拉非 registry 驱动）；priority 编辑控件（S6b）；S7a 做 round-trip 验收 |
| `service/gacha_service.py` | 修改（**S6c** + **S9**） | 定轨识别 `isinstance(bh, TargetedBehavior)` → `getattr(bh, '_btype', '') in ('targeted', 'targeted_soft')`（H1，**S6c**）。 **S9（2026-09-28 重梳）**：**不再是 `ExternalView` 的填充点**——`initial_counts` 提升为 `GachaState` 字段后，视图由 state 自产（`state.external_view()`），服务层的改动只剩「构造 `GachaState` 时把 `_initial_counts` 传进去」（原先它是本函数的局部变量） | <!-- REVIEW-R1-FIX: ISSUE-010 --> <!-- REVIEW-R1-FIX: ISSUE-027 --> <!-- REVIEW-R1-FIX: ISSUE-013 --> <!-- REVIEW-R1-FIX: ISSUE-007 --> <!-- REVIEW-R1-FIX: ISSUE-008 --> <!-- REVIEW-R1-FIX: ISSUE-027 --> <!-- REVIEW-R1-FIX: ISSUE-033 -->
| `service/batch_simulator.py` | 修改 | **ISSUE-007 / ISSUE-008：配置到运行时引擎的桥接，原稿全表零出现**。三处**枚举式透传点**须同步 `priority`（[batch_simulator.py:899-925](gacha_simulator/service/batch_simulator.py#L899-L925) 的 `pentry` **24 键**（实测；原写「26 键」）、:179-205 的 `_PityDef` 重建）与 `reads`、`initial_counts`（:398-408）：任一处漏写，引擎侧读到的恒为默认值，配置层看不出异常。**建议同时改造为「由 dataclass 字段驱动」以免后续再漏** **AUDIT-BREAK-1 追加**：本行是字段往返守卫测试的第一处断言对象（`assert set(pentry) == {f.name for f in dataclasses.fields(PityDef)}`，§六「PityDef 字段枚举透传守卫」条）；改造后 `pentry` 必须由 `dataclasses.fields(PityDef)` 驱动生成，不得继续手写键表 |
| `core/retreat_config.py` | 修改 | **ISSUE-007 / ISSUE-008**：[retreat_config.py:123-142](gacha_simulator/core/retreat_config.py#L123-L142) 按 24 个显式字段浅拷贝 `PityDef`（行号与字段数 2026-09-22 实测修正），同一批透传缺口的第三处，须补 `priority` / `reads` **AUDIT-BREAK-1 追加**：本行是字段往返守卫测试的第三处断言对象（同 `pentry` 口径），浅拷贝须改为 dataclass 字段驱动；漏字段的失败形态是**静默落回默认值**而非报错 |
| `core/strategy.py` | 修改（**S9**） | **ISSUE-013**：`StrategyContext.get_pity_probabilities`（:178）是 `external=None` 的既有查询路径，须由 `StrategyContext` 自行构造并传入 `ExternalView`（它持有 `GachaState`，:100/:113），或在 Modifier 侧以「`external is None` → 恒等」兜底并登记已知差异 **AUDIT-BREAK-9 追加**：本行为 `reads` 的**通道 B**（策略查询通道）宿主：`get_pity_probabilities` 经 `_pity_cache` 绕过 `Banner.draw`，须与通道 A 共用同一 `GachaState` / `_initial_counts` 源；验收见 §六「`reads` 双通道等价」条 |
| `core/worst_impact.py` | 修改（**S8-5**） | **ISSUE-GATE-FAIL-2 补登记（2026-09-22）**：本文件是第二处 `PoolPitySpec` 构造点、S8-5 的目标文件之一（§七 S8-5 已列），但原稿只在 §3.9.3 组件处置表与 §3.9 专项出现，**§四 全表零行**——实施者据此无法判断它是否在改动范围内。改动内容：删除硬编码槽位名（`{'ssr': ('ssr', 'ssr_featured')}` 与 `card_to_slot[cid] = 'ssr_featured'` 等回退分支）、只构造卡集合字段（`scope_cards` / `featured_cards` / `featured_ids` / `ssr_ids`），并复活/替换 `ref_pool = getattr(self, '_ref_pool', None)` 死分支（[worst_impact.py:504](gacha_simulator/core/worst_impact.py#L504)）；卡集合须与池内 reward id 对齐，断言 `set(scope_cards[scope]) ⊆ {r.id for r, _ in pool.rewards}`（§3.9.3 的 ISSUE-006 专项）。**亦为跨进程 pickle 的三条独立入口之一**（[worst_impact.py:136-140](gacha_simulator/core/worst_impact.py#L136-L140)） | <!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-2 -->
| `CLAUDE.md` | 更新（**文档同步，ISSUE-017**） | §二「保底 (core/pity.py)」整节在 P64 后失真（`SoftPityMixin` / `BEHAVIOR_REGISTRY` 的 type→class 映射 / `PityEngine` 签名 / P75 四条纪律 / `create_behavior` 数据流均被改动），扩展指南表「新保底行为」一行同样失真；须同步 | <!-- REVIEW-R1-FIX: ISSUE-017 -->
| `docs/00-meta/模块状态矩阵.md` | 更新（**文档同步，ISSUE-017**） | P64 行摘要仍写「覆盖 G1 幻塔必歪 + G5 priority」，未含 2026-09-21 纳入的 G3 / S9 与 S10/S11/S12，也未含 2026-09-22 的 M1/M2 划分 |
| `config/config.toml` | 更新 | 幻塔 `rotating_inverse` + G16 示例段 |
| `tests/core/test_pity_equivalence.py` | **新增**（**S5a / S5b**） | 等价性对比 harness（固定种子逐场对比概率分布 + `PityState.to_dict()` 快照，S5a）与按家族分批接入的等价性用例：`hard` / soft 族（3）/ rotating 族（3）/ targeted 族（2），每批独立运行、失败可独立归因（S5b）。**2026-09-22 补（ISSUE-GATE-file-list）**：原稿只写 `tests/` 泛行，S5 的用例无处落笔 | <!-- REVIEW-R1-FIX: ISSUE-GATE-file-list -->
| `tests/core/test_pity_invariants.py` | **新增**（**S10-1 / S10-2**） | 组合正确性验收（§3.12）：随机零件组合的生成器与不变式性质断言（归一性 / 非负性 / 因子合法性 / 状态键合法 / 确定性）+ 合法组合判据用例。**2026-09-22 补（ISSUE-GATE-file-list）** | <!-- REVIEW-R1-FIX: ISSUE-GATE-file-list -->
| `tests/core/test_pity_invariant_checker.py` | **新增**（**S11**） | `InvariantChecker` 的**专属**验收测试（§六「S10 / S11（保障层）」段）：**正例** `hard(scope='sr')` 的合法配置（Σ = 1.009）不得报错（归一性按 scope 感知口径）；**负例** 卡概率改负 / Σ 改到 1.2 / 白名单外写 `_active` 时必须抛错，且异常信息含**保底名 + 键 + 期望值 / 实际值**三要素。**原稿 S11 无任何测试文件**，`tests/core/test_pity_invariants.py` 归 S10-1 / S10-2（组合正确性，§3.12），与被测对象不同，两者不得混用 | <!-- REVIEW-R1-FIX: ISSUE-GATE-test-strategy --> |
| `tests/core/test_pity_condition.py` | **新增**（**S12-1**） | Condition 类族的**专属**验收测试（条件求值真值表，S12-1 / S12-2 的验收命令均指向本文件）：`Always` / `Flag` / `Counter` / `FateReady` / `Ratio` / `Owned` / `RandomThreshold` 七个叶子条件 + `And` / `Or` / `Not` 三个组合子。**ISSUE-GATE-FAIL-2 补登记（2026-09-22）**：`core/pity_condition.py` 与 `ConditionalModifier` 是 M1 内 S3 / S4 的直接前置（ISSUE-101），其测试文件与模块同批新增，原稿 §四 无本行 | <!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-2 -->
| `tests/` | 新增/修改 | 等价性测试（旧类 vs 新引擎，全部类型）+ G1/G5/G16 测试 + N1 / M4 / H4 三条强制约束专项断言（S5c）+ 跨进程 pickle round-trip（S7b） **AUDIT-BREAK-7 追加**：S7d（M1）与 S8-7（M2）两块的存量测试改造目标文件清单见 §六「存量测试文件在删除点之前完成改造」条；**AUDIT-BREAK-1 追加**：字段往返守卫测试（`batch_simulator` / `retreat_config` 两处透传）亦落于本目录 |
| `docs/01-活跃/subsystems/保底系统/01-理论.md` | 更新（**文档同步，ISSUE-028**） | 子系统三文件制之一，**已核涉及 P64**：`§2.1 执行顺序` 段（[:64](docs/01-活跃/subsystems/保底系统/01-理论.md#L64)）引用 P64 §1.5 的接线裁决与 §3.1.5.4 的顺序敏感集合。P64 落地后须回写：`_resolve_order` 已接入管道（不再是「算了但没人按顺序用」）、`priority` 语义、卡级管道与乘性因子形式（§3.1.5） | <!-- REVIEW-R1-FIX: ISSUE-028 --> |
| `docs/01-活跃/subsystems/保底系统/02-实施.md` | 更新（**文档同步，ISSUE-028**） | 子系统三文件制之一，**已核涉及 P64**：`§一 代码位置` 的 `pity.py` 行号表（[:17-42](docs/01-活跃/subsystems/保底系统/02-实施.md#L17-L42)，逐行列出 `SoftPityMixin` / 10 个行为类 / `BEHAVIOR_REGISTRY` / `_validate_registry` / `_resolve_order` / `compute_scope_mappings` / `PityEngine`）与 `§2.1`（[:36](docs/01-活跃/subsystems/保底系统/02-实施.md#L36)）。P64 后 10 类退役、`pity.py` 结构重排（新增 `pity_primitives` / `pity_tracker` / `pity_modifier` / `pity_condition` 四模块），该表与相关结论段整体失真，须整体刷新 | <!-- REVIEW-R1-FIX: ISSUE-028 --> |
| `docs/主流抽卡游戏卡池机制配置转换手册.md` | 更新（**文档同步，ISSUE-028 补全路径**） | 原稿只写「手册」未指明路径。内容：G1/G16 登记（G19/G13/G2/G14/G15/G5 已同步，2026-08-24）；G19 处置后的 §15.3/§15.4/§21 与 `targeted` 缺 `selected_card` 的说明（§1.2 顺带发现）也在此文件 | <!-- REVIEW-R1-FIX: ISSUE-028 --> |

<!-- REVIEW-R1-FIX: ISSUE-003 -->
**跨进程 pickle 约束（ISSUE-003，强制，2026-09-22 修复）**

`run_batch_parallel` 用 `MPPool(initializer=_wk_init, initargs=(env, target_specs))` 把**整个 `env` 序列化**给每个 worker（[batch_simulator.py:638-641](gacha_simulator/service/batch_simulator.py#L638-L641)），`env.pity_engine` 随之进子进程；[cli.py:266-267](gacha_simulator/cli.py#L266-L267) 的既有注释亦写明「顺序是硬要求：先设字段、再调 `run_batch_parallel`，彼时 env 已 pickle 给 worker」。P64 把 `PityEngine` 的组成从 10 个 behavior 类换成 `Pity` / `Tracker` / `Modifier` / `Condition` / `Lifecycle` 五族新对象，**全部进入这条 pickle 路径**。

- **约束**：新类的所有成员**必须可 pickle**——禁 lambda / 闭包 / 局部函数 / 不可 pickle 的第三方对象。§3.14 的 Condition 是「代码级 building block（与 P69 复合策略同构）」，而项目内 `ConditionalStrategy` 正是用 lambda 做条件，`ConditionalModifier` 又是自造包装器，故此处**必须显式禁止**而非默认安全。
- **故障形态（为什么必须写死在计划里）**：Windows spawn 下不可 pickle 成员会让每个 worker 的 initializer 直接抛错，而 `run_batch_parallel` 的三次「逐级降并发重试」会把它当资源瓶颈 `logging.warning` 后继续，最终退到**单进程兜底**——表现为**并行度静默归零、耗时暴涨，而不是报错**。
- **波及的三条独立入口**：`batch_simulator.run_batch_parallel`（:638）、[worst_impact.py:136-140](gacha_simulator/core/worst_impact.py#L136-L140)、[retreat_search.py:203-207](gacha_simulator/core/retreat_search.py#L203-L207)。
- **验收**：§六 增设「对 `env`（或 `env.pity_engine`）做 `pickle.dumps` / `loads` round-trip 断言」。

**不受影响**（S1–S5 期间）：PityEngine 调度层接口签名、`_validate_behaviors`（前提见 §3.2）、PityState/DrawInfo/PityContext（**语义与导入路径不变，S1 起改由 `pity_primitives.py` 承载 + `pity.py` re-export**，§3.1.6）、`_redistribute_scope`、GUI 参数控件、P75 `_rebind_state` 纪律（Pity 统一实现后语义不变）。**2026-09-21 审查修正**：`_redistribute_scope` 与 `DrawInfo`/`PityContext` 的槽位字段在 **S8** 中会被替换或删除（见 §3.9.3），此处的「不受影响」仅指 S1–S5

## 五、风险

| 风险 | 缓解 |
|------|------|
| 等价性破坏（重构回归）——preset 与旧类行为偏差 | **等价性测试守门**：固定种子，逐场对比 before_draw 输出概率分布 + after_draw 后状态快照完全一致；覆盖全部 10 个类型（含 counter 驱动）；P56 现有测试天然构成基准 |
| 软保底/硬保底 preset 化风险——`_compute_probabilities` 移植 | 全量 preset 化一次完成；等价性测试覆盖全部组合（含 soft 叠加三态） |
| Modifier 链顺序语义与现有 mixin 嵌套不完全一致 | Modifier 链「顺序应用非短路」契约明确写入设计；等价性测试覆盖 guaranteed / 非 guaranteed / 软保底叠加三态 |
| registry/GUI 兼容——preset 化后参数描述失效 | `params`/`ui_params` 原样保留；GUI 控件零改动，round-trip 验收覆盖 |
| P75 `_rebind_state` 纪律在 Pity 中退化 | Pity 统一实现 Trackers/Modifiers/Lifecycle 的 rebind 委托；独立测试断言跨模拟状态隔离。**ISSUE-029**：委托是**无守卫**调用，故三族（Tracker / Modifier / Lifecycle）的 `rebind` 必须逐个实现，`ConditionalModifier` 必须转发（见 §3.1.1 / §3.9.2 / §3.1.3 / §3.14.2 协议表与 §六 断言）；不实现即每次抽卡入口 `AttributeError` |
| 增量能力（事件驱动 deactivate）误入等价性范围 | 明确标注「旧类无此能力，不在等价性范围」，单独验收用例 |
| G16 与 P64 并行改 `_should_reset` 冲突 | G16 独立先行（单 commit 先落地），P64 重构时 CounterTracker 自然承载，无交叉 |
| CR 随机数消耗不齐（等价性 RNG 分叉） | InterceptModifier 随机数消耗协议（§3.1.2 H4）；等价性测试含 `cr_state_probs` (0,1) 中间值用例 |
| 全量 10 类 preset 化改动面扩大 | 不分阶段（软保底不再分阶段二），一次完成；等价性测试全量守门 |
| **生命周期字段到 Lifecycle 对象的转换点缺失（ISSUE-301）** | preset 工厂返回 dict 不写 `lifecycle=` 键、而旧 `create_behavior` 的 `lifecycle_kwargs` 段（:893-900）又已删除，两端各留一半：**全部 `deactivate_on_early_hit` 与全部 `depends_on` 配置静默失效**（§六 的 N1 例外断言、事件驱动型退役断言双双不可达；`depends_on` 的激活传播与「引用不存在名」的 `ConfigError` 一并消失），且旧类已退役、无对照物可发现。缓解：§3.1.3 定唯一转换点 `build_lifecycle(pdef)` + §3.2 取值来源表与代码块的 `lifecycle=` 键 + `create_behavior` 的 `ConfigError` 防线 + §六 断言 | <!-- REVIEW-R1-FIX: ISSUE-301 -->
| **S8 卡级管道引入的浮点差异与零概率退化** | 浮点差异量级 1e-16，等价性口径已在 §六 放宽为 1e-12 并单独设 S8 验收；零概率退化（因子在 p 支撑上全零）由 §3.1.5.6 约定「返回原分布」处理，与现行早退路径一致 |
| **映射表未写死的实现细节致等价性失败**（计数相位 / CR 随机数短路） | 两条已在 §3.1 列为强制约束（N1 / H4），§六 设对应断言；两者共同点是均不报错、只让结果静默偏移，故必须在 S1/S5 显式实现与断言。did_fire 一项已按 §3.1.1 M4 裁决为统一语义，属行为变更，走独立验收（可先行）；**范围含六类**，其中 counter 驱动 / rotating / targeted 为收严、三个 `_soft` 复合类型为放宽（ISSUE-102，见 §3.1.1 M4 表与 §六 断言） |
| **快照面差异：事件驱动型多一个 `_active: True` 键（GATE-4 定稿取 ①）** | 统一 `_active` 写入使 `rotating` / `targeted` / `rotating_cr` / `rotating_soft` / `rotating_cr_soft` 的命名空间比旧实现多一个 `_active: True` 键，与 §六「快照逐场完全一致」的字面口径冲突。缓解：§3.1.3 已定稿取 ①（统一写入），§六 按 ① 写死断言（备选分支已删），差异登记入 S1 至 S5 的差异归因清单。**不登记即会被等价性测试当成回归反复排查** | <!-- REVIEW-R1-FIX: ISSUE-GATE-risk-mitigation --> |
| **三个 `_soft` 复合类型的 `did_fire` 放宽（ISSUE-102 定稿：不加 hit 门控）** | 该族新 `did_fire` 为「出 scope」，旧经 MRO 为「出 scope ∧ is_featured / 命中定轨」，方向为**放宽**（`depends_on` 依赖方在未命中当轮即被激活），与 rotating / targeted 的**收严**方向相反。缓解：§3.1.1 M4 表六行、§六 断言、§七 S5c 三处已同步；不加 hit 门控（裁定见 §3.1.1）；该差异仅在配 `depends_on` 时可见，按「不在等价性范围内」单独验收 | <!-- REVIEW-R1-FIX: ISSUE-GATE-risk-mitigation --> |
| **`Lifecycle` 的第四组合 `DependentOnceActive` 为新增路径（ISSUE-032 衍生，2026-09-28 语义定稿）** | 把 `depends_on` 与 `max_triggers` 两维正交后，「被激活后又限触发次数」成为一个此前不存在的组合。旧实现里 `deactivate_on_early_hit`（N=1）对所有类型都可用，但「依赖激活 + 计数退役」从未组合过。**语义定稿（2026-09-28 用户裁决）：退役计数自「激活后」起算**——依据是「退役」计量的是「生效期间用了几次」，激活前的抽卡不消耗该保底的额度（未激活时 `is_active` 为假、`before_draw` / `after_draw` 首行早退，本就不参与结算）。残余风险仅是该组合无既有配置用例可比对，缓解：§六 设断言、S1d 单测固化 | <!-- REVIEW-R1-FIX: ISSUE-032 --> |
| **`priority` 字段定义与消费的时序错配（GATE-3(a)）** | `PityDef.priority` 原归 S6b 定义，而 S4-2 的 `Pity(..., priority=pdef.priority)` 与 S4b 的三处透传都排在 S6b 之前；实测 `PityDef`（[config_store.py:150-186](gacha_simulator/core/config_store.py#L150-L186)）当前确无该字段，照原序施工即 `AttributeError`；若改用 `getattr(pdef, 'priority', 0)` 兜底，则退化为恒 0 的**静默空转**（priority 永不生效且无任何报错）。缓解：字段定义 + `config_toml` 解析随 S4b 前移（新序 S4-1 → S4b → S4-2），S6b 只留排序键与 GUI 控件 | <!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order --> |
| **registry `class: None` 之后旧类无入口（GATE-3(c) / GATE-5）** | 等价性装置的「旧」侧与回滚路径各自需要旧类，而 10 个条目的 `class` 一律置 `None` 之后旧类在 registry 上已无入口（实测 `BEHAVIOR_REGISTRY` 当前每条都持有真实类对象）。缓解：harness **直接 import 旧类并以显式实参构造**（不经 registry）；回滚方式改为 **`git revert` 子块 commit**，不依赖 registry 保留旧类。备选 `legacy_class` 过渡字段已否决（§3.2） | <!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order --> |
| **S8 / S9 子项无预算与目标文件（GATE-1）** | M2 的 10 个子项原稿只有任务描述，无预算、无目标文件、无验收命令，且回滚单元写成「S8 + S9 整体」，与 M1 刚确立的「回滚单元 = 任务单元」相反。缓解：第八轮补齐逐子项预算（S8 约 3.1 / S9 约 2.4 人时）、目标文件与「每子项一个 commit」，并加依赖闭包回退规则（GATE-5） | <!-- REVIEW-R1-FIX: ISSUE-GATE-granularity --> |

## 六、验收标准

### 主线（Tracker + Modifier 统一骨架 + G1 + G5）

- [ ] **S1–S5 口径**：全部 10 个类型同配置下，新引擎输出概率分布 + 状态快照与旧类**逐场完全一致**（固定种子，含 hard/soft_step/rotating/rotating_cr/targeted/soft 组合各基准）。此阶段 Modifier 内部沿用槽位法，故要求位级一致
<!-- REVIEW-R1-FIX: ISSUE-023 -->
<!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
- [ ] **view 命名空间分配（ISSUE-GATE-dependency-order）**：三个 `_soft` 类型的 preset 中，soft 族的**软计数落在默认 view（`X` 命名空间）**（对齐旧 mixin 的 `X.counter`），`X_soft` 命名空间只含 `_active`（由命名空间载体 Tracker 的 `namespace=f'{name}_soft'` 与 `Lifecycle.initialize` 的推广作用域写入）；声明了 `namespace` 的零件收到的是 `StateView(state, part.namespace)` 而非默认 view；`_rebind_state` 重建默认 view 时**同批重建各零件命名空间 view**（否则 worker 内连跑 N 场模拟时第 2..N 场的零件 view 指向旧账本，与 ISSUE-004 同一失效模式）
- [ ] **`_soft` 族命名空间保留（ISSUE-023）**：`X_soft` 命名空间及其 `_active` 键在 preset 化后原样存在，`PityState.to_dict()` 的快照字段集合与旧类相同（三个 `_soft` 类型各一条）；若实施选择合并命名空间，则该差异须已登记进下方差异归因清单且 S1–S5 断言已相应放宽
<!-- REVIEW-R1-FIX: ISSUE-202 -->
- [ ] **`_active` 构造期写入（ISSUE-202）**：全部 10 个 preset 构造出的 `Pity`，其 `_lifecycle.initialize(state, name)` 已在构造期被调用——**非 `depends_on` 保底**在构造后 `state.get(name, "_active")` 为 `True`（若为 `False`/缺失，则 `before_draw` / `after_draw` 首行早退、计数型保底全线失效，属阻塞级缺陷）；`DependentActive` 构造期不写、其 `_active` 由引擎激活传播置位。**事件驱动型的差异须登记**：`rotating` / `targeted` / `rotating_cr` / `rotating_cr_soft` / `rotating_soft` 的命名空间在 preset 化后**多一个 `_active: True` 键**（旧类不写），该差异允许存在并须登记为 S1–S5 已知差异，不得当作回归（§3.1.3 已定稿取 ①「统一写入」，备选已否决，**故本断言只有这一版**）<!-- REVIEW-R1-FIX: ISSUE-GATE-risk-mitigation -->
<!-- REVIEW-R1-FIX: ISSUE-301 -->
- [ ] **`deactivate_on_early_hit` / `depends_on` 构造保真（ISSUE-301）**：① 全部 10 个 preset 的返回 dict 含 `lifecycle` 键（缺失时 `create_behavior` 抛 `ConfigError`，不静默回退 `AlwaysActive()`）；② `deactivate_on_early_hit=True` 的配置构造出的 `Pity._lifecycle.deactivate_on_early_hit` 为 `True`，`False`/缺省时为 `False`（不得恒 `False`）；③ `pdef.depends_on` 非空时 `_lifecycle` 为 `DependentActive` 且其 `depends_on` 与该字段相同，为空时 `isinstance(_lifecycle, AlwaysActive)`；④ 两个字段全缺省时与旧 `create_behavior`（不带 `lifecycle` 实参、behavior 落到默认 `LifecycleConfig()`）逐场一致。**本条失败即意味着两类配置静默失效**——N1 例外断言与本表的「参与 `depends_on` 的事件驱动型在激活前不改分布」断言随之不可达，`depends_on` 引用不存在名的 `ConfigError` 也一并消失

<!-- REVIEW-R1-FIX: ISSUE-204 -->
- [ ] **preset 构造不得静默跳过（ISSUE-204）**：全部 10 个 preset 构造成功且 `len(engine.behaviors) == len(pity_defs)`；任一 preset 构造失败**抛 `ConfigError`**（不得只 `logger.warning` 后跳过——跳过会让 `_resolve_order` / `_validate_behaviors` 在**截断后**的列表上执行，同 scope 互斥等校验失去语义，形成「配置里写了保底、运行时该保底不存在且无可见报错」）
- [ ] **S8 口径**：切换为卡级乘性因子后，与 **S5 的产物**逐场对比，概率分布**容差 1e-12 内一致**、状态快照**完全一致**（浮点求和顺序改变导致，量级 1e-16，见 §3.1.5.6）。差异超出容差即为回归
- [ ] **S8 单卡定向**：双 UP 池定轨（`targeted` 锁定其中一张）在必中触发时该卡拿到 100%，不再按基础权重平摊（当前实测为 50/50，见 §3.7）
<!-- REVIEW-R1-FIX: ISSUE-016 -->
<!-- REVIEW-R1-FIX: ISSUE-012 -->
<!-- REVIEW-R1-FIX: ISSUE-006 -->
- [ ] **S8 边界断言（ISSUE-016）**：`scope` 键缺失（无 featured 卡的稀有度、新增标准池）时保底返回恒等而非抛 `KeyError`；`scope_cards` / `featured_cards` 一律经 `.get(scope, ())` 消费
- [ ] **S8 差异归因清单（ISSUE-012 / ISSUE-006）**：S8 与 S5 产物的对比口径为**归一化后分布**；下列两处的差异**允许存在**并须逐一登记，不得当作回归——
  （a）`⟨m,p⟩ ≠ 1` 的配置（`hard` 的 scope 低于最高稀有度）：S5 输出 Σ = 1.009、S8 输出 Σ = 1，管道内可见绝对值改变（抽样分布因 `pool.draw` 的 `_adjusted_total_weight` 隐含归一化可能不变，见 §3.9.5）；
  （b）`worst_impact` 的卡集合对齐改造（§3.9.3 专项）会改变最差影响分析数值
<!-- REVIEW-R1-FIX: AUDIT-BREAK-5 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-6 -->
<!-- REVIEW-R1-FIX: AUDIT-BREAK-8 -->
- [ ] **S8 跨文件同步清单（AUDIT-BREAK-5 / 6 / 8，强制）**：S8 与 S4-3 删除旧符号时，下列**同源改动点必须在同一 commit 内同步**，否则会出现「删了定义、留了引用」的 `ImportError`，或「引用指向已改名函数」的静默错值：
  - **A（删 `aggregate_probs_by_rarity`）**：`core/banner.py`（[`draw` 内局部 import :209](gacha_simulator/core/banner.py#L209)、调用 :227、`scale_factors` 计算 :229-246、槽位取值 :242/:244）、`core/pool.py`（[定义 :244](gacha_simulator/core/pool.py#L244) 与 `infer_rarity_from_spec` :270/:275）、`core/__init__.py`（[:3](gacha_simulator/core/__init__.py#L3) 导出行 + `__all__` 同名项）。验收：`grep -rnE "aggregate_probs_by_rarity|infer_rarity_from_spec" gacha_simulator/ tests/` 零命中
  - **B（`worst_impact` 卡集合对齐）**：`core/worst_impact.py` 第二处 `PoolPitySpec` 构造 :540-548 与硬编码槽位 :512/:515 同步改；**[:504](gacha_simulator/core/worst_impact.py#L504) 的 `_ref_pool` 死分支仍须一并修正**（「死分支可跳过」不成立：S8 后它会随删除面变成半死状态，留下误读）
  - **C（`core/__init__.py` 是双重删除目标）**：S8-4 删 `_redistribute_scope` 导出，S4-3 删 10 个旧行为类与 `SoftPityMixin` 的再导出。验收：`python -c "import gacha_simulator.core as m; assert not [n for n in m.__all__ if not hasattr(m, n)]"` 通过，且 `import gacha_simulator` 无 `ImportError`
<!-- REVIEW-R1-FIX: AUDIT-BREAK-7 -->
- [ ] **存量测试文件在删除点之前完成改造（AUDIT-BREAK-7）**：`S7d`（M1，旧类移除 commit 之前）与 `S8-7`（M2，槽位字段 / `_redistribute_scope` 删除之前）两个时点，`pytest -q --collect-only` 必须**零 `ImportError` / 零 `AttributeError`**。原稿「S4-3 后 pytest 收集期即 `ImportError`」的表述**不成立**（旧行为类在发布前的移除 commit 之前始终可 import），真实断裂点为上述**两处删除 commit**，故按两个时点分别设块。目标文件：`tests/test_pity.py`、`tests/core/test_pity_validate_behaviors.py`、`tests/core/test_pity_rotating.py`、`tests/core/test_pity_integration.py`、`tests/core/test_pity_lifecycle.py`、`tests/core/test_pity_targeted.py`

### S9（状态可见性与 G3）

- [ ] **S9 口径 · reads**：`reads` 声明的保底能读到对应外部状态；未声明时 `ctx.external` 为 `None`；`reads` 写未知状态源在配置加载期抛 `ConfigError`（防拼写致静默失效）
- [ ] **S9 口径 · StateView**：Modifier 读其他保底的键返回 default（架构上关闭，§3.10.3）；`depends_on` 的激活传播不受影响（引擎侧执行，不经过 Modifier）
  <!-- REVIEW-R1-FIX: ISSUE-103 -->
- [ ] **`ctx.state` 通道关闭（ISSUE-103）**：`PityContext.state` 的字段注记为 `PityState`（不是 `StateView`），命名空间隔离全部由 `view` 形参承担；断言 Modifier 实现**不经 `ctx.state` 读状态键**（含自身命名空间），且 `TargetedBehavior` 原有三处 `ctx.state.get(self._name, "selected_card")` 已迁为 `view.get("selected_card")`（`pity.py` 内 `ctx.state` 的读取点归零，`SoftPityMixin` 的 fork 随 mixin 退役消失）
- [ ] **G3 专项（精确建模判据）**：崩坏3 精准补给「50 抽 UP 保护排除已拥有」——① 保底触发时已拥有的 UP 装备不被选中；② **普通抽卡仍能产出已拥有的装备**（这是与 pool 层近似的分界，必须单独断言）；③ 全部 UP 均已拥有时退化为恒等（§3.10.4）
- [ ] **`GachaState.clone()` 保真（S9 附带，独立验收，2026-09-28）**：`initial_counts` 加为字段后，`clone()` 必须逐字段带上它。判据：`s2 = s1.clone()` 后 `s2.initial_counts == s1.initial_counts`（int 值浅比较）。**为什么单列**：`run_simulation` 首行即 `initial_state.clone()`（[gacha_service.py:307](gacha_simulator/service/gacha_service.py#L307)），漏带则每场模拟的 `state.initial_counts` 恒空、`total_holding` 少算初始持有、P63 溢出分档**静默**出错。本项是本次改动**唯一的真实行为风险**，且失败时不报错
<!-- REVIEW-R1-FIX: ISSUE-009 -->
<!-- REVIEW-R1-FIX: ISSUE-013 -->
<!-- REVIEW-R1-FIX: ISSUE-008 -->
- [ ] **G3 补充用例（ISSUE-009）**：配置 `initial_count` 的 UP 装备同样被视为「已拥有」并从 UP 组排除（`owns()` 为 `total_holding` 口径，含初始持有）
- [ ] **`external is None` 兜底（ISSUE-013）**：策略层查询路径（`StrategyContext.get_pity_probabilities` → `PityEngine.get_probabilities`，不传 `external`）对配了 `reads` 的保底**不崩溃**；若该路径不填 `ExternalView`，须**登记为已知差异**（查询分布与抽卡管道不一致），不得静默留空
- [ ] **`reads` 运行期送达（ISSUE-008）**：`reads` 经 TOML → `ConfigStore` → `pentry` → `_PityDef` → 引擎**全程保真**（配置层校验通过不等于运行期送达；链路见 §四 `service/batch_simulator.py` / `core/retreat_config.py` 两行）
<!-- REVIEW-R1-FIX: ISSUE-033 -->
<!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
- [ ] **`reads` 落点归属（ISSUE-GATE-dependency-order）**：`PityDef.reads` 字段、`config_toml` 解析、`batch_simulator`（`pentry` / `_PityDef`）与 `retreat_config` 三处透传**同在 S9（M2）落地**；S3 的 `Pity(reads=...)` 形参在 S9 之前只接受默认空 tuple（此时无字段可注入），且 S3 不得为此改动 `PityDef`
- [ ] **`reads` 并集来源（ISSUE-033）**：`Pity.reads` 由 `PityDef.reads` 全程抵达；`PityEngine.get_reads_for_pool(pool_key)` 返回该池各保底 `reads` 的**并集**（去重；全池未声明时为 `()`）；`GachaService` 经**该接口**（而非自行遍历保底列表）构造 `ExternalView`，空并集时不构造（`external=None`）
<!-- REVIEW-R1-FIX: AUDIT-BREAK-9 -->
- [ ] **`reads` 双通道等价（AUDIT-BREAK-9，强制）**：`reads` 有两个互不覆盖的送达通道，必须**分别**验收：
  - **通道 A（抽卡管道）**：`GachaService` → [`banner.draw` :467](gacha_simulator/service/gacha_service.py#L467) → `PityEngine.before_draw`（已由 `-k "reads or external"` 用例覆盖）
  - **通道 B（策略查询）**：`StrategyContext.get_pity_probabilities`（[core/strategy.py:161-179](gacha_simulator/core/strategy.py#L161-L179)，经 `_pity_cache`）→ `PityEngine.get_probabilities`，**完全绕过 `Banner.draw`**；真实消费方为 [pity_reserve.py:52](gacha_simulator/strategies/builtin/pity_reserve.py#L52)。断言：配 `reads` 的池经通道 B 取到的分布与**同刻**通道 A 逐元素一致（容差 1e-12）且非退化为恒等；两通道必须共用同一 `GachaState` / `_initial_counts` 源（`ctx` 构造处 [gacha_service.py:412](gacha_simulator/service/gacha_service.py#L412)），采样时刻与 scope 口径不得各自为政。验收命令：`pytest -q tests/core/test_pity_integration.py -k "reads and strategy"`
- [ ] `cr_state_probs` 含 (0,1) 中间值的用例等价性通过（随机数消耗对齐，H4）
- [ ] **计数相位（N1）**：`hard(threshold=90)` 首次 100% 出现在第 90 抽；`soft` 的 boost 起始抽数与旧实现相同
- [ ] **did_fire 统一语义（M4）**：**六类**的 `did_fire` 均等价于「本次抽卡是否让本保底回到初始状态」，与各自 `after_draw` 的重置分支严格同条件；rotating/targeted 新补的 scope 门控属增量能力，按「不在等价性范围内」单独验收
  <!-- REVIEW-R1-FIX: ISSUE-102 -->
- [ ] **三个 `_soft` 复合类型的 M4 差异登记（ISSUE-102）**：`rotating_soft` / `rotating_cr_soft` / `targeted_soft` 的新 `did_fire` 为**「出 scope」**（该族 CounterTracker 为「触发稀有度重置抽数 counter」，hit/miss 两分支都 ResetCounter），旧经 MRO 为「出 scope ∧ is_featured / 命中定轨」——方向为**放宽**，与 §3.1.1 M4 表六行一致。断言：配 `depends_on` 时依赖方在「出 scope 但未命中」当轮即被激活；仅在配了 `depends_on` 时可见，按「不在等价性范围内」单独验收并写入差异归因清单。（§3.1.1 的 ISSUE-102 已裁定**不加 hit 门控**，**故本断言只有「出 scope」这一版**，备选分支已删除）<!-- REVIEW-R1-FIX: ISSUE-GATE-risk-mitigation -->
- [ ] **N1 例外**：`deactivate_on_early_hit=True` 且命中时，`commit` 跳过 counter 重置，状态快照与 `get_counter()` 与旧实现一致
- [ ] **Lifecycle 增量能力单独验收**：配 `depends_on` 的事件驱动型在激活前不改分布、不更新状态（旧实现为惰性，属行为变更，不在等价性范围内）
<!-- REVIEW-R1-FIX: ISSUE-032 -->
- [ ] **`OnceActive` / `DependentOnceActive` 配置接线（ISSUE-032，2026-09-27 裁决由「只验类」改为含配置；2026-09-28 两维正交修正）**：① `PityDef(max_triggers=2)` 经 `build_lifecycle` 产出 `OnceActive(cfg, max_triggers=2)`；② `PityDef(depends_on='a', max_triggers=2)` 产出 `DependentOnceActive(cfg, max_triggers=2)`（**两维都生效，非覆盖**）；③ TOML round-trip 保留 `max_triggers`；④ GUI 编辑 → 保存 → 重载一致；⑤ 触发 N 次后 `is_active` 为假且退役动作不改变 `commit` 语义；⑥ `DependentOnceActive` 的退役计数**自激活后起算**（未激活期间不计数）；⑦ `max_triggers = -1` 抛 `ConfigError`
- [ ] **CR 随机数短路（H4）**：`cr_base_rate == 0` 与 `cr_state_probs` 含 0 的用例中，随机数消费次数与旧实现逐位相同
- [ ] `rotating_inverse` preset 正确：出 UP → 下一次 SSR 必非 UP；出非 UP → 恢复基础比例（G1）
  <!-- REVIEW-R1-FIX: ISSUE-105 -->
- [ ] **`rotating_inverse` 的类型注册（ISSUE-105）**：① `_BTYPE_ORDER['rotating_inverse'] == 3`，接线后与同 scope 的 `rotating` 同档（先后按排序键第三位 name 决定）；② `_EVENT_DRIVEN_TYPES` 含 `rotating_inverse`，故 `is_event_driven` 为真、`_validate_behaviors` 规则 3 生效——同 scope 配置 `rotating` + `rotating_inverse` 抛 `ConfigError`（**不得静默通过**）；③ 配 `depends_on` 时 `is_active` 早退对 `rotating_inverse` 生效（§3.1.3）
- [ ] PityEngine 调度层**既有调用形式**不变（`before_draw`/`after_draw`/`get_probabilities` 的既有实参不变；**S9 新增可选参数 `external`**，见 §3.10.2）；`_validate_behaviors` 逻辑不变
- [ ] **接线（§1.5 裁决 1）**：概率管道顺序由 `_resolve_order` 排序键决定而非 TOML 书写顺序；独立排序视图方案下 `draw_pity_names` 输出串保持不变；固定种子基线对照完成，差异逐一归因到「含 `rotating_cr`」或「`target_featured=True` 的 soft 与 hard 共存」两类
- [ ] G5 priority：PityDef `priority` 字段生效，显式 priority 覆盖 type 顺序；priority 全 0 时排序结果与接线后默认序一致（当前 hard 已在 targeted 前，绝区零默认顺序已满足）
<!-- REVIEW-R1-FIX: ISSUE-007 -->
- [ ] **priority 透传保真（ISSUE-007）**：`priority` 经 `config_toml._build_pity()`（:663）→ `store.pity.pities` → `batch_simulator.from_config_store`（:899-925 的 `pentry`）→ `_build_pity_engine_from_gui`（:179-205 的 `_PityDef`）→ `create_behavior` **全程保真**；链上任一环节为**枚举式显式列举**，漏写即静默落回默认 0（同一缺口见 [retreat_config.py:123-142](gacha_simulator/core/retreat_config.py#L123-L142)）
<!-- REVIEW-R1-FIX: AUDIT-BREAK-1 -->
- [ ] **PityDef 字段枚举透传守卫（AUDIT-BREAK-1，强制）**：三处透传点均为**枚举式显式列举**（`pentry` 字典 [batch_simulator.py:899-925](gacha_simulator/service/batch_simulator.py#L899-L925)、`_PityDef(...)` 重建 [:179-204](gacha_simulator/service/batch_simulator.py#L179-L204)、[retreat_config.py:123-142](gacha_simulator/core/retreat_config.py#L123-L142)），新增 `PityDef` 字段若漏写即**静默落回默认值**。强制加一条**字段往返守卫测试**：`assert set(pentry) == {f.name for f in dataclasses.fields(PityDef)}`（`_PityDef(...)` 与 `retreat_config` 两处同口径），字段集失配即测试红。该守卫须与 S4b 的「dataclass 驱动的透传重写」**同 commit** 落地
- [ ] Lifecycle 统一：config_toml 拒绝分支已移除，事件驱动型配置 `deactivate_on_early_hit` 后出 UP 即退役
- [ ] GachaService 定轨流程（H1）：targeted preset 化后 `switch_epitomized_target`/`cancel_epitomized_path` 仍正常
<!-- REVIEW-R1-FIX: AUDIT-BREAK-4 -->
- [ ] **非抽卡动作端到端（AUDIT-BREAK-4，强制）**：`service/gacha_service.py` 有四处**同源**改动点（局部 import [:253](gacha_simulator/service/gacha_service.py#L253)、定轨识别 `isinstance` [:275](gacha_simulator/service/gacha_service.py#L275)、`selected_card` 写入 [:292](gacha_simulator/service/gacha_service.py#L292)/[:294](gacha_simulator/service/gacha_service.py#L294)）。漏改任一处**不报错但功能静默失效**（`isinstance` 恒假则 `switch_epitomized_target` / `cancel_epitomized_path` 走空分支、定轨目标永不变更）。断言必须是**端到端行为**而非符号存在性：构造 targeted 池，策略返回 `NonDrawAction(switch_epitomized_target)`，断言 `selected_card` 实际变更且后续分布随之改变；`cancel_epitomized_path` 同理
- [ ] P75 rebind：Pity 统一实现正确，跨模拟状态隔离测试通过
<!-- REVIEW-R1-FIX: ISSUE-004 -->
<!-- REVIEW-R1-FIX: ISSUE-005 -->
<!-- REVIEW-R1-FIX: ISSUE-003 -->
<!-- REVIEW-R1-FIX: ISSUE-029 -->
<!-- REVIEW-R1-FIX: ISSUE-030 -->
- [ ] **三族 rebind 接口存在且包装器转发（ISSUE-029）**：对 `Pity._trackers` / `_modifiers` 与 `_lifecycle` **逐项**断言 `callable(getattr(x, 'rebind', None))`；`ConditionalModifier.rebind` 转发到内层 Modifier（构造一个被包裹的 Modifier，断言其内部 Counter / Flag 被重绑到新 state）。**同一断言扩展到方法名（ISSUE-GATE-dependency-order）**：M1 阶段对 `modifiers` 链上**每个对象**（含包装器）断言 `callable(getattr(x, 'apply', None))` **并实际调用一次**（`x.apply(ctx, view, dist, readonly)` 不抛 `AttributeError`——纯存在性断言在「`ConditionalModifier.apply` 的转发目标无 `apply`」时同样为真、捕获不到该缺口；内层 `apply` 的承载处是 §3.9.2 的 `Modifier` 基类默认实现），S8 后追加断言 `factor` 亦存在——三者是骨架的无守卫调用面，缺一即每个抽卡入口 `AttributeError`。**不得依赖 `hasattr` 守卫**——`Pity._rebind_state` 是无守卫调用，S12 落地后 preset 内的 Modifier 一律被包裹，漏转发即每次抽卡入口 `AttributeError`
- [ ] **preset 工厂消费 `pdef`（ISSUE-030）**：非默认 `threshold` / `scope` / `counter_init` / `guaranteed_init` / `deltas` 配置下，新 preset 与旧类**逐场一致**（每项至少一条用例）；并断言零参形态未被采用（各 `_preset_xxx` 签名含 `pdef` 形参，`create_behavior` 以 `preset(pdef)` 调用）
<!-- REVIEW-R1-FIX: AUDIT-BREAK-2 -->
- [ ] **构造期参数注入只限旧类分支（AUDIT-BREAK-2）**：`create_behavior` 现于 [pity.py:877-880](gacha_simulator/core/pity.py#L877-L880) 向 `params` 注入 `target_featured` / `reset`，再以 `cls(name=..., state=..., scope=..., **params)` 收尾（[:902](gacha_simulator/core/pity.py#L902)）。preset 分支**不得**透传该 `params`（`Pity.__init__` 无这两个形参）。断言：`inspect.signature(Pity.__init__).parameters` **不含** `target_featured` / `reset`，且 preset 分支构造 10 个 preset 全成功（旧类分支仍按原样注入）。⚠ 待人工裁决：备选方案为保留这两个形参并统一注入（见 §3.1.4 AUDIT-BREAK-2 条）
<!-- REVIEW-R1-FIX: AUDIT-BREAK-3 -->
- [ ] **preset 返回 dict 键集与消费端闭合（AUDIT-BREAK-3）**：preset 返回 dict 的键集**恰为** `{trackers, modifiers, lifecycle, flags, counters}` 五键（`create_behavior` 对未知键抛 `ConfigError`，缺 `lifecycle` 抛 `ConfigError`）；`flags` / `counters` 由 `Pity.__init__` 的新形参消费，按**真值写入**规则 `state.set(name, k, v)`（falsy 值跳过，不写状态）。断言：① 某 preset 返回 `flags={'guaranteed': True}` 后，构造完成即 `state.get(name, 'guaranteed') is True`；② 返回六键（多一键）时抛 `ConfigError`。⚠ 待人工裁决：备选方案为去掉这两个键、初值只走状态声明（H2，见 §3.1.4 AUDIT-BREAK-3 条）
- [ ] **rebind 覆盖面含 view（ISSUE-004）**：`Pity._rebind_state` 重建 `self._view`；worker 内同一 engine 连跑 N 场模拟时第 2..N 场读的是当场账本；断言 `StateView` 不缓存命名空间 dict（命名空间后创建时仍能读到）
- [ ] **同 type 两条保底状态互不影响（ISSUE-005）**：同配置下两条同 preset 保底的 Tracker / Flag / Counter **不共享实例**（preset 为工厂函数，不是模块级常量）
- [ ] **跨进程 pickle round-trip（ISSUE-003）**：对 `env`（或 `env.pity_engine`）做 `pickle.dumps` / `loads` 断言通过——覆盖 `Pity` / `Tracker` / `Modifier` / `Condition` / `Lifecycle` 五族对象，禁 lambda / 闭包 / 不可 pickle 成员（否则并行度静默归零，见 §四 专项）
- [ ] 任意 Tracker × 任意 Modifier 组合自由（新 preset 无需新类）
- [ ] `_SOFT_SUFFIX_TYPES` 处理、`SoftPityMixin`、旧 counter 驱动类退役
- [ ] GUI round-trip：preset 参数编辑 → 保存 → 重载一致；新 type 出现在下拉（须手工追加 `_PITY_TYPES` 硬编码列表，非自动）
- [ ] pytest 全量通过
<!-- REVIEW-R1-FIX: ISSUE-017 -->
- [ ] **文档同步（ISSUE-017 / ISSUE-028）**：`CLAUDE.md` §二「保底 (core/pity.py)」章节与扩展指南「新保底行为」一行改写（P64 后原描述失真）；`docs/00-meta/模块状态矩阵.md` 的 P64 行摘要补 G3 / S9 / S10 / S11 / S12 与 M1/M2 划分；**子系统三文件制**的 `docs/01-活跃/subsystems/保底系统/01-理论.md`（`§2.1` 执行顺序 / `priority`）与 `02-实施.md`（`pity.py` 行号表与 10 类清单）同步（ISSUE-028，已核两者均含 P64 相关内容，见 §四）；`docs/主流抽卡游戏卡池机制配置转换手册.md` 按 §四 登记项更新 | <!-- REVIEW-R1-FIX: ISSUE-028 -->

### S10 / S11（保障层）

- [ ] **S10 组合正确性（§3.12）**：随机零件组合下不变式成立，归一性按 **scope 感知**口径（`Σp = 1 + Σp(被 F 豁免的更高稀有度槽位)`，无 F 参与时退化为 `Σp = 1`）/ 非负性 / 因子非负且在支撑上不全零 / 状态键在声明集内 / 同种子确定性；合法组合判据（同键冲突、引用不存在键、`depends_on` 成环）在构造期报出
- [ ] **S11 不变式运行时校验（§3.13；GATE-6 补齐，2026-09-22）**<!-- REVIEW-R1-FIX: ISSUE-GATE-6-test-strategy -->：`InvariantChecker` 可开关、生产关闭，且**对具体输入有确定的期望输出**
  - **正例**：对 `hard(scope='sr')` 的**合法**配置（§3.12.1 实测 `{ssr:0.006, ssr_featured:0.003, sr:1.0, r:0.0}`，Σ = 1.009），`check_after_before_draw` **不得报错**（归一性按 scope 感知口径）
  - **负例**：人为把一个卡概率改为负值、把 Σ 改到 1.2（超出 F 豁免量）、或在白名单以外写 `_active`，则**必须抛错**，且异常信息含**保底名 + 键 + 期望值 / 实际值**三要素
  - 测试文件为 `tests/core/test_pity_invariant_checker.py`（S11 专属；`tests/core/test_pity_invariants.py` 归 S10，两者被测对象不同，不得混用）
  - **原稿缺口**：S11 在 §六 无任何断言行、§七 无验收命令、§四 无专属测试文件行，而 §七 的 M1 完成标志却把它列为交付条件之一；本条与 §四 / §七 三处同步补齐
<!-- REVIEW-R1-FIX: ISSUE-GATE-test-strategy -->


### G16（独立先行）

- [ ] `reset="never"`：hard 保底出金不重置 counter，每 N 抽白送保底金；`reset="featured"`/默认行为不受影响
- [ ] 手册缺口登记同步（**2026-09-18 核实：G13/G2/G14/G15/G19 已同步**）：G16 由「🔵 待 P64」（[手册:2287](docs/主流抽卡游戏卡池机制配置转换手册.md#L2287)、[手册:775](docs/主流抽卡游戏卡池机制配置转换手册.md#L775)）改「✅ 已覆盖」；G1 由「🔴 高优先级 · → 待 P64 状态机引擎」（[手册:2283](docs/主流抽卡游戏卡池机制配置转换手册.md#L2283)）改「🟡 P64 设计中」；G5（[手册:2296](docs/主流抽卡游戏卡池机制配置转换手册.md#L2296)）待 priority 裁决后更新

## 七、GATE 任务分解

> **里程碑划分（2026-09-22，第四轮修订 ISSUE-101）**：主线子块按**验收口径**分为两段。**M1（S1a 至 S7c + S10-1 / S10-2 + S11 + S12）** 证明「重构未退化」并交付带保障的统一架构，口径为「与旧类逐场一致」；**M2（S8 + S9）** 做表达力扩展，口径为「与 M1 产物容差 1e-12 一致」。M1 结束是一个明确的暂停与交付点，故**不拆分为独立计划文件**（避免约 370 行的跨文件搬移与由此产生的长期引用同步成本）。
>
> **S12 自 M2 调入 M1（ISSUE-101，强制）**：`core/pity_condition.py` 与 `ConditionalModifier` 是 S4 的 preset 工厂与 S5 等价性测试的**直接前置**——计划全篇唯一的 preset 代码（§3.2 / §3.3 / §3.14.2）一律写成 `ConditionalModifier(ForceFeaturedModifier(pdef.scope), FlagCondition("guaranteed"))` 形态。S12 留在 M2 会造成：M1 阶段唯一可照抄的 preset 代码引用不存在的模块与类，S4/S5 在 M1 内无法闭合，「M1 独立交付、可暂停」的定位不成立（10 个 preset 全部无法构造，等价性测试无被测对象）。
>
> **M1 内部执行顺序（强制）**：**S1a → S1b-1 → S1b-2 → S1c → S1d → S2a → S2b → S12-1 → S12-2 → S3-1 → S3-2 → S4-1 → S4b → S4-2 → S4-3 → S4-4 → S4-5 → S5a → S5b → S5c → S6a → S6b → S6c → S7a → S7b → S7c → **S7d** → S10-1 → S10-2 → S11**。**S7d（存量保底测试文件改造，AUDIT-BREAK-7）排在 S7c 之后、保障层之前**：它消费 S5 的等价性结论与 S4 的新构造路径，且**必须早于「发布前一次性移除旧类」的 commit**（旧类本体移除后这批模块级 `import` 即 `ImportError`）。即先迁叶子原语（S1a）与 Tracker / Lifecycle（S1b 至 S1d），S2a / S2b 按 §3.1.2 历史形态实现 Modifier（条件写在类内），S12 随即外置（§3.14.2），S3 / S4 消费外置后的形态。**不得把 S12 放在 S4 之后**，否则 S4 的 preset 引用不存在的符号。**S4b（`priority` 字段定义 + 解析 + 三处透传）的位置在 S4-1 与 S4-2 之间**（2026-09-22 第八轮前移，GATE-3(a)）：S4-2 的构造形参 `Pity(..., priority=pdef.priority)` 要读该字段，而实测 `PityDef`（[config_store.py:150-186](gacha_simulator/core/config_store.py#L150-L186)）当前确无该字段，照前移前的原序（S4b 排在 S4-5 之后）施工即 `AttributeError`。**`build_lifecycle(pdef)` 的定义随 S1d 落地（ISSUE-GATE-3-dependency-order，2026-09-22）**：它依赖的 `LifecycleConfig`（S1a）与三个 Lifecycle 类（S1d）此时齐备，而 S4-2 / S4-3 的 preset 工厂返回 dict 已写 `lifecycle=build_lifecycle(pdef)`（§3.2 / §3.3 / §3.14.2），名字在**调用**时解析——若留到 S4-4 才定义，S4-3 的验收（「全部 10 个 preset 构造成功」）即 `NameError`；S4-4 只剩该键的校验防线与旧 `lifecycle_kwargs` 段删除（删除时机见 S4-4 任务项）。
<!-- REVIEW-R1-FIX: ISSUE-GATE-granularity -->
>
> 共 43 子块：G16 独立 2 + P82 接线独立 2 + 主线 29（细分自原 12 步，见下方「粒度裁定」）。**G16 与 P82 接线均独立先行，不占 P64 主线，也不属任何一个里程碑。** 主线 29 子块**逐块独立 commit**，回滚粒度等于任务粒度（GATE-5）。
>
> **执行顺序**：独立先行块 → M1 → M2。

### GATE-1 任务清单（checkbox）

#### 独立先行块（不属里程碑，可先于 M1 完成）

**G16 独立先行（独立 commit，~1 人时——GUI 需新建 reset 控件，非改下拉）**
- [ ] G16-1 `_should_reset` 加 `never` 分支 + PityDef/config_toml reset 枚举 + GUI **新建 reset 控件**（含「永不重置」）
- [ ] G16-2 测试（hard 出金不重置）+ 手册缺口登记同步（G16/G13/G2/G14/G15/G5；G19 已同步）

**P82 接线独立先行（独立 commit，建议排期；见 §1.5 裁决 1）**
- [ ] P82-1 `PityEngine` 独立排序视图（`self._pool_order` 于 behavior 构造后预计算）+ `get_behaviors_for_pool()` 改为消费排序视图，`PoolPitySpec.pity_names` 保持 TOML 顺序不动
- [ ] P82-2 基线固化 + 等价对照：接线前用固定种子跑 `config.toml` 与既有测试配置固化 `CompactResult` 快照，接线后同种子重跑逐字段对比，差异归因到敏感集合；确认 `draw_pity_names` 输出串不变

#### M1：核心重构与保障（S1–S7 + S10 + S11 + S12）

**主线：Tracker + Modifier 统一骨架（30 个子块逐块预算，合计 16.9 人时；每块独立 commit）**
<!-- REVIEW-R1-FIX: ISSUE-GATE-granularity -->

> **粒度裁定（2026-09-22，ISSUE-GATE-granularity）**：原 12 步主线中至少 7 步的实作量明显超过 1 人时（S1 同时新建 Tracker 家族 + Lifecycle 并迁出叶子原语；S4 同时改 registry schema、10 个 preset、deltas 归属与构造兜底；S6 同时做 G1 + G5 + H1 + H3 四件事），按该粒度派工无法保证「每步一轮内可验收」。故按**可独立验收的最小单元**细分，并给每个子块补 **目标文件 + 人时预算 + 验收命令**。原「~10 人时」为按 12 步粗估，未计入 S12 与保障层细目；本表逐块预算汇总后为 **约 16.4 人时**（差异来自细分后每块的构建与验证开销；**2026-09-22 第八轮按细分后的 29 块重新逐块汇总，合计仍为 16.4 人时**，故原「⚠ 待人工裁决」的估算口径争议随之解除）。
>
> **每块独立 commit（强制）**：S1a 至 S11 的每个子块各产出一个 commit（前缀与改动性质一致：`refactor:` / `feat:` / `test:` / `docs:`），使**回滚粒度与任务粒度一致**（GATE-5）。原稿只有 G16 与 P82 标了独立 commit，主线整体一次回滚，导致单块失败只能整体回退。
>
> **第八轮细分定稿（2026-09-22）**：贴住或超过 1 人时上限的子块再细分，细则如下（每块仍各自独立 commit，回滚粒度等于子块粒度）：
>
> | 原块 | 原预算 | 细分后 | 预算 | 细分的理由 |
> |---|---|---|---|---|
> | S1b | ~1.0（贴上限） | S1b-1 CounterTracker / S1b-2 FlagTracker | 0.6 / 0.4 | 双段 N1 相位与翻转语义是两类被测对象，单测红时的归因方向不同 |
> | S3 | ~1.2（超限） | S3-1 统一骨架 + rebind + `_pools` / S3-2 生命周期顺序与视图接线 | 0.7 / 0.5 | 骨架可独立构造并验收（构造期无 `AttributeError`），退役顺序与 `_active` 写入属另一类断言 |
> | S12 | ~1.5（超限） | S12-1 Condition 类族 / S12-2 `ConditionalModifier` + 去内部判断 | 0.6 / 0.7 | 原 S12-3（`InterceptModifier` 保持内部判断）折入 S12-2；原 S12-4 验收成为 S12-2 的验收项 |
> | S11 | ~0.6 | 不细分（预算改 0.8） | 0.8 | 增补专属测试文件与验收命令（GATE-6） |
> | S4b | ~0.3 | 不细分（预算改 0.4） | 0.4 | 增补 `PityDef.priority` 字段定义与 `config_toml` 解析（GATE-3(a) 前移），且位置移到 S4-2 之前 |
> | S6b | ~0.5 | 不细分（预算改 0.4） | 0.4 | 字段定义移出，只留 `_resolve_order` 排序键与 GUI 控件 |
>
> 上述增减相抵，主线合计 **16.4 人时 / 29 块**；**本轮（AUDIT-BREAK 修复）新增 S7d「存量保底测试文件改造」~0.5 人时**（AUDIT-BREAK-7，原计划该批文件无任何子块承接），汇总为 **30 块 / 约 16.9 人时**。
>
> **M2 子块预算（第八轮补，GATE-1；本轮按 AUDIT-BREAK-7 追加 S8-7 后更新）**：**S8 合计约 3.5 人时**（S8-1 0.5 / S8-2 0.4 / S8-3 0.5 / S8-4 0.8 / S8-5 0.6 / S8-6 0.3 / **S8-7 0.4**）；**S9 合计约 2.4 人时**（S9-1 0.5 / S9-2 0.8 / S9-3 0.5 / S9-4 0.6）；**M2 合计约 5.9 人时**。M2 亦**逐子项独立 commit**，回滚粒度为子项（依赖闭包规则见 GATE-5）。<!-- REVIEW-R1-FIX: ISSUE-GATE-1-granularity --><!-- REVIEW-R1-FIX: AUDIT-BREAK-7 -->

- [ ] **S1a 叶子原语层迁出**（~0.3 人时）｜目标文件 `core/pity_primitives.py`（新增）+ `core/pity.py`（re-export）
<!-- REVIEW-R1-FIX: ISSUE-002 -->
<!-- REVIEW-R1-FIX: ISSUE-019 -->
  - 迁出 `Counter` / `Flag` / `PityState` / `DrawInfo` / `PityContext` / `LifecycleConfig`，`pity.py` 保留 re-export（§3.1.6）
  - `_SOFT_TYPES` / `_HARD_TYPES` / `_EVENT_DRIVEN_TYPES` 由 `CounterBasedBehavior` 类属性升为**模块级常量**（ISSUE-024）；`_EVENT_DRIVEN_TYPES` **内容须追加 `rotating_inverse`**（不是原样迁移），`_BTYPE_ORDER['rotating_inverse'] = 3` 同批落地（ISSUE-105，见 §3.3）
  - ~~同批给 `Pity` 补 `_pools`~~ **已移出本步，归 S3-1**（2026-09-22 第八轮，ISSUE-GATE-dependency-order）：`Pity` 类要到 S3 才新建，本步无处可补（ISSUE-019 原文写「S1/S3」，现写死为 S3-1）。本步期间 `_build_activation_graph` 的池交集警告对每条 `depends_on` 恒真触发，属**已知过渡态**、不是回归，S3-1 落地后恢复语义（§3.12.2）
  - 验收命令：`python -c "from gacha_simulator.core.pity import Counter, Flag, PityState, DrawInfo, PityContext, LifecycleConfig"` 全部可用；`pytest -q tests/test_pity.py`
- [ ] **S1b-1 CounterTracker**（~0.6 人时）｜目标文件 `core/pity_tracker.py`（新增）
<!-- REVIEW-R1-FIX: ISSUE-301 -->
  - 实现 §3.1.1 的 **N1 双段接口**：`advance` 仅供 `CounterTracker` 在 `before_draw` 推进
  - `commit` 落重置，且须处理 `deactivate_on_early_hit` 的跳过重置例外（`commit(skip_reset=)`）
  - 实现 counter 家族的 **M4 `did_reset`**（统一为「本次是否回到初始状态」；`featured` 分支保留无 scope 门控的不对称）
  - 验收命令：N1（`hard(threshold=90)` 首次 100% 出现在第 90 抽）+ counter 家族 `did_reset` 语义单测
- [ ] **S1b-2 FlagTracker**（~0.4 人时）｜目标文件 `core/pity_tracker.py`
  - `FlagTracker(judge, hit, miss, flag)` 的 `commit` 落**翻转**（rotating 的二态翻转、targeted 的锁定命中）
  - 实现事件驱动家族的 **M4 `did_reset`**（`guaranteed` 翻转 / `selected_card` 命中两形态）
  - 验收命令：FlagTracker 翻转与 `did_reset` 单测（rotating / targeted 两族各一条）
  - **为何把 S1b 一分为二（GATE-1）**：S1b 原为 ~1.0 人时，贴住 1 人时上限；且 CounterTracker（双段 N1 相位 + `skip_reset` 例外）与 FlagTracker（翻转语义 + 事件驱动 `did_reset`）的被测对象与失败归因方向不同，合为一块时单测红无法定位到哪一族
- [ ] **S1c StreakTracker + FateTracker**（~0.7 人时）｜目标文件 `core/pity_tracker.py`
  - `StreakTracker` 的 `cr_counter` **不适用 `advance`**（§3.1.1 N1 显式例外），独立单测覆盖
  - `FateTracker` 的累积与阈值分支
  - 验收命令：H4 随机数消费次数在短路条件下与旧实现逐位相同
- [ ] **S1d Lifecycle 五方法族 + `build_lifecycle` helper**（~0.8 人时）｜目标文件 `core/pity_tracker.py` + `core/pity.py`
<!-- REVIEW-R1-FIX: ISSUE-301 -->
  - `AlwaysActive` / `OnceActive(cfg, max_triggers=…)` / `DependentActive(cfg)` 以 `LifecycleConfig` 为**构造参数袋**（共用基类持 `self._cfg`）；`deactivate_on_early_hit` 属性由 `cfg` 代理，`depends_on` 由 `DependentActive` 同源读出（§3.1.3）
  - 三族实现**五方法**协议：`initialize` / `is_active` / `should_deactivate` / `deactivate` / `rebind`（§3.1.3）；`depends_on` 引用不存在名须抛 `ConfigError`
  - **新增模块级 helper `build_lifecycle(pdef)`（写 `core/pity.py`，ISSUE-GATE-3-dependency-order，2026-09-22）**：`pdef.depends_on` 非空 → `DependentActive(LifecycleConfig(…))`，否则 `AlwaysActive(LifecycleConfig(…))`，`deactivate_on_early_hit` 一并带入（代码与逐行对照见 §3.1.3 定稿段）。**必须在 S4-2 / S4-3 之前落地**：那两个子块的 preset 工厂返回 dict 写 `lifecycle=build_lifecycle(pdef)`，而它们排在 S4-4 之前，晚定义则 S4-3 的 preset 构造验收即 `NameError`。**全库只能有一处定义**（`core/pity.py` 模块级），S4-4 不重复定义。<!-- REVIEW-R1-FIX: ISSUE-GATE-3-dependency-order -->
  - 验收命令：`OnceActive` 触发 N 次后 `is_active` 为假且退役动作不改 `commit` 语义（ISSUE-032）；`build_lifecycle` 按 §3.1.3 的三行取值表（`depends_on` 空/非空 × `deactivate_on_early_hit` 两值）逐行单测
- [ ] **S2a BoostModifier + ThresholdForceModifier + BaseRatioModifier**（~0.8 人时）｜目标文件 `core/pity_modifier.py`（新增）
  - **本步按 §3.1.2 历史形态实现**（触发条件写在 Modifier 内部），S12 随即外置
  - `ThresholdForceModifier` 的 F 语义按 §3.14.3（不得改为 `factor_redistribute`）
  - 验收命令：三类各自的内部判断分支单测
- [ ] **S2b Force 三兄弟 + InterceptModifier**（~0.8 人时）｜目标文件 `core/pity_modifier.py`
  - `ForceFeaturedModifier` / `ForceNonFeaturedModifier` / `ForceSelectedModifier`
  - `InterceptModifier` 消费随机数（短路条件、索引裁剪、空表分支、链上位置，H4 协议）
  - 验收命令：H4 契约 + 三类强制修饰的分布断言
<!-- REVIEW-R1-FIX: ISSUE-101 -->
<!-- REVIEW-R1-FIX: ISSUE-101 -->
- [ ] **S12-1 Condition 类族**（~0.6 人时）｜目标文件 `core/pity_condition.py`（新增）+ `core/pity_modifier.py`（方案见 **§3.14**）+ `tests/core/test_pity_condition.py`（新增，本条与 S12-2 的验收命令均指向它）。**位置在 M1 内、S2b 之后 S3 之前（ISSUE-101）**：S3 / S4 的 preset 工厂与 S5 的等价性测试一律消费本步产物，放在 S4 之后会让 M1 无法闭合
  - `Always` / `Flag` / `Counter` / `FateReady` / `Ratio` / `Owned` / `RandomThreshold` 七个叶子条件 + `And` / `Or` / `Not` 三个组合条件（`RandomThresholdCondition` 属 G14 专项，验收见 S12-2）
  - 验收命令：`pytest -q tests/core/test_pity_condition.py`（新增单测，覆盖条件求值真值表）
- [ ] **S12-2 `ConditionalModifier` + 各 Modifier 去内部判断**（~0.7 人时）｜目标文件 `core/pity_modifier.py`
  - [ ] 包装器实现 + 把 S2a / S2b 刚按 §3.1.2 形态写下的那批 Modifier 改写为 §3.14.2 形态（效果实现**不动**）
  - [ ] **ISSUE-029 追加**：包装器**必须转发 `rebind(state, name)` 到内层 Modifier**；M1 阶段同时转发 `apply`，S8 后追加转发 `factor`（§3.14.2 已写，§六 有断言）。S12 落地后 preset 内 Modifier 一律被包裹，漏转发即每次抽卡入口 `AttributeError`
  - [ ] **原 S12-3 折入本项**：`InterceptModifier` 保持内部判断（消费随机数，不适用纯读条件），理由写入实现注释
  - [ ] **验收（原 S12-4 成为本项验收项）**：条件不成立时返回 `None`（恒等）与改前的内部判断逐场一致；`ThresholdForceModifier` 的 F 语义保持（不得改为 `factor_redistribute`，依 §3.14.3）；`RandomThresholdCondition`（G14）专项。**ISSUE-101 追加**：本步的「改前」指 **S2a / S2b 写入的内部判断形态**，S12 不改任何因子计算路径（§3.14.3），故该对比在 M1 内即可完成，无需等 S8
  - [ ] 验收命令：`pytest -q tests/core/test_pity_condition.py` + 等价性对照脚本（条件不成立分支逐场一致）
<!-- REVIEW-R1-FIX: ISSUE-001 -->
<!-- REVIEW-R1-FIX: ISSUE-004 -->
<!-- REVIEW-R1-FIX: ISSUE-018 -->
- [ ] **S3-1 统一 Pity 骨架 + rebind 委托 + `_pools`**（~0.7 人时）｜目标文件 `core/pity.py`
<!-- REVIEW-R1-FIX: ISSUE-001 -->
<!-- REVIEW-R1-FIX: ISSUE-004 -->
<!-- REVIEW-R1-FIX: ISSUE-018 -->
  - Tracker + Modifier + Lifecycle **三元组**构造（§3.1.4 骨架）；保留 `is_soft` / `is_hard` / `is_event_driven` 的 btype 推导（不得写死）
  - `_rebind_state` 重建 `self._view` 且 `StateView` 每次现取；Tracker / Modifier / Lifecycle 三族各实现公开 `rebind(state, name)`（`Pity._rebind_state` 无守卫调用，见 §3.1.1 / §3.1.3 / §3.9.2）
  - **`self._pools = pools`（ISSUE-019 自 S1a 移入本步，2026-09-22 第八轮）**：由 `PityDef.pools` 注入（§3.1.4 骨架已含该形参），使 `_build_activation_graph` 的池交集警告恢复语义（§3.12.2）；S1a 至 S2b 期间该警告恒真触发属已知过渡态
  - `Pity` 增加 `reads` 形参（由 `PityDef.reads` 注入，**S9 之前只接受默认空 tuple**，见 §四 `core/pity.py`（S9）行）
  - 验收命令：`pytest -q tests/core/test_pity_lifecycle.py` 的构造与 rebind 部分；`_pools` 注入后同池 `depends_on` 不再触发池交集警告
- [ ] **S3-2 生命周期顺序与视图接线**（~0.5 人时）｜目标文件 `core/pity.py`
<!-- REVIEW-R1-FIX: ISSUE-202 -->
  - `after_draw` 的退役判定**先于** `commit`，`commit` 接受 `skip_reset`
  - **ISSUE-202 追加**：`Pity.__init__` 在创建 `_view` 前调用 `Lifecycle.initialize(state, name)` 写初始 `_active`（非 `depends_on` 保底写 `True`，`DependentActive` 空实现）
  - **StateView 薄版（ISSUE-GATE-dependency-order）**：按 §3.10.3 定稿做**按零件命名空间分配**（默认 view 绑 `self._name`；声明 `namespace` 的零件另建 view）；S9 才切断 `name` 之外的读取
  - 验收命令：P75 跨模拟状态隔离用例（worker 内连跑 N 场）+ 构造期 `_active` 断言（§六 ISSUE-202 条）
<!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
<!-- REVIEW-R1-FIX: ISSUE-015 -->
- [ ] **S4-1 registry schema 改造**（~0.5 人时）｜目标文件 `core/pity.py`
  - `class` 字段一律置 `None`（ISSUE-015）；`_validate_registry()`（:817-834）改校验 preset 可调用且返回含 `trackers`/`modifiers`/`lifecycle` 的 dict；`create_behavior` 的 `cls is None` 分支同步改写
  - `create_behavior` 双路径（preset / 旧类兼容）保留到等价性测试通过为止
  <!-- REVIEW-R1-FIX: AUDIT-BREAK-2 -->
  <!-- REVIEW-R1-FIX: AUDIT-BREAK-3 -->
  - **preset 分支的构造形态（AUDIT-BREAK-2 / AUDIT-BREAK-3，强制）**：preset 分支**按名取 key**（`trackers`/`modifiers`/`lifecycle` 必需，`flags`/`counters` 可选）构造 `Pity(...)`，**禁止 `**preset(pdef)` 直展开**（未知键 → `TypeError` 或死键），**禁止传旧类分支的 `params` dict**（其中 `target_featured` / `reset` 两处注入在骨架无对应形参 → `TypeError: unexpected keyword argument`）。构造代码与两道校验（查漏 `lifecycle`、查多未知键）见 §3.2 AUDIT-BREAK-3 条；接口冲突的完整分析见 §3.1.4 AUDIT-BREAK-2 条
  - 验收命令：`_validate_registry()` 在导入期对 10 条目全部通过；`create_behavior` 缺键抛 `ConfigError`；**追加**：`create_behavior(PityDef(name='x', btype='hard', reset='never'), state)` 返回 `Pity` 且不抛 `TypeError`（AUDIT-BREAK-2）＋ `inspect.signature(Pity.__init__)` 不含 `target_featured` / `reset`（防注入点被接回 preset 分支）
<!-- REVIEW-R1-FIX: ISSUE-007 -->
<!-- REVIEW-R1-FIX: ISSUE-008 -->
<!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
- [ ] **S4b `priority` 字段定义 + 解析 + 三处透传**（~0.4 人时）｜目标文件 `core/config_store.py` + `core/config_toml.py` + `service/batch_simulator.py` + `core/retreat_config.py`。**位置：S4-1 之后、S4-2 之前（2026-09-22 第八轮前移，GATE-3(a)）**<!-- REVIEW-R1-FIX: ISSUE-GATE-3-dependency-order -->
  - `PityDef` 新增 `priority` 字段（默认 0）+ `config_toml` 解析（`core/config_store.py` / `core/config_toml.py`）
  - `PityDef.priority` 在 `service/batch_simulator.py`（[batch_simulator.py:899-925] 的 `pentry`、:179-205 的 `_PityDef`）与 `core/retreat_config.py`（[retreat_config.py:123-142]）三处**枚举式透传点**同步补齐；**AUDIT-BREAK-1 升为强制**：三处一律**改造为 dataclass 字段驱动**（`dataclasses.fields(PityDef)` 逐字段取值/回填），原「建议」表述废止；逐字段枚举与 `pentry` 的 24 键清单**一经改造即删除**（不得与新写法并存）。理由：三处枚举是字段级类型断裂点，`pentry` 实测 24 键、`_PityDef` 实测逐字段重建（`_PityDef` 是 `PityDef` 的别名，[batch_simulator.py:163]），漏写即静默落回默认值且配置层无异常。三处的完整清单与失效面见 §3.6 AUDIT-BREAK-1 条
  - **归属说明**：`PityDef.reads` 的字段定义 + 解析 + 三处透传**整体归 S9（M2）**（ISSUE-008 的本步落点已撤销），且同样走改造后的 dataclass 驱动路径。本步只处理 `priority`，其消费方是紧随其后的 S4-2（构造形参）与 S6b（`_resolve_order` 排序）
  - 验收命令：`PityDef(priority=5)` 经 TOML round-trip 与三处透传后仍为 5（§六 ISSUE-007 条）；**AUDIT-BREAK-1 追加**：字段全量 round-trip 用例——`for f in dataclasses.fields(PityDef)` 用非默认值构造 → TOML round-trip → `ConfigStore` → `pentry` → `_PityDef` 逐字段等值，且断言 `set(pentry) == {f.name for f in dataclasses.fields(PityDef)}`（键集相等，防漏亦防多）。落点 `tests/service/test_batch_simulator.py`
<!-- REVIEW-R1-FIX: ISSUE-005 -->
- [ ] **S4-2 counter 驱动 preset（4 类）**（~0.6 人时）｜目标文件 `core/pity.py`
  - `soft_interval` / `soft_additive` / `soft_step` / `hard` 四类改造为 **preset 工厂函数**（不得模块级常量实例，ISSUE-005）；工厂签名统一 `def _preset_xxx(pdef)`、调用形式 `preset(pdef)`（ISSUE-030），逐条可配字段一律取自 `pdef`（取值来源表见 §3.2）
  - `PityDef.priority` 经**构造形参** `Pity(..., priority=pdef.priority)` 传入（不是构造后设 `_priority` 属性，§3.6 M3；ISSUE-203）。**`PityDef.priority` 的字段定义与解析见上一步 S4b**（2026-09-22 第八轮前移；新序 S4-1 → S4b → S4-2。实测 `PityDef`（[config_store.py:150-186](gacha_simulator/core/config_store.py#L150-L186)）当前无该字段，若先于 S4b 施工即 `AttributeError`）<!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
  - 验收命令：`python -c "from gacha_simulator.core.pity import BEHAVIOR_REGISTRY as R;from gacha_simulator.core.config_store import PityDef;ks=('soft_interval','soft_additive','soft_step','hard');d=[R[t]['preset'](PityDef(name=t,btype=t)) for t in ks];assert all({'trackers','modifiers','lifecycle'}<=set(x)<= {'trackers','modifiers','lifecycle','flags','counters'} for x in d),d"`——四类 preset 均可构造、返回 dict **⊆ 五键全集**且含三必需键，无 `AttributeError` / `NameError`；**非默认** `threshold` / `scope` / `counter_init` / `deltas` 与旧类逐场一致的等价性口径由 S5b 的 counter 驱动批次覆盖（§六 ISSUE-030 条）<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-6-测试策略 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-3 -->（**AUDIT-BREAK-3**：原写 `<=set(x)` 的**子集**判断不拒绝多余键，故「`flags`/`counters` 成了死键」在该命令下不可见；现值域上界为五键全集，**另加**下述消费者断言）
  - **消费者断言（AUDIT-BREAK-3，强制）**：`PityDef(name='h', btype='hard', counter_init=5, guaranteed_init=True)` 经 preset 与 `create_behavior` 构造出的 `Pity`，其 `state.get(name,'counter') == 5` 且（对含 flag 的类型）`state.get(name,'guaranteed') is True`——即 `flags` / `counters` 被 `Pity.__init__` 真正写入 state，而非「声明了没人读」。同时断言 `create_behavior` 对**未声明键**（如人为在 preset 里加一个 `foo`）抛 `ConfigError`
- [ ] **S4-3 事件驱动 preset（6 类）**（~0.8 人时）｜目标文件 `core/pity.py` + `core/__init__.py`
  - `rotating` / `rotating_soft` / `rotating_cr` / `rotating_cr_soft` / `targeted` / `targeted_soft` 六类 preset 化，签名与取值规则同 S4-2
  <!-- REVIEW-R1-FIX: AUDIT-BREAK-8 -->
  - **AUDIT-BREAK-8 追加**：本步同时删除 [core/\_\_init\_\_.py:9-20](gacha_simulator/core/__init__.py#L9-L20) 的 **10 个旧行为类 + `SoftPityMixin`** import 与 `__all__` 对应条目（`_redistribute_scope` 的导出归 S8-4，见 §3.9.3 C 项）。**只删 import 留 `NameError`、只删 `__all__` 留指向已删符号的 re-export**，两者必须同批；删除前须 `grep -rn "from gacha_simulator.core import"` 确认无调用方依赖这些符号（`from gacha_simulator.core.pity import …` 不受影响——旧类本体保留到发布前，GATE-5）
  - 验收命令：全部 10 个 preset 构造成功且 `len(engine.behaviors) == len(pity_defs)`；`python -c "import gacha_simulator.core as c; assert not {'HardPityBehavior','RotatingBehavior','TargetedBehavior','SoftPityMixin'} & set(c.__all__)"`（AUDIT-BREAK-8）；`pytest -q tests/core/test_pity_validate_behaviors.py`
<!-- REVIEW-R1-FIX: ISSUE-301 -->
- [ ] **S4-4 deltas 展开归属 + 旧 `lifecycle_kwargs` 段删除 + `create_behavior` 防线**（~0.3 人时；`build_lifecycle` 的定义移入 S1d，本步预算由 0.4 调为 0.3，主线合计仍 16.4 人时）｜目标文件 `core/pity.py`
  - deltas 展开职责移交（M6）
  - **`create_behavior` 增 `lifecycle` 键防线**：在 `preset(pdef)` 之后校验返回 dict 含该键，缺失即抛 `ConfigError`（不得静默回退骨架默认 `AlwaysActive()`，§3.1.3）。**10 个 preset 工厂的 `lifecycle=build_lifecycle(pdef)` 在 S4-2 / S4-3 写入**（helper 已于 S1d 定义，本步不重复定义、也不「先写 preset 后在 S4-4 补键」）；本步只补校验与清理
  - **删除旧 `create_behavior` 的 `lifecycle_kwargs` 段（:893-900）**：同一转换不得留两处（§3.1.3）。**删除时机不可前移**——S4-2 / S4-3 期间未迁移的类型仍走旧类兼容路径、仍需该段注入 `LifecycleConfig`，提前删除会让这些类型的 `deactivate_on_early_hit` / `depends_on` 静默失效（§3.2 双路径保留到等价性测试通过为止）
  - 验收命令：`create_behavior` 对缺 `lifecycle` 键的 preset 返回 dict 抛 `ConfigError`；10 个 preset 的 `Pity._lifecycle` 类型与 `deactivate_on_early_hit` 值符合 §3.1.3 三行取值表（§六 ISSUE-301 条）
  - **`OnceActive` 配置接线（ISSUE-032，2026-09-27 裁决）**：`PityDef.max_triggers: int = 0` 字段 + `config_toml` 解析与 round-trip（负值抛 `ConfigError`）+ `build_lifecycle` 第三路产出（`depends_on` 空且 `max_triggers > 0` → `OnceActive`）。本步预算 0.3 → 0.7 人时（GUI 控件归 S7a）；验收见 §六 ISSUE-032 条
<!-- REVIEW-R1-FIX: ISSUE-204 -->
- [ ] **S4-5 PityEngine 构造兜底改抛 ConfigError**（~0.2 人时）｜目标文件 `core/pity.py`
  - `PityEngine.__init__` 的 `try / except Exception` 构造兜底改为抛 `ConfigError`（§四 `core/pity.py` 行）；任一 preset 构造失败**不得只 `logger.warning` 后跳过**（跳过会让 `_resolve_order` / `_validate_behaviors` 在截断后的列表上执行，同 scope 互斥校验失去语义）
  - 验收命令：`pytest -q tests/core/test_pity_validate_behaviors.py -k engine_construct`（新增用例 `test_engine_construct_failure_raises_config_error`，落在该文件——构造期校验失败路径的既有归属）：构造一个 preset 体内会抛错的配置，断言 `PityEngine(...)` 抛 `ConfigError`，**不得** `logger.warning` 后跳过；并断言 `_resolve_order` / `_validate_behaviors` 在**未截断**的列表上执行（同 scope 两条互斥保底中任一条构造失败时，异常必须来自构造而非静默通过）<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-6-测试策略 -->
- [ ] **S5a 等价性测试骨架**（~0.8 人时）｜目标文件 `tests/core/test_pity_equivalence.py`（新增）
  - 固定种子逐场对比装置（旧 vs 新，概率分布 + 状态快照）；含 `cr_state_probs` 中间值用例（H4）
  - 验收命令：`pytest -q tests/core/test_pity_equivalence.py` 先跑通 1 个类型（装置自检）
- [ ] **S5b 全部 10 个类型 preset 化等价性**（~0.8 人时）｜目标文件 `tests/core/test_pity_equivalence.py`
  - 逐类型**批次**推进（counter 驱动 4 类一批 / 事件驱动 6 类一批）；**每批一个 commit**，失败即停在该批（回滚单元）
  - 验收命令：10 类逐场一致（§六 主线口径）
- [ ] **S5c 三条强制约束专项断言**（~0.7 人时）｜目标文件 `tests/core/test_pity_equivalence.py`
  - **N1** 触发抽数 / **M4 did_fire 六类语义**（counter 驱动 ×1 + rotating + targeted + 三个 `_soft` 复合类型，ISSUE-102）/ **H4 短路条件下随机数消费次数**
  - 验收命令：`pytest -q tests/core/test_pity_equivalence.py -k "n1 or m4 or h4"`——**N1**：`hard(threshold=90)` 首次 100% 出现在第 90 抽、soft 的 boost 起始抽数与旧实现相同；**M4**：六类 `did_fire` 语义逐类一条（counter 驱动 ×1 + rotating + targeted + 三个 `_soft` 复合类型，ISSUE-102）；**H4**：`cr_base_rate == 0` 与 `cr_state_probs` 含 0 两条不消耗路径下随机数消费次数与旧实现**逐位相同**，`cr_state_probs` 含 `(0,1)` 中间值的用例一并覆盖<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-6-测试策略 -->
- [ ] **S6a G1 `rotating_inverse` + H3 + GUI 类型列表**（~0.7 人时）｜目标文件 `core/pity.py` + `core/config_toml.py` + `gui/config_panel.py`
  - G1 `rotating_inverse` 注册（依赖 S1a 的 `_BTYPE_ORDER` / `_EVENT_DRIVEN_TYPES`）
  - H3 config_toml 拒绝分支移除；GUI `_PITY_TYPES` 硬编码列表追加新 type
  - 验收命令：§六 `rotating_inverse` 类型注册三条断言
- [ ] **S6b G5 `priority` 排序与 GUI 控件**（~0.4 人时）｜目标文件 `core/pity.py` + `core/config_toml.py`
  - `_resolve_order` 按 priority 排序，显式 priority 覆盖 type 顺序；priority 全 0 时与接线后默认序一致（当前 hard 已在 targeted 前，绝区零默认顺序已满足）。**字段定义与解析不在此步**，已在 S4b 落地（2026-09-22 第八轮前移，GATE-3(a)），本步只消费
  - 验收命令：§六 G5 priority 两条断言（显式覆盖 / 全 0 退化为默认序）
<!-- REVIEW-R1-FIX: ISSUE-GATE-dependency-order -->
- [ ] **S6c GachaService 定轨识别适配（H1）**（~0.4 人时）｜目标文件 `service/gacha_service.py`
  <!-- REVIEW-R1-FIX: AUDIT-BREAK-4 -->
  - **四处同改（AUDIT-BREAK-4 补，原稿只写一处）**：① [:253](gacha_simulator/service/gacha_service.py#L253) 的**函数局部** `from ..core.pity import TargetedBehavior`——**必须删除/改写**，局部 import 只在 `_apply_non_draw` 被调用时执行，故 ruff / H7 与导入期**均不报错**，仅策略返回 `NonDrawAction` 时才抛 `ImportError`；② [:275](gacha_simulator/service/gacha_service.py#L275) `isinstance(bh, TargetedBehavior)` → `getattr(bh, '_btype', '') in ('targeted', 'targeted_soft')`；③④ [:292](gacha_simulator/service/gacha_service.py#L292) / [:294](gacha_simulator/service/gacha_service.py#L294) 写 `selected_card` 依赖 ② 定位出的 `targeted_name`，判定口径**必须与 ② 同源同改**——否则定位到 0 条时抛 `InvalidActionError`、定位错保底时把 `selected_card` 写进错误命名空间（静默语义错误）
  - 验收命令：定轨流程专项用例；**追加端到端用例（AUDIT-BREAK-4）**：策略返回 `switch_epitomized_target` / `cancel_epitomized_path` 两条 `NonDrawAction` 各一条，断言不抛 `ImportError` 且 `pity_state.get(targeted_name,'selected_card')` 被正确写入/清空（只断言 `isinstance` 替换不足以覆盖 :253 —— 该行不被调用即不报错）
- [ ] **S7a GUI round-trip 验收**（~0.4 人时）｜目标文件 `gui/config_panel.py`（验收）
  - **新增「触发次数上限」数值控件（ISSUE-032，2026-09-27 裁决）**：`max_triggers`（0 = 不限），`_apply_pity_edit` 与 load/save 路径同步该键，与既有 pity 编辑区同列。本步预算 0.4 → 0.6 人时
  - preset 参数编辑 → 保存 → 重载一致；新 type 出现在下拉（须手工追加 `_PITY_TYPES` 硬编码列表，非自动）
  - 验收命令：`pytest -q tests/gui/test_config_panel_pity.py`——既有 GUI 端到端集成用例（链路 = 加载 TOML → `_refresh_from_store_impl` → `_on_pity_selected` → `_apply_pity_edit` → `apply_to_store` → `get_config`）；**新增用例**：编辑 preset 参数（如 `hard` 的 `threshold`）→ 保存 → 重载后控件值一致，且新 type `rotating_inverse` 出现在保底 type 下拉（`_PITY_TYPES` 为硬编码列表，须手工追加，非自动）<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-6-测试策略 -->
- [ ] **S7b 跨进程 pickle round-trip**（~0.3 人时）｜目标文件 `tests/service/test_batch_simulator.py`（既有文件，pickle 用例已在该文件内，且 `run_batch_parallel` 的 `MPPool` 入口即在此模块；ISSUE-003）
  - 对 `env`（或 `env.pity_engine`）做 `pickle.dumps` / `loads` 断言，覆盖 `Pity` / `Tracker` / `Modifier` / `Condition` / `Lifecycle` 五族对象，禁 lambda / 闭包 / 不可 pickle 成员（否则并行度静默归零，见 §四 专项）
  - 验收命令：`pytest -q tests/service/test_batch_simulator.py -k pickle`——新增用例覆盖五族对象各一条 round-trip（`dumps` → `loads` → 逐字段相等），并补一条「worker initializer 实际收到可用的 `env`」冒烟断言（现有 `run_batch_parallel` 的降并发重试会把不可 pickle 静默吞成单进程兜底，故必须显式断言并行度未退化）<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-6-测试策略 -->
<!-- REVIEW-R1-FIX: ISSUE-017 -->
- [ ] **S7c 手册示例 + 文档同步 + pytest 全量**（~0.5 人时）｜目标文件 `CLAUDE.md` + `docs/00-meta/模块状态矩阵.md` + 手册（ISSUE-017）
  - `CLAUDE.md` 保底章节与「新保底行为」一行改写；模块状态矩阵 P64 行摘要补 G3 / S9 / S10 / S11 / S12 与 M1/M2 划分；子系统三文件的 `01-理论.md` / `02-实施.md` 同步（ISSUE-028）
  - 验收命令：`pytest -q` 全量通过
<!-- REVIEW-R1-FIX: AUDIT-BREAK-7 -->
- [ ] **S7d 存量保底测试文件改造（旧类直构 → 新架构）**（~0.5 人时）｜目标文件 `tests/test_pity.py` + `tests/core/test_pity_validate_behaviors.py` + `tests/core/test_pity_rotating.py` + `tests/core/test_pity_integration.py` + `tests/core/test_pity_lifecycle.py` + `tests/core/test_pity_targeted.py`（**6 个存量文件**，另 `tests/core/test_pity_rebind.py` / `test_p60_pity_state.py` 若引用被改符号同批处理）
  **AUDIT-BREAK-7：本批文件在原计划里只出现在 §四 的泛写「tests/ 新增/修改」行与 §3.9.3 的槽位消费统计里，§七 **无任何子块**承接——而它们是**模块级** `from gacha_simulator.core.pity import (...)` 直取旧行为类并**直构**（实测 import 清单：`test_pity.py` 取 `HardPityBehavior` / `SoftStepBehavior` / `create_behavior` / `PoolPitySpec`；`test_pity_validate_behaviors.py:45-140` 直构 `_engine([PityDef(...)])` 并在 :97-99 直调 `create_behavior`；`test_pity_rotating.py` 取 4 个 Rotating 族类 + `_redistribute_scope`；`test_pity_integration.py` 取 3 个旧类 + `compute_scope_mappings`；`test_pity_lifecycle.py` 取 `HardPityBehavior`；`test_pity_targeted.py` 取 targeted 两族类）。**
  - **失败时点须写准（勿按原稿的「S4-3 后即 ImportError」施工）**：旧类**本体**保留到「发布前一次性移除」（GATE-5 末条），故 S4-3 **不**让这批文件崩——真正的崩点是 **①「发布前移除旧类」那个 commit**（`from gacha_simulator.core.pity import HardPityBehavior` 立即 `ImportError`，**pytest 收集期**即失败、H9 直接拦死），以及 **②S8 删槽位字段 / 替换 `_redistribute_scope` 时**（构造带槽位字段的 `PoolPitySpec`、调用已删函数）。故 S7d 与 M2 的 S8-7 是**两个时点、两批文件**，不得合并成一项。
  - 本步（S7d）改造范围：把「直取旧类」改为**经新架构构造**（`create_behavior(PityDef(...), state)` 取 `Pity`），保留全部既有断言语义（N1 / M4 / 生命周期 / 阈值行为）；**例外**：`tests/core/test_pity_equivalence.py` 的 harness 仍可直接 import 旧类（§3.2 GATE-3(c) 定稿，那是等价性装置的「旧」侧，不得改造）
  - 触发条件（强制）：**「发布前一次性移除旧类」的 commit 之前必须已完成 S7d**——否则该 commit 一落地 pytest 全红，回滚粒度被破坏
  - 验收命令：`pytest -q tests/ -k pity` 全绿；`grep -rn "HardPityBehavior\|SoftStepBehavior\|RotatingBehavior\|RotatingCRBehavior\|TargetedBehavior\|SoftPityMixin" tests/` 的命中**只允许**出现在 `tests/core/test_pity_equivalence.py`（等价性装置）
**保障层（与核心同批完成，否则核心缺验收与守门手段；逐子块独立 commit）**
<!-- REVIEW-R1-FIX: ISSUE-GATE-granularity -->
- [ ] S10 **组合正确性验收**（合计 ~0.9 人时，方案见 **§3.12**）：
  - [ ] S10-1 不变式性质测试（~0.5 人时）：随机组合零件，断言归一性 / 非负性 / 因子合法性 / 状态键合法 / 确定性（§3.12.1）｜目标文件 `tests/core/test_pity_invariants.py`（新增）
    - 验收命令：`pytest -q tests/core/test_pity_invariants.py`——五条不变式各一组断言，与 §六「S10 组合正确性」条一一对应；归一性按 **scope 感知**口径（`Σp = 1 + Σp(被 F 豁免的更高稀有度槽位)`，无 F 参与时退化为 `Σp = 1`）<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-6-测试策略 -->
  - [ ] S10-2 合法组合判据 + 构造期检查（~0.4 人时，与 `_validate_behaviors` 同层，§3.12.2）｜目标文件 `core/pity.py`（判据的构造期检查与 `_validate_behaviors`（[pity.py:933-985](gacha_simulator/core/pity.py#L933-L985)）同层，落在此处、不新建模块；`_build_activation_graph`（[pity.py:1205-1229](gacha_simulator/core/pity.py#L1205-L1229)）内补成环检测）+ `tests/core/test_pity_invariants.py`（用例，与 S10-1 同文件、按 `-k` 过滤）<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-2 -->
    - 验收命令：`pytest -q tests/core/test_pity_invariants.py -k "illegal or cycle"`——三类判据各一条**负例**，均须在**构造期**抛 `ConfigError`：① 同一键被两个 Tracker 声明（如两个 `CounterTracker` 都写 `counter`）；② Modifier 引用不存在的状态键；③ `depends_on` 成环（**成环检测为新增能力**——现状 `_build_activation_graph` 只校验指向存在的名字，不做环检测）<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-6-测试策略 -->
- [ ] S11 **不变式运行时校验**（~0.8 人时，方案见 **§3.13**）：可开关的 `InvariantChecker`，覆盖分布 / 状态 / 因子 / 生命周期四层；生产关闭｜目标文件 `core/invariants.py`（新增）+ `tests/core/test_pity_invariant_checker.py`（新增，**专属测试文件**）
  - 验收命令：`pytest -q tests/core/test_pity_invariant_checker.py`。**正例**：`hard(scope='sr')` 的合法配置（Σ = 1.009）不得报错（归一性按 scope 感知口径）；**负例**：人为把卡概率改负 / 把 Σ 改到 1.2 / 在白名单外写 `_active`，必须抛错且异常信息含**保底名 + 键 + 期望值 / 实际值**三要素
  - **原稿缺口（GATE-6）**：S11 在 §六 无任何断言行、§七 无验收命令、§四 无专属测试文件行，而 §七 的 M1 完成标志却把「不变式校验（S11）到位」列为交付条件之一；三处已同步补齐（§六「S10 / S11（保障层）」段、§四 测试文件行）<!-- REVIEW-R1-FIX: ISSUE-GATE-test-strategy -->

> **M1 完成标志**：全部 10 个类型与旧类**逐场一致**（§六 主线口径）；G1 / G5 可用；条件外置（S12）落地且触发行为与 S2 的内部判断形态逐场一致（S12-4）；GUI round-trip 通过；组合验收（S10）与不变式校验（S11）到位。**此时架构已统一且带保障，项目处于可交付状态**；M2 尚未开始不影响可用性。
#### M2：表达力扩展（S8 + S9；依赖 M1 完成）

- [ ] S8 **概率操作路径重构**（合计 ~3.5 人时；方案见 **§3.9**，声明见 §3.1.2 D20，数学形式见 §3.1.5）｜**逐子项独立 commit，回滚单元 = 子项**（GATE-1 / GATE-5）。**跨文件面（7 个源文件 + 1 批测试）**：`core/pity.py` / `core/banner.py` / `core/pool.py` / `core/worst_impact.py` / `service/batch_simulator.py` / `core/__init__.py` + **`tests/`（5 个槽位结构消费文件，见 S8-7）**。**AUDIT-BREAK-5 / 6 / 8**：`core/pool.py`（`aggregate_probs_by_rarity` 定义与内部调用）、`core/__init__.py`（import 块 + `__all__` 双改）、`core/worst_impact.py`（第二处 `PoolPitySpec` 构造点 + 硬编码槽位表）**均为本步目标文件**，逐处清单见 §3.9.3 的「跨文件同步清单」——漏改即 `ImportError`，不得因「主调用点在 banner.py」而只改一处。
  - [ ] S8-1 Modifier 接口改为 `factor(...) -> Optional[因子向量]`，`_apply_factor` 做归一化（~0.5 人时；§3.9.2）｜目标文件 `core/pity_modifier.py`
  - [ ] S8-2 管道改传卡级分布：`banner.py` 删除 `aggregate_probs_by_rarity` 调用与 `scale_factors` 还原段（~0.4 人时；§3.9.1）｜目标文件 `core/banner.py` + `core/pool.py`。<!-- REVIEW-R1-FIX: AUDIT-BREAK-5 -->**三处同步（缺一即 `ImportError`）**：① [banner.py:209](gacha_simulator/core/banner.py#L209) 的**函数局部 import**（只在 `draw()` 被调时执行，导入期与 ruff 都不报错）；② [banner.py:227](gacha_simulator/core/banner.py#L227) 调用 + :229-246 `scale_factors` 段 + :242/:244 slot 推导（`infer_rarity_from_spec` 的槽位反查用途）；③ [pool.py:244](gacha_simulator/core/pool.py#L244) 的函数定义与 :270/:275 内部调用。**:257 的 `after_draw` 调用保留**（与概率管道无关）
  - [ ] S8-3 `_redistribute_scope` 替换为卡级版 `factor_redistribute`，语义切为「保持组内当前比例」（~0.5 人时；§3.9.4）｜目标文件 `core/pity.py`
  - [ ] S8-4 删除槽位字段、改造 `compute_scope_mappings`、删除 `aggregate_probs_by_rarity` 及其导出行（~0.8 人时；§3.9.3）｜目标文件 `core/pity.py` + `core/pool.py` + `core/__init__.py` + `service/batch_simulator.py`（+ `python -c "import gacha_simulator.core"` 冒烟）：`PoolPitySpec` / `DrawInfo` 的 `scope_slots` / `featured_slots` / `card_to_slot` 一并删除；`compute_scope_mappings` 改为只产卡集合；`aggregate_probs_by_rarity` 与其导出同步清理；分布解包口径随卡级管道改写。<!-- REVIEW-R1-FIX: AUDIT-BREAK-8 -->**`core/__init__.py` 是双目标文件**：本步删 [core/\_\_init\_\_.py:3](gacha_simulator/core/__init__.py#L3) 的 `aggregate_probs_by_rarity` import、`_redistribute_scope` 的 import（:20）与两者在 `__all__` 的条目（**import 与 `__all__` 必须同批改**）；10 个旧行为类 + `SoftPityMixin` 的 re-export 归 S4-3（已在其任务项）；`infer_rarity_from_spec` 的去留以 §3.9.3「S8 后唯一消费者」的复核结论为准
  - [ ] S8-5 边界处理与 `worst_impact` 卡集合对齐（~0.6 人时；§3.9.5 / §3.9.6）｜目标文件 `core/pity.py` + `core/worst_impact.py`（<!-- REVIEW-R1-FIX: AUDIT-BREAK-6 -->第二处 `PoolPitySpec` 构造点 [worst_impact.py:540-548](gacha_simulator/core/worst_impact.py#L540-L548) + 硬编码槽位表 :512/:515，须整体重写为卡集合字段构造；该构造位于 `getattr(self,'_ref_pool',None)` **死分支**内，**不得因是死分支而不改**）：`T == 0` / `P == 0` / `P − T == 0` / **scope 键缺失** / **`⟨m,p⟩ ≠ 1`** 五类边界；只读查询口径同 §3.9.6。**ISSUE-006 追加**：`worst_impact` 的卡集合按池对齐（断言 `set(scope_cards[scope]) ⊆ {r.id for r, _ in pool.rewards}`，**ISSUE-201**：`Pool.rewards` 元素是 `(Reward, prob)` 二元组，须按二元组解包，口径同 §3.9.1），并复活/替换 `_ref_pool` 死分支
  - [ ] S8-6 验收：按 §六 的 S8 口径（对 S5 产物容差 1e-12）+ 单卡定向专项（~0.3 人时）｜目标文件 `tests/core/test_pity_equivalence.py`（S5a / S5b 的既有装置，加卡级管道对比组）
    - 验收命令：`pytest -q tests/core/test_pity_equivalence.py -k s8`——① 卡级管道产物与 **S5 产物**的**归一化后分布容差 1e-12**、状态快照完全一致；② 单卡定向：双 UP 池定轨（`targeted` 锁定其中一张）在必中触发时该卡拿到 100%（现状实测 50/50，§3.7）；③ §六 登记的两条**允许差异**（`⟨m,p⟩ ≠ 1` 的 Σ = 1.009 → 1、`worst_impact` 卡集合对齐）须作为已知差异断言、不得当作回归<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-6-测试策略 -->
  <!-- REVIEW-R1-FIX: AUDIT-BREAK-7 -->
  - [ ] S8-7 槽位结构消费的存量测试改造（~0.4 人时；§3.9.3 的 `tests/` 行）｜**与 M1 的 S7d 是两个时点、两批文件**（S7d 处置「直取旧类」的模块级 import，本步处置「槽位字段 / `_redistribute_scope`」的结构性断裂）。目标文件 `tests/core/test_pity_rotating.py`（import 并调用 `_redistribute_scope`）+ `tests/core/test_pity_integration.py` / `tests/test_pity.py` / `tests/core/test_pity_lifecycle.py` / `tests/core/test_pity_targeted.py`（构造带槽位字段的 `PoolPitySpec`，**5 个文件**，2026-09-22 计数修正见 §3.9.3）。改造口径：构造改按卡集合字段；`_redistribute_scope` 的用例改为对 `factor_redistribute` 的因子向量断言（语义差见 §3.9.4 三点差别）
    - 验收命令：`pytest -q tests/core/test_pity_rotating.py tests/core/test_pity_integration.py tests/test_pity.py tests/core/test_pity_lifecycle.py tests/core/test_pity_targeted.py` 全绿；`grep -rn "scope_slots\|featured_slots\|card_to_slot\|_redistribute_scope" tests/` 零命中
  - **S8-4 与 S8-5 必须分立（GATE-1 定稿，强制）**：S8-4 是**结构性删除**（槽位字段 + 工厂函数 + 导出面），失败形态是「某处仍在读 `card_to_slot`」这类 `AttributeError` / 导入失败；S8-5 是**数值边界与卡集合口径**，失败形态是「Σ 偏离 1e-12」这类静默偏移。两类失败的归因方向（谁没删干净 vs 谁算错了）完全相反，合成一块会让失败无法定位；且 S8-4 的删除面本身已横跨 4 个文件，接近单块预算上限。
<!-- REVIEW-R1-FIX: ISSUE-012 -->
<!-- REVIEW-R1-FIX: ISSUE-016 -->
<!-- REVIEW-R1-FIX: ISSUE-006 -->
<!-- REVIEW-R1-FIX: ISSUE-201 -->
- [ ] S9 **状态可见性与 G3 真实建模**（合计 ~2.4 人时；方案见 **§3.10**）｜**逐子项独立 commit，回滚单元 = 子项**（GATE-1 / GATE-5）
  - [ ] S9-1 `StateView` 限定 Modifier 状态视野（关闭跨保底读，~0.5 人时；§3.10.3），**签名沿用 S8-1 定稿的 `factor(ctx, view, dist, readonly)` 形态**（方法名由 `apply` 改为 `factor` 属 S8-1 的接口变更，**本步不改签名**，只收紧 `view` 的可读面）｜目标文件 `core/pity.py`。**ISSUE-103 追加**：`PityContext.state` 的字段注记保持 `PityState`（隔离只由 `view` 承担，§3.10.2）；`TargetedBehavior` 三处 `ctx.state.get(self._name, "selected_card")` 迁为 `view.get("selected_card")`（§3.10.3）
  - [ ] S9-2 `PityDef.reads` + `ExternalView` + 配置层白名单校验（~0.8 人时；§3.10.2）｜目标文件 `core/config_store.py` + `core/config_toml.py` + `service/batch_simulator.py` + `core/retreat_config.py` + `core/pity.py` + **`core/strategy.py`** + **`service/gacha_service.py`**（<!-- REVIEW-R1-FIX: AUDIT-BREAK-9 -->后两者是**通道 B（独立概率查询）与通道 A（抽卡管道）的填充点**，缺任一则 `reads` 只在一半路径生效且验收盲区不可见，逐通道说明见 §3.10.2 的 AUDIT-BREAK-9 条）。**ISSUE-033 追加**：`Pity.reads` 承载 + `PityEngine.get_reads_for_pool(pool_key)` 汇总接口（`GachaService` 与 `StrategyContext` 均**经它取并集**，不自行遍历保底）。<!-- REVIEW-R1-FIX: AUDIT-BREAK-1 -->**三处透传点（`pentry` / `_PityDef` / `retreat_config`）随 `reads` 字段定义同批落地**——S4b 已把三处改造为 dataclass 驱动，故本步只需确认新字段自动随行（§3.6 AUDIT-BREAK-1 条）
  - [ ] S9-3 `ForceNotOwnedModifier` 新零件 + G3 配置示例 + 手册 §7.3 缺口归属更正（~0.5 人时；§3.10.4）｜目标文件 `core/pity_modifier.py` + `config/config.toml` + 手册
<!-- REVIEW-R1-FIX: ISSUE-009 -->
<!-- REVIEW-R1-FIX: ISSUE-013 -->
<!-- REVIEW-R1-FIX: ISSUE-008 -->
  - [ ] S9-4 验收：§六 的 S9 口径三条 + G3 专项三条 + **G3 补充用例（含 `initial_count`）+ `external is None` 兜底 + `reads` 运行期送达**（~0.6 人时；ISSUE-009 / ISSUE-013 / ISSUE-008）。**填充点就地**（2026-09-28 重梳，ISSUE-027）：两条通道各持同一 `GachaState`，各自调 `state.external_view()`（通道 A 在 `Banner.draw`、通道 B 在 `StrategyContext.get_pity_probabilities`）；**不再新增 `Banner.draw` 形参**，`PityEngine` 两个入口加可选参 `external=None`。原「填充点定为 `GachaService`」的前提（`Banner.draw` 拿不到 `_initial_counts`）已随 `initial_counts` 提升为 state 字段而消失。｜目标文件 `tests/core/test_pity_integration.py`（既有文件，已含 `depends_on` 激活传播与 rotating / targeted 同池用例；G3 与 `reads` 用例加在此处）+ `tests/service/test_gacha_service.py`（`ExternalView` 填充点断言）<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-6-测试策略 -->
    - 验收命令：`pytest -q tests/core/test_pity_integration.py -k "g3 or reads or external"`（加 `pytest -q tests/service/test_gacha_service.py -k external` 覆盖填充点）——§六 的 S9 口径三条 + G3 专项三条（保底触发时已拥有的 UP 不被选中 / **普通抽卡仍能产出已拥有的装备** / 全部 UP 已拥有时退化为恒等）+ G3 补充用例（`initial_count` 的 UP 装备同样视为「已拥有」）+ `external is None` 兜底（策略层查询路径不崩溃，或按 §六 登记为已知差异）+ `reads` 运行期送达（TOML → `ConfigStore` → `pentry` → `_PityDef` → 引擎全程保真，`get_reads_for_pool` 返回并集）<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-6-测试策略 -->
    - **AUDIT-BREAK-9 追加（通道 B 独立验收，强制）**：上述用例只覆盖通道 A（`GachaService` → `Banner.draw` → `PityEngine.before_draw`）。**通道 B**（`StrategyContext.get_pity_probabilities` → `PityEngine.get_probabilities` 经 `_pity_cache`，见 `core/strategy.py:161-179`）必须另有独立验收：`pytest -q tests/core/test_pity_integration.py -k "reads and strategy"` —— 断言「配 `reads` 的池，经 `ctx.get_pity_probabilities(key)` 取到的分布，与**同刻** `before_draw` 返回值逐元素一致（容差 1e-12），且非退化为恒等 `expected_probs`」。理由：通道 B 是真实消费方（`strategies/builtin/pity_reserve.py:52` 调 `ctx.get_pity_probabilities(qualified_key)`），且它**绕过 `Banner.draw`**，A 通道全绿不能推出 B 通道正确。目标文件补 `core/strategy.py`（`_pity_cache` 与 `get_probabilities` 调用点）与 `service/gacha_service.py`（`ctx` 构造处 :412，保证两通道共用同一 `GachaState` / `_initial_counts` 源）。<!-- REVIEW-R1-FIX: AUDIT-BREAK-9 -->
- [ ] ~~S12 条件外置~~ **已迁至 M1**（排在 S2 之后、S4 之前，见上；ISSUE-101）。M2 不再包含本项。

> **M2 完成标志**：卡级管道与 **M1 产物**容差 1e-12 一致（§六 S8 口径）；单卡定向与 G3 专项通过（§六 S9 口径）。

### GATE-5 回滚策略

<!-- REVIEW-R1-FIX: ISSUE-GATE-granularity -->
- **回滚单元（2026-09-22 修订，ISSUE-GATE-granularity）**：G16 独立；**主线改为逐子块独立 commit，回滚单元 = 任务单元**（S1a 至 S11 共 **30** 块，见 GATE-1；2026-09-22 第八轮细分后由 26 变为 29，本轮 AUDIT-BREAK-7 新增 S7d 后为 30）。原稿「主线整体一次回滚」已撤销，其后果是单块失败只能整体回退，与 30 块的排期不相容。**回退规则 = 依赖闭包（强制，方向 = 向消费方闭包；ISSUE-GATE-5-rollback 补齐）**：回退某子块时**必须连带回退所有消费其产物的后继子块**——只有**同层兄弟块**之间互不牵连（如 S1b-1 与 S1b-2、S5a 与 S5b、S10-1 与 S10-2）。原稿只写「任一子块验收失败只 revert 该 commit，不牵连已通过的兄弟块」，该表述对**低层块**不成立（M2 段早已写明依赖闭包规则，M1 漏写，本条补齐）：
  - 回退 **S1a**（叶子原语层，含 `_SOFT_TYPES` / `_HARD_TYPES` / `_EVENT_DRIVEN_TYPES` 三个模块级常量；§3.1.4 骨架的 `Pity(PityBehavior)` **不继承** `CounterBasedBehavior`，裸名引用即 `NameError`）→ 连带回退 **S1b 至 S11 全部**；
  - 回退 **S1b / S1c / S1d**（Tracker / Lifecycle 族，含 `build_lifecycle`）→ 连带回退 **S3 至 S7**（凡引用被回退符号者一律连带；S2a / S2b 不引用 Tracker / Lifecycle 者可保留）；
  - 回退 **S12-1 / S12-2**（Condition 类族 / `ConditionalModifier`）→ 连带回退 **S3、S4（含 S4b）、S5、S6、S7**（§3.2 / §3.3 / §3.14.2 的 preset 一律为 `ConditionalModifier` 包裹形态，去掉包装器即全部断裂），S10 / S11 视其是否消费被回退符号而定；
  - 回退 **S3-1 / S3-2**（统一骨架）→ 连带回退 **S4 至 S7**；
  - 回退 **S4-1 / S4b** → 连带回退 **S4-2 至 S6b**（preset 工厂与构造形参消费 registry schema 与 `PityDef.priority`）；
  - 回退 **S4-2 / S4-3** → 连带回退 **S4-4**（其防线与旧段删除以「10 个 preset 已落地」为前提）与 **S5**。
  - 回退 **S7d**（存量保底测试文件改造，AUDIT-BREAK-7）→ **无连带**（只改测试文件，不产出被消费符号）；但**发布前「一次性移除旧类」的 commit 不得早于 S7d 完成**。回退 **S8-7**（槽位消费测试改造）须与 **S8-4** 成对（同一删除面），单回退一方会让测试重新引用已删符号。<!-- REVIEW-R1-FIX: AUDIT-BREAK-7 -->
- **强制（低层块回退 = 该里程碑的部分回退）**：低层块被回退后，**必须重跑受影响块的验收命令**（逐块命令见 GATE-1）并确认全绿，才可继续后续子块；未重跑即恢复施工，等于在未验证的状态上叠加新块。<!-- REVIEW-R1-FIX: ISSUE-GATE-5-rollback -->
- **安全网**：全量 preset 化不分阶段，**旧类保留到等价性测试通过为止**；每个子块的 commit 都是「新增/改写 + 该块验收」的原子对。**「任一块可单独 revert」有范围限定**：只在**同层兄弟块**之间成立，低层块回退会带走其消费方（依赖闭包规则见上）
- **等价性测试失败**：停在**失败的那一批 preset**（S5b 按 counter 驱动 / 事件驱动分批，每批一个 commit），保留失败 preset 为「未迁移」；**回退方式改为 `git revert` 该批次的 commit**（**不依赖 registry 保留旧类指针**：§3.2 定稿 `class` 一律置 `None` 之后 registry 已无旧类入口，原写「回退 registry 到该 preset 指向旧类」不可执行，见 GATE-3(c)）。旧类本身仍在代码中，直到发布前一次性移除，故「未迁移」的 preset 仍有可用实现；已通过的批次不回退
- **G16**：独立 commit，与 P64 主线完全解耦，可随时 cherry-pick 或 revert
- **里程碑暂停点（2026-09-22 新增）**：**M1 结束是一个明确的暂停/交付点**——此时架构已统一、行为与旧类一致、保障层到位。M2 可随时暂停或延后，不影响 M1 交付物的可用性
- **M2 的回滚单元（2026-09-22 第八轮修订）**<!-- REVIEW-R1-FIX: ISSUE-GATE-5-rollback -->：**逐子项回滚，回滚单元 = 子项**（S8-1 至 S8-7 / S9-1 至 S9-4 各一个 commit，见 GATE-1 的 M2 清单）。**依赖闭包规则（强制）**：S9 依赖 S8，若回退 S8 中任一子项，必须**连带回退其后的 S8 子项与全部 S9 子项**（S8-2 起管道形态逐项叠加，中途回退会留下半卡级 / 半槽位的混态），但 **S8 内部已通过的前序子项不因此回退**。原稿写「S8 + S9 整体」，与 M1 刚确立的「回滚单元 = 任务单元」相反；且 S8 / S9 各含 6 / 4 个子项、原稿无独立 commit，整体回退等于丢掉约 5.5 人时的可保留成果，已撤销。**S12 不在 M2 回滚单元内**（已随 M1 落地，ISSUE-101）；M1 内若回退 S4 / S5 等消费 S12 的子块，`ConditionalModifier` 本身是独立 commit，可单独 revert 而保留其他块；**反向不成立**——回退被消费方（S12-1 / S12-2）须按上方依赖闭包规则连带回退消费方 S3 / S4 / S5 / S6 / S7。<!-- REVIEW-R1-FIX: ISSUE-GATE-5-rollback -->
- **发布前**：主线完成后一次性移除旧保底类（无历史包袱原则，`RELEASED=False`）

---

*设计评审记录：2026-08-23 用户裁决路线 B（代码组合）、soft 纳入、无完全声明式状态机、G16 独立先行。2026-08-23 独立审查 14 项修正（H1-H4/M1-M6/L1-L4）。2026-08-24 设计重建：Tracker+Modifier 双层纯函数架构（用户裁决命名），范围从事件驱动 6 类扩大到全部保底类型统一，G2 归 milestone 层修正。本计划未含 ISSUE 体系——待 plan-review 工作流审查后补充。*

---

## ⚠ 自动化审查阻塞项

- 未解决问题：0 个<!-- REVIEW-R1-FIX: ISSUE-GATE-4-risk-mitigation -->
- **2026-09-22 第十轮（Fixer，问题项 `ISSUE-GATE-FAIL-2` 文件清单 / `ISSUE-GATE-FAIL-6` 测试策略）已处置并落点如下**：
  1. **文件清单（GATE-FAIL-2）**：① **S10-2 补目标文件**（`core/pity.py`——判据的构造期检查与 `_validate_behaviors` 同层；用例落 `tests/core/test_pity_invariants.py`），补齐「每步均标目标文件」的唯一例外；② **§四 补两行缺失文件**——`core/worst_impact.py`（S8-5 的第二处 `PoolPitySpec` 构造点，原稿只在 §3.9.3 与 §3.9 专项出现、§四 全表零行）与 `tests/core/test_pity_condition.py`（S12-1 的专属测试文件，其验收命令早已指向它而 §四 无行）；③ **行号事实修正**——`PityEngine.__init__` 构造兜底由 `[pity.py:1166-1172]` 改为 `[pity.py:1164-1172]`（实测 `try:` 在 `:1164`、`except Exception:` 在 `:1167`、`logger.warning` 在 `:1168-1172`，原范围漏掉 `try:` 与 `create_behavior` 调用行）。
  2. **测试策略（GATE-FAIL-6）**：**7 个缺验收命令的子块全部补齐**——S4-2（`python -c` 构造冒烟：四类 preset 可构造且返回 dict 三键齐全）、S4-5（用例落 `tests/core/test_pity_validate_behaviors.py`）、S5c（`-k "n1 or m4 or h4"`）、S7a（`tests/gui/test_config_panel_pity.py` + 手工确认新 type 入下拉）、S7b（目标文件由泛写 `tests/` 具体化为 `tests/service/test_batch_simulator.py`，命令 `-k pickle`）、S10-1 / S10-2（`tests/core/test_pity_invariants.py`，后者按 `-k "illegal or cycle"` 过滤）。顺带给 M2 的两个**验收子项** S8-6 / S9-4 补目标文件与验收命令（原稿只有验收内容描述）。修复后 **M1 的 29 个子块逐块具备「目标文件 + 人时预算 + 验收命令」**，与 §七 的粒度裁定自述一致。
  3. **未改动的边界（说明而非缺口）**：M2 的 S8-1 至 S8-5 / S9-1 至 S9-3 是**实施单元**，其验收由同族的 S8-6 / S9-4 统一承载（§七 已如此编排），故不逐项再加「验收命令」行；`ISSUE-GATE-FAIL-2` 描述中「另发现两处清单缺口」即上条第 ② 项的两行，现已闭环。<!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-2 --><!-- REVIEW-R1-FIX: ISSUE-GATE-FAIL-6-测试策略 -->
- **2026-09-22 第十一轮（Fixer，代码审计 9 项 `AUDIT-BREAK-1` 至 `AUDIT-BREAK-9`）已处置并落点如下**：
  1. **AUDIT-BREAK-1（字段枚举透传）**：三处透传点（`pentry` :899-925 / `_PityDef(...)` :179-204 / `retreat_config.py:123-142`）升级为**强制同 commit 同步 + S4b 必做 dataclass 驱动重写 + 字段往返守卫测试**（`assert set(pentry) == {f.name for f in dataclasses.fields(PityDef)}`）。落点：§3.6 / §六 / §四 三行
  2. **AUDIT-BREAK-2（构造期参数注入）**：`create_behavior` 对 `params` 的 `target_featured` / `reset` 注入**限定在旧类分支**，preset 分支不透传 `params`；验收改用 `inspect.signature(Pity.__init__)`。落点：§3.1.4 / §六。⚠ 待人工裁决（备选：保留两个形参统一注入）
  3. **AUDIT-BREAK-3（preset dict 键集）**：按键集**恰为五键** `{trackers, modifiers, lifecycle, flags, counters}` 定稿，新增 `flags` / `counters` 两个消费端形参（真值写入）。落点：§3.1.4 / §3.2 / §六。⚠ 待人工裁决（备选：去掉两键、初值只走状态声明 H2）
  4. **AUDIT-BREAK-4（`gacha_service.py` 四处同源改动）**：断言由「符号存在」改为**端到端非抽卡动作**用例（`switch_epitomized_target` 后 `selected_card` 实际变更）。落点：§3.6 H1 / §六
  5. **AUDIT-BREAK-5 / 6 / 8（S8 跨文件同步面）**：新增「跨文件同步清单」A/B/C 三段行级表（`banner.py` / `pool.py` / `core/__init__.py` / `worst_impact.py`），含 `grep` 零命中与 `__all__` 自洽两道验收命令。落点：§3.9.3 / §六
  6. **AUDIT-BREAK-7（存量测试文件）**：原稿「S4-3 后收集期即 `ImportError`」经核实**不成立**（旧类在移除 commit 前始终可 import），改按真实断裂点设两块：**S7d**（M1，旧类移除前）与 **S8-7**（M2，槽位字段 / `_redistribute_scope` 删除前）。落点：§七 S7d / S8-7 / §六 / §四
  7. **AUDIT-BREAK-9（`reads` 双通道）**：新增通道 B（`StrategyContext.get_pity_probabilities` 经 `_pity_cache`，绕过 `Banner.draw`）独立验收，含「两通道同刻逐元素一致」断言与命令。落点：§3.10.2 / §七 S9-4 / §六 / §四 `core/strategy.py` 行
  - **预算同步**：M1 由 29 块 / 16.4 人时修正为 **30 块 / 16.9 人时**（新增 S7d 0.5）；M2 的 S8 由 3.1 改为 **3.5 人时**（新增 S8-7 0.4）、M2 合计 5.5 改为 **5.9 人时**。GATE-5 回滚单元同步为 30 块
- 本轮（第八轮，Fixer 定稿）处置的 6 项争议（前六轮对抗循环未收敛项，现已逐条在上文写死，不再留待人工裁决）：

| # | 争议 | 定稿处置 | 落点 |
|---|---|---|---|
| 1 | 快照面取 ①「统一写入」还是 ②「仅计数驱动型写入」 | 取 ①（统一写入），差异登记为 S1 至 S5 的已知差异 | §3.1.3 / §六 / §五 |
| 2 | 三个 `_soft` 复合类型的 `did_reset` 是否加 hit 门控 | 不加门控，按「出 scope」登记为放宽型行为变更 | §3.1.1 / §六 / §五 |
| 3 | 本期是否接线福利保底可配置（`PityDef.max_triggers` + 三处透传） | 不接线，只验类语义；代价登记为风险行 | §3.1.3 / §六 / §五 |
| 4 | `PityDef.priority` 字段定义在 S4b 还是 S6b | 前移至 S4b，并置于 S4-2 之前（新序 S4-1 → S4b → S4-2） | §四 / §七 S4b / §七 S6b |
| 5 | registry `class: None` 之后旧类的构造与回退入口 | harness 直接 import 旧类构造；回滚改 `git revert`；否决 `legacy_class` 过渡字段 | §3.2 / GATE-5 |
| 6 | S11 的 §六 断言 / 验收命令 / 专属测试文件三处缺口 | 三处补齐，预算 0.6 改为 0.8 人时 | §六 / §七 S11 / §四 |

- 详情：[]
- **⚠ 待人工裁决（仅保留 veto 通道，不阻塞施工）**：上表第 1 至 3 项原为计划内的显式「⚠ 待人工裁决」标记，第八轮按「计划自身已标注的推荐项 / 最小改动项」定稿（① 统一写入 = 原标注「推荐」；不加 hit 门控 = 不引入第二套口径；不接线福利保底配置 = 不扩大范围）。若人工否决其中任一项，须**同步回改** §3.1.1 / §3.1.3 的对应段、§六 对应断言与 §五 风险行（三者已按定稿口径写死，无备选分支残留），并重启 §七 S1b-1 / S3 / S12 的相关子块。第 4 至 6 项为事实性缺口（字段不存在 / 符号无入口 / 测试文件缺失），无备选，按定稿执行即可**第十一轮追加两项**：`AUDIT-BREAK-2`（preset 分支是否透传 `params`：定稿「不透传」= 保持骨架签名干净；备选「保留 `target_featured` / `reset` 并统一注入」）与 `AUDIT-BREAK-3`（preset dict 是否保留 `flags` / `counters`：定稿「保留」= 让初值经构造期一次性写入；备选「去掉两键」= 初值只走状态声明 H2）。两项均按**保守方案**（第一项取「不透传」、第二项取「保留」）写入计划，另存 veto 通道，不阻塞施工。
- 原因：原写「6 轮对抗循环未收敛」与本条「未解决问题：0 个」互斥（既已收敛为 0，就不存在未收敛的原因）。第八轮已按上表逐条定稿并登记落点，故原因栏更正为「第八轮已完成全部 6 项争议的定稿与落点登记」。<!-- REVIEW-R1-FIX: ISSUE-GATE-risk-mitigation -->

## 自动化审查记录

<details>
<summary>第 1 次审查（2026-09-22）——P38 工作流自动化</summary>

- 复杂度: complex | 变更性质: breaking
- 阶段 1 影响面: 51 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 44 个

</details>
