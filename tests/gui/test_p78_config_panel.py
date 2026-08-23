"""P78 GUI 数据流测试——6b1 round-trip + 6b2 编辑 UI/删除联动。

覆盖（§5.2 阶段 6b）：
  6b1 数据流 round-trip（ISSUE-002/101/102/114/116/121/122/601/602）——get_config→
      set_config 全链路、GUI 保存→重载、保存侧防线、set_config 恢复补全。
  6b2 编辑 UI/删除联动（ISSUE-110/115/128/117/123/124/605）——双输入框换算往返、
      交替项摘要切换、删除确认/级联、里程碑禁用 select_voucher 段存活。
"""
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

import pytest  # noqa: E402

from gacha_simulator.core.config_store import (  # noqa: E402
    ConfigStore, CardDefEntry, MilestoneDef, MilestoneConfig, SelectVoucherDef,
)
from gacha_simulator.core.config_toml import save_toml, load_toml  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def _make_store():
    store = ConfigStore()
    store.card_defs = [
        CardDefEntry(card_id='c1', name='卡1', rarity='ssr'),
        CardDefEntry(card_id='c2', name='卡2', rarity='ssr'),
    ]
    store.resource_defs = {'draw_resource': '抽卡资源', 'voucher1': '武库箱券'}
    store.milestone = MilestoneConfig(enabled=True, milestones=[
        MilestoneDef(name='cyc', threshold=80, offset=20, repeat=True,
                     alternate_rewards=[{'resources': {'voucher1': 1}}, {'cards': ['c1']}]),
        MilestoneDef(name='plain', threshold=10, repeat=True),
    ])
    store.select_vouchers = [SelectVoucherDef(voucher='voucher1', cards=['c1', 'c2'])]
    return store


def _make_panel(store):
    from gacha_simulator.gui.config_panel import ConfigPanel
    p = ConfigPanel()
    p._store = store
    p._refresh_from_store_impl()
    return p


# ══════════════════════════════════════════════════════════════════
# 6b1 数据流 round-trip
# ══════════════════════════════════════════════════════════════════

def test_apply_to_store_transmits_new_fields(qapp):
    """ISSUE-002/101：apply_to_store 透传 offset/alternate_rewards + select_vouchers。"""
    p = _make_panel(_make_store())
    p.apply_to_store()
    m = p._store.milestone.milestones[0]
    assert m.offset == 20 and len(m.alternate_rewards) == 2, 'apply_to_store 透传失败'
    assert p._store.select_vouchers[0].voucher == 'voucher1', 'select_vouchers 写回失败'


def test_get_config_set_config_roundtrip(qapp):
    """ISSUE-102/114/116/121：get_config→set_config 全链路——新字段存活 + 条件省略键。"""
    p = _make_panel(_make_store())
    cfg = p.get_config()
    # get_config 契约（ISSUE-703）：键名 select_vouchers、条目同构
    assert 'select_vouchers' in cfg
    sv = cfg['select_vouchers'][0]
    assert sv['voucher'] == 'voucher1' and sv['cards'] == ['c1', 'c2']
    # 条件省略键（ISSUE-121）：plain 无新字段省略键
    plain = [x for x in cfg['milestone']['milestones'] if x['name'] == 'plain'][0]
    assert 'alternate_rewards' not in plain and 'offset' not in plain, 'plain 不应带空键'
    cyc = [x for x in cfg['milestone']['milestones'] if x['name'] == 'cyc'][0]
    assert cyc['offset'] == 20 and len(cyc['alternate_rewards']) == 2, 'cyc 条件键丢失'
    # set_config 恢复
    p2 = _make_panel(ConfigStore())
    p2.set_config(cfg)
    assert len(p2._store.milestone.milestones) == 2, 'set_config 里程碑整段丢失'
    assert p2._store.milestone.milestones[0].offset == 20, 'set_config offset 丢失'
    assert p2._store.select_vouchers[0].voucher == 'voucher1', 'set_config select_vouchers 丢失'
    assert p2._store.resource_defs.get('voucher1') == '武库箱券', 'set_config 补全覆盖了显示名'


