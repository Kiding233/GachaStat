"""过程分析服务（事件级交叉统计：AA/BB/AB/BA）。

移植 process_analysis_panel._build_traces + compute_aa/bb/ab/ba 核心逻辑。
"""
from __future__ import annotations


from gacha_simulator.core.process_trace import SampleTrace, infer_events, compute_pool_gdr_single_pool
from gacha_simulator.core.process_analysis import compute_aa, compute_bb, compute_ab, compute_ba
from gacha_simulator.core.gdr import make_gdr_calculator


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
        checker = make_gdr_calculator(store, target_specs, gdr_key, gdr_threshold=threshold, ssr_ids=ssr_ids)

        traces = []
        for idx, agg in enumerate(aggregate_data):
            pool_events = infer_events(agg, target_ids, pool_types=pool_types)
            pool_ids_sorted = sorted(pool_events.keys())
            events_list = [pool_events[pid] for pid in pool_ids_sorted]
            pool_success = {}
            for pid in pool_ids_sorted:
                val = compute_pool_gdr_single_pool(agg, pid, target_specs, gdr_key, ssr_ids=ssr_ids)
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
                                      pool_gdr_values={}))

        sections = []
        # AA：事件统计
        try:
            aa = compute_aa(traces, event_mode=event_mode, constraints=constraints)
            if aa:
                rows = [[r['pattern'], f"{r['count']}", f"{r['probability']:.4f}",
                         f"{r['cumulative_probability']:.4f}"] for r in aa]
                sections.append({'key': 'table', 'title': '事件统计（AA）',
                                 'headers': ['事件组合', '次数', '概率', '累计概率'], 'rows': rows})
        except Exception:
            pass
        # BB：成败模式
        try:
            bb = compute_bb(traces, success_mode=success_mode,
                            success_op=success_op, success_n=success_n)
            if bb and bb.get('pattern_table'):
                rows = [[p['pattern'], f"{p['count']}", f"{p.get('probability', 0):.4f}"]
                        for p in bb['pattern_table']]
                sections.append({'key': 'table', 'title': '成败统计（BB）',
                                 'headers': ['成败模式', '次数', '概率'], 'rows': rows})
        except Exception:
            pass
        # AB：事件→成败（含 low_sample 警告——样本 <5 时 Wilson CI 不可信）
        try:
            ab = compute_ab(traces, event_mode=event_mode, success_mode=success_mode,
                            constraints=constraints, success_op=success_op,
                            success_n=success_n, conf_level=conf)
            if ab:
                rows = []
                for r in ab:
                    row = [r.get('event_pattern'), f"{r.get('count', 0)}", f"{r.get('success_count', 0)}",
                           f"{r.get('failure_count', 0)}", f"{r.get('overall_success_prob', 0):.4f}",
                           f"{r.get('wilson_ci_lower', 0):.4f}", f"{r.get('wilson_ci_upper', 0):.4f}"]
                    if r.get('low_sample'):
                        row.append('样本<5')
                    else:
                        row.append('')
                    rows.append(row)
                sections.append({'key': 'table', 'title': '事件→成败（AB）',
                                 'headers': ['事件组合', '次数', '成功', '失败', 'P(成功)', 'CI下', 'CI上', '提示'],
                                 'rows': rows})
        except Exception:
            pass
        # BA：成败→事件（含 Wilson CI 列，对齐 core compute_ba 字段）
        try:
            ba = compute_ba(traces, event_mode=event_mode, success_mode=success_mode,
                            constraints=constraints, success_op=success_op,
                            success_n=success_n, conf_level=conf)
            if ba:
                rows = []
                for r in ba:
                    row = [r.get('event_pattern'), f"{r.get('p_given_success', 0):.4f}",
                           f"[{r.get('p_given_success_wilson_lower', 0):.4f}, {r.get('p_given_success_wilson_upper', 0):.4f}]",
                           f"{r.get('p_given_failure', 0):.4f}",
                           f"[{r.get('p_given_failure_wilson_lower', 0):.4f}, {r.get('p_given_failure_wilson_upper', 0):.4f}]",
                           f"{r.get('ratio', 0):.4f}", f"{r.get('count', 0)}"]
                    if r.get('low_sample'):
                        row.append('样本<5')
                    else:
                        row.append('')
                    rows.append(row)
                sections.append({'key': 'table', 'title': '成败→事件（BA）',
                                 'headers': ['事件组合', 'P(组合|成功)', '成功 CI', 'P(组合|失败)', '失败 CI', '比值', '次数', '提示'],
                                 'rows': rows})
        except Exception:
            pass
        if not sections:
            sections.append({'key': 'summary', 'title': '过程分析', 'items': {'状态': '无事件数据'}})
        return {'ok': True, 'sections': sections, 'traces': len(traces)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'ok': False, 'error': str(e), 'sections': []}
