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

import hashlib
import json
import struct
from pathlib import Path

from gacha_simulator.core.pity_primitives import DrawInfo, PityContext, PityState
from gacha_simulator.core.pity_tracker import (
    AlwaysActive, CounterTracker, DependentActive, DependentFiniteActive,
    FateTracker, FiniteActive, FlagTracker, Lifecycle, NamespaceTracker,
    StreakTracker, Tracker,
)

# ══════════════════════════════════════════════════════════════════
# S7e：等价性装置 golden（旧类下线后仍可断言的对照结果）
# ══════════════════════════════════════════════════════════════════
# 本文件里四条「与旧行为类逐位相同」的对照（随机数消费次数、`cr_counter` 轨迹、
# 定轨四键轨迹两条）的对照结果固化在 `tests/fixtures/p64_s7e_golden.json`
# （字段含义见该文件 `_format` 段）。断言一律用**严格 `==`**、不用 `approx`：
# golden 存的是 JSON 原生数，CPython 的 json 写侧用 `float.__repr__`、读侧用正确
# 舍入的 `float()`，故数值位级往返无损。旧类删除时只删「构造旧类并对照」的代码段
# （含 `old_traj == ...` 一侧），对 golden 的断言保留。
_GOLDEN_PATH = Path(__file__).resolve().parents[1] / 'fixtures' / 'p64_s7e_golden.json'
_GOLDEN = json.loads(_GOLDEN_PATH.read_text(encoding='utf-8'))['cases']


def _bits(node):
    """golden 数值载荷的规范位串（float 取 IEEE-754 双精度位模式）。"""
    if isinstance(node, dict):
        return '{' + ','.join(f'{k}={_bits(node[k])}' for k in sorted(node)) + '}'
    if isinstance(node, list):
        return '[' + ','.join(_bits(v) for v in node) + ']'
    if isinstance(node, float):
        return struct.pack('<d', node).hex()
    return repr(node)


def _golden(case_id):
    """取一条 golden 用例；先校验数值载荷与位摘要一致（防手改小数未同步）。"""
    case = _GOLDEN[case_id]
    got = hashlib.sha256(_bits(case['expected']).encode('utf-8')).hexdigest()
    assert got == case['bits_sha256'], (
        f'{case_id}：golden 数值载荷与位摘要不符（小数被改写或精度丢失）')
    return case


def test_golden_equivalence_expectations_are_not_constants():
    """反空转自检：本文件的 golden 载荷不是全零常量、也不是逐输入雷同的假对照。

    **如实登记两处退化**（是发现，不是缺陷）：
    - `tracker.cr_counter_trajectory`：三个种子给出**同一条**轨迹——`cr_counter`
      的推进只由 `(rarity, is_featured)` 决定，随机掷骰结果不进该键（实测五个种子
      1/7/42/999/123456 轨迹一致）。故本条的判别力来自「1..4 的阶梯形态」，
      种子维度对它是**不变量**。
    - `tracker.fate_trajectory.unselected`：四键全为默认 0（「整段不动」），
      判别力在「未被写入」而非数值差异。
    """
    counts = _golden('tracker.random_consumption')['expected']
    assert set(counts) == {0, 1}, '「不掷」与「掷 1 次」两类须并存（当前全同即退化）'

    per_seed = _golden('tracker.cr_counter_trajectory')['expected']
    assert len(per_seed) == 3
    assert all(len(set(traj)) == 4 for traj in per_seed.values()), \
        '轨迹须覆盖 1..4 四档（顺序契约失效时退化为全 0）'

    selected = _golden('tracker.fate_trajectory.selected')['expected']
    assert len({tuple(row) for row in selected}) > 1, '定轨轨迹不许是常量'

    unselected = _golden('tracker.fate_trajectory.unselected')['expected']
    assert set(unselected) == {0}, '未定轨那条登记为常量（判别力在「未被写入」）'


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
        """`skip_reset=True` 不跳过翻转：本形参是 counter 家族专享的例外通道
        （见 `Tracker.commit` 的「适用范围」段），事件驱动族一律不消费它，与旧
        `RotatingBehavior.after_draw` 逐行同构。

        **S6a 审查收口**：本用例**守的行为未变**（仍断言标志照翻），只改理由。原文
        的理由「该参数对事件驱动型不可达（`deactivate_on_early_hit` 被 H3 硬拒）」
        已随 S6a 删除拒绝分支而作废，此处的判据改为族属划线。
        """
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


# ══════════════════════════════════════════════════════════════════
# S1c-1：StreakTracker（rotating_cr 的捕获明光）
# ══════════════════════════════════════════════════════════════════

CR_KW = dict(scope=SCOPE, judge='featured', threshold=3, base_rate=0.018,
             state_probs=[0.0, 0.0, 0.75, 1.0])
CR_NAME = 'ssr_cr'


def _cr_ctx(rarity='sr', is_featured=False, state=None, current=None):
    st = state if state is not None else PityState()
    draw = DrawInfo(
        pool_id='p', pool_instance_id='p_0', reward_id=f'{rarity}_card',
        reward_rarity=rarity, is_featured=is_featured,
        scope_slots={'ssr': ('ssr', 'ssr_featured')},
        featured_slots={'ssr': ('ssr_featured',)},
    )
    return PityContext(
        draw=draw, state=st,
        current=current if current is not None else {'ssr': 0.01, 'ssr_featured': 0.005},
    )


