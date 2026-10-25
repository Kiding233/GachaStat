import pytest

from gacha_simulator.core.strategy import (
    FixedCountStrategy, TargetHuntingStrategy, StrategyContext,
    DrawSegmentStrategy, PriorityChainStrategy, NoDrawStrategy, Strategy,
    STRATEGY_REGISTRY, create_strategy, next_event_wait,
)
from gacha_simulator.core.action import DrawAction, WaitAction
from gacha_simulator.core.state import GachaState
from gacha_simulator.core.stop_condition import FixedActionCountCondition
from gacha_simulator.core.target_card import TargetCard, TargetCardSet
from gacha_simulator.core.banner import Banner


def _make_ctx(state, pools, total_draws=0, stop_condition=None):
    # P61（Ph1a）：策略消费 ctx.banners——裸 Pool 经单池包装为 Banner 传入
    banners = [Banner(id=p.id, name=p.name, pools={'main': p}) for p in pools]
    return StrategyContext(
        state=state,
        current_pools=pools,
        all_pools=pools,
        future_schedules=[],
        target_cards=TargetCardSet([]),
        stop_condition=stop_condition or FixedActionCountCondition(100),
        total_draws=total_draws,
        banners=banners,
        all_banners=banners,
    )


def test_fixed_count_strategy():
    state = GachaState(resources={'draw_resource': 1000})
    strategy = FixedCountStrategy(count=10)
    pools = []

    ctx = _make_ctx(state, pools, total_draws=0)
    action = strategy.select_action(ctx)
    assert isinstance(action, WaitAction)

    # P79 1e：枯竭态不得返回零等待（WaitAction(0) 会让 real_time 冻结，
    # 时间型停止条件永远够不着）。无可用 banner 时取 86400。
    ctx2 = _make_ctx(state, pools, total_draws=10)
    action2 = strategy.select_action(ctx2)
    assert isinstance(action2, WaitAction)
    assert action2.duration > 0


def test_target_hunting_strategy():
    state = GachaState(resources={'draw_resource': 160})
    strategy = TargetHuntingStrategy(target_pool_ids=['standard'])
    from gacha_simulator.core.pool import Pool, Reward
    pools = [Pool('standard', 'Standard', {'draw_resource': 160}, [(Reward('r1', 'R1'), 1.0)])]

    ctx = _make_ctx(state, pools)
    action = strategy.select_action(ctx)
    assert isinstance(action, DrawAction)
    # P61（Ph1a）：策略返回 DrawAction(banner_id=...)，pool_id 仅供反查
    assert action.banner_id == 'standard'


# ── P79 阶段 1：策略枯竭态契约与 next_event_wait ──────────────────────

_BUILTIN_KEYS = [
    'smart', 'pool_quota', 'pity_reserve', 'stop_on_target',
    'fixed_count', 'target_hunting', 'no_draw', 'draw_target',
]
# 插件策略由 load_plugin_strategies 注册并参与默认运行；其内部组合
# PityReserveStrategy + DrawSegmentStrategy 横跨策略层与 building block 层
_PLUGIN_KEY = 'plugin/example_phased'


def _state(real_time=0.0, resources=None):
    st = GachaState(resources=resources if resources is not None else {'draw_resource': 0})
    st.real_time = real_time
    return st


def _ctx(banners=(), real_time=0.0, total_draws=0, resources=None):
    return StrategyContext(
        state=_state(real_time=real_time, resources=resources),
        current_pools=[], all_pools=[], future_schedules=[],
        target_cards=TargetCardSet([]),
        stop_condition=FixedActionCountCondition(100),
        total_draws=total_draws,
        banners=list(banners), all_banners=list(banners),
    )


def _exhausted_ctx(total_draws=10 ** 6):
    """枯竭态：无可用 banner（抽不动）+ 抽数远超任何 count 阈值。"""
    return _ctx(total_draws=total_draws)


def _dummy_pool():
    from gacha_simulator.core.pool import Pool, Reward
    return Pool('main', 'Main', {'draw_resource': 160}, [(Reward('r1', 'R1'), 1.0)])


