# peer-review — P83 性能分析平台

> 审查日期：2026-09-21 | 流水线：plan-review 五阶段对抗验证
> 计划文件：`subsystems/性能分析/P83 性能分析平台——多路径测量·基线回归·现场剖析.md`
> 结论：⚠️ **有条件通过** —— 阶段 2 与阶段 3 均以熔断/撞上限收场；**阶段 4 检出的 10 条代码级断裂已在本轮全部修复**；剩余 **16 处 `⚠ 待人工裁决`**（含 2 条 GATE-CAP 未修项）需人工处置

---

## 流水线执行

| 阶段 | 结果 | 产出 |
|------|:---:|------|
| 0 分类 | ✅ | complex / evolutionary / 8 维度 / 34 预估缺陷 |
| 1 影响面扇出 | ✅ | 8 维度并行，**54 条发现**（9 条「高」、8 条阻断） |
| 2 对抗循环 | 🛑 | 6 轮 Find→Fix→Verify，**熔断**（`no_new_issues` 始终为 False，未满足「连续 2 轮 dry」），遗留 `ISSUE-104` |
| 3 可行性门控 | 🛑 | 6 项检查 × 6 轮，**撞硬上限**（`maxGateTotalRuns=6`），非 PASS 项 4 条 |
| 4 代码审计 | ⚠️→✅ | `HAS_BREAKS` —— 检出 **10 条断裂**（其中 5 条计入阻塞），**已由 `audit-fixer` 本轮全部修复** |
| 5 矩阵同步 | ✅ | 计划元数据与 `模块状态矩阵.md` 已比对同步 |

**运行成本：** 52 agents / 0 错误 / 5,791,359 subagent tokens / 1,666 tool uses / 约 4 小时 20 分。

**计划体量变化：** `791 行 / 71 KB` → **`1693 行 / 272 KB`**；子任务 `34 项 / 27.0 人时` → **`43 项 / 34.5 人时`**（0.5h 项 17 + 1.0h 项 26）。

---

## 一、阶段 4 代码审计：10 条断裂与处置（本次审查最有价值的产出）

阶段 4 与前三阶段的检查面**不同**：前两阶段核「计划自不自洽」「引用对不对得上」，阶段 4 核**「照着做会发生什么」**——沿数据流走 14 个环节，把 43 个子任务逐项映射到代码位置（`grep` 级核实）。检出的断裂全部是前三阶段漏掉的。

### 修复归类（`audit-fixer` 已全部处置，就地标注 `<!-- REVIEW-R1-FIX: AUDIT-BREAK-N -->`）

**A 类：接口归属缺失**

| 断裂 | 内容 |
|---|---|
| `AUDIT-BREAK-1` | `benchmarks/perf/__main__.py` 的唯一输入 `--plan <plan.json>` **无任何子任务承担其格式定义与读取**（`1b` 未给 `Plan.to_dict`/`from_dict`）→ G1 起点断链。**修复：** `1b` 补 `Plan.to_dict`/`from_dict` |
| `AUDIT-BREAK-2`（含 GATE-CAP-1 同源） | `1c` 的 `RunResult`/`EnvFingerprint` 字段表与 `02-实施.md` §4 不一致（缺 `repeats`/`wall_median`/`wall_samples`/`repeats_downgraded`/`return_compact`/`qt_qpa_platform`），不改则按旧形状实施会触发 `None < 3` 的 TypeError。**修复：** 定死「`1c` 的字段表为唯一真值源」，把 §4 逐项同步列入 `1a-2` 交付面，配 T1 用例与 §七 验收条 |
| `AUDIT-BREAK-6` / `-7` | §四 波及范围只登记 `gui/main_window.py`，而 10 个 `ChartWebView` 实为分落 6 个面板文件。**修复：** 按 8 文件登记 |

**B 类：数据流断链**

