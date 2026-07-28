<!-- META: P69 | module:subsystems/策略系统 | status:designing | last:2026-07-28 | depends:P55,P56,P60 -->
# P69 策略系统重构——统一策略组件框架

> 日期：2026-07-28 | 状态：设计中
> 依赖：P55（保底扁平化）✅ + P56（事件驱动保底）✅ + P60（基础平台）✅
> 关联模块：`core/strategy.py`、`core/config_store.py`、`gui/config_panel.py`、`service/batch_simulator.py`、`core/worst_impact.py`
> 版本影响：MINOR（功能性变更）——v2.3.0 → v2.4.0
> 优先级：P1（风险性——技术债务限制可扩展性，但不阻塞核心功能）

---

## 背景

当前策略系统采用「注册表字典 + if-elif 工厂 + 单一组合模式」，8 个策略全部硬编码。随着 P55/P56/P60 相继完成——保底系统实现了装饰器级的数据驱动工厂、事件驱动保底体系全面就绪、ConfigStore 基础平台成熟——策略系统成为下一个需要对齐这些模式以消除技术债务的模块。

用户期望的策略使用路径是：**委托 coding agent 编写自定义策略 → 放入 `config/strategies/` 目录 → 应用自动发现并可用**。框架的职责是为 agent 提供清晰的 API 契约、完整的上下文、和可复用的 building block。

---

## 一、问题

| # | 问题 | 位置 | 根因 |
|---|------|------|------|
| 1 | **工厂函数硬编码** | `strategy.py:463-492` | `create_strategy()` 是 8 分支 if-elif，每加策略需改源码，而 STRATEGY_REGISTRY 已有完整 params 元数据却未被工厂使用 |
| 2 | **猴子补丁注册** | `worst_impact.py:98` | `STRATEGY_REGISTRY['draw_target']['class'] = DrawTargetStrategy`——类定义与注册表物理分离 |
| 3 | **类定义与元数据分离** | `strategy.py` | display_name/params schema 在注册表 dict 中，description() 在 class body 中——需人工同步 |
| 4 | **双字段冗余** | `config_store.py:139-141` | `strategy_type`（显示名）和 `strategy_name`（key）一对一映射，同时存储，`__post_init__` 还有容错逻辑 |
| 5 | **params 无 schema 校验** | config_panel.py 序列化 | `strategy_params: Dict[str, Any]`——类型错误到运行时才暴露 |
| 6 | **CompositeStrategy 模式单一** | `strategy.py:338-357` | 只有 `first_valid`，不支持按抽数分段、按条件切换 |
| 7 | **无插件支持** | 全局 | 加新策略必须修改 `core/` 源码 |

**已确认的上下文事实（探索 agent 发现）：**
- 策略参数当前**不走 TOML 持久化**——`config_toml.py` 完全不处理 strategy 段，参数通过 `config_panel.py` 的 `get_config()`/`set_config()` 以 JSON dict 流转
- `_on_strategy_type_changed()` 已实现根据 STRATEGY_REGISTRY.params 动态创建 Qt 控件的逻辑——但控件创建是 6 分支 if-elif
- 保底系统 `BEHAVIOR_REGISTRY` + `create_behavior(pdef, state)` 的「扁平 dataclass → getattr 按需透传」模式是本次重构最接近的参考
- 项目中目前**没有使用装饰器**自动注册——三个注册表均为显式字典

---

## 二、目标

1. 策略类通过 `@register_strategy` 装饰器自描述全部元数据——类定义即注册，消除分离维护
2. 工厂函数完全数据驱动——ParamDescriptor 自动解析参数 + 类型校验 + `cls(**kwargs)`
3. 插件扫描 `config/strategies/*.py`——importlib 加载，装饰器副作用自动注册
4. TOML 格式从 `type + name + params` 简化为 `key + params`
5. GUI 参数渲染通用化——ParamDescriptor 自动分派 Qt 控件，消除 6 分支 if-elif
6. ConfigStore 从三字段简化为二字段（`strategy_key + strategy_params`）
7. CompositeStrategy 降级为代码级 building block（不进入 TOML/GUI），新增 DrawSegment / PriorityChain / Conditional 三种
8. 未知策略降级处理——插件被删除后保留原始数据 + 警告，不静默回退

---

## 三、方案

### 阶段 1：策略组件基础设施（主线，~3 天）

#### 1.1 ParamDescriptor 类族（新文件 `core/param_descriptor.py`，~120 LOC）

```python
@dataclass
class FloatParam:
    key: str; display_name: str; default: float = 0.0
    min_val: float = 0.0; max_val: float = 99999.0
    # 方法：validate(value) → float | to_widget(parent) → QDoubleSpinBox | from_widget(w) → float | set_widget(w, v) → None

@dataclass
class IntParam: ...      # → QSpinBox
@dataclass
class BoolParam: ...     # → QCheckBox
@dataclass
class StringListParam: ... # → QLineEdit（逗号分隔）
@dataclass
class PoolIntMapParam: ... # → QLineEdit（k:v 格式）
```

