<!-- META: P82 | module:subsystems/保底系统 | status:designing | last:2026-09-16 | depends:P55✅,P56✅,P64📋 -->
# P82 保底管道顺序接通：`_resolve_order()` 未接入概率管道

> 日期：2026-09-15 | 状态：设计中（**实测已完成**，见 §六；待方案裁决）
> 来源：P30 归档（2026-09-14）时的独立代码复核，发现缺陷 #11 的处置结论「顺序确定性已解决」不成立
> 涉及文件：`core/pity.py`、`service/batch_simulator.py`、`core/banner.py`
> 依赖：P55（引入 `_resolve_order`）✅ + P56（事件驱动型保底）✅ + **P64（保底状态机引擎，📋 设计中，其 G5 项建立在本计划所推翻的前提上）**
> 优先级：P1（风险性，接线会改变模拟行为，且 P64 的设计依赖本项裁决）

---

## 一、问题

### 1.1 现象

`PityEngine` 会计算保底执行顺序，但**计算结果不作用于概率分布**。概率管道的实际执行顺序是 **TOML 定义顺序**，与排序无关。

### 1.2 机制

系统里有两条并行的路径，`_resolve_order()` 的产物只进入了其中一条，而概率计算走的是另一条：

```
PityEngine.__init__()
  ordered = _resolve_order(behaviors, rarity_rank)   # pity.py:1257
  _validate_behaviors(ordered)                        # pity.py:1258
  self._behavior_list = ordered                       # pity.py:1260  ← 排序结果停在这里

概率计算（真实路径）
  get_probabilities / before_draw / after_draw        # pity.py:1362 / :1391 / :1423
    → self._behaviors_for_pool(pool_id)               # pity.py:1268-1269
      → get_behaviors_for_pool(pool_id)               # pity.py:1271
        → for pname in spec.pity_names                 # pity.py:1277  ← 顺序由这里决定
```

`spec.pity_names` 由 `service/batch_simulator.py:172-176` 按 `pity_defs_list` 的顺序逐个 append 生成，即 **TOML 中 `[[pity]]` 的书写顺序**。全库仅 `batch_simulator.py` 与 `core/worst_impact.py:540` 两处构造 `PoolPitySpec`，都没有再排序。

`_behavior_list` 的全部消费点只有三处，均与顺序无关：

| 位置 | 用途 |
|------|------|
| `pity.py:1232` / `:1260` | 赋值本身 |
| `pity.py:1329` | `_rebind_state` 的 Counter/Flag 重绑定循环 |
| `core/strategy_context_builder.py:93` | 提取跨池保底链接（`inter_pool_pity_links`） |

### 1.3 证据

- 代码链路如上，逐跳可查。
- `tests/` 全库对 `_resolve_order` **零引用**：没有任何测试断言它的排序结果被使用。
- P30 §2.4 的复核勘误（`docs/03-归档/P30 策略系统与保底理论文档补充计划.md`）已记录本条。

---

## 二、设计意图

`_resolve_order()` 是 P55 引入的，排序键为 `(稀有度 rank, btype 顺序, name)`：

1. **稀有度层级优先**：高稀有度（rank 值小）先执行，防止低稀有度保底抢占高稀有度概率槽位
2. **type 分类次之**：counter_soft → counter_hard → event_driven_soft → event_driven_hard
3. **name 字母序兜底**：同优先级按 name 确定性排序

设计目的是让管道顺序**确定的、有语义的**，而非取决于配置文件的书写顺序。

---

## 三、现状 vs 预期

| | 预期（按 `_resolve_order()` 的设计） | 实际 |
|---|---|---|
| 执行顺序 | 稀有度层级 → type → name | TOML 定义顺序 |
| 跨稀有度保护 | 高稀有度保底先执行，不被低稀有度干扰 | 不存在，顺序完全取决于用户如何书写配置 |
| 顺序确定性来源 | 排序算法 | 配置文件行序 |

### 可能原因

不适用单一解释。三种假设无法从代码区分：

1. P55 重构时漏了接线（`_behavior_list` 建好了但没人用）
2. 有意留待后续（P64 正要给 `_resolve_order` 加 `priority`，可能打算届时一并接通）
3. 曾接线后被改回（无 commit 证据支持，但无法排除）

---