def test_next_event_wait_returns_float_and_respects_cap():
    """8.2 next_event_wait：契约是 min(86400, 最近关闭时刻 - real_time)。"""
    # 无可用 banner → 上限
    assert next_event_wait(_exhausted_ctx()) == 86400.0
    # available_until 为 None → 上限
    assert next_event_wait(_ctx([Banner(id='b', name='b', pools={'main': _dummy_pool()})])) == 86400.0
    # 最近关闭时刻早于一天 → 取该差值
    b1 = Banner(id='b1', name='b1', pools={'main': _dummy_pool()}, available_until=7200.0)
    b2 = Banner(id='b2', name='b2', pools={'main': _dummy_pool()}, available_until=3600.0)
    assert next_event_wait(_ctx([b1, b2])) == 3600.0
    # 最近关闭时刻晚于一天 → 上限（86400 是硬上限，不得返回更大的值）
    b3 = Banner(id='b3', name='b3', pools={'main': _dummy_pool()}, available_until=200000.0)
    assert next_event_wait(_ctx([b3])) == 86400.0
    # 已过期 → 上限
    b4 = Banner(id='b4', name='b4', pools={'main': _dummy_pool()}, available_until=-100.0)
    assert next_event_wait(_ctx([b4])) == 86400.0
    # 返回类型必须是 float（不是 Action）——调用点负责包 WaitAction
    assert isinstance(next_event_wait(_exhausted_ctx()), float)


@pytest.mark.parametrize('key', _BUILTIN_KEYS + [_PLUGIN_KEY])
def test_strategy_exhausted_returns_time_advancing_wait(key):
    """8.2 策略契约：9 组策略（8 内置 + 插件）在枯竭态均返回 duration > 0。"""
    if key == _PLUGIN_KEY:
        from gacha_simulator.core.strategy_loader import load_plugin_strategies
        load_plugin_strategies()
    assert key in STRATEGY_REGISTRY, f'{key} 未注册'
    action = create_strategy(key, {}).select_action(_exhausted_ctx())
    # 先过 isinstance 再断言 duration：只断言 duration 属性会让「直接返回 float」
    # 的写法在 AttributeError 与断言失败之间表现不一致（运行期实为 ValueError）
    assert isinstance(action, WaitAction), f'{key} 枯竭态返回了 {type(action).__name__}'
    assert action.duration > 0, f'{key} 枯竭态返回零等待，real_time 会冻结'


def test_draw_segment_strategy_exhausted_fallback():
    """building block 兜底：全有界 segments 且抽数超出最后一档。"""
    seg = DrawSegmentStrategy([(0, 10, NoDrawStrategy())])
    action = seg.select_action(_exhausted_ctx(total_draws=100))
    assert isinstance(action, WaitAction)
    assert action.duration > 0


def test_priority_chain_strategy_exhausted_fallback():
    """building block 兜底：全部子策略返回 None。"""

    class _NoneStrategy(Strategy):
        _strategy_key = None

        @classmethod
        def description(cls) -> str:
            return '始终返回 None'

        def select_action(self, ctx):
            return None

    chain = PriorityChainStrategy([_NoneStrategy(), _NoneStrategy()])
    action = chain.select_action(_exhausted_ctx())
    assert isinstance(action, WaitAction)
    assert action.duration > 0


