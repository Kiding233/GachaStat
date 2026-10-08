"""结果数据管理层——ResultStore、数据集存储、可比性指纹"""
from __future__ import annotations

import json
import hashlib
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.ndarray,)):
            return obj.tolist()
        return super().default(obj)


@dataclass
class ComparabilityFingerprint:
    """模拟完成时自动提取，随 StoredDataset 持久化"""
    config_hash: str           # pools + pity + schedules 的 hash
    strategy_name: str
    target_cards: Dict[str, int]         # {card_id: quantity}
    initial_resources: Dict[str, float]  # {resource_id: amount}
    stop_condition: str                  # 停止条件 display_name
    seed_start: int
    seed_end: int
    num_simulations: int
    pool_ids: Tuple[str, ...]            # 池子 ID 列表（有序）
    created_at: str                      # ISO 时间戳
    strategy_key: str = ''               # P69 ISSUE-002：策略注册 key
    # 2026-10-01（用户裁决）：策略参数参与「策略」维度的可比性判定。
    # 原实现完全不记录它，于是「同一个策略、只改参数」的两次运行被判「所有维度相同」。
    strategy_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'config_hash': self.config_hash,
            'strategy_name': self.strategy_name,
            'strategy_key': self.strategy_key,
            'strategy_params': dict(self.strategy_params),
            'target_cards': dict(self.target_cards),
            'initial_resources': dict(self.initial_resources),
            'stop_condition': self.stop_condition,
            'seed_start': self.seed_start,
            'seed_end': self.seed_end,
            'num_simulations': self.num_simulations,
            'pool_ids': list(self.pool_ids),
            'created_at': self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ComparabilityFingerprint:
        return cls(
            config_hash=d.get('config_hash', ''),
            strategy_name=d.get('strategy_name', ''),
            strategy_key=d.get('strategy_key', ''),
            # 旧数据集没有这个键 -> 取空 dict（降级为「参数未记录」，不误判为不同）
            strategy_params=dict(d.get('strategy_params', {}) or {}),
            target_cards={str(k): int(v) for k, v in d.get('target_cards', {}).items()},
            initial_resources={str(k): float(v) for k, v in d.get('initial_resources', {}).items()},
            stop_condition=d.get('stop_condition', ''),
            seed_start=int(d.get('seed_start', 0)),
            seed_end=int(d.get('seed_end', 0)),
            num_simulations=int(d.get('num_simulations', 0)),
            pool_ids=tuple(d.get('pool_ids', [])),
            created_at=d.get('created_at', ''),
        )