| 断裂 | 内容 |
|---|---|
| `AUDIT-BREAK-3` | `6c`/`6d` 要求「调用 `run_batch_parallel` 的进程」扫 `<profile_dir>/<run_id>/` 合并 pstats 并填 `RunResult.functions`，但 `RunResult` 由适配器构造、`--perf-json` 只载 stage 计时与 `packet_bytes`，且 **`run_id` 在 CLI 子进程内生成无回传路径**，与 `D3`「`run_id` 由父进程生成」自相矛盾。**修复：** `--perf-json` 载荷补 `run_id`/`functions`，接通 cli 的 function 档 |
| `AUDIT-BREAK-4` | `2f` 的修复面不足：`scripts/profile_gui.py` 实际有**四层**断裂 |
| `AUDIT-BREAK-5` | 判为 `-4` 的下游扩散，不单独计入阻塞数 |
| `AUDIT-BREAK-8` / `-9`（各两处落点） | 第 8 段就绪聚合源 |
| `AUDIT-BREAK-10` | 经查证**已闭合**（`main_window.py:343` 首行即 `isinstance(result_bundle, dict)` 守卫） |

### `2f` 那条值得单独记（它证伪了作者的一处实测结论）

`scripts/profile_gui.py` 的实际失效点有**四层**，而计划原只覆盖第一层：

| 位置 | 错误 | 计划原覆盖 |
|---|---|:---:|
| `:43-44` | `from gacha_simulator.gui.batch_simulator import …` 指向 **0 字节文件** → `ImportError` | ✅ |
| `:87` | 读 `store.strategy_name`，而 `ConfigStore` 该属性已随 P69 改名为 `strategy_key` → `AttributeError` | ❌ |
| `:87` / `:113` | 以 `strategy_name=` 调用形参为 `strategy_key` 的 `run_batch_parallel` → `TypeError` | ❌ |
| — | 回写 `04-问题.md` P1（原条目未覆盖 `:87`/`:113`） | ❌ |

> **根因注记：** 计划作者在编写期**实测**该脚本时只观察到 `ImportError`——因为它在导入语句处即崩溃，**后三层错误没有机会暴露**。审查通过静态核对把四层全部找出。这是「实测通过不能替代独立审查」的直接实证。

**工时影响：** `2f` 由 0.5h 上调为 1.0h，§6.0 汇总随之订正。

### 三处冲突：`audit-fixer` 采保守解并标 `⚠ 待人工裁决`

1. **第 8 段就绪聚合源的实现方案**——保守解 = 8 文件公开访问器链（`chart_webview.py` 加只读 `is_loaded()` + 6 面板各自 `charts_ready()` + `main_window.py` 求与），无新全局状态但**触达 6 个产品面板**；备选解 = `chart_webview.py` 内维护类级 `WeakSet` 注册表，只改 2 文件但**给库引入进程级全局状态**。采保守解（决策 63）
2. **`02-实施.md` §4 未直接回写**——任务限定「修改计划文件」，改 `02-实施.md` 超授权；改为列入 `1a-2` 交付面
3. **`2f` 工时的 0.5 人时增量**是否接受

---

## 二、阶段 4 附带检出的非阻塞项（3 条）

1. §3.5 称「gui-qt / webui 的 `packet_bytes` 天然小于 cli 路径」并要求 `RunResult` 记 `return_compact`，与 `collect_perf` 仅由 cli `--perf-json` 开闸矛盾——**空值断裂**
2. `RunResult.return_compact` 与 `EnvFingerprint.QT_QPA_PLATFORM` 在 `1c` 字段表与 §8.1 group B 无归属
3. `from_dict` 的显式 keyword 字段表**无 `profile_*` 四字段**，使 cProfile 在 `worst_impact` 路径**静默不开**

### 结构性放行（值得单列）

**H7 的 `_run_ruff` 只跑 `ruff check gacha_simulator/`，新增的 `benchmarks/` 与 `tests/benchmarks/` 两棵树全程无静态检查。**

这与本计划反复强调的 **G5「平台自身不再腐烂」构成反讽**：为防「没人看着它烂掉」而设计的机制，落在了**唯一一道自动检查的射程之外**。

---

## 三、阶段 1 影响面：8 维度 54 条

### 阻断级（8 条，已在阶段 2 全部修复）