## 四、影响面

1. **P30 缺陷 #11 只解决了一半**：「冲突检测」由 `_validate_behaviors()` 落地且生效；「顺序由定义顺序决定」这一半仍成立。
2. **同 scope 的「一软一硬」配置下覆盖未被防住**：`SoftStepBehavior._compute_probabilities` 重分配概率后，`HardPityBehavior._compute_probabilities` 触发时以 `result = {k: 0.0 for k in ctx.current}` 重建分布，软保底的调整被整体覆盖。跨稀有度场景本应由排序键保护，但排序未生效，该保护实际不存在。
3. **P64 的 G5 项建立在不成立的前提上**：P64 计划写「`_resolve_order` 排序 key 加 `priority` 优先级」，若照原设计实施，新增的 `priority` 字段会与现在的 `_resolve_order` 一样空转。

---

## 五、候选方案

### 方案 A：接线（推荐先实测，再定是否实施）

在 `PityEngine.__init__` 里把排序结果写回各 spec 的 `pity_names`：改动一处，不动调用路径，无运行时开销。

```python
ordered = _resolve_order(list(self.behaviors.values()), self._rarity_rank)
_validate_behaviors(ordered)
self._behavior_list = ordered

# 新增：把排序结果写回各池的 pity_names
_order_idx = {getattr(bh, '_name', None): i for i, bh in enumerate(ordered)}
for spec in self.pool_specs.values():
    spec.pity_names.sort(key=lambda n: _order_idx.get(n, len(ordered)))
```

**备选实现**：在 `get_behaviors_for_pool()` 里按 `_behavior_list` 过滤重排。不推荐：该方法每抽被调用三次（三个调度入口），会在热路径引入过滤开销，除非再加缓存层。

### 方案 B：明确废弃

删除 `_resolve_order()`，或在 `_behavior_list` 处标注「未接通」。消除误导，但放弃顺序控制能力；P64 的 G5 项需一并撤销。

### 方案 C：暂不处理

维持现状，仅记录在案。P64 的 priority 设计需先判定本项。

---

## 六、实测结果（2026-09-16 完成）

### 方法

两级对比：

1. **模拟级**：同一份配置 + 固定种子（`-n 100 -w 1 -s 42`），对比接线前后的 CLI 输出（GDR、抽数、SSR 计数、累积快照）
2. **单元级**：直接构造两种 `pity_names` 顺序的 `PityEngine`，对比逐抽概率序列（绕开聚合统计的粗粒度）

### 结论

| 配置场景 | 顺序是否影响结果 | 说明 |
|---------|----------------|------|
| 单条保底（当前 `config.toml` 实况） | 否 | 管道只有一跳，排序是恒等变换 |
| soft + soft（同 / 异目标槽位） | 否 | 概率变换数学可交换；单元级 95 抽序列全同，手算亦证实 |
| soft + hard | 否 | hard 触发时覆盖一切，未触发时无作用 |
| rotating + soft / targeted + soft / hard + rotating | 否 | 同上 |
| **任一含 `rotating_cr` 的组合** | **是** | 随机扫描 46 组合中 12 组敏感，最大差异 30/95 抽 |

### 敏感性的根因

`RotatingCRBehavior.before_draw()` 内有随机数消费：

```python
if self._cr_base_rate > 0 and random.random() < self._cr_base_rate:
    return self._force_featured(ctx)
...
if state_prob > 0 and random.random() < state_prob:
    return self._force_featured(ctx)
```

执行顺序不同则 `random` 的调用时机不同，后续随机流错位，结果随之改变。**这不是概率语义上的顺序依赖，而是共享全局随机源的副作用。**

### 对方案选择的影响

- 方案 A（接线）的风险**不为零**：使用捕获明光的配置在固定种子下结果会变
- 但变化的性质是「随机流错位」而非「概率分布被改变」，两者在统计意义上收敛到同一分布，只是逐次实现不同
- 方案 C（暂不处理）亦有依据：除 `rotating_cr` 的随机流效应外，现状的顺序差异**不影响任何概率输出**
- **P64 的 G5 项（加 `priority` 排序键）**：本次实测说明单靠排序键无法表达顺序语义，因为多数组合本就顺序无关；`priority` 若要真正生效，需要作用于「随机流消费顺序」或引入顺序相关的行为类型

