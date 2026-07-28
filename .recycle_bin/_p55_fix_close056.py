"""Add back closing marker for ISSUE-056"""
path = 'docs/01-活跃/subsystems/保底系统/P55 保底体系重构——正交分解与Context驱动的独立保底架构.md'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = '        d[\"target_featured\"] = True\n\n<!-- REVIEW-R2-FIX: ISSUE-060'
new = '        d[\"target_featured\"] = True\n<!-- /REVIEW-R2-FIX: ISSUE-056 -->\n\n<!-- REVIEW-R2-FIX: ISSUE-060'
c = content.count(old)
print(f'Occurrences: {c}')
content = content.replace(old, new)
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
