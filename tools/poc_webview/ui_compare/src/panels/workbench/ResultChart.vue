<template>
  <div class="result-chart">
    <!-- 加载中 -->
    <div v-if="loading" class="rs rs-loading"><span class="muted">分析运行中…</span></div>
    <!-- 真实结果 sections（后端 analysis_service 产出）-->
    <template v-else-if="sections && sections.length">
      <template v-for="(sec, i) in sections" :key="i">
        <!-- summary：键值摘要 -->
        <div v-if="sec.key === 'summary'" class="rs rs-summary">
          <div class="rs-title">{{ sec.title }}</div>
          <div class="rs-body summary-body">
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item v-for="(v, k) in sec.items || {}" :key="k" :label="k">
                {{ v }}
              </el-descriptions-item>
            </el-descriptions>
          </div>
        </div>
        <!-- gauge：数值 -->
        <div v-else-if="sec.key === 'gauge'" class="rs rs-gauge">
          <div class="rs-title">{{ sec.title }}</div>
          <div class="rs-body gauge-body">
            <div class="gauge-num">{{ sec.value ?? '—' }}</div>
            <div class="gauge-desc">{{ sec.desc || '' }}</div>
          </div>
        </div>
        <!-- chart：ChartSpec → ECharts -->
        <div v-else-if="sec.key === 'chart'" class="rs rs-chart">
          <div class="rs-title">{{ sec.title }}</div>
          <div :ref="setChartEl" class="chart-box" />
          <div v-if="tableFallback" class="chart-fallback">
            <el-table :data="tableFallback.rows" size="small" border>
              <el-table-column v-for="h in tableFallback.headers" :key="h" :label="h" :prop="h" />
            </el-table>
          </div>
        </div>
        <!-- table：el-table -->
        <div v-else-if="sec.key === 'table'" class="rs rs-table">
          <div class="rs-title">{{ sec.title }}</div>
          <div class="rs-body">
            <el-table :data="tableRows(sec)" size="small" border max-height="320">
              <el-table-column v-for="h in sec.headers || []" :key="h" :label="h">
                <template #default="{ row }">{{ row[h] }}</template>
              </el-table-column>
            </el-table>
          </div>
        </div>
        <!-- 未知 key 兜底 -->
        <div v-else class="rs rs-raw">
          <div class="rs-title">{{ sec.title }}</div>
          <pre class="raw-json">{{ JSON.stringify(sec, null, 2) }}</pre>
        </div>
      </template>
    </template>
    <!-- 无 sections：未运行时按 methodDefs 描述显示结果区框架 -->
    <template v-else>
      <template v-for="sec in def.result" :key="sec.key">
        <div v-if="sec.key === 'summary'" class="rs rs-summary">
          <div class="rs-title">{{ sec.title }}</div>
          <div class="rs-body summary-body">— 未运行 —</div>
        </div>
        <div v-else-if="sec.key === 'gauge'" class="rs rs-gauge">
          <div class="rs-title">{{ sec.title }}</div>
          <div class="rs-body gauge-body"><div class="gauge-num">—</div></div>
        </div>
        <div v-else-if="sec.key === 'chart'" class="rs rs-chart">
          <div class="rs-title">{{ sec.title }}</div>
          <div class="chart-box chart-empty" />
        </div>
        <div v-else class="rs rs-table">
          <div class="rs-title">{{ sec.title }}</div>
          <el-empty :image-size="28" :description="sec.desc || ''" />
        </div>
      </template>
      <el-empty v-if="!def.result?.length" :image-size="28" description="本方法暂无结果区" />
    </template>
    <!-- 分析错误 -->
    <el-alert v-if="error" type="error" :closable="false" :title="error" class="rs-error" />
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { methodByType } from './methodDefs.js'
import { specToECharts } from './specToECharts.js'

const props = defineProps({
  type: { type: String, required: true },
  sections: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const def = computed(() => methodByType(props.type) || { result: [] })

// ── 图表容器（函数 ref 防 v-for 收集成数组）──
const chartEl = ref(null)
function setChartEl(el) { chartEl.value = el }
let chart = null
const tableFallback = ref(null)

// chart section → ECharts。table 类型（__table 标记）→ el-table 兜底
function renderCharts() {
  const charts = (props.sections || []).filter((s) => s.key === 'chart')
  tableFallback.value = null
  if (!charts.length || !chartEl.value) return
  const first = charts[0]
  const opt = specToECharts(first.spec)
  if (opt.__table) {
    tableFallback.value = { headers: opt.headers, rows: (opt.rows || []).map((r) => {
      const o = {}
      opt.headers.forEach((h, i) => { o[h] = r[i] })
      return o
    }) }
    return
  }
  if (!chart) {
    chart = echarts.init(chartEl.value)
    window.addEventListener('resize', onResize)
    chartEl.value.addEventListener('wheel', onWheel, { passive: false })
  }
  chart.setOption(opt, true)
  // 其余 chart section 附在标题行后（紧凑展示：当前仅渲染首个，避免多图叠放）
}

function tableRows(sec) {
  return (sec.rows || []).map((r) => {
    const o = {}
    sec.headers.forEach((h, i) => { o[h] = r[i] })
    return o
  })
}

watch(() => [props.sections, props.type], async () => {
  await nextTick()
  renderCharts()
}, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (chartEl.value) chartEl.value.removeEventListener('wheel', onWheel)
  if (chart) chart.dispose()
  chart = null
})
function onResize() { chart && chart.resize() }
// Ctrl+滚轮缩放（与 ResultChart 旧逻辑一致：普通滚轮放行页面）
function onWheel(e) {
  if (!e.ctrlKey || !chart) return
  e.preventDefault()
  const opt = chart.getOption()
  const dz = (opt.dataZoom && opt.dataZoom[0]) || { start: 0, end: 100 }
  const start = dz.start ?? 0
  const end = dz.end ?? 100
  const span = end - start
  const factor = e.deltaY > 0 ? 0.85 : 1.18
  const newSpan = Math.max(8, Math.min(100, span * factor))
  const center = (start + end) / 2
  chart.dispatchAction({ type: 'dataZoom', start: Math.max(0, center - newSpan / 2), end: Math.min(100, center + newSpan / 2) })
}
</script>

<style scoped>
.result-chart {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px;
}
.rs {
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
}
.rs-title {
  padding: 3px 8px;
  font-size: 11px;
  color: var(--gsc-text-muted);
  background: var(--gsc-bg-header);
  border-bottom: 1px solid var(--gsc-border);
}
.rs-body {
  padding: 8px;
}
.summary-body {
  font-size: 12px;
}
.gauge-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px;
}
.gauge-num {
  font-size: 24px;
  font-weight: 700;
  color: var(--gsc-text-primary);
}
.gauge-desc {
  font-size: 11px;
  color: var(--gsc-text-muted);
}
.chart-box {
  height: 240px;
}
.chart-empty {
  background: #f5f5f5;
}
.chart-fallback {
  padding: 6px;
}
.rs-loading {
  padding: 12px;
  text-align: center;
}
.rs-error {
  margin-top: 6px;
}
.raw-json {
  margin: 0;
  padding: 8px;
  font-family: var(--gsc-font-mono);
  font-size: 11px;
  white-space: pre-wrap;
  max-height: 240px;
  overflow: auto;
}
</style>
