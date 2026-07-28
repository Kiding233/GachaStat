<!-- META: P66 | module:harness | status:implementing | last:2026-07-20 -->

# P66 plan-execute：计划执行 + Fidelity 审计一站式 Workflow

> 日期：2026-07-20 | 状态：实现中
> 触发：用户需求——在现有 superpowers 指导基础上补充实施后自动反复对照计划文件检查的环节

## 一、问题

当前 superpowers 开发生命周期的执行阶段存在三个缺口：

1. **碎片化**：`executing-plans` → `verification-before-completion` → `finishing-a-development-branch` 需手动串联，无统一编排。`executing-plans` 是轻量手动技能，本身建议「有 subagent 用 subagent-driven-development」
2. **无事后 fidelity 检查**：`verification-before-completion` 核验的是声明（如测试是否通过），而非「计划是否被完整且准确实现」。`plan-review` workflow (P38) 是**事前**审查计划文件质量，非事后对照
3. **无收敛保证**：修复后没强制重查机制，遗漏和偏差可能残留

## 二、目标

提供一个 `/plan-execute` 命令，一站式完成：加载计划 → 逐任务执行（subagent-driven 模式）→ Fidelity 审计循环（loop-until-dry 收敛）→ 验证 → 收尾。实施结果与计划文件之间零偏差。

成功标准：
- `/plan-execute <计划文件>` 可触发完整五阶段流水线
- 审计循环自动收敛（连续 2 轮零新发现）或熔断（最多 5 轮）
- 支持 `--skip-audit` 和 `--audit-only` 两种变体模式
- 不修改任何 superpowers 现有文件

## 三、方案

### 整体架构

Skill + Workflow 双层结构，与现有 `/plan` skill + `plan-review` workflow 模式一致：

```
/plan-execute <计划文件>
       │
       ▼
┌─────────────────────────────────────┐
│  Skill: .claude/skills/plan-execute/│
│  - 校验 + 上下文注入 + 调用 WF      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Workflow: plan-execute.workflow.js │
│  阶段1: 加载 & 预检                 │
│  阶段2: 执行（逐任务 subagent）      │
│  阶段3: Fidelity 审计循环（新增）    │
│  阶段4: 验证（pytest + code review）│
│  阶段5: 收尾（finishing-a-branch）   │
└─────────────────────────────────────┘
```

### 阶段 2：执行

复用 subagent-driven-development 模式，串行 pipeline：
- `task-brief` 提取任务文本 → 派发 implementer（新鲜子代理）→ 自审查 → `review-package` 生成 diff → 派发 task reviewer → 通过/修复循环 → 写入进度账本

### 阶段 3：Fidelity 审计循环（核心新增）

5 个审计维度并行派发：

| # | 维度 | 检查内容 |
|---|------|---------|
| 1 | 完整性 | 计划的每个 checkbox → diff 中是否有对应实现 |
| 2 | 接口 fidelity | 函数签名/类结构/模块边界是否与计划一致 |
| 3 | 约束 fidelity | 架构约束/命名约定/技术栈是否遵守 |
| 4 | 计划外变更 | diff 中是否有计划未提及的变更 |
| 5 | 测试覆盖 | 计划中的测试场景是否都有对应测试 |

合并 → 去重 → 分类（Critical/Important/Minor）→ 派发单一 fixer → 重审。

```
dry = 0
while dry < 2:
    findings = 并行审计()
    if 为空: dry++
    else: dry = 0; fixer(findings)
```

收敛：连续 2 轮零新发现（任意严重度）。熔断：最多 5 轮。

### 参数

| 参数 | 说明 |
|------|------|
| `--skip-audit` | 跳过阶段 3-4（仅执行） |
| `--audit-only` | 跳过阶段 2（仅审计+验证，diff 基准为 HEAD vs merge-base） |
| `--max-rounds N` | 审计最大轮数（默认5） |

## 四、波及范围

### 新建文件

| 文件 | 用途 |
|------|------|
| `.claude/skills/plan-execute/SKILL.md` | Skill 入口定义 |
| `.claude/workflows/plan-execute.workflow.js` | 五阶段编排脚本 |
| `.claude/skills/plan-execute/auditor-completeness.md` | 审计维度 1 提示模板 |
| `.claude/skills/plan-execute/auditor-interface.md` | 审计维度 2 提示模板 |
| `.claude/skills/plan-execute/auditor-constraints.md` | 审计维度 3 提示模板 |
| `.claude/skills/plan-execute/auditor-extras.md` | 审计维度 4 提示模板 |
| `.claude/skills/plan-execute/auditor-coverage.md` | 审计维度 5 提示模板 |

### 依赖现有文件（只读复用，不修改）

> 注：以下文件为 superpowers 6.1.1 宿主环境提供的稳定接口，由 Claude Code harness 全局注入，不在项目本地磁盘。workflow.js 当前使用内联实现（内嵌提示词函数）以确保自包含性，与 superpowers 脚本接口逻辑等价。后续可在 harness 支持文件读取后迁移为引用外部模板。

| 文件 | 用途 |
|------|------|
| `superpowers 6.1.1/skills/subagent-driven-development/scripts/task-brief` | 提取任务文本（宿主环境全局注入） |
| `superpowers 6.1.1/skills/subagent-driven-development/scripts/review-package` | 生成 diff 包（宿主环境全局注入） |
| `superpowers 6.1.1/skills/subagent-driven-development/implementer-prompt.md` | 实现者提示模板（宿主环境全局注入） |
| `superpowers 6.1.1/skills/subagent-driven-development/task-reviewer-prompt.md` | 审查者提示模板（宿主环境全局注入） |
| `superpowers 6.1.1/skills/requesting-code-review/code-reviewer.md` | 最终审查模板（宿主环境全局注入） |
| `superpowers:finishing-a-development-branch` | 收尾 git 操作（宿主环境全局注入） |

### 不修改的文件

- 所有 superpowers 6.1.1 技能文件
- 项目 CLAUDE.md（后续按需添加 plan-execute 说明）

## 五、风险

| 风险 | 缓解 |
|------|------|
| Workflow 脚本复杂度过高（5 阶段 + 审计循环） | 阶段 1/4/5 极简；核心逻辑仅在阶段 2/3 |
| 审计 agent 输出格式不一致导致合并困难 | 使用结构化 schema 约束输出；合并逻辑在脚本层纯函数 |
| loop-until-dry 可能消耗大量 token | 默认 5 轮熔断 + 每轮合并为单一 fixer |
| 与 superpowers 未来版本不兼容 | 仅依赖稳定脚本接口（task-brief/review-package），不依赖内部实现 |

## 六、验收标准

- [ ] `/plan-execute <计划文件>` 可触发完整五阶段流水线
- [ ] 阶段 2 逐任务执行 + 审查 + 修复循环正常工作
- [ ] 阶段 3 审计循环收敛：5 维度并行审计 → 合并 → fix → 重审
- [ ] loop-until-dry：连续 2 轮零新发现自动停止
- [ ] 熔断保护：超过 max-rounds 输出未解决清单
- [ ] `--skip-audit` 模式跳过阶段 3-4
- [ ] `--audit-only` 模式跳过阶段 2
- [ ] 进度账本支持断点恢复（兼容 subagent-driven-development 格式）
- [ ] 不修改任何 superpowers 文件
