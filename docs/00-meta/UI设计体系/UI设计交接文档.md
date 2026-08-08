# UI 设计工作交接文档（P74 阶段 1a → 设计 Agent）

> 日期：2026-08-05
> 目的：把 GachaStat UI 换头计划的设计工作完整交接给设计 Agent。本文自包含，不依赖任何会话上下文。

---

## 1. 任务与背景

**项目**：GachaStat，抽卡概率模拟与分析系统（Python 桌面应用，统计工具定位）。

**任务**：为 UI 从 Qt 迁移到 Web 前端设计一套完整、统一的 UI 设计规范，并产出设计 tokens 与演示页面。当前处于 P74 换头计划「阶段 1a UI 设计体系」。

**为什么**：现有 UI 用 PyQt6 + Plotly WebEngine，观感工具化、无热重载、体积大。换头为 pywebview + Vue3 + Element Plus + ECharts。技术可行性已由 POC 四步实证（环境桥/ChartSpec 跨端/链路穿透/组件库对比）确认。

**当前状态**：技术选型已定，演示页骨架 + config 面板已完成初版，设计方向经过两轮用户反馈迭代。**设计规范尚未定稿，10 个设计裁决点待定。**

---

## 2. 技术栈与运行方式

| 层 | 选型 |
|----|------|
| 窗口容器 | pywebview（系统 WebView2，不捆绑浏览器内核，Python 主进程） |
| 前端框架 | Vue 3（组合式 API，`<script setup>`） |
| 组件库 | Element Plus（已选，4 库对比用户判定） |
| 图表库 | ECharts（垂直切片用户判定） |
| 构建 | Vite（dev server 热重载） |

**演示页位置**：`tools/poc_webview/ui_compare/`
- 启动：`python tools/poc_webview/ui_compare/load_compare.py`（一键启动，自动拉起 Vite）
- 源码：`src/`（main.js 入口 / App.vue 骨架 / panels/ 面板 / styles/ 样式）
- 开发热重载：改 `src/` 下文件，窗口实时更新

**关键架构事实**：
- 计算引擎（core/service/CLI）零 Qt 耦合，约 800 个 core 测试不动，前端只做表现层
- `ChartSpec` 是纯数据中间表示（可 JSON 序列化），后端推数据，前端渲染，后端零改动
- JS↔Python 桥：pywebview js_api，已验证 1.9MB 数据跨桥零卡顿

---

## 3. 已确定的设计决策（不得推翻，除非用户明确改）

以下决策已经用户确认，是设计工作的硬约束：

1. **技术选型**：pywebview + Vue3 + Element Plus + ECharts（不可改）
2. **统计工具定位**：密集信息展示 + 语义色强调结果状态，不是娱乐向界面
3. **中文界面**：所有文案中文，中文字体 Microsoft YaHei / PingFang SC
4. **视觉方向：黑白灰骨架 + 彩色语义点缀**
   - 大面积元素（背景/卡片/文字/表格）用黑白灰
   - 彩色只做语义点缀：蓝（主操作/图表系列）、绿（成功/达标）、红（危险/劣势）、黄（警告）
   - **结构感由色块层次 + 轻阴影承担，不用硬边框**（「黑框太突兀」已回退）
5. **无内容切换动画**（淡入上滑被视为 AI 味）；切换反馈体现在 Tab 行的样式（悬停整体变灰）
6. **界面结构**：顶部工具栏（品牌 + 文件/工具/帮助菜单）+ 内容 Tab 区 + 底部状态栏（状态消息 + 当前数据集）
7. **主操作色蓝色系**（当前值 #1976d2，可微调但保持蓝色系）
8. **A4 配置自动更新**：前端响应式为主 + 防抖写回 Python ConfigStore
9. **布局对齐现有 Qt**（不是自由发挥）：Master-Detail、参数区 + 图表区、QGroupBox 语义分区

> **视觉现状（2026-08-05 移交时）**：已迭代两版（绿色系 → 黑白灰 + 色块层次），用户均不完全满意（"黑框太突兀已回退"、"色块版还是不大行"）。**设计工作交由专门 design harness 继续**，本节 1-9 为已确定的方向约束，具体视觉方案由 design harness 产出并交用户验收。当前演示页视觉为中间态，非最终。

---

## 4. 现有 Qt 设计资产（可迁移素材，已由代码考察整理）

### 4.1 组件对照表（核心素材）
`docs/00-meta/UI设计体系/组件对照表.md`
- 10 类约 40 条 Qt 组件 → Element Plus 映射（表格/输入/选择/按钮/容器/反馈/对话框/异步/图表/其他）
- 每条含典型用法、映射注意点、【保留/重设计/待裁决】标注
- 含复合机制映射（Master-Detail、参数+图表区、运行按钮生命周期、语义色、异步契约、表单校验）
- 含语义色 design tokens 初稿

### 4.2 布局模式（源自 Qt，迁移对齐目标）
| 模式 | 结构 |
|------|------|
| Master-Detail（config 卡池管理） | 左列表（筛选+启用勾选+增删复制）+ 右详情表单 + 池子/生命周期子 Tab |
| 参数区 + 图表区（全分析面板） | 左参数卡（QScrollArea 包裹分组表单）+ 右结果区（图表容器），比例约 250-420 / 700-920 |
| 配置 9 子 Tab | 卡牌定义/资源管理/卡池管理/保底机制/累抽奖励/抽卡策略/目标卡/权重配置/满突溢出 |
| 标签即语义 | 表单标签「中文名 + 冒号」，单位含在标签（如"概率(%)"） |
| 动作栏 | 运行按钮 + 进度条 + 状态文案，位于面板底部 |

