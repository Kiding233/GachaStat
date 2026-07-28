"""ISSUE-060: Fix soft_interval TOML round-trip breakage

Fixes:
1. _build_pity_def(): Guard for deltas-first (round-trip path)
2. _build_toml_pity(): Call _deltas_to_soft_interval() and handle type downgrade
3. Remove redundant comment block
"""
path = 'docs/01-活跃/subsystems/保底系统/P55 保底体系重构——正交分解与Context驱动的独立保底架构.md'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: _build_pity_def() - handle direct deltas (round-trip guard)
old_read = '    <!-- REVIEW-R1-FIX: ISSUE-038——内层也转为 tuple 以保证完全不可变 -->\n    deltas  = tuple(tuple(seg) for seg in _expand_soft_to_deltas(raw)) if btype in SOFT_TYPES else None'
new_read = (
    '    <!-- REVIEW-R2-FIX: ISSUE-060——round-trip 守卫：若 TOML 中已存在 deltas 键（由 _build_toml_pity 写出），'
    '直接使用而跳过 _expand_soft_to_deltas()——避免 soft_interval 写回后再次加载时因缺少 start/end 而 ConfigError。'
    '语法糖展开仅在首次加载（无 deltas 键）时执行。 -->\n'
    '    # ISSUE-038 内层也转为 tuple 以保证完全不可变\n'
    '    if btype in SOFT_TYPES:\n'
    '        if \'deltas\' in raw:\n'
    '            # round-trip 路径：deltas 已由 _build_toml_pity() 写出——直接使用\n'
    '            deltas_raw_val = raw[\'deltas\']\n'
    '            if not isinstance(deltas_raw_val, list) or len(deltas_raw_val) == 0:\n'
    '                raise ConfigError(\n'
    '                    f"[[pity]] type=\'{btype}\' 的 deltas 格式错误（round-trip 路径）——"\n'
    '                    f"期望非空列表，实际: {deltas_raw_val!r}"\n'
    '                )\n'
    '            deltas = tuple(tuple(seg) for seg in deltas_raw_val)\n'
    '        else:\n'
    '            # 首次加载路径——语法糖展开（soft_interval/soft_additive → deltas）\n'
    '            deltas = tuple(tuple(seg) for seg in _expand_soft_to_deltas(raw))\n'
    '    else:\n'
    '        deltas = None'
)

print(f'Read path occurrences: {content.count(old_read)}')
content = content.replace(old_read, new_read)

# Fix 2: _build_toml_pity() - call _deltas_to_soft_interval() and handle type downgrade
old_write = (
    '    # ── counter 驱动：round-trip 可逆声明 ──\n'
    '    # ISSUE-056 同步修正注释：counter_init=0 在 is not 0 分支中不写出，\n'
    '    # 但加载时若 TOML 缺少 counter_init 键 → PityDef.counter_init 默认 0——语义等价，round-trip 可逆。\n'
    '    # 若需无条件写出（含 0），将上方条件从 is not 0 改为 is not None 并确保 PityDef.counter_init 类型为 Optional[int]。\n'
    '<!-- /REVIEW-R2-FIX: ISSUE-056 -->\n'
    '    if pdef.btype in SOFT_TYPES and pdef.deltas is not None:\n'
    '        d[\'deltas\'] = [list(seg) for seg in pdef.deltas]'
)

new_write = (
    '<!-- REVIEW-R2-FIX: ISSUE-060——soft_interval/additive round-trip 修复：\n'
    '     写回前尝试用 _deltas_to_soft_interval() 还原语法糖——\n'
    '     可还原 → 写出 start/end 替代 deltas（保持用户可读性）；\n'
    '     不可还原 → type 降级为 soft_step + deltas（数据不丢失）。\n'
    '     soft_additive 无反向还原函数——写回时 type 降级为 soft_step + deltas。\n'
    '     配合 _build_pity_def() 的 round-trip 守卫（deltas 键优先），\n'
    '     确保保存→加载往返可逆。 -->\n'
    '    if pdef.btype in SOFT_TYPES and pdef.deltas is not None:\n'
    '        restored = _deltas_to_soft_interval(pdef.deltas)\n'
    '        if restored is not None:\n'
    '            # round-trip 可还原为语法糖——写出 start/end 替代 deltas\n'
    '            d[\'type\'] = restored[\'type\']\n'
    '            d[\'start\'] = restored[\'start\']\n'
    '            d[\'end\'] = restored[\'end\']\n'
    '        else:\n'
    '            # 不可还原（如用户自定义 deltas 或 soft_additive）——\n'
    '            # 降级 type 为 soft_step（若原 type 非 soft_step）并写出 deltas\n'
    '            if pdef.btype != \'soft_step\':\n'
    '                d[\'type\'] = \'soft_step\'  # 覆盖构造函数中设置的 pdef.btype\n'
    '            d[\'deltas\'] = [list(seg) for seg in pdef.deltas]'
)

print(f'Write path occurrences: {content.count(old_write)}')
content = content.replace(old_write, new_write)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
