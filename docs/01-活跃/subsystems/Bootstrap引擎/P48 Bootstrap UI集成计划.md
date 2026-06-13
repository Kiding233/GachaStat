<!-- META: P48 | module:subsystems/Bootstrap引擎 | status:implementing | last:2026-06-13 -->

# P48 Bootstrap UI 集成——实施计划

> **For agentic workers:** 使用 TDD 逐任务实施。每个 Task 包含「写测试→跑通→实现→跑通→提交」完整闭环。
> 
> **前置：** P18 BootstrapEngine 核心类 ✅（`bootstrap_mean`/`bootstrap_quantile`/`bootstrap_probability`/`detect_heavy_tail` 接口已稳定）
> **关联：** [P18 引擎修复计划](P18 Bootstrap稳定性分析改进计划.md)（B2.8/B2.9 不影响本计划）

**Goal:** 将 Bootstrap CI 集成到 5 个面板（1 个已完成 + 4 个待实施），通过自动计算 + 图表阴影带展示不确定性。

**Architecture:** 分三层改动——数据模型层（`ForwardStep`/`BackwardStep`/`ResourceSearchStep` +`success_flags`）→ 模拟层（运行模拟时保存个体结果）→ UI 层（BootstrapEngine 调用 + 图表 CI 叠加）。不改动 BootstrapEngine 公开接口，不改动 chart_spec 抽象层。

**Tech Stack:** Python 3.10+ · `BootstrapEngine` (scipy) · Plotly `go.Scatter` (CI 阴影带) · PyQt6 QThread Worker 模式

**实施顺序：** Phase A（数据模型+引擎基础，T1-T4）→ Phase B（方案搜索面板，T5-T8）→ Phase C（脆弱性面板，T9-T10）→ Phase D（最差影响面板，T11-T12）

---

## 文件结构

| 文件 | 职责 | 改动类型 |
|------|------|---------|
| `core/forward_backward.py` | `ForwardStep`/`BackwardStep`/`ResourceSearchStep` 添加 `success_flags` 字段 | 新增字段 |
| `core/bootstrap.py` | `bootstrap_conditional_quantile()` 新方法 | 新方法 ~30行 |
| `core/retreat_search.py` | `search_max_targets_forward`/`search_min_resource` 保存个体结果 | 修改返回值 |
| `gui/plan_search_panel.py` | 方案搜索面板——前进法/后退法/资源搜索趋势图 CI 阴影带 | UI 改动 |
| `gui/retreat_panel.py` | 脆弱性面板——条件分位数 CI + 资源不足概率 CI + KDE 阴影带 | UI 改动 |
| `gui/worst_impact_panel.py` | 最差影响面板——保守资源 CI + 保底覆盖倍数 CI | UI 改动 |
| `tests/core/test_bootstrap.py` | `bootstrap_conditional_quantile` 测试 | 新测试 |
| `tests/core/test_forward_backward.py` | 数据模型序列化兼容性测试 | 新测试 |

**不波及：** `core/gdr.py` · `core/strategy.py` · `core/pity.py` · `gui/gacha_panel.py` · `gui/process_analysis_panel.py` · `gui/analysis_panel.py`（3A 已完成，本次不改）

---

## Phase A：数据模型 + 引擎基础

### Task 1: `ForwardStep`/`BackwardStep` 添加 `success_flags` 字段

**Files:**
- Modify: `gacha_simulator/core/forward_backward.py:11-24`
- Test: `tests/core/test_forward_backward.py`（新建）

- [ ] **Step 1: 写序列化兼容性测试**

