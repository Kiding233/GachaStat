<!-- META: P55 | module:保底系统 | status:completed | last:2026-07-19 | depends:P60✅ -->

# P55 保底体系重构——behavior 实现与配置集成

> 日期：2026-06-19 | 状态：设计中
> 触发：用户请求「会歪型软保底」（全体 SSR 每抽固定增量）+ 讨论中自然延伸至保底体系整体重构
> **原 Phase 1-4（平台层——PityState/DrawInfo/CounterBasedBehavior/BEHAVIOR_REGISTRY）+ 引擎调度 已提取至 [P60](../../../02-待办/P60%20基础平台——依赖消除与下游并行化.md)。本计划保留具体 behavior 实现（SoftInterval/Additive/Hard）+ 配置/UI/波及适配。**
> 依赖：[P60](../../../02-待办/P60%20基础平台——依赖消除与下游并行化.md)（提供 PityState / DrawInfo / PityContext / Counter / Flag / CounterBasedBehavior / BEHAVIOR_REGISTRY / PityEngine 调度器）

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-1 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-2 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-8 -->
## 零、实施前置条件与关键风险（代码审计注入）

> 以下7项为代码审计发现的阻塞性风险。每项必须在对应阶段实施前解决，否则保底管道将静默失效。

### 0.1 调用顺序：_parse_rarities() 必须先于 _build_pity() 执行（AUDIT-BREAK-1）

**风险：** 当前 `load_toml()`（`config_toml.py`）行59先调用 `_build_pity(data, store)`，行72后才调用 `_parse_rarities(data, store)`。新的 `_build_pity_def()` 需要 `rarity_rank_map` 做 scope 注册校验（若 scope 不在已注册稀有度中则 `ConfigError`）。此时 `rarity_rank` 为空 dict，所有 scope 校验均失败，全部保底配置被拒。

**修复方案（强制）：** 交换 `load_toml()` 中的调用顺序——先 `_parse_rarities()`，后 `_build_pity()`。或采用两阶段解析：`_build_pity()` 改为先收集原始数据、延迟到 `_parse_rarities()` 完成后统一校验。**推荐前者（交换顺序）——改动最小。**

伪代码：
```python
# load_toml() 修改前（当前顺序——错误）：
#   _build_pity(data, store)     # 行59：rarity_rank 尚为空
#   ...
#   _parse_rarities(data, store) # 行72：此时才填充 rarity_rank

# load_toml() 修改后（正确顺序）：
#   _parse_rarities(data, store) # 先解析稀有度——填充 rarity_rank
#   _build_pity(data, store)     # 再解析保底——此时 rarity_rank 已可用
```

### 0.2 rarity_rank 键大小写归一化（AUDIT-BREAK-2）

**风险：** P60 `_parse_rarities()` 将键 `.upper()` 存储（`{'SSR': 0, 'SR': 1}`）。`_build_pity()` 内 scope 默认为小写 `'ssr'`。若未归一化，`'ssr' not in {'SSR': 0, 'SR': 1}` → 校验失败。

**修复（强制）：** `_build_pity()` 调用 `_build_pity_def()` 之前，必须执行：
```python
rarity_rank_map = {k.lower(): v for k, v in store.rarity_rank.items()}
```
然后将 `rarity_rank_map`（而非 `store.rarity_rank`）传入 `_build_pity_def()` 的校验逻辑。计划 ISSUE-023 已识别此问题，补充到实施清单中。

### 0.3 GachaService probabilities key 语义断裂（AUDIT-BREAK-8）【CRITICAL】

**风险：** 这是整个保底管道的语义断裂点。当前代码：
```python
# GachaService.run_simulation_compact() 行176：
probabilities = {r.id: p for r, p in pool.rewards}
# 结果示例：{'limited_ssr_1': 0.005, 'standard_ssr_1': 0.005, 'sr_card_1': 0.05, ...}
```
此 dict 传入 `PityEngine.before_draw()` → `_build_draw_info()` → `DrawInfo.base_probabilities`。但 `SoftStepBehavior._compute_probabilities()` 中执行：
```python
scope_slots = ctx.draw.scope_slots.get(self._scope, ())
# scope_slots['ssr'] = ('ssr',)  —— 槽位 ID 为 'ssr'
pool = sum(result.get(s, 0.0) for s in non_target)
# result.get('ssr', 0.0) → 0.0  —— 'ssr' 键不存在于 base_probabilities 中！
```
**所有保底概率调整管道静默失效。**

**修复方案（二选一，推荐方案A）：**

- **方案A（推荐）：GachaService 按稀有度聚合概率。** 在 `before_draw()` 调用前，将 `{card_id: prob}` 聚合为 `{rarity: sum_probs}`：
  ```python
  # 聚合逻辑（在 GachaService.before_draw() 调用前插入）：
  rarity_probs = {}
  for rwd, prob in pool.rewards:
      rarity = self._pool_specs[pool.id].get_rarity(rwd.id)  # 或从 scope_cards 反查
      rarity_probs[rarity] = rarity_probs.get(rarity, 0.0) + prob
  # rarity_probs = {'ssr': 0.01, 'sr': 0.15, 'r': 0.84}
  ```
  此方案与 `scope_slots` 的槽位 ID（=稀有度名）语义一致，改动集中在 GachaService 一处。

- **方案B：scope_slots 使用卡牌 ID 列表。** 将 `scope_slots['ssr']` 设为具体卡牌 ID tuple（`('limited_ssr_1', 'standard_ssr_1')`），而非稀有度名。此方案改动 `_build_pool_pity_spec()` 中的槽位 ID 生成逻辑——但 `base_probabilities` 和抽卡后的 reward.id 已是卡牌 ID，无需聚合。

**实施决策：方案A（GachaService 聚合）为主路径——改动最小、语义最清晰。方案B 作为备选（若后续发现按稀有度聚合不足以满足某些复杂场景）。验收标准：`SoftStepBehavior._compute_probabilities()` 单元测试中 `scope_slots` 的 key 与 `ctx.current` 的 key 可正确匹配。**

**方案 A 实现——GachaService.before_draw() 调用前插入聚合逻辑：**

```python
# GachaService.run_simulation_compact() 中，before_draw 调用前

# 旧代码（行176）：
#   probabilities = {r.id: p for r, p in pool.rewards}
#   # → {'limited_ssr_1': 0.005, 'standard_ssr_1': 0.005, 'sr_1': 0.15, ...}

# 新代码——按稀有度聚合：
def _aggregate_probs_by_rarity(self, pool_id, pool, pity_spec):
    """将 {card_id: prob} 聚合为 {rarity: total_prob}。

    从 PoolPitySpec.scope_cards 反查每张卡牌的稀有度，
    按稀有度求和得到每个稀有度级别的总概率。
    scope_slots 的槽位 ID = 稀有度名（小写），聚合后的 key 与之对齐。
    """
    result = {}
    for rwd, prob in pool.rewards:
        rarity = self._get_rarity(rwd.id, pity_spec)
        if rarity:
            result[rarity] = result.get(rarity, 0.0) + prob
    return result

def _get_rarity(self, card_id, pity_spec):
    """从 PoolPitySpec.scope_cards 反查 card_id 的稀有度。
    scope_cards 格式：{'ssr': ('limited_ssr_1', 'standard_ssr_1'), 'sr': ('sr_1',), ...}
    """
    for rarity, cards in pity_spec.scope_cards.items():
        if card_id in cards:
            return rarity
    return None  # 非抽卡奖励（如资源）

# 调用点：
probs_by_card = {r.id: p for r, p in pool.rewards}
probs_by_rarity = self._aggregate_probs_by_rarity(pool.id, pool, pity_spec)
# probs_by_rarity = {'ssr': 0.01, 'sr': 0.15, 'r': 0.84}
probabilities = self._pity_engine.before_draw(pool.id, pity_state, probs_by_rarity)
```

**波及：** `batch_simulator.py` 中 `_worker_draw_loop()` 的 `before_draw` 调用也需走同一聚合路径。建议将 `_aggregate_probs_by_rarity()` 放在 `PityEngine` 或 `GachaService` 中作为共享方法。

### 0.4 PityDef 17字段重构——全链路断裂（AUDIT-BREAK-3）

**风险：** `PityDef` 从5字段（`name/type/params/target_distribution/reset_condition/pools`）增至17字段。`params` dict（所有值str类型）分裂为 `deltas(tuple|None)/threshold(int)/soft_start/soft_end/counter_init(int)` 等独立类型字段。`target_distribution` → `scope` + `target_featured` 替代。`reset_condition` → `target_featured` 推导。

所有访问旧字段的代码（约6文件）均断裂。**不可部分实施——PityDef 重构必须与所有消费方同步完成。**

### 0.5 PityConfig.counter_init 字段删除——5处 AttributeError（AUDIT-BREAK-4）

**风险：** `counter_init` 从 `PityConfig`（全局）移至 `PityDef`（per-behavior）。以下5处直接访问 `store.pity.counter_init` → `AttributeError`：

| 文件 | 行号 | 当前代码 | 修复 |
|------|------|---------|------|
| `config_panel.py` | 2269 | `counter_init = dict(store.pity.counter_init)` | 改为遍历 `store.pity.pities`，构建 `{pdef.name: pdef.counter_init}` |
| `config_panel.py` | 2921 | `store.pity.counter_init = {...}` | 改为将值写入每个 `PityDef.counter_init` |
| `config_panel.py` | 3037 | `store.pity.counter_init.get(p.name, 0)` | 改为 `p.counter_init`（直接从 PityDef 读取） |
| `batch_simulator.py` | 636 | `pity_cfg_dict.get('counter_init', 0)` | 新格式无此顶层键——从 `PityDef.counter_init` 读取 |
| `worst_impact.py` | 573 | `getattr(self.store.pity, 'counter_init', {})` | 改为遍历 `store.pity.pities` 读取每个 `PityDef.counter_init` |

### 0.6 PityEngine 构造函数签名变更——16+处调用断裂（AUDIT-BREAK-10）

**风险：** 签名从 `(pool_specs, pity_defs: Dict, behaviors: Dict, rarity_rank)` 变为 `(pool_specs, pity_defs: List[PityDef], state: PityState, rarity_rank)`。波及：

| 文件 | 位置 | 数量 |
|------|------|:--:|
| `batch_simulator.py` | `_build_pity_engine_from_gui()` 行190 | 1 |
| `worst_impact.py` | `_build_pity_engine()` 行528 | 1 |
| `test_pity.py` | 行161/213/224/233/260/285 | 6 |
| `test_p60_equivalence.py` | 行66/71/119/123/165/169/203/247/251/300 | ~10 |
| **合计** | | **~18** |

所有调用方需同步适配，否则导入时报 `TypeError`。**实施建议：阶段十二A 中一并修改所有调用方，不要分批。**

### 0.7 SimulationEnvBuilder pity_cfg_dict 构建逻辑需完全重写（AUDIT-BREAK-5）

**风险：** `SimulationEnvBuilder.from_config_store()`（`batch_simulator.py` 行526）的行606-614 构造 `pity_cfg_dict` 时访问了已不存在的字段：
- `pd.params` → 不存在（分裂为多个独立字段）
- `pd.target_distribution` → 不存在（`scope` + `target_featured` 替代）
- `pd.reset_condition` → 不存在（`target_featured` 推导）
- `pd.pools` → 类型从 `str` 变为 `tuple[str, ...]`

`pity_cfg_dict` 的构建逻辑需要完全重写以适配新 `PityDef`。**注意：此逻辑的消费方（如 `_build_pity_engine_from_gui()` 从 `pity_cfg_dict` 读取配置）也需要同步适配。**

### 0.8 GachaService run_simulation_compact() pity_triggered 检测链双重断裂（ISSUE-035）

**风险：** `GachaService.run_simulation_compact()` 行196-207 的 `pity_triggered` 确认检测链有两处断裂：

1. **行201 `_pity_engine.behaviors.get(pname)`：** P55 后 `PityEngine` 构造函数不再接收 `behaviors` dict 参数，`behaviors` 公开属性已被移除——此行抛出 `AttributeError`。
2. **行205 `behavior.is_active(cv)`：** 旧 `SoftPityBehavior` 覆写 `is_active()` 返回 `cv >= start_at`，P55 新 `CounterBasedBehavior` 不覆写此方法，回退到 `PityBehavior` 基类实现 `return False`——始终返回 `False`。

两处叠加导致 `pity_triggered` 总是 `False`，下游统计（`pity_triggers` 计数、`pool_counter_max` 计算）全部偏差。

此外行189-194 的 `pity_triggered` 初步检测（比较概率变化）在本上下文不受 P55 直接影响——`original_probs` 和 `probabilities` 的 key 均为卡牌 ID，比较逻辑可用；但 §0.3 AUDIT-BREAK-8 修复将 `probabilities` 改为 rarity-keyed，届时此比较也会断裂——需同步替换为 rarity-keyed 比较。

行209-214 的 `pool_counter_max` 计算直接读取 `pity_state.get(pname, 'counter', 0)`——`PityState.get()` 接口不变，但应迁移到 `PityEngine.get_counter()` 以保持单一访问入口。

**修复方案：**
```python
# gacha_service.py:196-207 替换为：
if _pity_engine and pity_triggered:
    spec = _pity_engine.get_spec(pool.id)
    if spec:
        triggered_names = []
        for pname in spec.pity_names:
            if _pity_engine.is_active(pname):         # ← P55 新增 Flag-based 查询
                triggered_names.append(pname)
        triggered_pity_name = ','.join(triggered_names) if triggered_names else None
# 行209-214 pool_counter_max 迁移：
#   旧: pity_state.get(pname, 'counter', 0)
#   新: _pity_engine.get_counter(pname)    # ← P60 已交付
```

**波及：** 阶段十二A `gacha_service.py` 适配项中补充行196-214 的检测链替换。

### 0.9 worst_impact.py _get_pity_cost() 访问 p.params 在 P55 后断裂——波及清单遗漏（ISSUE-036）

**风险：** `_get_pity_cost()` 方法（`worst_impact.py` 行340-354）通过 `p.params.get('end', '90')` 读取旧 `PityDef.params` dict 中的 `end` 值来计算保底总消耗（`end * cost`），再通过 `_compute_pity_coverage()` 供给 `pity_coverage` 结果字段（`worst_impact_panel.py` 中的 `PityCoverageGauge` 控件展示）。P55 后 `PityDef.params` dict 被删除（扁平化为 `deltas`/`threshold`/`soft_start`/`soft_end` 等独立字段），`p.params` 访问将抛出 `AttributeError`，阻断整个 `prepare_simulation_config()` 流程。

此调用路径未被计划 §4.2 波及表或 AUDIT-BREAK-3/4/5 列表覆盖——后者仅覆盖 `_build_pity_engine()` 和 `_get_initial_pity_state()`，遗漏了 `_get_pity_cost()`。此外该方法通过 `p = self.store.pity.pities[0]` 仅读取第一条 `PityDef`——在多保底场景下语义不准确但属已有问题，P55 修复时可一并改为遍历所有 `PityDef` 并取最大 end 值。

**修复方案：** 将 `p.params.get('end', '90')` 替换为从 P55 新字段推导 end 值：
```python
def _get_pity_end(self, pdef: PityDef) -> int:
    """从 P55 新字段推导保底所需的抽数上限。"""
    if pdef.btype == 'hard' and pdef.threshold:
        return pdef.threshold
    if pdef.deltas is not None:
        return sum(n for n, _ in pdef.deltas)  # deltas 各段抽数之和
    if pdef.soft_end is not None:
        return pdef.soft_end
    return 90  # 兜底默认值
```

**波及：** 阶段十二A `worst_impact.py` 适配项中补充 `_get_pity_cost()` 路径（行340-354）+ `_compute_pity_coverage()` 调用点（行325-327）。同时在波及表 worst_impact.py 行中补充此条目。

<!-- REVIEW-R1-FIX: ISSUE-036 -->
<!-- REVIEW-R1-FIX: ISSUE-035 -->
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-8 -->
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-2 -->
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-1 -->

<!-- REVIEW-R1-FIX: ISSUE-051 -->
### 0.10 CounterBasedBehavior.after_draw() 需插入 _on_reset() 钩子——修改 P60 交付代码（AUDIT-BREAK-30）

**风险：** 计划 §3.2（ISSUE-020）给出了 `_on_reset()` 钩子的伪代码（行1212-1240），要求在 `CounterBasedBehavior.after_draw()` 的 `_should_reset()` 检查之后插入 `if self._on_reset(ctx): return`。但当前 P60 已交付的 `after_draw()`（`pity.py:269-278`）不包含此钩子——P55 需要修改 P60 代码。计划将此变更嵌套在 `SoftStepBehavior`/`HardPityBehavior` 的行为描述中，未在 §0（实施前置条件）或任何变更清单中单独标注为「修改 P60 交付的 `CounterBasedBehavior.after_draw()` 方法体」。实施者可能误以为此变更属于「P60 已提供的基础设施」而跳过。

**修复方案（强制）：** 在 `CounterBasedBehavior.after_draw()` 的 `_should_reset(ctx)` 检查之后、默认重置流程之前插入钩子调用：

```python
# P60 当前代码（pity.py:269-278）——缺少 _on_reset() 钩子
def after_draw(self, ctx: 'PityContext') -> None:
    if not self._active.is_set():
        return
    if not self._should_reset(ctx):
        return
    if self._lifecycle.max_triggers and self._triggers.value() >= self._lifecycle.max_triggers:
        self._active.clear()
        return
    self._counter().reset()
    self._triggers.incr()

# P55 修改后（插入 _on_reset() 钩子）：
def after_draw(self, ctx: 'PityContext') -> None:
    if not self._active.is_set():
        return
    if not self._should_reset(ctx):
        return
    # ── P55 新增：_on_reset() 钩子（3 行） ──
    if self._on_reset(ctx):
        return  # 子类已完全处理——跳过默认 reset+incr 流程
    # ── 默认重置流程（P60 原有） ──
    if self._lifecycle.max_triggers and self._triggers.value() >= self._lifecycle.max_triggers:
        self._active.clear()
        return
    self._counter().reset()
    self._triggers.incr()
```

<!-- REVIEW-R2-FIX: ISSUE-057 -->
**关键约束（与 P60 的边界）：** 此为 P55 对 P60 已交付方法体的两处修改之一：

1. **`after_draw()` 插入 `_on_reset()` 钩子**（如上方伪代码所示）。
2. **`CounterBasedBehavior.__init__` 新增 `btype` 参数**——用于在基类层面推导 `is_soft`/`is_event_driven`/`is_hard` 分类属性（详见 §3.1.1 SoftStepBehavior 构造器注释行1117-1120 及 §3.2 `_resolve_order()` 分类属性定义）。子类（`SoftStepBehavior`/`HardPityBehavior`/等）通过 `super().__init__(...)` 将 `btype` 传入基类，基类在构造时完成分类属性赋值。

所有其他 P55 变更均为新增类/方法/字段，不修改 P60 代码。此变更必须在阶段五（`SoftStepBehavior` 实现）之前完成——`SoftStepBehavior._on_reset()`（覆写钩子）和 `HardPityBehavior._on_reset()` 依赖此钩子在父类中被调用。

**波及：** 实施时变更清单中将此标记为「修改 P60 交付代码」而非「新增行为」。P60 等价性测试（`test_p60_equivalence.py`）需同步验证 `_on_reset()` 钩子插入后无回归。
<!-- /REVIEW-R1-FIX: ISSUE-051 -->

<!-- REVIEW-R1-FIX: ISSUE-050 -->
### 0.11 retreat_config.py 完全遗漏于波及表——PityDef 构造 + PityConfig.counter_init 双断裂（AUDIT-BREAK-31）

**风险：** `retreat_config.py` 第67-74行构造旧格式 `PityDef`（5 字段：`name`/`btype`/`params`/`target_distribution`/`reset_condition`/`pools`），第75行将 `counter_init=dict(pity_counter_init)` 传入 `PityConfig()` 构造函数。P55 后：

1. **PityDef 5 字段全部移除** → 17 个新字段（`scope`/`target_featured`/`deltas`/`threshold`/`counter_init` 等）——旧字段访问全部 `AttributeError`。
2. **PityConfig.counter_init 字段被删除** → `TypeError: unexpected keyword argument 'counter_init'`。

该文件在计划 §4.2 波及表、§0.4 AUDIT-BREAK-3、§0.5 AUDIT-BREAK-4 中均未被列出。全文中搜索 `retreat_config` 返回零条结果。这是波及面分析的结构性遗漏——`retreat_config.py` 是 `RetreatSearchEngine` 的配置裁剪器，阻断整个撤退搜索流程。

**受影响的代码（`retreat_config.py:65-76`，当前）：**
```python
truncated.pity = PityConfig(
    enabled=original_store.pity.enabled,
    pities=[PityDef(
        name=pd.name,
        btype=pd.btype,
        params=dict(pd.params),
        target_distribution=dict(pd.target_distribution),
        reset_condition=pd.reset_condition,
        pools=pd.pools,
    ) for pd in original_store.pity.pities],
    counter_init=dict(pity_counter_init),
)
```

**修复方案：**

**(1) PityDef 构造：** 遍历 `original_store.pity.pities` 后直接引用 `PityDef` 对象（PityDef 本身是 dataclass，可直接 shallow-copy 或原样传递——两者引用同一不可变字段）：
```python
# P55 修复后：
pities=[PityDef(
    name=pd.name,
    btype=pd.btype,
    scope=pd.scope,
    target_featured=pd.target_featured,
    deltas=pd.deltas,
    threshold=pd.threshold,
    counter_init=pd.counter_init,
    guaranteed_init=pd.guaranteed_init,
    fate_points_init=pd.fate_points_init,
    soft_start=pd.soft_start,
    soft_end=pd.soft_end,
    soft_increment=pd.soft_increment,
    soft_deltas=pd.soft_deltas,
    cr_counter_threshold=pd.cr_counter_threshold,
    cr_base_rate=pd.cr_base_rate,
    cr_state_probs=pd.cr_state_probs,
    fate_threshold=pd.fate_threshold,
    switch_allowed=pd.switch_allowed,
    switch_resets_progress=pd.switch_resets_progress,
    pools=pd.pools,
    max_triggers=pd.max_triggers,
    deactivate_on_early_hit=pd.deactivate_on_early_hit,
    depends_on=pd.depends_on,
) for pd in original_store.pity.pities],
```

**(2) PityConfig 构造：** 移除 `counter_init` 参数——该字段已从 `PityConfig` 移至每个 `PityDef.counter_init`：
```python
truncated.pity = PityConfig(
    enabled=original_store.pity.enabled,
    pities=[...],  # 上方新格式
    # counter_init 已移除——值已含在每个 PityDef.counter_init 中
)
```

若需要 per-behavior 的初始计数器值（如 `pity_counter_init` dict 中的自定义值），应在返回前遍历 `pities` 逐条写入 `PityDef.counter_init`：
```python
for pdef in truncated.pity.pities:
    custom_init = pity_counter_init.get(pdef.name)
    if custom_init is not None:
        pdef.counter_init = custom_init
```

**波及：** 波及表 §4.2 补充 `retreat_config.py` 条目。阶段十二B 适配清单中补充此文件。
<!-- /REVIEW-R1-FIX: ISSUE-050 -->

## 一、问题

### 1.1 当前局限

当前保底体系（`core/pity.py`）存在五个结构性问题：

| # | 问题 | 影响 |
|---|------|------|
| 1 | `type = "soft"` 硬编码累加公式（`new = target + progress × other` 比例重分配），不支持替换为其他累加方式 | 无法表达「每抽固定＋6%」等增量型保底 |
| 2 | `progress` 计算和 `_apply_targeted()` 绑死在 `SoftPityBehavior.apply()` 中——方式与类一对一 | 新增累加方式必须写新类，且与旧公式耦合在同一 type 下 |
| 3 | `PityEngine.after_draw()` 硬编码 `is_ssr` 判定，生命周期逻辑外泄在引擎层 | 每加一个新保底类型就要改引擎；无法表达 SR/R 保底 |
| 4 | `PityState` 预设字段类型（仅 `counters: Dict[str, int]`），每加一种状态维度就要改数据结构 | 无法存储布尔标志、触发次数、per-banner 隔离计数——新增保底类型需要同时改 `PityState` 定义 |
| 5 | 保底行为的生命周期被 `PityEngine` 和 `PityBehavior` 割裂——`apply()` 在 behavior，`after_draw()` 在引擎 | 新增保底类型的改动散落两处，违背开闭原则 |

### 1.2 讨论结论（本次会话）

- **两个正交维度**：累加方式（怎么加）× 作用范围（加给谁）→ `type` × `scope`
- **十种 TOML type**：四种 counter 驱动（`soft_interval` / `soft_additive` / `soft_step` / `hard`）+ 六种事件驱动（`rotating` / `rotating_soft` / `rotating_cr` / `rotating_cr_soft` / `targeted` / `targeted_soft`）。`soft_interval` 和 `soft_additive` 是语法糖——TOML 解析时展开为 `deltas`，统一由 `SoftStepBehavior` 执行。`_soft` 后缀 = 自带软保底，`_cr` 后缀 = 带捕获明光（CR = Capturing Radiance，英文社区通用缩写）
- **统一 `scope` 参数**：作用于稀有度级别（`ssr` / `sr` / `r` 等，必须已在 `[rarities]` 注册），`target_featured` 布尔字段同时控制两个维度——概率调整范围（仅 featured 子集 / 全体）和计数器重置条件（仅 featured 出货 / 任意出货）。`_should_reset(ctx)` = 命中 scope 稀有度 且（`target_featured` → `is_featured` 为真；否则 → 直接通过）
- **行为独立化**：每个 `PityBehavior` 自管完整生命周期（概率调整 + 状态更新），引擎退化为纯调度器，对齐策略系统的 Context 注入模式
- **状态抽象化**：`PityState` 不预设字段类型——每个 behavior 以自身 `name` 为 namespace 存取任意类型数据
- **DrawInfo 拆分**：`PityContext` 拆为两层——`DrawInfo`（不可变静态事实，`frozen=True`）+ 可变载体（`current` / `state`），类型系统强制执行可变/不可变边界
- **Registry 模式**：`BEHAVIOR_REGISTRY` 一张表消除 if-else——含每个 type 的参数元数据（对齐策略 `STRATEGY_REGISTRY.params`），新增保底类型 = 写类 + 注册一行 + 写元数据 + 配 TOML
- **参数元数据驱动**：对齐策略系统的 `STRATEGY_REGISTRY.params` 模式——`BEHAVIOR_REGISTRY` 中声明每个 type 的参数元数据（`type` / `display_name` / `default` / `min` / `max`），config panel 据此渲染 UI 控件 + 就地校验。不需 params dataclass——TOML 解析后类型已是正确的（`int`/`float`/`str`），无类型转换需求
- **Counter / Flag 微抽象**：`Counter`（遥控器模式）+ `Flag`（布尔标志遥控器），消除字符串 key 散落
- **CounterBasedBehavior**：计数器驱动型保底的可选基类——统一计数器生命周期、子类只实现 `_compute_probabilities(ctx, counter)`
- **LifecycleConfig**：跨 type 共享的生命周期参数 dataclass——`max_triggers`（触发上限）+ P56 扩展 `deactivate_on_early_hit` / `depends_on`
- **执行顺序自动推导**：不再使用 `priority` 数字——基于 type 分类（概率增加/强制出卡）+ scope 层级（稀有度高低 + 重叠关系）自动推导执行顺序；校验分级（ConfigError / warn / 通过）
- **稀有度层级保护**：低稀有度保底绝不降低高稀有度概率——`scope=sr` 只从 R 取概率，不动 SSR
- **七大支柱**：`type × scope 正交` + `行为独立化` + `状态抽象化` + `DrawInfo 拆分` + `Registry` + `CounterBasedBehavior` + `执行顺序自动推导` → 配置者无需手写排序数字
- **YAGNI 移除**：`increment_step`（计数器加速）· `reset_min_counter`（前 N 抽不重置）· `persistence`（计数器跨池继承——由 `pools` 配置推导，无需独立参数）——调研 12 款游戏无实际用例
- **保留参数**：`pools`（适用池子）· `counter_init`（初始水位，模拟开始前已垫抽数）——不动链路，`batch_simulator` 直接写 `PityState`。**`reset` 已移除**——计数器重置条件由 `target_featured` 自动推导（`true` → 仅 featured 出货重置；`false` → 任意 scope 出货重置），`reset` 的三个枚举值中 `any_ssr` 与 `scope` 语义重叠，`featured_ssr` 与 `target_featured` 语义重叠，`never` 属于里程碑系统职责
- **rotating（轮换保底/大小保底）**：事件驱动——`RotatingBehavior`，纯净轮换，零参数。小保底 featured 占比由基础概率分布决定（非硬编码 50%）
- **rotating_soft（轮换+软保底）**：`RotatingSoftBehavior(RotatingBehavior)` 子类——~25 行增量
- **rotating_cr（轮换+捕获明光）**：`RotatingCRBehavior(RotatingBehavior)` 子类——CR 状态机。**不与 rotating 并存。**
- **rotating_cr_soft（轮换+CR+软保底）**：`RotatingCRSoftBehavior(RotatingCRBehavior)` 子类——~25 行增量
- **targeted（定向保底/定轨）**：事件驱动——`TargetedBehavior`，selected_card + 命定值 + 切换规则
- **targeted_soft（定轨+软保底）**：`TargetedSoftBehavior(TargetedBehavior)` 子类——~25 行增量

## 二、目标

### 2.1 核心交付

| # | 交付 | 说明 |
|---|------|------|
| 1 | **行为独立化** | `PityBehavior` 自管完整生命周期；`PityEngine` 退化为调度器 |
| 2 | **`PityContext` + `DrawInfo`** | `DrawInfo`（`frozen=True`，静态事实）+ `PityContext`（可变载体：`current` / `state`），类型系统强制执行可变/不可变边界 |
| 3 | **`BEHAVIOR_REGISTRY`** | 消除 if-else——含 type→类 + 参数元数据（对齐 `STRATEGY_REGISTRY`）；新增保底类型 = 写类 + 注册一段元数据 |
| 4 | **参数元数据驱动** | `BEHAVIOR_REGISTRY` 中含各 type 的参数元数据（`type` / `display_name` / `default`），对齐策略系统——config panel 据此渲染 UI + 校验，不引入 params dataclass |
| 5 | **`Counter` / `Flag` 微抽象** | 遥控器模式——`Counter(state, name)` 封装 `incr()`/`value()`/`reset()`/`reached()`；`Flag` 同理 |
| 6 | **`CounterBasedBehavior`** | 计数器驱动型保底可选基类——统一计数器生命周期，子类只实现 `_compute_probabilities()` |
| 7 | `type = "soft_interval"` | 语法糖——TOML 解析时展开为 deltas，统一由 `SoftStepBehavior` 执行 |
| 8 | `type = "soft_additive"` | 语法糖——同上。每抽固定百分点累加，`scope` 决定加给谁 |
| 9 | `type = "soft_step"` | 底层——RLE 压缩的逐抽增量数列 `deltas = [[n, inc], ...]`，任意形状 |
| 10 | `SoftStepBehavior` | 唯一的 counter 驱动软保底类——替代 `SoftIntervalBehavior` + `SoftAdditiveBehavior` |
| 11 | `scope` 参数 | 稀有度级别：`ssr` / `sr` / `r`（必须在 `[rarities]` 注册）。`featured` 由 `target_featured` 字段承担，不混入 scope |
| 12 | **`PityState` 抽象化** | 三层嵌套 namespace：`{behavior_name: {key: value}}`；`get()`/`set()`/`incr()` 接口 |
| 13 | **`LifecycleConfig`** | 跨 type 共享的生命周期参数 dataclass：`max_triggers`（C3）+ P56 扩展 `deactivate_on_early_hit` / `depends_on` |
| 14 | **执行顺序自动推导** | 基于 type 分类（概率增加/强制出卡）+ scope 层级关系自动排序；校验分级（ConfigError / warn / 通过） |

### 2.2 非目标

- `rotating` 事件驱动行为的完整实现（P56）——P55 仅确保基础设施（`PityState` / `Flag` / 跨 behavior 读取）支持
- `scope` 扩展为自定义卡组（`card_group` 定义）——当前稀有度级别足够
- Box 制 / 阶梯池 / 天井 / 不重复保底 —— 不属于保底引擎职责范围
- **捕获明光 —— 已决策（2026-06-20）：** 独立 `type="rotating_cr"`，`RotatingBehavior` 的子类。`cr_state_probs` 为数组预留。详见 P56 §3.3。

## 三、方案

> **原 §3.1-3.9（平台层——PityState / DrawInfo / PityContext / Counter / Flag / CounterBasedBehavior / BEHAVIOR_REGISTRY / 类结构全景 / PityEngine 调度器）已提取至 [P60](../../../02-待办/P60%20基础平台——依赖消除与下游并行化.md) 块 2-4。** 下文直接从执行顺序开始——此为 P55 保留的专属内容（执行顺序推导依赖具体 behavior 的 type 分类，属于 P55 而非平台层）。

### 3.1 执行顺序——矩阵规则自动推导（来源：原 §3.10）

