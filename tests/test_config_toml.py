"""P55 阶段六+十B：TOML 糖展开 + 旧格式迁移测试"""
import pytest
from gacha_simulator.core.config_toml import (
    _expand_soft_to_deltas,
    _check_pity_format,
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
        """start=73, end=90 → ((72, 0.0), (18, 5.555556))

        两端都含：首段为 start-1（第 73 抽即加成），档数 end-start+1 = 18，
        故 100% 恰好落在 end（第 90 抽）。"""
        result = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        assert len(result) == 2
        assert result[0] == (72, 0.0)
        assert result[1][0] == 18
        assert pytest.approx(result[1][1], abs=1e-4) == 100.0 / 18

    def test_soft_interval_start_zero(self):
        """start=0, end=10 → ((0, 0.0), (11, 100/11))"""
        result = _expand_soft_to_deltas('soft_interval', 0, 10, None)
        assert result[0] == (0, 0.0)   # start=0 → max(0, -1) = 0
        assert result[1][0] == 11      # 两端都含：10-0+1

    def test_soft_interval_end_equals_start(self):
        """end <= start → 防御性修正为 start+1"""
        result = _expand_soft_to_deltas('soft_interval', 90, 90, None)
        assert result[0] == (89, 0.0)
        assert result[1][0] == 1  # 修正为 1

    def test_soft_additive(self):
        """start=74, increment=6.0 → ((74, 0.0), (N, 6.0))"""
        result = _expand_soft_to_deltas('soft_additive', 74, None, 6.0)
        assert result[0] == (73, 0.0)
        assert result[1][1] == 6.0
        # 达到 100% 需要的抽数 = ceil(100/6) + 1 = 17
        assert result[1][0] > 0

    def test_soft_additive_zero_increment(self):
        """increment=0.0 → 退化为 1 段（无增长）"""
        result = _expand_soft_to_deltas('soft_additive', 10, None, 0.0)
        assert result[0] == (9, 0.0)
        # increment=0.0 → 不计增长段
        assert result[1][1] == 0.0

    def test_unknown_btype_returns_empty(self):
        """非 soft_interval/soft_additive → 空 tuple"""
        result = _expand_soft_to_deltas('hard', 0, 0, None)
        assert result == ()


# ═══════════════════════════════════════════════════════════════════
# 阶段十B：旧格式迁移
# ═══════════════════════════════════════════════════════════════════

class TestRejectLegacyPityFormat:
    """P81 B11：旧格式 [[pity]] 不再自动迁移，改为 ConfigError 拒绝。

    替换原先的 TestIsLegacyFormat / TestMigrateLegacyPity 两个类。其中
    test_reset_preserved 曾断言 ``reset`` 被原样保留为 'featured_ssr'，那正是
    本次删除的 bug（新引擎 _should_reset 只认 'featured' 与稀有度标签，该值恒
    False，保底计数器永不重置），故该断言随之删除而非改写。
    """

    def test_new_format_passes(self):
        _check_pity_format([
            {'name': 'p1', 'type': 'soft_interval', 'scope': 'ssr', 'start': 74, 'end': 90}
        ])

    def test_empty_list_passes(self):
        _check_pity_format([])

    def test_old_format_with_start_raises(self):
        with pytest.raises(ConfigError, match='旧格式'):
            _check_pity_format([{'name': 'p1', 'type': 'soft', 'start': 74, 'end': 90}])

    def test_old_format_with_func_raises(self):
        with pytest.raises(ConfigError, match='旧格式'):
            _check_pity_format([{'name': 'p1', 'type': 'soft', 'func': 'exp'}])

    def test_mixed_format_raises_ambiguity(self):
        with pytest.raises(ConfigError, match='混用'):
            _check_pity_format([
                {'name': 'old', 'type': 'soft', 'start': 74},
                {'name': 'new', 'type': 'soft_interval', 'scope': 'ssr'},
            ])

    def test_error_message_names_the_offending_entry(self):
        with pytest.raises(ConfigError, match='legacy_one'):
            _check_pity_format([{'name': 'legacy_one', 'type': 'soft', 'start': 74}])

    def test_func_hint_is_reported(self):
        """新格式 + func（手册 §2244 的字面形态）：提示语须点名 func 已不支持。

        该条目有 scope、type 也是新名，唯一的问题是 func。旧稿的提示语写
        「含 start/end/func 等字段」，紧接着又建议「软保底爬升用 start + end」，
        把 start/end 同时当旧格式标志与正确写法；现改为按判据陈述并附 func 专项提示。
        """
        with pytest.raises(ConfigError, match='func 自 P55 起不再支持'):
            _check_pity_format([
                {'name': 'p1', 'type': 'soft_interval', 'scope': 'ssr',
                 'start': 70, 'end': 90, 'func': 'step'}
            ])

    def test_message_does_not_call_start_a_legacy_marker(self):
        """提示语不得把 start/end 列为旧格式标志（它们正是新格式的软保底键）。"""
        with pytest.raises(ConfigError) as ei:
            _check_pity_format([{'name': 'p1', 'type': 'soft', 'start': 74}])
        msg = str(ei.value)
        assert '含 start/end/func 等字段' not in msg
        assert 'start + end + increment' in msg


class TestDeltasRoundTrip:
    """deltas ↔ soft_interval 往返可逆"""

    def test_round_trip(self):
        """deltas → soft_interval → 展开 → 逐段全等"""
        deltas = _expand_soft_to_deltas('soft_interval', 73, 90, None)
        assert deltas == ((72, 0.0), (18, 5.555556))  # 首段 = start-1，档数 = end-start+1
        result = _deltas_to_soft_interval(deltas)
        assert result == (73, 90)
        assert _expand_soft_to_deltas('soft_interval', *result, None) == deltas

    def test_start_zero_normalizes_to_equivalent_start_one(self):
        """start=0 经反函数归一化到 (1, end+1)，deltas 逐段全等。

        _expand_soft_to_deltas() 对 start=0 取 max(0, 0-1)=0，首段长 0；
        反函数只能还原出「首段长 + 1」，故给 start=1 并同步把 end 加 1，
        使档数 n_steps = end - start + 1 保持不变。二者 deltas 完全相同，
        在 _cumulative_boost() 下行为一致，属表示不唯一而非语义丢失。
        """
        d0 = _expand_soft_to_deltas('soft_interval', 0, 10, None)
        assert d0 == ((0, 0.0), (11, 9.090909))
        assert _deltas_to_soft_interval(d0) == (1, 11)
        assert _expand_soft_to_deltas('soft_interval', 1, 11, None) == d0

    def test_non_soft_interval_returns_none(self):
        """首段增量非零 → 无法还原"""
        deltas = ((10, 5.0), (20, 10.0))
        assert _deltas_to_soft_interval(deltas) is None

    def test_single_segment_returns_none(self):
        """非标准双段 → 无法还原"""
        assert _deltas_to_soft_interval(((10, 1.0),)) is None


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


class TestLegacyPityRejectedAtLoad:
    """P81 B11：端到端——旧格式 TOML 加载即抛 ConfigError（不再自动迁移）。"""

    _LEGACY = """[rarities]
ranks = [["SSR"], ["SR"], ["R"]]

[[pity]]
name = "s1"
type = "soft"
start = 74
end = 90
"""

    _MODERN = """[rarities]
ranks = [["SSR"], ["SR"], ["R"]]

[[pity]]
name = "s1"
type = "soft_interval"
scope = "ssr"
start = 74
end = 90
"""

    def _load(self, content):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml',
                                         delete=False, encoding='utf-8') as f:
            f.write(content)
            f.flush()
            path = f.name
        try:
            return load_toml(path)
        finally:
            os.unlink(path)

    def test_legacy_toml_raises_config_error(self):
        with pytest.raises(ConfigError, match='旧格式'):
            self._load(self._LEGACY)

    def test_new_format_toml_loads(self):
        store = self._load(self._MODERN)
        assert len(store.pity.pities) == 1
        assert store.pity.pities[0].btype == 'soft_interval'


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