Qt 控件方法内用 `TYPE_CHECKING` + `Any` 避开 core 层对 PyQt6 的直接依赖。`to_widget()`/`from_widget()`/`set_widget()` 三个方法构成 GUI 渲染的完整契约。

#### 1.2 @register_strategy 装饰器（修改 `core/strategy.py`，~80 LOC 新增）

```python
STRATEGY_REGISTRY: Dict[str, StrategyMeta] = {}

@dataclass
class StrategyMeta:
    key: str; display_name: str; description: str
    cls: Type[Strategy]; params: List[ParamDescriptor]
    internal: bool = False; plugin_path: Optional[str] = None
    _invalid_state: Optional[str] = None  # 加载失败的插件占位

def register_strategy(key, display_name, *, params=None, internal=False):
    """装饰器——副作用注册到 STRATEGY_REGISTRY"""

def create_strategy(key, params=None) -> Strategy:
    """数据驱动工厂——查 meta → 合并默认值 → 校验 → cls(**resolved)"""
```

`strategy_type_to_key()` / `strategy_key_to_type()` 保留，内部改为注册表遍历。

#### 1.3 迁移现有 8 个策略（修改 `core/strategy.py` + `worst_impact.py`，~+100/-150 LOC）

```python
@register_strategy('smart', '按需追卡')
class SmartStrategy(Strategy): ...

@register_strategy('pity_reserve', '保底预留',
    params=[FloatParam('pity_threshold_pct', '保底概率阈值(%)', default=80.0, min_val=0.0, max_val=100.0)])
class PityReserveStrategy(Strategy): ...

# ...依次迁移其余 6 个...
```

- `DrawTargetStrategy` 从 `worst_impact.py` 移入 `strategy.py`，以 `internal=True` 注册
- 删除旧 STRATEGY_REGISTRY dict（~100 LOC）
- 删除旧 create_strategy() 8 分支 if-elif（~30 LOC）
- 删除 `worst_impact.py:98` 猴子补丁行

#### 1.4 插件扫描器（新文件 `core/strategy_loader.py`，~70 LOC）

```python
def load_plugin_strategies(plugin_dir=None) -> int:
    """扫描 config/strategies/*.py → importlib 加载 → 装饰器自动注册"""
```

- 应用启动时调用（`core/__init__.py` 或 main_window 初始化阶段）
- 加载失败的插件注册为 `_invalid_state` 非空的占位 meta
- 插件目录不存在时静默返回 0

#### 1.5 GUI 通用参数渲染（新文件 `gui/param_renderer.py`，~80 LOC）

```python
def render_param_widgets(params, form_layout, widget_map, parent=None):
    """替代 config_panel.py _on_strategy_type_changed() 中的 6 分支 if-elif"""

def collect_params_from_widgets(params, widget_map) -> dict:
    """替代 _get_strategy_params_from_widgets() 中的 6 分支 if-elif"""

def set_params_to_widgets(params, widget_map, values):
    """替代 _set_strategy_params_to_widgets() 中的 if-elif"""
```

#### 1.6 ConfigStore 字段简化（修改 `config_store.py`，~+10/-20 LOC）

- 删除 `strategy_type: str`
- 重命名 `strategy_name` → `strategy_key`
- 新增 `_unknown_strategy_raw: Optional[Dict]` 降级字段

#### 1.7 config_panel 适配（修改 `gui/config_panel.py`，~+40/-60 LOC）

- 策略下拉框从 `STRATEGY_REGISTRY` 遍历 `StrategyMeta`，过滤 `internal=True`
- 参数区域调用 `render_param_widgets()` / `collect_params_from_widgets()`
- 序列化格式从 `{type, name, params}` 改为 `{key, params}`
- 加载时检测旧格式自动迁移；未知 key 降级到 `_unknown_strategy_raw` + 弹出一次 QMessageBox.warning

#### 1.8 SimulationEnv + 波及适配（修改 `batch_simulator.py` + 全文替换，~+30/-30 LOC）

- `SimulationEnv.strategy_name` → `strategy_key`
- `run_batch_parallel(strategy_name=...)` → `strategy_key=...`
- 全文搜索 `strategy_name` / `strategy_type` 引用并适配

#### 1.9 测试更新（修改测试文件，~120 LOC）

- 装饰器注册正确性、工厂参数解析、类型校验错误抛出、未知策略降级、TOML 新旧格式迁移
- 模块导入时执行 `_validate_registry()` 自检

**阶段 1 文件变更：**

