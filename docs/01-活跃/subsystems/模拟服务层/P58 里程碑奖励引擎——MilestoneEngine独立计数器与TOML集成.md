<!-- META: P58 | module:模拟服务层 | status:designing | last:2026-07-29 | depends:P60✅,P63✅ -->

# P58 累抽奖励引擎——独立 MilestoneEngine 实现

> 日期：2026-06-19 | 更新：2026-07-29 | 状态：设计中（P63 已实施，接口已收敛）
> **2026-06-20 架构决策：** milestone 不作为保底 type 实现——独立 `MilestoneEngine` + `[[milestone]]` TOML 段。理由：milestone 不操作概率、不参与 PityEngine 管道、语义与「保底」（运气保护）正交。独立方案代码量不增反减（~97 vs ~110 行），且零侵入 PityEngine / BEHAVIOR_REGISTRY。
> **2026-07-29 UI 审查修正：** ConfigPanel 右侧仅为全局 `preview_text` QLabel——无独立 TOML 预览区。Tab 命名「累抽奖励」（玩家社区有机术语，NGA/贴吧通用，语义精准：累计抽取→赠送）。P58 信号连接复用已有 `_update_preview()` 全局方法，仅在 `_do_update_preview()` 追加累抽摘要段。

---

## 一、问题

### 1.1 G20 缺口全景

手册基建补丁优先级 #1——当前所有 pity type 默认「替换」语义（保底触发时**覆盖**概率分布，吞掉正常抽卡产出），大量游戏需要「追加」语义（在正常产出之上**额外注入**，不吞正常产出）：

| # | 游戏 | 场景 | 触发方式 | 赠送内容 | 当前近似 |
|---|------|------|---------|---------|---------|
| 1 | 火影忍者 | 每 10 抽保底碎片 | `every=10` | 1 片 S/A 碎片 | `hard` 替换语义——**吞卡** |
| 2 | 火影忍者 | 50 抽大保底碎片 | `every=50` | 5 片 S 碎片 | `hard` 替换语义——**吞卡** |
| 3 | 火影忍者 | 首付返利 | `at=100`(S忍) / `at=50`(A忍) | 25-38 片碎片 | 未实现 |
| 4 | 阴阳师 | 40 抽赠送随机 SSR/SP | `at=40` | 随机 SSR/SP，不计入保底 | 未实现 |
| 5 | 明日方舟 | 300 抽赠送当期限定 | `at=300` | 当期限定干员，不计井币 | 未实现 |
| 6 | 终末地 | 30 抽取送十连 | `at=30` | 1 次十连，不计保底 | 附属池 workaround |
| 7 | 终末地 | 60 抽寻访档案 | `at=60` | 10 张下期限定券 | 附属池 workaround |

~~场景 8「异环保底双黄」已于 2026-06-17 交叉验证排除——三测特征，公测移除，见手册 §20.1 更正。~~

**触发方式分类：**
- `at=N`（单次触发）：场景 3/4/5/6/7 —— 5 个
- `every=N`（周期触发）：场景 1/2 —— 2 个

**覆盖策略：** 本计划覆盖全部 7 个场景。

### 1.2 为什么 milestone 不是「保底」

| 维度 | 保底 (Pity) | 里程碑 (Milestone) |
|------|------------|-------------------|
| **设计意图** | 运气保护——N 抽不出货→强制给 | 抽数奖励——抽满 N 抽→额外赠送 |
| **概率操作** | 修改概率分布（soft 累加、hard 覆盖） | **永远不碰概率** |
| **计数对象** | 「不出目标稀有度」的抽数 | **所有抽数**——无论出什么 |
| **重置条件** | 出了目标稀有度 | 自身触发后（repeat）或永久停用（at） |
| **产出位置** | 通过 `pool.draw()` 正常产出 | **旁路注入**，不走抽卡管线 |
| **副产物** | 照常计算（星辉/井币等） | 通过 P63 统一 `state.add_card(path="milestone_gift", overflow_bands=...)` 管道产生——与正常抽卡一致（P63 已实施 ✅） |
| **生命周期参数** | `reset` / `scope` / `target_featured` / `deactivate_on_early_hit` / `depends_on` | 均不需要——milestone 的计数器逻辑自包含 |

唯一共同点是「计数」。但保底计数是为了「累计未出目标稀有度的抽数」，milestone 计数是为了「累计所有抽数」——语义不同。

**架构决策（2026-06-20）：** milestone 不作为 `type = "milestone"` 寄生在 PityEngine 管道中。理由：

1. `MilestoneBehavior._compute_probabilities()` 永远是 no-op（透传）——违反 LSP
2. `gacha_service` 需要 `isinstance(bh, MilestoneBehavior)` 来区分「真保底」和「伪保底」——代码坏味道
3. 独立方案代码量更少（~97 vs ~110 行）
4. 独立方案零侵入 PityEngine / BEHAVIOR_REGISTRY——与 P55/P56 真正并行

---

## 二、目标

- 新增 `core/milestone.py` —— `MilestoneEngine` 独立调度器
- `[[milestone]]` 独立 TOML 配置段——与 `[[pity]]` 平级
- 计数器自管（极简 `int` 递增，不依赖 `CounterBasedBehavior`）
- 达阈值后返回 bonus 信号 → `state.add_card()` / `state.gain()`（P60 提供）
- `collector.on_bonus()` 区分「抽得」和「赠得」
- 覆盖 `at=N` + `every=N` 全部 7 个计数器驱动场景

### 非目标

- 事件驱动型赠送（异环保底双黄、幻塔歪后铸金）——依赖 P56 `RotatingBehavior` + `did_fire()`
- 赠送走 `Pool.draw()` 管线——不走。bonus 是直入库存
- 合并 `resources` 和 `acquired` 为统一 inventory——已决议不合并
- **寄生 PityEngine 管道**——已排除
- `MilestoneEngine.reset()`——MVP 不提供计数器重置 API。策略分支探索中如需重置里程碑状态，在后续计划中追加

---

## 三、方案

### 3.1 架构总览