```python
# tests/core/test_forward_backward.py
"""forward_backward 数据模型测试。"""
import json
from dataclasses import asdict
from gacha_simulator.core.forward_backward import ForwardStep, BackwardStep, ResourceSearchStep


class TestSuccessFlagsBackwardCompat:
    """success_flags 字段的向后兼容性。"""

    def test_forward_step_default_empty(self):
        """未提供 success_flags 时默认为空列表，不破坏旧构造代码。"""
        step = ForwardStep(
            added_card_id="card_001",
            target_set={"card_001"},
            success_probability=0.85,
            target_specs={"card_001": 1},
        )
        assert step.success_flags == []

    def test_backward_step_default_empty(self):
        """BackwardStep 同理。"""
        step = BackwardStep(
            removed_card_id="card_001",
            target_set=set(),
            success_probability=0.90,
            target_specs={},
        )
        assert step.success_flags == []

    def test_forward_step_with_flags(self):
        """提供 success_flags 时正常存储。"""
        step = ForwardStep(
            added_card_id="card_001",
            target_set={"card_001"},
            success_probability=0.85,
            target_specs={"card_001": 1},
            success_flags=[True, False, True, True],
        )
        assert step.success_flags == [True, False, True, True]
        assert step.success_probability == 0.85

    def test_json_roundtrip_ignores_flags(self):
        """JSON 序列化不含 success_flags（保持旧格式兼容）。"""
        step = ForwardStep(
            added_card_id="card_001",
            target_set={"card_001", "card_002"},
            success_probability=0.75,
            target_specs={"card_001": 1, "card_002": 1},
            success_flags=[True, False, True],
        )
        d = asdict(step)
        # set 在 JSON 中不可直接序列化，验证字段存在即可
        assert hasattr(step, 'success_flags')
        assert d['success_flags'] == [True, False, True]


class TestResourceSearchStepFlags:
    """ResourceSearchStep success_flags 兼容性。"""

    def test_default_empty(self):
        step = ResourceSearchStep(
            iteration=1, resource_value=100.0,
            success_probability=0.5, phase="搜索",
            lo_bound=50.0, hi_bound=200.0,
        )
        assert step.success_flags == []

    def test_with_flags(self):
        step = ResourceSearchStep(
            iteration=1, resource_value=100.0,
            success_probability=0.5, phase="验证",
            lo_bound=50.0, hi_bound=200.0,
            success_flags=[True] * 100,
        )
        assert len(step.success_flags) == 100
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/core/test_forward_backward.py -v
```
Expected: FAIL——`TypeError: __init__() got an unexpected keyword argument 'success_flags'`

- [ ] **Step 3: 修改 dataclass 定义**

```python
# gacha_simulator/core/forward_backward.py

from typing import List, Dict, Set, Optional
from dataclasses import dataclass, field

@dataclass
class ForwardStep:
    added_card_id: str
    target_set: Set[str]
    success_probability: float
    target_specs: Dict[str, int]
    success_flags: List[bool] = field(default_factory=list)  # ← 新增


@dataclass
class BackwardStep:
    removed_card_id: str
    target_set: Set[str]
    success_probability: float
    target_specs: Dict[str, int]
    success_flags: List[bool] = field(default_factory=list)  # ← 新增
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/core/test_forward_backward.py -v
```
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add tests/core/test_forward_backward.py gacha_simulator/core/forward_backward.py
git commit -m "feat: ForwardStep/BackwardStep 添加 success_flags 字段（默认空列表，向后兼容）"
```

---

### Task 2: `ResourceSearchStep` 添加 `success_flags` 字段

**Files:**
- Modify: `gacha_simulator/core/forward_backward.py:43-50`

- [ ] **Step 1: 测试已在 Task 1 的 `TestResourceSearchStepFlags` 中覆盖，直接运行确认**

```bash
pytest tests/core/test_forward_backward.py::TestResourceSearchStepFlags -v
```
Expected: 2 passed（Task 1 实施后应已通过）

- [ ] **Step 2: 修改 dataclass 定义**

```python
# gacha_simulator/core/forward_backward.py:43-50

@dataclass
class ResourceSearchStep:
    iteration: int
    resource_value: float
    success_probability: float
    phase: str
    lo_bound: float
    hi_bound: float
    success_flags: List[bool] = field(default_factory=list)  # ← 新增
