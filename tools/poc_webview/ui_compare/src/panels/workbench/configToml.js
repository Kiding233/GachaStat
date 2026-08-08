// ══════════════════════════════════════════════════════════════════
// 配置块渲染器核心：真实 TOML 解析 / 序列化（纯 JS，无 Vue 依赖）
//
// 对齐 gacha_simulator/core/config_toml.py 的真实结构：
//   [[banner]]            + [[banner.pool]] + [[banner.pool.reward]] + [[banner.lifecycle]]
//   [[card]] / [[weights]] / [[pity]] / [[milestone]] / [[targets]]
//   [resources.defs] / [resources.initial] / [rarities] / [strategy]
// 未建模段（resources.gain_rules / day_overrides / 其他未知段）→ _raw 块原样保留
//（round-trip 不丢；信息架构梳理：顺序无关解析，引用用显式 ID）
// ══════════════════════════════════════════════════════════════════

// ── 块类型层级（信息架构梳理第六节定稿：7 实体 + 2 全局单例）──
export const BLOCK_TYPES = {
  resource:  { label: '资源',     kind: 'entity' },
  banner:    { label: 'Banner',   kind: 'entity' },
  card:      { label: '卡片',     kind: 'entity' },
  pity:      { label: '保底规则', kind: 'entity' },
  milestone: { label: '累抽奖励', kind: 'entity' },
  target:    { label: '目标卡',   kind: 'entity' },
  weight:    { label: '权重',     kind: 'entity' },
  rarity:    { label: '稀有度层级', kind: 'global' },
  strategy:  { label: '策略',     kind: 'global' },
}
export const isEntity = (t) => BLOCK_TYPES[t]?.kind === 'entity'

// ── 空模板块 TOML（必填字段占位，与真实结构一致）──
export function emptyToml(type) {
  const map = {
    banner: '[[banner]]\nid = ""\nname = ""\nstart_day = 0\nend_day = 21',
    card: '[[card]]\ncard_id = ""\nname = ""\nrarity = "r"\ninitial_count = 0',
    resource: '[resources.defs]\n\n[resources.initial]',
    pity: '[[pity]]\nname = ""\ntype = "soft_interval"\nscope = "ssr"',
    milestone: '[[milestone]]\nname = ""\nthreshold = 40\nrepeat = false\nmax_triggers = 0\nbanner = ""',
    target: '[[targets]]\ncard_id = ""\nquantity = 1\npool_ids = []',
    weight: '[[weights]]\ncard_id = ""\ndesire = 1.0\nmiss_cost = 1.0\ncard_value = 1.0',
    rarity: '[rarities]\nranks = [["SSR"],["SR"],["R"]]',
    strategy: '[strategy]\nkey = "smart"',
  }
  return map[type] || ''
}

// ══════════════════════════════════════════════════════════════════
// 值解析 / 序列化（类型感知：数字不引号、布尔、数组、内联表）
// ══════════════════════════════════════════════════════════════════

// 顶层按分隔符分割（忽略引号内与 [ ] / { } 内的分隔符）
export function splitTopLevel(text, sep) {
  const out = []
  let depth = 0
  let inStr = false
  let cur = ''
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (ch === '"') inStr = !inStr
    if (!inStr) {
      if (ch === '[' || ch === '{') depth++
      else if (ch === ']' || ch === '}') depth--
    }
    if (ch === sep && depth === 0 && !inStr) { out.push(cur.trim()); cur = '' }
    else cur += ch
  }
  if (cur.trim()) out.push(cur.trim())
  return out
}

export function parseArray(text) {
  const inner = text.slice(1, text.endsWith(']') ? -1 : undefined).trim()
  if (!inner) return []
  return splitTopLevel(inner, ',').map((p) => parseValue(p))
}

export function parseInlineTable(text) {
  const inner = text.slice(1, text.endsWith('}') ? -1 : undefined).trim()
  const obj = {}
  for (const part of splitTopLevel(inner, ',')) {
    const m = part.match(/^([A-Za-z0-9_.]+)\s*=\s*(.+)$/)
    if (m) obj[m[1]] = parseValue(m[2].trim())
  }
  return obj
}

