from gacha_simulator.core.retreat_search import (
    RetreatSearchEngine,
    RetreatSearchResult, RetreatSearchPoint,
)


def test_search_result_dataclass():
    result = RetreatSearchResult(
        from_pool_id='pool_2',
        base_resource=5000.0,
        pity_init={'soft_pity': 30},
        search_mode='resource',
        points=[
            RetreatSearchPoint(extra_resource=12000.0, target_specs={'card_a': 1}, success_probability=0.96),
        ],
    )
    assert result.from_pool_id == 'pool_2'
    assert result.base_resource == 5000.0
    assert len(result.points) == 1
    assert result.points[0].extra_resource == 12000.0


def test_engine_init():
    from gacha_simulator.core.config_store import ConfigStore
    store = ConfigStore()
    engine = RetreatSearchEngine(
        config_store=store,
        from_pool_id='pool_1',
        base_resource=5000.0,
        pity_counter_init={'soft_pity': 0},
    )
    assert engine.from_pool_id == 'pool_1'
    assert engine.base_resource == 5000.0


def test_engine_stop():
    from gacha_simulator.core.config_store import ConfigStore
    store = ConfigStore()
    engine = RetreatSearchEngine(
        config_store=store,
        from_pool_id='pool_1',
        base_resource=5000.0,
        pity_counter_init={},
    )
    engine.stop()
    assert engine._should_stop is True


class TestForwardMethod:
    """前进法 search_max_targets_forward 的单元测试（mock 模拟调用）"""

    @staticmethod
    def _make_engine(store, add_order=None, success_threshold=0.95):
        return RetreatSearchEngine(
            config_store=store,
            from_pool_id='pool_1',
            base_resource=0.0,
            pity_counter_init={},
            add_order=add_order or {},
            success_threshold=success_threshold,
        )

    @staticmethod
    def _mock_env():
        """返回一个有 pools 属性的 mock 环境（非空列表，不会被跳过）"""
        class MockPool:
            pass
        return type('MockEnv', (), {'pools': [MockPool()]})()

    def test_forward_empty_candidates(self):
        """空候选集：直接返回空结果"""
        from gacha_simulator.core.config_store import ConfigStore
        store = ConfigStore()
        engine = self._make_engine(store)
        engine._filter_obtainable_targets = lambda specs: specs

        result = engine.search_max_targets_forward({})
        assert result.search_mode == 'forward'
        assert result.points == []

    def test_forward_single_card_succeeds(self, monkeypatch):
        """单张候选卡、模拟成功 → 1 个 point，包含该卡"""
        from gacha_simulator.core.config_store import ConfigStore
        store = ConfigStore()
        engine = self._make_engine(store, add_order={'card_a': 2.0})
        engine._filter_obtainable_targets = lambda specs: specs
        mock_env = self._mock_env()
        monkeypatch.setattr(engine, '_build_truncated_env', lambda base: mock_env)
        monkeypatch.setattr(engine, '_simulate_with_resource', lambda env, specs, res: 0.98)

        result = engine.search_max_targets_forward({'card_a': 1})
        assert result.search_mode == 'forward'
        assert len(result.points) == 1
        assert result.points[0].target_specs == {'card_a': 1}
        assert result.points[0].success_probability == 0.98

    def test_forward_multiple_cards_sorted_by_desire(self, monkeypatch):
        """多张候选卡：按抽取意愿降序排序，高 desire 优先添加"""
        from gacha_simulator.core.config_store import ConfigStore
        store = ConfigStore()
        desire = {'card_a': 1.0, 'card_b': 3.0, 'card_c': 2.0}
        engine = self._make_engine(store, add_order=desire)
        engine._filter_obtainable_targets = lambda specs: specs
        mock_env = self._mock_env()
        monkeypatch.setattr(engine, '_build_truncated_env', lambda base: mock_env)
        monkeypatch.setattr(engine, '_simulate_with_resource', lambda env, specs, res: 0.99)

        result = engine.search_max_targets_forward({'card_a': 1, 'card_b': 1, 'card_c': 1})
        # 按 desire 降序：card_b(3.0) → card_c(2.0) → card_a(1.0)
        assert len(result.points) == 3
        assert list(result.points[0].target_specs.keys()) == ['card_b']
        assert list(result.points[1].target_specs.keys()) == ['card_b', 'card_c']
        assert list(result.points[2].target_specs.keys()) == ['card_b', 'card_c', 'card_a']

    def test_forward_rollback_on_failure(self, monkeypatch):
        """添加某卡后成功率跌破阈值 → 回退到上一个有效方案"""
        from gacha_simulator.core.config_store import ConfigStore
        store = ConfigStore()
        desire = {'card_a': 3.0, 'card_b': 2.0}
        engine = self._make_engine(store, add_order=desire, success_threshold=0.95)
        engine._filter_obtainable_targets = lambda specs: specs
        mock_env = self._mock_env()
        monkeypatch.setattr(engine, '_build_truncated_env', lambda base: mock_env)

        call_count = [0]

        def mock_simulate(env, specs, res):
            call_count[0] += 1
            if call_count[0] == 1:
                return 0.98
            return 0.88

        monkeypatch.setattr(engine, '_simulate_with_resource', mock_simulate)

        result = engine.search_max_targets_forward({'card_a': 1, 'card_b': 1})
        assert len(result.points) == 2
        # 最终有效方案：points 中最后一个 prob >= threshold 的
        valid_points = [p for p in result.points if p.success_probability >= 0.95]
        assert len(valid_points) == 1
        assert valid_points[0].target_specs == {'card_a': 1}

    def test_forward_first_card_fails(self, monkeypatch):
        """第一张候选卡就失败 → 仍保留该卡的方案（最差情况）"""
        from gacha_simulator.core.config_store import ConfigStore
        store = ConfigStore()
        engine = self._make_engine(store, add_order={'card_a': 1.0}, success_threshold=0.95)
        engine._filter_obtainable_targets = lambda specs: specs
        mock_env = self._mock_env()
        monkeypatch.setattr(engine, '_build_truncated_env', lambda base: mock_env)
        monkeypatch.setattr(engine, '_simulate_with_resource', lambda env, specs, res: 0.50)

        result = engine.search_max_targets_forward({'card_a': 1})
        assert len(result.points) == 1
        assert result.points[0].target_specs == {'card_a': 1}
        assert result.points[0].success_probability == 0.50

    def test_forward_stops_on_flag(self, monkeypatch):
        """设置 _should_stop 后中途退出"""
        from gacha_simulator.core.config_store import ConfigStore
        store = ConfigStore()
        desire = {'card_a': 3.0, 'card_b': 2.0, 'card_c': 1.0}
        engine = self._make_engine(store, add_order=desire)
        engine._filter_obtainable_targets = lambda specs: specs
        mock_env = self._mock_env()
        monkeypatch.setattr(engine, '_build_truncated_env', lambda base: mock_env)

        call_count = [0]

        def mock_simulate(env, specs, res):
            call_count[0] += 1
            if call_count[0] == 1:
                engine.stop()
            return 0.98

        monkeypatch.setattr(engine, '_simulate_with_resource', mock_simulate)

        result = engine.search_max_targets_forward(
            {'card_a': 1, 'card_b': 1, 'card_c': 1}
        )
        assert len(result.points) == 1


