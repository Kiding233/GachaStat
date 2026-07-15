<!-- META: P63 | module:模拟服务层 | status:designing | last:2026-07-15 | depends:P60✅ -->

# P63 溢出卡资源转换——收敛到 state.add_card() 的统一溢出管道

> 日期：2026-07-15 | 更新：2026-07-15 | 状态：设计中
> 触发：游戏手册 §溢出/满突破后分解——抽到重复卡时产出不同资源（如原神星辉系统）。当前 `compute_bonus_resources()` 逻辑完整，但 TOML 配置管道断裂；milestone (P58) 注入的卡也不触发溢出。
> 依赖：P60（提供 `state.add_card()` / `state.get_card_count()` / `state.acquired` 一等公民字段）

---

## 一、问题

### 1.1 溢出转换机制的三层断裂

溢出转换（重复卡→资源）的核心逻辑 `compute_bonus_resources()` 已经正确实现了四档分档（`resources_gained` / `first_time_bonus` / `nth_time_bonus` / `excess_bonus`），调用时序也正确。但存在三个断裂点：

| # | 断裂点 | 表现 |
|---|--------|------|
| F1 | TOML → PoolDistEntry | `_build_pools()` 和 `_expand_template_with_bindings()` 构造 `PoolDistEntry` 时不读取 bonus 字段，下游拿到的永远是空 `{}` |
| F2 | bonus 附着在 Reward（池子级） | Milestone 注入的卡没有关联的 Reward 对象，无法调用 `compute_bonus_resources()` |
| F3 | `state.add_card()` 是纯计数器 | 只做 `acquired[card_id] += 1`，不触发资源变化。溢出判定分散在 `gacha_service` 循环中 |

### 1.2 架构问题

当前溢出判定是「抽卡循环的附带逻辑」而非「获得卡片这个动作的内建属性」：

```python
# 现状——溢出在外面单独算
state.add_card(reward.id)                    # 只管计数
# ... 十几行后 ...
bonus = compute_bonus_resources(reward, ...)  # 溢出在外面
rg = base + bonus
```

这导致：(a) 任何不走 `pool.draw()` 的卡牌获取路径（milestone、未来可能的兑换奖励等）都不会触发溢出；(b) `gacha_service` 承担了本该属于 `state` 的职责。

---

## 二、目标

### 核心目标

1. **修复 TOML 配置管道**：`_build_pools()` 和 `_expand_template_with_bindings()` 正确解析 bonus 字段，打通 TOML → PoolDistEntry → Reward → compute_bonus_resources 全链路
2. **收敛溢出判定到 state**：`GachaState.add_card()` 接受溢出配置，内部计算并返回溢出资源，统一所有卡牌获取路径
3. **Milestone 兼容**：P58 的 `MilestoneEngine.after_draw()` 注入卡牌时自动获得溢出资源，无需额外逻辑

### 设计决策（已确定）

| 决策 | 结论 | 理由 |
|------|------|------|
| 溢出配置存哪 | `PoolDistEntry`（不改 CardDefEntry） | 改动最小；batch_simulator 读取路径已通 |
| 资源归属策略 | 策略 1——溢出资源混入当抽 `combined_gained` | 自动归入触发池子；下游零改动；单通道防重复 |
| `collector.on_bonus()` | 只存元数据（事件名、时间戳、赠送内容），不承载资源金额 | 资源统一走 `draw_resources_gained` |
| 与 P55/P56 关系 | 零依赖、零冲突、可完全并行 | 改不同文件、不同段落 |
| `nth_time_bonus` | 保留 | 不改现有字段，不扩大范围 |

### 非目标

- 不修改 `compute_bonus_resources()` 的核心逻辑
- 不将 bonus 配置提升到 `CardDefEntry`（留给未来重构）
- 不新增 `repeat_bonus` 或 `max_copies` 便利字段
- 不改动分析面板、GDR 计算、方案搜索等下游模块

---

## 三、方案

### 3.1 架构变更

```
现状：
  pool.draw() → reward
  state.add_card(id)                        ← 只管计数
  ... 十几行后 ...
  compute_bonus_resources(reward, before, after)  ← 溢出在外面
  rg = base + bonus

方案 B：
  pool.draw() → reward
  rg = state.add_card(id, bonus_config, initial_counts)
       │
       └── acquired[card_id] += 1
       └── compute_bonus_resources_from_config(config, before, after)
       └── return bonus_dict
```

### 3.2 新增数据类：`CardBonusConfig`

放在 `core/pool.py`，与 `Reward` 平级。从 `Reward` 提取溢出配置，使其可被任何获取路径使用：