**设计决策：不再使用 `priority` 数字字段。** 执行顺序由 behavior 的 type 分类 + scope 层级关系自动推导。配置者无需手写排序数字。

#### 3.1.1 矩阵分析

两个 behavior 的交互由两个维度决定：**驱动方式**（counter vs 事件）× **scope 关系**（无关 / 重叠）。

| A \ B | 概率增加（soft_*、rotating_soft） | 重分配（rotating/targeted/rotating_cr） | 强制出卡（hard） |
|-------|-------------------|-------------------------|-----------------|
| **soft_* / rotating_soft** | 叠加——后执行者继续调整 | soft 先——先增加总出率，再分配内部比例 | soft 先——hard 设 100% 覆盖 soft |
| **rotating/targeted/rotating_cr** | rotating 后（同上） | 同 scope → 无意义，校验时 warn | rotating 先——分配完再 hard 覆盖 |
| **hard** | hard 后（同上） | hard 后（同上） | 同 scope → **ConfigError** |

**排序规则：soft / rotating_soft → rotating/targeted/rotating_cr → hard。** 先增加 scope 总出率，再分配内部比例，最后强制覆盖。每个 type 内部按稀有度降序。`rotating` / `targeted` / `rotating_cr` 为同一优先级，其中同 scope 两个以上 → ConfigError。

| scope 关系 | 处理 |
|-----------|------|
| **无关**（如 `ssr` ∪ `sr`，互不重叠） | 低稀有度保底只从 ≤ 自身稀有度取概率——不会碰高稀有度。顺序无关 |
| **重叠**（同 scope） | 按 type 规则（见上表） |

<!-- REVIEW-FIX-PREV: ISSUE-017 -->
#### 3.1.2 自动推导规则

`_resolve_order()` 和 `_validate_behaviors()` 是 **`PityEngine` 的私有方法**（非模块级函数）。它们需要访问 `self._rarity_rank` 来解析稀有度层级关系，且属于引擎专属逻辑，不应暴露为模块级函数。

引擎在构造时自动排序，不依赖配置者手写数字：

**P55 PityEngine 构造函数（完整签名）：**

```python
class PityEngine:
    def __init__(self, pool_specs: Dict[str, PoolPitySpec],
                 pity_defs: List[PityDef],
                 state: PityState,
                 rarity_rank: Dict[str, int]):
        self._pool_specs = pool_specs
        self._rarity_rank = {k.lower(): v for k, v in rarity_rank.items()}
        self._state = state

        # 工厂创建 behavior 实例（零 if-else 分发）
        self._behavior_list = [create_behavior(pdef.name, state, pdef)
                               for pdef in pity_defs]

        # 自动推导执行顺序 + 校验
        self._behavior_list = self._resolve_order(self._behavior_list)
        self._validate_behaviors(self._behavior_list)

        # 构建依赖激活图（P56 扩展，P55 暂为空）
        self._activation_graph = self._build_activation_graph(self._behavior_list)
```

**签名对比（旧 → 新）——所有调用方需同步适配：**

| 参数 | 旧签名 | 新签名 | 说明 |
|------|--------|--------|------|
| `pool_specs` | ✅ | ✅ | 不变 |
| `pity_defs` | `Dict[str, PityDefParsed]` | `List[PityDef]` | 扁平 PityDef 替代旧格式 |
| `behaviors` | `Dict[str, PityBehavior]` | **移除** | 工厂内部创建，调用方不传 |
| `rarity_rank` | ✅ | ✅ | 不变 |
| `state` | 不存在 | **新增** `PityState` | 引擎持有状态引用供 behavior 共享 |

```python
class PityEngine:
    # ── 在 __init__ 末尾调用 ──

    def _resolve_order(self, behaviors: List[PityBehavior]) -> List[PityBehavior]:
        """基于 type 分类 + scope 层级自动推导执行顺序。"""
        return sorted(behaviors, key=lambda bh: (
            self._rarity_rank.get(bh.scope, 99),  # 高稀有度排前（rank 越小越稀有）；未注册 scope → 排末尾
            self._type_order(bh),               # soft(0) < 事件驱动(1) < hard(2)
        ))

    @staticmethod
    def _type_order(bh: PityBehavior) -> int:
        if bh.is_soft:            return 0
        if bh.is_event_driven:    return 1   # rotating / rotating_soft / rotating_cr / targeted
        if bh.is_hard:            return 2
        return 99  # 未知类型排末尾
```

**设计要点：**
- `self._rarity_rank` 是 `PityEngine` 构造器参数 `rarity_rank: Dict[str, int]` 的实例副本（见 §3.2），存储稀有度名 → 层级的映射（0=最高稀有度）。
- `_type_order()` 是 `@staticmethod`——不依赖实例状态，仅根据 behavior 的 `is_soft`/`is_event_driven`/`is_hard` 属性分类。
- 未在 `rarity_rank` 中注册的 scope 返回 rank 99（排末尾），避免 KeyError 导致构造崩溃——但解析层的 scope 注册校验（`_build_pity_def()` §3.3.1）应在进入引擎前就拦截未注册 scope。

<!-- REVIEW-R2-FIX: ISSUE-058 -->
#### 3.1.2.1 分类属性定义——CounterBasedBehavior 构造时初始化

`_resolve_order()` 和 `_validate_behaviors()` 依赖 behavior 实例上的以下公开属性做排序和校验。这些属性在 `CounterBasedBehavior.__init__()` 中通过 `btype` 参数一次性初始化，子类无需覆写：

| 属性 | 类型 | 来源 | 说明 |
|------|------|------|------|
| `scope` | `str` | 构造器参数 `scope`（从 `PityDef.scope` 传入） | 稀有度作用域，如 `'ssr'`/`'sr'`/`'r'`——直接赋值 `self.scope = scope` |
| `is_soft` | `bool` | `btype in SOFT_TYPES` | 是否为 counter 驱动软保底 |
| `is_hard` | `bool` | `btype == 'hard'` | 是否为硬保底 |
| `is_event_driven` | `bool` | `not is_soft and not is_hard` | 是否为事件驱动型（rotating/rotating_soft/rotating_cr/targeted 等） |
| `type` | `str` | `btype`（直接赋值 `self.type = btype`） | 保底类型字符串——校验时用于比较同 type 软保底冲突 |

```python
class CounterBasedBehavior(PityBehavior, ABC):
    # P55 在 __init__ 中通过 btype 参数计算并赋值所有分类属性
    def __init__(self, name: str, state: 'PityState', scope: str,
                 btype: str,  # ← P55 新增参数（见 §0.10 ISSUE-057）
                 target_featured: bool = False,
                 lifecycle: 'LifecycleConfig' = None):
        self._name = name
        self._state = state
        # ── P55 分类属性（公开，_resolve_order/_validate_behaviors 使用） ──
        self.scope = scope
        self.is_soft = btype in SOFT_TYPES
        self.is_hard = (btype == 'hard')
        self.is_event_driven = (not self.is_soft and not self.is_hard)
        self.type = btype
        # ── P60 原有初始化（_rebind_state/Counter/Flag/lifecycle 等） ──
        ...
```

**设计约束：**
- `scope` 必须为公开属性（非私有 `_scope`），因为 `_resolve_order()` 中 `bh.scope` 和 `_scope_overlap(a.scope, b.scope)` 均通过公开属性访问。
- `is_soft`/`is_event_driven`/`is_hard` 三者互斥——恰好一个为 `True`（由 `btype` 唯一决定）。
- 子类（`SoftStepBehavior`/`HardPityBehavior` 等）通过 `super().__init__(..., btype=...)` 传入各自类型标识，无需覆写这些属性。
<!-- /REVIEW-R2-FIX: ISSUE-058 -->

<!-- REVIEW-FIX-PREV: ISSUE-026 -->
**_behaviors_for_pool() 必须按排序后顺序过滤（关键约束）：** `_resolve_order()` 对 `_behavior_list` 排序后，`_behaviors_for_pool(pool_id)` 必须遍历 `self._behavior_list`（已排序）并过滤出 `spec.pity_names` 中的 behavior——而非遍历 `spec.pity_names` 按原始插入顺序迭代。否则排序结果在 per-pool 调度中被静默绕过。

```python
def _behaviors_for_pool(self, pool_id: str):
    """返回当前池关联的 behavior 实例列表——按 _behavior_list 排序顺序。"""
    spec = self.pool_specs.get(pool_id)
    if spec is None:
        return []
    names = set(spec.pity_names)
    # 遍历排序后的 _behavior_list，保持 _resolve_order() 的排序结果
    return [(bh.name, bh) for bh in self._behavior_list if bh.name in names]
```

**设计理由：** `spec.pity_names` 的顺序由配置解析时 `PoolPitySpec` 构造时决定（TOML 中 `[[pity]]` 的出现顺序），不反映稀有度层级和执行优先级。若 `_behaviors_for_pool()` 按 `spec.pity_names` 顺序迭代，则例如 `sr_hard` 可能先于 `ssr_soft` 执行——违反「高稀有度先执行」原则，且 `sr_hard` 先执行时 SSR 概率尚未被 `ssr_soft` 提升，结果不同。
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-11 -->
<!-- AUDIT-BREAK-11 确认：此修改本身是纯简化——将遍历对象从 spec.pity_names 改为 _behavior_list。
     若 _resolve_order() 排序逻辑有误（rarity_rank 为空 → 所有 rank=99 → 排序退化为插入序），
     _behaviors_for_pool() 返回顺序与原始插入序相同——行为无退化（等价于旧行为）。
     但若 rarity_rank 非空而排序结果错误，则返回顺序仅影响概率调整管道的叠加效果，
     不会导致 TypeError 或空值断裂。低风险。 -->
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-11 -->
<!-- /REVIEW-FIX-PREV: ISSUE-026 --><!-- /REVIEW-FIX-PREV: ISSUE-017 -->

**举例：**

```
输入: [sr_hard(scope=sr), ssr_soft(scope=ssr)]

解析:
  ssr_soft  稀有度=高, type=soft → 排序靠前（先执行）
  sr_hard   稀有度=低, type=hard → 排序靠后（后执行）

执行:
  Step 1: ssr_soft: SSR 从 1%→10%, SR+R 等比缩小
  Step 2: sr_hard:  R→0, SR 涨到 90%, SSR 保持 10%  ← 不动 SSR
```

<!-- REVIEW-FIX-PREV: ISSUE-017 -->
<!-- REVIEW-FIX-PREV: ISSUE-018 -->
#### 3.1.3 校验分级

`_validate_behaviors()` 同样是 `PityEngine` 的私有方法，通过 `self._rarity_rank` 判断 scope 重叠关系。

```python
class PityEngine:
    # ── 在 __init__ 末尾 _resolve_order() 之后调用 ──

    def _validate_behaviors(self, behaviors: List[PityBehavior]) -> None:
        <!-- REVIEW-R1-FIX: ISSUE-037 -->
        # ── name 重名校验（PityEngine 层第二道防线） ──
        # TOML 解析层（_build_pity）已做第一道重名拦截，
        # 此处防止编程接口直接构造 PityDef list 时绕过 TOML 层。
        seen = set()
        for bh in behaviors:
            if bh.name in seen:
                raise ConfigError(
                    f"PityBehavior name '{bh.name}' 重复——"
                    f"每个 behavior 的 name 必须全局唯一以隔离 PityState namespace。"
                )
            seen.add(bh.name)
        <!-- /REVIEW-R1-FIX: ISSUE-037 -->

        for a, b in itertools.combinations(behaviors, 2):
            if not self._scope_overlap(a.scope, b.scope):
                continue
            if a.is_hard and b.is_hard:
                raise ConfigError(
                    f"同 scope '{a.scope}' 存在两个硬保底 '{a.name}' 和 '{b.name}'——"
                    f"后者覆盖前者，无意义。请合并为一个 hard 或使用不同 scope。"
                )
            if a.is_event_driven and b.is_event_driven:
                raise ConfigError(
                    f"同 scope '{a.scope}' 存在两个事件驱动型保底 '{a.name}'({a.type}) "
                    f"和 '{b.name}'({b.type})——后者覆盖前者。请合并或使用不同 scope。"
                )
            if a.is_soft and b.is_soft and a.type == b.type:
                raise ConfigError(
                    f"同 scope '{a.scope}' 存在两个同 type 软保底 '{a.name}' 和 '{b.name}'——"
                    f"管道叠加导致后者覆盖前者。"
                )
            if a.is_soft and b.is_soft and a.type != b.type:
                warnings.warn(
                    f"同 scope '{a.scope}' 存在两个不同 type 软保底 '{a.name}'({a.type}) "
                    f"和 '{b.name}'({b.type})——允许但请确认非误配置。"
                )

    def _scope_overlap(self, scope_a: str, scope_b: str) -> bool:
        """判断两个 scope 是否重叠（共享概率池，需要校验交互规则）。

        重叠判定规则：
          1. scope 相同 → 重叠（同一稀有度级别）
          2. scope 不同但处于 rarity_rank 中的同一层级（rank 值相等）→ 重叠
             例：UR 和 SSR 同为 rank 0 → 视为平级稀有度、可能共享概率池
          3. 否则 → 不重叠（如 ssr 与 sr 分属不同 rank）
        """
        if scope_a == scope_b:
            return True
        rank_a = self._rarity_rank.get(scope_a)
        rank_b = self._rarity_rank.get(scope_b)
        if rank_a is None or rank_b is None:
            return False  # 未注册 scope 不视为重叠——解析层已拦截
        return rank_a == rank_b
```<!-- /REVIEW-FIX-PREV: ISSUE-018 --><!-- /REVIEW-FIX-PREV: ISSUE-017 -->

| 场景 | 行为 |
|------|------|
| scope 无关 | 通过——自动排序，低稀有度不碰高稀有度 |
| scope 重叠 + 有 hard | 通过——自动排序（soft 前 hard 后） |
| 同 scope 两个 hard | **ConfigError**——无意义 |
| 同 scope 两个事件驱动型（rotating/rotating_soft/rotating_cr/targeted） | **ConfigError**——后者覆盖前者 |
| 同 scope 同 type 两个 soft | **ConfigError**——管道叠加导致后者覆盖前者 |
| 同 scope 不同 type 两个 soft | **warn**——允许但提醒可能非有意 |

### 3.2 PityContext 与 PityState——数据流与接口设计

**设计哲学：** 对齐策略系统——`PityEngine` 只负责调度，每个 `PityBehavior` 拿到 `PityContext` 后自己决定一切。

```
当前（割裂）：
  PityEngine.before_draw() → increment → get_probabilities() → behavior.apply()
  PityEngine.after_draw()  → [引擎层硬编码] 检查 rarity → reset

重构后（独立化）：
  PityEngine.before_draw() → 构建 PityContext → foreach behavior: behavior.before_draw(ctx)
  PityEngine.after_draw()  → 构建 PityContext → foreach behavior: behavior.after_draw(ctx)
```

#### PityContext 设计：DrawInfo 拆分

**设计哲学：** 将「不变的静态事实」与「管道中流转的可变状态」拆为两层，类型系统强制执行可变/不可变边界。

```
@dataclass(frozen=True)                    # ← frozen：不可变
class DrawInfo:
    """抽卡上下文中不变的部分——本次抽卡的静态事实。"""
    pool_id: str
    pool_instance_id: str                  # per-banner 计数器隔离（A2）
    reward_id: str
    reward_rarity: str                     # "ssr" | "sr" | "r"
    is_featured: bool
    scope_cards: Mapping[str, tuple[str, ...]]    # rarity → 具体卡牌 ID
    scope_slots: Mapping[str, tuple[str, ...]]    # rarity → 模板槽位 ID
    featured_slots: Mapping[str, tuple[str, ...]] # rarity → 标记 featured=true 的槽位 ID
    base_probabilities: Mapping[str, float]       # 槽位 ID → 基础概率
    rarity_rank: Mapping[str, int]                # rarity → 层级（0=最高），由 [rarities] 生成

@dataclass
class PityContext:
    """管道中流转的可变载体。"""
    draw: DrawInfo                         # 不可变——只读
    current: Dict[str, float]              # 当前管道概率——随 behavior 依次修改
    state: PityState                       # 状态引用——behavior 通过 set/incr 写入
```

**key 语义说明：**
- `scope_cards["ssr"]` = `("limited_ssr_1", "standard_ssr_1", ...)`——具体卡牌，用于判断 reward 属于哪个稀有度
- `scope_slots["ssr"]` = `("ssr", "ssr_alt")`——模板槽位，用于从 `base_probabilities` 中累加概率
- `featured_slots["ssr"]` = `("ssr",)`——其中标记了 `featured=true` 的槽位，用于 rotating 重分配 featured/非featured 内部比例
- `base_probabilities["ssr"]` = `0.2`——模板槽位的基础概率
- `rarity_rank["ssr"]` = `0`——由 `[rarities]` 生成，用于稀有度层级保护（低 rank 不从高 rank 取概率）

<!-- REVIEW-FIX-PREV: ISSUE-001 -->
<!-- REVIEW-FIX-PREV: ISSUE-002 -->
<!-- REVIEW-FIX-PREV: ISSUE-004 -->
<!-- REVIEW-FIX-PREV: ISSUE-008 -->
#### 3.2.1 scope_slots / featured_slots / scope_cards 的填充来源

ISSUE-001 指出：若 `DrawInfo` 构造时 `scope_slots={}` 且 `featured_slots={}`，则 `SoftStepBehavior._compute_probabilities()` 和 `HardPityBehavior._compute_probabilities()` 首行检查空 dict 即返回 `ctx.current.copy()`，保底概率调整管道完全静默不工作。本节给出填充方案。

<!-- REVIEW-FIX-PREV: ISSUE-011 -->
**ISSUE-002 / ISSUE-004 / ISSUE-011 勘误（本轮审议）：** 上一轮伪代码中的 `_build_draw_info()` 引用了 3 个运行时类不存在的属性——`pool.distribution`（Pool 类仅有 `rewards: List[Tuple[Reward, float]]`，无 `distribution`）、`reward.rarity`（Reward 类无 `rarity` 属性——稀有度存储在 `reward.extra_info` dict 中且仅在 `worst_impact.py` 构造时携带）、`pool.instance_id`（Pool 类仅有 `id: str` 属性，无 `instance_id`）。

当前代码库实际类型：
- `Pool`（`pool.py:176-182`）：`id: str` + `rewards: List[Tuple[Reward, float]]`——**无 distribution 属性，无 instance_id 属性**
- `Reward`（`pool.py:134-138`）：`id: str` + `name: str` + `resources_gained: Dict` + `extra_info: Dict`——**无 rarity/is_featured 属性**
- `PoolDistEntry`：仅在配置层（`config_store.py`）存在，**不在运行时 Pool 对象上**
- `batch_simulator.py:555-558`：构造 `Reward` 时**不携带 extra_info**（无 rarity/featured 键）
- `worst_impact.py:385`：构造 `Reward` 时携带 `extra_info={'rarity': ..., 'featured': ...}`——**仅此一处携带**

**实施路径决策（ISSUE-004 / ISSUE-011 更新）：** 原有两个选项均基于错误假设（Pool 对象上有 PoolDistEntry 列表）。修正后的两个选项——

| 选项 | 方案 | 优点 | 缺点 |
|------|------|------|------|
| A | `_build_draw_info()` 接收 `PoolPitySpec` 预计算数据（计划已列为首选路径），从 `spec.scope_slots` / `featured_slots` / `scope_cards` 读取，完全跳过遍历 pool | O(1)、无运行时类型依赖、不关心 Reward 构造细节 | 需确保 `SimulationEnvBuilder` 和 `_build_pity_engine_from_gui()` 正确预计算这些字段 |
| B | 遍历 `pool.rewards: List[Tuple[Reward, float]]`，从 `reward.id` 与 `spec.ssr_ids` / `featured_ids` 成员判定推导 `rarity` 和 `is_featured` | 不依赖预计算字段——兜底路径 | 需 `batch_simulator.py` 同步改造——构造 Reward 时携带 `extra_info`（含 rarity/featured），否则方案 B 不可靠 |

<!-- REVIEW-FIX-PREV: ISSUE-011 -->
**决策：选 A 为主路径（PoolPitySpec 预计算），方案 B 为可选兜底。** 理由：(1) 方案 A 完全规避运行时类型不匹配——`PoolPitySpec` 在构建期就已从 `PoolEntry.distribution: List[PoolDistEntry]` 预计算完成，`_build_draw_info()` 只做字段拷贝；(2) 方案 B 需要 `batch_simulator.py` 同步改造 Reward 构造逻辑（添加 extra_info），跨模块改动风险大且语义重复（预计算已覆盖）；(3) 若两个路径都实现，方案 A 优先、方案 B 仅在 `PoolPitySpec` 字段为空时兜底。

<!-- REVIEW-FIX-PREV: ISSUE-019 -->
<!-- REVIEW-FIX-PREV: ISSUE-025 -->
**修正后的 `_build_draw_info()`——方案 A 主路径（不依赖 Pool 对象）：**

`_build_draw_info()` 在两种上下文中被调用：(1) `before_draw()`——此时 reward 尚未产生，reward 参数为 `None`；(2) `after_draw()`——此时 reward 已确定，传入实际 Reward 对象。签名中 `reward` 参数类型为 `Optional[Reward]`。

```python
def _build_draw_info(self, pool_id: str, reward: Optional[Reward],
                     pool_spec: PoolPitySpec,
                     base_probabilities: Mapping[str, float]) -> DrawInfo:
    """从 PoolPitySpec 预计算数据 + 可选 Reward 对象 + 外部传入的 base_probabilities 构造 DrawInfo。

    两种调用上下文：
      - before_draw(): reward=None  ——奖励尚未产生，reward_rarity/is_featured/reward_id 使用占位值
      - after_draw():  reward=Reward ——奖励已确定，正常推导 reward_rarity/is_featured/reward_id

    关键设计决策（ISSUE-019）：base_probabilities 由 GachaService 在 before_draw()
    调用前计算完成并作为参数传入——PityEngine 不持有 Pool 引用、不遍历 pool.rewards。
    这样 before_draw/after_draw 签名无需改变，PityEngine 也无需持有 Pool 列表。

    pool_spec.scope_slots / featured_slots / scope_cards 已由
    SimulationEnvBuilder 在构建时从 PoolEntry.distribution 预计算。
    """
    # ── reward_rarity 推导（从 spec 成员判定——见 §3.2.1 _infer_rarity 扩展） ──
    # ISSUE-025：before_draw 上下文中 reward=None，使用空字符串占位
    if reward is not None:
        reward_rarity = self._infer_rarity(reward.id, pool_spec, self._rarity_rank)
        is_featured = reward.id in pool_spec.featured_ids
        reward_id = reward.id
    else:
        reward_rarity = ''       # before_draw：抽卡尚未发生，无稀有度
        is_featured = False      # before_draw：不可知
        reward_id = ''           # before_draw：无奖励 ID

    # ── 从 PoolPitySpec 预计算字段构造不可变映射 ──
    scope_slots   = pool_spec.scope_slots or {}
    featured_slots = pool_spec.featured_slots or {}
    scope_cards    = pool_spec.scope_cards or {}

    return DrawInfo(
        pool_id=pool_id,
        pool_instance_id=pool_id,          # Pool 仅有 id 属性——复用为 instance_id
        reward_id=reward_id,
        reward_rarity=reward_rarity,
        is_featured=is_featured,
        scope_cards=scope_cards,
        scope_slots=scope_slots,
        featured_slots=featured_slots,
        base_probabilities=MappingProxyType(base_probabilities),  # ← 外部传入，不遍历 pool.rewards
        rarity_rank=self._rarity_rank,
    )
```
<!-- /REVIEW-FIX-PREV: ISSUE-025 -->

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-9 -->
**GachaService 调用适配（ISSUE-019 波及 + AUDIT-BREAK-9 修正）：**

`GachaService.before_draw()` 的当前签名（P60 已定稿）：
```python
probabilities = self._pity_engine.before_draw(pool_id, pity_state, probabilities)
```

其中 `probabilities`（第 3 个参数，`Dict[str, float]`）是 GachaService 已计算好的 base_probabilities。P55 后引擎内部将其传入 `_build_draw_info(pool_id, reward, pool_spec, base_probabilities=probabilities)` 构造 `DrawInfo.base_probabilities`。**before_draw 外部签名不变。**

**AUDIT-BREAK-9 修正：`after_draw()` 签名需同步更新。** 当前 `GachaService` 行217：
```python
self._pity_engine.after_draw(pool.id, pity_state, reward.id)
# reward.id 是 str —— 但新签名需要 Reward 对象 + base_probabilities
```

计划 §3.2 声明「before_draw/after_draw 外部签名不变」——这是错误的。`after_draw()` 必须改为：
```python
self._pity_engine.after_draw(pool.id, pity_state, reward, probabilities)
# reward: Reward 对象（非 reward.id 字符串）——引擎需要 reward.extra_info 或 reward.id 推导稀有度
# probabilities: Dict[str, float] —— 与 before_draw 相同的 base_probabilities
```

**波及：** `batch_simulator.py` 和 `worst_impact.py` 中所有 `after_draw()` 调用点需同步更新——第3参数从 `str` 改为 `Reward` 对象，新增第4参数 `base_probabilities`。
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-9 -->
<!-- /REVIEW-FIX-PREV: ISSUE-019 -->

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-12 -->
**方案 B 兜底路径（仅在 `PoolPitySpec` 预计算字段为空时启用）：**

**AUDIT-BREAK-12 前置条件警告：** 方案 B 依赖 `Reward.extra_info` 含 `rarity`/`featured` 键。当前 `batch_simulator.py:555` 构造 `Reward` 时**不携带 `extra_info`**（仅 `worst_impact.py:385` 一处携带）。若方案 B 被启用（方案 A 预计算字段为空）且 Reward 无 extra_info → `rwd.extra_info.get('rarity', '')` 返回 `''` → `scope_slots`/`featured_slots`/`scope_cards` 全为空 → 保底静默不工作。**强制要求：若启用方案 B，`batch_simulator.py` 构造 Reward 时必须同步添加 `extra_info={'rarity': de.rarity, 'featured': de.featured}`。**
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-12 -->

```python
def _build_draw_info_fallback(self, pool, reward, pool_spec: PoolPitySpec) -> DrawInfo:
    """兜底路径——遍历 pool.rewards 实时推导 scope 分组。

    仅在 PoolPitySpec.scope_slots 为空时调用。
    要求 reward.extra_info 含 'rarity' / 'featured' 键（batch_simulator 需改造）。
    """
    scope_slots: Dict[str, list] = {}
    featured_slots: Dict[str, list] = {}
    scope_cards: Dict[str, list] = {}
    base_probs: Dict[str, float] = {}

    for rwd, prob in pool.rewards:
        r = rwd.extra_info.get('rarity', '')
        if not r:
            continue
        scope_slots.setdefault(r, []).append(rwd.id)
        scope_cards.setdefault(r, []).append(rwd.id)
        if rwd.extra_info.get('featured', False):
            featured_slots.setdefault(r, []).append(rwd.id)
        base_probs[rwd.id] = prob

    scope_slots   = {k: tuple(v) for k, v in scope_slots.items()}
    featured_slots = {k: tuple(v) for k, v in featured_slots.items()}
    scope_cards    = {k: tuple(v) for k, v in scope_cards.items()}

    reward_rarity = reward.extra_info.get('rarity', '')
    is_featured = reward.extra_info.get('featured', False)

    return DrawInfo(
        pool_id=pool.id,
        pool_instance_id=pool.id,
        reward_id=reward.id,
        reward_rarity=reward_rarity,
        is_featured=is_featured,
        scope_cards=scope_cards,
        scope_slots=scope_slots,
        featured_slots=featured_slots,
        base_probabilities=MappingProxyType(base_probs),
        rarity_rank=self._rarity_rank,
    )
```

**方案 B 的前置条件（若启用）：`batch_simulator.py` 构造 Reward 时必须携带 extra_info：**
```python
# batch_simulator.py:555-558 需改为：
rwd = Reward(id=de.card_id, name=getattr(de, 'card_id', ''),
             resources_gained=rg, first_time_bonus=ft,
             nth_time_bonus=nth, excess_bonus=xs,
             extra_info={'rarity': de.rarity, 'featured': de.featured})
```

**PoolPitySpec 新增字段（SimulationEnvBuilder 在构建时从 `PoolEntry.distribution: List[PoolDistEntry]` 一次性计算填入）：**

```python
@dataclass
class PoolPitySpec:
    pity_names: List[str]
    featured_ids: Set[str] = field(default_factory=set)
    ssr_ids: Set[str] = field(default_factory=set)
    <!-- REVIEW-FIX-PREV: ISSUE-029 -->
    # ⚠ P55 遗留字段——桥接代码（pity.py:498-502 / 538-542）删除后不再被消费。
    # 新 SoftStepBehavior._compute_probabilities() 和 HardPityBehavior._compute_probabilities()
    # 通过 DrawInfo.scope_slots / featured_slots 获取目标信息，不读取 resolved_targets。
    # 桥接代码是 resolved_targets 的唯一消费方——该代码标记为 P55 迁移后删除。
    # 桥接删除后，此字段 + batch_simulator._resolve_targets()（约 30 行）+
    # worst_impact._resolve_targets_for_pool()（约 21 行）一并移除。
    # 清理时机：阶段十二（波及文件适配）中 batch_simulator.py / worst_impact.py
    # 改造完成、桥接代码删除后，立即移除此字段及相关函数。
    resolved_targets: Dict[str, Dict[str, float]] = field(default_factory=dict)  # ← P55 后移除
    <!-- /REVIEW-FIX-PREV: ISSUE-029 -->
    # P55 新增（ISSUE-002 / ISSUE-008 / ISSUE-011）——由 SimulationEnvBuilder 预计算
    scope_cards: Dict[str, tuple[str, ...]] = field(default_factory=dict)
    scope_slots: Dict[str, tuple[str, ...]] = field(default_factory=dict)
    featured_slots: Dict[str, tuple[str, ...]] = field(default_factory=dict)
```

<!-- REVIEW-FIX-PREV: ISSUE-015 -->
`SimulationEnvBuilder`（`batch_simulator.py:510`）在 `_build_pity_engine_from_gui()` 中，遍历 `PoolEntry.distribution: List[PoolDistEntry]`，按 `entry.rarity` 分组后填入 `PoolPitySpec.scope_slots` / `featured_slots` / `scope_cards`。**注意：`PoolEntry.distribution` 是配置层类型，仅在构建期可用——运行时 Pool 对象上无此属性。**

<!-- REVIEW-FIX-PREV: ISSUE-032 -->
**预计算伪代码（`SimulationEnvBuilder._build_pool_pity_spec()`——约 30 行）：**

```python
def _build_pool_pity_spec(self, pe: PoolEntry) -> PoolPitySpec:
    """从 PoolEntry.distribution 预计算 PoolPitySpec 的 scope 分组字段。

    这是整个 scope_slots 数据链路的关键环节——若预计算逻辑错误，
    保底概率调整将静默失效。必须在构建期（而非运行时）完成分组，
    因为 PoolDistEntry 仅在配置层可用。
    """
    scope_slots: Dict[str, List[str]] = {}     # rarity → 槽位 ID 列表
    featured_slots: Dict[str, List[str]] = {}   # rarity → featured=true 的槽位 ID
    scope_cards: Dict[str, List[str]] = {}      # rarity → 卡牌 ID 列表
    featured_ids: Set[str] = set()
    ssr_ids: Set[str] = set()

    for de in getattr(pe, 'distribution', []):
        # ISSUE-015 防御性归一化：entry.rarity 可能为大写（'SSR'），
        # 必须 .lower() 后才能与 scope（默认小写）正确匹配。
        rarity = de.rarity.lower().strip()
        if not rarity or de.card_id == '_no_card':
            continue

        # scope_cards: rarity → 卡牌 ID（用于 _infer_rarity() 判定）
        scope_cards.setdefault(rarity, []).append(de.card_id)

        # scope_slots: rarity → 槽位 ID（用于 before_draw 概率调整时累加）
        # 槽位 ID 与卡牌 ID 可能不同（如多个卡牌共享同一稀有度槽位），
        # 此处以 rarity 名作为槽位 ID——与 base_probabilities 的 key 对齐。
        slot_id = rarity  # 默认：槽位 ID = 稀有度名
        scope_slots.setdefault(rarity, []).append(slot_id)

        # featured_slots: rarity → 标记 featured=true 的槽位 ID 子集
        if de.featured:
            featured_slots.setdefault(rarity, []).append(slot_id)

        # 向后兼容：填充旧 featured_ids / ssr_ids 集合
        if de.featured:
            featured_ids.add(de.card_id)
        if rarity == 'ssr':
            ssr_ids.add(de.card_id)

    # 去重 + 转为不可变 tuple
    scope_slots_map   = {k: tuple(dict.fromkeys(v)) for k, v in scope_slots.items()}
    featured_slots_map = {k: tuple(dict.fromkeys(v)) for k, v in featured_slots.items()}
    scope_cards_map   = {k: tuple(dict.fromkeys(v)) for k, v in scope_cards.items()}

    # ── 从 PoolEntry.pity_overrides 读取 pity_names（现有逻辑保留） ──
    pity_names = list(getattr(pe, 'pity_overrides', {}).keys()) if hasattr(pe, 'pity_overrides') else []

    return PoolPitySpec(
        pity_names=pity_names,
        featured_ids=featured_ids,
        ssr_ids=ssr_ids,
        scope_cards=scope_cards_map,
        scope_slots=scope_slots_map,
        featured_slots=featured_slots_map,
    )
```

