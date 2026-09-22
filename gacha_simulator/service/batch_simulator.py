#!/usr/bin/env python3
"""
统一批量模拟模块

为 cli、gui/gacha_panel、webui 及 core 的搜索与分析模块（retreat_search / worst_impact）
提供共享的并行批量模拟能力。
使用 multiprocessing.Pool + initializer 模式，静态环境通过 initializer 传入，
动态参数（target_specs, initial_resources）通过任务参数传入。
"""

from __future__ import annotations   # P58（ISSUE-303）：dataclass 字段注解延迟求值——milestone_defs: List[MilestoneDef] 免模块导入即 NameError

import fnmatch
import logging
import pickle                                    # P83 §3.5：三元组字节数口径
import random
import time                                      # P83 §3.5：阶段计时（受 collect_perf 门控）
import traceback
from typing import Dict, Any, Optional, Callable
from multiprocessing import Pool as MPPool
from dataclasses import dataclass, field as dc_field

from gacha_simulator.core.config_store import ConfigError   # P77：from_dict 类型守卫异常通道
from gacha_simulator.core.stop_condition import (
    AllPoolsEndCondition, CompositeStopCondition, create_stop_condition,
)
from gacha_simulator.core.strategy import (
    create_strategy,
)

logger = logging.getLogger(__name__)


class BatchResult:
    """批量模拟结果容器——向后兼容 list 接口，同时携带 worker 提取数据。"""

    # P83（`1e-4`）：新增 packet_bytes / stage_times 两槽。**__slots__ 与 __init__ 必须
    # 同批改**——只加槽不改构造签名则新槽永不被赋值、__slots__ 下访问即 AttributeError
    # （同 warnings 槽当年的处置）。两槽**只在 collect_perf=True 时被赋值**，默认关闭
    # 时保持空 list / 空 dict，且不做任何序列化、不取任何阶段计时。
    __slots__ = ('results', 'extraction', 'warnings', 'packet_bytes', 'stage_times')

    def __init__(self, results, extraction=None, warnings=None,
                 packet_bytes=None, stage_times=None):
        self.results = results if results is not None else []
        self.extraction = extraction
        # P79（阶段 3）：零进度 / 迭代预算耗尽告警的父进程载体。槽与构造签名必须
        # 同批改——只加槽不改 __init__ 则新槽永不被赋值、__slots__ 下访问即
        # AttributeError。
        self.warnings = warnings if warnings is not None else []
        # P83 §3.5：三元组序列化字节数（每次模拟一项），口径
        # len(pickle.dumps((compact, extraction, warnings)))。**当回归判据用，不当
        # 绝对开销读。**
        self.packet_bytes = packet_bytes if packet_bytes is not None else []
        # P83 §3.5：三段耗时（pool_start / simulate / extract）。单进程与 mp_failed
        # 路径记 pool_start=0.0 并在报告中标注「本路径无进程池」；且这两条路径的
        # 逐次提取与模拟调用同处一个 for 循环、循环体内无法按段切分，故逐次提取
        # 计入 simulate，extract 只含循环结束后的父进程合并——**跨路径的
        # simulate / extract 比值不可直接比较**。
        self.stage_times = stage_times if stage_times is not None else {}

    def __getitem__(self, i):
        return self.results[i]

    def __len__(self):
        return len(self.results)

    def __iter__(self):
        return iter(self.results)

    def __bool__(self):
        return bool(self.results)

    def __repr__(self):
        return f"BatchResult(n={len(self.results)}, extraction={'yes' if self.extraction else 'no'})"


@dataclass
class SimulationEnv:
    pools: list
    schedule_mgr: Any
    end_time: float
    pity_engine: Any
    resource_gain: Any
    pity_state_init: Optional[dict]
    card_defs: list
    initial_resources: Dict[str, float]
    target_ids: set = dc_field(default_factory=set)
    ssr_ids: set = dc_field(default_factory=set)
    all_drawable_ids: list = dc_field(default_factory=list)
    pool_end_times: Dict[str, float] = dc_field(default_factory=dict)
    gdr_context: Any = None
    daily_income: float = 0.0
    strategy_key: str = 'smart'
    strategy_params: Dict[str, Any] = dc_field(default_factory=dict)
    stop_condition: Any = None
    return_compact: bool = True
    # P83 §3.8 D1（`6a` 的四字段，2026-09-21 裁决采保守解：声明随 `1e-2` 在阶段 1
    # 落地——`1e-2` 即向 env 写这四个字段，而 SimulationEnv 是普通 dataclass，写未
    # 声明字段会**静默生效而不报错**，该缺口不会在执行时自我暴露，故须显式声明）。
    # 全部带默认值以保持跨进程 pickle 兼容（照 return_compact / n_heatmap_bins 模式）。
    # **注入点是「调用方在拿到 env 之后直接赋值」，不经 builder 的显式 keyword 表**：
    # from_config_store 与 from_dict 都以显式 keyword 列表构造 env，两张表内均无
    # profile_*——落在 builder 上是行不通的。
    profile_enabled: bool = False
    """总开关。默认 `False`——不设该字段的调用方（如经 `from_dict` 构造 env 的
    `worst_impact.py`）恒不产剖面，**如实登记、不是缺口**（§3.8 D1 第 2 条）。"""

    profile_dir: str = ''
    """**本字段取的是 run 级目录**，空则不落盘。

    §3.8 D1 把它注释为「run 级 profile **父**目录；实际落盘在
    `<profile_dir>/<run_id>/`」，而 `run_id` 在四字段里**没有载体**——worker 要往
    `<profile_dir>/<run_id>/` 写，却无从得知 `<run_id>`。故落地时把 `run_id` 折进
    本字段的取值：**调用方**（`cli.py` 的 `--profile-*` 与 `inline` 适配器）先算出
    `<--profile-dir>/<run_id>` 再赋给本字段，worker 直接往 `env.profile_dir` 写、
    `6c` 直接扫 `env.profile_dir`，两侧口径相同，无需第五个字段。
    D3 的隔离要求（no_draw 基线重跑不得混入主模拟的剖面）由此成立。"""

    profile_skip: int = 2
    """前 N 次调用不采样（warmup）。第 1 次调用含 `_run_single` 的懒加载 import 开销
    （`_wk_init` 刻意不预导入 `core` / `service`，避免 Windows spawn 下各 worker 同时
    加载 scipy 大 DLL），从第 1 次开始采样会把 import 算成热点（§3.8 D4）。"""

    profile_count: int = 50
    """**每个 worker 进程各自**采样多少次后关闭（per-worker，非本次 plan 的总量）。

    该字段随 env 被 pickle 到每个 worker，而注入点在 worker 侧的 `_wk_run_single`，
    故**每个 worker 各自从零计数**。一次 `run_batch_parallel(N, W)` 实际被插桩的样本数
    是 `profile_count × W`，真实插桩比例是 `profile_count × W / N`（§3.8 D1）。
    `Plan.validate()` 对它设了 per-worker 硬上限 500（D8）。"""
    card_overflow_map: Dict[str, list] = dc_field(default_factory=dict)  # ← P63
    # P61（Ph6，ISSUE-011）：Banner 构造定义——from_config_store 填充 List[Banner]
    # （与 pools 同对象）。_run_single 每次从它（或 pools）深拷贝重建，隔离 Banner
    # 运行时状态跨模拟泄漏（ISSUE-312）。带默认值保证跨进程 pickle 兼容。
    banner_defs: list = dc_field(default_factory=list)
    # P58（M4b，P61 落点 #1 纠正——2026-08-05）：里程碑配置定义（List[MilestoneDef]），
    # 非 MilestoneEngine 实例——_run_single 内按 per-simulation seed 延迟构造，保证
    # 计数器/RNG 状态每次模拟独立、固定种子可复现。P61 落地的 milestone_engine 字段
    # （传实例）保留 None 兜底不激活（见下方 milestone_engine 字段）。
    milestone_defs: list = dc_field(default_factory=list)
    # P61（Ph0 / ISSUE-329）：P58 里程碑 engine 跨进程来源契约——装配层（_run_single）
    # 构造 GachaService 前从本字段取出注入 register_milestone_engine（priority=0 订阅）。
    # ⚠ P58 纠正（P61 落点 #1）：本字段保留 None 兜底【不激活】——配置由 milestone_defs 承接。
    # 装配块条件由 `env.milestone_engine is not None` 改写为 `env.milestone_defs`（M4b）。
    milestone_engine: Any = None
    # P77：资源生命周期规则（List[ResourceLifecycle]），from_config_store 按 enabled
    # 门控填充（关闭时为空列表，GachaService 不建到期索引）；_run_single 透传至
    # GachaService。带默认值保证跨进程 pickle 兼容。
    resource_lifecycle_rules: list = dc_field(default_factory=list)


