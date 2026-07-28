"""ISSUE-060: Update the save_toml 关键变更 list to reflect the fix"""
path = 'docs/01-活跃/subsystems/保底系统/P55 保底体系重构——正交分解与Context驱动的独立保底架构.md'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = '- 不再写旧字段 `start`/`end`/`func`/`reset`/`target`——全部由新字段替代。'
new = ('- 不再写旧字段 `func`/`reset`/`target`——全部由新字段替代。'
       '`start`/`end` 在 round-trip 时由 `_deltas_to_soft_interval()` 尝试还原——'
       '可还原时写出以保持用户可读性，不可还原时 type 降级为 `soft_step` + `deltas`。')

count = content.count(old)
print(f'Occurrences: {count}')
content = content.replace(old, new)

# Also update the deltas serialization bullet point
old2 = '- deltas 序列化为 `[[n, inc], ...]` 列表（RLE 压缩格式）。'
new2 = ('- deltas 序列化为 `[[n, inc], ...]` 列表（RLE 压缩格式）。'
        '`_deltas_to_soft_interval()` 尝试反向还原为语法糖——'
        '成功则写出 `start`/`end` 替代 `deltas` 键，失败则写出 `deltas` 且 type 降级为 `soft_step`。')

count2 = content.count(old2)
print(f'Occurrences2: {count2}')
content = content.replace(old2, new2)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