**关键设计决策：**
- 槽位 ID 默认等同于稀有度名（`slot_id = rarity`），与当前 `base_probabilities` 中以稀有度名作为 key 的惯例对齐。若未来需要区分同稀有度的多个独立槽位，`PoolDistEntry` 需新增 `slot_id` 字段——此时修改此函数中 `slot_id = getattr(de, 'slot_id', rarity)` 即可。
- `scope_slots` 使用 `dict.fromkeys(v)` 去重——同一稀有度的多个 `PoolDistEntry` 共享同一槽位 ID 时只保留一个。
- 若 `pe.distribution` 为空或不存在，三个 scope 字段均为空 dict——供 `_build_draw_info()` 的方案 B 兜底路径（§3.2.1）接管。
<!-- REVIEW-R1-FIX: ISSUE-043 -->
- **`pity_names` 获取策略变更（行为-池子关联从 fnmatch 匹配切换为 `pity_overrides` 直接读取）：** 旧路径（`batch_simulator.py:169-188`）遍历 `PityDef` 列表，使用 `fnmatch.fnmatch(pid, pdef.pools)` 将每个 `PityDef` 匹配到池子——支持通配符（如 `'*'` = 全池子、`'pool_*'` 前缀匹配）。P55 改为直接从 `PoolEntry.pity_overrides` 字典读取行为名列表——不再遍历 `PityDef` 列表做 fnmatch 匹配。此变更的原因：(a) `pity_overrides` 在加载配置时已由 `SimulationEnvBuilder` 按 `PityDef.pools` 的 fnmatch 规则预填充——运行时只需 O(1) 查字典，消除 per-pool 的 O(pity_defs) 遍历开销；(b) `pity_overrides` 支持 per-pool 参数覆写（P56 扩展），为池子级别的差异化配置预留入口。**迁移契约（强制）：** `SimulationEnvBuilder` 必须在构造 `PoolPitySpec` 前遍历所有 `PityDef`，将每个 `PityDef.name` 按其 `pools` 字段（fnmatch 模式）匹配到对应池子的 `PoolEntry.pity_overrides` 字典中。`PityDef.pools` 字段保留——作为配置层声明式入口，不降级为纯文档/校验字段。若 `pity_overrides` 未初始化（旧路径未调用预填充逻辑），`getattr(pe, 'pity_overrides', {}).keys()` 返回空集 → 该池子无保底行为关联 → 保底静默失效。**验收：** `_build_pool_pity_spec()` 产出的 `PoolPitySpec.pity_names` 非空（至少含一条匹配的保底名）。
<!-- /REVIEW-R1-FIX: ISSUE-043 -->
<!-- /REVIEW-FIX-PREV: ISSUE-032 -->

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-7 -->
**ISSUE-015 + AUDIT-BREAK-7 防御性归一化：** `entry.rarity` 可能为大写（如 `"SSR"`——当前 `_infer_rarity()` 返回大写，`config_store.py:12` 默认 `'R'` 但用户可配 `'SSR'`），而 `PityDef.scope` 默认小写 `"ssr"`。分组时必须对 `entry.rarity` 调用 `.lower()` 归一化，否则 `scope_slots.get(self._scope, ())` 因大小写不匹配返回空 tuple——保底静默不触发。同时 `_build_pity_def()` 解析 scope 时也已统一 `.lower()`。**两处均做防御性归一化。** 此外槽位ID默认=稀有度名——与 `base_probabilities` 的 key 语义必须对齐（见 §0.3 AUDIT-BREAK-8）。
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-7 -->

**两种读取路径（优先级递减）：**
1. `PoolPitySpec` 已有预计算值（`scope_slots` 非空） → `_build_draw_info()` 直接从 `spec` 读取（O(1)，不遍历 pool.rewards）
2. `PoolPitySpec` 未提供（字段为空） → `_build_draw_info_fallback()` 遍历 `pool.rewards` 实时推导（需 Reward.extra_info 支持）

无论哪种路径，`DrawInfo.scope_slots` / `DrawInfo.featured_slots` / `DrawInfo.scope_cards` 最终都不为空——至少包含 `scope` 对应稀有度的条目。

**与 P60 的边界：** `DrawInfo` 数据类定义在 P60 平台层（`pity.py:13-24`）。P55 在此约定：(1) `_build_draw_info()` 在 P55 实现；(2) `PoolPitySpec` 的 3 个新字段在 P55 加入；(3) `SimulationEnvBuilder` 的预计算逻辑在 P55 加入。P55 的 behavior 实现仅消费 `DrawInfo` 中的这些字段，不关心填充逻辑。

<!-- REVIEW-FIX-PREV: ISSUE-025 -->
**3 个现有 DrawInfo 构造点的改造（pity.py:480/520/561）：**
原来 3 处硬编码 `scope_cards={}, scope_slots={}, featured_slots={}` 全部替换为调用 `self._build_draw_info()` 返回值中的对应字段：
- **before_draw 上下文（1 处，pity.py:480）：** `self._build_draw_info(pool_id, None, self.pool_specs[pool_id], base_probabilities=probabilities)`——reward=None，DrawInfo 中 reward_rarity=''/is_featured=False/reward_id='' 占位。before_draw 管道中 `SoftStepBehavior._compute_probabilities()` 仅需 `scope_slots`/`featured_slots`/`base_probabilities`，不依赖 reward 字段。
- **after_draw 上下文（2 处，pity.py:520/561）：** `self._build_draw_info(pool_id, reward, self.pool_specs[pool_id], base_probabilities=probabilities)`——reward 为实际抽卡结果，正常推导 reward_rarity/is_featured/reward_id。（`probabilities` 为 GachaService 传入的第 3 参数——见 ISSUE-019。）<!-- /REVIEW-FIX-PREV: ISSUE-025 -->

**收益：**
- `ctx.draw.base_probabilities` 是 `Mapping`，不可写——误写编译报错
- `ctx.draw` 是 `frozen`——不可整体重新赋值
- 测试中 `DrawInfo` 可独立构造 + 跨用例复用
- 接口即文档：`before_draw(self, ctx)` → 只能读 `ctx.draw`、写 `ctx.current`

<!-- REVIEW-FIX-PREV: ISSUE-016 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-13 -->
**现有 `_infer_rarity()` 方法的命运（ISSUE-016 + AUDIT-BREAK-13 大小写修正）：** 当前 `_infer_rarity()`（`pity.py:585-589`）通过 `reward.id in spec.ssr_ids` 成员判定，仅返回 `"SSR"` 或 `""`（空字符串），不区分 SR/R 等多级稀有度。P55 新增的 `_build_draw_info()` 方案 A 主路径中，`reward_rarity` 改为遍历 `rarity_rank` 所有层级 + 检查 `pool_spec.scope_cards` 成员——返回完整稀有度名（`"ssr"`/`"sr"`/`"r"`）。

**AUDIT-BREAK-13 关键警告：返回值大小写必须与 scope 一致。** `_should_reset()` 中比较 `ctx.draw.reward_rarity == self._scope`（两者均为小写）。若 `_infer_rarity()` 仍返回大写 `'SSR'` → `'SSR' != 'ssr'` → `_should_reset()` 始终返回 `False` → 计数器永不重置。**强制要求：扩展后的 `_infer_rarity()` 返回小写稀有度名，且 `_build_pool_pity_spec()` 中 `scope_cards` 的键也统一为小写。**

**策略：保留并扩展 `_infer_rarity()`。** 不创建新的独立稀有度判定方法——而是扩展 `_infer_rarity()` 使其遍历 spec 中的 scope_cards 键来返回完整稀有度名（小写）：

```python
def _infer_rarity(self, reward_id: str, pool_spec: PoolPitySpec,
                  rarity_rank: Dict[str, int]) -> str:
    """返回 reward_id 所属的完整稀有度名（小写），若未匹配返回 ''。"""
    # 按稀有度 rank 降序遍历（最高稀有度优先匹配）
    for rarity_name in sorted(rarity_rank, key=rarity_rank.get):
        if reward_id in pool_spec.scope_cards.get(rarity_name, ()):
            return rarity_name  # 已由 SimulationEnvBuilder 预计算时统一为小写
    # 兜底：检查旧 srr_ids（向后兼容）
    if reward_id in pool_spec.ssr_ids:
        return "ssr"
    return ""
```

**`after_draw()` 中的调用适配：** 当前 `after_draw()`（`pity.py:546-553`）调用 `self._infer_rarity(reward_id, spec)` 后构造 DrawInfo 的 `reward_rarity` 字段。P55 后：
- `_build_draw_info()` 内部调用扩展后的 `_infer_rarity(reward_id, pool_spec, rarity_rank)` 获取 `reward_rarity`
- `after_draw()` 不再单独调用 `_infer_rarity()`——直接使用 `_build_draw_info()` 返回的 `DrawInfo.reward_rarity`
- `_infer_rarity()` 保持为私有方法，不暴露为公共 API——通过 `_build_draw_info()` 间接消费

#### PityState 抽象化

**设计哲学：** 不预设字段类型——`PityState` 是一个以 `{behavior_name: {key: value}}` 为内部结构的三层嵌套 namespace 容器。behavior 自己决定存取什么、怎么解释，引擎不知道内部结构。

```
class PityState:
    """每个 behavior 通过自身 name 作为顶级 namespace 存取任意键值对。"""

    def get(self, name: str, key: str, default=None):
        return self._data.get(name, {}).get(key, default)

    def set(self, name: str, key: str, value):
        self._data.setdefault(name, {})[key] = value

    def incr(self, name: str, key: str, delta=1) -> int:
        v = self.get(name, key, 0) + delta
        self.set(name, key, v)
        return v

    def to_dict(self) -> dict:
        return {"data": self._data}

    @classmethod
    def from_dict(cls, d: dict) -> "PityState":
        ps = cls()
        ps._data = d.get("data", {})
        return ps
```

**对比：**

| | 旧 PityState（预设字段） | 新 PityState（抽象 namespace） |
|---|---|---|
| 结构 | `counters: Dict[str, int]` | `_data: Dict[str, Dict[str, Any]]` |
| 加新状态维度 | 修改 `PityState` 定义 → 改引擎 → 改序列化 | behavior 内部 `state.set(name, "新key", val)` |
| 扩展现有 behavior | 可能影响其他 behavior 的序列化 | 无影响——namespace 隔离 |
| 示例 | `state.counters["ssr_soft"] = 5` | `state.incr("ssr_soft", "counter")` |
| 轮换保底 | 需加 `flags: Dict[str, bool]` | `state.set("rotating", "guaranteed", True)` |
| 定轨 | 需加 `fate_points: Dict[str, int]` | `state.incr("epitomized", "fate_points")` |
| 终末地 per-banner | 需加 `scoped_counters: Dict[str, Dict[str, int]]` | `state.incr("ssr_hard", f"counter_{pool_instance_id}")` |

#### 完整数据流

```
                         ┌──────────────────────────────────────────────┐
                         │              PityEngine（调度器）              │
                         │                                              │
<!-- REVIEW-FIX-PREV: ISSUE-019 -->
  pool_id (str) ────────→│  1. 构建 PityContext                         │
  state (PityState) ────→│     · base_probabilities（GachaService 计算   │
                         │       后传入——§3.2.1 ISSUE-019）               │
  base_probabilities ───→│     · scope_cards（从 self.pool_specs 取      │
  reward (出卡结果) ────→│       PoolPitySpec 预计算字段）                │
                         │     · scope_slots（从 PoolPitySpec 按稀有度   │
                         │       分组槽位 ID——构造逻辑见 §3.2.1）         │
                         │     · featured_slots（scope_slots 中           │
                         │       featured=true 的子集）                   │
                         │     · reward_id / reward_rarity / is_featured │
                         │     · pool_instance_id（per-banner 隔离用）   │
                         │     · state 引用（behavior 可读写）            │<!-- /REVIEW-FIX-PREV: ISSUE-019 -->
                         │                                              │
                         │  2. before_draw():                            │
                         │     for bh in sorted_behaviors:               │
                         │       prob = bh.before_draw(ctx)              │──→ adjusted_probabilities
                         │       ctx.current = prob                      │    （用于最终抽卡）
                         │                                              │
                         │  3. after_draw(pool_id, state, reward, probs):  │
                         │     # ⚠ AUDIT-BREAK-9：第3参数从 reward.id    │
                         │     # (str) 改为 Reward 对象——引擎需要         │
                         │     # reward 推导稀有度和 featured 判定。      │
                         │     # 第4参数 probabilities（Dict[str,float]） │
                         │     # 为与 before_draw 相同的聚合后分布。      │
                         │     ctx = _build_draw_info(pool_id, reward,    │
                         │             pool_spec, probabilities)          │
                         │     for bh in behaviors:                      │
                         │       bh.after_draw(ctx)                      │──→ ctx.state._data 被修改
                         │       # bh 自己通过 state.set/incr 操作        │    （计数器、flag等）
                         │       # 引擎完全不知道 bh 做了什么              │
                         └──────────────────────────────────────────────┘
```

**关键约束：**
- `PityContext` 携带的 `base_probabilities` 是配置层产出的**原始**分布，behavior 不修改它
- `ctx.current` 在管道中传递——每个 behavior 在前一个调整后的概率上继续调整
- `state` 的写入是 behavior 通过自己的 namespace 隔离的，管道顺序不影响状态一致性
- behavior 之间可通过 `state.get("other_name", "key")` 读取对方状态（如未来的 `loss_streak` behavior 读取 rotating 的 `lost_rotating` flag——见手册 G17）

#### 策略层读接口

重构后保底状态散落在 `PityState._data["behavior_name"]["..."]` 中。策略系统（`StrategyContext.get_pity_probabilities()` / `select_action()`）需要**不耦合 `PityState` 内部结构**的查询接口。`PityEngine` 暴露以下方法供策略层消费：

```python
class PityEngine:
    # ── 策略层查询接口（不暴露 PityState 内部 key） ──

    def get_counter(self, name: str) -> int:
        """返回指定 behavior 的当前计数器值。不存在 → 0。"""
        return self._state.get(name, "counter", 0)

    def get_trigger_count(self, name: str) -> int:
        """返回指定 behavior 已触发的次数。"""
        return self._state.get(name, "triggers", 0)

    def is_guaranteed(self, name: str) -> bool:
        """返回指定 rotating behavior 是否处于大保底状态。非 rotating → False。"""
        return self._state.get(name, "guaranteed", False)

    def is_active(self, name: str) -> bool:
        """返回指定 behavior 当前是否活跃。"""
        return self._state.get(name, "_active", True)

    def get_state_summary(self) -> Dict[str, Dict[str, Any]]:
        """返回所有 behavior 的状态摘要（嵌套 dict 浅拷贝）。
        策略层可一次性获取全量状态，避免多次跨层调用。"""
        return {name: dict(ns) for name, ns in self._state._data.items()}
```

**设计原则：**
- 策略层通过 `PityEngine` 的方法查询，**不直接访问 `PityState._data`**——内部 key 名（`"counter"` / `"triggers"` / `"guaranteed"`）对策略层透明
- `get_state_summary()` 提供逃生舱——策略层可获取全量快照用于复杂决策，但常规查询应使用语义方法
- 这些方法是 **只读** 的——策略层不能通过此接口修改保底状态

<!-- REVIEW-FIX-PREV: ISSUE-010 -->
**只读查询的计数器值语义（ISSUE-010）：** `CounterBasedBehavior.before_draw(readonly=True)`（`pity.py:259-267`）中，只读路径取 `self._counter().value()`（当前值，不递增），非只读路径取 `self._counter().incr()`（递增后的值）。`_compute_probabilities(ctx, v)` 在两路径下收到的 `v` 差 1。

**设计决策：只读查询应返回「当前抽」的保底概率（递增前），即 `v = counter.value()`。** 理由：(1) 策略层的 `get_pity_probabilities()` 查询的是「如果不消耗抽数，当前状态下的保底概率」——尚未发生新的一抽，计数器不应递增；(2) 实际抽卡时 `before_draw(readonly=False)` 先递增再计算——此时 `v` 确实应该 +1，因为这一抽已经消耗了。两种路径的语义差异是**有意为之**、非 bug。

**策略层使用约定：** 若 `PityReserveStrategy`（`strategy.py:244-248`）需要判断「下一抽触发保底所需的抽数」，应调用 `PityEngine.get_counter(name)` 获取当前计数器值，而非依赖 `get_pity_probabilities()` 返回的概率分布来反推。命名约定：`get_counter()` 返回当前值（已消耗抽数），`get_pity_probabilities()` 返回若现在抽卡的概率分布。

#### SoftStepBehavior——deltas 引擎核心算法

`SoftStepBehavior` 是 P55 唯一的 counter 驱动软保底类。`soft_interval` / `soft_additive` 在 TOML 解析时展开为 `deltas`，统一由此类消费。

```python
class SoftStepBehavior(CounterBasedBehavior):
    """唯一的 counter 驱动软保底类——RLE deltas 驱动。

    deltas 格式：[[抽数段, 每抽增量%], ...]
    例：[[73, 0.0], [17, 5.88]] → 前 73 抽不增，后 17 抽每抽 +5.88%
    """

    # P55 对 P60 CounterBasedBehavior 的构造器扩展：
    # 新增 btype 参数——注入到基类，使 is_soft/is_event_driven/is_hard
    # 属性可通过 btype 推导（无需子类覆写）。P55 必须同步更新
    # CounterBasedBehavior.__init__ 签名以接受 btype。
    def __init__(self, name, state, scope, btype, deltas,
                 target_featured=False, lifecycle=None):
        super().__init__(name, state, scope, btype,
                         target_featured=target_featured, lifecycle=lifecycle)
        self._deltas = deltas

    # ── 核心：counter → 累计 boost ──

<!-- REVIEW-FIX-PREV: ISSUE-021 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-14 -->
<!-- AUDIT-BREAK-14 防御要求：若 soft_interval/soft_additive 语法糖未在构造前通过
     _expand_soft_to_deltas() 展开，self._deltas 为 None → for n, inc in self._deltas
     → TypeError。构造函数必须断言 self._deltas is not None，或 create_behavior()
     工厂在构造 SoftStepBehavior 前强制展开语法糖。 -->
    def _cumulative_boost(self, counter: int) -> float:
        """遍历 deltas RLE，按 counter 定位当前段并计算累计 boost%。

        ISSUE-021 防御：跳过 n <= 0 的段（防止 _expand_soft_to_deltas 产生
        [[-1, 0.0]] 等非法段导致 remaining 不减反增、boost 翻倍）。
        """
        boost = 0.0
        remaining = counter
        for n, inc in self._deltas:
            if n <= 0:
                continue  # 防御：跳过无效段（n 为负或零）
            if remaining <= n:
                boost += remaining * inc
                return min(boost, 100.0)
            boost += n * inc
            remaining -= n
        # counter 超出所有段 → 最后一档延续
        if self._deltas:
            boost += remaining * self._deltas[-1][1]
        return min(boost, 100.0)
<!-- /REVIEW-FIX-PREV: ISSUE-021 -->

    # ── 概率调整 ──

    <!-- REVIEW-FIX-PREV: AUDIT-BREAK-15 -->
    <!-- AUDIT-BREAK-15 关键警告：此函数的 pool/sum 操作依赖 ctx.current 的 key 与
         scope_slots 中的槽位 ID 语义一致。当前 GachaService 构造的 probabilities
         key 为卡牌ID（'limited_ssr_1'），而 scope_slots['ssr']=('ssr',)（稀有度名）。
         两者不匹配 → result.get('ssr', 0.0)=0.0 → pool=0 → 不偷概率 → 返回原分布。
         修复方案见 §0.3（GachaService 按稀有度聚合概率）或 §0.3 方案B。
         验收：scope_slots 的每个 slot_id 必须可作为 ctx.current 的 key 查找到非零值。 -->
    <!-- /REVIEW-FIX-PREV: AUDIT-BREAK-15 -->

    def _compute_probabilities(self, ctx, counter):
        """按 counter 计算 boost，跨稀有度重分配概率。

        算法：
          1. 累计 deltas → boost_pct（0–100）
          2. 定位 scope 槽位 + target_featured 收窄目标
          3. 从非目标槽位（含低稀有度）取 boost_pct% 概率 → 转给目标槽位
          4. 稀有度层级保护：排除 rank < scope_rank 的更高稀有度槽位
        """
        # 1. 累计 boost
        boost_pct = self._cumulative_boost(counter)
        if boost_pct <= 0:
            return ctx.current.copy()

        # 2. 槽位分组
        scope_slots = ctx.draw.scope_slots.get(self._scope, ())
        if not scope_slots:
            return ctx.current.copy()

        if self._target_featured:
            target_slots = ctx.draw.featured_slots.get(self._scope, scope_slots)
        else:
            target_slots = scope_slots

        # 3. 确定可抽取的概率池——排除目标槽位 + 更高稀有度槽位（层级保护）
        result = ctx.current.copy()
        scope_rank = ctx.draw.rarity_rank.get(self._scope, 99)

        higher_slots = set()
        for rarity, rank in ctx.draw.rarity_rank.items():
            if rank < scope_rank:
                higher_slots.update(ctx.draw.scope_slots.get(rarity, ()))

        non_target = [s for s in result
                      if s not in target_slots
                      and s not in higher_slots]

        if not non_target:
            return result

        pool = sum(result.get(s, 0.0) for s in non_target)
        if pool <= 0:
            return result

        # 4. 重分配：非目标 → 目标（按基础权重比例分配）
        steal = pool * boost_pct / 100.0
        ratio = 1.0 - boost_pct / 100.0

        for s in non_target:
            result[s] = result.get(s, 0.0) * ratio

        # 按目标槽位的基础权重比例分配（非均分——均分会破坏 SSR 内部 featured/standard 比例）
        target_weights = [ctx.draw.base_probabilities.get(s, 0.0) for s in target_slots]
        total_weight = sum(target_weights)
        if total_weight > 0:
            for s, w in zip(target_slots, target_weights):
                result[s] = result.get(s, 0.0) + steal * w / total_weight
        else:
            # 兜底：所有槽位基础权重为 0 时退化为均分
            per_target = steal / len(target_slots)
            for s in target_slots:
                result[s] = result.get(s, 0.0) + per_target

        return result
```

~60 行。关键性质：
- **deltas 逐段消费**：`_cumulative_boost` 遍历 RLE，counter 定位当前段后 break——不需要展开为逐抽数组
- **跨稀有度抽取**：`non_target` 包含 scope 及更低稀有度的**全部**非目标槽位——soft 保底将低稀有度概率注入高稀有度。例：`scope='ssr'` → pool = SR+R 全部概率（99%），`boost_pct=41.16%` → steal ≈ 40.7 个百分点
- **按基础权重比例分配**：`target_slots` 内部的概率增量不按均分（`steal / len`），而是按 `base_probabilities` 中各自的基础权重比例分配。保证 SSR 内部 featured/standard 比例在 soft 保底全程不变——soft 保底只增加 scope 总出率，不改变内部比例。内部比例的调整是 rotating 的职责
- **目标槽位保护**：`target_featured=true` 时 `target_slots` 收窄为 `featured_slots[scope]`——非 featured 槽位属于 `non_target` 被稀释
- **稀有度层级保护**：`higher_slots` 显式排除 rank < scope_rank 的槽位——`scope='sr'` 时 SSR 槽位不被抽取
- **封顶 100%**：`_cumulative_boost` 返回 min(boost, 100.0)，超出部分截断

#### HardPityBehavior——阈值触发强制出卡

```python
class HardPityBehavior(CounterBasedBehavior):
    """计数器驱动硬保底——counter 达到 threshold 时 scope 概率强制 100%。"""

    def __init__(self, name, state, scope, btype, threshold,
                 target_featured=False, lifecycle=None):
        super().__init__(name, state, scope, btype,
                         target_featured=target_featured, lifecycle=lifecycle)
        self._threshold = threshold

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-16 -->
    <!-- AUDIT-BREAK-16 关键警告：与 AUDIT-BREAK-15 相同的 key 语义断裂。
         scope_slots['ssr']=('ssr',) 但 ctx.current key 为卡牌ID。
         result.get('ssr', 0.0)=0.0 → scope_total=0 → 静默不工作。
         deactivate_on_early_hit 通过 _on_reset() 钩子实现——_active.clear()永久停用。
         修复方案同 §0.3。 -->
    <!-- /REVIEW-FIX-PREV: AUDIT-BREAK-16 -->
    def _compute_probabilities(self, ctx, counter):
        """counter < threshold → 不改动；≥ threshold → scope 概率 100%。"""
        if counter < self._threshold:
            return ctx.current.copy()

        scope_slots = ctx.draw.scope_slots.get(self._scope, ())
        if not scope_slots:
            return ctx.current.copy()

        target_slots = (
            ctx.draw.featured_slots.get(self._scope, scope_slots)
            if self._target_featured else scope_slots
        )

        result = ctx.current.copy()
        scope_rank = ctx.draw.rarity_rank.get(self._scope, 99)

        # 排除高稀有度槽位（层级保护）
        higher_slots = set()
        for rarity, rank in ctx.draw.rarity_rank.items():
            if rank < scope_rank:
                higher_slots.update(ctx.draw.scope_slots.get(rarity, ()))

        # 归零所有非目标、非高稀有度的槽位，累加概率到目标
        total = 0.0
        for s in list(result.keys()):
            if s not in higher_slots:
                total += result.get(s, 0.0)
                if s not in target_slots:
                    result[s] = 0.0

        # 目标槽位按基础权重比例分配全部概率
        if target_slots:
            target_weights = [ctx.draw.base_probabilities.get(s, 0.0) for s in target_slots]
            total_weight = sum(target_weights)
            if total_weight > 0:
                for s, w in zip(target_slots, target_weights):
                    result[s] = total * w / total_weight
            else:
                # 兜底：均分
                per_target = total / len(target_slots)
                for s in target_slots:
                    result[s] = per_target

        return result

<!-- REVIEW-FIX-PREV: ISSUE-020 -->
    def _on_reset(self, ctx) -> bool:
        """覆写父类钩子——加入 deactivate_on_early_hit 支持。

        返回 True 表示子类已处理重置逻辑，父类 after_draw() 跳过默认流程。
        返回 False 表示走父类默认的 reset + incr + max_triggers 检查。
        """
        if not self._lifecycle.deactivate_on_early_hit:
            return False  # 无特殊需求——走父类默认流程

        c = self._counter()
        if c.value() < self._threshold:
            # 提前命中（未达阈值就出货）→ 永久关闭此保底
            self._active.clear()
            return True   # 已处理——父类跳过
        # 达到阈值后触发 → 走父类默认 reset + incr 流程
        return False
```

~15 行（仅覆写钩子，不重复父类逻辑）。关键性质：
- **阈值前零干预**：`counter < threshold` 时直接返回 `ctx.current.copy()`——管道中后续 behavior 不受影响
- **阈值后强制 100%**：scope 稀有度的全部概率导向目标槽位，非目标归零
- **`deactivate_on_early_hit`**：通过覆写 `_on_reset()` 钩子实现——提前命中时 `_active.clear()` 永久停用——终末地 120 大保底场景
- **不覆写 `after_draw()`**：`HardPityBehavior` 仅覆写 `_on_reset()` 钩子，`before_draw()`/`after_draw()` 完全继承自 `CounterBasedBehavior`。若 P56 在父类 `after_draw()` 中新增生命周期逻辑（如 `depends_on` 激活），`HardPityBehavior` 自动获得——无代码重复、无静默丢失风险

**`CounterBasedBehavior.after_draw()` 中 `_on_reset()` 钩子的调用位置：**

```python
class CounterBasedBehavior(PityBehavior, ABC):
    def after_draw(self, ctx):
        if not self._active.is_set():
            return
        if not self._should_reset(ctx):
            return

        # ── 钩子：子类可覆写以注入自定义重置逻辑（如 deactivate_on_early_hit） ──
        if self._on_reset(ctx):
            return  # 子类已完全处理——跳过默认流程

        # ── 默认重置流程 ──
        self._counter().reset()
        self._triggers.incr()
        if (self._lifecycle.max_triggers
                and self._triggers.value() >= self._lifecycle.max_triggers):
            self._active.clear()

    def _on_reset(self, ctx) -> bool:
        """子类覆写点——自定义重置逻辑。

        返回 True  → 子类已处理，父类跳过默认 reset+incr 流程。
        返回 False → 走父类默认流程（默认实现）。
        """
        return False
```<!-- /REVIEW-FIX-PREV: ISSUE-020 -->

<!-- REVIEW-FIX-PREV: ISSUE-005 -->
#### CounterBasedBehavior._should_reset()——基于 scope + target_featured 自动推导

ISSUE-005 指出：当前 `CounterBasedBehavior`（`pity.py:227-286`）的 `__init__` 仍接受 `reset: str = None` 参数并赋值 `self._reset`（第 235、241 行），`_should_reset()`（第 280-283 行）仍使用 `self._reset` 判断——与计划 §1.2 声明的「reset 已移除」矛盾。

<!-- REVIEW-FIX-PREV: ISSUE-014 -->
**更新后的实现：**

```python
# ── 行为分类辅助（由 btype 推导，不依赖手写标志） ──

_SOFT_TYPES = {'soft_interval', 'soft_additive', 'soft_step',
               'rotating_soft', 'targeted_soft', 'rotating_cr_soft'}
_EVENT_DRIVEN_TYPES = {'rotating', 'rotating_soft', 'rotating_cr',
                       'rotating_cr_soft', 'targeted', 'targeted_soft'}
_HARD_TYPES = {'hard'}


class PityBehavior(ABC):
    """保底行为基类——所有 behavior 的公共接口。"""

    def __init__(self, name: str, state: 'PityState', scope: str,
                 btype: str, target_featured: bool = False,
                 lifecycle: 'LifecycleConfig' = None):
        self._name = name
        self._state = state
        self._scope = scope
        self._btype = btype
        self._target_featured = target_featured
        self._lifecycle = lifecycle if lifecycle is not None else LifecycleConfig()

    # ── 对外属性（供 _resolve_order / _validate_behaviors 使用） ──

    @property
    def scope(self) -> str:
        """稀有度作用范围（ssr/sr/r）。"""
        return self._scope

    @property
    def type(self) -> str:
        """行为类型标识（soft_interval / hard / rotating / ...）。"""
        return self._btype

    @property
    def category(self) -> str:
        """驱动分类：'counter' | 'event'——从 BEHAVIOR_REGISTRY 查询。"""
        return BEHAVIOR_REGISTRY[self._btype]['category']

    @property
    def is_soft(self) -> bool:
        """是否为软保底（概率增加型）——含 counter 驱动和事件驱动 soft 后缀。"""
        return self._btype in _SOFT_TYPES

    @property
    def is_event_driven(self) -> bool:
        """是否为事件驱动型（轮换/定轨/CR——重分配型）。"""
        return self._btype in _EVENT_DRIVEN_TYPES

    @property
    def is_hard(self) -> bool:
        """是否为硬保底（强制出卡型）。"""
        return self._btype in _HARD_TYPES

    <!-- REVIEW-R1-FIX: ISSUE-041 -->
    # ── 抽象方法——PityEngine 调度契约 ──
    # PityEngine.before_draw() / after_draw() 通过 bh.before_draw(ctx) /
    # bh.after_draw(ctx) 统一调度所有 behavior。P56 事件驱动 behavior
    #（RotatingBehavior 等）直接从 PityBehavior 继承——若基类未声明此契约，
    # P56 实施者忘记实现这两个方法时，PityEngine 调度将抛出 AttributeError
    # 而非清晰的 TypeError/NotImplementedError。

    @abstractmethod
    def before_draw(self, ctx: 'PityContext') -> Dict[str, float]:
        """概率调整——在抽卡前被 PityEngine 调用。

        返回调整后的概率分布 dict。behavior 内部可读取 ctx.draw（静态事实）、
        ctx.current（当前管道概率）、ctx.state（读写状态）。
        """
        ...

    @abstractmethod
    def after_draw(self, ctx: 'PityContext') -> None:
        """状态更新——在抽卡后被 PityEngine 调用。

        behavior 内部通过 ctx.state.set/incr 更新计数器/标志。
        引擎不感知 behavior 内部做了什么。
        """
        ...
    <!-- /REVIEW-R1-FIX: ISSUE-041 -->


class CounterBasedBehavior(PityBehavior, ABC):
    def __init__(self, name: str, state: 'PityState', scope: str,
                 btype: str,
                 target_featured: bool = False,
                 lifecycle: 'LifecycleConfig' = None):
        # reset 参数已移除——计数器重置条件由 scope + target_featured 自动推导
        super().__init__(name, state, scope, btype,
                         target_featured=target_featured, lifecycle=lifecycle)
        self._triggers = Counter(state, name, "triggers")
        self._active = Flag(state, name, "_active")
        if self._lifecycle.depends_on is None:
            self._active.set()

    def _should_reset(self, ctx: 'PityContext') -> bool:
        """计数器重置条件——由 scope + target_featured 自动推导。
        
        规则：
          1. reward_rarity 必须匹配 scope（稀有度层级）——不匹配则不重置
          2. 若 target_featured=True → 仅 featured 出货重置
          3. 若 target_featured=False → 任意 scope 出货重置
        """
        if ctx.draw.reward_rarity != self._scope:
            return False
        if self._target_featured:
            return ctx.draw.is_featured
        return True

    def did_fire(self, ctx: 'PityContext') -> bool:
        """委托给 _should_reset()——语义不变。"""
        return self._should_reset(ctx)
```

