"""过程分析服务（事件级交叉统计：AA/BB/AB/BA + 轨迹详情）。

移植 process_analysis_panel._build_traces + compute_aa/bb/ab/ba 核心逻辑，
表格输出对齐旧 UI 数据组织格式（列序/列名/pattern 显示格式化/低样本灰行标记）。
"""
from __future__ import annotations


from gacha_simulator.core.process_trace import SampleTrace, infer_events, compute_pool_gdr_single_pool
from gacha_simulator.core.process_analysis import (
    compute_aa, compute_bb, compute_ab, compute_ba,
    _get_event_label,
)
from gacha_simulator.core.gdr import make_gdr_calculator


def _make_checker(store, target_specs, gdr_key, threshold, ssr_ids):
    """构造 GDR 计算器。store 缺失（None）时退化为无权重计算（对齐 analysis_service._calc_gdr）。"""
    try:
        return make_gdr_calculator(store, target_specs, gdr_key,
                                   gdr_threshold=threshold, ssr_ids=ssr_ids)
    except Exception:
        from gacha_simulator.core.gdr import GDRCalculator
        return GDRCalculator(target_specs, gdr_key=gdr_key,
                             gdr_threshold=threshold, ssr_ids=ssr_ids,
                             desire_weights={}, miss_cost_weights={},
                             card_value_weights={})


def _format_event_pattern(pattern, event_mode):
    """对齐旧 process_analysis_panel._format_event_pattern 的显示文本。"""
    if isinstance(pattern, dict):
        if event_mode == 'custom':
            parts = [v for k, v in sorted(pattern.items()) if not v.endswith(':*')]
            return ', '.join(parts) if parts else '(全部任意)'
        return ', '.join(f'{k}:{v}' for k, v in sorted(pattern.items()))
    if isinstance(pattern, (list, tuple)):
        if not pattern:
            return '(空)'
        if event_mode == 'count_set':
            parts = []
            for et, cnt in pattern:
                if cnt > 0:
                    parts.append(f'{_get_event_label(et)}:{cnt}')
            return ', '.join(parts) if parts else '(无事件)'
        if event_mode == 'set':
            return ', '.join(str(x) for x in pattern)
        else:
            return ' → '.join(str(x) for x in pattern)
    return str(pattern)


def _format_success_pattern(pattern, success_mode):
    """对齐旧 process_analysis_panel._format_success_pattern 的显示文本。"""
    if isinstance(pattern, (list, tuple)):
        if success_mode in ('sequence',):
            return ', '.join('✓' if x else '✗' for x in pattern)
        elif success_mode == 'set' and len(pattern) == 2:
            return f"{pattern[0]}成功, {pattern[1]}失败"
        else:
            return str(pattern)
    elif isinstance(pattern, int):
        return f"成功{pattern}个池"
    elif isinstance(pattern, str):
        if pattern.startswith('>='):
            return f'≥{pattern[2:]}个成功'
        elif pattern.startswith('<='):
            return f'≤{pattern[2:]}个成功'
        elif pattern.startswith('='):
            return f'恰好{pattern[1:]}个成功'
        elif pattern.startswith('≠'):
            return f'≠{pattern[1:]}个成功'
        elif pattern.startswith('>'):
            return f'>{pattern[1:]}个成功'
        elif pattern.startswith('<'):
            return f'<{pattern[1:]}个成功'
    return str(pattern)