```python
@dataclass
class CardBonusConfig:
    """卡片级溢出配置——从 Reward/PoolDistEntry 提取，独立于池子。"""
    resources_gained: Dict[str, float] = field(default_factory=dict)
    first_time_bonus: Dict[str, float] = field(default_factory=dict)
    nth_time_bonus: Dict[int, Dict[str, float]] = field(default_factory=dict)
    excess_bonus: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_reward(cls, reward: 'Reward') -> 'CardBonusConfig':
        return cls(
            resources_gained=dict(reward.resources_gained),
            first_time_bonus=dict(reward.first_time_bonus),
            nth_time_bonus=dict(reward.nth_time_bonus),
            excess_bonus=dict(reward.excess_bonus),
        )

    def is_empty(self) -> bool:
        return not any([self.resources_gained, self.first_time_bonus,
                        self.nth_time_bonus, self.excess_bonus])
```

### 3.3 新增函数：`compute_bonus_resources_from_config()`

放在 `core/pool.py`。与现有 `compute_bonus_resources()` 逻辑一致，但不依赖 `Reward` 对象：

```python
def compute_bonus_resources_from_config(
    config: CardBonusConfig, acquired_before: int, acquired_after: int
) -> Dict[str, float]:
    bonus: Dict[str, float] = {}
    # 基础产出
    for k, v in config.resources_gained.items():
        bonus[k] = bonus.get(k, 0) + v
    # 首次获得
    if acquired_before == 0:
        for k, v in config.first_time_bonus.items():
            bonus[k] = bonus.get(k, 0) + v
    # 第N次获得
    for nth, resources in config.nth_time_bonus.items():
        if acquired_after == nth:
            for k, v in resources.items():
                bonus[k] = bonus.get(k, 0) + v
    # 满突破溢出
    if config.excess_bonus:
        threshold = config.excess_bonus.get('threshold', 999999)
        if acquired_before >= threshold:
            for k, v in config.excess_bonus.get('resources', {}).items():
                bonus[k] = bonus.get(k, 0) + v
    return bonus
```

E2 完成后，原 `compute_bonus_resources()` 改为委托新函数，消除逻辑分化：

```python
def compute_bonus_resources(reward: 'Reward', acquired_before: int,
                            acquired_after: int) -> Dict[str, float]:
    """委托到 CardBonusConfig 版本——保证零逻辑分化。"""
    config = CardBonusConfig.from_reward(reward)
    return compute_bonus_resources_from_config(config, acquired_before, acquired_after)
```

所有已有调用方（如有）不受影响。

### 3.4 改造 `GachaState.add_card()`

签名变更，向后兼容：

```python
# 改动前
def add_card(self, card_id: str) -> int:

# 改动后
def add_card(self, card_id: str,
             bonus_config: Optional['CardBonusConfig'] = None,
             initial_counts: Optional[Dict[str, int]] = None) -> Dict[str, float]:
```

不传 `bonus_config` 时行为与现在完全一致（纯计数，返回空 dict）。

**约束：** 当 `bonus_config` 不为 None 时，调用方**必须**传入 `initial_counts`，否则 `first_time_bonus` 和 `excess_bonus` 的分档判定会忽略初始持有数——例如玩家初始持有 2 张卡 X，模拟中第一次抽到 X 时 `total_before` 会被错误地计算为 0，错误触发 `first_time_bonus`。`gacha_service` 和 milestone 集成点始终传入 `_initial_counts`，不受影响。

### 3.5 构建 `card_bonus_map` + 简化 gacha_service

`GachaService.__init__()` 中一次性构建卡片→溢出配置映射：

```python
self.card_bonus_map: Dict[str, CardBonusConfig] = {}
for pool in pools.values():
    for reward, _ in pool.rewards:
        if reward.id != '_no_card' and reward.id not in self.card_bonus_map:
            cfg = CardBonusConfig.from_reward(reward)
            if not cfg.is_empty():
                self.card_bonus_map[reward.id] = cfg
```

抽卡循环中 bonus 段从 7 行简化为 1 行：

