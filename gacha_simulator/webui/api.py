"""GachaApi —— pywebview js_api 桥主类（新 UI 后端）。

前端（Vue3）通过 window.pywebview.api.<method>(...) 调用本类方法。
只依赖 core/service（无 Qt），与旧 gui/ 面板完全平行。

异步模型（已实测验证 pywebview 6.2.1）：
- js_api 方法在桥线程执行，前端拿到 Promise（UI 不卡）
- 耗时任务（模拟/搜索）启动后台线程，后台线程经 evaluate_js 推送进度/完成
- evaluate_js 后台线程安全，可放心调用

数据流：ConfigStore ← load_toml（真相源 config.toml）
       → SimulationEnvBuilder.from_config_store → run_batch_parallel → result_bundle
       → StoredDataset（result_store）存工作区数据集
"""
from __future__ import annotations

import json
import os
import threading
import traceback
from datetime import datetime

from gacha_simulator.core.config_toml import load_toml, save_toml
from gacha_simulator.core.config_store import ConfigStore
from gacha_simulator.core.result_store import StoredDataset, ComparabilityFingerprint
from gacha_simulator.paths import get_config_dir, get_user_data_dir


def _store_from_text(text: str) -> ConfigStore:
    """从 TOML 文本构造 ConfigStore（临时文件中转，不改 core）。"""
    import tempfile
    fd, path = tempfile.mkstemp(suffix='.toml')
    try:
        os.write(fd, text.encode('utf-8'))
        os.close(fd)
        return load_toml(path)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.remove(path)
        except OSError:
            pass


def _jsonable(obj):
    """递归清理 numpy/set 等不可 JSON 序列化类型（pywebview 返回值必须 JSON 兼容）。"""
    import numpy as np
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (set, frozenset)):
        return [_jsonable(v) for v in obj]
    return obj


