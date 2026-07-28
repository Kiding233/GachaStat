<!-- META: P61 | module:模拟服务层 | status:designing | last:2026-06-20 -->

# P61 池子可用性联动机制——step链与送抽插入

> 日期：2026-06-20 | 状态：设计中
> 触发：step池（拆分建模，每步抽N次后解锁下一步）与终末地30抽取送抽池（强制插入、一次性、不计保底）需要池间可用性联动，当前仅支持基于时间窗口的单池独立可用性。

## 一、问题

当前池子可用性仅基于 `available_from` / `available_until` 时间窗口判断（`Pool.is_available_at()` → `GachaService.run_simulation` 131-133 行硬编码过滤）。存在两个无法建模的场景：

| 场景 | 机制 | 缺失能力 |
|------|------|---------|
| **Step 池链** | 拆分 N 个独立 `Pool`，step N 抽满 M 次后解锁 step N+1，step N 不可用 | 池间依赖 + 抽数阈值触发 |
| **送抽插入** | 主池首次累计 30 抽 → 强制弹出独立送抽池 → 必须先抽送抽才回主池 → 送抽不计主池保底 | 强制插入 + 父池阻塞 + 一次性消耗 + 保底排除 |

更根本的问题是：**策略层只能看到 `current_pools`（已过滤的一维列表），无法知道某个池子为什么不可用**——缺失阻塞原因、依赖进度等诊断信息，策略无法对特殊阻塞（如送抽强制插入）做出分派。

## 二、目标

1. **可用性规则引擎** — 注册表模式（与 `STRATEGY_REGISTRY` / `BEHAVIOR_REGISTRY` 一致），每条规则独立评估一个池子是否可用，返回阻塞原因
2. **PoolAvailabilityContext** — 替代硬编码时间过滤，向策略暴露全量池子状态 + 阻塞原因 + 依赖进度
3. **Step 池链** — TOML 声明式配置 `step = { group, step, draws_to_advance }`，引擎自动管理步骤切换
4. **送抽插入** — TOML 声明式 `interrupt = { trigger_at_draws, interrupt_pool }`，引擎自动触发 + 阻塞父池 + 保底旁路
5. **一次性池 + 保底排除** — `one_shot` / `excludes_pity` 两个独立标志，通用化（不仅限送抽场景）
6. **向后兼容** — 所有新字段默认 None/False，不配置规则的池子行为完全不变

## 三、方案

### 3.1 新增文件：`core/availability.py`

**数据结构：**

```python
class PoolBlockReason(str, Enum):
    TIME_WINDOW = "time"          # 不在时间窗口
    DEPENDENCY_UNMET = "dep"      # 依赖池抽数不足
    INTERRUPTED = "interrupt"     # 被插入池阻塞
    CONSUMED = "consumed"         # 一次性池已消耗
    STEP_PASSED = "step_passed"   # step链中已被越过

PoolAvailability       # pool_id + is_available + reason + detail + meta
PoolAvailabilityContext # statuses: Dict[str, PoolAvailability] + active_pools + blocked_pools() + why_blocked()
EvaluationContext      # 规则评估所需的只读上下文：pools, pool_draw_counts, current_time, exhausted_pools
```

**规则注册表：**

| 规则 | 注册键 | 职责 |
|------|--------|------|
| `TimeWindowRule` | `"time_window"` | 现有逻辑迁移——基于 `available_from/available_until` |
| `StepDependencyRule` | `"step_dependency"` | step N 依赖 step N-1 抽满 `draws_to_advance` 次 |
| `InterruptRule` | `"interrupt"` | 父池抽满阈值后，本池可用并阻塞父池 |
| `OneShotRule` | `"one_shot"` | 一次性池子抽过后标记消耗 |

**AvailabilityEngine：**

遍历 `(pool, rule)` 笛卡尔积，首个返回非 None 的规则结果即为该池最终状态。维护 `_exhausted` 集合（运行中标记一次性池）。`InterruptRule` 的后处理：若送抽池 is_available → 改写父池为 `INTERRUPTED`。

### 3.2 Pool 元数据扩展（`core/pool.py`）

```python
@dataclass
class Pool:
    # ... 现有字段不变 ...
    step_config: Optional[StepConfig] = None       # step 链配置
    interrupt_config: Optional[InterruptConfig] = None  # 送抽插入配置
    is_one_shot: bool = False                       # 一次性池
    excludes_pity: bool = False                     # 不计入保底

@dataclass
class StepConfig:
    group: str              # step 链组名
    step_index: int         # 1-based
    draws_to_advance: int   # 本步需抽多少次解锁下一步

@dataclass
class InterruptConfig:
    parent_pool_id: str     # 触发池
    trigger_at_draws: int   # 触发阈值
    one_shot: bool = True
    blocks_parent: bool = True
```

### 3.3 StrategyContext 扩展（`core/strategy.py`）

新增字段 `pool_availability: Optional[PoolAvailabilityContext]`，策略可查询阻塞原因后分派：

```python
# SmartStrategy 示例：送抽优先
for pa in ctx.pool_availability.blocked_pools():
    if pa.reason == PoolBlockReason.INTERRUPTED:
        return DrawAction(pool_id=pa.meta["interrupt_pool"])
```

