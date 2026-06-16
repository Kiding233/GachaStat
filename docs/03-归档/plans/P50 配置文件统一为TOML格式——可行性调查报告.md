<!-- META: P50 | module:配置 | status:analyzing | last:2026-06-14 -->
# P50 配置文件统一为 TOML 格式——可行性调查报告

> 日期：2026-06-14 | 状态：分析中 | 优先级：🔵 P2 — 架构债务
> 来源：P49 配置审计结论——当前 10 个 txt 文件使用 4 种不同自定义语法，解析器总代码 ~500 行，已发现格式不一致导致数据损坏
> 涉及层：core（`config_io.py`、`pool_config.py`、`pity.py`、`resource_gain.py`）→ gui（`config_panel.py`）→ CLI → 测试

---

## 1. 现状盘点

### 1.1 文件清单

| # | 文件 | 格式 | 解析器 | 复杂度 | 跨文件引用 |
|---|------|------|--------|--------|-----------|
| 1 | `schedule.txt` | `\|` 分隔 + `;` / `,` 子分隔 + `=` kv | `parse_schedule_file()` | 88行·23分支 | → `pools/*.txt` (distribution_file) |
| 2 | `pools/*.txt` | 嵌套括号语法 `[key]:prob` / `[key]=[list]` / `[key]=value` | `parse_distribution_file()` | 84行·19分支 | ← `schedule.txt` (bindings) |
| 3 | `cards.txt` | `\|` 分隔 | `parse_cards_file()` | 24行·6分支 | — |
| 4 | `pity.txt` | `pity:` 前缀 + `\|` 分隔 + `=` kv | `parse_pity_file()` | 37行·5分支 | → 池子通配符 `fnmatch` |
| 5 | `gains.txt` | `[rule]` 段 + `rid:amt` 行 + `day:` 覆盖 | `_load_gains()` + `expand_gain_rules_to_schedule()` | 73行+116行·51分支合计 | → `resources.txt` (资源ID) |
| 6 | `resources.txt` | `\|` 分隔 | `parse_resources_file()` | 16行·4分支 | — |
| 7 | `initial_resources.txt` | `\|` 分隔 | `_load_initial_resources()` | 20行·5分支 | → `resources.txt` |
| 8 | `targets.txt` | `\|` 分隔 + `,` 子分隔 | `_load_targets()` | 35行·9分支 | → `cards.txt` (卡ID) |
| 9 | `weights.txt` | `\|` 分隔 | `_load_weights()` | 39行·10分支 | → `cards.txt` (卡ID) |
| 10 | `resources.txt` | `\|` 分隔 | 同上 #6 | — | — |

### 1.2 格式语法统计