def test_p79_stop_condition_bare_table_normalizes_to_none(tmp_path):
    """裸表头（`[stop_condition]` 下无任何键）同样规范化 None。

    计划 5.6「空树规范化」把三形态并列：**段缺失 / 顶层节点缺失 / conditions 为空
    数组**。TOML 的裸表头解析为 `{}`，若不收口，`store.stop_condition == {}`——
    运行时行为与 None 相同（`create_stop_condition` 对 falsy 返回 None），但规范化
    摘要不同（`'{}'` vs `''`），`config_hash` 随之不同，两个**行为一致**的配置被
    可比性分析判为「配置不同」。
    """
    store = load_toml(_p79_config_with(tmp_path, '\n[stop_condition]\n'))
    assert store.stop_condition is None
    # 空树不写出该段（round-trip 方向）
    out = tmp_path / 'out_bare.toml'
    save_toml(store, str(out))
    assert '[stop_condition]' not in out.read_text(encoding='utf-8')


def test_p79_shape_issues_surface_as_load_warnings(tmp_path):
    """R20：两类形态问题在加载期各产生一条 load_warnings（只告警、不阻断加载）。"""
    store = load_toml(_p79_config_with(tmp_path, """
[stop_condition]
mode = "any"
[[stop_condition.conditions]]
type = "fixed_action_count"
count = 500
""", name='shape1.toml'))
    unknown = [w for w in store.load_warnings if '未声明参数键' in w]
    assert len(unknown) == 1, store.load_warnings
    assert 'count' in unknown[0] and 'max_actions' in unknown[0]
    # 不阻断：条件树照常填充、照常可构造（只是参数用了默认值）
    assert store.stop_condition is not None

    store2 = load_toml(_p79_config_with(tmp_path, """
[stop_condition]
mode = "all"
""", name='shape2.toml'))
    shape = [w for w in store2.load_warnings if '缺少 conditions' in w]
    assert len(shape) == 1, store2.load_warnings


