"""P61 Ph4b 一次性迁移：config.toml 从 [[pools]] 改写为 [[banner]]。

迁移规则（P61 §3.4 一次性迁移 / DECISION-3/4 裁决）：
- 每个旧 [[pools]] → 一个 [[banner]]，pool 字段进 [[banner.pool]]（id="main"）
- start_day/end_day 上移到 banner 级（TOML 层保持天数，解析边界 *DAY 换秒）
- pool_type / bindings / distribution_template / target_cards 删除（推导化/展平视图 target_specs=[]）
- distribution_template + bindings 展开为内联 [[banner.pool.reward]]（与旧 _expand_binding 浮点逐位一致）
- exchange 池保留 exchange_card_id 快捷方式（本示例无 exchange 池）
- enabled=False 池不写入
- PityDef.pools 裸 id → 全限定键（["pool_c*"] → ["pool_c*.main"]，ISSUE-103/ISSUE-004）
- [[targets]].pool_ids 保留裸 banner id（策略按 banner.id 匹配，§3.4 ISSUE-315）

用法：python scripts/migrate_config_p61_ph4b.py
"""

import tomllib
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / 'gacha_simulator/config/config.toml'


def expand_binding(value: str, prob: float):
    """复刻旧 _expand_binding——等权/冒号加权展开，浮点运算与旧 _build_pools 逐位一致。"""
    if ',' not in value:
        return [(value, prob)]
    parts = [p.strip() for p in value.split(',')]
    weighted, unweighted = [], []
    for part in parts:
        if ':' in part:
            cid, w = part.rsplit(':', 1)
            try:
                weighted.append((cid.strip(), float(w)))
            except ValueError:
                weighted.append((part.strip(), 1.0))
        else:
            unweighted.append(part.strip())
    if not weighted and not unweighted:
        return [(value, prob)]
    total = sum(w for _, w in weighted) + len(unweighted)
    return ([(cid, prob * (w / total)) for cid, w in weighted] +
            [(cid, prob * (1.0 / total)) for cid in unweighted])


def _fmt_prob(v: float) -> str:
    """概率字面量——整数 → int 文本，浮点 → repr（round-trip 与旧展开逐位一致）。"""
    if float(v).is_integer():
        return str(int(v))
    return repr(float(v))


def _expand_rewards(p, templates):
    """单个旧池 → 展开后的 reward dict 列表（与旧 _build_pools 展开逻辑等价）。"""
    cards = []
    if p.get('exchange_card_id'):
        return [{'card_id': p['exchange_card_id'], 'probability': 100.0,
                 'rarity': 'ssr', 'featured': True}]
    tpl_name = p.get('distribution_template', '')
    bindings = p.get('bindings', {})
    if tpl_name and tpl_name in templates:
        binding_keys = {'ssr', 'sr', 'r', 'ssr_alt', 'ssr_alt1', 'ssr_alt2', 'featured', 'offrate'}
        for tc in templates[tpl_name]:
            cid, prob = tc['card_id'], tc['probability']
            rarity = tc.get('rarity', 'r')
            featured = tc.get('featured', False)
            if cid in binding_keys:
                for cc, cp in expand_binding(bindings.get(cid, cid), prob):
                    cards.append({'card_id': cc, 'probability': cp, 'rarity': rarity,
                                  'featured': (featured and cid == 'ssr')})
            else:
                cards.append({'card_id': cid, 'probability': prob, 'rarity': rarity,
                              'featured': featured})
    elif 'distribution' in p:
        for d in p['distribution']:
            cards.append({'card_id': d['card_id'], 'probability': d['probability'],
                          'rarity': d.get('rarity', 'r'), 'featured': d.get('featured', False)})
    return cards


def build_banner_block(data) -> str:
    """构造迁移后的 [[banner]] 段文本。"""
    templates = {t['name']: t.get('cards', []) for t in data.get('distribution_templates', [])}
    blocks = []
    for p in data.get('pools', []):
        if not p.get('enabled', True):
            continue
        lines = ['[[banner]]',
                 f'id = "{p["id"]}"',
                 f'name = "{p["name"]}"',
                 f'start_day = {p.get("start_day", 0)}',
                 f'end_day = {p.get("end_day", 21)}',
                 '',
                 '[[banner.pool]]',
                 'id = "main"',
                 f'cost = "{p.get("cost", "draw_resource:160")}"']
        if p.get('batch_size', 1) != 1:
            lines.append(f'batch_size = {p["batch_size"]}')
        for c in _expand_rewards(p, templates):
            lines += ['',
                      '[[banner.pool.reward]]',
                      f'card_id = "{c["card_id"]}"',
                      f'probability = {_fmt_prob(c["probability"])}']
            if c.get('rarity') != 'r':
                lines.append(f'rarity = "{c["rarity"]}"')
            if c.get('featured'):
                lines.append('featured = true')
        lines.append('')
        blocks.append('\n'.join(lines))
    return '\n'.join(blocks)


def migrate() -> None:
    text = CONFIG.read_text(encoding='utf-8')
    data = tomllib.loads(text)

    banner_block = build_banner_block(data)

    # ── 切分替换：分布模板段 → 保底配置段 之间替换为 [[banner]] ──
    start_marker = '# ── 分布模板'
    end_marker = '# ── 保底配置'
    s = text.index(start_marker)
    e = text.index(end_marker)

    new_head = (
        '# ── Banner 池子定义（P61 迁移：旧 [[pools]] + 分布模板 → [[banner]]） ──\n'
        '# 每个旧 [[pools]] → 一个 [[banner]]（pool 进 [[banner.pool]]，id="main"）；\n'
        '# distribution_template + bindings 已展开为内联 [[banner.pool.reward]]。\n'
        '# start_day/end_day 为 banner 级时间窗口（天），解析边界 *DAY 换秒。\n'
        '\n'
    )
    text = text[:s] + new_head + banner_block + '\n' + text[e:]

    # ── PityDef.pools 裸 id → 全限定键（ISSUE-103）──
    text = text.replace('pools = ["pool_c*"]', 'pools = ["pool_c*.main"]')

    CONFIG.write_text(text, encoding='utf-8')
    print('迁移完成：', CONFIG)


if __name__ == '__main__':
    migrate()