```
gacha_service 模拟循环
│
├─ PityEngine.before_draw → [soft → hard]           ← milestone 不参与
├─ pool.draw()
├─ PityEngine.after_draw → [soft → hard]            ← milestone 不参与
│
├─ MilestoneEngine.after_draw(pool_id) → [bonus...]  ← 独立判定、独立注入
│   ├─ 计数器递增（自管，极简 int）
│   ├─ 达阈值 → 解析 bonus_reward
│   ├─ state.add_card() / state.gain()
│   └─ collector.on_bonus()
│
├─ 资源结算（正常产出溢出 + milestone 卡片溢出 + milestone 直接资源，统一经 P63 add_card 管道归入 rg）
└─ collector.on_draw()
```

**关键约束：**
- MilestoneEngine 不触碰概率分布
- MilestoneEngine 不依赖 PityState——计数器自管
- bonus 注入发生在 PityEngine.after_draw() 之后、资源结算之前
- collector.on_bonus() 独立于 on_draw()——元数据（事件名、时间戳、赠送内容）走 on_bonus，资源金额统一走 `combined_gained`（P63 单通道约束）
- milestone 注入的卡牌通过 P63 统一 `state.add_card(card_id, path="milestone_gift", overflow_bands=card_overflow_map.get(card_id), initial_counts=...)` 管道触发溢出——与正常抽卡一致。P58 自身不实现溢出逻辑，由 P63 的 `match_overflow_bands()` 提供
- **GDR 始终包含里程碑奖励。** 里程碑是池子的固有属性——抽 A 池 40 发实打实多一张 SSR，GDR 如实反映。不提供排除开关：需要裸概率时删 `[[milestone]]` 段重跑即可

### 3.2 MilestoneEngine 实现

```python
# core/milestone.py (~55 行)

from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Dict, List, Optional
import random


class MilestoneEngine:
    """里程碑奖励引擎——独立于 PityEngine。

    职责：计数器管理、触发判定、奖励解析。
    不参与概率管道——在 pool.draw() 之后独立调用。
    不持有 GachaState——只返回 bonus dict，状态变更由 gacha_service 负责。
    """

    def __init__(self, defs: List['MilestoneDef'], seed: int = 42):
        self._defs = {d.name: d for d in defs}
        # 计数器自管——不依赖 PityState，也不持有 GachaState
        self._counters: Dict[str, int] = {}
        self._active: Dict[str, bool] = {d.name: True for d in defs}
        self._triggered: Dict[str, int] = {d.name: 0 for d in defs}
        # 独立 RNG——保证可复现性
        self._rng = random.Random(seed)

    def after_draw(self, pool_id: str) -> List[dict]:
        """判定并返回触发的 bonus 列表。

        调用方（gacha_service）负责消费 bonus：
          - card 类型 → state.add_card(cid, path="milestone_gift",
              overflow_bands=card_overflow_map.get(cid),
              initial_counts=_initial_counts)
          - resource 类型 → state.gain(resource_id, amount)
          - collector.on_bonus(...)
        """
        bonuses: List[dict] = []
        for name, md in self._defs.items():
            if not self._active[name]:
                continue
            if md.pools and not any(fnmatch(pool_id, pat) for pat in md.pools):
                continue

            c = self._counters.get(name, 0) + 1
            self._counters[name] = c

            if c < md.threshold:
                continue

            # ── 触发！解析 bonus ──
            bonus = self._resolve_bonus(md)
            bonuses.append({'name': name, 'bonus': bonus})

            # ── 生命周期管理 ──
            if md.repeat:
                self._counters[name] = 0        # every=N：重置继续
            else:
                self._active[name] = False       # at=N：永久停用

            self._triggered[name] += 1
            if md.max_triggers and self._triggered[name] >= md.max_triggers:
                self._active[name] = False

        return bonuses

    def _resolve_bonus(self, md: 'MilestoneDef') -> dict:
        """解析 bonus_reward——cards / resources / random_cards 可任意组合。

        返回 {'card_ids': [...], 'resources': {...}}——调用方同时消费两者。
        """
        br = md.bonus_reward
        result: dict = {'card_ids': list(br.get('cards', [])),
                        'resources': dict(br.get('resources', {}))}

        # 随机卡——从候选池中抽取（使用 self._rng 保证可复现）
        for rc in br.get('random_cards', []):
            candidates = rc['candidates']
            weights = rc.get('weights', [1.0] * len(candidates))
            count = rc.get('count', 1)
            chosen = self._rng.choices(candidates, weights=weights, k=count)
            result['card_ids'].extend(chosen)

        return result

    # ── 查询接口（供策略层消费） ──

    def get_counter(self, name: str) -> int:
        """距离下一里程碑还差几抽。"""
        return self._counters.get(name, 0)

    def is_active(self, name: str) -> bool:
        """该里程碑是否仍在生效。"""
        return self._active.get(name, False)

    def get_trigger_count(self, name: str) -> int:
        """已触发次数。"""
        return self._triggered.get(name, 0)

    def get_def(self, name: str) -> Optional['MilestoneDef']:
        """返回里程碑定义——策略可据此查看 threshold / bonus_reward。"""
        return self._defs.get(name)

    def get_all_defs(self) -> Dict[str, 'MilestoneDef']:
        """返回全部里程碑定义。"""
        return dict(self._defs)
```

~55 行。计数器管理逻辑极简——`int` 自增 + `if c >= threshold`，不需要 `CounterBasedBehavior` 的抽象层级。

**2026-07-29 修订：**
- `__init__` 新增 `seed` 参数（默认 42），`_rng = random.Random(seed)` 替换原来的裸 `import random` + `random.choices()`——保证随机卡抽取可复现。
- `state` 参数移除——引擎不持有 `GachaState`，状态变更由 `gacha_service` 负责。
- **延迟构造策略：** `SimulationEnv` 只存储 `MilestoneConfig`（`List[MilestoneDef]`），`MilestoneEngine` 在 `_run_single` 中以 per-simulation `seed` 构造——保证每次模拟独立可复现。构造开销可忽略（遍历几十条 def 构建 dict）。

**同抽多触发顺序：** `after_draw()` 按 `self._defs` 的迭代顺序判定——Python 3.7+ dict 保证插入顺序，TOML `[[milestone]]` 数组保证定义顺序，因此触发顺序是**确定性的**（按 TOML 中定义顺序）。M8 集成测试应覆盖同抽触发多个 milestone 的场景。

### 3.3 数据结构 (`config_store.py`)

