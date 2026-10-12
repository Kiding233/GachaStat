"""GachaService 初始持有数量测试

规则：card_counts / acquired_counts 只记录新抽到的卡（从0开始），
不预填入 initial_count。initial_count 单独保留，用于 bonus 计算时
确定总持有量（= initial_count + newly_acquired）。
"""
import copy
import os
import tempfile

import pytest

from gacha_simulator.core import (
    Pool, Reward, GachaState, TargetCard, TargetCardSet,
    SmartStrategy, AllPoolsEndCondition,
)
from gacha_simulator.core.action import NonDrawAction, WaitAction
from gacha_simulator.core.config_toml import load_toml, ConfigError
from gacha_simulator.core.pity import PityState
from gacha_simulator.core.strategy import Strategy
from gacha_simulator.service.batch_simulator import (
    SimulationEnvBuilder, run_batch_parallel,
)
from gacha_simulator.service.gacha_service import (
    GachaService, SimulationStats, _progress_signature,
)


def _make_pool(pool_id="test_pool"):
    # P61（Ph1a）：Pool 已删除 available_from/available_until——时间窗口移至 Banner。
    # 裸 Pool 经构造桥包装为 Banner 后无窗口（永不关闭），停止由 AllPoolsEndCondition 决定。
    # P61（Ph1a/ISSUE-319）：100% 单卡池被推导属性判定为兑换池（random=False），
    # exchange_card_id 对齐目标卡，SmartStrategy 走兑换分支完成抽卡。
    return Pool(
        id=pool_id,
        name="Test Pool",
        cost=[{"draw_resource": 160}],
        rewards=[(Reward(id="card_A", name="Card A"), 1.0)],
        exchange_card_id="card_A",
    )


def test_initial_count_not_prepopulated():
    """initial_count > 0 不预填入 card_counts——只记录新抽到的"""
    pool = _make_pool()
    strategy = SmartStrategy()
    stop_cond = AllPoolsEndCondition(1000.0)
    target = TargetCardSet([TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=2)])

    service = GachaService(
        [pool], strategy, stop_cond, target,
        card_defs=[{"card_id": "card_A", "initial_count": 1}],
    )
    state = GachaState(resources={"draw_resource": 100000})
    result = service.run_simulation_compact(state, max_iterations=200)

    # 概率 100%，每抽必出 card_A → quantity_needed=2，抽2次后满足
    # card_counts 只记新抽到的，应为 2（不含 initial_count）
    assert result.card_counts.get("card_A", 0) == 2


def test_initial_count_zero_no_effect():
    """initial_count=0 时不影响任何行为"""
    pool = _make_pool()
    strategy = SmartStrategy()
    stop_cond = AllPoolsEndCondition(1000.0)
    target = TargetCardSet([TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=1)])

    service = GachaService(
        [pool], strategy, stop_cond, target,
        card_defs=[{"card_id": "card_A", "initial_count": 0}],
    )
    state = GachaState(resources={"draw_resource": 100000})
    result = service.run_simulation_compact(state, max_iterations=200)

    assert result.card_counts.get("card_A", 0) == 1


def test_initial_count_multiple_cards():
    """多张卡有不同 initial_count——card_counts 只记新抽到"""
    pool = Pool(
        id="multi_pool",
        name="Multi",
        cost=[{"draw_resource": 160}],
        rewards=[(Reward(id="card_A", name="A"), 0.5), (Reward(id="card_B", name="B"), 0.5)],
    )
    strategy = SmartStrategy()
    stop_cond = AllPoolsEndCondition(1000.0)
    target = TargetCardSet([
        TargetCard(card_id="card_A", pool_ids=["multi_pool"], quantity_needed=2),
        TargetCard(card_id="card_B", pool_ids=["multi_pool"], quantity_needed=1),
    ])

    service = GachaService(
        [pool], strategy, stop_cond, target,
        card_defs=[
            {"card_id": "card_A", "initial_count": 3},
            {"card_id": "card_B", "initial_count": 0},
        ],
    )
    state = GachaState(resources={"draw_resource": 100000})
    result = service.run_simulation_compact(state, max_iterations=300)

    # card_A: initial=3, quantity=2 — 还需抽2张，card_counts只记新抽到
    assert result.card_counts.get("card_A", 0) >= 2
    # card_B: 无初始持有
    assert result.card_counts.get("card_B", 0) >= 1


