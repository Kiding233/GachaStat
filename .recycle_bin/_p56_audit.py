"""P56 全面对照审计——逐项检查44个计划交付物。"""
import ast, inspect

results = {}

# ===== A. pity.py =====
from gacha_simulator.core import pity as pmod
src = open(pmod.__file__, encoding='utf-8').read()

results['A1  import random'] = 'import random' in src[:200]

from gacha_simulator.core.pity import DrawInfo, PoolPitySpec, BEHAVIOR_REGISTRY
flds = DrawInfo.__dataclass_fields__
results['A2  DrawInfo.featured_cards'] = 'featured_cards' in flds
results['A3  DrawInfo.card_to_slot'] = 'card_to_slot' in flds
results['A4  PoolPitySpec.card_to_slot'] = 'card_to_slot' in PoolPitySpec.__dataclass_fields__

from gacha_simulator.core.pity import compute_scope_mappings
from gacha_simulator.core.pool import Pool, Reward
r1 = Reward(id='c1', name='C1', extra_info={'rarity':'SSR','featured':True})
p = Pool(id='p1', name='P1', cost=[{'r':1}], rewards=[(r1,1.0)])
m = compute_scope_mappings(p)
results['A5  compute_scope_mappings -> 5元组'] = len(m) == 5

classes = ['_redistribute_scope','SoftPityMixin','RotatingBehavior','RotatingSoftBehavior',
           'RotatingCRBehavior','RotatingCRSoftBehavior','TargetedBehavior','TargetedSoftBehavior']
for i, name in enumerate(classes):
    results[f'A{6+i}  {name}'] = hasattr(pmod, name)

for bt in ['rotating','rotating_soft','rotating_cr','rotating_cr_soft','targeted','targeted_soft']:
    results[f'A14 REGISTRY.{bt}'] = bt in BEHAVIOR_REGISTRY and BEHAVIOR_REGISTRY[bt]['class'] is not None

results['A15 _BTYPE_ORDER 10种'] = len(pmod._BTYPE_ORDER) == 10

cb_src = inspect.getsource(pmod.create_behavior)
results['A16 create_behavior._SOFT_SUFFIX_TYPES'] = '_SOFT_SUFFIX_TYPES' in cb_src
results['A17 create_behavior._P56_TYPES'] = '_P56_TYPES' in cb_src
results['A18 create_behavior.P56透传'] = 'cr_counter_threshold' in cb_src

bsi_src = inspect.getsource(pmod._build_pity_state_init)
results['A19 _build_pity_state_init.selected_card'] = 'selected_card' in bsi_src

eng_init = inspect.getsource(pmod.PityEngine.__init__)
results['A20 skip guard 已移除'] = 'continue  # P56 stub' not in eng_init

results['A21 _build_activation_graph'] = hasattr(pmod.PityEngine, '_build_activation_graph')

ad_src = inspect.getsource(pmod.PityEngine.after_draw)
results['A22 after_draw.did_fire传播'] = 'did_fire' in ad_src and '_activation_graph' in ad_src

results['A23 get_pity_def'] = hasattr(pmod.PityEngine, 'get_pity_def')
results['A24 get_behaviors_for_pool'] = hasattr(pmod.PityEngine, 'get_behaviors_for_pool')

# DrawInfo constructions
gp_src = inspect.getsource(pmod.PityEngine.get_probabilities)
bd_src = inspect.getsource(pmod.PityEngine.before_draw)
results['A25 get_probabilities含featured_cards'] = 'featured_cards=spec.featured_cards' in gp_src
results['A26 before_draw含card_to_slot'] = 'card_to_slot=spec.card_to_slot' in bd_src

# ===== B. action.py =====
from gacha_simulator.core import action as amod
results['B1  NonDrawAction'] = hasattr(amod, 'NonDrawAction')
results['B2  NON_DRAW_ACTION_REGISTRY'] = hasattr(amod, 'NON_DRAW_ACTION_REGISTRY')
results['B3  InvalidActionError'] = hasattr(amod, 'InvalidActionError')

# ===== C/D. config_store / pool =====
from gacha_simulator.core.config_store import PoolEntry
from gacha_simulator.core.pool import Pool
results['C1  PoolEntry.epitomizable_cards'] = 'epitomizable_cards' in PoolEntry.__dataclass_fields__
results['D1  Pool.epitomizable_cards'] = 'epitomizable_cards' in Pool.__dataclass_fields__

# ===== E. __init__.py =====
init_src = open('gacha_simulator/core/__init__.py', encoding='utf-8').read()
results['E1  import NonDrawAction'] = 'NonDrawAction' in init_src.split('from .action import')[1].split('\n')[0]
results['E2  import RotatingBehavior'] = 'RotatingBehavior' in init_src.split('from .pity import')[1].split('\n)')[0]
results['E3  __all__含NonDrawAction'] = "'NonDrawAction'" in init_src
results['E4  __all__含RotatingBehavior'] = "'RotatingBehavior'" in init_src

# ===== F. gacha_service.py =====
gs_src = open('gacha_simulator/service/gacha_service.py', encoding='utf-8').read()
results['F1  gacha_service导入NonDrawAction'] = 'NonDrawAction' in gs_src.split('class GachaService')[0]
results['F2  NonDrawAction分支'] = 'elif _isinstance(action, NonDrawAction)' in gs_src
results['F3  _apply_non_draw方法'] = 'def _apply_non_draw' in gs_src

# ===== G. batch_simulator.py =====
bs_src = open('gacha_simulator/service/batch_simulator.py', encoding='utf-8').read()
results['G1  PityDef含P56字段'] = 'soft_deltas=p.get' in bs_src
results['G2  compute_scope_mappings 5元组解包'] = ', card_to_slot = compute_scope_mappings(pool)' in bs_src
results['G3  PoolPitySpec含card_to_slot'] = 'card_to_slot=card_to_slot' in bs_src
results['G4  pentry含P56字段'] = "'soft_deltas': getattr" in bs_src
results['G5  Pool含epitomizable_cards'] = 'epitomizable_cards=getattr(pe' in bs_src

# ===== H. worst_impact.py =====
wi_src = open('gacha_simulator/core/worst_impact.py', encoding='utf-8').read()
results['H1  compute_scope_mappings 5元组'] = ', card_to_slot = compute_scope_mappings(ref_pool)' in wi_src
results['H2  fallback card_to_slot'] = 'card_to_slot = {}' in wi_src
results['H3  PoolPitySpec card_to_slot'] = 'card_to_slot=card_to_slot' in wi_src

# ===== I. config_toml.py =====
ct_src = open('gacha_simulator/core/config_toml.py', encoding='utf-8').read()
results['I1  epitomizable解析'] = 'epitomizable_raw = p.get' in ct_src
results['I2  PoolEntry含epitomizable'] = 'epitomizable_cards=epitomizable_cards' in ct_src
# I3: save_templates not yet implemented per plan

print(f'{"="*60}')
good = sum(1 for v in results.values() if v)
bad = sum(1 for v in results.values() if not v)
for k, v in sorted(results.items()):
    print(f'{"  ✅" if v else "  ❌"} {k}')
print(f'{"="*60}')
print(f'通过: {good}/{good+bad}')
if bad > 0:
    print(f'缺失: {bad} 项')
else:
    print('全部通过 ✅')