```python
@dataclass
class MilestoneDef:
    """单条里程碑定义——从 TOML [[milestone]] 解析。"""
    name: str                                   # 唯一标识
    threshold: int = 40                         # 触发阈值（抽数）
    repeat: bool = False                        # False=at:N 一次性 / True=every:N 周期
    max_triggers: int = 0                       # 最大触发次数（0=无限触发）
    bonus_reward: dict = field(default_factory=dict)
    pools: List[str] = field(default_factory=list)  # 作用池子（空=全部；支持 fnmatch 通配符，如 "limited_*"）


@dataclass
class MilestoneConfig:
    """里程碑配置容器。"""
    enabled: bool = True
    milestones: List[MilestoneDef] = field(default_factory=list)
```

`ConfigStore` 新增字段：

```python
milestone: MilestoneConfig = field(default_factory=MilestoneConfig)
```

**2026-07-29 修订：**
- `pools` 从 `str` 改为 `List[str]`——解决原来字符串 `in` 子串误匹配问题（`"ak_limited" in "onmyoji_limited"` → True）。空列表 = 全部池子，非空 = 精确匹配。
- `max_triggers` 默认值从 `1` 改为 `0`（0=无限触发），与 TOML 示例和文档一致。
- 匹配逻辑相应调整：`if md.pools and pool_id not in md.pools: continue`。

### 3.4 TOML 配置语法

```toml
# ── 累抽奖励（独立于保底体系——不修改概率、旁路注入） ──
# bonus_reward 三字段可任意组合——cards + resources + random_cards 并行，不限 type

# at=N：40 抽赠送随机 SSR，仅一次（阴阳师）
[[milestone]]
name = "onmyoji_40_gift"
threshold = 40
repeat = false
max_triggers = 1
pools = ["onmyoji_limited"]                       # 精确匹配单池；也可用 fnmatch: "onmyoji_*"
bonus_reward = { random_cards = [
    { candidates = ["ssr_ibaraki", "ssr_shuten", "ssr_oomoji", "ssr_kaguya"],
      weights = [1.0, 1.0, 1.0, 1.0], count = 1 },
] }

# every=N：每 10 抽保底碎片，无限重复（火影忍者）
[[milestone]]
name = "naruto_fragment"
threshold = 10
repeat = true
max_triggers = 0                                 # 0 = 无限触发
pools = []                                       # 空 = 全部池子；也可写 ["*"] 等价
bonus_reward = { resources = { fragment_s = 1 } }

# every=N：每 50 抽大保底碎片（火影忍者）
[[milestone]]
name = "naruto_s_fragment"
threshold = 50
repeat = true
max_triggers = 0
pools = []
bonus_reward = { resources = { fragment_s = 5 } }

# at=N：100 抽首付返利——S 忍碎片 + 金币（火影忍者）
# cards + resources 可同时赠送
# 注：一次性里程碑推荐 repeat=false（非 repeat=true, max_triggers=1——二者外部行为等价，前者更清晰）
[[milestone]]
name = "naruto_first_payback_s"
threshold = 100
repeat = false
max_triggers = 1
pools = []
bonus_reward = { cards = ["limited_ssr_1"], resources = { coin = 500 } }

# at=N：300 抽赠送当期限定 + 补偿资源（明日方舟）
[[milestone]]
name = "ak_300_gift"
threshold = 300
repeat = false
max_triggers = 1
pools = ["ak_limited"]
bonus_reward = { cards = ["limited_operator"], resources = { exchange_currency = 300 } }

# at=N：60 抽送跨期券（终末地）
[[milestone]]
name = "endfield_archive"
threshold = 60
repeat = false
max_triggers = 1
pools = ["endfield_limited"]
bonus_reward = { resources = { endfield_next_voucher = 10 } }
```

**与 `[[pity]]` 的语法对比：**

| | `[[pity]]` | `[[milestone]]` |
|---|---|---|
| 核心参数 | `type` / `scope` / `start` / `end` | `threshold` / `repeat` |
| 概率相关 | 有（`func` / `increment` / `target_featured`） | 无——不操作概率 |
| 重置逻辑 | `reset`（出 SSR/featured/never） | 自管（触发后 repeat 决定） |
| 奖励 | 无——产出走 pool.draw() | `bonus_reward`（card / resource / random_card） |
| 池子筛选 | `fnmatch` 通配符（`pools` 字段） | `fnmatch` 通配符（`pools` 字段）——与保底一致 |
| 语义 | 「保底」——运气保护 | 「里程碑」——抽数奖励 |

### 3.5 gacha_service 集成

```python
# gacha_service.py —— 在 PityEngine.after_draw 之后、资源结算之前

# ── 保底状态更新 ──
if _pity_engine:
    _pity_engine.after_draw(pool.id, pity_state, reward.id)

# ── 【新增】里程碑判定与注入 ──
milestone_rg: dict = {}
if _milestone_engine:
    for entry in _milestone_engine.after_draw(pool.id):
        bonus = entry['bonus']
        # 直接资源——更新 state.resources + 归入 rg（P63 单通道）
        direct_res = bonus.get('resources', {})
        if direct_res:
            state.gain(direct_res)
            for k, v in direct_res.items():
                milestone_rg[k] = milestone_rg.get(k, 0) + v
        # 卡牌——经 P63 state.add_card() 统一管道，自动计算溢出
        for cid in bonus.get('card_ids', []):
            overflow = state.add_card(
                cid,
                path="milestone_gift",
                overflow_bands=self.card_overflow_map.get(cid),
                initial_counts=_initial_counts,
            )
            for k, v in overflow.items():
                milestone_rg[k] = milestone_rg.get(k, 0) + v
        collector.on_bonus(
            milestone_name=entry['name'],
            card_ids=bonus.get('card_ids', []),
            resources=bonus.get('resources', {}),
            real_time=real_time,
        )
    # milestone 溢出资源 + 直接资源 → 归入 rg（P63 单通道）
    if milestone_rg:
        for k, v in milestone_rg.items():
            rg[k] = rg.get(k, 0) + v

# ── 资源结算（正常产出溢出经 P63 add_card 已返回）──
rg = dict(reward.resources_gained or {})
# ... 后续保持不变
```

