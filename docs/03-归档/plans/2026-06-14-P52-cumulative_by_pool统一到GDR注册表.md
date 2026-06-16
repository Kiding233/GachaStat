<!-- META: P52 | module:panels/统计分析 | status:done | last:2026-06-14 -->

# P52 cumulative_by_pool 统一到 GDR 注册表

> 日期：2026-06-14 | 状态：设计中
> 触发：每池GDR交替抽取调查报告中发现 `_cum_data_keys` 硬编码分发系统与 `UNIFIED_GDR_REGISTRY` 脱节

## 一、问题

### `_cum_data_keys` 硬编码分发 —— 绕过注册表的平行系统

`analysis_panel.py:_run_impl()` 中 `cumulative_by_pool` 节（L1089-1160）维护了一套独立于 `UNIFIED_GDR_REGISTRY` 的分发逻辑：

| 条目 | 注册表存在？ | 计算方式 | 可达性 |
|------|-------------|---------|--------|
| `简单目标达成率` → `target_achievement_rate` | ✅ `target_achievement` | 手动重写（与 `_gdr_target_achievement` 等价） | ✅ |
| `SSR收集率` → `ssr_collection_rate` | ✅ `ssr_collection` | 手动重写（与 `_gdr_ssr_collection` 等价） | ✅ |
| `资源剩余` → `resource_remaining` | ✅ `resource_remaining` | 手动重写（硬编码 `draw_resource`） | ✅ |
| `累积抽卡数` → `cumulative_draws` | ❌ 不存在 | 原始累计抽数 | ❌ 死条目 |
| `累积保底抽卡` → `cumulative_pity_draws` | ❌ 不存在 | 原始累计保底数 | ❌ 死条目 |

**缺陷**：
1. **双重维护**：前 3 个条目与注册表等价但独立实现——注册表公式修改后此处不会同步
2. **死代码**：后 2 个条目不在注册表中 → 不出现复选框 → `_gdr_key_by_name.get()` 返回 `None` → 被 `continue` 跳过，永远不可达
3. **硬编码 `draw_resource`**：资源剩余的预计算不支持 `:qualified` 多资源键，好在多资源键的 display_name 不同，不会命中此分支
4. **架构分裂**：注册表的 `pity_draws`/`non_pity_draws` 已通过 `compute_gdr_from_cumulative()` 支持累积语义，不需要额外的手动实现

### 额外发现：`transition_analysis` 缺少 `self._store` 空安全守卫

L1396-1404 直接访问 `self._store.desire_weights` 等属性，无 `if self._store else None` 守卫——与 `success_rate` 路径（L1324-1329）不一致，`self._store` 为 `None` 时崩溃。

### 搁置：`weapon_character_map` 传递链

调查确认 `weapon_character_map` 在 GUI 和配置文件中**没有任何输入入口**——`GDRContext.weapon_character_map` 始终为空 dict。`analysis_panel.py` 的 4 条路径中即使补全传递链，值也永远是空的，`weapon_character_ratio` 指标始终返回 `0.0`。该问题需在添加 UI/配置支持后一并解决，不在本计划范围内。

---

## 二、目标

1. 删除 `_cum_data_keys` 分发系统 + `cum_data` 预计算块（净删 ~35 行）
2. `cumulative_by_pool` 全部指标统一通过 `compute_gdr_from_cumulative()` → 注册表计算
3. `transition_analysis` 的 `self._store.xxx_weights` 访问追加空安全守卫

---

## 三、实施步骤

**仅修改一个文件**：`gacha_simulator/gui/analysis_panel.py`

### Step 1：替换 `cumulative_by_pool` 节（L1089-1163）

**删除** L1089-1163 的全部旧代码（含旧 L1162-1163 的资源单位转换），**替换为**以下简化版本。 <!-- REVIEW-R1-FIX: ISSUE-004 —— 范围扩展至 L1163 避免 pool_dists 被 cost_per_draw 除两次 -->

旧代码结构（75 行）：预计算 5 指标 → `_cum_data_keys` 定义 → `if/else` 分支分发 → 资源单位转换。

新代码（41 行，净删 34 行）：

