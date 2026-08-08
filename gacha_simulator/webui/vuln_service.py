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
    ChartSpec, ChartAnnotation, HistogramData, RidgeData,
    ScatterData, ScatterTrace,
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
    gdr_key = params.get('gdr', 'resource_remaining')
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

    sections = _build_sections(analysis, alpha)
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


def _build_sections(analysis, alpha) -> list:
    sections = []
    # 总览摘要
    summary_items = {
        '总体失败率': f'{analysis.overall_failure_rate:.2%}',
        'α': f'{analysis.alpha:.2f}',
        'GDR 指标': analysis.gdr_key,
        '模拟数': analysis.n_simulations,
    }
    sections.append({'key': 'summary', 'title': '脆弱性总览', 'items': summary_items})

    # 总览山脊：各池资源分布（脆弱池红、其余蓝）
    series = {}
    labels = {}
    colors = []
    for pr in analysis.pool_results:
        vals = pr.resource_values_all or []
        if len(vals) < 2:
            continue
        series[pr.pool_id] = np.array(vals)
        labels[pr.pool_id] = pr.pool_id
        colors.append('#c62828' if pr.vulnerability_intervals else '#1976d2')
    if series:
        ridge = ChartSpec(chart_type='ridge', data=RidgeData(series=series, labels=labels),
                          title='各池资源剩余分布（脆弱池红色）', xlabel='资源剩余', ylabel='池子',
                          layout_hints={'bin_edges': list(analysis.global_bin_edges)} if analysis.global_bin_edges else {})
        sections.append({'key': 'chart', 'title': '各池资源分布总览', 'spec': _spec_to_dict(ridge)})

    # 每池：直方图 + PAVA 图 + N_j + 区间表
    for pr in analysis.pool_results:
        base = f'池 {pr.pool_id}'
        rows = []
        for vi in pr.vulnerability_intervals:
            rows.append([f'[{vi.lower:.0f}, {vi.upper:.0f}]', f'{vi.mean:.0f}'])
        if rows:
            sections.append({'key': 'table', 'title': f'{base} 脆弱区间',
                             'headers': ['区间', '中心'], 'rows': rows})
        # 直方图（资源分布）——与原 UI plot_vulnerability 一致：全部池共享 global_bin_edges
        #（分箱宽度全局统一，否则各池独立分箱宽度不一致、与原 UI 视觉不同）
        vals = pr.resource_values_all or []
        failed = pr.resource_values_failed or []
        if len(vals) >= 2:
            hist_layout = ({'bin_edges': list(analysis.global_bin_edges)}
                           if analysis.global_bin_edges else {'nbins': 30})
            hist = ChartSpec(
                chart_type='histogram',
                data=HistogramData(samples=np.array(vals), mean_line=True, quantile_lines=None,
                                   overlays=[], density=False)
                if not failed else
                HistogramData(samples=np.array(vals), mean_line=True,
                              overlays=_overlays_from_failed(failed), density=False),
                title=f'{base} 资源分布', xlabel='资源剩余', ylabel='频次',
                layout_hints=hist_layout,
            )
            sections.append({'key': 'chart', 'title': f'{base} 资源分布', 'spec': _spec_to_dict(hist)})
        # PAVA 图
        pava = _pava_chart(pr, alpha)
        if pava is not None:
            sections.append({'key': 'chart', 'title': f'{base} PAVA 推断', 'spec': _spec_to_dict(pava)})
    return sections


def _overlays_from_failed(failed):
    from gacha_simulator.visualization.chart_spec import HistogramOverlay
    return [HistogramOverlay(samples=np.array(failed), color='#c62828', opacity=0.5,
                            label=f'失败样本(n={len(failed)})')]


def _pava_chart(pr, alpha):
    """PAVA 推断图：p̂_j 散点 + θ̃ 台阶 + α 参考线 + 脆弱区间（scatter multi-traces）。"""
    fit = pr.pava_fit
    if fit is None:
        return None
    traces = []
    if fit.get('used_fallback'):
        x = list(fit.get('bin_centers', []))
        y = list(fit.get('theta_per_bin', []))
        if x and y:
            traces.append(ScatterTrace(x=np.array(x), y=np.array(y), mode='lines',
                                      name='θ̃', line_color='darkred', marker_size=2))
    else:
        bc = list(fit.get('bin_centers', []))
        ph = list(fit.get('p_hat', []))
        if bc and ph:
            # 散点（p̂_j）——用多轨迹表达：每点一个 marker 不现实，改为折线+点
            traces.append(ScatterTrace(x=np.array(bc), y=np.array(ph), mode='markers',
                                      name='p̂_j', marker_size=6, marker_color='#888'))
        # PAVA 台阶
        xl = fit.get('x_left', [])
        xr = fit.get('x_right', [])
        tt = fit.get('theta_tilde', [])
        blocks = fit.get('blocks', [])
        if blocks and xl and xr and tt:
            sx, sy = [], []
            for bi, blk in enumerate(blocks):
                if bi < len(tt):
                    sx += [xl[blk[0]], xr[blk[-1]], None]
                    sy += [tt[bi], tt[bi], None]
            if sx:
                traces.append(ScatterTrace(x=np.array([v for v in sx if v is not None]),
                                          y=np.array([v for v in sy if v is not None]),
                                          mode='lines', name='θ̃', line_color='darkred', marker_size=2))
    if not traces:
        return None
    spec = ChartSpec(chart_type='scatter', data=ScatterData(traces=traces),
                     title=f'池 {pr.pool_id} PAVA 推断（α={alpha:.2f}）',
                     xlabel='资源剩余', ylabel='P(失败 | 资源剩余)',
                     annotations=[ChartAnnotation(type='hline', value=alpha, color='gray',
                                                  dash='dash', text=f'α={alpha}')])
    return spec


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