**2026-07-29 修订——匹配 P63 实际 API：**
- `state.add_card()` 签名：`(card_id, path="milestone_gift", overflow_bands=card_overflow_map.get(cid), initial_counts=_initial_counts) → Dict[str, float]`
- `card_overflow_map` 来自 `GachaService.card_overflow_map`（由 `SimulationEnvBuilder` 从 `ConfigStore.card_overflow_map` 注入）
- 不再使用计划中原假设的 `bonus_config=` kwarg——P63 统一为 `overflow_bands=` 参数 + `match_overflow_bands()` 内部匹配
- `on_bonus` 参数 `pity_name` → `milestone_name`（语义修正）

**关键时序：**

```
before_draw → PityEngine.before_draw (不含 milestone)
  → pool.draw() → 正常出卡
  → PityEngine.after_draw → 常规保底重置（hard/soft 等，不含 milestone）
  → state.add_card(reward.id, path="draw", overflow_bands=...) → 正常产出溢出（P63）
  → MilestoneEngine.after_draw → 达阈值 → 返回 bonus
  → state.add_card(cid, path="milestone_gift", overflow_bands=...) → milestone 卡片溢出（P63 统一管道）
  → state.gain() → milestone 直接资源（如有）
  → milestone 溢出 + 直接资源 → 归入 rg（P63 单通道）
  → collector.on_bonus() / collector.on_draw()
```

### 3.5a 策略层查询接口

策略需要知道「再憋几发就能触发里程碑」来做抽卡决策。

#### StrategyContext 新增字段

```python
# strategy.py —— StrategyContext 新增
@dataclass
class StrategyContext:
    # ... 现有字段不变 ...

    _milestone_engine: Optional['MilestoneEngine'] = field(default=None, repr=False)

    # ── 里程碑查询（代理 MilestoneEngine） ──

    def get_milestone_counter(self, name: str) -> int:
        """距离触发还差几抽。不存在 → 0。"""
        if self._milestone_engine is None:
            return 0
        return self._milestone_engine.get_counter(name)

    def is_milestone_active(self, name: str) -> bool:
        """该里程碑是否仍在生效（at=N 触发后停用）。"""
        if self._milestone_engine is None:
            return False
        return self._milestone_engine.is_active(name)

    def get_milestone_defs(self) -> Dict[str, 'MilestoneDef']:
        """返回全部里程碑定义——含 threshold / bonus_reward。"""
        if self._milestone_engine is None:
            return {}
        return self._milestone_engine.get_all_defs()
```

#### GachaService 传入

```python
# gacha_service.py
class GachaService:
    def __init__(self, ...,
                 milestone_engine: Optional[MilestoneEngine] = None):
        # ...
        self.milestone_engine = milestone_engine

# run_simulation 循环中构造 StrategyContext:
ctx = StrategyContext(
    # ... 现有参数 ...
    _milestone_engine=self.milestone_engine,
)
```

#### 策略使用示例

```python
# 策略 select_action 中：
for name, md in ctx.get_milestone_defs().items():
    if not ctx.is_milestone_active(name):
        continue
    remaining = md.threshold - ctx.get_milestone_counter(name)
    if remaining <= 5:
        # 即将触发——考虑继续抽而非换池
        ...
```

**设计约束：**
- 策略只读——不能通过 `StrategyContext` 修改里程碑计数器
- `get_milestone_defs()` 返回 `MilestoneDef`——策略能读到 `threshold` 和 `bonus_reward` 的完整内容（`cards` / `resources` / `random_cards`）
- 不存在里程碑配置时引擎为 `None`，所有查询返回安全默认值

### 3.6 collector 新增 `on_bonus` 事件

> **2026-07-29 注：** P63 决策明确 `on_bonus` / `bonus_events` 不在 P63 实施范围（「当前 collector.py 无此 API，由未来需求驱动实施」）。P58 需自行实现整个事件链路。

```python
# collector.py
class SimulationCollector(ABC):
    def on_bonus(self, milestone_name: str, card_ids: List[str],
                 resources: Dict[str, float], real_time: float):
        """milestone 注入事件——只存元数据（里程碑名、时间戳、赠送内容）。

        P63 单通道约束：资源金额不在这里存储——统一走 combined_gained。
        参数名用 milestone_name 而非 pity_name——语义准确。
        """

# CompactCollector
def on_bonus(self, ...):
    r = self._result
    r.bonus_events.append({
        'milestone_name': milestone_name,
        'card_ids': list(card_ids),
        'resources': dict(resources),      # 直接资源元数据（审计用，不做会计）
        'real_time': real_time,
        # 资源金额不在此存储——已通过 milestone_rg 归入 combined_gained（P63）
    })
```

`CompactResult` 新增字段：

```python
bonus_events: list = field(default_factory=list)
```

`to_dict()` / `from_dict()` 需同步更新——**此项未列入原实施阶段，需追加。**

**SharedResultCollector（流式分析）聚合策略：**
`SharedResultCollector.on_bonus()` 将 bonus 卡**直接合并**到 `card_counts`（赠卡累加至对应 card_id），资源**不重复入账**（已在 `rg` 中通过 `on_draw` 入账）。GDR 计算时自然包含里程碑产出——不区分来源。

正确性保证（逐层追踪）：
```
单抽 on_draw(card_id="ssr_a", resources_gained=rg)  ← rg 已含: 正常溢出 + milestone溢出 + milestone直接资源
     on_bonus(card_ids=["ssr_b"], resources={coin: 500})  ← 仅累加 card_counts["ssr_b"]，不动资源
```
- **不会少加：** milestone 卡通过 `on_bonus` 显式累加进 `card_counts`
- **不会多加：** 资源仅通过 `on_draw` 的 `rg` 入账（单通道），`on_bonus` 不碰资源

分析面板据此区分两类来源——但 GDR 计算时始终合并（里程碑是池子固有属性，§3.1 约束）。

#### 3.6a GDR 层合并 bonus_events

> **2026-07-29 注：** P63 未碰 GDR 层——此项完全由 P58 自行实现。

`bonus_events` 与 `card_counts` 是独立通道。GDR 计算时需要将 milestone 赠卡合并到正常产出中以正确计算出率。资源金额已通过 P63 单通道（`milestone_rg` → `combined_gained`）自动归入，无需额外合并：

