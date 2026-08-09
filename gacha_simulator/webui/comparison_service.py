"""比较分析服务（多数据集 L1-L4：描述统计 / 随机占优 / 假设检验 / 帕累托前沿）。"""
from __future__ import annotations

import numpy as np

from gacha_simulator.core.result_store import StoredDataset
from gacha_simulator.core.comparison_analyzer import (
    compute_gdr_values_for_datasets, DescriptiveStats,
    compute_dominance_matrix, compute_pvalue_matrix, ParetoFrontier,
)


def _f(v, digits=4):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return '—'
        return f'{float(v):.{digits}f}'
    except (ValueError, TypeError):
        return str(v)


def run_comparison(datasets: list, store, params: dict) -> dict:
    """datasets: StoredDataset dict 列表；params: {gdr, threshold, method, correction, x_gdr, y_gdr}。"""
    try:
        if not datasets or len(datasets) < 1:
            return {'ok': False, 'error': '至少需要一个数据集', 'sections': []}
        gdr_key = params.get('gdr', 'target_achievement')
        threshold = float(params.get('threshold', 1.0))
        method = params.get('method', 'MWU')
        alpha = float(params.get('alpha', 0.05))
        correction = params.get('correction', 'BH')
        ds_objs = [StoredDataset.from_dict(d) for d in datasets]
        target_specs_list = [d.target_specs or {} for d in ds_objs]
        ssr_ids = set(ds_objs[0].ssr_ids or []) if ds_objs else None
        desire = store.desire_weights if store else None
        miss = store.miss_cost_weights if store else None
        cv = store.card_value_weights if store else None

        defn = None
        lower_is_better = False
        try:
            from gacha_simulator.core.gdr import resolve_gdr_definition
            defn = resolve_gdr_definition(gdr_key)
            lower_is_better = defn.lower_is_better if defn else False
        except Exception:
            pass

        values_list, names, _ = compute_gdr_values_for_datasets(
            ds_objs, gdr_key, target_specs_list, threshold,
            desire_weights=desire, miss_cost_weights=miss, card_value_weights=cv,
            ssr_ids=ssr_ids,
        )

        sections = []
        # ── L1 描述统计 ──
        rows = []
        for v, n in zip(values_list, names):
            s = DescriptiveStats.compute(n, gdr_key, v, threshold, lower_is_better)
            rows.append([n, _f(s.mean), _f(s.median), _f(s.std), _f(s.skewness),
                         _f(s.kurtosis), _f(s.var_05), _f(s.cvar_05),
                         f'{s.success_rate:.2%}', _f(s.min_val, 0), _f(s.max_val, 0), str(s.n)])
        sections.append({'key': 'table', 'title': 'L1 描述统计',
                         'headers': ['数据集', '均值', '中位数', '标准差', '偏度', '峰度',
                                     'VaR₀.₀₅', 'CVaR₀.₀₅', '成功率', 'min', 'max', 'N'],
                         'rows': rows})
        # ── L1 分布对比图：PMF 叠加（共享分箱）+ ECDF 叠加（对齐旧 comparison_analysis_panel._render_l1_charts）──
        try:
            from gacha_simulator.core.gdr_binning import compute_bins
            from gacha_simulator.visualization.chart_spec import (
                ChartSpec, HistogramData, HistogramOverlay, ScatterData, ScatterTrace)
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                      '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
            all_vals = np.concatenate([np.asarray(v, dtype=float) for v in values_list])
            br = compute_bins(gdr_key, all_vals, cost_per_draw=None)
            # PMF 叠加：主序列（首数据集）为柱/直方，其余为半透明填充曲线
            overlays = []
            for i in range(1, len(values_list)):
                overlays.append(HistogramOverlay(samples=np.asarray(values_list[i], dtype=float),
                                                 color=colors[i % len(colors)], opacity=0.55, label=names[i]))
            pmf = ChartSpec(chart_type='histogram',
                            data=HistogramData(samples=np.asarray(values_list[0], dtype=float),
                                               mean_line=False, overlays=overlays, density=True),
                            title='L1 分布对比（PMF 叠加）', xlabel=gdr_key, ylabel='概率密度',
                            layout_hints=br.to_layout_hints())
            sections.append({'key': 'chart', 'title': 'L1 分布对比（PMF 叠加）', 'spec': _spec_to_dict(pmf)})
            # ECDF 叠加：每数据集一条累积曲线
            traces = []
            for i, (vals, name) in enumerate(zip(values_list, names)):
                sv = np.sort(np.asarray(vals, dtype=float))
                ye = np.arange(1, len(sv) + 1) / len(sv)
                traces.append(ScatterTrace(x=sv, y=ye, mode='lines', name=name,
                                           marker_size=2, line_color=colors[i % len(colors)]))
            ecdf = ChartSpec(chart_type='scatter', data=ScatterData(traces=traces),
                             title='L1 ECDF 叠加', xlabel=gdr_key, ylabel='累积概率')
            sections.append({'key': 'chart', 'title': 'L1 ECDF 叠加', 'spec': _spec_to_dict(ecdf)})
        except Exception:
            pass
        # ── L2 随机占优（对齐旧 comparison_analysis_panel：FSD/SSD/TSD 三阶循环，
        # rng_seed + order 作为各阶种子；分类矩阵消费三阶双向 p 值）──
        if len(values_list) >= 2:
            try:
                from gacha_simulator.core.comparison_analyzer import classify_dominance
                ordinal = {1: '一阶', 2: '二阶', 3: '三阶'}
                dom_results = {}
                for order, label in [(1, 'FSD'), (2, 'SSD'), (3, 'TSD')]:
                    dom = compute_dominance_matrix(values_list, names, order=order, n_bootstrap=500,
                                                   rng_seed=42 + order, engine='auto',
                                                   lower_is_better=lower_is_better)
                    mtx = dom.get('matrix')
                    if mtx is None:
                        continue
                    str_mtx = [[_f(v, 4) for v in row] for row in np.asarray(mtx, dtype=object)]
                    sections.append({'key': 'table',
                                     'title': f'L2 随机占优 {label}（{ordinal[order]}）p 值矩阵',
                                     'headers': ['数据集'] + names,
                                     'rows': [[names[i]] + str_mtx[i] for i in range(len(names))]})
                    dom_results[order] = dom
                # 阶段 0：分类矩阵（对齐旧 comparison_analysis_panel L564-587：
                # 三阶双向 p 值 → classify_dominance → ≻/≺/×/=/err）
                if len(dom_results) >= 1:
                    n = len(names)
                    classification = [['—'] * n for _ in range(n)]
                    for i in range(n):
                        for j in range(n):
                            if i == j:
                                continue
                            p_ij = {k: dom_results[k]['matrix'][i][j] for k in dom_results if dom_results[k].get('matrix')}
                            p_ji = {k: dom_results[k]['matrix'][j][i] for k in dom_results if dom_results[k].get('matrix')}
                            p_ij_clean = {k: v for k, v in p_ij.items() if v is not None}
                            p_ji_clean = {k: v for k, v in p_ji.items() if v is not None}
                            if not p_ij_clean and not p_ji_clean:
                                classification[i][j] = 'err'
                            else:
                                classification[i][j] = classify_dominance(p_ij_clean, p_ji_clean).label
                    # 符号映射（对齐旧 _render_classification_matrix 的 ≻/≺/×/=）
                    sym_map = {'≻': '≻', '≺': '≺', '×': '×', '=': '=', 'err': 'err', '—': '—'}
                    str_cls = [[sym_map.get(c, c) for c in row] for row in classification]
                    sections.insert(0, {'key': 'table',
                                        'title': 'L2 随机占优分类矩阵（≻=行一阶随机占优列, ≺=列占优行, ×=互不占优, ==等价）',
                                        'headers': ['数据集'] + names,
                                        'rows': [[names[i]] + str_cls[i] for i in range(n)]})
            except Exception:
                pass
        # ── L3 假设检验 ──
        if len(values_list) >= 2:
            try:
                pmat = compute_pvalue_matrix(values_list, names, method=method,
                                             lower_is_better=lower_is_better, alpha=alpha)
                raw = pmat.get('raw_matrix')
                holm = pmat.get('holm_matrix')
                bh = pmat.get('bh_matrix')
                lab = pmat.get('names', names)
                if raw is not None:
                    sel = {'raw': raw, 'Holm': holm, 'BH': bh}.get(correction, bh or raw)
                    str_mtx = [[_f(v, 4) for v in row] for row in np.asarray(sel, dtype=object)]
                    sections.append({'key': 'table',
                                     'title': f'L3 {method} 假设检验（{"BH校正" if correction=="BH" else "Holm校正" if correction=="Holm" else "原始 p"}）',
                                     'headers': ['数据集'] + lab,
                                     'rows': [[lab[i]] + str_mtx[i] for i in range(len(lab))]})
            except Exception:
                pass
        # ── L4 帕累托前沿 ──
        x_key = params.get('x_gdr', 'target_achievement')
        y_key = params.get('y_gdr', 'resource_remaining')
        if len(values_list) >= 2:
            try:
                xv, _, _ = compute_gdr_values_for_datasets(ds_objs, x_key, target_specs_list, threshold,
                                                           desire_weights=desire, miss_cost_weights=miss,
                                                           card_value_weights=cv, ssr_ids=ssr_ids)
                yv, _, _ = compute_gdr_values_for_datasets(ds_objs, y_key, target_specs_list, threshold,
                                                           desire_weights=desire, miss_cost_weights=miss,
                                                           card_value_weights=cv, ssr_ids=ssr_ids)
                pf = ParetoFrontier.compute(xv, yv, names, x_key, y_key,
                                            x_lower_is_better=False, y_lower_is_better=False)
                pts = pf.points
                if pts:
                    rows = [[p['name'], _f(p['x'], 4), _f(p['y'], 4)] for p in pts]
                    sections.append({'key': 'table', 'title': 'L4 帕累托前沿（有效点）',
                                     'headers': ['数据集', f'{x_key}', f'{y_key}'], 'rows': rows})
                    # 散点图
                    from gacha_simulator.visualization.chart_spec import ChartSpec, ScatterData, ScatterTrace
                    traces = []
                    for i, (name_, p) in enumerate(zip(names, pts)):
                        traces.append(ScatterTrace(x=np.array([p['x']]), y=np.array([p['y']]),
                                                   mode='markers', name=name_, marker_size=10))
                    # 加入全部点（非前沿）
                    spec = ChartSpec(chart_type='scatter', data=ScatterData(traces=traces),
                                     title='帕累托前沿', xlabel=x_key, ylabel=y_key)
                    sections.append({'key': 'chart', 'title': '帕累托前沿', 'spec': _spec_to_dict(spec)})
            except Exception:
                pass
        # 供前端 L2 分类矩阵点击 → 对 CDF 可视化（samples/names 透传各数据集原始 GDR 值）
        return {'ok': True, 'sections': sections,
                'names': list(names),
                'samples': [np.asarray(v, dtype=float).tolist() for v in values_list]}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'ok': False, 'error': str(e), 'sections': []}


def _spec_to_dict(spec) -> dict:
    from dataclasses import asdict

    def _clean(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.generic):
            return obj.item()
        if hasattr(obj, '__dataclass_fields__'):
            return _clean(asdict(obj))
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_clean(v) for v in obj]
        return obj

    return _clean(asdict(spec))
