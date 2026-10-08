/* GachaStat 图表标准 v1：ChartSpec(IR) → ECharts option 的前端 renderer。
 *
 * 这不是「在页面里画点好看的东西」，而是把未来真正要用的那条管线在探针里跑通：
 *   Python ChartSpec 数据类（gacha_simulator/visualization/chart_spec.py）
 *     → JSON → 本文件 specToOption() → ECharts option
 * 探针页面里的每个图都喂一份 ChartSpec 形状的对象，所以探针同时是设计的样品
 * 和渲染契约的样品；接前端 renderer 时这份代码是原型而非废稿。
 *
 * 【配色是算出来的，不是挑出来的】
 * 用 dataviz skill 的校验器（validate_palette.js）跑过，浅色底 surface #ffffff：
 *   分类色 #1976d2 / #00897b / #7b1fa2
 *     亮度带 PASS · 色度下限 PASS · CVD 分离 PASS（全对最差 #7b1fa2↔#1976d2
 *     ΔE 10.8 deutan）· 常视分离 PASS（最差 ΔE 16.1）· 对比度 PASS（均 ≥3:1）
 *   单色阶（连续量级）#82b5e9 #5c9fe0 #3a8ad4 #1f6fc4 #12539e #083a80
 *     亮度单调 PASS · 相邻级差 PASS · 亮端对白底 2.16:1 PASS · 单一色相 PASS
 * 语义色（good/warn/danger）不进分类色序列，见下面 STATUS 的注释。
 *
 * 【为什么用 SVG renderer 而不是默认的 canvas】
 * 「等宽数字」是本项目一条成文标准，而 canvas 里拿不到 font-variant-numeric，
 * 只能靠换字体近似。SVG renderer 输出的 text 是真 DOM 节点，CSS 一条
 * font-variant-numeric:tabular-nums 就生效。代价是元素多时慢，所以下面按
 * 数据点数量在 svg/canvas 之间切（threshold 见 RENDERER_BUDGET）。
 *
 * 【图题不画在图里】
 * 图注体系要求「图题在图下、表题在表上」，且标题/导语/口径脚注由 HTML 承载
 * （见 archetypes.html 与 工作区交互形态.md §5.7）。所以主题里 title 默认关掉，
 * spec.title 只在 layout_hints.title_in_chart 显式开启时才画。
 */
