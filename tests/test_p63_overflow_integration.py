"""P63 集成测试——溢出管道端到端验证。

覆盖：
  PIPE-1~7: add_card 溢出管道
  PRIO-1~3: 优先级查找（卡片 > 稀有度默认）
  REG-1~4: 回归验证
  CONFIG-RT: 配置 round-trip
  KEY-NORM: 键名 .lower() 规范化
"""

import os
import tempfile

import pytest
from gacha_simulator.core.state import GachaState
from gacha_simulator.core.overflow import (
    OverflowBand,
    match_overflow_bands,
)
from gacha_simulator.core.config_store import (
    CardDefEntry,
    ConfigStore,
)
from gacha_simulator.core.config_toml import load_toml, save_toml


# ══════════════════════════════════════════════════════════════════
# PIPE: add_card 溢出管道（§八.B）
# ══════════════════════════════════════════════════════════════════

def test_pipe_first_time_bonus():
    """PIPE-1: 首次获得触发 first_time_bonus"""
    state = GachaState()
    bands = [OverflowBand(1, 1, {"gem": 10})]
    result = state.add_card("X", path="draw",
                            overflow_bands=bands, initial_counts={})
    assert result == {"gem": 10}
    assert state.get_card_count("X") == 1


def test_pipe_second_time_no_bonus():
    """PIPE-2: 第 2 次获得无产出（间隙）"""
    state = GachaState()
    bands = [OverflowBand(1, 1, {"gem": 10})]
    state.add_card("X", path="draw", overflow_bands=bands, initial_counts={})
    result = state.add_card("X", path="draw", overflow_bands=bands, initial_counts={})
    assert result == {}


def test_pipe_excess_at_threshold():
    """PIPE-3: 第 7 次触发 excess_bonus"""
    state = GachaState()
    bands = [
        OverflowBand(1, 1, {"gem": 10}),
        OverflowBand(7, None, {"star": 25}),
    ]
    # 模拟前 6 次
    for _ in range(6):
        state.add_card("X", path="draw", overflow_bands=bands, initial_counts={"X": 0})
    # 第 7 次
    result = state.add_card("X", path="draw", overflow_bands=bands, initial_counts={"X": 0})
    assert result == {"star": 25}


def test_pipe_with_initial_counts():
    """PIPE-4: initial_counts 正确参与定位——不误判为首次"""
    state = GachaState()
    bands = [
        OverflowBand(1, 1, {"gem": 10}),
        OverflowBand(2, None, {"star": 5}),
    ]
    # 初始持有 3 张 → 首次模拟获得是 total_holding=4
    result = state.add_card("X", path="draw",
                            overflow_bands=bands, initial_counts={"X": 3})
    assert result == {"star": 5}


def test_pipe_missing_initial_counts_raises():
    """PIPE-5: 传 bands 不传 initial_counts → ValueError"""
    state = GachaState()
    bands = [OverflowBand(1, None, {"gem": 40})]
    with pytest.raises(ValueError, match="initial_counts"):
        state.add_card("X", overflow_bands=bands)


def test_pipe_acquired_by_path_recording():
    """PIPE-6: acquired_by_path 正确记录"""
    state = GachaState()
    state.add_card("X", path="draw")
    state.add_card("X", path="draw")
    state.add_card("X", path="milestone_gift")
    assert state.acquired_by_path["X"] == {"draw": 2, "milestone_gift": 1}


def test_pipe_no_bands_backward_compat():
    """PIPE-7: 不传 overflow_bands——向后兼容"""
    state = GachaState()
    result = state.add_card("X")
    assert result == {}
    assert state.get_card_count("X") == 1
    assert state.acquired_by_path["X"]["unknown"] == 1


# ══════════════════════════════════════════════════════════════════
# PRIO: 优先级查找（§八.A）
# ══════════════════════════════════════════════════════════════════

def test_prio_card_overrides_rarity():
    """PRIO-1: 卡片显式配置覆盖稀有度默认"""
    store = ConfigStore()
    store.card_defs = [
        CardDefEntry(card_id="A", rarity="ssr",
                     overflow_bands=[OverflowBand(1, 1, {"gem": 99})]),
    ]
    # 稀有度默认也有配置
    store.rarity_defaults = {
        "ssr": {"overflow_bands": [OverflowBand(1, 1, {"gem": 10})]}
    }
    from gacha_simulator.core.config_toml import _build_card_overflow_map
    _build_card_overflow_map(store)
    # 卡片显式覆盖应优先生效
    assert store.card_overflow_map["A"][0].resources == {"gem": 99}


