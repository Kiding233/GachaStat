"""P55 阶段六+十B：TOML 糖展开 + 旧格式迁移测试"""
import pytest
from gacha_simulator.core.config_toml import (
    _expand_soft_to_deltas,
    _is_legacy_format,
    _migrate_legacy_pity,
    _deltas_to_soft_interval,
    _parse_deltas_value,
    load_toml,
    save_toml,
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


# ══════════════════════════════════════════════════════════════════
# P79 8.1 断言 5：解析期校验不得在 banner 归一化前触发
# ══════════════════════════════════════════════════════════════════

_P79_PERMANENT_TOML = """[meta]
version = "2.4.0"

[resources.defs]
draw_resource = "抽卡资源"

[resources.initial]
draw_resource = 55000

[rarities]
ranks = [
    ["SSR"],
    ["SR"],
    ["R"],
]

[[banner]]
id = "perm"
name = "永久池"
start_day = 0

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "c1"
probability = 1.0
rarity = "SSR"

[[banner]]
id = "finite"
name = "限期池"
start_day = 0
end_day = 168

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "c2"
probability = 1.0
rarity = "SSR"
"""


def _p79_write(tmp_path, text):
    path = tmp_path / 'p79_assert5.toml'
    path.write_text(text, encoding='utf-8')
    return str(path)


def test_p79_assert5_no_false_positives_with_permanent_banner(tmp_path):
    """含永久 banner（available_until=None）的配置：load_warnings 为空。

    若校验函数被排在 _build_banners 之前，store.end_time 走空输入分支返回 0，
    生命周期规则与用户条件会被全量误判——该断言即用来固化调用序纪律。
    """
    store = load_toml(_p79_write(tmp_path, _P79_PERMANENT_TOML))

    assert store.load_warnings == [], store.load_warnings
    # 归一化后：永久 banner 的 available_until 被置为 max(有限 banner 的 available_until)
    assert store.end_time != 0
    assert store.end_time == 168 * 86400
    assert store.end_time == max(b.available_until for b in store.banner.banners)


def test_p79_assert5_validation_actually_ran(tmp_path):
    """在同配置上加一条真死规则：必须恰好命中该条——证明校验真的跑了。

    「load_warnings 为空」本身分不清「跑了但没发现问题」与「根本没跑」，
    故补这一条正向断言。
    """
    text = _P79_PERMANENT_TOML + """
[resources.lifecycle]
enabled = true

[[resources.lifecycle.rules]]
resource_id = "draw_resource"
expire_at = 9999.0

[resources.lifecycle.rules.on_expire]
clear = true
"""
    store = load_toml(_p79_write(tmp_path, text))

    dead = [w for w in store.load_warnings if '永不触发' in w]
    assert len(dead) == 1, store.load_warnings
    assert 'expire_at' in dead[0]
    # 阈值按归一化后的 end_time（168 天）判定，而非 0
    assert '168.0 天' in dead[0]


# ══════════════════════════════════════════════════════════════════
# P79 8.2 剩余四组（[stop_condition] round-trip + 加载期校验三类）
# ══════════════════════════════════════════════════════════════════

_MAIN_CONFIG = 'gacha_simulator/config/config.toml'

_NESTED_STOP_SECTION = """
[stop_condition]
mode = "any"

[[stop_condition.conditions]]
type = "target_acquired"
target_id = "limited_ssr_1"
quantity = 1

[[stop_condition.conditions]]
mode = "all"

[[stop_condition.conditions.conditions]]
type = "resource_threshold"
resource = "draw_resource"
operator = "<="
threshold = 0

[[stop_condition.conditions.conditions]]
mode = "not"

[[stop_condition.conditions.conditions.conditions]]
type = "target_acquired"
target_id = "limited_ssr_2"
quantity = 1
"""


def _p79_config_with(tmp_path, extra, name='p79.toml'):
    base = open(_MAIN_CONFIG, encoding='utf-8').read()
    path = tmp_path / name
    path.write_text(base + extra, encoding='utf-8')
    return str(path)


def test_p79_stop_condition_toml_round_trip_by_structure(tmp_path):
    """8.2「TOML round-trip」：写入 → 读取 → 再写入，**按解析后的结构**逐字段一致。

    不得按 TOML 文本比对：tomli_w 对复合子节点写 [[stop_condition.conditions]]
    表头，对 mode='not' 节点的子数组写成内联 conditions = [{...}]——
    结构相等而文本不同（实测确认）。
    """
    store = load_toml(_p79_config_with(tmp_path, _NESTED_STOP_SECTION))
    tree = store.stop_condition
    assert tree['mode'] == 'any'
    inner = tree['conditions'][1]
    assert inner['mode'] == 'all'
    assert inner['conditions'][1]['mode'] == 'not'

    first = tmp_path / 'out1.toml'
    save_toml(store, str(first))
    again = load_toml(str(first))
    assert again.stop_condition == tree

    second = tmp_path / 'out2.toml'
    save_toml(again, str(second))
    assert load_toml(str(second)).stop_condition == tree

    # 文本形态确实不同（内联 vs 表头），印证「必须按结构比对」
    text1 = first.read_text(encoding='utf-8')
    assert 'conditions = [' in text1          # not 节点写内联
    assert '[[stop_condition.conditions]]' in text1


def test_p79_stop_condition_absent_section_normalizes_to_none(tmp_path):
    """缺省段解析为「仅硬边界」。"""
    store = load_toml(_p79_config_with(tmp_path, ''))
    assert store.stop_condition is None


def test_p79_stop_condition_empty_conditions_normalizes_to_none(tmp_path):
    """conditions 为空数组一律规范化 None（否则 mode='all' 下 all([]) 恒真）。"""
    store = load_toml(_p79_config_with(tmp_path, """
[stop_condition]
mode = "all"
conditions = []
"""))
    assert store.stop_condition is None


def test_p79_load_validation_dead_rules(tmp_path):
    """8.2「加载期校验」：死规则两条（资源生命周期 + banner 生命周期）。"""
    store = load_toml(_p79_config_with(tmp_path, """
[resources.lifecycle]
enabled = true

[[resources.lifecycle.rules]]
resource_id = "draw_resource"
expire_at = 9999.0

[resources.lifecycle.rules.on_expire]
clear = true

[[banner.lifecycle]]
condition = "time_window"
at = 9999
action = "exhaust_banner"
"""))
    dead = [w for w in store.load_warnings if '永不触发' in w]
    assert len(dead) == 2, store.load_warnings
    assert any('resources.lifecycle' in w for w in dead)
    assert any('banner.lifecycle' in w for w in dead)


def test_p79_load_validation_coaxial_threshold(tmp_path):
    """8.2「加载期校验」同轴阈值例：阈值 ≤ 0 或早于硬边界各一条。"""
    store = load_toml(_p79_config_with(tmp_path, """
[stop_condition]
mode = "all"

[[stop_condition.conditions]]
type = "all_pools_end"
end_time = 0.0

[[stop_condition.conditions]]
type = "time_limit"
max_time = 864000.0
"""))
    coaxial = [w for w in store.load_warnings if '停止条件' in w]
    assert len(coaxial) == 2, store.load_warnings
    assert any('第 0 轮结束' in w for w in coaxial)      # all_pools_end(0.0)
    assert any('早于硬边界' in w for w in coaxial)        # time_limit 10 天


def test_p79_load_validation_semantic_trap(tmp_path):
    """8.2「加载期校验（语义陷阱）」：resource_threshold 以 <= 比较 0。"""
    store = load_toml(_p79_config_with(tmp_path, """
[stop_condition]
mode = "any"

[[stop_condition.conditions]]
type = "resource_threshold"
resource = "draw_resource"
operator = "<="
threshold = 0
"""))
    traps = [w for w in store.load_warnings if '暂态' in w]
    assert len(traps) == 1, store.load_warnings
    assert '首次暂时没钱就收工' in traps[0]


def test_p79_load_validation_whitelist_values(tmp_path):
    """8.2「加载期校验（非法值白名单）」：operator / resource 非白名单。

    并同时锁定 5.5 第 5 类的裁决——**不改 check() 的求值语义**、解析期不抛错。
    """
    store = load_toml(_p79_config_with(tmp_path, """
[stop_condition]
mode = "all"

[[stop_condition.conditions]]
type = "resource_threshold"
resource = "no_such_resource"
operator = "<"
threshold = 5.0
"""))
    whitelist = [w for w in store.load_warnings if '白名单' in w or '不在已定义资源中' in w]
    assert len(whitelist) == 2, store.load_warnings
    op_msg = next(w for w in whitelist if 'operator' in w)
    assert "'<'" in op_msg and '<= / >= / ==' in op_msg      # 给出合法取值集合与当前值
    res_msg = next(w for w in whitelist if '的 resource 取值' in w)
    assert "'no_such_resource'" in res_msg and 'draw_resource' in res_msg

    # 求值语义未变：非白名单 operator 仍返回 False；未知 resource 查询恒取 0
    from gacha_simulator.core.state import GachaState
    from gacha_simulator.core.stop_condition import ResourceThresholdCondition

    state = GachaState(resources={'draw_resource': 10})
    assert ResourceThresholdCondition('draw_resource', 0, '<').check(state, []) is False
    assert ResourceThresholdCondition('no_such_resource', 5, '>=').check(state, []) is False