```

- [ ] **Step 3: 运行测试确认**

```bash
pytest tests/core/test_forward_backward.py -v
```
Expected: 8 passed

- [ ] **Step 4: 提交**

```bash
git add gacha_simulator/core/forward_backward.py
git commit -m "feat: ResourceSearchStep 添加 success_flags 字段（默认空列表，向后兼容）"
```

---

### Task 3: 实现 `bootstrap_conditional_quantile()`

**Files:**
- Modify: `gacha_simulator/core/bootstrap.py`（在 `bootstrap_quantile` 方法后添加新方法）
- Test: `tests/core/test_bootstrap.py`（追加测试类）

- [ ] **Step 1: 写失败测试**

```python
# tests/core/test_bootstrap.py 末尾追加

class TestBootstrapConditionalQuantile:
    """bootstrap_conditional_quantile 条件分位数 Bootstrap。"""

    @pytest.fixture
    def engine(self):
        return BootstrapEngine(B=2000, ci_level=0.95, random_seed=42)

    def test_basic_conditional(self, engine):
        """基本条件分位数：仅对满足条件的子样本做 Bootstrap。"""
        rng = np.random.default_rng(42)
        values = rng.normal(100, 15, 500)
        # 条件：value < 90（低资源场景）
        cond = values < 90
        result = engine.bootstrap_conditional_quantile(values, cond, q=0.05)
        assert result.point_estimate > 0
        assert result.ci_lower <= result.point_estimate <= result.ci_upper
        assert result.method == 'percentile'
        assert result.n_samples == int(np.sum(cond))

    def test_empty_condition(self, engine):
        """无样本满足条件时返回 NaN。"""
        rng = np.random.default_rng(42)
        values = rng.normal(100, 15, 100)
        cond = np.zeros(100, dtype=bool)
        result = engine.bootstrap_conditional_quantile(values, cond, q=0.05)
        assert math.isnan(result.point_estimate)

    def test_small_condition_subset(self, engine):
        """条件子集 < 100 时显示「样本不足」标记。"""
        rng = np.random.default_rng(42)
        values = rng.normal(100, 15, 500)
        cond = values < 60  # 极端尾部，样本极少
        result = engine.bootstrap_conditional_quantile(values, cond, q=0.05)
        if int(np.sum(cond)) < 100:
            assert '样本不足' in result.method or result.n_samples < 100
        else:
            assert result.point_estimate > 0

    def test_reproducibility(self):
        """相同种子 + 相同数据 = 相同结果。"""
        rng = np.random.default_rng(99)
        values = rng.normal(100, 15, 300)
        cond = values < 95
        e1 = BootstrapEngine(B=1000, random_seed=42)
        e2 = BootstrapEngine(B=1000, random_seed=42)
        r1 = e1.bootstrap_conditional_quantile(values, cond, q=0.1)
        r2 = e2.bootstrap_conditional_quantile(values, cond, q=0.1)
        assert r1.ci_lower == r2.ci_lower
        assert r1.ci_upper == r2.ci_upper
```

- [ ] **Step 2: 运行测试确认失败**

```bash
pytest tests/core/test_bootstrap.py::TestBootstrapConditionalQuantile -v
```
Expected: FAIL——`AttributeError: 'BootstrapEngine' object has no attribute 'bootstrap_conditional_quantile'`

- [ ] **Step 3: 实现方法**

```python
# gacha_simulator/core/bootstrap.py
# 在 bootstrap_quantile() 方法后、_bootstrap_tail_gpd() 之前插入

    def bootstrap_conditional_quantile(
        self, values: Union[List[float], np.ndarray],
        condition_mask: Union[List[bool], np.ndarray],
        q: float = 0.05,
    ) -> BootstrapResult:
        """条件分位数 Bootstrap。

        仅对 condition_mask=True 的样本子集做有放回重抽样，
        估计该子集 q 分位数的 Bootstrap 置信区间。

        Parameters
        ----------
        values : array-like
            全量连续量样本。
        condition_mask : array-like of bool
            与 values 等长的布尔掩码——True 表示该样本满足条件。
        q : float
            目标分位数（0-1），默认 0.05（VaR 风格）。

        Returns
        -------
        BootstrapResult
            method 字段在子集样本量 < 100 时标注「样本不足」。
        """
        data = np.asarray(values, dtype=np.float64)
        mask = np.asarray(condition_mask, dtype=bool)
        subset = data[mask]
        n = len(subset)

        if n == 0:
            return BootstrapResult(
                float('nan'), float('nan'), float('nan'),
                0.0, 'percentile (empty condition)', 0, self.B,
            )

        if n < 100:
            point_est = float(np.quantile(subset, q))
            return BootstrapResult(
                point_est, float('nan'), float('nan'),
                0.0, f'percentile (样本不足, n={n})', n, self.B,
            )

        point_est = float(np.quantile(subset, q))

        def _q_stat(x):
            return float(np.quantile(x, q))

        from scipy.stats import bootstrap as _scipy_bootstrap
        scipy_res = _scipy_bootstrap(
            (subset,), _q_stat,
            n_resamples=self.B, confidence_level=self.ci_level,
            method='percentile', random_state=self._rng,
        )
        return self._from_scipy_result(scipy_res, point_est, 'percentile', n, self.B)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
