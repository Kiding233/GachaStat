"""一次性应用所有 P56 非-pity.py 文件的改动。"""
import os

# ============================================================
# 1. gacha_service.py
# ============================================================
f = 'gacha_simulator/service/gacha_service.py'
c = open(f, encoding='utf-8').read()
if 'NonDrawAction' not in c:
    c = c.replace(
        'GachaState, Pool, DrawAction, WaitAction,',
        'GachaState, Pool, DrawAction, WaitAction, NonDrawAction,')
    c = c.replace(
        'from ..core.pity import PityEngine, PityState\nfrom ..core.pool import NO_CARD_ID',
        'from ..core.action import NON_DRAW_ACTION_REGISTRY, InvalidActionError\nfrom ..core.pity import PityEngine, PityState\nfrom ..core.pool import NO_CARD_ID')
    c = c.replace(
        '            elif _isinstance(action, _WaitAction):',
        '            elif _isinstance(action, NonDrawAction):\n                self._apply_non_draw(action, _pools, _pity_engine, pity_state)\n\n            elif _isinstance(action, _WaitAction):')

    apply_method = '''
    def _apply_non_draw(self, action, pools, pity_engine, pity_state):
        """P56：执行 NonDrawAction——定轨切换/取消。"""
        from ..core.pity import TargetedBehavior
        if action.action_id not in NON_DRAW_ACTION_REGISTRY:
            raise InvalidActionError(f"未注册的 NonDrawAction action_id: '{action.action_id}'")
        pool_id = action.params.get('pool_id')
        if not pool_id: raise InvalidActionError(f"NonDrawAction 缺少 'pool_id'")
        pool = pools.get(pool_id)
        if pool is None: raise InvalidActionError(f"NonDrawAction 引用了不存在的池子 '{pool_id}'")
        targeted_name = None
        for pname, bh in pity_engine.get_behaviors_for_pool(pool_id):
            if isinstance(bh, TargetedBehavior): targeted_name = pname; break
        if targeted_name is None:
            raise InvalidActionError(f"池子 '{pool_id}' 未配置 targeted 保底")
        if action.action_id == 'switch_epitomized_target':
            card_id = action.params.get('card_id')
            if not card_id: raise InvalidActionError("switch_epitomized_target 缺少 'card_id'")
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

    '''
    c = c.replace(
        '    def _aggregate_probs_by_rarity(self, pool_id: str, pool, pity_spec)',
        apply_method + '    def _aggregate_probs_by_rarity(self, pool_id: str, pool, pity_spec)')

    open(f, 'w', encoding='utf-8').write(c)
    print('OK: gacha_service.py')
else:
    print('SKIP: gacha_service.py')

# ============================================================
# 2. batch_simulator.py
# ============================================================
f = 'gacha_simulator/service/batch_simulator.py'
c = open(f, encoding='utf-8').read()

# PityDef construction - add P56 fields
if 'soft_deltas=p.get' not in c:
    c = c.replace(
        "                soft_increment=p.get('increment'),\n                pools=tuple(",
        "                soft_increment=p.get('increment'),\n                soft_deltas=p.get('soft_deltas'),\n                cr_counter_threshold=p.get('cr_counter_threshold'),\n                cr_base_rate=p.get('cr_base_rate'),\n                cr_state_probs=p.get('cr_state_probs'),\n                fate_threshold=p.get('fate_threshold'),\n                switch_allowed=p.get('switch_allowed'),\n                switch_resets_progress=p.get('switch_resets_progress'),\n                pools=tuple(")
    print('OK: batch_simulator PityDef')

# compute_scope_mappings unpacking (5-tuple)
if ', card_to_slot = compute_scope_mappings(pool)' not in c:
    c = c.replace(
        'scope_cards, featured_cards, scope_slots, featured_slots = compute_scope_mappings(pool)',
        'scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot = compute_scope_mappings(pool)')
    c = c.replace(
        '                featured_slots=featured_slots,\n            )\n\n        return PityEngine',
        '                featured_slots=featured_slots,\n                card_to_slot=card_to_slot,\n            )\n\n        return PityEngine')
    print('OK: batch_simulator compute_scope_mappings')

# pentry dict
if "'soft_deltas': getattr" not in c:
    c = c.replace(
        "                    'depends_on': getattr(pd, 'depends_on', None),\n                }",
        "                    'depends_on': getattr(pd, 'depends_on', None),\n                    'start': getattr(pd, 'soft_start', None),\n                    'end': getattr(pd, 'soft_end', None),\n                    'increment': getattr(pd, 'soft_increment', None),\n                    'soft_deltas': getattr(pd, 'soft_deltas', None),\n                    'cr_counter_threshold': getattr(pd, 'cr_counter_threshold', None),\n                    'cr_base_rate': getattr(pd, 'cr_base_rate', None),\n                    'cr_state_probs': getattr(pd, 'cr_state_probs', None),\n                    'fate_threshold': getattr(pd, 'fate_threshold', None),\n                    'switch_allowed': getattr(pd, 'switch_allowed', None),\n                    'switch_resets_progress': getattr(pd, 'switch_resets_progress', None),\n                }")
    print('OK: batch_simulator pentry')

# Pool construction
if 'epitomizable_cards=getattr' not in c:
    c = c.replace(
        "                batch_size=getattr(pe, 'batch_size', 1),\n            )\n            pools.append(pool)",
        "                batch_size=getattr(pe, 'batch_size', 1),\n                epitomizable_cards=getattr(pe, 'epitomizable_cards', []),\n            )\n            pools.append(pool)")
    print('OK: batch_simulator Pool')

open(f, 'w', encoding='utf-8').write(c)