class GachaApi:
    """暴露给前端的 js_api 桥。"""

    def __init__(self):
        self._window = None          # 由 main_webview 注入（webview window）
        self._config_path = os.path.join(get_config_dir(), 'config.toml')
        self._tasks = {}
        self._task_lock = threading.Lock()
        self._task_seq = 0
        self._dataset_cache = {}     # 前端分析用数据集暂存（register_dataset）
        self._store = ConfigStore()
        self._load_store()

    # ── 窗口注入（main_webview 调用）──
    def attach_window(self, window):
        self._window = window

    def _push_js(self, script: str) -> None:
        """后台线程安全地推送 JS（evaluate_js 已验证线程安全）。"""
        if self._window is not None:
            try:
                self._window.evaluate_js(script)
            except Exception:
                pass

    # ── 配置 ──────────────────────────────────────────────────────────────

    def _load_store(self):
        self._store = ConfigStore()
        if os.path.exists(self._config_path):
            try:
                load_toml(self._config_path, self._store)
            except Exception:
                traceback.print_exc()

    def get_config_path(self) -> str:
        return self._config_path

    def load_config_text(self) -> dict:
        """读取当前 config.toml 文本（前端文本编辑的真相源）。"""
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, encoding='utf-8') as f:
                    return {'ok': True, 'text': f.read()}
            return {'ok': True, 'text': ''}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def _validate_store(self, store: ConfigStore) -> list:
        """保存校验（对齐 config_panel.validate_banners 逻辑，纯 core 实现）。"""
        errors = []
        seen_banner = set()
        has_finite_end = False
        for b in store.banner.banners:
            bid = b.id
            if not bid:
                errors.append('存在空 Banner id')
            elif bid in seen_banner:
                errors.append(f'Banner id 重复: {bid}')
            seen_banner.add(bid)
            if b.available_until is not None:
                has_finite_end = True
            seen_pool = set()
            for p in b.pools:
                pid = p.id
                if not pid:
                    errors.append(f'Banner「{bid or "?"}」存在空 Pool id')
                elif pid in seen_pool:
                    errors.append(f'Banner「{bid}」Pool id 重复: {pid}')
                seen_pool.add(pid)
                if not str(p.cost or '').strip():
                    errors.append(f'Banner「{bid}」Pool「{pid or "?"}」缺少成本(cost)')
        if store.banner.banners and not has_finite_end:
            errors.append('所有 Banner 均为永久（无结束时间），至少需要一个有结束时间的 Banner')
        return errors

    def save_config_text(self, text: str) -> dict:
        """解析校验 + 写回 config.toml（前端「保存」按钮）。"""
        try:
            store = _store_from_text(text)
            errors = self._validate_store(store)
            if errors:
                return {'ok': False, 'errors': errors}
            save_toml(store, self._config_path)
            self._store = store
            return {'ok': True, 'errors': []}
        except Exception as e:
            traceback.print_exc()
            return {'ok': False, 'errors': [str(e)]}

    def reset_default_config(self) -> dict:
        """重置为默认配置（重新解析当前 config.toml）。"""
        try:
            self._load_store()
            with open(self._config_path, encoding='utf-8') as f:
                return {'ok': True, 'text': f.read()}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def import_config_file(self, path: str) -> dict:
        """导入外部 TOML 文件（前端文件选择后传入路径）。"""
        try:
            if not path or not os.path.exists(path):
                return {'ok': False, 'error': '文件不存在'}
            with open(path, encoding='utf-8') as f:
                text = f.read()
            store = _store_from_text(text)
            self._store = store
            return {'ok': True, 'text': text}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def export_config_file(self, path: str) -> dict:
        """导出当前配置到指定路径。"""
        try:
            save_toml(self._store, path)
            return {'ok': True, 'path': path}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # ── 配置元信息（供前端下拉/展示）────────────────────────────────────

    def get_config_meta(self) -> dict:
        """返回当前配置的展示元信息（Banner 数 / 池数 / 目标卡 / 初始资源）。"""
        try:
            store = self._store
            banners = []
            for b in store.banner.banners:
                banners.append({
                    'id': b.id, 'name': b.name, 'enabled': b.enabled,
                    'pools': [p.id for p in b.pools],
                })
            targets = [{'card_id': tc.card_id, 'quantity': tc.quantity} for tc in store.target_cards]
            return {
                'ok': True,
                'banners': banners,
                'targets': targets,
                'initial_resources': dict(store.initial_resources),
                'strategy_key': getattr(store, 'strategy_key', 'smart'),
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def list_gdr_options(self) -> dict:
        """21 种广义出率指标（前端 GDR 下拉）。"""
        from gacha_simulator.core.gdr import get_expanded_gdr_entries
        try:
            entries = get_expanded_gdr_entries(self._store.resource_defs)
            return {
                'ok': True,
                'options': [{'key': k, 'display': d, 'lower_is_better': lb, 'default_threshold': t}
                            for k, d, lb, t in entries],
            }
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def list_strategy_options(self) -> dict:
        """内置策略（前端搜索/模拟策略下拉）。"""
        from gacha_simulator.core.strategy import STRATEGY_REGISTRY
        try:
            opts = [{'key': k, 'display': v.display_name, 'internal': v.internal, 'disabled': bool(v.disabled or v._invalid_state)}
                    for k, v in STRATEGY_REGISTRY.items() if not v.internal]
            return {'ok': True, 'options': opts}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # ── 模拟任务（异步，后台线程 + evaluate_js 推送）────────────────────

    def start_simulation(self, config_text: str, params: dict) -> dict:
        """派发模拟任务。params: {n, seed, w}。返回 task_id，进度/完成推送 JS。"""
        with self._task_lock:
            self._task_seq += 1
            task_id = f'sim{self._task_seq}'
            self._tasks[task_id] = {'id': task_id, 'type': 'sim', 'status': 'queued',
                                    'progress': 0, 'params': params, 'error': None}
        t = threading.Thread(target=self._run_simulation_worker,
                             args=(task_id, config_text, params), daemon=True)
        t.start()
        return {'ok': True, 'task_id': task_id}

    def _run_simulation_worker(self, task_id, config_text, params):
        from gacha_simulator.service.batch_simulator import SimulationEnvBuilder, run_batch_parallel
        task = self._tasks[task_id]
        task['status'] = 'running'
        self._push_task(task_id, 'progress', 0, 0, 0, '正在构建模拟环境…')
        try:
            store = _store_from_text(config_text) if config_text else self._store
            n = int(params.get('n', 1000))
            w = int(params.get('w', 4))
            seed = int(params.get('seed', 42))
            env = SimulationEnvBuilder.from_config_store(store)
            n_heatmap_bins = max(20, min(100, int(n ** 0.5)))
            env.n_heatmap_bins = n_heatmap_bins
            env.return_compact = False
            target_specs = {tc.card_id: tc.quantity for tc in store.target_cards}
            strategy_key = getattr(store, 'strategy_key', 'smart') or 'smart'
            strategy_params = dict(getattr(store, 'strategy_params', {}) or {})

            def _cb(done, total):
                pct = int(done / total * 100) if total else 0
                self._push_task(task_id, 'progress', done, total, pct, None)
                task['progress'] = pct

            batch_result = run_batch_parallel(
                env=env, target_specs=target_specs,
                initial_resources=env.initial_resources,
                num_simulations=n, max_workers=w, seed=seed,
                progress_callback=_cb,
                strategy_key=strategy_key, strategy_params=strategy_params,
            )

            self._push_task(task_id, 'progress', n, n, 100, '正在计算不抽卡基线…')

            no_draw_resource = None
            no_draw_resources = {}
            no_draw_pool_resources = {}
            try:
                nd = run_batch_parallel(
                    env=env, target_specs=target_specs,
                    initial_resources=env.initial_resources,
                    num_simulations=1, max_workers=1, seed=seed,
                    strategy_key='no_draw',
                )
                if nd and nd[0]:
                    no_draw_resources = nd[0].get('final_resources', {})
                    no_draw_resource = no_draw_resources.get('draw_resource', None)
                    no_draw_pool_resources = nd[0].get('banner_end_resources', {})
            except Exception:
                pass

            bundle = self._build_result_bundle(
                batch_result, env, target_specs, n, seed,
                no_draw_resource, no_draw_resources, no_draw_pool_resources, n_heatmap_bins,
            )
            dataset = self._dataset_from_bundle(bundle, store, seed)
            task['status'] = 'done'
            task['dataset'] = dataset
            self._push_js(f"typeof window.__gscTaskDone === 'function' && "
                          f"window.__gscTaskDone({json.dumps({'taskId': task_id, 'ok': True})})")
        except Exception as e:
            traceback.print_exc()
            task['status'] = 'failed'
            task['error'] = str(e)
            self._push_js(f"typeof window.__gscTaskDone === 'function' && "
                          f"window.__gscTaskDone({json.dumps({'taskId': task_id, 'ok': False, 'error': str(e)})})")

    def _build_result_bundle(self, batch_result, env, target_specs, n, seed,
                             no_draw_resource, no_draw_resources, no_draw_pool_resources, n_heatmap_bins):
        """组装 result_bundle（对齐 gacha_panel.SimulationThread 结构）。"""
        import numpy as np
        ext = getattr(batch_result, 'extraction', None)
        if ext is not None:
            heatmap_bins = {
                'achievement': np.linspace(0, 1.05, n_heatmap_bins + 1),
                'resource': np.linspace(0, max(env.initial_resources.get('draw_resource', 0), 1.0) * 2,
                                        n_heatmap_bins + 1),
            }
            gdr_ctx = env.gdr_context.to_dict() if hasattr(env.gdr_context, 'to_dict') else None
            bundle = {
                'aggregate_data': ext.get('aggregates', []),
                'draw_sequences': ext.get('kept_sequences', []),
                'heatmap_data': {
                    'data': {'achievement': ext.get('heatmap_ach', {}), 'resource': ext.get('heatmap_res', {})},
                    'bins': {k: v.tolist() for k, v in heatmap_bins.items()},
                },
                'cumulative_snapshots': ext.get('cumulative_snapshots', {}),
                'transition_flags': ext.get('transition_flags', []),
                'target_ids': list(env.target_ids),
                'ssr_ids': list(env.ssr_ids),
                'gdr_context': gdr_ctx,
                'pool_end_times': dict(env.pool_end_times),
                'target_specs': target_specs,
                'n_results': ext.get('n_results', 0),
                'n_requested': n,
                'no_draw_resource': no_draw_resource,
                'no_draw_resources': no_draw_resources,
                'no_draw_pool_resources': no_draw_pool_resources,
                'seed': seed,
            }
            return bundle
        return {
            'aggregate_data': [], 'draw_sequences': [], 'heatmap_data': {},
            'cumulative_snapshots': {}, 'transition_flags': [],
            'target_ids': list(env.target_ids), 'ssr_ids': list(env.ssr_ids),
            'gdr_context': env.gdr_context.to_dict() if hasattr(env.gdr_context, 'to_dict') else None,
            'pool_end_times': dict(env.pool_end_times), 'target_specs': target_specs,
            'n_results': 0, 'n_requested': n,
            'no_draw_resource': no_draw_resource, 'no_draw_resources': no_draw_resources,
            'no_draw_pool_resources': no_draw_pool_resources, 'seed': seed,
        }

    def _dataset_from_bundle(self, bundle, store, seed):
        """result_bundle → StoredDataset dict（可持久化 + 前端 meta）。"""
        from gacha_simulator.core.result_store import compute_config_hash
        agg = bundle['aggregate_data']
        initial_resources = dict(store.initial_resources) if isinstance(store.initial_resources, dict) else {}
        pool_ids = tuple(p.pool_id for p in store.pools)
        config_hash = compute_config_hash(
            store.banner.banners, getattr(store, 'pity', None),
            getattr(store, 'schedules', []),
            milestone_config=getattr(store, 'milestone', None),
        )
        strategy_name = getattr(store, 'strategy_key', '') or 'unknown'
        now = datetime.now().isoformat()
        fingerprint = ComparabilityFingerprint(
            config_hash=config_hash, strategy_name=strategy_name, strategy_key=strategy_name,
            target_cards=dict(bundle['target_specs']), initial_resources=initial_resources,
            stop_condition='all_pools_end', seed_start=seed,
            seed_end=seed + len(agg) - 1 if agg else seed,
            num_simulations=len(agg), pool_ids=pool_ids, created_at=now,
        )
        ds = StoredDataset(
            name='', fingerprint=fingerprint, created_at=now,
            strategy_name=strategy_name, strategy_key=strategy_name, num_simulations=len(agg),
            aggregate_data=agg, target_specs=dict(bundle['target_specs']),
            target_ids=list(bundle['target_ids']), ssr_ids=list(bundle['ssr_ids']),
            gdr_context=bundle['gdr_context'], pool_end_times=dict(bundle['pool_end_times']),
            draw_sequences=bundle['draw_sequences'], heatmap_data=bundle['heatmap_data'],
            cumulative_snapshots=bundle['cumulative_snapshots'],
            transition_flags=bundle['transition_flags'],
            no_draw_resource=bundle['no_draw_resource'],
            no_draw_resources=dict(bundle['no_draw_resources']),
            no_draw_pool_resources=dict(bundle['no_draw_pool_resources']),
            pool_types={}, initial_resources=initial_resources,
        )
        return ds.to_dict()

    def _push_task(self, task_id, kind, done, total, pct, msg):
        payload = json.dumps({'taskId': task_id, 'done': done, 'total': total, 'pct': pct, 'msg': msg})
        self._push_js(f"typeof window.__gscTaskProgress === 'function' && "
                      f"window.__gscTaskProgress({payload})")

    def get_task_status(self, task_id: str) -> dict:
        t = self._tasks.get(task_id)
        if not t:
            return {'ok': False, 'error': 'task not found'}
        return {'ok': True, 'task_id': task_id, 'status': t['status'],
                'progress': t.get('progress', 0), 'error': t.get('error')}

    # ── 数据集管理（工作区 dataset 持久化）──────────────────────────────

    def _dataset_dir(self):
        return get_user_data_dir('datasets')

    def load_dataset(self, name: str) -> dict:
        try:
            path = os.path.join(self._dataset_dir(), f'{name}.json')
            if not os.path.exists(path):
                return {'ok': False, 'error': 'dataset not found'}
            with open(path, encoding='utf-8') as f:
                return {'ok': True, 'dataset': json.load(f)}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def save_dataset(self, dataset: dict, name: str) -> dict:
        """保存数据集到工作区目录（StoredDataset JSON）。"""
        try:
            ds = StoredDataset.from_dict(_jsonable(dataset))
            ds.name = name
            path = os.path.join(self._dataset_dir(), f'{name}.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(ds.to_dict(), f, ensure_ascii=False)
            return {'ok': True, 'name': name}
        except Exception as e:
            traceback.print_exc()
            return {'ok': False, 'error': str(e)}

    def delete_dataset(self, name: str) -> dict:
        try:
            path = os.path.join(self._dataset_dir(), f'{name}.json')
            if os.path.exists(path):
                os.remove(path)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def list_datasets(self) -> dict:
        try:
            d = self._dataset_dir()
            names = [f[:-5] for f in os.listdir(d) if f.endswith('.json')] if os.path.isdir(d) else []
            metas = []
            for n in sorted(names):
                ds = self.load_dataset(n).get('dataset', {})
                metas.append({
                    'name': n,
                    'strategy': ds.get('strategy_name', ''),
                    'num_simulations': ds.get('num_simulations', 0),
                    'created_at': ds.get('created_at', ''),
                    'target_cards': (ds.get('fingerprint') or {}).get('target_cards', {}),
                })
            return {'ok': True, 'datasets': metas}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # ── 资源监控 ─────────────────────────────────────────────────────────

    def get_resource_usage(self) -> dict:
        try:
            import psutil
            return {
                'ok': True,
                'cpu': psutil.cpu_percent(interval=None),
                'mem': psutil.virtual_memory().percent,
            }
        except ImportError:
            # psutil 未装时返回占位（不阻塞前端）
            return {'ok': True, 'cpu': None, 'mem': None}
        except Exception:
            return {'ok': True, 'cpu': None, 'mem': None}

    # ── 关于 / 插件 ──────────────────────────────────────────────────────

    def get_about_info(self) -> dict:
        from gacha_simulator._version import __version__
        return {
            'ok': True,
            'version': __version__,
            'name': 'GachaStat',
            'tech': 'pywebview + Vue3 + Element Plus + ECharts（P74 换头）',
        }

    def list_plugins(self) -> dict:
        from gacha_simulator.core.strategy import STRATEGY_REGISTRY
        try:
            plugins = [{'key': k, 'name': v.display_name, 'path': v.plugin_path or '',
                        'disabled': bool(v.disabled), 'invalid': bool(v._invalid_state),
                        'internal': v.internal}
                       for k, v in STRATEGY_REGISTRY.items()]
            return {'ok': True, 'plugins': plugins}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def toggle_plugin(self, key: str, disable: bool) -> dict:
        """启用/禁用插件策略（持久化到 TOML [plugins].disabled）。"""
        try:
            from gacha_simulator.core.strategy_loader import disable_plugin_strategy, enable_plugin_strategy
            if disable:
                disable_plugin_strategy(key)
            else:
                enable_plugin_strategy(key)
            # 持久化禁用状态
            import tomllib
            with open(self._config_path, 'rb') as f:
                data = tomllib.load(f)
            plugins = data.get('plugins', {})
            disabled = list(plugins.get('disabled', []))
            if disable and key not in disabled:
                disabled.append(key)
            if not disable and key in disabled:
                disabled.remove(key)
            data['plugins'] = {'disabled': disabled}
            # 重写 TOML（保留原结构——用 toml 库）
            import tomli_w
            with open(self._config_path, 'wb') as f:
                tomli_w.dump(data, f)
            return {'ok': True}
        except Exception as e:
            traceback.print_exc()
            return {'ok': False, 'error': str(e)}

    # ── 统计分析 / 脆弱性 / 最差影响 / 比较 / 搜索（前端分析调用）───────

    def register_dataset(self, dataset: dict) -> dict:
        """暂存数据集（前端分析用）。返回 dataset_id（=创建时间戳）。"""
        if not hasattr(self, '_dataset_cache'):
            self._dataset_cache = {}
        import time as _t
        did = f'ds{int(_t.time() * 1000)}'
        self._dataset_cache[did] = _jsonable(dataset)
        # 限长防泄漏（最多 20 个）
        if len(self._dataset_cache) > 20:
            for k in list(self._dataset_cache)[:-20]:
                self._dataset_cache.pop(k, None)
        return {'ok': True, 'dataset_id': did}

    def _get_dataset(self, dataset_id: str):
        if hasattr(self, '_dataset_cache') and dataset_id in self._dataset_cache:
            return self._dataset_cache[dataset_id]
        # 回退：按名称从磁盘读
        try:
            return self.load_dataset(dataset_id).get('dataset')
        except Exception:
            return None

    def run_analysis(self, dataset_id: str, method: str, params: dict = None) -> dict:
        """统计分析（AnalysisService 14 方法）。"""
        dataset = self._get_dataset(dataset_id)
        if not dataset:
            return {'ok': False, 'error': '数据集不存在', 'sections': []}
        from gacha_simulator.webui.analysis_service import AnalysisService
        svc = AnalysisService(dataset, self._store)
        return svc.run(method, params or {})

    def run_process_analysis(self, dataset_id: str, params: dict = None) -> dict:
        dataset = self._get_dataset(dataset_id)
        if not dataset:
            return {'ok': False, 'error': '数据集不存在', 'sections': []}
        from gacha_simulator.webui.process_service import run_process_analysis
        return run_process_analysis(dataset, self._store, params or {})

    def run_vulnerability(self, dataset_id: str, params: dict = None) -> dict:
        dataset = self._get_dataset(dataset_id)
        if not dataset:
            return {'ok': False, 'error': '数据集不存在', 'sections': []}
        from gacha_simulator.webui.vuln_service import run_vulnerability_analysis
        return run_vulnerability_analysis(dataset, self._store, params or {})

    def generate_retreat_config(self, params: dict) -> dict:
        """脆弱性「生成调整配置」（截断时间线）→ TOML 文本。"""
        from gacha_simulator.webui.vuln_service import generate_retreat_config
        return generate_retreat_config(self._store, params or {})

    def generate_worst_config(self, dataset_id: str, params: dict = None) -> dict:
        """最差影响「生成后续池子配置」→ TOML 文本。"""
        dataset = self._get_dataset(dataset_id)
        if not dataset:
            return {'ok': False, 'error': '数据集不存在'}
        from gacha_simulator.webui.worst_impact_service import generate_worst_config
        return generate_worst_config(dataset, self._store, params or {})

    def analyze_worst_dist(self, dataset_id: str, params: dict = None) -> dict:
        """最差影响「新池子数分布」。"""
        dataset = self._get_dataset(dataset_id)
        if not dataset:
            return {'ok': False, 'error': '数据集不存在', 'sections': []}
        from gacha_simulator.webui.worst_impact_service import analyze_worst_dist
        return analyze_worst_dist(dataset, self._store, params or {})

    def run_comparison(self, dataset_ids: list, params: dict = None) -> dict:
        """比较分析（多数据集 L1-L4）。"""
        datasets = [self._get_dataset(did) for did in (dataset_ids or [])]
        datasets = [d for d in datasets if d]
        if not datasets:
            return {'ok': False, 'error': '无有效数据集', 'sections': []}
        from gacha_simulator.webui.comparison_service import run_comparison
        return run_comparison(datasets, self._store, params or {})

    def start_plan_search(self, config_text: str, params: dict) -> dict:
        """方案搜索（异步后台线程）。params 含 goal/target_specs/success_threshold 等。"""
        with self._task_lock:
            self._task_seq += 1
            task_id = f'search{self._task_seq}'
            self._tasks[task_id] = {'id': task_id, 'type': 'search', 'status': 'queued',
                                    'progress': 0, 'params': params, 'error': None}
        t = threading.Thread(target=self._run_search_worker,
                             args=(task_id, config_text, params), daemon=True)
        t.start()
        return {'ok': True, 'task_id': task_id}

    def _run_search_worker(self, task_id, config_text, params):
        from gacha_simulator.webui.plan_search_service import run_plan_search
        task = self._tasks[task_id]
        task['status'] = 'running'
        try:
            store = _store_from_text(config_text) if config_text else self._store

            def _cb(msg, pct):
                task['progress'] = pct
                self._push_task(task_id, 'progress', pct, 100, pct, msg)

            result = run_plan_search(store, params, progress_callback=_cb)
            task['status'] = 'done'
            # 存内层序列化结果（run_plan_search 返回 {ok, result: {...}}）
            task['result'] = result.get('result') if result.get('ok') else None
            if not result.get('ok'):
                task['error'] = result.get('error', '搜索失败')
            self._push_js(f"typeof window.__gscTaskDone === 'function' && "
                          f"window.__gscTaskDone({json.dumps({'taskId': task_id, 'ok': result.get('ok', False)})})")
        except Exception as e:
            traceback.print_exc()
            task['status'] = 'failed'
            task['error'] = str(e)
            self._push_js(f"typeof window.__gscTaskDone === 'function' && "
                          f"window.__gscTaskDone({json.dumps({'taskId': task_id, 'ok': False, 'error': str(e)})})")

    def get_task_result(self, task_id: str) -> dict:
        """前端拉取任务完成结果（搜索 / 模拟 dataset）。"""
        t = self._tasks.get(task_id)
        if not t:
            return {'ok': False, 'error': 'task not found'}
        out = {'ok': True, 'task_id': task_id, 'status': t['status'], 'type': t['type']}
        if t.get('result') is not None:
            out['result'] = _jsonable(t['result'])
        if t.get('dataset') is not None:
            out['dataset'] = _jsonable(t['dataset'])
        if t.get('error'):
            out['error'] = t['error']
        return out

    # ── 文件对话框 / 工作区保存 ─────────────────────────────────────────

    def pick_file(self, save: bool = False, file_types: list = None) -> dict:
        """pywebview 原生文件对话框。file_types 例：['TOML 配置文件 (*.toml)', '所有文件 (*)']。"""
        import webview
        if self._window is None:
            return {'ok': False, 'error': 'no window'}
        try:
            ft = tuple(file_types or ['所有文件 (*)'])
            if save:
                path = self._window.create_file_dialog(
                    webview.SAVE_DIALOG, save_filename='config.toml', file_types=ft)
            else:
                path = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=ft)
            if not path:
                return {'ok': True, 'path': None}
            p = path[0] if isinstance(path, (list, tuple)) else path
            return {'ok': True, 'path': p}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def save_workspace(self, tree: list) -> dict:
        """保存工作区（树结构 JSON 到用户数据目录 workspace.json）。"""
        try:
            import json as _json
            path = os.path.join(get_user_data_dir('workspace'), 'workspace.json')
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                _json.dump({'app': 'GachaStat workspace', 'tree': tree}, f, ensure_ascii=False, indent=2)
            return {'ok': True, 'path': path}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    def load_workspace(self) -> dict:
        """读取工作区树（workspace.json）。"""
        try:
            import json as _json
            path = os.path.join(get_user_data_dir('workspace'), 'workspace.json')
            if not os.path.exists(path):
                return {'ok': True, 'tree': None}
            with open(path, encoding='utf-8') as f:
                return {'ok': True, 'tree': _json.load(f).get('tree')}
        except Exception as e:
            return {'ok': False, 'error': str(e)}