| 语法类型 | 使用文件 | 解析复杂度 |
|----------|---------|-----------|
| `\|` 竖线分隔 | schedule / cards / targets / weights / resources / initial_resources | 低 |
| `=` kv 对 + `;` 分隔 | schedule.txt (bindings列) | 中 |
| `[key]:prob` / `[key]=[list]` 嵌套括号 | pools/*.txt | **高** |
| `[rule]` 段 + `rid:amt` 行 | gains.txt | 高 |
| `pity:` 前缀 | pity.txt | 中 |
| `day:` 覆盖行 | gains.txt | 中 |
| `# start_date:` 注释中的元数据 | gains.txt | 边角情况 |

**共 4 种完全不同的自定义语法**，解析器总代码量 **~500 行**（仅统计 `config_io.py` + `pool_config.py` + `pity.py` + `resource_gain.py` 中的 `parse_*` / `_load_*` 函数）。

### 1.3 跨文件引用关系

```
schedule.txt ──distribution_file──► pools/character_pool.txt
     │                                    │
     │ bindings (ssr=card_a)              │ 需要 bindings 来解析 $变量
     └────────────────────────────────────┘

cards.txt ──► card_id ──► targets.txt / weights.txt / schedule.txt
resources.txt ──► resource_id ──► gains.txt / initial_resources.txt / schedule.txt
pity.txt ──► pools=fnmatch ──► schedule.txt (pool_id)
```

**核心问题：** 跨文件引用依赖文件名和 ID 字符串，无完整性校验。文件缺失时静默跳过（仅 `logger.warning`），不会报错。

---

## 2. 统一 TOML 方案设计

### 2.1 Schema（全量，逐段注释）

下面是完整的 `config.toml`，每段标注了：
- **TOML 语法作用**（这个符号是什么意思）
- **替代了哪个原 txt 文件**
- **等价于当前哪种自定义语法**
- **加载时如何处理**（哪些是直接取值、哪些需要展开）

```toml
# ============================================================
# GachaStat 统一配置文件 —— config.toml
# ============================================================
# 语法速查：
#   key = value          标量（整数/浮点/布尔/字符串）
#   [section]            表（字典）—— . 号嵌套子表
#   [[array]]            数组表——每个 [[array]] 是数组中的一个元素
#   { k = v, k = v }     内联表——写在一行的小字典
# ============================================================

# ──────────────────────────────────────────────────────────
# 元信息 —— 原分散在 gains.txt 注释行中的 sim_start_date
# ──────────────────────────────────────────────────────────
[meta]
version = "2.2.0"
sim_start_date = "2026-06-14"           # day=0 对应的真实日期

# ──────────────────────────────────────────────────────────
# 模拟参数 —— 原在 ConfigStore 顶层，无独立 txt 文件
# ──────────────────────────────────────────────────────────
[simulation]
count = 1000                            # int —— 不可能是 "1000" 字符串
max_workers = 4
seed = 42

# ──────────────────────────────────────────────────────────
# 资源定义 —— 替代 resources.txt
# 原格式:  resource_id | display_name
# 现格式:  [resources.defs] 下的 key = value
# ──────────────────────────────────────────────────────────
[resources.defs]
draw_resource = "抽卡资源"             # TOML key = "显示名称"
exchange_currency = "兑换货币"

# ──────────────────────────────────────────────────────────
# 初始资源 —— 替代 initial_resources.txt
# 原格式:  resource_id | amount
# 现格式:  [resources.initial] 下的 key = 数值
# 类型:   TOML 自动识别为 int/float
# ──────────────────────────────────────────────────────────
[resources.initial]
draw_resource = 55000                   # float/int 自动识别

# ──────────────────────────────────────────────────────────
# 资源获取规则 —— 替代 gains.txt 的 [rule] 段
# 原格式:
#   [every_n_days: 1]
#   draw_resource: 60
# 现格式:
#   [[resources.gain_rules]]    ← 双括号 = 数组中的一条规则
#   type = "every_n_days"       ← 规则类型（不再嵌入冒号参数）
#   param = "1"                 ← 参数独立字段
#   gains = { ... }             ← 内联表：资源→数量
#
# type 取值（与当前 parse_gains_file 一致）：
#   "every_n_days"  — 每 N 天（param="1"=每天）
#   "weekly"        — 每周几（param="1"=周一）
#   "monthly_day"   — 每月第几天（param="1"）；含逗号为月,日
#   "monthly_week"  — 每月第几周几（param="1,1"）
# ──────────────────────────────────────────────────────────
[[resources.gain_rules]]
type = "every_n_days"
param = "1"
gains = { draw_resource = 60 }          # 每天 60

[[resources.gain_rules]]
type = "monthly_day"
param = "1"
gains = { exchange_currency = 50 }      # 每月1号 50

# ──────────────────────────────────────────────────────────
# 指定日期覆盖 —— 替代 gains.txt 的 day: 行
# 原格式:
#   day: 0 | draw_resource: 200, exchange_currency: 50
# 现格式:
#   [[resources.day_overrides]]
#   day = 0                ← 第几天
#   gains = { ... }        ← 当日获取
# 加载时: 覆盖和规则产生的 schedule 合并（累加语义不变）
# ──────────────────────────────────────────────────────────
[[resources.day_overrides]]
day = 0
gains = { draw_resource = 200 }

[[resources.day_overrides]]
day = 21
gains = { draw_resource = 200 }

# ──────────────────────────────────────────────────────────
# 卡牌定义 —— 替代 cards.txt
# 原格式:  card_id | name | rarity | [initial_count]
# 现格式:  [[cards]] 数组表，每张卡一个条目
# ──────────────────────────────────────────────────────────
[[cards]]
id = "limited_ssr_1"
name = "限定角色1"
rarity = "ssr"                          # "ssr" | "sr" | "r" | "无"
initial_count = 0                       # 可选，默认 0。模拟开始时已持有的数量

[[cards]]
id = "standard_ssr_1"
name = "常驻角色1"
rarity = "ssr"
initial_count = 0

# ──────────────────────────────────────────────────────────
# 分布模板 —— 替代 pools/character_pool.txt 的嵌套括号语法
#
# 原格式（嵌套括号，16 行）:
#   [1]:0.004
#   [1]=[featured,offrate]
#   [featured]:0.5
#   [offrate]:0.5
#   [featured]=ssr         ← $ssr → 查 bindings.ssr → limited_ssr_1
#   [offrate]=ssr_alt      ← $ssr_alt → 查 bindings.ssr_alt → 6张常驻
#
# 现格式（模板引用，每卡 5 行）:
#   card_id 使用绑定键占位（ssr / sr / r / ssr_alt），
#   加载时根据 [[pools]].bindings 展开：
#     "ssr" → bindings.ssr 中逗号分隔的卡均分 probability
#     "sr"  → bindings.sr 中逗号分隔的卡均分 probability
#     "r"   → bindings.r 中逗号分隔的卡均分 probability
#
# 如果 bindings.ssr_alt 含 6 张卡（如 standard_ssr_1~6），
# 每个拿 0.2% ÷ 6 = 0.033%
# ──────────────────────────────────────────────────────────

[[distribution_templates]]
name = "character_pool_with_offrate"    # 模板名，池子通过此名引用

[[distribution_templates.cards]]
card_id = "ssr"                        # 绑定键 —→ expanded via bindings.ssr
probability = 0.2                      # 百分比（0.2%）
rarity = "ssr"
featured = true

[[distribution_templates.cards]]
card_id = "ssr_alt"                    # 绑定键 —→ expanded via bindings.ssr_alt
probability = 0.2                      # 6 张卡均分 = 每张 0.033%
rarity = "ssr"

[[distribution_templates.cards]]
card_id = "sr"                         # 绑定键 —→ expanded via bindings.sr
probability = 5.1
rarity = "sr"

[[distribution_templates.cards]]
card_id = "r"                          # 绑定键 —→ expanded via bindings.r
probability = 94.5
rarity = "r"

# ── 另一个模板：武器池（概率、歪卡比例与角色池不同） ──────
# 原 weapon_pool.txt: [1]:0.007 → [featured]:0.75 / [offrate]:0.25
#   featured SSR = 0.7% × 0.75 = 0.525%
#   offrate SSR  = 0.7% × 0.25 = 0.175%
[[distribution_templates]]
name = "weapon_pool"

[[distribution_templates.cards]]
card_id = "ssr"
probability = 0.525                    # 0.7% × 75% = 0.525%（限定武器）
rarity = "ssr"
featured = true

[[distribution_templates.cards]]
card_id = "ssr_alt"                    # 歪出常驻武器
probability = 0.175                    # 0.7% × 25% = 0.175%
rarity = "ssr"

[[distribution_templates.cards]]
card_id = "sr"
probability = 5.1                      # 与原 weapon_pool.txt 一致
rarity = "sr"

[[distribution_templates.cards]]
card_id = "r"
probability = 94.2                     # 与原 weapon_pool.txt 一致
rarity = "r"

# ──────────────────────────────────────────────────────────
# 池子定义 —— 替代 schedule.txt
#
# 原格式（1 行，9 个 | 分隔列）:
#   pool_c1 | 角色池1 | 0 | 21 | draw_resource:160 |
#   pools/character_pool.txt |
#   ssr=limited_ssr_1;ssr_alt=standard_ssr_1,...;sr=sr_1,...;r=r_1,... |
#   limited_ssr_1 | 1
#
# 现格式: [[pools]] 数组表，每个字段有名字
#
# cost 字符串：保留原 DSL 语法不变——
#   "draw_resource:160"                          单资源
#   "exchange_currency:5 > draw_resource:160"    , 或 > 表示优先级回退
#   "exchange_currency:5 & draw_resource:160"    & 表示同时需要
#   , 和 > 语义相同（> 仅用于提升可读性，显式表达优先级意图）
#   parse_cost_string() 解析逻辑不变（括号分组功能从未使用，可移除）
#
# bindings: 原 ; 分隔 → TOML 子表 [pools.bindings]
#   值中的逗号分隔（如 "standard_ssr_1, standard_ssr_2"）保留为字符串，
#   展开逻辑由 _expand_binding() 处理，不变
#
# distribution_template: 引用上方定义的模板名
#   加载时：查找 distribution_templates[name] → 用 bindings 展开 → PoolDistEntry[]
#   如果池子有特殊的独立分布，可直接内联 [[pools.distribution]] 覆盖
# ──────────────────────────────────────────────────────────

[[pools]]
id = "pool_c1"
name = "角色池1"
type = "角色"                            # 角色 | 武器 | 兑换 | 资源
start_day = 0
end_day = 21
cost = "draw_resource:160"              # 保留 DSL 字符串——parse_cost_string() 不变
batch_size = 1
distribution_template = "character_pool_with_offrate"

[pools.bindings]                         # 原 ; 和 = 分隔 → TOML 子表
ssr = "limited_ssr_1"                   # 单个卡ID
ssr_alt = "standard_ssr_1, standard_ssr_2, standard_ssr_3, standard_ssr_4, standard_ssr_5, standard_ssr_6"
sr = "sr_1, sr_2, sr_3, sr_4, sr_5, sr_6"       # 逗号分隔——展开逻辑不变
r = "r_1, r_2, r_3, r_4, r_5, r_6"

pools.target_cards = ["limited_ssr_1"]   # TOML 原生数组——不需要 , 分隔解析

[[pools]]
id = "pool_c2"
name = "角色池2"
type = "角色"
start_day = 21
end_day = 42
cost = "draw_resource:160"
batch_size = 1
distribution_template = "character_pool_with_offrate"

[pools.bindings]
ssr = "limited_ssr_2"                   # ← 仅限SSR不同，其余绑定完全相同
ssr_alt = "standard_ssr_1, standard_ssr_2, standard_ssr_3, standard_ssr_4, standard_ssr_5, standard_ssr_6"
sr = "sr_1, sr_2, sr_3, sr_4, sr_5, sr_6"
r = "r_1, r_2, r_3, r_4, r_5, r_6"

pools.target_cards = ["limited_ssr_2"]

# ── 武器池示例（引用不同模板） ────────────────────────────
[[pools]]
id = "pool_w1"
name = "武器池1"
type = "武器"
start_day = 0
end_day = 21
cost = "draw_resource:160"
batch_size = 1
distribution_template = "weapon_pool"         # ← 引用武器池模板

[pools.bindings]
ssr = "weapon_ssr_1"
ssr_alt = "weapon_standard_1, weapon_standard_2"  # 常驻武器——歪卡池
sr = "weapon_sr_1, weapon_sr_2, weapon_sr_3"
r = "weapon_r_1, weapon_r_2, weapon_r_3"

pools.target_cards = ["weapon_ssr_1"]

# ──────────────────────────────────────────────────────────
# 保底配置 —— 替代 pity.txt
# 原格式:
#   pity: ssr_soft | type=soft | start=80 | end=90 | func=linear |
#         target=limited_ssr:100 | reset=featured_ssr | pools=pool_c*
# 现格式: [[pity]] 数组表，每个保底规则一个条目
#
# pools 字段保留 fnmatch 通配符字符串（"pool_c*"）不变
# ──────────────────────────────────────────────────────────

[[pity]]
name = "ssr_soft"
type = "soft"                           # "soft" | "hard"
start = 80                              # type=soft：开始递增的抽数
end = 90                                # type=soft：达到 100% 的抽数
func = "linear"                         # "linear" | "exp" | "step"（type=soft 时有效）
threshold = 0                           # type=hard：强制触发的抽数阈值（type=soft 时为 0）
reset = "featured_ssr"                  # "any_ssr" | "featured_ssr" | "never"
pools = "pool_c*"                       # fnmatch 通配符——保留字符串，匹配逻辑不变
target = { limited_ssr = 100 }          # 内联表：目标分布（key=绑定键, value=权重）
counter_init = 0                        # 初始水位

# ──────────────────────────────────────────────────────────
# 目标卡 —— 替代 targets.txt
# 原格式:  card_id | quantity | pool_ids(逗号分隔)
# 现格式:  [[targets]] 数组表
# pool_ids: TOML 原生数组 ["pool_c1", "pool_c7"] —— 不需要 , 分割
# ──────────────────────────────────────────────────────────

[[targets]]
card_id = "limited_ssr_1"
quantity = 1                            # 需要抽到的数量
pool_ids = ["pool_c1", "pool_c7"]       # TOML 原生数组

# ──────────────────────────────────────────────────────────
# 卡牌权重 —— 替代 weights.txt
# 原格式:  card_id | desire_weight | miss_cost_weight | card_value
# 现格式:  [[weights]] 数组表，每张卡一个条目
#          desire / miss_cost / card_value 支持数值或字符串表达式（动态权重）
#          未来可扩展字段：expr_engine / condition / priority 等
# ──────────────────────────────────────────────────────────

[[weights]]
card_id = "limited_ssr_1"
desire = 1.0
miss_cost = 1.0
card_value = 1.0

[[weights]]
card_id = "standard_ssr_1"
desire = 1.0
miss_cost = 1.0
card_value = 0.3

[[weights]]
card_id = "sr_1"
desire = 1.0
miss_cost = 1.0
card_value = 0.1

[[weights]]
card_id = "r_1"
desire = 1.0
miss_cost = 1.0
card_value = 0.0
```

### 2.2 Schema 设计要点

| 设计选择 | 理由 |
|----------|------|
| distribution 使用**模板引用**而非每池内联 | ① 8 个角色池共享同一分布结构，内联会导致 ~200 行重复内容；② 模板 + bindings 展开等价于当前 `schedule.txt → pools/character_pool.txt` 的引用模式；③ 部分池子有独立分布时，可直接内联 `[[pools.distribution]]` 覆盖模板 |
| probability 保持**百分比**（0.2 = 0.2%）| 与 GUI 编辑器和当前内部存储一致，避免混淆 |
| bindings 使用 TOML `[pools.bindings]` 内联表 | 替代 `;`/`=` 自定义分隔，标准 TOML 语法 |
| 池子分布**合并入池子定义** | 消除 `pools/*.txt` 独立文件，减少跨文件引用 |
| `fnmatch` 通配符保留为字符串 | TOML 无原生 glob 类型，保持字符串便于编辑器理解 |
| 资源数量使用 `float` | TOML 区分整数/浮点数，资源消耗可能是浮点 |

### 2.3 与当前 txt 格式的映射关系

| txt 文件 | TOML 路径 | 转换 |
|----------|----------|------|
| `schedule.txt` | `[[pools]]` | `\|` → TOML 数组表 |
| `pools/character_pool.txt` | `[[distribution_templates]]` + `[[pools.distribution]]`（可选覆盖） | 嵌套括号 → 模板引用 + 绑定展开 |
| `cards.txt` | `[[cards]]` | `\|` → TOML 数组表 |
| `pity.txt` | `[[pity]]` | `pity:\|` → TOML 数组表 |
| `gains.txt` | `[[resources.gain_rules]]` + `[[resources.day_overrides]]` | `[rule]`段 → 数组表 |
| `resources.txt` | `[resources.defs]` | `\|` → TOML 键值表 |
| `initial_resources.txt` | `[resources.initial]` | `\|` → TOML 键值表 |
| `targets.txt` | `[[targets]]` | `\|` → TOML 数组表 |
| `weights.txt` | `[[weights]]` | `\|` → TOML 数组表（每卡一条目，可扩展动态权重表达式） |

### 2.4 为什么「改为从 dict 构造」—— TOML 解析的数据流

这是理解迁移的核心：**`tomllib.load()` 的返回值是什么，以及为什么这比手写解析器好。**

#### 当前流程：字符串 → 手写正则 → ConfigStore

```
schedule.txt（原始字符串）
  │
  ▼ parse_schedule_file()  —— 88 行代码
  │   line.strip()
  │   parts = line.split('|')
  │   bindings 中 ;/=/,  三重嵌套分割
  │   target_specs : 分割 + int() 转换
  │   batch_size: int() + 边界检查
  │   ...
  │
  ▼ PoolConfig dataclass（中间产物）
  │
  ▼ _load_schedule() 再加工为 PoolEntry → ConfigStore
```

每一步都需要**显式编码**：
- 字符串分割（`split`）
- 类型转换（`int()`, `float()`）
- 边界校验（`if n < 1: n = 1`）
- 静默跳过错误行（丢失数据时无警告）

这 88 行只服务于 `schedule.txt` 一种格式。`parse_distribution_file` 又 84 行，`_load_gains` 又 73 行……累计 ~500 行。

#### TOML 流程：字符串 → 标准库 → dict → 构造

```
config.toml（原始字符串）
  │
  ▼ tomllib.load()  —— 0 行自写代码
  │   返回一个纯 Python dict：
  │   {
  │     "pools": [
  │       {
  │         "id": "pool_c1",
  │         "name": "角色池1",
  │         "start_day": 0,        ← 已经是 int，不需要 int()
  │         "end_day": 21,
  │         "batch_size": 1,
  │         "bindings": {
  │           "ssr": "limited_ssr_1",
  │           "sr": "sr_1, sr_2, sr_3, ..."
  │         },
  │         "distribution_template": "character_pool_with_offrate",
  │         "target_cards": ["limited_ssr_1"]
  │       },
  │       ...
  │     ],
  │     "cards": [...],
  │     "pity": [...],
  │     ...
  │   }
  │
  ▼ _build_config_store(config: dict) → ConfigStore  —— ~80 行新增代码
  │   for p in config["pools"]:
  │       store.pools.append(PoolEntry(
  │           pool_id=p["id"],          ← 直接取，没有 split
  │           start_day=p["start_day"],  ← 已经是 int
  │           ...
  │       ))
```

**关键差异：**

| | 当前 `parse_*()` | TOML `_build_*()` |
|---|---|---|
| 输入 | 原始字符串 | 已解析的 `dict` |
| 分隔符解析 | 手写 `split('\|')` / `split(';')` / 正则 | `tomllib` 已完成 |
| 类型转换 | `int(parts[2])`, `float(parts[1])` | 已是正确类型 |
| 格式校验 | 手写 `if len(parts) < 3: continue` | `tomllib` 发现语法错即抛异常 |
| 错误处理 | 静默 `continue`（P49 的根源） | 异常精确到行列号 |
| 代码量 | 每种格式 20-88 行 | 每种结构 ~10 行 |

**「从 dict 构造」不是额外工作，而是把打字机换成键盘。** 手写解析器做的所有脏活——分割、转换、校验——`tomllib.load()` 一行替代。你只剩一件事：从已知结构的 dict 中取值，构造 ConfigStore 对象。

这就是为什么报告中说 `parse_schedule_file` / `parse_distribution_file` / `parse_pity_file` / `parse_cards_file` / `parse_resources_file` 可以**全部删除**——它们的 500 行工作已经被 `tomllib.load()` 干完了。

---

## 3. 利弊分析

### 3.1 优势

| 维度 | 说明 |
|------|------|
| **消除自定义语法** | 4 种自定义语法 → 1 种标准格式。~500 行解析器代码可删除或大幅简化 |
| **消除格式不一致 bug** | P49 发现的 D1（扁平格式无法解析）一劳永逸解决——TOML 解析器由标准库保证正确性 |
| **消除跨文件引用** | `schedule.txt` → `pools/*.txt` 的文件路径引用演变为单一文件内的 TOML 嵌套结构，不会出现"文件存在但格式不兼容" |
| **类型安全** | TOML 原生支持整数/浮点/布尔/字符串/数组/表——不再需要 `int()` / `float()` 手工转换 |
| **编辑器支持** | VS Code / PyCharm / Notepad++ 均有 TOML 语法高亮和校验 |
| **可编程校验** | JSON Schema 可定义 TOML 结构约束（通过 `tomli` + `jsonschema`） |
| **单文件部署** | 用户只需管理一个 `config.toml` 而非 10 个 txt 文件 + `pools/` 子目录 |
| **Python 3.11+ 标准库** | `tomllib` 已内置（读），仅需 `tomli-w`（写，纯 Python 无依赖 ~5KB） |
| **向后兼容** | 可保留旧 txt 加载路径作为 fallback，新格式优先 |

### 3.2 劣势

| 维度 | 说明 | 缓解措施 |
|------|------|---------|
| **迁移成本** | 需重写 `config_io.py`（625行）的大部分读写逻辑 | 分阶段：先加 TOML 加载器共存，再逐步废弃 txt |
| **单文件膨胀** | 当前 10 个文件合计 ~210 行；若内联 8 个池子的分布（每池 4 卡 × 5 行），仅分布部分就 ~160 行，总文件膨胀至 ~500 行 | **模板引用方案**——分布模板 `[[distribution_templates]]` 定义一次，池子用 `distribution_template = "name"` 引用。8 池共享 1 个模板时总行数压回 ~250 行，与当前 11 个文件总量相当 |
| **缺少嵌套分组** | 原始 `character_pool.txt` 的 `[1]=[featured,offrate]` 嵌套结构信息在展开后丢失 | 模板中的 `card_id = "ssr"` 占位符 + bindings 展开保留了父子层级语义——模板定义「SSR 占总概率 0.4%」，bindings 定义「ssr = limited_ssr_1」——层级关系以模板→绑定方式间接表达。对于不需要嵌套的简单池子，可直接内联 `[[pools.distribution]]` 覆盖模板 |
| **依赖新增** | 需添加 `tomli-w`（写 TOML） | 纯 Python，无 C 扩展，~5KB，pip install 无负担 |
| **用户迁移** | 现有用户的 `config/` 目录需要一次性转换为 `config.toml` | 提供自动迁移脚本 `python -m gacha_simulator migrate-config` |
| **配置面板重构** | `config_panel.py`（3217行）中的 `apply_to_store` / `refresh_from_store` 逻辑需要适配 TOML 路径 | 实际上 ConfigStore 数据模型不变——GUI 读写的是 ConfigStore 对象，文件格式变化对 GUI 透明 |
| **git diff 可读性** | 单文件修改时 diff 上下文较大（整个 `config.toml` 而非单个 `schedule.txt`） | TOML 的 section 分隔清晰，diff 仍可定位到具体 section |

### 3.3 分布方案对比：三种组织方式

8 个角色池共享同一分布结构，TOML 有三种组织方式：

| | 方案 A：纯扁平内联 | 方案 B：模板引用（推荐） | 方案 C：混合文件 |
|---|---|---|---|
| **写法** | 每个池子下内联完整的 `[[pools.distribution]]` | 顶部定义 `[[distribution_templates]]`，池子用 `distribution_template = "name"` 引用 | `config.toml` 替代 8 个 txt，池子用 `distribution_file = "pools/xxx.txt"` 引用外部文件 |
| **8池分布行数** | ~160 行（每池 4 卡 × 5 行） | ~24 行（1 个模板 × 4 卡 × 5 行 + 8 行引用） | ~0（分布在外部分布文件中） |
| **总文件行数** | ~500 | ~250 | ~200 + 分布文件 |
| **文件数** | 1 | 1 | 1 + N 个分布文件 |
| **重复内容** | 严重——改 SSR 概率需改 8 处 | 无——改模板一处即可 | 无——共享模板文件 |
| **跨文件引用** | 无 | 无（模板定义在同一文件内） | 有——回到当前 txt 的问题 |
| **嵌套层级保留** | 丢失 | 间接保留（模板 + bindings） | 保留（分布文件保持嵌套括号语法） |
| **实现成本** | 最低 | 中等（需模板展开逻辑，可复用 bindings 解析） | 较高（两套解析器共存） |
| **适用场景** | ≤3 个池子且分布各有差异 | ≥4 个池子共享模板（当前场景） | 极度保守的过渡方案 |

**推荐方案 B（模板引用）**，理由：
1. 本质上是当前 `schedule.txt → pools/character_pool.txt` 关系的 TOML 等价物——模板（原分布文件）+ bindings（原绑定列）→ 展开
2. 模板定义在同一个 `config.toml` 内，无跨文件引用，不会出现「文件在但格式不兼容」
3. 大部分池子共享模板，少数特殊池子可直接内联 `[[pools.distribution]]` 覆盖——模板和内联可共存，加载器优先取内联

### 3.4 关键判断：文件格式变化对 GUI 的影响

**ConfigStore 数据模型不变。** 文件格式变更仅影响 `config_io.py` 的 load/save 层。`config_panel.py` 通过 `ConfigStore` ↔ GUI 的交互逻辑完全不受影响——`apply_to_store()` 和 `refresh_from_store()` 操作的仍是 `ConfigStore` 对象。

```
当前：
  txt 文件 → parse_*() → ConfigStore → GUI
  GUI → apply_to_store() → ConfigStore → _save_*() → txt 文件

改造后：
  config.toml → tomllib.load() → ConfigStore → GUI    ← 解析器替换，ConfigStore 不变
  GUI → apply_to_store() → ConfigStore → tomli_w.dump() → config.toml
```

---

## 4. 迁移影响面评估

### 4.1 代码改动范围

| 文件 | 当前行数 | 改动量 | 说明 |
|------|---------|--------|------|
| `core/config_io.py` | 625 | **重写** ~80% | txt 解析 → TOML 解析；16 个 `_load_*`/`_save_*` 缩减为 2 个 |
| `core/pool_config.py` | 432 | **大幅简化** | `parse_schedule_file` / `parse_distribution_file` / `parse_cards_file` 删除或改为从 dict 构造 |
| `core/pity.py` | 374 | **小幅** | `parse_pity_file` 改为从 dict 构造 |
| `core/resource_gain.py` | 505 | **小幅** | `parse_gains_file` 已废弃可移除；`parse_resources_file` 删除 |
| `gui/config_panel.py` | 3217 | **0 行** | 不变——ConfigStore 数据模型不受影响 |
| `service/batch_simulator.py` | 737 | **0 行** | 不变 |
| `cli.py` | 295 | **小幅** | `load_store_from_directory` 调用改为 `load_store_from_toml` |
| `main_window.py` | ~500 | **小幅** | 保存/加载路径切换 |
| **测试** | ~200行新增 | 新增 | TOML 加载/保存/往返测试 |
| **迁移脚本** | ~80行 | 新增 | txt → toml 一次性转换 |

**估计净代码量变化：** 删除 ~500 行自定义解析器 + ~200 行自定义写入器 → 新增 ~80 行 TOML 加载器 + ~60 行 TOML 写入器 + ~80 行迁移脚本。**净减少 ~480 行。**

### 4.2 新增依赖

```toml
# pyproject.toml
dependencies = [
    ...
    "tomli-w>=1.0",          # TOML 写入（tomllib 读已在 Python 3.11+ stdlib）
]
```

Python 3.10 兼容性：需额外添加 `tomli`（读）。可选方案：
- A) 要求 Python ≥3.11（利用 stdlib `tomllib`），仅加 `tomli-w`
- B) 保持 ≥3.10，同时加 `tomli` + `tomli-w`（两个轻量纯 Python 包）

推荐方案 A——Python 3.10 已于 2026 年停止安全更新，且用户环境为 3.12。

### 4.3 风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 迁移脚本有 bug 导致用户数据损坏 | 中 | 高 | 迁移前自动备份 `config/` → `config_backup/`；提供 `--dry-run` |
| TOML 写入格式与用户手工编辑预期不一致 | 低 | 低 | `tomli-w` 输出格式确定，运行一次后用户即适应该格式 |
| 单文件过大导致加载慢 | 极低 | 极低 | 当前 10 个 txt 共 ~6KB；合并 TOML ~20KB，`tomllib` 解析 <1ms |
| 现有脚本引用旧文件路径 | 低 | 低 | 当前仅 `scripts/verify_p26_*.py` 两处直接调 `load_store_from_directory(config_dir)`；改为 `load_store_from_toml(config_file)` 即可。CLI 参数 `--data-dir` 改为 `--config`。无 CI 引用 |

---

## 5. 实施策略

**一步到位，不搞共存。**

理由：
- 渐进迁移意味着 3 个版本周期内维护两套解析器（txt + TOML），而 txt 解析器正是 P49 bug 的来源
- 迁移脚本 `migrate-config` 是一次性操作，用户跑一次就完成转换
- CLI 调用方只有 2 个验证脚本 + CLI 自身的 `--data-dir` 参数，改动量极小
- 无 CI 依赖旧路径

### 实施步骤

| 步骤 | 内容 | 产出 |
|------|------|------|
| S1 | 新增 `core/config_toml.py`：`load_toml(path) → ConfigStore` + `save_toml(store, path)` | TOML ⇄ ConfigStore |
| S2 | 新增 `cli.py` 子命令 `migrate-config`：读取 `config/` 目录 → 写入 `config.toml`，自动备份原目录到 `config_backup/` | 迁移工具 |
| S3 | 替换加载入口：`main_window.py` 改为 `load_toml()`；CLI `--data-dir` 改为 `--config` | 入口切换 |
| S4 | 更新 `scripts/verify_p26_*.py` 从 `load_store_from_directory` 改为 `load_toml` | 脚本更新 |
| S5 | 删除 `config_io.py` 全部 `_load_*`/`_save_*` + `pool_config.py` 的 `parse_schedule_file`/`parse_distribution_file`/`parse_cards_file` + `pity.py` 的 `parse_pity_file` + `resource_gain.py` 的 `parse_gains_file`/`parse_resources_file` | 旧代码清理 |
| S6 | 回归：`pytest -q` + GUI 启动加载新格式 + 迁移脚本端到端测试 | 验证 |

### 不做的事

- **不保留 txt 加载路径**——迁移脚本是唯一的桥
- **不移除 `parse_cost_string()`**——cost 的 `> / &` DSL 保留为 TOML 字符串值
- **不移除 `_expand_binding()`**——bindings 逗号分隔展开保留
- **不移除 `expand_gain_rules_to_schedule()`**——gain_rules 从 ConfigStore 对象展开为 schedule dict 的逻辑不变

---

## 6. 结论

### 6.1 可行性：✅ 可行且推荐

统一 TOML 方案在技术上完全可行，且：

- **直接消除了 P49 发现的两条数据损坏路径**（扁平格式不兼容 + bindings 丢失）
- **减少 ~480 行自定义解析代码**
- **模板引用方案解决了单文件膨胀问题**（~250 行，与当前 11 个文件总量相当）
- **ConfigStore 数据模型不变**——GUI 面板和模拟引擎零改动
- **新增依赖轻量**（`tomli-w` ~5KB 纯 Python）
- **一步到位**——迁移脚本一次性转换，不维护两套解析器

### 6.2 与 P49 的关系

**P49 和 P50 可合并执行。** P49 修复 txt 格式的两个 bug vs P50 直接替换为 TOML——两者解决的是同一组文件的同一类问题。既然决定一步到位用 TOML，P49 中对 `parse_distribution_file` 添加扁平格式 fallback 的工作就是多余的——那个解析器会被整体删除。

合并策略：**跳过 P49，直接执行 P50。** 迁移脚本一次性将用户现有 `config/` 目录转为 `config.toml`，转换过程中不会触发 P49 的数据损坏路径（迁移脚本读的是原始 txt，写的是 TOML，不经过 GUI 的 `apply_to_store`）。

### 6.3 执行前提

| 条件 | 状态 |
|------|------|
| Python ≥3.11（`tomllib` 标准库） | ✅ 当前环境 3.12 |
| `tomli-w` 加入依赖 | 待加 |
| 迁移脚本就绪 + 测试通过 | 待实施 |
| 现有 P0 阻塞项清零（P18/P26/P27/P28/P31） | 建议先清 P0，再执行架构变更 |
