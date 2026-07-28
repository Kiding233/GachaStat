"""P56 阶段十三-b扩展：6 种 P56 保底类型的 TOML 解析 + round-trip + 错误配置拒收测试。

覆盖目标：
  1. 6 个新 type 的 TOML 解析 + round-trip
  2. deactivate_on_early_hit=true 与 type≠hard 的 ConfigError
  3. depends_on 引用不存在的名称 → ConfigError
"""

import pytest
import tempfile
import os
from gacha_simulator.core.config_toml import load_toml, save_toml, ConfigError


# ══════════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════════

_BASE_TOML = """[meta]
version = "2.3.0"

[rarities]
ranks = [
    ["SSR"],
    ["SR"],
    ["R"],
]

[[pools]]
id = "test_pool"
name = "测试池"
pool_type = "角色"
start_day = 0
end_day = 21
cost = "draw_resource:160"

[[pools.distribution]]
card_id = "c1"
probability = 0.5
rarity = "SSR"
featured = true

[[pools.distribution]]
card_id = "c2"
probability = 0.5
rarity = "SSR"
featured = false
"""


def _write_and_load(toml_str):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml',
                                      delete=False, encoding='utf-8') as f:
        f.write(toml_str)
        path = f.name
    try:
        return load_toml(path), path
    except Exception:
        os.unlink(path)
        raise


def _roundtrip(store, tmp_path):
    """TOML → Store → TOML → Store2，返回 (store, store2)。"""
    save_toml(store, tmp_path)
    return load_toml(tmp_path)


def _pity_section(btype, name, **extra):
    """构造 [[pity]] 段。"""
    lines = [
        '[[pity]]',
        f'name = "{name}"',
        f'type = "{btype}"',
        'scope = "ssr"',
    ]
    for k, v in extra.items():
        if isinstance(v, bool):
            lines.append(f'{k} = {str(v).lower()}')
        elif isinstance(v, list):
            lines.append(f'{k} = {v}')
        elif isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        else:
            lines.append(f'{k} = {v}')
    return '\n'.join(lines) + '\n'


# ══════════════════════════════════════════════════════════════════
# 6 种 P56 type 解析 + round-trip
# ══════════════════════════════════════════════════════════════════

class TestP56TypeParsing:
    """6 种新 type 的 TOML 解析正确性。"""

    @pytest.mark.parametrize("btype,extra", [
        ('rotating', {}),
        ('rotating_soft', {'soft_start': 74, 'soft_end': 90}),
        ('rotating_cr', {'cr_counter_threshold': 3, 'cr_base_rate': 0.00018,
                          'cr_state_probs': [0.0, 0.0, 0.0, 1.0]}),
        ('rotating_cr_soft', {'soft_start': 74, 'soft_end': 90,
                               'cr_counter_threshold': 3,
                               'cr_state_probs': [0.0, 0.0, 0.0, 1.0]}),
        ('targeted', {'fate_threshold': 1, 'switch_allowed': True,
                       'switch_resets_progress': True}),
        ('targeted_soft', {'soft_start': 63, 'soft_end': 80,
                            'fate_threshold': 1}),
    ])
    def test_parse_p56_type(self, btype, extra):
        """每种 P56 type 可被正确解析。"""
        toml = _BASE_TOML + _pity_section(btype, f'pity_{btype}', **extra)
        store, path = _write_and_load(toml)
        try:
            assert len(store.pity.pities) == 1
            pdef = store.pity.pities[0]
            assert pdef.btype == btype
            assert pdef.scope == 'ssr'
        finally:
            os.unlink(path)

    @pytest.mark.parametrize("btype,extra", [
        ('rotating', {}),
        ('rotating_soft', {'soft_start': 74, 'soft_end': 90}),
        ('rotating_cr', {'cr_counter_threshold': 3,
                          'cr_state_probs': [0.0, 0.0, 0.0, 1.0]}),
        ('rotating_cr_soft', {'soft_start': 74, 'soft_end': 90,
                               'cr_counter_threshold': 3,
                               'cr_state_probs': [0.0, 0.0, 0.0, 1.0]}),
        ('targeted', {'fate_threshold': 1}),
        ('targeted_soft', {'soft_start': 63, 'soft_end': 80,
                            'fate_threshold': 1}),
    ])
    def test_roundtrip_p56_type(self, btype, extra):
        """每种 P56 type round-trip 后字段保持一致。"""
        toml = _BASE_TOML + _pity_section(btype, f'pity_{btype}', **extra)
        store, path = _write_and_load(toml)
        try:
            store2 = _roundtrip(store, path)
            assert len(store2.pity.pities) == 1
            pdef2 = store2.pity.pities[0]
            assert pdef2.btype == btype
            assert pdef2.scope == 'ssr'
            assert pdef2.name == f'pity_{btype}'
        finally:
            os.unlink(path)