# ══════════════════════════════════════════════════════════════════
# P64 S9-5：策略侧存量持有口径（`initial_count` 计入「是否已拥有」）
# ══════════════════════════════════════════════════════════════════
#
# 判据面：`strategies/builtin/` 的 4 个策略文件共 9 处「是否已拥有」判据
# （pity_reserve 2 / pool_quota 2 / smart 2 / stop_on_target 3）全部由
# `ctx.acquired.get(t.card_id, 0)` 迁到 `ctx.state.total_holding(t.card_id)`。
# `ctx.acquired` 的定义不变（P60 语义「本次模拟**新获得**」，不含初始持有），
# 迁移的是**消费侧**。本组验**层内 9 处无遗漏**（逐策略覆盖）；跨层一致
# （引擎侧与策略侧同口径）由 `tests/core/test_pity_integration.py` 的
# `TestG3ExcludeOwned::test_g3_engine_and_strategy_agree_on_owned_set` 承担。
#
# **变异实测（2026-10-14，8 次，逐处还原）**：① `state.total_holding` 漏算
# `initial_counts` → 本组 4 条 + 服务层 4 条 + G3 跨层条全红；② 逐处回退
# `pity_reserve` s1 / s2、`pool_quota` s1 / s2、`smart` s1 / s2、
# `stop_on_target` s2 → 各自只有对应策略的那一条红（逐策略可辨）。
#
# **未被任何变异覆盖的新断言（登记）**：(a) 各条的**对照组**（`initial_counts`
# 为空 → `DrawAction` + `banner_id`）：作用是夹具判别力守卫，与迁移方向正交；
# (b) 各条的夹具守卫 `ctx.state.acquired == {}`（P60 语义：初始持有不预填
# `acquired`）；(c) `stop_on_target` 条的 ①（s1 直调）与 ③（默认配置主循环）
# 只被 ① 号变异覆盖，未做「单处回退」隔离（`stop_on_target` 的 s1 / s3 未单独
# 变异，受 8 次上限约束；两者形态与已隔离的 `pity_reserve` / `pool_quota` 的
# s1 / s2 逐字相同）；(d) `test_g3_engine_and_strategy_agree_on_owned_set` 的
# ①（`initial_counts` 夹具守卫）、③（**口径同一性守卫**：`SimView.owns` 与
# `GachaState.total_holding` 是同一对象的同一函数，无独立判别力）与 ⑤
# （`acquired` 仍为空的反向守卫）；该用例的 ④ **有判别力**，其牙齿由 s1 承担
# （策略侧迁移**整体回退**或**单处回退 s1** 时 ④ 红），但**单处回退 s3 仍不可辨**
# （`pool.is_exchange=False` 使兑换分支整体落空，s3 不决定是否返回 `DrawAction`）。
# 该夹具原缺 `resources`（`can_afford_batch` 恒 False，④ 退化为恒真）已于本步就地
# 补上池消耗的 `gem`；遮蔽关系与三档实测（2026-10-14 审查收口）见该用例 docstring。

_S95_CARD = 's95_card'
_S95_BANNER = 's95_banner'


def _s95_ctx(*, initial_counts=None, quantity=2, exchange=True, extra_targets=()):
    """P64 S9-5 夹具：目标卡 `s95_card`（需求 `quantity`）+ 单 Banner 单池。

    `exchange=True` 时池为兑换池（100% `s95_card`，`exchange_card_id` 指向它），
    策略的「兑换优先」分支会命中它；`False` 时为 0.5 / 0.5 双卡随机池（非兑换），
    只有 `_pool_needs_target` 一侧会命中。`acquired` 恒为空，初始持有只写
    `initial_counts`（P60 语义：初始持有不预填 `acquired`）。

    `extra_targets` 追加同池的目标卡 `(card_id, quantity_needed)`，用于需要
    「一张已达标 + 一张未达标」的判据（`stop_on_target` 的 `stop_on_any_target`
    分支只有在该形态下才与「跳过已达标、继续为未达标目标抽卡」区分得开）。
    """
    from gacha_simulator.core.pool import Pool, Reward

    if exchange:
        pool = Pool(id='main', name='S95', cost={'draw_resource': 160},
                    rewards=[(Reward(_S95_CARD, 'S95'), 1.0)],
                    exchange_card_id=_S95_CARD)
    else:
        pool = Pool(id='main', name='S95', cost={'draw_resource': 160},
                    rewards=[(Reward(_S95_CARD, 'S95'), 0.5),
                             (Reward('s95_other', 'Other'), 0.5)])
    banner = Banner(id=_S95_BANNER, name='S95', pools={'main': pool})
    state = GachaState(resources={'draw_resource': 100000},
                       initial_counts=dict(initial_counts or {}))
    targets = [TargetCard(card_id=_S95_CARD, pool_ids=[_S95_BANNER],
                          quantity_needed=quantity)]
    targets += [TargetCard(card_id=cid, pool_ids=[_S95_BANNER], quantity_needed=n)
                for cid, n in extra_targets]
    return StrategyContext(
        state=state,
        current_pools=[pool], all_pools=[pool], future_schedules=[],
        target_cards=TargetCardSet(targets),
        stop_condition=FixedActionCountCondition(100),
        banners=[banner], all_banners=[banner],
    )


