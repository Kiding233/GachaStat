<!-- META: P53 | module:配置 | status:ready | last:2026-06-14 -->
# P53 TOML 配置文件迁移实施计划

> 日期：2026-06-14 | 状态：📋就绪 | 优先级：🔵 P2 — 架构债务
> 来源：P50 可行性调查报告——确认 TOML 方案可行，Schema 已定稿，默认 `config.toml` 已就绪
> 依赖：无（可独立执行；P49 被本计划覆盖，P49 的 txt 修复将因旧解析器删除而不再需要）
> 涉及层：core（`config_toml.py` 新增 + `config_store.py`/`retreat_config.py` 字段改名 + `config_io.py`/`pool_config.py` 删除 + `pity.py`/`resource_gain.py` 裁剪）→ CLI → GUI → `scripts/` → 测试

---

## 一、目标

将 10 个 txt 配置文件（4 种自定义语法，~500 行解析器）替换为单一 `config.toml`，净删除 ~480 行代码。

**不做的事：**
- 不写迁移脚本——默认 `config.toml` 已等价于原始 txt，无需 txt→TOML 自动转换
- 不保留 txt 加载路径——`config_io.py` + 所有 `parse_*` 函数全部删除
- 不保留 JSON 配置文件路径——`json_config_to_store()` (96 行) + `default_config.json` + `--no-json` 标志全部删除；旧 `-c`/`--config` 重定义为 TOML 路径
- 不保留硬编码合成池子的默认回退——无参数运行时加载打包 `config.toml`
- 不移除 `parse_cost_string()` —— cost DSL 保留为 TOML 字符串值
- 不移除 `_expand_binding()` —— 从 `pool_config.py` 迁移至 `config_toml.py`，bindings 逗号分隔展开（含等权与冒号加权）保留
- 不移除 `expand_gain_rules_to_schedule()` —— gain_rules 展开逻辑不变
- 不将 simulation 参数（count/max_workers/seed）纳入 TOML —— 保持 CLI/GUI 动态传入

---

## 二、文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `gacha_simulator/core/config_toml.py` | **新建** | `load_toml()` + `save_toml()`，~200 行 |
| `gacha_simulator/core/config_store.py` | **修改** | `PoolEntry.distribution_file` → `distribution_template`；新增 `_distribution_templates: List[dict]` dataclass 字段；`ConfigStore.clear()` 显式重置 |<!-- REVIEW-R1-FIX: ISSUE-033 -->
| `gacha_simulator/core/config_io.py` | **删除** | 625 行全删——所有 `_load_*` / `_save_*` 函数不再需要 |
| `gacha_simulator/core/pool_config.py` | **删除** | 整文件删除——唯一保留函数 `_expand_binding()` 已迁移至 `config_toml.py`（见 S2a §2.2）。旧 `parse_*`/`load_*` 函数 + `PoolConfig`/`CardDef`/`CardCatalog` dataclass 一并删除 |<!-- REVIEW-R1-FIX: ISSUE-035 -->
| `gacha_simulator/core/pity.py` | **裁剪** | 删除 `parse_pity_file` + `build_pity_engine`（共 ~93 行） |
| `gacha_simulator/core/resource_gain.py` | **裁剪** | 删除 `parse_gains_file`（已废弃死代码）/ `parse_resources_file` |
| `gacha_simulator/core/__init__.py` | **修改** | 删除旧 `parse_*` re-export，新增 `load_toml` / `save_toml` |
| `gacha_simulator/core/retreat_config.py` | **修改** | `distribution_file` → `distribution_template`；`PoolEntry` 构造（L42-61）新增 `pool_type=p.pool_type` 和 `batch_size=p.batch_size`——与字段改名原子修改。`pool_type` 避免配置截断后池子类型信息丢失；`batch_size` 防止截断池子批次大小退化为默认值 1（当前 8 个默认池子均为 batch_size=1，该缺陷仅在未来引入非默认批次大小时触发）。**原子性约束（G-ATOMIC-1）：** 若 S2b-1 先改名 `distribution_file`→`distribution_template` 而此处未同步更新 L49 的 `distribution_file=p.distribution_file` → `distribution_template=p.distribution_template`，`AttributeError: 'PoolEntry' object has no attribute 'distribution_file'`——退路面板构造截断配置时崩溃 |<!-- REVIEW-R1-FIX: ISSUE-021 --><!-- REVIEW-R1-FIX: ISSUE-031 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-10 -->
| `gacha_simulator/cli.py` | **修改** | 删除 `json_config_to_store()` (96行) + 旧 JSON/硬编码路径；`-c`/`--config` 重定义为 TOML 路径；`--no-json` 删除；无参数时加载打包 `config.toml` |
| `gacha_simulator/gui/main_window.py` | **修改** | `_DEFAULT_CONFIG_DIR` → `_DEFAULT_CONFIG_FILE`；`load_store_from_directory` → `load_toml`；`save_store_to_directory` → `save_toml` |
| `gacha_simulator/gui/config_panel.py` | **修改** | `distribution_file=f"pools/{pid}.txt"` → `distribution_template=""`（2 处）+ `pool_type` 双写逻辑 |
| `gacha_simulator/gui/about_dialog.py` | **修改** | 配置文件指南 HTML（L133-169）从 txt `|` 分隔格式改写为 TOML 格式说明 |
| `CONTRIBUTING.md` | **修改** | `config/` 目录文件树（L18-25）从 7 个 txt 文件列表改为 `config.toml` 单行；新增独立实施步骤 S3.7 |<!-- REVIEW-R1-FIX: ISSUE-010 -->
| `CLAUDE.md` | **修改** | 第 26 行 `config/` 说明从「\| 分隔文本格式」改为「TOML 格式（单文件 `config.toml`）」；第 62 行 `config_io.py`→`config_toml.py`，删除 txt 文件列表；第 72 行扩展指南表 `config_io.py`→`config_toml.py` |<!-- REVIEW-R1-FIX: ISSUE-038 -->
| `scripts/verify_p26_pity_causality.py` | **修改** | `load_store_from_directory` → `load_toml` |
| `scripts/verify_p26_integration.py` | **修改** | `load_store_from_directory` → `load_toml` |
| `scripts/profile_gui.py` | **修改** | `load_store_from_directory` → `load_toml` |
| `scripts/profile_sim.py` | **修改** | `load_store_from_directory` → `load_toml` |
| `scripts/profile_simulation.py` | **修改** | `load_store_from_directory` → `load_toml` |
| `pyproject.toml` | **修改** | 添加 `tomli>=2.0`（3.10 回退）+ `tomli-w>=1.0` 依赖 |
| `tests/core/test_batch_draw.py` | **修改** | `parse_schedule_file` → 构造 `PoolEntry` 直接使用 `distribution=[]` |
| `tests/core/test_config_toml.py` | **新建** | TOML 加载/保存/往返测试（含边界与契约测试） |
| `tests/core/test_streaming.py` | **新建** | 从 `test_config_io.py` 提取 `TestStreaming` 类（4 个测试） |
| `tests/core/test_config_io.py` | **删除** | `TestStreaming` 已提取；其余测试对象 `load_store_from_directory` 已删除 |
| `tests/core/test_pool_config_parse.py` | **删除** | 测试对象 `parse_*` 函数已删除 |
| `tests/verify_toml_equivalence.py` | **删除** | 一次性验证工具——S4 删除旧解析器后不再有用 |
| `scripts/verify_p26_claims.py` | **无变更** | 零依赖 `parse_*` 或 `config_io`——安全 |
| `scripts/benchmark_chart.py` | **无变更** | 零依赖 `parse_*` 或 `config_io`——仅引用 `visualization.font_config` |

---

<!-- REVIEW-R1-FIX: AUDIT-BREAK-1 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-5 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-6 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-10 -->
### 二-A：原子提交约束（阻断性断裂防护）

以下变更组存在跨文件类型断裂——若不同时提交，中间状态将导致 `ImportError`/`TypeError`/`AttributeError`，使 GUI 启动即崩溃或 pytest 收集阶段全灭。

| 断裂组 | 涉及文件 | 断裂类型 | 约束 |
|--------|---------|---------|------|
| **G-ATOMIC-1** | `config_store.py`（S2b-1: `distribution_file`→`distribution_template` 改名 + `_distribution_templates` dataclass field 声明）+ `retreat_config.py`（S2b-1: 旧 `.distribution_file` 访问 + `PoolEntry` 构造）+ `config_panel.py`（S3b: 2处 `distribution_file=`→`distribution_template=`）+ `config_io.py`（S4.1: 删除——天然消除 `.distribution_file` 引用） | **TypeError/AttributeError**：改名后任一调用方仍传 `distribution_file=` 或访问 `.distribution_file`，立即触发异常。`config_panel.py:2371`/`config_panel.py:2884` 两处构造点 + `retreat_config.py:49` 一处读取点 + `config_io.py:161/424/538` 三处（S4.1 删除可消除） | S2b-1 + S3b + S5 的 `retreat_config.py` 修改必须在**同一 commit** 中完成。S4.1 删除 `config_io.py` 可独立于 G-ATOMIC-1（旧代码对改名毫不知情，`AttributeError` 仅发生于新代码访问旧字段时，但旧 `config_io.py` 自身不读取 `PoolEntry.distribution_template`），但仍建议 S4.1 与 G-ATOMIC-1 同 commit——减少 `git bisect` 跨越时的困惑 |
| **G-ATOMIC-2** | `pool_config.py`（S4.2: 整文件删除）+ `__init__.py`（S4.5: 删除 `from .pool_config import ...` re-export + 新增 `load_toml`/`save_toml`）+ `pity.py`（S4.3: 删除 `parse_pity_file`/`build_pity_engine`）+ `resource_gain.py`（S4.4: 删除 `parse_gains_file`/`parse_resources_file`） | **ImportError**：S4.2 删除 `pool_config.py` 后若 S4.5 未同步更新 `__init__.py:37`→`from gacha_simulator.core import PoolConfig` 触发 `ModuleNotFoundError: No module named 'gacha_simulator.core.pool_config'`（模块级导入，pytest 收集阶段即失败）。`_expand_binding` 已在 S2a 迁移至 `config_toml.py`，不从 `pool_config` 导入 | S4.2 + S4.3 + S4.4 + S4.5 必须在**同一 commit** 中完成（S4 原子删除 commit）。门控 G1（全局 grep）+ G3（`pytest -q`）双重验证 |

**违反后果一览：**

| 违反组 | 触发时机 | 症状 |
|--------|---------|------|
| G-ATOMIC-1 违反（改名与调用方不同步） | GUI 启动 / pytest 收集 / CLI 执行 | `TypeError: PoolEntry.__init__() got an unexpected keyword argument 'distribution_file'` 或 `AttributeError: 'PoolEntry' object has no attribute 'distribution_file'` |
| G-ATOMIC-2 违反（pool_config.py 删除与 __init__.py 不同步） | `import gacha_simulator.core` | `ModuleNotFoundError: No module named 'gacha_simulator.core.pool_config'`——整个 core 模块不可用 |
| `_distribution_templates` 非 dataclass field | `clear()` 创建新实例 | 旧模板残留→`_save_templates_and_pools` 写出不应存在的模板引用 |

**`_distribution_templates` 泄漏防御：**

```python
# config_store.py — ConfigStore dataclass 中声明（非动态属性赋值）
@dataclass
class ConfigStore:
    # ... 现有字段 ...
    _distribution_templates: List[dict] = field(default_factory=list)

    def clear(self):
        # ... 现有重置 ...
        self._distribution_templates.clear()        # 显式清空，防止模板残留
```

若实现时误用动态属性赋值而非先声明 dataclass field，`clear()` 创建的全新 `ConfigStore()` 实例将不含 `_distribution_templates` 属性，后续 `save_toml` 读取触发 `AttributeError`。务必先声明 dataclass field 再赋值。

---

## 三、实施步骤

### S1：添加 TOML 读写依赖

<!-- REVIEW-R1-FIX: ISSUE-003 — 添加 tomli 作为 Python 3.10 tomllib 回退 -->
**文件：** `pyproject.toml`

在 `[project].dependencies` 中添加：

```
"tomli>=2.0; python_version < '3.11'",
"tomli-w>=1.0",
```

- `tomli`：Python 3.10 的 `tomllib` 标准库回退（读 TOML）。`python_version < '3.11'` 条件依赖——Python 3.11+ 直接使用内置 `tomllib`，不安装 `tomli`
- `tomli-w`：写 TOML（所有 Python 版本均需，标准库无写支持）

**`config_toml.py` 顶部兼容导入模式**（在 S2a 中实现）：

```python
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib
```

**验证：** `pip install -e ".[dev]"` 成功；Python 3.10 环境下 `python -c "import tomli; import tomli_w"` 无错误；Python 3.11+ 环境下 `python -c "import tomllib; import tomli_w"` 无错误。

