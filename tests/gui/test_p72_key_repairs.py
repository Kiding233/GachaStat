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

    def test_categories_key_is_banner(self):
        """ISSUE-108(1)：ANALYSIS_CATEGORIES/_EXPANDABLE_KEYS 的累积项键改为 cumulative_by_banner，
        无旧 cumulative_by_pool 残留。"""
        from gacha_simulator.gui.analysis_panel import ANALYSIS_CATEGORIES, _EXPANDABLE_KEYS

        all_keys = [k for items in ANALYSIS_CATEGORIES.values() for k, _ in items]
        assert 'cumulative_by_banner' in all_keys
        assert 'cumulative_by_pool' not in all_keys
        assert 'cumulative_by_banner' in _EXPANDABLE_KEYS

    def test_needs_computation_initial_true(self):
        """ISSUE-108(2)：未计算过 → 需要重算（不恒 False）。"""
        panel = AnalysisPanel.__new__(AnalysisPanel)
        panel._computed_conditions = {}
        panel._get_conditions_for_key = lambda key: {'k': key}
        assert panel._needs_computation('cumulative_by_banner_x') is True

    def test_needs_computation_no_recompute_when_unchanged(self):
        """ISSUE-108(2)：条件未变 → 不需重算（不恒 True）。"""
        panel = AnalysisPanel.__new__(AnalysisPanel)
        panel._computed_conditions = {'cumulative_by_banner_x': {'k': 'x'}}
        panel._get_conditions_for_key = lambda key: {'k': 'x'}
        assert panel._needs_computation('cumulative_by_banner_x') is False

    def test_needs_computation_recompute_when_condition_changed(self):
        """ISSUE-123(2')：勾选指标变化（条件变化）→ 必须重算——防恒 False 导致勾选后静默不更新。"""
        panel = AnalysisPanel.__new__(AnalysisPanel)
        panel._computed_conditions = {'cumulative_by_banner_x': {'k': 'x'}}
        panel._get_conditions_for_key = lambda key: {'k': 'y'}  # 勾选变化 → 条件变化
        assert panel._needs_computation('cumulative_by_banner_x') is True


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


def _make_gdr_ctx():
    from gacha_simulator.core.gdr import GDRContext
    return GDRContext(
        target_specs={'card_A': 1},
        ssr_ids={'card_A'},
        all_drawable_ids=['card_A'],
        initial_resources={'draw_resource': 1000},
        resource_gain_per_day={},
    )


class TestPerPoolAnalysisBannerKeys:
    """ISSUE-106 第二部分：per_pool_analysis 两产键方返回键均为 banner 级。"""

    def test_compute_cumulative_snapshots_banner_keys(self):
        from gacha_simulator.core.info_vector import InfoVector
        from gacha_simulator.core.per_pool_analysis import compute_cumulative_snapshots

        history = [
            InfoVector('draw', 'card_A', 'b1.main', real_time_after=5.0,
                       resources_consumed={'draw_resource': 160}),
            InfoVector('draw', 'card_A', 'b2.main', real_time_after=15.0,
                       resources_consumed={'draw_resource': 160}),
        ]
        pool_end_times = {'b1': 10.0, 'b2': 20.0}
        snaps = compute_cumulative_snapshots(history, _make_gdr_ctx(), pool_end_times)
        assert [s.pool_id for s in snaps] == ['b1', 'b2']  # 键为 banner 级
        for s in snaps:
            assert '.' not in s.pool_id

    def test_cumulative_gdr_at_pool_ends_banner_keys(self):
        from gacha_simulator.core.per_pool_analysis import (
            CumulativeSnapshot, cumulative_gdr_at_pool_ends,
        )

        snap = CumulativeSnapshot(
            pool_id='b1', pool_end_time=10.0, cumulative_draws=10,
            cumulative_target_cards=1, cumulative_pity_draws=0,
            cumulative_resources_consumed={'draw_resource': 1600},
            target_achievement_rate=1.0, ssr_collection_rate=1.0,
            resource_remaining=100.0,
        )
        result = cumulative_gdr_at_pool_ends({'b1': [snap], 'b2': []})
        assert set(result.keys()) == {'b1'}  # 空 snaps 跳过，键为 banner 级