def test_pity_reserve_holding_includes_initial_count():
    """P64 S9-5：`pity_reserve` 的 2 处判据均取含初始持有的口径。

    ① `select_action` 首段的 `>= quantity_needed`：初始持有 2 = 需求 2 时，兑换池
    虽可抽也**不抽**（`WaitAction`）；② `_pool_needs_target` 的 `< quantity_needed`
    同口径判「不需要」。对照组（无初始持有）两处都判「需要」。
    """
    ctx = _s95_ctx(initial_counts={_S95_CARD: 2})
    assert ctx.state.acquired == {}, '夹具：初始持有不得预填 acquired（P60 语义）'
    assert ctx.state.total_holding(_S95_CARD) == 2

    assert isinstance(create_strategy('pity_reserve', {}).select_action(ctx), WaitAction), \
        '初始持有已达标，不应再抽兑换池'

    action0 = create_strategy('pity_reserve', {}).select_action(_s95_ctx())
    assert isinstance(action0, DrawAction), '对照：无初始持有时应抽卡'
    assert action0.banner_id == _S95_BANNER

    assert create_strategy('pity_reserve', {})._pool_needs_target(
        _S95_BANNER, _s95_ctx(initial_counts={_S95_CARD: 2}, exchange=False)) is False
    assert create_strategy('pity_reserve', {})._pool_needs_target(
        _S95_BANNER, _s95_ctx(exchange=False)) is True


def test_pool_quota_holding_includes_initial_count():
    """P64 S9-5：`pool_quota` 的 2 处判据均取含初始持有的口径。

    ① `select_action` 首段的 `>= quantity_needed`（兑换池路径）；
    ② `_pool_needs_target` 的 `< quantity_needed`。

    **覆盖边界（如实声明，2026-10-14 审查收口实测订正）**：**单 banner 下行为
    中性**：第三段「配额未尽则任意抽」在非兑换池上不读 `_pool_needs_target`，判
    True 走第二段抽、判 False 走第三段也抽，同一 banner 下不可区分。**多 banner
    下可观测**：第二段的「目标偏好」被第三段兜底取代，**抽卡目标 banner 改变**
    （实测：两个非兑换 banner，`B1` 的池不含目标 / `B2` 的池含目标，
    `quantity_needed=1`、`initial_counts={X:1}`：迁移后 `select_action` →
    `DrawAction(banner_id='B1')`；把 s1 谓词换回 `ctx.acquired.get` → `B2`）。此处
    以**直调 `_pool_needs_target`** 覆盖 ② 的口径，`select_action` 只覆盖 ①。
    """
    ctx = _s95_ctx(initial_counts={_S95_CARD: 2})
    assert ctx.state.acquired == {}

    assert isinstance(create_strategy('pool_quota', {}).select_action(ctx), WaitAction), \
        '初始持有已达标，不应再抽兑换池'

    action0 = create_strategy('pool_quota', {}).select_action(_s95_ctx())
    assert isinstance(action0, DrawAction), '对照：无初始持有时应抽卡'
    assert action0.banner_id == _S95_BANNER

    assert create_strategy('pool_quota', {})._pool_needs_target(
        _S95_BANNER, _s95_ctx(initial_counts={_S95_CARD: 2}, exchange=False)) is False
    assert create_strategy('pool_quota', {})._pool_needs_target(
        _S95_BANNER, _s95_ctx(exchange=False)) is True