def _cr_tracker(kw=None, state=None):
    st = state if state is not None else PityState()
    tr = StreakTracker(**(kw or CR_KW))
    tr.rebind(st, CR_NAME)
    return tr, st


class TestStreakTrackerN1Phase:
    """`cr_counter` 不属计数型——`advance` 为 no-op，掷骰在 `prepare`（裁决 6B′）。"""

    def test_advance_does_not_touch_cr_counter(self):
        """`advance` 是 no-op——若按「计数器」字面把它划入计数型，会每抽多推一次。"""
        tr, st = _cr_tracker()
        tr.advance(_cr_ctx(state=st), st, CR_NAME, False)
        assert st.get(CR_NAME, 'cr_counter', 0) == 0
        assert st.data.get(CR_NAME, {}) == {}

    def test_prepare_sets_flag_on_deterministic_intercept(self):
        """`state_prob >= 1.0` 确定性触发：置位 flag，且**不消耗随机数**。"""
        # state_probs 显式取 [1.0]，使 idx=0 即命中 1.0（确定性触发）
        tr, st = _cr_tracker(dict(CR_KW, base_rate=0.0, state_probs=[1.0]))
        tr.prepare(_cr_ctx(state=st), st, CR_NAME, False)
        assert st.get(CR_NAME, 'cr_intercepted') is True

    def test_prepare_clears_flag_when_no_intercept(self):
        """未拦截时**清位**——旧实现只在命中分支 return，照搬会让脏 flag 残留、
        拦截率被静默抬高。"""
        tr, st = _cr_tracker(dict(CR_KW, base_rate=0.0, state_probs=[0.0]))
        st.set(CR_NAME, 'cr_intercepted', True)      # 上一次掷中的残留
        tr.prepare(_cr_ctx(state=st), st, CR_NAME, False)
        assert st.get(CR_NAME, 'cr_intercepted') is False

    def test_prepare_clears_flag_when_guard_flag_set(self):
        """`guard_flag` 已置位：不掷骰，且清位防脏残留。"""
        tr, st = _cr_tracker()
        st.set(CR_NAME, 'guaranteed', True)
        st.set(CR_NAME, 'cr_intercepted', True)
        tr.prepare(_cr_ctx(state=st), st, CR_NAME, False)
        assert st.get(CR_NAME, 'cr_intercepted') is False

    def test_prepare_readonly_does_not_roll_or_write(self):
        """`readonly=True`：不掷骰、**不写**状态（纯查询不得改状态）。"""
        tr, st = _cr_tracker()
        st.set(CR_NAME, 'cr_intercepted', True)
        before = dict(st.data.get(CR_NAME, {}))
        tr.prepare(_cr_ctx(state=st), st, CR_NAME, True)
        assert st.data.get(CR_NAME, {}) == before


class TestStreakTrackerCommit:
    """`commit` 只更新 `cr_counter`；`was_guaranteed` 取**抽前**值（顺序契约）。"""

    def test_commit_updates_cr_counter(self):
        """出 scope：命中 → 归零；未命中 → 累积。出非 scope 不动。"""
        tr, st = _cr_tracker()
        tr.commit(_cr_ctx(rarity='ssr', is_featured=False, state=st), st, CR_NAME)
        tr.commit(_cr_ctx(rarity='ssr', is_featured=False, state=st), st, CR_NAME)
        assert st.get(CR_NAME, 'cr_counter', 0) == 2

        tr.commit(_cr_ctx(rarity='sr', is_featured=True, state=st), st, CR_NAME)
        assert st.get(CR_NAME, 'cr_counter', 0) == 2, '出非 scope 不得动 cr_counter'

        tr.commit(_cr_ctx(rarity='ssr', is_featured=True, state=st), st, CR_NAME)
        assert st.get(CR_NAME, 'cr_counter', 0) == 0

    def test_commit_skips_when_guaranteed_was_set_before_draw(self):
        """抽前 `guaranteed` 已置位 → `cr_counter` 不动（旧 `was_guaranteed` 分支）。

        读点由 `[StreakTracker, FlagTracker]` 的顺序契约保证——此处显式先跑
        `StreakTracker.commit`，此时 `FlagTracker` 尚未翻转 `guaranteed`。
        """
        tr, st = _cr_tracker()
        st.set(CR_NAME, 'guaranteed', True)
        tr.commit(_cr_ctx(rarity='ssr', is_featured=False, state=st), st, CR_NAME)
        assert st.get(CR_NAME, 'cr_counter', 0) == 0, '抽前已 guaranteed 时不得累积'

    def test_did_reset_is_false(self):
        """M4：`cr_counter` 归零是族内子状态，不构成「本保底回到初始状态」。"""
        tr, st = _cr_tracker()
        assert tr.did_reset(_cr_ctx(rarity='ssr', is_featured=True, state=st), st, CR_NAME) is False
        assert tr.did_reset(_cr_ctx(rarity='ssr', is_featured=False, state=st), st, CR_NAME) is False

    def test_state_keys_declares_both_keys(self):
        """`state_keys()` = `('cr_counter', flag)`——它多写一个拦截标记键。"""
        assert StreakTracker(**CR_KW).state_keys() == ('cr_counter', 'cr_intercepted')

    def test_rejects_unknown_judge(self):
        try:
            StreakTracker(scope=SCOPE, judge='nope')
        except ValueError:
            return
        raise AssertionError('未拒绝非法 judge')