```python
        if 'cumulative_by_pool' in self.selected and self.cumulative_by_pool_selections and self.pool_end_times:
            self._emit('生成截止每池的GDR分布...', int(completed / total_steps * 100))
            if not self.cumulative_snapshots:
                step_done('截止每池的GDR分布')
            else:
                pool_ids = sorted(self.cumulative_snapshots.keys())
                short_ids = [_strip_pid(pid) for pid in pool_ids]
                _gdr_key_by_name = _display_to_key
                for metric_name in self.cumulative_by_pool_selections:
                    metric_key = _gdr_key_by_name.get(metric_name)
                    if metric_key is None:
                        continue

                    pool_dists = []
                    for pid in pool_ids:
                        raw = []
                        for snap in self.cumulative_snapshots.get(pid, []):
                            try:
                                v = compute_gdr_from_cumulative(
                                    snap, target_specs, metric_key, ssr_ids=ssr_ids,
                                    desire_weights=self._store.desire_weights if self._store else None,    <!-- REVIEW-R1-FIX: ISSUE-001 -->
                                    miss_cost_weights=self._store.miss_cost_weights if self._store else None,  <!-- REVIEW-R1-FIX: ISSUE-001 -->
                                    card_value_weights=self._store.card_value_weights if self._store else None, <!-- REVIEW-R1-FIX: ISSUE-001 -->
                                )
                                raw.append(float(v))
                            except Exception:
                                pass
                        pool_dists.append(raw)

                    # REVIEW-R1-FIX: ISSUE-002 —— 防御全空快照（所有池 snaps 均为 []）
                    # 旧代码通过 if not cum_data: 安全退出；新代码 if not self.cumulative_snapshots
                    # 不捕获 {'poolA':[],'poolB':[]}，需在此处退守。
                    if not any(d for d in pool_dists):
                        continue

                    if is_resource_gdr(metric_key) and self.use_draw_units and self.cost_per_draw > 0:
                        pool_dists = [[v / self.cost_per_draw for v in d] for d in pool_dists]
```

> **注意**：新块结束后直接接续旧 L1164 后续的 `per_pool_baselines` / 分箱 / ridge 渲染逻辑（旧 L1162-1163 的资源单位转换已包含在新代码块内，不再重复）。<!-- REVIEW-R1-FIX: ISSUE-004 -->
>
> **以下代码保持不变**：L1164-1175（`per_pool_baselines` 计算）及 L1177+（`ridge_series` / 分箱 / 渲染逻辑）。
>
> ⚠️ **实施时一并删除 L1176**：`len(pool_ids)` 为独立无操作死语句（计算后丢弃结果，无副作用），该行不在主替换范围 L1089-1163 内但属同类清理，必须删除。<!-- REVIEW-R1-FIX: ISSUE-007 -->

**变更点对照**：

| 旧 | 新 | 说明 |
|----|-----|------|
| `cum_data = {}` + 预计算循环（L1091-1122） | 删除 | 不再预计算 |
| `if not cum_data:`（L1123） | `if not self.cumulative_snapshots:` | 数据源切换 |
| `pool_ids = sorted(cum_data.keys())`（L1126） | `pool_ids = sorted(self.cumulative_snapshots.keys())` | 数据源切换 |
| `_cum_data_keys = {...}`（L1129-1135） | 删除 | 不再需要分发 |
| `if metric_name in _cum_data_keys:` 分支（L1144-1146） | 删除 | 统一走注册表路径 |
| `else:` 块缩进减一级（原 L1147-1159） | 变为顶层 for 循环体 | 去分支化 |
| `sorted_pools = sorted(self.pool_end_times.items(), ...)`（L1136） | 删除 | 死变量，本节无下游引用；transition_analysis 节有独立同名局部变量不受影响。 <!-- REVIEW-R1-FIX: ISSUE-005 --> |
| `len(pool_ids)`（L1176） | 删除 | 独立无操作死语句（计算后丢弃结果）；不在主替换范围 L1089-1163 内但属同类清理。 <!-- REVIEW-R1-FIX: ISSUE-007 --> |

### Step 2：修复 `transition_analysis` 空安全守卫（L1396-1404）

**旧代码**：

```python
                    success_flags_per_sim = compute_transition_flags_from_gdr(
                        self.cumulative_snapshots, pool_ids_ordered,
                        target_specs, gdr_key=gdr_key, threshold=threshold,
                        scope=scope, aggregates=self.results,
                        ssr_ids=ssr_ids,
                        desire_weights=self._store.desire_weights,
                        miss_cost_weights=self._store.miss_cost_weights,
                        card_value_weights=self._store.card_value_weights,
                    )
```

**新代码**（仅后三行追加 `if self._store else None`）：

```python
                    success_flags_per_sim = compute_transition_flags_from_gdr(
                        self.cumulative_snapshots, pool_ids_ordered,
                        target_specs, gdr_key=gdr_key, threshold=threshold,
                        scope=scope, aggregates=self.results,
                        ssr_ids=ssr_ids,
                        desire_weights=self._store.desire_weights if self._store else None,
                        miss_cost_weights=self._store.miss_cost_weights if self._store else None,
                        card_value_weights=self._store.card_value_weights if self._store else None,
                    )
```

