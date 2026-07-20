<!-- META: P62 | module:GDR系统 | status:designing | last:2026-07-14 -->

# P62 可达目标卡筛选——GDR分母区分全量与池子开放子集

> 日期：2026-07-14 | 状态：设计中
> 触发：目标卡相关 GDR 公式分母始终使用全部目标卡，未区分「池子窗口在模拟期间曾开放过」的可达卡与「池子从未开放」的不可达卡。
> 依赖：无（零依赖，与所有活跃计划 P41/P22/P28/P55/P56/P57/P58 并行实施）
> 被依赖：无

---

## 一、问题

### 1.1 现状

所有目标卡相关 GDR 的分母为 `target_specs` 全集。但一次模拟中，某些目标卡所属的全部池子在模拟结束前均未开放（`start_day > final_time`），这些卡根本不可能获得，却计入分母虚降指标。

**典型场景：** 10 张目标卡分布在 3 个池子（A: day 0–21 / B: day 0–21 / C: day 100–121），sim 只跑 21 天 → C 池从未开放 → C 中的 3 张目标卡应排除出分母。

**不可混淆的判定：** 池子开放过但策略选择不抽 → 该卡仍记入分母，正确暴露策略遗漏。判定依据是池子时间窗口 `start_day ≤ final_time`，而非 `pool_draw_counts[pool_id] > 0`（策略实际是否抽取）。

### 1.2 受影响的 GDR（4 个）

逐条审查 17 个 `UNIFIED_GDR_REGISTRY` 条目后，确认仅 4 个因不可达卡产生分母/判定域偏差：

| GDR | 行号 | 不可达卡的影响 | 根因 |
|-----|------|--------------|------|
| `target_achievement` | L295–301 | 分母 `Σ qty` 虚增 | 不可达卡 qty 计入分母，分子贡献恒为 0 |
| `target_collection` | L304–310 | 分母 `len(target_specs)` 虚增 | 不可达卡种类计入分母，`got` 恒为 0 |
| `all_targets` | L313–318 | 返回值恒为 0 | 不可达卡永远不达标 |
| `weighted_satisfaction` | L395–409 | 系统性惩罚不可消除 | 不可达卡产生 `−qty × miss_cost` 永久惩罚 |

### 1.3 不受影响的 13 个

| 不受影响原因 | GDR |
|-------------|-----|
| `target_specs` 仅用于迭代，不可达卡贡献恒为 0 → 数学等价 | `extra_target`、`target_card_draws`、`resource_efficiency`、`resource_per_card` |
| 不使用 `target_specs` | `ssr_collection`、`resource_remaining`、`resource_consumed`、`non_pity_draws`、`pity_draws`、`weapon_character_ratio`、`draw_conversion_efficiency` |
| 分母非 `target_specs` | `per_pool_draw_rate` |
| 迭代域是 `card_counts` 非 `target_specs` | `total_card_value` |

---

## 二、目标

1. 新增 `filter_target_specs_by_obtainable()` —— 依据池子时间窗口筛选可达目标卡
2. 新增 4 个 `_obtainable` 后缀 GDR key，注册到 `UNIFIED_GDR_REGISTRY`
3. `GDRDefinition` 新增 `needs_store` 标志位 —— 告知调用方必须传入 `store`
4. `compute_gdr_from_compact()` 透传 `store` 至 wrapper 函数；wrapper 内部自行调用 `filter_target_specs_by_obtainable()` 过滤 `target_specs`（避免 `compute_gdr_from_compact` 与 wrapper 双重过滤） <!-- REVIEW-R1-FIX: ISSUE-006 -->
5. `GDRCalculator` / `make_gdr_calculator` 透传 `store` 参数
6. **零 GUI 变更** —— 统计分析面板下拉框自动出现新条目，用户同时勾选全量版和可达版即可并排对比
7. 6 类边界场景全覆盖测试

---

## 三、详细实施

### 任务 1：`filter_target_specs_by_obtainable()` 核心函数

**文件：** `gacha_simulator/core/gdr.py`，插入位置：`_gdr_draw_conversion_efficiency` 之后、`GDRDefinition` 之前（~L474）

```python
def filter_target_specs_by_obtainable(
    target_specs: Dict[str, int],
    store: 'ConfigStore',
    final_time: float,
) -> Dict[str, int]:
    """返回仅包含「可达」目标卡的 target_specs 子集。

    可达定义：目标卡所属的至少一个启用池子的 start_day ≤ final_time。
    判定依据是池子时间窗口，而非策略是否实际抽取（pool_draw_counts > 0）。

    Args:
        target_specs: {card_id: quantity} 全量目标卡
        store: ConfigStore 实例（需含 card_defs.pools + pools 元数据）
        final_time: 模拟实际结束时间（CompactResult.final_time）

    Returns:
        仅含可达目标卡的 Dict。若 store 为 None，返回原始 target_specs（保守回退）。
        若无一可达，返回空 dict。
    """
    if store is None:
        return dict(target_specs)  # 保守回退：不缩小分母

    # 构建 card_id → set(pool_ids) 索引（仅遍历一次 store.card_defs）
    card_pools: Dict[str, set] = {}
    for cd in store.card_defs:
        card_pools[cd.card_id] = set(cd.pools)

    # 构建 pool_id → start_day 映射（仅 enabled 池子）
    pool_start: Dict[str, int] = {}
    for p in store.pools:
        if p.enabled:
            pool_start[p.pool_id] = p.start_day

    # 筛选：至少一个所属池子的 start_day ≤ final_time
    obtainable: Dict[str, int] = {}
    for cid, qty in target_specs.items():
        for pid in card_pools.get(cid, set()):
            start = pool_start.get(pid)
            if start is not None and start <= final_time:
                obtainable[cid] = qty
                break  # 一个池子开放过即判定为可达

    return obtainable
```

**设计要点：**
- 两层索引（card_pools + pool_start）各只构建一次，O(n+m) 而非 O(n×m)
- `store is None` → 退化为原始 `target_specs`（worker 子进程可能无 store，安全回退）
- `final_time == 0`（纯 no_draw 模拟）→ `start_day == 0` 的池子仍可达，行为正确
- 返回空 dict 时，下游 GDR 自然返回 0.0（非 inf/NaN）

---

### 任务 2：4 个 wrapper 函数 + 注册条目