---

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — S2 实际工作量约 4-8 小时，拆为 S2a/S2b/S2c 三子步骤，每步控制在 ~1-2h -->
### S2a：新建 `core/config_toml.py` — 加载路径（load_toml + 基础 _build_* helper，~1.5h）

> **本子步骤覆盖：** `load_toml` 公开接口 + 5 个基础 `_build_*` helper（cards/resources/gain_rules/day_overrides/pity）+ `_build_targets` + TOML 加载伪代码 + 加载侧单元测试。
> **不涉及：** 保存路径（→S2b）、模板展开（→S2c）、GUI 双写逻辑（→S2c）。

**文件：** `gacha_simulator/core/config_toml.py`（新建）

#### 2.1 公开接口

```python
def load_toml(path: str, store: Optional[ConfigStore] = None) -> ConfigStore
def save_toml(store: ConfigStore, path: str) -> None
```

#### 2.2 内部 helper 函数（按子步骤分配）

| 函数 | 职责 | 子步骤 |
|------|------|--------|
| `_build_cards(data: dict, store: ConfigStore)` | `[[cards]]` → `store.card_defs` | S2a |
| `_build_resources(data: dict, store: ConfigStore)` | `[resources.defs]` + `[resources.initial]` → `store.resource_defs` / `store.initial_resources` | S2a |
| `_build_gain_rules(data: dict, store: ConfigStore)` | `[[resources.gain_rules]]` → `store.gain_rules` | S2a |
| `_build_day_overrides(data: dict, store: ConfigStore)` | `[[resources.day_overrides]]` → `store.day_overrides` | S2a |
| `_build_pity(data: dict, store: ConfigStore)` | `[[pity]]` → `store.pity`，含 `threshold` 字段 | S2a |
| `_build_targets(data: dict, store: ConfigStore)` | `[[targets]]` → `store.target_cards` | S2a |
| `_build_weights(data: dict, store: ConfigStore)` | `[[weights]]` 数组表 → `store.card_weights` | S2b-1 |
| `_build_distribution_templates(data: dict)` | `[[distribution_templates]]` → `List[dict]`（中间产物，尚未展开。每个 dict 含 `name` 键和 `cards` 键，格式：`[{"name": "xxx", "cards": [...]}, ...]`） | S2b-1 |<!-- REVIEW-R1-FIX: ISSUE-034 --><!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->
| `_build_pools(data: dict, store: ConfigStore, templates: dict)` | `[[pools]]` → `store.pools`，含绑定展开 + 分布模板引用解析 | S2b-1 |
| `_expand_binding(value: str, prob: float) -> List[Tuple[str, float]]` | 从 `pool_config.py` 原样迁移至 `config_toml.py`。逗号分隔的绑定值展开：等权（`"a,b,c"` → 均分概率）或加权（`"a:2.0,b:1.0"` → 按权重比例分配）。加权语法是 TOML 字符串内部 DSL——冒号、逗号、数字均为字符串字面量，与 TOML 解析器无冲突 | S2a |
| `_expand_template_with_bindings(template_cards: List[dict], bindings: Dict[str, str]) -> List[PoolDistEntry]` | 将模板中的绑定键（`"ssr"`/`"sr"`/`"r"`/`"ssr_alt"`/`"ssr_alt1"`/`"ssr_alt2"`）展开为具体 `PoolDistEntry`。调用 `_expand_binding()` 处理每个绑定键的值（含加权），`card_id` 不在绑定键集合中时按原样作为单卡 ID。`featured` 仅当显式为 `true` 时标记 | S2c |

#### 2.3 `load_toml` 实现伪代码

```python
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

def load_toml(path: str, store=None):
    if store is None:
        store = ConfigStore()
    else:
        store.clear()

    with open(path, 'rb') as f:
        data = tomllib.load(f)

    # 各段构建（顺序无关——ConfigStore 各字段独立）
    _build_resources(data, store)
    _build_cards(data, store)
    _build_gain_rules(data, store)
    _build_day_overrides(data, store)
    _build_pity(data, store)
    _build_targets(data, store)
    _build_weights(data, store)

    # 分布模板 → 池子（需先构建模板索引，再展开池子）
    templates = _build_distribution_templates(data)
    store._distribution_templates = templates  # 缓存供 save_toml 使用
    _build_pools(data, store, templates)

    return store
```

---

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — S2b 拆为 S2b-1（save_toml 骨架 + ConfigStore 字段 + clear()，~1h）和 S2b-2（模板匹配逻辑，~1h） -->
### S2b-1：新建 `core/config_toml.py` — 保存路径骨架（save_toml 基础结构 + ConfigStore 字段声明 + clear() 重置，~1h）

> **本子步骤覆盖：** `save_toml` 公开接口基础结构（meta / resources / gain_rules / day_overrides / cards / pity / targets / weights 各段序列化，pool 段暂以 `_save_templates_and_pools` stub 写出内联分布）+ `_build_weights` / `_build_distribution_templates` / `_build_pools` helper（加载路径必需，S2a 未覆盖的三段）+ `ConfigStore._distribution_templates` dataclass field 声明 + `ConfigStore.clear()` 显式重置。
> **前置依赖：** S2a（加载路径已实现，`load_toml` 可验证保存往返）。
> **不涉及：** `_save_templates_and_pools` 模板匹配实现（→S2b-2）、模板展开实现（→S2c）。
>
> **S2b-1 完成时验证：** 加载默认 `config.toml` → `save_toml` 写出（池子分布使用内联 `[[pools.distribution]]`，不依赖模板匹配）→ `load_toml` 重新加载 → 两次加载的 ConfigStore 等价。此基本往返验证确保保存骨架正确后再进入 S2b-2 的模板匹配逻辑。

#### 2.4 `save_toml` 实现伪代码

```python
import tomli_w

def save_toml(store, path):
    # 将 ConfigStore 各字段反向组装为 dict，然后用 tomli_w.dump() 写出
    data = {}

    # resources
    data['resources'] = {
        'defs': dict(store.resource_defs),
        'initial': dict(store.initial_resources),
    }

    # gain_rules
    data['resources']['gain_rules'] = [
        {'type': r.rule_type, 'param': r.param, 'gains': dict(r.gains)}
        for r in store.gain_rules
    ]

    # day_overrides
    data['resources']['day_overrides'] = [
        {'day': d.day, 'gains': dict(d.gains)}
        for d in store.day_overrides
    ]

    # cards
    data['cards'] = [
        {'id': c.card_id, 'name': c.name, 'rarity': c.rarity}
        for c in store.card_defs
    ]

    # distribution_templates——从现有池子的 distribution + bindings 反向推导
    # 因为 ConfigStore 的 PoolEntry.distribution 是展开后的 PoolDistEntry[]，
    # 反向推导模板需聚合所有同名模板的池子，提取公共结构。这是最复杂的反向映射。
    # 简化策略：如果存在默认 config.toml，保留其 [[distribution_templates]] 段不变；
    # 如果用户通过 GUI 修改了池子分布，按内联 [[pools.distribution]] 写出。
    _save_templates_and_pools(store, data)  # 内部读取 store._distribution_templates

    # pity
    data['pity'] = [
        {
            'name': p.name, 'type': p.btype,
            'start': int(p.params.get('start', 0)),
            'end': int(p.params.get('end', 0)),
            'func': p.params.get('func', 'linear'),
            'threshold': int(p.params.get('threshold', 0)),
            'reset': p.reset_condition, 'pools': p.pools,
            'target': dict(p.target_distribution),
            'counter_init': 0,
        }
        for p in store.pity.pities
    ] if store.pity.enabled else []

    # targets
    data['targets'] = [
        {'card_id': t.card_id, 'quantity': t.quantity, 'pool_ids': list(t.pool_ids)}
        for t in store.target_cards
    ]

    # weights——[[weights]] 数组表格式
    data['weights'] = [
        {'card_id': cid, 'desire': cw.desire_weight,
         'miss_cost': cw.miss_cost_weight, 'card_value': cw.card_value}
        for cid, cw in store.card_weights.items()
    ]

    with open(path, 'w', encoding='utf-8') as f:
        # 写入文件头注释块（tomli_w 不支持注释——手动写入片段后追加 tomli_w 输出）
        f.write(
            '# ============================================================\n'
            '# GachaStat 统一配置文件 —— 由 GachaStat GUI 自动生成\n'
            '# ============================================================\n'
            '# 语法速查：\n'
            '#   key = value          标量（整数/浮点/布尔/字符串）\n'
            '#   [section]            表（字典）—— . 号嵌套子表\n'
            '#   [[array]]            数组表——每个 [[array]] 是数组中的一个元素\n'
            '#   { k = v, k = v }     内联表——写在一行的小字典\n'
            '# ============================================================\n'
            '# 完整格式说明见 GUI 帮助→关于→配置文件指南\n'
            '\n'
        )
        tomli_w.dump(data, f)
```

#### 2.5 关键注意点（跨 S2a/S2b-1/S2b-2/S2c 子步骤通用）<!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->

- `tomllib.load()` 读二进制文件（`'rb'`），`tomli_w.dump()` 写文本文件（`'w'`）
- TOML 中 `probability` 是百分比（0.2 = 0.2%），`PoolDistEntry.probability` 也是百分比——无需转换
- **TOML 键名与 `PoolEntry` 字段严格一致**：`pool_type`（非 `type`）、`distribution_template`（非 `distribution_file`）——`_build_pools` 直接按 dataclass 字段名取值，无需隐式映射
- `bindings` 中的逗号分隔展开逻辑由 `_expand_binding()` 处理（该函数从 `pool_config.py` 原样迁移至 `config_toml.py`，见 S2a §2.2）。支持等权展开（`"a,b,c"` → 均分概率）和冒号加权展开（`"a:2.0,b:1.0"` → 按权重比例分配概率）。冒号语法是 TOML 字符串内部的 DSL——TOML 解析器仅将其视为字符串字面量，与 TOML 的 `key = value` 语法无冲突
- 与 `txt` 加载不同：TOML 解析失败时 `tomllib` 抛出明确异常（含行列号），不静默跳过
- **`[[pools]].target_cards` → `PoolEntry.target_specs`**：TOML 中 `target_cards = ["card_id"]` 是纯字符串数组；加载时转换为 `target_specs = [("card_id", 1)]`——池子级数量恒为 1，全局需求量由 `[[targets]]` 段的 `quantity` 字段独立管理（与当前 txt 行为一致）
- **`rerun_of` / `exchange_card_id`** 在 `[[pools]]` 中为可选字段，加载逻辑与当前 `_load_schedule` 一致：
  - `exchange_card_id` 存在时：分布 = 单个 `PoolDistEntry(card_id=exchange_card_id, probability=100.0, rarity='ssr', featured=True)`
  - `rerun_of` 存在时：从同名池子复制 `distribution`（在 `_build_pools` 内部处理）
  - 默认 `config.toml` 中不写这两个字段（无池子使用）
- **`pool_type` 字段**：默认 `config.toml` 中 8 个角色池均为 `pool_type = "角色"`。`PoolEntry.pool_type` 字段当前在模拟引擎中通过 `_infer_pool_type` 回退间接使用（因 `config_panel.py` 未直接设置该字段，其默认空字符串触发推断路径，见 `batch_simulator.py:558` 的 `getattr(pe, 'pool_type', '') or ...` 短路逻辑）。TOML 迁移后该字段由 `_build_pools` 直接赋值，消除推断依赖。GUI 池子表格按类型着色，需保留<!-- REVIEW-R1-FIX: ISSUE-041 -->
- <!-- REVIEW-R1-FIX: ISSUE-006 — ConfigStore 新增 `_distribution_templates` 字段 -->**`ConfigStore` 新增一个 dataclass 字段**：`config_store.py` 需在 `ConfigStore` dataclass 中声明 `_distribution_templates: List[dict] = field(default_factory=list)`。`load_toml` 时赋值（`store._distribution_templates = templates`），`save_toml` 时直接读取。**`ConfigStore.clear()` 必须显式重置**：`self._distribution_templates.clear()`。若采用动态属性赋值而非 dataclass field，`clear()` 不知晓其存在——先 `load_toml(store)` 加载配置 A，再以同一 store 加载配置 B，`_distribution_templates` 跨加载泄漏旧模板。

---

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — S2b-2 承接 S2b-1 的 save_toml 骨架，实现模板匹配智能判定 -->
### S2b-2：新建 `core/config_toml.py` — 分布模板匹配逻辑（_save_templates_and_pools + _distribution_matches_template，~1h）