def test_prio_fallback_to_rarity():
    """PRIO-2: 卡片无配置 → fallback 稀有度默认"""
    store = ConfigStore()
    store.card_defs = [
        CardDefEntry(card_id="B", rarity="ssr", overflow_bands=None),
    ]
    store.rarity_defaults = {
        "ssr": {"overflow_bands": [OverflowBand(1, 1, {"gem": 10})]}
    }
    from gacha_simulator.core.config_toml import _build_card_overflow_map
    _build_card_overflow_map(store)
    assert len(store.card_overflow_map["B"]) == 1
    assert store.card_overflow_map["B"][0].resources == {"gem": 10}


def test_prio_nothing_configured():
    """PRIO-3: 卡片和稀有度都无配置 → 不在 overflow_map 中"""
    store = ConfigStore()
    store.card_defs = [
        CardDefEntry(card_id="C", rarity="r", overflow_bands=None),
    ]
    from gacha_simulator.core.config_toml import _build_card_overflow_map
    _build_card_overflow_map(store)
    assert "C" not in store.card_overflow_map


# ══════════════════════════════════════════════════════════════════
# KEY-NORM: 键名 .lower() 规范化（§八.E GUI-7 / AUDIT-BREAK-2）
# ══════════════════════════════════════════════════════════════════

def test_key_norm_rarity_lower_match():
    """稀有度存储键为小写 → 卡片 rarity.lower() 能正确匹配"""
    store = ConfigStore()
    store.card_defs = [
        CardDefEntry(card_id="X", rarity="SSR", overflow_bands=None),
    ]
    store.rarity_defaults = {
        "ssr": {"overflow_bands": [OverflowBand(1, None, {"gem": 40})]}
    }
    from gacha_simulator.core.config_toml import _build_card_overflow_map
    _build_card_overflow_map(store)
    # rarity="SSR".lower() == "ssr" → 匹配 rarity_defaults["ssr"]
    assert "X" in store.card_overflow_map
    assert store.card_overflow_map["X"][0].resources == {"gem": 40}


def test_key_norm_mixed_case_card_rarity():
    """卡片稀有度为混合大小写（如 'SsR'）→ lower() 后正确匹配"""
    store = ConfigStore()
    store.card_defs = [
        CardDefEntry(card_id="Y", rarity="SsR", overflow_bands=None),
    ]
    store.rarity_defaults = {
        "ssr": {"overflow_bands": [OverflowBand(1, None, {"gem": 40})]}
    }
    from gacha_simulator.core.config_toml import _build_card_overflow_map
    _build_card_overflow_map(store)
    assert "Y" in store.card_overflow_map


# ══════════════════════════════════════════════════════════════════
# CONFIG-RT: 配置 round-trip（§八.A）
# ══════════════════════════════════════════════════════════════════

def test_config_roundtrip_rarity_defaults():
    """稀有度默认配置 load→save→load 往返无损"""
    # 使用实际 config.toml 但通过 load_toml 验证 round-trip
    config_path = os.path.join(
        os.path.dirname(__file__), '..', 'gacha_simulator', 'config', 'config.toml'
    )
    store = load_toml(config_path)

    # 注入稀有度默认规则
    store.rarity_defaults = {
        "ssr": {"overflow_bands": [
            OverflowBand(1, 1, {"exchange_currency": 10}),
            OverflowBand(8, None, {"exchange_currency": 25}),
        ]}
    }
    from gacha_simulator.core.config_toml import _build_card_overflow_map
    _build_card_overflow_map(store)

    # 保存到临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False,
                                     encoding='utf-8') as f:
        tmp_path = f.name
    try:
        save_toml(store, tmp_path)
        store2 = load_toml(tmp_path)

        # 验证 rarity_defaults round-trip
        assert "ssr" in store2.rarity_defaults
        bands = store2.rarity_defaults["ssr"]["overflow_bands"]
        assert len(bands) == 2
        assert bands[0].min == 1
        assert bands[0].max == 1
        assert bands[0].resources == {"exchange_currency": 10}
        assert bands[1].min == 8
        assert bands[1].max is None
        assert bands[1].resources == {"exchange_currency": 25}
    finally:
        os.unlink(tmp_path)