**文件：** `gacha_simulator/core/gdr.py`

#### 2a. Wrapper 实现（~L475，紧跟 filter 函数之后）

```python
def _gdr_target_achievement_obtainable(compact, target_specs, store=None, **kwargs):
    """简单目标达成率（可达）——分母仅含模拟期间池子已开放的目标卡。"""
    final_time = compact.get('final_time', 0) if isinstance(compact, dict) else getattr(compact, 'final_time', 0)
    obtainable = filter_target_specs_by_obtainable(target_specs, store, final_time)
    return _gdr_target_achievement(compact, obtainable, **kwargs)


def _gdr_target_collection_obtainable(compact, target_specs, store=None, **kwargs):
    """目标卡收集率（可达）——分母仅含可达目标卡种类数。"""
    final_time = compact.get('final_time', 0) if isinstance(compact, dict) else getattr(compact, 'final_time', 0)
    obtainable = filter_target_specs_by_obtainable(target_specs, store, final_time)
    return _gdr_target_collection(compact, obtainable, **kwargs)


def _gdr_all_targets_obtainable(compact, target_specs, store=None, **kwargs):
    """抽出全部目标卡（可达）——判定域仅含可达目标卡。"""
    final_time = compact.get('final_time', 0) if isinstance(compact, dict) else getattr(compact, 'final_time', 0)
    obtainable = filter_target_specs_by_obtainable(target_specs, store, final_time)
    return _gdr_all_targets(compact, obtainable, **kwargs)


def _gdr_weighted_satisfaction_obtainable(compact, target_specs, store=None,
                                           desire_weights=None, miss_cost_weights=None, **kwargs):
    """加权满意度（可达）——仅含可达目标卡，排除不可达卡的 miss_cost 永久惩罚。"""
    final_time = compact.get('final_time', 0) if isinstance(compact, dict) else getattr(compact, 'final_time', 0)
    obtainable = filter_target_specs_by_obtainable(target_specs, store, final_time)
    return _gdr_weighted_satisfaction(compact, obtainable,
                                       desire_weights=desire_weights,
                                       miss_cost_weights=miss_cost_weights,
                                       **kwargs)
```

#### 2b. `GDRDefinition.needs_store` 字段

```python
class GDRDefinition(NamedTuple):
    key: str
    display_name: str
    default_threshold: float
    compute_from_compact: Callable[..., float]
    compute_from_history: Optional[Callable[..., float]] = None
    needs_ssr_ids: bool = False
    needs_weapon_map: bool = False
    needs_weights: str = ''
    category: str = 'basic'
    lower_is_better: bool = False
    compatible_with_min_resource: bool = True
    needs_store: bool = False   # ← 新增：compute_from_compact 需要 store 参数
```

#### 2c. 注册条目

在 `UNIFIED_GDR_REGISTRY` 中追加 4 条（~L620 之后）：

```python
    'target_achievement_obtainable': GDRDefinition(
        key='target_achievement_obtainable',
        display_name='简单目标达成率（可达）',
        default_threshold=1.0,
        compute_from_compact=_gdr_target_achievement_obtainable,
        needs_store=True,
    ),
    'target_collection_obtainable': GDRDefinition(
        key='target_collection_obtainable',
        display_name='目标卡收集率（可达）',
        default_threshold=1.0,
        compute_from_compact=_gdr_target_collection_obtainable,
        needs_store=True,
    ),
    'all_targets_obtainable': GDRDefinition(
        key='all_targets_obtainable',
        display_name='抽出全部目标卡（可达）',
        default_threshold=1.0,
        compute_from_compact=_gdr_all_targets_obtainable,
        needs_store=True,
    ),
    'weighted_satisfaction_obtainable': GDRDefinition(
        key='weighted_satisfaction_obtainable',
        display_name='加权满意度（可达）',
        default_threshold=0.0,
        compute_from_compact=_gdr_weighted_satisfaction_obtainable,
        needs_weights='desire+miss_cost',
        category='weighted',
        needs_store=True,
    ),
```

---

### 任务 3：`compute_gdr_from_compact()` 适配

**文件：** `gacha_simulator/core/gdr.py` ~L819

```python
def compute_gdr_from_compact(
    compact: Union[Dict[str, Any], CompactResult],
    target_specs: Dict[str, int],
    gdr_key: str = 'target_achievement',
    desire_weights: Dict[str, float] = None,
    miss_cost_weights: Dict[str, float] = None,
    card_value_weights: Dict[str, float] = None,
    ssr_ids: Set[str] = None,
    weapon_character_map: Dict[str, str] = None,
    store: 'ConfigStore' = None,      # ← 新增
    **gdr_kwargs,
) -> float:
    _, resource_id = parse_gdr_key(gdr_key)
    defn = resolve_gdr_definition(gdr_key)
    if defn is None:
        return 0.0
    gdr_kwargs.pop('resource_id', None)

    # ← REVIEW-R1-FIX: ISSUE-011 —— needs_store 校验缺失时的可观测性提示
    # filter_target_specs_by_obtainable() 在 store=None 时执行保守回退（返回原始 target_specs），
    # 导致 _obtainable GDR 静默退化为全量版。通过 debug 级别日志提醒调用方：
    if getattr(defn, 'needs_store', False) and store is None:
        logger.debug('GDR %s 需要 store 参数但未传入，回退至全量 target_specs（非可达过滤）', gdr_key)

    # ← needs_store GDR 的过滤解耦说明（ISSUE-006）：
    # compute_gdr_from_compact 不做 auto-filter——过滤由 wrapper 函数（任务 2a）自行执行。
    # 若两处均执行过滤，会形成双重过滤（第二次为 no-op）和两个独立的 final_time 提取点，
    # 增加维护负担与未来不一致风险。此处仅将 store 透传至 wrapper。

    return defn.compute_from_compact(
        compact,
        target_specs=target_specs,
        desire_weights=desire_weights,
        miss_cost_weights=miss_cost_weights,
        card_value_weights=card_value_weights,
        ssr_ids=ssr_ids,
        weapon_character_map=weapon_character_map,
        resource_id=resource_id,
        store=store,      # ← 透传至 wrapper（wrapper 内部自行从 store 提取，此处冗余传入不影响旧函数）
        **gdr_kwargs,
    )
```

