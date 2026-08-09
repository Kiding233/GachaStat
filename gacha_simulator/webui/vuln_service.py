"""脆弱性分析服务（新 UI 新建模块，参考原 retreat_panel + plan_search_panel 衔接）。

分析：compute_vulnerability_analysis（core/vulnerability.py）→ VulnerabilityAnalysisResult。
绘图：绕过 Plotly（plot_vulnerability 直接返回 go.Figure），从 PoolVulnerabilityResult /
pava_fit 数据构造 ChartSpec（histogram + PAVA 曲线 + N_j 分箱）。
生成配置：RetreatConfigBuilder.build 截断时间线 → save_toml → TOML 文本（前端挂源配置下）。

「生成调整配置」的初始状态参数（对应原方案搜索的能力，不退化）：
- from_pool：带脆弱区间的池（脆弱性结果 pool_id，banner 键）
- base_resource：VI下限/VI均值/VI上限/25%/50%/75%分位/自定义（读 vulnerability_intervals / resource_values_all）
- pity_state：保底水位快照（pity_stats_at_pool_end 的 mean/median/p25/p75）
"""
from __future__ import annotations

import numpy as np

from gacha_simulator.core.vulnerability import compute_vulnerability_analysis
from gacha_simulator.core.retreat_config import RetreatConfigBuilder
from gacha_simulator.visualization.chart_spec import (
    ChartSpec, RidgeData,
)
from gacha_simulator.core.config_toml import save_toml


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


def run_vulnerability_analysis(dataset: dict, store, params: dict) -> dict:
    """脆弱性分析。dataset: StoredDataset dict；store: ConfigStore；params: {gdr, threshold, alpha, nbins}。"""
    aggregate_data = dataset.get('aggregate_data', []) or []
    target_specs = dict(dataset.get('target_specs', {}) or {})
    gdr_key = params.get('gdr', 'target_achievement')   # 对齐旧 retreat_panel populate_gdr_combo index 0
    gdr_threshold = float(params.get('threshold', 1.0))
    alpha = float(params.get('alpha', 0.5))   # 对齐旧 retreat_panel alpha 默认 0.5
    nbins = int(params.get('nbins', 20)) if params.get('nbins') else None
    desire_weights = store.desire_weights if store else None
    miss_cost_weights = store.miss_cost_weights if store else None
    card_value_weights = store.card_value_weights if store else None
    cost_per_draw = _extract_cost_per_draw(store)

    analysis = compute_vulnerability_analysis(
        aggregate_data, target_specs,
        gdr_key=gdr_key, gdr_threshold=gdr_threshold, alpha=alpha, num_bins=nbins,
        desire_weights=desire_weights, miss_cost_weights=miss_cost_weights,
        card_value_weights=card_value_weights, cost_per_draw=cost_per_draw,
        use_draw_units=False,
    )

    # 不抽卡基线（dataset 随模拟结果持久化；对齐旧 retreat_panel no_draw_pool_resources）
    no_draw_pool_resources = dict(dataset.get('no_draw_pool_resources', {}) or {})
    from gacha_simulator.core.gdr import parse_gdr_key
    _, resource_key = parse_gdr_key(gdr_key)

    # 池显示名映射（banner 键 → 中文名；对齐旧 retreat_panel._get_pool_names）
    pool_names = _build_pool_names(store)

    # 资源名（x 轴标题「资源剩余 (XX)」，对齐旧 plot_vulnerability resource_name）
    resource_name = _resource_display_name(store, resource_key)

    sections = _build_sections(analysis, alpha, no_draw_pool_resources,
                               resource_key, pool_names, resource_name)
    pools = _serialize_pools(analysis)
    return {
        'ok': True,
        'result': {
            'overall_failure_rate': analysis.overall_failure_rate,
            'alpha': analysis.alpha,
            'gdr_key': analysis.gdr_key,
            'gdr_threshold': analysis.gdr_threshold,
            'n_simulations': analysis.n_simulations,
            'pools': pools,
        },
        'sections': sections,
        'config_options': _config_options(analysis),
    }


