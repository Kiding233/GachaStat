# plan-execute：计划执行 + Fidelity 审计 Workflow 设计方案

> 状态：设计完成 | 日期：2026-07-20

## 一、动机

当前 superpowers 开发生命周期的执行阶段存在三个缺口：

1. **碎片化**：`executing-plans` → `verification-before-completion` → `finishing-a-development-branch` 需手动串联，无统一编排
2. **无事后 fidelity 检查**：`verification-before-completion` 核验的是「声明是否属实」（如测试是否通过），而非「计划是否被完整且准确地实现」
3. **无收敛保证**：修复后没有强制重新检查的机制，遗漏和偏差可能残留

本设计提供一个一站式 workflow——从计划加载、逐任务执行、fidelity 审计循环到收尾，确保实施结果与计划文件之间零偏差。

## 二、整体架构

```
/plan-execute <计划文件>
       │
       ▼
┌─────────────────────────────────────┐
│  Skill: plan-execute                │
│  - 校验计划文件存在/格式             │
│  - 注入项目上下文（CLAUDE.md 等）    │
│  - 解析计划元数据（任务数/模块等）   │
│  - 调用 Workflow                    │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Workflow: plan-execute.workflow.js │
│                                     │
│  阶段 1: 加载 & 预检                 │
│  阶段 2: 执行（逐任务实现+审查）      │
│  阶段 3: Fidelity 审计循环 ← 新增    │
│  阶段 4: 验证（测试 + 声明核验）     │
│  阶段 5: 收尾（git 操作）            │
└─────────────────────────────────────┘
```

**与现有体系的关系：** 本 workflow 不修改任何 superpowers 技能，独立叠加。它内嵌 subagent-driven-development 的执行模式，并取代了 `executing-plans` → `verification-before-completion` → `finishing-a-development-branch` 的手动串联。

## 三、Skill 入口

### 调用方式

```
/plan-execute <计划文件路径>
```

### 参数

| 参数 | 说明 |
|------|------|
| `--skip-audit` | 跳过阶段 3-4（仅执行，用于信任度高的简单计划） |
| `--audit-only` | 跳过阶段 2（对已完成的实现做 fidelity 审计+验证，diff 基准为当前 HEAD vs merge-base） |
| `--max-rounds N` | 审计循环最大轮数（默认 5） |

### Skill 职责

1. 校验：文件存在、格式合法、含有效任务列表
2. 确认：工作区干净（`git status`）、非 main/master 分支
3. 提取元数据：任务数、模块范围、全局约束
4. 注入上下文：项目 CLAUDE.md + 相关源码结构
5. 调用 workflow 脚本
6. 报告结果：收敛状态 + 审计摘要 + 下一步建议

## 四、Workflow 五阶段

### 阶段 1：加载 & 预检

- 读取计划文件，解析任务列表
- 使用 `scripts/task-brief` 提取每任务精确文本
- 批量扫描矛盾：任务间是否自相矛盾、是否与全局约束冲突（与 subagent-driven-development 的 Pre-Flight Plan Review 一致）
- 创建 `.superpowers/plan-execute/progress.md` 账本文件

### 阶段 2：执行

采用 subagent-driven-development 的每任务模式，**串行执行**（计划本身按依赖顺序排列）：

```
pipeline(所有任务):
  task-brief 提取任务文本
  → 派发 implementer（新鲜子代理，仅含该任务上下文）
    → 实现 → 测试 → 提交 → 自审查 → 写报告文件
  → review-package 生成 diff
  → 派发 task reviewer（规格合规 + 代码质量）
    → 有问题 → 派发 fixer → 重审
    → 通过 → 追加进度账本
```

关键复用：
- `scripts/task-brief`：提取单个任务文本
- `scripts/review-package`：生成 diff 包
- `implementer-prompt.md` / `task-reviewer-prompt.md`：子代理提示模板
- `.superpowers/sdd/progress.md`：账本格式（兼容 subagent-driven-development 的断点恢复）

状态处理与 subagent-driven-development 完全一致（DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED）。

### 阶段 3：Fidelity 审计循环（核心新增）

#### 输入

每个审计 agent 收到：
- 计划文件（任务文本 + 全局约束）
- git diff（`MERGE_BASE..HEAD`，通过文件传递，不进入主上下文）
- 进度账本（各任务 commit 范围，快速定位每个任务的变更）