**注意：** `store` 通过 `**gdr_kwargs` 传递已经可行（旧函数接受 `**kwargs` 会忽略），但显式传给 `compute_from_compact` 更明确。需要在函数签名中显式列出的原因是旧函数如 `_gdr_target_achievement(compact, target_specs, **kwargs)` 会忽略未知参数——安全。

---

### 任务 3a：`compute_gdr_from_cumulative()` 适配 <!-- REVIEW-R1-FIX: ISSUE-001 -->

**文件：** `gacha_simulator/core/gdr.py` ~L974

`compute_gdr_from_cumulative()` 内部构造 `pseudo_compact` 后调用 `compute_gdr_from_compact()`，但未传递 `store`。用户从 GUI 下拉框选择「（可达）」GDR 后，cumulative_by_pool 路径会静默返回未过滤的全量版结果。

```python
def compute_gdr_from_cumulative(cum_snapshot, target_specs, gdr_key,
                                 desire_weights=None, miss_cost_weights=None,
                                 card_value_weights=None, ssr_ids=None,
                                 weapon_character_map=None,
                                 initial_resources=None,
                                 store=None,                    # ← 新增
                                 **gdr_kwargs):
    # 构造 pseudo_compact <!-- REVIEW-R1-FIX: ISSUE-005 -->
    # 当前代码 L999-1015 中 pseudo_compact 不含 'final_time' 键，
    # 导致 compute_gdr_from_compact 的过滤逻辑读取 final_time=0，
    # 仅 start_day=0 的池子被判定为可达。
    # 修复：pseudo_compact 中新增 'final_time': cum_snapshot.get('pool_end_time', 0)
    #       cumulative_snapshots 中新增 'pool_end_time' 字段（见 streaming.py 适配说明）。
    cum_consumed = cum_snapshot.get('cumulative_consumed', {})
    cum_gained = cum_snapshot.get('cumulative_gained', {})
    final_r = cum_snapshot.get('pool_end_resources', {})
    pseudo_final = {k: final_r.get(k, 0.0) for k in initial_resources} if initial_resources else {}
    pseudo_compact = {
        'card_counts': cum_snapshot.get('cumulative_card_counts', {}),
        'total_draws': cum_snapshot.get('cumulative_draws', 0),
        'pity_triggers': cum_snapshot.get('cumulative_pity_draws', 0),
        'total_consumed': cum_consumed,
        'total_gained': cum_gained,
        'final_resources': pseudo_final,
        'final_time': cum_snapshot.get('pool_end_time', 0),   # ← 新增
        'pool_draw_counts': {},
        'pool_card_counts': {},
        'pool_pity_counts': {},
    }
    return compute_gdr_from_compact(
        pseudo_compact, target_specs, gdr_key,
        desire_weights, miss_cost_weights, card_value_weights,
        ssr_ids, weapon_character_map,
        store=store,                # ← 新增透传
        **gdr_kwargs,
    )
```

**上游调用方适配（`analysis_panel.py` ~L1107）：**

```python
# 原代码：
v = compute_gdr_from_cumulative(
    snap, target_specs, metric_key, ssr_ids=ssr_ids,
    desire_weights=self._store.desire_weights if self._store else None,
    miss_cost_weights=self._store.miss_cost_weights if self._store else None,
    card_value_weights=self._store.card_value_weights if self._store else None,
)
# 修改为：
v = compute_gdr_from_cumulative(
    snap, target_specs, metric_key, ssr_ids=ssr_ids,
    desire_weights=self._store.desire_weights if self._store else None,
    miss_cost_weights=self._store.miss_cost_weights if self._store else None,
    card_value_weights=self._store.card_value_weights if self._store else None,
    store=self._store,            # ← 新增
)
```

`process_trace.py` L243 调用 `compute_gdr_from_cumulative(..., **kwargs)`——通过 `**kwargs` 自动透传，无需修改。

**`streaming.py` 累积快照适配（~L265–274 + ~L279–292）：** <!-- REVIEW-R1-FIX: ISSUE-005 --> <!-- REVIEW-R1-FIX: ISSUE-008 -->

`compute_gdr_from_cumulative` 的 pseudo_compact 需要 `final_time` 字段用于可达过滤，该字段来源于累积快照的 `pool_end_time`。当前 `streaming.py` 的 `cumulative_snapshots` 构造（L265–274 第一处 while 循环，L279–292 第二处剩余池处理循环）不含 `pool_end_time`，需在快照构造前提取局部变量并在两处均新增该字段。

**注意：** 当前代码中 `pool_end_time` 并非命名变量。池子结束时间仅以 `self._sorted_pools[pool_idx][1]` 形式存在于排序元组索引中（L262、L279），从未被提取为独立变量。需要在两处 while 循环的快照构造前分别添加 `pool_end_time = self._sorted_pools[pool_idx][1]`。

```python
# 第一处：t 越过池结束时间的 while 循环（L262–276）
while pool_idx < self._n_pools and t > self._sorted_pools[pool_idx][1]:
    pid = self._sorted_pools[pool_idx][0]
    pool_end_time = self._sorted_pools[pool_idx][1]  # ← 新增：提取池子结束时间
    pool_end_res = compact.get('pool_end_resources', {}).get(pid, {})
    cumulative_snapshots.append({
        'pool_id': pid,
        'cumulative_card_counts': dict(cum_cards),
        'cumulative_draws': cum_draws,
        'cumulative_pity_draws': cum_pity,
        'cumulative_consumed': dict(cum_consumed),
        'cumulative_gained': dict(cum_gained),
        'pool_end_resource': pool_end_res.get('draw_resource', 0.0),
        'pool_end_resources': dict(pool_end_res),
        'pool_end_time': pool_end_time,    # ← 新增：池子结束时间戳，供可达过滤使用
    })
    transition_flags.append(self._check_success(cum_cards))
    pool_idx += 1

# 第二处：剩余池处理循环（L279–293）
while pool_idx < self._n_pools:
    pid = self._sorted_pools[pool_idx][0]
    pool_end_time = self._sorted_pools[pool_idx][1]  # ← 新增：提取池子结束时间
    pool_end_res = compact.get('pool_end_resources', {}).get(pid, {})
    cumulative_snapshots.append({
        'pool_id': pid,
        'cumulative_card_counts': dict(cum_cards),
        'cumulative_draws': cum_draws,
        'cumulative_pity_draws': cum_pity,
        'cumulative_consumed': dict(cum_consumed),
        'cumulative_gained': dict(cum_gained),
        'pool_end_resource': pool_end_res.get('draw_resource', 0.0),
        'pool_end_resources': dict(pool_end_res),
        'pool_end_time': pool_end_time,    # ← 新增：池子结束时间戳，供可达过滤使用
    })
    transition_flags.append(self._check_success(cum_cards))
    pool_idx += 1
```

