"""`reset = "on_effective"`（仅生效时重置）：幻塔「每 N 抽白送一个」的等价表达。

**机制**（2026-10-15 用户裁定）：`reset` 的既有取值把「何时归零」绑在**出卡事件**
上（`''` = 出作用稀有度 / `'featured'` = 出任意 featured 卡 / 稀有度名 / `'never'`
= 永不）。幻塔的「每 80 抽白送一个金」是另一件事：**保底触发时归零**，即「每 N 抽
送一个」而非「从第 N 抽起永久保底」。后者由 `reset = "never"` 承载（counter 从不
归零，第 N 抽起每一抽都强制），前者需要新取值。

**「生效」的判据**：该抽该保底的 `compute_delta()` 返回了**非 `None` 且非全零**的
增量，即**真的改动了分布**。不是「触发条件成立」（`counter >= τ`）：目标集为空时
`HardModifier` 返 `None`、分布未变，该抽不算生效、计数器不归零（§3.9.5 的恒等
分支）。判据的载体是**本保底命名空间**下的 `_effective` 键：骨架在 `before_draw`
的 Modifier 链里置位，`CounterTracker.commit`（`after_draw` 相位）读它，**不跨相位
传参**。清除时机是**每次 `before_draw` 开头**（`is_active` 早退之后、Modifier 链
之前）删键，故每抽读到的一定是**本抽**的结论、不会残留上一抽。

**类型白名单**：只有阈值触发型（`hard` 与两条 G3 `hard_exclude_owned_*`）允许该
取值。`soft_*` / `rotating*` / `targeted*` 的触发不产生「保底生效」这一事件（soft
是渐进爬升、事件驱动型由标记翻转承载），配该取值即语义不明，故**硬拒**（与裁决
7B 对 `target_featured` 的处置同形，落点在 `create_behavior`）。
"""

import os
import tempfile

import pytest

from gacha_simulator.core.config_store import ConfigError, PityDef
from gacha_simulator.core.config_toml import legal_reset_values, load_toml, save_toml
from gacha_simulator.core.invariants import InvariantChecker
from gacha_simulator.core.pity import PityEngine, PityState, PoolPitySpec
from gacha_simulator.core.pity_primitives import _EFFECTIVE_KEY
from gacha_simulator.core.pity_tracker import CounterTracker
from gacha_simulator.core.state import GachaState as _GachaState, SimView as _SimView

_RARITY = {'ssr': 0, 'sr': 1, 'r': 2}
_SIM = _SimView(_GachaState())

#: 有 ssr 卡的池（保底有目标集，`HardModifier` 会真的搬概率）。
FULL_SCOPE = {'ssr': ('ssr_up',), 'sr': ('sr_std',), 'r': ('r_std',)}
FULL_BASE = {'ssr_up': 0.01, 'sr_std': 0.05, 'r_std': 0.94}
#: **无 ssr 卡**的池（保底 scope='ssr' 在本池无目标可给，`HardModifier` 恒等）。
EMPTY_SCOPE = {'sr': ('sr_std',), 'r': ('r_std',)}
EMPTY_BASE = {'sr_std': 0.05, 'r_std': 0.95}


def _engine(defs, scope_cards, base, invariants=None, pool_id='p1'):
    spec = PoolPitySpec(pity_names=[d.name for d in defs], scope_cards=scope_cards)
    st = PityState()
    eng = PityEngine({pool_id: spec}, defs, rarity_rank=_RARITY, state=st,
                     invariants=invariants)
    return eng, st, pool_id, base


def _draw_once(eng, st, pool_id, base, reward_id='sr_std'):
    """一次完整抽卡（`before_draw` 相位 + `after_draw` 相位）。"""
    eng.before_draw(pool_id, st, base, _SIM)
    eng.after_draw(pool_id, st, reward_id, _SIM)


# ══════════════════════════════════════════════════════════════════
# Tracker 层：声明面与重置条件
# ══════════════════════════════════════════════════════════════════

class TestTrackerDeclaration:
    """`_effective` 的声明面：只有 `on_effective` 型声明它。"""

    def test_state_keys_declares_effective_only_for_on_effective(self):
        assert CounterTracker(scope='ssr', reset_on='on_effective').state_keys() == (
            'counter', _EFFECTIVE_KEY)
        assert CounterTracker(scope='ssr', reset_on='ssr').state_keys() == ('counter',)
        assert CounterTracker(scope='ssr', reset_on='never').state_keys() == ('counter',)

    def test_commit_reads_effective_flag_from_own_namespace(self):
        """`commit` 的判据是**本保底命名空间**下的 `_effective`，与出卡事件无关。"""
        from gacha_simulator.core.pity_primitives import DrawInfo, PityContext

        st = PityState()
        tr = CounterTracker(scope='ssr', reset_on='on_effective')
        tr.rebind(st, 'h1')
        st.set('h1', 'counter', 7)
        ctx = PityContext(
            draw=DrawInfo(pool_id='p1', pool_instance_id='p1', reward_id='sr_std',
                          reward_rarity='sr', is_featured=False),
            current={}, state=st, sim=_SIM)

        tr.commit(ctx, st, 'h1')
        assert st.get('h1', 'counter', 0) == 7, '未置位 `_effective` 即不重置'

        st.set('h1', _EFFECTIVE_KEY, True)
        assert tr.did_reset(ctx, st, 'h1') is True
        tr.commit(ctx, st, 'h1')
        assert st.get('h1', 'counter', 0) == 0, '置位 `_effective` 即重置'


