<!-- META: P58 | module:模拟服务层 | status:designing | last:2026-08-01 | depends:P60✅,P63✅,P61-Ph0(待) -->
<!-- ⚠ R2 审查编号冲突已按预见处理：本次 R2 审查问题列表实际编号为 ISSUE-310..314（全局唯一，与既有 R1 的
     REVIEW-R1-FIX: ISSUE-301..309 指代内容不重叠），修复标注统一用 REVIEW-R1-FIX: ISSUE-310..314 并附内容描述；
     如需彻底全局唯一前缀命名空间，仍须人工裁决 R2 前缀（如 REVIEW-R2-FIX）后全局替换。 -->

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

#### 1.1a 各场景具体期望输出（M8 测试输入/输出规范）<!-- REVIEW-FIX-PREV: GATE-6-测试策略 -->

以下为 7 个 G20 场景的 M8 集成测试期望——每个场景定义：输入 TOML 配置 → 模拟 N 抽 → 期望 bonus_events 长度、期望 card_counts 中的赠送卡计数、期望资源入账金额。

| # | 场景 | 模拟抽数 | bonus_events 长度 | card_counts 期望 | 资源期望 | 关键断言 |
|---|------|:---:|:---:|---|---|---|
| 1 | 火影每 10 抽碎片 | 25 抽 | 2 | `card_counts` 不含赠送（无 card） | `resources['fragment_s'] ≈ 2` | repeat=true, threshold=10; 第 10/20 抽各触发一次；milestone 不修改概率 |
| 2 | 火影 50 抽大保底碎片 | 120 抽 | 2 | 同 1——无 card | `resources['fragment_s'] ≈ 10`（5x2） | repeat=true, threshold=50; 第 50/100 抽触发 |
| 3 | 火影首付返利（S忍 100 抽） | 150 抽 | 1 | `card_counts['limited_ssr_1'] == 1`（**M8 测试配置保证 `limited_ssr_1` 不在任何池 distribution——仅作赠卡，否则 150 抽自然抽到 ≥1 张破坏 `== 1` 断言，REVIEW-R1-FIX: ISSUE-107**） | `resources['coin'] ≈ 500` | repeat=false, threshold=100; 触发后 `is_active=false`；第 100-150 抽不再次触发 |
<!-- REVIEW-R1-FIX: ISSUE-107 —— 场景 3/5 断言 `card_counts[...] == 1` 依赖「赠卡不在池 distribution」测试配置约束（方案 A 下 card_counts 含赠卡+自然抽卡，自然抽到会破坏相等断言） -->
| 4 | 阴阳师 40 抽随机 SSR | 80 抽 | 1 | `sum(card_counts[c] for c in ssr_candidates) == 1`（**M8 测试配置保证 4 个 `ssr_candidates` 候选不在任何池 distribution——仅作赠卡候选，REVIEW-R1-FIX: ISSUE-307**） | 无资源 | repeat=false; 第 40 抽触发；随机卡从 4 候选中等权抽取；RNG seed 固定可复现 |
| 5 | 明日方舟 300 抽当期限定 | 300 抽 | 1 | `card_counts['limited_operator'] == 1`（**M8 测试配置保证 `limited_operator` 不在任何池 distribution——仅作赠卡，REVIEW-R1-FIX: ISSUE-107**） | `resources['exchange_currency'] ≈ 300` | repeat=false; cards + resources 同时交付 |
| 6 | 终末地 30 抽取送十连 | 30 抽 | 1 | 无 card | `resources['endfield_next_voucher'] ≈ 1` | 需先定义 `endfield_next_voucher` 资源类型（等价 10 连） |
| 7 | 终末地 60 抽寻访档案 | 60 抽 | 1 | 无 card | `resources['endfield_next_voucher'] ≈ 10` | at=60; 独立于场景 6 的 milestone |

**多触发顺序验证场景（追加——同抽触发多个 milestone）：**<!-- REVIEW-FIX-PREV: GATE-6-测试策略-同抽多触发顺序 -->

| # | 场景 | 模拟抽数 | bonus_events 顺序 | 关键断言 |
|---|------|:---:|---|---|
| S1 | 场景 1（threshold=10）+ 场景 2（threshold=50）共存 | 50 抽 | `['naruto_fragment', 'naruto_s_fragment']`（按 TOML 定义顺序） | 第 50 抽同时触发两个 milestone；bonus_events 列表顺序 = TOML `[[milestone]]` 定义顺序（确定性） |

**空抽（_NO_CARD_ID）计数推进验证：**<!-- REVIEW-FIX-PREV: GATE-6-测试策略-空抽计数 -->
- 若存在交换池或概率归零场景（`pool.draw()` 返回 `_NO_CARD_ID`），`MilestoneEngine.after_draw()` 仍被调用 → 计数器无条件递增 → 空抽计入累抽进度。验证：模拟包含 N 次空抽的序列 → 计数器值 = 实际调用 `after_draw` 次数（含空抽）。

**里程碑卡溢出验证：**<!-- REVIEW-FIX-PREV: GATE-6-测试策略-溢出 -->
- 若里程碑赠送的卡牌已达到满突上限（`initial_counts` 中已满），`state.add_card(cid, overflow_bands=card_overflow_map.get(cid), ...)` 应触发 `match_overflow_bands()` 并返回溢出资源（如星辉、井币）。验证：模拟前预设该卡已满突破 → milestone 触发 → 溢出资源注入 `resources`（可用性）并计入 `on_bonus` 归因（方案 C，2026-08-03）→ `final_resources` 与合并后 `draw_resources_gained[draw_index]` 反映溢出金额。

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
├─ MilestoneEngine.after_draw(banner_id, pool_id) → [bonus...]  ← 独立判定、独立注入
│   ├─ 计数器递增（自管，极简 int）
│   ├─ 达阈值 → 解析 bonus_reward
│   ├─ state.add_card()（milestone 卡/溢出）→ 资源注入 state.resources
│   └─ collector.on_bonus()（源头归因，on_draw 后，方案 C）
│
├─ 资源结算（正常产出溢出归入 rg；milestone 资源已注入 state.resources、不进 rg/combined_gained）
└─ collector.on_draw() → collector.on_bonus()（方案 C：卡/资源归因源头合并）
```

**关键约束：**
- MilestoneEngine 不触碰概率分布
- MilestoneEngine 不依赖 PityState——计数器自管
- bonus 资源注入（state.resources）发生在 PityEngine.after_draw() 之后、资源结算之前；`on_bonus` 归因记录在 `collector.on_draw()` 之后（方案 C，2026-08-03）
- collector.on_bonus() 独立于 on_draw()——归因元数据（事件名、触发池、draw_index、赠送内容、资源金额）走 on_bonus；milestone 资源【不】走 combined_gained，而是注入 state.resources + on_bonus 源头归因（方案 C，2026-08-03；P63 单通道约束仅限正常产出结算通道）
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

    def after_draw(self, banner_id: str, pool_id: str) -> List[dict]:
        """判定并返回触发的 bonus 列表。

        调用方（gacha_service）负责消费 bonus：
          - card 类型 → state.add_card(cid, path="milestone_gift",
              overflow_bands=card_overflow_map.get(cid),
              initial_counts=_initial_counts)
          - resource 类型 → 注入 state.resources（方案 C，2026-08-03；不并入当抽 combined_gained）
          - collector.on_bonus(...)

        banner_id 用于 MilestoneDef.banner 级过滤（P61 后裸 pool_id 非全局唯一）：
        P61 前（M4 inline）调用方传 ""（banner="" 匹配全部，M1-M8 行为）；
        P61 后经 after_draw 事件传入真实 banner_id（M9）。

        _NO_CARD_ID（空抽）行为：计数器无条件递增——只要 gacha_service 调用了
        after_draw() 即视为一次有效抽数。空抽（交换池/概率归零场景下 pool.draw()
        返回 _NO_CARD_ID）仍消耗资源/抽数，计数器应正常推进（符合绝大多数游戏的期望
        行为——「花了钱就算一抽」）。若特定游戏需排除空抽，调用方应在 after_draw()
        调用前加 `if reward.id != _NO_CARD_ID` 守卫——MilestoneEngine 本身不做此判断。<!-- REVIEW-FIX-PREV: ISSUE-005 -->
        """
        bonuses: List[dict] = []
        for name, md in self._defs.items():
            if not self._active[name]:
                continue
            if md.banner and banner_id != md.banner:
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
        """当前累计抽数（已抽次数）。余量 = md.threshold - get_counter(name)。

        REVIEW-R1-FIX: ISSUE-305 —— 原 docstring「距离下一里程碑还差几抽」与实现不符：
        返回的是累计已抽数，不是余量。策略示例（§3.5a）正确用
        `remaining = md.threshold - ctx.get_milestone_counter(name)` 计算余量，但原 docstring
        会误导插件策略作者直接写 `if ctx.get_milestone_counter(name) <= 5:`（方向完全相反：
        把「累计不足 5」误判为「即将触发」）。
        """
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

#### 3.2a SimulationEnvBuilder 构造点——完整返回语句修改 <!-- REVIEW-FIX-PREV: ISSUE-029 -->

在 `SimulationEnvBuilder.from_config_store()` 的 `return SimulationEnv(...)` 语句（`batch_simulator.py` L710-727）中标明新增的 `milestone_defs` 参数位置。插入于现有 `card_overflow_map` 行之后、右括号之前：

```python
# batch_simulator.py L710-727 —— SimulationEnvBuilder.from_config_store() 返回语句
# REVIEW-R1-FIX: ISSUE-302 —— 里程碑配置在 return 之前提取（避免在实参列表内赋值）：
#   必须加 enabled 总闸门控——否则用户取消「启用累抽奖励」（apply_to_store 写 enabled=False、
#   milestones 仍保留）后直接运行模拟，MilestoneEngine 仍被构造、里程碑照常触发，总闸运行时无任何效果。
#   与 pity 路径 _build_pity_engine_from_gui（batch_simulator.py L87 `if not pity_config.get('enabled', True):
#   return None`）的 enabled 语义对齐（两者组合成『禁用=无效+保存即删除』闭环时，此处为 runtime 侧修复）。
_ms_cfg = getattr(config_store, 'milestone', MilestoneConfig())
_milestone_defs = list(_ms_cfg.milestones) if _ms_cfg.enabled else []
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
    # 【P58 新增】里程碑配置——MilestoneEngine 在 _run_single 中延迟构造；enabled=False 时为空列表
    milestone_defs=_milestone_defs,
)
```

`getattr(config_store, 'milestone', MilestoneConfig())` 无里程碑配置时返回空列表（`MilestoneConfig().milestones = []`），`MilestoneEngine` 收到空列表后无操作——向下兼容。**REVIEW-R1-FIX: ISSUE-302——`enabled=False` 时 `milestone_defs` 同样为空列表**（见上方门控），`MilestoneEngine` 构造后 `after_draw()` 无任何判定，与 pity 的 `enabled` 语义一致。
<!-- REVIEW-R1-FIX: ISSUE-303 —— batch_simulator.py 顶部【没有】`from __future__ import annotations`（L1-16 仅 `from typing import ...`）：
   dataclass 字段注解在类定义时求值，`milestone_defs: List[MilestoneDef]` 若仅按 TYPE_CHECKING 块延迟导入会模块导入即 NameError。
   正确做法：batch_simulator.py 顶部显式追加 `from __future__ import annotations`（config_store 无循环 import 风险），
   并在文件头部模块级 `import MilestoneDef`（见波及范围表 batch_simulator.py 行修正）；「已启用延迟求值」的错误陈述已删除。 -->

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
    banner: str = ""   # 精确指向一个 Banner（P61 协作）。空字符串 = 不按 banner 过滤（全部）。
                       # 2026-08-02 修正（无历史包袱一次性迁移）：原 `pools`（裸 pool_id fnmatch）已删除——
                       # P61 后 pool_id 是 Banner 内部 id（跨 banner 重复），裸 pool_id 无法全局唯一；
                       # 统一用 banner 级过滤，与 P61 全限定键方向一致（原 pools 的 `"*"` 字符串语法兼容同步删除）


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
- `max_triggers` 默认值从 `1` 改为 `0`（0=无限触发），与 TOML 示例和文档一致。

**2026-08-02 修订（无历史包袱一次性迁移，与 P61 D4 全限定键方向一致）：**
- `pools` 字段**删除**，统一改用 `banner`（精确指向一个 Banner）。历史轨迹：原 `pools` 从 `str` 改为 `tuple`（2026-07-29，解决 `in` 子串误匹配），再演进为 P61 后的 `banner` 级过滤。**删除理由**：P61 引入 Banner 后裸 pool_id 非全局唯一（跨 banner 重复），`pools` 的裸 pool_id fnmatch 语义失效；且项目未上线（CLAUDE.md「无历史包袱原则」），一次性迁移、不保留新旧双路径。
- 匹配逻辑相应调整：`if md.banner and banner_id != md.banner: continue` —— banner 精确匹配，空字符串 = 全部。原 `fnmatch(pool_id, pat)` 的 pool 粒度过滤能力由「banner 级」取代（P61 后 pool 粒度用全限定键 `{banner_id}.{pool_id}`，未来如需要可扩展）。

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
banner = "onmyoji_limited"                       # 精确指向一个 Banner（空 = 全部）
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
banner = ""                                      # 空 = 全部 banner
bonus_reward = { resources = { fragment_s = 1 } }

# every=N：每 50 抽大保底碎片（火影忍者）
[[milestone]]
name = "naruto_s_fragment"
threshold = 50
repeat = true
max_triggers = 0
banner = ""
bonus_reward = { resources = { fragment_s = 5 } }

# at=N：100 抽首付返利——S 忍碎片 + 金币（火影忍者）
# cards + resources 可同时赠送
# 注：一次性里程碑推荐 repeat=false（非 repeat=true, max_triggers=1——二者外部行为等价，前者更清晰）
[[milestone]]
name = "naruto_first_payback_s"
threshold = 100
repeat = false
max_triggers = 1
banner = ""
bonus_reward = { cards = ["limited_ssr_1"], resources = { coin = 500 } }

# at=N：300 抽赠送当期限定 + 补偿资源（明日方舟）
[[milestone]]
name = "ak_300_gift"
threshold = 300
repeat = false
max_triggers = 1
banner = "ak_limited"
bonus_reward = { cards = ["limited_operator"], resources = { exchange_currency = 300 } }

# at=N：60 抽送跨期券（终末地）
[[milestone]]
name = "endfield_archive"
threshold = 60
repeat = false
max_triggers = 1
banner = "endfield_limited"
bonus_reward = { resources = { endfield_next_voucher = 10 } }
```

**REVIEW-R1-FIX: ISSUE-002 —— 示例段引用的卡/资源必须存在于配置：** 示例中 `ak_300_gift` 的 `cards=["limited_operator"]`、`onmyoji_40_gift` 的 `random_cards` 候选（`ssr_ibaraki`/`ssr_shuten`/`ssr_oomoji`/`ssr_kaguya`）当前不在 shipped `config.toml` 的 `[card]` 段（现有卡仅 `limited_ssr_1..6`/`standard_ssr_1..6`/`sr_*`/`r_*`）。ISSUE-101 校验（§3.7 `_build_milestone` 对 cards/random_cards 引用做 `known_card_ids` 存在性校验）实施后，按 §3.4 原样写入 config.toml 会在 `load_toml()` 抛 ConfigError，GUI/CLI 加载即失败。**config.toml 更新任务必须『新增 `[[milestone]]` 示例段并补全被引用卡/资源的 `[card]`/`[resources.defs]` 定义（如 `limited_operator`、`ssr_ibaraki` 等），或示例改用现有 `limited_ssr_1` 等卡』**。资源侧不对称说明：`_build_milestone` 对 `resources` 键【不校验】存在性（§3.7 校验 dict 类型 + 值数值类型——REVIEW-R1-FIX: ISSUE-303，键存在性仍不校验），示例的 `fragment_s`/`coin`/`exchange_currency`/`endfield_next_voucher` 若未在 `[resources.defs]` 定义会以幽灵资源键静默注入——需在 config.toml 一并补全资源定义（UI 侧已有 ISSUE-104 的 apply_to_store 未定义资源 ID 警告路径，但 shipped 配置仍需用户自查补全）。

**与 `[[pity]]` 的语法对比：**

| | `[[pity]]` | `[[milestone]]` |
|---|---|---|
| 核心参数 | `type` / `scope` / `start` / `end` | `threshold` / `repeat` |
| 概率相关 | 有（`func` / `increment` / `target_featured`） | 无——不操作概率 |
| 重置逻辑 | `reset`（出 SSR/featured/never） | 自管（触发后 repeat 决定） |
| 奖励 | 无——产出走 pool.draw() | `bonus_reward`（card / resource / random_card） |
| 作用范围 | `pools` fnmatch（裸 pool id） | `banner` 精确匹配（P61 后裸 pool id 非全局唯一） |
| 语义 | 「保底」——运气保护 | 「里程碑」——抽数奖励 |

### 3.5 gacha_service 集成

```python
# gacha_service.py —— 在 PityEngine.after_draw 之后、资源结算之前
# 插入位置：正常溢出合并 (gacha_service.py L340) 之后、rg → resources (L341) 之前<!-- REVIEW-FIX-PREV: ISSUE-001 -->

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

# ── 【新增】里程碑判定与注入（方案 C：资源独立归因，2026-08-03 决策）──
# 核心：milestone 资源（直接 + 溢出）当抽末注入 resources（玩家/策略视角「当抽即用」），
# 但【不并入】当抽 combined_gained——M9 时代 emit 在逐抽结算之后，P63 单通道不可回溯，
# 无法当抽并入。归因走 on_bonus 源头合并（§3.6）：记录完整资源金额 + draw_index（0-based
# 本抽索引），on_bonus 在 collector.on_draw【之后】调用（此时 draw_resources_gained 已 append
# 本抽），直接把资源并入该抽产出 + total_gained——对象与 to_dict() 产物一致，流式/主路径都覆盖。
# M4/M9 统一此形态，迁移行为等价。
bonus_pending: list = []   # 暂存待 on_bonus 的 bonus（on_bonus 延迟至 on_draw 后）
if _milestone_engine:
    for entry in _milestone_engine.after_draw("", pool.id):   # P61 前 banner=""（全部生效）；M9 后传真实 banner_id
        bonus = entry['bonus']
        milestone_res: dict = {}   # 归因资源累计（直接 + 溢出），随 bonus_events 记录
        # 直接资源——注入 resources（当抽末可用，不进 combined_gained）
        direct_res = bonus.get('resources', {})
        if direct_res:
            for k, v in direct_res.items():
                resources[k] = resources.get(k, 0) + v
                milestone_res[k] = milestone_res.get(k, 0) + v
        # 卡牌——经 P63 state.add_card() 统一管道，溢出资源同样注入 resources 并计入归因
        for cid in bonus.get('card_ids', []):
            overflow = state.add_card(
                cid,
                path="milestone_gift",
                overflow_bands=self.card_overflow_map.get(cid),
                initial_counts=_initial_counts,
            )
            for k, v in overflow.items():
                resources[k] = resources.get(k, 0) + v
                milestone_res[k] = milestone_res.get(k, 0) + v
        bonus_pending.append((entry['name'], bonus.get('card_ids', []), milestone_res))

# ── rg → resources + combined_gained → collector.on_draw（保持不变）──
#   milestone 资源不进 rg/combined_gained——当抽 combined_gained 仅含正常产出 + 挂账等待收益
collector.on_draw(...)

# ── on_bonus（collector.on_draw 之后）──
#   【M4 前置（REVIEW-R2-FIX: GATE-依赖顺序）】collector.on_bonus 的 ABC 具体 no-op 默认由 M4 提供
#   （M4 先于 M5-serial），本调用点在 M4 阶段即不 AttributeError；M5-serial 实现 CompactCollector 合并。
#   draw_resources_gained 已 append 本抽；draw_index = stats.total_draws - 1（stats.on_draw 已 +1）
for mname, cids, mres in bonus_pending:
    collector.on_bonus(
        milestone_name=mname,
        card_ids=cids,
        resources=mres,               # 归因数据（直接 + 溢出）
        pool_id=pool.id,              # ← per-pool 归因；M4（P61 前）裸 pool.id 与 draw_pool_ids 同键空间；M9 须换全限定 draw_pool_key（见 M9 段键空间约定）<!-- REVIEW-FIX-PREV: ISSUE-011 -->
        real_time=real_time,          # 审计时间戳（不用于归因——抽卡不推进 real_time）
        draw_index=stats.total_draws - 1,   # 0-based 本抽索引（归因钥匙，唯一单调）
    )

# ... 后续保持不变
```

**2026-07-29 修订——匹配 P63 实际 API：**
- `state.add_card()` 签名：`(card_id, path="milestone_gift", overflow_bands=card_overflow_map.get(cid), initial_counts=_initial_counts) → Dict[str, float]`
- `card_overflow_map` 来自 `GachaService.card_overflow_map`（由 `SimulationEnvBuilder` 从 `ConfigStore.card_overflow_map` 注入）
- 不再使用计划中原假设的 `bonus_config=` kwarg——P63 统一为 `overflow_bands=` 参数 + `match_overflow_bands()` 内部匹配
- `on_bonus` 参数 `pity_name` → `milestone_name`（语义修正）

**关键时序（2026-08-03 方案 C 修订——资源独立归因）：**<!-- REVIEW-FIX-PREV: ISSUE-001 + ISSUE-003 -->

```
before_draw → PityEngine.before_draw (不含 milestone)
  → pool.draw() → 正常出卡
  → PityEngine.after_draw → 常规保底重置（hard/soft 等，不含 milestone）
  → rg = dict(reward.resources_gained or {}) → 正常资源提取
  → state.add_card(reward.id, path="draw", overflow_bands=...) → 正常产出溢出 → rg（P63）
  → MilestoneEngine.after_draw → 达阈值 → 返回 bonus
  → 直接资源 + milestone 卡片溢出资源 → 注入 resources（当抽末可用，不进 combined_gained）
  → rg → resources + combined_gained（仅正常产出 + 挂账等待收益，不含 milestone）
  → collector.on_draw()
  → collector.on_bonus(..., draw_index=stats.total_draws - 1)   # 源头合并资源（on_draw 后）
```

M9 时代同时序但触发点变为 `notifier.emit("after_draw")` 订阅（结算后），资源注入语义「下一抽起可用」、统计经 bonus_events 事后归因——见下方「P61 协作（Notifier 集成）」段。

**P61 协作（Notifier 集成）—— 2026-08-01 新增 / 2026-08-03 方案 C 修订：**

P61 引入 Banner 抽象后，抽卡事件经 `core/notifier.py`（P61 Ph0 交付）分发。P58 通过订阅 `after_draw` 事件集成，替代 M4 的 inline 调用（资源注入逻辑与 M4 完全一致，约 15 行迁移）：

```python
# gacha_service.py —— 模拟循环中（P61 已 emit，契约见 P61 §3.5）
# P61 侧新增 draw_index=stats.total_draws（1-based 当前抽数）——方案 C 归因钥匙来源
# REVIEW-R1-FIX: ISSUE-006 —— pool_id 必须用全限定 draw_pool_key（{banner_id}.{pool_id}），
#   与 draw_pool_ids 同键空间（§3.5 键空间约定）——禁止用裸 pool.id/banner.active_pool_id
notifier.emit("after_draw",
              banner_id=banner.id, pool_id=draw_pool_key,   # ← 全限定 draw_pool_key
              card_id=reward.id, pity_triggered=triggered,
              draw_index=stats.total_draws,     # 方案 C 新增（P61 契约扩展点）
              state=state, collector=collector)

# P58 模块中 —— 订阅函数（资源注入逻辑与上方 M4 inline 完全一致）
# REVIEW-R1-FIX: ISSUE-006 —— 不依赖模块级 _milestone_engine（Windows spawn 下重置为 None），
#   从装配注入点读取；装配契约见下方「M9 装配契约」
def _on_after_draw(banner_id, pool_id, card_id, pity_triggered, draw_index, state, collector):
    engine = _resolve_milestone_engine(state)   # ← 装配点注入（见下方）
    if engine:
        for entry in engine.after_draw(banner_id, pool_id):
            # ... 消费 bonus（与 M4 代码相同：资源注入 state.resources + on_bonus）
            # on_bonus 的 draw_index 参数 = draw_index - 1（0-based 本抽索引）...

notifier.subscribe("after_draw", _on_after_draw, priority=0)   # P58 资源注入先于 P61 生命周期检查
```

**REVIEW-R1-FIX: ISSUE-006——M9 装配契约（P61 协作）：**
- **notifier 来源**：`core/notifier.py` 的 `notifier` 实例由 P61 装配层创建并经 `GachaService.__init__(notifier=...)` 注入（P61 §5.4 装配函数 `register_milestone_engine(gacha_service)`）。P58 **不自行创建** notifier 实例；M9 阶段在 P61 装配层注册订阅（`register_milestone_engine` 内调 `notifier.subscribe`），而非在 `_run_single` 循环内直接引用未定义的 `notifier` 变量。
- **milestone_engine 来源**：**禁止模块级全局 `_milestone_engine`**——Windows spawn 模式下子进程模块级全局重置为 `None`（P61 ISSUE-329 同款问题）。装配点 = `_run_single` 内构造的 `MilestoneEngine(env.milestone_defs, seed=seed)` 实例，经闭包捕获传入 `_on_after_draw`（`functools.partial` 或工厂函数绑定），或存入 per-simulation 局部作用域。
- **键空间**：emit 侧 `pool_id` 传全限定 `draw_pool_key`（`{banner_id}.{pool_id}`）——与 `draw_pool_ids` 同键空间（§3.5 键空间约定）。禁止 M9 迁移时漏换为裸 `pool.id`/`banner.active_pool_id`。
- **M4 删除**：M9 落地时必须**显式删除 M4 inline 里程碑消费块**（`bonus_pending`/`_milestone_engine.after_draw("", pool.id)` 那一段）——否则同一抽双次 `after_draw`（inline + 事件订阅双触发）、计数器双递增、资源双重注入。M9 阶段表已列为显式子任务。