def test_p79_default_config_has_no_shape_warnings(tmp_path):
    """默认真实配置不得误报（告警一响就没人看了）。"""
    store = load_toml(_p79_config_with(tmp_path, ''))
    assert [w for w in store.load_warnings if '未声明参数键' in w] == []
    assert [w for w in store.load_warnings if '缺少 conditions' in w] == []


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
    assert ResourceThresholdCondition('draw_resource', 0, '<').check(state, _stats()) is False
    assert ResourceThresholdCondition('no_such_resource', 5, '>=').check(state, _stats()) is False


def test_p79_empty_condition_tree_omits_toml_section(tmp_path):
    """8.2「空配置表现」行的「**落盘为缺省**」一半。

    空树（None）写侧必须省略段（不写空表头），否则下次 load 会把它当成显式的
    空配置；读侧据此规范化为 None。
    """
    store = load_toml(_p79_config_with(tmp_path, ''))
    assert store.stop_condition is None

    out = tmp_path / 'p79_empty_out.toml'
    save_toml(store, str(out))
    text = out.read_text(encoding='utf-8')
    assert '[stop_condition]' not in text, '空树不得写出 [stop_condition] 段'
    assert load_toml(str(out)).stop_condition is None


def test_p79_nonempty_condition_tree_writes_toml_section(tmp_path):
    """反向：非空树必须落盘（否则配置静默丢失）。"""
    store = load_toml(_p79_config_with(tmp_path, _NESTED_STOP_SECTION))
    out = tmp_path / 'p79_full_out.toml'
    save_toml(store, str(out))
    text = out.read_text(encoding='utf-8')
    assert '[stop_condition]' in text
    assert load_toml(str(out)).stop_condition == store.stop_condition


