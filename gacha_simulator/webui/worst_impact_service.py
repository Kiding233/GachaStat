"""最差影响服务（新 UI：分析→生成配置→用户跑模拟→新池子数分析 三步）。

worst_config（生成后续池子配置）：
  按原 UI 参数（条件/GDR/阈值/α/自定义资源/持续天数/单抽消耗/卡牌分布）计算最差资源
  （条件资源分布 α 分位），构建 99 个后续虚拟池配置（worst_impact.prepare_simulation_config
  同构）→ TOML 文本。用户保存为派生配置 → 创建模拟任务跑它（旧版「面板内临时配置」提升为可复用配置）。

worst_dist（新池子数分布）：
  分析「后续池子配置跑出的 dataset」——每条模拟连续命中 featured 卡（_wi_featured_{i}）的
  池数 k 分布（复用 worst_impact.analyze_batch_results）。
"""
from __future__ import annotations

import numpy as np

from gacha_simulator.core.worst_impact import WorstImpactAnalyzer, ConditionalResourceDistribution, MAX_POOLS
from gacha_simulator.core.gdr import is_resource_gdr
from gacha_simulator.visualization.chart_spec import ChartSpec, BarData
from gacha_simulator.core.config_store import ConfigStore, BannerEntry, BannerPoolEntry, TargetCardEntry


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


def _make_analyzer(dataset, store, params):
    agg = dataset.get('aggregate_data', []) or []
    target_specs = dict(dataset.get('target_specs', {}) or {})
    gdr_key = params.get('gdr', 'resource_remaining')
    gdr_threshold = float(params.get('threshold', 1.0))
    custom_pool = None
    if params.get('duration') or params.get('cost') or params.get('distribution'):
        custom_pool = {
            'duration_days': int(params.get('duration', 21)),
            'cost': params.get('cost', 'draw_resource:160'),
            'distribution': params.get('distribution', []) or [],
        }
    return WorstImpactAnalyzer(agg, target_specs, store, gdr_key=gdr_key,
                               gdr_threshold=gdr_threshold, custom_pool_config=custom_pool)


def generate_worst_config(dataset, store, params: dict) -> dict:
    """生成后续池子配置 → TOML 文本（worst_config 方法块）。"""
    try:
        analyzer = _make_analyzer(dataset, store, params)
        analyzer._prepare_pool_info()
        if analyzer.custom_pool_config and analyzer.custom_pool_config.get('distribution'):
            analyzer._apply_custom_pool_config()
        condition = params.get('cond', 'failure')
        alpha = float(params.get('alpha', 0.05))
        custom_resource = params.get('customResource', '')
        if custom_resource not in (None, ''):
            try:
                worst_resource = float(custom_resource)
            except (ValueError, TypeError):
                worst_resource = None
        else:
            worst_resource = None
        if worst_resource is None:
            checker = analyzer._build_success_checker(target_specs=analyzer.target_specs,
                                                      ssr_ids=analyzer._main_ssr_ids)
            cond_dist = ConditionalResourceDistribution(
                analyzer.simulation_results, checker.is_success, resource=analyzer._resource_name)
            skip_evt = is_resource_gdr(analyzer.gdr_key) and condition == 'success'
            worst_resource = cond_dist.get_worst_case_resource(condition, alpha, use_evt=not skip_evt)
        # 防御：非有限值（失败样本为空 / EVT 外推失败）时逐级回退
        if worst_resource is None or not np.isfinite(worst_resource):
            # 回退 1：全部样本的 α 分位（关闭 EVT）
            cd_all = ConditionalResourceDistribution(
                analyzer.simulation_results, (lambda r: True), resource=analyzer._resource_name)
            fallback = cd_all.get_worst_case_resource('all', alpha, use_evt=False)
            if fallback is not None and np.isfinite(fallback):
                worst_resource = fallback
            else:
                # 回退 2：失败样本中位数，再退到全部中位数
                res_all = [r.get('final_resources', {}).get(analyzer._resource_name, 0.0)
                           for r in analyzer.simulation_results]
                median = float(np.median(res_all)) if res_all else 0.0
                worst_resource = median if np.isfinite(median) else 0.0
        pity_coverage = analyzer._compute_pity_coverage(worst_resource)
        sim_config = analyzer.prepare_simulation_config(worst_resource)
        config_text = _build_pool_config_text(sim_config, worst_resource)
        return {
            'ok': True,
            'config_text': config_text,
            'worst_resource': worst_resource,
            'pity_coverage': pity_coverage,
            'meta': {'condition': condition, 'alpha': alpha, 'num_pools': MAX_POOLS,
                     'resource_name': analyzer._resource_name,
                     'cost': analyzer._parsed_cost},
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'ok': False, 'error': str(e)}


