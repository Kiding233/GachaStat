<!-- META: P63 | module:模拟服务层 | status:designing | last:2026-07-28 | depends:P60✅ | review:R2-fixed(GATE-1-变更粒度,GATE-5-回滚路径,GATE-6-测试策略) -->
<!-- ref: docs/05-参考资料/外部研究/gacha-acquisition-reward-framework.md (v2) -->

# P63 溢出卡资源转换——收敛到 state.add_card() 的统一溢出管道

> 日期：2026-07-15 | 更新：2026-07-28 | 状态：设计中（R2 修复完成：GATE-1 变更粒度 + GATE-5 回滚路径 + GATE-6 测试策略）
> 触发：游戏手册 §溢出/满突破后分解——抽到重复卡时产出不同资源（如原神星辉系统）。当前 `compute_bonus_resources()` 逻辑完整，但 TOML 配置管道断裂；milestone (P58) 注入的卡也不触发溢出。
> 依赖：P60（提供 `state.add_card()` / `state.get_card_count()` / `state.acquired` 一等公民字段）
> 设计基础：`gacha-acquisition-reward-framework.md` v2——统一规则模型（Rule = Trigger × Path × Counter × BandedTable × Output，挂载于 Host）
> **2026-07-26 架构修订：** 基于框架文档 v2——三字段收敛为分段表内部表示 + 语法糖；新增路径记录与稀有度默认兜底；`resources_gained` 留在池子分布不变。
> **2026-07-26 六项决策：** ① `compute_bonus_resources()` 废弃删除 ② E2/E6 合并为原子阶段 ③ `resources_gained` 管道修复（E4） ④ 新建 `core/overflow.py` 内聚分段表代码 ⑤ `None` = 无穷（TOML `"inf"`） ⑥ `card_overflow_map` 放 `ConfigStore` 全系统共享

---

## 一、问题

### 1.1 触发点与机制分界

抽卡游戏中，「执行抽卡→获得卡牌→积累资源」这条链上存在三个独立的触发点，各自对应不同的奖励机制：

| # | 触发点 | 语义 | 条件 | 挂载 | 实证 |
|---|--------|------|------|------|------|
| ① | **DrawPerformed** 抽卡行为 | 一次付费抽卡动作完成，与抽到什么无关 | 恒真（按次结算） | 池子 | NIKKE 每抽给 1 金票；阴阳师每召唤 1 次得 1 异世之结 |
| ② | **CardAcquired** 卡牌获得 | 一张卡进入玩家仓库（任何路径：抽出/赠送/兑换） | 该卡累计获得次数 n 的分段表 | 卡片（或稀有度默认） | 原神 5★ 第 2~7 次获得→星辉×10，第 8 次起→星辉×25；明日方舟 6★ 三段黄票；星铁 5★ 光锥每次获得→星芒×40 |
| ③ | **MilestoneReached** 里程碑达成 | 池累计抽数跨越配置阈值 | 池抽数 == 阈值 | 池子 | 阴阳师 40 抽送 SSR；终末地 240 抽送信物、30/60 抽送十连 |

这三个触发点各自是一等公民——NIKKE 一抽同时触发 ①（金票）+ ②（重复 SSR→躯体标签），证明它们必须平行存在而非彼此的变体。

**当前系统只实现了 ② 的雏形**（`resources_gained` 在池子分布上），且是断裂的——TOML 管道不通、溢出分散在 `gacha_service` 循环中、Milestone 路径完全不支持。本计划的边界是 **② CardAcquired 触发点**。① 和 ③ 属于 P58（里程碑引擎）的范畴，此处仅确保接口兼容。

### 1.2 卡牌获得奖励的本质：分段表

框架文档的核心收敛——`first_time_bonus`（首次获得）、`nth_time_bonus`（第 N 次获得）、`excess_bonus`（持有 ≥N 后每次）**不是三种机制，而是同一种机制（分段表）的三组参数**：

```
分段表 = 若干互斥且完备的区间 → 产出
  [1, 1]   → { 黄票 × 1 }            ← "首次获得"
  [2, 6]   → { 黄票 × 10 }           ← "第 2~6 次获得"
  [7, ∞)   → { 黄票 × 15 }           ← "满潜后每次"
```

明日方舟 6★ 就是天然的三段表实证。原神 5★ 是两段表 `[1,1]→{命星} [2,7]→{星辉×10} [8,∞)→{星辉×25}`。星铁光锥是单段恒真表 `[1,∞)→{星芒×40}`。

关键假设（框架 ADR-6）：**仓库 = 累计获得次数，卡本体永不消耗。** 突破/命座/潜能是 `min(n-1, cap)` 的纯派生，不引入独立状态。在此假设下「持有数」与「累计获得次数」合一，分段表以**获得后的计数**求值（本次获得是第几次），全系统只有一种解释。

### 1.3 事实核查校正

框架文档对背景案例做了独立检索，纠正了两处关键偏差：

| 游戏 | 原假设 | 校正后事实 | 设计影响 |
|------|--------|-----------|----------|
| NIKKE | 重复 SSR→金票/银票（不同池产出不同） | 金票/银票按**抽卡次数**发放，与抽到哪张卡无关；重复 SSR→备用躯体→躯体标签 | 金票属于触发点①（DrawPerformed），躯体标签属于触发点②（CardAcquired）——本计划只管躯体标签 |
| 阴阳师 | 送的卡按持有数给御札（溢出自动生效） | 御札需玩家手动返魂（属处置系统）；但官方明确赠送**不计为召唤获得**——路径区分是真实存在的 | 路径必须被记录为事件事实；手动处置留在框架外 |
| 终末地 | 六星首次获得额外奖励（未证实） | 实际机制：**角色池出六星→产出武器池配额 2000**（跨池产出） | 产出归属不应硬编码为「触发池」；产出项应能声明目标资源账目 |

### 1.4 三层断裂

当前溢出转换机制存在三个断裂点：

| # | 断裂点 | 表现 |
|---|--------|------|
| F1 | TOML → PoolDistEntry | `_build_pools()` 和 `_expand_template_with_bindings()` 构造 `PoolDistEntry` 时不读取 bonus 字段，下游拿到的永远是空 `{}` |
| F2 | bonus 附着在 Reward（池子级） | Milestone 注入的卡没有关联的 Reward 对象，无法调用 `compute_bonus_resources()` |
| F3 | `state.add_card()` 是纯计数器 | 只做 `acquired[card_id] += 1`，不触发资源变化。也不记录获得路径 |

当前溢出判定是「抽卡循环的附带逻辑」而非「获得卡片这个动作的内建属性」——任何不走 `pool.draw()` 的卡牌获取路径都不会触发溢出。

---

## 二、目标

### 核心目标

1. **修复 TOML 配置管道**：卡片溢出规则正确解析到 `CardDefEntry`，池子固定产出 `resources_gained` 正确解析到 `PoolDistEntry`
2. **收敛溢出判定到 state**：`GachaState.add_card()` 接受溢出分段表，内部匹配并返回溢出资源，统一所有卡牌获取路径
3. **记录获得路径**：`GachaState` 按路径切片记录获得计数，为未来路径过滤（「仅抽卡触发」）预留基础设施
4. **Milestone 兼容**：P58 注入的卡以 `path=milestone_gift` 进入 `add_card()`，自动获得溢出能力

### 设计决策

| 决策 | 结论 | 理由 |
|------|------|------|
| `resources_gained` 存哪 | `PoolDistEntry`（不变） | 属于池×卡语义槽位——不同池子同一张卡可有不同的固定产出；框架 D6 池×卡预留层级 |
| 溢出分段表存哪 | `CardDefEntry` + 稀有度默认兜底 | 卡片溢出是卡片内在属性，路径无关、跨池一致（原神/方舟实证）；稀有度默认避免逐卡重复配置（终末地六星武库配额、星铁光锥） |
| 内部表示 | 分段表（bands）——互斥完备区间 → 产出 | 框架 ADR-1——首次/N次/溢出统一为分段表参数化 |
| 配置语法 | 三字段语法糖 + 分段表高级模式共存 | 99% 场景三字段够用；方舟三段表等复杂场景用分段表；解析时语法糖展开为 bands |
| `OverflowBand` 代码位置 | 新建 `core/overflow.py` | 同时被 config_store / config_toml / state / pool 引用——放 pool.py 会导致跨层反向导入；独立文件职责单一、导入链路干净 |
| `card_overflow_map` 构建位置 | `ConfigStore` 派生属性——TOML 解析完成后填充 | 分段表是配置数据而非服务逻辑；全系统（GachaService + P58 Milestone 引擎 + CLI）共享同一份解析结果 |
| 无限区间表示 | `max: int \| None`，`None` = ∞；TOML 中写 `"inf"` | Python dataclass 中 `None` 是最自然的前哨值，`int \| None` 类型注解明确表达「可能无上限」；`math.inf` 引入浮点精度问题 |
| `compute_bonus_resources()` | 废弃删除 | 唯一调用方 `gacha_service.py:339` 改为 `state.add_card()` 后无调用方；12 个旧测试迁移为 `match_overflow_bands` 测试 |
| Reward / PoolDistEntry 三字段 | 同步移除 `first_time_bonus` / `nth_time_bonus` / `excess_bonus` | 删函数→删字段→适配 batch_simulator 为原子阶段，不在 commit 间留僵尸字段 |
| 路径 | MVP 记录路径切片 `acquired_by_path`，不做过滤 | 当前 19 款游戏全部路径无关；路径过滤（「仅抽卡触发称号」）预留扩展 |
| 资源归属 | 触发池作为审计标签；产出项可声明目标账目 | 终末地跨池产出反例——产出归属不应硬编码为触发池 |
| 稀有度默认 | `[rarity_defaults]` TOML 段，卡片级覆盖 | 解析优先级：卡片 > 稀有度默认 |
| 向后兼容 | `add_card()` 不传参时行为不变（纯计数，返回 `{}`） | 渐进式——现有调用方零改动 |
| 与 P55/P56/P58 关系 | 零依赖、零冲突、可完全并行 | 改不同文件、不同段落 |
| `collector.on_bonus()`（设计意图——不属本计划实施范围，collector.py 不受影响）| 若未来实现，则仅存元数据（事件名、触发时间、卡片 ID、路径），不承载资源金额 | 资源统一走 `combined_gained`——`on_bonus` 若实现则为审计记录，不是会计科目；单通道防重复入账。当前 `collector.py` 无此 API，由未来需求驱动实施 |<!-- REVIEW-R1-FIX: ISSUE-113 -->
| GUI 范围 | 稀有度默认编辑器——「满突溢出」子标签页（`config_panel.py`）。卡片级覆盖、`nth_time_bonus`、高级三段表留 TOML 手写 | 覆盖 99% 场景（原神/星铁/终末地均为稀有度级规则）；卡片级是罕见例外

