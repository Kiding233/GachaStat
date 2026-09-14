// 真实 config.toml 完整 round-trip 验证（一次性）
import { readFileSync } from 'fs'
import { parseToml, blocksToToml } from './src/panels/workbench/configToml.js'

const text = readFileSync('../../../gacha_simulator/config/config.toml', 'utf8')
const once = parseToml(text)
const serialized = blocksToToml(once)
const twice = parseToml(serialized)

console.log('块类型序列:', once.map((b) => b.type).join(', '))
console.log('banner 块数:', once.filter((b) => b.type === 'banner').length)
console.log('_raw 块数:', once.filter((b) => b.type === '_raw').length)
console.log('pity 块数:', once.filter((b) => b.type === 'pity').length)
console.log('milestone 块数:', once.filter((b) => b.type === 'milestone').length)
console.log('target 块数:', once.filter((b) => b.type === 'target').length)
console.log('card 块数:', once.filter((b) => b.type === 'card').length)
console.log('weight 块数:', once.filter((b) => b.type === 'weight').length)

const j1 = JSON.parse(JSON.stringify(once.map((b) => b.data)))
const j2 = JSON.parse(JSON.stringify(twice.map((b) => b.data)))
const same = JSON.stringify(j1) === JSON.stringify(j2)
console.log('round-trip 数据等价:', same)
if (!same) {
  for (let i = 0; i < Math.max(j1.length, j2.length); i++) {
    if (JSON.stringify(j1[i]) !== JSON.stringify(j2[i])) {
      console.log('块', i, 'once:', JSON.stringify(j1[i])?.slice(0, 300))
      console.log('块', i, 'twice:', JSON.stringify(j2[i])?.slice(0, 300))
    }
  }
}
// _raw 保留原文中的关键内容
for (const b of once) {
  if (b.type === '_raw') {
    console.log('_raw 片段:', b.data.text.slice(0, 120).replace(/\n/g, ' '))
  }
}