```python
# ── 改动前（gacha_service.py 第 221-235 行，7行）──
if reward.id != _NO_CARD_ID:
    state.add_card(reward.id)                    # 纯计数
rg = dict(reward.resources_gained or {})         # 基础资源
if reward.first_time_bonus or reward.nth_time_bonus or reward.excess_bonus:
    ac_new = state.get_card_count(reward.id)
    init = _initial_counts.get(reward.id, 0)
    total_before = init + ac_new - 1
    total_after = init + ac_new
    bonus = compute_bonus_resources(reward, total_before, total_after)
    for k, v in bonus.items():
        rg[k] = rg.get(k, 0) + v                # bonus 叠加到 rg

# ── 改动后（1行，替代上述全部）──
# add_card 返回的 dict 已包含 resources_gained + first_time_bonus
# + nth_time_bonus + excess_bonus，无需调用方再叠加
if reward.id != _NO_CARD_ID:
    rg = state.add_card(reward.id,
                        bonus_config=self.card_bonus_map.get(reward.id),
                        initial_counts=_initial_counts)
else:
    rg = {}
```

且 Milestone 注入时同样受益——卡片溢出 + 直接资源统一归入本抽 `rg`：

```python
# P58 Milestone 注入——卡片溢出 + 直接资源，全部归入本抽 rg
milestone_rg = dict(entry['bonus'].get('resources', {}))   # milestone 直接资源
for cid in entry['bonus'].get('card_ids', []):
    overflow = state.add_card(cid,
                              bonus_config=self.card_bonus_map.get(cid),
                              initial_counts=_initial_counts)
    for k, v in overflow.items():
        milestone_rg[k] = milestone_rg.get(k, 0) + v       # milestone 卡片溢出
rg.update(milestone_rg)                                     # 全部归入本抽
```

### 3.6 资源归属与记账

```
所有资源收入（抽卡基础 + 抽卡溢出 + milestone直接 + milestone溢出 + wait收益）
        │
        ▼
      rg dict（单抽的资源汇总）
        │
        ├── state.resources[k] += v      ← 立即可用于下一抽
        ├── total_gained[k] += v         ← 全局累加
        └── combined_gained → draw_resources_gained[i]
                                    │
                      draw_pool_ids[i] = 触发池
                                    │
                      pool_resources_gained[pid] 自动归入
```

单通道约束：`collector.on_bonus()` 只存元数据，不存资源金额。资源统一走 `combined_gained`。

### 3.7 TOML 配置语法

bonus 字段挂在分布模板条目或内联 distribution 上：

```toml
# 分布模板中
[[distribution_templates.cards]]
card_id = "limited_ssr_1"
probability = 0.6
rarity = "ssr"
featured = true
resources_gained = { exchange_currency = 10 }
first_time_bonus = { exchange_currency = 10 }
excess_bonus = { threshold = 7, resources = { exchange_currency = 25 } }

# 或内联 distribution
[[pools.distribution]]
card_id = "sr_1"
probability = 5.0
rarity = "sr"
resources_gained = { exchange_currency = 2 }
excess_bonus = { threshold = 7, resources = { exchange_currency = 5 } }

# nth_time_bonus 同样支持（整数键行内表——TOML 标准合法语法）：
nth_time_bonus = { 2 = { exchange_currency = 20 }, 3 = { exchange_currency = 30 } }
```


---

## 四、实施阶段

| 阶段 | 内容 | 文件 | 预估行数 |
|:---:|------|------|:---:|
| E1 | `CardBonusConfig` dataclass + `from_reward()` | `core/pool.py` | ~25 |
| E2 | `compute_bonus_resources_from_config()` 函数 | `core/pool.py` | ~30 |
| E3 | `GachaState.add_card()` 签名扩展 + 溢出计算 | `core/state.py` | ~15 |
| E4 | TOML 解析管道修复——`_build_pools()` + `_expand_template_with_bindings()` 读取 bonus 字段 | `core/config_toml.py` | ~15 |
| E5 | `GachaService` 改造——`card_bonus_map` 构建 + 循环简化 + `__init__` 导出 | `service/gacha_service.py` | ~20 |
| E6 | TOML 配置示例——为现有卡片添加 bonus 配置段 | `config/config.toml` | ~15 |
| E7 | 集成测试——溢出转换端到端验证 | `tests/` | ~40 |

> E7 分两步：(a) 直接调用 `state.add_card()` 模拟 milestone 卡片注入，验证溢出资源正确返回——不依赖 P58；(b) P58 实施后补齐 MilestoneEngine 端到端集成测试。
| **总计** | | | **~160** |

---

