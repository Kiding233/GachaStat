"""T2：安全协议的拒绝规则单测。

形态一律是**构造期抛 `ValueError`**（§3.9 T2）——声明一个平台不接受的规格属调用方
编程错误，早失败优于「跑完发现读数不对」。

覆盖六条拒绝规则 + 一条豁免（决策 34）：

| 规则 | 拒绝条件 |
|---|---|
| 1 | `collector=False` 且 `n > 1000` |
| 4 | `collector=True` 且 `n > 1600` |
| 5 | 可用物理内存 < `max(2.0, workers × 0.75)` GB（`gui-qt` 按 `workers=1` 计并另加 0.5 GB） |
| D8 | `profile_count > 500`（per-worker） |
| D2.1 | `grain='function'` 且 `workers <= 1` |
| §3.3 | `grain='single'`（本期未实现） |

**本文件不依赖真实系统内存**：规则 5 的用例一律注入桩（§3.9 T2 的要求）。注意
`tests/benchmarks/conftest.py` 有一个 autouse 的「内存充足」注入，本文件内的注入
在其内层生效、退出后还原。
"""

import pytest

from benchmarks.perf.plan import (
    MEM_BASE_GB,
    MEM_GUI_QT_EXTRA_GB,
    MEM_PER_WORKER_GB,
    MemoryProbeUnavailable,
    N_MAX_NO_COLLECTOR,
    N_MAX_WITH_COLLECTOR,
    PROFILE_COUNT_MAX,
    SafetyRuleError,
    injected_memory_query,
    scale_issue,
)

AMPLE = 64.0


class TestRule1NoCollectorLimit:
    """规则 1：无收集器时 `n <= 1000`——**与规则 4 互不包含的独立上限**。"""

    def test_rejects_just_above_limit(self, make_plan):
        """用 `n = 1001` 构造，证明它能被**单独**拒绝（不是靠规则 4 兜住）。"""
        with pytest.raises(SafetyRuleError, match='规则 1'):
            make_plan(n=N_MAX_NO_COLLECTOR + 1, collector=False)

    def test_accepts_at_limit(self, make_plan):
        assert make_plan(n=N_MAX_NO_COLLECTOR, collector=False).n == N_MAX_NO_COLLECTOR

    def test_does_not_apply_with_collector(self, make_plan):
        """`collector=True` 且 `n = 1001` **放行**——两条规则互不包含的正面证明。"""
        assert make_plan(n=N_MAX_NO_COLLECTOR + 1, collector=True).collector is True


class TestRule4CollectorLimit:
    """规则 4：带收集器时 `n <= 1600`。"""

    def test_rejects_just_above_limit(self, make_plan):
        with pytest.raises(SafetyRuleError, match='规则 4'):
            make_plan(n=N_MAX_WITH_COLLECTOR + 1, collector=True)

    def test_accepts_at_limit(self, make_plan):
        assert make_plan(n=N_MAX_WITH_COLLECTOR, collector=True).n == N_MAX_WITH_COLLECTOR

    def test_limits_are_not_nested(self, make_plan):
        """规则 1 的拒绝集合不是规则 4 的真子集——`n=1001` 在两种申报下取向相反。"""
        with pytest.raises(SafetyRuleError):
            make_plan(n=N_MAX_NO_COLLECTOR + 1, collector=False)
        make_plan(n=N_MAX_NO_COLLECTOR + 1, collector=True)  # 不抛