### 非目标

- 不实现 DrawPerformed 和 MilestoneReached 触发点（属 P58 范畴）
- 不实现路径白名单过滤（MVP 记录路径但不按路径过滤规则）
- 不实现池×卡挂载层级（仅 `resources_gained` 占据该语义槽位，不新增通用规则挂载）
- 不改动分析面板、GDR 计算、方案搜索等下游模块
- 不在 `Reward` 上保留 `first_time_bonus` / `nth_time_bonus` / `excess_bonus`——三个字段从 Reward 移除

---

## 三、方案

### 3.1 架构变更

```
现状：
  pool.draw() → reward
  state.add_card(id)                        ← 只管计数，不记路径
  ... 十几行后 ...
  compute_bonus_resources(reward, before, after)  ← 溢出在外面
  rg = base + bonus

方案（修订后）：
  pool.draw() → reward
  rg = {}
  rg += reward.resources_gained                  ← 池子固定产出（不变）
  rg += state.add_card(                          ← 卡片溢出管道
      id, path="draw",
      overflow_bands=card_overflow_map.get(id)
  )
       │
       ├── acquired[card_id] += 1
       ├── acquired_by_path[card_id]["draw"] += 1
       ├── 定位分段表区间（n = total_holding）
       └── return 该段产出（{} 若无规则）
```

Milestone 赠送卡调用同一接口：

```
state.add_card(cid, path="milestone_gift", overflow_bands=...)
```

### 3.2 核心数据结构：分段表

内部统一用分段表表示，替代当前三个独立字段。所有与分段表相关的代码收敛到新建文件 `core/overflow.py`（含 dataclass + 匹配函数 + 语法糖展开函数）：

```python
# core/overflow.py
@dataclass
class OverflowBand:
    min: int
    max: int | None           # None = ∞（无穷大），TOML 中写 "inf"
    resources: Dict[str, float]
```

约束：
- 区间互斥且完备覆盖 `[1, ∞)`
- 以获得后的 `total_holding` 定位区间
- 相邻同产出区间自动合并（语法糖展开时）
- 空产出段（`resources = {}`）不存储——匹配时落在间隙直接返回 `{}`
- TOML 中 `range = [7, "inf"]` → 解析为 `OverflowBand(min=7, max=None, resources=...)`

三字段语法糖在 TOML 解析时展开为分段表，应用层只看到分段表：

| 语法糖字段 | 展开为 band |
|---|---|
| `first_time_bonus = { X = 10 }` | `[1, 1] → { X = 10 }` |
| `nth_time_bonus = { 3 = { X = 20 } }` | `[3, 3] → { X = 20 }` |
| `excess_bonus = { threshold = 7, resources = { X = 25 } }` | `[7, ∞) → { X = 25 }` |

### 3.3 TOML 配置语法

**① `resources_gained`——池子分布上，每次抽到的固定产出（预留槽位，暂无实证用例）：**

```toml
# 分布模板中
[[distribution_templates.cards]]
card_id = "limited_ssr_1"
probability = 0.6
rarity = "ssr"
featured = true
resources_gained = { starglitter = 10 }        # ← 每次抽到此卡固定给 10（与持有次数无关）

# 内联 distribution
[[pools.distribution]]
card_id = "sr_1"
probability = 5.0
rarity = "sr"
resources_gained = { starglitter = 2 }
```

> 该槽位为「同卡不同池不同固定产出」预留，手册 19 款游戏中无实证——终末地武库配额实为稀有度级恒真规则（见 ④），NIKKE 金票/银票属 DrawPerformed 触发点（P58 范畴）。当前保留以保持数据模型完备性。

**② 卡片溢出——三字段语法糖（覆盖 99% 场景）：**

```toml
[[card]]
card_id = "limited_ssr_1"
name = "限定 SSR 角色 A"
rarity = "ssr"
initial_count = 0

[card.overflow]
first_time_bonus = { starglitter = 10 }              # 首次获得 → 10
nth_time_bonus = { 3 = { special_token = 20 } }      # 第 3 次获得 → 特殊代币
excess_bonus = { threshold = 7, resources = { starglitter = 25 } }  # ≥7 次后每次 → 25
```

三字段可自由组合——不配的段不写即可。解析时展开为分段表：

```
bands = [1,1]→{starglitter:10} + [2,2]→{} + [3,3]→{special_token:20}
      + [4,6]→{} + [7,∞)→{starglitter:25}
```

**③ 卡片溢出——分段表高级模式（方舟三段黄票等复杂场景）：**

```toml
[[card]]
card_id = "ark_6star"
name = "六星干员"
rarity = "ssr"

# 使用 bands 数组时忽略语法糖字段
[[card.overflow_bands]]
range = [1, 1]
resources = { yellow_cert = 1 }       # 首次获得 → 1 黄票

[[card.overflow_bands]]
range = [2, 6]
resources = { yellow_cert = 10 }      # 第 2~6 次 → 10 黄票

[[card.overflow_bands]]
range = [7, "inf"]
resources = { yellow_cert = 15 }      # 满潜后每次 → 15 黄票
```

语法糖与 `overflow_bands` 不共存——配了 bands 数组则忽略语法糖。

**④ 稀有度默认——同稀有度统一规则的兜底：**

```toml
[rarity_defaults.ssr]
[[rarity_defaults.ssr.overflow_bands]]
range = [1, 7]
resources = { starglitter = 10 }

[[rarity_defaults.ssr.overflow_bands]]
range = [8, "inf"]
resources = { starglitter = 25 }

[rarity_defaults.sr]
[[rarity_defaults.sr.overflow_bands]]
range = [1, 7]
resources = { starglitter = 2 }

[[rarity_defaults.sr.overflow_bands]]
range = [8, "inf"]
resources = { starglitter = 5 }
```

框架设计能力不限三段——稀有度键名从 `[rarities].ranks` 动态解析，配置中注册几个稀有度就有几个段。恒真单段（星铁光锥、终末地武库配额）仅需一段 `[1, "inf"]` 覆盖全部获得次数。

解析优先级：**卡片显式配置 > 稀有度默认**。卡片配了 `[card.overflow]` 或 `[[card.overflow_bands]]` 则使用卡片配置；否则 fallback 到 `rarity_defaults[card.rarity.lower()]`（键名在解析时统一 `.lower()` 归一化存储——与 `rarity_rank` 的 `.upper()` 方向互补而非一致：`.lower()` 用于 TOML 段名查找（不分大小写），`.upper()` 用于展示/排序，两者独立正确但方向相反，跨映射查找时不可混用归一化方向）<!-- REVIEW-R1-FIX: ISSUE-011,ISSUE-114 -->；稀有度默认也没配该段则无溢出规则。

**设计前提验证：** 手册覆盖的 19 款游戏中，所有 CardAcquired 溢出规则均与获得路径无关——原神、星铁、方舟、NIKKE 躯体、火影的溢出行为在抽卡/兑换/赠送等所有路径下完全一致。这验证了「溢出规则绑定卡片」的设计前提，也解释了为何 MVP 不做路径过滤。

### 3.4 改造 `GachaState`

**新增字段：**

```
acquired_by_path: Dict[str, Dict[str, int]]
# {"card_id": {"draw": 3, "milestone_gift": 1}}
```

**`add_card()` 新签名：**

```python
def add_card(self, card_id: str, path: str = "unknown",
             overflow_bands: Optional[List[OverflowBand]] = None,
             initial_counts: Optional[Dict[str, int]] = None) -> Dict[str, float]:
    """获得一张卡。返回本次触发的溢出资源。
    
    Args:
        path: 获得路径——"draw" | "milestone_gift" | "exchange" | "event_gift"
        overflow_bands: 该卡的分段表（已解析），None 则跳过溢出计算
        initial_counts: 初始持有数映射（用于正确计算 total_holding）
    """
```

