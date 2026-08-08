// 配置块渲染器核心逻辑单测（Node 直接跑，无需浏览器）
// 运行：node test-config-toml.mjs
import { parseToml, blocksToToml, parseValue, serializeValue, emptyToml, BLOCK_TYPES } from './src/panels/workbench/configToml.js'

let failed = 0
function assert(cond, msg) {
  if (cond) console.log('  ok: ' + msg)
  else { console.error('  FAIL: ' + msg); failed++ }
}
function eq(a, b, msg) { assert(JSON.stringify(a) === JSON.stringify(b), `${msg}（got ${JSON.stringify(a)}）`) }
function sec(name) { console.log('\n── ' + name + ' ──') }

// ═══ 1. 值类型解析 ═══
sec('parseValue 类型感知')
eq(parseValue('"abc"'), 'abc', '引号字符串')
eq(parseValue('123'), 123, '整数')
eq(parseValue('1.5'), 1.5, '浮点')
eq(parseValue('true'), true, '布尔 true')
eq(parseValue('false'), false, '布尔 false')
eq(parseValue('[1, 2, 3]'), [1, 2, 3], '数字数组')
eq(parseValue('["a", "b"]'), ['a', 'b'], '字符串数组')
eq(parseValue('[["SSR"],["SR"],["R"]]'), [['SSR'], ['SR'], ['R']], '二维数组（稀有度）')
eq(parseValue('{ a = 1, b = "x" }'), { a: 1, b: 'x' }, '内联表')
eq(parseValue('[]'), [], '空数组')
eq(parseValue('[{ card_id = "x", probability = 0.2 }]'), [{ card_id: 'x', probability: 0.2 }], '数组含内联表（random_cards）')
eq(parseValue('"a\\"b"'), 'a"b', '转义引号')

// ═══ 2. 值序列化 ═══
sec('serializeValue 类型正确')
assert(serializeValue(123) === '123', '数字不引号')
assert(serializeValue(1.5) === '1.5', '浮点不引号')
assert(serializeValue(true) === 'true', '布尔不引号')
assert(serializeValue('abc') === '"abc"', '字符串引号')
assert(serializeValue(['a', 'b']) === '["a", "b"]', '字符串数组')
assert(serializeValue([['SSR'], ['SR']]) === '[["SSR"], ["SR"]]', '二维数组')
assert(serializeValue({ a: 1 }) === '{ a = 1 }', '内联表')

// ═══ 3. 跨行数组（真实 config.toml 的 pool_ids 写法）═══
sec('多行数组收集')
const multi = parseToml('[[targets]]\ncard_id = "x"\nquantity = 1\npool_ids = [\n    "b1.main",\n    "b2.main",\n]')
eq(multi[0].data.entries[0].pool_ids, ['b1.main', 'b2.main'], '跨行 pool_ids 解析')

// ═══ 4. 嵌套数组表归属（banner 聚合实体）═══
sec('嵌套归属：banner.pool.reward / lifecycle')
const nest = parseToml(`[[banner]]
id = "b1"
name = "B1"

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "c1"
probability = 0.2
rarity = "ssr"
featured = true

[[banner.pool.reward]]
card_id = "c2"
probability = 15.75
rarity = "r"
featured = false

[[banner.lifecycle]]
condition = "time_window"
at = 21
action = "exhaust_banner"`)
assert(nest.length === 1, '嵌套段不产生独立块，只有 1 个 banner 块')
const b = nest[0]
eq(b.data.id, 'b1', 'banner id')
eq(b.data.pools.length, 1, '1 个池')
eq(b.data.pools[0].rewards.length, 2, '池内 2 条奖励')
eq(b.data.pools[0].rewards[0], { card_id: 'c1', probability: 0.2, rarity: 'ssr', featured: true }, '奖励字段类型正确')
eq(b.data.lifecycle.length, 1, '1 条生命周期')
eq(b.data.lifecycle[0].action, 'exhaust_banner', 'lifecycle 归属 banner')

// ═══ 5. 默认文本 round-trip ═══
sec('round-trip：parse → serialize → parse 等价')
const demo = `[[banner]]
id = "b1"
name = "周年庆"
start_day = 0
end_day = 21

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "limited_ssr_1"
probability = 0.2
rarity = "ssr"
featured = true

[[banner.pool.reward]]
card_id = "r_1"
probability = 15.75
rarity = "r"
featured = false

[[banner.lifecycle]]
condition = "time_window"
at = 21
action = "exhaust_banner"

[[card]]
card_id = "limited_ssr_1"
name = "限定角色1"
rarity = "ssr"
initial_count = 0

[[weights]]
card_id = "limited_ssr_1"
desire = 1.0
miss_cost = 1.0
card_value = 1.0

[resources.defs]
draw_resource = "抽卡资源"

[resources.initial]
draw_resource = 55000

[[pity]]
name = "ssr_soft"
type = "soft_interval"
scope = "ssr"
target_featured = true
start = 80
end = 90

[[milestone]]
name = "里程碑1"
threshold = 10
repeat = true
max_triggers = 0
banner = ""

[milestone.bonus_reward]
cards = []
resources = { exchange_currency = 1 }
random_cards = []

[[targets]]
card_id = "limited_ssr_1"
quantity = 1
pool_ids = [
    "b1.main",
]

[rarities]
ranks = [["SSR"],["SR"],["R"]]

[strategy]
key = "smart"`
const once = parseToml(demo)
const twice = parseToml(blocksToToml(once))
// 以「序列化后重新解析」的结构对比（忽略块顺序差异 → 用 JSON 全比较）
eq(once.map((x) => x.type), twice.map((x) => x.type), '块类型序列一致')
eq(JSON.parse(JSON.stringify(once.map((x) => x.data))), JSON.parse(JSON.stringify(twice.map((x) => x.data))), '块数据 round-trip 等价')
assert(once.length === 9, '9 个块（banner/card/weight/resource/pity/milestone/target/rarity/strategy）')