| 文件 | 操作 | 净增 LOC |
|------|------|----------|
| `core/param_descriptor.py` | **新增** | +120 |
| `core/strategy_loader.py` | **新增** | +70 |
| `gui/param_renderer.py` | **新增** | +80 |
| `core/strategy.py` | 重构 | +80/-150 |
| `core/config_store.py` | 修改 | +10/-20 |
| `gui/config_panel.py` | 修改 | +40/-60 |
| `service/batch_simulator.py` | 修改 | +10/-10 |
| `core/worst_impact.py` | 修改 | -10 |
| 全文波及替换 | 修改 | +20/-20 |
| `core/__init__.py` | 修改 | +5 |
| `config/strategies/__init__.py` | **新增** | +1 |
| 测试文件 | 修改 | +120 |
| **阶段 1 合计** | | **净增 ~286 LOC** |

---

### 阶段 2：上下文契约完善（~1 天）

**StrategyContext 新增：**
- `future_resource_gains: Dict[int, Dict[str, float]]`——从 schedule_mgr 按天聚合未来资源收入
- `inter_pool_pity_links: Dict[str, List[str]]`——从 PityEngine 提取跨池保底继承关系
- `time_discount: float = 1.0`——时间偏好因子

**StrategyContextBuilder**（新文件 `core/strategy_context_builder.py`，~80 LOC）：
将当前分散在 `GachaService.run_simulation()` 中的上下文拼接逻辑抽取为链式构建器，在 `build()` 中自动计算上述三个新字段。

| 文件 | 操作 | 净增 LOC |
|------|------|----------|
| `core/strategy.py` | StrategyContext 扩字段 | +15 |
| `core/strategy_context_builder.py` | **新增** | +80 |
| `service/gacha_service.py` | 适配 Builder | +10/-15 |
| **阶段 2 合计** | | **净增 ~90 LOC** |

---

### 阶段 3：开发者辅助工具（~1 天）

纯 Python API——不进入 TOML 序列化，不进入 GUI。供 coding agent 在插件策略中作为 building block。

| 类 | 功能 | 构造函数 |
|----|------|---------|
| `DrawSegmentStrategy` | 按累计抽数分段 | `segments: List[tuple[int, Strategy]]` |
| `PriorityChainStrategy` | 优先级降级链 | `strategies: List[Strategy]` |
| `ConditionalStrategy` | lambda 条件分支 | `condition: Callable, true_s, false_s` |

旧 `CompositeStrategy` 保留但添加 `DeprecationWarning`，内部委托给 `PriorityChainStrategy`。

| 文件 | 操作 | 净增 LOC |
|------|------|----------|
| `core/strategy.py` | 新增 3 类 + 废弃旧类 | +130/-15 |
| **阶段 3 合计** | | **净增 ~115 LOC** |

---

### 阶段 4：插件管理 GUI（~1.5 天）

**插件管理面板**（新文件 `gui/plugin_manager_panel.py`，~200 LOC）：
- QTableWidget 列表：插件名称 | key | 状态(active/error/disabled) | 文件路径
- 启用/禁用（翻转 `StrategyMeta.internal`）
- 重新扫描（调用 `load_plugin_strategies()`）
- 错误状态展示完整 traceback
- 作为 QDialog，菜单项「工具 → 插件管理」触发

**热重载**（修改 `strategy_loader.py`，~40 LOC）：
- `reload_plugin_strategy(name)` / `disable_plugin_strategy(name)` / `enable_plugin_strategy(name)`



| 文件 | 操作 | 净增 LOC |
|------|------|----------|
| `gui/plugin_manager_panel.py` | **新增** | +200 |
| `gui/main_window.py` | 修改 | +15 |
| `core/strategy_loader.py` | 修改 | +40 |
| **阶段 4 合计** | | **净增 ~255 LOC** |

---

## 四、波及范围

### 直接修改文件（10 个）

| 文件 | 阶段 | 变更性质 |
|------|------|---------|
| `core/param_descriptor.py` | 1 | **新增** |
| `core/strategy_loader.py` | 1,4 | **新增** + 扩展 |
| `gui/param_renderer.py` | 1 | **新增** |
| `core/strategy_context_builder.py` | 2 | **新增** |
| `gui/plugin_manager_panel.py` | 4 | **新增** |
| `core/strategy.py` | 1,2,3 | 主重构 |
| `core/config_store.py` | 1 | 字段简化 |
| `gui/config_panel.py` | 1 | GUI 适配 |
| `service/batch_simulator.py` | 1 | 符号重命名 |
| `core/worst_impact.py` | 1 | 猴子补丁移除 |

### 全文搜索替换波及

| 旧符号 | 新符号 |
|--------|--------|
| `ConfigStore.strategy_type` | 删除（从 `STRATEGY_REGISTRY[key].display_name` 查询） |
| `ConfigStore.strategy_name` | `ConfigStore.strategy_key` |
| `SimulationEnv.strategy_name` | `SimulationEnv.strategy_key` |
| `STRATEGY_REGISTRY['...']['class']` | `STRATEGY_REGISTRY['...'].cls` |