内部流程：
1. `acquired[card_id] += 1`
2. `acquired_by_path[card_id][path] += 1`
3. 若 `overflow_bands` 非空：计算 `total_holding = initial_counts.get(card_id, 0) + acquired[card_id]`，定位分段表区间，返回区间产出
4. 否则返回 `{}`

不传 `overflow_bands` 时行为与现在完全一致（纯计数，返回 `{}`）。

**`clone()` 同步修改：**<!-- REVIEW-R1-FIX: ISSUE-105 -->
`clone()` 方法增加 `acquired_by_path` 的深拷贝——`{cid: dict(paths) for cid, paths in self.acquired_by_path.items()}`。`clone()` 是运行时语义（策略分支评估等场景需复制状态后模拟），非序列化语义——`acquired_by_path` 虽不参与 JSON 序列化（§七风险表），但在策略评估等 clone 分支场景下必须正确传递，否则 path 记录在分支上丢失，违反「记录获得路径」核心目标（第二节第 3 条）。

**约束：** 当 `overflow_bands` 不为 None 时，调用方**必须**传入 `initial_counts`——分段表以 `total_holding = initial_counts[card_id] + acquired[card_id]` 定位区间。不传 `initial_counts` 时，「初始持有 2 张卡 X，模拟中第一次抽到 X」会被错误地当作「第 1 次获得」而定位到 `[1,1]` 段，错误触发 `first_time_bonus`。`gacha_service` 和 milestone 集成点始终传入 `_initial_counts`，不受影响。<!-- REVIEW-R1-FIX: ISSUE-002 -->

**防御性校验：** `add_card()` 内部使用显式 `if overflow_bands is not None and initial_counts is None: raise ValueError(...)`——**不使用 `assert`**。`assert` 语义为内部不变式，`initial_counts` 属调用方外部输入；Python `-O`（optimize）标志会剥离所有 `assert` 语句，届时错误调用将静默产生错误的溢出资源计算结果。

### 3.5 构建 `card_overflow_map` + 简化 gacha_service

`card_overflow_map` 是 `ConfigStore` 的派生属性——TOML 解析完成后，卡片溢出规则与稀有度默认已全部就绪，此时即可确定每张卡的最终分段表。新增 `_build_card_overflow_map(store)` 辅助函数，在 `load_toml()` 中 `_backfill_card_pools(store)` 调用之后（第 74 行附近）调用：<!-- REVIEW-R1-FIX: ISSUE-010 -->

```
# ── 构建前：rarity_defaults 键名已在 _build_cards() 解析时归一化为 .lower() ──
# ── card_def.rarity 查找时同样 .lower() 归一化 —— 与 rarity_rank 的 .upper() 方向互补（用途不同：段查找 vs 展示排序） ──<!-- REVIEW-R1-FIX: ISSUE-114 -->
card_overflow_map = {}
for card_def in card_defs:
    if card_def.overflow_bands:
        bands = card_def.overflow_bands                 # 卡片显式配置
    else:
        rarity_key = card_def.rarity.lower()            # ← 归一化查找，避免大小写不匹配
        bands = rarity_defaults.get(rarity_key, {}).get('overflow_bands', [])
    if bands:
        card_overflow_map[card_def.card_id] = bands

ConfigStore.card_overflow_map = card_overflow_map
```

`ConfigStore.card_overflow_map` 为全系统共享——`GachaService`、P58 Milestone 引擎、CLI 工具均从同一位置读取，不重复计算优先级逻辑。

抽卡循环中 bonus 段简化：

```python
# ── 改动后 ──
rg = dict(reward.resources_gained or {})           # 池子固定产出（不变）
if reward.id != _NO_CARD_ID:
    overflow = state.add_card(
        reward.id, path="draw",
        overflow_bands=card_overflow_map.get(reward.id),
        initial_counts=_initial_counts,
    )
    for k, v in overflow.items():
        rg[k] = rg.get(k, 0) + v                    # 溢出合并到 rg
```

Milestone 注入同样受益——卡片溢出自动生效：

```python
# P58 Milestone 注入
milestone_rg = dict(entry['bonus'].get('resources', {}))
for cid in entry['bonus'].get('card_ids', []):
    overflow = state.add_card(
        cid, path="milestone_gift",
        overflow_bands=card_overflow_map.get(cid),
        initial_counts=_initial_counts,
    )
    for k, v in overflow.items():
        milestone_rg[k] = milestone_rg.get(k, 0) + v
rg.update(milestone_rg)
```

### 3.6 资源归属与记账

```
所有资源收入（池固定产出 + 卡片溢出 + milestone + wait收益）
        │
        ▼
      rg dict（单抽/单动作的资源汇总）
        │
        ├── state.resources[k] += v      ← 立即可用于下一抽
        ├── total_gained[k] += v         ← 全局累加
        └── combined_gained → draw_resources_gained[i]
                                    │
                      [审计标签：来源池、触发点类型]
                                    │
                      pool_resources_gained[pid] ← 触发池作为默认归属
```

跨池产出（终末地场景）：产出资源的 key 自身声明归属语义（如 `weapon_quota` 天生属武器池账目）。触发池仅作为审计标签随 `combined_gained` 记录，不强制决定归属科目。MVP 不实现显式的跨池会计，但数据格式预留了审计标签，未来不需要改格式。

### 3.7 `Reward` 与 `PoolDistEntry` 清理

**`compute_bonus_resources()`（`core/pool.py`）：废弃并删除。** 唯一调用方 `gacha_service.py:339` 在 §3.5 中改为 `state.add_card()`，函数在全项目中再无调用方。配套动作：
- 从 `core/__init__.py` 移除导出
- `tests/core/test_pool_bonus.py` 中 12 个测试迁移为 `match_overflow_bands()` + 语法糖展开测试

**`Reward`**（`core/pool.py`）：移除 `first_time_bonus` / `nth_time_bonus` / `excess_bonus` 三个字段。`resources_gained` 保留——作为唯一的池子级资源产出字段。

**`PoolDistEntry`**（`core/config_store.py`）：三个字段移除——与 Reward 同步，消除两端不一致的中间态。

**`batch_simulator.py`**：构造 `Reward` 时不再传这三个字段。

**`config_panel.py`**：<!-- REVIEW-R1-FIX: ISSUE-100,ISSUE-102 -->
- **`PoolDistEntry` 构造适配**（ISSUE-100）：`apply_to_store()` 第 3278-3281 行和 `_save_current_as_new_template()` 第 3814-3823 行两处 `PoolDistEntry()` 构造调用移除 `first_time_bonus`/`nth_time_bonus`/`excess_bonus` 三个关键字参数；`_refresh_from_store_impl()` 第 3960-3962 行的 `getattr(d, 'first_time_bonus', {})` 等读取同步移除。
- **`DistributionDialog` 清理**（ISSUE-102）：移除「额外资源」列——列数从 6 缩减为 5，表头标签移除「额外资源」；`_populate()` 第 192-195 行、`_add_row()` 第 222-224 行、`_add_no_card_row()` 第 257-259 行中的 `bonus_edit` 控件移除；`get_distribution()` 第 329/343-345 行移除 bonus 字段返回；删除模块级函数 `_bonus_to_text()`（第 22 行）和 `_parse_bonus_text()`（第 43 行）。

**`test_p60_gacha_state.py`**：<!-- REVIEW-R1-FIX: ISSUE-101 -->
- `test_add_card_increments` 断言从 `assert state.add_card("diluc") == 1`（int）改为断言返回 `dict` 类型且为空（不传 `overflow_bands` 时返回 `{}`）；新增带 `overflow_bands` 参数的测试验证溢出资源返回。

以上六项（废弃函数 + 移除字段 + 移除 PoolDistEntry 字段 + 适配 batch_simulator + 适配 config_panel.py + 清理 DistributionDialog + 测试适配）合并为**一个原子阶段**——函数删除后三个字段立即成为无引用死字段，不应在两个 commit 之间停留。

### 3.8 扩展预留

| 扩展点 | 预留方式 | 何时激活 |
|--------|---------|---------|
| 路径白名单过滤 | `acquired_by_path` 已记录路径切片；规则的 `path_filter` 字段留空（默认=全部） | 出现首个「仅抽卡触发」需求时 |
| 池×卡挂载（同卡不同池不同价） | `resources_gained` 占据此语义槽位；通用规则不在此层级新增 | 出现首个实装需求时 |
| 跨池产出显式归属 | `combined_gained` 携带审计标签（来源池+触发点） | 终末地级跨池会计需求时 |
| 装饰品产出（称号/头像框） | 产出类型枚举留位 | 运营系统接入时 |
| 跨卡条件（「持有 A 且获得 B 时」） | **不预留**——框架 ADR：无实装、破坏规则局部性、仅记录决策 | 出现强实装需求时作为 2.0 议题 |

### 3.9 GUI：「满突溢出」子标签页

**位置**：配置面板左侧第七个标签页（与「卡牌定义」「资源管理」「卡池配置」「保底机制」「策略与目标」「权重配置」并列）。

**内容**：稀有度级三规则编辑器——表格每行一个稀有度，四组字段：