def test_initial_count_does_not_satisfy_target():
    """初始持有再高也不满足需求——必须从gacha中新抽到"""
    pool = _make_pool()
    strategy = SmartStrategy()
    stop_cond = AllPoolsEndCondition(1000.0)
    target = TargetCardSet([TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=1)])

    service = GachaService(
        [pool], strategy, stop_cond, target,
        card_defs=[{"card_id": "card_A", "initial_count": 5}],
    )
    state = GachaState(resources={"draw_resource": 100000})
    result = service.run_simulation_compact(state, max_iterations=200)

    # 100%出A，抽1次满足 quantity_needed=1
    # card_counts 只记新抽到，不含初始持有
    assert result.card_counts.get("card_A", 0) == 1
    assert result.total_draws == 1


def test_card_defs_none_handled():
    """不传 card_defs 时应正常运行"""
    pool = _make_pool()
    strategy = SmartStrategy()
    stop_cond = AllPoolsEndCondition(1000.0)
    target = TargetCardSet([TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=1)])

    service = GachaService([pool], strategy, stop_cond, target)
    state = GachaState(resources={"draw_resource": 100000})
    result = service.run_simulation_compact(state, max_iterations=200)

    assert result.card_counts.get("card_A", 0) >= 1


def test_env_builder_from_config_store_smoke():
    """SimulationEnvBuilder.from_config_store() 冒烟测试——模拟 GUI→引擎 实际路径"""
    from gacha_simulator.core.config_store import (
        ConfigStore, CardDefEntry, BannerEntry, BannerPoolEntry, DAY,
        PityConfig, GainRule, TargetCardEntry,
    )
    from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

    store = ConfigStore()
    # P61（§3.9）：写入侧为 store.banner.banners
    store.banner.banners = [
        BannerEntry(
            enabled=True,
            id='pool_draw',
            name='测试抽卡池',
            available_from=0 * DAY,
            available_until=21 * DAY,
            pools=[BannerPoolEntry(
                id='main',
                cost='draw_resource:160',
                rewards=[
                    {'card_id': 'card_A', 'probability': 50.0, 'rarity': 'SSR', 'featured': True},
                    {'card_id': '_no_card', 'probability': 50.0, 'rarity': 'R'},
                ],
            )],
        ),
    ]
    store.card_defs = [
        CardDefEntry(card_id='card_A', name='角色A', rarity='SSR', pools=['pool_draw']),
    ]
    store.target_cards = [TargetCardEntry(card_id='card_A', quantity=2)]
    store.initial_resources = {'draw_resource': 100000}
    store.gain_rules = [GainRule(rule_type='every_n_days', param='1', gains={'draw_resource': 150})]
    store.pity = PityConfig(enabled=False)

    env = SimulationEnvBuilder.from_config_store(store)
    assert env is not None
    assert len(env.pools) == 1
    # P61（Ph6）：from_config_store 改读 store.banner，env.pools 承载 List[Banner]
    assert env.pools[0].id == 'pool_draw'
    assert env.pools[0].name == '测试抽卡池'
    # Pool.pool_type 已删除——推导属性 is_exchange（output='card' and not random）
    assert env.pools[0].active_pool.is_exchange is False
    # P61（Ph6 / ISSUE-001）：Banner 级时间窗口透传（TOML 解析边界已 *DAY 为秒）
    assert env.pools[0].available_from == 0 * DAY
    assert env.pools[0].available_until == 21 * DAY
    # P61（Ph6 / ISSUE-011）：banner_defs 与 pools 同源（_run_single 深拷贝隔离用）
    assert env.banner_defs is not None and len(env.banner_defs) == 1
    assert env.end_time == 21 * DAY


