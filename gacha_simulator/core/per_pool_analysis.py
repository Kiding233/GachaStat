from typing import List, Dict, Set
from dataclasses import dataclass, field


@dataclass
class PoolSnapshot:
    pool_id: str
    draw_count: int
    target_card_draws: int
    pity_draws: int
    resources_consumed: Dict[str, float]
    cards_obtained: Dict[str, int] = field(default_factory=dict)


def per_pool_summary_stats(
    batch_snaps: Dict[str, List[PoolSnapshot]],
) -> Dict[str, Dict[str, float]]:
    result = {}
    for pid, snaps in batch_snaps.items():
        if not snaps:
            continue
        draws = [s.draw_count for s in snaps]
        targets = [s.target_card_draws for s in snaps]
        pity = [s.pity_draws for s in snaps]
        n = len(snaps)
        result[pid] = {
            'mean_draws': sum(draws) / n,
            'mean_target_cards': sum(targets) / n,
            'mean_pity_draws': sum(pity) / n,
            'pity_count': sum(pity) / n,
            'target_count': sum(targets) / n,
        }
    return result


@dataclass
class TransitionMatrix:
    from_pool_id: str
    to_pool_id: str
    success_to_success: float
    success_to_fail: float
    fail_to_success: float
    fail_to_fail: float
    success_rate_before: float
    success_rate_after: float


def compute_transition_matrices_from_flags(
    success_flags_per_sim: List[List[bool]],
    pool_ids_ordered: List[str],
) -> List[TransitionMatrix]:
    """从布尔矩阵计算转移矩阵（纯函数）。

    Args:
        success_flags_per_sim: [模拟索引][池索引] → 该池结束时是否成功
        pool_ids_ordered: 按结束时间排序的池ID列表
    """
    n_sims = len(success_flags_per_sim)
    if n_sims == 0:
        return []

    n_pools = len(pool_ids_ordered)
    results = []
    for i in range(n_pools):
        to_pid = pool_ids_ordered[i]
        from_pid = pool_ids_ordered[i - 1] if i > 0 else '(初始)'

        if i == 0:
            before = [False] * n_sims
        else:
            before = [
                success_flags_per_sim[s][i - 1]
                if s < len(success_flags_per_sim) and i - 1 < len(success_flags_per_sim[s])
                else False
                for s in range(n_sims)
            ]
        after = [
            success_flags_per_sim[s][i]
            if s < len(success_flags_per_sim) and i < len(success_flags_per_sim[s])
            else False
            for s in range(n_sims)
        ]

        ss = sum(1 for b, a in zip(before, after) if b and a)
        sf = sum(1 for b, a in zip(before, after) if b and not a)
        fs = sum(1 for b, a in zip(before, after) if not b and a)
        ff = sum(1 for b, a in zip(before, after) if not b and not a)

        s_before = sum(1 for b in before if b)
        s_after = sum(1 for a in after if a)

        results.append(TransitionMatrix(
            from_pool_id=from_pid,
            to_pool_id=to_pid,
            success_to_success=ss / s_before if s_before > 0 else 0,
            success_to_fail=sf / s_before if s_before > 0 else 0,
            fail_to_success=fs / (n_sims - s_before) if (n_sims - s_before) > 0 else 0,
            fail_to_fail=ff / (n_sims - s_before) if (n_sims - s_before) > 0 else 0,
            success_rate_before=s_before / n_sims,
            success_rate_after=s_after / n_sims,
        ))
    return results


