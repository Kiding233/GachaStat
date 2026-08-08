<!-- META: P74 | module:UI框架替换 | status:designing | last:2026-08-05 -->

# P74 UI换头计划：pywebview + Vue3 + Element Plus + ECharts

> 日期：2026-08-05 | 状态：设计中
> 触发：用户要求全面替换 PyQt6 + Plotly（WebEngine）为更现代、更灵活、视觉更好的 UI，且不随安装包附带浏览器内核。
> 前置：完整调查与实证验证已完成，见 [调查报告-换头计划-UI框架替换-2026-08-05](../04-收件箱/调查报告-换头计划-UI框架替换-2026-08-05.md)

## 一、问题

当前 GUI 层（`gui/` 17,492 行，PyQt6 + QWebEngineView + Plotly）存在三方面成本：

1. **体积**：Chromium 内核约 120MB，占打包产物 50-65%（[应用打包 01-理论](../subsystems/应用打包/01-理论.md) §3.3 已记录），PyInstaller 无法缩减
2. **视觉与交互**：Qt 原生观感偏工具型，无 UI 热重载，现代化程度不足
3. **开发效率**：改 UI 代码需重启进程，无热重载反馈

## 二、已验证结论（POC 阶段 0，2026-08-05 实证）

| 结论 | 依据 |
|------|------|
| core/service/CLI 零 Qt 耦合，计算引擎可 100% 保留 | grep 核验（约 800 个 core 测试不受影响） |
| ChartSpec IR 是合格前后端数据契约 | 垂直切片：同一 ChartSpec 由 Plotly.js / ECharts 各自渲染成功 |
| pywebview（WebView2）本机可用，大数据跨桥零卡顿 | 链路穿透：真实 run_batch_parallel 200 次 / 3s / 1.9MB 一次跨桥 |
| 技术选型（用户实测判定） | pywebview + Vue 3 + Element Plus + ECharts，四步实证见调查报告第 8 章 |

验证产物：`tools/poc_webview/`（最小示例 / 垂直切片 / 链路穿透 / ui_compare 组件库对比）。

## 三、目标

换头完成后：
- `gui/` 无 PyQt6 / QWebEngineView / plotly 依赖，重建为 Vue 3 + Element Plus 前端
- 打包产物不捆绑 Chromium，体积显著下降（总包下限受 scipy 制约，约 150-200MB）
- 开发期获得热重载（Vite HMR），生产期加载构建产物
- 图表层改用 ECharts（ChartSpec 前端 renderer，后端零改动）
- 计算引擎零改动，~800 个 core 测试不动；同配置同种子模拟结果行为等价
- CLI / headless 路径不受影响

## 四、方案（技术选型）

| 层 | 选型 | 理由 |
|----|------|------|
| 窗口容器 | pywebview（系统 WebView2） | 不捆绑浏览器内核；Python 仍是主进程，multiprocessing.Pool 并行模拟零改动 |
| 前端框架 | Vue 3 | 模板声明式贴近 Qt 心智，Python 团队上手平缓 |
| 组件库 | Element Plus | 四库并排实测（Element/Naive/Arco/Ant）用户判定最佳 |
| 图表库 | ECharts | 垂直切片实测视觉/交互/体积全面胜出（echarts.min.js 约 1MB） |
| 构建 | Vite | dev server 热重载 + 生产构建产物 |

## 五、阶段拆分

```
阶段 0 ✅ 调查与验证（2026-08-05 已完成）
        调查报告 + POC 四步实证，技术选型落定

阶段 1a UI 设计体系（决策确认：全量对照表 / 不装新 skill / 规范放 00-meta/UI设计体系/）
        全量组件对照表：现有 Qt 控件 → Element Plus 组件映射（约 36 条，含 8 种复合机制）
        演示页面：展示所有组件与机制，基于真实模拟数据（复用垂直切片/链路穿透数据管道）
        在演示页确定 UI 设计规范：design tokens（语义色/字体/间距/圆角）+ 组件/布局/图表/交互规范
        产出 UI 规范文件：docs/00-meta/UI设计体系/（UI设计规范.md + 组件对照表.md）
        design tokens CSS 实现放前端工程（src/styles/tokens.css）

阶段 1b 图表与容器层
        ChartSpec → ECharts 前端 renderer
        pywebview 容器替换 ChartWebView
        Vite 工程化（Vue 3 + Element Plus + ECharts 脚手架）
        大数据 HTTP 通道（MB 级结果）

阶段 2  面板逐批迁移
        第一批：简单面板（数据管理/比较分析/插件管理）
        第二批：中等面板（统计分析/过程分析/方案搜索/脆弱性/最差影响/批量模拟）
        第三批：config_panel（5895 行复杂表单，最后迁移）

阶段 3  收尾
        移除 PyQt6 / PyQt6-WebEngine / plotly 依赖
        PyInstaller spec 重写 + 体积验证
        GUI 测试迁移 + 全量回归（core 测试不动）
```

## 六、影响面

| 对象 | 变更 |
|------|------|
| `gui/`（17,492 行） | 全部重建为前端面板 |
| `visualization/plotly_charts.py` | PlotlyRenderer 退役，ChartSpec IR 保留 |
| `core/vulnerability.py` | 2 处直接 import plotly（绕过 IR），需迁移到 ChartSpec 或前端 |
| `GachaStat.spec` | 重写（移除 Qt/WebEngine/plotly，加入前端产物 + WebView2 相关） |
| `pyproject.toml` | gui 依赖调整（PyQt6 → pywebview） |
| 图表引擎子系统 | ChartSpec 保留为数据契约，渲染层前端化 |

## 七、风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| config_panel 复杂表单迁移 | 🔴 高 | 最后迁移，保留 Qt 版并行直至覆盖 |
| 技术栈变双语言（Python + JS） | 🟡 中 | 前端只做表现层，业务逻辑全在 Python |
| WebView2 旧系统依赖 | 🟢 低-中 | 本机 Win 11 已验证；旧系统可选 Evergreen bootloader |
| 大数据 HTTP 通道 | 🟡 中 | 阶段 1 专项验证 |
| scipy 体积制约总包下限 | 🟡 中 | 若体积是硬约束，另行评估 scipy 裁剪（与 P73 协同） |

## 八、待决策 / 待验证

- ✅ 已决策（2026-08-05）：全量组件对照表（接受 1-2 天）/ 不装新 skill（用已有 frontend-design + dataviz）/ UI 规范位置 docs/00-meta/UI设计体系/
- 迁移节奏：阶段化（推荐）vs 一次性大爆炸
- 大数据 HTTP 通道方案（阶段 1 验证）
- config_panel 迁移策略（表单密度最高的面板）
- 打包体积实测目标值

## 九、验收

- `core/` 测试全过（~800），CLI 路径不变
- 10 面板功能在 Vue 前端可复刻（对照报告 §2.4 Tab 列表）
- 打包产物不含 Chromium，体积显著低于现状
- 开发环境热重载可用
- 同配置同种子模拟结果与旧版行为等价