# ══════════════════════════════════════════════════════════════════
# P79（阶段 3）：零进度兜底
#
# 回传断言的并行度纪律：直接断言 result.warnings / result.iterations 的用例
# 统一以 max_workers=1 运行（走进程内路径，规避子进程回传不确定性）；
# return_compact=False 且 max_workers>1 的生产形态另立一条回归（3e）。
# ══════════════════════════════════════════════════════════════════

_MAIN_CONFIG = 'gacha_simulator/config/config.toml'

# 带 targeted 保底的池——供 NonDrawAction 改写保底状态（防误杀用例）
_TARGETED_TOML = """[meta]
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

[[pity]]
name = "epi"
type = "targeted"
scope = "ssr"
fate_threshold = 1
switch_allowed = true
switch_resets_progress = true
"""


class _ZeroWaitStrategy(Strategy):
    """类型 1 复现：恒返回零等待，real_time 永久冻结。"""

    @classmethod
    def description(cls) -> str:
        return '始终零等待（类型 1 复现）'

    def select_action(self, ctx):
        return WaitAction(duration=0)


class _NonDrawSpinStrategy(Strategy):
    """防误杀：前 N 轮只发 NonDrawAction——不抽卡、不推进时间，但改写保底状态。

    在 c1 / c2 之间交替切换定轨目标，使「保底状态」这一维度逐轮变化。
    """

    def __init__(self, rounds: int = 4):
        self.rounds = rounds
        self.n = 0

    @classmethod
    def description(cls) -> str:
        return '前 N 轮交替切换定轨目标（合法多轮 NonDrawAction）'

    def select_action(self, ctx):
        if self.n < self.rounds:
            self.n += 1
            card = 'c1' if self.n % 2 else 'c2'
            # Banner 型 service 须用全限定键 {banner}.{pool}——_pool_id_to_banner
            # 只在裸 Pool 输入路径下填充，裸 id 会抛「引用了不存在的池子」
            return NonDrawAction(action_id='switch_epitomized_target',
                                 params={'pool_id': 'test_pool.main', 'card_id': card})
        return WaitAction(duration=86400)


class _EpiActionStrategy(Strategy):
    """按脚本顺序返回 NonDrawAction，脚本用尽后推进时间（86400 秒）。

    定轨端到端用例的驱动装置：动作列表由用例给出，策略本身不含分支逻辑。
    """

    def __init__(self, actions):
        self._actions = list(actions)
        self.n = 0

    @classmethod
    def description(cls) -> str:
        return '按脚本顺序发 NonDrawAction（定轨端到端用例）'

    def select_action(self, ctx):
        if self.n < len(self._actions):
            action = self._actions[self.n]
            self.n += 1
            return action
        return WaitAction(duration=86400)


def _run_with(strategy, stop_cond, max_iterations=1000):
    """以自建 service 跑一次（自建池为 100% 单卡池，不依赖外部配置）。"""
    pool = _make_pool()
    target = TargetCardSet(
        [TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=1)])
    svc = GachaService([pool], strategy, stop_cond, target,
                       card_defs=[{"card_id": "card_A", "initial_count": 0}])
    state = GachaState(resources={"draw_resource": 100000})
    return svc.run_simulation_compact(state, max_iterations=max_iterations)


def _write_targeted_config():
    fd, path = tempfile.mkstemp(suffix='.toml')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(_TARGETED_TOML)
    return path


#: `targeted` 的软保底变体。`_apply_non_draw` 的判据必须**同时**认这两型
#: （旧判据 `isinstance(bh, TargetedBehavior)` 天然覆盖子类 `TargetedSoftBehavior`，
#: 改为按 `btype` 元组判定后，漏写 `'targeted_soft'` 不会被任何用例判红）。
_TARGETED_SOFT_TOML = _TARGETED_TOML.replace(
    'type = "targeted"', 'type = "targeted_soft"').replace(
    'switch_resets_progress = true',
    'switch_resets_progress = true' + chr(10) + 'start = 74' + chr(10) + 'end = 90')  # TOML 键空间用 start/end（软保底语法糖），非字段名 soft_start/soft_end


