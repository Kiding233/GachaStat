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

// 区间（ShadedRegion）→ markArea.data（x 轴区间，仅 value 轴有意义）
function markAreas(regions) {
  if (!regions || !regions.length) return undefined
  const data = regions.map((r) => [
    { xAxis: r.lower, itemStyle: { color: r.color || 'rgba(200,50,50,0.12)' } },
    { xAxis: r.upper },
  ])
  return data
}

// 通用 markLine + markArea 挂到某 series 上
function addMarks(series, annotations, regions) {
  const ml = annotations ? markLines(annotations, 'xAxis') : undefined
  const ma = regions ? markAreas(regions) : undefined
  if (ml) series.markLine = { silent: true, symbol: 'none', data: ml }
  if (ma) series.markArea = { silent: true, data: ma }
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
      const samples = d.samples || []
      const nbins = (spec.layout_hints && spec.layout_hints.nbins) || 30
      const { centers, counts } = binCounts(samples, nbins)
      const w = centers.length > 1 ? centers[1] - centers[0] : 1
      const ml = []
      if (d.mean_line) ml.push({ xAxis: +sampleMean(samples).toFixed(4), label: { formatter: '均值 ' + sampleMean(samples).toFixed(2) } })
      if (d.quantile_lines) {
        const sorted = [...samples].sort((a, b) => a - b)
        for (const q of d.quantile_lines) ml.push({ xAxis: +quantile(sorted, q).toFixed(4), label: { formatter: 'P' + Math.round(q * 100) } })
      }
      // overlays：叠加的额外分布（同一 x 轴上画密度曲线）
      const overlays = (d.overlays || []).map((ov) => {
        const o = ov.samples || []
        const ob = (spec.layout_hints && spec.layout_hints.nbins) || 30
        const bc = binCounts(o, ob)
        return {
          type: 'line', smooth: true, symbol: 'none',
          data: bc.centers.map((c, i) => [c, bc.counts[i]]),
          lineStyle: { color: ov.color || '#ff4444', width: 1.5 },
          itemStyle: { color: ov.color || '#ff4444' },
          name: ov.label || '',
        }
      })
      const series = [{
        type: 'bar',
        data: centers.map((c, i) => [c, counts[i]]),
        barWidth: w * 0.85,
        itemStyle: { color: '#5470c6' },
        markLine: ml.length ? { silent: true, symbol: 'none', lineStyle: { color: '#ff4444', type: 'dashed', width: 1 }, label: { color: '#ff4444', fontSize: 11 }, data: ml } : undefined,
        markArea: markAreas(spec.shaded_regions),
      }]
      const opt = {
        title,
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid,
        legend: overlays.length ? { top: 0, right: 80, textStyle: { fontSize: 11 } } : undefined,
        xAxis: { type: 'value', name: xlab, nameLocation: 'middle', nameGap: 22 },
        yAxis: { type: 'value', name: ylab },
        series: [...series, ...overlays],
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
      const keys = Object.keys(d.series || {})
      const n = keys.length
      const nbins = (spec.layout_hints && spec.layout_hints.nbins) || 50
      const gridA = [], xAxis = [], yAxis = [], series = []
      keys.forEach((k, i) => {
        const rowH = 88 / n
        gridA.push({ left: 80, right: 25, top: (6 + i * rowH) + '%', height: rowH * 0.72 + '%' })
        xAxis.push({ type: 'value', gridIndex: i, name: (i === n - 1) ? xlab : '', nameLocation: 'middle', nameGap: 25 })
        yAxis.push({ type: 'value', gridIndex: i, name: (d.labels && d.labels[k]) || k, nameLocation: 'middle', show: true, axisLabel: { show: false }, splitLine: { show: false } })
        const { centers, counts } = binCounts(d.series[k], nbins)
        series.push({
          type: 'bar', xAxisIndex: i, yAxisIndex: i,
          data: centers.map((c, j) => [c, counts[j]]),
          barWidth: '85%',
          itemStyle: { color: 'hsl(' + ((i * 55 + 260) % 360) + ',70%,50%)', opacity: 0.75 },
          name: (d.labels && d.labels[k]) || k,
        })
      })
      const opt = {
        title,
        tooltip: { trigger: 'axis' },
        dataZoom: [{ type: 'inside', xAxisIndex: keys.map((_, i) => i), zoomOnMouseWheel: false, moveOnMouseWheel: false, moveOnMouseMove: false }],
        grid: gridA, xAxis, yAxis, series,
      }
      opt.toolbox = { right: 10, top: 0, feature: { dataZoom: { yAxisIndex: 'none' }, restore: {}, saveAsImage: {} } }
      return opt
    }
    case 'boxplot': {
      const keys = Object.keys(d.series || {})
      const labels = keys.map((k) => (d.labels && d.labels[k]) || k)
      const opt = {
        title,
        tooltip: { trigger: 'item' },
        grid,
        xAxis: { type: 'category', data: labels, name: xlab, nameLocation: 'middle', nameGap: 22 },
        yAxis: { type: 'value', name: ylab },
        series: [{
          type: 'boxplot',
          data: keys.map((k) => {
            const s = [...(d.series[k] || [])].sort((a, b) => a - b)
            return [quantile(s, 0.25), quantile(s, 0.5), quantile(s, 0.75), quantile(s, 0.05), quantile(s, 0.95)]
          }),
          itemStyle: { color: '#5470c6', borderColor: '#2f4f8f' },
        }],
      }
      return decorate(opt)
    }
    case 'scatter': {
      const base = (tr) => ({
        type: 'scatter',
        symbolSize: tr.marker_size || 7,
        symbol: tr.marker_symbol || 'circle',
        itemStyle: { color: tr.marker_color || '#5470c6' },
        data: (tr.x || []).map((xi, i) => [xi, (tr.y || [])[i]]),
      })
      let series
      if (d.traces && d.traces.length) series = d.traces.map(base)
      else series = [base({ x: d.x || [], y: d.y || [], mode: d.mode, marker_color: '#5470c6' })]
      const opt = {
        title,
        tooltip: { trigger: 'item' },
        grid,
        xAxis: { type: 'value', name: xlab, nameLocation: 'middle', nameGap: 22 },
        yAxis: { type: 'value', name: ylab },
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
      const opt = {
        title,
        tooltip: { position: 'top' },
        grid: { top: 30, bottom: 40, left: 60, right: 60 },
        xAxis: { type: 'category', data: cols, name: xlab, splitArea: { show: true } },
        yAxis: { type: 'category', data: rows, name: ylab, splitArea: { show: true } },
        visualMap: { min: Math.min(0, ...vals.map((v) => v[2])), max: Math.max(0, ...vals.map((v) => v[2])), calculable: true, orient: 'horizontal', left: 'center', bottom: 0, textStyle: { fontSize: 10 } },
        series: [{ type: 'heatmap', data: vals, label: { show: false } }],
      }
      return decorate(opt)
    }
    case 'waterfall_3d': {
      // ECharts 3D 需 echarts-gl；无依赖时退化为散点（x=池索引, y=资源, z=计数）
      const xs = d.x || []
      const ys = d.y || []
      const zs = d.z || []
      const data = xs.map((x, i) => [x, ys[i] ?? 0, zs[i] ?? 0])
      const opt = {
        title,
        tooltip: { trigger: 'item' },
        grid,
        xAxis: { type: 'value', name: spec.layout_hints?.zlabel || '池', nameLocation: 'middle', nameGap: 22 },
        yAxis: { type: 'value', name: spec.layout_hints?.zlabel || '资源', nameLocation: 'middle', nameGap: 22 },
        series: [{ type: 'scatter', symbolSize: 8, itemStyle: { color: '#5470c6' }, data: data.map((p) => [p[0], p[1], p[2]]) }],
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
        xAxis.push({ type: 'category', gridIndex: idx, data: d.col_labels || (mat[0] ? mat[0].map((_, j) => String(j)) : []), axisLabel: { fontSize: 10 } })
        yAxis.push({ type: 'category', gridIndex: idx, data: rows, axisLabel: { fontSize: 10 } })
        const vals = []
        mat.forEach((r, i) => r.forEach((v, j) => vals.push([j, i, v])))
        series.push({ type: 'heatmap', xAxisIndex: idx, yAxisIndex: idx, data: vals })
        visualMap.push({ min: Math.min(0, ...vals.map((v) => v[2])), max: Math.max(0, ...vals.map((v) => v[2])), show: false })
      })
      const opt = { title, tooltip: { position: 'top' }, grid: gridA, xAxis, yAxis, series, visualMap }
      return decorate(opt)
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
