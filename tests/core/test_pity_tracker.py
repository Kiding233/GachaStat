"""P64 S1b-1：Tracker 协议 + `CounterTracker`（§3.1.1）。

覆盖两块被测面：

1. **N1 相位**（计数型 Tracker 的 `advance` 段）——「每抽加一次」表现为
   「第 N 抽读到的值为 N」。旧 `CounterBasedBehavior.before_draw` 先自增再用
   自增后的值算概率，实测 `hard(threshold=90)` 首次 100% 落在**第 90 抽**；若把
   递增挪到 `after_draw`，第 90 抽读到 89、首次触发落到第 91 抽。总次数相同、
   差的是**读相位**，故本组断言钉住「第 90 抽读到 90」而不是「加了 90 次」。
   （概率层面的「首次 100% 出现在第 90 抽」由 S2a/S5 的 Modifier 与等价性装置
   断言，本层无概率管道。）
2. **M4 `did_reset`**（counter 家族）——与 `commit` 的重置条件严格同条件；
   `'featured'` 分支保留**无 scope 门控**的不对称。
"""

from gacha_simulator.core.pity_primitives import DrawInfo, PityContext, PityState
from gacha_simulator.core.pity_tracker import CounterTracker, FlagTracker, Tracker

NAME = 'ssr_hard'
SCOPE = 'ssr'


def _ctx(rarity: str = 'sr', is_featured: bool = False, state: PityState = None,
         reward_id: str = None):
    """构造一次抽卡的 PityContext（默认出非 scope 的非 featured 卡）。"""
    st = state if state is not None else PityState()
    draw = DrawInfo(
        pool_id='p', pool_instance_id='p_0', reward_id=reward_id or f'{rarity}_card',
        reward_rarity=rarity, is_featured=is_featured,
    )
    return PityContext(draw=draw, current={}, state=st)


def _tracker(reset_on=None, init=0, state=None):
    """构造已 rebind 的 CounterTracker 与其 state。"""
    st = state if state is not None else PityState()
    tr = CounterTracker(scope=SCOPE, reset_on=reset_on, init=init)
    tr.rebind(st, NAME)
    return tr, st


# ══════════════════════════════════════════════════════════════════
# N1 相位
# ══════════════════════════════════════════════════════════════════

class TestN1Phase:
    """计数型 Tracker 在 before_draw 的 advance 段推进。"""

    def test_n1_phase_counter_reads_draw_index(self):
        """第 N 抽（未重置）读到的 counter 值为 N——`hard(threshold=90)` 因此
        首次 100% 落在第 90 抽，而非第 91 抽。"""
        tr, st = _tracker(reset_on=SCOPE)
        seen = []
        for _ in range(90):
            ctx = _ctx(rarity='sr', state=st)   # 全程不出 scope → 不重置
            tr.advance(ctx, st, NAME, False)
            seen.append(st.get(NAME, 'counter', 0))

        assert seen[0] == 1, '首抽读到的应是 1（而非 0）'
        assert seen[88] == 89
        assert seen[89] == 90, '第 90 抽须读到 90——否则首次保底落在第 91 抽'

    def test_readonly_advance_does_not_increment(self):
        """`readonly=True`（只读查询）不推进计数。"""
        tr, st = _tracker(reset_on=SCOPE)
        for _ in range(5):
            tr.advance(_ctx(state=st), st, NAME, False)
        assert st.get(NAME, 'counter', 0) == 5

        tr.advance(_ctx(state=st), st, NAME, True)
        tr.advance(_ctx(state=st), st, NAME, True)
        assert st.get(NAME, 'counter', 0) == 5, '只读查询不得推进计数'

    def test_prepare_is_noop(self):
        """`CounterTracker.prepare` 是 no-op（掷骰相位属 StreakTracker）。"""
        tr, st = _tracker(reset_on=SCOPE)
        tr.advance(_ctx(state=st), st, NAME, False)
        tr.prepare(_ctx(state=st), st, NAME, False)
        assert st.get(NAME, 'counter', 0) == 1
        assert st.data.get(NAME, {}) == {'counter': 1}


# ══════════════════════════════════════════════════════════════════
# commit：重置条件
# ══════════════════════════════════════════════════════════════════

