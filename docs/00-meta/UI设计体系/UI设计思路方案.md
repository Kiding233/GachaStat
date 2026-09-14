# GachaStat 新 UI 设计思路方案（P74 阶段 1a）

> 阅读范围：`tools/poc_webview/ui_compare/` 演示代码、`UI设计交接文档.md`、`组件对照表.md`、现有 Qt 面板实现（`main_window.py` / `analysis_panel.py` / `comparison_analysis_panel.py` / `plan_search_panel.py` 等）。
> 目标：在现有 UI 功能不变的前提下，用 **pywebview + Vue3 + Element Plus + ECharts** 重新设计一套统一、现代、信息密集的桌面 UI。

---

## 1. 目标与边界

- **目标**：把现有 Qt 10 个主 Tab 的功能完整迁移到 Web 前端，形成一致的设计规范与可交互演示页。
- **边界**：
  - 不改动 `core/` / `service/` / CLI；前端只做表现层。
  - 继续沿用 `ChartSpec` 作为前后端数据契约，后端零改动。
  - 技术栈已锁定：pywebview（WebView2）+ Vue 3 + Element Plus + ECharts + Vite。

---

## 2. 整体视觉方向

- **蓝色系主调 + 黑白灰为辅**：以蓝色系（primary `#1976d2` 及其浅色阶）作为品牌/操作/强调色；背景、卡片、文字仍以黑白灰分层，避免过度饱和。
- **结构感由色块层次 + 轻阴影承担**：不再使用硬黑框（已回退），用背景灰、卡片白、浅阴影区分区域；蓝色用于激活态、主按钮、图表主系列。
- **无内容切换动画**：Tab 切换反馈体现在 Tab 行悬停变灰 + 激活态蓝色下划线；避免淡入上滑的「AI 味」。
- **中文界面**：默认字体 `Microsoft YaHei / PingFang SC`；字号以 12–14px 为主，避免 Qt 时代 11px 的妥协。
- **信息密度优先**：统计工具定位，保留表格、参数表单、图表并排的密集布局。

## 2.1 关于布局与交互逻辑的裁决

**直接结论：原有 Qt 的界面布局和交互逻辑基本是最合理的选项，Web 版应在其基础上做「现代化翻译」，而不是重新发明。**

理由：

1. **10 个主 Tab 与任务流一致**：配置 → 批量模拟 → 数据管理 → 各类分析 → 比较，符合用户实际工作顺序。
2. **「左参数 + 右结果」是统计工具的标准范式**：分析、方案搜索、脆弱性、最差影响等面板都适用，学习成本低。
3. **配置页 Master-Detail 适合管理多 Banner / 多 Pool**：左侧列表导航、右侧详情编辑，是处理复杂列表配置的最高效模式。
4. **全局状态栏 + 顶部菜单是桌面应用约定**：状态栏统一反馈运行状态，顶部菜单承载文件/工具/帮助，迁移到 Web 后保留同构结构即可。

需要改进的点（不是推翻布局）：

- 用 Element Plus 组件统一视觉和交互语言（card / tabs / form / table / dialog）。
- 把 Qt 的 `QSplitter` 改为固定比例的响应式左栏（320–420px）+ 右栏弹性；若需要拖拽分割，可引入第三方 splitter。
- 状态信息集中到全局状态栏，减少面板内重复的 QLabel。
- 运行按钮、进度条、校验反馈等交互按 Web 习惯统一。

---

## 3. Design Tokens 建议

在现有 `tokens.css` 基础上做一轮收敛，把语义更明确化。

| Token | 值 | 语义 |
|---|---|---|
| `--el-color-primary` | `#1976d2` | 主操作按钮 / 链接 / 激活态指示线 |
| `--el-color-success` | `#2e7d32` | 成功 / 达标 / p<0.05 显著 |
| `--el-color-success-light` | `#e8f5e9` | 显著性背景 |
| `--el-color-danger` | `#c62828` | 危险 / 停止 / 劣势 / 校验失败 |
| `--el-color-warning` | `#f5a623` | 警告 / 提示 |
| `--el-color-info` | `#6b7280` | 次级 / 说明文字 |
| `--gsc-bg` | `#eef1f5` | 应用背景 |
| `--gsc-bg-panel` | `#ffffff` | 卡片 / 面板背景 |
| `--gsc-bg-result` | `#f5f6f8` | 结果区 / 只读区背景 |
| `--gsc-bg-header` | `#f7f8fa` | 表头 / 分组标题背景 |
| `--gsc-border` | `#d5dae2` | 分割线 / 轻边框 |
| `--gsc-shadow` | `0 1px 4px rgba(0,0,0,0.05)` | 卡片轻阴影 |
| `--gsc-text-primary` | `#1f2329` | 主文字 |
| `--gsc-text-muted` | `#6b7280` | 次级文字 |
| `--gsc-text-faint` | `#9aa5b1` | 弱提示 / placeholder |
| `--gsc-brand-blue` | `#1976d2` | 品牌主蓝（按钮 / 激活态 / 关键强调） |
| `--gsc-brand-blue-light` | `#e3f2fd` | 蓝色浅色阶（hover 背景 / 选中背景） |
| `--gsc-brand-blue-dark` | `#125ea8` | 蓝色深色阶（激活 / 按下） |
| `--gsc-chart-primary` | `#2196f3` | 图表主系列（单数据集默认色） |
| `--gsc-chart-palette` | 10 色序列 | 多数据集对比，基于 Tableau10 略微降饱和 |
| `--gsc-font-main` | `Microsoft YaHei, PingFang SC, sans-serif` | 中文主字体 |
| `--gsc-font-mono` | `Consolas, Courier New, monospace` | 日志 / JSON |
| `--gsc-radius` | `6px` | 通用圆角 |
| `--gsc-space` | `12px` | 标准间距 |
| `--gsc-space-sm` | `8px` | 紧凑间距 |