> **本子步骤覆盖：** `_save_templates_and_pools` 实现（池子分布反向写入 TOML 结构，含模板引用 vs 内联分布判定）+ `_distribution_matches_template` 模板匹配逻辑（浮点容差 `math.isclose(rel_tol=1e-6)`、按 card_id 排序逐卡比较、bindings type 键过滤）+ 模板匹配往返测试（S5.1b 对应测试用例）。
> **前置依赖：** S2b-1（`save_toml` 骨架已实现并验证基本往返，`store._distribution_templates` 字段已就绪供读取）。
> **不涉及：** 模板展开实现（→S2c）。
>
> **S2b-2 完成时验证：** 加载默认 `config.toml` → `save_toml` 写出（池子分布通过模板匹配优先写 `distribution_template` 引用，仅修改过的池子写内联分布）→ `load_toml` 重新加载 → 对比原始加载结果，`distribution_template` 引用完整保留。

#### 2.6 `save_toml` 分布模板策略

写入时面临反向问题：`PoolEntry.distribution` 是展开后的 `PoolDistEntry[]`，嵌套分组信息已丢失。策略如下：

**核心思路：加载时记录模板名，保存时比较判定。**

1. **加载时记录**：`_build_pools` 解析 `distribution_template` 时，直接存入 `PoolEntry.distribution_template`（字段已从 `distribution_file` 更名）
2. **保存时比较**：对于每个池子，如果 `distribution_template` 非空，重新执行 `_expand_template_with_bindings(基准模板, bindings)` 得到「模板展开结果」，与当前 `pool.distribution` 逐卡比较（`math.isclose(prob, tol=1e-6)`）
3. **判定**：
   - 相同 → 写入 `distribution_template = "模板名"`（不写内联分布）
   - 不同 → 写入内联 `[[pools.distribution]]`（不写 `distribution_template`），逐卡列出完整 `PoolDistEntry`
4. **模板本身**：`[[distribution_templates]]` 段从 `store._distribution_templates` 读取——该字段在 `load_toml` 时由 `_build_distribution_templates` 存入，无需额外 I/O 或外部传参

**`_save_templates_and_pools` 伪代码：**

```python
def _save_templates_and_pools(store, data):
    """将池子分布反向写入 TOML 结构。
    
    基准模板从 store._distribution_templates 读取（load_toml 时缓存）。
    """
    original_templates = store._distribution_templates  # dataclass field，load_toml 时缓存；直接访问 fail-fast 优于 getattr 静默降级
    data['pools'] = []
    used_templates = set()
    
    for pool in store.pools:
        pool_dict = {
            'id': pool.pool_id, 'name': pool.name,
            'pool_type': pool.pool_type,
            'start_day': pool.start_day, 'end_day': pool.end_day,
            'cost': pool.cost,
            'batch_size': pool.batch_size,
            'bindings': {k: v for k, v in pool.bindings.items() if k != 'type'},  <!-- REVIEW-R1-FIX: ISSUE-039 — 过滤冗余 type 键，避免与顶层 pool_type 重复 -->
            'target_cards': [cid for cid, _ in pool.target_specs],
        }
        
        # rerun_of / exchange_card_id 可选
        if pool.rerun_of:
            pool_dict['rerun_of'] = pool.rerun_of
        if pool.exchange_card_id:
            pool_dict['exchange_card_id'] = pool.exchange_card_id
        
        # 判定：模板引用 vs 内联分布
        template_name = pool.distribution_template
        if template_name and _distribution_matches_template(
            pool.distribution, template_name, pool.bindings, original_templates
        ):
            # 分布未被修改 → 写模板引用
            pool_dict['distribution_template'] = template_name
            used_templates.add(template_name)
        else:
            # 分布已被修改或无模板 → 写内联分布
            pool_dict['distribution'] = [
                {
                    'card_id': d.card_id,
                    'probability': d.probability,
                    'rarity': d.rarity,
                    'featured': d.featured,
                }
                for d in pool.distribution
            ]
        
        data['pools'].append(pool_dict)
    
    # 写被引用的模板
    data['distribution_templates'] = [
        t for t in original_templates if t['name'] in used_templates
    ]


def _distribution_matches_template(distribution, template_name, bindings, templates):
    """比较当前分布与模板展开结果是否一致（浮点容差 1e-6）。"""
    template = next((t for t in templates if t['name'] == template_name), None)
    if template is None:
        return False
    
    expanded = _expand_template_with_bindings(template['cards'], bindings)
    
    if len(distribution) != len(expanded):
        return False
    
    # 按 card_id 排序后逐卡比较
    dist_sorted = sorted(distribution, key=lambda d: d.card_id)
    exp_sorted = sorted(expanded, key=lambda d: d.card_id)
    
    for d, e in zip(dist_sorted, exp_sorted):
        if d.card_id != e.card_id:
            return False
        if d.rarity != e.rarity:
            return False
        if d.featured != e.featured:
            return False
        if not math.isclose(d.probability, e.probability, rel_tol=1e-6):
            return False
    
    return True
```

**`bindings` 中 `type` 键过滤说明：** `_build_pools` 为向后兼容 GUI 将 `pool_type` 双写到 `bindings['type']`（§2.8），但 `_save_templates_and_pools` 写出时顶层已有 `pool_type` 字段，bindings 表中的 `type` 键为冗余信息——TOML 文件中同时出现 `pool_type = "角色"` 和 `bindings = { type = "角色", ... }` 会令用户困惑。保存时过滤 `type` 键（`{k: v for k, v in pool.bindings.items() if k != 'type'}`），读路径不变（双写策略确保 GUI 旧读取路径 `bindings['type']` 仍可用）。<!-- REVIEW-R1-FIX: ISSUE-039 -->

---

### S2c：新建 `core/config_toml.py` — 模板展开与 GUI 双写验证（_expand_template_with_bindings + 集成测试，~1h）

> **本子步骤覆盖：** `_expand_template_with_bindings` 实现（绑定键展开、概率均分、featured 标记）+ GUI `pool_type` 双写逻辑代码审查与集成验证 + S2a/S2b-1/S2b-2 串联集成测试。<!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->
> **前置依赖：** S2a + S2b-1 + S2b-2（加载/保存路径均已实现，模板匹配逻辑已就绪）。

#### 2.7 不变部分（零逻辑改动——适用所有 S2a/S2b-1/S2b-2/S2c 子步骤）<!-- REVIEW-R1-FIX: GATE-1-变更粒度 -->

| 文件 | 原因 |
|------|------|
| `service/batch_simulator.py` (737行) | `SimulationEnvBuilder.from_config_store` 不变 |
| `core/strategy.py` / `core/pity.py`（保底引擎）/ `core/gdr.py` | 不依赖配置文件格式 |
| `core/streaming.py` | 不依赖配置文件格式 |

#### 2.8 GUI 适配注意事项（归属 S2c——模板展开与 GUI 双写验证子步骤）

<!-- REVIEW-R1-FIX: ISSUE-011 — pool_type 双写需求：GUI 通过 bindings['type'] 读写，TOML 使用顶层 pool_type -->

**`pool_type` 双写逻辑（`config_panel.py`）：**

`main_window.py:346` 和 `config_panel.py` 通过 `bindings.get('type', '角色')` / `bindings['type']` 读写池子类型，但新 TOML 格式使用顶层 `pool_type` 字段。`_build_pools` 需同步两处：

<!-- REVIEW-R1-FIX: AUDIT-BREAK-2 — pool_type 空字符串防护：pool_data.get('pool_type') 可能返回 ''（TOML 中显式写 pool_type=""），'' or '角色' 正确短路到默认值。直接写 '角色' 默认值而不依赖 .get() 的 default 参数——后者仅在 key 不存在时生效，key 存在但 value 为空字符串时不触发 -->
```python
# _build_pools 中——同时写 PoolEntry.pool_type 和 bindings['type']
# CRITICAL: 使用 `or '角色'` 而非 `.get('pool_type', '角色')`——
# TOML 中若显式写 pool_type = ""，.get() 返回 ''（非 None），
# '' or '角色' 正确短路到默认值；.get('pool_type', '角色') 仅在 key 缺失时回退
pool_entry.pool_type = pool_data.get('pool_type') or '角色'
pool_entry.bindings['type'] = pool_entry.pool_type  # 向后兼容，确保 bindings['type'] 永不为空字符串
```

<!-- REVIEW-R1-FIX: ISSUE-019 — 两处 PoolEntry 构造各添加 pool_type=pool_type 参数 -->
<!-- REVIEW-R1-FIX: ISSUE-020 — get_config() L2232 读取路径同步改为优先 pe.pool_type -->

**读路径（3 处）：**

| 位置 | 方法 | 当前代码 | 修改 | 说明 |
|------|------|---------|------|------|
| L2989 | `refresh_from_store_impl` | `pe.bindings.get('type', '角色')` | `pe.pool_type or pe.bindings.get('type', '角色')` | |
| L2232 | `get_config()` | `p.bindings.get('type', '角色') if p.bindings else '角色'` | `p.pool_type or (p.bindings.get('type', '角色') if p.bindings else '角色')` | |
<!-- REVIEW-R1-FIX: AUDIT-BREAK-2 — 双写策略下 bindings['type'] 可能为 ''（池子类型为空字符串时）。.get('type','角色') 在 key 存在但 value='' 时不触发 default，返回 ''→GUI 着色退化。统一使用 or 短路链 -->
| L346 | `_dispatch_simulation_results` | `pe.bindings.get('type', '角色') if pe.bindings else '角色'` | `pe.pool_type or pe.bindings.get('type', '角色') if pe.bindings else '角色'` | 空字符串防护：`or` 短路到默认值 |<!-- REVIEW-R1-FIX: ISSUE-042 -->

`get_config()` 方法用于序列化当前配置供下游面板（如模拟面板）使用，若不同步修改，当 pool_type 仅存储在 `PoolEntry.pool_type` 字段而不在 bindings 中时，下游面板将始终回退到 `'角色'`，接收错误的池子类型。

**写路径（2 处 PoolEntry 构造）：**

| 位置 | 说明 | 修改 |
|------|------|------|
| L2364-2375 | 第一处 PoolEntry 构造（从 dict 导入） | 添加 `pool_type=pool_type` 参数；同时 `distribution_file=f"pools/{pid}.txt"` → `distribution_template=""` |
| L2877-2888 | 第二处 PoolEntry 构造（从 GUI 表格行读取） | 同上——添加 `pool_type=pool_type` + `distribution_file`→`distribution_template` 改名 |

两处当前代码均仅将类型存入 `bindings['type']`（L2363/L2875），`PoolEntry.pool_type` 保持 dataclass 默认值空字符串 `''`。数据流断裂：GUI 编辑→`apply_to_store()`→pool_type 未设→Ctrl+S 调用 `save_toml` 读取 `pool_type=''`→TOML 写出空 pool_type→重载 `load_toml` 时 pool_type 为空→GUI 表格行着色退化。

<!-- REVIEW-R1-FIX: AUDIT-BREAK-5 --><!-- REVIEW-R1-FIX: AUDIT-BREAK-6 — 两处 PoolEntry 构造必须与 S2b-1 distribution_file→distribution_template 改名同 commit（G-ATOMIC-1） -->
**字段名正确性（阻断性检查）：** 若 S2b-1 已将 `PoolEntry.distribution_file` 改名为 `distribution_template`，但此两处构造仍写 `distribution_file=f"pools/{pid}.txt"`（旧字段名），Python 将抛出 `TypeError: PoolEntry.__init__() got an unexpected keyword argument 'distribution_file'`——GUI 启动时 `refresh_from_store_impl` 调用 `apply_to_store`→`PoolEntry(...)` 构造立即崩溃。修复：`distribution_file=f"pools/{pid}.txt"` → `distribution_template=""`（TOML 配置分布由内联 `[[pools.distribution]]` 承载，不再依赖外部 txt 文件）。此变更必须与 S2b-1 的 `config_store.py` 字段改名字同属 G-ATOMIC-1 commit。

**`config_panel.py` 修改量修正：** 原估计「仅 2 处改名」不准确——实际需处理 2 处读 + 2 处 PoolEntry 构造（各含 `pool_type=` 添加 + `distribution_file`→`distribution_template` 改名），共 ~4 处 `bindings['type']`/`pool_type` 读写点 + 2 处字段改名。

---

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — S3 实际工作量约 3-5 小时，拆为 S3a/S3b/S3c 三子步骤，每步控制在 ~1-1.5h -->
### S3a：替换 CLI 入口（cli.py 破坏性重写 + output_data 修复，~1h）

> **本子步骤覆盖：** `cli.py` 破坏性重写——删除 `json_config_to_store()` (96行) + 旧 JSON/硬编码路径；`-c`/`--config` 重定义为 TOML 路径；`--no-json` 删除；无参数时加载打包 `config.toml`；`output_data` 中 `config` 字段修复（`NameError` 防御）。
> **不涉及：** GUI 入口替换（→S3b）、文档/脚本/测试替换（→S3c）。

