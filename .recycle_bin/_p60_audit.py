import os, re, sys

results = []

def read_safe(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, 'r', encoding='gbk', errors='ignore') as f:
            return f.read()

# 1. worst_impact.py L280
content = read_safe('gacha_simulator/core/worst_impact.py')
if "{'counters': init_pity}" in content:
    results.append('⚠️  worst_impact.py L280: 仍用旧格式 {counters: init_pity}')
else:
    results.append('✅ worst_impact.py: 格式已更新')

# 2. GDR PityProgressAtT registration
gdr = read_safe('gacha_simulator/core/gdr.py')
if 'PityProgressAtT' in gdr:
    results.append('✅ GDR: PityProgressAtT 已注册')
else:
    results.append('ℹ️  GDR: PityProgressAtT 未注册（计划标注为非阻塞）')

# 3. collector.py
coll = read_safe('gacha_simulator/core/collector.py')
if 'pity_state.to_dict()' in coll:
    results.append('✅ collector.py: pity_state.to_dict() 正常')
else:
    results.append('⚠️  collector.py: 异常')

# 4. streaming.py
stream = read_safe('gacha_simulator/core/streaming.py')
if 'pool_end_pity_states' in stream:
    results.append('✅ streaming.py: pool_end_pity_states 已处理')
else:
    results.append('ℹ️  streaming.py: 无 pool_end_pity_states')

# 5. 测试文件旧 API
old_api = []
for root, dirs, files in os.walk('tests'):
    for fn in files:
        if fn.endswith('.py') and not fn.startswith('test_p60'):
            tc = read_safe(os.path.join(root, fn))
            if 'state.increment(' in tc:
                old_api.append(f'{fn}: increment()')
            if 'pity_state.increment(' in tc:
                old_api.append(f'{fn}: pity_state.increment()')
            if '.reset(' in tc and 'pity' in tc.lower():
                # check if it's PityState.reset not something else
                if re.search(r'[a-z_]+\.reset\(', tc):
                    old_api.append(f'{fn}: .reset()')
if old_api:
    results.append(f'⚠️  测试旧API残留: {old_api}')
else:
    results.append('✅ 测试文件无旧API残留')

# 6. gacha_service.py 单参数 get
svc = read_safe('gacha_simulator/service/gacha_service.py')
# Find get(pname) without counter, 0
m = re.findall(r'pity_state\.get\(([^,)]+)\)', svc)
if m:
    results.append(f'⚠️  gacha_service.py 单参数get: {m}')
else:
    results.append('✅ gacha_service.py: 无单参数get')

# 7. PityEngine 旧 import 残留 — check batch_simulator imports old PityEngine methods
bs = read_safe('gacha_simulator/service/batch_simulator.py')
if 'SoftPityBehavior' in bs and 'HardPityBehavior' in bs:
    results.append('✅ batch_simulator: 旧 behavior 类正常导入')
if 'PityEngine' in bs:
    results.append('✅ batch_simulator: PityEngine 正常导入')

# 8. GachaState.acquired import check
state = read_safe('gacha_simulator/core/state.py')
if "acquired: Dict[str, int]" in state:
    results.append('✅ GachaState: acquired 字段存在')
if "def add_card" in state:
    results.append('✅ GachaState: add_card 方法存在')
if "def get_card_count" in state:
    results.append('✅ GachaState: get_card_count 方法存在')
if "pity_counters" not in state:
    results.append('✅ GachaState: pity_counters 已删除')
else:
    results.append('⚠️  GachaState: pity_counters 仍存在!')

# 9. StrategyContext.acquired @property
strat = read_safe('gacha_simulator/core/strategy.py')
if '@property' in strat and 'def acquired' in strat.split('@property')[1] if '@property' in strat else False:
    results.append('✅ StrategyContext: acquired 是 @property')
# Simpler check
if 'def acquired(self)' in strat:
    results.append('✅ StrategyContext: acquired @property 已定义')

# 10. DrawInfo / PityContext
pity = read_safe('gacha_simulator/core/pity.py')
if 'class DrawInfo' in pity:
    results.append('✅ pity.py: DrawInfo 已定义')
if 'class PityContext' in pity:
    results.append('✅ pity.py: PityContext 已定义')
if 'class CounterBasedBehavior' in pity:
    results.append('✅ pity.py: CounterBasedBehavior 已定义')
if 'BEHAVIOR_REGISTRY' in pity:
    results.append('✅ pity.py: BEHAVIOR_REGISTRY 已定义')
if 'def create_behavior' in pity:
    results.append('✅ pity.py: create_behavior 工厂已定义')
if 'class Counter' in pity:
    results.append('✅ pity.py: Counter 已定义')
