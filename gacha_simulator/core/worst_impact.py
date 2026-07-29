from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Set
from collections import defaultdict

from .distribution import EmpiricalDistribution
from .pool import Pool, Reward, parse_cost_string
from .pity import (
    PityEngine, PoolPitySpec, PityState,
    compute_scope_mappings,
)
from .stop_condition import ConsecutivePoolTargetCondition
from .schedule import PoolSchedule, PoolScheduleManager

import fnmatch
import os


DAY = 86400
MAX_POOLS = 99


class ConditionalResourceDistribution:
    def __init__(self, simulation_results, success_checker,
                 resource='draw_resource'):
        self.success_resources: List[float] = []
        self.failure_resources: List[float] = []

        for r in simulation_results:
            is_success = success_checker(r)
            final_res = r.get('final_resources', {})
            res_val = final_res.get(resource, 0.0)

            if is_success:
                self.success_resources.append(res_val)
            else:
                self.failure_resources.append(res_val)

    def get_conditional_distribution(self, condition='all', use_evt=True):
        if condition == 'success':
            samples = self.success_resources
        elif condition == 'failure':
            samples = self.failure_resources
        else:
            samples = self.success_resources + self.failure_resources
        return EmpiricalDistribution(samples)

    def get_worst_case_resource(self, condition='all', alpha=0.05, use_evt=True):
        dist = self.get_conditional_distribution(condition, use_evt=use_evt)
        return dist.quantile(alpha, use_evt=use_evt)


@dataclass
class WorstImpactResult:
    worst_resource: float
    pity_coverage: float
    pool_distribution: Dict[int, float] = field(default_factory=dict)
    expected_pools: float = 0.0

    def get_p_ge(self, k: int) -> float:
        return sum(p for kk, p in self.pool_distribution.items() if kk >= k)

    def get_max_consecutive_at_threshold(self, threshold: float) -> int:
        for k in sorted(self.pool_distribution.keys(), reverse=True):
            if self.get_p_ge(k) >= threshold:
                return k
        return 0


