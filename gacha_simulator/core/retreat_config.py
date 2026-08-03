import datetime as _dt
from typing import Dict
from .config_store import (
    ConfigStore, PityConfig, PityDef, GainRule, DayOverride,
    TargetCardEntry, CardDefEntry, BannerEntry, BannerPoolEntry,
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

        # P61（Ph3/ISSUE-101）：store.pools 为只读展平视图（无 setter），
        # 写侧迁移到 truncated.banner.banners——每个展平池重建为一个 BannerEntry
        # （pool 进 [[banner.pool]]，id="main"，banner_id 取全限定键 {banner_id}.main 的段）。
        truncated.banner.banners = []
        for p in original_store.pools:
            if p.start_day >= offset_day:
                banner_id = p.pool_id.split('.')[0] if '.' in p.pool_id else p.pool_id
                bp = BannerPoolEntry(
                    id='main',
                    cost=p.cost,
                    batch_size=p.batch_size,
                    exchange_card_id=p.exchange_card_id,
                    epitomizable_cards=list(p.epitomizable_cards),
                    rewards=[
                        {
                            'card_id': d.card_id,
                            'probability': d.probability,
                            'rarity': d.rarity,
                            'featured': d.featured,
                            **({'resources_gained': dict(d.resources_gained)}
                               if d.resources_gained else {}),
                        }
                        for d in p.distribution
                    ],
                )
                truncated.banner.banners.append(BannerEntry(
                    id=banner_id,
                    name=p.name,
                    enabled=p.enabled,
                    available_from=(p.start_day - offset_day) * DAY,
                    available_until=((p.end_day - offset_day) * DAY
                                     if p.end_day is not None else None),
                    pools=[bp],
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
        truncated.strategy_key = original_store.strategy_key
        truncated.auto_wait = original_store.auto_wait

        return truncated
