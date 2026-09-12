"""P79 8.2「`resolve_banner_end_time`」行落点：纯函数单测。

**不经 `load_toml`**：`_normalize_permanent_banners`（config_toml）已在解析期把
永久 banner 的 `available_until` 归一为 `max(finite_ends)`，故经解析入口拿到的
永远是归一后的值，21 天兜底分支无从覆盖。该分支属纯函数自身逻辑，只能手工构造
`available_until=None` 的 `BannerEntry` 直调。
"""

from gacha_simulator.core.config_store import BannerEntry, resolve_banner_end_time

DAY = 86400


def _entry(banner_id, available_from=None, available_until=None):
    return BannerEntry(id=banner_id, name=banner_id,
                       available_from=available_from,
                       available_until=available_until)


def test_empty_input_returns_zero():
    assert resolve_banner_end_time([]) == 0.0
    assert resolve_banner_end_time(None) == 0.0


def test_finite_banners_take_max():
    banners = [_entry('a', available_until=5000.0),
               _entry('b', available_until=9000.0),
               _entry('c', available_until=1000.0)]
    assert resolve_banner_end_time(banners) == 9000.0


def test_permanent_banner_falls_back_to_21_days():
    """21 天兜底分支：`available_until is None` → `available_from + 21 * DAY`。

    该分支是**防御性保留、当前无可达生产路径**——`_normalize_permanent_banners`
    的三个调用点已覆盖全部 ConfigStore 生产路径。若将来有调用方在归一化前读原始
    banner 列表，该分支即生效。
    """
    assert resolve_banner_end_time([_entry('p', available_from=0.0)]) == 21 * DAY
    assert resolve_banner_end_time(
        [_entry('p', available_from=5 * DAY)]) == (5 + 21) * DAY


def test_permanent_banner_without_available_from_uses_zero():
    """`available_from` 也为 None 时按 0 起算（不抛 TypeError）。"""
    assert resolve_banner_end_time([_entry('p')]) == 21 * DAY


def test_mixed_takes_the_larger_of_finite_and_fallback():
    banners = [_entry('perm', available_from=0.0),            # 兜底 21 天
               _entry('finite', available_until=30 * DAY)]    # 有限 30 天
    assert resolve_banner_end_time(banners) == 30 * DAY


def test_duck_typed_pool_schedule_accepted():
    """入参鸭子类型：`from_config_store` 传的是 PoolSchedule（字段同名）。"""
    from gacha_simulator.core.schedule import PoolSchedule

    assert resolve_banner_end_time([PoolSchedule('p', 0.0, 1000.0)]) == 1000.0


def test_config_store_end_time_property_matches_function():
    """`ConfigStore.end_time` 是同一函数的只读派生口（单一实现点）。"""
    from gacha_simulator.core.config_store import ConfigStore

    store = ConfigStore()
    store.banner.banners = [_entry('a', available_until=5000.0),
                            _entry('b', available_until=9000.0)]
    assert store.end_time == resolve_banner_end_time(store.banner.banners) == 9000.0