---

### 任务 3b：`compute_success_probability()` 适配 <!-- REVIEW-R1-FIX: ISSUE-002 -->

**文件：** `gacha_simulator/core/gdr.py` ~L924

`compute_success_probability()` 遍历历史数据并逐条调用 `compute_gdr_from_compact()`，但未传递 `store`。若用户传入 `_obtainable` GDR key，过滤不会生效。

```python
def compute_success_probability(
    histories,
    target_specs: Dict[str, int],
    gdr_key: str = 'target_achievement',
    gdr_threshold: float = 1.0,
    desire_weights: Dict[str, float] = None,
    miss_cost_weights: Dict[str, float] = None,
    card_value_weights: Dict[str, float] = None,
    ssr_ids: Set[str] = None,
    weapon_character_map: Dict[str, str] = None,
    store: 'ConfigStore' = None,      # ← 新增
) -> float:
    # ... 前置逻辑不变 ...
    for h in valid:
        val = compute_gdr_from_compact(
            h, target_specs, gdr_key,
            desire_weights, miss_cost_weights, card_value_weights,
            ssr_ids, weapon_character_map,
            store=store,               # ← 新增透传
        )
    # ... 后续逻辑不变 ...
```

---

### 任务 4：`GDRCalculator` + `make_gdr_calculator` 适配

**文件：** `gacha_simulator/core/gdr.py`

#### 4a. `GDRCalculator.__init__()` — 新增 `store` 参数

```python
class GDRCalculator:
    def __init__(self, target_specs, gdr_key='target_achievement',
                 gdr_threshold=None,
                 desire_weights=None, miss_cost_weights=None,
                 card_value_weights=None, ssr_ids=None,
                 weapon_character_map=None,
                 store=None):          # ← 新增
        self.target_specs = target_specs
        self.gdr_key = gdr_key
        self.desire_weights = desire_weights
        self.miss_cost_weights = miss_cost_weights
        self.card_value_weights = card_value_weights
        self.ssr_ids = ssr_ids
        self.weapon_character_map = weapon_character_map
        self.store = store             # ← 新增

        defn = resolve_gdr_definition(gdr_key)
        if gdr_threshold is None:
            self.gdr_threshold = defn.default_threshold if defn else 1.0
        else:
            self.gdr_threshold = gdr_threshold
        self.lower_is_better = defn.lower_is_better if defn else False
```

#### 4b. `GDRCalculator.compute_gdr()` — 透传 `store`

```python
    def compute_gdr(self, compact_or_aggregate):
        return compute_gdr_from_compact(
            compact_or_aggregate,
            target_specs=self.target_specs,
            gdr_key=self.gdr_key,
            desire_weights=self.desire_weights,
            miss_cost_weights=self.miss_cost_weights,
            card_value_weights=self.card_value_weights,
            ssr_ids=self.ssr_ids,
            weapon_character_map=self.weapon_character_map,
            store=self.store,          # ← 新增
        )
```

#### 4c. `make_gdr_calculator()` — 透传 `store`

`make_gdr_calculator` 已有 `store` 参数（用于提取权重），只需新增一行：

```python
def make_gdr_calculator(store, target_specs, gdr_key, *,
                         gdr_threshold=None, ssr_ids=None,
                         weapon_character_map=None) -> GDRCalculator:
    return GDRCalculator(
        target_specs=target_specs,
        gdr_key=gdr_key,
        gdr_threshold=gdr_threshold,
        desire_weights=store.desire_weights,
        miss_cost_weights=store.miss_cost_weights,
        card_value_weights=store.card_value_weights,
        ssr_ids=ssr_ids,
        weapon_character_map=weapon_character_map,
        store=store,              # ← 新增
    )
```

---

### 任务 5：`get_expanded_gdr_entries()` 计数更新

**文件：** `gacha_simulator/core/gdr.py` ~L681

`get_expanded_gdr_entries()` 遍历 `UNIFIED_GDR_REGISTRY`，新增 4 条自动纳入。仅需更新 docstring 中的计数：

```python
def get_expanded_gdr_entries(resource_defs=None):
    """返回展开后的 GDR 条目列表 [(key, display_name, lower_is_better, default_threshold)]。

    纯函数，不修改全局状态。
    - resource_defs 为 None → 21 条（原 17 + 4 可达变体）
    - resource_defs 不为 None → 资源类 GDR 按资源类型展开为 :qualified 条目

    >>> entries = get_expanded_gdr_entries()
    >>> len(entries)
    21                           # P62 后 17→21
    >>> entries = get_expanded_gdr_entries({'draw_resource': '抽卡资源', 'exchange_currency': '兑换货币'})
    >>> len(entries)
    25                           # P62 后 21→25
    """
```

以及相应的 `test_get_expanded_gdr_entries` 期望值从 17 → 21。

> <!-- REVIEW-R1-FIX: ISSUE-010 --> **ISSUE-010 补充：** 上述 docstring 中的 `>>>` doctest 示例数值同步更新（17→21, 21→25），确保可执行文档与注册表实际条目数一致。若项目后续启用 `--doctest-modules`，这些断言可直接验证。

---

### 任务 6：测试

**文件：** `tests/core/test_gdr.py`，在文件末尾追加（现有测试全保留）

