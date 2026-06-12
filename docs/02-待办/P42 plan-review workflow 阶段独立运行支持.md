<!-- META: P42 | module:02-待办 | status:planning | last:2026-06-12 -->
# P42 plan-review workflow 阶段独立运行支持

> 创建日期：2026-06-12 | 最后更新：2026-06-12
> 来源：P40 迭代审查需求——重复跑全流程 token 浪费
> 关联：[[P38]]

**目标：** 让 `/workflow plan-review` 支持 `--only-stage=N` 和 `--skip=X,Y` 参数，允许用户单独运行指定阶段。

---

## 问题

当前 workflow 是全流程一体化——阶段 0→1→2→3→4→5 顺序执行，无跳过机制。`skip_stages` 由分类器自动决定，用户不可控。

实际场景：
- P40 已跑过全流程，想再跑一次阶段 2（对抗循环）验证新修改 → 当前只能重跑全流程（350K+ token）
- 写计划时想用阶段 4（代码审计）做即时验证 → 当前只能重跑全流程

## 方案

在 workflow.js 中增加 3 处改动，约 40 行净增量。

### 改动点

| # | 位置 | 内容 |
|---|------|------|
| 1 | args 解析（L576） | 支持 `"path --only-stage=N"` 和 `"path --skip=X,Y"` 两种标志 |
| 2 | 阶段入口（L770） | 新增 `shouldRunStage(N)` / `effectiveSkipStage()` 辅助函数 |
| 3 | 各阶段门控 | 阶段 1-5 入口包裹 `shouldRunStage(N)` + 幂等性预检/汇总追加按条件跳过 |

### 阶段编号映射

`--only-stage=N` 中的 N 与代码标识的对应关系：

| 编号 | 代码标识 | 阶段内容 | 是否修改文件 |
|------|----------|----------|:--:|
| 0 | `classify` | 分类器——分析复杂度/维度/skip_stages | — |
| 1 | `fan_out_impact` | 扇出影响面——N agent 并行检查 N 维度 | — |
| 2 | `adversarial_loop` | 对抗循环——Finder→Fixer→Verifier 收敛 | ✅ |
| 3 | `feasibility_gate` | 可行性门控——6 项检查 + 内部修复 | ✅ |
| 4 | `code_audit` | 代码审计——4a 映射 + 4b 全链条 | — |
| 5 | `matrix_sync` | 矩阵同步——对比元数据 ↔ 模块状态矩阵 | ✅ |

阶段 0（分类器）始终运行，不受 `--only-stage` / `--skip` 影响。

### Args 解析方案

当前 L576 直接取 `args[0]` 作为路径。需增加标志提取逻辑：

```javascript
// 替换 L576 的简单赋值
const rawArg = Array.isArray(args) ? args[0] : (args || '')
// 从字符串末尾提取 --flag 对（路径可能含空格）
const flagMatch = rawArg.match(/^(.*?)\s+(--(?:only-stage|skip)=\S+(?:\s+--(?:only-stage|skip)=\S+)*)$/)
const planFilePath = flagMatch ? flagMatch[1].trim() : rawArg.trim()
const flagsStr = flagMatch ? flagMatch[2] : ''

// 解析标志
const userFlags = { onlyStage: null, skip: [] }
if (flagsStr) {
  const onlyMatch = flagsStr.match(/--only-stage=(\d+)/)
  if (onlyMatch) userFlags.onlyStage = parseInt(onlyMatch[1], 10)
  const skipMatch = flagsStr.match(/--skip=([\w_,]+)/)
  if (skipMatch) userFlags.skip = skipMatch[1].split(',').map(s => s.trim()).filter(Boolean)
}
```

无效的 stage 号（超出 0-5 范围）→ `log()` 警告，不抛错。

### 行为定义

| 参数 | 效果 |
|------|------|
| 无参数 | 行为不变——全流程 |
| `--only-stage=2` | 仅分类器 + 阶段 2；1/3/4/5/汇总/幂等性预检跳过 |
| `--only-stage=4` | 仅分类器 + 阶段 4；1/2/3/5/汇总/幂等性预检跳过 |
| `--skip=fan_out_impact` | 全流程但跳过阶段 1 |
| `--skip=code_audit,matrix_sync` | 全流程但跳过阶段 4+5 |
| `--only-stage=2 --skip=matrix_sync` | 组合：仅阶段 2，但若 only-stage 已限制则 skip 无额外效果 |

