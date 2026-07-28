---
name: plan-execute
description: 一站式计划执行——加载→逐任务 subagent 执行→Fidelity 审计循环(loop-until-dry)→验证→收尾。不修改 superpowers。
---

# Plan-Execute Skill — 计划执行 + Fidelity 审计

将计划文件通过五阶段流水线完整执行，含事后 fidelity 审计循环，确保实施结果与计划零偏差。

## 触发

- `/plan-execute <计划文件路径>` — slash command
- `/plan-execute <计划文件路径> --skip-audit` — 跳过审计（仅执行）
- `/plan-execute <计划文件路径> --audit-only` — 仅审计（已完成实现）
- `/plan-execute <计划文件路径> --max-rounds 3` — 指定审计循环最大轮数

## 流程

### 1. 校验

- 计划文件存在且可读
- 文件含有效 checkbox 任务列表（`- [ ] Task N: ...`）
- 工作区干净（`git status --porcelain` 为空或仅含预期文件）
- 非 main/master 分支（非阻塞警告，不终止流程）

### 2. 提取元数据

- 解析 META 头获取 P 编号、模块、状态
- 统计任务数
- 提取全局约束（架构约束、命名约定等）

### 3. 注入上下文

- 项目 CLAUDE.md（架构约束、扩展指南）
- 相关源码目录结构
- superpowers 脚本路径（task-brief、review-package）

### 4. 调用 Workflow

将以下参数传递给 `plan-execute.workflow.js`：
- `planFilePath`：计划文件绝对路径
- `skipAudit`：是否跳过阶段 3-4
- `auditOnly`：是否仅运行阶段 3-4
- `maxRounds`：审计循环最大轮数（默认 5）

### 5. 报告结果

Workflow 完成后汇总输出：
- 执行阶段：N 任务完成 / 审查通过
- 审计阶段：N 轮收敛 / 熔断 + 残留发现数
- 验证阶段：测试通过 / 失败
- 收尾阶段：分支状态

## 参数

| 参数 | 说明 |
|------|------|
| `--skip-audit` | 跳过阶段 3-4（仅执行，用于信任度高的简单计划） |
| `--audit-only` | 跳过阶段 2（对已完成的实现做 fidelity 审计+验证，diff 基准为 HEAD vs merge-base） |
| `--max-rounds N` | 审计循环最大轮数（默认 5） |

## 约束

- 不修改任何 superpowers 6.1.1 技能文件
- 阶段 2 串行执行（任务按计划中的依赖顺序排列）
- 审计循环连续 2 轮零新发现（任意严重度）→ 收敛；超过 max-rounds → 熔断
- 进度写入 `.superpowers/plan-execute/progress.md` 账本文件，支持断点恢复