```python
# ═══════════════════════════════════════════════════════════════════
# P62 可达目标卡筛选测试
# ═══════════════════════════════════════════════════════════════════

from gacha_simulator.core.config_store import ConfigStore, CardDefEntry, PoolEntry


def _make_store_for_p62():
    """P62 测试专用 ConfigStore fixture：
    - card_a: 仅池子 pool_early (day 0–10)
    - card_b: 仅池子 pool_late (day 100–120)
    - card_c: 同时属于两个池子
    - pool_disabled: enabled=False，不应使 card_d 变为可达
    """
    store = ConfigStore()
    store.card_defs = [
        CardDefEntry(card_id='card_a', pools=['pool_early']),
        CardDefEntry(card_id='card_b', pools=['pool_late']),
        CardDefEntry(card_id='card_c', pools=['pool_early', 'pool_late']),
        CardDefEntry(card_id='card_d', pools=['pool_disabled']),
    ]
    store.pools = [
        PoolEntry(pool_id='pool_early', start_day=0, end_day=10, enabled=True),
        PoolEntry(pool_id='pool_late', start_day=100, end_day=120, enabled=True),
        PoolEntry(pool_id='pool_disabled', start_day=0, end_day=10, enabled=False),
    ]
    return store


class TestFilterTargetSpecsByObtainable:
    """filter_target_specs_by_obtainable() 单元测试"""

    def test_all_obtainable_when_early_stop(self):
        """final_time=5: 仅 pool_early 已开放 → card_a + card_c 可达"""
        from gacha_simulator.core.gdr import filter_target_specs_by_obtainable
        store = _make_store_for_p62()
        result = filter_target_specs_by_obtainable(
            {'card_a': 1, 'card_b': 1, 'card_c': 2},
            store, final_time=5.0,
        )
        assert result == {'card_a': 1, 'card_c': 2}
        assert 'card_b' not in result

    def test_all_obtainable_when_long_run(self):
        """final_time=110: 两个池子均开放 → 全部可达"""
        from gacha_simulator.core.gdr import filter_target_specs_by_obtainable
        store = _make_store_for_p62()
        result = filter_target_specs_by_obtainable(
            {'card_a': 1, 'card_b': 1, 'card_c': 2},
            store, final_time=110.0,
        )
        assert result == {'card_a': 1, 'card_b': 1, 'card_c': 2}

    def test_none_obtainable(self):
        """final_time=-1: 无任何池子开放 → 返回空 dict"""
        from gacha_simulator.core.gdr import filter_target_specs_by_obtainable
        store = _make_store_for_p62()
        result = filter_target_specs_by_obtainable({'card_a': 1}, store, final_time=-1.0)
        assert result == {}

    def test_disabled_pool_ignored(self):
        """card_d 仅在 disabled 池子中 → 不可达"""
        from gacha_simulator.core.gdr import filter_target_specs_by_obtainable
        store = _make_store_for_p62()
        result = filter_target_specs_by_obtainable({'card_d': 1}, store, final_time=5.0)
        assert result == {}

    def test_store_none_fallback(self):
        """store=None → 返回原始 target_specs（保守回退）"""
        from gacha_simulator.core.gdr import filter_target_specs_by_obtainable
        result = filter_target_specs_by_obtainable({'card_a': 1, 'card_b': 1}, None, final_time=5.0)
        assert result == {'card_a': 1, 'card_b': 1}

    def test_empty_target_specs(self):
        """空 target_specs → 返回空"""
        from gacha_simulator.core.gdr import filter_target_specs_by_obtainable
        store = _make_store_for_p62()
        result = filter_target_specs_by_obtainable({}, store, final_time=5.0)
        assert result == {}

    def test_cross_pool_card_counted_once(self):
        """card_c 出现在两个池子中，只要一个开放即判定可达（不重复计数）"""
        from gacha_simulator.core.gdr import filter_target_specs_by_obtainable
        store = _make_store_for_p62()
        result = filter_target_specs_by_obtainable({'card_c': 3}, store, final_time=5.0)
        assert result == {'card_c': 3}
        assert len(result) == 1

    def test_final_time_zero_pool_start_zero_still_obtainable(self):
        """final_time=0, pool start_day=0 → 可达（no_draw 场景）"""
        from gacha_simulator.core.gdr import filter_target_specs_by_obtainable
        store = _make_store_for_p62()
        result = filter_target_specs_by_obtainable({'card_a': 1}, store, final_time=0.0)
        assert result == {'card_a': 1}


class TestObtainableGdrComputation:
    """通过 compute_gdr_from_compact 端到端验证 4 个可达 GDR"""

    def _make_compact(self, card_counts, final_time=5.0):
        return {
            'card_counts': card_counts,
            'final_time': final_time,
            'total_consumed': {'draw_resource': 1600},
            'final_resources': {'draw_resource': 0},
            'pool_draw_counts': {},
            'pool_card_counts': {},
            'total_draws': 10,
        }

    # ── target_achievement_obtainable ──

    def test_target_achievement_obtainable_full(self):
        """全量 3 张目标卡，仅 card_a 可达 → 分母仅含 card_a 的 qty"""
        from gacha_simulator.core.gdr import compute_gdr_from_compact
        store = _make_store_for_p62()
        compact = self._make_compact({'card_a': 1, 'card_b': 0, 'card_c': 0})
        target_specs = {'card_a': 1, 'card_b': 1, 'card_c': 2}   # 全量 sum(qty)=4
        # 可达子集: {'card_a': 1} → sum(qty)=1
        val = compute_gdr_from_compact(
            compact, target_specs, 'target_achievement_obtainable', store=store,
        )
        assert val == pytest.approx(1.0)   # 1/1 = 100%

    def test_target_achievement_obtainable_partial(self):
        """card_c 可达(qty=2)，只抽到 1 张 → 50%"""
        from gacha_simulator.core.gdr import compute_gdr_from_compact
        store = _make_store_for_p62()
        compact = self._make_compact({'card_a': 0, 'card_b': 0, 'card_c': 1})
        target_specs = {'card_a': 1, 'card_b': 1, 'card_c': 2}
        val = compute_gdr_from_compact(
            compact, target_specs, 'target_achievement_obtainable', store=store,
        )
        assert val == pytest.approx(0.5)   # min(1,2)/2 = 0.5

    def test_target_achievement_obtainable_zero_obtainable(self):
        """无任何可达卡 → 返回 0.0"""
        from gacha_simulator.core.gdr import compute_gdr_from_compact
        store = _make_store_for_p62()
        compact = self._make_compact({'card_a': 3}, final_time=-1.0)
        val = compute_gdr_from_compact(
            compact, {'card_a': 1}, 'target_achievement_obtainable', store=store,
        )
        assert val == 0.0  # 非 NaN/非 inf

    # ── target_collection_obtainable ──

    def test_target_collection_obtainable(self):
        """5 种全量目标卡，2 种可达 → 收集 1 种 → 50%"""
        from gacha_simulator.core.gdr import compute_gdr_from_compact
        store = _make_store_for_p62()
        compact = self._make_compact({'card_a': 1, 'card_c': 0})
        target_specs = {'card_a': 1, 'card_b': 1, 'card_c': 2}   # 全量 3 种
        # 可达: card_a + card_c = 2 种
        val = compute_gdr_from_compact(
            compact, target_specs, 'target_collection_obtainable', store=store,
        )
        assert val == pytest.approx(0.5)   # 1/2

    # ── all_targets_obtainable ──

    def test_all_targets_obtainable_success(self):
        """可达卡全部达标 → 1.0"""
        from gacha_simulator.core.gdr import compute_gdr_from_compact
        store = _make_store_for_p62()
        compact = self._make_compact({'card_a': 1, 'card_c': 2})
        target_specs = {'card_a': 1, 'card_b': 1, 'card_c': 2}
        val = compute_gdr_from_compact(
            compact, target_specs, 'all_targets_obtainable', store=store,
        )
        assert val == 1.0

    def test_all_targets_obtainable_fail(self):
        """card_c 可达但不足 → 0.0"""
        from gacha_simulator.core.gdr import compute_gdr_from_compact
        store = _make_store_for_p62()
        compact = self._make_compact({'card_a': 1, 'card_c': 1})
        target_specs = {'card_a': 1, 'card_b': 1, 'card_c': 2}
        val = compute_gdr_from_compact(
            compact, target_specs, 'all_targets_obtainable', store=store,
        )
        assert val == 0.0

    # ── weighted_satisfaction_obtainable ──

    def test_weighted_satisfaction_obtainable_no_permanent_penalty(self):
        """不可达卡不产生 miss_cost 惩罚——与全量版对比验证"""
        from gacha_simulator.core.gdr import compute_gdr_from_compact
        store = _make_store_for_p62()
        compact = self._make_compact({'card_a': 1, 'card_c': 2})
        target_specs = {'card_a': 1, 'card_b': 1, 'card_c': 2}
        desire = {'card_a': 1.0, 'card_b': 1.0, 'card_c': 1.0}
        miss = {'card_a': 2.0, 'card_b': 2.0, 'card_c': 2.0}

        # 全量版：card_b 不可达 → missed=1 → −2.0 惩罚
        val_full = compute_gdr_from_compact(
            compact, target_specs, 'weighted_satisfaction',
            desire_weights=desire, miss_cost_weights=miss,
        )
        # 可达版：card_b 被排除 → 无惩罚
        val_obt = compute_gdr_from_compact(
            compact, target_specs, 'weighted_satisfaction_obtainable',
            desire_weights=desire, miss_cost_weights=miss, store=store,
        )
        # 可达版 ≥ 全量版（排除了负向惩罚项）
        assert val_obt > val_full

    # ── 向后兼容 ──

    def test_store_none_fallback_original(self):
        """store=None 时，_obtainable GDR 回退到原始 target_specs，值与原版相同"""
        from gacha_simulator.core.gdr import compute_gdr_from_compact
        compact = self._make_compact({'card_a': 1, 'card_b': 0, 'card_c': 0})
        target_specs = {'card_a': 1, 'card_b': 1, 'card_c': 2}

        val_full = compute_gdr_from_compact(compact, target_specs, 'target_achievement')
        val_obt = compute_gdr_from_compact(compact, target_specs, 'target_achievement_obtainable')
        # store=None 时 filter 返回原始 target_specs → 结果应相同
        assert val_obt == pytest.approx(val_full)

    def test_gdr_calculator_with_store(self):
        """GDRCalculator 传入 store → compute_gdr 使用可达过滤"""
        from gacha_simulator.core.gdr import GDRCalculator
        store = _make_store_for_p62()
        calc = GDRCalculator(
            {'card_a': 1, 'card_b': 1, 'card_c': 2},
            gdr_key='target_achievement_obtainable',
            store=store,
        )
        compact = self._make_compact({'card_a': 1, 'card_b': 0, 'card_c': 0})
        val = calc.compute_gdr(compact)
        assert val == pytest.approx(1.0)  # 仅 card_a 可达，1/1

    def test_make_gdr_calculator_obtainable(self):
        """make_gdr_calculator + _obtainable GDR 端到端"""
        from gacha_simulator.core.gdr import make_gdr_calculator
        store = _make_store_for_p62()
        calc = make_gdr_calculator(store, {'card_a': 1, 'card_b': 1, 'card_c': 2},
                                    'target_achievement_obtainable')
        compact = self._make_compact({'card_a': 1, 'card_b': 0, 'card_c': 0})
        val = calc.compute_gdr(compact)
        assert val == pytest.approx(1.0)
```