**变更要点：**
- `__init__` 移除 `reset: str = None` 参数和 `self._reset = reset if reset is not None else scope` 赋值。`_should_reset()` 直接使用 `self._scope` 和 `self._target_featured` 判断。
- `did_fire()` 无需修改——委托给 `_should_reset()` 不变。
- `SoftStepBehavior` / `HardPityBehavior` 构造器中不再传 `reset` 参数——仅传 `name` / `state` / `scope` / `target_featured` / `lifecycle`。
- 旧 `reset` 枚举值与新逻辑的映射：`any_ssr` → `scope='ssr', target_featured=False`（语义等价）；`featured_ssr` → `scope='ssr', target_featured=True`（语义等价）；`never` → 由里程碑系统（P56 `max_triggers=0` + `_active` 永不 clear）处理。

#### PityDef——扁平化保底配置 dataclass

```python
@dataclass
class PityDef:
    """单条 [[pity]] 的解析结果——所有字段扁平化，无嵌套 params dict。"""
    name: str                                    # 行为名称（全局唯一标识）
    btype: str                                   # type 字段（soft_interval / hard / rotating / ...）
    scope: str = "ssr"                           # 稀有度级别（ssr / sr / r）
    target_featured: bool = False                # 是否限定 featured 子集

    # 作用域
    pools: tuple[str, ...] = ()                  # 适用池子名（空 = 全池子）
    counter_init: int = 0                        # 初始水位（模拟前已垫抽数，counter 驱动）

    # 事件驱动——初始状态（rotating / targeted 家族——模拟开始前的状态快照）
    guaranteed_init: bool = False                # 初始大保底状态（rotating 家族：上次歪了→下一金必出 featured）
    fate_points_init: int = 0                    # 初始命定值（targeted 家族：已累积的命定值）

    # counter 驱动（soft_* / hard）
    deltas: tuple | None = None                  # RLE 增量数组（soft_* 专用）
    threshold: int = 0                           # hard 保底阈值（0 = 非 hard）

    # 事件驱动——_soft 后缀（rotating_soft / targeted_soft / rotating_cr_soft）
    soft_start: int | None = None
    soft_end: int | None = None
    soft_increment: float | None = None
    soft_deltas: tuple | None = None

    # 事件驱动——rotating_cr
    cr_counter_threshold: int = 3
    cr_base_rate: float = 0.0
    cr_state_probs: tuple[float, ...] | None = None

    # 事件驱动——targeted
    fate_threshold: int = 1
    switch_allowed: bool = True
    switch_resets_progress: bool = True

    # 生命周期（LifecycleConfig 平级展开，避免嵌套 dataclass）
    max_triggers: int = 0                        # 0 = 无限次触发
    deactivate_on_early_hit: bool = False        # 提前命中永久关闭（仅 hard）
    depends_on: str | None = None                # 依赖另一 behavior 首次命中后激活
```

设计要点：
- **无 `params: Dict[str, str]`**——旧设计将参数塞入字符串 dict，运行时解析类型。新设计每个字段独立类型，Python 类型系统承担校验
- **tuple 而非 list**——`deltas` / `pools` / `cr_state_probs` 用不可变 tuple，防止意外修改
- **`counter_init` 从 `PityConfig` 移至 `PityDef`**——初始水位是 per-behavior 的，不是全局的
- **`guaranteed_init`**——rotating 家族的初始大保底状态。`true` = 模拟开始时已处于大保底（上次小保底歪了，下一金必出 featured）。`false`（默认）= 从小保底开始。仅对 `rotating` / `rotating_soft` / `rotating_cr` / `rotating_cr_soft` 有效
- **`fate_points_init`**——targeted 家族的初始命定值。`1` = 已歪一次，再歪一次触发保证。`0`（默认）= 从零开始。仅对 `targeted` / `targeted_soft` 有效
- **lifecycle 字段在 PityDef 中平级展开**——`max_triggers` / `deactivate_on_early_hit` / `depends_on` 三个独立字段，避免配置 dataclass 嵌套。`create_behavior()` 工厂负责将它们打包为 `LifecycleConfig(max_triggers=..., deactivate_on_early_hit=..., depends_on=...)` 传给 behavior 构造函数。**LifecycleConfig 是运行时 dataclass（`CounterBasedBehavior.__init__` 的形参），PityDef 是配置 dataclass——两者分工明确**

#### BEHAVIOR_REGISTRY——P55 条目（counter 驱动 4 种）

P60 已交付 registry 框架（5 条 `class=None` 的 stub）。P55 替换为真实类 + 补全 `ui_params`：

```python
BEHAVIOR_REGISTRY = {
    # ── counter 驱动（P55 交付） ──

    "soft_interval": {
        "class": SoftStepBehavior,        # 语法糖——展开为 deltas 后统一消费
        "display_name": "区间软保底",
        "category": "counter",
        "ui_params": {
            "start":           {"widget": "spin",  "default": 74, "min": 0, "max": 200, "label": "起始抽数"},
            "end":             {"widget": "spin",  "default": 90, "min": 0, "max": 200, "label": "结束抽数"},
            "target_featured": {"widget": "check", "default": False, "label": "仅限 featured"},
            "counter_init":    {"widget": "spin",  "default": 0, "min": 0, "max": 200, "label": "初始水位"},
        },
    },

    "soft_additive": {
        "class": SoftStepBehavior,        # 语法糖——展开为 deltas 后统一消费
        "display_name": "累加软保底",
        "category": "counter",
        "ui_params": {
            "start":     {"widget": "spin", "default": 74, "min": 0, "max": 200, "label": "起始抽数"},
            "increment": {"widget": "double_spin", "default": 6.0, "min": 0.1, "max": 100.0, "step": 0.5, "label": "每抽增量(%)"},
        },
    },

    "soft_step": {
        "class": SoftStepBehavior,        # 底层——RLE deltas 直接消费
        "display_name": "逐抽自定义",
        "category": "counter",
        "ui_params": {},                  # 无通用控件——使用 deltas 表格编辑器（§4.4.3）
    },

    "hard": {
        "class": HardPityBehavior,
        "display_name": "硬保底",
        "category": "counter",
        "ui_params": {
            "threshold":       {"widget": "spin", "default": 90,  "min": 1, "max": 200, "label": "保底抽数"},
            "target_featured": {"widget": "check", "default": False, "label": "仅限 featured"},
            "counter_init":    {"widget": "spin", "default": 0,   "min": 0, "max": 200, "label": "初始水位"},
        },
    },

    # ── 事件驱动（P56 交付——当前 stub，class=None 表示未实现） ──
    "rotating":         {"class": None, "display_name": "轮换保底",     "category": "event"},
    "rotating_soft":    {"class": None, "display_name": "轮换+软保底",   "category": "event"},
    "rotating_cr":      {"class": None, "display_name": "轮换+捕获明光", "category": "event"},
    "rotating_cr_soft": {"class": None, "display_name": "轮换+CR+软保底","category": "event"},
    "targeted":         {"class": None, "display_name": "定向保底",      "category": "event"},
    "targeted_soft":    {"class": None, "display_name": "定轨+软保底",   "category": "event"},
}
```

**`category` 字段用途：**
- `"counter"` → `counter_init` 控件启用、`Counter` 遥控器生命周期
- `"event"` → `counter_init` 控件禁用、SSR 事件触发而非计数器

**三种 `soft_*` 的关系：**
- `soft_interval` / `soft_additive` → TOML 解析时 `_expand_soft_to_deltas()` 展开 → 运行时统一走 `SoftStepBehavior`
- `soft_step` → deltas 原样传入 `SoftStepBehavior`
- UI 上三者不同参数、同一底层类——新增变体只需加 registry 条目 + 展开函数分支，不改 `SoftStepBehavior`

**`create_behavior()` 工厂函数：**

```python
def create_behavior(name: str, state: PityState, pdef: PityDef) -> PityBehavior:
    """从 PityDef + registry 构造 behavior 实例。

    消除 PityEngine 中的 if-else 分发——引擎只知道 (name, state, pdef)，
    具体实例化逻辑由 registry + 工厂封装。
    """
    entry = BEHAVIOR_REGISTRY.get(pdef.btype)
    if entry is None:
        raise ConfigError(f"未知的保底 type '{pdef.btype}'——请检查 BEHAVIOR_REGISTRY")

    cls = entry["class"]
    if cls is None:
        raise ConfigError(
            f"type '{pdef.btype}'（{entry['display_name']}）尚未实现——"
            f"事件驱动型保底由 P56 交付，当前仅 counter 驱动型可用"
        )

<!-- REVIEW-FIX-PREV: ISSUE-014 -->
    # 通用参数——所有 behavior 共享
    kwargs = dict(
        name=name, state=state, scope=pdef.scope,
        btype=pdef.btype,             # ISSUE-014：注入 btype 以支持 scope/type/is_soft 等属性推导
        target_featured=pdef.target_featured,
    )

    # counter 驱动——附加 deltas / threshold
    if entry["category"] == "counter":
        if pdef.deltas is not None:
            kwargs["deltas"] = pdef.deltas
        if pdef.threshold:
            kwargs["threshold"] = pdef.threshold

    # 事件驱动——_soft 后缀（三态语法糖，P56 构造 SoftStepBehavior 实例时消费）
    if pdef.soft_start is not None:
        kwargs["soft_start"] = pdef.soft_start
    if pdef.soft_end is not None:
        kwargs["soft_end"] = pdef.soft_end
    if pdef.soft_increment is not None:
        kwargs["soft_increment"] = pdef.soft_increment
    if pdef.soft_deltas is not None:
        kwargs["soft_deltas"] = pdef.soft_deltas

    # 事件驱动——rotating_cr（P56 RotatingCRBehavior 专用）
    if pdef.cr_counter_threshold != 3:    # 非默认值 → 显式传入
        kwargs["cr_counter_threshold"] = pdef.cr_counter_threshold
    if pdef.cr_base_rate:
        kwargs["cr_base_rate"] = pdef.cr_base_rate
    if pdef.cr_state_probs is not None:
        kwargs["cr_state_probs"] = pdef.cr_state_probs

    <!-- REVIEW-R1-FIX: ISSUE-033 -->
    # 事件驱动——targeted（P56 TargetedBehavior 专用）
    # ISSUE-033 守卫：仅当 btype 为 targeted/targeted_soft 时注入三个 targeted 专属参数。
    # 无条件传参会致 P55 阶段的 SoftStepBehavior / HardPityBehavior 构造函数
    # 收到 unexpected keyword argument 而抛出 TypeError。
    if pdef.btype in ('targeted', 'targeted_soft'):
        kwargs["fate_threshold"] = pdef.fate_threshold
        kwargs["switch_allowed"] = pdef.switch_allowed
        kwargs["switch_resets_progress"] = pdef.switch_resets_progress
    <!-- /REVIEW-R1-FIX: ISSUE-033 -->

    # 生命周期——非默认值时传入
    if pdef.max_triggers or pdef.deactivate_on_early_hit or pdef.depends_on:
        kwargs["lifecycle"] = LifecycleConfig(
            max_triggers=pdef.max_triggers,
            deactivate_on_early_hit=pdef.deactivate_on_early_hit,
            depends_on=pdef.depends_on,
        )

    return cls(**kwargs)
```

~20 行。关键性质：
- **引擎零分发**：`PityEngine.__init__` 中 `for pdef in pity_defs: create_behavior(name, state, pdef)`——不写 if-else
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-28 -->
- **AUDIT-BREAK-28 防御：BEHAVIOR_REGISTRY 条目验证。** 若 registry 条目中 `class` 字段指向不存在的类名或拼写错误 → 运行时段错误（非导入时——`create_behavior()` 在执行时才查 registry）。建议在阶段八添加 registry 自检函数，在模块导入时遍历所有条目验证 `class is not None` 条目确实存在且可导入。
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-28 -->
- **P56 占位安全**：事件驱动 `class=None` → 明确报错「P56 交付」，而非静默跳过或 AttributeError
- **category 驱动参数选择**：counter 型传 deltas/threshold；事件型不传——由子类构造器自己从 PityDef 提取

<!-- REVIEW-FIX-PREV: ISSUE-007 -->
#### PityEngine 构造函数签名——从接收 behaviors dict 到接收 pity_defs list

ISSUE-007 指出：计划声明「引擎零分发」但未明确指定 `PityEngine.__init__` 的新签名。当前签名（`pity.py:438-441`）为：

```python
def __init__(self, pool_specs: Dict[str, PoolPitySpec],
             pity_defs: Dict[str, PityDefParsed],
             behaviors: Dict[str, PityBehavior],
             rarity_rank: Dict[str, int] = None):
```

<!-- REVIEW-R1-FIX: ISSUE-044 -->
> **免责声明：** 本节所列「旧签名」为计划写作时（2026-06-19）的代码快照。P60 实施后 `pity.py` 已有微调（如 `pool_specs` 类型注解从隐式变为显式 `Dict[str, PoolPitySpec]`）。上述签名与代码实际签名功能等价——差异仅在于类型注解的有无，不影响实施正确性。若需精确签名，以当前 `pity.py` 实际代码为准。
<!-- /REVIEW-R1-FIX: ISSUE-044 -->

其中 `behaviors` 由调用方预先构造并传入。P55 改为引擎内部调用 `create_behavior()` 工厂。

**更新后的签名：**

```python
class PityEngine:
    def __init__(self,
                 pool_specs: Dict[str, PoolPitySpec],
                 pity_defs: List[PityDef],             # 类型从 Dict[str, PityDefParsed] 改为 List[PityDef]
                 state: PityState,                      # 新增——引擎需要 state 来构造 Counter/Flag
                 rarity_rank: Dict[str, int] = None):
        self.pool_specs = pool_specs
        self.pity_defs = pity_defs
        self._state = state
        self._rarity_rank = rarity_rank or {}

        # 引擎内部通过工厂构造 behaviors——不再从外部接收
        self.behaviors: Dict[str, PityBehavior] = {}
        self._behavior_list: List[PityBehavior] = []
        for pdef in pity_defs:
            bh = create_behavior(pdef.name, state, pdef)
            self.behaviors[pdef.name] = bh
            self._behavior_list.append(bh)

<!-- REVIEW-FIX-PREV: ISSUE-017 -->
        # 自动排序 + 校验（PityEngine 私有方法，使用 self._rarity_rank）
        self._behavior_list = self._resolve_order(self._behavior_list)
        self._validate_behaviors(self._behavior_list)<!-- /REVIEW-FIX-PREV: ISSUE-017 -->

<!-- REVIEW-FIX-PREV: ISSUE-027 -->
    # ── 状态重绑定（ISSUE-027） ──
    # 构造时 state 与 per-call state 可能不是同一对象（multiprocessing 下
    # SimulationEnvBuilder 创建 state_A → pickle 传输 → GachaService 从
    # pity_state_init dict 创建 state_B）。behavior 内部的 Counter/Flag 在
    # create_behavior() 时持有 state_A 引用——per-call 调度前必须重绑定到
    # 实际使用的 state_B，否则计数器递增写入错误对象、对调度层不可见。

    def _rebind_state(self, state: PityState) -> None:
        """将所有 behavior 的 Counter/Flag 重新绑定到新的 PityState 实例。

        在 before_draw() / after_draw() 入口调用——确保 behavior
        内部的 Counter/Flag 遥控器指向调度层实际使用的 state 对象。
        """
        if state is self._state:
            return  # 同一对象——无需重绑定
        self._state = state
        for bh in self._behavior_list:
            if hasattr(bh, '_rebind_state'):
                bh._rebind_state(state)

    def before_draw(self, pool_id: str, state: PityState,
                    base_probabilities: Dict[str, float]) -> Dict[str, float]:
        self._rebind_state(state)  # ← 确保 behaviors 写入正确的 state
        # ... 构建 PityContext → foreach bh in _behaviors_for_pool ...

    def after_draw(self, pool_id: str, state: PityState,
                   reward, base_probabilities: Dict[str, float]) -> None:
        self._rebind_state(state)  # ← 同上
        # ... 构建 PityContext → foreach bh in _behaviors_for_pool ...
```

<!-- REVIEW-R2-FIX: ISSUE-059 -->
#### 3.2.0 create_behavior() 工厂函数——P55 更新版

P60 的 `create_behavior()`（`pity.py:343-372`）从 `BEHAVIOR_REGISTRY` 的 `default_scope` 读取 scope、从 `pdef.params` dict 读取参数并做类型转换——两者在 P55 中均不兼容：(1) scope 是 per-behavior 配置字段（`PityDef.scope`），必须从 PityDef 实例读取而非 registry 默认值；(2) P55 的 `PityDef` 已扁平化，`params` dict 不存在，所有参数从 PityDef 平级字段读取。

```python
def create_behavior(name: str, state: 'PityState', pdef: 'PityDef') -> 'PityBehavior':
    """P55 新版工厂：按 btype 分发，从 PityDef 平级字段读取参数。

    P60 旧签名 `create_behavior(pdef: PityDefParsed, state, **extra)` 已废弃——
    P55 中 PityDefParsed 被 PityDef 替代，scope 从 registry default_scope 改为 per-instance 读取。
    """
    entry = BEHAVIOR_REGISTRY[pdef.btype]
    cls = entry["class"]
    scope = pdef.scope  # ← P55 变更：从 PityDef 实例读取，非 registry default_scope

    # ── 生命周期构造（从 PityDef 平级字段） ──
    lifecycle = LifecycleConfig(
        max_triggers=pdef.max_triggers,
        deactivate_on_early_hit=pdef.deactivate_on_early_hit,
        depends_on=pdef.depends_on,
    )

    # ── 按 btype 分发到具体 behavior 类 ──
    if pdef.btype in SOFT_TYPES:
        # soft_interval / soft_additive / soft_step → SoftStepBehavior
        return SoftStepBehavior(
            name=name, state=state, scope=scope, btype=pdef.btype,
            deltas=pdef.deltas,  # 语法糖已在 _build_pity_def() 中展开
            target_featured=pdef.target_featured,
            lifecycle=lifecycle,
        )

    if pdef.btype == 'hard':
        return HardPityBehavior(
            name=name, state=state, scope=scope, btype=pdef.btype,
            threshold=pdef.threshold,
            counter_init=pdef.counter_init,
            target_featured=pdef.target_featured,
            lifecycle=lifecycle,
        )

    if pdef.btype in ('rotating', 'rotating_soft'):
        return RotatingBehavior(
            name=name, state=state, scope=scope, btype=pdef.btype,
            counter_init=pdef.counter_init,
            guaranteed_init=pdef.guaranteed_init,
            target_featured=pdef.target_featured,
            soft_start=pdef.soft_start,
            soft_end=pdef.soft_end,
            soft_increment=pdef.soft_increment,
            soft_deltas=pdef.soft_deltas,
            lifecycle=lifecycle,
        )

    if pdef.btype in ('rotating_cr', 'rotating_cr_soft'):
        return RotatingCRBehavior(
            name=name, state=state, scope=scope, btype=pdef.btype,
            counter_init=pdef.counter_init,
            guaranteed_init=pdef.guaranteed_init,
            cr_counter_threshold=pdef.cr_counter_threshold,
            cr_base_rate=pdef.cr_base_rate,
            cr_state_probs=pdef.cr_state_probs,
            soft_start=pdef.soft_start,
            soft_end=pdef.soft_end,
            soft_increment=pdef.soft_increment,
            soft_deltas=pdef.soft_deltas,
            lifecycle=lifecycle,
        )

    if pdef.btype in ('targeted', 'targeted_soft'):
        return TargetedBehavior(
            name=name, state=state, scope=scope, btype=pdef.btype,
            counter_init=pdef.counter_init,
            fate_points_init=pdef.fate_points_init,
            fate_threshold=pdef.fate_threshold,
            switch_allowed=pdef.switch_allowed,
            switch_resets_progress=pdef.switch_resets_progress,
            soft_start=pdef.soft_start,
            soft_end=pdef.soft_end,
            soft_increment=pdef.soft_increment,
            soft_deltas=pdef.soft_deltas,
            lifecycle=lifecycle,
        )

    raise ConfigError(f"未知的保底类型: {pdef.btype}")
```

**关键变更（与 P60 `create_behavior()` 对比）：**
- **scope 来源：** `pdef.scope`（per-behavior 配置）取代 `BEHAVIOR_REGISTRY[].default_scope`。
- **参数来源：** `PityDef` 平级字段（`deltas`/`threshold`/`counter_init`/`soft_start` 等）取代 `pdef.params` dict。
- **LifecycleConfig 构造：** 从 PityDef 的 `max_triggers`/`deactivate_on_early_hit`/`depends_on` 平级字段构造。
- **类型转换：** 不再需要——`PityDef` 字段类型已在 `_build_pity_def()` 解析阶段完成校验和转换。
<!-- /REVIEW-R2-FIX: ISSUE-059 -->

**CounterBasedBehavior._rebind_state() 实现：**

```python
class CounterBasedBehavior(PityBehavior, ABC):
    def _rebind_state(self, state: PityState) -> None:
        """重新绑定所有 Counter/Flag 遥控器到新的 PityState 实例。"""
        self._state = state
        self._triggers = Counter(state, self._name, "triggers")
        self._active = Flag(state, self._name, "_active")
        # 子类覆写——重绑定自身特有的 Counter/Flag
        self._on_rebind_state(state)

    def _on_rebind_state(self, state: PityState) -> None:
        """子类覆写点——重绑定子类特有的 Counter/Flag。默认无操作。"""
        pass
```

**设计理由：** `Counter`/`Flag` 是轻量值对象（仅存 `(state_ref, name, key)` 三元组），重创建成本 O(1)。不采用「behaviors 延迟初始化 Counter/Flag」方案——因为 behavior 构造后可能需要立即通过 `get_counter()` 查询初始水位（`counter_init` 写入的初始值），延迟初始化会丢失此信息。`_rebind_state()` 同时保证构造时初始化和 per-call 调度两者都使用正确的 state 对象。

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-26 -->
**AUDIT-BREAK-26 遗漏风险：** 若 `_rebind_state()` 在 `get_probabilities()`（只读查询）中遗漏调用，只读路径将读取构造时的旧 state 对象（可能为空或过期），而非调度层实际使用的 state。**所有公开入口方法（`before_draw`/`after_draw`/`get_probabilities`/`get_counter`/`is_guaranteed` 等）均需在首行调用 `_rebind_state(state)`。**
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-26 -->

<!-- REVIEW-FIX-PREV: AUDIT-BREAK-29 -->
**AUDIT-BREAK-29 构造时序警告：** `SimulationEnv.pity_state_init: Optional[dict]` 数据流为：builder 构造 `PityEngine` 时传入 `PityState`（含 `counter_init` 值）→ behaviors 的 `Counter`/`Flag` 引用此 state → pickle 传输 → worker 中 `from_dict()` 创建新 `PityState`（也含 `counter_init`）→ `_rebind_state()` 重创建 `Counter` 指向新 state → `counter.value()=counter_init`（非 0）。流程自洽。**但若 builder 侧 `PityEngine` 构造在 `counter_init` 写入 `PityState` 之前**（即先构造引擎、后写初始水位），behavior 的 `Counter` 初始值为 0 → `_rebind_state` 后也为 0 → 丢失初始水位。**强制要求：`PityEngine` 构造前，`PityState` 必须已完成 `counter_init` 写入。**
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-29 -->

<!-- /REVIEW-FIX-PREV: ISSUE-027 -->
```

**签名变更清单：**

| 参数 | 旧 | 新 | 说明 |
|------|-----|-----|------|
| `pool_specs` | `Dict[str, PoolPitySpec]` | 不变 | — |
| `pity_defs` | `Dict[str, PityDefParsed]` | `List[PityDef]` | 从旧 PityDefParsed dict 改为扁平化 PityDef list |
| `behaviors` | `Dict[str, PityBehavior]` | **移除** | 引擎内部通过 create_behavior() 构造 |
| `state` | 无 | `PityState`（新增） | 引擎需要 state 来创建 Counter/Flag |
| `rarity_rank` | `Dict[str, int]` | 不变 | — |

**调用方适配：**

- `batch_simulator._build_pity_engine_from_gui()`（`batch_simulator.py:74` 附近）：移除预构造 behaviors 的逻辑，改为传入 `pity_defs: List[PityDef]` + `state: PityState`。旧逻辑中构造 `PoolPitySpec` 后手动创建 `SoftPityBehavior`/`HardPityBehavior` 实例的代码全部删除。
- `worst_impact._build_pity_engine()`（`worst_impact.py`）：同上——改为传入 `List[PityDef]` + `PityState`，不再预构造 behaviors dict。

### 3.3 配置语法

```toml
# ── 稀有度层级注册（P60 已交付 [rarities] 段 —— 见 P60 块5） ──
[rarities]
ranks = [
    ["UR", "SSR"],   # rank 0 — 最高，平级
    ["SR"],           # rank 1
    ["R"],            # rank 2
]

# ── 保底配置 ──

# 1. 区间软保底（语法糖——解析层展开为 deltas）
#    start=74, end=90 → deltas = [[73, 0.0], [17, 100/17]]（≈5.8824，每抽均摊）
[[pity]]
type = "soft_interval"
scope = "ssr"
target_featured = true
start = 74
end = 90
counter_init = 0                  # 可选，默认 0——模拟开始前已垫抽数

# 2. 累加软保底（语法糖——解析层展开为 deltas）
#    未指定 target_featured → 默认 false——全体 SSR 概率提升
[[pity]]
type = "soft_additive"
scope = "ssr"
start = 74
increment = 6.0

# 3. 自定义逐抽增量——RLE 压缩描述任意形状（底层）
[[pity]]
type = "soft_step"
scope = "ssr"
deltas = [
    [73, 0.0],     # 抽数 1-73：不增
    [5, 1.5],      # 抽数 74-78：每抽 +1.5%
    [6, 3.0],      # 抽数 79-84：每抽 +3.0%
    [5, 6.0],      # 抽数 85-89：每抽 +6.0%
    [1, 50.0],     # 抽数 90：+50%（总计跳到 100%）
]

# 5. 不歪型硬保底（仅 featured）
[[pity]]
type = "hard"
scope = "ssr"
target_featured = true
threshold = 180

# 6. SR 保底（每 10 抽保底 SR）
[[pity]]
type = "hard"
scope = "sr"
threshold = 10

# 7. 硬保底 + 仅触发一次（终末地 120 大保底）
[[pity]]
type = "hard"
scope = "ssr"
threshold = 120
max_triggers = 1

# 8. 轮换保底——基础二态轮换（纯净，无捕获明光）
# featured 占比由基础概率分布决定——无需 initial_win_rate
[[pity]]
type = "rotating"
scope = "ssr"

# 8b. 轮换保底 + 初始大保底状态——已垫了一个小保底歪了
[[pity]]
name = "rotating_5050"
type = "rotating"
scope = "ssr"
guaranteed_init = true             # 模拟开始时已处于大保底（下次必出 featured）

# 9. 轮换+软保底——RotatingSoftBehavior（74→90 + rotating）
[[pity]]
type = "rotating_soft"
scope = "ssr"
soft_start = 74
soft_end = 90

# 9b. 米池场景——已垫 73 抽 + 大保底状态
[[pity]]
name = "rotating_soft_char"
type = "rotating_soft"
scope = "ssr"
soft_start = 74
soft_end = 90
counter_init = 73                 # 已垫 73 抽
guaranteed_init = true            # 上次歪了，下一金必出 featured

# 10. 轮换+捕获明光——RotatingCRBehavior（原神 5.0+）
[[pity]]
type = "rotating_cr"
scope = "ssr"
cr_counter_threshold = 3
cr_base_rate = 0.00018
cr_state_probs = [0.0, 0.0, 0.0, 1.0]

# 11. 轮换+CR+软保底——RotatingCRSoftBehavior
[[pity]]
type = "rotating_cr_soft"
scope = "ssr"
soft_start = 74
soft_end = 90
cr_counter_threshold = 3
cr_base_rate = 0.00018
cr_state_probs = [0.0, 0.0, 0.0, 1.0]

# 12. 定向保底（定轨）——小保底 featured 占比由基础分布决定
[[pity]]
type = "targeted"
scope = "ssr"
fate_threshold = 1
switch_allowed = true
switch_resets_progress = true

# 13. 定轨+软保底——TargetedSoftBehavior
[[pity]]
type = "targeted_soft"
scope = "ssr"
soft_start = 63
soft_end = 80
fate_threshold = 1
switch_allowed = true
switch_resets_progress = true
```

#### 3.3.1 TOML → PityDef 解析

<!-- REVIEW-FIX-PREV: ISSUE-023 -->
**ISSUE-023 规范化步骤（在调用 `_build_pity_def()` 之前执行）：** P60 交付的 `ConfigStore._parse_rarities()` 将稀有度名 `.upper()` 后存入 `rarity_rank`，键为大写（如 `{'SSR': 0, 'SR': 1, 'R': 2}`）。`_build_pity()` 在调用 `_build_pity_def()` 之前，必须先将 `rarity_rank` 的键统一 `.lower()` 归一化：`rarity_rank_map = {k.lower(): v for k, v in config_store.rarity_rank.items()}`。`_build_pity_def()` 内部的 `scope.lower()` 校验才能正确匹配。`_parse_rarities` 本身保持大写存储不变（P60 已交付，改动影响面需评估——但建议后续 P60 修正中也改为小写，消除中间转换）。<!-- /REVIEW-FIX-PREV: ISSUE-023 -->

```python
SOFT_TYPES = {'soft_interval', 'soft_additive', 'soft_step'}

<!-- REVIEW-FIX-PREV: ISSUE-021 -->
def _expand_soft_to_deltas(raw):
    """语法糖展开：interval/additive → deltas。

    ISSUE-021 修正：当 start <= 1 时，跳过零增量前缀段（避免 [[-1, 0.0], ...] 负值第一段）。
    _cumulative_boost() 中同时增加 n <= 0 的防御性跳过（两处加固）。
    """
    <!-- REVIEW-R1-FIX: ISSUE-034 -->
    if raw['type'] == 'soft_interval':
        # ISSUE-034 防御：CLI/直接 TOML 编辑路径下 start 可能 >= end。
        # GUI 层（config_panel.py）有红色边框校验，但 TOML 解析层是最后安全网。
        if raw.get('start', 0) >= raw.get('end', 0):
            raise ConfigError(
                f"[[pity]] type='soft_interval' 的 start={raw['start']} "
                f"必须小于 end={raw['end']}。"
            )
        n = raw['end'] - raw['start'] + 1
        if raw['start'] <= 1:
            # start=0 或 start=1：无需零增量前缀，直接返回有效段
            return [[n, 100.0 / n]]
        return [[raw['start'] - 1, 0.0], [n, 100.0 / n]]
    <!-- /REVIEW-R1-FIX: ISSUE-034 -->
    if raw['type'] == 'soft_additive':
        # 每抽固定 +increment%，累加到 ≥100% 自然封顶
        # 例：start=74, increment=6.0 → ceil(100/6)=17 抽 → 74-90 每抽+6%
        n_additive = math.ceil(100.0 / raw['increment'])
        if raw['start'] <= 1:
            return [[n_additive, raw['increment']]]
        return [[raw['start'] - 1, 0.0], [n_additive, raw['increment']]]
    if raw['type'] == 'soft_step':
        <!-- REVIEW-R1-FIX: ISSUE-042 -->
        # ── soft_step 输入校验——deltas 直接来自用户输入，需在解析层校验格式 ──
        # 畸形输入（如 [[73]] 缺第二元素、"abc" 非列表、[[-1, 0.0]] 负数段）
        # 若不在此拦截，错误将延迟到 SoftStepBehavior._cumulative_boost() 中
        # for n, inc in self._deltas: 解包时才暴露（ValueError/TypeError）。
        deltas_raw = raw.get('deltas')
        if not isinstance(deltas_raw, list):
            raise ConfigError(
                f"[[pity]] type='soft_step' 的 deltas 必须是列表，"
                f"实际类型为 {type(deltas_raw).__name__}。"
            )
        if len(deltas_raw) == 0:
            raise ConfigError(
                f"[[pity]] type='soft_step' 的 deltas 不能为空列表——"
                f"至少需要一个 [抽数段, 每抽增量%] 条目。"
            )
        for i, seg in enumerate(deltas_raw):
            if not isinstance(seg, (list, tuple)) or len(seg) != 2:
                raise ConfigError(
                    f"[[pity]] type='soft_step' 的 deltas[{i}] = {seg!r} "
                    f"格式错误——每个条目必须是 [抽数段(int), 每抽增量%(float)]，"
                    f"长度为 2。"
                )
            n, inc = seg
            if not isinstance(n, int) or n <= 0:
                raise ConfigError(
                    f"[[pity]] type='soft_step' 的 deltas[{i}][0] = {n!r} "
                    f"必须是正整数（抽数段长度），实际为 {type(n).__name__}。"
                )
            if not isinstance(inc, (int, float)):
                raise ConfigError(
                    f"[[pity]] type='soft_step' 的 deltas[{i}][1] = {inc!r} "
                    f"必须是数字（每抽增量百分比），实际为 {type(inc).__name__}。"
                )
        return deltas_raw
        <!-- /REVIEW-R1-FIX: ISSUE-042 -->