class TestCommitReset:
    """`commit` 落重置；`skip_reset` 是 deactivate_on_early_hit 的例外通道。"""

    def test_commit_resets_on_scope_rarity(self):
        """`reset_on='ssr'`：出 SSR 归零，出 SR 不归零。"""
        tr, st = _tracker(reset_on=SCOPE)
        for _ in range(7):
            tr.advance(_ctx(rarity='sr', state=st), st, NAME, False)
        assert st.get(NAME, 'counter', 0) == 7

        tr.commit(_ctx(rarity='sr', state=st), st, NAME)
        assert st.get(NAME, 'counter', 0) == 7, '出非触发稀有度不得重置'

        tr.commit(_ctx(rarity='ssr', state=st), st, NAME)
        assert st.get(NAME, 'counter', 0) == 0

    def test_commit_reset_empty_falls_back_to_scope(self):
        """`reset_on` 空串回退 scope（对齐 create_behavior 仅在 truthy 时透传）。"""
        tr, st = _tracker(reset_on='')
        tr.advance(_ctx(rarity='sr', state=st), st, NAME, False)
        assert tr._reset_on == SCOPE
        tr.commit(_ctx(rarity='ssr', state=st), st, NAME)
        assert st.get(NAME, 'counter', 0) == 0

    def test_commit_reset_featured_has_no_scope_gate(self):
        """`reset_on='featured'`：只看 is_featured、**无 scope 门控**（有意保留的
        不对称，§3.1.1 三点声明第 2 条）。出非 scope 的 featured 卡同样重置。"""
        tr, st = _tracker(reset_on='featured')
        tr.advance(_ctx(rarity='sr', state=st), st, NAME, False)
        assert st.get(NAME, 'counter', 0) == 1

        tr.commit(_ctx(rarity='sr', is_featured=True, state=st), st, NAME)
        assert st.get(NAME, 'counter', 0) == 0, 'featured 分支不得加 scope 门控'

    def test_commit_never_never_resets(self):
        """`reset_on='never'`（G16 幻塔「出金不重置」）：出 scope 也不归零。"""
        tr, st = _tracker(reset_on='never')
        for _ in range(3):
            tr.advance(_ctx(rarity='ssr', state=st), st, NAME, False)
        assert st.get(NAME, 'counter', 0) == 3
        tr.commit(_ctx(rarity='ssr', state=st), st, NAME)
        assert st.get(NAME, 'counter', 0) == 3

    def test_commit_skip_reset_skips_reset(self):
        """`skip_reset=True` 跳过重置——`deactivate_on_early_hit` 的例外通道
        （旧 `_on_reset()` 返回 True 时提前 return，实测第 5 抽命中后 counter
        仍为 5，而非归 0）。"""
        tr, st = _tracker(reset_on=SCOPE)
        for _ in range(5):
            tr.advance(_ctx(rarity='sr', state=st), st, NAME, False)
        tr.commit(_ctx(rarity='ssr', state=st), st, NAME, skip_reset=True)
        assert st.get(NAME, 'counter', 0) == 5, '退役动作与重置同序判定，退役则跳过重置'

    def test_commit_requires_rebind_first(self):
        """未 `rebind` 即 `commit` 是 AttributeError——协议要求 `Pity` 无条件先重绑。"""
        tr = CounterTracker(scope=SCOPE, reset_on=SCOPE)
        try:
            tr.commit(_ctx(rarity='ssr'), PityState(), NAME)
        except AttributeError:
            return
        raise AssertionError('未 rebind 的 CounterTracker 不应可用')


# ══════════════════════════════════════════════════════════════════
# M4 did_reset
# ══════════════════════════════════════════════════════════════════