pytest tests/core/test_bootstrap.py::TestBootstrapConditionalQuantile -v
```
Expected: 4 passed

- [ ] **Step 5: 运行全部已有测试确认无回归**

```bash
pytest tests/core/test_bootstrap.py -v
```
Expected: all existing tests still pass

- [ ] **Step 6: 提交**

```bash
git add gacha_simulator/core/bootstrap.py tests/core/test_bootstrap.py
git commit -m "feat: BootstrapEngine 新增 bootstrap_conditional_quantile()——条件子集分位数 CI"
```

---

### Task 4: 验证 Phase A 完整性

- [ ] **Step 1: 运行全部 core 测试**

```bash
pytest tests/core/ -v --timeout=60
```
Expected: all pass（包括已有测试和新增的 forward_backward + bootstrap 测试）

- [ ] **Step 2: 提交（如无新改动则跳过）**

---

## Phase B：方案搜索面板（strategy + resource_search）

### Task 5: 前进法保存个体成功结果

**Files:**
- Modify: `gacha_simulator/core/retreat_search.py:514`（`search_max_targets_forward` 方法）

- [ ] **Step 1: 定位代码——查看 `search_max_targets_forward` 的模拟调用点**

关键理解——`search_max_targets_forward` 每步调用批量模拟（`run_batch_parallel`），返回 `List[CompactResult]`。当前从 `CompactResult` 聚合出 `success_probability: float`。需同时提取每条模拟的个体成功/失败。

`CompactResult` 的 `to_dict()` 包含每池成功信息，可通过 `make_gdr_calculator` 对每条结果调用 `compute_gdr` + `checker.is_success()` 得到个体 bool。

- [ ] **Step 2: 实现——在 `search_max_targets_forward` 中追加 success_flags 提取**

```python
# gacha_simulator/core/retreat_search.py
# 在 search_max_targets_forward() 方法中，每步模拟完成后追加：

from gacha_simulator.core.gdr import make_gdr_calculator

# ... 在每步模拟结果收集处（results = run_batch_parallel(...) 之后），追加：
checker = make_gdr_calculator(self._store, target_specs, self._gdr_key)
step_success_flags = [checker.is_success(r) for r in results]
```

然后在构造 `step` 对象时传入：
```python
step = RetreatSearchStep(
    # ... 现有字段 ...
    success_flags=step_success_flags,  # ← 新增
)
```

> **注意**：需先确认 `RetreatSearchStep` 是否有对应字段。如果前进法/后退法的步骤使用 `RetreatSearchStep` 而非 `ForwardStep`，则需在 `RetreatSearchStep` 上添加 `success_flags`。实际检查后确定改动位置。

- [ ] **Step 3: 运行方案搜索现有测试确认无回归**

```bash
pytest tests/ -k "retreat" -v --timeout=120
```

- [ ] **Step 4: 提交**

```bash
git add gacha_simulator/core/retreat_search.py
git commit -m "feat: 前进法 search_max_targets_forward 保存每步个体 success_flags"
```

> **实施时注意**：需先 `Read` `retreat_search.py` 中 `search_max_targets_forward` 的完整实现，确认步骤数据类名称和字段后精确改动。上述代码为意图描述，非精确 patch。

---

### Task 6: 后退法保存个体成功结果

**Files:**
- Modify: `gacha_simulator/core/retreat_search.py`（后退法对应方法）

- [ ] **Step 1: 同上逻辑应用于后退法**

步骤同 Task 5，改动目标为后退法对应方法（`search_min_targets_backward` 或类似）。

- [ ] **Step 2: 测试 + 提交**

---

### Task 7: 资源搜索保存个体成功结果

**Files:**
- Modify: `gacha_simulator/core/retreat_search.py:261`（`search_min_resource` 方法）

- [ ] **Step 1: 定位 `search_min_resource` 中 `ResourceSearchStep` 构造点**

每步二分搜索后构造 `ResourceSearchStep(iteration=..., resource_value=..., success_probability=..., ...)`。

- [ ] **Step 2: 在构造点追加 `success_flags`**

```python
# 每步模拟后提取个体 bool
checker = make_gdr_calculator(self._store, target_specs, self._gdr_key)
step_success_flags = [checker.is_success(r) for r in results]