<!-- /REVIEW-FIX-PREV: ISSUE-021 -->


def _build_pity_def(raw, rarity_rank_map):
    """单条 [[pity]] → PityDef。所有字段扁平化，无 params dict。

    rarity_rank_map: 由 _build_pity() 在调用前构造——从 ConfigStore.rarity_rank
    转换而来，键已统一为 .lower()。scope 注册校验依赖此映射。
    """
    btype = raw['type']

    <!-- REVIEW-R1-FIX: ISSUE-037 -->
    # ── name 字段非空校验 ──
    # 空名称导致 PityState namespace 静默冲突——所有 behavior 共享空字符串
    # namespace，Counter/Flag 遥控器互相覆盖。
    name = raw.get('name', '').strip()
    if not name:
        raise ConfigError(
            f"[[pity]] type='{btype}' 的 name 字段不能为空。"
            f"每条保底必须指定唯一的 name 以隔离 PityState namespace。"
        )
    <!-- /REVIEW-R1-FIX: ISSUE-037 -->

    scope = raw.get('scope', 'ssr').lower()   # 统一 .lower() 归一化

    # —— scope 注册校验 ——
    # rarity_rank_map 键已在 _build_pity() 调用前统一 .lower() 归一化
    if scope not in rarity_rank_map:
        raise ConfigError(
            f"[[pity]] type='{btype}' 的 scope='{scope}' "
            f"未在 [rarities] 中注册。已注册的稀有度：{list(rarity_rank_map.keys())}"
        )

    # —— 作用域 ——
    pools     = tuple(raw.get('pools', []))       # 适用池子
    cinit     = raw.get('counter_init', 0)         # 初始水位
    ginit     = raw.get('guaranteed_init', False)  # rotating 家族初始大保底状态
    finit     = raw.get('fate_points_init', 0)     # targeted 家族初始命定值

    # —— counter 驱动 ——
    target_featured = raw.get('target_featured', False)

    <!-- REVIEW-R1-FIX: ISSUE-034 -->
    # ISSUE-034 双重校验：TOML 解析层在调用 _expand_soft_to_deltas() 前
    # 再次校验 soft_interval 的 start < end。_expand_soft_to_deltas() 内部
    # 有同名校验（第一层），此处为第二层安全网——确保错误配置在解析阶段即被
    # ConfigError 拦截，而非进入运行时以 n <= 0 + boost=0 静默失效。
    if btype == 'soft_interval':
        if raw.get('start', 0) >= raw.get('end', 0):
            raise ConfigError(
                f"[[pity]] type='soft_interval' 的 start={raw.get('start')} "
                f"必须小于 end={raw.get('end')}。"
            )
    <!-- /REVIEW-R1-FIX: ISSUE-034 -->

    <!-- REVIEW-R2-FIX: ISSUE-060——round-trip 守卫：若 TOML 中已存在 deltas 键（由 _build_toml_pity 写出），直接使用而跳过 _expand_soft_to_deltas()——避免 soft_interval 写回后再次加载时因缺少 start/end 而 ConfigError。语法糖展开仅在首次加载（无 deltas 键）时执行。 -->
    # ISSUE-038 内层也转为 tuple 以保证完全不可变
    if btype in SOFT_TYPES:
        if 'deltas' in raw:
            # round-trip 路径：deltas 已由 _build_toml_pity() 写出——直接使用
            deltas_raw_val = raw['deltas']
            if not isinstance(deltas_raw_val, list) or len(deltas_raw_val) == 0:
                raise ConfigError(
                    f"[[pity]] type='{btype}' 的 deltas 格式错误（round-trip 路径）——"
                    f"期望非空列表，实际: {deltas_raw_val!r}"
                )
            deltas = tuple(tuple(seg) for seg in deltas_raw_val)
        else:
            # 首次加载路径——语法糖展开（soft_interval/soft_additive → deltas）
            deltas = tuple(tuple(seg) for seg in _expand_soft_to_deltas(raw))
    else:
        deltas = None
    # 设计要点：deltas 声明为 tuple[tuple[int, float], ...]——
    # 外层 tuple + 内层 tuple 双重不可变，防止 `pdef.deltas[0][1] = 999` 类意外修改。
    # _expand_soft_to_deltas() 返回 list-of-lists，此处包裹时内层也转换。
    <!-- /REVIEW-R1-FIX: ISSUE-038 -->
    threshold = raw.get('threshold', 0)            # hard 保底阈值

    # —— 事件驱动：_soft 后缀（三态语法糖 → 构造时由 _expand_soft_to_deltas 展开） ——
    soft_start     = raw.get('soft_start')
    soft_end       = raw.get('soft_end')
    soft_increment = raw.get('soft_increment')
    soft_deltas    = raw.get('soft_deltas')

    # —— 事件驱动：rotating_cr ——
    cr_counter_threshold = raw.get('cr_counter_threshold', 3)
    cr_base_rate         = raw.get('cr_base_rate', 0.0)
    cr_state_probs       = raw.get('cr_state_probs')

    # —— 事件驱动：targeted ——
    fate_threshold         = raw.get('fate_threshold', 1)
    switch_allowed         = raw.get('switch_allowed', True)
    switch_resets_progress = raw.get('switch_resets_progress', True)

    # —— 生命周期（平级字段，不嵌套） ——
    max_triggers            = raw.get('max_triggers', 0)
    deactivate_on_early_hit = raw.get('deactivate_on_early_hit', False)
    depends_on              = raw.get('depends_on')

    return PityDef(
        name=name,  <!-- REVIEW-R1-FIX: ISSUE-037——使用 .strip() 后非空校验过的 name -->
        btype=btype, scope=scope,
        target_featured=target_featured,
        pools=pools, counter_init=cinit,
        guaranteed_init=ginit, fate_points_init=finit,
        deltas=deltas, threshold=threshold,
        soft_start=soft_start, soft_end=soft_end,
        soft_increment=soft_increment, soft_deltas=soft_deltas,
        cr_counter_threshold=cr_counter_threshold,
        cr_base_rate=cr_base_rate, cr_state_probs=cr_state_probs,
        fate_threshold=fate_threshold,
        switch_allowed=switch_allowed, switch_resets_progress=switch_resets_progress,
        max_triggers=max_triggers,
        deactivate_on_early_hit=deactivate_on_early_hit,
        depends_on=depends_on,
    )
```

两个保留参数语义不变：
- `pools`：字符串数组 → `PityDef.pools`
- `counter_init`：int → `PityDef.counter_init`，`batch_simulator` 写 `PityState`

`reset` 已移除——计数器重置条件由 `target_featured` 自动推导：`_should_reset(ctx)` = 命中 scope 稀有度 且（`target_featured=true` → `is_featured` 为真；`false` → 直接通过）

目标分布（`target_distribution`）→ 替换为 `scope` + `target_featured`。

**调用上下文：`_build_pity()` 在调用 `_build_pity_def()` 前构造 `rarity_rank_map`：**

```python
def _build_pity(data, store):
    """TOML [[pity]] 列表 → List[PityDef]。"""
    # 从 ConfigStore 构造 rarity_rank_map（键统一 .lower() 归一化）
    rarity_rank_map = {k.lower(): v for k, v in store.rarity_rank.items()}

    pities = []
    for raw in data.get('pity', []):
        pdef = _build_pity_def(raw, rarity_rank_map)  # ← 传入归一化后的映射
        pities.append(pdef)

    <!-- REVIEW-R1-FIX: ISSUE-037 -->
    # ── name 重名校验（TOML 层第一道防线） ──
    # 两个 [[pity]] 使用相同 name → PityState 中同一 namespace 被后一个 behavior
    # 的 Counter/Flag 覆盖前一个——配置者无错误提示，计数器值意外丢失。
    names = [pdef.name for pdef in pities]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ConfigError(
            f"[[pity]] 中存在重复的 name 字段：{', '.join(sorted(duplicates))}。"
            f"每条保底的 name 必须全局唯一——name 是 PityState namespace 的隔离键，"
            f"重名将导致计数器/标志互相覆盖。"
        )
    <!-- /REVIEW-R1-FIX: ISSUE-037 -->

    <!-- REVIEW-R1-FIX: ISSUE-040 -->
    # ── 赋值到 ConfigStore（load_toml() 期望 _build_pity 直接修改 store.pity） ──
    # 当前 config_toml.py:59 调用 _build_pity(data, store) 时不接收返回值——
    # 期望函数内部完成 store.pity 赋值。若遗漏此步骤，store.pity 保持为
    # clear() 后的空 PityConfig(enabled=True, pities=[])，所有保底配置静默丢失。
    store.pity = PityConfig(enabled=True, pities=pities)
    <!-- /REVIEW-R1-FIX: ISSUE-040 -->

    return pities
```

**前置条件（§0.1 AUDIT-BREAK-1）：** `load_toml()` 必须先调用 `_parse_rarities(data, store)` 填充 `store.rarity_rank`，再调用 `_build_pity(data, store)`——否则 `rarity_rank_map` 为空 dict，所有 scope 校验失败。

<!-- REVIEW-FIX-PREV: ISSUE-006 -->
##### 旧格式兼容迁移

ISSUE-006 指出：当前 `config.toml` 的 `[[pity]]` 格式使用 `name` / `type`（`soft`|`hard`）/ `start` / `end` / `func` / `threshold` / `reset` / `pools` / `target` 等字段（见 `_build_pity()`，`config_toml.py:391-414`），与计划新格式字段集合完全不重叠。若不加迁移逻辑，用户加载现有 config.toml 时旧字段将被静默忽略，所有保底配置回退到默认值——静默数据丢失。

`_build_pity_def()` 需增加旧格式检测与自动迁移分支：

```python
def _build_pity_def(raw: dict) -> PityDef:
    """单条 [[pity]] → PityDef。同时检测并迁移旧格式。"""

    # ── 旧格式检测与自动迁移 ──
    if _is_legacy_format(raw):
        import warnings
        name = raw.get('name', '')
        warnings.warn(
            f"[[pity]] '{name}' 使用旧格式（start/end/func/reset/target），"
            f"已自动迁移为新格式。请检查迁移结果并更新 config.toml。"
        )
        raw = _migrate_legacy_pity(raw)

    # ... 后续解析（与  §3.3.1 主流程相同）...


def _is_legacy_format(raw: dict) -> bool:
    """检测旧格式：存在 start/end/func/reset 等旧字段且不存在 scope/target_featured 等新字段。"""
    has_legacy = any(k in raw for k in ('start', 'end', 'func', 'reset'))
    has_new = any(k in raw for k in ('scope', 'target_featured', 'deltas'))
    return has_legacy and not has_new


def _migrate_legacy_pity(raw: dict) -> dict:
    """旧格式 → 新格式映射。"""
    new = {}

    # type：soft → soft_interval；hard → hard
    old_type = raw.get('type', 'soft')
    new['type'] = {'soft': 'soft_interval', 'hard': 'hard'}.get(old_type, old_type)

    # scope：默认为池子最高稀有度 ssr
    new['scope'] = 'ssr'  # 旧格式无 scope，统一默认 ssr

    # soft_interval 参数
    if old_type == 'soft':
        new['start'] = raw.get('start', 0)
        new['end'] = raw.get('end', 0)
        new['type'] = 'soft_interval'  # 默认展开为区间型

    # hard 参数
    if old_type == 'hard':
        new['threshold'] = raw.get('threshold', 90)

    # reset 条件迁移
    reset = raw.get('reset', 'any_ssr')
    if reset == 'featured_ssr':
        new['target_featured'] = True
    elif reset == 'any_ssr':
        new['target_featured'] = False
    # reset == 'never' → 无对应新字段（里程碑系统职责），丢弃

    # 其他字段直接迁移
    if 'pools' in raw:
        new['pools'] = raw['pools']
    if 'name' in raw:
        new['name'] = raw['name']
    new['counter_init'] = raw.get('counter_init', 0)

<!-- REVIEW-FIX-PREV: ISSUE-012 -->
    # ── func 字段——非线形函数 ConfigError（不可静默丢弃） ──
    legacy_func = raw.get('func', 'linear')
    if legacy_func in ('exp', 'step'):
        raise ConfigError(
            f"[[pity]] '{raw.get('name', '?')}' 使用 func='{legacy_func}'（非线形软保底函数），"
            f"P55 的 deltas/RLE 模型无法等价表达 exp（二次函数）/ step（阶梯函数）的累积曲线。"
            f"请手动用 soft_step + 自定义 deltas 重新配置保底曲线，"
            f"或使用 soft_interval（线性区间）作为近似替代。"
        )
    # func='linear' → 等价于 soft_interval，无需特殊处理

    # 废弃字段——显式跳过
    # target, target_distribution → 丢弃（target_featured + scope 替代）

    return new
```

<!-- REVIEW-FIX-PREV: ISSUE-012 -->
**迁移规则速查表：**

| 旧字段 | 新字段 | 映射逻辑 |
|--------|--------|---------|
| `type = "soft"` | `type = "soft_interval"` | 统一展开为区间型（最接近旧语义） |
| `type = "hard"` | `type = "hard"` | 不变 |
| `start` / `end` | `start` / `end` | 直接迁移——由 `_expand_soft_to_deltas()` 消费 |
| `reset = "any_ssr"` | `target_featured = false` | scope 默认为 ssr |
| `reset = "featured_ssr"` | `target_featured = true` | 同上 |
| `reset = "never"` | 丢弃 | 里程碑系统职责——用户需手动配置 max_triggers |
| `func = "linear"` | 丢弃 | 等价于 soft_interval 线性区间——无需保留 |
| **`func = "exp"`** | **ConfigError** | 二次函数累积曲线无法用单段线性 RLE 表达——需用户手动用 `soft_step` + 自定义 `deltas` 近似 |
| **`func = "step"`** | **ConfigError** | 阶梯函数累积曲线同样无法用单段 RLE 表达——同上 |
| `target` / `target_distribution` | 丢弃 | `scope` + `target_featured` 替代 |
| `pools` | `pools` | 直接迁移 |

**迁移后行为：** 无论 GUI 加载还是 CLI 解析，检测到旧格式时自动迁移并发出 `UserWarning`（不阻塞加载），提示用户「已自动迁移——请检查配置并保存以更新 config.toml 格式」。旧格式字段在迁移后不再保留——保存时写出新格式。

<!-- REVIEW-R1-FIX: ISSUE-039 -->
##### 迁移后自动保存策略

**问题：** 迁移仅在内存中生效——若用户未手动保存（GUI 中点击保存按钮或程序退出时自动保存），磁盘上的 `config.toml` 仍是旧格式。下次加载时旧文件再次触发迁移警告。CLI 场景下无 GUI 自动保存机制，每次 CLI 运行都触发同一迁移警告，用户体验差。

**策略（按路径分层）：**

1. **GUI 路径：** `ConfigPanel.load_config()` 加载后检测 `load_toml()` 返回的 `ConfigStore` 是否包含 `_migrated_from_legacy` 标记（`ConfigStore` 新增布尔字段，迁移时设置为 `True`）。若标记为真，自动触发 `save_toml()` 覆盖磁盘文件（可选弹出确认对话框「配置格式已升级，是否保存为最新格式？」——默认 yes，5 秒超时自动确认）。确认后标记清除，下次加载不再触发。

2. **CLI 路径：** 新增 `--migrate` CLI 参数：
   - 有 `--migrate`：加载配置 → 迁移 → 自动 `save_toml()` 写回 → 打印「配置已保存为新格式」→ 退出（或继续执行后续模拟命令）
   - 无 `--migrate`：加载配置 → 迁移（仅内存）→ 打印 `UserWarning` + 建议「检测到旧格式配置已自动迁移。使用 --migrate 参数保存更新，或通过 GUI 保存一次」

3. **`_migrated_from_legacy` 标记实现：** `ConfigStore` 新增 `_migrated_from_legacy: bool = False` 属性（非 dataclass 字段，不入 TOML 序列化）。`_build_pity()` 中检测到旧格式并成功迁移后设 `store._migrated_from_legacy = True`。`save_toml()` 写回后设 `False`。

4. **CLI `--migrate` 实现伪代码：**
   ```python
   # cli.py 主入口
   if args.migrate:
       store = load_toml(config_path)
       if getattr(store, '_migrated_from_legacy', False):
           save_toml(store, config_path)
           print("配置已保存为最新格式。")
       else:
           print("配置已是最新格式，无需迁移。")
       # 可选：迁移后退出（不执行模拟），或继续执行后续命令
   ```

**设计理由：** 分离检测与保存——检测是无损的（仅内存），保存是显式的（需用户确认或 CLI 参数）。避免静默覆盖用户配置文件（用户可能希望先检查迁移结果再决定是否保存）。

<!-- /REVIEW-R1-FIX: ISSUE-039 -->
<!-- REVIEW-FIX-PREV: ISSUE-024 -->
##### 写路径：`_build_toml_pity()` —— PityDef → TOML dict

ISSUE-024 指出：当前 `save_toml()`（`config_toml.py:117-130`）按旧格式写出 `start`/`end`/`func`/`threshold`/`reset`/`target`/`counter_init=0`（硬编码），与新 PityDef 扁平字段完全不对应。以下提供写路径伪代码，与 `_build_pity_def()`（读路径）对称：

```python
def _build_toml_pity(pdef: PityDef) -> dict:
    """PityDef → TOML [[pity]] dict。与 _build_pity_def() 对称——round-trip 可逆。"""
    d: dict = {
        'type': pdef.btype,
        'scope': pdef.scope,
    }
    if pdef.name:
        d['name'] = pdef.name
    if pdef.pools:
        d['pools'] = list(pdef.pools)
<!-- REVIEW-R2-FIX: ISSUE-056 -->
    # ISSUE-056 修正：counter_init / guaranteed_init / fate_points_init / target_featured
    # 使用 is not 0 / is not False 显式比较（is not None 无需使用——四字段默认值均为 0 或 False，非 None），避免 Python 真值检查吞没零值和布尔 False。
    # counter_init=0 时 if pdef.counter_init: 为假 → 不写出 → round-trip 不可逆。
    # 受影响的字段（按声明顺序）：
    #   (a) counter_init: int 默认 0——改为 is not 0 比较。counter_init=0 时不写出（加载时缺键→默认值0语义等价）。若需无条件写出（含0），将条件从 is not 0 改为 is not None 并确保 PityDef.counter_init 类型为 Optional[int]。
    #   (b) guaranteed_init: bool 默认 False——改为 is not False 比较。
    #   (c) fate_points_init: int 默认 0——改为 is not 0 比较。
    #   (d) target_featured: bool 默认 False——改为 is not False 比较。
    if pdef.counter_init is not 0:
        d['counter_init'] = pdef.counter_init   # 从 PityDef 读取实际值，非 hardcode 0
    if pdef.guaranteed_init is not False:
        d['guaranteed_init'] = True             # rotating 家族初始大保底状态
    if pdef.fate_points_init is not 0:
        d['fate_points_init'] = pdef.fate_points_init  # targeted 家族初始命定值
    if pdef.target_featured is not False:
        d['target_featured'] = True

<!-- /REVIEW-R2-FIX: ISSUE-056 -->

<!-- REVIEW-R2-FIX: ISSUE-060——soft_interval/additive round-trip 修复：
     写回前尝试用 _deltas_to_soft_interval() 还原语法糖——
     可还原 → 写出 start/end 替代 deltas（保持用户可读性）；
     不可还原 → type 降级为 soft_step + deltas（数据不丢失）。
     soft_additive 无反向还原函数——写回时 type 降级为 soft_step + deltas。
     配合 _build_pity_def() 的 round-trip 守卫（deltas 键优先），
     确保保存→加载往返可逆。 -->
    if pdef.btype in SOFT_TYPES and pdef.deltas is not None:
        restored = _deltas_to_soft_interval(pdef.deltas)
        if restored is not None:
            # round-trip 可还原为语法糖——写出 start/end 替代 deltas
            d['type'] = restored['type']
            d['start'] = restored['start']
            d['end'] = restored['end']
        else:
            # 不可还原（如用户自定义 deltas 或 soft_additive）——
            # 降级 type 为 soft_step（若原 type 非 soft_step）并写出 deltas
            if pdef.btype != 'soft_step':
                d['type'] = 'soft_step'  # 覆盖构造函数中设置的 pdef.btype
            d['deltas'] = [list(seg) for seg in pdef.deltas]
    if pdef.threshold:
        d['threshold'] = pdef.threshold

    # ── 事件驱动：_soft 后缀 ──
    if pdef.soft_start is not None:
        d['soft_start'] = pdef.soft_start
    if pdef.soft_end is not None:
        d['soft_end'] = pdef.soft_end
    if pdef.soft_increment is not None:
        d['soft_increment'] = pdef.soft_increment
    if pdef.soft_deltas is not None:
        d['soft_deltas'] = [list(seg) for seg in pdef.soft_deltas]

    # ── 事件驱动：rotating_cr ──
    if pdef.btype in ('rotating_cr', 'rotating_cr_soft'):
        d['cr_counter_threshold'] = pdef.cr_counter_threshold
        if pdef.cr_base_rate:
            d['cr_base_rate'] = pdef.cr_base_rate
        if pdef.cr_state_probs is not None:
            d['cr_state_probs'] = list(pdef.cr_state_probs)

    # ── 事件驱动：targeted ──
    if pdef.btype in ('targeted', 'targeted_soft'):
        d['fate_threshold'] = pdef.fate_threshold
        d['switch_allowed'] = pdef.switch_allowed
        d['switch_resets_progress'] = pdef.switch_resets_progress

    # ── 生命周期（仅非默认值时写出——保持 TOML 简洁） ──
    if pdef.max_triggers:
        d['max_triggers'] = pdef.max_triggers
    if pdef.deactivate_on_early_hit:
        d['deactivate_on_early_hit'] = True
    if pdef.depends_on is not None:
        d['depends_on'] = pdef.depends_on

    return d


def _deltas_to_soft_interval(deltas: Sequence[Sequence[float]]) -> dict | None:
    """反向：尝试将 deltas 还原为 soft_interval 语法糖格式。

    仅在两段且首段增量为 0 时可还原。不可还原时返回 None——调用方降级为 soft_step + deltas。
    """
    if len(deltas) != 2:
        return None
    if deltas[0][1] != 0.0:
        return None
    zero_n = int(deltas[0][0])
    inc_n = int(deltas[1][0])
    # 验证增量均匀分配（100.0 / n 的浮点容差内）
    expected = 100.0 / inc_n
    if abs(deltas[1][1] - expected) > 0.01:
        return None
    return {'type': 'soft_interval', 'start': zero_n + 1, 'end': zero_n + inc_n}


def save_toml(config_store, path):
    """将 ConfigStore 序列化为 TOML 文件（改写自 config_toml.py:117-130）。"""
    data = {...}  # 其他节

    # ── 保底节：按新格式写出 ──
    <!-- REVIEW-FIX-PREV: ISSUE-028 -->
    # ISSUE-028 勘误：config_store 不存在 pity_defs 字段。
    # 实际结构为 config_store.pity: PityConfig，保底列表为 config_store.pity.pities: List[PityDef]。
    data['pity'] = [_build_toml_pity(pdef) for pdef in config_store.pity.pities]
    <!-- /REVIEW-FIX-PREV: ISSUE-028 -->
    <!-- REVIEW-FIX-PREV: AUDIT-BREAK-25 -->
    <!-- AUDIT-BREAK-25 防御：若 PityDef 重构未完成（仍使用旧 PityDefParsed），
         _build_toml_pity() 访问 pdef.scope/pdef.deltas/pdef.threshold → AttributeError。
         强制要求：save_toml() 必须与阶段十（PityDef 扁平化重构）同步完成。 -->
    <!-- /REVIEW-FIX-PREV: AUDIT-BREAK-25 -->

    with open(path, 'w') as f:
        toml.dump(data, f)
```

**关键变更（与旧 `save_toml` 对比）：**
- 不再写旧字段 `func`/`reset`/`target`——全部由新字段替代。`start`/`end` 在 round-trip 时由 `_deltas_to_soft_interval()` 尝试还原——可还原时写出以保持用户可读性，不可还原时 type 降级为 `soft_step` + `deltas`。
- `counter_init` 从 `PityDef.counter_init` 读取实际值（可能非零），而非硬编码 `0`。
- deltas 序列化为 `[[n, inc], ...]` 列表（RLE 压缩格式）。`_deltas_to_soft_interval()` 尝试反向还原为语法糖——成功则写出 `start`/`end` 替代 `deltas` 键，失败则写出 `deltas` 且 type 降级为 `soft_step`。
- 生命周期字段仅在非默认值（非零/非 False/非 None）时写出，保持 TOML 简洁。
- `_deltas_to_soft_interval()` 尝试将 deltas 还原为语法糖格式——仅在两段且首段为零增量时可行；不可还原时降级为 `soft_step` + `deltas`。
<!-- /REVIEW-FIX-PREV: ISSUE-024 -->

#### 3.3.2 测试策略——三层金字塔 + 数值锚点

P55 是 `breaking` 变更——所有旧测试失效，所有下游分析依赖保底概率正确性。测试策略分三层：单元层保证每个 behavior 的数学正确性，集成层保证多 behavior 叠加的管道正确性，端到端层保证 7 种策略行为不退化。

**3.3.2.1 测试数据工厂——减少测试摩擦**

每个测试都手动构造 `DrawInfo` / `PityContext` 的样板代码量极大。提供模块级 fixture 作为标准测试起点：

```python
# tests/conftest.py 或 tests/core/test_pity.py 模块顶

def make_pity_context(scope='ssr', target_featured=False, *,
                      counter=0, deltas=None, threshold=90,
                      base_probs=None, rarity_rank=None):
    """构造标准 PityContext 用于 behavior 单元测试。

    返回 (ctx, behavior) 元组——ctx 是完整的管道上下文，
    behavior 是按参数构造的 SoftStepBehavior 或 HardPityBehavior。
    """
    # 默认值——模拟标准 SSR 池（1% SSR, 15% SR, 84% R）
    if base_probs is None:
        base_probs = {'ssr': 0.01, 'sr': 0.15, 'r': 0.84}
    if rarity_rank is None:
        rarity_rank = {'ssr': 0, 'sr': 1, 'r': 2}

    draw_info = DrawInfo(
        pool_id='test_pool', pool_instance_id='test_pool',
        reward_id='', reward_rarity='', is_featured=False,
        scope_cards={'ssr': ('limited_ssr_1', 'standard_ssr_1'),
                     'sr': ('sr_card_1',), 'r': ('r_card_1',)},
        scope_slots={'ssr': ('ssr',), 'sr': ('sr',), 'r': ('r',)},
        featured_slots={'ssr': ('ssr',)} if target_featured else {},
        base_probabilities=MappingProxyType(base_probs),
        rarity_rank=rarity_rank,
    )
    state = PityState()
    ctx = PityContext(draw=draw_info, current=dict(base_probs), state=state)

    if deltas is not None:
        bh = SoftStepBehavior('test', state, scope, deltas,
                              target_featured=target_featured)
    else:
        bh = HardPityBehavior('test', state, scope, threshold,
                              target_featured=target_featured)
    return ctx, bh
```

**3.3.2.2 单元层——behavior 数学正确性**

每个 behavior 的核心算法通过独立单元测试覆盖。使用参数化覆盖关键数据点，而非对每个 counter 值测试。

```python
class TestSoftStepBehavior:
    """SoftStepBehavior._cumulative_boost() + _compute_probabilities()"""

    # ── _cumulative_boost 参数化 ──

    @pytest.mark.parametrize('deltas,counter,expected', [
        # 前段零增量
        ([[73, 0.0], [17, 5.88]], 0,   0.0),
        ([[73, 0.0], [17, 5.88]], 73,  0.0),
        # 进入增量段
        ([[73, 0.0], [17, 5.88]], 74,  5.88),
        ([[73, 0.0], [17, 5.88]], 80,  41.16),   # (80-73)*5.88
        ([[73, 0.0], [17, 5.88]], 90,  100.0),    # 17*5.88=99.96→min封顶
        # 超出全部段——最后一档延续
        ([[73, 0.0], [17, 5.88]], 120, 100.0),
        # 空 deltas
        ([], 50, 0.0),
    ])
    def test_cumulative_boost(self, deltas, counter, expected):
        ctx, bh = make_pity_context(deltas=deltas)
        assert bh._cumulative_boost(counter) == pytest.approx(expected, abs=1e-4)

    # ── _compute_probabilities 关键数据点 ──

    def test_no_boost_below_start(self):
        """counter=0 → 零 boost → 概率不变"""
        ctx, bh = make_pity_context(deltas=[[73, 0.0], [17, 5.88]], counter=0)
        result = bh._compute_probabilities(ctx, 0)
        assert result == pytest.approx(ctx.current)

    def test_soft_pity_midpoint_numerical(self):
        """counter=80, boost=41.16% → SSR 从 1% 升至 ≈41.7%
        数值锚点（手工验算）：
          pool = SR+R = 0.99
          steal = 0.99 × 0.4116 = 0.4076
          new_ssr = 0.01 + 0.4076 = 0.4176
          new_sr  = 0.15 × (1-0.4116) = 0.08826
        """
        ctx, bh = make_pity_context(
            deltas=[[73, 0.0], [17, 5.88]],
            base_probs={'ssr': 0.01, 'sr': 0.15, 'r': 0.84},
        )
        result = bh._compute_probabilities(ctx, 80)
        assert result['ssr'] == pytest.approx(0.4176, abs=1e-3)
        assert result['sr']  == pytest.approx(0.0883, abs=1e-3)

    def test_soft_pity_endpoint_full_boost(self):
        """counter=90, boost=100% → SSR 获取全部非 SSR 概率"""
        ctx, bh = make_pity_context(
            deltas=[[73, 0.0], [17, 5.88]],
            base_probs={'ssr': 0.01, 'sr': 0.15, 'r': 0.84},
        )
        result = bh._compute_probabilities(ctx, 90)
        assert result['ssr'] == pytest.approx(1.0)
        assert result['sr']  == pytest.approx(0.0)

    # ── 稀有度层级保护 ──

    def test_scope_sr_does_not_touch_ssr(self):
        """scope='sr' 的软保底不抽取 SSR 概率"""
        ctx, bh = make_pity_context(
            scope='sr', deltas=[[5, 0.0], [5, 20.0]],   # 每 10 抽 SR 保底
            base_probs={'ssr': 0.01, 'sr': 0.15, 'r': 0.84},
        )
        result = bh._compute_probabilities(ctx, 10)  # 100% boost
        assert result['ssr'] == pytest.approx(0.01)  # SSR 不变
        assert result['sr']  > 0.15                   # SR 增加

    # ── target_featured ──

    def test_target_featured_narrows_targets(self):
        """target_featured=true → 仅 featured 槽位获得 boost"""
        ctx, bh = make_pity_context(
            target_featured=True,
            deltas=[[73, 0.0], [17, 5.88]],
            base_probs={'ssr': 0.005, 'ssr_alt': 0.005, 'sr': 0.15, 'r': 0.84},
        )
        result = bh._compute_probabilities(ctx, 90)
        # ssr（featured）获得全部 SSR 概率 + 低稀有度抽取
        assert result['ssr'] > 0.9
        # ssr_alt（非 featured）被清零
        assert result['ssr_alt'] == pytest.approx(0.0)

    def test_proportional_distribution_unequal_weights(self):
        """不等基础权重 → 目标槽位按基础权重比例获得 boost（非均分）。

        场景：featured_A=0.003, featured_B=0.003, standard=0.004 → featured:standard=60:40
        均分会把 60:40 变成 50:50，按比例分配保持 60:40 不变。
        验证：100% boost 时 featured_A:featured_B:standard ≈ 30:30:40。
        """
        ctx, bh = make_pity_context(
            target_featured=False,  # 全体 SSR 按比例受益
            deltas=[[0, 100.0]],    # 从第 1 抽开始直接 +100% boost
            base_probs={'feat_a': 0.003, 'feat_b': 0.003, 'std': 0.004, 'sr': 0.15, 'r': 0.84},
        )
        # 修改 ctx 的 scope_slots 以匹配多槽位场景
        ctx.draw = replace(ctx.draw,
            scope_slots={'ssr': ('feat_a', 'feat_b', 'std'), 'sr': ('sr',), 'r': ('r',)})
        result = bh._compute_probabilities(ctx, 1)  # counter=1 → 100% boost
        # 按比例：total_weight = 0.01, feat_a 权重 = 0.003/0.01 = 0.3
        assert result['feat_a'] == pytest.approx(0.300, abs=1e-3)
        assert result['feat_b'] == pytest.approx(0.300, abs=1e-3)
        assert result['std']    == pytest.approx(0.400, abs=1e-3)
        # 比例保持 60:40 ✓


