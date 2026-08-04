"""P61 Ph8 交付：ConfigPanel「卡池管理」Tab 的 Banner round-trip 稳定性测试。

覆盖目标：
  1. refresh_from_store 填充 _banner_defs（含内层 pools/rewards）
  2. apply_to_store 写 store.banner.banners 与 _banner_defs 一致（id 不二次限定）
  3. 展平视图 pool_id 仍为全限定，round-trip 稳定
"""

import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def _make_panel():
    """构造含真实 TOML 的 ConfigPanel 并刷新。"""
    from gacha_simulator.core.config_toml import load_toml
    from gacha_simulator.gui.config_panel import ConfigPanel

    toml_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "gacha_simulator", "config", "config.toml",
    )
    store = load_toml(toml_path)
    p = ConfigPanel()
    p._store = store
    p._refresh_from_store_impl()
    return p


class TestBannerRoundtripP61:
    """Ph8 后 apply_to_store / refresh_from_store 的 Banner 键空间稳定。"""

    def test_refresh_fills_banner_defs(self, qapp):
        """refresh_from_store 后 _banner_defs 与 Banner 列表一致，id 为裸段。"""
        panel = _make_panel()
        assert len(panel._banner_defs) >= 1
        assert panel.banner_list.count() == len(panel._banner_defs)
        for b in panel._banner_defs:
            assert '.' not in b['id'], f"banner id 不应含 '.': {b['id']!r}"
            assert b['pools'], f"banner {b['id']} 应至少一个 pool"

    def test_apply_to_store_no_double_qualification(self, qapp):
        """apply_to_store 后 banner id 为裸段，展平视图保持全限定。"""
        panel = _make_panel()
        banner_ids_defs = {b['id'] for b in panel._banner_defs}

        panel.apply_to_store()
        store = panel._store

        banner_ids = {b.id for b in store.banner.banners}
        assert banner_ids == banner_ids_defs
        assert not any('.' in b.id for b in store.banner.banners), \
            "banner id 不应含 '.'（二次限定 pool_c1.main.main）"

        # 展平视图 pool_id 仍为全限定——round-trip 稳定
        pool_ids = {p.pool_id for p in store.pools}
        for b in store.banner.banners:
            for p in b.pools:
                assert f"{b.id}.{p.id}" in pool_ids, \
                    f"展平 pool_id 应含全限定键 {b.id}.{p.id}"

    def test_apply_to_store_preserves_pools_and_rewards(self, qapp):
        """apply_to_store 后内层池/奖励结构与 _banner_defs 一致。"""
        panel = _make_panel()
        panel.apply_to_store()
        store = panel._store
        assert len(store.banner.banners) == len(panel._banner_defs)
        for b_def, b_entry in zip(panel._banner_defs, store.banner.banners):
            assert len(b_entry.pools) == len(b_def['pools'])
            if b_def['pools']:
                p0 = b_entry.pools[0]
                p0_def = b_def['pools'][0]
                assert p0.id == p0_def['id']
                assert p0.cost == p0_def['cost']
                assert len(p0.rewards) == len(p0_def['rewards'])


