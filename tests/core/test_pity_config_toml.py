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

#: 生命周期子表段（S6a / H3 的接受面用例共用）。单独成常量而非三处内联，
#: 避免改一处漏两处。
_LIFECYCLE_DOA = '\n[pity.lifecycle]\ndeactivate_on_early_hit = true\n'



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
    """无效 P56 配置 → ConfigError。

    **P64 S6a（H3）收窄本类**：原 `test_deactivate_on_early_hit_rejected_for_rotating`
    与 `..._for_targeted` 两条正断言（事件驱动型 + `deactivate_on_early_hit` 必抛）
    已随拒绝分支一并删除，改写为接受面用例并移入 `TestS6aLifecycleAcceptance`。
    保留的用例与本类名一致（确为「无效配置」）。
    """


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


# ══════════════════════════════════════════════════════════════════
# P64 S6a（H3）：`deactivate_on_early_hit` 对全部类型开放
# ══════════════════════════════════════════════════════════════════
# P56 起 `_build_pity` 对「事件驱动型 + deactivate_on_early_hit=true」硬拒，
# 理由是「事件驱动型没有阈值前提前命中的概念」。P64 的 Lifecycle（§3.1.3）把退役
# 判定统一为 `should_deactivate(ctx, state, name, fired)`，第四实参 `fired` 取
# `any(tr.did_reset(...))`（M4 统一语义，§3.1.1），对全部类型同形，故 S6a 删除
# 该拒绝分支。**接受面只增不减**，M1 等价性口径不受影响（旧配置行为不变）。

class TestS6aLifecycleAcceptance:
    """事件驱动型 + `deactivate_on_early_hit` 的接受面与写回面（S6a / H3）。"""

    @pytest.mark.parametrize('btype,extra', [
        ('rotating', {}),
        ('targeted', {'fate_threshold': 1}),
        # S6a 新增类型：本行同时证明「新 type 的 `[[pity]]` 段不被契约表硬拒」
        ('rotating_inverse', {}),
    ])
    def test_event_driven_accepts_deactivate_on_early_hit(self, btype, extra):
        """不抛，且配置**真的生效**（`PityDef` 字段为 True，非静默落回默认）。

        只断言「不抛」不足以覆盖：拒绝分支若被改成 `p.get(...)` 取值丢弃，
        同样不抛而配置静默失效。故必须回读 `PityDef`。
        """
        toml = _BASE_TOML + _pity_section(btype, 'ok_ev', **extra)
        toml += _LIFECYCLE_DOA
        store, path = _write_and_load(toml)
        try:
            assert store.pity.pities[0].deactivate_on_early_hit is True, btype
        finally:
            os.unlink(path)

    def test_deactivate_on_early_hit_roundtrip_for_event_driven(self):
        """写盘 → 重载后仍为 True（写侧对事件驱动型照写、读侧照收）。

        `_pitydef_to_toml` 的生命周期段是**无条件逐字段书写**（不看 btype），
        S4c 起产出还要过键契约过滤；`lifecycle.*` 两个键对全部 btype 放行，
        故本闭环应成立。缺本用例时，「写侧写了、读侧删了」这种半改状态不可见。
        """
        toml = _BASE_TOML + _pity_section('rotating', 'rt_ev')
        toml += _LIFECYCLE_DOA
        store, path = _write_and_load(toml)
        try:
            # 复用同一路径（与本文件既有 `_roundtrip(store, path)` 调用同形）
            store2 = _roundtrip(store, path)
            assert store2.pity.pities[0].deactivate_on_early_hit is True
        finally:
            os.unlink(path)

    def test_deactivate_on_early_hit_allowed_for_soft_interval(self):
        """counter 驱动型的接受面**未被 S6a 改动**（回归守卫）。"""
        toml = _BASE_TOML + _pity_section('soft_interval', 'ok_soft',
                                          start=73, end=90)
        toml += _LIFECYCLE_DOA
        store, path = _write_and_load(toml)
        try:
            assert store.pity.pities[0].deactivate_on_early_hit is True
        finally:
            os.unlink(path)

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

    P64 S1a 已把 pity 侧的 `_SOFT_TYPES` / `_HARD_TYPES` / `_EVENT_DRIVEN_TYPES`
    升为 `pity_primitives.py` 的模块级常量，`CounterBasedBehavior` 的同名类属性
    自此是它们的**同对象别名**；`_SOFT_SUFFIX_TYPES` 不在迁移面内，仍是类属性。
    被测侧两侧本步都动过（存放位置 + `config_toml` 拷贝的内容），故本组断言仍是
    防漂移守卫，**不得删、也不得改成「剔除 rotating_inverse 后相等」**——两种做法
    都会让它失去检测力（AUDIT-BREAK-10）。
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
# 白名单 = 空串 / `featured` / 稀有度名（`[rarities].ranks` 的键）/ `never` /
# `on_effective`（2026-10-15 用户裁定新增；**取值面**合法，**类型面**另有
# `create_behavior` 的硬拒，只有阈值触发型可用，见 `test_pity_reset_on_effective.py`），
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
                             ['', 'featured', 'never', 'on_effective', 'ssr', 'sr', 'r'],
                             ids=['empty', 'featured', 'never', 'on_effective',
                                  'ssr', 'sr', 'r'])
    def test_reset_whitelist_accepts_legal_values(self, reset_value):
        """五类合法取值（空串 / featured / 稀有度名 / never / on_effective）均可载入。

        **`on_effective` 只验取值面**：`_build_pity` 的白名单是取值面，类型面
        （哪些 type 真正可用）由 `create_behavior` 的硬拒把关，故本用例的
        `type = "hard"` 是合法组合；非阈值触发型配该取值必抛的负例见
        `test_pity_reset_on_effective.py::TestTypeWhitelist`。
        """
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
        """取值集合与 `legal_reset_values()` 同源（白名单不在两处各写一份）。

        **集合快照随语义变更更新（2026-10-15）**：`'on_effective'` 由用户裁定
        新增（幻塔「每 N 抽白送一个」的等价表达），故本断言的内容快照随之增加
        一项。这是**语义变更的预期更新**而非放宽判据：断言仍是精确集合相等
        （既拦「少一项」也拦「多一项」），且 `'nevr'` / `'any_ssr'` /
        `'featured_ssr'` 的拒收用例未动。
        """
        from gacha_simulator.core.config_toml import legal_reset_values

        assert legal_reset_values({'ssr': 0, 'sr': 1, 'r': 2}) == {
            '', 'featured', 'never', 'on_effective', 'ssr', 'sr', 'r'}