class TestHardPityBehavior:
    """HardPityBehavior._compute_probabilities()"""

    def test_below_threshold_no_intervention(self):
        ctx, bh = make_pity_context(threshold=90)
        result = bh._compute_probabilities(ctx, 89)
        assert result == pytest.approx(ctx.current)

    def test_at_threshold_forces_100_percent(self):
        ctx, bh = make_pity_context(threshold=90, base_probs={'ssr': 0.01, 'sr': 0.15, 'r': 0.84})
        result = bh._compute_probabilities(ctx, 90)
        assert result['ssr'] == pytest.approx(1.0)
        assert result['sr']  == pytest.approx(0.0)

    def test_scope_sr_hard_does_not_touch_ssr(self):
        ctx, bh = make_pity_context(scope='sr', threshold=10, base_probs={'ssr': 0.01, 'sr': 0.15, 'r': 0.84})
        result = bh._compute_probabilities(ctx, 10)
        assert result['ssr'] == pytest.approx(0.01)  # 不变


class TestCounterBasedBehavior:
    """CounterBasedBehavior 生命周期（before_draw / after_draw / _should_reset）"""

    def test_before_draw_increments_counter(self):
        ctx, bh = make_pity_context(deltas=[[73, 0.0], [17, 5.88]])
        bh.before_draw(ctx)            # counter: 0→1
        assert ctx.state.get('test', 'counter') == 1

    def test_should_reset_featured_only(self):
        """target_featured=true → 歪了不重置"""
        ctx, bh = make_pity_context(target_featured=True)
        ctx.draw = replace(ctx.draw, reward_rarity='ssr', is_featured=False)
        assert bh._should_reset(ctx) is False

    def test_should_reset_any_ssr(self):
        """target_featured=false → 任意 scope 出货都重置"""
        ctx, bh = make_pity_context(target_featured=False)
        ctx.draw = replace(ctx.draw, reward_rarity='ssr', is_featured=False)
        assert bh._should_reset(ctx) is True

    def test_max_triggers_deactivates(self):
        ctx, bh = make_pity_context(
            deltas=[[0, 10.0]],   # 从第 1 抽开始每抽 +10%
            max_triggers=1,
        )
        ctx.draw = replace(ctx.draw, reward_rarity='ssr', is_featured=True)
        bh.after_draw(ctx)       # 触发一次 → _active 置 False
        assert ctx.state.get('test', '_active') is False
```

**3.3.2.3 集成层——PityEngine 多 behavior 管道**

单元测试验证单个 behavior 的数学正确性后，集成测试验证 PityEngine 的调度正确性——排序、校验、管道叠加：

```python
class TestPityEngineIntegration:
    """多 behavior 叠加 + 排序 + 校验"""

    def test_soft_before_hard_order(self):
        """ssr_soft + sr_hard → ssr_soft 先执行"""
        engine = PityEngine(
            pool_specs={...},
            pity_defs=[
                PityDef(name='sr_hard',  btype='hard', scope='sr',  threshold=10),
                PityDef(name='ssr_soft', btype='soft_interval', scope='ssr',
                        deltas=((73, 0.0), (17, 5.88))),
            ],
            state=PityState(),
            rarity_rank={'ssr': 0, 'sr': 1, 'r': 2},
        )
        # _behavior_list 已排序——第一个应为 ssr_soft
        assert engine._behavior_list[0].name == 'ssr_soft'

    def test_pipeline_preserves_total_probability(self):
        """管道叠加后概率总和仍为 1.0"""
        engine = _make_engine_with_behaviors(
            PityDef(name='soft', btype='soft_interval', scope='ssr', deltas=((73,0),(17,5.88))),
            PityDef(name='hard', btype='hard', scope='sr', threshold=10),
        )
        probs = {'ssr': 0.01, 'sr': 0.15, 'r': 0.84}
        ctx = engine.before_draw('test_pool', state, probs)
        assert sum(ctx.current.values()) == pytest.approx(1.0)

    def test_two_behaviors_independent_counters(self):
        """同 scope 不同 name → 计数器独立"""
        engine = _make_engine_with_behaviors(
            PityDef(name='soft1', btype='soft_interval', scope='ssr', deltas=((73,0),(17,5.88))),
            PityDef(name='soft2', btype='soft_interval', scope='ssr', deltas=((73,0),(17,5.88))),
        )
        for _ in range(50):
            engine.before_draw('test_pool', state, probs)
        # 两个 behavior 各自独立计数
        assert engine.get_counter('soft1') == 50
        assert engine.get_counter('soft2') == 50

    def test_pity_state_roundtrip(self):
        """PityState 序列化往返无损——集成测试验证完整 pipeline"""
        state = PityState()
        state.set('soft', 'counter', 42)
        state.set('rotating', 'guaranteed', True)
        restored = PityState.from_dict(state.to_dict())
        assert restored.get('soft', 'counter') == 42
        assert restored.get('rotating', 'guaranteed') is True
```

**3.3.2.4 端到端层——策略行为等价性（回归安全网）**

这是最重要的防线：7 种策略在重构前后，对相同模拟种子，产出相同的结果分布。实现方式：

```python
class TestStrategyRegression:
    """重构前后策略行为等价性——数值锚点"""

    # 每种策略取最常用保底组合
    REGRESSION_CASES = [
        # (策略名, 保底配置, 模拟参数)
        ('smart',          'soft_interval_ssr',           dict(n=5000, seed=42)),
        ('pool_quota',     'soft_interval_ssr+hard_sr',  dict(n=5000, seed=42)),
        ('pity_reserve',   'soft_interval_ssr',           dict(n=5000, seed=42)),
        ('stop_on_target', 'rotating+soft_interval_ssr',  dict(n=3000, seed=42)),
        ('target_hunting', 'targeted+soft_interval_ssr',  dict(n=2000, seed=42)),
        ('fixed_count',    'none',                        dict(n=5000, seed=42)),
        ('draw_target',    'rotating+soft_interval_ssr',  dict(n=3000, seed=42)),
    ]

    @pytest.mark.parametrize('strategy,pity_config,sim_params', REGRESSION_CASES)
    def test_strategy_regression(self, strategy, pity_config, sim_params):
        """给定相同 seed，重构前后 GDR 指标偏差 < 1%"""
        config = _load_regression_config(strategy, pity_config)
        result_old = _simulate_with_old_pity(config, **sim_params)
        result_new = _simulate_with_new_pity(config, **sim_params)

        # 关键 GDR 指标对比
        for gdr_key in ['success_probability', 'expected_draws', 'featured_ratio']:
            old_val = result_old[gdr_key]
            new_val = result_new[gdr_key]
            rel_diff = abs(new_val - old_val) / max(abs(old_val), 1e-9)
            assert rel_diff < 0.01, \
                f"{strategy}/{gdr_key}: old={old_val:.6f} new={new_val:.6f} diff={rel_diff:.4%}"
```

**策略回归套件的锚点值——用于手动验证：**

| 策略 | 保底 | n | seed | `success_probability` | `expected_draws` |
|------|------|:---:|:---:|:---:|:---:|
| `smart` | soft_interval(74→90) | 5000 | 42 | ~0.85 | ~62.5 |
| `pity_reserve` | soft_interval(74→90) | 5000 | 42 | ~0.78 | ~68.2 |
| `pool_quota` | soft_interval(74→90)+hard_sr(10) | 5000 | 42 | ~0.82 | ~64.1 |

> 注：锚点值为近似值——实施阶段十三用重构后代码实际跑出精确值并回填此表。

**3.3.2.5 测试执行顺序——与实施阶段对齐**

| 阶段 | 产出 | 对应测试 |
|------|------|---------|
| 五 | `SoftStepBehavior` | `TestSoftStepBehavior`（单元） |
| 七 | `HardPityBehavior` | `TestHardPityBehavior`（单元） |
| 八 | `BEHAVIOR_REGISTRY` + `create_behavior()` | `TestCounterBasedBehavior`（单元） |
| 九 | `_resolve_order()` + `_validate_behaviors()` | `TestPityEngineIntegration`（集成） |
| 十 | 配置解析 | TOML round-trip 测试 |
| 十二 | 波及适配 | 策略回归套件（端到端） |

**3.3.2.6 引擎等价性验证——旧引擎作为参照系（oracle）**

这是整个测试体系中最关键的安全网。思路：新旧引擎对同一配置、同一 counter 值，逐抽对比概率分布——完全相同则等价。偏差即 bug。

**为什么比策略回归更强：** 策略回归通过 GDR 指标（`success_probability` 等）间接推断——偏差 < 1% 可能掩盖数值错误。引擎等价性是**逐抽概率向量对比**——一个 counter 值的概率差 0.1% 都能发现。而且旧引擎（P60）已通过全量测试，是 trusted oracle。

**实现文件：`tests/test_p55_equivalence.py`，~100 行：**

```python
"""P55 引擎等价性验证——旧引擎 vs 新引擎，逐抽概率对比。

旧引擎 = P60 交付的 SoftPityBehavior.apply() + PityEngine.apply()（trusted oracle）
新引擎 = P55 SoftStepBehavior._compute_probabilities() + PityEngine.before_draw()

等价条件：对同一配置 + 同一 counter 值（1~200），新旧引擎产出的
概率分布向量偏差 < 1e-6（允许浮点误差）。
"""

import pytest
from gacha_simulator.core.pity import (
    SoftPityBehavior,          # 旧引擎
    SoftStepBehavior,          # 新引擎
    PityEngine, PityState,
    PityDef, PoolPitySpec,
    DrawInfo, PityContext,
)
from types import MappingProxyType


# ── 测试数据：标准 SSR 池 ──
STANDARD_BASE_PROBS = {'ssr': 0.01, 'sr': 0.15, 'r': 0.84}
STANDARD_RARITY_RANK = {'ssr': 0, 'sr': 1, 'r': 2}


def _make_new_ctx(scope='ssr', target_featured=False,
                  base_probs=None, counter=0):
    """构造新引擎的 PityContext。"""
    bp = base_probs or dict(STANDARD_BASE_PROBS)
    draw = DrawInfo(
        pool_id='test', pool_instance_id='test',
        reward_id='', reward_rarity='', is_featured=False,
        scope_cards={'ssr': ('ssr',), 'sr': ('sr',), 'r': ('r',)},
        scope_slots={'ssr': ('ssr',), 'sr': ('sr',), 'r': ('r',)},
        featured_slots={'ssr': ('ssr',)} if target_featured else {},
        base_probabilities=MappingProxyType(bp),
        rarity_rank=STANDARD_RARITY_RANK,
    )
    return PityContext(draw=draw, current=dict(bp), state=PityState())


# ── 等价性测试 ──

class TestEngineEquivalence:
    """新旧引擎逐抽概率等价——旧引擎是 oracle。"""

    @pytest.mark.parametrize('counter', range(1, 201))
    def test_soft_interval_equivalence(self, counter):
        """soft_interval(start=74, end=90) 等价性——200 个 counter 全量对比。

        旧引擎：SoftPityBehavior(start_at=73, end_at=90, func='linear')
        新引擎：SoftStepBehavior(deltas=[[73, 0.0], [17, 100/17]])
        """
        # 旧引擎——P60 已测试正确的实现
        old = SoftPityBehavior(start_at=73, end_at=90, func='linear')
        old_probs = dict(STANDARD_BASE_PROBS)
        old_result = old.apply(counter, old_probs)

        # 新引擎——P55 重构后的实现
        new_bh = SoftStepBehavior(
            'eq_test', PityState(), 'ssr',
            btype='soft_interval',
            deltas=((73, 0.0), (17, 100.0 / 17)),
        )
        new_ctx = _make_new_ctx(counter=counter)
        new_result = new_bh._compute_probabilities(new_ctx, counter)

        # 逐 key 对比
        assert set(old_result.keys()) == set(new_result.keys()), \
            f'counter={counter}: key 集合不同'
        for key in old_result:
            assert old_result[key] == pytest.approx(new_result[key], abs=1e-6), \
                f'counter={counter}, key={key}: old={old_result[key]:.8f} new={new_result[key]:.8f}'

    @pytest.mark.parametrize('counter', [1, 50, 89, 90, 91, 180])
    def test_hard_pity_equivalence(self, counter):
        """hard(threshold=90) 等价性——关键 counter 点对比。

        旧引擎：HardPityBehavior(threshold=90)
        新引擎：HardPityBehavior(scope='ssr', threshold=90)
        """
        old = HardPityBehavior(threshold=90)
        old_probs = dict(STANDARD_BASE_PROBS)
        old_result = old.apply(counter, old_probs) if counter >= 90 else old_probs

        new_bh = HardPityBehavior(
            'eq_test', PityState(), 'ssr',
            btype='hard', threshold=90,
        )
        new_ctx = _make_new_ctx(counter=counter)
        new_result = new_bh._compute_probabilities(new_ctx, counter)

        for key in old_result:
            assert old_result[key] == pytest.approx(new_result[key], abs=1e-6), \
                f'counter={counter}, key={key}: old={old_result[key]:.8f} new={new_result[key]:.8f}'


# ── 删除旧引擎前的最终确认 ──

@pytest.mark.slow
def test_full_simulation_equivalence():
    """端到端等价性——同一 ConfigStore + 同一 seed → 同一 GDR 指标。

    这是删除旧 pity.py 代码前的最后确认。用 run_batch_parallel()
    分别在旧/新引擎上跑 5000 次模拟，比较 success_probability / expected_draws。
    偏差 > 0.1% → 不通过。
    """
    from gacha_simulator.service.batch_simulator import run_batch_parallel
    from gacha_simulator.core.config_store import ConfigStore
    from gacha_simulator.core.gdr import make_gdr_calculator

    # 加载标准配置
    store = ConfigStore()
    store.load_defaults()
    store.rarity_rank = {'ssr': 0, 'sr': 1, 'r': 2}
    store.pity = PityConfig(
        enabled=True,
        pities=[PityDefParsed(
            name='soft1', btype='soft', params={'start': '74', 'end': '90', 'func': 'linear'},
            target_distribution={}, reset_condition='any_ssr', pools='',
        )],
        counter_init={},
    )

    old_result = run_batch_parallel(store, n=5000, seed=42, workers=4,
                                     use_new_engine=False)   # 开关——P55 实施时新增
    new_result = run_batch_parallel(store, n=5000, seed=42, workers=4,
                                     use_new_engine=True)

    for gdr_key in ['success_probability', 'expected_draws']:
        diff = abs(old_result[gdr_key] - new_result[gdr_key])
        assert diff < 0.001, \
            f'{gdr_key}: old={old_result[gdr_key]:.6f} new={new_result[gdr_key]:.6f} diff={diff:.6f}'
```

**这个测试的生命周期：**

```
<!-- REVIEW-R1-FIX: GATE-6-测试策略——每子阶段编码完成后立即运行对应测试，而非集中在阶段十三。 -->
阶段五A（Counter/Flag/DrawInfo）→ pytest tests/ -k "Counter or Flag or DrawInfo" 绿灯
    ↓
阶段五B（_cumulative_boost）    → pytest tests/ -k "cumulative_boost" 绿灯
    ↓
阶段五C（_compute_probabilities）→ pytest tests/ -k "compute_probabilities" 绿灯
    ↓
阶段五D（_on_reset 钩子）       → pytest tests/test_p60_equivalence.py 绿灯（P60 回归）
    ↓
阶段六（TOML 糖展开）           → pytest tests/ -k "expand_soft" 绿灯
    ↓
阶段七（HardPityBehavior）      → pytest tests/ -k "hard_pity" 绿灯
    ↓
阶段八（BEHAVIOR_REGISTRY）     → pytest tests/ -k "registry" 绿灯
    ↓
阶段九（排序+校验）             → pytest tests/ -k "resolve_order or validate" 绿灯
    ↓
阶段十A（PityDef 扁平化）       → pytest tests/ -k "pity_def or build_pity" 绿灯
    ↓
阶段十B（旧格式迁移）           → pytest tests/ -k "legacy or migrate" 绿灯
    ↓
阶段十一（UI 元数据驱动）       → GUI 手动冒烟（type 切换显隐+联动校验+deltas 表格+保存读回）
    ↓
<!-- REVIEW-R1-FIX: GATE-6-测试策略——阶段十二拆为 4 个子阶段，每子阶段有独立 pytest 验收子集。 -->
阶段十二A-1（PityEngine 构造签名）→ pytest tests/ -k "pity_engine or import" 绿灯（18处调用方零TypeError）
    ↓
阶段十二A-2（GachaService 聚合）  → pytest tests/ -k "gacha_service" 绿灯（AUDIT-BREAK-8 端到端）
    ↓
阶段十二A-3（worst_impact 适配）  → pytest tests/ -k "worst_impact" 绿灯
    ↓
阶段十二A-4（retreat+vuln+桥接）  → pytest tests/ -k "retreat or vulnerability" 绿灯
    ↓
阶段十二B-C（辅助+CLI）          → pytest tests/ --co 全量（新增+已有）绿灯
    ↓
<!-- REVIEW-R1-FIX: GATE-6-测试策略——阶段十三为「汇总回归」而非「首次测试」。 -->
阶段十三A-C（汇总回归+增量用例）→ pytest tests/ --cov 全量绿灯；新增 ≥20 用例验证通过
    ↓
删除旧 SoftPityBehavior / HardPityBehavior → 删除旧测试
    ↓
以后只有新引擎测试（§3.3.2.2-3.3.2.4）
```

<!-- REVIEW-R1-FIX: GATE-6-测试策略——关键变更为每子阶段编码后立即 pytest，而非等到阶段十三首次运行。
     原设计有 12 阶段回归窗口过长风险。每个实施阶段表行中已标注对应的 pytest 命令。-->

**关键设计决策：** `run_batch_parallel()` 新增 `use_new_engine=False` 参数——P55 实施期间默认为 False（走旧引擎），测试中用 True（走新引擎）。阶段十二验证通过后，默认值改为 True，旧引擎代码删除。

### 3.4 实施阶段

> 原 Phase 1-4（平台层）和微型任务已提取至 [P60](../../../02-待办/P60%20基础平台——依赖消除与下游并行化.md)。以下为 P55 保留的实施阶段。

| 阶段 | 内容 | 文件 | 预估工时 |
|------|------|------|:---:|
<!-- REVIEW-R1-FIX: GATE-1-变更粒度——阶段五拆分为 4 个子阶段（原单阶段约3h，现每子阶段≤50min） -->
| **阶段五A** | Counter / Flag 遥控器单元测试验证 + `DrawInfo` frozen 确认——`Counter.incr()`/`value()`/`reset()`/`reached()` 行为等价直接操作 `PityState`；`Flag.set()`/`clear()`/`is_set()` 正确隔离；`DrawInfo(frozen=True)` 误写编译报错。<!-- REVIEW-R1-FIX: GATE-6-测试策略——阶段五A 编码完成后立即运行 `pytest tests/core/test_pity.py -k "Counter or Flag" -v`，确认无回归。 --> | `pity.py` / `tests/` | 25min |
| **阶段五B** | `SoftStepBehavior._cumulative_boost()` 独立实现——遍历 RLE deltas、按 counter 定位当前段、min(boost, 100.0) 封顶。含 6 项单元测试（deltas 为空/counter=0/counter 超出所有段/counter 在首段内/counter 跨越两段/prefix 段增量非零）。<!-- REVIEW-R1-FIX: GATE-6-测试策略——阶段五B 编码完成后立即运行 `pytest tests/core/test_pity.py -k "cumulative_boost" -v`。 --> | `pity.py` / `tests/` | 30min |
| **阶段五C** | `SoftStepBehavior._compute_probabilities()` 实现——scope 槽位定位 + `target_featured` 收窄 + 跨稀有度重分配 + 稀有度层级保护 + 按基础权重比例分配。含 4 项概率分配单元测试（target_featured=true/false、scope_slots 为空、non_target 为空）。具体输入/期望输出见 §7 阶段五验收样例。<!-- REVIEW-R1-FIX: GATE-6-测试策略——阶段五C 编码完成后立即运行 `pytest tests/core/test_pity.py -k "compute_probabilities" -v`。 --> | `pity.py` / `tests/` | 30min |
| **阶段五D** | `CounterBasedBehavior.after_draw()` 插入 `_on_reset()` 钩子——修改 P60 已交付代码（`pity.py:269-278`），在 `_should_reset(ctx)` 检查之后、默认重置流程之前插入 `if self._on_reset(ctx): return`。`HardPityBehavior._on_reset()` 覆写钩子（deactivate_on_early_hit 支持）。<!-- REVIEW-R1-FIX: GATE-6-测试策略——阶段五D 编码完成后立即运行 `pytest tests/core/test_p60_equivalence.py -v`（P60 等价性测试全量），确认 hook 插入无回归。 --> | `pity.py` / `tests/` | 20min |
| **阶段六** | TOML 糖展开 `_expand_soft_to_deltas()`——`soft_interval`（start/end → deltas）/ `soft_additive`（start/increment → deltas）（~15 行）<!-- REVIEW-R1-FIX: GATE-6-测试策略——阶段六编码完成后立即运行 `pytest tests/core/test_config_toml.py -k "expand_soft" -v`。 --> | `config_toml.py` / `tests/` | 20min |
| **阶段七** | `HardPityBehavior` scope 化——继承 `CounterBasedBehavior` | `pity.py` | 15min |
| **阶段八** | BEHAVIOR_REGISTRY 条目更新——`soft_interval` / `soft_additive` / `soft_step` / `hard` + 事件驱动 6 种参数元数据完整化（事件驱动类 = `None` stub——P56 交付）。<!-- REVIEW-R1-FIX: GATE-6-测试策略——阶段八编码完成后立即运行 `pytest tests/core/test_pity.py -k "registry" -v`（含 registry 自检函数），确认 10 种 type 均可正确路由。 --> | `pity.py` / `tests/` | 25min |
| **阶段九** | `_resolve_order()` 自动排序 + `_validate_behaviors()` 校验<!-- REVIEW-R1-FIX: ISSUE-037 -->（含 name 重名第二道防线——PityEngine 层拦截编程接口绕过的重名）<!-- REVIEW-R1-FIX: GATE-6-测试策略——阶段九编码完成后立即运行 `pytest tests/core/test_pity.py -k "resolve_order or validate" -v`。 --> | `pity.py` / `tests/` | 25min |
<!-- REVIEW-FIX-PREV: ISSUE-GATE-1 -->
<!-- REVIEW-R1-FIX: GATE-1-变更粒度——阶段五原单阶段约3h（DrawInfo frozen 验证+Counter/Flag+~60行核心算法+_on_reset()钩子插入 P60代码），现拆为 4 个子阶段。 -->
<!-- GATE-1 修复：阶段十/十一/十二/十三超过 1 小时单人完成上限，拆分为细粒度子阶段。 -->
<!-- 阶段十二原描述仅一行，现按波及文件逐文件拆解具体需修改的函数和改动范围。 -->

| 阶段 | 内容 | 文件 | 预估工时 |
|------|------|------|:---:|
| **阶段十A** | `PityDef` 扁平字段重构——17 个独立类型字段替换旧 `PityDefParsed`（含 `params` dict），`counter_init` 从 `PityConfig` 移至 `PityDef`。`_build_pity_def()` 适配新字段（type/scope/target_featured/deltas/threshold 等）+ scope 注册校验（`rarity_rank_map` 键统一 `.lower()` 归一化——ISSUE-023）+ `counter_init` 解析透传。<!-- REVIEW-R1-FIX: ISSUE-037 -->**ISSUE-037：name 字段非空校验（strip+ConfigError）+ `_build_pity()` 返回前全量重名校验（TOML 层第一道防线）。**<!-- REVIEW-R1-FIX: ISSUE-038 -->**ISSUE-038：deltas 内层 tuple 化**——`tuple(tuple(seg) for seg in _expand_soft_to_deltas(raw))`，保证 `tuple[tuple[int, float], ...]` 完全不可变，与类型注解一致。 | `config_store.py` / `config_toml.py` | 35min |
| **阶段十B** | 旧格式自动迁移——`_is_legacy_format()` 检测（start/end/func/reset 旧字段）+ `_migrate_legacy_pity()` 15+ 字段映射（含 `func='exp'/'step'` → ConfigError）+ `_build_toml_pity()` 写路径（round-trip 可逆）+ `_deltas_to_soft_interval()` 反向还原。<!-- REVIEW-R1-FIX: ISSUE-039 -->**迁移后自动保存策略（ISSUE-039——§3.3.1 迁移后自动保存策略）：** `ConfigStore._migrated_from_legacy` 标记字段 + GUI 路径自动保存（检测标记→弹出确认→`save_toml()`）+ CLI `--migrate` 参数。**含独立测试面：** 旧格式 → 迁移 → 新格式 → 写回 → 再读 → 等价性校验（至少 5 条迁移规则逐一覆盖）+ `_migrated_from_legacy` 标记往返测试 | `config_toml.py` / `tests/` | 65min |
| **阶段十一A** | 动态控件工厂——`_build_param_widgets(ui_params, current_values)` 根据 `BEHAVIOR_REGISTRY` 中 `ui_params` 元数据生成 PyQt 控件（QSpinBox/QDoubleSpinBox/QCheckBox/QComboBox），替换旧硬编码 5 个控件。`_connect_dynamic_signals()` 批量连接 valueChanged/stateChanged → `_update_preview`。`_on_type_changed(new_type)` 遍历 `active_keys` 集合自动显隐控件 + `_apply_cross_checks()` 联动校验（rotating 家族强制勾选 target_featured、hard+sr/r 禁用 target_featured、deactivate_on_early_hit 仅 hard 可用） | `config_panel.py` | 40min |
| **阶段十一B** | deltas 表格编辑器——仅 `soft_step` 选中时渲染 QTableWidget（2 列：抽数/增量），行可增删。保存时读取表格行 → 序列化为 `deltas` 数组。`soft_interval`/`soft_additive` 选中时不渲染此表格——参数通过 spinbox 编辑，保存时由 `_expand_soft_to_deltas()` 展开 | `config_panel.py` | 25min |
| **阶段十一C** | `get_config()` + `_do_update_preview()` 适配——pity 节点改为输出 `List[PityDef]` 序列化格式（每条目含 name/btype/scope/target_featured/deltas/threshold/counter_init 等新字段），移除顶层 type/start/end 旧字段。预览文本遍历 pity 列表逐条展示摘要行——格式：`{btype}({scope})` + 关键参数。可选附加 `pities_summary` 预格式化文本列表 | `config_panel.py` | 30min |
<!-- REVIEW-R1-FIX: GATE-1-变更粒度——阶段十二A 原70min覆盖3文件+18处调用方，拆为4个子阶段（十二A-1至十二A-4），每子阶段≤30min、可独立验证。 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-6 -->
| **阶段十二A-1** | **PityEngine 构造签名批量同步（最阻塞项——18处调用方一次性适配）：** (a) `batch_simulator.py`——`_build_pity_engine_from_gui()` **全量重写（旧逻辑约120行全部删除——含 `_resolve_targets` 30行）**: 遍历 `PoolEntry.distribution` 预计算 `scope_slots`/`featured_slots`/`scope_cards`，传入 `List[PityDef]`+`PityState` 调用 `PityEngine` 新构造函数（移除 `behaviors` 参数，新增 `state`）；`SimulationEnvBuilder._build_pool_pity_spec()` 从 `PoolEntry.distribution` 预计算（约30行——ISSUE-032）；同步修复 `SimulationEnvBuilder.from_config_store()` 行602-618 `pity_cfg_dict` 构建逻辑（AUDIT-BREAK-5）；(b) `worst_impact.py`——`_build_pity_engine()` 适配新签名（移除 behaviors，新增 state），虚拟池从参考池子 `PoolEntry.distribution` 预计算（AUDIT-BREAK-18）；(c) `test_pity.py` 6处 + `test_p60_equivalence.py` ~10处构造签名批量同步（AUDIT-BREAK-27）。**验收：`pytest tests/ -k "import"` 零 TypeError。** | `batch_simulator.py` / `worst_impact.py` / `tests/` | 30min |
| **阶段十二A-2** | **GachaService 概率聚合 + 签名适配 + 检测链修复：** (a) `before_draw()` 调用前按稀有度聚合 probabilities（AUDIT-BREAK-8——§0.3方案A——`_aggregate_probs_by_rarity()` + `_get_rarity()` 约25行）；(b) `after_draw()` 第3参数从 `reward.id`(str) 改为 `reward`(Reward对象)，新增第4参数 `base_probabilities`（AUDIT-BREAK-9）；(c) 行196-214 `pity_triggered` 检测链适配（ISSUE-035——§0.8）：行201 `_pity_engine.behaviors.get(pname)` → `_pity_engine.is_active(pname)`，行205 `behavior.is_active(cv)` → 同上，行209-214 `pity_state.get(pname, 'counter', 0)` → `_pity_engine.get_counter(pname)`，行189-194 初步检测在 AUDIT-BREAK-8 修复后同步替换为 rarity-keyed 比较。**验收：`pytest tests/ -k "gacha_service" -v`（若存在）或手动端到端验证——见 §7 阶段十二A-2 补充验收标准。** | `gacha_service.py` | 25min |
| **阶段十二A-3** | **worst_impact.py 内部适配（类名替换+硬编码修复）：** (a) 类名替换——`SoftPityBehavior`→`SoftStepBehavior`、`HardPityBehavior`→`HardPityBehavior`（全量搜索替换）；(b) `_get_initial_pity_state()` counter_init 读取修正——从 `store.pity.counter_init` 改为遍历 `store.pity.pities` 读取每个 `PityDef.counter_init`（AUDIT-BREAK-19）；(c) `_get_pity_cost()` 行340-354 适配（ISSUE-036——§0.9）：`p.params.get('end', '90')` → 从 P55 新字段推导 end 值（`p.threshold` / `deltas` 总抽数 / `p.soft_end` / 兜底 90），同时改为遍历所有 `PityDef` 取最大 end 值替代仅读 `pities[0]`；同步删除 `_resolve_targets_for_pool()` 函数（约21行——ISSUE-029）。**验收：`pytest tests/ -k "worst_impact" -v`。** | `worst_impact.py` | 25min |
| **阶段十二A-4** | **retreat_config + vulnerability + 桥接代码清理：** (a) `retreat_config.py`——PityDef 构造适配 17 字段新格式 + PityConfig 移除 counter_init 参数（AUDIT-BREAK-31——§0.11）。若遗漏则 RetreatSearchEngine 的配置裁剪器断裂，阻断整个撤退搜索流程；(b) `vulnerability.py`——`PityState.data` 重命名为 `_data`，第 611 行 `for cname in ps.data:` 改为通过 `PityEngine.get_state_summary()` 或 `ps._data` 访问（ISSUE-030）；(c) 桥接代码清理——`PoolPitySpec.resolved_targets` 字段（`pity.py:498-502`）+ `_resolve_targets()`（`batch_simulator.py` ~30行）+ `_resolve_targets_for_pool()`（`worst_impact.py` ~21行）+ `PityEngine` 中 2 处桥接调用（`pity.py:498-502 / 538-542`）全部删除（ISSUE-029）。**验收：`pytest tests/ -k "retreat or vulnerability" -v` + `grep -r "resolved_targets" gacha_simulator/` 返回零结果。** | `retreat_config.py` / `vulnerability.py` / `pity.py` / `batch_simulator.py` / `worst_impact.py` | 25min |
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-6 -->
| **阶段十二B** | **辅助适配（轻量——独立于十二A，可并行）：** (a) `strategy.py`——检查 `StrategyContext` 是否引用 `PityState` 内部属性，改为通过 `PityEngine` 公共查询接口；(b) `process_analysis.py`——检查 pity 事件类型是否需要更新；(c) `process_trace.py`——同上；(d) `streaming.py`——同上；(e) `collector.py`——检查是否引用 pity 相关结构 | `strategy.py` / `process_analysis.py` / `process_trace.py` / `streaming.py` / `collector.py` | 20min |
| **阶段十二C** | **CLI + 配置示例：** (a) `cli.py`——检查是否构造 PityEngine，适配新签名；<!-- REVIEW-R1-FIX: ISSUE-039 -->**ISSUE-039：新增 `--migrate` CLI 参数**（检测 `_migrated_from_legacy` 标记 → `save_toml()` 覆盖旧文件）；(b) `config/config.toml`——`[[pity]]` 节使用新语法（soft_interval/soft_additive/hard 各至少一条示例）；(c) `core/__init__.py`——更新导出符号 | `cli.py` / `config.toml` / `__init__.py` | 25min |
| **阶段十三A** | **新增 pity 专项测试 ≥20 用例：** 覆盖——(a) `SoftStepBehavior._cumulative_boost()` 边界条件 6 项（deltas 为空、counter=0、counter 超出所有段、counter 在首段内、counter 跨越两段、prefix 段增量非零）；(b) `SoftStepBehavior._compute_probabilities()` 概率分配 4 项（target_featured=true/false、scope_slots 为空、non_target 为空）；(c) `HardPityBehavior._compute_probabilities()` 阈值行为 4 项（未达阈值不干预、达到阈值强制 100%、scope_slots 为空、deactivate_on_early_hit）；(d) `_should_reset()` 重置条件 4 项（reward_rarity 不匹配、target_featured=true+非 featured 不重置、target_featured=false+任意出货重置、target_featured=true+featured 出货重置）；(e) 同 pool 两 behavior 同 scope 不同 name → 计数器独立 2 项 | `tests/` | 55min |
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-27 -->
| **阶段十三B** | **现有测试适配（AUDIT-BREAK-27 约16处构造签名变更）：** (a) `test_pity.py:161/213/224/233/260/285` 共6处——`PityEngine(pool_specs, pity_defs, behaviors)` → `PityEngine(pool_specs, pity_defs, state)`（移除 `behaviors` 参数，新增 `state: PityState`）；(b) `test_p60_equivalence.py:66/71/119/123/165/169/203/247/251/300` 约10处——同上；(c) 7 种策略集成测试（`smart`/`pool_quota`/`pity_reserve`/`stop_on_target`/`target_hunting`/`fixed_count`/`draw_target`）在保底重构后行为无退化——至少 7 条集成测试逐一通过；(d) `PityState` 序列化往返测试（`to_dict()`→`from_dict()`——含三层嵌套 namespace、空 state、含多个 behavior 的 state）。**遗漏适配→导入时 TypeError。** | `tests/` | 35min |
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-27 -->
| **阶段十三C** | **文档更新（按波及表 §4.3 5 个文件）：** (a) `subsystems/保底系统/01-理论.md`——加入独立化设计 + 新 type/scope 理论；(b) `subsystems/保底系统/02-实施.md`——反映新类结构和上下文模型；(c) `subsystems/保底系统/04-问题.md`——缺陷状态同步；(d) `CLAUDE.md`——保底节（Behavior 类名/BEHAVIOR_REGISTRY 条目/PityEngine 签名/CounterBasedBehavior API）、策略节（PityEngine 5 个语义查询方法）、GDR 节（PityState 属性名）、并行模拟入口（`_build_pity_engine_from_gui()` 重写）；(e) `subsystems/保底系统/05-笔记.md`——H4 自动维护 | `docs/` | 25min |
<!-- /REVIEW-FIX-PREV: ISSUE-GATE-1 -->

## 四、波及范围

### 4.1 核心改动

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/pity.py` | **重构** | 两种 counter behavior（`SoftStepBehavior` / `HardPityBehavior`）+ BEHAVIOR_REGISTRY 条目更新（4 种 counter + 6 种事件驱动）+ `_resolve_order()` + `_validate_behaviors()`。<!-- REVIEW-FIX-PREV: ISSUE-022 -->**`PoolPitySpec` 新增 `scope_cards: Dict[str, tuple[str, ...]]`（ISSUE-008）、`scope_slots: Dict[str, tuple[str, ...]]` 和 `featured_slots: Dict[str, tuple[str, ...]]` 字段（ISSUE-001 / ISSUE-002）——`PoolPitySpec` 定义在 `pity.py:386-391`，非 `config_store.py`。**<!-- /REVIEW-FIX-PREV: ISSUE-022 --> |
| `core/config_store.py` | **修改** | `PityDef` 扁平化重构：17 个独立类型字段（无 `params` dict、无 `LifecycleConfig` 嵌套），`counter_init` 从 `PityConfig` 移至 `PityDef`。`rarity_rank` 字段（P60 已交付 `_parse_rarities()`——键为大写，在传入 `_build_pity()` 前需 `.lower()` 归一化——ISSUE-023） |
| `core/config_toml.py` | **修改** | `[rarities]` 解析 + `_build_pity()` 适配新字段（`type`/`scope` 等）+ scope 注册校验 + `counter_init` 透传 + 旧格式自动迁移（`_migrate_legacy_pity()`——ISSUE-006）。`_build_draw_info()` 基于现有 `List[PoolDistEntry]` 分组，不新增 DistributionTemplate 类（ISSUE-004 决策 B） |
<!-- REVIEW-R1-FIX: ISSUE-052 -->
| `core/__init__.py` | **修改** | **更新导出符号（具体增删清单）。** P55 后需要：(1) **新增导出**——`SoftStepBehavior`、`CounterBasedBehavior`、`PityContext`、`DrawInfo`、`Counter`、`Flag`、`LifecycleConfig`、`BEHAVIOR_REGISTRY`、`create_behavior`；(2) **移除导出**——`SoftPityBehavior`（被 `SoftStepBehavior` 替代）、`PityDefParsed`（被 `config_store.PityDef` 替代）；(3) **新增跨模块导入**——从 `config_store` 导入 `PityDef`（旧 `PityDefParsed` 定义在 `pity.py` 内部，新 `PityDef` 在 `config_store.py`）；(4) **类签名变更**——`HardPityBehavior` 继承 `CounterBasedBehavior` 而非旧 `PityBehavior`（不影响 import 但影响类型提示和 IDE 补全）。**具体变更对照：**

