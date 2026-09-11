"""P55 阶段六+十B：TOML 糖展开 + 旧格式迁移测试"""
import pytest
from gacha_simulator.core.config_toml import (
    _expand_soft_to_deltas,
    _is_legacy_format,
    _migrate_legacy_pity,
    _deltas_to_soft_interval,
    _parse_deltas_value,
    load_toml,
)
from gacha_simulator.core.config_store import ConfigError
import tempfile
import os


# ═══════════════════════════════════════════════════════════════════
# 阶段六：_expand_soft_to_deltas
# ═══════════════════════════════════════════════════════════════════

class TestExpandSoftToDeltas:
    """soft_interval / soft_additive 语法糖 → deltas"""

    def test_soft_interval_linear(self):
        """start=73, end=90 → ((73, 0.0), (17, 5.882353...))"""
        result = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        assert len(result) == 2
        assert result[0] == (73, 0.0)
        assert result[1][0] == 17  # 17 抽
        assert pytest.approx(result[1][1], abs=1e-4) == 100.0 / 17

    def test_soft_interval_start_zero(self):
        """start=0, end=10 → ((0, 0.0), (10, 10.0))"""
        result = _expand_soft_to_deltas('soft_interval', 0, 10, None)
        assert result[0] == (0, 0.0)
        assert result[1][0] == 10

    def test_soft_interval_end_equals_start(self):
        """end <= start → 防御性修正为 start+1"""
        result = _expand_soft_to_deltas('soft_interval', 90, 90, None)
        assert result[0] == (90, 0.0)
        assert result[1][0] == 1  # 修正为 1

    def test_soft_additive(self):
        """start=74, increment=6.0 → ((74, 0.0), (N, 6.0))"""
        result = _expand_soft_to_deltas('soft_additive', 74, None, 6.0)
        assert result[0] == (74, 0.0)
        assert result[1][1] == 6.0
        # 达到 100% 需要的抽数 = ceil(100/6) + 1 = 17
        assert result[1][0] > 0

    def test_soft_additive_zero_increment(self):
        """increment=0.0 → 退化为 1 段（无增长）"""
        result = _expand_soft_to_deltas('soft_additive', 10, None, 0.0)
        assert result[0] == (10, 0.0)
        # increment=0.0 → 不计增长段
        assert result[1][1] == 0.0

    def test_unknown_btype_returns_empty(self):
        """非 soft_interval/soft_additive → 空 tuple"""
        result = _expand_soft_to_deltas('hard', 0, 0, None)
        assert result == ()


# ═══════════════════════════════════════════════════════════════════
# 阶段十B：旧格式迁移
# ═══════════════════════════════════════════════════════════════════