def _extract_cost_per_draw(store) -> float:
    if store is None:
        return 160.0
    for p in store.pools:
        cost = getattr(p, 'cost', None)
        if cost:
            if isinstance(cost, list) and cost:
                for c in cost:
                    if isinstance(c, dict) and 'draw_resource' in c:
                        return float(c['draw_resource'])
                    if hasattr(c, 'get'):
                        val = c.get('draw_resource')
                        if val:
                            return float(val)
            elif hasattr(cost, 'get'):
                val = cost.get('draw_resource')
                if val:
                    return float(val)
    return 160.0


def _build_pool_names(store) -> dict:
    """池 ID → 显示名映射（banner 键；对齐旧 retreat_panel._get_pool_names）。

    store.pools 展平后 pe.name 即 banner 级名、pe.pool_id 为全限定键——
    按 banner 段映射，使 pool_names.get(pr.pool_id) 命中（pr.pool_id 为 banner 键）。
    """
    names = {}
    if store is None:
        return names
    for pe in getattr(store, 'pools', []):
        if not getattr(pe, 'enabled', True):
            continue
        pid = getattr(pe, 'pool_id', '')
        banner_id = pid.split('.')[0] if '.' in pid else pid
        names.setdefault(banner_id, getattr(pe, 'name', pid) or pid)
    return names


def _resource_display_name(store, resource_key: str) -> str:
    """资源显示名（对齐旧 plot_vulnerability resource_name 默认「抽卡资源」）。"""
    if store is not None:
        rd = getattr(store, 'resource_defs', {}) or {}
        if resource_key in rd:
            return rd[resource_key]
    return '抽卡资源'


def _build_sections(analysis, alpha, no_draw_pool_resources=None,
                    resource_key='draw_resource', pool_names=None,
                    resource_name='抽卡资源') -> list:
    pool_names = pool_names or {}
    no_draw_pool_resources = no_draw_pool_resources or {}
    sections = []
    # 总览摘要
    summary_items = {
        '总体失败率': f'{analysis.overall_failure_rate:.1%}',
        'α': f'{analysis.alpha:.2f}',
        'GDR 指标': analysis.gdr_key,
        '模拟数': analysis.n_simulations,
    }
    sections.append({'key': 'summary', 'title': '脆弱性总览', 'items': summary_items})

    # 总览山脊：各池资源分布（对齐旧 plot_vulnerability_ridge——
    # 全池 Viridis 渐变柱 + 均值红虚线 + 不抽卡基线绿点线 + 脆弱区间浅红带 + y 轴池名）
    series = {}
    labels = {}
    means = {}
    vuln_regions = {}
    for pr in analysis.pool_results:
        vals = pr.resource_values_all or []
        if len(vals) < 2:
            continue
        pid = pr.pool_id
        series[pid] = np.array(vals)
        labels[pid] = pool_names.get(pid, pr.pool_id)
        means[pid] = float(np.mean(vals))
        if pr.vulnerability_intervals:
            vuln_regions[pid] = (float(pr.vulnerability_intervals[0].lower),
                                 float(pr.vulnerability_intervals[0].upper))
    if series:
        # 全池 Viridis 渐变（对齐旧 sample_colorscale('Viridis', [i/(n-1)]))；脆弱性靠区间带表达）
        colors = {}
        n = len(series)
        pids = list(series.keys())
        _viridis = _viridis_colors(n)
        for i, pid in enumerate(pids):
            colors[pid] = _viridis[i]
        baselines = {}
        for pid in series:
            pool_res = no_draw_pool_resources.get(pid, {})
            if not isinstance(pool_res, dict):
                # 全限定键兜底（对齐 analysis_service 的 pid.split('.')[0] 做法）
                pool_res = no_draw_pool_resources.get(pid.split('.')[0], {})
            if isinstance(pool_res, dict) and resource_key in pool_res:
                baselines[pid] = float(pool_res[resource_key])
        ridge = ChartSpec(
            chart_type='ridge',
            data=RidgeData(series=series, baselines=baselines, labels=labels,
                           means=means, vuln_regions=vuln_regions, colors=colors),
            title='资源脆弱性总览', xlabel=f'资源剩余 ({resource_name})', ylabel='池子',
            layout_hints={'bin_edges': list(analysis.global_bin_edges)} if analysis.global_bin_edges else {},
        )
        sections.append({'key': 'chart', 'title': '各池资源分布总览', 'spec': _spec_to_dict(ridge)})

    # 每池：单池组合图（3 子图，对齐旧 plot_vulnerability）+ 区间表
    for pr in analysis.pool_results:
        pname = pool_names.get(pr.pool_id, pr.pool_id)
        base = f'池 {pname}'
        rows = []
        for vi in pr.vulnerability_intervals:
            rows.append([f'[{vi.lower:.0f}, {vi.upper:.0f}]', f'{vi.mean:.0f}'])
        if rows:
            sections.append({'key': 'table', 'title': f'{base} 脆弱区间',
                             'headers': ['区间', '中心'], 'rows': rows})
        comp = _composite_pool_chart(pr, alpha, analysis.global_bin_edges,
                                     pname=pname, resource_name=resource_name)
        if comp is not None:
            sections.append({'key': 'chart', 'title': f'{base} 脆弱性分析（PAVA 保序 + 变更点）',
                             'spec': _spec_to_dict(comp)})
    return sections