**关键变更：**
- `after_draw` 事件契约：`banner_id / pool_id / card_id / pity_triggered + draw_index + state / collector`（P61 §3.5 定义；`draw_index` 为方案 C 扩展字段，2026-08-03）
- **方案 C 归因钥匙**：`bonus_events` 存 `draw_index = 契约 draw_index - 1`（0-based 本抽索引），合并时直接索引 `draw_resources_gained`。**不用 real_time**——抽卡不推进 real_time（仅 WaitAction 推进，gacha_service L372-374），连续无等待抽卡共享同一 real_time 值，无法唯一定位一抽；`stats.total_draws` 每抽 +1（L37）单调唯一，`total_draws - 1` 即本抽在 `draw_resources_gained` 的索引（L107 每抽 append）
- **`pool_id` 键空间约定（2026-08-03 语义审查）**：`on_bonus` 的 `pool_id` 恒与 `draw_pool_ids` **同键空间**——M4（P61 前）传裸 `pool.id`（此时 `draw_pool_ids` 亦裸键）；M9（P61 后）须传 emit 契约的 `draw_pool_key`（全限定 `{banner_id}.{pool_id}`，此时 `draw_pool_ids` 亦全限定，ISSUE-006）。禁止 M9 迁移时漏换为裸 `pool.id`——否则 `bonus_events['pool_id']`/`pool_card_counts` 与 `draw_pool_ids` 键空间分裂、per-pool GDR 错配
- `MilestoneEngine.after_draw(banner_id, pool_id)` 签名含 banner_id：P61 后 pool_id 是 Banner 内部 id（跨 banner 重复），用 banner_id 做 banner 级过滤（`MilestoneDef.banner`，精确匹配，空 = 全部）；P61 前调用方传 `""`
- 订阅 priority=0：P58（资源注入）先于 P61（生命周期检查），避免「P61 切换池时 P58 资源未注入」的竞态
- `[[milestone]]` 用 `banner` 字段（精确指向一个 Banner）；原 `pools` 字段已删除（2026-08-02 无历史包袱迁移，见 §3.3 修订）——不再有「pools 保留兼容旧 pool_id 过滤」的双路径
- 依赖 P61-Ph0（core/notifier.py）+ **P61 emit 契约含 `draw_index` 字段**。Ph0 交付后 P58 与 P61 完全并行；M1-M8 零依赖 P61（此时 banner 过滤用 `banner=""`，全部生效），M9 依赖 Ph0 与契约字段

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
        """当前累计抽数（已抽次数），不存在 → 0。余量 = md.threshold - get_milestone_counter(name)。"""
        # REVIEW-R1-FIX: ISSUE-305 —— 与 MilestoneEngine.get_counter() 同源修正（§3.2）：docstring 原写
        #   「距离触发还差几抽」同样误导——本方法返回累计数，余量须由策略自行计算
        #   `remaining = md.threshold - ctx.get_milestone_counter(name)`（见下方策略使用示例）。
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
# (future_resource_gains / inter_pool_pity_links)<!-- REVIEW-FIX-PREV: ISSUE-004 -->
# 【阶段边界（REVIEW-R2-FIX: GATE-依赖顺序）】`__init__` 的 milestone_engine 参数属于 M4；
#   下方 build_strategy_context 传参 + 签名变更统一属于 M4a（gacha_service L228 唯一接线点，
#   M4 不碰此处）——两阶段以函数/文件边界分隔、各自验收，M4a 依赖 M4 的 self.milestone_engine 属性。
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
    _milestone_engine: Optional['MilestoneEngine'] = None,  # ← 新增 <!-- REVIEW-FIX-PREV: ISSUE-004 -->
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
                 resources: Dict[str, float], pool_id: str, real_time: float,
                 draw_index: int):
        """milestone 注入事件——记录归因元数据并源头合并卡/资源。
        pool_id 用于 per-pool GDR 分析归因。<!-- REVIEW-FIX-PREV: ISSUE-011 -->
        draw_index 为 0-based 本抽索引（归因钥匙）。方案 C（2026-08-03）：milestone 资源
        注入 state.resources（当抽末可用）、【不并入】当抽 combined_gained（P63 单通道不可回溯、
        M9 emit 在逐抽结算之后）；on_bonus 在 collector.on_draw【之后】调用，把 resources 源头
        并入 draw_resources_gained[draw_index] 与 total_gained——对象与 to_dict() 产物一致，
        流式/主路径均覆盖，无需统计层再合并（§3.6a）。
        参数名用 milestone_name 而非 pity_name——语义准确。
        """
# ⚠ 实现注意（2026-08-03 语义审查）：本方法必须为【具体 no-op 默认实现】，【不可】标 @abstractmethod——
#   InfoVectorCollector（run_simulation 默认 collector，gacha_service L180-183）不重写 on_bonus，
#   若标 abstractmethod 则无法实例化，无 milestone 配置时任何模拟即 TypeError。
#   InfoVectorCollector 继承空实现 → 历史路径静默丢弃 milestone 产出（已知限制，风险表 ISSUE-008）。
#   【M4 前置（REVIEW-R2-FIX: GATE-依赖顺序）】ABC 具体 no-op 默认由 M4 阶段提供——M4 先于 M5-serial，
#   而 M4 的 §3.5 内联消费块已调用 collector.on_bonus(...)，若 on_bonus 到 M5-serial 才存在，M4 阶段
#   带里程碑配置跑模拟即 AttributeError。M4 提供 ABC no-op 默认后，M4 验收须含里程碑配置路径
#   （不崩溃、产出静默丢弃属预期）；M5-serial 实现 CompactCollector.on_bonus 具体合并逻辑。

# CompactCollector
def on_bonus(self, ...):
    r = self._result
    r.bonus_events.append({
        'milestone_name': milestone_name,
        'card_ids': list(card_ids),
        'resources': dict(resources),      # 归因数据（直接 + 溢出）
        'pool_id': pool_id,                # ← 触发池 ID，用于 per-pool 归因<!-- REVIEW-FIX-PREV: ISSUE-011 -->
        'real_time': real_time,            # 审计时间戳（不用于归因）
        'draw_index': draw_index,          # 0-based 本抽索引（归因钥匙）
    })
    # ── 源头合并卡（方案 A）──<!-- REVIEW-FIX-PREV: ISSUE-003 -->
    # SharedResultCollector 无 on_bonus 方法，合并必须在 to_dict() 之前完成
    for cid in card_ids:
        r.card_counts[cid] = r.card_counts.get(cid, 0) + 1
        if pool_id:
            if pool_id not in r.pool_card_counts:
                r.pool_card_counts[pool_id] = {}
            r.pool_card_counts[pool_id][cid] = r.pool_card_counts[pool_id].get(cid, 0) + 1
    # ── 源头合并资源（方案 C，2026-08-03）──
    # 前置：on_bonus 在 collector.on_draw 之后——draw_resources_gained 已 append 本抽，
    #   draw_index 处元素存在，可安全累加。归因到触发抽 + 补 total_gained。
    for k, v in resources.items():
        dpg = r.draw_resources_gained[draw_index]
        dpg[k] = dpg.get(k, 0) + v
        r.total_gained[k] = r.total_gained.get(k, 0) + v

# ⚠ gacha_service 循环结束组装 CompactResult 时（现状 gacha_service L419 `result.total_gained = total_gained`）
# 必须改为【合并】而非覆盖：on_bonus 已把 milestone 资源并入 result.total_gained（对象字段），
# 局部 total_gained（仅正常产出 + 等待收益）直接赋值会整体覆盖、丢失 milestone 资源。
# 改为：
#   merged = dict(total_gained)
#   for k, v in result.total_gained.items():
#       merged[k] = merged.get(k, 0) + v
#   result.total_gained = merged
# 最终 final_resources / total_gained / draw_resources_gained 三处一致。
```

`CompactResult` 新增字段：

```python
bonus_events: list = field(default_factory=list)
```

`to_dict()` / `from_dict()` 无需显式代码（2026-08-03 语义审查核实）：`result_types.py` 的 `to_dict` 用 `dataclasses.asdict` 自动深拷贝新字段、`from_dict` 按 known 字段过滤自动接收 `bonus_events`——序列化零成本，M5-serial 实施时仅需测试验证自动同步正确性。**产物形状变化（REVIEW-R1-FIX: ISSUE-108）：** `to_dict()` 产物新增 `bonus_events` 键（无里程碑时为空列表）——`run_batch_parallel` 的 `on_result` / 结果落盘 / CLI JSON 输出键集合变化。`from_dict` 按 known 字段过滤向后兼容、既有测试为字段级断言不精确比对全量字典，故非阻塞；但对 `to_dict()` 输出做**全量字典精确比对**或**落盘 golden** 的既有路径需在 M5-serial 时逐一验证（当前未发现此类既有路径，标注以防未来新增）。<!-- REVIEW-R1-FIX: ISSUE-108 —— to_dict() 产物新增 bonus_events 键（无 milestone 时为空列表）的形状变化已标注；精确比对/golden 落盘既有路径需在 M5-serial 验证 --><!-- REVIEW-R2-FIX: GATE-变更粒度 —— M5 拆分为 M5-serial（collector/result_types/序列化）+ M5-stream（streaming 六路径），此处「M5」指 M5-serial -->

**SharedResultCollector（流式分析）聚合策略：**<!-- REVIEW-FIX-PREV: ISSUE-003 -->
**设计方案 A（源头合并——推荐）：** `SharedResultCollector` 不具备 `on_bonus` 方法（当前仅有 `on_result(compact: Dict)`），且 `extract_aggregate()` 仅读取 `compact['card_counts']`/`compact['pool_card_counts']` 等字段，不解析 `bonus_events`。因此 bonus 合并必须在数据进入 `SharedResultCollector` **之前**完成——即 `CompactCollector.on_bonus()` 中同步更新 `self._result.card_counts` 和 `self._result.pool_card_counts`。这样 `to_dict()` 产出的紧凑字典已含合并后的全量卡牌统计，`extract_aggregate()` 无需解析/合并改动、流式分析自然包含里程碑产出（**唯一例外：`extract_aggregate` 输出新增 `'bonus_events'` 键透传，仅供 GUI 面板减赠卡数据通道使用、不参与合并——REVIEW-R1-FIX: ISSUE-315/316，M5-stream**）。此方案与计划「GDR 始终包含里程碑奖励」的约束一致。方案 C（2026-08-03）同步在 `on_bonus()` 中把资源并入 `draw_resources_gained[draw_index]` 与 `total_gained`——`to_dict()` 产物对卡与资源均源头合并，流式路径里程碑产出（卡+资源）完整可见。**逐抽配对语义（REVIEW-R1-FIX: ISSUE-105）：** 方案 C 下 milestone 资源归因到触发抽行 `draw_resources_gained[draw_index]`，而 milestone 卡不插入 `draw_card_ids`——若 kept 序列未经方案 B 插入赠卡，则 `draw_card_ids[i]` 为正常抽卡但 `draw_resources_gained[i]` 可能含 milestone 资源（预期语义：赠礼资源配到触发抽行而非赠卡行，面板逐抽展示不误判）。实施 M5-stream 方案 B 插入赠卡时，必须按 ISSUE-103 平行插入资源占位（`draw_index + 1` 处插 `{}`），保证 `draw_card_ids` 与 `draw_resources_gained` 长度一致、逐抽配对不越界。<!-- REVIEW-R1-FIX: ISSUE-105 —— 明确方案 C 下 milestone 资源归因到触发抽行的逐抽配对语义；方案 B 插入赠卡时平行插入资源占位保证两数组长度一致 -->

**与 `_merge_milestone_cards()` 互斥声明（2026-07-30 审查修正 + 2026-08-03 R1 更新）：**<!-- REVIEW-FIX-PREV: ISSUE-002 -->
方案 A 在 `on_bonus` 阶段已完成 `card_counts` / `pool_card_counts` 的源头合并。若方案 A 被实施，**§3.6a 的 `_merge_milestone_cards()` 不得再重复写入 `card_counts` 或 `pool_card_counts`**——否则 milestone 赠卡会被双重计入。`_merge_milestone_cards()` 降级为仅构建合并后的 `merged: Dict[str, List[int]]` 映射，其 `pool_card_counts` 更新逻辑需移除——由 `card_counts` 反推即可。**REVIEW-R1-FIX: ISSUE-001 补充：** 方案 A 下 merged 映射无 GDR 消费方（gdr.py 全部 compact GDR 计算不读 `draw_card_ids`），因此 compact/cumulative 入口**不调用**本函数；仅时序型路径（kept 序列/轨迹图）按需调用。**REVIEW-R1-FIX: ISSUE-102 终裁决（措辞修正 REVIEW-R2-FIX: GATE-变更粒度）：`_merge_milestone_cards()` 在代码库从未存在（P58 未实施、grep 全仓核实），本计划不新增、故无「删除」对象**——（1）compact/cumulative 入口不调用（ISSUE-001）；（2）时序型路径的实际修复（ISSUE-009，M5-stream）是在 streaming.py kept 提取处直接构建按抽序的 `merged_card_ids` 平行数组，不消费本函数产出；（3）本函数假设产出 `Dict[str, List[int]]`（card_id→抽数索引列表）与轨迹图消费方需求（按抽序卡 ID 数组，含重复、含赠卡插入，analysis_panel L779/834/928/979 遍历 `seq['draw_card_ids']`）**格式不匹配**。综上时序合并职责全部收敛到 M5-stream streaming 提取处，gdr.py 保持零改动。两方案不可同时生效于同一数据字段。参见 §3.6a 开头的备选方案标注。

**方案 B'（备选——消费方叠加，命名澄清 REVIEW-R1-FIX: ISSUE-002）：** 若坚持 `card_counts` 不含赠送卡（区分抽得/赠得），则在 `extract_aggregate()` 中额外读取 `bonus_events` 并叠加。代码量更大、侵入更多路径，仅作为方案 A 不可行时的回退。**注意：** 此「方案 B'」与下方流式累积快照适配段的「方案 B」（`merged_card_ids` 按 `draw_index` 保序插入——**时序型路径的唯一实施路径**）是两个不同维度、不同命名，勿混淆。

**流式累积快照适配（2026-07-30 追加——2026-08-03 R1 修订：六条路径 + 方案 A 范围限制 + 方案 B 唯一路径）：**<!-- REVIEW-FIX-PREV: ISSUE-004 -->
当前有六条流式提取路径均遍历 `draw_card_ids`：

| 路径 | 文件:方法 | 行号 | 功能 |
|------|----------|------|------|
| 累积 GDR | `streaming.py:_update_cumulative()` | L488-531 | 构建 `cumulative_card_counts` |
| Worker 热力图 | `streaming.py:WorkerLocalExtractor.process()` | L215-254 | 成就×资源分箱热力图 |
| Worker 转变标记 | `streaming.py:WorkerLocalExtractor.process()` | L256-278 | 池结束时目标是否达成 |
| **Worker 累积快照** | **`streaming.py:WorkerLocalExtractor.process()`** | **L218-304（快照段 L266-278/L285-297 亦遍历 `draw_card_ids` 构建 `cum_cards`）** | **构建 `cumulative_snapshots`——批量路径（`run_batch_parallel` 强制入口）经 `merge_extraction_packets`（L345-348）产生，`analysis_panel` L1091-1107 逐池 `compute_gdr_from_cumulative` 与 `process_analysis_panel` L513-524 累积模式 GDR 消费** |
| DrawSeq 热力图 | `streaming.py:DrawSequenceExtractor._update_heatmap()` | L446-486 | 热力图分箱 |
| DrawSeq 转变标记 | `streaming.py:DrawSequenceExtractor._update_transition()` | L536-564 | 转变标记（方案 B 插入赠卡；success 判定按 `bonus_events[].card_ids` 减赠卡恢复 draw-only——与 `WorkerLocalExtractor.process` L277/L296 及 ISSUE-307 口径一致，REVIEW-R1-FIX: ISSUE-313。DrawSequenceExtractor 当前无调用方，属潜伏一致性，统一口径消除六路径表与验收矛盾） |

**REVIEW-R1-FIX: ISSUE-004——`DrawSequenceExtractor` 无调用方：** grep 确认 `DrawSequenceExtractor`（含 `_update_cumulative`/`_update_heatmap`/`_update_transition`）未被任何调用方实例化，仅经 `core/__init__.py` re-export；批量路径（`run_batch_parallel`，CLAUDE.md 强制入口）中 `process_analysis`/`analysis_panel` 消费的 `cumulative_snapshots` 由 **`WorkerLocalExtractor.process` 同循环内构建**并经 `merge_extraction_packets` 合并。因此 M5-stream 的适配**必须以 `WorkerLocalExtractor.process` 累积快照段（第 4 行）为第六条必改路径**——若仅按表格适配 `_update_cumulative`，批量路径累积快照仍遗漏 milestone 赠卡，`analysis_panel` L1091-1107 与 `process_analysis_panel` L513-524 的累积模式 GDR 遗漏里程碑产出，违背「GDR 始终包含里程碑奖励」。

milestone 赠卡不经过 `pool.draw()` 管线——不会出现在 `draw_card_ids` 中。统一修复策略（REVIEW-R1-FIX: ISSUE-002——**两方案不等效，方案 A 对时序/轨迹路径不可行**）：

**方案 A（总量型消费方有效）：** `CompactCollector.on_bonus()` 已同步更新 `card_counts`/`pool_card_counts`。对**只看最终总量**的消费方（`extract_aggregate()`、`compute_gdr_from_compact()`、per-pool `pool_card_counts`）直接用已合并计数即可。**但对时序/轨迹型路径不可行**：`_update_cumulative`（L488-531）按池结束时间 `times[i] > end_time` 逐抽截断、`_update_transition`（L536-564）按池时点判定、`_update_heatmap`（L446-486）与 `WorkerLocalExtractor.process` 热力图（L215-254）按抽序构建轨迹——`card_counts` 是**无时间维度的最终聚合**，无法重建中间池切片与逐位置轨迹。按方案 A 字面实施，除最后池外所有中间池 `cumulative_card_counts`/`transition_flags`/热力图会静默遗漏 milestone 赠卡，且同一快照内卡（无时点）与资源（`on_bonus` 已按 draw_index 合并）时点语义不一致。

**方案 B（唯一实施路径——所有六条路径）：** 在各遍历入口处构建 `merged_card_ids`（正常 `draw_card_ids` + `bonus_events` 赠卡按 `draw_index` 定位插入），遍历 `merged_card_ids` 而非 `draw_card_ids`。定位直接用 `bonus_events[].draw_index`（方案 C 归因钥匙，2026-08-03），无需 `_time_to_draw_index()` 映射工具。**规格补充（REVIEW-R1-FIX: ISSUE-002 + ISSUE-304）：** 赠卡插入时必须**平行对齐全部逐抽数组**——同一插入位置同步向 `draw_times` / `draw_pool_ids` / `draw_resources_gained` 插入占位值，**同时还需 `draw_pity`（占位 `False`）/ `draw_resources_consumed`（占位 `{}`）/ `draw_pity_names`（占位 `None`）/ `draw_pity_counter_max`（占位 `0`）**——六条流式路径的循环均按同一下标 i 读取这几个数组（`WorkerLocalExtractor.process` L235-260 的 `pity_flags[i]`/`draw_res_consumed[i]`、`_update_cumulative` L514-521 的 cumulative_pity/cumulative_consumed、`_update_heatmap` L460-465），只插 card_ids/times/pool_ids/resources_gained 会让插入点之后的每一行 pity 标志与消耗量整体前移一行，热力图 resource 轨迹、累积快照的 cumulative_pity/cumulative_consumed 静默错误；`kept_sequences`（L197-204 复制全部 6 个数组）同样会长度不一致。**必须保证插入后各数组长度一致（逐抽配对不越界）**；赠卡的时间值**继承 `draw_times[draw_index]`**（与该抽同一时点），池时点截断逻辑（`times[i] > end_time`）对继承的时间值自然生效，无需额外处理。`cumulative_snapshots`/`transition_flags`/热力图遍历 `merged_card_ids` 后 milestone 产出正确入图。**插入位置规格（REVIEW-R1-FIX: ISSUE-103，钉死）：** 赠卡行插入在**触发抽之后（索引 `draw_index + 1`）**——原 `draw_index` 处保持正常抽卡行（`draw_resources_gained[draw_index]` 已被 on_bonus 并入 milestone 资源，方案 C），新插入的赠卡行位于其后；`draw_resources_gained` 的平行占位值为**空 `{}`**（milestone 资源已归因到原 `draw_index` 行，禁止复制、禁止重复归因），`draw_times`/`draw_pool_ids` 占位值继承 `draw_times[draw_index]`/`draw_pool_ids[draw_index]`。**禁止在 `draw_index` 处直接插入**——会导致赠卡行被误配「正常抽卡 + milestone 资源」、正常抽卡行资源丢失、后续全部索引偏移。若有多个 milestone 同抽触发（S1），按 `bonus_events` 顺序在 `draw_index+1` 起连续插入（第 k 个赠卡 → `draw_index + k`）。<!-- REVIEW-R1-FIX: ISSUE-103/105 —— 插入位置钉死为 draw_index+1、draw_resources_gained 占位 {}，保证 draw_card_ids 与 draw_resources_gained 逐抽配对长度一致 -->

**赠卡行分母口径（REVIEW-R1-FIX: ISSUE-306）：** 方案 B 平行插入赠卡行后，六条流式路径的循环按行递增 `cum_draws`/`cumulative_draws`（streaming.py L257 `WorkerLocalExtractor.process` / L512 `_update_cumulative` 的 `cumulative_draws += 1`）——赠卡行无任何标记区分，同样计入分母。而 `cumulative_snapshots` 的 `cumulative_draws` 经 `compute_gdr_from_cumulative` → `pseudo_compact['total_draws']`（gdr.py L1132）成为 cumulative GDR 的分母；compact 路径 `total_draws = stats.total_draws`（真实抽数，不含赠卡）、单池模式 `compute_pool_gdr_single_pool` 读 `extract_aggregate` 的 `total_draws`（真实抽数）——**同一 GDR key 在「整体/单池」与「累积」模式分母不同**，`process_analysis_panel` L513-524 累积模式与单池模式的 target_achievement 等每抽指标被系统性稀释，§3.1「GDR 始终包含里程碑奖励」的一致性目标在分母维度不成立。**修复（保守方案）：方案 B 插入赠卡行时对 `cum_draws`/`cumulative_draws` 不做递增**——赠卡计入卡计数与热力图点、但不计入抽数分母（赠卡行循环仅处理卡计数/时点/资源，跳过抽数累加）；备选方案「快照中另存 `cumulative_gift_count` 并在文档标注分母口径差异」需改变快照结构、下游需适配，成本更高——选前者。M5-stream 实施时须对六条路径的抽数累加点统一加「赠卡行跳过」分支，并补「累积模式 GDR 与 compact 模式分母一致」断言。

**REVIEW-R1-FIX: ISSUE-009——kept_sequences GUI 轨迹消费方纳入：** 上述六条路径均不改 `kept_sequences` 本身（streaming L197-204/L406-413 直接浅拷贝 `draw_card_ids`）。而 `analysis_panel` L779（GDR 演化样本路径）、L834（SSR 热力图）、L928（3D 瀑布）、L979（2D 瀑布）与 `gacha_panel` 全部直接遍历 `seq['draw_card_ids']` 计算目标达成/SSR 轨迹。方案 B 扩展至 kept 序列提取处：按 `bonus_events[].draw_index` 将赠卡插入 `merged_card_ids` 作为 `kept_sequences` 的卡序列字段（`draw_times` 等平行对齐同上），或在面板侧消费时合并 `bonus_events`。**必须将 kept_sequences 的 GUI 消费纳入 M5-stream 适配范围**——否则轨迹图目标达成率系统性低于聚合 GDR（含 milestone），面板内跨图表数据不一致。

正确性保证（逐层追踪，2026-08-03 方案 C 修订）：
```
单抽 on_draw(card_id="ssr_a", resources_gained=rg)  ← rg 仅含正常产出（不含 milestone 资源）
     on_bonus(card_ids=["ssr_b"], resources={coin: 500, ...}, draw_index=i)  ← 卡源头合并 card_counts；资源记录归因数据