```
┌──────┬──────────────┬──────────┬─────────────────┬─────────────────┐
│ 稀有度 │ 首次获得产出   │ 满突张数   │ 满突前每次产出     │ 满突后每次产出     │
│      │ first_time   │ (阈值)    │ [1(2)~N]        │ [N+1, ∞)        │
├──────┼──────────────┼──────────┼─────────────────┼─────────────────┤
│ SSR  │ 星辉: 10     │ 7        │ 星辉: 10        │ 星辉: 25        │
│ SR   │ —            │ 7        │ 星辉: 2         │ 星辉: 5         │
│ R    │ —            │ —        │ —               │ —               │
└──────┴──────────────┴──────────┴─────────────────┴─────────────────┘
```

**稀有度列表来源**：从 `[rarities].ranks` 动态解析（展平 `[["SSR"], ["SR"], ["R"]]` → `["SSR", "SR", "R"]`），与 `ConfigStore.rarity_rank` 同源。配置中无 `[rarities]` 段时回退默认 SSR / SR / R 三级。

**展开逻辑**（写入 `ConfigStore.rarity_defaults` 时）：

| 用户填写 | 展开为分段表 |
|---------|------------|
| 首次✓ + 满突张数 N + 满突前✓ + 满突后✓ | `[1,1]→首次` + `[2,N]→满突前` + `[N+1,∞)→满突后` |
| 满突张数 N + 满突前✓ + 满突后✓ | `[1,N]→满突前` + `[N+1,∞)→满突后` |
| 满突张数空 + 满突前✓ | `[1,∞)→满突前`（恒真单段） |
| 全部空 | 该稀有度无溢出规则 |

**交互**：三组产出编辑器为键值对子表（资源名 / 数值，2 列 `QTableWidget`），复用卡片标签表模式。变更通过 `_on_detail_changed()` 信号实时写回 `ConfigStore.rarity_defaults`（P56 自动应用模式）。无「保存」按钮——改了即生效。

<!-- REVIEW-R1-FIX: ISSUE-111 -->**键名规范化（关键）：** GUI 写入/读取 `ConfigStore.rarity_defaults` 时，稀有度名必须转为 `.lower()`（如表格行展示 `"SSR"` → 写入时转为 `"ssr"`）。原因：§3.5 中 `_build_card_overflow_map()` 通过 `card_def.rarity.lower()` 查找溢出规则——若 GUI 直接用大写键名写入 `rarity_defaults["SSR"]`，运行时 `rarity_defaults.get("ssr")` 查找返回 `None`，导致该稀有度所有卡片静默回退到无溢出规则。实施时写入侧做 `rarity_name.lower()` 转换，读取侧同样 `.lower()` 查找，与 §3.3④ 中「解析时统一 `.lower()` 归一化存储」保持全程一致。

**不暴露在 GUI 中**：卡片级 `[card.overflow]` 覆盖、`nth_time_bonus`（第 N 次特殊奖励）、高级 `[[card.overflow_bands]]` 三段表——均通过 TOML 手写。

**成本**：~155 行，全部在 `gui/config_panel.py`。不新建文件。

## 四、实施阶段

| 阶段 | 内容 | 文件 | 预估行数 |
|:---:|------|------|:---:|
| E0 | 新建 `core/overflow.py`——`OverflowBand` dataclass + `match_overflow_bands(bands, n)` + `expand_sugar_to_bands(first, nth, excess)` 语法糖展开 | `core/overflow.py` | ~40 |
| E1 | `CardDefEntry` 新增 `overflow_bands: Optional[List[OverflowBand]]` 字段；`ConfigStore` 新增 `rarity_defaults` + `card_overflow_map` 字段；`ConfigStore.clear()` 增加 `rarity_defaults.clear()` + `card_overflow_map.clear()`（参照 `rarity_rank.clear()` 第 184 行先例——防止 `load_toml(store=existing_store)` 残留旧值） | `core/config_store.py` | ~25 |<!-- REVIEW-R1-FIX: ISSUE-103 -->
| E2 | `_build_cards()` 解析 `[card.overflow]` 语法糖 → 展开为 bands；解析 `[[card.overflow_bands]]` 数组；解析 `[rarity_defaults]` 段（解析时统一 `.lower()` 归一化键名——与 `rarity_rank` 的 `.upper()` 方向互补：`.lower()` 用于 TOML 段查找，`.upper()` 用于展示排序，两者独立正确但方向相反，跨映射查找时不可混用归一化方向）<!-- REVIEW-R1-FIX: ISSUE-010,ISSUE-011,ISSUE-114 -->；新增 `_build_card_overflow_map(store)` 辅助函数——在 `load_toml()` 中 `_backfill_card_pools(store)` 之后调用<!-- REVIEW-R1-FIX: ISSUE-010 --> | `core/config_toml.py` | ~40 |
| E2a | `save_toml()` 卡片序列化循环增加 `overflow_bands` 写出；`save_toml()` 新增 `[rarity_defaults]` 段序列化（遍历 `store.rarity_defaults`，按稀有度键名写出 `overflow_bands` 数组——与解析语法对称，参照 `rarities.ranks` 双向实现第 151-160 行）；溢出段写出格式策略：**统一写 bands 数组**（与内部表示一致、round-trip 无损） | `core/config_toml.py` | ~30 |<!-- REVIEW-R1-FIX: ISSUE-006,ISSUE-012,ISSUE-104,ISSUE-108 -->
| E3 | `GachaState.add_card()` 签名扩展——接受 path + overflow_bands + initial_counts；新增 `acquired_by_path` 字段；`GachaState.clone()` 增加 `acquired_by_path` 深拷贝（`{cid: dict(paths) for cid, paths in self.acquired_by_path.items()}`）——clone 是运行时语义（策略分支评估），非序列化语义，丢失 path 记录违反核心目标（第二节第 3 条） | `core/state.py` | ~30 |<!-- REVIEW-R1-FIX: ISSUE-105 -->
| E4 | TOML 分布管道修复——`_build_pools()` + `_expand_template_with_bindings()` 读取 `resources_gained`；`_distribution_matches_template()` 判等新增 `resources_gained` 比较（防止模板引用写回丢失字段）；`_save_templates_and_pools()` 内联分布写路径（第 225-233 行）增加条件写入 `resources_gained`——若 `d.resources_gained` 非空则写出，与 E4 读修复形成双向对称<!-- REVIEW-R1-FIX: ISSUE-003,ISSUE-106 --> | `core/config_toml.py` | ~25 |
| E5 | `GachaService` 改造——抽卡循环改为 `state.add_card()`；同步移除 `gacha_service.py` 第 11 行 import 中的 `compute_bonus_resources`（仅保留 `NO_CARD_ID as _NO_CARD_ID`——函数仍存在于 pool.py 不会被删除，移除导入不会导致 ImportError；但不移除会导致 ruff F401「imported but unused」阻断 E5 commit）<!-- REVIEW-R1-FIX: ISSUE-110 -->；构造器新增 `card_overflow_map` 参数；`SimulationEnv` 新增 `card_overflow_map` 字段（默认值 `{}`——保证 `from_dict()` 路径兼容性，`worst_impact.py` 等不使用 ConfigStore 的调用方不受影响）；`SimulationEnvBuilder.from_config_store()` 从 `ConfigStore.card_overflow_map` 注入 `SimulationEnv`<!-- REVIEW-R1-FIX: ISSUE-112 -->；`SimulationEnvBuilder.from_dict()` 增加 `card_overflow_map=config.get('card_overflow_map', {})` 透传；`_run_single()` 将 `env.card_overflow_map` 传递给 `GachaService` 构造器 | `service/gacha_service.py` + `service/batch_simulator.py` | ~45 |<!-- REVIEW-R1-FIX: ISSUE-004,ISSUE-107,ISSUE-110 -->
| E6a | 废弃 `compute_bonus_resources()`——删除函数体 + 从 `core/__init__.py` 移除导出 | `core/pool.py` + `core/__init__.py` | ~15 |<!-- REVIEW-R1-FIX: GATE-1-变更粒度——E6 拆分为 E6a/E6b/E6c/E6d 四个子阶段 -->
| E6b | `Reward` 移除 `first_time_bonus`/`nth_time_bonus`/`excess_bonus` 三个字段 + `PoolDistEntry` 移除三个字段 + `batch_simulator.py` 构造 `Reward` 时不再传这三个字段（4 文件联动——E6a 删除函数后此三字段立即成为无引用死字段，不得在 commit 间停留） | `core/pool.py` + `core/config_store.py` + `service/batch_simulator.py` | ~20 |<!-- REVIEW-R1-FIX: GATE-1 -->
| E6c | `config_panel.py` 适配——两处 `PoolDistEntry` 构造移除三个 bonus 参数（`apply_to_store` + `_save_current_as_new_template`）+ `_refresh_from_store_impl` 移除 bonus 读取 + `DistributionDialog` 清理（移除「额外资源」列、`bonus_edit` 控件、`_bonus_to_text()`/`_parse_bonus_text()` 模块级函数） | `gui/config_panel.py` | ~25 |<!-- REVIEW-R1-FIX: GATE-1 + ISSUE-100,ISSUE-102 -->
| E6d | 测试迁移——`test_pool_bonus.py` 12 个旧测试（实际 11 例）迁移为 `match_overflow_bands` 测试 + `test_p60_gacha_state.py` 断言适配（`add_card` 返回从 `int` 改为 `dict`；新增带 `overflow_bands` 的溢出资源返回测试） | `tests/core/test_pool_bonus.py` + `tests/test_p60_gacha_state.py` | ~30 |<!-- REVIEW-R1-FIX: GATE-1 + ISSUE-101 -->
| E7 | TOML 配置示例——卡片条目添加 `[card.overflow]` + `[rarity_defaults]` 配置 | `config/config.toml` | ~20 |
| E7a-1 | GUI「满突溢出」标签页骨架——标签页注册到配置面板左侧（第 7 个 Tab）+ 表格布局（稀有度列 × 四组产出编辑器列）+ 稀有度列表从 `[rarities].ranks` 动态解析（展平 `[["SSR"],["SR"],["R"]]` → `["SSR","SR","R"]`） | `gui/config_panel.py` | ~60 |<!-- REVIEW-R1-FIX: GATE-1-变更粒度——E7a 拆分为 E7a-1/E7a-2/E7a-3 三个子阶段 -->
| E7a-2 | GUI 数据绑定——读取 `ConfigStore.rarity_defaults` → 表格填充（每行渲染四组键值对子表）；`_on_detail_changed()` 信号实时写回 `ConfigStore.rarity_defaults`（P56 自动应用模式）；写入/读取时稀有度键名做 `.lower()` 规范化（§3.9 键名规范化）<!-- REVIEW-R1-FIX: GATE-1 + ISSUE-111 --> | `gui/config_panel.py` | ~50 |
| E7a-3 | 分段表展开逻辑——四种组合映射（首次+满突前+满突后 / 满突张数+满突前+满突后 / 仅有满突前→恒真单段 / 全空→无溢出规则）+ 空状态处理（未配置稀有度行显示「—」占位符） | `gui/config_panel.py` | ~45 |<!-- REVIEW-R1-FIX: GATE-1 -->
| E8 | 集成测试——分段表匹配、语法糖展开、优先级查找、端到端验证 + GUI 冒烟 | `tests/` | ~60 |
| **总计** | 13 个阶段（E0/E1/E2/E2a/E3/E4/E5 + E6a/E6b/E6c/E6d + E7 + E7a-1/E7a-2/E7a-3 + E8） | | **~560** |<!-- REVIEW-R1-FIX: GATE-1-变更粒度——E6 从 ~70 扩至 ~90（+~20），E7a 保持 ~155 不变，总计 ~540→~560 -->

