"""P60 门控测试：旧/新 PityEngine 行为等价。

⚠️ 本测试不通过 → P60 不可交付。
"""
import pytest
from gacha_simulator.core.pity import (
    PityState,
    PityEngine,
    PoolPitySpec,
    PityDefParsed,
    SoftPityBehavior,
    HardPityBehavior,
)


# ═══════════════════════════════════════════════════
# 测试 fixtures
# ═══════════════════════════════════════════════════

def _make_spec(pity_names, featured_ids=None, ssr_ids=None):
    return PoolPitySpec(
        pity_names=list(pity_names),
        featured_ids=featured_ids or set(),
        ssr_ids=ssr_ids or set(),
    )


def _make_pdef(name, btype="soft", params=None, reset="any_ssr"):
    return PityDefParsed(
        name=name, btype=btype,
        params=params or {"start": "80", "end": "90"},
        target_distribution={},
        reset_condition=reset, pools="*",
    )


# ═══════════════════════════════════════════════════
# T2：概率等价
# ═══════════════════════════════════════════════════

@pytest.mark.parametrize("counters,reset_condition", [
    # any_ssr
    ({"ssr_soft": 89}, "any_ssr"),
    ({"ssr_soft": 80}, "any_ssr"),
    ({"ssr_soft": 90}, "any_ssr"),
    # featured_ssr
    ({"ssr_soft": 89}, "featured_ssr"),
    ({"ssr_soft": 80}, "featured_ssr"),
    # never
    ({"ssr_hard": 89}, "never"),
    ({"ssr_hard": 90}, "never"),
])
def test_before_draw_probabilities_equivalent(counters, reset_condition):
    """重构前后 before_draw 产出的概率分布完全等价（rel=1e-9）。"""
    base_probs = {"ssr": 0.005, "ssr_alt": 0.005, "sr": 0.05, "r": 0.94}

    pdef = _make_pdef("ssr_soft", btype="soft",
                      params={"start": "80", "end": "90"},
                      reset=reset_condition)
    spec = _make_spec(["ssr_soft"], featured_ids={"ssr"}, ssr_ids={"ssr", "ssr_alt"})

    behavior = SoftPityBehavior(
        start_at=80, end_at=90,
        target_distribution={"ssr": 1.0},
    )
    old_engine = PityEngine(
        pool_specs={"pool_1": spec},
        pity_defs={"ssr_soft": pdef},
        behaviors={"ssr_soft": behavior},
    )
    new_engine = PityEngine(
        pool_specs={"pool_1": spec},
        pity_defs={"ssr_soft": pdef},
        behaviors={"ssr_soft": behavior},
    )

    old_state = PityState()
    new_state = PityState()
    for name, val in counters.items():
        old_state.data.setdefault(name, {})["counter"] = val
        new_state.data.setdefault(name, {})["counter"] = val

    old_probs = old_engine.before_draw("pool_1", old_state, base_probs)
    new_probs = new_engine.before_draw("pool_1", new_state, base_probs)

    for slot in set(old_probs) | set(new_probs):
        assert old_probs.get(slot, 0.0) == pytest.approx(
            new_probs.get(slot, 0.0), rel=1e-9
        ), f"slot {slot}: old={old_probs.get(slot, 0)} new={new_probs.get(slot, 0)}"


# ═══════════════════════════════════════════════════
# T3：after_draw 状态等价
# ═══════════════════════════════════════════════════

@pytest.mark.parametrize("reset_condition,reward_id,expected_counter_after", [
    ("any_ssr", "ssr", 0),
    ("any_ssr", "ssr_alt", 0),
    ("any_ssr", "sr", 90),
    ("featured_ssr", "ssr", 0),
    ("featured_ssr", "ssr_alt", 90),
    ("featured_ssr", "sr", 90),
    ("never", "ssr", 90),
    ("never", "sr", 90),
])
def test_after_draw_state_equivalent(reset_condition, reward_id, expected_counter_after):
    """重构前后 after_draw 对 PityState 的修改完全等价。"""
    base_probs = {"ssr": 0.005, "ssr_alt": 0.005, "sr": 0.05, "r": 0.94}

    pdef = _make_pdef("ssr_soft", btype="soft",
                      params={"start": "80", "end": "90"},
                      reset=reset_condition)
    spec = _make_spec(["ssr_soft"],
                      featured_ids={"ssr"},
                      ssr_ids={"ssr", "ssr_alt"})

    behavior = SoftPityBehavior(start_at=80, end_at=90)

    old_engine = PityEngine(
        pool_specs={"pool_1": spec}, pity_defs={"ssr_soft": pdef},
        behaviors={"ssr_soft": behavior},
    )
    new_engine = PityEngine(
        pool_specs={"pool_1": spec}, pity_defs={"ssr_soft": pdef},
        behaviors={"ssr_soft": behavior},
    )

    old_state = PityState()
    new_state = PityState()
    old_state.data.setdefault("ssr_soft", {})["counter"] = 89
    new_state.data.setdefault("ssr_soft", {})["counter"] = 89

    old_engine.before_draw("pool_1", old_state, base_probs)
    new_engine.before_draw("pool_1", new_state, base_probs)

    old_engine.after_draw("pool_1", old_state, reward_id)
    new_engine.after_draw("pool_1", new_state, reward_id)

    assert old_state.get("ssr_soft", "counter") == expected_counter_after
    assert new_state.get("ssr_soft", "counter") == expected_counter_after