def test_parallel_vs_single_thread_snapshot_equiv():
    """ISSUE-104：并行（WorkerLocalExtractor + merge_extraction_packets）与单线程
    （DrawSequenceExtractor）两条路径累积快照键均为 banner 级，累积消费端
    _compute_pool_gdr 在两条路径下行为等价（ISSUE-130 单线程分支不得跳过）。
    """
    from gacha_simulator.core.result_types import CompactResult
    from gacha_simulator.core.streaming import (
        WorkerLocalExtractor, merge_extraction_packets, DrawSequenceExtractor,
    )
    from gacha_simulator.gui.process_analysis_panel import ProcessAnalysisPanel

    pool_end_times = {'b1': 10.0, 'b2': 20.0}
    target_specs = {'card_A': 1}

    def make_compact(pool_ids, card_ids, times, res):
        return CompactResult(
            draw_pool_ids=pool_ids, draw_card_ids=card_ids, draw_times=times,
            draw_pity=[False] * len(pool_ids), draw_pity_names=[''] * len(pool_ids),
            draw_pity_counter_max=[0] * len(pool_ids),
            draw_resources_consumed=[{'draw_resource': 160}] * len(pool_ids),
            draw_resources_gained=[{}] * len(pool_ids),
            banner_end_resources=res,
        )

    compacts = [
        make_compact(['b1', 'b2'], ['card_A', 'card_A'], [5.0, 15.0],
                     {'b1': {'draw_resource': 500}, 'b2': {'draw_resource': 400}}),
        make_compact(['b1', 'b2'], ['card_A', 'other'], [3.0, 18.0],
                     {'b1': {'draw_resource': 500}, 'b2': {'draw_resource': 400}}),
    ]

    # 并行路径：WorkerLocalExtractor.process(dict) → merge 按 pool_id 聚合
    worker = WorkerLocalExtractor(pool_end_times=pool_end_times,
                                  target_ids={'card_A'}, target_specs=target_specs)
    packets = [worker.process(c.to_dict()) for c in compacts]
    par = merge_extraction_packets(packets)['cumulative_snapshots']

    # 单线程路径：DrawSequenceExtractor.on_result(CompactResult)
    extractor = DrawSequenceExtractor(max_keep=10, pool_end_times=pool_end_times,
                                      target_ids={'card_A'}, target_specs=target_specs)
    for c in compacts:
        extractor.on_result(c)
    single = extractor.get_cumulative_snapshots()

    # 键均为 banner 级（无 '.'）
    assert set(par.keys()) == {'b1', 'b2'}
    assert set(single.keys()) == {'b1', 'b2'}
    for pid in par:
        assert '.' not in pid
    for pid in single:
        assert '.' not in pid

    # 消费端行为等价：_compute_pool_gdr 在两条路径快照下均命中 b1
    def gdr_from(cum):
        panel = ProcessAnalysisPanel.__new__(ProcessAnalysisPanel)
        panel._cumulative_snapshots = cum
        return panel._compute_pool_gdr(
            'cumulative', None, 'b1.main', 0, target_specs, 'all_targets',
            ssr_ids=None, weapon_character_map=None, initial_resources={},
        )

    assert gdr_from(par) is not None
    assert gdr_from(single) is not None