`PERF-1` / `P83-CFG-1`（同一事实两处独立确认）：H7 目录边界门控硬阻，`benchmarks/` 与 `.gitignore` 全部 `BLOCK`；`PAR-1`：`_wk_run_single` 非唯一执行路径（`max_workers<=1` 进程内 `:422`、`mp_failed` 兜底 `:543` 均直接调 `_run_single`）；`CLI-1`/`CLI-2`：cli 的 stage 六段与三元组字节数均无采集通道；`GUI-01`：启动测量第 1/3/5 段无外部可观测口径；`GUI-02`：gui-qt 无「分发完成」边界且失败路径不发信号 → 永久阻塞；`WEBUI-1`：`5a` 点名驱动 `webui` 私有链。

### 高/中风险（节选）

- `GUI-03`：「阶段口径对齐 `profile_gui.py` 的 A/B/C 三段」不成立——该脚本的 B6 是**用新建面板直接调 `update_results` 的替身**，完全绕开 `MainWindow.on_simulation_finished`；真实 GUI 分发把同样 4 个面板分了**两次**
- `PAR-2`：`profile_count` 是 **per-worker** 语义，而 `D5` 按全局 `K/N` 论证摊薄；N=1000/W=18/K=50 时约 900/1000 次被插桩，与「摊薄」相反
- `PAR-3`/`CLI-5`：`D1` 用 `env` 字段做触发载体，但三条真实路径的 `env` 均由产品代码内部构造，外部适配器拿不到
- `P83-PERF-01`：`§3.13` 受控注入的规模与它自己的可检出阈值数量级打架（`w=4` 下预期比值约 1.04，落在 FAIL 条件「≤1.05」之下）——**整份计划的存续曾被一个与平台能力无关的注入量级决定**

### 被反复命中的同一类缺陷

审查在多个维度独立命中同一形态：

> **在正文里声明了某样东西，但 §6.0 表里没有执行单元承接它。**

实例：`§3.1` 第三层「调用面」（后补 `1k`）、`single` 档与 `RunResult.single` 字段（`ISSUE-104`）、`pyproject.toml` 两处改动（`psutil` / `py-spy`，后补 `1a-4` / `4a`）、`batch_simulator.py` 的改动（门控第 4 轮）、`plan.json` 的格式定义（阶段 4 `AUDIT-BREAK-1`）。

---

## 四、阶段 2 与阶段 3 的收敛形态

| 轮 / 项 | 结果 |
|---|---|
| 阶段 2 轮 1 | 38 条发现 → Fixer 应用 14、Verifier 13 PASS / 1 PARTIAL、冲突 4 |
| 阶段 2 轮 2–6 | 发现 9 / 14 / 4 / 7 / 5，**阻断项连续四轮为 0**，冲突稳定在 3–4 |
| 阶段 3 门控 | 6 轮撞上限；**第 6 轮四项的第一句全部是「通过」，其后才是「但是」**——门控对该计划**没有干净的通过态** |

**门控撞上限不等于其产出无价值**：`GATE-CAP` 留档 4 条，其中 `GATE-CAP-1` 已随 `AUDIT-BREAK-2` 修复；**`GATE-CAP-2`（阶段 1 边界句把 `py-spy` 标为「属阶段 5」，应为阶段 4）与 `GATE-CAP-3`（§五 一条建立在已被 §3.10 证伪前提上的重复风险行）经 `audit-fixer` 明确判为越权范围、未修**，仍在计划第 1674 行留档为待处置；`GATE-CAP-4` 的两条测试缺口已并入 `AUDIT-BREAK-2` 的修复。

**计划体量的增量绝大部分是真缺失**（`1k` 命令入口、`1a-4` psutil、`1e-*` 产品侧可选通道、`3f-2` main.py 打点、各拆分），不是注水；但**单调上涨的趋势本身值得注意**——门控每通过一轮，粒度标准被收紧一格，又能找出几处不达标。

---

## 五、待人工裁决清单