export function parseValue(text) {
  const s = text.trim()
  if (!s) return ''
  if (s.startsWith('{')) return parseInlineTable(s)
  if (s.startsWith('[')) return parseArray(s)
  if (s.startsWith('"')) return s.replace(/^"|"$/g, '').replace(/\\"/g, '"')
  if (s === 'true') return true
  if (s === 'false') return false
  if (/^-?\d/.test(s) && !isNaN(Number(s))) return Number(s)
  return s
}

export function serializeValue(v) {
  if (v === null || v === undefined || v === '') return ''
  if (typeof v === 'string') return '"' + v.replace(/"/g, '\\"') + '"'
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (typeof v === 'number') return String(v)
  if (Array.isArray(v)) {
    if (v.length && Array.isArray(v[0])) {
      return '[' + v.map((row) => '[' + row.map((x) => serializeValue(x)).join(', ') + ']').join(', ') + ']'
    }
    return '[' + v.map((x) => serializeValue(x)).join(', ') + ']'
  }
  if (typeof v === 'object') {
    return '{ ' + Object.entries(v).map(([k, x]) => `${k} = ${serializeValue(x)}`).join(', ') + ' }'
  }
  return String(v)
}

// ══════════════════════════════════════════════════════════════════
// 解析：TOML 文本 → 块列表（识别嵌套数组表，归属到实体块）
// ══════════════════════════════════════════════════════════════════

// 逻辑行合并：多行数组（[...] 跨行）拼接为单逻辑行；注释行跳过。
// 返回 { text, start, end }（start/end 为原始文本行号，0-based）——供「块→文本定位」
export function collectLogicalLines(text) {
  const out = []
  const rawLines = text.split('\n')
  let buf = null
  for (let i = 0; i < rawLines.length; i++) {
    const line = rawLines[i].trim()
    if (!line || line.startsWith('#')) continue
    if (!buf) buf = { text: line, start: i }
    else buf.text += ' ' + line
    const opens = (buf.text.match(/\[/g) || []).length
    const closes = (buf.text.match(/\]/g) || []).length
    if (opens <= closes) { out.push({ text: buf.text, start: buf.start, end: i }); buf = null }
  }
  if (buf) out.push({ text: buf.text, start: buf.start, end: rawLines.length - 1 })
  return out
}

function newBlock(type, data) {
  return { type, data }
}

export function parseToml(text) {
  const blocks = []
  let cur = null
  let mode = ''            // banner|pool|reward|lifecycle|card|weight|pity|pitylife|milestone|bonus|bonus_resources|target|defs|initial|rarity|strategy|raw
  let curStart = -1
  let curEnd = -1
  let curPool = null
  let curReward = null
  let curEntry = null    // card/weight/target 聚合表的当前条目
  let pendingRaw = null    // _raw 块：{ lines, start, end }

  // 块完成：补全 lines 行号区间（供「块→文本定位」）
  const closeCur = () => {
    if (cur && curStart >= 0) {
      cur.lines = [curStart, curEnd]
      cur = null
    }
  }
  const openBlock = (type, data, line) => {
    closeCur()
    const b = newBlock(type, data)
    cur = b
    curStart = line.start
    curEnd = line.end
    blocks.push(b)
    return b
  }
  const touchCur = (line) => { if (cur) curEnd = Math.max(curEnd, line.end) }
  const pushRaw = (line) => {
    if (!pendingRaw) pendingRaw = { lines: [], start: line.start, end: line.end }
    pendingRaw.lines.push(line.text)
    pendingRaw.end = line.end
  }
  const flushRaw = () => {
    if (pendingRaw && pendingRaw.lines.length) {
      blocks.push({ type: '_raw', data: { text: pendingRaw.lines.join('\n') }, lines: [pendingRaw.start, pendingRaw.end] })
      pendingRaw = null
    }
  }

  const assign = (key, v) => {
    if (mode === 'banner') cur.data[key] = v
    else if (mode === 'pool') curPool[key] = v
    else if (mode === 'reward') curReward[key] = v
    else if (mode === 'card' || mode === 'weight' || mode === 'target') curEntry[key] = v
    else if (mode === 'lifecycle') { const l = cur.data.lifecycle[cur.data.lifecycle.length - 1]; if (l) l[key] = v }
    else if (mode === 'pitylife') { cur.data.lifecycle = cur.data.lifecycle || {}; cur.data.lifecycle[key] = v }
    else if (mode === 'bonus') cur.data.bonus_reward[key] = v
    else if (mode === 'bonus_resources') cur.data.bonus_reward.resources[key] = v
    else if (mode === 'defs') {
      const e = cur.data.entries.find((x) => x.key === key)
      if (e) e.name = v
      else cur.data.entries.push({ key, name: v, initial: '' })
    } else if (mode === 'initial') {
      const e = cur.data.entries.find((x) => x.key === key)
      if (e) e.initial = v
      else cur.data.entries.push({ key, name: '', initial: v })
    } else cur.data[key] = v
  }

  for (const line of collectLogicalLines(text)) {
    const lineText = line.text
    const arrMatch = lineText.match(/^\[\[(.+)\]\]$/)
    const tabMatch = lineText.match(/^\[(.+)\]$/)

    if (arrMatch) {
      const path = arrMatch[1]
      if (path === 'banner') {
        flushRaw()
        openBlock('banner', { id: '', name: '', pools: [], lifecycle: [] }, line)
        mode = 'banner'
      } else if (path === 'banner.pool') {
        curPool = { id: '', cost: 'draw_resource:160', rewards: [] }
        cur.data.pools.push(curPool)
        mode = 'pool'
        touchCur(line)
      } else if (path === 'banner.pool.reward') {
        curReward = { card_id: '', probability: 0, rarity: 'r', featured: false }
        curPool.rewards.push(curReward)
        mode = 'reward'
        touchCur(line)
      } else if (path === 'banner.lifecycle') {
        cur.data.lifecycle.push({ condition: '', pool: '', at: 0, match: 'card_id', action: 'switch_to', target: '' })
        mode = 'lifecycle'
        touchCur(line)
      } else if (path === 'card' || path === 'weights' || path === 'targets') {
        // 聚合条目表：[[card]] / [[weights]] / [[targets]] 归并到一个块（每项一个条目）
        flushRaw()
        const kind = path === 'card' ? 'card' : path === 'weights' ? 'weight' : 'target'
        const defaults = path === 'card' ? { card_id: '', name: '', rarity: 'r', initial_count: 0 }
          : path === 'weights' ? { card_id: '', desire: 1, miss_cost: 1, card_value: 1 }
          : { card_id: '', quantity: 1, pool_ids: [] }
        if (cur && cur.type === kind) { cur.data.entries.push(defaults); touchCur(line) }
        else { openBlock(kind, { entries: [] }, line); cur.data.entries.push(defaults) }
        curEntry = cur.data.entries[cur.data.entries.length - 1]
        mode = kind
      } else if (path === 'pity') {
        flushRaw(); openBlock('pity', { name: '', type: 'soft_interval', scope: 'ssr' }, line); mode = 'pity'
      } else if (path === 'milestone') {
        flushRaw(); openBlock('milestone', { name: '', threshold: 40, repeat: false, max_triggers: 0, banner: '', bonus_reward: { cards: [], resources: {}, random_cards: [] } }, line); mode = 'milestone'
      } else if (path === 'targets') {
        // 已被上方聚合分支覆盖（保留此处避免逻辑分支遗漏）
        flushRaw(); openBlock('target', { entries: [] }, line)
        cur.data.entries.push({ card_id: '', quantity: 1, pool_ids: [] })
        curEntry = cur.data.entries[cur.data.entries.length - 1]
        mode = 'target'
      } else {
        // 未知数组表（resources.gain_rules 等）→ 原始文本块兜底
        flushRaw(); pushRaw(line); mode = 'raw'
      }
      continue
    }

    if (tabMatch) {
      const path = tabMatch[1]
      if (path === 'resources') {
        // resources 主表：gain_rules / day_overrides 等未建模内容 → 原始文本兜底
        flushRaw(); pushRaw(line); mode = 'raw'
      } else if (path === 'resources.defs') {
        flushRaw()
        if (!cur || cur.type !== 'resource') openBlock('resource', { entries: [] }, line)
        else touchCur(line)
        mode = 'defs'
      } else if (path === 'resources.initial') {
        if (!cur || cur.type !== 'resource') openBlock('resource', { entries: [] }, line)
        else touchCur(line)
        mode = 'initial'
      } else if (path === 'milestone.bonus_reward') {
        cur.data.bonus_reward = cur.data.bonus_reward || { cards: [], resources: {}, random_cards: [] }
        mode = 'bonus'
        touchCur(line)
      } else if (path === 'milestone.bonus_reward.resources') {
        // 真实 config.toml 的 resources 是子表写法（非内联 dict）
        cur.data.bonus_reward = cur.data.bonus_reward || { cards: [], resources: {}, random_cards: [] }
        cur.data.bonus_reward.resources = cur.data.bonus_reward.resources || {}
        mode = 'bonus_resources'
        touchCur(line)
      } else if (path === 'rarities') {
        flushRaw(); openBlock('rarity', { ranks: [] }, line); mode = 'rarity'
      } else if (path === 'strategy') {
        flushRaw(); openBlock('strategy', { key: '' }, line); mode = 'strategy'
      } else if (path === 'pity.lifecycle') {
        cur.data.lifecycle = cur.data.lifecycle || {}
        mode = 'pitylife'
        touchCur(line)
      } else if (path === 'rarity_defaults') {
        flushRaw(); pushRaw(line); mode = 'raw'
      } else {
        // 其他未知段（[card.tags] / [card.overflow] 等）→ 原始文本兜底
        flushRaw(); pushRaw(line); mode = 'raw'
      }
      continue
    }

    // kv 行
    const kv = lineText.match(/^([A-Za-z0-9_.]+)\s*=\s*(.+)$/)
    if (kv) {
      const v = parseValue(kv[2])
      if (mode === 'raw') {
        pushRaw(line)
      } else if ((kv[1] === 'card' || kv[1] === 'weights') && Array.isArray(v) && v.length && typeof v[0] === 'object') {
        // 顶层内联数组表 card = [ {...}, ... ] / weights = [ {...}, ... ] → 聚合进条目表块
        flushRaw()
        const kind = kv[1] === 'card' ? 'card' : 'weight'
        if (!cur || cur.type !== kind) openBlock(kind, { entries: [] }, line)
        else touchCur(line)
        cur.data.entries.push(...v)
      } else {
        assign(kv[1], v)
        touchCur(line)
      }
    }
  }
  closeCur()
  flushRaw()
  return blocks
}

// ══════════════════════════════════════════════════════════════════
// 序列化：块列表 → 真实 TOML（类型正确 + 嵌套结构）
// ══════════════════════════════════════════════════════════════════

// 各块类型「已建模」字段——之外的字段（保底专用参数等）序列化时原样写回，round-trip 不丢
const KNOWN_KEYS = {
  banner:    ['id', 'name', 'enabled', 'max_draws', 'start_day', 'end_day', 'pools', 'lifecycle'],
  card:      ['entries'],
  pity:      ['name', 'type', 'scope', 'target_featured', 'threshold', 'reset', 'start', 'end', 'counter_init', 'pools', 'lifecycle'],
  milestone: ['name', 'threshold', 'repeat', 'max_triggers', 'banner', 'bonus_reward'],
  target:    ['entries'],
  weight:    ['entries'],
  rarity:    ['ranks'],
  strategy:  ['key', 'params'],
}

// 已知字段之外的参数 → TOML 行（保持原值，类型正确）
function extraToml(d, type) {
  const known = new Set(KNOWN_KEYS[type] || [])
  const out = []
  for (const [k, v] of Object.entries(d)) {
    if (known.has(k)) continue
    if (v === undefined || v === null || v === '') continue
    out.push(`${k} = ${serializeValue(v)}`)
  }
  return out
}

export function blockToToml(b) {
  const d = b.data
  switch (b.type) {
    case 'banner': {
      const lines = ['[[banner]]']
      for (const key of ['id', 'name']) {
        if (d[key] !== undefined && d[key] !== '') lines.push(`${key} = ${serializeValue(d[key])}`)
      }
      if (d.enabled === false) lines.push('enabled = false')
      if (d.max_draws) lines.push(`max_draws = ${d.max_draws}`)
      if (d.start_day !== undefined && d.start_day !== null && d.start_day !== '') lines.push(`start_day = ${d.start_day}`)
      if (d.end_day !== undefined && d.end_day !== null && d.end_day !== '') lines.push(`end_day = ${d.end_day}`)
      const poolParts = (d.pools || []).map((p) => {
        const pl = ['[[banner.pool]]', `id = ${serializeValue(p.id)}`, `cost = ${serializeValue(p.cost)}`]
        if (p.batch_size && p.batch_size !== 1) pl.push(`batch_size = ${p.batch_size}`)
        if (p.excludes_all_pity) pl.push('excludes_all_pity = true')
        if (p.max_draws) pl.push(`max_draws = ${p.max_draws}`)
        if (p.exchange_card_id) pl.push(`exchange_card_id = ${serializeValue(p.exchange_card_id)}`)
        if (p.epitomizable_cards && p.epitomizable_cards.length) pl.push(`epitomizable_cards = ${serializeValue(p.epitomizable_cards)}`)
        const rew = (p.rewards || []).map((r) => {
          const rl = ['[[banner.pool.reward]]', `card_id = ${serializeValue(r.card_id)}`, `probability = ${r.probability}`]
          if (r.rarity) rl.push(`rarity = ${serializeValue(r.rarity)}`)
          if (r.featured) rl.push('featured = true')
          if (r.resources_gained && Object.keys(r.resources_gained).length) rl.push(`resources_gained = ${serializeValue(r.resources_gained)}`)
          return rl.join('\n')
        })
        return pl.concat(rew).join('\n')
      })
      const life = (d.lifecycle || []).map((l) => {
        const ll = ['[[banner.lifecycle]]', `condition = ${serializeValue(l.condition)}`]
        if (l.pool) ll.push(`pool = ${serializeValue(l.pool)}`)
        ll.push(`at = ${l.at ?? 0}`)
        if (l.match && l.match !== 'card_id') ll.push(`match = ${serializeValue(l.match)}`)
        if (l.action && l.action !== 'switch_to') ll.push(`action = ${serializeValue(l.action)}`)
        if (l.target) ll.push(`target = ${serializeValue(l.target)}`)
        return ll.join('\n')
      })
      return lines.concat(poolParts, life, extraToml(d, 'banner')).join('\n')
    }
    case 'resource': {
      const entries = d.entries || []
      const defs = entries.filter((e) => e.name).map((e) => `${e.key} = ${serializeValue(e.name)}`).join('\n')
      const initial = entries.filter((e) => e.initial !== undefined && e.initial !== null && e.initial !== '').map((e) => `${e.key} = ${e.initial}`).join('\n')
      const parts = []
      // 至少输出 [resources.defs] 段头——空资源块在 round-trip 中保留（不凭空消失）
      parts.push('[resources.defs]' + (defs ? '\n' + defs : ''))
      if (initial) parts.push('[resources.initial]\n' + initial)
      return parts.join('\n\n')
    }
    case 'card': {
      // 聚合条目表：每项输出一个 [[card]] 段
      return (d.entries || []).map((e) => {
        const lines = ['[[card]]']
        for (const key of ['card_id', 'name', 'rarity', 'initial_count']) {
          if (e[key] !== undefined && e[key] !== null && e[key] !== '') lines.push(`${key} = ${serializeValue(e[key])}`)
        }
        if (e.tags && Object.keys(e.tags).length) lines.push(`tags = ${serializeValue(e.tags)}`)
        if (e.list_tags && Object.keys(e.list_tags).length) lines.push(`list_tags = ${serializeValue(e.list_tags)}`)
        if (e.overflow_bands && e.overflow_bands.length) lines.push(`overflow_bands = ${serializeValue(e.overflow_bands)}`)
        return lines.join('\n')
      }).join('\n\n')
    }
    case 'pity': {
      const lines = ['[[pity]]']
      for (const key of ['name', 'type', 'scope']) {
        if (d[key] !== undefined && d[key] !== '') lines.push(`${key} = ${serializeValue(d[key])}`)
      }
      for (const key of ['target_featured', 'threshold', 'reset', 'start', 'end', 'counter_init']) {
        const v = d[key]
        if (v !== undefined && v !== null && v !== '' && v !== false) lines.push(`${key} = ${serializeValue(v)}`)
      }
      if (d.pools && d.pools.length) lines.push(`pools = ${serializeValue(d.pools)}`)
      if (d.lifecycle && Object.keys(d.lifecycle).length) lines.push(`lifecycle = ${serializeValue(d.lifecycle)}`)
      // 已知字段之外的参数（事件驱动型专用等）原样写回，round-trip 不丢
      return lines.concat(extraToml(d, 'pity')).join('\n')
    }
    case 'milestone': {
      const lines = ['[[milestone]]']
      for (const key of ['name', 'threshold', 'repeat', 'max_triggers', 'banner']) {
        const v = d[key]
        if (v !== undefined && v !== null && v !== '' && v !== false) lines.push(`${key} = ${serializeValue(v)}`)
      }
      const br = d.bonus_reward
      if (br && (br.cards?.length || Object.keys(br.resources || {}).length || br.random_cards?.length)) {
        lines.push('[milestone.bonus_reward]')
        if (br.cards?.length) lines.push(`cards = ${serializeValue(br.cards)}`)
        if (Object.keys(br.resources || {}).length) lines.push(`resources = ${serializeValue(br.resources)}`)
        if (br.random_cards?.length) lines.push(`random_cards = ${serializeValue(br.random_cards)}`)
      }
      return lines.concat(extraToml(d, 'milestone')).join('\n')
    }
    case 'target': {
      return (d.entries || []).map((e) => {
        const lines = ['[[targets]]']
        for (const key of ['card_id', 'quantity']) {
          if (e[key] !== undefined && e[key] !== null && e[key] !== '') lines.push(`${key} = ${serializeValue(e[key])}`)
        }
        if (e.pool_ids && e.pool_ids.length) lines.push(`pool_ids = ${serializeValue(e.pool_ids)}`)
        return lines.join('\n')
      }).join('\n\n')
    }
    case 'weight': {
      return (d.entries || []).map((e) => {
        const lines = ['[[weights]]']
        for (const key of ['card_id', 'desire', 'miss_cost', 'card_value']) {
          const v = e[key]
          if (v !== undefined && v !== null && v !== '') lines.push(`${key} = ${serializeValue(v)}`)
        }
        return lines.join('\n')
      }).join('\n\n')
    }
    case 'rarity': {
      const lines = ['[rarities]']
      if (d.ranks && d.ranks.length) lines.push(`ranks = ${serializeValue(d.ranks)}`)
      return lines.concat(extraToml(d, 'rarity')).join('\n')
    }
    case 'strategy': {
      const lines = ['[strategy]']
      if (d.key) lines.push(`key = ${serializeValue(d.key)}`)
      if (d.params && Object.keys(d.params).length) lines.push(`params = ${serializeValue(d.params)}`)
      return lines.concat(extraToml(d, 'strategy')).join('\n')
    }
    case '_raw':
      return d.text || ''
    default:
      return ''
  }
}

export function blocksToToml(list) {
  return list.map((b) => blockToToml(b)).filter(Boolean).join('\n\n')
}

// ══════════════════════════════════════════════════════════════════
// 搜索配置（[[search]]）：左文本右块与一般配置一致，仅块集合与运行方式不同
//   [[search]]           搜索信息（name / mode / ref_config）
//   [search.target]      搜索目标（goal）
//   [search.start]       起始状态（budget / seed）
//   [search.strategy]    策略（key）
//   [search.run]         运行参数（n / w）
//   [search.scan]        敏感性扫描参数（param / min / max / step / metric）
// ══════════════════════════════════════════════════════════════════

export const SEARCH_BLOCK_TYPES = {
  search_meta:     { label: '搜索信息',   kind: 'entity' },
  search_target:   { label: '搜索目标',   kind: 'entity' },
  search_start:    { label: '起始状态',   kind: 'entity' },
  search_strategy: { label: '策略',       kind: 'entity' },
  search_scan:     { label: '扫描参数',   kind: 'entity' },
}

export function emptySearchToml(type) {
  const map = {
    search_meta:     '[[search]]\nname = ""\nmode = "plan_search"\nref_config = ""',
    search_target:   '[search.target]\ngoal = "min_resource"',
    search_start:    '[search.start]\nbudget = 5000\nseed = 42',
    search_strategy: '[search.strategy]\nkey = "smart"',
    search_scan:     '[search.scan]\nparam = "max_draws"\nmin = 0\nmax = 100\nstep = 10\nmetric = "target_achievement"',
  }
  return map[type] || ''
}

export const SEARCH_INITIAL_TEXT = `[[search]]
name = "搜索任务 1"
mode = "plan_search"
ref_config = "c1"

[search.target]
goal = "min_resource"

[search.start]
budget = 5000
seed = 42

[search.strategy]
key = "smart"
`

// 解析 [[search]] 及其子表 → 搜索块列表
const SEARCH_MODE = {
  'search.target':   'target',
  'search.start':    'start',
  'search.strategy': 'strategy',
  'search.scan':     'scan',
}
const SEARCH_BLOCK_FOR = {
  target: 'search_target', start: 'search_start', strategy: 'search_strategy', scan: 'search_scan',
}

export function parseSearchToml(text) {
  const blocks = []
  let cur = null
  let curStart = -1
  let curEnd = -1
  const closeCur = () => { if (cur) { cur.lines = [curStart, curEnd]; cur = null } }
  const openBlock = (type, data, line) => { closeCur(); cur = { type, data }; curStart = line.start; curEnd = line.end; blocks.push(cur) }

  for (const line of collectLogicalLines(text)) {
    const t = line.text
    const arrMatch = t.match(/^\[\[(.+)\]\]$/)
    const tabMatch = t.match(/^\[(.+)\]$/)
    if (arrMatch && arrMatch[1] === 'search') {
      openBlock('search_meta', { name: '', mode: 'plan_search', ref_config: '' }, line)
    } else if (tabMatch && SEARCH_MODE[tabMatch[1]]) {
      openBlock(SEARCH_BLOCK_FOR[SEARCH_MODE[tabMatch[1]]], {}, line)
    } else {
      const kv = t.match(/^([A-Za-z0-9_.]+)\s*=\s*(.+)$/)
      if (kv && cur) { cur.data[kv[1]] = parseValue(kv[2]); curEnd = Math.max(curEnd, line.end) }
    }
  }
  closeCur()
  return blocks
}

const SEARCH_KNOWN = {
  search_meta:     ['name', 'mode', 'ref_config'],
  search_target:   ['goal'],
  search_start:    ['budget', 'seed'],
  search_strategy: ['key'],
  search_scan:     ['param', 'min', 'max', 'step', 'metric'],
}
const SEARCH_SECTION = {
  search_meta: null,
  search_target: 'target', search_start: 'start', search_strategy: 'strategy', search_scan: 'scan',
}

export function blocksToSearchToml(list) {
  return list.map((b) => {
    const d = b.data
    const header = b.type === 'search_meta' ? '[[search]]' : `[search.${SEARCH_SECTION[b.type]}]`
    const known = SEARCH_KNOWN[b.type] || []
    const lines = [header]
    for (const k of known) {
      const v = d[k]
      if (v !== undefined && v !== null && v !== '') lines.push(`${k} = ${serializeValue(v)}`)
    }
    // 已知字段之外 → 原样写回（round-trip 不丢）
    for (const [k, v] of Object.entries(d)) {
      if (known.includes(k) || v === undefined || v === null || v === '') continue
      lines.push(`${k} = ${serializeValue(v)}`)
    }
    return lines.join('\n')
  }).filter(Boolean).join('\n\n')
}