**子阶段顺序与并行性**（<!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->）：

```
E6a → E6b（严格先后——函数删除后字段立即成为死代码，不得在 commit 间停留）
E6c ∥ E6d（可并行——config_panel.py 与测试互不依赖，E6c 仅需 E6b 完成）
   └── 全部在同一 PR 内顺序合并，保证原子性

E7a-1 → E7a-2（顺序依赖——骨架就绪后才能绑数据）
E7a-2 ∥ E7a-3（可并行开发——数据绑定与展开逻辑互不依赖，但最终集成到 E7a-1 骨架）
```

所有子阶段预估均 ≤ 1h。保守总工期：E6a..E6d 顺序链路 ~2.5-3h，E7a 链路 ~2.5-3h（含集成）。其余 7 个阶段（E0/E1/E2/E2a/E3/E4/E5/E7/E8）每个 ≤ 1h，拆分合理。

---

## 五、波及范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/overflow.py` | **新建** | `OverflowBand` dataclass + `match_overflow_bands()` + `expand_sugar_to_bands()` |
| `core/config_store.py` | **修改** | `CardDefEntry` 新增 `overflow_bands`；`ConfigStore` 新增 `rarity_defaults` + `card_overflow_map`；`ConfigStore.clear()` 增加 `rarity_defaults.clear()` + `card_overflow_map.clear()`；`PoolDistEntry` 移除三个 bonus 字段 |<!-- REVIEW-R1-FIX: ISSUE-103 -->
| `core/config_toml.py` | **修改** | `_build_cards()` 解析语法糖+bands+稀有度默认（解析时统一 `.lower()` 键名<!-- REVIEW-R1-FIX: ISSUE-011 -->）；新增 `_build_card_overflow_map(store)` —— 在 `load_toml()` 中 `_backfill_card_pools(store)` 之后调用<!-- REVIEW-R1-FIX: ISSUE-010 -->；`_build_pools()` / `_expand_template_with_bindings()` 读取 `resources_gained`；`_save_templates_and_pools()` 内联分布写路径增加 `resources_gained` 条件写入；`_distribution_matches_template()` 判等新增 `resources_gained` 比较；`save_toml()` 卡片序列化循环增加 `overflow_bands` 写出 + `[rarity_defaults]` 段序列化——防止 GUI 保存时静默丢弃手写卡片级/稀有度级溢出配置 |<!-- REVIEW-R1-FIX: ISSUE-006,ISSUE-104,ISSUE-106 -->
| `core/state.py` | **修改** | `add_card()` 签名扩展；新增 `acquired_by_path` 字段；`clone()` 增加 `acquired_by_path` 深拷贝 |<!-- REVIEW-R1-FIX: ISSUE-105 -->
| `core/pool.py` | **修改** | E6a: `compute_bonus_resources()` 废弃删除；E6b: `Reward` 移除 `first_time_bonus`/`nth_time_bonus`/`excess_bonus` 三个字段 |<!-- REVIEW-R1-FIX: GATE-1 -->
| `core/__init__.py` | **小改** | 导出 `OverflowBand` + `match_overflow_bands`；移除 `compute_bonus_resources` 导出 |
| `service/gacha_service.py` | **修改** | 抽卡循环改为 `state.add_card()`；移除第 11 行 `compute_bonus_resources` 导入（F401 阻断规避）<!-- REVIEW-R1-FIX: ISSUE-110 -->；构造器新增 `card_overflow_map` 参数——由 `_run_single` 经 `SimulationEnv` 链路传入 |<!-- REVIEW-R1-FIX: ISSUE-004 -->
| `service/batch_simulator.py` | **修改** | 构造 `Reward` 不再传 bonus 字段；`SimulationEnv` 新增 `card_overflow_map` 字段（默认值 `{}`——保证 `from_dict()` 路径兼容）；`SimulationEnvBuilder.from_config_store()` 从 `ConfigStore.card_overflow_map` 注入 `SimulationEnv`<!-- REVIEW-R1-FIX: ISSUE-112 -->；`SimulationEnvBuilder.from_dict()` 增加 `card_overflow_map` 透传；`_run_single()` 传递给 `GachaService` 构造器 |<!-- REVIEW-R1-FIX: ISSUE-004,ISSUE-107 -->
| `config/config.toml` | **更新** | 卡片添加 `[card.overflow]` + 新增 `[rarity_defaults]` 段 |
| `gui/config_panel.py` | **修改** | E7a-1/E7a-2/E7a-3：新增「满突溢出」子标签页——稀有度级三规则编辑器 + 数据加载/写出 + 自动同步；E6c: `PoolDistEntry` 构造适配移除三个 bonus 参数 + `DistributionDialog` 清理移除额外资源列/函数 |<!-- REVIEW-R1-FIX: GATE-1 + ISSUE-100,ISSUE-102 -->
| `tests/` | **新增+迁移** | E6d 测试迁移 + E8 集成测试 + GUI 冒烟；`test_pool_bonus.py` → `match_overflow_bands` 测试迁移（11 例）；`test_p60_gacha_state.py` `add_card` 断言适配 dict 返回 |<!-- REVIEW-R1-FIX: GATE-1 + ISSUE-101 -->
| `CLAUDE.md` | **更新** | 新增 `core/overflow.py` 模块说明 + `GachaState.add_card()` 溢出管道签名与用法 + `clone()` 含 `acquired_by_path` 深拷贝 + 删除 `compute_bonus_resources()` 引用 |<!-- REVIEW-R1-FIX: ISSUE-005 -->

**不受影响：** `core/pity.py`、`core/collector.py`、`core/result_types.py`、`core/gdr.py`、`core/streaming.py`、`gui/` 除 config_panel.py 外的全部面板

---

## 六、依赖关系

```
P60（已完成 ✅）
├── state.add_card()          ← E3 改造的基础
├── state.get_card_count()    ← 分段表定位用
└── state.acquired            ← 单一真相源

本计划（P63）
├── 零依赖 P55 / P56 / P58
├── 与 P55 ∥ P56 ∥ P58 完全并行——改不同文件、不同段落
├── P58 从中受益——Milestone 注入时自动获得溢出能力
└── P58 不阻塞 P63——等 P58 就绪后只需改 path 参数
```

**并行性分析：**

| | P55 | P56 | P58 | P63 |
|---|---|---|---|---|
| `pity.py` | ✅ 改 | ✅ 改 | 不改 | 不改 |
| `pool.py` | 不改 | 不改 | 不改 | ✅ 改 |
| `state.py` | 不改 | 不改 | 不改 | ✅ 改 |
| `overflow.py` | 不改 | 不改 | 不改 | ✅ 新建 |
| `config_toml.py` | 可能改 | 可能改 | ✅ 改 | ✅ 改 |
| `gacha_service.py` | 可能改 | 可能改 | ✅ 改 | ✅ 改 |

