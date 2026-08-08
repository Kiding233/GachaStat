/* ChartSpec → Plotly.js / ECharts 双渲染器（垂直切片前端核心）。

验证点：同一份 ChartSpec JSON，两个库各自独立渲染。
- Plotly.js：沿用项目后端语义（histogram 自动分箱、cdf 手算、ridge 多行共享 x）
- ECharts：手动分箱、markLine 标注、多 grid 山脊

这是未来换头时前端 renderer 的原型。
*/

// ===== 通用工具 =====

function specTitle(spec) { return spec.title || spec.chart_type; }

// 简单直方图分箱（ECharts 无自动分箱，Plotly 有 go.Histogram）
function binCounts(samples, nbins) {
  const lo = Math.min(...samples);
  const hi = Math.max(...samples);
  if (hi === lo) return { centers: [lo], counts: [samples.length] };
  const w = (hi - lo) / nbins;
  const counts = new Array(nbins).fill(0);
  const centers = [];
  for (let i = 0; i < nbins; i++) centers.push(lo + (i + 0.5) * w);
  for (const v of samples) {
    let idx = Math.floor((v - lo) / w);
    if (idx >= nbins) idx = nbins - 1;
    counts[idx]++;
  }
  return { centers, counts };
}

// 经验 CDF 点（两个库都需手算，与后端 _build_cdf 语义一致）
function cdfPoints(samples) {
  const sorted = [...samples].sort((a, b) => a - b);
  const n = sorted.length;
  return sorted.map((x, i) => [x, (i + 1) / n]);
}

function sampleMean(samples) {
  return samples.reduce((a, b) => a + b, 0) / samples.length;
}

// ===== Plotly.js renderer =====

function specToPlotly(spec) {
  const t = spec.chart_type;
  const d = spec.data;
  if (t === 'bar') {
    return {
      data: [{ type: 'bar', x: d.labels, y: d.values, marker: { color: '#1f77b4' } }],
      layout: { title: specTitle(spec), xaxis: { title: spec.xlabel }, yaxis: { title: spec.ylabel } },
    };
  }
  if (t === 'histogram') {
    const nbins = (spec.layout_hints && spec.layout_hints.nbins) || 30;
    const fig = {
      data: [{
        type: 'histogram', x: d.samples, nbinsx: nbins,
        marker: { color: '#1f77b4' },
        hovertemplate: '抽数 %{x}<br>频数 %{y}<extra></extra>',
      }],
      layout: { title: specTitle(spec), bargap: 0.05, xaxis: { title: spec.xlabel }, yaxis: { title: spec.ylabel } },
    };
    const shapes = [];
    const anns = [];
    if (d.mean_line) {
      const m = sampleMean(d.samples);
      shapes.push({ type: 'line', x0: m, x1: m, y0: 0, y1: 1, yref: 'paper', line: { color: '#ff4444', dash: 'dash' } });
      anns.push({ x: m, y: 1.03, yref: 'paper', text: '均值 ' + m.toFixed(2), showarrow: false, font: { color: '#ff4444', size: 11 } });
    }
    if (d.quantile_lines) {
      const sorted = [...d.samples].sort((a, b) => a - b);
      d.quantile_lines.forEach(q => {
        const qv = sorted[Math.floor(q * (sorted.length - 1))];
        shapes.push({ type: 'line', x0: qv, x1: qv, y0: 0, y1: 1, yref: 'paper', line: { color: '#ff7f0e', dash: 'dot' } });
        anns.push({ x: qv, y: 0.95, yref: 'paper', text: 'P' + Math.round(q * 100), showarrow: false, font: { color: '#ff7f0e', size: 11 } });
      });
    }
    if (shapes.length) fig.layout.shapes = shapes;
    if (anns.length) fig.layout.annotations = anns;
    return fig;
  }
  if (t === 'cdf') {
    const pts = cdfPoints(d.samples);
    return {
      data: [{ type: 'scatter', x: pts.map(p => p[0]), y: pts.map(p => p[1]), mode: 'lines', line: { color: '#1f77b4' } }],
      layout: { title: specTitle(spec), xaxis: { title: spec.xlabel }, yaxis: { title: spec.ylabel, range: [0, 1.02] } },
    };
  }
  if (t === 'ridge') {
    const keys = Object.keys(d.series);
    const n = keys.length;
    const nbins = (spec.layout_hints && spec.layout_hints.nbins) || 50;
    const all = [].concat(...keys.map(k => d.series[k]));
    const lo = Math.min(...all);
    const hi = Math.max(...all);
    const w = (hi - lo) / nbins;
    const rowH = 0.92 / n;
    const traces = keys.map((k, i) => ({
      type: 'histogram', x: d.series[k],
      xbins: { start: lo, end: hi + w + w * 1e-6, size: w },
      marker: { color: 'hsl(' + ((i * 55 + 260) % 360) + ',70%,50%)', opacity: 0.75 },
      yaxis: 'y' + (i + 1),
      name: (d.labels && d.labels[k]) || k,
      hovertemplate: '<b>' + ((d.labels && d.labels[k]) || k) + '</b><br>抽数 %{x}<br>频数 %{y}<extra></extra>',
    }));
    const yaxes = {};
    for (let i = 0; i < n; i++) {
      const top = 1 - (i + 1) * rowH + 0.012;
      yaxes['yaxis' + (i + 1)] = {
        domain: [top, top + rowH - 0.03],
        title: { text: (d.labels && d.labels[keys[i]]) || keys[i], font: { size: 11 } },
        showgrid: false,
        zeroline: false,
      };
    }
    const layout = Object.assign({
      title: specTitle(spec),
      xaxis: { title: spec.xlabel, anchor: 'y' + n },
      barmode: 'overlay', bargap: 0.02,
      showlegend: false,
      margin: { l: 90, r: 20, t: 55, b: 40 },
    }, yaxes);
    return { data: traces, layout };
  }
  return { data: [], layout: { title: specTitle(spec) } };
}

