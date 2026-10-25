"""WebUI 最差影响服务（`webui/worst_impact_service.py`）的展示面测试。

**本文件的存在理由（2026-10-15）**：批 A 给 GUI 的覆盖倍数读数加了「可追溯行」
（α / N / 分子 / 分母），而 WebUI 侧的同一展示（`analyze_worst_dist` 的 gauge 段）
**没有**该行，两处口径不一致；且 GUI 侧那条因无自动化测试被记为「未覆盖面」。
本文件把 WebUI 侧的展示钉住，同时用同一函数断言两处同源。

**只测展示，不测数值口径**：覆盖倍数的计算（`_compute_pity_coverage`）不在断言面内，
断言的对象是「读数旁是否带上了 α / N 与两个原始量」。
"""

from gacha_simulator.core.config_store import ConfigStore
from gacha_simulator.core.worst_impact import coverage_trace_text
from gacha_simulator.webui.worst_impact_service import analyze_worst_dist

#: 保底关闭 / 无 PityDef 时的退化分母（`_get_pity_cost` 的既有口径：90 抽 × 160）。
_DEGENERATE_PITY_COST = 90 * 160


def _dataset(initial_resource=3060.0, n=2):
    """最小 dataset：`analyze_worst_dist` 只读 `aggregate_data` / `target_specs` /
    `initial_resources` 三个键，`aggregate_data` 的每条只需 `card_counts`。"""
    return {
        'aggregate_data': [
            {'card_counts': {'_wi_featured_0': 1},
             'final_resources': {'draw_resource': 3000.0}}
            for _ in range(n)
        ],
        'target_specs': {},
        'initial_resources': {'draw_resource': initial_resource},
    }


def _gauge(res):
    assert res['ok'], res.get('error')
    sec = next((s for s in res['sections'] if s.get('key') == 'gauge'), None)
    assert sec is not None, f'未产出 gauge 段：{[s.get("key") for s in res["sections"]]}'
    return sec


class TestWorstDistGaugeTrace:
    """`analyze_worst_dist` 的覆盖倍数读数须带 α / N 与两个原始量。"""

    def test_gauge_desc_carries_alpha_and_n(self):
        """读数旁带 `α=0.05` 与 `N=2`（α 是覆盖倍数最敏感的输入，N 决定分位噪声）。"""
        res = analyze_worst_dist(_dataset(), ConfigStore(),
                                 {'cond': 'all', 'alpha': 0.05})
        desc = _gauge(res)['desc']
        assert 'α=0.05' in desc, desc
        assert 'N=2' in desc, desc

    def test_gauge_desc_carries_raw_amounts(self):
        """能显示原始量更好：分子（保守资源）与分母（大保底成本）一并印出。"""
        res = analyze_worst_dist(_dataset(), ConfigStore(),
                                 {'cond': 'all', 'alpha': 0.05})
        desc = _gauge(res)['desc']
        assert '保守资源 3060' in desc, desc
        assert f'大保底成本 {_DEGENERATE_PITY_COST}' in desc, desc

    def test_gauge_desc_trace_matches_shared_helper(self):
        """可追溯段与 `core.worst_impact.coverage_trace_text` 的输出**逐字相同**。

        该函数是 GUI 与 WebUI 两处展示的**唯一实现**（2026-10-15 下沉），故本断言
        同时钉住「WebUI 侧口径 = GUI 侧口径」。
        """
        res = analyze_worst_dist(_dataset(), ConfigStore(),
                                 {'cond': 'all', 'alpha': 0.05})
        desc = _gauge(res)['desc']
        expected = coverage_trace_text(alpha=0.05, n=2, worst_resource=3060.0,
                                       pity_cost=_DEGENERATE_PITY_COST)
        assert desc.endswith(expected), (desc, expected)

    def test_alpha_from_params_is_honored(self):
        """α 取自 `params['alpha']`（前端 worst_dist 方法块的可调参数），非写死默认值。"""
        res = analyze_worst_dist(_dataset(), ConfigStore(),
                                 {'cond': 'all', 'alpha': 0.15})
        desc = _gauge(res)['desc']
        assert 'α=0.15' in desc, desc
        assert 'α=0.05' not in desc, desc


class TestTraceTextSingleImplementation:
    """可追溯文本是**一处实现**：GUI 面板的薄壳与 core 函数同源。"""

    def test_gui_panel_delegates_to_core_helper(self):
        """GUI 的 `_coverage_trace_text` 与 core 的 `coverage_trace_text` 输出逐字相同。"""
        from gacha_simulator.gui.worst_impact_panel import _coverage_trace_text

        kwargs = dict(alpha=0.05, n=1000, worst_resource=3060.0, pity_cost=14400.0)
        assert _coverage_trace_text(**kwargs) == coverage_trace_text(**kwargs)

    def test_gui_panel_does_not_reimplement_the_text(self):
        """**结构性**判据：GUI 侧的函数体里不得出现格式化（不自持第二份实现）。

        仅断言「输出相同」拦不住「两处各写一份、恰好今天一致」的形态（同型先例：
        缺陷 12 的两份 `infer_rarity`）。故本用例按 AST 看函数体（**跳过 docstring**，
        它在薄壳里会举例写出格式串）：薄壳必须调用 `coverage_trace_text(...)`，
        且函数体内不得出现任何 f-string（自持实现的标志）。
        """
        import ast
        import inspect
        import textwrap

        from gacha_simulator.gui import worst_impact_panel

        src = textwrap.dedent(inspect.getsource(worst_impact_panel._coverage_trace_text))
        fn = ast.parse(src).body[0]
        body = [n for n in fn.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str))]
        code = ast.Module(body=body, type_ignores=[])
        calls = [n for n in ast.walk(code)
                 if isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'coverage_trace_text']
        assert calls, f'GUI 薄壳未调用 coverage_trace_text：{src}'
        joined = [n for n in ast.walk(code) if isinstance(n, ast.JoinedStr)]
        assert not joined, f'GUI 侧出现自持实现的 f-string（口径将分叉）：{src}'

    def test_missing_items_are_omitted_not_placeholder(self):
        """缺项即略（不臆造未观测到的值）：只给 α 时输出只有 α 一段。"""
        assert coverage_trace_text(alpha=0.05) == 'α=0.05'
        assert coverage_trace_text() == ''
