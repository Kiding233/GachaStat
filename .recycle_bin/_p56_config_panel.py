"""P56 阶段十二——config_panel.py GUI 序列化层更新。"""
import os

f = 'gacha_simulator/gui/config_panel.py'
c = open(f, encoding='utf-8').read()
changes = 0

# ==== 十二-a: _PITY_TYPES 扩展 ====
old_types = """    _PITY_TYPES = [
        ('soft_interval', '区间软保底'),
        ('soft_additive', '累加软保底'),
        ('soft_step', '分段软保底'),
        ('hard', '硬保底'),
    ]"""
new_types = """    _PITY_TYPES = [
        ('soft_interval', '区间软保底'),
        ('soft_additive', '累加软保底'),
        ('soft_step', '分段软保底'),
        ('hard', '硬保底'),
        # P56 新增
        ('rotating', '轮换保底'),
        ('rotating_soft', '轮换+软保底'),
        ('rotating_cr', '轮换+捕获明光'),
        ('rotating_cr_soft', '轮换+CR+软保底'),
        ('targeted', '定轨保底'),
        ('targeted_soft', '定轨+软保底'),
    ]"""
if old_types in c:
    c = c.replace(old_types, new_types)
    changes += 1
    print('十二-a: _PITY_TYPES 扩展 OK')
else:
    print('十二-a: _PITY_TYPES 已就绪或模式不匹配')

# ==== 十二-b-1: get_config pity dict —— 追加 P56 字段 ====
old_gc = """                    'reset': pd.get('reset', ''),
                    'pools': pd.get('pools', '*'),
                    'lifecycle': {"""
if old_gc in c:
    new_gc = """                    'reset': pd.get('reset', ''),
                    'pools': pd.get('pools', '*'),
                    'guaranteed_init': pd.get('guaranteed_init', False),
                    'fate_points_init': pd.get('fate_points_init', 0),
                    'soft_deltas': pd.get('soft_deltas'),
                    'cr_counter_threshold': pd.get('cr_counter_threshold'),
                    'cr_base_rate': pd.get('cr_base_rate'),
                    'cr_state_probs': pd.get('cr_state_probs'),
                    'fate_threshold': pd.get('fate_threshold'),
                    'switch_allowed': pd.get('switch_allowed'),
                    'switch_resets_progress': pd.get('switch_resets_progress'),
                    'lifecycle': {"""
    c = c.replace(old_gc, new_gc)
    changes += 1
    print('十二-b-1: get_config pity 扩展 OK')

# ==== 十二-b-2: set_config PityDef 构造 —— 追加 P56 字段 ====
old_sc_pd = """                soft_start=pd.get('start'),
                soft_end=pd.get('end'),
                soft_increment=pd.get('increment'),
                reset=pd.get('reset', ''),"""
if old_sc_pd in c:
    new_sc_pd = """                soft_start=pd.get('start'),
                soft_end=pd.get('end'),
                soft_increment=pd.get('increment'),
                soft_deltas=pd.get('soft_deltas'),
                cr_counter_threshold=pd.get('cr_counter_threshold'),
                cr_base_rate=pd.get('cr_base_rate'),
                cr_state_probs=pd.get('cr_state_probs'),
                fate_threshold=pd.get('fate_threshold'),
                switch_allowed=pd.get('switch_allowed'),
                switch_resets_progress=pd.get('switch_resets_progress'),
                reset=pd.get('reset', ''),"""
    c = c.replace(old_sc_pd, new_sc_pd)
    changes += 1
    print('十二-b-2: set_config PityDef 扩展 OK')

# ==== 十二-b-3: set_config _pity_defs UI dict —— 追加 P56 字段 ====
old_sc_ui = """                'reset': pd.get('reset', ''),
                'pools': pd.get('pools', '*'),
                'max_triggers': (pd.get('lifecycle') or {}).get('max_triggers', 0),"""
if old_sc_ui in c:
    new_sc_ui = """                'reset': pd.get('reset', ''),
                'pools': pd.get('pools', '*'),
                'guaranteed_init': pd.get('guaranteed_init', False),
                'fate_points_init': pd.get('fate_points_init', 0),
                'soft_deltas': pd.get('soft_deltas'),
                'cr_counter_threshold': pd.get('cr_counter_threshold'),
                'cr_base_rate': pd.get('cr_base_rate'),
                'cr_state_probs': pd.get('cr_state_probs'),
                'fate_threshold': pd.get('fate_threshold'),
                'switch_allowed': pd.get('switch_allowed'),
                'switch_resets_progress': pd.get('switch_resets_progress'),
                'max_triggers': (pd.get('lifecycle') or {}).get('max_triggers', 0),"""
    c = c.replace(old_sc_ui, new_sc_ui)
    changes += 1
    print('十二-b-3: set_config _pity_defs 扩展 OK')