# ══════════════════════════════════════════════════════════════════
# P56 专属字段解析
# ══════════════════════════════════════════════════════════════════

class TestP56FieldParsing:
    """P56 专属字段（cr_counter_threshold / fate_threshold / switch 等）解析正确。"""

    def test_rotating_cr_fields_parsed(self):
        toml = _BASE_TOML + _pity_section(
            'rotating_cr', 'cr_test',
            cr_counter_threshold=5, cr_base_rate=0.001,
            cr_state_probs=[0.0, 0.1, 0.3, 0.6, 0.9, 1.0],
        )
        store, path = _write_and_load(toml)
        try:
            pdef = store.pity.pities[0]
            assert pdef.cr_counter_threshold == 5
            assert pdef.cr_base_rate == 0.001
            assert list(pdef.cr_state_probs) == [0.0, 0.1, 0.3, 0.6, 0.9, 1.0]
        finally:
            os.unlink(path)

    def test_targeted_fields_parsed(self):
        toml = _BASE_TOML + _pity_section(
            'targeted', 'tgt_test',
            fate_threshold=2, switch_allowed=False,
            switch_resets_progress=False,
        )
        store, path = _write_and_load(toml)
        try:
            pdef = store.pity.pities[0]
            assert pdef.fate_threshold == 2
            assert pdef.switch_allowed is False
            assert pdef.switch_resets_progress is False
        finally:
            os.unlink(path)

    def test_guaranteed_init_parsed(self):
        toml = _BASE_TOML + _pity_section(
            'rotating', 'rot_test', guaranteed_init=True,
        )
        store, path = _write_and_load(toml)
        try:
            pdef = store.pity.pities[0]
            assert pdef.guaranteed_init is True
        finally:
            os.unlink(path)

    def test_fate_points_init_parsed(self):
        toml = _BASE_TOML + _pity_section(
            'targeted', 'tgt_test', fate_points_init=2,
        )
        store, path = _write_and_load(toml)
        try:
            pdef = store.pity.pities[0]
            assert pdef.fate_points_init == 2
        finally:
            os.unlink(path)


# ══════════════════════════════════════════════════════════════════
# 错误配置拒收
# ══════════════════════════════════════════════════════════════════