// ═══ 6. 空模板 round-trip ═══
sec('空模板 round-trip（9 种块类型）')
for (const t of Object.keys(BLOCK_TYPES)) {
  const p = parseToml(emptyToml(t))
  const r = blocksToToml(p)
  const p2 = parseToml(r)
  eq(p2.map((x) => x.type), [t], `${t} 空模板可解析且序列化后仍为 ${t} 块`)
}

// ═══ 7. 未建模段（resources 主表 gain_rules/day_overrides）→ _raw 兜底不丢 ═══
sec('未建模段 → _raw 兜底（round-trip 不丢）')
const rawIn = `[resources]
gain_rules = [
    { type = "every_n_days", param = "", gains = { draw_resource = 60 } },
]
day_overrides = [
    { day = 0, gains = { draw_resource = 200 } },
]

[resources.defs]
draw_resource = "抽卡资源"

[resources.initial]
draw_resource = 55000`
const rawP = parseToml(rawIn)
assert(rawP.some((x) => x.type === '_raw'), 'gain_rules/day_overrides 归入 _raw 块')
assert(rawP.some((x) => x.type === 'resource'), 'defs/initial 归入 resource 块')
const rawText = blocksToToml(rawP)
const rawP2 = parseToml(rawText)
assert(rawP2.some((x) => x.type === '_raw' && x.data.text.includes('gain_rules')), 'round-trip 后 gain_rules 文本保留')
assert(rawP2.some((x) => x.type === '_raw' && x.data.text.includes('day_overrides')), 'round-trip 后 day_overrides 文本保留')

// ═══ 8. pity 未渲染参数（_extra）写回不丢 ═══
sec('pity 专用参数（_extra）round-trip 不丢')
const pityExtra = parseToml('[[pity]]\nname = "p1"\ntype = "targeted"\nscope = "ssr"\nfate_threshold = 2\nswitch_allowed = true')
const pt = blocksToToml(pityExtra)
assert(pt.includes('fate_threshold = 2'), '未渲染参数 fate_threshold 写回')
assert(pt.includes('switch_allowed = true'), '未渲染参数 switch_allowed 写回')

// ═══ 9. milestone bonus_reward round-trip ═══
sec('milestone bonus_reward（含 random_cards）round-trip')
const ml = parseToml(`[[milestone]]
name = "m1"
threshold = 10
repeat = true
max_triggers = 0
banner = ""

[milestone.bonus_reward]
cards = ["c1", "c2"]
resources = { exchange_currency = 300 }
random_cards = [{ candidates = ["c1", "c2"], weights = [1.0, 2.0], count = 1 }]`)
const mlText = blocksToToml(ml)
const ml2 = parseToml(mlText)
eq(ml2[0].data.bonus_reward.cards, ['c1', 'c2'], 'cards round-trip')
eq(ml2[0].data.bonus_reward.resources, { exchange_currency: 300 }, 'resources round-trip')
eq(ml2[0].data.bonus_reward.random_cards, [{ candidates: ['c1', 'c2'], weights: [1.0, 2.0], count: 1 }], 'random_cards round-trip')

// ═══ 10. resource 块多条条目聚合 ═══
sec('resource 块多条条目聚合')
const rc = parseToml(`[resources.defs]
a = "资源A"
b = "资源B"

[resources.initial]
a = 100`)
eq(rc[0].data.entries, [{ key: 'a', name: '资源A', initial: 100 }, { key: 'b', name: '资源B', initial: '' }], 'defs+initial 合并为条目')

// ═══ 11. 布尔序列化正确（enabled=false 才写）═══
sec('banner enabled/max_draws 边界')
const bann = parseToml('[[banner]]\nid = "x"\nname = "X"\nenabled = false\nmax_draws = 0\nstart_day = 0\nend_day = 21')
const bt = blocksToToml(bann)
assert(bt.includes('enabled = false'), 'enabled=false 写回')
assert(!bt.includes('max_draws'), 'max_draws=0（无限制）不写')

