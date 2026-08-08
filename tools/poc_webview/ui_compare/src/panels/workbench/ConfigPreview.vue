<template>
  <div class="cfg-preview">
    <div class="pv-head">
      <el-radio-group v-model="tab" size="small">
        <el-radio-button value="timeline">时间线预览</el-radio-button>
        <el-radio-button value="calendar">日历预览</el-radio-button>
        <el-radio-button value="summary">配置摘要</el-radio-button>
      </el-radio-group>
      <span class="muted pv-hint">累积资源曲线（各资源着色）在上 · 池子行区（开放区间线段）· 规则行区（保底/累抽作用池，点色对应池线）</span>
    </div>

    <!-- 时间线预览：资源曲线 + 池子行区（甘特）+ 规则行区 -->
    <div v-show="tab === 'timeline'" class="pv-section">
      <div :ref="setTlEl" class="tl-chart" />
      <div class="pv-legend">
        <span class="muted">时间线轴（天）下为每池开放区间；再下方为保底/累抽规则作用池（台阶中点 + 竖直虚线）</span>
      </div>
    </div>

    <!-- 日历预览：复用 Element Plus el-calendar，定制月份导航 + 每天资源获取标注 -->
    <div v-show="tab === 'calendar'" class="pv-section pv-cal">
      <el-calendar v-model="calDate">
        <template #header="{ date }">
          <div class="cal-header">
            <span class="cal-title">{{ fmtMonth(date) }}</span>
            <div class="cal-nav">
              <el-button size="small" text @click="calDate = shiftMonth(-1)">‹ 上月</el-button>
              <el-button size="small" text @click="calDate = new Date()">今天</el-button>
              <el-button size="small" text @click="calDate = shiftMonth(1)">下月 ›</el-button>
            </div>
          </div>
        </template>
        <template #date-cell="{ data }">
          <div class="cal-cell" :class="{ 'is-today': isToday(data.day), 'is-other': data.type === 'prev-month' || data.type === 'next-month' }">
            <div class="cal-day">{{ Number(data.day.split('-')[2]) }}</div>
            <div v-for="(amt, res) in dayGains(data.day) || {}" :key="res" class="cal-gain" :style="{ color: resColor(res), background: resColor(res) + '22' }">+{{ amt }}</div>
          </div>
        </template>
      </el-calendar>
      <div class="cal-legend">
        <span class="muted">彩色数字 = 当日资源获取（颜色按资源类型区分；day_overrides 与每日规则累加）</span>
        <span class="legend-today">蓝圈 = 今天</span>
      </div>
    </div>

    <!-- 配置摘要：聚合各块统计（对齐旧 config_panel 预览文本摘要）-->
    <div v-show="tab === 'summary'" class="pv-section">
      <div class="sum-grid">
        <div v-for="(v, k) in summaryItems" :key="k" class="sum-item">
          <div class="sum-key">{{ k }}</div>
          <div class="sum-val">{{ v }}</div>
        </div>
      </div>
      <div v-if="summaryPity.length" class="sum-block">
        <div class="sum-block-title">保底规则（{{ summaryPity.length }}）</div>
        <div v-for="(p, i) in summaryPity" :key="'p' + i" class="sum-line">{{ p }}</div>
      </div>
      <div v-if="summaryMilestone.length" class="sum-block">
        <div class="sum-block-title">累抽奖励（{{ summaryMilestone.length }}）</div>
        <div v-for="(m, i) in summaryMilestone" :key="'m' + i" class="sum-line">{{ m }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { parseToml } from './configToml.js'

const props = defineProps({ configText: { type: String, default: '' } })
const tab = ref('timeline')
const calDate = ref(new Date())

// ── 数据解析：池子开放区间 + 资源获取规则 + 保底/累抽规则 ──
const previewData = computed(() => {
  try {
    const blocks = parseToml(props.configText || '')
    const resBlock = blocks.find((b) => b.type === 'resource')
    const banners = blocks
      .filter((b) => b.type === 'banner')
      .map((b) => ({
        id: b.data.id, name: b.data.name || b.data.id,
        start: b.data.start_day ?? 0, end: b.data.end_day ?? null,
      }))
    // 资源定义（defs 的 key → 显示名）
    const resources = {}
    for (const e of resBlock?.data?.entries || []) {
      if (e.key && e.name) resources[e.key] = e.name
      else if (e.key) resources[e.key] = e.key
    }
    // 保底规则（pools 全限定 fnmatch）与累抽（banner 空=全部）
    const pityRules = blocks.filter((b) => b.type === 'pity').map((b) => ({
      name: b.data.name || '保底', pools: Array.isArray(b.data.pools) ? b.data.pools : ['*'],
    }))
    const milestoneRules = blocks.filter((b) => b.type === 'milestone').map((b) => ({
      name: b.data.name || '累抽', banner: b.data.banner || '',
    }))
    let startDate = new Date()
    const m = (props.configText || '').match(/sim_start_date\s*=\s*"(\d{4}-\d{2}-\d{2})"/)
    if (m && !isNaN(Date.parse(m[1]))) startDate = new Date(m[1])
    return {
      resources, banners,
      gainRules: resBlock?.data?.gainRules || [],
      dayOverrides: resBlock?.data?.dayOverrides || [],
      pityRules, milestoneRules,
      startDate,
    }
  } catch (e) {
    return { resources: {}, banners: [], gainRules: [], dayOverrides: [], pityRules: [], milestoneRules: [], startDate: new Date() }
  }
})

// ── 配置摘要（聚合各块统计，对齐旧 config_panel._do_update_preview 文本摘要）──
const fullBlocks = computed(() => {
  try { return parseToml(props.configText || '') } catch (e) { return [] }
})
const summaryItems = computed(() => {
  const banners = fullBlocks.value.filter((b) => b.type === 'banner')
  const cards = fullBlocks.value.filter((b) => b.type === 'card').flatMap((b) => b.data.entries || [])
  const targets = fullBlocks.value.filter((b) => b.type === 'target').flatMap((b) => b.data.entries || [])
  const weights = fullBlocks.value.filter((b) => b.type === 'weight').flatMap((b) => b.data.entries || [])
  const res = fullBlocks.value.find((b) => b.type === 'resource')
  const rar = fullBlocks.value.find((b) => b.type === 'rarity')
  const initRes = (res?.data?.entries || []).filter((e) => e.initial !== undefined && e.initial !== null && e.initial !== '')
    .map((e) => `${e.key}=${e.initial}`).join(' · ') || '—'
  return {
    'Banner / 池子': `${banners.length} 个 / ${banners.reduce((a, b) => a + (b.data.pools || []).length, 0)} 个池`,
    '卡牌': `${cards.length} 张（SSR ${cards.filter((c) => String(c.rarity).toLowerCase() === 'ssr').length}）`,
    '目标卡': `${targets.length} 张`,
    '权重': `${weights.length} 条`,
    '初始资源': initRes,
    '资源获取': `${(res?.data?.gainRules || []).length} 条规则 · 逐日额外 ${(res?.data?.dayOverrides || []).length} 条`,
    '稀有度层级': (rar?.data?.ranks || []).map((r) => (r || []).join('/')).join(' → ') || '—',
    '保底': `${fullBlocks.value.filter((b) => b.type === 'pity').length} 条`,
    '累抽奖励': `${fullBlocks.value.filter((b) => b.type === 'milestone').length} 条`,
  }
})
const summaryPity = computed(() => {
  const out = []
  for (const b of fullBlocks.value.filter((x) => x.type === 'pity')) {
    const d = b.data
    let s = `${d.name || '?'} · ${d.type} · scope=${d.scope}`
    if (d.threshold != null) s += ` · 阈值=${d.threshold}`
    if (d.start != null || d.end != null) s += ` · 水位=${d.start ?? ''}-${d.end ?? ''}`
    if (d.counter_init != null) s += ` · init=${d.counter_init}`
    if (Array.isArray(d.pools) && d.pools.length) s += ` · 池=${d.pools.join(',')}`
    out.push(s)
  }
  return out
})
const summaryMilestone = computed(() => {
  const out = []
  for (const b of fullBlocks.value.filter((x) => x.type === 'milestone')) {
    const d = b.data
    const br = d.bonus_reward || {}
    let s = `${d.name || '?'} · 阈值=${d.threshold}${d.repeat ? ' · 可重复' : ''}`
    if (d.banner) s += ` · banner=${d.banner}`
    const cards = br.cards || []
    const res = br.resources || {}
    const rc = br.random_cards || []
    const resTxt = Object.keys(res).length ? '+' + Object.keys(res).map((k) => `${k}:${res[k]}`).join(',') : ''
    s += ` · 奖励=${cards.length}卡${resTxt}${rc.length ? '+' + rc.length + '随机' : ''}`
    out.push(s)
  }
  return out
})

const maxDay = computed(() => {
  const fromBanners = Math.max(0, ...previewData.value.banners.map((b) => b.end ?? 0))
  const fromRules = Math.max(0, ...previewData.value.dayOverrides.map((o) => o.day ?? 0))
  return Math.max(fromBanners, fromRules, 30)
})

// 每日各资源量（gain_rules 展开 + day_overrides 累加）。
// 语义对齐引擎 core/resource_gain.py expand_gain_rules_to_schedule：
//   every_n_days param=n（空=1）→ 第 0,n,2n,… 天；weekly param=weekday(1-7) → 每周该星期几；
//   monthly_day param=日 或 "月,日"；monthly_week param="week,day" → 每月第 N 周的星期几。
// day_overrides 是「累加」（与每日规则求和），不是覆盖——字段名 legacy，引擎注释即「累加语义」。
function dailyGainByResource(maxDay) {
  const startDate = previewData.value.startDate
  const map = {}
  const add = (d, res, amt) => { if (d >= 0 && d <= maxDay && amt) { map[d] = map[d] || {}; map[d][res] = (map[d][res] || 0) + amt } }
  const dayDate = (d) => new Date(startDate.getTime() + d * 86400000)
  // Python isoweekday (1=周一..7=周日) → JS getDay() (0=周日..6=周六)
  const isoWeekday = (dt) => dt.getDay() === 0 ? 7 : dt.getDay()
  for (const g of previewData.value.gainRules) {
    const type = g.type || 'every_n_days'
    const param = (g.param === undefined || g.param === null) ? '' : String(g.param)
    const gains = g.gains || {}
    if (!Object.keys(gains).length) continue
    const grant = (d) => { for (const [res, amt] of Object.entries(gains)) add(d, res, amt) }
    if (type === 'every_n_days') {
      let n = parseInt(param, 10) || 1
      if (n <= 0) n = 1
      for (let d = 0; d <= maxDay; d += n) grant(d)
    } else if (type === 'weekly') {
      const wd = parseInt(param, 10) || 1
      for (let d = 0; d <= maxDay; d++) { if (isoWeekday(dayDate(d)) === wd) grant(d) }
    } else if (type === 'monthly_day') {
      let m = null
      let dayOfMonth = parseInt(param, 10) || 1
      if (param.includes(',')) {
        const parts = param.split(',')
        m = parseInt(parts[0], 10); dayOfMonth = parseInt(parts[1], 10)
      }
      for (let d = 0; d <= maxDay; d++) {
        const dt = dayDate(d)
        if ((m === null || dt.getMonth() + 1 === m) && dt.getDate() === dayOfMonth) grant(d)
      }
    } else if (type === 'monthly_week') {
      let parts = param.split(',')
      if (parts.length !== 2) parts = param.split('-')
      if (parts.length === 2) {
        const wk = parseInt(parts[0], 10); const wd = parseInt(parts[1], 10)
        for (let d = 0; d <= maxDay; d++) {
          const dt = dayDate(d)
          const weekOfMonth = Math.floor((dt.getDate() - 1) / 7) + 1
          if (weekOfMonth === wk && isoWeekday(dt) === wd) grant(d)
        }
      }
    }
  }
  // day_overrides：累加（引擎 day_overrides 分支「累加语义」——不是覆盖）
  for (const o of previewData.value.dayOverrides) {
    for (const [res, amt] of Object.entries(o.gains || {})) {
      if (o.day !== undefined && amt) { map[o.day] = map[o.day] || {}; map[o.day][res] = (map[o.day][res] || 0) + amt }
    }
  }
  return map
}

// 资源 → 徽标颜色（稳定：常见资源固定色，其余哈希生成；不同颜色仅代表不同资源）
const RES_NAMED = { draw_resource: '#67c23a', exchange_currency: '#e6a23c', stardust: '#9b59b6', starglitter: '#f56c6c' }
function resColor(res) {
  if (RES_NAMED[String(res)]) return RES_NAMED[String(res)]
  let h = 0
  for (const ch of String(res)) h = (h * 31 + ch.charCodeAt(0)) % 997
  return `hsl(${h % 360}, 65%, 42%)`
}

// 规则 → 作用的池子（banner 匹配）
function ruleAffectedBanners(rule) {
  const { banners } = previewData.value
  if (rule.banner !== undefined) {
    // 累抽：banner 字段（'' = 全部）
    if (!rule.banner) return banners
    return banners.filter((b) => b.id === rule.banner || rule.banner.split('.').includes(b.id))
  }
  // 保底：pools 全限定 {banner}.{pool} fnmatch
  const affected = []
  for (const b of banners) {
    const match = (rule.pools || []).some((p) => {
      const ptn = String(p)
      if (ptn === '*' || ptn === '*.main') return true
      return ptn.split('.')[0] === b.id || ptn.startsWith(b.id + '.')
    })
    if (match) affected.push(b)
  }
  return affected
}

// 池子开放区间中点（台阶中点，供规则行标记）
function midOf(banner) { return ((banner.start || 0) + (banner.end ?? banner.start ?? 0)) / 2 }

// ── 时间线 ECharts：资源曲线(上) + 池子行区(中) + 规则行区(下) ──
const tlEl = ref(null)
let tlChart = null
function setTlEl(el) { tlEl.value = el }

function buildTimeline() {
  const { resources, banners, pityRules, milestoneRules } = previewData.value
  const ROW_H = 28        // 池子/规则每行像素高
  const H_RES = 200       // 资源曲线区固定像素高
  const gain = dailyGainByResource(maxDay.value)
  const palette = ['#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de', '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc']
  const resKeys = Object.keys(resources)

  // ── grid1 资源累积获取曲线：截至第 d 天累计获取量（每种资源一条线，各自着色）──
  const resSeries = resKeys.map((rk, ri) => {
    const acc = []
    let total = 0
    for (let d = 0; d <= maxDay.value; d++) {
      total += gain[d]?.[rk] || 0
      acc.push([d, total])
    }
    return {
      type: 'line',
      xAxisIndex: 0, yAxisIndex: 0,
      smooth: true, showSymbol: false,
      data: acc,
      itemStyle: { color: palette[ri % palette.length] },
      lineStyle: { color: palette[ri % palette.length], width: 2 },
      areaStyle: { color: palette[ri % palette.length], opacity: 0.06 },
      name: resources[rk],
    }
  })

  // ── grid2 池子行区：每池一行，开放区间为水平线段（细线，端点即区间边界）──
  const poolGantt = {
    type: 'custom',
    renderItem(params, api) {
      const yv = api.coord([0, api.value(0)])
      const x1 = api.coord([api.value(1), 0])
      const x2 = api.coord([api.value(2), 0])
      return {
        type: 'line',
        shape: { x1: x1[0], y1: yv[1], x2: x2[0], y2: yv[1] },
        style: api.style({ stroke: api.value(3), lineWidth: 3 }),
      }
    },
    xAxisIndex: 1, yAxisIndex: 1,
    encode: { y: 0, x: [1, 2] },
    data: banners.map((b, i) => [i, b.start || 0, b.end ?? (b.start || 0), palette[i % palette.length]]),
    tooltip: { formatter: (p) => {
      const b = banners[p.dataIndex]
      return `池「${b.name}」开放：第 ${b.start ?? 0} - ${b.end ?? '∞'} 天`
    } },
  }

  // ── grid3 规则行区：保底/累抽每规则一行，标记作用池台阶中点 + 竖直虚线 ──
  const rules = [
    ...pityRules.map((r) => ({ name: `保底·${r.name}`, banners: ruleAffectedBanners(r), kind: 'pity' })),
    ...milestoneRules.map((r) => ({ name: `累抽·${r.name}`, banners: ruleAffectedBanners(r), kind: 'milestone' })),
  ]
  // 规则行点：每个「规则→池子」一个点（x = 池子开放区间中点）。点颜色 = 对应池子线段颜色，
  // 指示规则作用于哪几个池子；同一规则内中点相近（重叠）的点在行内上下错开显示。
  const poolColor = (bid) => {
    const i = banners.findIndex((b) => b.id === bid)
    return palette[Math.max(0, i % palette.length)]
  }
  const rulePoints = []
  rules.forEach((r, ri) => {
    const pts = []
    for (const b of r.banners) if (b.end != null) pts.push({ x: midOf(b), bid: b.id })
    pts.sort((a, b) => a.x - b.x)
    let lastX = -Infinity
    let cluster = 0
    pts.forEach((p) => {
      cluster = lastX !== -Infinity && Math.abs(p.x - lastX) < 4 ? cluster + 1 : 0
      lastX = p.x
      const yOff = cluster === 0 ? 0 : (cluster % 2 === 1 ? 1 : -1) * Math.ceil(cluster / 2) * 0.3
      rulePoints.push({
        value: [p.x, ri + Math.min(0.4, Math.max(-0.4, yOff))],
        name: `${r.name}→${banners.find((b) => b.id === p.bid)?.name || p.bid}`,
        color: poolColor(p.bid),
      })
    })
  })
  const ruleScatter2 = {
    type: 'scatter',
    xAxisIndex: 2, yAxisIndex: 2,
    symbolSize: 9, symbol: 'diamond',
    data: rulePoints,
    itemStyle: { color: (p) => (p.data && p.data.color) || '#888' },
    // 竖直虚线：从点向上（示意对应池子区间），颜色与点（对应池子）一致
    markLine: {
      silent: true, symbol: 'none',
      lineStyle: { type: 'dashed', width: 1, opacity: 0.5 },
      data: rulePoints.map((p) => ({ xAxis: p.value[0], lineStyle: { color: p.color }, label: { show: false } })),
    },
  }

  // 布局坐标：资源曲线(顶部) → 时间线轴空间(AXIS_SPACE) → 池子行 → 规则行
  const AXIS_SPACE = 34     // 时间线轴（grid1 底部）标签/刻度占位，避免与池子行重叠
  const grid1Top = 52
  const grid2Top = grid1Top + H_RES + AXIS_SPACE
  const grid3Top = grid2Top + Math.max(1, banners.length) * ROW_H + 8
  const GRID_W = Math.max(300, (tlEl.value?.clientWidth || 900) - 160)   // 三 grid 显式同宽 → x 像素一致
  const opt = {
    title: { text: '配置时间线预览（累积资源获取 · 池子开放 · 保底/累抽作用）', left: 'center', textStyle: { fontSize: 12 } },
    tooltip: { trigger: 'item' },
    legend: [
      { top: 24, left: 'center', textStyle: { fontSize: 10 }, data: resKeys.map((k) => resources[k]) },
    ],
    // 布局：资源曲线(固定高) → 时间线轴空间 → 池子行 → 规则行；每行定高，全图动态增高
    // grid 显式同宽（容器宽 - 左右留白），x 轴同范围 → 池子横条与规则点严格水平对齐
    grid: [
      { left: 130, width: GRID_W, top: grid1Top, height: H_RES },
      { left: 130, width: GRID_W, top: grid2Top, height: Math.max(1, banners.length) * ROW_H },
      { left: 130, width: GRID_W, top: grid3Top, height: Math.max(1, rules.length) * ROW_H },
    ],
    xAxis: [
      { type: 'value', gridIndex: 0, name: '天', nameLocation: 'middle', nameGap: 26, min: 0, max: maxDay.value, axisLabel: { show: true, fontSize: 10, formatter: '{value} 天' }, axisLine: { lineStyle: { width: 2, color: '#606266' } }, splitLine: { show: false } },
      { type: 'value', gridIndex: 1, min: 0, max: maxDay.value, axisLabel: { show: false }, splitLine: { show: false } },
      { type: 'value', gridIndex: 2, min: 0, max: maxDay.value, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, name: '累积获取', nameLocation: 'middle', nameGap: 40, minInterval: 1, axisLabel: { fontSize: 10 } },
      { type: 'category', gridIndex: 1, data: banners.map((b) => b.name), axisLabel: { fontSize: 10 } },
      { type: 'category', gridIndex: 2, data: rules.map((r) => r.name), axisLabel: { fontSize: 10, formatter: (v) => (v && v.length > 12 ? v.slice(0, 12) + '…' : v) }, name: '规则', nameLocation: 'middle', nameGap: 44 },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2], zoomOnMouseWheel: false, moveOnMouseWheel: true },
    ],
    series: [...resSeries, poolGantt, ruleScatter2],
  }
  // 容器高度动态 = 顶部 + 资源曲线 + 时间线轴空间 + 池子行 + 规则行 + 底部
  const totalH = grid3Top + Math.max(1, rules.length) * ROW_H + 34
  tlEl.value.style.height = totalH + 'px'
  if (!tlChart) {
    tlChart = echarts.init(tlEl.value)
    window.addEventListener('resize', onResize)
  }
  tlChart.setOption(opt, true)
}

