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
    PityConfig,
    PityDef,
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
    _build_gain_rules(data, store)
    _build_day_overrides(data, store)
    _build_pity(data, store)        # 依赖 rarity_rank 完成 scope 校验
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

    # pity（P55 扁平化格式）
    if store.pity.enabled and store.pity.pities:
        data['pity'] = [_pitydef_to_toml(p) for p in store.pity.pities]

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
        banner_entry = BannerEntry(
            id=banner_id,
            name=b.get('name', banner_id),
            enabled=b.get('enabled', True),
            max_draws=_normalize_max_draws(b.get('max_draws')),
            available_from=_days_to_sec(b.get('start_day')),
            available_until=_days_to_sec(b.get('end_day')),
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
