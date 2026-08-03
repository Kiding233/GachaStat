"""策略上下文构造器——集中构建 StrategyContext，计算派生字段。

P69 阶段 2b：将 GachaService._run_compact() 中分散的 StrategyContext 构造
收敛到单一函数，并自动计算 future_resource_gains / inter_pool_pity_links
等派生字段。实现为模块级函数——StrategyContext 只有一处构造点，不需要
Builder 类的链式灵活性。
"""

from __future__ import annotations

from typing import Dict, List, Optional, TYPE_CHECKING

from .strategy import StrategyContext

if TYPE_CHECKING:
    from .state import GachaState
    from .pool import Pool
    from .schedule import PoolScheduleManager
    from .pity import PityEngine, PityState
    from .resource_gain import ResourceGainFunction
    from .stop_condition import StopCondition
    from .target_card import TargetCardSet

# 秒/天换算常量（与 resource_gain.py ScheduleResourceGain.DAY 一致）
DAY = 86400


def build_strategy_context(
    state: GachaState,
    current_pools: List[Pool],
    all_pools: List[Pool],
    real_time: float,
    target_cards: TargetCardSet,
    stop_condition: StopCondition,
    pity_engine: Optional[PityEngine],
    pity_state: Optional[PityState],
    pool_draw_counts: Dict[str, int],
    total_draws: int,
    last_draw_pity_triggered: bool,
    ssr_ids: set,
    *,
    schedule_mgr: Optional[PoolScheduleManager] = None,
    lookahead: Optional[float] = None,
    resource_gain: Optional['ResourceGainFunction'] = None,
    time_discount: float = 1.0,
) -> StrategyContext:
    """构建完整的 StrategyContext，含派生字段。

    Args:
        state: 当前模拟状态。
        current_pools: 当前时间点可用的池子列表。
        all_pools: 全部池子列表。
        real_time: 当前模拟日历时间。
        target_cards: 目标卡集合。
        stop_condition: 停止条件。
        pity_engine: 保底引擎。
        pity_state: 保底状态。
        pool_draw_counts: 各池已抽次数。
        total_draws: 总抽数。
        last_draw_pity_triggered: 上抽是否触发了保底。
        ssr_ids: SSR 卡牌 ID 集合。
        schedule_mgr: 可选——排期管理器，用于计算 future_schedules。
        lookahead: 策略的 lookahead 天数——future_schedules / future_resource_gains 的时间窗口（天）。
        resource_gain: 可选——资源获得函数，用于计算 future_resource_gains（复用模拟结算同一 compute）。
        time_discount: 时间偏好因子（默认 1.0 = 无折扣）。

    Returns:
        完全填充的 StrategyContext。
    """
    # ── future_schedules：未来 lookahead 天内的池子开放窗口 ──
    future_schedules = []
    if schedule_mgr and lookahead:
        future_schedules = schedule_mgr.get_future_schedules(real_time, lookahead * DAY)

    # ── future_resource_gains：未来 lookahead 天的资源收入 ──
    # 复用抽卡/等待结算的同一函数 resource_gain.compute(elapsed_time, state)：
    # 对 schedule 型查未来日程、linear/periodic/step 型算未来增量（Ps01 R1，替代原 entry.day/gains 错误访问）
    future_resource_gains: Dict[str, float] = {}
    if resource_gain is not None and lookahead:
        future_resource_gains = resource_gain.compute(lookahead * DAY, state)

    # ── inter_pool_pity_links：从 PityEngine 提取跨池保底继承关系 ──
    inter_pool_pity_links: Dict[str, List[str]] = {}
    if pity_engine is not None:
        try:
            behaviors = getattr(pity_engine, '_behavior_list', [])
            for bh in behaviors:
                pools_attr = getattr(bh, 'pools', None) or getattr(bh, '_pools', None)
                if pools_attr and len(pools_attr) > 1:
                    # 该保底行为覆盖多个池子 → 这些池子共享保底计数器
                    for pid in pools_attr:
                        linked = [p for p in pools_attr if p != pid]
                        if pid not in inter_pool_pity_links:
                            inter_pool_pity_links[pid] = linked
                        else:
                            for lp in linked:
                                if lp not in inter_pool_pity_links[pid]:
                                    inter_pool_pity_links[pid].append(lp)
        except Exception:
            pass  # 提取失败不影响模拟——保守回退为空

    return StrategyContext(
        state=state,
        current_pools=current_pools,
        all_pools=all_pools,
        future_schedules=future_schedules,
        target_cards=target_cards,
        stop_condition=stop_condition,
        _pity_engine=pity_engine,
        _pity_state=pity_state,
        pool_draw_counts=pool_draw_counts,
        total_draws=total_draws,
        future_resource_gains=future_resource_gains,
        inter_pool_pity_links=inter_pool_pity_links,
        time_discount=time_discount,
        last_draw_pity_triggered=last_draw_pity_triggered,
        ssr_ids=ssr_ids,
    )