def _write_targeted_soft_config():
    fd, path = tempfile.mkstemp(suffix='.toml')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(_TARGETED_SOFT_TOML)
    return path


#: 同池三条保底的配置：两条 `targeted`（跨 scope）＋一条 `hard` 作非定轨命名空间的诱饵。
#: `epi_sr` 的 priority 故意高于 `epi_ssr`，用于钉住「同池多条 targeted 时写入落谁」。
#: 同 scope 两条 targeted 不可构造（`_validate_behaviors` 规则 3 抛 ConfigError），
#: 故跨 scope 是本形态的唯一可构造形态，详见 test_multi_targeted_pool_order_*。
_TARGETED_MULTI_TOML = """[meta]
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

[[pity]]
name = "epi_ssr"
type = "targeted"
scope = "ssr"
fate_threshold = 1
priority = 0

[[pity]]
name = "epi_sr"
type = "targeted"
scope = "sr"
fate_threshold = 1
priority = 10

[[pity]]
name = "hard90"
type = "hard"
scope = "ssr"
threshold = 90
"""


def _write_targeted_multi_config():
    fd, path = tempfile.mkstemp(suffix='.toml')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(_TARGETED_MULTI_TOML)
    return path


def test_zero_progress_dead_loop_is_caught():
    """四例之一：真死循环（恒返回 WaitAction(0)）被兜住并打 warning。"""
    r = _run_with(_ZeroWaitStrategy(), AllPoolsEndCondition(1000.0))
    assert r.warnings, '零等待死循环未被兜住'
    assert '零进度兜底' in r.warnings[0]
    # 连续 3 轮签名相同即 break（首轮只记录），故远小于迭代预算
    assert 3 <= r.iterations <= 6
    assert r.total_draws == 0


def test_zero_progress_affordability_spin_is_caught():
    """四例之二：affordability 空转（fixed_count count=50000 资源耗尽后抽不动）。

    该空转轮返回的正是 DrawAction（动作已产出后才被 affordability 拦下），
    是「判据不得取动作类型」的直接验证；空转走 continue 跳过循环体尾部，
    是「检测必须落循环体顶部」的直接验证。
    """
    store = load_toml(_MAIN_CONFIG)
    env = SimulationEnvBuilder.from_config_store(store)
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    env.strategy_key = 'fixed_count'
    env.strategy_params = {'count': 50000}

    r = run_batch_parallel(
        env=env, target_specs=specs, initial_resources=env.initial_resources,
        num_simulations=1, max_workers=1, seed=42).results[0]

    assert r.warnings and '零进度兜底' in r.warnings[0]
    assert r.iterations < 1000          # 现状为 100000
    assert r.total_draws > 0            # 空转前确实抽过卡


def test_zero_progress_does_not_kill_legit_non_draw_rounds():
    """四例之三：防误杀——合法多轮 NonDrawAction（改写保底状态）不被终止。"""
    r = _run_legit_non_draw_rounds(_write_targeted_config())
    assert r.warnings == [], f'合法 NonDrawAction 被误杀: {r.warnings}'
    assert r.iterations > 4, '未越过 NonDrawAction 阶段即结束'
    assert r.total_draws == 0


def test_non_draw_action_recognizes_targeted_soft():
    """`targeted_soft` 与 `targeted` 同为定轨族，`_apply_non_draw` 必须一并识别。

    S4-3 审查 minor 的守卫：判据由旧类判型改为 `btype` 元组后，把元组写成
    `('targeted',)`（漏 `'targeted_soft'`）时全量套件仍绿。本用例钉住该元组的完整性。
    """
    r = _run_legit_non_draw_rounds(_write_targeted_soft_config())
    assert r.warnings == [], (
        f'`targeted_soft` 未被 `_apply_non_draw` 识别（误杀）: {r.warnings}')
    assert r.iterations > 4
    assert r.total_draws == 0


def _run_legit_non_draw_rounds(path):
    """跑一场「多轮合法 NonDrawAction」的模拟，返回结果（两条用例共用同一装置）。"""
    batch, _probe = _run_non_draw_batch(path, lambda: _NonDrawSpinStrategy(rounds=4))
    return batch.results[0]