---

## 七、风险

| # | 风险 | 说明 | 缓解 |
|---|------|------|------|
| 1 | **模拟结果变更** | §六 实测已量化：仅含 `rotating_cr` 的配置会变（随机流错位），其余组合不变。原先「凡顺序不一致就会变」的判断过强 | 已由 2026-09-16 实测覆盖；选方案 A 时仍需按无历史包袱原则做等价对照 |
| 2 | **`spec.pity_names` 承担双重职责** | 它不只喂概率管道，还被 `core/banner.py:259-261` 用于拼装输出标签：`triggered_pity_name = ','.join(pity_spec.pity_names)`，写入 `CompactResult.draw_pity_names`。就地重排会**顺带改变该输出字符串的拼接顺序** | 下游多数消费者会转 set 或 sorted（`streaming.py:175-176`、`:198`、`process_trace.py:153`），最终聚合结果可能不变，但**原始字符串会变**，字符串比对类测试/golden 快照会失败。若要彻底隔离，需让管道读一份独立排序视图而非重排 `pity_names` 本身，改动面随之变大：此权衡需在实测阶段一并评估 |
| 3 | **`rarity_rank` 为空时排序退化** | `PityEngine` 存的是 `rarity_rank or {}`（`pity.py:1223`），`_resolve_order` 内部也有 `if rarity_rank is None: rarity_rank = {}` 防御（不会崩），但此时所有 scope 的 rank 都退化为 99，「稀有度层级优先」不生效，排序退化为只按 type + name | 接线前确认 `ConfigStore.[rarities].ranks` 在真实配置中已填写 |
| 4 | **测试覆盖为零** | `_resolve_order` 与 `_validate_behaviors` 均无测试（`tests/` 零引用） | 接线时同步补测试，否则回归无法捕获 |

---

## 八、与 P64 的关系

P64（保底状态机引擎，📋 设计）的 G5 项原文：

> `_resolve_order`（`pity.py:984`）排序 key 加 `priority` 优先级（位于稀有度 rank 之后、type order 之前）

该设计**建立在「`_resolve_order` 决定管道顺序」的前提上，而该前提不成立**。

**两项需合并裁决**，可能的三条路径：

| 路径 | 说明 |
|------|------|
| P82 先接通，P64 再加 priority | 顺序控制先恢复，priority 才有落脚点 |
| P82 与 P64 一并实施 | 一次性接通并引入 priority，避免改两次 |
| P82 判为废弃，P64 一并撤销 G5 | 若判定顺序控制无实际需求 |

**建议**：§六 实测已完成，其结论（排序键对多数组合无效）意味着 G5 需重新论证后再与 P82 一并裁决。

---

## 九、待裁决

| # | 事项 | 待定 | 实测后的建议 |
|---|------|------|-------------|
| 1 | 方案选择 | A（接线）/ B（废弃）/ C（暂缓） | 倾向 **B**：§六 实测显示多数组合顺序无关，接线只能改变含 `rotating_cr` 配置的随机流对齐，收益近零而引入「结果会变」的语义成本。若判定顺序控制确无需求，直接废弃 `_resolve_order()` 更诚实 |
| 2 | 与 P64 的排期关系 | 合并实施 / 先后实施 / 一并撤销 | §六 已说明 `priority` 排序键对多数组合无效，P64 的 G5 需重新论证 |
| 3 | `pity_names` 双职责的处理 | 直接重排（影响输出字符串）/ 引入独立排序视图 | 若最终选 A 才需处理；选 B 则此项消失 |

---

## 十、验收标准（若实施）

1. 概率管道的执行顺序由 `_resolve_order()` 的排序键决定，而非 TOML 书写顺序
2. §六 的基线对照完成，差异逐例判定并记录（已由 2026-09-16 实测完成）
3. `_resolve_order()` 与 `_validate_behaviors()` 补齐测试
4. `CompactResult.draw_pity_names` 的变化已评估并记录（若选择直接重排方案）
5. P64 的 G5 项前提已更新

---

*本计划源于 P30 归档时的独立代码复核发现，2026-09-15 建档，2026-09-16 完成实测（§六）。核心待办：方案裁决（实测倾向废弃 `_resolve_order()`），并据此重审 P64 的 G5。*