class TestP56ConfigRejection:
    """无效 P56 配置 → ConfigError。"""

    def test_deactivate_on_early_hit_rejected_for_rotating(self):
        """deactivate_on_early_hit=true + type=rotating → ConfigError（事件驱动型不支持）。"""
        toml = _BASE_TOML + '''[[pity]]
name = "bad_rot"
type = "rotating"
scope = "ssr"

[pity.lifecycle]
deactivate_on_early_hit = true
'''
        with pytest.raises(ConfigError, match='deactivate_on_early_hit'):
            _write_and_load(toml)

    def test_deactivate_on_early_hit_rejected_for_targeted(self):
        """deactivate_on_early_hit=true + type=targeted → ConfigError（事件驱动型不支持）。"""
        toml = _BASE_TOML + '''[[pity]]
name = "bad_tgt"
type = "targeted"
scope = "ssr"
fate_threshold = 1

[pity.lifecycle]
deactivate_on_early_hit = true
'''
        with pytest.raises(ConfigError, match='deactivate_on_early_hit'):
            _write_and_load(toml)

    def test_deactivate_on_early_hit_allowed_for_soft_interval(self):
        """deactivate_on_early_hit=true + type=soft_interval → 允许（counter 驱动型）。"""
        toml = _BASE_TOML + '''[[pity]]
name = "ok_soft"
type = "soft_interval"
scope = "ssr"
soft_start = 73
soft_end = 90

[pity.lifecycle]
deactivate_on_early_hit = true
'''
        store, path = _write_and_load(toml)
        try:
            assert store.pity.pities[0].deactivate_on_early_hit is True
        finally:
            os.unlink(path)

    def test_epitomizable_card_not_in_distribution(self):
        """epitomizable_cards 中 card_id 不在 distribution → ConfigError。"""
        toml = _BASE_TOML.replace('"c2"', '"c3"') + '''
[[pools]]
id = "bad_pool"
name = "坏池子"
pool_type = "武器"
start_day = 21
end_day = 42
cost = "draw_resource:160"
epitomizable_cards = ["nonexistent"]

[[pools.distribution]]
card_id = "bad"
probability = 1.0
rarity = "SSR"
featured = true
'''
        with pytest.raises(ConfigError, match='epitomizable_cards'):
            store, path = _write_and_load(toml)
            os.unlink(path)


# ══════════════════════════════════════════════════════════════════
# 新旧混用兼容
# ══════════════════════════════════════════════════════════════════

class TestMixedPityCompat:
    """P56 + P55 新旧保底条目共存——不互相干扰。"""

    def test_counter_and_event_pities_coexist(self):
        toml = (_BASE_TOML +
                _pity_section('soft_interval', 'soft73', soft_start=73, soft_end=90) +
                _pity_section('rotating', 'rot_char') +
                _pity_section('hard', 'hard180', threshold=180))
        store, path = _write_and_load(toml)
        try:
            assert len(store.pity.pities) == 3
            btypes = {p.btype for p in store.pity.pities}
            assert btypes == {'soft_interval', 'rotating', 'hard'}
        finally:
            os.unlink(path)

    def test_all_10_types_roundtrip(self):
        """全部 10 种 type 共存 → round-trip 保持每种 type。"""
        all_pities = (
            _pity_section('soft_interval', 'p1', soft_start=73, soft_end=90) +
            _pity_section('soft_additive', 'p2', soft_start=73) +
            _pity_section('soft_step', 'p3') +
            _pity_section('hard', 'p4', threshold=90) +
            _pity_section('rotating', 'p5') +
            _pity_section('rotating_soft', 'p6', soft_start=74, soft_end=90) +
            _pity_section('rotating_cr', 'p7', cr_counter_threshold=3,
                           cr_state_probs=[0.0, 0.0, 0.0, 1.0]) +
            _pity_section('rotating_cr_soft', 'p8', soft_start=74, soft_end=90,
                           cr_counter_threshold=3,
                           cr_state_probs=[0.0, 0.0, 0.0, 1.0]) +
            _pity_section('targeted', 'p9', fate_threshold=1) +
            _pity_section('targeted_soft', 'p10', soft_start=63, soft_end=80,
                           fate_threshold=1)
        )
        toml = _BASE_TOML + all_pities
        store, path = _write_and_load(toml)
        try:
            assert len(store.pity.pities) == 10
            store2 = _roundtrip(store, path)
            assert len(store2.pity.pities) == 10
            btypes1 = sorted(p.btype for p in store.pity.pities)
            btypes2 = sorted(p.btype for p in store2.pity.pities)
            assert btypes1 == btypes2
        finally:
            os.unlink(path)
