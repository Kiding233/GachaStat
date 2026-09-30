"""compute_config_hash 的 Banner 级敏感性测试（P61 / ISSUE-013）

compute_config_hash 在 Ph6 后以 store.banner.banners（List[BannerEntry]）为输入，
hash 覆盖 Banner 级字段（available_from/until 秒、enabled、max_draws、lifecycle
规则、内层池 rewards 分布/cost）。本测试锁定这些 Banner 级字段的敏感性，
防止回归到仅 hash pool_id/cost 的旧展平视图口径（那样时间窗口/lifecycle 差异
会误判可比）。
"""
from types import SimpleNamespace

from gacha_simulator.core.config_store import BannerEntry, BannerPoolEntry, LifecycleRuleEntry
from gacha_simulator.core.result_store import compute_config_hash

DAY = 86400


def _banner(banner_id='banner_c1', available_from=None, available_until=None,
            lifecycle=None, rewards=None, cost='draw_resource:160', enabled=True,
            max_draws=None):
    pool = BannerPoolEntry(id='main', cost=cost, rewards=rewards or [
        {'card_id': '_no_card', 'probability': 100.0, 'rarity': 'R'}])
    return BannerEntry(
        id=banner_id, name='测试池', enabled=enabled, max_draws=max_draws,
        available_from=available_from, available_until=available_until,
        pools=[pool], lifecycle=lifecycle or [],
    )


def test_hash_deterministic_same_banner():
    """相同 Banner 配置应产生相同 hash。"""
    h1 = compute_config_hash([_banner()], None)
    h2 = compute_config_hash([_banner()], None)
    assert h1 == h2


def test_hash_sensitive_to_available_window():
    """Banner 开放窗口差异应改变 hash（旧展平视图不覆盖，会误判可比）。"""
    h1 = compute_config_hash([_banner(available_from=0.0, available_until=21 * DAY)], None)
    h2 = compute_config_hash([_banner(available_from=0.0, available_until=30 * DAY)], None)
    assert h1 != h2


def test_hash_sensitive_to_lifecycle_rule():
    """lifecycle 转换规则差异应改变 hash。"""
    lr = LifecycleRuleEntry(condition='pool_draws', pool='main', at=80,
                            action='switch_to', target='step2')
    h1 = compute_config_hash([_banner()], None)
    h2 = compute_config_hash([_banner(lifecycle=[lr])], None)
    assert h1 != h2


def test_hash_sensitive_to_reward_distribution():
    """内层池 rewards 分布差异应改变 hash。"""
    r1 = [{'card_id': '_no_card', 'probability': 100.0, 'rarity': 'R'}]
    r2 = [{'card_id': 'card_a', 'probability': 100.0, 'rarity': 'SSR', 'featured': True}]
    h1 = compute_config_hash([_banner(rewards=r1)], None)
    h2 = compute_config_hash([_banner(rewards=r2)], None)
    assert h1 != h2


def test_hash_sensitive_to_pool_cost():
    """内层池 cost 差异应改变 hash。"""
    h1 = compute_config_hash([_banner(cost='draw_resource:160')], None)
    h2 = compute_config_hash([_banner(cost='draw_resource:320')], None)
    assert h1 != h2


def test_hash_sensitive_to_banner_enabled():
    """Banner enabled 差异应改变 hash。"""
    h1 = compute_config_hash([_banner(enabled=True)], None)
    h2 = compute_config_hash([_banner(enabled=False)], None)
    assert h1 != h2


# ══════════════════════════════════════════════════════════════════
# 2026-10-01：覆盖面回归 —— 「影响模拟结果却没进哈希」的七项
#
# 引入背景：逐项实测发现下列字段改动时旧实现的 hash 不变，于是两份配置哪怕一个
# 每天进 60 资源、一个每天进 600，compare_fingerprints 也判「所有维度相同」。
# 覆盖面以「SimulationEnvBuilder.from_config_store 会读的字段」为准。
# 本组用例把七项逐一钉住——**它们是「静默判为可比」的防线**。
# ══════════════════════════════════════════════════════════════════