```python
# 当前 __init__.py（约行7-11）：
from .pity import (
    PityBehavior, SoftPityBehavior, HardPityBehavior,
    PityDefParsed, PoolPitySpec,
    PityState, PityEngine,
)

# P55 后：
from .pity import (
    PityBehavior, CounterBasedBehavior, SoftStepBehavior, HardPityBehavior,
    PoolPitySpec, PityState, PityEngine,
    PityContext, DrawInfo, Counter, Flag, LifecycleConfig,
    BEHAVIOR_REGISTRY, create_behavior,
)
from .config_store import PityDef  # 替代旧 PityDefParsed
```

| 符号 | P55 动作 | 说明 |
|------|:---:|------|
| `SoftStepBehavior` | **新增** | 替代 `SoftPityBehavior` |
| `CounterBasedBehavior` | **新增** | ABC 基类——所有 counter 驱动保底的父类 |
| `PityContext` | **新增** | 管道中流转的可变载体 |
| `DrawInfo` | **新增** | frozen dataclass——抽卡静态事实 |
| `Counter` | **新增** | 遥控器——封装 PityState 计数器读写 |
| `Flag` | **新增** | 遥控器——封装 PityState 布尔标志读写 |
| `LifecycleConfig` | **新增** | 跨 type 生命周期参数 dataclass |
| `BEHAVIOR_REGISTRY` | **新增** | 全局注册表——type → 类 + 参数元数据 |
| `create_behavior` | **新增** | 工厂函数——零 if-else 创建 behavior 实例 |
| `PityDef` | **新增跨模块** | 从 `config_store` 导入（替代旧 `PityDefParsed`，后者仅在 `pity.py` 内定义） |
| `SoftPityBehavior` | **移除** | 被 `SoftStepBehavior` 替代 |
| `PityDefParsed` | **移除** | 被 `config_store.PityDef` 替代 |

**遗漏任一项 → 下游 `import` 错误。** 实施时需同步更新 `__all__` 列表。
<!-- /REVIEW-R1-FIX: ISSUE-052 -->

### 4.2 波及适配

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `service/batch_simulator.py` | 适配 | PityEngine 构造参数变化——从传入预构建 behaviors dict 改为传入 `List[PityDef]` + `PityState`（ISSUE-007）。`_build_pity_engine_from_gui()` 内部删除手动构造 `SoftPityBehavior`/`HardPityBehavior` 实例的逻辑。<!-- REVIEW-FIX-PREV: ISSUE-029 -->**同步清理：** `_resolve_targets()` 函数（约 167-188 行）在桥接代码删除后不再被消费——随阶段十二一并移除。<!-- /REVIEW-FIX-PREV: ISSUE-029 --><!-- REVIEW-FIX-PREV: AUDIT-BREAK-5 -->**【AUDIT-BREAK-5】`SimulationEnvBuilder.from_config_store()` 行602-618 构造 `pity_cfg_dict` 时访问已不存在的字段：** `pd.params`（分裂为多个独立字段）、`pd.target_distribution`（`scope`+`target_featured` 替代）、`pd.reset_condition`（`target_featured` 推导）、`pd.pools`（类型从 `str` 变为 `tuple[str,...]`）。`pity_cfg_dict` 构建逻辑需完全重写以适配新 `PityDef`。其消费方（如 `_build_pity_engine_from_gui()` 从 `pity_cfg_dict` 读取）也需同步适配。**建议：将 `pity_cfg_dict` 构建与 `_build_pity_engine_from_gui()` 重写放在同一阶段完成。**<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-5 --> |
| `service/gacha_service.py` | 适配 | PityEngine 构造参数变化——从传入预构建 behaviors dict 改为传入 `List[PityDef]` + `PityState`（ISSUE-007）。<!-- REVIEW-FIX-PREV: AUDIT-BREAK-8 -->**【CRITICAL】AUDIT-BREAK-8：`run_simulation_compact()` 行176 构造 `probabilities = {r.id: p for r, p in pool.rewards}`——key 为卡牌 ID（`'limited_ssr_1'`），但 `scope_slots['ssr']` = `('ssr',)`（稀有度名）。`SoftStepBehavior._compute_probabilities()` 中 `result.get('ssr', 0.0)` 始终返回 0.0——pool=0→不偷概率→所有保底概率调整静默失效。修复：在 `before_draw()` 调用前将 probabilities 按稀有度聚合为 `{rarity: sum_probs}` 格式。详见 §0.3。**<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-8 --><!-- REVIEW-FIX-PREV: AUDIT-BREAK-9 -->**`after_draw()` 签名变更（AUDIT-BREAK-9）：** 第3参数从 `reward.id`(str) 改为 `reward`(Reward对象)，新增第4参数 `base_probabilities`。详见 §3.2.1 的 AUDIT-BREAK-9 修正。<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-9 --><!-- REVIEW-R1-FIX: ISSUE-035 -->**【ISSUE-035】`run_simulation_compact()` 行196-214 `pity_triggered` 检测链适配：** 行201 `_pity_engine.behaviors.get(pname)`（`behaviors` dict 已移除）→ 替换为 `_pity_engine.is_active(pname)`（Flag-based 查询）；行205 `behavior.is_active(cv)`（P55 后始终返回 `False`）→ 同上替换；行209-214 `pool_counter_max` 计算读取 `pity_state.get(pname, 'counter', 0)` → 迁移到 `_pity_engine.get_counter(pname)`（单一访问入口）。行189-194 `pity_triggered` 初步检测（比较概率变化）在 AUDIT-BREAK-8 修复后也需同步替换为 rarity-keyed 比较。详见 §0.8。<!-- /REVIEW-R1-FIX: ISSUE-035 --> |
| `service/batch_simulator.py` | **修改** | `SimulationEnvBuilder` 需在构建 `PoolPitySpec` 时从 `PoolEntry.distribution: List[PoolDistEntry]` 预计算 `scope_slots` / `featured_slots` / `scope_cards`（按稀有度分组槽位 ID + 过滤 featured=true）——ISSUE-002 / ISSUE-008。**注意：SimulationEnvBuilder 类定义在 batch_simulator.py（约第 510 行），不存在独立的 env_builder.py 文件**<!-- REVIEW-FIX-PREV: ISSUE-003 --> |
| `core/worst_impact.py` | 适配 | 直接实例化 `SoftPityBehavior`/`HardPityBehavior` → 更新类名引用。<!-- REVIEW-FIX-PREV: ISSUE-029 -->**同步清理：** `_resolve_targets_for_pool()` 函数（约 501-526 行）在桥接代码删除后不再被消费——随阶段十二一并移除。<!-- /REVIEW-FIX-PREV: ISSUE-029 --><!-- REVIEW-FIX-PREV: AUDIT-BREAK-18 -->**【AUDIT-BREAK-18】虚拟池 ID（`_worst_impact_pool_{idx}`）无 `PoolEntry.distribution`：** 无法预计算 `scope_slots`/`featured_slots`/`scope_cards` → `PoolPitySpec` 三个字段为空 → `_build_draw_info()` 方案 B 兜底。但方案 B 需要 `Reward.extra_info` 含 `rarity`/`featured` 键 → worst_impact 构造虚拟 Reward 时需同步添加此信息（当前 `worst_impact.py:385` 已携带 `extra_info={'rarity': ..., 'featured': ...}`——需确认 `_build_pity_engine()` 中新构造的虚拟 Reward 也携带）。**更优方案：从参考池子的 `PoolEntry.distribution` 获取并预计算。**<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-18 --><!-- REVIEW-FIX-PREV: AUDIT-BREAK-19 -->**【AUDIT-BREAK-19】`_get_initial_pity_state()` 行573 `getattr(self.store.pity, 'counter_init', {})` → `PityConfig` 无此字段 → 总是返回默认值 `{}`。** 需改为遍历 `store.pity.pities` 读取每个 `PityDef.counter_init`：`{pdef.name: pdef.counter_init for pdef in store.pity.pities}`。<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-19 --><!-- REVIEW-R1-FIX: ISSUE-036 -->**【ISSUE-036】`_get_pity_cost()` 行340-354 访问 `p.params` 断裂：** `p.params` dict 在 P55 后不存在（扁平化为独立字段）→ `AttributeError`。修复：改为从 P55 新字段推导 end 值（`p.threshold` / `deltas` 总抽数 / `p.soft_end` / 兜底 90）。此行在 `prepare_simulation_config()` 流程中被调用，阻断整个 worst_impact 分析。同时该方法仅读取 `pities[0]` 第一条——多保底场景语义不准确，修复时一并改为遍历所有 `PityDef` 取最大 end 值。详见 §0.9。**波及：** `_compute_pity_coverage()` 调用点（行325-327）。<!-- /REVIEW-R1-FIX: ISSUE-036 --> |
<!-- REVIEW-FIX-PREV: ISSUE-030 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-17 -->
| `core/vulnerability.py` | **适配** | `PityState.data` 重命名为 `_data`（私有属性）——第 611 行 `for cname in ps.data:` 需改为通过 `get_state_summary()` 公共 API 或直接的 `ps._data` 访问。**建议优先使用 `PityEngine.get_state_summary()` 公共 API**（§3.2 策略层读接口），避免直接访问 PityState 内部属性。若直接访问，改为 `for cname in ps._data:`。**AUDIT-BREAK-17 确认：`PityEngine.get_state_summary()`（行611）中 `self._state.data.items()` 也需改为 `self._state._data.items()`。** |
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-17 -->
<!-- /REVIEW-FIX-PREV: ISSUE-030 -->
| `core/strategy.py` | 检查 | `StrategyContext` 是否引用 `PityState` |
| `core/process_analysis.py` | 检查 | pity 事件类型是否需要更新 |
| `core/process_trace.py` | 检查 | 同上 |
| `core/streaming.py` | 检查 | 同上 |
| `core/collector.py` | 检查 | 是否引用 pity 相关结构 |
| `gui/config_panel.py` | **修改** | `_setup_pity_config()` UI 重构——见下方 UI 适配说明。<!-- REVIEW-FIX-PREV: AUDIT-BREAK-20 -->**【AUDIT-BREAK-20】动态控件信号连接：** `_connect_dynamic_signals()` 必须为每个动态生成的控件连接 `valueChanged`/`stateChanged`→`_update_preview`。若遗漏——用户修改参数后预览文本不刷新。<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-20 --><!-- REVIEW-FIX-PREV: AUDIT-BREAK-21 -->**【AUDIT-BREAK-21/22】get_config() + _do_update_preview() 同步适配：** 旧消费者读取 `config['pity']['type']`/`['start']`/`['end']`→KeyError。建议过渡期同时输出新旧两种格式——新格式为主，旧格式字段保留但标记 deprecated。<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-21 --><!-- REVIEW-FIX-PREV: AUDIT-BREAK-23 -->**【AUDIT-BREAK-23/24】counter_init 读写断裂：** 行2269 `dict(store.pity.counter_init)`→AttributeError；行2921 `store.pity.counter_init = {...}`→AttributeError；行3037 `store.pity.counter_init.get(p.name,0)`→需改为 `p.counter_init`。见 §0.5 修复表。<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-23 --> |
| `gui/gacha_panel.py` | 检查 | 可能引用 pity 配置 |
| `gui/analysis_panel.py` | 检查 | 可能引用 pity 事件 |
| `gui/process_analysis_panel.py` | 检查 | 同上 |
| `gui/worst_impact_panel.py` | 检查 | 同上 |
| `gui/retreat_search_panel.py` | 检查 | 同上 |
| `cli.py` | 检查 | 是否构造 PityEngine |
| `config/config.toml` | **更新** | `[[pity]]` 节使用新语法 |
<!-- REVIEW-R1-FIX: ISSUE-050 -->
| `core/retreat_config.py` | **适配** | **【AUDIT-BREAK-31】PityDef 构造 + PityConfig.counter_init 双断裂：** (a) 行67-74 构造旧格式 `PityDef`（5字段 `name`/`btype`/`params`/`target_distribution`/`reset_condition`/`pools` 全部移除）→ 改为 P55 17字段新格式或直接 shallow-copy 引用 `original_store.pity.pities` 中已有的 `PityDef` 对象；(b) 行75 `counter_init=dict(pity_counter_init)` 传入 `PityConfig()` → `TypeError: unexpected keyword argument 'counter_init'`——移除该参数，改为返回前遍历 `pities` 逐条写入 `PityDef.counter_init`。详见 §0.11。此文件是 `RetreatSearchEngine` 的配置裁剪器——断裂阻断整个撤退搜索流程。 |
<!-- /REVIEW-R1-FIX: ISSUE-050 -->
<!-- REVIEW-R1-FIX: ISSUE-053 -->
| `scripts/profile_sim.py` | **检查** | 行86-89 通过 `env.pity_engine` 间接依赖 `PityEngine`（构造时传入 `GachaService`）。不直接构造 `PityEngine`——通过 `SimulationEnvBuilder.from_config_store()` 标准路径间接构造。若 builder 适配正确则无需修改。但若 `SimulationEnv` 的 `pity_engine` 字段初始化时序或类型在 P55 中变化（如 state 参数需在 Engine 构造前完成 counter_init 写入——AUDIT-BREAK-29），此脚本的 env 构建路径可能受波及。**建议：** 在阶段十二后执行一次完整 profile 脚本运行确认无 TypeError。 |
<!-- /REVIEW-R1-FIX: ISSUE-053 -->
<!-- REVIEW-R1-FIX: ISSUE-054 -->
| `core/generalized_drop_rate.py` | **检查** | 行72-76 `PityProgressAtT` 导入 `PityState` 并使用 `PityState.from_dict()` 反序列化后调用 `ps.get(self.counter_name, 'counter', 0)`。此路径使用稳定的公共 API（`from_dict` + `get`），不访问内部 `._data` 属性——P55 后无断裂风险。**但若 `PityState.from_dict()` 或 `get()` 签名在 P55 中意外变更，此文件可能静默失效。** 建议加入波及检查清单，实施后运行 GDR 计算确认 PityProgressAtT 指标无异常。 |
<!-- /REVIEW-R1-FIX: ISSUE-054 -->
| `scripts/profile_simulation.py` | **检查** | 行97-99 同 `profile_sim.py`——通过 `SimulationEnvBuilder.from_config_store()` 间接依赖。与 `profile_sim.py` 相同的检查路径。 |

### 4.3 文档

<!-- REVIEW-FIX-PREV: ISSUE-009 -->
| 文件 | 改动 |
|------|------|
| `subsystems/保底系统/01-理论.md` | 更新——加入独立化设计 + 新 type/scope 理论 |
| `subsystems/保底系统/02-实施.md` | 更新——反映新类结构和上下文模型 |
| `subsystems/保底系统/04-问题.md` | 更新——缺陷状态同步 |
| `subsystems/保底系统/05-笔记.md` | H4 自动维护 |
| `CLAUDE.md` | **新增（ISSUE-009）**——受 P55 影响的节：(1) **保底节**——Behavior 类名（`SoftPityBehavior`→`SoftStepBehavior` 等）、`BEHAVIOR_REGISTRY` 条目（从 5 条 stub 到 10 条含类引用）、`PityEngine` 签名（`behaviors` 参数移除，新增 `state`）、`CounterBasedBehavior` API（`reset` 参数移除）；(2) **策略节**——`PityEngine` 新增 5 个语义查询方法（`get_counter()`/`is_guaranteed()` 等）；(3) **GDR 节**——`PityState.data` 属性名（非 `_data`——当前 `pity.py:398` 为 `data`，GDR 调用规范需同步）；(4) **并行模拟入口**——`_build_pity_engine_from_gui()` 函数全量重写 |

### 4.4 UI 适配

#### 4.4.1 通用控件（所有 type）

| 控件 | 类型 | 来源 | 说明 |
|------|:---:|------|------|
| `type` | 下拉框 | `BEHAVIOR_REGISTRY` 所有条目 | 选项：10 种 type。切换时动态显隐下方专属控件 |
| `scope` | 下拉框 | `ConfigStore.rarity_ranks` | 仅稀有度名（`ssr`/`sr`/`r`），无 `featured` |
| `target_featured` | 复选框 | — | 默认不勾选。rotating 家族禁用并强制勾选 |
| `pools` | 文本编辑 | — | 池子名，逗号分隔 |
| `counter_init` | QSpinBox | — | 0–200，默认 0。仅 counter 驱动型（soft_*/hard）启用 |
| — | — | — | `reset` 已移除——计数器重置由 `target_featured` 控制：勾选 → 仅 featured 出货重置；不勾选 → 任意 scope 出货重置 |

#### 4.4.2 type 切换——动态显隐

```
选中 type                 显示                               隐藏
──────────────────────────────────────────────────────────────────
soft_interval          start / end                         deltas
soft_additive          start / increment                   deltas
soft_step              deltas 编辑器                       start/end/increment
hard                   threshold                            —
rotating               （无——零参数）                       —
rotating_soft          soft_start / soft_end                —
rotating_cr            cr_counter_threshold / cr_base_rate
                       / cr_state_probs                     —
rotating_cr_soft       soft_start / soft_end
                       + cr_counter_threshold / cr_base_rate
                       / cr_state_probs                     —
targeted               fate_threshold / switch_allowed
                       / switch_resets_progress              —
targeted_soft          soft_*（三态——见 P56  §3.4 soft 参数）
                       + targeted 全部字段                    —
```

#### 4.4.3 deltas 编辑器（soft_step）

RLE 数组 `[[n, inc], ...]` 用表格控件：

| 抽数段 | 每抽增量(%) |
|:---:|:---:|
| `73` | `0.0` |
| `5` | `1.5` |
| `6` | `3.0` |
| … | … |

两列 QTableWidget，行可增删。保存时序列化为 `deltas` 数组。

#### 4.4.4 联动校验

| 条件 | 行为 |
|------|------|
| `type` = rotating 家族 | `target_featured` 禁用 + 强制勾选 |
| `type` = hard + scope = sr/r | `target_featured` 禁用（低稀有度无 featured 概念） |
| `type` = soft_interval + start ≥ end | 红色边框 + 保存时拒绝 |
| `scope` = sr/r + target_featured = True | 黄色警告「低稀有度通常无 featured 子集」 |
| `counter_init` > 0 且 type 无计数器 | 禁用控件 |

<!-- REVIEW-FIX-PREV: ISSUE-013 -->
#### 4.4.5 get_config() / 预览文本 同步适配

**问题：** `config_panel.py` 中 `get_config()`（第 2305-2319 行）在 pity 节点输出旧格式——顶层 `type`/`start`/`end`/`counter_init` + `pities` 列表（含 `params`/`target_distribution`/`reset` 旧字段）。`_do_update_preview()`（第 2119-2121 行）读取 `config['pity']['type']`、`config['pity']['start']`、`config['pity']['end']` 用于展示预览文本。P55 后 pity 配置结构完全变化（无顶层 `type`/`start`/`end`，每条目独立 `PityDef` 字段），若不同步更新，预览文本将展示空白或默认值——用户看不到当前保底配置摘要。

**适配方案：**

1. **`get_config()`：** pity 节点改为输出 `List[PityDef]` 序列化格式（或扁平化 dict 列表），每条目包含 `name`/`btype`/`scope`/`target_featured`/`deltas`/`threshold`/`counter_init` 等 P55 新字段，移除顶层 `type`/`start`/`end` 旧字段。
2. **`_do_update_preview()`：** 不再读取 `config['pity']['type']`/`['start']`/`['end']`。改为遍历 `config['pity']` 列表，逐条展示每个 PityDef 的摘要行——格式：`{btype}({scope})` + 关键参数（如 `soft_interval 74-90` / `hard threshold=120` / `rotating_cr`）。摘要逻辑委托给 BEHAVIOR_REGISTRY 中每个条目的 `display_name` 字段 + PityDef 的参数值拼接。
3. **可选兼容策略：** 若担心预览逻辑改动过大，`get_config()` 除了输出新格式列表外，额外附加一条 `'pities_summary': [...]`（预格式化的摘要文本列表），预览直接 join 展示。

#### 4.4.6 向后兼容

旧 `scope = "featured"` → 解析时自动迁移：`scope` = 池子最高稀有度，`target_featured = True`，记录 warning。
旧 `reset_condition` → 丢弃——`_should_reset()` 由 `target_featured` 自动推导，无需手动配置。

#### 4.4.7 GUI 架构——集成方式与元数据驱动渲染

**集成点：** 不改动现有 `_setup_pity_config()` 的骨架——左侧 `QListWidget`（保底条目列表）+ 右侧 `QFormLayout`（详情表单）保留。改动集中在右侧详情面板：旧代码硬编码了 `start` / `end` / `func` / `reset` / `target` 五个控件，新代码改为从 `BEHAVIOR_REGISTRY` 读取当前 type 的参数元数据 → 动态生成控件。

**核心流程：**

```
用户选中左侧条目 → _on_pity_selected(idx)
  → 读取 PityDef 各字段值
  → 根据 PityDef.btype 从 BEHAVIOR_REGISTRY 取参数元数据
  → _build_param_widgets(meta, values) → 生成右侧控件
  → _on_type_changed(new_type) → 切换参数控件显隐
```

**元数据格式（BEHAVIOR_REGISTRY 中每个条目追加 `ui_params` 字段）：**

```python
# 例：soft_interval 的 UI 参数元数据
"ui_params": {
    "start":  {"widget": "spin",   "default": 74, "min": 0, "max": 200, "label": "起始抽数"},
    "end":    {"widget": "spin",   "default": 90, "min": 0, "max": 200, "label": "结束抽数"},
    "target_featured": {"widget": "check", "default": False, "label": "仅限 featured"},
    "counter_init":    {"widget": "spin",   "default": 0, "min": 0, "max": 200, "label": "初始水位"},
}

# hard 的 UI 参数元数据
"ui_params": {
    "threshold":       {"widget": "spin",  "default": 90, "min": 1, "max": 200, "label": "保底抽数"},
    "target_featured": {"widget": "check", "default": False, "label": "仅限 featured"},
    "counter_init":    {"widget": "spin",  "default": 0, "min": 0, "max": 200, "label": "初始水位"},
    "max_triggers":    {"widget": "spin",  "default": 0, "min": 0, "max": 100, "label": "最大触发次数（0=无限）"},
}
```

**控件工厂——根据元数据创建对应 PyQt 控件：**

```python
def _build_param_widgets(ui_params, current_values):
    """根据元数据生成 (label, widget) 列表，并填入当前值。"""
    widgets = []
    for key, spec in ui_params.items():
        wtype = spec["widget"]
        if wtype == "spin":
            w = QSpinBox()
            w.setRange(spec.get("min", 0), spec.get("max", 999))
            w.setValue(current_values.get(key, spec["default"]))
        elif wtype == "double_spin":
            w = QDoubleSpinBox()
            w.setRange(spec.get("min", 0.0), spec.get("max", 100.0))
            w.setSingleStep(spec.get("step", 0.5))
            w.setValue(current_values.get(key, spec["default"]))
        elif wtype == "check":
            w = QCheckBox()                       # 无自带文本——QFormLayout 提供 label
            w.setChecked(current_values.get(key, spec["default"]))
        elif wtype == "combo":
            w = QComboBox()
            w.addItems(spec["options"])
            w.setCurrentText(current_values.get(key, spec["default"]))
        widgets.append((spec["label"], w))
    <!-- REVIEW-FIX-PREV: ISSUE-031 -->
    # ── 信号-槽连接（动态控件必须显式连接——旧硬编码控件的信号连接将被移除） ──
    _connect_dynamic_signals(widgets)
    return widgets


def _connect_dynamic_signals(widgets: List[Tuple[str, QWidget]]) -> None:
    """为动态生成的控件批量连接 valueChanged / stateChanged → _update_preview。

    旧代码（config_panel.py:1045-1052）显式连接了硬编码控件
    （pity_start_spin.valueChanged.connect(self._update_preview) 等），
    这些旧控件引用在重构后将不存在。若信号未重连，用户修改参数后
    预览文本不会更新——表现为 UI 交互正常但预览区域始终显示旧文本。
    """
    for _label, w in widgets:
        if isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.valueChanged.connect(self._update_preview)
        elif isinstance(w, QComboBox):
            w.currentIndexChanged.connect(self._update_preview)
        elif isinstance(w, QCheckBox):
            w.stateChanged.connect(self._update_preview)
    <!-- /REVIEW-FIX-PREV: ISSUE-031 -->
```
```

**动态显隐——type 切换时只显示当前 type 的专属控件：**

```python
def _on_type_changed(self, new_type):
    """type 下拉框切换 → 显示当前 type 的控件，隐藏不属于它的。"""
    meta = BEHAVIOR_REGISTRY.get(new_type, {})
    active_keys = set(meta.get("ui_params", {}).keys())  # P56 stub 无 ui_params → 空集合

    for key, (label_w, w) in self._pity_widgets.items():
        visible = key in active_keys
        label_w.setVisible(visible)
        w.setVisible(visible)

    # 特殊规则——不在 ui_params 声明中的联动
    self._apply_cross_checks(new_type)
```

**联动校验实现：**

```python
def _apply_cross_checks(self, btype):
    """ui_params 声明式规则之外的跨字段校验。"""
    # rotating 家族 → target_featured 禁用 + 强制勾选（语义冗余：scope=ssr 已是 featured）
    rotating_family = {"rotating", "rotating_soft", "rotating_cr", "rotating_cr_soft"}
    tf_widget = self._pity_widgets.get("target_featured")
    if tf_widget:
        _, cb = tf_widget
        if btype in rotating_family:
            cb.setChecked(True)
            cb.setEnabled(False)
        elif btype == "hard":
            # hard + sr/r → 禁用（低稀有度无 featured）
            scope = self._scope_combo.currentText()
            cb.setEnabled(scope not in ("sr", "r"))
        else:
            cb.setEnabled(True)

    # deactivate_on_early_hit 仅 hard 可用
    de_widget = self._pity_widgets.get("deactivate_on_early_hit")
    if de_widget:
        _, cb = de_widget
        cb.setEnabled(btype == "hard")