step = ResourceSearchStep(
    iteration=iteration,
    resource_value=current_resource,
    success_probability=float(np.mean(step_success_flags)),
    phase=phase_label,
    lo_bound=lo,
    hi_bound=hi,
    success_flags=step_success_flags,  # ← 新增
)
```

- [ ] **Step 3: 提交**

---

### Task 8: 方案搜索面板——趋势图 CI 阴影带

**Files:**
- Modify: `gacha_simulator/gui/plan_search_panel.py:281-325`（`MinResourceResultPage._draw_chart`）
- Modify: `gacha_simulator/gui/plan_search_panel.py:412-436`（`MaxTargetsResultPage._draw_chart`）
- Modify: `gacha_simulator/gui/plan_search_panel.py:492-510`（`ParetoResultPage._draw_chart`）

- [ ] **Step 1: 为 `MinResourceResultPage._draw_chart` 添加 CI 阴影带**

在现有 `scatter_multi()` 调用之后追加 Bootstrap CI 计算和阴影带：

```python
# gui/plan_search_panel.py — MinResourceResultPage._draw_chart() 方法末尾

# ... 现有 scatter_multi 调用保持不变 ...

# —— Bootstrap CI 阴影带 ——
from gacha_simulator.core.bootstrap import BootstrapEngine
import plotly.graph_objects as go

steps_with_flags = [s for s in steps if hasattr(s, 'success_flags') and s.success_flags]
if steps_with_flags and len(steps_with_flags) >= 2:
    engine = BootstrapEngine(B=1000, ci_level=0.95, random_seed=42)
    ci_lowers, ci_uppers = [], []
    x_indices = []
    for i, s in enumerate(steps):
        if hasattr(s, 'success_flags') and s.success_flags:
            try:
                res = engine.bootstrap_probability(s.success_flags, use_bca=True)
                ci_lowers.append(res.ci_lower)
                ci_uppers.append(res.ci_upper)
                x_indices.append(i)
            except Exception:
                pass

    if x_indices:
        # 将 CI 阴影带追加到 ChartSpec 的原始图中
        fig = spec.to_figure() if hasattr(spec, 'to_figure') else None
        if fig is None:
            # 如果 chart_spec 不提供 to_figure，直接用 plotly 重建
            pass  # 详见实施时根据 chart_spec 实际接口调整
