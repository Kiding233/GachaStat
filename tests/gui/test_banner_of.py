"""banner_of 三态契约参数化单测（P72 ISSUE-103 stage-1 P72-utils-1）。

banner_of（P72 §4.1 项 5）是 retreat_panel 1a / plan_search_panel 1b /
process_analysis_panel 2a / analysis_panel 3d 共用的地基函数，三态契约需机器保护。
"""
import pytest

from gacha_simulator.gui.utils import banner_of


@pytest.mark.parametrize('pool_id,expected', [
    (None, None),             # None → None（pool_combo「(从头开始)」项 data=None）
    ('', None),               # 空串 → None
    ('b1', 'b1'),             # 裸 banner 键 → 原样返回
    ('b1.main', 'b1'),        # 全限定键 → 取第一个 '.' 前缀
    ('b1.main.sub', 'b1'),    # 多 '.' 全限定键 → 仍取第一个前缀
])
def test_banner_of_contract(pool_id, expected):
    assert banner_of(pool_id) == expected