def _run_non_draw_batch(path, make_strategy):
    """共用装置核心：以自建策略跑一场模拟，返回 `(batch, probe)`。

    probe 记录每次 `_apply_non_draw` 被调用**前**的 `pity_state` 快照
    （`probe['snapshots']`，元素为 `(action_id, to_dict())`）与模拟**实际使用**的那个
    `PityState` 活对象（`probe['pity_state']`）。断言写入落点必须读后者：
    `run_simulation` 内部对 `self.pity_state` 做 clone，服务实例上那份不承载本次运行
    的改写，拿它断言会恒绿。

    策略替换仍走 `create_strategy` 打桩（`max_workers=1` 走进程内路径，打桩生效）；
    对 `_apply_non_draw` 的包装是只读探针，转发给原函数。
    """
    try:
        store = load_toml(path)
        env = SimulationEnvBuilder.from_config_store(store)
        env.strategy_key = 'no_draw'
        env.strategy_params = {}

        strategy = make_strategy()
        probe = {'snapshots': [], 'pity_state': None}
        import gacha_simulator.service.batch_simulator as _bs
        orig_create = _bs.create_strategy
        orig_apply = GachaService._apply_non_draw

        def _spy(self, action, banners, pity_engine, pity_state):
            probe['snapshots'].append((action.action_id, pity_state.to_dict()))
            probe['pity_state'] = pity_state
            return orig_apply(self, action, banners, pity_engine, pity_state)

        _bs.create_strategy = lambda key, params=None: strategy
        GachaService._apply_non_draw = _spy
        try:
            batch = run_batch_parallel(
                env=env, target_specs={}, initial_resources=env.initial_resources,
                num_simulations=1, max_workers=1, seed=42)
            return batch, probe
        finally:
            _bs.create_strategy = orig_create
            GachaService._apply_non_draw = orig_apply
    finally:
        os.unlink(path)


def test_switch_epitomized_target_writes_selected_card():
    """端到端：策略返回 `switch_epitomized_target`，写入须落在定轨保底的命名空间。

    AUDIT-BREAK-4 的捕获面：`_apply_non_draw` 曾有一行**函数局部**
    `from ..core.pity import TargetedBehavior`（当前已删除）。函数局部 import 只在
    被调用时执行，导入期与 ruff 检查期均不报错，故断言必须发生在 `_apply_non_draw`
    **被调用**之后。本用例经主循环捕获（`len(batch.results) == 1`：任何在
    `_apply_non_draw` 内抛出的异常都被 `batch_simulator` 的进程内路径吞成
    「1/1 次模拟失败」告警且结果列表为空，不会向外抛），同文件的直调用例
    `test_apply_non_draw_direct_recognizes_both_targeted_types` 在调用点直接捕获，
    两者是同一条判据的两个面。

    实测（2026-10-13）：旧类 `TargetedBehavior` 在发布前仍定义于 `core/pity.py`
    （GATE-5），故今天恢复该局部 import 并不抛 `ImportError`；此时判红的是与它同源的
    第②处判据，`isinstance(bh, TargetedBehavior)` 对 preset 化的 `Pity` 实例恒为
    False，`_apply_non_draw` 转而抛 `InvalidActionError`（池子明明配了定轨保底却报
    「未配置 targeted 保底」）。两处改动的捕获面是本用例的同一条断言。

    写入落点断言（静默语义错误面）：定轨保底 `epi_ssr` 的命名空间被写入目标卡；
    同池另一条 targeted（`epi_sr`，priority 更高）与非定轨保底（`hard90`）的命名空间
    都不带该写入。
    """
    batch, probe = _run_non_draw_batch(
        _write_targeted_multi_config(),
        lambda: _EpiActionStrategy([
            NonDrawAction(action_id='switch_epitomized_target',
                          params={'pool_id': 'test_pool.main', 'card_id': 'c1'}),
        ]))
    assert len(batch.results) == 1, f'模拟未产出结果（_apply_non_draw 内抛错被吞成告警）: {batch.warnings}'
    r = batch.results[0]
    assert r.warnings == [], f'模拟告警非空: {r.warnings}'
    assert r.total_draws == 0

    snapshots = probe['snapshots']
    assert [a for a, _ in snapshots] == ['switch_epitomized_target']
    # 切换前该键为初始值 None（由 _build_pity_state_init 写入），故下方断言不是初始值假绿
    assert snapshots[0][1]['data']['epi_ssr']['selected_card'] is None

    ps = probe['pity_state']
    assert ps is not None, '_apply_non_draw 未被调用'
    assert ps.get('epi_ssr', 'selected_card') == 'c1'
    # 切换重置命定进度（switch_resets_progress 默认 true）。断言读**键存在性**而非
    # `get(..., 'fate_points') == 0`：后者在「该键根本没被写入」时同样取到默认 0，
    # 对「跳过重置写入」的回归恒绿。
    assert ps.data['epi_ssr']['fate_points'] == 0, ps.data['epi_ssr']
    # 落点命名空间：诱饵命名空间不容纳该写入
    assert 'selected_card' not in ps.data.get('hard90', {}), ps.data.get('hard90')
    assert ps.data.get('epi_sr', {}).get('selected_card', 'MISSING') is None, ps.data.get('epi_sr')