class TestDidReset:
    """counter 家族的 `did_reset` 与 `commit` 的重置条件严格同条件。"""

    def test_did_reset_matches_commit_condition(self):
        """同一 ctx 下 `did_reset` 为真 ⟺ `commit` 会重置 counter。"""
        for reset_on, rarity, feat in [
            (SCOPE, 'ssr', False), (SCOPE, 'sr', False), (SCOPE, 'sr', True),
            ('featured', 'sr', True), ('featured', 'ssr', False),
            ('never', 'ssr', True),
        ]:
            tr, st = _tracker(reset_on=reset_on)
            tr.advance(_ctx(rarity='sr', state=st), st, NAME, False)
            ctx = _ctx(rarity=rarity, is_featured=feat, state=st)
            fired = tr.did_reset(ctx, st, NAME)
            tr.commit(ctx, st, NAME)
            reset = st.get(NAME, 'counter', 0) == 0
            assert fired == reset, (
                f'reset_on={reset_on} rarity={rarity} featured={feat}：'
                f'did_reset={fired} 但 commit 重置={reset}'
            )

    def test_did_reset_featured_keeps_no_scope_gate(self):
        """`'featured'` 分支的 `did_reset` 同样不带 scope 门控（与 rotating /
        targeted 统一后带门控的语义不同）。"""
        tr, _ = _tracker(reset_on='featured')
        assert tr.did_reset(_ctx(rarity='sr', is_featured=True), PityState(), NAME) is True
        assert tr.did_reset(_ctx(rarity='ssr', is_featured=False), PityState(), NAME) is False


# ══════════════════════════════════════════════════════════════════
# 协议面：state_keys / namespace / rebind
# ══════════════════════════════════════════════════════════════════

class TestTrackerProtocol:
    """六个契约成员的默认形态与 CounterTracker 的覆写。"""

    def test_state_keys_counter(self):
        """`CounterTracker.state_keys()` = `('counter',)`——不依赖 state。"""
        tr = CounterTracker(scope=SCOPE, reset_on=SCOPE)
        assert tr.state_keys() == ('counter',)

    def test_base_tracker_defaults_are_noop(self):
        """协议基类的默认实现即「无状态零件」的定义。"""
        base = Tracker()
        st = PityState()
        ctx = _ctx(state=st)
        base.rebind(st, NAME)
        base.advance(ctx, st, NAME, False)
        base.prepare(ctx, st, NAME, False)
        base.commit(ctx, st, NAME)
        assert base.did_reset(ctx, st, NAME) is False
        assert base.state_keys() == ()
        assert base.namespace is None
        assert st.data == {}, '默认实现不得写任何 state 键'

    def test_namespace_default_none(self):
        """`namespace` 默认 None = 不做命名空间切换（§3.10.3 两级 view 分配的输入）。"""
        assert CounterTracker(scope=SCOPE, reset_on=SCOPE).namespace is None

    def test_rebind_redirects_writes_to_new_state(self):
        """`rebind` 是纯重定向——重绑后写入落在新 state，旧 state 不再被触碰。"""
        tr, old = _tracker(reset_on=SCOPE)
        tr.advance(_ctx(state=old), old, NAME, False)
        assert old.get(NAME, 'counter', 0) == 1

        new = PityState()
        tr.rebind(new, NAME)
        tr.advance(_ctx(state=new), new, NAME, False)
        assert new.get(NAME, 'counter', 0) == 1, '重绑后的写入须落在新 state'
        assert old.get(NAME, 'counter', 0) == 1, '旧 state 不得再被触碰'

    def test_init_exposed_for_state_init(self):
        """`init` 由构造形参持有（`Pity` 建初始快照时取用）。"""
        assert CounterTracker(scope=SCOPE, reset_on=SCOPE, init=20).init == 20
        assert CounterTracker(scope=SCOPE, reset_on=SCOPE).init == 0


# ══════════════════════════════════════════════════════════════════
# S1b-2：FlagTracker
# ══════════════════════════════════════════════════════════════════

ROTATING_KW = dict(scope=SCOPE, judge='featured', hit='clear', miss='set',
                   flag='guaranteed')
INVERSE_KW = dict(scope=SCOPE, judge='featured', hit='set', miss='clear',
                  flag='forced_loss')


def _flag_tracker(kw=None, state=None, name=NAME):
    st = state if state is not None else PityState()
    tr = FlagTracker(**(kw or ROTATING_KW))
    tr.rebind(st, name)
    return tr, st


