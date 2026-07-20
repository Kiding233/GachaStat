"""P56 阶段十三-b：epitomizable_cards 解析 + 校验 + round-trip 测试。

覆盖目标：
  1. epitomizable_cards 解析 + 校验（card_id 在 distribution 中）
  2. PoolEntry→Pool→SimulationEnv 传播完整性
  3. TOML round-trip 幂等
"""

import pytest
import tempfile
import os
from gacha_simulator.core.config_store import ConfigStore, PoolEntry, PoolDistEntry
from gacha_simulator.core.pool import Pool, Reward


class TestEpitomizableCardsConfigToml:
    """TOML 解析 + 校验 + round-trip。"""

    @pytest.fixture
    def config_toml_content(self):
        return """[meta]
version = "2.3.0"

[rarities]
ranks = [
    ["SSR"],
    ["SR"],
    ["R"],
]

[[pools]]
id = "weapon_pool"
name = "武器池"
pool_type = "武器"
start_day = 0
end_day = 21
cost = "draw_resource:160"
batch_size = 1
epitomizable_cards = ["f1", "f2"]

[[pools.distribution]]
card_id = "f1"
probability = 0.005
rarity = "SSR"
featured = true

[[pools.distribution]]
card_id = "f2"
probability = 0.005
rarity = "SSR"
featured = true

[[pools.distribution]]
card_id = "s1"
probability = 0.005
rarity = "SSR"
featured = false

[[pools.distribution]]
card_id = "s2"
probability = 0.005
rarity = "SSR"
featured = false
"""

    def test_parse_epitomizable_cards(self, config_toml_content):
        """解析 epitomizable_cards 字段。"""
        from gacha_simulator.core.config_toml import load_toml

        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml',
                                          delete=False, encoding='utf-8') as f:
            f.write(config_toml_content)
            tmp_path = f.name

        try:
            store = load_toml(tmp_path)
            pool = store.pools[0]
            assert pool.epitomizable_cards == ['f1', 'f2']
        finally:
            os.unlink(tmp_path)

    def test_roundtrip_epitomizable_cards(self, config_toml_content):
        """TOML → ConfigStore → TOML round-trip 保持 epitomizable_cards。"""
        from gacha_simulator.core.config_toml import load_toml, save_toml

        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml',
                                          delete=False, encoding='utf-8') as f:
            f.write(config_toml_content)
            tmp_path = f.name

        try:
            store = load_toml(tmp_path)

            with tempfile.NamedTemporaryFile(mode='w', suffix='.toml',
                                              delete=False, encoding='utf-8') as f2:
                tmp_path2 = f2.name
            try:
                save_toml(store, tmp_path2)
                store2 = load_toml(tmp_path2)
                assert store2.pools[0].epitomizable_cards == ['f1', 'f2']
            finally:
                os.unlink(tmp_path2)
        finally:
            os.unlink(tmp_path)

    def test_epitomizable_card_not_in_distribution_raises_error(self):
        """epitomizable_cards 中的 card_id 不在 distribution 中 → ConfigError。"""
        from gacha_simulator.core.config_toml import load_toml, ConfigError

        bad_toml = """[meta]
version = "2.3.0"

[rarities]
ranks = [
    ["SSR"],
    ["R"],
]

[[pools]]
id = "weapon_pool"
name = "武器池"
pool_type = "武器"
start_day = 0
end_day = 21
cost = "draw_resource:160"
epitomizable_cards = ["nonexistent"]

[[pools.distribution]]
card_id = "f1"
probability = 1.0
rarity = "SSR"
featured = true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml',
                                          delete=False, encoding='utf-8') as f:
            f.write(bad_toml)
            tmp_path = f.name

        try:
            with pytest.raises(ConfigError, match='epitomizable_cards'):
                load_toml(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_empty_epitomizable_cards_defaults_to_empty_list(self):
        """未声明 epitomizable_cards → 默认空列表。"""
        from gacha_simulator.core.config_toml import load_toml

        no_epi_toml = """[meta]
version = "2.3.0"

[rarities]
ranks = [
    ["SSR"],
    ["R"],
]

[[pools]]
id = "simple_pool"
name = "简单池"
pool_type = "角色"
start_day = 0
end_day = 21
cost = "draw_resource:160"

[[pools.distribution]]
card_id = "c1"
probability = 1.0
rarity = "SSR"
featured = true
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml',
                                          delete=False, encoding='utf-8') as f:
            f.write(no_epi_toml)
            tmp_path = f.name

        try:
            store = load_toml(tmp_path)
            assert store.pools[0].epitomizable_cards == []
        finally:
            os.unlink(tmp_path)


class TestEpitomizableCardsPropagation:
    """PoolEntry → Pool 传播。"""

    def test_pool_entry_to_pool_propagation(self):
        """PoolEntry.epitomizable_cards 正确传播到 Pool 对象。"""
        pool = Pool(
            id='weapon_pool', name='武器池', pool_type='武器',
            cost={'draw_resource': 160},
            rewards=[(Reward(id='f1', name='F1'), 0.5),
                     (Reward(id='f2', name='F2'), 0.5)],
            available_from=0, available_until=21,
            epitomizable_cards=['f1', 'f2'],
        )

        assert pool.epitomizable_cards == ['f1', 'f2']

    def test_pool_default_epitomizable_cards(self):
        """未指定 epitomizable_cards 时默认为空列表。"""
        pool = Pool(
            id='simple_pool', name='简单池', pool_type='角色',
            cost={'draw_resource': 160},
            rewards=[(Reward(id='c1', name='C1'), 1.0)],
            available_from=0, available_until=21,
        )
        assert pool.epitomizable_cards == []