def _build_pity_engine_from_gui(pity_config, pools, pool_featured_map=None, pool_ssr_map=None, pool_type_map=None, rarity_rank=None):
    """P55 重写：从扁平化 PityDef dict 构造 PityEngine。

    新格式示例：{'name': 'p1', 'type': 'soft_interval', 'scope': 'ssr',
                  'deltas': ((73,0.0), (17,5.882353)), ...}
    """
    from gacha_simulator.core.pity import (
        PityEngine, PoolPitySpec, PityState,
        compute_scope_mappings,
    )
    from gacha_simulator.core.config_store import PityDef as _PityDef

    if not pity_config.get('enabled', True):
        return None

    pities_cfg = pity_config.get('pities', [])

    # P81 §4.1-6：原「假兼容」检测已删除（其旧格式分支从未实现，非新格式时由函数
    # 末尾隐式 return None 静默禁用保底）。空列表现显式 early-return，保持「无引擎」
    # 语义不变：该语义原本是由那个隐式 return 顺带产生的。
    if not pities_cfg:
        return None

    # ── P55 新路径：从扁平化 dict 构造 PityDef → create_behavior() ──
    pity_defs_list = []
    for p in pities_cfg:
        pdef = _PityDef(
            name=p.get('name', 'pity'),
            btype=p.get('type', 'soft_interval'),
            scope=p.get('scope', 'ssr'),
            target_featured=p.get('target_featured', False),
            deltas=p.get('deltas'),
            threshold=p.get('threshold'),
            counter_init=p.get('counter_init', 0),
            guaranteed_init=p.get('guaranteed_init', False),
            fate_points_init=p.get('fate_points_init', 0),
            selected_card_init=p.get('selected_card_init'),
            soft_start=p.get('start'),
            soft_end=p.get('end'),
            soft_increment=p.get('increment'),
            soft_deltas=p.get('soft_deltas'),
            cr_counter_threshold=p.get('cr_counter_threshold'),
            cr_base_rate=p.get('cr_base_rate'),
            cr_state_probs=p.get('cr_state_probs'),
            fate_threshold=p.get('fate_threshold'),
            switch_allowed=p.get('switch_allowed'),
            switch_resets_progress=p.get('switch_resets_progress'),
            pools=tuple(p.get('pools', ('*',))) if isinstance(p.get('pools', '*'), (list, tuple)) else (p.get('pools', '*'),),
            deactivate_on_early_hit=p.get('deactivate_on_early_hit', False),
            depends_on=p.get('depends_on'),
            reset=p.get('reset', ''),
        )
        pity_defs_list.append(pdef)

    state = PityState()
    # 注入 counter_init 和其他初始状态
    counter_init_overrides = pity_config.get('counter_init', {})
    from gacha_simulator.core.pity import _build_pity_state_init
    state = _build_pity_state_init(pity_defs_list, counter_init_overrides)

    if rarity_rank is None:
        rarity_rank = {'ssr': 0, 'sr': 1, 'r': 2}

    # P61（Ph6 / ISSUE-332）：遍历对象重写——pools 承载 List[Banner]，
    # for b in pools: for pool_key, p in b.pools.items(): 双重展开。
    # pool_specs 键全限定 {banner_id}.{pool_key}（多池展开自然承接 {pid}.main 键，
    # 与 PityDef.pools 全限定 fnmatch 同口径，ISSUE-005/010/011）。
    pool_specs = {}
    for b in pools:
        for pool_key, p in b.pools.items():
            qualified_key = f"{b.id}.{pool_key}"
            spec_pity_names = []
            for pdef in pity_defs_list:
                pools_ptn = pdef.pools
                if pools_ptn == ('*',) or any(fnmatch.fnmatch(qualified_key, ptn) for ptn in pools_ptn):
                    spec_pity_names.append(pdef.name)

            featured = (pool_featured_map.get(qualified_key) or pool_featured_map.get(pool_key, set())
                        if pool_featured_map else set())
            ssr = (pool_ssr_map.get(qualified_key) or pool_ssr_map.get(pool_key, set())
                   if pool_ssr_map else set())
            scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot = compute_scope_mappings(p)
            pool_specs[qualified_key] = PoolPitySpec(
                pity_names=spec_pity_names,
                featured_ids=featured,
                ssr_ids=ssr,
                scope_cards=scope_cards,
                featured_cards=featured_cards,
                scope_slots=scope_slots,
                featured_slots=featured_slots,
                card_to_slot=card_to_slot,
            )

    return PityEngine(pool_specs, pity_defs_list, state=state, rarity_rank=rarity_rank)


# --- Worker 全局变量（每个子进程内共享）---
_wk_env: Optional[SimulationEnv] = None
_wk_target_set = None
_wk_extractor = None
_wk_return_compact = True
# P83（`6b`）：worker 侧的 cProfile 采样窗口控制器。`None` 表示不采样（默认）。
_wk_profiler = None