---

## 4. 十大裁决点建议

| # | 裁决点 | 建议方案 | 理由 |
|---|---|---|---|
| 1 | 运行按钮主色 | 统一用 **蓝色 primary `#1976d2`** | Qt 三套颜色混用（绿/蓝/无样式）造成认知混乱；蓝色稳定、与 Element Plus 默认主题一致 |
| 2 | 可编辑表格 | **el-table 默认只读 + 需编辑列用 scoped slot 内联控件** | 覆盖 config 概率 / 稀有度 / Featured / 资源串等场景；保持表格整洁 |
| 3 | 表格排序 | **所有展示表默认开启 `sortable`** | Qt 时代无排序是能力缺失，Web 端可顺手增强 |
| 4 | 进度显示 | **运行中显示 `el-progress` + 状态文案；完成后保留 3s 摘要，再折叠为轻量提示** | 避免常驻空进度条；plan_search 的 (done,total) 用进度条 + 百分比统一 |
| 5 | 选择交互 | **Master 列表用 `el-table` 单选高亮；普通枚举用 `el-select`；长列表开启 `filterable` + 虚拟滚动** | 区分「导航型选择」与「参数型选择」 |
| 6 | 时间数据模型 | **统一为浮点天 `el-input-number`**；唯一日期入口用 `el-date-picker` 再转换为天 | 与后端时间窗口（秒/天）保持一致，减少混合模型 |
| 7 | 校验时机 | **即时校验（`el-form rules`）为主；导出/保存前再做一次全局校验** | 前移 Qt 的后置校验，降低提交时批量报错 |
| 8 | 按钮反馈 | **统一 `:loading`，不突变按钮文字；危险操作二次确认** | Qt comparison 面板文字突变体验差 |
| 9 | 状态展示 | **统一全局状态栏；面板内只保留关键结果摘要，不重复放 QLabel 状态** | 避免两套状态体系互相覆盖 |
| 10 | 图表色板 | **全局 10 色序列（基于 Tableau10 降饱和）；单数据集用主蓝 `#2196f3`** | comparison 多数据集与全局规范统一 |

---

## 5. 面板级设计要点

### 5.1 配置面板（Config）

- 沿用 **9 个子 Tab**：卡牌定义 / 资源管理 / 卡池管理 / 保底机制 / 累抽奖励 / 抽卡策略 / 目标卡 / 权重配置 / 满突溢出。
- **卡池管理**：左侧 Master-Detail
  - 左：`el-card` 内 `el-table`（勾选启用 + 名称 + 筛选），行高亮驱动右侧详情。
  - 右：Banner 详情表单（`el-form` 双列）+ 池子 / 生命周期子 Tab。
  - 池子表格：ID 只读，概率 / 稀有度 / Featured / 资源串内联编辑。
- **复杂对话框**：
  - 编辑分布：表格内联概率，`computed` 实时合计，超 100% 标红，确定前校验。
  - 批量创建：模板选择 + 数量，预览后一键生成。
- **自动保存**：前端 `v-model` 即时响应，`watch` + `debounce(500ms)` 写回 Python `ConfigStore`。

### 5.2 批量模拟（Batch）

- 布局：**左侧参数卡片（320px）+ 右侧结果区**。
- 参数：模拟次数、并行进程、随机种子、停止条件、策略参数（`param_renderer` 动态表单）。
- 动作栏：「开始模拟」primary + 「停止」danger + `el-progress` + 状态文案。
- 结果区：关键指标卡片（均值/中位/成功率）+ ECharts Tab（分布 / CDF / 箱线等）。

### 5.3 数据管理（Data Manager）

- 左侧数据集列表（名称 / 策略 / 模拟次数 / 创建时间），支持多选。
- 操作：加载当前 / 删除 / 导出 / 跳转比较分析。
- 选中后右侧显示指纹摘要（config_hash、目标卡、初始资源等）。

### 5.4 统计分析（Analysis）

- 左侧参数卡：GDR 指标、目标卡筛选、分箱方式、阈值等。
- 右侧结果区：
  - 顶部指标卡片。
  - ECharts 图表区（Tab 切换：分布 / CDF / 热力图 / 山脊线等）。
  - 下方可展开明细表。

### 5.5 过程分析（Process）

- 左侧：事件类型多选（`el-checkbox-group`）、池子选择、目标卡选择。
- 右侧：事件频次表 + 交叉矩阵 + 桑基/热力图 ECharts。

