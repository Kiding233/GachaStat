"""`tests/benchmarks/` 的共用设施。

**为什么要有内存注入的 autouse fixture**：规则 5（可用物理内存阈值）在 `Plan`
**构造期**生效，若不注入，每个构造 `Plan` 的用例都会随本机当前可用内存随机红/绿
——本机在开发期实测可用内存 2.74 GB，而 `workers=4` 的 plan 需要 3.0 GB。规则 5
的拒绝行为另有专测（`test_safety_rules.py`），不该让它污染其余用例。
"""

import os

import pytest

from benchmarks.perf.plan import Plan, injected_memory_query
from benchmarks.perf.record import EnvFingerprint, ResourceStats, RunResult

#: 用例默认假设的可用内存（GB）——远高于任何阈值，使规则 5 不参与判定。
AMPLE_MEMORY_GB = 64.0

#: 本仓的示例配置（`cli` 路径的默认配置）。
DEFAULT_STAGES = {'config_load': 10.0, 'simulate': 900.0, 'extract': 90.0}


@pytest.fixture(autouse=True)
def _ample_memory():
    with injected_memory_query(lambda: AMPLE_MEMORY_GB):
        yield


@pytest.fixture
def fingerprint():
    """一个固定的环境指纹——不用 `capture()`，使比对判据不随本机变化。"""
    return EnvFingerprint(
        cpu='TestCPU', cores=22, os='Windows 11', python='3.12.5',
        code_version='2.4.0', qt_qpa_platform='offscreen',
    )


@pytest.fixture
def make_plan():
    def factory(**overrides):
        base = dict(config_path='config/config.toml', strategy_key='smart',
                    strategy_params={'desired': {}}, n=100, workers=2, seed=42)
        base.update(overrides)
        return Plan(**base)
    return factory


@pytest.fixture
def make_result(make_plan):
    """手工构造一条 `RunResult`——**不依赖真实计时**（§3.9 T1 的要求）。"""
    def factory(fp=None, *, path='cli', subject='simulation', repeats=3, wall=1000.0,
                stages=None, bytes_=1_688_000, return_compact=True,
                not_comparable=False, functions=None, samples_meta=None,
                repeats_downgraded=False, qt_qpa_platform='offscreen'):
        if fp is None:
            fp = EnvFingerprint(cpu='TestCPU', cores=22, os='Windows 11',
                                python='3.12.5', code_version='2.4.0',
                                qt_qpa_platform=qt_qpa_platform)
        plan = make_plan(path=path, subject=subject, repeats=max(1, repeats or 1))
        return RunResult(
            run_id='test-run', timestamp='2026-09-22T00:00:00+00:00',
            path=path, is_user_path=path != 'inline',
            fingerprint=fp, plan=plan,
            repeats=repeats,
            wall_median=wall,
            wall_samples=[wall] * (repeats or 0),
            repeats_downgraded=repeats_downgraded,
            stages=dict(DEFAULT_STAGES if stages is None else stages),
            single=None,
            functions=functions,
            resources=ResourceStats(bytes=bytes_),
            return_compact=return_compact,
            samples_meta=samples_meta,
            not_comparable=not_comparable,
            warnings=[],
        )
    return factory


@pytest.fixture
def record_without_repeats(make_result):
    """模拟「从文件读回、`repeats` 字段缺失」的记录。

    这正是 AUDIT-BREAK-2 指出的断裂场景：字段为 `None` 时与 `3` 比较即抛
    `TypeError`。**必须经 `from_dict` 构造**——`Plan.repeats` 是非 Optional 的，
    直接构造表达不出这个状态。
    """
    def factory(**overrides):
        payload = make_result(**overrides).to_dict()
        payload['repeats'] = None
        return RunResult.from_dict(payload)
    return factory


# ── 真实运行的开关门控（§3.9） ─────────────────────────────
#
# `pytest.mark.skipif` 是**内建标记**，无需在 `pyproject.toml` 注册 markers，
# 故不改配置；也避免这些用例撞 H9 的 120s 超时。

PERF_TESTS_ENV = 'P83_PERF_TESTS'
_TRUTHY = {'1', 'true', 'yes', 'on'}


def perf_tests_enabled() -> bool:
    """是否显式开启了需要真实进程池的用例。"""
    return os.environ.get(PERF_TESTS_ENV, '').strip().lower() in _TRUTHY


requires_real_run = pytest.mark.skipif(
    not perf_tests_enabled(),
    reason=f'需起真实进程池，默认不跑；设 {PERF_TESTS_ENV}=1 启用（§3.9）',
)


# ── 共用的 AST 助手 ────────────────────────────────────────

def call_arguments(source: str, callee: str) -> str:
    """取出 `callee(...)` 的实参文本（按括号配平）。

    供 T3 的「申报值与驱动代码相符」类断言使用——**必须能处理多行调用与嵌套括号**，
    否则会把 `run_batch_parallel(...)` 的实参截断，断言随之失真。
    """
    import re

    match = re.search(re.escape(callee) + r'\s*\(', source)
    if match is None:
        raise AssertionError(f'源码中找不到 {callee}( 的调用')
    start = match.end() - 1
    depth = 0
    for index in range(start, len(source)):
        if source[index] == '(':
            depth += 1
        elif source[index] == ')':
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f'{callee}( 的括号未配平')