def test_old_dataset_without_cumulative_snapshots_hints():
    """ISSUE-006：旧数据集（result_store 加载，无 cumulative_snapshots 字段）切累积模式——
    update_results 给出空态提示（不静默输出 0.0 误导用户）。
    """
    from gacha_simulator.gui.process_analysis_panel import ProcessAnalysisPanel

    panel = ProcessAnalysisPanel.__new__(ProcessAnalysisPanel)
    panel.status_label = SimpleNamespace()
    panel._last_status = ''
    panel.status_label.setText = lambda s: setattr(panel, '_last_status', s)

    # 有池但无累积快照（旧数据集场景）→ 空态提示
    panel.update_results([{'card_counts': {}}], pool_end_times={'b1': 10.0}, cumulative_snapshots={})
    assert '累积' in panel._last_status or '快照' in panel._last_status

    # 正常数据集（有累积快照）→ 无提示
    panel.update_results([{'card_counts': {}}], pool_end_times={'b1': 10.0},
                         cumulative_snapshots={'b1': [{}]})
    assert '提示' not in panel._last_status

    # 无池 → 无提示（累积模式本就不适用）
    panel.update_results([{'card_counts': {}}], pool_end_times={}, cumulative_snapshots={})
    assert '提示' not in panel._last_status


def _mock_bb_table(panel):
    """mock _fill_bb_table 依赖的 QTableWidget 接口（__new__ 模式）。"""
    panel.bb_table = SimpleNamespace()
    panel.bb_table.clear = lambda: None
    panel.bb_table.setColumnCount = lambda n: None
    panel.bb_table.setHorizontalHeaderLabels = lambda h: None
    panel.bb_table.setRowCount = lambda n: None
    panel.bb_table.setItem = lambda *a: None
    panel.bb_table.resizeColumnsToContents = lambda: None
    panel.bb_table.horizontalHeader = lambda: SimpleNamespace(
        setSectionResizeMode=lambda m: None)
    panel.success_mode_combo = SimpleNamespace(currentData=lambda: 'count')
    return panel


def test_bb_detail_label_caliber_projection_and_missing():
    """ISSUE-003 + ISSUE-103：成败统计 bb_detail_label 注明「未触达继承态」与
    「数据缺失，非真失败」两种口径。"""
    from gacha_simulator.gui.process_analysis_panel import ProcessAnalysisPanel

    panel = _mock_bb_table(ProcessAnalysisPanel.__new__(ProcessAnalysisPanel))
    panel.bb_detail_label = SimpleNamespace()
    panel._bb_text = ''
    panel.bb_detail_label.setText = lambda s: setattr(panel, '_bb_text', s)

    panel._fill_bb_table({
        'pattern_table': [], 'pool_success_rates': {},
        'all_fail_prob': 0, 'all_success_prob': 0, 'total': 0,
    })
    assert '未触达' in panel._bb_text and '继承态' in panel._bb_text  # ISSUE-003
    assert '数据缺失' in panel._bb_text and '非真失败' in panel._bb_text  # ISSUE-103


def test_chart_webview_new_prefix_hit():
    """ISSUE-108(3)：ChartWebView has_chart/update_chart 命中新前缀 cumulative_by_banner，
    旧前缀 cumulative_by_pool miss（set_charts 重置键集后旧 key 不残留）。
    """
    from gacha_simulator.gui.chart_webview import ChartWebView

    wv = ChartWebView.__new__(ChartWebView)
    wv._loaded = False
    wv._pending_updates = {}
    wv._pending_charts = None
    wv._renderer = SimpleNamespace()

    class _FakeFig:
        def to_json(self):
            return '{}'

    wv._renderer.to_figure = lambda spec: _FakeFig()

    wv.set_charts({'cumulative_by_banner_x': 'spec'})
    assert wv.has_chart('cumulative_by_banner_x') is True   # 新前缀命中
    assert wv.has_chart('cumulative_by_pool_x') is False    # 旧前缀 miss

    # update_chart 命中新前缀（_loaded=True 时登记 _chart_keys；False 时走 pending 暂存）
    wv._loaded = True
    wv.page = lambda: SimpleNamespace(runJavaScript=lambda *a, **k: None)
    wv.update_chart('cumulative_by_banner_y', 'spec')
    assert wv.has_chart('cumulative_by_banner_y') is True