---

### 任务 7：现有测试期望值修正

#### 7a. `test_get_expanded_gdr_entries` 中的计数

- **`tests/core/test_gdr.py` L351:** `assert len(entries) == 17` → `assert len(entries) == 21`
- **`tests/core/test_gdr.py` L359:** `assert len(entries) == 21` → `assert len(entries) == 25`
- **`tests/core/test_gdr.py` L552:** `assert combo.count() == 21` → `assert combo.count() == 25`

#### 7b. 确认无其他硬编码 17 的引用

需要 grep 确认：
```bash
rg "== 17|== 21" tests/  # 检查是否有其他文件硬编码注册表容量
```

---

### 任务 8：`_build_legacy_registries()` 兼容

`gdr.py` ~L732 的 `_build_legacy_registries()` 遍历所有注册条目构建 `GDR_REGISTRY` 和 `COMPACT_GDR_REGISTRY`。`compute_from_history=None` 的条目仅加入 `COMPACT_GDR_REGISTRY`。4 个新条目的 `compute_from_history=None`，因此仅出现在 compact 路径——正确。

无需修改。

---

## 四、波及范围

| 文件 | 变更 | 行数 |
|------|------|------|
| `core/gdr.py` | `filter_target_specs_by_obtainable()`（+35） + 4 wrapper（+30） + 4 注册条目（+35） + `GDRDefinition.needs_store`（+1） + `compute_gdr_from_compact()` 适配（+8） + `compute_gdr_from_cumulative()` 适配（+3）+ `compute_success_probability()` 适配（+3）+ `GDRCalculator.__init__`（+2） + `GDRCalculator.compute_gdr`（+1） + `make_gdr_calculator`（+1） + docstring（~2） | **+121 / ~3** |
| `gui/analysis_panel.py` | `cumulative_by_pool` 调用 `compute_gdr_from_cumulative()` 时新增 `store=self._store`（+1） | **+1** |
| `core/streaming.py` | 两处 while 循环各新增 `pool_end_time` 变量提取（+2） + 两处 `cumulative_snapshots` 字典各新增 `pool_end_time` 字段（+2） <!-- REVIEW-R1-FIX: ISSUE-005 --> <!-- REVIEW-R1-FIX: ISSUE-008 --> | **+4** |
| `tests/core/test_gdr.py` | 新增 `TestFilterTargetSpecsByObtainable`（8 用例） + `TestObtainableGdrComputation`（10 用例） + 3 处计数修正 | **+180 / ~3** |