### 4.3 语义色体系（源自 Qt，应保留为 tokens）
| 颜色 | 语义 |
|------|------|
| #4CAF50 绿 | 主操作（Qt 运行按钮）/ 推荐 |
| #2196F3 蓝 | 图表主系列 |
| #1976d2 蓝 | 主操作（另一分支） |
| #f44336 / #c62828 红 | 危险/停止/劣势/校验失败 |
| #2e7d32 深绿 + #e8f5e9 浅绿 | 显著/达标（p<0.05 标记） |
| #2c3e50 深蓝灰 | 强调文字/大数字 |
| #888 / #666 灰 | 次级文字 |
| #f5f5f5 浅灰 | 结果区/只读背景 |
| Tableau 10 色板 | 多策略图表系列 |

---

## 5. 待裁决的设计点（10 个，需要设计 Agent 逐一给出方案并让用户确认）

1. **运行按钮主色**：现有 Qt 三套并存（绿 analysis/plan_search、蓝 comparison/data_manager、无 gacha/retreat）→ 统一为一种。当前方向蓝色系
2. **可编辑表格策略**：只读 vs item 编辑 vs 内联控件（setCellWidget）→ 建议「el-table 只读 + 需编辑列 slot 内联控件」
3. **表格排序**：Qt 全项目 0 处 → 是否补 el-table sortable（行为增强）
4. **进度显示**：常驻 vs 运行中显示 vs (done,total) → 统一
5. **选择交互**：QListWidget（Master 列表）vs QComboBox（普通选择）→ 两种场景的对应组件
6. **时间数据模型**：唯一 QDateEdit（日期）vs 浮点天 spinbox → 统一方案
7. **表单校验时机**：Qt 全后置（保存时校验）vs el-form 即时校验 → 建议前移
8. **按钮反馈**：Qt comparison 文字突变 vs 仅禁用 → 统一为 :loading
9. **状态展示**：面板内 QLabel vs 全局状态栏 → 统一
10. **图表色板**：comparison Tableau 10 vs 其余单色 → 全局图表色板规范

---

## 6. 演示页现状（Design Handoff 的代码起点）

```
tools/poc_webview/ui_compare/
├── index.html                 # 挂载 #app
├── vite.config.js
├── load_compare.py            # 一键启动（自动拉起 Vite + pywebview）
├── src/
│   ├── main.js                # 挂载 App.vue（Element Plus + tokens + base）
│   ├── App.vue                # 应用骨架：工具栏 + 10 Tab + 状态栏
│   ├── styles/
│   │   ├── tokens.css         # design tokens（Element Plus 主题覆盖 + 项目 tokens）
│   │   └── base.css           # 基础样式：外壳/面板/Tab 交互
│   └── panels/
│       ├── ConfigPanel.vue    # 配置面板纯 UI（最完整，9 子 Tab + Master-Detail + 内联表格 + 对话框）
│       └── Placeholder.vue    # 占位面板
├── compare/                   # 旧组件库对比（已完成使命，参考保留）
└── node_modules/
```

**完成度**：
- ✅ 应用骨架（工具栏/10 Tab/状态栏）
- ✅ design tokens 初稿（tokens.css）
- ✅ config 面板纯 UI（覆盖：Master-Detail、9 子 Tab、内联编辑表格、嵌套对话框、防抖保存、日期、开关、下拉）
- ⬜ analysis 面板（参数+图表区标准结构，覆盖 QComboBox/QCheckBox 密集参数、run loading、进度）
- ⬜ plan_search（模式切换 + 结果页）
- ⬜ comparison（富文本矩阵 + 图表色板）
- ⬜ UI 规范文件定稿（本文档 + 对照表 → 汇总为 UI设计规范.md）

**注意**：演示页是纯 UI + 假数据，不含 Python 逻辑（阶段 1b 再接）。

---

## 7. 交付物要求

设计 Agent 需交付：

1. **UI 设计规范文件**（`docs/00-meta/UI设计体系/UI设计规范.md`）：
   - design tokens 表（颜色/字体/间距/圆角/阴影）与语义说明
   - 组件规范（Element Plus 使用约定、变体、状态）
   - 布局规范（面板骨架、Master-Detail、参数+图表区）
   - 图表规范（ECharts 配色/字体/tooltip/图例，需与 tokens 联动）
   - 交互规范（Tab 悬停、loading、校验、进度、对话框）
   - 10 个裁决点的最终裁决与理由
2. **design tokens 的 CSS 实现**（`src/styles/tokens.css`，前端直接消费）
3. **完成演示页面**：补齐 analysis/plan_search/comparison 面板纯 UI，覆盖全部待测组件，作为规范的可视化载体
4. **运行时验证**：每个阶段改动能通过 load_compare.py 查看，热重载生效

---

## 8. 协作边界与验收

- **设计 Agent 输出**：规范文档 + tokens + 演示页代码
- **用户验收**：逐面板查看演示页，确认 10 个裁决点，批准 UI 规范文件
- **不越界**：不改动 core/service（计算引擎）、不接 Python 逻辑（阶段 1b）、不改变技术选型
- **回归锚点**：core 约 800 个测试不动；行为等价要求（同配置同种子模拟结果一致）是最终迁移验收线

---

*本文档与 `组件对照表.md` 构成设计工作的完整输入。设计 Agent 完成后，将 UI 规范文件归档为阶段 1a 产出，进入阶段 1b 工程化。*
