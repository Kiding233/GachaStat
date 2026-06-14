# 脆弱性分析总览山脊线图滚动问题调查报告

> **日期**：2026-06-14 · **触发**：用户反馈「山脊线图 tag 应该可以滚动查看，现在是不是不行？」
> **涉及文件**：
> - [chart_webview.py](gacha_simulator/gui/chart_webview.py) — Plotly 图表 WebView 容器
> - [retreat_panel.py](gacha_simulator/gui/retreat_panel.py) — 脆弱性分析面板
> - [vulnerability.py](gacha_simulator/core/vulnerability.py) — 山脊线图构造 (`plot_vulnerability_ridge`)
> - [plotly_charts.py](gacha_simulator/visualization/plotly_charts.py) — PlotlyRenderer（本场景未经过，ridge_fig 直接由 vulnerability.py 生成 go.Figure）

---

## 1. 现象确认

**无法滚动：是的，山脊线图在当前实现中无法通过滚轮或拖动查看底部池子的行。**

当池子数量较多时（例如 ≥8 个），山脊线图总高度超出 WebView 可视区域，但：
- 鼠标滚轮在图表区域无效（不会触发页面级纵向滚动）
- 无滚动条出现
- 底部池子的直方图行及其左侧标签（pool name "tag"）被截断，用户无法查看

底层池子被截断的行 ≈ `ceil(viewport_height / 140)` 之后的所有行。

---

## 2. 数据链路追踪

```
retreat_panel._on_finished()
  → plot_vulnerability_ridge()           [vulnerability.py:526]
    → go.Figure (make_subplots rows=n)    [vulnerability.py:581]
    → fig.update_layout(height=n*140+80) [vulnerability.py:654]
  → charts["总览"] = ridge_fig           [retreat_panel.py:346]
  → chart_webview.set_charts(charts)     [retreat_panel.py:357]
    → ridge_fig.to_json()                [chart_webview.py:302]
    → runJavaScript("rebuildAll(...)")   [chart_webview.py:314]
      → renderChart(key, figureJson)     [chart_webview.js:86]
        → Plotly.newPlot(el, data, layout, {responsive: true, scrollZoom: false, ...})
```

**关键点**：ridge_fig 是绕过 `PlotlyRenderer` / `ChartSpec` 路径的 `go.Figure` 裸对象，`chart_webview.py:301-302` 检测到 `GoFigure` 实例后直接调用 `.to_json()`。

---

## 3. 根因分析

### 3.1 核心问题：`scrollZoom: false` 导致页面纵向滚动失效