if 'class Flag' in pity:
    results.append('✅ pity.py: Flag 已定义')
if 'class LifecycleConfig' in pity:
    results.append('✅ pity.py: LifecycleConfig 已定义')
if 'self.data' in pity:
    results.append('✅ pity.py: PityState.data 已公开')

# 11. gacha_service.py state.add_card
if 'state.add_card(reward.id)' in svc:
    results.append('✅ gacha_service.py: state.add_card() 已添加')
if 'state.get_card_count(reward.id)' in svc:
    results.append('✅ gacha_service.py: bonus 计算使用 state.get_card_count()')
if 'acquired_counts' not in svc:
    results.append('✅ gacha_service.py: acquired_counts 已删除')

# 12. stop_condition
sc = read_safe('gacha_simulator/core/stop_condition.py')
if 'state.get_card_count(self.target_id)' in sc:
    results.append('✅ stop_condition.py: TargetAcquiredCondition 使用 state.get_card_count()')
else:
    results.append('⚠️  stop_condition.py: 可能未更新')

# 13. config_store
cs = read_safe('gacha_simulator/core/config_store.py')
if 'featured_card_ids' in cs:
    results.append('✅ config_store.py: PoolEntry.featured_card_ids 存在')
if 'rarity_rank' in cs:
    results.append('✅ config_store.py: rarity_rank 字段存在')
if 'def is_limited' in cs:
    results.append('✅ config_store.py: is_limited() 方法存在')
if 'def _parse_rarities' in cs:
    results.append('✅ config_store.py: _parse_rarities() 方法存在')

# 14. config_toml
ct = read_safe('gacha_simulator/core/config_toml.py')
if 'store._parse_rarities(data)' in ct:
    results.append('✅ config_toml.py: _parse_rarities 已在 load_toml 调用')
if 'buckets = {}' in ct and 'rarities' in ct:
    results.append('✅ config_toml.py: save_toml [rarities] 段已添加')
if 'pool.featured_card_ids = [' in ct:
    results.append('✅ config_toml.py: _build_pools 统一填充 featured_card_ids')

# 15. config.toml
toml = read_safe('gacha_simulator/config/config.toml')
if '[rarities]' in toml:
    results.append('✅ config.toml: [rarities] 段已添加')

# 16. vulnerability.py
vuln = read_safe('gacha_simulator/core/vulnerability.py')
if 'PityState.from_dict(pes[pool_id])' in vuln:
    results.append('✅ vulnerability.py: from_dict 反序列化已实现（两处）')
if 'from .pity import PityState' in vuln:
    results.append('✅ vulnerability.py: PityState 导入已添加')

# 17. generalized_drop_rate.py
gdr_rate = read_safe('gacha_simulator/core/generalized_drop_rate.py')
if 'PityState.from_dict(pity_state)' in gdr_rate:
    results.append('✅ generalized_drop_rate.py: from_dict 反序列化已实现')
if 'from .pity import PityState' in gdr_rate:
    results.append('✅ generalized_drop_rate.py: PityState 导入已添加')
if 'ps.get(self.counter_name' in gdr_rate:
    results.append('✅ generalized_drop_rate.py: 三参数 get() 已正确')

# 18. batch_simulator.py from_dict
bs2 = read_safe('gacha_simulator/service/batch_simulator.py')
if 'PityState.from_dict(env.pity_state_init)' in bs2:
    results.append('✅ batch_simulator.py: _run_single 使用 from_dict')
if 'ps_init = _PS()' in bs2 or 'ps_init.set' in bs2:
    results.append('✅ batch_simulator.py: L648 方案A 已实现')

# 19. scripts
ps_sim = read_safe('scripts/profile_simulation.py')
ps_sim2 = read_safe('scripts/profile_sim.py')
if 'PityState.from_dict(env.pity_state_init)' in ps_sim:
    results.append('✅ profile_simulation.py: from_dict 已实现')
if 'PityState.from_dict(env.pity_state_init)' in ps_sim2:
    results.append('✅ profile_sim.py: from_dict 已实现')

# 20. PityEngine 新方法
pe_new = ['_behaviors_for_pool', 'get_counter', 'get_trigger_count', 'is_guaranteed', 'is_active', 'get_state_summary', '_infer_rarity']
for method in pe_new:
    if f'def {method}' in pity:
        results.append(f'✅ PityEngine.{method}() 已定义')
    else:
        results.append(f'⚠️  PityEngine.{method}() 缺失!')

# Summary
print('\n'.join(results))
warn = [r for r in results if r.startswith('⚠️')]
print(f'\n--- 共 {len(results)} 项检查, {len(warn)} 个警告 ---')