@dataclass
class StoredDataset:
    """一个命名数据集——原始模拟数据 + 元信息 + 分析缓存"""
    name: str
    fingerprint: ComparabilityFingerprint
    created_at: str
    strategy_name: str
    num_simulations: int
    notes: str = ''
    strategy_key: str = ''               # P69 ISSUE-002：策略注册 key

    # 原始模拟数据（dict 格式，来自 result_bundle）
    aggregate_data: List[Dict[str, Any]] = field(default_factory=list)
    target_specs: Dict[str, int] = field(default_factory=dict)
    target_ids: List[str] = field(default_factory=list)
    ssr_ids: List[str] = field(default_factory=list)
    gdr_context: Optional[Dict[str, Any]] = None
    pool_end_times: Dict[str, float] = field(default_factory=dict)
    draw_sequences: List[Any] = field(default_factory=list)
    heatmap_data: Dict[str, Any] = field(default_factory=dict)
    cumulative_snapshots: Dict[str, Any] = field(default_factory=dict)
    transition_flags: List[Any] = field(default_factory=list)
    no_draw_resource: Optional[float] = None
    no_draw_resources: Dict[str, float] = field(default_factory=dict)
    no_draw_pool_resources: Dict[str, Any] = field(default_factory=dict)
    pool_types: Dict[str, str] = field(default_factory=dict)
    initial_resources: Dict[str, float] = field(default_factory=dict)

    # 分析缓存（渐进填充）
    cached_analysis: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'fingerprint': self.fingerprint.to_dict(),
            'created_at': self.created_at,
            'strategy_name': self.strategy_name,
            'strategy_key': self.strategy_key,
            'num_simulations': self.num_simulations,
            'notes': self.notes,
            'aggregate_data': self.aggregate_data,
            'target_specs': self.target_specs,
            'target_ids': self.target_ids,
            'ssr_ids': self.ssr_ids,
            'gdr_context': self.gdr_context,
            'pool_end_times': self.pool_end_times,
            'draw_sequences': self.draw_sequences,
            'heatmap_data': self.heatmap_data,
            'cumulative_snapshots': self.cumulative_snapshots,
            'transition_flags': self.transition_flags,
            'no_draw_resource': self.no_draw_resource,
            'no_draw_resources': self.no_draw_resources,
            'no_draw_pool_resources': self.no_draw_pool_resources,
            'pool_types': self.pool_types,
            'initial_resources': self.initial_resources,
            'cached_analysis': self.cached_analysis,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> StoredDataset:
        return cls(
            name=d.get('name', ''),
            fingerprint=ComparabilityFingerprint.from_dict(d.get('fingerprint', {})),
            created_at=d.get('created_at', ''),
            strategy_name=d.get('strategy_name', ''),
            strategy_key=d.get('strategy_key', ''),
            num_simulations=int(d.get('num_simulations', 0)),
            notes=d.get('notes', ''),
            aggregate_data=d.get('aggregate_data', []),
            target_specs={str(k): int(v) for k, v in d.get('target_specs', {}).items()},
            target_ids=[str(x) for x in d.get('target_ids', [])],
            ssr_ids=[str(x) for x in d.get('ssr_ids', [])],
            gdr_context=d.get('gdr_context'),
            pool_end_times={str(k): float(v) for k, v in d.get('pool_end_times', {}).items()},
            draw_sequences=d.get('draw_sequences', []),
            heatmap_data=d.get('heatmap_data', {}),
            cumulative_snapshots=d.get('cumulative_snapshots', {}),
            transition_flags=d.get('transition_flags', []),
            no_draw_resource=d.get('no_draw_resource'),
            no_draw_resources={str(k): float(v) for k, v in d.get('no_draw_resources', {}).items()},
            no_draw_pool_resources=d.get('no_draw_pool_resources', {}),
            pool_types={str(k): str(v) for k, v in d.get('pool_types', {}).items()},
            initial_resources={str(k): float(v) for k, v in d.get('initial_resources', {}).items()},
            cached_analysis=d.get('cached_analysis', {}),
        )


@dataclass
class ComparabilityDiff:
    """两个数据集的可比性差异"""
    names: Tuple[str, ...]  # 2+ 个数据集名
    dimensions: Dict[str, str] = field(default_factory=dict)
    # 每个维度的值：'same' | 'different: value_a ≠ value_b' | 'varies'

    def only_strategy_differs(self) -> bool:
        """仅策略不同的纯策略比较"""
        diff_dims = {k for k, v in self.dimensions.items() if v != 'same'}
        # 2026-10-01：策略相关的三个字段已合成单一维度 'strategy'（原为
        # strategy_name / strategy_key 两项，P69 ISSUE-812 的限定随之收敛）
        return bool(diff_dims) and diff_dims <= {'strategy'}

    def all_same(self) -> bool:
        """所有维度相同"""
        return all(v == 'same' for v in self.dimensions.values())

    def mode_label(self) -> str:
        if self.all_same():
            return '所有维度相同'
        if self.only_strategy_differs():
            return '策略比较——同一环境下策略的选择差异。同种子可配对比较。'
        # P69 ISSUE-813：同时检查 strategy_name 和 strategy_key 维度
        strategy_diff = self.dimensions.get('strategy', 'same') != 'same'
        config_diff = any(
            self.dimensions.get(d, 'same') != 'same'
            for d in ['config_hash', 'target_cards', 'initial_resources', 'stop_condition', 'pool_ids']
        )
        if strategy_diff and config_diff:
            return '多重差异——策略和配置均不同，结论需谨慎归因'
        if config_diff and not strategy_diff:
            return '不同配置对比——同一策略在不同配置下表现的差异'
        return '部分维度不同，请检查差异矩阵'


