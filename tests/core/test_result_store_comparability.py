"""可比性维度的判定测试（重点：策略维度的合成，2026-10-01 用户裁决）。

裁决内容：策略相关字段（策略 key / 显示名 / **参数**）在可比性判定中**合成一个维度**，
「换策略」与「改参数」都算这一个维度的改动。

引入背景：原实现在维度表里分列 ``strategy_name`` 与 ``strategy_key`` 两项，而
``strategy_params`` 完全不参与——于是「同一个策略、只改参数」的两次运行会被判
「所有维度相同」，比较面板据此给出「可直接比较」的结论，而实际跑的不是同一套策略。
"""
from gacha_simulator.core.result_store import (
    ComparabilityFingerprint, ResultStore, StoredDataset,
)


def _fp(**kw):
    base = dict(
        config_hash='h1', strategy_name='按需追卡', strategy_key='smart',
        strategy_params={}, target_cards={'c1': 1}, initial_resources={'draw_resource': 100},
        stop_condition='', seed_start=0, seed_end=9, num_simulations=10,
        pool_ids=('b1.main',), created_at='2026-10-01T00:00:00',
    )
    base.update(kw)
    return ComparabilityFingerprint(**base)


def _store_with(*fps):
    rs = ResultStore()
    for i, fp in enumerate(fps):
        name = f'ds{i}'
        rs.add(name, StoredDataset(name=name, fingerprint=fp,
                                   created_at='2026-10-01T00:00:00',
                                   strategy_name='', num_simulations=10))
    return rs


def test_same_strategy_and_params_is_same():
    d = _store_with(_fp(), _fp()).compare_fingerprints(['ds0', 'ds1'])
    assert d.dimensions['strategy'] == 'same'


def test_param_change_is_a_strategy_dimension_change():
    """只改参数（策略不变）→ 策略维度判不同，且是**唯一**不同的维度。"""
    d = _store_with(_fp(), _fp(strategy_params={'count': 500})).compare_fingerprints(['ds0', 'ds1'])
    assert d.dimensions['strategy'] != 'same'
    assert d.only_strategy_differs(), '改参数应被认作纯策略维度的改动'
    assert d.mode_label().startswith('策略比较')
    assert '参数' in d.dimensions['strategy']


def test_strategy_change_is_a_strategy_dimension_change():
    d = _store_with(_fp(), _fp(strategy_key='no_draw', strategy_name='不抽卡')).compare_fingerprints(['ds0', 'ds1'])
    assert d.dimensions['strategy'] != 'same'
    assert d.only_strategy_differs()


def test_param_only_change_not_judged_all_same():
    """回归：这正是改动前的错误结论（判「所有维度相同」）。"""
    d = _store_with(_fp(), _fp(strategy_params={'a': 1})).compare_fingerprints(['ds0', 'ds1'])
    assert not d.all_same()


def test_param_key_order_does_not_matter():
    """参数字典的键序不影响判定（从 TOML 读来的 dict 键序不保证）。"""
    d = _store_with(_fp(strategy_params={'a': 1, 'b': 2}),
                    _fp(strategy_params={'b': 2, 'a': 1})).compare_fingerprints(['ds0', 'ds1'])
    assert d.dimensions['strategy'] == 'same'


def test_config_change_is_not_a_strategy_change():
    """配置维度与策略维度互相独立：改配置不该被判成策略比较。"""
    d = _store_with(_fp(), _fp(config_hash='h2')).compare_fingerprints(['ds0', 'ds1'])
    assert d.dimensions['strategy'] == 'same'
    assert d.dimensions['config_hash'] != 'same'
    assert not d.only_strategy_differs()
    assert d.mode_label().startswith('不同配置对比')


def test_fingerprint_roundtrip_carries_params():
    """参数随指纹序列化往返（否则存盘再读会丢掉这一维度）。"""
    fp = _fp(strategy_params={'count': 500, '中文键': '值'})
    back = ComparabilityFingerprint.from_dict(fp.to_dict())
    assert back.strategy_params == {'count': 500, '中文键': '值'}


def test_legacy_fingerprint_without_params_loads_empty():
    """旧数据集没有该键 —— 取空 dict，不因缺键而抛。"""
    d = _fp().to_dict()
    d.pop('strategy_params')
    assert ComparabilityFingerprint.from_dict(d).strategy_params == {}