# ══════════════════════════════════════════════════════════════════
# P64 S4b：`priority` 字段的解析 + round-trip 写回（G5 / ISSUE-923）
# ══════════════════════════════════════════════════════════════════
# `_pitydef_to_toml` 是**条件式逐字段书写**，不会自动带上任何新字段：不补写回，
# 「GUI 加载 → 保存」一次即把手写的 `priority` 从 TOML 抹掉（默认 0 与缺键在解析
# 侧等价，故丢失无任何报错）。

def _all_fields_non_default_pitydef():
    """全部字段非默认值的 `PityDef`（字段集由 dataclasses 现取，见同批守卫）。"""
    from gacha_simulator.core.config_store import PityDef

    return PityDef(
        name='p1', btype='soft_interval', scope='ssr', target_featured=True,
        deltas=((74, 0.0), (16, 6.25)), threshold=90, counter_init=3,
        guaranteed_init=True, fate_points_init=2, selected_card_init='up_a',
        soft_start=74, soft_end=90, soft_increment=6.25,
        soft_deltas=((74, 0.0), (16, 6.25)), cr_counter_threshold=3,
        cr_base_rate=0.018, cr_state_probs=(0.0, 0.0, 0.0, 1.0), fate_threshold=1,
        switch_allowed=False, switch_resets_progress=False, pools=('test_pool.main',),
        deactivate_on_early_hit=True, depends_on='other', max_triggers=2,
        reset='featured', priority=5,
    )


# ══════════════════════════════════════════════════════════════════
# P64 S4c：`[[pity]]` 键契约的一致性测试与硬拒用例
# ══════════════════════════════════════════════════════════════════
# 契约源是 `config_toml._PITY_COMMON_KEYS` / `._PITY_TYPE_KEYS`（全篇唯一契约源，
# 扩表编辑点见该处注释）。本组钉住三件事：
#   ① 每个 btype 的「全量键 fixture」经 `_pitydef_to_toml` 的产出键集**恰等于**
#      该 btype 的契约（双向：既不产出未声明键，也不漏产已声明键）；
#   ② 契约 ⊆ `_build_pity` 的**读取面**（读侧不认的键写进表里 = 幽灵键）；
#   ③ 未声明键在加载期硬拒，且错误信息点名该键与合法键集。