计划正文现有 **16 处 `⚠ 待人工裁决`**，均给出采用项、备选项与「选备选后须同步的章节」。**其中三处是同一个取舍的不同侧面：**

> **为了「测全」就得动产品代码，不动就得承认测不全。**

审查的选择是**动，但一律 opt-in / 默认关闭**：

| 侧面 | 采用项 |
|---|---|
| cli 采集通道（`:352`） | 产品侧加 opt-in 可选通道（`1e-2` 的 `--perf-json`、`1e-4` 的三件套） |
| 启动测量前三段（`:910`） | 给 `main.py` 加 opt-in 打点（`3f-2`） |
| 采样开闭窗口（`:481`） | **保留在 `_wk_run_single`**（守约束），单进程路径由 `6e` 标注降级 |

**这意味着 §3.2 约束 B「被测代码一行不改」实际已被放宽为「默认路径一行不改」。这个方向需要你确认。**

其余待裁决项（节选）：`subject='simulation'` 的 RSS 本期不采集（`:134`，决策 48）；是否给 `[dev]` 引入 `psutil`（`:239`，采用，备选 `ctypes`）；`2a`/`2b` 的「可提交」语义（`:381`）；第 8 段聚合源的实现方案（`:965`，决策 63）；启动测量闪窗（`:910`）；以及阶段 4 的三处冲突（见 §一）。

**另有 2 条 GATE-CAP 未修项**（`GATE-CAP-2` / `-3`，见 §四），需一并处置。

---

## 六、对计划编写方法的三条教训

1. **「声明 ↔ 交付物对齐」缺一道自检。** 本计划被 5 个独立维度反复命中同一形态（正文声明了、§6.0 无承接）。这不是笔误，是编写时缺少「每写一个声明，回 §6.0 确认谁交付它」这一步。
2. **实测通过不能替代独立审查。** 作者实测了 `profile_gui.py`（只见 `ImportError`）、统计了 `ChartWebView` 实例数（数对 10 个）、实测了 WebEngine 与 cProfile 注入——但 `profile_gui.py` 的**后三层错误被首层崩溃掩盖**，`ChartWebView` 的**归属写错**（`main_window.py` 实为 0 个）。两处均由审查独立发现。
3. **「检查项无终止条件」与「真有缺陷」要分开对待。** 阶段 3 第 6 轮四项的第一句都是「通过」——这类"但是"不应由人花时间裁决；但同一轮留档的 4 条经核实**全是真缺陷**。**不能因为门控撞上限就整体忽略其产出。**

---

## 附：本报告与工作流产出的关系

**本报告不由 `plan-review` 工作流自动生成。** 该工作流的 `review-logger` 步骤把摘要追加进**计划文件自身的「自动化审查记录」章节**，而 `CLAUDE.md` 记载的是「产出 `04-收件箱/peer-review-{plan}-{date}.md`，H1 SessionStart 自动注入」。

两者不一致，且 **H1（`.claude/hooks/inject_state.py:168-181`）硬编码只从 `04-收件箱/` 读 `peer-review-*.md`**，故仅追加进计划等于**该通道对后续会话不可见**——实施者打开计划能看到，但任何新会话的自动注入看不到。本报告即为补齐该通道而人工落盘。

同时记三处工作流缺陷：

1. `review-logger` 写入的日期为硬编码字面量 `2026-06-11`（脚本第 1144 行 `const reviewDate = '2026-06-11'`），实际审查日期为 `2026-09-21`。**该硬编码有其正当理由**——workflow 脚本禁用了 `Date.now()`/`new Date()`（会破坏 resume 缓存），脚注已说明「实际运行时用当前日期」，但无人实施该脚注所指的动作
2. 工作流不产出收件箱报告，与 `CLAUDE.md` 记载不符（已另案处置）
3. 阶段 4 的 `audit-fixer` 与 `block-writer` 共用 `label: 'block-writer'` 之外的独立标签，但阶段 4 的 `auditExecResult` 在 `if (auditMapResult)` 块内以 `const` 声明，**作用域不出该块**——若日后需在 `Summary` 阶段引用审计结果，需提升其作用域