def test_gui_save_reload_roundtrip(qapp, tmp_path):
    """ISSUE-113/121：GUI 保存→重载——无交替/零偏移里程碑省略键、重载正常。"""
    store = ConfigStore()
    store.card_defs = [CardDefEntry(card_id='c1', rarity='ssr')]
    store.resource_defs = {'v1': '券1'}   # v1 需在 resource_defs（否则 apply_to_store 正确级联删除）
    store.milestone.milestones = [MilestoneDef(name='plain', threshold=10, repeat=True)]
    store.select_vouchers = [SelectVoucherDef(voucher='v1', cards=['c1'])]
    p = _make_panel(store)
    p.apply_to_store()
    tmp = str(tmp_path / 'cfg.toml')
    save_toml(p._store, tmp)
    txt = open(tmp, encoding='utf-8').read()
    assert 'alternate_rewards' not in txt and 'offset' not in txt, '空键被写出'
    assert 'select_voucher' in txt, 'select_voucher 段丢失'
    s2 = load_toml(tmp)
    assert s2.milestone.milestones[0].offset == 0
    assert s2.select_vouchers[0].voucher == 'v1'


def test_save_side_filter_empty_alternate(qapp):
    """ISSUE-601：GUI 保存侧防线——空交替项/空 candidates 经 apply_to_store 过滤。"""
    p = _make_panel(ConfigStore())
    p._store.card_defs = [CardDefEntry(card_id='c1', rarity='ssr')]
    p._milestone_defs = [{'name': 'bad', 'threshold': 10, 'repeat': True,
                          'alternate_rewards': [{}, {'cards': ['c1']}], 'bonus_reward': {}}]
    p.apply_to_store()
    m = p._store.milestone.milestones[0]
    assert len(m.alternate_rewards) == 1, f'空交替项未过滤: {m.alternate_rewards}'
    assert m.alternate_rewards[0]['cards'] == ['c1']


def test_set_config_recovers_select_voucher_resource_defs(qapp):
    """ISSUE-602：set_config 恢复『select_vouchers 有、resource_defs 无』→ 补全 voucher id。"""
    p = _make_panel(ConfigStore())
    cfg = {
        'card_defs': [{'card_id': 'c1', 'name': '卡1', 'rarity': 'ssr'}],
        'resource_defs': [],
        'select_vouchers': [{'voucher': 'v1', 'cards': ['c1']}],
    }
    p.set_config(cfg)
    assert 'v1' in p._store.resource_defs, 'set_config 未补全 voucher id'


def test_resource_def_tab_roundtrip(qapp):
    """ISSUE-003/122：资源定义 Tab——set/get round-trip + 列表刷新 + 注册。"""
    p = _make_panel(ConfigStore())
    p.set_resource_defs([
        {'resource_id': 'r1', 'display_name': '资源1', 'initial_amount': 100},
        {'resource_id': 'r2', 'display_name': '资源2', 'initial_amount': 0},
    ])
    got = p.get_resource_defs()
    assert len(got) == 2 and got[0]['resource_id'] == 'r1'
    assert p._resource_list.count() == 2, '资源定义左列表行数错误'
    p._ensure_resource_registered('r3', '资源3')
    assert 'r3' in p._get_resource_ids(), '注册失败'


# ══════════════════════════════════════════════════════════════════
# 6b2 编辑 UI / 删除联动
# ══════════════════════════════════════════════════════════════════

def test_offset_editing_roundtrip(qapp):
    """ISSUE-110/128/501/502：双输入框换算往返——100/80 → threshold=80 offset=20 → 回填 100/80。"""
    p = _make_panel(ConfigStore())
    p._add_milestone()
    row = p._current_milestone_row
    md = p._milestone_defs[row]
    p.ml_repeat_check.setChecked(True)          # every
    p.ml_first_trigger_spin.setValue(100)
    p.ml_threshold_spin.setValue(80)
    p._flush_milestone_current_detail()
    assert md['threshold'] == 80 and md['offset'] == 20, f'every 换算错误: {md}'
    # 切行再切回 → 回填
    p._on_milestone_selected(-1)
    p._on_milestone_selected(row)
    assert p.ml_first_trigger_spin.value() == 100, '首次触发回填错误'
    assert p.ml_threshold_spin.value() == 80, '循环周期回填错误'


