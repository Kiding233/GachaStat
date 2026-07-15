<!-- META: P62 | module:GDR系统 | status:designing | last:2026-07-14 -->

# P62 可达目标卡筛选——GDR分母区分全量与池子开放子集

> 日期：2026-07-14 | 状态：设计中
> 触发：目标卡相关 GDR 公式分母始终使用全部目标卡，未区分「池子窗口在模拟期间曾开放过」的可达卡与「池子从未开放」的不可达卡，导致指标中混入不可达噪声。

## 一、问题

当前所有目标卡相关 GDR 的分母为 `target_specs` 全集（用户配置的全部目标卡）。但一次模拟中，某些目标卡所属的全部池子在模拟结束前均未开放（`start_day > final_time`），这些卡在本次模拟中根本不可能获得。

**判定逻辑：** 以池子时间窗口 `start_day ≤ final_time` 为依据——池子开放过但策略选择不抽，该卡仍记入分母，正确暴露策略遗漏。不可混淆为 `pool_draw_counts[pool_id] > 0`（策略实际是否抽取）。

**典型场景：** 10 张目标卡分布在 3 个池子（A: day 0–21 / B: day 0–21 / C: day 100–121），sim 跑了 21 天 → C 池从未开放 → C 中的卡应排除出分母 → 可达目标卡为 A+B 的子集。

### 受影响的 GDR（4 个）

逐条审查 17 个 UNIFIED_GDR_REGISTRY 条目，确认仅 4 个因不可达卡产生分母/判定域偏差：

| GDR | 不可达卡的影响 | 根因 |
|-----|--------------|------|
| `target_achievement` | 分母 `sum(qty)` 虚增 | 不可达卡 qty 计入分母，分子贡献恒为 0 |
| `target_collection` | 分母 `len(target_specs)` 虚增 | 不可达卡种类计入分母，`got` 恒为 0 |
| `all_targets` | 返回值恒为 0 | 不可达卡永远不达标 |
| `weighted_satisfaction` | 系统性惩罚不可消除 | 不可达卡产生 `−qty × miss_cost` 永久惩罚 |

### 不受影响的 13 个

| 不受影响原因 | GDR |
|-------------|-----|
| `target_specs` 仅用于迭代，不可达卡贡献恒为 0 → 数学等价 | `extra_target`、`target_card_draws`、`resource_efficiency`、`resource_per_card` |
| 不使用 `target_specs` | `ssr_collection`、`resource_remaining`、`resource_consumed`、`non_pity_draws`、`pity_draws`、`weapon_character_ratio`、`draw_conversion_efficiency` |
| 分母非 `target_specs`，不可达卡仅在分子中缺位 | `per_pool_draw_rate` |
| 迭代域是 `card_counts` 非 `target_specs` | `total_card_value` |

## 二、目标

1. 新增 `filter_target_specs_by_obtainable()` 工具函数，依据「池子时间窗口是否在模拟结束前已开放」筛选可达目标卡
2. 新增 4 个 `_obtainable` 后缀 GDR key，注册到 `UNIFIED_GDR_REGISTRY`
3. 统计分析面板无需新 UI——复用现有多选+并排出图能力，用户同时勾选全量版和可达版即可对比
4. 零可达卡、多池共享卡片等边界情况有明确定义和处理

## 三、方案

### UX 决策：注册新 key，不设 checkbox

统计分析面板本身支持多 GDR 同时选中、多图并排展示。注册新 key 后，下拉框自然多出 4 个「（可达）」条目，用户勾选全量版 + 可达版即可并排对比——无需切换、无需新增 UI 控件。

### 阶段一：核心函数 —— `filter_target_specs_by_obtainable()`

**新增位置：** `gacha_simulator/core/gdr.py`

```python
def filter_target_specs_by_obtainable(
    target_specs: Dict[str, int],
    store: ConfigStore,
    final_time: float,
) -> Dict[str, int]:
```

**判定逻辑：**
1. 从 `store.card_defs` 构建 `card_id → set(pool_ids)` 索引
2. 从 `store.pools` 构建 `pool_id → (start_day, end_day)` 映射（仅 `enabled=True` 的池子）
3. 对每张目标卡，若存在至少一个所属池子的 `start_day ≤ final_time`，则该卡「可达」
4. 返回仅包含可达卡的子集

**边界情况：**
- `obtainable` 为空 → 返回空 dict，调用方负责处理（`target_achievement` 等自然返回 0.0）
- 同一张卡出现在多个池子中 → 只要至少一个池子开放过即为可达
- `store` 为 None → 返回原始 `target_specs`（保守回退，不缩小分母）
- `final_time == 0`（纯 no_draw 模拟）→ start_day=0 的池子仍可达