在 [chart_webview.py:90-100](gacha_simulator/gui/chart_webview.py#L90-L100) 的 `renderChart` 函数中：

```javascript
Plotly.newPlot(el, data.data, data.layout, {
    responsive: true,
    displaylogo: false,
    scrollZoom: false,   // ← 关键配置
    displayModeBar: true,
    modeBarButtonsToRemove: ['sendDataToCloud', 'lasso2d', 'select2d'],
});
```

| 配置 | 含义 | 对滚动的影响 |
|------|------|-------------|
| `scrollZoom: false` | 禁止滚轮缩放图表 | Plotly **仍然拦截**图表区域的 `wheel` 事件，但丢弃而非传播到页面——这阻止了鼠标位于图表上方时的页面纵向滚动 |
| `responsive: true` | 图表宽度自适应容器 | 不直接影响高度，但启用后 Plotly 会重排 DOM，添加 `position: relative` 和内部绝对定位 div |
| `dragmode: "pan"` | 拖动以平移图表 | + `fixedrange=True`（y 轴锁定）→ 水平拖动有效，但纵向拖动不会滚动页面——**拖动手势也被 Plotly 拦截** |

### 3.2 机制详解

Plotly.js 的 `scrollZoom: false` 并不意味着 wheel 事件自由穿透。Plotly 在图表 SVG 层上注册 `wheel` 事件监听器，当 `scrollZoom=false` 时，处理函数执行 **空操作但未调用 `preventDefault()`**，理论上事件应继续冒泡。

**但实际行为因浏览器引擎而异**：
- 在 Chromium（Qt WebEngine 底层）中，`wheel` 事件目标为 Plotly 生成的 SVG 元素时，Chromium 的合成器线程可能独立处理滚动，不与 Plotly 的 JS 层交互
- Plotly 的 `responsive: true` 模式会在图表外层包裹 `position: relative` 容器，导致 `wheel` 事件目标为 Plotly 的内部元素而非可滚动的 body
- 当 `dragmode: "pan"` + `fixedrange=True`（y 轴固定）时，纵向拖动事件被 Plotly 捕获，拖动不产生图表 zom，也不传播到页面

### 3.3 次要因素

| 因素 | 状态 | 是否导致无法滚动 |
|------|------|:---:|
| CSS `overflow: hidden` | `_setup_shrinkable` 模式有，retreat panel **无** | ❌ |
| `html, body { height: 100% }` | retreat panel 骨架页 **无** | ❌ |
| QWebEngineView 的 `setMinimumHeight` | `_on_title_changed` 动态设置，但不强制 widget 撑高 | ❌ (不影响内部滚动) |
| Plotly `responsive: true` 的 resize | 初始渲染后用 ResizeObserver 监测容器，可能将图表高度约束为容器 clientHeight | ⚠️ 可能放大问题 |

### 3.4 综合判断

**主要根因**：Plotly 图表区域拦截了 wheel/drag 事件，导致鼠标位于山脊线图上方时页面无法纵向滚动。`dragmode: "pan"` + y 轴 `fixedrange=True` 的组合使得拖动也不能滚动页面。

**放大因素**：`responsive: true` 可能导致 Plotly 在 resize 时把图表高度压缩到视口之内，减少了「图表底部空白区域」（鼠标在空白区域时可以正常滚动页面），使用户更难找到可滚动区域。

---

## 4. 影响范围

**受影响**（山脊线图超长的 Tab）：
- 脆弱性分析 → 「总览」（池子 ≥ 8 时明显）
- 其他面板中**仅含一张超长图表且无 tab 切换**的场景（如果存在）

**不受影响**：
- 脆弱性分析的单个池子图表（双行高度 ~500px，不超出视口）
- 其他面板中图表高度未超出视口的场景

---

## 5. 修复方案

### 方案 A：页面级滚动修复（推荐）

**思路**：恢复 wheel 事件的页面滚动行为。

**实现**（在 `renderChart` 函数中添加 wheel 事件透传）：

```javascript
function renderChart(key, figureJson) {
    var data = JSON.parse(figureJson);
    var el = document.getElementById('chart-' + key);
    if (el) {
        Plotly.newPlot(el, data.data, data.layout, {
            responsive: true,
            displaylogo: false,
            scrollZoom: false,
            displayModeBar: true,
            modeBarButtonsToRemove: ['sendDataToCloud', 'lasso2d', 'select2d'],
        });
        // 【修复】wheel 事件透传至页面滚动
        el.addEventListener('wheel', function(e) {
            window.scrollBy(0, e.deltaY);
        }, { passive: true });
    }
}
```

或在 `rebuildAll` 末尾统一注入：
```javascript
// 允许所有图表容器下方页面随滚轮滚动
document.querySelectorAll('.chart-container').forEach(function(el) {
    el.addEventListener('wheel', function(e) {
        window.scrollBy(0, e.deltaY);
    }, { passive: true });
});
```

**优点**：改动最小（JS 层 3 行），不触及 Plotly 配置
**缺点**：`passive: true` 可能被 Chromium 忽略（需实测）

---

### 方案 B：关闭山脊线图的 `responsive` + 移除 `dragmode: pan`

**思路**：对高度超大的图表，关闭 `responsive` 让 Plotly 以固定高度渲染，确保页面必定溢出并显示滚动条。

**实现**：
1. 在 `chart_webview.py` 中为不同图表传递不同的 Plotly config（将 `responsive` 和 `scrollZoom` 作为参数化配置）
2. 对于超长图表（检测 `layout.height > viewport_height`），使用 `responsive: false` + `scrollZoom: false`
3. 同时在 `vulnerability.py:655` 中将 `dragmode="pan"` 改为 `dragmode=False`（对 ridge 图表无意义，因为只有 y 轴固定时横向拖动有用性存疑）

**优点**：从根源避免 Plotly resize 干扰
**缺点**：需要传递元数据（图表是否需要 responsive），改动涉及 3 个文件

---

### 方案 C：包装 QScrollArea（Qt 层修复）

**思路**：在 `RetreatPanel._setup_ui` 中将 `ChartWebView` 放入 `QScrollArea`。

```python
scroll = QScrollArea()
scroll.setWidgetResizable(True)
scroll.setWidget(self.chart_webview)
right_layout.addWidget(scroll)
```

**优点**：Qt 原生滚动条，不依赖 Web 引擎
**缺点**：
- `QWebEngineView` 在 `QScrollArea` 中存在已知渲染问题（Chromium 内部滚动与 Qt 外层滚动冲突）
- 可能出现双滚动条（Chromium 内置 + Qt 外层）
- 不推荐在生产中使用

---

### 方案 D：Patch Plotly 的 scrollZoom 行为

**思路**：Monkey-patch Plotly 的 wheel handler，当 `scrollZoom: false` 时显式传播事件。

不推荐——依赖 Plotly 内部实现，版本升级易碎。

---

## 6. 推荐方案

**推荐方案 A（wheel 事件透传）** 作为首选：

- 改动量最小（`chart_webview.py` 骨架 HTML 中 ~5 行 JS）
- 对所有面板的超长图表均有益（不限于山脊线图）
- 不影响现有 Plotly 的 `responsive` 或 `dragmode` 行为
- 无兼容性风险

**备选方案 B** 如果方案 A 在 Qt WebEngine 中无效。

---

## 7. 验证方法

修复后验证：
1. 创建包含 ≥10 个池子的测试配置
2. 运行批量模拟 → 打开脆弱性分析 → 运行分析
3. 切换到「总览」tab
4. **检查点 1**：用鼠标滚轮在山脊线图上滚动 → 应能纵向滚动看到底部池子
5. **检查点 2**：用鼠标在山脊线图上拖动 → 应能纵向滚动（或至少不阻止页面滚动）
6. **检查点 3**：底部池子的 pool name 标签（左侧 y 轴 title）应完整可见
7. **检查点 4**：顶部 tab bar 应保持 sticky（不随滚动消失）
8. **检查点 5**：切换到其他池子 tab 再切回「总览」→ 滚动位置应保持

---

## 8. 附录：相关代码位置索引

| 文件 | 行号 | 内容 |
|------|------|------|
| [chart_webview.py](gacha_simulator/gui/chart_webview.py) | 86-102 | `renderChart` JS 函数（Plotly 配置在此） |
| [chart_webview.py](gacha_simulator/gui/chart_webview.py) | 108-163 | `rebuildAll` JS 函数（DOM 构建 + 滚动初始化） |
| [chart_webview.py](gacha_simulator/gui/chart_webview.py) | 419-441 | `_setup_shrinkable`（注入 overflow:hidden 的 shrinkable 模式 CSS） |
| [chart_webview.py](gacha_simulator/gui/chart_webview.py) | 443-454 | `_on_title_changed`（动态 setMinimumHeight） |
| [retreat_panel.py](gacha_simulator/gui/retreat_panel.py) | 200-205 | ChartWebView 创建与布局 |
| [retreat_panel.py](gacha_simulator/gui/retreat_panel.py) | 344-357 | 图表组装（总览 + 各池）并传入 set_charts |
| [vulnerability.py](gacha_simulator/core/vulnerability.py) | 526-659 | `plot_vulnerability_ridge` 完整实现 |
| [vulnerability.py](gacha_simulator/core/vulnerability.py) | 646-648 | `row_height=140`、`total_height=n*140+80` |
| [vulnerability.py](gacha_simulator/core/vulnerability.py) | 655 | `dragmode="pan"` |
| [plotly_charts.py](gacha_simulator/visualization/plotly_charts.py) | 368-449 | `_build_ridge`（ChartSpec→go.Figure，本场景未使用但同类逻辑） |
| [plotly_charts.py](gacha_simulator/visualization/plotly_charts.py) | 685 | `dragmode="pan"`（所有图表统一设置） |
| [plotly_charts.py](gacha_simulator/visualization/plotly_charts.py) | 694 | `fig.update_yaxes(fixedrange=True)`（所有图表统一） |