## 五、波及范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `core/pool.py` | **修改** | 新增 `CardBonusConfig` + `compute_bonus_resources_from_config()` |
| `core/state.py` | **修改** | `add_card()` 签名扩展——接受 bonus_config + initial_counts，返回溢出资源 |
| `core/config_toml.py` | **修改** | `_build_pools()` + `_expand_template_with_bindings()` 中 5 处 `PoolDistEntry(...)` 补上 bonus 字段读取 |
| `core/__init__.py` | **小改** | 导出 `CardBonusConfig` + `compute_bonus_resources_from_config` |
| `service/gacha_service.py` | **修改** | 构建 `card_bonus_map`；简化抽卡循环 bonus 段；Milestone 集成点传参 |
| `service/batch_simulator.py` | **不改** | 已有 bonus 字段读取路径（550-557行），无需变更 |
| `service/config_service.py` | **不改** | 已知缺口——旧版 `import_pool_from_config()`（第49行）创建 `Reward(id, name)` 不传 bonus 字段。不影响主流程（GUI/CLI 走 batch_simulator），可在后续统一清理 |
| `config/config.toml` | **更新** | 为卡牌条目添加 `resources_gained` / `excess_bonus` 配置示例 |

**不受影响：** `core/pity.py`、`core/collector.py`、`core/result_types.py`、`core/gdr.py`、`core/streaming.py`、`gui/` 全部面板

---

## 六、依赖关系

```
P60（已完成 ✅）
├── state.add_card()          ← E3 改造的基础
├── state.get_card_count()    ← E3 溢出判定用
└── state.acquired            ← 单一真相源

本计划（P63）
├── 零依赖 P55 / P56 / P58
├── 与 P55 ∥ P56 ∥ P58 完全并行——改不同文件、不同段落
└── P58 从中受益——Milestone 注入时自动获得溢出能力
```

**并行性分析：**

| | P55 | P56 | P58 | P63 |
|---|---|---|---|---|
| `pity.py` | ✅ 改 | ✅ 改 | 不改 | 不改 |
| `pool.py` | 不改 | 不改 | 不改 | ✅ 改 |
| `state.py` | 不改 | 不改 | 不改 | ✅ 改 |
| `config_toml.py` | 可能改 | 可能改 | ✅ 改 | ✅ 改 |
| `gacha_service.py` | 可能改 | 可能改 | ✅ 改 | ✅ 改 |

`config_toml.py` 和 `gacha_service.py` 的改动在不同段落/函数，merge 不会产生冲突。

---

## 七、风险

| 风险 | 缓解 |
|------|------|
| `add_card()` 签名变更导致调用方遗漏传参 | 新参数全为 Optional，默认 None——向后兼容，不传则行为与现在一致 |
| `card_bonus_map` 中同一张卡在多个池子中有不同的 bonus 配置 | 取首次遇到的配置（`if reward.id not in map`）。未来如果出现「不同池子同卡不同 bonus」的需求，可升级为 `Dict[str, List[CardBonusConfig]]` |
| milestone 溢出资源被拒（`can_afford_batch` 预检查不感知收入） | 已有行为，非本计划引入。溢出资源通常与消耗资源是不同类型（星辉 ≠ 原石），无实际影响 |
| 旧序列化快照反序列化失败 | 不涉及序列化字段变更——`CompactResult` 不动，`CardBonusConfig` 是运行时对象 |
| `compute_bonus_resources` 与 `compute_bonus_resources_from_config` 逻辑分化 | E2 实现后，原函数内部委托给新函数，消除重复 |

---

## 八、验收标准

- [ ] `CardBonusConfig.from_reward()` 正确从 Reward 提取四个字段，空 Reward → `is_empty() == True`
- [ ] `compute_bonus_resources_from_config()` 四档分档逻辑与现有 `compute_bonus_resources()` 一致
- [ ] `state.add_card()` 不传 bonus_config 时行为不变（纯计数，返回 `{}`）
- [ ] `state.add_card()` 传 bonus_config 时正确返回溢出资源，`acquired_count` 正确递增
- [ ] `state.add_card()` 返回的溢出资源被合并到 `rg`，归入触发池子的 `pool_resources_gained`
- [ ] TOML 中配置的 `resources_gained` / `first_time_bonus` / `nth_time_bonus` / `excess_bonus` 正确解析到 `PoolDistEntry`
- [ ] `card_bonus_map` 从 pools 正确构建，不含 `_no_card`
- [ ] `gacha_service` 抽卡循环 bonus 段简化后，资源产出与改动前一致
- [ ] milestone (P58) 注入的卡正确触发溢出，溢出资源归入触发池子
- [ ] `total_gained` / `final_resources` 无重复累加——每笔资源只入账一次
- [ ] 批次内溢出资源立即可用于下一发（`resources` 是 `state.resources` 引用）
- [ ] `collector.on_bonus()` 不承载资源金额——只存元数据
- [ ] pytest 全量通过
- [ ] 7 个 G20 溢出场景的 TOML 配置 → 模拟 → 产出验证通过
