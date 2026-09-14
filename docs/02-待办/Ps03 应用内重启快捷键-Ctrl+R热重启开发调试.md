<!-- META: Ps03 | module:GUI基础设施 | status:已实施 | last:2026-08-05 -->

# Ps03 应用内重启快捷键：Ctrl+R 热重启开发调试

> 日期：2026-08-05 | 状态：已实施（独立审查见 §六，实施与验证见 §八）
> 触发：开发调试体验优化（用户反馈）——每次改完代码需手动「关闭应用 → 重新打开」才能看到效果，操作繁琐且耗时 3-5 秒
> 性质：开发效率工具（非产品功能），修改面小（main_window.py + main.py，约 40 行）

## 一、问题与方案演进

**现状**：改任意代码后要手动关闭应用再重新运行 `python -m gacha_simulator.main`，每次 3-5 秒，且重复「关窗→跑命令」两步。

**候选方案逐一评估**：

| 方案 | 否决原因 |
|------|---------|
| 自动重启 watcher（外部进程监控源码变化自动重启） | **agent 场景致命**：agent 推进计划时批量写文件，会反复无意义重启；改到一半的中间态会让应用起不来；且「生效时机」不可控 |
| 面板级重建（进程内 reload 面板，15ms） | 需维护面板↔文件路由表 + 处理 WebEngine 面板重建风险（7/10 面板含 QWebEngineView）+ 信号重连，复杂度最高，收益只在单面板 |
| **应用内 Ctrl+R 重启快捷键（选定）** | 手动触发（对 agent 场景天然正确：改文件不触发任何动作）；零路由；零 IPC；实现最简单 |

**结论**：快捷键方案用「手动触发」这一最朴素方式，同时规避了自动重启的反复/中间态问题和面板重建的复杂度。代价是保留秒级重启（Qt Widgets 固有边界），本方案解决的是「操作繁琐」部分。

## 二、实现原理

**核心**：重启 = **启动一个新进程 + 关闭旧进程**。Qt 的硬限制是「同一进程内不能销毁重建 QApplication」，但启动另一进程是 OS 级合法操作，完全绕开该限制。新进程 = 全新解释器 + 全新 QApplication + 全新加载代码，状态天然干净，等价于手动重启。

**流程**：

```
MainWindow: 按 Ctrl+R → _request_restart()（防抖：_restarting 标记）→ 发 restart_requested 信号
▼
main.py __main__ 块（重启动作在此，restart_pid 与退出清理同作用域）：
  ① 保存序列（复用 export_config）：validate_banners() → apply_to_store() → save_toml(默认路径)
       校验失败/异常 → cancel_restart() 复位防抖，保持旧进程不重启
  ② Popen 新进程（cwd=parent_dir 含包目录；frozen 分支用 sys.executable）
       Popen 异常 → cancel_restart() + QMessageBox 提示，保持旧进程
  ③ 启动探测：time.sleep(0.8) + poll()，新进程已退出（语法/导入错误）→ cancel_restart() + 提示
  ④ restart_pid = proc.pid
  ⑤ window.close() → closeEvent 见 _restarting 为真 → 跳过确认对话框直接 accept
  ⑥ app.exec() 返回 → 退出清理（L129-147）循环中跳过 restart_pid   否则误杀新进程
```

**关键坑**：`main.py` 退出清理会杀掉所有 `ParentProcessId=自身` 的子进程，而新进程正是旧进程的子进程，必须跳过 `restart_pid`（第⑥步）。同时 `MainWindow.closeEvent`（L606-616）有「确定要退出吗？」模态确认框，若不绕过，一键重启会退化成每次点确认，且取消路径造成双实例并存（共享 config.toml 互相覆盖），必须用 `_restarting` 标志跳过（第⑤步）。

## 三、改动清单

| 文件 | 改动 | 预估 |
|------|------|------|
| `gui/main_window.py` | ① import 加 `QShortcut, QKeySequence`；② 类属性加 `restart_requested = pyqtSignal()`；③ `__init__` 加 `self._restarting = False` + `QShortcut(QKeySequence("Ctrl+R"), self, activated=self._request_restart)`；④ 新增 `_request_restart()`（防抖，触发信号）与 `cancel_restart()`（复位防抖，供 main.py 取消路径调用）；⑤ `closeEvent` 开头加 `if self._restarting: event.accept(); return` | ~15 行 |
| `main.py` | ① `__main__` 块 `window` 创建后新增 `_on_restart_requested()`（保存序列 → Popen → 探测 → 记录 restart_pid → close，各失败路径 `window.cancel_restart()`）；② `window.restart_requested.connect(_on_restart_requested)`；③ 退出清理循环（L139-145）加 `if int(line) == restart_pid: continue` | ~30 行 |

**引用方式**（审查补充）：`_DEFAULT_CONFIG_FILE` 是 main_window.py 模块常量，main.py 用 `from gacha_simulator.paths import get_config_dir; os.path.join(get_config_dir(), 'config.toml')` 重算，不依赖私有常量。`QMessageBox` 在 handler 内局部 import（main.py 顶层无 PyQt6 import，spawn 子进程不重载 GUI 栈）。

## 四、风险与防护（含审查修正）

