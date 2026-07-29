"""P60 块 5：rarity_rank 稀有度解析。

is_limited() 方法已被 P65 卡片标签系统（CardDefEntry.tags/list_tags）替代，
对应的 7 个 is_limited 测试随方法一起移除。
"""
from gacha_simulator.core.config_store import ConfigStore


def test_rarity_rank_default():
    store = ConfigStore()
    store._parse_rarities({})
    assert store.rarity_rank["SSR"] == 0
    assert store.rarity_rank["SR"] == 1
    assert store.rarity_rank["R"] == 2


def test_rarity_rank_custom():
    store = ConfigStore()
    store._parse_rarities({"rarities": {"ranks": [["UR", "SSR"], ["SR"], ["R"]]}})
    assert store.rarity_rank["UR"] == 0
    assert store.rarity_rank["SSR"] == 0  # 平级
    assert store.rarity_rank["SR"] == 1
