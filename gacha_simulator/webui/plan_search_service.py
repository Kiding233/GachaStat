"""方案搜索服务（P26 退路搜索/资源目标搜索——PlanSearchEngine 封装）。

搜索模式：
- min_resource：二分找最小额外资源（search_min_resource）
- max_target：后退法最多目标卡（search_max_targets）
- forward：前进法（search_max_targets_forward）
- pareto：Pareto 前沿（search_pareto）

输入：config_store + 参数（含起始状态：from_pool / base_resource / pity_init，可来自脆弱性分析）。
输出：PlanSearchResult 序列化 dict + 前端结果区数据。
"""
from __future__ import annotations


from gacha_simulator.core.retreat_search import PlanSearchEngine


def run_plan_search(store, params: dict, progress_callback=None) -> dict:
    """执行方案搜索。params: {goal, target_specs, success_threshold, gdr_key, gdr_threshold,
    num_simulations, max_workers, from_pool, base_resource, pity_init, add_order, remove_order,
    upper_bound, lower_bound, precision, max_iter}。"""
    try:
        goal = params.get('goal', 'min_resource')
        from_pool = params.get('from_pool') or None
        if from_pool == '_root':
            from_pool = None
        base_resource = float(params.get('base_resource', 0.0) or 0.0)
        pity_init = dict(params.get('pity_init', {}) or {})
        engine = PlanSearchEngine(
            store,
            from_pool_id=from_pool,
            base_resource=base_resource,
            pity_counter_init=pity_init,
            add_order=dict(params.get('add_order', {}) or {}),
            remove_order=dict(params.get('remove_order', {}) or {}),
            success_threshold=float(params.get('success_threshold', 0.95)),
            gdr_key=params.get('gdr_key', 'all_targets'),
            gdr_threshold=float(params.get('gdr_threshold', 1.0)),
            num_simulations=int(params.get('num_simulations', 500)),
            max_workers=int(params.get('max_workers', 4)),
            max_binary_iterations=int(params.get('max_iter', 20)),
            precision_draws=int(params.get('precision', 1)),
            strategy_name=params.get('strategy', 'smart'),
            upper_bound=float(params.get('upper_bound', 8000.0)),
            lower_bound=float(params.get('lower_bound', 0.0)),
            progress_callback=progress_callback,
        )
        target_specs = dict(params.get('target_specs', {}) or {})
        # 未显式传 target_specs 时用 store 的目标卡
        if not target_specs and store:
            target_specs = {tc.card_id: tc.quantity for tc in store.target_cards}

        if goal == 'min_resource':
            result = engine.search_min_resource(target_specs)
        elif goal == 'max_target':
            result = engine.search_max_targets(target_specs)
        elif goal == 'forward':
            result = engine.search_max_targets_forward(target_specs)
        elif goal == 'pareto':
            direction = params.get('direction', 'backward')
            result = engine.search_pareto(target_specs, direction=direction)
        else:
            return {'ok': False, 'error': f'未知搜索模式: {goal}'}

        return {'ok': True, 'result': _serialize_result(result)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'ok': False, 'error': str(e)}


def _serialize_result(result) -> dict:
    out = {
        'search_mode': getattr(result, 'search_mode', ''),
        'direction': getattr(result, 'direction', ''),
        'from_pool_id': getattr(result, 'from_pool_id', None),
        'base_resource': getattr(result, 'base_resource', None),
        'start_mode': getattr(result, 'start_mode', ''),
        'success': bool(getattr(result, 'success', False)),
        'total_iterations': getattr(result, 'total_iterations', 0),
        'final_success_probability': getattr(result, 'final_success_probability', None),
        'cost_per_draw': getattr(result, 'cost_per_draw', None),
        'target_specs': dict(getattr(result, 'target_specs', {}) or {}),
    }
    # 三类结果页数据
    min_resource = getattr(result, 'min_resource', None)
    if min_resource is not None:
        out['min_resource'] = min_resource
    if getattr(result, 'binary_steps', None):
        out['binary_steps'] = [
            {'iteration': s.iteration, 'resource_value': s.resource_value,
             'success_probability': s.success_probability, 'phase': s.phase,
             'lo_bound': s.lo_bound, 'hi_bound': s.hi_bound}
            for s in result.binary_steps
        ]
    if getattr(result, 'points', None):
        out['points'] = [
            {'extra_resource': p.extra_resource, 'target_specs': dict(p.target_specs),
             'success_probability': p.success_probability}
            for p in result.points
        ]
    if getattr(result, 'forward_result', None):
        out['forward_result'] = _serialize_result(result.forward_result)
    if getattr(result, 'backward_result', None):
        out['backward_result'] = _serialize_result(result.backward_result)
    if getattr(result, 'pareto_points', None):
        out['pareto_points'] = [
            {'extra_resource': p.extra_resource, 'target_specs': dict(p.target_specs),
             'success_probability': p.success_probability}
            for p in result.pareto_points
        ]
    return out
