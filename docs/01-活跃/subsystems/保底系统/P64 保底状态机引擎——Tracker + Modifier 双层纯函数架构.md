<!-- META: P64 | module:保底系统 | status:designing | last:2026-10-09 | depends:P55,P56 -->

# P64 保底状态机引擎——Tracker + Modifier 双层纯函数架构

> 日期：2026-08-24（2026-09-16 补三条强制约束 + §3.1.5 形式化 + target_featured 反例；**2026-09-18 事实同步**：全量行号刷新至 P81 清理后的代码 + GUI 两处事实修正 + legacy 迁移描述更新；**同日裁决 P82 并入的三项**：接线 / 保留 priority / 顺序两层定性，见 §1.5；**2026-09-21 概率操作乘法化 + 状态可见性裁决**：§3.1.5 重写为乘性因子版 + §3.1.2 D20 分布空间归属 + §3.9 S8 实施方案 + §3.10 状态可见性与 G3 真实建模 + S8/S9 子块；跨保底读状态裁决为不纳入；G15 按「精确建模原则」重估为缺口；**同日增补三项架构改进**：§3.11 表达能力与边界、§3.12 组合正确性验收、§3.13 不变式运行时校验 + S10/S11 子块；**§3.14 条件外置**（条件提为独立对象 + ConditionalModifier 包装器；三方案比较与 R/F 等价性实测）+ S12 子块；**2026-09-22 GATE 加里程碑划分**：M1（S1–S7 + S10 + S11，口径「与旧类逐场一致」）/ M2（S8 + S9 + S12，口径「与 M1 产物容差一致」），M1 结束为暂停与交付点，计划文件不拆分；**同日第四轮（Fixer）**：**S12 由 M2 前移进 M1**（排在 S2 之后、S3/S4 之前，ISSUE-101，里程碑边界与 M2 回滚单元同步调整）、三个 `_soft` 复合类型的 M4 差异登记与方向更正（ISSUE-102）、`PityContext.state` 类型注记与 `ctx.state` 读取纪律（ISSUE-103）、Tracker 契约表签名回写定稿形态（ISSUE-104）、`rotating_inverse` 的类型集合与排序键取值（ISSUE-105）） | 状态：设计中（2026-08-23 初版 → 2026-08-24 双层纯函数重建）；**2026-09-22 审查修复轮**：新增 §3.1.6 模块归属与依赖方向（叶子原语层 `pity_primitives.py`）、骨架补 `is_soft`/`is_hard` 推导与 view 重建与「退役先于 commit」、preset 统一为工厂函数 + registry `class` 置 None、跨进程 pickle 约束、配置透传链（`priority`/`reads`）、`worst_impact` 卡集合对齐、外部状态填充点改 `GachaService` 与 `owns` 含初始持有、归一性断言改 scope 感知、`scope` 键缺失边界、文档同步面（CLAUDE.md / 模块状态矩阵），逐处标记 `ISSUE-xxx`；**同日第二轮**：`§3.14.2` 示例改 `.get(scope, ())`（ISSUE-020/016）、`§3.9.2` 归一化论证前提修正（ISSUE-021）、`factor_redistribute` 签名统一为 4 参（ISSUE-022）、`_soft` 族双命名空间与 S1–S5 快照口径对齐（ISSUE-023）、三类型集合随叶子层升为模块级常量（ISSUE-024）、`core/__init__.py` 10 个旧行为类导出面（ISSUE-025）、`compute_scope_mappings` 的改造归属 `pity.py`（ISSUE-026）、`Banner.draw` 送达路径定稿（ISSUE-027）、子系统 01-理论/02-实施 与手册路径入文档同步面（ISSUE-028）；**同日第三轮（Fixer，2026-09-22）**：`pity_primitives.py` 行补记三个类型集合常量与 `PityContext.external`（ISSUE-024 / ISSUE-034）、Tracker / Modifier / Lifecycle 三族 `rebind` 接口显式定义 + `ConditionalModifier` 转发（ISSUE-029）、preset 工厂签名定稿为 `preset(pdef)` 并补取值来源表（ISSUE-030）、§3.2 / §3.3 正文同步条件外置形态与「组装时的条件」列（ISSUE-031）、`FiniteActive` 声明为「无配置对应物、本期只实现类」（ISSUE-032）、`reads` 并集来源与 `get_reads_for_pool()` 访问器（ISSUE-033）；**同日第五轮（Fixer，2026-09-22）**：Lifecycle 协议补第五个方法 `initialize` 并同步 §3.1.4 骨架 / §四 行 / §3.13 不变式行 / §六 断言（`_active` 的构造期写入自此有归属，ISSUE-202）、§3.6 M3 的 `priority` 透传机制统一为构造形参 `Pity(..., priority=pdef.priority)`（ISSUE-203）、`worst_impact` 卡集合断言改为 `{r.id for r, _ in pool.rewards}`（`Pool.rewards` 元素是 `(Reward, prob)` 二元组，ISSUE-201）、`PityEngine.__init__` 构造期 `except Exception` 静默吞异常的处置定稿为抛 `ConfigError` 并补 §六 断言（ISSUE-204）；**同日第六轮（Fixer，2026-09-22）**：`deactivate_on_early_hit` / `depends_on` 到 Lifecycle 对象的构造来源全链补齐——§3.1.3 新增唯一转换点 `build_lifecycle(pdef)` 与旧路径逐行对照表、§3.2 取值来源表补 `lifecycle=` 行 + registry 校验与 `create_behavior` 的 `ConfigError` 防线 + 四份 preset 代码块补该键、§3.1.6 与 §四 四行登记、§五 风险行、§六 断言、§七 S1/S4 任务项；`LifecycleConfig` 去留定稿为「保留、角色改为 Lifecycle 构造参数袋」（ISSUE-301）；**同日第七轮（Fixer，2026-09-22）三 GATE 问题处置**：① `ISSUE-GATE-granularity` — §七 主线 12 步细分为 26 子块（S1a 至 S1d / S2a 至 S2b / S12 / S3 / S4-1 至 S4-5 / S4b / S5a 至 S5c / S6a 至 S6c / S7a 至 S7c / S10-1 至 S10-2 / S11），逐块补目标文件 + 人时预算 + 验收命令，进度合计由「~10 人时」修正为「约 16.4 人时」，并把「每块独立 commit」写入 GATE-1 与 GATE-5（回滚单元 = 任务单元）；② `ISSUE-GATE-file-list` — 五处行号与计数事实修正（`_EVENT_DRIVEN_TYPES` `:114-115`、`_build_activation_graph` `:1205-1229`、`ctx = PityContext(...)` `:1335`、测试文件 6 改 5、`pentry` 26 键改 24 键）并补齐 S3 / S5 / S10 / S11 四处缺失的目标文件（`core/invariants.py` 独立新模块登记 + 两个新测试文件行）；③ `ISSUE-GATE-dependency-order` — Modifier 方法名定稿为 `apply(ctx, view, dist, readonly)`（`factor` 自 S8 引入，§3.1.4 骨架据此）、`StateView` 由「S9 独占」改为「S3 落薄版 / S9 收紧」、`PityDef.reads` 字段与解析归 S9 而 `Pity.reads` 形参归 S3、`_soft` 族 view 命名空间分配定稿（软计数留 `X`、`X_soft` 只承 `_active`，§3.10.3）；**2026-09-22 第八轮（Fixer 定稿，GATE 五项）**：GATE-1 粒度（S1b / S3 / S12 各细分、M2 补逐子项预算与目标文件、S8-4 与 S8-5 分立）、GATE-3 依赖序（`priority` 字段定义前移至 S4b 且置于 S4-2 之前、`_pools` 由 S1a 改归 S3-1、registry `class` 置 `None` 后旧类改由 harness 直接 import 且回滚改 `git revert`）、GATE-4 风险（快照面取 ①统一写入、ISSUE-102 不加 hit 门控、ISSUE-032 维持只验类不接线，三项均已登记为 §五 风险行）、GATE-5 回滚（主线 29 块逐块回滚、M2 按子项回滚 + 依赖闭包规则）、GATE-6 测试（S11 补专属测试文件、验收命令与 §六 断言），五项定稿的落点见 §七 粒度裁定 / GATE-5 / §六「S10 / S11（保障层）」段 / 文末「自动化审查阻塞项」。**2026-09-22 第九轮（Fixer，GATE-3 / GATE-5 复核）**：① `build_lifecycle(pdef)` 的**定义自 S4-4 移入 S1d**（其依赖 S1a 的 `LifecycleConfig` 与 S1d 的四个 Lifecycle 类此时齐备），S4-4 只留 `lifecycle` 键的 `ConfigError` 防线与旧 `lifecycle_kwargs` 段删除（删除时机须待 10 个 preset 全部落地）——preset 工厂（S4-2 / S4-3）返回 dict 已写 `lifecycle=build_lifecycle(pdef)`，名字在调用时解析，留到 S4-4 才定义则 S4-3 的验收即 `NameError`；② 「`apply()` 保留为默认实现」落成**公共基类 `Modifier`**（§3.9.2 补默认 `apply` = `_apply_factor(dist, self.factor(...) or {})`，§3.2 / §3.14.2 的 Modifier 示例统一改为继承它，§3.14.2 的 `apply` 转发自此有承载处；备选「S8 删除 `apply`」已否决），§六 断言补「**实际调用一次**不抛 `AttributeError`」（纯存在性断言捕获不到该缺口）；③ S9-1 措辞改为「签名沿用 S8-1 定稿的 `factor` 形态」，改名不再记在本步；④ GATE-5 补 **M1 的依赖闭包回退规则**（向消费方闭包，逐块列出连带范围）与「低层块回退 = 部分回退，须重跑受影响验收」强制条。**2026-09-22 第十轮（Fixer，GATE 复核）**：① 文件清单（`ISSUE-GATE-FAIL-2`）——S10-2 补目标文件（唯一未标步）、§四 补 `core/worst_impact.py` 与 `tests/core/test_pity_condition.py` 两行缺失文件、`PityEngine.__init__` 构造兜底的行号由 `:1166-1172` 修正为 `:1164-1172`；② 测试策略（`ISSUE-GATE-FAIL-6`）——S4-2 / S4-5 / S5c / S7a / S7b / S10-1 / S10-2 七块补「验收命令」（S7b 目标文件由泛写 `tests/` 具体化），顺带补 M2 的 S8-6 / S9-4 两个验收子项，M1 的 29 子块自此**逐块**具备「目标文件 + 人时预算 + 验收命令」（落点见文末「自动化审查阻塞项」）。**2026-09-22 第十一轮（Fixer，代码审计 9 项 AUDIT-BREAK-1 至 AUDIT-BREAK-9）**：字段枚举透传升级为「同 commit 同步 + dataclass 驱动 + 字段往返守卫测试」（三处透传点行级表，AUDIT-BREAK-1）；`create_behavior` 的 `target_featured` / `reset` 注入限定旧类分支（AUDIT-BREAK-2）；preset 返回 dict 按键集恰五键定稿并新增 `flags` / `counters` 消费端（AUDIT-BREAK-3）；`gacha_service.py` 四处同源改动改为端到端非抽卡动作断言（AUDIT-BREAK-4）；新增 S8 跨文件同步清单 A/B/C 三段与 `grep` / `__all__` 两道验收（AUDIT-BREAK-5 / 6 / 8）；「S4-3 后收集期即 ImportError」经核实不成立，改按真实断裂点设 **S7d**（M1）与 **S8-7**（M2）两块（AUDIT-BREAK-7，M1 由 29 块 / 16.4 人时改为 30 块 / 16.9 人时，M2 的 S8 由 3.1 改为 3.5、M2 由 5.5 改为 5.9 人时）；`reads` 双通道（管道 vs 策略查询）各自独立验收（AUDIT-BREAK-9）；其中 AUDIT-BREAK-2 / 3 各存一条 veto 备选（落点见 §3.1.4 与文末「自动化审查阻塞项」）。 **2026-09-27/28（用户裁决，第二批）**：① **ISSUE-032 改判**——`FiniteActive` / `DependentFiniteActive` 的配置接线**纳入本期**（**否决**上述第八轮「只验类不接线」的定稿），连带 `PityDef.max_triggers` + `config_toml` 解析 + GUI 控件 + `build_lifecycle` 产出路径（§3.1.3）；② **Lifecycle 正交化**——由「三个互斥类」改为「两个正交维度（激活 × 退役）四个组合」，新增 `DependentFiniteActive`（第四组合的退役计数**自「激活后」起算**），原「`depends_on` 优先、`max_triggers` 被忽略」的写法作废（§3.1.3）；③ **G3 定稿为独立 type `hard_exclude_owned`**（**该单一 type 名已于 2026-09-30 第二轮按用户裁决拆为两个，见末条 ①**），其 `ForceNotOwnedModifier` 的触发条件为 `CounterCondition('counter', pdef.threshold)`（**非** `Always()`——条件极性于 2026-09-28 独立审查出并修正，§3.10.4）；④ **`_PITY_TYPES` 改为由 `BEHAVIOR_REGISTRY` 生成**（新增 type 自动出现在下拉，S6a / S9-3 的「手工追加」步骤删除，§3.6）；⑤ **ISSUE-027 送达路径重梳为方案 A**——`initial_counts` 由 `GachaService` 局部变量提升为 `GachaState` 字段、新增 `GachaState.external_view()`、两条通道就地构造、`Banner.draw` **不新增形参**；并新增 §六 的 `GachaState.clone()` 保真独立验收项（§3.10.2）；⑥ 上述改动涉及的「三个 Lifecycle」类表述同步为四类。 **2026-09-30（G3 定位同步 + 待确认项如实记录，用户裁定）**：① §1.3 的 G3 行补「所涉卡池均已下线，定位改为**历史机制建模能力**」（依据 2026-09-29 官方公告 API 全量穷举 2759 条），并写明「S9 的正当性不依赖 G3 是否现行」；② §二 目标行的 G3 括注同步该定位；③ **修正两处手册行号引用漂移**：手册 §7 重写（`e0a4bda`）后，§1.3 的 `#L963` 与 §3.10.4 的 `#L959` 已指向无关内容，改指 `§7.1:938` / `§7.2:970` / `§7.3:1001`；④ §3.10.4 开头补「所涉卡池已下线」段（含「第二部装备补给不是同一机制」的区分）；⑤ **§3.10.4「全部已拥有」条重写为完整的分歧记录**：列 2026-09-29 专项查证（零直接信源、四候选）、两倾向对照表（候选 (a) 保底不生效 / 候选 (b) 仍给一个 UP）及其依据强度、**两处不一致（给不给 + 给的是什么）与「两者各违背规则原文的一半」**，**裁定维持「待确认」、不按旁证定稿**，实现侧按 (a) 占位但随之挂起；⑥ **§六 G3 专项 ③ 与 §七 S9-4 验收命令加注**：该断言是候选 (a) 的实现形态，定稿前不得当作已定稿验收；⑦ 手册 §7.4 补「模拟器侧取值同样未定稿」的指针。 **2026-09-30 第二轮（G3 双实现 + 三处事实修正，用户裁决）**：① **G3 的「全部已拥有」由「按候选 (a) 占位并挂起」改为双实现并列**：`ForceNotOwnedModifier` 加 `on_all_owned` 构造参数，注册 `hard_exclude_owned_skip`（形态 a，「硬保底·排除已获得（全拥有时保底不触发）」）与 `hard_exclude_owned_any`（形态 b，「硬保底·排除已获得（全拥有时仍给一件 UP）」）两个 type；上一条 ⑤ 的「实现侧按 (a) 占位但随之挂起」**由本条取代**；命名口径定为「形态写进 type key 与 display_name」，手册登记为一条待确认项、两个候选实现；② **「关于」页面两处保底文本改为由 `BEHAVIOR_REGISTRY` 生成**（`gui/about_dialog.py:67` / `:207`，原为硬编码且已漂移，P56 的 6 个 type 至今未登记），§四 补该文件行，落点归 S9-3；③ **删除三处不存在的「`config_toml` 类型白名单」引用**（§3.10.4 配套第 2 条、§四 `core/config_toml.py` 行、§七 S9-3 目标文件）：实测 `_build_pity` 只校验 `name` 与 `scope`，两个未知 type 直接通过；真实后果在引擎侧，`BEHAVIOR_REGISTRY[btype]` 抛 `KeyError` 后被 `PityEngine.__init__` 吞成 `logger.warning`、保底静默消失（实测 `behaviors == []`），即 S4-5 要修的问题；④ **§四 与 §七 目标文件清单对齐**：`core/state.py` / `core/milestone.py` / `tests/test_p60_gacha_state.py` / `tests/test_p63_overflow_integration.py` 四者 §四 已标 S9 而 §七 S9 子块漏列，已补入 S9-2 与 S9-4；⑤ §六 G3 专项 ③ 拆为 ③a / ③b 两条，§七 S9-4 的验收命令、目标文件与预算同步（S9-3 0.7 → 0.9 人时，新增 `tests/gui/test_about_dialog.py`）。 **2026-09-30 第三轮（引用层机械刷新，四路独立审查后的核查修正）**：① **`service/batch_simulator.py` 全部 13 处行号失效**（09-28 / 09-30 三次 P83 并行性能提交把该文件从 1149 行推到 1392 行，文档 09-30 仍在做「事实修正」却未刷新该文件）：`pentry` `:899-925` → `:1143-1168`、`_PityDef` 别名 `:163` → `:193`、`_PityDef(...)` 重建 `:179-204` → `:209-234`、五元组解包与 `PoolPitySpec` 构造 `:183-192` → `:264-274`、`initial_counts` `:398-408` → `:460-470`、`_ms_initial` `:415-421` → `:461-470`、`GachaState(...)` `:430`/`:446` → `:492`、`MPPool(initializer=...)` `:638-641` → `:848-850`、`pity_names` `:173-177` → `:254-266`；② **`pity.py` 六处**：`_active` Flag 写入 `:118-121` → `:128`、`reset`/`target_featured` 形参 `:130-131` → `:118`、`guaranteed_init` truthy 块 `:1013-1015` → `:1009-1010`、`create_behavior` `:836-892` → `:837-915`、`SoftPityMixin` 方法区间 `:509-537` → `:509-543`（原区间漏掉 `_rebind_state`）、§3.9.5 的「统一 `.get` + 空集早退」三处改按族标注（`SoftStepBehavior` `:273`/`:303`、`RotatingBehavior` `:467`、`TargetedBehavior` `:646`；原写「`total <= 0` 在 `SoftStepBehavior`/`HardPityBehavior` 内」类归属有误）；③ **手册 10 处锚点**（§21 缺口表随手册重写整体位移）：G1 `:2283` → `:2396`、G2 `:2284` → `:2397`、G16 `:2287`/`:775` → `:2400`、G5 `:2296` → `:2409`、G13 `:2304` → `:2417`、G14 `:2305` → `:2418`、G15 `:2306` → `:2419`、G5 正文 `:554` → `:560`、§20.2 `:2039` → `:2143`；④ 其余：`strategy.py:100` → `:96`、`cli.py:266-267` → `:285-286`、`config_panel.py:3534-3539` → `:3535-3539`、失效的相对链接改为纯文本指向（目标在仓库外）；⑤ **计数与描述更正**：§七「共 43 子块……主线 29」三项相加仅 33，改为 **45**（G16 2 + P82 2 + M1 30 + M2 11）；§四 对 `模块状态矩阵.md` 的描述「仍写『覆盖 G1 + G5 priority』」经实测已不成立（该行自 2026-09-22 起已含 G3 / S9 / S10 / S11 / S12 与 M1/M2 划分），更新点收窄为 G3 双实现与待确认项。 **2026-10-01 第六轮（Fixer，独立复核 12 项）**：① ISSUE-901 的改判（槽位字段 / `compute_scope_mappings` 减量 / 两处构造点改造推迟到 GATE-5 末条）补同步到**四处残留的「S8 施工语」**（§3.9.3 `worst_impact` 行、§四 `worst_impact` 行、§四 `pity.py` 的 ISSUE-026 追加、§七 S8-5）并逐处挂 `ISSUE-904` 标记（**ISSUE-904**）；② **GATE-5 末条扩为完整收口清单**（七项同批：函数本体 / 4 调用点 / 10 旧类 / 6 个槽位字段 / `compute_scope_mappings` 槽位产出 / 两处构造点改造 / S8-7 的 5 个测试文件），此前全篇十余处引用的那一条本身只列三项（**ISSUE-905**）；③ S7d 的「失败时点②」与 S8-7 的回滚说明按改判前因果描述修正（S8 不删字段、不删函数本体，故②与①同一 commit；S8-7 与 S8-4 不再共享删除面）（**ISSUE-906**）；④ §3.9.3 的 `tests/` 行补登记**等价性装置**这一例外消费方（**ISSUE-907**）；⑤ 删去 §3.9.3 中「`_resolve_selected_slots` 仍改为直接给出卡集合」这句旧稿残留（该名字是旧 `TargetedBehavior` 的槽位级私有方法，照改会破坏 S5a 对照基准与旧类槽位语义）（**ISSUE-908**）；⑥ `factor_override` 的 `exempt` 改为一律只读 `scope_cards`，并把该函数补登记进 §3.1.6 叶子层与 §四（**ISSUE-909**）；⑦ AUDIT-BREAK-1 补「四个别名键必须先废弃」这一改造前提（`pentry` 的 `type`/`start`/`end`/`increment` 对 `btype`/`soft_start`/`soft_end`/`soft_increment`，写读两端须同 commit 改名，否则 dataclass 驱动式静默算错、键集断言恒红）（**ISSUE-910**）；⑧ 透传面由「三处」扩为「引擎侧三处 + GUI 侧五处」，并定稿 `reads` 的 GUI 通路为「不加控件但五处原样透传」（**ISSUE-911**）；⑨ H3 删分支所破坏的两处正断言与 GUI 的 `_PITY_TYPES` 写死计数补进 S6a / S9-3 与 §四（**ISSUE-912**）；⑩ `config/config.toml` 的 P79 常驻护栏波及面补登记，示例段定稿为**注释形态**（**ISSUE-913**）；⑪ `initial_counts` 的推导点位于 `if env.milestone_defs:` 块内的事实与「定稿为 `run_simulation` 内 clone 之后赋值」写入 §四，并把 `batch_simulator` 的**四处行号批量刷新**（`:492`→`:501`、`:461-470`→`:466-479`、`:1143-1168`→`:1161-1186`、`:209-234`→`:218-243`）（**ISSUE-914**；**2026-10-09 实测**：括号内三个右值为**错值**，现值应为 `:508` / `:477-482` / `:1168-1193`，仅 `:218-243` 准确；同段第⑦轮补正的 `MPPool(...)` 块与 `run_batch_parallel` 定义行现值亦为 `:873-876` / `:728`，原标 `:866-869` / `:721`；**ISSUE-953**）——**限定**：该四处是第六轮**全部**的刷新面；同文件另有两处旧引用（`MPPool(...)` 块、`_PityDef` 别名）与一条 `run_batch_parallel` 定义行未随该轮更正，已由第七轮补正（**ISSUE-915**）；⑫ `factor_override` 的模块归属随之补进 §3.1.6 / §四（并入 ⑥）。<!-- REVIEW-R1-FIX: ISSUE-915 -->**2026-10-01 第七轮（Fixer；独立复核 5 项 + 上一轮 ISSUE-914 的 3 条子项归并）**：① 两处旧引用未随第六轮的批量刷新更正（`MPPool(...)` 块 `:848-850` → `:866-869`、`_PityDef` 别名 `:193` → `:202`），同段 `run_batch_parallel` 定义行 `:638` → `:721` 一并补正，并把第六轮末句「全篇引用已按此批量刷新」收窄为「点名的四处已刷新，其余三处同批补正」（**ISSUE-915**）；② `initial_counts` 的三处表述互斥（`core/state.py` 行写「`_ms_initial` 计算点删除」、`batch_simulator` 行写「构造点须补 `initial_counts`」+「推导上提到块外」、`gacha_service` 行定稿「`run_simulation` 内 `clone()` 之后赋值」），统一为**一处推导源（`run_simulation` :310-315）+ 一处赋值点（`clone()` 之后）**——`batch_simulator` 侧只做删除（`_ms_initial` 与 `initial_counts=` 形参），里程碑 handler 改从 `state` 形参取，「上提到块外」写法作废（**ISSUE-916**）；③ `initialize` 已扩为多命名空间而 `rebind` 仍收单 `name`，`X_soft` 的 `_active` Flag 无重绑通道——定稿取「每个命名空间各持一个 Flag + `rebind(state, name, namespaces=())` 对称重绑」（与旧实现内层 `SoftStepBehavior` 的 Flag 形态同构），备选（只持 `name` 的 Flag、`namespaces` 直接写 state）记为未采用（**ISSUE-917**）；④ `get_config` 的别名键改名未登记两处既有消费面——`_do_update_preview` 的 `pdef.get('type', '?')`（预览逐条打印 `?`，且无任何测试覆盖的静默失真）与 `tests/gui/test_config_panel_pity.py:220` 的正断言（必红），并入 S7a 同批改造（**ISSUE-918**）；⑤ §3.1.3「归属定稿」段仍把骨架调用写成两实参 `initialize`，改为三实参（**ISSUE-919**）。**2026-10-01 第五轮（Fixer，独立复核 6 项）**：① 三族协议补**声明键集**只读成员 `state_keys()`（**ISSUE-501**）——§3.12.1 的「状态键合法」、§3.12.2 判据 1/2、§3.13 状态层 checker 与 S10-2 的构造期 `ConfigError` 四处都以「声明集」为输入，而三张协议表此前无任何承载成员，S10-2 / S11 无可用比对集；落点为 §3.1.1 / §3.1.2 / §3.1.3 三张协议表 + §3.1.4 骨架的 `self._declared_keys` 汇总 + §3.9.2 的 `Modifier.state_keys()` 默认实现与 §3.14.2 的转发 + §3.12.1 / §3.12.2 / §3.13 回指该成员名；② `_redistribute_scope` 的删除时点定稿为「S8 不删函数本体，只删 `core/__init__.py` 导出，本体并入发布前移除旧类的 commit」（**ISSUE-502**）——pity.py 内 4 处旧类调用点（**2026-10-09 实测订正：:549 / :661 / :727 / :731**，原写 :477 / :589 / :655 / :659 整体 +2）按 GATE-5 保留到发布前，只删函数即那 4 处在调用时 `NameError`；③ scope 取值统一为模块级 `_norm_scope(pdef, default='ssr')`（**ISSUE-503**）——原稿取值列写 `pdef.scope` 原值而依据列引的却是 `create_behavior` 的 `.lower()` 归一化式，直构路径下 `scope_cards.get('SSR')` 取空致保底静默恒等；④ `infer_rarity_from_spec` 的处置由「保留」改判「随 `aggregate_probs_by_rarity` 一并删除」（**ISSUE-504**）——其三类消费者全在 S8 的删除面内、函数本体零消费者，原「保留」使 §六 / S8-2 的 grep 零命中验收恒红；⑤ §3.9.2 的 S8 内循环写死 `self._view` 改为 `self._view_for(mod)`（**ISSUE-505**）——与同计划 ISSUE-407 的强制纪律冲突；⑥ `_EVENT_DRIVEN_TYPES` 的后果表述收窄为「仅规则 3 互斥校验失效」（**ISSUE-506**）——`is_active` 早退已由骨架对全部类型无条件承担，原表述为旧架构残留。 **2026-09-30 第四轮（Fixer，独立复核 8 项）**：① `ConditionalModifier.apply` 补条件判定（**ISSUE-401**，原只在 `factor` 判 → S12-2 至 S7 期间条件包装器全部退化为无条件）；② `Pity.after_draw` 补 `fired` 实参（**ISSUE-402**，原三实参调用 → `triggers` 退化为「激活后的抽数」或 `TypeError`）；③ `pdef.target_featured` 的 preset 承接（**ISSUE-403**，新增 `_target_of(pdef)` 选择子 + `ThresholdForceModifier` / `BoostModifier` 的 `target=` 形参，原「`judge="featured"` 即承接」不成立）；④ `reads` 门控落点为派生 ctx 的 `Pity._gated_ctx`（**ISSUE-404**，禁止就地改写**本调用内的**共享 ctx——每次调用构造一个 ctx，在同池全部保底之间复用；「每池共享」的旧口径已于 2026-10-01 更正）<!-- REVIEW-R1-FIX: ISSUE-926 -->；⑤ `_validate_registry()` 口径写死为「导入期只判 `preset` 可调用」（**ISSUE-405**，键集校验归运行期 `create_behavior`）；⑥ `Lifecycle` 基类统一代理 `depends_on`（**ISSUE-406**，`_build_activation_graph` 对每条 behavior 都读它）；⑦ 零件 `namespace` 声明面 + `NamespaceTracker` + `initialize(state, name, namespaces)` + `Pity._ns_views` / `_view_for`（**ISSUE-407**，原 `X_soft` 无产出者）；⑧ §四 的 `ForceNotOwnedModifier` 归属改回 `core/pity_modifier.py`（**ISSUE-408**，只留 registry 条目）。**2026-10-01 第八轮（Fixer，GATE 四项门控复核）**：① **GATE-2 文件清单**——`gui/config_panel.py` 的「`_PITY_TYPES` 已改为由 `BEHAVIOR_REGISTRY` 生成」六处为**既成事实误记**（实测仍为硬编码 10 项字面量、全仓与全历史检索生成式写法零命中，`1dbc9b0` 只改了本计划文件），六处逐条改判为「**待改造**、施工落 S6a」并写明三项代码改动（字面量→生成式 / registry 5 处 `display_name` 对齐 GUI 现值 / registry 条目顺序对齐 GUI 现值），§3.6 的 1125 与 1126 互斥表述随之消解（**ISSUE-929**）；`core/config_toml.py` 四处失效锚点更正（`:611`→`:636`、`:654-660`→`:677-682`、`:669`→`:692`、`:687`→`:710`）并对该文件锚点做全量复核（`:385-421`→`:392-428`）；② **GATE-3 依赖顺序**——S4-1 的验收在自身位置不可达（preset 工厂属 S4-2 / S4-3，而 `_validate_registry()` 在 `pity.py:832` 导入期即被调用），定稿为「S4-1 只改 validator 与 `create_behavior` 分支 + 写入**过渡判据**，条目按**原子**地在 S4-2 / S4-3 置 `class: None` 并写 `preset`，S4-3 收口时删除过渡分支」，两条原属 S4-1 的验收下移 S4-2、终局验收移入 S4-3，§3.2 与 GATE-5 的 S4-1 回退面同步（**ISSUE-930**）；③ **GATE-4 风险缓解**——ISSUE-926 的两个子项修复（`:1444` 派生 ctx 的归因改为 `SoftPityMixin.before_draw`、`:5` 的「每池共享」改为「本调用内的共享 ctx」），并**清空文末阻塞章节**、6 轮熔断记录移入「自动化审查记录」的第 6 次审查 details（**ISSUE-926**）；④ **GATE-6 测试策略**——M2 的 S8-1 至 S8-5、S9-1、S9-3 七个条目补**块级验收命令**（对齐 GATE-5「低层块回退后须重跑受影响块的验收命令」），S7a 的 `rotating_inverse` 断言加注「前提 = S6a 的生成式改造已落地」并给出未落地时的替代断言（**ISSUE-931**）。 **2026-10-01 第九轮（Fixer，GATE-6 测试策略续修）**：块级验收命令与其断言对象未绑定，三处存在「假通过」失效面（**实测**：S8-5 的 `-k "scope_cards or boundary"` 零命中（11 deselected，pytest **exit code 5**；**该计数 2026-10-09 订正为 16**）；S8-3 的 `-k redistribute` 只命中 3 条**既有**旧函数用例（退出码 0 而 `factor_redistribute` 零覆盖）；S10-2 的 `-k "illegal or cycle"` 用例命名未约束）。定稿「验收命令与断言对象绑定纪律」三条（计划内写死用例名 / 收集 ≥1 条 / 命中项不得全为既有用例）写入 §七 引言；三处逐条补命名约束与收集守卫（S8-3 过滤词改为 `factor_redistribute`，目标文件补 `tests/core/test_pity_rotating.py`）；其余四处带 `-k` 的命令（S5c / S8-6 / S9-1 / S9-3）补同款收集守卫；S4-5 记为合规范例（**GATE-6-测试策略**）。**2026-10-08 表示切换**：Modifier 的表示由**因子向量（乘性）改为增量向量（加性）**（用户裁决）。波及 §3.1.2（机制表加「A 侧形状」列、`ctx` 加 `base_probabilities` 字段）、§3.1.5 全节、§3.9.2 / .3 / .4 / .5、§3.12.1、§3.13、§四、§五、§六、§七 与 §3.1.4 骨架。接口 `factor(view, dist, ctx)` 改名 `delta(view, dist, ctx)`，**参数由四参收为三参，`readonly` 随「Modifier 是 pure 函数」废除**；助手 `transfer_factors` 改为 `transfer_linear(dist, A, Q, amount, shape, weights)`，`shape = 'declared'` 已启用（`HardModifier(tf=true)` / `NonFeaturedModifier` / `SelectedModifier` 三个机制取之）。依据与逐项对照见《保底算子表示切换·因子向量转增量向量·改写方案》。**2026-10-09 任务块范围与预算重新核定**（原注「范围与预算须按新形态重新核定」的落地）：取消三块与现行形态矛盾的子块——**S2b**（目标解析器族，A/Q 已内联进各类方法体）、**S8-3b**（`factor_override`（assign）原语已合并为 `transfer_linear`）、**S8-3c**（六类合并为 `TransferModifier`，被「一机制一类」否决）；**S2a** 扩为「基类 + 六类 + A/Q 内联 + `_lower_rarities`」并由 0.8 上调至 1.2 人时，**S8-3** 由 0.5 上调至 0.7（吸收 `declared` 分支与守卫）、**S8-6** 由 0.3 上调至 0.6（吸收六场景逐卡对照）。汇总：M1 由 31 块 / 17.7 人时改为 **28 块 / 16.6 人时**（**2026-10-09 第二轮（ISSUE-005）：S4-4 的 0.3→0.7 与 S7a 的 0.4→0.6 两块块内预算调整回写入 §七 求和行**），S8 由 4.4 改为 **4.0 人时**，S9 由 2.9 改为 **2.7 人时**（S9-2 条目自述的 0.8→0.6 下调此前未回写汇总行），M2 由 7.3 改为 **6.7 人时**，全计划由 46 子块改为 **43 子块**（G16 2 + P82 2 + M1 28 + M2 11）。**同时改掉一处虚高**：原链式记法（16.4 → +S7d 0.5 → +S4c 0.8 → 17.7）与块清单自相矛盾（16.4 已含 S7d 与 S4c），现一律改按**逐块求和**核定。**同日另有：Modifier 方法名 `delta` → `compute_delta`**（用户裁决，与 `PityDef.deltas` 解撞，见 §3.9.2 命名段）；**两份配套分析文档（三案推演 / 改写方案）归档**至 `docs/03-归档/subsystems/保底系统/`，其结论已全部落入本文。**2026-10-09 裁决 ISSUE-928**：`reset` 取值白名单并入 **G16-1**（备选「判为 P64 范围外」已否决），见 §3.1.1 三点声明第 3 条与 §3.8 配套段；`03-审计.md` 异常 6 随之由「待裁决」改为已裁决、待 G16-1 关闭。**2026-10-10 四条用户裁决**：① **裁决 6B′**——CR 掷骰相位由 `StreakTracker.commit` 改归 `StreakTracker.prepare`（`before_draw`、`advance` 之后、Modifier 链之前）；此为独立子 agent 考察后的改判，它同时修掉 6B 的一处未登记缺陷（按 §3.2 的 tracker 顺序落地时 `cr_counter` 恒为 0），并闭合首抽缺口与随机流位置差，`rotating_cr` / `rotating_cr_soft` 回归「与旧类逐场一致」批次，差异归因 (c) 项作废；连带 Tracker 契约新增第 5 个方法 `prepare`、`_preset_rotating_cr` 补代码块（原只有表行）、§3.9.6 新增只读查询的例外与两期处置、S1c 拆为 S1c-1 / S1c-2（主线 29 → 30 块、总数 44 → 45、M1 16.6 → 17.35 人时）。② **G16 方案确认取 (a)**（GUI 兜底条目改写为全合法形态）。③ **ISSUE-002 另一支确认维持 7B 的类型级硬拒**。④ **`acquired` 口径改判为迁移**（策略侧「是否已拥有」改用含初始持有的口径，但**不动 `state.acquired` 的定义**；实测当前 `config.toml` 全 `initial_count = 0`，故 P79 golden 无需重固化）。待人工裁决由 **7 组缩减为 3 组**。**2026-10-10 文书收尾（本轮）**：① **新增 S9-5 子块**——④ 的存量持有口径迁移此前只有 §四 的裁决而无 §七 落点，补为独立子块（~0.4 人时；M2 11 → 12 块、总数 45 → 46、S9 2.7 → 3.1、M2 6.7 → 7.1、全计划 25.4 → 26.55（差额 +1.15 = 上一轮 RULING-6B′ 的 M1 +0.75 与本轮 S9-5 的 +0.4；25.4 是本轮之前的声明值，其 M1 分量 16.6 当时已滞后于逐块求和）），并把 API 形态由 `SimView.owns()` 改判为 `ctx.state.total_holding()`（策略侧已持公开 `ctx.state`，改用 `SimView` 会连带改 `build_strategy_context` 与 9 处直构 `StrategyContext(...)` 的测试，而两 API 是同一实现的同一口径），次序约束由「不得早于 `SimView` 交付」改为「必须排在 S9-2 之后」；同轮订正 §四 该行原写的「5 个内置策略的 9 处」为实测的 **4 个文件 9 处**，并登记 `TargetAcquiredCondition` 与循环快照指纹两处**查证为不纳入**。② **S1c 的粒度裁定表行补齐**（上一轮拆分只改了任务块与汇总行，表内缺行），并给该表补「预算时点」注——表中 `S1b` / `S3` 两行的值已被 2026-10-10 的上调取代，防据表反推现行预算。③ **M1 执行顺序串补 `S1c-1 → S1c-2`**（上一轮拆分后漏登）。④ **2026-10-10 三项收尾裁定**：`TargetAcquiredCondition` **维持不含初始持有**（用户裁定；其语义为「获得 N 张后停止」，与 S9-5 的「是否已拥有」不同源，故不纳入迁移）；**P82 接线排期定为独立先行、排在 M1 之前**（用户授权由主 agent 定；§1.5 两处口径随之由「待裁决 / 建议」改为定稿，敏感集合第 2 类确认为真实敏感面、P82-2 归因表取五类）；`gacha_simulator/gui/batch_simulator.py`（0 字节的 git 跟踪文件，与 `service/batch_simulator.py` 重名、工作树零引用）按用户指示移入 `.recycle_bin/`（commit `8e0de08`）。**2026-10-09 行号核对第二轮（Fixer）**：① **回退上一轮 14 组方向性误改**（上一轮把 `b978e89` 已核对正确的锚点改成偏离更大的值，`pity.py` 一律 +2 / `pool.py` 一律 −2 / `config_toml.py` 两处 −8 与 −62，而真实偏移均为 0，故该轮「机械核对」的净效果为负）；② **首次修正** `core/pity.py` 的**系统性偏移 12 组**（`PityEngine` / `PityState` / `BEHAVIOR_REGISTRY` / `_validate_registry` / `create_behavior` / `_BTYPE_ORDER` / `compute_scope_mappings` / `_build_activation_graph` / `DrawInfo` 透传 / 卡集合前两项 / 守卫行 / `threshold` 默认值）与 `service/batch_simulator.py`（`_ms_initial` 段、`GachaState(...)` 构造点、`MPPool` 块）、`core/config_toml.py`（H3 拒绝分支 / `reset` 直取行 / `_deltas_to_soft_interval`）、`core/pool.py`、`core/strategy.py`、`core/strategy_context_builder.py`、`scripts/p79_verify.py` 与测试侧的其余实测偏差；③ **订正 `worst_impact` 的 `_ref_pool` 死代码论断**：该属性与所述分支在全库均不存在，改为对 `_ref_pool_entry`「写后即读、可退化为局部变量」的定性；④ **恢复「引用核对记录（2026-10-09，第二轮）」节**（上一轮整体删除，致核对口径与已知局限一并消失、下一轮失去基线），登记「已修 / 未核 / 局限」三段；⑤ 「自动化审查阻塞项」的绝对表述「当前无未解决阻塞项」改为「设计层无未解决阻塞项」，并指向该核对记录（ISSUE-001 ~ ISSUE-009 / REG-R1 / ISSUE-946）；⑥ **GATE 修复轮（Fixer，2026-10-09）**：**S2a 按 GATE-1 再细分为 S2a-1 / S2a-2**（主线 28 → 29 块、总数 43 → 44，预算合计 16.6 人时不变）；**S4c 补入 M1 强制执行顺序**（GATE-3，插在 S4b 与 S4-2 之间）；**两组 `+2` 行号残留订正**（GATE-2：`pity.py#L1216` ×5 → `L1214-L1215`，4 处旧类调用点 ×6 → `:549 / :661 / :727 / :731`）；**4 个独立先行块补目标文件与验收命令**（GATE-2 / GATE-6：G16-1 / G16-2 / P82-1 / P82-2）；**§五 风险表两行订正并补 S4c 风险行**（GATE-4：P75 行删去已取消的 `ConditionalModifier`、S8 / S9 行预算对齐 §七 现行值 4.0 / 2.7）；**S8-5 / S9-1 的实测计数订正**（GATE-6：11 → 16 deselected、10 → 12 条既有用例）；**文末「0 阻塞」补口径说明**（GATE-4）。**2026-10-09 GATE 复核第二批（Fixer，4 项门控）**：① **GATE-1 变更粒度**——G16-1 / G16-2 / P82-1 / P82-2 四块补**块级预算**（合计 2.1 人时），并把「全量预算」口径写入 §七「计数与预算的核定方法」（独立先行 2.1 + M1 16.6 + M2 6.7 = 25.4，此前只取 M1 + M2 的 23.3 会使四块落在预算外）；② **GATE-2 文件清单**——§3.1.6 的模块表由「三模块」改回**两模块**（`pity_condition.py` 已随 §3.14 取消，与 §四 同口径），§四 `02-实施.md` 行的「四模块」同批改三；③ **GATE-3 依赖顺序**——`InvariantChecker` 的 pickle round-trip 由 **S7b 移入 S11**（S7b 排在 S11 之前，按字面施工即 `ImportError`），§3.13 / §七 S11 的「S7b 已含」反指同步删除；④ **GATE-6 测试策略**——S10-2 的 ②b（引用非法键的 Condition）与「收集到 ≥4 条」守卫删除（断言对象已随 §3.14 取消），§1.2 / §3.10.4 / §3.12.1 / §3.12.2 / §3.13 / §四 pickle 段六处对 `Condition` / `ConditionalModifier` / `CounterCondition` 的指向改为现行内联形态。**2026-10-09 GATE 复核第二批续（Fixer，2 项门控）**：① **GATE-2 文件清单**：§四 `core/result_store.py` 行的保底分支锚点由 `:479-482` 订正为 **`:519-522`**（偏移约 40 行、原值落在 P79 的 docstring 上，**超出「区间起点差 1 至 4 行」的容忍度**），并把该订正写入「引用核对记录（2026-10-09）」的第四轮补记；② **GATE-6 测试策略**：清完 §六 两处指向已删符号的验收项：通道 A 条由「断言收到**非 `None`** 的 `external`（配 `reads` 的池）」+ `-k "reads or external"` 改为「断言 `sim` 实参为 **`SimView` 实例**」+ 写死用例名 `test_channel_a_fills_sim_view` + `-k sim_view`，**与 §七 S9-4 同口径**；S10 组合正确性条由「`CounterCondition` 经 `ConditionalModifier` 包裹」改为「内联后读键落在 Modifier 自己的 `state_keys()`」，**与 §3.12.1 / §3.12.2 / §3.13 三处对齐**；同族残留一并清理（§3.1.2 的方法名定稿段删去 `ConditionalModifier` 的转发说法、`apply` 承载处改指 **§3.14.3**；§3.10.4 两处删去已取消的 `reads`）。<!-- REVIEW-R1-FIX: GATE-check-1-变更粒度 --> <!-- REVIEW-R1-FIX: GATE-check-2-文件清单 --> <!-- REVIEW-R1-FIX: GATE-check-3-依赖顺序 --> <!-- REVIEW-R1-FIX: GATE-check-6-测试策略 --><!-- REVIEW-R1-FIX: ISSUE-004 --> <!-- REVIEW-R1-FIX: ISSUE-953 -->**2026-10-09 第 11 次审查（Fixer，代码审计维度，10 项；编号见「自动化审查记录」本节）**：① **AUDIT-BREAK-1**——S4b 条目内**复述**「四个别名键（`type`/`start`/`end`/`increment`）写读两端同 commit 改名」的前提（原只以「见 §3.6」指向，照抄 `dataclasses.fields` 式子会让 `btype` 落回默认且不报错）；② **AUDIT-BREAK-2**——**G16-1 升为 S4-5 与 S4c 的强制前置**（GUI 兜底保底条目的 `type='soft'` 现被构造兜底静默吞掉，S4-5 改抛 `ConfigError` 后即「打开无保底段的配置后运行模拟」直接崩），写法落进 M1 顺序行、独立先行块组标题、G16-1 与 S4-5 条目，S4-5 验收补 GUI 路径一条；③ **AUDIT-BREAK-3**——`Modifier` 基类 `apply` 的默认实现**分两期**：M1 期（S2a-1 起）只写占位 `raise NotImplementedError`，S8-1 换成 `_apply_delta(dist, self.compute_delta(...) or {})`（原稿把 S8 期式子写成唯一形态，且 §3.9.2「S1–S5 不实施」与之互斥），§3.9.2 加唯一例外括注、§3.14.3 改写为两期、S2a-1 验收 ① 改为可执行断言；④ **AUDIT-BREAK-4**——S8-2 的 `pool.py` 内部调用行号 `:270/:275` 订正为 **`:280` / `:285`**（与 §3.9.3 表第 3 行一致；原值偏 10 行且落在非空白行，空行机核抓不到）；⑤ **AUDIT-BREAK-9**——S9-2 的 `service/batch_simulator.py` 从「随 `reads` 删除」的划掉面**移回本步目标文件**（与 §六 ISSUE-916 ② / §四 该行的「删 `:477-482` 推导与 `:486` 实参」互斥），「本步现行内容」补第 ④ 件，`core/state.py` 行补 `GachaState.clone()` 的逐字段拷贝保真；⑥ **AUDIT-BREAK-10**——S1a 目标文件补 `core/config_toml.py` + `tests/core/test_pity_config_toml.py`，写死两条（类属性保留为模块级常量的同对象别名、同一 commit 给 `config_toml` 的同名拷贝补 `rotating_inverse`），验收命令补该文件两条断言（删断言或改成「剔除后相等」都不许）；⑦ **AUDIT-BREAK-5 / 6 / 7**——复核为**已对冲**（namespace 非 `None` 的 Modifier 用例、通道 B 的 `-k channel_b` 独立验收、S6c 的四处 + 端到端用例），**不改正文**；**AUDIT-BREAK-8** 与 ②同源（GUI 兜底条目），由 ②的强制前置一并覆盖。机械项：正文新增 3 行，指向本计划自身的行号引用按实测回写（2597→2599 / 2659→2662 / 2697→**2712** / 2805→2808（**2026-10-09 订正**：原写 `2697→2700`，实测 2700 是 S4-1 的 preset 构造形态条、2712 才是含 `S4b` / `max_triggers` / `rotating_inverse` 三处互指的条目；原表另列 `2709→2712` 一项，而本轮门控 JSON 实际未引 2709，该对齐无对应引文，已删）），锚点全量机核复跑 **428 条**（`.py` 409 / `.md` 19；纯空白行 0 / 越界 0 / 目标文件缺失 0），见「引用核对记录」第六轮补记。<!-- REVIEW-R1-FIX: AUDIT-BREAK-1 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-2 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-3 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-4 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-5 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-6 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-7 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-8 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-9 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-10 -->
> 触发：P56 审查发现的「触发器 × 选择器 × 拓扑 × 效果」四维抽象 + 组合爆炸。**2026-08-24 设计重建**：用户追问「最优雅架构」，从领域本质重新理解保底 → 提出 Tracker + Modifier + Lifecycle 三元组纯函数架构；用户裁决命名 Tracker+Modifier。
> 依赖：P55✅（counter 驱动正交分解 + deltas 展开）+ P56✅（6 个事件驱动类 + Flag/Counter/_redistribute_scope + LifecycleConfig，作为等价性基准）
> 合并：**P82（保底管道顺序接通）于 2026-09-16 并入本计划**，见 §1.5；其结论直接影响 §1.3 的 G5 项与 §3.6 的 priority 设计，P82 文件已归档
> 命名：Tracker（追踪器，状态转移）+ Modifier（概率修正器）+ Lifecycle（生命周期）
> 配套分析文档（**均已归档，2026-10-09**）：正文出现的「三案推演 §X」= `docs/03-归档/subsystems/保底系统/保底算子形式化三案推演与对比·乘性因子·加法增量·混合通道.md`，「改写方案 §X」= `docs/03-归档/subsystems/保底系统/保底算子表示切换·因子向量转增量向量·改写方案.md`。两者的结论已全部落入本文，只作推演过程记录，**不再是活规格**。

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

[`SoftPityMixin`](gacha_simulator/core/pity.py#L507) 缓解了 soft 维度，但 cr 是 RotatingBehavior 子类（[pity.py:554](gacha_simulator/core/pity.py#L554)）、targeted 是独立类（[pity.py:613](gacha_simulator/core/pity.py#L613)）。新增任意拓扑维度（如 inverse 必歪），将与每个现有维度再组合。每类重复实现 `_scope_total_prob`/`_featured_slots`/`_is_trigger_rarity` 骨架（[pity.py:490-498](gacha_simulator/core/pity.py#L490-L498)、[pity.py:694-698](gacha_simulator/core/pity.py#L694-L698) 等多处），after_draw（状态更新）与 before_draw（概率修正）硬编码耦合在各类的 if/else 里。**counter 驱动的 soft/hard 另起一套基类，与事件驱动完全不通**。<!-- REVIEW-R1-FIX: ISSUE-001 --><!-- REVIEW-R1-FIX: ISSUE-002 -->

### 1.2 剩余缺口盘点（2026-08-24 核实，含双信源）

| 缺口 | 现状核实 | P64 角色 |
|------|---------|---------|
| G1 幻塔连中后必歪 | 真缺口——rotating 只支持「歪→必中」，不支持「中→必歪」 | 新增 `ForceNonFeatured` Modifier + inverse preset |
| G16 幻塔完全不重置 | 单行——[`_should_reset`](gacha_simulator/core/pity.py#L205-L212) 加 `reset="never"` 分支 | **独立先行**（独立 commit，不并 P64） | <!-- REVIEW-R1-FIX: ISSUE-001 -->
| G19 尘白禁区不歪池 | **✅ 矛盾已解决（2026-09-18 独立调研）**：确认真实机制为「每次出金 100% 为当期 UP」。依据：三个相互独立信源直述同一规则（snowbreak.gg / Steam 社区 / Stage1st）+ 期望值数学自洽（不歪池综合出金率 1.24% 时拿 UP 期望约 80.6 抽，与米池的 80.65 抽相等；若提前出金仅 50% 为 UP，期望应约 121 抽，与三方实测数据冲突）+ 官方对米池必写「占出率 50%」而对特选池从不写该条款的对比。手册已据此修正：§15.3 配置由 `hard(target_featured=true)` 改为 `targeted(fate_threshold=0)` 加 `selected_card_init`；§15.4「165 箱当前无此机制」改为「P58 已覆盖」；§21 G19 行同步 | **已处置**；顺带发现手册全部 `targeted` 配置均缺 `selected_card`（见下方注） |

> **2026-09-18 顺带发现（手册层面，P64 范围外）**：手册的 `targeted` 配置除本次修正的尘白 2 处外，其余 **7 处**均未配 `selected_card_init`：绝区零 `epitomized_weapon`（定轨武器，`fate_threshold=1`）与 `bangboo_select`（邦布池，`=0`）；鸣潮 `wengine_targeted`（定轨武器，`=1`）、`ww_standard_weapon_select`（常驻武器，`=0`）、`ww_beginner_select`（新手池，`=0`）；§十四 `lds_mixed_select`（`=1`）；异环 `yihuan_wp_targeted`（武器定轨，`=1`）。**这不是配置缺陷**——`selected_card` 是运行时状态，定轨类玩法本就由策略层经 `switch_epitomized_target`（[gacha_service.py:292](gacha_simulator/service/gacha_service.py#L292)）在模拟中设定目标，把目标写死在 TOML 里反而与机制不符。但手册原先未说明这一点，读者照抄且不配策略时会遇到保底不生效且无任何提示。**已处置**：手册 §〇「保底 type 速查」补说明，列出两条设置途径与静默退化的行为。实测依据：`targeted` 的必中分支条件为 `self._guaranteed.is_set() or (selected and ...)`（[pity.py:652](gacha_simulator/core/pity.py#L652)），只判 `selected` 是否非空（实测填不存在的卡 ID 与填真实卡 ID 效果相同，均使概率由 0.001/0.001 变为 0.002/0.0）；`after_draw` 在 `selected is None` 时直接 return，命定值不累积。

### 1.3 保底相关缺口完整盘点（2026-08-24 逐条核实，双信源纪律）

> 信源纪律：两个以上不同信源一致且无矛盾才能确定为机制，否则标注「待确认」。见用户级记忆 `feedback-search-report-discipline`（位于 `~/.claude/projects/d--Users-DELL-Desktop-gacha-simulator----------/memory/`，在仓库之外，故不作相对链接）。

| 缺口 | 语义 | 归属 |
|------|------|------|
| G13 战双新手首次 40 | `hard.threshold` 首次特殊值（[手册:2417](docs/主流抽卡游戏卡池机制配置转换手册.md#L2417)，40 vs 60） | 🟢 配置即可（2026-08-24 双信源确认：[caoteng951](https://www.caoteng951.cn/tengzx01/4662.html) + [9game](https://www.9game.cn/zspms/4456638.html)）：`hard(threshold=60, counter_init=20)`，首次 40 触发、归零后续 60 |
| G2 阴阳师神眷阈值 | 神眷 = 「出 SSR/SP 概率掉落 + 累抽 450/800 必定获得」（[手册:2397](docs/主流抽卡游戏卡池机制配置转换手册.md#L2397)，机制双信源确认 2026-08-24：[17173 2023](http://news.17173.com/z/yys/content/01112023/111739115.shtml) + [9game 2023](https://www.9game.cn/yys/9780872.html)） | 🟡 **milestone 层扩展（2026-08-24 归属修正）**：神眷是兑换道具（资源），「必定获得」本质是累抽奖励（milestone at=动态 threshold），非保底概率；450/800 依赖全图鉴状态（跨系统状态）。与 G14（pity 动态 threshold）分属两系统，P64 范围外 |
| G14 战双命运池浮动 | 每次保底周期随机 T∈[80,100]、非保底出 S 1.5%、出 S 重置重抽 T（[手册:2418](docs/主流抽卡游戏卡池机制配置转换手册.md#L2418)，机制双信源确认 2026-08-24：[doyo](https://www.doyo.cn/news/26839.html) + [taptap 数学分析](https://www.taptap.cn/moment/15230243631530325)） | 🟡 后续扩展方向：T 分布未公布（U13）；确认后 P64 条件谓词可表达「counter ≥ 随机 T」 |
| G5 绝区零执行顺序 | 福利保底（`hard(max_triggers=1)`——**ISSUE-032：`max_triggers` 已纳入本期配置接线——`PityDef.max_triggers` + `config_toml` 解析 + GUI 控件（2026-09-27 裁决），见 §3.1.3**）应先于 targeted——当前 `_BTYPE_ORDER` hard=1 < targeted=3 已满足（[手册:560](docs/主流抽卡游戏卡池机制配置转换手册.md#L560) 描述过时，2026-08-24 核实） | ✅ **纳入 P64 主线**：显式化现有隐式顺序 + 提供覆盖能力（调度层 `priority`），见 §3.6 |
| G15 pjsk 加权抽数 | 付费石双倍天井进度（[手册:2419](docs/主流抽卡游戏卡池机制配置转换手册.md#L2419)，付费 +1 / 免费 +0.5） | 🔴 **缺口（2026-09-21 重估）**：原记「🟢 近似可配」（`reward.resources_gained` 每抽按池注入 + exchange pool 兑换 50/100 档），但按「精确建模原则」（CLAUDE.md §二）近似不计入已覆盖。该近似有语义打折（卡附带产出 vs 动作进度）与配置脆性（全 reward 需配）两处偏差，严格语义需 milestone `weight_by_pool`（milestone 层，P64 范围外） |
| G3 崩坏3 UP 保护排除已拥有 | 精准补给每 50 抽必出 UP 装备，但**已获得的装备从 UP 组中排除**（[手册 §7.1:938](docs/主流抽卡游戏卡池机制配置转换手册.md#L938) / [§7.3:1001](docs/主流抽卡游戏卡池机制配置转换手册.md#L1001)，原引 `#L963` 已随 §7 重写漂移，2026-09-30 修正） | ✅ **归本计划**（2026-09-21 裁决）：做**真实建模**，需 S8 卡级管道（子集定向）+ S9 状态可见性（读 `acquired`），方案见 §3.10.4。原记「pool 层过滤」属近似（会让普通抽卡也不出已拥有装备），已按「精确建模原则」否决。**2026-09-29 定位更正**：所涉卡池（精准补给 / 演武精备）**均已下线**：官方公告 API 全量穷举 2759 条（2016-09 ~ 2026-09）确认：精准补给末次 2024-11-06（7.9→8.0 之间**静默替换**为「装备补给」，**官方无下线公告**）、演武精备末次 2025-01-08。故本条定位由「待实现的现行机制」改为「**历史机制的建模能力**」：实现它的价值在**补全保底的历史信息视野**，**S9 的正当性不依赖 G3 是否现行**：其理由是「保底缺了『玩家拥有什么』这一块历史信息」，而非复现当前游戏。手册 §7.1 / §7.3 / §21 三处已同步（2026-09-29） |

> **关键洞察**：G14（战双命运池）是 pity 层「hard 触发条件的动态化」（threshold 每次重置随机 T）：P64 的「条件谓词 → 概率修正」抽象若延伸到 counter 驱动型可统一表达（hard 本身即「counter ≥ threshold → ForceFeatured」特例），记为后续扩展方向。G2（阴阳师神眷）是 milestone 层「累抽奖励动态 threshold」（450/800 按全图鉴状态，2026-08-24 归属修正），非 pity 层。G13 已由 `counter_init=20` 配置即可表达（2026-08-24 双信源确认），非扩展方向。

### 1.5 P82 并入：保底管道执行顺序（2026-09-16 实测完成）

**合并说明**：P82（保底管道顺序接通）于 2026-09-16 并入本计划，P82 文件归档。其结论直接影响 §1.3 的 G5 项与 §3.6 的 priority 设计，**已于 2026-09-18 裁决，见本节末的裁决结论**。

**P82 的问题**：`_resolve_order()`（[pity.py:914](gacha_simulator/core/pity.py#L914)）会计算排序（稀有度 rank → type 顺序 → name），但其结果**只写入 `self._behavior_list`**，而三个调度入口（`get_probabilities` / `before_draw` / `after_draw`）走的是 `get_behaviors_for_pool()` → `spec.pity_names`，后者由 `batch_simulator.py:263-275` 按 **TOML 定义顺序**构造。即排序算了但未接入概率管道，`P30 #11` 的「顺序由定义顺序决定」在代码上仍成立。<!-- REVIEW-R1-FIX: ISSUE-001 -->

**P82 的实测结论（2026-09-16）**：

| 配置场景 | 顺序是否影响结果 |
|---------|----------------|
| soft + soft（同 / 异目标槽位） | 否。概率变换数学可交换（手算 + 95 抽序列对比双重验证） |
| soft + hard | 否。hard 触发时覆盖一切，未触发时无作用 |
| rotating / targeted / hard 的各类组合 | 否 |
| **跨 scope（保 ssr + 保 sr）** | 否。层级保护使低稀有度保底不改变高稀有度保底的可窃取总量 |
| **含 `rotating_cr` 的组合** | **是**。46 组随机扫描中 12 组敏感，最大差异 30/95 抽 |

`rotating_cr` 敏感的根因是它**消费全局 `random`**（`before_draw` 内 `random.random() < cr_base_rate`），顺序改变导致随机流错位，属随机源共享的副作用，非概率语义上的顺序依赖。

> **⚠ 本表的时点（2026-10-06 补注）**：上表是 **2026-09-16 的实测**，其 `soft` 相关行测于**修正 ① 之前**的代码（相对量语义 `amount = β·p(Q)`）。**2026-10-06 修正 ① 落地后，`soft + soft（异 scope）` 由可交换变为不可交换**——详见 §3.1.5.5 的推论表（同 scope 仍是「是」，异 scope 是「否」）与 §3.4.1 的修正说明。本表其余各行（`soft + hard` / rotating·targeted·hard 组合 / 跨 scope）不受该修正影响。**本表的列头是「顺序是否影响结果」，与 §3.1.5.5 的「是否可交换」是同一件事的两种问法**（前者答「否」= 顺序无关 = 可交换，注意与后者答「否」= 不可交换的字面相反）。

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

- **核心改动点**：`PityEngine.get_behaviors_for_pool()`（[pity.py:1187-1197](gacha_simulator/core/pity.py#L1187-L1197)）的输出顺序，三个调度入口共用它，改此处即改管道。<!-- REVIEW-R1-FIX: ISSUE-001 -->
- **实现取向（推荐：独立排序视图）**：`PityEngine.__init__` 在 behavior 全部构造完成后，为每个 pool 预计算排序后的保底名列表（如 `self._pool_order: Dict[str, List[str]]`），`get_behaviors_for_pool()` 消费该视图；`PoolPitySpec.pity_names` **保持 TOML 顺序不动**。
  - 理由：`pity_names` 兼有第二职责——[banner.py:261](gacha_simulator/core/banner.py#L261) 用 `','.join(pity_spec.pity_names)` 生成 `draw_pity_names` 输出串，下游（[process_trace.py:123-125](gacha_simulator/core/process_trace.py#L123-L125)、[streaming.py:174-176](gacha_simulator/core/streaming.py#L174-L176)）以 `split(',')` + set 消费，**语义与顺序无关**，但字面顺序会进 golden 快照。独立视图使输出串保持不变，把行为变更面收窄到「概率管道顺序」一处。
- **排序键**：`(rarity rank, _BTYPE_ORDER, name)`（P55 既定），接线后 `_BTYPE_ORDER` 真正生效；`priority` 插入位置为 rank 之后、type order 之前（§3.6 M3）。
- **行为变更面**：仅「同一池内、书写顺序与排序键不一致」的配置受影响。已实测（P82 §六 + §3.1.5.5）敏感集合**共五类**（**ISSUE-941：原写「两类 + 补第三类」，现按各节实测记录汇总为五类；原记法作废**）。**真相源的登记是分布式的三处**：① §3.1.5.5 的「P82 结论的最终形态」表：第 1 / 2 / 5 类的判据与消除时点；② §3.1.5.5 的「推论表」：第 3 类的依据；③ 本清单本身：第 4 类是**全篇唯一**的实测记录点（§3.1.5.5 无该类承载行）。四处（上述三处 + §六 接线条）须同批更新： <!-- REVIEW-R1-FIX: ISSUE-941 -->
  1. **含 `rotating_cr` 者**：增量本身可交换，但掷骰消费全局 `random`，换序导致随机流错位、样本路径分叉。非代数问题。**注意**：本条与「分布差异」的关系见 §3.1.1 的「**首抽掷骰落点**」段（**2026-10-10 同步**：该段原题「⚠ 首抽无掷骰落点」，其缺口已由 RULING-6B′ 消除、段名随之改，§3.1.1 连带处置第 ④ 项要求的「本清单第 1 类注记同步」即此处）。
  2. **`target_featured=True` 的 soft 与 hard 共存者**：真实概率语义（约束冲突），非随机数错位。**排期已定（2026-10-10，用户授权由主 agent 定）**：**独立先行、排在 M1 之前**（§七 已按此列块）。故本类**是真实的敏感面**：接线当期 7B 尚未落地（其落点是 S4-4，在 M1 内），本类仍可构造，**P82-2 的差异归因表必须含本类**；7B 落地后本类不再可构造，归因证据须在**接线当期**取。原记「『接线早于 M1』是待裁决的前提」作废。**注**：两种排期的**最终交付物相同**（接线与 7B 硬拒都会落地），差别只在 P82-2 的归因表是五类还是四类，此处取五类（更严的一侧）。
  3. **`soft + soft`（异 scope）**：**2026-10-06 修正 ①**（软保底的 `amount` 由相对量改为**绝对百分点**）落地后，该类**由可交换变为不可交换**，判据与实测见 §3.1.5.5 的「推论表」（同 scope 仍是「是」，异 scope 是「否」）。本类原先只在 §3.1.5.5 出现、本节清单缺它，而本清单是 P82-2 的验收依据，缺本类会把该类配置的真实差异误判为回归。
  4. **跨 type 顺序反转且存在 `depends_on` 者**：依赖方的状态键**创建时机**会变（旧顺序在源触发当轮就执行依赖方 `after_draw` 并创建其 `counter` 键；新顺序下该轮依赖方仍未激活、键延后到下次 `before_draw` 才创建）。实测（rotating 源 + hard 依赖，`pity_names` 由 `(source, dependent)` 反转为 `(dependent, source)`）：依赖方 `_active` 最终值不变（均为 True），但 `PityState` 快照的键存在性有差异。该差异只在 `depends_on` 配置中出现，当前 `config.toml` 无此配置。<!-- P64-DEBUG-REG -->
  **补登记（系统性 debug，2026-10-15，实测）：本条的后果被说小了。** 当依赖方带 **`counter_init > 0`** 时，差异从「键存在性」**升级为概率差**：旧顺序在源触发当轮执行依赖方 `after_draw`，其 `CounterTracker.commit` 会把**已有的** `counter_init` **归零**；新顺序跳过该轮 `after_draw`，计数器保持 `counter_init`。**最小复现**：`src = rotating`、`dep = hard(threshold=5, depends_on='src', counter_init=3)`，`pity_names` 由 `(src, dep)` 反转为 `(dep, src)`；实测源在第 28 抽触发，旧顺序下依赖方 counter 当轮归零（draw 28 快照 `{counter: 0}`）、第 33 抽才触发，新顺序下保持 3、**第 30 抽即触发**（12 抽概率差，maxdiff **0.549**）。**边界**：`counter_init = 0` 时两者同为 0（一个写成 0、一个缺键），只有快照键存在性差异，与原文一致。**归因**：P82-1 之前 `get_behaviors_for_pool` 用 `spec.pity_names`（书写顺序），之后用 `_pool_order`（排序键），故执行顺序改变、上述相位差随之改变。**若要根治**：把 `after_draw` 的激活传播改为**两阶段**（先跑完全部 `after_draw`、再统一传播 `_active`），使激活相位与排序键解耦。
  5. **`hard` 与「在 `hard` 输出上非恒等」的算子共存**，当前唯一实例是 **`rotating` / `targeted` 处于 `guaranteed`（或 fate-ready）分支**：**这是裁决 7B 之后剩下的那一条代数型反例**（依据见 §3.1.5.5 的「判据」专段与「逐条验算」表）。`hard` 的输出与输入分布无关，而 `rotating`（guaranteed）的 `r = 1`，在 `hard` 的输出上**非恒等**，故两序不同。实测 `hard(threshold=5)` + `rotating`（第 1 抽中非 UP 的 SSR 置 guaranteed）：**抽 6 起分歧**，`[hard, rot]` = `{ssr: 0, ssr_featured: 1.0}`、`[rot, hard]` = `{ssr: 0.5556, ssr_featured: 0.4444}`；`targeted` 的同名分支与 `rotating` 逐位相同。**本类此前在本清单缺**，而 §3.1.5.5 的终版早已把它写成「当前实例」，两处口径以 §3.1.5.5 为准。 <!-- REVIEW-R1-FIX: ISSUE-703 -->

  其余组合数学可交换，接线不改变其输出。当前 `config.toml` 示例仅一条保底定义，五类均不受影响。**P82-2 的验收口径**：「差异逐一归因到敏感集合」中的敏感集合**即本条的五类清单**。 <!-- REVIEW-R1-FIX: ISSUE-941 -->
- **验证要求（基线固化 + 等价对照）**：接线前用固定种子跑 `config.toml` 与既有测试配置，固化 `CompactResult` 快照；接线后同种子重跑逐字段对比，差异必须逐一归因到上述**五类**，否则视为回归。`tests/core/test_pity_integration.py::TestDependsOnIntegration` 与 `TestMultiPityCoordination` 两组用例是该验证的重点观察对象（前者的 `pity_names=('source', 'dependent')` 接线后会反转，断言仍应通过；后者 `('rot', 'hard90')` 同样反转，概率断言应不变）。
- **排期（2026-10-10 定稿）：独立先行**（同 G16 模式，独立 commit），**排在 M1 之前**。理由：与 P64 主线的重构正交、可独立验收；`_resolve_order`/`_validate_behaviors` 在 P64 §3.2 中的「逻辑零改动」结论不受影响。原记「排期建议……最终以用户裁决为准」改为定稿（用户授权由主 agent 定），与 §七 的「独立先行块」小节一致。

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
- 覆盖 G1（inverse preset）+ G16（独立先行 `reset="never"`）+ G5（调度层**接线** + `priority` 显式排序，2026-09-18 裁决，见 §1.5）+ G3（UP 保护排除已拥有，真实建模，2026-09-21 裁决，见 §3.10.4；**所涉卡池已下线，按历史机制建模能力交付**，2026-09-29 定位更正）
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
| `FlagTracker(scope, judge, hit, miss, flag)`（**`scope` 为 2026-10-10 实施时补入**：原表与 §3.2 / §3.3 / §3.10.3 的四处调用点一律写四参，而本表「语义」列与 M4 表都要求「出 scope」门控、旧 `RotatingBehavior.after_draw` / `did_fire` 亦以 `reward_rarity == scope` 为前提；缺它则「出非 scope 稀有度的 featured 卡」会翻转标记并报 `did_reset=True`，与旧类实测不符，M1 的「与旧类逐场一致」不成立。落点见 S1b-2） | 出 scope 时，judge 命中取 `hit` / 未命中取 `miss`（`"set"` / `"clear"`），写 `flag` 指定的标记键。**四关键字参**，preset 实例：`FlagTracker(judge="featured", hit="clear", miss="set", flag="guaranteed")`（rotating）/ `... hit="set", miss="clear", flag="forced_loss"`（G1 rotating_inverse，§3.3） | RotatingBehavior guaranteed | 由 `flag` 形参指定（`guaranteed` / `forced_loss` 等） |
| `StreakTracker(scope, judge, threshold, base_rate, state_probs, flag='cr_intercepted', guard_flag='guaranteed')`（**`scope` 为 2026-10-10 实施时补入**，理由同 `FlagTracker` 行） | 连续未命中计数，未命中 +1、命中清零（在 `commit`）；**在 `prepare`（`before_draw`、`advance` 之后、Modifier 链之前）掷骰**，判定本抽是否拦截为 100% UP，结果写入 `flag` 指定的标记键。含 `guard_flag` 守卫（抽前该标记已置位时不掷骰）与 `readonly` 早退（两条都**不掷骰**）。**flag 每抽无条件写**（成功置位、失败清位），否则脏 flag 残留会静默抬高拦截率。**与 `FlagTracker` 的先后是契约**（`StreakTracker` 在前），见 §3.2 的 `_preset_rotating_cr`。`threshold` / `base_rate` / `state_probs` 取值 `pdef.cr_counter_threshold` / `cr_base_rate` / `cr_state_probs`。**形参与语义按裁决 6B 扩充**（掷骰自 `InterceptModifier` 移入，见下；**2026-10-10 改判为 6B′**，相位改归 `prepare`，见 §3.1.1 的 CR 掷骰相位段） | RotatingCRBehavior cr_counter + `before_draw` 掷骰分支 | `cr_counter`, `cr_intercepted` | <!-- REVIEW-R1-FIX: RULING-6B --><!-- REVIEW-R1-FIX: RULING-6B-PRIME -->
| `FateTracker(scope, judge, hit, miss, keys)`（**`scope` 为 2026-10-10 实施时补入**，理由同 `FlagTracker` 行；`hit` / `miss` 由 S1 定稿取 `clear` / `accumulate`，键的计数器/标记类别由 `_FATE_KEY_KINDS` 词表给出） | 出 scope 时，命中定轨对 `keys` 集清零/未命中累积。`keys` 即多键集：`fate_points` / `losses` / `guaranteed` / `lost_rotating`（§3.2 targeted 行；`hit` / `miss` 由 S1 定稿，形参名同 `FlagTracker` 口径）。另**读**外部注入的 `selected_card`，见 L4 | TargetedBehavior fate/losses | `fate_points`, `losses`, `guaranteed`, `lost_rotating`（另**读** `selected_card`） |
| `NamespaceTracker(namespace)`（**ISSUE-407 新增**） | **语义为空**：`advance` / `commit` / `did_reset` 全 no-op，不参与计数与概率。唯一作用是**声明一个命名空间**（§3.10.3 的 `X_soft` 载体），使该命名空间在 `PityState` 中存在、可被 `Lifecycle.initialize` 写入 `_active`、可进快照比对 | 旧实现由内层 `SoftStepBehavior(name + '_soft', …)` 经 `CounterBasedBehavior.__init__` 隐式产生（[pity.py:133](gacha_simulator/core/pity.py#L133)） | **无**（不声明任何键） | <!-- REVIEW-R1-FIX: ISSUE-407 --><!-- REVIEW-R1-FIX: ISSUE-002 -->

<!-- REVIEW-FIX-PREV: ISSUE-104 -->
> **签名不一致已被消除（ISSUE-104，2026-09-22）**：原表把 `FlagTracker` 写成 `FlagTracker(judge, inverse)` 两参、`FateTracker` 写成 `FateTracker(judge)` 单参、`CounterTracker` 写成 `(scope, reset_on)` 两参，与 §3.2 / §3.3 / §3.14.2 的 preset 代码**三处三种写法**；且 `FlagTracker` 无 `flag` 形参，无法表达「标记名」（rotating 用 `guaranteed`、G1 用 `forced_loss`），`CounterTracker` 缺 `init`。实施者按原表落笔即与全部 preset 代码不兼容。现按**定稿代码**回写（上表），并明确：`FlagTracker(judge="featured")` 这类单参简写形态**不是**可实施的签名，§3.2 preset 表的对应单元格已同步为定稿形态。

> **G16 自然落位**：`CounterTracker(reset_on="never")` 去掉重置规则即可，无需特殊分支。
> **G13 自然落位**：`CounterTracker(scope=…, reset_on=…, init=20)` + `HardModifier` 内联的 `counter >= 60` 判断首次 40。**阈值属 Modifier 的内联条件、不属 Tracker**——原稿写 `CounterTracker(init=20, threshold=60)`，而 `threshold` 不是 Tracker 形参（§3.2 preset 表；§3.14 条件内联，无独立条件对象。**GATE-check-6，2026-10-09 修正**：原写 `CounterCondition('counter', 60)`，该条件类族已随 §3.14 改判取消）。<!-- REVIEW-FIX-PREV: ISSUE-104 -->
> **G14 自然落位**（后续扩展）：`RandomThresholdTracker(range=(80,100))` 每次重置随机阈值。

**Tracker 协议（强制；`rebind` 为 2026-09-22 补全的公开接口名，ISSUE-029）**：Tracker 的契约由四个方法构成，`Pity`（§3.1.4）按 N1 相位与 M4 语义调用它们。

| 方法 | 语义 |
|------|------|
| `rebind(state, name)` | **P75 纪律**：把本 Tracker 内部的 `Counter` / `Flag` 遥控器重绑到 per-call `state`（纯重定向，不复制旧值）。`Pity._rebind_state` 对其**无条件**调用，故**方法必须存在**；无自身状态键的零件可写空实现，但不得省略 |
| `advance(ctx, state, name, readonly)` | 见下方 N1 相位表 |
| **`prepare(ctx, state, name, readonly)`** | 见下方 N1 相位表。**2026-10-10 新增（第 5 个方法）**，用于「抽前需要读 state 并消费随机源」的零件；与 `advance` / `commit` 同列 |
| `commit(ctx, state, name, skip_reset=False)` | 见下方 N1 相位表 |
| `did_reset(ctx, state, name)` | M4 统一语义（「本次抽卡是否让本保底回到初始状态」） |
| `state_keys() -> tuple[str, ...]` | 见下方「声明键集（ISSUE-501）」段 |

**声明键集（`state_keys()`，ISSUE-501，2026-10-01 补，强制）**：三族（Tracker / Modifier / Lifecycle）一律暴露**只读成员 `state_keys() -> tuple[str, ...]`**，返回该零件会**写入**（Modifier 为读或写）的 `PityState` 键名。它是**不依赖 state 的常量**（由构造形参决定），因此可在构造期直接取用，不需要 `rebind`。

**为什么必须有它**：§3.12.1 的「状态键合法」不变式、§3.12.2 的合法组合判据第 1/2 条（同一键被两个 Tracker 声明 / Modifier 引用不存在的键）、§3.13 的状态层 checker，**四处都以「每个零件声明的状态键集合」为输入**；而三族协议此前只有 `rebind` / `advance` / `commit` / `did_reset` / `apply` / `factor` 等行为成员，**没有任何承载声明集的成员**。缺它则 S10-2 与 S11 无可用比对集，实施者只能为三族各临场自定一次接口形态，且 §六 的「三类判据各一条负例在构造期抛 `ConfigError`」这一验收不可实现。声明集的**汇总点只有一个**：`Pity.__init__`（§3.1.4 骨架的 `self._declared_keys`），S10-2 与 S11 一律从 `Pity` 取，不各自收集。

**各族返回值**（只列定稿的四个 Tracker；`NamespaceTracker` 返回 `()`）：

| 零件 | `state_keys()` |
|------|---------------|
| `CounterTracker` | `('counter',)` |
| `FlagTracker` | `(flag,)`——键名由 `flag` 形参给出 |
| `StreakTracker` | `('cr_counter', flag)`——裁决 6B 后它多写一个拦截标记键（`flag` 形参，默认 `'cr_intercepted'`），须一并声明 |
| `FateTracker` | `keys` 形参（`('fate_points', 'losses', 'guaranteed', 'lost_rotating')`）——**注意它只声明「写」的键**，其**读**的 `selected_card` 不由它声明、也不进本集合（写入者是策略层 `NonDrawAction`，见下方 L4 例外 2；§3.12.2 的判据须为该键留白名单，否则合法配置会被误判为「引用不存在的键」） |
| Modifier 族 | 默认 `()`（不碰状态者不覆写）；读/写状态的 Modifier 返回其涉及的键 |
| Lifecycle 族 | `('triggers',)`（**仅 `max_triggers > 0` 时**；其余返回 `()`，见 §3.1.3 的计数载体段） |

<!-- REVIEW-FIX-PREV: ISSUE-029 -->
**为什么必须显式定义（ISSUE-029）**：现有代码的对应物是**私有**方法 `PityBehavior._rebind_state`（[pity.py:90](gacha_simulator/core/pity.py#L90)、[pity.py:152](gacha_simulator/core/pity.py#L152)），由 `PityEngine._rebind_state` 经 `hasattr(bh, '_rebind_state')` **守卫**调用（[pity.py:1246](gacha_simulator/core/pity.py#L1246) 起）。新架构用的是**无守卫的公开名 `rebind`**，调用点也从「每轮模拟首调度」变为「每次抽卡的调度入口」。故不得靠「旧代码里有就先当它存在」推断——协议不写、实现不加，首次抽卡即 `AttributeError`，等价于全部保底不可用。<!-- REVIEW-R1-FIX: ISSUE-002 -->

<!-- REVIEW-R1-FIX: ISSUE-407 -->
**零件的命名空间声明面（ISSUE-407，2026-09-30 独立复核补，强制）**：**Tracker / Modifier / Lifecycle 三族一律暴露 `namespace` 属性**（`Optional[str]`，默认 `None`），它是 §3.10.3「两级 view 分配」的**唯一输入**：

| 取值 | 语义 | `Pity` 传的 view |
|------|------|-----------------|
| `None`（默认） | 不做命名空间切换 | **默认 view** = `StateView(state, self._name)`；soft 族的软计数落在此（对齐旧 mixin 的 `X.counter`） |
| `'<ns>'` | 本零件声明独立命名空间 | `StateView(state, part.namespace)`（§3.10.3 定稿；`_soft` 族用它产出 `X_soft` 命名空间） |

**为什么必须写进三张契约表**（原稿只在 §3.10.3 的定稿段写「`part.namespace`」，三族协议表与四个 Tracker 的签名表都没有该成员，§3.2 的 `_soft` preset 代码里也没有任何载体零件）：§3.10.3 的「命名空间载体 Tracker」与 §六 的两条断言（`_soft` 族命名空间保留 / view 命名空间分配）会**没有任何实现落点**，实施者只能临场决定；而 `X_soft` 命名空间在旧实现里确有内容（[pity.py:133](gacha_simulator/core/pity.py#L133) 写入的 `_active: True`），它是 S1–S5 快照「逐场一致」的比对对象之一。**载体零件的定稿形态**：新增 `NamespaceTracker(namespace)`——语义为空（`advance` / `commit` / `did_reset` 均 no-op）、不参与计数与概率，只用于声明命名空间；`Pity` 收集方式与 `Lifecycle.initialize` 的写入推广见 §3.10.3。<!-- REVIEW-R1-FIX: ISSUE-002 -->

**计数器相位（N1，强制，2026-09-16 定稿）**

问题：旧 `CounterBasedBehavior.before_draw`（[pity.py:179-187](gacha_simulator/core/pity.py#L179-L187)）与 `SoftPityMixin.before_draw`（[pity.py:529-533](gacha_simulator/core/pity.py#L529-L533)）都是**先自增、再用自增后的值算概率**，实测 `hard(threshold=90)` 首次 100% 出现在**第 90 抽**。若把递增放到 `after_draw`，第 90 抽读到 89、首次触发落到第 91 抽。总次数两者相同，差的是**读相位**，故「每抽加一次」的表述覆盖不了它。

**方案（计数型 Tracker 分两段，非计数型只在 after 侧）**。「计数型」的界定必须**显式列出**：`CounterTracker.counter` 属计数型（旧 `before_draw` 推进）；`StreakTracker.cr_counter` **不属**（旧实现只在 `after_draw` 累加与清零，[pity.py:590-600](gacha_simulator/core/pity.py#L590-L600)），若按「计数器」字面把它划入计数型，`advance` 会每抽多推进一次。

| 方法 | 调用点 | 计数型 Tracker | 非计数型 Tracker |
|------|-------|---------------|-----------------|
| `advance(ctx, state, name, readonly)` | `Pity.before_draw` 首段 | `readonly=True` 只读不写；否则 `counter += 1` | no-op |
| **`prepare(ctx, state, name, readonly)`** | **`Pity.before_draw`，`advance` 之后、本保底 Modifier 链之前** | no-op | **`StreakTracker` 在此掷骰**（2026-10-10）；其余非计数型 no-op |
| `commit(ctx, state, name)` | `Pity.after_draw` | 命中时 `counter ← 0` | 置位/清位/累积 |

与旧实现结构同构（旧代码本就是 before 侧 `incr()`、after 侧 `reset()`），故在未触发下述例外时，`state` 中的计数值与旧实现逐位相同，「状态快照逐场一致」这条验收无需适配。

**例外（`deactivate_on_early_hit`，2026-09-16 补）**：旧 `CounterBasedBehavior.after_draw`（[pity.py:194-203](gacha_simulator/core/pity.py#L194-L203)）在 `_on_reset(ctx)` 返回 True 时**提前 return，跳过 `_counter().reset()`**；而 `SoftStepBehavior._on_reset` / `HardPityBehavior._on_reset`（[pity.py:327-335](gacha_simulator/core/pity.py#L327-L335)、[pity.py:403-411](gacha_simulator/core/pity.py#L403-L411)）恰在 `deactivate_on_early_hit=True` 时清 `_active` 并返回 True。实测：`hard(threshold=90, deactivate_on_early_hit=True)` 在第 5 抽命中后 counter 仍为 5（未重置），无该配置时归 0（概率流不受影响，差异只落在状态快照与 `get_counter()`）。故 `commit` 的语义须是「**Lifecycle 退役动作与重置同序判定，退役则跳过重置**」，不能写成无条件的「命中即归零」。<!-- REVIEW-R1-FIX: ISSUE-002 -->

**已排除的替代方案**：把 `counter_init` 与重置值都改成 1，使 after 侧递增也能对齐读数。数学上可对齐，但 `state` 中的值会整体偏移 1（抽完第 1 抽后 counter 为 2，而旧实现为 1），连带快照对比、`get_counter()` 查询、GUI 展示、`counter_init` 的用户含义（G13 的 `counter_init=20` 表示「已垫 20 抽」）全部平移，把一处相位约定扩散成全局数字偏移。

**不选「读时虚拟 +1」**：那会让「Modifier 读到的值」与「state 中的值」相差 1，任何读 counter 的下游代码都要区分用途，是长期负债。

**测试断言**：`hard(threshold=90)` 首次 100% 出现在第 90 抽；`soft` 的 boost 起始抽数；`readonly=True` 查询不推进计数。

**CR 掷骰的相位（裁决 6B → 2026-10-10 改判 6B′，强制）**：`rotating_cr` 的随机拦截**归 `StreakTracker.prepare`**（即 `Pity.before_draw`、`advance` 之后、Modifier 链之前），与旧 `RotatingCRBehavior.before_draw` 同相位。**改判理由**：6B 把掷骰放在 `commit` 后，与同一 `commit` 内的 `cr_counter` 更新条件（旧 `was_guaranteed`，取**抽前**的 `guaranteed`）**读点冲突**——一个读点无法同时给出「本抽是否需掷骰」（要抽前的 `g_N`）与「本抽是否被拦截」（要抽后的值）。实测（脚本化 RNG，15 抽对照，非仓库产物）：按 §3.2 的 tracker 顺序 `[FlagTracker, StreakTracker]` 落地时，`cr_counter` 轨迹恒为 `0,0,0,…,0`（旧实为 `1,1,2,2,2,3,3,4,4,4,4,5,5,5,6`），**CR 计数器整体失效**；仅把顺序反转为 `[StreakTracker, FlagTracker]` 能让计数器对上，但守卫仍取错值。回退到抽前相位后，两个判断重新共用同一个 `g_N`，读点冲突消失。

**等价性依据（五条，逐条对照旧 `RotatingCRBehavior.before_draw`，[pity.py:569-583](gacha_simulator/core/pity.py#L569-L583)）**：
1. **读到的计数同源**：旧码在抽 N 的 `before_draw` 读 `cr_counter`；新码在同一抽的 `prepare` 读同一值（`advance` 只动 `CounterTracker` 的 `counter`，不碰 `cr_counter`）。
2. **`guaranteed` 短路同源**：旧码首行 `if self._guaranteed.is_set(): return super().before_draw(...)` 即不掷骰；新码在 `prepare` 头部以 `guard_flag` 判同一标记（此时 FlagTracker 尚未在本抽的 `commit` 里翻转，读到的正是抽前值）。
3. **`readonly` 同源**：旧码查询路径不掷；新码 `prepare` 收 `readonly` 并在此分支早退。**这一条 6B 不需要（查询不调 `after_draw`），改判后必须显式实现**——策略层每次概率查询都会经 `StrategyContext.get_pity_probabilities` → `PityEngine.before_draw` 走到 `prepare`，漏掉即每次查询都掷骰。
4. **四条「不消耗随机数」的路径逐条复刻**（`state_prob >= 1.0` 的确定性触发、空 `state_probs`、下标裁剪、`cr_base_rate == 0`）——见 §3.1.2 的「CR 随机数消耗协议（H4）」。
5. **flag 每抽无条件写**（成功置位、**失败清位**）。旧码只在命中分支 `return`，照搬会让「上次掷中」的 flag 残留到下一抽，Modifier 因而误拦截、拦截率被静默抬高。

**Tracker 顺序是契约（强制）**：`StreakTracker` **必须**排在 `FlagTracker` **之前**。掷骰移出 `commit` 后，这个顺序不再有「同 commit 内读点竞争」的副作用，而 `state_keys()` 等其余量均顺序无关。§3.2 的 `_preset_rotating_cr` 代码块写死该顺序。

**首抽掷骰落点（ISSUE-702，2026-10-10 由 6B′ 消除）**：6B 形状下掷骰落在 `commit` 内，而「抽 0 的 commit」不存在，故**首抽恒无拦截判定**——旧码首抽读到 `Counter` 缺键的默认值 `0`（`idx = min(cr_counter.value(), len(cr_state_probs) - 1)` 得 `idx = 0`）后**照样掷骰**，两者相差**一枚随机数**，使全程样本路径整体移位。**该缺口已由 6B′（prepare 相位）消除**：抽 1 的 `before_draw` 即走到 `prepare`，与旧码同相位、同条件、同消费次数。

> **量级校正（2026-10-10，实测）**：原稿写「旧码首抽有**两次**拦截机会」（`cr_base_rate > 0 and random.random() < cr_base_rate`，以及 `idx = 0` 时的 `cr_state_probs[0]` 分支）。按真实机制配置（`cr_base_rate = 0.018`、`cr_state_probs = [0.0, 0.0, 0.75, 1.0]`），首抽 `idx = 0`、`state_prob = 0.0`，**第二处机会的概率为 0 且不消耗随机数**。故首抽的**分布差**只有 1.8e-4 量级，真正致命的是那一枚缺失的随机数导致的**样本路径整体移位**。归因据此写准。

**连带处置（6B′ 一并完成）**：① §六 差异归因清单的 (c) 项**删除**；② `rotating_cr` / `rotating_cr_soft` **回归**「与旧类逐场一致」批次（S5b / S8-6 的断言按逐场一致判）；③ §五 风险表「CR 随机数消耗不齐」行**结项**；④ §1.5 敏感类 1 与「自动化审查阻塞项」的待裁决枚举第 ① 组注记同步（该组闭合）。


**did_fire 统一语义（M4，强制，2026-09-16 裁决）**：`Pity.did_fire` 供 `PityEngine.after_draw` 的 depends_on 激活传播使用（[pity.py:1340](gacha_simulator/core/pity.py#L1340)）。<!-- REVIEW-R1-FIX: ISSUE-402 --> **P64 起它有两个调用点**：上游那一处，以及**本保底自身的 `Pity.after_draw`**（把 `fired` 传给 `Lifecycle.should_deactivate`，§3.1.4 骨架）——两者共用同一个「本次抽卡是否让本保底回到初始状态」判据，不得各写一套（原稿写「全代码唯一调用点」，已按新增调用点更正）。**统一语义 = 「本次抽卡是否让本保底回到初始状态」**，由各 Tracker 的 `did_reset(ctx, state, name)` 提供，`Pity.did_fire = any(tr.did_reset(...))`。

现状并不一致（**六类，其中三类方向相反**），`did_reset` 需把 rotating/targeted 收严、并**显式接受三个 `_soft` 复合类型的放宽**：

| 旧类 | 现状 did_fire | 统一后 `did_reset` | 变化 |
|------|--------------|-------------------|------|
| counter 驱动（soft/hard） | `_should_reset(ctx)`，按 `reset` 配置（[pity.py:205-208](gacha_simulator/core/pity.py#L205-L208)） | 同左（`scope`→出该稀有度；`featured`→出 featured，**无 scope 门控**） | 无 | <!-- REVIEW-R1-FIX: ISSUE-001 -->
| rotating | `ctx.draw.is_featured`（[pity.py:500-503](gacha_simulator/core/pity.py#L500-L503)） | 出 scope ∧ is_featured | **加 scope 门控（收严）** |
| targeted | `_is_hit(ctx)`，即 `reward_id == selected`（[pity.py:699-701](gacha_simulator/core/pity.py#L699-L701)） | 出 scope ∧ reward_id == selected | **加 scope 门控（收严）** |
| **`rotating_soft`** | 经 MRO 落到 `RotatingBehavior.did_fire` = **「出 scope ∧ is_featured」**（`SoftPityMixin` **不定义** `did_fire`，[pity.py:507-541](gacha_simulator/core/pity.py#L507-L541) 只有 `_init_soft_pity` / `before_draw` / `after_draw` / `_rebind_state`） | **「出 scope」**——该族 preset 的 CounterTracker 是「触发稀有度重置抽数 counter」，**hit/miss 两分支都 ResetCounter**（§3.2 preset 表，对齐 [pity.py:534-537](gacha_simulator/core/pity.py#L534-L537)），故 `did_reset = (reward_rarity == scope)` | **放宽（激活更宽）** | <!-- REVIEW-R1-FIX: ISSUE-002 -->
| **`rotating_cr_soft`** | 同上（`RotatingCRBehavior` 为 `RotatingBehavior` 子类且无覆写） | **「出 scope」**（同 rotating_soft） | **放宽（激活更宽）** |
| **`targeted_soft`** | 经 MRO 落到 `TargetedBehavior.did_fire` = **「出 scope ∧ 命中定轨」** | **「出 scope」**（同族 CounterTracker 的 reset 条件） | **放宽（激活更宽）** |

<!-- REVIEW-FIX-PREV: ISSUE-102 -->
> **为何三个 `_soft` 复合类型会放宽（ISSUE-102，2026-09-22 补）**：骨架的 `Pity.did_fire = any(tr.did_reset(...))` 取**任一** Tracker 的重置，而这三个类型的 preset 里同时有「事件驱动 Tracker（命中才翻转）+ 触发稀有度 counter Tracker（出 scope 即重置）」。旧实现只有前者参与 `did_fire`（后者在 mixin 里，且 mixin 不定义 `did_fire`），新实现多算了后者。**后果**：`depends_on` 依赖方在「出 scope 但未命中 UP / 未命中定轨」时被**提前激活**——方向与本表上方三行的收严相反。
>
> **覆盖缺口（修复前）**：本表的 M4 三行、§六 的「三类的 `did_fire`」断言、§七 S5 的「M4 did_fire 三类语义」三处**均未包含**这三个类型，而 §3.1.3 附近的等价性排除条款（「事件驱动型 + `depends_on` 须显式排除」）又把它们挡在等价性测试之外——放宽既不被测试捕获、也未登记为差异。**三处已同步补入**。
>
> **裁定（原为 ⚠ 待人工裁决，2026-09-22 第八轮定稿，ISSUE-GATE-risk-mitigation）**：可选方案本是让该族 CounterTracker 的 `did_reset` 只认「出 scope ∧ 命中」，把「触发稀有度即重置 counter」（N1 相位，决定 counter 何时归零）与「本次是否回到初始状态」（M4，决定 `depends_on` 传播）**分离**为两个语义。**裁定：不采纳 hit 门控**，该族 `did_reset` 一律按「出 scope」。理由：该族 CounterTracker 的重置条件本就与旧 `CounterBasedBehavior.after_draw` 的命中 / 未命中两分支同源，人为加门控会让「同一个 counter 的归零条件」与「本次是否回到初始状态」出现两套口径，反而引入新的静默不一致；放宽方向已按 §3.1.1 M4 表六行、§六 断言、§七 S5c 三处登记，并写入 §五 风险行。**「既不登记差异、又不加门控」的中间态仍禁止**。<!-- REVIEW-FIX-PREV: ISSUE-GATE-risk-mitigation -->

> **2026-09-18 注**：上表「现状 did_fire」列记录的是 2026-09-16 统一**之前**的行为，所引行号已随该次修改指向统一**之后**的代码（其中 rotating/targeted 两行现已含 scope 门控）。该列仅作历史对照，勿据以判断当前实现。

**理由**：现状的 rotating/targeted 在「出非 scope 稀有度的 UP」时 `did_fire` 为真，但其状态并未翻转（`after_draw` 的 scope 门控把它们挡在外面），`depends_on` 依赖方因此被提前激活。统一后 `did_fire` 与 `after_draw` 里的重置分支**严格同条件**。

**影响面（行为变更，分两类，方向相反——ISSUE-102 更正）**：

- **收严类**（counter 驱动 / rotating / targeted）：激活只会更严格、不会更宽。现有 `config.toml` 无 `depends_on`；`tests/core/test_pity_integration.py` 的被依赖方为 rotating、抽到的是 SSR featured，两种语义下同为 True。
- **放宽类**（`rotating_soft` / `rotating_cr_soft` / `targeted_soft`）：出 scope 但未命中时依赖方被**提前激活**，与上一类方向相反。**修复前本行原写「激活只会更严格、不会更宽」，对这三个类型不成立**——原表述只覆盖到表中前三行，已按六行重述。该三类**不在等价性范围内**（§3.1.3 的排除条款「事件驱动型 + `depends_on`」已覆盖；且三个 `_soft` 类型本身即事件驱动型），须按「行为变更」单独验收并登记差异归因。

**✅ 已于 2026-09-16 独立落地**（早于 P64 主线）：`RotatingBehavior.did_fire` 与 `TargetedBehavior.did_fire` 各加 scope 门控，`RotatingCRBehavior` 的冗余覆写删除。验证方式为「用改动前的 `pity.py` 跑新增测试」，`TestDidFireUnified` 5 例中 3 例失败（正是测 scope 门控的 3 例），确认测试有效；落地后全量 `pytest` 1573 passed，确认无隐藏依赖。P64 实施时应按此语义写 `did_reset`，勿回退。

**三点须显式声明（2026-09-16 补）**：

1. **`never` 行是新增后的语义，不是现状**：现有 `_should_reset` **没有** `never` 分支，恒 False 只是「稀有度字符串永不等于 `'never'`」的偶然结果。该分支由 §3.8 的 G16 独立先行新增。
2. **`featured` 的不对称是有意保留**：counter 驱动型的 `featured` 分支只看 `is_featured`、无 scope 门控（[pity.py:206-207](gacha_simulator/core/pity.py#L206-L207)），与 rotating/targeted 统一后带 scope 门控的语义不同。它属 `reset` 配置的既有语义，不在本次统一范围内；但须写明，否则「did_fire 统一」会被误读为三类完全同构。<!-- REVIEW-R1-FIX: ISSUE-002 -->
3. **`reset` 取值无白名单，未知值静默永不重置（原记「P64 范围外」；**2026-10-09 裁决归本计划，由 G16-1 消除**）**：`create_behavior` 仅在 `pdef.reset` 为 truthy 时透传该参数（[pity.py:881-882](gacha_simulator/core/pity.py#L881-L882)，故空串回退 `scope`）；一旦传入非空值，`_should_reset` 便对其做 `reward_rarity == reset` 比较（[pity.py:205-212](gacha_simulator/core/pity.py#L205-L212)），故任何既非 `'featured'` 又不等于稀有度名的值（如 legacy 值 `'featured_ssr'`）恒 False（永不重置）。**2026-09-18 更新**：原描述的触达路径已随 P81 B11 消失——`_migrate_legacy_pity`（旧 TOML 自动迁移）整函数删除，改为 `_check_pity_format()` 对旧格式显式抛 `ConfigError`（[config_toml.py:392-437](gacha_simulator/core/config_toml.py#L392-L437)）；`tests/test_config_toml.py` 中守护该值的 `TestMigrateLegacyPity`/`test_reset_preserved` 亦被 `TestRejectLegacyPityFormat` 整类替换。**缺陷本体（当时）**——新格式 TOML 的 `reset` 无取值白名单（[config_toml.py:770](gacha_simulator/core/config_toml.py#L770)<!-- REVIEW-R1-FIX: ISSUE-929 --> 即当时的直接透传点），手写 `reset = "featured_ssr"` 恒 False。已独立登记为保底系统 [03-审计.md](docs/01-活跃/subsystems/保底系统/03-审计.md) 异常 6（**2026-10-09 起状态为「已裁决，待 G16-1 关闭」**；原记「状态：待裁决」）。**2026-10-01 更新（ISSUE-928）**：该白名单已并入 **G16-1** 的施工面（`_build_pity` 对 `reset` 增取值白名单，空串 / `featured` / 稀有度名 / `never`，未知值抛 `ConfigError`），本条处置状态由「P64 范围外」改为**待 G16-1 消除**；G16-1 落地后 `03-审计.md` 异常 6 可置为已关闭。**✅ 2026-10-10 已消除（G16-1 落地）**：白名单落在 `_build_pity`（[config_toml.py:689-708](gacha_simulator/core/config_toml.py#L689-L708)，取值集合由模块级 `legal_reset_values()`（[config_toml.py:612-639](gacha_simulator/core/config_toml.py#L612-L639)）给出，`reset` 侧另有大小写归一），`_should_reset` 同批新增 `never` 分支（[pity.py:205-212](gacha_simulator/core/pity.py#L205-L212)）；[03-审计.md](docs/01-活跃/subsystems/保底系统/03-审计.md) 异常 6 随该块**关闭**（这是本条此前缺的落点——§七 G16-2 的目标文件只含三个测试文件与手册，不含 03-审计.md，故关闭动作归于 G16-1）。**✅ 2026-10-09 用户裁决：并入 G16-1**。备选路径（判为 P64 范围外，删除 G16-1 / §3.8 / §四 中「config_toml 的 reset 枚举」这一无落点的措辞，并保留本缺口登记、不改代码）**已否决**。理由：白名单与 G16 的 `never` 分支落在同一函数、同一 commit，不做则「永不重置」与拼写错误（如 `'nevr'`）的行为不可区分；且 `scope` 已有同层同形态的白名单先例，非引入新范式。**本裁决不向其他块并入额外工作**，G16-1 的施工面照原样。**连带**：`config_panel.py:6544-6547` 的 GUI 兜底条目改写（AUDIT-BREAK-1）须与之同一 commit，见 §3.8。<!-- REVIEW-R1-FIX: ISSUE-928 --><!-- REVIEW-R1-FIX: ISSUE-005 --> <!-- REVIEW-R1-FIX: ISSUE-951 -->

**键集语义（L4，等价性前提）**：Tracker 声明的键**仅当初始值为 truthy 时才预建 state 键**（`if init: set()`），与旧 `_build_pity_state_init`（[pity.py:985-1021](gacha_simulator/core/pity.py#L985-L1021)）在 `guaranteed_init=False`、`counter_init=0`、`fate_points_init=0` 时不预建键的行为一致。<!-- REVIEW-R1-FIX: ISSUE-002 -->

**两个例外（实现不得套用 truthy 规则）**：

1. `selected_card` 是**无条件注入**（同函数内 `state.set(pdef.name, "selected_card", sc)`，`sc` 为 None 也写），targeted 家族的初始快照里必然有该键。若新实现按 truthy 规则处理，`to_dict()` 比对会少该键。
2. `selected_card` 的**写入者不是 Tracker**，而是策略层的 `NonDrawAction`（[gacha_service.py:292](gacha_simulator/service/gacha_service.py#L292)、[gacha_service.py:294](gacha_simulator/service/gacha_service.py#L294)），`FateTracker` 只读它。故 Tracker 允许读「不由自己声明的键」，`selected_card` 的初始化路径独立于 Tracker 声明。

#### 3.1.2 Modifier（修正器）—— `(State, BaseDistribution) -> Distribution`

> **2026-09-21 修订**：本表已由 **§3.14** 修订（**条件外置**：触发条件从各 Modifier 内部提出为独立的 Condition 对象，效果实现不变）。本表保留作历史形态与术语索引，实施以 §3.14 为准。
>
> ~~**S2 与 S12 的先后（ISSUE-101 补）**~~（**2026-10-06 随 §3.14 改判删除**）：S12 已整块取消，条件自始内联。原内容：**S2 按本表形态实现**（触发条件写在 Modifier 内部），**S12 随即外置**为 §3.14.2 的 `ConditionalModifier` 形态——S12 已前移进 M1、排在 S2 之后、S4 之前（§七）。故本表不是「永不实施的死稿」，而是 **M1 内 S2 阶段的有效实现形态**；S12 之后以 §3.14 为准。S4 的 preset 工厂与 S5 的等价性测试一律消费**外置后**的形态（§3.2 / §3.3 / §3.14.2 的代码即该形态）。
>
> **Modifier 方法名定稿（ISSUE-GATE-dependency-order，2026-09-22；2026-10-08 由 `factor` 改为 `delta`，**2026-10-09 再由 `delta` 改为 `compute_delta`**，见 §3.9.2 的命名段）**：M1（S2 起至 S7）期间的 Modifier 方法名一律为 **`apply(ctx, view, dist, readonly) -> 分布`**（骨架 §3.1.4 按此调用）；**`compute_delta(view, dist, ctx) -> 增量向量` 自 S8 引入**（§3.9.2 定稿；**2026-10-08 用户裁决：签名由 `apply` 的四参收为三参，`readonly` 随「Modifier 是 pure 函数」一并废除**），此后骨架改调 `compute_delta`、`apply` 保留为默认实现（承载处是 **`Modifier` 基类**的默认实现 `_apply_delta(dist, self.compute_delta(...) or {})`，见 §3.14.3）。全篇两处（本表 / §3.1.4 骨架）以本条统一，见 §3.9.2 的「与 §3.1.4 骨架的关系」段。**GATE-FAIL-6-测试策略（2026-10-09 修正）**：原写「`ConditionalModifier` 也实现 `apply` 并转发到内层」，并把统一面记为「全篇三处（本表 / §3.1.4 骨架 / §3.14.2 包装器）……见 §3.14.2 的 `apply` 转发实现」；`ConditionalModifier` 与该包装器已随 2026-10-06 的 §3.14 改判取消（§3.14.2 现为「取消后的形态」、无转发实现，`apply` 的承载处是 §3.14.3 的基类默认实现）。<!-- REVIEW-R1-FIX: GATE-FAIL-6-测试策略 -->

Modifier 是 pure 函数（裁决 6B 后**无例外**：原先唯一消费 RNG 的 `InterceptModifier` 已并入 Tracker，见下；**2026-10-10 改判 6B′**，该「无例外」结论不变，仅掷骰相位改归 `prepare`）：给定当前状态和基础分布，返回修正后分布。**实现形态为增量向量**（§3.1.5.1）：每个 Modifier 产出一个增量向量 δ，链式应用即逐元素相加再归一化。「列表顺序」因此退化为**增量求值的先后**，不再是可交换性的来源（可交换性由 §3.1.5.5 的判据决定）。语义上全部复用 `_redistribute_scope` 的「scope 内重分配」。

| Modifier | 语义 | 对应现有 | 触发条件 |
|----------|------|---------|---------|
| `Modifier.compute_delta(view, dist, ctx)` | **唯一接口**：返回增量向量 `{card_id: δ}`，未列出的卡 `δ = 0`，`None` 表示恒等。框架统一归一化 | 见下方「七个机制」 | 由各机制自己的 `compute_delta()` 开头判定（条件内联） |

**`ctx` 的字段（2026-10-06 定稿；2026-10-08 增 `base_probabilities`）**：

| 字段 | 内容 |
|------|------|
| `scope_cards` | `{稀有度: tuple[card_id]}`，该稀有度的全部卡 |
| `featured_cards` | `{稀有度: tuple[card_id]}`，该稀有度内的 UP 卡（**只对有 UP 卡的稀有度建键**） |
| `rarity_rank` | `{稀有度: int}`，**0 = 最高** |
| `base_probabilities` | `{card_id: float}`，池子声明的基础权重（即 `DrawInfo.base_probabilities`，S8 后为卡级）。**`shape = 'declared'` 的 `w` 来源**；它归一化后就是初始分布（`PityContext.current` 的初值），故「按声明形状」与「按初始形状」只在 `current` 已被改动后才分岔 |
| `sim` | `SimView`，模拟级状态的只读视图（`owns(card_id)`）。**非 Optional，永远填充**（§3.10.2） |

| `invariants` | `InvariantChecker` 或 `None`（**S8-6 新增，非抽卡静态事实**）：增量层判据的载体。**只由 `PityEngine.before_draw` 写**（`get_probabilities` 不写），生产默认 `None`（零开销）。**边界（S8-6 审查登记，强制）**：属**未登记的新耦合面**，叶子层只能注 `Any`（§3.1.6 的「仅依赖标准库」），且**约定零件不得消费它**（当前 `pity_tracker.py` / `pity_modifier.py` 零读取） |

> **`ctx` 保留扩展能力（强制）**：上表是**当前机制需要的全部**（五字段为抽卡静态事实，另 `readonly` / `invariants` 为编排层协作字段），但 `ctx` 的类型是开放的。新机制若需要新的静态事实（池子类型、banner 开放时刻、已拥有集合等），**加字段，不改签名**。`compute_delta(view, dist, ctx)` 三参数是定稿，**不得再增形参**（G3 的 `owns` 即按此走 `ctx.sim`，见 §3.10.2）。

**七个机制形态（六个类；`HardModifier` 按 `target_featured` 分两行，每类只写一个 `compute_delta()`，方法体里只算五样）**：

| 类 | 条件 | A（加组） | Q（减组） | 转移量 | A 侧形状 |
|----|------|----------|----------|--------|---------|
| `HardModifier`（`target_featured=false`） | `counter >= τ` | `scope_cards[scope]` | 更低稀有度 | `p(Q)` | `current` |
| `HardModifier`（`target_featured=true`） | 同上 | `featured_cards[scope]` | 更低稀有度 ∪ `scope\featured` | `p(Q)` | `declared` |
| `SoftModifier` | `boost > 0` | `scope_cards[scope]` | 更低稀有度 | `boost/100` | `current` |
| `RotatingModifier` | `guaranteed` | `featured_cards[scope]` | `scope\featured` | `p(Q)` | `current` |
| `NonFeaturedModifier`（G1） | `forced_loss` | `scope\featured` | `featured_cards[scope]` | `p(Q)` | `declared` |
| `SelectedModifier`（targeted） | `guaranteed ∨ fate_ready` | `(selected,)` | `scope\selected` | `p(Q)` | `declared` |
| `NotOwnedModifier`（G3） | `counter >= τ` | `featured_cards[scope]` 中未拥有者 | 更低稀有度 ∪ `scope\A` | `p(Q)` | **`declared`**（**F7 裁决落地，2026-10-14**，见本表下方的裁决记录） |

**五样都是 `compute_delta()` 方法体内的局部量**，不是构造形参、不进接口。「更低稀有度」= `rarity_rank` 中 `rank > rank(scope)` 的稀有度下的全部卡；「`scope\X`」= scope 卡集去掉 X。

> **G3 的 Q 含已拥有的 UP（2026-10-07 用户裁决）**：G3 的 A = featured 中**未拥有**者，故 `scope\A` = (featured 中已拥有者) ∪ `scope\featured`。已拥有的 UP 落在 Q 内、本抽被搬空，从而「50 抽必出**未获得的** UP」成立。若按 `scope\featured`（不含已拥有者）取 Q，已拥有的 UP 保留原概率、本抽仍可被抽到，与手册「已获得的装备从 UP 组中排除」冲突。

**表里只有三列变出花样**：A/Q 的取法（5 种）、转移量（2 种：`p(Q)` 与 `boost/100`）、A 侧形状（2 种，见下）。条件各不相同，但与这三列无关。

> **A 侧形状（2026-10-08 用户裁决）**：`current` = A 内按当前比例 `p_c/p(A)` 分配增量；`declared` = A 内按声明权重 `w_c/w(A)` 分配（`w` 由 `ctx.base_probabilities` 传入，见 §3.9.4 的 `weights` 形参）。**分发依据**（三案推演 §8.4 的穷举）：**可能遇到 `p(A) = 0` 的机制取 `declared`**（`HardModifier(target_featured=true)` / `NonFeaturedModifier` / `SelectedModifier`，它们的 A 是 featured 的真子集，会被同 scope 的 counter 驱动算子清空），**其余取 `current`**（`soft` 只加总量不动形状，其余机制的 A 不会整组归零）。`declared` 在 `p(A) = 0` 时仍可分配，这是它唯一的用武之地；`w(A) = 0`（池子声明该组不可获得）时它返回 `None`，与 `current` 同。**Q 侧形状不可指定，恒为当前形状**（否则在 `p_c → 0` 时产出负概率）。

<!-- P64-S8-CLOSURE -->
> **`NotOwnedModifier`（G3）的 A 侧形状在计划内部不自洽（S8 收口登记，2026-10-14，待 S9-3 裁决）**：上表的「A 侧形状」列给它 **`current`**，而同节上方「A 侧形状（2026-10-08 用户裁决）」段的**分发依据**写「**可能遇到 `p(A) = 0` 的机制取 `declared`**（`HardModifier(target_featured=true)` / `NonFeaturedModifier` / `SelectedModifier`，它们的 A 是 featured 的真子集，会被同 scope 的 counter 驱动算子清空）」。G3 的 A = featured 中**未拥有**者，**正是 featured 的真子集**，按该依据应取 `declared`；M1 交付的形态也正是 `declared` 一侧，S8 按表改为 `current`。**已于 S9-3 接线前裁决（2026-10-14，主 agent）**：**取 `declared`**，上表该格已随之改为 `declared`。三条理由：① 本段的**分发依据**（「可能遇到 `p(A) = 0` 的机制取 `declared`（…它们的 A 是 featured 的真子集，会被同 scope 的 counter 驱动算子清空）…`declared` 在 `p(A) = 0` 时仍可分配，这是它唯一的用武之地」）**正指向 G3**，故表内该格原与本段的推导依据冲突，冲突时以依据为准；② **语义**：G3 的意图是「τ 抽**必出**未获得的 UP」，取 `current` 时该保证恰在被前序算子清空目标组的情形下**静默失效**（`transfer_linear` 返 `None`）；③ **M1 交付的形态本就是 `declared`**（S8 审查实测 `a5f1b1c` 的 `apply` 末尾即按 `w/total_w` 分配），故取 `declared` 是**回归 M1 口径**，`current` 才是一次未登记的语义变更。**代价已被压到最低**：`NotOwnedModifier` 在 S9-3 之前**无任何 registry 条目或 preset 构造它**（零生产可达配置）。**可推翻**（见报告 §八）。

> **边界一：`hard` 的 scope 为最低稀有度时，本族表达不了（2026-10-06 实测）**。`Q = 更低稀有度` 为空 → `amount = 0` → `transfer_linear` 返回恒等，**保底完全不生效**。旧实现靠「绝对赋值 + 更高稀有度豁免」造出 Σ > 1 的分布（实测 `hard(scope='r')` 得 Σ = 1.061），这是**造质量**，不属于「A 加 Q 减」族。**手册无此配置**（全部 `hard` 的 scope 为 `ssr`，除 `sr_pity` 为 `sr`），故登记为**边界**而非缺口。真要支持，须另写一个 `compute_delta()`（直接返回自定义增量表），**接口不变**。

> **边界二：`hard` 的 scope 为中间稀有度时与旧实现有差（2026-10-06 实测）**。`hard(scope='sr')`：新模型 `sr = 0.9890、ssr = 0.0110（原值不动）`；旧实现 `sr = 0.9891、ssr = 0.0109`。差 1.2e-04，成因是**旧实现在此情形 Σ = 1.011**（更高稀有度被「豁免」保留了绝对值），归一化后按比例缩水；新模型 `Σδ = 0`，更高稀有度**不写增量即精确保留**。量级 1e-4 ~ 3.5e-3（scope 越低差越大），属 §3.9.5 已登记的差异类。

**条件内联（2026-10-06 裁决）**：条件写在各类 `compute_delta()` 开头，不生效即 `return None`。**取消 §3.14 的 `ConditionalModifier` 与整个条件类族**（理由见 §3.14 的改判）。

**旧类到新类的映射**：

| 原类 | 新类 | 说明 |
|------|------|------|
| `BoostModifier` | `SoftModifier` | |
| `ThresholdForceModifier` | `HardModifier` | |
| `ForceFeaturedModifier` | `RotatingModifier` | |
| `ForceNonFeaturedModifier`（G1） | `NonFeaturedModifier` | |
| `ForceSelectedModifier` | `SelectedModifier` | |
| `ForceNotOwnedModifier`（G3） | `NotOwnedModifier` | |
| ~~`InterceptModifier`~~ | **取消** | 掷骰移入 `StreakTracker.prepare`（裁决 6B → 2026-10-10 改判 6B′，§3.1.1） |
| ~~`BaseRatioModifier`~~ | **删除** | 其转移量为 0（恒等），预设里不写该零件即可 |

**用户可见的变化为零**：TOML 字段、GUI 控件、关于页文本均不变。`target_featured` 的消费者是 `HardModifier` 自己的 `compute_delta()`（§3.2 取值来源表）。

<!-- REVIEW-R1-FIX: RULING-1B -->
<!-- REVIEW-R1-FIX: RULING-5B -->
<!-- REVIEW-R1-FIX: RULING-7B -->
<!-- REVIEW-R1-FIX: MODIFIER-IFACE -->

<!-- REVIEW-R1-FIX: ISSUE-407 -->
**Modifier 也暴露 `namespace` 属性（默认 `None`，ISSUE-407）**：声明了命名空间的 Modifier 由 `Pity` 传 `StateView(state, mod.namespace)` 而非默认 view；取值面与 Tracker / Lifecycle 同源，见 §3.1.1 的「零件的命名空间声明面」与 §3.10.3 的两级 view 分配定稿。

**Modifier 协议另含 `state_keys() -> tuple[str, ...]`（ISSUE-501，强制）**：返回本 Modifier 读或写的状态键名，默认实现为 `()`（`Modifier` 基类提供，见 §3.9.2 的基类代码块）。它是 §3.12.2 判据第 2 条「Modifier 引用了不存在的状态键」的**唯一输入**——「存在」的口径为「在 Tracker ∪ Lifecycle 的 `state_keys()` 并集内」（§3.12.2）。`ConditionalModifier` 须**转发内层的声明集**（与 `rebind` / `apply` / `compute_delta` 同列的转发义务；**包装器本身已随 2026-10-06 改判取消**，本条按历史记录保留，见 §3.14.2），否则被包裹的 Modifier 声明集恒空、该判据对全部 preset（原写「S12 起一律为包裹形态」；**2026-10-09 订正，ISSUE-004：S12 已于 2026-10-06 取消，现行形态是「条件内联、无包装器」**，本条与 ISSUE-902 一并按历史记录保留）退化为恒真。**`ConditionalModifier.state_keys()` 还须并入其条件的声明集（ISSUE-902，强制）**——§3.14 条件外置后读键者是 Condition 而非内层 Modifier，只转发内层会让条件读键落在比对集之外（详见 §3.14.2 的 Condition 协议段）。<!-- REVIEW-R1-FIX: ISSUE-501 --> <!-- REVIEW-R1-FIX: ISSUE-902 -->

**Modifier 链契约（强制）**：Pity 的 `before_draw` 按 `modifiers` 列表**顺序应用、非短路**，每个 Modifier 在前一个的输出上操作（增量逐元素相加再归一化）。覆盖型 Modifier（`RotatingModifier` 把非目标组搬空）以「把 Q 搬空」吸收前序调整，这正是 §3.1.5.5 吸收引理的实现对应。soft 抬高的 scope 总量在 guaranteed 下全部流入 featured，与旧 SoftPityMixin「先 soft 后事件」等价。

**分布空间归属（D20，2026-09-21 新增）**：Modifier 的输入输出是**卡级**分布（真实分布）。「槽位」是操作内部的临时聚合表示，由操作自行聚合与还原（还原即对单卡概率施加统一缩放，语义为「保持组内当前比例」）。管道不再以槽位级向量作为传输格式，`banner.py` 的 `scale_factors` 还原段随之删除。收益有三：① **单卡定向**成为可能（双 UP 池定轨、G3 的「UP 组排除已拥有」，二者本受同一约束制约）；② 消除聚合与还原的往返；③ 让 §3.1.5 的增量算子形式直接覆盖实现。代价见 §3.1.5.4 的让步声明与 §六 的等价性口径放宽。**实施方案（改哪些函数、接口怎么变、边界怎么处理）见 §3.9**。

**CR 随机数消耗协议（H4，强制；2026-10-10 改判 6B′ 后消费点由 Modifier 移至 `StreakTracker.prepare`）**：rotating_cr 旧类在 `before_draw` 用模块级 `random.random()`（[pity.py:574](gacha_simulator/core/pity.py#L574)、[pity.py:581](gacha_simulator/core/pity.py#L581)）做条件分支，消耗次数随分支而定。`StreakTracker.prepare` 必须在**完全相同的条件与顺序**下消耗相同数量的随机数，否则**分布仍等价**（掷骰结果与顺序无关），但固定种子轨迹即刻分叉。**6B′ 与 6B 的差别**：消费相位由 `after_draw` 回到 `before_draw`，与旧类同相位，故「与旧类逐场一致」重新可判（见下方「等价性口径」段）。

**短路条件（不可省略）**：旧实现两处消费均带前置短路，`self._cr_base_rate > 0 and random.random() < ...` 与 `state_prob > 0 and random.random() < state_prob`。故 `cr_base_rate == 0` 或 `state_prob == 0` 时**不消耗**随机数，`state_prob >= 1.0` 分支同样**不消耗**。若写成 `if random.random() < rate`（省去 `> 0`），配 0 的场合会多消耗一个随机数、随机流整体后移。现状代码在这一点上是正确的，本条仅为实施约束。

**另三条须逐位复刻的协议内容（2026-09-16 补）**：

1. **下标裁剪**：`idx = min(cr_counter.value(), len(cr_state_probs) - 1)`（[pity.py:578](gacha_simulator/core/pity.py#L578)）须原样保留，取值下标是裁剪后的 `idx`，不是 `cr_counter` 本身。
2. **空表分支不消耗**：`cr_state_probs` 为空列表时 `idx = -1`、`if idx >= 0` 为假（[pity.py:579](gacha_simulator/core/pity.py#L579)），整段 state_prob 检查被跳过、**不消耗**随机数。这是第三条不消耗路径，短路枚举须含它。
3. **`guaranteed` / `readonly` 守卫**：旧实现首行 `if self._guaranteed.is_set(): return super().before_draw(...)` 与 `if readonly: ...`（[pity.py:572-575](gacha_simulator/core/pity.py#L572-L575)）均**不掷骰**；搬迁后**两条都要在 `StreakTracker.prepare` 里显式实现**——`guard_flag` 守卫，以及 `readonly` 早退（6B 靠「查询不调 `after_draw`」天然满足，6B′ 移到 `before_draw` 后该天然性消失，漏掉即策略层每次概率查询都掷骰）。

> **原第 3 条「链中位置固定」已废止（裁决 6B，6B′ 沿用）**：旧稿要求 `InterceptModifier` 在 Modifier 链中固定在 `BoostModifier` 之后，以保住随机流位置。掷骰移入 Tracker 后该约束对象消失；取而代之的是 §3.1.1 的 CR 掷骰相位段（6B′ 下为 `prepare`：`before_draw` 内、`advance` 之后、Modifier 链之前），以及**同节的「Tracker 顺序是契约」条**（`StreakTracker` 必须排在 `FlagTracker` 之前）。

> **等价性口径（2026-10-10 改判 6B′ 后恢复）**：H4 的验收手段是「在相同条件与顺序下消耗同样次数」，它支撑 §六 的 M1「与旧类逐场一致」。6B 的形状下该手段失效（消费点移至 `after_draw`，相位与旧类不同），是一处**验收口径的净损失**；6B′ 把消费点放回 `before_draw`（`StreakTracker.prepare`），相位、条件、次数三条重新对齐，**该手段恢复适用**：`rotating_cr` / `rotating_cr_soft` 回归「与旧类逐场一致」批次。6B 想守的收益（「Modifier 层无非纯函数零件」）**在 6B′ 下同样成立**——掷骰落在 Tracker 的 `prepare` 相位，Modifier 只读 `cr_intercepted`。<!-- REVIEW-R1-FIX: RULING-6B -->

#### 3.1.3 Lifecycle（生命周期）—— 正交包装层
| Lifecycle | 语义 | 激活维 / 退役维 | 配置来源 |
|-----------|------|---------------|---------|
| `AlwaysActive` | 永远生效 | Always / Never | 默认（两者都未配） |
| `FiniteActive(max_triggers=N)` | 触发 N 次后退役（福利保底） | Always / AfterN(N) | `PityDef.max_triggers > 0` |
| `DependentActive` | 依赖另一个 Pity 激活 | Dependent / Never | `PityDef.depends_on` 非空 |
| `DependentFiniteActive(max_triggers=N)` | 被激活后，触发 N 次退役 | Dependent / AfterN(N) | `depends_on` 与 `max_triggers` 同时配置 |

> **类名变更（2026-10-06 用户裁决）**：原名 `OnceActive` / `DependentOnceActive` 与语义不符：`max_triggers` 可以是任意 N，不只 1 次。现名按计划自身声明的**两个正交维度**取：激活维（`Always` / `Dependent`）× 退役维（`Always` = 永不 / `Finite` = 触发 N 次后退役）。其余两名 `AlwaysActive` / `DependentActive` 不变。

**两个维度正交（2026-09-28 修正）**：`activation`（`Always` / `Dependent`）× `retirement`（`Never` / `AfterN`）各二值，**四个组合全部合法**——「被谁激活」与「触发几次后退役」是两件独立的事，不存在覆盖关系。上表四个具名类是这四个组合的现成写法（维度固定为二，故不构成组合爆炸）。除 `AlwaysActive` 外，其余三个均为 P64 新增或本期接线。

Lifecycle 独立于 Tracker/Modifier，只管 `is_active` 判定和 `deactivate_on_early_hit` 统一（P64 增量能力，使事件驱动型也可用；**必须同步移除 [config_toml.py:686-691](gacha_simulator/core/config_toml.py#L686-L691)<!-- REVIEW-R1-FIX: ISSUE-929 --> 的拒绝分支 H3**）。<!-- REVIEW-R1-FIX: ISSUE-005 -->

<!-- REVIEW-FIX-PREV: ISSUE-029 -->
<!-- REVIEW-FIX-PREV: ISSUE-032 -->
<!-- REVIEW-FIX-PREV: ISSUE-202 -->
**Lifecycle 协议（强制；ISSUE-029 补 `rebind`；ISSUE-202 补 `initialize`；ISSUE-407 补第三实参 `namespaces`）**：`Pity` 骨架调用以下**五个**方法——`initialize(state, name, namespaces=())`（**构造期**写入初始 `_active`，归属论证见下段 ISSUE-202 专段）、`is_active(state, name)`（`before_draw` / `after_draw` 首行早退）、`should_deactivate(ctx, state, name, fired)`（退役判定，**先于** `commit`，见 §3.1.4 的 ISSUE-018；**`fired` 形参为 2026-09-28 独立复核补**——它是「本次抽卡是否命中」的布尔值，由 `Pity` 用 `any(tr.did_reset(...))` 算好后传入，**Lifecycle 自身拿不到该判据**，因为 `LifecycleConfig` 只有 `deactivate_on_early_hit` / `depends_on`、无 `scope` / `reset`，而「命中」的定义依赖后者）、`deactivate(state, name)`（清 `_active`）、`rebind(state, name, namespaces=())`（重绑本生命周期为 `name` 与 `namespaces` 中**每个**命名空间持有的 `_active` Flag 到 per-call `state`；**实参面与 `initialize` 严格对称**，见下段 ISSUE-917 专段；与 Tracker / Modifier 同名同义，但后两族仍是两实参；`Pity._rebind_state` 无条件调用）。<!-- REVIEW-R1-FIX: ISSUE-917 --><!-- REVIEW-R1-FIX: ISSUE-919 -->。另须暴露**两个只读属性**——`deactivate_on_early_hit`（供 `Pity.after_draw` 判定「本次退役是否跳过重置」）与 **`depends_on`**（**ISSUE-406**：`PityEngine._build_activation_graph` 对**每一条** behavior **无条件**读 `lc.depends_on`（[pity.py:1214-1215](gacha_simulator/core/pity.py#L1214-L1215)，非只读 `Dependent` 族）<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->；改造后 `bh._lifecycle` 是**对象**（`getattr` 恒真），只要 `AlwaysActive` / `FiniteActive` 不代理该属性，**每次 `PityEngine(...)` 构造**都会 `AttributeError`。同一路径还被 S3-1 的验收「`_pools` 注入后同池 `depends_on` 不再触发池交集警告」与 §3.12.2 的池交集校验依赖）。两个属性**一并在 `Lifecycle` 基类里由 `self._cfg` 统一代理**——原稿「`depends_on` 由 `DependentActive` 从同一 `cfg` 读出」的写法**已废止**（它使该属性只存在于一个子类上，与本条要求的统一代理冲突）；`DependentActive` 自此只多一个「依赖激活」语义，不再单独持有该字段的读法。四个内置 Lifecycle 均须实现这**五**个方法（无状态可空实现），`rebind` 尤其不可省——`Pity` 不设守卫。<!-- REVIEW-R1-FIX: ISSUE-407 --> 另与其他两族一致暴露 **`namespace` 属性**（默认 `None`），由 `Pity` 决定给它传默认 view 还是 `StateView(state, lc.namespace)`（取值面见 §3.1.1 的「零件的命名空间声明面」；`Lifecycle.initialize` 对**本保底声明的全部命名空间**写 `_active` 的推广见 §3.10.3）。**并同样暴露 `state_keys() -> tuple[str, ...]`（ISSUE-501）**——Lifecycle 的声明集为 `('triggers',)`（`FiniteActive` / `DependentFiniteActive` 且 `max_triggers > 0` 时），其余三个 Lifecycle 返回 `()`；该成员是 §3.12.2 判据第 1/2 条的输入之一（`Pity` 汇总三族声明集，见 §3.1.4 骨架的 `_declared_keys`）。**早退不依赖任何类型集合**：**`before_draw` / `after_draw` 首行的 `is_active` 早退由骨架无条件承担**（§3.1.4 骨架对全部类型生效），`_EVENT_DRIVEN_TYPES` 只影响 `_validate_behaviors` 规则 3 的互斥校验、**不参与早退判定**（ISSUE-506）。<!-- REVIEW-R1-FIX: ISSUE-501 --> <!-- REVIEW-R1-FIX: ISSUE-506 -->

<!-- REVIEW-R1-FIX: ISSUE-406 -->
**`should_deactivate` 的调用形态（ISSUE-402，2026-09-30 独立复核补，强制）**：`Pity.after_draw` 的调用行必须是 `self._lifecycle.should_deactivate(ctx, self._state, self._name, fired)` 形态——**四实参、第四实参为 `fired`**，`fired = self.did_fire(ctx)` 在退役判定**之前**取值（§3.1.4 骨架已写死）。**不得写成三实参**：三实参下，若 Lifecycle 按本协议（四参）实现即每次抽卡 `TypeError`；若迁就三参，则 `triggers` 只能无条件累加、退化为「激活后的**抽数**」而非「**触发次数**」，`max_triggers=2` 在第 2 抽就退役，与「触发 N 次后退役」相反，本条条第 4 条与 §六 ISSUE-032 ⑤ 因此**全部不可达**。**验收分两层**（缺第二层则缺口不可见）：① S1d 单测直构 Lifecycle 并**显式传 `fired`**（覆盖四参语义）；② 一条**经 `Pity.after_draw` 的端到端断言**（覆盖调用形态——S1d 与 S3-2 的既有验收只断言构造期 `_active`，都不经过该调用行）。

**`max_triggers` 的计数载体（2026-09-28 独立审查补，原缺口）**：`FiniteActive` / `DependentFiniteActive` 的「已触发次数」必须落在 **state 的保底命名空间**下，键名定为 **`triggers`**（与 `counter` / `guaranteed` / `fate_points` 等既有键同层）。四条约束：

1. **不可放在 Lifecycle 对象内**——Lifecycle 实例在同一 worker 内**跨模拟复用**（`rebind` 每次调度都被调用），对象内计数会跨模拟泄漏，破坏「固定种子可复现」。
2. **键集声明**——该键须登记进 §3.12.1 的「状态键合法」不变式检查集；声明者是 **Lifecycle** 而非 Tracker（它是生命周期状态，不属追踪器）。**声明通道 = 三族统一的 `state_keys()`**（ISSUE-501）：`FiniteActive` / `DependentFiniteActive` 在 `max_triggers > 0` 时返回 `('triggers',)`，其余返回 `()`；该成员同时是 §3.12.2 判据与 §3.13 状态层 checker 的输入（§3.1.1 的「声明键集」段）。<!-- REVIEW-R1-FIX: ISSUE-501 -->
3. **与等价性口径的关系**——该键**仅在 `max_triggers > 0` 时**创建（与 `*_init` 的 truthy 规则一致），而旧实现无此能力（`deactivate_on_early_hit` 只覆盖 N=1 且不计数），故属**增量能力**，**不在「S1–S5 状态快照逐场一致」范围内**，须按 §3.5 的增量能力口径单独验收。
4. **读写都在 `should_deactivate`，且只在 `fired` 时累加**——`if fired: n = state.get(name, "triggers", 0) + 1; state.set(name, "triggers", n); if n >= max_triggers: return True`。**2026-09-28 独立复核补**：原稿只写了「读」、未写「谁累加」，而最自然的落点（无条件累加）会让 `triggers` 变成「激活后的**抽数**」而非「**触发次数**」——`max_triggers=2` 会在第 2 抽就退役，与「触发 N 次后退役」相反。加上 `fired` 判据后语义才正确，且与 §3.1.1 M4 的「命中 ≡ 回到初始状态」同源。
5. **未激活期间不累加**——`after_draw` 首行 `is_active` 早退（§3.1.4 骨架）在 `should_deactivate` 之前，故「自激活后起算」（§五 风险行 / §六 ⑥）由调用位置天然保证。

<!-- REVIEW-FIX-PREV: ISSUE-301 -->
**生命周期字段到 Lifecycle 对象的构造来源（ISSUE-301，2026-09-22 定稿，强制）**

`pdef.deactivate_on_early_hit` / `pdef.depends_on` 是两个**跨 type 共享**的字段（§1.4 第 2 条：与驱动类型无关的正交包装层，P55 只给 counter 驱动用，P64 要补到全部类型）。旧代码里它们的唯一转换点是 `create_behavior` 末尾的 `lifecycle_kwargs` 段（[pity.py:893-900](gacha_simulator/core/pity.py#L893-L900)：`params['lifecycle'] = LifecycleConfig(**lifecycle_kwargs)`），而新架构的 `Pity` 形参类型是 **Lifecycle 对象**（§3.1.4 骨架 `lifecycle: Lifecycle = AlwaysActive()`）。因此必须有且只有一处定义「参数袋 → 哪个 Lifecycle 类」的分工。若缺，实施者极易「preset 不写 `lifecycle` + 旧 `LifecycleConfig` 构造段又不删」两处各留一半，后果是**全部 `deactivate_on_early_hit` 与全部 `depends_on` 配置静默失效**——前者使 §六 的 N1 例外断言与「事件驱动型退役」断言双双不可达，后者使激活传播与「`depends_on` 引用不存在名」的 `ConfigError` 一并消失；且旧类已退役，没有任何旧实现可作对照发现。

**定稿：转换点唯一，位于 `core/pity.py` 的模块级 helper。** **落地步骤（ISSUE-GATE-3-dependency-order，2026-09-22）**：本 helper 的**定义随 S1d** 写入 `core/pity.py`（即 `AlwaysActive` / `FiniteActive` / `DependentActive` 与 `LifecycleConfig` 参数袋同批落地的那一块——其依赖 S1a 的 `LifecycleConfig` 与 S1d 的四个 Lifecycle 类此时已全部就位），**S4-4 不再定义它**、只留 `lifecycle` 键的校验防线与旧 `lifecycle_kwargs` 段清理（§七 S1d / S4-4）。**不可留到 S4-4 才定义**：§3.2 / §3.3 / §3.14.2 的 preset 工厂返回 dict 已写 `lifecycle=build_lifecycle(pdef)`，而 S4-2 / S4-3 排在 S4-4 之前，S4-3 的验收命令「全部 10 个 preset 构造成功」会**实际调用**工厂（模块级名字在调用时解析），晚定义即 `NameError`。<!-- REVIEW-FIX-PREV: ISSUE-GATE-3-dependency-order -->

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
        return DependentFiniteActive(cfg, max_triggers=_n)
    if _dep:
        return DependentActive(cfg)
    if _n > 0:
        return FiniteActive(cfg, max_triggers=_n)
    return AlwaysActive(cfg)
```

| 激活维（`pdef.depends_on`） | 退役维（`pdef.max_triggers`） | `build_lifecycle` 产出 | 旧路径对照（[pity.py:893-900](gacha_simulator/core/pity.py#L893-L900)） |
|---|---|---|---|
| 空 / None | `0`（不限） | `AlwaysActive(cfg)` | 无 `lifecycle_kwargs`、`params` 不带 `lifecycle` 键 → behavior 落到默认 `LifecycleConfig()` |
| 空 / None | `> 0` | `FiniteActive(cfg, max_triggers=n)` | 旧路径无对应物（旧 `deactivate_on_early_hit` 只覆盖「首次命中即退役」） |
| 非空 | `0`（不限） | `DependentActive(cfg)` | `LifecycleConfig(depends_on=…, …)` |
| 非空 | `> 0` | `DependentFiniteActive(cfg, max_triggers=n)` | 旧路径无对应物（两维正交后的新增组合） |

（`cfg` = `LifecycleConfig(depends_on=pdef.depends_on, deactivate_on_early_hit=pdef.deactivate_on_early_hit)`，四个组合都带入。**注意退役维取 `max_triggers`，不是 `deactivate_on_early_hit`**——后者是与两维正交的**第三个开关**（布尔，命中即退役），四组合下均由 `should_deactivate` 一并判定。原表把 `deactivate_on_early_hit` 误作第二轴，是本表被修正的原因。）

三条配套纪律：

1. **`LifecycleConfig` 的去留定稿 = 保留，角色改为「Lifecycle 对象的构造参数袋」**。四个 Lifecycle 实现共用一个基类 `Lifecycle`（住 `pity_tracker.py`），基类持有 `self._cfg`；`deactivate_on_early_hit` **与 `depends_on`** 两个属性**都由基类对 `self._cfg` 统一代理**（协议要求暴露这两个属性，见上段；**ISSUE-406** 已把原稿「`depends_on` 由 `DependentActive` 从同一 `cfg` 读出」的写法废止——`_build_activation_graph` 对每条 behavior 都读该属性，[pity.py:1214-1215](gacha_simulator/core/pity.py#L1214-L1215)）。<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->`core/__init__.py` 的导出面**不变**（ISSUE-025 的保留清单已含 `LifecycleConfig`），`core/pity_primitives.py` 仍承载其定义（§3.1.6 叶子层）。**旧 `create_behavior` 的 `lifecycle_kwargs` 段（:893-900）随之删除**——同一转换不得留两处。
2. **`FiniteActive` / `DependentFiniteActive` 的产出条件**：由 `build_lifecycle` 按两维独立取值（激活维看 `depends_on`、退役维看 `max_triggers > 0`），**两维同时配置时两者都生效**（产出 `DependentFiniteActive`）。2026-09-28 修正：原稿写「`depends_on` 非空时以 `DependentActive` 优先、`max_triggers` 被忽略」——该写法把一个二维空间压成了一维三选一，与两维正交的设计相悖。
3. **调用点**：每个 preset 工厂的返回 dict 一律含 `lifecycle=build_lifecycle(pdef)`（§3.2 取值来源表已补该行；§3.2 / §3.3 / §3.14.2 的四份 preset 代码块已同步写入）。§3.1.4 骨架的 `lifecycle: Lifecycle = AlwaysActive()` 只是**兜底默认值**，不是正常路径。**三处落点的步骤分工（ISSUE-GATE-3-dependency-order）**：helper 定义在 **S1d**、`lifecycle=` 键由 **S4-2 / S4-3** 的工厂写入、旧 `lifecycle_kwargs` 段的删除与 `lifecycle` 键防线留在 **S4-4**——删除时机不可前移，S4-2 / S4-3 期间未迁移的类型仍走 `create_behavior` 旧类兼容路径、仍需该段注入 `LifecycleConfig`，提前删除会让这些类型的 `deactivate_on_early_hit` / `depends_on` 静默失效（§七 S4-4）。

**防线（禁止静默回退）**：`create_behavior` 在 `preset(pdef)` 之后**校验返回 dict 含 `lifecycle` 键**，缺失即抛 `ConfigError`（与 preset 构造失败的处置同层，§四 `core/pity.py` 行 / ISSUE-204）。若改成「缺失时静默取骨架默认 `AlwaysActive()`」，任何忘了写该键的 preset 都会让该类保底的 `deactivate_on_early_hit` / `depends_on` 全部失效且无任何报错——这正是本条要消除的失效模式。§六 已补对应断言。

<!-- REVIEW-FIX-PREV: ISSUE-202 -->
**`_active` 的构造期写入归属（ISSUE-202，2026-09-22 定稿，强制）**

旧实现的这一动作在 `CounterBasedBehavior.__init__`（[pity.py:133-135](gacha_simulator/core/pity.py#L133-L135)）：<!-- REVIEW-R1-FIX: ISSUE-002 -->

```python
self._active = Flag(state, name, "_active")
if self._lifecycle.depends_on is None:
    self._active.set()
```

新骨架若不承接它，非 `depends_on` 保底的 `_active` 恒为默认 `False`（`PityEngine.is_active` 的默认值就是 `False`，[pity.py:1375-1379](gacha_simulator/core/pity.py#L1375-L1379)），而 `_active=True` 本就靠「构造期 set + 阶段 3 快照」承载——后果是 `before_draw` / `after_draw` 首行**双双早退**，**全部计数型保底静默失效**（M1 等价性会报错，但定位成本高，且 §3.1.3 的协议表会被当成权威依据）。<!-- REVIEW-R1-FIX: ISSUE-001 -->

**归属定稿**：写入动作由 **Lifecycle 协议新增的 `initialize(state, name, namespaces=())`** 承担，而不是留在 `Pity.__init__`——`_active` Flag 本就由 Lifecycle 持有（`rebind` 重绑它、`deactivate` 清它），构造期写入归同一持有者，`Pity` 不必按 `btype` 分叉（该 Flag 的**重绑**通道与 `initialize` 同实参面，见下段 ISSUE-917 专段）。<!-- REVIEW-R1-FIX: ISSUE-917 -->

| Lifecycle | `initialize(state, name, namespaces=())`（**ISSUE-407**：对 `name` 与 `namespaces` 中每个命名空间都按本表写入；`namespaces` = `Pity` 收集的零件命名空间集合；**同一组 `namespaces` 亦为 `rebind` 的第二实参**——**ISSUE-917**：两方法的实参面必须对称，见下专段） |
|-----------|---------------------------|
| `AlwaysActive` | 写 `_active = True`（对应旧 `depends_on is None` 分支） |
| `FiniteActive(max_triggers=N)` | 写 `_active = True`（首触发前生效，与 `AlwaysActive` 同） |
| `DependentActive(depends_on=…)` | 空实现（激活由引擎的 `depends_on` 传播写入，[pity.py:1340](gacha_simulator/core/pity.py#L1340)） | <!-- REVIEW-R1-FIX: ISSUE-002 -->
| `DependentFiniteActive(depends_on=…, max_triggers=N)` | 同 `DependentActive`：空实现（不写 `_active`，由引擎激活传播置位）；退役计数自激活后起算 |

`Pity.__init__` 在创建 `_view` **之前**调用 `self._lifecycle.initialize(state, self._name, self._namespaces)`（§3.1.4 骨架那行注释已改写为真实调用；**ISSUE-919**：实参形态须与骨架的调用行、§3.1.3 协议表、§六 与 §七 同口径——漏传 `namespaces` 则 `X_soft` 的 `_active` 无处产生，`rebind` 亦无对象可重绑，见下段 ISSUE-917）。<!-- REVIEW-R1-FIX: ISSUE-919 -->

<!-- REVIEW-R1-FIX: ISSUE-917 -->
**`rebind` 的实参面必须与 `initialize` 对称（ISSUE-917，2026-10-01 定稿，强制）**

问题：`initialize(state, name, namespaces=())` 对 `name` **与每个 `namespaces` 成员**都按上表写 `_active`，而 `rebind(state, name)` 只重绑 `name` 的 Flag。两种实现形态各有一支会失效：① **每个命名空间各持一个 `_active` Flag**——`X_soft` 的那个 Flag 永不被重绑，worker 内同一 engine 连跑第 2..N 场模拟时它仍指向上一场的 `PityState`（与 ISSUE-004 / P75 同一失效面），而骨架只按 `self._name` 读 `_active`（`is_active` / `before_draw` 首行早退），**写错账本不会报错**；② **Lifecycle 只持 `name` 的 Flag**、`namespaces` 的 `_active` 在 `initialize` 内直接 `state.set` 一次——该键即 write-once，`rebind` 无从触及，一旦将来需要清理某命名空间的 `_active` 便静默失效。

**定稿（取 ①）**：`Lifecycle` 基类持有 `self._ns_active`（键 = `name` 与 `namespaces` 的并集，`initialize` 按上表对各键写入），协议扩为 **`rebind(state, name, namespaces=())`**——对**并集中每个** Flag 做纯重定向（不复制旧值，P75 纪律），`Pity._rebind_state` 传 `self._namespaces`（§3.1.4 骨架同行）。`deactivate(state, name)` **只清 `name` 的 Flag**（退役只作用于本保底，与 §3.10.3 配套 2 一致；命名空间的 `_active` 因此与旧实现内层 `SoftStepBehavior._active` 同形——构造期写一次、此后不再被触碰）。取 ① 的旁证：旧实现正是「每个命名空间各持 Flag 且各自重绑」（内层 `SoftStepBehavior` 持 `X_soft` 的 `_active`，经 `SoftPityMixin._rebind_state` 委托重绑，[pity.py:539-543](gacha_simulator/core/pity.py#L539-L543)），故 ① 与旧实现**同构**（精确建模原则）。

**⚠ 备选（未采用）**：形态 ②。否决理由：它把「`X_soft._active` 永不被清除」当作不变式，而该事实只成立于旧实现（[pity.py:333](gacha_simulator/core/pity.py#L333) 的 `clear()` 在内层 `_on_reset` 中，而 mixin 从不调内层 `after_draw`），不是本次改造的契约；且该形态下 §六 无法给出「跨场重绑后仍写当前 state」的断言（该键根本不参与重绑）。<!-- REVIEW-R1-FIX: ISSUE-002 -->

**快照面的裁决（2026-09-22 第八轮定稿，原为 ⚠ 待人工裁决）**：旧实现中事件驱动型（`rotating` / `targeted` / `rotating_cr` 及两个 `_soft` 复合）**不写** `_active`，统一写入后其命名空间会**新增一个 `_active: True` 键**。这与 §六 主线「状态快照与旧类逐场完全一致」的字面口径冲突，两条路线择一。**取路线 ①（原推荐项）**：

1. **统一写入（采用）**：保留 `initialize` 的统一写入，并把「事件驱动型命名空间多一个 `_active: True` 键」登记为 S1 至 S5 的**已知差异**。理由：与 §3.5「`deactivate_on_early_hit` 对事件驱动型可用」的能力目标一致，且 §六 已有同型的 `_soft` 命名空间先例。对应断言与风险行已分别落在 §六 与 §五。<!-- REVIEW-FIX-PREV: ISSUE-GATE-risk-mitigation -->
2. ~~备选：`initialize` 改为**仅计数驱动型**写入（`AlwaysActive` 须按 `btype` 判定）~~（**已否决**）：代价是把分类分支重新引入 Lifecycle、与「统一骨架」的取向相悖，且会让「事件驱动型的 `deactivate_on_early_hit`」失去 `_active` 载体，与 §3.5 的增量能力目标直接冲突。

**实施者按 ① 落笔，S3 开工前不再需要二次决策**；§六 对应断言的备选分支已删除。

**`FiniteActive` 的配置层落点（ISSUE-032，2026-09-27 用户裁决：本期接线）**：`FiniteActive(max_triggers=N)` 的配置接线**纳入本期范围**（原 2026-09-22 第八轮定稿为「只实现类、不做配置接线」，2026-09-27 用户否决该定稿）。

**为什么它本该有配置**：`max_triggers`（触发 N 次后退役）是 Lifecycle 的**基本能力**——旧实现里 `deactivate_on_early_hit` 就是它在 N=1 时的特例（[pity.py:327-335](gacha_simulator/core/pity.py#L327-L335) 与 [pity.py:403-411](gacha_simulator/core/pity.py#L403-L411) 两处 `_active.clear()` 后返回 True、跳过 counter 重置）。把次数上限做成可配置的 N 是能力完备性的自然要求；只实现类而不给配置入口，等于该能力对用户不可见。手册 G5 的 `hard(max_triggers=1)`（[手册:560](docs/主流抽卡游戏卡池机制配置转换手册.md#L560)）正是它的真实用例，当前只是散写、无字段承载。<!-- REVIEW-R1-FIX: ISSUE-002 -->

**连带改动（四处，均已登记进 §四 与 §七）**：

1. **`PityDef` 新增 `max_triggers: int = 0`**（0 = 不限，与 `MilestoneDef.max_triggers` 的零值约定一致）——`core/config_store.py`
2. **`config_toml` 解析与该键 round-trip**（`_build_pity` 读取 + `_pitydef_to_toml` 写回）；范围校验：负值抛 `ConfigError`（防「写了 -1 却静默当 0」）
3. **`build_lifecycle(pdef)` 按两个正交维度独立取值**：激活维 = `depends_on` 非空 ? `Dependent` : `Always`；退役维 = `max_triggers > 0` ? `AfterN(n)` : `Never`。**两维同时配置时两者都生效**（产出 `DependentFiniteActive`）。配置来源：激活维取 `PityDef.depends_on`、退役维取 `PityDef.max_triggers`（0 = 不限）。**2026-09-28 修正**：原稿写「`depends_on` 优先、`max_triggers` 被忽略」是错的——「被谁激活」与「触发几次后退役」互不干涉，不存在覆盖关系
4. **`gui/config_panel.py` 新增「触发次数上限」数值控件**（0 = 不限），与既有 pity 编辑区同列；`_apply_pity_edit` 与 load/save 路径同步该键

**验收**见 §六 与 §七（`PityDef(max_triggers=2)` 经 `build_lifecycle` 产出 `FiniteActive`；TOML round-trip 保留；GUI 编辑→保存→重载一致；触发 N 次后 `is_active` 为假；`depends_on` 优先；负值抛 `ConfigError`）。<!-- REVIEW-FIX-PREV: ISSUE-032 -->

<!-- P64-DEBUG-REG -->
> **该变更的概率级后果补登记（系统性 debug，2026-10-15，实测量化）**：本段此前只登记了「旧实现只有 `CounterBasedBehavior` 读写 `_active`」这一**事实**，而等价性装置**明列 `depends_on` 不在覆盖面内**，故其概率级后果此前无记录。实测：`dep = rotating(guaranteed_init=True, depends_on='src')`、`src = hard(τ=10)` 时，**旧侧 rotating 不读 `_active`、从第 0 抽起即按 `guaranteed` 生效**（`{ssr_featured: 0.4, ssr: 0.0}`），新侧被 `DependentActive` 门控、源触发前恒等（`{ssr_featured: 0.2, ssr: 0.2}`）；**58 抽概率差、maxdiff 0.5**。`targeted(fate_points_init=1, depends_on='src')` 同形（`TargetedBehavior` 同样不读 `_active`）。**控制组（无 `depends_on`）两侧概率零差**，证明差异确由门控产生。**方向：新侧是正确的一侧**（`depends_on` 应当门控依赖方；旧实现对 6 个事件驱动型静默忽略该字段）。登记用途：日后若「门控被静默回退」，可据本条的量化值识别。

**`is_active` 早退对事件驱动型是行为变更（2026-09-16 补，须与等价性范围显式隔离）**：旧实现中只有 `CounterBasedBehavior` 读写 `_active`（[pity.py:185](gacha_simulator/core/pity.py#L185)、[pity.py:195](gacha_simulator/core/pity.py#L195)），`RotatingBehavior` / `TargetedBehavior` **完全不读它**；而引擎的 depends_on 传播会**写** `_active`（[pity.py:1340](gacha_simulator/core/pity.py#L1340)）。即旧实现里「事件驱动型配了 `depends_on`」是**惰性**的：标志被写入但无人读，`before_draw` / `after_draw` 照常执行。<!-- REVIEW-R1-FIX: ISSUE-002 -->

§3.1.4 骨架在 `before_draw` / `after_draw` 首行统一做 `is_active` 早退，会让这类配置**真正生效**（未激活前不改分布、不更新状态）。这是概率流改变，不是「只收严」，故：

- 属 P64 增量能力，须**单独验收**（判据：配 `depends_on` 的事件驱动型，激活前 `before_draw` 返回原分布、`after_draw` 不更新状态）
- 等价性验收须**显式排除**「事件驱动型 + `depends_on`」这类配置，否则与 N1/M4 的等价性主张冲突

#### 3.1.4 统一 Pity 骨架

<!-- REVIEW-FIX-PREV: ISSUE-001 -->
<!-- REVIEW-FIX-PREV: ISSUE-004 -->
<!-- REVIEW-FIX-PREV: ISSUE-018 -->
<!-- REVIEW-FIX-PREV: ISSUE-019 -->
<!-- REVIEW-FIX-PREV: ISSUE-024 -->
<!-- REVIEW-FIX-PREV: ISSUE-029 -->
<!-- REVIEW-FIX-PREV: ISSUE-033 -->
<!-- REVIEW-FIX-PREV: ISSUE-202 -->
```python
class Pity(PityBehavior):
    """统一保底骨架——Tracker + Modifier + Lifecycle 三元组。"""
    def __init__(self, *, name, state, scope, btype,
                 trackers: List[Tracker],
                 modifiers: List[Modifier],
                 lifecycle: Lifecycle = AlwaysActive(),
                 priority: int = 0,
                 pools: tuple = ('*',),         # ← ISSUE-019：供 _build_activation_graph 池交集校验
                 # ~~reads~~（2026-10-06 删除，§3.10.2 改判）：原形参由 PityDef.reads 注入、
                                                #   供 get_reads_for_pool() 汇总以做门控。门控取消后不再需要。
                 flags: Optional[dict] = None,  # ← AUDIT-BREAK-3：preset 返回 dict 的 `flags` 键在此
                 counters: Optional[dict] = None):  # 消费；`counters` 同理（键集与写入规则见下）
        self._name = name; self._state = state
        # ← ISSUE-503：`scope` 形参**必须是已归一化的小写值**——`create_behavior` 侧经
        #   `_norm_scope(pdef, entry['default_scope'])` 产出，preset 侧经 `_norm_scope(pdef)`
        #   产出（§3.2 取值来源表）。本骨架**不做二次归一化**（那会让「谁负责归一化」变成
        #   两处、且 preset 侧的零件已在骨架之前用各自取值构造完毕，骨架再改只会造成
        #   `Pity._scope` 与零件 `_scope` 再次分叉——正是 ISSUE-503 的缺陷形态）。
        self._scope = scope; self._btype = btype
        self._priority = priority
        self._pools = pools
        self._trackers = trackers; self._modifiers = modifiers
        self._lifecycle = lifecycle
        # ← ISSUE-001：**不得写死 is_event_driven**。三个分类标志继续由 btype 推导，
        #   与 CounterBasedBehavior.__init__（pity.py:132-137）同源。写死会让
        #   _validate_behaviors（pity.py:931-982）的规则 2/3/4（is_hard → is_event_driven
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
        #   AlwaysActive / FiniteActive 在其中写 _active = True，DependentActive 为空实现
        #   （激活由引擎 depends_on 传播写）。漏掉即非 depends_on 保底 _active 恒 False、
        #   before_draw / after_draw 首行双双早退，全部计数型保底静默失效（§3.1.3）。
        # ← ISSUE-407：先收集零件声明的命名空间（去 None），再调 initialize——
        #   Lifecycle 需要知道「本保底声明了哪些命名空间」才能把 _active 写进 X_soft
        #   （§3.10.3 配套 2）。顺序不可颠倒：_view / _ns_views 尚未创建时 initialize 只写 state。
        self._namespaces = tuple(sorted(
            {getattr(_p, 'namespace', None)
             for _p in (*trackers, *modifiers, lifecycle)} - {None}))
        # ← ISSUE-501：三族声明键集的**汇总点**（S10-2 的两条构造期判据与 S11 状态层
        #   checker 的唯一输入）。三族一律暴露只读成员 `state_keys() -> tuple[str, ...]`
        #   （由构造形参决定、不依赖 state），故此处无守卫直调；缺该方法即首次构造
        #   AttributeError（与 `rebind` 同级的协议义务，不得省，§3.1.1 的「声明键集」段）。
        #   三者分开存，因为判据口径不同：判据 1（同键被两个 Tracker 声明）查
        #   `'trackers'` 内的重复；判据 2（Modifier 引用不存在的键）以
        #   `trackers ∪ lifecycle` 为「存在」的并集（key: 'modifiers' 只作被查方）。
        #   判据本体（两条 ConfigError）随 S10-2 落地（§3.12.2）；S10-2 之前此处只汇总、
        #   不校验——但不能省略汇总，否则 S10-2 无数据来源、S11 的检查项同样落空。
        self._declared_keys = {
            'trackers':  tuple(k for _p in trackers  for k in _p.state_keys()),
            'modifiers': tuple(k for _p in modifiers for k in _p.state_keys()),
            'lifecycle': tuple(lifecycle.state_keys()),
        }
        # ← ISSUE-202：构造期写入 _active 有归属方法，不得只留注释。
        #   AlwaysActive / FiniteActive 对 name 与 _namespaces 中每个命名空间都写 True，
        #   DependentActive / DependentFiniteActive 为空实现
        #   （激活由引擎 depends_on 传播写）。漏掉即非 depends_on 保底 _active 恒 False、
        #   before_draw / after_draw 首行双双早退，全部计数型保底静默失效（§3.1.3）。
        self._lifecycle.initialize(state, name, self._namespaces)   # ← ISSUE-202 / ISSUE-407，须先于 _view 创建
        # ← ISSUE-004：随 state 重建，见 _rebind_state。
        # ← ISSUE-GATE-dependency-order：StateView **自 S3 起**即在本文件落一个薄版
        #   （get 直取 state.data.get(name, {})，定义见 §3.10.3），S9 才把 name 之外的读取
        #   切断并接入 Modifier 的 view 形参——故本行不是「引用未定义符号」。
        #   声明了 `namespace` 的零件由 Pity 另建 view（§3.10.3 定稿），本行是**默认 view**。
        self._view = StateView(state, name)
        # ← ISSUE-407：零件命名空间 view（keyed by namespace）。调用某零件时取
        #   self._view_for(part)，**不得写死 self._view**，否则 X_soft 的读取全落默认命名空间。
        self._ns_views = {_ns: StateView(state, _ns) for _ns in self._namespaces}
        # ← AUDIT-BREAK-3：preset 返回 dict 的 `flags` / `counters` 两键由此处**消费**
        #   （此前全计划无任何消费者：原样 `**preset` 展开进 Pity(...) 即 TypeError，
        #   不展开则两键成死代码，并与 _build_pity_state_init 并存为第二初始值机制）。
        #   写入规则与 §3.1.1 的 L4 键集语义一致——**仅 truthy 才预建键**（对齐
        #   _build_pity_state_init 的 `if cv:`，[pity.py:1003-1004]），故与引擎侧的
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
        self._lifecycle.rebind(state, self._name, self._namespaces)   # ← ISSUE-917：与 initialize 同实参面（逐命名空间重绑 _active Flag，否则 X_soft 跨场指向上一场 state）  # REVIEW-R1-FIX: ISSUE-917
        # ← ISSUE-004：view 必须随 state 重建。worker 内同一 engine 被 N 次模拟复用，
        #   跨模拟隔离唯一靠 rebind；view 若只在构造期建一次，第 2..N 场读的仍是旧账本。
        self._view = StateView(state, self._name)   # 默认 view
        # ← ISSUE-407：零件命名空间 view **同批重建**（否则 worker 内连跑 N 场模拟时零件
        #   view 指向旧账本，与 ISSUE-004 同一失效模式）。
        self._ns_views = {_ns: StateView(state, _ns) for _ns in self._namespaces}

    def _view_for(self, part):
        """零件级 view 取值（ISSUE-407）：声明了 `namespace` 的零件拿它自己的 view，
        其余拿默认 view。**遍历 trackers / modifiers 时一律经本方法，不得写死 `self._view`。**
        注意：Tracker 的 `advance` / `commit` / `did_reset` 形参是**原始 `state`**（§3.1.1
        协议表），故本方法只用于 Modifier 的 `view` 形参与需要 view 的零件调用。"""
        return self._ns_views.get(getattr(part, 'namespace', None)) or self._view

    # ~~_gated_ctx~~（2026-10-06 删除，§3.10.2 改判）：原方法按 `self._reads` 决定是否把
    # external 置 None 给 Modifier。门控取消后，`ctx.sim` 永远填充、对所有 Modifier 一致，
    # 不再需要派生 ctx。ISSUE-404（禁止就地改写共享 ctx）随之失去对象。

    def before_draw(self, ctx, readonly=False):
        if not self._lifecycle.is_active(self._state, self._name):
            return ctx.current.copy()
        for tr in self._trackers:            # N1：计数型先在 before 侧推进
            tr.advance(ctx, self._state, self._name, readonly=readonly)
        out = ctx.current.copy()
        for mod in self._modifiers:
            nxt = mod.apply(ctx, self._view_for(mod), out, readonly)    # ← ISSUE-407：按零件命名空间取 view
            if nxt is not None:
                out = nxt                    # 链式应用（非短路）；S8 后即增量逐元素相加再归一化
        return out

    def after_draw(self, ctx):
        if not self._lifecycle.is_active(self._state, self._name):
            return
        # ← ISSUE-402（2026-09-30 独立复核补，阻塞级）：`should_deactivate` 的**第四实参
        #   `fired` 必须在此算出并传入**（§3.1.3 协议是 `should_deactivate(ctx, state, name,
        #   fired)`）。`fired` ≡ 「本次抽卡是否让本保底回到初始状态」，由 `self.did_fire(ctx)`
        #   （= `any(tr.did_reset(...))`）给出——**Lifecycle 自身拿不到该判据**：`LifecycleConfig`
        #   只有 `deactivate_on_early_hit` / `depends_on`，无 `scope` / `reset`，而「命中」的
        #   定义依赖后者。三实参调用有两种失败形态：① Lifecycle 按四参协议实现 → 每次抽卡
        #   `TypeError`；② 迁就三参、`triggers` 只能无条件累加 → 该计数退化为「激活后的**抽数**」，
        #   `max_triggers=2` 在第 2 抽即退役，与「触发 N 次后退役」相反，§六 ISSUE-032 ⑤ 与
        #   §3.1.3 条第 4 条因此不可达。
        #   `did_reset` 只看本次 `ctx.draw`（§3.1.1 M4 统一语义），与 `commit` 的先后无关，
        #   故在退役判定之前取值是安全的。
        fired = self.did_fire(ctx)
        # ← ISSUE-018：退役判定必须【先于】commit。旧实现在 after_draw 里先判
        #   _should_reset，再调 _on_reset（deactivate_on_early_hit 时清 _active 并
        #   return True），命中则提前 return 跳过 _counter().reset()
        #   （pity.py:189-198 与 :329-337 / :405-413）。若写成「先 commit 后 deactivate」，
        #   counter 会被无条件归零，与 §3.1.1 的例外段、§六 的 N1 例外断言三者相悖。
        retire = self._lifecycle.should_deactivate(ctx, self._state, self._name, fired)
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

<!-- REVIEW-R1-FIX: ISSUE-501 --> <!-- REVIEW-R1-FIX: ISSUE-503 -->

<!-- REVIEW-R1-FIX: ISSUE-404 -->
**~~`reads` 门控的落点（ISSUE-404，2026-09-30 独立复核补）~~**（**2026-10-06 随 §3.10.2 改判删除**：门控取消，本条失去对象）。原内容：§3.10.2「送达路径定稿」第 4 条所写「由 `Pity` 按自身的 `self._reads` 决定是否把它暴露给 Modifier，未声明则传 `None`」的**唯一合法实现形态就是骨架里的 `_gated_ctx`**——**派生**一份 ctx 后交给 Modifier，**严禁就地改写 `ctx.external`**。理由是 `PityEngine` 每次调用只构造一个 ctx 并在同池全部保底间复用（[pity.py:1274-1300](gacha_simulator/core/pity.py#L1274-L1300)），就地置 `None` 会污染同池其他保底。两处配套（原稿均缺）：① §七 **S9-2** 明确承接这段门控代码（原稿 S9-2 只列字段 / 解析 / 透传 / `get_reads_for_pool`，全计划无任何子块写出该门控的形态）；② §六 补「**同池一条声明 `reads`、一条不声明**」的对照断言——原稿 G3 用例是单保底池，污染在该形态下不可见。

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-2 -->
**骨架形参与 `create_behavior` 两处注入点的接口对齐（AUDIT-BREAK-2，强制，⚠ 待人工裁决：备选方案见末条）**

问题：`create_behavior` 现有两条注入——`if getattr(pdef,'target_featured',False): params['target_featured']=True`（[pity.py:875-876](gacha_simulator/core/pity.py#L875-L876)）与 `if getattr(pdef,'reset',None): params['reset']=pdef.reset`（[pity.py:877-878](gacha_simulator/core/pity.py#L877-L878)），末行以 `cls(name=…, state=…, scope=…, **params)`（[pity.py:900](gacha_simulator/core/pity.py#L900)）落构造。本骨架的 `Pity.__init__` 是 keyword-only 且**不含 `target_featured` / `reset` 形参**，preset 分支若沿同一调用形式即 `TypeError: unexpected keyword argument`——而该异常恰好被 S4-5 的构造兜底包住（§3.1 附近的 `try/except` → 改抛 `ConfigError` 前为 `logger.warning` 后跳过），后果是**保底静默缺失**而非崩溃，与 ISSUE-204 同一失效面。<!-- REVIEW-R1-FIX: ISSUE-002 --> <!-- REVIEW-R1-FIX: ISSUE-951 -->

定稿（保守方案 = 分支隔离，不改骨架签名）：

1. **preset 分支不得走 `cls(**params)`**。两处注入**只服务于旧类兼容分支**——旧基类 `CounterBasedBehavior.__init__` 有 `reset` / `target_featured` 形参（[pity.py:123](gacha_simulator/core/pity.py#L123)），preset 分支按 §3.2 的「三必需键 + 两可选键」显式构造，**不传 `params`**（§3.2 已补构造代码与键集校验）。<!-- REVIEW-R1-FIX: ISSUE-002 -->
2. **这两个配置值在 preset 路径的消费点在工厂内部**（**逐字段核对，2026-09-30 修正**）：
   - `reset` → `CounterTracker(reset_on=pdef.reset or _norm_scope(pdef))`（§3.2 取值来源表）。**该字段确有承接，删除注入不丢能力。**
   - `target_featured` → **原稿只写了「决定 `judge="featured"`（§3.2 rotating 行）」，对 `hard` 不成立**（见下方 ISSUE-403 专段）。**2026-10-09 按裁决 7B 收窄（ISSUE-002）**：原稿在此并列的「三个 counter 驱动 soft 类型」已不再消费该字段（`soft_*` + `target_featured = true` 抛 `ConfigError`），消费面只剩 `hard` 一族。`judge="featured"` 是 `FlagTracker` 的**命中判定**（rotating 族的翻转条件），与 `target_featured` 的**目标集收窄**是两件事；旧实现里后者由 `HardPityBehavior._compute_probabilities` / `SoftStepBehavior._compute_probabilities` 消费（`target_slots = featured_slots if self._target_featured else scope_slots`，[pity.py:286-289](gacha_simulator/core/pity.py#L286-L289) / [pity.py:374-377](gacha_simulator/core/pity.py#L374-L377)）。**该消费点必须由 preset 工厂显式承接**（承接形态见下方专段与 §3.2 取值来源表），否则「删除注入」会丢能力。**原稿「故『删除注入』不丢能力，语义完全由工厂承接」的表述已按字段逐条重述**：对 `reset` 成立，对 `target_featured` 只在补上专段的承接后才成立。<!-- REVIEW-R1-FIX: ISSUE-002 -->
3. **旧类兼容分支与其 `params` 组装段随「发布前一次性移除旧类」一并删除**（GATE-5 末条）；届时 `params` dict 整体消失，本条的接口面收窄为「preset 分支唯一构造点」。S4-1 落地时须在两处注入外加注释标明「仅旧类分支」，避免后来者按 `cls(**params)` 复制到 preset 分支。
4. **§六 断言行**（已补）：preset 化的 type 经 `create_behavior(PityDef(name='x', btype='hard', reset='never'), state)` 返回 `Pity` 且**不抛 TypeError**；断言 `Pity.__init__` 不接受 `target_featured` / `reset`（`inspect.signature` 检查），使「有人把注入点接回 preset 分支」在测试期即失败。

<!-- REVIEW-R1-FIX: ISSUE-403 -->
**`target_featured` 在 preset 路径的承接（ISSUE-403，2026-09-30 独立复核补，强制）**

问题：`judge="featured"` **不能**代替 `target_featured`——前者是 rotating 族 `FlagTracker` 的**命中判定**（决定 `guaranteed` 何时翻转），后者是**目标集收窄**。旧实现中消费后者的是 `HardPityBehavior._compute_probabilities`（[pity.py:374-377](gacha_simulator/core/pity.py#L374-L377)）与 `SoftStepBehavior._compute_probabilities`（[pity.py:286-289](gacha_simulator/core/pity.py#L286-L289)）：<!-- REVIEW-R1-FIX: ISSUE-002 -->

```python
if self._target_featured:
    target_slots = ctx.draw.featured_slots.get(self._scope, scope_slots)   # ← 无 featured 槽时回退全部 scope 槽
else:
    target_slots = scope_slots
```

`create_behavior` 把 `pdef.target_featured` 注入这两个类的 `params`（[pity.py:875-876](gacha_simulator/core/pity.py#L875-L876)），而 preset 路径按本条**不得**收该形参（`Pity.__init__` 无它），且 S8 删除 `DrawInfo.scope_slots` / `featured_slots` 后**构造期已无处可查**。故必须在 preset 工厂内显式承接，否则 `target_featured=True` 的 `hard` 与三个 counter 驱动 soft 类型的目标集由「featured 槽」扩为「scope 内全部卡」——**不报错，只静默改行为**（手册现存 **10 处配置** `target_featured = true` **+ 1 处注释提及**，10 处配置全部落在 `type = "hard"` 且全部受影响，行号清单与 §3.2.1 的查证结论同源：315 / 343 / 534 / 629 / 1393 / 1479 / 1504 / 1638 / 1648 / 1706；注释提及在手册 `:1460`）。**2026-10-09 订正（ISSUE-006）**：原写「11 处」，把注释提及一并计入，与 §3.2.1 的「共 10 处」两处计数不一致。 <!-- REVIEW-R1-FIX: ISSUE-951 -->

**承接形态（定稿，不改核心架构）**：目标集由工厂算出的**选择子**传给消费它的 Modifier，签名各加一个关键字形参 `target`（默认 `'scope'`，与旧默认一致）：

```python
def _target_of(pdef) -> str:
    """pdef.target_featured 决定目标集（ISSUE-403）——全库唯一的取值点。

    True  → 目标集 = scope 内的 featured 卡集（旧 target_slots = featured_slots）
    False → 目标集 = scope 内全部卡（旧 target_slots = scope_slots）
    缺省同 False（PityDef.target_featured 默认 False）。
    **空 featured 集必须回退 scope 全集**（对齐旧的 .get(scope, scope_slots)）：
    目标集 = ctx.draw.featured_cards.get(scope) or ctx.draw.scope_cards.get(scope, ())
    缺这条回退，无 featured 卡的池在 target_featured=True 下会退化为恒等（旧实现回退全部 scope 槽）。
    """
    return 'featured' if getattr(pdef, 'target_featured', False) else 'scope'
```

| Modifier | 新签名 | `target` 的消费方式 |
|----------|--------|-------------------|
| `HardModifier`（hard，F 语义；**ISSUE-002：类名按 §3.1.2 定稿，`ThresholdForceModifier` 已废**） | `HardModifier(scope, threshold=τ, target='scope')` | 目标集 = `featured_cards` / `scope_cards`（按上表回退），F 语义（§3.14.3）不变，只换目标集 |
| ~~`SoftModifier` / `BoostModifier`（soft，B 语义）~~ | **不消费 `target`**（**裁决 7B，2026-10-05**）：`soft_*` + `target_featured = true` 由 `create_behavior` 抛 `ConfigError`，该字段在 soft 侧无消费路径；软保底构造形参一律为 `SoftModifier(scope, deltas=…)`（类名按 §3.1.2 定稿） | — |
| ~~`BaseRatioModifier`~~ | **已删除**（§3.1.2 映射表：转移量为 0，恒等） | 旧实现该分支不看 `target_featured` |

**消费面只有 `hard`（2026-10-09 订正，ISSUE-002）**：收窄前本条曾把三个 counter 驱动 soft 类型列为消费者（旧 `SoftStepBehavior._compute_probabilities` 确读该字段，[pity.py:286-289](gacha_simulator/core/pity.py#L286-L289)），但裁决 7B 已把该形态从配置面移除，故 `_preset_soft_step` **不写 `target=`**——否则 7B 的硬拒面与 `_target_of` 的消费者清单互相矛盾（按计划验收 ⇒ 必红，按 7B 施工 ⇒ 该验收项不可执行）。

**三处配套（缺一则本条无效）**：① §3.2 取值来源表补 `target_featured` 行、`_preset_hard` 与 preset 表的 `hard` 行同步写 `target=_target_of(pdef)`；② §3.1.2 表与 §3.14.2 表的对应行的签名回写为定稿形态；③ §六 / §七 S5b 补「`target_featured=True` 的 `hard` 与旧类逐场一致（含『该 scope 无 featured 卡』的空集回退用例）」的等价性用例，**同批补一条 7B 硬拒用例**（`soft_*` + `target_featured=true` 经 `create_behavior` 抛 `ConfigError`）——**原稿该字段无任何等价性用例，缺陷在验收盲区**；原稿要求的「三个 counter 驱动 soft 的等价性用例」已按 7B 改为硬拒用例（见 §六 ISSUE-403 条与 §七 S5b）。

**⚠ 待人工裁决（备选，未采用）**：在 `Pity.__init__` 保留 `target_featured: bool = False` / `reset: Optional[str] = None` 两个形参并吸收注入。否决理由：① `reset` 在 Tracker/Modifier 分解后已无骨架级语义（重置规则属 `CounterTracker.reset_on`），保留即「收了不用的死形参」；② `target_featured` **确有下游语义**（ISSUE-403 的目标集收窄），但骨架拿到该值后仍须转交 Modifier，等于多一层无收益的转手，且与本条要求的「目标集由工厂算选择子」相比只增加一处状态分布面。两者均与 ISSUE-030「逐条可配值一律取自 `pdef`、由工厂消费」的口径冲突。**注意：原稿此处的理由「featured 判定属 `judge`」对 `target_featured` 不成立**（ISSUE-403 已证 `judge="featured"` 是命中判定、不是目标集收窄），故本条只否决「把该值塞进 `Pity` 形参」，**不否决该字段本身**——承接形态见上方 ISSUE-403 专段。若人工改选本备选，须同步 §3.2 取值来源表与 S4-2 的构造代码，并保留 ISSUE-403 专段的空集回退纪律。

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-3 -->
**preset 返回 dict 的键集与其消费者（AUDIT-BREAK-3，强制，⚠ 待人工裁决：备选方案见末条）**

原稿缺陷：§3.2 / §3.3 / §3.14.2 的 preset 示例返回含 `flags={...}` / `counters={...}`（[行 693](#)/[706](#)/[720](#)/[763](#)/[1402](#)），但 `Pity.__init__` 无对应形参、全计划也**无任何声明的消费者**——原样 `**preset` 展开即 `TypeError`；不展开则两键成死代码，并与 `_build_pity_state_init` 并存为**第二初始值机制**。更隐蔽的是：S4-2 的验收断言是 `{'trackers','modifiers','lifecycle'} <= set(x)` 的**子集**判断（§七），不拒绝多余键，故该缺陷在 S4-2 / S4-3 的验收命令下**完全不可见**。

定稿（保守方案 = 保留键 + 就地定义消费者，与「初值走状态声明（H2）」的原设计一致）：

1. **键集 = 恰好 5 键**：`trackers` / `modifiers` / `lifecycle`（**必需**）+ `flags` / `counters`（**可选**，缺省 `{}`）。§3.2 的示例代码保持原样（`flags={"guaranteed": pdef.guaranteed_init}` 等），不再删除——它们的消费者就是本骨架新增的 `flags` / `counters` 形参。
2. **消费者 = `Pity.__init__` 的 `flags` / `counters` 形参**（本骨架代码已写入），构造期按 **L4 truthy 规则**写入 `state`（仅 truthy 才 `state.set`），与 `_build_pity_state_init` 的 `if cv:` 口径同源、幂等同值。
3. **构造形式 = 按名取键，禁止 `**` 直展开**（S4-1 落地）：`create_behavior` 从 preset 返回 dict 中显式取这 5 个键传给 `Pity`，**未声明的键抛 `ConfigError`**。这条同时是防「未来新增键静默成死代码」的闸门——它与同段的**缺 `lifecycle` 键校验**（ISSUE-301）是**两道互补的**运行期**校验**：本项查多（未知键）、那一项查漏（必需键缺）。<!-- REVIEW-R1-FIX: ISSUE-405 --> **导入期的 `_validate_registry()` 不参与任何键集校验**（只判 `preset` 可调用，见 §3.2 首段，ISSUE-405）。
4. **验收口径修正**（§七 S4-2 / S4-3 与 §六 已同步）：断言由子集判断改为**恰好键集** `set(x) == {'trackers','modifiers','lifecycle','flags','counters'}`（缺省时后两键可以是缺省而非显式空 dict，故实现可写 `{'trackers','modifiers','lifecycle'} <= set(x) <= 五键全集`），并**追加一条消费者断言**：`guaranteed_init=True` / `counter_init=5` 的配置经 preset 构造后，`state.get(name,'guaranteed')` / `state.get(name,'counter')` 已按 truthy 规则写入（否则「声明了初值但没人读」这一失效模式仍然不可见）。

**⚠ 待人工裁决（备选，未采用）**：删除 preset 返回 dict 的 `flags` / `counters` 两键，初值一律由 `CounterTracker(init=…)` 承载、`guaranteed` 初值改由 `FlagTracker` 加 `init=` 形参承载。否决理由：`FlagTracker` 定稿签名是四参 `(judge, hit, miss, flag)`（§3.1.1 ISSUE-104），加 `init=` 属签名扩张；且 §3.1.1 已把「初值」定义为**状态声明**而非 Tracker 形参（`_preset_rotating` 的注释「初值走状态声明（H2），不加 Tracker 形参」即此意）。若人工改选本备选，须同步 §3.1.1 的 Tracker 签名表、§3.2 的三个示例与取值来源表。

### 3.1.5 形式化：表达力与顺序判据（2026-10-08 增量版重写）

> **本节定位**：描述 **S8 完成后**架构的数学形态（卡级分布 + 增量向量）。S1–S5 期间的 Modifier 内部实现沿用槽位法（与旧类逐位一致，等价性由 §六 实测保证）；S8 把算子实现切换为增量法后，本节直接覆盖实现。
>
> **重写理由（2026-10-08）**：本节原为**乘性因子版**（2026-09-21 重写）。2026-10-08 用户裁决把表示由因子向量改为增量向量，理由是增量是更本原的形式（§2.1 的转移定义 `δ = t(u_A − u_Q)` 本就是增量）、表达力严格更强（常数因子是它的特例，反之不成立）、且能消掉一批边界特判。完整依据与改写面见《保底算子表示切换·因子向量转增量向量·改写方案》。
>
> **保留的结论**：可交换性判据仍压缩为一条复合律加一条吸收引理，只是判据对象由「因子乘积」改为「增量和」。

#### 3.1.5.1 定义：增量算子

一次抽卡有 n 个互斥结果（实现里即池中的卡，或等价地槽位）。所有概率分布构成单纯形

```
Δⁿ⁻¹ = { p ∈ Rⁿ : pᵢ ≥ 0, Σᵢ pᵢ = 1 }
```

**增量算子**由一个增量向量 δ ∈ Rⁿ 定义：

```
Ψ_δ(p) = (p + δ) / Σ(p + δ)
```

即「逐元素加增量，再归一化」。它把「概率操作」从『分布到分布的任意映射』收缩为『用一个向量平移分布』，这是本节全部论证的基础。

**性质 1（平移）**：`Ψ_δ` 在 p 坐标下就是平移 `p ↦ p + δ` 再归一化。转移族的 δ 在 U 内配平（`Σδ = 0`），此时 `Σ(p + δ) = 1`，归一化退化为恒等。<!-- P64-S8-CLOSURE -->**位级口径订正（2026-10-14，S8-5 审查实测）**：`Σδ = 0` 只在 **A 与 Q 各为单卡**时位级成立；**多卡组下**实测 `Σδ = 1.665e-16`、`Σ(p + δ) = 1.0000000000000002`，归一化**仍会执行**并把每张卡（含 U 外）缩放约 1 ULP。该缩放**无语义内容**（量级 1 ULP），但「U 外的卡逐位不变」这一表述**不成立**，详见 §3.9.5 第 6 行的订正。这条性质在 §3.1.5.2 与 §3.1.5.3 被直接使用。

**性质 2（与因子表示的关系）**：乘性因子是增量在「配平且 `m` 在 A / Q 内各自为常数」时的特例。此时 `δ_c = p_c(m_c − 1)`，两者逐点等价（三案推演 §2.4 的证明）；反之不成立，增量能表达因子表达不了的「把质量搬到零概率结果上」。

**性质 3（良定义条件）**：`Σ(p + δ) > 0`，且逐元素需 `p_c + δ_c ≥ 0`（否则产出负概率）。**注意这是值依赖约束**（因子表示的 `m ≥ 0` 是类型级约束，与 `p` 无关，这是换成增量付出的代价，见改写方案 §0.3）；对转移族它退化为单个标量 `amount ≤ p(Q)`，见 §3.9.4。这是本形式化唯一的边界来源，见 3.1.5.6。

#### 3.1.5.2 操作模型：增量向量与「A 加 Q 减」族

> **本节经 2026-10-05、2026-10-06、2026-10-08 三轮用户裁决重写。** 原「三个基本算子 R/F/B」与其次的「(全域 U、目标组 T、运算) 三元组」两版表述**均作废**；2026-10-08 又把表示由因子改为增量。

**Modifier 的定义只有一条**：给定 `(view, dist, ctx)`，返回**增量向量** `{card_id: δ}`；未列出的卡 `δ = 0`；`None` 表示恒等。框架逐元素相加后统一归一化。

```
Ψ_δ(p) = (p + δ) / Σ(p + δ)
```

**这是接口，不是实现约束。** 增量向量可以是任意形状：逐卡不同、只覆盖一部分卡、不配平（`Σ(p + δ) ≠ 1`）都合法。**归一化由框架承担，对任意形状都正确。**

##### 3.1.5.2.1 当前七个机制所属的一族：「A 加 Q 减」

七个机制恰好都能写成同一个形状：

```
A 内每卡  + amount · u_A(c)
Q 内每卡  − amount · p_c / p(Q)
其余      不写（= 0）
```

`amount` 是从 Q 搬到 A 的概率质量；`u_A` 是 A 上的单位分布（即「形状」），取值由 §3.9.4 的 `shape` 参数决定（七个机制中**三个**取 `'current'`，即 `u_A(c) = p_c / p(A)`；**四个**取 `'declared'`，即 `u_A(c) = w_c / w(A)`（**计数订正（S9-3，2026-10-14）**：`NotOwnedModifier` 随 F7 裁决取 `declared`），见 §3.1.2 表的「A 侧形状」列）。两种形状都在 U 内**配平**（`Σδ = 0`），故 `Σ(p + δ) = 1`，归一化退化为恒等。

**这不是定义，是一个族。** 三条前提都不是「Modifier 必须如此」：

| 前提 | 当前七个机制 | 若不满足 |
|------|-------------|---------|
| 恰好两个组 | 满足 | 直接写自定义增量表 |
| A 内形状规则统一 | 满足（`current` 或 `declared` 二选一） | 同上 |
| 配平（`Σδ = 0`） | 满足 | 同上；框架归一化会真的干活 |

**因此 `transfer_linear(dist, A, Q, amount, shape='current')` 是助手函数，不是接口的一部分**（§3.9.4）。新机制若不属于该族，直接实现 `compute_delta()` 即可，**接口不变**。<!-- P64-S8-LANDED -->
> **签名与归属的两点补充（2026-10-14，S8 落地）**：① 实际签名为 `transfer_linear(dist, A, Q, amount, shape='current', weights=None)`，本行写法漏了 `weights`（`shape='declared'` 时必传，§3.9.4）。② 它是 **S8 新增**的函数，住叶子层 `pity_primitives.py`，与**保留在 `pity.py` 的 `_redistribute_scope` 并存**到 GATE-5 末条「发布前一次性移除旧保底类」的 commit（ISSUE-502）：后者仍被 4 处旧类调用点依赖，不得提前删除。

##### 3.1.5.2.2 `amount` 的两种取法

| 取法 | 用于 | 语义 |
|------|------|------|
| `amount = p(Q)` | hard / rotating / targeted / G1 / G3 | 源组**全部**搬走（夺取型） |
| `amount = boost%(counter) / 100` | soft | 目标组概率**增加 boost 个百分点**（软保底） |

`amount` 是 `compute_delta()` 内的**局部量**：不是构造形参、不进接口、不在设计表里占一列。soft 的 `boost%` 由 `deltas` 经 `_cumulative_boost` 得出（§3.4.1）。

##### 3.1.5.2.3 与旧槽位级实现的对应

| 旧名 | 本族对应 |
|------|---------|
| `R_r(T)` | 夺取型：A = T，Q = scope − T，`amount = p(Q)` |
| `F(T)` | 夺取型：A = T，Q = 全池减 A 再减更高稀有度，`amount = p(Q)` |
| `B_β(T; Q)` | soft 型：A = T，Q = 源集。**改前实现取 `amount = β·p(Q)`（相对量）**（2026-10-06 前）；**改后已按修正 ① 改为绝对百分点**（`amount = boost/100`，见 §3.1.5.2.2）——**该修正已落地于 `SoftStepBehavior`，不是待办**（§3.4.1）。这一口径差异正是 §3.1.5.5 推论表「soft + soft（异 scope）」由可交换变为不可交换的原因 |

旧实现跑在**槽位级**。<!-- P64-S8-LANDED -->~~目标恒为单槽~~ **该半句经实测为假（订正，2026-10-14）**：旧实现取 `target_slots = scope_slots[scope]`（[pity.py:436](gacha_simulator/core/pity.py#L436)），同一 scope 内含**多个槽**（如 `ssr_featured` 与 `ssr`），且目标槽位概率按 `w_s / Σw`（**声明权重**）分配，故「A 内按什么分」在旧实现里**已有规则**。S8 降到卡级后 |A| 可大于 1，问题变成「**哪一种分法对**」，两者分岔的实测见 §六 差异清单的 (g) 项。**本族的答案是：A 内形状由机制声明**（§3.1.2 的「A 侧形状」列；**三个**取 `current` 即保持当前比例，**四个**取 `declared` 即按声明权重（**计数订正（S9-3，2026-10-14）**：随 F7 裁决反转）），依据见 §3.1.5.4 的表与三案推演 §8.4 的穷举。

##### 3.1.5.2.4 本轮修正的两处实现错误（2026-10-05）

| # | 位置 | 错在哪 | 正确形态 | 数值后果 |
|---|------|-------|---------|---------|
| ① | 原 `factor_override` | T 的因子写成 `w_c`，等于把目标值算成了 `∝ w_c·p_c` | 本族无此形态：A 内按当前形状分配 | 组内比例平方放大：基础 3:1 变 9:1 |
| ② | 原 `BoostModifier` 的 U | 写成 scope，soft 退化为**组内换位** | Q = 更低稀有度（§3.1.2 表第 3 行） | **soft 整体不生效**：SSR 总率不变 |

两处都是**槽位级公式直接升到卡级**的产物。**① 随「绝对赋值」形态的删除而消失**（本族不再有它）；**② 已按正确取法写死在 §3.1.2 的机制表里。**

> **基底的完备性**：还须计入恒等元（返回 `None`）。所有早退路径（条件不成立、`p(A) <= 0`、目标集为空等）返回的都是它。

<!-- REVIEW-R1-FIX: MODIFIER-IFACE -->

#### 3.1.5.3 复合律与顺序敏感的两类来源

**复合律**：

```
Ψ_{δ₂}(Ψ_{δ₁}(p))：先算 p₁ = Ψ_{δ₁}(p)，再算 Ψ_{δ₂}(p₁)
                  = (p₁ + δ₂(p₁)) / Σ(p₁ + δ₂(p₁))      （δ₂ 在 p₁ 处取值）
```

**判据的正确用法（2026-09-21 审查修正；2026-10-08 迁移到增量）**：可交换性**不能**由「增量是否依赖分布」直接判定：转移族的 δ 含 `p(Q)`（依赖当前分布），却与同类可交换（§3.1.5.5 推论表第 1 行）。唯一可用的判据是**逐元素比较两种顺序下的增量和**（吸收引理为其特例）。增量依赖分布只是「**可能**不可交换」的来源：它使 `δ₂` 的求值点随顺序改变，是否真的改变和须逐元素验证。

**顺序敏感的两类来源（2026-09-21 定性；2026-10-05 按裁决 6B / 7B 重写）**：

| 类型 | 例子 | 性质 |
|------|------|------|
| **约束冲突（语义）** | 两个算子对同一组给出互相矛盾的要求。**M1 实例**：`assign` 与「在 `assign` 输出上非恒等」的算子共存（如 `hard` 与 guaranteed 分支的 `rotating`）；**M2 实例**见 §3.1.5.5 的适用范围注 | **这是语义正确的表现**，不是缺陷。**M1 口径**：`assign` 是**写入**且输出与输入分布无关，故 `[X, hard] ≡ hard 的输出`，而 `[hard, X] ≡ X 作用于 hard 的输出`；两者相等**当且仅当 X 在 hard 的输出上恒等**（该判据在 M2 的夺取型 `hard` 下不成立，见 §3.1.5.5 的适用范围注）。**不是「同 U 才行」**：`soft(tf=False)` 与 `hard` 同 U 且可交换，`rotating`（非 guaranteed）与 `hard` 异 U 也可交换，而 `rotating`（guaranteed）与 `hard` 异 U **不可**交换。完整判据与逐条验算见 §3.1.5.5 |
| **随机数消费（实现）** | 含 `rotating_cr` 的配置 | 增量本身可交换，但掷骰消费全局 `random`，换序导致随机流错位。数学上若随机源独立则无影响，它只影响固定种子下的可复现性与样本路径。**这是实现绑定的副作用**。裁决 6B 把掷骰从 Modifier 移入 Tracker 后，本条**保留但降级**：Tracker 的 `prepare` 同样按行为顺序逐个调用（6B′ 把消费点定在 `before_draw` 的 `prepare`），换序仍会移动消费位置，**该方案只把它从 Modifier 层搬到 Tracker 层，并未消除**——消除它需要随机源独立，而那与「与旧类逐场一致」互斥（旧类消费的是全局 `random`），见 §3.1.1 的 CR 相位段 |

> **原「`soft(target_featured=True)` + `hard`」这一反例已不可构造（裁决 7B）**：`soft_*` 类型出现 `target_featured = true` 时按 §3.2 的取值来源表抛 `ConfigError`。其位置由「同 U 的 `share` 与 `assign` 共存」取代。P82 的修正结论「含 `rotating_cr`，或 `target_featured=True` 的 soft 与 hard 共存的配置会变」随之收窄为「**含 `rotating_cr` 的配置会变**」。<!-- REVIEW-R1-FIX: RULING-7B -->

对第一类，正规处置是**显式定义组合语义**（当前为顺序执行 + §1.5 裁决的 `priority` 覆盖），而非消除敏感。**2026-10-05 实测后补充**：第一类不是「同 U 才发生」，判据是「X 在 `assign` 的输出上是否恒等」，与 U 是否相同无关（§3.1.5.5）。另有一种理论上可行的替代语义是**约束求解**（把每个保底写成对分布的约束，求解满足全部约束的分布），它能彻底消除顺序敏感且冲突时较严约束自然胜出。

**约束化本身的成本比原稿记的低（2026-10-05 复核）**：3.1.5.2 的 `share` 形式**恰好就是约束形式**（`Σ_{c∈T} p_c = r · Σ_{c∈U} p_c`），故 6 个 `share` 机制天然可写成约束，无须改造。原稿称「带随机拦截的 `rotating_cr` 写不了」，实际是**可写但需线性组合**：CR 的每抽分布是混合 `ω · share(r=1) + (1−ω) · share(r_base)`，转约束要引入混合权重。真正的阻碍是另外两处：① `assign` 是绝对赋值而非齐次约束，写成约束要引入常数项；② 求解远比顺序应用昂贵。当前采用顺序执行是工程上的取舍，若日后要改，须先解决 ①。

#### 3.1.5.4 定理 1（表达力包含）

**命题**：在组内比例不变式

```
p_c / p(C_s) = w_c / w(C_s)      （对每个槽 s 及其卡集 C_s）
```

成立的前提下，旧 10 类的每个概率算子都等价于**转移算子**（`transfer_linear` 的「A 加 Q 减」形状，§3.1.5.2.1）的有限复合；每个状态转移 T 都是条件赋值语句的有限复合。

**证明**（构造性，2026-10-05 重写；2026-10-08 迁到增量词汇）：

| 类型 | 概率算子 | 状态转移 T |
|------|---------|-----------|
| `soft_step` | 转移（A = `scope_cards[scope]`，Q = 全池减更高，`amount = β`） | 出 scope 时 `counter ← 0` |
| `hard` | 夺取（A = `scope_cards[scope]`，Q = 全池减更高，`amount = p(Q)`），否则 `identity` | 同上 |
| `rotating` | 转移（A = `S_f`，Q = `S_c − S_f`）：`amount = p(Q)` 若 guaranteed，否则 `identity`（按当前份额，两侧增量相消） | 出 scope 时 `guaranteed ← is_featured` |
| `rotating_cr` | 拦截 ? 夺取（A = `S_f`）: 转移（按当前份额） | 父类 + 出 scope 且 ¬was_g 时 `cr ← is_featured ? 0 : cr+1`（裁决 6B 后掷骰并入本列；**2026-10-10 改判 6B′**，相位为 `prepare`） |
| `targeted` | （guaranteed 或 fate 就绪）? 夺取（A = `T_sel`）: 转移（按当前份额，A = `S_f`） | 命中定轨卡时四键清零，否则四键累积 |
| 各 `_soft` | 父算子 ∘ 转移（`amount = β`） | 父类 T 加 counter 清零 |

每个算子长度不超过 2；每个 T 只含条件赋值，无循环、无跨调用内存。

**须显式声明的让步（2026-10-05 收窄）**：原稿写「旧算子在目标组内按基础权重重写，乘性算子在目标组内按当前比例缩放」（按 2026-10-08 的增量版术语：转移族在目标组内按当前形状分配），把三处混成了一句。逐项分开后：

| 机制 | 组内分配口径 | 是否需要不变式 |
|------|-------------|---------------|
| 夺取型（hard / G3，原 `assign`） | 组间按声明权重和，组内按当前形状 | **不需要**。旧实现在槽级就写 `w_s/Σw`，卡级扩张是整槽同乘，与按当前形状分配逐位相同 |
| 目标为单槽或单卡（rotating / targeted / CR / G1） | 组内按当前形状 | **不需要**。单元素组内不存在「分配」这一层，两种口径退化为同一式子 |
| 目标**跨多个 (稀有度, featured) 组**（soft 的 `tf=False`） | 组内按当前形状 | **需要**。旧实现的增量按 `w_s/Σw` 分给 featured 与非 featured **两个槽**；不变式成立时「按声明权重加」与「按当前形状分配」同值，不成立时分开。**实测**：不变式破坏时差 1.03e-01（§3.14.3） |
| 目标落在单个 (稀有度, featured) 组内（soft 的 `tf=True`；rotating / targeted / CR / G1） | 组内按当前形状 | **不需要**。旧实现的目标槽只有一个，增量全给该槽、卡级扩张整槽同乘，比例恒保持。**实测**：不变式破坏下仍逐位一致（差 0） |

> **边界的正确表述**：需要不变式的条件是「**T 是否跨多个 (稀有度, featured) 组**」，不是「T 是整组还是单卡」。原稿按「单槽 / 整组」分档，在 `tf=True`（多张 UP 卡、跨行同组）一例上会给出错误预测。2026-10-05 实测修正。

**故本定理对「夺取型」与「单槽目标」的转移是严格包含，对 soft 是「不变式下包含」**，比原稿的「一律不变式下包含」更强。

> **`rotating_cr` 的命中分支是 `R_1` 而非 `F`**（2026-09-16 核对结论，增量版沿用）：它由 `_force_featured`（[pity.py:586-589](gacha_simulator/core/pity.py#L586-L589)）实现，内部调 `_redistribute_scope(ctx, 1.0, ...)`，只把 scope 内总量给 featured、scope 外原样保留。实测同一输入（0.5 / 0.5 / 0.08 / 0.9）下 `_force_featured` 得 {ssr_featured: 0.02, ssr: 0, sr: 0.08, r: 0.9}，`F(S_f)` 得 {ssr_featured: 1.0, ssr: 0, sr: 0, r: 0}。结论不因此改变（`R_1 ∈ {R}`），但构造表须按 `R_1` 记。

**效力**：本定理证的是**表达力包含**（存在一个 preset 表达旧行为），不保证实现出的 preset 与旧代码位级一致（浮点运算顺序差异），后者由等价性测试承担。

#### 3.1.5.5 定理 2（可交换性判据）

由 3.1.5.3 的复合律，可交换性判定归结为**逐元素比较两个顺序下的增量和**；实践中只需一条引理：

**吸收引理**：若某算子把集合 Q 搬空（夺取型，`δ_c = −p_c` 对 `c ∈ Q`），则任何**先于**它作用的算子在 Q 上留下的增量都被覆盖：复合在 Q 上的结果恒为 0，与先前算子无关，故在 Q 上可交换。

**推论表**（重算版）：

| 组合 | 可交换 | 依据 |
|------|-------|------|
| soft + soft（同 scope） | 是 | 裁决 7B 后同 scope 的两条 soft 目标集必为 scope（不再有「异目标集」这一形态），退化为同一 A 同一 Q 的两次转移：源侧增量按当前形状分配，两次在 Q 上线性叠加，可交换；复合等价于单次转移（原 `share` 语义下 `r = 1 − (1−r₁)(1−r₂)`） |
| soft + soft（异 scope） | **否**（绝对百分点语义下） | 原依据「低稀有度算子的源集与目标集都落在高稀有度算子的源集之内」只在**相对量**语义（`amount = β·p(Q)`）下成立。2026-10-05 修正 ① 把 `amount` 改为**绝对百分点**后不再成立：高稀有度算子固定搬 `b₁`，而低稀有度算子会改变前者源集中那一部分的值，两次顺序不同则前者从该部分取走的比例也不同。**手算反例（2026-10-08）**：`p = {ssr: 0.02, sr: 0.08, r: 0.90}`，`soft(ssr)` 的 boost = 5pp、`soft(sr)` 的 boost = 2pp，`[soft_ssr, soft_sr]` 得 `sr = 0.0959184`、`[soft_sr, soft_ssr]` 得 `sr = 0.0948980`，差 ≈ 1.02e-03 |
| **soft(tf=False) + hard（同 scope）** | **是（2026-10-05 实测）** | 见下方「判据」专段。实测：`soft(start=2) + hard(threshold=6)` 逐抽 1..15 无反例 |
| **hard + rotating（rotating 处于非 guaranteed 分支）** | **是（2026-10-05 实测）** | 该分支的 r = `p(S_f)/p(S_c)` 即当前份额，`share` 退化为恒等，**在任何分布上都是恒等**，故与 `hard` 可交换 |
| **hard + rotating / targeted（guaranteed 分支）** | **否（2026-10-05 实测）** | r = 1，非恒等。实测 `hard(threshold=5)` + `rotating`（第 1 抽中非 UP 的 SSR 置 guaranteed）：**抽 6 起分歧**，`[hard, rot]` = `{ssr: 0, ssr_featured: 1.0}`、`[rot, hard]` = `{ssr: 0.5556, ssr_featured: 0.4444}`。**`targeted` 的同名分支与 `rotating` 逐位相同**（直接对照三组输入，含 `hard` 的输出，差 0），故本行同时覆盖它。**裁决 7B 未消除本条**，它是 7B 之后唯一剩下的代数型反例 |
| 含 `rotating_cr` 的组合 | 否 | 非代数问题：增量本身可交换，但掷骰消费全局 `random`，换序导致 ω 消费位置改变、样本路径分叉。裁决 6B′ 后掷骰在 Tracker 的 `prepare`（`before_draw` 相位），同样按行为顺序调用，**本条结论不变** |

**判据（2026-10-05 实测归纳，取代原「逐类猜测」）**：

> **适用范围（2026-10-08 补，强制）**：本判据的立论是「`hard`（`assign`）的输出与输入分布无关」，那只成立于 **M1 的旧类**（`HardPityBehavior` 重建分布、只读 `base_probabilities`）。**S8 起 `hard` 是夺取型**（A = `scope_cards[scope]`、Q = 更低稀有度、A 侧形状 `current`，§3.1.2 表），A 内按当前比例分配，**输出依赖输入**，本判据**不再适用**，须回到上方「逐元素比较两种顺序下的增量和」的通用判据。**已知反例（手算，2026-10-08）**：池 `{ssr: 0.01, ssr_featured: 0.01, sr: 0.08, r: 0.90}`，`hard(ssr, tf=false)` 与 `rotating(guaranteed)`：两序都得 `{ssr: 0, ssr_featured: 1.0}`（**可交换**），而 `rotating` 在 `hard` 的输出 `{ssr: 0.5, ssr_featured: 0.5, sr: 0, r: 0}` 上显然非恒等，本判据会误判为「不可交换」。**下方推论表与逐条验算表均为 M1 旧类实测**，M2 口径待 §六 的「S8 可交换性复测」重算。

`hard`（`assign`）的输出**与输入分布无关**：它只读 `ctx.draw.base_probabilities`，把 U\T 置零、T 写成基础权重归一（`HardPityBehavior._compute_probabilities`，[pity.py:374-390](gacha_simulator/core/pity.py#L374-L390)，`result[s] = w / total_weight` 里的 `w` 取自 `base_probabilities` 而非 `ctx.current`）。故：

```
[X, hard]  ≡  hard 的输出                        （X 被 hard 覆盖）
[hard, X]  ≡  X 作用在 hard 的输出上
⟹  X 与 hard 可交换  ⟺  X 在「hard 的输出」这个分布上表现为恒等
```

**逐条验算**（全部与实测吻合）：

| X | X 在 hard 输出上是否恒等 | 依据 |
|---|------------------------|------|
| `soft(tf=False)` | 是 | hard 输出里 U\T 全为 0，而 soft 的源集恰为 U\T，`pool = 0` → 早退（[pity.py:307-309](gacha_simulator/core/pity.py#L307-L309)） | <!-- REVIEW-R1-FIX: ISSUE-002 -->
| `rotating`（非 guaranteed） | 是 | r = 当前份额，恒等（对任意分布成立） |
| `rotating`（guaranteed） | **否** | r = 1，把 scope 总量全给 featured |
| `soft(tf=True)` | **否** | hard 输出里 ssr（非 UP 的 SSR）= 0.5556，落在 soft 的源集内（源集 = 除目标与更高稀有度外的全体） |
| `targeted`（非 guaranteed / 非 fate-ready） | 是 | `featured_ratio = featured_total / total` 即当前份额，恒等（[pity.py:658-660](gacha_simulator/core/pity.py#L658-L660)） |
| `targeted`（guaranteed 或 fate-ready） | **否** | 与 `rotating` 的 guaranteed 分支**逐位相同**（同一式子 `_redistribute_scope(ctx, 1.0, total, <单个 featured 槽>, scope)`），在 `hard` 的输出上非恒等。**2026-10-05 直接对照实测**（三组输入含 `hard` 输出，最大差 0.00e+00） |

> **`hard + targeted` 的实测订正（2026-10-05）**：早先的引擎级探针得出「可交换」，**该结论不成立**：`TargetedBehavior` 直接继承 `PityBehavior`（[pity.py:613](gacha_simulator/core/pity.py#L613)）、不走 `CounterBasedBehavior` 的 `_active` 门控，探针里它从未进入 guaranteed / fate-ready 分支，全程落在恒等分支上，故测到的「可交换」只反映恒等分支。**改为直接对照两个 behavior 在同输入上的输出**后结论为：`targeted` 的 guaranteed 分支与 `rotating` 逐位相同，「在 `hard` 输出上非恒等」成立，**按判据 `hard + targeted` 不可交换**。<!-- REVIEW-R1-FIX: RULING-6B --><!-- REVIEW-R1-FIX: ISSUE-002 -->

**原引理 2.2 的处置**：原版那条「源集包含 + 统一缩放 + 固定权重再分配」的充分条件描述的是槽位级算子，在卡级 `share`/`assign` 下不再需要，上面的判据一行即可替代。

**原反例的复核（2026-10-05 重跑，条件与记录一致）**：原记录为 soft(`target_featured=True`，deltas 使第 6 抽起 boost) + hard(threshold=8)，两种 `pity_names` 顺序在第 8..12 抽出现分歧。**2026-10-05 用 `soft(start=2) + hard(threshold=6)` 独立重跑，得同一结论：抽 6..15 顺序敏感**（`[soft, hard]` 与 `[hard, soft]` 的 SSR 内部比例不同）。原记录**属实，不是误记**。

**该配置按裁决 7B 已不可构造**（`soft_*` 带 `target_featured = true` 抛 `ConfigError`），故这一条反例被消除。但**裁决 7B 并未消除全部代数型顺序敏感**，「`hard + rotating`（guaranteed 分支）」仍不可交换（见上表第 5 行），它是 7B 之后剩下的那一条。<!-- REVIEW-R1-FIX: RULING-7B -->

**P82 结论的最终形态（2026-10-05）**：

| 时点 | 结论 |
|------|------|
| 原始（P82） | 仅含 `rotating_cr` 的配置会变 |
| 2026-09-21 修正 | 含 `rotating_cr`，**或** `target_featured=True` 的 soft 与 hard 共存 |
| **2026-10-05 终版** | 含 `rotating_cr`，**或** `hard` 与「在 `hard` 输出上非恒等」的算子共存（当前实例：`rotating` 处于 guaranteed 分支）。原 `soft(tf=True) + hard` 一例因裁决 7B 消除 |

**本表不是全部敏感类的登记点（ISSUE-941）**：本表只收「时点 → 结论」的演化，**第 3 类（`soft + soft` 异 scope）**的判据在本节上方的「推论表」，**第 4 类（跨 type 顺序反转且存在 `depends_on`）**本节无承载行、全篇唯一实测记录在 §1.5。P82-2 的验收口径（「差异逐一归因到敏感集合」）以 §1.5 的五类清单为准，本表是其中第 1 / 2 / 5 类的依据。 <!-- REVIEW-R1-FIX: ISSUE-941 -->

**本条的时点敏感须注意**：2026-10-05 的上一版计划曾把结论写成「收窄回『含 `rotating_cr` 的配置会变』」，那是在 `hard + rotating` **尚未实测**时的推断；实测证明该推断不成立（见「判据」专段）。

**原引理 2.3 的处置**：原版引理 2.3 称「在当前槽位结构下，参数取『保持当前比例』的 `R` 是恒等映射，原因是单槽位使组内重写退化」。卡级增量版下该引理**不再需要**：转移族的 δ 在 A 内、Q 内各自按当前形状给出，当取「当前比例」时两侧增量恰好抵消（`δ_c = 0`），恒等性直接读出，无须借助槽位结构。**本节的判据表正是该性质的推广**（`rotating` 非 guaranteed 分支即「按当前份额」这一特例）。

#### 3.1.5.6 未覆盖（边界）

| 项 | 为何只能测 / 说明 |
|----|-----------|
| 位级一致 | 定理 1 保证构造存在，不保证浮点运算顺序一致；卡级管道下聚合次数随算子数增加，差异量级仍在 1e-16，但 §六 的等价性口径须由「完全一致」放宽为「容差内一致」。**2026-10-11 由 S5a 实测落地**：差异来源是新 `RotatingModifier` / `SelectedModifier` 条件不成立时直接返回恒等、旧类走 `_redistribute_scope` 的除再乘往返；量的上界 1.11e-16（九种池形状扫描），且**依赖基础概率的位模式**（0.2/0.2 形状下 28 抽里 23 抽不等、恰 1 ULP；0.006/0.004 与 0.005/0.005 为精确零差）。§六 S1–S5 口径已按本行拆为「分布容差 1e-12 + 状态位级一致」，落点 `tests/core/test_pity_equivalence.py` 的 `Tolerance` / `SnapshotPolicy` 显式参数 |
| 随机数消费次数 | 可证，但需先把 H4 的短路条件写死，再把 ω 显式化为消费序列逐位比对 |
| 全配置组合 | 组合空间过大，采样测试只覆盖有限点；本节的判据用于缩小「必须实测」的范围 |
| **无货可取（`p(Q) = 0`）** | 由性质 3，此时转移无源。语义上这是「无源可搬」，物理上不应发生（保底不作用于零概率组）。实现约定：返回 `None`，与现行早退路径一致 |
| **`p(A) = 0`（目标组当前无概率）** | `shape = 'current'` 下 `u_A = p_c/p(A)` 除零**发散**（因子写法下更甚：`(p(A)+amount)/p(A)` 取 ∞）。**2026-10-08 已裁决**：返回 `None`（恒等，不转移），见 §3.9.5 第 1 行。可达性与语义分析见下方 §3.1.5.6.1 |
| **`Q` 为空**（无源组） | 转移无货可取，返回 `None`。**2026-10-08 补**：增量形式下该情形由 `p(Q) = 0` 一行涵盖（Q 为空时 `p(Q) = 0` 恒成立），无独立条目 |
| **`A ⊄ U`**（目标解析器返回了作用域外的卡） | 转移的推导依赖 `A ⊆ U`（源侧为显式传入的 Q，须与 A 不交）。目标解析器返回的 A 若含 U 外的卡，那些卡不会被写到，其增量保持 0，但语义上等于该卡「既被指定为目标又不在作用域内」。**构造期须校验 `A ⊆ U` 并抛 `ConfigError`**，不得静默忽略 |
| 约束求解语义 | 3.1.5.3 提到的替代组合语义未实现；其可行性复核见 3.1.5.3 末段（`share` 天然是约束形式，阻碍在 `assign` 的常数项与求解成本） |

##### 3.1.5.6.1 `p(A) = 0` 边界的可达性实测与裁决（2026-10-06 实测 / 2026-10-08 裁决）

**可达性：可达，且有两条来源（2026-10-06 实测；首版结论「唯一路径」已更正）。** 实测方法：把 `SoftStepBehavior._compute_probabilities` 的守卫临时改为 `raise`（直接命中真实代码路径，不重写逻辑），跑真实模拟（`fixed_count`，100 抽）。

| 路线 | 结果 |
|------|------|
| `hard(scope='sr')` → `soft(scope='ssr')` | **不可达**：`hard` 对**更高稀有度豁免**（只清零更低稀有度），SSR 保留原概率，`target_total > 0` |
| `hard(scope='ssr')` → `soft(scope='sr')` | **不可达**：前一道 **`pool <= 0`** 守卫先命中（实测以该守卫为探针得到 `POOL_ZERO`） |
| 池中某稀有度的卡声明 `probability = 0.0`，`soft(scope=该稀有度)` | **可达**（来源一） |
| **`hard(scope='ssr')` → `hard(scope='r')` → `soft(scope='sr')`** | **可达**（来源二），**且全部声明概率为正** |

来源二的机理：`hard` 清零后把**更高稀有度还原为当前值**（[pity.py:381-395](gacha_simulator/core/pity.py#L381-L395) 的层级保护）。故 `hard(ssr)` 后 `SSR=1.0`、其余 0；`hard(r)` 再把 R 写为 1.0 并还原更高者（SSR 还原为 1.0、SR 仍为 0）→ `SSR=1.0 / SR=0 / R=1.0`，`Σ = 2.0`。此时 `soft(sr)` 的 `target_total = 0` 而 `pool = 1.0`，守卫命中。该组合合法（`_validate_behaviors` 只禁同 scope 的两个硬保底），但**它已经落在本计划登记过的「造质量」边界里**（§3.1.5.2 边界一：旧实现靠「绝对赋值 + 更高稀有度豁免」造出 `Σ > 1`）。

**两条来源的语义相反，而守卫分不清。** 这是本项的要害：

| 来源 | 目标组为 0 的原因 | 「不转移」对不对 |
|------|-----------------|----------------|
| 一 | 池子自己声明该稀有度不可获得 | **对**：抬起来与池子的声明冲突 |
| 二 | 被另一条保底清零 | **错**：`soft` 本就该把它抬起来，现在被静默吃掉 |

故「确保所有『先 0 后有』都不合理」这一前提**不成立**：来源二是合理的。由此：

- **堵输入堵不住**：拒绝 `probability <= 0` 只消灭来源一，来源二全用正概率（2026-10-06 实测）。
- **要堵来源二就得禁「会造质量的组合」**（两条不同 scope 的 `hard` 同时触发），那是比本项大得多的边界问题（§3.1.5.2 边界一已登记 `hard(scope=最低稀有度)` 的同类现象）。
- **把守卫改响亮**只是把「静默不生效」换成「报错不生效」，`soft` 仍然没抬起来。
- 唯一让来源二**正确生效**的路子是让形式化能表达「从 0 抬起」，即下方「乙案（加法）」或「丙案（绝对写入通道）」。

**已裁决（2026-10-08）：换增量，且 `p(A) = 0` 仍处置为「不转移」。**

原「形式化待决」列了四条候选（甲不动 / 乙全局换加法 / 丙混合通道 / 丁堵输入）。2026-10-08 用户裁决走**换增量**，但它与乙案不完全等同，两点须分清：

- **换增量的直接动机是消除转写层与一批边界特判**（§3.9.5 的「⟨m,p⟩ ≠ 1」一条随之消失），**不是**专门为 `p(A) = 0` 而换。**ISSUE-011 / ISSUE-903 的 M1 与 M2 的 `Σp` 口径分歧不受影响**（M1 沿用旧实现、F 型豁免更高稀有度、输出 Σ = 1.009；M2 框架无条件归一化、输出 Σ = 1；成因是两期的 hard 语义与归一化时机不同，与表示无关）
- **`p(A) = 0` 本身仍处置为「不转移」**：`shape = 'current'` 下 `u_A` 无定义，返回 `None`。这是来源一（池子声明不可获得）的正确行为。原候选表里「乙 / 丙 能让来源二生效」这一点，在裁决后由 `shape = 'declared'` 落地（2026-10-08 启用，见下）

**来源二在新框架下的可达性（2026-10-08 重新穷举）**：原实测的 `hard → hard → soft` 链依赖旧 `hard` 的「造质量」（`Σ = 2.0`），而新 `hard` 是夺取型、`⟨m,p⟩ ≡ 1`，且 `hard(scope=最低稀有度)` 的 Q 为空会空转（§3.1.2 边界一），故该链**不可达**。但另一条链**可达**：`NF(ssr)` / `Sel(ssr)` 清空 UP 之后 `H_tfT(ssr)` 要保 UP，此时 `p(A) = 0` 而 `p(Q) > 0`。这类组合全部是语义对撞（夺 UP 与保 UP），穷举结果见三案推演 §8.4 与 `.recycle_bin/probe_pA0_reach.py`。

**`shape = 'declared'` 已启用（2026-10-08 用户裁决）**：按声明权重分配对 `p_c = 0` 安全（`δ_c = t·w_c/w(A)` 不依赖 `p_c`），故 `HardModifier(target_featured=true)` / `NonFeaturedModifier` / `SelectedModifier` / `NotOwnedModifier` **四个**机制取它（**计数订正（S9-3，2026-10-14）**：末者随 F7 裁决加入）（§3.1.2 表的「A 侧形状」列），来源二在冲突配置下由此生效。`w` 取自 `ctx.base_probabilities`（2026-10-08 新增的 `ctx` 字段；它归一化后就是初始分布，见 §3.1.2 的字段表）。其余四个机制仍取 `current`。

**三条「支持换加法」的实测事实的现状**（2026-10-08 复核）：

- ① 原「性质 1（对数坐标 / 指数族）」全文档只出现一次：**随增量版重写而消失**。新性质 1（平移）在 §3.1.5.2 与 §3.1.5.3 被直接使用
- ② 本族配平、乘性机器从未真正跑过：**仍成立**，且是换增量的理由之一
- ③ `amount` 已是绝对百分点语义、因子是从绝对量反推的派生量：**仍成立**，换增量后推演公式与实现同形，这层转写消失

**代价已如实记账**（改写方案 §0.3）：J4 由类型级降为值依赖（转移族退化为 `amount ≤ p(Q)` 一个标量）；**顺序敏感不消失**，`δ` 仍通过 `p(Q)` 依赖当前分布，§3.1.5.3 的分析长度不变。

**前置欠账的部分清偿**：本节原文末条记「§3.1.5.3 / .4 / .5、§3.9.3 / .5 仍写在作废的 `share` / `assign` / `(U, T, 运算)` 词汇里」。2026-10-08 这轮已把 §3.1.5.1–.6 与 §3.9.2 / .3 / .4 / .5 迁到增量词汇（§3.1.5.4 的构造表与让步表、§3.9.3 的组件处置表均已处理）。**仍带旧词汇的是 §3.1.1（`rotating_cr` 的 `share` + `FlagCondition` 描述）、§3.1.5.3（顺序敏感表与约束化讨论）、§3.1.5.5（推论表与判据专段）、§3.2.1（soft 的两步分解）**，它们多为 M1 旧类实测或历史记录，已按标注保留。

<!-- REVIEW-FIX-PREV: ISSUE-002 -->
#### 3.1.6 模块归属与依赖方向（ISSUE-002，强制）

**两个**新模块（`pity_tracker.py` / `pity_modifier.py`；**2026-10-06 随 §3.14 改判：原列出的第三个模块 `pity_condition.py` 与其 Condition 类族一并不存在**，与 §四 的「不新增」行、§3.14.2 的「随之删除的符号」同口径；**GATE-check-2，2026-10-09 修正**）必须消费 `Counter` / `Flag`（[pity.py:41-79](gacha_simulator/core/pity.py#L41-L79)）、`PityState`（[pity.py:1083](gacha_simulator/core/pity.py#L1083)）、`PityContext` / `DrawInfo`（[pity.py:31](gacha_simulator/core/pity.py#L31) / [pity.py:14](gacha_simulator/core/pity.py#L14)）、`LifecycleConfig`（[pity.py:80](gacha_simulator/core/pity.py#L80)）；而 `pity.py` 又必须反向依赖新模块（Pity 骨架、preset 工厂、registry 条目、`create_behavior` 双路径）。**直接的双向模块级 import 会构成循环导入**，故指定依赖方向如下（否则 S1 一开工就要临场改架构）：<!-- REVIEW-R1-FIX: ISSUE-002 -->

| 层 | 模块 | 承载 | 依赖方向 |
|----|------|------|---------|
| **叶子（原语层）** | `core/pity_primitives.py`（**新增**） | `Counter` / `Flag` / `PityState` / `DrawInfo` / `PityContext` / `LifecycleConfig` + **助手函数 `transfer_linear`**（§3.9.4；**2026-10-06 改**：原 `factor_redistribute` / `factor_override` 两个「卡级原语」已合并为它，定位由「原语」降为「助手」；**2026-10-08 改**：由因子版改为增量版，加 `shape` 形参）+ **类型集合常量 `_SOFT_TYPES` / `_HARD_TYPES` / `_EVENT_DRIVEN_TYPES`**（ISSUE-024：自 `CounterBasedBehavior` 的类属性升为模块级常量，供 §3.1.4 骨架的 `Pity` 使用；**ISSUE-105：`_EVENT_DRIVEN_TYPES` 的内容须追加 `rotating_inverse`，不是原样迁移**） | 仅依赖标准库 | <!-- REVIEW-FIX-PREV: ISSUE-024 -->
| 实现层 | `core/pity_tracker.py` / `core/pity_modifier.py` | Tracker 家族 + Lifecycle / Modifier 家族（**条件内联在各机制的 `compute_delta()` 内，无独立 Condition 家族**；`pity_condition.py` 已于 2026-10-06 随 §3.14 改判取消） | **单向**依赖 `pity_primitives`，不 import `pity` | <!-- REVIEW-R1-FIX: GATE-check-2-文件清单 -->
| 编排层 | `core/pity.py` | `Pity` 骨架、`PityEngine`、`BEHAVIOR_REGISTRY`、preset 工厂、`build_lifecycle`（**ISSUE-301**：`PityDef` → Lifecycle 对象的唯一转换点，与 preset 工厂同住一处，见 §3.1.3）、`create_behavior`、`StateView`（**S3 落薄版 / S9 收紧**，定义见 §3.10.3；**ISSUE-034：本行是其归属登记**，`Pity` 骨架同住此处；~~`reads` 访问器~~（2026-10-06 取消，§3.10.2）） | 依赖 `pity_primitives` + **两个**实现层模块 | <!-- REVIEW-R1-FIX: GATE-check-2-文件清单 --> <!-- REVIEW-FIX-PREV: ISSUE-034 --> <!-- REVIEW-FIX-PREV: ISSUE-301 -->

- **S11 的校验层（`core/invariants.py`）不在上表的实现层内（ISSUE-003）**：它由**编排层单向引用**——`PityEngine(invariants=…)` 形参与两处调用点都在 `pity.py`，而 checker 自身**不 import `pity`**（`engine` / `Pity` 实例一律经实参传入），故不构成循环导入，也不改变**两个**实现层模块（`pity_tracker.py` / `pity_modifier.py`）的单向依赖方向。<!-- REVIEW-R1-FIX: ISSUE-003 --> <!-- REVIEW-R1-FIX: GATE-check-2-文件清单 -->
- **既有导入路径不变**：`pity.py` 顶部 `from .pity_primitives import Counter, Flag, PityState, DrawInfo, PityContext, LifecycleConfig`（re-export），故 `from gacha_simulator.core.pity import PityState` 等既有写法继续可用，`core/__init__.py` 的导出亦不变。这是本节与「PityState/DrawInfo/PityContext 完全保留」（§四「不受影响」）的关系：**语义与接口完全保留，仅换存放文件**。
- **`transfer_linear` 归属**：现址 `pity.py:416` 的 `_redistribute_scope` 在 S8 被**新增的** `transfer_linear` 取代为新骨架的落点（**旧函数本体保留至发布前**，ISSUE-502 / ISSUE-901；§3.9.3 / §3.9.4），而 §3.9.4 又把该函数定位为「所有组级 Modifier 的公共落点」。它住在 `pity_primitives.py`（叶子层），Modifier 层单向依赖它——**不得放在 `pity_modifier.py` 内**（否则 Tracker 侧与 `pity.py` 侧复用时会再次形成循环）。 <!-- REVIEW-R1-FIX: ISSUE-951 -->
- **过渡期（S1–S5）**：`_redistribute_scope`（槽位级）暂留 `pity.py`；**S8 只新增 `pity_primitives.transfer_linear` 并让新骨架改用它，不删旧函数本体**（ISSUE-502）。函数本体、其 4 处旧类调用点、10 个旧保底类、**以及旧类所依赖的 `PoolPitySpec` / `DrawInfo` 槽位三字段与 `compute_scope_mappings` 的槽位产出**，一律并入 GATE-5 末条「发布前一次性移除旧保底类」的同一个 commit（**ISSUE-901**；原稿「S8 一次性迁为 `factor_redistribute` 并删除旧函数」与 ISSUE-502 互斥，已改；§3.9.3 组件处置表与「跨文件同步清单」D 段为准）。
- §四的文件清单已按本条补齐 `core/pity_primitives.py`。

---

### 3.2 preset 映射（现有 10 类 → preset，含 counter 驱动统一）

<!-- REVIEW-FIX-PREV: ISSUE-015 -->
<!-- REVIEW-FIX-PREV: ISSUE-005 -->
registry（[pity.py:712](gacha_simulator/core/pity.py#L712)）条目新增 `preset` 字段（**工厂函数**），10 个条目的 `class` 字段**一律置 `None`**（ISSUE-015：原稿「条目从 class 指向 preset 工厂」与「事件驱动型置空、counter 驱动型保留旧类名」两处写法互相矛盾，且若把 `class` 指向工厂函数，[pity.py:815-832](gacha_simulator/core/pity.py#L815-L832) 的 `_validate_registry()` 在**模块导入期**即抛 `TypeError`，属全库级崩溃）。配套两处改造，并加一条**等价性装置与回滚的纪律**（见本段末，GATE-3(c) 定稿）。**落地时序（GATE-3 定稿，2026-10-01）**：`class` 置 `None` 与 `preset` 赋值**按条目原子地**在 S4-2 / S4-3 随工厂一并写入，**不在 S4-1 一次性置空**（S4-1 时 `preset` 工厂尚未定义，而 `BEHAVIOR_REGISTRY` 在导入期求值，条目既无 `preset` 又无 `class` 即导入失败）；**S4-3 收口后 10 条目一律为 `class: None` + 可调用 `preset`**。见 §七 S4-1 / S4-2 / S4-3 与 GATE-5 的 S4-1 回退面。<!-- REVIEW-R1-FIX: ISSUE-930 --><!-- REVIEW-R1-FIX: ISSUE-002 -->

- `_validate_registry()` 的校验对象由 `issubclass(cls, PityBehavior)` 改为「`preset` **可调用**」——**导入期只做可调用性判定（`callable()` / `inspect`），既不调用 preset、也不校验返回键集**（**ISSUE-405，2026-09-30 定稿**：`_validate_registry()` 的形参表为空（[pity.py:815-832](gacha_simulator/core/pity.py#L815-L832)），手上**没有 `PityDef` 实例**可传给 `preset(pdef)`；导入期真调用还会让任一 preset 体内的运行期错误（三个类型集合常量未随叶子层落地致 `NameError`、Modifier 构造签名不符致 `TypeError`）从「`PityEngine` 构造期可见」升级为**整包 `import gacha_simulator.core` 失败**）。**返回 dict 的键集校验（`lifecycle` 必需键查漏 + 未知键查多）一律在运行期由 `create_behavior` 承担**（见下段的两道 `ConfigError`；**`lifecycle` 为 ISSUE-301 新增的必需键**，理由见 §3.1.3）；**过渡判据（GATE-3 定稿）**：S4-1 落地时该判据取过渡式——「条目**含 `preset` 键则判其可调用**；**无 `preset` 键（尚未迁移）则沿用旧判据**（`class` 非 None 且为 `PityBehavior` 子类）」，使 S4-1 单独落地与 S4-2 / S4-3 的任一中间态在**导入期**都自洽；**S4-3 收口时删除「无 `preset` 键」分支**。<!-- REVIEW-R1-FIX: ISSUE-930 --><!-- REVIEW-R1-FIX: ISSUE-002 -->
- `create_behavior`（[pity.py:835-903](gacha_simulator/core/pity.py#L835-L903)）的 `cls = entry["class"]` / `if cls is None: raise ValueError` 分支改为「`preset = entry.get("preset")`，无 preset 且 class 为 None 时报未实现」，并**校验 preset 返回 dict 含 `lifecycle` 键**（缺失抛 `ConfigError`，不得静默取骨架默认值——ISSUE-301）。两处均须进 §四。<!-- REVIEW-R1-FIX: ISSUE-002 -->

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-3 -->
**preset 返回 dict 的键集契约与 `create_behavior` 的构造形态（AUDIT-BREAK-3，强制）**

preset 工厂返回的 dict 键集**恰好五键**：`trackers` / `modifiers` / `lifecycle`（必需）+ `flags` / `counters`（可选，缺省视为 `{}`）。后两键的消费者是 `Pity.__init__` 新增的 `flags` / `counters` 形参（§3.1.4 骨架，构造期按 L4 truthy 规则写 `state`）。`create_behavior` 的 preset 分支**按名取键**，**禁止 `**preset(pdef)` 直展开**——直展开会让未知键在 `Pity(...)` 处抛 `TypeError`（键多余）或静默落成死代码（键无人读）：

```python
# preset 分支（分支改写归 S4-1；preset 本体随 S4-2 / S4-3 逐条落地；旧类兼容分支保留到发布前，见 GATE-5）
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
    trackers=built['trackers'], modifiers=built['modifiers'], lifecycle=built['lifecycle'],
    flags=built.get('flags'), counters=built.get('counters'),
)
```

两点配套（缺一则本条无效）：① **不得传旧类分支的 `params` dict**（`target_featured` / `reset` 注入的接口冲突见 §3.1.4 AUDIT-BREAK-2 条）；② 未知键校验与缺 `lifecycle` 键校验是**两道互补校验**，不得合并成一道（前者查多、后者查漏，合并后两类问题互相掩盖）。<!-- REVIEW-R1-FIX: ISSUE-405 --> **两者都在运行期由 `create_behavior` 承担**；导入期的 `_validate_registry()` **只判 `preset` 可调用、不校验键集**（它拿不到 `PityDef`、也不得执行 preset 体）；**尚未迁移的条目（无 `preset` 键）在过渡期内沿用旧判据（`class` 为子类），该分支随 S4-3 收口删除**（GATE-3 定稿）。<!-- REVIEW-R1-FIX: ISSUE-930 -->

<!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order -->
**旧类构造路径与 registry 回退（GATE-3(c) 定稿，强制）**

`class` 字段全部置 `None` 之后旧类在 registry 上**已无入口**，故两处声称依赖旧类的机制必须各自落实，否则一开工即发现无处可依（实测现状：`BEHAVIOR_REGISTRY` 每条都持有真实类对象，如 [pity.py:715](gacha_simulator/core/pity.py#L715) 的 `class: SoftStepBehavior`）：<!-- REVIEW-R1-FIX: ISSUE-002 -->

1. **等价性装置的「旧」侧：直接 import 旧类并以显式实参构造，不经 registry**。S5a 的 harness 从 `gacha_simulator.core.pity` 取 `SoftStepBehavior` / `HardPityBehavior` / `RotatingBehavior` / `RotatingCRBehavior` / `TargetedBehavior` / `RotatingSoftBehavior` / `RotatingCRSoftBehavior` / `TargetedSoftBehavior` 等类对象并手动传参构造（旧类在发布前一次性移除之前一直存在，见 GATE-5）。**不得**经 `create_behavior` 或 registry 取旧类（S4-1 落地后那条路径已指向 preset）。
2. **回滚路径：改为 `git revert` 子块 commit，不依赖 registry 保留旧类**（见 GATE-5）。原稿「回退 registry 到该 preset 指向旧类」在 `class: None` 之后不可执行，已一并改写。

**已评估并否决的备选**：在 registry 条目中加过渡字段 `legacy_class`（S4-1 写入旧类、发布前删除）。否决理由：它与 ISSUE-015 要消除的「条目同时持有 `class` 与 `preset` 两套指向」属同一类歧义，且 `_validate_registry()` 要额外维护该字段的生命周期；harness 直接 import 更简单，也不引入新状态。

<!-- REVIEW-FIX-PREV: ISSUE-301 -->

**preset 必须是工厂函数，不是模块级常量实例（ISSUE-005，强制纪律）**：preset 定义一律写成 `def _preset_xxx(pdef): return dict(...)`（形参见下方 ISSUE-030 签名定稿），**不得写 `_preset_xxx = dict(trackers=[FlagTracker(...)], ...)`**。模块级赋值会把 Tracker / Modifier / Condition 实例化在模块命名空间里，`create_behavior` 每次拿回的是**同一批对象**：同进程内所有用该 preset 的保底共享同一 Tracker / Flag / Counter 遥控器，`_rebind_state` 会把它们的 `_state` 重绑到最后调度的保底，多个保底的计数写进同一账本。并行维度暴露最彻底——worker 内同一 engine 连跑 N 次模拟、`mp_failed` 单进程兜底与 `max_workers=1` 的测试路径都复用同一 engine，串扰既跨保底又跨模拟，固定种子结果随 worker 数变化。配套测试：「同 type 两条保底状态互不影响」（§六）。

<!-- REVIEW-FIX-PREV: ISSUE-030 -->
**工厂签名与调用约定（ISSUE-030，2026-09-22 定稿，强制）**

preset 工厂**接受一个形参 `pdef`**（`PityDef` 实例），签名统一为 `def _preset_xxx(pdef) -> dict`；`create_behavior` 的调用形式为 `preset(pdef)`（`pdef` 已在手，registry 条目无须另存默认值）。**「零参工厂」是错的**：照零参示例施工会把逐条可配字段退化成常量，M1 的「与旧类逐场一致」只在**默认配置**下成立，任何非默认 `threshold` / `scope` / `counter_init` / `guaranteed_init` / `deltas` 都会静默退回常量值。**必须走 `pdef` 的值**（逐条可配，[config_store.py:159-186](gacha_simulator/core/config_store.py#L159-L186)）：

| 目标位置 | 取值来源 | 依据 |
|---------|---------|------|
| `Tracker(scope=…)` / `Modifier(scope=…)` | **`_norm_scope(pdef)`**（模块级 helper，`= (getattr(pdef,'scope',None) or default).lower()`，与 `build_lifecycle` / `_target_of` 同住 `core/pity.py`；示例里可提为局部变量 `scope = _norm_scope(pdef)` 减少重复，取值口径不变） | **ISSUE-503**：`create_behavior` 传给 `Pity` 的正是**归一化后**的 `scope = (getattr(pdef,'scope',None) or _default_scope).lower()`（[pity.py:854](gacha_simulator/core/pity.py#L854)）；原稿本行取值列写 `pdef.scope` **原值**（未归一化），与依据列引的同一式自相矛盾。后果：`Pity._scope`（小写）与各 Tracker/Modifier 的 `_scope`（原值）不同源，任何绕开 TOML 层 `.lower()`（[config_toml.py:645](gacha_simulator/core/config_toml.py#L645)<!-- REVIEW-R1-FIX: ISSUE-929 -->）的直构路径（`PityDef(scope='SSR', btype='hard', …)`）下 `ctx.draw.scope_cards.get('SSR', ())` 取空 → 因子为 `None` → **该保底静默恒等、不报错**（`rarity_rank.get('SSR')` 同时落 99，排序与层级保护一并失效）。**归一化点定稿**：`_norm_scope(pdef, default='ssr')`，`create_behavior` 侧 `default` 传 registry 的 `default_scope`（10 条目全为 `'ssr'`），全部 preset 侧用默认值 | <!-- REVIEW-R1-FIX: ISSUE-503 --> | <!-- REVIEW-R1-FIX: ISSUE-005 -->
| `HardModifier` 的阈值 τ（**ISSUE-002：类名按 §3.1.2 定稿，`ThresholdForceModifier` 已废**） | `pdef.threshold`，`None` 时回退 **90** | 与 `HardPityBehavior` 默认 `threshold: int = 90`（[pity.py:349](gacha_simulator/core/pity.py#L349)）及 `ui_params` 默认值（[pity.py:752](gacha_simulator/core/pity.py#L752)）一致；`create_behavior` 只在 `threshold is not None` 时透传（[pity.py:873-874](gacha_simulator/core/pity.py#L873-L874)），故缺省必须由 preset 或 Modifier 兜底 | <!-- REVIEW-R1-FIX: ISSUE-002 --> <!-- REVIEW-R1-FIX: ISSUE-951 -->
| `CounterTracker(init=…)` / `counters` 初值 | `pdef.counter_init` | 对齐 `_build_pity_state_init` 的 truthy 规则（[pity.py:1003-1004](gacha_simulator/core/pity.py#L1003-L1004)，`if cv:` 才预建键） | <!-- REVIEW-R1-FIX: ISSUE-951 -->
| `FlagTracker` / `flags` 初值 | `pdef.guaranteed_init` | 同上（[pity.py:1007-1008](gacha_simulator/core/pity.py#L1007-L1008)） | <!-- REVIEW-R1-FIX: ISSUE-951 -->
| `SoftModifier(scope, deltas=…)`（**ISSUE-002：类名按 §3.1.2 定稿，`BoostModifier` 已废**） | `_soft_deltas_of(pdef)`——非空则取 `pdef.deltas` / `pdef.soft_deltas`，否则按 `soft_increment` 是否为 `None` 归一为 `soft_additive` / `soft_interval` 后交给 `_expand_soft_to_deltas()`（**ISSUE-001**：三分支归一的唯一展开点，定义见 §3.2 preset 代码块） | M6：展开职责搬入工厂，依赖 `create_behavior` 已透传的 `soft_*` 参数（[pity.py:866-874](gacha_simulator/core/pity.py#L866-L874)）。**不得把 `pdef.btype` 直喂 `_expand_soft_to_deltas`**（后缀型落 `return ()`，软保底静默消失），见 `_soft_deltas_of` 的 docstring | <!-- REVIEW-R1-FIX: ISSUE-001 -->
| `CounterTracker(reset_on=…)` | `pdef.reset or _norm_scope(pdef)` | 对齐 `create_behavior` 的 `if pdef.reset:` 透传口径（[pity.py:877-878](gacha_simulator/core/pity.py#L877-L878)）；回退分支与 `Tracker(scope=…)` 同源（ISSUE-503，原写 `pdef.scope` 原值） | <!-- REVIEW-R1-FIX: ISSUE-503 --> <!-- REVIEW-R1-FIX: ISSUE-951 -->
| **`hard` / `hard_exclude_owned_*` 的 `t_of`**（**ISSUE-403：不写即目标集静默放宽，不报错**；**2026-10-05 裁决 7B：`soft_*` 不再消费本项**） | `_target_of(pdef)`——`pdef.target_featured` 为 `True` → `'featured'`（目标集 = scope 内 featured 卡集，**空集回退 scope 全集**），否则 `'scope'` | 旧 `HardPityBehavior._compute_probabilities` / `SoftStepBehavior._compute_probabilities` 的 `target_slots = ctx.draw.featured_slots.get(scope, scope_slots) if self._target_featured else scope_slots`（[pity.py:374-377](gacha_simulator/core/pity.py#L374-L377) / [pity.py:286-289](gacha_simulator/core/pity.py#L286-L289)）。`create_behavior` 的注入（[pity.py:875-876](gacha_simulator/core/pity.py#L875-L876)）在 preset 分支**不可用**（`Pity.__init__` 无该形参，AUDIT-BREAK-2），故必须由工厂承接；完整论证与选择子定义见 §3.1.4 的 ISSUE-403 专段 | <!-- REVIEW-R1-FIX: ISSUE-403 --><!-- REVIEW-R1-FIX: ISSUE-002 --> <!-- REVIEW-R1-FIX: ISSUE-951 -->
| `FateTracker` / `StreakTracker` 参数 | `pdef.fate_threshold` / `fate_points_init` / `cr_counter_threshold` / `cr_base_rate` / `cr_state_probs` | 同 `create_behavior` 的 P56 透传清单（[pity.py:883-885](gacha_simulator/core/pity.py#L883-L885)） |
| **`SelectedModifier` 的定轨阈值 `τ_fate`**（**2026-10-10 S2a-2 落地时补登**：原表把 `pdef.fate_threshold` 只记在 `FateTracker` 行，而条件 `fate_points >= τ` 的**消费方是 Modifier**——preset 不写 `tau=` 即该字段静默失效、阈值恒取缺省 1，`targeted(fate_threshold=0)`（G19 尘白禁区不歪池）会从「定轨即必出」退化为「定轨后须等 1 抽」） | `pdef.fate_threshold`，`None` 时回退 **1** | 旧 `TargetedBehavior.__init__` 的 `self._fate_threshold = fate_threshold if fate_threshold is not None else 1`（[pity.py:594](gacha_simulator/core/pity.py#L594)）；`SelectedModifier` 的构造形参 `tau` 缺省同取 1（§3.9.2 的 `self._tau`），故缺省路径与旧类逐位一致 |
| **`lifecycle=`**（preset 返回 dict 的必需键，**不写即静默失效**） | 由 `core/pity.py` 的 `build_lifecycle(pdef)` 按**两个正交维度**产出：激活维 = `pdef.depends_on` 非空 ? `Dependent` : `Always`；退役维 = `pdef.max_triggers > 0` ? `AfterN(n)` : `Never`（四组合：`AlwaysActive` / `FiniteActive` / `DependentActive` / `DependentFiniteActive`）——**工厂不自行拼装** | **旧 `create_behavior` 的 `lifecycle_kwargs` 段（[pity.py:893-900](gacha_simulator/core/pity.py#L893-L900)）是这两个字段唯一的转换点**；preset 化后必须由工厂承接**且旧段须同步删除**。定稿与三条配套纪律见 §3.1.3；`create_behavior` 对缺失该键有 `ConfigError` 防线、§六 有断言 | <!-- REVIEW-FIX-PREV: ISSUE-301 --> |

### 3.2.1 `target_featured` 的适用范围收窄（裁决 7B，2026-10-05）

**查证结论**：手册 `docs/主流抽卡游戏卡池机制配置转换手册.md` 中 `target_featured = true` 共 **10 处，全部落在 `type = "hard"`**（行 315 / 343 / 534 / 629 / 1393 / 1479 / 1504 / 1638 / 1648 / 1706，逐个回溯所属 type 确认）。**`soft_*` 一次都没有**。项目内唯一在 soft 上使用它的是 `config.toml` 的示例块 `ssr_soft`（`config.toml:1104`），那是样例配置、不对应任何游戏机制。

**故收窄为**：

| 类型 | `target_featured = true` 时 |
|------|---------------------------|
| `hard` | 正常生效（目标集 = scope 内 featured 卡集），10 处机制全部在此 |
| `hard_exclude_owned_skip` / `hard_exclude_owned_any` | **该字段对它们静默无效**（**订正（S9-3 审查，2026-10-14）**：实测两条 type 的 preset 均**不消费** `target_featured`，其 `NotOwnedModifier` 只有 `_scope` / `_threshold` / `_on_all_owned` 三个属性；成因是 G3 的 A **恒为**「featured 中未拥有者」（§3.10.4 机制表第 7 行），故该键对它们无可作用面。**不是**与 `hard` 同列的「正常生效」。**另**：`target_featured` 的消费者全库**只有** `HardModifier`（`_target_of(pdef)` 的唯一调用点在 `_preset_hard`），故这一「接受并忽略」的形态对 `rotating` / `targeted` / `soft_*` 等**同样成立**（`soft_*` 由裁决 7B 单独硬拒），本行只订正两个新 type 的误列 |
| `soft_interval` / `soft_additive` / `soft_step` | **抛 `ConfigError`** |

**为什么 soft 侧可删而不丢能力**：`soft(target_featured=True)` 可**等价分解**为两步转移（原按 §3.1.5.2 的 `share` 语义写出，2026-10-08 迁到增量词汇；该形态已于裁决 7B 从配置面移除，本段按历史记录保留）：

1. 转移（A = `scope_cards[scope]`，Q = 全池减更高稀有度，`amount = β`），稀有度级
2. 转移（A = `featured_cards[scope]`，Q = `scope_cards[scope]`，`amount` 由第一步的份额推出），卡级

第 2 步与 rotating 家族的「卡级定向」**只在 A/Q 形状这一层同类**（都是「A 取卡集」），**条件与 amount 两列都不同**：rotating 的条件是 `guaranteed` / `extra_flag`（flag 门），amount 是夺取型 `p(Q)`（源组整组搬空）；而第 2 步的条件必须与第 1 步相同（soft 的 `boost > 0`，counter 驱动、不是 flag 门），amount 是「第 1 步搬进 scope 的那一份里落在非 featured 成员上的部分」。**故第 2 步既不能实例化 `RotatingModifier`，也不等同于现有任何一个 Modifier**（2026-10-11 订正：原句「是同一件事」易被读成「可复用 rotating 的零件」）。**若要一个「转移量可自由取值」的卡级算子**，那是**第三个机制**，当前表达不了，须另立条目而非复用 `target_featured`。<!-- P64-7B-GAP-REG -->

**缺口登记（2026-10-11）**：上句的「须另立条目」自 2026-10-05 写下起**从未真的另立**（全篇 `第三个机制` 仅此一处，§七 的 46 块与 §六 均无对应条目）。故 7B 的实际状态不是「该能力已有替代路径」，而是「**该能力在算子族词汇里可表达，但今天没有任何零件能表达它**」。「soft 侧可删而不丢能力」的严格含义应读作前者，不读作「今天拼得出来」。

**若日后重新裁决取「恢复 `soft(target_featured=true)`」支，施工面如下**（2026-10-11 查明）：

| 面 | 动作 |
|----|------|
| 实现 | **加一个具体 Modifier 类**，不是加一个与 soft 复合的第二个零件：条件内联 `boost_pct > 0`；A = `featured_cards[scope]`；Q = 更低稀有度卡集 ∪（scope 卡集减 A）；amount = `min(boost/100, p(Q))`；A 侧形状按 §3.1.2。**接口不变**（§3.1.5.2.1）。亦可给 `SoftModifier` 加一维目标集取值。**走「两步复合」不划算**：Modifier 接口没有跨零件传增量的通道（`apply` 只回一个新 dist），第 2 步只能自己按同一公式重算（那就得自己也持有 `deltas`），与一步式实现量相同却多一次遍历 |
| 接线 | `_preset_soft_step` 写回 `target=_target_of(pdef)` 并按 `pdef.target_featured` 选 A/Q；删掉 `create_behavior` 的类型级硬拒（`core/pity.py` 的 7B 段），改为按该字段分派；同步 `_target_of` 的消费面注释与 `SoftModifier` 的 docstring |
| 配置与基线 | `config.toml` 的 `ssr_soft` 可写回 `target_featured = true`；**两套 golden 需再次重固化**（p79 三组 + p82 五组，共 8 份），重固化属用户裁决级动作（先例 `68770ce`） |
| 用例面 | §六 `ISSUE-403` 与 §七 S5b 的 soft 用例由「硬拒用例」反向改回「等价性用例」（本节落地面 ⑤ 的反向） |
| 文档面 | 本节正文（落地面 ①②③④⑤）、§3.1.2 的消费表、§3.1.5.5 的 `soft + soft` 推论表与被消除的反例行、§1.5 的 P82 结论终版表、`docs/01-活跃/subsystems/保底系统/01-理论.md` 三行（`:24` / `:45` / `:97`）全部反向回写 |
| 裁决面 | 7B 是 2026-10-05 的用户裁决，2026-10-10 又确认过一次「维持 7B」。恢复等于推翻两次裁决，**第一步是重新裁决**，不是技术动作 |

**本清单不构成待办**：它是「若重新裁决取恢复支」的施工面估算，登记在此以免下次重新推导。
<!-- P64-USER-RULING-2026-10-15 -->
> **⚠ 已由用户裁决取「恢复支」（2026-10-15）**：用户明确要求**恢复 `ssr_soft` 的 `target_featured = true` 能力**。该决定**正是本清单第 6 面所说的「第一步：重新裁决」**，故清单的六面施工面**即刻转为待办**（不再是「不构成待办」）。
> **状态**：**已裁决、未实施**。**它不属于 P64 的 47 块**（P64 已全部落地并收口），**须另立计划块**；其中第 3 面的「**8 份 golden 重固化**」（p79 三组 + p82 五组）本身是**用户裁决级动作**（先例 `68770ce`），须在实施前单独确认。
> **在实施之前**：样例配置 `ssr_soft` 保持现状（无该键）、`soft_*` + `target_featured=true` 仍被 `create_behavior` 硬拒，故「最差影响大保底覆盖倍数」的当前读数（0.2125）即该现状下的**正确值**（详见报告 §八 的实测）。

**收益（三条）**：

1. **消掉 §3.1.5.5 的唯一「约束冲突」反例**：`soft(target_featured=True) + hard` 的顺序敏感是 P82 修正结论的来源；收窄后同 U 同 T，退化为可交换（该表已重算）
2. **消掉 `01-理论.md:24` 的文档与代码矛盾**：该句写「概率提升仅作用于该槽位：standard SSR 保持基础概率不变」，而 `tf=True` 时标准 SSR 进 `non_target` 被乘 `(1−β)`、`tf=false` 时它反而分到增量，两种情况都不是「不变」
3. **删除面小且有先例**：`deactivate_on_early_hit` 已在 rotating / targeted 上按类型拒绝并抛 `ConfigError`（`tests/core/test_pity_config_toml.py:217` / `:230`），「按 type 拒绝某字段」是本项目已有的模式

**为什么 hard 侧保留**：10 处机制在用，且裁决 1B 统一后它与 `hard(tf=false)` 只差 `t_of` 是哪个解析器，无任何特殊结构；删掉反而要写类型相关校验。G19（尘白禁区不歪池）已迁为 `targeted(fate_threshold=0)`，但那只说明「必出 UP 也可用 targeted 表达」，不等于 hard 侧 10 处都要迁。

**落地面（2026-10-09 写死校验点，ISSUE-002）**：① 校验点定稿为 **`create_behavior`**（preset 构造前即抛，与 S4-4 的 `lifecycle` 键防线同批），断言「`pdef.target_featured` 为真 且 `btype ∈ _SOFT_TYPES`」时抛 `ConfigError`——**不放在 `_build_pity`**：等价性 harness 与直构 `PityDef` 的路径绕过 TOML 层，防线须盖住构造入口。（原文写「`_build_pity` 或 `create_behavior`」属未选定，两处覆盖面不同，已写死为一处。）② `config.toml:1103-1104` 的示例块删去 `target_featured = true`；③ `docs/01-活跃/subsystems/保底系统/01-理论.md` 的三行（`:24` / `:45` / `:97`）改写；④ §3.1.5.5 的反例行与 P82 修正结论同步（已落正文）；⑤ **§六 ISSUE-403 条与 §七 S5b 的 soft 用例同批改写**（原要求「soft 配 `target_featured=True` 的等价性」与 ① 互斥，已改为硬拒用例，见两处）<!-- REVIEW-R1-FIX: ISSUE-002 -->。

**⚠ 待人工裁决（ISSUE-002 的另一支，本计划未采用）**：若改选「保留 soft 对 `target_featured` 的消费」，则 ① 的类型级硬拒须缩回 `hard` 族（`soft_*` 不再拒绝），并恢复 §六 / S5b 的 soft 等价性用例与 `_preset_soft_step` 的 `target=`。两支只能取一；本计划取「维持 7B」支，理由是 7B 为用户裁决（2026-10-05，晚于 ISSUE-403），且 §3.1.5.5 的结论表与 §1.5 的敏感集合收窄均以它为前提。**用户 2026-10-10 确认：维持 7B 的类型级硬拒**，本组不再计入「待人工裁决」枚举。

<!-- REVIEW-R1-FIX: RULING-7B -->

preset 自身只保留**语义固定项**（如 `judge="featured"` / `hit="clear"` / `miss="set"` 这类由机制语义决定的匹配面）。§六 已补「非默认 threshold / scope / counter_init 下 preset 与旧类逐场一致」的断言。

`create_behavior` 检测 `entry.get("preset")` 走新路径。

```python
def _preset_rotating(pdef):          # ISSUE-030：形参 pdef，逐条可配值一律取自它
    return dict(
        lifecycle=build_lifecycle(pdef),         # ISSUE-301：生命周期唯一转换点（§3.1.3）
        trackers=[FlagTracker(scope=scope, judge="featured", hit="clear", miss="set", flag="guaranteed")],
        modifiers=[
            RotatingModifier(scope),      # 条件（guaranteed）内联在 compute_delta() 里（§3.14）
        ],
        flags={"guaranteed": pdef.guaranteed_init},  # 初值走状态声明（H2），不加 Tracker 形参
    )

def _preset_rotating_cr(pdef):
    """CR（捕获明光）——rotating 之上加「连续未命中 → 随机拦截」。

    **Tracker 顺序是契约（强制，RULING-6B′）**：`StreakTracker` 必须排在 `FlagTracker`
    **之前**。掷骰在 `StreakTracker.prepare`（`before_draw`、`advance` 之后、Modifier 链之前），
    其 `guard_flag` 守卫读的是**抽前**的 `guaranteed`；若 `FlagTracker` 排在前面、在同一抽的
    `commit` 里翻转它，则守卫读点与 `cr_counter` 的更新条件取到同一个（抽后的）值，
    守卫语义反转、**`cr_counter` 恒为 0**。实测（脚本化 RNG，15 抽）：顺序反转时计数器轨迹
    恒 `0,0,...,0`，正序时与旧类同为 `1,1,2,2,2,3,3,4,4,4,4,5,5,5,6`。
    """
    return dict(
        lifecycle=build_lifecycle(pdef),
        trackers=[
            StreakTracker(scope=scope, judge="featured",
                          threshold=pdef.cr_counter_threshold,
                          base_rate=pdef.cr_base_rate,
                          state_probs=pdef.cr_state_probs,
                          flag="cr_intercepted",
                          guard_flag="guaranteed"),   # ← 顺序是契约：必须在 FlagTracker 之前
            FlagTracker(scope=scope, judge="featured", hit="clear", miss="set", flag="guaranteed"),
        ],
        modifiers=[
            RotatingModifier(scope, extra_flag="cr_intercepted"),
        ],
        flags={"guaranteed": pdef.guaranteed_init},
    )

def _norm_scope(pdef, default: str = 'ssr') -> str:
    """scope 的**唯一归一化点**（ISSUE-503）——`create_behavior` 与全部 preset 工厂共用。

    与 `create_behavior` 的 `scope = (getattr(pdef,'scope',None) or _default_scope).lower()`
    （[pity.py:854](gacha_simulator/core/pity.py#L854)）同式同源：`create_behavior` 侧把
    registry 条目的 `default_scope` 传进来（10 条目全为 `'ssr'`），preset 侧用默认值。
    **不归一化的后果**：`Pity._scope` 是小写、而各 Tracker / Modifier 的 `_scope` 是 pdef 原值，
    任何绕开 TOML 层 `.lower()`（[config_toml.py:645](gacha_simulator/core/config_toml.py#L645)<!-- REVIEW-R1-FIX: ISSUE-929 -->）
    的直构路径（`PityDef(scope='SSR', …)`）会让 `ctx.draw.scope_cards.get('SSR', ())` 取空 →
    增量为 `None` → **该保底静默恒等、不报错**。"""
    return (getattr(pdef, 'scope', None) or default).lower()

def _target_of(pdef) -> str:
    """pdef.target_featured 决定目标集（ISSUE-403）——与 build_lifecycle 同住本模块。

    'featured' 分支的消费方须做空集回退：目标集 = ctx.draw.featured_cards.get(scope)
    or ctx.draw.scope_cards.get(scope, ())（缺这条回退，无 featured 卡的池在
    target_featured=True 下会退化为恒等，而旧实现回退全部 scope 槽）。
    """
    return 'featured' if getattr(pdef, 'target_featured', False) else 'scope'

def _preset_hard(pdef):
    tau = pdef.threshold if pdef.threshold is not None else 90    # 缺省对齐 pity.py:351 / :752
    return dict(
        lifecycle=build_lifecycle(pdef),         # ISSUE-301
        trackers=[CounterTracker(scope=_norm_scope(pdef), reset_on=pdef.reset or _norm_scope(pdef),
                                 init=pdef.counter_init)],
        modifiers=[
            # ISSUE-403：target_featured 由本类自己的 compute_delta() 消费
            # 裁决 7B：本类型是 target_featured 的合法消费者（soft 侧已按 7B 移出）
            HardModifier(scope, threshold=tau, target=_target_of(pdef)),
        ],
        counters={"counter": pdef.counter_init},
    )

def _soft_deltas_of(pdef) -> tuple:
    """deltas 的**唯一展开点**（ISSUE-001）——旧 `SoftPityMixin._init_soft_pity`
    （pity.py:509-525）三分支归一在 preset 侧的替代，四个 soft 系类型共用。

    分支与 `_init_soft_pity` 逐条同义：
      ① `pdef.deltas` / `pdef.soft_deltas` 非空 → 直接用它（soft_step 形态）；
      ② 否则 `soft_increment is not None` → 归一为 `soft_additive` 后展开；
      ③ 否则归一为 `soft_interval` 后展开（`soft_start` 缺省 74、`soft_end` 缺省 90，
         与 `_init_soft_pity` 的默认值同值）。
    对 counter 驱动三类型，`_build_pity` 已在 `pdef.deltas` 里放好展开结果
    （config_toml.py:676），故 ① 是常态路径；分支 ②③ 是「后缀型只写语法糖」的路径
    ——旧路径由 `_init_soft_pity` 承担，preset 化后由本函数承担。

    **`pdef.btype` 一律不得直喂 `_expand_soft_to_deltas`**：该函数
    （config_toml.py:1607-1627）只认 `soft_interval` / `soft_additive` 两个字面量，
    其余一律落到函数末尾的 `return ()`；后缀型（`rotating_soft` /
    `rotating_cr_soft` / `targeted_soft`）的 btype 恰在「其余」之内，直喂的后果是
    「只写 soft_start/soft_end（或只写 soft_increment）」的合法配置展开出空元组 →
    `SoftModifier` 的 boost 恒 0、该步增量恒 `None`（恒等）→
    **软保底静默消失、且不报错**。旧路径不踩这一条：`_init_soft_pity` 先归一 btype 再展开。
    """
    if getattr(pdef, 'deltas', None) is not None:
        return pdef.deltas
    if getattr(pdef, 'soft_deltas', None):
        return pdef.soft_deltas
    from .config_toml import _expand_soft_to_deltas
    _s = pdef.soft_start if getattr(pdef, 'soft_start', None) is not None else 74
    _e = pdef.soft_end if getattr(pdef, 'soft_end', None) is not None else 90
    if getattr(pdef, 'soft_increment', None) is not None:
        return _expand_soft_to_deltas('soft_additive', _s, _e, pdef.soft_increment)
    return _expand_soft_to_deltas('soft_interval', _s, _e, None)

def _preset_soft_step(pdef):
    deltas = _soft_deltas_of(pdef)                                     # M6（ISSUE-001）
    return dict(
        lifecycle=build_lifecycle(pdef),         # ISSUE-301
        trackers=[CounterTracker(scope=_norm_scope(pdef), reset_on=pdef.reset or _norm_scope(pdef),
                                 init=pdef.counter_init)],
        modifiers=[
            # 裁决 7B：soft 不消费 target_featured（该形态经 create_behavior 抛 ConfigError）
            # 2026-10-05 错误 ②：Q 若写成 scope 内部，soft 整体不生效（§3.1.5.2.4）
            SoftModifier(scope, deltas=deltas),       # deltas 经 _soft_deltas_of(pdef)（ISSUE-001）
        ],
        counters={"counter": pdef.counter_init},
    )
```
<!-- REVIEW-R1-FIX: ISSUE-403 -->
> **`_target_of(pdef)` 的归属与消费面（ISSUE-403，强制；2026-10-09 按裁决 7B 收窄，ISSUE-002）**：该 helper 住 `core/pity.py` 模块级（与 `build_lifecycle` 同处，随 **S4-2** 的 counter 驱动 preset 落地），**消费面只有 `_preset_hard`**（`hard_exclude_owned_*` 的目标集由 G3 自己的解析器给出，见 §3.10.4）。**为何不再含 soft**：`target_featured` 在旧实现中确被两个类读取——`HardPityBehavior`（[pity.py:374-377](gacha_simulator/core/pity.py#L374-L377)）与 `SoftStepBehavior`（[pity.py:286-289](gacha_simulator/core/pity.py#L286-L289)）——但裁决 7B（2026-10-05）已把 `soft_*` + `target_featured = true` 定为 `ConfigError`，preset 侧因此没有 soft 消费者，`_preset_soft_step` **不写 `target=`**。（原稿此处写「由 `_preset_hard` 与 `_preset_soft_step` 消费（soft_interval / soft_additive 走同一工厂），消费面恰好是这四类」，与 7B 的硬拒面互斥，已改。）`rotating` 族的该字段落在 `RotatingBehavior.__init__` 的 `**kwargs` 里**被忽略**（[pity.py:450](gacha_simulator/core/pity.py#L450)），`rotating_soft` / `rotating_cr_soft` 的内层 `SoftStepBehavior` 也未传该值（[pity.py:527](gacha_simulator/core/pity.py#L527)）——故 **S4-3 的六个事件驱动 preset 一律不加 `target=`**，把 `_target_of` 照抄到事件驱动族即为**语义漂移**。<!-- REVIEW-R1-FIX: ISSUE-002 -->
<!-- REVIEW-FIX-PREV: ISSUE-030 -->
<!-- REVIEW-FIX-PREV: ISSUE-031 -->
<!-- REVIEW-FIX-PREV: ISSUE-301 -->
> **形态以 §3.14 为准（2026-10-06 改判）**：上例的 `modifiers` 已按 **条件内联**定稿，Modifier 只算增量，触发条件写在它自己的 `compute_delta()` 开头。原「由 `ConditionalModifier` 的第二个实参承载」的写法**已废弃**。

> **本表已按裁决 1B / 5B / 6B / 7B 改写（2026-10-05）**：Modifier 一栏由原来的类名列表改为 **`TransferModifier` 的三参数**（§3.1.5.2.3 的分解表是本表的依据），`BaseRatioModifier` / `InterceptModifier` / `ForceFeaturedModifier` 等类名不再出现。**注（2026-10-08）**：裁决 1B 的「`TransferModifier` 单类 + 三参数」形态已随 2026-10-06 的简化作废（§3.10.4 末段：「类消失，只剩一个 `compute_delta()` 与一个助手」），现行形态是 **§3.1.2 的「七个机制形态、一机制一类」**；本条按历史记录保留，其下方的表已按现行形态写。**`target_featured` 的可用类型收窄**：仅 `hard` 与 `hard_exclude_owned_*` 消费它；`soft_*` 类型若配置 `target_featured = true` **抛 `ConfigError`**（裁决 7B，理由见本表下方专段）。

| 现有 type | preset 三元组（含完整状态声明，H2 补全） | 条件（内联在各机制 `compute_delta()` 内，§3.14） |
|-----------|------------------------------------------|-----------------------------------|
| hard | Tracker: `CounterTracker(scope, reset_on, init)`；Modifier: `HardModifier(scope, threshold=τ, target=_target_of(pdef))` | `counter >= τ` |
| soft_step / soft_interval / soft_additive | Tracker: `CounterTracker(scope, reset_on, init)`；Modifier: `SoftModifier(scope, deltas=deltas)`（`deltas` 由工厂经 `_soft_deltas_of(pdef)` 展开，M6 / **ISSUE-001**；**不写 `target=`**，ISSUE-002） | `boost > 0` |
| rotating | Tracker: `FlagTracker(scope=scope, judge="featured", hit="clear", miss="set", flag="guaranteed")`；Modifier: `RotatingModifier(scope)` | `guaranteed` |
| rotating_soft | rotating 的 Tracker + `CounterTracker`；Modifier: `SoftModifier` + `RotatingModifier` | 各自 |
| rotating_cr | `[StreakTracker(scope=scope, judge="featured", …, flag='cr_intercepted', guard_flag='guaranteed'), FlagTracker(...)]`（**顺序是契约：`StreakTracker` 必须在前**，见 §3.1.1「Tracker 顺序是契约」条；代码见下方 `_preset_rotating_cr`）；Modifier: `RotatingModifier(scope, extra_flag='cr_intercepted')` | `guaranteed ∨ cr_intercepted` |
| rotating_cr_soft | rotating_cr 的 Tracker；Modifier: 再加 `SoftModifier` | 各自 |
| targeted | Tracker: `FateTracker(scope=scope, judge="selected", hit="clear", miss="accumulate", keys=("fate_points","losses","guaranteed","lost_rotating"))`；Modifier: `SelectedModifier(scope, tau=τ_fate)`（**`τ_fate` 取值见下方「取值来源表」，2026-10-10 S2a-2 落地时补登**） | `guaranteed ∨ fate_ready` |
| targeted_soft | targeted 的 Tracker；Modifier: 再加 `SoftModifier` | 各自 |

> **`RotatingModifier` 的 `extra_flag` 形参（2026-10-06 补）**：`rotating_cr` 与 `rotating` 的效果完全相同（「出金必是 UP」），差别只在条件多一个 `cr_intercepted`。条件内联后，用一个可选形参表达：

```python
class RotatingModifier(Modifier):
    def __init__(self, scope, extra_flag=None):
        self._scope, self._extra_flag = scope, extra_flag
    def compute_delta(self, view, dist, ctx):
        if not (view.get('guaranteed') or (self._extra_flag and view.get(self._extra_flag))):
            return None
        ...
```

> 这是「条件内联」的代价之一：**条件若有变体，用构造形参表达，而不是新写一个类**。判据同 §3.1.2 的四样：形参只影响「条件」，不影响 A/Q/转移量。

<!-- REVIEW-FIX-PREV: ISSUE-301 -->
> **表中 10 行的 Lifecycle 组件统一为 `build_lifecycle(pdef)`（ISSUE-301，强制）**：上表「preset 三元组」列只列 Tracker 与 Modifier 两项，**不逐行重复 Lifecycle**——10 行的 Lifecycle 一律由 `build_lifecycle(pdef)` 产出并作为返回 dict 的 `lifecycle=` 键（§3.1.3 定稿的四组合取值：激活维 = `pdef.depends_on` 空/非空、退役维 = `pdef.max_triggers` 0/正，`AlwaysActive` / `FiniteActive` / `DependentActive` / `DependentFiniteActive` 四者之一；`deactivate_on_early_hit` 四组合都带入 `cfg`）。**漏写该键即全部 `deactivate_on_early_hit` / `depends_on` / `max_triggers` 配置静默失效**，故 `create_behavior` 对此设 `ConfigError` 防线（§3.2 首段）、§六 设断言。

<!-- REVIEW-FIX-PREV: ISSUE-001 -->
**「零改动」的前提（ISSUE-001）**：`Pity` 必须继续由 `btype` 推导 `is_soft` / `is_hard` / `is_event_driven` 三个标志（§3.1.4 骨架已按此写入，删除了「统一后不再区分 counter/event」的写死行）。`_validate_behaviors`（[pity.py:931-982](gacha_simulator/core/pity.py#L931-L982)）按 `is_hard` → `is_event_driven` → `is_soft` 的 `elif` 链分派规则 2/3/4，标志缺失会让三个规则全部错判（实测：只打 `is_event_driven=True` 后，soft_interval + soft_additive 同 scope 由「通过」变抛 `ConfigError`，rotating + hard 同 scope 被拒，规则 2 静默失效）。若将来确要废掉这三个标志，必须与 §3.12.2 的合法组合判据**合并重写**分派逻辑并在 §六 补相应断言，不得只删标志。<!-- REVIEW-R1-FIX: ISSUE-001 -->

`_btype` 保留，故 `_resolve_order`（[pity.py:914](gacha_simulator/core/pity.py#L914)）/ `_validate_behaviors`（[pity.py:931](gacha_simulator/core/pity.py#L931)）排序校验逻辑零改动（**2026-09-18**：P82 接线独立先行后，排序结果被 `get_behaviors_for_pool()` 消费；P64 主线不改其排序逻辑，仅经 M3 新增 `priority` 键）。`params`/`ui_params` 保留，GUI 参数控件零改动。<!-- REVIEW-R1-FIX: ISSUE-001 --><!-- REVIEW-R1-FIX: ISSUE-002 -->

### 3.3 G1 inverse preset（新增）

幻塔连中必歪：出 UP 后下一次 SSR 必非 UP。与 rotating 对偶：

```python
def _preset_rotating_inverse(pdef):          # ISSUE-030：形参 pdef；ISSUE-031：条件外置形态
    return dict(
        lifecycle=build_lifecycle(pdef),         # ISSUE-301
        trackers=[FlagTracker(scope=scope, judge="featured", hit="set", miss="clear", flag="forced_loss")],
        modifiers=[
            NonFeaturedModifier(scope),     # 条件（forced_loss）内联
        ],
        # forced_loss 是 preset 内部标志，PityDef 无对应初始值字段（区别于 rotating 的
        # guaranteed_init），故初值恒为 False——与旧实现（无该机制）一致。scope 取自 pdef。
        flags={"forced_loss": False},
    )
```
<!-- REVIEW-FIX-PREV: ISSUE-030 -->
<!-- REVIEW-FIX-PREV: ISSUE-031 -->
<!-- REVIEW-FIX-PREV: ISSUE-301 -->

注册为 `rotating_inverse`（display_name「反向轮换保底（连中必歪）」）。`NonFeaturedModifier` 复用 `_redistribute_scope` 反向调用。**条件内联（2026-10-06 随 §3.14 改判，2026-10-08 同步）**——`NonFeaturedModifier` 本身**无 `flag` 形参**，触发条件写在其 `compute_delta()` 开头（原写「由外层 `ConditionalModifier` 承载，见 §3.14.6」，该包装器与那个小节均已随改判删除）。

<!-- REVIEW-FIX-PREV: ISSUE-105 -->
**三处类型注册（ISSUE-105，强制，2026-09-22 补）**：`rotating_inverse` 不只是「多一个 registry 条目」，它必须同时进入**两个类型集合**与**一个排序表**，缺任一处即静默失效：

| 落点 | 取值 / 内容 | 不做的后果 |
|------|------------|-----------|
| `_BTYPE_ORDER`（[pity.py:906-911](gacha_simulator/core/pity.py#L906-L911)，现状 10 项、**无该键**） | 加 `'rotating_inverse': 3`（与 `rotating` / `targeted` / `targeted_soft` 同族档位） | `_resolve_order` 用 `_BTYPE_ORDER.get(btype, 99)`（[pity.py:926](gacha_simulator/core/pity.py#L926)），缺键落到 **99**（排在全部已知类型之后）。接线后（P82 使排序键成为管道顺序的唯一来源，§1.5）会改变它与同 scope 其它保底的先后 | <!-- REVIEW-R1-FIX: ISSUE-952 -->
| `_EVENT_DRIVEN_TYPES`（[pity.py:114-115](gacha_simulator/core/pity.py#L114-L115)，现状 6 项） | 追加 `'rotating_inverse'`（该集合升为模块级常量后同样须含它） | `_btype` 推导出的 `is_soft` / `is_hard` / `is_event_driven` **全为 False** → `_validate_behaviors`（[pity.py:931-982](gacha_simulator/core/pity.py#L931-L982)）规则 2/3/4 全部跳过（`elif` 链三条规则无一命中），**同 scope 的 `rotating` + `rotating_inverse` 可共存而不报错**（规则 3 即「同 scope 两个事件驱动型互斥」），正是本计划反复强调的静默失效模式。**ISSUE-506（2026-10-01 修正因果，强制）**：该集合的**唯一**消费点就是规则 3（实测全库 `is_event_driven` 只被 [pity.py:971](gacha_simulator/core/pity.py#L971) 读，其余均为写入点），故后果**仅此一条**——原稿续写的「还决定 `is_active` 早退是否作用于该类型」是**旧架构的残留**（旧实现只有 `CounterBasedBehavior` 读写 `_active`）。改造后 `before_draw` / `after_draw` 首行的早退由 §3.1.4 骨架对**全部类型无条件**承担（§3.1.3 已把「早退作用于事件驱动型」列为 P64 的统一增量能力），与 `_EVENT_DRIVEN_TYPES` 无关；按原表述排查「某类型 `_active` 不生效」会查错方向 | <!-- REVIEW-R1-FIX: ISSUE-506 --> | <!-- REVIEW-R1-FIX: ISSUE-001 -->
| `_SOFT_TYPES` / `_HARD_TYPES` | **不加**（rotating_inverse 既非 soft 也非 hard） | — |

§四 的 `core/pity.py` 重构行原只写「`_BTYPE_ORDER` 加 `rotating_inverse`」而未给取值，已补；S1 的「三个集合升为模块级常量」任务项已注明「**常量内容需追加 `rotating_inverse`**」——不得按「原样迁移」理解。§六 已补对应断言。


<!-- P64-G1-GAP-REG -->
**G1 的「连 2 次」缺口登记（2026-10-13，S7c 审查裁定）**：手册 §5.3 把幻塔该规则写作「连歪 **2** 次 → 下次必中；连中 **2** 次 → 下次必歪」，而本节的两个 preset 都用单标志二态翻转（`FlagTracker` 的 `hit` / `miss`，其 `commit` 只做 `set()` / `clear()`、**无连击计数器**），故**只表达连 1 次**。按项目 CLAUDE.md 的精确建模原则（近似必须显式登记为缺口、不得计入「已覆盖」；遇到只能近似表达的场合**默认登记缺口**），本条已按三渠道登记：手册 §5.4 该行与 §21 总缺口汇总改为两段式（`✅ 类型已注册（连 1 次语义）＋ 🟡 残余缺口（连 2 次语义未实现）`）、模块状态矩阵 P64 行补一条。

**涉及两个 preset**：`rotating`（必中半）与 `rotating_inverse`（必歪半），不是只有后者。

**关闭路径二选一**：① 按项目「搜索报告纪律」为该规则找到 **≥2 个独立且无矛盾**的信源，若实为连 1 次，则订正手册 §5.3 的口径并撤掉该缺口；② 若确为连 2 次，则维持缺口登记（届时须另立实施条目，落点是 `FlagTracker` 加连击计数或新增一个 Streak 型 Tracker）。

**与本计划已有的「7B 缺口」（§3.2.1）不同**：7B 是**能力从配置面移除**（可表达但未接线），本条是**手册的机制定义与实现不等价**（近似）。两者都按精确建模原则登记，但关闭方式不同。

### 3.4 软保底统一（不再分阶段二）

新架构下 soft 不再是 mixin，而是 `CounterTracker + SoftModifier`（**ISSUE-002：类名按 §3.1.2 定稿，`BoostModifier` 已废**）。**无需分阶段**，全部 10 个类型在同一阶段 preset 化：

- `SoftStepBehavior`/`HardPityBehavior` 同步退役为 preset（CounterTracker + 对应 Modifier）
- `SoftPityMixin` + 3 个 `_soft` 类同步退役
- **deltas 展开职责移交（M6）**：`SoftPityMixin._init_soft_pity` 唯一做 `soft_start/soft_end/soft_increment → deltas` 展开（[pity.py:511-528](gacha_simulator/core/pity.py#L511-L528)），退役后该展开移入 preset 工厂（依赖 create_behavior 已透传的 soft_* 参数，[pity.py:864-874](gacha_simulator/core/pity.py#L864-L874)）

`rotating_soft` = rotating 的 Tracker/Modifier 各加一项，`_SOFT_SUFFIX_TYPES` 处理移除；任意 Tracker × 任意 Modifier 自由组合，不再需要每组合一个类。

**施工分工（2026-10-06 用户裁决）**：

| 项 | 内容 | 归属 |
|---|------|------|
| **甲** | §3.4.1 的语义规格 + §3.1.5.2 的 `t` 定义 | **P64（已写入）** |
| **乙** | 改 `SoftStepBehavior._compute_probabilities` 的分配式、改 `_expand_soft_to_deltas` 的首段边界与档数、同步改反推函数 `_deltas_to_soft_interval`（**该反函数无生产调用方，仅测试**，见下表第 3 行） | **已于 2026-10-06 落地**（三处全改，当日全量 1953 passed / 35 skipped；基线对照经 `SOFT_SEMANTICS_EXEMPT` 豁免后 PASS）。**同日追加端点裁决与一轮独立审查修复**，见 §3.4.1.2，全量升至 1960 passed / 35 skipped |

**乙的改动清单（3 处，2026-10-06 试改实测）**：

| # | 位置 | 改动 |
|---|------|------|
| 1 | `pity.py` `SoftStepBehavior._compute_probabilities`（[pity.py:306-323](gacha_simulator/core/pity.py#L306-L323)） | 重分配段改为百分点语义 + A 内按当前形状分配（19 行 → 12 行） |
| 2 | `config_toml.py` `_expand_soft_to_deltas`（[config_toml.py:1581](gacha_simulator/core/config_toml.py#L1581)） | 两条 `return` 的首段由 `s` 改为 `max(0, s - 1)`；`soft_interval` 的档数另经同日裁决改为 `end - start + 1`（§3.4.1.2） | <!-- REVIEW-R1-FIX: ISSUE-001 -->
| 3 | `config_toml.py` `_deltas_to_soft_interval`（[config_toml.py:1652-1675](gacha_simulator/core/config_toml.py#L1652-L1675)） | 它是第 2 处的反函数，`return (n1, n1 + n2)` 须同步为 `(n1 + 1, n1 + n2 + 1)`，否则 `TestDeltasRoundTrip` 失败。**更正（2026-10-06 实测）**：该反函数无生产调用方，写回路径不经它，故此项不影响 GUI round-trip | <!-- REVIEW-R1-FIX: ISSUE-005 -->

**第 3 处不做则**：`tests/test_config_toml.py::TestDeltasRoundTrip` 失败（实测 `(72, 0.0) == (73, 0.0)`）。

**更正（2026-10-06 实测）**：此处原写「且 GUI「加载 → 保存」会静默改小 `start` 与 `end`」，该断言不成立。`_pitydef_to_toml()` 直接取 `PityDef.soft_start` / `soft_end` 写回，全库无任何生产路径调用 `_deltas_to_soft_interval()`（仅 `tests/test_config_toml.py` 调用），故第 3 处漏改只影响测试，不影响 GUI。

**GUI 写回路径实测（2026-10-06）**：真实 `config.toml` 经 `load_toml → save_toml → load_toml`，`PityDef` 逐字段差异 0、`[pity]` 段逐行一致；`soft_interval` / `soft_additive` / 直写 `deltas` 三种形态均保值。同轮实测查出并已修复一处独立缺陷：后缀型（`rotating_soft` / `rotating_cr_soft` / `targeted_soft`）的 `soft_start` / `soft_end` / `soft_increment` 此前被 `_pitydef_to_toml()` 整体丢弃，重载后落到注册表默认值 start=74 / end=90，用户配置被静默改写。修复见 commit `af9537c`。

**为什么分开（当时的理由，已成历史）**：乙会改变所有 soft 配置的模拟数值。P64 的验收口径之一是「与旧实现逐场一致」，若与甲同时动乙，P64 的对照基准当场失效，两件事互相干扰。**该顾虑已随乙在当日独立落地而消解**（`a6c9b31`，2026-10-06）：P64 的 M1 对照基准改为「与**改后**的旧类逐场一致」，P79 的 3 组 golden 基线经用户裁决**重固化**为新基线（`68770ce`，2026-10-07，同时删除 `SOFT_SEMANTICS_EXEMPT` 豁免分支）。故本段只作分工来历的记录，**不代表乙仍未落地**。

##### 3.4.1.1 乙前 vs 乙后的数值差（2026-10-06 实测；2026-10-06 补齐可复现输入）

**可复现输入。** 两行各用一组分布，共同设定：`soft` boost = 50、`target_featured=False`（目标组 = 全部 SSR 槽）、`scope_slots['ssr'] = (f1, f2, s1)`、`featured_slots['ssr'] = (f1, f2)`、`rarity_rank` 使 sr / r 均在可夺池内：

| 行 | `base_probabilities`（f1 / f2 / s1 / sr1 / r1） | `current`（同序） |
|----|----------------------------------------------|------------------|
| **A** 不变式成立（featured 组内 base 与 current 同为 2:1） | 0.004 / 0.002 / 0.005 / 0.05 / 0.939 | 同左 |
| **B** 不变式破坏（featured 组内 base 9:1、current 2:1） | 0.018 / 0.002 / 0.0166667 / 0.05 / 0.9133333 | 0.009 / 0.001 / 0.02 / 0.05 / 0.92 |

（`sr1` / `r1` 只决定可夺池大小，不单独出现在下面结论里；乙前的实现另需 `base_probabilities`，故两行都给出。）

**逐格实测**：

| 行 | 实现 | f1 | f2 | s1 | sr1 | r1 | **featured 合计** |
|----|------|----|----|----|-----|----|-----------------|
| A | 乙前 | 0.183818 | 0.091909 | 0.229773 | 0.025000 | 0.469500 | 0.275727 |
| A | **乙后** | 0.185818 | 0.092909 | 0.232273 | 0.024722 | 0.464278 | **0.278727** |
| B | 乙前 | 0.247091 | 0.027455 | 0.240455 | 0.025000 | 0.460000 | 0.274545 |
| B | **乙后** | 0.159000 | 0.017667 | 0.353333 | 0.024227 | 0.445773 | **0.176667** |

**「差」的口径（原未写明，2026-10-06 补）**：指**全部槽位的最大绝对差**，不是 featured 合计之差。A 行的 5.22e-03 来自 `r1`（0.469500 → 0.464278）；B 行的 1.13e-01 来自 `s1`（0.240455 → 0.353333）。featured 合计之差另算：A 行 0.003000、B 行 0.097878。

**复现方式**：以 `git archive a6c9b31^` 抽出乙前代码树，与当前树各按上表输入调 `SoftStepBehavior._compute_probabilities(ctx, 1)`（`deltas = ((0, 0.0), (1, 50.0))` 使 boost 恰为 50）。

两处差异各有来源，**不可混为一谈**：

| 差异 | 来源 | 量级 |
|------|------|------|
| 不变式成立时也差 5.2e-03 | **修正 ①**（转移量由「源组的 x%」改为「+x 个百分点」） | 小 |
| 不变式破坏时差 1.13e-01 | **修正 ① + 旧实现的目标内分配** | 大 |

**旧实现的目标内分配**：它把增量按各**槽**的基础权重和（`w_s/Σw`）分给 featured 与非 featured 两个槽。**该分配只有在「组内比例 = 基础权重比例」时才等价于「保持当前比例」**——不变式成立时两者同值，破坏时分开（上表 9:1 那一行：旧实现的 featured 合计 0.2745、新实现 0.1767）。

**乙之后该依赖消失**：新实现的目标组是一个组、A 内按当前形状分配，**不需要任何不变式**。这是本次修正的附带收益，与修正 ① ② 一并登记。

**乙的实测波及面（2026-10-06 落地当日全量 1953 passed / 35 skipped；下列为改前试改时的中间态记录。当日后续追加 §3.4.1.2 的端点裁决与审查修复后为 1960 passed / 35 skipped）**：

| 测试 | 性质 | 处置 |
|------|------|------|
| `test_config_toml.py::TestExpandSoftToDeltas` ×4 | 规格测试，断言首段 `(73, 0.0)` | 更新期望值（改后才是正确的） |
| `test_config_toml.py::TestDeltasRoundTrip` | 反推与展开不一致 | 由第 3 处修复 |
| `test_pity.py::TestSoftStepProgress::test_boost_zero_below_start` | 断言 `_cumulative_boost(73) == 0` | 更新期望值 |
| `test_p79_stop_condition_baseline::test_equivalence_verify_script_passes` | **golden 基线对照** | 见下 |

**基线影响**：`tests/fixtures/p79_golden/` 共 **9 组**，其中 **5 组受影响**，分两类：① **3 组走 soft 语义豁免**（`smart` / `pool_quota` / `draw_target`，各 6 个字段变化，实测）；② **2 组整组豁免**（`stop_on_target` / `fixed_count`，各 13 个字段变化，属 P79 1c 的时间冻结失效形态修复，与乙无关）。另 **4 组逐字段一致**（`pity_reserve` / `target_hunting` / `no_draw` / `plugin__example_phased`）。处置：先以 `SOFT_SEMANTICS_EXEMPT` 整组豁免，后经 2026-10-06 独立审查指出该豁免把三组永久移出回归网（见 §3.4.1.2 第（三）1 条），**当日改为重固化这三组 golden**（用户裁决）：新基线已记入其 `meta.note`，三组重新纳入逐字段对照，`p79_verify.py` 不再有 soft 专属豁免集。**旧基线（乙前的值）见 git 历史**，即重固化提交的父提交 `f0fc5f5`。

**风险评级：低**。依据：代码面 3 处共约 25 行；无 golden 之外的数值资产；项目未发布、无历史结果文件；基线处置有现成机制。**唯一需要留意的是第 3 处**（反推函数），漏改不会报错、只会让 GUI 静默改数。

**两处附带的既有问题（登记，不在本轮处理）**：

1. **`soft_additive` 的 `soft_end` 是死字段**：`_expand_soft_to_deltas` 对 `soft_additive` 只算 `n_steps = 100/inc + 1`，`end` 不参与。手册的 `soft_additive` 也确实不写 `end`，故功能与配置均未受影响，但 `PityDef.soft_end` 对该类型空转。
2. **手册第 1088 行注释有误**：写 `start = 50, increment = 2.0  # 每抽 +2%，第 70 抽 100%`，按任何模型都算不出第 70 抽 100%（20 抽 × 2% = 40%）。属手册笔误，归手册同步面。


##### 3.4.1.2 端点裁决与一轮独立审查的修复（2026-10-06 追加）

**（一）`soft_interval` 的端点语义（用户裁决）**

修正 ② 只把首段改成 `start-1`，档数仍是 `end - start`，于是整条爬升**平移一抽**：首个增量落在 `start`（这是要修的），但 100% 也提前到了 `end-1`（这是副作用）。仓库真实配置 `config.toml` 的 `ssr_soft`（`soft_interval` 80/90）直接受影响。

裁决：两种语法糖的端点语义**不同**，按配置形态区分：

| 形态 | 指定内容 | 语义 | 档数 |
|------|---------|------|------|
| `soft_interval` | 头 + 尾 | `start` 是开始提升那一抽，`end` 是**到达 100% 那一抽**，两端都含 | `end - start + 1` |
| `soft_additive` | 起始点 + 增量 | 只按增量累加，**哪一抽累计到 100% 就是哪一抽**，不设终点 | `int(100/increment) + 1` |

落点：`_expand_soft_to_deltas` 的 `soft_interval` 分支改 `n_steps = e - s + 1`（`e < s` 时兜底 `e = s`，单档 100%），`soft_additive` 分支不动；反函数 `_deltas_to_soft_interval` 同步改回 `(n1 + 1, n1 + n2)`。

实测（`ssr_soft` 80/90）：`deltas = ((79, 0.0), (11, 9.090909))`，第 80 抽 9.09%、第 89 抽 90.91%、**第 90 抽 100%**。此前（修正 ② 的中间态）是 `((79, 0.0), (10, 10.0))`，第 89 抽即 100%。

| 口径 | 爬升区间 | 首个增量 | 100% 点 |
|------|---------|---------|--------|
| 修正前 | `[start+1, end]` | 第 81 抽 | `end` |
| 修正 ② 中间态（错） | `[start, end-1]` | 第 80 抽 | `end-1` |
| **本轮定稿** | `[start, end]` | 第 80 抽 | `end` |

**（二）TOML 写回的三处修复（同日独立审查提出，已修）**

| # | 问题 | 实测反例 | 修法 |
|---|------|---------|------|
| 1 | 后缀型写回分支条件过窄：只给 `increment` 或只给 `end` 时整条丢弃 | `rotating_soft, end=80`：往返前 `((73,0.0),(6,16.666667))`，往返后 `((73,0.0),(16,6.25))`（落回默认 74/90） | 分支条件放宽为「三键任一非 None」，三键各自独立写出 |
| 2 | 读写优先级相反：读取侧 `deltas` 优先，写回侧语法糖优先 | `soft_interval` + `deltas=[[10,1.0],[5,2.0]]` + `start=73,end=90`：往返前 `((10,1.0),(5,2.0))`，往返后 `((72,0.0),(18,5.555556))` | 新增 `_sugar_matches_deltas()`：写回语法糖的前提是它展开后与 `p.deltas` 逐段相同，否则写 `deltas` |
| 3 | 测试键名修复不彻底：`TestP56TypeParsing` 的 parametrize 用 dict 字面量 `{'soft_start': …}`（冒号），未被上一轮的 `soft_start=`（等号）替换命中，新增的值级断言被守卫整体跳过 | `if 'start' in extra:` 恒为 False | parametrize 改用 `start`/`end`；守卫补 `else` 分支；断言按「后缀型 deltas 为 None / 非后缀型非 None」分支 |

修后实测七种组合（后缀型三键单独与组合、`soft_interval` 的 `deltas`+语法糖并存、只给 `start`、`soft_additive`）全部「往返前后引擎 deltas 一致」。

**（三）本轮登记、未处置的审查发现**

1. ~~**`SOFT_SEMANTICS_EXEMPT` 的回归效力**~~（**2026-10-06 已处置**，用户裁决取「重固化」）：该分支只断言 `final_time == env.end_time` 后 `continue`，**不做任何字段比较**，且与 `EXEMPT_STRATEGIES` 分支逐行重复，后果是 `smart` / `pool_quota` / `draw_target` 三组**永久退出逐字段回归对照**，而这三组恰是软保底数值改动的核心风险面。**处置**：重固化这三组 golden（`meta.note` 已记明为新基线），删除 `SOFT_SEMANTICS_EXEMPT` 与其分支，三组重新纳入逐字段对照。重固化前后的逐字段差异实测为 `card_counts` / `draw_card_ids` / `pool_card_counts` 三项（另加全局白名单三项）；同批重跑确认其余 6 组的 `compact` 未受任何非白名单字段影响。**连带改动**：`tests/test_p79_stop_condition_baseline.py::test_baseline_snapshots_are_pristine` 原断言「全部快照版本 2、无 `iterations` / `warnings`」（即「全是改动前产物」），重固化后该前提不再成立，故改为**两类形态契约**并新增 `REFROZEN` 白名单：未重固化的 6 份仍须是版本 2 无该两字段，`REFROZEN` 内的 3 份须是版本 3 含该两字段。新增一份重固化必须同时改该白名单，从而「悄悄重固化」仍然失败。**遗留**：本节 §3.4.1.1 的 6 个数值仍无测试钉住（全库 grep 只命中本文档），重固化把「新基线是对的」这一判断交给了本次裁决而非断言。
2. **§3.4.1.1 表的第 2 行无法由表头所述池复现**（第 1 行可精确复现）：表头 base 的 f1:f2 = 2:1，旧实现保持目标组内当前比例，输出比必落在 `(2, ρ)` 开区间，而表内输出恰为 9.0（要求 steal = 0），同行 s1 上升又要求 steal > 0，两者矛盾。审查给出一组可逐位吻合的反解分布，但原始 harness 未留档，故记为「与表头所述池不符」，不定性为编造。
3. **表下「差」的口径未写明**：两个值等于「全部槽位的最大绝对差」，不等于表内加粗的「featured 合计」列之差，易误读。
4. ~~`_check_pity_format` 的提示语自相矛盾~~（**2026-10-06 已修**）：原提示语写「含 start/end/func 等字段」，紧接着又建议「软保底爬升用 start + end」，把 `start`/`end` 同时当旧格式标志与正确写法。现改为按判据陈述（「带 start 却缺 scope，或含 func 字段」）并附 `func` 专项提示。**2026-10-09 口径同步**：`func` 的处置在搁置条目 11 中已裁决为**维持硬拒**（与 `scope` 白名单同风格，前提是先做「`load_toml` 失败原子」），随本计划 `§七 S4c` 落地；本条原写「本身未裁决」与搁置记录不一致，现以搁置记录为准。
5. ~~跨模块重复常量~~（**2026-10-06 已修**）：`_SOFT_SUFFIX_TYPES`（`config_toml.py` 模块级 / `pity.py` 的 `CounterBasedBehavior` 类属性）与 `_EVENT_DRIVEN_TYPES`（两处）各两份。已把两处函数局部常量升为可导入的模块级 / 类属性，并新增 `TestDuplicatedConstants` 钉住两组相等，防漂移。
6. 两处不可达守卫：`pity.py:511` 的空 deltas 分支、`pity.py:225-229` 的 `deltas is None` ValueError（被 `TypeError` 顶掉，诊断信息永不触发）。

#### 3.4.1 `deltas` 的两处语义修正（2026-10-06 实测确认；**同日落地**）

> **本节记录两处既有实现的语义错误**——**两处均已于 2026-10-06 当日修正落地**（commit `a6c9b31`，用户裁决取「乙」案）。它们不由 P64 引入，但 P64 的软保底规格若照**改前**形态书写，会把错误固化。**P64 按修正后的语义写规格；代码修正归「乙」，已落地**——分工与三处改动清单见 §3.4 的施工分工表，数值差见 §3.4.1.1，端点裁决与同轮审查修复见 §3.4.1.2。
>
> **读法（强制）**：下文凡写「现状 / 改前」处，一律指 **2026-10-06 修正前**的实现；写「改后 / 已落地」处指当前代码。**当前代码是修正后的形态**（`SoftStepBehavior._compute_probabilities` 取百分点绝对量、`_expand_soft_to_deltas` 首段取 `start−1`），不是本节表格里「改前」那一行的数值。

**判据来源：手册自带的数字。** 手册 §1610 写「基础 0.8%，第 65 抽起每抽 +5%，第 **79** 抽 ~**75.8%**」。这个数同时定死两件事：

| 模型 | 第 79 抽算得 | 与手册 75.8% |
|------|-------------|-------------|
| **A 的概率 +x 个百分点**（`0.008 + 5×15/100`） | **0.758000** | **✓ 精确命中** |
| 从源组按比例取 x%（`0.008 + 0.992×0.75`） | 0.752000 | ✗ 差 0.6 点 |
| **改前实现**（2026-10-06 前） | **0.702400** | ✗ 差 5.6 点（两处错误叠加：比例模型 + `start` 偏移） |

**修正 ①：`deltas` 的增量是「百分点」，不是「源组的百分比」**

```
改前：steal = p(Q) × boost% / 100      ← 参数被当成「取源组的百分之几」（乘法）
改后：t     = boost% / 100             ← 百分点，直接就是转移量（加法）   ← 已落地
```

两者差一个因子 `p(Q)`。因 `p(Q) ≈ 1`（低稀有度池占绝大部分），前期差异极小（第 75 抽 0.0703 vs 0.0710），**到爬升后段才拉开**（第 89 抽：改前 0.9009、改后 0.966）。这是它长期未被发现的原因。

**修正 ②：`start` 含首抽**

`_expand_soft_to_deltas`（[config_toml.py:1581](gacha_simulator/core/config_toml.py#L1581)）**改前**对 `start=74` 产出 `((74, 0.0), …)`，而 `_cumulative_boost`（[pity.py:242-263](gacha_simulator/core/pity.py#L242-L263)）按「前 74 抽增量 0」解释，故**第 74 抽无加成、第 75 抽才有**。手册写的是「74 抽**起**」，即第 74 抽即加成。**改后**首段取 `start−1`（已落地，见 §3.4 的乙改动清单第 2 行）；另注意 `soft_interval` 的**档数**另经同日裁决改为 `end − start + 1`（§3.4.1.2 的端点表，使 100% 恰好落在 `end`）。<!-- REVIEW-R1-FIX: ISSUE-001 -->

**`deltas` 的格式与含义均不变**：`((段长, 每抽增量), …)`，增量单位是百分点。改的只是**展开端**（首段 `start−1`）与**消费端**（不再乘 `p(Q)`）各一处。**两处均已落地**（2026-10-06，`a6c9b31`）；本节保留「改前 / 改后」对照，是为说明规格的来历与判据。

**P64 的规格写法**：`soft` 的转移量是

```
t = boost%(counter) / 100        # boost% 经 _cumulative_boost 从 deltas 得出
```

其中 `boost%` 的语义是「目标组概率应增加的百分点数」。`t` 是 `compute_delta()` 内的**局部变量**，不是 Modifier 的构造形参（它由 deltas 与当前 counter 算出，无独立配置来源）。

<!-- REVIEW-R1-FIX: SOFT-SEMANTICS -->

### 3.5 Lifecycle 统一（P64 增量能力）

`deactivate_on_early_hit` 目前只在 counter 驱动型（[pity.py:332-335](gacha_simulator/core/pity.py#L332-L335)、[pity.py:408-411](gacha_simulator/core/pity.py#L408-L411)）实现，且 config_toml 对事件驱动型配置该参数直接抛 ConfigError（[config_toml.py:686-691](gacha_simulator/core/config_toml.py#L686-L691)<!-- REVIEW-R1-FIX: ISSUE-929 -->）。P64 统一进 Lifecycle 包装层，使全部类型可用。**必须同步移除 config_toml 的拒绝分支（H3）**，否则增量能力无法配置。**此为增量能力（旧事件驱动类无此能力），不在等价性范围内**。覆盖手册 §16.6 终末地 80/120 协调「若 120 用 rotating 表达」的场景。<!-- REVIEW-R1-FIX: ISSUE-005 -->

### 3.6 与引擎/配置/GUI 对接

- **PityEngine**（[pity.py:1122](gacha_simulator/core/pity.py#L1122)）：调度层接口签名不变，`before_draw`/`after_draw`/`get_probabilities` 调用链不变，P75 rebind 由 Pity 统一实现。**G5 priority（2026-09-18 裁决：保留并实施，与接线配套）**：`_resolve_order`（[pity.py:914](gacha_simulator/core/pity.py#L914)）排序 key 加 `priority` 优先级（位于稀有度 rank 之后、type order 之前）。**透传（M3）**：`PityDef` 新增 `priority: int = 0`，`create_behavior` 以 **构造形参 `Pity(..., priority=pdef.priority)`** 传入（**ISSUE-203**：原稿写的「`create_behavior` 构造后设置 `pity._priority` 属性」与 §3.1.4 骨架已定稿的 `priority: int = 0` 构造形参 + `self._priority = priority` **互斥**，同一份计划对同一个值给了两条替代机制；现以骨架为准，**「构造后设属性」写法废弃**。`create_behavior` **自身**签名不改——它本就是 `Pity(...)` 的唯一构造点，直接多传一个关键字实参即可）——priority 全 0 时排序结果与现状完全一致，显式 priority 覆盖 type 顺序。<!-- REVIEW-FIX-PREV: ISSUE-203 -->**论证**：接线（§1.5 裁决 1）使排序键成为管道顺序的唯一来源，配置者不再能靠「TOML 书写顺序」控制优先级，`priority` 因此成为唯一的顺序覆盖入口；当前 `_BTYPE_ORDER` hard=1 < targeted=3 已满足绝区零 G5 需求，priority 的价值是「显式化现有隐式顺序 + 提供未来场景覆盖」。**接线本身建议独立先行（§1.5 实施方案），本项随主线实施**<!-- REVIEW-R1-FIX: ISSUE-001 --><!-- REVIEW-R1-FIX: ISSUE-002 -->
- **PityDef/TOML**：现有 type 名继续有效（preset 别名）；`rotating_inverse` 新 type 无需新字段；`PityDef.priority` 新增；参数透传（[pity.py:864-892](gacha_simulator/core/pity.py#L864-L892)）逻辑保留，目标从具体类变 preset 工厂（**工厂签名 `preset(pdef)`，逐条可配字段由工厂消费——ISSUE-030，见 §3.2**）

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-1 -->
**PityDef 字段级透传纪律（AUDIT-BREAK-1，强制，2026-09-22 补）**

问题：从 `ConfigStore` 到运行期引擎之间是**枚举式透传**——**引擎/配置侧三处 + GUI 侧五处（ISSUE-911，2026-10-01 补）**。二者是**两段不同的键空间**：引擎侧三处（#1–#3）用 `PityDef` **字段名**，GUI 侧（#4–#8）自成一套内部 dict 键名，其中 `get_config` / `set_config` 两处还用**别名**（`type` / `start` / `end` / `increment`）。**漏任意一处，字段即在某条路径上静默落回默认值**，且配置层与测试都看不出异常：

| # | 位置 | 现状 | 漏写的后果 |
|---|------|------|-----------|
| 1 | `batch_simulator.from_config_store` 的 `pentry` dict（[batch_simulator.py:1168-1193](gacha_simulator/service/batch_simulator.py#L1168-L1193)，**S4b 起为 `dataclasses.fields(PityDef)` 驱动**。**订正（2026-10-13）**：原写「**24 键**」，而 `PityDef` 实测 **26 个 dataclass 字段**，逐字段枚举已随 S4b 改造删除） | 逐字段 `getattr(pd, 'x', 默认)` | 该字段在 GUI / 批处理路径**恒为默认值**，配置层看不出任何异常 |
| 2 | `_build_pity_engine_from_gui` 的 `_PityDef(...)` 重建（[batch_simulator.py:218-243](gacha_simulator/service/batch_simulator.py#L218-L243)） | 逐字段 `p.get('x', 默认)` | 同上（`_PityDef` 是 `PityDef` 的别名，[batch_simulator.py:202](gacha_simulator/service/batch_simulator.py#L202) 的函数内 import；**ISSUE-915** 更正原引 `:193`——那是 `_build_pity_engine_from_gui` 的定义行）<!-- REVIEW-R1-FIX: ISSUE-915 --> |
| 3 | `retreat_config` 的浅拷贝（[retreat_config.py:123-142](gacha_simulator/core/retreat_config.py#L123-L142)，24 个显式字段） | 逐字段复制 | 同 1 |
| 4 | `gui/config_panel.py` 的 `set_config()` 保底段（[config_panel.py:6541-6605](gacha_simulator/gui/config_panel.py#L6541-L6605)） | config dict → `PityDef(...)` → `self._pity_defs`，两端**均用别名键**（`p.get('type')` / `p.get('start')` / `p.get('end')` / `p.get('increment')`） | TOML 里的新字段在 **GUI 打开时**即丢；此后任何一次保存都会把它写没 |
| 5 | `gui/config_panel.py` 的 `_refresh_from_store_impl()` 保底段（[config_panel.py:7443-7468](gacha_simulator/gui/config_panel.py#L7443-L7468)） | `store.pity.pities` → `_pity_defs` 逐键 dict（字段名口径） | 同 4（这是「从 store 刷新」的一条独立回填路径，与 #4 并列） |
| 6 | `gui/config_panel.py` 的 `_flush_pity_current_detail()`（[config_panel.py:3244-3324](gacha_simulator/gui/config_panel.py#L3244-L3324)） | 控件 → `self._pity_defs[row]` 的**实时**写回（键为字段名口径） | 同 4，且它是 #4 / #5 / #8 三条的上游——`_pity_defs` 是该文件内保底态的**单一大本营** |
| 7 | `gui/config_panel.py` 的 `get_config()` 保底段（[config_panel.py:6336-6366](gacha_simulator/gui/config_panel.py#L6336-L6366)） | `_pity_defs` → config dict（**别名** `'type': pd.get('btype')`） | 导出即丢，GUI→TOML 的保存链路在此断 |
| 8 | `gui/config_panel.py` 的 `apply_to_store()` 保底段（[config_panel.py:7167-7196](gacha_simulator/gui/config_panel.py#L7167-L7196)） | `_pity_defs` → `PityDef(...)` 逐字段重建 | 同 4；`get_config()` 首行即调它，故 #7 的口径实际由 #8 决定 |
| **~~GUI 的 `reads` 通路（ISSUE-911 追加）~~**（**2026-10-06 删除**：字段取消） | 原：`PityDef.reads`（S9-2）**在 GUI 侧无任何控件与键**（计划全篇对 `reads` 的 GUI 通路零声明） | 取保守路径：**不加控件，但在 #4–#8 五处保留该键的原样透传**（`_pity_defs` 与 config dict 各留一条 `'reads'`），使 TOML 写好的 `reads` 经「GUI 打开 → 导出」不被抹掉 | 若因「不建控件就不透传」而漏掉，则**凡经 GUI 往返一次的配置，`reads` 静默清空**，且 S9-4 的 `reads` 运行期送达验收（TOML → `ConfigStore` → `pentry` → `_PityDef` → 引擎）在 GUI 路径上恒不覆盖 |

已定：`priority`（S4b）与 ~~`reads`（S9-2，已取消）~~ 各自随字段定义同步补齐三处（§七两步的目标文件已含这三处）。**但「逐个字段补」的写法会随字段新增反复断裂**——例如 `max_triggers` 本期按 §七「本轮处置表」第 3 项**不接线**（只验类语义），一旦将来接线就必须记得改三处，否则又是一个静默失效点。

强制纪律（三条）：

1. **同 commit 纪律**：任何 `PityDef` 新增字段（含 `priority` / ~~`reads`~~ / 将来的 `max_triggers`）**必须在引入该字段的同一子块内**同步三处透传点，不得留到后续子块；三处透传点与该字段的定义/解析**同一 commit 落地**。
2. **改造成 dataclass 驱动（S4b 落地，原写「建议」现升为强制）**：三处一律改为由 `dataclasses.fields(PityDef)` 驱动（`pentry = {f.name: getattr(pd, f.name) for f in fields(pd)}` / `_PityDef(**{f.name: p[f.name] ...})` / 浅拷贝同式），使「新字段」在结构上不可能被漏掉。逐字段枚举与 `pentry` 的**逐字段键清单**（原写「24 键」，`PityDef` 实测 26 字段，数字已过期）**一经改造即删除**，不得与新写法并存（并存即第二真相源）。
3. **防回归断言（S4b 落地）**：新增一条**字段全量 round-trip** 测试——`for f in fields(PityDef)`，用非默认值构造 `PityDef`，经 TOML round-trip → `ConfigStore` → `pentry` → `_PityDef` 后逐字段断言等值；并断言 `pentry` 的键集 `== {f.name for f in fields(PityDef)}`（键集相等而非包含，防漏也防多）。该断言使「第 N+1 个字段漏透传」在 CI 期即失败，不再依赖人工记忆。落点见 §七 S4b 与 §六。

<!-- REVIEW-R1-FIX: ISSUE-910 -->
> **改造前提：四个别名键必须先废弃（ISSUE-910，强制，2026-10-01）**——第 2 条「一律改为 `dataclasses.fields(PityDef)` 驱动」在**别名制**下会**静默算错**，不是一个可以照抄的式子：
> - **事实**：`pentry`（引擎侧 #1）用的是**别名键**——`'type'` / `'start'` / `'end'` / `'increment'`（[batch_simulator.py:1168-1193](gacha_simulator/service/batch_simulator.py#L1168-L1193)），分别对应 `PityDef` 的 `btype` / `soft_start` / `soft_end` / `soft_increment`；其唯一消费者 `_build_pity_engine_from_gui` 的 `_PityDef(...)` 重建（[batch_simulator.py:218-243](gacha_simulator/service/batch_simulator.py#L218-L243)）正按这四个别名读回（`btype=p.get('type', 'soft_interval')` 等）。
> - **照抄式子的后果**：`pentry = {f.name: getattr(pd, f.name) for f in fields(pd)}` 产出的是 `btype` / `soft_start` / `soft_end` / `soft_increment` 四个**字段名**键，而读端仍找 `type` / `start` / `end` / `increment`——`btype` 落回默认 `soft_interval`（软保底类型全变）、软保底三段参数整体丢失，**且不报错**。
> - **键集断言的处境**：`assert set(pentry) == {f.name for f in fields(PityDef)}` 在别名制下**恒不相等**（多四个别名键、少四个字段名键），只加断言不改名 = 守卫恒红。
> - **故强制前提**：改造必须**两处同 commit 改名为字段名**——写端（`pentry` 的四个键）与读端（`_PityDef(...)` 的四个 `p.get(...)`）一并改为 `btype` / `soft_start` / `soft_end` / `soft_increment`，此后第 2 条的构造式与第 3 条的键集断言才同时成立。同理，GUI 侧 #7 / #4 的别名（`'type': pd.get('btype')`、`p.get('start')`）须与 #6 / #8 的字段名口径统一。**这四个键的翻译关系是本条改造的前提，未登记即等于埋一个静默失效点**（§七 S4b 同条）。**改名的两处未登记消费面（ISSUE-918，2026-10-01，与五处同批）**：① `get_config` 的 `'type'` 键被**同文件** `_do_update_preview` 逐条读取（[config_panel.py:6046](gacha_simulator/gui/config_panel.py#L6046) 的 `btype = pdef.get('type', '?')`）——改名后 GUI 预览里**每条保底的类型打印 `?`**，而 `preview_text` **全库无测试断言**（`grep -rn preview_text` 仅命中 config_panel.py 自身），属**静默失真**（不是丢字段，是显示错值）；② [tests/gui/test_config_panel_pity.py:220](tests/gui/test_config_panel_pity.py#L220) 的 `assert "type" in pdef` 是**正断言该别名键存在**，改名即必红。二者落点见 §七 S7a。<!-- REVIEW-R1-FIX: ISSUE-918 --><!-- REVIEW-R1-FIX: ISSUE-911 -->

- **GUI config_panel**：**2026-09-18 事实修正（两处）**——① 保底 type 下拉**不是** registry 驱动，而是硬编码列表 `_PITY_TYPES`（[config_panel.py:2019-2031](gacha_simulator/gui/config_panel.py#L2019-L2031)，10 项；[config_panel.py:2084](gacha_simulator/gui/config_panel.py#L2084) 处 `addItems`），新增 `rotating_inverse` 须**手工追加**该列表，否则 GUI 不可选（由 registry 驱动的是**参数控件**，[config_panel.py:2765-2772](gacha_simulator/gui/config_panel.py#L2765-L2772)，该部分「零改动」成立）；② **GUI 现无 reset 控件**，`_apply_pity_edit` 不写 `pd['reset']`，`reset` 仅在 load/save 路径透传（[config_panel.py:6349](gacha_simulator/gui/config_panel.py#L6349)、[config_panel.py:7190](gacha_simulator/gui/config_panel.py#L7190)），故 G16 的 GUI 部分是**新建控件**而非「下拉加一项」；③ priority 编辑控件（G5）同为新建；参数控件零改动
- **GUI config_panel（`_PITY_TYPES` 生成式改造 = **待改造**，落点 S6a；**非既成事实**）**：**现状（2026-10-01 实测）**：`_PITY_TYPES` 仍是**硬编码 10 项字面量列表**（[config_panel.py:2019-2031](gacha_simulator/gui/config_panel.py#L2019-L2031)，[config_panel.py:2084](gacha_simulator/gui/config_panel.py#L2084) 的 `addItems` 直接消费它）；全仓与**全历史**检索生成式写法 `_PITY_TYPES = [(k, v` **零命中**（从未存在过）；`1dbc9b0`（2026-09-28，message 含「保底 type 下拉改 registry 驱动」）**只改了本计划文件**（15 insertions / 7 deletions），未动任何代码。故上一条（2026-09-18 事实修正：硬编码、须手工追加）**当前成立**，本条是它之后**要做的改造**，不是对它的更正——两条不互斥。**改造内容（三项同 commit，S6a 施工）**：① [config_panel.py:2019-2031](gacha_simulator/gui/config_panel.py#L2019-L2031) 的字面量列表改为生成式 `_PITY_TYPES = [(k, v["display_name"]) for k, v in BEHAVIOR_REGISTRY.items()]`；② registry 的 **5 处 `display_name` 文案对齐 GUI 现值**（registry 现为「轮换保底（带软保底）」/「轮换保底（递增概率）」/「定向保底（定轨）」等，GUI 现为「轮换+软保底」/「轮换+捕获明光」/「定轨保底」等）；③ registry 的**条目书写顺序**调整为 GUI 现值（`targeted` 在 registry 为第 7 位、在 GUI 为第 9 位，移至 `rotating_cr_soft` 之后）——`BEHAVIOR_REGISTRY` 是字面量字典（Python 3.7+ 保序），其遍历点仅 `_validate_registry` 自检与 `create_behavior` 按键查表，**均无顺序语义**。**改造理由（两条，均经实测）**：① `BEHAVIOR_REGISTRY` 的顶层 `display_name` 在改造前**全库无人读取**（[config_panel.py:3535-3539](gacha_simulator/gui/config_panel.py#L3535-L3539) 与 [config_panel.py:3726](gacha_simulator/gui/config_panel.py#L3726) 读的都是 `STOP_CONDITION_REGISTRY`，非保底），属死字段；② 项目内已有同模式先例——停止条件的下拉即 `[(key, entry['display_name']) for key, entry in STOP_CONDITION_REGISTRY.items() if not entry.get('internal')]`（同上），**保底是唯一例外**。**收益**：新增 type 自动出现在下拉；**在改造落地前，新增 type（`rotating_inverse` / `hard_exclude_owned_skip` / `hard_exclude_owned_any`）仍须手工追加 `_PITY_TYPES`**，S6a / S9-3 的「手工追加」步骤只能在改造落地后删除。**界面呈现零变化**（文案与顺序均与改造前一致）。<!-- REVIEW-R1-FIX: ISSUE-929 -->
- **config/config.toml**：新增幻塔 `rotating_inverse` + G16 示例配置。**ISSUE-913**：本文件是 P79 常驻护栏（[p79_verify.py:38](scripts/p79_verify.py#L38)）的固定输入，**示例段默认取注释形态**（不进生效 TOML），否则须同步 golden 重固化与有意变更登记，详见 §四 该文件行 <!-- REVIEW-R1-FIX: ISSUE-913 --><!-- REVIEW-R1-FIX: ISSUE-007 -->
- **GachaService 定轨识别（H1，强制）**：[gacha_service.py:275](gacha_simulator/service/gacha_service.py#L275) 用 `isinstance(bh, TargetedBehavior)` 识别定轨保底（`switch_epitomized_target`/`cancel_epitomized_path` 两条 NonDrawAction 流程）。targeted preset 化后 bh 变为 `Pity` 实例，isinstance 恒 False → 定轨流程整体失效。须改为 `getattr(bh, '_btype', '') in ('targeted', 'targeted_soft')`（或 Pity 加 `_is_targeted` 标记），波及范围表补 `service/gacha_service.py`。<!-- REVIEW-FIX-PREV: AUDIT-BREAK-4 --> **本条含一处「不报错但必崩」的补充（AUDIT-BREAK-4，强制）**：同一函数首行的**函数局部 import** `from ..core.pity import TargetedBehavior`（[gacha_service.py:253](gacha_simulator/service/gacha_service.py#L253)）必须一并删除/改写——`S4-3` 之后该符号在**发布前移除旧类**时消失，而**局部 import 只在函数被调用时执行**，故 ruff / H7 与导入期均不报错，仅当策略真的返回 `NonDrawAction`（`switch_epitomized_target` / `cancel_epitomized_path`）时才抛 `ImportError`——`NoneDrawAction` 全库唯一构造点是策略层，测试若只覆盖 `DrawAction` 路径则 CI 全绿。**S6c 的目标面因此是四处而非一处**：`:253` 局部 import、`:275` isinstance 判定、`:292`/`:294` 两处写 `selected_card`（其 `targeted_name` 变量由 :275 的循环体赋值，判定口径与 :275 **必须同源同改**，否则定位到 0 条或定位错保底时 :292/:294 会把 `selected_card` 写进错误命名空间）。**验收命令同步追加一条「策略返回 `NonDrawAction` 的端到端用例」**（§七 S6c / §六），仅断言 `isinstance` 替换不足以覆盖 `:253`。

<!-- P64-S6C-SYNC -->
**实测订正（S6c 落地后回写，2026-10-13）**：本段原写「仅当策略真的返回 `NonDrawAction` 时才抛 `ImportError`」，该句**在今天是错的**，只在**发布前一次性移除旧类之后**才成立。今日 `TargetedBehavior` 仍定义于 [pity.py:667](gacha_simulator/core/pity.py#L667)（GATE-5 保留旧类至发布前），故恢复该局部 import **能正常导入**，S6c 实施者实测「恢复局部 import 且不使用」时相关 6 条用例**全绿**。今日真正判红的变异是**同源 `isinstance` 判据回退**（对 preset 化的 `Pity` 实例恒 False，改抛 `InvalidActionError`）。**两条捕获面因此是分开的**：① 「重新引入且使用」由端到端与直调用例在调用点捕获；② 「重新引入但未使用」用例抓不到，由 **H7 的 ruff `F401`** 兜住（实测仅插入未使用的局部 import 即 `F401`、rc=1）。此外本段末句对**判据式子**的写法也与实现不同源，见 §四 该行的订正。
- **G14 动态 threshold（后续扩展）**：`RandomThresholdTracker(range=(80,100))` 每次重置随机阈值，`HardModifier` 读随机阈值判定，与 G16 同属 Tracker 维度扩展，无需新 Modifier

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
def _should_reset(self, ctx):                       # pity.py:205
    if self._reset == "featured":
        return ctx.draw.is_featured
    if self._reset == "never":
        return False                                # 新增：永不重置
    return ctx.draw.reward_rarity == self._reset
```

配套（**ISSUE-928**：原写「PityDef/config_toml 的 reset 枚举加 `"never"`」在配置层无对应物，见下）：**`_build_pity` 对 `reset` 增取值白名单**（空串 / `featured` / 稀有度名（`[rarities].ranks` 的键）/ `never`，未知值抛 `ConfigError`——与既有 `scope` 白名单**同层同形态**，落在 [config_toml.py:642](gacha_simulator/core/config_toml.py#L642) 一侧）、GUI **新建 reset 输入控件**并加「永不重置」选项（现无该控件，见 §3.6 事实修正）、一条测试（**含负例**：未知 `reset` 值抛 `ConfigError`）、手册 G16 从「🔵 待 P64」改「✅ 已覆盖」。<!-- REVIEW-R1-FIX: ISSUE-928 -->P64 主线落地后该分支由 `CounterTracker(reset_on="never")` 自然承载。

**GUI 兜底保底条目的两个非法取值（AUDIT-BREAK-1，强制，2026-10-01）**：[config_panel.py:6544-6547](gacha_simulator/gui/config_panel.py#L6544-L6547) 在 `pities_data` 为空时**就地合成**一条兜底条目 `{'name': 'ssr_soft', 'type': 'soft', 'params': {'start': …, 'end': …}, 'reset': 'any_ssr', 'pools': '*'}`。实测它的两个取值**恰好都落在本计划新增的硬拒面上**，而此前两者都只是静默失效（保底存在但不生效、且不报错）：

1. **`type='soft'` 不在 `BEHAVIOR_REGISTRY`**——实测十条目为 `soft_interval` / `soft_additive` / `soft_step` / `hard` / `rotating` / `rotating_soft` / `rotating_cr` / `rotating_cr_soft` / `targeted` / `targeted_soft`，无 `'soft'`。今天它经 `create_behavior` 的 `BEHAVIOR_REGISTRY[pdef.btype]`（[pity.py:843](gacha_simulator/core/pity.py#L843)）抛 `KeyError`，被 `PityEngine.__init__` 的 `try / except Exception`（[pity.py:1166-1174](gacha_simulator/core/pity.py#L1166-L1174)）吞成 `logger.warning` —— 保底**静默消失**。**S4-5 把该兜底改抛 `ConfigError` 之后，同一路径变成「打开即崩」**。
2. **`reset='any_ssr'` 不在 G16 白名单内**（白名单 = 空串 / `featured` / 稀有度名 / `never`）。今天它与任何稀有度名都不相等，经 `_should_reset` 的兜底分支恒 False，即**偶然地等价于「永不重置」**；白名单一落地，该条目经「GUI 保存 → TOML 重载」即在 `_build_pity` 一侧抛 `ConfigError`。
3. **附带缺陷（同一处）**：该条目的 `params` 是**嵌套 dict**，而扁平化后的 `_build_pity` 只读顶层 `p.get('start')` / `p.get('end')`（[config_toml.py:660-662](gacha_simulator/core/config_toml.py#L660-L662)），故 `pity.start` / `pity.end` 两个平台默认值（`config.toml` 的 80/90、GUI 的 74/90）在该条目上**都是丢的**——即便类型与 reset 合法，也拿不到用户填的阈值。<!-- REVIEW-R1-FIX: ISSUE-005 -->

**处置（须与 G16-1 的 reset 白名单同一 commit，不得留到 S4-5）**：**推荐 (a)** —— 把兜底条目改写为全合法形态 `{'name': 'ssr_soft', 'type': 'soft_interval', 'scope': 'ssr', 'start': int(pity.get('start', 74)), 'end': int(pity.get('end', 90)), 'reset': '', 'pools': '*'}`：`type` 换成真实的 registry 键、`scope` 必须显式写出（`_build_pity` 的 scope 白名单只放行 `[rarities].ranks` 内的小写名）、`reset=''` 在 `_should_reset` 里落回 scope 兜底分支（`reward_rarity == 'ssr'`）——与名称 `ssr_soft` 及原 `any_ssr` 的意图一致。**备选 (b)** —— 删除该兜底条目（`pities_data` 为空即留空），由 `_build_pity` 的空段 `load_warnings` 承担提示，代价是 GUI 新建配置不再自带默认保底。**两方案均须配一条回归用例**：`set_config({'pity': {'pities': []}})` → `get_config()` → `load_toml` 不抛 `ConfigError`（方案 a 下再断言 `PityEngine` 构造成功、`name='ssr_soft'` 的保底确实存在）。

> **为何必须与白名单同 commit**：白名单是**新增的硬拒**、兜底条目是**既有的非法数据**，两者落在不同 commit 就是「提交后立即崩」。同批落地的判据见 §七 G16-1 与 G16-2。<!-- REVIEW-R1-FIX: AUDIT-BREAK-1 -->
>
> **✅ 用户 2026-10-10 确认：取方案 (a)**（改写为全合法形态，保持「GUI 新建配置自带一条 soft 保底」的现状语义）。原「仅保留否决权」的标注就此关闭，本组不再计入「待人工裁决」枚举。理由：删掉兜底条目后，「一条保底都没有」这个状态在 GUI 编辑态没有任何提示面（`load_warnings` 只在加载 / 保存路径）。

### 3.9 概率操作路径重构（S8 实施方案，2026-09-21 新增）

> §3.1.2 的 D20 是**声明**（分布空间归属改为卡级），§3.1.5 是**数学形式**（乘性算子），本节是**实施方案**（改哪些函数、接口怎么变、边界怎么处理）。三者配套，缺一则 S8 不可执行。
>
> **过渡期纪律**：S1–S5 期间本节内容全部**不实施**，Modifier 内部沿用槽位法，以保证与旧类一致（§六 S1–S5 口径；**2026-10-11 订正**：该口径已按 §3.1.5.6 拆为「概率分布容差 1e-12 + 状态快照位级一致」，故此处不再写「位级一致」）。S8 一次性切换，验收对 S5 产物取 1e-12 容差。 **本轮（AUDIT-BREAK-3）补一处唯一例外**：本纪律**不覆盖 `Modifier` 基类自身的落地**——S2a-1（M1）就要交付 `Modifier` 基类，而本节下方给的基类 `apply` 默认实现体依赖 S8 才存在的两个符号（`_apply_delta` 归 S8-1、`compute_delta` 是 S8 起的方法名），照抄即 `NameError`。故 **M1 期基类 `apply` 只写占位实现 `raise NotImplementedError`，S8-1 替换为正式默认实现**（见 §3.14.3 与 §七 S2a-1）；「本节内容全部不实施」= 增量接口与引擎侧归一化不在 M1 落地，**不等于基类不落地**。<!-- REVIEW-R1-FIX: AUDIT-BREAK-3 -->

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

> **⚠ 现状路径的这处缺陷已于 2026-10-09 修复（缺陷 12）**：上段伪代码的「槽位 → 卡级（还原）」一步**曾对 SR / R 卡静默跳过缩放**——它用 `infer_rarity_from_spec` 反查槽位，而该函数只认 SSR（[pool.py:234](gacha_simulator/core/pool.py#L234)），SR / R 得到 `None` → `if slot in scale_factors` 为假。后果是喂给 `pool.draw()` 的卡级字典 Σ > 1，采样时按 `1/Σ` 稀释，**软保底效果被打折**（真实 `config.toml` 的 `ssr_soft` 第 90 抽：意图 100%、实际 50.1%）。**修法**：改 `infer_rarity_from_spec` 本体（先按 `scope_cards` 反查，未覆盖时回退原有的 `ssr_ids` / `featured_ids` 判定），一处改动覆盖三个调用点，且回退分支把 `worst_impact` 路径原样保住。**注意**：S8 仍会**删除**这个函数（ISSUE-504），此处记录的是它被删之前就已修正。完整实测、修法取舍与验收数据见 [04-问题.md](docs/01-活跃/subsystems/保底系统/04-问题.md) 缺陷 12。

**目标**（S8 后，往返全部消失）：

```
probabilities = {r.id: p for r, p in pool.rewards}              # 卡级
adjusted      = pity_engine.before_draw(key, state, probabilities)   # 卡级管道
pool._apply_probabilities(adjusted)
```

净删除：`aggregate_probs_by_rarity` 的调用（banner 侧）、`scale_factors` 段（11 行）、`infer_rarity_from_spec` 的槽位反查用途（**该用途是其全部消费者的最后一个，故函数本体随之删除**，见 §3.9.3 处置表与 ISSUE-504）。

#### 3.9.2 Modifier 接口：产出增量，引擎做归一化

**接口变更**（S8；**2026-10-08 用户裁决由因子改为增量**）：Modifier 从「返回修正后的分布」改为「返回**增量向量**」，归一化收到引擎层统一做。依据与改写面见《保底算子表示切换·因子向量转增量向量·改写方案》。

```python
class Modifier:
    def compute_delta(self, view, dist, ctx) -> Optional[Dict[str, float]]:
        """返回增量向量 {card_id: δ}；未列出的卡默认 δ = 0；None 表示恒等。

        **三参数是定稿（2026-10-06 用户裁决），不得再增形参**（§3.1.2）。

        view：状态视图。S8 期间是 PityState 的薄包装（可读全部命名空间），
              S9 后收紧为「只含自身命名空间」的 StateView（§3.10.3）。
              **订正（S9-1 审查，2026-10-14）**：上两行与代码事实不符。`StateView`
              自 **S3-1（`2200055`）** 起即为「只含自身命名空间」的定稿形态，S9-1
              在 `StateView` 本体上**零代码增量**；S8 期间各 Modifier 收到的实参
              已经是 `StateView`（11 个 registry 类型真管道实测 11/11）。
        dist：当前分布 {card_id: p}。
        ctx ：本次抽卡的静态事实（scope_cards / featured_cards / rarity_rank）。
              需要新的事实时**加字段，不改签名**。
        """

    def rebind(self, state, name) -> None:      # ISSUE-029：P75 纪律的统一接口
        """把本 Modifier 内部持有的 Counter / Flag 重绑到 per-call state（纯重定向）。
        Pity._rebind_state 无条件调用它，故方法必须存在；无状态零件可 pass，不得省略。"""

    def state_keys(self) -> tuple:
        """**声明键集（ISSUE-501）**：本 Modifier 读或写的 `PityState` 键名，只读常量、
        不依赖 state。基类默认 `()`（不碰状态的 Modifier 不覆写）；读状态的 Modifier
        （如 `SoftModifier` 读 `counter`、`RotatingModifier` 读 `guaranteed`）
        覆写为本类的键集。**条件内联后无需转发**（§3.14 已取消包装器）。
        消费面：§3.12.2 判据第 2 条「Modifier 引用了不存在的状态键」，比对基准为
        `Pity._declared_keys` 的 `trackers` ∪ `lifecycle` 并集（§3.1.4 骨架）。"""
        return ()

    def apply(self, ctx, view, dist, readonly):
        """**默认实现**（ISSUE-GATE-3-dependency-order，2026-09-22 定稿）：把本 Modifier 的增量向量
        作用到分布并归一化。`apply` 自此**不是**每个 Modifier 的必写方法——各 Modifier 覆写的是
        `compute_delta()`，`apply()` 由本基类提供。两期分工：**M1（S2 起至 S7）** 各 Modifier 直接实现 `apply`
        （§3.1.2 历史形态，返回分布）并覆写掉本默认实现；**S8 起** 各 Modifier 改实现 `compute_delta(view, dist, ctx)`，
        骨架逐项调用 `compute_delta`，本默认实现成为唯一的 `apply` 定义。**注意参数也随之收窄**：`apply` 是四参
        （含 `readonly`），`compute_delta` 是三参（2026-10-08 用户裁决，`readonly` 随「Modifier 是 pure 函数」
        一并废除），故本方法仍收四参、其内部调用 `compute_delta` 时只传三参。

        **这是「`apply()` 保留为默认实现」的承载处**（§3.1.2 / §3.9.2 原稿只写该句、未指明它住哪）：
        （原 `ConditionalModifier.apply` 转发段落已随 §3.14 改判删除；本基类的 `apply` 默认实现仍保留）
        只写 `compute_delta`——没有本基类即 `AttributeError: 内层对象无 apply`，而该调用点在每个抽卡的调度
        入口，后果是全部保底不可用（§六 的存在性断言不触发调用，捕获不到该缺口，故本条必须落成代码）。"""
        return _apply_delta(dist, self.compute_delta(view, dist, ctx) or {})

# Pity 骨架
for mod in self._modifiers:
    # ← ISSUE-505（与 ISSUE-407 同源，强制）：**遍历点一律经 `self._view_for(mod)`，
    #   不得写死 `self._view`**。声明了 `namespace` 的 Modifier 必须读到自己的命名空间，
    #   写死默认 view 会让它读错账本、恒返回 default（不报错，只让该零件静默失效）。
    #   §3.1.4 骨架的 M1 形态（`mod.apply(cctx, self._view_for(mod), out, readonly)`）
    #   已按此写；**S8 换方法名与参数**（`apply(ctx, view, dist, readonly)` →
    #   `compute_delta(view, dist, ctx)`，`readonly` 随「Modifier 是 pure 函数」一并废除，
    #   2026-10-08 用户裁决），**本行不得回退为 `self._view`**。
    d = mod.compute_delta(self._view_for(mod), out, ctx)
    if d is not None:
        out = _apply_delta(out, d)       # (out + d) / Σ(out + d)

def _apply_delta(dist, d):
    out = {c: dist[c] + d.get(c, 0.0) for c in dist}
    total = sum(out.values())
    return dist if total <= 0 else {c: v / total for c, v in out.items()}
```

<!-- P64-S8-LANDED -->
> **落地时的形态订正（2026-10-14，S8-1/2/3 原子 commit `f18045f`）**：
> ① **`_apply_delta` 与 `transfer_linear` 的实际存放处是叶子层 `core/pity_primitives.py`**，`pity.py` 只做 re-export。本节上方「Pity 骨架」代码块把它们写在编排层块内，那是**可见面**而非存放处：`Modifier.apply` 的默认实现住**实现层**，而实现层不得 import 编排层（§3.1.6 的单向依赖）。§3.9.4 的「模块归属」段已写叶子层，两处口径以叶子层为准。
> ② **基类 `compute_delta` 未覆写时抛 `NotImplementedError`**（本节只给 docstring，等价于返回 `None`）。理由：返回 `None` 会让「漏写该方法的零件」静默变成恒等，正是本计划一律按阻塞级处理的失效模式。
> ③ `compute_delta` 的三参签名未变（`(view, dist, ctx)`），本节已写明的「不得再增形参」照旧。

> **Modifier 方法名定稿为 `compute_delta`（2026-10-09 用户裁决）**：原名为 `delta`，与 **`PityDef.deltas`**（软保底的 RLE 段表 `((段长, 每抽增量), …)`，§3.4.1）**同型易混**——两者都在讲增量、都在保底子系统内，但一个是方法名、一个是配置字段。本项由《保底算子表示切换·因子向量转增量向量·改写方案》§6 第 3 项提出（该文已归档），2026-10-08 的裁决表只裁了「是否切换」「助手命名 `transfer_linear`」「`shape` 是否入签名」三项、未及本项，故 2026-10-09 补裁。**选 `compute_delta` 的理由**：不撞、符合代码库既有的 `compute_*` 惯例（`compute_scope_mappings` / `compute_gdr_from_compact` / `_compute_probabilities`…）、保留 δ 词汇（与助手 `transfer_linear` 返回的 δ、框架 `_apply_delta` 的归一化同源）、且读起来就是「算出增量」这个动作本身。**改名面**：本文 68 处（含 §3.1.2 表头、§3.9.2 签名、§3.9.4 三个调用示例、§3.1.4 骨架内循环、**§3.14.2 的现行形态段**、**§3.10.1 的「Modifier 能读到什么」句**、**§六 ISSUE-029 的断言对象**、**§3.2 preset 代码块的注释**、§七 S8-1 / S9-1 任务块）。**ISSUE-008（2026-10-09）**：原清单漏列加粗的三处，导致它们仍写 `factor`（该符号经 `factor` → `delta` → `compute_delta` 两次改名后已不存在），本轮已同批改齐。**未受影响、不得连带改**：`_apply_delta`（框架归一化函数）、`PityDef.deltas` / `soft_deltas`（配置字段）、`_expand_soft_to_deltas`（展开函数）、数学符号 `δ`。**注意 M1 期方法名仍是 `apply`**（返回分布），`compute_delta` 是 S8 起的形态，两期分工见上。

<!-- REVIEW-R1-FIX: ISSUE-501 --> <!-- REVIEW-R1-FIX: ISSUE-505 -->

<!-- REVIEW-FIX-PREV: ISSUE-029 -->
> **`Modifier` 是全部 Modifier 的公共基类（ISSUE-GATE-3-dependency-order 定稿，2026-09-22）**：`rebind`（空实现，供无状态零件继承、有状态者覆写）与 `apply`（由 `compute_delta` 导出，见上方代码）两个**默认实现都住在本基类**；`compute_delta` 是各 Modifier 唯一必写的那个。**§3.2 / §3.14.2 的每个 Modifier 示例一律写成 `class XxxModifier(Modifier):`**——原稿为裸类、无基类，使「`apply()` 保留为默认实现」无承载处，S8 之后 `ConditionalModifier.apply` 的转发目标会落成 `AttributeError`；`ConditionalModifier` 同样继承本基类并覆写 `apply` / `compute_delta` / `rebind` 三个转发。**备选（S8 一并删除 `apply` 与 `ConditionalModifier.apply`）已否决**：它与 §3.1.2 的「`apply` 保留为默认实现」互斥，还要同步改 §六 的 M1 断言口径，改动面更大且无额外收益。<!-- REVIEW-FIX-PREV: ISSUE-GATE-3-dependency-order -->
> **`rebind` 是 S8 之前就需要的接口（ISSUE-029）**：`Pity._rebind_state`（§3.1.4）自 S1 起就无条件调用 `mod.rebind(state, name)`，而本节的 `compute_delta()` 是 **S8** 才引入——两者不可混为一谈，别把 `rebind` 当成 S8 的附属接口。各 Modifier 是否持有状态零件（Counter / Flag）不同，恒等零件可直接 `pass`。~~**另注意 S12 的连带影响**~~（**2026-10-09 删，ISSUE-004：S12 已于 2026-10-06 整块取消，包装器不复存在**）：原内容为「S12 落地后 preset 里的 Modifier 一律被 `ConditionalModifier` 包裹，该包装器必须转发 `rebind`，否则首次抽卡即抛 `AttributeError`」——该风险随包装器取消而消失，`rebind` 义务回到各 Modifier 自身（§3.1.2 三族协议表已写明）。

> **与 §3.1.4 骨架的关系（ISSUE-GATE-dependency-order 定稿，2026-09-22）**：S1–S5 期间 Modifier 的方法名是 **`apply(ctx, view, dist, readonly)`**（返回修正后的分布，§3.1.2 历史形态），骨架按此调用、本节的内循环不实施；S8 引入 **`compute_delta(view, dist, ctx)`** 返回增量向量，内循环改为 `mod.compute_delta(self._view_for(mod), out, ctx)` + `_apply_delta`，`apply()` 保留为默认实现、`compute_delta()` 缺省时回退到它。**视图形参同源（ISSUE-505，强制）**：S8 的内循环**换方法名与参数**（`apply` 的四参收为三参，`readonly` 随「Modifier 是 pure 函数」废除，2026-10-08 用户裁决），`view` 实参一律继承 §3.1.4 骨架的 `self._view_for(mod)`（ISSUE-407 的零件级 view 取值，**不得写死 `self._view`**）——原稿本节内循环写死 `self._view`，与同计划 ISSUE-407 的强制纪律冲突；现全部 `Modifier` 的 `namespace` 均为 `None`（只有 `NamespaceTracker` 声明 `X_soft`），故今日无行为差异，但 ISSUE-407 的意义正是「为后续声明命名空间的零件留出读取通道」，写死 `self._view` 会让该通道在 Modifier 侧空转。<!-- REVIEW-R1-FIX: ISSUE-505 -->
>
> **~~包装器的转发义务~~（2026-10-06 随 §3.14 改判删除）**：原 `ConditionalModifier` 须转发 `rebind` / `apply` / `factor` / `state_keys` 四个方法，漏一个即每个抽卡入口 `AttributeError`。**包装器取消后本条作废**；`rebind` 与 `apply` 的默认实现仍由 `Modifier` 基类提供（§3.14.3）。

<!-- REVIEW-FIX-PREV: ISSUE-004 -->
> **`self._view` 的生命周期（ISSUE-004，强制）**：`self._view` 是 `Pity` 的成员，**每次 `_rebind_state` 必须重建**（§3.1.4 骨架已写），且 `StateView` 自身**不得在构造期缓存命名空间 dict**（§3.10.3 已改为每次 `get` 现取）。两条缺一：worker 内同一 engine 连跑 N 场模拟，第 2..N 场读的是第 1 场的账本；若 view 建于命名空间尚未创建之时（`depends_on` 依赖方构造期不写 `_active`），`state.data.get(name, {})` 会拿到一个与 state 脱联的空 dict，此后引擎 `state.set` 新建的命名空间与该 view 无关，所有读取恒返回 default 且不报错。此条同时是 §五 风险表「Pity 统一实现 Trackers/Modifiers/Lifecycle 的 rebind 委托」的落地条件。

**为什么归一化放引擎层（ISSUE-021，2026-09-22 修正论证前提；2026-10-08 换增量后重述）**：原稿的论证是「§3.1.5.2 已证三个基本算子的 ⟨m,p⟩ 恒为 1，归一化是恒等操作」，而那只在两类情形成立（`R_r` / `B_β` 且 `T ⊊ S`、`T ∩ Q = ∅`；`F` 作用于最高稀有度 scope）。**换增量后该论证整体作废**：转移族恒有 `Σδ = 0`，故 `Σ(p + δ) ≡ 1`，族内算子的归一化确实退化为恒等（§3.9.5 已记该条消失）。**但归一化仍必须保留在引擎层**，理由是接口本身允许不配平：§3.1.5.2 明确「增量向量可以是任意形状……不配平（`Σ(p + δ) ≠ 1`）都合法」，非族内的自定义 Modifier 可以不配平，故归一化是**对接口的兜底**，删不得。把它集中在引擎层有两个好处：① Modifier 只负责「算出增量」，职责单一；② 边界（`Σ(p + δ) ≤ 0`）只需在一处处理。`dist` 参数保留在 `compute_delta()` 中，因为增量依赖当前分布（转移族的 `δ_Q` 含 `p(Q)`，见 §3.1.5.2.1）。

**增量向量按稀疏给出**：Modifier 只需列出被改动的卡，其余默认 0。组级操作给出整组的增量，单卡定向给出单张的增量，两者是同一种东西（这正是 §3.1.5 与「槽位收回操作内部」合流之处）。

#### 3.9.3 组件处置表

| 组件 | 处置 | 说明 |
|------|------|------|
| `PoolPitySpec.scope_cards` / `featured_cards` | **保留** | 卡集合，是分组的真相源；Modifier 据此确定 scope 与 target |
| `PoolPitySpec.scope_slots` / `featured_slots` / `card_to_slot` | **推迟删除**（ISSUE-901，改判；随 GATE-5 末条「发布前一次性移除旧保底类」的同一 commit） | 槽位名与卡→槽位映射在**卡级管道**下确无消费者，但**旧保底类及其调用链仍在读它们**：`SoftStepBehavior._compute_probabilities`（[pity.py:277-284](gacha_simulator/core/pity.py#L277-L284)）、`HardPityBehavior`（:372-398）、`RotatingBehavior`（:494-498）、`TargetedBehavior`（:648-698）一律以 `ctx.draw.scope_slots.get(self._scope, ())` 取源集，`_redistribute_scope` 的函数体（[pity.py:432](gacha_simulator/core/pity.py#L432)）亦然。**ISSUE-502 只保住了函数本体、没有保住它的输入**——同批删字段即让该函数「在而不可调用」（模块级名字在调用时解析，导入期与 ruff 都不报错），S5a harness 的旧实现对照基准与 S8-6 的「对 S5 产物容差 1e-12」双双落空。**旧稿残留句已删（ISSUE-908，2026-10-01）**：原句写「`_resolve_selected_slots` 的目标定位**仍**改为直接给出卡集合 `(selected,)`（新骨架不依赖槽位）」——该名字全库只有一个定义，即旧 `TargetedBehavior._resolve_selected_slots`（[pity.py:681](gacha_simulator/core/pity.py#L681)），其返回值直接喂给 `_redistribute_scope(ctx, featured_ratio, total, targeted_slots, self._scope)`（[:655](gacha_simulator/core/pity.py#L655)）。照该句施工会同时造成两件坏事：(a) 动了 ISSUE-502 / ISSUE-901 明令**保留至发布前**的旧类，S8-6 的「现跑旧类」基线当场变质；(b) 该旧类下游是槽位级函数（`result[s] = featured_total * w / f_total_w`、`base_probabilities.get(s, 0.0)`），传入卡 id 只会**新增键**而不命中目标槽，目标槽拿不到 100%。**新架构下该职责由 §3.1.2 机制表的 `SelectedModifier`（A = `(selected,)`）承担；旧 `TargetedBehavior` 的该私有方法一律不改** | <!-- REVIEW-R1-FIX: ISSUE-908 --> <!-- REVIEW-R1-FIX: ISSUE-901 -->
| `compute_scope_mappings` | **推迟改造（减量部分）** | **卡集合本就存在**：该函数五元组的前两项即 `scope_cards` / `featured_cards`（[pity.py:1065-1066](gacha_simulator/core/pity.py#L1065-L1066)），且 `PityEngine` 三个调度入口已把它们透传进 `DrawInfo`（[pity.py:1293-1297](gacha_simulator/core/pity.py#L1293-L1297)）——**S8-4 对卡级路径零改动，无「增量」可做**。原定的「不再生成槽位名」是**减量**改造，必须与槽位三字段同批（同一函数无法只留一半产出），随 GATE-5 末条「发布前一次性移除旧保底类」commit（**ISSUE-901**）。**不得在 S8-4 提前减量**：三个解包点（[batch_simulator.py:273](gacha_simulator/service/batch_simulator.py#L273) / [worst_impact.py:530](gacha_simulator/core/worst_impact.py#L530) / [test_pity_integration.py:107](tests/core/test_pity_integration.py#L107)、:160）一律按五元组解包，提前改返回值元数会同时波及 `PoolPitySpec` 构造与 `DrawInfo` 构造，波及面反而大于「本步不动」 | <!-- REVIEW-R1-FIX: ISSUE-901 --><!-- REVIEW-R1-FIX: ISSUE-002 --> <!-- REVIEW-R1-FIX: ISSUE-955 -->
| `aggregate_probs_by_rarity` | **删除** | 唯一**生产**调用点在 [banner.py:227](gacha_simulator/core/banner.py#L227)；同时清 `core/__init__.py` 的导出。**事实订正（S8-4 审查，2026-10-14）**：另有 **2 个测试消费者在 S8-4 前仍活**（`tests/core/test_pool.py` 的 import 与调用、`tests/core/test_worst_impact.py` 的函数内 import 与调用，共 4 处），故「唯一调用点」字面为假，其改造点归 **S8-4**（不是 S8-2）|
| `_redistribute_scope(ctx, ratio, total, target_slots, scope)` | **替换（下游切换到新函数；函数本体保留至「发布前一次性移除旧类」的 commit）** | 新骨架（`Pity` + 卡级 Modifier 链）改用卡级版 `transfer_linear(dist, A, Q, amount, shape='current', weights=None)`（**6 参，定稿签名以 §3.9.4 的定义为准**；无 `base_weights` 这个旧形参，A 内分配由 `shape` 决定、`declared` 时权重经 `weights` 传入，理由见 §3.9.4），产出增量向量而非新分布。**ISSUE-022**：原稿此表写 5 参（多 `base_weights`）、§3.9.4 写 4 参、§3.14.3 写关键字 `scope=`，三处互不兼容，2026-09-22 统一为 4 参；**2026-10-08 加 `shape` 形参后为 5 参**（`dist, A, Q, amount, shape='current'`，其中仍不含 `base_weights`）。<br>**ISSUE-502（2026-10-01 补，强制）**：**函数本体在 S8 不删**。`pity.py` 内仍有 4 处调用点（**2026-10-09 实测订正**：:475 `RotatingBehavior`、:587 `RotatingCRBehavior._force_featured`、:653/:657 `TargetedBehavior`；原写 :477 / :589 / :655 / :659 整体 +2）<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->，全部位于**按 GATE-5 要保留到发布前的旧类体内**——删函数本体即 `NameError`（模块级名字在**调用时**解析，导入期与 ruff 都不报错），而 S5a 等价性 harness 与 S8-6 的对照基准正是这些旧类。故 S8 的处置是：**新增 `transfer_linear` + 让新骨架改用**，`_redistribute_scope` 与 `transfer_linear` 并存；**只删 `core/__init__.py` 的导出**（:20 import + :117 `__all__` 条目，随 S8-4），不删 `pity.py` 内的定义。函数本体的删除并入 GATE-5 末条的「发布前一次性移除旧保底类」commit（旧类与其调用点同时消失） | <!-- REVIEW-FIX-PREV: ISSUE-022 --> <!-- REVIEW-R1-FIX: ISSUE-502 -->
| `infer_rarity_from_spec` | **删除**（**随 `aggregate_probs_by_rarity` 一并删**，含 `core/__init__.py` 的 import 与 `__all__` 导出） | **ISSUE-504（2026-10-01 复核，推翻原「保留」定稿）**：全库引用实测只有 4 类——① 定义 [pool.py:234](gacha_simulator/core/pool.py#L234)；② 内部消费 [pool.py:280](gacha_simulator/core/pool.py#L280) / [pool.py:285](gacha_simulator/core/pool.py#L285)，两者都在将随本表删除的 `aggregate_probs_by_rarity` 内；③ [banner.py:242](gacha_simulator/core/banner.py#L242) / [banner.py:244](gacha_simulator/core/banner.py#L244) 与 [banner.py:209](gacha_simulator/core/banner.py#L209) 的局部 import，全在将随 S8-2 删除的 `scale_factors` 段内；④ 导出 [core/\_\_init\_\_.py:3](gacha_simulator/core/__init__.py#L3) 与 [:101](gacha_simulator/core/__init__.py#L101)。①②③ 消灭后本函数**零消费者**（`_infer_rarity`（[pity.py:1342](gacha_simulator/core/pity.py#L1342)）用的是 `spec.ssr_ids` / `scope_cards`，**它是同一条规则的第二个实现，不是无关的另一件事，见紧随本行的注**），故 S8 后保留它只会留下无人调用的死代码，并与 §六 / S8-2 的 `grep` 零命中验收**恒冲突**（原「保留」定稿下该 grep 永远为红）。**原稿的「S8 时再复核」已由本节复核取代** | <!-- REVIEW-R1-FIX: ISSUE-504 --><!-- REVIEW-R1-FIX: ISSUE-001 -->
> **⚠ S8 删 `infer_rarity_from_spec` 会留下它的孪生兄弟（2026-10-09 登记，实施本步前必读）**：
> 「卡 id → 稀有度」这一条规则在库里**有两份实现**——A = `pool.infer_rarity_from_spec`（喂**概率**路径：`scale_factors` 还原段与聚合），
> B = `PityEngine._infer_rarity`（[pity.py:1342](gacha_simulator/core/pity.py#L1342)，喂**状态**路径：`after_draw` 填 `DrawInfo.reward_rarity`，
> 被 `_should_reset` / `_is_trigger_rarity` / `did_fire` 共 6 处消费）。**ISSUE-504 删掉的是 A，留下的是 B**，而计划此前只把 B 写作「与本函数无关」。
> 两份的差异：判定顺序（A 先 `scope_cards`、B 先 `ssr_ids`）、A 多一条 `featured_ids` 回退、认不出时 A 返 `None` / B 返 `''`。
> **S8 之后 A 的两项能力是被丢弃而不是被合并**——B 能正常工作，靠的是「`scope_cards` 覆盖池内全部 id」这一不变量（真实配置实测 8 个池 × 每池 19 张 = 152 张（**数字口径订正，S8-4 审查 2026-10-14**：原写「8 个 banner × 各池 152 张卡」，实测每池 19 张）
> 逐卡成立，且 `ssr_ids == scope_cards['ssr']`、`featured_ids ⊆ scope_cards`）。**实施本步时必须核对这条不变量在所有构造点成立**，
> 其中 `worst_impact` 那处**当前是破的**（按原始 id 建 `scope_cards`、池内是重命名的 `_wi_featured_{i}`，见 ISSUE-006），故**S8-5 的卡集合对齐是本步的前置**：
> 不先对齐，B 会在最差影响路径上失去对 `_wi_featured_*` 的判定（A 今天是靠 `featured_ids` / `ssr_ids` 回退兜住的）。
> 另：这条重复已在 `tests/core/test_pity_integration.py::TestRarityInferenceConsistency` 加了守卫（A 与 B 逐卡必须一致 + 上述两条不变量），
> 缺陷 12 正是 A 单方面漂移造成的（实测修前 152 张卡中 96 张分歧）。详见 [04-问题.md](docs/01-活跃/subsystems/保底系统/04-问题.md) 的同源重复实现登记。
| `DrawInfo.scope_slots` / `featured_slots` / `card_to_slot` | **推迟删除**（ISSUE-901，随 `PoolPitySpec` 同步） | `PityEngine` 的三个调度入口（`before_draw` / `after_draw` / `get_probabilities`）在此期间**继续透传**三字段（[pity.py:1290-1300](gacha_simulator/core/pity.py#L1290-L1300)），否则旧类首次读 `ctx.draw.scope_slots` 即 `AttributeError`，S5a harness 连 `DrawInfo` 都构造不出来。`DrawInfo.base_probabilities` 语义由「槽位级」改为「卡级」**仍按 S8 执行**（该字段是卡级管道的输入，与槽位三字段的存废无关） | <!-- REVIEW-R1-FIX: ISSUE-901 -->
| `service/batch_simulator.py` | **改造（推迟，ISSUE-901）** | [batch_simulator.py:273-290](gacha_simulator/service/batch_simulator.py#L273-L290) 解包 `compute_scope_mappings` 的五元组并构造含槽位字段的 `PoolPitySpec`——与 worst_impact 同属构造点。**S8-4 对它零改动**：槽位三字段推迟删除（见上两行），`PoolPitySpec` 的 8 字段构造在 S8 期间保持原样，新骨架读的 `scope_cards` / `featured_cards` 本就由同一五元组产出并存入该 spec。与 worst_impact 的构造点改造、`compute_scope_mappings` 的减量**同批**并入 GATE-5 末条 commit。**2026-09-21 审查补** | <!-- REVIEW-R1-FIX: ISSUE-901 --><!-- REVIEW-R1-FIX: ISSUE-003 -->
| `core/__init__.py` | **改造** | 除 `aggregate_probs_by_rarity` 外，`_redistribute_scope` 的导出（[core/\_\_init\_\_.py:20](gacha_simulator/core/__init__.py#L20)、`:117`）在 S8 替换后亦须一并处理。**2026-09-21 审查补**。**ISSUE-025（2026-09-22）**：同一 import 块（[core/\_\_init\_\_.py:9-20](gacha_simulator/core/__init__.py#L9-L20)）还导入并在 `:107-117` 的 `__all__` 中逐项导出 **10 个旧行为类**（`SoftStepBehavior` / `CounterBasedBehavior` / `HardPityBehavior` / `RotatingBehavior` / `RotatingSoftBehavior` / `RotatingCRBehavior` / `RotatingCRSoftBehavior` / `TargetedBehavior` / `TargetedSoftBehavior` / `SoftPityMixin`）——preset 化后这些符号退役，须同步删除其 import 与 `__all__` 条目，否则 ImportError 或留下指向已删符号的 re-export | <!-- REVIEW-FIX-PREV: ISSUE-025 -->
| `tests/` | **改造** | **5 个文件**直接消费槽位结构（实测全库命中 5 个，原写「6 个」）：`tests/core/test_pity_rotating.py`（import 并调用 `_redistribute_scope`）、`tests/core/test_pity_integration.py` / `tests/test_pity.py` / `tests/core/test_pity_lifecycle.py` / `tests/core/test_pity_targeted.py`（构造带槽位字段的 `PoolPitySpec`）。**2026-09-21 审查补**；**2026-09-22 计数修正（ISSUE-GATE-file-list）**。**ISSUE-907（2026-10-01）：另有第 6 个合法消费方 `tests/core/test_pity_equivalence.py`**——等价性装置必须**自行构造**带槽位字段的 `PoolPitySpec` / `DrawInfo` 喂给旧类（§3.2 首段强制它不经 registry），它是 S8-7 那条 `grep` 验收的**例外之一**（**ISSUE-942：原写「唯一例外」，不成立**：例外清单共三项：① 本行的 `test_pity_equivalence.py`；② `tests/core/test_pool.py:62` 的 `card_to_slot={'ssr_a': 'ssr_featured'}` 构造；③ `tests/core/test_worst_impact.py:303` 的 `spec.featured_slots['ssr'][0]` 读取。后两者挂在 **S8-2** 名下、由 S8-2 的同一 commit 改造，完整清单与归属见 §七 S8-7 的验收命令行），故本行标的文件既不在 S8-7 的改造面内、也不计入「5 个文件」。**另有四个「被删符号」消费方（与槽位消费面不同批，ISSUE-005 / ISSUE-942）**：`tests/core/test_pool.py` / `tests/core/test_worst_impact.py` / `tests/core/test_pity_integration.py` / **`tests/test_banner.py`**（`:958` 的类 docstring `TestPityAdjustmentReachesCardLevel` 含 `infer_rarity_from_spec`，**实测第四个命中文件**，ISSUE-712），改造点为 **S8-2**（两函数定义的删除点），与本行的槽位消费面（改造点 S8-7）不得混为一事 | <!-- REVIEW-R1-FIX: ISSUE-907 --> <!-- REVIEW-R1-FIX: ISSUE-942 -->
| `core/worst_impact.py` | **改造** | 第二处 `PoolPitySpec` 构造点（[worst_impact.py:543-552](gacha_simulator/core/worst_impact.py#L543-L552)），**该处已无硬编码槽位表**（槽位由 `compute_scope_mappings(wi_pool)` 产出，[worst_impact.py:530-531](gacha_simulator/core/worst_impact.py#L530-L531)；字面量 `'ssr_featured'` 全文仅见于 :487 的 docstring）。**改造亦推迟（ISSUE-901 / ISSUE-904，2026-10-01 改判）**：S8 期间**不改本处**——槽位三字段推迟到 GATE-5 末条才删，此刻按 8 字段构造仍然成立。删三个槽位实参、只构造卡集合字段（`scope_cards` / `featured_cards` / `featured_ids` / `ssr_ids`）与 `_ref_pool_entry` 的局部变量化，两项一并并入 GATE-5 末条「发布前一次性移除旧保底类」的同一 commit（原写「S8 后只构造卡集合字段」与同节 B 段互斥，已改）。**S8-5 仍须做的是卡集合按池对齐**（**ISSUE-006（强制）：卡集合必须与该 spec 所属池的 reward id 对齐**——见下方专项），该项与槽位字段的存废无关 | <!-- REVIEW-R1-FIX: ISSUE-904 -->
| `Pool._apply_probabilities` | **保留** | 接收卡级分布，语义不变 |
| `CompactResult` 输出字段 | **不受影响** | 已核对：无槽位相关字段（`draw_pity_names` 等均为池/保底名，非槽位名） |

<!-- P64-S8-CLOSURE -->
> **上表 `tests/` 行的归属订正（S8-4 审查，2026-10-14）**：该行把 `tests/core/test_pool.py` 与 `tests/core/test_worst_impact.py` 的改造点归 **S8-2**，而 S8-2 只删了 `infer_rarity_from_spec`、**保留了 `aggregate_probs_by_rarity` 的本体**（该本体在 **S8-4** 才删）。故「改造点落在 S8-2」**不可执行**（计划内部自相矛盾），实际顺延到 **S8-4** 并由其完成。**另**：`tests/core/test_pity_registry_schema.py` 的「导出仍在」正断言（S7d 审查登记）亦在 S8-4 反转。

<!-- P64-S8-CLOSURE -->
> **覆盖登记（S8-4 审查，2026-10-14）**：上段提到的守卫 `tests/core/test_pity_integration.py::TestRarityInferenceConsistency` **已由 S8-2（`f18045f`）改名为 `TestRarityInferenceGuards`**，其中「**A 与 B 逐卡一致**」那一半的**对象随 A 被删而消失**（旧类断言 `a == b` 且 `a == real`，新类只断言 `B == real` 与两条不变量）。**该对象消失此前从未登记**（计划正文仍引用旧类名）。实质影响低（A 已删、概率路径不再做稀有度反查，该判据无剩余对象；`B == real` 那一半原样保住），但**属判据消失未登记**，故登记于此并订正上段的类名引用。

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-5 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-6 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-8 -->
**跨文件同步清单（AUDIT-BREAK-5 / 6 / 8，强制，2026-09-22 补）**

上表的删除项在多处有并列的消费面，**只改「主调用点」即漏改**——漏改的失败形态是 `ImportError`（导入期或首次调用期），不是因为「没人用」而静默。逐处列明（行号为 2026-09-22 实测）：

**A. `aggregate_probs_by_rarity` / `infer_rarity_from_spec` 的删除面（S8，三处同步，缺一即 ImportError）**

| # | 位置 | 现状 | 处置 |
|---|------|------|------|
| 1 | [banner.py:209](gacha_simulator/core/banner.py#L209) | `draw()` 内**函数局部** import 两符号 | 随 `scale_factors` 段一并删除（局部 import 只在 `draw` 被调时执行，导入期不报错——漏改在首次抽卡时崩） |
| 2 | [banner.py:227](gacha_simulator/core/banner.py#L227)（调用）/ :229-246（`scale_factors` 段）/ :242、:244（slot 推导用 `infer_rarity_from_spec`）/ :257（`after_draw`） | 聚合 + 还原四件套 | §3.9.1 的「净删除」三件 + 改传卡级分布；:257 的 `after_draw` 调用**保留**（与概率管道无关，勿误删） |
| 3 | [pool.py:254](gacha_simulator/core/pool.py#L254)（`aggregate_probs_by_rarity` 定义）/ :280、:285（其内部对 `infer_rarity_from_spec` 的消费）/ **:234（`infer_rarity_from_spec` 定义）** | 函数定义与内部调用 | 删除**两个**函数定义（**ISSUE-504**：`infer_rarity_from_spec` 在 ①②③ 类消费者消失后零消费者，原「保留、S8-2 时复核」已由 §3.9.3 处置表的复核结论取代——**删除**） | <!-- REVIEW-R1-FIX: ISSUE-504 --><!-- REVIEW-R1-FIX: ISSUE-001 --> <!-- REVIEW-R1-FIX: ISSUE-954 -->
| 4 | [core/\_\_init\_\_.py:3](gacha_simulator/core/__init__.py#L3) | `from .pool import … aggregate_probs_by_rarity, infer_rarity_from_spec` | 删除 `aggregate_probs_by_rarity` **与 `infer_rarity_from_spec`** 两个 import（**ISSUE-504：复核结论已定 = 一并删除**，不再留待落地时判断）；对应的 `__all__` 两条目同批删（见第 5 行口径） | <!-- REVIEW-R1-FIX: ISSUE-504 -->
| 5 | [core/\_\_init\_\_.py:101](gacha_simulator/core/__init__.py#L101) 的 `__all__`（`'aggregate_probs_by_rarity', 'infer_rarity_from_spec'` 两条目） | 逐项导出 | 同步删除**两条**条目（ISSUE-504）<!-- REVIEW-R1-FIX: ISSUE-504 -->；**`__all__` 与 import 块必须同批改**——只删 import 会留 `NameError`，只删 `__all__` 会留下对已删符号的 re-export |

**B. 槽位字段的第二个构造点（`core/worst_impact.py`，改造随槽位字段的删除同批）**：[worst_impact.py:543-552](gacha_simulator/core/worst_impact.py#L543-L552) 构造 `PoolPitySpec`，其槽位实参 `scope_slots`（:549）、`featured_slots`（:550）、`card_to_slot`（:551）均取自 `compute_scope_mappings(wi_pool)`（:530-531），**文件内不存在硬编码槽位表**（原引 `:512` / `:515` 实为 `from gacha_simulator.core.pity import _build_pity_state_init` 与 `pool_specs = {}`）。**ISSUE-901：S8 期间不改本处**——槽位三字段推迟到 GATE-5 末条才删，此刻按 8 字段构造仍然成立；改造（删三个槽位实参、只构造卡集合字段、把 `_ref_pool_entry` 局部变量化）与字段删除**同一个 commit**。**S8-5 仍须做的是卡集合对齐**（§3.9.3 ISSUE-006 专项：`scope_cards` / `featured_cards` 与池内 reward id 的对齐**已由 `e32577f`（2026-10-09）落地**并已就位构造期覆盖不变量，见该专项）——这一条与槽位字段的存废无关，不受本条影响。**（2026-10-09 订正）** 本条原写「该构造点位于 `ref_pool = getattr(self,'_ref_pool',None)` 的**死分支**内」，实测全库 grep `_ref_pool` 只命中 `_ref_pool_entry`（:83 / :372 / :373），**该属性与所述分支在全库都不存在**，与本节下方 ISSUE-006 专项的实测结论一致。 <!-- REVIEW-R1-FIX: ISSUE-955 -->

**C. `core/__init__.py` 是 S8 与 S4-3 的**双目标文件**（AUDIT-BREAK-8）**：除 A 项第 4/5 行外，[core/\_\_init\_\_.py:9-20](gacha_simulator/core/__init__.py#L9-L20) 还从 `pity` 导入并在 `__all__` 中逐项导出 **10 个旧行为类 + `SoftPityMixin` + `_redistribute_scope`**（`SoftStepBehavior` / `CounterBasedBehavior` / `HardPityBehavior` / `RotatingBehavior` / `RotatingSoftBehavior` / `RotatingCRBehavior` / `RotatingCRSoftBehavior` / `TargetedBehavior` / `TargetedSoftBehavior` / `SoftPityMixin` / `_redistribute_scope`，ISSUE-025 已登记）。**须分别在不同子块处置**：`_redistribute_scope` 的导出随 **S8-4** 删（它是 S8 的替换对象；**ISSUE-502：只删 `core/__init__.py` 的 import 与 `__all__` 条目，`pity.py` 内的函数本体保留至「发布前一次性移除旧类」的 commit**）<!-- REVIEW-R1-FIX: ISSUE-502 -->；10 个旧类与 `SoftPityMixin` 的 re-export 随 **S4-3**（preset 化完成、旧类在本包公共面上退役）删——**不随「发布前一次性移除旧类」才删**，否则从 S4-3 到发布前这段窗口里 `import gacha_simulator.core` 会带着一批已无 registry 入口的符号，诱惑新代码继续用旧类。删除 `__all__` 条目时须确认无 `from gacha_simulator.core import HardPityBehavior` 形态的调用方（`from gacha_simulator.core.pity import …` 不受影响，旧类本体保留到发布前）。

**D. 旧保底类与 `_redistribute_scope` 对 `DrawInfo` / `PoolPitySpec` 槽位字段的依赖（ISSUE-901，强制）**：上表与 S8 的删除清单**不含** `PoolPitySpec` / `DrawInfo` 的 `scope_slots` / `featured_slots` / `card_to_slot` 六个字段，也**不含** `compute_scope_mappings` 的槽位名产出——它们在旧保底类与等价性装置存活期间是必需品（旧类概率入口 + `PityEngine` 的三个 `DrawInfo(...)` 构造点 + `_redistribute_scope` 函数体）。误删的失败形态是双重的：`PityEngine.before_draw` / `after_draw` / `get_probabilities` 三处 `DrawInfo(...)` 构造先一步 `TypeError`（关键字参数不存在），随后所有旧类在 `ctx.draw.scope_slots.get(...)` 处 `AttributeError`。**该失败只落在等价性 harness 与 S8-6 上**（S7d 已改造的 5 个存量文件不再构造槽位），归因方向反直觉——实施者会先怀疑新卡级管道算错，而真因是「删早了」。三字段与槽位产出的删除点 = GATE-5 末条的「发布前一次性移除旧保底类」commit，与 `_redistribute_scope` 本体、其 4 处调用点（**实测 :549 / :661 / :727 / :731**，2026-10-09 订正；原写 :477 / :589 / :655 / :659）、10 个旧行为类同批。<!-- REVIEW-R1-FIX: ISSUE-901 -->

<!-- REVIEW-FIX-PREV: ISSUE-006 -->
**ISSUE-006 专项：`worst_impact` 的卡集合必须与池内 reward id 对齐（强制）**

**现状（2026-10-09 实测；已由 `e32577f fix(worst_impact): 虚拟池的卡集合按池内真实 id 生成` 落地）**：卡集合与池内 id **已对齐**。五个映射统一由 `compute_scope_mappings(wi_pool)` 按池生成（[worst_impact.py:530-531](gacha_simulator/core/worst_impact.py#L530-L531)），同一 spec 的 `featured_ids` / `ssr_ids` 取自其中的 `featured_cards` / `scope_cards`（:545-546），池子 `rewards` 的 id 由 `featured_id = f'_wi_featured_{i}'` 重命名而来（[worst_impact.py:177-188](gacha_simulator/core/worst_impact.py#L177-L188)），**构造期覆盖不变量已就位**（:536-541：`_covered = set(card_to_slot)` / `_missing = {r.id for r, _ in wi_pool.rewards} - _covered` / `raise ValueError`）。本条原写的「[worst_impact.py:508](gacha_simulator/core/worst_impact.py#L508) 用参考池的**原始卡 id** 生成 `scope_cards` / `featured_cards`」是 `e32577f` **之前**的旧现状（:508 现为注释 `# shallow copy via dataclass fields`），其失效形态（原始 id 不在分布里）**已不可达**。 <!-- REVIEW-R1-FIX: ISSUE-955 -->

- **当前为何不崩**：槽位级管道下 `aggregate_probs_by_rarity` 只把 `scope_cards` 当加速缓存用（取不到时回退 `infer_rarity_from_spec` → `spec.ssr_ids`，后者恰含 `_wi_featured_0`）。
- **S8 后为何崩或静默归零**：`scope_cards` / `featured_cards` 成为管道**唯一真相源**（§3.9.4 的 `transfer_linear` 直接 `sum(dist[c] for c in A)`）。实测该式对原始 id 抛 `KeyError`；若实现改用 `.get` 兜底，则所有保底调整**静默归零**。**（2026-10-09 注：上面两条描述的是 `e32577f` 之前的失效机理，保留以说明本不变量的必要性；现状已不可达。）**
- **顺带实测的写后即读（2026-10-09 订正）**：`_ref_pool_entry`（[worst_impact.py:83](gacha_simulator/core/worst_impact.py#L83) 初始化为 `None`、[:372](gacha_simulator/core/worst_impact.py#L372) 赋 `pool_entries[-1]`、[:373](gacha_simulator/core/worst_impact.py#L373) 立即读取）**写后即读、无跨方法消费**，可退化为局部变量。**原稿此处写的「[worst_impact.py:504](gacha_simulator/core/worst_impact.py#L504) 的 `ref_pool = getattr(self, '_ref_pool', None)` 分支恒不执行」不成立**：实测全库（`gacha_simulator/` 与 `tests/`）grep `ref_pool` 只命中 `_ref_pool_entry` 三行（:83 / :372 / :373），**`_ref_pool` 这个属性、以及所述分支在全库都不存在**，且 `worst_impact.py:504` 实为 `pity_defs_list = []`。<!-- REVIEW-R1-FIX: ISSUE-006 -->
- **改造口径（2026-10-09 更新）**：按池重建卡集合**已落地**（`e32577f`）、覆盖不变量**已就位**（[worst_impact.py:536-541](gacha_simulator/core/worst_impact.py#L536-L541)），故 S8 期间**无增量可做**；GATE-5 末条只需保留该不变量，并**断言 `set(scope_cards[scope]) ⊆ {r.id for r, _ in pool.rewards}`**（**ISSUE-201**：`Pool.rewards` 的类型是 `List[Tuple[Reward, float]]`（[pool.py:152](gacha_simulator/core/pool.py#L152)），迭代元素是 `(Reward, prob)` 二元组——原稿写的 `{r.id for r in …}` 单变量解包形式（把元素当成 `Reward`）会立即抛 `AttributeError: 'tuple' object has no attribute 'id'`；同文件 [:162](gacha_simulator/core/pool.py#L162) / [:181](gacha_simulator/core/pool.py#L181) 的消费方式与 §3.9.1 的 `{r.id: p for r, p in pool.rewards}` 均按二元组解包，本处与之一致）。<!-- REVIEW-FIX-PREV: ISSUE-201 --> <!-- REVIEW-R1-FIX: ISSUE-955 -->
- **差异归因**：本改造会**改变最差影响分析的数值**（超出「与 M1 产物容差 1e-12 一致」的口径），须写入 §六 的差异归因清单，不得当作回归。

#### 3.9.4 助手函数 `transfer_linear`

> **本节经 2026-10-06 用户裁决重写，2026-10-08 用户裁决由因子改为增量。** 原两个「卡级原语」（`factor_redistribute` = share / `factor_override` = assign）**均作废**，其职责合为一个助手。

**定位：助手，不是接口。** Modifier 的接口是 `compute_delta(view, dist, ctx)` 返回任意增量向量（§3.1.2）；当前七个机制恰好都落在「A 加 Q 减」这一族（§3.1.5.2.1），故提供本函数供其复用。**不属于该族的新机制直接实现 `compute_delta()`，不经过本函数。**

```python
def transfer_linear(dist, A, Q, amount, shape='current', weights=None):
    """把 amount 的概率质量从 Q 搬到 A，返回增量向量。

    A 内每卡 + amount · u_A(c)        u_A 由 shape 定：
                                        'current'  → p_c / p(A)
                                        'declared' → w_c / w(A)，w 由 weights 传入
    Q 内每卡 − amount · p_c / p(Q)    （Q 侧恒为当前形状，不可指定）
    其余不写（= 0）

    配平：Σδ = amount − amount = 0，故 Σ(p + δ) = 1，
    框架归一化退化为恒等（§3.1.5.2.1；**位级口径见该节的 2026-10-14 订正**：单卡组下恰为恒等，多卡组下 Σδ 可为 ±1 ULP）。
    """
    pQ = sum(dist[c] for c in Q)
    if pQ <= 0 or amount <= 0:
        return None                      # 无货可取 → 恒等
    if shape == 'current':
        pA = sum(dist[c] for c in A)
        if pA <= 0:
            return None                  # 目标组当前无概率 → 未定义（见前置条件表）
        uA = {c: dist[c] / pA for c in A}
    elif shape == 'declared':
        if not weights:
            raise ValueError("shape='declared' 必须同时传 weights"
                             "（声明权重，即 ctx.base_probabilities）")
        wA = sum(weights.get(c, 0.0) for c in A)
        if wA <= 0:
            return None                  # 池子声明该组不可获得 → 不转移（来源一）
        uA = {c: weights.get(c, 0.0) / wA for c in A}
    else:
        raise ValueError("未知的 shape: %r" % (shape,))

    d = {c: amount * uA[c] for c in A}
    for c in Q:
        d[c] = d.get(c, 0.0) - amount * dist[c] / pQ
    return d
```

**前置条件**（助手对 `p(Q) <= 0` / `amount <= 0` / `p(A) <= 0` 三处**已做**防御性返回 `None`，见上方代码；调用方**仍应**在 `compute_delta()` 开头早退，以免把行为依赖在助手的内部实现上）：

| 条件 | 不满足时 |
|------|---------|
| `A` 与 `Q` 不交 | 增量冲突，结果无定义 |
| `p(Q) > 0` | 无货可取，返回 `None`（恒等） |
| `p(A) > 0`（`shape = 'current'` 时） | 目标组当前无概率，`u_A` 未定义，返回 `None`（恒等）。**这是「来源一」（池子声明该组不可获得）的正确处置：不转移。** `shape = 'declared'` 无此限制 |
| `w(A) > 0`（`shape = 'declared'` 时） | 池子声明该组不可获得，返回 `None`（恒等）。**与上一行同为来源一的处置，只是判定依据从当前分布换成声明权重** |
| `weights` 已传（`shape = 'declared'` 时） | 未传则抛 `ValueError`（无权重即无从分配） |
| `amount <= p(Q)` | 否则 Q 侧增量为负、产出负概率。soft 的 `boost%` 封顶 100，故 `amount <= 1`；夺取型 `amount = p(Q)` 恒满足 |

**三个机制的实际调用**（前两个取默认 `current`，第三个演示 `declared`）：

```python
class RotatingModifier(Modifier):
    def compute_delta(self, view, dist, ctx):
        if not view.get('guaranteed'):
            return None
        scope = ctx.scope_cards[self._scope]
        feat = ctx.featured_cards.get(self._scope, ())
        A = feat
        Q = tuple(c for c in scope if c not in set(feat))
        if not A or sum(dist[c] for c in A) <= 0:
            return None
        return transfer_linear(dist, A, Q, sum(dist[c] for c in Q))


class SoftModifier(Modifier):
    def compute_delta(self, view, dist, ctx):
        boost = self._cumulative_boost(view.get('counter'))   # deltas → boost%
        if boost <= 0:
            return None
        A = ctx.scope_cards[self._scope]
        Q = _lower_rarities(ctx, self._scope)
        if not A or sum(dist[c] for c in A) <= 0:
            return None
        return transfer_linear(dist, A, Q, boost / 100.0)


class SelectedModifier(Modifier):                      # targeted：A 侧取 declared
    def compute_delta(self, view, dist, ctx):
        if not (view.get('guaranteed') or view.get('fate_points', 0) >= self._tau):
            return None
        sel = view.get('selected_card')
        scope = ctx.scope_cards[self._scope]
        A = (sel,)
        Q = tuple(c for c in scope if c != sel)
        if not A or sum(dist[c] for c in A) <= 0:
            return None
        return transfer_linear(dist, A, Q, sum(dist[c] for c in Q),
                               shape='declared', weights=ctx.base_probabilities)
```

<!-- P64-S8-LANDED -->
> **本节三个调用示例与 §3.9.5 冲突两处，落地时按 §3.9.5 实现（2026-10-14）**：
> ① `SelectedModifier` 示例带 `if not A or sum(dist[c] for c in A) <= 0: return None`，而 §3.9.5 第 1 行与 §3.1.5.6.1 明写 **`shape='declared'` 的机制在 `p(A) = 0` 时仍能转移**（「来源二」正是在冲突配置下生效的那条路径），只有 `w(A) = 0` 才返 `None`。故 `declared` 机制在方法体开头的早退判据是 **`w(A) <= 0`，不是 `p(A) <= 0`**；两条正例已钉住「来源二」。
> ② `SoftModifier` 示例把 `amount` 直接取 `boost / 100`，**缺 `min(boost / 100, p(Q))` 封顶**。`amount > p(Q)` 会让 Q 侧增量为负、产出负概率（违反 §3.12.1 非负性判据），而旧实现本就写 `t = min(boost_pct / 100.0, pool)`。故封顶是**对齐旧实现**的必要动作，不是新增语义。

**模块归属**：`transfer_linear` 住叶子层 `core/pity_primitives.py`（§3.1.6 叶子行 / §四 该文件行）。理由：七个机制分居 `pity_modifier.py` 与预设工厂两处，放在任一处都会造成重复；**它与 `Pity` 骨架之间无依赖，故放叶子层不构成循环。**

**已删除的两个符号**：`factor_redistribute`、`factor_override`。全库（含 §3.1.6、§四、§七 各任务块）的引用须同步替换为本函数或「按 §3.1.2 表直接写 `compute_delta()`」。

<!-- REVIEW-R1-FIX: MODIFIER-IFACE -->

#### 3.9.5 边界处理

> **2026-10-08 用户裁决由因子改为增量后重写**（原表以 `share` / `assign` / 因子为词汇）。
> 逐条对照与理由见《保底算子表示切换·因子向量转增量向量·改写方案》§3。

| 情形 | 处理 | 依据 |
|------|------|------|
| `p(A) == 0`（目标组当前无概率） | **`shape = 'current'` 时返回 `None`（恒等，不转移）**：`u_A = p_c/p(A)` 未定义。**这是「来源一」（池子声明该组不可获得）的正确处置**，抬起来会与池子的声明冲突。**`shape = 'declared'` 的四个机制不受此限**（**计数订正（S9-3，2026-10-14）**：`NotOwnedModifier` 随 F7 裁决取 `declared`）：它们按 `w` 分配，`p(A) = 0` 时仍能转移（这正是来源二在冲突配置下生效的路径），只有 `w(A) = 0` 才返 `None` | §3.1.5.6.1。**2026-10-08 由因子改为增量时重写**：原表按 `share` / `assign` 分两支（前者跳过目标因子、后者返恒等），增量形式下**两分支合一**。原记录的旧码行为（`SoftStepBehavior` 的 `steal·w/Σw` 会把零概率目标槽从 0 抬起）在新框架下不出现，故「为对齐旧行为而保留源侧写因子」的理由随之消失。**须在 S8 验收中专项覆盖** |
| `p(Q) == 0`（无货可取） | 返回 `None`（恒等） | 同 §3.1.5.6 的「支撑上全为零」行 |
| `p(Q) == amount`（源组被搬空） | 正常执行：`δ_Q = −amount·p_c/p(Q) = −p_c`，源组归零；`δ_A = +amount·u_A` 照常 | 原 `P − T == 0` 行。**增量形式下该情形由公式自然涵盖，无分支**。原记录的实测（现码把零概率槽 `b` 从 0 造到 0.25、卡级版保持 0）在新框架下不再出现。**须在 S8 验收中专项覆盖** |
| **目标集为空**（`target_cards == ()`） | **返回 `None`（恒等）**，现址为 §3.9.4 的 `transfer_linear` 代码与其前置条件表（原写「§3.9.4.1 的守卫、§3.9.4.2 的守卫、§3.14.2 的说明」，那两个子节与 `ConditionalModifier` 包装器均已随 2026-10-06 改判消失） | **2026-10-05 补守卫**。原稿的 `return m or None` **不构成**该保证：`target_cards` 为空时 `T = 0`、`P − T = P > 0`，走 `ratio >= 1` 分支把**整个 U 写 0**，返回 `{'…': 0.0}` 而非 `None`。实测 `factor_redistribute(dist, ('ssr_featured','ssr'), (), 1.0)` 得 `{'ssr_featured': 0.0, 'ssr': 0.0}`，`_apply_factor` 归一化后全 scope 归零。**（本条为 2026-10-05 的历史记录，其中的 `factor_redistribute`、因子 `m` 与 `_apply_factor` 都是当时形态；表示已于 2026-10-08 改为增量，但本条的结论「目标集为空必须返回 `None`」不变。）****触发路径真实存在**：`rotating` 绑定到无 featured 卡的池（`PityDef.pools` 默认 `('*',)`，见 §3.9.5 的 scope 键缺失行）时 `featured_cards.get(scope, ())` 返空集 |
| **scope 键缺失**（如 `featured_cards` 无该稀有度键） | 一律用 `.get(scope, ())` 取集合，**空集合经上一条守卫返回 `None`（恒等）**；**禁止 `ctx.draw.scope_cards[self._scope]` 直接下标**。`compute_scope_mappings` 只对池中实际出现的稀有度建键、`featured_cards` 只对**有 featured 卡**的稀有度建键（实测 `scope_cards={'ssr':…,'sr':…}` 而 `featured_cards={'ssr':…}`，下标 `['sr']` 抛 `KeyError 'sr'`）。因 `PityDef.pools` 默认 `('*',)`，任何新增的无 featured 卡池（标准池等）都会让绑定该池的 `rotating` / `targeted` / G3 保底从「静默 no-op」变成**整场模拟崩溃**或（改前）**全 scope 归零**（ISSUE-016） | 旧实现统一 `.get(self._scope, ())` 并在为空时早退返回原分布（`SoftStepBehavior` [:277-279](gacha_simulator/core/pity.py#L277-L279)、`RotatingBehavior` :470-471、`TargetedBehavior` :649-650） | <!-- REVIEW-FIX-PREV: ISSUE-016 --> <!-- REVIEW-FIX-PREV: ISSUE-012 -->
| **`Σ(p + δ) ≠ 1`**（更高稀有度被归一化缩放） | **本条已消失**：增量形式下转移族恒有 `Σδ = 0`，故 `Σ(p + δ) ≡ 1`，`_apply_delta` 的归一化退化为恒等，U 之外的卡不被触碰（**位级订正，2026-10-14，S8-5 审查实测**：只有 **A 与 Q 各为单卡**时归一化因子才恰为 `1.0`（位级恒等）；**多卡组下** `Σδ` 可为 ±1 ULP（实测 `1.665e-16`），归一化**仍执行**、把每张卡（含 U 外）缩放约 1 ULP，该缩放无语义内容。故「逐位不变」不可满足） | 2026-10-08 由因子改为增量。**但 ISSUE-012 与 ISSUE-903 的分歧仍在**：M1 沿用旧实现（`apply` 返回分布，F 型豁免更高稀有度，输出 Σ = 1.009），M2 的框架无条件归一化（Σ = 1），两者 `Σp` 口径相反，与表示无关。**须在 S8 验收中专项覆盖**（**口径订正，2026-10-14**）：断言 U 外的卡**相对 1e-12 不变**（**不得**写「逐位不变」，多卡组下不可满足）；`Σ(p + δ) = 1` 一条**只作绊线**（`_apply_delta` 无条件归一化使其成为**结构保证**、不具判别力，S8-5 实测） |
| **`A ⊄ U`**（目标解析器返回了 U 之外的卡） | **构造期抛 `ConfigError`**，不得静默忽略 | 2026-10-05 新增（§3.1.5.6 同条；2026-10-08 变量名由 `T` 统一为 `A`）。静默忽略的后果是该卡「既被指定为目标又不在作用域内」，读者无从判断是配置错误还是有意为之 |
| 归一化后总量 ≤ 0 | 返回原分布 | `_apply_delta` 内的退化保护 |

<!-- P64-S8-CLOSURE -->
> **§3.9.5 表内四行的口径登记（S8-5 审查，2026-10-14，只登记不改表）**：
> **第 1 行（`p(A) = 0`）**：S8 后该形态在机制级的红因是**崩溃**（`pA <= 0` 守卫被删即 `ZeroDivisionError`），**不是**「把零概率目标抬起来」；判别性断言落在**助手级**（`tests/core/test_pity_rotating.py::TestTransferLinear` 的 `pA` / `wA` 两条），管道级用例只能证明「没崩」。
> **第 2 行（`P == 0`）**：旧词汇「U 内全零」在 S8 实现面被**加宽**为 `p(Q) = 0`（前者是后者的真子集），实现与夹具取更宽的一支（改写方案 §3 同口径）。**另**：夺取型的 `amount ≡ p(Q)`，故 `p(Q) = 0` 时「守卫返 `None`」与「返全零增量」在管道输出上同值（等价改写探针实测管道级用例仍绿、助手级转红），**该形态的判别力只在助手级**。
> **第 3 行（`P − T == 0`）**：夺取型全部传 `amount = sum(dist[c] for c in Q)`，故 `p(Q) == amount` **恒真**、不是可判边界；可判的是其**后置条件「源组精确归零」**，且该判别需要 **A 与 Q 非单卡**的夹具（真实 `config.toml` 池形状下「先除后乘 / 先乘后除」同值、不可判，实测）。
> **第 6 行**：见上方的位级订正（「逐位不变」不可满足）。

<!-- P64-S8-CLOSURE -->
> **§3.9.3 的 `tests/` 行与 §七 S8-7 行的计数订正（S8-7 审查，2026-10-14）**：① 上表 `tests/` 行的「**5 个文件**」与 §七 S8-7 行的「清单订正 12 个 / 扣例外后 9 个」**两处均与实测不符，且同段自相矛盾**：S8-7 落地前实测 **14 文件 / 259 raw / 207 code**，落地后 **8 文件 / 140 raw / 84 code**（`code` 桶逐位复算一致）。② **例外清单由三项扩为六项**：④ `tests/core/test_pity_rotating.py` 的 `slot_ctx` 与 `TestRedistributeScope` 三条及 `TestTransferLinear` 的单卡夹具（服务保留期的 `_redistribute_scope`）；⑤ `tests/core/test_pity_registry_schema.py` 的 `_fx_draw`（**双用途夹具**：同一 draw 同时喂新 `Pity` 与旧 `RotatingCRBehavior`）与其 `_redistribute_scope` 存活断言（ISSUE-502 的正面守卫）；⑥ `tests/core/test_pity_tracker.py` 的 `_cr_ctx`（同为双用途）。三项此前从未登记。③ **原例外②③的实质已变**（不只行号漂移）：`test_pool.py` 的命中已由「构造 `card_to_slot={...}`」变为 `_` 前缀解包（S8-4 留下），`test_worst_impact.py` 的命中已由「读 `spec.featured_slots['ssr'][0]`」变为 docstring。
> **两条覆盖质量登记（S8-7 审查，2026-10-14，均非 S8-7 引入）**：**(i) `rarity_rank` 方向反的夹具长期未被断言捕获**：多键反向表（如 `{'ssr': 3, 'sr': 2}`）会让 `_lower_rarities` 恒返空集，进而使 `SoftModifier.compute_delta` **恒返 `None`**（软保底静默恒等），而相关文件的用例只断言 counter / flag / 轨迹、**无一条读分布**，故订正前后皆绿。夹具已由 S8-7 订正为正确方向，但**该形态仍无断言驱动**，建议后续补一条「`boost > 0` 时分布确实改变」的用例。**(ii) 双用途夹具的保留不承重**：删掉它们的槽位实参后全量仍绿（S8-7 审查复现 205 passed），即保留的是「对照腿输入保真」的语义要求而非断言承重。**若将来要为它设守卫，正确形态是断言「对照腿输出 != `ctx.current.copy()`」（即对照腿未早退），而不是断言「夹具字段非空」**（后者是对字面量的同义反复、零缺陷检出能力）。

<!-- P64-S8-CLOSURE -->
> **`A ⊄ U` 构造期 `ConfigError` 当前无任务块归属（S8 收口登记，2026-10-14）**：本表与 §3.1.5.6 各写一次该要求，但 §七 无任何块承接它（`S10-2` 只做声明键的两条判据、`_validate_behaviors` 只做 scope 重叠、`config_toml` 只做 scope 白名单），S8-1/2/3 **未实现、只登记**（实测畸形 spec 下机制照常转移、不报错，该形态在 `compute_scope_mappings` 的产出上不可达）。**须补一个承接块或按缺口登记**，否则它会随 S8 收口静默落空。

#### 3.9.6 对只读查询的影响

`PityEngine.get_probabilities(pool_id, state, base)` 与 `before_draw` 走同一路径，S8 后同样改为卡级进出。**S8 起 Modifier 是 pure 函数（§3.1.2），`readonly` 形参随 2026-10-08 的签名裁决一并废除**：查询与抽卡前天然无副作用差异，增量照算，两者给出的分布必然相同（P16 的查询/修改分离由「pure」这一性质直接保证，不再需要一个开关）。**M1 期间仍用 `readonly`**（那时的 Modifier 会推进自己的计数器，见 §3.9.2 的两期分工）。

**`rotating_cr` 的例外（2026-10-10 补，RULING-6B′）**：上段的「查询与抽卡前必然给出相同分布」在 `rotating_cr` 上**不成立**，且这是 6B′ 相对 6B 的**新增回归**，须显式处置：

| 实现 | 只读查询读到的 `cr_intercepted` | 与第 N 抽实际分布的关系 |
|---|---|---|
| 旧 `RotatingCRBehavior` | 不读（`readonly` 早退，永不体现拦截） | 无关 |
| 6B | `commit(N−1)` 写的 | **恰好等于**（故上段性质成立） |
| **6B′（本方案）** | `prepare(N−1)` 写的（即上一抽的判定） | **不等于**（差一抽） |

**成因**：6B 的掷骰在 `after_draw`，查询不调 `after_draw`，读到的自然是「最近一次已发生的判定」＝第 N 抽的判定；6B′ 的掷骰回到 `before_draw` 的 `prepare`，查询会走到 `prepare` 的 `readonly` 早退分支，于是读到的是**上一次非只读调用**留下的 flag。

**处置（两期）**：① **M1 期**由 Modifier 依 `readonly` 抑制 `extra_flag`（复刻旧查询语义：查询不体现拦截）；② **M2 期** `readonly` 从 Modifier 签名废除后，按 §3.1.2「新机制若需要新的静态事实，加字段、不改签名」的规则给 `ctx` 加一个查询标记字段。影响面限于用 `get_pity_probabilities` 的策略（`strategies/builtin/pity_reserve.py` 等），当前配置里没有 `rotating_cr` 落在这些池上，但性质须说清而非留白。<!-- P64-S8-CLOSURE -->
> **接线点与捕获面的登记（S8-5 审查，2026-10-14）**：② 的落点是 `PityContext.readonly`，**唯一写入点是 `Pity.before_draw` 的首行**（`pity.py:1416`）。**Modifier 级用例直构 `ctx(readonly=True)` 会绕过该行**，故该行必须有**引擎级**捕获面，否则它被删时 Modifier 级用例仍绿（S8-5 实测复现：删该行后既有 Modifier 级用例 1 passed，新增的 `boundary_readonly_query_suppresses_cr_intercept` 转红）。

**接线（§1.5）与 S8 的交互**：接线引入的 `_pool_order` 独立排序视图作用于「按哪个顺序遍历保底」，与本节改造的「单个保底内部如何算概率」是正交的两层，互不影响。

---

### 3.10 状态可见性与 G3 真实建模（2026-09-21 裁决）

#### 3.10.1 四类状态的处置

Modifier 在 `compute_delta(view, dist, ctx)` 中能读到什么，是表达力的一个独立维度（与分布空间正交）。裁决如下：

| 状态 | 真实需求 | 裁决 | 依据 |
|------|---------|------|------|
| 本保底的状态 | 大量 | 保持 | 计数、标志、命定值等 |
| **其他保底的状态** | **零** | **不纳入**，且架构上关闭（3.10.3） | 手册全量查证（2026-09-21）：所有「清零 / 重置 / 联动 / 互斥」描述均属三类——保底自身计数被重置、同名保底跨池共享、资源生命周期（P77）；**无一处需读其他保底状态** |
| **GachaState**（持有 / 资源） | G3 一处 | **开放**，经 `ctx.sim` 直接可读（3.10.2） | CLAUDE.md §二「精确建模原则」：G3 不接受 pool 层近似 |
| 时间 | 零 | 不开放 | 时间型机制属 Banner lifecycle 层，P61 已覆盖 |

两处最像「跨保底读取」的机制已逐一排除：

- **绝区零 G5**：`hard(max_triggers=1)` 与 `targeted` 同时作用于同 scope（[手册:560](docs/主流抽卡游戏卡池机制配置转换手册.md#L560)）——这是**执行顺序**问题，由 §1.5 裁决的 `priority` 处理，不涉及状态读取。**ISSUE-032 注**：`max_triggers` 是手册的散写，`PityDef` **无该字段**（见 §3.1.3），此处引用的是「福利保底与 targeted 同 scope 共存」这一**形态**，不代表该配置键已存在
- **终末地计数器 3**：「获得首个 UP 后 240 抽」看似依赖另一保底的触发事件，实为**自身 Flag 门控**（出 UP 时置位，计数器仅在置位后推进），单保底内即可表达

#### 3.10.2 模拟级状态经 `ctx.sim` 直接可读（2026-10-06 改判）

> **本节结论已反转。** 原设计（2026-09-21）用 `PityDef.reads` 声明 + 门控填充 `ctx.external`，未声明则为 `None`。**2026-10-06 用户裁决取消该机制**：`sim` 成为 `ctx` 的普通字段，永远填充、非 Optional。

**形态**：

```python
@dataclass(frozen=True)
class DrawFacts:                 # 原 ctx，三字段 + 一个
    scope_cards: Mapping[str, tuple]
    featured_cards: Mapping[str, tuple]
    rarity_rank: Mapping[str, int]
    sim: 'SimView'               # ← 非 Optional，永远填充

class SimView:
    """模拟级状态的只读视图（玩家持有 / 资源）。"""
    def owns(self, card_id: str) -> int: ...      # 该卡持有张数（`total_holding` 口径，含初始持有）
```

```python
class NotOwnedModifier(Modifier):
    def compute_delta(self, view, dist, ctx):
        if view.get('counter') < self._threshold:
            return None
        A = tuple(c for c in ctx.featured_cards.get(self._scope, ())
                  if ctx.sim.owns(c) == 0)        # 直接读，无 None 检查
        ...
```

**改判理由：原设计把一个 Optional 字段变成了四层静默失效来源。**

| # | `external` 为 `None` 的来源 |
|---|---------------------------|
| 1 | 默认参数：`PityEngine.before_draw(..., external=None)` 是可选参，不传即 None |
| 2 | 通道 A（`Banner.draw`）漏填 |
| 3 | 通道 B（`StrategyContext.get_pity_probabilities`）漏填 |
| 4 | 门控拦截：保底未声明 `reads` |

而 **`None` 的语义是「恒等」**（Modifier 读到即 `return None`），故四层来源**全部落到「保底静默不生效、无任何报错」**。计划为此打过两个补丁，都在处理同一个症状：

- **ISSUE-013**（2026-09-22）：「Modifier 内**必须先判 `ctx.external is None`** 再读外部状态」，即把兜底责任推给每个 Modifier
- **AUDIT-BREAK-9**（2026-09-22）：「两条送达通道**必须都填**」，即用纪律补漏

**门控是纯负债**：它的正向功能是「防止 Modifier 意外读 sim」，但读 sim 的 Modifier 是有意读的，不会意外；它只贡献了第 4 层 None 来源。

**依赖显式这一条保留，但改由手工注解承担**：

```python
class NotOwnedModifier(Modifier):
    uses_sim = ('owns',)         # 纯文档：供检查器报告「哪些保底读了 sim 的什么」
```

**注解不参与门控**，理由：它的漂移后果是「文档过时」，而门控的漂移后果是「保底静默算错」。两者不对称，故只保留前者。注解里的名字仍须校验为已知源（`owns`），否则 `ConfigError`。

**删除的符号**：`PityDef.reads`、`Pity.reads` 形参、`PityEngine.get_reads_for_pool()`、`Pity._gated_ctx`、`ExternalView`（改名 `SimView`）、`ExternalView.balance()`（**全库零使用**，§3.10.1 的需求只有 G3 一处而 G3 只用 `owns`）。

**保留的**：`GachaState.external_view()`（改名 `sim_view()`）：`SimView` 仍需要一个构造点，它仍是「材料全在 state 上」的那一个方法。**（2026-10-10 澄清）**：本段与上段的「删除 / 保留」说的是**本轮设计符号的增删**，不是现行代码状态——`ExternalView` 与 `GachaState.external_view()` 在**全库零命中**（从未进入代码），`ExternalView.balance()` 的「全库零使用」是在设计稿语境下说的，不构成对现行代码的事实断言。

**两条送达通道仍然存在**（`Banner.draw` 与 `StrategyContext`），但**漏填的后果变了**：`sim` 非 Optional，构造 `ctx` 时缺参即 `TypeError`（构造期失败），而非运行期静默恒等。

<!-- REVIEW-R1-FIX: SIM-IN-CTX -->

<!-- P64-S9-2-LANDED -->
> **注解校验的作用域与归属登记（S9-2 审查，2026-10-14）**：① `uses_sim` 的校验**只遍历 `modifiers`**（`Tracker` / `Lifecycle` 侧无承载面；在 Tracker 上声明未知源不会报错），这与本节的注解形态（只给 Modifier）自洽，但**与 `after_draw` docstring 的「Tracker 亦可读 `ctx.sim`」合看则存在不对称**，登记备查。② `KNOWN_SIM_SOURCES` 住**实现层**（`pity_modifier.py`）、校验函数住**编排层**（`pity.py`），计划未规定两者归属，属 S9-2 的自定口径（理由：校验函数若也放实现层，需在实现层引 `config_store`）。③ 校验点位于 `Pity.__init__`、**任何 state 写入之前**，且**不参与门控**（实测删掉 `NotOwnedModifier.uses_sim` 后全量全绿）。④ **`sim=None` 不被类型系统拦**：类型系统只拦「缺参」（`TypeError`），显式传 `None` 能构造成功、消费点抛 `AttributeError`（**响亮失败，非静默恒等**），故本节要消除的静默失效形态确已消除，但「非 Optional」是**约定而非运行时强制**。

#### 3.10.3 关闭跨保底读取（StateView）

现状有一个**无守卫的口子**：`PityState` 全局共享，Modifier 拿到的是整个对象，`state.get('别的保底名', 'key', 0)` 今天就能跑通且不报错。既然真实需求为零（3.10.1），处置是**架构上关闭**，而非把它正规化。

<!-- REVIEW-FIX-PREV: ISSUE-004 -->
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

<!-- REVIEW-FIX-PREV: ISSUE-103 -->
**`ctx.state` 是同一份账本的另一条通道，须显式关闭（ISSUE-103，强制）**：`PityContext.state` 仍是原始 `PityState`（§3.10.2 的字段注记已改回），故 Modifier 若写 `ctx.state.get('别人的保底名', 'key', 0)` 今日依旧跑通——**「架构上做不到」只对 `view` 形参成立，对 `ctx.state` 不成立**，后者靠纪律关闭。三条落地项：

- **纪律**：Modifier **只经 `view` 读状态**，禁止经 `ctx.state` 读任何状态键（**含自身命名空间**——自身也走 `view`，避免两套读法并存后难以审计）。写入侧不受影响：Tracker 的 `commit(ctx, state, name, …)` 接收的仍是原始 `state`（§3.1.1 协议表）。
- **三处存量迁移（S9 必改项）**：`TargetedBehavior` 的三处 `ctx.state.get(self._name, "selected_card")`（[pity.py:649](gacha_simulator/core/pity.py#L649) / [:661](gacha_simulator/core/pity.py#L661) / [:675](gacha_simulator/core/pity.py#L675)；**ISSUE-946** 实测更正原引 `:651 / :663 / :677`）——~~targeted preset 化后改由 `ForceSelectedModifier` 经 `view.get("selected_card")` 读取~~（**订正（S9-1 审查，2026-10-14）**：① 类名 `ForceSelectedModifier` 是**改名前的旧名**，现为 `SelectedModifier`（§3.1.2 的对照表已映射）；② **迁移形态写错**：`TargetedBehavior` **没有 `view` 形参**，实际形态是 **`StateView(ctx.state, self._name).get("selected_card")`**（S9-1 已落地为私有方法 `_selected_card(ctx)`）；新骨架侧才是 `SelectedModifier` 的 `view.get("selected_card")`。**S9-4 的可机械复核判据应为「`pity.py` 内不再出现 `ctx.state.get(`」，而不是「出现 `view.get("selected_card")`」**（后者在 `pity.py` 内恒零命中）（`selected_card` 由策略层 `NonDrawAction` 写入**自身**命名空间，`view` 看得见，跨保底读仍被关闭）。另 [pity.py:530](gacha_simulator/core/pity.py#L530) 的（**ISSUE-946** 实测更正原引 `:532`） `PityContext(draw=ctx.draw, current=modified, state=ctx.state)`（`SoftPityMixin.before_draw` 的 fork）随 mixin 退役一并消失，不构成迁移项。
- **登记**：S9-1 任务项、§四 `core/pity.py` 行、§六 S9 口径均同步本条。

**命名空间绑定已定稿（2026-09-21 审查补；2026-09-22 定稿，见下方「view 按零件命名空间分配」段）**：组合型 `_soft` 族存在**两个**命名空间——`SoftPityMixin._init_soft_pity` 以 `name + '_soft'` 构造内部 `SoftStepBehavior`（[pity.py:527](gacha_simulator/core/pity.py#L527)），而 mixin 自身的 `_counter` 在 `name` 下（[pity.py:528](gacha_simulator/core/pity.py#L528)，`before_draw` 的 `v = self._counter.incr()` 即被 `SoftStepBehavior` 消费的软计数）。`StateView` 的 `name` 取哪个**不再留到 S9 临场决定**，否则「读自己」也会返回 default，落进本文反复强调的静默失效模式。

<!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order -->
**定稿：view 按「默认 + 零件命名空间」两级分配（ISSUE-GATE-dependency-order，2026-09-22，强制）**

| 层 | 命名空间 | 承载 |
|----|---------|------|
| **默认 view** | `self._name` | 未声明 `namespace` 的零件一律用它；**soft 族的软计数在此**（对齐旧 mixin 的 `X.counter`，[pity.py:528](gacha_simulator/core/pity.py#L528)），故 `BoostModifier` 读软计数不经额外 view |
| **零件命名空间 view** | `part.namespace` | 声明了 `namespace` 的零件（Tracker / Modifier / Lifecycle）由 `Pity` 按 `StateView(state, part.namespace)` 建独立 view，调用该零件时传**它自己的 view** |

三条配套定稿（**ISSUE-407，2026-09-30 独立复核补：三条原稿只写「谁负责」，未给出接口与落点，现补实**）：

1. **`_soft` 族保留 `X_soft` 命名空间**：该族 preset 显式声明一个**命名空间载体 Tracker**（`NamespaceTracker(namespace)`，§3.1.1 签名表新增条目；语义为空、不影响概率），使 `X_soft` 命名空间存在并与 ISSUE-023 的快照口径一致（旧实现该空间只有 `_active` 一个键，[pity.py:133](gacha_simulator/core/pity.py#L133)）。**载体必须写进 preset 代码**——原稿只写「该族 preset 声明一个载体」，而 §3.2 的 preset 代码里没有任何载体、四个 Tracker 的签名表也没有 `namespace` 形参，`X_soft` 的产出者无处落地。示例（`rotating_soft`，另两个 `_soft` 类型同形）：<!-- REVIEW-R1-FIX: ISSUE-002 -->

```python
def _preset_rotating_soft(pdef):
    deltas = _soft_deltas_of(pdef)      # M6，同 _preset_soft_step（ISSUE-001）
    return dict(
        lifecycle=build_lifecycle(pdef),
        trackers=[
            FlagTracker(scope=scope, judge="featured", hit="clear", miss="set", flag="guaranteed"),
            CounterTracker(scope=_norm_scope(pdef), reset_on=_norm_scope(pdef), init=pdef.counter_init),
            NamespaceTracker(namespace=f'{pdef.name}_soft'),   # ← ISSUE-407：X_soft 的唯一产出者
        ],
        modifiers=[SoftModifier(scope, deltas=deltas),
                   RotatingModifier(scope)],
        flags={"guaranteed": pdef.guaranteed_init},
        counters={"counter": pdef.counter_init},
    )
```

2. **`_active` 写入的作用域推广**：`Lifecycle.initialize` 的写入对象由「本保底命名空间」推广为「**本保底声明的全部命名空间**」——**接口定稿为 `initialize(state, name, namespaces=())`**，`namespaces` = `Pity` 收集到的零件命名空间集合（`{getattr(p, 'namespace', None) for p in _trackers + _modifiers + [_lifecycle]} - {None}`）；`AlwaysActive` / `FiniteActive` 对 `name` 与其中**每个**命名空间各写 `_active = True`，`DependentActive` / `DependentFiniteActive` 仍为空实现；`deactivate(state, name)` **只清默认命名空间**（退役只作用于本保底）；**`rebind` 同批收 `namespaces`**（**ISSUE-917**）：两接口实参面必须对称，否则 `X_soft` 的 `_active` Flag 在 worker 内跨场重绑后仍指上一场 state（§3.1.3 有专段）。<!-- REVIEW-R1-FIX: ISSUE-917 -->否则 `X_soft: {_active: True}` 无处产生，ISSUE-023 的快照断言与「统一 `_active` 写入」互相牵制。**调用次序**：`Pity.__init__` 先收集零件命名空间、再调 `initialize`、再建 view（§3.1.4 骨架的 ISSUE-202 行已按此写）。
3. **`_view` 的语义不变 + 按零件分发**：§3.1.4 骨架的 `self._view` 是**默认 view**（`self._name`）；`Pity` 另按命名空间建 `self._ns_views: Dict[str, StateView]`，调用某零件时取 `self._ns_views.get(getattr(part, 'namespace', None)) or self._view`（`Pity` 对 `trackers` / `modifiers` 的遍历点一律走该取值，不得写死 `self._view`）。`_rebind_state` 重建默认 view 的**同时**按同一 state 重建 `_ns_views`（否则 worker 内连跑 N 场模拟时零件 view 指向旧账本，与 ISSUE-004 同一失效模式）。<!-- REVIEW-R1-FIX: ISSUE-407 -->

> **为何不给「soft 计数并入 `X` 单命名空间」留口子**：ISSUE-023 已论证 `X_soft` 必须原样保留（快照逐场一致的前提），两种写法择一写死，本计划取上表方案；实施时不得既合并命名空间、又保留原断言。

**两个命名空间必须原样保留（ISSUE-023，强制）**：这不只是 S9 的读取侧命名问题，它同时是 **S1–S5 等价性验收的前提**——§六 S1–S5 要求「新引擎输出的状态快照与旧类**逐场完全一致**」，而 `PityState.to_dict()` 输出**全部**命名空间。代码事实：内部引擎 `SoftStepBehavior(name + '_soft', state, …)` 经 `CounterBasedBehavior.__init__` 写 `_active` Flag（[pity.py:133](gacha_simulator/core/pity.py#L133)），故旧实现在 `X_soft` 命名空间里留下 `{_active: True}`，加上 mixin 自身在 `X` 下的 `counter`，快照共含**两个**命名空间。因此 `_soft` 族 preset 化时须**原样保留 `X_soft` 命名空间及其中的 `_active` 键**（内部 soft Tracker 的命名空间名取 `f'{name}_soft'`），**不得**把 soft 计数合并进单一命名空间、也不得改名。若实施时确要合并，必须**先把该快照差异登记进 §六 的差异归因清单并相应放宽 S1–S5 的「完全一致」断言**——两条路择一，不得既合并又保留原断言。<!-- REVIEW-R1-FIX: ISSUE-002 -->

**不影响 `depends_on`**：激活传播由引擎在 `PityEngine.after_draw` 中执行（`state.set(dep_name, "_active", True)`），不经过 Modifier，故不受 StateView 影响。

<!-- P64-S9-1-LANDED -->
> **S9-1 收口登记（`5a63e2a` + 审查，2026-10-14）**：
> **① 一条比 ISSUE-103 更严的验收子句（审查建议保持，已登记）**：S9-1 的正例断言「骨架的 **`before_draw` 路径整体**不触 `ctx.state`」，而 ISSUE-103 的纪律只约束 **Modifier**。审查判定**不应收窄**（收窄后「骨架把 `ctx.state` 当 view 传或作他用」这一失效形态会失去牙齿），并给出**将来的处置规则**：若骨架出于正当理由引入 `ctx.state` 消费者，应把该子句**收窄到 Modifier 相位**，**而不是删除**。
> **② 行号锚点已漂移（refcheck 无标记故无机器门控）**：三处迁移点在基线 `876254c` 上实测为 `pity.py:723 / :735 / :749`（计划写 `:649 / :661 / :675`，**ISSUE-946** 曾订正为 `:651 / :663 / :677`，仍不准），S9-1 迁移后为 `:738 / :750 / :764`；`SoftPityMixin` 的 fork 计划写 `:530`、基线实测 `:604`。**建议后续改用符号化引用**。
> **③ 本迁移是「为 S9-4 的断言时点服务」的临时面**：它随 ISSUE-502 的删除 commit 一并消失，**不应被当作长期资产维护**。

#### 3.10.4 G3 真实建模（崩坏3 精准补给）

机制（[手册 §7.1:938](docs/主流抽卡游戏卡池机制配置转换手册.md#L938) / [§7.2 历史配置示例:970](docs/主流抽卡游戏卡池机制配置转换手册.md#L970)；原引 `#L959` 已随 §7 重写漂移，2026-09-30 修正）：精准补给每 50 抽必出 UP 装备，但**已获得的装备从 UP 组中排除**。

**所涉卡池已下线 → 本节按「历史机制建模能力」交付（2026-09-29 定位更正）**：精准补给 2016-10-02 ~ 2024-11-06（静默替换为装备补给）、演武精备 2024-07-24 ~ 2025-01-08。**第二部的「装备补给」不是同一机制**：它是「单目标 60 抽必出指定武器 + 获得时重新计数」，**无「未获得」语义**，用既有 `hard` / `targeted` 即可表达，不需要本节能力。两者的区分见手册 §7.1 的「存续」列与 §7.2 的「历史卡池」段。

**为什么不能沿用 pool 层近似**：pool 层过滤（把已拥有的卡从 reward 列表移除）会让**每次抽卡**都不出它们，而真实机制只作用于「50 抽 UP 保护」这一个触发点——普通抽卡仍可产出已拥有的装备。按「精确建模原则」这是语义打折，不接受。手册原先将其归为 pool 层，是架构约束下的权宜。

**实现**：一个 `NotOwnedModifier` 零件（§3.1.2 机制表第 7 行），四样由 `compute_delta()` 就地算出：条件 `counter >= τ`；A = `featured_cards[scope]` 中**未拥有**者（**动态目标**，由下方 `_t_not_owned` 解析器给出）；Q = 更低稀有度 ∪ `scope\A`；转移量 = `p(Q)`。下给出的是**目标解析器**的实现（原 `ForceNotOwnedModifier` 类本体的前半段）：

> **2026-10-07 裁决（用户）**：Q 取「更低稀有度 ∪ `scope\A`」，即**已拥有的 UP 落在 Q 内、本抽被搬空**，实现「必出未获得的 UP」。原文写 `mode = 'assign'`（绝对写入通道），与本节末段的 `transfer_linear` 形态互斥，且其 Q 不含已拥有者、等于不排除，已按裁决改正。

<!-- REVIEW-FIX-PREV: ISSUE-016 -->
<!-- REVIEW-FIX-PREV: ISSUE-013 -->
<!-- REVIEW-FIX-PREV: ISSUE-GATE-3-dependency-order -->
```python
def _t_not_owned(scope, field='featured_cards', on_all_owned='skip'):
    """G3 的目标组解析器：scope 内的目标卡中「未拥有」的子集（§3.1.5.2.3 第 7 行）。

    on_all_owned 决定「全部已拥有」这一退化分支的行为（§3.10.4 的待确认项）：
      'skip'（形态 a）-> 返回 ()，该次保底不触发（恒等）
      'any' （形态 b）-> 目标集退化为全部目标卡，仍给出一件
    """
    def resolve(ctx, view, dist):
        # 2026-10-06：ctx.sim 非 Optional，无需 None 兜底（§3.10.2 改判）
        pool_cards = ctx.featured_cards.get(scope, ()) if field == 'featured_cards'             else ctx.scope_cards.get(scope, ())
        if not pool_cards:
            return ()              # scope 键缺失，空集合返恒等（ISSUE-016）
        target = tuple(c for c in pool_cards if ctx.sim.owns(c) == 0)
        if not target:
            # 全部已拥有：形态 a 返空（该次保底不触发）；形态 b 退化为全部目标卡（§3.10.4 待确认项）
            if on_all_owned == 'skip':
                return ()          # 形态 a（§3.1.5.6）
            return pool_cards      # 形态 b
        return target
    return resolve
```

> **原类本体的 `factor` 后半段已删除**：该职责由 §3.1.2 机制表的 `NotOwnedModifier` 承担（`compute_delta()` 内直接调 `transfer_linear`），Q 由「更低稀有度 ∪ scope 减 A」就地算出，**不再需要 `resolve_universe` 与 `exempt` 特判**（更高稀有度不写增量即自动不变）。**这是 2026-10-06 简化的核心：类消失，只剩一个 `compute_delta()` 与一个助手。**


配套（**2026-09-28 定稿**，原写「待 S9 实施时定」；**2026-09-30 用户裁决改为双实现**，见下第 1 条与末段「双实现的形态选择」）：

1. **新增两个独立 type（双实现，2026-09-30 用户裁决）**：`BEHAVIOR_REGISTRY` 注册两条 preset，**四键齐全**（对照 `_preset_hard`，2026-09-28 复核补）。两条除 `on_all_owned` 取值外**完全同构**，trackers / lifecycle / counters / 条件极性 / F 语义全部共享（**GATE-FAIL-6-测试策略，2026-10-09 修正**：原列 `reads`，该字段与门控已随 2026-10-06 的 §3.10.2 改判取消，`ctx.sim` 直接可读）：
   - **`hard_exclude_owned_skip`**：display_name「硬保底·排除已获得（全拥有时保底不触发）」、`on_all_owned='skip'`（候选 a / 形态 a）
   - **`hard_exclude_owned_any`**：display_name「硬保底·排除已获得（全拥有时仍给一件 UP）」、`on_all_owned='any'`（候选 b / 形态 b）
   - **命名口径（2026-09-30，强制）**：形态写进 **type key**（TOML 里自解释，不得留一个读不出形态的裸名）与 **display_name**（GUI 下拉与「关于」页面同源呈现，见第 4 条）；两条 display_name 必须带形态括注，禁止只差一个字的短名
   - `trackers=[CounterTracker(scope=_norm_scope(pdef), reset_on=pdef.reset or _norm_scope(pdef))]`——**`reset_on` 取 `pdef.reset or _norm_scope(pdef)`**，原稿写死 `"scope"` 会让 `reset` 配置被静默忽略（§3.2 取值来源表已定该口径）
   - `modifiers=[NotOwnedModifier(scope, threshold=tau, on_all_owned=<形态>)]`，其中 **`tau = pdef.threshold if pdef.threshold is not None else 50`**——`PityDef.threshold` 默认 `None`（[config_store.py:162](gacha_simulator/core/config_store.py#L162)）且 `_build_pity` 直取 `p.get('threshold')`（[config_toml.py:700](gacha_simulator/core/config_toml.py#L700)；**ISSUE-946** 实测更正原引 `:692`<!-- REVIEW-R1-FIX: ISSUE-929 -->），不回退则 TOML 不写该键时条件成 `counter >= None`（TypeError）；`_preset_hard` 的同一回退见 §3.2 取值来源表
   - `lifecycle=build_lifecycle(pdef)`——**原稿未给**，缺则该类保底的 `deactivate_on_early_hit` / `depends_on` / `max_triggers` 全部静默失效（§3.1.3 与 §3.2 均要求每个 preset 必含该键，`create_behavior` 有 `ConfigError` 防线）
   - `counters={"counter": pdef.counter_init}`——**原稿未给**，缺则「已垫抽数」静默归零（对照 `_preset_hard`）
   - registry 两条的 `params` 中 `threshold` 的 `default` 取 **50**（与机制一致，`hard` 为 90）；`default_scope` 一律取 `"ssr"`
2. ~~**`config_toml` 校验放行**该 type（`_build_pity` 的类型白名单）~~ **该条删除（2026-09-30 事实修正）：白名单不存在**。实测 `_build_pity` 只校验 `name` 与 `scope`，`_check_pity_format` 只管新旧格式；把 `type = "hard_exclude_owned"` / `"rotating_inverse"` 交给 `_build_pity` 直接通过、不抛错。未知 type 的真实后果在引擎侧：`create_behavior` 的 `BEHAVIOR_REGISTRY[btype]` 抛 `KeyError`，被 `PityEngine.__init__` 的 `try / except Exception` 吞成 `logger.warning` 后跳过，引擎照常构造、该条保底静默消失（实测 `behaviors == []`）。这正是 S4-5 要修的问题，修好后未知 type 在构造期抛 `ConfigError`，**任何层都不需要类型白名单**。同一处事实错误还出现在 §四 的 `core/config_toml.py` 行（`rotating_inverse` 校验放行）与 §七 S9-3 的目标文件清单，两处已同步删除
3. **GUI 下拉自动出现**——`_PITY_TYPES` 改为由 `BEHAVIOR_REGISTRY` 生成（§3.6 的改造，落在 S6a），新 type 注册后自动进入下拉，**不需要手工追加**（**前提 = S6a 的该项改造已落地；未落地则本步手工追加**）<!-- REVIEW-R1-FIX: ISSUE-929 -->
4. **「关于」页面文本改由 registry 生成（2026-09-30 新增，归 S9-3）**：`gui/about_dialog.py` 的「保底机制」条目（[about_dialog.py:67](gacha_simulator/gui/about_dialog.py#L67)）现只列 4 种，P56 交付的 6 种事件驱动型至今未登记；`_create_config_guide_tab` 的 `[[pity]]` 示例注释（[about_dialog.py:207](gacha_simulator/gui/about_dialog.py#L207)）现只列 6 种。**两处改为由 `BEHAVIOR_REGISTRY` 的 `display_name` 生成**，与第 3 条同源。理由：硬编码列表已漂移过一次，而「声明与承接分居两处」是本计划审查中出现频率最高的缺陷形态（peer-review 教训一）；改由 registry 生成后，两种形态的说明随 `display_name` 自动进入关于页，**单一真相源**，本节的形态措辞只需维护一处
5. ~~配置加 `reads = ["acquired"]`~~（**2026-10-06 删除**：`ctx.sim` 直接可读，无配置项）

> **条件极性的修正（2026-09-28 独立审查发现；2026-10-09 按 §3.14 改判改述触发形态）**：`NotOwnedModifier` 的触发条件必须是 **`counter >= pdef.threshold`**（50 抽保底触发时；§3.14 条件内联后即 `compute_delta()` 开头的 `view.get('counter', 0) >= pdef.threshold` 判断），**不是恒真**。**GATE-check-6**：原写 `CounterCondition('counter', pdef.threshold)` 与 `Always()`，两个条件类名均已随 §3.14 改判取消，此处按现行内联形态重述。原稿在 §3.14.2 的条件表与 §3.14.6 的修订范围表里写成 `Always()`（两处均已随 2026-10-06 改判删除，本条按历史记录保留），那等于「每次抽卡都只出未拥有的」——**正是本节开头自己否定的那个 pool 层近似**（「pool 层过滤会让每次抽卡都不出它们」），并与 §六 的 G3 断言②「普通抽卡仍能产出已拥有的装备」直接冲突。加上该条件后，preset 里的 `CounterTracker` 也才有了消费端（原稿声明了计数器却无任何条件读它）。
>
> **注册面补全（同次审查；2026-09-30 按双实现更新为两条）**：`hard_exclude_owned_skip` / `hard_exclude_owned_any` **两条** registry 条目须与本批新增的 `rotating_inverse` **同构**——① `display_name`（按上条第 1 项带形态括注，两条不得同名）；② **`default_scope`**（取 `"ssr"`，与既有 10 条一致）；③ **`params`**（`threshold`，与 `hard` 同形）；④ **四类集合分类**：`_BTYPE_ORDER`（counter 驱动，与 `hard` 同级取 `1`）、`_EVENT_DRIVEN_TYPES`（**不在**此集）、`_SOFT_TYPES`（不在）、`_HARD_TYPES`（**在**）。缺任一都会让新 type 在排序、校验或软硬判定上落空。**②③④ 三条对两条完全一致，只有 ① 与 preset 工厂里的 `on_all_owned` 取值不同**。

**为什么定为独立 type 而非 `hard` 的可选参数（如 `exclude_owned = true`）**：① 与 G1 的 `rotating_inverse` **同构**（G1 亦走新 type，见 S6a）；② 参数化方案要连带 `PityDef` 新字段 + `config_toml` 解析 + GUI 复选框 + preset 工厂分支**四处**，而新 type 只需在既有注册/校验/下拉三处机制上追加；③ 语义上「排除已获得的硬保底」是一个独立机制，不是 `hard` 的一个开关。

> **双实现的形态选择（2026-09-30 用户裁决）**：同一论证也适用于「形态 a / 形态 b」这一对。与其在 `PityDef` 上加一个枚举字段（连带新字段定义 + 解析 + round-trip + GUI 控件，且该字段只为这一条保底存在），不如用两个 type 承载，差异只落在 `NotOwnedModifier` 的一个构造参数上；且现有 `rotating` / `rotating_soft` / `targeted` / `targeted_soft` 已是「同族机制多 type」的既有模式。**否决的备选**：`hard_exclude_owned` 单 type 加 `all_owned_behavior = "skip" | "any"` 取值。技术上可行（registry 的 `options` 会自动渲染成 QComboBox，[config_panel.py:2789](gacha_simulator/gui/config_panel.py#L2789)），但会把一个「待确认的子行为」升格为 `PityDef` 的常驻字段（键集 24 → 25），且手册缺口表要在「一个 type 的一个取值」上做文章，消除债务时留下一个无用的空字段。

**「全部已拥有」的退化分支：待确认（2026-09-21 审查修正；2026-09-29 专项查证后维持；2026-09-30 如实记录分歧，不按旁证定稿）**。手册 §7.1 / §7.3 / §21 均未描述该情形，**无信源**。当前拟定为「返回恒等」（无可导向目标），但这意味着该次 50 抽的「必出 UP」不发生，与规则原文「**必定获得**一件未获得的 UP 装备」的前半句可能冲突。按「不凭空断言」纪律标为**待确认**，实施前需查证游戏机制或由用户裁定。原稿直接判「合理选择」并为其设验收，属越权断言。

**2026-09-29 专项查证结论（方法与信源强度见手册 §7.4 / §7.5）**：**零直接信源**：四个候选均未被证实，也均未被排除：**(a)** 该次保底不触发 / **(b)** 给出一个 UP 装备（不保证是「未获得」的）/ **(c)** 转常驻池 / **(d)** 转碎片或其它补偿。检索环境受限（NGA / 米游社 / 贴吧 / HoYoLab 反爬拦截，Bing 对中文长尾无结果），能拿到的只有官方公告镜像。

**两种倾向及其不一致（如实记录；两者均无判据，均未定稿）**：

| 倾向 | 内容 | 依据 | 依据强度 |
|------|------|------|---------|
| **(a) 保底不生效** | 候选集（未拥有的 UP 装备）为空 → 该次保底**不发生**，不给出任何 UP 装备 | ① **旁证**：同项目**家园补给**（同类「必 new」机制）在「已获取全部所含角色」时**机制不生效**：「必为未获得女武神的机制（除非已经获取全部家园补给的所含角色）」（萌娘百科单源，该段落**自标「待补充」**）；② **反证 (d)**：同项目**扩充补给**（角色池）在已拥有 UP 角色时另有「副产物随机替换为碎片能量」的记载（**同在萌娘百科该段落**，与①同源、非独立信源），而**装备精准池无任何对应条文**，即崩坏3 确实有「已拥有时转碎片」的设计，但它落在角色池、不在装备池，反过来说明装备池走的是「候选为空即不触发」而非「转碎片」 | 社区维基**单源** + 同源性推断；**非**直接证据 |
| **(b) 仍给一个 UP** | 该次保底**仍生效**，但目标集退化为全部 UP → **给出一个 UP 装备**（不保证是「未获得」的） | 用户 2026-09-28 的判断「UP 里随机给一个比较合理」（同轮另有「应该先努力查证」的要求），**提出于上述查证之前**，是**设计倾向**而非信源 | **零信源**（纯设计倾向） |

**不一致点（两处，且不是同一件事）**：① **给不给**：(a) 该次保底不发生，(b) 仍给出装备；② **给的是什么**（这条更关键）：(b) 保住了「**必定获得**一件 UP 装备」的字面承诺，代价是放弃「**未获得的**」这个限定；(a) 则两个限定都放弃。换言之，**两者各违背规则原文的一半**：(a) 违背「必定获得」，(b) 违背「未获得」，**无一方能凭规则文本胜出**。所以「按旁证定稿为 (a)」并不比「按倾向定稿为 (b)」更有文本依据，差别只在 (a) 多一条同项目旁证。

**裁定（2026-09-30 用户裁定）**：**维持「待确认」，不按旁证定稿**。理由：(a) 的唯一支撑是**社区维基单源且自标「待补充」**，按「两个以上不同信源一致且无矛盾」的信源纪律**不构成判据**；(b) 更是零信源。按「精确建模原则」的推论，**无等价实现可写时应显式登记为缺口/待确认，而非择一交付**。

**实现侧（2026-09-30 改为双实现并列，不确定性不再挂起在单一实现上；用户裁决）**：S9-3 落地时**两个 type 都建**：`hard_exclude_owned_skip`（形态 a，`on_all_owned='skip'`，即 `target` 为空时 `return None` 退化恒等）与 `hard_exclude_owned_any`（形态 b，`on_all_owned='any'`，即目标集退化为全部 `pool_cards`、仍给出一件）。**两者都不是定稿**：它们是一对并列的建模假设，由用户按需选择，谁也不是「已确认等价」的实现。§六 G3 专项第 ③ 条与 §七 S9-4 的验收命令在机制定稿前**不得当作已定稿验收通过**（两处已加注，并已按两个形态拆成两条断言）。若日后查证定稿为其中一方，**删去被否的那个 type 即可**（registry 条目 + preset 工厂 + GUI 下拉 + 关于页措辞随 `display_name` 自动同步），S8 管道与 `ctx.sim` 送达机制不受影响（**GATE-FAIL-6-测试策略，2026-10-09 修正**：原写「`reads` 机制」，该字段与门控已于 2026-10-06 随 §3.10.2 删除）。**债务登记**：按「精确建模原则」的推论，这一对是**待消除的债务**而非可接受终态，手册 §7.3 / §21 登记为**一条**待确认项、两个候选实现（不得登记成两条独立缺口）。

**与 §3.7 槽位粒度约束的关系**：G3 同时需要 S8（子集定向）与本节（状态可见性），两者都到位才可表达。

---

### 3.11 架构的表达能力与边界（2026-09-21 新增）

> **为什么单列一节**：P64 的定位是「通用保底引擎」，其价值取决于「能表达什么、不能表达什么」是否清晰可判。此前的边界信息散落在 §3.1.5.6（数学边界）、§3.7（范围边界）、§3.9.5（实现边界）、§3.10.1（状态裁决）四处，遇到新机制时判定成本高、且容易误判（本轮审查即发现 `F` 算子的定义被写错）。本节把三类信息集中，并给出**判定方法**而非仅列清单。

#### 3.11.1 表达能力（三层，互相正交）

| 维度 | 能力 | 形式化位置 |
|------|------|-----------|
| **状态空间** | `Z^k × {0,1}^m`：k 个计数器 + m 个标志，数量由 preset 静态声明 | §3.1.5.1 |
| **分布空间** | **卡级**任意子集上的增量调制（S8 前为槽位级） | §3.1.5.2、§3.1.2 D20 |
| **状态可见性** | 本保底状态 + `ctx.sim`（模拟级状态：`acquired` / `resources`）；**不含**其他保底状态 | §3.10 |
| 抽样模型 | 从分布独立抽样（`ξ ~ p`） | §3.1.5.1 |

**判定方法**：给定一个新机制，问三个问题——
1. 它的历史依赖能否用**有限个计数器/标志**声明？（能 → 状态空间够）
2. 它的概率操作能否写成**增量向量**？（能 → 分布空间够；注意增量可依赖当前分布）
3. 它需要读的信息是否在**本保底状态或 `ctx.sim`** 内？（是 → 状态可见性够）

三问皆「是」则可表达，且实现方式是「新增 Tracker 或 Modifier 零件，不改架构」（§二目标）。

#### 3.11.2 边界（三类，各附判定依据）

| 边界 | 内容 | 依据 |
|------|------|------|
| **非抽样型抽卡** | 结果不是「从分布独立抽样」的机制（如异环棋盘：掷骰前进、落点由当前位置决定，属马尔可夫转移）。入口在 **pool 层**（`pool.draw`）而非 pity 层 | [手册 §20.2](docs/主流抽卡游戏卡池机制配置转换手册.md#L2143) |
| **跨保底状态耦合** | 「A 触发后修改 B 的状态」不能表达（`StateView` 架构上关闭，§3.10.3）。替代：`depends_on`（激活传播）、状态合并、或同名共享 | §3.10.1 裁决；手册全量查证「零真实需求」 |
| **求值顺序敏感** | 增量依赖当前分布时，换序一般改变结果（§3.1.5.3）。这是**语义属性**（约束冲突），非实现缺陷；处置方式为 §1.5 裁决的接线 + `priority` | §3.1.5.5 推论表 |

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
| 归一性 | `Σ p = 1`（容差 1e-12）。**例外（ISSUE-011，2026-09-22 修复）**：当参与本次 `before_draw` 的算子含 scope **低于最高稀有度**的 `F` 型（hard）时，其语义为「全池置零 + 更高稀有度槽位还原原值」（§3.1.5.2），此时恒有 `Σp = 1 + p(被豁免的更高稀有度槽位) ≠ 1`（实测 `hard(scope='sr')` 输出 `{ssr:0.006, ssr_featured:0.003, sr:1.0, r:0.0}`，Σ = 1.009）。而 scope 取值只要在 `[rarities].ranks` 内即合法（config_toml 白名单只查这个），故 M1 槽位级管道下**对合法配置直接断言 `Σp = 1` 会抛假警报**。该断言须按 scope 感知重述：`Σp = 1 + Σp(被 F 豁免的高稀有度槽位)`；无 F 参与时退化为 `Σp = 1`。**适用范围（ISSUE-903，强制）**：上述 scope 感知口径是 **M1 槽位级管道**的性质（F 结果直接成为管道输出）。**自 S8 起** `_apply_delta`（§3.9.2）无条件归一化——`return {c: v / total ...}` 把任何一步增量应用后的分布一律缩到 `Σ = 1`；因转移族恒有 `Σδ = 0`，该归一化对族内算子**退化为恒等**（**位级订正，2026-10-14**：仅 A 与 Q 各为单卡时位级恒等；多卡组下归一化仍执行、把每卡缩放约 1 ULP，见 §3.9.5 第 6 行。**故 U 外的卡不是「不被缩放」而是「被缩放约 1 ULP」**），故 S8 起恒有 `Σp ≡ 1`（容差 1e-12）（§3.9.5 实测口径：S5 输出 Σ = 1.009、S8 输出 Σ = 1）。故 **S8 之后本不变式改为恒等断言 `Σp = 1`（容差 1e-12）**，`core/invariants.py` 的分布层判据必须按里程碑两段实现，否则对合法配置抛假警报。**落地状态（2026-10-14）**：该反转**已随 S8-1/2/3 的原子 commit 执行**（判据现为恒等 `Σp = 1`，三个 F 豁免符号已删），本行的「两段实现」不必再做 | <!-- REVIEW-FIX-PREV: ISSUE-011 --> <!-- REVIEW-R1-FIX: ISSUE-903 -->
| 非负性 | 所有卡的概率 ≥ 0 |
| 增量合法性 | `p + δ ≥ 0`；δ 在 p 的支撑上不全为 0 |
| 状态键合法 | Tracker 写入的键在其**自己声明的**键集内——声明集即三族统一的 `state_keys()`（**ISSUE-501**：Tracker / Modifier / Lifecycle 各暴露，`Pity.__init__` 汇总为 `self._declared_keys`，见 §3.1.1 的「声明键集」段与 §3.1.4 骨架）；`StateView` 只保证**读**侧，写侧须另查。**Modifier 的内联条件读键同属检查面**：条件内联后读键落在 Modifier 自己的 `state_keys()` 里（§3.14.2），故本不变式覆盖的「读键」不限于 Modifier 声明的**写**键（**GATE-check-6，2026-10-09 修正**：原写「`Condition` 类族经 `ConditionalModifier.state_keys()` 并入（ISSUE-902）」，该两类与那条纪律已随 §3.14 改判取消） | <!-- REVIEW-R1-FIX: ISSUE-501 --> <!-- REVIEW-R1-FIX: ISSUE-902 -->
| 确定性 | 同种子 + 同配置 → 逐位相同 |

**3.12.2 合法组合判据**

不是所有组合都有意义，需要定义「合法」并在构造期检查（与 `_validate_behaviors` 的四条规则同层）。**前两条判据的共同输入是三族的声明键集**（**ISSUE-501**：`state_keys()` → `Pity._declared_keys`，见 §3.1.1 / §3.1.2 / §3.1.3 的三张协议表与 §3.1.4 骨架；缺该成员则本节判据与 §3.13 的状态层检查**均无可用比对集**，S10-2 的构造期负例验收不可实现）<!-- REVIEW-R1-FIX: ISSUE-501 -->：

- 同一键被两个 Tracker 声明的冲突（如两个 `CounterTracker` 都写 `counter`）——判据输入 = 各 Tracker 的 `state_keys()`（**ISSUE-501**），比对 `Pity._declared_keys['trackers']` 内的重复；检查点在 `Pity.__init__`（数据是 per-Pity 的，无需引擎上下文），抛 `ConfigError`
- Modifier 引用了不存在的状态键——「存在」的口径 = 该键在 **Tracker ∪ Lifecycle** 的 `state_keys()` 并集内（**ISSUE-501**）。**比对集 = `Pity._declared_keys['modifiers']`（各 Modifier 自己的 `state_keys()` 声明集）**——§3.14 条件内联后读键一律落在 Modifier 自己的 `state_keys()` 里（**一处声明**，比原先「Modifier 与 Condition 两处并集」更简单，§3.14.2），故键名拼错仍能在此处被构造期拦下。**GATE-check-6（2026-10-09）**：原稿此处以 `ConditionalModifier.state_keys()` 转发条件读键（`FlagCondition` / `CounterCondition` / `FateReadyCondition`）并引 ISSUE-902，该两类与那条纪律均已随 §3.14 改判取消；本条现按「Modifier 自己的声明集」表述。<!-- REVIEW-R1-FIX: GATE-check-6-测试策略 -->**须含一条白名单**：`selected_card` 由策略层的 `NonDrawAction` 写入（[gacha_service.py:292](gacha_simulator/service/gacha_service.py#L292)、[gacha_service.py:294](gacha_simulator/service/gacha_service.py#L294)）、**无任何零件声明它**，而 `FateTracker` 会读它（§3.1.1 的 L4 例外 2）——不留白名单则合法配置被误判为「引用不存在的键」，`targeted` 族全部构造失败
- Lifecycle 依赖图成环（**现状：无成环检测**；`_build_activation_graph`（[pity.py:1203-1227](gacha_simulator/core/pity.py#L1203-L1227)）只建图 + 校验 `depends_on` 指向存在的名字，**不做环检测**）<!-- REVIEW-R1-FIX: ISSUE-002 -->
<!-- REVIEW-FIX-PREV: ISSUE-019 -->
<!-- REVIEW-FIX-PREV: ISSUE-001 -->
<!-- REVIEW-FIX-PREV: ISSUE-015 -->
- **池交集校验当前不可用（ISSUE-019，2026-09-22 修复）**：原稿称「现有 `_build_activation_graph` 已部分覆盖」，实测其第二段校验**恒为假阳性**——它用 `getattr(bh, '_pools', ())` 取双方池集合，而全库没有任何 behavior 设置 `_pools`（grep 只命中 [pity.py:1222-1223](gacha_simulator/core/pity.py#L1222-L1223) 这两行读取点（**1224-1225** 消费其派生集合；**ISSUE-946** 实测更正原引 `:1224-1225` 与「1226-1227 消费」，读写被整体错位 2 行））。故 `src_pools` / `dst_pools` 恒为空集，`'*' not in ()` 为真、交集为空为真，`warnings.warn` 对**每一条** `depends_on` 配置无条件触发。处置（**已定稿，2026-09-22 第八轮**）：由 **S3-1** 给 `Pity.__init__` 设 `self._pools = pools`（由 `PityDef.pools` 注入，§3.1.4 骨架已含 `pools` 形参）使该警告恢复语义。**原稿写「S1/S3」二选一，现写死为 S3-1**：`Pity` 类要到 S3 才新建，S1a 阶段无处可补（该任务项已自 S1a 移出，见 §七 S1a / S3-1）。**「删除这段恒真分支」的备选已否决**：该警告对 `depends_on` 跨池错配的运维价值高于其误报成本，删除等于放弃唯一一处跨池一致性检查。**已知过渡态**：S1a 至 S2a-2 期间（`Pity` 尚未落地）该警告仍对每条 `depends_on` 恒真触发，属预期行为、不是回归；S3-1 落地后恢复语义，§六 有对应断言。<!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order -->
- **标志分派前提（ISSUE-001）**：本节的构造期检查与 `_validate_behaviors`（[pity.py:931-982](gacha_simulator/core/pity.py#L931-L982)）同层，后者依赖 `is_soft` / `is_hard` / `is_event_driven` 三个由 `btype` 推导的标志（§3.2 首段）。若将来重构该分派，须与本节判据合并设计，不得单独改动其一<!-- REVIEW-R1-FIX: ISSUE-001 -->

**3.12.3 与等价性验收的分工**

| | 验证什么 | 方法 |
|---|---|---|
| 等价性（§六 主线） | 旧能力未退化 | 与旧类逐场对比 |
| 组合正确性（本节） | 新能力可用且自洽 | 性质测试 + 合法组合判据 |

两者互补：等价性是「守」，组合正确性是「攻」。

---

### 3.13 不变式运行时校验（2026-09-21 新增）

> **问题**：架构里有一批**隐式不变式**（分布归一、组内比例关系、增量非负、Tracker 只读自己的键、计数相位），**破坏了不会报错**。§五 风险表自己承认：「两者共同点是均不报错、只让结果静默偏移」。
>
> 「静默失效」在本系统反复出现：scope 写错、`reset` 取值非法、`targeted` 缺 `selected_card`、CR 短路条件写错——每一次都靠人肉排查。

**设计**：加一层**可开关**的校验（调试模式或测试模式下启用，生产关闭），在每次 `before_draw` / `after_draw` 后断言关键性质，破坏时立即抛出并指明位置（保底名 + 键 + 期望/实际）。**校验开关的载体（ISSUE-945，强制，2026-10-09 定稿）**：开关是 **`InvariantChecker` 的构造形参 `enabled: bool`**（存为实例字段），**不是模块级全局开关**。理由是并行路径：`run_batch_parallel` 用 `MPPool(initializer=_wk_init, initargs=(env, target_specs))` 把**整个 `env` 序列化**给每个 worker（[batch_simulator.py:873-876](gacha_simulator/service/batch_simulator.py#L873-L876)），checker 实例随 `env.pity_engine` 进入每一条 pickle 路径，故 Windows spawn 出的 worker **自动继承**该设置；若落在模块级全局（或读 `os.environ` 的全局标志），父进程的设置**不会传给 worker**，校验只在主进程生效、并行路径**静默失去校验能力**：这正是本仓库已被咬过一次的缺陷型（commit `38962ab`，2026-09-30：「父进程函数体内注册的插件策略在 spawn 子进程不存在」），教训写在 `_wk_init` 内。故：① `enabled` **随实例进 pickle**（§七 **S11** 的 round-trip 覆盖已含 `InvariantChecker`——该用例落在 S11 的专属文件 `tests/core/test_pity_invariant_checker.py`；**GATE-check-3，2026-10-09 修正**：原写 S7b，而 S7b 排在本步之前）；② **禁止**任何模块级全局开关作为「生产关闭」的载体。**状态层的比对集来源（ISSUE-501）**：三族声明的键集由 `Pity.__init__` 汇总为 `self._declared_keys`（§3.1.4 骨架），checker 从 `Pity` 实例取；`state_keys()` 是三族统一暴露的只读成员（§3.1.1 / §3.1.2 / §3.1.3），checker **不得**自行遍历 `trackers` / `modifiers` 推断，否则三处（§3.12.1 / §3.12.2 / §3.13）会各有一套口径。<!-- REVIEW-R1-FIX: ISSUE-501 --><!-- REVIEW-R1-FIX: ISSUE-003 -->

```python
class InvariantChecker:
    """可开关的不变式校验——仅在 debug/test 模式启用。"""
    def __init__(self, enabled: bool = False): ...   # 开关载体 = 构造形参，随实例进 pickle（ISSUE-945）
    # ── 调用点固定为 PityEngine 两个调度入口各一行（ISSUE-003），见下段「调用点与构造源」──
    def check_after_before_draw(self, pool_id, dist, engine): ...
    def check_after_after_draw(self, pool_id, state, engine): ...
    # ── 增量层不复用上面两个入口（dist 取不到该步的 δ），S8 起专用第三个入口 ──
    def check_delta(self, pool_id, dist, delta): ...
```

**校验项**（初版）：

| 层 | 项 |
|----|-----|
| 分布 | `Σp = 1 + Σp(被 F 豁免的高稀有度槽位)`；所有 `p ≥ 0`。**ISSUE-011（2026-09-22 修复）**：原稿写死 `Σp = 1`，但 scope 低于最高稀有度的 `F` 型（hard）语义上就保留更高稀有度槽位原值（实测 `hard(scope='sr')` Σ = 1.009），且该 scope 合法。若保持原样，checker 一旦启用即对**合法配置**抛假警报，而 M1 的交付定义又要求 S11 到位。**S8 之后同一份判据反向失配（ISSUE-903）**：`_apply_delta`（§3.9.2）无条件归一化，且因转移族 `Σδ = 0` 而退化为恒等，S8 起任何一步增量应用后 `Σp ≡ 1`，scope 感知式 `1 + 0.0089 ≈ 1.0089 ≠ 1` 会对**合法配置**再抛一次假警报（M1 与本式相符、M2 与之相悖，两个里程碑的期望值相反）。checker 须按「管道形态」二选一取式：M1 用 scope 感知式，**S8 起改用 `Σp = 1`**。**落地状态（2026-10-14）**：S8 起的恒等式**已随 S8-1/2/3 落地**（`Σδ = 0` 的位级例外见 §3.9.5 第 6 行的订正，容差 1e-12 足以覆盖） | <!-- REVIEW-FIX-PREV: ISSUE-011 --> <!-- REVIEW-R1-FIX: ISSUE-903 -->
| 状态 | Tracker 写入的键在其 `state_keys()` 声明集内（**ISSUE-501**：声明集由 `Pity` 汇总为 `self._declared_keys`，checker 从 `Pity` 取、不自行推断，与 §3.12.1 / §3.12.2 同一数据源）；`_declared_keys['modifiers']` 由各 Modifier 自己的 `state_keys()` 提供（三族统一协议，§3.1.2；内联条件的读键同在这一处声明里），故 checker 的状态层对「Modifier 内部的判断把 `'counter'` 拼成 `'countr'`」这类静默失效同样有效（**GATE-check-6，2026-10-09 修正**：原写「条件读的键由 `ConditionalModifier.state_keys()` 提供（ISSUE-902）」，该两类与那条纪律已随 §3.14 改判取消）；计数型计数器的值单调（除重置外） | <!-- REVIEW-R1-FIX: ISSUE-501 --> <!-- REVIEW-R1-FIX: ISSUE-902 -->
| 增量 | `p + δ ≥ 0`；在 p 的支撑上不全为 0。**该层只对 S8 起成立（ISSUE-003）**：M1 槽位级管道没有增量表示，仅凭 `dist` 取不到该步的 δ，故不复用两个入口，改由 `check_delta(pool_id, dist, delta)` 承担，~~调用点在 `_apply_delta()`（§3.9.2）内部~~——那里 p 与 δ 同时在手；该入口随 **S8-6** 落地（**落点订正，S8-6 审查 2026-10-14**：`_apply_delta` 已迁**叶子层** `pity_primitives.py`、签名收为 `(dist, d)`，**取不到 engine 与 `pool_id`**，故实际落点是 **`Pity.before_draw` 的内循环**（`d is not None` 分支内、`_apply_delta` 之前），校验器经 `PityContext.invariants` 进骨架、**只由 `PityEngine.before_draw` 写**）；M1 不启用本层 | <!-- REVIEW-R1-FIX: ISSUE-003 --> |
| 生命周期 | `_active` 只由**构造期 `Lifecycle.initialize` 的初始写入**、引擎的激活传播与本保底的退役动作写入（**ISSUE-202**：构造期写入若不列入白名单，该不变式会对**每条**非 `depends_on` 保底在构造期写 `_active=True` 报假警报） | <!-- REVIEW-FIX-PREV: ISSUE-202 -->

**调用点与构造源（ISSUE-003，强制，2026-10-09 补）**——原稿只给了类名与两个入口的签名，**没写谁构造它、谁调用它、`enabled=True` 从哪来**，且两个入口的实参取不到「增量」层的判据对象：

- **挂载层 = `PityEngine` 的一个字段**（不是模块级全局、不是 `Pity`、不是 `env` 的新字段）：`PityEngine.__init__(..., invariants: Optional[InvariantChecker] = None)` → `self._invariants`。挂这一层的理由是它随 `env.pity_engine` 进每条并行路径的 pickle 图（§四 `core/invariants.py` 行），spawn worker 自动继承该设置（ISSUE-945）。
- **调用点 = `PityEngine.before_draw` / `after_draw` 各一行**，位置固定为「该池的全部保底跑完、返回值之前」：

  ```python
  if self._invariants is not None:
      self._invariants.check_after_before_draw(pool_id, dist, self)
  ```

  故 **`core/pity.py` 是 S11 的目标文件之一**——原稿的目标面只写 `core/invariants.py`（新建）与 `tests/core/test_pity_invariant_checker.py`，两处调用点无处落地（§四 `core/pity.py` 行同批登记）。
- **`enabled=True` 的产出源 = 测试夹具**：S11 专属测试与 §六 的等价性 harness 直接构造 `InvariantChecker(enabled=True)` 并注入 `PityEngine`。**本期不加 env 字段、不加 CLI 开关、不加 TOML 配置项**（不引入新的用户配置面）；生产路径传 `invariants=None`，**连实例都不建**，零开销。
- **增量层的入口与调用点（S8 起，见上表「增量」行）**：M2 管道不再以分布形式传递中间量，两个入口的第二实参只有分布，取不到该步的 δ；故增量层改用第三个入口 `check_delta(pool_id, dist, delta)`，~~调用点在 `_apply_delta()` 内部（§3.9.2）~~，随 **S8-6** 落地（**落点见上表「增量」行的订正**：实际在 `Pity.before_draw` 的内循环，校验器经 `PityContext.invariants` 进骨架、只由 `PityEngine.before_draw` 写；`get_probabilities` **不写**，保持「只读查询不在四层判据面内」的已登记边界）。<!-- P64-S8-CLOSURE -->
      **实参面须先重写（S8 收口，2026-10-14）**：`_apply_delta` 现已迁至**叶子层** `pity_primitives.py`、签名收为 `(dist, d)`，**取不到 engine 与 `pool_id`**，故「调用点在 `_apply_delta()` 内部」照抄写不出。三条候选：① 把调用点移到骨架内循环（`pity.py`）并就地透传 `pool_id` 与 engine；② 把 checker 作为形参传入 `_apply_delta`（会使叶子层依赖调用方顺序，须评估）；③ 在骨架内循环里包一层。**取哪条由 S8-6 裁决并登记。**<!-- REVIEW-R1-FIX: ISSUE-003 -->

**与性能的关系**：校验只在开关打开时运行，且检查项为 O(卡数)，对生产路径无影响。§五 风险表的相关条目可据此更新缓解手段。

---

### 3.14 条件外置的取消（2026-10-06 改判）

> **本节结论已反转。** 原方案（2026-09-21）把触发条件从各 Modifier 内部提出来，成为独立的 Condition 类族 + `ConditionalModifier` 包装器。**2026-10-06 用户裁决取消该抽象，条件回到各机制的 `compute_delta()` 内部。**
>
> **小节编号说明（2026-10-08 补，同日晚二次补全）**：本节改判时删去了原 §3.14.4 / §3.14.5 / §3.14.6，以及 §3.14.3 下的两个子节（它们描述的「方案 C：6 个类合并为 `TransferModifier`」与条件表、修订范围表随该抽象一并作废），故 §3.14 现只剩 3.14.1 至 3.14.3 且无子节。文中若见「§3.14.5」「§3.14.6」「§3.14.3.1」「§3.14.3.2」的引用，指向的都是那些已删小节；凡未加历史标注的引用，均已于 2026-10-08 改为指向本节现存内容。

#### 3.14.1 改判理由

**① 条件与效果在游戏规则里是绑死的，抽出来不产生新组合。**

| 机制 | 条件 |
|------|------|
| hard / G3 | counter ≥ τ |
| soft | boost > 0 |
| rotating | flag guaranteed |
| targeted | flag guaranteed **或** fate_points ≥ τ |
| G1 | flag forced_loss |

「大小保底」这条规则本身就是「歪过 → 出金必是 UP」。把条件抽成对象，**不会凭空多出任何手册需要的组合**。唯一一处条件确实独立变化的是 **G14**（战双：counter ≥ **随机**阈值，效果与 hard 相同），而 G14 至今未实现。

**② 抽出来的代价是四条纪律。**

`ConditionalModifier` 必须转发 `apply` / `rebind` / `factor` / `state_keys` 四个方法，**漏一个就整条保底链不可用**（骨架对 `modifiers` 列表逐项无守卫调用）。计划为这一点写了 ISSUE-401、ISSUE-029、ISSUE-902、ISSUE-GATE-3-dependency-order 四条纪律。

**③ 组合爆炸的方向相反。**

一旦条件是独立对象，`ConditionalModifier(任意效果, 任意条件)` 就成了合法写法，于是要回答「soft 效果 × guaranteed 条件」是什么意思，即**语义爆炸**。现状靠「preset 里手写配对」把语义钉死，等于用纪律去补抽象的洞。**条件内联反而封死了这个洞**：不存在的组合无法表达。

#### 3.14.2 取消后的形态

条件写在各类 `compute_delta()` 的开头（M1 期为 `apply()`，S8 起为 `compute_delta()`，见 §3.1.2 与 §3.9.2 的方法名定稿），不生效即 `return None`：

```python
class RotatingModifier(Modifier):
    def compute_delta(self, view, dist, ctx):
        if not view.get('guaranteed'):          # ← 条件内联
            return None
        ...
```

**随之删除的符号**：`ConditionalModifier`、`Condition` 类族（`Always` / `Flag` / `Counter` / `FateReady` / `Ratio` / `Owned` / `RandomThreshold`）、组合子（`And` / `Or` / `Not`）、`core/pity_condition.py` 整个模块。

**随之删除的纪律**：ISSUE-401（`apply` / `factor` 条件判定须一致）、ISSUE-902（`Condition.state_keys()` 转发）、ISSUE-029 中 `ConditionalModifier` 的转发义务、ISSUE-GATE-3-dependency-order 中包装器的部分。

**保留的**：`state_keys()` 协议本身（§3.1.1 / §3.1.2 / §3.1.3 三族统一暴露）：条件内联后，条件读的键自然落在 Modifier 自己的 `state_keys()` 里，**一处声明**，比原先「Modifier 与 Condition 两处并集」更简单。

<!-- P64-S8-CLOSURE -->
> **六场景数据的来源登记（S8-6 审查，2026-10-14）**：本节的 `§3.14.3.1` / `§3.14.3.2` 是**已删小节**，正文只剩指向它们的引用，故 §七 S8-6 的 ⑥ 所需的**六场景池与场景定义已不在本计划正文**。来源提交为 **`d813393`**（其 `§3.14.3.1` 含池 `f1 0.004 / f2 0.002 / s1 0.005 / sr1 0.05 / r1 0.939` 与六场景表，并写明旧侧到卡级的还原口径是 `banner.py` 的 `scale_factors` 整槽同乘）。该数据现由 `tests/core/test_pity_equivalence.py` 的常量（`S8_SIX_CARDS` 等）承载。

#### 3.14.3 `Modifier` 基类仍需提供的两个默认实现

`apply` 与 `rebind` 的承载处不随条件外置取消而消失：

- **`rebind(state, name)`**：`Pity._rebind_state` 自 S1 起无条件调用（P75 纪律）。无状态零件 `pass`，有状态者覆写。**必须存在，不得省略。**
- **`apply`**：M1（S1–S7）骨架调用它、S8 起骨架改调 `compute_delta`。**基类默认实现分两期（本轮 AUDIT-BREAK-3 订正；原稿把 S8 期的式子写成唯一形态）**：**M1 期（S2a-1 起至 S7）只写占位实现 `def apply(self, ctx, view, dist, readonly): raise NotImplementedError`**——各具体 Modifier 一律自实现 `apply(ctx, view, dist, readonly) -> 分布`，占位实现**无消费者、故无可执行语义**，照抄 S8 期的式子即 `NameError`（`_apply_delta` 归 S8-1、`compute_delta` 是 S8 起的方法名）；**S8-1 起**把这一处换成正式默认实现 `_apply_delta(dist, self.compute_delta(...) or {})`，此后内层零件只写 `compute_delta`。**这是「`apply` 保留为默认实现」的承载处**，删掉它则 S8 之后每个抽卡入口 `AttributeError`。

<!-- REVIEW-R1-FIX: MODIFIER-IFACE -->
<!-- REVIEW-R1-FIX: COND-INLINE -->

## 四、波及范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/pity_primitives.py` | **新增**（**S1a** + **S8** + **S9**） | **叶子原语层**（§3.1.6）：`Counter` / `Flag` / `PityState` / `DrawInfo` / `PityContext` / `LifecycleConfig`（自 `pity.py` 迁出）+ **类型集合常量 `_SOFT_TYPES` / `_HARD_TYPES` / `_EVENT_DRIVEN_TYPES`**（自 `CounterBasedBehavior` 的**类属性**升为**模块级常量**，[pity.py:114-115](gacha_simulator/core/pity.py#L114-L115)（`_SOFT_TYPES` / `_HARD_TYPES` 在 :112 / :113）；§3.1.4 骨架的 `Pity(PityBehavior)` 不继承该基类，裸名引用即 `NameError`，故三者必须随叶子层落在此文件）+ **助手函数 `transfer_linear`**（S8 起；**2026-10-06**：原两式合并为它，由七个机制共用；**2026-10-08**：由因子版改为增量版、加 `shape` 形参；**不得下沉到 `pity_modifier.py`**，§3.9.4）。**S9（ISSUE-034）**：`PityContext` 加 `external` 字段——`PityContext`（[pity.py:31](gacha_simulator/core/pity.py#L31)）已迁至本文件，该字段的定义与编辑点**在此行**，不在 `core/pity.py`。`pity.py` 保留 re-export，既有导入路径不变。**ISSUE-301**：`LifecycleConfig` **保留**（不是删除项），角色由「`PityBehavior` 的 `lifecycle` 形参类型」改为「Lifecycle 对象的构造参数袋」，由四个 Lifecycle 实现的基类持有（§3.1.3） | <!-- REVIEW-FIX-PREV: ISSUE-002 --> <!-- REVIEW-FIX-PREV: ISSUE-301 --> <!-- REVIEW-FIX-PREV: ISSUE-024 --> <!-- REVIEW-FIX-PREV: ISSUE-034 -->
| `core/pity_tracker.py` | **新增**（**S1b** + **S1c** + **S1d**，逐块独立 commit） | Tracker 家族（CounterTracker/FlagTracker/StreakTracker/FateTracker + **`NamespaceTracker`**——**ISSUE-407** 新增，语义为空、只声明命名空间，供三个 `_soft` 类型的 preset 产出 `X_soft`）+ Lifecycle（四类：`AlwaysActive` / `FiniteActive` / `DependentActive` / `DependentFiniteActive`——**两个正交维度的四个组合**，2026-09-28 修正，~140 行）。**ISSUE-202**：Lifecycle 的协议为**五方法**——`initialize` / `is_active` / `should_deactivate` / `deactivate` / `rebind`；`initialize(state, name, namespaces=())` 承担 `_active` 的构造期写入（`Always` 维对 `name` 与 `namespaces` 中每个命名空间各写 `_active=True`，`Dependent` 维空实现），由 `Pity.__init__` 在创建 `_view` 前调用（§3.1.3 专段 / §3.1.4 骨架）。<!-- REVIEW-R1-FIX: ISSUE-407 --> **ISSUE-407**：三族（Tracker / Modifier / Lifecycle）统一暴露 **`namespace` 属性**（默认 `None`，§3.1.1「零件的命名空间声明面」），`Pity` 据此经 `self._ns_views` 传对应 view；`should_deactivate` 为**四实参**（第四实参 `fired`，ISSUE-402）。<!-- REVIEW-R1-FIX: ISSUE-501 --> **ISSUE-501**：本文件的 Tracker 族与 Lifecycle 族**一律实现 `state_keys() -> tuple[str, ...]`**（只读、由构造形参决定、不依赖 state；Tracker 返回其写的键，Lifecycle 仅在 `max_triggers > 0` 时返回 `('triggers',)`），它是 §3.12.1 / §3.12.2 / §3.13 与 S10-2 构造期判据的唯一输入（`Pity.__init__` 汇总为 `_declared_keys`，§3.1.4 骨架）。**ISSUE-301**：Lifecycle 以 `LifecycleConfig` 为构造参数袋（共用基类持 `self._cfg`）——**`deactivate_on_early_hit` 与 `depends_on` 两个属性都由基类对 `cfg` 统一代理**（**ISSUE-406**：`PityEngine._build_activation_graph` 对**每条** behavior 无条件读 `lc.depends_on`（[pity.py:1214-1215](gacha_simulator/core/pity.py#L1214-L1215)），只代理前者会让<!-- REVIEW-R1-FIX: GATE-2-文件清单 --> `AlwaysActive` / `FiniteActive` 在每次 `PityEngine(...)` 构造时 `AttributeError`；原稿「`depends_on` 由 `Dependent` 维同源读出」已废止） | <!-- REVIEW-FIX-PREV: ISSUE-202 --> <!-- REVIEW-FIX-PREV: ISSUE-301 --> |
| ~~`core/pity_condition.py`~~ | **不新增**（**2026-10-06 随 §3.14 改判删除**） | 原 Condition 类族与 `ConditionalModifier` 包装器均已取消，条件内联进各机制的 `compute_delta()`。原行内容如下（存档）：Condition 类族（7 个内置 + 3 个组合子），纯读无副作用；**每个 Condition 一律实现 `state_keys() -> tuple[str, ...]`**（**ISSUE-902**：`Always` 返回 `()`、`FlagCondition(flag)` 返回 `(flag,)`、`CounterCondition(key, τ)` 返回 `(key,)`、`FateReadyCondition(τ)` 返回 `('fate_points',)`、`And`/`Or`/`Not` 取子条件并集；它是 §3.12.2 判据第 2 条与 §3.13 checker 覆盖**条件读键**的唯一输入，缺它则条件键名拼错时四道防线全部静默通过）；配套 `ConditionalModifier` 包装器（~80 行，其 `state_keys()` 返回**内层 Modifier 与条件**的并集，§3.14.2）。**为何必须在 M1**：S4 的 preset 工厂（§3.2 / §3.3 / §3.14.2）与 S5 的等价性测试一律消费 `ConditionalModifier` / `FlagCondition` / `CounterCondition` / `Always`，本模块留在 M2 会让 M1 唯一可照抄的 preset 代码引用不存在的模块，S4/S5 无法闭合 | <!-- REVIEW-FIX-PREV: ISSUE-101 --> |
| `core/pity_modifier.py` | **新增**（**S2a-1 / S2a-2**） | Modifier 家族（**一机制一类，六个类、七个机制形态**，§3.1.2 机制表；裁决 1B 的「`TransferModifier` 单类 + 三参数」形态已随 2026-10-06 的简化作废，`ConditionalModifier` 包装器亦随 §3.14 改判取消）（~80 行，原估 150 行）。**S8**：实现形态切换为增量向量（§3.1.5.1）。**2026-10-09**：原「S2a + S2b 两块」改为本文件独占——S2b（目标解析器族）取消，A/Q 解析与 `_lower_rarities` 内联进本文件的各类方法体；同轮按 GATE-1 再细分为 S2a-1 / S2a-2（§七 S2a-1 / S2a-2）。<!-- REVIEW-R1-FIX: ISSUE-501 --> **ISSUE-501**：本文件的 `Modifier` 基类提供 `state_keys()` 的默认实现（返回 `()`），读状态的 Modifier 覆写它。条件内联后，条件读的键自然落在各 Modifier 自己的 `state_keys()` 里（§3.14.2）；原 `ConditionalModifier` 的「转发内层声明集」义务已随该类取消而消失<!-- REVIEW-R1-FIX: GATE-4-风险缓解 --> |
| `core/invariants.py` | **新增**（**S11**） | `InvariantChecker`（可开关的不变式运行时校验，§3.13）：`check_after_before_draw(pool_id, dist, engine)` / `check_after_after_draw(pool_id, state, engine)`，覆盖分布 / 状态 / 增量 / 生命周期四层；生产关闭。**2026-09-22 补登记（ISSUE-GATE-file-list）**：原稿只在 §3.13 给类名、§四 无任何落点行，实施者无从判断该新建模块还是并入 `core/pity.py`；现定稿为**独立新模块**（与 `Pity` 骨架解耦，便于生产关闭时零开销）。**S8 波及（ISSUE-903，强制）**：本模块的**分布层归一性判据是跨里程碑两段的**——M1 槽位级管道下取 scope 感知式 `Σp = 1 + Σp(被 F 豁免的更高稀有度槽位)`，**S8 起 `_apply_delta`（§3.9.2）无条件归一化，同一判据须改为恒等断言 `Σp = 1`**（容差 1e-12）。故 S8 的目标文件**含本行**：S8-6 必须同批 re-derive 该判据，否则 M2 一旦启用 checker 即对合法配置误报（§3.12.1 / §3.13 / §六 S10 三处同口径）。**开关载体（ISSUE-945，强制）**：`enabled: bool` **构造形参**，随实例进 pickle，**禁止模块级全局开关**（spawn worker 不继承，见 §3.13 的「校验开关的载体」段）。**调用点与构造源（ISSUE-003，强制，2026-10-09 补）**：本模块只提供类，**两个（S8 起三个）入口的调用点与 `PityEngine(invariants=…)` 形参在 `core/pity.py`**（`self._invariants`，随 `env.pity_engine` 进 pickle；`enabled=True` 由测试夹具产出），完整分工见 §3.13 的「调用点与构造源」段。 <!-- REVIEW-R1-FIX: ISSUE-945 --> <!-- REVIEW-R1-FIX: ISSUE-003 --> | <!-- REVIEW-FIX-PREV: ISSUE-GATE-file-list --> <!-- REVIEW-R1-FIX: ISSUE-903 -->
| `core/pool.py` | 修改（**S8**） | 删除 `aggregate_probs_by_rarity`（[pool.py:254](gacha_simulator/core/pool.py#L254)，唯一调用点在 banner）+ **`infer_rarity_from_spec`（[pool.py:234](gacha_simulator/core/pool.py#L234)，ISSUE-504：其 ①②③ 类消费者随本行与 S8-2 一并消失，函数零消费者）** + `core/__init__.py` 的两者导出行。<!-- REVIEW-R1-FIX: ISSUE-504 -->**ISSUE-026（2026-09-22 修正文件名）**：原稿把「`compute_scope_mappings` 改造为只产出卡集合」记在本行，但该函数**定义在** [pity.py:1038](gacha_simulator/core/pity.py#L1038)，`pool.py` 只有 `infer_rarity_from_spec` / `aggregate_probs_by_rarity`——本行不含该函数的改造，改造点见下方 `core/pity.py` 行 | <!-- REVIEW-FIX-PREV: ISSUE-026 --><!-- REVIEW-R1-FIX: ISSUE-001 --><!-- REVIEW-R1-FIX: ISSUE-002 -->
| `core/__init__.py` | 修改（**S8**） | **ISSUE-025**：删除 `aggregate_probs_by_rarity`（[core/\_\_init\_\_.py:3](gacha_simulator/core/__init__.py#L3)、`:101`）与 `_redistribute_scope`（`:20`、`:117`）的导出，**并删除 10 个旧行为类的 import 与 `__all__` 条目**（[core/\_\_init\_\_.py:9-20](gacha_simulator/core/__init__.py#L9-L20) / `:107-117`：`SoftStepBehavior` / `CounterBasedBehavior` / `HardPityBehavior` / `RotatingBehavior` / `RotatingSoftBehavior` / `RotatingCRBehavior` / `RotatingCRSoftBehavior` / `TargetedBehavior` / `TargetedSoftBehavior` / `SoftPityMixin`）。**保留**仍在的对外符号：`PityBehavior` / `PoolPitySpec` / `PityState` / `PityEngine` / `DrawInfo` / `PityContext` / `Counter` / `Flag` / `LifecycleConfig`（**ISSUE-301：保留，角色改为 Lifecycle 构造参数袋，不是退役项**） / `BEHAVIOR_REGISTRY` / `create_behavior` / `compute_scope_mappings`。**待定**：preset 化后是否新增对外符号（如 `Pity` / Tracker 家族 / `StateView`），实施时登记 | <!-- REVIEW-FIX-PREV: ISSUE-025 --> <!-- REVIEW-FIX-PREV: ISSUE-301 -->
| `core/milestone.py` | 修改（**S9**，2026-09-28 审查补） | `register_milestone_engine(..., initial_counts=...)` 的闭包捕获（[:163](gacha_simulator/core/milestone.py#L163)）~~简化为从 `GachaState` 取~~ **形参整个删除**（**订正（S9-2 审查，2026-10-14）**：`register_milestone_engine` 与 `_consume_bonus` 的 `initial_counts` 形参一并删除，改由 `state.add_card` 读 `self.initial_counts`；原写「简化」轻于实际）（`initial_counts` 升为 state 字段后，服务层不必再经形参传入）。**原稿 §四 全表无本文件** |
| `tests/test_p60_gacha_state.py` + `tests/test_p63_overflow_integration.py` | 修改（**S9**，2026-09-29 补） | 两条用例正断言 `add_card` 的 `ValueError` 守卫（[:40](tests/test_p60_gacha_state.py#L40)、[:78](tests/test_p63_overflow_integration.py#L78)），守卫删除后必失败，须同步改为断言「从 `state.initial_counts` 自动取」。**原计划未登记这两个文件**。**本步另须处理 9 处关键字实参（2026-10-01 补登记，源自本 run 阶段 4 代码审计的阻塞断裂 ③）**：实测两文件用例体内共 **9 处** `add_card(..., initial_counts=...)` 关键字实参（`test_p60_gacha_state.py` 的 :21/:27/:69，`test_p63_overflow_integration.py` 的 :36/:45/:46/:59/:61/:74），形参移除后**逐条 `TypeError`**。失败形态是「当场报错」而非静默，且两文件已在本行改造范围内，故**不新增子块**，但须写入 §七 S9-2 的改造范围，否则实施者按「只改两条守卫用例」施工会漏 |
| `core/state.py` | 修改（**S9**，2026-09-28 重梳） | ① 新增 `initial_counts: Dict[str, int]` 字段（本场模拟的初始持有）——原为 `GachaService.run_simulation` 的局部变量与四处传参；② `add_card` / `total_holding` 的 `initial_counts` 形参**移除**（内部改读 `self.initial_counts`）——**单一真相源**（2026-09-29 定稿，原写「改可选」会留两个来源）；连带**删除** `add_card` 的防御守卫<!-- P64-S9-2-LANDED -->
      **删守卫的后果登记（S9-2 审查，2026-10-14）**：原守卫是 **fail-fast**（「传了 `overflow_bands` 就必须传 `initial_counts`」）；删除后「漏设 `initial_counts`」从**抛错**变为**静默少算**（实测 `GachaState()` 空字段 + `bands` → 无异常、返回偏小的分档结果）。**生产侧无此路径**：全库仅两处 `add_card` 调用（`gacha_service` 与 `milestone`），两者的 `state` 都出自 `run_simulation` 的 clone，而 `gacha_service.py:333` 在 clone 之后**无条件赋值**。**但该赋值点此前无任何断言观察**（随包 `config.toml` 的 `initial_count` 全为 0，故 `p79_verify` / `p82_baseline` 亦盲），已由 S9-2 收口补一条端到端断言钉住。（[state.py:120-125](gacha_simulator/core/state.py#L120-L125) 的「传了 bands 未传 counts → ValueError」，其触发条件已不存在）；③ 新增 **`SimView`** 类（只读查询视图，暴露 `owns`；~~`balance`~~ 2026-10-06 删除，全库零使用；`now()` 已于 §3.10.2 删除，`time` 不在白名单）与 `GachaState.sim_view() -> SimView`（O(1) 包装）。**ISSUE-009：`owns()` 口径为「含初始持有」**——`state.initial_counts.get(c,0) + state.acquired.get(c,0)`，两者同为一个 state 的字段，口径一致由构造保证。**行为等价的三条判据（2026-09-28 查证）**：① **`clone()` 必须带该字段**（**独立验收项见 §六**）——`run_simulation` 首行即 `initial_state.clone()`，漏带则初始持有在克隆时丢失、P63 溢出分档静默出错；② **真实构造点唯一且每场新建**——[batch_simulator.py:508](gacha_simulator/service/batch_simulator.py#L508)（其上方注释已要求跨模拟隔离、每场新建 GachaState），与 `_initial_counts` 的「每场从 `card_defs` 现算」语义等价；③ **`add_card` 的 `initial_counts` 形参一并移除**（2026-09-29 定稿：**统一为单一真相源**）——原计划「形参改可选、缺省取 `self.initial_counts`」会留下**两个真相源**（服务层局部变量 vs state 字段），任一路径只更新其一即静默不一致（直构 `GachaState` 的测试路径上 `state.initial_counts` 恒空 → G3 的 `owns()` 少算初始持有 → 退化为「只算模拟内获得」，正是「精确建模原则」要消除的失效形态）。故两处调用点（[gacha_service.py:481](gacha_simulator/service/gacha_service.py#L481) 抽卡获得、[milestone.py:211](gacha_simulator/core/milestone.py#L211) 里程碑发卡）改为**不传该参**，`add_card` 内部直接读 `self.initial_counts`；**另一条闭包捕获路径**——[milestone.py:163](gacha_simulator/core/milestone.py#L163) 的 `register_milestone_engine(..., initial_counts=...)` 同理改为从 `GachaState` 取（[batch_simulator.py:473-487](gacha_simulator/service/batch_simulator.py#L473-L487) 的 `_ms_initial` 推导**整段删除**（[batch_simulator.py:477-482](gacha_simulator/service/batch_simulator.py#L477-L482) 的 `_ms_initial = {}` 与其后的 `for _cd in env.card_defs` 循环；块首 `if env.milestone_defs:` 在 :473）——**它不是 `GachaState` 初值的来源**：该块在 `if env.milestone_defs:` 内、无里程碑时不执行（ISSUE-914 指出的坑），故「推导上提到块外 → 构造点补传」这条路径**不采用**。全篇只有**一处推导源**（`run_simulation` 内的 `_initial_counts` 现算，[gacha_service.py:310-315](gacha_simulator/service/gacha_service.py#L310-L315)）与**一处赋值点**（该函数 `clone()` 之后，见 §四 `service/gacha_service.py` 行）。<!-- REVIEW-R1-FIX: ISSUE-916 --><!-- REVIEW-R1-FIX: ISSUE-003 -->
| `core/config_store.py` | 修改（**S9**） | ~~`PityDef` 新增 `reads: tuple[str, ...] = ()`~~（**2026-10-06 删除**，§3.10.2 改判）。**归属（ISSUE-GATE-dependency-order）**：字段定义 + 解析 + 透传链**整体归 S9（M2）**，S4b 不再触碰 `reads`（M1 内无任何消费者） | <!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order -->
| `core/config_store.py` | 修改（**S4-4**） | `PityDef` 新增 `max_triggers: int = 0`（0 = 不限）——`FiniteActive` 的配置接线（ISSUE-032，2026-09-27 裁决） |
| `core/config_toml.py` | 修改（**S4-4**） | `max_triggers` 解析（`_build_pity`）+ round-trip 写回（`_pitydef_to_toml`）+ 负值抛 `ConfigError` |
| `gui/config_panel.py` | 修改（**S7a**） | 新增「触发次数上限」数值控件（0 = 不限），`_apply_pity_edit` 与 load/save 路径同步该键。**ISSUE-911（2026-10-01，透传面补登记）**：本文件另有**五处**与三处引擎侧并列的**枚举式保底字段透传**——`set_config`（[:6541-6605](gacha_simulator/gui/config_panel.py#L6541-L6605)，**别名键** `type`/`start`/`end`/`increment`）、`_refresh_from_store_impl`（[:7443-7468](gacha_simulator/gui/config_panel.py#L7443-L7468)）、`_flush_pity_current_detail`（[:3244-3324](gacha_simulator/gui/config_panel.py#L3244-L3324)）、`get_config`（[:6336-6366](gacha_simulator/gui/config_panel.py#L6336-L6366)，别名键）、`apply_to_store`（[:7167-7196](gacha_simulator/gui/config_panel.py#L7167-L7196)）。五处均为**静默丢失**形态：TOML 里写好的 `priority`（S4b）/ ~~`reads`（S9-2，已取消）~~ / `max_triggers`（S4-4）只要经「GUI 打开 → 导出」一次即被抹掉，且无任何断言覆盖，详见 §3.6 AUDIT-BREAK-1 的 #4–#8 行。**~~`reads` 的 GUI 通路取保守路径~~**（2026-10-06 删除，字段取消）：原「不加控件，但五处须保留该键的原样透传」（§3.6 同行）。**ISSUE-918（2026-10-01）**：四个别名键的改名另有两处消费面须同批——同文件 `_do_update_preview` 的 `pdef.get('type', '?')`（[:6046](gacha_simulator/gui/config_panel.py#L6046)，改名后 GUI 预览逐条打印 `?`）与 [tests/gui/test_config_panel_pity.py:220](tests/gui/test_config_panel_pity.py#L220) 的正断言（落点 §七 S7a） | <!-- REVIEW-R1-FIX: ISSUE-911 --><!-- REVIEW-R1-FIX: ISSUE-918 -->
| `core/config_toml.py` | 修改（**S9**） | ~~`reads` 的解析 + 状态源白名单校验（未知名称抛 `ConfigError`）、round-trip 写回 |
| `core/pity.py` | 修改（**S3** + **S8** + **S9** + **S11**） | `StateView` 限定 Modifier 的状态视野（**ISSUE-034：`StateView` 的引入时点订正为 **S3-1**（`2200055`），定义见 §3.10.3，归属登记见 §3.1.6 编排层行**（**S9-1 审查订正，2026-10-14**：原写「S9 在本文件新增的符号」，与同行的「自 S3 起落薄版」及 §3.1.4 骨架注释自相矛盾））；**`PityContext.sim` 的编辑点不在此行**——`PityContext` 已迁至 `pity_primitives.py`，见上表该行（ISSUE-034；**2026-10-06**：字段由 `external` 改名 `sim`，§3.10.2）。**ISSUE-103**：`PityContext.state` 的字段注记**保持 `PityState`**（隔离只由 `view` 承担）；本行为 `TargetedBehavior` 三处 `ctx.state.get(self._name, "selected_card")` 的迁移点（改为 `view.get`）。<!-- REVIEW-R1-FIX: ISSUE-408 --> **`NotOwnedModifier` 的类本体归 `core/pity_modifier.py`**（§3.1.6 实现层 / §3.14.2 Modifier 类族 / §七 S9-3 目标文件），**本行只登记两条 registry 条目**（`hard_exclude_owned_skip` / `hard_exclude_owned_any`，§3.10.4 配套第 1 条）。**原稿写「本行新增 `ForceNotOwnedModifier` 零件」与本文件的分层定稿相悖**：按该写法会把这个 Modifier 类写进编排层 `core/pity.py`，与 §3.1.6「编排层只住 `Pity` 骨架 / `PityEngine` / registry / preset 工厂 / `create_behavior` / `StateView`」冲突，并与 §七 S9-3 的目标文件清单产生重复定义。**ISSUE-033 追加 / 归属修正（2026-09-22，ISSUE-GATE-dependency-order）**：`Pity` 增加 `reads` 形参归 **S3**（骨架构造形参，默认 `()`，与 `priority` / `pools` 同口径，**不消费任何字段**）；`PityDef.reads` 注入 + `PityEngine.get_reads_for_pool()` 访问器归 **S9**（定义见 §3.10.2）——原稿把两者整体标 S9，与 S3 任务行「`Pity` 增加 `reads` 形参」冲突。**`StateView` 落地时点**：自 **S3** 起在本文件落**薄版**（`get` 直取 `state.data.get(name, {})`，定义见 §3.10.3），S9 才把 `name` 之外的读取切断并接入 Modifier 的 `view` 形参（骨架 §3.1.4 的 `self._view = StateView(state, name)` 因此不是引用未定义符号）。**view 的按零件命名空间分配（§3.10.3 定稿）同在本文件落地（S3 默认 view + 零件 view 框架，S9 收紧）**。**ISSUE-026 追加（S8）**：`compute_scope_mappings`（[pity.py:1038](gacha_simulator/core/pity.py#L1038)）的改造**归属在本文件、不在 `core/pool.py`**——归属结论不变，但**时点已推迟（ISSUE-901 / ISSUE-904，2026-10-01 改判）**：该项是**减量**改造（不再生成槽位名），必须与槽位三字段同批，并入 GATE-5 末条「发布前一次性移除旧保底类」的同一 commit；**S8-4 不做**（卡集合本就是该函数五元组的既有前两项 `scope_cards` / `featured_cards`，且 `PityEngine` 三个调度入口早已透传进 `DrawInfo`，卡级路径无增量可做）<!-- REVIEW-R1-FIX: ISSUE-904 --> **S11（ISSUE-003，强制）**：`InvariantChecker` 的两个（S8 起三个）调用点与 `PityEngine(invariants=…)` 形参在本文件，类的定义归 `core/invariants.py`（§3.13 的「调用点与构造源」段） | <!-- REVIEW-FIX-PREV: ISSUE-026 --> <!-- REVIEW-FIX-PREV: ISSUE-034 --> <!-- REVIEW-FIX-PREV: ISSUE-033 --><!-- REVIEW-R1-FIX: ISSUE-002 --> <!-- REVIEW-R1-FIX: ISSUE-003 -->
| `core/banner.py` | 修改（**S8 + S9**） | **S8**：删除 `scale_factors` 聚合/还原段（[banner.py:229-246](gacha_simulator/core/banner.py#L229-L246)），概率管道改传卡级分布；`aggregate_probs_by_rarity` 的调用点随之移除。**2026-09-21 审查修正：原写 `service/banner.py` 路径不存在**。**S9（ISSUE-027，2026-09-28 重梳）**：**不新增形参**——`Banner.draw` 本就持有 `state`，通道 A 直接传 `pity_engine.before_draw(..., sim=state.sim_view())`（**S9 落地时该调用点在 [banner.py:228](gacha_simulator/core/banner.py#L228)**；实测现行调用为 `pity_engine.before_draw(qualified_key, pity_state, rarity_probs)`、尚无 `sim` 实参；**2026-10-10 订正**：原写 `external=state.external_view()` 与 `:195` 是改名前的旧口径与旧行号） | <!-- REVIEW-FIX-PREV: ISSUE-027 -->
| `core/pity.py` | **重构**（**S1d** `build_lifecycle` / **S3** 骨架 / **S4-1…S4-5** preset 与 registry / **S6a·S6b** 排序与 priority） | **S3 的目标文件即本行**（统一 Pity 骨架 + `Pity._rebind_state` + `StateView` 薄版）。统一 Pity 骨架 + 10 个类型改造为 registry preset + `_BTYPE_ORDER` 加 `rotating_inverse`（**取值 `3`**，与 `rotating` / `targeted` 同档）+ **`_EVENT_DRIVEN_TYPES` 追加 `rotating_inverse`**（ISSUE-105：只登记排序表而不登记类型集合，会让 `_validate_behaviors` 规则 3 的互斥校验**静默失效**——`is_soft` / `is_hard` / `is_event_driven` 三标志全 False 时 `elif` 链三条规则无一命中。**ISSUE-506 修正**：原稿同处并列的「与 `is_active` 早退双双静默失效」不成立——早退由 §3.1.4 骨架对全部类型无条件承担，该集合不参与早退判定，见 §3.3）<!-- REVIEW-R1-FIX: ISSUE-506 -->+ `_resolve_order` 加 `priority` 排序（G5）。**G16 独立先行（不混入本行重构，§3.8）**：`_should_reset` 加 `never` 分支。**P82 接线独立先行（§1.5 裁决 1）**：`PityEngine` 独立排序视图 + `get_behaviors_for_pool()` 改消费它。**ISSUE-204（强制，2026-09-22 补登记）**：`PityEngine.__init__` 的 `try / except Exception` + `logger.warning` 构造兜底（[pity.py:1164-1172](gacha_simulator/core/pity.py#L1164-L1172)；**ISSUE-GATE-FAIL-2 行号修正（2026-09-22）**：原写 `:1166-1172`，实测 `try:` 起于 `:1164`、`except Exception:` 在 `:1167`、`logger.warning` 在 `:1168-1172`，原范围漏掉 `try:` 与 `create_behavior` 调用行）须**同步改掉**——改为抛 `ConfigError`（preset 构造失败属配置错误，与 `_validate_behaviors` 的校验失败同层），使 `_resolve_order` / `_validate_behaviors` 在**完整**列表上执行。<!-- REVIEW-R1-FIX: ISSUE-405 -->导入期的 `_validate_registry()` **只做 `preset` 的可调用性判定（`callable` / `inspect`），既不调用 preset、也不校验返回键集**——该函数形参表为空（[pity.py:815-832](gacha_simulator/core/pity.py#L815-L832)），手上没有 `PityDef` 实例可传；且导入期真调用会把 preset 体内的错误升级为**整包导入失败**（ISSUE-405 定稿，§3.2 首段）；**返回 dict 的键集校验（缺 `lifecycle` 查漏 + 未知键查多）在运行期由 `create_behavior` 承担**（§3.2），故 preset 体内的失败（三个类型集合常量未随叶子层落地致 `NameError`、Modifier 构造签名与 §3.14.2 定稿形态不符致 `TypeError`、缺 `rebind`）在导入期不报错、只在此处被吞成一条日志。若确要保留跳过语义，则须至少补 §六 的「10 个 preset 全部构造成功」断言并把告警升级为加载期可见（写入 `load_warnings`）。**ISSUE-301（强制）**：新增模块级 helper `build_lifecycle(pdef)`（`pdef.depends_on` 非空 → `DependentActive`，否则 `AlwaysActive`，`deactivate_on_early_hit` 一并带入 `LifecycleConfig`），10 个 preset 工厂的返回 dict **一律含 `lifecycle=` 键**；**ISSUE-503（强制）**：另新增模块级 helper `_norm_scope(pdef, default='ssr')`（scope 的唯一归一化点，`create_behavior` 与 10 个 preset 工厂共用；`create_behavior` 的 `scope = (getattr(pdef,'scope',None) or _default_scope).lower()`（[pity.py:854](gacha_simulator/core/pity.py#L854)）随之改写为本 helper 调用），**preset 示例中一律不得出现裸 `pdef.scope`**；`create_behavior` 在 `preset(pdef)` 之后校验该键存在、缺失抛 `ConfigError`（**旧 `lifecycle_kwargs` 段（:893-900）随之删除**，不得两处并存）。**不做的后果**：全部 `deactivate_on_early_hit` / `depends_on` 配置静默失效且无对照实现可发现（§3.1.3） | <!-- REVIEW-FIX-PREV: ISSUE-204 --> <!-- REVIEW-FIX-PREV: ISSUE-301 --><!-- REVIEW-R1-FIX: ISSUE-002 -->
| `core/config_toml.py` | 修改（**G16-1 / S6a / S6c**） | **`_build_pity` 对 `reset` 增取值白名单（空串 / `featured` / 稀有度名（`[rarities].ranks` 的键）/ `never`，未知值抛 `ConfigError`）**（G16 独立先行；**ISSUE-928**：原写「reset 枚举 `never`」在配置层无对应物——实测 `_build_pity` 只做 `name` 非空/查重（[:636-641](gacha_simulator/core/config_toml.py#L636-L641)）与 `scope` 白名单（[:642-646](gacha_simulator/core/config_toml.py#L642-L646)）两道硬拒，`reset` 是 `p.get('reset', '')` 直取（[:718](gacha_simulator/core/config_toml.py#L718)），按字面无对象可改）+ **移除事件驱动型 deactivate_on_early_hit 拒绝分支（H3，S6a）**（S6c）。**ISSUE-912（2026-10-01，波及面补登记）**：该分支（[config_toml.py:686-691](gacha_simulator/core/config_toml.py#L686-L691)<!-- REVIEW-R1-FIX: ISSUE-929 -->）被**两条既有用例正断言**——[test_pity_config_toml.py:249](tests/core/test_pity_config_toml.py#L249) / [:263](tests/core/test_pity_config_toml.py#L263) 的 `pytest.raises(ConfigError, match='deactivate_on_early_hit')`，删除分支即两处必红；GUI 侧配套的 `_on_pity_type_changed` 的 `setEnabled(is_counter)` 与 [test_config_panel_p56.py:116](tests/gui/test_config_panel_p56.py#L116)「仅 hard 启用」断言同批。**S7c 的验收是 `pytest -q` 全量通过、H9 会拦推**，故这三处断言必须与 S6a 同一 commit 改写（GUI 侧控件自 H3 起对事件驱动型也应可勾选）。原计划的存量测试清单（S7d / S8-7）**均未含这两个文件**，本轮补登记~~原写「`rotating_inverse` 校验放行（S6a）」~~ **该步骤已于 2026-09-30 删除：`_build_pity` 无类型白名单（实测两个未知 type 直接通过、不抛错），无对应物可放行**，详见 §3.10.4 配套第 2 条 | <!-- REVIEW-R1-FIX: ISSUE-001 --><!-- REVIEW-R1-FIX: ISSUE-005 -->
| `core/config_store.py` | 修改（**S4b**，字段定义） | PityDef 新增 `priority` 字段（G5）。**字段定义与 `config_toml` 解析随 S4b 落地**（2026-09-22 第八轮前移：原归 S6b，但 S4-2 的 `Pity(..., priority=pdef.priority)` 与 S4b 的三处透传都排在 S6b 之前，而实测 `PityDef`（[config_store.py:150-186](gacha_simulator/core/config_store.py#L150-L186)）当前确无该字段，照原序施工即 `AttributeError`，改用 `getattr` 兜底则退化为恒 0 的静默空转）；S6b 只留 `_resolve_order` 排序键与 GUI 控件。新序：**S4-1 → S4b → S4-2** | <!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order -->
| `core/config_toml.py` | 修改（**S4b**） | `priority` 解析（`_build_pity`）+ **round-trip 写回（`_pitydef_to_toml`，非默认才写）**（**ISSUE-923**：§四 原表**无本行**——只有 `core/config_store.py` 行提「字段定义与 `config_toml` 解析随 S4b 落地」，写回面零落点；`_pitydef_to_toml` 是条件式逐字段书写，不会自动带上新字段，漏写回即 GUI「加载 → 保存」抹掉手写值） | <!-- REVIEW-R1-FIX: ISSUE-923 -->
| `gui/config_panel.py` | 修改（**G16-1 / S6a / S6b / S9-3**；**S7a** 验收） | **新建 reset 控件**并加「永不重置」（G16 独立先行，现无该控件）；`_PITY_TYPES` **改为由 `BEHAVIOR_REGISTRY` 生成**（**待改造，施工落在 S6a**，见 §3.6；2026-10-01 实测仍为硬编码 10 项字面量）——改造落地后新增 type（`rotating_inverse` / `hard_exclude_owned_skip` / `hard_exclude_owned_any`）**自动出现在下拉**，不再需要手工追加；**改造落地前仍须手工追加 `_PITY_TYPES`**<!-- REVIEW-R1-FIX: ISSUE-929 -->；priority 编辑控件（S6b）；S7a 做 round-trip 验收。**AUDIT-BREAK-1（2026-10-01）**：本文件的 GUI 兜底保底条目（[:6544-6547](gacha_simulator/gui/config_panel.py#L6544-L6547)，`type='soft'` / `reset='any_ssr'` / 嵌套 `params`）须在 **G16-1 的同一 commit** 内改为合法形态，否则白名单落地即「打开配置即抛 `ConfigError`」，见 §3.8 AUDIT-BREAK-1 段 |
| `gui/about_dialog.py` | 修改（**S9-3**，2026-09-30 新增；**原稿 §四 全表无本文件**） | 「关于」页的「保底机制」条目（[about_dialog.py:67](gacha_simulator/gui/about_dialog.py#L67)）与配置文件指南的 `[[pity]]` 示例注释（[about_dialog.py:207](gacha_simulator/gui/about_dialog.py#L207)）改为由 `BEHAVIOR_REGISTRY` 的 `display_name` 生成，使 G3 两种形态的说明与后续新增 type 自动进入关于页（§3.10.4 配套第 4 条） |
| `service/gacha_service.py` | 修改（**S6c** + **S9**） | 定轨识别 `isinstance(bh, TargetedBehavior)` → **实测落地的口径是 `pity_engine.get_pity_def(pname).btype in ('targeted', 'targeted_soft')`**（H1，**S6c**）。**订正（S6c 落地后回写，2026-10-13）**：本行原写 `getattr(bh, '_btype', '')`，与实现不同源；两者对**任何可构造配置等价**（11 个 registry 条目全走 preset 分支、`Pity._btype` 直取 `pdef.btype`、旧类分支不可达），实测把判据换回 `getattr(bh, '_btype', '')` 时 6 条用例全绿。实现取 `get_pity_def` 的真实价值是**与下游 `switch_allowed` / `switch_resets_progress` 的取型同源**，不依赖零件侧 `_btype` 的实现细节。 **S9（2026-09-28 重梳；同日复核修正）**：**不再是 `SimView` 的填充点**——`initial_counts` 提升为 `GachaState` 字段后，视图由 state 自产（`state.sim_view()`）。**注意：`GachaService` 并不构造 `GachaState`**（全库构造点只有 [batch_simulator.py:508](gacha_simulator/service/batch_simulator.py#L508) 与 `clone()`；`run_simulation` 首行是 `initial_state.clone()`，[gacha_service.py:307](gacha_simulator/service/gacha_service.py#L307)），故本文件的改动是**把 `_initial_counts` 的计算结果落到 state 上**——**定稿为「`run_simulation` 内 `clone()` 之后赋值」**（**ISSUE-914，2026-10-01 二择一定稿**）：原稿并列「经构造点或 clone 之后的赋值」两个候选而未定，二者覆盖面不同——构造点赋值只覆盖 `batch_simulator` 那一处 `GachaState(...)`，**覆盖不到任何直接构造 `GachaState` 后进入 `run_simulation` 的调用方**（测试、脚本、`worst_impact` / `retreat_search` 等），而这些路径的首行是 `initial_state.clone()`（[gacha_service.py:307](gacha_simulator/service/gacha_service.py#L307)），故赋值落在 `run_simulation` 内 clone 之后才覆盖**全部**入口，且与「state 字段是单一真相源」的定稿同口径。**落点写死（ISSUE-916，2026-10-01）**：本步**不新增推导**——`run_simulation` 的 [:310-315](gacha_simulator/service/gacha_service.py#L310-L315) 已有 `_initial_counts` 的现算（数据源 `self.card_defs`，与 `batch_simulator` 的 `env.card_defs` 同源），改动只是在 [:307](gacha_simulator/service/gacha_service.py#L307) 的 `state = initial_state.clone()` 之后把它写到 `state.initial_counts` 上；`batch_simulator.py:508` 的 `GachaState(...)` **不增该形参**、`_ms_initial` 随之删除（§四 `service/batch_simulator.py` 行）。原稿「服务层的改动只剩构造 GachaState 时把 `_initial_counts` 传进去」是事实错误。<!-- REVIEW-R1-FIX: ISSUE-914 --><!-- REVIEW-R1-FIX: ISSUE-916 --> | <!-- REVIEW-FIX-PREV: ISSUE-010 --> <!-- REVIEW-FIX-PREV: ISSUE-027 --> <!-- REVIEW-FIX-PREV: ISSUE-013 --> <!-- REVIEW-FIX-PREV: ISSUE-007 --> <!-- REVIEW-FIX-PREV: ISSUE-008 --> <!-- REVIEW-FIX-PREV: ISSUE-027 --> <!-- REVIEW-FIX-PREV: ISSUE-033 --><!-- REVIEW-R1-FIX: ISSUE-003 --> <!-- REVIEW-R1-FIX: ISSUE-953 -->
| `service/batch_simulator.py` | 修改（**S8 / S9**） | **ISSUE-007 / ISSUE-008：配置到运行时引擎的桥接，原稿全表零出现**。三处**枚举式透传点**须同步 `priority`（[batch_simulator.py:1168-1193](gacha_simulator/service/batch_simulator.py#L1168-L1193) 的 `pentry` **24 键**（实测；原写「26 键」）、[:218-243](gacha_simulator/service/batch_simulator.py#L218-L243) 的 `_PityDef` 重建、`core/retreat_config.py` 的浅拷贝——即 §3.6 AUDIT-BREAK-1 表 **#1–#3**，此处「三处」与那张表同指）（~~与 `reads`~~，2026-10-06 取消）：任一处漏写，引擎侧读到的恒为默认值，配置层看不出异常。**`initial_counts` 不属本行透传面**（它是 `GachaState` 字段、**不是** `PityDef` 字段，AUDIT-BREAK-1 的三处本就不含它）：初值由 `GachaService.run_simulation` 现算并落到 state 字段（§四 `service/gacha_service.py` 行），本行只**删除** `_ms_initial` 推导与 :486 实参（见本行末 S9 段）。<!-- REVIEW-R1-FIX: ISSUE-916 -->**建议同时改造为「由 dataclass 字段驱动」以免后续再漏** **AUDIT-BREAK-1 追加**：本行是字段往返守卫测试的第一处断言对象（`assert set(pentry) == {f.name for f in dataclasses.fields(PityDef)}`，§六「PityDef 字段枚举透传守卫」条）；改造后 `pentry` 必须由 `dataclasses.fields(PityDef)` 驱动生成，不得继续手写键表 | **S9（2026-09-28 审查补；ISSUE-914 于 2026-10-01 补定稿；ISSUE-916 于 2026-10-01 收口为「单一推导源 + 单一赋值点」）**：`GachaState(...)` 构造点在 [batch_simulator.py:508](gacha_simulator/service/batch_simulator.py#L508)（**行号已刷新**，原引 `:492`），**不增 `initial_counts` 形参**——初值的推导源与赋值点都在 `GachaService.run_simulation`（§四 `service/gacha_service.py` 行定稿），本文件**不再持有任何推导**。本步的改动只有**删除**两处：① `if env.milestone_defs:` 块内的 `_ms_initial` 推导（[batch_simulator.py:477-482](gacha_simulator/service/batch_simulator.py#L477-L482)，块首 `if env.milestone_defs:` 在 :473）——**默认配置（无里程碑）根本不执行该块**，它既不能充当构造点的初值来源，也无保留价值（原稿「把 `initial_counts` 的推导整段上提到该条件块之外」的写法**作废**）；② [:486](gacha_simulator/service/batch_simulator.py#L486) 的 `initial_counts=_ms_initial` 实参。里程碑侧改从 `GachaState` 取，且**只能落在 handler 内**——注册（[:483](gacha_simulator/service/batch_simulator.py#L483)）发生在 `GachaState` 构造（:508）之前，届时无 state 可读；`_on_after_draw(banner_id, pool_id, card_id, pity_triggered, draw_index, state, collector)` 的形参里就有当场的 `state`（[milestone.py:180](gacha_simulator/core/milestone.py#L180)），故 `_consume_bonus` 改读 `state.initial_counts`（[milestone.py:215](gacha_simulator/core/milestone.py#L215)），`register_milestone_engine` 的闭包捕获同步删除（[milestone.py:163](gacha_simulator/core/milestone.py#L163)）。**行号刷新（ISSUE-914 / ISSUE-953；2026-10-09 按工作树实测重刷）**：本段原把四处旧引用标为「现值」，实测四者皆非现值，现按实测改正：`GachaState(` **:508**（原标 :501）、`_ms_initial` 区间 **:477-482**（原标 :466-479；块首 `if env.milestone_defs:` 在 :473、`:486` 为 `initial_counts=_ms_initial` 实参）、`pentry` 块 **:1168-1193**（原标 :1161-1186）、`_PityDef(...)` 重建块 **:218-243**（原标一致，四者中唯一准确）。同文件其余锚点现值：`compute_scope_mappings` 五元组解包 **:273**、`MPPool(...)` 块 **:873-876**（原标 :866-869）、`run_batch_parallel` 定义行 **:728**（原标 :721）、`_PityDef` 别名 **:202**（原标 :193，**ISSUE-925**）。按「值会持续漂移」的既有认识，**本节只保证 2026-10-09 工作树时点的值**。<!-- REVIEW-R1-FIX: ISSUE-914 --><!-- REVIEW-R1-FIX: ISSUE-953 --><!-- REVIEW-R1-FIX: ISSUE-925 --><!-- REVIEW-R1-FIX: ISSUE-914 --><!-- REVIEW-R1-FIX: ISSUE-915 --><!-- REVIEW-R1-FIX: ISSUE-003 -->
| `core/retreat_config.py` | 修改 | **ISSUE-007 / ISSUE-008**：[retreat_config.py:123-142](gacha_simulator/core/retreat_config.py#L123-L142) 按 24 个显式字段浅拷贝 `PityDef`（行号与字段数 2026-09-22 实测修正），同一批透传缺口的第三处，须补 `priority`（~~`reads`~~ 已于 2026-10-06 取消）**AUDIT-BREAK-1 追加**：本行是字段往返守卫测试的第三处断言对象（同 `pentry` 口径），浅拷贝须改为 dataclass 字段驱动；漏字段的失败形态是**静默落回默认值**而非报错 |
| `core/strategy.py` | 修改（**S9**） | **2026-10-06 改判（§3.10.2）**：`StrategyContext.get_pity_probabilities`（**定义在 [:158](gacha_simulator/core/strategy.py#L158)**，方法体内的 `get_probabilities` 调用在 `:178`；**2026-10-10 订正**：原写 `:178` 作方法起点，实测不符）是第二条送达通道，须自行构造并传入 **`SimView`**（它是 `StrategyContext` 的方法，而 `StrategyContext` 持有 `GachaState`，[:96](gacha_simulator/core/strategy.py#L96)；`acquired` 经 `:112-115` 的 property 读取），**（ISSUE-727：「或在 Modifier 侧以『`external is None` → 恒等』兜底并登记已知差异」这一备选已删，该分支是死分支**：§3.10.2 已删除 `ExternalView` / `external` / `PityDef.reads` 并把 `sim` 改为**非 Optional**，漏参在构造 `DrawFacts` 时即 `TypeError`，不存在「`external is None`」这一状态）。**另须裁决 `acquired` 的口径（ISSUE-730 / ISSUE-944，强制）**：本文件的 `StrategyContext.acquired`（[core/strategy.py:112-115](gacha_simulator/core/strategy.py#L112-L115)）直读 `state.acquired`、**不含初始持有**，而 S9 把 `SimView.owns()` 定为 `total_holding` 口径（含初始持有，§3.10.2）。配置了 `initial_count > 0` 的卡时，同一抽内策略判「未拥有」而保底引擎（G3 的 `NotOwnedModifier`）判「已拥有」，两处结论相反且都不报错。**裁决（2026-10-10 用户裁定：迁移到含初始持有的口径）**：**策略侧的「是否已拥有」判据一律改用含初始持有的口径**——`initial_count > 0` 的卡，策略侧不再判「未拥有」。**裁决理由（用户原话归纳）**：「是否已拥有」在存量检测语义上只应使用含初始持有的量；玩家开局就有 5 张的卡，策略不该认为「还缺 5 张」。
| `strategies/builtin/pity_reserve.py` + `pool_quota.py` + `smart.py` + `stop_on_target.py` | 修改（**S9-5**，2026-10-10 新增） | 9 处「是否已拥有」判据由 `ctx.acquired.get(t.card_id, 0)` 改为 `ctx.state.total_holding(t.card_id)`（含初始持有）。**本行是 ISSUE-730 / ISSUE-944 裁决的落点登记，原稿 §四 全表无这四个文件**；逐处行号、API 形态的选择理由与验收命令见 §七 S9-5 |

**实现形态（关键：不动 `state.acquired` 的定义）**：`state.acquired` 的语义是「本次模拟**新获得**的卡」，**不含** `initial_count`，且该语义**有测试钉住**（`tests/service/test_gacha_service.py` 的 `test_initial_count_not_prepopulated`，断言「`initial_count > 0` 不预填入 `card_counts`」）。故迁移的是**消费侧**：**4 个内置策略文件的 9 处** `ctx.acquired.get(t.card_id, 0)`（**2026-10-10 实测**：`pity_reserve.py` 2 / `pool_quota.py` 2 / `smart.py` 2 / `stop_on_target.py` 3；形态含 `>= quantity_needed` 5 处、`< quantity_needed` 3 处、`smart.py:39` 的中间赋值 1 处。原写「5 个内置策略」在**文件数**上不准确，处数 9 正确）改用 `ctx.state.total_holding(t.card_id)`（含初始持有口径；**为何不用 `ctx.sim.owns()` 见 §七 S9-5**）；`ctx.acquired` 本身保留原语义与既有消费者。

**影响面实测（2026-10-10）**：`gacha_simulator/config/config.toml` 的全部 `card_defs` 均为 `initial_count = 0`，而 P79 的 `p79_verify.py` 正是以该文件为固定输入（`CONFIG = 'gacha_simulator/config/config.toml'`）。**故本次迁移不改变 P79 golden**（`pity_reserve` 等组无需重固化）——原先「会改变输出、golden 需重固化」的判断在该配置下不成立；真正受影响的只有「用户配置了非零 `initial_count`」的场景，而那正是本条要修的场景。**但仓内另有 3 条非零 `initial_count` 的既有用例会随迁移改变行为**（`tests/service/test_gacha_service.py`，逐条见 §七 S9-5 的「既有测试的必红面」条）——「P79 golden 不受影响」与「这 3 条用例必红」是两件事，不得据前者推断后者。

**次序（强制）**：迁移的落地块是 **§七 S9-5**（2026-10-10 新增），且**必须排在 S9-2 之后**——本迁移依赖的是 `state.total_holding` 的 `initial_counts` 形参移除（§四 `core/state.py` 行，属 S9-2），而非 `SimView` 类的存在；2026-10-10 改判 API 形态后，原写「不得早于 `SimView` 交付」不再精确。§六 的对照用例（G3 补充用例行）相应从「两侧期望值各自断言」改为「两侧**同口径**断言（均为含初始持有）」。**AUDIT-BREAK-9 追加**：本行为 `reads` 的**通道 B**（策略查询通道）宿主：`get_pity_probabilities` 经 `_pity_cache` 绕过 `Banner.draw`，须与通道 A 共用同一 `GachaState` / `_initial_counts` 源；验收见 §六「**`sim` 双通道送达**」条（**2026-10-10 订正**：该条原名含 `reads`，该字段已于 2026-10-06 取消并改名） | <!-- REVIEW-R1-FIX: ISSUE-009 -->
| `core/strategy_context_builder.py` | **本次不改**（**行为变化登记为已知差异**，ISSUE-921） | `build_strategy_context()` 的 `inter_pool_pity_links` 段（[:89-107](gacha_simulator/core/strategy_context_builder.py#L89-L107)，整段包在 `except Exception: pass` 内）用 `getattr(pity_engine, '_behavior_list', [])` + `getattr(bh, 'pools', None) or getattr(bh, '_pools', None)` 提取跨池联动。**P64 后该字段由「恒空 dict」变为实际产出**：① `_behavior_list` 的元素由旧 behavior 类换成 `Pity` 对象；② §3.1.4 骨架的 `self._pools = pools`（:493）与 §3.2 的 `pools=tuple(getattr(pdef, 'pools', ('*',)))`（:903）让该属性**首次有值**（`pools` 长度 > 1 时才产出，与既有判定一致）。**键空间为全限定 `{banner_id}.{pool_id}`**（与抽卡管道传入 `pity_engine` 的 `qualified_key` 同口径，[banner.py:55-56](gacha_simulator/core/banner.py#L55-L56)；`Pity._pools` 取自 `PityDef.pools`，落地时须核对每条 `[[pity]]` 的 `pools` 值的书写口径）。**当前 8 个内置策略零消费该字段**，故本期不产生行为差异；本行**不改该文件**，只登记「未登记影响面 + 跨模块耦合」——策略构建器直读保底引擎的**私有属性**（`_behavior_list` / `_pools`），P64 改内部结构即触及它。计划全篇此前对该文件零命中（`strategy_context_builder` 与 `inter_pool_pity_links` 的 grep 均为 0），本行补上。**可选的后续消解（不在本次范围）**：改经保底引擎的公开访问器取值，消除私有属性耦合 | <!-- REVIEW-R1-FIX: ISSUE-921 --><!-- REVIEW-R1-FIX: ISSUE-009 -->
| `core/result_store.py` | **本次范围外 + 已知缺口登记**（ISSUE-922） | `compute_config_hash()` 的保底分支（[:519-522](gacha_simulator/core/result_store.py#L519-L522)；**GATE-FAIL-2-文件清单，2026-10-09 实测订正**：原标 `:479-482`，该处是 P79 的 docstring，真实保底分支在 `:519-522`，偏移约 40 行）<!-- REVIEW-R1-FIX: GATE-FAIL-2-文件清单 -->写 `h.update(pd.name.encode())` + `h.update(str(getattr(pd, 'params', {})).encode())`，而 `PityDef.params` 自 P55 扁平化后**已不存在**（[config_store.py:153](gacha_simulator/core/config_store.py#L153) 的 docstring 明写「旧字段（params/target_distribution/reset_condition）已移除」），该式恒为 `str({})`——**只有保底名进指纹**。缺陷本体是 P55 遗留，但 **P64 是第一个往 `PityDef` 塞「影响结果的新字段」的改动**（`priority` 经 §1.5 裁决直接决定概率管道执行顺序；~~`reads` 决定 G3 因子是否生效~~，2026-10-06 取消），两份**仅 `priority` / `reads` 不同**的数据集会被判为「配置: 相同」→ 面板与 GDR 的跨数据集对比结论失真（数据集指纹是可比性判定的唯一依据，调用方 [gui/main_window.py](gacha_simulator/gui/main_window.py) / [webui/api.py](gacha_simulator/webui/api.py)）。**处置（取保守路径）**：本次**不改哈希**，登记为已知缺口（手册 §21 汇总同批登记，见 §六 缺口登记条）；若实施时选择同批修复，则把该分支改为按 `dataclasses.fields(PityDef)` 逐字段入哈希（与 §3.6 的 dataclass 驱动改造同源、一次覆盖后续新字段），并配 `tests/core/test_result_store_config_hash.py` 的 pity 用例（该文件现无任何 pity 断言） | <!-- REVIEW-R1-FIX: ISSUE-922 -->
| `core/worst_impact.py` | 修改（**S8-5**） | **ISSUE-GATE-FAIL-2 补登记（2026-09-22）**：本文件是第二处 `PoolPitySpec` 构造点、S8-5 的目标文件之一（§七 S8-5 已列），但原稿只在 §3.9.3 组件处置表与 §3.9 专项出现，**§四 全表零行**——实施者据此无法判断它是否在改动范围内。改动内容**分两批（ISSUE-901 / ISSUE-904，2026-10-01 改判）**：**S8-5 只做「卡集合按池对齐」**——卡集合须与池内 reward id 对齐，断言 `set(scope_cards[scope]) ⊆ {r.id for r, _ in pool.rewards}`（§3.9.3 的 ISSUE-006 专项；**2026-10-09 实测**：该对齐已由 `e32577f` 落地、覆盖不变量已在 `worst_impact.py:536-541` 就位，故 S8-5 本子项降为「保留不变量」，不再有改造量），该项与槽位字段的存废无关；**「删除三个槽位实参、只构造卡集合字段（`scope_cards` / `featured_cards` / `featured_ids` / `ssr_ids`）、`_ref_pool_entry` 的写后即读的局部变量化（[:372](gacha_simulator/core/worst_impact.py#L372) 赋 / [:373](gacha_simulator/core/worst_impact.py#L373) 读；**原写「复活/替换 [worst_impact.py:504](gacha_simulator/core/worst_impact.py#L504) 死分支」，该分支实测不存在**，见 §3.9.3 订正）」三项一并推迟**到 GATE-5 末条「发布前一次性移除旧保底类」的同一 commit——S8 期间槽位三字段不删，按 8 字段构造仍成立，S8-5 提前只给卡集合字段会让旧类在第一处 `ctx.draw.scope_slots.get(...)` 即崩。<!-- REVIEW-R1-FIX: ISSUE-904 -->**亦为跨进程 pickle 的三条独立入口之一**（[worst_impact.py:136-140](gacha_simulator/core/worst_impact.py#L136-L140)） | <!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-2 --> <!-- REVIEW-R1-FIX: ISSUE-955 -->
| `CLAUDE.md` | 更新（**文档同步，ISSUE-017**） | §二「保底 (core/pity.py)」整节在 P64 后失真（`SoftPityMixin` / `BEHAVIOR_REGISTRY` 的 type→class 映射 / `PityEngine` 签名 / P75 四条纪律 / `create_behavior` 数据流均被改动），扩展指南表「新保底行为」一行同样失真；须同步 | <!-- REVIEW-FIX-PREV: ISSUE-017 -->
| `docs/00-meta/模块状态矩阵.md` | 更新（**文档同步，ISSUE-017**） | 实测该行**已含** G3 / S9 / S10 / S11 与「M1（S1–S7 + S10 + S11）/ M2（S8 + S9）」划分（自 2026-09-22 起；**2026-10-09 订正（ISSUE-004）**：原记「已含 G3 / S9 / S10 / S11 / **S12**」与「含自 M2 前移的 **S12**」两处，S12 已于 2026-10-06 整块取消、不进摘要），**2026-09-30 复核：原写「仍写『覆盖 G1 幻塔必歪 + G5 priority』，未含 G3 / S9 与 S10/S11，也未含 M1/M2 划分」已不成立**。**2026-10-10 核对：该「更新点」已不存在**——矩阵 [:72](docs/00-meta/模块状态矩阵.md#L72) 与头部 [:4](docs/00-meta/模块状态矩阵.md#L4) 均已含「2026-09-30 裁决双实现 `hard_exclude_owned_skip` / `hard_exclude_owned_any` 两条 type，§3.10.4「全部已拥有」退化分支维持待确认」，矩阵已领先于本行的记载，原写「尚未进摘要」已不成立（本行不再有待办更新点） |
| `config/config.toml` | 更新 | 幻塔 `rotating_inverse` + G16 示例段。**ISSUE-913（2026-10-01，波及面补登记）**：本文件是 **P79 常驻护栏的固定输入**——[p79_verify.py:38](scripts/p79_verify.py#L38) 的 `CONFIG = 'gacha_simulator/config/config.toml'`，由活测试 [test_p79_stop_condition_baseline.py:29-37](tests/test_p79_stop_condition_baseline.py#L29-L37) 以子进程运行并断言「退出码 0 + stdout 含『等价对照结果：PASS』」，另有 `tests/fixtures/p79_golden/` 的 golden 快照逐字段比对。**故新增段的形态必须先定**：① **推荐（注释形态）**——示例写成 `# ` 注释块或纯说明文字，**不进 TOML 的生效段**，golden 的 `draw_pity_names` / `final_pity_state` / `banner_end_pity_states` 等字段一字不变，护栏不受影响；② 若必须写成**生效 TOML 段**（新增 `[[pity]]` / `[[banner]]`），则 golden 必然变化，须同步「golden 重固化方案 + 有意变更登记」（**禁止**用 `p79_baseline.py` 覆盖已提交基线），并在 §六 的差异归因清单登记该项——否则该活测试必红、H9 直接拦推。**计划全文原对 `p79` / `fixtures` / `golden` 零命中**，本行是本条护栏的唯一登记点。**归属待定（2026-10-10，G16-2 实现审查登记）**：本行登记的「幻塔 `rotating_inverse` + G16 示例段」至今**无块承接**——§七 的 G16-1 / G16-2 目标文件均不含本文件，实测该文件对 `never` / `rotating_inverse` 两个词零命中；落地前须先定归属（且受本行 ISSUE-913 的注释形态约束），不在 G16-2 内扩范围处理 | <!-- REVIEW-R1-FIX: ISSUE-913 --><!-- REVIEW-R1-FIX: ISSUE-007 -->
| `tests/core/test_pity_config_toml.py` + `tests/gui/test_config_panel_p56.py` | 修改（**S6a / S9-3**，2026-10-01 补登记） | **ISSUE-912**：前者两条用例正断言 H3 的 `ConfigError`（[:249](tests/core/test_pity_config_toml.py#L249) / [:263](tests/core/test_pity_config_toml.py#L263)）；后者 [:53](tests/gui/test_config_panel_p56.py#L53) 写死 `_PITY_TYPES` 数量为 10、[:116](tests/gui/test_config_panel_p56.py#L116) 正断言 `deactivate_on_early_hit` 仅 `hard` 启用。**原 §四 与 §七 的存量测试清单（S7d / S8-7）对这两个文件零命中**，按原计划施工会在 S6a / S9-3 的 commit 上直接 `pytest -q` 全红（H9 拦推） | <!-- REVIEW-R1-FIX: ISSUE-001 -->
| `tests/core/test_pity_config_toml.py` + `tests/test_config_toml.py` | 修改（**S4c**，2026-10-06 补登记） | 键契约一致性测试（每个 btype 用全量键构造 → `_pitydef_to_toml` 产出键集 ⊆ 契约表；反向契约表 ⊆ `_build_pity` 读取面）+ 未知键硬拒用例 + `load_toml` 失败原子性用例（失败后传入 store 逐字段不变） |
| `tests/core/test_pity_equivalence.py` | **新增**（**S5a / S5b**） | 等价性对比 harness（固定种子逐场对比概率分布 + `PityState.to_dict()` 快照，S5a）与按家族分批接入的等价性用例：`hard` / soft 族（3）/ rotating 族（3）/ targeted 族（2），每批独立运行、失败可独立归因（S5b）。**2026-09-22 补（ISSUE-GATE-file-list）**：原稿只写 `tests/` 泛行，S5 的用例无处落笔 | <!-- REVIEW-FIX-PREV: ISSUE-GATE-file-list -->
| `tests/core/test_pity_invariants.py` | **新增**（**S10-1 / S10-2**） | 组合正确性验收（§3.12）：随机零件组合的生成器与不变式性质断言（归一性 / 非负性 / 增量合法性 / 状态键合法 / 确定性）+ 合法组合判据用例。**2026-09-22 补（ISSUE-GATE-file-list）** | <!-- REVIEW-FIX-PREV: ISSUE-GATE-file-list -->
| `tests/core/test_pity_invariant_checker.py` | **新增**（**S11**） | `InvariantChecker` 的**专属**验收测试（§六「S10 / S11（保障层）」段）：**正例** `hard(scope='sr')` 的合法配置（Σ = 1.009）不得报错（归一性按 scope 感知口径）；**负例** 卡概率改负 / Σ 改到 1.2 / 白名单外写 `_active` 时必须抛错，且异常信息含**保底名 + 键 + 期望值 / 实际值**三要素。**原稿 S11 无任何测试文件**，`tests/core/test_pity_invariants.py` 归 S10-1 / S10-2（组合正确性，§3.12），与被测对象不同，两者不得混用 | <!-- REVIEW-FIX-PREV: ISSUE-GATE-test-strategy --> |
| ~~`tests/core/test_pity_condition.py`~~ | **不新增**（**2026-10-06 随 §3.14 改判删除**） | 原 Condition 类族专属验收测试（条件求值真值表，S12-1 / S12-2 的验收命令均指向本文件）：`Always` / `Flag` / `Counter` / `FateReady` / `Ratio` / `Owned` / `RandomThreshold` 七个叶子条件 + `And` / `Or` / `Not` 三个组合子。**ISSUE-GATE-FAIL-2 补登记（2026-09-22）**：`core/pity_condition.py` 与 `ConditionalModifier` 是 M1 内 S3 / S4 的直接前置（ISSUE-101），其测试文件与模块同批新增，原稿 §四 无本行 | <!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-2 -->
| `tests/` | 新增/修改 | 等价性测试（旧类 vs 新引擎，全部类型）+ G1/G5/G16 测试 + N1 / M4 / H4 三条强制约束专项断言（S5c）+ 跨进程 pickle round-trip（S7b） **AUDIT-BREAK-7 追加**：S7d（M1）与 S8-7（M2）两块的存量测试改造目标文件清单见 §六「存量测试文件在删除点之前完成改造」条；**AUDIT-BREAK-1 追加**：字段往返守卫测试（`batch_simulator` / `retreat_config` 两处透传）亦落于本目录 |
| `docs/01-活跃/subsystems/保底系统/01-理论.md` | 更新（**文档同步，ISSUE-028**） | 子系统文档集（目录实测六件）之一，**已核涉及 P64**：`§2.1 执行顺序` 段（[:64](docs/01-活跃/subsystems/保底系统/01-理论.md#L64)）引用 P64 §1.5 的接线裁决与 §3.1.5.4 的顺序敏感集合。P64 落地后须回写：`_resolve_order` 已接入管道（不再是「算了但没人按顺序用」）、`priority` 语义、卡级管道与增量形式（§3.1.5） | <!-- REVIEW-FIX-PREV: ISSUE-028 --> |
| `docs/01-活跃/subsystems/保底系统/02-实施.md` | 更新（**文档同步，ISSUE-028**） | 子系统文档集（目录实测六件）之一，**已核涉及 P64**：`§一 代码位置` 的 `pity.py` 行号表（[:17-42](docs/01-活跃/subsystems/保底系统/02-实施.md#L17-L42)，逐行列出 `SoftPityMixin` / 10 个行为类 / `BEHAVIOR_REGISTRY` / `_validate_registry` / `_resolve_order` / `compute_scope_mappings` / `PityEngine`）与 `§2.1`（[:36](docs/01-活跃/subsystems/保底系统/02-实施.md#L36)）。P64 后 10 类退役、`pity.py` 结构重排（新增 `pity_primitives` / `pity_tracker` / `pity_modifier` **三**模块；**`pity_condition.py` 已于 2026-10-06 随 §3.14 改判取消、不在新增面**，照抄旧稿会引入不存在的模块），该表与相关结论段整体失真，须整体刷新 | <!-- REVIEW-FIX-PREV: ISSUE-028 --> |
| `docs/01-活跃/subsystems/保底系统/00-档案.md` + `03-审计.md` + `04-问题.md` | 更新（**文档同步，ISSUE-927**） | **原 §四 只列 `01-理论.md` / `02-实施.md` 两件**（措辞「三文件制」，与目录实际六件不符），而这三件同样会随 P64 失真：`00-档案.md` / `03-审计.md` 含 `scope_slots` / `PoolPitySpec` / `SoftPityMixin` 等 S8 结构性删除与 S1–S5 旧类退役对象的记述；`03-审计.md` 的异常 6（`reset` 无取值白名单，见 §1.3，已并入 G16-1）与 `04-问题.md` 的「已处置 / 去向」索引须按落地结果回写。**落地时点 = S7c 同批**（不得只改两件） | <!-- REVIEW-R1-FIX: ISSUE-927 -->
| `scripts/p82_baseline.py` + `tests/fixtures/p82_baseline/` | **新增**（**P82-2**） | **原 §四 无本行**（GATE-2 文件清单，2026-10-09 补登记）：P82-2 的两个新建产物——`scripts/p82_baseline.py`（基线固化脚本，生成固定种子下的 `CompactResult` 快照）与 `tests/fixtures/p82_baseline/`（快照存放目录）。属**独立先行块**，不占里程碑，也不进 M1 / M2 的逐块预算求和 |
| `docs/主流抽卡游戏卡池机制配置转换手册.md` | 更新（**文档同步，ISSUE-028 补全路径**） | 原稿只写「手册」未指明路径。内容：G1/G16 登记（G19/G13/G2/G14/G15/G5 已同步，2026-08-24）；G19 处置后的 §15.3/§15.4/§21 与 `targeted` 缺 `selected_card` 的说明（§1.2 顺带发现）也在此文件 | <!-- REVIEW-FIX-PREV: ISSUE-028 --> |

<!-- REVIEW-FIX-PREV: ISSUE-003 -->
**跨进程 pickle 约束（ISSUE-003，强制，2026-09-22 修复）**

`run_batch_parallel` 用 `MPPool(initializer=_wk_init, initargs=(env, target_specs))` 把**整个 `env` 序列化**给每个 worker（[batch_simulator.py:873-876](gacha_simulator/service/batch_simulator.py#L873-L876)——`with MPPool(` / `processes=` / `initializer=_wk_init` / `initargs=(env, target_specs)` 四行；**ISSUE-915** 更正原引 `:848-850`，那三行是 P83 的 chunksize 与降并发重试注释，与 `MPPool` 无关），`env.pity_engine` 随之进子进程；[cli.py:291-292](gacha_simulator/cli.py#L291-L292) 的既有注释亦写明（**ISSUE-946** 实测更正原引 `:285-286`，含 pickle 字样的行是 :292）「顺序是硬要求：先设字段、再调 `run_batch_parallel`，彼时 env 已 pickle 给 worker」。P64 把 `PityEngine` 的组成从 10 个 behavior 类换成 `Pity` / `Tracker` / `Modifier` / `Lifecycle` **四族**新对象（**ISSUE-731：原写「五族」含 `Condition`，该类族已随 §3.14 改判取消**）加 `InvariantChecker`，**全部进入这条 pickle 路径**。<!-- REVIEW-R1-FIX: ISSUE-915 --><!-- REVIEW-R1-FIX: ISSUE-003 -->

- **约束**：新类的所有成员**必须可 pickle**——禁 lambda / 闭包 / 局部函数 / 不可 pickle 的第三方对象。Condition 已随 §3.14 改判内联进各 Modifier 的 `compute_delta()`，但**风险面并未消失**：Modifier 家族本身是类（可 pickle），而它们的**内联条件是方法体内的裸判断**——与项目内 `ConditionalStrategy` 用 lambda 做条件同源，若把内联条件写成 lambda / 闭包（如 `self._cond = lambda view: ...`），实例即不可 pickle。故此处**必须显式禁止**而非默认安全。（**GATE-check-6，2026-10-09 修正**：原稿举已取消的 `Condition`「代码级 building block」与 `ConditionalModifier`「自造包装器」为例；结论不变、举例对象改按仍存在的实体。）
- **故障形态（为什么必须写死在计划里）**：Windows spawn 下不可 pickle 成员会让每个 worker 的 initializer 直接抛错，而 `run_batch_parallel` 的三次「逐级降并发重试」会把它当资源瓶颈 `logging.warning` 后继续，最终退到**单进程兜底**——表现为**并行度静默归零、耗时暴涨，而不是报错**。
- **波及面（三条产品路径 = cli / gui / webui，共 8 个调用点）**：`batch_simulator.run_batch_parallel`（[:728](gacha_simulator/service/batch_simulator.py#L728) 函数定义行，2026-10-09 实测；原引 `:638` 已随 P83 提交漂移、**ISSUE-915** 改为 `:721`，本轮按实测再改为 `:728`）；**产品侧三条路径各有 2 个调用点**：cli（[cli.py:343](gacha_simulator/cli.py#L343) / [:382](gacha_simulator/cli.py#L382)）、gui（[gacha_panel.py:84](gacha_simulator/gui/gacha_panel.py#L84) / [:108](gacha_simulator/gui/gacha_panel.py#L108)）、webui（[api.py:293](gacha_simulator/webui/api.py#L293) / [:310](gacha_simulator/webui/api.py#L310)）；**内部调用两处**：[worst_impact.py:136-140](gacha_simulator/core/worst_impact.py#L136-L140)（调用在 :139）、[retreat_search.py:203-207](gacha_simulator/core/retreat_search.py#L203-L207)（import :203 / 调用 :207）。每条都把 `env`（含 `env.pity_engine`）pickle 给 worker，故新对象族须在**全部 8 条**上过 round-trip（**ISSUE-003**：原写「三条独立入口」，只列了定义行 + 两个内部调用，漏掉三条产品路径）。<!-- REVIEW-R1-FIX: ISSUE-915 --><!-- REVIEW-R1-FIX: ISSUE-003 -->
- **验收**：§六 增设「对 `env`（或 `env.pity_engine`）做 `pickle.dumps` / `loads` round-trip 断言」。

**不受影响**（S1–S5 期间）：PityEngine 调度层接口签名、`_validate_behaviors`（前提见 §3.2）、PityState/DrawInfo/PityContext（**语义与导入路径不变，S1 起改由 `pity_primitives.py` 承载 + `pity.py` re-export**，§3.1.6）、`_redistribute_scope`、GUI 参数控件、P75 `_rebind_state` 纪律（Pity 统一实现后语义不变）。**2026-09-21 审查修正**：`_redistribute_scope` 与 `DrawInfo`/`PityContext` 的槽位字段在 **S8** 中会被替换或删除（见 §3.9.3），此处的「不受影响」仅指 S1–S5。**2026-10-01 更正（ISSUE-901）**：上述「S8 删除槽位字段」已改判为**推迟**——`DrawInfo` / `PoolPitySpec` 的 `scope_slots` / `featured_slots` / `card_to_slot` 与 `_redistribute_scope` 的函数本体同批，在 GATE-5 末条「发布前一次性移除旧保底类」commit 中删除；S8 只删 `aggregate_probs_by_rarity` / `infer_rarity_from_spec` 及其导出面，旧保底类在发布前保持完整可用（等价性 harness 与 S8-6 的对照基准依赖此点）

## 五、风险

| 风险 | 缓解 |
|------|------|
| 等价性破坏（重构回归）——preset 与旧类行为偏差 | **等价性测试守门**：固定种子，逐场对比 before_draw 输出概率分布 + after_draw 后状态快照完全一致；覆盖全部 10 个类型（含 counter 驱动）；P56 现有测试天然构成基准 |
| 软保底/硬保底 preset 化风险——`_compute_probabilities` 移植 | 全量 preset 化一次完成；等价性测试覆盖全部组合（含 soft 叠加三态） |
| Modifier 链顺序语义与现有 mixin 嵌套不完全一致 | Modifier 链「顺序应用非短路」契约明确写入设计；等价性测试覆盖 guaranteed / 非 guaranteed / 软保底叠加三态 |
| registry/GUI 兼容——preset 化后参数描述失效 | `params`/`ui_params` 原样保留；GUI 控件零改动，round-trip 验收覆盖 |
| P75 `_rebind_state` 纪律在 Pity 中退化 | Pity 统一实现 Trackers/Modifiers/Lifecycle 的 rebind 委托；独立测试断言跨模拟状态隔离。**ISSUE-029**：委托是**无守卫**调用，故**三族（Tracker / Modifier / Lifecycle）的 `rebind` 必须逐个实现**（骨架不做守卫调用，缺一个即每次抽卡入口 `AttributeError`；协议表见 §3.1.1 / §3.9.2 / §3.1.3 / §3.14.3 与 §六 断言）。**2026-10-09 订正（GATE-4）**：原文此处写「`ConditionalModifier` 必须转发」，而该类已随 S12 于 2026-10-06 整块取消（§3.14.2 改判为「取消后的形态」，其「随之删除的符号」段已明列该类），§六 的对应断言亦已删除（ISSUE-004）——原缓解同时指向不存在的类与已改判的小节、不可操作，故删去；<!-- REVIEW-R1-FIX: GATE-4-风险缓解 -->**ISSUE-917**：Lifecycle 的 `rebind` 为三实参（`namespaces`），漏传即 `X_soft` 的 `_active` Flag 跨场不重绑（写错账本且不报错）<!-- REVIEW-R1-FIX: ISSUE-917 --> |
| 增量能力（事件驱动 deactivate）误入等价性范围 | 明确标注「旧类无此能力，不在等价性范围」，单独验收用例 |
| G16 与 P64 并行改 `_should_reset` 冲突 | G16 独立先行（单 commit 先落地），P64 重构时 CounterTracker 自然承载，无交叉 |
| ~~CR 随机数消耗不齐（等价性 RNG 分叉）~~ **已结项（2026-10-10，RULING-6B′）** | `StreakTracker.prepare` 的随机数消耗协议（原 §3.1.2 H4）；消费相位回到 `before_draw` 后与旧类同相位，**「与旧类逐场一致」重新可判**。等价性测试含 `cr_state_probs` (0,1) 中间值用例，并新增两条负例：只读查询不消耗随机数、掷骰失败后 flag 必须为假 |
| 全量 10 类 preset 化改动面扩大 | 不分阶段（软保底不再分阶段二），一次完成；等价性测试全量守门 |
| **生命周期字段到 Lifecycle 对象的转换点缺失（ISSUE-301）** | preset 工厂返回 dict 不写 `lifecycle=` 键、而旧 `create_behavior` 的 `lifecycle_kwargs` 段（:893-900）又已删除，两端各留一半：**全部 `deactivate_on_early_hit` 与全部 `depends_on` 配置静默失效**（§六 的 N1 例外断言、事件驱动型退役断言双双不可达；`depends_on` 的激活传播与「引用不存在名」的 `ConfigError` 一并消失），且旧类已退役、无对照物可发现。缓解：§3.1.3 定唯一转换点 `build_lifecycle(pdef)` + §3.2 取值来源表与代码块的 `lifecycle=` 键 + `create_behavior` 的 `ConfigError` 防线 + §六 断言 | <!-- REVIEW-FIX-PREV: ISSUE-301 -->
| **S8 卡级管道引入的浮点差异与零概率退化** | 浮点差异量级 1e-16，等价性口径已在 §六 放宽为 1e-12 并单独设 S8 验收；零概率退化（无货可取，`p(Q) = 0`）由 §3.1.5.6 约定「返回 `None`」处理，与现行早退路径一致 |
| **映射表未写死的实现细节致等价性失败**（计数相位 / CR 随机数短路） | 两条已在 §3.1 列为强制约束（N1 / H4），§六 设对应断言；两者共同点是均不报错、只让结果静默偏移，故必须在 S1/S5 显式实现与断言。did_fire 一项已按 §3.1.1 M4 裁决为统一语义，属行为变更，走独立验收（可先行）；**范围含六类**，其中 counter 驱动 / rotating / targeted 为收严、三个 `_soft` 复合类型为放宽（ISSUE-102，见 §3.1.1 M4 表与 §六 断言） |
| **快照面差异：事件驱动型多一个 `_active: True` 键（GATE-4 定稿取 ①）** | 统一 `_active` 写入使 `rotating` / `targeted` / `rotating_cr` / `rotating_soft` / `rotating_cr_soft` 的命名空间比旧实现多一个 `_active: True` 键，与 §六「快照逐场完全一致」的字面口径冲突。缓解：§3.1.3 已定稿取 ①（统一写入），§六 按 ① 写死断言（备选分支已删），差异登记入 S1 至 S5 的差异归因清单。**不登记即会被等价性测试当成回归反复排查** | <!-- REVIEW-FIX-PREV: ISSUE-GATE-risk-mitigation --> |
| **三个 `_soft` 复合类型的 `did_fire` 放宽（ISSUE-102 定稿：不加 hit 门控）** | 该族新 `did_fire` 为「出 scope」，旧经 MRO 为「出 scope ∧ is_featured / 命中定轨」，方向为**放宽**（`depends_on` 依赖方在未命中当轮即被激活），与 rotating / targeted 的**收严**方向相反。缓解：§3.1.1 M4 表六行、§六 断言、§七 S5c 三处已同步；不加 hit 门控（裁定见 §3.1.1）；该差异仅在配 `depends_on` 时可见，按「不在等价性范围内」单独验收 | <!-- REVIEW-FIX-PREV: ISSUE-GATE-risk-mitigation --> |
| **`Lifecycle` 的第四组合 `DependentFiniteActive` 为新增路径（ISSUE-032 衍生，2026-09-28 语义定稿）** | 把 `depends_on` 与 `max_triggers` 两维正交后，「被激活后又限触发次数」成为一个此前不存在的组合。旧实现里 `deactivate_on_early_hit`（N=1）对所有类型都可用，但「依赖激活 + 计数退役」从未组合过。**语义定稿（2026-09-28 用户裁决）：退役计数自「激活后」起算**——依据是「退役」计量的是「生效期间用了几次」，激活前的抽卡不消耗该保底的额度（未激活时 `is_active` 为假、`before_draw` / `after_draw` 首行早退，本就不参与结算）。残余风险仅是该组合无既有配置用例可比对，缓解：§六 设断言、S1d 单测固化 | <!-- REVIEW-FIX-PREV: ISSUE-032 --> |
| **`priority` 字段定义与消费的时序错配（GATE-3(a)）** | `PityDef.priority` 原归 S6b 定义，而 S4-2 的 `Pity(..., priority=pdef.priority)` 与 S4b 的三处透传都排在 S6b 之前；实测 `PityDef`（[config_store.py:150-186](gacha_simulator/core/config_store.py#L150-L186)）当前确无该字段，照原序施工即 `AttributeError`；若改用 `getattr(pdef, 'priority', 0)` 兜底，则退化为恒 0 的**静默空转**（priority 永不生效且无任何报错）。缓解：字段定义 + `config_toml` 解析随 S4b 前移（新序 S4-1 → S4b → S4-2），S6b 只留排序键与 GUI 控件 | <!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order --> |
| **registry `class: None` 之后旧类无入口（GATE-3(c) / GATE-5）** | 等价性装置的「旧」侧与回滚路径各自需要旧类，而 10 个条目的 `class` 一律置 `None` 之后旧类在 registry 上已无入口（实测 `BEHAVIOR_REGISTRY` 当前每条都持有真实类对象）。缓解：harness **直接 import 旧类并以显式实参构造**（不经 registry）；回滚方式改为 **`git revert` 子块 commit**，不依赖 registry 保留旧类。备选 `legacy_class` 过渡字段已否决（§3.2） | <!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order --> |
| **S8 / S9 子项无预算与目标文件（GATE-1）** | M2 的 10 个子项原稿只有任务描述，无预算、无目标文件、无验收命令，且回滚单元写成「S8 + S9 整体」，与 M1 刚确立的「回滚单元 = 任务单元」相反。缓解：第八轮补齐逐子项预算（**现行值见 §七 引言的「M2 子块预算」行：S8 合计 4.0 / S9 合计 3.1 人时**（S9 自 2026-10-10 起为 3.1，含新增的 S9-5）；原写「S8 约 3.1 / S9 约 2.4」是该行初稿值，已被 §七 的重新核定取代，此处不再复述数值以免失真）、目标文件与「每子项一个 commit」，并加依赖闭包回退规则（GATE-5）<!-- REVIEW-R1-FIX: GATE-4-风险缓解 --> | <!-- REVIEW-FIX-PREV: ISSUE-GATE-granularity --> |
| **S4c `load_toml` 非原子 → GUI 启动路径配置半装（GATE-4 补登）** | `load_toml` 现实现先 `store.clear()` 再逐段构建（[config_toml.py:62-64](gacha_simulator/core/config_toml.py#L62-L64)），中途抛 `ConfigError` 即停在半成品；已实测（真实配置 + 一处非法 `scope`）：`banners 8→0`、`pity 1→0`。GUI 侧（[main_window.py:240-242](gacha_simulator/gui/main_window.py#L240-L242)）为 `except Exception` → stderr traceback + 状态栏一行字，**窗口照常打开、配置半装**，即本表多行同级强调的「不报错、静默半开」形态。缓解：S4c 的 ② 把加载改为「副本上构建、成功再 swap」或「失败回滚快照」，并顺带修好 `load_toml` 调用链内现有十余处会抛 `ConfigError` 的段（cards / pity / milestone / select_voucher / banners / resource_lifecycle / stop_condition）；回退无连带（只改 `config_toml.py` 与测试，见 GATE-5）<!-- REVIEW-R1-FIX: GATE-4-风险缓解 --> |

## 六、验收标准

### 主线（Tracker + Modifier 统一骨架 + G1 + G5）

- [ ] **S1–S5 口径**：全部 10 个类型同配置下，新引擎输出与旧类**逐场一致**，承诺按两列拆分（**2026-10-11 按 §3.1.5.6 的既有登记同步措辞**，见该节「位级一致」行与 §3.1.5 定理 1 的效力说明）：**概率分布 = 容差 1e-12 内逐场一致**（该数值即 S8 与 S5 产物对比所用，非新造）；**状态快照 = 位级一致**，除已登记的增量键（`_active`，ISSUE-202；`cr_intercepted`，§3.1.1 声明产物）之外逐字段相同。原写「逐场完全一致」对六个事件驱动型不成立：其实测差异为**非条件分支的 1 ULP**（来源是新侧条件不成立时直接恒等、旧侧走 `_redistribute_scope` 的除再乘往返，量的上界 1.11e-16，九种池形状扫描；该 1 ULP 是旧侧往返舍入的产物、不含语义内容）。状态机的部分（counter 整数相位、flag 布尔翻转、随机流位置）在两种口径下**都是精确比较**，故放宽的只是浮点分布一列，不削弱「重构未退化」的证明力。载体见 `tests/core/test_pity_equivalence.py` 的 `Tolerance` 参数。（固定种子，含 hard/soft_step/rotating/targeted/soft 组合各基准；**`rotating_cr` / `rotating_cr_soft` 已于 2026-10-10 回归本行**——RULING-6B′ 把掷骰相位移回 `before_draw` 的 `StreakTracker.prepare`，首抽缺口与随机流位置差同时消除，与旧类逐场一致；原「不在此列」的排除与下方差异归因清单 (c) 项一并作废）。此阶段 Modifier 内部沿用槽位法，故要求位级一致 <!-- REVIEW-R1-FIX: ISSUE-702 --> <!-- REVIEW-R1-FIX: ISSUE-940 -->
<!-- REVIEW-FIX-PREV: ISSUE-023 -->
<!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order -->
- [ ] **view 命名空间分配（ISSUE-GATE-dependency-order；接口由 ISSUE-407 补实）**：三个 `_soft` 类型的 preset 中，soft 族的**软计数落在默认 view（`X` 命名空间）**（对齐旧 mixin 的 `X.counter`），`X_soft` 命名空间只含 `_active`——**产出者是 preset 里显式的 `NamespaceTracker(namespace=f'{pdef.name}_soft')`**（§3.1.1 签名表新增条目，§3.2 的 `_preset_rotating_soft` 示例），`_active` 由 **`Lifecycle.initialize(state, name, namespaces)`** 的推广作用域写入（`namespaces` = `Pity` 收集的零件命名空间集合）；声明了 `namespace` 的零件收到的是 `StateView(state, part.namespace)` 而非默认 view（`Pity` 经 `self._ns_views` 取值，遍历 `trackers` / `modifiers` 时不得写死 `self._view`）；`_rebind_state` 重建默认 view 时**同批重建 `self._ns_views`**（否则 worker 内连跑 N 场模拟时第 2..N 场的零件 view 指向旧账本，与 ISSUE-004 同一失效模式）<!-- REVIEW-R1-FIX: ISSUE-407 -->
- [ ] **`_soft` 族命名空间保留（ISSUE-023）**：`X_soft` 命名空间及其 `_active` 键在 preset 化后原样存在，`PityState.to_dict()` 的快照字段集合与旧类相同（三个 `_soft` 类型各一条）；若实施选择合并命名空间，则该差异须已登记进下方差异归因清单且 S1–S5 断言已相应放宽
<!-- REVIEW-FIX-PREV: ISSUE-202 -->
- [ ] **`_active` 构造期写入（ISSUE-202）**：全部 10 个 preset 构造出的 `Pity`，其 `_lifecycle.initialize(state, name, namespaces)` 已在构造期被调用——**非 `depends_on` 保底**在构造后 `state.get(name, "_active")` 为 `True`（若为 `False`/缺失，则 `before_draw` / `after_draw` 首行早退、计数型保底全线失效，属阻塞级缺陷）；`DependentActive` 构造期不写、其 `_active` 由引擎激活传播置位。**事件驱动型的差异须登记**：`rotating` / `targeted` / `rotating_cr` / `rotating_cr_soft` / `rotating_soft` 的命名空间在 preset 化后**多一个 `_active: True` 键**（旧类不写），该差异允许存在并须登记为 S1–S5 已知差异，不得当作回归（§3.1.3 已定稿取 ①「统一写入」，备选已否决，**故本断言只有这一版**）<!-- REVIEW-FIX-PREV: ISSUE-GATE-risk-mitigation -->
- [ ] **`X_soft._active` 的跨场重绑（ISSUE-917，强制，2026-10-01）**：`Lifecycle` 为 `name` 与 `namespaces` 的并集中**每个**命名空间各持一个 `_active` Flag，`rebind(state, name, namespaces)` 对**并集中每个** Flag 做纯重定向（不复制旧值）。判据两条：① 构造期 `state.get('x_soft', '_active') is True` 且 `state.get('x', '_active') is True`（`AlwaysActive` / `FiniteActive`，与上条 ISSUE-023 的快照断言同场）；② **worker 内连跑第 2..N 场**——`lc.rebind(s2, 'x', ('x_soft',))` 后命名空间 Flag 的写入落点 `is s2`（断言 `lc._ns_active['x_soft']._state is s2`）；反向形态（`rebind` 只重绑 `name`）本条必红。`deactivate(state, name)` 只清 `name`，命名空间的 `_active` 不受退役影响（与旧实现内层 `SoftStepBehavior._active` 同形）。<!-- REVIEW-R1-FIX: ISSUE-917 -->
<!-- REVIEW-FIX-PREV: ISSUE-301 -->
- [ ] **`deactivate_on_early_hit` / `depends_on` 构造保真（ISSUE-301）**：① 全部 10 个 preset 的返回 dict 含 `lifecycle` 键（缺失时 `create_behavior` 抛 `ConfigError`，不静默回退 `AlwaysActive()`）；② `deactivate_on_early_hit=True` 的配置构造出的 `Pity._lifecycle.deactivate_on_early_hit` 为 `True`，`False`/缺省时为 `False`（不得恒 `False`）；③ `pdef.depends_on` 非空时 `_lifecycle` 为 `DependentActive` 且其 `depends_on` 与该字段相同，为空时 `isinstance(_lifecycle, AlwaysActive)`；④ 两个字段全缺省时与旧 `create_behavior`（不带 `lifecycle` 实参、behavior 落到默认 `LifecycleConfig()`）逐场一致。**本条失败即意味着两类配置静默失效**——N1 例外断言与本表的「参与 `depends_on` 的事件驱动型在激活前不改分布」断言随之不可达，`depends_on` 引用不存在名的 `ConfigError` 也一并消失

<!-- REVIEW-FIX-PREV: ISSUE-204 -->
- [ ] **preset 构造不得静默跳过（ISSUE-204）**：全部 10 个 preset 构造成功且 `len(engine.behaviors) == len(pity_defs)`；任一 preset 构造失败**抛 `ConfigError`**（不得只 `logger.warning` 后跳过——跳过会让 `_resolve_order` / `_validate_behaviors` 在**截断后**的列表上执行，同 scope 互斥等校验失去语义，形成「配置里写了保底、运行时该保底不存在且无可见报错」）
- [ ] **S8 口径**：切换为卡级增量后，与 **S5 的产物**逐场对比，概率分布**容差 1e-12 内一致**、状态快照**完全一致**（浮点求和顺序改变导致，量级 1e-16，见 §3.1.5.6）。差异超出容差即为回归
- [ ] **S8 单卡定向**：双 UP 池定轨（`targeted` 锁定其中一张）在必中触发时该卡拿到 100%，不再按基础权重平摊（当前实测为 50/50，见 §3.7）
<!-- REVIEW-FIX-PREV: ISSUE-016 -->
<!-- REVIEW-FIX-PREV: ISSUE-012 -->
<!-- REVIEW-FIX-PREV: ISSUE-006 -->
- [ ] **S8 边界断言（ISSUE-016）**：`scope` 键缺失（无 featured 卡的稀有度、新增标准池）时保底返回恒等而非抛 `KeyError`；`scope_cards` / `featured_cards` 一律经 `.get(scope, ())` 消费
- [ ] **无 featured 卡的池 + 强制分支的边界不等价（F2，2026-10-10 补登记，强制）**：旧 `RotatingCRBehavior._force_featured`（[pity.py:584-586](gacha_simulator/core/pity.py#L584-L586)）在「池内该 scope 无 featured 槽」时把**整个 scope 的概率清零**（S5b 审查 minor 订正：清零的是 **scope 小计**，scope 外的槽位不受影响，故完整分布的 Σ 保持在 scope 外的那部分，实测 `0.2/0.2` 形状下为 `{'ssr': 0.0, 'sr': 0.051, 'r': 0.549}`、Σ = 0.6）——实测 `cr_base_rate = 1.0`、`featured_slots = {}` 时，`before_draw` 的 scope 小计为 **0**；而上一条「S8 空目标集断言」要求新形态在 `A` 为空时 `return None`（**恒等**）。两者**不等价**。旧实现的**非强制路径**因 `RotatingBehavior.before_draw` 的空集早退（[pity.py:470-471](gacha_simulator/core/pity.py#L470-L471)）恰好是恒等，**只有 CR 的强制分支例外**。**处置**：S5b 须补一条「无 featured 卡的池 + 必然拦截」的用例把它显形；若判为「旧实现的行为本身是缺陷」，则按缺口登记而非等价性断言。**当前不可达**：真实 `config.toml` 的每个池该 scope 都有 featured 卡，故不影响既有验收。
- [ ] **S8 空目标集断言（2026-10-05 补，2026-10-06 改，强制）**：`A` 为空或 `p(A) <= 0` 时 `compute_delta()` 必须 `return None`（恒等），**不得把空集传给 `transfer_linear`**（虽然后者会对 `p(A) <= 0` 返回 `None`，但「A 为空」这一语义判断留在调用方，**才能区分「机制未触发」与「触发了但目标集为空」**（**强度订正（S8-6 审查，2026-10-14）**：该理由是**可调试性主张、无可观测行为面**：审查实测删掉该调用方守卫后**全量 `2955 passed` 零红**，因为 `transfer_linear` 对空 A（`current` / `declared` 两形态）、空 Q、`p(A) = 0` 一律自守返 `None`，管道输出、状态与随机流完全同值。故**该守卫不得计入任何覆盖判据**）。触发路径：`RotatingModifier` 绑定到无 featured 卡的池。断言须覆盖 §3.1.2 表里的**每个**机制
- [x] **可交换性实测（2026-10-05 完成，脚本形态见 §3.1.5.5）**：对**旧类**（`pity.py` 现行实现）逐抽扫描，结论四条：① `soft(tf=False) + hard` **可交换**；② `hard + rotating`（rotating 非 guaranteed）**可交换**；③ `hard + rotating`（rotating **guaranteed**）**不可交换**（抽 6 起分歧）；④ `soft(tf=True) + hard` **不可交换**（该配置按裁决 7B 已不可构造，反例随之消除）。归纳判据见 §3.1.5.5 的「判据」专段（`X` 与 `hard` 可交换 ⟺ `X` 在 `hard` 的输出上恒等）
- [x] **`assign` 口径 3 实测验证（2026-10-05 完成）**：§3.9.4.2 的 `factor_override`（口径 3 + `resolve_universe`）对旧 `HardPityBehavior` 的复现程度已在**卡级**逐卡对照完毕，**6/6 场景逐位一致（差 0）**，含「更高稀有度豁免」的 U 构建路径；且**不需要**「组内比例 = 基础权重比例」不变式（扰动分布下仍一致）。口径 1 同时被排除（会把组内比例压回基础比例）。方法与数据见 §3.14.3。
- [x] **`share` 的不变式依赖边界（2026-10-05 完成）**：实测确认需要不变式的条件是「**T 跨多个 (稀有度, featured) 组**」，不是「T 是整组」。`soft(tf=True)`（T 落在单组内）在不变式破坏下仍逐位一致。§3.1.5.4 的三行表已按此修正，数据见 §3.14.3。
- [ ] **S8 口径 3 的回归断言（M2 施工，未完成）**：上两条测的是**旧类对照**。S8 落地后须把 §3.14.3 的六场景固化为测试（`tests/core/test_pity_primitives.py`），断言对象为**卡级逐卡**结果而非目标组总量（只断言总量 = 1.0 对本轮修的两处错误恒通过）
    <!-- P64-S8-CLOSURE -->
    **口径限定（S8 收口，2026-10-14）**：本行的「`A` 为空**或 `p(A) <= 0`**」两支**只对 `shape = 'current'` 的机制成立**（§3.9.5 第 1 行 / §3.1.5.6.1 的「来源二」）：「A 为空」对全部机制成立，而 `p(A) <= 0 → None` 对三个 `declared` 机制（`HardModifier(target_featured=true)` / `NonFeaturedModifier` / `SelectedModifier`）**不成立**（它们按 `w` 分配，`w(A) > 0` 时照常转移）。本行原文写于 2026-10-05/06，早于 2026-10-08 的 `declared` 裁决。
- [ ] **S8 可交换性复测（M2 口径，未完成）**：上条测的是**旧类**。S8 落地后须对**新骨架 + 卡级管道**复测同样四组，确认判据在卡级下同样成立。**关键差异面**：旧类的 `hard` 在槽位级取 `base_probabilities`，卡级下若取自 `DrawInfo.base_probabilities` 而该字段语义已由槽位级改为卡级（§3.9.3 的 `DrawInfo.base_probabilities` 行），须确认归一化后仍与旧产物一致
- [x] **`targeted` 的有效分支补测（2026-10-05 完成）**：**已改为直接对照两个 behavior 在同输入上的输出**（不经引擎，避开 `TargetedBehavior` 不走 `_active` 门控、探针无法可靠注入状态的问题）：`targeted` 的 guaranteed / fate-ready 分支与 `rotating` 的 guaranteed 分支**逐位相同**（三组输入，含 `hard` 的输出，最大差 0.00e+00），故按判据 `hard + targeted` **不可交换**。原「可交换」结论作废，原因是探针覆盖不足（详见 §3.1.5.5 判据表的注）
- [ ] **S8 差异归因清单（ISSUE-012 / ISSUE-006）**：S8 与 S5 产物的对比口径为**归一化后分布**（**口径订正（S8-6 审查，2026-10-14）**：S5a 装置的**实际**口径是**原始值逐元素**，两者在 Σ = 1 的形状上同值、Σ ≠ 1 时装置更严，见下方 (a) 的订正段；本导语与 (a) 段以装置实际口径为准并登记）；下列各项的差异**允许存在**并须逐一登记，不得当作回归——
  （a）`⟨m,p⟩ ≠ 1` 的配置（`hard` 的 scope 低于最高稀有度）：S5 输出 Σ = 1.009、S8 输出 Σ = 1，管道内可见绝对值改变（抽样分布因 `pool.draw` 的 `_adjusted_total_weight` 隐含归一化可能不变，见 §3.9.5）；**连带的观测面变更（ISSUE-903）**：`core/invariants.py` 的分布层归一性判据须同批从 scope 感知式改为恒等断言 `Σp = 1`，`tests/core/test_pity_invariant_checker.py` 的正例期望值随之更新（S8-6 ⑤）；<!-- REVIEW-R1-FIX: ISSUE-903 -->
      <!-- P64-S8-CLOSURE -->
      **量级与范围的订正（S8 收口，2026-10-14，实测）**：本行的「Σ = 1.009 → 1、量级 1e-4 ~ 3.5e-3」只覆盖了**一条**子机制。实测该类有**两条**子机制、两条上界（对比口径仍取本行规定的**归一化后分布**）：
      **(i) Σ > 1 的归一化**（旧实现的「目标集绝对赋值 + 更高稀有度豁免」造出 Σ > 1，新实现 `Σδ = 0`）：上界 `m²/(1+m)`，`m` = 更高稀有度质量。`m = 0.01` 时 **9.9e-5**（与本行同量级），`m = 0.4` 时 **0.114**。
      **(ii) `p(A) = 0` 或 `p(Q) = 0`**（新实现按 §3.9.5 拒绝转移，旧实现仍绝对赋值、**造质量**）：上界 `1/(1+m)`，实测最大 **0.714**（`p(sr) = 0` 的形状）；多硬保底链（`hard(ssr) + hard(sr)`、`soft(ssr) + hard(sr)`）下 0.5。
      **故「抽样分布因 `_adjusted_total_weight` 隐含归一化可能不变」只对 `m = 0`（scope 为最高稀有度）成立**，实测 `hard(ssr, *)` 差 0.0，而 `m > 0` 时抽样分布差 `m²/(1+m)`。本行登记的量级上界对退化形状不成立，以本注的两条式子为准。**另**：本行规定的「对比口径为归一化后分布」与 S5a 装置的实际口径（**原始值逐元素**）不一致，在 Σ = 1 的形状上两者同值、Σ ≠ 1 时装置更严，该差异一并登记。
  （b）`worst_impact` 的卡集合对齐改造（§3.9.3 专项）会改变最差影响分析数值
  （c）~~**`rotating_cr` / `rotating_cr_soft` 的分布差异 + 随机流分叉**~~ **已作废（2026-10-10，RULING-6B′）**：本项原由裁决 6B（掷骰移至 `after_draw`）立项，性质为「分布差异 + 随机流分叉」（首抽拦截概率归零 + 全局 `random` 消费位置改变）。6B′ 把掷骰相位移回 `before_draw` 的 `StreakTracker.prepare`，与旧类同相位、同条件、同消费次数，**两项差异同时消失**，故本项不再登记；`rotating_cr` / `rotating_cr_soft` 回归上方「S1–S5 口径」的逐场完全一致批次。原文本见本文件 git 历史（2026-10-09 版）。
  （d）**`boost` 的 U 由 scope 改回全池（§3.1.5.2.4 错误 ②）**：原稿把 soft 的 U 写成 scope，该形态下 soft 整体不生效（SSR 总率不变）。这是**修复**不是差异，须由 S5b 的等价性测试覆盖「soft 与旧类逐场一致」来确认——若该测试此前通过而按旧稿实现，说明测试本身有缺口，一并修
  （e）**`assign` 的目标值除以当前值（§3.1.5.2.4 错误 ①）**：同上，属修复。须新增专项断言「`hard` 的目标组内比例与旧实现一致」（不能只断言目标组总量 = 1.0，那对两处错误都通过）
  （f）**卡级还原段跳过 SR / R 的缩放（缺陷 12）——已于 2026-10-09 提前修复，本项差异随之消失**。原状：S5 的管道是「卡级 → 槽位级 → `before_draw` → **还原回卡级**」，而还原段用 `infer_rarity_from_spec` 反查槽位——该函数只认 SSR，SR / R 卡得到 `None`，缩放被跳过（[banner.py:240-247](gacha_simulator/core/banner.py#L240-L247) + [pool.py:234](gacha_simulator/core/pool.py#L234)），故喂给 `pool.draw()` 的卡级字典 **Σ > 1**（真实 `config.toml` 的 `ssr_soft` 在爬升末端实测 Σ = 1.996），采样按 `1/Σ` 稀释。**修复后 S5 与 S8 的输出一致**（同一抽次实测：修前有效 SSR = 0.5010，修后 = 1.0000 = 槽位级意图），故**本项不再是一条差异**，S8 的「对 S5 产物容差 1e-12」验收**无需为它网开一面**。**保留本条记录的目的**：若有人拿**修复之前**固化的 S5 快照作对照（例如旧 P79 golden 的父提交），会看到上述差异，那是修复而非回归。完整实测与修法见 [04-问题.md](docs/01-活跃/subsystems/保底系统/04-问题.md) 缺陷 12
  （g）**形状改变型算子经 `priority` 排在 `hard` 之前时，`hard` 的 A 侧形状与旧实现分岔（S8 收口新增，2026-10-14，实测差 0.5）**：旧实现在**槽级**对目标槽位按 `w_s / Σw`（声明权重）赋值，故 `hard(scope='ssr')` 会把前序算子（`rotating` / `targeted`）造成的形状**重置**为声明比例；S8 的 `HardModifier(target_featured=false)` 按 §3.1.2 的「A 侧形状」列取 **`current`**（保留当前比例），前序算子的效果被**保留**。实测（同 scope、`rotating` 经 `priority = 1` 排前、`hard` 的 `counter` 已达 `threshold`）：旧类原始 `{ssr_featured: 0.5, ssr: 0.5}`、M1 生产管道 `{f1: 0.5, s1: 0.5}`、S8 `{f1: 1.0, s1: 0.0}`，归一化后逐元素最大差 **0.5**。
      **性质**：**实现忠于 §3.1.2 的机制表，是机制表与旧实现分岔**，故不改实现、只登记，并在 **S8-6 新增第 ⑦ 条验收面**（当前所有验收批次都无 `priority` 覆盖，该形态**无观测面**）。**可达性**：真实 `config.toml` 无 `hard`（仅 `ssr_soft`），手册的 `hard` 全为 `scope = ssr` 且 `_BTYPE_ORDER` 下 `hard` 默认排在 `rotating` / `targeted` 之前，故**须显式写 `priority` 才可达**。**语义取向（可推翻的裁决）**：取 `current` 使前序「出金必是 UP」不被后续 `hard` 抹掉，与真实机制「继承已生效的必 UP」一致；改取 `declared` 则与旧实现逐位一致、但会重置前序形状。
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-5 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-6 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-8 -->
- [ ] **S8 跨文件同步清单（AUDIT-BREAK-5 / 6 / 8，强制）**：S8 与 S4-3 删除旧符号时，下列**同源改动点必须在同一 commit 内同步**，否则会出现「删了定义、留了引用」的 `ImportError`，或「引用指向已改名函数」的静默错值：
  - **A（删 `aggregate_probs_by_rarity` **与 `infer_rarity_from_spec`**，后者见 ISSUE-504）**：`core/banner.py`（[`draw` 内局部 import :209](gacha_simulator/core/banner.py#L209)、调用 :227、`scale_factors` 计算 :229-246、槽位取值 :242/:244）、`core/pool.py`（**两个定义**：`aggregate_probs_by_rarity` [:254](gacha_simulator/core/pool.py#L254) 与 `infer_rarity_from_spec` [:234](gacha_simulator/core/pool.py#L234)；后者的内部消费 :270/:275 随前一函数一并消失）、`core/__init__.py`（[:3](gacha_simulator/core/__init__.py#L3) 导出行 + `__all__` 同名项，**两条目**）。验收：`grep -rnE "aggregate_probs_by_rarity|infer_rarity_from_spec" gacha_simulator/ tests/` 零命中——**该零命中口径正是 ISSUE-504 把 `infer_rarity_from_spec` 由「保留」改判「删除」的直接依据**：保留函数本体则本行验收恒红。<!-- P64-S8-CLOSURE -->
      **S8-4 落地后的实际口径（2026-10-14）**：判据取 **AST 绑定引用零命中**（全库 379 个 `.py` 实测 0 处）；**文本命中允许保留**（实测 20 行，其中 3 行为负断言用例的字符串字面量）。**并订正**：S8 收口时写的「24 行全部是注释与 docstring、零代码引用」不成立，`test_pool.py` 与 `test_worst_impact.py` 各有 2 处真实代码引用，已由 S8-4 一并改造。 <!-- REVIEW-R1-FIX: ISSUE-504 --><!-- REVIEW-R1-FIX: ISSUE-001 -->
  - **B（`worst_impact` 卡集合对齐）**：`core/worst_impact.py` 第二处 `PoolPitySpec` 构造 `:543-552`（[worst_impact.py:543-552](gacha_simulator/core/worst_impact.py#L543-L552)）与槽位实参 `:549` / `:550` / `:551` 同步改（**2026-10-09 实测**：该处**无**硬编码槽位表，原引 `:512` / `:515` 实为 `from gacha_simulator.core.pity import _build_pity_state_init` 与 `pool_specs = {}`）；**`_ref_pool_entry` 的写后即读须一并处置**（[worst_impact.py:372](gacha_simulator/core/worst_impact.py#L372) 赋、[:373](gacha_simulator/core/worst_impact.py#L373) 立即读，无跨方法消费，可退化为局部变量）。**原稿此处写「[:504](gacha_simulator/core/worst_impact.py#L504) 的 `_ref_pool` 死分支」，实测该属性与分支在全库均不存在**（见 §3.9.3 的订正）<!-- REVIEW-R1-FIX: ISSUE-006 --> <!-- REVIEW-R1-FIX: ISSUE-955 -->
  - **C（`core/__init__.py` 是双重删除目标）**：S8-4 删 `_redistribute_scope` 导出，S4-3 删 10 个旧行为类与 `SoftPityMixin` 的再导出。验收：`python -c "import gacha_simulator.core as m; assert not [n for n in m.__all__ if not hasattr(m, n)]"` 通过，且 `import gacha_simulator` 无 `ImportError`
  - **D（旧类与 `_redistribute_scope` 的 `DrawInfo` 槽位字段依赖，ISSUE-901）**：S8-4 **不删** `PoolPitySpec` / `DrawInfo` 的 `scope_slots` / `featured_slots` / `card_to_slot`，**不改** `compute_scope_mappings` 的槽位产出为「只产卡集合」——旧保底类、`_redistribute_scope` 函数体与 `PityEngine` 三个 `DrawInfo(...)` 构造点仍依赖它们，删除点统一在 GATE-5 末条「发布前一次性移除旧保底类」commit。验收：S8-6 执行时 `tests/core/test_pity_equivalence.py` 的旧类侧仍能构造 `DrawInfo` 并跑出非恒等分布（若旧类侧输出退化为恒等，即槽位字段已提前消失）<!-- REVIEW-R1-FIX: ISSUE-901 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-7 -->
- [ ] **存量测试文件在删除点之前完成改造（AUDIT-BREAK-7）**：`S7d`（M1，旧类移除 commit 之前）与 `S8-7`（M2，槽位字段 / `_redistribute_scope` 删除之前）两个时点，`pytest -q --collect-only` 必须**零 `ImportError` / 零 `AttributeError`**。原稿「S4-3 后 pytest 收集期即 `ImportError`」的表述**不成立**（旧行为类在发布前的移除 commit 之前始终可 import），真实断裂点为上述**两处删除 commit**，故按两个时点分别设块。目标文件：`tests/test_pity.py`、`tests/core/test_pity_validate_behaviors.py`、`tests/core/test_pity_rotating.py`、`tests/core/test_pity_integration.py`、`tests/core/test_pity_lifecycle.py`、`tests/core/test_pity_targeted.py`

### S9（状态可见性与 G3）

- [ ] **S9 口径 · sim**（2026-10-06 改写）：**所有**保底都能读到 `ctx.sim`（非 Optional，永远填充）；`SimView.owns()` 的 `total_holding` 口径正确（含初始持有）。原内容：`reads` 声明的保底能读到对应外部状态；未声明时 `ctx.external` 为 `None`；`reads` 写未知状态源在配置加载期抛 `ConfigError`（防拼写致静默失效）
<!-- REVIEW-R1-FIX: ISSUE-404 -->
- [x] ~~**`reads` 门控无池内污染（ISSUE-404，强制）**~~（**2026-10-06 随 §3.10.2 改判删除**：门控取消，本断言失去对象）。原内容：**同池一条保底声明 `reads`、另一条不声明**时 —— 声明者的 `ctx.external` 仍为 `ExternalView`（配 `reads` 的 G3 保底实际排除已拥有卡，**非退化为恒等**），未声明者的为 `None`。判据两条：① 在 `PityEngine.before_draw` 的**同一次调用**内，池内两条保底分别断言 `external` 的可见性；② 断言 `Pity._gated_ctx` **不修改传入的 `ctx`**（调用后 `ctx.external` 仍是调用方传入的原值），实现形态为「派生一份 ctx」。**为什么单列**：`PityEngine` **每次调用**只构造一个 ctx 并在同池保底间复用（[pity.py:1274-1300](gacha_simulator/core/pity.py#L1274-L1300)；**ISSUE-926** 更正原写「每池」）<!-- REVIEW-R1-FIX: ISSUE-926 -->，就地改写 `ctx.external` 会让同池**声明者**的 G3 静默退化为恒等且无报错；原稿的 G3 用例是**单保底池**，该污染形态在验收盲区内
- [ ] **S9 口径 · StateView**：Modifier 读其他保底的键返回 default（架构上关闭，§3.10.3）；`depends_on` 的激活传播不受影响（引擎侧执行，不经过 Modifier）
  <!-- REVIEW-FIX-PREV: ISSUE-103 -->
- [ ] **`ctx.state` 通道关闭（ISSUE-103）**：`PityContext.state` 的字段注记为 `PityState`（不是 `StateView`），命名空间隔离全部由 `view` 形参承担；断言 Modifier 实现**不经 `ctx.state` 读状态键**（含自身命名空间），且 `TargetedBehavior` 原有三处 `ctx.state.get(self._name, "selected_card")` 已迁为 **`StateView(ctx.state, self._name).get("selected_card")`**（**S9-1 审查订正，2026-10-14**：原写 `view.get("selected_card")`，而 `TargetedBehavior` 没有 `view` 形参）<!-- P64-S8-CLOSURE -->
      **口径限定（强制，S9-4 落地该断言时必读）**：「`pity.py` 内 `ctx.state` 的读取点归零」**只在「状态键读取点」口径下成立**：全文件代码命中仅剩 `:604` 的 `SoftPityMixin` fork（`forked = PityContext(draw=..., current=..., state=ctx.state)`），那是**构造透传、不含任何键读取**，且该 mixin 到 GATE-5 末条才退役。**若按字面断言 `grep 'ctx\.state' pity.py` 归零，该判据恒不可达。** 建议判据：`pity.py` 内**不再出现 `ctx.state.get(`**。
      **现状依据（S9-1 审查实测）**：把 `ctx.state` 换成任何访问即抛的探针后，**11 个 registry 类型 × `before_draw` / `after_draw` 两相位共 22 次真管道调用，触达 `ctx.state` 的次数为 0**。
      **6 个真 Modifier 的机器守卫（AST 扫描）由 S9-4 落**，S9-1 不越界代落。
- [ ] **G3 专项（精确建模判据）**（**落地状态（S9-4，2026-10-14）**：①②③a③b 与「含 `initial_count`」的**引擎侧半条**已落地于 `tests/core/test_pity_integration.py::TestG3ExcludeOwned`（5 条）；**跨层半条已由 S9-5 落地**（`TestG3ExcludeOwned::test_g3_engine_and_strategy_agree_on_owned_set`；**其判据 ④ 的牙齿经 S9-5 收口补上**：原夹具未给 `resources` 使 `can_afford_batch` 恒 False，导致「策略侧 9 处整体回退后该用例仍绿」，收口补 `gacha_state.resources['gem'] = 1` 后实测「整体回退 → ④ 必红」；另判据 ③ 是 `SimView.owns` 与 `GachaState.total_holding` 的**口径同一性守卫**、**非**跨层判据，已登记）；另：**③a / ③b 是一对并列的建模假设、§3.10.4 明令「机制定稿前不得当作已定稿验收通过」**，故本步的绿只表示「两条实现的**实际行为**已被钉住」，**不是**「机制已定稿」）：崩坏3 精准补给「50 抽 UP 保护排除已拥有」——① 保底触发时已拥有的 UP 装备不被选中；② **普通抽卡仍能产出已拥有的装备**（这是与 pool 层近似的分界，必须单独断言）；③ 全部 UP 均已拥有时的行为，**两个 type 各一条断言**：**③a** `hard_exclude_owned_skip` 保底不触发、分布退化为恒等；**③b** `hard_exclude_owned_any` 目标集退化为全部 UP、仍给出一件（§3.10.4）　**③ 注（2026-09-30）：③a / ③b 是一对并列的建模假设，不是同一个待定断言的两条写法；「全部已拥有时的行为」在 §3.10.4 仍为「待确认」（零直接信源、两种倾向并存且各违背规则原文的一半），故两条在机制定稿前均不得作为「已定稿验收」通过，定稿后删去被否的一侧；①② 不受影响**
- [ ] **`GachaState.clone()` 保真（S9 附带，独立验收，2026-09-28）**：`initial_counts` 加为字段后，`clone()` 必须逐字段带上它。判据：`s2 = s1.clone()` 后 `s2.initial_counts == s1.initial_counts`（int 值浅比较）。**为什么单列**：`run_simulation` 首行即 `initial_state.clone()`（[gacha_service.py:307](gacha_simulator/service/gacha_service.py#L307)），漏带则每场模拟的 `state.initial_counts` 恒空、`total_holding` 少算初始持有、P63 溢出分档**静默**出错。本项是本次改动**唯一的真实行为风险**，且失败时不报错
- [ ] **`initial_counts` 的赋值点覆盖全部入口（ISSUE-916，强制，2026-10-01）**：推导源唯一 = `GachaService.run_simulation` 的 `_initial_counts` 现算（[gacha_service.py:310-315](gacha_simulator/service/gacha_service.py#L310-L315)），赋值点唯一 = 同函数 `clone()` 之后（[:307](gacha_simulator/service/gacha_service.py#L307) 之后；**行号订正（S9-4 审查，2026-10-14）**：实测 `state = initial_state.clone()` 在 `:316`、`state.initial_counts = _initial_counts` 在 `:333`；`batch_simulator.py` 的构造点实测在 **`:586`**（计划他处写 `:508`））。**覆盖现状**：判据 ①（直构 `GachaState` 后进 `run_simulation`）已由 **S9-2 收口**的 `tests/service/test_gacha_service.py::test_initial_count_feeds_overflow_bands` 钉住（S9-4 复核 passed、未重造）。**订正（S9-5，2026-10-15）**：该用例的夹具已由 S9-5 **改动**（`quantity_needed` 1 → 2，因迁移后「需求 1 + 初始 1」开局即达标、一张不抽、溢出无从触发），故「未重造」在 S9-5 之后不再成立；断言集合未变、判别力保留。判据两条：① **直接构造** `GachaState` 后进入 `run_simulation(_compact)` 的路径（测试 / 脚本 / `worst_impact` / `retreat_search` / `benchmarks/perf/adapters/inline.py`）同样拿到非空 `initial_counts`——显形面为 `grep -rln "GachaState(" tests/ benchmarks/` 的**全部命中文件**（实测 **17** 个，全部落在 `tests/` 下：`core::test_batch_draw` / `core::test_p69_strategy` / `core::test_resource_gain` / `core::test_state` / `core::test_stop_condition` / `core::test_strategy` / `core::test_worst_impact` / `service::test_batch_simulator` / `service::test_gacha_service` / `test_banner` / `test_config_toml` / `test_p58_milestone` / `test_p60_gacha_state` / `test_p63_overflow_integration` / `test_p79_stop_condition_matrix` / `test_resource_lifecycle` / `test_resource_lifecycle_integration`；命令 `grep -rln "GachaState(" tests/ benchmarks/ | wc -l` 即得。**2026-10-09 订正（ISSUE-007）**：原写 16，少计一个入口），若赋值点落在「构造点补传」形态则这些路径恒为空；② `batch_simulator.py:508` 的 `GachaState(...)` **不传** `initial_counts`、`:477-482` 的 `_ms_initial` 已删、`register_milestone_engine` 无 `initial_counts` 实参（[:486](gacha_simulator/service/batch_simulator.py#L486)）。<!-- REVIEW-R1-FIX: ISSUE-916 --><!-- REVIEW-R1-FIX: ISSUE-003 --> <!-- REVIEW-R1-FIX: ISSUE-953 -->
- [ ] **范围外缺口与行为变化登记（编号对应：ISSUE-922 = ①；ISSUE-921 = ②。不阻塞，2026-10-01）**：① `core/result_store.py` 的 `compute_config_hash` 保底分支读的 `PityDef.params` 自 P55 起已不存在（只有保底名进指纹），P64 新增的 `priority`（~~`reads`~~ 已取消）为**影响结果的字段**却不进指纹 → 数据集「配置: 相同/不同」判定失真（跨数据集对比结论随之失真）。**本次不改哈希**；~~须把该缺口登记进手册 §21 缺口汇总~~ **已于 2026-10-09 登记**（手册 §二十一新增的「引擎侧已知缺口（非游戏机制）」小节，编号 **E1**；与 §四 `core/result_store.py` 行同口径）；修复形态（按 `dataclasses.fields(PityDef)` 逐字段入哈希 + `tests/core/test_result_store_config_hash.py` 的 pity 用例）列为后续项；② `core/strategy_context_builder.py` 的 `inter_pool_pity_links` 在 P64 后由「恒空」转**非空**（`Pity._pools` 首次有值，键空间为全限定 `{banner_id}.{pool_id}`），当前 8 个内置策略零消费该字段 → 本期不产生行为差异，**登记为已知差异**；M2 验收时若引入消费该字段的策略，须回看本项。<!-- REVIEW-R1-FIX: ISSUE-921 --><!-- REVIEW-R1-FIX: ISSUE-922 -->
<!-- REVIEW-FIX-PREV: ISSUE-009 -->
<!-- REVIEW-FIX-PREV: ISSUE-013 -->
<!-- REVIEW-FIX-PREV: ISSUE-008 -->
- [ ] **G3 补充用例（ISSUE-009）**：配置 `initial_count` 的 UP 装备同样被视为「已拥有」并从 UP 组排除（`owns()` 为 `total_holding` 口径，含初始持有）。**并补一条口径对照用例（ISSUE-730 / ISSUE-944）**：同一配置（`initial_count > 0` 的 UP 卡）下断言**两侧结论一致，且均为「已拥有」**：引擎侧 `SimView.owns()` 为 `True`（`total_holding` 口径），策略侧**同样为 True**（2026-10-10 用户裁定迁移后，策略侧改用含初始持有的口径，见 §四 `core/strategy.py` 行）；**并加一条反向守卫**：`state.acquired` 本身**仍不含**该卡（`test_initial_count_not_prepopulated` 钉住的语义不变），即「迁移的是消费侧、不是 `acquired` 的定义」。本用例的形态随裁决由「登记差异的可见性守卫」改为「同口径等价断言」。 <!-- REVIEW-R1-FIX: ISSUE-944 -->
- [ ] **策略侧存量口径（S9-5，2026-10-10 新增）**：4 个内置策略文件的 9 处「是否已拥有」判据全部取含初始持有的口径。判据：`state.initial_counts` 非零、`state.acquired` 为空、目标 `quantity_needed` 等于初始持有时，四个策略均判「该目标已达成」（不再为该目标抽对应池）。**与上一条的分工**：上条（G3 补充用例）验**跨层一致**（引擎侧与策略侧结论相同），本条验**层内 9 处无遗漏**（逐策略覆盖），两者不可互替。
- [ ] **`sim` 的两条送达通道都填（ISSUE-013 改写，2026-10-06）**：`sim` 非 Optional，故漏填是**构造期 `TypeError`**而非运行期静默恒等。断言：① `Banner.draw` 通道与 ② `StrategyContext.get_pity_probabilities` 通道**都**构造 `ctx` 且都带 `sim`；任一通道缺参即 `TypeError`（不是「读到 None」）。原内容（`external is None` 兜底）：策略层查询路径（`StrategyContext.get_pity_probabilities` → `PityEngine.get_probabilities`，不传 `external`）对配了 `reads` 的保底**不崩溃**；若该路径不填 `ExternalView`，须**登记为已知差异**（查询分布与抽卡管道不一致），不得静默留空
- [ ] **`sim` 运行期送达（ISSUE-008 改写，2026-10-06）**：`SimView` 经两条通道抵达 `ctx`（见下条）。原内容：`reads` 经 TOML → `ConfigStore` → `pentry` → `_PityDef` → 引擎**全程保真**（配置层校验通过不等于运行期送达；链路见 §四 `service/batch_simulator.py` / `core/retreat_config.py` 两行）
<!-- REVIEW-FIX-PREV: ISSUE-033 -->
<!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order -->
- [x] ~~**`reads` 落点归属（ISSUE-GATE-dependency-order）**~~（**2026-10-06 随 §3.10.2 改判删除**：无此字段）。原内容：`PityDef.reads` 字段、`config_toml` 解析、`batch_simulator`（`pentry` / `_PityDef`）与 `retreat_config` 三处透传**同在 S9（M2）落地**；S3 的 `Pity(reads=...)` 形参在 S9 之前只接受默认空 tuple（此时无字段可注入），且 S3 不得为此改动 `PityDef`
- [x] ~~**`reads` 并集来源（ISSUE-033）**~~（**2026-10-06 随 §3.10.2 改判删除**：门控取消，无需并集汇总）。原内容：`Pity.reads` 由 `PityDef.reads` 全程抵达；`PityEngine.get_reads_for_pool(pool_key)` 返回该池各保底 `reads` 的**并集**（去重；全池未声明时为 `()`）；`GachaService` 经**该接口**（而非自行遍历保底列表）构造 `ExternalView`，空并集时不构造（`external=None`）
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-9 -->
- [ ] **`sim` 双通道送达（AUDIT-BREAK-9 改写，强制，2026-10-06）**：`SimView` 有两个互不覆盖的送达通道，必须**分别**验收：
  - **通道 A（抽卡管道）**：`GachaService` → [`banner.draw` :467](gacha_simulator/service/gacha_service.py#L467) → `PityEngine.before_draw`（**ISSUE-920：本通道无既有用例可覆盖**——实测全 `tests/` 目录下 `external` 仅命中 [tests/benchmarks/test_startup_timeline.py:282](tests/benchmarks/test_startup_timeline.py#L282) 的同名无关用例。**故须显式新增**：断言 `Banner.draw` 路径上 `PityEngine.before_draw` 收到的 `sim` 实参为 **`SimView` 实例**（`owns()` 可调用），落点 `tests/service/test_gacha_service.py`；**用例名在计划内写死为 `test_channel_a_fills_sim_view`**，验收命令 `pytest -q tests/service/test_gacha_service.py -k sim_view`，落地时先 `--collect-only` 确认收集到 ≥1 条且命中项为本步新增（该文件现零 `sim_view` 用例，零匹配的 `-k` 以 **exit code 5** 假通过；原写「断言收到**非 `None`** 的 `external`（配 `reads` 的池）」+ `-k "reads or external"`，`external` 与 `reads` 均已随 2026-10-06 的 §3.10.2 改判取消，该口径失去对象；**本句与 §七 S9-4 同口径**）<!-- REVIEW-R1-FIX: ISSUE-920 --><!-- REVIEW-R1-FIX: GATE-FAIL-6-测试策略 -->
  - **通道 B（策略查询）**：`StrategyContext.get_pity_probabilities`（[core/strategy.py:158-180](gacha_simulator/core/strategy.py#L158-L180)，经 `_pity_cache`）→ `PityEngine.get_probabilities`，**完全绕过 `Banner.draw`**；真实消费方为 [pity_reserve.py:52](gacha_simulator/strategies/builtin/pity_reserve.py#L52)。断言：两条通道都构造 `ctx` 且都带 `sim` 的池经通道 B 取到的分布与**同刻**通道 A 逐元素一致（容差 1e-12）且非退化为恒等；两通道必须共用同一 `GachaState` / `_initial_counts` 源（`ctx` 构造处 [gacha_service.py:412](gacha_simulator/service/gacha_service.py#L412)），采样时刻与 scope 口径不得各自为政。验收命令：`pytest -q tests/core/test_pity_integration.py -k channel_b`（**ISSUE-727 / ISSUE-943：原写 `-k "reads and strategy"`，而 `reads` 已于 2026-10-06 随 §3.10.2 删除**（该节「删除的符号」明列 `PityDef.reads` / `Pity.reads` / `get_reads_for_pool` / `_gated_ctx`），**实测该文件现存 12 条用例无一含这两个词，filter 零命中、pytest 以 exit code 5 假通过**；本步须按「GATE-6 的三条」在计划内**写死新增用例名**（建议 `test_channel_b_matches_before_draw`），并在落地时先 `--collect-only` 确认收集到 ≥1 条；备选佐证手段是 p79 golden 的 `pity_reserve` 组做端到端对照） <!-- REVIEW-R1-FIX: ISSUE-727 --> <!-- REVIEW-R1-FIX: ISSUE-943 --><!-- REVIEW-R1-FIX: ISSUE-009 -->
- [ ] `cr_state_probs` 含 (0,1) 中间值的用例等价性通过（随机数消耗对齐，H4）
- [ ] **计数相位（N1）**：`hard(threshold=90)` 首次 100% 出现在第 90 抽；`soft` 的 boost 起始抽数与旧实现相同
- [ ] **did_fire 统一语义（M4）**：**六类**的 `did_fire` 均等价于「本次抽卡是否让本保底回到初始状态」，与各自 `after_draw` 的重置分支严格同条件；rotating/targeted 新补的 scope 门控属增量能力，按「不在等价性范围内」单独验收
  <!-- REVIEW-FIX-PREV: ISSUE-102 -->
- [ ] **三个 `_soft` 复合类型的 M4 差异登记（ISSUE-102）**：`rotating_soft` / `rotating_cr_soft` / `targeted_soft` 的新 `did_fire` 为**「出 scope」**（该族 CounterTracker 为「触发稀有度重置抽数 counter」，hit/miss 两分支都 ResetCounter），旧经 MRO 为「出 scope ∧ is_featured / 命中定轨」——方向为**放宽**，与 §3.1.1 M4 表六行一致。断言：配 `depends_on` 时依赖方在「出 scope 但未命中」当轮即被激活；仅在配了 `depends_on` 时可见，按「不在等价性范围内」单独验收并写入差异归因清单。（§3.1.1 的 ISSUE-102 已裁定**不加 hit 门控**，**故本断言只有「出 scope」这一版**，备选分支已删除）<!-- REVIEW-FIX-PREV: ISSUE-GATE-risk-mitigation -->
- [ ] **N1 例外**：`deactivate_on_early_hit=True` 且命中时，`commit` 跳过 counter 重置，状态快照与 `get_counter()` 与旧实现一致
- [ ] **Lifecycle 增量能力单独验收**：配 `depends_on` 的事件驱动型在激活前不改分布、不更新状态（旧实现为惰性，属行为变更，不在等价性范围内）
<!-- REVIEW-FIX-PREV: ISSUE-032 -->
- [ ] **`FiniteActive` / `DependentFiniteActive` 配置接线（ISSUE-032，2026-09-27 裁决由「只验类」改为含配置；2026-09-28 两维正交修正）**：① `PityDef(max_triggers=2)` 经 `build_lifecycle` 产出 `FiniteActive(cfg, max_triggers=2)`；② `PityDef(depends_on='a', max_triggers=2)` 产出 `DependentFiniteActive(cfg, max_triggers=2)`（**两维都生效，非覆盖**）；③ TOML round-trip 保留 `max_triggers`；④ GUI 编辑 → 保存 → 重载一致；⑤ 触发 N 次后 `is_active` 为假且退役动作不改变 `commit` 语义；⑥ `DependentFiniteActive` 的退役计数**自激活后起算**（未激活期间不计数）；⑦ `max_triggers = -1` 抛 `ConfigError`
- [ ] **CR 随机数短路（H4）**：`cr_base_rate == 0` 与 `cr_state_probs` 含 0 的用例中，随机数消费次数与旧实现逐位相同
<!-- REVIEW-R1-FIX: ISSUE-402 -->
- [ ] **`should_deactivate` 的 `fired` 实参（ISSUE-402，强制）**：`Pity.after_draw` **必须**四实参调用 `should_deactivate(ctx, state, name, fired)`，`fired = self.did_fire(ctx)` 在退役判定**之前**取值。判据两条：① **端到端**——`FiniteActive(max_triggers=2)` 的 `Pity` 在**命中两次**后 `is_active` 为假，而**连续未命中 ≥ 2 抽**时仍为真（若 `triggers` 无条件累加，后者会在第 2 抽即退役，本断言必红）；② 直构 Lifecycle 显式传 `fired`（真值 / 假值两态），断言 `triggers` 只在 `fired=True` 时累加。**为什么必须端到端**：S1d 的直构单测与 S3-2 的构造期 `_active` 断言都不经过该调用行，「三实参调用」这一形态在两层验收里都不可见；若 Lifecycle 迁就三参，`triggers` 退化为「激活后的抽数」且不报错。
<!-- REVIEW-R1-FIX: ISSUE-406 -->
- [ ] **Lifecycle 属性代理完整（ISSUE-406，强制）**：四个 Lifecycle 类**都**暴露 `deactivate_on_early_hit` **与** `depends_on` 两个只读属性（由基类对 `self._cfg` 统一代理）。判据：① `AlwaysActive()` / `FiniteActive(cfg, max_triggers=1)` 实例上 `depends_on` **属性存在**（用哨兵默认值的 `getattr` 判定，不等于哨兵；缺省为 `None`）；② **用这两个类各构造一条 `Pity` 后 `PityEngine([...], …)` 构造成功**——`_build_activation_graph` 对**每条** behavior 无条件读 `lc.depends_on`（[pity.py:1214-1215](gacha_simulator/core/pity.py#L1214-L1215)），未代理即每次 `PityEngine(...)` 构造 `AttributeError`。<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->原稿只把 `deactivate_on_early_hit` 定为必须暴露的属性，实施者无从判断 `depends_on` 是否也需要。
- [ ] `rotating_inverse` preset 正确：出 UP → 下一次 SSR 必非 UP；出非 UP → 恢复基础比例（G1）
  <!-- P64-G1-GAP-REG -->
  **G1 残余缺口（2026-10-13 登记，S7c 审查裁定 B）**：本行的语义**已实现且正确**，但它覆盖的是**「连 1 次」**；手册 §5.3 的机制定义写「连歪 2 次 / 连中 2 次」，两者**不等价**，故按精确建模原则**不计入「G1 已覆盖」**。涉及 `rotating`（连中半）与 `rotating_inverse`（连歪半）**两个 preset**（二者均用 `FlagTracker` 的 `hit` / `miss` 二值翻转，其 `commit` 只做 `set()` / `clear()`、无连击计数器）。已按三渠道登记：手册 §5.4 幻塔缺口表 + §21 总缺口汇总 + `模块状态矩阵.md` 的 P64 行（另 §一 目录表已清掉「⚠️ 缺口 + ✅ 已实现」的自相矛盾）。详细机制与两条收敛路径见 §3.3 的 `P64-G1-GAP-REG` 段。
  <!-- REVIEW-FIX-PREV: ISSUE-105 -->
- [ ] **`rotating_inverse` 的类型注册（ISSUE-105）**：① `_BTYPE_ORDER['rotating_inverse'] == 3`，接线后与同 scope 的 `rotating` 同档（先后按排序键第三位 name 决定）；② `_EVENT_DRIVEN_TYPES` 含 `rotating_inverse`，故 `is_event_driven` 为真、`_validate_behaviors` 规则 3 生效——同 scope 配置 `rotating` + `rotating_inverse` 抛 `ConfigError`（**不得静默通过**）；③ 配 `depends_on` 时 `is_active` 早退对 `rotating_inverse` 生效（§3.1.3）——**ISSUE-506：该早退由骨架对全部类型无条件承担、不由 `_EVENT_DRIVEN_TYPES` 决定**，故本断言对任何类型同形，**它不构成「缺 `rotating_inverse`」的捕获面**（捕获面只有 ②）
- [ ] PityEngine 调度层**既有调用形式**不变（`before_draw`/`after_draw`/`get_probabilities` 的既有实参不变；**S9 新增必填参数 `sim`**（2026-10-06：非 Optional，§3.10.2））；`_validate_behaviors` 逻辑不变
- [ ] **接线（§1.5 裁决 1）**：概率管道顺序由 `_resolve_order` 排序键决定而非 TOML 书写顺序；独立排序视图方案下 `draw_pity_names` 输出串保持不变；固定种子基线对照完成，差异逐一归因到**敏感集合**：口径以 **§1.5 的五类清单**为准（本行原列的「含 `rotating_cr`」与「`target_featured=True` 的 soft 与 hard 共存」是其中的第 1 / 2 类，**本行原只列两类、缺第 3 / 4 / 5 类**）：① 含 `rotating_cr` 者；② `target_featured=True` 的 soft 与 hard 共存者；③ `soft + soft`（异 scope）；④ 跨 type 顺序反转且存在 `depends_on` 者；⑤ `hard` 与「在 `hard` 输出上非恒等」的算子共存（当前实例：`rotating` / `targeted` 处于 guaranteed 分支）。**本行与 §1.5 是从属关系**：§1.5 是展开清单，§3.1.5.5 是第 1 / 2 / 5 类的判据依据 <!-- REVIEW-R1-FIX: ISSUE-703 -->
- [ ] G5 priority：PityDef `priority` 字段生效，显式 priority 覆盖 type 顺序；priority 全 0 时排序结果与接线后默认序一致（当前 hard 已在 targeted 前，绝区零默认顺序已满足）
<!-- REVIEW-FIX-PREV: ISSUE-007 -->
- [ ] **priority 透传保真（ISSUE-007）**：`priority` 经 `config_toml._build_pity()`（构造 `PityDef` 在 :694；函数定义在 :612）→ `store.pity.pities` → `batch_simulator.from_config_store`（:1168-1193 的 `pentry`）→ `_build_pity_engine_from_gui`（:218-243 的 `_PityDef`）→ `create_behavior` **全程保真**；链上任一环节为**枚举式显式列举**，漏写即静默落回默认 0（同一缺口见 [retreat_config.py:123-142](gacha_simulator/core/retreat_config.py#L123-L142)） <!-- REVIEW-R1-FIX: ISSUE-953 --><!-- REVIEW-R1-FIX: ISSUE-956 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-1 -->
- [ ] **PityDef 字段枚举透传守卫（AUDIT-BREAK-1，强制）**：三处透传点均为**枚举式显式列举**（`pentry` 字典 [batch_simulator.py:1168-1193](gacha_simulator/service/batch_simulator.py#L1168-L1193)、`_PityDef(...)` 重建 [:218-243](gacha_simulator/service/batch_simulator.py#L218-L243)、[retreat_config.py:123-142](gacha_simulator/core/retreat_config.py#L123-L142)），新增 `PityDef` 字段若漏写即**静默落回默认值**。强制加一条**字段往返守卫测试**：`assert set(pentry) == {f.name for f in dataclasses.fields(PityDef)}`（`_PityDef(...)` 与 `retreat_config` 两处同口径），字段集失配即测试红。该守卫须与 S4b 的「dataclass 驱动的透传重写」**同 commit** 落地
- [ ] Lifecycle 统一：config_toml 拒绝分支已移除（S6a），事件驱动型自此可配 `deactivate_on_early_hit`。**订正（S6a 审查 F9，2026-10-13）**：本行原写「事件驱动型配置后**出 UP 即退役**」，实测**只对 `rotating` 成立**，三点实测为：`targeted` 需 `selected_card` 已被策略写入（否则 miss、`did_reset=False`、不退役）；`rotating_inverse` 的 fired 方向**相反**（M4 统一语义下其「回到初始态」是**出非 UP**）；三者行为均由 M4 统一语义一致推出、无代码矛盾，属本行措辞过窄
- [ ] GachaService 定轨流程（H1）：targeted preset 化后 `switch_epitomized_target`/`cancel_epitomized_path` 仍正常
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-4 -->
- [ ] **非抽卡动作端到端（AUDIT-BREAK-4，强制）**：`service/gacha_service.py` 有四处**同源**改动点（局部 import [:253](gacha_simulator/service/gacha_service.py#L253)、定轨识别 `isinstance` [:275](gacha_simulator/service/gacha_service.py#L275)、`selected_card` 写入 [:292](gacha_simulator/service/gacha_service.py#L292)/[:294](gacha_simulator/service/gacha_service.py#L294)）。漏改任一处**不报错但功能静默失效**（`isinstance` 恒假则 `switch_epitomized_target` / `cancel_epitomized_path` 走空分支、定轨目标永不变更）。断言必须是**端到端行为**而非符号存在性：构造 targeted 池，策略返回 `NonDrawAction(switch_epitomized_target)`，断言 `selected_card` 实际变更且后续分布随之改变；`cancel_epitomized_path` 同理
- [ ] P75 rebind：Pity 统一实现正确，跨模拟状态隔离测试通过
<!-- REVIEW-FIX-PREV: ISSUE-004 -->
<!-- REVIEW-FIX-PREV: ISSUE-005 -->
<!-- REVIEW-FIX-PREV: ISSUE-003 -->
<!-- REVIEW-FIX-PREV: ISSUE-029 -->
<!-- REVIEW-FIX-PREV: ISSUE-030 -->
<!-- REVIEW-R1-FIX: ISSUE-401 -->
- [x] ~~**`ConditionalModifier` 的 `apply` 与 `factor` 条件判定一致（ISSUE-401，强制）**~~（**2026-10-06 随 §3.14 改判删除**：包装器已取消，条件只在一处）｜原内容存档：断言两个方法的条件判定**同源且都生效**——① 条件为假时 `ConditionalModifier(...).apply(ctx, view, dist, readonly)` 返回 `None`（**恒等**），分布与不套包装器时逐元素一致；② 条件为真时返回内层结果；③ 对同一对内层 Modifier + 条件，`apply` 与 `factor` 两条路径在条件为假时**都**返回 `None`（防止只在一处判）。**为什么单列**：M1（S12-2 起至 S7）骨架调的是 `apply`（§3.1.4 骨架 / §3.1.2 历史形态），`factor` 自 S8 才引入——只判 `factor` 只会让 S12-2 至 S7 期间 preset 内全部条件包装器退化为**无条件**（hard 每抽强制 F、soft 每抽抬概率、ForceFeatured / ForceSelected 恒生效），且**不报错**；S12-2 自身的验收（「与改前的内部判断逐场一致」）与本条共同构成唯一捕获面。
- [ ] **三族 rebind 接口存在（ISSUE-029，2026-10-06 去掉包装器部分）**：对 `Pity._trackers` / `_modifiers` 与 `_lifecycle` **逐项**断言 `callable(getattr(x, 'rebind', None))`;~~`ConditionalModifier.rebind` 转发到内层 Modifier（构造一个被包裹的 Modifier，断言其内部 Counter / Flag 被重绑到新 state）~~（**2026-10-09 删，ISSUE-004：包装器已随 S12 取消，该断言的断言对象不存在**）。**同一断言扩展到方法名（ISSUE-GATE-dependency-order）**：M1 阶段对 `modifiers` 链上**每个对象**（含包装器）断言 `callable(getattr(x, 'apply', None))` **并实际调用一次**（`x.apply(ctx, view, dist, readonly)` 不抛 `AttributeError`——纯存在性断言在「`ConditionalModifier.apply` 的转发目标无 `apply`」时同样为真、捕获不到该缺口；内层 `apply` 的承载处是 §3.9.2 的 `Modifier` 基类默认实现），S8 后追加断言 `compute_delta` 亦存在（**ISSUE-008：原写 `factor`，该名经 `factor` → `delta` → `compute_delta` 两次改名后已不存在**）——三者是骨架的无守卫调用面，缺一即每个抽卡入口 `AttributeError`。**不得依赖 `hasattr` 守卫**——`Pity._rebind_state` 是无守卫调用~~，S12 落地后 preset 内的 Modifier 一律被包裹，漏转发即每次抽卡入口 `AttributeError`~~（**2026-10-09 删，ISSUE-004：包装器已随 S12 取消**；本条对「零件缺 `apply` / `rebind` / `compute_delta`」仍成立）<!-- REVIEW-R1-FIX: ISSUE-008 -->
- [ ] **preset 工厂消费 `pdef`（ISSUE-030）**：非默认 `threshold` / `scope` / `counter_init` / `guaranteed_init` / `deltas` 配置下，新 preset 与旧类**逐场一致**（每项至少一条用例）；并断言零参形态未被采用（各 `_preset_xxx` 签名含 `pdef` 形参，`create_behavior` 以 `preset(pdef)` 调用）
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-2 -->
- [ ] **构造期参数注入只限旧类分支（AUDIT-BREAK-2）**：`create_behavior` 现于 [pity.py:875-878](gacha_simulator/core/pity.py#L875-L878) 向 `params` 注入 `target_featured` / `reset`，再以 `cls(name=..., state=..., scope=..., **params)` 收尾（[:900](gacha_simulator/core/pity.py#L900)）。preset 分支**不得**透传该 `params`（`Pity.__init__` 无这两个形参）。断言：`inspect.signature(Pity.__init__).parameters` **不含** `target_featured` / `reset`，且 preset 分支构造 10 个 preset 全成功（旧类分支仍按原样注入）。⚠ 待人工裁决：备选方案为保留这两个形参并统一注入（见 §3.1.4 AUDIT-BREAK-2 条） <!-- REVIEW-R1-FIX: ISSUE-951 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-3 -->
- [ ] **preset 返回 dict 键集与消费端闭合（AUDIT-BREAK-3）**：preset 返回 dict 的键集**恰为** `{trackers, modifiers, lifecycle, flags, counters}` 五键（`create_behavior` 对未知键抛 `ConfigError`，缺 `lifecycle` 抛 `ConfigError`）；`flags` / `counters` 由 `Pity.__init__` 的新形参消费，按**真值写入**规则 `state.set(name, k, v)`（falsy 值跳过，不写状态）。断言：① 某 preset 返回 `flags={'guaranteed': True}` 后，构造完成即 `state.get(name, 'guaranteed') is True`；② 返回六键（多一键）时抛 `ConfigError`。⚠ 待人工裁决：备选方案为去掉这两个键、初值只走状态声明（H2，见 §3.1.4 AUDIT-BREAK-3 条）
<!-- REVIEW-R1-FIX: ISSUE-403 -->
- [ ] **`target_featured` 保真（ISSUE-403，强制；2026-10-09 按裁决 7B 收窄 soft 部分，ISSUE-002）**：`pdef.target_featured=True` 的 `hard` 在 preset 化后**目标集与旧类逐场一致**。判据三条：① 新 preset 的 `HardModifier` 的 `target` 取自 `_target_of(pdef)`（`True → 'featured'`，否则 `'scope'`）；② **该 scope 无 featured 卡时目标集回退 scope 全集**（对齐旧 `featured_slots.get(scope, scope_slots)`，[pity.py:286-289](gacha_simulator/core/pity.py#L286-L289)），用例须覆盖「无 featured 卡的稀有度（如 `sr`）配 `target_featured=True`」这一空集回退分支；③ `rotating` 族 preset **不得**出现 `target=`（旧实现忽略该字段，加了即语义漂移）。**该字段在旧实现中有两个消费点（`HardPityBehavior` / `SoftStepBehavior`），preset 路径若不显式承接即静默放宽为 scope 全集**——不报错，只改概率流，故本断言是唯一捕获面。**soft 一侧（`SoftStepBehavior`）的消费已按裁决 7B 从配置面移除，故「三个 counter 驱动 soft 与旧类逐场一致」不再成立、不由本条件承载**（原稿该半句与 7B 互斥，已改）：soft 侧改为**硬拒用例**——`create_behavior` 对 `PityDef(btype='soft_interval' / 'soft_additive' / 'soft_step', target_featured=True)` 抛 `ConfigError`（与 §3.2.1 落地面 ① 同源）。S5b 的 counter 驱动批次须含上述 `hard` 用例与 soft 硬拒用例各一条。<!-- REVIEW-R1-FIX: ISSUE-002 -->
- [ ] **rebind 覆盖面含 view（ISSUE-004）**：`Pity._rebind_state` 重建 `self._view`；worker 内同一 engine 连跑 N 场模拟时第 2..N 场读的是当场账本；断言 `StateView` 不缓存命名空间 dict（命名空间后创建时仍能读到）
- [ ] **同 type 两条保底状态互不影响（ISSUE-005）**：同配置下两条同 preset 保底的 Tracker / Flag / Counter **不共享实例**（preset 为工厂函数，不是模块级常量）
- [ ] **跨进程 pickle round-trip（ISSUE-003 / ISSUE-731）**：对 `env`（或 `env.pity_engine`）做 `pickle.dumps` / `loads` 断言通过——覆盖 `Pity` / `Tracker` / `Modifier` / `Lifecycle` **四族**对象（**ISSUE-731：原写「五族」含 `Condition`，该类族已随 §3.14 改判取消；实际随 env 进 pickle 的是四族**）加 **`InvariantChecker`**（`core/invariants.py`，随 `env.pity_engine` 进入每条并行路径的 pickle 图；**ISSUE-945：它的开关载体是构造形参 `enabled`、随实例进本 pickle 图，故 spawn worker 自动继承**；**GATE-check-3：本断言由 M1 末位的 S11 的专属文件承载，不在 S7b**），禁 lambda / 闭包 / 不可 pickle 成员（否则并行度静默归零，见 §四 专项） <!-- REVIEW-R1-FIX: ISSUE-731 --> <!-- REVIEW-R1-FIX: ISSUE-945 -->
- [ ] 任意 Tracker × 任意 Modifier 组合自由（新 preset 无需新类）
- [ ] `_SOFT_SUFFIX_TYPES` 处理、`SoftPityMixin`、旧 counter 驱动类退役
- [ ] GUI round-trip：preset 参数编辑 → 保存 → 重载一致；新 type **自动**出现在下拉（`_PITY_TYPES` 改为由 `BEHAVIOR_REGISTRY` 生成**是 S6a 的施工项、非既成事实**，见 §3.6；改造落地后「须手工追加」的要求随之作废，**落地前新增 type 仍须手工追加**）<!-- REVIEW-R1-FIX: ISSUE-929 -->
- [ ] pytest 全量通过
<!-- REVIEW-FIX-PREV: ISSUE-017 -->
- [ ] **文档同步（ISSUE-017 / ISSUE-028）**：`CLAUDE.md` §二「保底 (core/pity.py)」章节与扩展指南「新保底行为」一行改写（P64 后原描述失真）；`docs/00-meta/模块状态矩阵.md` 的 P64 行摘要补 G3 / S9 / S10 / S11 与 M1/M2 划分（**ISSUE-004：S12 已于 2026-10-06 取消，不进摘要**）；**子系统文档集**（目录实测六件，同步面五件）的 `docs/01-活跃/subsystems/保底系统/01-理论.md`（`§2.1` 执行顺序 / `priority`）与 `02-实施.md`（`pity.py` 行号表与 10 类清单）同步，**并补 `00-档案.md` / `03-审计.md` / `04-问题.md` 三件**（ISSUE-028 / **ISSUE-927**，已核均含 P64 相关内容的失真面，见 §四）；`docs/主流抽卡游戏卡池机制配置转换手册.md` 按 §四 登记项更新 | <!-- REVIEW-FIX-PREV: ISSUE-028 -->

### S10 / S11（保障层）

- [ ] **S10 组合正确性（§3.12）**：随机零件组合下不变式成立，归一性按 **scope 感知**口径（`Σp = 1 + Σp(被 F 豁免的更高稀有度槽位)`，无 F 参与时退化为 `Σp = 1`）——**该口径仅对 M1 槽位级管道成立；S8 起 `_apply_delta` 归一化到 `Σp = 1`，此条须随之改为 `Σp = 1`（ISSUE-903，§3.12.1 / §3.13）** / 非负性 / 增量合法性（`p + δ ≥ 0` 且在支撑上不全零） / 状态键在声明集内 / 同种子确定性；合法组合判据（同键冲突、引用不存在键、`depends_on` 成环）在构造期报出。**「状态键在声明集内」的比对集 = `Pity._declared_keys`（ISSUE-501）**，其来源是三族统一的 `state_keys()`（§3.1.1 / §3.1.2 / §3.1.3；汇总点 §3.1.4 骨架），断言须先证该汇总非空——若三族未实现 `state_keys()`，`_declared_keys` 三个元组恒空，本不变式与 §3.12.2 判据会**双双恒真通过**。**且 `_declared_keys['modifiers']` 必须含内联条件的读键**：条件内联后读键一律落在 Modifier 自己的 `state_keys()` 里（§3.14.2，**一处声明**），断言须覆盖一条「内联条件读键」用例（如 `NotOwnedModifier.compute_delta()` 内联读 `'counter'` 时，`'counter'` 须出现在该 Modifier 的 `state_keys()` 内、进而出现在 `_declared_keys['modifiers']` 中），否则「条件只在 `compute_delta()` 内读、不申报」的实现会让本不变式对条件全盲（**GATE-check-6 / GATE-FAIL-6-测试策略，2026-10-09 修正**：原写「`CounterCondition('counter', τ)` 经 `ConditionalModifier` 包裹」，该两类已随 §3.14 改判取消；本条与 §3.12.1 / §3.12.2 / §3.13 三处的现行内联口径同批对齐） <!-- REVIEW-R1-FIX: ISSUE-501 --> <!-- REVIEW-R1-FIX: GATE-FAIL-6-测试策略 -->
- [ ] **S11 不变式运行时校验（§3.13；GATE-6 补齐，2026-09-22）**<!-- REVIEW-FIX-PREV: ISSUE-GATE-6-test-strategy -->：`InvariantChecker` 可开关、生产关闭，且**对具体输入有确定的期望输出**
  - **正例**：对 `hard(scope='sr')` 的**合法**配置（§3.12.1 实测 `{ssr:0.006, ssr_featured:0.003, sr:1.0, r:0.0}`，Σ = 1.009），`check_after_before_draw` **不得报错**（归一性按 scope 感知口径）。**S8 之后该正例的期望值反转为 `Σp = 1`（ISSUE-903）**：`_apply_delta` 无条件归一化，此时若仍按 `1 + Σp(豁免槽位)` 判，同一份合法配置会从「正确」变「误报」；本文件须按里程碑两段设期望值，S8 落地时同批更新本正例<!-- REVIEW-R1-FIX: ISSUE-903 -->
  - **负例**：人为把一个卡概率改为负值、把 Σ 改到 1.2（超出 F 豁免量）、或在白名单以外写 `_active`，则**必须抛错**，且异常信息含**保底名 + 键 + 期望值 / 实际值**三要素
  - 测试文件为 `tests/core/test_pity_invariant_checker.py`（S11 专属；`tests/core/test_pity_invariants.py` 归 S10，两者被测对象不同，不得混用）
  - **原稿缺口**：S11 在 §六 无任何断言行、§七 无验收命令、§四 无专属测试文件行，而 §七 的 M1 完成标志却把它列为交付条件之一；本条与 §四 / §七 三处同步补齐
<!-- REVIEW-FIX-PREV: ISSUE-GATE-test-strategy -->


### G16（独立先行）

- [ ] `reset="never"`：hard 保底出金不重置 counter；`reset="featured"`/默认行为不受影响。**2026-10-10 订正（G16-2 实现审查）：本行原含第三个分句「每 N 抽白送保底金」，该半未验证且与本块交付的实现互斥**——`never` 下 counter 从不归零，实测（hard / `threshold=80` / `reset='never'` / 连跑 90 抽）forced 抽次 = 第 80..90 抽连续 11 抽、counter 终值 90，即「第 N 抽起**每抽**都强制」而非「每 N 抽一个」。**⚠ 待人工裁决**：该半已登记为残余缺口（手册 §5.4 幻塔缺口表 + §21 G16 行 + `docs/00-meta/模块状态矩阵.md` P64 行）；能产生周期性的候选语义是「保底**触发时**归零」，现有 `reset` 取值集合（`scope` / `featured` / `never`）无此项，故 **G16 的 ✅ 只对「出金不重置 counter」半成立**，本行不再据该半宣告覆盖
- [ ] **GUI 兜底保底条目合法（AUDIT-BREAK-1）**：`set_config`（无 `pity` 段或 `pities` 为空）合成的兜底条目，其 `type` 在 `BEHAVIOR_REGISTRY` 内、`reset` 在 G16 白名单内；`set_config({'pity': {'pities': []}}) → get_config() → load_toml` 全程不抛 `ConfigError`，且该条目的 `soft_start` / `soft_end` 取自 `pity.start` / `pity.end`（不再走嵌套 `params`）<!-- REVIEW-R1-FIX: AUDIT-BREAK-1 -->
- [ ] 手册缺口登记同步（**2026-09-18 核实：G13/G2/G14/G15/G19 已同步**）：G16 由「🔵 待 P64」（[手册:2400](docs/主流抽卡游戏卡池机制配置转换手册.md#L2400)、[手册:2400](docs/主流抽卡游戏卡池机制配置转换手册.md#L2400)）改「✅ 已覆盖」；G1 由「🔴 高优先级 · → 待 P64 状态机引擎」（[手册:2396](docs/主流抽卡游戏卡池机制配置转换手册.md#L2396)）改「🟡 P64 设计中」；G5（[手册:2409](docs/主流抽卡游戏卡池机制配置转换手册.md#L2409)）待 priority 裁决后更新
- **03-审计.md 异常 6 的关闭归属（2026-10-10 补齐）**：§1.3 第 3 条写「G16-1 落地后 `03-审计.md` 异常 6 可置为已关闭」，而 §七 G16-2 的目标文件只列三个测试文件 + 手册，不含 `03-审计.md`——该关闭动作**归 G16-1**（落地时即执行），已随 G16-1 落地关闭（异常 6 行含实测锚点：`pity.py:205-212` / `:881-882`、`config_toml.py:689-708` / `:612-639` / `:770` / `:392-437`）。本节验收门（`set_config` 无保底段 → `get_config` → `load_toml`）的**载入侧断言同期补齐**：原用例只在载入侧断言「名字还在」，而 `_pitydef_to_toml` 漏写 start/end 会让条目在重载后被 `PityEngine` 静默跳过（`behaviors` 为空表）却不报错，现断言阈值活过往返 + `'ssr_soft' in engine.behaviors`。详见「自动化审查记录」的 G16-1 实现审查条目

## 七、GATE 任务分解

<!-- P64-SELFCHECK-LANDED -->
> **统一自查结论（2026-10-15，独立子 agent，`2b46a05..HEAD` 全量）**：**47 块全部有交付**（逐块对到 commit、再对到代码符号与测试，无一缺失）；**无未自报的越界文件**（全部 P64 生产侧改动落在本计划 §四 的声明清单内；`core/strategy_context_builder.py` 与 `core/result_store.py` 确实零改动）；**计划明令不做的事一件没做**（抽核 6 处「本步零改动」全部成立）；**健康度全绿**（全量 `3023 passed / 35 skipped`、`ruff check gacha_simulator tests` 通过、`--collect-only` 3058 条零 `ImportError`/`AttributeError`、两条护栏 PASS 零漂移、CLI 冒烟跑通、`RELEASED=False`）；**回滚单元自洽**（47 块各自独立 commit，S8-1/2/3 的单 commit 与 S5b 的分批均为计划明文）。
> **本次自查的三条登记（低，只登记）**：
> **F5（声明面偏大，非交付缺失）**：`S8-4` 的声明目标含 `core/pity.py`，而 `b62c09b` 实测未改它；`S3-2` 的声明目标为 `core/pity.py`，而 `ef46c2e` 只改了测试文件（自述「补两处断言缺口」，代码在 S3-1 已落）。**两处的实际交付均无缺失**。
> **F6（`68b16c0` 改到 6 个生产文件，此前未登记）**：该 commit 是「把本次新增文本里的破折号改用冒号」的样式提交，改到 `banner.py` / `invariants.py` / `pity.py` / `pity_modifier.py` / `pity_primitives.py` / `pool.py` + 13 个测试文件；自查用 AST 比对确认**语义零变化**（唯一非 docstring 的 AST 差异是两条 assert 消息字符串）。**复核确认：非越界**，此处补登。
> **F7（清单口径）**：`S8-7` 实际改 **12 个测试文件**（本行原声明 5 个、报告登记 8 个），已在 S8-7 的 LANDED 段登记「剩余面须按实测重算」；`S7d` 声明的 `test_pity_validate_behaviors.py` 实测 **0 处需改**（该文件当时无需改造）。
> **另**：本计划 §七 的 35 个真块 checkbox 由本次自查一并回写为 `[x]`（此前只有 M2 面 13 条被勾，导致计划正本看不出「47 块已全部落地」）。

> **里程碑划分（2026-09-22，第四轮修订 ISSUE-101）**：主线子块按**验收口径**分为两段。**M1（S1a 至 S7c + S10-1 / S10-2 + S11；S12 已于 2026-10-06 整块取消，不再列入）** 证明「重构未退化」并交付带保障的统一架构，口径为「与旧类逐场一致」<!-- REVIEW-R1-FIX: ISSUE-004 -->；**M2（S8 + S9）** 做表达力扩展，口径为「与 M1 产物容差 1e-12 一致」。M1 结束是一个明确的暂停与交付点，故**不拆分为独立计划文件**（避免约 370 行的跨文件搬移与由此产生的长期引用同步成本）。
>
> ~~**S12 自 M2 调入 M1（ISSUE-101）**~~（**2026-10-06 随 §3.14 改判删除**：S12 已整块取消；此处原记「M1 由 30 块降为 28 块」为**当时**计数，此后经 S4c 新增、2026-10-09 的 S2b 取消（并入 S2a）与同轮 S2a 再细分为 S2a-1 / S2a-2，并改按逐块求和核定；**2026-10-10 再经 S1c 拆分与 S9-5 新增，当前 M1 为 30 块、总数 46 子块**，见上「共 46 子块」行）。原内容：`core/pity_condition.py` 与 `ConditionalModifier` 是 S4 的 preset 工厂与 S5 等价性测试的**直接前置**——计划全篇唯一的 preset 代码（§3.2 / §3.3 / §3.14.2）一律写成 `ConditionalModifier(ForceFeaturedModifier(_norm_scope(pdef)), FlagCondition("guaranteed"))` 形态。S12 留在 M2 会造成：M1 阶段唯一可照抄的 preset 代码引用不存在的模块与类，S4/S5 在 M1 内无法闭合，「M1 独立交付、可暂停」的定位不成立（10 个 preset 全部无法构造，等价性测试无被测对象）。
>
> **M1 内部执行顺序（强制）**：**S1a → S1b-1 → S1b-2 → **S1c-1 → S1c-2** → S1d → S2a-1 → S2a-2 → S3-1 → S3-2 → S4-1 → S4b → **S4c** → S4-2 → S4-3 → S4-4 → S4-5 → S5a → S5b → S5c → S6a → S6b → S6c → S7a → S7b → S7c → **S7d** → S10-1 → S10-2 → S11**。**S7d（存量保底测试文件改造，AUDIT-BREAK-7）排在 S7c 之后、保障层之前**：它消费 S5 的等价性结论与 S4 的新构造路径，且**必须早于「发布前一次性移除旧类」的 commit**（旧类本体移除后这批模块级 `import` 即 `ImportError`）。即先迁叶子原语（S1a）与 Tracker / Lifecycle（S1b 至 S1d），S2a-1 / S2a-2 按 §3.1.2 定稿形态实现 Modifier（条件与 A/Q 内联在类内；原 S2b 已并入本族，2026-10-09；同轮按 GATE-1 二分，见上方「细分子块表」），S3 / S4 消费该形态。**S12 已整块取消（§3.14 改判），故原「S12 随即外置、不得放在 S4 之后」的排序约束不再适用**——条件自始内联，S4 的 preset 直接写内联形态。**S4b（`priority` 字段定义 + 解析 + 三处透传）的位置在 S4-1 与 S4-2 之间**（2026-09-22 第八轮前移，GATE-3(a)）：S4-2 的构造形参 `Pity(..., priority=pdef.priority)` 要读该字段，而实测 `PityDef`（[config_store.py:150-186](gacha_simulator/core/config_store.py#L150-L186)）当前确无该字段，照前移前的原序（S4b 排在 S4-5 之后）施工即 `AttributeError`。**`build_lifecycle(pdef)` 的定义随 S1d 落地（ISSUE-GATE-3-dependency-order，2026-09-22）**：它依赖的 `LifecycleConfig`（S1a）与四个 Lifecycle 类（S1d）此时齐备，而 S4-2 / S4-3 的 preset 工厂返回 dict 已写 `lifecycle=build_lifecycle(pdef)`（§3.2 / §3.3 / §3.14.2），名字在**调用**时解析——若留到 S4-4 才定义，S4-3 的验收（「全部 10 个 preset 构造成功」）即 `NameError`；S4-4 只剩该键的校验防线与旧 `lifecycle_kwargs` 段删除（删除时机见 S4-4 任务项）。**S4c（`[[pity]]` 键契约与 `load_toml` 失败原子性）插在 S4b 与 S4-2 之间**（2026-10-09 补登，与 S4c 条目自述的「位置：S4b 之后」一致；2026-10-06 新增该块时本串漏登）：它只改 `config_toml.py` 的解析 / 加载路径与测试，不产出被消费符号，故不构成 S4-2 的前置，插在此处仅为把 `config_toml.py` 的两批编辑并批。**本轮（AUDIT-BREAK-2）追加一条强制依赖（本节顺序串之外的强制前置）**：**G16-1 是 S4-5 与 S4c 的强制前置**——S4-5 把 `PityEngine.__init__` 的构造兜底由「`logger.warning` 后跳过」改为抛 `ConfigError`（[pity.py:1162-1170](gacha_simulator/core/pity.py#L1162-L1170)），而**现存**的构造失败项就是 GUI 兜底保底条目（[config_panel.py:6544-6547](gacha_simulator/gui/config_panel.py#L6544-L6547)：`type='soft'` 不在 `BEHAVIOR_REGISTRY` 的 10 个键内，`create_behavior` 首行 `BEHAVIOR_REGISTRY[pdef.btype]` 即 `KeyError`；`reset='any_ssr'` 不在 G16-1 白名单、嵌套 `params` 会被 S4c 的未知键硬拒），该条目在 `set_config` 无 pity 段时被注入 `store.pity.pities` 与 `_pity_defs`，经 `get_config` / `_build_pity_engine_from_gui` 进引擎构造、**当前被本步要删的 try/except 静默吞掉**；S4c 的未知键硬拒踩的是同一处（未知键即嵌套 `params`）。故按本节顺序串单独施工时 S4-5 / S4c 是必红项，且 S4-5 的验收（新增单测 `test_engine_construct_failure_raises_config_error`）覆盖不到 GUI 路径（验收追加见 S4-5 条目）。<!-- REVIEW-R1-FIX: AUDIT-BREAK-2 -->
<!-- REVIEW-FIX-PREV: ISSUE-GATE-granularity -->
>
> 共 **47** 子块（**2026-10-13 由 46 增至 47**：S7d 审查发现等价性装置的三个未承接文件必须在旧类存活时固化 golden，故新增 **S7e**）：G16 独立 2 + P82 接线独立 2 + **M1 主线 31**（**2026-10-13 由 30 增至 31**：新增 S7e；**2026-10-10 按 GATE-1 粒度裁定把 S1c 再拆为 S1c-1 / S1c-2**：RULING-6B′ 给 `StreakTracker` 加了 `prepare` 实作，原 S1c ~0.7 升至约 1.0、贴住 1 人时上限，故拆为 0.7 + 0.3，主线 29 → 30 块、总数 44 → 45）（细分自原 12 步，见下方「粒度裁定」；**2026-10-09 逐块求和核定**，取代原链式记法下的「31」；**同轮 GATE-1 把 S2a 再细分为 S2a-1 / S2a-2，故主线 28 → 29 块、总数 43 → 44**）+ **M2 12**（S8-1…S8-7 + S9-1…**S9-5**；2026-10-05 曾加 S8-3b / S8-3c 两块，**2026-10-09 两块取消**，故回到 11；**2026-10-10 按 GATE-1 新增 S9-5**——`initial_count` 的存量持有口径迁移此前只有 §四 的裁决而无 §七 落点，补为独立子块，M2 11 → 12）。**G16 与 P82 接线均独立先行，不占 P64 主线，也不属任何一个里程碑。** M1 的 30 个子块与 M2 的 12 个子块均**逐块独立 commit**，回滚粒度等于任务粒度（GATE-5）。**2026-09-30 更正**：原写「共 43 子块……主线 29」三项相加仅 33，且与同文件「主线 30 个子块」冲突。**2026-10-09 注明**：该括注引用的是**当时**的历史数字（43 / 29），与本行现行的 46 / 30 无关。
>
> **执行顺序**：独立先行块 → M1 → M2。

### GATE-1 任务清单（checkbox）

#### 独立先行块（不属里程碑，可先于 M1 完成）

> **本轮（AUDIT-BREAK-2）一处例外（强制）**：**G16-1 是 M1 的 S4-5 与 S4c 的强制前置**，不属本行的「可先于 M1 完成」可选面——S4-5 把 `PityEngine` 构造兜底由「`logger.warning` 后跳过」改为抛 `ConfigError`、S4c 在 `_build_pity` 加未知键硬拒，而 GUI 兜底保底条目（[config_panel.py:6544-6547](gacha_simulator/gui/config_panel.py#L6544-L6547) 的 `type='soft'` / `reset='any_ssr'` / 嵌套 `params`）当前正被该兜底静默吞掉；不同批落地即「打开无保底段的配置后运行模拟」由静默不生效变为直接崩。理由与落点见下方「M1 内部执行顺序」行的同条。<!-- REVIEW-R1-FIX: AUDIT-BREAK-2 -->

**G16 独立先行（独立 commit，逐块预算 G16-1 ~0.6 + G16-2 ~0.4 = ~1.0 人时——GUI 需新建 reset 控件，非改下拉）**<!-- REVIEW-R1-FIX: GATE-check-1-变更粒度 -->
- [x] G16-1（**~0.6 人时**）`_should_reset` 加 `never` 分支 + **`_build_pity` 对 `reset` 增取值白名单（空串 / `featured` / 稀有度名（`[rarities].ranks` 的键）/ `never`，未知值抛 `ConfigError`）** + GUI **新建 reset 控件**（含「永不重置」）｜目标文件 `core/pity.py`（`_should_reset`）+ `core/config_toml.py`（`_build_pity` 的白名单）+ `gui/config_panel.py`（reset 控件与 GUI 兜底条目修正）。**ISSUE-928**：<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->原写「PityDef/config_toml reset 枚举」在配置层**无对应物**（`PityDef` 无该枚举、`_build_pity` 也无该白名单，见 §3.8 配套段）；改为白名单后「永不重置」与**拼写错误**（如 `'nevr'`）才可区分——否则两者经 `_should_reset` 的兜底分支（`reward_rarity == self._reset`）都恒 False、行为不可区分，而 `scope` 已有白名单防的正是这种静默失效。**AUDIT-BREAK-1（2026-10-01，同 commit 强制）**：本步在加白名单的**同一 commit** 内须修掉 [config_panel.py:6544-6547](gacha_simulator/gui/config_panel.py#L6544-L6547) 的 GUI 兜底保底条目（`type='soft'` 不在 registry、`reset='any_ssr'` 不在本白名单、`params` 嵌套致 start/end 丢失）——两处取值都踩在本次新增的硬拒面上，不同批即「提交后打开配置即崩」，处置方案与判据见 §3.8 的 AUDIT-BREAK-1 段。**验收追加**：`set_config` 无保底段 → `get_config` → `load_toml` 不抛 `ConfigError`，且修后条目在 `BEHAVIOR_REGISTRY` 内、`reset` 在白名单内<!-- REVIEW-R1-FIX: AUDIT-BREAK-1 --> **本轮（AUDIT-BREAK-2）追加**：本块是 M1 的 **S4-5 / S4c 的强制前置**（不是「可先于 M1 完成」的可选面，也不是「已完成的既成事实」）——S4-5 与 S4c 各自新增的硬拒（构造失败抛 `ConfigError` / `[[pity]]` 未知键抛 `ConfigError`）都以本块修好的兜底条目为前提；理由、失效形态与 GUI 路径的验收追加见下方「M1 内部执行顺序」行与 S4-5 条目。<!-- REVIEW-R1-FIX: AUDIT-BREAK-2 --> **2026-10-10 落地后补记（G16-1 实现审查）**：本块已落地为 commit `707cbbf`，独立审查的 6 项发现已在后续修复 commit 内收口，其中三项改变本行的验收面——① 本行「验收追加」要求的 `set_config → get_config → load_toml` 全程可用**当时只在内存态成立**（`_pitydef_to_toml` 对 `deltas is None` 的 soft_interval 漏写 start/end，重载后 `create_behavior` 抛 TypeError 并被 `PityEngine` 静默跳过，而 `load_toml` 不报错，故「名字还在」的弱断言照样绿）：已修写回侧（新增 `_write_sugar_form()`）并**把断言补到载入侧**；② 本行「与既有 `scope` 白名单同层同形态」当时有两处不对称（`reset` 不 `.lower()`、缺 map 时不跳过校验），已归一前者、有意保留后者并在 `legal_reset_values()` 的 docstring 内写明可达性；③ 03-审计.md 异常 6 的关闭**归本块**（§六 G16 已补记）。
- [x] G16-2（**~0.4 人时**）测试（hard 出金不重置 + **负例：未知 `reset` 值（含拼写错误）抛 `ConfigError`**，ISSUE-928）+ 手册缺口登记同步（**实际需改的仅 G16/G1/G5**；G13/G2/G14/G15/G19 已同步——**2026-10-10 订正**：原写「G16/G13/G2/G14/G15/G5；G19 已同步」，与同文件 §六「2026-09-18 核实」的结论及逐行实测均不符，且漏 G1）｜目标文件 `tests/core/test_pity_integration.py`（behavior 用例：hard 出金不重置）+ `tests/core/test_pity_config_toml.py`（白名单负例：未知 `reset` 值抛 `ConfigError`）+ `tests/gui/test_config_panel_pity.py`（reset 控件的 round-trip，含「永不重置」）+ 手册 `docs/主流抽卡游戏卡池机制配置转换手册.md`（G16 登记由「🔵 待 P64」改「✅ 已覆盖」）。**验收命令**：`pytest -q tests/core/test_pity_integration.py -k "never_reset"` + `pytest -q tests/core/test_pity_config_toml.py -k "reset_whitelist"`——两处过滤词须落在本步新增用例名内，落地时 `--collect-only` 确认各收集到 ≥1 条且命中项**全部为新增**（过滤词与断言对象绑定纪律见 §七 引言）<!-- REVIEW-R1-FIX: GATE-2-文件清单 --><!-- REVIEW-R1-FIX: GATE-6-测试策略 --> **2026-10-10 补记（跨块衔接，G16-1 实现审查）**：本块目标文件 `tests/gui/test_config_panel_pity.py` 内**已存在** G16-1 的 5 条兜底条目用例（`TestPityFallbackEntry`，落在该文件 262 行起的分节，含 `_reset_whitelist()` / `_engine_from_store()` 两个 helper），本块做 S6a / S7a 改造时**须避开该段不重叠**；另本块的「reset 控件 round-trip」用例须补一条**未列出取值原样保留**：G16-1 已把 reset 下拉改为按 `store.rarity_rank` 补全取值 + 未列出取值补「原样保留」项（`_pity_reset_choices()` / `_populate_reset_combo()`），原因见「自动化审查记录」的 G16-1 实现审查条目第 3 条——旧形态会把取值表外的 `reset` 静默改写成空串。**且本块不做全篇锚点刷新**（该工作单列为 G16-2 之后的收尾项）。 **2026-10-10 落地后补记（G16-2 实现审查）**：本块已落地为 commit `493611f`；独立审查的 7 项（重要 1 / 轻微 6）与本轮对 §六 G16 第 1 条的订正已在修复轮内一并收口，逐项处置见「自动化审查记录」的 G16-2 实现审查条目。其中第 1 项改变本块的验收口径——**G16 的 ✅ 只对「出金不重置 counter」半成立**，「每 N 抽白送金」半登记为残余缺口 · ⚠ 待人工裁决（见 §六 G16 第 1 条）。

**P82 接线独立先行（独立 commit，逐块预算 P82-1 ~0.3 + P82-2 ~0.8 = ~1.1 人时；见 §1.5 裁决 1）**<!-- REVIEW-R1-FIX: GATE-check-1-变更粒度 -->
- [x] P82-1（**~0.3 人时**）`PityEngine` 独立排序视图（`self._pool_order` 于 behavior 构造后预计算）+ `get_behaviors_for_pool()` 改为消费排序视图，`PoolPitySpec.pity_names` 保持 TOML 顺序不动｜目标文件 `core/pity.py`（`PityEngine.__init__` 与 [pity.py:1187](gacha_simulator/core/pity.py#L1187) 的 `get_behaviors_for_pool`；§1.5「接线实施方案」的核心改动点）。**验收口径**：本块**不设独立数值验收**——证据由 P82-2 承担（同种子重跑的逐字段对比 + `draw_pity_names` 不变断言），本块只负责接线；施工中先跑 `pytest -q tests/core/test_pity_integration.py` 确认既有用例全绿（重排视图若无接口错，该文件应不受影响）<!-- REVIEW-R1-FIX: GATE-2-文件清单 --><!-- REVIEW-R1-FIX: GATE-6-测试策略 -->
- [x] P82-2（**~0.8 人时**）基线固化 + 等价对照：接线前用固定种子跑 `config.toml` 与既有测试配置固化 `CompactResult` 快照，接线后同种子重跑逐字段对比，差异归因到敏感集合；确认 `draw_pity_names` 输出串不变。｜目标文件：生成脚本 `scripts/p82_baseline.py`（新建，沿用 `scripts/p79_baseline.py` 的 `--config` / `--seed` / `--out` 三参形态与 `sys.path` 注入写法）+ 快照目录 `tests/fixtures/p82_baseline/`（新建，每组配置一个 JSON，形态同 `tests/fixtures/p79_golden/`）+ 对照观察点落在 `tests/core/test_pity_integration.py` 的 `TestDependsOnIntegration` / `TestMultiPityCoordination`（§1.5 指定的两组重点观察对象）。**禁止**用 `scripts/p79_baseline.py` 覆盖 `tests/fixtures/p79_golden/`（那是 P79 常驻护栏的在线基线，§3.4.1.2 已明令）。**生成命令**：接线前 `python scripts/p82_baseline.py --config gacha_simulator/config/config.toml --seed 42 --out tests/fixtures/p82_baseline`；**验收命令**：接线后同种子重跑，逐字段对比（差异须逐一归因到 §1.5 的五类敏感集合），并断言 `draw_pity_names` 输出串不变<!-- REVIEW-R1-FIX: GATE-2-文件清单 --><!-- REVIEW-R1-FIX: GATE-6-测试策略 -->

#### M1：核心重构与保障（S1–S7 + S10 + S11；S12 已于 2026-10-06 取消）

**主线：Tracker + Modifier 统一骨架（30 个子块逐块预算，合计 17.35 人时；每块独立 commit。2026-10-09 S2b 取消、并入 S2a，同轮按 GATE-1 把 S2a 再细分为 S2a-1 / S2a-2，并改按逐块求和核定，取代原链式记法）**
<!-- REVIEW-FIX-PREV: ISSUE-GATE-granularity -->

> **粒度裁定（2026-09-22，ISSUE-GATE-granularity）**：原 12 步主线中至少 7 步的实作量明显超过 1 人时（S1 同时新建 Tracker 家族 + Lifecycle 并迁出叶子原语；S4 同时改 registry schema、10 个 preset、deltas 归属与构造兜底；S6 同时做 G1 + G5 + H1 + H3 四件事），按该粒度派工无法保证「每步一轮内可验收」。故按**可独立验收的最小单元**细分，并给每个子块补 **目标文件 + 人时预算 + 验收命令**。原「~10 人时」为按 12 步粗估，未计入 S12 与保障层细目（**2026-10-09：S12 已于 2026-10-06 取消，本句按当时口径保留**）；本表逐块预算汇总后为 **约 16.6 人时**（差异来自细分后每块的构建与验证开销；**2026-09-22 第八轮按细分后的 29 块重新逐块汇总**，当时记为 16.4，**2026-10-09 按 ISSUE-005 订正为 16.6**——原记未回写 S4-4（0.3 → 0.7）与 S7a（0.4 → 0.6）的块内上调；**本段一律以逐块求和为准**，见下方「计数与预算的核定方法」行，故原「⚠ 待人工裁决」的估算口径争议随之解除）<!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->
>
> **每块独立 commit（强制）**：S1a 至 S11 的每个子块各产出一个 commit（前缀与改动性质一致：`refactor:` / `feat:` / `test:` / `docs:`），使**回滚粒度与任务粒度一致**（GATE-5）。原稿只有 G16 与 P82 标了独立 commit，主线整体一次回滚，导致单块失败只能整体回退。
>
> **第八轮细分定稿（2026-09-22）**：贴住或超过 1 人时上限的子块再细分，细则如下（每块仍各自独立 commit，回滚粒度等于子块粒度）：
>
> | 原块 | 原预算 | 细分后 | 预算 | 细分的理由 |
> |---|---|---|---|---|
> | S1b | ~1.0（贴上限） | S1b-1 CounterTracker / S1b-2 FlagTracker | 0.6 / 0.4 | 双段 N1 相位与翻转语义是两类被测对象，单测红时的归因方向不同 |
> | **S1c**（**2026-10-10 再细分**，GATE-1） | ~0.7（RULING-6B′ 给 `StreakTracker` 新增 `prepare` 实作后升至约 1.0，贴住上限） | S1c-1 `StreakTracker`（含 `prepare` 实作）/ S1c-2 `FateTracker` | 0.7 / 0.3 | 掷骰段（相位、四条不消耗路径、下标裁剪、flag 每抽无条件写、两条守卫）是 6B′ 的全部新增面，归 `StreakTracker`；`FateTracker` 是独立保底类型，与掷骰段无共享断言 |
> | S3 | ~1.2（超限） | S3-1 统一骨架 + rebind + `_pools` / S3-2 生命周期顺序与视图接线 | 0.7 / 0.5 | 骨架可独立构造并验收（构造期无 `AttributeError`），退役顺序与 `_active` 写入属另一类断言 |
> | ~~S12~~ | ~~~1.5~~ | **2026-10-06 取消**（§3.14 改判），原 S12-1 / S12-2 共 ~1.3 人时从 M1 扣除 | — | 原行：Condition 类族 / `ConditionalModifier` + 去内部判断 | 0.6 / 0.7 | 原 S12-3（`InterceptModifier` 保持内部判断）折入 S12-2；原 S12-4 验收成为 S12-2 的验收项 |
> | S11 | ~0.6 | 不细分（预算改 0.8） | 0.8 | 增补专属测试文件与验收命令（GATE-6） |
> | S4b | ~0.3 | 不细分（预算改 0.4） | 0.4 | 增补 `PityDef.priority` 字段定义与 `config_toml` 解析（GATE-3(a) 前移），且位置移到 S4-2 之前 |
> | S6b | ~0.5 | 不细分（预算改 0.4） | 0.4 | 字段定义移出，只留 `_resolve_order` 排序键与 GUI 控件 |
> | **S2a**（**2026-10-09 再细分**，GATE-1） | ~1.2（超 1 人时上限；系原 S2a 0.8 + 原 S2b 0.4 合并所致） | S2a-1 `Modifier` 基类 + `_lower_rarities` + `HardModifier` / `SoftModifier`（**转移量语义族**）/ S2a-2 `RotatingModifier` / `NonFeaturedModifier` / `SelectedModifier` / `NotOwnedModifier`（**目标集语义族**） | 0.6 / 0.6 | 原 S2b 的拆分依据（「解析对象不同」）随 A/Q 内联消失，改用**转移量口径 vs 目标集口径**作新依据：前者错则 Σ 静默偏移（数值错），后者错则目标集静默放宽或退化恒等（语义错），两类失败归因方向相反；§3.1.2 机制表天然按此二分，两族各自可独立构造与单测。合计 1.2 不变 |
>
> **表中预算的时点（2026-10-10 补注）**：各行记的是**该轮细分定稿时**的值；若条目此后又作上调，以条目自述与「主线」汇总行为准，**不得据本表反推现行预算**。**现行值与本表的差异**：`S1b-1` 0.65 / `S1b-2` 0.45（本表记 0.6 / 0.4，2026-10-10 随 `prepare` 上调）、`S3-1` 0.85（本表记 0.7，同轮上调）、`S1c-1` 0.7 / `S1c-2` 0.3（本表即现行值）。
>
> 上述增减相抵，主线合计 **17.75 人时 / 31 块**（**2026-10-13 由 17.35/30 增至 17.75/31**：S7d 审查新增 S7e ~0.4 人时；**2026-10-10 上调 +0.75**，RULING-6B′：`S1b-1` 0.6→0.65、`S1b-2` 0.4→0.45、`S3-1` 0.7→0.85、`S5b` 0.8→0.9、`S5c` 0.7→0.8、`S1c` 拆为 `S1c-1` 0.7 + `S1c-2` 0.3）（**2026-10-09 订正**：原记 16.4 与本节「逐块求和」口径冲突，系 S4-4 / S7a 的块内上调未回写所致；**本段其后的「新增 S7d ~0.5 人时」「新增 S4c ~0.8 人时」两句系历史记录，两块早已含在 16.6 内，不得再累加**，方法见下行）<!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->；**本轮（AUDIT-BREAK 修复）新增 S7d「存量保底测试文件改造」~0.5 人时**（AUDIT-BREAK-7，原计划该批文件无任何子块承接）；**2026-10-06 新增 S4c ~0.8 人时**；**2026-10-09 核定**：S2b 取消（并入 S2a），其 0.8 中 0.4 并入 S2a-1 / S2a-2、0.4 扣除（S2a 随后按 GATE-1 再细分为 S2a-1 0.6 + S2a-2 0.6，合计 1.2 不变）；**同轮按 ISSUE-005 把 S4-4（0.3 → 0.7）与 S7a（0.4 → 0.6）的块内预算调整回写入求和行**，主线为 **29 块 / 16.6 人时**；**2026-10-10 按 RULING-6B′ 调整为 30 块 / 17.35 人时**。
>
> **⚠ 计数与预算的核定方法（2026-10-09，强制）**：以下各数一律改为**逐块预算直接求和**（汇总 §七 各顶层任务行的 `~X 人时`），**不再沿用「+X 人时」的链式累加**。原链式记法（16.4 → +S7d 0.5 → +S4c 0.8 → 17.7）与块清单自相矛盾：**16.4 本身已含 S7d 与 S4c**（该值随后又按 ISSUE-005 订正为 16.6——S4-4 / S7a 的块内上调未回写；**逐块求和的现行结果见下行实测**），故 17.7 把这两块**重复计入一次**，虚高 1.3 人时。块数口径 = 顶层任务行数 + 1（S10 拆为 S10-1 / S10-2 两块计入）。**实测（2026-10-09；此处记的是该轮时点值，逐块清单随 RULING-6B′ 与 S9-5 已变，现行值见 §七 主线汇总行）**：主线 28 行 / 16.6 人时（口径下 29 块）——S1a 0.3 / S1b-1 0.6 / S1b-2 0.4 / S1c 0.7 / S1d 0.8 / **S2a-1 0.6** / **S2a-2 0.6** / S3-1 0.7 / S3-2 0.5 / S4-1 0.5 / S4b 0.4 / S4c 0.8 / S4-2 0.6 / S4-3 0.8 / S4-4 **0.7** / S4-5 0.2 / S5a 0.8 / S5b 0.8 / S5c 0.7 / S6a 0.7 / S6b 0.4 / S6c 0.4 / S7a **0.6** / S7b 0.3 / S7c 0.5 / S7d 0.5 / S10 0.9 / S11 0.8。**2026-10-09 订正（ISSUE-005）**：本轮把 S4-4 与 S7a 两块此前只写在块内、未回写到本行的预算调整补入——S4-4 的块内自述「本步预算 0.3 → 0.7 人时」与 S7a 的「本步预算 0.4 → 0.6 人时」原先与求和行相反（同一块内两处自述互相矛盾，且都与本行不同，与 2026-10-09 已为 S9-2 处理过的「下调未回写」同源）；现按**块内条目为准**（同 S9-2 的先例）取值，故 M1 合计由 16.0 改为 **16.6 人时**。 **全量预算口径（GATE-check-1，2026-10-09 补，强制）**：本节的三个求和覆盖**互不重叠**的范围，不得互相替代、更不得只取其中之一当全量——**独立先行 4 块合计 2.1 人时**（G16-1 0.6 + G16-2 0.4 + P82-1 0.3 + P82-2 0.8；两块均不属任何里程碑）+ **M1 17.35**（30 块）+ **M2 7.1**（12 块）= **全计划 46 块 / 26.55 人时**（**2026-10-10 更新**：原记 16.6 / 6.7 / 44 块 / 25.4 是 RULING-6B′ 与 S9-5 之前的时点值）。此前把「M1 + M2」两串相加（23.3）当作全量，会让独立先行 4 块**落在预算之外**（G16-1 / G16-2 原只有组标题的「~1 人时」、P82-1 / P82-2 原连组级预算都没有，P82-2 的实作面（新建 `scripts/p82_baseline.py` + 两组快照生成 + 逐字段对照 + 差异归因到五类敏感集合）更无法判定是否 ≤1 小时）；本轮已为这 4 块补块级预算并纳入本口径。<!-- REVIEW-R1-FIX: GATE-check-1-变更粒度 -->
>
> **M2 子块预算（第八轮补，GATE-1；本轮按 AUDIT-BREAK-7 追加 S8-7 后更新；2026-10-09 重新核定 S8 与 S9）**：**S8 合计 4.0 人时**（S8-1 0.5 / S8-2 0.4 / **S8-3 0.7** / S8-4 0.8 / S8-5 0.6 / **S8-6 0.6** / **S8-7 0.4**）；**S9 合计 3.1 人时**（S9-1 0.5 / **S9-2 0.6** / **S9-3 0.9** / **S9-4 0.7** / **S9-5 0.4**，末项 2026-10-10 新增）；**M2 合计 7.1 人时**。**⚠ 核定方法同 M1（2026-10-09）**：一律逐块求和。**S9 的旧记 2.9 与块清单不符**——S9-2 条目自述「2026-10-06 由 0.8 下调至 0.6」，而下调未回写到本汇总行，故旧记多算 0.2（旧表照抄 0.8），现按条目 0.6 计，S9 = 2.7。**2026-10-09 重新核定（原 S8-3b / S8-3c 两块取消）**：S8-3b（0.5）承载的「`factor_override`（assign）原语」随 §3.9.4 合并为 `transfer_linear` 而不存在——其三条纪律中 ①② 由规格（§3.1.2 表 + §3.9.4 的 `declared` 分支）承担、③ 由 `transfer_linear` 的守卫与各类早退承担，**实现面 0.2 并入 S8-3、验收面 0.3 并入 S8-6**；S8-3c（0.4）承载的「六类合并为 `TransferModifier`」被 §3.1.2 的现行形态（一机制一类）否决，**0.4 全部释放、无工作并入他块**。净减 0.4。**2026-10-05 记录**：当时 S8 由 3.5 增至 4.4，新增上述两块。**2026-09-30 更正**：原表记 S9-3 为 0.5，与 S9-3 条目自述的 0.7（2026-09-28 因增 type 注册而上调）不一致，本次一并按条目为准对齐；S9-3 再随 G3 双实现与关于页两处上调至 0.9，S9-4 随 `tests/gui/test_about_dialog.py` 上调至 0.7。M2 亦**逐子项独立 commit**，回滚粒度为子项（依赖闭包规则见 GATE-5）。**全量预算口径见上行「计数与预算的核定方法」**——M2 的 7.1 与 M1 的 17.35、独立先行的 2.1 三方相加（26.55）才是全计划预算，本节只登记 M2 一段。<!-- REVIEW-R1-FIX: GATE-check-1-变更粒度 --><!-- REVIEW-FIX-PREV: ISSUE-GATE-1-granularity --><!-- REVIEW-FIX-PREV: AUDIT-BREAK-7 -->
>
> **验收命令与断言对象绑定纪律（GATE-6，2026-10-01 强制，GATE-6-测试策略）**：全篇凡带 `-k` 过滤的块级验收命令，必须同时满足三条，缺任一条则**不作为验收依据**：① **计划内写死用例名**（或写明过滤词须落在新增用例名内）。只给过滤词而不约束命名，等于把「命令是否命中」交给实施者临场决定；② **落地时确认收集到 ≥1 条**（`pytest --collect-only` 或首跑输出）。零命中时 pytest 以 **`exit code 5`（no tests ran）结束**，会被误读为通过；③ **命中项不得全为既有用例**。过滤词若命中既有用例（如在旧函数的测试上做子串匹配），会出现「退出码 0、全绿、新物零覆盖」的假验收。**ISSUE-920 是①③的首个实例**（S9-4 原写「既有 `-k external`」而该文件零 `external` 用例）；**本轮按同一口径处置 S8-3 / S8-5 / S10-2 三处**（逐处标注见对应子块），其余带 `-k` 的命令（S5c / S8-6 / S9-1 / S9-3）已按②补收集守卫。**合规范例 = S4-5**：`-k engine_construct` 已写死新增用例名 `test_engine_construct_failure_raises_config_error`，命中无疑（该条无需改动）。

- [x] **S1a 叶子原语层迁出**（~0.3 人时）｜目标文件 `core/pity_primitives.py`（新增）+ `core/pity.py`（re-export）。**本轮（AUDIT-BREAK-10）目标文件追加 `core/config_toml.py` + `tests/core/test_pity_config_toml.py`**（原清单只列上述两个文件，而本步的两条必红断言落在后者的 `TestDuplicatedConstants` 与前者 `config_toml` 的同名拷贝上，详见下行与验收命令行）<!-- REVIEW-R1-FIX: AUDIT-BREAK-10 -->
<!-- REVIEW-FIX-PREV: ISSUE-002 -->
<!-- REVIEW-FIX-PREV: ISSUE-019 -->
  - 迁出 `Counter` / `Flag` / `PityState` / `DrawInfo` / `PityContext` / `LifecycleConfig`，`pity.py` 保留 re-export（§3.1.6）
  - `_SOFT_TYPES` / `_HARD_TYPES` / `_EVENT_DRIVEN_TYPES` 由 `CounterBasedBehavior` 类属性升为**模块级常量**（ISSUE-024）；`_EVENT_DRIVEN_TYPES` **内容须追加 `rotating_inverse`**（不是原样迁移），`_BTYPE_ORDER['rotating_inverse'] = 3` 同批落地（ISSUE-105，见 §3.3）
  - **本轮（AUDIT-BREAK-10）本步的两条必红面必须同 commit 处理（强制）**：`tests/core/test_pity_config_toml.py` 的 `TestDuplicatedConstants`（[:477-487](tests/core/test_pity_config_toml.py#L477-L487)）断言 `config_toml._SOFT_SUFFIX_TYPES` / `._EVENT_DRIVEN_TYPES` 与 `CounterBasedBehavior` 的两个同名类属性相等，而本步同时改动两侧的可读面，**两种做法都有害**：① 删掉类属性则该测试 `AttributeError`（且 [pity.py:140](gacha_simulator/core/pity.py#L140) 的 `self.is_event_driven = btype in self._EVENT_DRIVEN_TYPES` 一并断）；② 保留类属性但不同步 `config_toml` 的拷贝则 `_EVENT_DRIVEN_TYPES` 两侧不等（pity 侧本步起含 `rotating_inverse`，而 `config_toml` 侧拷贝不含，该拷贝的消费分支 [config_toml.py:686-691](gacha_simulator/core/config_toml.py#L686-L691) 要到 S6a 才删），等值断言失败。**定稿（保守，不弱化任何既有断言）**：**三个类属性保留为模块级常量的同对象别名**（`CounterBasedBehavior._SOFT_TYPES = _SOFT_TYPES` 等三项，不是「原样保留旧内容」的双真相源），**并在同一 commit 把 `config_toml` 的同名拷贝 `_EVENT_DRIVEN_TYPES`（[config_toml.py:1684-1685](gacha_simulator/core/config_toml.py#L1684-L1685)）补上 `rotating_inverse`**。该补写的副作用只有一条：S6a 之前「`rotating_inverse` + `deactivate_on_early_hit`」也走 H3 硬拒——与 S6a 之后的语义一致（该类型是事件驱动型），且无任何断言其内容。`_SOFT_SUFFIX_TYPES` **不在本步迁移面内**（两侧内容本已相同，[pity.py:859](gacha_simulator/core/pity.py#L859) 的 `create_behavior` 局部常量仍取该类属性），不受影响。**不得删这两条断言、也不得改成「剔除 `rotating_inverse` 后相等」**——两种做法都会让这份防漂移守卫失去检测力。同 commit 更新该测试类的 docstring（其现文写「P64 计划要把它们升为 `pity_primitives.py` 的模块级常量（未实施）」，本步后已不成立）<!-- REVIEW-R1-FIX: AUDIT-BREAK-10 -->
  - ~~同批给 `Pity` 补 `_pools`~~ **已移出本步，归 S3-1**（2026-09-22 第八轮，ISSUE-GATE-dependency-order）：`Pity` 类要到 S3 才新建，本步无处可补（ISSUE-019 原文写「S1/S3」，现写死为 S3-1）。本步期间 `_build_activation_graph` 的池交集警告对每条 `depends_on` 恒真触发，属**已知过渡态**、不是回归，S3-1 落地后恢复语义（§3.12.2）
  - 验收命令：`python -c "from gacha_simulator.core.pity import Counter, Flag, PityState, DrawInfo, PityContext, LifecycleConfig"` 并且 `pytest -q tests/test_pity.py`；**本轮（AUDIT-BREAK-10）追加**：`pytest -q tests/core/test_pity_config_toml.py -k "soft_suffix_types_match or event_driven_types_match"`——本步改写了这两条断言的**被测侧**（pity 侧常量的存放位置 + `config_toml` 同名拷贝的内容），故命中即本步的验收面；落地时以 `--collect-only` 确认各收集到 1 条（零命中时 pytest 以 **exit code 5** 假通过，纪律见 §七 引言）<!-- REVIEW-R1-FIX: AUDIT-BREAK-10 -->
- [x] **S1b-1 CounterTracker**（~0.65 人时；**2026-10-10 上调**：Tracker 协议新增 `prepare` 空实现）｜目标文件 `core/pity_tracker.py`（新增）
<!-- REVIEW-FIX-PREV: ISSUE-301 -->
  - 实现 §3.1.1 的 **N1 双段接口**：`advance` 仅供 `CounterTracker` 在 `before_draw` 推进
  - `commit` 落重置，且须处理 `deactivate_on_early_hit` 的跳过重置例外（`commit(skip_reset=)`）
  - 实现 counter 家族的 **M4 `did_reset`**（统一为「本次是否回到初始状态」；`featured` 分支保留无 scope 门控的不对称）
  - 验收命令：N1（`hard(threshold=90)` 首次 100% 出现在第 90 抽）+ counter 家族 `did_reset` 语义单测
- [x] **S1b-2 FlagTracker**（~0.45 人时；**2026-10-10 上调**：同 S1b-1）｜目标文件 `core/pity_tracker.py`
  - `FlagTracker(judge, hit, miss, flag)` 的 `commit` 落**翻转**（rotating 的二态翻转、targeted 的锁定命中）
  - 实现事件驱动家族的 **M4 `did_reset`**（`guaranteed` 翻转 / `selected_card` 命中两形态）
  - 验收命令：FlagTracker 翻转与 `did_reset` 单测（rotating / targeted 两族各一条）
  - **为何把 S1b 一分为二（GATE-1）**：S1b 原为 ~1.0 人时，贴住 1 人时上限；且 CounterTracker（双段 N1 相位 + `skip_reset` 例外）与 FlagTracker（翻转语义 + 事件驱动 `did_reset`）的被测对象与失败归因方向不同，合为一块时单测红无法定位到哪一族
- [x] **S1c-1 StreakTracker**（~0.7 人时；**2026-10-10 按 GATE-1 粒度裁定拆分**，原 S1c ~0.7 → S1c-1 0.7 + S1c-2 0.3）｜目标文件 `core/pity_tracker.py`。**本块含 RULING-6B′ 的 `prepare` 实作**：掷骰段（四条不消耗路径 + 下标裁剪 + flag 每抽无条件写 + `guard_flag` / `readonly` 两条守卫），`commit` 收窄为只更新 `cr_counter`
- [x] **S1c-2 FateTracker**（~0.3 人时）｜目标文件 `core/pity_tracker.py`
  - `StreakTracker` 的 `cr_counter` **不适用 `advance`**（§3.1.1 N1 显式例外），独立单测覆盖
  - `FateTracker` 的累积与阈值分支
  <!-- REVIEW-R1-FIX: ISSUE-407 -->
  - **`NamespaceTracker(namespace)` 新增（ISSUE-407）**：Tracker 族的第五个成员，语义为空（`advance` / `commit` / `did_reset` 全 no-op、不声明任何状态键），唯一作用是声明命名空间（供三个 `_soft` 类型的 preset 产出 `X_soft`，§3.10.3 配套 1）。单测断言三方法 no-op、且构造后 `state` 中**不新增**任何键（只有 `Lifecycle.initialize` 会写 `X_soft._active`）
  - 验收命令：H4 随机数消费次数在短路条件下与旧实现逐位相同
- [x] **S1d Lifecycle 五方法族 + `build_lifecycle` helper**（~0.8 人时）｜目标文件 `core/pity_tracker.py` + `core/pity.py`
<!-- REVIEW-FIX-PREV: ISSUE-301 -->
  - `AlwaysActive` / `FiniteActive(cfg, max_triggers=…)` / `DependentActive(cfg)` / `DependentFiniteActive(cfg, max_triggers=…)` 以 `LifecycleConfig` 为**构造参数袋**（共用基类持 `self._cfg`）；<!-- REVIEW-R1-FIX: ISSUE-406 --> **`deactivate_on_early_hit` 与 `depends_on` 两个属性一律由基类对 `cfg` 统一代理**（§3.1.3；**不得只代理前者**——`_build_activation_graph` 对每条 behavior 读 `lc.depends_on`（[pity.py:1214-1215](gacha_simulator/core/pity.py#L1214-L1215)），未代理即每次 `PityEngine(...)` 构造 `AttributeError`；<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->原稿「`depends_on` 由 `DependentActive` 同源读出」已废止）
  - 三族实现**五方法**协议：`initialize` / `is_active` / `should_deactivate` / `deactivate` / `rebind`（§3.1.3），其中 **`initialize(state, name, namespaces=())` 与 `rebind(state, name, namespaces=())` 的实参面必须对称**（**ISSUE-917**：为 `name` 与 `namespaces` 各持一个 `_active` Flag、逐个重绑；只重绑 `name` 则 `X_soft` 的 Flag 在 worker 内连跑第 2..N 场时仍指上一场 state），`deactivate` 只清 `name`。<!-- REVIEW-R1-FIX: ISSUE-917 -->；`depends_on` 引用不存在名须抛 `ConfigError`。<!-- REVIEW-R1-FIX: ISSUE-407 --> **`initialize` 的签名定为 `initialize(state, name, namespaces=())`**（`namespaces` = 本保底声明的零件命名空间集合，由 `Pity` 收集后传入）：`AlwaysActive` / `FiniteActive` 对 `name` 与其中每个命名空间各写 `_active = True`，`Dependent*` 仍为空实现；`deactivate(state, name)` 只清默认命名空间（§3.10.3 配套 2）。另三族统一的 **`namespace` 属性**（默认 `None`）在本步一并落到 Lifecycle 上。<!-- REVIEW-R1-FIX: ISSUE-402 --> **`should_deactivate(ctx, state, name, fired)` 为四实参**——单测直构 Lifecycle 时须显式传 `fired`（真值 / 假值两态各一条），并另有一条**经 `Pity.after_draw` 的端到端断言**覆盖调用形态（否则该调用行无验收面）
  - **新增模块级 helper `build_lifecycle(pdef)`（写 `core/pity.py`，ISSUE-GATE-3-dependency-order，2026-09-22）**：`pdef.depends_on` 非空 → `DependentActive(LifecycleConfig(…))`，否则 `AlwaysActive(LifecycleConfig(…))`，`deactivate_on_early_hit` 一并带入（代码与逐行对照见 §3.1.3 定稿段）。**必须在 S4-2 / S4-3 之前落地**：那两个子块的 preset 工厂返回 dict 写 `lifecycle=build_lifecycle(pdef)`，而它们排在 S4-4 之前，晚定义则 S4-3 的 preset 构造验收即 `NameError`。**全库只能有一处定义**（`core/pity.py` 模块级），S4-4 不重复定义。<!-- REVIEW-FIX-PREV: ISSUE-GATE-3-dependency-order -->
  - 验收命令：`FiniteActive` 触发 N 次后 `is_active` 为假且退役动作不改 `commit` 语义（ISSUE-032）；`build_lifecycle` 按 §3.1.3 的**四组合取值表**（`depends_on` 空/非空 × `max_triggers` 0/正）逐行单测
**S2a Modifier 家族（一机制一类）+ `Modifier` 基类 + A/Q 内联解析——2026-10-09 按 GATE-1 再细分为 S2a-1 / S2a-2**（原块 ~1.2 人时）｜目标文件 `core/pity_modifier.py`（新增，两块续写同一文件）。**2026-10-09 范围与预算重新核定**（原注「本任务的范围与预算须按新形态重新核定」的落地）：本块由原 S2a（基类 + 六类）与原 S2b（目标解析器族）**合并**而来。理由：新形态下「条件 / A / Q / 转移量 / A 侧形状」全是各类方法体内的局部量（§3.1.2「五样都是 `compute_delta()` 方法体内的局部量」），解析器族作为**独立文件与独立契约面不复存在**（`resolve_universe` 全库无对应物，§3.10.4 已记「不再需要 `resolve_universe`」）。预算 **1.2 = 原 S2a 0.8 + 原 S2b 0.4**：只并入原 S2b 的 A/Q 计算与 `_lower_rarities` 内联化；其余 0.4 从 M1 扣除（五个命名解析器与 `resolve_universe` 的独立契约面消失，只剩计算逻辑本身）。**再细分（2026-10-09）**：本块随即按**转移量口径 vs 目标集口径**二分——S2a-1（0.6 人时）与 S2a-2（0.6 人时），合计 1.2 不变；依据与理由见下方「细分子块表」的 2026-10-09 行<!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->
- [x] **S2a-1 `Modifier` 基类 + `_lower_rarities(ctx, scope)` + `HardModifier` / `SoftModifier`（转移量语义族）**（~0.6 人时）｜目标文件 `core/pity_modifier.py`（新增；S2a-2 续写同一文件）<!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->
  - **M1 期方法名为 `apply(ctx, view, dist, readonly) -> 分布`**（§3.1.2 / §3.9.2 的两期分工），S8 起改实现 `compute_delta(view, dist, ctx) -> 增量向量`（§3.9.2）。本步按 §3.1.2 定稿形态实现，**触发条件与 A/Q 一律内联在各类方法体内**：不写外置条件类族（S12 已取消）、不写解析器族（原 S2b 已并入本族）。该定稿为 S2a-1 与 S2a-2 共有，S2a-2 不再重复声明。 **本轮（AUDIT-BREAK-3，强制）本步交付的基类 `apply` 取 M1 期占位形态**：§3.9.2 / §3.14.3 给出的基类默认实现体是 `return _apply_delta(dist, self.compute_delta(view, dist, ctx) or {})`，而 **`_apply_delta` 的归属是 S8-1（M2）、`compute_delta` 是 S8 起才存在的方法名**，二者在本步（M1 第 6 块）都不存在——照抄即 `NameError`，且 M1 期没有任何消费者（各具体 Modifier 均自实现 `apply`）。故本步写 `def apply(self, ctx, view, dist, readonly): raise NotImplementedError` 作为占位（**S8-1 把它替换为唯一的那处 `apply` 定义**，替换点与 §3.9.2 过渡期纪律的例外括注、§3.14.3 的两期形态同源）<!-- REVIEW-R1-FIX: AUDIT-BREAK-3 -->
  - 交付物（本步）= `Modifier` 基类（`rebind` 空实现 + `apply` 默认实现 + `state_keys` 默认 `()` + `namespace` 属性，§3.9.2）+ **`HardModifier`（按 `target_featured` 分两行）+ `SoftModifier`**——即「六个类、七个机制形态」中**转移量语义族的三个机制形态**（§3.1.2 机制表）；其余四类见 S2a-2
  - `HardModifier` 的转移量按 §3.1.2 表（`amount = p(Q)`，不得写成 soft 的 `boost/100`）；`SoftModifier` 的 `t = boost%(counter) / 100`（§3.4.1 修正 ①，**不得再乘 `p(Q)`**）
  - **`_lower_rarities(ctx, scope)` 助手随 S2a-1 落地**（§3.9.4 的 `SoftModifier` 示例已调用它，但全篇此前无定义处，S2a-1 补上）：返回 `rarity_rank` 中 `rank > rank(scope)` 的稀有度下的全部卡，供 `HardModifier` / `SoftModifier` / `NotOwnedModifier` 共用；住 `core/pity_modifier.py`（只本族消费，不下沉叶子层）。**S2a-2 的 `NotOwnedModifier` 消费同一助手**（两族共用，定义只此一处）
  - 验收命令：`pytest -q tests/core/test_pity_modifier.py`（本步新建该文件；用例名须落在本步新增用例内——`-k` 过滤词与断言对象绑定纪律见 §七 引言）——① `Modifier` 基类的 `apply` **M1 期占位实现**（调用即 `NotImplementedError`，有可执行断言对象）与 `rebind` 空实现各一条<!-- REVIEW-R1-FIX: AUDIT-BREAK-3 -->；② `HardModifier` 按 `target_featured` 的两分支，含 §3.1.2 的转移量口径（`amount = p(Q)`，不得写成 `boost/100`）；③ `SoftModifier` 的 `t = boost%(counter) / 100` 与「不得再乘 `p(Q)`」；④ `_lower_rarities` 的 scope 分层（返回 `rarity_rank` 中 `rank > rank(scope)` 的稀有度下的全部卡）
- [x] **S2a-2 `RotatingModifier` / `NonFeaturedModifier` / `SelectedModifier` / `NotOwnedModifier`（目标集语义族）**（~0.6 人时）｜目标文件 `core/pity_modifier.py`（续 S2a-1 的同一文件）<!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->
  - 交付物（本步）= **四个类、四个机制形态**（`RotatingModifier` / `NonFeaturedModifier` / `SelectedModifier` / `NotOwnedModifier`）。四者的 `A` 来源各异（「全部 featured 卡」/「非 featured 的最高稀有度卡」/「定轨选中卡」/「未持有卡」），是 `shape='declared'` 分支的主力，§3.1.2 机制表
  - 旧形态的对应关系：原「Force 三兄弟 + `InterceptModifier`」中的三个 Force 类即 `RotatingModifier` / `NonFeaturedModifier` / `SelectedModifier`（§3.1.2 映射表），`InterceptModifier` 整个删除；条件内联的形态范例见 §3.14.2 的 `RotatingModifier`
  - 逐类在方法体内解析 A/Q（不写解析器族，原 S2b 已并入本族），并复用 S2a-1 已落地的 `_lower_rarities`；本步对 `core/pity_modifier.py` 为**续写**，不新建文件
  - 验收命令：`pytest -q tests/core/test_pity_modifier.py -k "rotating_modifier or non_featured or selected or not_owned"`——四类各自的目标集构造与 `A` 侧形状各一条用例，用例名须含上列过滤词之一；落地时 `--collect-only` 确认收集到 ≥1 条且命中项**全部为本步新增**（过滤词与断言对象绑定纪律见 §七 引言）
- [x] ~~**S2b 目标解析器族 `_u_scope` / `_u_pool` / `_t_featured` / `_t_selected` / `_t_not_owned`**~~（**2026-10-09 取消，A/Q 计算与 `_lower_rarities` 并入 S2a-1、目标集解析并入 S2a-2**）（原 ~0.8 人时）：新形态下 A/Q 是各类方法体内的局部量（§3.1.2），解析器族不再作为独立文件与契约面存在。预算去向：**0.4 并入 S2a**（A/Q 计算与 `_lower_rarities` 的内联化，即现 S2a-1 / S2a-2），**0.4 从 M1 扣除**（独立契约面消失）。原内容存档：原「Force 三兄弟 + InterceptModifier」已按裁决 1B / 6B 取消——三个 Force 类现为 `RotatingModifier` / `NonFeaturedModifier` / `SelectedModifier`（§3.1.2 映射表，**其本体即 S2a-1 / S2a-2 的六个类**，不另占本块）；`InterceptModifier` 整个删除，掷骰归 `StreakTracker.commit`（**其短路条件 / 索引裁剪 / 空表分支 / `guaranteed` 守卫的搬迁工作归 S1c**，H4 验收口径亦随之改为「Tracker 在同一相位消费同样次数」，见 §3.1.1 的 CR 掷骰相位段）。原验收命令「H4 契约 + 三类强制修饰的分布断言」的去向：前者随 `StreakTracker` 归 S1c（S1c 的验收命令即此条），后者归 S5b / S5c 的等价性装置
<!-- REVIEW-FIX-PREV: ISSUE-101 -->
<!-- REVIEW-FIX-PREV: ISSUE-101 -->
- [x] ~~**S12-1 Condition 类族** / **S12-2 `ConditionalModifier` + 各 Modifier 去内部判断**~~（**2026-10-06 随 §3.14 改判整块删除**）：条件内联进各机制的 `compute_delta()`（M1 期为 `apply()`），不再需要 Condition 类族与包装器。原两块共 ~1.3 人时，**从 M1 预算中扣除**。原目标文件 `core/pity_condition.py`（新增）与 `tests/core/test_pity_condition.py`（新增）一并不存在。
- [x] **S3-1 统一 Pity 骨架 + rebind 委托 + `_pools`**（~0.85 人时；**2026-10-10 上调**：`before_draw` 新增 `prepare` 循环，位于 `advance` 之后、Modifier 链之前，并透传 `readonly`）｜目标文件 `core/pity.py`
<!-- REVIEW-FIX-PREV: ISSUE-001 -->
<!-- REVIEW-FIX-PREV: ISSUE-004 -->
<!-- REVIEW-FIX-PREV: ISSUE-018 -->
  - Tracker + Modifier + Lifecycle **三元组**构造（§3.1.4 骨架）；保留 `is_soft` / `is_hard` / `is_event_driven` 的 btype 推导（不得写死）
  - `_rebind_state` 重建 `self._view` 且 `StateView` 每次现取；Tracker / Modifier 两族实现公开 `rebind(state, name)`、**Lifecycle 实现 `rebind(state, name, namespaces=())`**（**ISSUE-917**：与 `initialize` 同实参面，漏传即 `X_soft` 的 `_active` Flag 跨场不重绑）。<!-- REVIEW-R1-FIX: ISSUE-917 -->（`Pity._rebind_state` 无守卫调用，见 §3.1.1 / §3.1.3 / §3.9.2）
  - **`self._pools = pools`（ISSUE-019 自 S1a 移入本步，2026-09-22 第八轮）**：由 `PityDef.pools` 注入（§3.1.4 骨架已含该形参），使 `_build_activation_graph` 的池交集警告恢复语义（§3.12.2）；S1a 至 S2a-2 期间该警告恒真触发属已知过渡态
  - ~~`Pity` 增加 `reads` 形参~~（**2026-10-06 删除**，§3.10.2 改判）。原注：由 `PityDef.reads` 注入，**S9 之前只接受默认空 tuple**，见 §四 `core/pity.py`（S9）行）
  - 验收命令：`pytest -q tests/core/test_pity_lifecycle.py` 的构造与 rebind 部分；`_pools` 注入后同池 `depends_on` 不再触发池交集警告
- [x] **S3-2 生命周期顺序与视图接线**（~0.5 人时）｜目标文件 `core/pity.py`
<!-- REVIEW-FIX-PREV: ISSUE-202 -->
  - `after_draw` 的退役判定**先于** `commit`，`commit` 接受 `skip_reset`。<!-- REVIEW-R1-FIX: ISSUE-402 --> **退役判定的调用形态 = 四实参**：`fired = self.did_fire(ctx)` 在判定前取值，再 `self._lifecycle.should_deactivate(ctx, self._state, self._name, fired)`（§3.1.4 骨架；三实参即 `triggers` 退化为「激活后的抽数」或 `TypeError`）
  - **ISSUE-202 追加**：`Pity.__init__` 在创建 `_view` **之前**调用 `Lifecycle.initialize(state, name, namespaces)` 写初始 `_active`（非 `depends_on` 保底写 `True`，`DependentActive` 空实现）。<!-- REVIEW-R1-FIX: ISSUE-407 --> **`namespaces` 由 `Pity` 从 `trackers` / `modifiers` / `lifecycle` 的 `namespace` 属性收集**（去 `None`），`AlwaysActive` / `FiniteActive` 对 `name` 与其中每个命名空间各写一次（这是 `X_soft: {_active: True}` 的唯一产出路径）
  - **StateView 薄版（ISSUE-GATE-dependency-order；ISSUE-407 补实接口）**：按 §3.10.3 定稿做**按零件命名空间分配**——默认 view 绑 `self._name`；`Pity` 另建 **`self._ns_views: Dict[str, StateView]`**（keyed by 零件 `namespace`），遍历 `trackers` / `modifiers` 时经 `self._ns_views.get(getattr(part, 'namespace', None)) or self._view` 取值，**不得写死 `self._view`**；`_rebind_state` 重建默认 view 时同批重建 `_ns_views`；S9 才切断 `name` 之外的读取
  - 验收命令：P75 跨模拟状态隔离用例（worker 内连跑 N 场）+ 构造期 `_active` 断言（§六 ISSUE-202 条）
<!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order -->
<!-- REVIEW-FIX-PREV: ISSUE-015 -->
- [x] **S4-1 registry schema 改造（只改 validator 与 `create_behavior` 分支；条目改写随 S4-2 / S4-3 逐条原子落地，GATE-3 定稿）**（~0.5 人时）｜目标文件 `core/pity.py`
  - `class` 字段一律置 `None`（ISSUE-015）<!-- S4-1-REVIEW-FIX: 与 §3.2 / GATE-3 对齐 -->**但本步不一次性置空**：`class` 置 None 与 `preset` 赋值按条目**原子地**随 S4-2 / S4-3 落地（§3.2 与 GATE-3 定稿；S4-1 审查 low，2026-10-10 补：本步若真去置空，10 条目在导入期即 `TypeError`，与下行实测的结论一致）；`_validate_registry()`（:815-829，模块级调用 :832；2026-10-09 实测订正）<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->**改判 `preset` 可调用性**（`callable` / `inspect`——**不调用 preset、不校验返回键集**，ISSUE-405）；返回 dict 的键集校验（缺 `lifecycle` 查漏 + 未知键查多）落在 `create_behavior` 运行期；`create_behavior` 的 `cls is None` 分支同步改写
  - **过渡判据（S4-1 写入、S4-3 收口时整段删除；GATE-3 定稿）**：`_validate_registry()` 的判据改为「条目**含 `preset` 键则判其可调用**（`callable` / `inspect`，**不调用 preset、不校验返回键集**，ISSUE-405）；**无 `preset` 键（尚未迁移）则沿用旧判据**（`class` 非 None 且为 `PityBehavior` 子类）」。该式使 S4-1 单独落地时导入期仍通过（此时 10 条目全为旧形态），且 S4-2 / S4-3 的任一中间态都自洽
  - `create_behavior` 双路径（preset / 旧类兼容）保留到等价性测试通过为止
  <!-- REVIEW-FIX-PREV: AUDIT-BREAK-2 -->
  <!-- REVIEW-FIX-PREV: AUDIT-BREAK-3 -->
  - **preset 分支的构造形态（AUDIT-BREAK-2 / AUDIT-BREAK-3，强制）**：preset 分支**按名取 key**（`trackers`/`modifiers`/`lifecycle` 必需，`flags`/`counters` 可选）构造 `Pity(...)`，**禁止 `**preset(pdef)` 直展开**（未知键 → `TypeError` 或死键），**禁止传旧类分支的 `params` dict**（其中 `target_featured` / `reset` 两处注入在骨架无对应形参 → `TypeError: unexpected keyword argument`）。构造代码与两道校验（查漏 `lifecycle`、查多未知键）见 §3.2 AUDIT-BREAK-3 条；接口冲突的完整分析见 §3.1.4 AUDIT-BREAK-2 条
  - **验收命令（GATE-3 收窄：本节只列 S4-1 位置可达的部分）**：① `python -c "import gacha_simulator.core.pity"` 冒烟——导入期 `_validate_registry()` 在**过渡判据**下对 10 条目全部通过（此时全为旧形态，走旧判据分支）；② 单测人为构造非法条目（把某条的 `preset` 置为非 callable，或把未迁移条目的 `class` 置 `None`）断言 `_validate_registry()` 抛错——**不得只测「不抛」**；③ `inspect.signature(Pity.__init__)` 不含 `target_featured` / `reset`（防注入点被接回 preset 分支；`Pity` 骨架已在 S3-1 落地，本步可验）。**原写在本步、但位置不可达的两项已下移**：`create_behavior` 缺键抛 `ConfigError`、`create_behavior(PityDef(name='x', btype='hard', reset='never'), state)` 返回 `Pity` 且不抛 `TypeError`（AUDIT-BREAK-2）——二者要求 `hard` 已有 preset，**移入 S4-2 验收**；**「10 条目全部具备可调用 `preset`、过渡判据的旧分支已删」的终局验收移入 S4-3 收口**<!-- REVIEW-R1-FIX: ISSUE-930 -->
<!-- REVIEW-FIX-PREV: ISSUE-007 -->
<!-- REVIEW-FIX-PREV: ISSUE-008 -->
<!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order -->
- [x] **S4b `priority` 字段定义 + 解析 + 三处透传**（~0.4 人时）｜目标文件 `core/config_store.py` + `core/config_toml.py` + `service/batch_simulator.py` + `core/retreat_config.py`。**位置：S4-1 之后、S4-2 之前（2026-09-22 第八轮前移，GATE-3(a)）**<!-- REVIEW-FIX-PREV: ISSUE-GATE-3-dependency-order -->
  - `PityDef` 新增 `priority` 字段（默认 0）+ `config_toml` 解析（`_build_pity`）+ **round-trip 写回（`_pitydef_to_toml`，非默认才写）**（`core/config_store.py` / `core/config_toml.py`）。**ISSUE-923**：`_pitydef_to_toml`（[config_toml.py:1709](gacha_simulator/core/config_toml.py#L1709)）是**条件式逐字段书写**（如 `if p.reset: entry['reset'] = p.reset`），**不会自动带上任何新字段**——不补写回则「GUI 加载 → 保存」一次即把手写的 `priority` 从 TOML 抹掉，而下一步的 round-trip 验收正是以写回为前提。同表对照：`max_triggers`（§四 `core/config_toml.py` 的 S4-4 行）与 ~~`reads`~~（同文件 S9 行，已取消）都显式写了「round-trip 写回」，`priority` 是唯一漏写的那一行。<!-- REVIEW-R1-FIX: ISSUE-923 --><!-- REVIEW-R1-FIX: ISSUE-001 -->
  - `PityDef.priority` 在 `service/batch_simulator.py`（[batch_simulator.py:1168-1193] 的 `pentry`、:218-243 的 `_PityDef`）与 `core/retreat_config.py`（[retreat_config.py:123-142]）三处**枚举式透传点**同步补齐；**AUDIT-BREAK-1 升为强制**：三处一律**改造为 dataclass 字段驱动**（`dataclasses.fields(PityDef)` 逐字段取值/回填），原「建议」表述废止；逐字段枚举与 `pentry` 的 24 键清单**一经改造即删除**（不得与新写法并存）。理由：三处枚举是字段级类型断裂点，`pentry` 实测 24 键、`_PityDef` 实测逐字段重建（`_PityDef` 是 `PityDef` 的别名，[batch_simulator.py:202](gacha_simulator/service/batch_simulator.py#L202)；**ISSUE-925** 更正原引 `:193`——该行是 `_build_pity_engine_from_gui` 附近的别的语句，`_PityDef` 的函数内 import 在 `:202`）<!-- REVIEW-R1-FIX: ISSUE-925 -->，漏写即静默落回默认值且配置层无异常。三处的完整清单与失效面见 §3.6 AUDIT-BREAK-1 条。 **本轮（AUDIT-BREAK-1）把该条的前提在块内复述一遍（强制，防止只读块内文字即施工）**：三处改造为 dataclass 驱动**必须与四个别名键的改名同 commit**——写端 `pentry` 的 `'type'` / `'start'` / `'end'` / `'increment'`（[batch_simulator.py:1168-1193](gacha_simulator/service/batch_simulator.py#L1168-L1193)）与读端 `_PityDef(...)` 的四个 `p.get(...)`（[batch_simulator.py:218-243](gacha_simulator/service/batch_simulator.py#L218-L243)）**一并改名**为 `btype` / `soft_start` / `soft_end` / `soft_increment`（两个区块的其余字段已是字段名口径）。**照抄 `{f.name: getattr(pd, f.name)}` 而不改名的后果**：读端仍找 `'type'`，`btype` 落回默认 `soft_interval`（软保底类型全变）、软保底三段参数整体丢失，**且配置层不报任何异常**；同时本条的键集断言 `assert set(pentry) == {f.name for f in dataclasses.fields(PityDef)}` 在别名制下**恒不相等**（多四个别名键、少四个字段名键），守卫恒红。GUI 侧五处（含 `_do_update_preview` 与 `tests/gui/test_config_panel_pity.py` 的存量断言）的同批改名归 **S7a**，不在本步；本步只管引擎侧三处的写端 / 读端<!-- REVIEW-R1-FIX: AUDIT-BREAK-1 --> <!-- REVIEW-R1-FIX: ISSUE-953 -->
  - **归属说明**（**2026-10-06 改**）：原 `PityDef.reads` 的字段定义 + 解析 + 三处透传整体归 S9（M2）（ISSUE-008 的本步落点已撤销），且同样走改造后的 dataclass 驱动路径。本步只处理 `priority`，其消费方是紧随其后的 S4-2（构造形参）与 S6b（`_resolve_order` 排序）
  - 验收命令：`PityDef(priority=5)` 经 TOML round-trip 与三处透传后仍为 5（§六 ISSUE-007 条）；**写回判据（ISSUE-923）**：`_pitydef_to_toml(PityDef(priority=5))` 导出的 dict 含 `priority == 5`（且默认值 0 **不写出**该键），并跑一次「写盘 → 重载」闭环断言值不变；**AUDIT-BREAK-1 追加**：字段全量 round-trip 用例——`for f in dataclasses.fields(PityDef)` 用非默认值构造 → TOML round-trip → `ConfigStore` → `pentry` → `_PityDef` 逐字段等值，且断言 `set(pentry) == {f.name for f in dataclasses.fields(PityDef)}`（键集相等，防漏亦防多）。落点 `tests/service/test_batch_simulator.py`
- [x] **S4c `[[pity]]` 键契约与 `load_toml` 失败原子性**（~0.8 人时；**2026-10-06 用户裁决归入本计划**）｜目标文件 `core/config_toml.py` + `tests/core/test_pity_config_toml.py` + `tests/test_config_toml.py`。**位置：S4b 之后**（① 的 TOML 键空间与 S4b 改的 `pentry` 内部键空间是两回事，故 ① 不依赖 S4b 的改名；排在 S4b 之后是为了把 `config_toml.py` 的编辑并批）
  - **① 键契约 + 硬拒（读侧：未知键静默忽略）**：建模块级 `_PITY_COMMON_KEYS`（`type` / `name` / `scope` / **`priority`** / `target_featured` / `reset` / `pools` / `lifecycle` / `counter_init` / `guaranteed_init` / `fate_points_init` / `selected_card_init`）与 `_PITY_TYPE_KEYS`（每 btype 的键集，**含嵌套键** `lifecycle.deactivate_on_early_hit` / `lifecycle.depends_on`），加 `pity_key_issues(pity_list) -> List[str]`（形态照 [stop_condition.py:314](gacha_simulator/core/stop_condition.py#L314) 的 `stop_condition_shape_issues`：不抛、只读、返回消息列表，加载期与保存闸门共用一处实现），并在 `_build_pity` 内**硬拒**（`ConfigError`，与 `scope` 白名单同风格）。
    - **`priority` 必须收进 `_PITY_COMMON_KEYS`（2026-10-09 订正）**：`priority` 由紧邻在前的 **S4b** 定义且**要求 TOML round-trip 写回**（非默认才写），故 `_pitydef_to_toml` 在 `priority != 0` 时必然产出该键；本表若缺它，本步在 `_build_pity` 的未知键硬拒就会拒收**刚由 S4b 写出的合法配置**。`max_triggers`（S4-4 定义）与三个新增 btype（S6a 的 `rotating_inverse`；S9-3 的 `hard_exclude_owned_skip` / `hard_exclude_owned_any`，含 `on_all_owned` 键）同理，其扩表编辑点已分别写进各块任务项——**本表是全篇唯一契约源，改表只在此处与那三块发生**。<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->
    - **白名单来源不得取 `BEHAVIOR_REGISTRY[btype]['params']`**：实测它是 GUI 控件声明面，比真键契约窄：`rotating_soft` 缺 `end`、`rotating_cr` 缺 `cr_state_probs`、四个 init 键与 `reset`/`pools`/`lifecycle`/`target_featured` 均不在其中，照抄会把合法键报成未知。
    - **`func` 不入契约**：`_check_pity_format` 已按「带 start 却缺 scope，或含 func」硬拒，其提示语比未声明键更准（该提示语的自相矛盾已于 2026-10-06 修正）。
    - **一致性测试（必须同批）**：对每个 btype 用**全量键（含非默认 `priority` / `max_triggers`）**构造 → `_pitydef_to_toml` → 断言产出键集 ⊆ 契约表；反向断言契约表 ⊆ `_build_pity` 的读取面。**用例必须显式给非默认值**（如 `priority=1` / `max_triggers=1`）——这两个键的写回条件都是「非默认才写」，全默认构造时用例恒绿、检测力归零。没有它，契约表自身就是新的漂移点。<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->
  - **② `load_toml` 失败原子性（① 的前提）**：现实现先 `store.clear()` 再逐段构建（[config_toml.py:62-64](gacha_simulator/core/config_toml.py#L62-L64)），中途抛错即停在半成品。实测（真实配置 + 一处非法 `scope`）：`banners 8→0`、`pity 1→0`。改为「副本上构建、成功再 swap」或「失败回滚快照」。**这不是 ① 独有的问题**：`load_toml` 调用链内现有十余处会抛 `ConfigError`（cards / pity / milestone / select_voucher / banners / resource_lifecycle / stop_condition），本步顺带修好全部。GUI 启动路径（[main_window.py:240-242](gacha_simulator/gui/main_window.py#L240-L242)）现状为「`except Exception` → stderr traceback + 状态栏一行字，窗口照常打开、配置半装」，即**静默半开**；硬拒若不配 ② 只会多一个触发点。
  - 验收命令：`pytest -q tests/core/test_pity_config_toml.py tests/test_config_toml.py -k "key or atomic or unknown"`（收集 ≥1 条）；另加两条端到端：① 含未知键的 `[[pity]]` 抛 `ConfigError`，且错误信息点名该键与合法键集；② 加载失败后传入的 `store` 与加载前**逐字段相同**（`banner.banners` / `card_defs` / `pity.pities` / `resource_defs` 计数与内容不变）
<!-- REVIEW-FIX-PREV: ISSUE-005 -->
- [x] **S4-2 counter 驱动 preset（4 类）**（~0.6 人时）｜目标文件 `core/pity.py`
  - `soft_interval` / `soft_additive` / `soft_step` / `hard` 四类改造为 **preset 工厂函数**（不得模块级常量实例，ISSUE-005）；工厂签名统一 `def _preset_xxx(pdef)`、调用形式 `preset(pdef)`（ISSUE-030），逐条可配字段一律取自 `pdef`（取值来源表见 §3.2）
  - `PityDef.priority` 经**构造形参** `Pity(..., priority=pdef.priority)` 传入（不是构造后设 `_priority` 属性，§3.6 M3；ISSUE-203）。**`PityDef.priority` 的字段定义与解析见上一步 S4b**（2026-09-22 第八轮前移；新序 S4-1 → S4b → S4-2。实测 `PityDef`（[config_store.py:150-186](gacha_simulator/core/config_store.py#L150-L186)）当前无该字段，若先于 S4b 施工即 `AttributeError`）<!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order -->
  - 验收命令：`python -c "from gacha_simulator.core.pity import BEHAVIOR_REGISTRY as R;from gacha_simulator.core.config_store import PityDef;ks=('soft_interval','soft_additive','soft_step','hard');d=[R[t]['preset'](PityDef(name=t,btype=t)) for t in ks];assert all({'trackers','modifiers','lifecycle'}<=set(x)<= {'trackers','modifiers','lifecycle','flags','counters'} for x in d),d"`——四类 preset 均可构造、返回 dict **⊆ 五键全集**且含三必需键，无 `AttributeError` / `NameError`；**非默认** `threshold` / `scope` / `counter_init` / `deltas` 与旧类逐场一致的等价性口径由 S5b 的 counter 驱动批次覆盖（§六 ISSUE-030 条）<!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-6-测试策略 --><!-- REVIEW-FIX-PREV: AUDIT-BREAK-3 -->（**AUDIT-BREAK-3**：原写 `<=set(x)` 的**子集**判断不拒绝多余键，故「`flags`/`counters` 成了死键」在该命令下不可见；现值域上界为五键全集，**另加**下述消费者断言）
  - **由 S4-1 移入的两项验收（GATE-3，2026-10-01；原位置在 S4-1 不可达）**：本批含 `hard`，故两项在此可达——① `create_behavior` 对缺 `lifecycle` 键的 preset 返回 dict 抛 `ConfigError`（人为构造一个缺键 preset）；② `create_behavior(PityDef(name='x', btype='hard', reset='never'), state)` 返回 `Pity` 且不抛 `TypeError`（AUDIT-BREAK-2）；③ 本批 4 条 registry 条目已原子地 `class: None` + 可调用 `preset`，导入期不破（`python -c "import gacha_simulator.core.pity"`）<!-- REVIEW-R1-FIX: ISSUE-930 -->
  - **消费者断言（AUDIT-BREAK-3，强制）**：`PityDef(name='h', btype='hard', counter_init=5, guaranteed_init=True)` 经 preset 与 `create_behavior` 构造出的 `Pity`，其 `state.get(name,'counter') == 5` 且（对含 flag 的类型）`state.get(name,'guaranteed') is True`——即 `flags` / `counters` 被 `Pity.__init__` 真正写入 state，而非「声明了没人读」。同时断言 `create_behavior` 对**未声明键**（如人为在 preset 里加一个 `foo`）抛 `ConfigError`
  <!-- REVIEW-R1-FIX: ISSUE-403 -->
  - **`_target_of(pdef)` + `target=` 键（ISSUE-403，强制；2026-10-09 按裁决 7B 收窄至 `hard`，ISSUE-002）**：本步另落地模块级 helper `_target_of(pdef)`（与 `build_lifecycle` 同住 `core/pity.py`），并在 **`_preset_hard`** 的 `HardModifier` 构造里写 `target=_target_of(pdef)`。**`_preset_soft_step` 不写该键**——裁决 7B 下 `soft_*` + `target_featured=true` 在 `create_behavior` 处即抛 `ConfigError`，soft 侧没有消费路径（原稿要求本工厂也写 `target=_target_of(pdef)`，与 7B 互斥，已改）。**漏写不会报错**——`target` 默认 `'scope'`，`target_featured=True` 的配置会静默把目标集由 featured 卡集放宽为 scope 全集（§六 ISSUE-403 条）。**S4-3 的六个事件驱动 preset 不加该键**（旧实现忽略 `rotating` 族的 `target_featured`，加了即语义漂移）。**本步同时落 7B 的类型级硬拒**（`create_behavior` 内、preset 构造前，§3.2.1 落地面 ①），验收见 §六 ISSUE-403 条 <!-- S4-2-REVIEW-FIX: 重固化追认登记 -->
- [x] **S4-2 的三项连带后果（2026-10-11 用户追认）**：① `config.toml:1103-1104` 的示例块删去 `target_featured = true`（即上条落地面 ②）；② **重固化两套 golden** 共 8 份（p79 三组：`smart` / `pool_quota` / `draw_target`；p82 五组：同三组加 `fixed_count` / `stop_on_target`），归因经三方对照钉死（`旧树+新配置` 对 `新树+新配置` 九组逐字段 0 差异，差异集合与「只改配置」逐组完全相同，非把回归洗成基线），变动面与配置项作用面相称；③ 三处存量测试改造（`test_pity.py` 的合成 spec 补 `card_to_slot` 与低稀有度卡集、`test_banner.py` 补 `store.rarity_rank`、`test_worst_impact.py` 的断言方向随目标集口径）。**重固化属用户裁决级动作**（先例 `68770ce`，2026-10-07），本行即追认记录；改动前的快照可用 `git checkout de4983f^ -- tests/fixtures/` 取回。
<!-- REVIEW-R1-FIX: ISSUE-002 -->
- [x] **S4-3 事件驱动 preset（6 类）**（~0.8 人时）｜目标文件 `core/pity.py` + `core/__init__.py`
  - `rotating` / `rotating_soft` / `rotating_cr` / `rotating_cr_soft` / `targeted` / `targeted_soft` 六类 preset 化，签名与取值规则同 S4-2
  <!-- REVIEW-R1-FIX: ISSUE-407 -->
  - **三个 `_soft` 类型的命名空间载体（ISSUE-407，强制）**：`rotating_soft` / `rotating_cr_soft` / `targeted_soft` 的 preset **必须**含 `NamespaceTracker(namespace=f'{pdef.name}_soft')`（形态见 §3.10.3 配套 1 的 `_preset_rotating_soft` 示例）。缺它则 `X_soft` 命名空间不存在、`Lifecycle.initialize` 的推广写入无处落、§六 的 `_soft` 族命名空间保留断言无法通过。**六个事件驱动 preset 一律不加 `target=`**（旧实现忽略该族的 `target_featured`，ISSUE-403）
  <!-- REVIEW-FIX-PREV: AUDIT-BREAK-8 -->
  - **AUDIT-BREAK-8 追加**：本步同时删除 [core/\_\_init\_\_.py:9-20](gacha_simulator/core/__init__.py#L9-L20) 的 **10 个旧行为类 + `SoftPityMixin`** import 与 `__all__` 对应条目（`_redistribute_scope` 的导出归 S8-4，见 §3.9.3 C 项）。**只删 import 留 `NameError`、只删 `__all__` 留指向已删符号的 re-export**，两者必须同批；删除前须 `grep -rn "from gacha_simulator.core import"` 确认无调用方依赖这些符号（`from gacha_simulator.core.pity import …` 不受影响——旧类本体保留到发布前，GATE-5）
  - 验收命令：全部 10 个 preset 构造成功且 `len(engine.behaviors) == len(pity_defs)`；`python -c "import gacha_simulator.core as c; assert not {'HardPityBehavior','RotatingBehavior','TargetedBehavior','SoftPityMixin'} & set(c.__all__)"`（AUDIT-BREAK-8）；`pytest -q tests/core/test_pity_validate_behaviors.py`
  - **收口验收（GATE-3，2026-10-01）**：本步须删除 `_validate_registry()` 过渡判据中的「无 `preset` 键」分支（此后 10 条目一律走 preset 可调用判定），并断言 `python -c "from gacha_simulator.core.pity import BEHAVIOR_REGISTRY as R; assert all(callable(e['preset']) for e in R.values()); assert all(e['class'] is None for e in R.values())"`——ISSUE-015 的「`class` 一律置 `None`」在本步终局达成；外加 `python -c "import gacha_simulator.core.pity"` 冒烟<!-- REVIEW-R1-FIX: ISSUE-930 -->
<!-- REVIEW-FIX-PREV: ISSUE-301 -->
- [x] **S4-4 deltas 展开归属 + 旧 `lifecycle_kwargs` 段删除 + `create_behavior` 防线**（**~0.7 人时**；`build_lifecycle` 的定义移入 S1d，本步预算先由 0.4 调为 0.3，再因块内「`FiniteActive` 配置接线（ISSUE-032）」调为 0.7——**三处取值已统一，见下条与 §七 的逐块求和行**）｜目标文件 `core/pity.py` <!-- REVIEW-R1-FIX: ISSUE-005 -->
  - deltas 展开职责移交（M6）
  - **`create_behavior` 增 `lifecycle` 键防线**：在 `preset(pdef)` 之后校验返回 dict 含该键，缺失即抛 `ConfigError`（不得静默回退骨架默认 `AlwaysActive()`，§3.1.3）。**10 个 preset 工厂的 `lifecycle=build_lifecycle(pdef)` 在 S4-2 / S4-3 写入**（helper 已于 S1d 定义，本步不重复定义、也不「先写 preset 后在 S4-4 补键」）；本步只补校验与清理
  - **删除旧 `create_behavior` 的 `lifecycle_kwargs` 段（:893-900）**：同一转换不得留两处（§3.1.3）。**删除时机不可前移**——S4-2 / S4-3 期间未迁移的类型仍走旧类兼容路径、仍需该段注入 `LifecycleConfig`，提前删除会让这些类型的 `deactivate_on_early_hit` / `depends_on` 静默失效（§3.2 双路径保留到等价性测试通过为止）
  - 验收命令：`create_behavior` 对缺 `lifecycle` 键的 preset 返回 dict 抛 `ConfigError`；10 个 preset 的 `Pity._lifecycle` 类型与 `deactivate_on_early_hit` 值符合 §3.1.3 **四组合取值表**（§六 ISSUE-301 条）
  - **`FiniteActive` 配置接线（ISSUE-032，2026-09-27 裁决）**：`PityDef.max_triggers: int = 0` 字段 + `config_toml` 解析与 round-trip（负值抛 `ConfigError`）+ `build_lifecycle` 的退役维产出（`max_triggers > 0` 时产出 `FiniteActive` 或 `DependentFiniteActive`，见 §3.1.3 四组合表）。本步预算 0.3 → 0.7 人时（GUI 控件归 S7a）；验收见 §六 ISSUE-032 条 **契约表同批扩（2026-10-09）**：本步在 `core/config_toml.py` **同 commit 扩 `_PITY_COMMON_KEYS`（加 `max_triggers`）**——S4c 的 `_build_pity` 已对未声明键硬拒，不扩则本步刚落地的 `max_triggers` 解析会把合法配置判为未知键。<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->
<!-- REVIEW-FIX-PREV: ISSUE-204 -->
- [x] **S4-5 PityEngine 构造兜底改抛 ConfigError**（~0.2 人时）｜目标文件 `core/pity.py`
  - `PityEngine.__init__` 的 `try / except Exception` 构造兜底改为抛 `ConfigError`（§四 `core/pity.py` 行）；任一 preset 构造失败**不得只 `logger.warning` 后跳过**（跳过会让 `_resolve_order` / `_validate_behaviors` 在截断后的列表上执行，同 scope 互斥校验失去语义）
  - 验收命令：`pytest -q tests/core/test_pity_validate_behaviors.py -k engine_construct`（新增用例 `test_engine_construct_failure_raises_config_error`，落在该文件——构造期校验失败路径的既有归属）：构造一个 preset 体内会抛错的配置，断言 `PityEngine(...)` 抛 `ConfigError`，**不得** `logger.warning` 后跳过；并断言 `_resolve_order` / `_validate_behaviors` 在**未截断**的列表上执行（同 scope 两条互斥保底中任一条构造失败时，异常必须来自构造而非静默通过）<!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-6-测试策略 -->。**前置（本轮 AUDIT-BREAK-2，强制）**：**G16-1 必须先于本步落地**——本步把「构造失败」由静默跳过改为抛 `ConfigError`，而现存的那条构造失败路径就在 GUI 兜底保底条目（[config_panel.py:6544-6547](gacha_simulator/gui/config_panel.py#L6544-L6547) 的 `type='soft'` / `reset='any_ssr'` / 嵌套 `params`），它当前正被本步要删的 try/except 吞掉；不同批落地即「打开无保底段的配置后运行模拟」由静默不生效变为直接崩。**验收追加（覆盖新增单测覆盖不到的 GUI 路径）**：`set_config`（无保底段）→ `get_config` → `load_toml` → `_build_pity_engine_from_gui` **不抛** `ConfigError`<!-- REVIEW-R1-FIX: AUDIT-BREAK-2 -->
- [x] **S5a 等价性测试骨架**（~0.8 人时）｜目标文件 `tests/core/test_pity_equivalence.py`（新增）
  - 固定种子逐场对比装置（旧 vs 新，概率分布 + 状态快照）；含 `cr_state_probs` 中间值用例（H4）
  - 验收命令：`pytest -q tests/core/test_pity_equivalence.py` 先跑通 1 个类型（装置自检）
- [x] **S5b 全部 10 个类型 preset 化等价性**（~0.9 人时；**2026-10-10 上调**：`rotating_cr` / `rotating_cr_soft` 回归「逐场一致」批次）｜目标文件 `tests/core/test_pity_equivalence.py`
  - 逐类型**批次**推进（counter 驱动 4 类一批 / 事件驱动 6 类一批）；**每批一个 commit**，失败即停在该批（回滚单元）
  - **ISSUE-403 追加（强制；2026-10-09 按裁决 7B 改写，ISSUE-002）**：counter 驱动批次须含 **`target_featured=True`** 的 `hard` 用例两条：① 目标集收窄为 featured（与旧类逐场一致）；② **该 scope 无 featured 卡时的空集回退**（目标集退回 scope 全集）。**并含 7B 硬拒用例一条**：`soft_interval` / `soft_additive` / `soft_step` 配 `target_featured=True` 时经 `create_behavior` 抛 `ConfigError`（原稿此处要求「soft 用例与旧类逐场一致」，与 7B 互斥，已改）。原稿该字段在等价性批次中零覆盖，是 §六 ISSUE-403 条唯一能落地的验收面 <!-- REVIEW-R1-FIX: ISSUE-002 -->
  - **ISSUE-001 追加（强制，2026-10-09）**：`_soft` 批次须含一条「**只写 `soft_start` / `soft_end`**（不写 `deltas`）的 `rotating_soft`」等价性用例——该形态是 `_soft_deltas_of(pdef)` 分支 ③ 的唯一显形面：若预设按 `pdef.btype` 直喂 `_expand_soft_to_deltas`，展开结果为空元组、`SoftModifier` 的 boost 恒 0、软保底静默消失，而**该批次的其余用例（写 `deltas` 或写 `increment`）测不出来**。同批补一条「只写 `soft_increment` 的 `rotating_cr_soft`」用例覆盖分支 ② <!-- REVIEW-R1-FIX: ISSUE-001 -->
  - **7B 缺口登记（2026-10-11）**：`soft_*` 的 `target_featured` 能力自裁决 7B 起从配置面移除，而替代它的「转移量可自由取值的卡级算子」从未另立条目。本批的 soft 用例按 7B 为**硬拒用例**；若日后重新裁决取恢复支，本批与 §六 `ISSUE-403` 的 soft 用例面须一并反向改写，施工清单见 §3.2.1 的「缺口登记」段。<!-- P64-7B-GAP-REG -->
  - 验收命令：10 类逐场一致（§六 主线口径）
- [x] **S5c 三条强制约束专项断言**（~0.8 人时；**2026-10-10 上调**：H4 新增两条负例——只读查询不消耗随机数、掷骰失败后 flag 必须为假）｜目标文件 `tests/core/test_pity_equivalence.py`
  - **N1** 触发抽数 / **M4 did_fire 六类语义**（counter 驱动 ×1 + rotating + targeted + 三个 `_soft` 复合类型，ISSUE-102）/ **H4 短路条件下随机数消费次数**
  - 验收命令：`pytest -q tests/core/test_pity_equivalence.py -k "n1 or m4 or h4"`——**N1**：`hard(threshold=90)` 首次 100% 出现在第 90 抽、soft 的 boost 起始抽数与旧实现相同；**M4**：六类 `did_fire` 语义逐类一条（counter 驱动 ×1 + rotating + targeted + 三个 `_soft` 复合类型，ISSUE-102）；**H4**：`cr_base_rate == 0` 与 `cr_state_probs` 含 0 两条不消耗路径下随机数消费次数与旧实现**逐位相同**，`cr_state_probs` 含 `(0,1)` 中间值的用例一并覆盖<!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-6-测试策略 --> **GATE-6-测试策略（2026-10-01 补：收集守卫）**：过滤词 `n1` / `m4` / `h4` 须落在三类新增用例名内（`tests/core/test_pity_equivalence.py` 为 S5a **新建**文件，零命中时 pytest 以 **exit code 5**（no tests ran）结束、会被误读为通过），落地时确认三类各收集到 ≥1 条 <!-- REVIEW-R1-FIX: GATE-6-测试策略 -->
- [x] **S6a G1 `rotating_inverse` + H3 + GUI 类型列表**（~0.7 人时）｜目标文件 `core/pity.py` + `core/config_toml.py` + `gui/config_panel.py`
  - G1 `rotating_inverse` 注册（依赖 S1a 的 `_BTYPE_ORDER` / `_EVENT_DRIVEN_TYPES`） **契约表同批扩（2026-10-09）**：本步在 `core/config_toml.py` **同 commit 扩 `_PITY_TYPE_KEYS`（新增 `rotating_inverse` 条目，键集同 `rotating`）**——与 S6a 的 GUI 下拉生成式改造、S4c 的一致性测试三面同批，缺一则 `rotating_inverse` 的 `[[pity]]` 段被硬拒。<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->
  - H3 config_toml 拒绝分支移除（[config_toml.py:686-691](gacha_simulator/core/config_toml.py#L686-L691)）。<!-- REVIEW-R1-FIX: ISSUE-005 -->
  - **GUI 下拉改造（本步施工项，**非既成事实**；2026-10-01 实测仍为硬编码 10 项）**：`_PITY_TYPES` 改为由 `BEHAVIOR_REGISTRY` 生成，含三项同 commit 改动（① [config_panel.py:2019-2031](gacha_simulator/gui/config_panel.py#L2019-L2031) 字面量 → 生成式；② registry 5 处 `display_name` 对齐 GUI 现值；③ registry 条目顺序调整为 GUI 现值，`targeted` 移至 `rotating_cr_soft` 之后），现状实测与理由见 §3.6。**改造落地后** `rotating_inverse` 自动进入下拉（S7a 的该条验收以此为前提）；**未落地则本步须手工追加 `_PITY_TYPES`**。**同批**：[test_config_panel_p56.py:53](tests/gui/test_config_panel_p56.py#L53) 的 `assert len(panel._PITY_TYPES) == 10` 须改写为 `== len(BEHAVIOR_REGISTRY)` 并去掉写死的数量名（本步 +`rotating_inverse` 即由 10 变 11，不改写则该 commit 一落地即红）<!-- REVIEW-R1-FIX: ISSUE-929 -->
  - **同批断言更新（ISSUE-912，强制）**：H3 删掉的是 [config_toml.py:686-691](gacha_simulator/core/config_toml.py#L686-L691)<!-- REVIEW-R1-FIX: ISSUE-929 --> 的 `_EVENT_TYPES` 拒绝分支，它当前被**两条正断言**钉住——[test_pity_config_toml.py:249](tests/core/test_pity_config_toml.py#L249) / [:263](tests/core/test_pity_config_toml.py#L263)。本步须把这两条从「必抛 `ConfigError`」改写为「**不抛，且配置生效**」，否则 S7c 的 `pytest -q` 全量直接红。GUI 侧 `_on_pity_type_changed` 的 `setEnabled(is_counter)` 与 [test_config_panel_p56.py:116](tests/gui/test_config_panel_p56.py#L116) 的「仅 hard 启用」断言同批改为「事件驱动型同样可勾选」（目标文件补 `tests/core/test_pity_config_toml.py` + `tests/gui/test_config_panel_p56.py`）<!-- REVIEW-R1-FIX: ISSUE-005 --><!-- REVIEW-R1-FIX: ISSUE-001 -->
  - 验收命令：§六 `rotating_inverse` 类型注册三条断言；**追加**：`pytest -q tests/core/test_pity_config_toml.py tests/gui/test_config_panel_p56.py` 全绿 <!-- REVIEW-R1-FIX: ISSUE-912 -->
  - **S6a 审查收口登记（2026-10-12，三条口径，独立审查 APPROVED_WITH_CONCERNS 的 two-important 处置）**：<!-- P64-S6A-CLOSURE -->
    1. **事件驱动型的 `skip_reset` 口径**：S6a 删除 H3 拒绝分支后，「事件驱动型 + `deactivate_on_early_hit`」这一路径**首次可达**，而 `FlagTracker` / `StreakTracker` / `FateTracker` **一律不消费 `skip_reset`**（审查实测：`rotating` + 该开关出 UP 后 `_active` 转 False，标志照翻）。取此支的依据是 §七 S1b / S1c 的分块划线（该例外属 CounterTracker，见本节「双段 N1 相位 + `skip_reset` 例外」句），且旧事件驱动族无跳过分支，与 M1 的等价性口径同向。**属设计内口径，不是缺口**；已在三个 Tracker 的 docstring 与 `Tracker.commit` 的「适用范围」段写明。**若日后要求改为「事件驱动型同样尊重 `skip_reset`」，落点 = 三个 Tracker 的 `commit` 补跳过分支 + 反向改写 `tests/core/test_pity_tracker.py::test_flag_tracker_skip_reset_does_not_skip_flip`，且须先裁决它是否破坏「与旧类逐行同构」。**
    2. **§六 未勾选行「事件驱动型配置 `deactivate_on_early_hit` 后出 UP 即退役」只对 `rotating` 成立**（审查实测三点）：`targeted` 需 `selected_card` 已被策略写入，否则 miss、`did_reset=False`、不退役；`rotating_inverse` 的 fired 方向**相反**（M4 统一语义下其「回到初始态」是**出非 UP**）。三者行为均由 M4 统一语义一致推出、无代码矛盾，属该句措辞过窄，落 **S7c 的文档同步面**。
    3. **生成式下拉未带 `internal` 过滤**：先例（停止条件下拉）为 `[... if not entry.get('internal', False)]`，S6a 按 §3.6 给定式子未加。当前 `BEHAVIOR_REGISTRY` 无 `internal` / `disabled` 键（grep 零命中），故无害且与计划式子逐字一致；但 `_validate_registry()` 只校验 `preset` 可调用、不校验 `display_name` 存在。将来若新增「仅供内部使用」的 pity 类型，须一并补过滤。
- [x] **S6b G5 `priority` 排序与 GUI 控件**（~0.4 人时）｜目标文件 `core/pity.py` + `core/config_toml.py`
  - `_resolve_order` 按 priority 排序，显式 priority 覆盖 type 顺序；priority 全 0 时与接线后默认序一致（当前 hard 已在 targeted 前，绝区零默认顺序已满足）。**字段定义与解析不在此步**，已在 S4b 落地（2026-09-22 第八轮前移，GATE-3(a)），本步只消费
  - 验收命令：§六 G5 priority 两条断言（显式覆盖 / 全 0 退化为默认序）
<!-- REVIEW-FIX-PREV: ISSUE-GATE-dependency-order -->
- [x] **S6c GachaService 定轨识别适配（H1）**（~0.4 人时）｜目标文件 `service/gacha_service.py`
  <!-- REVIEW-FIX-PREV: AUDIT-BREAK-4 -->
  - **四处同改（AUDIT-BREAK-4 补，原稿只写一处）**：① [:253](gacha_simulator/service/gacha_service.py#L253) 的**函数局部** `from ..core.pity import TargetedBehavior`——**必须删除/改写**，局部 import 只在 `_apply_non_draw` 被调用时执行，故 ruff / H7 与导入期**均不报错**，仅策略返回 `NonDrawAction` 时才抛 `ImportError`；② [:275](gacha_simulator/service/gacha_service.py#L275) `isinstance(bh, TargetedBehavior)` → `getattr(bh, '_btype', '') in ('targeted', 'targeted_soft')`；③④ [:292](gacha_simulator/service/gacha_service.py#L292) / [:294](gacha_simulator/service/gacha_service.py#L294) 写 `selected_card` 依赖 ② 定位出的 `targeted_name`，判定口径**必须与 ② 同源同改**——否则定位到 0 条时抛 `InvalidActionError`、定位错保底时把 `selected_card` 写进错误命名空间（静默语义错误）
  - 验收命令：定轨流程专项用例；**追加端到端用例（AUDIT-BREAK-4）**：策略返回 `switch_epitomized_target` / `cancel_epitomized_path` 两条 `NonDrawAction` 各一条，断言不抛 `ImportError` 且 `pity_state.get(targeted_name,'selected_card')` 被正确写入/清空（只断言 `isinstance` 替换不足以覆盖 :253 —— 该行不被调用即不报错）
- [x] **S7a GUI round-trip 验收**（**~0.6 人时**）｜目标文件 `gui/config_panel.py`（验收） <!-- REVIEW-R1-FIX: ISSUE-005 -->
  - **新增「触发次数上限」数值控件（ISSUE-032，2026-09-27 裁决）**：`max_triggers`（0 = 不限），`_apply_pity_edit` 与 load/save 路径同步该键，与既有 pity 编辑区同列。本步预算 0.4 → 0.6 人时
  - preset 参数编辑 → 保存 → 重载一致；新 type **自动**出现在下拉（**前提 = S6a 的 `_PITY_TYPES` 生成式改造已落地**；未落地则本步须先手工追加 `rotating_inverse` 再断言，见 S7a 验收命令）<!-- REVIEW-R1-FIX: ISSUE-929 -->
  - **GUI 五处枚举透传的同批改造（ISSUE-911，强制，2026-10-01）**：`set_config` / `_refresh_from_store_impl` / `_flush_pity_current_detail` / `get_config` / `apply_to_store` 五处逐字段键表须与引擎侧三处**同批**改为 `dataclasses.fields(PityDef)` 驱动（含四个别名键 `type`/`start`/`end`/`increment` → `btype`/`soft_start`/`soft_end`/`soft_increment` 的**写读两端同步改名**，见 §3.6 AUDIT-BREAK-1 的 ISSUE-910 条）。**验收追加**：`priority`（S4b 引入）与 `max_triggers`（S4-4 引入）各一条 GUI 往返用例——TOML 写入非默认值 → GUI 加载 → 直接保存 → 重读 TOML，两键仍为原值；该用例是五处漏改的**唯一显形面**（漏改不报错）。**另两处未登记的消费面（ISSUE-918，2026-10-01 强制，与五处同批）**：① 同文件 `_do_update_preview` 读 `get_config` 输出的别名键 `btype = pdef.get('type', '?')`（[config_panel.py:6046](gacha_simulator/gui/config_panel.py#L6046)）——改名后 GUI 预览里**每条保底的类型都打印 `?`**，而 `preview_text` 全库无测试断言（`grep -rn preview_text` 仅命中 config_panel.py 自身），属**静默失真**；② [tests/gui/test_config_panel_pity.py:220](tests/gui/test_config_panel_pity.py#L220) 的 `assert "type" in pdef` 是**正断言该别名键存在**，改名即必红。<!-- REVIEW-R1-FIX: ISSUE-918 -->
  - 验收命令：`pytest -q tests/gui/test_config_panel_pity.py`——既有 GUI 端到端集成用例（链路 = 加载 TOML → `_refresh_from_store_impl` → `_on_pity_selected` → `_apply_pity_edit` → `apply_to_store` → `get_config`）；**新增用例**：编辑 preset 参数（如 `hard` 的 `threshold`）→ 保存 → 重载后控件值一致，且新 type `rotating_inverse` 出现在保底 type 下拉（**前提 = S6a 的生成式改造已落地**，届时自动出现；**若该改造未落地，本断言改为「`_PITY_TYPES` 中已手工含 `rotating_inverse`」**，二者与 §3.6 / S6a 同源）<!-- REVIEW-R1-FIX: ISSUE-929 -->；**存量用例同批改造（ISSUE-918，强制）**：`tests/gui/test_config_panel_pity.py:220` 的 `assert "type" in pdef` 为正断言别名键存在，须改为 `assert "btype" in pdef`，并补一条 `_do_update_preview` 的预览文本断言（改名后类型不再打印 `?`）。<!-- REVIEW-R1-FIX: ISSUE-918 --><!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-6-测试策略 -->
- [x] **S7b 跨进程 pickle round-trip**（~0.3 人时）｜目标文件 `tests/service/test_batch_simulator.py`（既有文件，pickle 用例已在该文件内，且 `run_batch_parallel` 的 `MPPool` 入口即在此模块；ISSUE-003）
  - 对 `env`（或 `env.pity_engine`）做 `pickle.dumps` / `loads` 断言，覆盖 `Pity` / `Tracker` / `Modifier` / `Lifecycle` **四族**对象（**ISSUE-731**：原写「五族」含 `Condition`，该类族已随 §3.14 改判取消）。**`InvariantChecker` 的 round-trip 不在本步（GATE-check-3，2026-10-09 修正）**：该类与 `PityEngine(invariants=…)` 形参由 **S11** 产出，而 S11 排在本步之后（§七 强制顺序串的末位），本步引用它即 `ImportError`、pytest **收集期**即红；该用例已移入 S11 的专属文件 `tests/core/test_pity_invariant_checker.py`（见 §七 S11 的验收命令）。**旧稿的反指同时删除**：S11 原写「S7b 的 round-trip 覆盖已含 InvariantChecker」，把下游指向了排在它之前的块。禁 lambda / 闭包 / 不可 pickle 成员（否则并行度静默归零，见 §四 专项）<!-- REVIEW-R1-FIX: GATE-check-3-依赖顺序 --> <!-- REVIEW-R1-FIX: ISSUE-731 -->
  - 验收命令：`pytest -q tests/service/test_batch_simulator.py -k pickle`——新增用例覆盖**四族**对象（`Pity` / `Tracker` / `Modifier` / `Lifecycle`；**ISSUE-731：原写「五族」，`Condition` 族已取消**）各一条 round-trip（`dumps` → `loads` → 逐字段相等）（**GATE-check-3：`InvariantChecker` 的 round-trip 已移出本步、归 S11**，见上条与 §七 S11 验收命令——本步落地时该类尚不存在），并补一条「worker initializer 实际收到可用的 `env`」冒烟断言（现有 `run_batch_parallel` 的降并发重试会把不可 pickle 静默吞成单进程兜底，故必须显式断言并行度未退化）<!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-6-测试策略 -->
<!-- REVIEW-FIX-PREV: ISSUE-017 -->
- [x] **S7c 手册示例 + 文档同步 + pytest 全量**（~0.5 人时）｜目标文件 `CLAUDE.md` + `docs/00-meta/模块状态矩阵.md` + 手册（ISSUE-017）+ **`docs/01-活跃/subsystems/保底系统/` 五件**（`00-档案.md` / `01-理论.md` / `02-实施.md` / `03-审计.md` / `04-问题.md`；**ISSUE-927**：原清单未列子系统文档，同步面与 §四 的三件新增行同口径，见下条）
  - `CLAUDE.md` 保底章节与「新保底行为」一行改写；模块状态矩阵 P64 行摘要补 G3 / S9 / S10 / S11 与 M1/M2 划分（**ISSUE-004：S12 已于 2026-10-06 取消，不进摘要**）。**订正（S7c 落地后回写，2026-10-13）**：§四 该文件的核对行已写「**该『更新点』已不存在**」（矩阵 P64 行实测早已含 G3 / S9 / S10 / S11 与 M1/M2 划分、且已注明 S12 取消），故 S7c 只补了一条核对记录、未新增重复内容；子系统文档同步（ISSUE-028 / **ISSUE-927**）：该目录实测**六件**（`00-档案.md` / `01-理论.md` / `02-实施.md` / `03-审计.md` / `04-问题.md` / `05-笔记.md`，其中 `05-笔记.md` 由 H4 自动维护）——**同步面为五件**：`01-理论.md`（§2.1 执行顺序）与 `02-实施.md`（§一 代码位置行号表 + §2.1）按涉及面刷新，**另补 `00-档案.md` / `03-审计.md` / `04-问题.md`**（实测前两者含 `scope_slots` / `PoolPitySpec` / `SoftPityMixin` 等 P64 结构性删除对象的记述，后者是「已处置 / 去向」的索引依据；对照 P83 计划的同步面即为六件齐列）；**措辞更正**：原写「子系统三文件」与目录实际件数不符，「三文件制」的提法仅指文档体例，不代表同步面只有三件
  - 验收命令：`pytest -q` 全量通过
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-7 -->
- [x] **S7d 存量保底测试文件改造（旧类直构 → 新架构）**（~0.5 人时）｜目标文件 `tests/test_pity.py` + `tests/core/test_pity_validate_behaviors.py` + `tests/core/test_pity_rotating.py` + `tests/core/test_pity_integration.py` + `tests/core/test_pity_lifecycle.py` + `tests/core/test_pity_targeted.py`（**6 个存量文件** + **`tests/core/test_pity_rebind.py`**（**必改**，非「若引用」——见下条；**ISSUE-924**）；`tests/test_p60_pity_state.py` **已核实无需改动**（只 `from gacha_simulator.core.pity import PityState`，`pity.py` 保留 re-export，语义不变））
  **AUDIT-BREAK-7：本批文件在原计划里只出现在 §四 的泛写「tests/ 新增/修改」行与 §3.9.3 的槽位消费统计里，§七 **无任何子块**承接——而它们是**模块级** `from gacha_simulator.core.pity import (...)` 直取旧行为类并**直构**（实测 import 清单：`test_pity.py` 取 `HardPityBehavior` / `SoftStepBehavior` / `create_behavior` / `PoolPitySpec`；`test_pity_validate_behaviors.py:45-140` 直构 `_engine([PityDef(...)])` 并在 :97-99 直调 `create_behavior`；`test_pity_rotating.py` 取 4 个 Rotating 族类 + `_redistribute_scope`；`test_pity_integration.py` 取 3 个旧类 + `compute_scope_mappings`；`test_pity_lifecycle.py` 取 `HardPityBehavior`；`test_pity_targeted.py` 取 targeted 两族类）。**
  - **失败时点须写准（勿按原稿的「S4-3 后即 ImportError」施工）**：旧类**本体**保留到「发布前一次性移除」（GATE-5 末条），故 S4-3 **不**让这批文件崩——真正的崩点是 **①「发布前移除旧类」那个 commit**（`from gacha_simulator.core.pity import HardPityBehavior` 立即 `ImportError`，**pytest 收集期**即失败、H9 直接拦死），以及 **②「发布前移除旧类」的同一 commit**（**ISSUE-906 修正，2026-10-01**：原稿写「②S8 删槽位字段 / 替换 `_redistribute_scope` 时（构造带槽位字段的 `PoolPitySpec`、调用已删函数）」——按 ISSUE-901 改判后，S8 **不删**槽位字段、也**不删**函数本体（S8-4 只删 `core/__init__.py` 的导出，而本批文件是自 `gacha_simulator.core.pity` 直接 import，不受导出面影响），该句已不成立。故 S7d 的断裂点只有**一个时点**：①与②是**同一个 commit**，不是两个）。<!-- REVIEW-R1-FIX: ISSUE-906 -->故 S7d 与 M2 的 S8-7 是**两个时点、两批文件**，不得合并成一项。
  - 本步（S7d）改造范围：把「直取旧类」改为**经新架构构造**（`create_behavior(PityDef(...), state)` 取 `Pity`），保留全部既有断言语义（N1 / M4 / 生命周期 / 阈值行为 / **rebind 纯重定向（不复制旧值）** / **跨模拟隔离（sim1 → sim2 从初始态起）** / **交错时序自愈**——后三条由 `tests/core/test_pity_rebind.py` 承担（P75 回归），原本只写在该文件的 docstring 里、**不在原清单内**，据清单派工会整条漏掉，**ISSUE-924**）；**例外**：`tests/core/test_pity_equivalence.py` 的 harness 仍可直接 import 旧类（§3.2 GATE-3(c) 定稿，那是等价性装置的「旧」侧，不得改造）
  - **`tests/core/test_pity_rebind.py` 是必改项而非可选项（ISSUE-924，2026-10-01）**：该文件 :10-13 是**模块级** `from gacha_simulator.core.pity import (PityState, PityEngine, SoftStepBehavior, HardPityBehavior, RotatingBehavior, TargetedBehavior)`（4 个旧行为类），并以 4 个工厂函数直构这些类、直接断言 `engine._behavior_list` / `bh._state` / `bh._counter()` / `engine._state is a`（P75 纯重定向 + 跨模拟隔离语义）。故它是「发布前一次性移除旧类」那个 commit 的**必崩点**（`pytest` **收集期**即 `ImportError`，H9 直接拦推）——与 S7d 的触发条件同一条。原稿的「若引用被改符号同批处理」把**必改**降级为**可选**，且把无关的 `test_p60_pity_state.py` 并列其中（条件恰好写反）。<!-- REVIEW-R1-FIX: ISSUE-924 -->
  - 触发条件（强制）：**「发布前一次性移除旧类」的 commit 之前必须已完成 S7d**——否则该 commit 一落地 pytest 全红，回滚粒度被破坏
  - 验收命令：`pytest -q tests/ -k pity` 全绿；`grep -rn "HardPityBehavior\|SoftStepBehavior\|RotatingSoftBehavior\|RotatingCRBehavior\|RotatingCRSoftBehavior\|TargetedBehavior\|TargetedSoftBehavior\|CounterBasedBehavior\|SoftPityMixin" tests/` 的命中**只允许**出现在 `tests/core/test_pity_equivalence.py`（等价性装置）
  <!-- P64-S7D-CLOSURE -->
  **验收命令订正（S7d 落地后回写，2026-10-13，S7d 审查）**：本命令原列 **6 个符号**，而「发布前一次性移除旧类」的待删集合是 **10 个**（原 6 个 + `RotatingSoftBehavior` / `RotatingCRSoftBehavior` / `TargetedSoftBehavior` / `CounterBasedBehavior`）。**这个缺口使该命令作为门控本身不完整**：后 4 个符号的命中一律不可见。实测后果：`tests/core/test_pity_config_toml.py` 的 `TestDuplicatedConstants` 两条（`:510` / `:516`）函数局部 `from gacha_simulator.core.pity import CounterBasedBehavior` 并读其类属性 `_SOFT_SUFFIX_TYPES` / `_EVENT_DRIVEN_TYPES`，是**第 4 个真实断裂点**，在原 6 符号模式下自检抓不到。**本命令已按 10 符号补齐**（上行为准）。
<!-- P64-S7E-LANDED -->
**S7e 已落地（`71ea8cf`，2026-10-13）**，独立审查 `APPROVED_WITH_CONCERNS`。实测：**11 条对照断言 / 20 条 golden case** 已固化入 `tests/fixtures/p64_s7e_golden.json`（`test_pity_modifier.py` 6 处 15 条 / `test_pity_tracker.py` 4 处 4 条 / `test_pity_registry_schema.py` **1 处**）。
**审查纠正了本块范围的一处提示**：检索式粗查曾得「registry 有 3 处对照点」，实测**等价性对照只 1 处**（与本计划 GATE-5 ⑧ 列的单点 `:764` 一致）；该文件其余 5 处旧类引用是**旧类兼容分支的守卫**（`_LegacyKwargsProbe` / `test_legacy_branch_still_works` / `test_legacy_branch_no_longer_injects_lifecycle` / `test_no_preset_and_class_none_raises_value_error`，以及模块级 import），**不该固 golden**。
**审查新增的删除点动作（本人须补入 ⑧ 的清单）**：`_assert_matches_golden` 在删除点**必须改写签名**（去掉 `expect` 形参与其第三个断言），这不是「删一段」能自然覆盖的动作。
**审查登记的边界**：① 摘要闸只盖 `expected`、**不盖 `input`**，而删除点之后只剩各用例自带的 input 断言（且基线三条的 `counter` / `threshold` / `target_feature`、randomised 的 `rng_seed`、registry 的 `state_probs` **均无** input 断言）；② `modifier.randomised.hard.ssr.*` 两条的 `effective` 与既有 `modifier.hard.target_scope` / `target_featured` **逐位相同**，故对本断言的**增量判别力为零**，不得当作独立覆盖点计入。

<!-- P64-S8-CLOSURE -->
**modifier 面的 golden 已随 S8 退役（2026-10-14，需裁决记录）**：`tests/fixtures/p64_s7e_golden.json` 的 **15 条 `modifier.*` 条目**随 S8-1/2/3 的原子 commit 退役（20 条剩 5 条：tracker 4 + registry 1），理由是那 15 条固化的是 **M1 槽位级**形态、其唯一消费者（`tests/core/test_pity_modifier.py`）已整体改写为卡级显式期望值。**后果**：本块「趁旧类存活固化 golden、供 GATE-5 末条的旧类删除点使用」这一立块目的**对 modifier 面落空**（槽位级 golden 与卡级新侧不同键空间，删对照段后保留 golden 断言的动作**已不可执行**）。**已按最合理读法定案（可随时推翻）**：接受退役，modifier 面的位级判据改由 **S8-6 的等价性装置**承接；GATE-5 ⑧ 与 S7e 条的措辞须按此回写。**替代方案（若你要求保住 S5 参考面）**：把那 15 条改为**只对旧类**的冻结断言（`old_class_output == golden`），在 GATE-5 删除点一并删除。
- [x] ~~**S7e 等价性装置 golden 固化（S7d 审查新增，2026-10-13）**~~（~0.4 人时）<!-- P64-SELFCHECK-F1 -->
      **读法消歧（统一自查，2026-10-15）**：本行的 `[x]` **+** 删除线**不是「已取消」**（本计划另有 5 条「`[x]` + 删除线 = 已取消」，写法相同故易误读）：S7e **确实交付**（`71ea8cf`，`tests/fixtures/p64_s7e_golden.json` 现存 5 条），删除线标记的是「其 modifier 面 15 条 golden 已随 S8 退役」。｜目标文件 `tests/core/test_pity_modifier.py` + `tests/core/test_pity_tracker.py` + `tests/core/test_pity_registry_schema.py`（+ 落盘 golden 数据）
  **为什么必须独立成块且必须排在 GATE-5 末条之前**：这三处用例的断言对象**就是旧实现**（「新 Modifier / Tracker 与旧类逐位相等」），它们与 `test_pity_equivalence.py` 同类，是**等价性装置**。旧类一删，既无法再生成对照值、也无法再跑对照断言。故必须**趁旧类存活**把对照结果**固化为 golden 数值**（写入 `tests/fixtures/`），此后删除点只删「构造旧类并对照」的那一段、保留 golden 断言。
  - **本块与 S7d 的关系**：S7d 处置「直取旧类」的**模块级 import**（6 个点名文件）；本块处置**等价性装置的三个未承接文件**，是 S7d 验收 grep 的**例外面**，故不改写它们的旧类 import。
  - **回滚单元独立**（GATE-5 回滚段）：本块只新增 golden 数据与断言，回退即删该数据与断言，无连带。
  - 验收命令：`pytest -q tests/core/test_pity_modifier.py tests/core/test_pity_tracker.py tests/core/test_pity_registry_schema.py` 全绿；**牙齿**：把某个 golden 数值改错，对应用例必红。
  - **与 GATE-5 末条第 ⑧ 项的对应**：⑧ 的「先固化为 golden」指的就是本块的产物。

**保障层（与核心同批完成，否则核心缺验收与守门手段；逐子块独立 commit）**
<!-- REVIEW-FIX-PREV: ISSUE-GATE-granularity -->
- [x] S10 **组合正确性验收**（合计 ~0.9 人时，方案见 **§3.12**）：
  - [x] S10-1 不变式性质测试（~0.5 人时）：随机组合零件，断言归一性 / 非负性 / 增量合法性 / 状态键合法 / 确定性（§3.12.1）｜目标文件 `tests/core/test_pity_invariants.py`（新增）
    - 验收命令：`pytest -q tests/core/test_pity_invariants.py`——五条不变式各一组断言，与 §六「S10 组合正确性」条一一对应；归一性按 **scope 感知**口径（`Σp = 1 + Σp(被 F 豁免的更高稀有度槽位)`，无 F 参与时退化为 `Σp = 1`）。**该口径只对 M1 槽位级管道成立**（ISSUE-903）：S10 属 M1，故本步按 scope 感知式实现；**S8 起 `_apply_delta` 归一化到 `Σp = 1`，同一断言须随之改写**，改写点登记在 M2 的 S8-6（⑤）<!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-6-测试策略 --> <!-- REVIEW-R1-FIX: ISSUE-903 -->
  - [x] S10-2 合法组合判据 + 构造期检查（~0.4 人时，与 `_validate_behaviors` **同模块层**，§3.12.2）
    <!-- P64-S10-2-CLARIFY -->
    **措辞澄清（S10-2 落地后回写，2026-10-13，S10-2 审查裁定）**：本行原写「与 `_validate_behaviors` 同层」，而 §3.12.2 把判据 1 的检查点写死在 `Pity.__init__`（理由「数据是 per-Pity 的，无需引擎上下文」）。实施者报此为「计划内部张力」，审查裁定**二者不冲突**：本行的「同层」「不新建模块」指的是**模块层**（`_check_declared_keys` 确实定义在 `pity.py` 内、紧邻 `_validate_behaviors`），而**调用点**在 `Pity.__init__`，实现**同时满足两者**；所谓张力来自把「同层」误读成「同一调用点」。**§3.12.2 的检查点表述不必改，本行的口径也不变，此处只补注以免后续读者重蹈误读。**审查另实测：判据 1/2 的引擎层负例确实写不出（`PityEngine` 只收 `PityDef`、无 preset 能产出这两种非法组合），但**判据 3 的引擎层负例可写**（两个 `PityDef` 的 `depends_on` 互指即在引擎路径抛 `ConfigError`），故实施者当初「三条负例不可写」的理由只适用于判据 1/2。｜目标文件 `core/pity.py`（判据的构造期检查与 `_validate_behaviors`（[pity.py:931-982](gacha_simulator/core/pity.py#L931-L982)）同层，落在此处、不新建模块；`_build_activation_graph`（[pity.py:1203-1227](gacha_simulator/core/pity.py#L1203-L1227)）内补成环检测）+ `tests/core/test_pity_invariants.py`（用例，与 S10-1 同文件、按 `-k` 过滤）。**ISSUE-501（强制）**：判据 1/2 的输入是 `Pity._declared_keys`（三族 `state_keys()` 的汇总，§3.1.4 骨架已写入），本步只落两条 `ConfigError` 的检查本体与用例；**不得**在 S10-2 内另做「怎么取声明集」的决定——三族接口与汇总点已定稿，改口径即三处（§3.12.1 / §3.12.2 / §3.13）失配 <!-- REVIEW-R1-FIX: ISSUE-501 --><!-- REVIEW-R1-FIX: ISSUE-001 --><!-- REVIEW-R1-FIX: ISSUE-002 -->
    - 验收命令：`pytest -q tests/core/test_pity_invariants.py -k "illegal or cycle"`——三类判据各一条**负例**，均须在**构造期**抛 `ConfigError`：① 同一键被两个 Tracker 声明（如两个 `CounterTracker` 都写 `counter`）；② Modifier 引用不存在的状态键（**读键取自它自己的 `state_keys()` 声明集**，§3.14 条件内联后不再有独立的 Condition 读键；**GATE-check-6，2026-10-09 修正**：原稿在此设 ②b「一个引用非法键的 **Condition**（`CounterCondition('countr', τ)` 套在 `ConditionalModifier` 内）」并称其为 ISSUE-902 的关键用例，而 Condition 类族与 `ConditionalModifier` 均已随 §3.14 改判取消、ISSUE-902 的纪律同批删除，该用例**无对象可写**）——负例一条：②a 一个引用非法键的 Modifier；③ `depends_on` 成环（**成环检测为新增能力**——现状 `_build_activation_graph` 只校验指向存在的名字，不做环检测）<!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-6-测试策略 --> **GATE-6-测试策略（2026-10-01 补：命名约束 + 收集守卫，同 ISSUE-920 口径）**：`tests/core/test_pity_invariants.py` 是 S10-1 / S10-2 共用的**新增**文件，本命令的命中项须**全部**为下列**三条**负例（用例名已写死，实施时以此为准；若改名，须同步改本命令的过滤词）：① `test_illegal_duplicate_key_across_trackers`、② `test_illegal_unknown_key_in_modifier`、③ `test_cycle_depends_on`（过滤词 `illegal` / `cycle` 分别落在用例名内）。落地时先以 `--collect-only` 确认**收集到 ≥3 条**（下列三条各一），零命中时 pytest 以 **exit code 5** 结束、会被误读为通过。**GATE-check-6（2026-10-09，强制）**：原列的 ②b `test_illegal_unknown_key_in_condition` 与「收集到 ≥4 条」守卫已删——②b 的断言对象已不存在，保留「≥4 条」会把实施者逼到「造出第 4 条」或直接失败，属本纪律 ③ 的镜像失效面（不是假通过，而是**逼出假用例**）<!-- REVIEW-R1-FIX: GATE-check-6-测试策略 --> <!-- REVIEW-R1-FIX: GATE-6-测试策略 -->
- [x] S11 **不变式运行时校验**（~0.8 人时，方案见 **§3.13**）：可开关的 `InvariantChecker`，覆盖分布 / 状态 / 增量 / 生命周期四层；生产关闭。**开关载体见 §3.13 的「校验开关的载体」段（ISSUE-945）**：`enabled: bool` 构造形参、随实例进 pickle（§七 **S11** 的 round-trip 覆盖已含 `InvariantChecker`，该用例随 S11 落在 `tests/core/test_pity_invariant_checker.py`；**GATE-check-3，2026-10-09 修正**：原写 S7b，而 S7b 排在本步之前、其时该类尚不存在），**禁止模块级全局开关**｜目标文件 `core/invariants.py`（新增）+ **`core/pity.py`（调用点与 `PityEngine(invariants=…)` 形参，ISSUE-003）** + `tests/core/test_pity_invariant_checker.py`（新增，**专属测试文件**） <!-- REVIEW-R1-FIX: ISSUE-945 -->
  - **调用点、挂载层与开关来源（ISSUE-003，强制）**：checker 实例挂 `PityEngine._invariants`（构造形参 `invariants=None` 为默认关闭态），调用点 = `PityEngine.before_draw` / `after_draw` 各一行；`enabled=True` 只由**测试夹具**产出（不加 env 字段 / CLI 开关 / TOML 项）。**增量层不复用这两个入口**——S8 起改由 `check_delta(pool_id, dist, delta)` 在 ~~`_apply_delta()` 内部~~ **`Pity.before_draw` 的内循环**自查（**落点订正，S8-6 审查 2026-10-14**：`_apply_delta` 已迁叶子层、取不到 `pool_id` 与 engine；校验器经 `PityContext.invariants` 进骨架、只由 `PityEngine.before_draw` 写）（该处 p 与 δ 同时在手），本步（M1）不启用该层。完整分工见 §3.13 的「调用点与构造源」段 <!-- REVIEW-R1-FIX: ISSUE-003 -->
  - **验收命令追加两条（ISSUE-003，强制）**：① `PityEngine(..., invariants=InvariantChecker(enabled=True))` 的替身（计数用子类）在跑一次 `before_draw` / `after_draw` 后，断言两个入口**被实际调用**至少各一次——**不得只断言「类存在」**；② `invariants=None` 时断言引擎不建实例、两个入口零调用<!-- REVIEW-R1-FIX: ISSUE-003 -->
  - 验收命令：`pytest -q tests/core/test_pity_invariant_checker.py`（**GATE-check-3：另含一条 `InvariantChecker` 的 pickle round-trip**——`dumps` → `loads` → `enabled` 字段相等；该用例由 S7b 移入本步，S7b 的 `-k pickle` 不再包含它）。**正例**：`hard(scope='sr')` 的合法配置（Σ = 1.009）不得报错（归一性按 scope 感知口径）；**负例**：人为把卡概率改负 / 把 Σ 改到 1.2 / 在白名单外写 `_active`，必须抛错且异常信息含**保底名 + 键 + 期望值 / 实际值**三要素
  - **原稿缺口（GATE-6）**：S11 在 §六 无任何断言行、§七 无验收命令、§四 无专属测试文件行，而 §七 的 M1 完成标志却把「不变式校验（S11）到位」列为交付条件之一；三处已同步补齐（§六「S10 / S11（保障层）」段、§四 测试文件行）<!-- REVIEW-FIX-PREV: ISSUE-GATE-test-strategy -->

> **M1 完成标志**：全部 10 个类型与旧类**逐场一致**（§六 主线口径）；G1 / G5 可用；GUI round-trip 通过；组合验收（S10）与不变式校验（S11）到位。**此时架构已统一且带保障，项目处于可交付状态**；M2 尚未开始不影响可用性。
#### M2：表达力扩展（S8 + S9；依赖 M1 完成）

<!-- P64-S8-LANDED -->
> **S8-1 / S8-2 / S8-3 已落地（原子单元，单 commit `f18045f`，2026-10-14）**，独立审查判 `APPROVED_WITH_CONCERNS`（7 条发现，无一构成实现侧的正确性缺陷）。实测：全量 `2915 passed / 35 skipped`；`p79_verify` 与 `p82_baseline --verify` 均 PASS 且**零漂移**（未重生成任何 golden）；8 处变异全红。
> **原子单元按计划强制执行**：三块同一个 commit（不采用「S8-3 前移到 S8-2 之前」的备选，因它同样躲不掉键空间错位窗口）。**回滚约束**照计划：回退任一方须连带回退另外两方。
> **本单元的交付面超出三块声明的目标文件**：为让全量转绿，同批改写了 `tests/` 下 8 个存量文件（`test_pity.py` / `test_pool.py` / `test_worst_impact.py` / `test_pity_lifecycle.py` / `test_pity_registry_schema.py` / `test_retreat_config.py` / `test_pity_targeted.py` / `test_pity_integration.py`），故 **S8-7 的剩余面须重算**（见其条目）。
> **提前执行的项（时点偏移，原登记在更晚的块）**：**S8-6 ⑤**（`core/invariants.py` 分布层判据由「scope 感知式 + 可达取值集」改为恒等 `Σp = 1`，同批删 `_exemption_options` / `_EXEMPTION_PART_TYPES` / `_DrawProbe`，`tests/core/test_pity_invariant_checker.py` 与 `tests/core/test_pity_invariants.py` 随之改写；S11 收口的里程碑绊线用例替换为 `test_issue_903_reversal_is_landed`）；**S8-4 的一部分**（`core/__init__.py` 删 `infer_rarity_from_spec` 的 import 与 `__all__` 条目，理由见 S8-2 条）；**S8-6 登记的部分用例面**（单卡定向、空目标集）。**提前的唯一理由是「不提前则全量必红」**，已由审查确认其中的判据改写属**收紧**（新判据的接受集严格包含于旧的可达取值集）。

- [x] S8 **概率操作路径重构**（合计 ~4.0 人时；方案见 **§3.9**，声明见 §3.1.2 D20，数学形式见 §3.1.5）｜**逐子项独立 commit，回滚单元 = 子项**（GATE-1 / GATE-5）。**跨文件面（7 个源文件 + 1 批测试）**：`core/pity.py` / `core/banner.py` / `core/pool.py` / `core/worst_impact.py` / `service/batch_simulator.py` / `core/__init__.py` + **`tests/`（5 个槽位结构消费文件，见 S8-7）**。**AUDIT-BREAK-5 / 6 / 8**：`core/pool.py`（`aggregate_probs_by_rarity` 定义与内部调用）、`core/__init__.py`（import 块 + `__all__` 双改）、`core/worst_impact.py`（第二处 `PoolPitySpec` 构造点 + 其槽位实参）**均为本步目标文件**，逐处清单见 §3.9.3 的「跨文件同步清单」——漏改即 `ImportError`，不得因「主调用点在 banner.py」而只改一处。 <!-- REVIEW-R1-FIX: ISSUE-955 -->
  - [x] S8-1（**已落地**：单 commit `f18045f`）Modifier 接口改为 `compute_delta(...) -> Optional[增量向量]`，`_apply_delta` 做归一化（~0.5 人时；§3.9.2）｜目标文件 `core/pity_modifier.py` + `tests/core/test_pity_modifier.py`（新增）。**ISSUE-505（强制）**：内循环的 view 实参**一律经 `self._view_for(mod)`**（继承 §3.1.4 骨架的 M1 形态，只换方法名、不改取值方式），**不得写死 `self._view`**；本步须含一条 `namespace` 非 `None` 的 Modifier 用例（默认情形下无行为差异，缺口只在声明命名空间的零件上显形，**无该用例则本形态无验收面**；端到端比对本步无专属命令，用例挂 S8-6 的 ④）<!-- REVIEW-R1-FIX: ISSUE-505 -->
    - 验收命令（GATE-6 补，块级最小验收——S8 逐子项回滚时须按 GATE-5 重跑本命令，无块级命令则该条无法执行）：`pytest -q tests/core/test_pity_modifier.py`——三形态覆盖：`compute_delta(...)` 返回 `None` / `{}` / 非空增量时 `_apply_delta` 的归一化结果；**含一条 `namespace` 非 `None` 的 Modifier 用例**（经 `self._view_for(mod)` 取 view，端到端比对仍挂 S8-6 的 ④）<!-- REVIEW-R1-FIX: ISSUE-931 -->
  - [x] S8-2（**已落地**：同上 commit）管道改传卡级分布：`banner.py` 删除 `aggregate_probs_by_rarity` 调用与 `scale_factors` 还原段（~0.4 人时；§3.9.1）｜目标文件 `core/banner.py` + `core/pool.py`。<!-- REVIEW-FIX-PREV: AUDIT-BREAK-5 -->**三处同步（缺一即 `ImportError`）**：① [banner.py:209](gacha_simulator/core/banner.py#L209) 的**函数局部 import**（只在 `draw()` 被调时执行，导入期与 ruff 都不报错）；② [banner.py:227](gacha_simulator/core/banner.py#L227) 调用 + :229-246 `scale_factors` 段 + :242/:244 slot 推导（`infer_rarity_from_spec` 的槽位反查用途）；③ [pool.py:254](gacha_simulator/core/pool.py#L254) 的 `aggregate_probs_by_rarity` 定义与 :280 / :285 内部调用（**本轮 AUDIT-BREAK-4 订正**：原写 `:270/:275` 为错值——实测 :270 是 `if pity_spec and pity_spec.scope_cards:`、:275 为空行，两处 `infer_rarity_from_spec` 消费在 :280 与 :285，与 §3.9.3 表第 3 行一致；原值偏 10 行且落在非空白行，故计划的空行机核抓不到）<!-- REVIEW-R1-FIX: AUDIT-BREAK-4 -->，**以及 [pool.py:234](gacha_simulator/core/pool.py#L234) 的 `infer_rarity_from_spec` 定义**（**ISSUE-504：零消费者，随本步一并删**，其导出条目归 S8-4）<!-- REVIEW-R1-FIX: ISSUE-504 -->。**:257 的 `after_draw` 调用保留**（与概率管道无关）<!-- REVIEW-R1-FIX: ISSUE-001 -->
    <!-- P64-S8-CLOSURE -->
    **切分订正（S8 收口，2026-10-14）**：本行原把 `infer_rarity_from_spec` 的处置切成「**定义**归 S8-2、**导出条目**归 S8-4」，该切分**不可执行**：该函数被 `core/__init__.py` 的 import 块直接引入，只删定义即 `import gacha_simulator.core` 失败（实测报 `ImportError: cannot import name 'infer_rarity_from_spec' from 'gacha_simulator.core.pool'`），而这正是本计划自己列的「缺一即 `ImportError`」失效形态。**故定义与导出条目同批在 S8-2 删除**，S8-4 不再处理该符号（其 `__all__` 条目已随本批消失）。
    - 验收命令（GATE-6 补，块级最小验收）：`python -c "import gacha_simulator.core.banner"` 冒烟（函数局部 import 的删除不在导入期暴露，故须**真跑** `pytest -q tests/test_banner.py`——banner 抽卡路径现有用例全绿，含 `draw()` 被实际调用）<!-- REVIEW-R1-FIX: ISSUE-931 -->
  - [x] S8-3（**已落地**：同上 commit）`_redistribute_scope` 替换为卡级版 `transfer_linear`（含 `shape` 双分支与全部守卫），语义切为「A 内形状由机制声明」（~0.7 人时；§3.9.4）｜目标文件 `core/pity.py`。**2026-10-09 预算由 0.5 调为 0.7**：原 S8-3b 取消后，其实现面（`shape='declared'` 分支 + `weights` 形参 + `p(A) <= 0` / `w(A) <= 0` / 目标集为空三处守卫，即原 ①③ 两条纪律的落地）并入本步——原 S8-3 的表述只写了 `current` 一侧（「语义切为『A 内按当前形状分配』」），而 §3.9.4 定稿的 `transfer_linear` 是**双分支 + 三守卫**的完整函数，缺 `declared` 一侧则 §3.1.2 表中三个取 `declared` 的机制（`HardModifier(target_featured=true)` / `NonFeaturedModifier` / `SelectedModifier`）无实现落点。**ISSUE-502（强制，二择一已定稿）**：本步**只新增 `transfer_linear` 并让新骨架改用它**，`_redistribute_scope` 的**函数本体保留**（pity.py 内 4 处旧类调用点 :549 / :661 / :727 / :731 仍依赖它（2026-10-09 实测订正：原写 `:477 / :589 / :655 / :659`，整体 +2）<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->），与 `transfer_linear` 并存到「发布前一次性移除旧类」的 commit；S8-4 只删其 `core/__init__.py` 导出，**不动函数本体**。**若改选「S8 一并删函数本体」，则必须同 commit 处理那 4 处调用点**（改为 `transfer_linear` 会让旧类语义从槽位级变卡级，S5a harness 的「旧实现」对照基准随即失效）——该路线与 S8-6 的「对 S5 产物容差 1e-12」自相矛盾，故不采纳。<!-- REVIEW-R1-FIX: ISSUE-502 -->
    <!-- P64-S8-CLOSURE -->
    **行号订正（S8-4 审查，2026-10-14）**：4 处旧类调用点的真值为 `pity.py:549 / :661 / :727 / :731`（`RotatingBehavior.before_draw` / `RotatingCRBehavior._force_featured` / `TargetedBehavior.before_draw` 两处），实测在 `0f60328` 与 `4508d78` 上一致。本计划此前写的 `:475 / :587 / :653 / :657` 以及自述的「2026-10-09 实测订正（原写 `:477 / :589 / :655 / :659`，整体 +2）」**均为错值**（475 是 `_redistribute_scope` 的段注释行号，非调用点），已全篇替换为真值。
    - 验收命令（GATE-6 补，块级最小验收）：`pytest -q tests/core/test_pity_rotating.py -k transfer_linear`——固定输入下 `transfer_linear` 与 `_redistribute_scope` 在**单槽位 / 组内等权**场景逐元素相等（两者的语义差别见 §3.9.4 三点；跨槽位或不等权场景改按增量向量断言，不要求逐元素等值）<!-- REVIEW-R1-FIX: ISSUE-931 --> **GATE-6-测试策略（2026-10-01 修订，原命令不可用）**：原写 `-k redistribute` 实测命中 `TestRedistributeScope` 的 **3 条既有用例**（`test_full_featured_ratio` / `test_half_featured_ratio_preserves_proportions` / `test_zero_total_ratio_math`，靠类名子串命中），这 3 条只调用旧 `_redistribute_scope`（模块级 import [test_pity_rotating.py:16](tests/core/test_pity_rotating.py#L16) 与 :401 / :410 / :419 三处调用），结果是**退出码 0、全绿，而本步要验的 `transfer_linear` 零覆盖**。故过滤词改为 `transfer_linear`，本步新增用例名须含它（建议 `test_transfer_linear_matches_scope_equivalent`（单槽位 / 组内等权逐元素相等）+ `test_transfer_linear_ratio_preserving`（跨槽位或不等权按增量向量断言）），**目标文件补 `tests/core/test_pity_rotating.py`**；落地时确认收集到 ≥1 条且命中项全部为本步新增用例 <!-- REVIEW-R1-FIX: GATE-6-测试策略 -->
  - [x] ~~**S8-3b `factor_override`（assign）与 `resolve_universe` 落地**~~（**2026-10-06 随 §3.9.4 改写作废；2026-10-09 三条纪律的去向定稿、预算清零**）（原 ~0.5 人时；§3.9.4，2026-10-05 补）：两个卡级原语已合并为助手 `transfer_linear`，「assign 形态」不再作为独立原语存在。**三条纪律的去向（原「待人工确认」的落地）**：**①**（目标值按口径 3、必须除以 `gt`）**无实现面**——`factor_override` 与其「`∝ w_c·p_c`」形态已不存在；新形态由 `transfer_linear(shape='declared')` 的 `u_A = w_c/w(A)` **加性**分配承担，是**一次**比例而非平方（三案推演 §4.4 已证：修正 ① 的结论不适用于加法形态）；**②**（`resolve_universe` 统一构建 `u_cards`、不得现算 `exempt`）**随解析器族消失**——A/Q 内联进各类方法体（原 S2b 已并入 S2a-1 / S2a-2），「两套键空间」与 `rarity_rank.get(scope, 99)` 魔数均无落点；**③**（空目标集返 `None`）**落在 `transfer_linear` 自身**（`pQ <= 0` / `amount <= 0` / `pA <= 0` / `wA <= 0` 四处防御性返回，§3.9.4 前置条件表）**与各类方法体开头的早退**（§3.9.4 三个调用示例）。**预算去向**：原 0.5 中 **0.2 并入 S8-3**（`declared` 分支与三处守卫的实现）、**0.3 并入 S8-6**（原验收命令所载的六场景逐卡对照）。**验收命令的去向**：原写 `pytest -q tests/core/test_pity_primitives.py -k "assign or universe"`——该文件（原拟新建）**不存在**，`assign` / `universe` 两个符号亦不存在；其载的**六场景逐卡对照**（`scope` × `tf` 全组合、`scope` 不在 `[rarities].ranks` 内抛 `ConfigError`、空目标集返 `None`）**整段移入 S8-6**，改以 `transfer_linear` / 新骨架为被测对象，断言对象仍为**逐卡结果**（不得只断言目标组总量 = 1.0，那对错误 ① 恒通过；也不得只断言不变式成立的那一档，那对错误 ② 恒通过）<!-- REVIEW-R1-FIX: ISSUE-931 -->
  - [x] ~~**S8-3c `TransferModifier` 合并**~~（**2026-10-09 取消，预算 0.4 全部释放**：本项按「6 个类合并为 `TransferModifier`」施工，与 §3.1.2 的现行形态（七个机制形态、一机制一类）直接冲突，被否决；§3.10.4 末段的「类消失，只剩一个 `compute_delta()` 与一个助手」是**当时的**裁决 1B 形态，已随 2026-10-06 的简化作废，不得作为本项依据。其引用的 **§3.14.5 小节不存在**（§3.14 经 2026-10-06 改判后只剩 3.14.1 至 3.14.3），原「方案 C」的内容已失去落点。**无任何工作并入其他块**：六个类保留在 S2a-1 / S2a-2，preset 工厂归 S4-2 / S4-3）（原 ~0.4 人时；§3.1.2 映射表，2026-10-05 补）｜原内容存档：目标文件 `core/pity_modifier.py` + `core/pity.py`（preset 工厂）。按 §3.14.5 的方案 C 落地：6 个类合并为 `TransferModifier(u_of, t_of, mode, ratio_of)`，删除 `ForceFeatured` / `ForceNonFeatured` / `ForceSelected` / `ForceNotOwned` / `BaseRatio` / `Intercept` 六个类，目标解析器族落 `core/pity_modifier.py`
  - **⚠ S8-1 / S8-2 / S8-3 必须视为一个原子单元（2026-10-01 补登记；2026-10-05 曾扩入 S8-3b，2026-10-09 随 S8-3b 取消而缩回三块）**：三块的顺序是 S8-1 换接口（`compute_delta`）→ S8-2 管道换卡级 → S8-3 交付卡级 `transfer_linear`。**任一中间态都是键空间错位窗口**：`_apply_delta` 的 `d.get(c, 0.0)` 把「未在增量向量里出现的键」当作恒等 0.0，于是增量键与 `dist` 键不匹配时**不报错**，而是让**全部保底静默退化为恒等**。计划的 GATE-5 只在回滚段承认「半卡级 / 半槽位混态」，未给排序约束。**强制定稿**：三块**同一个 commit 落地**（或把 S8-3 前移到 S8-2 之前），并**新增一条跨块断言**：S8-2 的验收命令在冒烟之外须断言「卡级管道下同一配置的分布与 S5 产物逐元素一致（容差 1e-12）」，使中间态的静默退化在 CI 期即暴露。**回滚约束**：回退 S8-1 / S8-2 / S8-3 中任一方须**连带回退另外两方**（GATE-5 的「S8 逐子项回滚」在本三块上收窄为此条）。
  - [x] S8-4（**已落地**：`b62c09b` + 收口 `bd999e8`）**删除 `aggregate_probs_by_rarity` 与其导出行 + 卡级管道的分布解包口径改写**（~0.8 人时；§3.9.3）｜目标文件 `core/pity.py` + `core/pool.py` + `core/__init__.py` + **`core/pity_primitives.py`**（末者为 S8-4 实增：「分布解包口径」的落点，见下方 LANDED 段）（+ `python -c "import gacha_simulator.core"` 冒烟）：`aggregate_probs_by_rarity` 与其导出同步清理；分布解包口径随卡级管道改写。**本步不做 `compute_scope_mappings` 的「只产卡集合」改造**——卡集合（`scope_cards` / `featured_cards`）是该函数五元组的**既有前两项**（[pity.py:1065-1066](gacha_simulator/core/pity.py#L1065-L1066)），`PityEngine` 三个调度入口早已透传进 `DrawInfo`，新骨架可直接消费，本步无增量可做（**ISSUE-901**）。**ISSUE-901（强制，与原稿互斥已改判）**：本步**不删** `PoolPitySpec` / `DrawInfo` 的 `scope_slots` / `featured_slots` / `card_to_slot`，也**不改** `compute_scope_mappings` 的槽位产出为「只产卡集合」，**不改** `service/batch_simulator.py` 的 `PoolPitySpec` 构造（本步对它零改动）——旧保底类在发布前仍读这三字段（4 处旧类概率入口 + `_redistribute_scope` 函数体 + `PityEngine` 三个 `DrawInfo(...)` 构造点），删早即 S5a harness 与 S8-6 同时失效。三字段与槽位产出的删除并入 GATE-5 末条「发布前一次性移除旧保底类」commit。<!-- REVIEW-R1-FIX: ISSUE-901 --><!-- ⚠ 待人工裁决（ISSUE-901 备选路径）：若坚持在本步删字段，则 S8-6 的基线必须改为「S5 阶段固化 golden 快照」（丢弃「现跑旧类」），并同步改写 §六 差异归因清单、GATE-5 末条与 §3.9.3 的「旧类仍可用」表述——本计划取保守路径（推迟删除），备选保留待用户裁决 --><!-- REVIEW-FIX-PREV: AUDIT-BREAK-8 -->**`core/__init__.py` 是双目标文件**：本步删 [core/\_\_init\_\_.py:3](gacha_simulator/core/__init__.py#L3) 的 `aggregate_probs_by_rarity` import、`_redistribute_scope` 的 import（:20）与两者在 `__all__` 的条目（**import 与 `__all__` 必须同批改**）；10 个旧行为类 + `SoftPityMixin` 的 re-export 归 S4-3（已在其任务项）；`infer_rarity_from_spec` 的去留**已由 §3.9.3 的复核结论定稿为「一并删除」**（**ISSUE-504**：其唯一消费者链在 S8-2 / S8-4 中断，本步删其 `core/__init__.py:3` import 与 `__all__:101` 条目，函数本体已在 S8-2 删除）<!-- REVIEW-R1-FIX: ISSUE-504 --><!-- REVIEW-R1-FIX: ISSUE-002 -->
    <!-- P64-S8-CLOSURE -->
    **S8-4 落地实测（`b62c09b` + 收口 `bd999e8`，2026-10-14）**：删 `aggregate_probs_by_rarity` 的**本体**（`pool.py`，62 行）与其 `core/__init__.py` 的 import 与 `__all__` 条目（同批）；删 `_redistribute_scope` 的**导出**（import 与 `__all__` 条目，**本体保留在 `pity.py`**，4 处旧类调用点未动，ISSUE-502）；把 `tests/core/test_pity_registry_schema.py` 的「导出仍在」正断言反转为退役断言（并配对称的「本体存活」反向断言）；**改写两个此前未登记的真实消费者** `tests/core/test_pool.py` 与 `tests/core/test_worst_impact.py`（见下方事实订正）；`DrawInfo.base_probabilities` 的定义处补卡级口径注记。全量 `2917 passed / 35 skipped`；`p79_verify` 与 `p82_baseline --verify` PASS 零漂移。
    **「分布解包口径」的定位结论**：**无代码可改，只有声明缺失**（两个填充点已随 S8-2 传卡级；`after_draw` 入参是 `reward_id: str` 而非分布；策略侧读概率的路径已按卡 id 求和；`_apply_delta` 与 `invariants` 只做键无关的 Σ 运算）。故落点为定义处的注记。**审查补充**：排除清单遗漏了 `PityContext.current`（管道内实际流动的那份分布，§3.1.2 的 ctx 字段表把它与 `base_probabilities` 绑定为同口径），登记备查。
    **审查另确认**：该注记中「填错只会在 `transfer_linear` 的 `sum(dist[c] for c in Q)` 处显形」一句**与代码事实相反**（该式读 `dist`，不读 `weights`），已由收口订正为实测形态（`declared` 分支下**静默返回 `None`**；空表 / `None` 另走 `ValueError` 守卫）。
    **判据口径订正（S8 收口，2026-10-14）**：本行的 grep 零命中是**文本口径**，而 S8-1/2/3 落地时保留了若干**解释性注释**（写明「该符号已删」与其替代），实测当前命中 **24 行**（`core/__init__.py` 3 / `banner.py` 3 / `pity.py` 1 / `pool.py` 4 / `test_pity_integration.py` 2 / `test_pool.py` 5 / `test_worst_impact.py` 5 / `test_banner.py` 1），**全部为注释与 docstring、零代码引用**。故本步须**收窄口径**（例如排除注释行，或改判「代码引用零命中」），或同批清理这些字样；**不得因该 grep 非零而判定本步未完成**。<!-- P64-S8-CLOSURE -->
      **该行的事实陈述经 S8-4 实测订正（2026-10-14）**：本行原写「24 行命中**全部是注释与 docstring、零代码引用**」，**不成立**。S8-4 之前（`4508d78`）实测有 **4 处真实代码引用**：`tests/core/test_pool.py:3`（import）与 `:67`（调用）、`tests/core/test_worst_impact.py:171`（函数内 import）与 `:178`（调用）。即该符号在 S8-2 之后**仍有测试消费者**，`aggregate_probs_by_rarity` 的删除点（S8-4）才是它们的改造点。**教训（留档）**：这类「某处命中全是注释 / 零引用」的**可机核事实陈述**，主 agent 在收口前必须自己复算一次，不得直接采信审查报告。
    - 验收命令（GATE-6 补，块级最小验收）：`python -c "import gacha_simulator.core"` 冒烟 + `grep -rn "aggregate_probs_by_rarity\|infer_rarity_from_spec" gacha_simulator/ tests/` 零命中（**S8-4 落地后的实际口径，2026-10-14**：判据取 **AST 绑定引用零命中**（全库 379 个 `.py` 实测 0 处）；**文本命中允许保留**，实测 20 行，其中 3 行为负断言用例里的字符串字面量、其余为注释与 docstring）（`tests/core/test_pity_equivalence.py` 这一等价性装置亦不得例外——两者是「新管道不消费」的符号，旧类不读它们）<!-- REVIEW-R1-FIX: ISSUE-931 -->
  - [x] S8-5（**已落地**：`9bdc34e`）边界处理与 `worst_impact` 卡集合对齐（~0.6 人时；§3.9.5 / §3.9.6）｜目标文件 **订正为 `tests/core/test_worst_impact.py`**（**生产代码零改动**，实测 `git diff --numstat` 为 `434 0`；原写的 `core/pity.py` + `core/worst_impact.py` 与交付不符）（<!-- REVIEW-FIX-PREV: AUDIT-BREAK-6 -->第二处 `PoolPitySpec` 构造点 [worst_impact.py:543-552](gacha_simulator/core/worst_impact.py#L543-L552)。**ISSUE-901 / ISSUE-904：本步只在原 8 字段构造上做「卡集合按池对齐」，不重写为卡集合字段构造**——删三个槽位实参、只构造卡集合字段、`_ref_pool_entry` 写后即读的局部变量化（原写「复活/替换 `getattr(self,'_ref_pool',None)` 死分支（[:504]）」，**该分支实测不存在**，见 §3.9.3 订正）三项一并推迟到 GATE-5 末条，与槽位三字段的删除同一 commit。原稿「须整体重写为卡集合字段构造……不得因是死分支而不改」按 S8-5 施工即在 S8 提前让槽位字段落空，正是 §3.9.3 B 段**原稿**自述的「复活血路即崩」形态，已改；**注**：§3.9.3 B 段该说法已于 2026-10-09 订正为「`_ref_pool` 属性与所述分支在全库都不存在」）<!-- REVIEW-R1-FIX: ISSUE-904 -->：`T == 0` / `P == 0` / `P − T == 0` / **scope 键缺失** / **`⟨m,p⟩ ≠ 1`** 五类边界；只读查询口径同 §3.9.6。**ISSUE-006 追加（2026-10-09：该对齐已由 `e32577f` 落地、构造期覆盖不变量已就位，本子项降为「保留不变量」）**：`worst_impact` 的卡集合按池对齐（断言 `set(scope_cards[scope]) ⊆ {r.id for r, _ in pool.rewards}`，**ISSUE-201**：`Pool.rewards` 元素是 `(Reward, prob)` 二元组，须按二元组解包，口径同 §3.9.1）。~~并复活/替换 `_ref_pool` 死分支~~ **该子项已随 ISSUE-901 推迟**（见本行开头），S8-5 不做——原句与本行前段自相矛盾，已删 <!-- REVIEW-R1-FIX: ISSUE-904 --> <!-- REVIEW-R1-FIX: ISSUE-955 -->
    <!-- P64-S8-CLOSURE -->
    **S8-5 落地实测（`9bdc34e`，2026-10-14）**：新增 9 条用例（五类边界各一条 + 卡集合对齐一条 + 一条计划外补充），全部经**真实虚拟池 + 真实 spec + `PityEngine.before_draw` 卡级管道**，与既有助手级 / Modifier 级断言**不同层级、无重复**。收集守卫达成（由**零命中、exit code 5** 变为 **9/25**，命中项全为本步新增）。全量 `2926 passed / 35 skipped`；`p79_verify` 与 `p82_baseline --verify` PASS 零漂移。8 处变异全红。
    **ISSUE-006 的处置性质**：卡集合对齐**已由 `e32577f` 落地**（五个映射统一由 `compute_scope_mappings(wi_pool)` 按池生成、构造期覆盖不变量在位），故本步是**保留不变量**而非新增能力；其边际判别力在「卡集合 ⊆ 池」这一方向（既存用例守的是「池 ⊆ 卡集合」，两向互补）。
    **本块的失败形态订正（GATE-1 声明与本块实测不符，2026-10-14）**：原声明的「**Σ 偏离 1e-12** 这类静默偏移」在本块**无覆盖**（6 条 `Σ == 1` 断言零判别力，`_apply_delta` 的无条件归一化使其成为结构保证），且该形态**由输入产生**（如池内重复 id，实测 Σ = 0.8）而非由算子产生。本块真实的静默偏移捕获面是：**源组位级归零**（Q 侧「先乘后除」的 1 ULP 负残值）、**U 外相对不变**、**只读标记接线**、**卡集合对齐**。**「Σ 偏离」的覆盖责任转给 S8-6**（不变式层）。
    **额外补的一条计划外用例**：`boundary_readonly_query_suppresses_cr_intercept`（引擎级只读接线），理由是 §3.9.6 处置② 在引擎侧**原无捕获面**（见 §3.9.6 的登记）。
    **本步登记的一条既有缺陷**：`WorstImpactAnalyzer` 的「多张 SSR 塌缩成一张」与「参照池无 SSR 时目标不可达」**同根因**（`_featured_ids` 只从最后一个 enabled 池推导，推不出唯一 UP 卡时无守卫；下游 `prepare_simulation_config` 用单一 id 重命名、`all_featured_ids` 又无条件登记 99 个 `_wi_featured_{i}`）。**随包 `config.toml` 不可达**（8 池各 7 张 SSR、各 1 张 featured），**用户配置可构造**；**早于 P64**，不在本计划范围内修（详见报告 §六）。
    - 验收命令（GATE-6 补，块级最小验收）：`pytest -q tests/core/test_worst_impact.py -k "scope_cards or boundary"`——本步新增的卡集合对齐断言（`set(scope_cards[scope]) ⊆ {r.id for r, _ in pool.rewards}`）与五类边界（`T == 0` / `P == 0` / `P − T == 0` / scope 键缺失 / `⟨m,p⟩ ≠ 1`）各一组<!-- REVIEW-R1-FIX: ISSUE-931 --> **GATE-6-测试策略（2026-10-01 补）**：命令的断言对象须由**本步新增**用例承载且**命名命中该 filter**（原稿未约束命名）。命名约束：卡集合对齐用例名含 `scope_cards`（建议 `test_worst_impact_scope_cards_aligned_to_pool`）；五类边界用例名含 `boundary`（建议 `test_worst_impact_boundary_t_zero` / `_p_zero` / `_p_minus_t_zero` / `_scope_key_missing` / `_non_unit_sum`，共五条）。**收集守卫（实测依据）**：`pytest -q tests/core/test_worst_impact.py -k "scope_cards or boundary"` 当前**零命中**（**16** deselected，pytest **exit code 5**；2026-10-09 实测订正，原写「11 deselected」），落地时先 `--collect-only`<!-- REVIEW-R1-FIX: GATE-6-测试策略 --> 确认收集到 **≥1 条**且命中项全部为本步新增用例 <!-- REVIEW-R1-FIX: GATE-6-测试策略 -->
  - [x] S8-6（**已落地**：`c5e680c` + 收口）验收：按 §六 的 S8 口径（对 S5 产物容差 1e-12）+ 单卡定向专项 + **`transfer_linear` 六场景逐卡对照**（~0.6 人时；**2026-10-09 由 0.3 上调**，并入原 S8-3b 的验收内容）｜目标文件 `tests/core/test_pity_equivalence.py`（S5a / S5b 的既有装置，加卡级管道对比组）
    - **⑥ `transfer_linear` 六场景逐卡对照（2026-10-09 自原 S8-3b 移入，强制）**：覆盖 §3.14.3 已实测的**六场景**（`scope` × `tf` 全组合，含更高稀有度豁免路径），断言**逐卡**结果与旧 `HardPityBehavior` 一致（**措辞订正（S8-6 审查，2026-10-14）**：「一致」**只对 `m = 0` 的两档成立**；`m > 0` 的四档正是**已登记的差异类 (a)**（旧 `Σ = 1+m`、新 `Σ = 1`），实际断言改为该类的**逐卡闭式差**（目标卡 `+m²/(1+m)`、更高稀有度卡 `-p_c·m/(1+m)`、Q 内 0），`m` = 高于 scope 的稀有度质量）（**不能只断言目标组总量 = 1.0**——那对 §3.1.5.2.4 错误 ① 恒通过；也不能只断言不变式成立的那一档——那对错误 ② 恒通过）；另两条：`scope` 不在 `[rarities].ranks` 内时抛 `ConfigError`、空目标集返 `None`。`shape='declared'` 分支须至少一条正例（`p(A) = 0` 但 `w(A) > 0` 时转移成功，即「来源二」）与一条负例（`w(A) = 0` 时不转移，即「来源一」）。**原 S8-3b 的验收命令不可照抄**（其拟新建的 `tests/core/test_pity_primitives.py` 与 `assign` / `universe` 两个符号均不存在），本组用例挂本文件、用例名须含 `s8`
    <!-- P64-S8-CLOSURE -->
    **S8-6 落地实测（`c5e680c`，2026-10-14）**：新增 **29 条**用例（① 3 / ② 1 / ③ 2 / ④ 2 / ⑥ 12+4 / ⑦ 1 / ⑨ 4），`-k s8 --collect-only` 由 **exit code 5** 变为 **42/120、exit 0**；全量 `2955 passed / 35 skipped`；`p79_verify` 与 `p82_baseline --verify` PASS 零漂移。它自报 8 处变异中 **7 红、1 处为等价变异**（删 `HardModifier` 调用方的「`A` 为空」守卫，全量零红，见 §六「S8 空目标集断言」行的强度订正）。
    **⑧ 的落点裁决与「唯一通道」的订正（S8-6 审查，2026-10-14）**：取候选 ① 落地，但实施者给的两条论证**有误**，已订正：① **「唯一通道」不成立**（另存在「`Pity` 自持引用、引擎装配后注入」与「`before_draw` 加 keyword-only 形参 + `isinstance(bh, Pity)` 分派」两条替代）；② **「候选 ② 与 §3.1.6 相抵」是对该节的误引**（§3.1.6 约束的是 **import 方向**，把鸭子类型对象当形参传入**不产生模块依赖**）。**真正的取舍理由**：候选 ① 无需分派、校验器随调用走、不给叶子层加 `pool_id` 形参。
    **本步声明与实测不符（三条，均已登记）**：**①** 一处用例 docstring 自述的判别力不成立（空目标集用例的夹具 Σ = 1，`_apply_delta(dist, {})` 在该形态下是恒等，故「无条件 `d or {}`」变异不会让它变红；已由收口改为 Σ ≠ 1 的夹具或订正说明）；**②** `get_probabilities` 不写 `ctx.invariants` 这一已登记边界**零测试守卫**（审查实测在 `get_probabilities` 也写该字段的变异下全量零红，已由收口补断言）；**③** `check_delta` 的**实参顺序**只被「键空间」断言偶然捕获（其对调变异仅在夹具键集不对称时才红，已由收口补一条不依赖键集大小的实参面断言）。
    **未覆盖面清单**：8 条，已写进提交信息（含 ⑥ 的 `scope='r'` 两档与 `tf=1` 三档、① 的两条口径守卫、④ 对新增调用点的捕获面等）。
    - **⑦ 形状改变型算子排在 `hard` 之前时的 A 侧形状（S8 收口新增，2026-10-14，强制）**：见 §六 差异清单新增的 (g) 项。**当前所有验收批次都没有 `priority` 覆盖**，故该形态**无观测面**：须构造「`rotating`（或 `targeted`）经 `priority` 排在 `hard` 之前、同 scope」的配置，断言 S8 的既定语义（`hard` 的 A 侧取**当前形状**，即保留前序算子已造成的形状）。
    - 验收命令：`pytest -q tests/core/test_pity_equivalence.py -k s8`——① 卡级管道产物与 **S5 产物**的**归一化后分布容差 1e-12**（**口径订正（S8-6 审查，2026-10-14）**：S5a 装置的**实际**口径是**原始值逐元素**（Σ ≠ 1 时更严），与 §六 (a) 订正段同一口径）、状态快照完全一致（**ISSUE-502：「S5 产物」= S5a harness 现跑旧类产出**——旧类与 `_redistribute_scope` 本体均保留至发布前，故本条与「S8 不删函数本体」相容；**若将来改为固化 golden 快照**，须同步在 S5a 登记快照文件与重生成命令，并在此改为「读快照」）<!-- REVIEW-R1-FIX: ISSUE-502 -->；② 单卡定向：双 UP 池定轨（`targeted` 锁定其中一张）在必中触发时该卡拿到 100%（现状实测 50/50，§3.7）；③ §六 登记的两条**允许差异**（`⟨m,p⟩ ≠ 1` 的 Σ = 1.009 → 1、`worst_impact` 卡集合对齐）须作为已知差异断言、不得当作回归；<!-- P64-S8-CLOSURE -->
    **时点偏移（S8 收口，2026-10-14）**：**⑤ 已随 S8-1/2/3 的原子 commit 提前执行**（判据改恒等 `Σp = 1`、三个 F 豁免符号删除、两个测试文件改写；审查实测该反转属**收紧**）。本行保留作记录，S8-6 落地时**不要重复执行**，只需复核其仍然成立。
    **⑤ `core/invariants.py` 的分布层归一性判据同批 re-derive（ISSUE-903，强制）**：S8 起 `_apply_delta` 无条件归一化，checker 的 scope 感知式会退化为对合法配置的假警报，本步须把该判据改为恒等断言 `Σp = 1` 并重跑 `pytest -q tests/core/test_pity_invariant_checker.py`（其正例期望值随 §六 S11 条同步改为 `Σp = 1`）——**验收命令**：`pytest -q tests/core/test_pity_invariant_checker.py` 全绿；④ **遍历点命名空间（ISSUE-505）**：构造一个 `namespace` 非 `None` 的 Modifier，断言 S8 内循环经 `self._view_for(mod)` 取 view（读到的状态来自该命名空间、未落默认 view），并断言 S8 骨架内**无** `mod.compute_delta(ctx, self._view, …)` 直写形态；⑥ 六场景逐卡对照（见上条）<!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-6-测试策略 --> <!-- REVIEW-R1-FIX: ISSUE-505 --> **GATE-6-测试策略（2026-10-01 补：收集守卫）**：本步新增用例名须含 `s8`（② / ③ / ④ / ⑥ 各一条）。`tests/core/test_pity_equivalence.py` 为 S5a **新建**文件，零命中时 pytest 以 **exit code 5** 结束、会被误读为通过，落地时确认收集到 ≥1 条 <!-- REVIEW-R1-FIX: GATE-6-测试策略 -->
  <!-- REVIEW-FIX-PREV: AUDIT-BREAK-7 -->
  - [x] S8-7（**已落地**：`f752cfb`）槽位结构消费的存量测试改造（~0.4 人时；§3.9.3 的 `tests/` 行）<!-- P64-S8-CLOSURE -->
    **剩余面重算（S8 收口，2026-10-14）**：S8-1/2/3 的原子 commit 已**顺带改造 8 个存量测试文件**（清单见本节的 LANDED 段），故本步的剩余面须先重跑其验收命令的 grep 与收集守卫，按实测重算，**不要照抄本行的 5 文件清单**。｜**与 M1 的 S7d 是两个时点、两批文件**（S7d 处置「直取旧类」的模块级 import，本步处置「槽位字段 / `_redistribute_scope`」的结构性断裂）。目标文件 `tests/core/test_pity_rotating.py`（import 并调用 `_redistribute_scope`）+ `tests/core/test_pity_integration.py` / `tests/test_pity.py` / `tests/core/test_pity_lifecycle.py` / `tests/core/test_pity_targeted.py`（构造带槽位字段的 `PoolPitySpec`，**5 个文件**，2026-09-22 计数修正见 §3.9.3）。**清单订正（2026-10-13，S7d 审查）**：实测该 grep 命中 **12 个文件**，扣除三项已声明的例外后是 **9 个**（原写 5 个，S7d 自报的 7 个亦偏低）。缺的 4 个是：`tests/core/test_pity_rebind.py`（**其槽位字段系 S7d 新增**，旧版 0 命中）、`tests/core/test_pity_modifier.py`、`tests/core/test_pity_registry_schema.py`、`tests/core/test_pity_tracker.py`。。改造口径：构造改按卡集合字段；~~`_redistribute_scope` 的用例改为对 `transfer_linear` 的增量向量断言~~（**后半不可执行（S8-7 审查，2026-10-14）**：与 **ISSUE-502**（本体保留、4 处旧类调用点仍在）相抵。**且实施者给的理由须收紧**：审查实测该函数在 `test_pity_equivalence.py` 中**被间接调用 6211 次**，故「会丢掉该函数的覆盖」不准确；真正的损失是**直接边界**，尤其 `test_zero_total_ratio_math` 的 `total = 0` 在 6211 次间接调用中命中 **0 次**。故口径应为「**保留 `_redistribute_scope` 的直接单测至其删除 commit**」）
    <!-- P64-S8-CLOSURE -->
    **S8-7 落地实测（`f752cfb`，2026-10-14）**：12 文件 **+85/-153**、**零断言改动**（主 agent 独立核实：`git diff -U0 | grep -c "^[+-].*assert "` 为 0；含 `==` / `approx(` 的改动行只有 1 处且是注释）、**全量测试数不变**（`2957 passed / 35 skipped`）；`p79_verify` 与 `p82_baseline --verify` PASS 零漂移。做法是把**只服务新骨架**的 `DrawInfo` / `PoolPitySpec` 构造点的槽位三实参剥离（两类字段均有 `default_factory`，构造合法性不变），并在每个被剥离的夹具写明归属注记。
    **验收口径替换（S8-7 审查，2026-10-14，强制）**：本行的「`grep` 零命中」**不可达**（实测 HEAD 仍命中 **8 文件 / 84 处代码**，其中 `test_pity_equivalence.py` 独占 57 处；只要 ISSUE-901 / ISSUE-502 有效，该判据恒不可达）。审查给出**可机械复核**的替代判据：**把 `DrawInfo` 的 `scope_slots` / `featured_slots` / `card_to_slot`（`pity_primitives.py`）与 `PoolPitySpec` 的同名三字段（`pity.py`）的 `default_factory` 换成「任何读取即抛」的探针类，全量测试须全绿**（S8-7 落地时审查实测 `2957 passed / 35 skipped` 全绿）。该判据直接编码「剥离面零读者」这一实质，且一键可复核；**六项例外清单降为随附登记**，不再作为验收判据。
    - 验收命令：`pytest -q tests/core/test_pity_rotating.py tests/core/test_pity_integration.py tests/test_pity.py tests/core/test_pity_lifecycle.py tests/core/test_pity_targeted.py` 全绿；`grep -rn "scope_slots\|featured_slots\|card_to_slot\|_redistribute_scope" tests/` 零命中——**例外清单（三项；ISSUE-717 / ISSUE-942：原写「唯一例外」，实测该 grep 另有命中）**：① `tests/core/test_pity_equivalence.py`（等价性装置必须自行构造带槽位字段的 `PoolPitySpec` / `DrawInfo` 喂给旧类，与 S7d 对「直取旧类」的 grep 豁免同源；**ISSUE-901**）；② `tests/core/test_pool.py:62`（构造 `card_to_slot={'ssr_a': 'ssr_featured'}`）与 ③ `tests/core/test_worst_impact.py:303`（读 `spec.featured_slots['ssr'][0]`）。后两者**挂在 S8-2 名下**，由 S8-2 的同一 commit 改造，故它们**不在本步的 5 文件清单内**，但 grep 零命中的口径须把这三项都计入例外并写明归属，否则实施者按本步清单判断会漏。本步只改造 **5 个槽位消费文件**的构造与断言，**不删字段本体**（字段的删除在 GATE-5 末条）<!-- REVIEW-R1-FIX: ISSUE-901 -->
  - **S8-4 的测试侧断裂点（2026-10-13，S7d 审查补登）**：`tests/core/test_pity_registry_schema.py` 的 `TestRedistributeScopeExportStillPresent::test_redistribute_scope_exported_knowingly` 断言 `'_redistribute_scope' in core_pkg.__all__`（实测当前为 `True`），而 S8-4 明写「删 `_redistribute_scope` 的 import 与 `__all__` 条目」。**该用例在 S8-4 必红**，而 S8-4 的目标文件清单（`core/pity.py` + `core/pool.py` + `core/__init__.py`）**不含任何测试文件**。处置：随 S8-4 同批改造该用例（改为断言该符号**不在** `__all__`，与 S4-3 对 10 个旧行为类的退役断言同形）。
  - **S8-4 与 S8-5 必须分立（GATE-1 定稿，强制）**：S8-4 是**结构性删除**（`aggregate_probs_by_rarity` / `infer_rarity_from_spec` 的函数与导出面；**槽位字段不在本步删**，见 ISSUE-901），失败形态是「某处仍在引用已删符号」这类 `ImportError`；S8-5 是**数值边界与卡集合口径**，失败形态是「Σ 偏离 1e-12」这类静默偏移。两类失败的归因方向（谁没删干净 vs 谁算错了）完全相反，合成一块会让失败无法定位；且 S8-4 的删除面本身已横跨 4 个文件，接近单块预算上限。
<!-- REVIEW-FIX-PREV: ISSUE-012 -->
<!-- REVIEW-FIX-PREV: ISSUE-016 -->
<!-- REVIEW-FIX-PREV: ISSUE-006 -->
<!-- REVIEW-FIX-PREV: ISSUE-201 -->
- [x] S9 **状态可见性与 G3 真实建模**（合计 ~3.1 人时；方案见 **§3.10**）｜**逐子项独立 commit，回滚单元 = 子项**（GATE-1 / GATE-5）
  - [x] S9-1（**已落地**：`5a63e2a`）`StateView` 限定 Modifier 状态视野（关闭跨保底读，~0.5 人时；§3.10.3），**签名沿用 S8-1 定稿的 `compute_delta(view, dist, ctx)` 形态**（方法名与参数由 `apply(ctx, view, dist, readonly)` 改为 `compute_delta(view, dist, ctx)` 属 S8-1 的接口变更，**本步不改签名**，只收紧 `view` 的可读面）｜目标文件 `core/pity.py` + **`core/pity_modifier.py`** + **`core/pity_primitives.py`**（末两者为**契约文本**的订正落点，S9-1 实增；亦可记作落在 §四 的对应行）。**ISSUE-103 追加**：`PityContext.state` 的字段注记保持 `PityState`（隔离只由 `view` 承担，§3.10.2）；`TargetedBehavior` 三处 `ctx.state.get(self._name, "selected_card")` 迁为 `view.get("selected_card")`（§3.10.3）
    - 验收命令（GATE-6 补，块级最小验收）：`pytest -q tests/core/test_pity_integration.py -k stateview`——**Modifier 经 view 读其他保底键时返回 `default` 而非抛 `KeyError`** 的单测（跨保底读关闭的正例与负例各一），与现存用例同文件<!-- REVIEW-R1-FIX: ISSUE-931 --> **GATE-6-测试策略（2026-10-01 补：收集守卫）**：用例名须含 `stateview`（正例 / 负例各一），且命中项须**全部为本步新增**。    <!-- P64-S9-1-LANDED -->
    **S9-1 落地实测（`5a63e2a`，2026-10-14）**：收集面由**零命中（exit code 5）**变为 **2/28**（正例 / 负例各一，命中项全为本步新增）；全量 `2959 passed / 35 skipped`；`p79_verify` 与 `p82_baseline --verify` PASS 零漂移；6 处变异逐处还原。**判定结论**：`StateView` 早已到位（S3-1）、本步在 `StateView` 本体上**零代码增量**，实际交付是**旧类三处 `ctx.state` 读取的迁移**（收敛为 `_selected_card(ctx)`，逐位等价，见 §3.10.3 的订正）**加验收面**。
    **计数订正（S9-1 审查，2026-10-14）**：本行与 S9-4 记的「该文件当前 **12** 条既有用例」**与实测不符**：基线 `876254c` 实测 **26** 条（HEAD 28 条 = 26 + 本步新增 2）。**建议改为 26 或去掉写死的条数。**
    实测 `-k stateview` 在该文件当前 **12** 条既有用例下**零命中**（pytest **exit code 5**；2026-10-09 实测订正，原写「10 条」；与 S9-4 / ISSUE-947 的 12 条一致）<!-- REVIEW-R1-FIX: GATE-6-测试策略 -->，落地时确认收集到 ≥1 条 <!-- REVIEW-R1-FIX: GATE-6-测试策略 -->
  - [x] S9-2 ~~`PityDef.reads`~~ + **`SimView`** + `uses_sim` 注解校验（~0.6 人时，2026-10-06 由 0.8 下调；§3.10.2）｜目标文件 `core/state.py`（**`SimView`** 类 + `GachaState.sim_view()` 构造点；`initial_counts` 字段、`add_card` / `total_holding` 形参移除与守卫删除）+ `core/pity_primitives.py`（`PityContext.sim` 字段，**非 Optional**——`PityContext` 已迁至本文件，字段的编辑点在此行，§四 该行 ISSUE-034）+ `core/pity.py`（`PityEngine` 两个入口的**必填参 `sim`** 透传）+ **`core/strategy.py`** + **`service/gacha_service.py`** + **`core/banner.py`**（后两者是**通道 B（独立概率查询）与通道 A（抽卡管道）的填充点**，缺任一则 `sim` 只在一半路径生效且验收盲区不可见，逐通道说明见下行）+ `core/milestone.py`（闭包捕获改从 state 取）+ `tests/test_p60_gacha_state.py` + `tests/test_p63_overflow_integration.py`（两文件正断言被删守卫，须与本步同一 commit 改造，否则该 commit `pytest -q` 全红）+ ~~`core/config_store.py` / `core/config_toml.py` / `core/retreat_config.py`~~（**2026-10-06 随 `reads` 删除**：`config_store` 为 `reads` 的**字段定义**、`config_toml` 为**解析**、`retreat_config` 为**三处枚举式透传点之一**（另两处即 `pentry` 与 `_PityDef` 重建，同在 `service/batch_simulator.py`）；字段取消后这三者无改造量，而 `batch_simulator.py` 因别的事由仍须改造，见下）；**`service/batch_simulator.py` 不属该删除线，本步必须改造**（**本轮 AUDIT-BREAK-9 订正**：原把它并列在删除线上，与 §六 ISSUE-916 ②、§四 该文件行的「本步删除 `:477-482` 的 `_ms_initial` 推导与 `:486` 的 `initial_counts=_ms_initial` 实参」直接互斥）——`register_milestone_engine` 的**全库唯一调用点**就在 [batch_simulator.py:483-487](gacha_simulator/service/batch_simulator.py#L483-L487)，本步把 `core/milestone.py` 的闭包捕获改为从 state 取初始持有后，该调用点即 `TypeError`（仅在有里程碑定义的配置上触发：该推导在 `if env.milestone_defs:` 块内，默认配置不执行该块，故只跑默认配置会**静默漏过**）；**`core/state.py` 行另须覆盖 `GachaState.clone()`（[state.py:89-97](gacha_simulator/core/state.py#L89-L97)）的逐字段显式拷贝**（**本轮 AUDIT-BREAK-9 补**：原条目文字只写三件事 + 形参移除，未提 clone）——`run_simulation` 首行即 `initial_state.clone()`，漏改则 `state.initial_counts` 恒空、`total_holding` 少算初始持有、P63 溢出分档静默出错，§六「`GachaState.clone()` 保真」条的断言对象随之落空<!-- REVIEW-FIX-PREV: AUDIT-BREAK-9 --><!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->
    - **两条送达通道（§3.10.2 定稿，须逐通道落地）**：**通道 A** = `Banner.draw`（填充点在 **`core/banner.py`**，调 `pity_engine.before_draw(..., sim=state.sim_view())`，调用点 [gacha_service.py:467](gacha_simulator/service/gacha_service.py#L467)）；**通道 B** = `StrategyContext.get_pity_probabilities`（填充点在 **`core/strategy.py`**）。**ISSUE-920（2026-10-01 补登记，原清单漏列；2026-10-06 按 §3.10.2 改判改写）**：原清单只列到 `service/gacha_service.py`，漏 `core/banner.py` 这一实际填充点。**漏填的后果已变**：`sim` 非 Optional，缺参在**构造期**抛 `TypeError`，不再是「运行期读到 `None` → G3 的 `NotOwnedModifier` 静默退化为恒等」这一静默失效形态（§3.10.2）。
    - **改名说明（§3.10.2「删除的符号」/「保留的」两段）**：`ExternalView` → **`SimView`**；`GachaState.external_view()` → **`sim_view()`**；`PityContext.external` → **`sim`**。`SimView` 只暴露 `owns(card_id) -> int`（`total_holding` 口径，**含初始持有**，ISSUE-009），`balance()` 已于 2026-10-06 删除（全库零使用）。与 S9-1 的 `StateView` 的分工：后者限定**单个保底命名空间**的状态视野（关闭跨保底读，§3.10.3），前者暴露**模拟级只读事实**，二者不可互相替代。
    - **本步现行内容（2026-10-06 改判后，取代原 `reads` 段）**：只落三件事（**本轮 AUDIT-BREAK-9 追加第 ④ 件，见本条末尾**）——① **`SimView`** 类与 `GachaState.sim_view()` 构造点；② `PityContext.sim` 字段（非 Optional）与 `PityEngine` ~~两个入口~~ **三个调度入口**（`before_draw` / `after_draw` / `get_probabilities`）的必填参 `sim`（**订正（S9-2 审查，2026-10-14）**：字段非 Optional 与「`after_draw` 也构造 ctx」两条合起来只有「三入口全必填」一种自洽解；§六 的口径本就写三入口，本行的「两个入口」是措辞错误）；③ **`uses_sim` 类属性注解的校验**（注解名须在已知源集合内，当前只有 `owns`，否则抛 `ConfigError`；注解**不参与门控**，只作文档与检查器输入，§3.10.2）；④ **`service/batch_simulator.py` 的两处删除与调用点实参同步**（**本轮 AUDIT-BREAK-9 补**）：删 [batch_simulator.py:477-482](gacha_simulator/service/batch_simulator.py#L477-L482) 的 `_ms_initial` 推导与[:486](gacha_simulator/service/batch_simulator.py#L486) 的 `initial_counts=_ms_initial` 实参，与 `core/milestone.py` 的闭包改读 state **同一 commit**——否则 [batch_simulator.py:483-487](gacha_simulator/service/batch_simulator.py#L483-L487) 的 `register_milestone_engine` 调用点即 `TypeError`。另：`GachaState.clone()`（[state.py:89-97](gacha_simulator/core/state.py#L89-L97)）须带新字段（见目标文件行的同条）<!-- REVIEW-R1-FIX: AUDIT-BREAK-9 -->
    - **~~ISSUE-033 追加：`Pity.reads` 承载 + `PityEngine.get_reads_for_pool(pool_key)` 汇总接口（`GachaService` 与 `StrategyContext` 均经它取并集）~~**（**2026-10-06 随 §3.10.2 改判删除**：门控取消，无并集可汇总，两条通道各持同一 `GachaState` 自产 `sim`）。**~~三处透传点（`pentry` / `_PityDef` / `retreat_config`）随 `reads` 字段定义同批落地~~**（同批删除：无新字段可透传，S4b 已把三处改造为 dataclass 驱动，本步无需再确认「新字段自动随行」）。**~~本步另含 `reads` 门控代码的落点（ISSUE-404）：§3.1.4 骨架的 `Pity._gated_ctx` 按 `self._reads` 派生一份 ctx~~**（同批删除：§3.10.3 改用 `StateView` 从架构上关闭跨保底读，不再派生 ctx；原 ISSUE-926「就地置 `None` 会污染同池其他保底」的约束随之失去对象）。**结论闭环**：原稿末句「原稿本步只列字段 / 解析 / 透传 / `get_reads_for_pool`，无任何子块承接这段门控代码」至此收尾——该段门控代码**整体取消**（§3.10.2 / §3.10.3），**本步不落任何 `reads` 相关代码**。
    <!-- P64-S9-2-LANDED -->
    **S9-2 落地实测（`d1cf8de`，2026-10-14）**：28 文件 **+722/-220**（9 生产 + 19 测试）；`-k sim_view` 收集 **3/32**（`test_pity_integration.py`）+ **1/19**（`tests/service/test_gacha_service.py`），命中项全为本步新增；全量 **`2966 passed / 35 skipped`**；`p79_verify` 与 `p82_baseline --verify` PASS 零漂移；9 处变异逐处还原（超上限 1 处，已登记）。
    **四条订正（S9-2 审查，2026-10-14）**：
    **① 目标文件清单严重偏小**：本行只列 **2 个测试文件**，实测必填参改动落到 **15 个测试文件**（其中 **14 个含 `sim=` 插入共 126 处**，另 1 个仅探针签名转发；构成 = 引擎入口 75 + `PityContext` 直构 51）。**订正为**「`tests/` 下全部引擎入口调用点与 `PityContext` 直构点 + 3 处既有探针须同签名转发」。
    **② 「必填参 `sim` 透传」措辞不准**：无上游形参可透传，实际是「**入口必填形参 + 各调用点就地自产 `state.sim_view()`**」。
    **③ ④ 的 AUDIT-BREAK-9 理由前提不成立**：本行写「默认配置不执行该块，故只跑默认配置会静默漏过」，而**随包 `config.toml` 含 2 条 `[[milestone]]`**（`env.milestone_defs` 实测长度 2），且实测 **132 条用例**触达 `_consume_bonus` 的卡牌分支。**真正的理由是「推导源与赋值点须唯一」**，不是可达性低。
    **④ 用例计数过时**：§六 与本行记的「该文件现存 12 条用例」应改为 **32**（29 既有 + 3 新增），或按 §七 S9-1 的建议去掉写死条数。
    **⑤ 通道 B 的用例名与分工**：计划建议的 `test_channel_b_matches_before_draw` 实际落地为 **`test_channel_b_fills_sim_view`**（`-k channel_b` 仍匹配）；本步只落「**填充点**」断言，**1e-12 逐元素对照归 S9-4**，S9-4 不得误以为已覆盖。
    - 验收命令（GATE-6 补，块级最小验收）：`pytest -q tests/core/test_pity_integration.py -k sim_view`——**用例名须在计划内写死**（建议 `test_sim_view_owns_includes_initial_counts`：断言 `SimView.owns()` 取 `total_holding` 口径（含初始持有）；`test_sim_view_annotation_unknown_source_raises_config_error`：断言 `uses_sim` 注解名不在已知源集合（`owns`）时抛 `ConfigError`），落地时先 `--collect-only` 确认收集到 ≥1 条且命中项**全部为本步新增**（`-k` 零命中时 pytest 以 **exit code 5** 假通过，纪律见 §七 引言的「验收命令与断言对象绑定纪律」）<!-- REVIEW-R1-FIX: GATE-6-测试策略 -->。**两通道填充点各一条断言**（本步目标文件已列）：`core/banner.py`（通道 A）与 `core/strategy.py`（通道 B）各断言 `sim` 被实际传入；详尽的通道 B 独立验收（同刻分布逐元素一致，容差 1e-12）归 S9-4。
  - [x] S9-3（**已落地**：`86c1a89`）`NotOwnedModifier` 新零件 + **两个新 type（G3 双实现，2026-09-30 裁决）** `hard_exclude_owned_skip` / `hard_exclude_owned_any`（`BEHAVIOR_REGISTRY` 两条注册；GUI 下拉**自动出现**——**前提 = S6a 的 `_PITY_TYPES` 生成式改造已落地**，未落地则本步手工追加这两个 type）<!-- REVIEW-R1-FIX: ISSUE-929 -->+ **「关于」页面两处文本改为 registry 生成**（§3.10.4 配套第 4 条）+ G3 配置示例 + 手册 §7.3 / §21 缺口归属更正（登记为**一条**待确认项、两个候选实现）（~0.9 人时，原 0.7 因增第二个 type 与关于页两处；§3.10.4）｜目标文件 `core/pity_modifier.py`（`on_all_owned` 构造参数）+ `core/pity.py`（两条 registry 条目）+ `gui/config_panel.py`（下拉）+ **`gui/about_dialog.py`**（`:67` 与 `:207` 两处文本）+ `tests/gui/test_about_dialog.py`（新增）+ **`tests/gui/test_config_panel_p56.py`**（**ISSUE-912**：其 [:53](tests/gui/test_config_panel_p56.py#L53) 的 `assert len(panel._PITY_TYPES) == 10` 与 [:48-53](tests/gui/test_config_panel_p56.py#L48) 的 `test_pity_types_has_10_entries` 会被本步（+2 个 type）与 S6a（+`rotating_inverse`）共同打破；`_PITY_TYPES` 自 S6a 起改为 registry 生成，该断言须改为 `== len(BEHAVIOR_REGISTRY)` 并去掉写死的数量名——**且该改写必须在 S6a 就完成**（S6a 的 `rotating_inverse` 已使它由 10 变 11），否则 S6a 的 commit 一落地即红）<!-- REVIEW-R1-FIX: ISSUE-929 -->+ `config/config.toml` + 手册。**已删除 `core/config_toml.py`（校验）**：该白名单不存在，见 §3.10.4 配套第 2 条
    <!-- P64-S9-3-LANDED -->
    **S9-3 落地实测（`86c1a89`，2026-10-14）**：10 文件 **+691/-42**；全量 **`3007 passed / 35 skipped`**（+40 = 24 条新函数 + 16 条新参数化实例）；`ruff` 与 `refcheck` 通过；`p79_verify` 与 `p82_baseline --verify` PASS 零漂移；9 处变异逐处还原（超上限 1 处，已登记）。交付：`NotOwnedModifier` 接线（`on_all_owned` 形参 + **A 侧形状改 `declared`（F7 裁决）**）、两条 registry 条目（四键齐全 / `threshold` 默认 50 / `display_name` 带形态括注 / `reset_on = pdef.reset or _norm_scope(pdef)` / `tau` 缺省回退 50）、`_HARD_TYPES` 与 `_BTYPE_ORDER` 同步、GUI 下拉**零改动自动出现**（实测 13 项、两条新 type 在第 5/6 位）、「关于」页两处文本改由 registry 生成（占位符替换、版式未动、运行期无 `@@` 残留）、手册 §7.2/§7.3/§7.4/§21/目录与 `config.toml` 的注释示例同步。
    **四条订正（S9-3 审查，2026-10-14）**：
    **① 契约表条删去「键集含 `on_all_owned`」**（**pre-ruling 残留**）：`PityDef` 无该字段、`_build_pity` 不读它，实测把该键登记进 `_PITY_TYPE_KEYS` 会被计划**自己的反向一致性不变式**拒收（`test_contract_subset_of_build_pity_read_face` 报「幽灵键」）。两条键集与 `hard` 逐键同形（`{'threshold'}`）。
    **② 验收命令的过滤词须放宽**：`-k exclude_owned` **只命中 2 条**（对 `TestHardExcludeOwned` 不匹配），而本步新增 **11 条**断言；实测「`reset_on` 写死 `'scope'`」这一变异在该命令下**全绿**（回归盲区）。**订正为 `-k "HardExcludeOwned or exclude_owned"`**（实测命中 11 条，全为本步新增）。
    **③ 目标文件清单的两处订正**：删 `gui/config_panel.py` 与 `tests/gui/test_config_panel_p56.py`（S6a 已落地、本步零改动即生效）；并订正本行的**内部矛盾**（本行写「已删除 `core/config_toml.py`（校验）」，而契约表条又要求本步改它，实测本步确改了它）。
    **④ 用例计数**：本行写的「当前 **12** 条既有用例」实测为 **14** 条（与 S9-1 的「12 / 实为 26」同族的计数漂移，建议去掉写死条数）。
    **另两条登记**：**(i)** `tests/gui/test_about_dialog.py` 在计划里被本行与 §七 S9-4 行**双重登记**，本步已新建（8 例）；**S9-4 行的「（新增）」应去掉**，并注明「语义断言归 S9-4」（其验收命令仍有效，不需调整）。**(ii)** 「关于」页原文本的 `分段软保底 (RLE deltas)` 说明随生成化消失（registry 的 `display_name` 无此后缀），属**单一真相源的既定代价**，登记备查。
    **③ 文档同步的计数项**：`CLAUDE.md`（**每次会话自动加载**）、`CLAUDE.md` 另一处、`docs/01-活跃/subsystems/保底系统/02-实施.md` 两处、`00-档案.md` 一处写「`BEHAVIOR_REGISTRY`（11 条目）」的句子在 +2 后失真，**文档同步块（ISSUE-017）须把「registry 条目数 11 → 13」列为显式回写项**。
    - **契约表同批扩（2026-10-09）**：本步在 `core/config_toml.py` **同 commit 扩 `_PITY_TYPE_KEYS`（新增 `hard_exclude_owned_skip` / `hard_exclude_owned_any` 两条，~~键集含 `on_all_owned`~~（**该半句为 pre-ruling 残留，见上方订正①**））**——两条新 type 的 `[[pity]]` 段否则被 S4c 的未知键硬拒；与 S4c 的一致性测试「反向断言契约表 ⊆ `_build_pity` 读取面」互为约束。<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->
    - 验收命令（GATE-6 补，块级最小验收）：`pytest -q tests/core/test_pity_validate_behaviors.py -k exclude_owned`——两条 registry 条目（`hard_exclude_owned_skip` / `hard_exclude_owned_any`）的 `create_behavior` 构造用例各一（`on_all_owned` 形态随构造参数正确落到 `ForceNotOwnedModifier`；**G3 的「全拥有」行为断言随 §3.10.4 的待确认项挂起，本命令只验构造与接线**）<!-- REVIEW-R1-FIX: ISSUE-931 --> **GATE-6-测试策略（2026-10-01 补：收集守卫）**：用例名须含 `exclude_owned`（两条 registry 条目各一，建议 `test_create_behavior_hard_exclude_owned_skip` / `test_create_behavior_hard_exclude_owned_any`）。实测 `-k exclude_owned` 在当前 12 条既有用例下**零命中**（pytest **exit code 5**），落地时确认收集到 ≥1 条 <!-- REVIEW-R1-FIX: GATE-6-测试策略 -->
<!-- REVIEW-FIX-PREV: ISSUE-009 -->
<!-- REVIEW-FIX-PREV: ISSUE-013 -->
<!-- REVIEW-FIX-PREV: ISSUE-008 -->
  - [x] S9-4（**已落地**：`94d7a12` + 收口 `50b24ed` / `0d1c9ee`）验收：§六 的 S9 口径三条 + G3 专项三条 + **G3 补充用例（含 `initial_count`）+ `sim` 两条通道都填**（~0.7 人时；ISSUE-009 / ISSUE-013 / ISSUE-008；2026-09-30 上调，~~新增 `tests/gui/test_about_dialog.py`~~（**归属订正（S9-3 收口，2026-10-14）**：该文件已由 **S9-3** 新建（8 例），本步复核 8 passed；**其语义断言归 S9-4**，S9-3 只落生成化））。**填充点就地**（2026-09-28 重梳，ISSUE-027）：两条通道各持同一 `GachaState`，各自调 `state.sim_view()`（通道 A 在 `Banner.draw`、通道 B 在 `StrategyContext.get_pity_probabilities`）；**不再新增 `Banner.draw` 形参**，`PityEngine` 两个入口加**必填参 `sim`**（2026-10-06：原为可选参 `external=None`，§3.10.2）。原「填充点定为 `GachaService`」的前提（`Banner.draw` 拿不到 `_initial_counts`）已随 `initial_counts` 提升为 state 字段而消失。｜目标文件 `tests/core/test_pity_integration.py`（既有文件，已含 `depends_on` 激活传播与 rotating / targeted 同池用例；G3 与 `sim` / `SimView` 用例加在此处）+ `tests/service/test_gacha_service.py`（`sim` 填充点断言）+ `tests/gui/test_about_dialog.py`（新增：关于页两处文本与 `BEHAVIOR_REGISTRY` 的 `display_name` 同源，两个形态的括注均须出现）<!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-6-测试策略 -->
    <!-- P64-S9-4-LANDED -->
    **S9-4 落地实测（`94d7a12` + 收口 `50b24ed` / `0d1c9ee`，2026-10-14）**：**1 文件 +563 纯新增**（`tests/core/test_pity_integration.py`，**源码零改动**，收口另改 4 个测试文件）；全量 **`3018 passed / 35 skipped`**；`ruff` 与 `refcheck` 通过；`p79_verify` 与 `p82_baseline --verify` PASS 零漂移；8 处变异逐处还原。交付：**G3 专项 5 条**（① 触发时已拥有的 UP 归零、同时证明它落在 Q 内被搬空；② `counter < τ` 时已拥有 UP **保留原概率**（与 pool 层近似的分界）；③a/③b 两形态；补充：**初始持有的 UP 同样被排除**）、**S9 口径三条**（`sim` 送达 13 类型 × 3 入口的同一性；`StateView` + `depends_on` 传播；**`ctx.state` 通道关闭**含「动态发现恰 6 个 Modifier + AST 扫描 `X.state` 属性读取数为 0」与 `pity.py` 的三层判据）、**通道 B 的 1e-12 对照**（S8-6 收口登记归本步）。
    **四条订正（S9-4 审查，2026-10-14）**：
    **① 过滤词放宽**（见下方验收命令行）：`ctx.state` 那一条**当时无绑定验收命令**。
    **② `_ALL_TYPES` 覆盖缺口已修**：`tests/core/test_pity_registry_schema.py` 的 `_ALL_TYPES` 是手工维护的清单，**S9-3 的两个新 type 逃出了「全部类型」扫描**（其中 `test_all_presets_construct_in_engine` 是 S4-5「preset 构造失败被静默跳过」形态的**唯一机器防线**）。收口已把两条并入（新建 `_C94_TYPES`）并**一律去掉写死条数**；**收口给了可执行证据**（用 pytest 插件在收集期变异 + 对照组：13 条下两条变异各自变红，还原 11 条下同变异全绿，即缺口真实存在且已被闭合）。
    **③ 一处已失真的论证整体改写**：`tests/service/test_batch_simulator.py` 原以「`NotOwnedModifier` 无产出方、任何 env 都不可达、`core/pity.py` 连 import 都没有它」为硬理由，而 S9-3 后**三句全不成立**（`pity.py:25` 已 import、两条 G3 preset 已产出它）。收口改写了该段（含同文件另 3 处同句副本与 1 处旧类名错引）。
    **④ 两处测试 docstring 事实错误**：原写「`c = ctx; c.state.get(...)` 可绕过 AST 扫描」**实测拦得住**（属性名仍是 `state`），真实绕过只有 `getattr` / `vars` / `__dict__` 这类**字符串键**形态；另一处「新增 Modifier 不必改本用例」与其精确集合断言矛盾。两处已订正。
    **两条计数/时点登记**：**(i) ISSUE-920 的前提已过期**（本行与本节的提示写「该文件现存用例名无一含 `g3` / `sim`」，而 S9-2 落地后已有 **4 条**名含 `sim`，故「命中项全部为本步新增」**不可能达成**；**另一半**：计划 §六 写「该文件现零 `sim_view` 用例」亦已过期，`test_channel_a_fills_sim_view` 由 S9-2 落在服务层测试文件）。**(ii) 文档同步的计数项**：`CLAUDE.md`（**每次会话自动加载**，三处）、`02-实施.md`（两处）、`00-档案.md`（一处）写「`BEHAVIOR_REGISTRY`（11 条目）」在 +2 后失真，**文档同步块（ISSUE-017）须列为显式回写项**。
    - 验收命令：`pytest -q tests/core/test_pity_integration.py -k "g3 or sim or ctxstate"`（**过滤词放宽（S9-4 收口，2026-10-14）**：原写 `-k "g3 or sim"` **收不到** `TestCtxStateChannelClosed` 的三条用例（类名与用例名都不含 `g3` / `sim`），而本行的验收面含「§六 S9 口径**三条**」，故该条**当时无绑定验收命令**；放宽后实测 **15/43**、覆盖全验收面）（**ISSUE-920 提示**：该文件现存用例名无一含 `g3` / `sim`（实测 **12** 条为 `o1_lookup` / `dependent_activated` / `rotating_and_hard` 等；**ISSUE-947：本节原写「10 条」，与 §六 通道 B 条的「12 条」自相矛盾**） <!-- REVIEW-R1-FIX: ISSUE-947 -->，故这条 `-k` 只有在 S9-4 **新增**用例按此命名时才有匹配——**无匹配时 pytest 以 exit code 5 结束，会被误读为通过**，落地时须确认收集到 ≥1 条；加 `pytest -q tests/service/test_gacha_service.py -k sim_view` 覆盖填充点——**ISSUE-920：该用例须本步新增且用例名须在计划内写死**（建议 `test_channel_a_fills_sim_view`；原文件零 `sim_view` 用例，零匹配的 `-k` 以 **exit code 5** 假通过；原写 `-k external`，`external` 已于 2026-10-06 随 §3.10.2 改判改名，该过滤词失去对象）。断言 `Banner.draw` 路径上的 `before_draw` 的 `sim` 实参为 `SimView` 实例（`owns()` 可调用），即 `core/banner.py` 的 `state.sim_view()` 填充点确实接线<!-- REVIEW-R1-FIX: GATE-6-测试策略 -->；加 `pytest -q tests/gui/test_about_dialog.py` 覆盖关于页文本同源）——§六 的 S9 口径三条 + G3 专项四条（保底触发时已拥有的 UP 不被选中 / **普通抽卡仍能产出已拥有的装备** / **③a** `hard_exclude_owned_skip` 全拥有时退化为恒等 / **③b** `hard_exclude_owned_any` 全拥有时仍给出一件 UP；**③a / ③b 两条随 §3.10.4 的待确认项挂起，机制定稿前均不作为已定稿验收**）+ G3 补充用例（`initial_count` 的 UP 装备同样视为「已拥有」）+ ~~`external is None` 兜底（策略层查询路径不崩溃，或按 §六 登记为已知差异）~~（**2026-10-06 随 §3.10.2 改判删除**：`sim` 非 Optional，「读到 `None`」这一状态不存在，该兜底分支为死分支、无对象可断言；现行口径的验收见上一条）+ **`sim` 为必填参且两条通道都填**（`Banner.draw` 经 `core/banner.py`、`StrategyContext.get_pity_probabilities` 经 `core/strategy.py`，任一缺参在构造 `DrawFacts` 时即 `TypeError`）+ **`SimView` 只暴露 `owns` 源**（`uses_sim` 注解名不在已知源集合时抛 `ConfigError`）<!-- REVIEW-R1-FIX: GATE-6-测试策略 --><!-- REVIEW-FIX-PREV: ISSUE-GATE-FAIL-6-测试策略 -->
    - **AUDIT-BREAK-9 追加（通道 B 独立验收，强制）**：上述用例只覆盖通道 A（`GachaService` → `Banner.draw` → `PityEngine.before_draw`）。**通道 B**（`StrategyContext.get_pity_probabilities` → `PityEngine.get_probabilities` 经 `_pity_cache`，见 `core/strategy.py:161-179`）必须另有独立验收：`pytest -q tests/core/test_pity_integration.py -k channel_b`（**ISSUE-943：本行原未随 §六 同批改写，而本行是通道 B 的**唯一**验收面，位置比 §六 更关键**）：**用例名须在计划内写死**（建议 `test_channel_b_matches_before_draw`，filter 用 `-k channel_b`），并在落地时先 `--collect-only` 确认收集到 ≥1 条（**ISSUE-727：原写 `-k "reads and strategy"`，`reads` 已于 2026-10-06 删除，该文件现存 12 条用例无一含这两个词，filter 零命中、pytest 以 exit code 5 假通过**）。断言口径（**ISSUE-943：原写「配 `reads` 的池」，该前提已随 `reads` 删除而失效**）：**所有保底都能读到 `sim`（非 Optional，永远填充）**，经 `ctx.get_pity_probabilities(key)` 取到的分布，与**同刻** `before_draw` 返回值逐元素一致（容差 1e-12），且**非退化为恒等 `expected_probs`**。<!-- REVIEW-R1-FIX: ISSUE-943 -->理由：通道 B 是真实消费方（`strategies/builtin/pity_reserve.py:52` 调 `ctx.get_pity_probabilities(qualified_key)`），且它**绕过 `Banner.draw`**，A 通道全绿不能推出 B 通道正确。目标文件补 `core/strategy.py`（`_pity_cache` 与 `get_probabilities` 调用点）与 `service/gacha_service.py`（`ctx` 构造处 :412，保证两通道共用同一 `GachaState` / `_initial_counts` 源）。<!-- REVIEW-FIX-PREV: AUDIT-BREAK-9 -->
  - [x] S9-5（**已落地**：`3facb27` + 收口 `9637e01` / `cf92e55`）**`initial_count` 存量持有口径的策略侧迁移**（~0.4 人时；**2026-10-10 新增**，ISSUE-730 / ISSUE-944 的落地块）｜**目标文件** `strategies/builtin/pity_reserve.py` + `strategies/builtin/pool_quota.py` + `strategies/builtin/smart.py` + `strategies/builtin/stop_on_target.py`（**4 个文件共 9 处**，2026-10-10 实测：`pity_reserve` 2（[:26](gacha_simulator/strategies/builtin/pity_reserve.py#L26) / [:34](gacha_simulator/strategies/builtin/pity_reserve.py#L34)）/ `pool_quota` 2（[:28](gacha_simulator/strategies/builtin/pool_quota.py#L28) / [:52](gacha_simulator/strategies/builtin/pool_quota.py#L52)）/ `smart` 2（[:39](gacha_simulator/strategies/builtin/smart.py#L39) / [:46](gacha_simulator/strategies/builtin/smart.py#L46)）/ `stop_on_target` 3（[:30](gacha_simulator/strategies/builtin/stop_on_target.py#L30) / [:41](gacha_simulator/strategies/builtin/stop_on_target.py#L41) / [:45](gacha_simulator/strategies/builtin/stop_on_target.py#L45)）；原记「5 个内置策略的 9 处」在**文件数**上不准确，处数 9 正确）+ `tests/core/test_strategy.py`（新增用例）+ **`tests/service/test_gacha_service.py`**（**2026-10-10 补登记**：3 条非零 `initial_count` 的既有用例随本块行为改变而必红，须同 commit 改造，见下条）
    - **改动形态**：9 处 `ctx.acquired.get(t.card_id, 0)` 一律改为 `ctx.state.total_holding(t.card_id)`（含初始持有口径）。**`ctx.acquired` 本身不改定义**——P60 语义「本次模拟**新获得**」由 [tests/service/test_gacha_service.py](tests/service/test_gacha_service.py) 的 `test_initial_count_not_prepopulated` 钉住，迁移的是**消费侧**（§四 `core/strategy.py` 行）。
    - **既有测试的必红面（2026-10-10 补登记，强制）**：`tests/service/test_gacha_service.py` 有 ~~**3 条**~~ **4 条**非零 `initial_count` 的用例会随迁移变红（**订正（S9-5 实测，2026-10-15）**：计划登记 3 条是 2026-10-10 时点值，第 4 条 `test_initial_count_feeds_overflow_bands` 由 **S9-2 收口**于 2026-10-14 落地、晚于该时点；其改造形态是**夹具 `quantity_needed` 1 → 2、断言未动**。另三条的改造形态：`test_initial_count_not_prepopulated` 断言 2 → 1；`test_initial_count_multiple_cards` **夹具重做**（单池 0.5/0.5 随机池 → 两池各 100% 单卡，原断言在该夹具下不稳定：实测失败率 77.0%）；`test_initial_count_does_not_satisfy_target` **整条重写并改名**为 `test_initial_count_satisfies_target`）的用例用 `SmartStrategy`（本块 4 个目标文件之一），其行为随迁移而改变，**必须与本块同一 commit 改造**，否则该 commit 的 `pytest -q` 全红（H9 拦推）：① `test_initial_count_not_prepopulated`（[:41](tests/service/test_gacha_service.py#L41)）——`initial_count=1` / `quantity_needed=2`，现状策略判「还缺 2 张」抽 2 次（`card_counts == 2`），迁移后判「还缺 1 张」抽 1 次（**断言值改为 1**；其**意图**「`card_counts` 只记新抽到的、不预填初始持有」不变）；② `test_initial_count_does_not_satisfy_target`（[:108](tests/service/test_gacha_service.py#L108)）——`initial_count=5` / `quantity_needed=1`，迁移后策略**开局即判达标、一张不抽**（`card_counts` 为空、`total_draws == 0`），该用例的 docstring「**初始持有再高也不满足需求**」正是 2026-10-10 裁决所推翻的语义，**须整条重写或删除**（不得只改断言值，否则留下一条与现行口径相反的用例）；③ `test_initial_count_multiple_cards`（[:77](tests/service/test_gacha_service.py#L77)）——`initial_count=3` / `quantity_needed=2`，迁移后 card_A 开局达标、断言 `card_A >= 2` 失败。三条均为「策略判据口径」的直接后果，不是测试自身的缺陷。
    - **次序（强制）**：本块**必须排在 S9-2 之后**——`total_holding` 的 `initial_counts` 形参由 S9-2 移除并改读 `self.initial_counts`（§四 `core/state.py` 行），早于 S9-2 落地时该函数仍是两参形态，9 处改不动（写成 `total_holding(card_id, state.initial_counts)` 会绕过「单一真相源」定稿）。
    - **为何不用 `ctx.sim.owns()`（2026-10-10 定稿，取代 §四 该行原写的「改用 `SimView.owns()`」）**：`SimView` 是给**保底侧**的只读隔离面（`PityContext.sim`），而策略侧已持有公开的 `ctx.state`；在策略侧新增 `StrategyContext.sim` 字段会连带改 `build_strategy_context`（§四 `core/strategy_context_builder.py` 行定稿为「本次不改」）与 5 个测试文件里 **9 处**直构 `StrategyContext(...)` 的形参（`tests/core/test_strategy.py` ×2、`tests/core/test_batch_draw.py`、`tests/core/test_p69_strategy.py`、`tests/core/test_worst_impact_correctness.py` ×3、`tests/test_p58_milestone.py` ×2；实测 9 处构造）。两 API 是**同一实现的同一口径**（§3.10.2 的 `owns` 即 `total_holding` 的 O(1) 包装），故取零新增字段的一侧。
    - **同轮查证、判为不纳入的三处**（**第三处由 S9-5 审查补登，2026-10-15**）：⓪ `core/target_card.py:29-32` 的 `TargetCardSet.get_unfinished_targets(acquired)` 是**公开 API**（`core/__init__.py:142` 导出），其判据 `acquired.get(t.card_id, 0) < t.quantity_needed` **仍是不含初始持有的旧口径**；生产侧**零调用**（唯一调用在 `tests/core/test_target_card.py:19`）。它是**将来写策略者的静默陷阱**（传入 `ctx.acquired` 即得旧口径），故按「旧口径须显式登记」纪律列此，**处置待裁决**（登记为待清理死码 / 或裁决其语义并纳入迁移）；① `TargetAcquiredCondition`（[stop_condition.py:61](gacha_simulator/core/stop_condition.py#L61)）经 `state.get_card_count()` 读 `state.acquired`，语义是「**本次模拟获得** N 张」（`description()` 即「获得 N 张 X」），与本块的「是否已拥有」不是同一判据；② `GachaService` 的循环快照指纹（[gacha_service.py:90](gacha_simulator/service/gacha_service.py#L90)）用 `state.acquired` 做差分检测，与持有口径无关。**两者均维持现状。2026-10-10 用户裁定（针对 ①）**：`TargetAcquiredCondition` 的语义就是「**获得** N 张后停止」，**不含**初始持有——若取含初始持有，则「开局已有 N 张 + `quantity=N`」会立刻满足、一场不抽，与该条件的配置意图相反。故 ① 以「语义不同源」判为不纳入，② 同理。
    - **与 S9-4 的分工（不可互替）**：S9-4 的 G3 口径对照用例验「**引擎侧与策略侧结论一致**」（跨层，落 `tests/core/test_pity_integration.py`），本块验「**四个策略的 9 处判据都已迁移**」（层内，逐策略覆盖）。只跑对照用例时，未被它触达的其余三个策略的判据仍可能漏改。
    <!-- P64-S9-5-LANDED -->
    **S9-5 落地实测（`3facb27` + 收口 `9637e01` / `cf92e55`，2026-10-14 / 15）**：7 文件 +371/-45（4 个策略文件 + 3 个测试文件；收口另改 2 个测试文件，**生产代码第二轮零改动**）；全量 **`3023 passed / 35 skipped`**（基线 3018，+5 = 4 条策略用例 + 1 条 G3 跨层用例）；`ruff` 与 `refcheck` 通过；`p79_verify` 与 `p82_baseline --verify` PASS 零漂移（**归因**：`config/config.toml` 的 24 条 `card_defs` 的 `initial_count` **全为 0**，故本迁移不改变两条护栏的固定输入行为）；8 处变异逐处还原（M1「`total_holding` 漏算初始持有」→ **13 failed**）。
    **落地形态**：4 个内置策略（`pity_reserve` / `pool_quota` / `smart` / `stop_on_target`）共 **9 处** `ctx.acquired.get(t.card_id, 0)` → `ctx.state.total_holding(t.card_id)`（**行号订正**：实测 `pity_reserve` :31/:39、`pool_quota` :33/:57、`smart` :44/:51、`stop_on_target` :35/:46/:50，计划登记的 26/34 等为 2026-10-10 时点值、统一 +5 行）；`ctx.acquired` **定义未改**；四个文件各补一段口径纪律的模块 docstring（「是否已拥有」一律取 `total_holding`）。**逐策略覆盖**：`tests/core/test_strategy.py` 四条（用例名与计划写死的四个一致，覆盖 9/9 判据处，含 `select_action` 侧与 `_pool_needs_target` 侧），互不代偿（逐处回退各自只红对应那条）。
    **三条订正（S9-5 审查，2026-10-15）**：**① G3 跨层条判据 ③ 是同义反复**（`SimView.owns` 就是 `total_holding`，两侧同一对象同一函数、无独立判别力；M1 下两侧同时变空仍绿）→ 降级为「口径同一性守卫」并补进未覆盖面清单。**② `pool_quota` 的 s1 迁移不是「行为中性」**：**单 banner 下**确实不可观测（第三段兜底产出与第二段逐字相同），但**多 banner 下可观测**（第二段带 `_pool_needs_target` 过滤、第三段不带，实测迁移后抽 B1、换回旧谓词抽 B2）→ 措辞已改为与实测一致，并保留「是否让第三段也读该判据」的设计裁决登记。**③ G3 跨层条判据 ④ 的牙齿是收口补上的**（见上）。
    **两条覆盖边界登记**（计划原未登记）：`pool_quota` 的 s1 在单 banner 下被第三段遮蔽；`stop_on_target` 的 s2 在单目标夹具下不可辨（需挂未达标目标卡）。
    - 验收命令（GATE-6）：`pytest -q tests/core/test_strategy.py -k holding_includes_initial`——**用例名须在计划内写死**（建议 `test_pity_reserve_holding_includes_initial_count` / `test_pool_quota_holding_includes_initial_count` / `test_smart_holding_includes_initial_count` / `test_stop_on_target_holding_includes_initial_count`，四个策略各一条；亦可合并为一条 `parametrize` 覆盖四个 key，用例名仍须含该过滤词）。**断言形态**：`state.initial_counts = {card_id: n}` 且 `state.acquired` **为空**、目标 `quantity_needed = n` 时，策略判「该目标已达成」（不再为该目标抽对应池）；对照组为 `initial_counts` 为空时判「未达成」。**收集守卫实测（2026-10-10）**：`tests/core/test_strategy.py` 现有 **6** 条用例（`fixed_count_strategy` / `target_hunting_strategy` / `next_event_wait_returns_float_and_respects_cap` / `strategy_exhausted_returns_time_advancing_wait` / `draw_segment_strategy_exhausted_fallback` / `priority_chain_strategy_exhausted_fallback`），`-k holding_includes_initial` **零命中**（pytest 以 **exit code 5** 假通过），落地时先 `--collect-only` 确认收集到 ≥1 条且命中项**全部为本步新增**<!-- REVIEW-R1-FIX: GATE-6-测试策略 -->
- [x] ~~S12 条件外置~~（**2026-10-06 整块取消**，§3.14 改判）。原注：已迁至 M1（排在 S2 之后、S4 之前，见上；ISSUE-101）。M2 不再包含本项。

> **M2 完成标志**（**落地状态，2026-10-15**）：
> ① **卡级管道与 M1 产物容差 1e-12 一致**（§六 S8 口径）：已由 **S8-6** 落地（`TestS8CaliberAgainstS5Products`，对照基准为**现跑旧类**）。
> ② **单卡定向与 G3 专项通过**（§六 S9 口径）：单卡定向由 **S8-6** 落地；**G3 专项**由 **S9-4**（引擎侧三条 + 两形态 + 含初始持有）与 **S9-5**（跨层半条）落地。
> **⚠ 口径提醒（S9-4 审查登记，强制）**：**§3.10.4 明令「`on_all_owned` 的两形态在机制定稿前不得当作已定稿验收通过」**，故 G3 专项的绿只表示「两条实现的**实际行为**已被钉住」，**不是**「该机制已定稿」。

### GATE-5 回滚策略

<!-- REVIEW-FIX-PREV: ISSUE-GATE-granularity -->
- **回滚单元（2026-09-22 修订，ISSUE-GATE-granularity）**：G16 独立；**主线改为逐子块独立 commit，回滚单元 = 任务单元**（S1a 至 S11 共 **30** 块（**2026-10-10 再经 S1c 拆分**，原 29），见 GATE-1；2026-09-22 第八轮细分后由 26 变为 29，本轮 AUDIT-BREAK-7 新增 S7d、2026-10-06 新增 S4c，**2026-10-09 取消 S2b、再细分 S2a 并改按逐块求和核定后为 29**）。原稿「主线整体一次回滚」已撤销，其后果是单块失败只能整体回退，与逐块排期不相容。**回退规则 = 依赖闭包（强制，方向 = 向消费方闭包；ISSUE-GATE-5-rollback 补齐）**：回退某子块时**必须连带回退所有消费其产物的后继子块**——只有**同层兄弟块**之间互不牵连（如 S1b-1 与 S1b-2、S5a 与 S5b、S10-1 与 S10-2）。原稿只写「任一子块验收失败只 revert 该 commit，不牵连已通过的兄弟块」，该表述对**低层块**不成立（M2 段早已写明依赖闭包规则，M1 漏写，本条补齐）：
  - 回退 **S1a**（叶子原语层，含 `_SOFT_TYPES` / `_HARD_TYPES` / `_EVENT_DRIVEN_TYPES` 三个模块级常量；§3.1.4 骨架的 `Pity(PityBehavior)` **不继承** `CounterBasedBehavior`，裸名引用即 `NameError`）→ 连带回退 **S1b 至 S11 全部**；
  - 回退 **S1b / S1c / S1d**（Tracker / Lifecycle 族，含 `build_lifecycle`）→ 连带回退 **S3 至 S7**（凡引用被回退符号者一律连带；S2a-1 / S2a-2 不引用 Tracker / Lifecycle 者可保留）；
  - ~~回退 **S12-1 / S12-2**~~（**2026-10-06 取消**，无此二块）→ 原连带回退范围 **S3、S4（含 S4b）、S5、S6、S7**（§3.2 / §3.3 / §3.14.2 的 preset 一律为 `ConditionalModifier` 包裹形态，去掉包装器即全部断裂），S10 / S11 视其是否消费被回退符号而定；
  - 回退 **S3-1 / S3-2**（统一骨架）→ 连带回退 **S4 至 S7**；
  - 回退 **S4-1 / S4b** → 连带回退 **S4-2 至 S6b**（preset 工厂与构造形参消费 registry schema 与 `PityDef.priority`）。**S4-1 的回退面（GATE-3 定稿，2026-10-01）**：S4-1 的「过渡判据」与 S4-2 / S4-3 的「按条目置 `class: None` + 写 `preset`」是**同一机制的两端**——单独 revert S4-1 会让已迁移条目落回旧判据（`preset` 不再是校验对象、而 `class` 已是 `None`）而**导入期即失败**，故回退 S4-1 必须连带 S4-2 / S4-3（含 S4-3 收口），与本行既有范围一致；**反向不成立**——回退 S4-2 / S4-3 不牵连 S4-1（过渡判据正是为此保留）。<!-- REVIEW-R1-FIX: ISSUE-930 -->
  - 回退 **S4c**（键契约与 `load_toml` 原子性）→ **无连带**（只改 `config_toml.py` 的解析/加载路径与测试，不产出被消费符号）；② 的原子性改动是纯收窄，不改变成功路径的行为
  - 回退 **S4-2 / S4-3** → 连带回退 **S4-4**（其防线与旧段删除以「10 个 preset 已落地」为前提）与 **S5**。
  - 回退 **S7d**（存量保底测试文件改造，AUDIT-BREAK-7）→ **无连带**（只改测试文件，不产出被消费符号）；但**发布前「一次性移除旧类」的 commit 不得早于 S7d 完成**。回退 **S8-7**（槽位消费测试改造）**须与 GATE-5 末条（发布前一次性移除旧保底类）成对**——**ISSUE-906 修正（2026-10-01）**：原稿写「须与 **S8-4** 成对（同一删除面），单回退一方会让测试重新引用已删符号」，按 ISSUE-901 改判后 S8-4 已不碰任何槽位结构（它只删 `aggregate_probs_by_rarity` / `infer_rarity_from_spec` 及导出面），与 S8-7 不再共享删除面。S8-7 处置的是「测试仍引用槽位字段」这一**形态**，其收口点是末条删字段那一次 commit；**S8-7 与 S8-4 自此互不牵连**，可各自独立 revert。<!-- REVIEW-R1-FIX: ISSUE-906 --><!-- REVIEW-FIX-PREV: AUDIT-BREAK-7 -->
- **强制（低层块回退 = 该里程碑的部分回退）**：低层块被回退后，**必须重跑受影响块的验收命令**（逐块命令见 GATE-1）并确认全绿，才可继续后续子块；未重跑即恢复施工，等于在未验证的状态上叠加新块。<!-- REVIEW-FIX-PREV: ISSUE-GATE-5-rollback -->
- **安全网**：全量 preset 化不分阶段，**旧类保留到等价性测试通过为止**；每个子块的 commit 都是「新增/改写 + 该块验收」的原子对。**「任一块可单独 revert」有范围限定**：只在**同层兄弟块**之间成立，低层块回退会带走其消费方（依赖闭包规则见上）
- **等价性测试失败**：停在**失败的那一批 preset**（S5b 按 counter 驱动 / 事件驱动分批，每批一个 commit），保留失败 preset 为「未迁移」；**回退方式改为 `git revert` 该批次的 commit**（**不依赖 registry 保留旧类指针**：§3.2 定稿 `class` 一律置 `None` 之后 registry 已无旧类入口，原写「回退 registry 到该 preset 指向旧类」不可执行，见 GATE-3(c)）。旧类本身仍在代码中，直到发布前一次性移除，故「未迁移」的 preset 仍有可用实现；已通过的批次不回退
- **G16**：独立 commit，与 P64 主线完全解耦，可随时 cherry-pick 或 revert。**2026-10-10 补**：G16-1 现为**两个 commit**（`707cbbf` 落地 + 其后实现审查 6 项的修复 commit），回滚单元仍是「G16-1」这一**任务单元**——revert 须两个一起、顺序为先修复 commit 后 `707cbbf`（修复 commit 依赖 `707cbbf` 引入的 `never` 分支与白名单）；见「自动化审查记录」的 G16-1 实现审查条目
- **P82**：**P82-1 / P82-2 各为独立 commit**（与 §七「独立先行块」组的「独立 commit」宣告一致），可单独 cherry-pick 或 revert；但**回退不是无条件解耦**——**P82-1**（`PityEngine.__init__` 的排序视图 + `get_behaviors_for_pool`）改的是概率管道的**实际执行顺序**（§1.5 登记五类敏感集合），被 **S5a / S5b**（等价性装置）与 **S6b**（priority 排序）消费，回退须按上文依赖闭包规则连带处理消费方；**P82-2** 新建的 `tests/fixtures/p82_baseline/` 基线快照**随 P82-1 回退同时失效**（它固化的正是接线前的顺序语义），且 S5a / S5b 的「现跑旧类」对照基准与之同源——回退后须**用同种子重跑 `scripts/p82_baseline.py` 重新生成基线**，方可再跑 S5a / S5b 验收，不得沿用失效快照。<!-- REVIEW-R1-FIX: GATE-5-回滚路径 -->
- **里程碑暂停点（2026-09-22 新增）**：**M1 结束是一个明确的暂停/交付点**——此时架构已统一、行为与旧类一致、保障层到位。M2 可随时暂停或延后，不影响 M1 交付物的可用性
- **M2 的回滚单元（2026-09-22 第八轮修订）**<!-- REVIEW-FIX-PREV: ISSUE-GATE-5-rollback -->：**逐子项回滚，回滚单元 = 子项**（S8-1 至 S8-7 / S9-1 至 **S9-5** 各一个 commit，见 GATE-1 的 M2 清单；**2026-10-10 补 S9-5**）。**依赖闭包规则（强制）**：S9 依赖 S8，若回退 S8 中任一子项，必须**连带回退其后的 S8 子项与全部 S9 子项**（S8-2 起管道形态逐项叠加，中途回退会留下半卡级 / 半槽位的混态），但 **S8 内部已通过的前序子项不因此回退**。原稿写「S8 + S9 整体」，与 M1 刚确立的「回滚单元 = 任务单元」相反；且 S8 / S9 各含 6 / 4 个子项、原稿无独立 commit，整体回退等于丢掉约 5.5 人时的可保留成果，已撤销。~~**S12 不在 M2 回滚单元内**（已随 M1 落地，ISSUE-101）；M1 内若回退 S4 / S5 等消费 S12 的子块，`ConditionalModifier` 本身是独立 commit，可单独 revert 而保留其他块；**反向不成立**——回退被消费方（S12-1 / S12-2）须按上方依赖闭包规则连带回退消费方 S3 / S4 / S5 / S6 / S7。~~（**2026-10-09 删，ISSUE-004**：S12 已于 2026-10-06 整块取消，`ConditionalModifier` 不存在，「独立 commit 可单独 revert」与「回退被消费方 S12-1 / S12-2」两说均无对象。M2 的回滚单元仍为逐子项回滚（S8-1 至 S8-7 / S9-1 至 S9-4），依赖闭包规则不变。）<!-- REVIEW-FIX-PREV: ISSUE-GATE-5-rollback --> **S9 内部的回滚边界（2026-10-09 补，GATE-5）**：S9-1 / S9-2 / S9-3 **互为同层兄弟块、互不牵连**，三者各自只新增本块符号、跨块无消费关系，故可逐子项独立 commit / revert（与 S8 的逐项叠加形态不同）；**S9-4 是共同验收面**——回退 S9 内任一前序子项后须重跑 S9-4 的验收命令，而 S9-4 自身不产出被后续消费的符号，故不反向牵连 S9-1…S9-3。<!-- REVIEW-R1-FIX: GATE-5-回滚路径 -->
- **发布前**：主线完成后一次性移除旧保底类（无历史包袱原则，`RELEASED=False`）。**ISSUE-502 的收口点**：`_redistribute_scope` 的**函数本体**、`pity.py` 内 4 处旧类调用点（:549 / :661 / :727 / :731，2026-10-09 实测订正）与 10 个旧行为类在本 commit **同批删除**；在此之前 `_redistribute_scope` 与 `transfer_linear` 并存（前者只服务旧类，后者只服务新骨架，两者不得互相调用）
  - **末条 = 完整收口清单（ISSUE-905 / ISSUE-901 定稿，2026-10-01）**：全篇**十余处**写「并入 GATE-5 末条……的同一个 commit」（§3.9.3 组件处置表的多行、§3.9.3 跨文件同步清单 B / D 段、§3.9.4、§四、S8-4、S8-7 等），若本条只列三项，实施者按本条施工即**漏删/漏改**——被引用的那一条本身必须完整。**七项同批，缺一即留下半态**：① `_redistribute_scope` 的**函数本体**（[pity.py:416](gacha_simulator/core/pity.py#L416) 起，导出面已在 S8-4 删，本项只清函数本体）；② `pity.py` 内 **4 处旧类调用点**（:475 `RotatingBehavior` / :587 `RotatingCRBehavior._force_featured` / :653、:657 `TargetedBehavior`；2026-10-09 实测订正，原写 `477 / 589 / 655 / 659` 整体 +2）<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->；③ **10 个旧行为类 + `SoftPityMixin`** 的类本体（`core/__init__.py` 的 re-export 已在 S4-3 删）；④ `PoolPitySpec` 与 `DrawInfo` 的 **6 个槽位字段** `scope_slots` / `featured_slots` / `card_to_slot`（各 3 个），含 `PityEngine` 三个调度入口的 `DrawInfo(...)` 透传实参（[pity.py:1290-1300](gacha_simulator/core/pity.py#L1290-L1300)）；⑤ `compute_scope_mappings` 的**槽位产出**（减量改造，只留 `scope_cards` / `featured_cards` 及其反向索引）；⑥ **两处构造点的改造**——`service/batch_simulator.py`（[batch_simulator.py:273-290](gacha_simulator/service/batch_simulator.py#L273-L290) 的五元组解包与 8 字段 `PoolPitySpec` 构造）与 `core/worst_impact.py`（[worst_impact.py:543-552](gacha_simulator/core/worst_impact.py#L543-L552) 的槽位实参 :549/:550/:551（无硬编码表，亦无 `_ref_pool` 分支））；⑦ **S8-7 的 5 个槽位消费测试文件**的收口确认（S8-7 已在 M2 内完成改造，本项只跑 `grep -rn "scope_slots\|featured_slots\|card_to_slot\|_redistribute_scope" tests/` 归零，并处置其**例外（三项；ISSUE-942）**：① `tests/core/test_pity_equivalence.py`（本项执行时 **S8-2 已改造 `test_pool.py` / `test_worst_impact.py`**，故此刻的例外只剩它；上面三项是 S8-7 时点的口径，与 §七 S8-7 的例外清单同源、两处不冲突）；② `tests/core/test_pool.py:62` 与 ③ `tests/core/test_worst_impact.py:303`**（原写「唯一例外」，与 §七 S8-7 的三项清单字面冲突，读者会误以为 S8-7 也只有一项）**。① 的处置：`tests/core/test_pity_equivalence.py`——该文件的「旧侧」随 ①②③ 一并消失，须同批改为「读 S5 阶段固化的 golden 快照」或整体归档，**不得留下引用已删符号的装置**）。<!-- P64-S7E-GAP-REG -->
      **缺口登记（S7e 审查，2026-10-13）**：本项的**首选处置当前不可执行**——`tests/fixtures/` 下**不存在任何 S5 阶段固化的 golden**（只有 `p79_golden/` / `p82_baseline/` / S7e 新增的 `p64_s7e_golden.json`），而 `tests/core/test_pity_equivalence.py` 本身（2486 行、26 处旧类引用）**零** golden / json / fixtures 引用。即：**S7e 的立块理由（趁旧类存活固化成 golden）对该文件逐字成立，而它被明确排除在 S7e 范围外**。按现状，删除点对该文件**只能整体归档**，S5a / S5b / S5c 建起的**位级等价判据随之失传**。
      **两条出路（待裁决）**：**(a)** 在 GATE-5 之前另立一块，用与 S7e 相同的手法为该 harness 固化 golden（成本明显高于 S7e：它是 93 条量级的全套件、跨 10 个类型的多抽序列）；**(b)** 明确裁决「整体归档可接受」并登记裁决痕迹。**尺度说明（供裁决参考，不代替裁决）**：端到端层面的引擎输出**已被 `p79_verify` / `p82_baseline` 的 9 组 CompactResult golden 钉住**，故丢的不是「引擎输出无人守」，而是**按类型 / 按抽数序列的单元级位级判据**（定位回归时粒度更粗）。**不得默认落下**：无论选哪条，都须留下显式的裁决记录。<!-- REVIEW-R1-FIX: ISSUE-905 --> <!-- REVIEW-R1-FIX: ISSUE-901 --><!-- REVIEW-R1-FIX: ISSUE-002 --><!-- REVIEW-R1-FIX: ISSUE-003 --> <!-- REVIEW-R1-FIX: ISSUE-955 -->
  - **⑧ 五个测试文件的收口（S7d 落地后补登，2026-10-13，S7d 审查）**：原七项**无一项覆盖测试文件的旧类断裂点**，而实测旧类符号的命中**不止 `test_pity_equivalence.py` 一处**。五个文件、三类处置，缺一即 `pytest` **收集期**红：
    - **等价性装置（断言对象就是旧实现）**：`tests/core/test_pity_equivalence.py`（豁免，**保持不动**）、`tests/core/test_pity_modifier.py`（`:36` 模块级 import 4 旧类 + 6 条 `*_matches_old_class` 位级对照）、`tests/core/test_pity_tracker.py`（`:547` / `:590` / `:794` / `:822` 函数局部 import，做随机数消费次数与轨迹逐位对照）、`tests/core/test_pity_registry_schema.py:764`（函数局部 import）。**处置：先固化为 golden 数值（须在旧类存活时生成），删除时只删对照段、保留 golden 断言**，落点见新增的 **S7e**。
    - **旧类兼容分支守卫**：`tests/core/test_pity_registry_schema.py` 的 `_LegacyKwargsProbe(HardPityBehavior)`（`:69`）与 `test_legacy_branch_still_works` / `test_legacy_branch_no_longer_injects_lifecycle` / `test_no_preset_and_class_none_raises_value_error`。**处置：随 `create_behavior` 的 legacy 分支同批删除**。
      <!-- P64-S7E-CLOSURE -->
      **清单订正（S7e 审查，2026-10-13）**：本条守卫清单**漏了一项、且对另一项的处置写错**。① `test_missing_preset_key_raises` **不属本清单**（原写在别处被本块的 commit message 归为「随 legacy 分支删除」）：实测它走 `_validate_registry()`（`pity.py:1183`），该判据自 S4-3 收口起已是 **preset-only**、**随删除点存活**；它只是拿 `HardPityBehavior` 当 `class` 键的**惰性填充值**。故删除点的动作是**改写**（换掉那个填充值）而非删除，否则「缺 `preset` 必抛」这条守卫会一并消失。② 本清单应补入它并标明「改写」。
    - **删除点对 golden 装置的动作（S7e 审查补充）**：除删「构造旧类并对照」那一段外，还须**改写 `_assert_matches_golden` 的签名**（去 `expect` 形参与其第三个断言）。删一段不能自然覆盖该动作，漏做即 `TypeError`。
      <!-- P64-S8-CLOSURE -->
      **本动作对 modifier 面已失效（S8 收口，2026-10-14）**：`test_pity_modifier.py` 已被 S8-1/2/3 整体改写为卡级显式期望值，其 15 条 golden 一并退役（见 §七 S7e 条的登记与裁决）。**删除点现只剩 tracker 面 4 条与 registry 面 1 条**（其消费者 `test_pity_tracker.py` / `test_pity_registry_schema.py` 未随 S8 改写），故本清单的「保留 golden 断言」在删除点的实际适用面须按 5 条重算。
    - **改指向模块级常量**：`tests/core/test_pity_config_toml.py` 的 `TestDuplicatedConstants` 两条（`:510` / `:516`）。**注意 §七 S1a 明写「不得删这两条断言」**（它们是防漂移守卫），而它们依赖的类属性恰在本 commit 消失，故**必须改指向 `pity_primitives` 的模块级常量**；`_SOFT_SUFFIX_TYPES` 在 `pity_primitives` **无对应物**（它仍是 `CounterBasedBehavior` 的类属性），其去向需一并裁决（迁为 `pity_primitives` 模块级常量，或随 `config_toml` 侧的那份拷贝一并处置）。
  - **已就地消解、不在本 commit 清单内的一项（ISSUE-909）**：原 `factor_override` 的 `exempt` 计算原同时展开 `scope_slots`，已改为只读 `scope_cards`（§3.9.4），本 commit 无需再改该函数。<!-- REVIEW-R1-FIX: ISSUE-909 --><!-- REVIEW-R1-FIX: ISSUE-502 -->

---

*设计评审记录：2026-08-23 用户裁决路线 B（代码组合）、soft 纳入、无完全声明式状态机、G16 独立先行。2026-08-23 独立审查 14 项修正（H1-H4/M1-M6/L1-L4）。2026-08-24 设计重建：Tracker+Modifier 双层纯函数架构（用户裁决命名），范围从事件驱动 6 类扩大到全部保底类型统一，G2 归 milestone 层修正。本计划未含 ISSUE 体系——待 plan-review 工作流审查后补充。*

---

## 自动化审查记录

<details>
<summary>第 1 次审查（上次）</summary>

- 复杂度: complex | 变更性质: breaking
- 阶段 1 影响面: 51 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 44 个

</details>

<details>
<summary>第 2 次审查（2026-09-30，Fixer 修复 8 项）</summary>

- 问题面：8 项（阻塞 3 / 高风险 1 / 中风险 3 / 低风险 1），全部为本轮独立复核新发现，均已在计划内定稿
- 阻塞项（**2026-10-06 更新**）：~~**ISSUE-401**~~（**已消解**：包装器取消，条件只在一处）、~~**ISSUE-902**~~（**已消解**：条件内联后读键落在 Modifier 自己的 `state_keys()` 里）。原记录：**ISSUE-401**（`ConditionalModifier.apply` 不判条件 → S12-2 至 S7 期间条件包装器全部退化为无条件）、**ISSUE-402**（骨架 `should_deactivate` 缺 `fired` 实参 → `triggers` 退化为「激活后的抽数」或 `TypeError`）、**ISSUE-403**（`pdef.target_featured` 在 preset 路径无承接 → hard 与三个 counter 驱动 soft 的目标集静默放宽）
- 非阻塞项（**2026-10-06 更新**）：~~**ISSUE-404**~~（**已消解**：门控取消，`_gated_ctx` 与池内污染断言一并删除）、**ISSUE-405**（`_validate_registry()` 口径写死为「导入期只判可调用」）、**ISSUE-406**（`depends_on` 属性由基类统一代理）、**ISSUE-407**（零件 `namespace` 声明面 + `NamespaceTracker` + `initialize(namespaces)` + `Pity._ns_views`/`_view_for`）、**ISSUE-408**（§四 的 `ForceNotOwnedModifier` 归属改回 `core/pity_modifier.py`）
- 落点：§3.1.1 / §3.1.2 / §3.1.3 / §3.1.4（骨架）/ §3.1.6 / §3.2 / §3.10.2 / §3.10.3 / §3.14.2 / §四 / §六 / §七（S1c / S1d / S4-2 / S4-3 / S5b / S9-2）（**2026-10-09：`/ S12-2` 随 S12 取消删除，ISSUE-004**）
- 改动方式：全部为**补内部一致性与接口落点**，未改动任何核心架构决策（双层纯函数、条件外置、M1/M2 划分、里程碑顺序、G3 双实现均保持原状）；每处修复均带 `<!-- REVIEW-R1-FIX: ISSUE-xxx -->` 标记

</details>

<details>
<summary>第 3 次审查（2026-10-01，Fixer 修复 3 项）</summary>

- 问题面：3 项（阻塞 1 / 中风险 2），均为独立复核新发现；2 项在计划内定稿，1 项取保守路径并保留备选待裁决
- **ISSUE-901（阻塞）**：S8-4 删 `PoolPitySpec` / `DrawInfo` 的 `scope_slots` / `featured_slots` / `card_to_slot` 与 ISSUE-502 的「旧类与 `_redistribute_scope` 保留至发布前」互斥——函数本体留下、它的输入被删，S5a harness 的旧实现对照基准与 S8-6 的「对 S5 产物容差 1e-12」双双落空。**取保守路径**：三字段、`compute_scope_mappings` 的槽位产出、`service/batch_simulator.py` 与 `worst_impact.py` 的构造点改造一并**推迟**到 GATE-5 末条「发布前一次性移除旧保底类」commit；S8-4 只删 `aggregate_probs_by_rarity` / `infer_rarity_from_spec` 及其导出面。经复核，`compute_scope_mappings` 的前两项**本就**是卡集合且已透传进 `DrawInfo`，S8 对卡级路径零改动、无「增量」可做（原稿「改造为只产卡集合」纯属减量）。备选路径（若坚持本步删字段，则 S8-6 基线改为固化 golden 快照）已用 `⚠ 待人工裁决` 标注保留
- **ISSUE-902（中风险）**：Condition 类族无 `state_keys()` 声明通道。§3.14 条件外置后读键者是 Condition 而非内层 Modifier，只转发内层的 `ConditionalModifier.state_keys()` 让 §3.12.2 判据第 2 条的比对集恒不含条件读键，条件键名拼错时构造期两条判据 / §3.13 checker / §六 负例**四道防线全部静默通过**。定稿：Condition 基类加 `state_keys()`（`Always` → `()`、`FlagCondition(flag)` → `(flag,)`、`CounterCondition(key, τ)` → `(key,)`、`FateReadyCondition(τ)` → `('fate_points',)`、`And`/`Or`/`Not` 取并集），`ConditionalModifier.state_keys()` 返回内层与条件的并集，S10-2 负例拆为 ②a（非法键 Modifier）/ ②b（非法键 Condition）
- **ISSUE-903（中风险）**：归一性口径被写成跨里程碑的绝对断言。§3.12.1 / §3.13 / §六 S10 三处的 scope 感知式（`Σp = 1 + Σp(被 F 豁免的更高稀有度槽位)`）只是 **M1 槽位管道**的性质；S8 起 `_apply_delta` 无条件归一化到 `Σp = 1`，同一判据会在 M2 对**合法配置**误报。定稿：三处标注适用范围，`core/invariants.py` 的分布层判据按里程碑两段实现，`core/invariants.py` 补进 §四 的 S8 波及行、S8-6 增验收项 ⑤（re-derive + 重跑 `test_pity_invariant_checker.py`）
- 落点：§3.1.2 / §3.1.6 / §3.9.3（组件处置表 + 跨文件同步清单新增 D 段）/ §3.12.1 / §3.12.2 / §3.13 / §3.14.2 / §四（原列 §3.14.6，该小节已随 2026-10-06 改判删除） / §六（S8 差异归因、跨文件同步、S10、S11）/ §七（S8-4 / S8-6 / S8-7 / S10-1 / S10-2）
- 改动方式：全部为**补内部一致性与接口落点**，未改动任何核心架构决策（双层纯函数、条件外置、M1/M2 划分、里程碑顺序、G3 双实现均保持原状）；每处修复均带 `<!-- REVIEW-R1-FIX: ISSUE-xxx -->` 标记

</details>

<details>
<summary>第 4 次审查（2026-10-01，Fixer 修复 11 项）</summary>

- 问题面：11 项（阻塞 4 / 高风险 3 / 中风险 3 / 低风险 1），均为 AGENTS 阶段 1 证据链与阶段 2 对抗循环的未响应残留；**全部在计划内定稿**（无 `⚠ 待人工裁决` 新增项）
- 阻塞 4 项：**ISSUE-904**（ISSUE-901 的改判未同步到四处「仍按 S8 删/改槽位字段施工」的位置——按任一处施工都会在 S8 提前删掉旧类依赖的输入，S5a harness 与 S8-6 基线同时失效）、**ISSUE-909**（§3.9.4 的 `factor_override` 仍读 `ctx.draw.scope_slots`，且该函数在模块归属表与 §四 零落点）、**ISSUE-910**（AUDIT-BREAK-1 的 dataclass 驱动改造与 `pentry` 的四个别名键互斥——照抄式子会让 `btype` 落回默认、软保底三段参数丢失）、**ISSUE-911**（GUI 五处枚举式透传未进任何清单，`priority` / ~~`reads`~~ / `max_triggers` 会经「GUI 加载→保存」静默丢失）
- 高风险 3 项：**ISSUE-905**（GATE-5 末条收口清单不含 ISSUE-901 任何一项，而全篇十余处都引它）、**ISSUE-908**（`_resolve_selected_slots` 旧稿残留句会改坏旧类的槽位语义与 S5a 基准）、**ISSUE-913**（`config/config.toml` 是 P79 常驻护栏的固定输入，增改会打断 `test_p79_stop_condition_baseline.py`）
- 中风险 3 项：**ISSUE-906**（S7d 的「失败时点②」与 S8-7 回滚说明仍按改判前因果描述）、**ISSUE-912**（H3 删分支后两条既有正断言与 GUI 的 `_PITY_TYPES` 写死计数必红，计划零登记）、**ISSUE-914**（`_ms_initial` 的推导在 `if env.milestone_defs:` 块内，且所引 `batch_simulator` 行号在今日 HEAD 上全部漂移）
- 低风险 1 项：**ISSUE-907**（§3.9.3 的 `tests/` 行未登记等价性装置这一例外消费方）
- 落点：§3.6（AUDIT-BREAK-1）/ §3.1.6 / §3.9.3（组件处置表 + 跨文件同步清单）/ §3.9.4 / §四 / §七（S6a / S7a / S7d / S8-5 / GATE-5 末条与回滚段）/ 首部历史行（新增第六轮条目 + `batch_simulator` 四处行号批量刷新）
- 改动方式：全部为**补内部一致性与事实修正**，未改动任何核心架构决策（双层纯函数、条件外置、M1/M2 划分、里程碑顺序、G3 双实现、ISSUE-901 的保守路径均保持原状）；每处修复均带 `<!-- REVIEW-R1-FIX: ISSUE-xxx -->` 标记

</details>

<details>
<summary>第 5 次审查（2026-10-01，Fixer 修复 10 项）</summary>

- 问题面：10 项（阻塞 1 / 中风险 5 / 低风险 4），为本轮独立复核新发现与上一轮未响应的 sub_item；**全部在计划内定稿**（无新增 `⚠ 待人工裁决` 项）
- 阻塞 1 项：**ISSUE-916**（sub_item）——§四 `service/batch_simulator.py` 行**行首句**仍把 `initial_counts` 并入「三处枚举式透传点」并指向 `:477-482`，与同行 S9 段「删除 `_ms_initial` 推导与 :486 实参」直接互斥，也与 §3.6 AUDIT-BREAK-1 的三处（`pentry` / `_PityDef` / `retreat_config`）不一致（`initial_counts` 是 `GachaState` 字段、不进 `PityDef` 透传面）。定稿：删去该并列项，明写「不属本行透传面」+「三处 = §3.6 #1–#3」<!-- REVIEW-R1-FIX: ISSUE-003 --> <!-- REVIEW-R1-FIX: ISSUE-953 -->
- 中风险 5 项：**ISSUE-920**（§七 S9-2 目标文件缺 `core/banner.py`（通道 A 的实际填充点），且 §六 / §3.10.2 / S9-4 三处验收引用**不存在**的 `-k sim` 用例——零匹配的 `-k` 以 exit code 5 假通过）、**ISSUE-921**（`core/strategy_context_builder.py` 零命中：`inter_pool_pity_links` 由恒空转非空且直读保底私有属性，登记为已知差异 + 未登记影响面）、**ISSUE-922**（`core/result_store.py` 的 `compute_config_hash` 读已不存在的 `PityDef.params`，新增的 `priority`（~~`reads`~~ 已取消）不进指纹 → 数据集可比性判定失真；本次范围为外，登记缺口）、**ISSUE-923**（S4b 只登记 `priority` 的**解析**、漏 `_pitydef_to_toml` **写回**，而验收要求 round-trip 保真；§四 也缺该行）、**ISSUE-924**（`tests/core/test_pity_rebind.py` 仍为条件式登记，实为「移除旧类」commit 的**必崩点**（模块级 import 4 个旧类），其 P75 三条语义不在 S7d 保留清单内）
- 低风险 4 项：**ISSUE-925**（「已批量补正」的声明不完整——§七 S4b 仍引 `batch_simulator.py:202`，应为 `:202`）、**ISSUE-926**（「`PityContext` 每池构造一次并复用」与实测不符且与 §3.1.4 骨架 docstring 自相矛盾，补第 4 处派生构造点 `:532`）、**ISSUE-927**（文档同步面只列 `01-理论` / `02-实施` 两件，目录实为六件，`00-档案` / `03-审计` / `04-问题` 同样失真）、**ISSUE-928**（G16 的「PityDef/config_toml 的 reset 枚举」在配置层无对应物；改为 `_build_pity` 的 `reset` 取值白名单，使「永不重置」与拼写错误可区分）
- 落点：§1.3（第 3 条缺口状态）/ §3.8（配套段）/ §3.10.2（构造点理由 2 与第 4 条、送达通道配套段）/ §四（`service/batch_simulator.py` 行首句、新增 `core/config_toml.py` S4b 行 / `core/strategy_context_builder.py` 行 / `core/result_store.py` 行 / 三件文档行、`01-理论` / `02-实施` 措辞）/ §六（通道 A 验收句、缺口与行为变化登记条）/ §七（S4b 施工项与验收、S7c 同步面、S7d 目标文件与保留语义、S9-2 目标文件、S9-4 验收命令、G16-1 / G16-2）
- 改动方式：全部为**补内部一致性、事实修正与落点补齐**，未改动任何核心架构决策（双层纯函数、条件外置、M1/M2 划分、里程碑顺序、G3 双实现、S8 不删槽位字段、`_ms_initial` 删除与「一处推导源 + 一处赋值点」均保持原状）；每处修复均带 `<!-- REVIEW-R1-FIX: ISSUE-xxx -->` 标记

</details>

<details>
<summary>第 6 次审查（2026-10-01，6 轮对抗循环熔断记录，存档）</summary>

- 复杂度: complex | 变更性质: breaking
- 阶段 2 对抗循环: 6 轮，熔断（Finder → Fixer → Verifier 迭代 6 轮后未满足收敛条件，曾使计划处于「不可自动合并」标记态，需人工裁决）
- 未解决问题: 1 个 —— **ISSUE-926**（维度：事实验证），两个子项：
  1. 计划 :1444（**2026-10-09 核对：该行号已失效（:1444 为空白行），所述正文亦已随本轮改写而不在该处**，本条按历史记录保留）把第四处派生 `PityContext` 构造（`pity.py:530`）归因为「`_redistribute_scope` 的派生副本」——实测该 fork 位于 `SoftPityMixin.before_draw`（`pity.py:529-533`），而 `_redistribute_scope`（`pity.py:416-441`）是「入参带 ctx、返回 `Dict[str, float]`」的纯重分配函数，**全篇不构造 `PityContext`**（实测构造点 4 处：`:530` / `:1272` / `:1301` / `:1333`） <!-- REVIEW-R1-FIX: ISSUE-951 -->
  2. 计划 :5（2026-09-30 第四轮条目④）残留「禁止就地改写**每池共享的 ctx**」，与已更正的「每次调用构造一次、在同池全部保底之间复用」口径互斥（全篇「每池共享」仅此一处）
- 处置（2026-10-01，Fixer）：两子项均已在正文修复——:1444 归因改为 `SoftPityMixin.before_draw` 的派生副本并注明 `_redistribute_scope` 全篇不构造 `PityContext`；:5 改为「本调用内的共享 ctx（每次调用构造一个，在同池全部保底之间复用）」。§3.1.4 的 `_gated_ctx` docstring（:589）与之一致
- 结论：阻塞解除

</details>

<details>
<summary>第 7 次审查（2026-10-01，GATE 四项门控复核）</summary>

- 问题面：4 项（均为可行性门控维度：文件清单 / 依赖顺序 / 风险缓解 / 测试策略），全部为本轮独立复核新发现；**4 项已在计划内定稿**（无 `⚠ 待人工裁决` 新增项）
- **GATE-2 文件清单（ISSUE-929）**：六处把「`_PITY_TYPES` 已改为由 `BEHAVIOR_REGISTRY` 生成（2026-09-28 改造）」当作既成事实，实测为假（代码从未改动）——改判为「待改造 + 落点 S6a」并写明三项代码改动；同轮更正 `core/config_toml.py` 的四处失效锚点并全量复核
- **GATE-3 依赖顺序（ISSUE-930）**：S4-1 的验收（10 条目通过 preset 可调用性判定）在其位置不可达——preset 工厂由 S4-2 / S4-3 创建，而 `_validate_registry()` 在导入期调用，按字面施工即导入失败。定稿「过渡判据 + 条目原子迁移 + S4-3 收口」，验收随之下移/上收
- **GATE-4 风险缓解（ISSUE-926）**：文末「⚠ 自动化审查阻塞项」自带的 6 轮熔断标记与两个子项（`:1444` 的归因措辞、`:5` 的「每池共享」残留）——两子项修复后清空该章节，熔断历史移入第 6 次审查 details
- **GATE-6 测试策略（ISSUE-931）**：S8-1 至 S8-5、S9-1、S9-3 七个条目只有目标文件与预算、无块级验收命令，与 GATE-5 的「回滚单元 = 子项 + 低层块回退后重跑受影响块命令」冲突；逐条补块级最小验收命令，S7a 的 `rotating_inverse` 断言改为带前提的形态
- 落点：§3.6 / §3.2 / §四 / §六 / §七（S4-1 / S4-2 / S4-3 / S6a / S7a / S8-1 至 S8-5 / S9-1 / S9-3 / GATE-5）/ 首部变更日志 / 文末「自动化审查阻塞项」
- 改动方式：**补内部一致性、事实修正与落点补齐**，未改动任何核心架构决策（双层纯函数、条件外置、M1/M2 划分、里程碑顺序、G3 双实现、S8 不删槽位字段均保持原状）；每处修复均带 `<!-- REVIEW-R1-FIX: ISSUE-xxx -->` 标记

</details>

<details>
<summary>第 8 次审查（2026-10-01，Fixer 修复 1 项）</summary>

- 问题面：1 项（维度：可行性门控 GATE-6-测试策略），为本轮独立复核新发现；**已在本轮内全部定稿**（无 `⚠ 待人工裁决` 新增项）
- **GATE-6-测试策略**：L1 成立（45 个子块均有验收方式，M2 的 10 个子项已补齐预算 + 目标文件 + 命令），L2 的断言具体性与边界覆盖抽检合格（N1 / M4 / H4 / S10-2 三类构造期负例 / S11 正例与负例三要素 / S8-5 五类边界）；失效面集中在「验收命令与其断言对象未绑定」，两种形态均已实测：① **假通过**：S8-5 的 `pytest -q tests/core/test_worst_impact.py -k "scope_cards or boundary"` 当前**零命中**（11 deselected，pytest **exit code 5**；**2026-10-09 订正：实测为 16 deselected**），而计划只在 S9-4 处写了「确认收集到 ≥1 条」的同款守卫；② **跑了但不测新物**：S8-3 的 `pytest -q tests/core/test_pity_rotating.py -k redistribute` 只命中 `TestRedistributeScope` 的 3 条**既有**用例（靠类名子串命中，实测 3 passed / 17 deselected、退出码 0），这 3 条只调用旧 `_redistribute_scope`，本步要验的 `factor_redistribute` 不在其内；③ **同类风险面**：S10-2 的 `-k "illegal or cycle"` 在新增文件上运行而用例命名未约束（S4-5 的 `-k engine_construct` 因已写死用例名而命中无疑，无需改动）
- 处置：§七 引言新增「**验收命令与断言对象绑定纪律**」三条（①计划内写死用例名或写明命名约束；②落地时确认收集 ≥1 条，零命中时 `exit code 5` 会被误读为通过；③命中项不得全为既有用例，否则为「全绿 + 新物零覆盖」的假验收），并把 S4-5 记为合规范例。逐处修复：S8-5 补两类用例命名约束（`scope_cards` / `boundary`）+ 收集守卫；S8-3 过滤词由 `redistribute` 改为 `factor_redistribute`（原词命中 3 条既有旧函数用例），补命名约束与收集守卫，目标文件补 `tests/core/test_pity_rotating.py`；S10-2 写死四条负例用例名 + 收集守卫；S5c / S8-6 / S9-1 / S9-3 四处补同款收集守卫
- 落点：§七（引言新增绑定纪律段；S5c / S8-3 / S8-5 / S8-6 / S10-2 / S9-1 / S9-3 的验收命令）/ 首部变更日志（第九轮条目）
- 改动方式：**只动「验收命令与其断言对象」的绑定关系与新增 `tests/core/test_pity_rotating.py` 这一测试目标文件**，未改动任何核心架构决策（双层纯函数、条件外置、M1/M2 划分、里程碑顺序、G3 双实现、S8 不删槽位字段、各子块的预算与实现目标文件均保持原状）；每处修复均带 `<!-- REVIEW-R1-FIX: GATE-6-测试策略 -->` 标记

</details>

<details>
<summary>第 9 次审查（2026-09-30）——P38 工作流自动化</summary>

- 复杂度: complex | 变更性质: breaking
- 阶段 1 影响面: 77 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 43 个

</details>

<details>
<summary>第 10 次审查（2026-10-09，GATE-check 四项门控复核，Fixer 修复 4 项）</summary>

- 问题面：4 项（全部为**可行性门控**维度：变更粒度 / 文件清单 / 依赖顺序 / 测试策略），均为本轮独立复核新发现；**4 项已在计划内定稿**（无 `⚠ 待人工裁决` 新增项）
- **GATE-1 变更粒度（GATE-check-1）**：L2（描述模糊）不成立——各块均有实现点、目标文件、约束与验收命令。未达标面在**预算**：G16-1 / G16-2 原只有组标题的「~1 人时」、P82-1 / P82-2 连组级预算都没有，而 §七 自定的方法恰是「逐块预算直接求和」，故 23.3（16.6 + 6.7）实为**不含这 4 块**的缺口值，P82-2 的实作面（新建脚本 + 两组快照 + 逐字段对照 + 差异归因到五类敏感集合）无预算即无从判定是否 ≤1h。处置：四块各补块级预算（0.6 / 0.4 / 0.3 / 0.8 = 2.1 人时），并在「计数与预算的核定方法」与「M2 子块预算」两处写入**全量预算口径**（独立先行 2.1 + M1 16.6 + M2 6.7 = 44 块 / 25.4 人时）
- **GATE-2 文件清单（GATE-check-2）**：L1（每步标注文件 + 函数）成立（40 个活跃块逐块有目标文件与符号名），L2（抽样核验一致性）超额完成（10 个文件逐锚点比对全一致；markdown 行号链接机核 410 条、纯空白行 0 处、越界 0 处）。未达标面一处：§3.1.6（标「强制」）仍把 `core/pity_condition.py` 列为实现层三模块之一、编排层仍写「依赖三个实现层模块」，而 §四 与 §3.14 已判该模块不新增；S1a–S2a 各块均不产出它，**无任何任务块承接该矛盾**。处置：§3.1.6 改两模块（正文 + 实现层表格行 + 编排层依赖列），§四 `02-实施.md` 行的「四模块」同批改三
- **GATE-3 依赖顺序（GATE-check-3）**：L1（步骤依赖无环）不成立一处——**S7b 的验收要求「加一条 `InvariantChecker` 的 round-trip」，而该类的产出者是排在其后 5 位的 S11**；反向亦有反指（S11 写「S7b 的 round-trip 覆盖已含 InvariantChecker」）。按字面施工，S7b 落地即 `ImportError`（pytest 收集期红），而 S11 所引的覆盖在其位置上不可能存在；与第 7 次审查修掉的 ISSUE-930（S4-1 的验收在其位置不可达）属**同一失败形态的复现**。处置：取**方案 ①**（保守，不动强制顺序串与 GATE-5 回退闭包）——该 round-trip 移入 S11 的专属文件 `tests/core/test_pity_invariant_checker.py`，S7b 只保留四族；§3.13 / §七 S11 的反指改为「本块自带」。L2 其余部分成立（S1a 的三类型集合与 `_BTYPE_ORDER` 被 S1d / S2a / S6a 消费、S1d 的 `build_lifecycle` 被 S4-2 / S4-3 消费、S4-1 的 registry schema 被 S4-2 / S4-3 按名取键消费、S8-1 的 `compute_delta` 签名被 S8-2 / S8-3 / S9-1 沿用）
- **GATE-6 测试策略（GATE-check-6）**：L1（每步有验收方式）成立，L2 的输入/期望值/边界覆盖大体成立（用例名写死、期望值写死、收集守卫、五类边界）。未达标面一处指向**已删除符号**：S10-2 的验收把 ②b `test_illegal_unknown_key_in_condition` 写死并称其为 ISSUE-902 的关键用例，而同批又要求「收集到 ≥4 条」——该用例的断言对象（Condition 类族 + `ConditionalModifier`）已随 §3.14 整块取消，实施者无对象可写，而守卫会逼其造出第 4 条（**不是假通过，而是逼出假用例**）。处置：删 ②b 与 ≥4 条守卫（改 ≥3 条，三条用例名写死），并把同族残留**六处**（§1.2 G13 行 / §3.10.4 条件极性 / §3.12.1 状态键合法 / §3.12.2 判据二 / §3.13 状态层 / §四 pickle 约束段）的 `Condition` / `ConditionalModifier` / `CounterCondition` 指向改为现行**内联**形态（§3.14.2 的「一处声明」口径）
- 落点：§1.2 / §3.1.6 / §3.10.4 / §3.12.1 / §3.12.2 / §3.13 / §四（`02-实施.md` 行 + pickle 约束段）/ §六（pickle round-trip 行）/ §七（独立先行块组标题与 G16-1 / G16-2 / P82-1 / P82-2；S7b 正文与验收命令；S10-2 验收命令；S11 块首与验收命令；「计数与预算的核定方法」与「M2 子块预算」行）/ 首部变更日志
- 改动方式：全部为**补内部一致性与依赖序可达性**，未改动任何核心架构决策（双层纯函数、条件内联、M1/M2 划分、里程碑顺序与强制顺序串、G3 双实现、S8 不删槽位字段、各块的实作范围与既有预算均保持原状——新增的只是 4 个独立先行块的预算与一条全量求和口径）；每处修复均带 `<!-- REVIEW-R1-FIX: GATE-check-N-xxx -->` 标记

</details>

<details>
<summary>第 11 次审查（2026-10-09，P38 工作流自动化 代码审计维度，Fixer 修复 10 项）</summary>

- 问题面：10 项（维度：**代码审计**；均为「断裂点 + 失败形态 + 计划内是否有对冲」三件套的复核结果），全部为本轮独立复核新发现；**全部在计划内定稿**（无新增 `⚠ 待人工裁决` 项）
- **编号提示（本轮特有，须先读）**：本节的 `AUDIT-BREAK-N` 是**本轮**审计工具生成的编号，与首部变更日志、§3.1.4 / §3.6 / §七 中既有的 `<!-- REVIEW-FIX-PREV: AUDIT-BREAK-N -->`（上一轮代号）**编号相同但所指不同**（例：既有的 AUDIT-BREAK-1 指「dataclass 驱动 vs `pentry` 别名键」，本轮的 AUDIT-BREAK-1 是它的**残余面**「改名前提只写在 §3.6、S4b 块内未复述」；既有的 AUDIT-BREAK-2 / 3 指 preset 构造形态，本轮的两条分别指 GUI 兜底条目与基类 `apply` 的 M1 形态）。本轮修复的标记一律为 `<!-- REVIEW-R1-FIX: AUDIT-BREAK-N -->`（**无 `PREV`**），可据此区分轮次
- **7 条改正文（逐条）**：
  1. **AUDIT-BREAK-1（别名键改名前提只写在别处）**：S4b 的「三处改造为 dataclass 驱动」在 §3.6 ISSUE-910 段有完整的改名前提，但 S4b 条目本身只以「见 §3.6 AUDIT-BREAK-1 条」指向——施工者只读块内文字即按字面照抄 `{f.name: getattr(pd, f.name)}`，而读端仍找 `'type'`，`btype` 落回默认 `soft_interval`、软保底三段参数整体丢失，**配置层无异常**。定稿：在 S4b 条目内**复述**该前提（四个别名键写读两端同 commit 改名、其余字段已是字段名口径、键集断言在别名制下恒红、GUI 侧同批归 S7a），并保留指向 §3.6 的交叉引用<!-- REVIEW-R1-FIX: AUDIT-BREAK-1 -->
  2. **AUDIT-BREAK-2（G16-1 被当成可选先行块）**：S4-5 把 `PityEngine.__init__` 的构造兜底改为抛 `ConfigError`，而**现存**的构造失败项就是 GUI 兜底保底条目（[config_panel.py:6544-6547](gacha_simulator/gui/config_panel.py#L6544-L6547)：`type='soft'` 不在 `BEHAVIOR_REGISTRY` 内、`reset='any_ssr'` 不在 G16-1 白名单、嵌套 `params` 会被 S4c 的未知键硬拒），它当前正被该兜底吞掉；修复原本只写在独立先行块 G16-1，而 4 个独立先行块的原措辞是「不属里程碑，可先于 M1 完成」（**非强制前置**）、M1 的强制顺序串也不含它们，故按顺序串单独施工时 S4-5（与 S4c）是必红项，且 S4-5 的验收是一条新增单测、覆盖不到 GUI 路径。定稿：**G16-1 升为 S4-5 与 S4c 的强制前置**，写进 M1 顺序行、独立先行块组标题与 G16-1 / S4-5 条目；S4-5 验收追加 GUI 路径一条（`set_config` 无保底段 → `get_config` → `load_toml` → `_build_pity_engine_from_gui` 不抛）<!-- REVIEW-R1-FIX: AUDIT-BREAK-2 -->
  3. **AUDIT-BREAK-3（基类 `apply` 默认实现的 M1 期形态缺失）**：上一轮 GATE-3 已就此判 `NEEDS_CLARIFY` 并给出二选一建议，本轮工作树核对显示正文未采纳任何一支——S2a-1 要交付的基类 `apply` 默认实现，其规格体（`_apply_delta(dist, self.compute_delta(...) or {})`）依赖 **S8-1 的 `_apply_delta`** 与 **S8 起才存在的 `compute_delta`**，M1 期照抄即 `NameError`，验收 ① 也没有可执行断言对象；且 §3.9.2 的「S1 至 S5 期间本节内容全部不实施」与「该默认实现要在 S2a-1 落地并单测」直接互斥。定稿：**M1 期基类只写占位实现 `raise NotImplementedError`**（各具体 Modifier 自实现 `apply`，M1 期该占位无消费者），S8-1 把它替换为正式默认实现；§3.9.2 的过渡期纪律加**唯一例外**括注、§3.14.3 的 `apply` 条改写为**两期形态**、S2a-1 的交付形态与验收 ① 同步改写<!-- REVIEW-R1-FIX: AUDIT-BREAK-3 -->
  4. **AUDIT-BREAK-4（S8-2 的 `pool.py` 行号错值）**：S8-2 写 `pool.py` 的内部调用在 `:270/:275`，实测两处 `infer_rarity_from_spec` 消费在 `:280` 与 `:285`（`:270` 是 `if pity_spec and pity_spec.scope_cards:`、`:275` 为空行），同篇 §3.9.3 表第 3 行写的是 `:280、:285`（本日已订正）。定稿：S8-2 的 `:270/:275` 改为 `:280` / `:285` 并注明「原值偏 10 行且落在非空白行，故计划的空行机核抓不到」<!-- REVIEW-R1-FIX: AUDIT-BREAK-4 -->
  5. **AUDIT-BREAK-9（S9-2 的清单与验收互斥 + `clone` 漏项）**：S9-2 的目标文件把 `service/batch_simulator.py` 划掉并注「字段取消后无改造量」，而 §六 ISSUE-916 ② 与 §四 该文件行都要求本步删除 `:477-482` 的 `_ms_initial` 推导与 `:486` 的 `initial_counts=_ms_initial` 实参（`register_milestone_engine` 的**全库唯一调用点**即在 `:483-487`，`core/milestone.py` 改为从 state 取后该处立即 `TypeError`，仅在有里程碑定义的配置上触发故只跑默认配置会静默漏过）；同条文字也未提 `GachaState.clone`（`state.py:89-97` 逐字段显式拷贝），漏改则新字段不被 clone 带上（`initial_counts` 恒空、`total_holding` 少算初始持有、P63 溢出分档静默出错）。定稿：`service/batch_simulator.py` 从删除面移回本步目标文件并写明两处删除点与调用点实参同步，「本步现行内容」补第 ④ 件，`core/state.py` 行补 `clone()` 保真<!-- REVIEW-R1-FIX: AUDIT-BREAK-9 -->
  6. **AUDIT-BREAK-10（S1a 的两条必红断言无任何子块承接）**：S1a 改动三个类型集合常量的存放位置、并给 `_EVENT_DRIVEN_TYPES` 追加 `rotating_inverse`，而 `tests/core/test_pity_config_toml.py:470-487` 的 `TestDuplicatedConstants` 断言 `config_toml` 的同名拷贝与 `CounterBasedBehavior` 的两个类属性相等——删类属性即 `AttributeError`，留别名而不同步拷贝即等值断言失败；而 S1a 的目标文件不含 `config_toml.py`、验收命令也不含该文件（实测 `tests/test_pity.py` 无该用例，全库仅上述文件命中），故 commit 一落地即红而验收看不出，缺口要到 S7c 的全量 `pytest` 才暴露（相隔约 20 块、H9 会拦推）。定稿：S1a 目标文件补 `core/config_toml.py` + `tests/core/test_pity_config_toml.py`；写明两条（**类属性保留为模块级常量的同对象别名**、**同一 commit 给 `config_toml` 的同名拷贝补 `rotating_inverse`**），并明确**不得删这两条断言、也不得改成「剔除 `rotating_inverse` 后相等」**（两种做法都让这份防漂移守卫失去检测力）；验收命令补该文件的两条断言<!-- REVIEW-R1-FIX: AUDIT-BREAK-10 -->
- **3 条登记为「无需改动」（本条只记录复核结论，不改正文）**：
  7. **AUDIT-BREAK-5（namespace 静默落回默认 view）**：为**已对冲**——S8-1 已含「必须有一条 `namespace` 非 `None` 的 Modifier 用例」、§3.10.3 的 `StateView` 收紧已配正负例两条，落点存在；该静默退化面在设计上是验收盲区（只在声明命名空间的零件上显形），计划已按此对冲，无新增改动<!-- REVIEW-R1-FIX: AUDIT-BREAK-5 -->
  8. **AUDIT-BREAK-6（通道 B 的独立验收）**：为**已对冲**——S9-2 目标文件已含 `core/banner.py`（通道 A）与 `core/strategy.py`（通道 B）两个填充点，S9-4 已配 `-k channel_b` 的独立验收（容差 1e-12 且非退化恒等）。本轮工作树核对确认计划自陈与代码一致：`strategy.py:178` 是 `PityEngine.get_probabilities` 的**全库唯一外部调用点**（其余命中皆在测试内直构 engine），通道 B 的真实消费方只有 `strategies/builtin/pity_reserve.py:52`；通道 A 的调用点亦唯一（`banner.py:228`）<!-- REVIEW-R1-FIX: AUDIT-BREAK-6 -->
  9. **AUDIT-BREAK-7（定轨识别的四处 + 端到端用例）**：为**已对冲**——S6c 已按上一轮把目标面写成四处（`:253` 函数局部 import / `:275` isinstance / `:292` 与 `:294` 写 `selected_card`）并追加「策略返回 `NonDrawAction` 的端到端用例」；本轮工作树核对确认四处的行号与形态与计划一致（`:253` / `:275` / `:292` / `:294` 实测落位）<!-- REVIEW-R1-FIX: AUDIT-BREAK-7 -->
  10. **AUDIT-BREAK-8（GUI 编辑路径）**：五处 + 两处消费面**均已登记**（S7a 的五处改造、`_do_update_preview` 与 `tests/gui/test_config_panel_pity.py:220` 的同批改写），与本轮第 2 条同源（根因都是 GUI 兜底保底条目）——第 2 条把 G16-1 升为强制前置后，本条无独立改动面，登记为**同源、不重复计入**<!-- REVIEW-R1-FIX: AUDIT-BREAK-8 -->
- 落点：§3.9.2（过渡期纪律的唯一例外括注）/ §3.14.3（`apply` 两期形态）/ §七（引言「M1 内部执行顺序」行 + 独立先行块组标题 + G16-1 + S1a（三处）+ S2a-1（两处）+ S4b + S4-5 + S8-2 + S9-2（三处））
- 改动方式：全部为**补内部一致性、依赖序可达性与事实修正**，未改动任何核心架构决策（双层纯函数、条件内联、M1/M2 划分、里程碑划分与强制顺序串、G3 双实现、S8 不删槽位字段、`_redistribute_scope` 本体保留至发布前、S9-2 的 SimView 三件事、`_EVENT_DRIVEN_TYPES` 追加 `rotating_inverse` 均保持原状；本轮只是**追加**一条强制依赖（G16-1）、给 M1 期补一个占位实现形态、把两处清单/行号改准）；每处修复均带 `<!-- REVIEW-R1-FIX: AUDIT-BREAK-N -->` 标记
- **本轮机械项（行号等纯机械工作，随本轮一并核）**：正文新增 **3 行**（独立先行块组标题下的例外块 + S1a 的类型集合条目），插入点分别在旧第 2589 行之后（+2）与旧第 2632 行之后（+1）；本轮**未改动任何 markdown 行号锚点**（无锚点被删或改指），但上述插入使**指向本计划自身**的既有行号引用发生 +2 / +3 漂移，受影响的引用已按实测回写（见下方「引用核对记录」的**第六轮补记**）；`#L` 锚点的提取数、空行判定与越界判定同批复跑，结果同见该补记
- 结论：10 项全部收口（7 改正文 + 3 登记无需改动），无遗留；门控 `文件清单` / `依赖顺序` 两项的 `NEEDS_CLARIFY` 与第 10 次审查的处置各自独立，本轮不改变其判定

</details>

<details>
<summary>第 12 次审查（2026-10-09）——P38 工作流自动化</summary>

- 复杂度: complex | 变更性质: breaking
- 阶段 1 影响面: 68 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 72 个

</details>

<details>
<summary>G16-1 实现审查（2026-10-10，独立审查，Fixer 修复 6 项）</summary>

- **审查对象**：本条的审查对象**不是计划正文**，而是块 G16-1 的**实现产物**（commit `707cbbf`：`core/pity.py` 的 `never` 分支 / `core/config_toml.py` 的 reset 白名单 / `gui/config_panel.py` 的 reset 控件与兜底条目 / `tests/gui/test_config_panel_pity.py` 的 5 条回归用例）。6 项发现全部属「实现与验收口径不符」类，无设计层问题
- **问题面**：6 项（**重要 1 / 轻微 5**，阻塞 0）
- **修复 4 项**：
  1. **（重要）「引擎可构造」验收只在内存态成立，保存一次即失效**。根因在 `_pitydef_to_toml` 的 soft_interval / soft_additive 分支以 `_sugar_matches_deltas()` 为唯一闸门，而后者对 `p.deltas is None` 恒返回 False——**GUI 内部构造的 `PityDef` 的 `deltas` 恒为 None**（`deltas` 只由 TOML 解析期的 `_expand_soft_to_deltas()` 产生，GUI 侧 `apply_to_store` 只填 `soft_start` / `soft_end`），故 start / end 一个都不写回。实测链路：`set_config({'pity': {'pities': []}})` → `get_config` → `save_toml` → `load_toml`，重载条目 `soft_start` / `soft_end` 双双为 None、`deltas` 为 None，`create_behavior` 抛 TypeError（`SoftStepBehavior` 缺 `deltas` 实参），`PityEngine.__init__` 的 `try / except` 记 `logger.warning` 后跳过（`behaviors == {}`），而 `load_toml` 本身不报错——**该验收项在载入侧因此为假**（原用例只在载入侧断言「名字还在」）。**该缺陷非本块引入**（与兜底条目无关的 GUI 新建保底 `pity_2` 同样保存后失效），但本块的验收项依赖它成立，且 §3.8 已写明「方案 a 下再断言 `PityEngine` 构造成功」。**处置取方案 ①**（在 G16-1 的目标文件内放宽写回）：新增 `_write_sugar_form()`（[config_toml.py:1761-1782](gacha_simulator/core/config_toml.py#L1761-L1782)）——`soft_start` 非空且（`deltas is None` **或** 语法糖展开与 deltas 逐段相同）时写回语法糖，两个分支（soft_interval / soft_additive）共用；**同时把断言补到载入侧**（阈值活过往返 + `'ssr_soft' in engine.behaviors`）。牙齿已实测：还原写回侧后新增的载入侧用例必红（`assert (None, None) == (74, 90)`）
  2. **`reset` 白名单与自述的「与 scope 同层同形态」有两处不对称**：`scope` 先 `.lower()` 再校验而 `reset` 原样比较（同一份 TOML 里 `scope='SSR'` 合法、`reset='SSR'` 被拒）；`scope` 校验带 `if rarity_rank_map and` 守卫而 `reset` 没有。**处置**：`reset` 侧补大小写归一（与 `scope` 同形态）；空 map 一处**有意保留不对称**，并把可达性写进 `legal_reset_values()` 的 docstring——实测 `ConfigStore._parse_rarities()` 在缺 `[rarities]` 段时补默认三级（`[["SSR"], ["SR"], ["R"]]`），故 **TOML 路径下 `rarity_rank_map` 不可能为空**，空 map 只手构 `ConfigStore()`（字段默认 `{}`）或 `clear()` 之后可达，而两条路径都不经 `_build_pity`。保留不对称的收益：`reset='nevr'` 在任何配置下都被硬拒（与 `scope` 侧「缺 map 即整条跳过」的取舍不同，因为 `reset` 即使缺 map 也仍能校验前三类）
  3. **GUI reset 下拉与本白名单不同源、未知取值被静默改写**（新控件，本块引入）。原按硬编码 6 项取值、未知取值经 `_pity_reset_index()` 一律回落下标 0（「跟随稀有度」），此后该行任一次编辑触发的 flush（`_flush_pity_current_detail` / `_apply_pity_edit`）都会把它**静默改写成空串**。**处置**：`_pity_reset_choices()` 按 `store.rarity_rank` 补入未列出的稀有度名（取值与白名单同源），`_populate_reset_combo()` 对仍未列出的取值补「原样保留」项，`_pity_reset_value()` 改读 `currentData()`。实测：`reset='ur'`（白名单放行、基础表未列）与完全未列出的取值经 flush 与重选均原样保留；旧实现下两者都变成 `''`（已实测）
  4. **测试侧三处**：① `_RESET_WHITELIST` 原为白名单常量的**第二份拷贝**（`config_toml` 未导出该集合，白名单改动只能靠往返用例间接兜住）→ 改为调用新导出的 `legal_reset_values()`，并**现读磁盘上的 `config.toml`**（不取 `panel._store`：`set_config` 会先 `store.clear()` 清掉 `rarity_rank`，取面板的 store 会得到收缩后的白名单）；② §3.8 要求的断言对象是 `PityEngine`，实现却用内存态 `create_behavior` → 改为 `PityEngine` 并断言 `'ssr_soft' in engine.behaviors`（该路径的失败形态是 `logger.warning` 后跳过，「没抛异常」不构成证据）；③ 5 条新用例落在 §七 G16-2 的目标文件内属跨块触碰，已在 G16-2 条目内写明避让
- **接受并登记 1 项**：
  5. **`_flush_pity_current_detail` 的 `if self._refreshing: return` 守卫（计划外改动）复核接受**：机制为 `_refresh_from_store_impl()` 先重建 `_pity_defs`、再 `pity_list.clear()` 触发 `_on_pity_selected(-1)`，其首行 flush 把**上一条**的控件值写回新 `_pity_defs[row]`；与父提交版本对照实测：还原该守卫后 `set_config({'pity': {'pities': []}})` 的第 0 条由 `{soft_start: 74, target_featured: False, pools: ('*',)}` 被改写成 `{soft_start: 80, target_featured: True, pools: ()}`，§六 G16 的 74/90 与 start/end 断言即不成立。该守卫与本文件既有四处同类守卫（旧 6059 / 6066 / 6072 / 7166）同模式，落在本块目标文件内，**保留**
- **登记未处置 1 项（本块不修，理由与归属如下）**：
  6. 该守卫**只覆盖 pity 一处**：`_flush_banner_current_detail`（`config_panel.py:1256`）/ `_flush_milestone_current_detail`（`:2500`）/ `_flush_resource_detail`（`:5083`）/ `_flush_current_detail`（`:5506`，行号为 2026-10-10 实测）四个同构函数无此守卫，其 `_on_banner_selected`（`:1218`）/ `_on_card_selected`（`:5495`）同为「先 flush 再填充」，**疑似同一缺陷类残留**（仅代码路径核实，未实测触达）；`pity_scope_combo`（`:2102`）的取值亦仍为硬编码 `["ssr","sr","r"]`，与 scope 白名单不同源，属**继承模式**（非本块引入）。两条均已登记 [04-问题.md](docs/01-活跃/subsystems/保底系统/04-问题.md) 的「GUI 详情面板 flush 守卫缺口」
- **落点**：`core/config_toml.py`（新增 `_write_sugar_form()` / `legal_reset_values()`；`_build_pity` 的 reset 段补大小写归一）/ `gui/config_panel.py`（`_pity_reset_choices()` + `_populate_reset_combo()` 替换 `_pity_reset_index()`；`_pity_reset_value()` 改读 `currentData()`）/ `tests/gui/test_config_panel_pity.py`（`_reset_whitelist()` / `_engine_from_store()` 两个 helper + 两条载入侧断言 + 断言对象改 `PityEngine`）/ `03-审计.md`（异常 6 关闭 + 六条锚点重刷）/ 本文 §1.2 / §1.3 / §六 G16 / §七 G16-1 与 G16-2 / 本节对照表
- **改动方式**：全部为**补验收真实性、形式对称与静默数据丢失面**；reset 白名单的取值集合本身未变（仍为「空串 / `featured` / `never` / 稀有度名」），未改动任何核心架构决策
- **未随本块做（明确归属，防再次失联）**：**本文全篇行号锚点未刷新**（待核面与机核口径见上方第七轮补记；`pity.py` 143 + 10 条、`config_panel.py` 26 条、`config_toml.py` 17 条）。**归属**：单列收尾项，排在 **G16-2 之后**（G16-2 自身只含 3 个测试文件 + 手册，容量不足以承接）；做法沿用本文「引用核对记录」既定的机核流程（提取锚点 → 读目标行 → 判符号落位），**禁止无实测依据的整体平移**
- 结论：6 项全部收口（4 修复 + 1 接受并登记 + 1 登记遗留项），无新增 `⚠ 待人工裁决`

</details>

<details>
<summary>G16-2 实现审查（2026-10-10，独立审查，Fixer 修复 6 项 + 登记 1 项）</summary>

- **审查对象**：块 G16-2 的实现产物（commit `493611f`：`tests/core/test_pity_integration.py` 的 `TestNeverResetHardPity` / `tests/core/test_pity_config_toml.py` 的 `TestResetValueWhitelist` / `tests/gui/test_config_panel_pity.py` 的 `TestPityResetCombo` / 手册的 G16·G1·G5 缺口登记同步）。7 项发现（**重要 1 / 轻微 6**，阻塞 0）中 6 项属「文档口径与实测不符」与「测试固化待裁决语义」两类，无设计层问题
- **修复 6 项**：
  1. **（重要）手册把「出金不重置」与「每 N 抽一个白送金」并作一条 ✅**：§5.3 第 719 行在该行的 ✅ 之后原保留「等价于每 80 抽一个额外的『白送』保底金」，而该外推在本仓库内无第二信源、且与 `reset = "never"` 的实际行为互斥（实测：counter 单调增至 90、第 80 抽起每抽强制，见 §六 G16 第 1 条）。**处置**：删去该句，改写为「已覆盖半 + 残余缺口」两段并指向 §5.4 / §21；§5.4 幻塔缺口行与 §21 G16 行同步补「② 每 80 抽一个白送金 = 未实现 · 待裁决」，优先级列改「🟢 已覆盖（①）＋ 🟡 残余缺口（②，待裁决）」；游戏目录 §五行与 §5.3 示例的注释同步收窄。按「精确建模原则」，G16 的 ✅ 只对「出金不重置」半成立
  2. **测试把待裁决的语义固化成断言**（`test_never_reset_gold_at_79_keeps_80th_guaranteed`）：第 80 抽之后的 `assert counter == THRESHOLD` 写了两遍（仅报错文案不同），而「保底触发时归零」这一候选修法在该点的终值恰为 0，裁决一旦改向该用例必红。**处置**：两条重复断言一并撤下，改为注释写明「该终值有意不钉住」与两种候选语义的取值及理由（**未**改用「counter 非 0」——该断言在候选语义下同样为假，换汤不换药）
  3. **类 docstring 复述了未验证的判据半边**：原引「hard 保底出金不重置 counter，每 N 抽白送保底金」整条判据。**处置**：只引已钉住的两条（出金不重置 + 达阈值当抽被强制），并把「每 N 抽白送」半的缺口登记与「为何不钉第 80 抽终值」写进 docstring
  4. **模块级 `assert` 扩大失败面**：`tests/core/test_pity_config_toml.py` 的 `assert '["UR"]' in _TOML_EXTRA_RARITY` 落在 import 期（全测试树唯一一处模块级断言），`_BASE_TOML` 的 `[rarities]` 形态一变会让整文件在收集期 ERROR、连带掩盖其余 42 条用例的信号。**处置**：移入其唯一消费者 `test_reset_whitelist_tracks_rarity_ranks`（失败面与该用例一一对应）。**牙齿已实测**：把 `_TOML_EXTRA_RARITY` 强制回退为 `_BASE_TOML` 后，该文件 1 failed / 42 passed（改前同形态是整文件收集期 ERROR）
  5. **G1 在手册内跨节不一致**：§21 的 G1 行已改「🟡 P64 设计中（2026-10-10 登记，未实施）」，而 §5.4 幻塔缺口表的「隐藏连歪/连中机制」行仍为「🔴 高」且无 P64 登记（与被本块同步掉的 G16 属同类问题）。**处置**：§5.4 该行补 P64 登记与设计要点、优先级列改「🟡 P64 设计中（2026-10-10）」，与 §21 同口径
  6. **§七 G16-2 的手册同步清单与核实结论不符**：原写「（G16/G13/G2/G14/G15/G5；G19 已同步）」，而 §六 的核实与实测均为「实际需改 G16/G1/G5，其余已同步」（以父提交为基准只有 G1/G16/G5 三行带「待 P64」标记），且漏 G1。**处置**：按实测订正该清单
- **登记 1 项（不在本块处理，归属随 G16 残余缺口裁决一并定）**：
  7. **两处「能力演示面」缺失**：① 手册 §5.3 的配置转换示例体未含 `reset` 键（该节示例未使用刚宣告覆盖的能力）；② §四 登记的 `config/config.toml`「幻塔 `rotating_inverse` + G16 示例段」无块承接（实测该文件对 `never` / `rotating_inverse` 零命中）。**处置：两处均不随本块改体**——① 示例体应写该机制的**忠实映射**，而其取值形态（`reset = "never"` 是否足够、是否需另加「触发时归零」的取值）恰是 §六 G16 待裁决的那一项，先写等于把待裁决结论固化为文档；且该手册被全库行号型引用锚定，在 §5.3 插行会连带 §六/§七 的 15 处锚点（11 个不同行号）与 04-收件箱 5 份抽查记录的 35 处快照一起漂移。② 已在 §四 该行标注归属待定。**本块的替代动作**：给 §5.3 示例的注释加一句「本示例体未含该键，取值与残余缺口见 §5.4」（行内改写、行数不变），读者不会误以为该示例已是幻塔保底的完整配置
- **本轮未触碰**：手册 §5.3 的标题编号（「5.3 核心特点」与「5.3 配置转换」两个同号二级标题，与本次改动无关的既有笔误，未纳入本块）；`config/config.toml`（受 §四 ISSUE-913 的注释形态约束，归属待定）
- **结论**：6 项修复 + 1 项登记；G16 的 ✅ 口径已收窄为「出金不重置」半，新增 `⚠ 待人工裁决` 1 项（「每 N 抽白送金」半的实现形态），其余无遗留

</details>

### 引用核对记录（2026-10-09，第二轮）

> 本节记录本轮「全篇行号核对」的口径、结果与仍未核的面，供下次核对复用。它不是计划内容，不参与任何里程碑。
> **上一轮把本节整体删除，导致核对口径与已知局限一并消失、下一轮失去基线**，故本节按「已修 + 未核 + 局限」三段固定保留。

**核对对象**：本文全部 markdown 链接形式的行号引用（`[显示文本](路径#L行号)`），脚本全量提取共 **403 条**（`.py` 384 条 / `.md` 19 条；去重后 **248** 个「路径:起行:止行」组合，按「路径:起行」去重为 **237** 个）。另补核了**裸反引号形态**（`` `file.py:nnn` `` / `` `file.py:nnn-mmm` ``）的引用。跨文档引用未纳入完整核对，见「未核清单」。**提取口径与命令（可复现）**：正则 `r'\[([^\]]*)\]\(([^)\s#]+)#L(\d+)(?:-L(\d+))?\)'` 逐行 `finditer`，按 `(路径, 起行, 止行)` 与 `(路径, 起行)` 两种键去重（实测 248 / 237）。**注**：403 是**本轮开始时的提取数**；本轮订正过程中新增了 4 条交叉引用（`worst_impact.py` 的 `530-531` / `177-188` / `536-541`，以及 §七 S8-5 行的 `543-552`），故订正后的提取数为 407 条。 <!-- REVIEW-R1-FIX: ISSUE-957 -->

**第三轮机核补记（2026-10-09，脚本复跑）**：以同一正则复跑实测，提取数 **408 条**（`.py` 389 条 / `.md` 19 条），去重后 **248** 个「路径:起行:止行」/ 按「路径:起行」去重 **237** 个；**落在纯空白行的锚点 0 处、越界锚点 0 处**。据此订正上文两处：① 「订正后的提取数为 407 条」应为 **408 条**（「403 + 4」的推算未计入第 5 条净增；已逐条列出的新增仍为那 4 条）；② 括号内的「去重后 248 / 237」与订正后的 408 条口径吻合；若按字面当作 403 条时的值，则本轮新增的 4 个去重键（`530-531` / `177-188` / `536-541` / `543-552`）无从落位，故应读作订正后的值。
**第四轮机核补记（2026-10-09，本轮 GATE 修复后复跑）**：以同一正则复跑实测，提取数 **410 条**（`.py` 391 条 / `.md` 19 条），去重后 **249** 个「路径:起行:止行」/ 按「路径:起行」去重 **237** 个；**落在纯空白行的锚点 0 处、越界锚点 0 处**。与第三轮的 408 条（389 / 19，248 / 237）相比净增 **2** 条 `.py` 锚点、去重键 +1（增量来源未逐条归因，系第三轮之后各行号订正轮次的净增）；**本计划此后以 410 条为准**，第三轮的 408 条保留为其时点记录。<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->

**方法与结果**（口径 = 脚本提取锚点 → 读目标行原文 → 判「符号是否落位」）：

1. **落在空行的锚点（确定性必错，零人工判读）**：本轮开始时共 **20 处**，全部改正，复查后为 **0 处**。清单可作机核基线——凡锚点区间全为空白行即必错。
2. **反向核对上一轮的改动**：发现 **14 组**把上一提交（`b978e89`，其 message 自述「全篇行号核对修 54 处」）已核对正确的值改成了偏离更大的值，属**方向性错误而非遗漏**（`core/pity.py` 一律 +2、`core/pool.py` 一律 −2、`config_toml.py` 的 `_expand_soft_to_deltas`/`_pitydef_to_toml` 为 −8/−62，而三者的真实偏移均为 0）。本轮已把其中 **14 组**逐条回退到实测值（标记 `ISSUE-001`）。**2026-10-09 第二轮复核发现：`core/pity.py` 侧仍有残余 +2 未清**（`_redistribute_scope`：`418`→`416`；`_should_reset`：`200-203`→`205-208`；`create_behavior` 的三处参数注入：`877-880`→`873-878`；`_validate_behaviors` 区间：`933-985`→`931-982`；`_BTYPE_ORDER`：`908-914`→`906-911` 及其缺键消费点 `928`→`926`；`PityContext` 四个构造点：`532/1274/1303/1335`→`530/1272/1301/1333`；`_build_pity_state_init`：`1005-1011`/`1009-1010`→`1003-1004`/`1007-1008`），另有 `service/batch_simulator.py` 与 `core/worst_impact.py` 的同类残余（`pentry`：`1161-1186`→`1168-1193`；`GachaState(`：`501`→`508`；`PoolPitySpec` 构造点：`506-548`/`540-548`→`543-552`），均已在第二轮逐处订正，清单见下方「本轮实测对照表（残余项）」。故**不得再据本条推定全篇已回退完毕**。<!-- REVIEW-R1-FIX: ISSUE-951 --><!-- REVIEW-R1-FIX: ISSUE-957 -->
3. **`core/pity.py` 的系统性偏移（上一轮遗留，本轮首次修正，标记 `ISSUE-002`）**：`PityEngine` / `PityState` / `BEHAVIOR_REGISTRY` / `_validate_registry` / `create_behavior` / `_BTYPE_ORDER` / `compute_scope_mappings` / `_build_activation_graph` / `DrawInfo` 透传 / 卡集合前两项 / `_rebind_state` 守卫行 / `HardPityBehavior` 的 `threshold` 默认值等 12 组，按实测通行；同批另修同一文件内若干区间起止行。
4. **同批首次修正（非上一轮引入）**：`service/batch_simulator.py` 的 `_ms_initial` 段与 `GachaState(...)` 构造点、`core/config_toml.py` 的 `reset` 直取行 / `_deltas_to_soft_interval` / H3 拒绝分支、`core/pool.py` 的两处消费点、`core/worst_impact.py` 的 `_ref_pool` 论断、`core/strategy.py` 与 `core/strategy_context_builder.py` 各一处（标记 `ISSUE-003/005/006/009`）。
5. **方法纪律（下一轮必须遵守）**：**禁止无实测依据的整体平移**。每一处改动都必须落在「符号 → 实测行」的对照上；脚本化核对（提取锚点 → 读目标行 → 空行/符号判定）先行，人工只判脚本报出的疑似项。

**本轮已核（值为实测行）**：`core/pity.py`、`core/pool.py`、`core/config_toml.py`、`core/worst_impact.py`、`core/strategy.py`、`core/strategy_context_builder.py`、`service/batch_simulator.py`、`cli.py`、`scripts/p79_verify.py`、`tests/core/test_pity_config_toml.py` 的全部行号链接。

**未核清单（下一轮须处理）**：

- **裸反引号引用**（`` `pity.py:nnn` `` / `` `:nnn` `` 形态）：2026-10-09 第二轮已做机器提取（正则 ``[`\[]([\w/]+\.py):(\d+)(?:-(\d+))?[`\]]``）并逐条验目标行，结果见下方对照表；跨文件路径（`gui/` 等）的裸引用仍按本清单下一条处理。 <!-- REVIEW-R1-FIX: ISSUE-957 -->
- **跨文档引用**（如 `[手册:2419](docs/...)`）只验目标文件存在，未验其内部行号是否仍对。
- **`gui/` 与其余文件侧的密集区间引用**未逐条复核：`gui/config_panel.py`（5 处区间）、`gui/about_dialog.py`、`core/banner.py`、`core/config_store.py`、`core/__init__.py`、`core/milestone.py`、`service/gacha_service.py`、`core/retreat_config.py`、`core/state.py`、`core/process_trace.py`、`core/streaming.py`、`tests/` 其余文件：本轮只做了越界检查，未验符号落位。

**已知局限（下次核对应注意）**：

1. **无自动漂移检测**。`tools/refcheck/` 对本文零关系登记（其 `check` 输出为「关系 0 条」），本文的行号漂移不在任何自动门控内；`scripts/` 下亦无「锚点落在空行即报错」的一次性机核脚本。**建议**：把该机核做成提交前的一次性脚本（提取全部 `#Lnnn` → 读目标行 → 空行即报错），它已在本次核对中证明可零人工判读地抓出 20 处必错项。
2. **核对的判据是「符号是否落位」**，对「符号在附近但区间起止不精确」（差 1–4 行）不报警；读者仍能定位，故未逐条处理；上一轮自述的同一局限仍然成立。
3. **行号引用会持续漂移**。本文 403 条行号引用不会自动再生，代码每变一次就可能部分失效。**落盘对照要求**：把本轮「符号 → 实测行」的对照表固化为脚本产物（而非只写在正文里），下一轮只重跑脚本 + 人工判定新增项。 <!-- REVIEW-R1-FIX: ISSUE-957 -->
4. **源文件本身在变**：本轮核对以工作树（`HEAD` = 本轮会话时的 `pity.py` 等源码）为准；若源码随后被改动，本节结论随之部分失效；故本节记录的是**核对时点**的事实。

**本轮实测对照表（残余项；2026-10-09 第二轮，标记 `ISSUE-951` / `ISSUE-952` / `ISSUE-953` / `ISSUE-954` / `ISSUE-955` / `ISSUE-956` / `ISSUE-957`）**：下表是本轮复核时**仍指向错行**、并已逐处订正的锚点（左＝订正前值，右＝工作树实测值）。口径与上文一致：机核（markdown 链接全量提取 + 裸反引号提取，读目标行，空行/符号判定）先行，人工只判机核报出的疑似项。

| 符号 | 文件 | 订正前 | 实测 | 落点 |
|---|---|---|---|---|
| `_redistribute_scope` | `core/pity.py` | `418` | `420`（体至 445） | §3.1.6 / §七 末条 |
| `_should_reset` | `core/pity.py` | `200-203` | `205-212`（含 G16 的 `never` 分支） | §1.2 G16 行 / §3.1.1 |
| `create_behavior` 的参数注入 | `core/pity.py` | `877-878`（target_featured）、`879-880`（reset）、`875-876`（threshold） | `879-880`、`881-882`、`877-878` | §3.1.4 / §3.2 / §七 S4b |
| `_validate_behaviors` | `core/pity.py` | `933-985`、`931-985` | `935-986` | §3.1.3 / §3.9.2 / §3.12.2 / §七 |
| `_BTYPE_ORDER` / 其缺键消费点 | `core/pity.py` | `908-914` / `928` | `910-915` / `930` | §七 S7a |
| `_build_pity_state_init` | `core/pity.py` | `1005-1011` / `1009-1010` | `1007-1008`（`if cv:`）/ `1011-1012`（`guaranteed_init`） | §3.1.4 / §3.2 |
| `PityContext` 构造点 | `core/pity.py` | `532` / `1274` / `1303` / `1335` | `534` / `1276` / `1305` / `1337` | §七 第 6 次审查记录 |
| `_validate_registry()` 模块级调用 | `core/pity.py` | `834` | `836` | 首部变更日志 |
| `pentry` 块 | `service/batch_simulator.py` | `1161-1186` | `1168-1193`（**订正 2026-10-13**：原写「24 键 = 1169-1192」，S4b 起改 `dataclasses.fields(PityDef)` 驱动，键数随 `PityDef` 字段数，实测 26） | §3.6 / §四 / §七 S4b |
| `GachaState(...)` 构造点 | `service/batch_simulator.py` | `501` | `508` | §四 / §七 S9-2 |
| `_ms_initial` 推导块 | `service/batch_simulator.py` | `466-479` / `470-475` | `477-482`（块首 `if env.milestone_defs:` 在 473） | §四 / §七 S9-2 |
| `_PityDef(...)` 重建块 | `service/batch_simulator.py` | `218-243` | `218-243`（四者中唯一准确） | §3.6 / §七 S4b |
| `MPPool(...)` 块 / `run_batch_parallel` | `service/batch_simulator.py` | `866-869` / `721` | `873-876` / `728` | §四 pickle 段 |
| `PoolPitySpec(` 构造点 | `core/worst_impact.py` | `506-548` / `540-548` | `543-552` | §3.9.3 表 / 跨文件同步清单 B |
| 五元组解包点 | `core/worst_impact.py` | `506`（当作解包点） | `530-531` | §3.9.3 表 |
| `infer_rarity_from_spec` 消费点 | `core/pool.py` | `278` / `283` | `280` / `285` | §3.9.3 表 |
| `_build_pity()` 内 `PityDef(` 构造 | `core/config_toml.py` | `663` | `746`（函数定义在 643） | §七 S4b |

**第三轮补记（2026-10-09，GATE 修复轮；标记 `GATE-2-文件清单`）**：本轮另订正**两组此前未登记的 `+2` 残留**（形态与上表所列的「方向性错误」一致，上一轮的订正清单未覆盖它们）——① `_build_activation_graph` 内「无条件读 `lc.depends_on`」的锚点，全篇 **5 处**由 `pity.py#L1216` 改为 **`L1214-L1215`**（实测 1214 = `if lc and lc.depends_on:`、1215 = `dep = lc.depends_on`，而 1216 = `if dep not in all_names:`）；② `_redistribute_scope` 的 **4 处旧类调用点**，全篇 **6 处**由 `:477 / :589 / :655 / :659` 改为 **`:549 / :661 / :727 / :731`**（实测：定义 416、调用 475 / 587 / 653 / 657）。核对口径与上文一致（提取锚点 → 读目标行 → 判符号落位），并**按上文「方法纪律」第 5 条执行**：不作无实测依据的整体平移，每一处都落在「符号 → 实测行」的对照上。<!-- REVIEW-R1-FIX: GATE-2-文件清单 --><!-- REVIEW-R1-FIX: GATE-6-测试策略 -->

**第四轮补记（2026-10-09，GATE 复核第二批；标记 `GATE-FAIL-2-文件清单`）**：`core/result_store.py` 的 `compute_config_hash` 保底分支锚点由 `#L479-L482` 订正为 **`#L519-L522`**（实测 518 = `# 保底配置`、519 = `if pity_config and hasattr(pity_config, 'pities'):`、521 = `h.update(pd.name.encode())`、522 = `h.update(str(getattr(pd, 'params', {})).encode())`）。原值偏移约 **40 行**，落在 P79 的 docstring 上，**超出「已知局限」第 2 条自述的「区间起点差 1 至 4 行」容忍度**，故不属该局限的豁免面、按错行处理。落点：§四 `core/result_store.py` 行（ISSUE-922 的缺口登记处）。<!-- REVIEW-R1-FIX: GATE-FAIL-2-文件清单 -->
**第六轮补记（2026-10-09，第 11 次审查 Fixer 轮；标记 `AUDIT-BREAK-1` 至 `AUDIT-BREAK-10`）**：本轮按审计问题列表改动正文，**新增 markdown 行号锚点 18 条**（分布在 §七 引言 M1 顺序行 2 条 / 独立先行块组标题 1 条 / S1a 5 条 / S4b 2 条 / S4-5 1 条 / S9-2 6 条 / 审查记录 1 条），逐条为「符号 → 实测行」的顺向填写（`config_panel.py:6544-6547`、`pity.py:1162-1170`、`pity.py:140`、`pity.py:859`、`config_toml.py:686-691`、`config_toml.py:1684-1685`、`test_pity_config_toml.py:477-487`、`batch_simulator.py:1168-1193` / `:218-243` / `:477-482` / `:483-487` / `:486`、`state.py:89-97`），均已在工作树逐条读目标行确认落位（非空白行且语义相符）。**同批复跑机核（口径与本文件上方各轮一致）**：提取数 **428 条**（`.py` **409** 条 / `.md` 19 条），去重后 **256** 个「路径:起行:止行」/ 按「路径:起行」去重 **243** 个；**落在纯空白行的锚点 0 处、越界锚点 0 处、目标文件缺失 0 个**。与第五轮的 410 条（391 / 19，249 / 237）相比净增 **18** 条 `.py` 锚点、去重键 +7 / +6，增量与本轮新增逐条对应（无既有锚点被删或改指）。**本轮唯一未自动再生项**：正文新增 3 行使**指向本计划自身**的行号引用整体后移，已在「自动化审查阻塞项」的机械复校段按实测回写（2597→2599 / 2659→2662 / 2697→**2712** / 2805→2808（**2026-10-09 订正**：原写 `2697→2700`，实测 2700 是 S4-1 的 preset 构造形态条、2712 才是含 `S4b` / `max_triggers` / `rotating_inverse` 三处互指的条目；原表另列 `2709→2712` 一项，而本轮门控 JSON 实际未引 2709，该对齐无对应引文，已删）；插入点之前的引用与「照录原文」的 JSON 不动）。**未处理面**仍为上方「已知局限」第 2 条（符号在附近、区间起点差 1 至 4 行）与「未核清单」所列各项。<!-- REVIEW-R1-FIX: AUDIT-BREAK-10 -->

**第五轮补记（2026-10-09，GATE-2 机械项修复；标记 `GATE-2-文件清单`）**：本轮按复核清单订正 4 组纯机械项——① `core/pity.py#L856` **3 处**改为 **`#L854`**（实测 854 = `scope = (getattr(pdef, 'scope', None) or _default_scope).lower()`，856 为注释行）；② `pity.py:334-336` / `:410-412`（`deactivate_on_early_hit` 退役分支）改为 **`:332-335` / `:408-411`**；③ `_validate_registry()` 的 **`:817-834`** 改为 **`:815-829`（模块级调用 `:832`）**；④ `tests/core/test_pity_rebind.py:11-15` 改为 **`:10-13`**、`tests/gui/test_config_panel_p56.py` 的 `:45-50` 改为 **`:48-53`**（实测 48 = `class TestPityTypesP56:`、51 = `def test_pity_types_has_10_entries`，原区间不含该用例）。另：全篇 markdown 锚点提取数按上方第四轮机核补记订正为 **410 条**。<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->

**同批更正的事实性表述（非行号）**：`core/worst_impact.py` 的**硬编码槽位表**与「用参考池原始卡 id 生成卡集合」两种现状**均已不存在**（后者由 `e32577f`（2026-10-09）改为按池生成，并配构造期覆盖不变量 `worst_impact.py:536-541`），`_ref_pool` 属性与所述死分支在全库不存在；§3.9.3 组件处置表 A 行、跨文件同步清单 B 段与 ISSUE-006 专项开篇已按文件实际改写，并删去与 ISSUE-006 专项相斥的 `_ref_pool` 死分支说法。

**第七轮补记（2026-10-10，G16-1 落地 + 实现审查修复轮）**：`core/pity.py` 在 `_should_reset` 内新增 `never` 分支（+4 行，插入点在旧 206 行之后），**其后的全部 `pity.py` 锚点整体 +4**；`core/config_toml.py` 有三处插入——G16-1 的 reset 白名单 **+17**（插入点在旧 657 行之后）、本轮新增的 `legal_reset_values()` **+31**（插入点在旧 611 行之后）、本轮 `reset` 大小写归一段 **+5**（插入点在旧 665 行之后）——故其偏移**分段为 +17 / +31 / +36，不能整体平移**；`gui/config_panel.py` 为 **+3**（`_PITY_RESET_CHOICES` 注释）/ **+5**（旧 2109 行之后，reset 控件注释）/ **+33**（旧 3280 行之后，两个 helper 替换为 `_pity_reset_choices()` / `_populate_reset_combo()`）。上表「实测」列**已就地按本轮核对结果重刷**（`core/pity.py` 各行 +4；`config_toml.py` 行按上述偏移），「订正前」列保持上一轮原值不动。**本文其余锚点本轮未逐条刷新**（不在 G16-1 的施工面内，按 §七 的单列收尾项承接，见下方「G16-1 实现审查」条目的「未随本块做」段）。**待核面的机核口径（2026-10-10 实测）**：`pity.py` 锚点共 markdown **169** 条 + 裸引用 **12** 条，其中行号 **> 212** 者 **143 + 10** 条——它们就是 +4 偏移的**全部候选面**（本文对照表已就地订正的 8 条不在内）；`config_panel.py` 行号 > 2109 的 markdown 锚点 **26** 条（落在 +5 / +33 两段偏移上）；`config_toml.py` 行号 > 657 的 markdown 锚点 **17** 条（落在 +17 / +31 / +36 三段偏移上）。**注意判据强度**：以「落在空行 / 超长」为判据的机核对上述 181 条 `pity.py` 锚点只报出 22 条疑点——它对「整体平移」不敏感（平移后的行号照样落在某行代码上），故下一轮**不能依赖该判据**，必须逐条按符号落位核。

**本轮仍未处理（与「已知局限」第 2 条同口径）**：机核只判「锚点是否指向所声明的符号」，对「符号在附近、区间起点差 1 至 4 行」不报警，例如 `core/pity.py:306-323`（起点差 1 行，306 为空行）与 `:490-498`（起点差 1 行）、`core/pity.py:225-229`（`__init__` 签名区起点差 1 行）均按此保留；文件侧的裸引用（`cli.py`、`gui/config_panel.py` 等）与跨文档引用仍见上方「未核清单」。

<!-- REVIEW-R1-FIX: ISSUE-951 --><!-- REVIEW-R1-FIX: ISSUE-957 -->

<!-- REVIEW-R1-FIX: ISSUE-004 --> <!-- REVIEW-R1-FIX: ISSUE-946 --> <!-- REVIEW-R1-FIX: ISSUE-008 --> <!-- REVIEW-R1-FIX: ISSUE-726 --> <!-- REVIEW-R1-FIX: REG-R1 -->

## ⚠ 自动化审查阻塞项

> **本轮（2026-10-09，P38 工作流自动化）未解决问题：0 个，详情 `[]`。标注原因：6 轮对抗循环未收敛。**

- **未解决问题数**：**0**
- **详情**：`[]`
- **标注原因**：阶段 2 对抗循环在 6 轮上限内未满足收敛条件。**口径说明**：熔断判据是「连续 2 轮无新发现且无遗留」（`dryRounds >= 2`）在 `maxRounds` 内未成立，**不等价于存在未解决问题**；本轮 Verifier 未留下 FAIL / PARTIAL 残留，故清单为空。**本条不阻塞施工**：它表示自动化审查在轮次上限处收口，而不是本审查轮次内留下待裁决的问题。**口径补充（2026-10-09，GATE-4；枚举面同日按机核订正）**：「未解决问题 0 个」是**审查口径**（本轮 Verifier 无 FAIL / PARTIAL 残留），**不等于「决策全闭合」**——正文各节仍开放 **3 组** `⚠ 待人工裁决` 的决策备选（**2026-10-10 由 7 组缩减**，处置逐条见下），各条均自述「不阻塞施工」或「本计划已取保守路径、备选留待用户裁决」：① **AUDIT-BREAK-2** 备选（§3.1.4 定稿条 + 备选段 + §六 断言面，三处同组）；② **AUDIT-BREAK-3** 备选（§3.1.4 同构三处）；③ **ISSUE-901** 备选路径（§七 S8-4，标注在 HTML 注释内）。

**2026-10-10 移出本表的四组**：**ISSUE-702**（原第 ① 组，首抽掷骰缺口消除方向）——由 **RULING-6B′** 闭合（掷骰相位改归 `StreakTracker.prepare`，首抽不再缺失），差异归因 (c) 项随之作废；**ISSUE-002 另一支**（原第 ⑤ 组）——用户 2026-10-10 确认**维持 7B 的类型级硬拒**；**G16 方案 (a) / (b)**（原第 ⑥ 组）——用户 2026-10-10 确认**取 (a) 改写为全合法形态**；**ISSUE-730 / ISSUE-944**（原第 ⑦ 组，`StrategyContext.acquired` 的口径）——用户 2026-10-10 裁定**迁移到含初始持有的口径**（改选备选路径，见 §四 `core/strategy.py` 行；**落点为 §七 S9-5**，2026-10-10 新增的独立子块，~0.4 人时，M2 11 → 12 块）。**枚举纪律（本条自纠）**：原稿此处为人工列举（「4 组 + 两处同类」共 6 处），机核全篇实测得 **13 处**活标注、归并 **7 组**——漏列第 ⑦ 组，且第 ① 组的位置原记为 §1.3（实为 §3.1.1）。凡「共 N 处」的声明须附提取命令与机核输出，且该声明本身要被下一轮复核。**ISSUE-928（§3.1.1 三点声明第 3 条，`reset` 白名单是否归 P64 范围外）原亦在此列，已于 2026-10-09 裁决为「并入 G16-1」，不再计入本表。** **同轮另查证两处邻近判据、判为不纳入 S9-5**：① `TargetAcquiredCondition`（[stop_condition.py:61](gacha_simulator/core/stop_condition.py#L61)）经 `get_card_count()` 读 `state.acquired`，其语义是「本次模拟**获得** N 张」（`description()` 即「获得 N 张 X」），与被裁决的「是否已拥有」不同源；② `GachaService` 的循环快照指纹（[gacha_service.py:90](gacha_simulator/service/gacha_service.py#L90)）用 `state.acquired` 做差分检测（`initial_counts` 全场不变，不影响差分判定）。**2026-10-10 用户裁定：维持现状**——`TargetAcquiredCondition` 的语义即「**获得** N 张后停止」，不含初始持有，故**不存在第 ④ 组**；判据与理由见 §七 S9-5。<!-- REVIEW-R1-FIX: GATE-4-风险缓解 -->
- **本轮机械项复校（2026-10-09）**：markdown 链接锚点全量提取 **428 条**（`.py` 409 / `.md` 19；去重 256 / 243；**2026-10-10 第七轮机核为 446 条**（`.py` 425 / `.md` 21；目标文件缺失 0 / 越界 0），见下行订正），**落在纯空白行者 0 处、越界者 0 处**（**原记 410 系第四轮机核时的时点值**；第六轮新增 18 条锚点后为 428，见下方「引用核对记录」的**第六轮补记**），口径与脚本见上方「引用核对记录（2026-10-09）」的第三轮 / 第四轮机核补记；未处理面仍为「符号在附近、区间起点差 1 至 4 行」与「未核清单」所列各项。<!-- REVIEW-R1-FIX: GATE-2-文件清单 -->

- **门控硬上限（2026-10-09，P38 工作流自动化）**：累计 **6 轮**可行性门控未通过（上限 **6**）。机制：`.claude/workflows/plan-review.workflow.js` 的累积计数器 `gateTotalRuns` 与上限 `maxGateTotalRuns = 6`，到点直接写本条并 `break`，不再走「内层 3 次重试 / 退回阶段 2 空转」两条路径。非 PASS 项 **2 个**，均判 `NEEDS_CLARIFY`：**`文件清单`**（GATE-2）与 **`依赖顺序`**（GATE-3）；两项均为「L1 成立、L2 抽样核验通过，只留一处未达标面」的形态，各附 `clarify_suggestions`（可直接施工的补写建议）。6 项检查中其余 4 项（变更粒度 / 风险缓解 / 回滚路径 / 测试策略）判 PASS。明细照录如下。**本条不改变审查口径**：它是门控在轮次上限处收口，与上方「阶段 2 对抗循环 6 轮熔断」同属轮次上限机制，不等价于「存在未解决问题」（该项仍为 0 个，指本轮 Verifier 无 FAIL / PARTIAL 残留）。

```json
[{"id":"文件清单","verdict":"NEEDS_CLARIFY","detail":"L1 成立：44 块逐块标注目标文件与符号名（新增文件与既有文件的行内符号均有）。L2 抽样核验全部通过，并另做机核：全量 markdown 锚点 410 条（.py 391 / .md 19），落在纯空白行者 0 处、越界者 0 处、目标文件缺失者 0 个。逐锚点抽检 7 个文件均与工作树一致：core/pity.py（_redistribute_scope 定义 416、4 处调用点 475/587/653/657、_validate_registry 815-829 且模块级调用 832、_validate_behaviors 931-982、_BTYPE_ORDER 906-911 与缺键消费点 926、_should_reset 205-208、_SOFT_TYPES/_HARD_TYPES 112/113、_EVENT_DRIVEN_TYPES 114-115、get_behaviors_for_pool 1187-1197、构造兜底 try/except 1162-1171、_build_activation_graph 1203-1227、lc.depends_on 1214-1215、四个 PityContext 构造点 530/1272/1301/1333、_build_pity_state_init 1003-1004 与 1007-1008）；service/batch_simulator.py（_PityDef 别名 import 202、pentry 1168-1193 实测 24 键、_ms_initial 477-482、GachaState( 508、MPPool 873-876）；core/config_toml.py（load_toml 的 store.clear() 62-64、H3 拒绝分支 686-691、_build_pity 定义 612 与 PityDef( 构造 694、_pitydef_to_toml 1709）；gui/config_panel.py（_PITY_TYPES 2019-2031、_do_update_preview 的别名读 6046、GUI 兜底保底条目 6544-6547）；core/worst_impact.py（五元组解包 530-531、PoolPitySpec( 543-552 及槽位实参 549/550/551）；service/gacha_service.py（253 局部 import / 275 isinstance / 292 与 294 的 selected_card 写入）；另核 tests/core/test_pity_rebind.py:10、tests/gui/test_config_panel_p56.py:48/53/116、tests/core/test_pity_config_toml.py:249/263、tests/gui/test_config_panel_pity.py:220 亦一致。未达标面一处：P82-2（第 2597 行）的两个新建产物 scripts/p82_baseline.py 与 tests/fixtures/p82_baseline/ 只出现在该任务块内部，§四 波及范围表（第 2345 至 2404 行）无任何 scripts/ 行、tests/fixtures 零登记（该表的 tests/ 行为泛写行）。这与本计划既有口径不一致：第七轮 ISSUE-GATE-file-list 曾把补 S3/S5/S10/S11 四处缺失目标文件列为 GATE-2 未达标面，第十轮 ISSUE-GATE-FAIL-2 也曾为 §四 补 core/worst_impact.py 等两行缺失文件。","clarify_suggestions":[{"location":"计划第 2345 至 2404 行（§四 波及范围表）","issue":"P82-2 的新建产物 scripts/p82_baseline.py 与 tests/fixtures/p82_baseline/ 未进入波及范围表，全篇无 scripts/ 行","suggestion":"在 §四 表内新增两行： scripts/p82_baseline.py（新增，P82-2）：基线固化脚本，沿用 scripts/p79_baseline.py 的 --config/--seed/--out 三参与 sys.path 注入写法，禁止覆盖 tests/fixtures/p79_golden/ ； tests/fixtures/p82_baseline/（新增，P82-2）：每组配置一个 JSON，形态同 tests/fixtures/p79_golden/"}]},{"id":"依赖顺序","verdict":"NEEDS_CLARIFY","detail":"L1 成立：M1 的 29 块给定唯一线性强制顺序（第 2580 行），无环；M2 逐子项独立 commit 并配向消费方的依赖闭包规则（GATE-5）；S7b 对 InvariantChecker 的前置依赖已按第十轮 GATE-check-3 移入 S11 专属文件、两处反指已删；S8-1/S8-2/S8-3 的原子单元登记与 GATE-5 的连带范围一致。L2 主要产销对逐条对上：preset 返回 dict 的五键集到 Pity(...) 按名取键构造、三族 state_keys() 到 Pity._declared_keys、build_lifecycle 随 S1d 定义先于 S4-2/S4-3 调用、priority 字段随 S4b 先于 S4-2 构造形参与 S6b 排序、_PITY_COMMON_KEYS 的扩表点（S4b 的 priority / S4-4 的 max_triggers / S6a 的 rotating_inverse）均晚于 S4c（第 2697 行与 S4-4/S6a 条目已互指）、NamespaceTracker 随 S1c 先于 S4-3、_lower_rarities 随 S2a-1 先于 S2a-2、_target_of 与裁决 7B 的类型级硬拒同在 S4-2、_apply_delta 的增量层调用点（S8-6）晚于其定义（S8-1）。未达标面一处，与第十轮 GATE-check-3（S7b 引用其后 5 位的 S11 产物）属同一失败形态：S2a-1（第 2659 行）的交付物明列「Modifier 基类（rebind 空实现 + apply 默认实现 + state_keys 默认 () + namespace 属性）」，而 §3.14.3（第 2339 行）与 §3.9.2（第 1693 行）把该 apply 默认实现写死为 _apply_delta(dist, self.compute_delta(view, dist, ctx) or {})；_apply_delta 的归属是 S8-1（第 2805 行「_apply_delta 做归一化」），其所在代码块（第 1684 至 1708 行）处在「S1–S5 期间本节内容全部不实施」的过渡期纪律之下。即 M1 阶段该默认实现体内引用一个 M2 才存在的模块级函数，而 S2a-1 的验收第 ① 条（Modifier 基类的 apply 默认实现与 rebind 空实现各一条）要求对它写可执行用例，按字面施工即 NameError；同时 M1 期所有具体 Modifier 均直接实现 apply（§3.1.2 历史形态），该默认实现在 M1 无任何消费者，其形态与 _apply_delta 的落地时机计划未作规定。","clarify_suggestions":[{"location":"计划第 2659 行（S2a-1 交付物与验收 ①）、第 2339 行（§3.14.3）、第 1693 与 1708 行（§3.9.2）、第 2805 行（S8-1）","issue":"S2a-1 交付的 Modifier 基类 apply 默认实现，其规格体内的 _apply_delta 由 S8-1 交付，导致 M1 期该默认实现按规格写即 NameError，且 S2a-1 验收 ① 的断言对象不可执行","suggestion":"在 S2a-1 与 §3.14.3 各补一句明确 M1 期形态，二选一：(a) _apply_delta 随 S2a-1 与默认实现同批落地（S8-1 只改调用点、不新建该函数，并把「_apply_delta 做归一化」改为「_apply_delta 沿用 S2a-1 实现」）；(b) M1 期基类 apply 为占位（raise NotImplementedError 或省略），默认实现与 S2a-1 验收 ① 一并移入 S8-1。选定后同步 §3.9.2 的「S1–S5 期间本节内容全部不实施」边界与 S8-1 的任务项措辞"}]}]
```

**本条机械复校（2026-10-09，本条落地时按工作树核对）**：`文件清单` 项所引行号逐条落位：2599（P82-2 任务块，实测含 `scripts/p82_baseline.py` 与 `tests/fixtures/p82_baseline`）、2345 至 2404（§四 波及范围表，2344 为标题、2405 为下一节标题，表体行 2346 至 2391 全在该区间内）、2339（§3.14.3 的 `apply` 条）、1693 与 1708（§3.9.2，1693 = `return _apply_delta(dist, self.compute_delta(view, dist, ctx) or {})`、1708 = `def _apply_delta(dist, d):`，过渡期纪律在 1618 行）、2662（S2a-1 任务行）、2808（S8-1 任务行，含「`_apply_delta` 做归一化」）；`依赖顺序` 项的 2580（M1 内部执行顺序行）同样落位。**一处不落位**：`依赖顺序` 项括注的「第 2697 行」实为 **第 2712 行**（2712 = 「**`priority` 必须收进 `_PITY_COMMON_KEYS`（2026-10-09 订正）**」条，文中「由紧邻在前的 **S4b** 定义」加「`max_triggers`（S4-4 定义）与三个新增 btype（S6a 的 `rotating_inverse`）」正是所述互指处；2700 属 S4-1 块的 preset 构造形态条，与该互指无关）。上方 JSON 按门控原文照录未改，本条以本节实测为准。**本轮（第 11 次审查）追加的偏移说明**：本轮正文新增 **3 行**（独立先行块组标题之后 +2、S1a 的类型集合条目之后 +1），故上列引用中**位于插入点之后**的五条已按实测整体后移（2597→**2599**、2659→**2662**、2697→**2700**、2709→**2712**、2805→**2808**；其中只有 2597 落在两处插入点之间，故取 +2，其余四条取 +3），而 `2580`（M1 内部执行顺序行）与 `2345 至 2404`（§四 波及范围表）、`2339` / `1693` / `1708`（均在插入点之前）**不变**——仍为原位；**上方 JSON 里的旧值不再回写**（照录原文），需以本段为准。另「§四（2345 至 2404 行）无任何 `scripts/` 行」按「表内无 `scripts/` 文件的登记行」口径成立（2380 行 `config/config.toml` 行的**说明文字内**引用了 `scripts/p79_verify.py`，非该行的登记文件；`tests/fixtures` 亦无登记行，2387 行的 `tests/` 为泛写行），与该项的表述一致。全篇 markdown 锚点复跑仍为 **410 条**（`.py` 391 / `.md` 19；去重 249 / 237），**落在纯空白行者 0 处、越界者 0 处、目标文件缺失者 0 个**；本次新增内容不含行号锚点，未改变该计数。**（2026-10-10 订正）**：该结论只对**该轮**成立，其后第六轮 +18、第七轮（S9-5 与跨文档订正等改动）再增，**现行全量锚点为 446 条**（`.py` 425 / `.md` 21）——本节两处「现行值」（本行 410 与上行 428）**均已过期，以 446 为准**（口径与脚本见「引用核对记录」；区间终点落在纯空白行的 12 处属既有状态，文档「本轮仍未处理」段已登记其中两例）。

**历史（保留，2026-10-01 清空）**：设计层无未解决阻塞项。原「6 轮对抗循环未收敛」的熔断记录已移入上方「自动化审查记录」的第 6 次审查条目；ISSUE-926 的两个子项（:1444 的归因措辞、:5 的「每池共享」残留）均已修复。**行号等机械项的回退与尚未核对的面见上方「引用核对记录（2026-10-09）」：本计划的行号锚点仍有未核面，不得据「无未解决阻塞项」推定全篇引用已核或已修。**<!-- REVIEW-R1-FIX: ISSUE-926 --><!-- REVIEW-R1-FIX: ISSUE-004 -->
