// ══════════════════════════════════════════════════════════════════
// ChartSpec → ECharts option 转换器（绘图迁移核心）
//
// 后端分析函数产出 ChartSpec（gacha_simulator/visualization/chart_spec.py），
// 经 js_api 序列化为纯 JSON（spec_to_dict）推到前端，此模块转为 ECharts option。
//
// 支持全部 ChartType：histogram / cdf / ridge / boxplot / scatter / bar /
// heatmap / waterfall_3d / subplot_grid / table
// + annotations（vline/hline 参考线）+ shaded_regions（MarkArea 区间）
// ══════════════════════════════════════════════════════════════════

// ── 通用工具（与 spec_renderers.js 保持一致，避免依赖后端 numpy）──

export function binCounts(samples, nbins) {
  const lo = Math.min(...samples)
  const hi = Math.max(...samples)
  if (hi === lo) return { centers: [lo], counts: [samples.length] }
  const w = (hi - lo) / nbins
  const counts = new Array(nbins).fill(0)
  const centers = []
  for (let i = 0; i < nbins; i++) centers.push(lo + (i + 0.5) * w)
  for (const v of samples) {
    let idx = Math.floor((v - lo) / w)
    if (idx >= nbins) idx = nbins - 1
    counts[idx]++
  }
  return { centers, counts }
}

export function cdfPoints(samples) {
  const sorted = [...samples].sort((a, b) => a - b)
  const n = sorted.length
  return sorted.map((x, i) => [x, (i + 1) / n])
}

function sampleMean(samples) {
  return samples.reduce((a, b) => a + b, 0) / samples.length
}

function quantile(sorted, q) {
  if (!sorted.length) return 0
  const idx = Math.floor(q * (sorted.length - 1))
  return sorted[idx]
}

// Plotly/matplotlib 色阶名 → ECharts 颜色数组（ChartSpec.colorscale 用 Plotly 名）
const PLOTLY_SCALES = {
  Viridis: ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725'],
  YlOrRd: ['#ffffb2', '#fed976', '#feb24c', '#fd8d3c', '#fc4e2a', '#e31a1c', '#b10026'],
  RdBu_r: ['#67001f', '#b2182b', '#d6604d', '#f4a582', '#fddbc7', '#f7f7f7', '#d1e5f0', '#92c5de', '#4393c3', '#2166ac', '#053061'],
  Blues: ['#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b'],
  RdYlGn: ['#d73027', '#f46d43', '#fdae61', '#fee08b', '#ffffbf', '#d9ef8b', '#a6d96a', '#66bd63', '#1a9850'],
}
function scaleColors(name) {
  return PLOTLY_SCALES[name] || PLOTLY_SCALES.Viridis
}

// ── 通用装饰：toolbox / dataZoom / 参考线 / 区间 ──
// 滚轮调和（用户选定）：dataZoom.inside 关闭自身滚轮/拖动捕获，
// 缩放由 ResultChart 的 Ctrl+滚轮监听 dispatchAction 驱动，普通滚轮放行给页面。
function decorate(opt, { xValue = false } = {}) {
  opt.toolbox = {
    right: 8, top: 2, itemSize: 13,
    feature: {
      dataZoom: { yAxisIndex: 'none', title: { zoom: '区域缩放', back: '还原缩放' } },
      restore: { title: '还原' },
      saveAsImage: { title: '保存图片' },
    },
  }
  // 轴型：value（数值）轴才能区域缩放；category 轴 dataZoom.inside 无意义
  if (xValue) {
    opt.dataZoom = [{ type: 'inside', zoomOnMouseWheel: false, moveOnMouseWheel: false, moveOnMouseMove: false, start: 0, end: 100 }]
  }
  return opt
}

// 参考线（ChartAnnotation：vline / hline）→ markLine.data
// axisKey='xAxis' 取 vline，axisKey='yAxis' 取 hline（PAVA α 参考线等）
function markLines(annotations, axisKey) {
  if (!annotations || !annotations.length) return undefined
  const data = annotations
    .filter((a) => a.type === (axisKey === 'xAxis' ? 'vline' : 'hline'))
    .map((a) => {
      const item = { lineStyle: { color: a.color || '#ff4444', type: a.dash || 'dash', width: 1 } }
      item[axisKey === 'xAxis' ? 'xAxis' : 'yAxis'] = a.value
      if (a.text) item.label = { formatter: a.text, color: a.color || '#ff4444', fontSize: 11 }
      return item
    })
  return data.length ? data : undefined
}