分类器（阶段 0）始终运行——后续阶段依赖其输出的 `classification` 对象，且仅消耗 2 个 agent（~5-10K token）。

`--only-stage` 时自动跳过：
- 汇总审查记录追加（未跑修改阶段，无需记录）
- 幂等性预检——但有例外：若 `--only-stage` 指向的阶段会修改文件（阶段 2/3/5），则**不跳过**幂等性预检，避免旧标注与新一轮修改混淆

阶段依赖与降级行为：

| 场景 | 行为 |
|------|------|
| `--only-stage=2` 无阶段 1 数据 | `allImpactFindings` 为空数组——Finder 仅基于计划文件 + 代码审查，不含扇出维度上下文。`FINDER_PROMPT` 已原生处理 null impact |
| `--only-stage=3` 门控 FAIL | **不退回阶段 2**（阶段 2 被 `--only-stage` 排除）。FAIL 直接记录到阻塞项章节 |
| `--only-stage=4` 审计断裂 | **不退回阶段 2**。断裂点记录到阻塞项章节 |
| `--only-stage=0` | 仅运行分类器 + 输出分类结果，跳过所有后续阶段 + 幂等性预检 + 汇总 |
| 无效 stage 号（如 `--only-stage=7`） | `log()` 警告 → 降级为全流程（行为等同无参数） |
| `--only-stage` + `--skip` 组合 | `onlyStage` 优先生效——skip 中与 onlyStage 冲突的项被忽略，skip 中其余项在 onlyStage 范围内仍生效 |

`shouldRunStage(N)` 与 `effectiveSkipStage(N)` 的区别：

```javascript
// 用户意图——仅来自 --only-stage 标志
const shouldRunStage = (n) => {
  if (userFlags.onlyStage === null) return true        // 无限制
  if (n === 0) return true                             // 分类器始终运行
  return n === userFlags.onlyStage
}

// 合并用户意图 + 分类器自动决定
const effectiveSkip = (name) => {
  // 分类器决定跳过（如 greenfield → 跳过 code_audit）
  if ((classification.skip_stages || []).includes(name)) return true
  // 用户 --skip 标志
  if (userFlags.skip.includes(name)) return true
  return false
}
```

### 使用示例

```bash
# 迭代修改计划后重跑对抗循环
/workflow plan-review "docs/02-待办/P40 预发布缺陷修复计划.md --only-stage=2"

# 写实施步骤时即时验证代码一致性
/workflow plan-review "docs/02-待办/P40 预发布缺陷修复计划.md --only-stage=4"

# 跳过门控和审计，快速跑完
/workflow plan-review "docs/02-待办/P40 预发布缺陷修复计划.md --skip=fan_out_impact,code_audit"
```

---

## 参考 P38

P38（计划审查工作流设计）为本计划提供了以下设计基础：

### 双工作流拆分前例（P38 §3.4 方案 A）

P38 曾设计将全流程拆为两次独立调用——`plan-review-phase0-3` + `plan-review-phase4-5`——通过 `.claude/plan_review_state.json` 传递中间状态。这验证了「阶段独立运行」在本项目中已有架构先例。P42 的不同之处在于：拆分点由用户运行时决定（`--only-stage=N`），而非硬编码在阶段 3 之后。

### 阶段间数据依赖（P38 §2.1 + §3.1–3.6）

P38 详细描述了各阶段的输入来源，汇总如下：

| 阶段 | 依赖前序数据 | `--only-stage` 降级 |
|------|-------------|---------------------|
| 1 | `classification.dimensions`（阶段 0） | —（分类器始终运行） |
| 2 | `allImpactFindings`（阶段 1）+ `classification` | `allImpactFindings` 降级为空数组 |
| 3 | 计划文件当前状态（经阶段 2 修改）+ `classification` | 文件为上次运行后状态 |
| 4 | 计划文件当前状态 + `classification` | 同上 |
| 5 | `classification.plan_identity`（阶段 0） | —（分类器始终运行） |