```
- **卡不会少加：** milestone 卡通过 `on_bonus` 显式累加进 `card_counts`
- **资源不会少算：** milestone 资源注入 `resources`（可用性）+ `bonus_events` 记录（归因）——统计层合并后逐抽产出 / 总账 / 最终余额三处一致（§3.6a）
- **资源不双重入账：** milestone 资源不进 `combined_gained`（P63 结算通道不可回溯），仅在统计层合并一次

分析面板据此区分两类来源——但 GDR 计算时始终合并（里程碑是池子固有属性，§3.1 约束；**合并发生在 `on_bonus` 源头，GDR 读到的 `card_counts`/`pool_card_counts` 已含 milestone，无需 `_merge_milestone_cards`，REVIEW-R1-FIX: ISSUE-001**）。池成败/事件分类（非 GDR 指标）只认 draw 序列的口径见 §3.6b。

#### 3.6a GDR 层合并 bonus_events

> **2026-07-30 审查修正（REVIEW-R1-FIX: ISSUE-001 同步更新）：** 方案 A（`on_bonus` 源头合并）生效时，`_merge_milestone_cards()` **只应构建 `merged: Dict[str, List[int]]` 映射**（供时序型计算），**不得再写入 `result.pool_card_counts`**，否则 milestone 赠卡被双重计入。`pool_card_counts` 可从已合并的 `card_counts` 反推——无需在此函数中二次累加。两方案互斥：同一数据字段不得经由两条路径重复修改。**2026-08-03 R1 裁决补充：** merged 映射无 GDR 消费方（ISSUE-001），方案 A 下 compact/cumulative 入口**不调用**本函数——仅时序型路径（kept 序列/轨迹图）按需调用，且须 dict/CompactResult 双形态防御。**2026-08-03 R2 终裁决（REVIEW-R1-FIX: ISSUE-102；措辞修正 REVIEW-R2-FIX: GATE-变更粒度）：本函数在代码库从未存在（P58 未实施），不新增、故无「删除」对象**——时序型路径的实际修复（M5-stream streaming kept 提取处）不消费本函数产出、假设产出格式与轨迹图需求不匹配，gdr.py 保持零改动，详见下方说明。

> **2026-07-29 注：** P63 未碰 GDR 层——此项完全由 P58 自行实现。

`bonus_events` 与 `card_counts` 是独立通道。GDR 计算时需要将 milestone 赠卡合并到正常产出中以正确计算出率。**资源归因在 on_bonus 源头完成（2026-08-03 方案 C 修订）**——方案 C 下 milestone 资源注入 `state.resources`（可用性）而非当抽 `combined_gained`；`on_bonus`（collector.on_draw 之后）按 `draw_index` 直接把资源并入该抽产出 `draw_resources_gained[draw_index]` 与 `total_gained`。因此 `to_dict()` 产物（含流式路径）与 CompactResult 对象均已含 milestone 资源，无需统计层再合并；卡时序映射由 M5-stream streaming 方案 B 构建（**`_merge_milestone_cards` 在代码库从未存在、gdr.py 不新增该函数——措辞修正 REVIEW-R2-FIX: GATE-变更粒度，REVIEW-R1-FIX: ISSUE-102**）。三处一致由 on_bonus 保证：逐抽明细 / 总账 / `final_resources`：

> **2026-08-03 R1 审查修正（REVIEW-R1-FIX: ISSUE-001）——双形态防御 + merged 映射消费方裁决：**
> 1. `compute_gdr_from_compact` 签名接受 `Union[Dict, CompactResult]`，全部真实调用方（analysis_panel L285/688 `checker.compute_gdr(agg)`、streaming `extract_process` L136、process_trace `compute_pool_gdr_single_pool` L281 `pseudo_compact`、comparison_analyzer / vulnerability / worst_impact / retreat_search）传的都是 **dict**；`compute_gdr_from_cumulative` 内部构造的 pseudo_compact（仅含 card_counts/total_draws/pity_triggers/total_consumed/total_gained/final_resources/final_time/pool_*_counts）同样**无 `draw_card_ids` / `bonus_events`**。因此 `_merge_milestone_cards` 若以属性方式访问（`result.draw_card_ids`）会 AttributeError 全链路崩溃——**必须双形态防御**（isinstance 守卫 + `.get('bonus_events', [])` 容错），见下方代码。
> 2. **grep 确认 gdr.py 全部 compact GDR 计算不读 `draw_card_ids`**——方案 A 下 `card_counts`/`pool_card_counts` 已在 on_bonus 源头合并，`merged` 时序映射在当前**无任何消费方**，方案 A 下在 compact/cumulative 入口调用本函数是死代码（与「方案 A 源头合并已覆盖卡计数」的主张自相矛盾）。**裁决：** 方案 A 生效时 compact/cumulative 入口**不调用** `_merge_milestone_cards`——直接以已合并的 `card_counts`/`pool_card_counts` 计算即可；本函数仅保留为「时序型」消费方（M5-stream 轨迹/kept 序列路径，ISSUE-009 需要按抽序插入赠卡）的可选辅助，且必须经双形态防御后才可安全调用。**R2 终裁决（REVIEW-R1-FIX: ISSUE-102；措辞修正 REVIEW-R2-FIX: GATE-变更粒度）：上述「可选辅助」裁决被推翻——本函数不新增（grep 全仓核实代码库从未存在，无「删除」对象）**。理由：ISSUE-009 修复在 streaming kept 提取处直接构建按抽序 `merged_card_ids` 数组，不消费本函数；本函数假设 `Dict[str, List[int]]` 产出与轨迹图按抽序数组格式不匹配；双形态防御仅解决「不崩」，不解决「格式不可用」。时序合并职责全部收敛到 M5-stream streaming，见下方说明。

```python
# 【REVIEW-R1-FIX: ISSUE-102 终裁决——本函数从未存在、M5a 阶段不新增（无「删除」对象，措辞修正 REVIEW-R2-FIX: GATE-变更粒度）】
# 历史沿革：ISSUE-001 裁决方案 A 下 compact/cumulative 入口不调用本函数（card_counts 源头已合并）；
#   但 ISSUE-009 修复（M5-stream）在 streaming.py kept 序列提取处直接构建按抽序的 merged_card_ids 平行数组，
#   不消费本函数产出；且本函数产出 Dict[str, List[int]]（card_id→抽数索引列表）与轨迹图消费方
#   （analysis_panel L779/834/928/979 遍历 seq['draw_card_ids'] 的按抽序卡 ID 数组）格式不匹配。
# 结论：保留即死代码，时序合并职责全部收敛到 M5-stream streaming 提取处（方案 B，见 §3.6）。
# 禁止恢复：若未来需要「某卡的抽数位置列表」，应在 streaming 合并处直接构建所需形态，不重建本函数。
# draw_index 直接索引（无 real_time→draw_index 映射）的语义仍有效——由 M5-stream streaming 插入时使用。
<!-- REVIEW-FIX-PREV: ISSUE-009 -->
```
<!-- REVIEW-R1-FIX: ISSUE-102 —— `_merge_milestone_cards()` 从未存在、M5a 阶段不新增（grep 全仓核实无此函数、无「删除」对象——措辞修正 REVIEW-R2-FIX: GATE-变更粒度）：入口不调用（ISSUE-001）、ISSUE-009 修复在 streaming kept 提取处构建按抽序数组不消费其产出、假设产出 Dict[str,List[int]] 与轨迹图按抽序数组格式不匹配；时序合并职责收敛到 M5-stream streaming 方案 B -->

资源归因（方案 C，源头完成）：`on_bonus`（collector.on_draw 后）直接把 `resources` 并入 `draw_resources_gained[draw_index]` 与 `total_gained`——对象与 `to_dict()` 产物一致，流式/主路径均覆盖。

**波及（2026-07-30 修正 + 2026-08-03 R1 裁决 + R2 ISSUE-102 终裁决）：** 方案 A 生效时，`compute_gdr_from_compact()` / `compute_gdr_from_cumulative()` **无需在入口调用任何合并函数**——`card_counts`/`pool_card_counts` 已在 `on_bonus` 源头合并、`cumulative_card_counts` 由方案 B（§3.6 六路径表）按 `draw_index` 插入赠卡，GDR 计算读取的已是含 bonus 的计数（REVIEW-R1-FIX: ISSUE-001——merged 时序映射无消费方，入口调用是死代码）。**REVIEW-R1-FIX: ISSUE-102（措辞修正 REVIEW-R2-FIX: GATE-变更粒度）——`_merge_milestone_cards()` 从未存在、不新增该函数**：时序合并（kept 序列/轨迹图，ISSUE-009）统一在 M5-stream streaming 提取处按 `draw_index` 构建按抽序 `merged_card_ids` 平行数组完成（与 ISSUE-001 早期「仅保留为时序型路径可选辅助」表述不一致处，以本终裁决为准——gdr.py 不保留任何合并函数，避免死代码与产出格式错配）。两个入口均在 `gdr.py`，函数签名零改动。若历史路径（`compute_gdr_from_history()`，通过 `generalized_drop_rate.py` 中的 `GeneralizedDropRate` 子类计算）也需反映 milestone 产出，需在历史路径中单独适配（见风险表 ISSUE-008）。

**归因钥匙（2026-08-03 方案 C 修订，废弃 real_time 映射）：** `bonus_events` 直接存 `draw_index`（0-based 本抽索引），来源 `stats.total_draws - 1`（M4 inline）或 P61 emit 契约 `draw_index - 1`（M9 订阅）。**不用 real_time 映射**——抽卡不推进 real_time（仅 WaitAction 推进，gacha_service L372-374），连续无等待抽卡共享同一 real_time 值，`{draw_times[i]: i}` 字典退化为「时间点 → 该段最后一抽」，milestone 资源会错位到段末。`draw_index` 由 `stats.total_draws`（每抽 +1，唯一单调）推导，无映射、无碰撞。

### 3.6b 分析口径——赠卡与池成败/事件分类（REVIEW-R1-FIX: ISSUE-007）

**问题：** `process_trace.infer_events` 双路径——draw-sequence 路径（L43 遍历 `draw_card_ids`，不含 milestone 赠卡）与 aggregate 路径（L49 读 `pool_card_counts`，方案 A 源头合并后含赠卡）；`_resolve_skip_ignore`（L65-66）也读 `pool_card_counts` → 0 抽池因赠卡被判 `skip` 而非 `ignore`。同一池可呈现「事件 miss 但 GDR 成功」矛盾叙事，AA/BB/AB/BA 交叉统计与池成败判定受污染。`streaming.extract_process`（L136-138）`success` 经 `compute_gdr`（含 milestone）而 `pool_events` 经 `infer_events`（不含 milestone），同一模拟两种结论。§3.6 声称「gui/ 分析面板（通过 collector 隔离）不受影响」对 `process_analysis_panel` 数据流不成立。

**口径裁决（保守方案，REVIEW-R1-FIX: ISSUE-007）：** 池成败与事件分类**只认 draw 序列**——`pool_card_counts` 与 `draw_card_ids` 口径对齐：`infer_events` 双路径统一以 draw 口径判定成败；`_resolve_skip_ignore` 读 `pool_card_counts` 判目标存在时，按 `bonus_events[].card_ids` 减去赠卡、恢复 draw 口径（`bonus_events` 即赠卡来源清单，可回溯）。**减赠卡数据通道（REVIEW-R1-FIX: ISSUE-315——AUDIT-BREAK-1 修正）：** `infer_events` 仅接收 `compact` 一个数据对象，减赠卡数据源必须为 `compact['bonus_events']`——draw-sequence 路径（`streaming.extract_process` L138）的 compact 是 `to_dict()` 产物、M5-serial 后含 `bonus_events` 键，天然有数据源；aggregate 路径（`process_analysis_panel` L474 传 `extract_aggregate` 产物）的 agg **无 `bonus_events` 键**（`extract_aggregate` 当前输出不含该键）——**必须由 `extract_aggregate` 输出新增 `'bonus_events': list(compact.get('bonus_events', []))` 键（M5-stream 实施）** 透传，否则 `compact.get('bonus_events', [])` 恒空、减赠卡退化为不减（含赠卡判定残留；`.get` 容错不崩溃，但「事件分类口径 ISSUE-007」验收在 `process_analysis_panel` 数据流不可达）。`infer_events` 内统一按 `compact.get('bonus_events', [])` 读键；旧数据集无该键 → 空列表 → 保守回退不减（向后兼容）。GDR 指标保持含 milestone（§3.1 约束），但池成败/事件分类属策略过程叙事，不含赠卡为预期差异——`extract_process` 的 `success`（GDR 口径）与 `pool_events`（draw 口径）二者语义不同、分别标注，不算矛盾。若产品侧认为「赠卡也应计入池成败」（抽 0 抽但赠卡达成目标 = 池成功），需换「事件定义也认赠卡」方案——**⚠ 待人工裁决**，本计划按保守口径实施。

**REVIEW-R1-FIX: ISSUE-307——口径裁决范围扩展至转变分析两条 flags 来源：** 上述裁决的修复范围仅覆盖 `process_trace.infer_events` 双路径 + `_resolve_skip_ignore`，未覆盖转变分析（transition_flags）的两条 flags 来源：
(1) `analysis_panel` L1349-1351「优先使用 streaming 提取器预计算的 transition_flags」——该 flags 由 `WorkerLocalExtractor.process` L277/L296 `transition_flags.append(self._check_success(cum_cards))` 产生，方案 B（M5-stream）后 `cum_cards` 含赠卡（赠卡为目标卡时 cum_cards 达标 → 该池判成功）；
(2) 回退路径 `compute_transition_flags_from_gdr`（per_pool_analysis.py L285，analysis_panel L1361 调用）经 GDR 框架读 `cumulative_snapshots`/`aggregates`（方案 B 含赠卡 / 方案 A 源头合并含赠卡）。
结果是 `analysis_panel` 转变分析判「池成功」（赠卡计入）、`process_analysis` 的 `infer_events`（draw-only）判同一池「事件 miss/池失败」——两面板对同一数据集呈现矛盾的池成败叙事，§3.6b 声称的「口径对齐」对转变分析路径不成立。**修复（保守方案，与 ISSUE-007 同口径）：** 将 streaming 预计算 `transition_flags`（L277/L296 判定 `cum_cards` 时按 `bonus_events[].card_ids` 减去赠卡再 `_check_success`）与 `compute_transition_flags_from_gdr`（判定前对 `cumulative_snapshots`/`aggregates` 按 `bonus_events` 减赠卡恢复 draw 口径）纳入 draw-only 口径；或显式声明转变分析为「赠卡含入口径」并在面板标注其与过程分析 draw-only 池成败的区别——**⚠ 待人工裁决**，本计划按 draw-only 统一口径实施。**REVIEW-R1-FIX: ISSUE-312——回退路径 bonus_events 数据通道（前轮 ISSUE-307 未覆盖的缺口）：** `compute_transition_flags_from_gdr` 签名（per_pool_analysis.py L285-295）只接收 `cumulative_snapshots`/`aggregates`，二者均不携带 bonus_events（cumulative_snapshots schema（streaming.py L266-276）无 bonus_events 字段；aggregates 来自 `extract_aggregate`（streaming.py L76-120）不输出 bonus_events）——「判定前按 bonus_events 减赠卡」无数据源可减。**数据通道方案（保守、改动局部化）：** 为该函数新增 `bonus_events: List[List[Dict]] = None` 参数（per-sim 赠卡清单，`None` = 无赠卡数据 → 保守回退不减赠卡，即当前行为）；`analysis_panel` L1287/L1361 两处调用从 `self.results` 逐 sim 提取 `result.get('bonus_events', [])` 透传。**⚠ 数据源前提修正（REVIEW-R1-FIX: ISSUE-316——AUDIT-BREAK-2 修正）：** 原计划声称 `self.results` 为「`CompactResult.to_dict()` 产物，M5-serial 新增 `bonus_events` 键可携带」——**前提不成立**。`analysis_panel.self.results`（L2474 赋值）实际来源是 main_window L364/L512 传入的 `aggregate_data`（`extract_aggregate` 产物，gacha_panel L124 `ext.get('aggregates', [])`），`extract_aggregate` 当前输出**不含 `bonus_events` 键**，故 `result.get('bonus_events', [])` 恒空、透传形同虚设、回退路径 draw-only 修正不生效（`.get` 容错不崩溃，但「转变分析 draw-only 口径 ISSUE-307」验收在回退路径不可达）。**数据通道改为：** 由 `extract_aggregate` 输出新增 `'bonus_events': list(compact.get('bonus_events', []))` 键（M5-stream 实施，与 ISSUE-315 同款修复）——M5-serial 的 `CompactResult.bonus_events` → `to_dict()` → `SharedResultCollector.on_result` → `extract_aggregate` 透传 → `aggregate_data` 每条含键 → `self.results` 自动获得，`r.get('bonus_events', [])` 即有数据（旧数据集无键 → 空列表 → 保守回退不减）。`StoredDataset.aggregate_data` 为 `List[Dict]`（result_store.py L86），落盘/加载自动保留新键（to_dict L114 / from_dict L142 无需改动）。函数内层循环按 `sim_idx` 遍历（per_pool_analysis.py L313），判定前构造 draw-only 视图：cumulative 路径复制 snap 的 `cumulative_card_counts` 减去「该 sim 该 pool 的赠卡 card_ids」（`[cid for ev in bonus_events[sim_idx] if ev.get('pool_id') == pool_id for cid in ev.get('card_ids', [])]`）再传 `compute_pool_gdr_cumulative`；single_pool 路径同理从 `agg['card_counts']` 减赠卡。**不改 cumulative_snapshots schema**（该 schema 被 `analysis_panel` L1091-1107 / `process_analysis_panel` L513-524 多处消费，改结构影响面大）。**波及：** `core/streaming.py`（transition_flags 预计算判定处，M5-stream 方案 B 中实现 + **`extract_aggregate` 输出新增 `bonus_events` 键透传，ISSUE-316**）+ `core/per_pool_analysis.py`（`compute_transition_flags_from_gdr` 新增 bonus_events 参数 + draw-only 判定）+ `gui/analysis_panel.py`（L1287/L1361 两处调用透传）+ `core/process_trace.py` 纳入波及表。

**波及：** `core/process_trace.py`（infer_events 双路径 + `_resolve_skip_ignore` 口径对齐，**减赠卡数据源 = `compact['bonus_events']`，aggregate 路径经 `extract_aggregate` 透传键——ISSUE-315**）与 `core/streaming.py`（extract_process success/事件注释 + **transition_flags 预计算判定减赠卡，ISSUE-307** + **`extract_aggregate` 输出新增 `bonus_events` 键透传——ISSUE-315/316 数据通道，M5-stream**）纳入波及表。

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
        # REVIEW-R1-FIX: ISSUE-012 —— 全部输入校验统一走 ConfigError 通道（对照 _build_pity 用
        #   p.get('name','').strip() + ConfigError 模式）；禁止 m['name']（KeyError 裸异常）与
        #   int(m.get(...))（ValueError 裸异常）绕过标准错误通道
        name = m.get('name', '').strip()
        br = m.get('bonus_reward', {})

        # ── 输入校验 ──
        if not name:
            raise ConfigError("里程碑缺少 name 字段")
        if name in seen_names:
            raise ConfigError(f"里程碑名称重复: '{name}'")
        seen_names.add(name)

        try:
            threshold = int(m.get('threshold', 40))
            max_triggers = int(m.get('max_triggers', 0))
        except (TypeError, ValueError):
            raise ConfigError(f"里程碑 '{name}' threshold/max_triggers 必须为整数")

        if threshold < 1:
            raise ConfigError(f"里程碑 '{name}' 阈值必须 ≥ 1，当前为 {threshold}")

        cards = br.get('cards', [])
        if not isinstance(cards, list):
            raise ConfigError(f"里程碑 '{name}' bonus_reward.cards 必须是数组，当前为 {type(cards).__name__}")
        # REVIEW-R1-FIX: ISSUE-012 + ISSUE-101 —— card_id 引用存在性校验（对照 _build_pools 对
        #   epitomizable_cards 的 ConfigError 先例 config_toml.py L1081：先构建 id 集合再判断）。
        # ⚠ 禁止 `cid not in store.card_defs`——store.card_defs 是 List[CardDefEntry]（config_store.py L129），
        #   str 与 CardDefEntry 对象比较恒 False，任何带 cards/random_cards 的里程碑配置必然抛 ConfigError、
        #   load_toml 全失败（ISSUE-101 阻塞）。拼写错误的 card_id 会经 state.add_card 产生幽灵持有并污染 GDR
        known_card_ids = {c.card_id for c in store.card_defs}
        for cid in cards:
            if cid not in known_card_ids:
                raise ConfigError(f"里程碑 '{name}' bonus_reward.cards 引用不存在的 card_id: '{cid}'")

        resources = br.get('resources', {})
        if not isinstance(resources, dict):
            raise ConfigError(f"里程碑 '{name}' bonus_reward.resources 必须是键值对，当前为 {type(resources).__name__}")
        # REVIEW-R1-FIX: ISSUE-303 —— resources 值做数值类型校验（与 cards 引用校验强度对齐）：
        #   原仅校验 dict 类型、值不校验——TOML `resources = { fragment_s = "abc" }` 在 M4 注入
        #   `resources[k] = resources.get(k, 0) + v`（0 + "abc"）与 on_bonus 合并 `dpg.get(k, 0) + v`
        #   均抛 TypeError → worker 的 _run_single try/except 捕获 → 返回 None → 仅 n_failed 警告、
        #   模拟静默失败；负数值/字符串拼接等静默接受。卡侧有存在性校验（ISSUE-101）、资源侧连数值
        #   类型校验都没有——§3.7 声明「resources 键不校验」只覆盖键存在性，值类型缺口在此补上。
        #   逐项数值校验：非 (int, float) 抛 ConfigError（bool 是 int 子类、非数值语义，一并排除）。
        for _rk, _rv in resources.items():
            if not isinstance(_rv, (int, float)) or isinstance(_rv, bool):
                raise ConfigError(
                    f"里程碑 '{name}' bonus_reward.resources['{_rk}'] 值必须为数值（int/float），"
                    f"当前为 {type(_rv).__name__}"
                )

        random_cards = br.get('random_cards', [])
        if not isinstance(random_cards, list):
            raise ConfigError(f"里程碑 '{name}' bonus_reward.random_cards 必须是数组，当前为 {type(random_cards).__name__}")
        for i, rc in enumerate(random_cards):
            candidates = rc.get('candidates', [])
            if not candidates:
                raise ConfigError(f"里程碑 '{name}' random_cards[{i}].candidates 不得为空")
            # REVIEW-R1-FIX: ISSUE-012 + ISSUE-101 —— 候选 card_id 同样校验存在性（复用上方 known_card_ids 集合，
            #   禁止对 List[CardDefEntry] 做 `cid not in store.card_defs`——str in 列表恒 False，恒抛 ConfigError）
            for cid in candidates:
                if cid not in known_card_ids:
                    raise ConfigError(f"里程碑 '{name}' random_cards[{i}].candidates 引用不存在的 card_id: '{cid}'")
            if 'weights' in rc and len(rc['weights']) != len(candidates):
                raise ConfigError(
                    f"里程碑 '{name}' random_cards[{i}].weights 长度({len(rc['weights'])})"
                    f"与 candidates({len(candidates)})不匹配"
                )  <!-- REVIEW-FIX-PREV: ISSUE-005: 防止手工 TOML 中 weights 长度错误 → random.choices ValueError -->
            # REVIEW-R1-FIX: ISSUE-309 —— 全零权重校验：UI 权重列 QDoubleSpinBox ≥0、0=永不出现（§3.8.3），
            #   若某候选池全部候选权重为 0，_resolve_bonus 的 self._rng.choices(...) 抛
            #   `ValueError: Total of weights must be greater than zero`，该异常在 worker 的 _run_single
            #   被捕获 → 返回 None → 模拟静默失败（仅 n_failed warning），用户无明确原因。解析期校验转 ConfigError。
            # REVIEW-R1-FIX: ISSUE-302 —— 权重数值校验改写：原 `if wlist and all(float(w) == 0.0 for w in wlist)`
            #   有两个缺陷：(1) 权重列表全部为非数字字符串（如 ["high","high"]）时 float() 抛裸 ValueError，
            #   绕过 ConfigError 通道——违背 ISSUE-012「全部输入校验统一走 ConfigError」目标；(2) 列表前部已有
            #   非零权重时 all() 短路返回 False、校验静默通过——运行时 _resolve_bonus 的 random.choices 对
            #   字符串权重做算术求和 → TypeError → worker 捕获 → 模拟静默失败。改为逐项 float() 转换并统一
            #   数值校验：非数字值抛 ConfigError（不是靠 all() 短路隐式放行）；校验结果统一转为 float 存入
            #   w_norm，作为运行时权重的规范化基准。
            wlist = rc.get('weights', [1.0] * len(candidates))
            w_norm: list = []
            for w in wlist:
                try:
                    w_norm.append(float(w))
                except (TypeError, ValueError):
                    raise ConfigError(
                        f"里程碑 '{name}' random_cards[{i}].weights 含非数字值 '{w}'（类型 {type(w).__name__}）"
                        f"——必须为数值"
                    )
            if w_norm and all(w == 0.0 for w in w_norm):
                raise ConfigError(f"里程碑 '{name}' random_cards[{i}].weights 全为零——random.choices 无法抽样，至少一个权重 > 0")
            # REVIEW-R1-FIX: ISSUE-302 —— 规范化写回：校验通过后把数值化权重写回 rc['weights']，
            #   否则手工 TOML 的数字字符串权重（如 ["1", "1"]）校验通过但 MilestoneDef 仍存字符串，
            #   运行时 _resolve_bonus 的 self._rng.choices(weights=字符串) 对字符串求和仍抛 TypeError。
            rc['weights'] = w_norm
            # REVIEW-R1-FIX: ISSUE-301 —— count 字段解析期校验（对照 threshold 的校验模式）：
            #   原未校验 count——负数 → self._rng.choices(candidates, weights=weights, k=count) 抛 ValueError；
            #   字符串/浮点 → TypeError；count=0 → choices 返回空列表、里程碑无效果且无任何提示。三类异常均在
            #   worker 的 _run_single try/except 中被捕获 → 返回 None → 仅 n_failed 警告、模拟静默失败且用户
            #   无明确原因。与 ISSUE-309（全零权重）完全同类，但全零权重已被解析期拦截、count 未拦截——手工
            #   TOML 的 count 错误会在模拟期才暴露为静默失败。try/except 转整数 + count >= 1 校验（UI 侧
            #   RandomCardPoolDialog 抽取张数 QSpinBox 下限设 1 见 §3.8.3）。
            try:
                count = int(rc.get('count', 1))
            except (TypeError, ValueError):
                raise ConfigError(f"里程碑 '{name}' random_cards[{i}].count 必须为整数")
            if count < 1:
                raise ConfigError(f"里程碑 '{name}' random_cards[{i}].count 必须 ≥ 1（正整数），当前为 {count}")
            rc['count'] = count   # 规范化写回——运行时 _resolve_bonus 的 self._rng.choices(k=count) 直接用整数 k（数字字符串 "2" 校验通过后若不写回，运行时 k="2" 仍 TypeError）

        # ── banner 过滤解析（空字符串 = 全部；无字符串兼容，2026-08-02 无历史包袱迁移）──
        # REVIEW-R1-FIX: ISSUE-012 —— 此处仅做类型检查（isinstance str）。「banner 值存在或为空」的
        #   存在性校验在 M1-M8 阶段不可做——P61 前不存在 [[banner]] 定义可供对齐；该存在性校验推迟到
        #   M9（P61 集成后传真实 banner_id 时，对照 [[banner]] 段校验）。
        raw_banner = m.get('banner', '')
        if not isinstance(raw_banner, str):
            raise ConfigError(f"里程碑 '{name}' banner 字段必须是字符串（空 = 全部）")

        milestones.append(MilestoneDef(
            name=name,
            threshold=threshold,
            repeat=m.get('repeat', False),
            max_triggers=max_triggers,
            bonus_reward={
                'cards': list(cards),
                'resources': dict(resources),
                'random_cards': list(random_cards),
            },
            banner=raw_banner,
        ))

    store.milestone = MilestoneConfig(enabled=True, milestones=milestones)
    # ⚠ 设计限制：enabled 为运行时标志，不持久化到 TOML——load_toml() 始终重置为 True。
    # 与保底系统的 PityConfig.enabled 行为一致。用户期望「禁用累抽」跨会话保持需在 UI 层
    # 额外存储偏好（不在本计划范围内）。<!-- REVIEW-FIX-PREV: ISSUE-004 -->
```
<!-- REVIEW-R1-FIX: ISSUE-101 —— card_id 存在性校验改为 `known_card_ids = {c.card_id for c in store.card_defs}` 集合判断（store.card_defs 是 List[CardDefEntry]，`cid not in store.card_defs` 恒 False 导致任何带 cards 的配置恒抛 ConfigError） -->

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
            'banner': m.banner,
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
| `banner` | `QLineEdit` | 空=全部 Banner；填 Banner id 则仅该 Banner 内触发 |
| `bonus_reward.cards` | `QListWidget`（多选） | 每行显示 `[稀有度] 名称 (card_id)`，稀有度着色 |
| `bonus_reward.resources` | `QTableWidget`（资源×数量，列0 = 可编辑 `QComboBox`） | 从 `store.resource_defs` 填充（下拉候选 = 资源 Tab 已定义 ID；可编辑以允许临时输入，保存时校验合法性并提示——REVIEW-R1-FIX: ISSUE-104，与资源管理 Tab 的 `resource_defs_table` 数据源一致） |
| `bonus_reward.random_cards` | 池列表（可点击选中）+ 弹窗 | 主面板以 `QListWidget` 每行显示一个候选池摘要（`[池名: 卡列表, 抽N张]`）；行选中（`currentRowChanged`）即更新 `_selected_random_pool_idx`（REVIEW-R1-FIX: ISSUE-003——否则多个随机池时「编辑」恒作用于池 0）；点击 `[编辑]` 弹出 `QDialog` 编辑当前选中池 |

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

