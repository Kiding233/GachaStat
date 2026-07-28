"""Remove duplicated sentence"""
path = 'docs/01-活跃/subsystems/保底系统/P55 保底体系重构——正交分解与Context驱动的独立保底架构.md'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
old = '所有其他 P55 变更均为新增类/方法/字段，不修改 P60 代码。所有其他 P55 变更均为新增类/方法/字段，不修改 P60 代码。'
new = '所有其他 P55 变更均为新增类/方法/字段，不修改 P60 代码。'
count = content.count(old)
print(f'Found: {count}')
content = content.replace(old, new)
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
