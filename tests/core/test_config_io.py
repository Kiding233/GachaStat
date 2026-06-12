"""config_io / pool_config / streaming 测试——第二批覆盖率提升"""
from gacha_simulator.core.config_io import load_store_from_directory
from gacha_simulator.core.config_store import ConfigStore
from gacha_simulator.core.pool_config import (
    parse_cards_file, parse_schedule_file,
    CardCatalog,
)


class TestConfigIO:
    """config_io.py 核心加载路径"""

    def test_load_empty_directory(self, tmp_path):
        """空目录——所有 _load_* 静默跳过，不崩溃"""
        store = load_store_from_directory(str(tmp_path))
        assert store is not None
        assert store.pools == []
        assert store.resource_defs == {}

    def test_load_with_resources_file(self, tmp_path):
        """resources.txt 正确解析"""
        (tmp_path / 'resources.txt').write_text(
            'draw_resource | 抽卡资源\n'
            'gem | 宝石\n',
            encoding='utf-8',
        )
        store = load_store_from_directory(str(tmp_path))
        assert 'draw_resource' in store.resource_defs
        assert 'gem' in store.resource_defs

    def test_load_with_cards_file(self, tmp_path):
        """cards.txt 正确解析"""
        (tmp_path / 'cards.txt').write_text(
            'card_a | SSR角色 | SSR | pool_1\n'
            'card_b | SR角色 | SR | pool_1,pool_2\n',
            encoding='utf-8',
        )
        store = load_store_from_directory(str(tmp_path))
        assert len(store.card_defs) == 2
        assert store.card_defs[0].card_id == 'card_a'

    def test_load_with_schedule_file(self, tmp_path):
        """schedule.txt 正确解析"""
        (tmp_path / 'schedule.txt').write_text(
            'pool_1 | 新手池 | 0 | 21 | 160 | draw_resource\n'
            'pool_2 | 标准池 | 21 | 42 | 160 | draw_resource\n',
            encoding='utf-8',
        )
        store = load_store_from_directory(str(tmp_path))
        assert len(store.pools) == 2
        assert store.pools[0].pool_id == 'pool_1'

    def test_load_with_pity_file(self, tmp_path):
        """pity.txt 正确解析——pity: 行前缀"""
        (tmp_path / 'pity.txt').write_text(
            'pity:soft_ssr | soft | 73 | 90 | linear | | any_ssr | pool_1,pool_2\n',
            encoding='utf-8',
        )
        store = load_store_from_directory(str(tmp_path))
        assert len(store.pity.pities) == 1
        assert store.pity.pities[0].name == 'soft_ssr'

    def test_load_with_gains_file(self, tmp_path):
        """gains.txt——[rule_type param] 头部 + 资源行格式"""
        (tmp_path / 'gains.txt').write_text(
            '[every_n_days 1]\n'
            'draw_resource:60\n',
            encoding='utf-8',
        )
        store = load_store_from_directory(str(tmp_path))
        assert len(store.gain_rules) == 1

    def test_load_with_targets_file(self, tmp_path):
        """targets.txt 正确解析"""
        (tmp_path / 'targets.txt').write_text(
            'card_a | 1 | pool_1\n',
            encoding='utf-8',
        )
        store = load_store_from_directory(str(tmp_path))
        assert len(store.target_cards) == 1
        assert store.target_cards[0].card_id == 'card_a'

    def test_load_with_initial_resources(self, tmp_path):
        """initial_resources.txt 正确解析"""
        (tmp_path / 'initial_resources.txt').write_text(
            'draw_resource | 10000\n'
            'gem | 5000\n',
            encoding='utf-8',
        )
        store = load_store_from_directory(str(tmp_path))
        assert store.initial_resources.get('draw_resource') == 10000.0
        assert store.initial_resources.get('gem') == 5000.0

    def test_load_with_weights_file(self, tmp_path):
        """weights.txt 正确解析——存入 card_weights"""
        (tmp_path / 'weights.txt').write_text(
            'card_a | 2.0 | 1.0 | 1.0\n',
            encoding='utf-8',
        )
        store = load_store_from_directory(str(tmp_path))
        assert 'card_a' in store.card_weights

    def test_load_store_none_creates_new(self, tmp_path):
        """store=None → 自动创建 ConfigStore"""
        store = load_store_from_directory(str(tmp_path), None)
        assert isinstance(store, ConfigStore)

    def test_load_store_existing_clears(self, tmp_path):
        """传入已有 store → clear 后重新加载"""
        store = ConfigStore()
        store.pools.append('stale_data')  # 将被 clear
        result = load_store_from_directory(str(tmp_path), store)
        assert result is store
        assert store.pools == []