# TOML 键 → (PityDef 字段, 非默认值)。与 `_pitydef_to_toml` 的写回分支一一对应；
# `deltas` / `soft_deltas` 不在此表（形态互斥，由 `_pitydef_from_contract` 处理），
# `lifecycle` 也不是字段（嵌套键各自映射到 `deactivate_on_early_hit` / `depends_on`）。
_PITY_KEY_TO_FIELD = {
    'priority': ('priority', 5),
    'max_triggers': ('max_triggers', 2),
    'target_featured': ('target_featured', True),
    'reset': ('reset', 'featured'),
    'pools': ('pools', ('test_pool.main',)),
    'counter_init': ('counter_init', 3),
    'guaranteed_init': ('guaranteed_init', True),
    'fate_points_init': ('fate_points_init', 2),
    'selected_card_init': ('selected_card_init', 'up_a'),
    'lifecycle.deactivate_on_early_hit': ('deactivate_on_early_hit', True),
    'lifecycle.depends_on': ('depends_on', 'other'),
    'start': ('soft_start', 74),
    'end': ('soft_end', 90),
    'increment': ('soft_increment', 6.25),
    'threshold': ('threshold', 90),
    'cr_counter_threshold': ('cr_counter_threshold', 3),
    'cr_base_rate': ('cr_base_rate', 0.018),
    'cr_state_probs': ('cr_state_probs', (0.0, 0.0, 0.0, 1.0)),
    'fate_threshold': ('fate_threshold', 1),
    'switch_allowed': ('switch_allowed', False),
    'switch_resets_progress': ('switch_resets_progress', False),
}

_EVENT_BTYPES = frozenset({'rotating', 'rotating_soft', 'rotating_cr',
                           'rotating_cr_soft', 'targeted', 'targeted_soft'})


def _pity_type_key_btypes():
    """契约表里的 btype 全集——参数化用例由此派生，扩表即自动覆盖新类型。"""
    from gacha_simulator.core.config_toml import _PITY_TYPE_KEYS
    return set(_PITY_TYPE_KEYS)


def _flat_type_keys(btype):
    """该 btype 的类型专用键（去掉嵌套的 `lifecycle.*`）。"""
    from gacha_simulator.core.config_toml import _PITY_TYPE_KEYS
    return {k for k in _PITY_TYPE_KEYS[btype] if not k.startswith('lifecycle.')}


def _form_for_btype(btype):
    """该 btype 的软保底形态：'deltas' / 'sugar' / None（无软保底键）。

    `deltas` 与语法糖三元组（`start` / `end` / `increment`）在写侧由同一分支产出、
    不能同时写出（`_write_sugar_form`），故 fixture 二选一；`soft_step` 只有
    `deltas` 一个类型键，只能走 deltas 形态。
    """
    keys = _flat_type_keys(btype)
    if 'deltas' in keys and 'start' not in keys:
        return 'deltas'
    if 'start' in keys:
        return 'sugar'
    return None


def _pitydef_from_contract(btype, *, form):
    """按 btype 的键契约构造「全量键」`PityDef`——契约内字段一律置非默认值。

    **必须是非默认值**：`_pitydef_to_toml` 是条件式逐字段书写（`priority` /
    `target_featured` / `lifecycle` 等均为「非默认才写」），全默认构造时用例恒绿、
    检测力归零。

    事件驱动型不置 `deactivate_on_early_hit`：读侧对「事件驱动型 + 提前命中」有专条
    硬拒，那是另一处被测面。
    """
    from gacha_simulator.core.config_store import PityDef
    from gacha_simulator.core.config_toml import (_expand_soft_to_deltas,
                                                  _pity_declared_keys)

    keys = _pity_declared_keys(btype) - {'name', 'type', 'scope', 'lifecycle'}
    kwargs = {}
    for key in sorted(k for k in keys if k != 'deltas'):
        field, value = _PITY_KEY_TO_FIELD[key]
        kwargs[field] = value
    if btype in _EVENT_BTYPES:
        kwargs.pop('deactivate_on_early_hit', None)

    if form == 'deltas':
        for f in ('soft_start', 'soft_end', 'soft_increment'):
            kwargs.pop(f, None)
        kwargs['deltas'] = ((74, 0.0), (16, 6.25))
        kwargs['soft_deltas'] = kwargs['deltas']   # 读侧由写出的 deltas 重建
    elif form == 'sugar' and btype in ('soft_interval', 'soft_additive'):
        # 直写语法糖的配置，读侧会展开出 deltas；fixture 预置同一份展开值，
        # 否则「往返等值」会因这一处**格式层**产物而失配。
        kwargs['deltas'] = _expand_soft_to_deltas(
            btype, kwargs['soft_start'], kwargs.get('soft_end'),
            kwargs.get('soft_increment'))

    return PityDef(name='p_' + btype, btype=btype, scope='ssr', **kwargs)