class TestIsLegacyFormat:
    """_is_legacy_format 检测"""

    def test_new_format_not_legacy(self):
        assert _is_legacy_format([
            {'name': 'p1', 'type': 'soft_interval', 'scope': 'ssr', 'start': 74, 'end': 90}
        ]) is False

    def test_old_format_with_start_detected(self):
        assert _is_legacy_format([
            {'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90}
        ]) is True

    def test_old_format_with_func_detected(self):
        assert _is_legacy_format([
            {'name': 'p1', 'type': 'soft', 'func': 'exp'}
        ]) is True

    def test_empty_list_not_legacy(self):
        assert _is_legacy_format([]) is False


class TestMigrateLegacyPity:
    """_migrate_legacy_pity 迁移规则"""

    def test_soft_interval_migration(self):
        """旧 soft → 新 soft_interval"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90}]
        new = _migrate_legacy_pity(old)
        assert new[0]['type'] == 'soft_interval'
        assert new[0]['scope'] == 'ssr'
        assert new[0]['start'] == 74
        assert new[0]['end'] == 90

    def test_hard_migration(self):
        """旧 hard → 新 hard"""
        old = [{'name': 'h1', 'type': 'hard', 'threshold': 180}]
        new = _migrate_legacy_pity(old)
        assert new[0]['type'] == 'hard'
        assert new[0]['threshold'] == 180

    def test_target_distribution_to_featured(self):
        """旧 target → 新 target_featured=true"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90,
                'target': {'limited_ssr': 100}}]
        new = _migrate_legacy_pity(old)
        assert new[0]['target_featured'] is True

    def test_reset_preserved(self):
        """reset 条件保留"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90,
                'reset': 'featured_ssr'}]
        new = _migrate_legacy_pity(old)
        assert new[0]['reset'] == 'featured_ssr'

    def test_counter_init_migrated(self):
        """旧 counter_init → 新 counter_init"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90,
                'counter_init': 30}]
        new = _migrate_legacy_pity(old)
        assert new[0]['counter_init'] == 30

    def test_func_exp_raises_config_error(self):
        """func='exp' → ConfigError"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90,
                'func': 'exp'}]
        with pytest.raises(ConfigError, match='exp'):
            _migrate_legacy_pity(old)

    def test_func_step_raises_config_error(self):
        """func='step' → ConfigError"""
        old = [{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90,
                'func': 'step'}]
        with pytest.raises(ConfigError, match='step'):
            _migrate_legacy_pity(old)


class TestDeltasRoundTrip:
    """deltas ↔ soft_interval 往返可逆"""

    def test_round_trip(self):
        """deltas → soft_interval → 展开 → 等价"""
        deltas = ((73, 0.0), (17, 5.882353))
        result = _deltas_to_soft_interval(deltas)
        assert result is not None
        start, end = result
        expanded = _expand_soft_to_deltas('soft_interval', start, end, None)
        assert expanded[0] == deltas[0]
        assert expanded[1][0] == deltas[1][0]

    def test_non_soft_interval_returns_none(self):
        """首段增量非零 → 无法还原"""
        deltas = ((10, 5.0), (20, 10.0))
        assert _deltas_to_soft_interval(deltas) is None

    def test_single_segment_returns_none(self):
        """非标准双段 → 无法还原"""
        assert _deltas_to_soft_interval(((10, 1.0),)) is None


class TestMigrationRoundTrip:
    """旧格式 → 迁移 → 新格式 → 写回 → 再读 等价性"""

    def test_migration_preserves_semantics(self):
        """迁移后字段语义等价"""
        old = [
            {'name': 'ssr_soft', 'type': 'soft', 'start': 74, 'end': 90,
             'reset': 'any_ssr', 'counter_init': 0},
            {'name': 'ssr_hard', 'type': 'hard', 'threshold': 180},
        ]
        migrated = _migrate_legacy_pity(old)
        # 迁移后条目数一致
        assert len(migrated) == 2
        # soft → soft_interval
        assert migrated[0]['type'] == 'soft_interval'
        assert migrated[0]['scope'] == 'ssr'
        assert migrated[0]['start'] == 74
        assert migrated[0]['end'] == 90
        # hard → hard
        assert migrated[1]['type'] == 'hard'
        assert migrated[1]['threshold'] == 180


class TestParseDeltasValue:
    """_parse_deltas_value 解析"""

    def test_none_returns_none(self):
        assert _parse_deltas_value(None) is None

    def test_tuple_preserved(self):
        result = _parse_deltas_value(((10, 5.0), (20, 10.0)))
        assert result == ((10, 5.0), (20, 10.0))

    def test_list_converted(self):
        result = _parse_deltas_value([[10, 5.0], [20, 10.0]])
        assert result == ((10, 5.0), (20, 10.0))


class TestMigrationMarkRoundTrip:
    """_migrated_from_legacy 标记往返测试"""

    def test_flag_set_on_migration(self):
        """旧格式加载后 _migrated_from_legacy=True"""
        content = """[rarities]
ranks = [["SSR"], ["SR"], ["R"]]

[[pity]]
name = "s1"
type = "soft"
start = 74
end = 90
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml',
                                         delete=False, encoding='utf-8') as f:
            f.write(content)
            f.flush()
            path = f.name

        try:
            store = load_toml(path)
            assert store._migrated_from_legacy is True
            assert len(store.pity.pities) == 1
            assert store.pity.pities[0].btype == 'soft_interval'
        finally:
            os.unlink(path)

    def test_flag_false_on_new_format(self):
        """新格式加载后 _migrated_from_legacy=False"""
        content = """[rarities]
ranks = [["SSR"], ["SR"], ["R"]]

[[pity]]
name = "s1"
type = "soft_interval"
scope = "ssr"
start = 74
end = 90
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml',
                                         delete=False, encoding='utf-8') as f:
            f.write(content)
            f.flush()
            path = f.name

        try:
            store = load_toml(path)
            assert store._migrated_from_legacy is False
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════
# P77：资源生命周期段（[resources.lifecycle]）解析 / 校验 / round-trip
# ═══════════════════════════════════════════════════════════════════

DAY = 86400

# 基础配置：一个有限 Banner（b_lim，10 天）+ 一个永久 Banner（b_perm，无 end_day）
_P77_BASE = '''
[resources.defs]
draw_resource = "抽卡资源"
lim_a = "限时币A"
perm_b = "常驻币B"

[[card]]
card_id = "c1"
name = "卡1"
rarity = "ssr"

[[banner]]
id = "b_lim"
name = "限时池"
start_day = 0
end_day = 10

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "c1"
probability = 100
rarity = "ssr"

[[banner]]
id = "b_perm"
name = "永久池"

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "c1"
probability = 100
rarity = "ssr"
'''

_SECTION = '''
[resources.lifecycle]
enabled = true

[[resources.lifecycle.rules]]
resource_id = "lim_a"
{expire}
[resources.lifecycle.rules.on_expire]
{on_expire}
'''


def _p77_toml(expire='expire_at = 12', on_expire='clear = true', section=_SECTION):
    """拼接基础配置与 lifecycle 段。section 传空串可省略该段。"""
    if not section:
        return _P77_BASE
    return _P77_BASE + section.format(expire=expire, on_expire=on_expire)


def _load_str(content):
    """写临时 TOML 并加载（无论成败均清理临时文件）。"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False,
                                     encoding='utf-8') as f:
        f.write(content)
        path = f.name
    try:
        return load_toml(path)
    finally:
        os.unlink(path)