def _store():
    from gacha_simulator.core.config_store import ConfigStore
    return ConfigStore()


def _store_hash(store):
    from gacha_simulator.core.result_store import compute_config_hash_for_store
    return compute_config_hash_for_store(store)


def test_hash_sensitive_to_rarity_rank():
    """稀有度层级决定保底的 scope 解析，差异必须改变 hash。"""
    s1, s2 = _store(), _store()
    s1.rarity_rank = {'SSR': 0, 'SR': 1}
    s2.rarity_rank = {'SSR': 1, 'SR': 0}
    assert _store_hash(s1) != _store_hash(s2)


def test_hash_sensitive_to_gain_rules():
    """收入规则决定资源随时间怎么涨——改动数值必须改变 hash。"""
    from gacha_simulator.core.config_store import GainRule
    s1, s2 = _store(), _store()
    s1.gain_rules = [GainRule(rule_type='every_n_days', param='', gains={'draw_resource': 60})]
    s2.gain_rules = [GainRule(rule_type='every_n_days', param='', gains={'draw_resource': 600})]
    assert _store_hash(s1) != _store_hash(s2)
    # 删光规则同样要变（「有没有收入」是最粗的一档差异）
    assert _store_hash(s1) != _store_hash(_store())


def test_hash_sensitive_to_day_overrides():
    from gacha_simulator.core.config_store import DayOverride
    s1, s2 = _store(), _store()
    s1.day_overrides = [DayOverride(day=0, gains={'draw_resource': 200})]
    s2.day_overrides = [DayOverride(day=0, gains={'draw_resource': 9999})]
    assert _store_hash(s1) != _store_hash(s2)


def test_hash_sensitive_to_sim_start_date():
    """起始日期决定按日历展开的收入规则落在哪些天。"""
    s1, s2 = _store(), _store()
    s1.sim_start_date = '2026-01-05'
    s2.sim_start_date = '2026-03-15'
    assert _store_hash(s1) != _store_hash(s2)


def test_hash_sensitive_to_card_defs():
    """卡定义的 initial_count 改变初始持有量，rarity/tags 改变分组。"""
    from gacha_simulator.core.config_store import CardDefEntry
    s1, s2 = _store(), _store()
    s1.card_defs = [CardDefEntry(card_id='c1', name='卡1', rarity='SSR', initial_count=0)]
    s2.card_defs = [CardDefEntry(card_id='c1', name='卡1', rarity='SSR', initial_count=5)]
    assert _store_hash(s1) != _store_hash(s2)
    s3 = _store()
    s3.card_defs = [CardDefEntry(card_id='c1', name='卡1', rarity='SR', initial_count=0)]
    assert _store_hash(s1) != _store_hash(s3)


def test_hash_sensitive_to_resource_lifecycle():
    """资源到期转换/清零改变余额。"""
    from gacha_simulator.core.resource_lifecycle import ResourceLifecycle
    s1, s2 = _store(), _store()
    s1.resource_lifecycle.enabled = True
    s1.resource_lifecycle.rules = [
        ResourceLifecycle(resource_id='token', expire_at=1000.0, on_expire={'clear': True})]
    s2.resource_lifecycle.enabled = True
    s2.resource_lifecycle.rules = []
    assert _store_hash(s1) != _store_hash(s2)


def test_hash_sensitive_to_card_overflow_map():
    """满突溢出的分段表改变返还的资源。"""
    from gacha_simulator.core.overflow import OverflowBand
    s1, s2 = _store(), _store()
    s1.card_overflow_map = {'c1': [OverflowBand(min=1, max=None,
                                                resources={'exchange_currency': 5})]}
    s2.card_overflow_map = {'c1': [OverflowBand(min=1, max=None,
                                                resources={'exchange_currency': 50})]}
    assert _store_hash(s1) != _store_hash(s2)