#### 3.1 CLI（`gacha_simulator/cli.py`）

<!-- REVIEW-R1-FIX: ISSUE-001 — 采用方案B：删除旧 JSON 路径，-c/--config 重定义为 TOML 路径 -->
<!-- REVIEW-R1-FIX: ISSUE-002 — json_config_to_store() + 三条旧加载路径全部删除 -->
<!-- REVIEW-R1-FIX: ISSUE-004 — 添加 else 分支：无参数时加载打包默认 config.toml 作为回退 -->

**破坏性变更声明：** `-c`/`--config` 标志从「JSON 配置文件路径」改为「TOML 配置文件路径」。旧 `default_config.json` 和 `json_config_to_store()` 函数（cli.py:29-125, 96 行）一并删除。无参数运行时自动加载打包默认 `config.toml`，不再硬编码合成 8 个池子。

**变更清单（cli.py）：**

| 行/区域 | 操作 | 说明 |
|---------|------|------|
| 29-125 | **删除** | `json_config_to_store()` 函数——96 行全删（合成 card_id 如 `f'{pid}_ssr'` 与 TOML 真实 card_id 不兼容） |
| 148（现有 `-c`/`--config`） | **修改** | `help` 文本从 `'Config file path'` 改为 `'TOML 配置文件路径（默认：打包 config.toml）'`；`default` 从 `'default_config.json'` 改为 `None` |
| 156 | **删除** | `--data-dir` 参数及其所有引用（包含在 L161-193 删除块中） |
| 161-193 | **删除** | JSON 覆盖路径 + 硬编码默认回退——全部替换为下方新逻辑 |

**新加载逻辑（替换 cli.py:161-193）：**

```python
from gacha_simulator.core.config_toml import load_toml

if args.config:
    # 用户指定 TOML 路径
    load_toml(args.config, store)
else:
    # 无参数 → 加载打包默认 config.toml
    from gacha_simulator.paths import get_config_dir
    default_toml = os.path.join(get_config_dir(), 'config.toml')
    load_toml(default_toml, store)
```

**`--no-json` 标志处理：** cli.py:150 的 `parser.add_argument('--no-json', ...)` 及其引用一并删除。此标志原用于跳过 JSON 覆盖层，新加载路径无 JSON 概念。

<!-- REVIEW-R1-FIX: ISSUE-018 — output_data 中 config 字段需同步处理，否则新加载路径下 NameError -->
**`output_data` 中 `config` 字段处理（cli.py:271-285）：**

当前代码 `output_data = {'config': config, ...}` 中的 `config` 变量由旧 L180（`config = json.load(f)` JSON 文件解析）或 L184（硬编码默认 `config = {...}`）赋值。S3.1 新加载逻辑将 L161-193 整体替换为 `load_toml()` 调用（上方伪代码 L418-427），`config` 变量不再被任何语句赋值——执行到 L271 时 Python 抛出 `NameError: name 'config' is not defined`。

**修复方案**（在伪代码中追加）：

```python
# 追加于新加载逻辑之后（cli.py:161-193 替换区域末尾）
# 为 output_data 构造 config 元数据 dict（替代旧 JSON config）
config_meta = {
    'path': str(args.config) if args.config else default_toml,
    'num_pools': len(store.pools),
    'num_cards': len(store.card_defs),
    'pity_enabled': store.pity.enabled,
    'num_targets': len(store.target_cards),
}
```

同步修改 cli.py:272 行——`'config': config` → `'config': config_meta`。

<!-- REVIEW-R1-FIX: AUDIT-BREAK-3 — cli.py 无 pytest 测试用例，NameError 在 pytest -q 下不可探测 -->
**关键验证（不可跳过）：** `cli.py` 当前无任何 pytest 测试覆盖——`output_data['config']=config` 若未修复，`pytest -q` 将照常通过（不执行 CLI 代码路径）。必须在 S3a 完成后手动执行 CLI 冒烟测试：

```bash
python -m gacha_simulator.cli -n 10 -w 2                    # 无 -c 参数→加载打包 config.toml
python -m gacha_simulator.cli -c gacha_simulator/config/config.toml -n 10 -w 2  # 指定 TOML 路径
```

若 `config` 变量悬空→`NameError: name 'config' is not defined` 在 L272 行触发，`pytest -q` 不会捕获。S6.3 的 CLI 验证步骤已覆盖此路径，但 S3a 实现时应立即自测而非等到 S6。

**`paths.py` 路径解析验证：** `-c` 默认值从 `'default_config.json'`（CWD 相对路径）改为 `None`→回退到 `get_config_dir() / 'config.toml'`。需确认 `gacha_simulator/paths.py` 已定义 `get_config_dir()` 且在打包/开发两种环境下均返回正确路径。若无 `paths.py`→`ImportError`；若 `get_config_dir()` 返回错误路径→`FileNotFoundError`。P50 可行性调查已确认该函数存在。

**替代方案（更简单）：** 仅记录 TOML 路径字符串——`'config': str(args.config) if args.config else default_toml`。该方案的优点是修改量最小（单行变动），但丢失了旧输出中 config dict 的结构化信息。推荐采用上方修复方案（保留结构化元数据，便于下游脚本解析）。

---

### S3b：替换 GUI 入口（main_window.py + config_panel.py + about_dialog.py，~1.5h）

> **本子步骤覆盖：** GUI 三文件——`main_window.py`（`_DEFAULT_CONFIG_DIR`→`_DEFAULT_CONFIG_FILE` + `load_store_from_directory`→`load_toml` + `save_store_to_directory`→`save_toml` + 模板匹配失败时的状态栏提示）+ `config_panel.py`（4 处 `pool_type` 读写点 + 2 处 `distribution_file`→`distribution_template` 改名 + 2 处 `PoolEntry` 构造添加 `pool_type=`）+ `about_dialog.py`（HTML 9 段 TOML 格式改写）。
> **前置依赖：** S3a（CLI 已切换到 TOML 加载路径，`load_toml`/`save_toml` 导入可用）。

#### 3.2 GUI（`gacha_simulator/gui/main_window.py`）

<!-- REVIEW-R1-FIX: ISSUE-014 — 使用 get_config_dir() 封装路径解析，兼容 PyInstaller 打包环境 -->
常量：

```python
# 旧
_DEFAULT_CONFIG_DIR = ...

# 新 — 使用 paths.py 封装，兼容开发与 PyInstaller 打包环境
from ..paths import get_config_dir
_DEFAULT_CONFIG_FILE = os.path.join(get_config_dir(), 'config.toml')
```

导入：

```python
# 旧
from ..core.config_io import load_store_from_directory, save_store_to_directory

# 新
from ..core.config_toml import load_toml, save_toml
```

调用：

```python
# _load_default_config —— load_store_from_directory(path, store) → load_toml(path, store)
# import_config —— 同上，path 变为 .toml 文件路径
# export_config —— save_store_to_directory(path, store) → save_toml(store, path)
```

<!-- REVIEW-R1-FIX: AUDIT-BREAK-4 — 参数顺序与文件对话框变更 -->
**参数顺序警告（阻断性）：** `save_toml(store, path)` 与 `save_store_to_directory(path, store)` 的 `store`/`path` 参数顺序**恰好颠倒**。旧调用为 `save_store_to_directory(path, store)`（path 在前），新调用为 `save_toml(store, path)`（store 在前）。若实现时疏忽写成 `save_toml(path, store)`，`path`（str）被当作 `ConfigStore` 传入→`tomli_w.dump()` 调用 `store.pools` 时触发 `AttributeError: 'str' object has no attribute 'pools'`。`main_window.py` 中 3 处调用点（`_load_default_config`/`import_config`/`export_config`）需逐一核对参数顺序。

**`import_config` 文件对话框变更：** 旧代码调用 `QFileDialog.getExistingDirectory`（返回目录路径）选择配置目录；TOML 迁移后改为 `QFileDialog.getOpenFileName`（返回文件路径 + 过滤器）。须设置 TOML 文件过滤器：

```python
path, _ = QFileDialog.getOpenFileName(
    self, "导入配置文件", "",
    "TOML 配置文件 (*.toml);;所有文件 (*)"
)
```

若忘记添加 `.toml` 过滤器→用户默认看到「所有文件」视图；若误用 `getExistingDirectory`→返回目录路径而非文件路径→`load_toml` 收到目录句柄→`open(path, 'rb')` 在 Windows 上触发 `PermissionError`。

**`export_config` 模板匹配失败提示：** 保存配置时若部分池子分布与模板不匹配（`_distribution_matches_template` 返回 `False`），`save_toml` 将回退到内联 `[[pools.distribution]]` 写出——数据不丢但 `config.toml` 中 `distribution_template` 引用消失、文件膨胀。`export_config` 调用后建议追加状态栏消息提示用户：

```python
# main_window.py export_config 方法中——save_toml 调用后
inline_count = sum(1 for p in store.pools if not p.distribution_template)
if inline_count > 0:
    self.statusBar().showMessage(
        f"配置已保存。{inline_count} 个池子使用内联分布（模板不匹配）。", 8000
    )
```

此为非阻断优化——不实现不影响正确性，但能避免用户困惑「为什么模板引用不见了」。

#### 3.3 验证脚本（`scripts/verify_p26_*.py`）

```python
# 旧
from gacha_simulator.core.config_io import load_store_from_directory
return load_store_from_directory(config_dir, store)

# 新
from gacha_simulator.core.config_toml import load_toml
return load_toml(os.path.join(config_dir, 'config.toml'), store)
```

#### 3.4 性能剖析脚本（`scripts/profile_*.py`）

3 个开发者工具脚本在顶部直接调用了 `load_store_from_directory`，需改为 `load_toml`：

| 文件 | 改动 |
|------|------|
| `scripts/profile_sim.py` | `load_store_from_directory(config_dir)` → `load_toml(config_toml_path)` |
| `scripts/profile_simulation.py` | 同上 |
| `scripts/profile_gui.py` | 同上 |

#### 3.5 测试辅助（`tests/core/test_batch_draw.py`）

<!-- REVIEW-R1-FIX: ISSUE-024 — 扩充为三步，覆盖模块级 PoolConfig 导入 + 两个测试函数处置，均在 S4.2 删除 PoolConfig 前完成 -->

**实施顺序约束：本步骤在 S4.2（删除 `PoolConfig` dataclass）之前执行。** L14 的 `from gacha_simulator.core.pool_config import PoolConfig` 是模块级导入，pytest 收集阶段即触发——若 S4.2 先删除 `PoolConfig`，`ImportError` 会导致整个测试文件（含 10 个仍有效的批次抽卡测试）无法收集，破坏门控 G3。

**三步操作：**

##### (a) 删除 L14 模块级 `PoolConfig` 导入行

```python
# 删除此行（pytest 收集阶段触发 ImportError 的根因）
from gacha_simulator.core.pool_config import PoolConfig
```

`test_batch_draw.py` 的生产代码路径（L26/44/55 使用 `parse_schedule_file` 构造测试数据）在下方 (c) 一并改为直接构造 `PoolEntry`，不再需要 `PoolConfig` 导入。

##### (b) 删除或改写 `test_pool_config_batch_size_default()`（L22-28）

该测试构造 `PoolConfig(...)` 验证 `batch_size` 默认值为 1。`PoolConfig` dataclass 在 S4.2 删除后此测试对象消失。

**推荐方案（改写为 `PoolEntry` 等效测试）：**

```python
# 旧：测试 PoolConfig.batch_size 默认值（L22-28）
def test_pool_config_batch_size_default():
    pc = PoolConfig(
        pool_id='test', name='test', start_day=0, end_day=21,
        cost_str='draw_resource:160', distribution_file='pools/test.txt',
    )
    assert pc.batch_size == 1

# 新：测试 PoolEntry.batch_size 默认值（语义等价，改换被测 dataclass）
def test_pool_entry_batch_size_default():
    pe = PoolEntry(
        pool_id='test', name='test', pool_type='角色',
        start_day=0, end_day=21, cost='draw_resource:160',
        distribution=[], distribution_template='',
    )
    assert pe.batch_size == 1
```

`PoolEntry` 的 `batch_size` 字段同样有默认值 `1`（`config_store.py`），改写后测试语义等价。

<!-- REVIEW-R1-FIX: AUDIT-BREAK-7 — PoolEntry 构造必须使用 distribution_template=（新字段名）而非 distribution_file=（旧字段名） -->
**字段名正确性检查：** 上方案例中 `PoolEntry(... distribution_template='')` 使用了 S2b-1 改名后的新字段名。若误写为 `distribution_file=''`（旧字段名），Python 将抛出 `TypeError: unexpected keyword argument 'distribution_file'`——pytest 收集阶段即失败，约 10 个有效批次抽卡测试全部丢失。S3c 中所有直接构造 `PoolEntry` 的测试代码（含 (b) 改写和 (c) 替换）均须使用 `distribution_template` 字段名。G3 门控（`pytest -q` 全通过）作为最后防线。