class TestStreakTrackerH4RandomConsumption:
    """H4：随机数消费次数与旧 `RotatingCRBehavior.before_draw` **逐位相同**。

    表驱动：每组条件分别在旧类与新 Tracker 上跑一次，用同一个计数桩替换
    `random.random`，比对调用次数。四条「不消耗随机数」的路径（readonly /
    guard_flag / `state_prob >= 1.0` / `state_prob <= 0`）另加空表与
    `base_rate == 0` 两条，逐条覆盖。
    """

    CASES = [
        # (guaranteed, readonly, cr_counter, base_rate, state_probs, 说明)
        (False, False, 0, 0.0,   [0.0, 0.0, 0.0, 1.0], 'state_prob=0 → 不掷'),
        (False, False, 1, 0.0,   [0.0, 0.0, 0.0, 1.0], 'state_prob=0 → 不掷'),
        (False, False, 3, 0.0,   [0.0, 0.0, 0.0, 1.0], 'idx 命中 1.0 → 确定性，不掷'),
        (False, False, 9, 0.0,   [0.0, 0.0, 0.75, 1.0], '下标裁剪到 3 → 确定性，不掷'),
        (False, False, 2, 0.0,   [0.0, 0.0, 0.75, 1.0], 'state_prob=0.75 → 掷 1 次'),
        (False, False, 0, 0.018, [0.0, 0.0, 0.0, 1.0], 'base_rate 掷 1 次（失败）'),
        (False, False, 0, 0.018, [],                    '空表 → idx=-1，仅 base_rate 掷'),
        (True,  False, 0, 0.018, [0.0, 0.0, 0.0, 1.0], 'guaranteed → 不掷'),
        (False, True,  0, 0.018, [0.0, 0.0, 0.0, 1.0], 'readonly → 不掷'),
    ]

    def test_random_consumption_matches_old_behavior(self, monkeypatch):
        import random as _random
        from gacha_simulator.core.pity import RotatingCRBehavior

        golden = _golden('tracker.random_consumption')
        assert [list(row) for row in self.CASES] == golden['input']['cases'], \
            '输入漂移：条件表与 golden 不同'
        counts = golden['expected']

        for idx, (guaranteed, readonly, counter, base_rate, probs, why) in \
                enumerate(self.CASES):
            calls = {'n': 0}

            def fake_random():
                calls['n'] += 1
                return 0.5          # base_rate=0.018 → 失败；state_prob=0.75 → 命中

            monkeypatch.setattr(_random, 'random', fake_random)

            # 旧实现
            old_st = PityState()
            old = RotatingCRBehavior('cr', old_st, scope=SCOPE, cr_counter_threshold=3,
                                     cr_base_rate=base_rate, cr_state_probs=probs)
            if guaranteed:
                old_st.set('cr', 'guaranteed', True)
            old_st.set('cr', 'cr_counter', counter)
            calls['n'] = 0
            old.before_draw(_cr_ctx(state=old_st), readonly=readonly)
            old_n = calls['n']

            # 新实现
            new_st = PityState()
            tr = StreakTracker(scope=SCOPE, judge='featured', threshold=3,
                               base_rate=base_rate, state_probs=probs)
            tr.rebind(new_st, 'cr')
            if guaranteed:
                new_st.set('cr', 'guaranteed', True)
            new_st.set('cr', 'cr_counter', counter)
            calls['n'] = 0
            tr.prepare(_cr_ctx(state=new_st), new_st, 'cr', readonly)
            new_n = calls['n']

            assert old_n == new_n, (
                f'{why}：旧实现掷 {old_n} 次、新实现掷 {new_n} 次'
                f'（guaranteed={guaranteed} readonly={readonly} counter={counter} '
                f'base_rate={base_rate} probs={probs}）'
            )
            assert old_n == counts[idx], f'{why}：旧实现消费次数与 golden 不等'
            assert new_n == counts[idx], f'{why}：新实现消费次数与 golden 不等'

    def test_cr_counter_trajectory_matches_old_behavior(self, monkeypatch):
        """15 抽序列下 `cr_counter` 轨迹与旧实现逐位相同（含 `was_guaranteed` 读点）。

        **S7e 如实登记**：本条的 golden 对三个种子给出**同一条**轨迹——`cr_counter`
        只由 `(rarity, is_featured)` 驱动，随机掷骰结果不进该键。故种子循环是保留
        既有形态，判别力来自「1..4 阶梯」而非种子差异。
        """
        import random as _random
        from gacha_simulator.core.pity import RotatingCRBehavior

        def make_rng(seed):
            rng = _random.Random(seed)
            return lambda: rng.random()

        # 抽卡序列：(rarity, is_featured)
        seq = [('ssr', False), ('sr', False), ('ssr', True), ('ssr', False),
               ('ssr', False), ('ssr', True), ('ssr', False), ('sr', True),
               ('ssr', False), ('ssr', False), ('ssr', True), ('ssr', False),
               ('ssr', False), ('ssr', False), ('ssr', True)]

        golden = _golden('tracker.cr_counter_trajectory')
        assert [list(s) for s in seq] == golden['input']['seq'], \
            '输入漂移：抽卡序列与 golden 不同'
        assert list(golden['input']['seeds']) == [1, 7, 42], '输入漂移：种子表与 golden 不同'

        for seed in (1, 7, 42):
            old_st = PityState()
            old = RotatingCRBehavior('cr', old_st, scope=SCOPE, cr_counter_threshold=3,
                                     cr_base_rate=0.018, cr_state_probs=[0.0, 0.0, 0.75, 1.0])
            monkeypatch.setattr(_random, 'random', make_rng(seed))
            old_traj = []
            for rarity, feat in seq:
                ctx = _cr_ctx(rarity=rarity, is_featured=feat, state=old_st)
                old.before_draw(ctx)
                old.after_draw(ctx)
                old_traj.append(old_st.get('cr', 'cr_counter', 0))

            new_st = PityState()
            streak = StreakTracker(scope=SCOPE, judge='featured', threshold=3,
                                   base_rate=0.018, state_probs=[0.0, 0.0, 0.75, 1.0])
            flag = FlagTracker(scope=SCOPE, judge='featured', hit='clear', miss='set',
                               flag='guaranteed')
            streak.rebind(new_st, 'cr')
            flag.rebind(new_st, 'cr')
            monkeypatch.setattr(_random, 'random', make_rng(seed))
            new_traj = []
            for rarity, feat in seq:
                ctx = _cr_ctx(rarity=rarity, is_featured=feat, state=new_st)
                streak.prepare(ctx, new_st, 'cr', False)      # 掷骰相位
                # 顺序契约：StreakTracker 在前，读到的 guaranteed 是抽前值
                streak.commit(ctx, new_st, 'cr')
                flag.commit(ctx, new_st, 'cr')
                new_traj.append(new_st.get('cr', 'cr_counter', 0))

            assert old_traj == new_traj, f'seed={seed}：旧 {old_traj} 新 {new_traj}'
            exp = golden['expected'][str(seed)]
            assert old_traj == exp, f'seed={seed}：旧实现轨迹与 golden 不等'
            assert new_traj == exp, f'seed={seed}：新实现轨迹与 golden 不等'


