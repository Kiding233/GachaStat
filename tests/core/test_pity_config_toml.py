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

[[banner]]
id = "test_pool"
name = "测试池"
start_day = 0
end_day = 21

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "c1"
probability = 0.5
rarity = "SSR"
featured = true

[[banner.pool.reward]]
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
        ('rotating_soft', {'start': 74, 'end': 90}),
        ('rotating_cr', {'cr_counter_threshold': 3, 'cr_base_rate': 0.00018,
                          'cr_state_probs': [0.0, 0.0, 0.0, 1.0]}),
        ('rotating_cr_soft', {'start': 74, 'end': 90,
                               'cr_counter_threshold': 3,
                               'cr_state_probs': [0.0, 0.0, 0.0, 1.0]}),
        ('targeted', {'fate_threshold': 1, 'switch_allowed': True,
                       'switch_resets_progress': True}),
        ('targeted_soft', {'start': 63, 'end': 80,
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
            # 软保底参数必须真的落进 deltas（TOML 键名为 start/end/increment，
            # 写成字段名 soft_start 会被解析器静默忽略）
            if 'start' in extra:
                assert pdef.soft_start == extra['start']
                assert pdef.soft_end == extra.get('end')
                # 后缀型的 deltas 由 SoftPityMixin 在 create_behavior() 时展开，
                # 不经 PityDef.deltas；非后缀型在 _build_pity 即展开。
                if btype in ('rotating_soft', 'rotating_cr_soft', 'targeted_soft'):
                    assert pdef.deltas is None
                else:
                    assert pdef.deltas is not None
            else:
                assert pdef.deltas is None, '未给 start 的条目不应产出 deltas'
        finally:
            os.unlink(path)

    @pytest.mark.parametrize("btype,extra", [
        ('rotating', {}),
        ('rotating_soft', {'start': 74, 'end': 90}),
        ('rotating_cr', {'cr_counter_threshold': 3,
                          'cr_state_probs': [0.0, 0.0, 0.0, 1.0]}),
        ('rotating_cr_soft', {'start': 74, 'end': 90,
                               'cr_counter_threshold': 3,
                               'cr_state_probs': [0.0, 0.0, 0.0, 1.0]}),
        ('targeted', {'fate_threshold': 1}),
        ('targeted_soft', {'start': 63, 'end': 80,
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
            # 软保底语法糖参数与展开后的 deltas 均须保值
            src_p = store.pity.pities[0]
            assert pdef2.soft_start == src_p.soft_start
            assert pdef2.soft_end == src_p.soft_end
            assert pdef2.soft_increment == src_p.soft_increment
            assert pdef2.deltas == src_p.deltas
            if 'start' in extra:
                assert pdef2.soft_start == extra['start']
                assert pdef2.soft_end == extra.get('end')
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
start = 73
end = 90

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
[[banner]]
id = "bad_pool"
name = "坏池子"
start_day = 21
end_day = 42

[[banner.pool]]
id = "main"
cost = "draw_resource:160"
epitomizable_cards = ["nonexistent"]

[[banner.pool.reward]]
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
                _pity_section('soft_interval', 'soft73', start=73, end=90) +
                _pity_section('rotating', 'rot_char') +
                _pity_section('hard', 'hard180', threshold=180))
        store, path = _write_and_load(toml)
        try:
            assert len(store.pity.pities) == 3
            btypes = {p.btype for p in store.pity.pities}
            assert btypes == {'soft_interval', 'rotating', 'hard'}
            soft = next(p for p in store.pity.pities if p.btype == 'soft_interval')
            assert soft.deltas == ((72, 0.0), (18, 5.555556))
        finally:
            os.unlink(path)

    def test_all_10_types_roundtrip(self):
        """全部 10 种 type 共存 → round-trip 保持每种 type。"""
        all_pities = (
            _pity_section('soft_interval', 'p1', start=73, end=90) +
            _pity_section('soft_additive', 'p2', start=73) +
            _pity_section('soft_step', 'p3') +
            _pity_section('hard', 'p4', threshold=90) +
            _pity_section('rotating', 'p5') +
            _pity_section('rotating_soft', 'p6', start=74, end=90) +
            _pity_section('rotating_cr', 'p7', cr_counter_threshold=3,
                           cr_state_probs=[0.0, 0.0, 0.0, 1.0]) +
            _pity_section('rotating_cr_soft', 'p8', start=74, end=90,
                           cr_counter_threshold=3,
                           cr_state_probs=[0.0, 0.0, 0.0, 1.0]) +
            _pity_section('targeted', 'p9', fate_threshold=1) +
            _pity_section('targeted_soft', 'p10', start=63, end=80,
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
            # 逐条 deltas 保值（软保底语法糖不被往返改写）。
            # 只有 soft_interval / soft_additive 在 _build_pity 展开到
            # PityDef.deltas；三种 *_soft 后缀型由 SoftPityMixin 在
            # create_behavior 时另经 soft_start/soft_end 展开，故此处为 None。
            d1 = {p.name: p.deltas for p in store.pity.pities}
            d2 = {p.name: p.deltas for p in store2.pity.pities}
            assert d1 == d2
            assert {k for k, v in d1.items() if v is not None} == {'p1', 'p2'}
            # 后缀型：语法糖参数须保值（mixin 展开的唯一依据）
            sfx1 = {p.name: (p.soft_start, p.soft_end) for p in store.pity.pities
                    if p.btype.endswith('_soft')}
            sfx2 = {p.name: (p.soft_start, p.soft_end) for p in store2.pity.pities
                    if p.btype.endswith('_soft')}
            assert sfx1 == sfx2 == {'p6': (74, 90), 'p8': (74, 90), 'p10': (63, 80)}
        finally:
            os.unlink(path)


# ══════════════════════════════════════════════════════════════════
# §3.4.1 修正 ①②：软保底语法糖的生产写回路径 round-trip
# ══════════════════════════════════════════════════════════════════

class TestSoftSugarRoundTrip:
    """load_toml → save_toml → load_toml 后语法糖参数逐字段保值。

    生产写回（_pitydef_to_toml）直接取 PityDef.soft_start / soft_end /
    soft_increment，不经 _deltas_to_soft_interval，故这里钉住的是
    「语法糖参数不被 deltas 往返改写」这一条。对应 GUI 的
    main_window 载入 → 保存 路径。
    """

    def test_soft_interval_start_end_preserved(self):
        toml = _BASE_TOML + _pity_section('soft_interval', 'si',
                                          start=80, end=90)
        store, path = _write_and_load(toml)
        try:
            p = store.pity.pities[0]
            assert p.deltas == ((79, 0.0), (11, 9.090909))  # 首段 = start-1，档数 = end-start+1
            p2 = _roundtrip(store, path).pity.pities[0]
            assert (p2.soft_start, p2.soft_end) == (80, 90)
            assert p2.soft_increment is None
            assert p2.deltas == p.deltas
        finally:
            os.unlink(path)

    def test_soft_additive_start_increment_preserved(self):
        toml = _BASE_TOML + _pity_section('soft_additive', 'sa',
                                          start=65, increment=6.0)
        store, path = _write_and_load(toml)
        try:
            p = store.pity.pities[0]
            assert p.deltas == ((64, 0.0), (17, 6.0))  # 首段 = start-1
            p2 = _roundtrip(store, path).pity.pities[0]
            assert (p2.soft_start, p2.soft_increment) == (65, 6.0)
            assert p2.deltas == p.deltas
        finally:
            os.unlink(path)

    def test_soft_suffix_start_end_preserved(self):
        """后缀型（rotating_soft / targeted_soft / rotating_cr_soft）的软保底
        参数不经 PityDef.deltas 展开，须由 writer 独立写回。

        修前这三项被丢弃，重载后落到注册表默认值（start=74 / end=90），
        用户配置被静默改写。
        """
        for btype, extra in [('rotating_soft', dict(start=63, end=80)),
                             ('targeted_soft', dict(start=50, end=70,
                                                    fate_threshold=1)),
                             ('rotating_cr_soft', dict(start=63, end=80,
                                                       cr_counter_threshold=3))]:
            toml = _BASE_TOML + _pity_section(btype, 'x', **extra)
            store, path = _write_and_load(toml)
            try:
                p = store.pity.pities[0]
                assert p.deltas is None  # 后缀型不走 PityDef.deltas
                p2 = _roundtrip(store, path).pity.pities[0]
                assert (p2.soft_start, p2.soft_end) == (extra['start'], extra['end'])
                assert p2.soft_increment is None
            finally:
                os.unlink(path)

    def test_soft_suffix_raw_deltas_preserved(self):
        """后缀型直写 deltas 时，PityDef.deltas 非 None，走既有 deltas 分支写回。"""
        toml = _BASE_TOML + _pity_section('rotating_soft', 'x',
                                          deltas=[[62, 0.0], [17, 5.882353]])
        store, path = _write_and_load(toml)
        try:
            p = store.pity.pities[0]
            assert p.deltas == ((62, 0.0), (17, 5.882353))
            p2 = _roundtrip(store, path).pity.pities[0]
            assert p2.deltas == p.deltas
            assert p2.soft_start is None
        finally:
            os.unlink(path)

    def test_raw_deltas_preserved(self):
        toml = _BASE_TOML + _pity_section('soft_interval', 'raw',
                                          deltas=[[79, 0.0], [10, 10.0]])
        store, path = _write_and_load(toml)
        try:
            p = store.pity.pities[0]
            assert p.deltas == ((79, 0.0), (10, 10.0))
            p2 = _roundtrip(store, path).pity.pities[0]
            assert p2.deltas == p.deltas
        finally:
            os.unlink(path)


# ══════════════════════════════════════════════════════════════════
# 跨模块重复常量的漂移守卫
# ══════════════════════════════════════════════════════════════════

class TestDuplicatedConstants:
    """同名集合在 pity.py 与 config_toml.py 各存一份，此处钉住相等。

    P64 计划要把它们升为 `pity_primitives.py` 的模块级常量（未实施）；
    在那之前，两份拷贝靠本断言防漂移（2026-10-06 独立审查提出）。
    """

    def test_soft_suffix_types_match(self):
        from gacha_simulator.core.pity import CounterBasedBehavior
        from gacha_simulator.core import config_toml
        assert (config_toml._SOFT_SUFFIX_TYPES
                == CounterBasedBehavior._SOFT_SUFFIX_TYPES)

    def test_event_driven_types_match(self):
        from gacha_simulator.core.pity import CounterBasedBehavior
        from gacha_simulator.core import config_toml
        assert (config_toml._EVENT_DRIVEN_TYPES
                == CounterBasedBehavior._EVENT_DRIVEN_TYPES)
# ══════════════════════════════════════════════════════════════════
# P64 G16-1 / ISSUE-928：`[[pity]].reset` 取值白名单
# ══════════════════════════════════════════════════════════════════
# 白名单 = 空串 / `featured` / 稀有度名（`[rarities].ranks` 的键）/ `never`，
# 其余取值一律抛 `ConfigError`。被测面是 `_build_pity` 的校验分支与其取值来源
# `legal_reset_values()`；未知值（含拼写错误如 `'nevr'`）在旧实现里经
# `_should_reset` 的兜底分支（`reward_rarity == reset`）恒为 False，即**静默
# 等价于 `never`**，两种语义不可区分、也不报错。

_TOML_EXTRA_RARITY = _BASE_TOML.replace('    ["R"],\n',
                                        '    ["R"],\n    ["UR"],\n', 1)
# 形态守卫**不落模块级**：模块级 `assert` 在 import 期失败，会让本文件全部用例
# 在收集期 ERROR（连带掩盖其余用例的真实信号）。守卫移入其唯一消费者
# test_reset_whitelist_tracks_rarity_ranks，失败面与该用例一一对应。


class TestResetValueWhitelist:
    """`reset` 取值白名单（G16-1 的硬拒面）。"""

    @staticmethod
    def _load(reset_value):
        toml = _BASE_TOML + _pity_section('hard', 'h1', threshold=90,
                                          reset=reset_value)
        return _write_and_load(toml)

    @pytest.mark.parametrize('reset_value',
                             ['', 'featured', 'never', 'ssr', 'sr', 'r'],
                             ids=['empty', 'featured', 'never', 'ssr', 'sr', 'r'])
    def test_reset_whitelist_accepts_legal_values(self, reset_value):
        """四类合法取值（空串 / featured / 稀有度名 / never）均可载入。"""
        store, path = self._load(reset_value)
        try:
            assert store.pity.pities[0].reset == reset_value
        finally:
            os.unlink(path)

    @pytest.mark.parametrize('reset_value',
                             ['nevr', 'any_ssr', 'featured_ssr', 'ur'])
    def test_reset_whitelist_rejects_unknown_value(self, reset_value):
        """未知值一律抛 `ConfigError`。

        四个样本各有出处：`'nevr'` 是拼写错误（与 `never` 一字之差）、
        `'any_ssr'` 是 G16-1 前 GUI 兜底条目用的旧取值、`'featured_ssr'` 是
        legacy TOML 的 reset 值、`'ur'` 是本配置 `[rarities].ranks` 未注册的
        稀有度名（白名单随 ranks 浮动）。
        """
        with pytest.raises(ConfigError, match='reset'):
            self._load(reset_value)

    def test_reset_whitelist_normalizes_case(self):
        """大小写归一（与上方 `scope` 白名单同形态）：`reset='SSR'` 落为 `'ssr'`。"""
        store, path = self._load('SSR')
        try:
            assert store.pity.pities[0].reset == 'ssr'
        finally:
            os.unlink(path)

    def test_reset_whitelist_error_names_value_and_available(self):
        """异常信息同时含出错取值与可用取值（与 `scope` 白名单同层同形态）。"""
        with pytest.raises(ConfigError) as ei:
            self._load('nevr')
        msg = str(ei.value)
        assert "'nevr'" in msg, msg
        assert "'never'" in msg, msg          # 可用取值列表须能看出「永不重置」
        assert "'featured'" in msg, msg

    def test_reset_whitelist_tracks_rarity_ranks(self):
        """取值集合随 `[rarities].ranks` 浮动：该表新增 `UR` 后 `reset='ur'` 放行。"""
        msg = '_BASE_TOML 的 [rarities] 形态变了，本用例随即失效'
        assert '["UR"]' in _TOML_EXTRA_RARITY, msg
        toml = (_TOML_EXTRA_RARITY +
                _pity_section('hard', 'h1', threshold=90, reset='ur'))
        store, path = _write_and_load(toml)
        try:
            assert store.pity.pities[0].reset == 'ur'
        finally:
            os.unlink(path)

    def test_reset_whitelist_shared_with_legal_reset_values(self):
        """取值集合与 `legal_reset_values()` 同源（白名单不在两处各写一份）。"""
        from gacha_simulator.core.config_toml import legal_reset_values

        assert legal_reset_values({'ssr': 0, 'sr': 1, 'r': 2}) == {
            '', 'featured', 'never', 'ssr', 'sr', 'r'}