class TestFlagTrackerFlip:
    """`commit` 落翻转——rotating 的二态翻转（§3.2 preset 表）。"""

    def test_flag_tracker_rotating_flip(self):
        """出 scope：命中（featured）→ 清位；未命中 → 置位。出非 scope 不动。"""
        tr, st = _flag_tracker()
        st.set(NAME, 'guaranteed', True)

        tr.commit(_ctx(rarity='sr', state=st), st, NAME)
        assert st.get(NAME, 'guaranteed') is True, '出非触发稀有度不得翻转'

        tr.commit(_ctx(rarity='ssr', is_featured=True, state=st), st, NAME)
        assert st.get(NAME, 'guaranteed') is False, '命中应清位（回到初始态）'

        tr.commit(_ctx(rarity='ssr', is_featured=False, state=st), st, NAME)
        assert st.get(NAME, 'guaranteed') is True, '未命中应置位（进入大保底）'

    def test_flag_tracker_selected_judge_hit(self):
        """`judge='selected'`：命中判据是 `reward_id == selected_card`（读外部注入键）。"""
        tr, st = _flag_tracker(dict(scope=SCOPE, judge='selected', hit='clear',
                                    miss='set', flag='guaranteed'))
        st.set(NAME, 'selected_card', 'up_card')
        st.set(NAME, 'guaranteed', True)

        tr.commit(_ctx(rarity='ssr', reward_id='other_card', state=st), st, NAME)
        assert st.get(NAME, 'guaranteed') is True, '未命中定轨卡应置位'

        tr.commit(_ctx(rarity='ssr', reward_id='up_card', state=st), st, NAME)
        assert st.get(NAME, 'guaranteed') is False, '命中定轨卡应清位'

    def test_flag_tracker_inverse_form_flips_oppositely(self):
        """G1 形态（`hit='set'` / `miss='clear'`，flag=`forced_loss`）翻转方向相反。"""
        tr, st = _flag_tracker(INVERSE_KW)
        tr.commit(_ctx(rarity='ssr', is_featured=True, state=st), st, NAME)
        assert st.get(NAME, 'forced_loss') is True, '连中后进入「必歪」态'
        tr.commit(_ctx(rarity='ssr', is_featured=False, state=st), st, NAME)
        assert st.get(NAME, 'forced_loss') is False, '歪掉后退出「必歪」态'

    def test_flag_tracker_skip_reset_does_not_skip_flip(self):
        """`skip_reset=True` 不跳过翻转——与旧 `RotatingBehavior.after_draw` 同构
        （该参数对事件驱动型不可达：`deactivate_on_early_hit` 被 H3 硬拒）。"""
        tr, st = _flag_tracker()
        st.set(NAME, 'guaranteed', True)
        tr.commit(_ctx(rarity='ssr', is_featured=True, state=st), st, NAME,
                  skip_reset=True)
        assert st.get(NAME, 'guaranteed') is False

    def test_flag_tracker_advance_and_prepare_are_noop(self):
        """非计数型：`advance` / `prepare` 均 no-op（`cr_counter` 归 StreakTracker）。"""
        tr, st = _flag_tracker()
        ctx = _ctx(state=st)
        tr.advance(ctx, st, NAME, False)
        tr.prepare(ctx, st, NAME, False)
        assert st.data.get(NAME, {}) == {}

    def test_flag_tracker_requires_rebind_first(self):
        """未 `rebind` 即 `commit` 是 AttributeError。"""
        tr = FlagTracker(**ROTATING_KW)
        try:
            tr.commit(_ctx(rarity='ssr', is_featured=True), PityState(), NAME)
        except AttributeError:
            return
        raise AssertionError('未 rebind 的 FlagTracker 不应可用')


