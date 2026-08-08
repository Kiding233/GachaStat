"""P72 键层级修复回归测试——脆弱性匹配 / 累积模式 banner 段 / 键空间契约。

2026-08-08：D1-D5 裁决后由 .recycle_bin/test_p72_key_repairs.py 迁移至正式位置
（ISSUE-107）并修正路线 A 语义 + 补测（ISSUE-106 键空间契约 / 项 2c 空快照）。
不依赖 QApplication——用 __new__ 构造面板实例，直接测纯逻辑方法。

键空间背景（P72 §2.3）：
- banner 键（b1）：时间域表（pool_end_times / cumulative_snapshots / banner_end_resources / 脆弱性结果）
- 全限定键（b1.main）：归属域表（pool_card_counts / pool_draw_counts / infer_events 产出）
"""
from types import SimpleNamespace

from gacha_simulator.core.per_pool_analysis import compute_transition_flags_from_gdr
from gacha_simulator.core.vulnerability import (
    PoolVulnerabilityResult,
    VulnerabilityAnalysisResult,
)
from gacha_simulator.gui.analysis_panel import AnalysisPanel
from gacha_simulator.gui.plan_search_panel import PlanSearchPanel
from gacha_simulator.gui.process_analysis_panel import ProcessAnalysisPanel
from gacha_simulator.gui.retreat_panel import RetreatPanel


def _make_vuln_result(pool_ids):
    """构造最小 VulnerabilityAnalysisResult（pool_id 为 banner 键）。"""
    return VulnerabilityAnalysisResult(
        pool_results=[
            PoolVulnerabilityResult(
                pool_id=pid, n_total=100, n_failed=20, failure_rate=0.2,
                resource_bins=[], freq_all=[], freq_failed=[],
            )
            for pid in pool_ids
        ],
        alpha=0.05,
        gdr_key='all_targets',
        gdr_threshold=1.0,
        n_simulations=100,
        overall_failure_rate=0.2,
    )


class TestFindVulnerabilityPoolRouteA:
    """路线 A（D2 已裁决）：起始池下拉统一 banner 键，直接匹配 + falsy 守卫。

    原回收站测试假设路线 B 语义（'b1.main' 经归一命中 'b1'）；路线 A 下下拉
    不再传全限定键，_find_vulnerability_pool 只收 banner 键。全限定键传入属防御性
    miss（不归一，防止旧调用方静默错配）。
    """

    def test_banner_key_matches(self):
        panel = PlanSearchPanel.__new__(PlanSearchPanel)
        panel._vulnerability_result = _make_vuln_result(['b1', 'c2'])
        assert panel._find_vulnerability_pool('b1').pool_id == 'b1'
        assert panel._find_vulnerability_pool('c2').pool_id == 'c2'

    def test_full_qualified_key_returns_none_under_route_a(self):
        """路线 A 下拉不再传全限定键；若旧调用方仍传入，防御性不命中。"""
        panel = PlanSearchPanel.__new__(PlanSearchPanel)
        panel._vulnerability_result = _make_vuln_result(['b1'])
        assert panel._find_vulnerability_pool('b1.main') is None

    def test_no_vuln_result_returns_none(self):
        panel = PlanSearchPanel.__new__(PlanSearchPanel)
        panel._vulnerability_result = None
        assert panel._find_vulnerability_pool('b1') is None

    def test_falsy_guard_returns_none(self):
        """ISSUE-702：None/空串（「(从头开始)」项 data=None）不崩溃、安全返回 None。"""
        panel = PlanSearchPanel.__new__(PlanSearchPanel)
        panel._vulnerability_result = _make_vuln_result(['b1'])
        assert panel._find_vulnerability_pool(None) is None
        assert panel._find_vulnerability_pool('') is None


class TestRetreatPoolNamesBannerMapping:
    """项 1a（ISSUE-001）：retreat_panel._get_pool_names 按 banner 段映射。

    脆弱性结果 pr.pool_id 为 banner 键，映射须按 banner 段命中（原全限定键表恒 miss）。
    """

    def _panel(self):
        panel = RetreatPanel.__new__(RetreatPanel)
        panel._store = SimpleNamespace(pools=[
            SimpleNamespace(pool_id='b1.main', name='周年庆', enabled=True),
            SimpleNamespace(pool_id='b1.step1', name='周年庆', enabled=True),
            SimpleNamespace(pool_id='c2', name='武器特选', enabled=True),
            SimpleNamespace(pool_id='legacy', name='旧池', enabled=False),
        ])
        return panel

    def test_banner_key_resolves_to_banner_name(self):
        names = self._panel()._get_pool_names()
        assert names.get('b1', 'b1') == '周年庆'
        assert names.get('c2', 'c2') == '武器特选'

    def test_multi_pool_banner_deduped(self):
        names = self._panel()._get_pool_names()
        assert names['b1'] == '周年庆'  # b1.main + b1.step1 去重为一项

    def test_disabled_pool_excluded(self):
        names = self._panel()._get_pool_names()
        assert 'legacy' not in names