def _stats(**kw):
    """P81 §4.1-4：停止条件 check() 的 stats 形参改为必填，测试统一由此构造。"""
    from gacha_simulator.service.gacha_service import SimulationStats
    s = SimulationStats()
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_b8_legacy_colon_gain_rule_surfaces_as_load_warning():
    """P81 B8：旧写法（参数嵌在类型串里）的增益规则在加载期报出、不阻断加载。

    该写法已不再被识别——GUI 对未识别的类型统一显示为「每天」，用户无从察觉，
    故必须靠告警说明「配置没按写的生效」。此处直接测 `_build_gain_rules`（告警
    所在单元），不构造整份 TOML：主配置的 gain_rules 是内联数组，无法再追加同名表。
    """
    from gacha_simulator.core.config_store import ConfigStore
    from gacha_simulator.core.config_toml import _build_gain_rules

    store = ConfigStore()
    _build_gain_rules({'resources': {'gain_rules': [
        {'type': 'every_n_days:3', 'param': '', 'gains': {'draw_resource': 160}},
    ]}}, store)

    legacy = [w for w in store.load_warnings if '旧写法' in w]
    assert len(legacy) == 1, store.load_warnings
    assert 'every_n_days:3' in legacy[0]
    # 不阻断：规则照常入 store（界面会显示为「每天」，用户靠上面这条告警察觉）
    assert [r.rule_type for r in store.gain_rules] == ['every_n_days:3']

    # 新格式（type + param 两字段）不产生该告警
    store2 = ConfigStore()
    _build_gain_rules({'resources': {'gain_rules': [
        {'type': 'every_n_days', 'param': '3', 'gains': {'draw_resource': 160}},
    ]}}, store2)
    assert [w for w in store2.load_warnings if '旧写法' in w] == []
    assert [r.rule_type for r in store2.gain_rules] == ['every_n_days']

# ══════════════════════════════════════════════════════════════════
# P64 S4c ②：`load_toml` 失败原子性
# ══════════════════════════════════════════════════════════════════
# 原实现先 `store.clear()` 再逐段构建，中途抛错即停在**半装**状态——实测（真实
# 配置 + 一处非法输入）：`banner.banners` 8→0、`pity.pities` 1→0，已构建的段落
# 留下、未构建的段落已清空；而 GUI 的 `_load_default_config` / `import_config`
# 是 `except Exception` → stderr traceback + 状态栏一行字，窗口照常打开，即
# **静默半开**。
#
# `load_toml` 调用链内现有近百处 `raise ConfigError`（cards / pity / milestone /
# select_voucher / banners / resource_lifecycle / stop_condition 各段皆有），逐处
# 包 try 治不了本，故改为「先快照、抛错即整体回滚」（`_restore_config_store`）。
# 本组对**每个段落**各注入一处非法输入（外加一例 TOML 语法错误，证明非
# `ConfigError` 的异常同样回滚），断言失败后传入的 store 与加载前逐字段相同。

# 基准配置 = 真实 `config/config.toml` + 本增量段。增量段的用途是**反空转**：
# 真实配置自身在 resource_lifecycle / select_voucher / stop_condition 三段上是空的。
# **订正（S4c 审查 low，2026-10-10 实测）**：原文写「不补的话这三段的用例仍然绿」，
# 与实测不符。删掉 `_GOOD_EXTRAS` 且把原子性变异回「先 clear 再构建」后，这三段的
# 用例并非绿，而是先在下方反空转守卫（`assert all(c >= 1 ...)` 覆盖这三段的计数）
# 处报错，10 条全红。让这三段有判别力的是「守卫 + 增量段」**两者**：守卫保证段落非
# 空，增量段保证「确有内容可被清掉」，缺任一半该段用例都失去意义。
_GOOD_EXTRAS = '''
[resources.lifecycle]
enabled = true

[[resources.lifecycle.rules]]
resource_id = "exchange_currency"
expire_at = 100

[resources.lifecycle.rules.on_expire]
clear = true

[[select_voucher]]
voucher = "draw_resource"
cards = ["limited_ssr_1"]

[stop_condition]
type = "fixed_action_count"
max_actions = 500
'''


