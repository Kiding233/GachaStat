"""TOML 配置文件读写——替代旧 config_io.py + pool_config.py 的 txt 解析器。

S2a: load_toml + 基础 _build_* helper + _expand_binding 迁移
S2b-1: save_toml 骨架 + _build_weights / _build_distribution_templates / _build_pools
S2b-2: _save_templates_and_pools + _distribution_matches_template
S2c: _expand_template_with_bindings
"""

import math
from typing import Dict, List, Optional, Tuple

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from .config_store import (
    CardDefEntry,
    CardWeightEntry,
    ConfigError,
    ConfigStore,
    DayOverride,
    GainRule,
    PityConfig,
    PityDef,
    PoolDistEntry,
    PoolEntry,
    TargetCardEntry,
)

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

    # 分布模板 → 池子（需先构建模板索引，再展开池子）
    templates = _build_distribution_templates(data)
    store._distribution_templates = templates
    _build_pools(data, store, templates)

    # 回填 card_defs.pools：从池子分布逆向推导每张卡属于哪些池子
    _backfill_card_pools(store)

    return store


def save_toml(store: ConfigStore, path: str) -> None:
    """将 ConfigStore 保存为 TOML 文件。

    分布模板匹配策略：对于每个池子，若 distribution_template 非空且
    当前分布与模板展开结果一致，则写出模板引用；否则写出内联 distribution。
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

    # cards
    data['cards'] = [
        {'id': c.card_id, 'name': c.name, 'rarity': c.rarity}
        for c in store.card_defs
    ]

    # templates + pools
    _save_templates_and_pools(store, data)

    # pity（P55 扁平化格式）
    if store.pity.enabled and store.pity.pities:
        data['pity'] = [_pitydef_to_toml(p) for p in store.pity.pities]

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
# 分布模板保存辅助
# ══════════════════════════════════════════════════════════════════


def _save_templates_and_pools(store: ConfigStore, data: dict) -> None:
    """将池子分布反向写入 TOML 结构。

    基准模板从 store._distribution_templates 读取（load_toml 时缓存）。
    """
    original_templates = store._distribution_templates
    data['pools'] = []
    used_templates: set = set()

    for pool in store.pools:
        pool_dict: dict = {
            'id': pool.pool_id, 'name': pool.name,
            'pool_type': pool.pool_type or '角色',
            'start_day': pool.start_day, 'end_day': pool.end_day,
            'cost': pool.cost,
            'batch_size': pool.batch_size,
            'bindings': {k: v for k, v in pool.bindings.items() if k != 'type'},
            'target_cards': [cid for cid, _ in pool.target_specs],
        }

        # rerun_of / exchange_card_id 可选
        if pool.rerun_of:
            pool_dict['rerun_of'] = pool.rerun_of
        if pool.exchange_card_id:
            pool_dict['exchange_card_id'] = pool.exchange_card_id

        # 判定：模板引用 vs 内联分布
        template_name = pool.distribution_template
        if template_name and _distribution_matches_template(
            pool.distribution, template_name, pool.bindings, original_templates
        ):
            pool_dict['distribution_template'] = template_name
            used_templates.add(template_name)
        else:
            pool_dict['distribution'] = [
                {
                    'card_id': d.card_id,
                    'probability': d.probability,
                    'rarity': d.rarity,
                    'featured': d.featured,
                }
                for d in pool.distribution
            ]

        data['pools'].append(pool_dict)

    # 写被引用的模板
    if used_templates:
        data['distribution_templates'] = [
            t for t in original_templates if t['name'] in used_templates
        ]


def _distribution_matches_template(
    distribution: List[PoolDistEntry],
    template_name: str,
    bindings: Dict[str, str],
    templates: List[dict],
) -> bool:
    """比较当前分布与模板展开结果是否一致（浮点容差 rel_tol=1e-6）。"""
    template = next((t for t in templates if t['name'] == template_name), None)
    if template is None:
        return False

    expanded = _expand_template_with_bindings(template['cards'], bindings)

    if len(distribution) != len(expanded):
        return False

    dist_sorted = sorted(distribution, key=lambda d: d.card_id)
    exp_sorted = sorted(expanded, key=lambda d: d.card_id)

    for d, e in zip(dist_sorted, exp_sorted):
        if d.card_id != e.card_id:
            return False
        if d.rarity != e.rarity:
            return False
        if d.featured != e.featured:
            return False
        if not math.isclose(d.probability, e.probability, rel_tol=1e-6):
            return False

    return True


# ══════════════════════════════════════════════════════════════════
# 绑定展开
# ══════════════════════════════════════════════════════════════════


def _expand_binding(value: str, prob: float) -> List[Tuple[str, float]]:
    """展开逗号分隔的绑定值。

    从 pool_config.py 原样迁移至 config_toml.py。
    支持等权展开（"a,b,c" → 均分概率）和冒号加权展开（"a:2.0,b:1.0" → 按权重比例分配）。
    """
    if ',' not in value:
        return [(value, prob)]
    parts = [p.strip() for p in value.split(',')]
    weighted = []
    unweighted = []
    for part in parts:
        if ':' in part:
            cid, w = part.rsplit(':', 1)
            try:
                weight = float(w)
                weighted.append((cid.strip(), weight))
            except ValueError:
                weighted.append((part.strip(), 1.0))
        else:
            unweighted.append(part.strip())
    if not weighted and not unweighted:
        return [(value, prob)]
    total_weight = sum(w for _, w in weighted) + len(unweighted)
    results = []
    for cid, w in weighted:
        results.append((cid, prob * (w / total_weight)))
    for cid in unweighted:
        results.append((cid, prob * (1.0 / total_weight)))
    return results


def _expand_template_with_bindings(
    template_cards: List[dict],
    bindings: Dict[str, str],
) -> List[PoolDistEntry]:
    """将模板中的绑定键展开为具体 PoolDistEntry 列表。

    card_id 为绑定键（ssr/sr/r/ssr_alt/ssr_alt1/ssr_alt2 等）时，
    调用 _expand_binding() 展开；否则按原样作为单卡 ID。
    featured 仅当显式为 True 时标记。
    """
    BINDING_KEYS = {'ssr', 'sr', 'r', 'ssr_alt', 'ssr_alt1', 'ssr_alt2',
                    'featured', 'offrate'}
    result: List[PoolDistEntry] = []

    for tc in template_cards:
        card_id = tc['card_id']
        prob = tc['probability']
        rarity = tc.get('rarity', 'r')
        featured = tc.get('featured', False)

        if card_id in BINDING_KEYS:
            # 绑定键 → 从 bindings 查找值并展开
            binding_value = bindings.get(card_id, card_id)
            expanded = _expand_binding(binding_value, prob)
            for cid, card_prob in expanded:
                result.append(PoolDistEntry(
                    card_id=cid,
                    probability=card_prob,
                    rarity=rarity,
                    featured=(featured and card_id == 'ssr'),
                ))
        else:
            # 非绑定键 → 直接作为单卡 ID
            result.append(PoolDistEntry(
                card_id=card_id,
                probability=prob,
                rarity=rarity,
                featured=featured,
            ))

    return result


# ══════════════════════════════════════════════════════════════════
# 各段 _build_* helper
# ══════════════════════════════════════════════════════════════════


def _build_cards(data: dict, store: ConfigStore) -> None:
    """[[cards]] → store.card_defs"""
    for c in data.get('cards', []):
        store.card_defs.append(CardDefEntry(
            card_id=c['id'],
            name=c.get('name', c['id']),
            rarity=c.get('rarity', 'r'),
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
        max_triggers = lifecycle_raw.get('max_triggers', 0)
        deactivate_on_early_hit = lifecycle_raw.get('deactivate_on_early_hit', False)
        depends_on = lifecycle_raw.get('depends_on')

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
            max_triggers=max_triggers,
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
    if p.pools and p.pools != ('*',):
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
    if p.max_triggers:
        lifecycle['max_triggers'] = p.max_triggers
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


def _build_targets(data: dict, store: ConfigStore) -> None:
    """[[targets]] → store.target_cards"""
    for t in data.get('targets', []):
        store.target_cards.append(TargetCardEntry(
            card_id=t['card_id'],
            quantity=t.get('quantity', 1),
            pool_ids=list(t.get('pool_ids', [])),
        ))


def _build_weights(data: dict, store: ConfigStore) -> None:
    """[[weights]] 数组表 → store.card_weights"""
    for w in data.get('weights', []):
        cid = w['card_id']
        store.card_weights[cid] = CardWeightEntry(
            desire_weight=float(w.get('desire', 1.0)),
            miss_cost_weight=float(w.get('miss_cost', 1.0)),
            card_value=float(w.get('card_value', 1.0)),
        )


def _build_distribution_templates(data: dict) -> List[dict]:
    """[[distribution_templates]] → List[dict]（中间产物，尚未展开）。

    每个 dict 含 'name' 键和 'cards' 键，
    格式：[{"name": "xxx", "cards": [...]}, ...]。
    """
    result = []
    for t in data.get('distribution_templates', []):
        result.append({
            'name': t['name'],
            'cards': t.get('cards', []),
        })
    return result


def _build_pools(data: dict, store: ConfigStore, templates: List[dict]) -> None:
    """[[pools]] → store.pools，含绑定展开 + 分布模板引用解析。"""
    # 构建模板索引：name → cards
    template_index = {t['name']: t['cards'] for t in templates}

    for p in data.get('pools', []):
        pool_type = p.get('pool_type') or '角色'

        # 解析 distribution
        distribution: List[PoolDistEntry] = []
        template_name = p.get('distribution_template', '')

        if p.get('exchange_card_id'):
            # 兑换池——100% 出指定卡
            distribution = [
                PoolDistEntry(
                    card_id=p['exchange_card_id'],
                    probability=100.0,
                    rarity='ssr',
                    featured=True,
                )
            ]
        elif p.get('rerun_of'):
            # 复刻池——稍后在第二步从同名池子复制
            pass  # 第二步处理
        elif template_name and template_name in template_index:
            # 模板引用 → 展开
            bindings = dict(p.get('bindings', {}))
            distribution = _expand_template_with_bindings(
                template_index[template_name], bindings
            )
        elif 'distribution' in p:
            # 内联分布
            for d in p['distribution']:
                distribution.append(PoolDistEntry(
                    card_id=d['card_id'],
                    probability=d['probability'],
                    rarity=d.get('rarity', 'r'),
                    featured=d.get('featured', False),
                ))

        # bindings + target_specs
        bindings = dict(p.get('bindings', {}))
        # pool_type 双写——同时设置 PoolEntry.pool_type 和 bindings['type']
        bindings['type'] = pool_type

        target_specs = [
            (cid, 1) for cid in p.get('target_cards', [])
        ]

        pool_entry = PoolEntry(
            pool_id=p['id'],
            name=p.get('name', p['id']),
            pool_type=pool_type,
            start_day=p.get('start_day', 0),
            end_day=p.get('end_day', 21),
            cost=p.get('cost', 'draw_resource:160'),
            batch_size=p.get('batch_size', 1),
            distribution_template=template_name,
            bindings=bindings,
            target_specs=target_specs,
            rerun_of=p.get('rerun_of'),
            exchange_card_id=p.get('exchange_card_id'),
            distribution=distribution,
        )
        store.pools.append(pool_entry)

    # 第二步：处理 rerun_of（从同名池子复制 distribution）
    pool_index = {p.pool_id: p for p in store.pools}
    for pool in store.pools:
        if pool.rerun_of and not pool.distribution:
            source = pool_index.get(pool.rerun_of)
            if source:
                pool.distribution = list(source.distribution)

    # P60：统一填充 featured_card_ids——覆盖所有 pool（含复刻池，其 distribution 在第二步才赋值）
    for pool in store.pools:
        pool.featured_card_ids = [d.card_id for d in pool.distribution if d.featured]


def _backfill_card_pools(store: ConfigStore) -> None:
    """从池子分布逆向推导每张卡属于哪些池子，回填 card_defs[i].pools。

    旧 schedule.txt → _load_schedule 的等价逻辑：
    pool.distribution 中每出现一张卡，就把该 pool_id 加入对应的
    card_defs 条目。distribution 已在 _build_pools 中展开为具体
    卡牌 ID（非绑定键），因此无需再做展开。
    """
    card_index = {cd.card_id: i for i, cd in enumerate(store.card_defs)}
    for pool in store.pools:
        for dist_entry in pool.distribution:
            cid = dist_entry.card_id
            if cid in card_index and cid != '_no_card':
                idx = card_index[cid]
                if pool.pool_id not in store.card_defs[idx].pools:
                    store.card_defs[idx].pools.append(pool.pool_id)