class ResultStore:
    """集中式结果数据管理层（core/ 层——无 GUI 依赖）

    所有修改方法（add/remove/rename/set_current/clear）必须在主线程调用。
    回调通过同步 for 循环发射——若在非主线程调用 emit，
    回调函数操作 QWidget 将导致 Qt 线程亲和性崩溃。

    已知限制（Known Limitation）：_emit_datasets_changed/_emit_current_changed
    中的 threading.current_thread() 检查是**被动检测**机制——当回调在非主线程被触发时，
    错误会记录到日志但**不会阻止回调执行**。在当前调用模式下（所有 add()/remove()/rename()
    均从主线程 gui/ 面板发起）安全可控。若未来引入以下场景之一，需将回调发射升级为
    消息队列模式（类比 Qt 的 AutoConnection）：
    - 从后台 worker 线程直接调用 ResultStore.add() 存储模拟结果
    - 从 multiprocessing.Pool 回调中修改 ResultStore
    - 在任何非主线程路径中触发 _emit_datasets_changed() / _emit_current_changed()

    升级路径：当需要跨线程安全时，(a) 在 core/ 层引入 queue.Queue 消息队列——
    修改方法将操作入队，主线程轮询执行；(b) 或在 gui/ 层使用
    QMetaObject.invokeMethod() 将回调调度到主线程事件循环。
    两种方案均保持 core/ 层零 PyQt6 依赖。
    """

    def __init__(self):
        self._datasets: Dict[str, StoredDataset] = {}
        self._current_name: Optional[str] = None
        self._on_datasets_changed: List[Callable[[], None]] = []
        self._on_current_changed: List[Callable[[str], None]] = []

    def connect_datasets_changed(self, callback: Callable[[], None]):
        """注册数据集变更回调（替代 pyqtSignal）"""
        self._on_datasets_changed.append(callback)

    def connect_current_changed(self, callback: Callable[[str], None]):
        """注册当前数据集变更回调（替代 pyqtSignal）"""
        self._on_current_changed.append(callback)

    def _emit_datasets_changed(self):
        if threading.current_thread() is not threading.main_thread():
            logger.error(
                "ResultStore._emit_datasets_changed() called from non-main thread %s. "
                "All ResultStore modifications must be called from the main thread. "
                "Callbacks that operate on QWidget will cause Qt thread-affinity crashes.",
                threading.current_thread().name,
            )
        for cb in self._on_datasets_changed:
            cb()

    def _emit_current_changed(self, name: str):
        if threading.current_thread() is not threading.main_thread():
            logger.error(
                "ResultStore._emit_current_changed('%s') called from non-main thread %s.",
                name, threading.current_thread().name,
            )
        for cb in self._on_current_changed:
            cb(name)

    # —— CRUD ——

    def add(self, name: str, dataset: StoredDataset) -> str:
        """添加数据集。名称冲突时追加后缀。返回实际使用的名称。"""
        actual_name = name
        counter = 1
        while actual_name in self._datasets:
            actual_name = f"{name}_{counter}"
            counter += 1
        dataset.name = actual_name
        self._datasets[actual_name] = dataset
        self._emit_datasets_changed()
        return actual_name

    def remove(self, name: str) -> bool:
        if name not in self._datasets:
            return False
        if self._current_name == name:
            self._current_name = None
            self._emit_current_changed('')
        del self._datasets[name]
        self._emit_datasets_changed()
        return True

    def rename(self, old: str, new: str) -> bool:
        if old not in self._datasets or new in self._datasets:
            return False
        ds = self._datasets.pop(old)
        ds.name = new
        self._datasets[new] = ds
        if self._current_name == old:
            self._current_name = new
            self._emit_current_changed(new)
        self._emit_datasets_changed()
        return True

    def get(self, name: str) -> Optional[StoredDataset]:
        return self._datasets.get(name)

    def list_datasets(self) -> List[Dict[str, Any]]:
        """返回元数据列表（不含原始数据），供表格展示"""
        result = []
        for name, ds in self._datasets.items():
            fp = ds.fingerprint
            result.append({
                'name': name,
                'strategy_name': fp.strategy_name,
                'num_simulations': fp.num_simulations,
                'created_at': fp.created_at,
                'notes': ds.notes,
                'target_cards': fp.target_cards,
                'is_current': name == self._current_name,
            })
        result.sort(key=lambda x: x['created_at'], reverse=True)
        return result

    # —— 当前加载 ——

    def set_current(self, name: Optional[str]):
        if name and name not in self._datasets:
            return
        self._current_name = name
        self._emit_current_changed(name or '')

    @property
    def current(self) -> Optional[StoredDataset]:
        if self._current_name is None:
            return None
        return self._datasets.get(self._current_name)

    @property
    def current_name(self) -> Optional[str]:
        return self._current_name

    # —— 缓存 ——

    def get_cached(self, name: str, cache_key: str) -> Optional[Any]:
        ds = self._datasets.get(name)
        if ds is None:
            return None
        return ds.cached_analysis.get(cache_key)

    def put_cached(self, name: str, cache_key: str, result: Any):
        ds = self._datasets.get(name)
        if ds is not None:
            ds.cached_analysis[cache_key] = result

    # —— 可比性 ——

    def compare_fingerprints(self, names: List[str]) -> Optional[ComparabilityDiff]:
        """比较 2+ 个数据集的可比性指纹。>=3 时返回汇总视图。"""
        if len(names) < 2:
            return None
        fps = []
        for n in names:
            ds = self._datasets.get(n)
            if ds is None:
                return None
            fps.append((n, ds.fingerprint))

        dims = {}
        for i in range(len(fps)):
            for j in range(i + 1, len(fps)):
                name_a, fp_a = fps[i]
                name_b, fp_b = fps[j]
                pair_key = f"{name_a} vs {name_b}"
                dims[pair_key] = {}
                # 2026-10-01（用户裁决）：策略相关字段**合成一个维度** —— 「换策略」与
                # 「改参数」都算这一个维度的改动。原实现分列 strategy_name 与
                # strategy_key 两项，且 strategy_params 完全不参与，于是同一策略只改
                # 参数的两次运行会被判「所有维度相同」。
                _na, _nb = _strategy_label(fp_a), _strategy_label(fp_b)
                if _strategy_signature(fp_a) == _strategy_signature(fp_b):
                    dims[pair_key]['strategy'] = 'same'
                elif _na != _nb:
                    dims[pair_key]['strategy'] = f'different: {_na} ≠ {_nb}'
                else:
                    dims[pair_key]['strategy'] = 'different: 同一策略、参数不同'

                for attr in ['config_hash', 'stop_condition',
                             'seed_start', 'seed_end', 'num_simulations']:
                    a = getattr(fp_a, attr)
                    b = getattr(fp_b, attr)
                    dims[pair_key][attr] = 'same' if a == b else f'different: {a} ≠ {b}'
                for attr in ['target_cards', 'initial_resources', 'pool_ids']:
                    a = getattr(fp_a, attr)
                    b = getattr(fp_b, attr)
                    dims[pair_key][attr] = 'same' if a == b else 'different'
        return ComparabilityDiff(
            names=tuple(names),
            dimensions=dimensions_to_flat(dims, names),
        )

    # —— 持久化 ——

    def save_all(self, path: str):
        data = {
            'version': 1,
            'datasets': {name: ds.to_dict() for name, ds in self._datasets.items()},
            'current': self._current_name,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, cls=_NumpyEncoder)

    def load_all(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for name, ds_dict in data.get('datasets', {}).items():
            self._datasets[name] = StoredDataset.from_dict(ds_dict)
        current = data.get('current')
        if current and current in self._datasets:
            self._current_name = current
        self._emit_datasets_changed()
        if self._current_name:
            self._emit_current_changed(self._current_name)

    def __len__(self) -> int:
        return len(self._datasets)

    def __contains__(self, name: str) -> bool:
        return name in self._datasets


def _strategy_label(fp) -> str:
    """策略维度的可读名（用于差异单元格的展示）。"""
    return getattr(fp, 'strategy_key', '') or getattr(fp, 'strategy_name', '') or '?'


def _strategy_signature(fp) -> str:
    """策略维度的**判定签名**：名称 + 参数。

    参数经 ``json.dumps(sort_keys=True)`` 规范化 —— 它是从 TOML 读来的 dict，
    键序不保证，直接 ``str()`` 比较会把「同一份参数」判成不同。
    """
    params = getattr(fp, 'strategy_params', None) or {}
    if not params:
        return _strategy_label(fp)
    return f"{_strategy_label(fp)}|{json.dumps(params, sort_keys=True, ensure_ascii=False)}"


def dimensions_to_flat(dims: Dict[str, Dict[str, str]], names: List[str]) -> Dict[str, str]:
    """将 pairwise 差异字典展平为单层 {维度: 状态}。>=3 个数据集时合并为汇总。"""
    if len(names) == 2:
        pair_key = f"{names[0]} vs {names[1]}"
        return dims.get(pair_key, {})
    # >=3: 汇总——所有 pair 中任意不同的维度标为 'varies'
    flat = {}
    all_keys = set()
    for pair_dims in dims.values():
        all_keys.update(pair_dims.keys())
    for key in sorted(all_keys):
        statuses = {pair_dims.get(key, 'same') for pair_dims in dims.values()}
        if all(s == 'same' for s in statuses):
            flat[key] = 'same'
        else:
            flat[key] = 'varies'
    return flat


def compute_config_hash(pools_config: List[Any], pity_config: Any,
                        milestone_config: Any = None,
                        stop_condition_summary: Any = None, *,
                        rarity_rank: Any = None,
                        card_defs: Any = None,
                        gain_rules: Any = None,
                        day_overrides: Any = None,
                        sim_start_date: Any = None,
                        resource_lifecycle: Any = None,
                        card_overflow_map: Any = None,
                        card_weights: Any = None) -> str:
    """计算配置的确定性 hash（用于可比性判断）。

    P61（Ph7 / ISSUE-013）：纳入 Banner 级配置。pools_config 现为
    store.banner.banners（List[BannerEntry]）——hash 覆盖 Banner 的
    available_from/until（秒）、enabled、max_draws、lifecycle 规则、内层池
    rewards 分布（featured/rarity/probability）；对旧 List[PoolEntry] 展平
    视图保留兼容分支（仅 hash pool_id/cost，不覆盖 Banner 级字段——时间
    窗口/lifecycle 差异时指纹会误判可比，主路径不得再走该分支）。

    P58（REVIEW-R1-FIX: ISSUE-008）：milestone_config（store.milestone）纳入
    hash——仅 milestone 不同的数据集判「配置: 不同」（否则 only_strategy_differs()
    / mode_label() 误判纯策略比较）。None（调用方未传）→ 不纳入，兼容旧调用方。

    P79：stop_condition_summary（``canonical_stop_condition_summary`` 的产物）纳入
    hash。不纳入时「仅停止条件不同」的两组数据会被判为 same 维度，可比性结论与真实
    情况相反，且 hash 与指纹同时失明。沿用 milestone_config 式的关键字默认 None，
    既有三参 / 四参位置调用保持不变。
    """
    h = hashlib.sha256()

    def _update(seg: str):
        h.update(seg.encode())

    # 池子配置
    for p in sorted(pools_config, key=lambda x: getattr(x, 'id', getattr(x, 'pool_id', ''))):
        if hasattr(p, 'lifecycle'):
            # BannerEntry——Banner 级全字段
            _update(str(getattr(p, 'id', '')))
            _update(str(getattr(p, 'name', '')))
            _update(str(getattr(p, 'enabled', True)))
            _update(str(getattr(p, 'max_draws', None)))
            _update(str(getattr(p, 'available_from', None)))
            _update(str(getattr(p, 'available_until', None)))
            for lp in getattr(p, 'lifecycle', []) or []:
                _update(str(lp))
            for bp in getattr(p, 'pools', []) or []:
                _update(getattr(bp, 'id', ''))
                _update(str(getattr(bp, 'cost', '')))
                _update(str(getattr(bp, 'batch_size', 1)))
                _update(str(getattr(bp, 'max_draws', None)))
                _update(str(getattr(bp, 'excludes_all_pity', False)))
                _update(str(getattr(bp, 'exchange_card_id', None)))
                _update(str(getattr(bp, 'epitomizable_cards', [])))
                for r in getattr(bp, 'rewards', []) or []:
                    _update(str(r))
        else:
            # 旧 PoolEntry 展平视图兼容分支（仅 pool_id/cost）
            _update(getattr(p, 'pool_id', ''))
            _update(str(getattr(p, 'cost', '')))
    # 保底配置
    if pity_config and hasattr(pity_config, 'pities'):
        for pd in sorted(pity_config.pities, key=lambda x: x.name):
            h.update(pd.name.encode())
            h.update(str(getattr(pd, 'params', {})).encode())
    # 2026-10-01 删除 schedules_config 形参：它处理 pool_id / available_from /
    # available_until 三项，而这三项已被上方 BannerEntry 分支覆盖（Banner 是排期的
    # 权威载体），且生产调用从来只传空列表（ConfigStore 没有 schedules 属性，
    # 三处调用都写 getattr(store, 'schedules', [])，其中一处还是 worktree 旧副本）。
    # 一个「恒空的形参」比不写更危险：读代码的人会以为排期已被覆盖。
    # ── 2026-10-01：补入「影响模拟结果、此前一个身份字段都没覆盖」的七项 ──
    #
    # 依据是逐项实测：改动下列任一字段时旧实现的 hash **不变**，于是两份配置哪怕一个
    # 每天进 60 资源、一个每天进 600，compare_fingerprints 也判「所有维度相同」。
    # 覆盖面以「SimulationEnvBuilder.from_config_store 会读的字段」为准（该函数是
    # 配置进入 worker 的唯一通道，它不读的字段不影响模拟结果，故不在此列）。
    #
    # 序列化一律**自己拼规范化字符串**，不用 dataclass 的 repr —— repr 随字段增删
    # 而变，跨版本不稳定，会做出「同一份配置两个 hash」这种事。
    if rarity_rank:
        _update('rarity_rank')
        for _k, _v in sorted(rarity_rank.items()):
            _update(f'{_k}={_v}')
    if card_defs:
        _update('card_defs')
        for _cd in sorted(card_defs, key=lambda x: getattr(x, 'card_id', '')):
            _update(str(getattr(_cd, 'card_id', '')))
            _update(str(getattr(_cd, 'name', '')))
            _update(str(getattr(_cd, 'rarity', '')))
            _update(str(getattr(_cd, 'initial_count', 0)))
            _update(str(sorted(getattr(_cd, 'pools', []) or [])))
            # tags / list_tags（P65）决定卡牌维度，影响分析分组
            _update(str(sorted((getattr(_cd, 'tags', {}) or {}).items())))
            _update(str(sorted((getattr(_cd, 'list_tags', {}) or {}).items())))
    if gain_rules:
        _update('gain_rules')
        for _gr in gain_rules:
            _update(str(getattr(_gr, 'rule_type', '')))
            _update(str(getattr(_gr, 'param', '')))
            _update(str(sorted((getattr(_gr, 'gains', {}) or {}).items())))
    if day_overrides:
        _update('day_overrides')
        for _ov in sorted(day_overrides, key=lambda x: getattr(x, 'day', 0)):
            _update(str(getattr(_ov, 'day', 0)))
            _update(str(sorted((getattr(_ov, 'gains', {}) or {}).items())))
    if sim_start_date:
        # 只影响按日历展开的收入规则（monthly_day / weekly / monthly_week），
        # 但会改变模拟结果，故属配置身份（P85 的 I1/I2）
        _update('sim_start_date')
        _update(str(sim_start_date))
    if resource_lifecycle is not None:
        _update('resource_lifecycle')
        _update(str(getattr(resource_lifecycle, 'enabled', True)))
        for _rl in getattr(resource_lifecycle, 'rules', []) or []:
            _update(str(getattr(_rl, 'resource_id', '')))
            _update(str(getattr(_rl, 'expire_at', None)))
            _update(str(getattr(_rl, 'expire_with_banner', None)))
            _update(str(sorted((getattr(_rl, 'on_expire', {}) or {}).items())))
    if card_overflow_map:
        # 满突溢出的资源返还。它是解析期由 card_defs + rarity_defaults 展开的结果，
        # 故纳入展开结果即可同时覆盖 rarity_defaults
        _update('card_overflow_map')
        for _cid in sorted(card_overflow_map):
            _update(str(_cid))
            for _band in card_overflow_map[_cid] or []:
                _update(str(getattr(_band, 'min', None)))
                _update(str(getattr(_band, 'max', None)))
                _update(str(sorted((getattr(_band, 'resources', {}) or {}).items())))
    if card_weights:
        # 2026-10-07（用户裁决「无条件纳入」）：抽取意愿 / 错失代价 / 单卡价值三维权重。
        #
        # 它们不参与模拟，但**是 GDR 的输入**，因而改变基于 GDR 的一切分析结论
        # （加权满意度、总出卡价值），以及将来消费加权 GDR 的策略。纳入与否**不由
        # 「当前有没有策略消费它」决定**：若按当前事实决定，将来加了消费它的策略时，
        # 历史数据集的配置身份会静默失效（与 2026-10-01 补七项同一类事故）。
        #
        # 不纳入时的失效形态：两份只有权重不同的配置被判「配置完全相同」，而它们的
        # GDR 分析结论不同，且无任何提示。
        _update('card_weights')
        for _cwid in sorted(card_weights):
            _cw = card_weights[_cwid]
            _update(str(_cwid))
            _update(str(getattr(_cw, 'desire_weight', None)))
            _update(str(getattr(_cw, 'miss_cost_weight', None)))
            _update(str(getattr(_cw, 'card_value', None)))
    # 里程碑配置（P58 ISSUE-008——仅 milestone 不同的数据集判「配置: 不同」）
    if milestone_config is not None and hasattr(milestone_config, 'milestones'):
        _update(str(getattr(milestone_config, 'enabled', True)))
        for md in sorted(milestone_config.milestones, key=lambda x: getattr(x, 'name', '')):
            _update(md.name)
            _update(str(md.threshold))
            _update(str(md.repeat))
            _update(str(md.max_triggers))
            _update(str(md.banner))
            _update(str(md.bonus_reward))
            # P78（ISSUE-108）：alternate_rewards/offset 纳入 hash——仅新字段不同的
            # 数据集判「配置: 不同」（否则交替/偏移里程碑与旧形态 hash 相同、误判可比）
            _update(str(md.alternate_rewards))
            _update(str(md.offset))
    # 停止条件（P79）——摘要须含参数值，故由调用方经 canonical_stop_condition_summary
    # 传入（表达式渲染只含 id，不足以承担指纹维度）
    if stop_condition_summary is not None:
        _update(str(stop_condition_summary))
    return h.hexdigest()[:16]


def compute_config_hash_for_store(store, *, stop_condition_summary: Any = None) -> str:
    """从 ConfigStore 计算配置身份哈希 —— **生产代码的唯一入口**。

    为什么要这个包装：底层 `compute_config_hash` 有十来个成分参数，散在各调用点自行
    拼装，**漏传一个就是「静默判为可比」**。本函数被引入的直接原因就是这件事：
    2026-10-01 实测发现有七项影响模拟结果的配置完全没进哈希，而当时两个调用点都
    只传了三个参数。把「该取哪些字段」收在一处，完整性就从「每个调用点都要记得」
    变成一件结构上的事。

    `stop_condition_summary` 仍由调用方传入：它是**导出量**（条件树经
    `canonical_stop_condition_summary` 规范化），不是 store 上的字段。
    """
    _banner_cfg = getattr(store, 'banner', None)
    return compute_config_hash(
        getattr(_banner_cfg, 'banners', None) if _banner_cfg is not None else [],
        getattr(store, 'pity', None),
        getattr(store, 'milestone', None),
        stop_condition_summary,
        rarity_rank=getattr(store, 'rarity_rank', None),
        card_defs=getattr(store, 'card_defs', None),
        gain_rules=getattr(store, 'gain_rules', None),
        day_overrides=getattr(store, 'day_overrides', None),
        sim_start_date=getattr(store, 'sim_start_date', None),
        resource_lifecycle=getattr(store, 'resource_lifecycle', None),
        card_overflow_map=getattr(store, 'card_overflow_map', None),
        card_weights=getattr(store, 'card_weights', None),
    )


def canonical_stop_condition_summary(tree: Optional[Dict[str, Any]]) -> str:
    """条件树 → 可比性指纹用的**规范化摘要**（P79 阶段 4「可比性指纹」段）。

    规范形态定死为 ``json.dumps(tree, sort_keys=True, separators=(',', ':'),
    ensure_ascii=False)``：

    - ``sort_keys`` 消除同一棵树经 TOML 解析与 GUI 重建两条路径的键序差异
    - ``separators`` 去空白，保证跨 Python 版本一致
    - ``tree`` 为 ``None`` 或空表 ``{}``（空树 = 仅引擎硬边界收口）产出固定哨兵
      ``''``，与任何真实树都不同。解析层已把空树规范化为 ``None``，此处再收一道：
      ``store.stop_condition`` 可被程序化赋值为 ``{}``（GUI 编辑期中间态），两者
      运行时行为一致，指纹不应分叉

    只做确定性序列化，**不做语义归一**（不排序条件数组、不去重）——输入树的规范化
    由解析期的空树规范化承担。

    **本函数必须含全部参数值，不能只渲染条件 id**：表达式渲染（stop_condition_expr
    的树 → 表达式方向）只含 id，两组仅阈值不同的停止条件会产出同一表达式串，使
    「可比性指纹」的断言不成立，故摘要不落 ``stop_condition_expr.py``。

    落本模块（与 ``ComparabilityFingerprint`` / ``compute_config_hash`` 同文件）：
    模块已 import json（:4），零新增 import 边，且摘要正是指纹的 ``stop_condition``
    维度。函数体置于 ``compute_config_hash`` 之后，避免上移其行号锚点。
    """
    if not tree:
        return ''
    return json.dumps(tree, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