def _expected_emitted_keys(btype, form):
    """该 btype 的全量键 fixture 经写侧应产出的键集（与被测实现独立推导）。"""
    from gacha_simulator.core.config_toml import _PITY_COMMON_KEYS

    drop = {'deltas'} if form != 'deltas' else {'start', 'end', 'increment'}
    return set(_PITY_COMMON_KEYS) | (_flat_type_keys(btype) - drop)


def _build_pity_read_keys():
    """从 `_build_pity` 源码提取「被读取的 TOML 键」集合（反向断言用）。

    源码扫描而非用例穷举：读侧每加一处 `p.get(k)` / `p[k]` / `'k' in p` 即自动纳入，
    无需同步维护第二份清单。`lifecycle_raw.get(...)` 的一层嵌套键单独收，
    返回 `(顶层键集, 嵌套键集)`。
    """
    import inspect
    import re

    from gacha_simulator.core.config_toml import _build_pity

    code = inspect.getsource(_build_pity)
    pats = [r"p\.get\(\s*'([a-z_]+)'", r'p\.get\(\s*"([a-z_]+)"',
            r"p\['([a-z_]+)'\]", r"'([a-z_]+)'\s+in\s+p\b"]
    top = set()
    for pat in pats:
        top |= set(re.findall(pat, code))
    nested = set(re.findall(r"lifecycle_raw\.get\(\s*'([a-z_]+)'", code))
    return top, nested


