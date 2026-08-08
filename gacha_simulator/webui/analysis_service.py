"""统计分析服务——从 StoredDataset 数据计算各分析方法，产出 ChartSpec + 表格。

移植旧 gui/analysis_panel.py 的 AnalysisWorker._run_impl 核心逻辑（15 步分支），
但不依赖 Qt：输入 dataset dict（StoredDataset.to_dict，全 JSON 可序列化），
调 core 函数（make_gdr_calculator / EmpiricalDistribution / compute_bins /
per_pool_analysis / compute_transition_* / wilson_ci），输出统一 sections 结构，
ChartSpec 经 spec_to_dict 转纯 dict 供前端渲染。

sections 结构（前端 ResultChart 按 key 渲染）：
  [{'key': 'summary', 'title': str, 'items': {k: v}},
   {'key': 'chart',   'title': str, 'spec': ChartSpec dict},
   {'key': 'table',   'title': str, 'headers': [...], 'rows': [[...]]},
   {'key': 'gauge',   'title': str, 'value': float, 'desc': str}]
"""
from __future__ import annotations

import numpy as np

from gacha_simulator.core.gdr import (
    make_gdr_calculator, resolve_gdr_definition, is_resource_gdr, parse_gdr_key,
    compute_gdr_from_cumulative, GDRContext,
)
from gacha_simulator.core.gdr_binning import compute_bins
from gacha_simulator.core.distribution import EmpiricalDistribution, JointSamples
from gacha_simulator.core.per_pool_analysis import (
    PoolSnapshot, per_pool_summary_stats,
    compute_transition_matrices_from_flags, compute_transition_flags_from_gdr,
)
from gacha_simulator.core.process_analysis import wilson_ci
from gacha_simulator.visualization.chart_spec import (
    ChartSpec, ChartAnnotation, HistogramData, HistogramOverlay, CDFData,
    RidgeData, ScatterData, ScatterTrace, BarData, HeatmapData,
    Waterfall3DData, SubplotGridData,
)


def _spec_to_dict(spec) -> dict:
    """ChartSpec → 纯 dict（供 JSON 序列化）。"""
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


def _sec_chart(title, spec):
    return {'key': 'chart', 'title': title, 'spec': _spec_to_dict(spec)}


def _sec_table(title, headers, rows):
    return {'key': 'table', 'title': title, 'headers': headers, 'rows': rows}


def _sec_summary(title, items):
    return {'key': 'summary', 'title': title, 'items': items}