// ── 日历：每天各资源获取（gain_rules + day_overrides 累加，按资源分别徽标）──
function dayGains(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  const diff = Math.round((d - previewData.value.startDate) / 86400000)
  if (diff < 0 || diff > maxDay.value) return null
  return dailyGainByResource(maxDay.value)[diff] || null
}
// 日历辅助：月份标题 / 月份切换 / 今天
function fmtDateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function fmtMonth(date) {
  // el-calendar header 插槽的 date 是格式化字符串（如「2026年8月」），非 Date 对象
  if (typeof date === 'string') return date
  const d = date instanceof Date ? date : new Date(date)
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月`
}
function shiftMonth(delta) {
  const d = new Date(calDate.value)
  d.setMonth(d.getMonth() + delta)
  return d
}
function isToday(dateStr) {
  return dateStr === fmtDateStr(new Date())
}

watch(() => [props.configText, tab.value], async () => {
  if (tab.value !== 'timeline') return
  await nextTick()
  if (tlEl.value) buildTimeline()
}, { deep: true })

onMounted(async () => {
  await nextTick()
  if (tlEl.value) buildTimeline()
})
function onResize() { tlChart && tlChart.resize() }
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (tlChart) tlChart.dispose()
  tlChart = null
})
</script>

<style scoped>
.cfg-preview {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  min-height: 0;
}
.pv-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pv-hint {
  font-size: 11px;
}
.pv-section {
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
  padding: 8px;
}
.tl-chart {
  min-height: 400px;
}
.pv-legend {
  margin-top: 4px;
  font-size: 11px;
}
.pv-cal :deep(.el-calendar__body) {
  padding: 6px;
}
.pv-cal :deep(.el-calendar-table .el-calendar-day) {
  padding: 2px;
}
.cal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  border-bottom: 1px solid var(--gsc-border);
}
.cal-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gsc-text-primary);
}
.cal-nav {
  display: flex;
  gap: 4px;
}
.cal-nav .el-button {
  height: 24px;
  font-size: 12px;
}
.cal-cell {
  height: 100%;
  min-height: 54px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding: 2px;
  border-radius: 4px;
  font-size: 12px;
  cursor: default;
}
.cal-cell.is-other .cal-day {
  color: var(--gsc-text-faint);
}
.cal-day {
  width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  border-radius: 50%;
  color: var(--gsc-text-primary);
}
.cal-cell.is-today .cal-day {
  background: var(--el-color-primary);
  color: #fff;
  font-weight: 700;
}
.cal-gain {
  margin-top: 2px;
  padding: 0 5px;
  border-radius: 8px;
  background: rgba(103, 194, 58, 0.12);
  color: var(--el-color-success);
  font-size: 10px;
  font-weight: 600;
}
.cal-cell:not(.is-other):hover {
  background: var(--gsc-bg-result);
}
.cal-legend {
  margin-top: 6px;
  display: flex;
  gap: 14px;
  align-items: center;
  font-size: 11px;
}
.legend-today::before {
  content: '●';
  color: var(--el-color-primary);
  margin-right: 3px;
}
/* 配置摘要 */
.sum-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 6px;
}
.sum-item {
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
  padding: 5px 8px;
}
.sum-key {
  font-size: 11px;
  color: var(--gsc-text-muted);
}
.sum-val {
  font-size: 12px;
  font-weight: 600;
  margin-top: 2px;
  word-break: break-all;
}
.sum-block {
  margin-top: 10px;
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
  padding: 6px 8px;
}
.sum-block-title {
  font-size: 11px;
  color: var(--gsc-text-muted);
  font-weight: 600;
  border-bottom: 1px solid var(--gsc-border);
  margin: -6px -8px 6px;
  padding: 3px 8px;
  background: var(--gsc-bg-header);
}
.sum-line {
  font-family: var(--gsc-font-mono);
  font-size: 11px;
  line-height: 1.6;
}
</style>
