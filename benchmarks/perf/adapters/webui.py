"""`webui` 路径适配器。

**按公开入口驱动，不碰 `webui/api.py` 一行**（§3.10「webui 路径的驱动入口」）：

```
GachaApi() → start_simulation(config_text, params) → 轮询 get_task_status → get_task_result
```

**不走私有链**（`_run_simulation_worker` / `_build_result_bundle`）。理由两条，任一
成立即足以否决：① 绕过公开入口直接调私有方法需要自行复刻 task 记账（`_run_simulation_worker`
首行就是 `task = self._tasks[task_id]`，直接调用必然 `KeyError`）；② 把私有方法当契约用，
与 §3.2 约束 A（适配器只能修复或包装已有入口，不得新写驱动）同时相悖。

**本路径可测的载荷是「粗段」**（§3.10 末段）：总墙钟 + 结果落地（dataset）+ 任务状态
流转。**不是** IPC 三元组、也不是逐段阶段分解——那两者只在私有方法体内，不外流。
故 `stages` 在本路径上**一段都不产出**：六段里 `config_load` / `env_build` / `pool_start`
/ `simulate` / `extract` 全在 `_run_simulation_worker` 的函数体内（`api.py:270` 起），
`dispatch` 对应的「dataset 落地」与任务结束同刻发生、切不出时长。这不是缺口而是一条
**如实标注**：报告里写明「本路径未采集阶段计时」及成因，**不得**填 0 冒充采到了。

**若实施时确需 IPC 三元组或阶段计时：** 那必须**与 P74 一起**在 `api.py` 上做（新增
opt-in 通道），并按 §四 的登记规则补登该文件与回滚边界；**不得**在本文件里绕过公开
入口私自接私有方法。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from benchmarks.perf.adapters.base import (
    Adapter,
    AdapterError,
    SingleRun,
    new_run_id,
    register_adapter,
)
from benchmarks.perf.plan import Plan
from benchmarks.perf.profilers.stage import normalize_resources, normalize_stages

logger = logging.getLogger(__name__)

__all__ = ['WebUiAdapter']

#: 任务状态的终态（`api.py` 的 `get_task_status` 只回这四个取值）。
_TERMINAL_STATUSES = ('done', 'failed')

#: 轮询间隔（秒）。**它同时是 `wall` 的观测误差上界**：完成时刻靠轮询发现，故实测
#: 墙钟最多比真值晚一个间隔。0.05s 对秒级的模拟可忽略；若将来测亚秒级任务，须先
#: 缩小它或改为按状态转移时刻插值。
_POLL_INTERVAL = 0.05

#: 本路径**结构上不产出**的阶段：六段全部。五段在私有方法体内、`dispatch` 与任务
#: 结束同刻（见模块 docstring）。声明出来是为了让报告能区分「本路径不产出」与
#: 「应收未收」——后者才需要排查。
_ABSENT_STAGES = ('config_load', 'env_build', 'pool_start', 'simulate',
                  'extract', 'dispatch')


@register_adapter
class WebUiAdapter(Adapter):
    """`webui` 路径。"""

    name = 'webui'
    is_user_path = True

    #: WebUI 的模拟入口不向 `run_batch_parallel` 传 `on_result`（`api.py:293`）。
    collector = False

    absent_stages = _ABSENT_STAGES

    def available(self) -> bool:
        """本环境能否跑这条路径。

        `webui/api.py` 的顶层只依赖 `core` / `service`（`pywebview` 是方法内按需
        import），故只要本包可导入即可驱动——**不需要 webview 窗口**：`GachaApi`
        的窗口是 `main_webview` 后注入的（`attach_window`），模拟链路本身不用它。
        """
        try:
            import gacha_simulator.webui.api  # noqa: F401
        except Exception as exc:  # pragma: no cover - 取决于环境
            logger.debug('webui 路径不可用：%s', exc)
            return False
        return True

    # ── 单次驱动 ─────────────────────────────────────────

    def _run_once(self, plan: Plan) -> SingleRun:
        api = self._make_api()
        config_text = self._read_config_text(plan)
        warnings: List[str] = []

        started = time.perf_counter()
        task_id = self._dispatch(api, plan, config_text)
        observed = self._await_completion(api, task_id, warnings)
        wall = observed['done_at'] - started

        self._confirm_result_landed(api, task_id)

        warnings.append(
            '本路径未采集阶段计时：六段里前五段全在 `_run_simulation_worker` 的函数体内、'
            '分发段与任务结束同刻，均无回传通道（§3.10）。**不是** collect_perf 未开启。'
        )
        warnings.append(
            '本路径的墙钟含产品侧自动附加的一次 `no_draw` 基线模拟'
            '（`webui/api.py:310`，n=1）——它属这条路径的真实成本，不是测量开销，'
            '但不可与不含该基线路径的读数直接相比。'
        )
        if plan.profile_enabled or plan.grain == 'function':
            # D9 的同类形态：路径降级（本路径不提供注入通道），与 D7 的「剖析故障」
            # 成因不同，故文案须可区分。
            warnings.append(
                '路径降级：本路径不提供剖析注入通道（§3.8 D1 的四字段落在 '
                '`run_batch_parallel` 的调用方，而本路径的调用方在私有方法体内）——'
                'plan 请求了函数级统计但本路径无从采集，functions 为 None。'
            )

        stages, stage_warnings = normalize_stages(None, absent_by_design=self.absent_stages)
        warnings.extend(w for w in stage_warnings if w not in warnings)
        resources, resource_warnings = normalize_resources(subject=plan.subject)
        warnings.extend(w for w in resource_warnings if w not in warnings)

        if observed['queue_to_running'] is not None:
            warnings.append(
                f'本路径可观测的任务状态流转：派发 → running 耗时 '
                f'{observed["queue_to_running"]:.3f}s（进程内的阶段计时不可得，'
                '这个数是本路径能给出的最细的前置开销）。'
            )
        if observed['progress_events']:
            warnings.append(
                f'本路径可观测到 {observed["progress_events"]} 次进度回调——'
                '它是产品侧推送的，与阶段边界不对应，故不作为段计时。'
            )

        return SingleRun(
            wall=wall,
            stages=stages,
            resources=resources,
            # 本路径无从采集函数级统计（成因见上方告警）
            functions=None,
            samples_meta=None,
            # `api.py:283` 在跑主模拟前置 `env.return_compact = False`——与 `gui-qt`
            # 同理，三元组首分量恒为 None。
            return_compact=False,
            run_id=new_run_id(),
            warnings=warnings,
        )

    @staticmethod
    def _make_api():
        """构造 `GachaApi`。**不 attach 窗口**——模拟链路不需要它。"""
        from gacha_simulator.webui.api import GachaApi

        return GachaApi()

    @staticmethod
    def _read_config_text(plan: Plan) -> str:
        """把 `plan.config_path` 的内容读成文本交给 `start_simulation`。

        `start_simulation(config_text, ...)` 在 `config_text` 非空时用它构造 `store`
        （`_store_from_text` → 临时文件中转），为空则回退到 API 自己从磁盘加载的那份
        （`api.py:291`）。**这里必须传文本**：plan 指的是哪份配置，测量就该跑哪份；
        回退会让「配置 X 的读数」实际来自另一份配置，而报告上看不出来。
        """
        from pathlib import Path

        path = Path(plan.config_path)
        try:
            return path.read_text(encoding='utf-8')
        except OSError as exc:
            raise AdapterError(
                f'读不到 plan.config_path（{plan.config_path}）：{exc}——'
                '本路径必须把配置文本经公开入口传进去，不能退回到 API 自载的那份'
                '（那会让读数来自另一份配置）。'
            ) from exc

    @staticmethod
    def _dispatch(api: Any, plan: Plan, config_text: str) -> str:
        """经公开入口派发任务，取回 task_id。"""
        payload = api.start_simulation(config_text, {'n': int(plan.n),
                                                    'seed': int(plan.seed),
                                                    'w': int(plan.workers)})
        if not isinstance(payload, dict) or not payload.get('ok'):
            raise AdapterError(f'start_simulation 未派发成功：{payload!r}')
        task_id = payload.get('task_id')
        if not task_id:
            raise AdapterError(f'start_simulation 未回传 task_id：{payload!r}')
        return str(task_id)

    def _await_completion(self, api: Any, task_id: str,
                          warnings: List[str]) -> Dict[str, Any]:
        """轮询 `get_task_status` 到终态，返回父进程侧读数。

        **完成判据是任务状态 + 结果落地**（不由状态单独作数）：状态为 `done` 只说明
        线程跑完了，`get_task_result` 拿不到 dataset 就仍是失败（同 §3.10 第 1 条对
        「副作用而非信号」的要求）。

        **绝不无超时等待**（§3.10 第 3 条）：超时抛错。**注意本路径的超时杀不掉
        被测对象**——任务是 `daemon=True` 的后台线程（`api.py:268`），跑在**本进程内**，
        没有进程树可回收。这是本路径与 `cli` / `gui-qt` 的结构性差异，故错误信息里
        须写明，免得读的人以为已经清理干净了。
        """
        started = time.perf_counter()
        deadline = started + self.timeout_seconds
        queue_to_running: Optional[float] = None
        progress_events = 0
        last_progress = -1

        while True:
            status = api.get_task_status(task_id)
            if not isinstance(status, dict) or not status.get('ok'):
                raise AdapterError(f'get_task_status 失败：{status!r}')

            state = status.get('status')
            if state == 'running' and queue_to_running is None:
                queue_to_running = time.perf_counter() - started
            progress = status.get('progress')
            if isinstance(progress, int) and progress != last_progress:
                progress_events += 1
                last_progress = progress

            if state in _TERMINAL_STATUSES:
                if state == 'failed':
                    raise AdapterError(
                        f'webui 路径的任务失败：{status.get("error")!r}'
                        '（被测对象是本进程内的后台线程，超时或失败都无法回收进程树）'
                    )
                return {'done_at': time.perf_counter(),
                        'queue_to_running': queue_to_running,
                        'progress_events': progress_events}

            if time.perf_counter() >= deadline:
                raise AdapterError(
                    f'webui 路径超过硬超时 {self.timeout_seconds:.0f}s（§3.10 第 3 条：'
                    '绝不无超时等待）。**本路径无可回收的进程树**：被测对象是本进程内'
                    '`daemon=True` 的后台线程，超时只能放弃这一条读数，线程会自己跑完。'
                )
            time.sleep(_POLL_INTERVAL)

    @staticmethod
    def _confirm_result_landed(api: Any, task_id: str) -> Dict[str, Any]:
        """确认**结果真的落地**：`get_task_result` 必须带回 dataset。

        这是 §3.10 第 1 条在本路径上的落点——「完成」以副作用为准，不以状态字段为准。
        状态说 `done` 而 dataset 缺位，说明落点发生了变化（或本该有结果的任务性质变了），
        此时报错而不是产出一条看起来正常的读数。
        """
        payload = api.get_task_result(task_id)
        if not isinstance(payload, dict) or not payload.get('ok'):
            raise AdapterError(f'get_task_result 失败：{payload!r}')
        dataset = payload.get('dataset')
        if not dataset:
            raise AdapterError(
                f'webui 路径：任务已 done 但结果未落地（get_task_result 无 dataset）——'
                f'完成判据是结果落地这个副作用，不是状态字段。载荷键：{sorted(payload)}'
            )
        return payload

    def _qt_qpa_platform(self, run: SingleRun) -> Optional[str]:
        """§3.11 的三态口径：**空串 = 本路径不适用**。

        `webui` 走 pywebview（WebView2），不经过 Qt 的平台插件——`QT_QPA_PLATFORM`
        对它没有意义。这里**不能返回 `None`**（那是「未记录」，会让本路径的基线永久
        不可比）；空串是一个确定值，使 `webui` 的记录只在同路径内相比。
        """
        return ''