def test_atn_offset_editing(qapp):
    """ISSUE-502：at=N 场景——循环周期禁用、写回 threshold=首次触发、offset=0。"""
    p = _make_panel(ConfigStore())
    p._add_milestone()
    row = p._current_milestone_row
    md = p._milestone_defs[row]
    p.ml_repeat_check.setChecked(False)
    p.ml_first_trigger_spin.setValue(120)
    p.ml_threshold_spin.setValue(80)   # 残留（禁用态）
    p._flush_milestone_current_detail()
    assert not p.ml_threshold_spin.isEnabled(), 'at=N 循环周期应禁用'
    assert md['threshold'] == 120 and md['offset'] == 0, f'at=N 写回错误: {md}'


def test_alternate_summary_switch(qapp):
    """ISSUE-115：行切换交替摘要清空/恢复——A 含交替、B 无。"""
    p = _make_panel(ConfigStore())
    p._add_milestone()
    row_a = p._current_milestone_row
    p._milestone_defs[row_a]['alternate_rewards'] = [
        {'cards': ['c1'], 'resources': {}, 'random_cards': []}]
    p._add_milestone()   # B 无交替
    assert p.ml_alternate_list.count() == 0, 'B 无交替应清空摘要'
    p._on_milestone_selected(row_a)
    assert p.ml_alternate_list.count() == 1, 'A→B→A 摘要恢复失败'