# ══════════════════════════════════════════════════════════════════
# S1c-2：FateTracker（定轨）+ NamespaceTracker
# ══════════════════════════════════════════════════════════════════

FATE_NAME = 'ssr_targeted'
FATE_KEYS = ('fate_points', 'losses', 'guaranteed', 'lost_rotating')
FATE_KW = dict(scope=SCOPE, judge='selected', hit='clear', miss='accumulate',
               keys=FATE_KEYS)


def _fate_tracker(kw=None, state=None, selected='up_card'):
    st = state if state is not None else PityState()
    tr = FateTracker(**(kw or FATE_KW))
    tr.rebind(st, FATE_NAME)
    if selected is not None:
        st.set(FATE_NAME, 'selected_card', selected)
    return tr, st


class TestFateTrackerCommit:
    """`commit` 的命中清零 / 未命中累积（逐行对齐旧 `TargetedBehavior.after_draw`）。"""

    def test_fate_tracker_miss_accumulates(self):
        """出 scope 且未命中定轨：计数器 +1、标记置位（四键齐动）。"""
        tr, st = _fate_tracker()
        tr.commit(_ctx(rarity='ssr', reward_id='other', state=st), st, FATE_NAME)
        assert st.get(FATE_NAME, 'fate_points', 0) == 1
        assert st.get(FATE_NAME, 'losses', 0) == 1
        assert st.get(FATE_NAME, 'guaranteed') is True
        assert st.get(FATE_NAME, 'lost_rotating') is True

    def test_fate_tracker_hit_clears_all_keys(self):
        """出 scope 且命中定轨：计数器归零、标记清位。"""
        tr, st = _fate_tracker()
        tr.commit(_ctx(rarity='ssr', reward_id='other', state=st), st, FATE_NAME)
        tr.commit(_ctx(rarity='ssr', reward_id='other', state=st), st, FATE_NAME)
        assert st.get(FATE_NAME, 'fate_points', 0) == 2

        tr.commit(_ctx(rarity='ssr', reward_id='up_card', state=st), st, FATE_NAME)
        assert st.get(FATE_NAME, 'fate_points', 0) == 0
        assert st.get(FATE_NAME, 'losses', 0) == 0
        assert st.get(FATE_NAME, 'guaranteed') is False
        assert st.get(FATE_NAME, 'lost_rotating') is False

    def test_fate_tracker_out_of_scope_no_change(self):
        """出非 scope 稀有度：整段不动（即使 reward_id 等于定轨卡）。"""
        tr, st = _fate_tracker()
        tr.commit(_ctx(rarity='sr', reward_id='up_card', state=st), st, FATE_NAME)
        assert st.get(FATE_NAME, 'fate_points', 0) == 0
        assert st.get(FATE_NAME, 'guaranteed') is None, '不得写任何键'

    def test_fate_tracker_selected_none_no_change(self):
        """未定轨（`selected_card is None`）：整段不动。

        旧 `after_draw` 的 `if selected is None: return`——缺这一条则「未定轨」会
        被当成「未命中」而累积 `losses` / 置位 `guaranteed`。
        """
        tr, st = _fate_tracker(selected=None)
        st.set(FATE_NAME, 'selected_card', None)     # 无条件注入的 None
        tr.commit(_ctx(rarity='ssr', reward_id='any', state=st), st, FATE_NAME)
        assert st.get(FATE_NAME, 'fate_points', 0) == 0
        assert st.get(FATE_NAME, 'losses', 0) == 0
        assert st.get(FATE_NAME, 'guaranteed') is None

    def test_fate_tracker_advance_and_prepare_are_noop(self):
        """非计数型：`advance` / `prepare` 均 no-op。"""
        tr, st = _fate_tracker()
        ctx = _ctx(state=st)
        tr.advance(ctx, st, FATE_NAME, False)
        tr.prepare(ctx, st, FATE_NAME, False)
        assert st.get(FATE_NAME, 'fate_points', 0) == 0
        assert st.get(FATE_NAME, 'guaranteed') is None