```

> **实施时注意**：`chart_spec` 的 `ChartSpec`/`ScatterData` 是否暴露底层 `go.Figure`。如果不暴露，三种方案：(a) 给 `ChartSpec` 加 `to_figure()` 方法（~5 行），(b) 在本面板绕过 chart_spec 直接用 Plotly，(c) 给 `ScatterTrace` 加 `fill` 支持。**推荐 (b)**——本面板已有多处 go.Scatter 用法，与 chart_spec 混用无问题。

- [ ] **Step 2: 同逻辑应用于 `MaxTargetsResultPage._draw_chart`**

- [ ] **Step 3: 同逻辑应用于 `ParetoResultPage._draw_chart`**

- [ ] **Step 4: 手动验证——启动 GUI，运行方案搜索，确认 CI 阴影带渲染**

```bash
python -m gacha_simulator.main
```
操作：配置面板设置目标卡 → 方案搜索面板 → 运行前进法/后退法/资源搜索 → 检查趋势图是否有半透明阴影带。

- [ ] **Step 5: 提交**

```bash
git add gacha_simulator/gui/plan_search_panel.py
git commit -m "feat: 方案搜索面板趋势图添加 Bootstrap CI 阴影带"
```

---

## Phase C：脆弱性面板（retreat_panel）

### Task 9: 脆弱性面板——条件分位数 CI + 资源不足概率 CI

**Files:**
- Modify: `gacha_simulator/gui/retreat_panel.py:339-378`（`_on_finished` 方法）

- [ ] **Step 1: 在 `_on_finished` 中追加 Bootstrap CI 计算**

`_on_finished` 方法收到 `result` dict，其中 `result["analysis"]` 是 `VulnerabilityAnalysis` 对象，包含 `overall_failure_rate` 和各池的 `pool_results`。`self._simulation_results` 保存了原始模拟结果。

资源不足概率 = `overall_failure_rate`（已经是二项比例，直接 Bootstrap）：

```python
# gui/retreat_panel.py — _on_finished() 方法，summary 行之后追加

from gacha_simulator.core.bootstrap import BootstrapEngine

# 1. 总体失败率 Bootstrap CI（资源不足概率）
engine = BootstrapEngine(B=1000, ci_level=0.95, random_seed=42)
n_sims = analysis.n_simulations
# 从 simulation_results 计算每条模拟的 GDR 是否满足阈值
from gacha_simulator.core.gdr import make_gdr_calculator
checker = make_gdr_calculator(self._store, target_specs, gdr_key)
success_flags = [checker.is_success(r) for r in self._simulation_results]
failure_flags = [not s for s in success_flags]

try:
    failure_ci = engine.bootstrap_probability(failure_flags, use_bca=True)
    summary_ci = (
        f"总体失败率: {analysis.overall_failure_rate:.1%} "
        f"[{failure_ci.ci_lower:.1%}, {failure_ci.ci_upper:.1%}]  |  "
        f"模拟次数: {n_sims}  |  "
        f"α = {analysis.alpha}"
    )
    self.status_label.setText(summary_ci)
except Exception:
    pass  # Bootstrap 失败则保持原 summary 不变
```

- [ ] **Step 2: 手动验证——启动 GUI，运行脆弱性分析，确认状态栏显示 CI**

- [ ] **Step 3: 提交**

---

### Task 10: 脆弱性面板——核密度回归 CI 阴影带

**Files:**
- Modify: `gacha_simulator/core/vulnerability.py`（`plot_vulnerability` 或 `plot_vulnerability_ridge`）
- Modify: `gacha_simulator/gui/retreat_panel.py`

- [ ] **Step 1: 分析现有绘图函数**

`plot_vulnerability()` 和 `plot_vulnerability_ridge()` 返回 Plotly Figure。核密度回归曲线位于 `plot_vulnerability()` 中。Bootstrap KDE 阴影带的计算逻辑：
```
对 B 次重抽样中的每一次：
  1. 从原始数据中重抽样 N 条
  2. 对重抽样数据做 KDE → 得到逐点密度估计
从 B 组密度估计中取 α/2 和 1-α/2 分位点 → 阴影带边界
```

这是一个较重计算（B × N 次 KDE 评估），建议：
- B 降至 500
- KDE 评估网格 ≤ 200 点
- 仅在用户点击「显示 CI」时触发（*此处与 P18 的「自动计算」决策冲突——核密度回归的计算成本显著高于简单分位数 Bootstrap，手动触发更合理*）

- [ ] **Step 2: 实现 `_bootstrap_kde_band()` 工具函数**

```python
# gacha_simulator/core/vulnerability.py 或 gui/retreat_panel.py