def test_cancel_epitomized_path_clears_selected_card():
    """端到端：策略返回 `cancel_epitomized_path`，定轨目标须被清空。

    先切换后取消，使「清空」有可清之物：`probe['snapshots'][1]` 是取消**前**的快照，
    断言其中 `selected_card` 已是 'c1'，否则「最终为 None」可能来自「取消本身没写入」
    的假绿。同样断言落点命名空间（诱饵命名空间既不被写、也不被清）。
    """
    batch, probe = _run_non_draw_batch(
        _write_targeted_multi_config(),
        lambda: _EpiActionStrategy([
            NonDrawAction(action_id='switch_epitomized_target',
                          params={'pool_id': 'test_pool.main', 'card_id': 'c1'}),
            NonDrawAction(action_id='cancel_epitomized_path',
                          params={'pool_id': 'test_pool.main'}),
        ]))
    assert len(batch.results) == 1, f'模拟未产出结果（_apply_non_draw 内抛错被吞成告警）: {batch.warnings}'
    r = batch.results[0]
    assert r.warnings == [], f'模拟告警非空: {r.warnings}'
    assert r.total_draws == 0

    assert [a for a, _ in probe['snapshots']] == [
        'switch_epitomized_target', 'cancel_epitomized_path']
    before_cancel = probe['snapshots'][1][1]['data']['epi_ssr']
    assert before_cancel['selected_card'] == 'c1', before_cancel

    ps = probe['pity_state']
    assert ps.get('epi_ssr', 'selected_card') is None
    assert ps.get('epi_ssr', 'lost_rotating') is False
    assert ps.get('epi_ssr', 'losses') == 0
    assert 'selected_card' not in ps.data.get('hard90', {}), ps.data.get('hard90')
    assert ps.data.get('epi_sr', {}).get('selected_card', 'MISSING') is None, ps.data.get('epi_sr')