def _viridis_colors(n):
    """Viridis 渐变取色（对齐旧 plot_vulnerability_ridge sample_colorscale('Viridis', ...)）。"""
    from gacha_simulator.visualization.chart_spec import _VIRIDIS_HEX
    if n <= 1:
        return [_VIRIDIS_HEX[10]]
    idx = [int(round(i / (n - 1) * (len(_VIRIDIS_HEX) - 1))) for i in range(n)]
    return [_VIRIDIS_HEX[i] for i in idx]


def _composite_pool_chart(pr, alpha, global_bin_edges, pname=None, resource_name='抽卡资源'):
    """单池组合图——对齐旧 plot_vulnerability 的 3 子图结构：
    ① 等距直方图（频次 + 均值红虚线）② PAVA 推断（p̂_j 灰点 + θ̃ 台阶 + α 线 + 脆弱区间带）
    ③ 分位数分箱 N_j 分布（柱宽=PAVA 箱宽，色=安全蓝/脆弱红）。
    返回 ChartSpec(chart_type='composite') 或 None（数据不足）。
    """
    if not pr.resource_bins or pr.pava_fit is None:
        return None
    from gacha_simulator.visualization.chart_spec import (
        PanelSpec, PanelCompositeData, ChartSpec, HistogramData,
        ScatterData, ScatterTrace, BarData,
        ChartAnnotation, ShadedRegion,
    )
    bin_edges = np.array(pr.resource_bins, dtype=float)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    samples_all = np.repeat(bin_centers, np.maximum(pr.freq_all, 0).astype(int))
    if len(samples_all) < 2:
        return None
    fit = pr.pava_fit
    is_fallback = bool(fit.get('used_fallback', False) or len(fit.get('theta_per_bin', [])) > 50)
    gbe = np.asarray(global_bin_edges, dtype=float) if global_bin_edges is not None else None

    # ① 直方图（频次，density=False；对齐旧 plot_vulnerability：纯频次柱 + 均值线，无失败样本叠加）
    hist_data = HistogramData(samples=samples_all, mean_line=True, density=False)
    p1 = PanelSpec(chart_type='histogram', data=hist_data, title='频次',
                   layout_hints={'bin_edges': list(gbe)} if gbe is not None
                   else {'bin_edges': list(bin_edges)},
                   show_x_axis=False)

    # ② PAVA 推断
    traces = []
    if is_fallback:
        # 回退路径：PAVA 自身 bin_centers 连线（对齐旧 plot_vulnerability L1059-1067）
        traces.append(ScatterTrace(x=np.array(fit['bin_centers']),
                                   y=np.array(fit['theta_per_bin']), mode='lines',
                                   name='θ̃', line_color='darkred', line_width=2.5))
    else:
        N_j = np.asarray(fit['N_j'], dtype=float)
        N_max = float(N_j.max()) if len(N_j) else 1.0
        sizes = [max(4.0, 20.0 * nj / N_max) for nj in N_j]
        traces.append(ScatterTrace(
            x=np.array(fit['bin_centers']), y=np.array(fit['p_hat']), mode='markers',
            name='p̂_j', marker_color='#888', marker_sizes=sizes,
            opacity=0.6, customdata=[int(n) for n in N_j],
        ))
        xl = np.asarray(fit['x_left'])
        xr = np.asarray(fit['x_right'])
        for bi, blk in enumerate(fit['blocks']):
            if bi < len(fit['theta_tilde']):
                traces.append(ScatterTrace(
                    x=np.array([float(xl[blk[0]]), float(xr[blk[-1]])]),
                    y=np.array([float(fit['theta_tilde'][bi]), float(fit['theta_tilde'][bi])]),
                    mode='lines', name='θ̃', line_color='darkred', line_width=2.5,
                ))
    pava_annotations = [ChartAnnotation(type='hline', value=alpha, color='gray',
                                        dash='dash', text=f'α={alpha}')]
    pava_regions = [ShadedRegion(lower=vi.lower, upper=vi.upper,
                                 color='rgba(200,50,50,0.15)',
                                 label=f'脆弱区间 [{vi.lower:.0f}, {vi.upper:.0f}]')
                    for vi in pr.vulnerability_intervals]
    p2 = PanelSpec(chart_type='scatter', data=ScatterData(traces=traces), title='P(失败 | 资源剩余)',
                   annotations=pava_annotations, shaded_regions=pava_regions, show_x_axis=False)

    # ③ N_j 分位数分箱分布
    p3 = None
    if not is_fallback:
        xl = np.asarray(fit['x_left'])
        xr = np.asarray(fit['x_right'])
        centers = ((xl + xr) / 2).tolist()
        widths = (xr - xl).tolist()
        N_j = np.asarray(fit['N_j'], dtype=float)
        colors = []
        for j in range(len(fit['theta_per_bin'])):
            colors.append('rgba(220,50,50,0.6)' if fit['theta_per_bin'][j] > alpha
                          else 'rgba(31,119,180,0.5)')
        p3 = PanelSpec(chart_type='bar', data=BarData(labels=[], values=N_j, orientation='v'),
                       title='N_j',
                       layout_hints={'bar_centers': centers,
                                     'bar_widths': widths,
                                     'bar_colors': colors}, show_x_axis=True)

    panels = [p1, p2] + ([p3] if p3 else [])
    comp = ChartSpec(
        chart_type='composite',
        data=PanelCompositeData(panels=panels, xlabel=f'资源剩余 ({resource_name})',
                                row_heights=[0.4, 0.35, 0.25]),
        title=pname or pr.pool_id,
    )
    return comp