# ══════════════════════════════════════════════════════════════════
# 引擎行为：两形态（生效归零 / 未生效不归零）
# ══════════════════════════════════════════════════════════════════

class TestEngineEffectiveReset:
    """阈值触发型的两个形态，经 `PityEngine` 完整调度路径。"""

    def test_counter_resets_only_on_the_draw_that_takes_effect(self):
        """形态 ①：保底生效的那一抽归零，之后**未生效的抽不归零**。

        判别力在两处：第 2 抽（`counter=2 >= τ=2` 且目标集非空 → 生效 → 归零）、
        第 3 抽（`counter=1 < τ` → 不生效 → 计数保留为 1）。若把清除时机改错
        （`_effective` 残留上一抽），第 3 抽会被误判为生效、counter 归 0。
        """
        defs = [PityDef(name='h1', btype='hard', scope='ssr', threshold=2,
                        reset='on_effective')]
        eng, st, pool_id, base = _engine(defs, FULL_SCOPE, FULL_BASE)

        _draw_once(eng, st, pool_id, base)
        assert eng.get_counter('h1') == 1, '第 1 抽未达阈值，不生效、不归零'

        _draw_once(eng, st, pool_id, base)
        assert eng.get_counter('h1') == 0, '第 2 抽生效，计数器归零'

        _draw_once(eng, st, pool_id, base)
        assert eng.get_counter('h1') == 1, (
            '第 3 抽未达阈值，`_effective` 不得残留上一抽（残留即误归零）')

    def test_counter_does_not_reset_when_target_set_is_empty(self):
        """形态 ②：`counter >= τ` 但**分布未变**（目标集为空）→ 不算生效、不归零。

        判据是「真的改动了分布」而非「触发条件成立」：本池无 ssr 卡，
        `HardModifier.compute_delta` 在 `A` 为空时返 `None`（§3.9.5 的恒等分支），
        故第 2 / 3 抽都只是把 counter 累积上去。
        """
        defs = [PityDef(name='h1', btype='hard', scope='ssr', threshold=2,
                        reset='on_effective')]
        eng, st, pool_id, base = _engine(defs, EMPTY_SCOPE, EMPTY_BASE)

        for _ in range(3):
            _draw_once(eng, st, pool_id, base)
        assert eng.get_counter('h1') == 3, (
            '目标集为空时保底恒等，「条件成立」不得被当作生效')

    def test_invariant_checker_accepts_the_new_state_key(self):
        """S11 状态层的声明面完整：`_effective` 在 Tracker 的 `state_keys()` 内，
        故 `enabled=True` 下跑完整调度不抛 `InvariantError`。"""
        defs = [PityDef(name='h1', btype='hard', scope='ssr', threshold=2,
                        reset='on_effective')]
        eng, st, pool_id, base = _engine(defs, FULL_SCOPE, FULL_BASE,
                                         invariants=InvariantChecker(enabled=True))
        for _ in range(4):
            _draw_once(eng, st, pool_id, base)


# ══════════════════════════════════════════════════════════════════
# 类型白名单：只有阈值触发型可配
# ══════════════════════════════════════════════════════════════════

class TestTypeWhitelist:
    """非阈值触发型配 `reset='on_effective'` 一律抛 `ConfigError`。"""

    @pytest.mark.parametrize('btype,kwargs', [
        ('soft_interval', {'soft_start': 73, 'soft_end': 90}),
        ('soft_additive', {'soft_start': 70, 'soft_increment': 6}),
        ('rotating', {}),
        ('targeted', {'fate_threshold': 1}),
    ])
    def test_non_threshold_type_is_rejected(self, btype, kwargs):
        defs = [PityDef(name='x', btype=btype, scope='ssr',
                        reset='on_effective', **kwargs)]
        with pytest.raises(ConfigError, match='on_effective'):
            _engine(defs, FULL_SCOPE, FULL_BASE)

    @pytest.mark.parametrize('btype', ['hard', 'hard_exclude_owned_skip',
                                       'hard_exclude_owned_any'])
    def test_threshold_types_are_accepted(self, btype):
        defs = [PityDef(name='x', btype=btype, scope='ssr', threshold=2,
                        reset='on_effective')]
        eng, st, pool_id, base = _engine(defs, FULL_SCOPE, FULL_BASE)
        assert eng.get_pity_def('x').reset == 'on_effective'


# ══════════════════════════════════════════════════════════════════
# 配置面：白名单 + round-trip
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
rarity = "SR"
featured = false
"""


def _write_and_load(toml_text):
    fd, path = tempfile.mkstemp(suffix='.toml')
    try:
        os.close(fd)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(toml_text)
        return load_toml(path), path
    except Exception:
        os.unlink(path)
        raise


class TestConfigSurface:
    """`legal_reset_values()` 纳入新取值，且写侧 round-trip 不丢。"""

    def test_legal_reset_values_includes_on_effective(self):
        assert 'on_effective' in legal_reset_values({'ssr': 0, 'sr': 1, 'r': 2})

    def test_toml_round_trip_preserves_on_effective(self):
        toml = _BASE_TOML + (
            '\n[[pity]]\nname = "h1"\ntype = "hard"\nscope = "ssr"\n'
            'threshold = 2\nreset = "on_effective"\n'
            'pools = ["test_pool.main"]\n')
        store, path = _write_and_load(toml)
        try:
            assert store.pity.pities[0].reset == 'on_effective'
            save_toml(store, path)
            store2 = load_toml(path)
            assert store2.pity.pities[0].reset == 'on_effective', (
                'round-trip 丢失新取值即「GUI 加载后保存」静默改语义')
        finally:
            os.unlink(path)