// ═══ 12. 顶层内联数组（真实 config.toml 的 card= / weights= 写法）═══
sec('顶层内联数组 card= / weights=')
const topArr = parseToml(`card = [
    { card_id = "c1", name = "卡1", rarity = "ssr", initial_count = 0 },
    { card_id = "c2", name = "卡2", rarity = "sr", initial_count = 0 },
]
weights = [
    { card_id = "c1", desire = 1.0, miss_cost = 1.0, card_value = 1.0 },
]`)
assert(topArr.filter((b) => b.type === 'card').length === 1, 'card 内联数组聚合 1 个卡片块')
eq(topArr[0].data.entries.length, 2, '卡片块含 2 个条目')
eq(topArr[0].data.entries[0].card_id, 'c1', '卡片条目字段正确')
assert(topArr.filter((b) => b.type === 'weight').length === 1, 'weights 内联数组聚合 1 个权重块')
eq(topArr[1].data.entries.length, 1, '权重块含 1 个条目')
const ta2 = parseToml(blocksToToml(topArr))
eq(ta2.map((b) => b.type), topArr.map((b) => b.type), '顶层内联数组 round-trip 块类型一致')
eq(ta2[0].data.entries.length, 2, 'round-trip 后卡片条目数一致')

// ═══ 13. 模拟块编辑写回（渲染→文本→重解析 双向同步核心链路）═══
sec('模拟块编辑写回')
let editBlocks = parseToml(demo)
editBlocks[0].data.name = '改名后的 Banner'
editBlocks[0].data.pools[0].rewards[0].probability = 99.5
editBlocks[4].data.start = 75
const newText = blocksToToml(editBlocks)
assert(newText.includes('name = "改名后的 Banner"'), 'banner 名称编辑写回文本')
assert(newText.includes('probability = 99.5'), '奖励概率编辑写回文本')
assert(newText.includes('start = 75'), 'pity 起始水位编辑写回文本')
const reEdited = parseToml(newText)
eq(reEdited[0].data.name, '改名后的 Banner', '重解析后 banner 名称生效')
eq(reEdited[0].data.pools[0].rewards[0].probability, 99.5, '重解析后奖励概率生效')
eq(reEdited[4].data.start, 75, '重解析后 pity 起始水位生效')
// 幂等：serialize(parse(x)) 后再 serialize 不变（稳定收敛，无振荡）
const stable = blocksToToml(parseToml(newText))
assert(stable === newText, '序列化稳定收敛（无循环振荡）')

// ═══ 14. 块 → 文本定位：lines 行号区间准确 ═══
sec('块→文本定位 lines 行号')
const locText = `[[banner]]
id = "b1"
name = "B1"

[[card]]
card_id = "c1"

[[pity]]
name = "p1"`
const loc = parseToml(locText)
eq(loc[0].lines, [0, 2], 'banner 行区间 [0,2]（内容行，空行不计）')
eq(loc[1].lines, [4, 5], 'card 行区间 [4,5]')
eq(loc[2].lines, [7, 8], 'pity 行区间 [7,8]')
// 嵌套段归入 banner 区间
const loc2 = parseToml(`[[banner]]
id = "b1"

[[banner.pool]]
id = "main"

[[banner.pool.reward]]
card_id = "c1"
probability = 0.2

[[card]]
card_id = "c2"`)
eq(loc2[0].lines, [0, 8], 'banner 含嵌套池/奖励行区间扩展')
eq(loc2[1].lines, [10, 11], 'card 与 banner 分开')
// 多行数组的 lines 覆盖整个数组
const loc3 = parseToml(`[[targets]]
card_id = "x"
pool_ids = [
    "a.main",
    "b.main",
]`)
eq(loc3[0].lines, [0, 5], 'targets 多行数组区间 [0,5]')

// ═══ 15. 池子额外参数 round-trip（不计保底/一次性/池最大抽数/定轨卡 + 奖励资源获取）═══
sec('池子额外参数 + 奖励资源获取')
const poolExtra = parseToml(`[[banner]]
id = "b1"
name = "B1"

[[banner.pool]]
id = "main"
cost = "draw_resource:160"
batch_size = 10
excludes_all_pity = true
max_draws = 80
exchange_card_id = "c1"
epitomizable_cards = ["c1"]

[[banner.pool.reward]]
card_id = "c1"
probability = 100.0
rarity = "ssr"
featured = true
resources_gained = { exchange_currency = 60 }`)
const pe2 = parseToml(blocksToToml(poolExtra))
const ppx = pe2[0].data.pools[0]
eq(ppx.excludes_all_pity, true, '不计保底 round-trip')
eq(ppx.exchange_card_id, 'c1', '一次性卡 round-trip')
eq(ppx.max_draws, 80, '池最大抽数 round-trip')
eq(ppx.epitomizable_cards, ['c1'], '定轨卡 round-trip')
eq(ppx.rewards[0].resources_gained, { exchange_currency: 60 }, '奖励资源获取 round-trip')

console.log(failed ? `\n${failed} 项失败` : '\n全部通过')
process.exit(failed ? 1 : 0)