### 3.4 GachaService 集成（`service/gacha_service.py`）

- `__init__` 中构建 `AvailabilityEngine`，传入规则实例列表
- `run_simulation` 中：原有硬编码时间过滤（131-133 行）替换为 `self._avail_engine.evaluate()`
- 抽卡后：若池子 `is_one_shot=True` → `avail_engine.mark_exhausted(pool.id)`
- 保底调用：`if pool.excludes_pity: skip pity_engine.before_draw/after_draw`（约 178 行和 217 行加守卫）

### 3.5 SimulationEnvBuilder 映射（`service/batch_simulator.py`）

`from_config_store` 构建 `Pool` 时从 `PoolEntry` 读取新字段 → 映射到 `StepConfig` / `InterruptConfig` / `is_one_shot` / `excludes_pity`。

### 3.6 配置层（`core/config_store.py` + `config/config_toml.py`）

`PoolEntry` 新增 4 个可选字段。`config_toml._build_pools()` 解析 TOML `[pool.step]` / `[pool.interrupt]` / `one_shot` / `excludes_pity` 键。

### 3.7 TOML 配置示例

```toml
# Step 池链
[[pools]]
id = "pool_step1"
# ... 现有字段 ...
step = { group = "chain_main", step = 1, draws_to_advance = 10 }

[[pools]]
id = "pool_step3"
step = { group = "chain_main", step = 3, draws_to_advance = 0 }  # 0=最终步

# 主池 + 送抽
[[pools]]
id = "pool_main"
interrupt = { trigger_at_draws = 30, interrupt_pool = "pool_free_draw" }

[[pools]]
id = "pool_free_draw"
cost = "free_draw:1"
one_shot = true
excludes_pity = true
```

### 3.8 实施阶段

| 阶段 | 内容 | 预估 |
|------|------|------|
| Ph1 | `core/availability.py` — 数据结构 + 4 规则 + AvailabilityEngine | 核心，约 200 行 |
| Ph2 | `core/pool.py` — StepConfig/InterruptConfig + 4 字段 | +30 行 |
| Ph3 | `core/strategy.py` — StrategyContext 新增 pool_availability | +2 行 |
| Ph4 | `service/gacha_service.py` — 集成 AvailabilityEngine + 保底旁路 | ~30 行变更 |
| Ph5 | `service/batch_simulator.py` + `config_store.py` + `config_toml.py` — 配置映射 | +30 行 |
| Ph6 | 测试 — `tests/test_availability.py` 覆盖 4 规则 + 引擎 + 集成 | 新建测试文件 |

## 四、波及范围

| 文件 | 变更性质 | 量级 |
|------|---------|------|
| `core/availability.py` | **新建** | ~200 行 |
| `core/pool.py` | 新增 dataclass + 4 字段 | +35 行 |
| `core/strategy.py` | `StrategyContext` 新增 1 字段 | +2 行 |
| `service/gacha_service.py` | 替换可用性过滤 + 保底跳过 | ~30 行变更 |
| `service/batch_simulator.py` | `from_config_store` 映射新字段 | +10 行 |
| `core/config_store.py` | `PoolEntry` 新增可选字段 | +6 行 |
| `config/config_toml.py` | 解析新 TOML key | +15 行 |
| `tests/test_availability.py` | **新建** | ~150 行 |

无 GUI 变更。不触及保底引擎内部逻辑。

## 五、风险

| 风险 | 缓解 |
|------|------|
| `current_pools` → `PoolAvailabilityContext` 接口变更导致现有 7 种策略全部需要适配 | `current_pools` 字段保留（指向 `active_pools`），不读 `pool_availability` 的策略行为不变 |
| 规则顺序敏感性——两条规则同时返回非 None 时以先到为准 | `AvailabilityEngine.evaluate` 按注册表顺序 break-on-first-match，注册表顺序明确文档化 |
| StepChain 与时间窗口重叠——step 池仍在时间窗口内但被 DEPENDENCY_UNMET 阻塞 | `TimeWindowRule` 先于 `StepDependencyRule` 注册，时间窗外的池先被 TIME_WINDOW 截断；时间窗内则由后续规则评估 |
| 送抽池资源不足——`free_draw:1` 消耗失败时策略循环 | 策略层 `can_afford_batch` 预检查 + 若送抽资源不足 → 回退到资源获取等待，与现有 DrawAction 失败处理一致 |

## 六、验收标准

- [ ] `TimeWindowRule` 行为与现有硬编码过滤一致（回归）
- [ ] step 链：step1→step2→step3 按 `draws_to_advance` 阈值自动切换
- [ ] 送抽插入：主池 30 抽后触发，主池被阻塞，抽完送抽后恢复
- [ ] `excludes_pity=True` 的池子跳过保底 before_draw/after_draw
- [ ] `is_one_shot=True` 的池子抽后永久不可用
- [ ] `StrategyContext.pool_availability` 暴露完整阻塞原因和依赖进度
- [ ] 不配置规则的池子行为完全不变（向后兼容）
- [ ] `test_availability.py` 覆盖全部 4 条规则 + 引擎集成