class TestFlagTrackerDidReset:
    """M4：`did_reset` = 本次写入的是 flag 的初值侧（走到 `clear` 的那一支）。"""

    def test_flag_tracker_did_reset_rotating(self):
        """M4 表行：出 scope ∧ `is_featured`（与 `RotatingBehavior.did_fire` 逐字一致）。"""
        tr, st = _flag_tracker()
        assert tr.did_reset(_ctx(rarity='ssr', is_featured=True, state=st), st, NAME) is True
        assert tr.did_reset(_ctx(rarity='ssr', is_featured=False, state=st), st, NAME) is False
        assert tr.did_reset(_ctx(rarity='sr', is_featured=True, state=st), st, NAME) is False, (
            '须带 scope 门控——「出非 scope 稀有度的 UP」不算回到初始态')

    def test_flag_tracker_did_reset_selected(self):
        """M4 表行：出 scope ∧ `reward_id == selected`。"""
        tr, st = _flag_tracker(dict(scope=SCOPE, judge='selected', hit='clear',
                                    miss='set', flag='guaranteed'))
        st.set(NAME, 'selected_card', 'up_card')
        assert tr.did_reset(_ctx(rarity='ssr', reward_id='up_card', state=st), st, NAME) is True
        assert tr.did_reset(_ctx(rarity='ssr', reward_id='other', state=st), st, NAME) is False
        assert tr.did_reset(_ctx(rarity='sr', reward_id='up_card', state=st), st, NAME) is False

    def test_flag_tracker_inverse_form_did_reset(self):
        """G1 形态：`clear` 落在未命中侧，故 `did_reset` = 出 scope ∧ 未命中。

        G1 的 `rotating_inverse` 不在 §3.1.1 M4 的六行表内，此处按 M4 的**统一语义**
        （「本次抽卡是否让本保底回到初始状态」）推导：`forced_loss` 初值为 False，
        被**置位**表示「进入必歪态」，故置位不算回到初始态、清位才算。若改按
        「judge 命中」实现，本行会在置位时报 True，与统一语义相反。
        """
        tr, st = _flag_tracker(INVERSE_KW)
        assert tr.did_reset(_ctx(rarity='ssr', is_featured=True, state=st), st, NAME) is False
        assert tr.did_reset(_ctx(rarity='ssr', is_featured=False, state=st), st, NAME) is True

    def test_flag_tracker_did_reset_matches_commit_flip_to_initial(self):
        """同一 ctx 下 `did_reset` 为真 ⟺ `commit` 把 flag 写回初值（False）。"""
        for kw in (ROTATING_KW, INVERSE_KW):
            tr, st = _flag_tracker(kw)
            for feat in (True, False):
                st.set(NAME, kw['flag'], not feat)   # 先置于相反态
                ctx = _ctx(rarity='ssr', is_featured=feat, state=st)
                fired = tr.did_reset(ctx, st, NAME)
                tr.commit(ctx, st, NAME)
                back_to_init = st.get(NAME, kw['flag']) is False
                assert fired == back_to_init, f'{kw}: feat={feat} 不一致'


class TestFlagTrackerProtocol:
    """协议面：`state_keys` / `namespace` / 形参校验 / rebind。"""

    def test_flag_tracker_state_keys(self):
        """`state_keys()` = `(flag,)`——`selected_card` 是**读**的键，不进声明集。"""
        assert FlagTracker(**ROTATING_KW).state_keys() == ('guaranteed',)
        assert FlagTracker(**INVERSE_KW).state_keys() == ('forced_loss',)

    def test_flag_tracker_namespace_default_none(self):
        assert FlagTracker(**ROTATING_KW).namespace is None

    def test_flag_tracker_rejects_unknown_judge(self):
        """未知 `judge` / `hit` / `miss` 立即抛错，不静默退化为恒等。"""
        for bad in (dict(scope=SCOPE, judge='nope', hit='clear', miss='set', flag='g'),
                    dict(scope=SCOPE, judge='featured', hit='nope', miss='set', flag='g'),
                    dict(scope=SCOPE, judge='featured', hit='clear', miss='nope',
                         flag='g')):
            try:
                FlagTracker(**bad)
            except ValueError:
                continue
            raise AssertionError(f'未拒绝非法形参: {bad}')

    def test_flag_tracker_rebind_redirects_to_new_state(self):
        """`rebind` 纯重定向——重绑后翻转落在新 state。"""
        tr, old = _flag_tracker()
        old.set(NAME, 'guaranteed', True)
        tr.commit(_ctx(rarity='ssr', is_featured=True, state=old), old, NAME)
        assert old.get(NAME, 'guaranteed') is False

        new = PityState()
        new.set(NAME, 'guaranteed', True)
        tr.rebind(new, NAME)
        tr.commit(_ctx(rarity='ssr', is_featured=True, state=new), new, NAME)
        assert new.get(NAME, 'guaranteed') is False
        assert old.get(NAME, 'guaranteed') is False, '旧 state 不得再被触碰'
