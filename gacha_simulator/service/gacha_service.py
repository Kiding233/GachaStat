from typing import Dict, List, Optional, Union
import time
import uuid
from ..core import (
    GachaState, Pool, DrawAction, WaitAction,
    InfoVector, Strategy, StrategyContext, StopCondition, TargetCardSet, ResourceGainFunction, CompactResult,
    SimulationCollector, InfoVectorCollector, CompactCollector,
)
from ..core.pity import PityEngine, PityState
from ..core.pool import NO_CARD_ID as _NO_CARD_ID, compute_bonus_resources


class SimulationStats:
    __slots__ = ('total_actions', 'total_draws', 'total_waits',
                 'total_resources_consumed', 'total_resources_gained',
                 'card_counts', 'pool_draw_counts', 'pity_triggers',             # ← P60：移除 acquired_counts
                 'last_draw_card_id', 'last_action_time',
                 'last_draw_pity_triggered')

    def __init__(self):
        self.total_actions = 0
        self.total_draws = 0
        self.total_waits = 0
        self.total_resources_consumed = {}
        self.total_resources_gained = {}
        self.card_counts = {}
        self.pool_draw_counts = {}
        self.pity_triggers = 0
        self.last_draw_card_id = None
        self.last_action_time = 0.0
        self.last_draw_pity_triggered = False

    def on_draw(self, card_id: str, pool_id: str, pity_triggered: bool = False):
        self.total_actions += 1
        self.total_draws += 1
        self.last_draw_card_id = card_id
        self.last_action_time += 1
        self.last_draw_pity_triggered = pity_triggered
        cc = self.card_counts
        cc[card_id] = cc.get(card_id, 0) + 1
        pc = self.pool_draw_counts
        pc[pool_id] = pc.get(pool_id, 0) + 1

    def on_wait(self, duration: float):
        self.total_actions += 1
        self.total_waits += 1
        self.last_action_time += duration


_EMPTY_DICT = {}


