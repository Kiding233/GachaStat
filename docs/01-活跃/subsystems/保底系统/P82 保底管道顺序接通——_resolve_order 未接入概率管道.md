<!-- META: P82 | module:subsystems/保底系统 | status:designing | last:2026-09-15 | depends:P55✅,P56✅,P64📋 -->
# P82 保底管道顺序接通：`_resolve_order()` 未接入概率管道

> 日期：2026-09-15 | 状态：设计中（待实测裁决）
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

## 六、第一步：实测（无论选哪个方案都应先做）

在动代码之前先量化影响，数据驱动决策：

1. **固化基线**：用当前 `config.toml` + 固定种子跑一批模拟，固化 `CompactResult` golden 快照
2. **临时接线**：在本地应用方案 A 的改动（不提交）
3. **同种子重跑**：逐字段对比，重点看
   - GDR 指标（`make_gdr_calculator` 系列）
   - `draw_pity_names` / `pool_pity_names`
   - 保底触发次数与计数器峰值
4. **判定**：
   - 若差异为零（现配置的书写顺序恰好已符合排序键）→ 接线是纯净化，风险极低，可直接实施
   - 若差异非零 → 差异范围内是「修复」还是「破坏」，需逐例判断，并按无历史包袱原则做完整等价对照

**预估**：若现有配置中「同池多保底」的书写顺序与新排序键一致，差异为零，本计划的实施成本此时可降到最低。

---

## 七、风险

| # | 风险 | 说明 | 缓解 |
|---|------|------|------|
| 1 | **模拟结果变更**（主要） | 凡「同池多保底且书写顺序与排序键不一致」的配置，结果都会变。这是行为变更而非纯重构 | §六 的基线对照；无历史包袱原则要求（`RELEASED=False` 期间允许，但必须配等价对照） |
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

**建议**：先做 §六 的实测，拿到差异数据后再与 P64 的排期合并决策。

---

## 九、待裁决

| # | 事项 | 待定 |
|---|------|------|
| 1 | 方案选择 | A（接线）/ B（废弃）/ C（暂缓）：建议先做实测再定 |
| 2 | 与 P64 的排期关系 | 合并实施 / 先后实施 / 一并撤销 |
| 3 | `pity_names` 双职责的处理 | 直接重排（影响输出字符串）/ 引入独立排序视图（改动更大） |

---

## 十、验收标准（若实施）

1. 概率管道的执行顺序由 `_resolve_order()` 的排序键决定，而非 TOML 书写顺序
2. §六 的基线对照完成，差异逐例判定并记录
3. `_resolve_order()` 与 `_validate_behaviors()` 补齐测试
4. `CompactResult.draw_pity_names` 的变化已评估并记录（若选择直接重排方案）
5. P64 的 G5 项前提已更新

---

*本计划源于 P30 归档时的独立代码复核发现，2026-09-15 建档。核心待办：先实测差异规模，再决定是否接线。*