##### (c) 删除 `test_parse_schedule_with_batch_size`（L42-60）及 L44 延迟导入

L42-60 的测试构造临时 txt 文件并通过 `parse_schedule_file` 解析——该函数在 S4.2 删除。L44 的 `from gacha_simulator.core.pool_config import parse_schedule_file` 延迟导入一并删除。

L26/44/55 使用 `parse_schedule_file` 构造测试数据的其他引用点改为直接构造 `PoolEntry` 对象：

```python
# 旧：依赖 parse_schedule_file 解析临时 txt
configs, _ = parse_schedule_file(tmp.name)

# 新：直接构造 PoolEntry
pool_entry = PoolEntry(
    pool_id='test_pool',
    distribution=[PoolDistEntry(card_id='test_card', probability=100.0, rarity='ssr')],
    ...
)
```

#### 3.6 关于对话框（`gacha_simulator/gui/about_dialog.py`）

<!-- REVIEW-R1-FIX: ISSUE-009 — 配置文件指南 HTML 从 txt 格式改写为 TOML 格式说明 -->
<!-- REVIEW-R1-FIX: ISSUE-022 — 补全全部 9 个 TOML 段说明，与旧 txt 指南的 9 个主题一一对应 -->

```html
<h3>配置文件指南</h3>
<p>所有配置集中在单一 <code>config.toml</code> 文件中，使用标准 TOML 格式。</p>

<h4>[[cards]] — 卡牌定义</h4>
<pre>[[cards]]
id = "刻晴"
name = "刻晴"
rarity = "ssr"</pre>

<h4>[resources.defs] + [resources.initial] — 资源定义与初始资源</h4>
<pre>[resources.defs]
draw_resource = "抽卡资源"
exchange_currency = "兑换货币"

[resources.initial]
draw_resource = 1000
exchange_currency = 0</pre>
<p>对应旧 <code>resources.txt</code> + <code>initial_resources.txt</code></p>

<h4>[[resources.gain_rules]] + [[resources.day_overrides]] — 资源增益</h4>
<pre>[[resources.gain_rules]]
type = "every_n_days"
param = 7
gains = { draw_resource = 100 }

[[resources.day_overrides]]
day = 1
gains = { draw_resource = 500 }</pre>
<p>规则类型：<code>every_n_days</code>, <code>weekly</code>, <code>monthly_day</code>, <code>monthly_week</code>。对应旧 <code>gains.txt</code>。</p>

<h4>[[pools]] — 池子定义</h4>
<pre>[[pools]]
id = "pool_0"
name = "常驻池"
pool_type = "角色"
start_day = 0
end_day = 21
cost = "draw_resource:160"
batch_size = 1
distribution_template = "standard_character"
bindings = { ssr = "刻晴,莫娜", sr = "班尼特,行秋", r = "r1,r2" }
target_cards = ["刻晴"]</pre>
<p><b>费用语法</b>：<code>资源ID:数量</code>。多资源可用 <code>&gt;</code>（大于号）或 <code>,</code>（逗号）分隔，表示按书写顺序的<b>强制优先级</b>——先尝试排在前面的资源，不够再回退到后续资源。</p>
<p>示例：<code>exchange_currency:5 &gt; draw_resource:160</code> 表示优先消耗兑换货币，不足时再用抽卡资源。</p>
<p><code>&amp;</code> 表示同时需要多种资源（AND），<code>()</code> 用于分组。完整示例：<code>(draw_resource:160 &gt; exchange_currency:5) &amp; stardust:10</code></p>
<p><b>绑定键</b>：ssr, ssr_alt, ssr_alt1, ssr_alt2, featured, offrate, sr, r, rerun_of, exchange_card</p>
<p>可选字段：<code>rerun_of</code>（复刻，引用另一池子的分布）、<code>exchange_card_id</code>（兑换池，100% 出指定卡）。对应旧 <code>schedule.txt</code>。</p>

<h4>[[pity]] — 保底规则</h4>
<pre>[[pity]]
name = "ssr_soft"
type = "ssr"
start = 74
end = 90
func = "linear"
threshold = 180
reset = "any_ssr"
pools = ["*"]
target = { ssr = 1.0 }
counter_init = 0</pre>
<p>软保底参数：<code>start</code>（起始抽数）/ <code>end</code>（终止抽数）/ <code>func</code>（linear|exp|step）。硬保底参数：<code>threshold</code>（100% 触发抽数）。<code>reset</code> 值：any_ssr|featured_ssr|never。对应旧 <code>pity.txt</code>。</p>

<h4>[[targets]] — 目标卡</h4>
<pre>[[targets]]
card_id = "刻晴"
quantity = 2
pool_ids = ["pool_0", "pool_1"]</pre>
<p>对应旧 <code>targets.txt</code>。</p>

<h4>[[weights]] — 权重配置（可选）</h4>
<pre>[[weights]]
card_id = "刻晴"
desire = 2.0
miss_cost = 1.2
card_value = 1.5</pre>
<p>所有卡默认权重 1.0。desire_weight 影响前进法排序，miss_cost_weight 影响后退法排序，card_value 影响出卡价值计算。对应旧 <code>weights.txt</code>。</p>

<h4>[[distribution_templates]] — 池子分布模板</h4>
<pre>[[distribution_templates]]
name = "standard_character"
[[distribution_templates.cards]]
card_id = "ssr"
probability = 0.6
rarity = "ssr"
featured = true
[[distribution_templates.cards]]
card_id = "sr"
probability = 5.1
rarity = "sr"
[[distribution_templates.cards]]
card_id = "r"
probability = 94.3
rarity = "r"</pre>
<p>模板中的 <code>card_id</code> 为绑定键时（ssr/sr/r/ssr_alt 等），加载时按池子的 <code>bindings</code> 展开为具体卡牌并均分概率。对应旧 <code>pools/*.txt</code> 分布文件。</p>
```
<!-- REVIEW-R1-FIX: ISSUE-022 -->

#### 3.6b PyInstaller 打包验证（~5min）

**文件：** `GachaStat.spec`

当前 L19 的 `datas` 配置为：

```python
datas=[
    ('gacha_simulator/config', 'config'),   # 打包整个 config/ 目录
    ...
],
```

P53 执行后 `gacha_simulator/config/` 目录中旧 txt 文件全部删除，仅保留 `config.toml`。`datas` 行绑定的是**整个目录**——配置无需修改。

**验证步骤：**

1. 确认 `GachaStat.spec:19` 的 `('gacha_simulator/config', 'config')` 行存在且未变更
2. 确认 `gacha_simulator/config/` 目录中旧 txt 文件已删除（`cards.txt`/`gains.txt`/`initial_resources.txt`/`pity.txt`/`resources.txt`/`schedule.txt`/`pools/*.txt`）
3. 确认 `gacha_simulator/config/config.toml` 文件存在
4. 确认 `paths.py:get_config_dir()` 返回的路径在开发环境指向 `gacha_simulator/config/`

PyInstaller 构建后验证：

```bash
# 打包后检查 _internal/config/ 目录内容
pyinstaller GachaStat.spec --noconfirm
# 检查 dist/GachaStat/_internal/config/ 仅含 config.toml
```

---

### S3c：替换文档 + 脚本 + 测试入口（CONTRIBUTING.md + CLAUDE.md + 脚本 + test_batch_draw.py，~1h）

> **本子步骤覆盖：** 文档三文件（`CONTRIBUTING.md` L18-25 配置文件树 + L12 注释 + L40/L42 禁止规则更新 + 引导文字；`CLAUDE.md` L26/L62/L72 三行引用修正）+ 5 个脚本（`verify_p26_pity_causality.py` / `verify_p26_integration.py` / `profile_gui.py` / `profile_sim.py` / `profile_simulation.py`——`load_store_from_directory`→`load_toml`）+ 1 个测试文件（`test_batch_draw.py` 三步处置：删除 L14 导入 + 改写 `test_pool_config_batch_size_default` + 删除 `test_parse_schedule_with_batch_size`）。
> **前置依赖：** S3a + S3b（CLI + GUI 已切换到新接口，`load_toml`/`save_toml` 公共 API 稳定）。

#### 3.7 贡献者指南（`CONTRIBUTING.md`）

<!-- REVIEW-R1-FIX: ISSUE-010 — 新增独立实施步骤，替换 L18-25 旧 txt 配置文件树 -->
<!-- REVIEW-R1-FIX: ISSUE-017 — CONTRIBUTING.md 遗留缺口闭环：锚点+步骤+替换文本三合一 -->

`CONTRIBUTING.md` 第 18-25 行当前列出 7 个旧 txt 配置文件（`cards.txt`/`gains.txt`/`initial_resources.txt`/`pity.txt`/`resources.txt`/`schedule.txt`/`pools/`），迁移后全部过时。新贡献者看到的配置文件树指向一个已不存在的 txt 文件体系，产生误导。

**替换文本**（替换 L18-25 的 `config/` 子树）：

```
├── config/              # 默认配置文件
│   └── config.toml      # 统一 TOML 配置文件
```

**同步修改 L17 行注释**（将「默认配置文件」改为更具体的说明）：

```
├── config/              # 默认 TOML 配置文件（单文件）
```

**说明文字**（在文件树下方补充一行引导）：

```
> 配置文件格式为 TOML。完整格式说明见 GUI 关于对话框（帮助→关于→配置文件指南 Tab），
> 或直接阅读 `gacha_simulator/config/config.toml` 中的注释。
```

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — L12→L17（config/注释行实际位置） -->
**修改量：** 3 行替换（L18-25 子树 → 单行 `config.toml`）+ 1 行注释更新（L17）+ 1 行引导文字。共 ~5 行变更。

<!-- REVIEW-R1-FIX: ISSUE-026 — L42 pyproject.toml 禁止规则与 P53 S1 依赖变更矛盾 -->
**`pyproject.toml` 禁止规则更新（L42）：** `CONTRIBUTING.md` 第 37-44 行将 `pyproject.toml` 列入「禁止修改的路径」表格，标注为「项目配置文件」。但 P53 的 S1 步骤明确修改 `pyproject.toml` 以添加 `tomli>=2.0` 和 `tomli-w>=1.0` 运行时依赖——若不同步更新此规则，未来审阅 PR 的贡献者可能据此认为 P53 的 `pyproject.toml` 修改不合规。

**修复**（与 L18-25 配置文件树更新一并提交）：

将 L42 行说明从「项目配置文件」改为明确授权说明：

```
| `pyproject.toml` | 项目配置文件——计划性架构迁移（如 P53 添加 TOML 依赖）可修改 |
```

或采用更简洁的脚注形式：

```
| `pyproject.toml` | 项目配置文件（计划性架构迁移授权修改） |
```

此变更不阻塞代码执行但消除贡献者指南与迁移计划的规范性矛盾。

<!-- REVIEW-R1-FIX: ISSUE-032 -->
**`tests/` 禁止规则更新（L40）：** `CONTRIBUTING.md` 第 40 行将 `tests/` 列入「禁止修改的路径」表格，标注为「测试目录」。但 P53 计划将对 tests/ 执行：新建 2 个文件（`test_config_toml.py`、`test_streaming.py`）、删除 3 个文件（`test_config_io.py`、`test_pool_config_parse.py`、`verify_toml_equivalence.py`）、修改 1 个文件（`test_batch_draw.py`）——合计 6 个测试文件操作。若不同步更新，未来审阅者可能依据此规则认为 P53 的测试文件变更不合规。

**修复**（与 pyproject.toml 行一并提交）：

将 L40 行说明从「测试目录（单元测试、测试输出等）」改为授权说明：

```
| `tests/` | 测试目录——计划性架构迁移（如 P53）可添加/删除/修改配套测试 |
```

或采用统一句式与 pyproject.toml 行对齐：

```
| `tests/` | 测试目录（计划性架构迁移授权修改） |
```

推荐后者，与 L42 pyproject.toml 行格式一致，审阅者一眼可识别两类路径均受迁移计划授权。

---

#### 3.8 项目指令文件（`CLAUDE.md`）

<!-- REVIEW-R1-FIX: ISSUE-038 — CLAUDE.md 含 3 处过时引用，P53 执行后变为错误信息，需纳入文档同步范围 -->

**文件：** `CLAUDE.md`

P53 执行后，CLAUDE.md 中 3 处引用将指向已不存在的 `config_io.py` 和 txt 文件体系，需同步更新。

**3 处修改：**