class TestFateTrackerDidReset:
    """M4：出 scope ∧ 命中定轨（§3.1.1 M4 表行）。"""

    def test_fate_tracker_did_reset(self):
        tr, st = _fate_tracker()
        assert tr.did_reset(_ctx(rarity='ssr', reward_id='up_card', state=st),
                            st, FATE_NAME) is True
        assert tr.did_reset(_ctx(rarity='ssr', reward_id='other', state=st),
                            st, FATE_NAME) is False
        assert tr.did_reset(_ctx(rarity='sr', reward_id='up_card', state=st),
                            st, FATE_NAME) is False, '须带 scope 门控'

    def test_fate_tracker_did_reset_false_when_not_selected(self):
        """未定轨时恒 False（与旧 `_is_hit` 在 `selected is None` 时返回 False 一致）。"""
        tr, st = _fate_tracker(selected=None)
        st.set(FATE_NAME, 'selected_card', None)
        assert tr.did_reset(_ctx(rarity='ssr', reward_id='up_card', state=st),
                            st, FATE_NAME) is False

    def test_fate_tracker_did_reset_matches_commit_clear_branch(self):
        """`did_reset` 为真 ⟺ `commit` 走了 `clear` 分支。"""
        for rarity, rid in (('ssr', 'up_card'), ('ssr', 'other'),
                            ('sr', 'up_card')):
            tr, st = _fate_tracker()
            st.set(FATE_NAME, 'fate_points', 3)
            ctx = _ctx(rarity=rarity, reward_id=rid, state=st)
            fired = tr.did_reset(ctx, st, FATE_NAME)
            tr.commit(ctx, st, FATE_NAME)
            cleared = st.get(FATE_NAME, 'fate_points', 0) == 0
            assert fired == cleared, f'{rarity}/{rid}: {fired} vs {cleared}'