def _load_worker_profiler():
    """惰性导入 `benchmarks/` 的 worker 侧剖析原语（P83 §3.8 `6b`）。

    **为什么必须是惰性 + 可失败的导入**：`benchmarks/` 是**开发侧测量资产、不进发布
    产物**（同 `py-spy` 的定位），打包构建下它根本不存在。若做成模块级硬 import，
    发布产物会在 import 期就崩——而剖析只是可选设施，**绝不因测量设施缺失而影响
    模拟本身**（§3.8 D7）。导入失败时返回 `None`，`profile_enabled` 即便为真也不采样，
    与默认关闭同效。
    """
    try:
        from benchmarks.perf.profilers.cprofile import WorkerProfiler
    except Exception as exc:  # pragma: no cover - 打包构建下必然走到这里
        logging.debug('worker 侧剖析原语不可用（benchmarks/ 未随产物分发）：%s', exc)
        return None
    return WorkerProfiler


def _make_worker_profiler(env: SimulationEnv):
    """按 `env` 的四字段造一个采样窗口控制器；不采样时返回 `None`。

    一律用 `getattr` 读四字段：`6a` 单独 revert 后本函数落默认值而非抛
    `AttributeError`（同 P79 `2b` 的 `getattr(store, 'stop_condition', None)` 处置）。
    """
    if not getattr(env, 'profile_enabled', False):
        return None
    directory = getattr(env, 'profile_dir', '') or ''
    if not directory:
        return None
    cls = _load_worker_profiler()
    if cls is None:
        return None
    try:
        return cls(
            profile_dir=directory,
            skip=int(getattr(env, 'profile_skip', 2)),
            count=int(getattr(env, 'profile_count', 50)),
        )
    except Exception as exc:  # pragma: no cover - 构造失败不该影响模拟
        logging.warning('采样窗口构造失败，已停用剖析：%s', exc)
        return None


def _build_target_set(card_defs, target_specs):
    """构建 TargetCardSet（单/多进程共用）。

    P61（Ph6 / ISSUE-315 / BLOCK-1 修复）：TargetCard.pool_ids 一律取 banner 级段——
    card_defs.pools 是全限定键 {banner_id}.{pool_id}（无段则原样保留），与 4 策略
    _pool_needs_target 的 banner.id 匹配口径恒同。此前主进程路径与 _wk_init 各自内联
    构建导致口径漂移（单进程 vs 多进程策略 miss），统一收敛到此公共函数。
    """
    from gacha_simulator.core import TargetCard, TargetCardSet
    if not target_specs:
        return TargetCardSet([])
    card_def_map = {c['card_id']: c for c in card_defs} if card_defs else {}
    targets = []
    for card_id, qty in target_specs.items():
        raw_pools = card_def_map.get(card_id, {}).get('pools', [])
        pools = [k.split('.')[0] if '.' in k else k for k in raw_pools]
        targets.append(TargetCard(card_id=card_id, pool_ids=pools, quantity_needed=qty))
    return TargetCardSet(targets)


def _wk_init(env: SimulationEnv, target_specs: Dict[str, int] = None):
    """子进程 initializer——将 SimulationEnv 注入子进程全局变量，预构建不可变数据。"""
    global _wk_env, _wk_target_set, _wk_extractor, _wk_return_compact, _wk_profiler
    _wk_env = env
    _wk_return_compact = getattr(env, 'return_compact', True)
    # P83（`6b`）：**只建控制器，不在这里 enable()**。`Pool.__exit__` 走 `terminate()`
    # （本机 Python 3.12.5 源码核验），进程级 enable 的收尾本就不可靠；真正的开闭
    # 窗口在 `_wk_run_single` 内围绕单次 `_run_single` 调用。
    _wk_profiler = _make_worker_profiler(env)

    # 不在此处预导入 gacha_simulator.core / .service。
    # Windows spawn 下每个 worker 同时执行 initializer，若预导入
    # scipy（通过 core → bootstrap → scipy.stats），4 个 worker
    # 同时加载大 DLL 可触发页面文件耗尽 (ImportError: DLL load
    # failed: 页面文件太小)。懒加载在 _run_single 首次调用时触发，
    # 各 worker 错峰加载，内存峰值更低。

    # P61（Ph6 / ISSUE-315）：TargetCard.pool_ids 一律为 banner 级键，与
    # run_batch_parallel 主进程共用 _build_target_set，避免口径漂移（BLOCK-1）
    _wk_target_set = _build_target_set(env.card_defs, target_specs)

    # 预构建 WorkerLocalExtractor（每个 worker 一份，并行提取）
    from gacha_simulator.core.streaming import WorkerLocalExtractor
    _wk_extractor = WorkerLocalExtractor(
        pool_end_times=env.pool_end_times,
        target_ids=env.target_ids,
        ssr_ids=env.ssr_ids,
        target_specs=target_specs or {},
        initial_resources=env.initial_resources,
        n_heatmap_bins=getattr(env, 'n_heatmap_bins', 50),
        max_keep=min(200, max(10, len(target_specs or {}) * 2 + 10)),
    )