### 阶段二：4 个可达变体 wrapper + 注册

每个 wrapper 先调用 `filter_target_specs_by_obtainable()` 过滤 `target_specs`，再委托原版计算：

| 新 key | 委托原函数 | 公式变化 |
|--------|-----------|---------|
| `target_achievement_obtainable` | `_gdr_target_achievement` | 分母 `Σ_{T} qty` → `Σ_{O} qty` |
| `target_collection_obtainable` | `_gdr_target_collection` | 分母 `|T|` → `|O|` |
| `all_targets_obtainable` | `_gdr_all_targets` | 判定域 `T` → `O` |
| `weighted_satisfaction_obtainable` | `_gdr_weighted_satisfaction` | 迭代域 `T` → `O`，排除不可达卡惩罚 |

`GDRDefinition.needs_store = True` 新增标志位——告知 `compute_gdr_from_compact()` 调用方必须传入 `store` 参数，否则回退到原始 `target_specs`。

```python
GDRDefinition(NamedTuple):
    ...
    needs_store: bool = False   # ← 新增字段
```

`compute_gdr_from_compact()` 中：
```python
if defn.needs_store and store is not None:
    final_time = compact.get('final_time', 0) if isinstance(compact, dict) else compact.final_time
    target_specs = filter_target_specs_by_obtainable(target_specs, store, final_time)
```

### 阶段三：GDRCalculator + make_gdr_calculator 接入

`GDRCalculator.__init__()` 新增 `store: Optional[ConfigStore] = None` 参数，`compute_gdr()` 透传。

`make_gdr_calculator()` 已有 `store` 参数，无需变更签名——`store` 已传入构造器。

### 阶段四：GUI

**零 UI 变更。** `populate_gdr_combo()` 遍历 `UNIFIED_GDR_REGISTRY` 时自动纳入 4 个新条目。下拉框从 17 条变为 21 条（`get_expanded_gdr_entries()` 中资源类展开后更多，但结构不变）。

统计分析面板、过程分析面板、方案搜索面板等所有调用 `populate_gdr_combo()` 的地方自动获得新选项，无需逐个修改。

### 阶段五：测试

- `filter_target_specs_by_obtainable()` 单元测试：正常可达、全部不可达、部分可达、多池共享、空 target_specs、disabled 池子
- 4 个 wrapper 集成测试：与手工过滤后调用原版的结果一致
- 边界测试：零可达卡 → `target_achievement_obtainable` 返回 0.0（非 inf/NaN）
- `store=None` 回退测试：wrapper 返回与原版相同

## 四、波及范围

| 文件 | 变更 | 行数估算 |
|------|------|---------|
| `core/gdr.py` | `filter_target_specs_by_obtainable()` + 4 个 wrapper + 4 个注册条目 + `GDRDefinition.needs_store` + `compute_gdr_from_compact()` 参数 | +70 / ~8 |
| `tests/test_gdr.py` | 新增测试 | +70 |

**不涉及 GUI 文件。** 不涉及 `process_trace.py` / `per_pool_analysis.py`（独立体系）。

## 五、风险

| 风险 | 缓解 |
|------|------|
| `store` 在 worker 子进程中不可用 | `SimulationEnv` 已序列化 `card_defs` + `pools` 到子进程；`store=None` 时回退原始 target_specs |
| 注册表从 17 → 21 条，下游遍历方需兼容 | `get_expanded_gdr_entries()` 等遍历函数本身无硬编码上限，仅需确认 UI 下拉框无宽度/截断问题 |
| 与 P28（每池GDR严谨性）交叉 | P28 的 `pool_target_map` 是池子→目标卡映射，与 `final_time` 维度互补，不冲突 |
| `final_time` 在 dict 格式 compact 中可能缺失 | `compact.get('final_time', 0)` 兜底 → `final_time=0` 退化为仅 start_day=0 的池子可达 |

## 六、验收标准

- [ ] `filter_target_specs_by_obtainable()` 正确区分可达/不可达卡——判定依据为池子 `start_day ≤ final_time`
- [ ] 4 个 `_obtainable` GDR 计算结果与手工过滤 target_specs 后调用原版一致
- [ ] `GDRCalculator` 传入 4 个新 key 时三方法（compute_gdr / is_success / check_batch）行为正确
- [ ] 统计分析面板下拉框自动出现 4 个新条目，无需代码修改
- [ ] 零可达卡 → `target_achievement_obtainable` 返回 0.0（不产生 inf/NaN）
- [ ] `store=None` 时回退到原始 target_specs，值与原版相同
- [ ] 现有测试全部通过（向后兼容——未修改原有 17 个 key 的行为）
- [ ] 新增测试覆盖 6 个边界场景