def test_apply_non_draw_direct_recognizes_both_targeted_types():
    """定轨流程专项：直调 `_apply_non_draw`（不经模拟循环），两型定轨保底都须被识别。

    与端到端用例的分工：端到端走主循环，`_apply_non_draw` 内的异常被
    `batch_simulator` 的进程内路径吞成「N/N 次模拟失败」告警，只剩「结果列表为空」
    一个信号；本用例直调，异常直接冒泡，判红信息落在识别点本身，且不经 P79 零进度
    兜底机制。覆盖 `targeted` 与 `targeted_soft` 两型（判据元组漏 `'targeted_soft'`
    即红）与「写入落在该保底自己的命名空间」。

    经 `self` 的读取点只有裸 pool_id 反查（`_pool_id_to_banner`），本例用全限定键
    `test_pool.main`，故服务实例只作容器用，不参与断言。
    """
    for path, name in ((_write_targeted_config(), 'epi'),
                       (_write_targeted_soft_config(), 'epi')):
        try:
            store = load_toml(path)
            env = SimulationEnvBuilder.from_config_store(store)
            banners = {b.id: b for b in env.pools}
            svc = GachaService(
                copy.deepcopy(env.pools), _ZeroWaitStrategy(), AllPoolsEndCondition(1.0),
                TargetCardSet([TargetCard(card_id='c1', pool_ids=['test_pool'],
                                          quantity_needed=1)]),
                pity_engine=env.pity_engine)
            pity_state = PityState.from_dict(env.pity_state_init)
            svc._apply_non_draw(
                NonDrawAction(action_id='switch_epitomized_target',
                              params={'pool_id': 'test_pool.main', 'card_id': 'c1'}),
                banners, env.pity_engine, pity_state)
            assert pity_state.get(name, 'selected_card') == 'c1'
            assert pity_state.data[name]['fate_points'] == 0, pity_state.data[name]
        finally:
            os.unlink(path)


def test_multi_targeted_pool_order_puts_rarity_before_priority():
    """同池多条 targeted 时取哪一条：现行为取 `_pool_order` 中最靠前的那条。

    `_apply_non_draw` 取池内**第一条** targeted 保底，池内序取自 `_resolve_order` 的
    排序键 `(稀有度 rank, -priority, type order, name)`。本用例用 priority=10 的
    `epi_sr` 对上 priority=0 的 `epi_ssr`：跨 scope 时 rank 先比较（ssr 的 rank 0
    先于 sr 的 rank 1），故写入落 `epi_ssr`，priority 不参与该裁决。

    同 scope 两条 targeted **不可构造**（`_validate_behaviors` 规则 3：同 scope 两个
    事件驱动型抛 ConfigError），故「两条 targeted 且 priority 不同」只有本用例这一种
    可构造形态。结论：priority 对 `_apply_non_draw` 的选靶恒无影响。
    """
    path = _write_targeted_multi_config()
    try:
        store = load_toml(path)
        engine = SimulationEnvBuilder.from_config_store(store).pity_engine
        order = [n for n, _ in engine.get_behaviors_for_pool('test_pool.main')]
        assert order == ['hard90', 'epi_ssr', 'epi_sr'], order
        assert engine.get_pity_def('epi_sr').priority == 10
        assert engine.get_pity_def('epi_ssr').priority == 0
    finally:
        os.unlink(path)

    # 同一形态改成同 scope：构造期即被规则 3 拒收（priority 无从裁决两条 targeted）
    same_scope = _TARGETED_MULTI_TOML.replace('scope = "sr"', 'scope = "ssr"')
    assert same_scope != _TARGETED_MULTI_TOML
    fd, path2 = tempfile.mkstemp(suffix='.toml')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(same_scope)
    try:
        with pytest.raises(ConfigError) as ei:
            SimulationEnvBuilder.from_config_store(load_toml(path2))
        assert '事件驱动型' in str(ei.value), str(ei.value)
    finally:
        os.unlink(path2)