class GachaService:
    def __init__(
        self,
        pools: List[Pool],
        strategy: Strategy,
        stop_condition: StopCondition,
        target_cards: TargetCardSet,
        schedule_manager: Optional['PoolScheduleManager'] = None,  # noqa: F821
        resource_gain: Optional[ResourceGainFunction] = None,
        pity_engine: Optional[PityEngine] = None,
        pity_state: Optional[PityState] = None,
        ssr_ids: Optional[set] = None,
        card_defs: Optional[List] = None,
    ):
        self.pools = {p.id: p for p in pools}
        self.strategy = strategy
        self.stop_condition = stop_condition
        self.target_cards = target_cards
        self.schedule_manager = schedule_manager
        self.resource_gain = resource_gain
        self.pity_engine = pity_engine
        self.pity_state = pity_state or PityState()
        self.ssr_ids = ssr_ids or set()
        self.card_defs = card_defs or []
        self.session_id = str(uuid.uuid4())
        self._pools_list = list(self.pools.values())

    # ── P55：概率聚合（AUDIT-BREAK-8） ──

    def _aggregate_probs_by_rarity(self, pool_id: str, pool, pity_spec) -> Dict[str, float]:
        """将 {card_id: prob} 聚合为槽位级别概率。

        P55 feature-slot 分离：若 PoolPitySpec.featured_cards 存在，
        则将 featured 卡牌的概率拆入独立槽位（如 'ssr_featured'），
        而非与 standard 卡牌共享同一 'ssr' 槽位。
        """
        result: Dict[str, float] = {}
        rarity_cache: Dict[str, Optional[str]] = {}

        # 预构建 card_id → rarity 映射（仅 standard 卡——featured 单独处理）
        featured_ids: set = set()
        if pity_spec and pity_spec.featured_cards:
            for rarity, cards in pity_spec.featured_cards.items():
                for cid in cards:
                    featured_ids.add(cid)
        if pity_spec and pity_spec.scope_cards:
            for rarity, cards in pity_spec.scope_cards.items():
                for cid in cards:
                    if cid not in featured_ids:
                        rarity_cache[cid] = rarity

        for rwd, prob in pool.rewards:
            cid = rwd.id
            if cid in featured_ids:
                # featured → 独立槽位
                rarity = self._infer_rarity_from_spec(cid, pity_spec) or 'ssr'
                slot = f'{rarity}_featured'
            else:
                rarity = rarity_cache.get(cid)
                if rarity is None and pity_spec:
                    rarity = self._infer_rarity_from_spec(cid, pity_spec)
                if rarity:
                    slot = rarity.lower()
                else:
                    continue
            result[slot] = result.get(slot, 0.0) + prob

        return result

    @staticmethod
    def _infer_rarity_from_spec(card_id: str, pity_spec) -> Optional[str]:
        """从 PoolPitySpec 推断卡牌稀有度（大小写归一化）。"""
        cid = card_id.lower()
        if pity_spec.ssr_ids and cid in {c.lower() for c in pity_spec.ssr_ids}:
            return 'ssr'
        if pity_spec.featured_ids and cid in {c.lower() for c in pity_spec.featured_ids}:
            return 'ssr'
        return None

    def run_simulation(
        self,
        initial_state: GachaState,
        max_iterations: int = 100000,
        lightweight: bool = False,
        collector: Optional[SimulationCollector] = None,
    ) -> Union[List[InfoVector], CompactResult]:
        if collector is None:
            collector = InfoVectorCollector(
                session_id=self.session_id, lightweight=lightweight
            )

        state = initial_state.clone()
        pity_state = self.pity_state.clone()
        stats = SimulationStats()
        _initial_counts = {}
        for cd in self.card_defs:
            ic = cd.get('initial_count', 0) if isinstance(cd, dict) else getattr(cd, 'initial_count', 0)
            if ic > 0:
                cid = cd['card_id'] if isinstance(cd, dict) else cd.card_id
                _initial_counts[cid] = ic
        pools_list = self._pools_list
        real_time = state.real_time
        resources = state.resources
        _check = self.stop_condition.check
        _strategy = self.strategy
        _target_cards = self.target_cards
        _stop = self.stop_condition
        _pools = self.pools
        _schedule_mgr = self.schedule_manager
        _lookahead = self.strategy.lookahead
        _resource_gain = self.resource_gain
        _pity_engine = self.pity_engine
        _isinstance = isinstance
        _DrawAction = DrawAction
        _WaitAction = WaitAction
        _is_compact = isinstance(collector, CompactCollector)

        pool_end_times_sorted = sorted(
            [(p.id, p.available_until) for p in pools_list if p.available_until],
            key=lambda x: x[1]
        ) if _is_compact else []
        recorded_pool_ends = set() if _is_compact else None
        _pending_wait_gains = {} if _is_compact else None
        total_consumed = {} if _is_compact else None
        total_gained = {} if _is_compact else None

        for iteration in range(max_iterations):
            if _check(state, [], stats):
                break

            current_pools = [p for p in pools_list
                           if (p.available_from is None or real_time >= p.available_from)
                           and (p.available_until is None or real_time <= p.available_until)]

            future_schedules = []
            if _schedule_mgr and _lookahead:
                future_schedules = _schedule_mgr.get_future_schedules(real_time, _lookahead)

            ctx = StrategyContext(
                state=state,
                current_pools=current_pools,
                all_pools=pools_list,
                future_schedules=future_schedules,
                target_cards=_target_cards,
                stop_condition=_stop,
                _pity_engine=_pity_engine,
                _pity_state=pity_state,
                pool_draw_counts=dict(stats.pool_draw_counts),
                total_draws=stats.total_draws,
                last_draw_pity_triggered=stats.last_draw_pity_triggered,
                ssr_ids=self.ssr_ids,
            )

            action = _strategy.select_action(ctx)

            if _isinstance(action, _DrawAction):
                pool = _pools.get(action.pool_id)
                if not pool:
                    raise ValueError(f"Pool not found: {action.pool_id}")

                batch_size = max(getattr(pool, 'batch_size', 1), 1)

                # ── 原子预检查：batch_size 发可负担性 ──
                if not state.can_afford_batch(pool.cost, batch_size):
                    continue

                # ── 批次逐发执行 ──
                for _ in range(batch_size):
                    cost = pool.cost
                    spent = state.spend(cost)
                    if spent is None:
                        # 防御性：can_afford_batch 已预检查，不应发生
                        # 极端情况（奖励扣减导致中途枯竭）→ 停止本批次
                        break

                    probabilities = {r.id: p for r, p in pool.rewards}
                    if _pity_engine:
                        # P55：按稀有度聚合概率（AUDIT-BREAK-8）
                        pity_spec = _pity_engine.get_spec(pool.id)
                        rarity_probs = self._aggregate_probs_by_rarity(
                            pool.id, pool, pity_spec
                        ) if pity_spec else probabilities
                        # 使用聚合后的概率传给 engine
                        adjusted_rarity = _pity_engine.before_draw(
                            pool.id, pity_state, rarity_probs
                        )
                        # 从聚合概率还原为卡牌级别概率
                        if rarity_probs is not probabilities:
                            scale_factors = {}
                            for slot, new_total in adjusted_rarity.items():
                                old_total = rarity_probs.get(slot, 0)
                                if old_total > 0 and new_total != old_total:
                                    scale_factors[slot] = new_total / old_total
                            # 应用缩放因子到原始卡牌概率——区分 featured/standard 槽位
                            pity_spec = pity_spec or _pity_engine.get_spec(pool.id)
                            featured_ids = set()
                            if pity_spec and pity_spec.featured_cards:
                                for cards in pity_spec.featured_cards.values():
                                    featured_ids.update(cards)
                            for rwd_id in probabilities:
                                if rwd_id in featured_ids:
                                    slot = f'{self._infer_rarity_from_spec(rwd_id, pity_spec) or "ssr"}_featured'
                                else:
                                    rarity = self._infer_rarity_from_spec(rwd_id, pity_spec)
                                    slot = rarity.lower() if rarity else None
                                if slot and slot in scale_factors:
                                    probabilities[rwd_id] *= scale_factors[slot]
                        pool._apply_probabilities(probabilities)
                    else:
                        pool._apply_probabilities(probabilities)

                    reward = pool.draw()

                    # P55：pity_triggered 检测——基于 after_draw 的实际触发结果
                    # （使用 featured_ids 判定——等价于 CounterBasedBehavior._should_reset）
                    pity_triggered = False
                    triggered_pity_name = None

                    if _pity_engine:
                        _pity_engine.after_draw(pool.id, pity_state, reward.id)
                        # 保底触发判定：本次抽到的卡满足重置条件（featured SSR）
                        spec = _pity_engine.get_spec(pool.id)
                        if spec and reward.id in spec.featured_ids and spec.pity_names:
                            pity_triggered = True
                            triggered_pity_name = ','.join(spec.pity_names)

                    # 池级保底计数器最大值（供 collector 记录）
                    pool_spec = _pity_engine.get_spec(pool.id) if _pity_engine else None
                    pool_counter_max = 0
                    if pool_spec:
                        for pname in pool_spec.pity_names:
                            cv = _pity_engine.get_counter(pname) if _pity_engine else pity_state.get(pname, 'counter', 0)
                            pool_counter_max = max(pool_counter_max, cv)

                    stats.on_draw(reward.id, pool.id, pity_triggered)
                    # P60：卡片计入 state.acquired（一等公民）——替代旧 stats.acquired_counts
                    if reward.id != _NO_CARD_ID:
                        state.add_card(reward.id)

                    if pity_triggered:
                        stats.pity_triggers += 1

                    rg = dict(reward.resources_gained or {})
                    if reward.first_time_bonus or reward.nth_time_bonus or reward.excess_bonus:
                        ac_new = state.get_card_count(reward.id)          # ← P60：从 state 读取
                        init = _initial_counts.get(reward.id, 0)
                        total_before = init + ac_new - 1
                        total_after = init + ac_new
                        bonus = compute_bonus_resources(reward, total_before, total_after)
                        for k, v in bonus.items():
                            rg[k] = rg.get(k, 0) + v
                    if rg:
                        for k, v in rg.items():
                            resources[k] = resources.get(k, 0) + v

                    if _is_compact:
                        for k, v in spent.items():
                            total_consumed[k] = total_consumed.get(k, 0) + v
                        if rg:
                            for k, v in rg.items():
                                total_gained[k] = total_gained.get(k, 0) + v
                        combined_gained = dict(rg)
                        for k, v in _pending_wait_gains.items():
                            combined_gained[k] = combined_gained.get(k, 0) + v
                        _pending_wait_gains.clear()
                    else:
                        combined_gained = rg.copy() if rg else _EMPTY_DICT

                    collector.on_draw(
                        card_id=reward.id, pool=pool, spent=spent,
                        resources_gained=rg, pity_triggered=pity_triggered,
                        triggered_pity_name=triggered_pity_name,
                        pity_counter_max=pool_counter_max,
                        real_time=real_time, pity_state=pity_state,
                        combined_gained=combined_gained,
                    )

            elif _isinstance(action, _WaitAction):
                rt_before = real_time
                real_time += action.duration
                state.real_time = real_time

                rg = {}
                if _resource_gain:
                    rg = _resource_gain.compute(action.duration, state)
                    for k, v in rg.items():
                        resources[k] = resources.get(k, 0) + v
                    if _is_compact:
                        for k, v in rg.items():
                            total_gained[k] = total_gained.get(k, 0) + v
                            _pending_wait_gains[k] = _pending_wait_gains.get(k, 0) + v

                if _is_compact:
                    for pid, pet in pool_end_times_sorted:
                        if pid not in recorded_pool_ends and real_time >= pet:
                            collector.on_pool_end(pid, dict(resources), pity_state.to_dict())
                            recorded_pool_ends.add(pid)

                stats.on_wait(action.duration)

                collector.on_wait(
                    duration=action.duration, resources_gained=rg,
                    real_time_before=rt_before, real_time_after=real_time,
                )

            else:
                raise ValueError(f"Unknown action type: {action}")

            if _is_compact:
                for pid, pet in pool_end_times_sorted:
                    if pid not in recorded_pool_ends and real_time >= pet:
                        collector.on_pool_end(pid, dict(resources), pity_state.to_dict())
                        recorded_pool_ends.add(pid)

        state.real_time = real_time
        state.resources = resources

        if _is_compact:
            for pid, pet in pool_end_times_sorted:
                if pid not in recorded_pool_ends and real_time >= pet:
                    collector.on_pool_end(pid, dict(resources), pity_state.to_dict())
                    recorded_pool_ends.add(pid)

            result = collector.get_result()
            result.total_consumed = total_consumed
            result.total_gained = total_gained
            result.total_draws = stats.total_draws
            result.total_waits = stats.total_waits
            result.pity_triggers = stats.pity_triggers
            result.final_resources = dict(resources)
            result.final_time = real_time
            result.pool_types = {pid: p.pool_type for pid, p in self.pools.items()}
            result.strategy_name = type(self.strategy).__name__
            result.generated_at = time.time()
            return result

        return collector.get_result()

    def run_simulation_compact(
        self, initial_state: GachaState, max_iterations: int = 100000,
    ) -> CompactResult:
        return self.run_simulation(
            initial_state, max_iterations=max_iterations,
            collector=CompactCollector(),
        )