// ===== ECharts renderer =====

function specToECharts(spec) {
  const t = spec.chart_type;
  const d = spec.data;
  if (t === 'bar') {
    return {
      title: { text: specTitle(spec), left: 'center' },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      toolbox: { right: 10, feature: { restore: {}, saveAsImage: { name: 'bar' } } },
      dataZoom: [{ type: 'inside', xAxisIndex: 0 }],
      xAxis: { type: 'category', data: d.labels, name: spec.xlabel },
      yAxis: { type: 'value', name: spec.ylabel },
      series: [{ type: 'bar', data: d.values, barWidth: '45%', itemStyle: { color: '#5470c6' } }],
    };
  }
  if (t === 'histogram') {
    const nbins = (spec.layout_hints && spec.layout_hints.nbins) || 30;
    const { centers, counts } = binCounts(d.samples, nbins);
    const w = centers.length > 1 ? centers[1] - centers[0] : 1;
    const mean = sampleMean(d.samples);
    const markLines = [];
    // 均值/分位数线是「抽数」量纲，画在 x 轴（垂直线），不是 y 轴（频次）
    if (d.mean_line) markLines.push({ xAxis: +mean.toFixed(2), label: { formatter: '均值 ' + mean.toFixed(2) } });
    if (d.quantile_lines) {
      const sorted = [...d.samples].sort((a, b) => a - b);
      d.quantile_lines.forEach(q => {
        const qv = sorted[Math.floor(q * (sorted.length - 1))];
        markLines.push({ xAxis: +qv.toFixed(2), label: { formatter: 'P' + Math.round(q * 100) } });
      });
    }
    return {
      title: { text: specTitle(spec), left: 'center' },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 60, right: 40, top: 55, bottom: 45 },
      toolbox: { right: 10, feature: { dataZoom: { yAxisIndex: 'none' }, restore: {}, saveAsImage: { name: 'histogram' } } },
      dataZoom: [{ type: 'inside', xAxisIndex: 0 }],
      xAxis: { type: 'value', name: spec.xlabel },
      yAxis: { type: 'value', name: spec.ylabel },
      series: [{
        type: 'bar',
        data: centers.map((c, i) => [c, counts[i]]),
        barWidth: w * 0.85,
        itemStyle: { color: '#5470c6' },
        markLine: markLines.length ? {
          silent: true, symbol: 'none',
          lineStyle: { color: '#ff4444', type: 'dashed', width: 1 },
          label: { color: '#ff4444', fontSize: 11 },
          data: markLines,
        } : undefined,
      }],
    };
  }
  if (t === 'cdf') {
    return {
      title: { text: specTitle(spec), left: 'center' },
      tooltip: { trigger: 'axis' },
      toolbox: { right: 10, feature: { dataZoom: { yAxisIndex: 'none' }, restore: {}, saveAsImage: { name: 'cdf' } } },
      dataZoom: [{ type: 'inside', xAxisIndex: 0 }],
      xAxis: { type: 'value', name: spec.xlabel },
      yAxis: { type: 'value', name: spec.ylabel, min: 0, max: 1.02 },
      series: [{
        type: 'line',
        data: cdfPoints(d.samples).map(p => [p[0], +p[1].toFixed(4)]),
        showSymbol: false,
        lineStyle: { color: '#5470c6', width: 2 },
        areaStyle: { color: 'rgba(84,112,198,0.08)' },
      }],
    };
  }
  if (t === 'ridge') {
    const keys = Object.keys(d.series);
    const n = keys.length;
    const nbins = (spec.layout_hints && spec.layout_hints.nbins) || 50;
    const grid = [], xAxis = [], yAxis = [], series = [];
    keys.forEach((k, i) => {
      const rowH = 88 / n;
      grid.push({ left: 80, right: 25, top: (6 + i * rowH) + '%', height: rowH * 0.72 + '%' });
      xAxis.push({ type: 'value', gridIndex: i, name: (i === n - 1) ? spec.xlabel : '', nameLocation: 'middle', nameGap: 25 });
      yAxis.push({ type: 'value', gridIndex: i, name: (d.labels && d.labels[k]) || k, nameLocation: 'middle', show: true, axisLabel: { show: false }, splitLine: { show: false } });
      const { centers, counts } = binCounts(d.series[k], nbins);
      series.push({
        type: 'bar', xAxisIndex: i, yAxisIndex: i,
        data: centers.map((c, j) => [c, counts[j]]),
        barWidth: '85%',
        itemStyle: { color: 'hsl(' + ((i * 55 + 260) % 360) + ',70%,50%)', opacity: 0.75 },
        name: (d.labels && d.labels[k]) || k,
      });
    });
    return {
      title: { text: specTitle(spec), left: 'center' },
      tooltip: { trigger: 'axis' },
      toolbox: { right: 10, feature: { dataZoom: { yAxisIndex: 'none' }, restore: {}, saveAsImage: { name: 'ridge' } } },
      dataZoom: [{ type: 'inside', xAxisIndex: keys.map((_, i) => i) }],
      grid, xAxis, yAxis, series,
    };
  }
  return {};
}
