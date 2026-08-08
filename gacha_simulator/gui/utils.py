"""GUI 层共用工具函数（P72 ISSUE-704 落点）。

多面板共用的轻量工具放本模块；单面板私有的辅助仍放各面板模块内。
本模块不依赖 Qt（纯函数），供 plan_search_panel / retreat_panel /
process_analysis_panel / analysis_panel 跨面板共用。
"""
from typing import Optional


def banner_of(pool_id: Optional[str]) -> Optional[str]:
    """全限定键 → banner 键转换（三态契约，P72 ISSUE-702）。

    - None / 空串 → None（不抛异常，供 pool_combo「(从头开始)」data=None 项）
    - 裸 banner 键（无 ``.``，如 ``'b1'``）→ 原样返回
    - 全限定键（含 ``.``，如 ``'b1.main'`` / ``'b1.main.sub'``）→ 取第一个 ``.`` 前缀（``'b1'``）

    P72 键空间统一背景：脆弱性结果 / 累积快照等**时间域**表用 banner 键（``'b1'``），
    归属域表用全限定键（``'b1.main'``）。消费端经本函数归一后再跨表匹配，
    避免「拿归属域键查时间域表」的恒空键错配（P72 §2.3 N1/N3 根因）。
    """
    if pool_id is None or pool_id == '':
        return None
    if '.' in pool_id:
        return pool_id.split('.')[0]
    return pool_id