def run_process_analysis(dataset, store, params: dict) -> dict:
    try:
        aggregate_data = dataset.get('aggregate_data', []) or []
        target_ids = set(dataset.get('target_ids', []) or [])
        target_specs = dict(dataset.get('target_specs', {}) or {})
        ssr_ids = set(dataset.get('ssr_ids', []) or [])
        pool_types = dataset.get('pool_types', {}) or {}
        gdr_key = params.get('gdr', 'target_achievement')
        threshold = float(params.get('threshold', 1.0))
        event_mode = params.get('eventMode', 'sequence')
        success_mode = params.get('successMode', 'count')
        conf = float(params.get('ci', 0.95))
        # 自定义模式约束（对齐旧 process_analysis_panel custom_threshold_widget / success_custom_widget）
        constraints = params.get('constraints') or None
        success_op = params.get('successOp') or None
        success_n = params.get('successN')
        success_n = int(success_n) if success_n is not None else None
        checker = _make_checker(store, target_specs, gdr_key, threshold, ssr_ids)

        traces = []
        for idx, agg in enumerate(aggregate_data):
            pool_events = infer_events(agg, target_ids, pool_types=pool_types)
            pool_ids_sorted = sorted(pool_events.keys())
            events_list = [pool_events[pid] for pid in pool_ids_sorted]
            pool_success = {}
            pool_gdr_values = {}
            for pid in pool_ids_sorted:
                val = compute_pool_gdr_single_pool(agg, pid, target_specs, gdr_key, ssr_ids=ssr_ids)
                pool_gdr_values[pid] = val if val is not None else 0.0
                if val is None:
                    pool_success[pid] = False
                elif checker.lower_is_better:
                    pool_success[pid] = val <= checker.gdr_threshold
                else:
                    pool_success[pid] = val >= checker.gdr_threshold
            try:
                val = checker.compute_gdr(agg)
            except Exception:
                val = 0.0
            traces.append(SampleTrace(events=events_list, pool_success=pool_success,
                                      is_success=checker.is_success(agg), gdr_value=val,
                                      pool_gdr_values=pool_gdr_values))

        sections = []
        # AA：事件统计（对齐旧列：['事件组合','出现次数','概率','累计概率']）
        try:
            aa = compute_aa(traces, event_mode=event_mode, constraints=constraints)
            if aa:
                rows = [[_format_event_pattern(r['pattern'], event_mode), f"{r['count']}",
                         f"{r['probability']:.4f}", f"{r['cumulative_probability']:.4f}"] for r in aa]
                sections.append({'key': 'table', 'title': '事件统计（AA）',
                                 'headers': ['事件组合', '出现次数', '概率', '累计概率'], 'rows': rows})
        except Exception:
            pass
        # BB：成败模式（对齐旧列：['成败模式','出现次数','概率','累计概率'] + 汇总说明）
        try:
            bb = compute_bb(traces, success_mode=success_mode,
                            success_op=success_op, success_n=success_n)
            if bb and bb.get('pattern_table'):
                rows = [[_format_success_pattern(p['pattern'], success_mode), f"{p['count']}",
                         f"{p.get('probability', 0):.4f}", f"{p.get('cumulative_probability', 0):.4f}"]
                        for p in bb['pattern_table']]
                sections.append({'key': 'table', 'title': '成败统计（BB）',
                                 'headers': ['成败模式', '出现次数', '概率', '累计概率'], 'rows': rows})
                # 汇总说明（对齐旧 bb_detail_label：总样本/全部池失败概率/全部池成功概率/各池成功率）
                pool_rates = (bb.get('pool_success_rates') or {})
                items = {
                    '总样本': str(bb.get('total', 0)),
                    '全部池失败概率': f"{bb.get('all_fail_prob', 0):.4f}",
                    '全部池成功概率': f"{bb.get('all_success_prob', 0):.4f}",
                }
                for pid, rate in sorted(pool_rates.items()):
                    items[f'池 {pid} 成功率'] = f"{rate:.4f}"
                sections.append({'key': 'summary', 'title': '成败统计 · 汇总', 'items': items})
        except Exception:
            pass
        # AB：事件→成败（对齐旧 8 列顺序：
        # ['事件组合','P(成功|组合)',CI,'P(失败|组合)',CI,'出现次数','成功数','失败数']）
        try:
            ab = compute_ab(traces, event_mode=event_mode, success_mode=success_mode,
                            constraints=constraints, success_op=success_op,
                            success_n=success_n, conf_level=conf)
            if ab:
                ci_label = f"{conf:.0%} CI"
                rows = []
                for r in ab:
                    pattern = _format_event_pattern(r.get('event_pattern'), event_mode)
                    low = r.get('low_sample', False)
                    if low:
                        # 样本不足：概率显示 成功/失败 计数，CI 用 '—'（对齐旧 UI 灰行）
                        p_s = f"{r['success_count']}/{r['count']}"
                        p_f = f"{r['failure_count']}/{r['count']}"
                        c_s = c_f = '—'
                    else:
                        p = r['overall_success_prob']
                        p_s = f"{p:.4f}"
                        p_f = f"{1 - p:.4f}"
                        c_s = f"[{r['wilson_ci_lower']:.4f}, {r['wilson_ci_upper']:.4f}]"
                        c_f = f"[{1 - r['wilson_ci_upper']:.4f}, {1 - r['wilson_ci_lower']:.4f}]"
                    rows.append([pattern, p_s, c_s, p_f, c_f,
                                 str(r['count']), str(r['success_count']), str(r['failure_count']),
                                 '样本不足' if low else ''])
                sections.append({'key': 'table', 'title': '事件→成败（AB）',
                                 'headers': ['事件组合', 'P(成功|组合)', ci_label,
                                             'P(失败|组合)', ci_label, '出现次数', '成功数', '失败数', '▲'],
                                 'rows': rows})
        except Exception:
            pass
        # BA：成败→事件（对齐旧 7 列顺序：
        # ['事件组合','P(组合|成功)',CI,'P(组合|失败)',CI,'比值','出现次数']）
        try:
            ba = compute_ba(traces, event_mode=event_mode, success_mode=success_mode,
                            constraints=constraints, success_op=success_op,
                            success_n=success_n, conf_level=conf)
            if ba:
                ci_label = f"{conf:.0%} CI"
                rows = []
                for r in ba:
                    pattern = _format_event_pattern(r.get('event_pattern'), event_mode)
                    ratio = r.get('ratio')
                    if ratio is None or ratio == float('inf'):
                        ratio_text = '∞'
                    else:
                        ratio_text = f"{ratio:.2f}"
                    low = r.get('low_sample', False)
                    if low:
                        p_s = f"(N={r['count']})"
                        p_f = f"(N={r['count']})"
                        c_s = c_f = '—'
                    else:
                        p_s = f"{r['p_given_success']:.4f}"
                        p_f = f"{r['p_given_failure']:.4f}"
                        c_s = f"[{r['p_given_success_wilson_lower']:.4f}, {r['p_given_success_wilson_upper']:.4f}]"
                        c_f = f"[{r['p_given_failure_wilson_lower']:.4f}, {r['p_given_failure_wilson_upper']:.4f}]"
                    rows.append([pattern, p_s, c_s, p_f, c_f, ratio_text, str(r['count']),
                                 '样本不足' if low else ''])
                sections.append({'key': 'table', 'title': '成败→事件（BA）',
                                 'headers': ['事件组合', 'P(组合|成功)', ci_label,
                                             'P(组合|失败)', ci_label, '比值', '出现次数', '▲'],
                                 'rows': rows})
        except Exception:
            pass
        # 轨迹详情（对齐旧 _show_trace_detail 7 列：逐池事件表）
        trace_rows = []
        for i, t in enumerate(traces):
            gdr_disp = f"{t.gdr_value:.4f}" if t.gdr_value is not None else '—'
            for ev in t.events:
                gdr_val = t.pool_gdr_values.get(ev.pool_id, 0.0)
                pool_ok = t.pool_success.get(ev.pool_id, False)
                trace_rows.append([
                    i + 1,                     # 轨迹序号
                    '✓ 成功' if t.is_success else '✗ 失败',
                    gdr_disp,
                    ev.pool_id, ev.event_type, ev.pity_name or '',
                    str(ev.draws), str(ev.counter_max),
                    f"{gdr_val:.4f}", '✓' if pool_ok else '✗',
                ])
        if trace_rows:
            sections.append({'key': 'table', 'title': '轨迹详情（逐池事件）',
                             'headers': ['轨迹', '整体', 'GDR', '池子ID', '事件类型', '保底名',
                                         '抽卡数', '计数器最大值', '池GDR', '池成败'],
                             'rows': trace_rows,
                             'meta': {'trace_filter': True}})
        if not sections:
            sections.append({'key': 'summary', 'title': '过程分析', 'items': {'状态': '无事件数据'}})
        return {'ok': True, 'sections': sections, 'traces': len(traces)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'ok': False, 'error': str(e), 'sections': []}