#### 五个审计维度（并行派发）

| # | 维度 | 检查内容 |
|---|------|---------|
| 1 | 完整性 | 计划的每个 checkbox → git diff 中是否有对应实现 |
| 2 | 接口 fidelity | 计划中的函数签名/类结构/模块边界 → 实际代码是否一致 |
| 3 | 约束 fidelity | 计划中的架构约束/命名约定/技术栈 → 是否有违反 |
| 4 | 计划外变更 | git diff 中是否有计划未提及的新增/删除/修改 |
| 5 | 测试覆盖 | 计划中的测试场景 → 是否存在对应测试用例 |

每个审计 agent 输出结构化发现列表，含 `file`、`location`、`severity`、`evidence` 字段。

#### 合并 & 去重

在 Workflow 脚本层执行（不派发 agent）：
- 按 `file + line` 去重（同位置发现归属最高严重度）
- 分类：Critical（功能缺失/接口不一致）→ Important（约束违反/计划外变更）→ Minor（命名偏差/注释遗漏）
- 生成统一 `findings.json`

#### 修复

- 单轮内所有发现合并为一份清单
- 派发**一个** fix agent（避免多 fixer 上下文重叠和冲突）
- fix agent 收到完整 findings 清单 + 计划原文
- fix 完成后自动运行相关测试，结果写入报告

#### 收敛判定

```
dry = 0
while dry < 2:
    findings = 并行审计()
    if findings 为空:
        dry += 1
    else:
        dry = 0
        派发 fixer(findings)
```

连续 2 轮零新发现（任意严重度，含 Minor）→ 收敛。2 轮而非 1 轮是防止「修复引入新问题但首轮审计维度未覆盖到」的情况。

#### 熔断保护

- 最大轮数默认 5，可通过 `--max-rounds` 配置
- 超过上限仍未收敛 → 输出未解决发现清单，交人工裁决
- 不会因熔断而中止——输出清晰的状态报告

### 阶段 4：验证

- 运行 `pytest --cov`，确认全部通过
- 最终全分支 code review（复用 `requesting-code-review` 的 `code-reviewer.md` 模板）

### 阶段 5：收尾

- 调用 `superpowers:finishing-a-development-branch`
- 清理 `.superpowers/plan-execute/` 临时文件

## 五、文件清单

| 文件 | 位置 | 用途 |
|------|------|------|
| `SKILL.md` | `.claude/skills/plan-execute/` | Skill 定义，含参数说明和入口逻辑 |
| `plan-execute.workflow.js` | `.claude/workflows/` | Workflow 编排脚本，五阶段完整流程 |
| `auditor-completeness.md` | `.claude/skills/plan-execute/` | 审计维度 1：完整性检查提示模板 |
| `auditor-interface.md` | `.claude/skills/plan-execute/` | 审计维度 2：接口 fidelity 提示模板 |
| `auditor-constraints.md` | `.claude/skills/plan-execute/` | 审计维度 3：约束 fidelity 提示模板 |
| `auditor-extras.md` | `.claude/skills/plan-execute/` | 审计维度 4：计划外变更提示模板 |
| `auditor-coverage.md` | `.claude/skills/plan-execute/` | 审计维度 5：测试覆盖提示模板 |

## 六、边界 & 限制

1. **串行执行**：阶段 2 任务串行执行。第一版不做并行依赖解析，计划本身应按依赖顺序排列任务
2. **不修改 superpowers**：完全独立叠加，不复写任何现有技能文件
3. **依赖 Git**：审计依赖 `git diff` 和 `git merge-base`，仅适用于 Git 仓库
4. **计划格式假设**：假设计划文件使用 checkbox 语法（`- [ ] Task N: ...`），与 `writing-plans` 技能输出格式兼容
5. **Token 消耗**：审计循环每轮 5 个并行 agent，通常 1-3 轮收敛，预估 50K-200K token

## 七、后续迭代方向

- 任务并行执行：解析计划中的 `[parallel]` 标注，独立任务并发
- 对抗验证增强：对审计发现追加 skeptic 反驳层（`--strict` 模式）
- 增量审计：仅审计未通过维度，减少重复检查