| 风险 | 等级 | 防护 |
|------|------|------|
| **closeEvent 确认框阻断一键重启 / 取消路径双实例** | 高（审查 HIGH-1） | `_restarting` 标志在 closeEvent 开头跳过确认；取消路径全部 `cancel_restart()` 复位 |
| **新进程启动失败导致应用丢失**（语法错误/ImportError/cwd 错） | 高（审查 HIGH-2） | Popen 包 `try/except`；0.8s 探测 `poll()` 判定秒崩；失败路径保持旧进程 + 提示。边界：延迟崩溃（>0.8s 才暴露）仍可能丢失，属尽力而为 |
| **裸 save_toml 写出非法配置**（未 apply_to_store / 未校验） | 中（审查 MED-1） | 保存序列复用 `validate_banners() → apply_to_store() → save_toml()`；校验失败不写盘 |
| 快速连按 Ctrl+R 启动多实例 | 低（审查 MED-2） | `_restarting` 防抖 + 所有取消路径复位 |
| **cwd / frozen 未处理** | 中（审查 MED-3） | `cwd=parent_dir`（含包目录，非 get_app_dir）；`frozen` 分支用 `Popen([sys.executable])` |
| **「孤儿清理兜底」声明不成立** | 中（审查 MED-4） | Windows 父进程死亡后 PPID 不重排为 1，新进程启动清理（L96-122）的 `ppid==1` 分支未必命中残留 worker。残留清理的唯一可靠路径是**旧进程自身退出清理**（正常路径覆盖），风险表声明已降级 |
| WebEngineProcess / worker 子进程残留 | 低 | 重启走正常退出路径（close → 清理 → os._exit），旧进程退出清理完整执行 |
| 未保存配置丢失 | 低 | 重启函数内自动保存（含校验） |
| 内存态模拟结果丢失 | 低（固有语义） | 重启即失，属 Qt Widgets 重启的固有语义；不做弹窗打断一键体验，计划备注说明 |
| 临时目录 `gachastat_charts_*` 累积 | 无 | 启动时清理，每次重启都执行 |

**资源泄露核查结论**（独立审查确认）：整个进程退出，进程内内存/句柄/Qt 对象被 OS 一次性回收，无进程内泄露；全库无 socket/端口/命名共享内存/mutex（batch_simulator 的 multiprocessing.Pool 走匿名管道，不跨独立实例冲突），不存在锁残留或端口占用。

## 五、验证标准

- [ ] 按 Ctrl+R：窗口**无确认框**直接关闭 → 新实例自动启动（配置保持，含自动保存的改动）
- [ ] `validate_banners()` 校验失败时：不重启、不写盘、提示、可继续编辑后重按
- [ ] 人为制造语法错误（如临时在 main.py 加非法语句）：按 Ctrl+R → 新进程秒崩被探测 → 旧窗口保留 + 提示
- [ ] 快速连按 Ctrl+R：只启动一个新实例（防抖生效）
- [ ] 旧进程退出后无残留子进程（任务管理器核对 python.exe / QtWebEngineProcess.exe）
- [ ] `pytest -q` 全量通过（纯新增，不影响现有测试）
- [ ] ruff check 通过（H7 门控）

## 六、独立审查记录

**审查方式**：独立子 agent 只读审查（不携带编写者上下文），核对计划全部技术断言与代码事实（main.py 清理逻辑、main_window 快捷键/信号、config_toml 签名、保存机制等）。

**结论**：方案主体成立，核心机制（Popen 新进程 → 退出清理跳过 restart_pid）代码层面完全走得通，关键断言（A/B/C/D/E/G/H/I）均与代码事实相符，multiprocessing spawn 与 freeze_support 不构成阻碍。按现状不可直接实施，需修正 HIGH-1（closeEvent 绕过）、HIGH-2（Popen/探测兜底）、MED-1（保存序列复用）三点，并补充 MED-3/MED-4/LOW 项。**以上修正已全部纳入 §二/§三/§四**。

## 七、备注

- **边界诚实声明**：秒级重启延迟是 Qt Widgets 无法消灭的物理边界（QApplication 不可重建）；本方案把「每次手动关窗+跑命令」压缩为「一个键」，并自动完成保存/启动/清理。新进程延迟崩溃（>0.8s 才暴露）仍可能丢应用，属尽力而为的探测边界。
- **可选叠加（不在本计划范围）**：状态栏「代码已变更，按 Ctrl+R 重启」提示（无副作用 QTimer 检测，只提醒不生效）；未来若频繁改的视觉参数可配置化，可走现有 `_on_config_changed → refresh_from_store()` 链路毫秒级刷新。
- **不引入**：外部 watcher 进程、IPC、面板路由表，保持方案最小侵入。

## 八、实施记录（2026-08-05）

- **代码改动**：
  - `gui/main_window.py`（+17 行）：`restart_requested` 信号、`Ctrl+R` 快捷键（QShortcut）、`_request_restart()`（防抖触发）/ `cancel_restart()`（取消复位）、`closeEvent` 重启路径跳过确认框
  - `main.py`（+30 行）：`_on_restart_requested()`（保存序列 → Popen 新进程 → 0.8s 探测 → 记录 restart_pid → close，各失败路径保持旧进程 + 提示）、信号连接、退出清理跳过 `restart_pid`
- **自动化验证**：py_compile ✅ / ruff check ✅ / pytest 全量 **964 passed, 1 skipped** ✅（无回归）
- **手动 GUI 验证（待用户执行）**：Ctrl+R 无确认框直接重启 / 语法错误时保留旧窗口 + 提示 / 快速连按仅单实例