def _serialize_pools(analysis) -> list:
    out = []
    for pr in analysis.pool_results:
        out.append({
            'pool_id': pr.pool_id,
            'n_total': pr.n_total, 'n_failed': pr.n_failed,
            'failure_rate': pr.failure_rate,
            'vulnerability_intervals': [
                {'lower': vi.lower, 'upper': vi.upper, 'mean': vi.mean} for vi in pr.vulnerability_intervals
            ],
            'resource_mean_all': pr.resource_mean_all,
            'resource_mean_failed': pr.resource_mean_failed,
            'resource_values_all': pr.resource_values_all,
            'pity_stats': {
                cname: {'mean': s.mean, 'median': s.median, 'p25': s.p25, 'p75': s.p75}
                for cname, s in pr.pity_stats_at_pool_end.items()
            },
        })
    return out


def _config_options(analysis) -> dict:
    """供前端「生成调整配置」的初始状态选项（对齐原方案搜索的资源预设/保底水位）。"""
    from_pools = []
    for pr in analysis.pool_results:
        if pr.vulnerability_intervals:
            from_pools.append({
                'pool_id': pr.pool_id,
                'vi_lower': pr.vulnerability_intervals[0].lower,
                'vi_mean': pr.vulnerability_intervals[0].mean,
                'vi_upper': pr.vulnerability_intervals[0].upper,
                'resource_mean': pr.resource_mean_all,
                'percentiles': {
                    'p25': float(np.percentile(pr.resource_values_all, 25)) if pr.resource_values_all else 0,
                    'p50': float(np.percentile(pr.resource_values_all, 50)) if pr.resource_values_all else 0,
                    'p75': float(np.percentile(pr.resource_values_all, 75)) if pr.resource_values_all else 0,
                },
                'pity_stats': {
                    cname: {'mean': s.mean, 'median': s.median, 'p25': s.p25, 'p75': s.p75}
                    for cname, s in pr.pity_stats_at_pool_end.items()
                },
            })
    return {'from_pools': from_pools}