def _build_pool_config_text(sim_config, worst_resource) -> str:
    """sim_config（SimulationEnv dict，含 List[Banner]）→ ConfigStore → TOML 文本。"""
    store = ConfigStore()
    store.initial_resources = {'draw_resource': worst_resource}
    cost_str = 'draw_resource:160'
    for b in sim_config['pools']:
        entry = BannerEntry(id=b.id, name=b.name, enabled=True,
                            available_from=b.available_from, available_until=b.available_until,
                            pools=[], lifecycle=[])
        for pk, p in b.pools.items():
            rewards = []
            for r, prob in p.rewards:
                rewards.append({
                    'card_id': r.id,
                    'probability': round(float(prob) * 100, 4),
                    'rarity': (r.extra_info or {}).get('rarity', 'r'),
                    'featured': bool((r.extra_info or {}).get('featured', False)),
                    'resources_gained': dict(r.resources_gained or {}),
                })
            entry.pools.append(BannerPoolEntry(
                id=pk, cost=cost_str, batch_size=1, excludes_all_pity=False,
                max_draws=0, exchange_card_id=None, epitomizable_cards=[], rewards=rewards,
            ))
        store.banner.banners.append(entry)
    store.target_cards = [TargetCardEntry(card_id=fid, quantity=1, pool_ids=[])
                          for fid in sim_config.get('target_specs', {})]
    store.strategy_key = 'draw_target'
    store.strategy_params = {'pool_id': ''}
    import tempfile
    import os
    from gacha_simulator.core.config_toml import save_toml
    fd, path = tempfile.mkstemp(suffix='.toml')
    try:
        os.close(fd)
        save_toml(store, path)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        return text
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def analyze_worst_dist(dataset, store, params: dict) -> dict:
    """新池子数分布（worst_dist 方法块）——分析「后续池子配置跑出的 dataset」。"""
    try:
        agg = dataset.get('aggregate_data', []) or []
        analyzer = WorstImpactAnalyzer(agg, dict(dataset.get('target_specs', {}) or {}), store,
                                       gdr_key=params.get('gdr', 'target_achievement'),
                                       gdr_threshold=float(params.get('threshold', 1.0)))
        result = analyzer.analyze_batch_results(agg, len(agg))
        dist = result['distribution']
        expected = result['expected']
        sections = []
        # gauge：大保底资源覆盖（worst 资源不可重算——用 dataset 的初始资源近似）
        init_res = (dataset.get('initial_resources') or {}).get('draw_resource', 0)
        sections.append({'key': 'summary', 'title': '新池子数分布',
                         'items': {'期望连续新池子数': f'{expected:.2f}',
                                   '初始资源': f'{init_res:.0f}',
                                   '模拟数': len(agg)}})
        # 柱状图
        ks = sorted(dist.keys())
        bars = ChartSpec(chart_type='bar', data=BarData(
            labels=[f'k={k}' for k in ks], values=np.array([dist[k] for k in ks])),
            title='新池子数分布', xlabel='连续成功池数 k', ylabel='概率')
        sections.append({'key': 'chart', 'title': 'P(X=k) 分布', 'spec': _spec_to_dict(bars)})
        # 详情表
        cum = 0.0
        rows = []
        for k in ks:
            cum += dist[k]
            p_ge = sum(dist[j] for j in ks if j >= k)
            rows.append([str(k), f'{dist[k]:.4f}', f'{p_ge:.4f}', f'{cum:.4f}'])
        sections.append({'key': 'table', 'title': '分布详情',
                         'headers': ['k', 'P(X=k)', 'P(X≥k)', '累计概率'], 'rows': rows})
        return {'ok': True, 'sections': sections, 'expected': expected, 'distribution': dist}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'ok': False, 'error': str(e), 'sections': []}