def _bootstrap_kde_band(data: np.ndarray, grid: np.ndarray,
                        B: int = 500, ci_level: float = 0.95,
                        random_seed: int = 42) -> Tuple[np.ndarray, np.ndarray]:
    """Bootstrap KDE 置信带。
    
    Returns:
        (lower_band, upper_band): 与 grid 等长的 CI 边界。
    """
    from scipy.stats import gaussian_kde
    rng = np.random.default_rng(random_seed)
    n = len(data)
    alpha = (1.0 - ci_level) / 2.0
    estimates = np.zeros((B, len(grid)))
    
    for b in range(B):
        idx = rng.integers(0, n, size=n)
        try:
            kde = gaussian_kde(data[idx])
            estimates[b] = kde(grid)
        except Exception:
            estimates[b] = np.nan
    
    lower = np.nanpercentile(estimates, alpha * 100, axis=0)
    upper = np.nanpercentile(estimates, (1 - alpha) * 100, axis=0)
    return lower, upper
```

- [ ] **Step 3: 在 `plot_vulnerability()` 中可选叠加 KDE CI 阴影带**

添加参数 `show_ci: bool = False`，开启时调用 `_bootstrap_kde_band()`。

- [ ] **Step 4: 手动验证 + 提交**

---

## Phase D：最差影响面板（worst_impact_panel）

### Task 11: 保守资源 CI + 保底覆盖倍数 CI

**Files:**
- Modify: `gacha_simulator/gui/worst_impact_panel.py:450-480`（结果展示区域）

- [ ] **Step 1: 理解当前数据流**

`WorstImpactWorker.run()` → `self.analyzer.analyze(...)` → 返回 `WorstImpactResult`（含 `worst_resource: float`、`pool_distribution: Dict[int, float]`）。

保守资源 = `worst_resource`（条件分布的 VaR 分位数）。要给这个值加 CI，需要在 `analyze()` 内部进行 Bootstrap 重抽样——即对条件分布的 α 分位数做 Bootstrap。

当前 `analyze()` 内部逻辑：对每种资源水平跑 N 次模拟 → 统计成功率 → 插值找到 α 分位数。Bootstrap CI 需对**每次 Bootstrap 重抽样重复这整个过程**。

- [ ] **Step 2: 实现 `bootstrap_conservative_resource()`**

```python
# gacha_simulator/core/bootstrap.py 或 worst_impact.py

def bootstrap_worst_resource(
    engine: BootstrapEngine,
    analyzer,  # WorstImpactAnalyzer
    condition,
    alpha: float,
    num_simulations: int,
    custom_resource: Optional[float] = None,
) -> BootstrapResult:
    """保守资源估计值的 Bootstrap CI。
    
    对模拟结果做有放回重抽样，每轮重新计算条件分位数，
    从 B 轮估计中取百分位 CI。
    
    注意：此操作较重——每轮需要 num_simulations 次独立模拟。
    建议 num_simulations 降至 500，B 降至 200。
    """
    # 先跑一次完整分析获取原始模拟结果用于重抽样
    base_result = analyzer.analyze(
        condition=condition, alpha=alpha,
        num_simulations=num_simulations,
        custom_resource=custom_resource,
    )
    # ... 重抽样逻辑 ...