| 行 | 当前内容 | 修改 |
|----|---------|------|
| L26 | `├── config/     # 配置文件（\| 分隔文本格式）` | `├── config/     # 配置文件（TOML 格式，单文件 config.toml）` |
| L62 | `配置文件 \| 分隔文本 → config_io.py 读写（schedule.txt/pools/*.txt/pity.txt/targets.txt/gains.txt/cards.txt/resources.txt/initial_resources.txt）` | `配置文件 TOML 格式 → config_toml.py 读写（单一 config.toml）` |
| L72 | `\| 新配置项 \| ConfigStore → config_io.py → config_panel.py → SimulationEnvBuilder \|` | `\| 新配置项 \| ConfigStore → config_toml.py → config_panel.py → SimulationEnvBuilder \|` |

**修改量：** 3 行替换，~3 行变更。无新增导入或逻辑改动——仅修正过时文件路径与格式描述。

---

### S4：删除旧解析器代码

<!-- REVIEW-R1-FIX: ISSUE-012 — S3→S4 硬性门控：S3a/S3b/S3c 完成验证是 S4 执行的前置条件 --><!-- REVIEW-R1-FIX: GATE-1-变更粒度 — 门控引用从 S3 更新为 S3a/S3b/S3c -->
**实施顺序约束：S3a/S3b/S3c（替换 CLI/GUI/文档/脚本入口，原 S3）和 S5.0（等价性验证）必须在 S4（删除旧代码）之前完成并验证通过。**

**S4 执行前门控（三条全部 PASS 方可进入 S4）：**

| 门控 | 验证命令/方法 | 说明 |
|------|-------------|------|
| G1 | `grep -rn "parse_schedule_file\|...\|CardCatalog" --include="*.py" .` | S4.0 全局搜索确认无遗漏引用——所有命中项已在新导入路径中替换 |
| G2 | `python tests/verify_toml_equivalence.py` | S5.0 等价性验证全部 PASS——旧解析器与 TOML 解析器输出一致 |
| G3 | `pytest -q` | 全部通过——S3a/S3b/S3c 的新导入路径未破坏现有测试 |

无迁移脚本依赖后，旧代码**全部删除**，不做保留。

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — S4.0 预估 5min -->
#### S4.0 删除前预检（全局搜索确认无遗漏引用，~5min）

在删除任何代码前，先执行全局搜索，将输出与文件结构表逐一核对：

```bash
<!-- REVIEW-R1-FIX: ISSUE-023 — 移除幽灵函数 load_multi_config_from_directory（代码库中从未存在，load_config_from_directory 已覆盖） -->
grep -rn "parse_schedule_file\|parse_distribution_file\|parse_cards_file\|parse_pity_file\|parse_gains_file\|parse_resources_file\|load_store_from_directory\|save_store_to_directory\|load_config_from_directory\|json_config_to_store\|build_pity_engine\|PoolConfig\|CardDef\|CardCatalog" --include="*.py" .
```

核对清单：
1. 所有命中项均在 §二 文件结构表的「修改」或「删除」清单中
2. 如有不在清单中的命中项 → 先更新文件结构表，再继续
3. 确认 `scripts/` 目录下未被文件结构表覆盖的文件（`verify_p26_claims.py`、`benchmark_chart.py`）无对旧符号的引用
4. ~~运行 `pytest -q` 确认当前测试全部通过（建立基线）~~ → **移至 S3c 最后一步作为门控 G3**

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — S4.1 预估 5min -->
#### S4.1 `gacha_simulator/core/config_io.py` → 删除整个文件（~5min）

625 行全删。包含：
- `load_store_from_directory` / `save_store_to_directory`
- 全部 `_load_*` / `_save_*` 函数
- `_get_ssr_ids_from_bindings` / `_get_sr_ids_from_bindings` / `_get_featured_ids_from_bindings` 等辅助函数
- `_parse_resource_amount` / `_normalize_rule_type`

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — S4.2 预估 5min（整文件删除，无 import 清理或保留函数验证） -->
#### S4.2 `gacha_simulator/core/pool_config.py` → 删除整个文件（~5min）

**整文件删除。** 唯一保留函数 `_expand_binding()` 已在 S2a 迁移至 `config_toml.py`，旧 `parse_*`/`load_*` 函数 + `PoolConfig`/`CardDef`/`CardCatalog` dataclass 均已无调用方，一并删除。

删除清单：
- `parse_schedule_file` (~88 行)
- `parse_distribution_file` (~84 行)
- `parse_cards_file` (~43 行)
- `load_config_from_directory` (~91 行)
- `PoolConfig` / `CardDef` / `CardCatalog` dataclass
- 所有顶层 import 语句（`import os`/`import re`/`from .pool import ...`/`from .schedule import ...`/`from .target_card import ...`/`from .pity import ...`）
- `_expand_binding`（已迁移至 `config_toml.py:S2a`——本文件中的副本不再需要）

**原子提交约束：** S4.2 与 S4.5（`__init__.py` 删除旧 re-export）必须属于同一 G-ATOMIC-2 commit——若 `pool_config.py` 已删除但 `__init__.py` 仍执行 `from .pool_config import ...`，`import gacha_simulator.core` 触发 `ImportError`（`ModuleNotFoundError: No module named 'gacha_simulator.core.pool_config'`）。

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — S4.3 预估 10min -->
#### S4.3 `gacha_simulator/core/pity.py` → 裁剪（~10min）

<!-- REVIEW-R1-FIX: ISSUE-013 — 明确 build_pity_engine 一并删除 -->
删除：
- `parse_pity_file` (~62 行)
- `build_pity_engine` (~31 行, pity.py:344-374)——唯一调用方 `load_config_from_directory` 已在 S4.2 删除，保留则为不可达死代码；其参数签名（接受 `config_dir` 读 `pity.txt`）与 TOML 新世界完全无关

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — S4.4 预估 10min -->
#### S4.4 `gacha_simulator/core/resource_gain.py` → 裁剪（~10min）

<!-- REVIEW-R1-FIX: ISSUE-025 — 追加五个私有辅助函数删除，parse_gains_file 删除后唯一调用方消失 -->
删除：
- `parse_gains_file` (~117 行)——早已标记 `DeprecationWarning`，生产代码零调用
- `parse_resources_file` (~21 行)
- `_parse_resource_amount` (L107-114)、`_weekday_of_day` (L117-121)、`_month_of_day` (L124-128)、`_day_of_month` (L131-135)、`_week_of_month` (L138-142)——五个私有辅助函数的唯一调用方恰是 `parse_gains_file`，S4.4 删除后变为不可达死代码（合计 ~36 行）。不触发 ImportError 或运行时异常，但残留在模块中增加后续维护认知负担。S4.0 全局 grep 模式不包含这些私有函数名，需显式列出

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — S4.5 预估 10min -->
#### S4.5 `gacha_simulator/core/__init__.py` → 更新 re-export（~10min）

<!-- REVIEW-R1-FIX: ISSUE-005 — 精确列出 __all__ 修改清单，含逐项验证命令 -->

**import 语句变更（第 11 行附近）：**

```python
# 删除
from .pity import (
    ...,
    parse_pity_file, build_pity_engine,   # 移除这两个符号
)
from .pool_config import parse_schedule_file, parse_distribution_file, parse_cards_file, load_config_from_directory, PoolConfig, CardDef, CardCatalog  # 整行删除——pool_config.py 已整文件删除

# 新增
from .config_toml import load_toml, save_toml
```

**`__all__` 精确修改清单：**

| 位置 | 操作 | 符号 |
|------|------|------|
| 第 94 行 | **删除** | `'parse_pity_file'`, `'build_pity_engine'` |
| 第 111 行 | **删除** | `'PoolConfig'`, `'CardDef'`, `'CardCatalog'`, `'parse_schedule_file'`, `'parse_distribution_file'`, `'parse_cards_file'`, `'load_config_from_directory'` |
| 末尾 | **新增** | `'load_toml'`, `'save_toml'` |

<!-- REVIEW-R1-FIX: AUDIT-BREAK-9 — S4.5 必须与 S4.2-S4.4 同属 G-ATOMIC-2 commit；ruff check 零 F822/F401 -->
**原子提交约束：** S4.5 必须与 S4.2（删除 pool_config.py 整文件）、S4.3（删除 pity.py parse_pity_file/build_pity_engine）、S4.4（删除 resource_gain.py parse_*）同属 G-ATOMIC-2 commit。若 S4.2 删除了 `pool_config.py` 但 S4.5 的 `__init__.py:37` 仍执行 `from .pool_config import ...`→`ModuleNotFoundError: No module named 'gacha_simulator.core.pool_config'`（`import gacha_simulator.core` 整个模块不可用）。

**验证命令：**

```bash
python -c "from gacha_simulator.core import load_toml, save_toml"     # 新接口可用
python -c "from gacha_simulator.core import parse_schedule_file"      # 应触发 ImportError——正确行为
python -c "from gacha_simulator.core.pool_config import PoolConfig"   # 应触发 ModuleNotFoundError——pool_config.py 已整文件删除
ruff check gacha_simulator/core/__init__.py                            # 零 F822（__all__ 中未定义符号）
ruff check gacha_simulator/core/                                       # 零 F401（unused-import）
```

---

### S5：测试

#### S5.0 迁移前等价性验证（一次性）

在删除旧解析器前，运行 `tests/verify_toml_equivalence.py` 确认 `config.toml` 与原始 10 个 txt 配置文件完全等价：

```bash
python tests/verify_toml_equivalence.py
```

要求：全部 PASS。该脚本在 S4 旧解析器删除后一并删除（一次性验证工具）。

<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — S5.1 拆为 S5.1a（基础加载/保存/边界测试，10 个用例，~1h）和 S5.1b（模板匹配+契约测试，14 个用例，~1h），两批间通过 pytest 当前通过率隔离 -->
#### S5.1a 新建 `tests/core/test_config_toml.py` — 基础加载/保存/边界测试（~1h）

> **本批覆盖：** 基础 TOML 加载/保存/边界测试，验证 `load_toml` 和 `save_toml` 基本功能与各段 `_build_*` helper 的正确性。
> **前置依赖：** S2b-1（`save_toml` 骨架已实现，基本往返可验证）。

| 测试 | 覆盖 |
|------|------|
| `test_load_default_config` | 加载默认 `config.toml` → 验证 8 池/24 卡/1 保底/6 目标/24 权重 |
| `test_load_missing_file_raises` | 加载不存在的文件 → FileNotFoundError |
| `test_load_invalid_toml_raises` | 加载语法错误的 TOML → tomllib.TOMLDecodeError |
| `test_save_and_reload_roundtrip` | 加载 → 保存 → 重新加载 → 两次加载的 ConfigStore 等价 |
| `test_template_expansion` | 验证 `_expand_template_with_bindings`：`ssr` 绑定 1 卡 → 1 个 PoolDistEntry(prob=原值)；`ssr_alt` 绑定 6 卡 → 6 个 PoolDistEntry(prob=原值/6) |
| `test_template_expansion_no_binding` | 验证 `card_id` 不在 bindings 中时直接作为 card_id（不展开） |
| `test_hard_pity_threshold` | 验证 `threshold` 字段正确加载到 `PityDef.params['threshold']` |
| `test_weights_array_format` | 验证 `[[weights]]` 数组表 → 24 个 `CardWeightEntry` |
| `test_rerun_of_pool` | 验证 `rerun_of` 字段：池子引用另一池子的分布 |
| `test_exchange_card_pool` | 验证 `exchange_card_id` 字段：兑换池 100% 出指定卡 |

---

#### S5.1b 新建 `tests/core/test_config_toml.py` — 模板匹配+契约测试（~1h）

> **本批覆盖：** 各段 `_build_*` helper 独立验证 + `save_toml` 模板匹配契约测试（模板引用保留、修改回退内联、容差边界、字段不匹配）。
> **前置依赖：** S2b-2（`_save_templates_and_pools` + `_distribution_matches_template` 已实现）+ S5.1a（基础测试全部通过，pytest 通过率已建立基线）。