class TestRule5Memory:
    """规则 5：`avail >= max(2.0, workers × 0.75)` GB，`gui-qt` 另加 0.5 GB。"""

    def test_requires_base_when_few_workers(self, make_plan):
        required = max(MEM_BASE_GB, 1 * MEM_PER_WORKER_GB)
        with injected_memory_query(lambda: required - 0.01):
            with pytest.raises(SafetyRuleError, match='规则 5'):
                make_plan(workers=1)

    def test_scales_with_workers(self, make_plan):
        required = 4 * MEM_PER_WORKER_GB
        assert required > MEM_BASE_GB
        with injected_memory_query(lambda: required - 0.01):
            with pytest.raises(SafetyRuleError, match='规则 5'):
                make_plan(workers=4)

    def test_accepts_at_threshold(self, make_plan):
        with injected_memory_query(lambda: 4 * MEM_PER_WORKER_GB):
            assert make_plan(workers=4).workers == 4

    def test_gui_qt_counts_as_one_worker_plus_extra(self, make_plan):
        """`gui-qt` 按 `workers=1` 计并另加 0.5 GB——故 8 worker 的 gui-qt 比 cli 宽松。"""
        required = max(MEM_BASE_GB, 1 * MEM_PER_WORKER_GB) + MEM_GUI_QT_EXTRA_GB
        with injected_memory_query(lambda: required - 0.01):
            with pytest.raises(SafetyRuleError):
                make_plan(workers=8, path='gui-qt')
        with injected_memory_query(lambda: required):
            assert make_plan(workers=8, path='gui-qt').path == 'gui-qt'

    def test_gui_qt_extra_is_real(self, make_plan):
        """同样的内存，cli 的 4 worker 被拒而 gui-qt 放行——证明那 0.5 GB 确实另计。

        取 `available` 落在 `[gui-qt 的下限, cli 的下限)` 内：cli 需
        `workers × 0.75 = 3.0`，gui-qt 需 `1 × 0.75 + 0.5 = 1.25 → 取底 2.0 + 0.5 = 2.5`。
        """
        cli_required = 4 * MEM_PER_WORKER_GB                     # 3.0
        gui_qt_required = max(MEM_BASE_GB, MEM_PER_WORKER_GB) + MEM_GUI_QT_EXTRA_GB   # 2.5
        assert gui_qt_required < cli_required
        available = (gui_qt_required + cli_required) / 2          # 落在两者之间
        with injected_memory_query(lambda: available):
            with pytest.raises(SafetyRuleError):
                make_plan(workers=4, path='cli')
            assert make_plan(workers=4, path='gui-qt').path == 'gui-qt'

    def test_unreadable_memory_is_rejected_not_skipped(self, make_plan):
        """缺 `psutil` 时**拒绝**而非静默跳过——内存阈值是防 OOM 的硬规则。"""
        def broken():
            raise MemoryProbeUnavailable('规则 5 需要 psutil：缺 psutil，请安装 [dev] extras')

        with injected_memory_query(broken):
            with pytest.raises(MemoryProbeUnavailable, match='psutil'):
                make_plan()

    def test_error_message_names_the_numbers(self, make_plan):
        with injected_memory_query(lambda: 1.0):
            with pytest.raises(SafetyRuleError) as excinfo:
                make_plan(workers=4)
        message = str(excinfo.value)
        assert '1.00' in message and '3.00' in message and 'workers=4' in message


class TestRuleD8ProfileCount:
    """D8：`profile_count > 500` 即拒绝（**per-worker 语义**）。"""

    def test_rejects_above_hard_cap(self, make_plan):
        with pytest.raises(SafetyRuleError, match='D8'):
            make_plan(profile_count=PROFILE_COUNT_MAX + 1)

    def test_accepts_at_hard_cap(self, make_plan):
        assert make_plan(profile_count=PROFILE_COUNT_MAX).profile_count == PROFILE_COUNT_MAX

    def test_applies_regardless_of_switch(self, make_plan):
        """开关关闭时也拒绝——越界值本身就是编程错误，不因「暂时用不上」而放行。"""
        with pytest.raises(SafetyRuleError):
            make_plan(profile_count=PROFILE_COUNT_MAX + 1, profile_enabled=False)

    def test_message_states_per_worker_semantics(self, make_plan):
        with pytest.raises(SafetyRuleError, match='per-worker'):
            make_plan(profile_count=PROFILE_COUNT_MAX + 1, workers=4)


class TestRuleD21FunctionGrain:
    """D2.1：`grain='function'` 且 `workers <= 1` 即拒绝。

    三条执行路径中只有 MPPool 路径经过 `_wk_run_single`，单进程内联与 `mp_failed`
    兜底路径的开闭窗口不生效、不产出任何 profile 文件。
    """

    @pytest.mark.parametrize('workers', [1])
    def test_rejects_single_worker(self, make_plan, workers):
        with pytest.raises(SafetyRuleError, match='D2.1'):
            make_plan(grain='function', workers=workers)

    def test_accepts_two_workers(self, make_plan):
        assert make_plan(grain='function', workers=2).grain == 'function'

    def test_other_grains_unaffected(self, make_plan):
        assert make_plan(grain='stage', workers=1).grain == 'stage'
        assert make_plan(grain='batch', workers=1).grain == 'batch'


class TestRuleSingleGrainNotImplemented:
    """§3.3：`grain='single'` 本期未实现，声明即拒绝。"""

    def test_rejected(self, make_plan):
        with pytest.raises(ValueError, match='本期未实现'):
            make_plan(grain='single')

    def test_message_points_at_the_way_out(self, make_plan):
        with pytest.raises(ValueError, match='采集通道'):
            make_plan(grain='single')

    def test_unknown_grain_also_rejected(self, make_plan):
        with pytest.raises(ValueError, match='必须是'):
            make_plan(grain='turbo')