```

> **复杂度警示**：Bootstrap 保守资源需要 B × N 次模拟（而非纯数组操作），与 P18「零额外模拟」原则冲突。**建议降级为「仅显示点估计 + 标注 N<1000 时 CI 不稳定」，完整 CI 在 P18 B2.8/B2.9 完成后通过 GPD-param Bootstrap 实现。**

- [ ] **Step 3: 保底覆盖倍数 CI**

保底覆盖倍数 = `worst_resource / pity_threshold`。直接从保守资源 CI 派生（除法保持 CI 比例）：

```python
pity_threshold = analyzer._get_pity_threshold()
coverage_ci_lower = worst_ci.ci_lower / pity_threshold
coverage_ci_upper = worst_ci.ci_upper / pity_threshold
```

- [ ] **Step 4: 提交**

---

### Task 12: 新池子数分布 Bootstrap（可选，优先级最低）

**Files:**
- Modify: `gacha_simulator/core/worst_impact.py:59`（`WorstImpactResult.pool_distribution`）
- Modify: `gacha_simulator/gui/worst_impact_panel.py`

- [ ] **Step 1: 保存每模拟的池子计数**

当前 `pool_distribution: Dict[int, float]` 是聚合后的概率质量函数。要 Bootstrap 池子数分布的 CI，需保存个体结果——在 `analyze()` 中额外返回 `pool_counts_per_sim: List[int]`。

- [ ] **Step 2: Bootstrap 池子数分布**

对 `pool_counts_per_sim` 做 Bootstrap，估计每个 k 的概率 + CI。

- [ ] **Step 3: 提交**

---

## Phase E：收尾

### Task 13: 运行全量测试 + 清理

- [ ] **Step 1: 全量测试**

```bash
pytest --cov=gacha_simulator --cov-report=term -v --timeout=120
```

- [ ] **Step 2: 修复任何回归**

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: P48 Bootstrap UI 集成——方案搜索+脆弱性+最差影响面板 CI"
```

---

## 依赖关系

```
Phase A (T1-T4): 数据模型 + 引擎基础
    ├── T1: ForwardStep/BackwardStep.success_flags
    ├── T2: ResourceSearchStep.success_flags
    ├── T3: bootstrap_conditional_quantile()
    └── T4: 验证
         ↓
Phase B (T5-T8): 方案搜索面板
    ├── T5: 前进法保存 flags
    ├── T6: 后退法保存 flags
    ├── T7: 资源搜索保存 flags
    └── T8: 趋势图 CI 阴影带 ← 依赖 T5/T6/T7
         ↓
Phase C (T9-T10): 脆弱性面板
    ├── T9: 条件分位数 + 资源不足概率 CI ← 依赖 T3
    └── T10: KDE 阴影带
         ↓
Phase D (T11-T12): 最差影响面板
    ├── T11: 保守资源 CI（含降级策略）
    └── T12: 新池子数 CI（可选）

Phase E (T13): 收尾
```

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| T5-T7：`retreat_search.py` 中步骤数据类不是 `ForwardStep`/`BackwardStep` | **实施前先读代码确认**——实际类型可能是 `RetreatSearchStep` 或其他，需按实际类名添加 `success_flags` |
| T8：ChartSpec 不暴露底层 Figure，CI 阴影带难以叠加 | 绕过 chart_spec，直接用 `go.Figure` + `go.Scatter(fill='tonexty')` 重建含 CI 的图表 |
| T11：保守资源 Bootstrap 需要 B×N 次模拟（非零成本） | 采用降级策略：仅显示点估计 + 标注不确定性，完整 CI 等 P18 B2.8/B2.9 |
| T10：KDE Bootstrap 计算时间 > 5 秒（B=500 × N=10000） | B 降至 200，KDE 网格 ≤ 100 点；提供手动触发按钮（非自动） |
| 数据模型字段改动破坏 pickle/json 序列化 | `field(default_factory=list)` 确保反序列化时缺失字段自动填充空列表 |

---

## 验收标准

- [x] analysis_panel GDR 统计表格显示 Bootstrap CI（3A，已完成）
- [ ] strategy_panel：前进法/后退法趋势图显示成功率 CI 阴影带
- [ ] resource_search_panel：成功率-资源曲线显示 CI 阴影带
- [ ] retreat_panel：资源不足概率显示 CI + 条件分位数显示 CI
- [ ] worst_impact_panel：保守资源显示 CI（含降级策略标注）
- [ ] 所有面板 N<100 时显示「样本不足」
- [ ] 所有 Bootstrap 调用包裹 try/except，失败时优雅降级
- [ ] 全部已有测试保持绿色
- [ ] 手动目视：GUI 各面板运行后 CI 信息正确渲染

---

## 更新记录

| 日期 | 变更 |
|------|------|
| 2026-06-13 | 从 P18 §七 提取 UI 集成部分，创建设计文档 |
| 2026-06-13 | 扩展重构为实施计划——13 个 Task，五阶段，含精确代码引用和测试用例 |