```python
# generalized_drop_rate.py —— 各 compute_* 函数中

def _merge_milestone_cards(result: CompactResult) -> Dict[str, List[int]]:
    """将 bonus_events 中的卡按抽数索引合并到 card_counts。

    bonus_events 携带 real_time → 映射到对应抽数 → 追加到该抽的卡产出中。
    """
    merged: Dict[str, List[int]] = defaultdict(list)
    # 先复制正常抽卡产出
    for i, card_id in enumerate(result.card_sequence):  # 或从 card_counts 反推
        merged[card_id].append(i)

    # 合并里程碑赠卡
    for ev in result.bonus_events:
        draw_idx = result._time_to_draw_index(ev.real_time)  # 时间戳→抽数
        for cid in ev.get('card_ids', []):
            merged[cid].append(draw_idx)

    return merged
```

资源同理——`bonus_events` 中的资源在总账 `resources` 中已合并，但单抽明细需要对齐 `real_time`。

**波及：** `compute_gdr_from_compact()` / `compute_gdr_from_history()` 调用前先合并。不改函数签名——合并发生在入口。

**`real_time → draw_index` 映射方案：** 模拟结束后构建 `{draw_times[i]: i}` 字典（`CompactResult.draw_times` 已存在），O(1) 查找。`bonus_events` 数量极少（每场至多数十次），字典开销可忽略。`real_time` 来自 `gacha_service` 循环中的同一时钟，应精确匹配——KeyError 反而能暴露时钟不同步 bug。

### 3.7 TOML 解析 (`config_toml.py`)

**读取——在 `load_toml()` 中紧跟 `_build_pity` 之后调用：**

```python
def _build_milestone(data: dict, store: ConfigStore) -> None:
    """[[milestone]] → store.milestone"""
    ml_list = data.get('milestone', [])
    if not ml_list:
        store.milestone = MilestoneConfig(enabled=True)
        return

    seen_names: set = set()
    milestones = []
    for m in ml_list:
        name = m['name']
        threshold = int(m.get('threshold', 40))
        br = m.get('bonus_reward', {})

        # ── 输入校验 ──
        if name in seen_names:
            raise ConfigError(f"里程碑名称重复: '{name}'")
        seen_names.add(name)

        if threshold < 1:
            raise ConfigError(f"里程碑 '{name}' 阈值必须 ≥ 1，当前为 {threshold}")

        cards = br.get('cards', [])
        if not isinstance(cards, list):
            raise ConfigError(f"里程碑 '{name}' bonus_reward.cards 必须是数组，当前为 {type(cards).__name__}")

        resources = br.get('resources', {})
        if not isinstance(resources, dict):
            raise ConfigError(f"里程碑 '{name}' bonus_reward.resources 必须是键值对，当前为 {type(resources).__name__}")

        random_cards = br.get('random_cards', [])
        if not isinstance(random_cards, list):
            raise ConfigError(f"里程碑 '{name}' bonus_reward.random_cards 必须是数组，当前为 {type(random_cards).__name__}")
        for i, rc in enumerate(random_cards):
            candidates = rc.get('candidates', [])
            if not candidates:
                raise ConfigError(f"里程碑 '{name}' random_cards[{i}].candidates 不得为空")

        # ── pools 兼容解析（支持 fnmatch 通配符）──
        raw_pools = m.get('pools', [])
        if isinstance(raw_pools, str):
            raw_pools = [raw_pools]  # "*" → ["*"]（fnmatch 中 * 匹配全部）

        milestones.append(MilestoneDef(
            name=name,
            threshold=threshold,
            repeat=m.get('repeat', False),
            max_triggers=int(m.get('max_triggers', 0)),
            bonus_reward={
                'cards': list(cards),
                'resources': dict(resources),
                'random_cards': list(random_cards),
            },
            pools=list(raw_pools),
        ))

    store.milestone = MilestoneConfig(enabled=True, milestones=milestones)
```

**写入——在 `save_toml()` 中紧跟 `# pity` 段之后：**

```python
# milestone
if store.milestone.enabled and store.milestone.milestones:
    data['milestone'] = [
        {
            'name': m.name,
            'threshold': m.threshold,
            'repeat': m.repeat,
            'max_triggers': m.max_triggers,
            'pools': m.pools if m.pools else [],
            'bonus_reward': m.bonus_reward,
        }
        for m in store.milestone.milestones
    ]
```

### 3.8 UI 设计

#### 3.8.1 布局方案

在 `left_tabs` 中新增独立 Tab「累抽奖励」——位于「保底机制」Tab 之后。

理由：
- `[[milestone]]` 与 `[[pity]]` 是平级的顶级配置段
- 独立 Tab 语义自解释——「累抽」是玩家社区有机术语（累计抽取→赠送），玩家一眼理解
- 不与 P55/P56 的保底 UI 改造冲突

**预览机制（2026-07-29 修正）：** ConfigPanel 右侧 `right_widget` 内仅有一个全局 `QGroupBox("配置预览")` + monospace `QLabel`（`preview_text`）。所有 Tab 共享此预览区——`_do_update_preview()` 遍历各配置段统一拼接摘要文本。P58 的 6 条信号连接（`milestone_enabled.stateChanged` / `ml_name_edit.textChanged` / ... → `self._update_preview()`）触发的是 ConfigPanel 已有的 500ms 去抖全局预览方法，无需在里程碑 Tab 内创建独立的 TOML 预览区。唯一需追加的是 `_do_update_preview()` 中的 milestone 摘要段（~10 行）。

#### 3.8.2 控件映射

| 字段 | 控件 | 说明 |
|------|------|------|
| `name` | `QLineEdit` | 唯一标识 |
| `threshold` | `QSpinBox` | 触发阈值（1–9999） |
| `repeat` | `QCheckBox` | 勾选=周期重复(every:N)，不勾=一次性(at:N) |
| `max_triggers` | `QSpinBox` | 0=无限，≥1=触发 N 次后停用 |
| `pools` | `QLineEdit` | `*` = 全部池子，或逗号分隔的池子 ID 列表 |
| `bonus_reward.cards` | `QListWidget`（多选） | 从 `store.card_defs` 填充，可多选 |
| `bonus_reward.resources` | `QTableWidget`（资源+数量） | 从 `store.resource_defs` 填充，每行一个资源 + 数量 |
| `bonus_reward.random_cards` | `QTableWidget`（候选池+权重+抽取数） | 每个候选池一行：候选卡多选 + 权重 + count |

#### 3.8.3 布局逻辑