def generate_retreat_config(store, params: dict) -> dict:
    """生成调整配置（截断时间线）→ TOML 文本。

    params: {from_pool, base_resource, base_custom, pity_state}
    base_resource: p50/mean/p25/p75/custom
    pity_state: none/mean/median/p25/p75（决定 pity_counter_init）
    """
    from_pool_id = params.get('from_pool', '')
    if not from_pool_id or from_pool_id == '_root':
        return {'ok': False, 'error': '需选择起始池（脆弱性分析产生的脆弱区间池）'}
    base_res = _resolve_base_resource(params)
    pity_init = _resolve_pity_init(params)
    try:
        truncated = RetreatConfigBuilder.build(
            store, from_pool_id,
            initial_resources={'draw_resource': base_res},
            pity_counter_init=pity_init,
        )
        # 序列化为 TOML 文本（前端保存为新配置节点）
        import tempfile
        import os
        fd, path = tempfile.mkstemp(suffix='.toml')
        try:
            os.close(fd)
            save_toml(truncated, path)
            with open(path, encoding='utf-8') as f:
                text = f.read()
            os.remove(path)
            return {'ok': True, 'config_text': text,
                    'meta': {'from_pool': from_pool_id, 'base_resource': base_res, 'pity_init': pity_init}}
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'ok': False, 'error': str(e)}


def _resolve_base_resource(params: dict) -> float:
    """对齐原方案搜索 _get_selected_resource 逻辑。"""
    mode = params.get('base_resource', 'p50')
    custom = params.get('base_custom', '')
    # 若前端传了具体数值（从 config_options 直接取值），直接返回
    if isinstance(mode, (int, float)):
        return float(mode)
    # 若 mode 是 'custom' 用自定义文本
    if mode == 'custom':
        try:
            return float(custom)
        except (ValueError, TypeError):
            return 0.0
    # 否则需要 config_options 提供的具体值——由前端解析后传入具体数值
    # 这里保守回退 0（前端应传数值）
    return 0.0


def _resolve_pity_init(params: dict) -> dict:
    mode = params.get('pity_state', 'none')
    if mode == 'none':
        return {}
    # 前端应传 pity_stats 具体表 {counter: init_value}
    raw = params.get('pity_stats', {}) or {}
    if not raw:
        return {}
    if mode == 'mean':
        return {k: int(round(v.get('mean', 0))) for k, v in raw.items()}
    if mode == 'median':
        return {k: int(round(v.get('median', 0))) for k, v in raw.items()}
    if mode == 'p25':
        return {k: int(round(v.get('p25', 0))) for k, v in raw.items()}
    if mode == 'p75':
        return {k: int(round(v.get('p75', 0))) for k, v in raw.items()}
    return {}