def test_config_roundtrip_card_overflow():
    """卡片溢出配置 load→save→load 往返无损"""
    config_path = os.path.join(
        os.path.dirname(__file__), '..', 'gacha_simulator', 'config', 'config.toml'
    )
    store = load_toml(config_path)

    # 给一张卡配置溢出规则
    for cd in store.card_defs:
        if cd.card_id == "limited_ssr_1":
            cd.overflow_bands = [
                OverflowBand(1, 1, {"gem": 50}),
                OverflowBand(7, None, {"starlight": 25}),
            ]
            break

    from gacha_simulator.core.config_toml import _build_card_overflow_map
    _build_card_overflow_map(store)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False,
                                     encoding='utf-8') as f:
        tmp_path = f.name
    try:
        save_toml(store, tmp_path)
        store2 = load_toml(tmp_path)

        # 验证卡片溢出 round-trip
        found = None
        for cd in store2.card_defs:
            if cd.card_id == "limited_ssr_1":
                found = cd
                break
        assert found is not None
        assert found.overflow_bands is not None
        assert len(found.overflow_bands) == 2
        assert found.overflow_bands[0].resources == {"gem": 50}
        assert found.overflow_bands[1].max is None  # "inf" → None
    finally:
        os.unlink(tmp_path)


# ══════════════════════════════════════════════════════════════════
# REG: 回归——空配置行为不变（§八.C）
# ══════════════════════════════════════════════════════════════════

def test_reg_no_overflow_config_unchanged():
    """REG-1: 空溢出配置时 add_card 行为不变"""
    state = GachaState()
    # 无 bands → 返回 {}，仅计数
    assert state.add_card("any_card") == {}
    assert state.get_card_count("any_card") == 1


def test_reg_clone_preserves_path():
    """clone() 保留 acquired_by_path"""
    state = GachaState()
    state.add_card("X", path="draw")
    state.add_card("X", path="milestone_gift")
    clone = state.clone()
    assert clone.acquired_by_path == {"X": {"draw": 1, "milestone_gift": 1}}
    # 修改 clone 不影响原始
    clone.add_card("X", path="draw")
    assert state.acquired_by_path["X"]["draw"] == 1
    assert clone.acquired_by_path["X"]["draw"] == 2


# ══════════════════════════════════════════════════════════════════
# GUI 展开逻辑（§三.9 四种组合映射）
# ══════════════════════════════════════════════════════════════════

def test_expand_full_combo():
    """首次 + 满突前 + 满突后——三段表"""
    from gacha_simulator.gui.config_panel import ConfigPanel
    panel = ConfigPanel.__new__(ConfigPanel)
    bands = panel._expand_fields_to_bands(
        first={"gem": 10},
        threshold=7,
        pre_excess={"gem": 5},
        post_excess={"gem": 25},
    )
    assert bands is not None
    assert len(bands) == 3
    assert match_overflow_bands(bands, 1) == {"gem": 10}
    assert match_overflow_bands(bands, 3) == {"gem": 5}
    assert match_overflow_bands(bands, 7) == {"gem": 25}


def test_expand_no_first():
    """无首次、有满突张数 + 满突前 + 满突后——两段表"""
    from gacha_simulator.gui.config_panel import ConfigPanel
    panel = ConfigPanel.__new__(ConfigPanel)
    bands = panel._expand_fields_to_bands(
        first={},
        threshold=7,
        pre_excess={"gem": 5},
        post_excess={"gem": 25},
    )
    assert bands is not None
    assert len(bands) == 2
    assert match_overflow_bands(bands, 1) == {"gem": 5}
    assert match_overflow_bands(bands, 7) == {"gem": 25}


def test_expand_constant_single():
    """仅有满突前、无张数——恒真单段 [1,∞)"""
    from gacha_simulator.gui.config_panel import ConfigPanel
    panel = ConfigPanel.__new__(ConfigPanel)
    bands = panel._expand_fields_to_bands(
        first={},
        threshold=None,
        pre_excess={"gem": 40},
        post_excess={},
    )
    assert bands is not None
    assert len(bands) == 1
    assert bands[0].max is None
    assert match_overflow_bands(bands, 1) == {"gem": 40}
    assert match_overflow_bands(bands, 100) == {"gem": 40}


def test_expand_all_empty():
    """全空 → 无溢出规则"""
    from gacha_simulator.gui.config_panel import ConfigPanel
    panel = ConfigPanel.__new__(ConfigPanel)
    bands = panel._expand_fields_to_bands(
        first={}, threshold=None, pre_excess={}, post_excess={}
    )
    assert bands is None