def test_store_hash_is_deterministic():
    """同一份配置两次取值必须相同（防序列化引入非确定性）。"""
    from gacha_simulator.core.config_store import GainRule, CardDefEntry
    s = _store()
    s.gain_rules = [GainRule(rule_type='every_n_days', param='', gains={'a': 1})]
    s.card_defs = [CardDefEntry(card_id='c1', name='卡1', rarity='SSR', initial_count=0)]
    assert _store_hash(s) == _store_hash(s)


def test_hash_legacy_pool_entry_branch():
    """旧 PoolEntry 展平视图兼容分支：pool_id/cost 参与 hash（Banner 级字段不覆盖）。"""
    legacy = SimpleNamespace(pool_id='pool_c1', cost='draw_resource:160')
    h1 = compute_config_hash([legacy], None)
    h2 = compute_config_hash(
        [SimpleNamespace(pool_id='pool_c1', cost='draw_resource:320')], None)
    assert h1 != h2


# ══════════════════════════════════════════════════════════════════
# P79 8.2：停止条件的可比性指纹（摘要含参数值 + 纳入 config_hash）
# ══════════════════════════════════════════════════════════════════

def _summary(tree):
    from gacha_simulator.core.result_store import canonical_stop_condition_summary
    return canonical_stop_condition_summary(tree)


def test_summary_empty_tree_sentinel():
    """空树产出固定哨兵 ''，与任何真实树都不同。

    空树的两种写法（`None` = 段缺失/规范化结果，`{}` = 裸表头或 GUI 编辑期中间态）
    运行时行为一致，故须产出同一哨兵——否则同一行为的两种写法会得到不同
    `config_hash`，可比性分析误判为「配置不同」（P79 R19 审计定位）。
    """
    assert _summary(None) == ''
    assert _summary({}) == ''
    assert _summary({'type': 'time_limit', 'max_time': 1.0}) != ''


def test_summary_is_key_order_independent():
    """sort_keys 消除 TOML 解析与 GUI 重建两条路径的键序差异。"""
    a = {'mode': 'any', 'conditions': [{'type': 'time_limit', 'max_time': 1.0}]}
    b = {'conditions': [{'max_time': 1.0, 'type': 'time_limit'}], 'mode': 'any'}
    assert _summary(a) == _summary(b)


def test_summary_differs_on_parameter_value_only():
    """两组的差异**仅在参数值**（条件 id / 形态完全相同）时摘要仍须不同。

    这是「摘要须含参数值、不能只渲染条件 id」的直接验证——表达式渲染只含 id，
    两组仅阈值不同的配置会产出同一表达式串。
    """
    a = {'mode': 'any', 'conditions': [{'type': 'time_limit', 'max_time': 1.0}]}
    b = {'mode': 'any', 'conditions': [{'type': 'time_limit', 'max_time': 2.0}]}
    assert _summary(a) != _summary(b)


def test_config_hash_differs_on_stop_condition_only():
    """两组不同 [stop_condition] 的配置产出不同 config_hash。

    不纳入时这两组会被判为 same 维度，可比性结论与真实情况相反。
    """
    a = {'mode': 'any', 'conditions': [{'type': 'time_limit', 'max_time': 1.0}]}
    b = {'mode': 'all', 'conditions': [
        {'type': 'time_limit', 'max_time': 1.0},
        {'type': 'resource_threshold', 'resource': 'draw_resource',
         'operator': '<=', 'threshold': 0}]}
    banner = _banner()
    h_a = compute_config_hash([banner], None, stop_condition_summary=_summary(a))
    h_b = compute_config_hash([banner], None, stop_condition_summary=_summary(b))
    assert h_a != h_b


def test_config_hash_unchanged_by_old_call_shapes():
    """既有三参 / 四参位置调用不受新参数影响（同一 hash）。"""
    banner = _banner()
    assert (compute_config_hash([banner], None) ==
            compute_config_hash([banner], None, None))
    assert (compute_config_hash([banner], None) ==
            compute_config_hash([banner], None, None, None))