| 测试 | 覆盖 |
|------|------|
| `test_build_resources` | 验证 `[resources.defs]` + `[resources.initial]` → `store.resource_defs` / `store.initial_resources` |
| `test_build_gain_rules` | 验证 `[[resources.gain_rules]]` → `store.gain_rules` |
| `test_build_day_overrides` | 验证 `[[resources.day_overrides]]` → `store.day_overrides` |
| `test_build_cards` | 验证 `[[cards]]` → `store.card_defs` |
| `test_build_targets` | 验证 `[[targets]]` → `store.target_cards` |
| `test_save_toml_template_roundtrip` | 加载 → 保存 → 重新加载，验证 `distribution_template` 引用保留 |
| `test_target_cards_to_target_specs` | 验证 `["card_id"]` → `[("card_id", 1)]` 转换 |
| `test_load_toml_store_none_creates_new` | 验证 `load_toml(path)` → 自动创建并返回新 `ConfigStore` |
| `test_load_toml_store_existing_clears` | 验证传入已有 `store` → `store.clear()` 后加载，返回同一实例 |
| `test_save_modified_distribution_falls_back_to_inline` | 修改分布后保存 → 验证内联 `[[pools.distribution]]` 写出而非 `distribution_template` 引用 |
| `test_distribution_matches_template_tolerance_boundary` | 概率差 `1e-7` → 判定匹配；概率差 `1e-5` → 判定不匹配。**注意：测试概率基数须与实现 `rel_tol=1e-6` 对应的等效绝对容差匹配**——以 `probability=0.6`（0.6%）为基数时 `rel_tol=1e-6` → 绝对容差 ~`6e-7`，`1e-7` 小于此值（判定匹配）、`1e-5` 大于此值（判定不匹配）。若以 `probability=100.0` 为基数则绝对容差为 `1e-4`，两个用例判定会反转——测试中须固定使用与默认模板概率规模一致的基数 |
| `test_distribution_template_not_found` | 引用不存在的模板名 → `_distribution_matches_template` 返回 `False` → 回退内联分布 |
| `test_distribution_length_mismatch` | 分布长度与模板展开结果不一致 → `_distribution_matches_template` 返回 `False` |
| `test_distribution_field_mismatch` | `card_id`/`rarity`/`featured` 任意字段与模板不匹配 → 返回 `False` |

#### S5.2 旧测试文件处理

<!-- REVIEW-R1-FIX: ISSUE-007 — 提取 TestStreaming 类到独立测试文件再删除 -->
<!-- REVIEW-R1-FIX: ISSUE-008 — CardCatalog 随 dataclass 一并删除（ISSUE-015），其测试合理删除，此处确认无遗漏 -->

##### S5.2a 提取 `TestStreaming` 类（执行于删除前）

`tests/core/test_config_io.py` 第 166-202 行包含 `TestStreaming` 类（4 个测试方法：`test_shared_result_collector_creation` / `test_extract_aggregate` / `test_streaming_success_counter` / `test_merge_extraction_packets_empty`），测试对象为 `streaming.py` 模块——与 `config_io` 或任何 `parse_*` 函数完全无关。删除 `test_config_io.py` 前提取到新文件：

| 新文件 | 来源 | 测试方法数 |
|--------|------|-----------|
| `tests/core/test_streaming.py` | `test_config_io.py` L166-202 | 4 |

##### S5.2b 确认 `TestCardCatalog` 处置

`tests/core/test_pool_config_parse.py` 的 `TestCardCatalog` 类（4 个测试方法）随 `CardCatalog` dataclass 一并删除——该 dataclass 在 ISSUE-015 决议中确认无生产代码调用方。<!-- REVIEW-R1-FIX: GATE-1-变更粒度 — TestConfigIOSaveLoad→TestPoolConfig（test_config_io.py:117 实际类名） -->
同时 `TestPoolConfig`（2 个测试方法）因 `config_io.py` 删除而合理删除。

##### S5.2c 执行删除

- `tests/core/test_config_io.py` → 删除（`TestStreaming` 已提取；其余测试对象已不存在）
- `tests/core/test_pool_config_parse.py` → 删除（测试对象 `parse_*` 函数 + `CardCatalog` 已删除）
- `tests/verify_toml_equivalence.py` → 删除（一次性验证工具，使命完成）

---

### S6：回归验证

#### 6.1 测试回归

```bash
pytest -q --cov=gacha_simulator --cov-report=term
```

要求：全部通过，覆盖率不下降。

#### 6.2 GUI 手动验证

1. 启动 GUI：`python -m gacha_simulator.main`
2. 确认配置面板正确显示 8 个池子、24 张卡、1 条保底
3. Ctrl+S 保存 → 重启 GUI → 重新加载 → 配置不丢失
4. 修改池子分布 → 保存 → 重启 → 修改保留

#### 6.3 CLI 验证

```bash
python -m gacha_simulator.cli --config gacha_simulator/config/config.toml -n 10 -w 2
```

---

## 四、风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| `save_toml` 模板匹配误判：用户微调分布后被判定为"与模板相同"而丢失修改 | 低→中 | 中 | 比较时使用 `math.isclose(prob1, prob2, rel_tol=1e-6)` 浮点容差；`store._distribution_templates` 作为比较基准（load_toml 时缓存，自包含、无额外 I/O）；S5.1 新增 4 个边界测试覆盖所有分支 |
| 删除 `parse_*` 函数破坏未被搜索到的调用方 | 低 | 高 | S4.0 预检步骤 + S3a/S3b/S3c→S4 门控 G1——全局搜索确认无遗漏引用（含 `scripts/` 和 `tests/`）；`pytest -q`（门控 G3）作为最后防线 |
| 旧脚本/用户工具引用 `--data-dir` | 低 | 低 | CLI 采用破坏性变更——`-c`/`--config` 直接重定义为 TOML 路径，argparse 自动拒绝未知参数；帮助文本明确说明 |
| 旧脚本引用 `--no-json` 或依赖 `json_config_to_store` | 低 | 低 | 与 `--config` 同批次删除——若用户有外部脚本依赖 CLI 的 JSON 加载，需同时更新。计划明确标注为破坏性变更 |
| `tomli-w` 输出格式与用户手工编辑预期不一致 | 低 | 低 | `tomli-w` 输出确定性格式；用户首次保存后即适应该格式 |
| `config.toml` 未覆盖的边界情况（如资源池、兑换池、武器池等当前 txt 中不存在的池子类型） | 低 | 低 | 默认 `config.toml` 仅覆盖 8 个角色池场景；`_build_pools` 保留 `exchange_card_id`/`rerun_of`/内联 `[[pools.distribution]]` 三条路径以兼容未来扩展 |
| `pool_type` 双写遗漏——GUI 编辑→保存→重载后类型信息丢失 | 低→中 | 中 | 计划 §2.8 明确双写逻辑：`_build_pools` 同时写 `PoolEntry.pool_type` + `bindings['type']`（使用 `or '角色'` 短路空字符串）；`config_panel.py` 读路径优先 `pe.pool_type`，写路径双写 |
| **G-ATOMIC-1 违反**：`distribution_file`→`distribution_template` 改名与调用方（`retreat_config.py`/`config_panel.py`×2）不同 commit | 中 | **高** | §二-A 明确原子提交约束——S2b-1+S3b+S5 的 retreat_config.py 修改必须在同一 commit。GUI 启动→`TypeError` 或 `AttributeError` 直接崩溃 |
| **G-ATOMIC-2 违反**：S4.2 删除 pool_config.py 整文件与 S4.5 `__init__.py` re-export 更新不同 commit | 中 | **高** | §二-A 明确 S4.2+S4.3+S4.4+S4.5 必须同一 commit。`import gacha_simulator.core`→`ModuleNotFoundError` 整个模块不可用 |
| TOML 注释丢失——`tomli_w.dump()` 不保留注释，用户保存后文件头以外的注释全部消失 | 高 | 低 | `save_toml` 在文件开头手动写入语法速查头块（~10 行）；完整格式说明见 GUI 帮助→关于→配置文件指南（S3b §3.6 已覆盖 9 段 TOML 格式 HTML）；此为 TOML 格式的已知限制——标准库 `tomllib`/`tomli-w` 均不支持注释往返 |
| `pool_type` 空字符串 `''` 导致 `.get('type','角色')` 不触发 default→GUI 着色退化 | 低→中 | 低 | `_build_pools` 使用 `pool_data.get('pool_type') or '角色'`（`or` 短路空字符串）；L346 `_dispatch_simulation_results` 同步改为 `pe.pool_type or pe.bindings.get(...)` |
| `save_toml(store, path)` 与 `save_store_to_directory(path, store)` 参数顺序颠倒 | 低→中 | 中 | §3.2 main_window.py 显式警告——3 处调用点逐一核对参数顺序；若写成 `save_toml(path, store)`→`AttributeError: 'str' object has no attribute 'pools'` |
| Python 3.10 `tomllib` 不可用 | 低 | 高 | S1 添加 `tomli>=2.0` 条件依赖 + `config_toml.py` 顶部 try/except 导入回退 |

<!-- REVIEW-R1-FIX: GATE-5-回滚路径 — 新增回滚策略小节 -->
### 四-B：回滚策略

本计划涉及大量删除操作（S4 整节），回滚路径按执行阶段分级：

**S1-S3 阶段（新增与修改，无删除）：**
- S1（`pyproject.toml` 添加依赖）：`git checkout -- pyproject.toml` 回滚，`pip install -e ".[dev]"` 恢复
- S2a/S2b-1/S2b-2/S2c（`config_toml.py` 新建 + `config_store.py`/`retreat_config.py` 字段修改）：新增文件直接 `git rm` 删除；修改文件 `git checkout -- <path>` 逐文件还原
- S3a/S3b/S3c（CLI/GUI/文档/脚本/测试入口替换）：每文件可独立 `git checkout -- <path>` 回滚，修改互不依赖

**S4 阶段（不可逆删除）：**
- S4.0 预检是闸门——全局搜索确保无遗漏引用后方可进入 S4.1
- S4.1-S4.5 为原子删除步骤：5 个子步骤应在**同一 commit** 中完成，确保 `git diff` 清晰展示删除面
- 门控 G1+G2+G3（§三 S4 执行前门控表）为最后防线——三条全部 PASS 方可进入 S4
- **S4 执行后唯一回滚方案：`git revert <commit>`**——因此 S4 必须独立为一个 commit（`feat: S4 删除旧解析器代码`），不可与 S1-S3 或 S5-S6 的变更混在同一个 commit 中

**S5-S6 阶段（测试与回归验证）：**
- S5 新建测试文件：`git rm` 删除

**建议 commit 拆分方案：**

| Commit | 范围 | 回滚方式 |
|--------|------|---------|
| `feat: S1 添加 TOML 依赖` | S1 | `git revert` 或 `git checkout` |
| `feat: S2 config_toml.py 加载保存路径` | S2a+S2b-1+S2b-2+S2c | `git revert` |
| `feat: S3 替换 CLI/GUI/文档入口` | S3a+S3b+S3c | `git revert` |
| `feat: S4 删除旧解析器代码` | S4.0-S4.5（原子） | **仅 `git revert`** |
| `test: S5 新增 TOML 测试` | S5.0-S5.2c | `git revert` |
| `chore: S6 回归验证` | S6.1-S6.3 | `git revert` |

S4 的独立 commit 是最关键约束——若 S4 后发现 S6 回归验证失败，`git revert` S4 commit 即可恢复全部旧解析器代码，无需手动重写。

---

## 五、验收标准

1. `python tests/verify_toml_equivalence.py` 全部通过（旧解析器删除前，一次性验证）
2. `tomllib.load()` 正确解析默认 `config.toml`，`pytest -q` 零失败
3. `pytest -q --cov=gacha_simulator --cov-report=term` 覆盖率不低于当前基线
4. GUI 启动 → 加载 `config.toml` → 配置面板显示 8 池/24 卡/1 保底/6 目标/24 权重
5. GUI 修改配置 → Ctrl+S 保存 → 重启 → 重新加载 → 配置不丢失
6. `python -m gacha_simulator.cli --config config.toml -n 10` 正常运行
7. 两个 `verify_p26_*.py` 脚本使用 `load_toml` 正常运行
8. 3 个 `profile_*.py` 脚本使用 `load_toml` 正常运行
<!-- REVIEW-R1-FIX: ISSUE-023 — 移除幽灵函数 load_multi_config_from_directory（天然零结果丧失鉴别力） -->
9. 旧 `parse_*` 函数已删除——`grep "parse_schedule_file\|parse_distribution_file\|parse_cards_file\|parse_pity_file\|parse_gains_file\|parse_resources_file\|load_store_from_directory\|save_store_to_directory\|load_config_from_directory\|json_config_to_store\|build_pity_engine\|PoolConfig\|CardDef\|CardCatalog" gacha_simulator/ scripts/ tests/ -r` 无结果（排除 `verify_toml_equivalence.py`——该文件本身在 S5 中删除）
10. `config_io.py` 文件已删除
11. `pool_config.py` 文件已删除——`_expand_binding` 已迁移至 `config_toml.py`，旧 `PoolConfig`/`CardDef`/`CardCatalog` dataclass 无残留
12. `gacha_simulator/config/` 目录中旧 txt 文件（`cards.txt`/`gains.txt`/`initial_resources.txt`/`pity.txt`/`resources.txt`/`schedule.txt`/`pools/*.txt`）全部删除，仅保留 `config.toml`

---

## 附录 A：与 P49 的关系

P49 修复 txt 格式两个 bug → P53 直接删除整条 txt 解析链路。

