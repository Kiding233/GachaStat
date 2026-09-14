"""P79 §8.3 基线对照：等价对照取用 + 「有意变更」表逐行显式断言。

两个目的：

1. **等价对照**（8.3「等价对照」表）：取用 ``scripts/p79_verify.py`` 的输出——
   除 ``fixed_count`` / ``stop_on_target`` 外逐字段与改动前基线一致
2. **有意变更须显式断言新值**（8.3「有意变更」表）：防止将来被误判为回归而「修回去」

分工：``scripts/p79_verify.py`` 跑对照，本文件固化有意变更的期望值，两者不互相替代。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = 'gacha_simulator/config/config.toml'
GOLDEN_DIR = ROOT / 'tests' / 'fixtures' / 'p79_golden'
SEED = 42


# ══════════════════════════════════════════════════════════════════
# 一、等价对照（取用 scripts/p79_verify.py 的输出）
# ══════════════════════════════════════════════════════════════════

def test_equivalence_verify_script_passes():
    """对照脚本退出码 0 = 逐字段等价（白名单外无差异）。"""
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'p79_verify.py')],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding='utf-8', errors='replace',
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '等价对照结果：PASS' in result.stdout


def test_baseline_snapshots_are_pristine():
    """基线快照是**改动前**的冻结产物：仍是版本 2、无 iterations / warnings。"""
    for path in sorted(GOLDEN_DIR.glob('*.json')):
        compact = json.load(open(path, encoding='utf-8'))['compact']
        assert compact['result_version'] == 2, path.name
        assert 'iterations' not in compact, path.name
        assert 'warnings' not in compact, path.name


# ══════════════════════════════════════════════════════════════════
# 二、有意变更（8.3「有意变更」表逐行）
# ══════════════════════════════════════════════════════════════════

@pytest.fixture(scope='module')
def env_and_targets():
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.core.strategy_loader import load_plugin_strategies
    from gacha_simulator.service.batch_simulator import (
        SimulationEnvBuilder, _build_target_set,
    )

    load_plugin_strategies()
    store = load_toml(CONFIG)
    env = SimulationEnvBuilder.from_config_store(store)
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    return store, env, _build_target_set(env.card_defs, specs)


def _run(env_and_targets, strategy_key):
    from gacha_simulator.service.batch_simulator import _run_single

    _, env, target_set = env_and_targets
    env.strategy_key = strategy_key
    env.strategy_params = {}
    return env, _run_single(env, target_set, SEED, env.initial_resources)


def _baseline(strategy_key):
    path = GOLDEN_DIR / (strategy_key.replace('/', '__') + '.json')
    return json.load(open(path, encoding='utf-8'))['compact']


@pytest.mark.parametrize('strategy_key', ['fixed_count', 'stop_on_target'])
def test_intended_change_final_time(env_and_targets, strategy_key):
    """`final_time`：0 天 → env.end_time（5.3）。"""
    env, result = _run(env_and_targets, strategy_key)
    assert _baseline(strategy_key)['final_time'] == 0.0     # 基线确为冻结态
    assert result.final_time == env.end_time


@pytest.mark.parametrize('strategy_key', ['fixed_count', 'stop_on_target'])
def test_intended_change_total_waits(env_and_targets, strategy_key):
    """`total_waits`：从 99900 量级回到真实等待次数（5.3）。"""
    _, result = _run(env_and_targets, strategy_key)
    assert _baseline(strategy_key)['total_waits'] >= 99000
    assert result.total_waits == 168                        # 168 天 / 86400 秒一步
    assert len(result.wait_durations) == result.total_waits


@pytest.mark.parametrize('strategy_key', ['fixed_count', 'stop_on_target'])
def test_intended_change_final_resources(env_and_targets, strategy_key):
    """`final_resources` 增加完整等待期收入；同步变化的还有 total_gained 与
    banner_end_*（1c 实测补登的 4 项）。"""
    _, result = _run(env_and_targets, strategy_key)
    base = _baseline(strategy_key)
    assert result.final_resources['draw_resource'] > \
        base['final_resources']['draw_resource']
    assert result.banner_end_resources, 'banner_end_resources 应为期满快照（非空字典）'
    assert result.banner_end_pity_states
    assert sum(result.total_gained.values()) > 0


def test_intended_change_obtainable_gdr_denominator(env_and_targets):
    """`_obtainable` 系列 4 个 GDR 的分母由 final_time 决定（2.4）。"""
    from gacha_simulator.core.gdr import filter_target_specs_by_obtainable

    store, env, _ = env_and_targets
    specs = {tc.card_id: tc.quantity for tc in store.target_cards}
    assert len(specs) == 6

    at_zero = filter_target_specs_by_obtainable(specs, store, 0.0)
    at_end = filter_target_specs_by_obtainable(specs, store, env.end_time)
    # 改造前 fixed_count 的 final_time = 0 → 分母收窄到 1
    assert len(at_zero) == 1
    assert len(at_end) == 6


def test_intended_change_fingerprint(env_and_targets):
    """`ComparabilityFingerprint.stop_condition` 由硬编码变为条件树摘要，
    `config_hash` 随之变化（阶段 4）。"""
    from gacha_simulator.core.result_store import (
        canonical_stop_condition_summary, compute_config_hash,
    )

    store, env, _ = env_and_targets
    empty = canonical_stop_condition_summary(None)
    named = canonical_stop_condition_summary(
        {'mode': 'any', 'conditions': [{'type': 'time_limit', 'max_time': 1.0}]})
    assert empty == '' and named != empty
    assert named != 'all_pools_end'          # 不再是硬编码的 display_name

    def _hash(summary):
        return compute_config_hash(store.banner.banners, store.pity, [],
                                   milestone_config=store.milestone,
                                   stop_condition_summary=summary)

    assert _hash(empty) != _hash(named)


def test_intended_change_new_result_fields(env_and_targets):
    """`CompactResult.iterations` / `warnings` / `result_version`（阶段 3）。"""
    from gacha_simulator.core.result_types import CompactResult

    fresh = CompactResult()
    assert fresh.iterations == 0
    assert fresh.warnings == []
    assert fresh.result_version == 3

    # 旧快照（版本 2）缺这两个字段 → 键过滤后取默认值
    restored = CompactResult.from_dict({'total_draws': 42, 'result_version': 2})
    assert restored.iterations == 0 and restored.warnings == []

    _, result = _run(env_and_targets, 'smart')
    assert result.iterations > 0
    assert result.warnings == []          # 健康跑法无误报
    assert result.result_version == 3


def test_unchanged_strategies_keep_iterations_from_baseline_order(env_and_targets):
    """等价组的 iterations 与计划 §2.1 的原始实测吻合（563 / 4032）。"""
    _, smart = _run(env_and_targets, 'smart')
    assert smart.iterations == 563
    _, hunting = _run(env_and_targets, 'target_hunting')
    assert hunting.iterations == 4032


def test_golden_dir_is_version_controlled():
    """四件产物须入库（§11.5：否则回滚无参照物）。"""
    assert GOLDEN_DIR.is_dir()
    assert len(list(GOLDEN_DIR.glob('*.json'))) == 9
    assert (ROOT / 'scripts' / 'p79_baseline.py').exists()
    assert (ROOT / 'scripts' / 'p79_verify.py').exists()
    assert os.path.exists(ROOT / 'tests' / 'test_p79_stop_condition_baseline.py')


def test_worst_impact_self_built_condition_shares_end_time_with_env():
    """8.3「等价对照」表第 3 行：`worst_impact` 全流程逐字段不变。

    该行的依据是「硬边界与其自建条件同值」：worst_impact 自建的
    `ConsecutivePoolTargetCondition` 的 `end_time` 已等于它传给 env 的 `end_time`，
    故 `_run_single` 追加的硬边界在该路径上**在收口时刻上与它不可能分歧**，
    行为因此不变。

    局限（如实说明）：§8.3 未为这一行定义基线产物——9 组 golden 快照只覆盖策略键
    （worst_impact 不是策略，走 `from_dict` 路径），故**无法**用改动前快照做逐字段
    对照。本用例固化上述**冗余性前提**并叠加一次全流程跑通，是该行目前可达到的最强
    载体。
    """
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.core.worst_impact import WorstImpactAnalyzer
    from gacha_simulator.service.batch_simulator import (
        SimulationEnvBuilder, _build_target_set, _run_single,
    )

    store = load_toml(CONFIG)
    analyzer = WorstImpactAnalyzer(simulation_results=[], target_specs={}, store=store)
    analyzer._prepare_pool_info()
    cfg = analyzer.prepare_simulation_config(worst_resource=50000.0)

    # 前提：自建条件与 env 共用同一个终点时刻（硬边界因此冗余）
    assert cfg['stop_condition'].end_time == cfg['end_time']

    env = SimulationEnvBuilder.from_dict(cfg)
    # from_dict 路径原样接收调用方传入的条件对象（计划阶段 2 的裁决）
    assert env.stop_condition is cfg['stop_condition']
    assert env.end_time == cfg['end_time']

    target_set = _build_target_set(env.card_defs, cfg['target_specs'])
    result = _run_single(env, target_set, SEED, env.initial_resources)
    assert result is not None
    assert result.final_time <= env.end_time, '追加的硬边界不得使终点外移'
    assert result.warnings == [], result.warnings