`cards` / `resources` / `random_cards` 三个区域**始终并行显示**——无 type 切换。用户可同时配置三种奖励，留空的区域不生效。

#### 3.8.4 代码结构

```python
def _setup_milestone_config(self, parent):
    """[[milestone]] 配置 UI"""
    self._milestone_defs = []

    # ── 启用开关 ──
    self.milestone_enabled = QCheckBox("启用累抽奖励")
    self.milestone_enabled.setChecked(True)
    parent.addWidget(self.milestone_enabled)

    # ── 主布局：左列表 + 右详情 ──
    main_layout = QHBoxLayout()

    # 左侧——里程碑列表 + 按钮
    left_layout = QVBoxLayout()
    self.milestone_list = QListWidget()
    self.milestone_list.currentRowChanged.connect(self._on_milestone_selected)
    left_layout.addWidget(self.milestone_list)

    btn_layout = QHBoxLayout()
    for text, slot in [("添加里程碑", self._add_milestone),
                       ("移除里程碑", self._remove_milestone),
                       ("应用修改", self._apply_milestone_edit)]:
        btn = QPushButton(text)
        btn.clicked.connect(slot)
        btn_layout.addWidget(btn)
    left_layout.addLayout(btn_layout)
    main_layout.addLayout(left_layout, 1)

    # 右侧——详情面板
    detail_group = QGroupBox("里程碑详情")
    detail_group.setEnabled(False)
    self._milestone_detail_group = detail_group
    detail_form = QFormLayout(detail_group)

    # 基础字段
    self.ml_name_edit = QLineEdit()
    detail_form.addRow("名称:", self.ml_name_edit)

    self.ml_threshold_spin = QSpinBox()
    self.ml_threshold_spin.setRange(1, 9999)
    self.ml_threshold_spin.setValue(40)
    detail_form.addRow("触发阈值(抽):", self.ml_threshold_spin)

    self.ml_repeat_check = QCheckBox("周期重复（every=N）")
    detail_form.addRow("触发模式:", self.ml_repeat_check)

    self.ml_max_triggers_spin = QSpinBox()
    self.ml_max_triggers_spin.setRange(0, 999)
    self.ml_max_triggers_spin.setValue(0)
    self.ml_max_triggers_spin.setToolTip("0 = 无限触发")
    detail_form.addRow("最大触发次数:", self.ml_max_triggers_spin)

    self.ml_pools_edit = QLineEdit()
    self.ml_pools_edit.setText("*")
    self.ml_pools_edit.setToolTip("* = 所有池子，或逗号分隔的池子 ID 列表")
    detail_form.addRow("适用池子:", self.ml_pools_edit)

    # ── bonus_reward 子面板 —— 三区域并行，无 type 切换 ──
    detail_form.addRow(QLabel(""))  # 分隔
    detail_form.addRow("── 奖励配置（可同时填写多个区域） ──", QLabel(""))

    # ── 固定卡牌 ──
    detail_form.addRow("固定赠送卡牌:", QLabel("（可多选）"))
    self.ml_cards_list = QListWidget()
    self.ml_cards_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
    self.ml_cards_list.setMaximumHeight(100)
    detail_form.addRow(self.ml_cards_list)

    # ── 资源 ──
    detail_form.addRow("赠送资源:", QLabel("（资源 → 数量）"))
    self.ml_resources_table = QTableWidget()
    self.ml_resources_table.setColumnCount(2)
    self.ml_resources_table.setHorizontalHeaderLabels(["资源", "数量"])
    header = self.ml_resources_table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    self.ml_resources_table.setColumnWidth(1, 80)
    self.ml_resources_table.setMaximumHeight(120)
    detail_form.addRow(self.ml_resources_table)

    res_btn_layout = QHBoxLayout()
    add_res_btn = QPushButton("添加资源")
    add_res_btn.clicked.connect(self._add_milestone_resource)
    remove_res_btn = QPushButton("移除资源")
    remove_res_btn.clicked.connect(self._remove_milestone_resource)
    res_btn_layout.addWidget(add_res_btn)
    res_btn_layout.addWidget(remove_res_btn)
    res_btn_layout.addStretch()
    detail_form.addRow(res_btn_layout)

    # ── 随机卡牌 ──
    detail_form.addRow("随机卡牌池:", QLabel("（候选卡 + 权重 + 抽取张数）"))
    self.ml_random_table = QTableWidget()
    self.ml_random_table.setColumnCount(3)
    self.ml_random_table.setHorizontalHeaderLabels(["候选卡", "权重", "抽取数"])
    rheader = self.ml_random_table.horizontalHeader()
    rheader.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    rheader.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    rheader.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
    self.ml_random_table.setColumnWidth(1, 60)
    self.ml_random_table.setColumnWidth(2, 60)
    self.ml_random_table.setMaximumHeight(120)
    detail_form.addRow(self.ml_random_table)

    rand_btn_layout = QHBoxLayout()
    add_rand_btn = QPushButton("添加候选")
    add_rand_btn.clicked.connect(self._add_milestone_random_card)
    remove_rand_btn = QPushButton("移除候选")
    remove_rand_btn.clicked.connect(self._remove_milestone_random_card)
    rand_btn_layout.addWidget(add_rand_btn)
    rand_btn_layout.addWidget(remove_rand_btn)
    rand_btn_layout.addStretch()
    detail_form.addRow(rand_btn_layout)

    main_layout.addWidget(detail_group, 2)
    parent.addLayout(main_layout)

    # ── 预览信号 ──
    self.milestone_enabled.stateChanged.connect(self._update_preview)
    self.ml_name_edit.textChanged.connect(self._update_preview)
    self.ml_threshold_spin.valueChanged.connect(self._update_preview)
    self.ml_repeat_check.stateChanged.connect(self._update_preview)
    self.ml_max_triggers_spin.valueChanged.connect(self._update_preview)
    self.ml_pools_edit.textChanged.connect(self._update_preview)
```

在 `_setup_ui()` 中注册 Tab（紧跟保底机制 Tab 之后）：

```python
milestone_tab_scroll = QScrollArea()
milestone_tab_scroll.verticalScrollBar().setSingleStep(15)
milestone_tab_scroll.setWidgetResizable(True)
milestone_tab_content = QWidget()
milestone_tab_layout = QVBoxLayout(milestone_tab_content)
self._setup_milestone_config(milestone_tab_layout)
milestone_tab_layout.addStretch()
milestone_tab_scroll.setWidget(milestone_tab_content)
self.left_tabs.addTab(milestone_tab_scroll, "累抽奖励")
```