# --- 单次模拟执行（纯函数，不依赖全局变量）---
def _run_single(env: SimulationEnv, target_set, seed: int, initial_resources: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """执行一次模拟。env 和 target_set 通过参数显式传入，不依赖全局变量。"""
    from gacha_simulator.core import GachaState
    from gacha_simulator.service import GachaService
    from gacha_simulator.core.notifier import Notifier

    random.seed(seed)

    strategy = create_strategy(env.strategy_key, env.strategy_params)
    # P79 引擎硬边界（5.2）：用户条件恒与硬边界取 any——用户条件可满足时按其收口；
    # 不可满足时（时间冻结 / 时间越界 / 目标不可达）由硬边界在 env.end_time 兜底，
    # 保证任何「策略 × 停止条件」组合都在时间线终点结束。
    # env.stop_condition 为 None 时退化为单一硬边界，与接线前逐字段等价。
    # 注意 from_dict 路径（worst_impact.py）自建条件并传同值 end_time，硬边界与
    # 之一致，冗余但无害。
    if env.stop_condition is not None:
        stop_cond = CompositeStopCondition(
            [env.stop_condition, AllPoolsEndCondition(env.end_time)], mode='any')
    else:
        stop_cond = AllPoolsEndCondition(env.end_time)

    pity_state = None
    if env.pity_state_init:
        from gacha_simulator.core.pity import PityState
        # P81 B9：from_dict 已删除 P60 之前的 'counters' 旧格式自动升级分支
        # （真实数据均为 to_dict() 产出的新格式；旧格式不再被支持）
        pity_state = PityState.from_dict(env.pity_state_init)

    # P61 Ph0：装配层创建共享 Notifier 实例，与模拟循环 emit 同一实例（§3.5「Notifier 装配位置」）
    notifier = Notifier()
    # P58（M4b，P61 落点 #1/#2/#3 纠正——2026-08-05）：装配优先——priority=0 订阅先于
    # GachaService 的 P61 priority=1 转换订阅注册（§5.2 装配顺序）。
    # - 落点 #1：配置经 env.milestone_defs（非 P61 的 milestone_engine 实例字段）——
    #   per-simulation seed 延迟构造，计数器/RNG 状态每次模拟独立、固定种子可复现；
    # - 落点 #2：register_milestone_engine 定义于 core/milestone.py，装配块 import 顺手指向它；
    # - 落点 #3：闭包捕获（非模块级全局——Windows spawn 下 worker 模块全局重置为 None）。
    # - 独立审查发现 2（2026-08-05）：engine 须【两处接线】——注册订阅 + 传入 GachaService
    #   （M4a 策略查询用），否则 build_strategy_context 传 self.milestone_engine 恒为 None、
    #   策略层里程碑查询静默退化（结算仍走订阅路径，不崩溃）。
    _milestone_engine = None
    if env.milestone_defs:
        from gacha_simulator.core.milestone import MilestoneEngine, register_milestone_engine
        _milestone_engine = MilestoneEngine(env.milestone_defs, seed=seed)
        # initial_counts 由 env.card_defs 推导（与 GachaService.run_simulation 内同源）
        _ms_initial = {}
        for _cd in env.card_defs:
            _ic = _cd.get('initial_count', 0) if isinstance(_cd, dict) else getattr(_cd, 'initial_count', 0)
            if _ic > 0:
                _cid = _cd['card_id'] if isinstance(_cd, dict) else _cd.card_id
                _ms_initial[_cid] = _ic
        register_milestone_engine(
            notifier, _milestone_engine,
            card_overflow_map=env.card_overflow_map,
            initial_counts=_ms_initial,
        )
    # P61（Ph6 / ISSUE-312，阻塞）：Banner 运行时状态跨模拟隔离——env.pools 承载
    # List[Banner]，直接传入则 draw/_check_transitions 修改的 _pool_draws/_exhausted/
    # _active_pool_id 等泄漏到下次模拟（固定种子不可复现）。每次构造 GachaService 前
    # 深拷贝（或从 banner_defs 重建），Pool 纯数据可安全 deepcopy。
    import copy
    banners = copy.deepcopy(env.banner_defs or env.pools)
    service = GachaService(
        banners, strategy, stop_cond, target_set,
        schedule_manager=env.schedule_mgr,
        pity_engine=env.pity_engine,
        resource_gain=env.resource_gain,
        pity_state=pity_state,
        ssr_ids=env.ssr_ids,
        card_defs=env.card_defs,
        card_overflow_map=env.card_overflow_map,
        notifier=notifier,
        milestone_engine=_milestone_engine,   # P58（M4b）：策略层查询 + M4a 传参（None 时无里程碑行为）
        # P77：资源生命周期规则（env 侧已按 enabled 门控；规则为纯数据，浅拷贝列表隔离）
        resource_lifecycle_rules=list(env.resource_lifecycle_rules or []),
    )
    state = GachaState(resources=dict(initial_resources))
    return service.run_simulation_compact(state)


def _wk_run_single(args):
    """子进程 worker 入口——模拟 + 本地提取。

    统一返回 **三元组** ``(compact_or_None, extraction, warnings)``：``return_compact``
    只决定 compact 位是否为 None，**不再决定是否携带告警**。P79（阶段 3）：GUI 抽卡
    面板与 WebUI 在跑主模拟前置 ``env.return_compact = False`` 且默认 ``max_workers=4``，
    若告警随 compact 一并丢弃（原实现 False 分支只 ``return extraction``），子进程写进
    ``CompactResult.warnings`` 的告警从未跨进程回传，而测试以 ``max_workers=1`` 走进程内
    路径恰好全绿。

    ⚠ 四条 return 的 arity 必须一致为 3：只改末条时两条早退返回的 ``None`` / 2 元组会在
    父进程的新守卫（``len(result) == 3``）下全部落入 else 分支被整体当作 ext_pkt，
    compact 与 warnings 双丢且无告警。
    """
    seed, initial_resources = args
    try:
        # P83（`6b`）：开闭窗口**围绕单次 `_run_single` 调用**（§3.8 D2）。窗口在
        # `profiler is None`（默认）时完全不介入，故不采样时的热路径与改动前逐项一致。
        # 剖面结果经 `dump_stats` 走文件，**不改变下面四条 return 的 arity**。
        if _wk_profiler is None:
            compact = _run_single(_wk_env, _wk_target_set, seed, initial_resources)
        else:
            with _wk_profiler.window():
                compact = _run_single(_wk_env, _wk_target_set, seed, initial_resources)
    except Exception:
        traceback.print_exc()
        return (None, None, [])

    if compact is None:
        return (None, None, [])

    extraction = None
    if _wk_extractor is not None:
        try:
            extraction = _wk_extractor.process(compact)
        except Exception:
            traceback.print_exc()

    warnings = list(getattr(compact, 'warnings', []) or [])
    if _wk_return_compact:
        return (compact, extraction, warnings)
    return (None, extraction, warnings)


# --- 公共批量模拟接口 ---

def _packet_size(compact, extraction, warnings) -> int:
    """三元组序列化长度——P83 §3.5 的字节数口径。

    量的是**整个三元组**而非只量 compact：`extraction` 包内含
    `heatmap_ach_bins` / `heatmap_res_bins` 两个长度等于本次抽卡次数的数组，是唯一
    随抽数增长的传输分量（P12 的 Phase 1.5 砍掉 93% 所针对的正是它），只量 compact
    会正好漏掉它。另：**不可把各分量各自序列化后相加当总量**——实测分项之和
    1996 KB > 整体 1688 KB（118%），pickle 的 memo 在同一次序列化内共享重复对象引用。

    **只在 collect_perf=True 时调用**：一次约 1688 KB 的序列化不是零成本操作，
    而 gui-qt / webui 每完成一次主模拟都要再跑一次 no_draw 基线，默认记录即构成
    测量者效应。
    """
    return len(pickle.dumps((compact, extraction, warnings)))


def _stage_times(collect_perf: bool, pool_start: float, simulate: float,
                 extract: float) -> dict:
    """三段耗时的统一构造。

    未开启采集时返回**空 dict**——**不假装采到了三个 0**：「没采」与「采到 0」是
    两回事，前者应记为未采集（归一后由 `WARN_STAGES_NOT_COLLECTED` 标注）。
    """
    if not collect_perf:
        return {}
    return {'pool_start': pool_start, 'simulate': simulate, 'extract': extract}


def run_batch_parallel(
    env: SimulationEnv,
    target_specs: Dict[str, int],
    initial_resources: Dict[str, float],
    num_simulations: int,
    max_workers: int,
    seed: int = 0,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    strategy_key: str = '',
    strategy_params: Optional[dict] = None,
    on_result: Optional[Callable[[Dict[str, Any]], None]] = None,
    collect_perf: bool = False,
) -> 'BatchResult':
    """批量并行模拟。

    env: 模拟环境（池、保底、资源等静态配置）。
    target_specs / initial_resources: 每次模拟的动态参数。
    strategy_key / strategy_params: 可为空，为空时使用 env 中的默认值。
    collect_perf: P83 §3.5 的 opt-in 门控（默认 False 即今日行为）。开启时
        `BatchResult` 的 packet_bytes / stage_times 两槽才被赋值；**关闭时两槽
        保持空、`pickle.dumps` 一次都不调用、阶段计时一个都不取**。之所以用显式
        参数而非环境变量：开关可事后从调用点判断，不引入进程全局隐式状态。
        `cli.py --perf-json` 是它的唯一开启者。
    """
    if strategy_key:
        env.strategy_key = strategy_key
    if strategy_params is not None:
        env.strategy_params = strategy_params

    # 构建 TargetCardSet（单/多进程共用）
    target_set = _build_target_set(env.card_defs, target_specs)

    # P79（阶段 3）：三条执行路径（进程内 / MPPool / mp_failed 兜底）各自的告警
    # 统一累加到此，在各自的终点写入 BatchResult.warnings——兜底路径正是 MPPool
    # 异常时 GUI / WebUI 主模拟实际走的路径，漏汇总即静默丢失告警。
    warnings_acc: list = []

    # P83（`1e-4`）：两槽的载体与三段计时。**全部受 collect_perf 门控**——关闭时
    # packet_bytes 恒为空 list、stage_times 恒为空 dict、pickle.dumps 零调用、
    # 阶段计时零采集，即三条产品路径的默认行为与改动前逐项一致。
    packet_bytes_acc: list = []
    pool_start_sec = 0.0
    simulate_sec = 0.0
    extract_sec = 0.0

    if max_workers <= 1:
        # 单进程路径：直接调用 _run_single，同时本地提取
        from gacha_simulator.core.streaming import WorkerLocalExtractor, merge_extraction_packets
        _local_ext = WorkerLocalExtractor(
            pool_end_times=env.pool_end_times,
            target_ids=env.target_ids,
            ssr_ids=env.ssr_ids,
            target_specs=target_specs or {},
            initial_resources=env.initial_resources,
            n_heatmap_bins=getattr(env, 'n_heatmap_bins', 50),
            max_keep=min(200, max(10, len(target_specs or {}) * 2 + 10)),
        )
        results = [] if on_result is None else None
        extraction_packets = []
        n_failed = 0
        # 本路径无进程池，故 pool_start 记 0.0（报告据此标注「本路径无进程池」）
        _sim_started = time.perf_counter() if collect_perf else 0.0
        for i in range(num_simulations):
            s = seed + i if seed >= 0 else random.randint(0, 999999)
            try:
                result = _run_single(env, target_set, s, initial_resources)
            except Exception:
                traceback.print_exc()
                result = None
            if result is not None:
                ext_pkt = None
                try:
                    ext_pkt = _local_ext.process(result)
                except Exception:
                    pass
                if ext_pkt is not None:
                    extraction_packets.append(ext_pkt)
                sim_warnings = list(getattr(result, 'warnings', []) or [])
                warnings_acc.extend(sim_warnings)
                if collect_perf:
                    # 三元组落地处。口径与 _wk_run_single 的返回值逐项对应：
                    # 单进程路径不设 env.return_compact，故首分量恒为 compact 本体
                    # （与 MPPool 路径在 return_compact=True 下一致）。
                    packet_bytes_acc.append(_packet_size(result, ext_pkt, sim_warnings))
            if on_result is not None:
                if result is not None:
                    on_result(result)
                else:
                    n_failed += 1
            else:
                if result is not None:
                    results.append(result)
                else:
                    n_failed += 1
            if progress_callback:
                progress_callback(i + 1, num_simulations)
        if collect_perf:
            # 逐次提取与模拟调用同处一个 for 循环、循环体内无法按段切分，故逐次
            # 提取的耗时计入 simulate（§3.5 的口径例外）。
            simulate_sec = time.perf_counter() - _sim_started
        if n_failed > 0:
            logging.warning("%s/%s simulations failed", n_failed, num_simulations)
        _extract_started = time.perf_counter() if collect_perf else 0.0
        merged_ext = merge_extraction_packets(
            extraction_packets,
            heatmap_config={'n_heatmap_bins': getattr(env, 'n_heatmap_bins', 50), 'max_keep': 200},
        ) if extraction_packets else None
        if collect_perf:
            extract_sec = time.perf_counter() - _extract_started
        return BatchResult(results if on_result is None else [], merged_ext,
                           warnings=warnings_acc,
                           packet_bytes=packet_bytes_acc,
                           stage_times=_stage_times(collect_perf, pool_start_sec,
                                                    simulate_sec, extract_sec))

    seeds = [seed + i if seed >= 0 else random.randint(0, 999999) for i in range(num_simulations)]
    tasks = [(s, initial_resources) for s in seeds]

    # 降低 chunksize 以加快首次进度回调。
    # 原公式 max(1, N/(W*4)) 对 N=1000/W=18 给出 14，首次进度需等 14 次模拟完成。
    # 改为 divisor=16 后，chunksize≈4，首次进度约 1 秒内出现，同时保持合理 IPC 效率。
    chunksize = max(1, num_simulations // (max_workers * 16))

    # Windows spawn 模式下频繁创建/销毁 Pool 可导致 worker 进程 EOFError，
    # 进而引发父进程 MaybeEncodingError。以逐级降并发重试来绕过系统资源瓶颈。
    mp_failed = False
    for _retry in range(3):  # workers=N, N/2, N/4
        workers = max(1, max_workers // (2 ** _retry))
        try:
            _pool_started = time.perf_counter() if collect_perf else 0.0
            with MPPool(
                processes=workers,
                initializer=_wk_init,
                initargs=(env, target_specs),
            ) as mp_pool:
                if collect_perf:
                    # 进程池构造到就绪（含 initializer 执行完毕）
                    pool_start_sec = time.perf_counter() - _pool_started
                    _sim_started = time.perf_counter()
                results = [] if on_result is None else None
                extraction_packets = []
                n_failed = 0
                for i, result in enumerate(mp_pool.imap_unordered(_wk_run_single, tasks, chunksize=chunksize)):
                    # 解包 worker 返回值：统一为三元组
                    # (compact_or_None, extraction, warnings)——return_compact 只决定
                    # compact 位是否为 None。守卫长度须随三元组由 2 改为 3。
                    if isinstance(result, tuple) and len(result) == 3:
                        compact, ext_pkt, warns = result
                    else:
                        compact = None
                        ext_pkt = result
                        warns = []
                    if warns:
                        warnings_acc.extend(warns)

                    if collect_perf:
                        # 三元组落地处：worker 返回值即三元组本体，逐项对应
                        # _wk_run_single 的 (compact_or_None, extraction, warnings)。
                        packet_bytes_acc.append(_packet_size(compact, ext_pkt, list(warns)))

                    if on_result is not None:
                        if compact is not None:
                            on_result(compact)
                        else:
                            n_failed += 1
                    elif compact is not None:
                        results.append(compact)

                    if ext_pkt is not None:
                        extraction_packets.append(ext_pkt)

                    if progress_callback:
                        progress_callback(i + 1, num_simulations)
                if collect_perf:
                    # 本路径的提取在 worker 内，父进程侧只有下方的收尾合并，
                    # 故 simulate 不含逐次提取（与单进程 / mp_failed 的口径不同）。
                    simulate_sec = time.perf_counter() - _sim_started
                if n_failed > 0:
                    logging.warning("%s/%s simulations failed", n_failed, num_simulations)
            break
        except Exception as e:
            ename = type(e).__name__
            if workers > 1:
                logging.warning("%s，以 workers=%s 重试…", ename, max(1, workers // 2))
                time.sleep(0.5)
                continue
            # workers=1 也失败 → 记录并走单进程兜底
            import traceback as _tb
            logging.warning("%s (workers=1)，回退到单进程内联执行", ename)
            _tb.print_exc()
            mp_failed = True
            break
    else:
        # 循环未 break（3 次迭代全部 workers < 1 或边界情况）
        mp_failed = True

    if mp_failed:
        # 单进程兜底：直接在当前线程循环调用 _run_single，不 spawn 子进程
        # 需要手动初始化 extractor（Pool 路径由 _wk_init 完成）
        from gacha_simulator.core.streaming import WorkerLocalExtractor
        _local_extractor = WorkerLocalExtractor(
            pool_end_times=env.pool_end_times,
            target_ids=env.target_ids,
            ssr_ids=env.ssr_ids,
            target_specs=target_specs or {},
            initial_resources=env.initial_resources,
            n_heatmap_bins=getattr(env, 'n_heatmap_bins', 50),
            max_keep=min(200, max(10, len(target_specs or {}) * 2 + 10)),
        )
        results = [] if on_result is None else None
        extraction_packets = []
        n_failed = 0
        # 本路径无进程池，pool_start 记 0.0（同单进程路径）
        pool_start_sec = 0.0
        _sim_started = time.perf_counter() if collect_perf else 0.0
        for idx in range(num_simulations):
            s = seeds[idx]
            try:
                compact = _run_single(env, target_set, s, initial_resources)
            except Exception:
                import traceback as _tb2
                _tb2.print_exc()
                compact = None
            if compact is not None:
                ext_pkt = None
                try:
                    ext_pkt = _local_extractor.process(compact)
                except Exception:
                    pass
                if on_result is not None:
                    on_result(compact)
                else:
                    results.append(compact)
                if ext_pkt is not None:
                    extraction_packets.append(ext_pkt)
                sim_warnings = list(getattr(compact, 'warnings', []) or [])
                warnings_acc.extend(sim_warnings)
                if collect_perf:
                    # 三元组落地处（本路径 compact 恒非 None，与单进程路径同型）
                    packet_bytes_acc.append(_packet_size(compact, ext_pkt, sim_warnings))
            else:
                n_failed += 1
            if progress_callback:
                progress_callback(idx + 1, num_simulations)
        if collect_perf:
            # 同单进程路径：逐次提取与模拟调用同处一个 for 循环，逐次提取计入
            # simulate，extract 只含循环结束后的父进程合并。
            simulate_sec = time.perf_counter() - _sim_started
        if n_failed > 0:
            logging.warning("%s/%s simulations failed (single-process fallback)", n_failed, num_simulations)

    # 合并 worker / 单进程提取结果
    _extract_started = time.perf_counter() if collect_perf else 0.0
    merged_extraction = None
    if extraction_packets:
        from gacha_simulator.core.streaming import merge_extraction_packets
        n_heatmap_bins = getattr(env, 'n_heatmap_bins', 50)
        merged_extraction = merge_extraction_packets(
            extraction_packets,
            heatmap_config={'n_heatmap_bins': n_heatmap_bins, 'max_keep': 200},
        )

    raw_results = results if on_result is None else []
    if collect_perf:
        extract_sec = time.perf_counter() - _extract_started

    # 统一终点：兼作 MPPool 与 mp_failed 兜底的汇合点
    return BatchResult(raw_results, merged_extraction, warnings=warnings_acc,
                       packet_bytes=packet_bytes_acc,
                       stage_times=_stage_times(collect_perf, pool_start_sec,
                                                simulate_sec, extract_sec))


class SimulationEnvBuilder:
    @staticmethod
    def from_config_store(config_store) -> SimulationEnv:
        from gacha_simulator.core.pool import Pool, Reward, parse_cost_string
        from gacha_simulator.core.schedule import PoolScheduleManager, PoolSchedule

        # P79 4a2：原局部 DAY = 86400 随内联 end_time 表达式一并移除——
        # 终点公式已提为 core 层 resolve_banner_end_time（其内自带 DAY）
        banner_entries = config_store.banner.banners
        schedules = []
        banners = []
        pool_featured_map = {}
        pool_ssr_map = {}

        # P61（Ph6）：from_config_store 改从 store.banner 解析（ISSUE-001/011）。
        # 每个 BannerEntry → 运行时 Banner（Pool.id 为 pools 字典键 'main'/'free_10pull'）；
        # 全限定键 {banner_id}.{pool_id} 供保底绑定/统计/卡池回填消费（ISSUE-010/011）。
        for be in banner_entries:
            inner_pools = {}
            for bp in be.pools:
                rewards = []
                # P61（Ph6 / ISSUE-006）：featured_ids 由 rewards 的 featured=True 标志聚合
                featured_ids = {r['card_id'] for r in bp.rewards if r.get('featured')}
                ssr_ids = set()
                for r in bp.rewards:
                    cid = r.get('card_id', '')
                    # P61（Ph6 / ISSUE-007）：Reward.extra_info['rarity'] 小写回填——
                    # match='rarity' 的 _check_transitions 唯一数据源（漏注入则 KeyError/恒空）
                    rwd = Reward(
                        id=cid, name=cid,
                        resources_gained=dict(r.get('resources_gained', {}) or {}),
                        extra_info={'rarity': str(r.get('rarity', 'r')).lower(),
                                    'featured': r.get('featured', False)},
                    )
                    rewards.append((rwd, r.get('probability', 0) / 100.0))
                    if str(r.get('rarity', '')).upper() == 'SSR' and cid != '_no_card':
                        ssr_ids.add(cid)

                if not featured_ids and ssr_ids:
                    featured_ids = set(ssr_ids)

                qualified_key = f"{be.id}.{bp.id}"
                pool_featured_map[qualified_key] = featured_ids
                pool_ssr_map[qualified_key] = ssr_ids

                cost_str = bp.cost or 'draw_resource:160'
                parsed_cost = parse_cost_string(cost_str) if cost_str else [{'draw_resource': 160}]
                pool = Pool(
                    id=bp.id,
                    name=bp.id,
                    cost=parsed_cost,
                    rewards=rewards,
                    excludes_all_pity=bp.excludes_all_pity,
                    max_draws=bp.max_draws,
                    # P61（Ph6 / ISSUE-313）：exchange_card_id 从 BannerPoolEntry 透传——
                    # smart/pity_reserve/pool_quota/stop_on_target 4 策略以
                    # pool.is_exchange and pool.exchange_card_id == t.card_id 定位兑换池，
                    # 漏透传则 banner 模式兑换池匹配静默失效
                    exchange_card_id=bp.exchange_card_id,
                    batch_size=bp.batch_size,
                    epitomizable_cards=list(bp.epitomizable_cards),
                )
                inner_pools[bp.id] = pool

            # P61（Ph6）：Banner 级时间窗口直接透传（TOML 解析边界已 *DAY 为秒）；
            # lifecycle 规则经 TransitionRule 承载；max_draws 透传
            from gacha_simulator.core.banner import Banner, TransitionRule
            banner = Banner(
                id=be.id,
                name=be.name,
                pools=inner_pools,
                lifecycle=[
                    TransitionRule(
                        condition=lc.condition,
                        pool=lc.pool,
                        at_value=lc.at,
                        match=lc.match,
                        action=lc.action,
                        target=lc.target,
                    )
                    for lc in be.lifecycle
                ],
                max_draws=be.max_draws,
                available_from=be.available_from,
                available_until=be.available_until,
            )
            banners.append(banner)
            schedules.append(PoolSchedule(
                pool_id=be.id,
                available_from=be.available_from,
                available_until=be.available_until,
            ))

        schedule_mgr = PoolScheduleManager(schedules)
        # P79 5.5：时间线终点改由 core 层单一实现点供给（原为内嵌局部表达式）。
        # 该公式同时服务 GUI 只读提示与解析期校验，复制到别处即形成第二真相源。
        from gacha_simulator.core.config_store import resolve_banner_end_time
        end_time = resolve_banner_end_time(schedules)

        pity_cfg_dict = {'enabled': True, 'pities': [], 'counter_init': {}}
        pc = config_store.pity
        if pc and hasattr(pc, 'pities'):
            pity_cfg_dict['enabled'] = getattr(pc, 'enabled', True)
            for pd in pc.pities:
                # P55：扁平化 PityDef → 兼容旧 dict 格式（供 _build_pity_engine_from_gui 消费）
                pentry = {
                    'name': pd.name,
                    'type': getattr(pd, 'btype', 'soft'),
                    'scope': getattr(pd, 'scope', 'ssr'),
                    'target_featured': getattr(pd, 'target_featured', False),
                    'deltas': getattr(pd, 'deltas', None),
                    'threshold': getattr(pd, 'threshold', None),
                    'reset': getattr(pd, 'reset', ''),
                    'pools': getattr(pd, 'pools', ('*',)),
                    'counter_init': getattr(pd, 'counter_init', 0),
                    'guaranteed_init': getattr(pd, 'guaranteed_init', False),
                    'fate_points_init': getattr(pd, 'fate_points_init', 0),
                    'selected_card_init': getattr(pd, 'selected_card_init', None),
                    'deactivate_on_early_hit': getattr(pd, 'deactivate_on_early_hit', False),
                    'depends_on': getattr(pd, 'depends_on', None),
                    'start': getattr(pd, 'soft_start', None),
                    'end': getattr(pd, 'soft_end', None),
                    'increment': getattr(pd, 'soft_increment', None),
                    'soft_deltas': getattr(pd, 'soft_deltas', None),
                    'cr_counter_threshold': getattr(pd, 'cr_counter_threshold', None),
                    'cr_base_rate': getattr(pd, 'cr_base_rate', None),
                    'cr_state_probs': getattr(pd, 'cr_state_probs', None),
                    'fate_threshold': getattr(pd, 'fate_threshold', None),
                    'switch_allowed': getattr(pd, 'switch_allowed', None),
                    'switch_resets_progress': getattr(pd, 'switch_resets_progress', None),
                }
                pity_cfg_dict['pities'].append(pentry)
                # counter_init 从 PityDef 读取
                ci = getattr(pd, 'counter_init', 0)
                if ci:
                    pity_cfg_dict['counter_init'][pd.name] = ci

        rarity_rank = {k.lower(): v for k, v in config_store.rarity_rank.items()}
        pity_engine = _build_pity_engine_from_gui(
            pity_cfg_dict, banners, pool_featured_map, pool_ssr_map, {},
            rarity_rank=rarity_rank)

        initial_resources = {}
        ir_raw = config_store.initial_resources
        if isinstance(ir_raw, dict):
            initial_resources = dict(ir_raw)
        elif isinstance(ir_raw, list):
            for ir in ir_raw:
                rid = getattr(ir, 'resource_id', 'draw_resource')
                amt = getattr(ir, 'amount', 0)
                if amt > 0:
                    initial_resources[rid] = initial_resources.get(rid, 0) + float(amt)

        resource_gain = SimulationEnvBuilder._build_resource_gain(config_store, end_time)

        # P75（阶段 3）：无条件产出完整初始状态快照——engine 构造完成后立即取快照，
        # 此时 _state 为 _build_pity_state_init 结果（含 counter_init / guaranteed_init /
        # fate_points_init / selected_card_init + behaviors 构造期写入的 _active=True）。
        # 纯重定向后每模拟 from_dict 重建的 B 需含全部初始态（ISSUE-106），
        # 否则 _active 读默认 False、计数型保底永不触发。
        pity_state_init = None
        if pity_engine is not None:
            _ps_snapshot = getattr(pity_engine, '_state', None)
            if _ps_snapshot is not None:
                pity_state_init = _ps_snapshot.to_dict()

        # 构建卡牌列表，pools 从池子分布实时推导（非从 store.card_defs 复制）
        # —— 这样用户在 GUI 中修改池子绑定后，pools 自动反映最新状态
        card_defs = []
        for cd in config_store.card_defs:
            card_defs.append({
                'card_id': cd.card_id,
                'name': getattr(cd, 'name', ''),
                'rarity': getattr(cd, 'rarity', 'r'),
                'pools': [],
                'initial_count': getattr(cd, 'initial_count', 0),
            })
        card_index = {cd['card_id']: i for i, cd in enumerate(card_defs)}
        # P61（Ph6）：pools 从 banner 池实时推导（全限定键 {banner_id}.{pool_id} 入 card_defs.pools）
        for be in banner_entries:
            for bp in be.pools:
                qkey = f"{be.id}.{bp.id}"
                for r in bp.rewards:
                    cid = r.get('card_id', '')
                    if cid in card_index and cid != '_no_card':
                        idx = card_index[cid]
                        if qkey not in card_defs[idx]['pools']:
                            card_defs[idx]['pools'].append(qkey)

        target_ids = set()
        for tc in getattr(config_store, 'target_cards', []):
            target_ids.add(tc.card_id)

        ssr_ids = set()
        for cd in config_store.card_defs:
            if getattr(cd, 'rarity', '').upper() == 'SSR':
                ssr_ids.add(cd.card_id)
        if not ssr_ids:
            for pid, ssr_set in pool_ssr_map.items():
                ssr_ids.update(ssr_set)

        # P61（Ph6 / AUDIT-BREAK-5 ①）：all_drawable_ids 遍历 banner 池展开
        all_drawable_ids = [r.id for b in banners for p in b.pools.values()
                            for r, _ in p.rewards]
        pool_end_times = {s.pool_id: s.available_until for s in schedules}

        from gacha_simulator.core.gdr import GDRContext
        target_specs = {tc.card_id: getattr(tc, 'quantity', 1) for tc in getattr(config_store, 'target_cards', [])}

        # 从 gain_rules 计算日均资源收入（供需要该字段的 GDR 使用）
        gain_per_day: Dict[str, float] = {}
        for gr in getattr(config_store, 'gain_rules', []):
            divisor = 1.0
            if gr.rule_type == 'every_n_days':
                try:
                    n = int(gr.param) if gr.param else 1
                    divisor = max(1, n)
                except (ValueError, TypeError):
                    divisor = 1
            elif gr.rule_type == 'weekly':
                divisor = 7
            elif gr.rule_type in ('monthly_day', 'monthly_week'):
                divisor = 30.4375
            for rid, amt in (gr.gains or {}).items():
                gain_per_day[rid] = gain_per_day.get(rid, 0.0) + float(amt) / divisor

        gdr_context = GDRContext(
            target_specs=target_specs,
            ssr_ids=ssr_ids,
            all_drawable_ids=all_drawable_ids,
            initial_resources=dict(initial_resources),
            resource_gain_per_day=gain_per_day,
        )

        strategy_key = getattr(config_store, 'strategy_key', 'smart') or 'smart'
        strategy_params = dict(getattr(config_store, 'strategy_params', {}) or {})

        # P58（M4b）：里程碑配置提取——enabled 总闸门控（REVIEW-R1-FIX: ISSUE-302）。
        # enabled=False 时 milestone_defs 为空列表——与 pity 路径 _build_pity_engine_from_gui 的
        # enabled 语义对齐（『禁用=无效+保存即删除』闭环的 runtime 侧修复）。
        from gacha_simulator.core.config_store import MilestoneConfig
        _ms_cfg = getattr(config_store, 'milestone', MilestoneConfig())
        _milestone_defs = list(_ms_cfg.milestones) if _ms_cfg.enabled else []

        # P77：资源生命周期规则提取：enabled 总闸门控（关闭时透传空列表，GachaService
        # 构造期不建到期索引、跳过到期检查）。深拷贝隔离跨模拟状态。
        import copy as _copy
        from gacha_simulator.core.resource_lifecycle import ResourceLifecycleConfig
        _lc_cfg = getattr(config_store, 'resource_lifecycle', ResourceLifecycleConfig())
        _lifecycle_rules = _copy.deepcopy(list(_lc_cfg.rules)) if _lc_cfg.enabled else []

        # P79（缺陷 A 的另一半）：用户停止条件树 → 对象。字段 stop_condition 由
        # 子任务 4a1 引入、TOML 填充由 4a3 引入，二者均晚于本项，故以 getattr
        # 容忍字段缺失——硬取属性会使本项落地即对旧 ConfigStore 抛
        # AttributeError。树为 None / 空树时 env.stop_condition 为 None，
        # 由 _run_single 退化为单一硬边界（与接线前等价）。
        # 注意：只改 _run_single 不生效——生产路径（CLI / GUI / WebUI）的
        # env.stop_condition 恒为 None 的根因就在此处。
        _stop_tree = getattr(config_store, 'stop_condition', None)
        _stop_condition = create_stop_condition(_stop_tree) if _stop_tree else None

        return SimulationEnv(
            pools=banners,
            schedule_mgr=schedule_mgr,
            end_time=end_time,
            pity_engine=pity_engine,
            resource_gain=resource_gain,
            pity_state_init=pity_state_init,
            card_defs=card_defs,
            initial_resources=initial_resources,
            target_ids=target_ids,
            ssr_ids=ssr_ids,
            all_drawable_ids=all_drawable_ids,
            pool_end_times=pool_end_times,
            gdr_context=gdr_context,
            strategy_key=strategy_key,
            strategy_params=strategy_params,
            card_overflow_map=dict(getattr(config_store, 'card_overflow_map', {})),
            # P61（Ph6 / ISSUE-011）：Banner 构造定义（与 pools 同对象，_run_single 深拷贝用）
            banner_defs=banners,
            # P58：里程碑配置——_run_single 内延迟构造 MilestoneEngine（enabled=False 时为空列表）
            milestone_defs=_milestone_defs,
            # P61 已落地的 milestone_engine 字段传 None（不激活）——由 milestone_defs 承接
            milestone_engine=None,
            # P77：资源生命周期规则（enabled 门控后）
            resource_lifecycle_rules=_lifecycle_rules,
            # P79：用户停止条件（条件树 → 对象；None 时由 _run_single 退化为硬边界）
            stop_condition=_stop_condition,
        )

    @staticmethod
    def from_dict(config: dict) -> 'SimulationEnv':
        """从字典构造 SimulationEnv（供 worst_impact.py 等不使用 ConfigStore 的调用方使用）。"""
        # P77：仅接受单一规范键 resource_lifecycle_rules（不回退顶层 resource_lifecycle，
        # 该名与 ConfigStore.resource_lifecycle: ResourceLifecycleConfig 同名，回退分支可能
        # 取到配置对象而非 List[ResourceLifecycle]，遍历期类型错误且与 TOML 嵌套路径混淆）
        _lc = config.get('resource_lifecycle_rules', [])
        if not isinstance(_lc, list):
            raise ConfigError(
                'resource_lifecycle_rules 须为 List[ResourceLifecycle]，'
                f'当前为 {type(_lc).__name__}')
        return SimulationEnv(
            pools=config['pools'],
            schedule_mgr=config['schedule_mgr'],
            end_time=config['end_time'],
            pity_engine=config['pity_engine'],
            resource_gain=config.get('resource_gain'),
            pity_state_init=config.get('pity_state_init'),
            card_defs=config['card_defs'],
            initial_resources=config.get('initial_resources', {}),
            ssr_ids=config.get('ssr_ids', set()),
            strategy_key=config.get('strategy_key', 'smart'),
            strategy_params=config.get('strategy_params', {}),
            stop_condition=config.get('stop_condition'),
            card_overflow_map=config.get('card_overflow_map', {}),
            milestone_defs=config.get('milestone_defs', []),   # ← P58：worst_impact 等非 ConfigStore 调用方不丢失
            resource_lifecycle_rules=_lc,                       # ← P77
        )

    @staticmethod
    def _build_resource_gain(config_store, end_time):
        from gacha_simulator.core.resource_gain import (
            ScheduleResourceGain, CompositeResourceGain,
            expand_gain_rules_to_schedule,
        )
        import datetime as _dt

        gain_functions = []
        total_days = int(end_time / 86400) + 1 if end_time else 30

        # 解析起始日期（默认当天）
        start_date_str = getattr(config_store, 'sim_start_date', None)
        if not start_date_str:
            start_date = _dt.date.today()
        else:
            try:
                start_date = _dt.date.fromisoformat(start_date_str)
            except (ValueError, TypeError):
                start_date = _dt.date.today()

        schedule = expand_gain_rules_to_schedule(
            gain_rules=list(getattr(config_store, 'gain_rules', [])),
            day_overrides=list(getattr(config_store, 'day_overrides', [])),
            total_days=total_days,
            start_date=start_date,
        )

        if schedule:
            gain_functions.append(ScheduleResourceGain(schedule, total_days))

        if gain_functions:
            if len(gain_functions) == 1:
                return gain_functions[0]
            return CompositeResourceGain(gain_functions)
        return None