`config_toml.py` 和 `gacha_service.py` 的改动在不同段落/函数，merge 不会产生冲突。

---

## 七、风险

| 风险 | 缓解 |
|------|------|
| `add_card()` 签名变更导致调用方遗漏传参 | 新参数全为 Optional——不传则行为与现在一致（纯计数，返回 `{}`）；传 `overflow_bands` 不传 `initial_counts` 时 `ValueError` 显式检查（`assert` 在 Python `-O` 下被剥离，不可用于外部输入校验）<!-- REVIEW-R1-FIX: ISSUE-002 --> |
| 分段表配置复杂度过高 | 语法糖覆盖 99% 场景——三字段一行搞定原神/星铁/方舟；bands 数组仅高级用户手写 |
| 语法糖展开与 bands 数组行为不一致 | 解析时统一展开为 bands 内部表示；同一卡片两种写法展开结果必须等价；单元测试覆盖 |
| `Reward` 移除三个字段后旧序列化兼容 | 这三个字段从未在 TOML 中被正确填充（F1 断裂），移除零影响 |
| 稀有度默认与卡片规则优先级歧义 | 解析时明确：卡片显式配置 > 稀有度默认；卡片未配任何 overflow 段才 fallback |
| `card_overflow_map` 构建时 card_defs 中的 dict/dataclass 不一致 | `_build_card_overflow_map(store)` 在 `load_toml()` 末尾——`_backfill_card_pools()` 之后调用<!-- REVIEW-R1-FIX: ISSUE-010 -->——此时 `CardDefEntry` 已全部解析完毕，无 dict/object 混用问题 |
| `ConfigStore.clear()` 未覆盖 `rarity_defaults` 与 `card_overflow_map`——`load_toml(store=existing_store)` 先 `clear()` 再填充，未重置的新字段残留上一次加载的旧值 | E1 在 `clear()` 方法末尾增加 `self.rarity_defaults.clear()` 和 `self.card_overflow_map.clear()`，参照 `rarity_rank.clear()`（第 184 行）先例 |<!-- REVIEW-R1-FIX: ISSUE-103 -->
| `overflow_bands` 写出格式策略未决定——bands 数组 vs 语法糖三字段的二选一影响 E2a 具体代码 | 策略：默认写 bands 数组（与内部表示一致、round-trip 无损）；可选增加反向还原辅助函数——若 bands 可无损映射为三字段语法糖则写语法糖，否则写 bands。在 E2a 实施时明确选择并记录在代码注释中 |<!-- REVIEW-R1-FIX: ISSUE-108 -->
| 分段表区间不完备（留空洞） | 匹配时隐式处理——落在存储段之间直接返回 `{}`；不预存空段，避免内存膨胀 |
| 旧序列化快照反序列化失败 | `CompactResult` 不涉及新字段变更——`overflow_bands` 是 `ConfigStore` 共享查找表，`acquired_by_path` 不参与序列化；序列化风险为零 |
| `GachaState.clone()` 未拷贝 `acquired_by_path`——策略分支评估等 clone 场景下 path 记录丢失，违反「记录获得路径」核心目标（第二节第 3 条）。虽 MVP 不做路径过滤不会导致功能错误，但记录准确性受损 | E3 同步修改 `clone()` 增加 `acquired_by_path` 深拷贝：`{cid: dict(paths) for cid, paths in self.acquired_by_path.items()}`。测试 `test_clone_copies_acquired` 扩展为验证 clone 对象的 acquired_by_path 独立于原对象 |<!-- REVIEW-R1-FIX: ISSUE-105 -->
| TOML save 时 `_distribution_matches_template()` 判等不比较 `resources_gained`——含该字段的分布被误判为模板匹配，写回模板引用导致字段丢失 | E4 同步修改 `_distribution_matches_template()` 比较循环——`card_id`/`rarity`/`featured`/`probability` 四字段之外新增 `resources_gained` 的 dict 相等性判断；若分布 `resources_gained` 非空且与模板展开结果不一致，判等返回 False 写出内联分布而非模板引用 <!-- REVIEW-R1-FIX: ISSUE-003 -->
| `_save_templates_and_pools()` 内联分布写路径不写 `resources_gained`——E4 仅修复读方向，含非默认 `resources_gained` 的分布在 save 时静默丢失该字段 | E4 内联分布写路径（第 225-233 行）增加条件写入：若 `d.resources_gained` 非空则写入 `resources_gained` 字段，与 E4 的读修复形成双向对称 |<!-- REVIEW-R1-FIX: ISSUE-106 -->
| `"inf"` 字符串解析与整数区间不一致 | 解析时统一：`"inf"` → `None`，整数保持 `int`；`match_overflow_bands` 中 `max is None` → 恒通过上限检查 |
| E4 修改 `_distribution_matches_template()` 新增 `resources_gained` 比较后——分布含非默认 `resources_gained` 将不再匹配模板，写为内联数组。已有 config.toml 中如存在 GUI 手动添加的 `resources_gained`（虽因管道断裂此前 load 时丢失），升级后面临格式变化 | 影响极小（该字段无实证用例至今管道断裂），但应记录。验收时确认：`grep config.toml` 中 `distribution_templates` 段落含 `resources_gained` 的条目——如有则升级后分布将转为内联数组 |<!-- REVIEW-R1-FIX: ISSUE-109 -->
| `card_overflow_map` 数据流链路断裂——`SimulationEnv`/`SimulationEnvBuilder`/`_run_single` 未传递 `card_overflow_map` 至 `GachaService` | E5 覆盖完整链路：`ConfigStore.card_overflow_map` → `SimulationEnvBuilder.from_config_store()` 注入 `SimulationEnv`<!-- REVIEW-R1-FIX: ISSUE-112 --> → `_run_single()` 传递 → `GachaService.__init__` 接受参数。四环节任一遗漏将导致 `GachaService` 抽卡循环中 `card_overflow_map.get(reward.id)` 为 `None` 或 `AttributeError` |<!-- REVIEW-R1-FIX: ISSUE-004 -->
| `SimulationEnvBuilder.from_dict()` 不含 `card_overflow_map`——`worst_impact.py` 等使用 from_dict 路径的调用方缺少该字段 | `SimulationEnv.card_overflow_map` 设置默认值 `{}` 保证兼容性；`from_dict()` 增加 `card_overflow_map=config.get('card_overflow_map', {})` 透传。若保持默认值 `{}`，worst_impact.py 场景下溢出管道静默不生效（无功能性损坏但无溢出行为） |<!-- REVIEW-R1-FIX: ISSUE-107 -->
| `save_toml()` 卡片序列化不写 `overflow_bands`——GUI 保存时静默丢弃手写卡片级溢出配置 | E2a 在 `save_toml()` 卡片循环中增加 `overflow_bands` 序列化：若非空，写入 `[card.overflow_bands]` TOML 数组，与解析路径双向对称；另见 `save_toml()` 测试验证 round-trip 无损 |<!-- REVIEW-R1-FIX: ISSUE-006 -->
| `save_toml()` 不写 `[rarity_defaults]` 段——GUI E7a 编辑器改动在保存时丢失，重启后复原；load→save→load 往返测试中数据静默丢失 | E2a 新增 `rarity_defaults` 段序列化：遍历 `store.rarity_defaults`，将每个稀有度的 `overflow_bands` 数组写出为 TOML 数组表格式（与解析语法对称），参照 `rarities.ranks`（第 151-160 行）的双向实现模式 |<!-- REVIEW-R1-FIX: ISSUE-104 -->

---

## 7.A 回滚策略（<!-- REVIEW-R1-FIX: GATE-5-回滚路径 -->）

### 回滚原则

每个阶段一个独立 commit（`feat: P63 E<N> <描述>`），回滚粒度 = 单个 commit。子阶段（E6a-d、E7a-1/2/3）亦各自独立 commit——子阶段拆分（GATE-1）消除了 E6 的「8 项改动一 commit」问题，使每个子阶段可独立 revert。

**级联原则：** 若回滚的 stage 有下游 stage 依赖其产出，则下游 stage 也需 revert。级联规则：

| 回滚阶段 | 级联退避 | 理由 |
|----------|---------|------|
| E2（TOML 解析变更） | E1（新增字段）**不必**退——`CardDefEntry.overflow_bands` 字段新增本身不引入逻辑变更，仅在 E2 解析后才有值 | 字段新增是纯 schema 扩展 |
| E2a（TOML save 变更） | E2 **不必**退——save 与 load 独立函数，E2 的 `_build_cards` 解析不受 E2a 影响 | save/load 路径独立 |
| E6a（删除 compute_bonus_resources） | E5（gacha_service 改造）**必须**退——E5 已将调用方改为 `state.add_card()`，E6a 删除后若 E5 不退则 E5 commit 中 `from pool import compute_bonus_resources` 将 ImportError | E5 依赖 E6a 建立的新事实（函数已无调用方） |
| E6b（移除字段） | E6a **必须**退——E6b 移除的字段是 E6a 删除的函数引用的，E6a 先退不然 E6b 的字段成为无引用死字段但保留在代码中 | 防止僵尸字段 |
| E7a-1（GUI 骨架） | 无下游依赖——E7a-2/E7a-3 均在同一个 `config_panel.py` 文件中，revert E7a-1 时 E7a-2/E7a-3 的数据绑定和展开逻辑代码在文件中成为死代码，**建议一起退**以保持文件整洁 | 同文件级联 |
| E7a-2（数据绑定） | E7a-3（展开逻辑）**不必**退——展开逻辑写入 `rarity_defaults` 的格式是标准 `overflow_bands` 数组，数据绑定读取同一个数据结构，互不影响 | 读/写互不依赖 |