def _real_config_path():
    """真实配置路径（开发环境即 `gacha_simulator/config/config.toml`）。"""
    from gacha_simulator.paths import get_config_dir
    return os.path.join(get_config_dir(), 'config.toml')


def _good_config_text():
    with open(_real_config_path(), encoding='utf-8') as f:
        return f.read() + _GOOD_EXTRAS


def _store_field_snapshot(store):
    """store 全部 dataclass 字段的深拷贝快照（逐字段比对的基准）。

    逐字段**现取**（`dataclasses.fields`）而非手写清单——手写清单漏一项即让
    「逐字段相同」的断言失去覆盖面。
    """
    import copy as _c
    import dataclasses as _d
    from gacha_simulator.core.config_store import ConfigStore
    return {f.name: _c.deepcopy(getattr(store, f.name))
            for f in _d.fields(ConfigStore)}


def _load_text_into(store, text):
    """写临时文件后加载到 store（无论成败清临时文件）。"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False,
                                     encoding='utf-8') as f:
        f.write(text)
        path = f.name
    try:
        return load_toml(path, store=store)
    finally:
        os.unlink(path)


def _inject(text, find, replace):
    """在基准配置上注入一处非法输入：`find` 空串表示**追加**，否则为定点替换。"""
    if not find:
        return text + replace
    assert text.count(find) == 1, f'注入锚点在基准配置中不唯一：{find!r}'
    return text.replace(find, replace)


# 段落名 → (锚点, 替换文本, 期望异常)
# 追加形态用于数组表（`[[card]]` / `[[pity]]` / …），定点替换用于基准配置里
# **已存在**的表（`[resources.lifecycle]` / `[stop_condition]`）——同名表不能
# 二次定义，追加会退化成 TOMLDecodeError，测不到该段自己的校验分支。
_ILLEGAL_BY_SEGMENT = [
    ('cards',
     '', '\n[[cards]]\nid = "x"\nname = "x"\nrarity = "SSR"\n',
     ConfigError),
    ('pity',
     '', '\n[[pity]]\nname = "bad"\ntype = "hard"\nscope = "ssr"\n'
         'threshold = 90\nmax_tirggers = 2\n',
     ConfigError),
    ('milestone',
     '', '\n[[milestone]]\nname = "m_bad"\nthreshold = 0\n',
     ConfigError),
    ('select_voucher',
     '', '\n[[select_voucher]]\nvoucher = "exchange_currency"\n'
         'cards = ["no_such_card"]\n',
     ConfigError),
    ('banners',
     '', '\n[[banner]]\nid = "b_bad"\nname = "bad"\nstart_day = 0\nend_day = 1\n'
         '\n[[banner.pool]]\nid = "main"\ncost = "draw_resource:160"\n'
         'epitomizable_cards = ["nonexistent"]\n'
         '\n[[banner.pool.reward]]\ncard_id = "limited_ssr_1"\n'
         'probability = 1.0\nrarity = "SSR"\nfeatured = true\n',
     ConfigError),
    ('resource_lifecycle',
     'resource_id = "exchange_currency"\n', '',
     ConfigError),
    ('stop_condition',
     '[stop_condition]\ntype = "fixed_action_count"\nmax_actions = 500\n',
     '[stop_condition]\nconditions = "not_a_list"\n',
     ConfigError),
    ('toml_syntax',
     '', '\n[[banner]\n',
     Exception),
]


class TestLoadTomlFailureAtomicity:
    """加载失败 → 传入的 store 逐字段回滚（P64 S4c ②）。"""

    @staticmethod
    def _loaded_store():
        """基准配置装好的 store + 反空转守卫（任一段落为空则本组用例失去意义）。"""
        store = _load_text_into(None, _good_config_text())
        counts = (len(store.banner.banners), len(store.card_defs),
                  len(store.pity.pities), len(store.resource_defs),
                  len(store.milestone.milestones),
                  len(store.resource_lifecycle.rules), len(store.select_vouchers))
        assert all(c >= 1 for c in counts) and store.stop_condition is not None, (
            f'基准配置的段落为空 {counts} / stop_condition={store.stop_condition}——'
            f'本组用例的反空转前提失效（计划实测：banners 8 / cards 24 / pity 1）')
        return store

    @pytest.mark.parametrize('segment,find,replace,exc',
                             _ILLEGAL_BY_SEGMENT,
                             ids=[c[0] for c in _ILLEGAL_BY_SEGMENT])
    def test_failed_load_leaves_store_unchanged(self, segment, find, replace, exc):
        """各段落各自的非法输入 → 抛错，且 store 逐字段与加载前相同。"""
        store = self._loaded_store()
        before = _store_field_snapshot(store)
        counts_before = (len(store.banner.banners), len(store.card_defs),
                         len(store.pity.pities), len(store.resource_defs),
                         len(store.milestone.milestones),
                         len(store.resource_lifecycle.rules),
                         len(store.select_vouchers))

        with pytest.raises(exc):
            _load_text_into(store, _inject(_good_config_text(), find, replace))

        after = _store_field_snapshot(store)
        counts_after = (len(store.banner.banners), len(store.card_defs),
                        len(store.pity.pities), len(store.resource_defs),
                        len(store.milestone.milestones),
                        len(store.resource_lifecycle.rules),
                        len(store.select_vouchers))
        assert counts_after == counts_before, (
            f'{segment}：失败后段落计数被改动（原实现此处为 banners 8→0 / pity 1→0）')
        diff = sorted(k for k in before if before[k] != after[k])
        assert diff == [], f'{segment}：失败后下列字段与加载前不同：{diff}'

    def test_failed_load_keeps_store_usable(self):
        """失败后 store 仍可用（回滚不留残留：配置项与派生值都对得上）。"""
        store = self._loaded_store()
        end_time_before = store.end_time
        n_pools = len(store.pools)

        with pytest.raises(ConfigError):
            _load_text_into(
                store,
                _inject(_good_config_text(), '',
                        '\n[[pity]]\nname = "bad"\ntype = "hard"\nscope = "ssr"\n'
                        'max_tirggers = 2\n'))

        assert store.end_time == end_time_before
        assert len(store.pools) == n_pools
        assert store.pity.pities and store.pity.pities[0].name == 'ssr_soft'

    def test_successful_load_after_failure_still_replaces(self):
        """失败 → 再成功加载：成功那次照常整体替换（回滚不粘连上次的失败）。"""
        store = self._loaded_store()
        with pytest.raises(ConfigError):
            _load_text_into(
                store,
                _inject(_good_config_text(), '',
                        '\n[[milestone]]\nname = "m_bad"\nthreshold = 0\n'))

        minimal = ('[rarities]\nranks = [["SSR"], ["SR"], ["R"]]\n'
                   '\n[[banner]]\nid = "b1"\nname = "b1"\nstart_day = 0\nend_day = 3\n'
                   '\n[[banner.pool]]\nid = "main"\ncost = "draw_resource:160"\n'
                   '\n[[banner.pool.reward]]\ncard_id = "c1"\nprobability = 1.0\n'
                   'rarity = "SSR"\nfeatured = true\n')
        _load_text_into(store, minimal)
        assert len(store.banner.banners) == 1
        assert store.card_defs == []
        assert store.pity.pities == []

    def test_failure_with_fresh_store_still_raises(self):
        """`store=None`（新建实例）路径：照常抛错，异常不被吞掉。"""
        with pytest.raises(ConfigError):
            _load_text_into(
                None,
                _inject(_good_config_text(), '',
                        '\n[[pity]]\nname = "bad"\ntype = "hard"\nscope = "ssr"\n'
                        'max_tirggers = 2\n'))