class TestPityBindTableRoundtripP61:
    """Ph8b 保底「绑定池」勾选表格 round-trip（ISSUE-328）。

    空勾选 → pools=[]（不绑定任何池，不沿用旧空文本→('*',) 反转语义）；
    全选 → ('*',)；多 pattern → 逐键 fnmatch 勾选且 round-trip 保留。
    """

    def test_empty_selection_persists_as_empty(self, qapp):
        """全不选保存 pools=[]，加载不勾选任何行、保底规则不触发。"""
        panel = _make_panel()
        assert panel._pity_defs, '应有至少一条保底'
        panel.pity_list.setCurrentRow(0)
        panel._set_pity_bind_all(False)
        assert panel._read_pity_bind_patterns() == ()
        panel.apply_to_store()
        store_pools = panel._store.pity.pities[0].pools
        assert store_pools == (), f'空勾选应保存 pools=[]，实际 {store_pools}'
        # 重新加载：不勾选任何行
        panel._pity_defs[0]['pools'] = ()
        panel._on_pity_selected(0)
        checked = [i for i in range(panel.pity_bind_table.rowCount())
                   if panel.pity_bind_table.cellWidget(i, 0).isChecked()]
        assert checked == [], f'空勾选加载后应无勾选行，实际 {checked}'

    def test_select_all_persists_as_wildcard(self, qapp):
        """全选保存 pools=('*',)，加载全勾选。"""
        panel = _make_panel()
        panel.pity_list.setCurrentRow(0)
        panel._set_pity_bind_all(True)
        assert panel._read_pity_bind_patterns() == ('*',)
        panel.apply_to_store()
        assert panel._store.pity.pities[0].pools == ('*',)
        panel._pity_defs[0]['pools'] = ('*',)
        panel._on_pity_selected(0)
        rows = panel.pity_bind_table.rowCount()
        assert rows >= 1
        checked = sum(1 for i in range(rows)
                      if panel.pity_bind_table.cellWidget(i, 0).isChecked())
        assert checked == rows, f'全选加载后应全勾选，实际 {checked}/{rows}'

    def test_multi_pattern_survives_roundtrip(self, qapp):
        """部分勾选（多池）保存后 round-trip 保留，不丢失为 () 或误扩为 ('*',)。"""
        panel = _make_panel()
        banners = panel._store.banner.banners
        assert len(banners) >= 2, '需要至少 2 个 banner'
        p0 = f"{banners[0].id}.{banners[0].pools[0].id}"
        p1 = f"{banners[1].id}.{banners[1].pools[0].id}"
        panel.pity_list.setCurrentRow(0)
        # 先全不选，再模拟用户勾选前 2 行（对应 p0、p1）
        panel._set_pity_bind_all(False)
        panel.pity_bind_table.cellWidget(0, 0).setChecked(True)
        panel.pity_bind_table.cellWidget(1, 0).setChecked(True)
        patterns = panel._read_pity_bind_patterns()
        assert set(patterns) == {p0, p1}, f'部分勾选应生成精确键，实际 {patterns}'
        panel.apply_to_store()
        pools = panel._store.pity.pities[0].pools
        assert set(pools) == {p0, p1}, f'多 pattern 应保留，实际 {pools}'
        # 加载：对应行勾选（不误扩全选、不清空）
        panel._pity_defs[0]['pools'] = (p0, p1)
        panel._refresh_pity_bind_table((p0, p1))
        checked = [i for i in range(panel.pity_bind_table.rowCount())
                   if panel.pity_bind_table.cellWidget(i, 0).isChecked()]
        assert checked == [0, 1], f'多 pattern 加载应勾选 2 行，实际 {checked}'

    def test_partial_select_same_banner_not_compressed(self, qapp):
        """B3 修复：同一 Banner 多池仅勾选部分池时保留精确键（防 {banner}.* 误绑未勾选池）。"""
        from gacha_simulator.core.config_store import BannerPoolEntry
        panel = _make_panel()
        banners = panel._store.banner.banners
        # 给 banner0 追加 free 池（构造多池场景）
        banners[0].pools.append(BannerPoolEntry(id='free', cost='ticket:1'))
        panel._refresh_from_store_impl()
        panel.pity_list.setCurrentRow(0)
        panel._set_pity_bind_all(False)
        main_idx = next(i for i in range(panel.pity_bind_table.rowCount())
                        if panel._pity_bind_keys[i] == f"{banners[0].id}.main")
        panel.pity_bind_table.cellWidget(main_idx, 0).setChecked(True)
        patterns = panel._read_pity_bind_patterns()
        # 只勾 1 池（banner 有 2 池）→ 保留精确键，不压缩为 {banner}.* 误绑未勾选的 free
        assert patterns == (f"{banners[0].id}.main",), \
            f'部分勾选不应压缩误绑未勾选池，实际 {patterns}'

    def test_all_select_same_banner_compressed(self, qapp):
        """B3：同一 Banner 全部池勾选时压缩为 {banner}.*（紧凑，fnmatch 命中全部）。"""
        from gacha_simulator.core.config_store import BannerPoolEntry
        panel = _make_panel()
        banners = panel._store.banner.banners
        banners[0].pools.append(BannerPoolEntry(id='free', cost='ticket:1'))
        panel._refresh_from_store_impl()
        panel.pity_list.setCurrentRow(0)
        panel._set_pity_bind_all(False)
        bid = banners[0].id
        for i in range(panel.pity_bind_table.rowCount()):
            if panel._pity_bind_keys[i].split('.', 1)[0] == bid:
                panel.pity_bind_table.cellWidget(i, 0).setChecked(True)
        patterns = panel._read_pity_bind_patterns()
        assert patterns == (f"{bid}.*",), f'同 banner 全池勾选应压缩为 {{banner}}.*，实际 {patterns}'
