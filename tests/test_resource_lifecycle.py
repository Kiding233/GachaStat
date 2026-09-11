"""P77 资源生命周期：数据模型与到期时刻解析单测（§3.8 6a）。

覆盖：dataclass 默认值、resolve_expire_time 两种到期来源与缺失回退、
build_strategy_context 产出的 resource_expiry 预览（余额 / 剩余天数契约 / 到期行为）。
"""

import pytest

from gacha_simulator.core.resource_lifecycle import (
    ResourceLifecycle,
    ResourceLifecycleConfig,
    resolve_expire_time,
)
from gacha_simulator.core.state import GachaState
from gacha_simulator.core.stop_condition import AllPoolsEndCondition
from gacha_simulator.core.strategy_context_builder import build_strategy_context
from gacha_simulator.core.target_card import TargetCardSet

DAY = 86400


def _build_ctx(resources, real_time, rules, banners=None):
    """构造最小 StrategyContext（仅资源到期预览相关字段有值）。"""
    state = GachaState(resources=dict(resources))
    state.real_time = real_time
    _banners = banners or []
    return build_strategy_context(
        state=state,
        current_pools=[],
        all_pools=[],
        real_time=real_time,
        target_cards=TargetCardSet([]),
        stop_condition=AllPoolsEndCondition(0),
        pity_engine=None,
        pity_state=None,
        pool_draw_counts={},
        total_draws=0,
        last_draw_pity_triggered=False,
        ssr_ids=set(),
        banners=_banners,
        all_banners=_banners,
        resource_lifecycle_rules=rules,
    )


# ══════════════════════════════════════════════════════════════════
# 默认值与向后兼容
# ══════════════════════════════════════════════════════════════════

class TestDefaults:
    def test_defaults(self):
        """空配置默认启用且无规则；空规则各字段为 None（无生命周期声明）。"""
        cfg = ResourceLifecycleConfig()
        assert cfg.enabled is True
        assert cfg.rules == []

        rule = ResourceLifecycle(resource_id='x')
        assert rule.expire_at is None
        assert rule.expire_with_banner is None
        assert rule.on_expire is None

    def test_ctx_expiry_empty_without_rules(self):
        """未传规则时预览恒为空列表（P69 契约：现有策略不经修改即可运行）。"""
        ctx = _build_ctx({'a': 1}, 0.0, None)
        assert ctx.resource_expiry == []


# ══════════════════════════════════════════════════════════════════
# resolve_expire_time：到期时刻解析
# ══════════════════════════════════════════════════════════════════

class TestResolveExpireTime:
    def test_resolve_expire_at(self):
        """expire_at 直传（已为秒）。"""
        rule = ResourceLifecycle(resource_id='x', expire_at=12 * DAY)
        assert resolve_expire_time(rule, {}) == 12 * DAY

    def test_resolve_expire_with_banner(self):
        """expire_with_banner 查 banner 的 available_until。"""
        rule = ResourceLifecycle(resource_id='x', expire_with_banner='b1')
        assert resolve_expire_time(rule, {'b1': 5 * DAY}) == 5 * DAY

    def test_resolve_expire_banner_missing(self):
        """banner 不存在时返回 None（校验层负责报错，解析层只做回退）。"""
        rule = ResourceLifecycle(resource_id='x', expire_with_banner='b9')
        assert resolve_expire_time(rule, {'b1': 5 * DAY}) is None


# ══════════════════════════════════════════════════════════════════
# resource_expiry 预览（策略可知性）
# ══════════════════════════════════════════════════════════════════

class TestExpiryPreview:
    def test_remaining_ceil(self):
        """剩余天数向上取整，余额与到期行为透传。"""
        rule = ResourceLifecycle(
            resource_id='a', expire_at=5 * DAY,
            on_expire={'convert_to': 'b', 'from': 3, 'to': 2})
        ctx = _build_ctx({'a': 3}, 2 * DAY, [rule])

        assert len(ctx.resource_expiry) == 1
        exp = ctx.resource_expiry[0]
        assert exp.resource_id == 'a'
        assert exp.balance == 3
        assert exp.remaining == 3                 # ceil((5-2)/1) = 3
        assert exp.expire_at == 5 * DAY
        assert exp.on_expire == {'convert_to': 'b', 'from': 3, 'to': 2}
        assert 'a' in exp.description

    def test_remaining_zero_after_expire(self):
        """已越过到期点时 remaining 钳 0（与 real_time >= expire_at 的 >= 边界对齐）。"""
        rule = ResourceLifecycle(resource_id='a', expire_at=5 * DAY,
                                 on_expire={'clear': True})
        ctx = _build_ctx({'a': 3}, 6 * DAY, [rule])
        assert ctx.resource_expiry[0].remaining == 0

    def test_remaining_ceil_vs_int_on_partial_day(self):
        """不足一天时向上取整为 1 天（int() 向下取整会得 0，令「剩余 N 天内」阈值提前误判）。"""
        rule = ResourceLifecycle(resource_id='a', expire_at=5 * DAY,
                                 on_expire={'clear': True})
        ctx = _build_ctx({'a': 3}, int(4.5 * DAY), [rule])   # 距到期 0.5 天
        assert ctx.resource_expiry[0].remaining == 1

    def test_remaining_zero_at_exact_due(self):
        """正好到期时 remaining 为 0，与 real_time >= expire_at 的触发边界一致。"""
        rule = ResourceLifecycle(resource_id='a', expire_at=5 * DAY,
                                 on_expire={'clear': True})
        ctx = _build_ctx({'a': 3}, 5 * DAY, [rule])
        assert ctx.resource_expiry[0].remaining == 0

    def test_expire_with_banner_preview(self):
        """expire_with_banner 经 all_banners 展开为具体到期时刻。"""
        class _B:
            id = 'b1'
            available_until = 7 * DAY

        rule = ResourceLifecycle(resource_id='a', expire_with_banner='b1',
                                 on_expire={'clear': True})
        ctx = _build_ctx({'a': 5}, 1 * DAY, [rule], banners=[_B()])
        assert ctx.resource_expiry[0].expire_at == 7 * DAY
        assert ctx.resource_expiry[0].remaining == 6

    def test_undeclared_resource_absent(self):
        """无生命周期声明的资源不出现在预览中。"""
        rule = ResourceLifecycle(resource_id='a', expire_at=5 * DAY,
                                 on_expire={'clear': True})
        ctx = _build_ctx({'a': 1, 'untracked': 99}, 0.0, [rule])
        ids = [e.resource_id for e in ctx.resource_expiry]
        assert ids == ['a']
        assert 'untracked' not in ids
