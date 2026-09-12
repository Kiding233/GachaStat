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


def _sched(until):
    return SimpleNamespace(pool_id='banner_c1', available_from=0, available_until=until)


def test_hash_deterministic_same_banner():
    """相同 Banner 配置应产生相同 hash。"""
    h1 = compute_config_hash([_banner()], None, [])
    h2 = compute_config_hash([_banner()], None, [])
    assert h1 == h2


def test_hash_sensitive_to_available_window():
    """Banner 开放窗口差异应改变 hash（旧展平视图不覆盖，会误判可比）。"""
    h1 = compute_config_hash([_banner(available_from=0.0, available_until=21 * DAY)], None, [])
    h2 = compute_config_hash([_banner(available_from=0.0, available_until=30 * DAY)], None, [])
    assert h1 != h2


def test_hash_sensitive_to_lifecycle_rule():
    """lifecycle 转换规则差异应改变 hash。"""
    lr = LifecycleRuleEntry(condition='pool_draws', pool='main', at=80,
                            action='switch_to', target='step2')
    h1 = compute_config_hash([_banner()], None, [])
    h2 = compute_config_hash([_banner(lifecycle=[lr])], None, [])
    assert h1 != h2


def test_hash_sensitive_to_reward_distribution():
    """内层池 rewards 分布差异应改变 hash。"""
    r1 = [{'card_id': '_no_card', 'probability': 100.0, 'rarity': 'R'}]
    r2 = [{'card_id': 'card_a', 'probability': 100.0, 'rarity': 'SSR', 'featured': True}]
    h1 = compute_config_hash([_banner(rewards=r1)], None, [])
    h2 = compute_config_hash([_banner(rewards=r2)], None, [])
    assert h1 != h2


def test_hash_sensitive_to_pool_cost():
    """内层池 cost 差异应改变 hash。"""
    h1 = compute_config_hash([_banner(cost='draw_resource:160')], None, [])
    h2 = compute_config_hash([_banner(cost='draw_resource:320')], None, [])
    assert h1 != h2


def test_hash_sensitive_to_banner_enabled():
    """Banner enabled 差异应改变 hash。"""
    h1 = compute_config_hash([_banner(enabled=True)], None, [])
    h2 = compute_config_hash([_banner(enabled=False)], None, [])
    assert h1 != h2


def test_hash_sensitive_to_schedule_window():
    """排期窗口（可用时间秒）差异应改变 hash。"""
    h1 = compute_config_hash([_banner()], None, [_sched(21 * DAY)])
    h2 = compute_config_hash([_banner()], None, [_sched(30 * DAY)])
    assert h1 != h2


def test_hash_legacy_pool_entry_branch():
    """旧 PoolEntry 展平视图兼容分支：pool_id/cost 参与 hash（Banner 级字段不覆盖）。"""
    legacy = SimpleNamespace(pool_id='pool_c1', cost='draw_resource:160')
    h1 = compute_config_hash([legacy], None, [])
    h2 = compute_config_hash(
        [SimpleNamespace(pool_id='pool_c1', cost='draw_resource:320')], None, [])
    assert h1 != h2


# ══════════════════════════════════════════════════════════════════
# P79 8.2：停止条件的可比性指纹（摘要含参数值 + 纳入 config_hash）
# ══════════════════════════════════════════════════════════════════

def _summary(tree):
    from gacha_simulator.core.result_store import canonical_stop_condition_summary
    return canonical_stop_condition_summary(tree)


def test_summary_empty_tree_sentinel():
    """空树（None）产出固定哨兵 ''，与任何真实树都不同。"""
    assert _summary(None) == ''
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
    h_a = compute_config_hash([banner], None, [], stop_condition_summary=_summary(a))
    h_b = compute_config_hash([banner], None, [], stop_condition_summary=_summary(b))
    assert h_a != h_b


def test_config_hash_unchanged_by_old_call_shapes():
    """既有三参 / 四参位置调用不受新参数影响（同一 hash）。"""
    banner = _banner()
    assert (compute_config_hash([banner], None, []) ==
            compute_config_hash([banner], None, [], None))
    assert (compute_config_hash([banner], None, []) ==
            compute_config_hash([banner], None, [], None, None))