_CUMULATIVE_SNAP = {
    'cumulative_card_counts': {'targetA': 1},
    'cumulative_draws': 10,
    'cumulative_pity_draws': 0,
    'cumulative_consumed': {'draw_resource': 1600.0},
    'cumulative_gained': {'draw_resource': 0.0},
    'banner_end_resources': {'draw_resource': 100.0},
}


class TestProcessAnalysisCumulativeKey:
    """process_analysis 累积模式 banner 段查表（P72 §4.1-2，迁移自回收站）。"""

    def _panel(self):
        panel = ProcessAnalysisPanel.__new__(ProcessAnalysisPanel)
        panel._cumulative_snapshots = {'b1': [_CUMULATIVE_SNAP]}
        return panel

    def _compute(self, panel, pool_id):
        return panel._compute_pool_gdr(
            'cumulative', None, pool_id, 0,
            {'targetA': 1}, 'all_targets',
            ssr_ids=None, weapon_character_map=None,
            initial_resources={},
        )

    def test_full_qualified_pool_finds_banner_snapshot(self):
        """全限定键 b1.main 经 banner 段归一查到快照，不再恒空（修复前 None）。"""
        assert self._compute(self._panel(), 'b1.main') is not None

    def test_same_banner_pools_share_snapshot(self):
        """同 banner 内多 pool 累积 GDR 相同——活动级累积（P72 裁决，同 banner 多行重复值）。"""
        panel = self._panel()
        assert self._compute(panel, 'b1.main') == self._compute(panel, 'b1.step1')

    def test_missing_banner_snapshot_returns_none(self):
        """banner 无累积快照 → 空列表越界 → None（不崩溃）。"""
        panel = ProcessAnalysisPanel.__new__(ProcessAnalysisPanel)
        panel._cumulative_snapshots = {}
        assert self._compute(panel, 'b1.main') is None


class TestEmptySnapshotToNone:
    """项 2c（D4 路线 a 落点 1）：per_pool_analysis 累积分支空快照 → None。

    修复前空快照经 compute_gdr_from_cumulative({}) 算出 0.0，对 lower_is_better 类
    指标（resource_consumed 越少越好）误判成功（0.0 <= 1.0）；修复后短路 None → 计失败。
    """

    def test_lower_is_better_no_false_success(self):
        flags = compute_transition_flags_from_gdr(
            {'b1': [{}]}, ['b1'], {'c1': 1},
            gdr_key='resource_consumed', threshold=1.0, scope='cumulative')
        assert flags == [[False]]

    def test_non_empty_snapshot_contract_unchanged(self):
        """非空快照走正常计算（落点 1 不触碰 compute_pool_gdr_cumulative 导出契约）。"""
        flags = compute_transition_flags_from_gdr(
            {'b1': [{'cumulative_card_counts': {'c1': 5}, 'cumulative_draws': 10,
                     'cumulative_pity_draws': 0,
                     'cumulative_consumed': {'draw_resource': 1600},
                     'cumulative_gained': {}, 'banner_end_resources': {'draw_resource': 0}}]},
            ['b1'], {'c1': 1}, gdr_key='resource_consumed', threshold=2000.0,
            scope='cumulative')
        assert flags == [[True]]


class TestCumulativeByBannerRename:
    """项 3（ISSUE-105）：chart key 改名后旧前缀缓存键被 prune。

    改名 cumulative_by_pool_ → cumulative_by_banner_ 后，_get_ordered_charts 清理
    旧前缀键，防止经「未匹配键」段排在尾部呈无名图表。
    """

    def test_legacy_cache_pruned(self):
        panel = AnalysisPanel.__new__(AnalysisPanel)
        panel._chart_specs_cache = {
            'cumulative_by_pool_x': 'old',
            'cumulative_by_banner_y': 'new',
            'gdr_dist_z': 'z',
        }
        ordered = panel._get_ordered_charts()
        assert 'cumulative_by_pool_x' not in panel._chart_specs_cache
        assert 'cumulative_by_pool_x' not in ordered
        assert 'cumulative_by_banner_y' in ordered
        assert 'gdr_dist_z' in ordered


class TestAnalysisPoolNamesBannerLayer:
    """项 3d（ISSUE-701）：analysis_panel._get_pool_names 补 banner 层。

    时间域消费点（山脊图 ridge_labels / 转变矩阵标题 _pool_label）用 banner 键查
    此层，不再退化裸 banner id；归属域全限定键 label 保持多池区分。
    """

    def _names(self):
        panel = AnalysisPanel.__new__(AnalysisPanel)
        panel._store = SimpleNamespace(pools=[
            SimpleNamespace(pool_id='b1.main', name='周年庆'),
            SimpleNamespace(pool_id='b1.step1', name='周年庆'),
            SimpleNamespace(pool_id='c2', name='武器特选'),
        ])
        return panel._get_pool_names()

    def test_banner_key_resolves(self):
        names = self._names()
        assert names.get('b1', 'b1') == '周年庆'
        assert names.get('c2', 'c2') == '武器特选'

    def test_full_qualified_label_unchanged(self):
        names = self._names()
        assert names['b1.main'] == '周年庆.main'  # 多池区分 label 保留
        assert names['c2'] == '武器特选'