**抽取张数约束（REVIEW-R1-FIX: ISSUE-301）：** 抽取张数 `QSpinBox` 下限设 1（`setMinimum(1)`）——解析期 `_build_milestone` 已校验 `count >= 1`（§3.7），UI 必须与之一致：count=0 时 `_resolve_bonus` 的 `choices(k=0)` 返回空列表、里程碑无效果且无任何提示（静默无效），负数/非整数则在 worker 抛异常静默失败。UI 设下限 1 使编辑中间态与解析期校验一致，杜绝「UI 写出 count=0 → load_toml 抛 ConfigError」的 round-trip 断裂。

#### 3.8.4 预览机制

ConfigPanel 右侧 `right_widget` 内仅有一个全局 `QGroupBox("配置预览")` + monospace `QLabel`（`preview_text`）。所有 Tab 共享此预览区——`_do_update_preview()` 遍历各配置段统一拼接摘要文本。

P58 的 7 条信号连接（`milestone_enabled.stateChanged` / `ml_name_edit.textChanged` / `ml_threshold_spin.valueChanged` / `ml_repeat_check.stateChanged` / `ml_max_triggers_spin.valueChanged` / `ml_banner_edit.textChanged` / 随机卡摘要变更 → `self._update_preview()`）触发的是 ConfigPanel 已有的 500ms 去抖全局预览方法。唯一需追加的是 `_do_update_preview()` 中的累抽摘要段：

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
    self._selected_random_pool_idx = 0  # 当前选中编辑的候选池索引（由池列表行选中维护，REVIEW-R1-FIX: ISSUE-003）
    self._current_milestone_row = -1    # REVIEW-R1-FIX: ISSUE-001 —— 追踪当前编辑行（仿 _current_pity_row 模式）
    self._warned_milestone_resource_ids = set()  # REVIEW-R1-FIX: ISSUE-311 —— 未定义资源 ID 一次性警告去重集合（apply_to_store 被预览链路高频调用，同一 rid 仅首次弹窗，后续静默）

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

    self.ml_banner_edit = QLineEdit()
    self.ml_banner_edit.setPlaceholderText("留空 = 全部 Banner")
    detail_form.addRow("适用 Banner:", self.ml_banner_edit)

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

    # 随机卡——池列表（可点击选中）+ 弹窗编辑
    # REVIEW-R1-FIX: ISSUE-003 —— 随机池摘要从纯文本 QLabel 换为可点击 QListWidget：
    #   每个候选池一行（行文本 = 摘要），currentRowChanged 实时维护 _selected_random_pool_idx——
    #   否则多个随机卡池时「编辑」按钮恒作用于池 0、其余池无法进入弹窗编辑。
    self.ml_random_pool_list = QListWidget()
    self.ml_random_pool_list.setMaximumHeight(100)
    self.ml_random_pool_list.currentRowChanged.connect(self._on_random_pool_selected)
    detail_form.addRow("随机卡:", self.ml_random_pool_list)

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
    # REVIEW-R1-FIX: ISSUE-001 —— 行追踪机制（必须与 _flush_pity_current_detail 的 _current_pity_row 对齐）：
    #   _on_milestone_selected 先 flush 到 _current_milestone_row（旧行）再切换到新行；
    #   _flush_milestone_current_detail 读该属性而非 currentRow()——currentRowChanged 触发时
    #   currentRow() 已指向新行，若直接读 currentRow() 会用旧行控件值覆写新行数据。
    # 所有控件变更 → 实时写回 self._milestone_defs[row] → 触发预览
    for w in [self.ml_name_edit, self.ml_banner_edit]:
        w.textChanged.connect(self._flush_milestone_current_detail)
    for w in [self.ml_threshold_spin, self.ml_max_triggers_spin]:
        w.valueChanged.connect(self._flush_milestone_current_detail)
    self.ml_repeat_check.stateChanged.connect(self._flush_milestone_current_detail)
    self.milestone_enabled.stateChanged.connect(self._update_preview)
    # ⚠ 资源表修改（_add_milestone_resource / _remove_milestone_resource）→ _flush_milestone_current_detail() → _update_preview()
    # ⚠ 随机卡池修改（_add/_remove/_edit_milestone_random_pool）→ _flush_milestone_current_detail() → _update_preview()
    # ⚠ 500ms 去抖保证多重触发仅执行一次 _do_update_preview，预览数据流完整 <!-- REVIEW-FIX-PREV: ISSUE-006 -->

# REVIEW-R1-FIX: ISSUE-010 —— _populate_milestone_cards_list 调用点：_refresh_from_store_impl() 中
#   store 就绪后立即调用（见 §3.8.5a 回填段）——否则 ml_cards_list 恒空，bonus_reward.cards 固定卡
#   多选无法 GUI 编辑、_on_milestone_selected 的 setSelected 无 item 可操作。
#   （对照 _sync_weight_cards 在 _do_update_preview L3062 有明确调用。）
def _populate_milestone_cards_list(self):
    """从 store.card_defs 填充固定卡牌 QListWidget——每行 [稀有度] 名称 (card_id)。"""
    self.ml_cards_list.clear()
    if not self._store:
        return
    # REVIEW-R1-FIX: ISSUE-301 —— store.card_defs 是 List[CardDefEntry]（config_store.py L129），无 .items()，
    #   原先 `for cid, entry in self._store.card_defs.items()` 会抛 AttributeError，任何含 [[milestone]] 配置的
    #   加载/导入/重载都会在 M7c 回填段崩溃。改为列表迭代 + entry.card_id（对照 _sync_weight_cards/
    #   _build_pity 的列表访问模式——config_panel 中 self._store.card_defs 恒按 cd.card_id 列表访问）
    for entry in self._store.card_defs:
        cid = entry.card_id
        rarity = (entry.rarity or '?').upper()
        display = f"[{rarity}] {entry.name} ({cid})"
        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, cid)
        # 稀有度着色
        color_map = {'SSR': QColor(255, 215, 0), 'SR': QColor(160, 80, 220), 'R': QColor(100, 149, 237)}
        item.setForeground(color_map.get(rarity, QColor(0, 0, 0)))
        self.ml_cards_list.addItem(item)

def _on_milestone_selected(self, row):
    """选中左侧累抽条目 → 刷新右侧详情面板。"""
    # REVIEW-R1-FIX: ISSUE-001 —— 先 flush 到【上一行】（_current_milestone_row 追踪，仿
    #   _flush_pity_current_detail 读 _current_pity_row 的模式）：currentRowChanged 触发时
    #   currentRow() 已是新行，若 flush 直接读 currentRow() 会用旧行控件值覆写新行数据。
    self._flush_milestone_current_detail()
    # 再切换到新行——此后控件回填触发的信号 flush 均写入新行（含随机卡池摘要回填）
    self._current_milestone_row = row
    if row < 0 or row >= len(self._milestone_defs):
        self._milestone_detail_group.setEnabled(False)
        return
    md = self._milestone_defs[row]
    self._milestone_detail_group.setEnabled(True)

    # REVIEW-R1-FIX: ISSUE-310 —— 回填段 blockSignals：ml_name_edit/ml_banner_edit(textChanged)、
    #   ml_threshold_spin/ml_max_triggers_spin(valueChanged)、ml_repeat_check(stateChanged) 均已连接
    #   _flush_milestone_current_detail（上方信号连接段），回填期间 _current_milestone_row 已指向新行，
    #   若逐一 setText/setValue 不阻断信号，每次触发 flush 时尚未更新的控件（threshold/repeat/banner +
    #   ml_cards_list 选中项 + ml_resources_table + _milestone_random_pools）仍是上一行值，被一并写入
    #   _milestone_defs[新行]——bonus_reward.cards/resources 残留上一行数据，点击行后 500ms 内
    #   _update_preview → get_config()（config_panel.py L3057/L3230 开头调 apply_to_store）即把损坏数据
    #   写入 store.milestone，模拟与保存都使用错误赠卡/资源。对照既有 _on_pity_selected（config_panel.py
    #   L1342-1344/L1395-1397）明确用 blockSignals(True) 阻断回填期级联 flush——本处对齐该先例。
    _bs_widgets = [self.ml_name_edit, self.ml_threshold_spin, self.ml_repeat_check,
                   self.ml_max_triggers_spin, self.ml_banner_edit]
    for w in _bs_widgets:
        w.blockSignals(True)
    try:
        # 基础字段
        self.ml_name_edit.setText(md.get('name', ''))
        self.ml_threshold_spin.setValue(md.get('threshold', 40))
        self.ml_repeat_check.setChecked(md.get('repeat', False))
        self.ml_max_triggers_spin.setValue(md.get('max_triggers', 0))
        self.ml_banner_edit.setText(md.get('banner', ''))

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
        self._selected_random_pool_idx = 0   # REVIEW-R1-FIX: ISSUE-003 —— 切换里程碑时重置池选中到 0（避免沿用上一里程碑的索引）
        self._update_milestone_random_summary()
    finally:
        for w in _bs_widgets:
            w.blockSignals(False)
    # 回填完成后主动 flush 一次——blockSignals 期间无任何级联 flush，需显式把基础字段与
    #   bonus_reward（cards/resources/random_cards）一致写入新行（flush 读 _current_milestone_row = row；
    #   ml_cards_list 选中项 / ml_resources_table / random_pools 已就绪，无旧值残留）
    self._flush_milestone_current_detail()   # REVIEW-R2-FIX: ISSUE-310（2026-08-03 人工裁决补实际调用）

def _flush_milestone_current_detail(self):
    """从右侧控件读取当前值 → 实时写回 self._milestone_defs[row]。"""
    # REVIEW-R1-FIX: ISSUE-001 —— 读 _current_milestone_row（追踪的旧行）而非 currentRow()：
    #   currentRowChanged 触发时 currentRow() 已指向新行，flush 用旧行控件值会覆写新行数据。
    #   （与 _flush_pity_current_detail 读 _current_pity_row 的模式完全对齐。）
    row = self._current_milestone_row
    if row < 0 or row >= len(self._milestone_defs):
        return
    md = self._milestone_defs[row]

    # REVIEW-R1-FIX: ISSUE-314 —— 空名回退复用 _add_milestone 的查重循环（生成不冲突名称）：
    #   原 f"milestone_{row+1}" 不保证唯一——用户清空某行名称后可能与另一行同名（如 3 条里程碑中
    #   row1 被清空 → "milestone_2" 与 row2 同名），保存后 _build_milestone 的『里程碑名称重复』
    #   ConfigError 使整个 config.toml 无法加载；_remove_milestone 造成行号位移使 row+1 回退名漂移，
    #   加剧不确定性。查重须排除当前行自身（本行原名可能是 milestone_N）。对照 _add_milestone L1382-1385。
    _raw_name = self.ml_name_edit.text().strip()
    if _raw_name:
        new_name = _raw_name
    else:
        _existing = {d['name'] for i, d in enumerate(self._milestone_defs) if i != row}
        _n = 1
        while f'milestone_{_n}' in _existing:
            _n += 1
        new_name = f'milestone_{_n}'
    md['name'] = new_name
    # 更名时迁移 _milestone_random_pools 键——防止随机卡池静默丢失
    old_name = self.milestone_list.item(row).text()
    if old_name != new_name and old_name in self._milestone_random_pools:
        self._milestone_random_pools[new_name] = self._milestone_random_pools.pop(old_name)
    md['threshold'] = self.ml_threshold_spin.value()
    md['repeat'] = self.ml_repeat_check.isChecked()
    md['max_triggers'] = self.ml_max_triggers_spin.value()
    md['banner'] = self.ml_banner_edit.text().strip()

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
        # REVIEW-R1-FIX: ISSUE-104 —— 兼容两种行形态：新增行（列0 = QComboBox）取 currentText；
        #   回填的既有行（列0 = QTableWidgetItem 直填）取 item 文本
        res_widget = self.ml_resources_table.cellWidget(i, 0)
        res_item = self.ml_resources_table.item(i, 0)
        amt_item = self.ml_resources_table.item(i, 1)
        rid = ''
        if res_widget is not None and hasattr(res_widget, 'currentText'):
            rid = res_widget.currentText().strip()
        elif res_item:
            rid = res_item.text().strip()
        if rid and amt_item:
            # REVIEW-R1-FIX: ISSUE-004 —— 金额读取防异常 + 过滤 0 值行：
            #   用户输入非数字（如 'abc'）时 float() 抛 ValueError——本方法由 textChanged 等信号
            #   实时调用，异常在 Qt 信号槽内未捕获会中断编辑流，try/except 回落 0.0；
            #   新增行未编辑金额（EditRole 默认 0）若直接入库会持久化 {rid: 0.0} 语义噪音，
            #   统一过滤 amount == 0 的资源项（0 金额 = 无效配置，写 TOML 无意义）。
            #   （对照卡片权重列的 QDoubleSpinBox 已天然约束数字，资源金额列无同类约束，
            #     若后续需强约束可加 QDoubleSpinBox 单元格委托。）
            try:
                amount = float(amt_item.data(Qt.ItemDataRole.EditRole) or 0)
            except (TypeError, ValueError):
                amount = 0.0
            if amount != 0:
                resources[rid] = amount
    md.setdefault('bonus_reward', {})['resources'] = resources

    # 随机卡——从 _milestone_random_pools 回写 <!-- REVIEW-FIX-PREV: ISSUE-030 -->
    pools = self._milestone_random_pools.get(md['name'], [])
    md.setdefault('bonus_reward', {})['random_cards'] = list(pools)

    self.milestone_list.item(row).setText(md['name'])
    self._update_preview()

