# benchmarks —— 性能分析平台

> 子系统：`docs/01-活跃/subsystems/性能分析/`
> 计划：`P83 性能分析平台——多路径测量·基线回归·现场剖析.md`
> 建档：2026-09-22（`1a-3`）

本目录是**开发侧测量资产，不进发布产物**（同 `py-spy` 的定位）。它按「粒度 × 路径 × 因子」三轴正交组织性能测量，回答三个问题：

- 「这次改动有没有变慢」——与历史基线比比值
- 「用户现场为什么卡」——attach 到真实进程采样
- 「软件启动变慢了吗」——启动时间线分段

**本文件是平台唯一面向未来维护者的入口文档。** 下面两节是**硬规则，不是建议**：它们的每一条都对应一次已发生的事故或一次实测证伪，违反的后果写在表里。

---

## 一、安全协议 · 内核级（规则 1-5）

以下五条全部来自 2026-09-17 的一次真实事故，不是预防性建议。

**事故经过：** 为验证 `py-spy` 可用性，手写探针以 `num_simulations=60000, max_workers=4` 驱动 `run_batch_parallel`，导致目标机器（总内存 15.3 GB）内存耗尽崩溃。

**根因（已核实到代码级）：** 探针未传 `on_result`，而 `service/batch_simulator.py:415` 是 `results = [] if on_result is None else None`，`:441` / `:496` / `:556` 在无收集器时逐条 `results.append(...)`，`:452` 把整个 list 返回——父进程同时持有 60000 份 `CompactResult`。

**加重因素：** 探针首版漏写 `if __name__ == '__main__':` 守卫，spawn 出的 worker 反过来又去创建自己的进程池，形成级联。

| # | 规则 | 违反后果 |
|---|------|---------|
| 1 | 必须传 `on_result` 流式收集器；**无收集器时 `n` 另有独立上限：`n ≤ 1000`** | 全部结果堆在父进程，必 OOM |
| 2 | 主模块必须有 `if __name__ == '__main__':` 守卫 | Windows spawn 下级联起进程池 |
| 3 | 杀进程必须带 `/T`（`taskkill /PID <pid> /T /F`） | Windows 杀父不杀子，孤儿 worker 残留 |
| 4 | 设 N 上限，且先小规模试跑验证进程模型 | 首次就跑大批量，出错即全量代价 |
| 5 | 启动前检查可用内存，低于阈值直接拒绝 | 在用户正在使用的机器上打满内存 |

**规则 1 与 2 特别值得记录：现有脚本里本来就有这两份防护**（`scripts/profile_sim.py:116` 主模块守卫、`:32-33,53` 流式收集器），手写驱动把它们同时丢掉。绕过已有代码自己写驱动，等于放弃已经付过学费换来的防护。

### 规则 1 / 4 / 5 的具体数值

这些是 `Plan.validate()` 与测试断言的**唯一口径**。它们是**初始值而非测量结论**：若被实测证伪（例如某台机器 2.0 GB 余量下仍 OOM），允许修订，但**须在 `02-实施.md` 记录修订理由与原值，不得静默放宽**。

