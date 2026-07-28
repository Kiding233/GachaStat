"""ISSUE-058: Add classification attribute definitions to CounterBasedBehavior"""
path = 'docs/01-活跃/subsystems/保底系统/P55 保底体系重构——正交分解与Context驱动的独立保底架构.md'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Insert after line 502 (end of design points) - find unique anchor text
anchor = '- 未在 `rarity_rank` 中注册的 scope 返回 rank 99（排末尾），避免 KeyError 导致构造崩溃——但解析层的 scope 注册校验（`_build_pity_def()` §3.3.1）应在进入引擎前就拦截未注册 scope。\n'

new_block = (
    '\n'
    '<!-- REVIEW-R2-FIX: ISSUE-058 -->\n'
    '#### 3.1.2.1 分类属性定义——CounterBasedBehavior 构造时初始化\n'
    '\n'
    '`_resolve_order()` 和 `_validate_behaviors()` 依赖 behavior 实例上的以下公开属性做排序和校验。'
    '这些属性在 `CounterBasedBehavior.__init__()` 中通过 `btype` 参数一次性初始化，子类无需覆写：\n'
    '\n'
    '| 属性 | 类型 | 来源 | 说明 |\n'
    '|------|------|------|------|\n'
    '| `scope` | `str` | 构造器参数 `scope`（从 `PityDef.scope` 传入） | 稀有度作用域，如 `\'ssr\'`/`\'sr\'`/`\'r\'`——直接赋值 `self.scope = scope` |\n'
    '| `is_soft` | `bool` | `btype in SOFT_TYPES` | 是否为 counter 驱动软保底 |\n'
    '| `is_hard` | `bool` | `btype == \'hard\'` | 是否为硬保底 |\n'
    '| `is_event_driven` | `bool` | `not is_soft and not is_hard` | 是否为事件驱动型（rotating/rotating_soft/rotating_cr/targeted 等） |\n'
    '| `type` | `str` | `btype`（直接赋值 `self.type = btype`） | 保底类型字符串——校验时用于比较同 type 软保底冲突 |\n'
    '\n'
    '```python\n'
    'class CounterBasedBehavior(PityBehavior, ABC):\n'
    '    # P55 在 __init__ 中通过 btype 参数计算并赋值所有分类属性\n'
    '    def __init__(self, name: str, state: \'PityState\', scope: str,\n'
    '                 btype: str,  # ← P55 新增参数（见 §0.10 ISSUE-057）\n'
    '                 target_featured: bool = False,\n'
    '                 lifecycle: \'LifecycleConfig\' = None):\n'
    '        self._name = name\n'
    '        self._state = state\n'
    '        # ── P55 分类属性（公开，_resolve_order/_validate_behaviors 使用） ──\n'
    '        self.scope = scope\n'
    '        self.is_soft = btype in SOFT_TYPES\n'
    '        self.is_hard = (btype == \'hard\')\n'
    '        self.is_event_driven = (not self.is_soft and not self.is_hard)\n'
    '        self.type = btype\n'
    '        # ── P60 原有初始化（_rebind_state/Counter/Flag/lifecycle 等） ──\n'
    '        ...\n'
    '```\n'
    '\n'
    '**设计约束：**\n'
    '- `scope` 必须为公开属性（非私有 `_scope`），因为 `_resolve_order()` 中 `bh.scope` 和 `_scope_overlap(a.scope, b.scope)` 均通过公开属性访问。\n'
    '- `is_soft`/`is_event_driven`/`is_hard` 三者互斥——恰好一个为 `True`（由 `btype` 唯一决定）。\n'
    '- 子类（`SoftStepBehavior`/`HardPityBehavior` 等）通过 `super().__init__(..., btype=...)` 传入各自类型标识，无需覆写这些属性。\n'
    '<!-- /REVIEW-R2-FIX: ISSUE-058 -->\n'
)

content = content.replace(anchor, anchor + new_block)
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