# ============================================================
# 3. worst_impact.py
# ============================================================
f = 'gacha_simulator/core/worst_impact.py'
c = open(f, encoding='utf-8').read()

# compute_scope_mappings unpack
if ', card_to_slot = compute_scope_mappings(ref_pool)' not in c:
    c = c.replace(
        'scope_cards, featured_cards, scope_slots, featured_slots = compute_scope_mappings(ref_pool)',
        'scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot = compute_scope_mappings(ref_pool)')
    print('OK: worst_impact unpack')

# fallback card_to_slot
if 'card_to_slot = {}' not in c:
    old_fb = (
        "            else:\n"
        "                scope_cards = {'ssr': tuple(self._ssr_ids)} if self._ssr_ids else {}\n"
        "                featured_cards = {'ssr': tuple(self._featured_ids)} if self._featured_ids else {}\n"
        "                if self._ssr_ids and self._featured_ids:\n"
        "                    scope_slots = {'ssr': ('ssr', 'ssr_featured')}\n"
        "                    featured_slots = {'ssr': ('ssr_featured',)}\n"
        "                else:\n"
        "                    scope_slots = {'ssr': ('ssr',)} if self._ssr_ids else {}\n"
        "                    featured_slots = {'ssr': ('ssr',)} if self._featured_ids else {}"
    )
    new_fb = (
        "            else:\n"
        "                scope_cards = {'ssr': tuple(self._ssr_ids)} if self._ssr_ids else {}\n"
        "                featured_cards = {'ssr': tuple(self._featured_ids)} if self._featured_ids else {}\n"
        "                card_to_slot = {}\n"
        "                if self._ssr_ids and self._featured_ids:\n"
        "                    scope_slots = {'ssr': ('ssr', 'ssr_featured')}\n"
        "                    featured_slots = {'ssr': ('ssr_featured',)}\n"
        "                    for cid in self._featured_ids: card_to_slot[cid] = 'ssr_featured'\n"
        "                    for cid in (self._ssr_ids - self._featured_ids): card_to_slot[cid] = 'ssr'\n"
        "                else:\n"
        "                    scope_slots = {'ssr': ('ssr',)} if self._ssr_ids else {}\n"
        "                    featured_slots = {'ssr': ('ssr',)} if self._featured_ids else {}\n"
        "                    for cid in self._ssr_ids: card_to_slot[cid] = 'ssr'"
    )
    c = c.replace(old_fb, new_fb)
    print('OK: worst_impact fallback')

# PoolPitySpec
if ', card_to_slot=card_to_slot' not in c:
    c = c.replace(
        '                featured_slots=featured_slots,\n                )',
        '                featured_slots=featured_slots,\n                card_to_slot=card_to_slot,\n                )')
    print('OK: worst_impact PoolPitySpec')

open(f, 'w', encoding='utf-8').write(c)

# ============================================================
# 4. config_toml.py
# ============================================================
f = 'gacha_simulator/core/config_toml.py'
c = open(f, encoding='utf-8').read()

if 'epitomizable_raw = p.get' not in c:
    old_pe = (
        "        pool_entry = PoolEntry(\n"
        "            pool_id=p['id'],\n"
        "            name=p.get('name', p['id']),\n"
        "            pool_type=pool_type,\n"
        "            start_day=p.get('start_day', 0),\n"
        "            end_day=p.get('end_day', 21),\n"
        "            cost=p.get('cost', 'draw_resource:160'),\n"
        "            batch_size=p.get('batch_size', 1),\n"
        "            distribution_template=template_name,\n"
        "            bindings=bindings,\n"
        "            target_specs=target_specs,\n"
        "            rerun_of=p.get('rerun_of'),\n"
        "            exchange_card_id=p.get('exchange_card_id'),\n"
        "            distribution=distribution,\n"
        "        )"
    )
    new_pe = (
        "        # P56：解析 epitomizable_cards——校验 card_id 在 distribution 中存在\n"
        "        epitomizable_raw = p.get('epitomizable_cards', [])\n"
        "        epitomizable_cards = []\n"
        "        if epitomizable_raw:\n"
        "            dist_card_ids = {d.card_id for d in distribution}\n"
        "            for cid in epitomizable_raw:\n"
        "                if cid not in dist_card_ids:\n"
        "                    raise ConfigError(\n"
        "                        f\"池子 '{p['id']}' 的 epitomizable_cards 中包含 \"\n"
        "                        f\"未在 distribution 中出现的卡牌 '{cid}'——\"\n"
        "                        f\"请检查卡牌 ID 拼写或将该卡加入池子分布\"\n"
        "                    )\n"
        "                epitomizable_cards.append(cid)\n"
        "\n"
        "        pool_entry = PoolEntry(\n"
        "            pool_id=p['id'],\n"
        "            name=p.get('name', p['id']),\n"
        "            pool_type=pool_type,\n"
        "            start_day=p.get('start_day', 0),\n"
        "            end_day=p.get('end_day', 21),\n"
        "            cost=p.get('cost', 'draw_resource:160'),\n"
        "            batch_size=p.get('batch_size', 1),\n"
        "            distribution_template=template_name,\n"
        "            bindings=bindings,\n"
        "            target_specs=target_specs,\n"
        "            rerun_of=p.get('rerun_of'),\n"
        "            exchange_card_id=p.get('exchange_card_id'),\n"
        "            distribution=distribution,\n"
        "            epitomizable_cards=epitomizable_cards,\n"
        "        )"
    )
    if old_pe in c:
        c = c.replace(old_pe, new_pe)
        print('OK: config_toml.py')
    else:
        print('WARN: config_toml.py old PoolEntry pattern not found')
else:
    print('SKIP: config_toml.py')

open(f, 'w', encoding='utf-8').write(c)

print('\n=== All non-pity files updated ===')