def _load_into(content, store):
    """加载到已有 store（走 clear() 重置路径）。"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False,
                                     encoding='utf-8') as f:
        f.write(content)
        path = f.name
    try:
        return load_toml(path, store=store)
    finally:
        os.unlink(path)


def _save_and_read(store):
    """保存 store 并返回文件文本（调用方不持有临时文件）。"""
    from gacha_simulator.core.config_toml import save_toml
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False,
                                     encoding='utf-8') as f:
        path = f.name
    try:
        save_toml(store, path)
        with open(path, encoding='utf-8') as fh:
            return fh.read()
    finally:
        os.unlink(path)


class TestResourceLifecycleParsing:
    """解析正确性与天→秒换算。"""

    def test_rule_parsed(self):
        """规则解析：expire_at 与 on_expire 落入 ResourceLifecycle。"""
        store = _load_str(_p77_toml())
        assert store.resource_lifecycle.enabled is True
        assert len(store.resource_lifecycle.rules) == 1
        rule = store.resource_lifecycle.rules[0]
        assert rule.resource_id == 'lim_a'
        assert rule.on_expire == {'clear': True}

    def test_expire_at_days_to_sec(self):
        """expire_at 在天书写、解析边界换算为秒（与 Banner 同口径）。"""
        store = _load_str(_p77_toml(expire='expire_at = 1'))
        assert store.resource_lifecycle.rules[0].expire_at == 1 * DAY

    def test_expire_with_banner(self):
        """expire_with_banner 记录 banner id（到期时刻由运行期解析）。"""
        store = _load_str(_p77_toml(expire='expire_with_banner = "b_lim"'))
        rule = store.resource_lifecycle.rules[0]
        assert rule.expire_with_banner == 'b_lim'
        assert rule.expire_at is None

    def test_convert_on_expire(self):
        """转换形式解析 from/to 正整数。"""
        store = _load_str(_p77_toml(
            on_expire='convert_to = "perm_b"\nfrom = 3\nto = 2'))
        assert store.resource_lifecycle.rules[0].on_expire == {
            'convert_to': 'perm_b', 'from': 3, 'to': 2}

    def test_absent_section_defaults(self):
        """无 [resources.lifecycle] 段时默认启用且无规则（旧配置零影响）。"""
        store = _load_str(_p77_toml(section=''))
        assert store.resource_lifecycle.enabled is True
        assert store.resource_lifecycle.rules == []


class TestResourceLifecycleValidation:
    """五类以上校验均显式抛 ConfigError（不静默漂移）。"""

    def test_validate_mutex(self):
        """expire_at 与 expire_with_banner 同时给出 → ConfigError。"""
        with pytest.raises(ConfigError, match='二选一'):
            _load_str(_p77_toml(
                expire='expire_at = 12\nexpire_with_banner = "b_lim"'))

    def test_validate_neither(self):
        """两者均缺 → ConfigError。"""
        with pytest.raises(ConfigError, match='二选一'):
            _load_str(_p77_toml(expire='# none'))

    def test_validate_banner_ref_missing(self):
        """引用的 banner 不存在 → ConfigError。"""
        with pytest.raises(ConfigError, match='不存在'):
            _load_str(_p77_toml(expire='expire_with_banner = "nope"'))

    def test_validate_permanent_banner(self):
        """指向归一前永久 Banner（无 end_day）→ ConfigError。"""
        with pytest.raises(ConfigError, match='永久 Banner'):
            _load_str(_p77_toml(expire='expire_with_banner = "b_perm"'))

    def test_validate_resource_id_unknown(self):
        """resource_id 未在 [resources.defs] 中定义 → ConfigError。"""
        content = _p77_toml().replace('resource_id = "lim_a"',
                                      'resource_id = "ghost"')
        with pytest.raises(ConfigError, match='未在'):
            _load_str(content)

    def test_validate_dup_resource(self):
        """同一 resource_id 两条规则 → ConfigError。"""
        dup = '\n[[resources.lifecycle.rules]]\nresource_id = "lim_a"\nexpire_at = 5\n' \
              '[resources.lifecycle.rules.on_expire]\nclear = true\n'
        with pytest.raises(ConfigError, match='重复'):
            _load_str(_p77_toml() + dup)

    def test_validate_on_expire_mutex(self):
        """on_expire 同时含 convert_to 与 clear → ConfigError。"""
        with pytest.raises(ConfigError, match='二选一'):
            _load_str(_p77_toml(
                on_expire='convert_to = "perm_b"\nfrom = 1\nto = 1\nclear = true'))

    def test_validate_on_expire_pair(self):
        """有到期时间但缺 on_expire → ConfigError（无保留态，必须成对）。"""
        content = _p77_toml().replace(
            '[resources.lifecycle.rules.on_expire]\nclear = true\n', '')
        with pytest.raises(ConfigError, match='成对'):
            _load_str(content)

    def test_validate_convert_ratio_from_zero(self):
        """from < 1 → ConfigError（正整数约束）。"""
        with pytest.raises(ConfigError, match='不小于 1'):
            _load_str(_p77_toml(
                on_expire='convert_to = "perm_b"\nfrom = 0\nto = 2'))

    def test_validate_convert_target_unknown(self):
        """convert_to 目标未在 [resources.defs] 声明 → ConfigError。

        防 GUI 回填时 findText 失败静默落到 index 0、写回时改写转换目标
        （独立审查发现的配置损坏路径）。
        """
        with pytest.raises(ConfigError, match='未在'):
            _load_str(_p77_toml(
                on_expire='convert_to = "ghost_target"\nfrom = 1\nto = 1'))

    def test_validate_convert_ratio_non_int(self):
        """to 非整数 → ConfigError。"""
        with pytest.raises(ConfigError, match='正整数'):
            _load_str(_p77_toml(
                on_expire='convert_to = "perm_b"\nfrom = 1\nto = 1.5'))

    def test_validate_self_loop(self):
        """convert_to 与 resource_id 相同（自环）→ ConfigError。"""
        with pytest.raises(ConfigError, match='自环'):
            _load_str(_p77_toml(
                on_expire='convert_to = "lim_a"\nfrom = 1\nto = 1'))


class TestResourceLifecycleRoundTrip:
    """写出与再解析的一致性，含条件写键与 clear() 重置。"""

    def test_roundtrip(self):
        """含规则的段往返后字段一致。"""
        store = _load_str(_p77_toml(
            expire='expire_with_banner = "b_lim"',
            on_expire='convert_to = "perm_b"\nfrom = 3\nto = 2'))
        text = _save_and_read(store)
        assert '[resources.lifecycle]' in text

        store2 = _load_str(text)
        r0 = store.resource_lifecycle.rules[0]
        r1 = store2.resource_lifecycle.rules[0]
        assert (r1.resource_id, r1.expire_with_banner, r1.on_expire) == \
            (r0.resource_id, r0.expire_with_banner, r0.on_expire)

    def test_expire_at_roundtrip_days(self):
        """expire_at 写出时换算回天，再解析等值。"""
        store = _load_str(_p77_toml(expire='expire_at = 12'))
        store2 = _load_str(_save_and_read(store))
        assert store2.resource_lifecycle.rules[0].expire_at == 12 * DAY

    def test_empty_section_omitted(self):
        """无规则时保存不写出 lifecycle 段（现有配置零变化）。"""
        store = _load_str(_p77_toml(section=''))
        assert '[resources.lifecycle]' not in _save_and_read(store)

    def test_enabled_false_roundtrip(self):
        """enabled=False 恒写出关闭态，往返不丢失开关。"""
        content = _p77_toml(section='\n[resources.lifecycle]\nenabled = false\n')
        store = _load_str(content)
        assert store.resource_lifecycle.enabled is False
        store2 = _load_str(_save_and_read(store))
        assert store2.resource_lifecycle.enabled is False

    def test_clear_resets_lifecycle(self):
        """clear() 重置规则：复用同一 store 二次加载无该段的 TOML 不残留旧规则。"""
        from gacha_simulator.core.config_store import ConfigStore

        store = ConfigStore()
        store = _load_into(_p77_toml(), store)
        assert len(store.resource_lifecycle.rules) == 1

        # 复用同一 store 再加载无 lifecycle 段的 TOML（load_toml 内部先 clear）
        store = _load_into(_p77_toml(section=''), store)
        assert store.resource_lifecycle.rules == []
        assert store.resource_lifecycle.enabled is True
