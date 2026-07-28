"""P60 块 5：is_limited() 等价性 + rarities 解析。"""
import pytest
from gacha_simulator.core.config_store import ConfigStore


def make_store_with_pool(pool_id="pool_1", featured_ids=None):
    """构造最小 ConfigStore——含一个池子的 featured_card_ids。"""
    from gacha_simulator.core.config_store import PoolEntry
    store = ConfigStore()
    pool = PoolEntry(pool_id=pool_id)
    if featured_ids:
        pool.featured_card_ids = list(featured_ids)
    store.pools.append(pool)
    return store


def test_is_limited_true_for_featured_card():
    store = make_store_with_pool(featured_ids=["limited_ssr_1"])
    assert store.is_limited("limited_ssr_1") is True


def test_is_limited_false_for_non_featured_card():
    store = make_store_with_pool(featured_ids=["limited_ssr_1"])
    assert store.is_limited("standard_ssr_1") is False


def test_is_limited_false_when_no_pools():
    store = ConfigStore()
    assert store.is_limited("any_card") is False


def test_is_limited_checks_all_pools():
    """限定卡可能出现在任意池子的 featured_ids 中。"""
    from gacha_simulator.core.config_store import PoolEntry
    store = ConfigStore()
    p1 = PoolEntry(pool_id="p1")
    p1.featured_card_ids = ["card_a"]
    p2 = PoolEntry(pool_id="p2")
    p2.featured_card_ids = ["card_b"]
    store.pools = [p1, p2]
    assert store.is_limited("card_a") is True
    assert store.is_limited("card_b") is True
    assert store.is_limited("card_c") is False


# ── T5：等价性测试 —— 与旧 startswith 比较 ──

@pytest.mark.parametrize("card_id,expected", [
    ("limited_ssr_1", True),       # 在 featured_ids 中 → True（与 startswith 一致）
    ("standard_ssr_1", False),     # 不在 featured_ids 中 → False（与 startswith 一致）
    # 边界：以 "limited" 开头但不在 featured_ids → is_limited() 返回 False（修复误判）
    ("limited_standard", False),   # 旧 startswith 误判为 True，新行为正确为 False
])
def test_is_limited_vs_startswith(card_id, expected):
    """is_limited 基于配置推导，不依赖命名约定。"""
    store = make_store_with_pool(featured_ids=["limited_ssr_1", "limited_ssr_2"])
    assert store.is_limited(card_id) == expected


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
