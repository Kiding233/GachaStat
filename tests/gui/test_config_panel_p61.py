"""P61 Ph3 交付：ConfigPanel 写侧迁移 store.banner 后的 pool_id round-trip 稳定性测试。

覆盖目标：
  1. 表格第 1 列保持全限定 {banner_id}.{pool_id} 展平键
  2. apply_to_store 写 BannerEntry 时拆出裸 banner id，杜绝二次限定（pool_c1.main.main）
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


class TestPoolIdRoundtripP61:
    """apply_to_store 后 banner/pool 键空间稳定。"""

    def test_table_first_column_is_qualified(self, qapp):
        """表格第 1 列为全限定 {banner_id}.{pool_id} 键。"""
        panel = _make_panel()
        assert panel.pool_table.rowCount() >= 1
        cell = panel.pool_table.item(0, 1)
        assert cell is not None and cell.text().strip()
        assert '.' in cell.text().strip(), \
            f"表格第 1 列应为全限定键，实际: {cell.text().strip()!r}"

    def test_apply_to_store_no_double_qualification(self, qapp):
        """apply_to_store 后 banner id 为裸段，展平视图保持全限定。"""
        panel = _make_panel()
        qualified = panel.pool_table.item(0, 1).text().strip()
        banner_id = qualified.rsplit('.', 1)[0]

        panel.apply_to_store()
        store = panel._store

        # banner id 拆为裸段——不存在二次限定
        banner_ids = {b.id for b in store.banner.banners}
        assert banner_id in banner_ids, f"banner id 应含裸段 {banner_id!r}，实际: {banner_ids}"
        assert not any('.' in b.id for b in store.banner.banners), \
            "banner id 不应含 '.'（二次限定 pool_c1.main.main）"

        # 展平视图 pool_id 仍为全限定——round-trip 稳定
        pool_ids = {p.pool_id for p in store.pools}
        assert qualified in pool_ids, f"扁平 pool_id 应含 {qualified!r}，实际: {pool_ids}"

    def test_apply_to_store_preserves_inner_pool_id_main(self, qapp):
        """apply_to_store 后每个 banner 的内层池 id 固定为 main。"""
        panel = _make_panel()
        panel.apply_to_store()
        store = panel._store
        for b in store.banner.banners:
            assert len(b.pools) == 1
            assert b.pools[0].id == 'main'