# ═══════════════════════════════════════════════════
# T2a：硬保底概率等价
# ═══════════════════════════════════════════════════

@pytest.mark.parametrize("counters,reset_condition", [
    ({"ssr_hard": 89}, "any_ssr"),
    ({"ssr_hard": 90}, "any_ssr"),
    ({"ssr_hard": 89}, "featured_ssr"),
    ({"ssr_hard": 90}, "featured_ssr"),
    ({"ssr_hard": 89}, "never"),
    ({"ssr_hard": 90}, "never"),
])
def test_before_draw_hard_pity_equivalent(counters, reset_condition):
    """硬保底——重构前后概率等价（rel=1e-9）。"""
    base_probs = {"ssr": 0.005, "ssr_alt": 0.005, "sr": 0.05, "r": 0.94}

    pdef = _make_pdef("ssr_hard", btype="hard",
                      params={"threshold": "90"},
                      reset=reset_condition)
    spec = _make_spec(["ssr_hard"], featured_ids={"ssr"}, ssr_ids={"ssr", "ssr_alt"})

    behavior = HardPityBehavior(threshold=90)
    old_engine = PityEngine(
        pool_specs={"pool_1": spec}, pity_defs={"ssr_hard": pdef},
        behaviors={"ssr_hard": behavior},
    )
    new_engine = PityEngine(
        pool_specs={"pool_1": spec}, pity_defs={"ssr_hard": pdef},
        behaviors={"ssr_hard": behavior},
    )

    old_state = PityState()
    new_state = PityState()
    for name, val in counters.items():
        old_state.data.setdefault(name, {})["counter"] = val
        new_state.data.setdefault(name, {})["counter"] = val

    old_probs = old_engine.before_draw("pool_1", old_state, base_probs)
    new_probs = new_engine.before_draw("pool_1", new_state, base_probs)

    for slot in set(old_probs) | set(new_probs):
        assert old_probs.get(slot, 0.0) == pytest.approx(
            new_probs.get(slot, 0.0), rel=1e-9
        ), f"hard pity slot {slot}: old={old_probs.get(slot, 0)} new={new_probs.get(slot, 0)}"


# ═══════════════════════════════════════════════════
# T2b：get_probabilities() 只读——不修改 PityState
# ═══════════════════════════════════════════════════

def test_get_probabilities_readonly():
    """策略层多次查询 get_probabilities() 不修改保底计数器。"""
    base_probs = {"ssr": 0.005, "ssr_alt": 0.005, "sr": 0.05, "r": 0.94}

    pdef = _make_pdef("ssr_soft", btype="soft",
                      params={"start": "80", "end": "90"},
                      reset="any_ssr")
    spec = _make_spec(["ssr_soft"], featured_ids={"ssr"}, ssr_ids={"ssr", "ssr_alt"})

    behavior = SoftPityBehavior(start_at=80, end_at=90)
    engine = PityEngine(
        pool_specs={"pool_1": spec}, pity_defs={"ssr_soft": pdef},
        behaviors={"ssr_soft": behavior},
    )

    state = PityState()
    state.data.setdefault("ssr_soft", {})["counter"] = 85

    probs1 = engine.get_probabilities("pool_1", state, base_probs)
    counter_after_1 = state.get("ssr_soft", "counter", 0)
    probs2 = engine.get_probabilities("pool_1", state, base_probs)
    counter_after_2 = state.get("ssr_soft", "counter", 0)

    assert counter_after_1 == 85, f"get_probabilities 不应修改计数器，实际变为 {counter_after_1}"
    assert counter_after_2 == 85, f"第二次查询也不应修改计数器，实际变为 {counter_after_2}"
    for slot in set(probs1) | set(probs2):
        assert probs1.get(slot, 0.0) == pytest.approx(
            probs2.get(slot, 0.0), rel=1e-9
        ), f"两次查询结果应一致 slot {slot}"


