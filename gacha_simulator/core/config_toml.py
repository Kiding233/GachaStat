"""TOML 配置文件读写——替代旧 config_io.py + pool_config.py 的 txt 解析器。

P61（Ph4）：池子配置段已从旧 [[pools]]（含 distribution_template/bindings 模板引用）
一次性迁移为 [[banner]]（D3/D4 裁决，无兼容双路径）。分布模板系统已移除
（§3.10.6）——模板在迁移时展开为内联 [[banner.pool.reward]]。
"""

import warnings
from typing import Dict, List, Optional

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from .config_store import (
    BannerEntry,
    BannerPoolEntry,
    CardDefEntry,
    CardWeightEntry,
    ConfigError,
    ConfigStore,
    DayOverride,
    GainRule,
    LifecycleRuleEntry,
    MilestoneConfig,
    MilestoneDef,
    PityConfig,
    PityDef,
    SelectVoucherDef,   # ← P78
    TargetCardEntry,
)
from .overflow import OverflowBand, expand_sugar_to_bands

# P61：秒/天换算——Banner 时间窗口（秒）与 TOML start_day/end_day（天）在解析/保存边界换算
DAY = 86400

# ══════════════════════════════════════════════════════════════════
# 公开接口
# ══════════════════════════════════════════════════════════════════


def load_toml(path: str, store: Optional[ConfigStore] = None) -> ConfigStore:
    """从 TOML 文件加载配置。

    Args:
        path: config.toml 文件路径。
        store: 可选——已有 ConfigStore 实例（调用 clear() 后重新填充）。
               传入 None 则创建新实例。

    Returns:
        填充后的 ConfigStore。
    """
    if store is None:
        store = ConfigStore()
    else:
        store.clear()

    with open(path, 'rb') as f:
        data = tomllib.load(f)

    # P60：稀有度层级解析（必须在 _build_pity 之前——§0.1 AUDIT-BREAK-1）
    store._parse_rarities(data)

    # 各段构建
    _build_resources(data, store)
    _build_cards(data, store)
    _build_select_voucher(data, store)   # P78：[[select_voucher]] 自选券候选集段（ISSUE-129——须在 _build_resources L65 之后、_build_cards L66 之后：voucher id setdefault 补全需 resource_defs 就绪、候选卡校验需 card_defs 就绪）
    _build_gain_rules(data, store)
    _build_day_overrides(data, store)
    _build_pity(data, store)        # 依赖 rarity_rank 完成 scope 校验
    _build_milestone(data, store)   # P58：[[milestone]] 累抽奖励段（依赖 card_defs 做引用校验）
    _build_targets(data, store)
    _build_weights(data, store)

    # P69：策略段
    _build_strategy(data, store)

    # Banner 段（[[banner]] + [[banner.pool]] + [[banner.lifecycle]]）
    _build_banners(data, store)

    # P61（ISSUE-004）：旧 [[pools]] 段残留检测——解析器只认 [[banner]]，
    # 残留段不解析。banner 为空且检测到残留时显式警告，避免静默 end_time=0/模拟 0 抽。
    if data.get('pools') and not store.banner.banners:
        warnings.warn(
            "检测到旧 [[pools]] 段（已弃用）——当前解析出 0 个 Banner。"
            "请将配置一次性迁移为 [[banner]] 格式（P61），否则模拟将无池可抽。"
        )

    # 回填 card_defs.pools：从池子分布逆向推导每张卡属于哪些池子
    _backfill_card_pools(store)

    # P63：解析稀有度默认溢出规则（键名统一 .lower()）
    _build_rarity_defaults(data, store)

    # P63：构建 card_overflow_map（必须在 _build_cards 和 _build_rarity_defaults 之后）
    _build_card_overflow_map(store)

    # P77：资源生命周期段（须在 _build_banners/_normalize_permanent_banners 之后，依赖永久池标记）
    _build_resource_lifecycle(data, store)

    return store


def save_toml(store: ConfigStore, path: str) -> None:
    """将 ConfigStore 保存为 TOML 文件。

    P61（Ph4）：池子段以 [[banner]] 格式写出（见 _save_banners）。分布模板系统
    已移除（§3.10.6）——rewards 一律内联，不写 [[distribution_templates]]。
    """
    import tomli_w

    data: dict = {}

    # resources
    data['resources'] = {
        'defs': dict(store.resource_defs),
        'initial': dict(store.initial_resources),
    }

    # gain_rules
    if store.gain_rules:
        data['resources']['gain_rules'] = [
            {'type': r.rule_type, 'param': r.param, 'gains': dict(r.gains)}
            for r in store.gain_rules
        ]

    # day_overrides
    if store.day_overrides:
        data['resources']['day_overrides'] = [
            {'day': d.day, 'gains': dict(d.gains)}
            for d in store.day_overrides
        ]

    # cards（P65：段名 [[card]]，字段 card_id）
    data['card'] = []
    for c in store.card_defs:
        entry = {
            'card_id': c.card_id,
            'name': c.name,
            'rarity': c.rarity,
            'initial_count': c.initial_count,
        }
        if c.tags:
            filtered = {k: v for k, v in c.tags.items() if v}
            if filtered:
                entry['tags'] = filtered
        if c.list_tags:
            lt = {k: v for k, v in c.list_tags.items() if v}
            if lt:
                entry['list_tags'] = lt
        # P63：卡片溢出分段表——统一写 bands 数组（与内部表示一致、round-trip 无损）
        if c.overflow_bands:
            entry['overflow_bands'] = [
                {
                    'range': [b.min, 'inf' if b.max is None else b.max],
                    'resources': dict(b.resources),
                }
                for b in c.overflow_bands
            ]
        data['card'].append(entry)

    # P61：Banner 段（[[banner]] + [[banner.pool]] + [[banner.pool.reward]] + [[banner.lifecycle]]）
    _save_banners(store, data)

    # P77：资源生命周期段（两档条件写键）
    _save_resource_lifecycle(store, data)

    # pity（P55 扁平化格式）
    if store.pity.enabled and store.pity.pities:
        data['pity'] = [_pitydef_to_toml(p) for p in store.pity.pities]

    # milestone（P58：[[milestone]] 累抽奖励段——独立于保底体系）
    if store.milestone.enabled and store.milestone.milestones:
        data['milestone'] = []
        for m in store.milestone.milestones:
            entry = {
                'name': m.name,
                'threshold': m.threshold,
                'repeat': m.repeat,
                'max_triggers': m.max_triggers,
                'banner': m.banner,
                'bonus_reward': m.bonus_reward,
            }
            # P78 条件写键纪律（ISSUE-113）——空列表/零偏移省略键：
            # 显式空 alternate_rewards=[]/offset=0 写出会在下次 load_toml 命中
            # ISSUE-112 规则 1/ISSUE-007 抛 ConfigError（GUI 保存→重载断裂）。
            if m.alternate_rewards:
                entry['alternate_rewards'] = m.alternate_rewards
            if m.offset:
                entry['offset'] = m.offset
            data['milestone'].append(entry)

    # select_voucher（P78：[[select_voucher]] 自选券候选集段——独立 gate，ISSUE-118：
    # 与 milestone 的 enabled-and-milestones gate 无关，防 milestone 禁用/为空时段被整体跳过）
    if store.select_vouchers:
        data['select_voucher'] = [
            {'voucher': v.voucher, 'cards': list(v.cards)}
            for v in store.select_vouchers
        ]

    # strategy（P69：key + params 格式）
    if store.strategy_key:
        strategy_entry: dict = {'key': store.strategy_key}
        # 仅写入与默认值不同的参数
        from .strategy import STRATEGY_REGISTRY
        meta = STRATEGY_REGISTRY.get(store.strategy_key)
        if meta and meta.params and store.strategy_params:
            non_default = {}
            for pdesc in meta.params:
                user_val = store.strategy_params.get(pdesc.key)
                if user_val is not None and user_val != pdesc.default:
                    non_default[pdesc.key] = user_val
            if non_default:
                strategy_entry['params'] = non_default
        data['strategy'] = strategy_entry

    # plugins（P69 阶段 4d：持久化禁用状态）
    from .strategy import STRATEGY_REGISTRY as _sr
    disabled_keys = [
        key for key, m in _sr.items()
        if m.disabled and not m.internal
    ]
    if disabled_keys:
        data['plugins'] = {'disabled': disabled_keys}

    # targets
    if store.target_cards:
        data['targets'] = [
            {'card_id': t.card_id, 'quantity': t.quantity,
             'pool_ids': list(t.pool_ids)}
            for t in store.target_cards
        ]

    # weights —— [[weights]] 数组表格式
    if store.card_weights:
        data['weights'] = [
            {'card_id': cid, 'desire': cw.desire_weight,
             'miss_cost': cw.miss_cost_weight, 'card_value': cw.card_value}
            for cid, cw in store.card_weights.items()
        ]

    # rarities —— P60 新增：往返对称（load_toml 已解析 → 写入保证不丢失）
    if store.rarity_rank:
        # rarity_rank 是 name→rank 的反向映射（如 {"SSR": 0, "SR": 1, "R": 2}）
        # 逆转为 ranks 分组格式：[[names_at_rank_0], [names_at_rank_1], ...]
        # dict 分桶替代 range 预分配——消除极端 rank 值的 O(max_rank) 膨胀
        buckets = {}
        for name, rank_idx in store.rarity_rank.items():
            buckets.setdefault(rank_idx, []).append(name)
        ranks = [buckets[r] for r in sorted(buckets)]
        data['rarities'] = {'ranks': ranks}

    # P63：稀有度默认溢出规则——与解析路径双向对称
    if store.rarity_defaults:
        rd_data = {}
        for rarity_key, rd_entry in store.rarity_defaults.items():
            bands = rd_entry.get('overflow_bands', [])
            if bands:
                rd_data[rarity_key] = {
                    'overflow_bands': [
                        {
                            'range': [b.min, 'inf' if b.max is None else b.max],
                            'resources': dict(b.resources),
                        }
                        for b in bands
                    ]
                }
        if rd_data:
            data['rarity_defaults'] = rd_data

    header = (
        '# ============================================================\n'
        '# GachaStat 统一配置文件 —— 由 GachaStat GUI 自动生成\n'
        '# ============================================================\n'
        '# 语法速查：\n'
        '#   key = value          标量（整数/浮点/布尔/字符串）\n'
        '#   [section]            表（字典）—— . 号嵌套子表\n'
        '#   [[array]]            数组表——每个 [[array]] 是数组中的一个元素\n'
        '#   { k = v, k = v }     内联表——写在一行的小字典\n'
        '# ============================================================\n'
        '# 完整格式说明见 GUI 帮助→关于→配置文件指南\n'
        '\n'
    )
    body = tomli_w.dumps(data)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(header)
        f.write(body)


