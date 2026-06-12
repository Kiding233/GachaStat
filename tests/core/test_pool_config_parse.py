"""pool_config.py 解析函数快速覆盖"""
from gacha_simulator.core.pool_config import (
    parse_distribution_file,
    CardCatalog,
)
from gacha_simulator.core.config_io import save_store_to_directory, load_store_from_directory
from gacha_simulator.core.config_store import ConfigStore, PoolEntry, CardDefEntry


class TestParseDistribution:
    """distribution.txt 解析"""

    def test_basic_distribution(self, tmp_path):
        f = tmp_path / 'dist.txt'
        f.write_text(
            '[ssr_card]: 0.6\n'
            '[sr_card]: 5.1\n'
            '[r_card]: 94.3\n',
            encoding='utf-8',
        )
        result = parse_distribution_file(str(f))
        assert len(result) == 3
        ids = [r.id for r, prob in result]
        assert 'ssr_card' in ids

    def test_empty_distribution(self, tmp_path):
        f = tmp_path / 'dist.txt'
        f.write_text('', encoding='utf-8')
        result = parse_distribution_file(str(f))
        assert result == []


class TestCardCatalog:
    """CardCatalog 操作"""

    def test_get_card_exists(self):
        cat = CardCatalog()
        cat.add_card('card_a', 'SSR', name='角色A', pools=['pool_1'])
        assert cat.get_card('card_a') is not None
        assert cat.get_card('card_a').name == '角色A'

    def test_get_card_missing(self):
        cat = CardCatalog()
        assert cat.get_card('missing') is None

    def test_add_card_overwrite(self):
        """同 card_id 多次添加——最后一次覆盖（不合并 pools）"""
        cat = CardCatalog()
        cat.add_card('card_a', 'SSR', pools=['pool_1'])
        cat.add_card('card_a', 'SSR', pools=['pool_2'])
        card = cat.get_card('card_a')
        assert card.pools == ['pool_2']  # 覆盖语义

    def test_merge_catalogs(self):
        cat1 = CardCatalog()
        cat1.add_card('a', 'SSR', pools=['p1'])
        cat2 = CardCatalog()
        cat2.add_card('b', 'SR', pools=['p2'])
        cat1.merge(cat2)
        assert 'b' in cat1.cards


class TestConfigIOSaveLoad:
    """config_io.py save + load 往返"""

    def test_save_load_roundtrip(self, tmp_path):
        (tmp_path / 'pools').mkdir()
        store = ConfigStore()
        store.resource_defs = {'draw': '抽卡资源'}
        store.pools = [PoolEntry(pool_id='p1', name='池1', start_day=0, end_day=21)]
        store.card_defs = [CardDefEntry(card_id='c1', name='角色', rarity='SSR')]

        save_store_to_directory(str(tmp_path), store)
        # 重新加载
        loaded = load_store_from_directory(str(tmp_path))
        assert loaded.resource_defs.get('draw') == '抽卡资源'
        assert loaded.pools[0].pool_id == 'p1'
        assert loaded.card_defs[0].card_id == 'c1'

    def test_save_creates_directories(self, tmp_path):
        """目录不存在时自动创建"""
        store = ConfigStore()
        save_store_to_directory(str(tmp_path / 'sub' / 'config'), store)
        assert (tmp_path / 'sub' / 'config').is_dir()