### 向后兼容

- `create_strategy(name, params)` 签名不变（内部重构）
- `strategy_type_to_key()` / `strategy_key_to_type()` 保留
- 旧 TOML `type + name` 格式自动检测并迁移
- 旧 JSON config 自动转换

---

## 五、风险

| 风险 | 缓解 |
|------|------|
| `importlib` 在 PyInstaller 打包后路径解析失效 | `load_plugin_strategies()` 检测 `sys.frozen`，打包版提示插件目录路径 |
| 现有测试中硬编码 `ConfigStore(strategy_type=..., strategy_name=...)` | 全文搜索所有测试中的关键字参数并替换 |
| 全文搜索替换遗漏导致运行时 AttributeError | `__post_init__` 中保留过渡期兼容——检测旧字段名时发出 FutureWarning |

---

## 六、验收标准

### 阶段 1

- [ ] `create_strategy()` 不含 if-elif 分支，完全数据驱动
- [ ] 参数类型校验生效：`create_strategy('pity_reserve', {'pity_threshold_pct': '八十'})` 抛出 ValueError
- [ ] `worst_impact.py` 中无 `STRATEGY_REGISTRY` 直接赋值
- [ ] `ConfigStore` 无 `strategy_type` 字段
- [ ] 新 TOML `key + params` 格式正确读写
- [ ] 旧 TOML `type + name` 格式自动迁移
- [ ] 未知策略 TOML 加载时弹出警告
- [ ] 所有现有测试通过

### 阶段 2

- [ ] `StrategyContext` 含三个新字段，默认值不影响旧逻辑
- [ ] `StrategyContextBuilder` 正确计算未来资源 + 跨池链接

### 阶段 3

- [ ] DrawSegment / PriorityChain / Conditional 三种复合策略行为正确
- [ ] 三个类不在 TOML 序列化中出现

### 阶段 4

- [ ] 插件管理面板正确展示插件列表 + 状态 + 错误信息
- [ ] 启用/禁用/重新扫描功能正常

### 全量回归

- [ ] CLI `python -m gacha_simulator.cli -n 100` 正常执行
- [ ] GUI 策略下拉 + 参数控件 + 模拟运行正常
- [ ] 批量模拟 / 策略比较 / 最差影响 / 退路搜索 四面板正常
- [ ] 配置 round-trip 无数据丢失
- [ ] `_version.py` + `技术栈.md` 版本号同步至 v2.4.0

---

## 附录：命名空间约定

| 策略来源 | key 格式 | 示例 | GUI 列表 |
|---------|---------|------|---------|
| 内置核心 | `{short_name}` | `smart`、`pity_reserve` | 正常显示 |
| 内置内部 | `{short_name}` + `internal=True` | `draw_target`、`no_draw` | 不显示 |
| 插件策略 | `plugin/{name}`（装饰器显式指定） | `plugin/my_adaptive` | 正常显示 |
| 插件错误 | `plugin/{name}` + `_invalid_state` 非空 | `plugin/broken` | 仅插件管理面板可见 |

## 附录：插件策略最小示例

```python
# config/strategies/my_phased_plan.py
from gacha_simulator.core.strategy import (
    register_strategy, Strategy, StrategyContext,
    FloatParam, IntParam,
    DrawSegmentStrategy,
)
from gacha_simulator.core.action import DrawAction, WaitAction

@register_strategy('plugin/phased_plan', '两阶段策略',
    params=[
        FloatParam('early_threshold', '前期阈值(%)', default=80.0, min_val=0.0, max_val=100.0),
        FloatParam('late_threshold', '后期阈值(%)', default=50.0, min_val=0.0, max_val=100.0),
        IntParam('switch_at', '切换抽数', default=50, min_val=1),
    ])
class PhasedPlanStrategy(Strategy):
    """前N抽高阈值保守，后期低阈值激进。"""

    def __init__(self, early_threshold=80.0, late_threshold=50.0, switch_at=50):
        from gacha_simulator.core.strategy import PityReserveStrategy
        self.inner = DrawSegmentStrategy([
            (0, switch_at, PityReserveStrategy(pity_threshold_pct=early_threshold)),
            (switch_at, None, PityReserveStrategy(pity_threshold_pct=late_threshold)),
        ])

    @classmethod
    def description(cls):
        return "前期高阈值保守，后期低阈值激进"

    def select_action(self, ctx):
        return self.inner.select_action(ctx)
```

TOML 中仅存储原子参数：
```toml
[strategy]
key = "plugin/phased_plan"
params = { early_threshold = 80.0, late_threshold = 50.0, switch_at = 50 }
```