# ══════════════════════════════════════════════════════════════════
# P79 8.2：退避搜索的两条时间线都不继承用户停止条件
# ══════════════════════════════════════════════════════════════════

_CONF = 'gacha_simulator/config/config.toml'


def _store_with_condition():
    from gacha_simulator.core.config_toml import load_toml

    store = load_toml(_CONF)
    store.stop_condition = {
        'mode': 'any',
        'conditions': [{'type': 'fixed_action_count', 'max_actions': 20}],
    }
    return store


def test_build_env_full_timeline_drops_condition():
    """完整时间线分支（from_pool_id=None）。"""
    store = _store_with_condition()
    env = RetreatSearchEngine(config_store=store)._build_env(50000)
    assert env.stop_condition is None


def test_build_env_truncated_timeline_drops_condition():
    """截断时间线分支（from_pool_id 非空）——两条时间线语义必须一致。"""
    store = _store_with_condition()
    pool_id = store.pools[1].pool_id
    env = RetreatSearchEngine(config_store=store,
                              from_pool_id=pool_id)._build_env(50000)
    assert env.stop_condition is None


def test_search_engine_env_condition_none_but_builder_wires_it():
    """前提断言：同一个 store 经 from_config_store 会带上条件。

    否则上面的「为 None」可能只是接线失效导致的假通过。
    """
    from gacha_simulator.service.batch_simulator import SimulationEnvBuilder

    store = _store_with_condition()
    assert SimulationEnvBuilder.from_config_store(store).stop_condition is not None