class TestPoolConfig:
    """pool_config.py 解析函数"""

    def test_parse_cards_file(self, tmp_path):
        f = tmp_path / 'cards.txt'
        f.write_text(
            'card_a | 角色A | SSR | pool_1\n'
            'card_b | 角色B | SR | pool_1,pool_2\n',
            encoding='utf-8',
        )
        catalog = parse_cards_file(str(f))
        assert isinstance(catalog, CardCatalog)
        assert 'card_a' in catalog.cards
        assert catalog.cards['card_a'].rarity == 'SSR'

    def test_parse_cards_file_empty(self, tmp_path):
        f = tmp_path / 'cards.txt'
        f.write_text('', encoding='utf-8')
        catalog = parse_cards_file(str(f))
        assert len(catalog.cards) == 0

    def test_parse_schedule_file(self, tmp_path):
        f = tmp_path / 'schedule.txt'
        f.write_text(
            'pool_1 | 新手池 | 0 | 21 | 160 | draw_resource\n',
            encoding='utf-8',
        )
        pools, catalog = parse_schedule_file(str(f))
        assert len(pools) == 1
        assert pools[0].pool_id == 'pool_1'

    def test_parse_cards_and_schedule_roundtrip(self, tmp_path):
        """parse_schedule_file + parse_cards_file 基础解析"""
        sched = tmp_path / 'schedule.txt'
        sched.write_text(
            'pool_1 | 池1 | 0 | 21 | 160 | draw_resource\n',
            encoding='utf-8',
        )
        cards_f = tmp_path / 'cards.txt'
        cards_f.write_text(
            'card_a | 角色A | SSR | pool_1\n',
            encoding='utf-8',
        )
        pools, sched_catalog = parse_schedule_file(str(sched))
        file_catalog = parse_cards_file(str(cards_f))
        assert len(pools) == 1
        assert 'card_a' in file_catalog.cards


class TestStreaming:
    """streaming.py 核心类"""

    def test_shared_result_collector_creation(self):
        from gacha_simulator.core.streaming import SharedResultCollector
        collector = SharedResultCollector()
        assert collector is not None
        assert collector.n_results == 0

    def test_extract_aggregate(self):
        from gacha_simulator.core.streaming import extract_aggregate
        from gacha_simulator.core.result_types import CompactResult
        r = CompactResult(
            total_draws=10,
            total_consumed={'draw': 1600.0},
            card_counts={'card_a': 1},
            strategy_name='smart',
        )
        agg = extract_aggregate(r)
        assert agg['total_draws'] == 10
        assert agg['card_counts']['card_a'] == 1

    def test_streaming_success_counter(self):
        from gacha_simulator.core.streaming import StreamingSuccessCounter
        counter = StreamingSuccessCounter(
            target_specs={'card_a': 1},
            gdr_key='all_targets',
            gdr_threshold=1.0,
        )
        assert counter is not None
        assert counter.total == 0

    def test_merge_extraction_packets_empty(self):
        from gacha_simulator.core.streaming import merge_extraction_packets
        result = merge_extraction_packets([])
        assert isinstance(result, dict)