class TestFateTrackerProtocol:
    """协议面与形参校验。"""

    def test_fate_tracker_state_keys(self):
        """`state_keys()` = `keys` 形参——只含「写」的键，`selected_card` 不在内。"""
        assert FateTracker(**FATE_KW).state_keys() == FATE_KEYS
        assert FateTracker(scope=SCOPE, judge='selected', hit='clear',
                           miss='accumulate', keys=('fate_points',)).state_keys() == \
            ('fate_points',)

    def test_fate_tracker_namespace_default_none(self):
        assert FateTracker(**FATE_KW).namespace is None

    def test_fate_tracker_rejects_unknown_key(self):
        """未知状态键抛 `ValueError`，不静默当成标记处理。"""
        try:
            FateTracker(scope=SCOPE, judge='selected', hit='clear',
                        miss='accumulate', keys=('fate_points', 'no_such_key'))
        except ValueError:
            return
        raise AssertionError('未拒绝未知状态键')

    def test_fate_tracker_rejects_unknown_action_and_judge(self):
        for bad in (dict(scope=SCOPE, judge='nope', hit='clear',
                         miss='accumulate', keys=FATE_KEYS),
                    dict(scope=SCOPE, judge='selected', hit='nope',
                         miss='accumulate', keys=FATE_KEYS),
                    dict(scope=SCOPE, judge='selected', hit='clear',
                         miss='nope', keys=FATE_KEYS)):
            try:
                FateTracker(**bad)
            except ValueError:
                continue
            raise AssertionError(f'未拒绝非法形参: {bad}')

    def test_fate_tracker_requires_rebind_first(self):
        """未 `rebind` 即 `commit` 当场报错，不静默成功。

        具体异常类型按族的实现而异（`CounterTracker` 是 `None.incr()` 的
        `AttributeError`，本族是空控制器字典的 `KeyError`），契约是「未重绑即报错」
        而非某一种异常类型。此处须先置 `selected_card`，否则会在旧实现同源的
        「未定轨整段不动」早退处返回，走不到控制器查表。
        """
        tr = FateTracker(**FATE_KW)
        st = PityState()
        st.set(FATE_NAME, 'selected_card', 'up_card')
        try:
            tr.commit(_ctx(rarity='ssr', reward_id='up_card', state=st), st, FATE_NAME)
        except (AttributeError, KeyError):
            return
        raise AssertionError('未 rebind 的 FateTracker 不应可用')

    def test_fate_tracker_trajectory_matches_old_behavior(self):
        """12 抽序列下四个键的轨迹与旧 `TargetedBehavior.after_draw` 逐位相同。"""
        from gacha_simulator.core.pity import TargetedBehavior

        seq = [('ssr', 'other'), ('sr', 'up_card'), ('ssr', 'up_card'),
               ('ssr', 'other'), ('ssr', 'other'), ('sr', 'other'),
               ('ssr', 'other'), ('ssr', 'up_card'), ('ssr', 'other'),
               ('ssr', 'other'), ('ssr', 'up_card'), ('ssr', 'other')]

        golden = _golden('tracker.fate_trajectory.selected')
        assert [list(s) for s in seq] == golden['input']['seq'], \
            '输入漂移：抽卡序列与 golden 不同'
        assert list(golden['input']['keys']) == list(FATE_KEYS), \
            '输入漂移：四键与 golden 不同'

        old_st = PityState()
        old = TargetedBehavior('tg', old_st, scope=SCOPE, fate_threshold=2)
        old_st.set('tg', 'selected_card', 'up_card')
        old_traj = []
        for rarity, rid in seq:
            old.after_draw(_ctx(rarity=rarity, reward_id=rid, state=old_st))
            old_traj.append(tuple(old_st.get('tg', k, 0) for k in FATE_KEYS))

        new_st = PityState()
        fate = FateTracker(**FATE_KW)
        fate.rebind(new_st, 'tg')
        new_st.set('tg', 'selected_card', 'up_card')
        new_traj = []
        for rarity, rid in seq:
            fate.commit(_ctx(rarity=rarity, reward_id=rid, state=new_st), new_st, 'tg')
            new_traj.append(tuple(new_st.get('tg', k, 0) for k in FATE_KEYS))

        assert old_traj == new_traj, f'旧 {old_traj}\n新 {new_traj}'
        assert [list(t) for t in old_traj] == golden['expected'], '旧类侧轨迹与 golden 不等'
        assert [list(t) for t in new_traj] == golden['expected'], '生产侧轨迹与 golden 不等'

    def test_fate_tracker_trajectory_matches_old_when_not_selected(self):
        """未定轨（`selected_card=None`）时两侧轨迹同为「整段不动」。"""
        from gacha_simulator.core.pity import TargetedBehavior

        golden = _golden('tracker.fate_trajectory.unselected')

        old_st = PityState()
        old = TargetedBehavior('tg', old_st, scope=SCOPE, fate_threshold=2)
        old_st.set('tg', 'selected_card', None)
        old.after_draw(_ctx(rarity='ssr', reward_id='any', state=old_st))

        new_st = PityState()
        fate = FateTracker(**FATE_KW)
        fate.rebind(new_st, 'tg')
        new_st.set('tg', 'selected_card', None)
        fate.commit(_ctx(rarity='ssr', reward_id='any', state=new_st), new_st, 'tg')

        for k in FATE_KEYS:
            assert old_st.get('tg', k, 0) == new_st.get('tg', k, 0), k
        assert [old_st.get('tg', k, 0) for k in FATE_KEYS] == golden['expected'], \
            '旧类侧与 golden 不等'
        assert [new_st.get('tg', k, 0) for k in FATE_KEYS] == golden['expected'], \
            '生产侧与 golden 不等'
        assert new_st.get('tg', 'fate_points', 0) == 0


class TestNamespaceTracker:
    """命名空间载体（ISSUE-407）——语义为空，只声明命名空间。"""

    def test_namespace_tracker_declares_namespace_only(self):
        """`namespace` 是构造形参，`state_keys()` 为空、构造后不写任何 state 键。"""
        tr = NamespaceTracker(namespace='ssr_soft')
        st = PityState()
        ctx = _ctx(state=st)
        tr.rebind(st, 'ssr')
        tr.advance(ctx, st, 'ssr', False)
        tr.prepare(ctx, st, 'ssr', False)
        tr.commit(ctx, st, 'ssr')
        assert tr.did_reset(ctx, st, 'ssr') is False
        assert tr.namespace == 'ssr_soft'
        assert tr.state_keys() == ()
        assert st.data == {}, '构造后不得新增任何键（X_soft._active 由 Lifecycle 写）'

    def test_namespace_tracker_rejects_empty_namespace(self):
        try:
            NamespaceTracker(namespace='')
        except ValueError:
            return
        raise AssertionError('未拒绝空 namespace')


# ══════════════════════════════════════════════════════════════════
# S1d：Lifecycle 五方法族 + build_lifecycle
# ══════════════════════════════════════════════════════════════════

from gacha_simulator.core.pity_primitives import LifecycleConfig  # noqa: E402
from gacha_simulator.core.pity import build_lifecycle  # noqa: E402
from gacha_simulator.core.config_store import PityDef  # noqa: E402

LC_NAME = 'ssr_hard'


def _pdef(**kw):
    pd = PityDef(name='x', btype='hard')
    for k, v in kw.items():
        setattr(pd, k, v)
    return pd