**不涉及：** `config_store.py`（只读使用）、`process_trace.py`（通过 `**kwargs` 自动透传 `store`，无需修改）、`make_gdr_calculator` 的所有现有调用方（新增 `store` 参数已有默认值 `None`）。

<!-- REVIEW-R1-FIX: ISSUE-012 --> **ISSUE-012 补充：** `gui/process_analysis_panel.py` L515 同样调用 `compute_pool_gdr_cumulative()`（经 `process_trace` 转发），与 `analysis_panel.py` L1107 处于对称位置。该调用站通过 `**gdr_kwargs` 透传参数，`store=None` 默认值保证行为安全，无需代码修改。与 `analysis_panel.py` 主动传入 `store=self._store` 不同，此面板目前不主动传入 `store`。未来如需在此面板的累积路径上支持 `_obtainable` GDR 正确过滤，需追加 `store` 传入。

**已核实无需修改——GDRCalculator 直接构造站（`store=None` 默认值保证行为安全）：** <!-- REVIEW-R1-FIX: ISSUE-009 -->
- `streaming.py` L21-25 `StreamingSuccessCounter.__init__`：直接构造 `GDRCalculator(target_specs, gdr_key, ...)` 不传 `store`，默认值为 `None`，`filter_target_specs_by_obtainable` 执行保守回退，行为安全。
- `streaming.py` L131-135 `extract_process`：同上，直接构造 `GDRCalculator` 不传 `store`，行为安全。
- `vulnerability.py` L521-527 `compute_vulnerability_analysis`：直接构造 `GDRCalculator(target_specs=target_specs, gdr_key=gdr_key, ...)` 不传 `store`，行为安全。

上述 3 处均为现有调用站，`store` 参数具有 `None` 默认值，子进程/流式分析场景中不传 `store` 时 `filter_target_specs_by_obtainable()` 返回原始 `target_specs`（保守回退），不产生错误。无需代码修改。

**间接涉及（`store=None` 退化安全）：** `per_pool_analysis.py` 的 `compute_transition_flags_from_gdr`（~L317）通过 `compute_pool_gdr_cumulative` → `compute_gdr_from_cumulative` 间接到达 `compute_gdr_from_compact`。自身累积快照不含 `pool_end_time` 且不传 `store`，`filter_target_specs_by_obtainable` 返回原始 `target_specs`（store=None 回退），`_obtainable` GDR 值退化为全量版——行为安全但并非真正的可达过滤。本计划不要求修改此文件代码，但需在验收标准中验证此退化路径不会静默产生错误。 <!-- REVIEW-R1-FIX: ISSUE-007 -->

> **波及注意：** `compute_gdr_from_cumulative()` 和 `compute_success_probability()` 是 `gdr.py` 内部调用 `compute_gdr_from_compact()` 的另外两条路径。两者均需新增 `store` 参数并透传，否则 `needs_store=True` 的 GDR 在这两条路径上静默退化到全量版。`analysis_panel.py` L1107 作为 `compute_gdr_from_cumulative()` 的直接调用方，需同步传入 `store=self._store`。此外 `compute_gdr_from_cumulative` 的 `pseudo_compact` 需新增 `final_time` 字段（从 `cum_snapshot['pool_end_time']` 提取），对应 `streaming.py` 两处 while 循环各需新增 `pool_end_time` 变量提取（`self._sorted_pools[pool_idx][1]`）及字典字段写入，否则 cumulative 路径上过滤逻辑读取 `final_time=0` 产生错误结果。 <!-- REVIEW-R1-FIX: ISSUE-003, ISSUE-005, ISSUE-008 -->

---

## 五、实施阶段

| 阶段 | 任务 | 预估 |
|------|------|------|
| **A** | 任务 1：`filter_target_specs_by_obtainable()` 实现 | 30 min |
| **B** | 任务 2：4 wrapper + `GDRDefinition.needs_store` + 注册条目 | 45 min |
| **C** | 任务 3+3a+3b+4+5：`compute_gdr_from_compact()` + `compute_gdr_from_cumulative()`（含 `pseudo_compact` 新增 `final_time`） + `compute_success_probability()` + `GDRCalculator` + `make_gdr_calculator` + `streaming.py` 两处 while 循环各提取 `pool_end_time` 变量 + 累积快照新增字段 + 计数 docstring <!-- REVIEW-R1-FIX: ISSUE-005 --> <!-- REVIEW-R1-FIX: ISSUE-008 --> | 45 min |
| **D** | 任务 6–7：18 个测试用例 + 3 处计数修正 | 60 min |
| **E** | 验证：`pytest tests/core/test_gdr.py -v` 全部通过 + 手动 GUI 冒烟（打开统计分析面板，确认下拉框多出 4 个条目，切换 cumulative_by_pool 确认可达版 GDR 数值正确） | 15 min |

**总预估：3.25 小时**

---