def test_smart_holding_includes_initial_count():
    """P64 S9-5：`smart` 的 2 处判据均取含初始持有的口径。

    ① `_get_needed_card_exchange` 的 `>= quantity_needed`（兑换优先分支）；
    ② `_pool_needs_target` 的 `< quantity_needed`（中间赋值形态 `ac_val`）。

    **覆盖边界（如实声明）**：`select_action` 的兑换分支与 `_pool_needs_target`
    两条路径在本夹具下判据取值相同（同一张卡、同一需求），单跑 `select_action`
    无法分辨是哪一处生效；故 ① 由 `select_action`（兑换池夹具）覆盖、② 由直调
    `_pool_needs_target`（随机池夹具）覆盖，逐处可辨。
    """
    ctx = _s95_ctx(initial_counts={_S95_CARD: 2})
    assert ctx.state.acquired == {}

    assert isinstance(create_strategy('smart', {}).select_action(ctx), WaitAction), \
        '初始持有已达标，不应再抽兑换池'

    action0 = create_strategy('smart', {}).select_action(_s95_ctx())
    assert isinstance(action0, DrawAction), '对照：无初始持有时应抽卡'
    assert action0.banner_id == _S95_BANNER

    assert create_strategy('smart', {})._pool_needs_target(
        _S95_BANNER, _s95_ctx(initial_counts={_S95_CARD: 2}, exchange=False)) is False
    assert create_strategy('smart', {})._pool_needs_target(
        _S95_BANNER, _s95_ctx(exchange=False)) is True


def test_stop_on_target_holding_includes_initial_count():
    """P64 S9-5：`stop_on_target` 的 3 处判据均取含初始持有的口径。

    ① `_pool_needs_target` 的 `< quantity_needed`（直调覆盖）；
    ② `stop_on_any_target` 分支的 `>= quantity_needed`：**任一**目标达标即整场停手。
    该分支的语义是「任意目标」而非「所有目标」，故夹具须另有一张**未达标**的目标卡
    （`s95_other`），否则「整场停手」与「跳过已达标目标、继续为未达标目标抽卡」
    的产出相同、变异不可辨（实测：单目标夹具下把 ② 回退仍返回 `WaitAction`）；
    ③ `select_action` 主循环的 `>= quantity_needed`。
    """
    # ③ 主循环（默认配置：stop_on_featured=True / stop_on_any_target=False）
    ctx = _s95_ctx(initial_counts={_S95_CARD: 2})
    assert ctx.state.acquired == {}
    assert isinstance(create_strategy('stop_on_target', {}).select_action(ctx), WaitAction), \
        '初始持有已达标，不应再抽兑换池'

    action0 = create_strategy('stop_on_target', {}).select_action(_s95_ctx())
    assert isinstance(action0, DrawAction), '对照：无初始持有时应抽卡'
    assert action0.banner_id == _S95_BANNER

    # ② `stop_on_any_target` 分支：card_A 由初始持有达标 → 整场停手（card_B 仍缺也不抽）
    any_cfg = {'stop_on_any_target': True}
    pair_kw = dict(exchange=False, extra_targets=[('s95_other', 1)])
    assert isinstance(
        create_strategy('stop_on_target', any_cfg).select_action(
            _s95_ctx(initial_counts={_S95_CARD: 2}, **pair_kw)), WaitAction), \
        'stop_on_any_target：初始持有已达标的任一目标即令整场停手'
    # 对照甲：关掉该分支 → 继续为未达标的 card_B 抽卡（证明上一条确为 ② 之功）
    assert isinstance(
        create_strategy('stop_on_target', {}).select_action(
            _s95_ctx(initial_counts={_S95_CARD: 2}, **pair_kw)), DrawAction), \
        '对照：stop_on_any_target=False 时应继续为未达标的 card_B 抽卡'
    # 对照乙：无初始持有时 ② 不触发
    assert isinstance(
        create_strategy('stop_on_target', any_cfg).select_action(
            _s95_ctx(**pair_kw)), DrawAction), \
        '对照：无初始持有时不停手'

    # ① `_pool_needs_target`
    assert create_strategy('stop_on_target', {})._pool_needs_target(
        _S95_BANNER, _s95_ctx(initial_counts={_S95_CARD: 2}, exchange=False)) is False
    assert create_strategy('stop_on_target', {})._pool_needs_target(
        _S95_BANNER, _s95_ctx(exchange=False)) is True