---

## 四、实施阶段

| 阶段 | 内容 | 文件 | 预估行数 |
|:---:|------|------|:---:|
| M1 | `MilestoneDef` + `MilestoneConfig` dataclass + `ConfigStore` 新增 `milestone` 字段（import `OverflowBand` from P63） | `config_store.py` | ~25 |
| M2 | `_build_milestone()` 解析 + `save_toml()` 写出 `[[milestone]]` 段 | `config_toml.py` | ~35 |
| M3 | `MilestoneEngine` 实现——计数器自管 + 触发判定 + `_resolve_bonus()`（使用 `self._rng`） | `core/milestone.py` | ~55 |
| M4 | `gacha_service` 集成——`__init__` 新增 `milestone_engine` 参数 + 模拟循环中 bonus 消费 + `StrategyContext` 传入 | `gacha_service.py` | ~20 |
| M4b | `SimulationEnv` 新增 `milestone_defs` 字段；`SimulationEnvBuilder.from_config_store()` 提取配置；`_run_single` 中 `MilestoneEngine(defs, seed=seed)` 延迟构造 | `batch_simulator.py` | ~15 |
| M4a | `StrategyContext` 新增 `_milestone_engine` 字段 + 3 个查询方法 | `strategy.py` | ~20 |
| M5 | `collector.on_bonus()` + `CompactResult.bonus_events` + `to_dict()`/`from_dict()` 序列化 + `SharedResultCollector` 同步 | `collector.py` + `result_types.py` | ~25 |
| M5a | GDR 层合并 `bonus_events`——`_merge_milestone_cards()` + `real_time→draw_index` 映射 | `generalized_drop_rate.py` | ~25 |
| M7 | 配置面板 UI——独立 Tab「累抽奖励」+ 全局预览联动（复用已有 `_update_preview()`）+ 摘要段追加 | `config_panel.py` | ~100 |
| M8 | 集成测试（7 个 G20 场景的 TOML 配置 → 模拟 → 验证产出） | `tests/` | ~50 |
| **总计** | | | **~370** |

> ~~M6（`resources_gained` 解析遗漏修复）已删除——P63 已修复 TOML 管道。~~ M4b 新增——`batch_simulator.py` 的 `SimulationEnv`/`SimulationEnvBuilder` 需传递 `milestone_config`。M5 行数上调以覆盖序列化 + `SharedResultCollector`。

---

## 五、依赖关系

```
P60（已完成 ✅）
├── state.add_card(card_id, path, overflow_bands, initial_counts) → Dict[str, float]  ← M3/M4 使用
├── state.gain() / state.get_card_count() / state.total_holding()
├── is_limited()                                                                ← M2 可选校验
└── [rarities]                                                                  ← 不依赖（milestone 不操作概率）

P63（已完成 ✅ —— 2026-07-29）
├── OverflowBand dataclass + match_overflow_bands() + expand_sugar_to_bands()    ← M4 使用
├── ConfigStore.card_overflow_map: Dict[str, List[OverflowBand]]                ← M4 使用
├── state.acquired_by_path（路径切片记录）                                       ← milestone 用 path="milestone_gift"
├── rarity_defaults（稀有度默认溢出兜底）                                        ← 无需每卡配置
└── SimulationEnv.card_overflow_map → GachaService.card_overflow_map            ← 构建链完整

本计划（P58——独立 MilestoneEngine）
├── 零依赖 PityEngine / BEHAVIOR_REGISTRY
├── 零依赖 CounterBasedBehavior / PityState
├── 零依赖 P55 / P56
└── 与 P55 / P56 / P63 完全并行——改不同文件、不同 TOML 段、不同 UI Tab
```

**关键识别：独立方案消除了「milestone 与 P55 共享平台层」的伪依赖。** P55 的 `CounterBasedBehavior` 是为保底计数器（未出目标稀有度）设计的——milestone 不需要它。里程碑计数器是纯粹的 `int` 自增，极简到不需要继承任何东西。

**P63 接口约定（2026-07-29 锁定）：**
- milestone 注入卡调用 `state.add_card(cid, path="milestone_gift", overflow_bands=card_overflow_map.get(cid), initial_counts=_initial_counts)`
- 溢出由 `match_overflow_bands()` 自动匹配分段表，返回 `Dict[str, float]`
- `card_overflow_map` 来自 `GachaService.card_overflow_map`（`SimulationEnvBuilder` 从 `ConfigStore.card_overflow_map` 注入）

---

## 六、波及范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/config_store.py` | **修改** | 新增 `MilestoneDef` + `MilestoneConfig` dataclass；`ConfigStore` 新增 `milestone` 字段；import `OverflowBand`（P63） |
| `core/config_toml.py` | **修改** | 新增 `_build_milestone()` + `save_toml()` 新段 |
| `core/milestone.py` | **新建** | `MilestoneEngine` 独立调度器——import `OverflowBand` / `match_overflow_bands`（P63） |
| `core/collector.py` | **修改** | 新增 `on_bonus` 抽象方法 + `CompactCollector` 实现 |
| `core/result_types.py` | **小改** | `CompactResult` 新增 `bonus_events` 字段 + `to_dict()`/`from_dict()` 序列化 |
| `core/generalized_drop_rate.py` | **修改** | GDR 计算入口合并 `bonus_events`——`_merge_milestone_cards()`（~20 行，P63 未碰此项） |
| `service/gacha_service.py` | **修改** | `__init__` 新增 `milestone_engine` 参数 + 模拟循环中 bonus 消费 + `StrategyContext` 传入 `_milestone_engine`（~20 行） |
| `service/batch_simulator.py` | **修改** | `SimulationEnv` 新增 `milestone_defs: List[MilestoneDef]` 字段（非 `MilestoneEngine`——延迟构造）；`SimulationEnvBuilder.from_config_store()` 提取 `store.milestone.milestones`；`_run_single` 中 `MilestoneEngine(env.milestone_defs, seed=seed)` 构造并传入 `GachaService`（~15 行） |
| `core/strategy.py` | **修改** | `StrategyContext` 新增 `_milestone_engine` + 3 个查询方法（~20 行） |
| `gui/config_panel.py` | **修改** | 新增 `_setup_milestone_config()` + 联动方法 + Tab 注册（~100 行） |
| `config/config.toml` | **更新** | 新增 `[[milestone]]` 示例段 |
| `tests/` | **新增** | ~50 行集成测试 |