class TestBuildLifecycle:
    """`build_lifecycle` 按 §3.1.3 的四组合取值表逐行。"""

    def test_build_lifecycle_four_combinations(self):
        """`depends_on` 空/非空 × `max_triggers` 0/正——四组合各自产出对应类。

        两维**独立**取值（2026-09-28 修正）：`depends_on` 非空**不**吞掉
        `max_triggers`，两维同时配置时产出 `DependentFiniteActive`。
        """
        for kw, want, keys in [
            ({}, 'AlwaysActive', ()),
            ({'max_triggers': 2}, 'FiniteActive', ('triggers',)),
            ({'depends_on': 'src'}, 'DependentActive', ()),
            ({'depends_on': 'src', 'max_triggers': 3}, 'DependentFiniteActive',
             ('triggers',)),
        ]:
            lc = build_lifecycle(_pdef(**kw))
            assert type(lc).__name__ == want, f'{kw} → {type(lc).__name__}'
            assert lc.state_keys() == keys, f'{kw} 的 state_keys 不符'

    def test_build_lifecycle_carries_both_cfg_fields(self):
        """`cfg` 的两个字段四个组合都带入，且两个属性在**全部四类**上都可读
        （ISSUE-406：`_build_activation_graph` 对每条 behavior 读 `lc.depends_on`）。"""
        for kw in ({}, {'max_triggers': 2}, {'depends_on': 'src'},
                   {'depends_on': 'src', 'max_triggers': 3}):
            lc = build_lifecycle(_pdef(deactivate_on_early_hit=True, **kw))
            assert lc.deactivate_on_early_hit is True
            assert lc.depends_on == kw.get('depends_on')
            assert lc.namespace is None

    def test_build_lifecycle_retirement_axis_is_max_triggers(self):
        """退役维取 `max_triggers`，**不是** `deactivate_on_early_hit`。

        后者是与两维正交的第三个开关——只配它时仍产出 `AlwaysActive`，
        退役由 `should_deactivate` 单独判定。
        """
        lc = build_lifecycle(_pdef(deactivate_on_early_hit=True))
        assert isinstance(lc, AlwaysActive)
        assert lc.state_keys() == ()


class TestLifecycleInitialize:
    """`initialize` 的写入面：`Always` 维写 `name` + 每个命名空间；`Dependent` 维空实现。"""

    def test_always_active_writes_name_and_namespaces(self):
        lc = build_lifecycle(_pdef())
        st = PityState()
        lc.initialize(st, LC_NAME, ('ssr_soft',))
        assert st.get(LC_NAME, '_active') is True
        assert st.get('ssr_soft', '_active') is True, '命名空间须一并写入（ISSUE-407）'

    def test_finite_active_writes_active_too(self):
        """`FiniteActive` 首触发前生效，与 `AlwaysActive` 同。"""
        lc = build_lifecycle(_pdef(max_triggers=2))
        st = PityState()
        lc.initialize(st, LC_NAME, ())
        assert st.get(LC_NAME, '_active') is True

    def test_dependent_active_initialize_is_noop(self):
        """`Dependent*` 不写 `_active`——由引擎的 `depends_on` 传播置位。"""
        for kw in ({'depends_on': 'src'}, {'depends_on': 'src', 'max_triggers': 2}):
            lc = build_lifecycle(_pdef(**kw))
            st = PityState()
            lc.initialize(st, LC_NAME, ('ssr_soft',))
            assert st.get(LC_NAME, '_active') is None, f'{kw} 不得写 _active'
            assert st.get('ssr_soft', '_active') is None

    def test_initialize_dedupes_name_in_namespaces(self):
        """`name` 也在 `namespaces` 里时不重复（并集语义）。"""
        lc = build_lifecycle(_pdef())
        st = PityState()
        lc.initialize(st, LC_NAME, (LC_NAME, 'ssr_soft'))
        assert set(lc._ns_active) == {LC_NAME, 'ssr_soft'}


class TestLifecycleRetirement:
    """`should_deactivate` 的四实参语义 + `Finite*` 的触发计数。"""

    def test_should_deactivate_explicit_fired_both_states(self):
        """四实参形态：`fired` 真 / 假两态各一条（未配退役条件时恒 False）。"""
        lc = build_lifecycle(_pdef())
        st = PityState()
        ctx = _ctx(state=st)
        assert lc.should_deactivate(ctx, st, LC_NAME, False) is False
        assert lc.should_deactivate(ctx, st, LC_NAME, True) is False

    def test_deactivate_on_early_hit_retires_on_fired(self):
        """配 `deactivate_on_early_hit` 时：`fired=True` → 退役；`False` → 不退役。"""
        lc = build_lifecycle(_pdef(deactivate_on_early_hit=True))
        st = PityState()
        ctx = _ctx(state=st)
        assert lc.should_deactivate(ctx, st, LC_NAME, False) is False
        assert lc.should_deactivate(ctx, st, LC_NAME, True) is True

    def test_finite_active_counts_only_on_fired(self):
        """`triggers` **只在 `fired` 时累加**——无条件累加会退化为「抽数」。

        `max_triggers=2` 若按抽数计会在第 2 抽退役，与「触发 N 次后退役」相反。
        """
        lc = build_lifecycle(_pdef(max_triggers=2))
        st = PityState()
        ctx = _ctx(state=st)
        for _ in range(5):
            assert lc.should_deactivate(ctx, st, LC_NAME, False) is False
        assert st.get(LC_NAME, 'triggers', 0) == 0, '未触发不得累加'

        assert lc.should_deactivate(ctx, st, LC_NAME, True) is False
        assert st.get(LC_NAME, 'triggers', 0) == 1
        assert lc.should_deactivate(ctx, st, LC_NAME, True) is True
        assert st.get(LC_NAME, 'triggers', 0) == 2

    def test_dependent_finite_counts_after_activation(self):
        """`DependentFiniteActive` 同样按 `fired` 计数（自激活后起算由骨架的
        `is_active` 早退保证，本层只验计数）。"""
        lc = build_lifecycle(_pdef(depends_on='src', max_triggers=1))
        st = PityState()
        ctx = _ctx(state=st)
        assert lc.should_deactivate(ctx, st, LC_NAME, True) is True
        assert st.get(LC_NAME, 'triggers', 0) == 1

    def test_triggers_not_stored_on_lifecycle_object(self):
        """计数落在 state 而非 Lifecycle 对象上——对象在同一 worker 内跨模拟复用，
        对象内计数会跨模拟泄漏（破坏「固定种子可复现」）。"""
        lc = build_lifecycle(_pdef(max_triggers=2))
        a, b = PityState(), PityState()
        ctx_a, ctx_b = _ctx(state=a), _ctx(state=b)
        lc.should_deactivate(ctx_a, a, LC_NAME, True)
        assert lc.should_deactivate(ctx_b, b, LC_NAME, True) is False, \
            '第二个 state 的计数须从 0 起算'
        assert a.get(LC_NAME, 'triggers', 0) == 1
        assert b.get(LC_NAME, 'triggers', 0) == 1


