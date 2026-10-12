/* ============================================================
   敏感性扫描 · 三行子图渲染器（两案共享）
   ------------------------------------------------------------
   配色与语法取自项目既有图表语言，不新造：
     · 模板      plotly_white（visualization/plotly_charts.py:85 等 4 处 template=）
     · 数据色    #1f77b4（vulnerability.py:1042 的 marker_color）
     · 区间色    darkred ＋ rgba(200,50,50,0.15)
                 （vulnerability.py:1090 / :1105 的 vrect 与线色）
     · 正/负语义 #2e7d32 与 #c62828（gui/ 中的 ok / danger）
     · 文字      #333 / #666 / #888（vulnerability.py:980 的 title_font）
   行的语义沿用 plot_vulnerability 的 rows=3 语法：
     ① 响应值分布 → ② 响应曲线＋同时带 → ③ 每点 CI 宽度
   ============================================================ */
(function (global) {
  'use strict';

  var C = {
    data: '#1f77b4',            // 曲线、直方图
    dataFill: 'rgba(31,119,180,0.45)',
    band: 'rgba(31,119,180,0.18)',   // 同时置信带填充
    bandEdge: '#7fb0d8',             // 带的上/下缘
    interval: 'rgba(200,50,50,0.15)',// 说不准地带（同 vrect）
    intervalLine: 'darkred',         // 翻转点标记
    hold: '#e8f5e9',                 // 结论成立域（ok 语义）
    rule: '#666',                    // τ 判据线
    grid: '#EAEAEA',
    txt: '#333', txt2: '#666', txt3: '#888'
  };
  global.CHART3_COLORS = C;

  /* opt: {w,h,th0,th1,tau,series:[{th,s}],half:[],hist:[{v,c}],ciw:[],
           flip:[lo,hi],crossX,tauPos,tauPct,ticks:[],xlabel,sTop,sBot} */
  global.drawChart3 = function (host, opt) {
    var W = opt.w, H = opt.h, L = 62, R = 18, T = 16, B = 24;
    var rows = [0.40, 0.35, 0.25], gap = 20;
    var innerH = H - T - B - gap * 2;
    var rh = rows.map(function (r) { return innerH * r; });
    var plotW = W - L - R;

    var th0 = opt.th0, th1 = opt.th1, tau = opt.tau;
    var sTop = opt.sTop, sBot = opt.sBot;

    function X(th) { return L + (th - th0) / (th1 - th0) * plotW; }
    function rowTop(i) {
      var y = T;
      for (var k = 0; k < i; k++) y += rh[k] + gap;
      return y;
    }
    function yRow(i, v) {                    // v 为 [0,1] 归一化后的响应
      return rowTop(i) + rh[i] * (1 - v) * 0.86 + rh[i] * 0.07;
    }
    function N(v) { return (v - sBot) / (sTop - sBot); }
    function f(n) { return n.toFixed(1); }

    var g = [];
    var poly = function (a) {
      return a.map(function (p) { return f(p[0]) + ',' + f(p[1]); }).join(' ');
    };

    /* ---- 行① 响应值分布（同一批样本的那一份分布） ---- */
    var hist = opt.hist;
    var maxC = Math.max.apply(null, hist.map(function (h) { return h.c; }));
    var bw = plotW / hist.length;
    hist.forEach(function (h, i) {
      var x = L + i * bw + 0.5;
      var yv = yRow(0, h.c / maxC * 0.92);
      g.push('<rect x="' + f(x) + '" y="' + f(yv) + '" width="' + f(bw - 1) +
        '" height="' + f(yRow(0, 0) - yv) + '" fill="' + C.dataFill +
        '" stroke="' + C.data + '" stroke-width=".5"/>');
    });
    // 行① 的横轴是**响应值**（s），不是 θ。判据线 τ 在这一轴上的位置
    // 才是「切在第几分位」的含义；早先把分数当 θ 传给 X()，算到画布外。
    var xTau = L + (tau - sBot) / (sTop - sBot) * plotW;
    g.push('<line x1="' + f(xTau) + '" y1="' + f(rowTop(0)) + '" x2="' + f(xTau) +
      '" y2="' + f(yRow(0, 0)) + '" stroke="' + C.intervalLine +
      '" stroke-width="1.2" stroke-dasharray="4 3"/>');
    var tx = xTau + 4;
    var anchor = 'start';
    if (xTau > L + plotW * 0.62) { tx = xTau - 4; anchor = 'end'; }
    g.push('<text x="' + f(tx) + '" y="' + f(rowTop(0) + 9) +
      '" font-size="9" fill="' + C.txt2 + '" text-anchor="' + anchor +
      '">τ = ' + tau + '，切在第 ' + opt.tauPct + ' 分位</text>');
    g.push('<text x="' + L + '" y="' + f(rowTop(0) - 5) + '" font-size="10" fill="' +
      C.txt2 + '">① 响应值分布（本批样本）</text>');
    g.push('<text x="' + (L - 6) + '" y="' + f(yRow(0, 1)) +
      '" font-size="9" fill="' + C.txt3 + '" text-anchor="end">频次</text>');

    /* ---- 行② 主图 ---- */
    var bandTop = opt.series.map(function (p, i) {
      return [X(p.th), yRow(1, N(p.s + opt.half[i]))];
    });
    var bandBot = opt.series.map(function (p, i) {
      return [X(p.th), yRow(1, N(p.s - opt.half[i]))];
    });
    var pts = opt.series.map(function (p) { return [X(p.th), yRow(1, N(p.s))]; });

    var yTop = yRow(1, 1) - 4, yBot = yRow(1, 0);
    // 结论成立域（s 高于 τ 的一段）
    g.push('<rect x="' + f(L) + '" y="' + f(yTop) + '" width="' + f(opt.crossX - L) +
      '" height="' + f(yBot - yTop) + '" fill="' + C.hold + '" opacity=".9"/>');
    // 说不准地带
    g.push('<rect x="' + f(X(opt.flip[0])) + '" y="' + f(yTop) + '" width="' +
      f(X(opt.flip[1]) - X(opt.flip[0])) + '" height="' + f(yBot - yTop) +
      '" fill="' + C.interval + '"/>');
    // 同时置信带
    g.push('<polygon points="' + poly(bandTop) + ' ' +
      poly(bandBot.slice().reverse()) + '" fill="' + C.band + '" stroke="none"/>');
    g.push('<polyline points="' + poly(bandTop) + '" fill="none" stroke="' +
      C.bandEdge + '" stroke-width="1"/>');
    g.push('<polyline points="' + poly(bandBot) + '" fill="none" stroke="' +
      C.bandEdge + '" stroke-width="1"/>');
    // 响应曲线
    g.push('<polyline points="' + poly(pts) + '" fill="none" stroke="' + C.data +
      '" stroke-width="1.8"/>');

    // τ 判据线
    var yTau = yRow(1, N(tau));
    g.push('<line x1="' + f(L) + '" y1="' + f(yTau) + '" x2="' + f(L + plotW) +
      '" y2="' + f(yTau) + '" stroke="' + C.rule +
      '" stroke-width="1.4" stroke-dasharray="6 3"/>');
    g.push('<text x="' + f(L + plotW - 2) + '" y="' + f(yTau - 4) +
      '" font-size="10" fill="' + C.txt2 + '" text-anchor="end">τ = ' + tau + '</text>');

    // 翻转点
    g.push('<line x1="' + f(opt.crossX) + '" y1="' + f(yTop) + '" x2="' +
      f(opt.crossX) + '" y2="' + f(yBot) + '" stroke="' + C.intervalLine +
      '" stroke-width="1.4"/>');
    g.push('<circle cx="' + f(opt.crossX) + '" cy="' + f(yTau) +
      '" r="3.4" fill="' + C.intervalLine + '"/>');
    g.push('<text x="' + L + '" y="' + f(rowTop(1) - 5) + '" font-size="10" fill="' +
      C.txt2 + '">② 响应曲线 ＋ 同时置信带</text>');
    g.push('<text x="' + (L - 6) + '" y="' + f(yRow(1, 1)) +
      '" font-size="9" fill="' + C.txt3 + '" text-anchor="end">' +
      (opt.ylabel || '成功率') + '</text>');

    /* ---- 行③ 每点 CI 宽度 ----
       柱子必须坐在自己那个 θ 上，与行②的采样点、底部刻度同一根竖线。
       早先按 plotW/n 等分铺开，5 个点时整排右移了半格（刻度在 62/262/462…，
       柱子却在 86/246/406…），与刻度对不上。 */
    var ciw = opt.ciw;
    var maxW = Math.max.apply(null, ciw);
    var npts = opt.series.length;
    var stepX = npts > 1 ? (X(opt.series[1].th) - X(opt.series[0].th)) : plotW;
    var bwid = Math.max(8, Math.min(stepX * 0.55, 64));
    opt.series.forEach(function (p, i) {
      var h = (ciw[i] / maxW) * 0.7;
      var x = X(p.th) - bwid / 2;
      g.push('<rect x="' + f(x) + '" y="' + f(yRow(2, h)) + '" width="' +
        f(bwid) + '" height="' + f(yRow(2, 0) - yRow(2, h)) +
        '" fill="rgba(31,119,180,0.30)" stroke="' + C.data + '" stroke-width=".5"/>');
    });
    g.push('<text x="' + L + '" y="' + f(rowTop(2) - 5) + '" font-size="10" fill="' +
      C.txt2 + '">③ 每点 CI 宽度</text>');

    /* ---- 共用 x 轴 ---- */
    opt.ticks.forEach(function (t) {
      g.push('<line x1="' + f(X(t)) + '" y1="' + f(yRow(2, 0)) + '" x2="' + f(X(t)) +
        '" y2="' + f(yRow(2, 0) + 4) + '" stroke="' + C.txt3 + '"/>');
      g.push('<text x="' + f(X(t)) + '" y="' + f(yRow(2, 0) + 15) +
        '" font-size="10" fill="' + C.txt2 + '" text-anchor="middle">' + t + '</text>');
    });
    g.push('<text x="' + f(L + plotW / 2) + '" y="' + f(H - 2) +
      '" font-size="10" fill="' + C.txt2 + '" text-anchor="middle">' +
      opt.xlabel + '</text>');

    host.innerHTML = '<svg width="100%" height="' + H + '" viewBox="0 0 ' + W + ' ' + H +
      '" preserveAspectRatio="xMidYMid meet" style="display:block;background:#fff;' +
      'border:1px solid #e3e6eb;border-radius:4px">' + g.join('') + '</svg>';
  };

  /* ---- 复算侧示例数据：扫 GDR 阈值 0.75 → 0.95 ---- */
  global.demoDataRecompute = function () {
    var th0 = 0.75, th1 = 0.95, series = [], half = [], ciw = [], W = 880;
    for (var i = 0; i < 11; i++) {
      var th = th0 + (th1 - th0) * i / 10, t = i / 10;
      var s = 0.955 - 0.693 / (1 + Math.exp(-(t - 0.55) * 9));
      series.push({ th: +th.toFixed(3), s: +s.toFixed(4) });
      half.push(0.060 + 0.030 * Math.abs(t - 0.5) * 2);
      ciw.push(0.032 + 0.026 * Math.abs(t - 0.5) * 2);
    }
    var hist = [];
    for (var j = 0; j < 14; j++) {
      var v = 0.15 + j * 0.06;
      hist.push({ v: +v.toFixed(2), c: Math.exp(-Math.pow((v - 0.55) / 0.26, 2)) * 100 });
    }
    return {
      w: W, h: 380, th0: th0, th1: th1, tau: 0.60, series: series, half: half,
      hist: hist, ciw: ciw, tauPct: 62,
      flip: [0.878, 0.893],
      crossX: 62 + (0.885 - th0) / (th1 - th0) * (W - 62 - 18),
      sTop: 1.0, sBot: 0.0,
      ticks: [0.75, 0.80, 0.85, 0.90, 0.95], xlabel: 'θ　GDR 阈值'
    };
  };

  /* ---- 派发侧示例数据：扫保底阈值 70 → 90 ---- */
  global.demoDataDispatch = function () {
    var th0 = 70, th1 = 90, series = [], half = [], W = 880;
    for (var i = 0; i < 5; i++) {
      var th = th0 + (th1 - th0) * i / 4, t = i / 4;
      var s = 0.30 + 0.58 / (1 + Math.exp(-(t - 0.5) * 7));
      series.push({ th: +th.toFixed(1), s: +s.toFixed(4) });
      half.push(0.085);
    }
    var hist = [];
    for (var j = 0; j < 12; j++) {
      var v = 0.2 + j * 0.05;
      hist.push({ v: +v.toFixed(2), c: Math.exp(-Math.pow((v - 0.55) / 0.3, 2)) * 100 });
    }
    return {
      w: W, h: 380, th0: th0, th1: th1, tau: 0.60, series: series, half: half,
      hist: hist, ciw: [0.075, 0.068, 0.062, 0.068, 0.075], tauPct: 58,
      flip: [80.5, 83.5],
      crossX: 62 + (82 - th0) / (th1 - th0) * (W - 62 - 18),
      sTop: 1.0, sBot: 0.0,
      ticks: [70, 75, 80, 85, 90], xlabel: 'θ　保底 threshold（抽）'
    };
  };
})(window);