def test_progress_signature_covers_all_dimensions():
    """四例之四：进度信号完备性——逐项构造单一维度变化，签名均须随之变化。"""
    store = load_toml(_MAIN_CONFIG)
    env = SimulationEnvBuilder.from_config_store(store)
    banners = {b.id: b for b in env.pools}
    pity = PityState()

    def sig(state=None, stats=None, bs=None, real_time=0.0, ps=None):
        return _progress_signature(
            state if state is not None
            else GachaState(resources={'draw_resource': 100}, acquired={'c1': 1}),
            stats if stats is not None else SimulationStats(),
            bs if bs is not None else banners,
            real_time,
            ps if ps is not None else pity)

    base = sig()
    # 同态深拷贝必须产出同一签名（否则检测会持续误判为「有进度」）
    assert sig(bs=copy.deepcopy(banners)) == base

    variants = {}
    variants['资源余额'] = sig(
        state=GachaState(resources={'draw_resource': 101}, acquired={'c1': 1}))
    variants['持卡数量'] = sig(
        state=GachaState(resources={'draw_resource': 100}, acquired={'c1': 2}))
    variants['时间'] = sig(real_time=1.0)

    ss_draws = SimulationStats()
    ss_draws.total_draws = 1
    variants['抽数'] = sig(stats=ss_draws)
    ss_pool = SimulationStats()
    ss_pool.pool_draw_counts = {'pool_c1.main': 1}
    variants['池抽数'] = sig(stats=ss_pool)
    ss_pity = SimulationStats()
    ss_pity.last_draw_pity_triggered = True
    variants['上次抽卡触发保底'] = sig(stats=ss_pity)

    ps2 = PityState()
    ps2.set('p1', 'counter', 5)
    variants['保底状态'] = sig(ps=ps2)

    deep = copy.deepcopy(banners)
    deep[next(iter(banners))]._exhaust()
    variants['banner 耗尽标记'] = sig(bs=deep)

    # banner 活跃池（active_pool_id）——默认配置每个 banner 只有单池，切换不出差异，
    # 故手工构造一个双池 banner。该维度确实参与签名（gacha_service._progress_signature），
    # 漏测会让它在将来被误删而无人察觉。
    from gacha_simulator.core.banner import Banner

    donor = next(iter(banners.values()))
    extra_pool = next(iter(donor.pools.values()))
    multi = Banner(id='multi_pool', name='多池 banner',
                   pools={'main': extra_pool, 'alt': extra_pool})
    with_multi = dict(banners)
    with_multi['multi_pool'] = multi
    baseline_multi = sig(bs=with_multi)

    switched = copy.deepcopy(with_multi)
    switched['multi_pool']._active_pool_id = 'alt'
    variants['banner 活跃池'] = sig(bs=switched)
    assert variants['banner 活跃池'] != baseline_multi, 'banner 活跃池未被纳入签名'

    assert len(variants) == 9
    unchanged = [name for name, v in variants.items() if v == base]
    assert not unchanged, f'以下维度未被签名覆盖: {unchanged}'

def test_zero_iteration_boundary():
    """3e：max_iterations=0 不抛 NameError，iterations==0 且耗尽告警正常写入。"""
    pool = _make_pool()
    target = TargetCardSet(
        [TargetCard(card_id="card_A", pool_ids=["test_pool"], quantity_needed=1)])
    svc = GachaService([pool], SmartStrategy(), AllPoolsEndCondition(1000.0), target,
                       card_defs=[{"card_id": "card_A", "initial_count": 0}])
    state = GachaState(resources={"draw_resource": 100000})

    r = svc.run_simulation_compact(state, max_iterations=0)
    assert r.iterations == 0
    assert r.total_draws == 0
    assert any('迭代预算耗尽' in w for w in r.warnings), r.warnings
    # 文案不得引用未绑定的 iteration
    assert all('iteration' not in w for w in r.warnings)

    # 充足预算下不应出现该告警
    r2 = svc.run_simulation_compact(GachaState(resources={"draw_resource": 100000}),
                                    max_iterations=200)
    assert not any('迭代预算耗尽' in w for w in r2.warnings), r2.warnings


def test_return_compact_false_with_parallel_workers_propagates_warnings():
    """3e：生产形态回归——return_compact=False 且 max_workers>1 时告警仍到达调用方。

    GUI 抽卡面板与 WebUI 在跑主模拟前都置 env.return_compact = False 且默认
    max_workers=4；只覆盖 max_workers=1 会让闸门对这两条主要入口失明。
    """
    store = load_toml(_MAIN_CONFIG)
    env = SimulationEnvBuilder.from_config_store(store)
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    env.return_compact = False
    env.strategy_key = 'fixed_count'
    env.strategy_params = {'count': 50000}

    batch = run_batch_parallel(
        env=env, target_specs=specs, initial_resources=env.initial_resources,
        num_simulations=2, max_workers=2, seed=42)

    assert batch.results == []          # return_compact=False → compact 不回传
    assert batch.warnings, '告警未经 BatchResult.warnings 到达调用方'
    assert all('零进度兜底' in w for w in batch.warnings)