class TestPityKeyContract:
    """契约表的一致性（双向）+ 读侧面覆盖 + 硬拒。"""

    def test_contract_tables_are_module_level_and_disjoint(self):
        """契约表形态：通用键与类型键不交叠，且类型键表覆盖全部 btype。"""
        from gacha_simulator.core.config_toml import _PITY_COMMON_KEYS, _PITY_TYPE_KEYS
        from gacha_simulator.core.pity import BEHAVIOR_REGISTRY

        assert 'priority' in _PITY_COMMON_KEYS, (
            'priority 由 S4b 落地且要求 round-trip 写回，缺它即拒收刚写出的合法配置')
        assert 'max_triggers' in _PITY_COMMON_KEYS, (
            'max_triggers 由 S4-4 落地且要求 round-trip 写回（ISSUE-032）：'
            '不入契约表时，读侧的未声明键硬拒会把刚写出的合法配置判为未知键')
        for btype, keys in _PITY_TYPE_KEYS.items():
            flat = {k for k in keys if not k.startswith('lifecycle.')}
            assert not (flat & _PITY_COMMON_KEYS), (btype, flat & _PITY_COMMON_KEYS)
        assert set(_PITY_TYPE_KEYS) == set(BEHAVIOR_REGISTRY), (
            '契约表的 btype 集与 BEHAVIOR_REGISTRY 不一致：'
            f'{set(_PITY_TYPE_KEYS) ^ set(BEHAVIOR_REGISTRY)}')

    @pytest.mark.parametrize('btype', sorted(_pity_type_key_btypes()))
    def test_emitted_keys_equal_contract(self, btype):
        """① 全量键 fixture → `_pitydef_to_toml` 产出键集 == 该 btype 的契约。

        `==` 的补集方向防「契约表登记了写侧产不出的幽灵键」（表与实现漂移）。

        **`⊆` 方向的触发面有限（S4c 审查 low，2026-10-10 实测）**：fixture 由
        `_pity_declared_keys(btype)` 派生，产不出跨类型键，故「写侧产出未声明键」
        在本用例下不可触发（实测删掉写侧过滤时，本用例 10 个 btype 全绿）；真正
        杀死该变异的是 `test_writer_filters_cross_type_fields`。此处保留 `⊆` 作为
        廉价不变式，但不要把它当作写侧过滤的守卫。
        """
        from gacha_simulator.core.config_toml import (_pity_declared_keys,
                                                      _pitydef_to_toml)

        form = _form_for_btype(btype)
        emitted = set(_pitydef_to_toml(_pitydef_from_contract(btype, form=form)))
        expected = _expected_emitted_keys(btype, form)
        assert emitted <= _pity_declared_keys(btype), (
            f'{btype}: 写侧产出了未声明键 '
            f'{sorted(emitted - _pity_declared_keys(btype))}')
        assert emitted == expected, (
            f'{btype}: 写侧产出与契约不符；多 {sorted(emitted - expected)}、'
            f'少 {sorted(expected - emitted)}')

    def test_priority_keys_subset_of_contract(self):
        """`PityDef(priority=5)` 的产出键集 ⊆ 通用键（S4b 写回面的自检）。"""
        from gacha_simulator.core.config_store import PityDef
        from gacha_simulator.core.config_toml import (_PITY_COMMON_KEYS,
                                                      _pitydef_to_toml)

        assert set(_pitydef_to_toml(PityDef(name='x', priority=5))) <= _PITY_COMMON_KEYS

    def test_contract_subset_of_build_pity_read_face(self):
        """② 反向：契约表 ⊆ `_build_pity` 的读取面。

        表里声明、读侧却不读的键 = 幽灵键（用户写它 → 加载期放行 → 无声失效），
        与建表立意相反。
        """
        from gacha_simulator.core.config_toml import (_PITY_COMMON_KEYS,
                                                      _PITY_TYPE_KEYS)

        top, nested = _build_pity_read_keys()
        # 扫描本身有效性的守卫：扫不到主体育（如 `_build_pity` 被抽成多个函数、
        # 读键改走变量）时下面的子集断言会假通过，故先钉住扫描面。
        assert len(top) >= 20 and 'priority' in top and 'name' in top, (
            f'源码扫描面异常（读键不足或缺少已知键）：{sorted(top)}')
        assert nested >= {'deactivate_on_early_hit', 'depends_on'}, sorted(nested)

        read_face = top | {f'lifecycle.{k}' for k in nested}
        contract = set(_PITY_COMMON_KEYS)
        for keys in _PITY_TYPE_KEYS.values():
            contract |= keys
        assert contract <= read_face, f'幽灵键：{sorted(contract - read_face)}'

    def test_pity_key_issues_is_pure_and_readonly(self):
        """③ `pity_key_issues` 不抛、只读、返回消息列表（形态同 shape_issues）。"""
        import copy

        from gacha_simulator.core.config_toml import pity_key_issues

        legal = [{'name': 'ok', 'type': 'hard', 'scope': 'ssr', 'threshold': 90}]
        assert pity_key_issues(legal) == []

        bad = [{'name': 'bad', 'type': 'hard', 'scope': 'ssr', 'max_tirggers': 2,
                'lifecycle': {'deactivate_on_early_hit': True, 'foo': 1}}]
        before = copy.deepcopy(bad)
        issues = pity_key_issues(bad)
        assert bad == before, '被测函数修改了入参'
        assert len(issues) == 2, issues
        assert any('max_tirggers' in m for m in issues)
        assert any('foo' in m for m in issues)

        # 输入非法（非 list / 条目非 dict）不抛——那是 _build_pity 既有校验的报错面
        assert pity_key_issues(None) == []
        assert pity_key_issues({'name': 'x'}) == []
        assert pity_key_issues(['not a dict']) == []

    def test_unknown_key_rejected_names_key_and_legal_set(self):
        """未声明键 → `ConfigError`，信息点名该键与合法键集（端到端）。"""
        toml = (_BASE_TOML +
                '[[pity]]\nname = "bad"\ntype = "hard"\nscope = "ssr"\n'
                'threshold = 90\nmax_tirggers = 2\n')
        with pytest.raises(ConfigError) as ei:
            _write_and_load(toml)
        msg = str(ei.value)
        assert 'max_tirggers' in msg, msg      # 点名出错键
        assert 'threshold' in msg, msg         # 该 type 的类型键
        assert 'counter_init' in msg, msg      # 通用键
        assert 'name' in msg, msg

    def test_func_still_rejected_by_legacy_check(self):
        """`func` 不入契约表：它由 `_check_pity_format` 的旧格式判据报出（提示语更贴题）。

        这同时钉住硬拒的**次序**：未声明键的报错排在 `_check_pity_format` 之后，
        含 `func` 的条目先吃到旧格式提示，而不是被当成「未声明键 func」。
        """
        toml = (_BASE_TOML +
                '[[pity]]\nname = "x"\ntype = "soft_interval"\nscope = "ssr"\n'
                'start = 73\nfunc = "linear"\n')
        with pytest.raises(ConfigError) as ei:
            _write_and_load(toml)
        msg = str(ei.value)
        assert 'func' in msg, msg
        assert '未声明键' not in msg, msg

    def test_cross_type_key_rejected(self):
        """跨类型误写（soft_step 写 threshold）→ `ConfigError`（读侧确实不消费它）。"""
        toml = _BASE_TOML + _pity_section('soft_step', 'x', threshold=90)
        with pytest.raises(ConfigError, match='threshold'):
            _write_and_load(toml)

    def test_nested_lifecycle_unknown_key_rejected(self):
        """`[pity.lifecycle]` 子表的未声明键 → `ConfigError`。"""
        toml = _BASE_TOML + '''[[pity]]
name = "x"
type = "hard"
scope = "ssr"
threshold = 90

[pity.lifecycle]
deactivate_on_early_hit = true
deactvate_on_early_hit = true
'''
        with pytest.raises(ConfigError, match='lifecycle'):
            _write_and_load(toml)

    def test_registered_key_of_other_type_still_accepted_for_its_own_type(self):
        """未声明键硬拒不是「白名单外的键一刀切」——各类型自己的键照常放行。"""
        toml = _BASE_TOML + (
            _pity_section('soft_additive', 'a', start=65, increment=6.0) +
            _pity_section('rotating_cr', 'b', cr_counter_threshold=3,
                          cr_state_probs=[0.0, 0.0, 0.0, 1.0]) +
            _pity_section('targeted', 'c', fate_threshold=1, switch_allowed=False))
        store, path = _write_and_load(toml)
        try:
            assert [p.btype for p in store.pity.pities] == [
                'soft_additive', 'rotating_cr', 'targeted']
        finally:
            os.unlink(path)