# ==== 十二-b-4: apply_to_store PityDef 构造 —— 追加 P56 字段 ====
old_ats = """                soft_deltas=pd.get('deltas') if pd.get('btype') == 'soft_step' else None,
                reset=pd.get('reset', ''),"""
if old_ats in c:
    new_ats = """                soft_deltas=pd.get('deltas') if pd.get('btype') == 'soft_step' else None,
                cr_counter_threshold=pd.get('cr_counter_threshold'),
                cr_base_rate=pd.get('cr_base_rate'),
                cr_state_probs=pd.get('cr_state_probs'),
                fate_threshold=pd.get('fate_threshold'),
                switch_allowed=pd.get('switch_allowed'),
                switch_resets_progress=pd.get('switch_resets_progress'),
                reset=pd.get('reset', ''),"""
    c = c.replace(old_ats, new_ats)
    changes += 1
    print('十二-b-4: apply_to_store PityDef 扩展 OK')

# ==== 十二-b-5: refresh_from_store _pity_defs —— 追加 P56 字段 ====
old_rfs = """                'reset': getattr(p, 'reset', ''),
                'pools': pools_val,
                'max_triggers': getattr(p, 'max_triggers', 0),"""
if old_rfs in c:
    new_rfs = """                'reset': getattr(p, 'reset', ''),
                'pools': pools_val,
                'guaranteed_init': getattr(p, 'guaranteed_init', False),
                'fate_points_init': getattr(p, 'fate_points_init', 0),
                'soft_deltas': getattr(p, 'soft_deltas', None),
                'cr_counter_threshold': getattr(p, 'cr_counter_threshold', None),
                'cr_base_rate': getattr(p, 'cr_base_rate', None),
                'cr_state_probs': getattr(p, 'cr_state_probs', None),
                'fate_threshold': getattr(p, 'fate_threshold', None),
                'switch_allowed': getattr(p, 'switch_allowed', None),
                'switch_resets_progress': getattr(p, 'switch_resets_progress', None),
                'max_triggers': getattr(p, 'max_triggers', 0),"""
    c = c.replace(old_rfs, new_rfs)
    changes += 1
    print('十二-b-5: refresh_from_store 扩展 OK')

# ==== 十二-c-1: get_config pools 输出 —— 追加 epitomizable_cards ====
old_gc_pools = """                'batch_size': getattr(p, 'batch_size', 1),
                'distribution': [{'card_id': d.card_id, 'probability': d.probability,"""
if old_gc_pools in c and 'epitomizable_cards' not in c.split("'batch_size': getattr(p, 'batch_size', 1),")[1][:80]:
    new_gc_pools = """                'batch_size': getattr(p, 'batch_size', 1),
                'epitomizable_cards': getattr(p, 'epitomizable_cards', []),
                'distribution': [{'card_id': d.card_id, 'probability': d.probability,"""
    c = c.replace(old_gc_pools, new_gc_pools)
    changes += 1
    print('十二-c-1: get_config pools epitomizable_cards OK')

# ==== 十二-c-2: set_config PoolEntry —— 追加 epitomizable_cards ====
old_sc_pe = """                distribution_template="",
                bindings=bindings,
                distribution=distribution,
                batch_size=p.get('batch_size', 1),
            ))"""
if old_sc_pe in c and 'epitomizable_cards' not in c.split('distribution_template=""')[1].split('))')[0]:
    new_sc_pe = """                distribution_template="",
                bindings=bindings,
                distribution=distribution,
                batch_size=p.get('batch_size', 1),
                epitomizable_cards=p.get('epitomizable_cards', []),
            ))"""
    c = c.replace(old_sc_pe, new_sc_pe)
    changes += 1
    print('十二-c-2: set_config PoolEntry epitomizable_cards OK')

# ==== 十二-c-3: apply_to_store PoolEntry —— 追加 epitomizable_cards ====
old_ats_pe = """                distribution=distribution,
                batch_size=batch_size,
            ))"""
if old_ats_pe in c and 'epitomizable_cards' not in c.split('batch_size=batch_size')[1].split('))')[0]:
    new_ats_pe = """                distribution=distribution,
                batch_size=batch_size,
                epitomizable_cards=pool.get('epitomizable_cards', []),
            ))"""
    c = c.replace(old_ats_pe, new_ats_pe)
    changes += 1
    print('十二-c-3: apply_to_store PoolEntry epitomizable_cards OK')

# Write back
open(f, 'w', encoding='utf-8').write(c)
print(f'\nconfig_panel.py: {changes} 处改动已应用')