```

**deltas 表格控件（仅 `soft_step`）：**

不通过 `ui_params` 机制——表格控件是复合的，需手写。`soft_step` 选中时，在表单底部追加一个 QTableWidget（2 列：抽数 / 增量），行可增删。保存时读取表格行 → 序列化为 `deltas` 数组。`soft_interval` / `soft_additive` 选中时不渲染此表格——它们的参数通过 spinbox 编辑，保存时由 `_expand_soft_to_deltas()` 展开。

**与现有代码的差异：**

| | 旧代码 | 新代码 |
|---|---|---|
| 控件创建 | 硬编码 5 个控件（`type_combo`, `name_edit`, `start_spin`, `end_spin`, `reset_combo`, `target_table`） | 工厂函数从 `ui_params` 元数据动态生成 |
| type 切换 | `_on_pity_type_changed()` ~10 行手动 hide/show | 遍历 `active_keys` 集合自动显隐 |
| 新 type 扩展 | 修改 config_panel.py 多处 | 仅在 `BEHAVIOR_REGISTRY` 中追加 `ui_params`，零改动 config_panel.py |
| 校验 | 内联在 handler 中 | 声明式规则（`ui_params` 的 `min`/`max`）+ 少量跨字段函数 |

## 五、风险

| 风险 | 缓解 |
|------|------|
| `worst_impact.py` 直接实例化原类名（`SoftPityBehavior` / `HardPityBehavior`） | 全量替换为新类名，不保留旧别名 |
| 独立化后 behavior 间状态竞争（多 behavior 同时修改 `ctx.state`） | namespace 隔离——各 behavior 操作独立 key；执行顺序由自动推导规则保证确定性 |
| `PityState` 抽象化后序列化兼容 | `to_dict()`/`from_dict()`通用——三层嵌套结构，namespace 隔离天然保证兼容 |
| `CounterBasedBehavior` 计数器作用域与池子配置的一致性 | 计数器作用域由 `pools` 配置推导——保底作用于哪些池子，计数器就在哪些池子间共享；不引入独立的 `persistence` 参数 |
| `base_probabilities` key 语义不明确（槽位 vs 卡牌 id） | DrawInfo 显式区分 `scope_cards`（卡牌 ID）与 `scope_slots`（槽位 ID）；AdditiveBehavior 累加使用 slots |
| `[rarities]` 中 scope 未注册但被 `[[pity]]` 引用 | 解析时即校验——`scope` 值必须在 `[rarities]` 的某一行中出现过，否则 ConfigError |
| 配置面板 UI 改动过大 | 渐进式——先加新字段，确保必填校验 |
| `ctx.current` 管道缺少历史记录 | **已知局限（搁置）：** behavior 只能看到当前管道状态，无法回溯前一个 behavior 调整前的 `ctx.current`。调试复杂叠加场景时可能不便。低优先级，后续按需在 `PityContext` 增加 `previous: Optional[Dict]` 字段 |
| `scope_slots` / `featured_slots` / `scope_cards` 未被填充导致保底静默失效（ISSUE-001 / ISSUE-002 / ISSUE-008） | `DrawInfo` 构造时必须调用 `_build_draw_info()`（§3.2.1）从 `List[PoolDistEntry]` 分组槽位 ID；`SimulationEnvBuilder` 在构建 `PoolPitySpec` 时预计算这三个字段。验收标准：`SoftStepBehavior._compute_probabilities()` 单元测试中 `scope_slots` 非空且 `featured_slots` 为正确子集 |
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-8 -->
| **【CRITICAL】GachaService probabilities key 语义断裂（AUDIT-BREAK-8）**——`probabilities = {card_id: prob}` 的 key 是卡牌 ID，但 `scope_slots['ssr']` = `('ssr',)`（稀有度名）。`result.get('ssr', 0.0)` 始终返回 0.0 → 所有保底概率调整静默失效 | 修复方案见 §0.3——推荐方案 A（GachaService 按稀有度聚合概率为 `{rarity: sum_probs}`）。验收：`SoftStepBehavior._compute_probabilities()` 中 `pool > 0` |
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-8 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-1 -->
| **调用顺序错误（AUDIT-BREAK-1）**——`load_toml()` 先 `_build_pity()` 后 `_parse_rarities()` → `rarity_rank` 为空时 scope 注册校验全部失败 | 交换 `load_toml()` 中的调用顺序：先 `_parse_rarities()` 后 `_build_pity()`。见 §0.1 |
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-1 -->
<!-- REVIEW-FIX-PREV: AUDIT-BREAK-10 -->
| **PityEngine 构造签名变更波及 16+ 处调用断裂（AUDIT-BREAK-10）**——`behaviors` 参数移除、`state` 参数新增 → 所有调用方 TypeError | 阶段十二A 中批量修改全部 ~18 处调用方（见 §0.6 清单）。不可分批——必须一次性同步完成 |
<!-- /REVIEW-FIX-PREV: AUDIT-BREAK-10 -->

## 六、设计边界提醒

### 现有能力（不要推倒重来）

以下能力当前 `core/pity.py` 已实现，P55 是**重构**而非新建——保留核心逻辑，改的是组织方式：

| 现有能力 | 代码位置 | P55 如何处理 |
|---------|---------|-------------|
| `SoftPityBehavior._apply_targeted()` — 概率增量按 `resolved_targets` 分配 | `pity.py:62-88` | **保留分配算法**。P55 的 `target_featured` 参数是此能力的声明式入口——`PoolPitySpec.resolved_targets` 的构建逻辑改为由 `target_featured` + `scope` 推导 |
| `PityEngine.after_draw()` — `is_ssr` 判定 + 三级 `reset_condition` | `pity.py:246-264` | **重构**。P55 移除 `reset_condition`（`_should_reset()` 由 `target_featured` 自动推导），`after_draw()` 退化为 `foreach behavior: bh.after_draw(ctx)` |
| `PityState` — `increment()` / `reset()` / `get()` 基础操作 | `pity.py:165-192` | **保留语义**。P55 扩展为 namespace 容器（`_data: Dict[str, Dict[str, Any]]`），但 `incr` / `set` / `get` 语义不变 |
| `PityEngine.before_draw()` — 先 `increment` 再 `get_probabilities` 的管道顺序 | `pity.py:227-236` | **保留顺序**。P55 改为 `foreach behavior: bh.before_draw(ctx)`，但「先计数、后算概率」不变 |
| `PityEngine.get_probabilities()` — 不修改状态的查询 | `pity.py:203-225` | **保留此方法**。策略层已有只读查询入口，P55 扩充为 5 个语义方法 |
| `PoolPitySpec.featured_ids` / `ssr_ids` — 区分限定/常驻的基础设施 | `pity.py:158-163` | **保留**。P55 的 `DrawInfo.featured_slots` 由此推导 |

### P55 新建能力（只建一次，不要叠层）

以下为 P55 新建——每个需求对应**一个**机制：

| 新建能力 | 机制 | 不要做的事 |
|---------|------|-----------|
| behavior 自管完整生命周期 | `PityBehavior.before_draw()` / `after_draw()` 独立接口 | 不要在 Engine 层写 if-else 分发 |
| 新增保底类型零改动 Engine | `BEHAVIOR_REGISTRY` + `create_behavior()` 工厂 | 不要额外建 plugin 系统或注册中心 |
| 状态字段不预设类型 | `PityState` namespace 化（`_data: Dict[str, Dict]`） | 不要建 typed state schema |
| 计数器操作拼写安全 | `Counter` / `Flag` 微抽象 | 不要引入完整 ORM 或状态管理框架 |
| 计数器重置条件 | `_should_reset(ctx)` = 命中 scope 稀有度 且（`target_featured=true` → `is_featured` 为真），无需独立 `reset` 参数 | 不要加 inter-behavior 重置传播协议 |
| 触发 N 次后停用 | `max_triggers` → `_active.clear()` | 不要额外建「一次性 behavior」子类 |
| 策略查询保底状态 | `PityEngine.get_counter()` / `is_guaranteed()` 等 | 不要让策略直接访问 `PityState._data` |
| 管道概率依次传递 | `ctx.current` → 返回新 dict → engine 赋值 | 不要加概率快照/回滚机制 |

<!-- REVIEW-R1-FIX: GATE-5-回滚路径——新增 §6.5 per-stage 回滚策略。 -->
### 6.5 回滚策略——per-stage 独立回退机制

P55 是 breaking 变更（PityDef 5→17字段、PityEngine 构造签名变更、波及21文件），且 §0.4 标注「不可部分实施」。为降低单点阻塞风险，补充以下 per-stage 回滚策略：

#### 6.5.1 特性开关——双引擎并存

`run_batch_parallel()` 已设计 `use_new_engine=False` 参数，此为全局回退开关。实施阶段五-十二期间默认值为 `False`（走旧引擎），仅在测试路径中显式传 `True`。若阶段十二A-1（PityEngine 构造签名变更）中任一子阶段失败且短时间内无法修复：

```
回退操作：
  git checkout -- gacha_simulator/core/pity.py         # 恢复旧 PityEngine
  git checkout -- gacha_simulator/service/batch_simulator.py  # 恢复旧 _build_pity_engine_from_gui
  # use_new_engine 默认 False → 旧引擎继续工作，其他 P55 子阶段不受影响
```

**关键约束：** `use_new_engine` 是运行时开关（非编译时），不依赖 git 回退。若仅阶段十二A 失败而阶段五-十（behavior 实现+配置解析）已完成，旧引擎仍可正常加载 `config.toml`（旧格式），新 behavior 代码加载但不被调用——需确认旧引擎不 import 新 behavior 类。**当前 `PityEngine.__init__` 不 import `SoftStepBehavior`/`HardPityBehavior`（旧引擎使用 `SoftPityBehavior`/`HardPityBehavior`），满足隔离条件。**

#### 6.5.2 PityDef 中间兼容层

PityDef 5→17字段重构是单向断裂——无法部分实施。为降低过渡期风险，建议在 `PityDef` dataclass 中添加**只读向后兼容属性**（非持久化、仅桥接）：

```python
@dataclass
class PityDef:
    # ... 17 个新字段（P55 主路径）...

    # ── 向后兼容桥接（P55 过渡期——阶段十二完成后删除） ──
    # 允许未适配的消费方在过渡期通过旧属性名访问。
    # 待所有消费方适配完成后（阶段十二A-4 桥接代码清理），删除以下 3 个 property。
    @property
    def params(self) -> dict:
        """过渡期兼容：将新字段映射回旧 params dict 格式。
        仅在旧消费方（未适配 P55 的代码）访问时触发——触发时 emit DeprecationWarning。
        """
        import warnings
        warnings.warn(
            f"PityDef.params 已废弃——请改用 PityDef 平级字段（deltas/threshold/soft_start 等）。"
            f"此兼容桥接将在阶段十二完成后删除。",
            DeprecationWarning, stacklevel=2,
        )
        result = {}
        if self.deltas is not None:
            result['deltas'] = self.deltas
        if self.threshold:
            result['threshold'] = self.threshold
        if self.soft_start is not None:
            result['soft_start'] = self.soft_start
        if self.soft_end is not None:
            result['soft_end'] = self.soft_end
        # ...（按需扩展）
        return result

    @property
    def target_distribution(self) -> dict:
        """过渡期兼容：从 scope+target_featured 反向推导旧 target_distribution。"""
        import warnings
        warnings.warn("PityDef.target_distribution 已废弃——请改用 scope + target_featured。",
                      DeprecationWarning, stacklevel=2)
        return {'scope': self.scope, 'featured': self.target_featured}

    @property
    def reset_condition(self) -> str:
        """过渡期兼容：从 target_featured 反向推导旧 reset_condition。"""
        import warnings
        warnings.warn("PityDef.reset_condition 已废弃——请改用 target_featured。",
                      DeprecationWarning, stacklevel=2)
        return 'featured_ssr' if self.target_featured else 'any_ssr'
```

**使用策略：** 此兼容层在阶段十A（PityDef 扁平化）时一次性实现（~30行），使阶段十二A 消费方适配可分批复用——先修复导致 `TypeError` 的硬断裂点（PityEngine 构造签名），再逐个消费方迁移到新字段（兼容层 DeprecationWarning 指引定位）。阶段十二A-4 桥接代码清理时一并删除这 3 个兼容 property。

#### 6.5.3 Git 分支策略——分批合入

P55 变更量大，建议分 4 个批次合入 main，每批次打 tag：

| 批次 | 阶段范围 | tag | 回退内容 |
|------|---------|-----|---------|
| B1 | 阶段五A-D + 六 + 七（behavior 实现 + 语法糖） | `p55-b1-behaviors` | `git revert p55-b1-behaviors`——恢复旧 behavior 类。不影响运行时（behavior 未被 Engine 调用） |
| B2 | 阶段八 + 九 + 十A-B（Registry + 排序校验 + PityDef + 迁移） | `p55-b2-config` | `git revert p55-b2-config`——恢复旧 PityDefParsed + 旧配置解析。新 behavior 代码保留但不被调用 |
| B3 | 阶段十一A-C（UI 面板） | `p55-b3-ui` | GUI 改动独立于引擎——回退不影响模拟正确性 |
| B4 | 阶段十二A1-4 + B-C + 十三A-C（波及适配 + 测试） | `p55-b4-adapt` | 最危险的批次——若失败回退到 B3 tag、旧引擎继续工作。`use_new_engine=False` 保底 |

**分批避险规则：** 每个批次合入前，该批次所有子阶段必须全量 pytest 绿灯。若 B4 合入后发现问题，回退到 B3 tag（`git reset --hard p55-b3-ui`）——所有 P55 behavior/配置代码完好，仅 `use_new_engine` 开关保持 `False`，等价于 P55 未激活。

#### 6.5.4 per-stage 回滚操作速查表

| 失败阶段 | 回退命令 | 影响范围 | 恢复时间 |
|---------|---------|---------|:---:|
| 五A-D 任一 | `git checkout -- gacha_simulator/core/pity.py` | 仅 behavior 代码 | <1min |
| 六 | `git checkout -- gacha_simulator/core/config_toml.py` | 仅语法糖展开 | <1min |
| 七-九 | `git checkout -- gacha_simulator/core/pity.py` | behavior + registry + 排序 | <1min |
| 十A-B | `git checkout -- gacha_simulator/core/config_store.py gacha_simulator/core/config_toml.py` | PityDef + 迁移 | <1min |
| 十一A-C | `git checkout -- gacha_simulator/gui/config_panel.py` | 仅 GUI 面板 | <1min |
| 十二A-1 | `git checkout -- gacha_simulator/core/pity.py gacha_simulator/service/batch_simulator.py` + 测试文件 | PityEngine 签名+构造方 | <2min |
| 十二A-2 | `git checkout -- gacha_simulator/service/gacha_service.py` | 仅 GachaService | <1min |
| 十二A-3 | `git checkout -- gacha_simulator/analysis/worst_impact.py` | 仅 worst_impact | <1min |
| 十二A-4 | `git checkout -- gacha_simulator/core/pity.py gacha_simulator/service/retreat_config.py gacha_simulator/analysis/vulnerability.py` | 桥接清理+retreat+vuln | <2min |
<!-- /REVIEW-R1-FIX: GATE-5-回滚路径 -->

<!-- REVIEW-FIX-PREV: ISSUE-GATE-6 -->
<!-- GATE-6 修复：验收清单按阶段重新分组（五-十三），每阶段至少一条独立可验证验收项。 -->
<!-- 补充关键行为边界条件测试的具体输入/期望输出。提供 SoftStepBehavior 具体验收样例。 -->

## 七、验收标准

### 宏观目标

<!-- REVIEW-R1-FIX: GATE-6-测试策略——「无 import 错误」标准太弱（已适配但逻辑错误导致概率偏差无法检测），替换为具体功能等价性验收。 -->
<!-- REVIEW-R1-FIX: GATE-6-测试策略——每子阶段编码完成后立即运行对应 pytest，不等阶段十三。阶段十三是「汇总回归」而非「首次测试」。 -->
- [ ] **pytest 全量通过**——每子阶段编码完成后立即运行对应 pytest 子集（命令标注在各实施阶段表行中），阶段十三为全量汇总回归。含新增 pity 专项测试 >=20 用例，覆盖所有新 type/scope/轻量扩展组合
- [ ] `worst_impact.py` / `batch_simulator.py` / `gacha_service.py` **功能等价性验证：** `run_batch_parallel(store, n=5000, seed=42, use_new_engine=True)` 产出的 13 种 GDR 指标与 `use_new_engine=False`（旧引擎）的差异 < 0.001（等价性桥接测试——§3.3.2.1）。**仅「无 import 错误」不够——必须验证概率分布无偏差。**
- [ ] 配置面板可完整编辑所有新字段
- [ ] 现有 7 种策略在保底重构后行为无退化（集成测试——`smart` / `pool_quota` / `pity_reserve` / `stop_on_target` / `target_hunting` / `fixed_count` / `draw_target` 逐一通过）

### 阶段五——`SoftStepBehavior(CounterBasedBehavior)` 实现

- [ ] `DrawInfo` 不可变性：`frozen=True` 生效，误写编译报错
- [ ] `Counter` 封装正确：`incr()`/`value()`/`reset()`/`reached()` 等价直接操作 `PityState`
- [ ] **SoftStepBehavior 验收样例（具体输入/期望输出）：**
  - **输入：** `deltas=[[73, 0.0], [17, 5.88]]`、`scope='ssr'`、`counter=80`、`base_probabilities={'ssr': 0.01, 'sr': 0.15, 'r': 0.84}`、`scope_slots={'ssr': ('ssr',)}`、`featured_slots={'ssr': ('ssr',)}`
  - **计算：** `_cumulative_boost(80)` = `(80 - 73) * 5.88 = 41.16%`
  - **期望：** SSR 概率从 1% 提升至 `0.01 + 0.99 * 0.4116 ≈ 0.417484`（约为 41.75%），SR 和 R 等比缩小至 `0.15 * (1 - 0.4116) ≈ 0.08826` 和 `0.84 * (1 - 0.4116) ≈ 0.494256`
- [ ] **边界条件——deltas 为空列表：** `deltas=[]`，`counter=50` → `_cumulative_boost(50)` 返回 `0.0`，`_compute_probabilities()` 返回 `ctx.current.copy()`（不修改概率）
- [ ] **边界条件——counter=0：** `deltas=[[73, 0.0], [17, 5.88]]`，`counter=0` → `_cumulative_boost(0)` 返回 `0.0`，零 boost
- [ ] **边界条件——counter 超出所有 deltas 段：** `deltas=[[73, 0.0], [17, 5.88]]`，`counter=120` → `70 * 5.88 = 411.6%`，截断为 `min(411.6, 100.0) = 100.0%`
- [ ] **边界条件——scope_slots 中无目标 scope：** `scope='ur'`，但 `scope_slots={'ssr': ('ssr',)}`（无 'ur' 键）→ `_compute_probabilities()` 返回 `ctx.current.copy()`（不调整概率）
- [ ] **边界条件——target_featured=true 但 featured_slots 为空：** `target_featured=true`，`scope='ssr'`，`featured_slots={}` → `target_slots` 回退为 `scope_slots`（不导致空目标集合）
- [ ] `type = "soft_additive"` + `scope = "ssr"` 产出概率分布与公式一致（>=3 个抽样点校验：counter=74→SSR 概率≈6.9%（boost=6%×99%），counter=80→SSR 概率≈42.6%（boost=42%×99%），counter=90→SSR 概率=100%（boost=102%封顶→全部非 SSR 概率被抽取））

### 阶段六——TOML 糖展开 `_expand_soft_to_deltas()`

- [ ] `soft_interval`（start=74, end=90）→ `deltas = [[73, 0.0], [17, 100/17]]`（≈5.8824，浮点容差 ±1e-4 内）
- [ ] `soft_interval`（start=1, end=10）→ 跳过零前缀段，直接返回 `[[10, 10.0]]`
- [ ] `soft_additive`（start=74, increment=6.0）→ `deltas = [[73, 0.0], [17, 6.0]]`（`17 = ceil(100/6)`）
- [ ] `soft_step`（deltas 原样）→ `deltas` 直接传递，不做转换

### 阶段七——`HardPityBehavior` scope 化

- [ ] `scope = "sr"` 硬保底正确工作——第 N 抽出 SR 时重置，累加至 100% 后必出 SR
- [ ] `max_triggers = 1` 正确限制触发次数——触发一次后不再触发
- [ ] **边界条件——counter < threshold（未达阈值）：** `threshold=90`, `counter=89` → `_compute_probabilities()` 返回 `ctx.current.copy()`（不干预）
- [ ] **边界条件——counter >= threshold（达到阈值）：** `threshold=90`, `counter=90`, `scope='ssr'`, `scope_slots={'ssr': ('ssr',)}`, `ctx.current={'ssr': 0.01, 'sr': 0.15}` → SSR 概率强制 100%（`result['ssr'] = 0.01 + 0.15 = 0.16`，若仅有 ssr 槽位则为其全部），非目标槽位归零

### 阶段八——BEHAVIOR_REGISTRY 条目更新

- [ ] `BEHAVIOR_REGISTRY`（含参数元数据）+ `create_behavior()` 工厂函数正确路由所有 10 种 type（4 种 counter 驱动 + 6 种事件驱动 stub）
- [ ] 事件驱动 type（rotating/rotating_cr/targeted 等，`class=None`）→ `create_behavior()` 明确报错「P56 交付」，而非静默跳过或 AttributeError
- [ ] `PityEngine` 无保底业务逻辑——`after_draw()` 仅为 `foreach behavior: behavior.after_draw(ctx)`
- [ ] `PityContext` 完整性：behavior 仅通过 `ctx.draw` / `ctx.current` / `ctx.state` 获取信息，不访问外部全局状态

### 阶段九——`_resolve_order()` 自动排序 + 校验

- [ ] 自动推导：`_resolve_order()` 正确排序——高稀有度先执行、同稀有度 soft 在 hard 前。具体用例：输入 `[sr_hard(scope=sr, type=hard), ssr_soft(scope=ssr, type=soft_interval)]` → 排序后 `[ssr_soft, sr_hard]`（ssr 稀有度更高、soft 优先）
- [ ] 校验分级——同 scope 两个 hard → ConfigError
- [ ] 校验分级——同 scope 两个事件驱动型（rotating/rotating_soft/rotating_cr/targeted）→ ConfigError
- [ ] 校验分级——同 scope 同 type 两个 soft → ConfigError
- [ ] 校验分级——同 scope 不同 type 两个 soft → warn（不阻塞，允许但提醒）
- [ ] 稀有度层级保护：`scope="sr"` 的增量不着色 `rank < SR_rank` 的稀有度（如 UR/SSR）——此保护天然成立：`scope_slots` 仅含 sr 对应稀有度的槽位，物理上碰不到高稀有度

### 阶段十——配置解析

- [ ] `[rarities]` 解析正确——`rarity_rank` 映射生成、平级同 rank、未注册 scope → ConfigError
- [ ] `PityState` 序列化往返无损——输入 `{'data': {'bh1': {'counter': 5}, 'bh2': {'guaranteed': True}}}` → `from_dict()` → `to_dict()` → 输出相等
- [ ] `PityState` 抽象化：behavior 通过 `get()`/`set()`/`incr()` 操作自身 namespace，引擎不预设字段类型
- [ ] 旧格式迁移——`_is_legacy_format()` 正确识别旧格式（含 start/end 但无 scope/target_featured）
- [ ] 旧格式迁移——`_migrate_legacy_pity()` 正确映射 15+ 字段（type: soft→soft_interval, reset: any_ssr→target_featured=false 等）
- [ ] 旧格式迁移——`func='exp'`/`func='step'` → ConfigError（明确报错，不含糊）
- [ ] 写路径——`_build_toml_pity()` 与 `_build_pity_def()` round-trip 可逆（PityDef → TOML dict → PityDef 一致性校验）
- [ ] `_deltas_to_soft_interval()` 反向还原——`[[73, 0.0], [17, 5.88]]` 两段且首段增量为 0 且第二段增量满足 `100/n` 容差 → 还原为 `{start: 74, end: 90}`

### 阶段十一——配置面板 UI

- [ ] 参数元数据驱动：config panel 依据 `BEHAVIOR_REGISTRY.ui_params` 元数据渲染 UI 控件，必填/范围/类型校验生效
- [ ] type 切换动态显隐：选中 `soft_interval` → 显示 start/end，隐藏 deltas 表格；选中 `soft_step` → 显示 deltas 表格，隐藏 start/end/increment
- [ ] 联动校验——`type` = rotating 家族 → `target_featured` 禁用 + 强制勾选
- [ ] 联动校验——`type` = hard + `scope` = sr/r → `target_featured` 禁用
- [ ] 联动校验——`type` = soft_interval + start >= end → 红色边框 + 保存时拒绝
- [ ] deltas 表格编辑器——行可增删，保存时正确序列化为 `[[n, inc], ...]` 数组
- [ ] `get_config()` 输出新格式——每条目含 name/btype/scope/target_featured 等 P55 新字段，不出现旧字段 start/end/func/reset/target
- [ ] `_do_update_preview()` 正确展示新格式摘要文本——遍历 pity 列表逐条展示而非读取顶层 type/start/end

### 阶段十二——波及文件适配

<!-- REVIEW-R1-FIX: GATE-6-测试策略——阶段十二按拆分的子阶段分组，每子阶段补充具体功能等价性验收标准。 -->

#### 阶段十二A-1——PityEngine 构造签名批量同步

- [ ] `batch_simulator.py`——`_build_pity_engine_from_gui()` 全量重写完成（旧逻辑约120行全部删除），新逻辑约40行；`SimulationEnvBuilder._build_pool_pity_spec()` 正确预计算 `scope_slots`/`featured_slots`/`scope_cards`（至少含一个非空 scope 分组）；`SimulationEnvBuilder.from_config_store()` 行602-618 `pity_cfg_dict` 构建逻辑已适配（AUDIT-BREAK-5）；`_resolve_targets()` 已删除
- [ ] `worst_impact.py`——`_build_pity_engine()` 适配新签名（移除 behaviors，新增 state），虚拟池从参考池子 `PoolEntry.distribution` 预计算（AUDIT-BREAK-18）
- [ ] **【GATE-6 补充——18处调用方回归验收】`test_pity.py` 6处 + `test_p60_equivalence.py` ~10处构造签名同步完成。验收标准（三级）：**
  1. **编译级：** `pytest tests/ --co -q` 零 `TypeError` / `ImportError`（导入时签名不匹配立即暴露）
  2. **等价性级：** `pytest tests/test_p60_equivalence.py -v` 全量绿灯——P60 交付的 13 项等价性断言无回归（`SoftPityBehavior` vs `SoftStepBehavior` 等效性、`HardPityBehavior` 新旧等效性、`PityState` 序列化往返）
  3. **概率分布级：** `run_batch_parallel(store, n=5000, seed=42, use_new_engine=True)` 与 `use_new_engine=False` 的 13 种 GDR 差异 < 0.001——排除「已适配但 `counter_init` 传入丢失」「scope_slots 分组错误」等逻辑偏差

#### 阶段十二A-2——GachaService 概率聚合 + 检测链修复

- [ ] PityEngine 构造签名适配（移除 behaviors 参数，新增 state）
- [ ] `before_draw()` 调用前按稀有度聚合 probabilities（AUDIT-BREAK-8——方案A——`_aggregate_probs_by_rarity()` + `_get_rarity()` 约25行）
- [ ] `after_draw()` 第3参数从 `reward.id`(str) 改为 `reward`(Reward对象)，新增第4参数 `base_probabilities`（AUDIT-BREAK-9）
- [ ] 行196-214 `pity_triggered` 检测链：行201 `_pity_engine.behaviors.get(pname)` -> `_pity_engine.is_active(pname)`，行205 `behavior.is_active(cv)` -> 同上，行209-214 `pity_state.get(pname, 'counter', 0)` -> `_pity_engine.get_counter(pname)`（ISSUE-035）
- [ ] **【GATE-6 补充——AUDIT-BREAK-8 端到端验证】** 完整链路测试：TOML 配置（含 `[[pity]] type='soft_interval' scope='ssr' target_featured=true start=74 end=90`）-> `SimulationEnvBuilder.from_config_store()` -> `GachaService.run_simulation_compact()` -> `PityEngine.before_draw()` -> `SoftStepBehavior._compute_probabilities()` -> 验证 `ctx.current` 中 `'ssr'` 键的值为非零（AUDIT-BREAK-8 修复前为 0.0）。**验收脚本：** 加载默认 `config.toml`，单池 100 抽模拟，确认 `PityEngine.get_counter('ssr_soft') > 0` 且保底计数器正常递增（验证概率聚合后 key 匹配 scope_slots 槽位 ID）。
- [ ] **【GATE-6 补充——行189-194 probability 初步检测修复】** AUDIT-BREAK-8 将 `probabilities` 从 card-id-keyed 改为 rarity-keyed 后，行189-194 的 `if original_probs != probabilities` 比较同步替换为 rarity-keyed 比较——否则 `pity_triggered` 初步检测因 key 的 dict 结构不同而误判。

#### 阶段十二A-3——worst_impact.py 内部适配

- [ ] 类名替换——`SoftPityBehavior`->`SoftStepBehavior`、`HardPityBehavior`->`HardPityBehavior`（全量搜索替换，零遗漏）
- [ ] `_get_initial_pity_state()` counter_init 读取修正——从 `store.pity.counter_init` 改为遍历 `store.pity.pities` 读取每个 `PityDef.counter_init`（AUDIT-BREAK-19）
- [ ] `_get_pity_cost()` 行340-354 适配（ISSUE-036）——`p.params.get('end', '90')` -> 从 P55 新字段推导 end 值，遍历所有 `PityDef` 取最大 end 值
- [ ] `_resolve_targets_for_pool()` 已删除（约21行——ISSUE-029）
- [ ] **【GATE-6 补充——worst_impact 虚拟池方案B 兜底路径验收】** `worst_impact.py:385` 当前是唯一构造 Reward 时携带 `extra_info={'rarity': ..., 'featured': ...}` 的位置。若方案 A（PoolPitySpec 预计算）失败且方案 B 兜底路径被触发，需验证：(a) `batch_simulator.py` 构造 Reward 时已同步添加 `extra_info`（否则方案 B 返回空 scope_slots，保底静默失效——AUDIT-BREAK-12）；(b) `_build_draw_info_fallback()` 从 `reward.extra_info` 推导的 `scope_slots` 与方案 A 预计算的结果一致。**验收脚本：** 构造一个 `PoolPitySpec(scope_slots={}, scope_cards={})`（强制触发方案 B），运行一次模拟，确认保底计数器正常递增（验证兜底路径未被静默绕过）。

#### 阶段十二A-4——retreat_config + vulnerability + 桥接代码清理

- [ ] `retreat_config.py`——PityDef 构造适配 17 字段新格式 + PityConfig 移除 `counter_init` 参数（AUDIT-BREAK-31）
- [ ] `vulnerability.py`——不再直接访问 `PityState.data`，改为通过 `PityEngine.get_state_summary()` 或 `ps._data`（ISSUE-030）
- [ ] **【ISSUE-055 显式标注】`PityEngine.get_state_summary()` data->_data：** `self._state.data.items()` 改为 `self._state._data.items()`（`pity.py:610`）。此变更作为 `PityState.data` 重命名的同步变更项，必须在阶段十二A-4 中与 `vulnerability.py` 的 `data`->_data 变更同步完成。**若遗漏 -> `AttributeError: 'PityState' object has no attribute '_data'`（旧代码仍用 `data`）或 `AttributeError: 'PityState' object has no attribute 'data'`（新代码已改为 `_data` 但 PityState 未同步重命名）。**
- [ ] 桥接代码清理——`PoolPitySpec.resolved_targets` 字段（`pity.py:498-502`）+ `_resolve_targets()`（`batch_simulator.py` ~30行）+ `_resolve_targets_for_pool()`（`worst_impact.py` ~21行）+ `PityEngine` 中 2 处桥接调用（`pity.py:498-502 / 538-542`）全部删除（ISSUE-029）。验收：`grep -r "resolved_targets" gacha_simulator/` 返回零结果。

#### 阶段十二B——辅助适配

- [ ] `strategy.py`——`StrategyContext` 不再引用 `PityState` 内部属性，改为通过 `PityEngine` 公共查询接口
- [ ] `process_analysis.py` / `process_trace.py` / `streaming.py` / `collector.py`——pity 相关引用已更新（无 import 错误）

#### 阶段十二C——CLI + 配置示例

- [ ] `cli.py`——PityEngine 构造签名适配（若 CLI 直接构造）；`--migrate` CLI 参数已实现（ISSUE-039）
- [ ] `config/config.toml`——`[[pity]]` 节更新为新语法（soft_interval/soft_additive/hard 各至少一条示例）
- [ ] `core/__init__.py`——导出符号已更新（新增 SoftStepBehavior/CounterBasedBehavior/PityContext/DrawInfo/Counter/Flag/LifecycleConfig/BEHAVIOR_REGISTRY/create_behavior；移除 SoftPityBehavior/PityDefParsed）

### 阶段十三——测试与文档

- [ ] **两 behavior 同 scope 不同 name → 计数器独立：** `bh1`（name='soft1', scope='ssr'）、`bh2`（name='soft2', scope='ssr'），`bh1` 计数器递增至 80，`bh2` 计数器仍为 0——`PityEngine.get_counter('soft1') = 80`、`PityEngine.get_counter('soft2') = 0`
- [ ] `_should_reset()` 由 `target_featured` 控制——4 项子验收：
  - `target_featured=true` + `reward_rarity='ssr'` + `is_featured=false`（歪了）→ `_should_reset()` 返回 `False`（不重置）
  - `target_featured=true` + `reward_rarity='ssr'` + `is_featured=true`（没歪）→ 返回 `True`（重置）
  - `target_featured=false` + `reward_rarity='ssr'` + `is_featured=false`（歪了）→ 返回 `True`（任意 SSR 出货都重置）
  - `reward_rarity='sr'`（不匹配 scope='ssr'）→ 返回 `False`（不重置）
- [ ] `CounterBasedBehavior` 生命周期统一：两个子类（`SoftStepBehavior` / `HardPityBehavior`）只实现 `_compute_probabilities()`，`before_draw`/`after_draw` 由基类统一
- [ ] 文档——`01-理论.md` 含独立化设计 + 新 type/scope 理论
- [ ] 文档——`02-实施.md` 反映新类结构
- [ ] 文档——`CLAUDE.md` 保底节/策略节/GDR 节/并行模拟入口 4 处同步更新
<!-- /REVIEW-FIX-PREV: ISSUE-GATE-6 -->

## 自动化审查记录

### 第 1 次审查（2026-06-11）——P38 工作流自动化

- 复杂度: complex | 变更性质: breaking
- 阶段 1 影响面: 52 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 32 个

### 第 2 次审查（2026-06-11）——P38 工作流自动化

- 复杂度: complex | 变更性质: breaking
- 阶段 1 影响面: 82 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 跳过
- 累计问题: 24 个

## ⚠ 自动化审查阻塞项

**未解决问题: 0 个**

**详情:** []

**阻塞原因:** 6 轮对抗循环未收敛。