### 逐阶段回滚验证

每个阶段 revert 后的验证命令和预期结果：

| 回滚阶段 | 验证命令 | 预期（回到基线） |
|----------|---------|-----------------|
| E0 | `python -c "from gacha_simulator.core.overflow import OverflowBand; print(OverflowBand(1,None,{}))"` 报 ImportError | 确认 overflow.py 文件不存在 |
| E1 | `python -c "from gacha_simulator.core.config_store import ConfigStore; s=ConfigStore(); assert not hasattr(s, 'card_overflow_map')"` | card_overflow_map 属性不存在 |
| E2 | `python -c "from gacha_simulator.core.config_toml import load_toml; s=load_toml('config/config.toml'); print(type(s.card_defs[0].overflow_bands))"` 输出 `<class 'NoneType'>` | CardDefEntry 无 overflow_bands 解析值 |
| E2a | 修改 config.toml 中某卡片添加 `overflow_bands` → 执行 `load_toml` + `save_toml` → diff 确认段被丢弃 | save_toml 不写 overflow_bands |
| E3 | `pytest tests/test_p60_gacha_state.py -v` 中 `test_add_card_increments` 断言 `== int`（而非 dict）| `add_card()` 不改签名 |
| E4 | `python -c "from gacha_simulator.core.config_toml import load_toml; s=load_toml('config/config.toml'); d=s.pools[0].distribution[0]; print(d.resources_gained)"` 输出 `{}` | resources_gained 不解析 |
| E5 | `grep 'compute_bonus_resources' gacha_simulator/service/gacha_service.py` 有结果 | 旧 import 仍在 |
| E6a | `pytest tests/core/test_pool_bonus.py -v` 全部 11 例通过 | 旧测试仍有效 |
| E6b | `grep 'first_time_bonus\|nth_time_bonus\|excess_bonus' gacha_simulator/core/pool.py` 有结果 | 三字段仍在 Reward |
| E6c | 启动 GUI → 打开「分布模板」编辑器 → 「额外资源」列可见 | DistributionDialog 未清理 |
| E6d | `pytest tests/test_p60_gacha_state.py::test_add_card_increments -v` 断言 `== int` | 旧断言恢复 |
| E7 | `grep 'overflow' config/config.toml` 无结果 | 配置无溢出段 |
| E7a-1/2/3 | 启动 GUI → 配置面板左侧无「满突溢出」标签页 | GUI 无新Tab |
| E8 | `pytest tests/ -k "overflow or bonus" -v` 无匹配测试 | 集成测试不存在 |

### 破坏性阶段的紧急恢复流程

**E2（TOML 解析）加载失败场景：**

若 E2 引入的 `_build_cards()` 解析逻辑在已有 `config.toml` 上报 `ConfigError` 阻断加载：

1. `git revert <E2-commit>`（单 commit，E1 不退）
2. 运行 `pytest tests/core/test_config_toml.py -v` 确认加载正常
3. 运行 `python -m gacha_simulator.cli -n 100` 确认 CLI 可用
4. 修复后在 E2 解析逻辑中增加 try/except 容错——语法糖展开失败时退化为空 bands + 日志警告，不阻断加载

**E6（破坏性阶段）行为偏差场景：**

若 E8 集成测试发现溢出资源结果与预期偏差：

1. 从 E5 revert（E5→E6a→E6b→E6c→E6d 级联退避，共 4 个 commit）
2. 运行基线测试确认：
   ```bash
   # 确认 compute_bonus_resources 仍可用
   pytest tests/core/test_pool_bonus.py -v
   # 确认 add_card 签名恢复为旧版
   pytest tests/test_p60_gacha_state.py -v
   # 确认 gacha_service 使用旧 import
   pytest tests/ -k "integration" -v
   ```
3. 从 E5 开始重建——不单独挑出 E6 中的某一子阶段热修复
4. 修复后在 E6a 引入新测试验证等价性（见 GATE-6 补充测试）

**E7a（GUI）展示/写入 bug 场景：**

若 GUI 展开逻辑或键名规范化有 bug——发布 hotfix 而非 revert 整个 E7a：

1. 确认 bug 所属子阶段（数据绑定 E7a-2 / 展开逻辑 E7a-3）
2. 若为 E7a-3 展开逻辑 bug——仅修复该子阶段，E7a-1 和 E7a-2 保持
3. 若为 E7a-2 键名规范化 bug——直接修复 `.lower()` 调用，加单元测试
4. 若 bug 涉及多个子阶段交叉——revert 整个 E7a-1/2/3（3 commits），因三个 commit 在同一个文件中交互

---

## 八、验收标准

### A. 数据结构与解析（E0/E1/E2/E2a）

- [ ] `OverflowBand` dataclass 正确建模分段表区间 `{min, max: int|None, resources}`，`None` = 无穷
- [ ] `core/overflow.py` 独立文件——dataclass + `match_overflow_bands()` + `expand_sugar_to_bands()` 三者内聚
- [ ] TOML 中 `"inf"` 字符串正确解析为 `None`
- [ ] 三字段语法糖 `first_time_bonus` / `nth_time_bonus` / `excess_bonus` 正确展开为 bands
- [ ] `[[card.overflow_bands]]` 数组模式正确解析
- [ ] `[rarity_defaults]` 段正确解析；卡片级配置覆盖稀有度默认
- [ ] `ConfigStore.card_overflow_map` 在 TOML 解析完成后正确填充，全系统共享

<!-- REVIEW-R1-FIX: GATE-6-测试策略 —— 分段表匹配边界用例 + 语法糖等价性验证 -->

**具体测试用例（必须覆盖）：**

`match_overflow_bands` 边界用例：

| 测试 ID | 输入 | 期望输出 | 覆盖场景 |
|---------|------|----------|---------|
| MATCH-1 | `bands=[], n=1` | `{}` | 空 bands 列表——无规则即无产出 |
| MATCH-2 | `bands=[(1,None)→{gem:40}], n=1` | `{gem:40}` | 单段恒真表 [1,∞)——星铁光锥场景 |
| MATCH-3 | `bands=[(1,None)→{gem:40}], n=5` | `{gem:40}` | 恒真表 n=5 仍命中 |
| MATCH-4 | `bands=[(1,None)→{gem:40}], n=100` | `{gem:40}` | 恒真表 n=100 仍命中 |
| MATCH-5 | `bands=[(1,1)→{A:10}, (2,7)→{B:10}, (8,None)→{C:25}], n=3` | `{B:10}` | 常规三段表中段命中 |
| MATCH-6 | `bands=[(1,1)→{A:10}, (8,None)→{C:25}], n=3` | `{}` | 区间不完备——[2,7] 无段，落在间隙 |
| MATCH-7 | `bands=[(8,None)→{C:25}, (1,1)→{A:10}], n=1` | `{A:10}` | bands 乱序——验证匹配逻辑不依赖输入顺序 |
| MATCH-8 | `bands=[(1,2)→{A:10}, (3,3)→{B:20}], n=2` | `{A:10}` | n=2 命中 [1,2] 上界 |
| MATCH-9 | `bands=[(1,2)→{A:10}, (3,3)→{B:20}], n=3` | `{B:20}` | n=3 命中 [3,3] 精确单点 |
| MATCH-10 | `bands=[(1,5)→{A:10}], n=6` | `{}` | n=6 超出最后一个段且该段非无穷——落在间隙 |

语法糖展开等价性验证：

| 测试 ID | 语法糖输入 | 期望 bands 输出 | 覆盖场景 |
|---------|-----------|----------------|---------|
| SUGAR-1 | `first={gem:10}` | `[(1,1)→{gem:10}]` | 仅首次获得 |
| SUGAR-2 | `excess={threshold:7, resources:{star:25}}` | `[(7,None)→{star:25}]` | 仅满突后 |
| SUGAR-3 | `nth={3:{token:20}}` | `[(3,3)→{token:20}]` | 仅第 N 次 |
| SUGAR-4 | `first={A:10} + excess={thr:7, res:{A:25}}` | `[(1,1)→{A:10}, (7,None)→{A:25}]` | 首次+满突（中间 [2,6] 不存空段） |
| SUGAR-5 | 语法糖展开结果 vs 手写 `[[card.overflow_bands]]` 同一卡片 | `expand_sugar_to_bands()` 结果与手写 bands 数组逐字段相等（min/max/resources 全部匹配） | 等价性——bitwise 对比 |

语法糖 + bands 共存优先级：

| 测试 ID | 输入 | 期望 | 覆盖场景 |
|---------|------|------|---------|
| PRIO-1 | 同一卡片同时配 `[card.overflow]` 语法糖 + `[[card.overflow_bands]]` | 使用 bands 数组，忽略语法糖 | §3.3③——配了 bands 则忽略语法糖 |
| PRIO-2 | 卡片未配任何 overflow 段 → fallback `rarity_defaults[card.rarity.lower()]` | 使用稀有度默认 bands | 卡片 > 稀有度默认优先级 |
| PRIO-3 | 卡片未配 overflow + 对应稀有度默认也未配 | `card_overflow_map` 不含该 card_id；`add_card` 返回 `{}` | 全空——无溢出规则 |