class TestLifecycleProtocol:
    """`is_active` / `deactivate` / `rebind` 对称性 / `state_keys` / `namespace`。"""

    def test_is_active_reads_default_false(self):
        lc = build_lifecycle(_pdef())
        st = PityState()
        assert lc.is_active(st, LC_NAME) is False, '缺键时默认 False（对齐旧引擎）'
        lc.initialize(st, LC_NAME, ())
        assert lc.is_active(st, LC_NAME) is True

    def test_deactivate_clears_only_name(self):
        """`deactivate` 只清 `name` 的 `_active`，命名空间的与旧实现同形（不被触碰）。"""
        lc = build_lifecycle(_pdef())
        st = PityState()
        lc.initialize(st, LC_NAME, ('ssr_soft',))
        lc.deactivate(st, LC_NAME)
        assert st.get(LC_NAME, '_active') is False
        assert st.get('ssr_soft', '_active') is True, '命名空间的 _active 不被 deactivate 触碰'

    def test_rebind_is_symmetric_with_initialize(self):
        """`rebind(state, name, namespaces)` 与 `initialize` 实参面对称——对**并集中
        每个** Flag 重定向（ISSUE-917）：只重绑 `name` 会让 `X_soft` 的 Flag 在
        worker 内连跑第 2..N 场时仍指上一场 state。"""
        lc = build_lifecycle(_pdef())
        old = PityState()
        lc.initialize(old, LC_NAME, ('ssr_soft',))
        assert old.get(LC_NAME, '_active') is True

        new = PityState()
        lc.rebind(new, LC_NAME, ('ssr_soft',))
        assert lc._ns_active[LC_NAME]._state is new
        assert lc._ns_active['ssr_soft']._state is new, '命名空间的 Flag 须同批重定向'

        lc.deactivate(new, LC_NAME)
        assert new.get(LC_NAME, '_active') is False
        assert old.get(LC_NAME, '_active') is True, '旧 state 不得再被触碰'

    def test_state_keys_all_four(self):
        """`state_keys()`：`Finite*` 且 `max_triggers > 0` 时为 `('triggers',)`，其余 `()`。"""
        assert build_lifecycle(_pdef()).state_keys() == ()
        assert build_lifecycle(_pdef(max_triggers=1)).state_keys() == ('triggers',)
        assert build_lifecycle(_pdef(depends_on='s')).state_keys() == ()
        assert build_lifecycle(_pdef(depends_on='s', max_triggers=1)).state_keys() == \
            ('triggers',)

    def test_namespace_default_none(self):
        assert build_lifecycle(_pdef()).namespace is None

    def test_base_lifecycle_defaults(self):
        """基类默认形态即「无退役条件的 Always 维」——五方法均可直接调用。"""
        lc = Lifecycle()
        st = PityState()
        ctx = _ctx(state=st)
        lc.initialize(st, LC_NAME, ())
        assert lc.is_active(st, LC_NAME) is True
        assert lc.should_deactivate(ctx, st, LC_NAME, True) is False
        lc.rebind(st, LC_NAME, ())
        lc.deactivate(st, LC_NAME)
        assert lc.state_keys() == ()
        assert lc.depends_on is None
        assert lc.deactivate_on_early_hit is False

    def test_lifecycle_config_default_bag(self):
        """未传 `cfg` 时构造默认参数袋（骨架的兜底默认 `AlwaysActive()` 走这条）。"""
        lc = AlwaysActive()
        assert isinstance(lc._cfg, LifecycleConfig)
        assert FiniteActive(max_triggers=2)._max_triggers == 2
        assert isinstance(DependentActive(LifecycleConfig(depends_on='s')), Lifecycle)
        assert isinstance(DependentFiniteActive(LifecycleConfig(depends_on='s'),
                                                max_triggers=1), FiniteActive)