(function (global) {
  'use strict';

  var echarts = global.echarts;
  if (!echarts) {
    throw new Error('gs-charts.js 需要先加载 libs/echarts.min.js');
  }

  var FONT_STACK = '"Microsoft YaHei","PingFang SC","Segoe UI",system-ui,sans-serif';

  /* ── 令牌 ──
     ECharts 不认 var()，但图表配色必须与 HTML（数据带、表格、图注）同源，
     否则同一个数在图里和表里是两种蓝。所以这里从 :root 上「读」CSS 变量
     （变量定义在 libs/gs-charts.css），读不到才回退到下面这些字面量。
     改配色只改 CSS 一处。 */
  var FALLBACK = {
    '--gsc-chart-c1': '#1976d2', '--gsc-chart-c2': '#00897b', '--gsc-chart-c3': '#7b1fa2',
    '--gsc-chart-seq-1': '#82b5e9', '--gsc-chart-seq-2': '#5c9fe0',
    '--gsc-chart-seq-3': '#3a8ad4', '--gsc-chart-seq-4': '#1f6fc4',
    '--gsc-chart-seq-5': '#12539e', '--gsc-chart-seq-6': '#083a80',
    '--gsc-chart-div-neg': '#0d47a1', '--gsc-chart-div-mid': '#b0b8c4',
    '--gsc-chart-div-pos': '#c62828',
    '--gsc-chart-good': '#2e7d32', '--gsc-chart-warn': '#b26a00',
    '--gsc-chart-danger': '#c62828', '--gsc-chart-muted': '#8b93a3',
    '--gsc-chart-grid': '#e6e9ee', '--gsc-chart-axis': '#c8ced9',
    '--gsc-chart-surface': '#ffffff',
    '--gsc-text-primary': '#1f2430', '--gsc-text-muted': '#5a6272',
    '--gsc-text-faint': '#8b93a3', '--gsc-accent': '#1976d2',
    '--gsc-font-main': FONT_STACK,
  };

  function readTokens() {
    var out = {}, cs = null;
    try {
      if (typeof getComputedStyle === 'function' && document.documentElement) {
        cs = getComputedStyle(document.documentElement);
      }
    } catch (e) { cs = null; }
    Object.keys(FALLBACK).forEach(function (k) {
      var v = cs ? cs.getPropertyValue(k) : '';
      v = (v || '').trim();
      out[k] = v || FALLBACK[k];
    });
    return out;
  }

  var V = readTokens();

  var TOK = {
    ink: V['--gsc-text-primary'], ink2: V['--gsc-text-muted'], ink3: V['--gsc-text-faint'],
    accent: V['--gsc-accent'], surface: V['--gsc-chart-surface'],
    grid: V['--gsc-chart-grid'],      // 比表面深一档的灰，发丝线，实线
    axis: V['--gsc-chart-axis'],
  };

  /* 分类色：固定顺序，不循环、不生成。第 4 个序列不是「再挑一个颜色」，
     而是折进「其他」或改小倍数图（见 dataviz 反模式）。本项目图里极少超过 3 条。 */
  var CAT = [V['--gsc-chart-c1'], V['--gsc-chart-c2'], V['--gsc-chart-c3']];

  /* 语义色：只用于语义，永不作为序列身份。红＝尾部/最差/危险，绿＝达标，
     橙＝警告，灰＝不活跃/中性。图里出现红色必须意味着「坏」，没有例外。 */
  var STATUS = {
    good: V['--gsc-chart-good'], warn: V['--gsc-chart-warn'],
    danger: V['--gsc-chart-danger'], muted: V['--gsc-chart-muted'],
  };

  /* 单色阶：连续量级的编码。色盲、灰度打印下都单调可读。 */
  var SEQ = [V['--gsc-chart-seq-1'], V['--gsc-chart-seq-2'], V['--gsc-chart-seq-3'],
    V['--gsc-chart-seq-4'], V['--gsc-chart-seq-5'], V['--gsc-chart-seq-6']];

  /* 发散色阶：两个色相 + 中性灰中点。蓝↔红分冷暖，中点读作「无」。
     这里红色是「极性的一极」而非状态，是语义色纪律的登记例外：同一张图里
     不允许发散色阶的极色再被当作状态色使用。 */
  var DIV = [V['--gsc-chart-div-neg'], '#3a8ad4', V['--gsc-chart-div-mid'],
    '#d95f5f', V['--gsc-chart-div-pos']];

  var FONT = V['--gsc-font-main'];

  /* 分类色取第 n 条序列；语义场景一律走 STATUS，不要用这里 */
  function cat(i) { return CAT[i % CAT.length]; }

  /* ── 主题 ── */
  var THEME = {
    color: CAT,
    backgroundColor: 'transparent',
    textStyle: { fontFamily: FONT, fontSize: 11, color: TOK.ink2 },

    // 图题归 HTML（见图注体系），默认不画
    title: { show: false },

    // 栅格：containLabel 让轴标签无论如何都不被裁，同时使各图左缘自动对齐
    grid: { left: 6, right: 18, top: 22, bottom: 10, containLabel: true },

    /* 线：2px、圆头圆角；数据点 ≥8px（r≥4）；面积是一层薄雾不是实块 */
    line: {
      symbol: 'circle', symbolSize: 8, showSymbol: false,
      lineStyle: { width: 2, cap: 'round', join: 'round' },
      itemStyle: { borderWidth: 2, borderColor: TOK.surface },   // 2px 表面环
      emphasis: { focus: 'series', scale: 1.2 },
    },
    /* 柱：≤24px，顶端 4px 圆角、基线端方角 */
    bar: {
      barMaxWidth: 24,
      itemStyle: { borderRadius: [4, 4, 0, 0] },
      emphasis: { focus: 'series' },
    },
    scatter: {
      symbolSize: 8,
      itemStyle: { borderWidth: 2, borderColor: TOK.surface },
      emphasis: { focus: 'series', scale: 1.3 },
    },
    /* 热力图：标签只在格子里、按填充亮度择色，见 heatLabel */
    heatmap: {
      itemStyle: { borderWidth: 2, borderColor: TOK.surface },   // 2px 表面缝，不描边
      emphasis: { itemStyle: { borderWidth: 2, borderColor: TOK.ink } },
    },

    categoryAxis: {
      axisLine: { show: true, lineStyle: { color: TOK.axis, width: 1 } },
      axisTick: { show: false },
      axisLabel: { color: TOK.ink3, fontSize: 11, hideOverlap: true },
      splitLine: { show: false },
      nameTextStyle: { color: TOK.ink3, fontSize: 11 },
    },
    valueAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: TOK.ink3, fontSize: 11 },
      // 细线分区：实线发丝，一档深于表面，绝不用虚线（虚线读作阈值）
      splitLine: { show: true, lineStyle: { color: TOK.grid, width: 1, type: 'solid' } },
      nameTextStyle: { color: TOK.ink3, fontSize: 11 },
    },

    /* 图例：顶部水平（既有 §6 图表规范），放左侧给右上角的工具箱让位。
       单序列不给图例，标题已说明画的是什么；图例只在 ≥2 序列时出现。 */
    legend: {
      top: 0, left: 0,
      textStyle: { color: TOK.ink2, fontSize: 11 },
      itemWidth: 12, itemHeight: 8, itemGap: 14,
      icon: 'roundRect',
    },

    /* 提示：值在前、序列名在后（读者已经知道是哪条线，要的是数字） */
    tooltip: {
      backgroundColor: 'rgba(255,255,255,.97)',
      borderColor: TOK.axis, borderWidth: 1,
      padding: [7, 10],
      textStyle: { color: TOK.ink, fontSize: 12, fontFamily: FONT },
      extraCssText: 'box-shadow:0 6px 18px rgba(20,30,50,.14);border-radius:4px;'
        + 'font-variant-numeric:tabular-nums',
    },
    axisPointer: {
      lineStyle: { color: TOK.axis, width: 1 },
      crossStyle: { color: TOK.axis, width: 1 },
      shadowStyle: { color: 'rgba(25,118,210,.06)' },
    },

    /* 标注层：阈值线可以虚线（它确实表示阈值），线着色、文字用墨色 */
    markLine: {
      symbol: 'none', silent: true,
      lineStyle: { type: 'dashed', width: 1.5 },
      label: { color: TOK.ink2, fontSize: 11 },
    },
    markArea: { silent: true },

    toolbox: {
      right: 6, top: 0, itemSize: 13,
      iconStyle: { borderColor: TOK.ink3 },
      emphasis: { iconStyle: { borderColor: TOK.accent } },
      /* 这里不放 dataZoom：主题的 toolbox.feature 会与每个图的合并，
         于是每张图都会长出一个点了没反应的缩放按钮。缩放按钮由
         specToOption 在「图确实有缩放轴」时才补。 */
      feature: {
        restore: {},
        saveAsImage: { name: 'gachastat', pixelRatio: 2, backgroundColor: TOK.surface },
      },
    },

    /* 色阶图例：矩阵型的主要版面问题是它的落位，这里交给调用方按需覆写 */
    visualMap: {
      textStyle: { color: TOK.ink3, fontSize: 10 },
      inRange: { color: SEQ },
    },
  };

  echarts.registerTheme('gs', THEME);

  /* ── 工具 ── */

  function isArr(a) { return Array.isArray(a) || ArrayBuffer.isView(a); }
  function arr(a) { return isArr(a) ? Array.prototype.slice.call(a) : []; }

  /* 有效位纪律：不把浮点尾数泄到界面上 */
  function num(v, digits) {
    var n = Number(v);
    if (!isFinite(n)) return String(v);
    var d = digits == null ? 2 : digits;
    var r = Math.round(n * Math.pow(10, d)) / Math.pow(10, d);
    return String(r);
  }
  /* 千分位，用于轴刻度（读者眼里的整洁数字） */
  function comma(v) {
    var n = Number(v);
    if (!isFinite(n)) return String(v);
    var s = String(Math.round(n * 100) / 100).split('.');
    s[0] = s[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return s.join('.');
  }
  /* 轴刻度用：按量级选有效位。密度轴的值可以小到 2e-4，一律走 comma()
     会把整条轴抹成两个「0」（这是实际出过的显示事故）。 */
  function axisNum(v) {
    var n = Number(v);
    if (!isFinite(n)) return String(v);
    if (n === 0) return '0';
    var a = Math.abs(n);
    if (a >= 1000) return comma(n);
    if (a >= 1) return String(Math.round(n * 100) / 100);
    if (a >= 0.01) return String(Math.round(n * 1000) / 1000);
    if (a >= 0.0001) return n.toExponential(1);
    return n.toExponential(0);
  }
  function quantile(sorted, q) {
    if (!sorted.length) return NaN;
    var pos = q * (sorted.length - 1);
    var lo = Math.floor(pos), hi = Math.ceil(pos);
    return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }
  /* ECharts 无自动分箱，与后端 _build_histogram 同语义手算 */
  function binCounts(samples, nbins) {
    if (!samples.length) return { centers: [], counts: [] };
    var lo = Math.min.apply(null, samples), hi = Math.max.apply(null, samples);
    if (hi === lo) return { centers: [lo], counts: [samples.length] };
    var w = (hi - lo) / nbins, counts = new Array(nbins).fill(0), centers = [];
    for (var i = 0; i < nbins; i++) centers.push(lo + (i + 0.5) * w);
    for (var j = 0; j < samples.length; j++) {
      var idx = Math.floor((samples[j] - lo) / w);
      if (idx >= nbins) idx = nbins - 1;
      if (idx < 0) idx = 0;
      counts[idx]++;
    }
    return { centers: centers, counts: counts, width: w, lo: lo, hi: hi };
  }

  /* 栅格与轴名：containLabel 保证轴标签不被裁；top/bottom 留出轴名与工具箱的位置。
     这两处不留白是实际出过的排版事故（工具箱压住曲线、轴名压在刻度上）。 */
  /* 轴范围与比例量格式：比例量的纵轴截断会把「0.9 与 1.0 差不多」读成「差了 10%」，
     所以由 spec 显式声明范围，声明了就按声明画。 */
  function rng(spec, which) {
    var h = spec.layout_hints || {};
    var r = (which === 'x' ? h.x_range : h.y_range) || [];
    return [r[0] == null ? null : r[0], r[1] == null ? null : r[1]];
  }
  function pctAxis(spec) { return !!(spec.layout_hints || {}).y_percent; }

  function gridOf(o) {
    return Object.assign(
      { left: 6, right: 18, top: 22, bottom: 10, containLabel: true }, o || {});
  }
  /* 轴名默认不画：每个结果块的导语已经写明「横轴＝X，纵轴＝Y」（图注体系），
     图里再画一遍是重复，而且轴名与刻度、工具箱、数据标注抢位置。
     要单独看一张图时开 layout_hints.axis_names。
     注意：这个开关只管「轴名」，不管山脊的行名（行名也是 yAxis.name，
     但它是行标签，任何时候都得画）。 */
  function aliasOn(spec) { return !!(spec.layout_hints || {}).axis_names; }
  /* 这两个开关在多处用到，做成 helper 而不是各构造器的局部变量：
     局部变量版本出过一次错，同一个写法在另一个构造器里引用未定义的名字。 */
  function compactOn(spec) { return !!(spec.layout_hints || {}).compact; }
  function sparkOn(spec) { return !!(spec.layout_hints || {}).sparkline; }
  function xName(spec) {
    return {
      name: aliasOn(spec) ? (spec.xlabel || '') : '',
      nameLocation: 'end', nameGap: 9,
      nameTextStyle: { color: TOK.ink3, fontSize: 11, align: 'right',
        verticalAlign: 'top', padding: [4, 0, 0, 0] },
    };
  }
  function yName(spec) {
    return {
      name: aliasOn(spec) ? (spec.ylabel || '') : '',
      nameLocation: 'end', nameGap: 10,
      nameTextStyle: { color: TOK.ink3, fontSize: 11, align: 'left',
        verticalAlign: 'bottom', padding: [0, 0, 2, 0] },
    };
  }

  /* 标注层：annotations → markLine，shaded_regions → markArea ── */
  function markLineOf(spec, axis) {
    var out = [], vi = 0;
    (spec.annotations || []).forEach(function (a) {
      var isV = a.type === 'vline';
      if (axis === 'x' && !isV) return;
      if (axis === 'y' && isV) return;
      /* 两条竖直标注线靠得近时（P50 与 P90 本来就近），标签会叠在一起。
         错开靠垂直 offset，不靠换位置：标注线标签一律贴顶，
         往下的位置是柱子的地盘，标签压上去就没法读了。 */
      var pos = a.label_pos || (isV ? 'insideEndTop' : 'insideEndRight');
      var dy = isV ? (vi % 2) * 15 : 0;
      if (isV) vi++;
      out.push({
        xAxis: isV ? a.value : undefined,
        yAxis: isV ? undefined : a.value,
        lineStyle: { color: a.color || STATUS.danger, type: a.dash || 'dash', width: 1.5 },
        // 文字用墨色：颜色由线本身承载，标签染色会让文字变成数据重量
        label: {
          formatter: a.text || num(a.value),
          color: TOK.ink2, fontSize: 11, position: pos,
          offset: [0, dy],
          rotate: 0,   // 默认会随竖线转 90°，中文竖排既难读又压住着色带
        },
      });
    });
    return out;
  }
  function markAreaOf(spec, axis) {
    var out = [];
    (spec.shaded_regions || []).forEach(function (r) {
      var c = r.color || 'rgba(198,40,40,.10)';
      out.push([
        { xAxis: r.lower, itemStyle: { color: c }, label: label(r) },
        { xAxis: r.upper },
      ]);
      if (axis === 'y') { /* 反向区间也支持：这里只登记用法，横轴区间是主用途 */ }
    });
    return out;
  }
  function label(r) {
    if (!r.label) return { show: false };
    return { show: true, position: 'insideTop', color: TOK.ink2, fontSize: 10, formatter: r.label };
  }

  /* 数据点标注：拐点、阈值点、极值点。型 2 要求「直接标在图上并给出坐标」，
     不让读者去对刻度。 */
  function markPointOf(spec) {
    var pts = (spec.layout_hints || {}).mark_points || [];
    return pts.map(function (p) {
      return {
        coord: [p.x, p.y], symbol: 'circle', symbolSize: 9,
        itemStyle: { color: p.color || TOK.accent, borderColor: TOK.surface, borderWidth: 2 },
        label: {
          show: true, position: p.pos || 'top', distance: 7,
          formatter: p.text || num(p.y), color: TOK.ink2, fontSize: 11,
        },
      };
    });
  }

  /* 把标注层挂到主序列上；没有主序列时由调用方自行处理 */
  function withMarks(series, spec, axis) {
    var ml = markLineOf(spec, axis || 'x');
    var ma = markAreaOf(spec, axis || 'x');
    var mp = markPointOf(spec);
    if (ml.length) series.markLine = { data: ml };
    if (ma.length) series.markArea = { data: ma };
    if (mp.length) series.markPoint = { data: mp, silent: true };
    return series;
  }

  /* ── 各图型 ── */

  function optHistogram(spec) {
    var d = spec.data || {};
    var samples = arr(d.samples);
    var nbins = (spec.layout_hints && spec.layout_hints.nbins) || 30;
    var b = binCounts(samples, nbins);
    var total = samples.length || 1;
    var w = b.width || 1;

    /* density=true 走概率密度（与后端一致），否则频数 */
    var values = b.counts.map(function (c) {
      return d.density === false ? c : c / (total * w);
    });
    var sorted = samples.slice().sort(function (x, y) { return x - y; });
    var marks = [];
    var compact = compactOn(spec);
    /* sparkline：支撑性小图，只要形状不要刻度 */
    var spark = sparkOn(spec);
    if (d.mean_line) {
      var m = samples.reduce(function (a, x) { return a + x; }, 0) / total;
      marks.push({ xAxis: +m.toFixed(2),
        label: compact ? { show: false }
          : { formatter: '均值 ' + comma(Math.round(m)) } });
    }
    (d.quantile_lines || []).forEach(function (q) {
      var qv = quantile(sorted, q);
      marks.push({
        xAxis: +qv.toFixed(2),
        lineStyle: { type: 'dot', color: TOK.ink2 },
        label: compact ? { show: false }
          : { formatter: 'P' + Math.round(q * 100) + ' ' + num(qv) },
      });
    });

    var series = [withMarks({
      type: 'bar',
      data: b.centers.map(function (c, i) { return [c, +values[i].toFixed(6)]; }),
      barWidth: w * 0.82,             // 柱间留白由 2px 表面缝给，不描边
      itemStyle: { color: cat(0), borderRadius: 0 },
      name: spec.ylabel || '密度',
    }, spec)];
    if (marks.length) {
      series[0].markLine = Object.assign({ data: marks }, series[0].markLine || {});
    }
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
        valueFormatter: function (v) { return num(v, 4); } },
      grid: gridOf(),
      xAxis: Object.assign({ type: 'value',
        axisLabel: { show: !spark, formatter: axisNum },
        axisLine: { show: true } }, xName(spec)),
      yAxis: Object.assign({
        type: 'value',
        axisLabel: { show: !spark, formatter: axisNum },
        splitLine: { show: !spark },
        axisLine: { show: false },
      }, yName(spec)),
      series: series,
    };
  }

  function optCdf(spec) {
    var samples = arr((spec.data || {}).samples);
    var sorted = samples.slice().sort(function (a, b) { return a - b; });
    var n = sorted.length || 1;
    var pts = sorted.map(function (x, i) { return [x, +((i + 1) / n).toFixed(5)]; });
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'line' },
        valueFormatter: function (v) { return num(v, 4); } },
      grid: gridOf(),
      xAxis: Object.assign({ type: 'value',
        axisLabel: { show: !sparkOn(spec), formatter: axisNum },
        axisLine: { show: true } }, xName(spec)),
      yAxis: Object.assign({
        type: 'value', min: 0, max: 1,
        axisLabel: { formatter: function (v) { return Math.round(v * 100) + '%'; } },
      }, yName(spec)),
      series: [withMarks({
        type: 'line', data: pts, showSymbol: false, sampling: 'lttb',
        lineStyle: { width: 2, cap: 'round', join: 'round', color: cat(0) },
        areaStyle: { color: cat(0), opacity: 0.10 },   // 一层薄雾，不是实块
        step: (spec.layout_hints || {}).step || false,
        name: spec.ylabel || '累积概率',
      }, spec)],
    };
  }

  /* 山脊：每池一行，多 grid 共享横轴。行本身即选择器（点行选中该池）。 */
  function optRidge(spec) {
    var d = spec.data || {};
    var keys = Object.keys(d.series || {});
    var n = keys.length || 1;
    var nbins = (spec.layout_hints && spec.layout_hints.nbins) || 40;
    var rowH = 100 / n;
    var grid = [], xAxis = [], yAxis = [], series = [];
    keys.forEach(function (k, i) {
      /* 行名列宽 96px：yAxis.show=false 时 containLabel 算不出宽度，
         行名会被推到画布外裁掉（这是实际出过的显示事故）。 */
      grid.push({
        left: 96, right: 14, containLabel: false,
        top: (i * rowH + rowH * 0.10) + '%',
        height: (rowH * 0.74) + '%',
      });
      xAxis.push(Object.assign({
        type: 'value', gridIndex: i,
        axisLabel: { show: i === n - 1, formatter: axisNum },
        axisLine: { show: i === n - 1 },
        splitLine: { show: false },
      }, i === n - 1 ? xName(spec) : { name: '' },
        { nameTextStyle: { padding: [2, 0, 0, 0] } }));
      yAxis.push({
        /* 注意：不能写 show:false，因为 ECharts 在轴隐藏时连轴名一起不画，
           行名会整列消失。改为轴显示、只隐掉轴线与刻度。 */
        type: 'value', gridIndex: i, show: true,
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { show: false }, splitLine: { show: false },
        name: (d.labels && d.labels[k]) || k,
        /* 锚点落在行名列（96px 宽）的中线上：nameGap 是「从轴线往左多少像素」，
           所以 96 - 48 = 48。align:'right' 会把整段字推到锚点左侧从而出画布。 */
        nameLocation: 'middle', nameGap: 48, nameRotate: 0,
        nameTextStyle: { color: TOK.ink2, fontSize: 11, align: 'center',
          verticalAlign: 'middle' },
      });
      var b = binCounts(arr(d.series[k]), nbins);
      var mx = Math.max.apply(null, b.counts.concat([1]));
      var col = (d.colors && d.colors[k]) || cat(0);
      var sel = (spec.layout_hints || {}).selected;
      var dim = sel && sel !== k;
      var marks = [];
      if (d.means && d.means[k] != null) {
        marks.push({ xAxis: +d.means[k].toFixed(2), lineStyle: { type: 'dashed', color: STATUS.danger },
          label: { show: false } });
      }
      if (d.vuln_regions && d.vuln_regions[k]) {
        var rg = d.vuln_regions[k];
        marks.push([
          { xAxis: rg[0], itemStyle: { color: 'rgba(198,40,40,.10)' }, label: { show: false } },
          { xAxis: rg[1] },
        ]);
      }
      var s = {
        type: 'bar', xAxisIndex: i, yAxisIndex: i,
        data: b.centers.map(function (c, j) { return [c, +(b.counts[j] / mx).toFixed(4)]; }),
        barWidth: '86%',
        itemStyle: { color: col, opacity: dim ? 0.32 : 0.88 },
        name: (d.labels && d.labels[k]) || k,
        silent: false,
        emphasis: { itemStyle: { opacity: 1 } },
      };
      if (marks.length) s.markLine = { silent: true, symbol: 'none', data: marks };
      series.push(s);
    });
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (ps) {
          if (!ps.length) return '';
          var p = ps[0];
          return (p.seriesName || '') + '<br>资源剩余 ' + comma(p.value[0])
            + '<br>相对频次 ' + num(p.value[1], 3);
        } },
      /* 不挂 dataZoom。两个理由：
         1) inside 型 dataZoom 会接管整个图表元素上的滚轮，把「滚轮下滑看剩下的池」
            和「滚轮缩放横轴」变成互相打架，实测是两者都没发生（滚轮被整个吞掉）。
            山脊装在一个 overflow-y:auto 的容器里，垂直滚动是它唯一的导航方式。
         2) 山脊的用途是一眼看全所有池的完整区间；缩放横轴恰好破坏这个用途。 */
      grid: grid, xAxis: xAxis, yAxis: yAxis, series: series,
    };
  }

  function optBoxplot(spec) {
    var d = spec.data || {};
    var keys = Object.keys(d.series || {});
    var data = keys.map(function (k) {
      var s = arr(d.series[k]).slice().sort(function (a, b) { return a - b; });
      return [quantile(s, 0), quantile(s, 0.25), quantile(s, 0.5), quantile(s, 0.75), quantile(s, 1)]
        .map(function (v) { return +v.toFixed(3); });
    });
    return {
      tooltip: { trigger: 'item' },
      grid: gridOf(),
      xAxis: Object.assign({ type: 'category', data: keys }, xName(spec)),
      yAxis: Object.assign({ type: 'value', axisLabel: { formatter: axisNum } }, yName(spec)),
      series: [{
        type: 'boxplot', data: data, name: spec.ylabel || '分布',
        /* 箱体的边框与中位线由 borderColor 管；须线的颜色走 lineStyle。
           不显式给就是黑色，在浅色主题里最重的一笔反而是箱线。 */
        itemStyle: { color: 'rgba(25,118,210,.08)', borderColor: cat(0), borderWidth: 1.5 },
        lineStyle: { color: cat(0), width: 1.2 },
      }],
    };
  }

  function optScatter(spec) {
    var d = spec.data || {};
    var hintsS = spec.layout_hints || {};
    var hiddenY = hintsS.hide_y || hintsS.sparkline;
    var traces = d.traces;
    var series = [], legend = false;
    if (traces && traces.length) {
      legend = traces.length >= 2;   // 单序列不给图例：标题已经说明画的是什么
      series = traces.map(function (t, i) {
        var col = t.marker_color || t.line_color || cat(i);
        /* 标注层挂到第一条轨迹上。traces 分支原来漏了这一步，
           于是「硬保底 90」这类竖线和数据点标注整个丢失，页面上毫无提示。 */
        return {
          type: 'line', name: t.name || ('序列 ' + (i + 1)),
          data: arr(t.x).map(function (x, j) { return [x, arr(t.y)[j], (t.customdata || [])[j]]; }),
          /* 数据点该不该画：markers 模式必画；lines 模式点少才画（点多会连成虚线，
             形状反而看不清）；marker_symbol='none' 是显式要求不画。 */
          showSymbol: t.marker_symbol !== 'none'
            && (t.mode === 'markers' || arr(t.x).length <= 24),
          symbol: t.marker_symbol === 'circle' ? 'circle' : (t.marker_symbol || 'circle'),
          symbolSize: t.marker_size || 8,
          lineStyle: t.mode === 'markers' ? { width: 0 }
            : { width: t.line_width || 2, color: col, cap: 'round' },
          itemStyle: { color: col, opacity: t.opacity == null ? 1 : t.opacity,
            borderWidth: 2, borderColor: TOK.surface },
          emphasis: { focus: 'series' },
        };
      });
      if (series.length && (spec.annotations || []).length) {
        series[0] = withMarks(series[0], spec);
      }
    } else {
      var pstyle = (spec.layout_hints || {}).point_styles;
      series = [withMarks({
        type: d.mode === 'lines' ? 'line' : 'scatter',
        data: arr(d.x).map(function (x, i) {
          var base = { value: [x, arr(d.y)[i]] };
          var st = pstyle && pstyle[i];
          if (st) {
            base.symbolSize = st.size || 10;
            base.itemStyle = st.hollow
              ? { color: TOK.surface, borderColor: st.color || cat(0), borderWidth: 2 }
              : { color: st.color || cat(0), borderWidth: 2, borderColor: TOK.surface };
          }
          return base;
        }),
        symbolSize: 8, itemStyle: { color: cat(0), borderWidth: 2, borderColor: TOK.surface },
      }, spec)];
    }
    return {
      /* 散点很密时逐点命中不现实：轴触发给出十字线 + 最近点读数 */
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' },
        valueFormatter: function (v) { return num(v, 4); } },
      legend: legend ? { show: true, top: 0, left: 0 } : { show: false },
      grid: gridOf({ top: legend ? 26 : 22 }),
      xAxis: Object.assign({ type: 'value', scale: !(spec.layout_hints || {}).x_range,
        min: rng(spec, 'x')[0], max: rng(spec, 'x')[1],
        axisLabel: { show: !sparkOn(spec), formatter: axisNum },
        splitLine: { show: !sparkOn(spec) } }, xName(spec)),
      yAxis: Object.assign({ type: 'value', scale: !rng(spec, 'y'),
        min: rng(spec, 'y')[0], max: rng(spec, 'y')[1],
        axisLabel: { show: !hiddenY, formatter: pctAxis(spec) ? function (v) {
          return Math.round(v * 100) + '%'; } : axisNum },
        splitLine: { show: !hiddenY } }, yName(spec)),
      series: series,
    };
  }

  function optBar(spec) {
    var d = spec.data || {};
    var labels = d.labels || [];
    var values = arr(d.values);
    var horiz = d.orientation === 'h';
    /* 分类色只给一条柱：柱长已经编码了量级，再按大小深浅涂一遍是浪费通道。
       需要突出「最差那一项」时走 layout_hints.worst_index，用语义色。 */
    var hintsB = spec.layout_hints || {};
    var worst = hintsB.worst_index;
    /* bar_spans：[[start, end], ...]，end 为 null 时按 [start, end, 画到哪] 处理。
       时间窗口、开放区间这类「有起止的条」用它，不必新加 chart_type。 */
    var spans = hintsB.bar_spans;
    var data = values.map(function (v, i) {
      return {
        value: v,
        itemStyle: worst === i
          ? { color: STATUS.danger, borderRadius: horiz ? [0, 4, 4, 0] : [4, 4, 0, 0] }
          : { color: cat(0), borderRadius: horiz ? [0, 4, 4, 0] : [4, 4, 0, 0] },
      };
    });
    var catAxis = {
      type: 'category', data: labels, inverse: !!hintsB.y_inverse,
      axisLabel: { color: TOK.ink3, fontSize: 11, hideOverlap: true,
        rotate: (!horiz && labels.length > 10) ? 30 : 0 },
    };
    var valAxis = { type: 'value', axisLabel: { formatter: axisNum } };
    /* 分类多时给横轴缩放（几十个池会挤，见 §5.9 的池数规模） */
    var sparkB = !!hintsB.sparkline;
    var zoomed = !horiz && labels.length > 14 && !hintsB.no_zoom && !sparkB;
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
        valueFormatter: function (v) { return comma(v); } },
      grid: gridOf({ bottom: zoomed ? 30 : 18 }),
      xAxis: Object.assign(horiz ? Object.assign({}, valAxis, xName(spec))
                                 : Object.assign({}, catAxis, xName(spec)),
        sparkB ? { axisLabel: { show: false }, axisLine: { show: false } } : {}),
      yAxis: Object.assign(horiz ? Object.assign({}, catAxis, yName(spec))
                                 : Object.assign({}, valAxis, yName(spec)),
        sparkB ? { axisLabel: { show: false }, splitLine: { show: false } } : {}),
      /* 分类多时给横轴缩放。两点：
         1) 缩放靠可见的滑块，滚轮留给页面滚动（zoomOnMouseWheel:'shift' 需要按 Shift）。
            默认的「滚轮即缩放」在会滚动的页面里会静默吃掉滚动，而 inside 型
            没有可见的滑块提示这件事。
         2) 样式写在这里而不是主题里：主题的 dataZoom 会让每张图的工具箱都长出
            一个缩放按钮，包括那些根本没有可缩放轴的图。 */
      dataZoom: zoomed
        ? [{ type: 'inside', xAxisIndex: 0, zoomOnMouseWheel: 'shift',
             moveOnMouseMove: true, throttle: 40 },
           { type: 'slider', xAxisIndex: 0, height: 14, bottom: 2,
             borderColor: TOK.grid, fillerColor: 'rgba(25,118,210,.08)',
             handleStyle: { color: TOK.surface, borderColor: TOK.axis },
             textStyle: { color: TOK.ink3, fontSize: 10 } }]
        : undefined,
      legend: spans ? { show: false } : undefined,
      series: spans ? [
        /* 甘特：一条透明偏移序列 + 一条可见长度序列叠起来，值仍是 длины区间 */
        { type: 'bar', stack: 'span', silent: true,
          data: spans.map(function (r) { return r[0]; }),
          itemStyle: { color: 'transparent' }, barMaxWidth: 22 },
        withMarks({ type: 'bar', stack: 'span', data: spans.map(function (r) {
          var open = r[1] == null;
          return { value: (r[1] == null ? r[2] : r[1]) - r[0],
            itemStyle: { color: open ? 'rgba(25,118,210,.22)' : cat(0),
              borderRadius: 2 } };
        }), barMaxWidth: 22, name: '区间' }, spec),
      ] : [withMarks({ type: 'bar', data: data,
        name: spec.ylabel || '数值', barMaxWidth: 24 }, spec)],
    };
  }

  /* 热力图：色阶图例的落位是矩阵型的主要版面问题，默认竖条贴右。
     matrix 为 null 时直接用 opts.data（3D 降级那条路就是这样喂的）。 */
  function heatOption(matrix, rowLabels, colLabels, opts) {
    opts = opts || {};
    var data = opts.data;
    var lo = Infinity, hi = -Infinity;
    if (!data) {
      data = [];
      for (var r = 0; r < (matrix || []).length; r++) {
        var row = arr(matrix[r]);
        for (var c = 0; c < row.length; c++) {
          var v = Number(row[c]);
          if (!isFinite(v)) continue;
          if (v < lo) lo = v;
          if (v > hi) hi = v;
          data.push([c, r, v]);
        }
      }
    } else {
      data.forEach(function (p) {
        var v = Number(p[2]);
        if (!isFinite(v)) return;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      });
    }
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    if (hi === lo) { hi = lo + 1; }
    /* 极值格直接标数值：颜色深浅只能读个大概，结论要精确到数。
       mark_cells 用来框出「最强/最弱那一对」并说明它为什么是结论。 */
    var cells = data.map(function (d0) { return d0; });
    (opts.markCells || []).forEach(function (mc) {
      cells = cells.map(function (d0) {
        if (d0[0] === mc[0] && d0[1] === mc[1]) {
          return { value: d0, itemStyle: { borderColor: mc[2] || STATUS.danger,
            borderWidth: 2, borderType: 'solid' },
            label: mc[3] ? { show: true, color: TOK.ink, fontSize: 10,
              formatter: num(d0[2], 2) } : { show: false } };
        }
        return d0;
      });
    });
    if (opts.labelExtremes && data.length) {
      var best = data[0], worst = data[0];
      data.forEach(function (d0) {
        if (d0[2] > best[2]) best = d0;
        if (d0[2] < worst[2]) worst = d0;
      });
      [best, worst].forEach(function (t) {
        cells = cells.map(function (d0) {
          var v = d0 && d0.value ? d0.value : d0;
          if (v[0] === t[0] && v[1] === t[1]) {
            return { value: v, label: { show: true, color: TOK.surface,
              fontSize: 10, fontWeight: 600, formatter: num(t[2], 2) } };
          }
          return d0;
        });
      });
    }
    var vm = Object.assign({
      type: 'continuous', min: lo, max: hi,
      calculable: true, orient: 'vertical', right: 4, top: 'middle',
      itemWidth: 12, itemHeight: (opts.h ? Math.max(36, Math.min(120, opts.h * 0.46)) : 96),
      formatter: function (v) { return num(v, 2); },
    }, opts.visualMap || {});
    return {
      tooltip: { trigger: 'item',
        formatter: function (p) {
          return (rowLabels[p.value[1]] || p.value[1]) + ' → '
            + (colLabels[p.value[0]] || p.value[0]) + '<br>'
            + '<b>' + num(p.value[2], 3) + '</b>';
        } },
      grid: gridOf({ right: 62, top: 22, bottom: 8 }),
      xAxis: { type: 'category', data: colLabels, splitArea: { show: false },
        axisLabel: { color: TOK.ink3, fontSize: 11, hideOverlap: true } },
      /* 类别轴默认自下而上，矩阵第 0 行会跑到最下面去。转移矩阵与相关性矩阵
         都要求行序自上而下与数据同序，故 inverse。 */
      yAxis: { type: 'category', data: rowLabels, inverse: true,
        splitArea: { show: false },
        axisLabel: { color: TOK.ink3, fontSize: 11, hideOverlap: true } },
      visualMap: vm,
      series: [{ type: 'heatmap', data: cells, progressive: 0,
        itemStyle: { borderWidth: 2, borderColor: TOK.surface } }],
    };
  }

  function optHeatmap(spec, ctx) {
    var d = spec.data || {};
    var h = spec.layout_hints || {};
    return heatOption(arr(d.matrix), d.row_labels || [], d.col_labels || [], {
      h: ctx && ctx.h, visualMap: h.visual_map,
      markCells: h.mark_cells, labelExtremes: h.label_extremes,
    });
  }

  /* 子图网格：多个矩阵拼一张图，共用行列标签 */
  function optSubplotGrid(spec) {
    var d = spec.data || {};
    var mats = d.matrices || [];
    var titles = d.titles || [];
    var cols = d.cols || 4;
    var rows = Math.ceil(mats.length / cols) || 1;
    var grid = [], xAxis = [], yAxis = [], series = [];
    /* 顶部 26% 留给工具箱与子图标题，底部 18% 留给 x 轴；剩下的按行列均分。
       子图之间横向留 4% 缝，纵向留 6%（子图标题要地方落）。 */
    var TOP = 30, BOTTOM = 16, GAPX = 4, GAPY = 6, RIGHT = 9;
    var cellH = (100 - TOP - BOTTOM - GAPY * (rows - 1)) / rows;
    var cellW = (100 - RIGHT - GAPX * (cols - 1)) / cols;
    mats.forEach(function (m, i) {
      var gr = Math.floor(i / cols), gc = i % cols;
      grid.push({
        left: (gc * (cellW + GAPX)) + '%', width: cellW + '%',
        top: (TOP + gr * (cellH + GAPY)) + '%', height: cellH + '%',
        containLabel: true,
      });
      xAxis.push({ type: 'category', gridIndex: i, data: d.col_labels || [],
        axisLabel: { show: gr === rows - 1, fontSize: 10, hideOverlap: true } });
      yAxis.push({ type: 'category', gridIndex: i, data: d.row_labels || [],
        axisLabel: { show: gc === 0, fontSize: 10, hideOverlap: true } });
      var data = [];
      for (var r = 0; r < m.length; r++) {
        var row = arr(m[r]);
        for (var c = 0; c < row.length; c++) data.push([c, r, Number(row[c])]);
      }
      series.push({ type: 'heatmap', xAxisIndex: i, yAxisIndex: i, data: data,
        progressive: 0, itemStyle: { borderWidth: 2, borderColor: TOK.surface } });
    });
    return {
      tooltip: { trigger: 'item' },
      /* 子图标题是「面板标签」不是「图题」，必须留在图里：4 张矩阵共用一个图注，
         读者得知道哪格是哪一池。用多 title 逐个贴在各子图上方，
         而不是塞进 xAxis.name（那会把标签压到图的下面去）。 */
      title: titles.map(function (t, i) {
        var gc = i % cols, gr = Math.floor(i / cols);
        return {
          show: true, text: t, left: Math.max(0, gc * (cellW + GAPX) - 1.5) + '%',
          top: (TOP + gr * (cellH + GAPY) - 8) + '%',
          textStyle: { color: TOK.ink2, fontSize: 11, fontWeight: 600, fontFamily: FONT },
        };
      }),
      grid: grid, xAxis: xAxis, yAxis: yAxis, series: series,
      visualMap: { type: 'continuous', min: 0, max: 1, calculable: true,
        orient: 'vertical', right: '1%', top: 'middle', itemWidth: 12, itemHeight: 80,
        inRange: { color: SEQ }, textStyle: { color: TOK.ink3, fontSize: 10 } },
    };
  }

  /* 3D 瀑布在 868px 的框里不可读（近柱遮远柱、刻度读不准），默认降级 2D：
     把第三维（计数）编成色阶铺在 x×y 平面上，量级与位置都不丢。 */
  function optWaterfall2D(spec, ctx) {
    var d = spec.data || {};
    var xs = arr(d.x), ys = arr(d.y), zs = arr(d.z);
    var xv = Array.from(new Set(xs)).sort(function (a, b) { return a - b; });
    var yv = Array.from(new Set(ys)).sort(function (a, b) { return a - b; });
    var xi = new Map(xv.map(function (v, i) { return [v, i]; }));
    var yi = new Map(yv.map(function (v, i) { return [v, i]; }));
    var data = zs.map(function (z, k) { return [xi.get(xs[k]), yi.get(ys[k]), z]; });
    return heatOption(null, yv.map(function (v) { return comma(v); }),
      xv.map(function (v) { return comma(v); }), { data: data, h: ctx && ctx.h });
  }

  /* 组合图：多面板共享横轴，只有末面板显示 x 轴（对齐旧 shared_xaxes） */
  function optComposite(spec, ctx) {
    var panels = spec.panels || [];
    var n = panels.length || 1;
    var heights = (spec.layout_hints || {}).row_heights
      || panels.map(function () { return 1 / n; });
    var grid = [], xAxis = [], yAxis = [], series = [], titles = [];
    /* 按像素排版，不用百分比：组合图是「几个面板叠在一个固定高度里」，
       百分比会把面板高度算得随容器漂移，矮容器下面板会压成一条。
       TOP 给工具箱，BOTTOM 给末面板的 x 轴，LABEL_H 是每个面板上方的标签带
       （第 i 个面板的标签若没有自己的带，会压在 i-1 个面板的图上）。 */
    var H = (ctx && ctx.h) || 240;
    var TOP = 22, BOTTOM = 26, LABEL_H = 15;
    var body = Math.max(30, H - TOP - BOTTOM - LABEL_H * n);
    var top = TOP + LABEL_H;
    panels.forEach(function (p, i) {
      var h = heights[i] * body;
      grid.push({ left: 6, right: 18, top: top, height: h, containLabel: true });
      var last = i === n - 1;
      var built = buildPanel(p);
      (built.series || []).forEach(function (s) {
        s.xAxisIndex = i; s.yAxisIndex = i;
        series.push(s);
      });
      xAxis.push(Object.assign({
        gridIndex: i, axisLabel: { show: last, formatter: axisNum },
        axisLine: { show: last }, splitLine: { show: false },
      }, last ? xName(spec) : { name: '' }, built.xAxis));
      yAxis.push(Object.assign({
        gridIndex: i, axisLabel: { show: true, formatter: axisNum },
        splitLine: { show: true },
      }, built.yAxis));
      /* 面板标签用 title 数组贴在各面板上方，与 subplot_grid 同法：
         它是面板标签不是图题，必须留在图里（图注只写一份）。 */
      if (p.title) {
        titles.push({
          show: true, text: p.title, left: 2, top: (top - LABEL_H + 2),
          textStyle: { color: TOK.ink2, fontSize: 11, fontWeight: 600, fontFamily: FONT },
        });
      }
      top += h + LABEL_H;
    });
    var out = {
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      grid: grid, xAxis: xAxis, yAxis: yAxis, series: series,
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
    };
    if (titles.length) out.title = titles;
    return out;
  }

  /* 组合图的子面板复用单图构造，只取轴与序列 */
  function buildPanel(p) {
    var hints = Object.assign({}, p.layout_hints || {}, { compact: true });
    var fake = { chart_type: p.chart_type, data: p.data, title: '',
      xlabel: '', ylabel: '', annotations: p.annotations || [],
      shaded_regions: p.shaded_regions || [], layout_hints: hints };
    var o = specToOption(fake) || {};
    /* 面板标签一律走 title，不走 yAxis.name：两处都画的话标签会叠一遍，
       而且 yAxis.name 的位置在面板内部，会压住自己的 y 轴刻度。 */
    return {
      series: o.series || [],
      xAxis: o.xAxis && o.xAxis.type === 'value' ? { type: 'value' } : {},
      yAxis: o.yAxis ? { type: o.yAxis.type || 'value' } : {},
    };
  }

  /* ── 派发 ── */

  var BUILDERS = {
    histogram: optHistogram,
    cdf: optCdf,
    ridge: optRidge,
    boxplot: optBoxplot,
    scatter: optScatter,
    bar: optBar,
    heatmap: optHeatmap,
    subplot_grid: optSubplotGrid,
    waterfall_3d: optWaterfall2D,
    composite: optComposite,
  };

  /* 表不在图表里渲：表主型（型 5）本来就该是 HTML 表，再塞进 canvas 是把
     可选中、可复制、可读屏的文本降级成像素。返回 null，由调用方走 <table>。 */
  var NOT_A_CHART = { table: true };

  function specToOption(spec, ctx) {
    if (!spec || !spec.chart_type) return null;
    if (NOT_A_CHART[spec.chart_type]) return null;
    var fn = BUILDERS[spec.chart_type];
    if (!fn) {
      console.warn('[gs-charts] 未实现的 chart_type：' + spec.chart_type);
      return null;
    }
    var o = fn(spec, ctx) || {};
    var hints = spec.layout_hints || {};
    /* 图题默认不画（归 HTML 图注），显式开启才画 */
    if (hints.title_in_chart && spec.title) {
      o.title = { show: true, text: spec.title, left: 'left',
        textStyle: { color: TOK.ink, fontSize: 12, fontWeight: 600, fontFamily: FONT } };
    }
    /* 工具箱：§6 图表规范要求默认给「保存图片 / 数据缩放 / 还原」。
       数据缩放只在图确实带缩放轴时才给按钮，否则是个点了没反应的图标。 */
    var tbFeature = { restore: {} };
    if (o.dataZoom) tbFeature.dataZoom = { yAxisIndex: 'none' };
    tbFeature.saveAsImage = { name: 'gachastat', pixelRatio: 2, backgroundColor: TOK.surface };
    o.toolbox = Object.assign({
      right: 4, top: 0, itemSize: 12, feature: tbFeature,
    }, o.toolbox || {});
    return o;
  }

  /* ── 挂载 ── */

  /* SVG 便于 CSS 控字（等宽数字）；元素多时换 canvas，见文件头说明 */
  var RENDERER_BUDGET = 3000;
  function countPoints(option) {
    var n = 0;
    (option.series || []).forEach(function (s) {
      var d = s && s.data;
      n += Array.isArray(d) ? d.length : 0;
      if (s && s.markLine && Array.isArray(s.markLine.data)) n += s.markLine.data.length;
    });
    return n;
  }

  var instances = [];

  /* 山脊把「行」作为选择单位，而柱子的高度是数据本身，行内大量空白点不动。
     所以在 zr 层按 y 坐标定位行：点行内任意位置都算选中该行。 */
  function bindPick(chart, el, spec, onPick) {
    if (!onPick) return;
    chart.off('click');
    if (chart.__gsZrOff) { chart.__gsZrOff(); chart.__gsZrOff = null; }
    if (spec && (spec.layout_hints || {}).pick_rows) {
      var keys = Object.keys(((spec.data || {}).series) || {});
      var nrow = keys.length || 1;
      var handler = function (e) {
        var h = el.clientHeight || 1;
        var i = Math.floor((e.offsetY / h) * nrow);
        if (i < 0) i = 0;
        if (i >= nrow) i = nrow - 1;
        onPick({ seriesIndex: i, seriesName: keys[i], fromRowBand: true });
      };
      chart.getZr().on('click', handler);
      chart.__gsZrOff = function () { chart.getZr().off('click', handler); };
      return;
    }
    chart.on('click', function (p) { onPick(p); });
  }

  function mount(el, spec, opts) {
    opts = opts || {};
    var option = specToOption(spec, { w: el.clientWidth, h: el.clientHeight });
    var chart = echarts.getInstanceByDom(el);
    if (!option) {
      if (chart) { chart.dispose(); }
      return null;
    }
    var renderer = opts.renderer
      || (countPoints(option) > RENDERER_BUDGET ? 'canvas' : 'svg');
    if (chart && chart.__gsRenderer !== renderer) { chart.dispose(); chart = null; }
    if (!chart) {
      chart = echarts.init(el, 'gs', { renderer: renderer });
      chart.__gsRenderer = renderer;
      instances.push(chart);
    }
    chart.setOption(option, { notMerge: true, lazyUpdate: false });
    chart.resize();
    bindPick(chart, el, spec, opts.onPick);
    return chart;
  }

  function resizeAll() { instances.forEach(function (c) { if (!c.isDisposed()) c.resize(); }); }

  /* ── Vue 组件 ──
     <gs-chart :spec="obj" :height="140" @pick="fn"></gs-chart>
     容器高度必须含轴标签带（dataviz 反模式：定高裁掉 x 轴），所以这里用
     显式 height，不用「撑满父容器」。 */
  var GsChart = {
    name: 'GsChart',
    props: {
      spec: { type: Object, default: null },
      height: { type: [Number, String], default: 140 },
      renderer: { type: String, default: '' },
    },
    emits: ['pick', 'ready'],
    data: function () { return { inst: null }; },
    computed: {
      boxStyle: function () {
        var h = typeof this.height === 'number' ? this.height + 'px' : this.height;
        return { width: '100%', height: h };
      },
    },
    mounted: function () {
      this.draw();
      this._ro = new ResizeObserver(this.draw);
      this._ro.observe(this.$el);
    },
    beforeUnmount: function () {
      if (this._ro) this._ro.disconnect();
      if (this.inst && !this.inst.isDisposed()) this.inst.dispose();
      var i = instances.indexOf(this.inst);
      if (i >= 0) instances.splice(i, 1);
    },
    watch: {
      spec: { deep: true, handler: function () { this.draw(); } },
      height: function () { this.$nextTick(this.draw); },
    },
    methods: {
      draw: function () {
        if (!this.$el) return;
        var el = this.$el;
        /* 空态：不画空图框，交给父级给文案 */
        if (!this.spec) {
          if (this.inst && !this.inst.isDisposed()) this.inst.dispose();
          this.inst = null;
          return;
        }
        var self = this;
        var chart = mount(el, this.spec, {
          renderer: this.renderer,
          onPick: function (p) { self.$emit('pick', p); },
        });
        if (chart && chart !== this.inst) {
          this.inst = chart;
          this.$emit('ready', chart);
        }
      },
    },
    template: '<div class="gs-chart" :style="boxStyle"></div>',
  };

  /* ── 导出 ── */
  var GS = {
    TOK: TOK, CAT: CAT, SEQ: SEQ, DIV: DIV, STATUS: STATUS,
    cat: cat, num: num, comma: comma, quantile: quantile,
    specToOption: specToOption, mount: mount, resizeAll: resizeAll,
    GsChart: GsChart,
    install: function (app) { app.component('gs-chart', GsChart); return app; },
    /* 供离线验证：探针断言用得到 */
    _stats: function () {
      return {
        instances: instances.length,
        disposed: instances.filter(function (c) { return c.isDisposed(); }).length,
        renderers: instances.map(function (c) { return c.__gsRenderer; }),
      };
    },
  };
  global.GS = GS;
})(window);