def test_remove_resource_def_cancel_keeps_all(qapp, monkeypatch):
    """ISSUE-123：删除确认「取消」→ 资源行与 select_voucher 条目均保留。"""
    from PyQt6.QtWidgets import QMessageBox
    p = _make_panel(ConfigStore())
    p.resource_defs = [{'resource_id': 'v1', 'display_name': '券1', 'initial_amount': 0},
                       {'resource_id': 'other', 'display_name': '其他', 'initial_amount': 0}]
    p._rebuild_resource_list()
    p._select_vouchers = [{'voucher': 'v1', 'cards': ['c1']}]
    monkeypatch.setattr(QMessageBox, 'question',
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    p._resource_list.setCurrentRow(0)
    p._remove_resource_def()
    assert len(p.resource_defs) == 2, '取消后资源行被删'
    assert len(p._select_vouchers) == 1, '取消后 select_voucher 条目被删'


def test_remove_resource_def_confirm_cascades(qapp, monkeypatch):
    """ISSUE-117：确认删除 → 资源行 + select_voucher 级联删。"""
    from PyQt6.QtWidgets import QMessageBox
    p = _make_panel(ConfigStore())
    p.resource_defs = [{'resource_id': 'v1', 'display_name': '券1', 'initial_amount': 0}]
    p._rebuild_resource_list()
    p._select_vouchers = [{'voucher': 'v1', 'cards': ['c1']}]
    monkeypatch.setattr(QMessageBox, 'question',
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    p._resource_list.setCurrentRow(0)
    p._remove_resource_def()
    assert len(p.resource_defs) == 0, '确认删除后资源行未删'
    assert len(p._select_vouchers) == 0, '确认删除后 select_voucher 未级联删'


def test_apply_to_store_cascades_orphan_voucher(qapp):
    """ISSUE-702：apply_to_store 重建后静默级联删除孤儿 select_voucher（不弹框）。"""
    p = _make_panel(ConfigStore())
    p.set_resource_defs([{'resource_id': 'v1', 'display_name': '券1', 'initial_amount': 0}])
    p._select_vouchers = [{'voucher': 'v1', 'cards': ['c1']}, {'voucher': 'ghost', 'cards': ['c1']}]
    p.apply_to_store()
    out = p._store.select_vouchers
    assert len(out) == 1 and out[0].voucher == 'v1', f'孤儿未级联删除: {out}'


def test_set_config_rejects_duplicate_milestone_name(qapp):
    """ISSUE-606：set_config 注入重复 milestone name 被拒（与 TOML 路径同强度）。"""
    from gacha_simulator.core.config_store import ConfigError
    p = _make_panel(ConfigStore())
    cfg = {
        'card_defs': [{'card_id': 'c1', 'name': '卡1', 'rarity': 'ssr'}],
        'milestone': {'enabled': True, 'milestones': [
            {'name': 'dup', 'threshold': 10},
            {'name': 'dup', 'threshold': 20},
        ]},
    }
    with pytest.raises(ConfigError):
        p.set_config(cfg)


def test_set_config_rejects_non_dict_milestone(qapp):
    """ISSUE-606：set_config 注入非 dict milestones 抛 ConfigError（非裸 AttributeError）。"""
    from gacha_simulator.core.config_store import ConfigError
    p = _make_panel(ConfigStore())
    cfg = {
        'card_defs': [{'card_id': 'c1', 'name': '卡1', 'rarity': 'ssr'}],
        'milestone': {'enabled': True, 'milestones': ['bad']},
    }
    with pytest.raises(ConfigError):
        p.set_config(cfg)


def test_set_config_rejects_duplicate_name_with_spaces(qapp):
    """ISSUE-606：strip 后重名（含空格变体）set_config 同样拒绝——两入口完全同构。"""
    from gacha_simulator.core.config_store import ConfigError
    p = _make_panel(ConfigStore())
    cfg = {
        'card_defs': [{'card_id': 'c1', 'name': '卡1', 'rarity': 'ssr'}],
        'milestone': {'enabled': True, 'milestones': [
            {'name': 'dup', 'threshold': 10},
            {'name': ' dup ', 'threshold': 20},
        ]},
    }
    with pytest.raises(ConfigError):
        p.set_config(cfg)


def test_voucher_candidates_edit_roundtrip(qapp):
    """ISSUE-004/605：资源详情面板候选集编辑——勾选写回 + 回填。"""
    p = _make_panel(_make_store())
    p._resource_list.setCurrentRow(0)   # 选中 voucher1
    p._populate_resource_detail({'resource_id': 'voucher1', 'display_name': '武库箱券', 'initial_amount': 0})
    # 默认 c1/c2 勾选（store.select_vouchers）
    selected = []
    for i in range(p._voucher_cards_list.count()):
        if p._voucher_cards_list.item(i).isSelected():
            selected.append(p._voucher_cards_list.item(i).data(Qt.ItemDataRole.UserRole))
    assert set(selected) == {'c1', 'c2'}, f'候选集回填错误: {selected}'


def test_alternate_resource_undef_warning_once(qapp, monkeypatch):
    """ISSUE-005/109：交替项内未定义资源 id 触发一次性警告——首次弹、二次静默。"""
    from PyQt6.QtWidgets import QMessageBox
    warnings_called = []

    def _fake_warning(*a, **k):
        warnings_called.append(a[2] if len(a) > 2 else '')   # (parent, title, text) 的 text

    monkeypatch.setattr(QMessageBox, 'warning', staticmethod(_fake_warning))
    p = _make_panel(ConfigStore())
    p._store.card_defs = [CardDefEntry(card_id='c1', rarity='ssr')]
    p._store.resource_defs = {'draw_resource': '抽卡资源'}
    p._warned_milestone_resource_ids = set()
    # 交替项引用未定义资源 ghost_res
    p._milestone_defs = [{'name': 'm', 'threshold': 10, 'repeat': True,
                          'alternate_rewards': [{'resources': {'ghost_res': 1}}, {'cards': ['c1']}],
                          'bonus_reward': {}}]
    # 首次 apply_to_store → 弹一次警告
    p.apply_to_store()
    assert len(warnings_called) == 1, f'首次应弹 1 次警告: {warnings_called}'
    assert 'ghost_res' in warnings_called[0]
    # 二次 apply_to_store → 静默（_warned_milestone_resource_ids 已含 ghost_res）
    p.apply_to_store()
    assert len(warnings_called) == 1, f'二次应静默: {warnings_called}'