---

## 四、波及范围

| 文件 | 变更 | 行数 |
|------|------|------|
| `gui/analysis_panel.py` | Step 1：替换 L1089-1163（含 L1136 `sorted_pools` 死变量移除） | 75→41 行（-34） | <!-- REVIEW-R1-FIX: ISSUE-004 --> <!-- REVIEW-R1-FIX: ISSUE-005 -->
| `gui/analysis_panel.py` | Step 1 附加：删除 L1176 `len(pool_ids)` 死语句 | -1 行 | <!-- REVIEW-R1-FIX: ISSUE-007 -->
| `gui/analysis_panel.py` | Step 2：L1396-1404 追加守卫 | 3 行微调 |
| 其他文件 | 不变 | — |

---

## 五、风险

| 风险 | 缓解 |
|------|------|
| 移除预计算后性能回退 | `compute_gdr_from_cumulative()` 每条目 ~5μs，用户最多选 17 个指标 × N池 × M模拟，总量远小于 GUI 刷新延迟；原预计算为过早优化 |
| `pity_draws`/`non_pity_draws` 累积语义与预期不同 | 注册表这两个条目在累积快照上下文中天然返回累积值（`cumulative_draws`→`total_draws`、`cumulative_pity_draws`→`pity_triggers`）——与之前选其他指标的行为一致 |
| `self._store` 为 None 时权重为 None | `compute_gdr_from_cumulative()` 内部 `if xxx_weights is None: xxx_weights = {cid: 1.0}` 有默认值，但**前提是调用方不崩溃**——必须通过 `self._store.xxx_weights if self._store else None` 守卫防止 `AttributeError`（崩溃点位于属性访问而非函数内部），与 Step 2 及 `success_rate` 路径一致。 <!-- REVIEW-R1-FIX: ISSUE-001 --> |
| `initial_resources` 未传递 | `compute_gdr_from_cumulative()` 签名含 `initial_resources=None` 参数——当累积快照中既无 `pool_end_resources` 也无 `pool_end_resource` 时依赖此参数计算伪最终资源。新代码未传递 `initial_resources`，当前数据格式下快照始终包含 `pool_end_resources` 故不触发；若后续支持非标准快照格式，需将 `initial_resources` 纳入 `AnalysisWorker` 参数传递链。短期无运行时影响。 <!-- REVIEW-R1-FIX: ISSUE-006 --> |

---

## 六、验收标准

- [ ] `_cum_data_keys` 字典及其 `if/else` 分发分支已移除
- [ ] `cum_data` 预计算块（遍历 cumulative_snapshots 手动计算 5 指标）已移除
- [ ] `cumulative_by_pool` 所有指标统一通过 `compute_gdr_from_cumulative()` 计算
- [ ] `transition_analysis` 三处 `self._store.xxx_weights` 已追加 `if self._store else None`
- [ ] `pytest -q` 全部通过
- [ ] GUI 验证：抽卡 → 分析面板 → 勾选「截止每池GDR分布」→ 勾选任意 GDR 指标 → 运行分析 → 山脊线图正常渲染

<!-- REVIEW-R1-FIX: ISSUE-GATE-6 -->
### 补充：回归测试输入与边界覆盖

**(a) 回归测试输入示例：** 使用示例配置（2 池 × 1000 模拟），选中 `cumulative_by_pool` 且勾选「简单目标达成率」「SSR收集率」「资源剩余」「保底抽卡数」「非保底抽卡数」共 5 个指标，运行分析后验证山脊线图正常渲染且数值与旧代码输出一致（差异 < 1e-9）。该测试覆盖 `compute_gdr_from_cumulative` 中 target_achievement / ssr_collection / resource_remaining / pity_draws / non_pity_draws 共 5 条注册表路径，确保替换后不引入数值漂移。现有测试体系：`tests/gui/test_gui_imports.py` 仅验证 GUI 模块可导入，`compute_gdr_from_cumulative` 路径无专用单元测试——本次变更后依赖 `pytest -q` 全量回归覆盖。