class TestPriorityTomlRoundTrip:
    """`PityDef.priority` 的 TOML 往返：解析、非默认写回、默认不写。"""

    def test_writeback_emits_non_default(self):
        from gacha_simulator.core.config_toml import _pitydef_to_toml
        from gacha_simulator.core.config_store import PityDef

        assert _pitydef_to_toml(PityDef(name='x', priority=5))['priority'] == 5

    def test_writeback_omits_default(self):
        """默认 0 不写出该键（round-trip 纪律：缺键与 0 在解析侧等价）。"""
        from gacha_simulator.core.config_toml import _pitydef_to_toml
        from gacha_simulator.core.config_store import PityDef

        assert 'priority' not in _pitydef_to_toml(PityDef(name='x'))
        assert 'priority' not in _pitydef_to_toml(PityDef(name='x', priority=0))

    def test_parse_from_toml(self):
        toml = _BASE_TOML + _pity_section('soft_interval', 'p1',
                                          start=74, end=90, priority=5)
        store, path = _write_and_load(toml)
        try:
            assert store.pity.pities[0].priority == 5
        finally:
            os.unlink(path)

    def test_parse_missing_key_defaults_to_zero(self):
        toml = _BASE_TOML + _pity_section('soft_interval', 'p1', start=74, end=90)
        store, path = _write_and_load(toml)
        try:
            assert store.pity.pities[0].priority == 0
        finally:
            os.unlink(path)

    def test_save_load_closed_loop_preserves_priority(self):
        """「写盘 → 重载」闭环：priority=5 经 `save_toml` / `load_toml` 后不变。"""
        from gacha_simulator.core.config_store import ConfigStore, PityConfig

        store = ConfigStore()
        store.pity = PityConfig(enabled=True, pities=[
            _all_fields_non_default_pitydef()])
        path = tempfile.mkdtemp() + '/p64_priority.toml'
        save_toml(store, path)
        store2 = load_toml(path)
        # 写回确实落了盘（而非被条件式逐字段书写漏掉）
        with open(path, encoding='utf-8') as f:
            assert 'priority = 5' in f.read()
        assert store2.pity.pities[0].priority == 5

    @pytest.mark.parametrize('btype', sorted(_pity_type_key_btypes()))
    def test_full_field_toml_roundtrip(self, btype):
        """字段全量 TOML round-trip：**按键契约**逐字段等值（S4c 重写）。

        原版用单个 `soft_interval` + 全字段非默认的 fixture，在 S4c 键契约落地后
        不再成立——那份额外把 `cr_*` / `fate_*` / `switch_*` / `threshold` 也置了
        非默认值，而这些键对 `soft_interval` 未声明：写侧按契约过滤、读侧按契约硬拒。
        改为**按 btype 参数化**：每条只置该类型契约内的键（通用键 + 该类型键），
        断言 `PityDef` 全部字段往返等值——契约外字段恒为默认，「串值」也会被这条
        断言抓住。

        软保底形态由 `_form_for_btype()` 自动挑（`deltas` 与语法糖三元组在写侧由
        同一分支产出、不能同时写出，见 `_write_sugar_form`）。
        """
        import dataclasses

        from gacha_simulator.core.config_store import ConfigStore, PityConfig, PityDef

        src = _pitydef_from_contract(btype, form=_form_for_btype(btype))
        store = ConfigStore()
        store.pity = PityConfig(enabled=True, pities=[src])
        path = tempfile.mkdtemp() + '/p64_full_' + btype + '.toml'
        save_toml(store, path)
        got = load_toml(path).pity.pities[0]

        lost = []
        for f in dataclasses.fields(PityDef):
            if getattr(got, f.name) != getattr(src, f.name):
                lost.append((f.name, getattr(src, f.name), getattr(got, f.name)))
        assert lost == [], f"下列字段在 TOML round-trip 中失真：{lost}"
        assert got.btype == src.btype

    def test_writer_filters_cross_type_fields(self):
        """写侧按键契约过滤跨类型字段（S4c 新增，防「写盘 → 重载」自破）。

        `_pitydef_to_toml` 对 `cr_*` / `fate_*` / `switch_*` / `threshold` 是逐字段
        无条件书写（只看字段非默认，不看 btype）。读侧自 S4c 起对未声明键硬拒，
        故写侧必须同表过滤，否则把该 btype 不消费的字段写进 TOML 后自己读不回来。

        **可达路径不止手构 PityDef**：GUI 兜底条目经 `PityDef(switch_allowed=None)`
        令 `not None` 为真，给 `soft_interval` 条目写出 `switch_allowed = false`
        （2026-10-10 实测），过滤前「导入无保底段的配置 → 导出 → 再导入」即失败。
        """
        import dataclasses

        from gacha_simulator.core.config_store import ConfigStore, PityConfig, PityDef
        from gacha_simulator.core.config_toml import (_pity_declared_keys,
                                                      _pitydef_to_toml)

        src = _all_fields_non_default_pitydef()          # btype='soft_interval'
        entry = _pitydef_to_toml(src)

        assert set(entry) <= _pity_declared_keys('soft_interval'), sorted(entry)
        for cross in ('cr_base_rate', 'cr_counter_threshold', 'cr_state_probs',
                      'fate_threshold', 'switch_allowed', 'switch_resets_progress',
                      'threshold'):
            assert cross not in entry, cross + ' 属其他类型的键，不该写进 soft_interval'
        # 契约内的键照常写出（过滤只砍跨类型字段，不是整体丢弃）
        assert entry['priority'] == 5 and entry['reset'] == 'featured'
        assert entry['deltas'] == [[74, 0.0], [16, 6.25]]
        assert entry['lifecycle'] == {'deactivate_on_early_hit': True,
                                      'depends_on': 'other'}

        # 端到端：往返后跨类型字段落回默认值，条目仍可加载
        store = ConfigStore()
        store.pity = PityConfig(enabled=True, pities=[src])
        path = tempfile.mkdtemp() + '/p64_filter.toml'
        save_toml(store, path)
        got = load_toml(path).pity.pities[0]
        for f in dataclasses.fields(PityDef):
            if f.name in ('cr_base_rate', 'cr_counter_threshold', 'cr_state_probs',
                          'fate_threshold', 'threshold'):
                assert getattr(got, f.name) is None, f.name
        assert got.switch_allowed is True and got.switch_resets_progress is True
        assert got.deltas == ((74, 0.0), (16, 6.25))


