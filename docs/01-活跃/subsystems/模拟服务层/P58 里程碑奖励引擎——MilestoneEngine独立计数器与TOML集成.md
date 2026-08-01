<!-- META: P58 | module:模拟服务层 | status:designing | last:2026-08-01 | depends:P60✅,P63✅,P61-Ph0(待) -->

# P58 累抽奖励引擎——独立 MilestoneEngine 实现

> 日期：2026-06-19 | 更新：2026-07-29 | 状态：设计中（P63 已实施，接口已收敛）
> **2026-06-20 架构决策：** milestone 不作为保底 type 实现——独立 `MilestoneEngine` + `[[milestone]]` TOML 段。理由：milestone 不操作概率、不参与 PityEngine 管道、语义与「保底」（运气保护）正交。独立方案代码量不增反减（~97 vs ~110 行），且零侵入 PityEngine / BEHAVIOR_REGISTRY。
> **2026-07-29 UI 审查修正：** ConfigPanel 右侧仅为全局 `preview_text` QLabel——无独立 TOML 预览区。Tab 命名「累抽奖励」（玩家社区有机术语，NGA/贴吧通用，语义精准：累计抽取→赠送）。P58 信号连接复用已有 `_update_preview()` 全局方法，仅在 `_do_update_preview()` 追加累抽摘要段。UI 整体方案确认：与保底编辑器统一模式（总闸→左列表右详情→底部按钮），随机卡采用摘要行+弹窗编辑（`RandomCardPoolDialog`，四列勾选/卡/稀有度/权重），权重为每卡独立列。

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

#### 1.1a 各场景具体期望输出（M8 测试输入/输出规范）<!-- REVIEW-R1-FIX: GATE-6-测试策略 -->

以下为 7 个 G20 场景的 M8 集成测试期望——每个场景定义：输入 TOML 配置 → 模拟 N 抽 → 期望 bonus_events 长度、期望 card_counts 中的赠送卡计数、期望资源入账金额。

| # | 场景 | 模拟抽数 | bonus_events 长度 | card_counts 期望 | 资源期望 | 关键断言 |
|---|------|:---:|:---:|---|---|---|
| 1 | 火影每 10 抽碎片 | 25 抽 | 2 | `card_counts` 不含赠送（无 card） | `resources['fragment_s'] ≈ 2` | repeat=true, threshold=10; 第 10/20 抽各触发一次；milestone 不修改概率 |
| 2 | 火影 50 抽大保底碎片 | 120 抽 | 2 | 同 1——无 card | `resources['fragment_s'] ≈ 10`（5x2） | repeat=true, threshold=50; 第 50/100 抽触发 |
| 3 | 火影首付返利（S忍 100 抽） | 150 抽 | 1 | `card_counts['limited_ssr_1'] == 1` | `resources['coin'] ≈ 500` | repeat=false, threshold=100; 触发后 `is_active=false`；第 100-150 抽不再次触发 |
| 4 | 阴阳师 40 抽随机 SSR | 80 抽 | 1 | `sum(card_counts[c] for c in ssr_candidates) == 1` | 无资源 | repeat=false; 第 40 抽触发；随机卡从 4 候选中等权抽取；RNG seed 固定可复现 |
| 5 | 明日方舟 300 抽当期限定 | 300 抽 | 1 | `card_counts['limited_operator'] == 1` | `resources['exchange_currency'] ≈ 300` | repeat=false; cards + resources 同时交付 |
| 6 | 终末地 30 抽取送十连 | 30 抽 | 1 | 无 card | `resources['endfield_next_voucher'] ≈ 1` | 需先定义 `endfield_next_voucher` 资源类型（等价 10 连） |
| 7 | 终末地 60 抽寻访档案 | 60 抽 | 1 | 无 card | `resources['endfield_next_voucher'] ≈ 10` | at=60; 独立于场景 6 的 milestone |

**多触发顺序验证场景（追加——同抽触发多个 milestone）：**<!-- REVIEW-R1-FIX: GATE-6-测试策略-同抽多触发顺序 -->

| # | 场景 | 模拟抽数 | bonus_events 顺序 | 关键断言 |
|---|------|:---:|---|---|
| S1 | 场景 1（threshold=10）+ 场景 2（threshold=50）共存 | 50 抽 | `['naruto_fragment', 'naruto_s_fragment']`（按 TOML 定义顺序） | 第 50 抽同时触发两个 milestone；bonus_events 列表顺序 = TOML `[[milestone]]` 定义顺序（确定性） |

**空抽（_NO_CARD_ID）计数推进验证：**<!-- REVIEW-R1-FIX: GATE-6-测试策略-空抽计数 -->
- 若存在交换池或概率归零场景（`pool.draw()` 返回 `_NO_CARD_ID`），`MilestoneEngine.after_draw()` 仍被调用 → 计数器无条件递增 → 空抽计入累抽进度。验证：模拟包含 N 次空抽的序列 → 计数器值 = 实际调用 `after_draw` 次数（含空抽）。

**里程碑卡溢出验证：**<!-- REVIEW-R1-FIX: GATE-6-测试策略-溢出 -->
- 若里程碑赠送的卡牌已达到满突上限（`initial_counts` 中已满），`state.add_card(cid, overflow_bands=card_overflow_map.get(cid), ...)` 应触发 `match_overflow_bands()` 并返回溢出资源（如星辉、井币）。验证：模拟前预设该卡已满突破 → milestone 触发 → 溢出资源正确入账 `milestone_rg` → `combined_gained` 反映溢出金额。

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
          - resource 类型 → 归入 milestone_rg（P63 单通道，不通过 state.gain）
          - collector.on_bonus(...)

        _NO_CARD_ID（空抽）行为：计数器无条件递增——只要 gacha_service 调用了
        after_draw() 即视为一次有效抽数。空抽（交换池/概率归零场景下 pool.draw()
        返回 _NO_CARD_ID）仍消耗资源/抽数，计数器应正常推进（符合绝大多数游戏的期望
        行为——「花了钱就算一抽」）。若特定游戏需排除空抽，调用方应在 after_draw()
        调用前加 `if reward.id != _NO_CARD_ID` 守卫——MilestoneEngine 本身不做此判断。<!-- REVIEW-R1-FIX: ISSUE-005 -->
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

#### 3.2a SimulationEnvBuilder 构造点——完整返回语句修改 <!-- REVIEW-R1-FIX: ISSUE-029 -->

在 `SimulationEnvBuilder.from_config_store()` 的 `return SimulationEnv(...)` 语句（`batch_simulator.py` L710-727）中标明新增的 `milestone_defs` 参数位置。插入于现有 `card_overflow_map` 行之后、右括号之前：

```python
# batch_simulator.py L710-727 —— SimulationEnvBuilder.from_config_store() 返回语句
return SimulationEnv(
    pools=pools,
    schedule_mgr=schedule_mgr,
    end_time=end_time,
    pity_engine=pity_engine,
    resource_gain=resource_gain,
    pity_state_init=pity_state_init,
    card_defs=card_defs,
    initial_resources=initial_resources,
    target_ids=target_ids,
    ssr_ids=ssr_ids,
    all_drawable_ids=all_drawable_ids,
    pool_end_times=pool_end_times,
    gdr_context=gdr_context,
    strategy_key=strategy_key,
    strategy_params=strategy_params,
    card_overflow_map=dict(getattr(config_store, 'card_overflow_map', {})),
    # 【P58 新增】里程碑配置——MilestoneEngine 在 _run_single 中延迟构造
    milestone_defs=list(getattr(config_store, 'milestone', MilestoneConfig()).milestones),
)
```

`getattr(config_store, 'milestone', MilestoneConfig())` 无里程碑配置时返回空列表（`MilestoneConfig().milestones = []`），`MilestoneEngine` 收到空列表后无操作——向下兼容。`from __future__ import annotations` 延迟求值无需额外的 `TYPE_CHECKING` 守卫。

####

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
    pools: tuple = ()  # 作用池子（空元组=全部；支持 fnmatch 通配符，如 "limited_*"）。类型与 PityDef.pools (tuple) 一致<!-- REVIEW-R1-FIX: ISSUE-006 -->
    banner: str = ""   # P61 协作：精确指向一个 Banner（推荐用法）。P61 后 pool_id 是 Banner 内部 id（跨 banner 重复），故新增 banner 级过滤；pools 保留兼容旧 pool_id 过滤。空字符串 = 不按 banner 过滤


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
- `pools` 从 `str` 改为 `tuple`（最终类型，与 `PityDef.pools: tuple = ('*',)` 一致<!-- REVIEW-R1-FIX: ISSUE-006 -->），解决原来字符串 `in` 子串误匹配问题（`"ak_limited" in "onmyoji_limited"` → True）。空元组 `()` = 全部池子，非空 = fnmatch 精确匹配。
- `max_triggers` 默认值从 `1` 改为 `0`（0=无限触发），与 TOML 示例和文档一致。
- 匹配逻辑相应调整：`if md.pools and not any(fnmatch(pool_id, pat) for pat in md.pools): continue` —— tuple 同样支持 `any()` 迭代。

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
# 插入位置：正常溢出合并 (gacha_service.py L340) 之后、rg → resources (L341) 之前<!-- REVIEW-R1-FIX: ISSUE-001 -->

# ── 保底状态更新 ──
if _pity_engine:
    _pity_engine.after_draw(pool.id, pity_state, reward.id)

# ── 资源结算（正常产出）──
rg = dict(reward.resources_gained or {})

# ── 正常产出溢出（P63 统一管道）──
if reward.id != _NO_CARD_ID:
    overflow = state.add_card(
        reward.id,
        path="draw",
        overflow_bands=self.card_overflow_map.get(reward.id),
        initial_counts=_initial_counts,
    )
    for k, v in overflow.items():
        rg[k] = rg.get(k, 0) + v

# ── 【新增】里程碑判定与注入 ──<!-- REVIEW-R1-FIX: ISSUE-001 -->
milestone_rg: dict = {}
if _milestone_engine:
    for entry in _milestone_engine.after_draw(pool.id):
        bonus = entry['bonus']
        # 直接资源——归入 milestone_rg（P63 单通道，不通过 state.gain）<!-- REVIEW-R1-FIX: ISSUE-003 -->
        # state.gain() 已删除——同一批资源经 milestone_rg → rg → resources
        # 再次累加到 state.resources 会双重入账，违反 P63 单通道约束
        direct_res = bonus.get('resources', {})
        if direct_res:
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
            pool_id=pool.id,               # ← 用于 per-pool 归因（pool_card_counts）<!-- REVIEW-R1-FIX: ISSUE-011 -->
            real_time=real_time,
        )
    # milestone 溢出资源 + 直接资源 → 归入 rg（P63 单通道）—— rg 已在上方定义完毕
    if milestone_rg:
        for k, v in milestone_rg.items():
            rg[k] = rg.get(k, 0) + v

# ── rg → resources + combined_gained → collector.on_draw（保持不变）──
# ... 后续保持不变
```

**2026-07-29 修订——匹配 P63 实际 API：**
- `state.add_card()` 签名：`(card_id, path="milestone_gift", overflow_bands=card_overflow_map.get(cid), initial_counts=_initial_counts) → Dict[str, float]`
- `card_overflow_map` 来自 `GachaService.card_overflow_map`（由 `SimulationEnvBuilder` 从 `ConfigStore.card_overflow_map` 注入）
- 不再使用计划中原假设的 `bonus_config=` kwarg——P63 统一为 `overflow_bands=` 参数 + `match_overflow_bands()` 内部匹配
- `on_bonus` 参数 `pity_name` → `milestone_name`（语义修正）

**关键时序：**<!-- REVIEW-R1-FIX: ISSUE-001 + ISSUE-003 -->

```
before_draw → PityEngine.before_draw (不含 milestone)
  → pool.draw() → 正常出卡
  → PityEngine.after_draw → 常规保底重置（hard/soft 等，不含 milestone）
  → rg = dict(reward.resources_gained or {}) → 正常资源提取
  → state.add_card(reward.id, path="draw", overflow_bands=...) → 正常产出溢出 → rg（P63）
  → MilestoneEngine.after_draw → 达阈值 → 返回 bonus
  → state.add_card(cid, path="milestone_gift", overflow_bands=...) → milestone 卡片溢出 → milestone_rg（P63 统一管道）
  → 直接资源归入 milestone_rg（P63 单通道，不通过 state.gain）<!-- REVIEW-R1-FIX: ISSUE-003 -->
  → milestone_rg 归入 rg（P63 单通道）
  → rg → resources（资源累加，P63 单通道）
  → collector.on_bonus() + collector.on_draw()
