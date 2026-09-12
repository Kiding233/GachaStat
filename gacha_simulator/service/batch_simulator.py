#!/usr/bin/env python3
"""
统一批量模拟模块

为 gacha_panel、strategy_panel、resource_search_panel 提供共享的并行批量模拟能力。
使用 multiprocessing.Pool + initializer 模式，静态环境通过 initializer 传入，
动态参数（target_specs, initial_resources）通过任务参数传入。
"""

from __future__ import annotations   # P58（ISSUE-303）：dataclass 字段注解延迟求值——milestone_defs: List[MilestoneDef] 免模块导入即 NameError

import fnmatch
import logging
import random
import traceback
from typing import Dict, Any, Optional, Callable
from multiprocessing import Pool as MPPool
from dataclasses import dataclass, field as dc_field

from gacha_simulator.core.config_store import ConfigError   # P77：from_dict 类型守卫异常通道
from gacha_simulator.core.stop_condition import AllPoolsEndCondition, create_stop_condition
from gacha_simulator.core.strategy import (
    create_strategy,
)

logger = logging.getLogger(__name__)


class BatchResult:
    """批量模拟结果容器——向后兼容 list 接口，同时携带 worker 提取数据。"""

    __slots__ = ('results', 'extraction')

    def __init__(self, results, extraction=None):
        self.results = results if results is not None else []
        self.extraction = extraction

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
    旧格式向后兼容：{'name': 'p1', 'type': 'soft', 'params': {...}, ...}
    """
    from gacha_simulator.core.pity import (
        PityEngine, PoolPitySpec, PityState,
        compute_scope_mappings,
    )
    from gacha_simulator.core.config_store import PityDef as _PityDef

    if not pity_config.get('enabled', True):
        return None

    pities_cfg = pity_config.get('pities', [])

    # 检测新旧格式
    is_new_format = any('scope' in p or 'deltas' in p or 'target_featured' in p
                        for p in pities_cfg)

    if is_new_format:
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
    global _wk_env, _wk_target_set, _wk_extractor, _wk_return_compact
    _wk_env = env
    _wk_return_compact = getattr(env, 'return_compact', True)

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
    if env.stop_condition is not None:
        stop_cond = env.stop_condition
    else:
        stop_cond = AllPoolsEndCondition(env.end_time)

    pity_state = None
    if env.pity_state_init:
        from gacha_simulator.core.pity import PityState
        # P60：from_dict 已内置旧格式自动升级（检测 'counters' 键自动迁移）
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

    return_compact=True（默认）时返回 (compact, extraction) 元组以兼容 on_result 回调。
    return_compact=False 时只返回 extraction，节省 pickle 传输开销。
    """
    seed, initial_resources = args
    try:
        compact = _run_single(_wk_env, _wk_target_set, seed, initial_resources)
    except Exception:
        traceback.print_exc()
        return (None, None) if _wk_return_compact else None

    if compact is None:
        return (None, None) if _wk_return_compact else None

    extraction = None
    if _wk_extractor is not None:
        try:
            extraction = _wk_extractor.process(compact)
        except Exception:
            traceback.print_exc()

    if _wk_return_compact:
        return (compact, extraction)
    return extraction


# --- 公共批量模拟接口 ---
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
) -> 'BatchResult':
    """批量并行模拟。

    env: 模拟环境（池、保底、资源等静态配置）。
    target_specs / initial_resources: 每次模拟的动态参数。
    strategy_key / strategy_params: 可为空，为空时使用 env 中的默认值。
    """
    if strategy_key:
        env.strategy_key = strategy_key
    if strategy_params is not None:
        env.strategy_params = strategy_params

    # 构建 TargetCardSet（单/多进程共用）
    target_set = _build_target_set(env.card_defs, target_specs)

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
        if n_failed > 0:
            logging.warning("%s/%s simulations failed", n_failed, num_simulations)
        merged_ext = merge_extraction_packets(
            extraction_packets,
            heatmap_config={'n_heatmap_bins': getattr(env, 'n_heatmap_bins', 50), 'max_keep': 200},
        ) if extraction_packets else None
        return BatchResult(results if on_result is None else [], merged_ext)

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
            with MPPool(
                processes=workers,
                initializer=_wk_init,
                initargs=(env, target_specs),
            ) as mp_pool:
                results = [] if on_result is None else None
                extraction_packets = []
                n_failed = 0
                for i, result in enumerate(mp_pool.imap_unordered(_wk_run_single, tasks, chunksize=chunksize)):
                    # 解包 worker 返回值：
                    # - tuple (compact, extraction)：return_compact=True 路径（兼容 on_result 回调）
                    # - 非 tuple：return_compact=False 路径，直接是 extraction_packet
                    if isinstance(result, tuple) and len(result) == 2:
                        compact, ext_pkt = result
                    else:
                        compact = None
                        ext_pkt = result

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
                if n_failed > 0:
                    logging.warning("%s/%s simulations failed", n_failed, num_simulations)
            break
        except Exception as e:
            ename = type(e).__name__
            if workers > 1:
                import time
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
            else:
                n_failed += 1
            if progress_callback:
                progress_callback(idx + 1, num_simulations)
        if n_failed > 0:
            logging.warning("%s/%s simulations failed (single-process fallback)", n_failed, num_simulations)

    # 合并 worker / 单进程提取结果
    merged_extraction = None
    if extraction_packets:
        from gacha_simulator.core.streaming import merge_extraction_packets
        n_heatmap_bins = getattr(env, 'n_heatmap_bins', 50)
        merged_extraction = merge_extraction_packets(
            extraction_packets,
            heatmap_config={'n_heatmap_bins': n_heatmap_bins, 'max_keep': 200},
        )

    raw_results = results if on_result is None else []
    return BatchResult(raw_results, merged_extraction)


class SimulationEnvBuilder:
    @staticmethod
    def from_config_store(config_store) -> SimulationEnv:
        from gacha_simulator.core.pool import Pool, Reward, parse_cost_string
        from gacha_simulator.core.schedule import PoolScheduleManager, PoolSchedule

        DAY = 86400
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
        # P61（Ph6 / ISSUE-001）：永久 Banner（available_until=None）兜底 21 天，
        # end_time = max(有效结束时间)——与现状 (start_day + 21) * DAY 秒等价
        end_time = max(
            (s.available_until if s.available_until is not None
             else (s.available_from or 0) + 21 * DAY)
            for s in schedules
        ) if schedules else 0

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
