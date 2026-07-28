"""ISSUE-057: 修改 §0.10 关键约束——声明 CounterBasedBehavior.__init__ btype 参数修改"""
import re

path = 'docs/01-活跃/subsystems/保底系统/P55 保底体系重构——正交分解与Context驱动的独立保底架构.md'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = '**关键约束（与 P60 的边界）：** 此为 P55 唯一一处对 P60 已交付方法体的修改。'

new = (
    '<!-- REVIEW-R2-FIX: ISSUE-057 -->\n'
    '**关键约束（与 P60 的边界）：** 此为 P55 对 P60 已交付方法体的两处修改之一：\n'
    '\n'
    '1. **`after_draw()` 插入 `_on_reset()` 钩子**（如上方伪代码所示）。\n'
    '2. **`CounterBasedBehavior.__init__` 新增 `btype` 参数**'
    '——用于在基类层面推导 `is_soft`/`is_event_driven`/`is_hard` 分类属性'
    '（详见 §3.1.1 SoftStepBehavior 构造器注释行1117-1120 及 §3.2 `_resolve_order()` 分类属性定义）。'
    '子类（`SoftStepBehavior`/`HardPityBehavior`/等）通过 `super().__init__(...)` 将 `btype` 传入基类，'
    '基类在构造时完成分类属性赋值。\n'
    '\n'
    '所有其他 P55 变更均为新增类/方法/字段，不修改 P60 代码。'
)

count = content.count(old)
print(f'Occurrences: {count}')
content = content.replace(old, new)
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