```

**P61 协作（Notifier 集成）—— 2026-08-01 新增：**

P61 引入 Banner 抽象后，抽卡事件经 `core/notifier.py`（P61 Ph0 交付）分发。P58 通过订阅 `after_draw` 事件集成，替代 M4 的 inline 调用（逻辑不变，约 15 行迁移）：

```python
# gacha_service.py —— 模拟循环中（P61 已 emit，契约见 P61 §3.5）
notifier.emit("after_draw",
              banner_id=banner.id, pool_id=banner.active_pool_id,
              card_id=reward.id, pity_triggered=triggered,
              state=state, collector=collector)

# P58 模块中 —— 订阅函数（逻辑与上方 M4 inline 完全一致）
def _on_after_draw(banner_id, pool_id, card_id, pity_triggered, state, collector):
    if _milestone_engine:
        for entry in _milestone_engine.after_draw(banner_id, pool_id):
            # ... 消费 bonus（与 M4 代码完全相同，用 state/collector 更新资源）...

notifier.subscribe("after_draw", _on_after_draw, priority=0)   # P58 资源注入先于 P61 生命周期检查
```

**关键变更：**
- `after_draw` 事件契约：`banner_id / pool_id / card_id / pity_triggered + state / collector`（P61 §3.5 定义）
- `MilestoneEngine.after_draw(banner_id, pool_id)` 签名扩展：P61 后 pool_id 是 Banner 内部 id（跨 banner 重复），需用 banner_id 做 banner 级过滤（`MilestoneDef.banner`）。P61 前（M4 inline）用 `after_draw("", pool_id)` 等价旧行为
- 订阅 priority=0：P58（资源注入）先于 P61（生命周期检查），避免「P61 切换池时 P58 资源未注入」的竞态
- `[[milestone]]` 推荐新增 `banner` 字段（精确指向一个 Banner）；`pools` 保留兼容旧 pool_id 过滤
- 依赖 P61-Ph0（core/notifier.py）。Ph0 交付后 P58 与 P61 完全并行；M1-M8 零依赖 P61，M9 依赖 Ph0

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

#### GachaService + strategy_context_builder 传入

```python
# gacha_service.py
class GachaService:
    def __init__(self, ...,
                 milestone_engine: Optional[MilestoneEngine] = None):
        # ...
        self.milestone_engine = milestone_engine