class TestDecision34StartupExemption:
    """决策 34：`subject='startup'` 下规则 1 与规则 4 **不适用**，规则 5 与 D8 仍适用。

    理由：`startup` 下 `n` / `workers` / `chunksize` / `strategy_key` / `seed` 一律
    被忽略，规则 1 与 4 的对象不存在；而启动测量驱动的正是 `gui-qt` 冷进程，是四条
    路径中最吃内存的形态，故规则 5 与 D8 不因被忽略而豁免。
    """

    def test_rules_1_and_4_do_not_apply(self, make_plan):
        plan = make_plan(subject='startup', n=99_999, workers=64, path='gui-qt')
        assert plan.subject == 'startup'

    def test_rule_5_still_applies(self, make_plan):
        with injected_memory_query(lambda: 0.5):
            with pytest.raises(SafetyRuleError, match='规则 5'):
                make_plan(subject='startup', n=10, workers=1, path='gui-qt')

    def test_rule_d8_still_applies(self, make_plan):
        with pytest.raises(SafetyRuleError, match='D8'):
            make_plan(subject='startup', path='gui-qt', profile_count=PROFILE_COUNT_MAX + 1)

    def test_startup_memory_uses_one_worker(self, make_plan):
        """startup 按 `workers=1` 计（`n` / `workers` 被忽略），再按 gui-qt 另加 0.5。"""
        required = max(MEM_BASE_GB, MEM_PER_WORKER_GB) + MEM_GUI_QT_EXTRA_GB
        with injected_memory_query(lambda: required - 0.01):
            with pytest.raises(SafetyRuleError):
                make_plan(subject='startup', workers=1, path='gui-qt')
        with injected_memory_query(lambda: required):
            assert make_plan(subject='startup', workers=1, path='gui-qt').subject == 'startup'


class TestEveryRejectionIsAValueError:
    """§3.9 T2 的形态要求：一律 `ValueError`（`SafetyRuleError` 是其子类）。"""

    @pytest.mark.parametrize('overrides', [
        {'collector': False, 'n': N_MAX_NO_COLLECTOR + 1},
        {'collector': True, 'n': N_MAX_WITH_COLLECTOR + 1},
        {'profile_count': PROFILE_COUNT_MAX + 1},
        {'grain': 'function', 'workers': 1},
        {'grain': 'single'},
        {'grain': 'turbo'},
        {'n': 0},
        {'workers': 0},
        {'repeats': 0},
        {'profile_skip': -1},
        {'subject': 'nope'},
        {'path': 'wasm'},
    ])
    def test_value_error(self, make_plan, overrides):
        with pytest.raises(ValueError):
            make_plan(**overrides)


class TestScaleIssueForScripts:
    """`scale_issue()`：给 `scripts/` 下那些**不经 `Plan` 构造**就直接调
    `run_batch_parallel` 的脚本用的规模护栏（`04-问题.md` 的 P0）。

    那些脚本没有构造期校验这道防线，而 `workers` 取自核数（22 核 → 上限 16），按
    规则 5 需要 12 GB 可用内存，本机长期只有 2-5 GB。**阈值不在脚本里另立一份**——
    本函数内部仍走 `Plan.validate()`，故只有一处口径。
    """

    def test_accepts_a_small_scale(self):
        with injected_memory_query(lambda: 64.0):
            assert scale_issue(100, 2) is None

    def test_rejects_when_memory_is_short(self):
        with injected_memory_query(lambda: 3.0):
            issue = scale_issue(1000, 16)
        assert issue is not None and '规则 5' in issue

    def test_rejects_over_the_n_limit(self):
        """脚本传了 `on_result`（collector=True），故受规则 4 的 1600 管。"""
        with injected_memory_query(lambda: 64.0):
            assert scale_issue(N_MAX_WITH_COLLECTOR + 1, 2) is not None
            assert scale_issue(N_MAX_WITH_COLLECTOR, 2) is None

    def test_collector_flag_selects_the_rule(self):
        """`collector=False` 时受规则 1 的 1000 管——传错只影响该用哪条规则。"""
        with injected_memory_query(lambda: 64.0):
            assert scale_issue(N_MAX_NO_COLLECTOR + 1, 2, collector=False) is not None
            assert scale_issue(N_MAX_NO_COLLECTOR + 1, 2, collector=True) is None

    def test_gui_qt_path_carries_the_extra_half_gigabyte(self):
        """`gui-qt` 的特例要跟着走，否则 `profile_gui.py` 那道防线会偏松。"""
        with injected_memory_query(lambda: 2.4):
            assert scale_issue(100, 2, path='gui-qt') is not None
            assert scale_issue(100, 2, path='cli') is None

    def test_malformed_values_are_rejected_not_raised(self):
        """`n <= 0` 一类形态错误也算拒绝：本函数的契约是「返回成因」而非抛异常。"""
        with injected_memory_query(lambda: 64.0):
            assert scale_issue(0, 2) is not None

    def test_shares_the_single_source_of_truth(self):
        """反向自检：改动规则的唯一来源，本函数必须跟着变。"""
        import inspect

        from benchmarks.perf import plan as plan_module

        assert 'Plan(' in inspect.getsource(plan_module.scale_issue)
