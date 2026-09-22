"""`cli` 路径适配器。

**驱动方式：包装已有入口，不新写驱动**（§3.2 约束 A）。argv 组装 →
`python -m gacha_simulator.cli` 子进程 → 计时挂点 → 归一 `RunResult`。

**不放弃解释器启动与 import 成本**（§3.5）：被测对象就是真实的 CLI 入口，
故墙钟从进程创建起算。这也正是备选方案（进程内 import cli 的模块级符号）被否
的原因——那会丢掉「解释器启动」与「import 成本」两段。

**可采集面**（§3.5「阶段分解到此闭合」）：

| §3.3 段 | 采集点 | 本路径 |
|---|---|---|
| 配置加载 / env 构建 | `cli.py` 的 `main()`（`load_toml` 与 `from_config_store` 前后），经 `--perf-json` 的 `stages` 回传 | 是 |
| 进程池启动 / 模拟 / extractor 合并 | `BatchResult.stage_times`，经同一 JSON 回传 | 是 |
| 分发 | 各路径自身的分发点（`gui-qt` 的面板分发 / `webui` 的 dataset 落地） | **否**（`cli` 无分发器，见 `absent_stages`） |

`分发` 段缺失**属事实而非缺口**，故经 `absent_stages` 声明，报告据此标注
「本路径不产出该段」，**不得留空静默跳过**。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from benchmarks.perf.adapters.base import (
    Adapter,
    AdapterError,
    SingleRun,
    kill_process_tree,
    new_run_id,
    register_adapter,
)
from benchmarks.perf.plan import Plan
from benchmarks.perf.profilers.stage import (
    map_product_stage_times,
    normalize_resources,
    normalize_stages,
)
from benchmarks.perf.record import FuncStat

logger = logging.getLogger(__name__)

__all__ = ['CliAdapter']

#: `--strategy-params` 走 JSON 字符串；空 dict 不必传（省一次解析）。
_EMPTY_PARAMS: Dict[str, Any] = {}


@register_adapter
class CliAdapter(Adapter):
    """`cli` 路径。"""

    name = 'cli'
    is_user_path = True

    #: 三条产品入口都不向 `run_batch_parallel` 传 `on_result`（§3.4 表）。
    collector = False

    #: `cli` 的 `main()` 没有分发器（§3.5 采集通道末表）。
    absent_stages = ('dispatch',)

    def available(self) -> bool:
        """`cli` 无额外依赖——只要本包可导入即可跑。"""
        try:
            import gacha_simulator.cli  # noqa: F401
        except Exception as exc:  # pragma: no cover - 取决于环境
            logger.debug('cli 路径不可用：%s', exc)
            return False
        return True

    # ── 单次驱动 ─────────────────────────────────────────

    def build_argv(self, plan: Plan, *, perf_json: str, output: str) -> List[str]:
        """组装被测 CLI 的 argv。

        独立成方法以便单测断言 argv 形态（不必真的起子进程）。
        """
        argv = [
            sys.executable, '-m', 'gacha_simulator.cli',
            '-c', plan.config_path,
            '-n', str(plan.n),
            '-w', str(plan.workers),
            '-s', str(plan.seed),
            '-o', output,
            '--no-progress',
            '--strategy', plan.strategy_key,
            '--perf-json', perf_json,
        ]
        if plan.chunksize is not None:
            # `cli.py` 目前无 chunksize 参数；有则透传，无则由下方软降级记录。
            argv += ['--chunksize', str(plan.chunksize)]
        if plan.strategy_params and plan.strategy_params != _EMPTY_PARAMS:
            argv += ['--strategy-params', json.dumps(plan.strategy_params, ensure_ascii=False)]
        return argv

    def _build_argv(self, plan: Plan, *, perf_json: str, output: str) -> tuple:
        """实际使用的 argv 与「**确实被剔除**的开关」列表。

        与 `build_argv` 分开，使「理想 argv」与「本版 CLI 可接受的 argv」两件事
        各自可测：`--chunksize` 在 `cli.py` 上不存在，直接传会让 argparse 以退出码
        2 终止**整次测量**，属「测量工具伤及被测对象」，故在此剔除并记软降级。

        `dropped` **只含真的从 argv 里去掉的那些**：本版 CLI 不支持、而本次 plan
        也没打算传的开关（例如 plan 未设 `chunksize` 时的 `--chunksize`），不应
        产生一条「已剔除」的告警——**没有的东西谈不上被剔除**，报出来只会让读报告
        的人去找一个本就不存在的参数。
        """
        argv = self.build_argv(plan, perf_json=perf_json, output=output)
        help_text = self._cli_help_text()
        dropped: List[str] = []
        for flag in _OPTIONAL_FLAGS:
            if flag in help_text or flag not in argv:
                continue
            argv = _drop_flag(argv, flag)
            dropped.append(flag)
        return argv, dropped

    _cli_help_text_cached: Optional[str] = None

    def _cli_help_text(self) -> str:
        """被测 CLI 的 `--help` 文本（一次进程，按类缓存）。"""
        cls = type(self)
        if cls._cli_help_text_cached is None:
            try:
                result = subprocess.run(
                    [sys.executable, '-m', 'gacha_simulator.cli', '--help'],
                    capture_output=True, text=True, encoding='utf-8', timeout=120,
                )
                cls._cli_help_text_cached = f'{result.stdout}\n{result.stderr}'
            except (OSError, subprocess.SubprocessError) as exc:
                logger.debug('取 cli --help 失败：%s', exc)
                cls._cli_help_text_cached = ''
        return cls._cli_help_text_cached

    def _run_once(self, plan: Plan) -> SingleRun:
        with tempfile.TemporaryDirectory(prefix='p83-cli-') as tmp:
            perf_json = os.path.join(tmp, 'perf.json')
            output = os.path.join(tmp, 'cli_out.json')
            argv, dropped = self._build_argv(plan, perf_json=perf_json, output=output)
            warnings: List[str] = []
            for flag in dropped:
                warnings.append(
                    f'被测 CLI 暂不支持 {flag}，已从 argv 剔除——该参数对应的读数本次不可得'
                    '（软降级，不影响模拟本身）'
                )

            started = time.perf_counter()
            returncode, stdout, stderr = self._spawn(argv)
            wall = time.perf_counter() - started

            if returncode != 0:
                tail = (stderr or stdout or '').strip().splitlines()[-6:]
                raise AdapterError(f'cli 路径退出码 {returncode}：' + ' | '.join(tail))

            payload = _read_perf_json(perf_json)
            if payload is None and '--perf-json' not in dropped:
                warnings.append(
                    f'未取到 --perf-json 载荷（{perf_json}）——阶段计时与三元组字节数本次不可得'
                )
            return self._normalize(payload, plan, wall, warnings)

    def _spawn(self, argv: Sequence[str]) -> tuple:
        """起子进程并等待，**带硬超时**。

        超时按规则 3 杀**整棵进程树**（`taskkill /T`）：Windows 上杀父不杀子，
        `multiprocessing` 的 worker 会残留。
        """
        proc = subprocess.Popen(
            list(argv),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        try:
            stdout, stderr = proc.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            kill_process_tree(proc.pid)
            proc.communicate()
            raise AdapterError(
                f'cli 路径超过硬超时 {self.timeout_seconds:.0f}s，已按规则 3 杀掉整棵进程树'
            ) from None
        return proc.returncode, stdout, stderr

    def _normalize(
        self,
        payload: Optional[Mapping[str, Any]],
        plan: Plan,
        wall: float,
        warnings: List[str],
    ) -> SingleRun:
        """把回传载荷归一为 `SingleRun`。"""
        payload = payload or {}
        run_id = payload.get('run_id') or new_run_id()

        # 阶段：cli 自身测的两段 + 产品侧 stage_times 的三段
        raw: Dict[str, float] = dict(payload.get('stages') or {})
        product = map_product_stage_times(payload.get('stage_times'))
        if product:
            raw.update(product)
        stages, stage_warnings = normalize_stages(raw or None, absent_by_design=self.absent_stages)
        warnings.extend(stage_warnings)

        resources, resource_warnings = normalize_resources(
            packet_bytes=payload.get('packet_bytes'),
            subject=plan.subject,
        )
        warnings.extend(resource_warnings)

        functions = _parse_functions(payload.get('functions'), warnings)
        if functions is None and plan.profile_enabled:
            # D7：`--perf-json` 的载荷只有定死的五项，剖析降级的**成因文案装不下**，
            # 被测进程只能把它打到 stderr（那正是 `--perf-json` 之外的通道）。此处记
            # 一条指向 stderr 的说明，使 `RunResult.warnings` 里至少能看出「请求了
            # 剖析但没拿到函数级统计」以及**该去哪儿看成因**——而不是留一个无声的 None。
            warnings.append(
                '已请求剖析（plan.profile_enabled）但未取到函数级统计：'
                '被测进程的 stderr 里有具体成因（§3.8 D7）。'
            )

        return SingleRun(
            wall=wall,
            stages=stages,
            resources=resources,
            functions=functions,
            # `cli.py` 不设 `env.return_compact`，取 `SimulationEnv` 的默认 `True`
            # （与该路径三元组首分量非 `None` 的事实一致）。
            return_compact=True,
            run_id=run_id,
            warnings=warnings,
        )


#: 本适配器会传、但可能尚未在产品 CLI 上落地的可选开关。取不到即剔除。
_OPTIONAL_FLAGS = ('--chunksize', '--perf-json', '--profile-dir', '--profile-skip',
                   '--profile-count')


def _drop_flag(argv: List[str], flag: str) -> List[str]:
    """从 argv 中移除一个 `--flag value` 对（或一个布尔开关）。"""
    if flag not in argv:
        return argv
    index = argv.index(flag)
    tail = argv[index + 1:index + 2]
    take = 2 if tail and not tail[0].startswith('--') else 1
    return argv[:index] + argv[index + take:]


def _read_perf_json(path: str) -> Optional[Mapping[str, Any]]:
    """读 `--perf-json` 的载荷。文件不存在即返回 `None`（非错误）。"""
    target = Path(path)
    if not target.is_file():
        return None
    try:
        with target.open(encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise AdapterError(f'--perf-json 载荷解析失败（{path}）：{exc}') from exc
    if not isinstance(data, Mapping):
        raise AdapterError(f'--perf-json 载荷顶层必须是对象，收到 {type(data).__name__}')
    return data


def _parse_functions(raw: Any, warnings: List[str]) -> Optional[List[FuncStat]]:
    """解析函数级统计。

    接受两种形态：四元序列 `[name, ncalls, tottime, cumtime]` 与键值对象
    （`FuncStat.to_dict()` 的形态）。`None` 或空 → `None`。
    """
    if not raw:
        return None
    stats: List[FuncStat] = []
    for index, item in enumerate(raw):
        try:
            if isinstance(item, Mapping):
                stats.append(FuncStat(
                    name=str(item['name']),
                    ncalls=int(item['ncalls']),
                    tottime=float(item['tottime']),
                    cumtime=float(item['cumtime']),
                ))
            elif isinstance(item, Sequence) and len(item) == 4:
                stats.append(FuncStat(
                    name=str(item[0]), ncalls=int(item[1]),
                    tottime=float(item[2]), cumtime=float(item[3]),
                ))
            else:
                raise ValueError(f'无法识别的元素形态 {item!r}')
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AdapterError(f'functions[{index}] 形态不符：{exc}') from exc
    return stats or None