### 5.6 方案搜索（Plan Search）

- 左侧参数区：
  - 搜索模式：`el-radio-group`（最少资源 / 最多目标卡 / Pareto）。
  - 起始状态：起始池 `el-select`、基准资源 `el-select` + `el-input`、保底水位表格。
  - 优先级配置：目标卡加入/删除顺序表。
  - 搜索参数：GDR 指标、阈值、成功率、模拟次数、并行进程、二分搜索参数。
  - 动作栏：开始搜索 / 停止 + 进度。
- 右侧：快照导航（`<` / 下拉 / `>` / `×`）+ 结果栈（`v-show` 切换三种结果页）。
  - 最少资源：摘要 + 二分步骤表 + 散点图。
  - 最多目标卡：步骤表 + 成功率折线图。
  - Pareto：解空间表 + 资源-目标散点图。

### 5.7 脆弱性分析 / 最差影响（Retreat / Worst Impact）

- 均使用左参右图结构。
- 脆弱性：池子列表 + 参数 + 结果表 + 区间图。
- 最差影响：指标选择 + 表格 + 敏感性条形图。

### 5.8 比较分析（Comparison）

- 顶部控制栏：GDR 指标、阈值、检验方法、校正方法、「运行分析」按钮、loading 文案。
- 内容区纵向分区：
  - L1 探索性分析：描述统计表 + PMF/ECDF 图。
  - L2 随机占优：方向提示 + v1 回退警示 + 分类矩阵 + FSD/SSD/TSD p 值矩阵 + 积分 CDF 图。
  - L3 假设检验：p 值矩阵表。
  - L4 帕累托前沿：X/Y 轴选择 + 散点图。

### 5.9 其他

- **插件管理**：独立对话框，表格展示插件名 / 路径 / 状态，启用/禁用/重新扫描。
- **关于**：`el-dialog` 内渲染富文本 / Markdown 文档。
- **敏感度分析**：当前占位，预留单参数变化 + GDR 折线图布局。

---

## 6. 图表规范（ECharts）

- **配色**：消费 `--gsc-chart-palette`；单系列用 `--gsc-chart-primary`；显著/达标用 `--el-color-success`；危险用 `--el-color-danger`。
- **工具栏**：每个图表默认启用 `toolbox`（保存图片、数据缩放、还原）。
- **缩放**：需要时开启 `dataZoom`（inside + slider）。
- **Tooltip**：统一中文格式化，保留 3–4 位小数。
- **Legend**：顶部水平排列，避免遮挡图表。
- **字体**：图表内字体继承 `--gsc-font-main`，保证中文清晰。
- **空态**：用 `el-empty` 或图表占位提示，替代 Qt 的空白面板。

---

## 7. 交互规范

- **Tab 切换**：鼠标悬停整行背景变灰，激活项显示 primary 色下划线；无内容动画。
- **按钮状态**：运行中统一使用 `el-button :loading`；停止按钮 danger。
- **表单校验**：
  - 即时校验：`el-form :rules`。
  - 全局校验：导出 / 保存前调用 Python 校验，失败时 `ElMessageBox` 集中展示错误列表。
- **进度与状态**：
  - 运行中：全局状态栏显示当前步骤；面板内进度条显示百分比。
  - 完成：状态栏显示结果摘要；进度条短暂保留后隐藏。
- **对话框**：
  - 底部 footer 统一「取消 / 确定」。
  - 确定前校验，失败不关闭。
- **快捷键**：保留 `Ctrl+O` 导入、`Ctrl+S` 导出、`Ctrl+Q` 退出；开发期保留 `Ctrl+R` 热重启入口。

---

## 8. 实现路径建议

阶段 1a（当前）：
1. 确认并固化 design tokens（本方案第 3 节）。
2. 完成 `analysis` / `plan_search` / `comparison` 三个面板的纯 UI 演示页。
3. 产出 `UI设计规范.md`：tokens / 组件 / 布局 / 图表 / 交互 / 10 裁决点。
4. 通过 `load_compare.py` 运行演示页，热重载验证。

阶段 1b：
- `ChartSpec` → ECharts 前端 renderer。
- pywebview 容器替换 `ChartWebView`。
- Vite 工程化 + 大数据 HTTP 通道验证。

阶段 2：
- 按简单 / 中等 / 复杂分批迁移面板；`config_panel` 最后迁移。

阶段 3：
- 移除 PyQt6 / WebEngine / plotly 依赖；重写 PyInstaller spec；迁移 GUI 测试。

---

## 9. 下一步

以上 10 个裁决点和视觉 tokens 是我基于现有 Qt 实现、交接文档和演示页现状提出的推荐方案。

请在下列选项中告诉我你的倾向：
1. **直接按此方案进入阶段 1a 实现**：补齐 analysis / plan_search / comparison 面板 + 完善 tokens + 输出规范文档。
2. **先调整部分裁决点**：指出需要修改的条目，我再据此生成最终规范。
3. **只做规范文档，暂缓演示页**：先固化 `UI设计规范.md`，后续再补代码。