class WorstImpactAnalyzer:
    def __init__(self, simulation_results, target_specs, store,
                 gdr_key='all_targets', gdr_threshold=1.0,
                 custom_pool_config=None):
        self.simulation_results = simulation_results
        self.target_specs = target_specs
        self.store = store
        self.gdr_key = gdr_key
        self.gdr_threshold = gdr_threshold
        self.custom_pool_config = custom_pool_config
        self.cond_dist = None
        self._pity_engine = None
        self._ref_pool_entry = None
        self._featured_ids: Set[str] = set()
        self._ssr_ids: Set[str] = set()
        self._standard_ssr_ids: Set[str] = set()
        self._featured_prob: float = 0.0
        self._pool_duration = 21 * DAY
        self._parsed_cost = [{'draw_resource': 160}]
        self._resource_name = 'draw_resource'
        self._rewards = []
        self._main_ssr_ids: Set[str] = set()
        for cd in store.card_defs:
            if getattr(cd, 'rarity', '').upper() == 'SSR':
                self._main_ssr_ids.add(cd.card_id)
        if not self._main_ssr_ids:
            for pe in store.pools:
                for de in getattr(pe, 'distribution', []):
                    if getattr(de, 'rarity', '').upper() == 'SSR' and de.card_id != '_no_card':
                        self._main_ssr_ids.add(de.card_id)

    def analyze(self, condition='failure', alpha=0.05,
                num_simulations=500, progress_callback=None,
                custom_resource=None):
        self._prepare_pool_info()

        if custom_resource is not None:
            worst_resource = float(custom_resource)
        else:
            main_checker = self._build_success_checker(
                target_specs=self.target_specs,
                ssr_ids=self._main_ssr_ids,
            )
            self.cond_dist = ConditionalResourceDistribution(
                self.simulation_results, main_checker.is_success,
                resource=self._resource_name,
            )
            from .gdr import is_resource_gdr
            # 资源类 GDR + success 条件时，成功组资源被下界截断，EVT 外推可能越界
            _skip_evt = (
                is_resource_gdr(self.gdr_key)
                and condition == 'success'
            )
            worst_resource = self.cond_dist.get_worst_case_resource(
                condition, alpha, use_evt=not _skip_evt,
            )

        pity_coverage = self._compute_pity_coverage(worst_resource)

        sim_config = self.prepare_simulation_config(worst_resource)

        from .streaming import SharedResultCollector, extract_aggregate
        collector = SharedResultCollector()
        collector.add_extractor('aggregate', extract_aggregate)

        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder, run_batch_parallel

        sim_env = SimulationEnvBuilder.from_dict(sim_config)

        run_batch_parallel(
            env=sim_env,
            target_specs=sim_config['target_specs'],
            initial_resources=sim_config['initial_resources'],
            num_simulations=num_simulations,
            max_workers=os.cpu_count() or 4,
            seed=42,
            progress_callback=lambda done, total: progress_callback(
                f"模拟中: {done}/{total}", int(done / total * 100)
            ) if progress_callback else None,
            strategy_key='draw_target',
            strategy_params={'pool_id': ''},
            on_result=collector.on_result,
        )

        aggregate_data = collector.get_extracted('aggregate')
        result = self.analyze_batch_results(aggregate_data, num_simulations)

        return WorstImpactResult(
            worst_resource=worst_resource,
            pity_coverage=pity_coverage,
            pool_distribution=result['distribution'],
            expected_pools=result['expected'],
        )

    def prepare_simulation_config(self, worst_resource: float) -> dict:
        self._prepare_pool_info()

        pools = []
        schedules = []
        pool_targets = {}
        pool_schedules_list = []
        all_featured_ids = set()
        all_ssr_ids = set()
        card_defs = []

        for i in range(MAX_POOLS):
            pid = f'_worst_impact_pool_{i}'
            featured_id = f'_wi_featured_{i}'

            new_rewards = []
            for r, prob in self._rewards:
                if r.id in self._featured_ids:
                    new_r = Reward(
                        id=featured_id,
                        name=f'限定#{i}',
                        resources_gained=dict(r.resources_gained) if r.resources_gained else {},
                        extra_info=dict(r.extra_info) if r.extra_info else {},
                    )
                    new_rewards.append((new_r, prob))
                else:
                    new_rewards.append((r, prob))

            start_time = i * self._pool_duration
            end_time = (i + 1) * self._pool_duration

            pool = Pool(
                id=pid,
                name=f'新池子#{i}',
                cost=self._parsed_cost,
                rewards=new_rewards,
                available_from=start_time,
                available_until=end_time,
            )
            pools.append(pool)
            schedules.append(PoolSchedule(
                pool_id=pid,
                available_from=start_time,
                available_until=end_time,
            ))
            pool_targets[pid] = featured_id
            pool_schedules_list.append((pid, start_time, end_time))
            all_featured_ids.add(featured_id)
            all_ssr_ids.add(featured_id)
            card_defs.append({
                'card_id': featured_id,
                'name': f'限定#{i}',
                'rarity': 'SSR',
                'pools': [pid],
            })

        for r, prob in self._rewards:
            if r.id not in self._featured_ids:
                rarity = r.extra_info.get('rarity', '').upper()
                if rarity == 'SSR':
                    all_ssr_ids.add(r.id)
                card_defs.append({
                    'card_id': r.id,
                    'name': r.name or r.id,
                    'rarity': rarity,
                    'pools': [p.id for p in pools],
                })

        schedule_mgr = PoolScheduleManager(schedules)
        total_end_time = MAX_POOLS * self._pool_duration

        target_specs = {fid: 1 for fid in all_featured_ids}

        stop_condition = ConsecutivePoolTargetCondition(
            pool_schedules=pool_schedules_list,
            pool_targets=pool_targets,
            resource_name=self._resource_name,
            end_time=total_end_time,
        )

        pity_engine = self._build_pity_engine(all_featured_ids, all_ssr_ids, pool_targets)

        pity_state_init = None
        init_pity = self._get_initial_pity_state()
        if init_pity:
            # P60 方案 A——构造初始 PityState 后序列化
            ps_init = PityState()
            for cname, cval in init_pity.items():
                ps_init.set(cname, 'counter', cval)
            pity_state_init = ps_init.to_dict()

        return {
            'pools': pools,
            'schedule_mgr': schedule_mgr,
            'end_time': total_end_time,
            'pity_engine': pity_engine,
            'resource_gain': None,
            'pity_state_init': pity_state_init,
            'card_defs': card_defs,
            'target_specs': target_specs,
            'initial_resources': {self._resource_name: worst_resource},
            'ssr_ids': all_ssr_ids,
            'stop_condition': stop_condition,
            'pool_targets': pool_targets,
        }

    def analyze_batch_results(self, aggregate_data: list, num_simulations: int = 0) -> dict:
        success_counts = defaultdict(int)

        for result in aggregate_data:
            card_counts = result.get('card_counts', {})
            consecutive = 0
            for i in range(MAX_POOLS):
                featured_id = f'_wi_featured_{i}'
                if card_counts.get(featured_id, 0) >= 1:
                    consecutive += 1
                else:
                    break
            success_counts[consecutive] += 1

        n = num_simulations if num_simulations > 0 else (len(aggregate_data) or 1)
        n_failed = n - len(aggregate_data)
        if n_failed > 0:
            success_counts[0] += n_failed

        distribution = {k: count / n for k, count in sorted(success_counts.items())}
        expected = sum(k * prob for k, prob in distribution.items())

        return {'distribution': distribution, 'expected': expected}

    def _compute_pity_coverage(self, resource):
        pity_cost = self._get_pity_cost()
        return resource / pity_cost if pity_cost > 0 else float('inf')

    def _build_success_checker(self, target_specs=None, ssr_ids=None):
        from .gdr import make_gdr_calculator
        self._checker = make_gdr_calculator(
            self.store,
            target_specs or self.target_specs,
            self.gdr_key,
            gdr_threshold=self.gdr_threshold,
            ssr_ids=ssr_ids or self._ssr_ids,
        )
        return self._checker

    @staticmethod
    def _get_pity_end(pdef) -> int:
        """从 P55 新字段推导保底所需的抽数上限。"""
        if pdef.threshold is not None:
            return pdef.threshold
        if getattr(pdef, 'deltas', None) is not None:
            return sum(n for n, _ in pdef.deltas)
        if getattr(pdef, 'soft_end', None) is not None:
            return pdef.soft_end
        return 90  # 兜底默认值

    def _get_pity_cost(self):
        if not self.store.pity.enabled or not self.store.pity.pities:
            return 90 * 160
        # 取所有 PityDef 中最大的 end 值（替代仅读 pities[0]）
        max_end = max((self._get_pity_end(p) for p in self.store.pity.pities), default=90)
        cost = 160
        if self.store.pools:
            c = self.store.pools[0].cost
            if isinstance(c, str) and ':' in c:
                try:
                    cost = int(c.split(':')[1])
                except ValueError:
                    pass
        return max_end * cost

    def _prepare_pool_info(self):
        if self.custom_pool_config and self.custom_pool_config.get('distribution'):
            self._apply_custom_pool_config()
            return

        pool_entries = [pe for pe in self.store.pools if pe.enabled]
        if not pool_entries:
            return

        self._ref_pool_entry = pool_entries[-1]
        pe = self._ref_pool_entry

        cost_str = getattr(pe, 'cost', 'draw_resource:160')
        self._parsed_cost = parse_cost_string(cost_str)
        # 优先从 gdr_key 解析 resource_id；解析失败则从 cost 字段提取；最终回退 'draw_resource'
        from .gdr import parse_gdr_key
        _, parsed_rid = parse_gdr_key(self.gdr_key)
        if parsed_rid != 'draw_resource' and self._parsed_cost and parsed_rid in self._parsed_cost[0]:
            self._resource_name = parsed_rid
        else:
            self._resource_name = list(self._parsed_cost[0].keys())[0] if self._parsed_cost else 'draw_resource'

        rewards = []
        if pe.distribution:
            for de in pe.distribution:
                r = Reward(
                    id=de.card_id,
                    name='',
                    resources_gained=dict(de.resources_gained) if de.resources_gained else {},
                    extra_info={'rarity': de.rarity, 'featured': de.featured},
                )
                prob = de.probability
                rewards.append((r, prob))

        self._featured_ids = set()
        self._ssr_ids = set()
        self._featured_prob = 0.0
        for r, prob in rewards:
            rarity = r.extra_info.get('rarity', '').upper()
            featured = r.extra_info.get('featured', False)
            if rarity == 'SSR':
                self._ssr_ids.add(r.id)
                if featured:
                    self._featured_ids.add(r.id)
                    self._featured_prob += prob

        if not self._featured_ids and self._ssr_ids:
            self._featured_ids = set(self._ssr_ids)
            self._featured_prob = sum(
                prob for r, prob in rewards
                if r.id in self._ssr_ids
            )

        self._standard_ssr_ids = self._ssr_ids - self._featured_ids

        pool_duration_days = pe.end_day - pe.start_day
        if pool_duration_days <= 0:
            pool_duration_days = 21

        self._pool_duration = pool_duration_days * DAY
        self._rewards = rewards

    def _apply_custom_pool_config(self):
        cfg = self.custom_pool_config
        duration_days = cfg.get('duration_days', 21)
        self._pool_duration = duration_days * DAY

        cost_str = cfg.get('cost', 'draw_resource:160')
        self._parsed_cost = parse_cost_string(cost_str)
        from .gdr import parse_gdr_key
        _, parsed_rid = parse_gdr_key(self.gdr_key)
        if parsed_rid != 'draw_resource' and self._parsed_cost and parsed_rid in self._parsed_cost[0]:
            self._resource_name = parsed_rid
        else:
            self._resource_name = list(self._parsed_cost[0].keys())[0] if self._parsed_cost else 'draw_resource'

        rewards = []
        for d in cfg.get('distribution', []):
            r = Reward(
                id=d.get('card_id', ''),
                name='',
                resources_gained=d.get('resources_gained', {}),
                extra_info={'rarity': d.get('rarity', 'R'), 'featured': d.get('featured', False)},
            )
            rewards.append((r, d.get('probability', 0.0)))

        self._featured_ids = set()
        self._ssr_ids = set()
        self._featured_prob = 0.0
        for r, prob in rewards:
            rarity = r.extra_info.get('rarity', '').upper()
            featured = r.extra_info.get('featured', False)
            if rarity == 'SSR':
                self._ssr_ids.add(r.id)
                if featured:
                    self._featured_ids.add(r.id)
                    self._featured_prob += prob

        if not self._featured_ids and self._ssr_ids:
            self._featured_ids = set(self._ssr_ids)
            self._featured_prob = sum(
                prob for r, prob in rewards
                if r.id in self._ssr_ids
            )

        self._standard_ssr_ids = self._ssr_ids - self._featured_ids
        self._rewards = rewards

    def _build_pity_engine(self, all_featured_ids=None, all_ssr_ids=None, pool_targets=None):
        if not self.store.pity.enabled:
            return None

        # P55：从扁平化 PityDef 构造引擎
        is_new_format = any(hasattr(pd, 'scope') and not hasattr(pd, 'params')
                           for pd in self.store.pity.pities)

        if is_new_format:
            from gacha_simulator.core.config_store import PityDef as _PityDef
            pity_defs_list = []
            for pd in self.store.pity.pities:
                if not isinstance(pd, _PityDef):
                    continue
                # shallow copy via dataclass fields
                pity_defs_list.append(pd)

            state = PityState()
            from gacha_simulator.core.pity import _build_pity_state_init
            state = _build_pity_state_init(pity_defs_list)

            # P55 ISSUE-032：从参考池或已知 ID 构建 scope 映射
            ref_pool = getattr(self, '_ref_pool', None)
            if ref_pool and hasattr(ref_pool, 'rewards'):
                scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot = compute_scope_mappings(ref_pool)
            else:
                scope_cards = {'ssr': tuple(self._ssr_ids)} if self._ssr_ids else {}
                featured_cards = {'ssr': tuple(self._featured_ids)} if self._featured_ids else {}
                card_to_slot = {}
                if self._ssr_ids and self._featured_ids:
                    scope_slots = {'ssr': ('ssr', 'ssr_featured')}
                    featured_slots = {'ssr': ('ssr_featured',)}
                    for cid in self._featured_ids:
                        card_to_slot[cid] = 'ssr_featured'
                    for cid in (self._ssr_ids - self._featured_ids):
                        card_to_slot[cid] = 'ssr'
                else:
                    scope_slots = {'ssr': ('ssr',)} if self._ssr_ids else {}
                    featured_slots = {'ssr': ('ssr',)} if self._featured_ids else {}
                    for cid in self._ssr_ids:
                        card_to_slot[cid] = 'ssr'

            pool_specs = {}
            for pool_idx in range(MAX_POOLS):
                pid = f'_worst_impact_pool_{pool_idx}'
                matching = []
                for pdef in pity_defs_list:
                    pools_ptn = getattr(pdef, 'pools', ('*',))
                    if pools_ptn == ('*',) or any(fnmatch.fnmatch(pid, ptn) for ptn in pools_ptn):
                        matching.append(pdef.name)

                pool_featured = {f'_wi_featured_{pool_idx}'} if all_featured_ids else self._featured_ids
                pool_ssr = (pool_featured | self._standard_ssr_ids) if all_ssr_ids else self._ssr_ids

                pool_specs[pid] = PoolPitySpec(
                    pity_names=matching,
                    featured_ids=pool_featured,
                    ssr_ids=pool_ssr,
                    scope_cards=scope_cards,
                    featured_cards=featured_cards,
                    scope_slots=scope_slots,
                    featured_slots=featured_slots,
                card_to_slot=card_to_slot,
                )

            rr = {k.lower(): v for k, v in self.store.rarity_rank.items()} if hasattr(self, 'store') and self.store else {'ssr': 0, 'sr': 1, 'r': 2}
            return PityEngine(pool_specs, pity_defs_list,
                            state=state, rarity_rank=rr)

    def _get_initial_pity_state(self):
        if not self.store.pity.enabled:
            return {}
        state = {}
        # P55：counter_init 已从 PityConfig 移至每个 PityDef
        for pdef in self.store.pity.pities:
            ci = getattr(pdef, 'counter_init', 0)
            if ci > 0:
                state[pdef.name] = ci
        return state