| 项 | 值 | 口径与理由 |
|---|---|---|
| 规则 4 · N 上限（`collector=True`） | 单条 `Plan` 的 **`n ≤ 1600`**，超限即 `Plan.validate()` 抛 `ValueError` | 该上限防的正是内存，且**父进程内存与 `n` 线性相关**：传 `on_result` 只省下 `results` 列表（`CompactResult` 对象），**提取包仍是父进程逐模拟累积、直到批次结束才 `merge_extraction_packets` 合并**（`batch_simulator.py:433` / `:500` / `:559` 各自 append，`:449` / `:573` 收尾合并），故父进程保留量 ≈ `n × 每模拟提取包`。按实测（`extraction`+`warnings` 单独序列化 1216 KB/模拟）折算，1600 次约 1.9 GB，与规则 1 的 1000 × 1996 KB ≈ 1.9 GB 取自**同一个约 2.0 GB 的内存预算**（规则 5 的余量下限）。更长的扫描须拆成多条 plan |
| 规则 4 · 首次试跑 | 首次在某 `(workers, chunksize)` 组合上跑 `n > 100` 之前，**须先以 `n ≤ 100` 跑通一次** | 试跑失败只损失百次量级代价。写成纪律而非自动行为（平台不记忆历史组合） |
| 规则 5 · 内存阈值 | `avail ≥ max(2.0 GB, workers × 0.75 GB)`，低于即拒绝 | `avail` 取**可用物理内存**（非总量、非提交量），单位 GB，直比较不取整。`workers` 取本次 plan 的 `workers`；`gui-qt` 路径按 `workers = 1` 计并**另加 0.5 GB**（实测 `MainWindow` 显示后 412 MB + 10 个 Chromium 子进程）。**`subject='startup'` 下本条同样适用**（`workers` 取 1，再按 `gui-qt` 特例另加 0.5 GB）：启动测量驱动的正是 `gui-qt` 冷进程，是四条路径中最吃内存的形态，不因 `n` / `workers` 被忽略而豁免 |
| 规则 5 · 可注入点 | 内存查询函数必须可注入（默认实现读真实系统内存，测试注入桩） | 规则 5 的用例依赖它 |

### 规则 1 的独立上限

规则 1 的阈值**与规则 4 互不包含**（若沿用规则 4 的 1600，规则 1 的拒绝集合会成为规则 4 的真子集，删掉规则 1 行为分毫不变，而事故量级 60000 恰好落在放行区间内）：

> **`collector=False` 且 `n > 1000` 即 `Plan.validate()` 抛 `ValueError`。**

无收集器时父进程持有**全部 `n` 份 `CompactResult` 与全部 `n` 份提取包**（实测 `compact` 单独 780 KB、`extraction`+`warnings` 单独 1216 KB，合计约 1996 KB/模拟，1000 份约 1.9 GB）。**只计 `compact` 的 0.76 GB 会漏掉占六成的提取包。**

### `Plan.collector` 是「如实申报 + 校验」字段，不是运行期开关

- 适配器必须按本路径的**真实驱动**填 `collector`。**代码事实：三条产品入口（`cli` / `gui-qt` / `webui`）没有一条向 `run_batch_parallel` 传 `on_result`**（`cli.py:150` / `gacha_panel.py:82` / `webui/api.py:293`），申报值为 `False`；`inline` 的驱动来源（`scripts/profile_sim.py:53`）确实传 `on_result`，申报值为 `True`
- 平台**不因 `collector` 改变驱动方式**。填错（例如把 `cli` 的 plan 填成 `True`）**不会**让 `cli` 真的带上收集器，只会让报告说谎
- **推论（必须记住）**：`cli` / `gui-qt` / `webui` 三条路径的 plan 实际受**规则 1 的 1000 上限**约束，而非规则 4 的 1600

---

## 二、安全协议 · 路径级（规则 6-11）

规则 6-8 来自 2026-09-17 对 QtWebEngine 的实测（六变体矩阵）；规则 9-11 来自启动测量（2026-09-18）。

| # | 规则 | 违反后果 |
|---|------|---------|
| 6 | `gui-qt` 路径必须构造 **`QApplication(sys.argv)`（非空 argv）**，且 `QApplication` 之前须 `setAttribute(AA_ShareOpenGLContexts)` | 空 argv 下 QtWebEngine 初始化失败，进程以 `0xC0000409` 终止 |
| 7 | `gui-qt` 路径收尾必须**显式回收 Chromium 子进程** | `MainWindow` 显示后实测 10 个 `QtWebEngineProcess` 子进程；不回收将残留 |
| 8 | 关闭 `MainWindow` 必须**先置 `win._restarting = True`** 再 `close()` | 否则弹「确定要退出吗」确认框并阻塞，自动化流程卡死等人点击（`main_window.py:627-641`） |
| 9 | `subject='startup'` 必须在**全新冷进程**内测量，由子进程回传自己的时间线 | 模块 import 缓存是启动成本的主要部分（实测 `MainWindow` import 0.320s）；在已预热的适配器进程内测会趋近 0 |
| 10 | 启动测量前**先跑一次同条件预热并丢弃**，只记录第二次 | 冷热文件缓存相差数倍，而清空 Windows 文件缓存需管理员权限、不可靠复现。**冷启动显式不在覆盖范围内** |
| 11 | RSS 必须**固定采样时刻**（取启动完成时刻的峰值）。**本条只适用于 `subject='startup'`** | 实测空闲期工作集被系统回收，单次运行内 368 MB → 36 MB，不同时刻取值可差十倍 |

