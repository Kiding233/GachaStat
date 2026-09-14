<!-- META: P73 | module:应用打包 | status:designing | last:2026-08-05 -->

# P73 scipy依赖替换：混合策略与golden等价对照

> 日期：2026-08-05 | 状态：设计中
> 触发：用户调研「项目哪些地方依赖 scipy、可替代性如何」后确认全量替换方向。动机：scipy 利用率低（仅 9 个函数）、Windows spawn 页面文件风险、PyInstaller 打包体积难压

## 一、问题

scipy 是硬依赖（[pyproject.toml](pyproject.toml#L14) 声明 `scipy>=1.10`），但运行时只用到 9 个函数，全部是基础统计推断设施，分布在 4 个 core 文件：

| 文件 | 导入方式 | scipy 功能 |
|------|---------|-----------|
| [core/bootstrap.py](gacha_simulator/core/bootstrap.py#L12) | 顶层导入 | `scipy.stats.bootstrap`（BCa / percentile）、`scipy.stats.genpareto`（fit / rvs） |
| [core/evt_tail.py](gacha_simulator/core/evt_tail.py#L16) | 顶层导入 | `scipy.stats.genpareto.fit` |
| [core/vulnerability.py](gacha_simulator/core/vulnerability.py#L182) | 惰性导入 | `scipy.stats.norm.ppf`（Wilson CI） |
| [core/comparison_analyzer.py](gacha_simulator/core/comparison_analyzer.py#L52) | 惰性导入 | `skew` / `kurtosis` / `ks_2samp` / `mannwhitneyu` / `ttest_ind` |

持有 scipy 的三重成本：

1. **Windows spawn 内存风险**：multiprocessing 下每个 worker 进程 import `core` 会级联加载 scipy 大 DLL，4 个 worker 同时加载可触发「页面文件太小 / DLL load failed」。[core/__init__.py](gacha_simulator/core/__init__.py#L90) 已有惰性导入特判缓解，但 `bootstrap.py` / `evt_tail.py` 仍是顶层导入，在 spawn 关键路径上。
2. **PyInstaller 打包体积**：scipy 解压约 250MB，[GachaStat.spec](GachaStat.spec) 显式收集 4 个 scipy C 扩展，压缩困难。
3. **导入慢**：scipy 导入约 1-2 秒，冷启动成本。

另有两处非运行时引用：[tests/core/test_evt_tail.py](tests/core/test_evt_tail.py#L6) 用 `genpareto.rvs` 生成已知分布数据；[技术栈.md](docs/00-meta/技术栈.md#L9) 与 [about_dialog.py](gacha_simulator/gui/about_dialog.py#L86) 声明 scipy。

## 二、目标

替换完成后：

- `pyproject.toml` 不再声明 scipy，`pip check` 无未满足依赖
- 4 个 core 文件 grep 无 scipy 引用，`bootstrap.py` / `evt_tail.py` 移除顶层导入
- `GachaStat.spec` 无 scipy 扩展
- `tests/` 目录无 scipy import（含 `test_evt_tail.py` 的数据生成）
- **行为等价**：固定种子下 bootstrap CI、EVT VaR/CVaR、Wilson CI、检验 p 值与旧 scipy 版在对照容差内一致
- 技术栈.md、about_dialog.py 技术栈列表同步更新
- Windows spawn 下 worker 不再加载 scipy DLL

## 三、方案

### 已确认决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 实现策略 | 混合策略 | 易替换的重写（norm.ppf / skew / kurtosis / ttest / percentile / MWU），难的（BCa、GPD 拟合）参考 scipy 算法重写并配 scipy 参考对照 |
| GPD 拟合路线 | MLE 主 + PWM 兜底，切 PWM 时提示系统差异 | 行为等价为主；PWM（Hosking & Wallis 1987 闭式解）兜住 MLE 数值失败；PWM 与 scipy MLE 有系统差异，必须显式提示 |
| 验证机制 | scipy 参考对照 | 验证期 scipy 保留为参考实现，双实现对同一批固定种子数据对比，跑通后才移除 scipy。兜住自写漏考虑的风险 |

**关键约束**：scipy 的 `genpareto.fit` 是 `rv_continuous` 通用框架 `fit()` 方法的一部分，依赖 `_nnlf`、数值优化器、参数惩罚等框架代码，无法独立复制。故「难」档实际均为「参考算法重写 + 对照验证」，而非逐字搬运。

### 对照验证机制（贯穿全程）

每个替换点配一组**对照测试**（新实现 vs scipy，同数据同种子）：

- 验证期：scipy 保留，对照测试实时双跑
- 通过标准：统计量 / 参数 / CI 在设定容差内一致（容差分三级：1e-6 紧容差用于解析公式类，1e-3 用于数值迭代类，显著性结论一致用于假设检验类）
- 阶段四移除 scipy 时：对照测试转为 **golden 数值断言**（固化 scipy 输出为常量），对照测试本身删除或标 skip

### 阶段划分

**阶段一：统计基础替换（低难度，独立）**

新建 `core/stats_math.py`（纯 numpy 统计函数库）：

- `norm.ppf`（Wilson CI 用）→ Acklam 有理逼近，精度 1e-9；`norm.cdf` 用 `math.erfc`（标准库自带，`Φ(x) = 0.5·erfc(-x/√2)`）
- `skew` / `kurtosis`（`bias=False` 对应 Fisher 定义）→ numpy 三/四阶矩公式
- `ttest_ind`（Welch）→ 闭式公式 + t 分布 CDF（不完全 beta 函数连分数实现）
- `mannwhitneyu` → rankdata + 正态近似（含 tie 校正）
- `ks_2samp` → ECDF 最大距离统计量 + 自举 p 值（复用项目 Bootstrap 基础设施）

接入：`core/vulnerability.py`、`core/comparison_analyzer.py` 改引 stats_math。

**阶段二：GPD 拟合引擎（高风险，独立阶段）**

新建 `core/gpd_fit.py`，供 evt_tail 与 bootstrap 共用：

- 自写 MLE：负对数似然（浮点稳定写法，处理 `1 + ξy/σ` 为负与对数空间）+ 迭代求解，初值用矩估计
- PWM 兜底：Hosking & Wallis (1987) 闭式解，MLE 数值失败时启用
- 切 PWM 时 `logger.warning` + 结果带 `method='PWM'` 标记，调用方在结果 / 日志层提示系统差异
- Smith 正则性检查保留（ξ < -1 返回 None，沿用 [evt_tail.py](gacha_simulator/core/evt_tail.py#L44) 既有逻辑）
- GPD rvs 逆 CDF 抽样（供测试生成数据，替代 test_evt_tail.py 的 `genpareto.rvs`）

接入：`core/evt_tail.py` 的 `_fit_gpd` 改引 gpd_fit。

**阶段三：Bootstrap 引擎替换（高风险）**

[core/bootstrap.py](gacha_simulator/core/bootstrap.py)：

- `scipy.stats.bootstrap` 移除 → 手写：
  - percentile：纯 numpy（复用已有 `_percentile_ci`，[bootstrap.py:57](gacha_simulator/core/bootstrap.py#L57)）
  - BCa：jackknife 加速系数 + 偏差校正（Efron & Tibshirani 1993），约 40 行
- 内部 `genpareto.fit` / `rvs` → 阶段二 gpd_fit 引擎

**阶段四：依赖与打包清理（收尾）**

- `pyproject.toml` 移除 scipy 依赖
- `GachaStat.spec` 移除 4 个 scipy C 扩展
- `core/__init__.py`：移除 BootstrapEngine 惰性导入特判（scipy 消失后无大 DLL 级联，bootstrap 顶层导入 stats_math / gpd_fit，纯 numpy）
- `service/batch_simulator.py` 相关注释清理
- 技术栈.md、about_dialog.py 更新技术栈列表
- 测试改造：`test_evt_tail.py` 数据生成改自写 GPD rvs；`test_bootstrap.py` BCa 断言适配；对照测试转 golden 断言
- 全量 `pytest` + 固定种子 golden 回归（bootstrap CI / EVT VaR/CVaR / Wilson CI / 检验 p 值）

### 依赖与顺序

阶段一独立可先做；阶段二前置阶段三（bootstrap 引用 GPD 引擎）；阶段四依赖前三阶段全部完成。阶段一与阶段二可并行。

## 四、波及范围

**代码**

- 修改：`core/bootstrap.py`、`core/evt_tail.py`、`core/vulnerability.py`、`core/comparison_analyzer.py`、`core/__init__.py`
- 新建：`core/stats_math.py`、`core/gpd_fit.py`

**测试**

- 修改：`tests/core/test_bootstrap.py`、`tests/core/test_evt_tail.py`
- 新建：`tests/core/test_stats_math.py`、`tests/core/test_gpd_fit.py`、各替换点对照测试

**配置 / 打包 / 文档**

- `pyproject.toml`、`GachaStat.spec`、`docs/00-meta/技术栈.md`、`gui/about_dialog.py`、`service/batch_simulator.py`

**子系统波及**：Bootstrap引擎、分布估计、脆弱性分析、策略比较、应用打包、测试体系

## 五、风险

| 风险 | 缓解 |
|------|------|
| GPD MLE 数值不稳定（初值 / 收敛 / 奇异） | PWM 兜底 + scipy 参考对照；沿用 evt_tail 既有 try/except 容错结构 |
| BCa 手写与 scipy 实现细节差异 | 对照测试 + 固定种子 golden；容差分级（先 1e-4 后人工抽查） |
| KS p 值替代（自举）与 scipy 结果差异 | 对照验证显著性结论一致（拒绝 / 不拒绝一致），不要求逐位相等 |
| 切 PWM 时系统差异被静默吞掉 | 显式 warning + 结果 `method` 标记，日志可见 |
| test_evt_tail.py 仍依赖 scipy 生成数据 | 自写 GPD rvs（逆 CDF）随阶段二落地 |
| 移除声明后仍有间接 scipy 引入 | 阶段四 `pip check` + 全库 import 扫描验证 |
| 等价验证不彻底 | 每个替换点强制对照测试，通过后才进下一阶段 |

## 六、验收标准

- [ ] `pyproject.toml` 无 scipy；`pip check` 无未满足依赖
- [ ] 4 个 core 文件 grep 无 scipy；`bootstrap.py` / `evt_tail.py` 无顶层 scipy 导入
- [ ] `GachaStat.spec` 无 scipy 扩展
- [ ] `tests/` 目录 grep 无 scipy import
- [ ] 固定种子 golden 回归：bootstrap CI / EVT VaR/CVaR / Wilson CI / 检验 p 值在对照容差内与基线一致
- [ ] 全量 pytest 通过（H9 push 门控）
- [ ] 技术栈.md、about_dialog.py 已同步
- [ ] Windows 批量模拟正常跑通（spawn 路径无 scipy 加载）