def _add_milestone(self):
    """添加新累抽条目——默认占位，选中后编辑。"""
    <!-- REVIEW-FIX-PREV: ISSUE-001 —— 搜索不冲突编号替代 len()+1 自增 -->
    existing = {d['name'] for d in self._milestone_defs}
    n = 1
    while f'milestone_{n}' in existing:
        n += 1
    md = {'name': f'milestone_{n}', 'threshold': 40,
          'repeat': False, 'max_triggers': 0, 'banner': '',
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
    # REVIEW-R1-FIX: ISSUE-104 —— 资源列改为可编辑 QComboBox（从 store.resource_defs 填充），
    #   与 §3.8.2「从 store.resource_defs 填充」声明一致、与资源管理 Tab 数据源统一；
    #   可编辑允许临时输入未定义 ID，保存（apply_to_store）时校验合法性并提示
    combo = QComboBox()
    known = list(self._store.resource_defs.keys()) if self._store else []
    combo.addItems(known)
    combo.setEditable(True)
    self.ml_resources_table.setCellWidget(row, 0, combo)
    amt_item = QTableWidgetItem()
    amt_item.setData(Qt.ItemDataRole.EditRole, 0)   # REVIEW-R1-FIX: ISSUE-004 —— 金额默认 0；未编辑的 0 金额行在 _flush_milestone_current_detail 被过滤，不会持久化 {rid: 0.0}
    self.ml_resources_table.setItem(row, 1, amt_item)
    self._flush_milestone_current_detail()
<!-- REVIEW-R1-FIX: ISSUE-104 —— 资源 ID 来源统一为 store.resource_defs 下拉（可编辑），apply_to_store 保存时校验未定义 ID 并警告；_flush_milestone_current_detail 兼容下拉/item 双形态读取 -->
def _remove_milestone_resource(self):
    row = self.ml_resources_table.currentRow()
    if row >= 0:
        self.ml_resources_table.removeRow(row)
        self._flush_milestone_current_detail()

# ── 随机卡池操作 ──

def _add_milestone_random_pool(self):
    """追加一个空候选池。"""
    row = self._current_milestone_row   # REVIEW-R1-FIX: ISSUE-001 —— 奖励编辑作用于当前编辑行（单一真相源，避免 currentRow() 与新行追踪分裂）
    if row < 0:
        return
    md = self._milestone_defs[row]
    pools = self._milestone_random_pools.setdefault(md['name'], [])
    # REVIEW-R1-FIX: ISSUE-305 —— 空候选池（未勾选任何卡）是合法的编辑中间态，但必须保证 save 前被过滤：
    #   _build_milestone 对空 candidates 抛 ConfigError，直接保存会 round-trip 断裂。
    #   过滤点在 apply_to_store()（见 §3.8.5a 写出段）——此处仅追加中间态，保存时自动丢弃。
    pools.append({'candidates': [], 'weights': [], 'count': 1})
    self._update_milestone_random_summary()
    self._flush_milestone_current_detail()

def _remove_milestone_random_pool(self):
    """移除当前选中的候选池（基于 _selected_random_pool_idx，由池列表行选中维护）。"""
    # REVIEW-R1-FIX: ISSUE-003 —— 选中池索引由 ml_random_pool_list.currentRowChanged →
    #   _on_random_pool_selected 维护（原「tooltip 存储索引」注释无任何点击/选中机制支撑，已废除）
    row = self._current_milestone_row   # REVIEW-R1-FIX: ISSUE-001 —— 同 _add_milestone_random_pool
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
    row = self._current_milestone_row   # REVIEW-R1-FIX: ISSUE-001 —— 同 _add_milestone_random_pool
    if row < 0:
        return
    md = self._milestone_defs[row]
    pools = self._milestone_random_pools.setdefault(md['name'], [])
    # REVIEW-R1-FIX: ISSUE-308 —— 空池守卫：pools 为空时 idx 恒为 0、pools[0] 抛 IndexError，
    #   Qt 信号槽内异常使「编辑」按钮失效且数据流中断。无空池时先追加一个空池再进入弹窗
    #   （复用 _add_milestone_random_pool 的追加逻辑，编辑完成后即成为有效候选池）。
    if not pools:
        self._add_milestone_random_pool()
        pools = self._milestone_random_pools[md['name']]
    idx = getattr(self, '_selected_random_pool_idx', 0)
    if idx >= len(pools):
        idx = 0
    dialog = RandomCardPoolDialog(self._store, pools[idx], self)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        pools[idx] = dialog.result()
        self._update_milestone_random_summary()
        self._flush_milestone_current_detail()

def _on_random_pool_selected(self, row):
    """随机池列表行选中 → 记录当前编辑目标池索引（供 编辑/移除 使用）。"""
    # REVIEW-R1-FIX: ISSUE-003 —— 用户点击池行即更新 _selected_random_pool_idx，
    #   使「编辑/移除选中」作用于当前选中池而非恒为池 0
    self._selected_random_pool_idx = row if row >= 0 else 0

def _update_milestone_random_summary(self):
    """刷新随机卡池列表——每个候选池一行摘要（可点击选中）。"""
    row = self._current_milestone_row   # REVIEW-R1-FIX: ISSUE-001 —— 同 _add_milestone_random_pool
    self.ml_random_pool_list.clear()
    if row < 0:
        return
    md = self._milestone_defs[row]
    pools = self._milestone_random_pools.get(md['name'], [])
    if not pools:
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
    self.ml_random_pool_list.addItems(lines)
    # REVIEW-R1-FIX: ISSUE-003 —— 恢复选中到当前池（clamp 到有效范围）；setCurrentRow 触发
    #   currentRowChanged → _on_random_pool_selected 同步 _selected_random_pool_idx
    idx = min(self._selected_random_pool_idx, len(pools) - 1)
    self.ml_random_pool_list.setCurrentRow(idx)
```

`RandomCardPoolDialog` 为独立 `QDialog`（四列勾选/卡/稀有度/权重表格 + 抽取张数 `QSpinBox`），详见图示。

#### 3.8.5a 现有方法适配（M7c——独立于 M7a Tab 骨架与 M7b1 RandomCardPoolDialog / M7b2 奖励编辑器）<!-- REVIEW-FIX-PREV: GATE-1-变更粒度 -->

<!-- REVIEW-FIX-PREV: ISSUE-001 -->
**`apply_to_store()` 追加 milestone 同步：** 在方法末尾（`store.card_weights` 写入之后）追加 ~10 行：

```python
# apply_to_store() 末尾追加 —— 将 UI 层的 self._milestone_defs 写回 ConfigStore
store.milestone.enabled = self.milestone_enabled.isChecked()
store.milestone.milestones = []
for md in self._milestone_defs:
    # REVIEW-R1-FIX: ISSUE-104 —— 保存前校验资源 ID 合法性：未在 resource_defs 定义的给出一次性警告
    #   （不阻塞保存——与 §1.1a 场景 6「先定义 endfield_next_voucher」的用户流程呼应，幽灵资源键由用户修正）
    # REVIEW-R1-FIX: ISSUE-311 —— 警告不得挂在高频路径：apply_to_store 被 get_config()（config_panel.py
    #   L3230 开头）无条件调用，而 get_config 又被 500ms 去抖 _update_preview → _do_update_preview（L3057）
    #   触发，任何 Tab 任意 UI 交互都会经过本循环；且 gacha_panel 启动模拟同样走 apply_to_store。
    #   直接在循环内对每个未定义 rid 调 QMessageBox.warning（模态、阻塞）会对每次编辑动作弹框、无去重。
    #   改为一次性语义：_setup_milestone_config 已初始化 self._warned_milestone_resource_ids = set()，
    #   同一 rid 仅首次提示（加入集合），后续预览/模拟启动链路静默；若需彻底静默可迁移至保存（export_config）
    #   前弹窗，但需新增保存钩子——本计划选保守的集合去重方案。
    for rid in md.get('bonus_reward', {}).get('resources', {}):
        if rid and rid not in store.resource_defs and rid not in self._warned_milestone_resource_ids:
            self._warned_milestone_resource_ids.add(rid)
            QMessageBox.warning(self, "未定义资源",
                                f"资源 ID '{rid}' 未在资源管理 Tab 定义，模拟时可能无法识别")
    # REVIEW-R1-FIX: ISSUE-305 —— 写出前过滤空候选随机池：UI 允许添加未勾选任何卡的空池
    #   （_add_milestone_random_pool 默认追加 {'candidates': [], ...}），但 _build_milestone 对空
    #   candidates 抛 ConfigError——不过滤则 save→load round-trip 断裂、整个配置文件无法加载。
    #   过滤（丢弃 candidates 为空的池）保证存出的 TOML 必含非空 candidates，模拟期 _resolve_bonus 不受影响。
    # REVIEW-R1-FIX: ISSUE-304 —— 过滤条件扩展为「candidates 为空 或 weights 全零」：UI 权重列
    #   QDoubleSpinBox 允许 0（§3.8.3「0=永不出现」），用户可将某随机池全部候选权重设为 0——全零权重池
    #   candidates 非空、不被上述空 candidates 过滤丢弃，save_toml 写出后 load_toml 的 _build_milestone
    #   全零权重校验（ISSUE-309 解析期拦截）抛 ConfigError → 整个 config.toml 无法加载、GUI/CLI 均失败。
    #   空 candidates 中间态有上方过滤兜底，全零权重中间态无对应兜底——UI 允许的编辑中间态与解析期校验
    #   不对称、round-trip 断裂。扩展过滤保证 UI 中间态与解析期校验一致。
    #   注：此处权重数据源必为数值（UI QDoubleSpinBox 产出 float；load_toml 回填数据已被 ISSUE-302 校验），
    #   float(w) 转换安全、不会抛裸异常。
    _br = dict(md.get('bonus_reward', {'cards': [], 'resources': {}, 'random_cards': []}))
    _br['random_cards'] = [
        rc for rc in _br.get('random_cards', [])
        if rc.get('candidates') and not (rc.get('weights') and all(float(w) == 0.0 for w in rc.get('weights')))
    ]
    store.milestone.milestones.append(MilestoneDef(
        name=md.get('name', ''),
        threshold=md.get('threshold', 40),
        repeat=md.get('repeat', False),
        max_triggers=md.get('max_triggers', 0),
        banner=md.get('banner', ''),
        bonus_reward=_br,
    ))
```

模式与 `store.pity.pities` 写入（L3925-3969）一致——遍历 UI 内部 dict 列表 → 转换为 dataclass → 赋值到 store。

<!-- REVIEW-FIX-PREV: ISSUE-002 -->
**`_refresh_from_store_impl()` 追加 milestone 回填（REVIEW-R1-FIX: ISSUE-003——挂载点从 `set_config()` 迁移）：**
⚠ 原计划把回填挂到 `set_config()`（config_panel L3359），但 grep 确认 `set_config()` 在**整个包内无调用方**——实际配置加载路径是 `_load_default_config`/`import_config` → `load_toml` → `refresh_from_store()`（main_window L229/L257）。按原计划挂载，「累抽奖励」Tab 恒空；随后任意 UI 交互触发 `_do_update_preview`（L3057）→ `get_config`（L3230 开头调 `apply_to_store`）→ 用空 `_milestone_defs` 覆写 `store.milestone.milestones`，再经 `config_changed`→`_on_config_changed`（main_window L195）二次 `apply_to_store`，`export_config` 保存时按 §3.7 条件跳过 `[[milestone]]` 段——**已加载里程碑配置被静默清空丢失**。**修复：** 回填追加到 `_refresh_from_store_impl()`（config_panel L4045，与 `pity_enabled`/`_pity_defs` 回填 L4074-4111 同模式），`store` 就绪后调用。验收项挂载点同步改为「`refresh_from_store()` 回填」。若未来有调用方需复用回填，可提取独立方法 `_backfill_milestone_from_store()` 供 `_refresh_from_store_impl()` 调用。

```python
# _refresh_from_store_impl() 中追加（store 已就绪；与 _pity_defs 回填同模式）
self._milestone_defs = []
self.milestone_list.clear()
self._current_milestone_row = -1   # REVIEW-R1-FIX: ISSUE-001 —— 回填不选中任何行，重置行追踪（避免沿用上一加载会话的旧行索引）
self.milestone_enabled.setChecked(store.milestone.enabled)
for md in store.milestone.milestones:
    self._milestone_defs.append({
        'name': md.name,
        'threshold': md.threshold,
        'repeat': md.repeat,
        'max_triggers': md.max_triggers,
        'banner': md.banner,
        'bonus_reward': {
            'cards': list(md.bonus_reward.get('cards', [])),
            'resources': dict(md.bonus_reward.get('resources', {})),
            'random_cards': list(md.bonus_reward.get('random_cards', [])),
        },
    })
    self.milestone_list.addItem(md.name)
# REVIEW-R1-FIX: ISSUE-010 —— _populate_milestone_cards_list 调用时机：store 就绪后立即填充
#   固定卡多选区域（对照 _sync_weight_cards 在 _do_update_preview 有明确调用）
self._populate_milestone_cards_list()
```

模式仿照 `_pity_defs` 回填逻辑（L4074-4111，`_refresh_from_store_impl` 内）：遍历 store 中的 dataclass → 转换为 UI dict → 追加到 `self._milestone_defs` → 刷新 `QListWidget`。回填块需放在 `_refresh_from_store_impl()` 内 `store` 就绪之后、其他控件回填同段（可用 `# ---- 里程碑 ----` 注释分组）。

<!-- REVIEW-FIX-PREV: ISSUE-003 -->
**`get_config()` 追加 `milestone` 键：** 在返回字典中（`'card_weights'` 之前或之后）追加：

```python
'milestone': {
    'enabled': store.milestone.enabled,
    'milestones': [
        {'name': m.name, 'threshold': m.threshold, 'repeat': m.repeat,
         'max_triggers': m.max_triggers, 'banner': m.banner, 'bonus_reward': m.bonus_reward}
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
| M1 | `MilestoneDef` + `MilestoneConfig` dataclass + `ConfigStore` 新增 `milestone` 字段（import `OverflowBand` from P63）+ `ConfigStore.clear()` 追加 `self.milestone = MilestoneConfig()` 重置 <!-- REVIEW-FIX-PREV: ISSUE-007 --> | `config_store.py` | ~26 |
| M2 | `_build_milestone()` 解析 + `save_toml()` 写出 `[[milestone]]` 段。**验收含 shipped config.toml 示例段加载断言（REVIEW-R1-FIX: ISSUE-002）**——config.toml 更新任务须补全 §3.4 示例被引用卡/资源定义（或改用现有卡），否则 ISSUE-101 校验下 `load_toml()` 抛 ConfigError。**校验扩展（REVIEW-R1-FIX: ISSUE-301/302/303）：random_cards.count 整数校验且 ≥1、weights 逐项 float 数值校验、resources 值数值类型校验——均转 ConfigError** | `config_toml.py` | ~40 |
| M3 | `MilestoneEngine` 实现——计数器自管 + 触发判定 + `_resolve_bonus()`（使用 `self._rng`）。**同时 `core/__init__.py` 补导出 `MilestoneEngine`/`MilestoneDef`/`MilestoneConfig`**（REVIEW-R1-FIX: ISSUE-013——新核心模块纳入显式 re-export + `__all__` 清单，`get_milestone_defs()` 返回类型已成 `StrategyContext` 公共接口一部分） | `core/milestone.py` + `core/__init__.py` | ~58 |
| M4 | `gacha_service` 集成——`__init__` 新增 `milestone_engine` 参数 + 模拟循环中 bonus 消费（§3.5 内联消费块：`_milestone_engine.after_draw` 判定 → 资源注入 `state.resources` + 卡走 `state.add_card(path="milestone_gift")` → `bonus_pending` 暂存 → `collector.on_bonus` 源头归因）。**`SimulationCollector` 新增 `on_bonus` 具体 no-op 默认（M4 前置，REVIEW-R2-FIX: GATE-依赖顺序）**——否则 M4 先于 M5-serial、调用 `collector.on_bonus(...)` 带里程碑配置跑模拟即 AttributeError（当前 collector.py 无此方法）；ABC 基类先提供具体 no-op（InfoVectorCollector 继承空实现 → 历史路径静默丢弃 milestone 产出，已知限制），M5-serial 再实现 `CompactCollector.on_bonus`。**M4 验收需含里程碑配置路径**（带 `[[milestone]]` 配置跑模拟不崩溃，产出静默丢弃属预期、M5-serial 后可见）。**「StrategyContext 传入」归 M4a**（`build_strategy_context` 签名与 gacha_service L228 调用处传参统一由 M4a 完成——本阶段不碰 L228，REVIEW-R2-FIX: GATE-依赖顺序 接线边界） | `gacha_service.py` + `core/collector.py` | ~22 |
| M4b | `SimulationEnv` 新增 `milestone_defs` 字段；`SimulationEnvBuilder.from_config_store()` 提取配置；`_run_single` 中 `MilestoneEngine(defs, seed=seed)` 延迟构造 | `batch_simulator.py` | ~15 |
| M4a | `StrategyContext` 新增 `_milestone_engine` 字段 + 3 个查询方法；`build_strategy_context()` (`strategy_context_builder.py`) 签名新增 `_milestone_engine` 参数并透传；**gacha_service.py L228 调用处传入 `self.milestone_engine`（StrategyContext 传入的唯一接线点，REVIEW-R2-FIX: GATE-依赖顺序——M4 不碰 L228，两阶段以函数/文件边界分隔：M4 做 `__init__` 参数与循环内 bonus 消费、M4a 做 build_strategy_context 签名变更与调用处传参，各自验收；依赖 M4 的 `__init__` 新增 `milestone_engine` 属性）** <!-- REVIEW-FIX-PREV: ISSUE-004 --> | `strategy.py` + `strategy_context_builder.py` + `gacha_service.py` | ~25 |
| M5-serial | `collector.on_bonus()`（**含 `draw_index` 参数 + 卡/资源源头合并**，方案 C 2026-08-03）+ `CompactResult.bonus_events`（**含 `pool_id`/`draw_index` 字段**）+ `to_dict()`/`from_dict()` 序列化 + **`_RESULT_VERSION` 1 → 2（REVIEW-R1-FIX: ISSUE-106）** + **`to_dict()` 产物新增 `bonus_events` 键形状变化需验证既有全量比对/golden 落盘路径（REVIEW-R1-FIX: ISSUE-108）** + **gacha_service.py L419 `result.total_gained = total_gained` 改合并修复（REVIEW-R2-FIX: GATE-变更粒度——原仅 §3.6 散文描述未映射到任何 M 阶段；on_bonus 已把 milestone 资源并入 `result.total_gained` 对象字段，覆盖赋值会整体丢失，改为 `merged = dict(total_gained); for k, v in result.total_gained.items(): merged[k] = merged.get(k, 0) + v; result.total_gained = merged`，最终 `final_resources`/`total_gained`/`draw_resources_gained` 三处一致）** + **`SharedResultCollector` 同步验证（方案 A 源头合并自动覆盖——`extract_aggregate` 读取的 `card_counts`/`pool_card_counts` 已含 milestone，无需新增 on_bonus 方法；仅验证，无代码改动。**`extract_aggregate` 输出新增 `bonus_events` 键透传归 M5-stream，ISSUE-315/316**）**。**前置：M4 已提供 `SimulationCollector.on_bonus` 具体 no-op 默认，本阶段实现 `CompactCollector.on_bonus`（REVIEW-R2-FIX: GATE-依赖顺序）**<!-- REVIEW-FIX-PREV: ISSUE-005 --><!-- REVIEW-R2-FIX: GATE-变更粒度 —— 原 M5 拆为 M5-serial（collector/result_types/序列化/L419，~22 行）+ M5-stream（streaming 六路径，~30 行）；原可选拆分建议命名为 M5a/M5b（历史命名），与既有 M5a（GDR 层）直接撞名、无法直接执行，已删除该建议并改为正式拆分命名 M5-serial/M5-stream（不撞名） --> | `collector.py` + `result_types.py` + `gacha_service.py` | ~22 |
| M5-stream | **流式六条路径适配（方案 B 为唯一实施路径，REVIEW-R1-FIX: ISSUE-002/004/009；原「M5b」命名已弃用——历史命名与 M5a GDR 层撞名，REVIEW-R2-FIX: GATE-变更粒度）**：`_update_cumulative` / `WorkerLocalExtractor.process`（热力图 + 转变标记 + **累积快照段 L218-304**）/ `_update_heatmap` / `_update_transition` + **kept_sequences 提取处**按 `bonus_events[].draw_index` 插入赠卡构建 `merged_card_ids`，平行对齐**全部逐抽数组** `draw_times`/`draw_pool_ids`/`draw_resources_gained`/`draw_pity`（占位 False）/`draw_resources_consumed`（占位 {}）/`draw_pity_names`（占位 None）/`draw_pity_counter_max`（占位 0）——六条流式路径循环同下标读取 pity 标志与消耗量（REVIEW-R1-FIX: ISSUE-304，漏插则插入点后每行行错位）<!-- REVIEW-FIX-PREV: ISSUE-005 -->（赠卡时间值继承 `draw_times[draw_index]`；**插入位置 = `draw_index + 1`（触发抽之后），`draw_resources_gained` 占位值 = `{}`——milestone 资源已在 on_bonus 归因到原 draw_index 行，REVIEW-R1-FIX: ISSUE-103**）<!-- REVIEW-FIX-PREV: ISSUE-005 -->**赠卡行不计入 `cum_draws`/`cumulative_draws` 分母（REVIEW-R1-FIX: ISSUE-306——streaming.py L257/L512，保证 cumulative GDR 分母与 compact/单池一致）**；**`transition_flags` 预计算判定（L277/L296）按 `bonus_events[].card_ids` 减赠卡恢复 draw-only 口径（REVIEW-R1-FIX: ISSUE-307，与 infer_events 池成败一致）；`_update_transition`（L536-564）转变标记 success 判定同样减赠卡恢复 draw-only（REVIEW-R1-FIX: ISSUE-313，DrawSequenceExtractor 无调用方、统一口径消除六路径表与验收矛盾）**。**`extract_aggregate`（streaming.py L76-120）输出新增 `'bonus_events': list(compact.get('bonus_events', []))` 键——GUI 面板数据源（`analysis_panel.self.results` / `process_analysis_panel._aggregate_data` = `aggregate_data` = `extract_aggregate` 产物）减赠卡数据通道，REVIEW-R1-FIX: ISSUE-315/316（AUDIT-BREAK-1/2 修复）**。**依赖 M5-serial（`bonus_events` 字段与 `draw_index` 归因钥匙在此引入）；与 M5a（GDR 验证）并行**<!-- REVIEW-FIX-PREV: GATE-1-变更粒度 --> | `streaming.py` | ~30 |
| M5a | GDR 层——**验证性改动，无删除对象（REVIEW-R2-FIX: GATE-变更粒度）**：grep 确认 `_merge_milestone_cards()` 在 gdr.py 及全仓**从未存在**（P58 未实施故从未实现过），原「删除 `_merge_milestone_cards()`（原 ~15 行删除）」叙述误导执行者、已删除该叙述。**本阶段净效果 = `gdr.py` 零代码改动**：方案 A 生效时 compact/cumulative 入口**不调用**任何合并函数（`card_counts`/`pool_card_counts` 已在 on_bonus 源头合并，REVIEW-R1-FIX: ISSUE-001）；时序合并（kept 序列/轨迹图，ISSUE-009）统一在 M5-stream streaming 提取处按 `draw_index` 构建按抽序 `merged_card_ids` 平行数组（不新增、不删除任何函数）。**验收 = M8 集成测试验证合并正确性**（GDR 读到的计数已含 milestone，无需函数调用、无签名改动）。`draw_index` 直接索引（无 real_time→draw_index 映射）语义由 M5-stream 插入时使用；若历史路径也需合并，`generalized_drop_rate.py` 也需改动 <!-- REVIEW-FIX-PREV: ISSUE-009 --><!-- REVIEW-FIX-PREV: ISSUE-011 --> | `gdr.py` | ~0（验证性，无代码改动） |
| M7a | 配置面板 Tab 骨架——`_setup_milestone_config` 基础布局：总闸开关 + QListWidget 左列表 + QGroupBox 右详情 + 基础字段控件（名称/阈值/repeat/max_triggers/banner）+ `_on_milestone_selected`（**回填段 `blockSignals(True)` 阻断级联 flush，回填完成恢复后主动 flush 一次——REVIEW-R1-FIX: ISSUE-310**）+ `_add_milestone` + `_remove_milestone` + 信号连接骨架（不含奖励区域）<!-- REVIEW-FIX-PREV: GATE-1-变更粒度 --> | `config_panel.py` | ~60 |
| M7b1 | `RandomCardPoolDialog` 独立 QDialog 类——四列勾选/卡/稀有度/权重表格（从 `self._store.card_defs` 填充）+ 权重列 `QDoubleSpinBox` + 抽取张数 `QSpinBox` + 确定/取消按钮 + `result()` 方法返回 `{candidates, weights, count}`。不依赖里程碑编辑器其他控件，可独立开发与测试<!-- REVIEW-FIX-PREV: GATE-1-变更粒度 --> | `config_panel.py` | ~35 |
| M7b2 | 奖励编辑器 CRUD + 回写逻辑——固定卡牌 QListWidget（含 `_populate_milestone_cards_list`）+ 资源 QTableWidget（含 `_add/_remove_milestone_resource`；**资源列改为可编辑 `QComboBox` 从 `store.resource_defs` 填充，`_flush_milestone_current_detail` 兼容下拉/item 双形态读取——REVIEW-R1-FIX: ISSUE-104**；**金额读取 try/except 防异常 + 过滤 0 金额行——REVIEW-R1-FIX: ISSUE-004**）+ 随机卡池列表（`_update_milestone_random_summary` + **可点击行选中 `_on_random_pool_selected` 维护 `_selected_random_pool_idx`——REVIEW-R1-FIX: ISSUE-003**）+ 随机卡池 CRUD（`_add/_remove/_edit_milestone_random_pool`，依赖 M7b1 的 `RandomCardPoolDialog`）+ `_flush_milestone_current_detail` 全量回写逻辑（**行追踪改为 `_current_milestone_row`——REVIEW-R1-FIX: ISSUE-001**；**空名回退复用 `_add_milestone` 查重循环生成不冲突名称（查重排除当前行自身）——REVIEW-R1-FIX: ISSUE-314**）。M7b1 提供 Dialog 后串行集成。**REVIEW-R1-FIX: ISSUE-010——`_populate_milestone_cards_list` 调用点 = `_refresh_from_store_impl()` store 就绪后，验收项补固定卡列表非空断言**<!-- REVIEW-FIX-PREV: GATE-1-变更粒度 --> | `config_panel.py` | ~45 |
| M7c | 现有方法适配——`apply_to_store()` 里程碑写入（~10行，**含未定义资源 ID 警告校验 + 一次性去重集合 `self._warned_milestone_resource_ids`——REVIEW-R1-FIX: ISSUE-104 + ISSUE-311**，预览链路仅首次弹窗、后续静默）<!-- REVIEW-FIX-PREV: ISSUE-001 --> + **`_refresh_from_store_impl()` 里程碑回填**（~10行，REVIEW-R1-FIX: ISSUE-003——挂载点从无调用方的 `set_config()` 迁移至实际加载路径 `refresh_from_store()`）<!-- REVIEW-FIX-PREV: ISSUE-002 --> + `get_config()` 追加 `milestone` 键（~8行）<!-- REVIEW-FIX-PREV: ISSUE-003 --> + Tab 注册到 `_setup_ui()`（~7行）<!-- REVIEW-FIX-PREV: GATE-1-变更粒度 --> | `config_panel.py` | ~35 |
| M8 | 集成测试（7 个 G20 场景的 TOML 配置 → 模拟 → 验证期望输出）+ 单元测试（MilestoneEngine._resolve_bonus、_build_milestone 解析器、TOML round-trip、collector 序列化闭环）<!-- REVIEW-FIX-PREV: GATE-6-测试策略 --> + **「清空里程碑名称后保存→加载成功」round-trip 用例（REVIEW-R1-FIX: ISSUE-314）** | `tests/` | ~130 |
| M9 | P61 协作——订阅 `after_draw` 事件（notifier priority=0，P61 Ph0 交付）→ `_on_after_draw` 调用 `MilestoneEngine.after_draw(banner_id, pool_id)` 传真实 banner_id（P61 前 M4 inline 传 `""`）。`banner` 字段解析与过滤已在 M1-M8（`_build_milestone` / `after_draw` 双参）落地，M9 仅接事件。依赖 P61-Ph0（notifier.py）。**REVIEW-R1-FIX: ISSUE-006 三子任务——（1）装配契约：notifier 实例由 P61 装配层经 `GachaService.__init__(notifier=)` 注入，`_on_after_draw` 经 P61 §5.4 `register_milestone_engine` 注册，milestone_engine 由 `_run_single` 内构造实例闭包捕获（禁止模块级全局——Windows spawn 重置为 None）；（2）emit 侧 pool_id 传全限定 `draw_pool_key`（与 draw_pool_ids 同键空间）；（3）**显式删除 M4 inline 里程碑消费块**（bonus_pending 段）——否则同抽双次 after_draw、计数器双递增、资源双重注入** | `milestone.py` + `gacha_service.py` | ~20 |
| **总计** | | | **~657** |

> ~~M6（`resources_gained` 解析遗漏修复）已删除——P63 已修复 TOML 管道。~~ M4b 新增——`batch_simulator.py` 的 `SimulationEnv`/`SimulationEnvBuilder` 需传递 `milestone_config`。**M5 拆分为 M5-serial（collector.py + result_types.py + gacha_service.py L419 合并修复，~22 行）+ M5-stream（streaming.py 六路径，~30 行）——REVIEW-R2-FIX: GATE-变更粒度**：原 M5 把 collector/result_types 序列化与 streaming 六路径方案 B 两类高协调度工作捆在一起（>1 小时）；原「可选拆分 M5a/M5b」建议命名（历史命名）与既有 M5a（GDR 层）撞名、无法直接执行，已删除该建议并改为正式拆分命名 M5-serial/M5-stream（不撞名）。**依赖链：M4（含 on_bonus ABC no-op 前置）→ M5-serial → M5-stream（bonus_events 字段先引入）+ M5a（GDR 验证，与 M5-stream 并行）；M4a 依赖 M4（`__init__` 新增 `milestone_engine` 属性），统一完成 build_strategy_context 传参（REVIEW-R2-FIX: GATE-依赖顺序）**。**M7 拆分为 M7a / M7b1 / M7b2 / M7c 四个 ≤1 小时子阶段**（分别 ~60/~35/~45/~35 行，保守估计各 20-50 分钟）。M7b1（`RandomCardPoolDialog` 独立 QDialog）先于 M7b2（奖励编辑器 CRUD + 回写）串行执行——M7b2 的 `_edit_milestone_random_pool` 依赖 M7b1 提供的 Dialog。M8 行数上调至 ~130 以覆盖 GATE-6 单元测试（~50 行）与集成测试（~80 行）。<!-- REVIEW-FIX-PREV: GATE-1-变更粒度 / GATE-6-测试策略 / UPDATED TOTALS -->

<!-- REVIEW-FIX-PREV: GATE-6-测试策略 -->
### 四、附：M8 单元测试范围声明

M8 测试分为两层——**单元测试（~50 行）**覆盖核心引擎逻辑的独立正确性，**集成测试（~80 行）**覆盖端到端数据流（TOML → 模拟 → collector → GDR）。

#### A. 单元测试（4 个模块，~50 行）

| 编号 | 测试目标 | 输入 | 期望输出 | 对应验收项 |
|:---:|------|------|------|------|
| UT1 | `MilestoneEngine._resolve_bonus()` | 构造 `MilestoneDef(name="test", bonus_reward={'cards': ['a','b'], 'resources': {'c': 5}, 'random_cards': [{'candidates': ['x','y'], 'weights': [1.0,1.0], 'count': 1}]})`，传入 `engine._rng = random.Random(42)` 固定 seed | `result['card_ids']` 含 `['a','b']` + 1 张随机卡（固定 seed 下确定）；`result['resources'] == {'c': 5}`；`_resolve_bonus` 不修改 `engine._counters`/`_active`/`_triggered` | `bonus_reward.cards` / `bonus_reward.resources` / `bonus_reward.random_cards` 解析正确 + 随机卡可复现 |
| UT2 | `_build_milestone()` 解析器 | 最小合法 TOML dict：`{'milestone': [{'name': 'test', 'threshold': 10, 'repeat': True, 'bonus_reward': {'cards': ['a'], 'resources': {}, 'random_cards': []}}]}` → 传入 `ConfigStore(card_defs=[CardDefEntry(card_id='a', ...)])`（**card_defs 必须含 'a'——ISSUE-101 修正后 cards 引用做存在性校验，裸 ConfigStore() 空 card_defs 会抛 ConfigError，无法覆盖解析正例**）；负例：`cards: ['ghost_id']`（card_defs 不含）→ 抛 ConfigError；**校验扩展负例（REVIEW-R1-FIX: ISSUE-301/302/303）：`random_cards[0].count = 0`/`-1`/`"2"` → ConfigError（count 必须整数且 ≥1）；`random_cards[0].weights = ["high","high"]` → ConfigError（非数字权重，而非裸 ValueError）；`bonus_reward.resources = {coin: "abc"}` → ConfigError（资源值必须数值）** | `store.milestone.milestones` 长度为 1；`milestones[0].name == 'test'`；`milestones[0].threshold == 10`；`milestones[0].repeat == True`；`milestones[0].banner == ''` （空字符串=全部 Banner）；**正例加载成功（cards 引用有效卡）+ 各负例抛 ConfigError（REVIEW-R1-FIX: ISSUE-101 + ISSUE-301/302/303）** | `[[milestone]]` 独立 TOML 段解析正确 + `banner` 正确过滤 + card_id 引用校验不误伤有效卡 + count/weights/resources 值校验全走 ConfigError |
| UT3 | TOML round-trip | 构造 `MilestoneConfig(milestones=[MilestoneDef(...)])` → 写入 TOML → `load_toml()` 读回 → 构造新 `ConfigStore` | 读回的 `store.milestone.milestones` 与原始相等：`name`/`threshold`/`repeat`/`max_triggers`/`banner`/`bonus_reward` 逐字段一致。`random_cards` 内嵌列表/数字完整保真（无字符串化退化） | TOML 段 round-trip 保真——GUI 编辑 → 保存 → 重载后字段不丢失 |
| UT4 | collector `on_bonus()→to_dict()→from_dict()` 序列化闭环 | 构造 `CompactCollector`（先 on_draw 制造 `draw_resources_gained` 长度 ≥1）→ 调用 `on_bonus(milestone_name="m1", card_ids=["a","b"], resources={"coin":500}, pool_id="pool_1", real_time=10.0, draw_index=0)` → `to_dict()` → `from_dict()` 重构 `CompactResult` | 重构后 `result.bonus_events[0]['milestone_name'] == 'm1'`；`card_ids == ['a','b']`；`resources == {'coin': 500}`；`pool_id == 'pool_1'`；`real_time == 10.0`；`draw_index == 0`；**`result.result_version == 2`（M5-serial 将 `_RESULT_VERSION` bump 至 2，REVIEW-R1-FIX: ISSUE-106）**。并行模拟不丢数据 | `CompactResult.to_dict()`/`from_dict()` 正确序列化/反序列化 `bonus_events` + 序列化版本号反映格式演进 |<!-- REVIEW-R1-FIX: ISSUE-106 —— M5-serial bump `_RESULT_VERSION` 1→2 并在 UT4 中断言 `result_version == 2` -->

#### B. 集成测试（8 组场景，~80 行）

覆盖 §1.1a 中 7 个 G20 场景 + S1 同抽多触发 + 空抽计数 + 溢出 + 流式六路径 + kept_sequences 轨迹 + 方案 A/B 互斥 + `run_batch_parallel` 单进程兜底路径。各场景具体期望已在 §1.1a 表格中列明。**REVIEW-R1-FIX: ISSUE-315/316 追加——aggregate_data 数据通道用例：** `extract_aggregate(compact.to_dict())` 产物含 `bonus_events` 键（值与 compact 一致）；含赠卡场景下 `process_analysis_panel` L474 `infer_events(agg, ...)` 的 agg（aggregate 分支，`_aggregate_data`）与 `analysis_panel` L1287/L1361 的 `self.results`（= `aggregate_data`）均读到非空 `bonus_events`，减赠卡 draw-only 修正生效——`process_analysis_panel` 池成败与 `infer_events` draw-sequence 路径一致、`compute_transition_flags_from_gdr` 回退路径判池失败与 streaming 预计算一致；旧数据集（无 `bonus_events` 键）加载不崩溃、保守回退不减（`.get` 容错）。**REVIEW-R1-FIX: ISSUE-002 追加——shipped config.toml 加载用例：** 含 §3.4 示例 `[[milestone]]` 段的 `config.toml` 经 `load_toml()` 成功（被引用卡/资源已在 `[card]`/`[resources.defs]` 定义，不抛 ConfigError）——覆盖「示例段写入后配置可加载」验收项。**REVIEW-R1-FIX: ISSUE-314 追加——清空名称 round-trip 用例：** 清空某条里程碑名称后（`_flush_milestone_current_detail` 空名回退为不冲突的 `milestone_N`）→ `save_toml()` → `load_toml()` 成功（无『里程碑名称重复』ConfigError）——round-trip 断言在 config_toml 层，UI 回退逻辑建议 pytest-qt 或手动验收。

#### C. 验收项与测试层级映射

以下将 §八 中全部 45 条 checklist 逐条标注覆盖来源——**UT**=单元测试覆盖，**IT**=集成测试覆盖，**设计保证**=代码结构保证（如默认值守卫、类型约束）、无需独立测试用例。

| 验收项关键词 | 覆盖层级 |
|------|:---:|
| `[[milestone]]` 独立 TOML 段解析正确 | UT2 + IT（场景 1-7 均依赖 TOML 解析） |
| `bonus_reward.cards` 直入 `state.acquired` | UT1 + IT（场景 5 含 card 赠送） |
| `bonus_reward.resources` 注入 `resources` + on_bonus 源头归因（方案 C，2026-08-03） | UT1 + IT（场景 1/2/3/5/6/7 含资源） |
| `bonus_reward.random_cards` 加权随机抽取可复现 | UT1（固定 seed）+ IT（场景 4） |
| cards+resources+random_cards 同时配置生效 | UT1（三字段并存）+ IT（场景 3 含 card+resource） |
| repeat=false 触发后永久停用 | IT（场景 3：150 抽仅 1 次 bonus_events） |
| repeat=true 触发后归零继续 | IT（场景 1：25 抽触发 2 次） |
| max_triggers 正确限制 | IT（需追加专用场景：repeat=true, max_triggers=2 → 3 次触发后 is_active=False） |
| banner 正确过滤 | UT2（空→全部；非空→仅该 banner 触发——该路径 M1-M8 无 banner 概念、M4 传 `""` 时非空 banner 的 milestone 永不触发，**过滤验证移至 M9**（P61 集成后传真实 banner_id））+ IT（M9 后补场景 4/5 限定单 banner） |
| bonus 不触发常规保底重置 | IT（含保底配置的 milestone 场景→验证保底计数器不受影响） |
| milestone 卡溢出（P63 管道） | IT（里程碑卡溢出场景：满突后赠送→溢出资源注入 state.resources + on_bonus 归因，方案 C 2026-08-03） |
| milestone 溢出资源+直接资源注入 state.resources + on_bonus 归因（方案 C，2026-08-03） | IT（同溢出场景） |
| collector.on_bonus() 记录归因数据（含资源金额 + draw_index，方案 C 2026-08-03） | UT4（序列化后含资源金额字段 + draw_index）+ IT |
| SharedResultCollector 同步 | IT（流式路径——需 SharedResultCollector 场景） |
| CompactResult.to_dict()/from_dict() 序列化 | UT4（含 `result_version == 2` 断言——REVIEW-R1-FIX: ISSUE-106） |
| GDR 合并 bonus_events | IT（场景含 milestone→GDR 计算验证 bonus 卡入出率） |
| GDR 合并不改函数签名 | 设计保证（`_merge_milestone_cards()` 在代码库从未存在、gdr.py 不新增该函数——REVIEW-R1-FIX: ISSUE-102，措辞修正 REVIEW-R2-FIX: GATE-变更粒度；`compute_gdr_from_compact`/`compute_gdr_from_cumulative` 签名零改动，入口不做任何合并调用，合并由 on_bonus 源头 + M5-stream streaming 方案 B 完成） |
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
| `refresh_from_store()` 回填（`_refresh_from_store_impl` 内） | 手动验收（UI 组件，建议 pytest-qt） |
| get_config 含 milestone 键 | UT（调用 `get_config()`→断言 `'milestone' in result`） |
| bonus_events 含 pool_id | UT4（构造 bonus_events→验证 `pool_id` 字段存在） |
| 流式六路径含 bonus 卡 | IT（流式路径专用场景：milestone 赠卡→`streaming._update_cumulative` + 5 条 Worker/DrawSeq 路径（含 `WorkerLocalExtractor.process` 累积快照段）+ kept_sequences 提取→验证 bonus 卡贡献入热力图/转变标记/累积快照/kept 序列） |
| 方案 A/B 互斥 | IT（§1.1a 方案 A/B 互斥断言：若实施方案 A，`card_counts['milestone_card']` = `sum(...)` + bonus 卡不被双重计入） |
| 里程碑卡溢出 | IT（满突后赠送→溢出资源注入 state.resources + `on_bonus` 归因，`draw_resources_gained[draw_index]` 反映，方案 C 2026-08-03） |
| 空抽计数推进 | IT（`_NO_CARD_ID` 抽数→计数器正常推进） |
| 同抽多触发顺序确定性 | IT（场景 S1：50 抽同时触发 2 个 milestone→顺序验证） |
| 场景 1 具体期望 | IT（25 抽→bonus_events=2, resources=2） |
| 场景 3 具体期望 | IT（150 抽→bonus_events=1, card_counts['limited_ssr_1']=1, is_active=False） |
| 场景 4 具体期望 | IT（80 抽+固定 seed→赠卡确定+候选集内） |
| 场景 5 具体期望 | IT（300 抽→card+resource 同时交付） |
| CLAUDE.md 同步 | 代码审查（git diff 确认 CLAUDE.md 包含新条目） |
| pytest 全量通过 | CI（`pytest -q` 全量 + 新测试无回归） |
<!-- /REVIEW-FIX-PREV: GATE-6-测试策略 -->

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
└── ✅ `docs/00-meta/模块状态矩阵.md` 行 65 P63 已手动更新为「✅ 完成」<!-- REVIEW-FIX-PREV: ISSUE-004 -->
   —— P63 核心代码（OverflowBand、state.add_card()、card_overflow_map）已落地。
   2026-07-30 plan-review R2 修正：不再依赖 C1 cron，已在本次审查中直接修正矩阵状态。

P61-Ph0（待实施 —— 2026-08-01 新增）
├── core/notifier.py（subscribe/emit/priority）                      ← M9 使用
├── after_draw 事件契约（banner_id / **pool_id=全限定 draw_pool_key** / card_id / pity_triggered + **draw_index** + state/collector；`draw_index` 为 P58 方案 C 扩展字段、`draw_pool_key` 与 `draw_pool_ids` 同键空间，REVIEW-R1-FIX: ISSUE-006） ← M9 订阅
└── Ph0 交付后 P58 与 P61 完全并行；M1-M8 零依赖 P61，仅 M9 依赖 Ph0

本计划（P58——独立 MilestoneEngine）
├── 零依赖 PityEngine / BEHAVIOR_REGISTRY
├── 零依赖 CounterBasedBehavior / PityState
├── 零依赖 P55 / P56
└── 与 P55 / P56 / P63 / P61(M1-M8) 完全并行——改不同文件、不同 TOML 段、不同 UI Tab
```

**P58 内部阶段依赖（REVIEW-R2-FIX: GATE-依赖顺序）：**
```
M1 → M2 → M3 → M4 → M4a（依赖 M4 的 `__init__` 新增 `milestone_engine` 属性）→ M5-serial → M5-stream（依赖 M5-serial 引入 `bonus_events` 字段与 `draw_index` 归因钥匙）+ M5a（GDR 验证，与 M5-stream 并行）→ M7a → M7b1 → M7b2 → M7c → M8；M9 依赖 P61-Ph0
```
- **M4/M4a 接线边界**：M4 只做 `__init__` 参数 + `_run_single` 循环内 milestone 消费块（§3.5）；M4a 统一完成 `build_strategy_context` 签名变更（strategy_context_builder.py）+ gacha_service L228 调用处传参——两阶段以函数/文件边界分隔、各自验收，L228 是 StrategyContext 传入的唯一接线点。
- **on_bonus 前置**：`SimulationCollector.on_bonus` 具体 no-op 默认由 M4 提供（先于 M5-serial 的调用点，避免 M4 带里程碑配置跑模拟 AttributeError）；M5-serial 实现 `CompactCollector.on_bonus` 具体合并逻辑。

**关键识别：独立方案消除了「milestone 与 P55 共享平台层」的伪依赖。** P55 的 `CounterBasedBehavior` 是为保底计数器（未出目标稀有度）设计的——milestone 不需要它。里程碑计数器是纯粹的 `int` 自增，极简到不需要继承任何东西。

**P63 接口约定（2026-07-29 锁定）：**
- milestone 注入卡调用 `state.add_card(cid, path="milestone_gift", overflow_bands=card_overflow_map.get(cid), initial_counts=_initial_counts)`
- 溢出由 `match_overflow_bands()` 自动匹配分段表，返回 `Dict[str, float]`
- `card_overflow_map` 来自 `GachaService.card_overflow_map`（`SimulationEnvBuilder` 从 `ConfigStore.card_overflow_map` 注入）

---

## 六、波及范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/config_store.py` | **修改** | 新增 `MilestoneDef` + `MilestoneConfig` dataclass；`ConfigStore` 新增 `milestone` 字段；`ConfigStore.clear()` 追加 `self.milestone = MilestoneConfig()` 重置行 <!-- REVIEW-FIX-PREV: ISSUE-007 -->；import `OverflowBand`（P63） |
| `core/config_toml.py` | **修改** | 新增 `_build_milestone()` + `save_toml()` 新段（**cards/random_cards 引用做 `known_card_ids` 存在性校验，REVIEW-R1-FIX: ISSUE-002**；**resources 键存在性不校验但值做数值类型校验——REVIEW-R1-FIX: ISSUE-303**；**random_cards 权重逐项 float 数值校验（含非数字值 ConfigError）+ count 整数校验且 ≥1——REVIEW-R1-FIX: ISSUE-302/301**；resources 键存在性不校验仍为已知不对称，由 UI 侧 ISSUE-104 警告覆盖） |
| `core/milestone.py` | **新建** | `MilestoneEngine` 独立调度器——import `OverflowBand` / `match_overflow_bands`（P63） |
| `core/collector.py` | **修改** | **M4 前置（REVIEW-R2-FIX: GATE-依赖顺序）：** `SimulationCollector` 新增 `on_bonus` 具体 no-op 默认（【不可】标 @abstractmethod——`InfoVectorCollector` 不重写则无法实例化）；**M5-serial：** `CompactCollector.on_bonus` 实现（含 `draw_index` 参数 + 卡/资源源头合并，方案 C 2026-08-03） |
| `core/result_types.py` | **小改** | **M5-serial：** `CompactResult` 新增 `bonus_events` 字段 + `to_dict()`/`from_dict()` 序列化 + **`_RESULT_VERSION` 1 → 2（REVIEW-R1-FIX: ISSUE-106——新增字段反映序列化格式演进，供下游 pickle/golden 识别）+ `to_dict()` 产物新增 `bonus_events` 键（无 milestone 时为空列表）——精确比对/golden 落盘的既有路径需在 M5-serial 验证（REVIEW-R1-FIX: ISSUE-108）** |
| `core/gdr.py` | **修改（行数收敛）** | **REVIEW-R1-FIX: ISSUE-001 + ISSUE-102 裁决——方案 A 生效时 compact/cumulative 入口不调用任何合并函数**（`card_counts` 源头已合并）；**`_merge_milestone_cards()` 在代码库从未存在（P58 未实施、grep 全仓无此函数，REVIEW-R2-FIX: GATE-变更粒度 已核实）——原「删除该函数」叙述误导执行者、已修正为「零代码改动、无删除对象」**；时序合并统一在 M5-stream streaming kept 提取处构建按抽序数组。compact 入口 `compute_gdr_from_compact()`(L935) + cumulative 入口 `compute_gdr_from_cumulative()`(L1104) 均在此文件，**签名零改动**。若历史路径也需要合并，`generalized_drop_rate.py` 也需修改——波及表明确两份文件各自改动 <!-- REVIEW-FIX-PREV: ISSUE-009 --> |
| `service/gacha_service.py` | **修改** | **M4：** `__init__` 新增 `milestone_engine` 参数 + 模拟循环中 bonus 消费（§3.5 内联消费块）；**M4a：** L228 `build_strategy_context` 调用处传入 `_milestone_engine`（唯一传参点，REVIEW-R2-FIX: GATE-依赖顺序——两阶段以函数边界分隔）；**M5-serial：** L419 `result.total_gained = total_gained` 改合并修复（REVIEW-R2-FIX: GATE-变更粒度） |
| `service/batch_simulator.py` | **修改** | `SimulationEnv` 新增 `milestone_defs: List[MilestoneDef]` 字段（非 `MilestoneEngine`——延迟构造）；`SimulationEnvBuilder.from_config_store()` 提取 `store.milestone.milestones`（**含 enabled 门控，REVIEW-R1-FIX: ISSUE-302**）；`_run_single` 中 `MilestoneEngine(env.milestone_defs, seed=seed)` 构造并传入 `GachaService`。**`SimulationEnv.from_dict()` 同步追加 `milestone_defs=config.get('milestone_defs', [])`** ——确保 `worst_impact.py` 等非 ConfigStore 调用方不丢失 milestone 配置（~1行）<!-- REVIEW-FIX-PREV: ISSUE-006 -->。**文件头部 import 修正（REVIEW-R1-FIX: ISSUE-303）：** batch_simulator.py 当前**没有** `from __future__ import annotations`（L1-16 为 `from typing import Dict, Any, Optional, Callable`）——dataclass 字段注解在类定义时求值，`milestone_defs: List[MilestoneDef]` 若仅走 `TYPE_CHECKING` 块会模块导入即 NameError。正确做法：**顶部追加 `from __future__ import annotations`**（config_store 无循环 import 风险，亦可再模块级 `from gacha_simulator.core.config_store import MilestoneDef` 直接导入）；原「已启用延迟求值」陈述与事实相反，已删除 <!-- REVIEW-FIX-PREV: ISSUE-002 -->（~15行总计） |
| `core/strategy.py` | **修改** | `StrategyContext` 新增 `_milestone_engine` + 3 个查询方法（~20 行） |
| `core/strategy_context_builder.py` | **修改** | `build_strategy_context()` 签名新增 `_milestone_engine` 参数，透传到 `StrategyContext`——确保 `future_resource_gains` / `inter_pool_pity_links` 派生字段不丢失（~5行） <!-- REVIEW-FIX-PREV: ISSUE-004 --> |
| `gui/config_panel.py` | **修改** | 新增 `_setup_milestone_config()` + 联动方法 + Tab 注册（~100行，M7a）。`RandomCardPoolDialog` 独立 QDialog 类（~35行，M7b1）。奖励编辑器 CRUD 方法（`_populate_milestone_cards_list` / `_add/_remove_milestone_resource` / `_add/_remove/_edit_milestone_random_pool` / `_update_milestone_random_summary` + **`_on_random_pool_selected`，REVIEW-R1-FIX: ISSUE-003**）+ `_flush_milestone_current_detail` 全量回写逻辑（~45行，M7b2，依赖 M7b1；**`_populate_milestone_cards_list` 调用点 = `_refresh_from_store_impl()` store 就绪后，REVIEW-R1-FIX: ISSUE-010**；**行追踪 `_current_milestone_row`（仿 `_current_pity_row`）修复切换列表行时旧行控件覆写新行数据，REVIEW-R1-FIX: ISSUE-001**；**空名回退复用 `_add_milestone` 查重循环生成不冲突名称（查重排除当前行自身），REVIEW-R1-FIX: ISSUE-314**；**资源金额 try/except + 0 值行过滤，REVIEW-R1-FIX: ISSUE-004**；**`_on_milestone_selected` 回填段 `blockSignals(True)` 阻断级联 flush + 回填完成主动 flush 一次，REVIEW-R1-FIX: ISSUE-310**）。**同时适配 3 个现有方法：** `apply_to_store()` 追加 `store.milestone.milestones` 写入（~10行，**含未定义资源 ID 一次性去重警告 `self._warned_milestone_resource_ids`——REVIEW-R1-FIX: ISSUE-311**）<!-- REVIEW-FIX-PREV: ISSUE-001 -->、**`_refresh_from_store_impl()` 追加里程碑回填**（~10行，REVIEW-R1-FIX: ISSUE-003——挂载点从无调用方的 `set_config()` 迁移至实际加载路径）<!-- REVIEW-FIX-PREV: ISSUE-002 -->、`get_config()` 追加 `'milestone'` 键（~8行）<!-- REVIEW-FIX-PREV: ISSUE-003 --> + Tab 注册（~7行，M7c）<!-- REVIEW-FIX-PREV: GATE-1-变更粒度 --> |
| `core/retreat_config.py` + `core/retreat_search.py` | **修改** | `RetreatConfigBuilder.build` 透传 `original_store.milestone` + `original_store.card_overflow_map` + `original_store.rarity_defaults`（REVIEW-R1-FIX: ISSUE-005 **+ ISSUE-306 扩展**）——否则截断分支（`from_pool_id` 指定）truncated_store 恒空 milestone，与完整时间线分支（含 milestone）GDR/最少资源/Pareto 搜索结果不一致。**ISSUE-306 修正：仅透传 milestone 不够**——截断 store 是 `ConfigStore()` 新建（retreat_config.py L25），`card_overflow_map`/`rarity_defaults` 为空、`CardDefEntry` 复制（L124-135）也不带 `overflow_bands`、且不执行 `_build_card_overflow_map`；P58 M4 的 milestone 赠卡走 `state.add_card(cid, overflow_bands=self.card_overflow_map.get(cid))`——空 map 下赠卡溢出资源（星辉/井币等）不触发，「截断模式与完整时间线模式一致」验收项不成立。**透传范围扩展为 milestone + card_overflow_map + rarity_defaults**（或在截断 store 上执行等价 overflow map 构建），保证两模式数值一致 |
| `core/process_trace.py` | **小改** | `infer_events` 双路径 + `_resolve_skip_ignore` 口径对齐（REVIEW-R1-FIX: ISSUE-007——池成败/事件分类只认 draw 序列，`pool_card_counts` 读时按 `bonus_events` 减赠卡恢复 draw 口径）。**REVIEW-R1-FIX: ISSUE-307 扩展——draw-only 口径与转变分析回退路径一致（转变分析减赠卡在 streaming/per_pool_analysis 层完成，本文件无新增改动）** |
| `core/streaming.py` | **修改** | **M5-stream** 方案 B 六条路径 + kept_sequences 按 `bonus_events[].draw_index` 插入赠卡（平行对齐全部逐抽数组，REVIEW-R1-FIX: ISSUE-002/004/009/304）。**REVIEW-R1-FIX: ISSUE-306——赠卡行对 `cum_draws`/`cumulative_draws` 不做递增（streaming.py L257/L512），保证 cumulative GDR 分母与 compact/单池一致**。**REVIEW-R1-FIX: ISSUE-307——`WorkerLocalExtractor.process` L277/L296 `transition_flags` 预计算判定 `cum_cards` 时按 `bonus_events[].card_ids` 减去赠卡、恢复 draw-only 口径（否则 `analysis_panel` 转变分析判「池成功」与 `infer_events` 的「池失败」矛盾）**。**REVIEW-R1-FIX: ISSUE-313——`DrawSequenceExtractor._update_transition`（L536-564）转变标记 success 判定同样按 `bonus_events[].card_ids` 减赠卡恢复 draw-only（与 L277/L296 一致；DrawSequenceExtractor 无调用方，统一口径消除六路径表与验收矛盾）**。**`extract_aggregate`（L76-120）输出新增 `'bonus_events': list(compact.get('bonus_events', []))` 键（REVIEW-R1-FIX: ISSUE-315/316——GUI 面板数据源 `analysis_panel.self.results` / `process_analysis_panel._aggregate_data` 均为 `extract_aggregate` 产物，减赠卡数据通道由此键供给；旧数据集无键 → 空列表 → 保守回退不减）**。另含 `extract_process` success/事件注释口径标注（ISSUE-007） |
| `core/result_store.py` + `gui/main_window.py` | **小改** | `compute_config_hash` 纳入 milestone 字段（REVIEW-R1-FIX: ISSUE-008）——否则仅 milestone 不同的数据集被判「配置: 相同」，`only_strategy_differs()`/`mode_label()` 可能误判纯策略比较 |
| `core/gdr_analysis.py` | **不修改（已知限制标注）** | 历史路径（InfoVector 驱动）静默丢弃 milestone 产出——`SuccessProbabilityAnalyzer` 不反映里程碑（REVIEW-R1-FIX: ISSUE-011，见风险表 ISSUE-008 扩展） |
| `core/per_pool_analysis.py` | **修改（ISSUE-307 + ISSUE-312）** | `compute_transition_flags_from_gdr`（L285，转变分析回退路径）**新增 `bonus_events: List[List[Dict]] = None` 参数**（REVIEW-R1-FIX: ISSUE-312——cumulative_snapshots schema 与 aggregates 均不携带 bonus_events，无数据源可减赠卡，数据通道由调用方 analysis_panel 逐 sim 从 `self.results` 的 `'bonus_events'` 键透传；`None` = 无赠卡数据保守回退不减。**`self.results` 为 `aggregate_data`（`extract_aggregate` 产物）而非 `CompactResult.to_dict()` 产物，`bonus_events` 键须由 `extract_aggregate` 输出透传保证非恒空——REVIEW-R1-FIX: ISSUE-316**）——判定前按该 sim 该 pool 的赠卡 card_ids 从 `cumulative_card_counts`/`agg['card_counts']` 减去、恢复 draw-only 口径，否则方案 B/A 后该路径判「池成功」与 `infer_events` 的「池失败」矛盾。`compute_per_pool_snapshots`/`compute_cumulative_snapshots`（历史路径）仍不反映里程碑（已知限制，同 gdr_analysis.py） |
| `core/__init__.py` | **小改** | 补导出 `MilestoneEngine`/`MilestoneDef`/`MilestoneConfig`（REVIEW-R1-FIX: ISSUE-013，M3 阶段） |
| `config/config.toml` | **更新** | 新增 `[[milestone]]` 示例段 + **补全被引用卡/资源定义（REVIEW-R1-FIX: ISSUE-002）**——`limited_operator`/`ssr_ibaraki` 等卡补 `[card]` 段（或示例改用现有 `limited_ssr_1` 等卡）、`fragment_s`/`coin`/`exchange_currency`/`endfield_next_voucher` 补 `[resources.defs]`；保证含示例段后 `load_toml()` 成功 |
| `tests/` | **新增** | ~130 行测试（M8）。单元测试（~50行）：`MilestoneEngine._resolve_bonus()` 独立测试、`_build_milestone()` 解析器测试、TOML round-trip（构造→保存→加载→断言相等）、collector `on_bonus()→to_dict()→from_dict()` 序列化闭环。集成测试（~80行）：7 个 G20 场景期望输出验证 + 同抽多触发顺序 + 空抽计数 + 里程碑卡溢出 + 流式六路径 + kept_sequences 轨迹 + 方案 A/B 互斥 + `run_batch_parallel` 单进程兜底路径<!-- REVIEW-FIX-PREV: GATE-6-测试策略 / GATE-1-变更粒度 --> |
| `CLAUDE.md` | **修改** | 扩展指南表格新增「新里程碑」行，架构分层注释新增 `core/milestone.py` 条目。`StrategyContext` 关键识别附注新增 `_milestone_engine` 字段说明 <!-- REVIEW-FIX-PREV: ISSUE-012 --> |
| `scripts/profile_sim.py` + `scripts/profile_simulation.py` | **不修改（向下兼容）** | 两个性能分析脚本直接构造 `GachaService`（`profile_sim.py` L87-90 / `profile_simulation.py` L99-104），均传入显式关键字参数。`GachaService.__init__` 新增 `milestone_engine` 参数后，因默认值 `None` 向下兼容，当前无需修改。若未来性能基准需启用里程碑，需在构造时追加 `milestone_engine=...` 参数。是否启用留待性能基准设计时决定。<!-- REVIEW-FIX-PREV: ISSUE-028 --> |

**不受影响（面板代码零改动或仅透传小改，消费数据由 M5-stream 方案 B 覆盖）：** `core/pity.py`（零改动）、`core/pool.py`、`gui/gacha_panel.py`（**REVIEW-R1-FIX: ISSUE-004/007/009——面板代码不改，但面板消费的 `cumulative_snapshots`（`analysis_panel` L1091-1107 逐池 `compute_gdr_from_cumulative`、`process_analysis_panel` L513-524 累积模式 GDR）与 `kept_sequences` 轨迹（`analysis_panel` L779/834/928/979、`gacha_panel`）由 M5-stream 方案 B 在 streaming 层产出含 milestone 的数据**。**REVIEW-R1-FIX: ISSUE-306——累积模式 GDR 分母由 streaming 赠卡行不递增抽数保证，与 compact/单池一致**）、`core/overflow.py`（仅 import，零改动）。**`gui/process_analysis_panel.py`（面板代码零改动，REVIEW-R1-FIX: ISSUE-315——L471-474 遍历的 `_aggregate_data` = `aggregate_data` = `extract_aggregate` 产物，M5-stream 后每条含 `bonus_events` 键，L474 `infer_events(agg, ...)` 的 aggregate 分支即可按 `compact['bonus_events']` 减赠卡；旧数据集无键 → 空列表 → 保守回退不减）**。**`gui/analysis_panel.py`（小改，REVIEW-R1-FIX: ISSUE-312 + ISSUE-316——L1287/L1361 两处 `compute_transition_flags_from_gdr` 调用处新增 `bonus_events=[r.get('bonus_events', []) for r in self.results]` 透传参数；`self.results` 实际为 `aggregate_data`（`extract_aggregate` 产物，main_window L364/L512 传入、analysis_panel L2474 赋值），**非** `CompactResult.to_dict()` 产物——`bonus_events` 键由 `extract_aggregate` 输出透传（M5-stream）保证可达 `self.results`，否则 `r.get('bonus_events', [])` 恒空、回退路径 draw-only 修正不生效。面板其余消费逻辑零改动）**

**2026-07-29 修订：** M6（`resources_gained` 解析遗漏修复）已删除——P63 已修复 TOML 管道。`batch_simulator.py` 新增入波及范围——`SimulationEnv` + `SimulationEnvBuilder` 需传递 `milestone_config`。

---

## 七、风险

| 风险 | 缓解 |
|------|------|
| ~~`SimulationStats.acquired_counts` 移除后外部引用遗漏~~ | ~~P60 已处理~~ —— 已消除 |
| ~~旧序列化快照（无 `acquired`）反序列化失败~~ | ~~P60 已处理~~ —— 已消除 |
| ~~TOML 中 `resources_gained`/bonus 字段从未被解析~~ | ~~P63 已修复 TOML 管道~~ —— 已消除 |
| `milestone` 计数器生命周期（`repeat`=true 重置 vs false 停用）自管 bug | 极简逻辑——`int` 自增 + `if c >= threshold`，M8 集成测试覆盖 |
| bonus 注入时序不当（早于/晚于保底重置导致状态不一致） | 时序固定（方案 C，2026-08-03）：`PityEngine.after_draw` → `state.add_card(path="draw")`（正常溢出，P63）→ `MilestoneEngine.after_draw` → 直接资源 + `state.add_card(path="milestone_gift")`（milestone 溢出）注入 `resources`（不进 combined_gained）→ 资源结算 → `collector.on_draw` → `collector.on_bonus`（源头归因，draw_index） |
| `bonus_events` 序列化遗漏导致并行模拟数据丢失 | `CompactResult.to_dict()`/`from_dict()` 必须同步更新——M5-serial 追加此项 |
| `SharedResultCollector` 未实现 `on_bonus`——流式分析中里程碑不可见 | M5-serial 同步验证（方案 A 源头合并自动覆盖——`extract_aggregate` 读取的计数已含 milestone，无需新增 on_bonus 方法） |
| GDR `_merge_milestone_cards()` 依赖 `real_time→draw_index` 映射 | **已消除（方案 C，2026-08-03）**：`bonus_events` 直接存 `draw_index`（0-based 本抽索引，来源 `stats.total_draws - 1`），无映射；资源归因移到 `on_bonus` 源头合并。**REVIEW-R1-FIX: ISSUE-102（措辞修正 REVIEW-R2-FIX: GATE-变更粒度）——该函数在代码库从未存在、gdr.py 不新增**（时序合并由 M5-stream streaming 方案 B 完成，`draw_index` 语义仍由 streaming 插入时使用） |
|（已删除）原 `pools` 字符串 `"*"` 兼容 | 2026-08-02 无历史包袱迁移删除 `pools` 字段（§3.3 修订）——不再有字符串检测；`banner` 解析校验字符串类型（§3.7） |
| banner 拼写错误/引用不存在 Banner id → 里程碑永不触发 | REVIEW-R1-FIX: ISSUE-012——`_build_milestone()` 仅对 banner 做类型检查（isinstance str，§3.7）；**「banner 值存在或为空」的存在性校验在 M1-M8 阶段不可做**（P61 前不存在 `[[banner]]` 定义可供对齐），推迟到 M9（P61 集成后对照 `[[banner]]` 段校验）。banner 精确匹配（非 fnmatch），配置错误由用户自查 banner id 与 `[[banner]]` 定义对齐 |
| 配置面板 UI 与 P55/P56 保底 UI 改造潜在冲突 | 独立 Tab——不碰 `_setup_pity_config()` |
| `apply_to_store()` 缺少里程碑写入逻辑——GUI 编辑无法持久化到 TOML | **M7c 追加：** 在 `apply_to_store()` 中遍历 `self._milestone_defs` 转换为 `MilestoneDef` 实例写入 `store.milestone.milestones`（~10行）。模式与 `store.pity.pities` 写入一致 <!-- REVIEW-FIX-PREV: ISSUE-001 / GATE-1-变更粒度 --> |
| `set_config()` 全包无调用方——按原挂载点回填永不执行、「累抽奖励」Tab 恒空，且 UI 交互会以空 `_milestone_defs` 静默覆写已加载配置（REVIEW-R1-FIX: ISSUE-003） | **M7c 追加：** 回填挂载到 `_refresh_from_store_impl()`（config_panel L4045——实际加载路径 `refresh_from_store()` 调用，main_window L229/L257），从 `store.milestone.milestones` 反序列化到 `self._milestone_defs` + 刷新 `milestone_list` + 调用 `_populate_milestone_cards_list()`（~10行+调用）。模式仿照 `_pity_defs` 回填逻辑（L4074-4111） <!-- REVIEW-FIX-PREV: ISSUE-002 / GATE-1-变更粒度 --> |
| `get_config()` 返回字典缺少 `milestone` 键——预览摘要始终为空 | **M7c 追加：** `get_config()` 返回字典追加 `'milestone': {'enabled': ..., 'milestones': [...]}` 键（~8行）。`_do_update_preview()` 合成摘要代码已为此适配 <!-- REVIEW-FIX-PREV: ISSUE-003 / GATE-1-变更粒度 --> |
| `build_strategy_context()` 未纳入波及范围——`StrategyContext` 构造绕过此函数将丢失派生字段 | **波及范围追加 `strategy_context_builder.py`：** `build_strategy_context()` 签名新增 `_milestone_engine` 参数，`gacha_service.py` 调用处传入 `self.milestone_engine` <!-- REVIEW-FIX-PREV: ISSUE-004 --> |
| 流式路径 `_update_cumulative()` / `WorkerLocalExtractor.process()`（含累积快照段 L218-304）/ `DrawSequenceExtractor._update_heatmap()` / `DrawSequenceExtractor._update_transition()` / kept_sequences 均遍历 `draw_card_ids`——bonus 卡不在其中，流式 GDR/热力图/转变标记/轨迹图遗漏里程碑产出（REVIEW-R1-FIX: ISSUE-004/009） | **M5-stream 追加——方案 B（唯一实施路径，REVIEW-R1-FIX: ISSUE-002）：** 六条路径（`_update_cumulative` / `WorkerLocalExtractor.process` 内联热力图 + 转变标记 + **累积快照段** / `_update_heatmap` / `_update_transition` / **kept_sequences 提取处**）在遍历前构建 `merged_card_ids`（正常 draw 序列 + bonus 赠卡按 `draw_index` 定位插入，方案 C 归因钥匙），**平行对齐全部逐抽数组 `draw_times`/`draw_pool_ids`/`draw_resources_gained`/`draw_pity`/`draw_resources_consumed`/`draw_pity_names`/`draw_pity_counter_max`（赠卡 pity 标志占位 False、consumed 占位 {}、pity_names 占位 None、pity_counter_max 占位 0——REVIEW-R1-FIX: ISSUE-304：流式循环同下标读取 `pity_flags[i]`/`draw_res_consumed[i]`，漏插则插入点后每行行错位；赠卡时间值继承 `draw_times[draw_index]`；插入位置 = `draw_index + 1`，`draw_resources_gained` 占位 = `{}`——milestone 资源已在 on_bonus 归因到原 draw_index 行，REVIEW-R1-FIX: ISSUE-103）**。方案 A 仅对总量型消费方有效、对时序/轨迹型路径不可行（`card_counts` 无时间维度无法重建中间池切片与逐位置轨迹）。卡计数/资源归因均源头合并（on_bonus），无需 `_time_to_draw_index()` 映射 <!-- REVIEW-FIX-PREV: ISSUE-004 --> |
| `SimulationEnv.from_dict()` 遗漏 `milestone_defs` 参数——`worst_impact.py` 等调用方丢失 milestone 配置 | **波及范围追加 `from_dict`：** `SimulationEnv.from_dict()` 追加 `milestone_defs=config.get('milestone_defs', [])`（与 `card_overflow_map` 占位模式一致） <!-- REVIEW-FIX-PREV: ISSUE-006 --> |
| `ConfigStore.clear()` 遗漏 `self.milestone = MilestoneConfig()`——连续配置加载间状态残留 | **M1 追加：** `clear()` 末尾追加 `self.milestone = MilestoneConfig()`（1行）。虽非功能阻塞（配置加载路径开头 `clear()` 后立即回填），但违反全量清零契约 <!-- REVIEW-FIX-PREV: ISSUE-007 --> |
| `InfoVectorCollector` 继承空 `on_bonus` 实现——历史路径 `compute_gdr_from_history()` 将静默丢失里程碑数据 | **已知限制（标注）：** `InfoVectorCollector` 不实现 `on_bonus`——历史路径 GDR 不反映 milestone 产出。批量模拟主流使用 compact 路径，历史路径为边缘场景。若后续需支持，需新建 `InfoVector` 动作类型 `milestone_gift`。**REVIEW-R1-FIX: ISSUE-011/014 扩展：**（a）波及另两份 InfoVector 驱动分析——`gdr_analysis.py`（`SuccessProbabilityAnalyzer`）与 `per_pool_analysis.py`（`compute_per_pool_snapshots`/`compute_cumulative_snapshots`）同样不反映里程碑产出（波及表已标注不修改）；（b）**resource_remaining 数值分叉**——compact 路径读 `final_resources`（方案 C 含 milestone 注入），历史路径读 `resources_gained`（不含 milestone），同一 GDR key 两路径结果不同；（c）**state.resources 语义分叉**——M4 milestone 资源注入直接作用于 `state.resources`（gacha_service L196 是引用），与 collector 类型无关：历史路径最终 `state.resources` 余额含 milestone、但逐抽 `resources_gained` 明细不含。一致性目标：compact 路径为准，历史路径为已知降级并在文档/面板标注 <!-- REVIEW-FIX-PREV: ISSUE-008 --> |
| GDR 波及范围表指向 `generalized_drop_rate.py`——但 `compute_gdr_from_compact`/`compute_gdr_from_cumulative` 实际在 `gdr.py` | **波及范围表修正：** M5a 目标文件改为 `gdr.py`。**REVIEW-R1-FIX: ISSUE-001 + ISSUE-102 裁决更新（措辞修正 REVIEW-R2-FIX: GATE-变更粒度）：方案 A 生效时 compact/cumulative 入口不调用任何合并函数（merged 映射无消费方、死代码）；`_merge_milestone_cards()` 在代码库从未存在、gdr.py 不新增该函数（无「删除」对象，时序合并由 M5-stream streaming 提取处方案 B 完成）。**若历史路径也需合并，`generalized_drop_rate.py` 也需修改——波及表明确两份文件各自改动 <!-- REVIEW-FIX-PREV: ISSUE-009 --> |
| 计划 §3.6a 伪代码使用 `result.card_sequence`——实际字段是 `result.draw_card_ids` | **伪代码修正：** `card_sequence` → `draw_card_ids` <!-- REVIEW-FIX-PREV: ISSUE-010 --> |
| `pool_card_counts` 未纳入 milestone 合并——per-pool GDR 分析遗漏里程碑产出 | **bonus_events 增加 `pool_id` 字段：** `after_draw(banner_id, pool_id)` 已知触发池，`on_bonus`/`bonus_events` 同时存储 `pool_id`。合并时同步更新 `pool_card_counts` <!-- REVIEW-FIX-PREV: ISSUE-011 --> |
| 计划波及范围表未含 `CLAUDE.md`——重大架构变更后未同步项目指令文件 | **波及范围表追加一行：** `CLAUDE.md`——扩展指南表格新增「新里程碑」行，架构分层注释新增 `core/milestone.py` 条目 <!-- REVIEW-FIX-PREV: ISSUE-012 --> |
| `run_batch_parallel` 单进程兜底路径（L307-325）与 `_wk_run_single` worker 路径（L242-267）是否正确构造 `MilestoneEngine` 并传入 `GachaService`——当前 plan-review 审查仅覆盖计划文件与靶向代码，未执行集成测试环境验证 | **M4b 实施后、M8 集成测试中追加：** 专门针对 `run_batch_parallel` 单进程兜底路径的测试用例——验证 `_run_single` 内部正确构造 `MilestoneEngine(defs, seed=seed)` 并传入 `GachaService.__init__`。同时验证 `_wk_env.milestone_defs` 经 pickle 正确序列化/反序列化（`SimulationEnv.from_dict()` 需含 `milestone_defs`）。当前 M8 仅计划 7 个 G20 场景 TOML 配置测试——需追加至少 1 个批量并行路径覆盖用例。参见 ISSUE-006 <!-- REVIEW-FIX-PREV: ISSUE-006 --> |
| `RetreatConfigBuilder.build` 不拷贝 milestone——截断模式恒空 milestone，与完整时间线模式行为不自洽，§3.1「GDR 始终包含里程碑奖励」对截断模式不成立（REVIEW-R1-FIX: ISSUE-005） | **M4b 追加（REVIEW-R1-FIX: ISSUE-306 扩展）：** `RetreatConfigBuilder.build` 透传 `original_store.milestone`（截断起点计数器归零语义：截断池的 milestone 计数器从 0 重新累计——与 `pity_counter_init` 同一语义）。**同时透传 `original_store.card_overflow_map` + `original_store.rarity_defaults`（或在截断 store 上执行等价 overflow map 构建）**——否则截断模式 milestone 赠卡走 `state.add_card(overflow_bands=card_overflow_map.get(cid))` 时空 map 无溢出资源，与完整时间线模式（含溢出）数值不同，「截断与完整模式一致」验收项不成立。若产品侧认为截断模式不应含里程碑或不应含溢出，需显式声明为预期差异并同步收敛验收项措辞——**⚠ 待人工裁决**，本计划按「透传 milestone + 溢出数据」实施 |
| `infer_events` 双路径分类分裂——draw-sequence 路径不含赠卡、aggregate 路径含赠卡，同一池「事件 miss 但 GDR 成功」矛盾叙事，AA/BB/AB/BA 交叉统计受污染（REVIEW-R1-FIX: ISSUE-007） | §3.6b 口径裁决：池成败/事件分类只认 draw 序列——`infer_events` 读 `pool_card_counts` 时按 `bonus_events[].card_ids` 减赠卡恢复 draw 口径；**减赠卡数据源 = `compact['bonus_events']`，aggregate 路径（process_analysis_panel L474）经 `extract_aggregate` 透传键供给——REVIEW-R1-FIX: ISSUE-315**；`extract_process` 的 success（GDR 口径）与 pool_events（draw 口径）分别标注、语义不同 |
| `compute_config_hash` 未纳入 milestone——仅 milestone 不同的数据集被判「配置: 相同」，`only_strategy_differs()`/`mode_label()` 可能误判纯策略比较（REVIEW-R1-FIX: ISSUE-008） | `compute_config_hash` 纳入 milestone 字段（name/threshold/repeat/max_triggers/banner/bonus_reward），main_window 调用处透传 `store.milestone`；或显式在文档标注可比性不含 milestone 维度（倾向前者） |
| kept_sequences GUI 轨迹消费方未被覆盖——轨迹图目标达成率系统性低于聚合 GDR（含 milestone），面板内跨图表数据不一致（REVIEW-R1-FIX: ISSUE-009） | M5-stream kept_sequences 提取处按 `bonus_events[].draw_index` 插入赠卡构建 `merged_card_ids`（平行对齐全部逐抽数组——kept_sequences L197-204 复制全部 6 个数组，含 `draw_pity`/`draw_resources_consumed` 等，REVIEW-R1-FIX: ISSUE-304；赠卡 pity 标志占位 False、consumed 占位 {}），面板代码零改动即自动反映。**REVIEW-R1-FIX: ISSUE-102——此修复在 streaming 提取处直接构建按抽序数组，独立于从未存在的 `_merge_milestone_cards()`（gdr.py 不新增该函数、无「删除」对象——措辞修正 REVIEW-R2-FIX: GATE-变更粒度，不消费其假设的 `Dict[str, List[int]]` 映射，避免两处冗余实现）** |
| `_populate_milestone_cards_list` 全文无调用点——固定卡多选区域不可用、`_on_milestone_selected` 的 setSelected 无 item 可操作（REVIEW-R1-FIX: ISSUE-010） | M7b2：调用点 = `_refresh_from_store_impl()` store 就绪后（见 §3.8.5a 回填段）；验收项补固定卡列表非空断言 |
| `_build_milestone` 裸异常（`m['name']` KeyError / `int()` ValueError）绕过 ConfigError 通道 + card_id 引用未校验（REVIEW-R1-FIX: ISSUE-012）+ **校验对象抄错导致任何带 cards 配置恒抛 ConfigError（REVIEW-R1-FIX: ISSUE-101）** | §3.7 修订：name 用 `m.get('name','').strip()` + ConfigError；threshold/max_triggers 用 try/except 转 ConfigError；`bonus_reward.cards`/`random_cards[].candidates` 引用 card_id 解析期校验存在性（对照 `_build_pools` 对 `epitomizable_cards` 的 ConfigError 先例 config_toml.py L1081）。**ISSUE-101 修正：先 `known_card_ids = {c.card_id for c in store.card_defs}` 构建 id 集合再判断——禁止 `cid not in store.card_defs`（store.card_defs 是 List[CardDefEntry]，str in 列表恒 False，任何带 cards 的配置必然抛 ConfigError、load_toml 全失败）**；UT2 补「cards 引用有效卡加载成功」正例 |
| 新核心模块未纳入 `core/__init__.py` 显式 re-export + `__all__` 清单（REVIEW-R1-FIX: ISSUE-013） | M3：补导出 `MilestoneEngine`/`MilestoneDef`/`MilestoneConfig`——`get_milestone_defs()` 返回类型已成 `StrategyContext` 公共接口一部分 |
| 资源表手输空行与「从 store.resource_defs 填充」声明脱节，UI 无资源 ID 校验——用户可输入未定义资源 ID，TOML 层 `_build_milestone` 同样不校验 resources 键存在性，幽灵资源键污染模拟（REVIEW-R1-FIX: ISSUE-104） | **M7b2 追加：** 资源列（列0）改为可编辑 `QComboBox`（候选 = `store.resource_defs` 键）；`_add_milestone_resource` 插入下拉行、`_flush_milestone_current_detail` 兼容下拉/item 两种形态读取；**`apply_to_store()` 校验资源 ID 未定义给出警告**（不阻塞保存，用户自查，与场景 6「先定义 `endfield_next_voucher`」流程呼应）。**REVIEW-R1-FIX: ISSUE-311——警告带一次性去重（`self._warned_milestone_resource_ids` 集合），预览链路仅首次弹窗、后续静默，避免模态框阻塞编辑与模拟启动** |
| `_populate_milestone_cards_list` 用 `for cid, entry in self._store.card_defs.items()` 迭代——`ConfigStore.card_defs` 是 `List[CardDefEntry]`（config_store.py L129）无 `.items()`，任何含 [[milestone]] 配置的加载/导入/重载在 M7c 回填段即 AttributeError（REVIEW-R1-FIX: ISSUE-301） | **M7b2 修正：** 改为列表迭代 `for entry in self._store.card_defs: cid = entry.card_id; rarity = (entry.rarity or '?').upper()`（对照 `_sync_weight_cards`/`_build_pity` 列表访问模式）；`_on_milestone_selected` 的 setSelected 依赖此列表填充，修复后固定卡多选可正常回填 |
| `from_config_store()` 提取 `milestone_defs` 忽略 `enabled` 总闸——用户取消「启用累抽奖励」（apply_to_store 写 enabled=False、milestones 仍保留）后直接运行模拟，MilestoneEngine 仍被构造、里程碑照常触发，总闸运行时无任何效果（REVIEW-R1-FIX: ISSUE-302） | **M4b 修正：** 提取时加入 enabled 门控 `_ms_cfg = getattr(config_store, 'milestone', MilestoneConfig()); _milestone_defs = list(_ms_cfg.milestones) if _ms_cfg.enabled else []`（§3.2a），与 pity 路径 `_build_pity_engine_from_gui`（batch_simulator.py L87）的 enabled 语义对齐——两处组合成「禁用=无效+保存即删除」闭环，本修正封堵 runtime 侧 |
| `_flush_milestone_current_detail` 用 `currentRow()` 定位——currentRowChanged 触发时 currentRow() 已是新行，flush 用旧行控件值覆写新行数据，且 flush 末尾 `item(row).setText` 用旧行名称重命名新行列表项（REVIEW-R1-FIX: ISSUE-001） | **M7b2 修正：** 新增 `self._current_milestone_row` 属性（仿 `_flush_pity_current_detail` 的 `_current_pity_row`）——`_on_milestone_selected` 先 flush 到该旧行、再赋值为新 row、最后回填控件；`_flush_milestone_current_detail` 读该属性而非 `currentRow()`；回填时重置为 -1 |
| 多个随机卡池共存时 `_selected_random_pool_idx` 无用户选择机制——「编辑」恒作用于池 0（REVIEW-R1-FIX: ISSUE-003） | **M7b2 修正：** `ml_random_summary` 纯文本 QLabel 换为可点击 `QListWidget`（`ml_random_pool_list`），`currentRowChanged` → `_on_random_pool_selected` 实时维护 `_selected_random_pool_idx`；切换里程碑时池选中重置为 0；`_update_milestone_random_summary` 重绘后 clamp 恢复选中 |
| 资源金额 `float()` 无异常守卫——非数字输入在 Qt 信号槽内崩溃；空金额行持久化 `{rid: 0.0}` 语义噪音（REVIEW-R1-FIX: ISSUE-004） | **M7b2 修正：** `_flush_milestone_current_detail` 金额读取 try/except 回落 0.0；`amount == 0` 的资源项统一过滤不入库；`_add_milestone_resource` 默认 0 金额注释标注过滤行为 |
| §3.4 示例 `[[milestone]]` 段引用未定义卡（`limited_operator`/`ssr_ibaraki` 等）——ISSUE-101 校验实施后 shipped config.toml 无法加载（REVIEW-R1-FIX: ISSUE-002） | **config.toml 更新任务改：** 新增示例段的同时补全被引用卡/资源的 `[card]`/`[resources.defs]` 定义（或改用现有 `limited_ssr_1` 等卡）；M2 验收补「含示例段后 `load_toml()` 成功」断言；资源键在 TOML 层不校验（幽灵键静默注入）为已知不对称，由 UI 侧 ISSUE-104 警告 + shipped 配置自查覆盖 |
| `random_cards.count` 未解析期校验——负数/字符串/浮点/0 分别抛 ValueError/TypeError/空列表，worker 静默失败或里程碑无效无提示（REVIEW-R1-FIX: ISSUE-301） | **§3.7 修订：** count 解析期 try/except 转整数 + `count >= 1` 校验转 ConfigError（对照 threshold 校验模式）；**§3.8.3 修订：** `RandomCardPoolDialog` 抽取张数 `QSpinBox` 下限设 1——UI 中间态与解析期校验一致，杜绝 round-trip 断裂 |
| weights 全零校验缺陷——纯非数字字符串列表 float() 抛裸 ValueError 绕过 ConfigError；前部非零时 all() 短路校验静默通过、运行时 TypeError（REVIEW-R1-FIX: ISSUE-302） | **§3.7 修订：** 权重校验改写为逐项 try/except `float(w)` 转数值，非数字值抛 ConfigError（不靠 all() 短路隐式放行）；校验结果统一转 float 存 `w_norm` 作为运行时权重规范化基准 |
| `bonus_reward.resources` 值未校验为数值——字符串值在 M4 注入 `resources.get(k, 0) + v` 与 on_bonus 合并 `dpg.get(k, 0) + v` 均 TypeError，worker 静默失败（REVIEW-R1-FIX: ISSUE-303） | **§3.7 修订：** 遍历 resources 值做 `isinstance(v, (int, float))` 数值校验（bool 一并排除），非数值抛 ConfigError——与 cards 引用校验强度对齐 |
| 全零权重是 UI 合法中间态但 apply_to_store 不过滤——保存后 load_toml 抛 ConfigError 全配置不可加载（REVIEW-R1-FIX: ISSUE-304） | **§3.8.5a 修订：** apply_to_store 过滤条件扩展为「candidates 为空 或 weights 全零」——UI 中间态与解析期校验对称；数据源权重必为数值（UI QDoubleSpinBox / ISSUE-302 校验后的回填），float(w) 转换安全 |
| `get_counter()`/`get_milestone_counter()` docstring「距离还差几抽」与实现（累计已抽数）不符——误导策略作者写反方向判断（REVIEW-R1-FIX: ISSUE-305） | **§3.2/§3.5a 修订：** docstring 改为「当前累计抽数」并注明余量 = `md.threshold - get_counter(name)`；策略使用示例保持正确写法 |
| 方案 B 赠卡行使 cumulative_draws 分母含赠卡——cumulative GDR 与 compact/单池 GDR 分母不一致，每抽指标被系统性稀释（REVIEW-R1-FIX: ISSUE-306） | **M5-stream 修订：** 赠卡行插入时对 `cum_draws`/`cumulative_draws`（streaming.py L257/L512）不做递增——赠卡计入卡计数与热力图点、不计入抽数分母；补「累积模式与 compact 模式分母一致」断言 |
| §3.6b 口径裁决未覆盖转变分析——streaming 预计算 transition_flags（L277/L296 cum_cards 含赠卡）与回退路径 compute_transition_flags_from_gdr（cumulative_snapshots/aggregates 含赠卡）判「池成功」与 infer_events 的「池失败」矛盾（REVIEW-R1-FIX: ISSUE-307） | **§3.6b 修订：** 口径裁决扩展——streaming transition_flags 预计算与 `compute_transition_flags_from_gdr` 判定时按 `bonus_events[].card_ids` 减赠卡恢复 draw-only 口径（与 ISSUE-007 一致）；或显式声明转变分析为「赠卡含入口径」——⚠ 待人工裁决，本计划按 draw-only 实施。**REVIEW-R1-FIX: ISSUE-312 补充——回退路径无 bonus_events 数据通道：** cumulative_snapshots schema（streaming.py L266-276）与 aggregates（extract_aggregate）均不携带 bonus_events，「减赠卡」无数据源。数据通道 = `compute_transition_flags_from_gdr` 新增 `bonus_events` 参数 + analysis_panel L1287/L1361 从 `self.results` 透传。**REVIEW-R1-FIX: ISSUE-316 修正——`self.results` 非 `CompactResult.to_dict()` 产物而是 `extract_aggregate` 产物（aggregate_data），原「to_dict 产物含 bonus_events 键」陈述不成立、`r.get('bonus_events', [])` 恒空；数据通道改为 `extract_aggregate` 输出新增 `bonus_events` 键（M5-stream，与 ISSUE-315 同款）** |
| 回退路径转变标记口径统一后，`DrawSequenceExtractor._update_transition`（L536-564）六路径表要求「方案 B 插入赠卡」、验收要求「转变标记不遗漏」，与 ISSUE-307 draw-only 口径自相矛盾（REVIEW-R1-FIX: ISSUE-313） | **§3.6 六路径表 + 验收修订：** `_update_transition` success 判定按 `bonus_events[].card_ids` 减赠卡恢复 draw-only（与 WorkerLocalExtractor.process L277/L296 一致）；DrawSequenceExtractor 当前无调用方，统一口径消除六路径表与验收矛盾（潜伏一致性风险） |
| `_on_milestone_selected` 回填段缺 blockSignals——级联 flush 用上一行控件旧值覆写新行 bonus_reward，点击行后 500ms 内预览链路把损坏数据写入 store.milestone（REVIEW-R1-FIX: ISSUE-310） | **§3.8.5 修订：** 回填段对所有已连接 flush 信号的控件（ml_name_edit/ml_banner_edit/ml_threshold_spin/ml_max_triggers_spin/ml_repeat_check）包 `blockSignals(True)`，回填完成恢复后主动 flush 一次（对照 `_on_pity_selected` L1342-1344/L1395-1397 先例）；验收补「点击行后 `_milestone_defs[row].bonus_reward` 仍等于 store 原始值」断言 |
| 未定义资源 ID 警告挂在 apply_to_store 循环内——预览链路（500ms 去抖 → get_config → apply_to_store）持续弹模态框，『一次性警告』无实现（REVIEW-R1-FIX: ISSUE-311） | **§3.8.5a 修订：** `_setup_milestone_config` 初始化 `self._warned_milestone_resource_ids = set()`，apply_to_store 中对未定义 rid 仅首次提示并加入集合，后续预览/模拟启动链路静默（保守方案，不新增保存钩子） |
| `_flush_milestone_current_detail` 空名回退 `f"milestone_{row+1}"` 不保证唯一——清空名称后可能与另一行同名，保存后『里程碑名称重复』ConfigError 使整个 config.toml 无法加载（REVIEW-R1-FIX: ISSUE-314） | **§3.8.5 修订：** 空名回退复用 `_add_milestone` 查重循环生成不冲突名称（查重排除当前行自身）；M8 补「清空名称后保存→加载成功」round-trip 用例 |

---

## 八、验收标准

- [ ] `[[milestone]]` 独立 TOML 段解析正确——与 `[[pity]]` 互不影响
- [ ] `bonus_reward.cards`——达阈值后固定卡经 `state.add_card(cid, path="milestone_gift", overflow_bands=...)` 直入 `state.acquired`，不修改概率分布
- [ ] `bonus_reward.resources`——达阈值后资源注入 `resources`（可用性）+ `on_bonus` 源头归因（方案 C，2026-08-03；不并入当抽 combined_gained、不双重入账）
- [ ] `bonus_reward.random_cards`——达阈值后从候选池加权随机抽取指定张数（使用 `self._rng.choices()` 保证可复现），直入 `state.acquired`
- [ ] `cards` + `resources` + `random_cards` 可同时配置、同时生效——一次触发可同时赠送卡+资源+随机卡
- [ ] `repeat = false`（at=N）：触发一次后永久停用，计数器不复位
- [ ] `repeat = true`（every=N）：触发后计数器归零继续计数，下一轮继续触发
- [ ] `max_triggers` 正确限制触发次数——达上限后永久停用；默认 0 = 无限触发
- [ ] `banner` 正确过滤——空字符串 = 全部 Banner，非空 = 仅该 Banner 内触发（2026-08-02 起无 `"*"` 字符串兼容，原 pools 已删除）
- [ ] bonus 注入不触发常规保底重置（`hard`/`soft` 计数器不受 milestone 影响）
- [ ] milestone 注入的卡经 P63 `state.add_card(path="milestone_gift", overflow_bands=card_overflow_map.get(cid), initial_counts=...)` 统一管道正确触发溢出（`match_overflow_bands()` 自动匹配分段表），与正常抽卡一致
- [ ] milestone 溢出资源 + 直接资源注入 `resources` + `on_bonus` 源头归因（方案 C，2026-08-03；不进 rg/combined_gained，不双重入账）
- [ ] `collector.on_bonus()` 记录归因元数据（`milestone_name`、时间戳、`pool_id`、`draw_index`、赠送卡 ID、资源金额）——资源走源头归因（方案 C，2026-08-03；不并入当抽 combined_gained）
- [ ] `SharedResultCollector` 流式聚合包含 milestone——方案 A 源头合并自动覆盖（`extract_aggregate` 读取的 `card_counts`/`pool_card_counts` 已含 milestone，无需新增 `on_bonus` 方法；M5-serial 验证）
- [ ] `CompactResult.to_dict()`/`from_dict()` 正确序列化/反序列化 `bonus_events`——并行模拟不丢数据
- [ ] **`result.total_gained` 合并而非覆盖（M5-serial，REVIEW-R2-FIX: GATE-变更粒度）**——gacha_service.py L419 改为合并：`merged = dict(total_gained); for k, v in result.total_gained.items(): merged[k] = merged.get(k, 0) + v; result.total_gained = merged`（on_bonus 已把 milestone 资源并入 `result.total_gained` 对象字段，覆盖赋值会整体丢失）；最终 `final_resources` / `total_gained` / `draw_resources_gained` 三处一致
- [ ] **M4 阶段带里程碑配置跑模拟不崩溃（REVIEW-R2-FIX: GATE-依赖顺序）**——`SimulationCollector.on_bonus` 具体 no-op 默认由 M4 提供（先于 M5-serial 的调用点），M4 验收含里程碑配置路径；milestone 产出静默丢弃属预期、M5-serial 后可见
- [ ] GDR 计算含 milestone（REVIEW-R1-FIX: ISSUE-001 + ISSUE-102 裁决）——方案 A 生效时 `compute_gdr_from_compact`/`compute_gdr_from_cumulative` 入口**不调用**任何合并函数（`card_counts`/`pool_card_counts` 源头已合并）；**`_merge_milestone_cards()` 在代码库从未存在（grep 全仓核实，REVIEW-R2-FIX: GATE-变更粒度——无删除对象、gdr.py 零代码改动）**——时序合并由 M5-stream streaming 提取处（方案 B `merged_card_ids` 按抽序平行数组）统一完成，gdr.py 不保留、也不曾存在任何合并函数
- [ ] GDR 合并不改函数签名——`compute_gdr_from_compact` / `compute_gdr_from_cumulative` 签名零改动，合并全部由 `on_bonus` 源头（卡计数/资源）与 M5-stream streaming 方案 B（时序数组）完成，**不在 GDR 入口处做任何合并调用**（`compute_gdr_from_history` 不存在；历史路径通过 `GeneralizedDropRate` 子类直接迭代 `InfoVector`，无统一入口函数）<!-- REVIEW-FIX-PREV: ISSUE-005 -->
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
- [ ] `from_config_store()` 提取 `milestone_defs` 尊重 `enabled` 总闸——`store.milestone.enabled=False` 时模拟运行不构造/不触发 MilestoneEngine（REVIEW-R1-FIX: ISSUE-302，与 pity `enabled` 语义一致，batch_simulator.py L87 对齐）
- [ ] `build_strategy_context()` (`strategy_context_builder.py`) 签名含 `_milestone_engine` 参数——派生字段（`future_resource_gains` / `inter_pool_pity_links`）不丢失
- [ ] `apply_to_store()` 将 `self._milestone_defs` 写回 `store.milestone.milestones`——GUI 编辑可持久化到 TOML
- [ ] 资源表资源 ID 来源统一——列0 为可编辑 `QComboBox`（从 `store.resource_defs` 填充，与 §3.8.2 声明一致）；保存时未定义资源 ID 给出警告提示，且带一次性去重（`self._warned_milestone_resource_ids` 集合——同一 rid 仅首次弹窗，预览/模拟启动链路不持续阻塞，REVIEW-R1-FIX: ISSUE-104 + ISSUE-311）
- [ ] `refresh_from_store()` 回填 `self._milestone_defs`（在 `_refresh_from_store_impl()` 内，REVIEW-R1-FIX: ISSUE-003——挂载点从无调用方的 `set_config()` 迁移）——加载已有配置后里程碑 Tab 正确显示
- [ ] `get_config()` 返回字典含 `'milestone'` 键——`_do_update_preview()` 中里程碑摘要可正常渲染
- [ ] 里程碑列表切换不破坏数据——`_flush_milestone_current_detail` 读 `_current_milestone_row`（仿 `_flush_pity_current_detail` 的 `_current_pity_row` 模式），`_on_milestone_selected` 先 flush 到旧行、再赋值为新 row、最后回填控件；切换列表行时不会用旧行控件值覆写新行数据，列表项名称不会被旧行文本重命名（REVIEW-R1-FIX: ISSUE-001）。**回填段以 `blockSignals(True)` 阻断级联 flush（对照 `_on_pity_selected` L1342-1344/L1395-1397），回填完成恢复信号后主动 flush 一次——点击行后 `_milestone_defs[row].bonus_reward`（cards/resources/random_cards）仍等于 store 原始值（REVIEW-R1-FIX: ISSUE-310）**
- [ ] shipped `config.toml` 含 §3.4 示例 `[[milestone]]` 段后 `load_toml()` 成功——被引用卡（`limited_operator`/`ssr_ibaraki` 等）已在 `[card]` 定义（或示例改用现有 `limited_ssr_1` 等卡），被引用资源（`fragment_s`/`coin`/`exchange_currency`/`endfield_next_voucher`）已在 `[resources.defs]` 定义或显式接受幽灵键（REVIEW-R1-FIX: ISSUE-002）
- [ ] 随机卡池可点击选中——`ml_random_pool_list` 行选中（`_on_random_pool_selected`）即更新 `_selected_random_pool_idx`，「编辑」作用于当前选中池而非恒为池 0；切换里程碑时池选中重置为 0（REVIEW-R1-FIX: ISSUE-003）
- [ ] 资源金额输入非数字不崩溃——`float()` 读取有 try/except 守卫（非数字回落 0）；未编辑金额（0 值）的资源行不持久化为 `{rid: 0.0}` 条目（REVIEW-R1-FIX: ISSUE-004）
- [ ] `bonus_events` 含 `pool_id` 字段——per-pool GDR 分析可正确归因里程碑产出
- [ ] 流式路径 `_update_cumulative()` 包含 bonus 卡——流式 GDR 不遗漏 milestone 产出<!-- REVIEW-FIX-PREV: GATE-6-测试策略-流式路径 -->
- [ ] 流式路径 `WorkerLocalExtractor.process()` 热力图分箱包含 bonus 卡贡献——不遗漏<!-- REVIEW-FIX-PREV: GATE-6-测试策略-流式路径 -->
- [ ] 流式路径 `WorkerLocalExtractor.process()` 转变标记 draw-only 口径——success 判定按 `bonus_events[].card_ids` 减赠卡再 `_check_success`（REVIEW-R1-FIX: ISSUE-307），与 `infer_events` 池成败一致；热力图分箱仍含 bonus 卡贡献（不遗漏）<!-- REVIEW-FIX-PREV: GATE-6-测试策略-流式路径 -->
- [ ] 流式路径 `DrawSequenceExtractor._update_heatmap()` 热力图分箱包含 bonus 卡贡献——不遗漏<!-- REVIEW-FIX-PREV: GATE-6-测试策略-流式路径 -->
- [ ] 流式路径 `DrawSequenceExtractor._update_transition()` 转变标记 draw-only 口径——success 判定按 `bonus_events[].card_ids` 减赠卡（与 `WorkerLocalExtractor.process` L277/L296 及 ISSUE-307 一致）；DrawSequenceExtractor 当前无调用方，统一口径消除六路径表与验收矛盾（REVIEW-R1-FIX: ISSUE-313）<!-- REVIEW-FIX-PREV: GATE-6-测试策略-流式路径 -->
- [ ] 流式路径 `WorkerLocalExtractor.process()` **累积快照段**（L218-304）包含 bonus 卡贡献——`analysis_panel` L1091-1107 / `process_analysis_panel` L513-524 累积模式 GDR 不遗漏 milestone 产出（REVIEW-R1-FIX: ISSUE-004）
- [ ] 方案 B merged_card_ids **平行数组对齐**——赠卡插入同步对齐**全部逐抽数组** `draw_times`/`draw_pool_ids`/`draw_resources_gained`/**`draw_pity`（占位 False）/`draw_resources_consumed`（占位 {}）/`draw_pity_names`（占位 None）/`draw_pity_counter_max`（占位 0）**（REVIEW-R1-FIX: ISSUE-304——流式循环同下标读取 `pity_flags[i]`/`draw_res_consumed[i]`，漏插则插入点后每行行错位），池时点截断继承 `draw_times[draw_index]`；**插入位置 = `draw_index + 1`（触发抽之后），`draw_resources_gained` 占位值 = `{}`（milestone 资源已在 on_bonus 归因到原 draw_index 行）**；**`draw_card_ids` 与 `draw_resources_gained` 逐抽配对长度一致、遍历不越界（ISSUE-105 逐抽配对语义）**（REVIEW-R1-FIX: ISSUE-002/103/105）
- [ ] kept_sequences 轨迹含 bonus 卡——`analysis_panel` GDR 演化样本路径（L779）/SSR 热力图（L834）/瀑布图（L928/L979）与 `gacha_panel` 轨迹目标达成率不系统性低于聚合 GDR（REVIEW-R1-FIX: ISSUE-009）
- [ ] 事件分类口径——`infer_events` 池成败/事件分类只认 draw 序列（读 `pool_card_counts` 按 `bonus_events` 减赠卡，**数据源 = `compact['bonus_events']`；`process_analysis_panel` aggregate 路径经 `extract_aggregate` 输出透传该键，REVIEW-R1-FIX: ISSUE-315**），与 GDR（含 milestone）语义分别标注、不构成矛盾叙事（REVIEW-R1-FIX: ISSUE-007）
- [ ] 转变分析 draw-only 口径——streaming 预计算 `transition_flags`（`WorkerLocalExtractor.process` L277/L296 判定 `cum_cards` 按 `bonus_events` 减赠卡）与回退路径 `compute_transition_flags_from_gdr`（per_pool_analysis.py L285，**判定前按新增 `bonus_events` 参数减赠卡——数据通道由 analysis_panel L1287/L1361 从 `self.results` 逐 sim 透传 `'bonus_events'` 键；`self.results` 为 `aggregate_data`（`extract_aggregate` 产物）而非 `CompactResult.to_dict()` 产物，`bonus_events` 键须由 `extract_aggregate` 输出透传（M5-stream）保证非恒空，REVIEW-R1-FIX: ISSUE-312 + ISSUE-316**）与 `infer_events` 的 draw-only 池成败一致、两面板无矛盾叙事（REVIEW-R1-FIX: ISSUE-307）
- [ ] 累积模式 GDR 分母与 compact/单池一致——方案 B 赠卡行不计入 `cumulative_draws`/`cum_draws`（streaming.py L257/L512），`compute_gdr_from_cumulative` 的 `total_draws`（gdr.py L1132）不含赠卡（REVIEW-R1-FIX: ISSUE-306）
- [ ] apply_to_store 过滤全零权重池——UI 权重全 0 的随机池保存时被过滤（不写出），`load_toml()` 不因全零权重抛 ConfigError、round-trip 不断裂（REVIEW-R1-FIX: ISSUE-304）；`RandomCardPoolDialog` 抽取张数 `QSpinBox` 下限 1（REVIEW-R1-FIX: ISSUE-301 UI 侧）
- [ ] 清空里程碑名称后保存→加载成功——`_flush_milestone_current_detail` 空名回退复用 `_add_milestone` 查重循环生成不冲突名称（查重排除当前行自身），保存后 `load_toml()` 不抛『里程碑名称重复』ConfigError（REVIEW-R1-FIX: ISSUE-314；M8 补「清空名称→保存→加载」round-trip 用例，覆盖 `_remove_milestone` 行号位移后回退名漂移场景）
- [ ] `RetreatConfigBuilder.build` 透传 milestone + 溢出数据——截断模式（`from_pool_id` 指定）与完整时间线模式 GDR/最少资源/Pareto 搜索结果一致（REVIEW-R1-FIX: ISSUE-005 + ISSUE-306：**透传范围含 `original_store.milestone` + `card_overflow_map` + `rarity_defaults`，保证 milestone 赠卡溢出资源两模式数值一致**）
- [ ] `compute_config_hash` 纳入 milestone——仅 milestone 配置不同的数据集判为「配置: 不同」而非「配置: 相同」（REVIEW-R1-FIX: ISSUE-008）
- [ ] `_build_milestone` 输入校验统一 ConfigError——缺 name / 非法 threshold / 非法 max_triggers / card_id 引用不存在均抛 `ConfigError` 而非 KeyError/ValueError 裸异常；card_id 存在性校验用 `known_card_ids = {c.card_id for c in store.card_defs}` 集合判断（**cards/random_cards 引用有效卡必须成功加载——UT2 补正例，REVIEW-R1-FIX: ISSUE-101**）（REVIEW-R1-FIX: ISSUE-012）。**扩展：random_cards 权重逐项 float 数值校验（含非数字值 `["high"]` 抛 ConfigError 而非裸 ValueError，REVIEW-R1-FIX: ISSUE-302）+ count 整数校验且 ≥1（REVIEW-R1-FIX: ISSUE-301）+ resources 值数值类型校验（非 int/float 抛 ConfigError，REVIEW-R1-FIX: ISSUE-303）**
- [ ] `_populate_milestone_cards_list` 有调用点且固定卡列表非空——`refresh_from_store()` 后 `ml_cards_list.count() == len(store.card_defs)`（REVIEW-R1-FIX: ISSUE-010；**且对 `List[CardDefEntry]` 迭代不抛 AttributeError——修复 `.items()` 误用，REVIEW-R1-FIX: ISSUE-301**）
- [ ] `core/__init__.py` 导出 `MilestoneEngine`/`MilestoneDef`/`MilestoneConfig`——`from gacha_simulator.core import MilestoneEngine` 可用（REVIEW-R1-FIX: ISSUE-013）
- [ ] 方案 A/B 互斥——若实施 `on_bonus` 源头合并（方案 A），milestone 卡不被双重计入（**`_merge_milestone_cards` 在代码库从未存在、不存在第二写入路径**，REVIEW-R1-FIX: ISSUE-102，措辞修正 REVIEW-R2-FIX: GATE-变更粒度）；`card_counts['milestone_card']` 恰好等于 bonus_events 中该卡出现次数（`sum(1 for ev in bonus_events for cid in ev['card_ids'] if cid == 'milestone_card')`）<!-- REVIEW-FIX-PREV: GATE-6-测试策略-方案AB互斥 -->
- [ ] 里程碑卡溢出——满突后 milestone 赠送触发 `match_overflow_bands()`，溢出资源注入 `state.resources` + `on_bonus` 归因；`draw_resources_gained[draw_index]` 反映溢出金额（方案 C，2026-08-03）<!-- REVIEW-FIX-PREV: GATE-6-测试策略-溢出 -->
- [ ] 空抽计数推进——`_NO_CARD_ID` 抽数正常计入累抽进度；计数器值 = `after_draw` 调用次数（含空抽）<!-- REVIEW-FIX-PREV: GATE-6-测试策略-空抽计数 -->
- [ ] 同抽多触发顺序确定性——第 50 抽同时触发 threshold=10 和 threshold=50 两个 milestone；`bonus_events` 顺序 = TOML `[[milestone]]` 定义顺序（`for name, md in self._defs.items()` 迭代顺序即 dict 插入顺序 = TOML 数组顺序）<!-- REVIEW-FIX-PREV: GATE-6-测试策略-同抽多触发顺序 -->
- [ ] 场景 1（火影每 10 抽碎片）——25 抽 → `len(bonus_events) == 2`，`resources['fragment_s'] == 2`<!-- REVIEW-FIX-PREV: GATE-6-测试策略-具体期望 -->
- [ ] 场景 3（火影首付返利）——150 抽 → `len(bonus_events) == 1`，`card_counts['limited_ssr_1'] == 1`（**M8 测试配置保证 `limited_ssr_1` 不在池 distribution——仅作赠卡，否则 `== 1` 断言被自然抽卡破坏**，REVIEW-R1-FIX: ISSUE-107），`is_active('naruto_first_payback_s') == False`<!-- REVIEW-FIX-PREV: GATE-6-测试策略-具体期望 -->
- [ ] 场景 4（阴阳师 40 抽随机 SSR）——80 抽、固定 seed → `sum(card_counts.values())` 赠卡 == 1，且候选卡在 `ssr_candidates` 集合内；重复模拟同 seed → 同一张卡（可复现性）<!-- REVIEW-FIX-PREV: GATE-6-测试策略-具体期望 -->（**M8 测试配置保证 `ssr_candidates` 4 候选不在池 distribution——仅作赠卡候选，与 ISSUE-107 同款约束，否则 80 抽自然抽到任一张即破坏 `sum == 1` 断言，REVIEW-R1-FIX: ISSUE-307**）
- [ ] 场景 5（明日方舟 300 抽）——bonus 同时含 card + resource；`card_counts['limited_operator'] == 1`（**M8 测试配置保证 `limited_operator` 不在池 distribution——仅作赠卡**，REVIEW-R1-FIX: ISSUE-107）且 `resources['exchange_currency'] >= 300`（含正常产出溢出）<!-- REVIEW-FIX-PREV: GATE-6-测试策略-具体期望 -->
- [ ] `CLAUDE.md` 扩展指南 + 架构分层同步更新 `core/milestone.py` 条目
- [ ] pytest 全量通过

---
<!-- REVIEW-FIX-PREV: GATE-5-回滚路径 -->
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
| M5-serial | 删除 `collector.py` 中 `on_bonus` 方法定义 + `CompactCollector.on_bonus` 实现 + `CompactResult.bonus_events` 字段；移除 `to_dict()`/`from_dict()` 中 `bonus_events` 的序列化逻辑；gacha_service.py L419 回退为覆盖赋值 | collector + result_types + gacha_service 三文件回滚——`bonus_events` 列表始终为空时对下游无影响，但需清理代码以防误导 |
| M5-stream | 删除 `streaming.py` 中六路径 `merged_card_ids` 方案 B 插入逻辑 + kept_sequences 插入 + cum_draws/cumulative_draws 分母跳过分支 + transition_flags 减赠卡 draw-only 判定 | streaming.py 单文件回滚——删去赠卡行插入后流式路径回退为不含 milestone 产出的 draw-only 视图 |
| M5a | 无需操作（M5a 收敛为验证性改动——gdr.py 零代码改动、无删除对象，`_merge_milestone_cards` 在代码库从未存在，REVIEW-R2-FIX: GATE-变更粒度）；若需回退时序合并，删除 M5-stream 在 streaming 提取处的 `merged_card_ids` 插入逻辑 | GDR 计算回退为不含里程碑产出的裸出率——与删除 `[[milestone]]` TOML 段后重跑等效 |
| M7a | 删除 `config_panel.py` 中 `_setup_milestone_config()` 方法体 + `_setup_ui()` 中「累抽奖励」Tab 注册行 + left_tabs 中的 `addTab` 调用 | 仅 UI 层——`store.milestone` 数据仍存在但 Tab 不显示。调用方 `_setup_ui()` 中仅移除 `addTab` 行 |
| M7b1 | 删除 `config_panel.py` 中 `RandomCardPoolDialog` 类定义 | 若 M7b2 也回滚（其 `_edit_milestone_random_pool` 依赖此 Dialog），需同步删除引用 |
| M7b2 | 删除 `config_panel.py` 中 `_populate_milestone_cards_list` / `_add_milestone_resource` / `_remove_milestone_resource` / `_add_milestone_random_pool` / `_remove_milestone_random_pool` / `_edit_milestone_random_pool` / `_update_milestone_random_summary` / `_flush_milestone_current_detail` 方法体；移除 `_on_milestone_selected` 中奖励相关控件回填逻辑 | 仅 UI 层——里程碑数据 `self._milestone_defs` 仍存在但编辑入口消失 |
| M7c | 删除 `apply_to_store()` 中 `store.milestone.milestones` 写入段 + `_refresh_from_store_impl()` 中 `self._milestone_defs` 回填段 + `get_config()` 返回字典中 `'milestone'` 键 | 仅 UI→store 数据流断裂——里程碑 TOML 段仍可手工编辑，但 GUI 无法读写 |
| M8 | 删除 `tests/` 中里程碑相关测试文件/函数 | 测试套件回退为不含里程碑覆盖——已有测试不受影响 |

**回滚验证方法：**
1. 执行相应阶段的回滚操作
2. 运行 `pytest -q`——确认无 import 错误或测试失败
3. 删除已有 `[[milestone]]` TOML 段后运行模拟——确认无 crash
4. 若仅回滚 M7（UI 层），启动 GUI——确认「累抽奖励」Tab 不存在且其他 Tab 正常

**最简回滚路径（整体回退 P58）：** 删除 `core/milestone.py` 文件 + 移除 `config_store.py` 中新增 dataclass/字段 + 移除 `gacha_service.py` 中 bonus 消费块（`if _milestone_engine:` 块） + 移除 `config_panel.py` 中里程碑 UI 方法——其余所有代码因默认值守卫（`None` / 空列表 / 安全默认值）自动退化为无行为。
<!-- /REVIEW-FIX-PREV: GATE-5-回滚路径 -->

---

## ⚠ 自动化审查阻塞项

> **状态（2026-08-03 人工裁决）：** 阻塞项 ISSUE-310 已解决——修复方案（blockSignals + 回填后 flush）已写入计划 §3.8.5，对抗循环遗留的「回填后无显式 flush 调用」已补（L1344）。下述为原问题描述与解决记录。

### ISSUE-310（panel/GUI 配置面板）

**问题描述：**

计划 §3.8.5 的 `_on_milestone_selected`（L1273-1313）在切换到新行后，通过 `ml_name_edit.setText`/`ml_threshold_spin.setValue`/`ml_repeat_check.setChecked` 等逐一回填基础字段，但这些控件均已连接 `_flush_milestone_current_detail`（M7a L1239-1243）。回填期间 `_current_milestone_row` 已指向新行，每次 setText/setValue 触发 flush 时，尚未更新的控件（threshold/repeat/banner 以及 ml_cards_list 选中项、ml_resources_table）仍是上一行的值，被一并写入 `_milestone_defs[新行]`。随后 L1295-1308 的 setSelected/setRowCount 只更新视觉、不触发 flush。最终 `_milestone_defs[新行].bonus_reward.cards/resources` 残留上一行数据。点击行后 500ms 内 `_update_preview`→`get_config()`（config_panel.py L3057/L3230 开头调 apply_to_store）即把损坏数据写入 store.milestone，模拟与保存都使用错误赠卡/资源。对照既有 `_on_pity_selected`（config_panel.py L1342-1344/L1395-1397）明确用 blockSignals(True) 阻断回填期级联 flush，本计划完全省略该机制，计划的验收项「切换列表行时不会用旧行控件值覆写新行数据」无法达成。

**解决记录（2026-08-03 人工裁决）：**

- ✅ `blockSignals(True)` 阻断回填期级联 flush 已写入计划（§3.8.5 `_on_milestone_selected` 的 `_bs_widgets` 段）——对照既有 `_on_pity_selected` 先例
- ✅ 回填完成后主动 `self._flush_milestone_current_detail()` 调用已补（§3.8.5 L1344）——解决「预览不刷新」与「空名回退不即时应用」两个子项
- 至此 ISSUE-310 修复闭环，可进入实施

---

## 自动化审查记录

<details>
<summary>第 1 次审查（2026-06-11）——P38 工作流自动化</summary>

- 复杂度: complex | 变更性质: evolutionary
- 阶段 1 影响面: 80 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 47 个

</details>