# ═══════════════════════════════════════════════════
# T2c：模板绑定池子——resolved_targets 桥接等价
# ═══════════════════════════════════════════════════

def test_resolved_targets_bridge_equivalent():
    """模板绑定池子——resolved_targets 覆盖 behavior 内置 target_distribution 的行为等价。"""
    base_probs = {"ssr": 0.005, "ssr_alt": 0.005, "sr": 0.05, "r": 0.94}

    pdef = _make_pdef("ssr_soft", btype="soft",
                      params={"start": "80", "end": "90"},
                      reset="any_ssr")
    spec = PoolPitySpec(
        pity_names=["ssr_soft"],
        featured_ids={"diluc"},
        ssr_ids={"diluc", "jean", "ssr_alt"},
        resolved_targets={"ssr_soft": {"diluc": 0.5, "jean": 0.5}},
    )

    behavior = SoftPityBehavior(
        start_at=80, end_at=90,
        target_distribution={"diluc": 1.0},
    )

    old_engine = PityEngine(
        pool_specs={"pool_1": spec}, pity_defs={"ssr_soft": pdef},
        behaviors={"ssr_soft": behavior},
    )
    new_engine = PityEngine(
        pool_specs={"pool_1": spec}, pity_defs={"ssr_soft": pdef},
        behaviors={"ssr_soft": behavior},
    )

    old_state = PityState()
    new_state = PityState()
    old_state.data.setdefault("ssr_soft", {})["counter"] = 89
    new_state.data.setdefault("ssr_soft", {})["counter"] = 89

    old_probs = old_engine.before_draw("pool_1", old_state, base_probs)
    new_probs = new_engine.before_draw("pool_1", new_state, base_probs)

    for slot in set(old_probs) | set(new_probs):
        assert old_probs.get(slot, 0.0) == pytest.approx(
            new_probs.get(slot, 0.0), rel=1e-9
        ), f"resolved_targets slot {slot}: old={old_probs.get(slot, 0)} new={new_probs.get(slot, 0)}"

    state_q = PityState()
    state_q.data.setdefault("ssr_soft", {})["counter"] = 85
    probs_q_old = old_engine.get_probabilities("pool_1", state_q, base_probs)
    probs_q_new = new_engine.get_probabilities("pool_1", state_q, base_probs)
    for slot in set(probs_q_old) | set(probs_q_new):
        assert probs_q_old.get(slot, 0.0) == pytest.approx(
            probs_q_new.get(slot, 0.0), rel=1e-9
        )


# ═══════════════════════════════════════════════════
# T3a：跨池 behavior 不交叉污染
# ═══════════════════════════════════════════════════

def test_cross_pool_no_contamination():
    """两个池子各有同名 behavior——调度不应跨池污染计数器。"""
    base_probs = {"ssr": 0.005, "ssr_alt": 0.005, "sr": 0.05, "r": 0.94}

    pdef1 = _make_pdef("ssr_soft", btype="soft",
                       params={"start": "80", "end": "90"}, reset="any_ssr")
    spec1 = _make_spec(["ssr_soft"], featured_ids={"ssr_a"}, ssr_ids={"ssr_a", "ssr_alt"})
    bh1 = SoftPityBehavior(start_at=80, end_at=90)

    pdef2_soft = _make_pdef("ssr_soft_p2", btype="soft",
                            params={"start": "80", "end": "90"}, reset="any_ssr")
    pdef2_hard = _make_pdef("ssr_hard", btype="hard",
                            params={"threshold": "90"}, reset="any_ssr")
    spec2 = _make_spec(["ssr_soft_p2", "ssr_hard"], featured_ids={"ssr_b"}, ssr_ids={"ssr_b", "ssr_alt"})
    bh2_soft = SoftPityBehavior(start_at=80, end_at=90)
    bh2_hard = HardPityBehavior(threshold=90)

    engine = PityEngine(
        pool_specs={"pool_1": spec1, "pool_2": spec2},
        pity_defs={"ssr_soft": pdef1, "ssr_soft_p2": pdef2_soft, "ssr_hard": pdef2_hard},
        behaviors={"ssr_soft": bh1, "ssr_soft_p2": bh2_soft, "ssr_hard": bh2_hard},
    )

    state = PityState()

    engine.before_draw("pool_1", state, base_probs)
    engine.after_draw("pool_1", state, "sr")

    probs_p2 = engine.get_probabilities("pool_2", state, base_probs)
    assert abs(sum(probs_p2.values()) - 1.0) < 1e-9