**规则 6 的排查教训（值得单独记住）：** 该现象先后被归因于「非交互式执行环境」与「Chromium 自带沙箱」，**两次都被证伪**。真实原因是**探针自身用了 `QApplication([])` 传空 argv**。**排查自身工具的失败时，应把「我调用的方式是否正确」列为一等假设，排在环境假设之前。**

---

## 三、驱动复用约束（硬规则）

> **适配器不得新写驱动，只能修复或包装已有入口。**

- **正例：** `gui-qt` 适配器 import `main_window` 现有的 `MainWindow` 与 `gacha_panel` 的 `SimulationThread`，用 `offscreen` + `QApplication(sys.argv)` 驱动，**不重写该入口**
- **反例：** 为「方便测量」新写一个脚本去跑模拟
- **判别式：** 任何一个适配器如果需要「先写个脚本来跑」，说明它设计错了

**理由：** 自己写驱动，测出来的是驱动而不是产品。2026-09-17 的事故是极端例证——手写驱动引入的两个缺陷，直接改变了被测对象的进程模型（级联起池）与内存行为（结果堆积），此时测出的任何数字都不描述产品。

**推论：** `scripts/` 下现有三份 profile 脚本是**待接管的资产，不是待废弃的旧物**。它们编码了踩坑换来的防护，修复它们就是平台的第一批工作。

---

## 四、依赖登记

| 依赖 | 进哪个 extras | 用途 | 缺失时 |
|---|---|---|---|
| `psutil` | **`[dev]`** | 规则 5 的可用物理内存；规则 11 的 RSS 峰值；第 7 段的整棵进程树 CPU | **规则 5 拒绝，不静默跳过**（内存阈值是防 OOM 的硬规则，读不到就不放行）；RSS 与 CPU 记 `None` 并在 `warnings` 标注「本指标不可得」，比对侧把 `None` 排除出比值（**不得当 0**） |
| `py-spy` | **`[dev]`** | 外部采样式现场剖析（`record` / `dump` + speedscope 解析） | 软降级，不抛异常 |

两项都**只进开发依赖，不进发布产物**。`psutil` 在 `webui/api.py:503` 已有一处**软 import**（供 WebUI 运行期资源监视端点，缺失时返回占位）——**该处不随之收紧为硬依赖**：二者共用同一个包，但依赖关系互不推导，`[dev]` 声明只为测量设施负责。

---

## 五、目录结构

```
benchmarks/
├── README.md                 # 本文件
├── perf/                     # 测量内核（无 Qt 依赖）
│   ├── plan.py               # Plan + PlanGrid + validate() + 因子展开
│   ├── record.py             # RunResult / EnvFingerprint / 序列化
│   ├── report.py             # 基线登记与比值比对
│   ├── __main__.py           # 命令入口薄壳
│   ├── adapters/             # base.py + cli / gui_qt / webui / inline
│   └── profilers/            # stage.py / cprofile.py / pyspy.py
├── baselines/                # 入库基线，按「核数区间 + OS 版本」分组
└── runs/                     # 运行产物，不入库（.gitignore）
```

**测试不放在这里**，放 `tests/benchmarks/`——本库所有测试统一在 `tests/` 下，先例为 `tests/harness/`。

---

## 六、怎么跑

