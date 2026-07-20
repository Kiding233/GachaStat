import datetime as _dt
from typing import Dict
from .config_store import ConfigStore, PoolEntry, PityConfig, PityDef, GainRule, DayOverride, TargetCardEntry, CardDefEntry, PoolDistEntry


class RetreatConfigBuilder:
    @staticmethod
    def build(
        original_store: ConfigStore,
        from_pool_id: str,
        initial_resources: Dict[str, float],
        pity_counter_init: Dict[str, int],
    ) -> ConfigStore:
        from_pool = None
        for p in original_store.pools:
            if p.pool_id == from_pool_id:
                from_pool = p
                break

        if from_pool is None:
            raise ValueError(f"Pool '{from_pool_id}' not found in config")

        offset_day = from_pool.end_day if from_pool.end_day > 0 else (from_pool.start_day + 21)

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

        truncated.pools = []
        for p in original_store.pools:
            if p.start_day >= offset_day:
                truncated.pools.append(PoolEntry(
                    enabled=p.enabled,
                    pool_id=p.pool_id,
                    name=p.name,
                    start_day=p.start_day - offset_day,
                    end_day=p.end_day - offset_day,
                    cost=p.cost,
                    distribution_template=p.distribution_template,
                    pool_type=p.pool_type,
                    batch_size=p.batch_size,
                    bindings=dict(p.bindings),
                    target_specs=list(p.target_specs),
                    rerun_of=p.rerun_of,
                    exchange_card_id=p.exchange_card_id,
                    distribution=[PoolDistEntry(
                        card_id=d.card_id,
                        probability=d.probability,
                        rarity=d.rarity,
                        featured=d.featured,
                        resources_gained=dict(d.resources_gained),
                    ) for d in p.distribution],
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
                soft_start=pd.soft_start, soft_end=pd.soft_end,
                soft_increment=pd.soft_increment, soft_deltas=pd.soft_deltas,
                cr_counter_threshold=pd.cr_counter_threshold,
                cr_base_rate=pd.cr_base_rate, cr_state_probs=pd.cr_state_probs,
                fate_threshold=pd.fate_threshold,
                switch_allowed=pd.switch_allowed,
                switch_resets_progress=pd.switch_resets_progress,
                pools=pd.pools,
                max_triggers=pd.max_triggers,
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
            )
            for cd in original_store.card_defs
        ]

        truncated.resource_defs = dict(original_store.resource_defs)
        truncated.strategy_type = original_store.strategy_type
        truncated.strategy_name = original_store.strategy_name
        truncated.auto_wait = original_store.auto_wait

        return truncated