**策略：跳过 P49，直接执行 P53。** P49 发现的 D1（分布文件扁平格式无法解析）和 D2（GUI 保存后 bindings 丢失）的根因均在 `config_io.py` + `pool_config.py` 的 txt 解析器链路中——该链路在 S4 中被整体删除。无需修复 bug，直接移除有 bug 的代码。

## 附录 B：变更日志

| 日期 | 变更 |
|------|------|
| 2026-06-14 | 初始版本——基于 P50 可行性报告 + 影响面搜索结果 |
| 2026-06-14 | 审查修订——`pool_type` 字段名统一 + `distribution_file`→`distribution_template` 改名 + 遗漏脚本补齐 + `target_cards`→`target_specs` 转换说明 + `_save_templates_and_pools` 伪代码 + S4.0 预检步骤 + 测试扩展 + 验收标准追加 |
| 2026-06-14 | R1 对抗修复（plan-review Fixer，18 个问题）——S1 添加 `tomli` 条件依赖 + Python 3.10 兼容导入；S3.1 CLI 重写（`-c`/`--config` 重定义为 TOML，删除 `json_config_to_store` + 旧 JSON/硬编码路径，添加默认 `config.toml` 回退）；S3.2 `_DEFAULT_CONFIG_FILE` 改用 `get_config_dir()`；S3.6 新增 `about_dialog.py` 更新步骤；§2.5 新增 `ConfigStore._distribution_templates` 字段消除参数断层；§2.8 新增 `pool_type` 双写逻辑；S4.2 `PoolConfig`/`CardDef`/`CardCatalog` 明确删除；S4.3 `build_pity_engine` 明确删除；S4.5 精确 `__all__` 修改清单 + 验证命令；§三 新增 S3→S4 硬性门控条件；S5.1 新增 8 个边界/契约测试；S5.2a 提取 `TestStreaming`；§二 补全 `about_dialog.py`/`CONTRIBUTING.md`/2 个无变更脚本；§四 风险矩阵更新 |
| 2026-06-14 | R2 对抗修复（plan-review Fixer，7 个问题——ISSUE-017/018/019/020/021/022 + 遗留 ISSUE-010）——ISSUE-017/010：§二 `CONTRIBUTING.md` 条目添加 `<!-- REVIEW-R1-FIX -->` 锚点 + §三 新增 S3.7 独立实施步骤（提供 L18-25 旧 txt 树→`config.toml` 单行的替换文本、L12 注释更新、引导文字）；ISSUE-018：S3.1 追加 `output_data` 中 `config` 字段处理说明——新加载路径下 `config` 变量悬空导致 `NameError`，提供双方案（结构化元数据 dict / TOML 路径字符串）；ISSUE-019：§2.8 扩展为读写路径表格——详列 L2364-2375 和 L2877-2888 两处 PoolEntry 构造各需添加 `pool_type=pool_type`，含数据流断裂分析；ISSUE-020：§2.8 新增 `get_config()` L2232 读取路径修正——`p.pool_type or p.bindings.get(...)`，确保下游面板不接收错误池子类型；ISSUE-021：§二 `retreat_config.py` 条目追加 `pool_type=p.pool_type` 拷贝说明——与 `distribution_file`→`distribution_template` 改名原子修改；ISSUE-022：S3.6 HTML 替换从 4 段扩展至 9 段（[resources.defs]+[resources.initial] / [[resources.gain_rules]]+[[resources.day_overrides]] / [[targets]] / [[weights]] / [[distribution_templates]] + 费用语法 + 绑定键），与旧 txt 指南 9 个主题一一对应 |
| 2026-06-14 | R3 对抗修复（plan-review Fixer，4 个问题——ISSUE-023/024/025/026）——ISSUE-023：S4.0 grep 模式、S4.2 删除清单、验收标准第 9 条三处移除幽灵函数 `load_multi_config_from_directory`（代码库中从未存在，`load_config_from_directory` 已覆盖）；ISSUE-024：S3.5 扩充为三步处置——(a) 删除 L14 模块级 `PoolConfig` 导入（pytest 收集阶段触发 ImportError 根因）、(b) 删除或改写 `test_pool_config_batch_size_default()` 为 `PoolEntry` 等效测试、(c) 删除 `test_parse_schedule_with_batch_size` 及 L44 延迟导入，三步均在 S4.2 删除 PoolConfig 前完成；ISSUE-025：S4.4 追加 `_parse_resource_amount` / `_weekday_of_day` / `_month_of_day` / `_day_of_month` / `_week_of_month` 五个私有辅助函数（~36 行）——`parse_gains_file` 删除后唯一调用方消失，变为不可达死代码；ISSUE-026：S3.7 追加 L42 `pyproject.toml` 禁止规则更新——将「项目配置文件」改为「项目配置文件——计划性架构迁移授权修改」，消除与 P53 S1 添加 TOML 依赖的矛盾 |
| 2026-06-14 | R4 对抗修复（plan-review Fixer，4 个问题——ISSUE-031/032/033/034）——ISSUE-031：§二 `retreat_config.py` 条目追加 `batch_size=p.batch_size` 拷贝说明——与 `pool_type=p.pool_type` 同批修改，防止截断池子批次大小退化为默认值 1；ISSUE-032：S3.7 追加 L40 `tests/` 禁止规则更新——将「测试目录（单元测试、测试输出等）」改为「测试目录（计划性架构迁移授权修改）」，与 L42 pyproject.toml 行格式对齐；ISSUE-033：§二 `config_store.py` 条目 + §2.5 关键注意点重写——`_config_version` 和 `_distribution_templates` 统一声明为 `ConfigStore` dataclass field（含 `default_factory`/默认值），`clear()` 显式重置二者（`self._config_version = None` + `self._distribution_templates.clear()`），消除跨加载版本号/模板泄漏；S2.4 save_toml 伪代码 `getattr` 回退逻辑改为 `store._config_version or '2.2.0'`（dataclass field 默认 None 时 `getattr` 不触发 default）；ISSUE-034：S2.2 helper 表 `_build_distribution_templates` 返回类型从 `Dict[str, List[dict]]` 修正为 `List[dict]`（格式 `[{"name": ..., "cards": [...]}]`），与 S2.6 save 消费侧 `t['name']` 迭代兼容 |
| 2026-06-14 | R5 对抗修复（plan-review Fixer，GATE-1-变更粒度）——S2 拆为 S2a（加载路径 + 5 基础 helper + 单元测试，~1.5h）/ S2b（保存路径 + 模板匹配 + ConfigStore 字段 + clear() 重置，~2h）/ S2c（模板展开 + GUI 双写验证 + 集成测试，~1h）；S3 拆为 S3a（cli.py 破坏性重写 + output_data 修复，~1h）/ S3b（GUI 三文件入口替换 + pool_type 读写点 + about_dialog HTML 改写，~1.5h）/ S3c（文档三文件 + 5 脚本 + test_batch_draw.py 三步处置，~1h）；helper 函数表新增子步骤分配列；不变部分标注适用所有 S2 子步骤；§2.8 标注归属 S2c |
| 2026-06-14 | R6 对抗修复（plan-review Fixer，GATE-1-变更粒度第二轮）——S2b 进一步拆为 S2b-1（save_toml 骨架 + ConfigStore 字段声明 + clear() 重置 + _build_weights/_build_distribution_templates/_build_pools helper，~1h）和 S2b-2（_save_templates_and_pools + _distribution_matches_template 模板匹配逻辑 + 模板匹配往返测试，~1h），两子步骤间通过「S2b-1 完成后先验证 save→load 基本往返（分布写内联）」衔接；S5.1 拆为 S5.1a（基础加载/保存/边界测试，test_load_default_config 至 test_exchange_card_pool 共 10 个，~1h）和 S5.1b（模板匹配+契约测试，test_build_resources 至 test_distribution_field_mismatch 共 14 个，~1h），两批间通过 pytest 当前通过率隔离；helper 函数表 S2b→S2b-1 更新；S2c 前置依赖引用更新为 S2a+S2b-1+S2b-2；§2.5 及不变部分跨子步骤引用更新 |
| 2026-06-14 | R7 对抗修复（plan-review Fixer，GATE-1-变更粒度第三轮 + GATE-5-回滚路径）——GATE-1：S4.0-S4.5 各标注预估工时（S4.0: 5min, S4.1: 5min, S4.2: 5min, S4.3: 10min, S4.4: 10min, S4.5: 10min，合计 ~45min）；S3.7 行号修正 L12→L17（config/注释行在 CONTRIBUTING.md 第 17 行）；S5.2b 类名修正 TestConfigIOSaveLoad→TestPoolConfig（test_config_io.py:117 实际类名）；S3a 变更表追加 --data-dir 显式行。GATE-5：§四后新增「四-B：回滚策略」小节——详列 S1-S3 逐文件 git checkout 回滚、S4 原子删除 + 独立 commit + git revert 唯一回滚、S5-S6 回滚方式、建议的 6-commit 拆分方案 |
| 2026-06-14 | R8 对抗修复（plan-review Fixer，10 个 AUDIT-BREAK 问题——代码审计维度类型断裂/空值断裂）——§二后新增「二-A：原子提交约束」小节：定义 G-ATOMIC-1（distribution_file→distribution_template 改名与调用方原子提交）和 G-ATOMIC-2（S4.2-S4.5 删除与 re-export 原子提交），含违反后果一览表 + `_distribution_templates` 泄漏防御伪代码；§2.8 `_build_pools` 双写逻辑改用 `or '角色'` 短路空字符串（防御 TOML 中显式 `pool_type=""`）；L346 `_dispatch_simulation_results` 从「无需修改/建议后续统一」改为必须改用 `or` 短路链；S3a 追加 CLI 手动冒烟测试步骤（cli.py 无 pytest 测试，NameError 不可自动探测）+ `paths.py` 路径解析验证；S3b `main_window.py` 追加 `save_toml` 参数顺序颠倒警告 + `QFileDialog` 从 `getExistingDirectory`→`getOpenFileName` 变更及 `.toml` 过滤器代码；S3b `config_panel.py` 追加两处构造点字段名正确性检查（`distribution_file=`→`distribution_template=`，须与 S2b-1 同属 G-ATOMIC-1）；S3c `test_batch_draw.py` 追加 PoolEntry 构造 `distribution_template=` 字段名正确性警告；S4.2 追加 `_expand_binding` 保留验证命令 + 原子提交警告；S4.5 追加 G-ATOMIC-2 约束 + `ruff check` 零 F401/F822 + `PoolConfig` 导入应失败验证；§二 retreat_config.py 条目追加 G-ATOMIC-1 原子性约束说明（L49 `p.distribution_file`→`p.distribution_template`）；§四风险矩阵新增 5 行（G-ATOMIC-1 违反 / G-ATOMIC-2 违反 / `pool_type` 空字符串 / `save_toml` 参数顺序颠倒） |
| 2026-06-14 | R9 就绪度审计修订（7 项优化）——① 移除 `[meta]` 段：`load_toml`/`save_toml` 伪代码 + `about_dialog.py` HTML 指南 + S0 文件结构表删除 `sim_start_date` 读写（`ConfigStore` 默认值已覆盖）；② 移除 `_config_version` 字段：该字段无赋值来源（`save_toml` 永远回退到硬编码值），从 dataclass/`clear()`/ISSUE-033 全部删除；③ `_expand_binding` 从 `pool_config.py` 迁移至 `config_toml.py`——grep 确认零外部导入，移后 `pool_config.py` 整文件删除（原「裁剪保留 25 行」）；④ §2.5 追加 `_expand_binding` 加权语法兼容性说明——冒号加权（`"a:2.0,b:1.0"`）是 TOML 字符串内部 DSL，无冲突；⑤ S2b-1 `save_toml` 追加文件头注释块输出逻辑（~10 行手动写入后 `tomli_w.dump()` 追加）；⑥ S3b 新增 §3.6b PyInstaller 打包验证项——确认 `GachaStat.spec` `datas` 行无需修改；⑦ 风险矩阵新增 TOML 注释丢失风险行（已知限制，已通过文件头块 + about_dialog HTML 缓解）；G-ATOMIC-2 + S4.0 grep + S4.5 `__init__.py` + 验收标准同步更新 |

## ⚠️ 自动化审查阻塞项

**未解决问题：** 0 个

**阻塞详情：** []

**标注原因：** 6 轮对抗循环未收敛。

## 自动化审查记录

### 第 1 次审查（2026-06-11）——P38 工作流自动化

- 复杂度: complex | 变更性质: breaking
- 阶段 1 影响面: 36 个发现
- 阶段 2 对抗循环: 6 轮，熔断
- 阶段 3 门控: 6 项检查
- 阶段 4 代码审计: 已执行
- 累计问题: 40 个