// 区间（ShadedRegion）→ markArea 完整对象（ECharts 要求 { data: [...] }，裸数组不渲染）
// 含 label 时在起点项上挂文字标注（对齐旧 UI vrect annotation_text「脆弱区间 [x, y]」）
function markAreas(regions) {
  if (!regions || !regions.length) return undefined
  const data = regions.map((r) => {
    const first = { xAxis: r.lower, itemStyle: { color: r.color || 'rgba(200,50,50,0.12)' } }
    if (r.label) first.label = { formatter: r.label, fontSize: 10, color: '#666', position: 'insideTopLeft' }
    return [first, { xAxis: r.upper }]
  })
  return { silent: true, data }
}

// 通用 markLine + markArea 挂到某 series 上
function addMarks(series, annotations, regions) {
  const ml = annotations ? markLines(annotations, 'xAxis') : undefined
  const ma = regions ? markAreas(regions) : undefined
  if (ml) series.markLine = { silent: true, symbol: 'none', data: ml }
  if (ma) series.markArea = ma
  return series
}

// ── 主转换 ──

export function specToECharts(spec) {
  if (!spec || !spec.chart_type) return {}
  const t = spec.chart_type
  const d = spec.data || {}
  const title = { text: spec.title || t, left: 'center', textStyle: { fontSize: 12 } }
  const grid = { top: 30, bottom: 28, left: 60, right: 30 }
  const xlab = spec.xlabel || ''
  const ylab = spec.ylabel || ''

  switch (t) {
    case 'bar': {
      // orientation='h' 水平柱（每池分析）：y 轴分类、x 轴数值（对齐旧 PlotlyRenderer）
      if (d.orientation === 'h') {
        const opt = {
          title,
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          grid,
          xAxis: { type: 'value', name: xlab },
          yAxis: { type: 'category', data: d.labels || [], name: ylab },
          series: [{ type: 'bar', data: d.values || [], barWidth: '55%', itemStyle: { color: '#5470c6' } }],
        }
        return decorate(opt)
      }
      const opt = {
        title,
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid,
        xAxis: { type: 'category', data: d.labels || [], name: xlab, nameLocation: 'middle', nameGap: 22 },
        yAxis: { type: 'value', name: ylab },
        series: [{ type: 'bar', data: d.values || [], barWidth: '45%', itemStyle: { color: '#5470c6' } }],
      }
      return decorate(opt)
    }
    case 'histogram': {
      // GDR 直方图：优先用后端 compute_bins 的 bin_edges（离散整数格点 / 步长对齐 / 连续 FD），
      // 无 bin_edges 时回退前端等距分箱（nbins）。柱宽必须按数据坐标绘制——
      // ECharts 的 barWidth 单位是「像素」，把数据单位（如 320 资源）当 barWidth 会画出巨块。
      // 因此用 custom 系列 renderItem 按 bin_edges 逐根画矩形（对齐旧 Plotly go.Histogram xbins）。
      const samples = d.samples || []
      const hints = spec.layout_hints || {}
      let edges = hints.bin_edges
      if (!Array.isArray(edges) || edges.length < 2) {
        const nb = hints.nbins || 30
        const lo = samples.length ? Math.min(...samples) : 0
        const hi = samples.length ? Math.max(...samples) : 1
        if (hi === lo) { edges = [lo - 0.5, lo + 0.5] }
        else { edges = Array.from({ length: nb + 1 }, (_, j) => lo + (hi - lo) * j / nb) }
      }
      const nb = edges.length - 1
      const counts = new Array(nb).fill(0)
      for (const v of samples) {
        for (let j = 0; j < nb; j++) {
          if (v >= edges[j] && (j === nb - 1 ? v <= edges[j + 1] : v < edges[j + 1])) { counts[j]++; break }
        }
      }
      // density=True → 概率密度：每 bin 除以（n × bin 宽），变宽分箱各自归一（对齐 histnorm='probability density'）
      if (d.density && samples.length) {
        for (let j = 0; j < nb; j++) {
          const w = edges[j + 1] - edges[j]
          if (w > 0) counts[j] = counts[j] / (samples.length * w)
        }
      }
      const ml = []
      if (d.mean_line) ml.push({ xAxis: +sampleMean(samples).toFixed(4), label: { formatter: '均值 ' + sampleMean(samples).toFixed(2) } })
      if (d.quantile_lines) {
        const sorted = [...samples].sort((a, b) => a - b)
        for (const q of d.quantile_lines) ml.push({ xAxis: +quantile(sorted, q).toFixed(4), label: { formatter: 'P' + Math.round(q * 100) } })
      }
      // overlays：叠加分布（同一 x 轴，按相同 bin_edges 对齐）
      const overlays = (d.overlays || []).map((ov) => {
        const o = ov.samples || []
        const oc = new Array(nb).fill(0)
        for (const v of o) {
          for (let j = 0; j < nb; j++) {
            if (v >= edges[j] && (j === nb - 1 ? v <= edges[j + 1] : v < edges[j + 1])) { oc[j]++; break }
          }
        }
        if (d.density && o.length) {
          for (let j = 0; j < nb; j++) {
            const w = edges[j + 1] - edges[j]
            if (w > 0) oc[j] = oc[j] / (o.length * w)
          }
        }
        return {
          type: 'line', smooth: true, symbol: 'none',
          data: edges.slice(0, -1).map((c, j) => [(edges[j] + edges[j + 1]) / 2, oc[j]]),
          lineStyle: { color: ov.color || '#ff4444', width: 1.5 },
          itemStyle: { color: ov.color || '#ff4444' },
          areaStyle: { color: ov.color || '#ff4444', opacity: 0.25 },
          name: ov.label || '',
        }
      })
      const histSeries = {
        type: 'custom',
        // data 用 [bin左边界, count] 对：ECharts 据此推导 value 轴范围（=bin_edges 范围），
        // renderItem 再按数据坐标画矩形。裸数字数组会让轴退化为索引范围，柱全部偏出画布。
        renderItem(params, api) {
          const j = params.dataIndex
          const x = api.value(0)          // bin 左边界（数据值）
          const y = api.value(1)          // 该 bin 计数
          const x1 = api.coord([x, 0])
          const x2 = api.coord([edges[j + 1], 0])
          const yBase = api.coord([x, 0])[1]
          const yTop = api.coord([x, y])[1]
          const w = Math.abs(x2[0] - x1[0])
          return {
            type: 'rect',
            shape: {
              x: Math.min(x1[0], x2[0]), y: Math.min(yBase, yTop),
              width: Math.max(w, 1), height: Math.max(0, Math.abs(yBase - yTop)),
            },
            style: api.style({ fill: '#5470c6' }),
          }
        },
        data: edges.slice(0, -1).map((e, j) => [e, counts[j]]),
        markLine: ml.length ? { silent: true, symbol: 'none', lineStyle: { color: '#ff4444', type: 'dashed', width: 1 }, label: { color: '#ff4444', fontSize: 11 }, data: ml } : undefined,
        markArea: markAreas(spec.shaded_regions),
      }
      const opt = {
        title,
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid,
        legend: overlays.length ? { top: 0, right: 80, textStyle: { fontSize: 11 } } : undefined,
        xAxis: { type: 'value', name: xlab, nameLocation: 'middle', nameGap: 22 },
        yAxis: { type: 'value', name: ylab },
        series: [histSeries, ...overlays],
      }
      return decorate(opt, { xValue: true })
    }
    case 'cdf': {
      const samples = d.samples || []
      const opt = {
        title,
        tooltip: { trigger: 'axis' },
        grid,
        xAxis: { type: 'value', name: xlab, nameLocation: 'middle', nameGap: 22 },
        yAxis: { type: 'value', name: ylab, min: 0, max: 1.02 },
        series: [addMarks({
          type: 'line',
          data: cdfPoints(samples).map((p) => [p[0], +p[1].toFixed(4)]),
          showSymbol: false,
          lineStyle: { color: '#5470c6', width: 2 },
          areaStyle: { color: 'rgba(84,112,198,0.08)' },
        }, spec.annotations, spec.shaded_regions)],
      }
      return decorate(opt, { xValue: true })
    }
    case 'ridge': {
      // 山脊线图（对齐原 UI Plotly）：单子图定高，全图高度随堆叠数动态增长
      //（很多个固定高度的分布图叠在一起，分布间略有重叠）。
      // grid 用像素（非百分比）→ 容器高度 = top + rows × rowHeight，由 ResultChart 据 __gscRidge 设置。
      const keys = Object.keys(d.series || {})
      const n = keys.length
      if (!n) return {}
      const hints = spec.layout_hints || {}
      // 共享分箱边界：优先后端 global_bin_edges（脆弱性各池同一 bin 宽度——与原 UI 一致），
      // 否则全部序列合并后等距分箱（对齐旧 plotly ridge nbins 默认 50）。
      let edges = hints.bin_edges
      const allSamples = keys.flatMap((k) => d.series[k] || [])
      if (!Array.isArray(edges) || edges.length < 2) {
        const nb = hints.nbins || 50
        const lo = allSamples.length ? Math.min(...allSamples) : 0
        const hi = allSamples.length ? Math.max(...allSamples) : 1
        if (hi === lo) { edges = [lo - 0.5, lo + 0.5] }
        else { edges = Array.from({ length: nb + 1 }, (_, j) => lo + (hi - lo) * j / nb) }
      }
      const nbins = edges.length - 1
      const ROW_H = 140       // 每行像素高度（对齐旧 plotly ridge row_height=140）
      const TOP = 40          // 顶部预留（标题）
      // 每序列按共享边界计数；全局 y 上限 = 各序列最大计数 × 1.18（对齐旧 plotly ridge global_ymax）
      const countAll = {}
      let globalMax = 1
      for (const k of keys) {
        const c = new Array(nbins).fill(0)
        for (const v of d.series[k] || []) {
          for (let j = 0; j < nbins; j++) {
            if (v >= edges[j] && (j === nbins - 1 ? v <= edges[j + 1] : v < edges[j + 1])) { c[j]++; break }
          }
        }
        countAll[k] = c
        const m = Math.max(...c)
        if (m > globalMax) globalMax = m
      }
      const globalYmax = globalMax * 1.18
      const gridA = [], xAxis = [], yAxis = [], series = []
      keys.forEach((k, i) => {
        const top = TOP + i * ROW_H
        gridA.push({ left: 120, right: 30, top, height: ROW_H - 4 })  // 行高≈ROW_H，轻微重叠
        const isLast = i === n - 1
        xAxis.push({
          type: 'value', gridIndex: i,
          axisLabel: { show: isLast, fontSize: 10 },
          axisLine: { show: isLast },
          axisTick: { show: isLast },
          splitLine: { show: false },
          name: isLast ? xlab : '',
          nameLocation: 'middle', nameGap: 22,
        })
        yAxis.push({
          type: 'value', gridIndex: i,
          name: (d.labels && d.labels[k]) || k,
          nameLocation: 'middle',
          nameGap: 90,
          show: true,
          min: 0,
          max: globalYmax,
          axisLine: { show: false },
          axisTick: { show: false },
          // 对齐旧 Plotly ridge：y 轴显示刻度（每行独立标数），splitLine 关闭
          axisLabel: { show: true, fontSize: 9, color: '#888' },
          splitLine: { show: false },
        })
        // 数据坐标柱宽（与 histogram 同思路：custom renderItem 按共享边界画矩形）。
        // data 用 [bin左边界, count] 对，让 value 轴推导为 bin_edges 范围（裸数字轴会退化）。
        const barData = countAll[k]
        const barColor = (d.colors && d.colors[k]) || 'hsl(' + ((i * 55 + 260) % 360) + ',70%,50%)'
        // markLine：均值红虚线 + 不抽卡基线绿点线（对齐旧 plot_vulnerability_ridge）
        const ml = []
        if (d.means && d.means[k] != null) {
          ml.push({ xAxis: +Number(d.means[k]).toFixed(2), lineStyle: { color: 'rgba(220,50,50,0.55)', type: 'dashed', width: 1 } })
        }
        if (d.baselines && d.baselines[k] != null) {
          ml.push({ xAxis: +Number(d.baselines[k]).toFixed(2), lineStyle: { color: 'rgba(0,128,0,0.7)', type: 'dotted', width: 1.4 } })
        }
        // markArea：脆弱区间带（浅红 rgba(231,76,60,0.08)）
        const ma = (d.vuln_regions && d.vuln_regions[k]) ? {
          silent: true,
          data: [
            [{ xAxis: d.vuln_regions[k][0], itemStyle: { color: 'rgba(231,76,60,0.08)' } }, { xAxis: d.vuln_regions[k][1] }],
          ],
        } : undefined
        series.push({
          type: 'custom', xAxisIndex: i, yAxisIndex: i,
          renderItem(params, api) {
            const j = params.dataIndex
            const x = api.value(0)          // bin 左边界
            const y = api.value(1)          // 计数
            const x1 = api.coord([x, 0])
            const x2 = api.coord([edges[j + 1], 0])
            const yBase = api.coord([x, 0])[1]
            const yTop = api.coord([x, y])[1]
            const w = Math.abs(x2[0] - x1[0])
            return {
              type: 'rect',
              shape: {
                x: Math.min(x1[0], x2[0]), y: Math.min(yBase, yTop),
                width: Math.max(w, 1), height: Math.max(0, Math.abs(yBase - yTop)),
              },
              style: api.style({ fill: barColor, opacity: 0.7 }),
            }
          },
          data: barData.map((c, j) => [edges[j], c]),
          name: (d.labels && d.labels[k]) || k,
          markLine: ml.length ? { silent: true, symbol: 'none', data: ml } : undefined,
          markArea: ma,
        })
      })
      const opt = {
        title,
        tooltip: { trigger: 'axis' },
        dataZoom: [{ type: 'inside', xAxisIndex: keys.map((_, i) => i), zoomOnMouseWheel: false, moveOnMouseWheel: false, moveOnMouseMove: false }],
        grid: gridA, xAxis, yAxis, series,
      }
      opt.toolbox = { right: 10, top: 0, feature: { dataZoom: { yAxisIndex: 'none' }, restore: {}, saveAsImage: {} } }
      // 标记：ResultChart 据此把容器高度设为 top + rows×rowHeight（全图动态增高）
      opt.__gscRidge = { rows: n, rowHeight: ROW_H, top: TOP }
      return opt
    }
    case 'boxplot': {
      // 水平箱线（对齐旧 _build_boxplot orientation='h'）：y 轴分类
      const keys = Object.keys(d.series || {})
      const labels = keys.map((k) => (d.labels && d.labels[k]) || k)
      const opt = {
        title,
        tooltip: { trigger: 'item' },
        grid,
        xAxis: { type: 'value', name: xlab },
        yAxis: { type: 'category', data: labels, name: ylab },
        series: [{
          type: 'boxplot',
          data: keys.map((k) => {
            const s = [...(d.series[k] || [])].sort((a, b) => a - b)
            return [s[0], quantile(s, 0.25), quantile(s, 0.5), quantile(s, 0.75), s[s.length - 1]]
          }),
          itemStyle: { color: '#5470c6', borderColor: '#2f4f8f' },
        }],
      }
      return decorate(opt)
    }
    case 'scatter': {
      // 每条轨迹：支持点大小 ∝ N_j（marker_sizes）、透明度、每点附加数据（tooltip）
      const base = (tr) => ({
        type: 'scatter',
        symbolSize: tr.marker_sizes ? (i) => tr.marker_sizes[i] : (tr.marker_size || 7),
        symbol: tr.marker_symbol || 'circle',
        itemStyle: { color: tr.marker_color || '#5470c6', opacity: tr.opacity ?? 1 },
        data: (tr.x || []).map((xi, i) => [xi, (tr.y || [])[i]]),
        ...(tr.line_width != null ? { lineStyle: { width: tr.line_width } } : {}),
        ...(tr.customdata && tr.customdata.length ? {
          tooltip: {
            formatter(params) {
              const pt = params.data || []
              const n = tr.customdata[params.dataIndex] ?? ''
              return `箱中心: ${pt[0] == null ? '' : Number(pt[0]).toFixed(0)}<br>p̂: ${pt[1] == null ? '' : Number(pt[1]).toFixed(3)}<br>N: ${n}`
            },
          },
        } : {}),
      })
      let series
      let colorOpt = {}
      if (d.traces && d.traces.length) {
        series = d.traces.map(base)
      } else if (d.color_values && d.color_values.length) {
        // 颜色映射散点（对齐旧 color_values + colorscale）：每点着色
        const pts = (d.x || []).map((xi, i) => [xi, (d.y || [])[i], d.color_values[i]])
        series = [{
          type: 'scatter', symbolSize: 10,
          data: pts,
          itemStyle: { color: '#333' },
        }]
        colorOpt = {
          visualMap: {
            min: Math.min(...d.color_values), max: Math.max(...d.color_values),
            dimension: 2, calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
            textStyle: { fontSize: 10 },
            inRange: { color: scaleColors(d.colorscale) },
          },
        }
      } else {
        series = [base({ x: d.x || [], y: d.y || [], mode: d.mode, marker_color: '#5470c6' })]
      }
      // α 阈值参考线（hline）+ 脆弱区间带（markArea）——挂到第一条轨迹上
      const hml = markLines(spec.annotations, 'yAxis')
      const ma = markAreas(spec.shaded_regions)
      if (series.length) {
        if (hml) series[0].markLine = { silent: true, symbol: 'none', data: hml }
        if (ma) series[0].markArea = ma
      }
      const opt = {
        title,
        tooltip: { trigger: 'item' },
        grid,
        xAxis: { type: 'value', name: xlab, nameLocation: 'middle', nameGap: 22 },
        yAxis: { type: 'value', name: ylab },
        ...colorOpt,
        series,
      }
      return decorate(opt, { xValue: true })
    }
    case 'heatmap': {
      const mat = d.matrix || []
      const rows = d.row_labels || mat.map((_, i) => String(i))
      const cols = d.col_labels || (mat[0] ? mat[0].map((_, j) => String(j)) : [])
      const vals = []
      mat.forEach((row, i) => row.forEach((v, j) => vals.push([j, i, v])))
      // 对齐旧 plotly_charts heatmap：x 轴置顶（xaxis_side='top'）、色阶不钳 0
      //（旧 go.Heatmap 未设 zmin/zmax，Plotly 自动映射数据范围；前端仅展示用数据范围）
      const vmMin = Math.min(...vals.map((v) => v[2]))
      const vmMax = Math.max(...vals.map((v) => v[2]))
      const opt = {
        title,
        tooltip: { position: 'top' },
        grid: { top: 30, bottom: 40, left: 60, right: 60 },
        xAxis: { type: 'category', data: cols, name: xlab, position: 'top', splitArea: { show: true } },
        yAxis: { type: 'category', data: rows, name: ylab, splitArea: { show: true } },
        visualMap: {
          min: vmMin === vmMax ? vmMin - 1 : vmMin,
          max: vmMax,
          calculable: true, orient: 'horizontal', left: 'center', bottom: 0, textStyle: { fontSize: 10 },
          inRange: { color: scaleColors(d.colorscale) },
        },
        series: [{ type: 'heatmap', data: vals, label: { show: false } }],
      }
      return decorate(opt)
    }
    case 'waterfall_3d': {
      // 3D 瀑布（ECharts 需 echarts-gl，未装时退化为二维散点）：z（概率）作为点颜色 visualMap，
      // x/y 轴名取 spec.xlabel/ylabel（修复旧实现 x/y 都取 zlabel 的轴名错误）
      const xs = d.x || []
      const ys = d.y || []
      const zs = d.z || []
      const data = xs.map((x, i) => [x, ys[i] ?? 0, zs[i] ?? 0])
      const zmin = Math.min(0, ...zs)
      const zmax = Math.max(0, ...zs)
      const opt = {
        title,
        tooltip: { trigger: 'item' },
        grid,
        xAxis: { type: 'value', name: spec.xlabel || '时间步', nameLocation: 'middle', nameGap: 22 },
        yAxis: { type: 'value', name: spec.ylabel || '目标卡数', nameLocation: 'middle', nameGap: 26 },
        visualMap: {
          min: zmin, max: zmax, dimension: 2, calculable: true, orient: 'horizontal',
          left: 'center', bottom: 0, textStyle: { fontSize: 10 },
          inRange: { color: scaleColors('YlOrRd') },
        },
        series: [{ type: 'scatter', symbolSize: 6, data }],
      }
      return decorate(opt, { xValue: true })
    }
    case 'subplot_grid': {
      // 多热力图网格：matrices 并排（每行 cols 个）
      const mats = d.matrices || []
      const titles = d.titles || []
      const cols = d.cols || 4
      const rows = d.row_labels || (mats[0] ? mats[0].map((_, i) => String(i)) : [])
      const gridA = [], xAxis = [], yAxis = [], series = [], visualMap = []
      const perW = 100 / Math.min(cols, mats.length || 1)
      mats.forEach((mat, idx) => {
        const colI = idx % cols
        const rowI = Math.floor(idx / cols)
        const gw = perW * 0.92
        const gh = 88 / Math.max(1, Math.ceil(mats.length / cols))
        gridA.push({ left: (colI * perW + 2) + '%', right: (100 - (colI + 1) * perW + perW * 0.08) + '%', top: (rowI * gh + 3) + '%', height: gh * 0.8 + '%' })
        // #7：子图标题（对齐旧 Plotly 子图底部池名 annotation）——用 grid 上方标题组件
        if (titles[idx]) gridA[gridA.length - 1].title = { text: titles[idx], left: 'center', textStyle: { fontSize: 10 } }
        // #5：x 轴置顶（对齐旧 xaxis_side='top'）
        xAxis.push({ type: 'category', gridIndex: idx, data: d.col_labels || (mat[0] ? mat[0].map((_, j) => String(j)) : []), axisLabel: { fontSize: 10 }, position: 'top' })
        yAxis.push({ type: 'category', gridIndex: idx, data: rows, axisLabel: { fontSize: 10 } })
        const vals = []
        mat.forEach((r, i) => r.forEach((v, j) => vals.push([j, i, v])))
        series.push({ type: 'heatmap', xAxisIndex: idx, yAxisIndex: idx, data: vals })
        // #6：每个 visualMap 绑定对应 seriesIndex（否则多 visualMap 作用域歧义、共用最后一张色阶）
        visualMap.push({ min: Math.min(0, ...vals.map((v) => v[2])), max: Math.max(0, ...vals.map((v) => v[2])), show: false, seriesIndex: [idx] })
      })
      const opt = { title, tooltip: { position: 'top' }, grid: gridA, xAxis, yAxis, series, visualMap }
      return decorate(opt)
    }
    case 'composite': {
      // 组合图（对齐旧 Plotly make_subplots rows=n shared_xaxes）：多个子面板垂直堆叠，
      // 共享 x 轴（仅末面板显示 x 轴标签），各面板独立 y 轴标题与系列。
      // 面板高度按 row_heights 比例分配（对齐旧 row_heights=[0.4,0.35,0.25]），
      // 用像素 grid，总高由 __gscComposite 标记交给 ResultChart。
      const panels = d.panels || []
      const n = panels.length
      if (!n) return {}
      const BASE_H = 420        // 基准总高（约对齐旧 plot_vulnerability height=520 的紧凑版）
      const TOP = 40           // 顶部预留（标题）
      // row_heights 归一化 → 各面板像素高（缺省等分）
      const rh = (d.row_heights && d.row_heights.length === n) ? d.row_heights : null
      const rhSum = rh ? rh.reduce((a, b) => a + b, 0) : n
      const panelHs = panels.map((_, i) => Math.round(BASE_H * ((rh ? rh[i] : 1) / rhSum)))
      const gridA = [], xAxis = [], yAxis = [], series = []
      // 各面板 layout_hints：bin_edges（histogram）、bar_centers/widths/colors（N_j）
      const edgesByPanel = panels.map((p) => {
        const h = p.layout_hints || {}
        return (Array.isArray(h.bin_edges) && h.bin_edges.length >= 2) ? h.bin_edges : null
      })
      const edgeForPanel = (i) => {
        if (edgesByPanel[i]) return edgesByPanel[i]
        // 回退：取第一个有 bin_edges 的面板（共享 x 轴，各面板坐标应一致）
        for (let j = 0; j < n; j++) if (edgesByPanel[j]) return edgesByPanel[j]
        return null
      }
      let cumTop = TOP
      panels.forEach((p, i) => {
        const ph = panelHs[i]
        const top = cumTop
        cumTop += ph + 6
        gridA.push({ left: 70, right: 24, top, height: ph - 6 })
        const isLast = i === n - 1
        const xlabP = isLast ? (d.xlabel || '') : ''
        xAxis.push({
          type: 'value', gridIndex: i,
          axisLabel: { show: isLast, fontSize: 10 },
          axisLine: { show: isLast },
          axisTick: { show: isLast },
          splitLine: { show: false },
          name: xlabP,
          nameLocation: 'middle', nameGap: 22,
        })
        // 对齐旧 plot_vulnerability：PAVA 面板 y 轴固定 [-0.05, 1.05]（概率区间）
        const pd = p.data || {}
        const pt = p.chart_type
        const yRange = (pt === 'scatter' && p.title && /失败/.test(p.title))
          ? { min: -0.05, max: 1.05 }
          : {}
        yAxis.push({
          type: 'value', gridIndex: i,
          name: p.title || '',
          nameLocation: 'middle',
          nameGap: 36,
          show: true,
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { show: true, fontSize: 9, color: '#888' },
          splitLine: { show: false },
          ...yRange,
        })
        if (pt === 'histogram') {
          // 直方图面板：custom renderItem 按 bin_edges 画矩形 + 均值 markLine + 失败 overlay
          const samples = pd.samples || []
          const edges = edgeForPanel(i)
          const nb = edges.length - 1
          const counts = new Array(nb).fill(0)
          for (const v of samples) {
            for (let j = 0; j < nb; j++) {
              if (v >= edges[j] && (j === nb - 1 ? v <= edges[j + 1] : v < edges[j + 1])) { counts[j]++; break }
            }
          }
          if (pd.density && samples.length) {
            for (let j = 0; j < nb; j++) {
              const w = edges[j + 1] - edges[j]
              if (w > 0) counts[j] = counts[j] / (samples.length * w)
            }
          }
          const ml = []
          if (pd.mean_line && samples.length) {
            const mn = samples.reduce((a, b) => a + b, 0) / samples.length
            ml.push({ xAxis: +mn.toFixed(2), label: { formatter: '均值 ' + mn.toFixed(2) } })
          }
          const ovs = (pd.overlays || []).map((ov) => {
            const o = ov.samples || []
            const oc = new Array(nb).fill(0)
            for (const v of o) {
              for (let j = 0; j < nb; j++) {
                if (v >= edges[j] && (j === nb - 1 ? v <= edges[j + 1] : v < edges[j + 1])) { oc[j]++; break }
              }
            }
            if (pd.density && o.length) {
              for (let j = 0; j < nb; j++) {
                const w = edges[j + 1] - edges[j]
                if (w > 0) oc[j] = oc[j] / (o.length * w)
              }
            }
            return {
              type: 'line', smooth: true, symbol: 'none',
              data: edges.slice(0, -1).map((c, j) => [(edges[j] + edges[j + 1]) / 2, oc[j]]),
              lineStyle: { color: ov.color || '#ff4444', width: 1.5 },
              itemStyle: { color: ov.color || '#ff4444' },
              areaStyle: { color: ov.color || '#ff4444', opacity: 0.25 },
              name: ov.label || '',
              xAxisIndex: i, yAxisIndex: i,
            }
          })
          const histS = {
            type: 'custom', xAxisIndex: i, yAxisIndex: i,
            renderItem(params, api) {
              const j = params.dataIndex
              const x = api.value(0)
              const y = api.value(1)
              const x1 = api.coord([x, 0])
              const x2 = api.coord([edges[j + 1], 0])
              const yBase = api.coord([x, 0])[1]
              const yTop = api.coord([x, y])[1]
              const w = Math.abs(x2[0] - x1[0])
              return {
                type: 'rect',
                shape: {
                  x: Math.min(x1[0], x2[0]), y: Math.min(yBase, yTop),
                  width: Math.max(w, 1), height: Math.max(0, Math.abs(yBase - yTop)),
                },
                style: api.style({ fill: '#1f77b4' }),
              }
            },
            data: edges.slice(0, -1).map((e, j) => [e, counts[j]]),
            markLine: ml.length ? { silent: true, symbol: 'none', lineStyle: { color: 'rgba(220,50,50,0.55)', type: 'dashed', width: 1 }, data: ml } : undefined,
          }
          series.push(histS, ...ovs)
        } else if (pt === 'scatter') {
          // PAVA 面板：p̂_j 灰点（大小∝N_j）+ θ̃ 台阶 + α hline + 脆弱区间 markArea
          const traces = pd.traces || []
          const sers = traces.map((tr) => ({
            type: 'scatter', xAxisIndex: i, yAxisIndex: i,
            symbolSize: tr.marker_sizes ? (idx) => tr.marker_sizes[idx] : (tr.marker_size || 7),
            symbol: tr.marker_symbol || 'circle',
            itemStyle: { color: tr.marker_color || '#5470c6', opacity: tr.opacity ?? 1 },
            data: (tr.x || []).map((xi, jj) => [xi, (tr.y || [])[jj]]),
            lineStyle: tr.line_width != null ? { width: tr.line_width } : undefined,
            ...(tr.customdata && tr.customdata.length ? {
              tooltip: {
                formatter(params) {
                  const pt = params.data || []
                  const nd = tr.customdata[params.dataIndex] ?? ''
                  return `箱中心: ${pt[0] == null ? '' : Number(pt[0]).toFixed(0)}<br>p̂: ${pt[1] == null ? '' : Number(pt[1]).toFixed(3)}<br>N: ${nd}`
                },
              },
            } : {}),
          }))
          const hml = markLines(p.annotations, 'yAxis')
          const ma = markAreas(p.shaded_regions)
          if (sers.length) {
            if (hml) sers[0].markLine = { silent: true, symbol: 'none', data: hml }
            if (ma) sers[0].markArea = ma
          }
          series.push(...sers)
        } else if (pt === 'bar') {
          // N_j 面板：柱宽=PAVA 箱宽，色=安全蓝/脆弱红（对齐旧 go.Bar width=bar_widths）
          const vals = pd.values || []
          const h = p.layout_hints || {}
          const centers = h.bar_centers || []
          const widths = h.bar_widths || []
          const colors = h.bar_colors || []
          series.push({
            type: 'custom', xAxisIndex: i, yAxisIndex: i,
            renderItem(params, api) {
              const j = params.dataIndex
              const cx = api.coord([centers[j], 0])
              const half = api.coord([centers[j] + (widths[j] ?? 1) / 2, 0])[0] - cx[0]
              const yBase = api.coord([centers[j], 0])[1]
              const yTop = api.coord([centers[j], vals[j]])[1]
              return {
                type: 'rect',
                shape: {
                  x: cx[0] - half, y: Math.min(yBase, yTop),
                  width: Math.max(half * 2, 1), height: Math.max(0, Math.abs(yBase - yTop)),
                },
                style: api.style({ fill: colors[j] || '#5470c6' }),
              }
            },
            data: vals.map((v, j) => [centers[j] ?? 0, v]),
            // 对齐旧 go.Bar hovertemplate「箱: [a, b] N」：由 bar_centers/widths 还原箱范围
            tooltip: {
              formatter(params) {
                const j = params.dataIndex
                const lo = centers[j] - (widths[j] ?? 0) / 2
                const hi = centers[j] + (widths[j] ?? 0) / 2
                const v = vals[j]
                return `箱: [${Number(lo).toFixed(0)}, ${Number(hi).toFixed(0)}]<br>N: ${v}`
              },
            },
          })
        }
      })
      const opt = {
        title,
        tooltip: { trigger: 'axis' },
        // 对齐旧 plot_vulnerability showlegend=False：复合面板系列名不显示图例
        legend: { show: false },
        grid: gridA, xAxis, yAxis, series,
      }
      opt.toolbox = { right: 8, top: 2, itemSize: 13, feature: { dataZoom: { yAxisIndex: 'none', title: { zoom: '区域缩放', back: '还原缩放' } }, restore: { title: '还原' }, saveAsImage: { title: '保存图片' } } }
      opt.dataZoom = [{ type: 'inside', xAxisIndex: panels.map((_, i) => i), zoomOnMouseWheel: false, moveOnMouseWheel: false, moveOnMouseMove: false }]
      opt.__gscComposite = { total: cumTop + 8 }
      return opt
    }
    case 'table': {
      // 表格不画 ECharts——返回特殊标记，由调用方渲染 el-table
      return { __table: true, headers: d.headers || [], rows: d.rows || [] }
    }
    default:
      return {}
  }
}

// ChartSpec JSON 数组 → 多个 ECharts option（供结果区多图）
export function specsToECharts(specList) {
  if (!Array.isArray(specList)) return []
  return specList.map((s) => specToECharts(s))
}
