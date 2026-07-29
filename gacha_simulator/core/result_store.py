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

    def to_dict(self) -> Dict[str, Any]:
        return {
            'config_hash': self.config_hash,
            'strategy_name': self.strategy_name,
            'strategy_key': self.strategy_key,
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
        # P69 ISSUE-812：差异维度限定在 strategy_name 或 strategy_key 中
        return bool(diff_dims) and diff_dims <= {'strategy_name', 'strategy_key'}

    def all_same(self) -> bool:
        """所有维度相同"""
        return all(v == 'same' for v in self.dimensions.values())

    def mode_label(self) -> str:
        if self.all_same():
            return '所有维度相同'
        if self.only_strategy_differs():
            return '策略比较——同一环境下策略的选择差异。同种子可配对比较。'
        # P69 ISSUE-813：同时检查 strategy_name 和 strategy_key 维度
        strategy_diff = (
            self.dimensions.get('strategy_name', 'same') != 'same'
            or self.dimensions.get('strategy_key', 'same') != 'same'
        )
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
                for attr in ['strategy_name', 'strategy_key', 'config_hash', 'stop_condition',
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
                        schedules_config: List[Any]) -> str:
    """计算配置的确定性 hash（用于可比性判断）"""
    h = hashlib.sha256()
    # 池子配置
    for p in sorted(pools_config, key=lambda x: getattr(x, 'pool_id', '')):
        h.update(getattr(p, 'pool_id', '').encode())
        h.update(str(getattr(p, 'cost', '')).encode())
    # 保底配置
    if pity_config and hasattr(pity_config, 'pities'):
        for pd in sorted(pity_config.pities, key=lambda x: x.name):
            h.update(pd.name.encode())
            h.update(str(getattr(pd, 'params', {})).encode())
    # 排期
    for s in sorted(schedules_config, key=lambda x: getattr(x, 'pool_id', '')):
        h.update(getattr(s, 'pool_id', '').encode())
        h.update(str(getattr(s, 'available_from', 0)).encode())
        h.update(str(getattr(s, 'available_until', 0)).encode())
    return h.hexdigest()[:16]
