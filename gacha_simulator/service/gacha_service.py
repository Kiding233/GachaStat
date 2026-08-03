from typing import Dict, List, Optional, Union
import time
import uuid
from ..core import (
    Banner, GachaState, Pool, DrawAction, WaitAction, NonDrawAction,
    InfoVector, Strategy, StopCondition, TargetCardSet, ResourceGainFunction, CompactResult,
    build_strategy_context,
    SimulationCollector, InfoVectorCollector, CompactCollector,
)
from ..core.action import NON_DRAW_ACTION_REGISTRY, InvalidActionError
from ..core.pity import PityEngine, PityState
from ..core.pool import NO_CARD_ID as _NO_CARD_ID
from ..core.notifier import Notifier


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


def _derive_pool_type(pool) -> str:
    """由 output/random 推导属性映射回旧 pool_type 三值（§3.13.1，ISSUE-002）。

    output='resource' → '资源'；output='card' and not random → '兑换'；其余 → '角色'。
    """
    if pool.output == 'resource':
        return '资源'
    if pool.output == 'card' and not pool.random:
        return '兑换'
    return '角色'


class GachaService:
    def __init__(
        self,
        pools: List[Union[Pool, Banner]],
        strategy: Strategy,
        stop_condition: StopCondition,
        target_cards: TargetCardSet,
        schedule_manager: Optional['PoolScheduleManager'] = None,  # noqa: F821
        resource_gain: Optional[ResourceGainFunction] = None,
        pity_engine: Optional[PityEngine] = None,
        pity_state: Optional[PityState] = None,
        ssr_ids: Optional[set] = None,
        card_defs: Optional[List] = None,
        card_overflow_map: Optional[Dict[str, list]] = None,
        notifier: Optional[Notifier] = None,  # P61 Ph0：装配层注入共享实例，None 时服务内 fallback 自建
    ):
        # ── P61（§3.5 要点 10）：构造桥——双型收纳为运行时 Banner 字典 ──
        # 元素为 Pool → 就地单池包装 Banner(id=p.id, pools={'main': p})（原子提交→Ph6 间
        #   时间窗口 None 兜底，§3.13.4 / ISSUE-102）；
        # 元素为 Banner → 直接收纳 {b.id: b}（Ph6 后 from_config_store 构建 List[Banner]）。
        self._banners: Dict[str, Banner] = {}
        # 裸 pool_id → Banner 反查表（仅唯一映射时建立——多 Banner 同名池不登记，
        # banner_id=None 时反查歧义已由 Ph1a 强制双字段规避，ISSUE-316）
        self._pool_id_to_banner: Dict[str, Banner] = {}
        for p in pools:
            if isinstance(p, Banner):
                self._banners[p.id] = p
            else:
                banner = Banner(id=p.id, name=p.name, pools={'main': p})
                self._banners[p.id] = banner
                self._pool_id_to_banner[p.id] = banner

        self.strategy = strategy
        self.stop_condition = stop_condition
        self.target_cards = target_cards
        self.schedule_manager = schedule_manager
        self.resource_gain = resource_gain
        self.pity_engine = pity_engine
        self.pity_state = pity_state or PityState()
        self.ssr_ids = ssr_ids or set()
        self.card_defs = card_defs or []
        self.card_overflow_map = card_overflow_map or {}
        self._notifier = notifier or Notifier()
        self.session_id = str(uuid.uuid4())
        # ── P61（Ph2）：单抽粒度 after_draw 订阅——生命周期转换唯一触发点之一 ──
        # priority=1：P58 以 priority=0 订阅（里程碑资源注入先执行），P61 转换后执行。
        # handler 透传 card_id / state.real_time（card_obtained / time_window 求值输入，ISSUE-001）。
        self._notifier.subscribe("after_draw", self._on_banner_after_draw, priority=1)

    # ── P61：Banner 生命周期转换订阅 handler（§3.5「Notifier 装配位置」/ ISSUE-001）──

    def _on_banner_after_draw(self, banner_id, card_id, state, **kw):
        """after_draw 事件订阅——评估该 Banner 的全部 lifecycle 转换（边缘触发）。"""
        banner = self._banners.get(banner_id)
        if banner is None:
            return
        banner._check_transitions(card_id=card_id, real_time=state.real_time)

    # ── P56：非抽卡动作（定轨切换/取消） ──

    def _apply_non_draw(self, action, banners, pity_engine, pity_state):
        """P56：执行 NonDrawAction——定轨切换/取消。"""
        from ..core.pity import TargetedBehavior
        if action.action_id not in NON_DRAW_ACTION_REGISTRY:
            raise InvalidActionError(f"未注册的 NonDrawAction action_id: '{action.action_id}'")
        pool_id = action.params.get('pool_id')
        if not pool_id:
            raise InvalidActionError("NonDrawAction 缺少 'pool_id'")
        # P61（§3.5 要点 5 / ISSUE-006）：定位 Banner——banner_id 优先，否则全限定/裸 pool_id 反查
        banner_id = action.params.get('banner_id')
        banner = None
        if banner_id:
            banner = banners.get(banner_id)
        elif '.' in pool_id:
            bid, _key = pool_id.split('.', 1)
            banner = banners.get(bid)
        else:
            banner = self._pool_id_to_banner.get(pool_id)
        if banner is None:
            raise InvalidActionError(f"NonDrawAction 引用了不存在的池子 '{pool_id}'")
        pool = banner.active_pool
        qualified_key = f"{banner.id}.{banner.active_pool_id}"
        targeted_name = None
        for pname, bh in pity_engine.get_behaviors_for_pool(qualified_key):
            if isinstance(bh, TargetedBehavior):
                targeted_name = pname
                break
        if targeted_name is None:
            raise InvalidActionError(f"池子 '{qualified_key}' 未配置 targeted 保底")
        if action.action_id == 'switch_epitomized_target':
            card_id = action.params.get('card_id')
            if not card_id:
                raise InvalidActionError("switch_epitomized_target 缺少 'card_id'")
            epi_cards = getattr(pool, 'epitomizable_cards', [])
            if epi_cards and card_id not in epi_cards:
                raise InvalidActionError(f"卡牌 '{card_id}' 不在 epitomizable_cards 中")
            pity_def = pity_engine.get_pity_def(targeted_name)
            if pity_def and not getattr(pity_def, 'switch_allowed', True):
                raise InvalidActionError(f"保底 '{targeted_name}' 不允许切换目标")
            if pity_def and getattr(pity_def, 'switch_resets_progress', True):
                pity_state.set(targeted_name, "fate_points", 0)
            pity_state.set(targeted_name, "selected_card", card_id)
        elif action.action_id == 'cancel_epitomized_path':
            pity_state.set(targeted_name, "selected_card", None)
            pity_state.set(targeted_name, "lost_rotating", False)
            pity_state.set(targeted_name, "losses", 0)

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
        banners = self._banners
        notifier = self._notifier
        real_time = state.real_time
        resources = state.resources
        _check = self.stop_condition.check
        _strategy = self.strategy
        _target_cards = self.target_cards
        _stop = self.stop_condition
        _schedule_mgr = self.schedule_manager
        _lookahead = self.strategy.lookahead
        _resource_gain = self.resource_gain
        _pity_engine = self.pity_engine
        _isinstance = isinstance
        _DrawAction = DrawAction
        _WaitAction = WaitAction
        _is_compact = isinstance(collector, CompactCollector)

        # P61（§3.5 要点 6 / ISSUE-003）：banner 结束快照——banner 级 available_until（秒）
        banner_end_times_sorted = sorted(
            [(b.id, b.available_until) for b in banners.values() if b.available_until],
            key=lambda x: x[1]
        ) if _is_compact else []
        recorded_banner_ends = set() if _is_compact else None
        _pending_wait_gains = {} if _is_compact else None
        total_consumed = {} if _is_compact else None
        total_gained = {} if _is_compact else None

        for iteration in range(max_iterations):
            if _check(state, [], stats):
                break

            # P61（§3.5）：可用性过滤——Banner 级 is_available(real_time)，
            # 时间窗口未开/已关/已 exhausted 的 Banner 在此被排除（旧 current_pools 逐池过滤语义）
            active_banners = [b for b in banners.values() if b.is_available(state.real_time)]

            ctx = build_strategy_context(
                state=state,
                banners=active_banners,
                all_banners=list(banners.values()),
                current_pools=[b.active_pool for b in active_banners],
                all_pools=[b.active_pool for b in banners.values()],
                real_time=real_time,
                target_cards=_target_cards,
                stop_condition=_stop,
                pity_engine=_pity_engine,
                pity_state=pity_state,
                pool_draw_counts=dict(stats.pool_draw_counts),
                total_draws=stats.total_draws,
                last_draw_pity_triggered=stats.last_draw_pity_triggered,
                ssr_ids=self.ssr_ids,
                schedule_mgr=_schedule_mgr,
                lookahead=_lookahead,
                resource_gain=_resource_gain,
            )

            action = _strategy.select_action(ctx)

            if _isinstance(action, _DrawAction):
                # P61（§3.5 要点 5 / ISSUE-006）：banner_id 优先；None 时按 pool_id 反查唯一 Banner
                banner = banners.get(action.banner_id)
                if banner is None and action.banner_id is None and action.pool_id:
                    banner = (self._pool_id_to_banner.get(action.pool_id)
                              or ('.' in action.pool_id
                                  and banners.get(action.pool_id.split('.', 1)[0])))
                if banner is None:
                    raise ValueError(f"Pool not found: {action.banner_id or action.pool_id}")

                pool = banner.active_pool
                batch_size = max(getattr(pool, 'batch_size', 1), 1)

                # ── 原子预检查：batch_size 发可负担性（优化项——mid-batch 成本剧变
                # 由 per-draw 扣费检查兜底，ISSUE-002）──
                if not state.can_afford_batch(pool.cost, batch_size):
                    continue

                # ── 批次逐发执行（batch 循环保留在 gacha_service，ISSUE-003）──
                for _ in range(batch_size):
                    pool = banner.active_pool          # 每次重读活跃池（上一抽可能已 switch_to）
                    # ── 批次中途耗尽守卫（ISSUE-302）──
                    if banner.is_exhausted:
                        break
                    spent = state.spend(pool.cost)
                    if spent is None:
                        break

                    # Banner.draw：路由到活跃池 + P55 聚合/调整/还原 + 保底旁路 + after_draw，
                    # 【不】评估 _check_transitions（单一触发点，ISSUE-001）
                    out = banner.draw(state, _pity_engine, pity_state, pool)
                    reward = out.reward
                    draw_pool_key = f"{banner.id}.{out.pool_id}"   # 全限定统计键（ISSUE-021）
                    pity_triggered = out.pity_triggered
                    triggered_pity_name = out.triggered_pity_name

                    # ── 逐抽结算（stats/collector 键统一为全限定，ISSUE-002）──
                    stats.on_draw(reward.id, draw_pool_key, pity_triggered)
                    if pity_triggered:
                        stats.pity_triggers += 1

                    rg = dict(reward.resources_gained or {})
                    # P63：卡片获得 + 溢出统一走 state.add_card() 管道
                    if reward.id != _NO_CARD_ID:
                        overflow = state.add_card(
                            reward.id, path="draw",
                            overflow_bands=self.card_overflow_map.get(reward.id),
                            initial_counts=_initial_counts,
                        )
                        for k, v in overflow.items():
                            rg[k] = rg.get(k, 0) + v
                    if rg:
                        for k, v in rg.items():
                            resources[k] = resources.get(k, 0) + v

                    # 池级保底计数器最大值（供 collector 记录）
                    pool_counter_max = 0
                    if _pity_engine:
                        pool_spec = _pity_engine.get_spec(draw_pool_key)
                        if pool_spec:
                            for pname in pool_spec.pity_names:
                                cv = _pity_engine.get_counter(pname) if _pity_engine else pity_state.get(pname, 'counter', 0)
                                pool_counter_max = max(pool_counter_max, cv)

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
                        pool_key=draw_pool_key,
                    )

                    # ── 单抽粒度 emit——batch 内每抽一次（ISSUE-004）──
                    # 事件契约（§3.5 唯一真相）：banner_id / pool_id=全限定键 / card_id /
                    # pity_triggered / draw_index=stats.total_draws / state / collector
                    notifier.emit("after_draw",
                                  banner_id=banner.id,
                                  pool_id=draw_pool_key,
                                  card_id=reward.id,
                                  pity_triggered=pity_triggered,
                                  draw_index=stats.total_draws,
                                  state=state,
                                  collector=collector)

            elif _isinstance(action, NonDrawAction):
                self._apply_non_draw(action, banners, _pity_engine, pity_state)

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

                # ── 等待期纯时间条件评估（ISSUE-003）：仅 time_window 可能在此满足 ──
                for b in active_banners:
                    b._check_transitions(real_time=state.real_time)

                if _is_compact:
                    for bid, bet in banner_end_times_sorted:
                        if bid not in recorded_banner_ends and real_time >= bet:
                            banner_obj = banners.get(bid)
                            if banner_obj is not None:
                                banner_obj._exhaust()      # 时间窗口过期即永久关闭（ISSUE-001）
                            collector.on_banner_end(bid, dict(resources), pity_state.to_dict())
                            recorded_banner_ends.add(bid)

                stats.on_wait(action.duration)

                collector.on_wait(
                    duration=action.duration, resources_gained=rg,
                    real_time_before=rt_before, real_time_after=real_time,
                )

            else:
                raise ValueError(f"Unknown action type: {action}")

            if _is_compact:
                for bid, bet in banner_end_times_sorted:
                    if bid not in recorded_banner_ends and real_time >= bet:
                        banner_obj = banners.get(bid)
                        if banner_obj is not None:
                            banner_obj._exhaust()
                        collector.on_banner_end(bid, dict(resources), pity_state.to_dict())
                        recorded_banner_ends.add(bid)

        state.real_time = real_time
        state.resources = resources

        if _is_compact:
            for bid, bet in banner_end_times_sorted:
                if bid not in recorded_banner_ends and real_time >= bet:
                    banner_obj = banners.get(bid)
                    if banner_obj is not None:
                        banner_obj._exhaust()
                    collector.on_banner_end(bid, dict(resources), pity_state.to_dict())
                    recorded_banner_ends.add(bid)

            result = collector.get_result()
            result.total_consumed = total_consumed
            result.total_gained = total_gained
            result.total_draws = stats.total_draws
            result.total_waits = stats.total_waits
            result.pity_triggers = stats.pity_triggers
            result.final_resources = dict(resources)
            result.final_time = real_time
            # P61（§3.13.1 / ISSUE-002）：pool_types 由推导属性填充，键为全限定 {banner_id}.{pool_id}
            result.pool_types = {
                f"{b.id}.{pk}": _derive_pool_type(p)
                for b in banners.values()
                for pk, p in b.pools.items()
            }
            result.strategy_name = type(self.strategy).__name__
            result.strategy_key = getattr(
                type(self.strategy), '_strategy_key',
                type(self.strategy).__name__
            )  # P69 ISSUE-007：策略注册 key，复合策略类回退为类名
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