class AnalysisService:
    """单数据集统计分析服务。"""

    def __init__(self, dataset: dict, store=None):
        self.dataset = dataset
        self.store = store                       # ConfigStore（权重来源，可 None）
        self.aggregate_data = dataset.get('aggregate_data', []) or []
        self.target_specs = dict(dataset.get('target_specs', {}) or {})
        self.ssr_ids = set(dataset.get('ssr_ids', []) or [])
        self.gdr_context = None
        if dataset.get('gdr_context'):
            try:
                self.gdr_context = GDRContext.from_dict(dataset['gdr_context'])
            except Exception:
                self.gdr_context = None
        self.pool_end_times = dict(dataset.get('pool_end_times', {}) or {})
        self.draw_sequences = dataset.get('draw_sequences', []) or []
        self.heatmap_data = dataset.get('heatmap_data', {}) or {}
        self.cumulative_snapshots = dataset.get('cumulative_snapshots', {}) or {}
        self.transition_flags = dataset.get('transition_flags', []) or []
        self.no_draw_resource = dataset.get('no_draw_resource')
        self.no_draw_resources = dict(dataset.get('no_draw_resources', {}) or {})
        self.no_draw_pool_resources = dict(dataset.get('no_draw_pool_resources', {}) or {})
        self.initial_resources = dict(dataset.get('initial_resources', {}) or {})
        self.use_draw_units = False
        self.cost_per_draw = 160
        self.alpha = 0.05
        self._store = store
        # 目标卡集合（全限定键池 ID 显示名映射占位——新 UI 无显式池名表）
        self.pool_names = {}

    # ── 数据准备 ──────────────────────────────────────────────────────

    def _calc_gdr(self, gdr_key):
        """构造单指标计算器。"""
        weights_ok = True
        try:
            return make_gdr_calculator(self.store, self.target_specs, gdr_key,
                                       gdr_threshold=None, ssr_ids=self.ssr_ids), weights_ok
        except Exception:
            # store 缺失/权重问题 → 退化无权重计算（直接构造 GDRCalculator 传空权重，
            # 避免 make_gdr_calculator 对 store=None 解引用抛 AttributeError 在 try 外崩溃）
            from gacha_simulator.core.gdr import GDRCalculator
            return GDRCalculator(self.target_specs, gdr_key=gdr_key,
                                 gdr_threshold=None, ssr_ids=self.ssr_ids,
                                 desire_weights={}, miss_cost_weights={},
                                 card_value_weights={}), False

    def _gdr_values(self, gdr_key, aggregate_data=None):
        agg = aggregate_data if aggregate_data is not None else self.aggregate_data
        calc, _ = self._calc_gdr(gdr_key)
        return [calc.compute_gdr(r) for r in agg if r]

    def _compute_all_gdr_dists(self):
        """计算全部 GDR 的 EmpiricalDistribution（对齐 _prepare_gdr_dists）。"""
        from gacha_simulator.core.gdr import get_expanded_gdr_entries
        out = {}
        try:
            entries = get_expanded_gdr_entries(self.store.resource_defs if self.store else None)
        except Exception:
            entries = []
        for key, display, lower_is_better, _thr in entries:
            try:
                vals = self._gdr_values(key)
                out[key] = EmpiricalDistribution(vals)
            except Exception:
                pass
        if not out:
            # 兜底：至少 target_achievement / resource_remaining
            for key in ('target_achievement', 'resource_remaining'):
                try:
                    vals = self._gdr_values(key)
                    out[key] = EmpiricalDistribution(vals)
                except Exception:
                    pass
        return out

    def _unique_count(self, samples):
        return len(set(samples))

    # ── 分发 ─────────────────────────────────────────────────────────

    def run(self, method: str, params: dict = None) -> dict:
        params = params or {}
        handlers = {
            'gdr_dist': self._gdr_dist,
            'gdr_statistics': self._gdr_statistics,
            'correlation': self._correlation,
            'success_rate': self._success_rate,
            'risk_var_cvar': self._risk_var_cvar,
            'risk_worst_case': self._risk_worst_case,
            'risk_best_case': self._risk_best_case,
            'conditional_dist': self._conditional_dist,
            'time_series': self._time_series,
            'time_heatmap': self._time_heatmap,
            'waterfall_3d': self._waterfall_3d,
            'waterfall_2d': self._waterfall_2d,
            'draws_vs_gdr': self._draws_vs_gdr,
            'per_pool_draws': self._per_pool_draws,
            'per_pool_target_rate': self._per_pool_target_rate,
            'per_pool_pity_rate': self._per_pool_pity_rate,
            'cumulative_by_pool': self._cumulative_by_pool,
            'transition_analysis': self._transition_analysis,
        }
        fn = handlers.get(method)
        if not fn:
            return {'ok': False, 'error': f'未知分析方法: {method}', 'sections': []}
        try:
            sections = fn(params)
            return {'ok': True, 'method': method, 'sections': sections}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {'ok': False, 'method': method, 'error': str(e), 'sections': []}

    # ── 各方法 ───────────────────────────────────────────────────────

    def _gdr_dist(self, p):
        gdr_key = p.get('gdr', 'target_achievement')
        show_hist = p.get('hist', True)
        show_cdf = p.get('cdf', False)
        vals = np.array(self._gdr_values(gdr_key), dtype=float)
        if len(vals) == 0:
            return [{'key': 'summary', 'title': 'GDR 分布', 'items': {'状态': '无数据'}}]
        dist = EmpiricalDistribution(vals.tolist())
        defn = resolve_gdr_definition(gdr_key)
        display = defn.display_name if defn else gdr_key
        sections = []
        base = None
        if parse_gdr_key(gdr_key)[0] == 'resource_remaining':
            _rid = parse_gdr_key(gdr_key)[1]
            base = self.no_draw_resources.get(_rid, self.no_draw_resource)
        annotations = []
        if base is not None:
            annotations.append(ChartAnnotation(type='vline', value=base, color='green',
                                               dash='dash', text=f'不抽卡基线: {base:.1f}'))
        if show_hist:
            bin_result = compute_bins(gdr_key, vals, target_specs=self.target_specs,
                                      cost_per_draw=self.cost_per_draw if is_resource_gdr(gdr_key) else None,
                                      use_draw_units=False)
            title = f'{display} 分布'
            if bin_result.inf_label:
                title += f' ({bin_result.inf_label})'
            spec = ChartSpec(chart_type='histogram',
                             data=HistogramData(samples=vals, mean_line=True,
                                                quantile_lines=[self.alpha]),
                             title=title, xlabel=display,
                             ylabel='频数' if not bin_result.density else '概率密度',
                             annotations=annotations,
                             layout_hints=bin_result.to_layout_hints())
            sections.append(_sec_chart(title, spec))
        if show_cdf:
            cdf_spec = ChartSpec(chart_type='cdf', data=CDFData(samples=vals),
                                 title=f'{display} 累积分布', xlabel=display,
                                 ylabel='累积概率',
                                 annotations=[ChartAnnotation(type='hline', value=self.alpha,
                                                              color='orange', dash='dot',
                                                              text=f'α={self.alpha:.2f}')] + annotations)
            sections.append(_sec_chart(f'{display} 累积分布', cdf_spec))
        sections.insert(0, _sec_summary('概览', {
            '均值': f'{dist.mean():.4f}', '中位数': f'{dist.median():.4f}',
            '标准差': f'{dist.std():.4f}', '样本数': dist.n,
        }))
        return sections

    def _gdr_statistics(self, p):
        gdr_key = p.get('gdr', 'target_achievement')
        vals = np.array(self._gdr_values(gdr_key), dtype=float)
        if len(vals) == 0:
            return [{'key': 'summary', 'title': 'GDR 指标统计', 'items': {'状态': '无数据'}}]
        dist = EmpiricalDistribution(vals.tolist())
        defn = resolve_gdr_definition(gdr_key)
        display = defn.display_name if defn else gdr_key
        qs = {f'Q{int(q*100)}': f'{dist.quantile(q, use_evt=False):.4f}' for q in (0.05, 0.25, 0.5, 0.75, 0.95)}
        rows = [['均值', f'{dist.mean():.4f}'], ['中位数', f'{dist.median():.4f}'],
                ['标准差', f'{dist.std():.4f}'], ['最小值', f'{dist.min_val():.4f}'],
                ['最大值', f'{dist.max_val():.4f}']]
        for k, v in qs.items():
            rows.append([k, v])
        return [{'key': 'summary', 'title': f'{display} 统计摘要',
                 'items': {'均值': f'{dist.mean():.4f}', '中位数': f'{dist.median():.4f}', '样本数': dist.n}},
                {'key': 'table', 'title': f'{display} 统计表', 'headers': ['指标', '值'], 'rows': rows}]

    def _correlation(self, p):
        a_key = p.get('gdrA', 'target_achievement')
        b_key = p.get('gdrB', 'resource_consumed')
        vals_a = np.array(self._gdr_values(a_key), dtype=float)
        vals_b = np.array(self._gdr_values(b_key), dtype=float)
        n = min(len(vals_a), len(vals_b))
        if n < 2:
            return [{'key': 'summary', 'title': '相关性分析', 'items': {'状态': '数据不足'}}]
        va, vb = vals_a[:n], vals_b[:n]
        if np.std(va) < 1e-12 or np.std(vb) < 1e-12:
            r = float('nan')
        else:
            r = float(np.corrcoef(va, vb)[0, 1])
        a_name = (resolve_gdr_definition(a_key).display_name if resolve_gdr_definition(a_key) else a_key)
        b_name = (resolve_gdr_definition(b_key).display_name if resolve_gdr_definition(b_key) else b_key)
        # 散点图 + 相关系数
        spec = ChartSpec(chart_type='scatter',
                         data=ScatterData(x=va, y=vb, mode='markers'),
                         title=f'{a_name} × {b_name} 散点图', xlabel=a_name, ylabel=b_name)
        return [_sec_summary('相关系数', {
            'Pearson r': '—' if np.isnan(r) else f'{r:.4f}',
            '样本数': n,
        }), _sec_chart('相关性散点图', spec)]

    def _success_rate(self, p):
        gdr_key = p.get('gdr', 'target_achievement')
        threshold = float(p.get('threshold', 1.0))
        scope = p.get('scope', 'overall')
        conf = float(p.get('ci', 0.95))
        calc = make_gdr_calculator(self.store, self.target_specs, gdr_key, gdr_threshold=threshold,
                                   ssr_ids=self.ssr_ids)
        if scope == 'overall':
            flags = [calc.is_success(r) for r in self.aggregate_data if r]
        else:
            # per_pool：用 transition_flags 预计算（第 0 池）——简化；完整每池在累计分析
            flags = [bool(f) for f in self.transition_flags] if self.transition_flags else []
        success = sum(flags)
        total = len(flags)
        rate = success / total if total else 0.0
        lo, hi = wilson_ci(success, total, conf)
        defn = resolve_gdr_definition(gdr_key)
        display = defn.display_name if defn else gdr_key
        return [_sec_table('成功率分析', ['成功数 / 总数', '成功率', f'{conf*100:.1f}% Wilson CI'],
                           [[f'{success} / {total}', f'{rate*100:.2f}%',
                             f'[{lo*100:.2f}%, {hi*100:.2f}%]']]),
                {'key': 'summary', 'title': '成功率', 'items': {
                    '判定标准': display, '成功率': f'{rate*100:.2f}%'}}]

    def _risk_var_cvar(self, p):
        alpha = float(p.get('alpha', 0.05))
        dists = self._compute_all_gdr_dists()
        rows = []
        for name, dist in dists.items():
            if dist.n < 2:
                continue
            defn = resolve_gdr_definition(name)
            display = defn.display_name if defn else name
            rows.append([display, f"{dist.mean():.4f}", f"{dist.median():.4f}",
                         f"{dist.std():.4f}", f"{dist.var(alpha):.4f}", f"{dist.cvar(alpha):.4f}",
                         f"{dist.var_mean_diff(alpha):.4f}", f"{dist.var_median_diff(alpha):.4f}"])
        if not rows:
            return [{'key': 'summary', 'title': 'VaR / CVaR', 'items': {'状态': '无数据'}}]
        return [_sec_table(f'GDR 风险指标 (VaR/CVaR α={alpha})',
                           ['GDR指标', '均值', '中位数', '标准差', f'VaR({alpha})', f'CVaR({alpha})', 'VaR-均值差', 'VaR-中位数差'],
                           rows)]

    def _risk_worst_case(self, p):
        return self._risk_tail(p, worst=True)

    def _risk_best_case(self, p):
        return self._risk_tail(p, worst=False)

    def _risk_tail(self, p, worst=True):
        alpha = float(p.get('alpha', 0.05))
        gdr_key = p.get('gdr', 'resource_remaining' if worst else 'target_achievement')
        dists = self._compute_all_gdr_dists()
        primary = dists.get(gdr_key)
        if not primary or primary.n == 0:
            return [{'key': 'summary', 'title': '风险分析', 'items': {'状态': '无数据'}}]
        defn = resolve_gdr_definition(gdr_key)
        lower = defn.lower_is_better if defn else False
        if worst:
            val = primary.quantile(1 - alpha) if lower else primary.quantile(alpha)
            in_tail = [v >= val if lower else v <= val for v in primary.samples]
            tail_label = f'上{1-alpha}分位' if lower else f'VaR({alpha})'
            color = 'red'
        else:
            val = primary.quantile(alpha) if lower else primary.quantile(1 - alpha)
            in_tail = [v <= val if lower else v >= val for v in primary.samples]
            tail_label = f'VaR({alpha})' if lower else f'上{1-alpha}分位'
            color = 'green'
        tail_samples = [primary.samples[i] for i in range(primary.n) if in_tail[i]]
        tail_dist = EmpiricalDistribution(tail_samples) if tail_samples else EmpiricalDistribution([])
        rows = []
        for name, dist in dists.items():
            if dist.n < 2 or name == gdr_key:
                continue
            joint = JointSamples([(primary.samples[i], dist.samples[i])
                                  for i in range(primary.n) if i < dist.n])
            cond = joint.conditional_second((lambda f: f >= val) if lower else (lambda f: f <= val))
            if cond.n == 0:
                continue
            dname = resolve_gdr_definition(name).display_name if resolve_gdr_definition(name) else name
            rows.append([dname, f'{cond.n}', f'{dist.mean():.4f}', f'{cond.mean():.4f}',
                         f'{cond.mean()-dist.mean():.4f}', f'{cond.median():.4f}', f'{cond.std():.4f}'])
        sections = []
        display = defn.display_name if defn else gdr_key
        sections.append(_sec_summary(f'{("最差" if worst else "最好")}情形', {
            '主指标': display, '尾部阈值': f'{val:.4f}', '尾部样本': tail_dist.n,
        }))
        if rows:
            sections.append(_sec_table(f'{("最差" if worst else "最好")}情形条件统计',
                                       ['GDR指标', '样本数', '全局均值', '条件均值', '均值差', '中位数', '标准差'], rows))
        # 主分布直方图 + 尾部叠加
        bin_result = compute_bins(gdr_key, np.array(primary.samples), target_specs=self.target_specs,
                                  cost_per_draw=self.cost_per_draw if is_resource_gdr(gdr_key) else None,
                                  use_draw_units=False)
        overlays = []
        if tail_dist.n > 0:
            overlays.append(HistogramOverlay(samples=np.array(tail_dist.samples), color=color,
                                             opacity=0.6, label=f'{tail_label}, n={tail_dist.n}'))
        spec = ChartSpec(chart_type='histogram',
                         data=HistogramData(samples=np.array(primary.samples), mean_line=False,
                                            overlays=overlays, density=bin_result.density),
                         title=f'{("最差" if worst else "最好")}情形分析: {display} (α={alpha})',
                         xlabel=display, ylabel='频次' if not bin_result.density else '密度',
                         annotations=[ChartAnnotation(type='vline', value=val, color='orange',
                                                      dash='dash', text=f'{tail_label}={val:.4f}')],
                         layout_hints=bin_result.to_layout_hints())
        sections.append(_sec_chart(f'{("最差" if worst else "最好")}情形分布', spec))
        return sections

    def _conditional_dist(self, p):
        cond_key = p.get('cond', 'target_achievement')
        target_key = p.get('gdr', 'resource_remaining')
        threshold = float(p.get('threshold', 0.5))
        cond_vals = self._gdr_values(cond_key)
        target_vals = self._gdr_values(target_key)
        n = min(len(cond_vals), len(target_vals))
        if n < 2:
            return [{'key': 'summary', 'title': '条件分布', 'items': {'状态': '数据不足'}}]
        joint = JointSamples(list(zip(cond_vals[:n], target_vals[:n])))
        all_t = joint.second_distribution()
        succ = joint.conditional_second(lambda f, t=threshold: f >= t)
        fail = joint.conditional_second(lambda f, t=threshold: f < t)
        cdef = resolve_gdr_definition(cond_key)
        tdef = resolve_gdr_definition(target_key)
        cname = cdef.display_name if cdef else cond_key
        tname = tdef.display_name if tdef else target_key
        rows = []
        for label, cd in [('全部', all_t), (f'{cname}≥{threshold}', succ), (f'{cname}<{threshold}', fail)]:
            if cd.n > 0:
                rows.append([label, f'{cd.n}', f'{cd.mean():.4f}', f'{cd.median():.4f}',
                             f'{cd.std():.4f}', f'{cd.quantile(0.25):.4f}', f'{cd.quantile(0.75):.4f}'])
        sections = [_sec_table(f'{cname} 条件下 {tname} 的分布统计量',
                               ['条件', '样本数', '均值', '中位数', '标准差', 'Q25', 'Q75'], rows)]
        overlays = []
        if succ.n > 0:
            overlays.append(HistogramOverlay(samples=np.array(succ.samples), color='green', opacity=0.5,
                                            label=f'条件≥{threshold}(n={succ.n})'))
        if fail.n > 0:
            overlays.append(HistogramOverlay(samples=np.array(fail.samples), color='red', opacity=0.5,
                                            label=f'条件<{threshold}(n={fail.n})'))
        bin_result = compute_bins(target_key, np.array(all_t.samples), target_specs=self.target_specs,
                                  cost_per_draw=self.cost_per_draw if is_resource_gdr(target_key) else None,
                                  use_draw_units=False)
        anns = []
        if parse_gdr_key(target_key)[0] == 'resource_remaining':
            _rid = parse_gdr_key(target_key)[1]
            ref = self.no_draw_resources.get(_rid, self.no_draw_resource)
            if ref is not None:
                anns.append(ChartAnnotation(type='vline', value=ref, color='green', dash='dash',
                                            text=f'不抽卡基线: {ref:.1f}'))
        spec = ChartSpec(chart_type='histogram',
                         data=HistogramData(samples=np.array(all_t.samples), mean_line=False,
                                            overlays=overlays, density=bin_result.density),
                         title=f'条件分布: {tname} | {cname} (阈值={threshold})',
                         xlabel=tname, ylabel='频数' if not bin_result.density else '密度',
                         annotations=anns, layout_hints=bin_result.to_layout_hints())
        sections.append(_sec_chart('条件分布', spec))
        return sections

    def _time_series(self, p):
        if not self.draw_sequences:
            return [{'key': 'summary', 'title': '时间序列', 'items': {'状态': '无逐抽序列数据'}}]
        target_ids = set(self.target_specs.keys())
        target_count = sum(self.target_specs.values())
        n_sample = min(20, len(self.draw_sequences))
        rng = np.random.default_rng(42)
        indices = rng.choice(len(self.draw_sequences), n_sample, replace=False) if len(self.draw_sequences) > n_sample else range(len(self.draw_sequences))
        traces = []
        for idx in indices:
            seq = self.draw_sequences[idx]
            card_ids = seq.get('draw_card_ids', []) or []
            gdr_series = []
            obtained = 0
            for cid in card_ids:
                if cid in target_ids:
                    obtained += 1
                gdr_series.append(obtained / target_count if target_count > 0 else 0)
            traces.append(ScatterTrace(x=np.arange(len(gdr_series)), y=np.array(gdr_series),
                                       mode='lines', name=f'样本{idx}', marker_size=1))
        spec = ChartSpec(chart_type='scatter', data=ScatterData(traces=traces),
                         title='GDR演化（样本路径）', xlabel='抽卡序号', ylabel='目标达成率')
        return [_sec_chart('时间序列', spec)]

    def _time_heatmap(self, p):
        hd = self.heatmap_data.get('data', {}) if isinstance(self.heatmap_data, dict) else {}
        bins = self.heatmap_data.get('bins', {}) if isinstance(self.heatmap_data, dict) else {}
        sections = []
        configs = [
            ('目标达成率', 'achievement', 0, 1.05, 25),
            ('资源剩余', 'resource', None, None, 25),
            ('SSR出数', 'ssr_count', None, None, 25),
        ]
        for gdr_name, gkey, vmin_d, vmax_d, nb in configs:
            time_data = {}
            if gkey in ('achievement', 'resource') and hd:
                for step_idx, step_data in hd.items():
                    if gkey in step_data:
                        time_data[step_idx] = step_data[gkey]
            elif gkey == 'ssr_count' and self.draw_sequences:
                for seq in self.draw_sequences:
                    card_ids = seq.get('draw_card_ids', []) or []
                    ssr_so_far = 0
                    for i, cid in enumerate(card_ids):
                        if cid in self.ssr_ids:
                            ssr_so_far += 1
                        time_data.setdefault(i, []).append(ssr_so_far)
            if not time_data:
                continue
            sorted_draws = sorted(time_data.keys())
            if len(sorted_draws) > 40:
                step = len(sorted_draws) / 40
                sampled = sorted(set(int(i * step) for i in range(40)))
                sampled.append(len(sorted_draws) - 1)
                sampled_draws = [sorted_draws[i] for i in sampled]
            else:
                sampled_draws = sorted_draws
            prebinned = gkey in bins
            if prebinned:
                edges = bins[gkey]
                n_bins = len(edges) - 1
                mat = np.zeros((n_bins, len(sampled_draws)))
                for ci, d in enumerate(sampled_draws):
                    counts = np.array(time_data[d], dtype=float)
                    mat[:, ci] = counts / max(counts.sum(), 1)
                y_lo, y_hi = edges[0], edges[-1]
            else:
                y_all = [v for d in sampled_draws for v in time_data[d] if np.isfinite(v)]
                if not y_all:
                    continue
                y_lo = float(np.min(y_all)) if vmin_d is None else vmin_d
                y_hi = float(np.max(y_all)) if vmax_d is None else vmax_d
                if abs(y_hi - y_lo) < 1e-9:
                    y_hi = y_lo + 1.0
                edges = np.linspace(y_lo, y_hi, nb + 1)
                mat = np.zeros((nb, len(sampled_draws)))
                for ci, d in enumerate(sampled_draws):
                    col = np.array([v for v in time_data[d] if np.isfinite(v)])
                    if len(col) == 0:
                        continue
                    counts, _ = np.histogram(col, bins=edges)
                    mat[:, ci] = counts / max(len(col), 1)
            n_ticks = min(7, len(edges) - 1)
            y_ticks = np.linspace(y_lo, y_hi, n_ticks)
            if gkey == 'achievement':
                y_labels = [f'{v:.0%}' for v in y_ticks]
            elif gkey == 'ssr_count':
                y_labels = [f'{v:.0f}' for v in y_ticks]
            else:
                y_labels = [f'{v:.2f}' for v in y_ticks]
            col_labels = [f'{sampled_draws[i]}' for i in range(len(sampled_draws))]
            spec = ChartSpec(chart_type='heatmap', data=HeatmapData(
                matrix=mat, row_labels=y_labels, col_labels=col_labels, colorscale='YlOrRd'),
                title=f'{gdr_name} 分布随抽卡次数演化 ({len(self.aggregate_data)} 次模拟)',
                xlabel='抽卡次数', ylabel=gdr_name)
            sections.append(_sec_chart(f'{gdr_name} 时间热力图', spec))
        return sections or [{'key': 'summary', 'title': '时间热力图', 'items': {'状态': '无数据'}}]

    def _draws_vs_gdr(self, p):
        gdr_key = p.get('gdr', 'target_achievement')
        vals = self._gdr_values(gdr_key)
        draws = [r.get('total_draws', 0) for r in self.aggregate_data if r]
        n = min(len(vals), len(draws))
        if n < 2:
            return [{'key': 'summary', 'title': '抽卡数-达成率', 'items': {'状态': '数据不足'}}]
        defn = resolve_gdr_definition(gdr_key)
        display = defn.display_name if defn else gdr_key
        spec = ChartSpec(chart_type='scatter',
                         data=ScatterData(x=np.array(draws[:n]), y=np.array(vals[:n]), mode='markers'),
                         title=f'抽卡数 vs {display}', xlabel='总抽卡数', ylabel=display)
        return [_sec_chart('抽卡数-达成率', spec)]

    # ── 瀑布图（对齐旧 analysis_panel waterfall_3d / waterfall_2d）：目标达成随抽卡步数的分布演化 ──
    def _waterfall(self, p, mode):
        if not self.draw_sequences:
            return [{'key': 'summary', 'title': '瀑布图', 'items': {'状态': '无逐抽序列数据'}}]
        target_ids = set(self.target_specs.keys())
        target_count = sum(self.target_specs.values())
        time_gdr_data = {}
        for seq in self.draw_sequences:
            card_ids = seq.get('draw_card_ids', []) or []
            obtained = 0
            for i, cid in enumerate(card_ids):
                if cid in target_ids:
                    obtained += 1
                time_gdr_data.setdefault(i, []).append(obtained)
        if not time_gdr_data:
            return [{'key': 'summary', 'title': '瀑布图', 'items': {'状态': '无数据'}}]
        sorted_times = sorted(time_gdr_data.keys())
        gdr_range = list(range(0, target_count + 1))
        if mode == '3d':
            t_sample = min(40, len(sorted_times))
            t_indices = sorted(set(np.linspace(0, len(sorted_times) - 1, t_sample, dtype=int)))
            xs, ys, zs = [], [], []
            for idx in t_indices:
                t_val = sorted_times[idx]
                data = time_gdr_data[t_val]
                total = len(data)
                counts = {}
                for v in data:
                    counts[v] = counts.get(v, 0) + 1
                for g in gdr_range:
                    xs.append(float(t_val))
                    ys.append(float(g))
                    zs.append(counts.get(g, 0) / total if total else 0.0)
            spec = ChartSpec(chart_type='waterfall_3d',
                             data=Waterfall3DData(x=np.array(xs), y=np.array(ys), z=np.array(zs)),
                             title='3D瀑布图', xlabel='时间步', ylabel='目标卡数',
                             layout_hints={'zlabel': '概率'})
            return [_sec_chart('3D瀑布图', spec)]
        t_sample = min(25, len(sorted_times))
        t_indices = sorted(set(np.linspace(0, len(sorted_times) - 1, t_sample, dtype=int)))
        t_min = sorted_times[t_indices[0]]
        t_max = sorted_times[t_indices[-1]]
        traces = []
        for idx in t_indices:
            t_val = sorted_times[idx]
            data = time_gdr_data[t_val]
            total = len(data)
            counts = {}
            for v in data:
                counts[v] = counts.get(v, 0) + 1
            probs = [counts.get(g, 0) / total if total else 0.0 for g in gdr_range]
            # viridis 色阶按时间渐变（对齐旧 _build_waterfall_2d）
            frac = (t_val - t_min) / max(t_max - t_min, 1)
            r = int((0.267 + frac * (0.993 - 0.267)) * 255)
            g2 = int((0.004 + frac * (0.906 - 0.004)) * 255)
            b = int((0.329 + frac * (0.144 - 0.329)) * 255)
            traces.append(ScatterTrace(x=np.array(gdr_range, dtype=float), y=np.array(probs),
                                      mode='lines', name=f't={int(t_val)}',
                                      marker_size=1, line_color=f'#{r:02x}{g2:02x}{b:02x}'))
        spec = ChartSpec(chart_type='scatter', data=ScatterData(traces=traces),
                         title='2D瀑布图', xlabel='目标卡数量', ylabel='概率')
        return [_sec_chart('2D瀑布图', spec)]

    def _waterfall_3d(self, p):
        return self._waterfall(p, '3d')

    def _waterfall_2d(self, p):
        return self._waterfall(p, '2d')

    def _per_pool(self, mode):
        agg = self.aggregate_data
        if not agg:
            return [{'key': 'summary', 'title': '每池分析', 'items': {'状态': '无数据'}}]
        target_ids = set(self.target_specs.keys())
        batch_snaps = {}
        for r in agg:
            pdc = r.get('pool_draw_counts', {}) or {}
            pcc = r.get('pool_card_counts', {}) or {}
            ppc = r.get('pool_pity_counts', {}) or {}
            prc = r.get('pool_resources_consumed', {}) or {}
            for pid in set(pdc) | set(pcc) | set(ppc):
                snap = PoolSnapshot(pool_id=pid, draw_count=pdc.get(pid, 0),
                                    target_card_draws=sum(c for cid, c in pcc.get(pid, {}).items() if cid in target_ids),
                                    pity_draws=ppc.get(pid, 0),
                                    resources_consumed=dict(prc.get(pid, {})))
                batch_snaps.setdefault(pid, []).append(snap)
        stats = per_pool_summary_stats(batch_snaps)
        if not stats:
            return [{'key': 'summary', 'title': '每池分析', 'items': {'状态': '无每池数据'}}]
        pool_ids = sorted(stats.keys())
        labels = [self.pool_names.get(pid, pid) for pid in pool_ids]
        if mode == 'draws':
            vals = [stats[pid].get('mean_draws', 0) for pid in pool_ids]
            title, color, xlab = '每池平均抽卡数', '#2196F3', '抽卡数'
        elif mode == 'target':
            vals = [stats[pid].get('target_count', 0) for pid in pool_ids]
            title, color, xlab = '每池目标卡数', '#4CAF50', '目标卡数'
        else:
            vals = [stats[pid].get('pity_count', 0) for pid in pool_ids]
            title, color, xlab = '每池保底数', '#FF9800', '保底数'
        spec = ChartSpec(chart_type='bar', data=BarData(labels=labels, values=np.array(vals), orientation='h'),
                         title=title, xlabel=xlab, ylabel='池子', layout_hints={'color': color})
        rows = [[lbl, f'{v:.2f}' if mode == 'draws' else f'{v:.0f}'] for lbl, v in zip(labels, vals)]
        return [_sec_chart(title, spec),
                _sec_table(f'{title} 表', ['池子', '值'], rows)]

    def _per_pool_draws(self, p):
        return self._per_pool('draws')

    def _per_pool_target_rate(self, p):
        return self._per_pool('target')

    def _per_pool_pity_rate(self, p):
        return self._per_pool('pity')

    def _cumulative_by_pool(self, p):
        gdr_key = p.get('gdr', 'target_achievement')
        if not self.cumulative_snapshots:
            return [{'key': 'summary', 'title': '截止每池 GDR', 'items': {'状态': '无累计快照数据'}}]
        pool_ids = sorted(self.cumulative_snapshots.keys())
        series = {}
        labels = {}
        for pid in pool_ids:
            raw = []
            for snap in self.cumulative_snapshots.get(pid, []):
                try:
                    v = compute_gdr_from_cumulative(
                        snap, self.target_specs, gdr_key, ssr_ids=self.ssr_ids,
                        desire_weights=self.store.desire_weights if self.store else None,
                        miss_cost_weights=self.store.miss_cost_weights if self.store else None,
                        card_value_weights=self.store.card_value_weights if self.store else None,
                        store=self.store,
                    )
                    raw.append(float(v))
                except Exception:
                    pass
            if raw:
                series[pid] = np.array(raw)
                labels[pid] = self.pool_names.get(pid, pid)
        if not series:
            return [{'key': 'summary', 'title': '截止每池 GDR', 'items': {'状态': '计算失败'}}]
        defn = resolve_gdr_definition(gdr_key)
        display = defn.display_name if defn else gdr_key
        baselines = {}
        if parse_gdr_key(gdr_key)[0] == 'resource_remaining' and self.no_draw_pool_resources:
            _, rid = parse_gdr_key(gdr_key)
            for pid in pool_ids:
                pid_banner = pid.split('.')[0] if '.' in pid else pid
                pool_res = self.no_draw_pool_resources.get(pid_banner, {})
                if rid in pool_res:
                    baselines[pid] = float(pool_res[rid])
        spec = ChartSpec(chart_type='ridge', data=RidgeData(series=series, baselines=baselines, labels=labels),
                         title=f'{display} (截止每池)', xlabel=display, ylabel='池子')
        return [_sec_chart(f'{display} 截止每池', spec)]

    def _transition_analysis(self, p):
        if not self.pool_end_times:
            return [{'key': 'summary', 'title': '转变分析', 'items': {'状态': '无池结束时间数据'}}]
        sorted_pools = sorted(self.pool_end_times.items(), key=lambda x: x[1])
        pool_ids_ordered = [pid for pid, _ in sorted_pools]
        if self.transition_flags:
            flags = self.transition_flags
        elif self.cumulative_snapshots:
            flags = compute_transition_flags_from_gdr(
                self.cumulative_snapshots, pool_ids_ordered, self.target_specs,
                gdr_key='all_targets', threshold=1.0, scope='cumulative',
                aggregates=self.aggregate_data, ssr_ids=self.ssr_ids,
                desire_weights=self.store.desire_weights if self.store else None,
                miss_cost_weights=self.store.miss_cost_weights if self.store else None,
                card_value_weights=self.store.card_value_weights if self.store else None,
                bonus_events=[r.get('bonus_events', []) for r in self.aggregate_data],
            )
        else:
            return [{'key': 'summary', 'title': '转变分析', 'items': {'状态': '缺少 transition_flags 与累计快照'}}]
        trans = compute_transition_matrices_from_flags(flags, pool_ids_ordered)
        if not trans:
            return [{'key': 'summary', 'title': '转变分析', 'items': {'状态': '无足够数据生成转移矩阵'}}]
        # 成功率变化：转移前/后 两条折线（对齐旧 UI transition_analysis_rates）
        xs = np.arange(len(trans))
        spec = ChartSpec(chart_type='scatter', data=ScatterData(traces=[
            ScatterTrace(x=xs, y=np.array([t.success_rate_before for t in trans]),
                         mode='lines+markers', name='转移前成功率', marker_size=8, line_color='#2196F3'),
            ScatterTrace(x=xs, y=np.array([t.success_rate_after for t in trans]),
                         mode='lines+markers', name='转移后成功率', marker_size=8, line_color='#4CAF50',
                         marker_symbol='square'),
        ]), title='相邻池子间成功率变化', xlabel='转移', ylabel='成功率')
        # 转移概率矩阵子图网格（2×2 × 转移数，Blues，每行 4 个，对齐旧 UI transition_analysis_matrices）
        matrices = []
        grid_titles = []
        for t in trans:
            matrices.append(np.array([
                [t.success_to_success, t.success_to_fail],
                [t.fail_to_success, t.fail_to_fail],
            ]))
            grid_titles.append(f'{self.pool_names.get(t.from_pool_id, t.from_pool_id)}→{self.pool_names.get(t.to_pool_id, t.to_pool_id)}')
        grid = ChartSpec(chart_type='subplot_grid',
                         data=SubplotGridData(matrices=matrices, titles=grid_titles,
                                              row_labels=['成功', '失败'], col_labels=['成功', '失败'],
                                              colorscale='Blues', cols=4),
                         title='转移概率矩阵')
        # 转移矩阵（2×2 → 文本表）
        rows = []
        for t in trans:
            rows.append([self.pool_names.get(t.from_pool_id, t.from_pool_id),
                         self.pool_names.get(t.to_pool_id, t.to_pool_id),
                         f'{t.success_to_success:.4f}', f'{t.success_to_fail:.4f}',
                         f'{t.fail_to_success:.4f}', f'{t.fail_to_fail:.4f}'])
        return [_sec_chart('相邻池子间成功率变化', spec),
                _sec_chart('转移概率矩阵', grid),
                _sec_table('转移矩阵', ['前池', '后池', '成功→成功', '成功→失败', '失败→成功', '失败→失败'], rows)]
