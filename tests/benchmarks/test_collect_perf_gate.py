"""T1：`collect_perf` 门控的零默认行为（§3.9 T1 的专条，随 `1e-4` 交付）。

**这一条同时是 §8.2 / §8.3「默认路径零行为变化、可单独 revert」的全部依据**——
若 `collect_perf=False` 时仍做序列化或取阶段计时，那两节的结论立刻失效。

**不起真实进程池**（故可进默认 `pytest -q`，不撞 H9 的 120s）：用 `max_workers=1`
走单进程路径，且 `n=2` 规模。`_packet_size` 用 monkeypatch 计数——只在
`collect_perf=True` 时才应被调用。
"""

import os

import pytest

import gacha_simulator.service.batch_simulator as bs
from gacha_simulator.core.config_toml import load_toml
from gacha_simulator.paths import get_config_dir
from gacha_simulator.service.batch_simulator import BatchResult, SimulationEnvBuilder

N = 2          # 极小规模：本文件只关心门控语义，不关心测量数值
SEED = 7


def _config_path():
    return os.path.join(get_config_dir(), 'config.toml')


@pytest.fixture
def env_and_targets():
    store = load_toml(_config_path())
    env = SimulationEnvBuilder.from_config_store(store)
    targets = {tc.card_id: getattr(tc, 'quantity', 1) for tc in store.target_cards}
    return env, targets


@pytest.fixture
def packet_size_counter(monkeypatch):
    """把 `_packet_size` 换成计数包装器——保留原行为，只数调用次数。"""
    counter = {'calls': 0}
    original = bs._packet_size

    def spy(*args, **kwargs):
        counter['calls'] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(bs, '_packet_size', spy)
    return counter


def _run(env, targets, collect_perf):
    return bs.run_batch_parallel(
        env=env, target_specs=targets, initial_resources=env.initial_resources,
        num_simulations=N, max_workers=1, seed=SEED,
        strategy_key='smart', collect_perf=collect_perf,
    )


class TestSlotsStayEmptyByDefault:
    def test_default_is_off(self):
        """签名默认值必须是 `False`——它是「今日行为」的同义语。"""
        import inspect

        signature = inspect.signature(bs.run_batch_parallel)
        assert signature.parameters['collect_perf'].default is False

    def test_slots_empty(self, env_and_targets):
        env, targets = env_and_targets
        result = _run(env, targets, collect_perf=False)
        assert result.packet_bytes == []
        assert result.stage_times == {}

    def test_no_serialization_at_all(self, env_and_targets, packet_size_counter):
        env, targets = env_and_targets
        _run(env, targets, collect_perf=False)
        assert packet_size_counter['calls'] == 0, '关闭时必须一次 pickle.dumps 都不做'

    def test_simulation_result_unchanged(self, env_and_targets):
        """同种子下开/关不改变模拟结果——测量不得伤及被测对象。"""
        env_a, targets_a = env_and_targets
        off = [r.get('total_draws') for r in _run(env_a, targets_a, collect_perf=False)]
        env_b, targets_b = env_and_targets
        on = [r.get('total_draws') for r in _run(env_b, targets_b, collect_perf=True)]
        assert off == on


class TestSlotsFilledWhenEnabled:
    def test_slots_filled(self, env_and_targets, packet_size_counter):
        env, targets = env_and_targets
        result = _run(env, targets, collect_perf=True)
        assert len(result.packet_bytes) == N
        assert packet_size_counter['calls'] == N
        assert set(result.stage_times) == {'pool_start', 'simulate', 'extract'}

    def test_single_process_pool_start_is_zero(self, env_and_targets):
        """单进程路径无进程池——`pool_start` 记 `0.0`（报告据此标注「本路径无进程池」）。"""
        env, targets = env_and_targets
        result = _run(env, targets, collect_perf=True)
        assert result.stage_times['pool_start'] == 0.0
        assert result.stage_times['simulate'] > 0
        assert result.stage_times['extract'] >= 0

    def test_bytes_are_positive(self, env_and_targets):
        env, targets = env_and_targets
        result = _run(env, targets, collect_perf=True)
        assert all(value > 0 for value in result.packet_bytes)


class TestBatchResultBackwardCompatibility:
    """两槽是**新增**的：旧构造签名必须继续可用，否则所有既有调用点都要改。"""

    def test_legacy_construction(self):
        legacy = BatchResult([1, 2, 3])
        assert legacy.packet_bytes == [] and legacy.stage_times == {}
        assert list(legacy) == [1, 2, 3] and bool(legacy) is True

    def test_slots_are_declared(self):
        """`__slots__` 与 `__init__` 必须同批改——只加槽不改构造签名则新槽永不赋值。"""
        assert 'packet_bytes' in BatchResult.__slots__
        assert 'stage_times' in BatchResult.__slots__
