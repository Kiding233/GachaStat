import datetime as _dt
from typing import Dict
from .config_store import (
    ConfigStore, PityConfig, PityDef, GainRule, DayOverride,
    TargetCardEntry, CardDefEntry, BannerEntry, BannerPoolEntry,
    LifecycleRuleEntry, MilestoneConfig, MilestoneDef,   # P58（ISSUE-005/306）：里程碑透传
)

# P61：秒/天换算——截断后时间窗口以秒写入 store.banner（与 config_store/config_toml 同口径）
DAY = 86400


class RetreatConfigBuilder:
    @staticmethod
    def build(
        original_store: ConfigStore,
        from_pool_id: str,
        initial_resources: Dict[str, float],
        pity_counter_init: Dict[str, int],
    ) -> ConfigStore:
        # P72 ISSUE-129：falsy 守卫——from_pool_id=None/''（起始池「(从头开始)」或调用方未传）
        # 时统一走 ValueError，避免下方 `'.' not in from_pool_id` 对 None 裸抛 TypeError；
        # 错误消息与 L39 既有「Pool ... not found in config」统一
        if not from_pool_id:
            raise ValueError(f"Pool '{from_pool_id}' not found in config")
        from_pool = None
        for p in original_store.pools:
            if p.pool_id == from_pool_id:
                from_pool = p
                break
        if from_pool is None and '.' not in from_pool_id:
            # P61（ISSUE-101）兜底：展平视图 pool_id 为全限定键 {banner_id}.main，
            # 兼容调用方传裸 banner id 的场景
            for p in original_store.pools:
                if p.pool_id.split('.')[0] == from_pool_id:
                    from_pool = p
                    break

        if from_pool is None:
            raise ValueError(f"Pool '{from_pool_id}' not found in config")

        # P61（ISSUE-333）：end_day=None（永久 Banner）时不能做 `end_day > 0` 比较——
        # None 比较抛 TypeError，按永久池语义回退 start_day + 21
        offset_day = (from_pool.end_day
                      if from_pool.end_day is not None and from_pool.end_day > 0
                      else (from_pool.start_day + 21))

        truncated = ConfigStore()

        # Phase 2: 复制原始 sim_start_date 并偏移 offset_day 天
        original_start_str = getattr(original_store, 'sim_start_date', None)
        if not original_start_str:
            original_start = _dt.date.today()
        else:
            try:
                original_start = _dt.date.fromisoformat(original_start_str)
            except (ValueError, TypeError):
                original_start = _dt.date.today()
        truncated_start = original_start + _dt.timedelta(days=offset_day)
        truncated.sim_start_date = truncated_start.isoformat()

        # P61（2026-08-04 修复 D3/D4）：遍历 store.banner.banners 保持多池结构——
        # 不遍历展平视图（否则多池 banner 拆出重复 id，GachaService 构造桥 dict 收纳
        # 后者覆盖前者、丢池）；同时复制原 banner 的 lifecycle 规则（D4）。
        truncated.banner.banners = []
        for b in original_store.banner.banners:
            b_from_day = b.available_from // DAY if b.available_from is not None else 0
            if b_from_day < offset_day:
                continue  # 该 banner 在退避点之前，截断
            pools = [
                BannerPoolEntry(
                    id=p.id,
                    cost=p.cost,
                    batch_size=p.batch_size,
                    excludes_all_pity=p.excludes_all_pity,
                    max_draws=p.max_draws,
                    exchange_card_id=p.exchange_card_id,
                    epitomizable_cards=list(p.epitomizable_cards),
                    rewards=[
                        {
                            'card_id': d.get('card_id', ''),
                            'probability': d.get('probability', 0),
                            'rarity': d.get('rarity', 'R'),
                            'featured': d.get('featured', False),
                            **({'resources_gained': dict(d.get('resources_gained', {}))}
                               if d.get('resources_gained') else {}),
                        }
                        for d in p.rewards
                    ],
                )
                for p in b.pools
            ]
            # D4：复制 lifecycle 规则（截断配置的 switch_to/exhaust 转换不丢失）。
            # D3（2026-08-04）：time_window 条件 at 为绝对秒时刻，随窗口整体 -offset_day
            # 偏移（保持相对 banner 开池时机不变）；pool_draws 等抽数条件 at 是计数、原样复制。
            lifecycle = [
                LifecycleRuleEntry(
                    condition=lc.condition, pool=lc.pool,
                    at=(lc.at - offset_day * DAY) if lc.condition == 'time_window' else lc.at,
                    match=lc.match, action=lc.action, target=lc.target,
                )
                for lc in (b.lifecycle or [])
            ]
            truncated.banner.banners.append(BannerEntry(
                id=b.id,
                name=b.name,
                enabled=b.enabled,
                max_draws=b.max_draws,  # 复审查发现：banner 级抽数上限（新手池自动 exhaust）不丢失
                available_from=(b_from_day - offset_day) * DAY,
                available_until=((b.available_until // DAY - offset_day) * DAY
                                 if b.available_until is not None else None),
                pools=pools,
                lifecycle=lifecycle,
            ))

        # P55：PityDef 扁平化——shallow-copy 23 字段（dataclass 字段不可变）
        pities = []
        for pd in original_store.pity.pities:
            # 应用 per-behavior counter_init 覆盖
            custom_init = pity_counter_init.get(pd.name)
            ci = custom_init if custom_init is not None else pd.counter_init
            pities.append(PityDef(
                name=pd.name, btype=pd.btype, scope=pd.scope,
                target_featured=pd.target_featured,
                deltas=pd.deltas, threshold=pd.threshold,
                counter_init=ci,
                guaranteed_init=pd.guaranteed_init,
                fate_points_init=pd.fate_points_init,
                selected_card_init=pd.selected_card_init,  # ISSUE-132：漏拷——阶段 3 后完整分支携带、截断分支丢失致不对称
                soft_start=pd.soft_start, soft_end=pd.soft_end,
                soft_increment=pd.soft_increment, soft_deltas=pd.soft_deltas,
                cr_counter_threshold=pd.cr_counter_threshold,
                cr_base_rate=pd.cr_base_rate, cr_state_probs=pd.cr_state_probs,
                fate_threshold=pd.fate_threshold,
                switch_allowed=pd.switch_allowed,
                switch_resets_progress=pd.switch_resets_progress,
                pools=pd.pools,
                deactivate_on_early_hit=pd.deactivate_on_early_hit,
                depends_on=pd.depends_on,
                reset=pd.reset,
            ))
        truncated.pity = PityConfig(
            enabled=original_store.pity.enabled,
            pities=pities,
        )

        truncated.initial_resources = dict(initial_resources)

        truncated.gain_rules = [
            GainRule(
                rule_type=gr.rule_type,
                param=gr.param,
                gains=dict(gr.gains),
            )
            for gr in original_store.gain_rules
        ]

        truncated.day_overrides = []
        for dor in original_store.day_overrides:
            new_day = dor.day - offset_day
            if new_day >= 0:
                truncated.day_overrides.append(DayOverride(
                    day=new_day,
                    gains=dict(dor.gains),
                ))

        truncated.target_cards = [
            TargetCardEntry(
                card_id=tc.card_id,
                quantity=tc.quantity,
                pool_ids=list(tc.pool_ids),
            )
            for tc in original_store.target_cards
        ]

        truncated.card_defs = [
            CardDefEntry(
                card_id=cd.card_id,
                name=cd.name,
                rarity=cd.rarity,
                pools=list(cd.pools),
                initial_count=cd.initial_count,
                tags=dict(cd.tags),
                list_tags={k: list(v) for k, v in cd.list_tags.items()},
                overflow_bands=list(cd.overflow_bands) if cd.overflow_bands is not None else None,  # P58（ISSUE-306）：截断模式赠卡溢出不丢失
            )
            for cd in original_store.card_defs
        ]

        truncated.resource_defs = dict(original_store.resource_defs)
        truncated.strategy_key = original_store.strategy_key
        truncated.auto_wait = original_store.auto_wait

        # P58（REVIEW-R1-FIX: ISSUE-005 + ISSUE-306）：截断模式透传 milestone + 溢出数据——
        # 否则截断分支（from_pool_id 指定）truncated_store 恒空 milestone，与完整时间线分支
        # （含 milestone）GDR/最少资源/Pareto 搜索结果不一致；空 card_overflow_map 下赠卡溢出
        # 资源不触发，「截断与完整模式一致」验收项不成立。
        truncated.milestone = MilestoneConfig(
            enabled=original_store.milestone.enabled,
            milestones=[
                MilestoneDef(
                    name=m.name, threshold=m.threshold, repeat=m.repeat,
                    max_triggers=m.max_triggers, bonus_reward=dict(m.bonus_reward),
                    banner=m.banner,
                )
                for m in original_store.milestone.milestones
            ],
        )
        truncated.card_overflow_map = dict(original_store.card_overflow_map)
        truncated.rarity_defaults = dict(original_store.rarity_defaults)

        return truncated