```bash
# 首次建基线（建基线须 repeats >= 3，否则拒绝入库）
python -m benchmarks.perf run --plan <plan.json> --baseline <name> --register

# G1：一条命令产出「配置 X 在路径 P 上对比基线 B 的比值」
python -m benchmarks.perf run --plan <plan.json> --baseline <name>
```

`plan.json` 是 `Plan.to_dict()` 的形态，读取器为 `Plan.from_dict()`：缺省键取字段默认值，**未知键与非法值以非零退出码报错**（不静默忽略——「参数键名即契约」是本库一贯口径）。**薄壳不自行定义输入规格**，它只做「读文件 → `Plan.from_dict()` → 跑 plan → 格式化」。

**退出码：** `0` 正常；`2` 用法错误 / `plan.json` 非法 / 安全协议拒绝 / 缺基线；`3` 该路径在本环境不可用；`4` 适配器运行失败。

**`run` 的实跑输出**（`--quiet` 只留结论行）。下面是 2026-09-22 一次**真实运行**的逐字记录，`plan.json` 为 `n=20 / workers=2 / seed=42 / repeats=3 / grain=batch`（绝对路径已简写）：

```
$ python -m benchmarks.perf run --plan plan.json --baseline g1-smoke --register
本次记录：path=cli / n=20 / workers=2 / seed=42 / strategy=smart
  配置：<配置目录>/config.toml（plan.json: <plan.json 路径>）
  墙钟中位数：1.394s（repeats=3，样本 3 个）
  机器类别：17+cores_Windows 11 / QT_QPA_PLATFORM=
  阶段：config_load=0.011s，env_build=0.001s，pool_start=0.585s，simulate=0.491s，extract=0.004s
  ⚠ 2 条告警：
    - 本路径不产出该段：dispatch（分发）
    - 本期不采集：subject=simulation 的 RSS 峰值（P83 §3.3）
已登记基线 'g1-smoke' → <baselines>/17+cores_Windows 11/g1-smoke.json

$ python -m benchmarks.perf run --plan plan.json --baseline g1-smoke
本次记录：path=cli / n=20 / workers=2 / seed=42 / strategy=smart
  墙钟中位数：1.363s（repeats=3，样本 3 个）
  阶段：config_load=0.005s，env_build=0.001s，pool_start=0.530s，simulate=0.472s，extract=0.004s

本次（cli / 17+cores_Windows 11） vs 基线 g1-smoke：
  总墙钟比值（本次 / 基线）：1.005
  三元组字节数比值：1.000（代理指标，当回归判据用、不当绝对开销读）
  阶段比值：
    config_load  0.446
    env_build    0.921
    extract      1.003
    pool_start   0.907
    simulate     0.961
  阶段占比（本次 / 基线）：
    config_load  0.005 / 0.010
    env_build    0.001 / 0.001
    extract      0.004 / 0.003
    pool_start   0.524 / 0.536
    simulate     0.467 / 0.450

结论：配置 <配置目录>/config.toml 在路径 cli 上对比基线 g1-smoke 的总墙钟比值 = 1.005
```

**读这份输出的三件事：**

- `QT_QPA_PLATFORM=`（空）表示**本路径不适用**（`cli` 不是 Qt 路径），不是「未记录」。三种状态的区分见 `perf/record.py` 的 `EnvFingerprint.qt_qpa_platform`
- 阶段只有五段——`dispatch` 缺失**属事实而非缺口**（`cli` 没有分发器），故报告显式标注而非留空
- **`config_load` 的比值 0.446 不是「优化了 55%」**：它是 11ms → 5ms 量级的抖动，落在基线中位数 < 50 ms 的区间。§3.13 的定向性判据对这类短段改用绝对判据（绝对差 ≤ 50 ms），正是为此

**取这份样例时的环境注记：** 本机当时可用内存 1.42 GB，**低于规则 5 的 2.0 GB 下限，裸命令被门控按设计拒绝**。故样例是在规则 5 被显式注入旁路的前提下跑出的；除此之外全程真实（真实子进程、真实模拟、真实基线登记与比值比对）。**这条注记本身就是规则 5 生效的实证。**