结论：**阶段 0（分类器）是所有阶段的唯一共同前置**——P42 规定分类器始终运行的设计判断被 P38 的依赖关系验证。

### `skip_stages` 自动跳过逻辑（P38 §3.1）

P38 分类器已有一套自动跳过规则（`greenfield` → 跳过 `code_audit`；`simple` + 无 `.py` → 跳过 `fan_out_impact` + `code_audit`）。P42 的 `effectiveSkip()` 在此基础上叠加用户显式控制——两套逻辑互补，不替代。

### Token 消耗基线（P38 §七）

P38 估算：simple ~100–150K / medium ~200–300K / complex ~350–500K+。P42 的动机——「避免重复跑全流程浪费 350K+ token」——基于此数据。`--only-stage=2` 预计可将重跑成本降至 ~30–60K。

> P38 最终采用方案 B（日志警告）而非双工作流拆分——当时认为固定拆分点的维护复杂度大于收益。P42 的用户自选拆分点（`--only-stage=N`）消除了这一权衡：拆分逻辑通用、无额外维护负担。

---

## 影响面

| 维度 | 评估 |
|------|------|
| 向后兼容 | ✅ 无参数时行为完全不变 |
| 其他 workflow | 无——仅 plan-review.workflow.js 一个文件 |
| 幂等性 | 修改文件的阶段（2/3/5）不跳过预检；纯读阶段跳过 |
| 分类器 | 始终运行，`--only-stage` 不影响分类逻辑 |
| 回溯机制 | `--only-stage` 模式下禁用跨阶段回溯，FAIL 直接记录阻塞项 |
| 风险 | 低——改动是纯门控（if 包裹），不修改任何阶段内部逻辑 |

## 实施

**涉及文件：** `.claude/workflows/plan-review.workflow.js`（修改 ~40 行）

**步骤：**
1. 替换 L576 args 解析——支持字符串中 `--only-stage=N` / `--skip=X,Y` 标志提取（正则见「Args 解析方案」）
2. 新增 `userFlags` 对象 + `shouldRunStage(N)` / `effectiveSkipStage(N)` 辅助函数（插入在 L770 `skipStage()` 之后）
3. 阶段 1-5 入口包裹门控：
   - 阶段 1（L776）：`if (shouldRunStage(1) && !effectiveSkip('fan_out_impact') && ...)`
   - 阶段 2（L799-907）：`if (shouldRunStage(2))` 包裹整段对抗循环
   - 阶段 3（L910-1018）：`if (shouldRunStage(3))` 包裹门控；FAIL 时检查 `shouldRunStage(2)` 决定是否回溯
   - 阶段 4（L1021）：`if (shouldRunStage(4) && !effectiveSkip('code_audit'))`
   - 阶段 5（L1086-1107）：`if (shouldRunStage(5))` 包裹矩阵同步
4. 幂等性预检（L585-621）：仅当 `shouldRunStage(2) || shouldRunStage(3) || shouldRunStage(5)` 时执行（会修改文件的阶段）
5. 汇总追加（L1125-1142）：`if (userFlags.onlyStage === null)` 时执行（全流程模式）
6. 更新 L1-3 文件头部注释——增加 `--only-stage=N` / `--skip=X,Y` 用法说明

**工时：** 1h（原估算 0.5h → 考虑边界处理 + 测试）

**测试：**
- 无参数调用 → 全流程不变（行为完全向后兼容）
- `--only-stage=0` → 仅输出分类结果，不修改文件
- `--only-stage=2` → 分类 + 对抗循环（幂等性预检执行——阶段 2 会修改文件）
- `--only-stage=3` → 分类 + 门控；门控 FAIL 直接记录阻塞项（不回溯阶段 2）
- `--only-stage=4` → 分类 + 代码审计（幂等性预检跳过——纯读阶段）
- `--skip=fan_out_impact` → 跳过阶段 1，其余正常
- `--skip=code_audit,matrix_sync` → 跳过阶段 4+5，其余正常
- `--only-stage=2 --skip=matrix_sync` → 仅阶段 2，skip 无额外效果（onlyStage 优先）
- 无效 stage 号 `--only-stage=7` → 警告 + 降级为全流程