# ══════════════════════════════════════════════════════════════════
# P64 S4-4：`PityDef.max_triggers` 的 TOML 往返与退役维接线（ISSUE-032）
# ══════════════════════════════════════════════════════════════════
# `max_triggers`（0 = 不限）是 §3.1.3 退役维 `AfterN(N)` 的配置来源、与 `depends_on`
# （激活维）正交。本组钉住三件事：
#   ① 解析 + round-trip（非默认写回、默认不写、闭环保留）；
#   ② 负值与非整数在加载期硬拒（负值若放行会被 `_n > 0` 静默当成 0）；
#   ③ 配置面到 `build_lifecycle` 的接线（TOML → `PityDef` → `FiniteActive` /
#      `DependentFiniteActive`）：只测 `build_lifecycle` 时该键的配置入口可整体失踪
#      而用例全绿。

class TestMaxTriggersTomlRoundTrip:
    """`max_triggers` 的 TOML 往返：解析、非默认写回、默认不写。"""

    def test_writeback_emits_non_default(self):
        from gacha_simulator.core.config_toml import _pitydef_to_toml
        from gacha_simulator.core.config_store import PityDef

        assert _pitydef_to_toml(PityDef(name='x', max_triggers=2))['max_triggers'] == 2

    def test_writeback_omits_default(self):
        """默认 0 不写出该键（round-trip 纪律：缺键与 0 在解析侧等价）。"""
        from gacha_simulator.core.config_toml import _pitydef_to_toml
        from gacha_simulator.core.config_store import PityDef

        assert 'max_triggers' not in _pitydef_to_toml(PityDef(name='x'))
        assert 'max_triggers' not in _pitydef_to_toml(
            PityDef(name='x', max_triggers=0))

    def test_parse_from_toml(self):
        toml = _BASE_TOML + _pity_section('hard', 'p1', threshold=90,
                                          max_triggers=2)
        store, path = _write_and_load(toml)
        try:
            assert store.pity.pities[0].max_triggers == 2
        finally:
            os.unlink(path)

    def test_parse_missing_key_defaults_to_zero(self):
        toml = _BASE_TOML + _pity_section('hard', 'p1', threshold=90)
        store, path = _write_and_load(toml)
        try:
            assert store.pity.pities[0].max_triggers == 0
        finally:
            os.unlink(path)

    def test_save_load_closed_loop_preserves_max_triggers(self):
        """「写盘 → 重载」闭环：手写的 `max_triggers = 2` 经 save / load 后不变。

        写侧是条件式逐字段书写，漏写回时该键被静默抹掉（缺键与 0 在解析侧等价），
        故本用例同时断言**字面量落了盘**。
        """
        toml = _BASE_TOML + _pity_section('hard', 'p1', threshold=90,
                                          max_triggers=2)
        store, path = _write_and_load(toml)
        try:
            store2 = _roundtrip(store, path)
            with open(path, encoding='utf-8') as f:
                assert 'max_triggers = 2' in f.read(), (
                    '写回漏了该键，「GUI 加载 → 保存」一次即抹掉')
            assert store2.pity.pities[0].max_triggers == 2
        finally:
            os.unlink(path)

    def test_negative_rejected(self):
        """⑦ `max_triggers = -1` 抛 `ConfigError`（不静默当 0）。"""
        toml = _BASE_TOML + _pity_section('hard', 'p1', threshold=90,
                                          max_triggers=-1)
        with pytest.raises(ConfigError, match='max_triggers'):
            _write_and_load(toml)

    @pytest.mark.parametrize('value', ['2', True, 1.5])
    def test_non_integer_rejected(self, value):
        """非整数取值硬拒：字符串会让 `_n > 0` 抛 `TypeError`（被构造兜底吞掉）。

        参数是**值**而非 TOML 字面量（`_pity_section` 按 Python 类型自行书写）。
        """
        # 复用 `_pity_section`（S4-4 审查 low：内联手写等于第二份段格式，
        # 段格式一改本用例会静默失效）
        toml = _BASE_TOML + _pity_section('hard', 'p1', threshold=90,
                                          max_triggers=value)
        with pytest.raises(ConfigError, match='max_triggers'):
            _write_and_load(toml)

    def test_toml_to_lifecycle_wiring(self):
        """③ 配置面接线：TOML → `PityDef` → `build_lifecycle` 的四组合。

        只测 `build_lifecycle` 时，`PityDef.max_triggers` 的解析 / 写回可整体失踪
        而用例全绿（`build_lifecycle` 用 `getattr` 兜底），故本用例从 TOML 起跑。
        """
        from gacha_simulator.core.pity import build_lifecycle
        from gacha_simulator.core.pity_tracker import (AlwaysActive,
                                                       DependentActive,
                                                       DependentFiniteActive,
                                                       FiniteActive)

        toml = (_BASE_TOML +
                _pity_section('hard', 'plain', threshold=90) +
                _pity_section('hard', 'welfare', threshold=90, max_triggers=2) +
                _pity_section('hard', 'dep', threshold=90) +
                '[pity.lifecycle]\ndepends_on = "welfare"\n' +
                _pity_section('hard', 'dep_finite', threshold=90,
                              max_triggers=3) +
                '[pity.lifecycle]\ndepends_on = "welfare"\n')
        store, path = _write_and_load(toml)
        try:
            got = {p.name: build_lifecycle(p) for p in store.pity.pities}
        finally:
            os.unlink(path)

        assert isinstance(got['plain'], AlwaysActive)
        assert isinstance(got['welfare'], FiniteActive)
        assert got['welfare']._max_triggers == 2
        assert got['welfare'].state_keys() == ('triggers',)
        assert isinstance(got['dep'], DependentActive)
        assert isinstance(got['dep_finite'], DependentFiniteActive)
        assert got['dep_finite']._max_triggers == 3
        assert got['plain'].state_keys() == ()