**不受影响：** `core/pity.py`（零改动）、`core/pool.py`、`gui/` 分析面板（通过 collector 隔离）、`core/overflow.py`（仅 import，零改动）

**2026-07-29 修订：** M6（`resources_gained` 解析遗漏修复）已删除——P63 已修复 TOML 管道。`batch_simulator.py` 新增入波及范围——`SimulationEnv` + `SimulationEnvBuilder` 需传递 `milestone_config`。

---

## 七、风险

| 风险 | 缓解 |
|------|------|
| ~~`SimulationStats.acquired_counts` 移除后外部引用遗漏~~ | ~~P60 已处理~~ —— 已消除 |
| ~~旧序列化快照（无 `acquired`）反序列化失败~~ | ~~P60 已处理~~ —— 已消除 |
| ~~TOML 中 `resources_gained`/bonus 字段从未被解析~~ | ~~P63 已修复 TOML 管道~~ —— 已消除 |
| `milestone` 计数器生命周期（`repeat`=true 重置 vs false 停用）自管 bug | 极简逻辑——`int` 自增 + `if c >= threshold`，M8 集成测试覆盖 |
| bonus 注入时序不当（早于/晚于保底重置导致状态不一致） | 时序固定：`PityEngine.after_draw` → `state.add_card(path="draw")`（正常溢出，P63）→ `MilestoneEngine.after_draw` → `state.add_card(path="milestone_gift")`（milestone 溢出，P63）→ 资源结算 |
| `bonus_events` 序列化遗漏导致并行模拟数据丢失 | `CompactResult.to_dict()`/`from_dict()` 必须同步更新——M5 追加此项 |
| `SharedResultCollector` 未实现 `on_bonus`——流式分析中里程碑不可见 | M5 同时覆盖 `SharedResultCollector` |
| GDR `_merge_milestone_cards()` 依赖 `real_time→draw_index` 映射 | `CompactResult` 需新增 `_time_to_draw_index()` 或预建映射字典——M5a 设计时决定 |
| `pools` 字段兼容旧 TOML（字符串 `"*"` 语法） | `_build_milestone()` 中 `isinstance(raw_pools, str)` 检测 → 自动转 `["*"]`（fnmatch 中 `*` 匹配全部） |
| fnmatch 通配符误匹配（如 `"limited_*"` 不当匹配 `"limited_pool_old"`) | 与保底体系一致的 fnmatch 行为——用户自己在 TOML 中控制精度 |
| 配置面板 UI 与 P55/P56 保底 UI 改造潜在冲突 | 独立 Tab——不碰 `_setup_pity_config()` |

---

## 八、验收标准

- [ ] `[[milestone]]` 独立 TOML 段解析正确——与 `[[pity]]` 互不影响
- [ ] `bonus_reward.cards`——达阈值后固定卡经 `state.add_card(cid, path="milestone_gift", overflow_bands=...)` 直入 `state.acquired`，不修改概率分布
- [ ] `bonus_reward.resources`——达阈值后资源归入 `rg`（P63 单通道），不重复入账
- [ ] `bonus_reward.random_cards`——达阈值后从候选池加权随机抽取指定张数（使用 `self._rng.choices()` 保证可复现），直入 `state.acquired`
- [ ] `cards` + `resources` + `random_cards` 可同时配置、同时生效——一次触发可同时赠送卡+资源+随机卡
- [ ] `repeat = false`（at=N）：触发一次后永久停用，计数器不复位
- [ ] `repeat = true`（every=N）：触发后计数器归零继续计数，下一轮继续触发
- [ ] `max_triggers` 正确限制触发次数——达上限后永久停用；默认 0 = 无限触发
- [ ] `pools` 正确过滤——空列表 = 全部池子，非空 = 精确匹配（`isinstance(raw_pools, str)` 兼容旧 `"*"` 语法）
- [ ] bonus 注入不触发常规保底重置（`hard`/`soft` 计数器不受 milestone 影响）
- [ ] milestone 注入的卡经 P63 `state.add_card(path="milestone_gift", overflow_bands=card_overflow_map.get(cid), initial_counts=...)` 统一管道正确触发溢出（`match_overflow_bands()` 自动匹配分段表），与正常抽卡一致
- [ ] milestone 溢出资源 + 直接资源统一归入 `rg`（P63 单通道），不重复入账
- [ ] `collector.on_bonus()` 只存元数据（`milestone_name`、时间戳、赠送卡 ID、资源），不承载资源金额（P63 单通道约束）
- [ ] `SharedResultCollector` 同步实现 `on_bonus`——流式分析中里程碑事件可见
- [ ] `CompactResult.to_dict()`/`from_dict()` 正确序列化/反序列化 `bonus_events`——并行模拟不丢数据
- [ ] GDR 计算层合并 `bonus_events`——里程碑卡按 `real_time→draw_index` 对齐到正确抽数，参与 GDR 计算
- [ ] GDR 合并不改函数签名——在 `compute_gdr_from_compact/compute_gdr_from_history` 入口处完成
- [ ] `PityEngine` 零改动——milestone 完全不参与保底管道
- [ ] `BEHAVIOR_REGISTRY` 不含 `milestone` 条目
- [ ] 7 个 G20 场景的 TOML 配置 → 模拟 → 产出验证通过
- [ ] 配置面板「累抽奖励」Tab 可完整编辑所有字段；修改后触发全局预览刷新（`_update_preview` → `_do_update_preview` 含 milestone 摘要段）
- [ ] `StrategyContext` 可查询里程碑计数器、活跃状态、定义信息（threshold / bonus_reward）
- [ ] 策略层接口只读——不能通过 `StrategyContext` 修改里程碑计数器
- [ ] 不存在里程碑配置时，`StrategyContext` 查询返回安全默认值（0 / False / 空 dict）
- [ ] `MilestoneEngine.__init__` 接收 `seed` 参数——`random.Random(seed)` 保证随机卡抽取可复现
- [ ] pytest 全量通过