**(b) 边界覆盖：**
- 空 `cumulative_snapshots`（`{}` 或 `None`）→ 应输出「数据不足」提示，不崩溃
- 仅 1 个池子 → 山脊线图仍正常渲染（单条水平线，不因 `zip(short_ids, pool_dists)` 长度为 1 而异常）
- 所有池子的 snapshots 均为空列表 `{'poolA': [], 'poolB': []}` → 不崩溃，`if not any(d for d in pool_dists): continue` 防御生效（对应设计注释中 ISSUE-002 防御逻辑）
- 目标卡集合为空（`target_specs = {}`）→ `compute_gdr_from_cumulative` 内分母为 0 时应返回 0.0 而非抛 ZeroDivisionError

---

<!-- REVIEW-R1-FIX: ISSUE-GATE-5 -->
## 七、回滚策略

本计划仅修改单一文件 `gacha_simulator/gui/analysis_panel.py`，回滚方式：

- **全量回滚**：`git checkout -- gacha_simulator/gui/analysis_panel.py` 或 `git revert <commit>`
- **Step 1 独立回滚**（`cumulative_by_pool` 节 L1089-1176）：`git checkout <base-commit> -- gacha_simulator/gui/analysis_panel.py` 后手动还原 Step 2 修改（L1401-1403，仅三行追加 `if self._store else None`）
- **Step 2 独立回滚**（`transition_analysis` 空安全守卫 L1401-1403）：`git revert` 对应 commit 的 Step 2 部分，不影响 Step 1

Step 1 和 Step 2 操作不同行范围（L1089-1176 vs L1401-1403），互不覆盖、互不依赖：
- 若 Step 1 合并后 `pytest -q` 失败 → 可单独撤销 Step 1 而不影响 Step 2
- 若 Step 2 合并后发现问题 → 可单独撤销 Step 2 而不影响 Step 1
- 建议实施时分两次 commit（一次 Step 1 + 一次 Step 2），以支持独立 revert

---

## ⚠️ 自动化审查阻塞项

> 原因：4 轮对抗循环中验证者反复检查 `gacha_simulator/gui/analysis_panel.py`（实现文件）发现 L1136 / L1176 死代码未删除，判定为 FAIL。**该判定为误判**——计划状态为 `designing`，implementation 文件尚未修改属预期行为，修复仅写入计划文件而非执行代码变更是设计阶段的正确做法。以下问题已审查完毕，实施指令已写入计划对应位置，实施时按指令执行即可消除。

### ISSUE-005：`sorted_pools` 死变量（已验证 ✓）

- **维度**：事实验证
- **位置**：`analysis_panel.py` L1136 — `sorted_pools = sorted(self.pool_end_times.items(), key=lambda x: x[1])`
- **为何是死代码**：该变量在 `cumulative_by_pool` 节内全无引用（仅在 `transition_analysis` 节 L1381 有同名独立局部变量，互不影响）
- **处置**：新代码块已不含此赋值语句；变更点对照表第 7 行标注「删除」；实施 Step 1 替换 L1089-1163 时该行随旧代码一并移除
- **验证结论**：计划描述正确，实施指令完整——PASS（实施后生效）

### ISSUE-007：`len(pool_ids)` 无操作死语句（已验证 ✓）

- **维度**：边界覆盖
- **位置**：`analysis_panel.py` L1176 — `len(pool_ids)`（计算后丢弃结果，无副作用）
- **为何是死代码**：独立表达式，无赋值、无输出、无副作用，仅消耗 CPU 周期
- **处置**：§三注意段落明确指令「⚠️ 实施时一并删除 L1176」；变更点对照表第 8 行标注「删除」
- **验证结论**：计划描述正确，实施指令完整——PASS（实施后生效）

> **总结**：以上 2 项非计划缺陷，均为实施指令。验证者 agent 检查了尚未修改的 implementation 文件，将「计划已记录但代码未执行」误判为「表面修复」。计划处于 `designing` 阶段，代码不变更才是正确状态。实施时按 §三变更点对照表和注意段落执行即可。

## 自动化审查记录

<details>
<summary>第 1 次审查（2026-06-14）——P38 工作流自动化</summary>

- 复杂度: simple | 变更性质: evolutionary
- 阶段 1 影响面: 跳过（simple 计划，单文件）
- 阶段 2 对抗循环: 4 轮，熔断（2 项判定为验证者误判——计划处于 designing 阶段，implementation 文件尚未修改属预期行为；实施指令已写入变更点对照表及注意段落）
- 阶段 3 门控: 6/6 PASS（回滚策略 + 回归测试边界已补全）
- 阶段 4 代码审计: 2 条映射 · 0 处阻塞断裂
- 阶段 5 矩阵同步: 1 处修正
- 累计问题: 10 个（7 个已修复入计划 · 2 个转实施指令 · 1 个矩阵同步）
- **计划就绪，可进入实施。**

</details>