### B. add_card 溢出管道（E3/E5）

- [ ] `state.add_card()` 不传 overflow_bands 时行为不变（纯计数，返回 `{}`）
- [ ] `state.add_card()` 传 overflow_bands 时正确返回溢出资源，`acquired_by_path` 正确记录路径
- [ ] `state.add_card()` 返回的溢出资源被合并到 `rg`
- [ ] `total_gained` / `final_resources` 无重复累加——每笔资源只入账一次
- [ ] 批次内溢出资源立即可用于下一发

<!-- REVIEW-R1-FIX: GATE-6-测试策略 —— 溢出管道端到端具体数值期望 -->

**具体测试用例（必须覆盖）：**

| 测试 ID | 场景 | 输入 | 期望输出 | 覆盖 |
|---------|------|------|----------|------|
| PIPE-1 | 卡 X 首次获得 first_time_bonus | `overflow_bands=[(1,1)→{gem:10}]`，`add_card("X")` × 1 | 返回 `{gem:10}` | 首次获得 |
| PIPE-2 | 卡 X 第 2 次获得无产出 | 同上 bands，`add_card("X")` × 2 | 第 2 次返回 `{}`（间隙） | 中间段无产出 |
| PIPE-3 | 卡 X 第 7 次触发 excess | `overflow_bands=[(1,1)→{gem:10},(7,None)→{star:25}]`，`add_card("X")` × 7，initial_counts 含 `"X":0` | 第 7 次返回 `{star:25}` | excess_bonus threshold=7 |
| PIPE-4 | 含 initial_counts=3 时首次模拟获得 | `overflow_bands=[(1,1)→{gem:10},(2,None)→{star:5}]`，`initial_counts={"X":3}`，`add_card("X")` × 1 | total_holding=4，命中 [2,None)→`{star:5}` | initial_counts 正确参与定位——不误判为首次 |
| PIPE-5 | 不传 initial_counts + 传 overflow_bands | `add_card("X", overflow_bands=[...])` 未传 initial_counts | 抛出 `ValueError`（非 assert——Python -O 下不剥离） | §3.4 防御性校验 |
| PIPE-6 | `acquired_by_path` 记录 | `add_card("X", path="draw")` × 2，`add_card("X", path="milestone_gift")` × 1 | `state.acquired_by_path["X"] == {"draw":2, "milestone_gift":1}` | 路径切片正确累加 |
| PIPE-7 | 不传 overflow_bands（向后兼容） | `add_card("X")` 无任何可选参数 | 返回 `{}`，`acquired["X"] += 1`，`acquired_by_path["X"]["unknown"] += 1` | 旧调用方零改动 |

### C. 回归验证（E4/E5/E6a-E6d）

- [ ] TOML 中 `resources_gained` 正确解析到 `PoolDistEntry`（分布模板 + 内联分布）
- [ ] `gacha_service` 抽卡循环简化后，资源产出与改动前一致
- [ ] `compute_bonus_resources()` 已删除；旧测试（11 例，`test_pool_bonus.py`）迁移为 `match_overflow_bands` 测试
- [ ] `Reward` 不再包含 `first_time_bonus` / `nth_time_bonus` / `excess_bonus`
- [ ] `PoolDistEntry` 不再包含三个 bonus 字段
- [ ] 空配置（无任何 overflow 段）时系统行为完全不变

<!-- REVIEW-R1-FIX: GATE-6-测试策略 —— 端到端回归具体数值期望 + 判定方式 -->

**具体回归测试用例（必须覆盖）：**

| 测试 ID | 场景 | 方法 | 期望 |
|---------|------|------|------|
| REG-1 | 使用现有 `config.toml`（无 overflow 段）运行相同 seed 的 1000 次模拟 | 对比 E6d 前后的 `CompactResult` | `total_gained` 和 `final_resources` 完全一致（dict 逐键逐值相等） |
| REG-2 | `config.toml` 中池子分布含 `resources_gained` 字段——修复 E4 管道后首次生效 | `load_toml` → 检查 `PoolDistEntry.resources_gained` | 非空值时，该值正确累计到 `total_gained`；不重复入账（不会既走 `resources_gained` 又走溢出管道为同一笔资源记两次） |
| REG-3 | 旧 `test_pool_bonus.py` 11 个测试全部迁移 | 新测试位于 `tests/core/test_overflow.py`，`pytest -v` | 11 例全部通过（语义等价——行为未变，API 变了：`match_overflow_bands(bands,n)` 替代 `compute_bonus_resources(reward,before,after)`） |
| REG-4 | `test_p60_gacha_state.py::test_add_card_increments` 断言适配 | `assert state.add_card("diluc") == {}` 和 `assert state.add_card("diluc", overflow_bands=...) == {...}` | dict 返回（非 int）+ 带 bands 参数返回正确溢出资源 |

**「空配置行为完全不变」判定方式：**
- 使用现有 `config.toml`（确认 `grep -E "overflow|rarity_defaults"` 无结果）
- `seed=42, n=1000`，E5 前后各跑一次
- 对比 `CompactResult.to_dict()` 的 `total_gained` / `final_resources` / `total_draws` 三个顶层 key
- 判定标准：所有 key 逐值相等（dict 深度比较），不允许 ±1 浮点偏差

### D. Milestone 接口（E3/E5 预留——待 P58）

- [ ] [P63 接口] `state.add_card()` 接受 `path=milestone_gift` 参数，溢出管道接口就绪；单元测试用模拟 Milestone 调用验证 <!-- REVIEW-R1-FIX: ISSUE-001 —— P63 侧接口可独立验证，端到端行为待 P58 完成后验证 -->
- [ ] [P58 联动] Milestone (P58) 注入的卡以 `path=milestone_gift` 进入 `add_card()`，正确触发溢出 ⚠ 待 P58 完成后验证 <!-- REVIEW-R1-FIX: ISSUE-001 -->

### E. GUI「满突溢出」标签页（E7a-1/E7a-2/E7a-3）

- [ ] GUI「满突溢出」标签页正确注册到配置面板左侧（第 7 个 Tab）
- [ ] 稀有度列表从 `[rarities].ranks` 动态解析；无配置时回退 SSR / SR / R 三级
- [ ] 三组产出编辑器（键值对子表）正确读写：首次获得 / 满突前 / 满突后
- [ ] 满突张数 + 产出 → 正确展开为分段表写入 `ConfigStore.rarity_defaults`（四种组合均覆盖）
- [ ] GUI 变更实时写回 `ConfigStore`（P56 自动应用模式），关闭/切换 Tab 不丢失

<!-- REVIEW-R1-FIX: GATE-6-测试策略 —— GUI 交互场景 + 边界用例 -->

**具体 GUI 测试用例（必须覆盖）：**

| 测试 ID | 场景 | 操作 | 期望 |
|---------|------|------|------|
| GUI-1 | 切换稀有度行后数据保持 | 编辑 SSR 行 first_time = `{gem:10}` → 点击 SR 行 → 回到 SSR 行 | first_time 仍显示 `{gem:10}` |
| GUI-2 | 空值处理 | 某稀有度全部产出字段留空 → 保存 | 该稀有度在 `rarity_defaults` 中不存在或 `overflow_bands` 为空列表 |
| GUI-3 | 非法输入防御——负数 | 产出编辑器中输入 `gem: -5` | 拒绝写入或截断为 0（需确定 UI 行为——建议红色边框标记 + 不写入 store） |
| GUI-4 | 非法输入防御——非数值 | 产出编辑器中输入 `gem: abc` | 拒绝写入，保持旧值 |
| GUI-5 | 关闭/切换 Tab 不丢失 | 编辑后切换到「权重配置」Tab → 切回「满突溢出」 | 数据完整保留（实时写回 store 而非「应用」按钮后写回） |
| GUI-6 | 稀有度列表动态解析 | 配置 `[rarities].ranks = [["UR"], ["SSR"], ["SR"]]` | 表格显示 UR / SSR / SR 三行（非默认 SSR/SR/R） |

### F. 全局

- [ ] pytest 全量通过


## 📋 审查记录

<details>
<summary>2026-07-28 —— P38 plan-review（R2-fixed ✅ 通过）</summary>

- **复杂度**: complex | **变更性质**: evolutionary
- **阶段 1 影响面**: 5 维度并行扫描，21 条发现
- **阶段 2 对抗循环**: 6 轮 Find→Fix→Verify，25 个 ISSUE 全部 PASS（收敛）
- **阶段 3 门控**: 6 项检查（3 PASS / 1 NEEDS_SPLIT / 2 NEEDS_CLARIFY → 已修复）
- **阶段 4 代码审计**: 已执行，3 个 GATE 问题修复（变更粒度拆分 + 回滚策略 + 35 个测试用例）
- **阶段 5 矩阵同步**: 已执行
- **累计修复**: 28 项（虚构符号名×2 / 遗漏波及×6 / 边界覆盖×5 / 逻辑闭合×3 / 文档错误×2 / GATE修复×3 / 对抗循环×7）
- **结论**: ✅ 通过，建议实施。无遗留阻塞项。

</details>