## 六、风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| `store` 在 worker 子进程中不可用 | 低 | `store=None` 时 `filter_target_specs_by_obtainable()` 返回原始 `target_specs`——退化到原版行为，不产生错误 |
| 注册表从 21 → 25 条（`get_expanded_gdr_entries` 含多资源展开时），UI 下拉框宽度 | 低 | 统计分析面板已有 21 条（资源展开后），25 条增量可忽略；`populate_gdr_combo` 无硬编码上限 |
| 旧代码直接调 `compute_gdr_from_compact(..., store=xxx)` 不传 `store` | 低 | `store` 默认 `None`——参数缺失 = 退化为原始行为 |
| `final_time` 在 dict 格式 compact 中缺失 | 中 | normal compact 路径（CompactResult/dict）的 `final_time` 通常由 simulation runner 写入，风险低；cumulative 路径的 `pseudo_compact` 当前不含 `final_time`，需 streaming.py 两处 while 循环分别提取 `pool_end_time = self._sorted_pools[pool_idx][1]` 并写入快照字典，再由 `compute_gdr_from_cumulative` 映射至 `pseudo_compact['final_time']`（见 ISSUE-005/ISSUE-008 修复）。若遗漏此字段，cumulative_by_pool 面板的可达 GDR 将仅判定 `start_day=0` 的池子可达 | <!-- REVIEW-R1-FIX: ISSUE-005 --> <!-- REVIEW-R1-FIX: ISSUE-008 -->

---

## 七、验收标准

- [ ] `filter_target_specs_by_obtainable()` 8 个边界测试通过
- [ ] 4 个 `_obtainable` GDR 端到端计算正确 —— 与手工过滤 `target_specs` 后调用原版一致
- [ ] `GDRCalculator(store=store)` + `_obtainable` key → 三方法行为正确
- [ ] `make_gdr_calculator(store, ..., 'target_achievement_obtainable')` 端到端通过
- [ ] 零可达卡 → `target_achievement_obtainable` 返回 `0.0`（非 inf/NaN）
- [ ] `store=None` 时 `_obtainable` GDR 值 == 原版值（向后兼容）
- [ ] `compute_gdr_from_cumulative(..., store=store)` 路径正确过滤——cumulative_by_pool 面板下拉选择「（可达）」GDR 后数值与全量版有差异（若存在不可达卡） <!-- REVIEW-R1-FIX: ISSUE-001 -->
- [ ] `compute_success_probability(..., store=store)` 路径正确过滤——使用 `_obtainable` GDR key 时成功率基于可达子集计算 <!-- REVIEW-R1-FIX: ISSUE-002 -->
- [ ] `per_pool_analysis.py` transition_flags 路径上使用 `_obtainable` GDR key 且 `store=None` 时，回退行为已验证——值等于全量版，不会静默产生 NaN/0 等异常值 <!-- REVIEW-R1-FIX: ISSUE-007 -->
- [ ] 现有 596 行测试全部通过（`test_gdr.py`）
- [ ] GUI 下拉框自动出现 4 个「（可达）」条目，无需代码修改
- [ ] `ruff check` 通过
- [ ] `CLAUDE.md` GDR 小节同步更新：补充 `needs_store` 字段用途说明 + `filter_target_specs_by_obtainable()` 公共函数签名与可达判定规则 <!-- REVIEW-R1-FIX: ISSUE-004 -->

---

## ⚠ 自动化审查阻塞项

> 原因：4 轮对抗循环未收敛。以下 2 个问题经多轮 Finder → Fixer → Verifier 迭代后仍存在分歧，标记为阻塞项供人工决策。

### ISSUE-010 — `get_expanded_gdr_entries()` doctest 与 docstring 文本同步

| 维度 | 详情 |
|------|------|
| **维度** | 文档同步 |
| **状态** | 未收敛 |

**问题描述：**

计划任务 5 更新了 `get_expanded_gdr_entries()` 的 docstring 文本描述（17 -> 21 条，21 -> 25 条），但未处理现有的 `>>>` doctest 示例。当前代码 L688-693 包含可执行的 doctest 断言 `len(entries) == 17` 和 `len(entries) == 21`。

计划展示的新 docstring 中已移除 `>>>` 示例。若实施者按计划逐字替换 docstring，这些 doctest 将被**静默删除**；若实施者保留但未更新数值，则 doctest 断言**错误**（17 vs 21、21 vs 25）。

**影响评估：**

该项目的 `pyproject.toml` 中未配置 `--doctest-modules`，因此不会引发 CI 失败。但会留下：
- 方案 A（逐字替换）：doctest 示例丢失，文档完整性下降
- 方案 B（保留旧值）：可执行文档断言与实际注册表容量不一致，产生误导

**待决策：**

1. 是否在计划的新 docstring 中显式保留并更新 `>>>` doctest 示例（17 -> 21, 21 -> 25）？
2. 是否在 `pyproject.toml` 中启用 `--doctest-modules` 以自动验证此类断言？

---

### ISSUE-011 — `GDRDefinition.needs_store` 退化路径缺乏可观测性

| 维度 | 详情 |
|------|------|
| **维度** | 逻辑闭合 |
| **状态** | 未收敛 |

**问题描述：**

计划新增 `GDRDefinition.needs_store` 字段用于标识需要 `ConfigStore` 的 GDR。然而，`compute_gdr_from_compact()` 在解析 `GDRDefinition` 后并**不检查** `defn.needs_store` 标志。

当 `store=None` 且 `needs_store=True` 时，`filter_target_specs_by_obtainable()` 执行保守回退（返回原始 `target_specs`），导致 `_obtainable` GDR **静默返回与全量版相同的结果**。

**影响评估：**

调用方无法感知此退化：
- 无日志警告
- 无异常抛出
- 返回值与全量版 GDR 完全相同

在调试场景中可能造成困惑——用户在 GUI 下拉框中勾选了「（可达）」版却得到与全量版相同的数值，且缺乏任何提示说明原因。

**计划中的处理方式：**

该退化行为在计划中被标注为「安全回退」，但缺少可观测性支撑。计划任务 3 的代码展示中已包含一条 `logger.debug()` 日志（L239），但：
- `debug` 级别日志在默认配置下不可见
- 该日志仅在 `compute_gdr_from_compact()` 中存在，`GDRCalculator` / `make_gdr_calculator` / `compute_success_probability` / `compute_gdr_from_cumulative` 路径均不产生相同提示

**待决策：**

1. 是否将日志级别从 `debug` 提升为 `warning`？
2. 是否在其他调用路径（`GDRCalculator.compute_gdr`、`compute_success_probability`、`compute_gdr_from_cumulative`）中同步添加可观测性提示？
3. 是否接受「安全回退 = 无需提示」的设计哲学？

---

## 自动化审查记录

<details>
<summary>第 1 次审查（2026-06-11）——P38 工作流自动化</summary>

- 复杂度: medium | 变更性质: evolutionary
- 阶段 1 影响面: 0 个发现
- 阶段 2 对抗循环: 4 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 12 个

</details>