def compute_transition_flags_from_gdr(
    cumulative_snapshots: Dict[str, List[Dict]],
    pool_ids_ordered: List[str],
    target_specs: Dict[str, int],
    gdr_key: str = 'all_targets',
    threshold: float = 1.0,
    scope: str = 'cumulative',
    aggregates: List[Dict] = None,
    ssr_ids: Set[str] = None,
    bonus_events: List[List[Dict]] = None,   # P58（ISSUE-312）：per-sim 赠卡清单，None=无赠卡数据保守回退不减
    **gdr_kwargs,
) -> List[List[bool]]:
    """通过 GDR 框架逐池判定成功/失败，替代硬编码的 _compute_transition_flags()。

    P58（REVIEW-R1-FIX: ISSUE-312）——转变分析 draw-only 口径回退路径：
    方案 B/A 后 cumulative_snapshots/aggregates 含 milestone 赠卡（target 为赠卡时
    判池成功），与 infer_events 的 draw-only 池成败矛盾。判定前按 bonus_events
    （per-sim 赠卡清单，data 通道由 extract_aggregate 透传）减去该 sim 该 pool 的
    赠卡 card_ids，恢复 draw-only 口径。None = 无赠卡数据 → 保守回退不减（当前行为）。
    """
    from .process_trace import compute_pool_gdr_cumulative, compute_pool_gdr_single_pool

    if scope == 'cumulative':
        n_sims = len(next(iter(cumulative_snapshots.values()), [])) if cumulative_snapshots else 0
    else:
        n_sims = len(aggregates) if aggregates else 0

    if n_sims == 0:
        return []

    from .gdr import resolve_gdr_definition
    gdr_defn = resolve_gdr_definition(gdr_key)
    lower_is_better = gdr_defn.lower_is_better if gdr_defn else False

    def _draw_only_card_counts(counts: Dict[str, int], sim_idx: int, pool_id: str) -> Dict[str, int]:
        """P58（ISSUE-312）：从含赠卡的计数恢复 draw-only 口径。

        bonus_events[sim_idx] 为该 sim 的全部赠卡事件；pool_id 为 pool_ids_ordered
        键（banner_id 或全限定，与 cumulative_snapshots 同键空间）；bonus_events[].pool_id
        为全限定 {banner_id}.{pool_id}（emit 契约）——按 banner_id 段匹配（与
        streaming._check_success_draw_only 同口径）。
        """
        if not bonus_events or sim_idx >= len(bonus_events):
            return dict(counts)
        draw_only = dict(counts)
        pid = pool_id or ''
        pid_banner = pid.split('.')[0] if pid else ''
        for ev in bonus_events[sim_idx]:
            ev_pool = ev.get('pool_id', '') or ''
            ev_banner = ev_pool.split('.')[0] if ev_pool else ''
            # 匹配：pool_id 全限定 → banner 段相等；pool_id 裸 banner → 相等；空 → 全部
            if ev_banner and pid_banner and ev_banner != pid_banner:
                continue
            if not ev_banner and pid_banner:
                continue
            for cid in ev.get('card_ids', []):
                if cid in draw_only:
                    draw_only[cid] = max(0, draw_only[cid] - 1)
        return draw_only

    flags_per_sim = [[] for _ in range(n_sims)]
    for pool_id in pool_ids_ordered:
        for sim_idx in range(n_sims):
            if scope == 'cumulative':
                snaps = cumulative_snapshots.get(pool_id, [])
                snap = snaps[sim_idx] if sim_idx < len(snaps) else {}
                if snap:
                    snap = dict(snap)
                    snap['cumulative_card_counts'] = _draw_only_card_counts(
                        snap.get('cumulative_card_counts', {}), sim_idx, pool_id)
                    val = compute_pool_gdr_cumulative(
                        snap, pool_id, target_specs, gdr_key,
                        ssr_ids=ssr_ids, **gdr_kwargs,
                    )
                else:
                    # P72 ISSUE-703 路线(a) 落点1（D4 已裁决）：空快照（数据缺失）→ None，
                    # 消费侧计失败并注明「数据缺失，非真失败」，避免空快照经
                    # compute_gdr_from_cumulative({}) 算出 0.0 对 lower_is_better 类指标误判成功。
                    # compute_pool_gdr_cumulative 对非空快照契约不变（落点 1 不触碰导出函数）。
                    val = None
            else:
                agg = aggregates[sim_idx] if aggregates and sim_idx < len(aggregates) else {}
                if agg:
                    agg = dict(agg)
                    agg['card_counts'] = _draw_only_card_counts(
                        agg.get('card_counts', {}), sim_idx, pool_id)
                val = compute_pool_gdr_single_pool(
                    agg, pool_id, target_specs, gdr_key,
                    ssr_ids=ssr_ids, **gdr_kwargs,
                )
            if val is None:
                flags_per_sim[sim_idx].append(False)
            elif lower_is_better:
                flags_per_sim[sim_idx].append(val <= threshold)
            else:
                flags_per_sim[sim_idx].append(val >= threshold)
    return flags_per_sim