# run_simulation 循环中通过 build_strategy_context() 构造 StrategyContext:
# ⚠ 必须修改 strategy_context_builder.py 的函数签名——不绕过此函数，避免丢失派生字段
# (future_resource_gains / inter_pool_pity_links)<!-- REVIEW-R1-FIX: ISSUE-004 -->
ctx = build_strategy_context(
    # ... 现有参数 ...
    _milestone_engine=self.milestone_engine,
)
```

**`strategy_context_builder.py` 修改（M4a 追加）——`build_strategy_context()` 签名新增参数：**
```python
def build_strategy_context(
    # ... 现有参数 ...
    *,
    _milestone_engine: Optional['MilestoneEngine'] = None,  # ← 新增 <!-- REVIEW-R1-FIX: ISSUE-004 -->
) -> StrategyContext:
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
                 resources: Dict[str, float], pool_id: str, real_time: float):
        """milestone 注入事件——只存元数据（里程碑名、时间戳、赠送内容、触发池）。
        pool_id 用于 per-pool GDR 分析归因。<!-- REVIEW-R1-FIX: ISSUE-011 -->
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
        'pool_id': pool_id,                # ← 触发池 ID，用于 per-pool 归因<!-- REVIEW-R1-FIX: ISSUE-011 -->
        'real_time': real_time,
        # 资源金额不在此存储——已通过 milestone_rg 归入 combined_gained（P63）
    })
    # ── 源头合并 card_counts / pool_card_counts（方案 A）──<!-- REVIEW-R1-FIX: ISSUE-003 -->
    # SharedResultCollector 无 on_bonus 方法，合并必须在 to_dict() 之前完成
    for cid in card_ids:
        r.card_counts[cid] = r.card_counts.get(cid, 0) + 1
        if pool_id:
            if pool_id not in r.pool_card_counts:
                r.pool_card_counts[pool_id] = {}
            r.pool_card_counts[pool_id][cid] = r.pool_card_counts[pool_id].get(cid, 0) + 1
```

`CompactResult` 新增字段：

```python
bonus_events: list = field(default_factory=list)
```

`to_dict()` / `from_dict()` 需同步更新——**此项未列入原实施阶段，需追加。**

**SharedResultCollector（流式分析）聚合策略：**<!-- REVIEW-R1-FIX: ISSUE-003 -->
**设计方案 A（源头合并——推荐）：** `SharedResultCollector` 不具备 `on_bonus` 方法（当前仅有 `on_result(compact: Dict)`），且 `extract_aggregate()` 仅读取 `compact['card_counts']`/`compact['pool_card_counts']` 等字段，不解析 `bonus_events`。因此 bonus 合并必须在数据进入 `SharedResultCollector` **之前**完成——即 `CompactCollector.on_bonus()` 中同步更新 `self._result.card_counts` 和 `self._result.pool_card_counts`。这样 `to_dict()` 产出的紧凑字典已含合并后的全量卡牌统计，`extract_aggregate()` 无需改动、流式分析自然包含里程碑产出。此方案与计划「GDR 始终包含里程碑奖励」的约束一致。

**与 _merge_milestone_cards() 互斥声明（2026-07-30 审查修正）：**<!-- REVIEW-R1-FIX: ISSUE-002 -->
方案 A 在 `on_bonus` 阶段已完成 `card_counts` / `pool_card_counts` 的源头合并。若方案 A 被实施，**§3.6a 的 `_merge_milestone_cards()` 不得再重复写入 `card_counts` 或 `pool_card_counts`**——否则 milestone 赠卡会被双重计入。`_merge_milestone_cards()` 降级为仅构建合并后的 `merged: Dict[str, List[int]]` 映射（供 GDR 时序计算），其 `pool_card_counts` 更新逻辑需移除——由 `card_counts` 反推即可。两方案不可同时生效于同一数据字段。参见 §3.6a 开头的备选方案标注。

**方案 B（备选）：** 若坚持 `card_counts` 不含赠送卡（区分抽得/赠得），则在 `extract_aggregate()` 中额外读取 `bonus_events` 并叠加。代码量更大、侵入更多路径，仅作为方案 A 不可行时的回退。

**流式累积快照适配（2026-07-30 追加——2026-07-30 修订扩展至全部四条路径）：**<!-- REVIEW-R1-FIX: ISSUE-004 -->**
当前有五条流式提取路径均遍历 `draw_card_ids`：

| 路径 | 文件:方法 | 行号 | 功能 |
|------|----------|------|------|
| 累积 GDR | `streaming.py:_update_cumulative()` | L488-531 | 构建 `cumulative_card_counts` |
| Worker 热力图 | `streaming.py:WorkerLocalExtractor.process()` | L215-254 | 成就×资源分箱热力图 |
| Worker 转变标记 | `streaming.py:WorkerLocalExtractor.process()` | L256-278 | 池结束时目标是否达成 |
| DrawSeq 热力图 | `streaming.py:DrawSequenceExtractor._update_heatmap()` | L446-486 | 热力图分箱 |
| DrawSeq 转变标记 | `streaming.py:DrawSequenceExtractor._update_transition()` | L536-564 | 转变标记 |

milestone 赠卡不经过 `pool.draw()` 管线——不会出现在 `draw_card_ids` 中。统一修复策略：

**方案 A（推荐——与 ISSUE-003 联动）：** `CompactCollector.on_bonus()` 已同步更新 `card_counts`/`pool_card_counts`。以上五条路径统一改用合并后的 `card_counts` 作为输入源（`to_dict()` 产出的 compact dict 中 `card_counts` 已含 bonus）。`_update_cumulative()` 无需遍历 `draw_card_ids`——直接从 `card_counts` 增量构建 `cumulative_card_counts`。`WorkerLocalExtractor.process()` 中的热力图/转变标记同理。

**方案 B（备选）：** 在各遍历入口处构建 `merged_card_ids`（正常 `draw_card_ids` + `bonus_events` 赠卡按 `real_time` 定位插入），遍历 `merged_card_ids` 而非 `draw_card_ids`。`real_time → draw_index` 映射共用 `_time_to_draw_index()` 工具函数。

两方案等效——方案 A 更简洁（源头已完成合并，消费方无需感知 bonus 来源），方案 B 保留时序信息（bonus 赠卡插入到正确的抽数位置）。实际实现时两方案可组合使用。

正确性保证（逐层追踪）：
```
单抽 on_draw(card_id="ssr_a", resources_gained=rg)  ← rg 已含: 正常溢出 + milestone溢出 + milestone直接资源
     on_bonus(card_ids=["ssr_b"], resources={coin: 500})  ← 仅累加 card_counts["ssr_b"]，不动资源
```
- **不会少加：** milestone 卡通过 `on_bonus` 显式累加进 `card_counts`
- **不会多加：** 资源仅通过 `on_draw` 的 `rg` 入账（单通道），`on_bonus` 不碰资源

分析面板据此区分两类来源——但 GDR 计算时始终合并（里程碑是池子固有属性，§3.1 约束）。

#### 3.6a GDR 层合并 bonus_events

> **2026-07-30 审查修正：** 此节定义的 `_merge_milestone_cards()` 是**方案 B（备选）**<!-- REVIEW-R1-FIX: ISSUE-002 -->——仅当 §3.6 的方案 A（`on_bonus` 源头合并）未实施时才需要。若方案 A 已生效（`card_counts` / `pool_card_counts` 在 `on_bonus` 阶段已完成合并），则 `_merge_milestone_cards()` 只应构建 `merged: Dict[str, List[int]]` 映射（供 GDR 时序计算），**不得再写入 `result.pool_card_counts`**，否则 milestone 赠卡被双重计入。`pool_card_counts` 可否从已合并的 `card_counts` 反推——无需在此函数中二次累加。两方案互斥：同一数据字段不得经由两条路径重复修改。

> **2026-07-29 注：** P63 未碰 GDR 层——此项完全由 P58 自行实现。

`bonus_events` 与 `card_counts` 是独立通道。GDR 计算时需要将 milestone 赠卡合并到正常产出中以正确计算出率。资源金额已通过 P63 单通道（`milestone_rg` → `combined_gained`）自动归入，无需额外合并：

```python
# gdr.py —— 在 compute_gdr_from_compact() / compute_gdr_from_cumulative() 入口处调用
<!-- REVIEW-R1-FIX: ISSUE-009 -->

def _merge_milestone_cards(result: CompactResult) -> Dict[str, List[int]]:
    """将 bonus_events 中的卡按抽数索引合并到 card_counts。

    bonus_events 携带 real_time → 映射到对应抽数 → 追加到该抽的卡产出中。
    同时更新 pool_card_counts——bonus_events 中的 pool_id 用于 per-pool 归因。
    """
    merged: Dict[str, List[int]] = defaultdict(list)
    # 先复制正常抽卡产出
    for i, card_id in enumerate(result.draw_card_ids):  # ← 修正：card_sequence → draw_card_ids <!-- REVIEW-R1-FIX: ISSUE-010 -->
        merged[card_id].append(i)

    # 合并里程碑赠卡
    for ev in result.bonus_events:
        draw_idx = result._time_to_draw_index(ev['real_time'])  # 时间戳→抽数
        pool_id = ev.get('pool_id', '')
        for cid in ev.get('card_ids', []):
            merged[cid].append(draw_idx)
            # 同步更新 pool_card_counts——在循环内逐卡累加，多卡赠礼不漏<!-- REVIEW-R1-FIX: ISSUE-002 -->
            if pool_id and cid:
                if pool_id not in result.pool_card_counts:
                    result.pool_card_counts[pool_id] = {}
                result.pool_card_counts[pool_id][cid] = result.pool_card_counts[pool_id].get(cid, 0) + 1

    return merged
```

资源同理——`bonus_events` 中的资源在总账 `resources` 中已合并，但单抽明细需要对齐 `real_time`。

**波及（2026-07-30 修正）：** `compute_gdr_from_compact()` / `compute_gdr_from_cumulative()` 调用前先合并——这两个入口均在 `gdr.py` 中。不改函数签名——合并发生在入口。若历史路径（`compute_gdr_from_history()`，通过 `generalized_drop_rate.py` 中的 `GeneralizedDropRate` 子类计算）也需反映 milestone 产出，需在历史路径中单独适配（见风险表 ISSUE-008）。

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
            if 'weights' in rc and len(rc['weights']) != len(candidates):
                raise ConfigError(
                    f"里程碑 '{name}' random_cards[{i}].weights 长度({len(rc['weights'])})"
                    f"与 candidates({len(candidates)})不匹配"
                )  <!-- REVIEW-R1-FIX: ISSUE-005: 防止手工 TOML 中 weights 长度错误 → random.choices ValueError -->

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
            pools=tuple(raw_pools),  # tuple 类型与 PityDef.pools 一致<!-- REVIEW-R1-FIX: ISSUE-006 -->
        ))

    store.milestone = MilestoneConfig(enabled=True, milestones=milestones)
    # ⚠ 设计限制：enabled 为运行时标志，不持久化到 TOML——load_toml() 始终重置为 True。
    # 与保底系统的 PityConfig.enabled 行为一致。用户期望「禁用累抽」跨会话保持需在 UI 层
    # 额外存储偏好（不在本计划范围内）。<!-- REVIEW-R1-FIX: ISSUE-004 -->
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

#### 3.8.1 整体布局

与保底编辑器统一模式——顶部总闸开关 → 水平左列表右详情 → 底部按钮栏。在 `left_tabs` 中新增独立 Tab「累抽奖励」——位于「保底机制」Tab 之后。

```
┌─ 累抽奖励 ───────────────────────────────────────────────────────┐
│ ☑ 启用累抽奖励                                ← 全局总闸，持久化   │
│                                                                    │
│ ┌────────────────┐ ┌─ 累抽详情 ─────────────────────────────────┐ │
│ │ onmyoji_40     │ │ 名称:  [onmyoji_40_gift              ]     │ │
│ │ naruto_frag    │ │ 触发阈值: [40                      ] 抽    │ │
│ │ ak_300_gift    │ │ ☐ 可重复触发                               │ │
│ │                │ │ 最大触发: [1                       ] 次    │ │
│ │                │ │ 适用池子: [onmyoji_limited          ]      │ │
│ │                │ │                                            │ │
│ │                │ │ ── 奖励配置（可同时填写多区域） ──          │ │
│ │                │ │                                            │ │
│ │                │ │ 固定卡牌（可多选）:                          │ │
│ │                │ │ ┌──────────────────────────────────────┐   │ │
│ │                │ │ │ [SSR] ☐ 茨木童子 (ssr_ibaraki)        │   │ │
│ │                │ │ │ [SR ] ☐ 姑获鸟   (sr_ubume)          │   │ │
│ │                │ │ │ [R  ] ☐ 河童     (r_kappa)           │   │ │
│ │                │ │ └──────────────────────────────────────┘   │ │
│ │                │ │                                            │ │
│ │                │ │ 资源:                                      │ │
│ │                │ │ ┌──────────────────┬──────┐               │ │
│ │                │ │ │ 资源              │ 数量  │               │ │
│ │                │ │ │ coin             │ 500  │               │ │
│ │                │ │ │ fragment_s       │ 5    │               │ │
│ │                │ │ └──────────────────┴──────┘               │ │
│ │                │ │ [添加] [移除选中]                                │ │
│ │                │ │                                            │ │
│ │                │ │ 随机卡:  [池1: SSR茨木/SSR酒吞,抽1张] [编辑]│ │
│ │                │ │          [池2: SP天剣×2,抽1张]     [编辑]│ │
│ │                │ │          [添加] [移除选中]                  │ │
│ └────────────────┘ └───────────────────────────────────────────┘ │
│              [添加] [移除选中]                                    │
└──────────────────────────────────────────────────────────────────┘
```

**与保底编辑器对照：**

| | 保底编辑器 | 累抽编辑器 |
|---|----------|----------|
| 总开关 | `QCheckBox("启用保底")` | `QCheckBox("启用累抽奖励")` |
| 左列表 | `QListWidget` 保底条目 | `QListWidget` 累抽条目 |
| 右详情 | `QGroupBox("保底详情")` | `QGroupBox("累抽详情")` |
| 详情布局 | `QFormLayout` 逐行 | `QFormLayout` 逐行 + 奖励三区域 |
| 底部按钮 | 添加/移除选中 | 同 |
| 自动写入 | `_flush_pity_current_detail` 实时写回 | `_flush_milestone_current_detail` 同模式 |
| 卡片选择 | 无（保底不选卡） | `QListWidget` 多选 + 稀有度着色 |
| 资源表 | 无 | `QTableWidget` 资源×数量 |
| 随机卡 | 无 | 摘要行 + 弹窗编辑 |

#### 3.8.2 控件映射

| 字段 | 控件 | 说明 |
|------|------|------|
| `enabled` | `QCheckBox` | 全局总闸——`False` → 不构造 `MilestoneEngine`，与 `PityConfig.enabled` 语义一致。运行时标志，不持久化到 TOML |
| `name` | `QLineEdit` | 唯一标识 |
| `threshold` | `QSpinBox` | 触发阈值（1–9999） |
| `repeat` | `QCheckBox("可重复触发")` | 不勾选=`at:N`一发即停，勾选=`every:N`触发后重置继续 |
| `max_triggers` | `QSpinBox` | 0=无限，≥1=触发 N 次后停用 |
| `pools` | `QLineEdit` | 空=全部池子，或逗号分隔的 fnmatch 表达式 |
| `bonus_reward.cards` | `QListWidget`（多选） | 每行显示 `[稀有度] 名称 (card_id)`，稀有度着色 |
| `bonus_reward.resources` | `QTableWidget`（资源×数量） | 从 `store.resource_defs` 填充 |
| `bonus_reward.random_cards` | 摘要行 + 弹窗 | 主面板仅显示摘要行（`[池名: 卡列表, 抽N张]`），点击 `[编辑]` 弹出 `QDialog` |

#### 3.8.3 随机卡弹窗 (`RandomCardPoolDialog`)

**交互：** 主面板的随机卡区显示每个候选池的摘要行 + `[编辑]` 按钮 + `[+ 添加]` 按钮。点击 `[编辑]` 弹出 `QDialog`，包含四列表格 + 抽取张数。

```
┌─ 编辑随机卡池 ─────────────────────────────────┐
│                                                  │
│ ┌────┬──────────┬────────┬──────┐               │
│ │ 勾选│ 卡        │ 稀有度  │ 权重  │               │
│ ├────┼──────────┼────────┼──────┤               │
│ │ ☑  │ 茨木童子   │ SSR    │ 1.0  │               │
│ │ ☑  │ 酒吞童子   │ SSR    │ 1.0  │               │
│ │ ☐  │ 大天狗     │ SSR    │ 1.0  │               │
│ │ ☐  │ 辉夜姬     │ SSR    │ 1.0  │               │
│ │ ☑  │ 天剣絆主   │ SP     │ 2.0  │               │
│ │ ☐  │ 姑获鸟     │ SR     │ 1.0  │               │
│ └────┴──────────┴────────┴──────┘               │
│                                                  │
│ 抽取张数: [1                            ]       │
│                                                  │
│ 提示: 仅勾选的卡参与抽取，权重越大中选概率越高      │
│                                                  │
│                        [确定] [取消]              │
└──────────────────────────────────────────────────┘
```

**四列说明：**

| 列 | 控件 | 说明 |
|----|------|------|
| 勾选 | `QCheckBox` | 仅勾选的卡参与抽取；未勾选的权重忽略 |
| 卡 | `QTableWidgetItem`（只读） | 显示 `名称 (card_id)` |
| 稀有度 | `QTableWidgetItem`（只读） | 稀有度着色（SSR金/SR紫/R蓝） |
| 权重 | `QDoubleSpinBox` | ≥0，默认 1.0；0=永不出现 |

**数据来源：** 表格从 `self._store.card_defs` 填充全部可用卡。打开弹窗时回填已有勾选状态和权重值。

**「+ 添加」按钮：** 在 `self._milestone_random_pools` 列表中追加新池，默认无勾选卡、权重全部 1.0、抽取数 1。

#### 3.8.4 预览机制

ConfigPanel 右侧 `right_widget` 内仅有一个全局 `QGroupBox("配置预览")` + monospace `QLabel`（`preview_text`）。所有 Tab 共享此预览区——`_do_update_preview()` 遍历各配置段统一拼接摘要文本。

P58 的 7 条信号连接（`milestone_enabled.stateChanged` / `ml_name_edit.textChanged` / `ml_threshold_spin.valueChanged` / `ml_repeat_check.stateChanged` / `ml_max_triggers_spin.valueChanged` / `ml_pools_edit.textChanged` / 随机卡摘要变更 → `self._update_preview()`）触发的是 ConfigPanel 已有的 500ms 去抖全局预览方法。唯一需追加的是 `_do_update_preview()` 中的累抽摘要段：

```python
# _do_update_preview() 中追加 ~15 行
ml_cfg = config.get('milestone', {})
if ml_cfg.get('enabled', True) and ml_cfg.get('milestones'):
    lines = []
    for md in ml_cfg['milestones']:
        mode = f"every={md['threshold']}" if md.get('repeat') else f"at={md['threshold']}"
        br = md.get('bonus_reward', {})
        parts = []
        if br.get('cards'):
            parts.append(f"{len(br['cards'])}张固定卡")
        if br.get('resources'):
            parts.append(f"{len(br['resources'])}项资源")
        if br.get('random_cards'):
            parts.append(f"{len(br['random_cards'])}个随机池")
        lines.append(f"  {md['name']}: {mode} → {', '.join(parts) or '无奖励'}")
    preview += "\n累抽奖励:\n" + '\n'.join(lines)
```

#### 3.8.5 代码结构

```python
def _setup_milestone_config(self, parent):
    """[[milestone]] 配置 UI——与 _setup_pity_config() 统一模式"""
    self._milestone_defs = []
    self._milestone_random_pools = {}   # milestone_name → [{candidates, weights, count}]
    self._selected_random_pool_idx = 0  # 当前选中编辑的候选池索引

    # ── 全局总闸 ──
    self.milestone_enabled = QCheckBox("启用累抽奖励")
    self.milestone_enabled.setChecked(True)
    parent.addWidget(self.milestone_enabled)

    # ── 主布局：左列表 + 右详情 ──
    main_layout = QHBoxLayout()

    # 左侧——累抽列表 + 按钮
    left_layout = QVBoxLayout()
    self.milestone_list = QListWidget()
    self.milestone_list.currentRowChanged.connect(self._on_milestone_selected)
    left_layout.addWidget(self.milestone_list)

    btn_layout = QHBoxLayout()
    for text, slot in [("添加", self._add_milestone),
                       ("移除选中", self._remove_milestone)]:
        btn = QPushButton(text)
        btn.clicked.connect(slot)
        btn_layout.addWidget(btn)
    left_layout.addLayout(btn_layout)
    main_layout.addLayout(left_layout, 1)

    # 右侧——详情面板
    detail_group = QGroupBox("累抽详情")
    detail_group.setEnabled(False)
    self._milestone_detail_group = detail_group
    detail_form = QFormLayout(detail_group)

    # 基础字段——所有信号实时写回数据（_flush_milestone_current_detail），无需"应用修改"按钮
    self.ml_name_edit = QLineEdit()
    detail_form.addRow("名称:", self.ml_name_edit)

    self.ml_threshold_spin = QSpinBox()
    self.ml_threshold_spin.setRange(1, 9999)
    self.ml_threshold_spin.setValue(40)
    detail_form.addRow("触发阈值(抽):", self.ml_threshold_spin)

    self.ml_repeat_check = QCheckBox("可重复触发")
    detail_form.addRow("触发模式:", self.ml_repeat_check)

    self.ml_max_triggers_spin = QSpinBox()
    self.ml_max_triggers_spin.setRange(0, 999)
    self.ml_max_triggers_spin.setValue(0)
    self.ml_max_triggers_spin.setToolTip("0 = 无限触发")
    detail_form.addRow("最大触发次数:", self.ml_max_triggers_spin)

    self.ml_pools_edit = QLineEdit()
    self.ml_pools_edit.setPlaceholderText("留空 = 全部池子，或逗号分隔的池子 ID")
    detail_form.addRow("适用池子:", self.ml_pools_edit)

    # ── 奖励配置（三区域并行） ──
    detail_form.addRow(QLabel(""))  # 分隔
    detail_form.addRow("── 奖励配置（可同时填写多区域） ──", QLabel(""))

    # 固定卡牌
    self.ml_cards_list = QListWidget()
    self.ml_cards_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
    self.ml_cards_list.setMaximumHeight(100)
    detail_form.addRow("固定赠送卡牌:", self.ml_cards_list)

    # 资源
    self.ml_resources_table = QTableWidget()
    self.ml_resources_table.setColumnCount(2)
    self.ml_resources_table.setHorizontalHeaderLabels(["资源", "数量"])
    self.ml_resources_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    self.ml_resources_table.setMaximumHeight(120)
    detail_form.addRow("赠送资源:", self.ml_resources_table)

    res_btn_layout = QHBoxLayout()
    add_res_btn = QPushButton("添加")
    add_res_btn.clicked.connect(self._add_milestone_resource)
    remove_res_btn = QPushButton("移除选中")
    remove_res_btn.clicked.connect(self._remove_milestone_resource)
    res_btn_layout.addWidget(add_res_btn)
    res_btn_layout.addWidget(remove_res_btn)
    res_btn_layout.addStretch()
    detail_form.addRow(res_btn_layout)

    # 随机卡——摘要行 + 弹窗编辑
    self.ml_random_summary = QLabel("（无）")
    detail_form.addRow("随机卡:", self.ml_random_summary)

    rand_btn_layout = QHBoxLayout()
    edit_rand_btn = QPushButton("编辑")
    edit_rand_btn.clicked.connect(self._edit_milestone_random_pool)
    add_rand_btn = QPushButton("添加")
    add_rand_btn.clicked.connect(self._add_milestone_random_pool)
    remove_rand_btn = QPushButton("移除选中")
    remove_rand_btn.clicked.connect(self._remove_milestone_random_pool)
    rand_btn_layout.addWidget(edit_rand_btn)
    rand_btn_layout.addWidget(add_rand_btn)
    rand_btn_layout.addWidget(remove_rand_btn)
    rand_btn_layout.addStretch()
    detail_form.addRow(rand_btn_layout)

    main_layout.addWidget(detail_group, 2)
    parent.addLayout(main_layout)

    # ── 自动写入 + 预览信号（仿 _flush_pity_current_detail 模式） ──
    # 所有控件变更 → 实时写回 self._milestone_defs[row] → 触发预览
    for w in [self.ml_name_edit, self.ml_pools_edit]:
        w.textChanged.connect(self._flush_milestone_current_detail)
    for w in [self.ml_threshold_spin, self.ml_max_triggers_spin]:
        w.valueChanged.connect(self._flush_milestone_current_detail)
    self.ml_repeat_check.stateChanged.connect(self._flush_milestone_current_detail)
    self.milestone_enabled.stateChanged.connect(self._update_preview)
    # ⚠ 资源表修改（_add_milestone_resource / _remove_milestone_resource）→ _flush_milestone_current_detail() → _update_preview()
    # ⚠ 随机卡池修改（_add/_remove/_edit_milestone_random_pool）→ _flush_milestone_current_detail() → _update_preview()
    # ⚠ 500ms 去抖保证多重触发仅执行一次 _do_update_preview，预览数据流完整 <!-- REVIEW-R1-FIX: ISSUE-006 -->

def _populate_milestone_cards_list(self):
    """从 store.card_defs 填充固定卡牌 QListWidget——每行 [稀有度] 名称 (card_id)。"""
    self.ml_cards_list.clear()
    if not self._store:
        return
    for cid, entry in self._store.card_defs.items():
        rarity = getattr(entry, 'rarity', '?').upper()
        display = f"[{rarity}] {entry.name} ({cid})"
        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, cid)
        # 稀有度着色
        color_map = {'SSR': QColor(255, 215, 0), 'SR': QColor(160, 80, 220), 'R': QColor(100, 149, 237)}
        item.setForeground(color_map.get(rarity, QColor(0, 0, 0)))
        self.ml_cards_list.addItem(item)

def _on_milestone_selected(self, row):
    """选中左侧累抽条目 → 刷新右侧详情面板。"""
    # 先刷回当前编辑
    self._flush_milestone_current_detail()
    if row < 0 or row >= len(self._milestone_defs):
        self._milestone_detail_group.setEnabled(False)
        return
    md = self._milestone_defs[row]
    self._milestone_detail_group.setEnabled(True)

    # 基础字段
    self.ml_name_edit.setText(md.get('name', ''))
    self.ml_threshold_spin.setValue(md.get('threshold', 40))
    self.ml_repeat_check.setChecked(md.get('repeat', False))
    self.ml_max_triggers_spin.setValue(md.get('max_triggers', 0))
    self.ml_pools_edit.setText(','.join(md.get('pools', [])) if isinstance(md.get('pools'), list) else str(md.get('pools') or ''))  <!-- REVIEW-R1-FIX: ISSUE-003: 防御 None 值 → setText(None) 显示为 'None' -->

    # 奖励：固定卡牌
    card_ids = set(md.get('bonus_reward', {}).get('cards', []))
    for i in range(self.ml_cards_list.count()):
        item = self.ml_cards_list.item(i)
        cid = item.data(Qt.ItemDataRole.UserRole)
        item.setSelected(cid in card_ids)

    # 奖励：资源
    resources = md.get('bonus_reward', {}).get('resources', {})
    self.ml_resources_table.setRowCount(len(resources))
    for i, (res_id, amount) in enumerate(resources.items()):
        self.ml_resources_table.setItem(i, 0, QTableWidgetItem(res_id))
        amt_item = QTableWidgetItem()
        amt_item.setData(Qt.ItemDataRole.EditRole, amount)
        self.ml_resources_table.setItem(i, 1, amt_item)

    # 奖励：随机卡摘要
    self._milestone_random_pools[md['name']] = md.get('bonus_reward', {}).get('random_cards', [])
    self._update_milestone_random_summary()

def _flush_milestone_current_detail(self):
    """从右侧控件读取当前值 → 实时写回 self._milestone_defs[row]。"""
    row = self.milestone_list.currentRow()
    if row < 0 or row >= len(self._milestone_defs):
        return
    md = self._milestone_defs[row]

    md['name'] = new_name = self.ml_name_edit.text().strip() or f"milestone_{row+1}"
    # 更名时迁移 _milestone_random_pools 键——防止随机卡池静默丢失
    old_name = self.milestone_list.item(row).text()
    if old_name != new_name and old_name in self._milestone_random_pools:
        self._milestone_random_pools[new_name] = self._milestone_random_pools.pop(old_name)
    md['threshold'] = self.ml_threshold_spin.value()
    md['repeat'] = self.ml_repeat_check.isChecked()
    md['max_triggers'] = self.ml_max_triggers_spin.value()
    pools_text = self.ml_pools_edit.text().strip()
    md['pools'] = [p.strip() for p in pools_text.split(',') if p.strip()] if pools_text else []

    # 固定卡牌
    cards = []
    for i in range(self.ml_cards_list.count()):
        item = self.ml_cards_list.item(i)
        if item.isSelected():
            cards.append(item.data(Qt.ItemDataRole.UserRole))
    md.setdefault('bonus_reward', {})['cards'] = cards

    # 资源
    resources = {}
    for i in range(self.ml_resources_table.rowCount()):
        res_item = self.ml_resources_table.item(i, 0)
        amt_item = self.ml_resources_table.item(i, 1)
        if res_item and amt_item:
            rid = res_item.text().strip()
            if rid:
                resources[rid] = float(amt_item.data(Qt.ItemDataRole.EditRole) or 0)
    md.setdefault('bonus_reward', {})['resources'] = resources

    # 随机卡——从 _milestone_random_pools 回写 <!-- REVIEW-R1-FIX: ISSUE-030 -->
    pools = self._milestone_random_pools.get(md['name'], [])
    md.setdefault('bonus_reward', {})['random_cards'] = list(pools)

    self.milestone_list.item(row).setText(md['name'])
    self._update_preview()

def _add_milestone(self):
    """添加新累抽条目——默认占位，选中后编辑。"""
    <!-- REVIEW-R1-FIX: ISSUE-001 —— 搜索不冲突编号替代 len()+1 自增 -->
    existing = {d['name'] for d in self._milestone_defs}
    n = 1
    while f'milestone_{n}' in existing:
        n += 1
    md = {'name': f'milestone_{n}', 'threshold': 40,
          'repeat': False, 'max_triggers': 0, 'pools': [],
          'bonus_reward': {'cards': [], 'resources': {}, 'random_cards': []}}
    self._milestone_defs.append(md)
    self.milestone_list.addItem(md['name'])
    self.milestone_list.setCurrentRow(len(self._milestone_defs) - 1)

def _remove_milestone(self):
    """移除选中的累抽条目。"""
    row = self.milestone_list.currentRow()
    if row < 0:
        return
    name = self._milestone_defs[row]['name']
    del self._milestone_defs[row]
    self._milestone_random_pools.pop(name, None)
    self.milestone_list.takeItem(row)
    if row < len(self._milestone_defs):
        self.milestone_list.setCurrentRow(row)
    self._update_preview()

# ── 资源子表操作 ──

def _add_milestone_resource(self):
    row = self.ml_resources_table.rowCount()
    self.ml_resources_table.insertRow(row)
    self.ml_resources_table.setItem(row, 0, QTableWidgetItem(''))
    amt_item = QTableWidgetItem()
    amt_item.setData(Qt.ItemDataRole.EditRole, 0)
    self.ml_resources_table.setItem(row, 1, amt_item)
    self._flush_milestone_current_detail()

def _remove_milestone_resource(self):
    row = self.ml_resources_table.currentRow()
    if row >= 0:
        self.ml_resources_table.removeRow(row)
        self._flush_milestone_current_detail()

# ── 随机卡池操作 ──

def _add_milestone_random_pool(self):
    """追加一个空候选池。"""
    row = self.milestone_list.currentRow()
    if row < 0:
        return
    md = self._milestone_defs[row]
    pools = self._milestone_random_pools.setdefault(md['name'], [])
    pools.append({'candidates': [], 'weights': [], 'count': 1})
    self._update_milestone_random_summary()
    self._flush_milestone_current_detail()

def _remove_milestone_random_pool(self):
    """移除当前选中的候选池（基于内部索引，在 _edit 弹窗中维护）。"""
    # 通过 ml_random_summary 的 tooltip 存储当前选中池索引
    row = self.milestone_list.currentRow()
    if row < 0:
        return
    md = self._milestone_defs[row]
    pools = self._milestone_random_pools.get(md['name'], [])
    idx = getattr(self, '_selected_random_pool_idx', -1)
    if 0 <= idx < len(pools):
        pools.pop(idx)
        self._selected_random_pool_idx = max(0, idx - 1)
        self._update_milestone_random_summary()
        self._flush_milestone_current_detail()

def _edit_milestone_random_pool(self):
    """打开 RandomCardPoolDialog 编辑当前候选池。"""
    row = self.milestone_list.currentRow()
    if row < 0:
        return
    md = self._milestone_defs[row]
    pools = self._milestone_random_pools.setdefault(md['name'], [])
    idx = getattr(self, '_selected_random_pool_idx', 0)
    if idx >= len(pools):
        idx = 0
    dialog = RandomCardPoolDialog(self._store, pools[idx], self)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        pools[idx] = dialog.result()
        self._update_milestone_random_summary()
        self._flush_milestone_current_detail()

def _update_milestone_random_summary(self):
    """刷新随机卡摘要 QLabel。"""
    row = self.milestone_list.currentRow()
    if row < 0:
        self.ml_random_summary.setText("（无）")
        return
    md = self._milestone_defs[row]
    pools = self._milestone_random_pools.get(md['name'], [])
    if not pools:
        self.ml_random_summary.setText("（无）")
        return
    lines = []
    for i, pool in enumerate(pools):
        names = [c[:6] for c in pool.get('candidates', [])]
        w_hint = ''
        weights = pool.get('weights', [])
        if weights and not all(w == 1.0 for w in weights):
            varied = [f"{c[:6]}={w}" for c, w in zip(names, weights) if w != 1.0]
            w_hint = f" ({', '.join(varied)})" if varied else ''
        lines.append(f"池{i+1}: {', '.join(names[:3])}{'...' if len(names)>3 else ''}, 抽{pool.get('count',1)}张{w_hint}")
    self.ml_random_summary.setText('\n'.join(lines))
```

`RandomCardPoolDialog` 为独立 `QDialog`（四列勾选/卡/稀有度/权重表格 + 抽取张数 `QSpinBox`），详见图示。

#### 3.8.5a 现有方法适配（M7c——独立于 M7a Tab 骨架与 M7b1 RandomCardPoolDialog / M7b2 奖励编辑器）<!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->

<!-- REVIEW-R1-FIX: ISSUE-001 -->
**`apply_to_store()` 追加 milestone 同步：** 在方法末尾（`store.card_weights` 写入之后）追加 ~10 行：

```python
# apply_to_store() 末尾追加 —— 将 UI 层的 self._milestone_defs 写回 ConfigStore
store.milestone.enabled = self.milestone_enabled.isChecked()
store.milestone.milestones = []
for md in self._milestone_defs:
    store.milestone.milestones.append(MilestoneDef(
        name=md.get('name', ''),
        threshold=md.get('threshold', 40),
        repeat=md.get('repeat', False),
        max_triggers=md.get('max_triggers', 0),
        pools=tuple(md.get('pools', [])),  # tuple 类型与 PityDef.pools 一致<!-- REVIEW-R1-FIX: ISSUE-006 -->
        bonus_reward=md.get('bonus_reward', {'cards': [], 'resources': {}, 'random_cards': []}),
    ))
```

模式与 `store.pity.pities` 写入（L3925-3969）一致——遍历 UI 内部 dict 列表 → 转换为 dataclass → 赋值到 store。

<!-- REVIEW-R1-FIX: ISSUE-002 -->
**`set_config()` 追加 milestone 回填：** 在方法末尾（`self.refresh_from_store()` 之前）追加 ~10 行：

```python
# set_config() 末尾追加 —— 从 ConfigStore 回填里程碑 UI
self._milestone_defs = []
self.milestone_list.clear()
self.milestone_enabled.setChecked(store.milestone.enabled)
for md in store.milestone.milestones:
    self._milestone_defs.append({
        'name': md.name,
        'threshold': md.threshold,
        'repeat': md.repeat,
        'max_triggers': md.max_triggers,
        'pools': list(md.pools),
        'bonus_reward': {
            'cards': list(md.bonus_reward.get('cards', [])),
            'resources': dict(md.bonus_reward.get('resources', {})),
            'random_cards': list(md.bonus_reward.get('random_cards', [])),
        },
    })
    self.milestone_list.addItem(md.name)
```

模式仿照 `_pity_defs` 回填逻辑（L3408-3478）：遍历 store 中的 dataclass → 转换为 UI dict → 追加到 `self._milestone_defs` → 刷新 `QListWidget`。

<!-- REVIEW-R1-FIX: ISSUE-003 -->
**`get_config()` 追加 `milestone` 键：** 在返回字典中（`'card_weights'` 之前或之后）追加：

```python
'milestone': {
    'enabled': store.milestone.enabled,
    'milestones': [
        {'name': m.name, 'threshold': m.threshold, 'repeat': m.repeat,
         'max_triggers': m.max_triggers, 'pools': m.pools, 'bonus_reward': m.bonus_reward}
        for m in store.milestone.milestones
    ],
},
```

`_do_update_preview()` 中使用 `config.get('milestone', {})` 读取——追加此前缺失的键后，预览摘要中累抽奖励段可正常渲染。

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
| M1 | `MilestoneDef` + `MilestoneConfig` dataclass + `ConfigStore` 新增 `milestone` 字段（import `OverflowBand` from P63）+ `ConfigStore.clear()` 追加 `self.milestone = MilestoneConfig()` 重置 <!-- REVIEW-R1-FIX: ISSUE-007 --> | `config_store.py` | ~26 |
| M2 | `_build_milestone()` 解析 + `save_toml()` 写出 `[[milestone]]` 段 | `config_toml.py` | ~35 |
| M3 | `MilestoneEngine` 实现——计数器自管 + 触发判定 + `_resolve_bonus()`（使用 `self._rng`） | `core/milestone.py` | ~55 |
| M4 | `gacha_service` 集成——`__init__` 新增 `milestone_engine` 参数 + 模拟循环中 bonus 消费 + `StrategyContext` 传入 | `gacha_service.py` | ~20 |
| M4b | `SimulationEnv` 新增 `milestone_defs` 字段；`SimulationEnvBuilder.from_config_store()` 提取配置；`_run_single` 中 `MilestoneEngine(defs, seed=seed)` 延迟构造 | `batch_simulator.py` | ~15 |
| M4a | `StrategyContext` 新增 `_milestone_engine` 字段 + 3 个查询方法；`build_strategy_context()` (`strategy_context_builder.py`) 签名新增 `_milestone_engine` 参数并透传；`gacha_service.py` 调用处传入 `self.milestone_engine` <!-- REVIEW-R1-FIX: ISSUE-004 --> | `strategy.py` + `strategy_context_builder.py` + `gacha_service.py` | ~25 |
| M5 | `collector.on_bonus()` + `CompactResult.bonus_events`（**含 `pool_id` 字段**）+ `to_dict()`/`from_dict()` 序列化 + `SharedResultCollector` 同步（含 `_update_cumulative()` 中的 bonus 卡注入，解决流式路径遗漏<!-- REVIEW-R1-FIX: ISSUE-005 -->）<!-- REVIEW-R1-FIX: GATE-1-变更粒度 —— 行数 ~30→~40 反映跨文件协调成本（collector.py + result_types.py + streaming.py 三文件 + to_dict/from_dict 因 dataclasses.asdict 零成本但需验证自动同步正确性）。可选拆分：M5a「collector + result_types 序列化」（~15行）→ M5b「流式路径适配」（~15行——streaming.py 五条路径统一改用合并后 card_counts 作为输入源） --> | `collector.py` + `result_types.py` + `streaming.py` | ~40 |
| M5a | GDR 层合并 `bonus_events`——`_merge_milestone_cards()`（合并 `card_counts` + `pool_card_counts`）+ `real_time→draw_index` 映射。代码位于 `gdr.py`（compact/cumulative 入口均在此）；若历史路径也需合并，`generalized_drop_rate.py` 也需改动 <!-- REVIEW-R1-FIX: ISSUE-009 --><!-- REVIEW-R1-FIX: ISSUE-011 --> | `gdr.py` | ~25 |
| M7a | 配置面板 Tab 骨架——`_setup_milestone_config` 基础布局：总闸开关 + QListWidget 左列表 + QGroupBox 右详情 + 基础字段控件（名称/阈值/repeat/max_triggers/pools）+ `_on_milestone_selected` + `_add_milestone` + `_remove_milestone` + 信号连接骨架（不含奖励区域）<!-- REVIEW-R1-FIX: GATE-1-变更粒度 --> | `config_panel.py` | ~60 |
| M7b1 | `RandomCardPoolDialog` 独立 QDialog 类——四列勾选/卡/稀有度/权重表格（从 `self._store.card_defs` 填充）+ 权重列 `QDoubleSpinBox` + 抽取张数 `QSpinBox` + 确定/取消按钮 + `result()` 方法返回 `{candidates, weights, count}`。不依赖里程碑编辑器其他控件，可独立开发与测试<!-- REVIEW-R1-FIX: GATE-1-变更粒度 --> | `config_panel.py` | ~35 |
| M7b2 | 奖励编辑器 CRUD + 回写逻辑——固定卡牌 QListWidget（含 `_populate_milestone_cards_list`）+ 资源 QTableWidget（含 `_add/_remove_milestone_resource`）+ 随机卡摘要行（`_update_milestone_random_summary`）+ 随机卡池 CRUD（`_add/_remove/_edit_milestone_random_pool`，依赖 M7b1 的 `RandomCardPoolDialog`）+ `_flush_milestone_current_detail` 全量回写逻辑。M7b1 提供 Dialog 后串行集成<!-- REVIEW-R1-FIX: GATE-1-变更粒度 --> | `config_panel.py` | ~45 |
| M7c | 现有方法适配——`apply_to_store()` 里程碑写入（~10行）<!-- REVIEW-R1-FIX: ISSUE-001 --> + `set_config()` 里程碑回填（~10行）<!-- REVIEW-R1-FIX: ISSUE-002 --> + `get_config()` 追加 `milestone` 键（~8行）<!-- REVIEW-R1-FIX: ISSUE-003 --> + Tab 注册到 `_setup_ui()`（~7行）<!-- REVIEW-R1-FIX: GATE-1-变更粒度 --> | `config_panel.py` | ~35 |
| M8 | 集成测试（7 个 G20 场景的 TOML 配置 → 模拟 → 验证期望输出）+ 单元测试（MilestoneEngine._resolve_bonus、_build_milestone 解析器、TOML round-trip、collector 序列化闭环）<!-- REVIEW-R1-FIX: GATE-6-测试策略 --> | `tests/` | ~130 |
| M9 | P61 协作——`MilestoneEngine.after_draw` 扩展 banner_id 参数 + `_on_after_draw` 订阅函数（替代 M4 inline，逻辑不变）+ `[[milestone]].banner` 字段解析 + `MilestoneDef.banner` 过滤。依赖 P61-Ph0（notifier.py） | `milestone.py` + `gacha_service.py` + `config_toml.py` | ~15 |
| **总计** | | | **~630** |

> ~~M6（`resources_gained` 解析遗漏修复）已删除——P63 已修复 TOML 管道。~~ M4b 新增——`batch_simulator.py` 的 `SimulationEnv`/`SimulationEnvBuilder` 需传递 `milestone_config`。M5 行数上调至 ~40 以反映跨文件协调成本（`collector.py` + `result_types.py` + `streaming.py` 三文件 + `to_dict`/`from_dict` 序列化自动同步验证）。**M7 拆分为 M7a / M7b1 / M7b2 / M7c 四个 ≤1 小时子阶段**（分别 ~60/~35/~45/~35 行，保守估计各 20-50 分钟）。M7b1（`RandomCardPoolDialog` 独立 QDialog）先于 M7b2（奖励编辑器 CRUD + 回写）串行执行——M7b2 的 `_edit_milestone_random_pool` 依赖 M7b1 提供的 Dialog。M8 行数上调至 ~130 以覆盖 GATE-6 单元测试（~50 行）与集成测试（~80 行）。<!-- REVIEW-R1-FIX: GATE-1-变更粒度 / GATE-6-测试策略 / UPDATED TOTALS -->

<!-- REVIEW-R1-FIX: GATE-6-测试策略 -->
### 四、附：M8 单元测试范围声明

M8 测试分为两层——**单元测试（~50 行）**覆盖核心引擎逻辑的独立正确性，**集成测试（~80 行）**覆盖端到端数据流（TOML → 模拟 → collector → GDR）。

#### A. 单元测试（4 个模块，~50 行）

| 编号 | 测试目标 | 输入 | 期望输出 | 对应验收项 |
|:---:|------|------|------|------|
| UT1 | `MilestoneEngine._resolve_bonus()` | 构造 `MilestoneDef(name="test", bonus_reward={'cards': ['a','b'], 'resources': {'c': 5}, 'random_cards': [{'candidates': ['x','y'], 'weights': [1.0,1.0], 'count': 1}]})`，传入 `engine._rng = random.Random(42)` 固定 seed | `result['card_ids']` 含 `['a','b']` + 1 张随机卡（固定 seed 下确定）；`result['resources'] == {'c': 5}`；`_resolve_bonus` 不修改 `engine._counters`/`_active`/`_triggered` | `bonus_reward.cards` / `bonus_reward.resources` / `bonus_reward.random_cards` 解析正确 + 随机卡可复现 |
| UT2 | `_build_milestone()` 解析器 | 最小合法 TOML dict：`{'milestone': [{'name': 'test', 'threshold': 10, 'repeat': True, 'bonus_reward': {'cards': ['a'], 'resources': {}, 'random_cards': []}}]}` → 传入 `ConfigStore()` | `store.milestone.milestones` 长度为 1；`milestones[0].name == 'test'`；`milestones[0].threshold == 10`；`milestones[0].repeat == True`；`milestones[0].pools == ()` （空元组=全部池子） | `[[milestone]]` 独立 TOML 段解析正确 + `pools` 正确过滤 |
| UT3 | TOML round-trip | 构造 `MilestoneConfig(milestones=[MilestoneDef(...)])` → 写入 TOML → `load_toml()` 读回 → 构造新 `ConfigStore` | 读回的 `store.milestone.milestones` 与原始相等：`name`/`threshold`/`repeat`/`max_triggers`/`pools`/`bonus_reward` 逐字段一致。`random_cards` 内嵌列表/数字完整保真（无字符串化退化） | TOML 段 round-trip 保真——GUI 编辑 → 保存 → 重载后字段不丢失 |
| UT4 | collector `on_bonus()→to_dict()→from_dict()` 序列化闭环 | 构造 `CompactCollector` → 调用 `on_bonus(milestone_name="m1", card_ids=["a","b"], resources={"coin":500}, pool_id="pool_1", real_time=10.0)` → `to_dict()` → `from_dict()` 重构 `CompactResult` | 重构后 `result.bonus_events[0]['milestone_name'] == 'm1'`；`card_ids == ['a','b']`；`resources == {'coin': 500}`；`pool_id == 'pool_1'`；`real_time == 10.0`。并行模拟不丢数据 | `CompactResult.to_dict()`/`from_dict()` 正确序列化/反序列化 `bonus_events` |

#### B. 集成测试（8 组场景，~80 行）

覆盖 §1.1a 中 7 个 G20 场景 + S1 同抽多触发 + 空抽计数 + 溢出 + 流式五路径 + 方案 A/B 互斥 + `run_batch_parallel` 单进程兜底路径。各场景具体期望已在 §1.1a 表格中列明。

#### C. 验收项与测试层级映射

以下将 §八 中全部 45 条 checklist 逐条标注覆盖来源——**UT**=单元测试覆盖，**IT**=集成测试覆盖，**设计保证**=代码结构保证（如默认值守卫、类型约束）、无需独立测试用例。

| 验收项关键词 | 覆盖层级 |
|------|:---:|
| `[[milestone]]` 独立 TOML 段解析正确 | UT2 + IT（场景 1-7 均依赖 TOML 解析） |
| `bonus_reward.cards` 直入 `state.acquired` | UT1 + IT（场景 5 含 card 赠送） |
| `bonus_reward.resources` 归入 `rg`（P63 单通道） | UT1 + IT（场景 1/2/3/5/6/7 含资源） |
| `bonus_reward.random_cards` 加权随机抽取可复现 | UT1（固定 seed）+ IT（场景 4） |
| cards+resources+random_cards 同时配置生效 | UT1（三字段并存）+ IT（场景 3 含 card+resource） |
| repeat=false 触发后永久停用 | IT（场景 3：150 抽仅 1 次 bonus_events） |
| repeat=true 触发后归零继续 | IT（场景 1：25 抽触发 2 次） |
| max_triggers 正确限制 | IT（需追加专用场景：repeat=true, max_triggers=2 → 3 次触发后 is_active=False） |
| pools 正确过滤 | UT2（空→全部，非空→fnmatch）+ IT（场景 4/5 限定单池） |
| bonus 不触发常规保底重置 | IT（含保底配置的 milestone 场景→验证保底计数器不受影响） |
| milestone 卡溢出（P63 管道） | IT（里程碑卡溢出场景：满突后赠送→`combined_gained` 含溢出资源） |
| milestone 溢出资源+直接资源归入 rg | IT（同溢出场景） |
| collector.on_bonus() 只存元数据 | UT4（序列化后不含资源金额字段）+ IT |
| SharedResultCollector 同步 | IT（流式路径——需 SharedResultCollector 场景） |
| CompactResult.to_dict()/from_dict() 序列化 | UT4 |
| GDR 合并 bonus_events | IT（场景含 milestone→GDR 计算验证 bonus 卡入出率） |
| GDR 合并不改函数签名 | 设计保证（`_merge_milestone_cards()` 入口调用，不修改 `compute_gdr_from_compact` 签名） |
| PityEngine 零改动 | 设计保证（无 `import milestone`）+ 代码审查（git diff 确认 `pity.py` 无变更） |
| BEHAVIOR_REGISTRY 不含 milestone | 设计保证（不注册 type）+ 代码审查（grep `milestone` in `pity.py`） |
| 7 个 G20 场景验证 | IT（§1.1a 表格，7 个场景各 1 个用例） |
| 配置面板「累抽奖励」Tab | 手动验收（UI 组件——pytest 不覆盖 PyQt6 渲染，建议手动 checklist 或 pytest-qt） |
| StrategyContext 查询里程碑 | UT（mock MilestoneEngine 注入 StrategyContext→验证 get_milestone_counter/is_active/get_defs 返回值） |
| 策略层接口只读 | 设计保证（`StrategyContext` 不暴露 `_milestone_engine._counters` 等写方法） |
| 不存在里程碑时安全默认值 | UT（`_milestone_engine=None`→查询返回 0/False/{}） |
| MilestoneEngine.__init__ 接收 seed | UT1（固定 seed 后 `_resolve_bonus` 可复现） |
| ConfigStore.clear() 重置 | UT（`clear()` 后 `store.milestone == MilestoneConfig()`） |
| SimulationEnv.from_dict() 支持 milestone_defs | IT（`run_batch_parallel` 路径→验证 pickle 序列化/反序列化不丢失 `milestone_defs`） |
| build_strategy_context 含 _milestone_engine | 设计保证（签名审查）+ IT（策略集成场景） |
| apply_to_store 写回 | 手动验收（UI 组件，建议 pytest-qt） |
| set_config 回填 | 手动验收（同上） |
| get_config 含 milestone 键 | UT（调用 `get_config()`→断言 `'milestone' in result`） |
| bonus_events 含 pool_id | UT4（构造 bonus_events→验证 `pool_id` 字段存在） |
| 流式五路径含 bonus 卡 | IT（流式路径专用场景：milestone 赠卡→`streaming._update_cumulative` + 4 条 Worker/DrawSeq 路径→验证 bonus 卡贡献入热力图/转变标记/累积快照） |
| 方案 A/B 互斥 | IT（§1.1a 方案 A/B 互斥断言：若实施方案 A，`card_counts['milestone_card']` = `sum(...)` + bonus 卡不被双重计入） |
| 里程碑卡溢出 | IT（满突后赠送→溢出资源正确入账 `milestone_rg`） |
| 空抽计数推进 | IT（`_NO_CARD_ID` 抽数→计数器正常推进） |
| 同抽多触发顺序确定性 | IT（场景 S1：50 抽同时触发 2 个 milestone→顺序验证） |
| 场景 1 具体期望 | IT（25 抽→bonus_events=2, resources=2） |
| 场景 3 具体期望 | IT（150 抽→bonus_events=1, card_counts['limited_ssr_1']=1, is_active=False） |
| 场景 4 具体期望 | IT（80 抽+固定 seed→赠卡确定+候选集内） |
| 场景 5 具体期望 | IT（300 抽→card+resource 同时交付） |
| CLAUDE.md 同步 | 代码审查（git diff 确认 CLAUDE.md 包含新条目） |
| pytest 全量通过 | CI（`pytest -q` 全量 + 新测试无回归） |
<!-- /REVIEW-R1-FIX: GATE-6-测试策略 -->

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
├── SimulationEnv.card_overflow_map → GachaService.card_overflow_map            ← 构建链完整
└── ✅ `docs/00-meta/模块状态矩阵.md` 行 65 P63 已手动更新为「✅ 完成」<!-- REVIEW-R1-FIX: ISSUE-004 -->
   —— P63 核心代码（OverflowBand、state.add_card()、card_overflow_map）已落地。
   2026-07-30 plan-review R2 修正：不再依赖 C1 cron，已在本次审查中直接修正矩阵状态。

P61-Ph0（待实施 —— 2026-08-01 新增）
├── core/notifier.py（subscribe/emit/priority）                      ← M9 使用
├── after_draw 事件契约（banner_id/pool_id/card_id/pity_triggered + state/collector） ← M9 订阅
└── Ph0 交付后 P58 与 P61 完全并行；M1-M8 零依赖 P61，仅 M9 依赖 Ph0

本计划（P58——独立 MilestoneEngine）
├── 零依赖 PityEngine / BEHAVIOR_REGISTRY
├── 零依赖 CounterBasedBehavior / PityState
├── 零依赖 P55 / P56
└── 与 P55 / P56 / P63 / P61(M1-M8) 完全并行——改不同文件、不同 TOML 段、不同 UI Tab
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
| `core/config_store.py` | **修改** | 新增 `MilestoneDef` + `MilestoneConfig` dataclass；`ConfigStore` 新增 `milestone` 字段；`ConfigStore.clear()` 追加 `self.milestone = MilestoneConfig()` 重置行 <!-- REVIEW-R1-FIX: ISSUE-007 -->；import `OverflowBand`（P63） |
| `core/config_toml.py` | **修改** | 新增 `_build_milestone()` + `save_toml()` 新段 |
| `core/milestone.py` | **新建** | `MilestoneEngine` 独立调度器——import `OverflowBand` / `match_overflow_bands`（P63） |
| `core/collector.py` | **修改** | 新增 `on_bonus` 抽象方法 + `CompactCollector` 实现 |
| `core/result_types.py` | **小改** | `CompactResult` 新增 `bonus_events` 字段 + `to_dict()`/`from_dict()` 序列化 |
| `core/gdr.py` | **修改** | GDR compact/cumulative 入口合并 `bonus_events`——`_merge_milestone_cards()`（~20行，P63 未碰此项）。compact 入口 `compute_gdr_from_compact()`(L935) + cumulative 入口 `compute_gdr_from_cumulative()`(L1104) 均在此文件。若历史路径也需要合并，`generalized_drop_rate.py` 也需修改——波及表明确两份文件各自改动 <!-- REVIEW-R1-FIX: ISSUE-009 --> |
| `service/gacha_service.py` | **修改** | `__init__` 新增 `milestone_engine` 参数 + 模拟循环中 bonus 消费 + `StrategyContext` 传入 `_milestone_engine`（~20 行） |
| `service/batch_simulator.py` | **修改** | `SimulationEnv` 新增 `milestone_defs: List[MilestoneDef]` 字段（非 `MilestoneEngine`——延迟构造）；`SimulationEnvBuilder.from_config_store()` 提取 `store.milestone.milestones`；`_run_single` 中 `MilestoneEngine(env.milestone_defs, seed=seed)` 构造并传入 `GachaService`。**`SimulationEnv.from_dict()` 同步追加 `milestone_defs=config.get('milestone_defs', [])`** ——确保 `worst_impact.py` 等非 ConfigStore 调用方不丢失 milestone 配置（~1行）<!-- REVIEW-R1-FIX: ISSUE-006 -->。**文件头部 import 需追加：** `from gacha_simulator.core.config_store import MilestoneDef`——当前 `from __future__ import annotations` 已启用延迟求值，亦可使用 `TYPE_CHECKING` 块延迟导入以防循环依赖 <!-- REVIEW-R1-FIX: ISSUE-002 -->（~15行总计） |
| `core/strategy.py` | **修改** | `StrategyContext` 新增 `_milestone_engine` + 3 个查询方法（~20 行） |
| `core/strategy_context_builder.py` | **修改** | `build_strategy_context()` 签名新增 `_milestone_engine` 参数，透传到 `StrategyContext`——确保 `future_resource_gains` / `inter_pool_pity_links` 派生字段不丢失（~5行） <!-- REVIEW-R1-FIX: ISSUE-004 --> |
| `gui/config_panel.py` | **修改** | 新增 `_setup_milestone_config()` + 联动方法 + Tab 注册（~100行，M7a）。`RandomCardPoolDialog` 独立 QDialog 类（~35行，M7b1）。奖励编辑器 CRUD 方法（`_populate_milestone_cards_list` / `_add/_remove_milestone_resource` / `_add/_remove/_edit_milestone_random_pool` / `_update_milestone_random_summary`）+ `_flush_milestone_current_detail` 全量回写逻辑（~45行，M7b2，依赖 M7b1）。**同时适配 3 个现有方法：** `apply_to_store()` 追加 `store.milestone.milestones` 写入（~10行）<!-- REVIEW-R1-FIX: ISSUE-001 -->、`set_config()` 追加里程碑回填（~10行）<!-- REVIEW-R1-FIX: ISSUE-002 -->、`get_config()` 追加 `'milestone'` 键（~8行）<!-- REVIEW-R1-FIX: ISSUE-003 --> + Tab 注册（~7行，M7c）<!-- REVIEW-R1-FIX: GATE-1-变更粒度 --> |
| `config/config.toml` | **更新** | 新增 `[[milestone]]` 示例段 |
| `tests/` | **新增** | ~130 行测试（M8）。单元测试（~50行）：`MilestoneEngine._resolve_bonus()` 独立测试、`_build_milestone()` 解析器测试、TOML round-trip（构造→保存→加载→断言相等）、collector `on_bonus()→to_dict()→from_dict()` 序列化闭环。集成测试（~80行）：7 个 G20 场景期望输出验证 + 同抽多触发顺序 + 空抽计数 + 里程碑卡溢出 + 流式五路径 + 方案 A/B 互斥 + `run_batch_parallel` 单进程兜底路径<!-- REVIEW-R1-FIX: GATE-6-测试策略 / GATE-1-变更粒度 --> |
| `CLAUDE.md` | **修改** | 扩展指南表格新增「新里程碑」行，架构分层注释新增 `core/milestone.py` 条目。`StrategyContext` 关键识别附注新增 `_milestone_engine` 字段说明 <!-- REVIEW-R1-FIX: ISSUE-012 --> |
| `scripts/profile_sim.py` + `scripts/profile_simulation.py` | **不修改（向下兼容）** | 两个性能分析脚本直接构造 `GachaService`（`profile_sim.py` L87-90 / `profile_simulation.py` L99-104），均传入显式关键字参数。`GachaService.__init__` 新增 `milestone_engine` 参数后，因默认值 `None` 向下兼容，当前无需修改。若未来性能基准需启用里程碑，需在构造时追加 `milestone_engine=...` 参数。是否启用留待性能基准设计时决定。<!-- REVIEW-R1-FIX: ISSUE-028 --> |

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
| `apply_to_store()` 缺少里程碑写入逻辑——GUI 编辑无法持久化到 TOML | **M7c 追加：** 在 `apply_to_store()` 中遍历 `self._milestone_defs` 转换为 `MilestoneDef` 实例写入 `store.milestone.milestones`（~10行）。模式与 `store.pity.pities` 写入一致 <!-- REVIEW-R1-FIX: ISSUE-001 / GATE-1-变更粒度 --> |
| `set_config()` 缺少里程碑回填——加载配置后 UI 不显示里程碑 | **M7c 追加：** 在 `set_config()` 末尾从 `store.milestone.milestones` 反序列化到 `self._milestone_defs` + 刷新 `milestone_list`（~10行）。模式仿照 `_pity_defs` 回填逻辑（L3408-3478） <!-- REVIEW-R1-FIX: ISSUE-002 / GATE-1-变更粒度 --> |
| `get_config()` 返回字典缺少 `milestone` 键——预览摘要始终为空 | **M7c 追加：** `get_config()` 返回字典追加 `'milestone': {'enabled': ..., 'milestones': [...]}` 键（~8行）。`_do_update_preview()` 合成摘要代码已为此适配 <!-- REVIEW-R1-FIX: ISSUE-003 / GATE-1-变更粒度 --> |
| `build_strategy_context()` 未纳入波及范围——`StrategyContext` 构造绕过此函数将丢失派生字段 | **波及范围追加 `strategy_context_builder.py`：** `build_strategy_context()` 签名新增 `_milestone_engine` 参数，`gacha_service.py` 调用处传入 `self.milestone_engine` <!-- REVIEW-R1-FIX: ISSUE-004 --> |
| 流式路径 `_update_cumulative()` / `WorkerLocalExtractor.process()` / `DrawSequenceExtractor._update_heatmap()` / `DrawSequenceExtractor._update_transition()` 均遍历 `draw_card_ids` 构建热力图/转变标记/累积快照——bonus 卡不在 `draw_card_ids` 中，流式 GDR/热力图/转变标记将遗漏里程碑产出 | **M5 追加——统一合并策略：** 所有四条路径（`_update_cumulative` / `WorkerLocalExtractor.process` 内联热力图+转变标记 / `_update_heatmap` / `_update_transition`）统一改用已合并的 `card_counts`（方案 A 下由 `CompactCollector.on_bonus()` 提前注入）作为输入源，而非仅遍历原始 `draw_card_ids`。或在进入遍历前构建 `merged_card_ids`（正常 draw 序列 + bonus 赠卡按 `real_time` 定位插入）。`real_time → draw_index` 映射共用 `_time_to_draw_index()` 工具函数 <!-- REVIEW-R1-FIX: ISSUE-004 --> |
| `SimulationEnv.from_dict()` 遗漏 `milestone_defs` 参数——`worst_impact.py` 等调用方丢失 milestone 配置 | **波及范围追加 `from_dict`：** `SimulationEnv.from_dict()` 追加 `milestone_defs=config.get('milestone_defs', [])`（与 `card_overflow_map` 占位模式一致） <!-- REVIEW-R1-FIX: ISSUE-006 --> |
| `ConfigStore.clear()` 遗漏 `self.milestone = MilestoneConfig()`——连续 `set_config()` 间状态残留 | **M1 追加：** `clear()` 末尾追加 `self.milestone = MilestoneConfig()`（1行）。虽非功能阻塞（`set_config()` 开头 `clear()` 后立即覆盖），但违反全量清零契约 <!-- REVIEW-R1-FIX: ISSUE-007 --> |
| `InfoVectorCollector` 继承空 `on_bonus` 实现——历史路径 `compute_gdr_from_history()` 将静默丢失里程碑数据 | **已知限制（标注）：** `InfoVectorCollector` 不实现 `on_bonus`——历史路径 GDR 不反映 milestone 产出。批量模拟主流使用 compact 路径，历史路径为边缘场景。若后续需支持，需新建 `InfoVector` 动作类型 `milestone_gift` <!-- REVIEW-R1-FIX: ISSUE-008 --> |
| GDR 波及范围表指向 `generalized_drop_rate.py`——但 `compute_gdr_from_compact`/`compute_gdr_from_cumulative` 实际在 `gdr.py` | **波及范围表修正：** M5a 目标文件改为 `gdr.py`，`_merge_milestone_cards()` 位于 `gdr.py` 中，在 compact/cumulative 入口处调用。若历史路径也需合并，`generalized_drop_rate.py` 也需修改——波及表明确两份文件各自改动 <!-- REVIEW-R1-FIX: ISSUE-009 --> |
| 计划 §3.6a 伪代码使用 `result.card_sequence`——实际字段是 `result.draw_card_ids` | **伪代码修正：** `card_sequence` → `draw_card_ids` <!-- REVIEW-R1-FIX: ISSUE-010 --> |
| `pool_card_counts` 未纳入 milestone 合并——per-pool GDR 分析遗漏里程碑产出 | **bonus_events 增加 `pool_id` 字段：** `after_draw(pool_id)` 已知触发池，`on_bonus`/`bonus_events` 同时存储 `pool_id`。合并时同步更新 `pool_card_counts` <!-- REVIEW-R1-FIX: ISSUE-011 --> |
| 计划波及范围表未含 `CLAUDE.md`——重大架构变更后未同步项目指令文件 | **波及范围表追加一行：** `CLAUDE.md`——扩展指南表格新增「新里程碑」行，架构分层注释新增 `core/milestone.py` 条目 <!-- REVIEW-R1-FIX: ISSUE-012 --> |
| `run_batch_parallel` 单进程兜底路径（L307-325）与 `_wk_run_single` worker 路径（L242-267）是否正确构造 `MilestoneEngine` 并传入 `GachaService`——当前 plan-review 审查仅覆盖计划文件与靶向代码，未执行集成测试环境验证 | **M4b 实施后、M8 集成测试中追加：** 专门针对 `run_batch_parallel` 单进程兜底路径的测试用例——验证 `_run_single` 内部正确构造 `MilestoneEngine(defs, seed=seed)` 并传入 `GachaService.__init__`。同时验证 `_wk_env.milestone_defs` 经 pickle 正确序列化/反序列化（`SimulationEnv.from_dict()` 需含 `milestone_defs`）。当前 M8 仅计划 7 个 G20 场景 TOML 配置测试——需追加至少 1 个批量并行路径覆盖用例。参见 ISSUE-006 <!-- REVIEW-R1-FIX: ISSUE-006 --> |

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
- [ ] GDR 合并不改函数签名——在 `compute_gdr_from_compact` / `compute_gdr_from_cumulative` 入口处完成（`compute_gdr_from_history` 不存在；历史路径通过 `GeneralizedDropRate` 子类直接迭代 `InfoVector`，无统一入口函数）<!-- REVIEW-R1-FIX: ISSUE-005 -->
- [ ] `PityEngine` 零改动——milestone 完全不参与保底管道
- [ ] `BEHAVIOR_REGISTRY` 不含 `milestone` 条目
- [ ] 7 个 G20 场景的 TOML 配置 → 模拟 → 产出验证通过
- [ ] 配置面板「累抽奖励」Tab 可完整编辑所有字段；修改后触发全局预览刷新（`_update_preview` → `_do_update_preview` 含 milestone 摘要段）
- [ ] `StrategyContext` 可查询里程碑计数器、活跃状态、定义信息（threshold / bonus_reward）
- [ ] 策略层接口只读——不能通过 `StrategyContext` 修改里程碑计数器
- [ ] 不存在里程碑配置时，`StrategyContext` 查询返回安全默认值（0 / False / 空 dict）
- [ ] `MilestoneEngine.__init__` 接收 `seed` 参数——`random.Random(seed)` 保证随机卡抽取可复现
- [ ] `ConfigStore.clear()` 重置 `self.milestone = MilestoneConfig()`——全量清零契约不违反
- [ ] `SimulationEnv.from_dict()` 支持 `milestone_defs` 参数——`worst_impact.py` 等调用方不丢失配置
- [ ] `build_strategy_context()` (`strategy_context_builder.py`) 签名含 `_milestone_engine` 参数——派生字段（`future_resource_gains` / `inter_pool_pity_links`）不丢失
- [ ] `apply_to_store()` 将 `self._milestone_defs` 写回 `store.milestone.milestones`——GUI 编辑可持久化到 TOML
- [ ] `set_config()` 回填 `self._milestone_defs`——加载已有配置后里程碑 Tab 正确显示
- [ ] `get_config()` 返回字典含 `'milestone'` 键——`_do_update_preview()` 中里程碑摘要可正常渲染
- [ ] `bonus_events` 含 `pool_id` 字段——per-pool GDR 分析可正确归因里程碑产出
- [ ] 流式路径 `_update_cumulative()` 包含 bonus 卡——流式 GDR 不遗漏 milestone 产出<!-- REVIEW-R1-FIX: GATE-6-测试策略-流式路径 -->
- [ ] 流式路径 `WorkerLocalExtractor.process()` 热力图分箱包含 bonus 卡贡献——不遗漏<!-- REVIEW-R1-FIX: GATE-6-测试策略-流式路径 -->
- [ ] 流式路径 `WorkerLocalExtractor.process()` 转变标记包含 bonus 卡贡献——不遗漏<!-- REVIEW-R1-FIX: GATE-6-测试策略-流式路径 -->
- [ ] 流式路径 `DrawSequenceExtractor._update_heatmap()` 热力图分箱包含 bonus 卡贡献——不遗漏<!-- REVIEW-R1-FIX: GATE-6-测试策略-流式路径 -->
- [ ] 流式路径 `DrawSequenceExtractor._update_transition()` 转变标记包含 bonus 卡贡献——不遗漏<!-- REVIEW-R1-FIX: GATE-6-测试策略-流式路径 -->
- [ ] 方案 A/B 互斥——若实施 `on_bonus` 源头合并（方案 A），`_merge_milestone_cards()` 不再写入 `pool_card_counts`，milestone 卡不被双重计入；`card_counts['milestone_card']` 恰好等于 bonus_events 中该卡出现次数（`sum(1 for ev in bonus_events for cid in ev['card_ids'] if cid == 'milestone_card')`）<!-- REVIEW-R1-FIX: GATE-6-测试策略-方案AB互斥 -->
- [ ] 里程碑卡溢出——满突后 milestone 赠送触发 `match_overflow_bands()`，溢出资源正确入账 `milestone_rg`；`combined_gained` 反映溢出金额<!-- REVIEW-R1-FIX: GATE-6-测试策略-溢出 -->
- [ ] 空抽计数推进——`_NO_CARD_ID` 抽数正常计入累抽进度；计数器值 = `after_draw` 调用次数（含空抽）<!-- REVIEW-R1-FIX: GATE-6-测试策略-空抽计数 -->
- [ ] 同抽多触发顺序确定性——第 50 抽同时触发 threshold=10 和 threshold=50 两个 milestone；`bonus_events` 顺序 = TOML `[[milestone]]` 定义顺序（`for name, md in self._defs.items()` 迭代顺序即 dict 插入顺序 = TOML 数组顺序）<!-- REVIEW-R1-FIX: GATE-6-测试策略-同抽多触发顺序 -->
- [ ] 场景 1（火影每 10 抽碎片）——25 抽 → `len(bonus_events) == 2`，`resources['fragment_s'] == 2`<!-- REVIEW-R1-FIX: GATE-6-测试策略-具体期望 -->
- [ ] 场景 3（火影首付返利）——150 抽 → `len(bonus_events) == 1`，`card_counts['limited_ssr_1'] == 1`，`is_active('naruto_first_payback_s') == False`<!-- REVIEW-R1-FIX: GATE-6-测试策略-具体期望 -->
- [ ] 场景 4（阴阳师 40 抽随机 SSR）——80 抽、固定 seed → `sum(card_counts.values())` 赠卡 == 1，且候选卡在 `ssr_candidates` 集合内；重复模拟同 seed → 同一张卡（可复现性）<!-- REVIEW-R1-FIX: GATE-6-测试策略-具体期望 -->
- [ ] 场景 5（明日方舟 300 抽）——bonus 同时含 card + resource；`card_counts['limited_operator'] == 1` 且 `resources['exchange_currency'] >= 300`（含正常产出溢出）<!-- REVIEW-R1-FIX: GATE-6-测试策略-具体期望 -->
- [ ] `CLAUDE.md` 扩展指南 + 架构分层同步更新 `core/milestone.py` 条目
- [ ] pytest 全量通过

---
<!-- REVIEW-R1-FIX: GATE-5-回滚路径 -->
## 九、回滚策略

整体原则：各阶段独立可逆——`MilestoneEngine` 不存在时 `gacha_service` 无行为变化（`milestone_engine=None` 默认值向下兼容），所有新增文件/字段可单独删除而不影响现有功能。

| 阶段 | 回滚操作 | 影响范围 |
|:---:|------|------|
| M1 | 删除 `config_store.py` 中 `MilestoneDef` / `MilestoneConfig` 类定义 + `ConfigStore.milestone` 字段 + `ConfigStore.clear()` 中 `self.milestone = MilestoneConfig()` 行 | dataclass 定义与字段——删除后其他阶段引用此类型的 import 需同步清理 |
| M2 | 删除 `config_toml.py` 中 `_build_milestone()` 函数定义 + `load_toml()` 中对其的调用 + `save_toml()` 中 `# milestone` 写入段 | TOML 解析/写出——删除后已有 `[[milestone]]` 段被静默忽略（无 crash），不影响其他 TOML 段的读写 |
| M3 | 删除 `core/milestone.py` 整个文件 | 新文件——零波及。`gacha_service.py` / `batch_simulator.py` 中的 import 需同步移除（或无 import 则无需操作） |
| M4 | 无需操作——`GachaService.__init__` 中 `milestone_engine: Optional[MilestoneEngine] = None` 默认值已保证无里程碑时不执行 bonus 逻辑；若已删除 M3 文件，移除 `milestone_engine` 参数以清理签名亦可 | 无行为变化——`if _milestone_engine:` 守卫在 `None` 时跳过整个 bonus 消费块 |
| M4a | 无需操作——`StrategyContext._milestone_engine` 默认 `None`，三个查询方法均返回安全默认值（`0` / `False` / `{}`）；若已删除 M3 文件，可移除 `build_strategy_context()` 的 `_milestone_engine` 参数和 `StrategyContext` 中的字段与方法体 | 无行为变化——策略层查询始终返回安全默认值 |
| M4b | 无需操作——`SimulationEnv.milestone_defs` 默认空列表导致 `MilestoneEngine` 构造时收到空 `_defs`，`after_draw()` 无任何判定；若已删除 M3 文件，移除 `SimulationEnv` 字段 + `SimulationEnvBuilder` 提取行 + `_run_single` 构造调用 | `batch_simulator.py` 中删去 3 处：`SimulationEnv` dataclass 字段 + `from_config_store()` 提取 + `_run_single` 构造 |
| M5 | 删除 `collector.py` 中 `on_bonus` 方法定义 + `CompactCollector.on_bonus` 实现 + `CompactResult.bonus_events` 字段；移除 `to_dict()`/`from_dict()` 中 `bonus_events` 的序列化逻辑 + `streaming.py` 中 bonus 合并代码 | collector + result_types + streaming 三文件回滚——`bonus_events` 列表始终为空时对下游无影响，但需清理代码以防误导 |
| M5a | 删除 `gdr.py` 中 `_merge_milestone_cards()` 函数定义及 compact/cumulative 入口处的调用 | GDR 计算回退为不含里程碑产出的裸出率——与删除 `[[milestone]]` TOML 段后重跑等效 |
| M7a | 删除 `config_panel.py` 中 `_setup_milestone_config()` 方法体 + `_setup_ui()` 中「累抽奖励」Tab 注册行 + left_tabs 中的 `addTab` 调用 | 仅 UI 层——`store.milestone` 数据仍存在但 Tab 不显示。调用方 `_setup_ui()` 中仅移除 `addTab` 行 |
| M7b1 | 删除 `config_panel.py` 中 `RandomCardPoolDialog` 类定义 | 若 M7b2 也回滚（其 `_edit_milestone_random_pool` 依赖此 Dialog），需同步删除引用 |
| M7b2 | 删除 `config_panel.py` 中 `_populate_milestone_cards_list` / `_add_milestone_resource` / `_remove_milestone_resource` / `_add_milestone_random_pool` / `_remove_milestone_random_pool` / `_edit_milestone_random_pool` / `_update_milestone_random_summary` / `_flush_milestone_current_detail` 方法体；移除 `_on_milestone_selected` 中奖励相关控件回填逻辑 | 仅 UI 层——里程碑数据 `self._milestone_defs` 仍存在但编辑入口消失 |
| M7c | 删除 `apply_to_store()` 中 `store.milestone.milestones` 写入段 + `set_config()` 中 `self._milestone_defs` 回填段 + `get_config()` 返回字典中 `'milestone'` 键 | 仅 UI→store 数据流断裂——里程碑 TOML 段仍可手工编辑，但 GUI 无法读写 |
| M8 | 删除 `tests/` 中里程碑相关测试文件/函数 | 测试套件回退为不含里程碑覆盖——已有测试不受影响 |

**回滚验证方法：**
1. 执行相应阶段的回滚操作
2. 运行 `pytest -q`——确认无 import 错误或测试失败
3. 删除已有 `[[milestone]]` TOML 段后运行模拟——确认无 crash
4. 若仅回滚 M7（UI 层），启动 GUI——确认「累抽奖励」Tab 不存在且其他 Tab 正常

**最简回滚路径（整体回退 P58）：** 删除 `core/milestone.py` 文件 + 移除 `config_store.py` 中新增 dataclass/字段 + 移除 `gacha_service.py` 中 bonus 消费块（`if _milestone_engine:` 块） + 移除 `config_panel.py` 中里程碑 UI 方法——其余所有代码因默认值守卫（`None` / 空列表 / 安全默认值）自动退化为无行为。
<!-- /REVIEW-R1-FIX: GATE-5-回滚路径 -->

---

## ⚠ 自动化审查阻塞项

6 轮对抗循环未收敛。标注原因：6 轮对抗循环未收敛。

以下 0 个未解决问题及详情: []