# ══════════════════════════════════════════════════════════════════
# Banner 保存辅助
# ══════════════════════════════════════════════════════════════════


def _save_banners(store: ConfigStore, data: dict) -> None:
    """从 store.banner.banners 写 [[banner]] 段（D3/D4 一次性迁移，无双路径分支）。

    - start_day/end_day（天）由 available_from/until（秒）// DAY 换算（与展平视图同口径）
    - max_draws None 不写；0 保存边界同样归一化为 None（ISSUE-331）
    - rewards 统一内联写 [[banner.pool.reward]]（BannerPoolEntry 无 distribution_template 字段，
      一次性迁移后模板已展开为内联，保存不写 [[distribution_templates]]）
    - lifecycle time_window.at（秒）保存回天（/ DAY，ISSUE-001）
    """
    banners = []
    for b in store.banner.banners:
        b_dict: dict = {'id': b.id, 'name': b.name}
        if not b.enabled:
            b_dict['enabled'] = False
        if b.max_draws is not None:
            b_dict['max_draws'] = b.max_draws
        if b.available_from is not None:
            b_dict['start_day'] = int(b.available_from // DAY)
        if b.available_until is not None:
            b_dict['end_day'] = int(b.available_until // DAY)

        if b.pools:
            pools = []
            for bp in b.pools:
                bp_dict: dict = {'id': bp.id, 'cost': bp.cost}
                if bp.batch_size != 1:
                    bp_dict['batch_size'] = bp.batch_size
                if bp.excludes_all_pity:
                    bp_dict['excludes_all_pity'] = True
                if bp.max_draws is not None:
                    bp_dict['max_draws'] = bp.max_draws
                if bp.exchange_card_id:
                    bp_dict['exchange_card_id'] = bp.exchange_card_id
                if bp.epitomizable_cards:
                    bp_dict['epitomizable_cards'] = list(bp.epitomizable_cards)
                if bp.rewards:
                    bp_dict['reward'] = [
                        {
                            'card_id': r['card_id'],
                            'probability': r['probability'],
                            'rarity': r.get('rarity', 'r'),
                            'featured': r.get('featured', False),
                            **({'resources_gained': dict(r['resources_gained'])}
                               if r.get('resources_gained') else {}),
                        }
                        for r in bp.rewards
                    ]
                pools.append(bp_dict)
            b_dict['pool'] = pools

        if b.lifecycle:
            lifecycle = []
            for lc in b.lifecycle:
                lc_dict: dict = {'condition': lc.condition}
                if lc.pool is not None:
                    lc_dict['pool'] = lc.pool
                lc_dict['at'] = lc.at / DAY if lc.condition == 'time_window' else lc.at
                if lc.match != 'card_id':
                    lc_dict['match'] = lc.match
                if lc.action != 'switch_to':
                    lc_dict['action'] = lc.action
                if lc.target is not None:
                    lc_dict['target'] = lc.target
                lifecycle.append(lc_dict)
            b_dict['lifecycle'] = lifecycle

        banners.append(b_dict)

    data['banner'] = banners


# ══════════════════════════════════════════════════════════════════
# 各段 _build_* helper
# ══════════════════════════════════════════════════════════════════


def _check_card_format(data: dict) -> None:
    """P65：防御性检测——阻断旧格式卡片段，避免静默数据丢失。

    检测旧段名 [[cards]]（复数）和旧字段名 id（应为 card_id）。
    仅旧格式 → ConfigError 提示手动升级。
    新旧并存 → ConfigError 报告歧义。
    """
    has_old = 'cards' in data
    has_new = 'card' in data

    if has_old and not has_new:
        raise ConfigError(
            "检测到旧格式卡片段 [[cards]]。\n"
            "P65 已将卡片段升级为 [[card]] + card_id 字段。\n"
            "请手动升级 config.toml：\n"
            "  1. [[cards]] → [[card]]\n"
            "  2. id → card_id\n"
            "  3. rarity 保留在顶层\n"
            "  4. 其他维度按需移入 [card.tags] 和 [card.list_tags]"
        )
    if has_old and has_new:
        raise ConfigError(
            "config.toml 中同时存在 [[cards]]（旧格式）和 [[card]]（新格式）段。\n"
            "请移除 [[cards]] 段，仅保留 [[card]] 段。"
        )

    # 字段级检测：[[card]] 段中条目含 id 但缺 card_id
    for i, c in enumerate(data.get('card', [])):
        if 'id' in c and 'card_id' not in c:
            raise ConfigError(
                f"[[card]] 第 {i+1} 个条目使用了旧字段名 'id'，应为 'card_id'。\n"
                f"请将所有卡片条目中的 id 改为 card_id。"
            )
        # ISSUE-014: id 和 card_id 同时存在——歧义场景
        if 'id' in c and 'card_id' in c:
            raise ConfigError(
                f"[[card]] 第 {i+1} 个条目同时包含 'id'（旧字段名，值={c['id']}）和 "
                f"'card_id'（新字段名，值={c['card_id']}）。"
                f"请删除 'id' 字段，仅保留 'card_id'。"
            )


def _warn_cross_table_keys(tags: dict, list_tags: dict, card_id: str) -> None:
    """TOML 加载时检测跨表同名 key——[card.tags] 和 [card.list_tags] 中重复的 key。

    检测逻辑：set(tags.keys()) & set(list_tags.keys())，排除空字符串。
    以单值 tags 为准（多值表中冲突 key 不删除，由用户裁决）。
    """
    overlap = set(tags.keys()) & set(list_tags.keys())
    overlap.discard('')
    if overlap:
        warnings.warn(
            f"卡片 '{card_id}' 的 [card.tags] 和 [card.list_tags] 中存在同名 key："
            f"{', '.join(sorted(overlap))}。将以单值标签为准。"
        )


def _build_cards(data: dict, store: ConfigStore) -> None:
    """[[card]] → store.card_defs（P65：新格式）"""
    _check_card_format(data)
    for c in data.get('card', []):
        # ── 顶层字段 ──
        card_id = c['card_id']
        name = c.get('name', card_id)
        rarity = c.get('rarity', 'r')
        ic = c.get('initial_count', 0)

        # ── 标签 ──
        tags = dict(c.get('tags', {}))
        list_tags: Dict[str, List[str]] = {}
        raw_lt = c.get('list_tags', {})
        for k, v in raw_lt.items():
            if isinstance(v, list):
                list_tags[k] = [str(x) for x in v]
            else:
                list_tags[k] = [str(v)]

        # P65：跨表同名 key 检测
        _warn_cross_table_keys(tags, list_tags, card_id)

        # ── P63：卡片溢出规则解析 ──
        overflow_bands = None
        # 高级模式：[[card.overflow_bands]] 数组——与语法糖不共存
        raw_bands = c.get('overflow_bands')
        if raw_bands:
            parsed_bands = _parse_overflow_bands_array(raw_bands)
            if parsed_bands is not None:
                overflow_bands = parsed_bands
        else:
            # 语法糖模式：[card.overflow] 三字段
            overflow_raw = c.get('overflow')
            if overflow_raw:
                first = overflow_raw.get('first_time_bonus')
                nth_raw = overflow_raw.get('nth_time_bonus')
                # 将 TOML 的整数键还原为 int（tomllib 可能保留为 int）
                nth = None
                if nth_raw:
                    nth = {int(k): v for k, v in nth_raw.items()}
                excess = overflow_raw.get('excess_bonus')
                overflow_bands = expand_sugar_to_bands(
                    first_time_bonus=first,
                    nth_time_bonus=nth,
                    excess_bonus=excess,
                )
                if not overflow_bands:
                    overflow_bands = None  # 全部为空 → 无规则

        store.card_defs.append(CardDefEntry(
            card_id=card_id,
            name=name,
            rarity=rarity,
            initial_count=ic,
            tags=tags,
            list_tags=list_tags,
            overflow_bands=overflow_bands,
        ))


def _build_resources(data: dict, store: ConfigStore) -> None:
    """[resources.defs] + [resources.initial]"""
    res = data.get('resources', {})
    store.resource_defs.update(res.get('defs', {}))
    store.initial_resources.update(res.get('initial', {}))


def _build_gain_rules(data: dict, store: ConfigStore) -> None:
    """[[resources.gain_rules]] → store.gain_rules"""
    res = data.get('resources', {})
    for r in res.get('gain_rules', []):
        store.gain_rules.append(GainRule(
            rule_type=r['type'],
            param=str(r.get('param', '1')),
            gains=dict(r.get('gains', {})),
        ))


def _build_day_overrides(data: dict, store: ConfigStore) -> None:
    """[[resources.day_overrides]] → store.day_overrides"""
    res = data.get('resources', {})
    for d in res.get('day_overrides', []):
        store.day_overrides.append(DayOverride(
            day=d['day'],
            gains=dict(d.get('gains', {})),
        ))


def _build_pity(data: dict, store: ConfigStore) -> None:
    """[[pity]] → store.pity（P55 扁平化 PityDef 格式）。"""
    pity_list = data.get('pity', [])
    if not pity_list:
        store.pity = PityConfig(enabled=True)
        return

    # P55 阶段十B：旧格式自动迁移
    if _is_legacy_format(pity_list):
        pity_list = _migrate_legacy_pity(pity_list)
        store._migrated_from_legacy = True

    # 稀有度 rank map（小写归一化——ISSUE-023/§0.2）
    rarity_rank_map = {k.lower(): v for k, v in store.rarity_rank.items()}

    pities = []
    names_seen: set = set()
    for p in pity_list:
        name = p.get('name', '').strip()
        # ISSUE-037: name 非空校验（TOML 层第一道防线）
        if not name:
            raise ConfigError("[[pity]] 条目缺少 'name' 字段或 name 为空字符串")
        if name in names_seen:
            raise ConfigError(
                f"[[pity]] 条目 name='{name}' 重复——每个保底行为必须有唯一的 name"
            )
        names_seen.add(name)

        btype = p.get('type', 'soft_interval')
        scope = p.get('scope', 'ssr').lower()

        # scope 注册校验（AUDIT-BREAK-1/2 修复）
        if rarity_rank_map and scope not in rarity_rank_map:
            from .pity import logger as pity_logger
            pity_logger.warning(
                f"PityDef '{name}' scope='{scope}' 未在 [rarities] 中注册——"
                f"保底行为将分配给未知稀有度层级。"
            )

        # 解析 deltas / 语法糖参数
        deltas = None
        soft_start = p.get('start')
        soft_end = p.get('end')
        soft_increment = p.get('increment')

        # ISSUE-034：start >= end 前置校验——在静默修正前报错
        if btype == 'soft_interval' and soft_start is not None and soft_end is not None:
            if soft_start >= soft_end:
                raise ConfigError(
                    f"保底 '{name}'：soft_start ({soft_start}) 必须小于 "
                    f"soft_end ({soft_end})"
                )

        if 'deltas' in p:
            deltas = _parse_deltas_value(p['deltas'])
        elif btype in ('soft_interval', 'soft_additive') and soft_start is not None:
            # 语法糖展开：soft_interval / soft_additive → deltas
            deltas = _expand_soft_to_deltas(btype, soft_start, soft_end,
                                            soft_increment, p.get('func', 'linear'))

        # 生命周期参数
        lifecycle_raw = p.get('lifecycle', {})
        deactivate_on_early_hit = lifecycle_raw.get('deactivate_on_early_hit', False)
        depends_on = lifecycle_raw.get('depends_on')

        # P56：deactivate_on_early_hit 仅 counter 驱动型支持
        # 事件驱动型（rotating/targeted）没有「阈值前提前命中」的概念
        _EVENT_TYPES = frozenset({'rotating', 'rotating_soft', 'rotating_cr',
                                   'rotating_cr_soft', 'targeted', 'targeted_soft'})
        if deactivate_on_early_hit and btype in _EVENT_TYPES:
            raise ConfigError(
                f"保底 '{name}'：deactivate_on_early_hit=true 不适用于"
                f"事件驱动型保底（type='{btype}'）。"
            )

        # 构造扁平化 PityDef
        pities.append(PityDef(
            name=name,
            btype=btype,
            scope=scope,
            target_featured=p.get('target_featured', False),
            deltas=deltas,
            threshold=p.get('threshold'),
            counter_init=p.get('counter_init', 0),
            guaranteed_init=p.get('guaranteed_init', False),
            fate_points_init=p.get('fate_points_init', 0),
            selected_card_init=p.get('selected_card_init'),
            soft_start=soft_start,
            soft_end=soft_end,
            soft_increment=soft_increment,
            soft_deltas=_parse_deltas_value(p['deltas']) if 'deltas' in p else None,
            cr_counter_threshold=p.get('cr_counter_threshold'),
            cr_base_rate=p.get('cr_base_rate'),
            cr_state_probs=_parse_state_probs(p.get('cr_state_probs')),
            fate_threshold=p.get('fate_threshold'),
            switch_allowed=p.get('switch_allowed', True),
            switch_resets_progress=p.get('switch_resets_progress', True),
            pools=tuple(p.get('pools', ('*',))) if isinstance(p.get('pools', '*'), list) else (p.get('pools', '*'),),
            deactivate_on_early_hit=deactivate_on_early_hit,
            depends_on=depends_on,
            reset=p.get('reset', ''),
        ))

    store.pity = PityConfig(enabled=True, pities=pities)


def _validate_reward_dict(reward: dict, known_card_ids: set, allow_empty: bool = False) -> dict:
    """校验单个 reward dict（cards / resources / random_cards 三字段，P78 ISSUE-131）。

    供 `_build_milestone` 的 bonus_reward（allow_empty=True——空 {} 合法，ISSUE-503）
    与 alternate_rewards 每个交替项（allow_empty=False——空 {} 拒，ISSUE-112 规则 2）
    共用——与引擎侧 `_resolve_bonus_from(reward)` 同构（交替项与 bonus_reward 同为
    卡片/资源/随机池三字段）。set_config 恢复路径亦经此（ISSUE-114/116 同构校验）。

    **校验 + 规范化写回一体（ISSUE-701）**：非纯校验——对 random_cards 的
    weights/count 原地规范化写回（与 _build_milestone 原 L696-708/L717 行为一致），
    保证 set_config 入口对字符串数值权重同样规范化、引擎 rng.choices 收到 float
    权重不崩溃。副作用声明：原地修改调用方传入的 dict（幂等无害）。

    Args:
        reward: 待校验的 reward dict（cards/resources/random_cards）。
        known_card_ids: 已知卡 id 集合（cards/random_cards 存在性校验）。
        allow_empty: True 时空 {} 直接通过（bonus_reward 合法空奖励里程碑）；
            False 时空 {} 抛 ConfigError（alternate_rewards 空项，ISSUE-112 规则 2）。

    Returns:
        校验后的 reward dict（含 cards/resources/random_cards 三键，规范化后的
        random_cards 写回原 dict）。若 allow_empty=True 且 reward 为空 {} 则原样返回。
    """
    # ISSUE-503：bonus_reward={} 空奖励里程碑是既有合法语义（纯计数/统计锚点）
    if allow_empty and not reward:
        return reward
    if not isinstance(reward, dict):
        raise ConfigError(
            f"奖励项必须是表（dict），当前为 {type(reward).__name__}")

    # ── cards 校验（存在性 + 类型）──
    cards = reward.get('cards', [])
    if not isinstance(cards, list):
        raise ConfigError(
            f"奖励项 cards 必须是数组，当前为 {type(cards).__name__}")
    for cid in cards:
        if cid not in known_card_ids:
            raise ConfigError(f"奖励项 cards 引用不存在的 card_id: '{cid}'")

    # ── resources 校验（类型 + 值数值——ISSUE-303）──
    resources = reward.get('resources', {})
    if not isinstance(resources, dict):
        raise ConfigError(
            f"奖励项 resources 必须是键值对，当前为 {type(resources).__name__}")
    for _rk, _rv in resources.items():
        if not isinstance(_rv, (int, float)) or isinstance(_rv, bool):
            raise ConfigError(
                f"奖励项 resources['{_rk}'] 值必须为数值（int/float），"
                f"当前为 {type(_rv).__name__}")

    # ── random_cards 校验（类型 + candidates 存在性 + weights 数值 + count ≥1）──
    random_cards = reward.get('random_cards', [])
    if not isinstance(random_cards, list):
        raise ConfigError(
            f"奖励项 random_cards 必须是数组，当前为 {type(random_cards).__name__}")
    for i, rc in enumerate(random_cards):
        # ISSUE-606：rc['candidates'] 缺键 KeyError 兜底——显式报错而非裸 KeyError
        if not isinstance(rc, dict):
            raise ConfigError(f"奖励项 random_cards[{i}] 必须是表（dict）")
        candidates = rc.get('candidates')
        if candidates is None:
            raise ConfigError(f"奖励项 random_cards[{i}] 缺少 candidates 字段")
        if not candidates:
            raise ConfigError(f"奖励项 random_cards[{i}].candidates 不得为空")
        for cid in candidates:
            if cid not in known_card_ids:
                raise ConfigError(
                    f"奖励项 random_cards[{i}].candidates 引用不存在的 card_id: '{cid}'")
        if 'weights' in rc and len(rc['weights']) != len(candidates):
            raise ConfigError(
                f"奖励项 random_cards[{i}].weights 长度({len(rc['weights'])})"
                f"与 candidates({len(candidates)})不匹配")
        # ISSUE-302：权重逐项 float 数值校验 + 规范化写回
        wlist = rc.get('weights', [1.0] * len(candidates))
        w_norm: list = []
        for w in wlist:
            try:
                w_norm.append(float(w))
            except (TypeError, ValueError):
                raise ConfigError(
                    f"奖励项 random_cards[{i}].weights 含非数字值 '{w}'"
                    f"（类型 {type(w).__name__}）——必须为数值")
        if w_norm and all(w == 0.0 for w in w_norm):
            raise ConfigError(
                f"奖励项 random_cards[{i}].weights 全为零——random.choices 无法抽样，至少一个权重 > 0")
        rc['weights'] = w_norm
        # ISSUE-301：count 解析期校验 + 规范化写回（ISSUE-701）
        try:
            count = int(rc.get('count', 1))
        except (TypeError, ValueError):
            raise ConfigError(f"奖励项 random_cards[{i}].count 必须为整数")
        if count < 1:
            raise ConfigError(
                f"奖励项 random_cards[{i}].count 必须 ≥ 1（正整数），当前为 {count}")
        rc['count'] = count

    return {
        'cards': list(cards),
        'resources': dict(resources),
        'random_cards': list(random_cards),
    }


def _build_select_voucher(data: dict, store: ConfigStore) -> None:
    """[[select_voucher]] → store.select_vouchers（P78 自选券候选集段）。

    候选集定义——资源 id → 可兑换卡片显式列表。纯元数据声明（模拟结算不消费，
    仅供查询/展示层）。依赖 store.resource_defs（_build_resources 已先执行）做
    voucher id 自动补全、store.card_defs（_build_cards 已先执行）做候选卡存在性校验。
    """
    sv_list = data.get('select_voucher', [])
    if not sv_list:
        store.select_vouchers = []
        return

    known_card_ids = {c.card_id for c in store.card_defs}
    seen_vouchers: set = set()
    vouchers = []
    for i, item in enumerate(sv_list):
        if not isinstance(item, dict):
            raise ConfigError(f"select_voucher[{i}] 必须是表（dict），当前为 {type(item).__name__}")
        raw_voucher = item.get('voucher', '')
        if not isinstance(raw_voucher, str):
            raise ConfigError(f"select_voucher[{i}] voucher 字段必须是字符串，当前为 {type(raw_voucher).__name__}")
        voucher = raw_voucher.strip()
        if not voucher:
            raise ConfigError(f"select_voucher[{i}] 缺少 voucher 字段")
        # ISSUE-111：voucher id 唯一性
        if voucher in seen_vouchers:
            raise ConfigError(f"select_voucher voucher id 重复: '{voucher}'")
        seen_vouchers.add(voucher)

        cards = item.get('cards', [])
        if not isinstance(cards, list):
            raise ConfigError(f"select_voucher '{voucher}' cards 必须是数组，当前为 {type(cards).__name__}")
        # ISSUE-111：候选卡存在性校验
        for cid in cards:
            if not isinstance(cid, str) or cid not in known_card_ids:
                raise ConfigError(
                    f"select_voucher '{voucher}' cards 引用不存在的 card_id: '{cid}'")
        # ISSUE-111：空候选集允许（可兑换空集，模拟不崩溃）但发 warning（ISSUE-105 通道）
        if not cards:
            warnings.warn(
                f"select_voucher '{voucher}' 候选集为空（cards = []）——可兑换空集，"
                "确认是否笔误（P78，ISSUE-105 通道）")
        # ISSUE-005/119：voucher id 自动补全 resource_defs——setdefault 保留既有显示名
        store.resource_defs.setdefault(voucher, voucher)

        vouchers.append(SelectVoucherDef(voucher=voucher, cards=list(cards)))

    store.select_vouchers = vouchers


def _validate_milestone_dict(md_dict: dict, known_card_ids: set) -> MilestoneDef:
    """校验单个里程碑 dict 并构造 MilestoneDef（P78 ISSUE-114/606）。

    供 set_config 恢复路径（config_panel 跨模块复用，ISSUE-125 契约——与
    `_normalize_permanent_banners` 先例同构）构造 MilestoneDef 前校验——校验范围
    与 `_build_milestone` 全量同构（name/threshold/max_triggers/repeat/banner/
    bonus_reward/alternate_rewards/offset），保证「同一非法配置经 TOML 与
    set_config 两入口均被拒」；D6/D7/ISSUE-120 warning 亦同强度复跑（ISSUE-707）。

    Args:
        md_dict: 里程碑配置 dict（get_config 输出或外部 JSON 恢复源）。
        known_card_ids: 已知卡 id 集合（cards/random_cards 存在性校验，ISSUE-201）。

    Returns:
        校验后的 MilestoneDef 实例。

    Raises:
        ConfigError: 任一字段非法（与 _build_milestone 同强度）。
    """
    # ISSUE-606：与 _build_milestone 同构——非 dict 类型守卫（set_config 注入 None/str
    # 时抛 ConfigError 而非裸 AttributeError，两入口错误通道一致）
    if not isinstance(md_dict, dict):
        raise ConfigError(
            f"里程碑配置项必须是表（dict），当前为 {type(md_dict).__name__}")
    # name
    raw_name = md_dict.get('name', '')
    if not isinstance(raw_name, str):
        raise ConfigError(
            f"里程碑 name 字段必须是字符串，当前为 {type(raw_name).__name__}")
    name = raw_name.strip()
    if not name:
        raise ConfigError("里程碑缺少 name 字段")

    # threshold/max_triggers——拒 bool/float（ISSUE-606 全量同构）
    for field, default in (('threshold', 40), ('max_triggers', 0)):
        val = md_dict.get(field, default)
        if isinstance(val, bool) or not isinstance(val, int):
            raise ConfigError(
                f"里程碑 '{name}' {field} 必须为整数，当前为 {type(val).__name__}"
                f"（值 {val!r}）")
    threshold = md_dict['threshold'] if 'threshold' in md_dict else 40
    max_triggers = md_dict['max_triggers'] if 'max_triggers' in md_dict else 0
    if threshold < 1:
        raise ConfigError(f"里程碑 '{name}' 阈值必须 ≥ 1，当前为 {threshold}")
    if max_triggers < 0:
        raise ConfigError(
            f"里程碑 '{name}' max_triggers 必须 ≥ 0（0=无限触发），当前为 {max_triggers}")

    # repeat——拒字符串 truthy
    repeat = md_dict.get('repeat', False)
    if not isinstance(repeat, bool):
        raise ConfigError(
            f"里程碑 '{name}' repeat 必须是布尔值，当前为 {type(repeat).__name__}")

    # banner——类型
    raw_banner = md_dict.get('banner', '')
    if not isinstance(raw_banner, str):
        raise ConfigError(f"里程碑 '{name}' banner 字段必须是字符串（空 = 全部）")

    # bonus_reward——委托 _validate_reward_dict（allow_empty=True，空 {} 合法，ISSUE-503）
    br = md_dict.get('bonus_reward', {})
    if not isinstance(br, dict):
        raise ConfigError(
            f"里程碑 '{name}' bonus_reward 必须是表（dict），当前为 {type(br).__name__}")
    bonus_reward = _validate_reward_dict(br, known_card_ids, allow_empty=True)

    # alternate_rewards——与 _build_milestone 同构（ISSUE-112/120）
    alt_key_present = 'alternate_rewards' in md_dict
    alt_raw = md_dict.get('alternate_rewards', [])
    if alt_key_present and not isinstance(alt_raw, list):
        raise ConfigError(
            f"里程碑 '{name}' alternate_rewards 必须是数组，当前为 {type(alt_raw).__name__}")
    if alt_key_present and len(alt_raw) == 0:
        raise ConfigError(
            f"里程碑 '{name}' 显式配置了空 alternate_rewards = []——"
            "交替奖励为空却声明该键（与未配置等效却易误导），请删除该键或填写交替项")
    if len(alt_raw) == 1:
        warnings.warn(
            f"里程碑 '{name}' alternate_rewards 仅 1 项——单元素交替列表等价于 "
            "bonus_reward（% len(...) 恒返回同一项），确认是否笔误（P78，ISSUE-105 通道）")
    alternate_rewards: list = []
    for _i, item in enumerate(alt_raw):
        if not isinstance(item, dict):
            raise ConfigError(
                f"里程碑 '{name}' alternate_rewards[{_i}] 必须是表（dict），"
                f"当前为 {type(item).__name__}")
        if not item:
            raise ConfigError(
                f"里程碑 '{name}' alternate_rewards[{_i}] 为空项 {{}}——"
                "至少含 cards/resources/random_cards 之一")
        alternate_rewards.append(
            _validate_reward_dict(item, known_card_ids, allow_empty=False))

    # offset——ISSUE-007（int、≥0、threshold+offset≥1）
    offset = md_dict.get('offset', 0)
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise ConfigError(
            f"里程碑 '{name}' offset 必须为整数，当前为 {type(offset).__name__}"
            f"（值 {offset!r}）")
    if offset < 0:
        raise ConfigError(
            f"里程碑 '{name}' offset 必须 ≥ 0（负 offset 非法——首节点不得早于 threshold），"
            f"当前为 {offset}")
    if threshold + offset < 1:
        raise ConfigError(
            f"里程碑 '{name}' threshold + offset 必须 ≥ 1，当前为 {threshold + offset}")

    # D6/D7 warning 同强度复跑（ISSUE-707）
    if offset != 0 and not repeat:
        warnings.warn(
            f"里程碑 '{name}' 配置了 offset={offset} 但 repeat=False（at=N 单次触发）——"
            "offset 仅推后单次触发点（首节点 = threshold+offset），确认语义正确（P78，ISSUE-105 通道）")
    if alternate_rewards and not repeat:
        warnings.warn(
            f"里程碑 '{name}' 配置了 alternate_rewards 但 repeat=False（at=N 单次触发）——"
            "交替序列仅触发一次、只取第一项 A，B 及后续永不使用，确认是否笔误（P78，ISSUE-105 通道）")

    return MilestoneDef(
        name=name,
        threshold=threshold,
        repeat=repeat,
        max_triggers=max_triggers,
        bonus_reward=bonus_reward,
        banner=raw_banner,
        alternate_rewards=alternate_rewards,
        offset=offset,
    )


def _validate_select_voucher_dict(sv_list: list, known_card_ids: set) -> list:
    """校验 select_voucher 条目列表并返回 SelectVoucherDef 列表（P78 ISSUE-116）。

    供 set_config 恢复路径跨模块复用——校验范围与 `_build_select_voucher` 全量同构
    （voucher 类型/空/去重 + cards 类型/候选卡存在性 + 空候选集 warning），保证
    「同一非法配置经 TOML 与 set_config 两入口均被拒」且 warning 强度一致。

    Args:
        sv_list: select_voucher 条目 dict 列表（get_config 输出或外部 JSON 恢复源，
            条目格式与 TOML `[[select_voucher]]` 段同构：{'voucher', 'cards'}）。
        known_card_ids: 已知卡 id 集合（ISSUE-201）。

    Returns:
        校验后的 SelectVoucherDef 列表。

    Raises:
        ConfigError: 任一条目非法。
    """
    if not isinstance(sv_list, list):
        raise ConfigError(
            f"select_voucher 必须是数组，当前为 {type(sv_list).__name__}")
    seen_vouchers: set = set()
    result = []
    for i, item in enumerate(sv_list):
        if not isinstance(item, dict):
            raise ConfigError(
                f"select_voucher[{i}] 必须是表（dict），当前为 {type(item).__name__}")
        raw_voucher = item.get('voucher', '')
        if not isinstance(raw_voucher, str):
            raise ConfigError(
                f"select_voucher[{i}] voucher 字段必须是字符串，当前为 {type(raw_voucher).__name__}")
        voucher = raw_voucher.strip()
        if not voucher:
            raise ConfigError(f"select_voucher[{i}] 缺少 voucher 字段")
        if voucher in seen_vouchers:
            raise ConfigError(f"select_voucher voucher id 重复: '{voucher}'")
        seen_vouchers.add(voucher)

        cards = item.get('cards', [])
        if not isinstance(cards, list):
            raise ConfigError(
                f"select_voucher '{voucher}' cards 必须是数组，当前为 {type(cards).__name__}")
        for cid in cards:
            if not isinstance(cid, str) or cid not in known_card_ids:
                raise ConfigError(
                    f"select_voucher '{voucher}' cards 引用不存在的 card_id: '{cid}'")
        if not cards:
            warnings.warn(
                f"select_voucher '{voucher}' 候选集为空（cards = []）——可兑换空集，"
                "确认是否笔误（P78，ISSUE-105 通道）")
        result.append(SelectVoucherDef(voucher=voucher, cards=list(cards)))
    return result


def _build_milestone(data: dict, store: ConfigStore) -> None:
    """[[milestone]] → store.milestone（P58 累抽奖励段）。

    独立于保底体系——milestone 不操作概率、旁路注入。依赖 store.card_defs
    （_build_cards 已先执行）做 cards/random_cards 引用存在性校验。
    """
    ml_list = data.get('milestone', [])
    if not ml_list:
        store.milestone = MilestoneConfig(enabled=True)
        return

    # card_id 引用校验集合（ISSUE-101：store.card_defs 是 List[CardDefEntry]，
    # 禁止 `cid not in store.card_defs`——str in 列表恒 False）
    known_card_ids = {c.card_id for c in store.card_defs}

    seen_names: set = set()
    milestones = []
    for m in ml_list:
        # ISSUE-012：全部输入校验统一走 ConfigError 通道（禁止裸 KeyError/ValueError）
        # 代码审查 F1（2026-08-05）：m 非 dict / name 非 str → ConfigError 而非裸 AttributeError
        if not isinstance(m, dict):
            raise ConfigError(f"里程碑配置项必须是表（dict），当前为 {type(m).__name__}")
        raw_name = m.get('name', '')
        if not isinstance(raw_name, str):
            raise ConfigError(
                f"里程碑 name 字段必须是字符串，当前为 {type(raw_name).__name__}")
        name = raw_name.strip()
        if not name:
            raise ConfigError("里程碑缺少 name 字段")
        if name in seen_names:
            raise ConfigError(f"里程碑名称重复: '{name}'")
        seen_names.add(name)

        # 代码审查 F3（2026-08-05）：threshold/max_triggers 拒绝 bool 与 float 截断（静默误配置）
        for field, val in (('threshold', m.get('threshold', 40)),
                           ('max_triggers', m.get('max_triggers', 0))):
            if isinstance(val, bool) or not isinstance(val, int):
                raise ConfigError(
                    f"里程碑 '{name}' {field} 必须为整数，当前为 {type(val).__name__}"
                    f"（值 {val!r}）")
        threshold = m['threshold'] if 'threshold' in m else 40
        max_triggers = m['max_triggers'] if 'max_triggers' in m else 0

        if threshold < 1:
            raise ConfigError(f"里程碑 '{name}' 阈值必须 ≥ 1，当前为 {threshold}")

        # 代码审查 F2（2026-08-05）：max_triggers 负数 → 触发一次即永久停用的静默行为偏离
        if max_triggers < 0:
            raise ConfigError(
                f"里程碑 '{name}' max_triggers 必须 ≥ 0（0=无限触发），当前为 {max_triggers}")

        br = m.get('bonus_reward', {})
        if not isinstance(br, dict):
            raise ConfigError(
                f"里程碑 '{name}' bonus_reward 必须是表（dict），当前为 {type(br).__name__}")

        # ── bonus_reward 校验（P78 委托 _validate_reward_dict，allow_empty=True——空 {} 合法，ISSUE-503）──
        bonus_reward = _validate_reward_dict(br, known_card_ids, allow_empty=True)

        # ── P78: alternate_rewards 解析（交替奖励序列——ISSUE-006/112）──
        # 区分「键存在与否」：显式空列表抛 ConfigError（用户写了以为在交替、实际静默
        # 回退 bonus_reward），键缺失走默认值 []（不配置旧 TOML 行为完全不变）。
        alt_key_present = 'alternate_rewards' in m
        alternate_rewards_raw = m.get('alternate_rewards', [])
        if alt_key_present and not isinstance(alternate_rewards_raw, list):
            raise ConfigError(
                f"里程碑 '{name}' alternate_rewards 必须是数组，当前为 {type(alternate_rewards_raw).__name__}")
        if alt_key_present and len(alternate_rewards_raw) == 0:
            raise ConfigError(
                f"里程碑 '{name}' 显式配置了空 alternate_rewards = []——"
                "交替奖励为空却声明该键（与未配置等效却易误导），请删除该键或填写交替项")
        # ISSUE-120：单元素交替列表发 warning（等价于 bonus_reward，疑似笔误）
        if len(alternate_rewards_raw) == 1:
            warnings.warn(
                f"里程碑 '{name}' alternate_rewards 仅 1 项——单元素交替列表等价于 "
                "bonus_reward（% len(...) 恒返回同一项），确认是否笔误（P78，ISSUE-105 通道）")
        # 逐项校验（allow_empty=False——空 {} 项拒，ISSUE-112 规则 2）
        alternate_rewards: list = []
        for _i, item in enumerate(alternate_rewards_raw):
            if not isinstance(item, dict):
                raise ConfigError(
                    f"里程碑 '{name}' alternate_rewards[{_i}] 必须是表（dict），"
                    f"当前为 {type(item).__name__}")
            # ISSUE-112 规则 2：空项 {}（无 cards/resources/random_cards 任一）抛 ConfigError
            if not item:
                raise ConfigError(
                    f"里程碑 '{name}' alternate_rewards[{_i}] 为空项 {{}}——"
                    "至少含 cards/resources/random_cards 之一")
            alternate_rewards.append(
                _validate_reward_dict(item, known_card_ids, allow_empty=False))

        # 代码审查 F3（2026-08-05）：repeat 拒绝字符串 truthy（如 repeat = "false" 被当 True）
        # P78：提前到 offset/alternate_rewards 之前——D6/D7 warning 需判断 repeat
        repeat = m.get('repeat', False)
        if not isinstance(repeat, bool):
            raise ConfigError(
                f"里程碑 '{name}' repeat 必须是布尔值，当前为 {type(repeat).__name__}")

        # ── P78: offset 解析（ISSUE-007——int 拒 bool/float、offset ≥ 0、threshold+offset ≥ 1）──
        offset = m.get('offset', 0)
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise ConfigError(
                f"里程碑 '{name}' offset 必须为整数，当前为 {type(offset).__name__}"
                f"（值 {offset!r}）")
        # ISSUE-501：显式 offset ≥ 0（原「threshold+offset ≥ 1 兜底」数学上不成立——threshold+offset
        # 恒 = 首次触发，GUI 已保证 ≥ 1，永不触发拒绝；须显式 offset ≥ 0 拒绝负 offset）
        if offset < 0:
            raise ConfigError(
                f"里程碑 '{name}' offset 必须 ≥ 0（负 offset 非法——首节点不得早于 threshold），"
                f"当前为 {offset}")
        if threshold + offset < 1:
            raise ConfigError(
                f"里程碑 '{name}' threshold + offset 必须 ≥ 1，当前为 {threshold + offset}")

        # D6：offset × at=N（repeat=False）语义易混淆 → warning（非 ConfigError）
        if offset != 0 and not repeat:
            warnings.warn(
                f"里程碑 '{name}' 配置了 offset={offset} 但 repeat=False（at=N 单次触发）——"
                "offset 仅推后单次触发点（首节点 = threshold+offset），确认语义正确（P78，ISSUE-105 通道）")
        # D7：alternate_rewards × repeat=False 只取 A → warning（非 ConfigError）
        if alternate_rewards and not repeat:
            warnings.warn(
                f"里程碑 '{name}' 配置了 alternate_rewards 但 repeat=False（at=N 单次触发）——"
                "交替序列仅触发一次、只取第一项 A，B 及后续永不使用，确认是否笔误（P78，ISSUE-105 通道）")

        # ── banner 过滤（类型检查；存在性校验推迟到 M9——P61 已落地，见计划）──
        raw_banner = m.get('banner', '')
        if not isinstance(raw_banner, str):
            raise ConfigError(f"里程碑 '{name}' banner 字段必须是字符串（空 = 全部）")

        milestones.append(MilestoneDef(
            name=name,
            threshold=threshold,
            repeat=repeat,
            max_triggers=max_triggers,
            bonus_reward=bonus_reward,
            banner=raw_banner,
            # ── P78 新增（解析期已校验）──
            alternate_rewards=alternate_rewards,
            offset=offset,
        ))

    store.milestone = MilestoneConfig(enabled=True, milestones=milestones)


def _build_resource_lifecycle(data: dict, store: ConfigStore) -> None:
    """[resources.lifecycle] → store.resource_lifecycle（P77）。

    enabled 开关：顶层启用标志。关闭时 rules 仍解析校验，透传期收敛为空
    （见 batch_simulator）。显式报错而非静默漂移：
    到期时刻二选一 / banner 引用 / 永久池拒绝 / resource_id 存在性 / 去重 /
    on_expire 两态 / 自环 / 到期与动作成对 / from,to 正整数。
    """
    from .resource_lifecycle import ResourceLifecycle, ResourceLifecycleConfig

    raw = data.get('resources', {}).get('lifecycle')
    if raw is None:
        store.resource_lifecycle = ResourceLifecycleConfig(enabled=True, rules=[])
        return
    if not isinstance(raw, dict):
        raise ConfigError("resources.lifecycle 必须是表（dict）")
    enabled = raw.get('enabled', True)
    if not isinstance(enabled, bool):
        raise ConfigError("resources.lifecycle.enabled 必须是布尔值")
    rules_raw = raw.get('rules', [])
    if not isinstance(rules_raw, list):
        raise ConfigError("resources.lifecycle.rules 必须是数组")

    # banner id → available_until 映射（用于 expire_with_banner 展开与引用校验）
    banner_until = {b.id: b.available_until for b in store.banner.banners}
    banner_ids = set(banner_until.keys())
    # 归一前永久池（无 end_day）：不可作为到期对齐目标（复用虚假归一时间）
    permanent_ids = {b.id for b in store.banner.banners
                     if getattr(b, '_is_permanent', False)}

    seen_resource = set()
    rules: List[ResourceLifecycle] = []
    for idx, item in enumerate(rules_raw):
        if not isinstance(item, dict):
            raise ConfigError(f"resources.lifecycle.rules[{idx}] 必须是表（dict）")
        rid = item.get('resource_id', '')
        if not isinstance(rid, str) or not rid.strip():
            raise ConfigError(f"resources.lifecycle.rules[{idx}] 缺少 resource_id")
        rid = rid.strip()
        # 同一 resource_id 只允许一条
        if rid in seen_resource:
            raise ConfigError(f"resources.lifecycle: resource_id '{rid}' 重复，一个资源只允许一条生命周期")
        seen_resource.add(rid)
        # resource_id 必须已在 resource_defs 中定义
        if rid not in store.resource_defs:
            raise ConfigError(f"resources.lifecycle.rules[{idx}] 的 resource_id '{rid}' 未在 [resources.defs] 中定义")

        has_at = 'expire_at' in item
        has_banner = 'expire_with_banner' in item
        if has_at == has_banner:
            raise ConfigError(
                f"resources.lifecycle.rules[{idx}] 的 expire_at 与 expire_with_banner 必须二选一"
            )

        expire_at_sec = None
        expire_with_banner = None
        if has_at:
            try:
                expire_at_sec = float(item['expire_at']) * DAY
            except Exception:
                raise ConfigError(f"resources.lifecycle.rules[{idx}] 的 expire_at 必须为数值（天）")
        else:
            eb = item.get('expire_with_banner', '')
            if not isinstance(eb, str) or not eb.strip():
                raise ConfigError(f"resources.lifecycle.rules[{idx}] 的 expire_with_banner 必须为非空字符串")
            eb = eb.strip()
            if eb not in banner_ids:
                raise ConfigError(
                    f"resources.lifecycle.rules[{idx}] 的 expire_with_banner '{eb}' 不存在"
                )
            if eb in permanent_ids:
                raise ConfigError(
                    f"resources.lifecycle.rules[{idx}] 的 expire_with_banner '{eb}' 指向永久 Banner"
                    "（归一前无结束时间，需为该 Banner 显式配置 end_day）"
                )
            avail = banner_until.get(eb)
            if avail is None:
                raise ConfigError(
                    f"resources.lifecycle.rules[{idx}] 的 expire_with_banner '{eb}' 无可用结束时间"
                )
            expire_with_banner = eb

        on_expire = item.get('on_expire')
        if on_expire is None or not isinstance(on_expire, dict) or not on_expire:
            raise ConfigError(
                f"resources.lifecycle.rules[{idx}] 缺少 on_expire 或 on_expire 既不是转换也不是清零"
                "，到期时间与 on_expire 必须成对出现"
            )
        has_convert = 'convert_to' in on_expire
        has_clear = 'clear' in on_expire
        if has_convert == has_clear:
            raise ConfigError(
                f"resources.lifecycle.rules[{idx}] 的 on_expire 必须二选一："
                "转换（convert_to+from/to）或清零（clear）"
            )
        if has_convert:
            tgt = on_expire.get('convert_to', '')
            if not isinstance(tgt, str) or not tgt.strip():
                raise ConfigError(
                    f"resources.lifecycle.rules[{idx}] 的 on_expire.convert_to 必须为非空字符串"
                )
            tgt = tgt.strip()
            if tgt == rid:
                raise ConfigError(
                    f"resources.lifecycle.rules[{idx}] 的 convert_to 不能与 resource_id 相同（自环无意义）"
                )
            # from/to 正整数
            fval = on_expire.get('from')
            tval = on_expire.get('to')
            if isinstance(fval, bool) or not isinstance(fval, int):
                raise ConfigError(
                    f"resources.lifecycle.rules[{idx}] 的 on_expire.from 必须为正整数"
                )
            if isinstance(tval, bool) or not isinstance(tval, int):
                raise ConfigError(
                    f"resources.lifecycle.rules[{idx}] 的 on_expire.to 必须为正整数"
                )
            if fval < 1 or tval < 1:
                raise ConfigError(
                    f"resources.lifecycle.rules[{idx}] 的 on_expire.from/to 必须 ≥ 1"
                )
            on_expire_norm = {'convert_to': tgt, 'from': int(fval), 'to': int(tval)}
        else:
            # clear 分支：值任意 truthy 均视为清零（与示例 clear=true 同构）
            on_expire_norm = {'clear': True}

        rules.append(ResourceLifecycle(
            resource_id=rid,
            expire_at=expire_at_sec,
            expire_with_banner=expire_with_banner,
            on_expire=on_expire_norm,
        ))

    store.resource_lifecycle = ResourceLifecycleConfig(enabled=bool(enabled), rules=rules)


def _save_resource_lifecycle(store: ConfigStore, data: dict) -> None:
    """将 store.resource_lifecycle 写回 data['resources']['lifecycle']（P77）。

    两档条件写键：
    - enabled==False 恒写（保留关闭态，避免往返丢失）
    - enabled==True 且 rules 非空才写段，空列表省略段
    """
    lc = getattr(store, 'resource_lifecycle', None)
    if lc is None:
        return
    if not lc.enabled:
        # 关闭态恒写（rules 可空亦保留开关）
        rules_out = []
        for r in lc.rules:
            item = {'resource_id': r.resource_id}
            if r.expire_at is not None:
                item['expire_at'] = float(r.expire_at) / DAY
            elif r.expire_with_banner:
                item['expire_with_banner'] = r.expire_with_banner
            item['on_expire'] = dict(r.on_expire) if r.on_expire else {}
            rules_out.append(item)
        data['resources']['lifecycle'] = {'enabled': False, 'rules': rules_out}
        return
    if not lc.rules:
        return
    rules_out = []
    for r in lc.rules:
        item = {'resource_id': r.resource_id}
        if r.expire_at is not None:
            item['expire_at'] = float(r.expire_at) / DAY
        elif r.expire_with_banner:
            item['expire_with_banner'] = r.expire_with_banner
        item['on_expire'] = dict(r.on_expire) if r.on_expire else {}
        rules_out.append(item)
    data['resources']['lifecycle'] = {'enabled': True, 'rules': rules_out}



def _expand_soft_to_deltas(btype: str, start, end, increment, func: str = 'linear') -> tuple:
    """将 soft_interval / soft_additive 语法糖展开为 deltas。

    soft_interval: [[start, 0.0], [end-start, 100/(end-start)%]]
      例：start=73, end=90 → ((73, 0.0), (17, 5.88235...))
    soft_additive: [[start, 0.0], [1, increment], [1, increment], ...]
      注：每抽递增 i% → 简化为 ((start, 0.0), (1, increment), (1, increment), ...)
      但为了 RLE 效率，将连续相同 increment 合并为一段。
      实际：((start, 0.0), (∞, increment)) 但 ∞ 不现实——
      改为 ((start, 0.0), (remaining, increment))，remaining 取到 100% 为止。
    """
    if btype == 'soft_interval':
        s = int(start) if start else 0
        e = int(end) if end else 90
        if e <= s:
            e = s + 1
        n_steps = e - s
        inc = 100.0 / n_steps
        return ((s, 0.0), (n_steps, round(inc, 6)))

    if btype == 'soft_additive':
        s = int(start) if start is not None else 0
        inc = float(increment) if increment is not None else 6.0
        # 计算达到 100% 所需的抽数（封顶）
        if inc > 0:
            n_steps = int(100.0 / inc) + 1
        else:
            n_steps = 1
        return ((s, 0.0), (n_steps, inc))

    # func 参数在 P55 后不再支持——仅 linear
    return ()


def _parse_deltas_value(value) -> Optional[tuple]:
    """解析 deltas 值 → tuple[tuple[int, float], ...] 或 None。"""
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        result = []
        for seg in value:
            if isinstance(seg, (tuple, list)) and len(seg) >= 2:
                result.append((int(seg[0]), float(seg[1])))
        return tuple(result) if result else None
    return None


def _parse_state_probs(value) -> Optional[tuple]:
    """解析 cr_state_probs → tuple[float, ...] 或 None。"""
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        return tuple(float(v) for v in value)
    return None


def _deltas_to_soft_interval(deltas: tuple) -> tuple:
    """deltas → (soft_start, soft_end) 反向还原。

    仅当 deltas 符合 soft_interval 模式时可用：
    ((N, 0.0), (M, inc)) 其中 inc 为常数。
    返回 ((start, end),) 或 None（若无法还原）。

    例：((73, 0.0), (17, 5.882353)) → (73, 90)
    """
    if not deltas or len(deltas) != 2:
        return None
    n1, inc1 = deltas[0]
    n2, inc2 = deltas[1]
    if inc1 != 0.0:
        return None  # 首段增量非零——非 soft_interval 模式
    return (n1, n1 + n2)


def _pitydef_to_toml(p) -> dict:
    """P55：PityDef → TOML dict（round-trip 可逆）。"""
    entry = {'name': p.name, 'type': p.btype, 'scope': p.scope}

    # 核心参数
    if p.threshold is not None:
        entry['threshold'] = p.threshold
    if p.target_featured:
        entry['target_featured'] = True
    if p.reset:
        entry['reset'] = p.reset
    if p.pools != ('*',):
        # P61（ISSUE-328）：pools=()（空勾选 = 不绑定任何池）必须显式写出 pools = []
        # ——否则重载默认 ('*',) 语义反转（不绑定 → 绑定全部池）
        entry['pools'] = list(p.pools)

    # 语法糖参数（优先写出直观形式，否则写出 deltas）
    if p.btype == 'soft_interval' and p.soft_start is not None and p.soft_end is not None:
        entry['start'] = p.soft_start
        entry['end'] = p.soft_end
    elif p.btype == 'soft_additive' and p.soft_start is not None and p.soft_increment is not None:
        entry['start'] = p.soft_start
        entry['increment'] = p.soft_increment
    elif p.deltas is not None:
        entry['deltas'] = [list(seg) for seg in p.deltas]

    # 初始状态
    if p.counter_init:
        entry['counter_init'] = p.counter_init
    if p.guaranteed_init:
        entry['guaranteed_init'] = True
    if p.fate_points_init:
        entry['fate_points_init'] = p.fate_points_init
    if p.selected_card_init:
        entry['selected_card_init'] = p.selected_card_init

    # 事件驱动型参数
    if p.cr_counter_threshold is not None:
        entry['cr_counter_threshold'] = p.cr_counter_threshold
    if p.cr_base_rate is not None:
        entry['cr_base_rate'] = p.cr_base_rate
    if p.cr_state_probs is not None:
        entry['cr_state_probs'] = list(p.cr_state_probs)
    if p.fate_threshold is not None:
        entry['fate_threshold'] = p.fate_threshold
    if not p.switch_allowed:
        entry['switch_allowed'] = False
    if not p.switch_resets_progress:
        entry['switch_resets_progress'] = False

    # 生命周期
    lifecycle = {}
    if p.deactivate_on_early_hit:
        lifecycle['deactivate_on_early_hit'] = True
    if p.depends_on:
        lifecycle['depends_on'] = p.depends_on
    if lifecycle:
        entry['lifecycle'] = lifecycle

    return entry


# ══════════════════════════════════════════════════════════════════
# P55 阶段十B：旧格式自动迁移
# ══════════════════════════════════════════════════════════════════

# 旧格式特征字段——这些字段在新格式中不存在（被扁平化替代）
_LEGACY_PITY_KEYS = frozenset({'start', 'end', 'func', 'reset', 'target',
                               'counter_init_top'})


def _is_legacy_format(pity_list: list) -> bool:
    """检测 [[pity]] 节是否使用旧格式。

    旧格式特征：条目含 'start'/'end'/'func' 等语法糖字段（非新格式的 'scope'/'deltas'）。
    """
    if not pity_list:
        return False
    for p in pity_list:
        keys = set(p.keys())
        if 'start' in keys and 'scope' not in keys:
            return True
        if 'func' in keys:
            return True
    return False


def _migrate_legacy_pity(pity_list: list) -> list:
    """将旧格式 [[pity]] 条目迁移为新格式。

    旧格式示例：
      {name='p1', type='soft', start=74, end=90, func='linear', reset='any_ssr'}
    新格式示例：
      {name='p1', type='soft_interval', scope='ssr', start=74, end=90,
       deltas=((74,0.0),(16,6.25))}

    func='exp'/'step' 不支持——抛出 ConfigError。
    """
    if not pity_list:
        return pity_list

    new_pities = []
    for p in pity_list:
        btype = p.get('type', 'soft')
        name = p.get('name', 'pity')

        # 映射旧 type → 新 btype
        if btype == 'soft':
            btype = 'soft_interval'

        entry = {'name': name, 'type': btype, 'scope': 'ssr'}

        # func 检查——仅 linear 支持
        func = p.get('func', 'linear')
        if func not in ('linear', '', None):
            raise ConfigError(
                f"Pity '{name}': func='{func}' 在 P55 后不再支持——"
                f"仅 linear 可用。如需自定义爬升曲线，请使用 soft_step + deltas。"
            )

        # start/end → soft_interval 参数
        start = p.get('start')
        end_val = p.get('end')
        if start is not None:
            entry['start'] = int(start)
        if end_val is not None:
            entry['end'] = int(end_val)

        # increment → soft_additive 参数
        increment = p.get('increment')
        if increment is not None:
            entry['increment'] = float(increment)

        # threshold → hard 参数
        threshold = p.get('threshold')
        if threshold is not None:
            entry['threshold'] = int(threshold)

        # reset 条件
        reset = p.get('reset')
        if reset and reset != 'any_ssr':
            entry['reset'] = reset

        # target_distribution → target_featured
        target = p.get('target', {})
        if target:
            entry['target_featured'] = True

        # pools
        pools = p.get('pools', '*')
        if pools != '*':
            entry['pools'] = [pools] if isinstance(pools, str) else list(pools)

        # counter_init（旧格式中可能在顶层）
        ci = p.get('counter_init', 0)
        if ci:
            entry['counter_init'] = int(ci)

        # deltas（如果旧格式直接有 deltas）
        deltas = p.get('deltas')
        if deltas is not None:
            entry['deltas'] = deltas

        new_pities.append(entry)

    return new_pities


def _build_rarity_defaults(data: dict, store: ConfigStore) -> None:
    """[rarity_defaults] → store.rarity_defaults。

    稀有度键名统一 .lower() 归一化存储——与 rarity_rank 的 .upper() 方向互补。
    .lower() 用于 TOML 段名查找（不分大小写），.upper() 用于展示/排序。

    TOML 格式：
      [rarity_defaults.ssr]
      [[rarity_defaults.ssr.overflow_bands]]
      range = [1, 7]
      resources = { starglitter = 10 }
    """
    raw = data.get('rarity_defaults', {})
    if not raw:
        return

    store.rarity_defaults.clear()
    for rarity_name, rd_config in raw.items():
        key = rarity_name.lower()
        entry: dict = {}
        raw_bands = rd_config.get('overflow_bands', [])
        if raw_bands:
            bands = _parse_overflow_bands_array(raw_bands)
            if bands:
                entry['overflow_bands'] = bands
        if entry:
            store.rarity_defaults[key] = entry


def _build_targets(data: dict, store: ConfigStore) -> None:
    """[[targets]] → store.target_cards"""
    for t in data.get('targets', []):
        store.target_cards.append(TargetCardEntry(
            card_id=t['card_id'],
            quantity=t.get('quantity', 1),
            pool_ids=list(t.get('pool_ids', [])),
        ))


def _build_strategy(data: dict, store: ConfigStore) -> None:
    """[strategy] → store.strategy_key + store.strategy_params（P69：key + params 格式）。

    旧 TOML type + name 格式自动检测并迁移到 key 格式。
    key 不存在时回退 'smart'。
    """
    strat = data.get('strategy', {})
    if not strat:
        return

    # 新格式：key + params
    if 'key' in strat:
        store.strategy_key = str(strat['key'])
        store.strategy_params = dict(strat.get('params', {}))
        return

    # 旧格式兼容：type(显示名) + name(key) —— 自动迁移
    if 'name' in strat:
        store.strategy_key = str(strat['name'])
        store.strategy_params = dict(strat.get('params', {}))
        return


def _build_plugins(data: dict, store: ConfigStore) -> None:
    """[plugins] → 设置 StrategyMeta.disabled = True（P69 阶段 4d）。"""
    plugins = data.get('plugins', {})
    disabled_list = plugins.get('disabled', [])
    if not disabled_list:
        return

    from .strategy import STRATEGY_REGISTRY
    for key in disabled_list:
        meta = STRATEGY_REGISTRY.get(key)
        if meta is not None and not meta.internal:
            meta.disabled = True


def _build_weights(data: dict, store: ConfigStore) -> None:
    """[[weights]] 数组表 → store.card_weights"""
    for w in data.get('weights', []):
        cid = w['card_id']
        store.card_weights[cid] = CardWeightEntry(
            desire_weight=float(w.get('desire', 1.0)),
            miss_cost_weight=float(w.get('miss_cost', 1.0)),
            card_value=float(w.get('card_value', 1.0)),
        )


def _build_banners(data: dict, store: ConfigStore) -> None:
    """[[banner]] → store.banner.banners。

    只认 [[banner]]（D3/D4 一次性迁移，无自动包装路径）；旧 [[pools]] 段残留不解析
    （load_toml 检测到残留时显式警告，ISSUE-004）。
    - start_day/end_day（天）→ available_from/until（秒，*DAY，ISSUE-001）
    - max_draws=0（「0=无限制」合法写法）归一化为 None（ISSUE-331）
    - lifecycle time_window.at（模拟内相对天数）*DAY 换算为秒
    - rewards 统一 dict 表示（ISSUE-304）；exchange_card_id 快捷方式 → 100% 单卡分布
    - pool_type/rerun_of 旧键解析时忽略（不报错，ISSUE-012）
    """
    for b in data.get('banner', []):
        banner_id = b['id']
        _raw_end_day = b.get('end_day')
        banner_entry = BannerEntry(
            id=banner_id,
            name=b.get('name', banner_id),
            enabled=b.get('enabled', True),
            max_draws=_normalize_max_draws(b.get('max_draws')),
            available_from=_days_to_sec(b.get('start_day')),
            available_until=_days_to_sec(_raw_end_day),
            # P77：记录归一前永久池标记（end_day 缺省）——归一后 available_until 恒非 None
            _is_permanent=(_raw_end_day is None),
        )

        for bp in b.get('pool', []):
            rewards = _parse_pool_rewards(bp)
            banner_entry.pools.append(BannerPoolEntry(
                id=bp['id'],
                cost=bp.get('cost', 'draw_resource:160'),
                batch_size=bp.get('batch_size', 1),
                excludes_all_pity=bp.get('excludes_all_pity', False),
                max_draws=_normalize_max_draws(bp.get('max_draws')),
                exchange_card_id=bp.get('exchange_card_id'),
                epitomizable_cards=_parse_epitomizable_cards(bp, rewards, banner_id),
                rewards=rewards,
            ))

        for lc in b.get('lifecycle', []):
            banner_entry.lifecycle.append(LifecycleRuleEntry(
                condition=lc['condition'],
                pool=lc.get('pool'),
                at=_lifecycle_at(lc),
                match=lc.get('match', 'card_id'),
                action=lc.get('action', 'switch_to'),
                target=lc.get('target'),
            ))

        store.banner.banners.append(banner_entry)

    # P61（2026-08-04 用户决策）：永久 Banner（available_until=None）解析归一为有限池，
    # 运行时不再出现 None（消除 streaming/pool_end_times/worst_impact_panel 的 None 守卫族）。
    _normalize_permanent_banners(store.banner.banners)


def _normalize_permanent_banners(banners) -> None:
    """永久 Banner（available_until=None）解析归一为有限池（2026-08-04 用户决策）。

    把 available_until=None 的 Banner 归一为「最后一个有结束时间的 Banner 的
    available_until」——运行时按有限池处理，无 None、无需额外守卫。
    全永久组合（无任何有结束时间的 Banner）无法确定模拟期参照 → 拒绝加载。
    空配置（无 banner）跳过——由 load_toml 的空 banner 旧格式警告处理。
    """
    if not banners:
        return
    finite_ends = [b.available_until for b in banners if b.available_until is not None]
    if not finite_ends:
        raise ConfigError(
            "配置中所有 Banner 均为永久（无结束时间 end_day），至少需要一个有 "
            "available_until 的 Banner 作为模拟期参照。")
    last_end = max(finite_ends)
    for b in banners:
        if b.available_until is None:
            b.available_until = last_end


def _normalize_max_draws(value) -> Optional[int]:
    """TOML/UI 层「0=无限制」归一化为运行时 None 哨兵（ISSUE-331）。

    max_draws=0 直接落引擎则 _total_draws >= 0 恒 True、首抽即自动 exhaust，与语义相反。
    """
    if value is None:
        return None
    v = int(value)
    return None if v <= 0 else v


def _days_to_sec(value) -> Optional[float]:
    """天 → 秒（ISSUE-001）；None（永久 Banner/无窗口）透传 None。"""
    if value is None:
        return None
    return float(value) * DAY


def _lifecycle_at(lc: dict) -> float:
    """lifecycle 阈值解析：time_window 条件以「模拟内相对天数」书写 → 秒（*DAY）。

    P61（ISSUE-009）：抽数条件（pool_draws / banner_draws）的 at 必须为整数——
    浮点阈值会在 int() 截断处产生 1 抽偏差（at=10.5 实际 11 抽才满足、
    pending_transitions 却 int() 截断显示 10），配置错误显式报错而非静默漂移。
    """
    at = lc.get('at', 0.0)
    if lc.get('condition') == 'time_window':
        return float(at) * DAY
    if isinstance(at, float) and not at.is_integer():
        raise ValueError(
            f"lifecycle {lc.get('condition', '')} 的阈值必须为整数抽数，实际 {at}")
    return float(at)


def _parse_pool_rewards(bp: dict) -> List[dict]:
    """[[banner.pool.reward]] → List[dict]（card_id/probability/rarity/featured/resources_gained）。

    exchange_card_id 快捷方式 → 100% 单卡分布。
    """
    if bp.get('exchange_card_id'):
        return [{
            'card_id': bp['exchange_card_id'],
            'probability': 100.0,
            'rarity': 'ssr',
            'featured': True,
        }]
    rewards = []
    for r in bp.get('reward', []):
        entry = {
            'card_id': r['card_id'],
            'probability': r['probability'],
            'rarity': r.get('rarity', 'r'),
            'featured': r.get('featured', False),
        }
        if r.get('resources_gained'):
            entry['resources_gained'] = dict(r['resources_gained'])
        rewards.append(entry)
    return rewards


def _parse_epitomizable_cards(bp: dict, rewards: List[dict], banner_id: str) -> List[str]:
    """epitomizable_cards 解析 + 校验（card_id 在 rewards 中，P56）。"""
    raw = bp.get('epitomizable_cards', [])
    if not raw:
        return []
    reward_ids = {r['card_id'] for r in rewards}
    for cid in raw:
        if cid not in reward_ids:
            raise ConfigError(
                f"池子 '{banner_id}.{bp['id']}' 的 epitomizable_cards 中包含 "
                f"未在 distribution 中出现的卡牌 '{cid}'——请检查卡牌 ID 拼写或将该卡加入池子分布"
            )
    return list(raw)


def _parse_overflow_bands_array(raw_bands: list) -> Optional[List[OverflowBand]]:
    """解析 [[card.overflow_bands]] 数组 → List[OverflowBand]。

    TOML 格式：
      [[card.overflow_bands]]
      range = [1, 1]
      resources = { yellow_cert = 1 }

    range[1] 可以是整数或字符串 "inf"（→ None）。
    返回 None 若数组为空或全部区间无效。
    """
    bands: List[OverflowBand] = []
    for entry in raw_bands:
        rng = entry.get('range', [])
        if not rng or len(rng) < 2:
            continue
        min_val = int(rng[0])
        max_raw = rng[1]
        if isinstance(max_raw, str) and max_raw.strip().lower() == 'inf':
            max_val = None
        else:
            max_val = int(max_raw)
        resources = dict(entry.get('resources', {}))
        bands.append(OverflowBand(min=min_val, max=max_val, resources=resources))
    return bands if bands else None


def _build_card_overflow_map(store: ConfigStore) -> None:
    """构建 card_overflow_map——确定每张卡的最终分段表。

    优先级：卡片显式配置 > 稀有度默认。
    稀有度默认键名已统一为 .lower()——查找时同样 .lower() 归一化。
    """
    store.card_overflow_map.clear()
    rarity_defaults = store.rarity_defaults  # 键名已 .lower()

    for card_def in store.card_defs:
        if card_def.overflow_bands:
            store.card_overflow_map[card_def.card_id] = list(card_def.overflow_bands)
        else:
            rarity_key = card_def.rarity.lower()
            rd = rarity_defaults.get(rarity_key, {})
            default_bands = rd.get('overflow_bands', [])
            if default_bands:
                store.card_overflow_map[card_def.card_id] = list(default_bands)


def _backfill_card_pools(store: ConfigStore) -> None:
    """从池子分布逆向推导每张卡属于哪些池子，回填 card_defs[i].pools。

    旧 schedule.txt → _load_schedule 的等价逻辑：
    pool.distribution 中每出现一张卡，就把该 pool_id 加入对应的
    card_defs 条目。distribution 已在 _build_banners 中展开为具体
    卡牌 ID（含 exchange_card_id 快捷方式展开），因此无需再做展开。
    """
    card_index = {cd.card_id: i for i, cd in enumerate(store.card_defs)}
    for pool in store.pools:
        for dist_entry in pool.distribution:
            cid = dist_entry.card_id
            if cid in card_index and cid != '_no_card':
                idx = card_index[cid]
                if pool.pool_id not in store.card_defs[idx].pools:
                    store.card_defs[idx].pools.append(pool.pool_id)
