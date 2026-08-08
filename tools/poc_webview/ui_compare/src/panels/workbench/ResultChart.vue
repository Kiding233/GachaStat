<template>
  <div class="result-chart">
    <!-- 加载中 -->
    <div v-if="loading" class="rs rs-loading"><span class="muted">分析运行中…</span></div>
    <!-- 真实结果 sections（后端 analysis_service 产出，每个 chart section 独立图表实例）-->
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
        <!-- chart：ChartSpec → ECharts（函数 ref 按 index 绑定，多图各自实例）-->
        <div v-else-if="sec.key === 'chart'" class="rs rs-chart">
          <div class="rs-title">{{ sec.title }}</div>
          <div v-if="!tableFallback[i]" :ref="(el) => setChartContainers(el, i)" class="chart-box" />
          <div v-else class="chart-fallback">
            <el-table :data="tableFallback[i].rows" size="small" border>
              <el-table-column v-for="h in tableFallback[i].headers" :key="h" :label="h" :prop="h" />
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

// ── 每个 chart section 独立容器与 echarts 实例（函数 ref 按 index 槽位绑定）──
const chartContainers = {}   // section index → DOM 元素
const chartInstances = {}    // section index → echarts 实例
const tableFallback = ref({}) // section index → { headers, rows }（__table 类型兜底表）

function setChartContainers(el, i) {
  if (el) chartContainers[i] = el
  else delete chartContainers[i]
}

function renderCharts() {
  const sections = props.sections || []
  // 清空已移除 section 的实例
  for (const k of Object.keys(chartInstances)) {
    const sec = sections[Number(k)]
    if (!sec || sec.key !== 'chart') {
      try { chartInstances[k].dispose() } catch (e) {}
      delete chartInstances[k]
    }
  }
  const nextFallback = {}
  sections.forEach((sec, i) => {
    if (sec.key !== 'chart') return
    const el = chartContainers[i]
    if (!el) return
    const opt = specToECharts(sec.spec)
    if (opt.__table) {
      // table 类型（ChartSpec chart_type='table'）→ el-table 兜底
      nextFallback[i] = {
        headers: opt.headers,
        rows: (opt.rows || []).map((r) => {
          const o = {}
          opt.headers.forEach((h, idx) => { o[h] = r[idx] })
          return o
        }),
      }
      try { if (chartInstances[i]) { chartInstances[i].dispose(); delete chartInstances[i] } } catch (e) {}
      return
    }
    let inst = chartInstances[i]
    if (!inst) {
      inst = echarts.init(el)
      chartInstances[i] = inst
      window.addEventListener('resize', onResize)
      el.addEventListener('wheel', (e) => onWheel(e, inst), { passive: false })
    }
    // 山脊线图：单子图定高，全图高度随堆叠数动态增长（容器高度 = top + rows×rowHeight）
    // 组合图（composite）：多面板按 row_heights 比例堆叠，总高已算好
    if (opt.__gscRidge) {
      el.style.height = (opt.__gscRidge.top + opt.__gscRidge.rows * opt.__gscRidge.rowHeight) + 'px'
    } else if (opt.__gscComposite && opt.__gscComposite.total) {
      el.style.height = opt.__gscComposite.total + 'px'
    } else {
      el.style.height = ''
    }
    inst.setOption(opt, true)
    inst.resize()
  })
  tableFallback.value = nextFallback
}

watch(() => props.sections, async () => {
  await nextTick()
  renderCharts()
}, { deep: true })

onBeforeUnmount(() => {
  for (const k of Object.keys(chartInstances)) {
    try { chartInstances[k].dispose() } catch (e) {}
  }
  window.removeEventListener('resize', onResize)
})
function onResize() {
  for (const k of Object.keys(chartInstances)) chartInstances[k].resize()
}
// Ctrl+滚轮缩放（每个实例独立；普通滚轮放行页面）
function onWheel(e, inst) {
  if (!e.ctrlKey || !inst) return
  e.preventDefault()
  const opt = inst.getOption()
  const dz = (opt.dataZoom && opt.dataZoom[0]) || { start: 0, end: 100 }
  const start = dz.start ?? 0
  const end = dz.end ?? 100
  const span = end - start
  const factor = e.deltaY > 0 ? 0.85 : 1.18
  const newSpan = Math.max(8, Math.min(100, span * factor))
  const center = (start + end) / 2
  inst.dispatchAction({ type: 'dataZoom', start: Math.max(0, center - newSpan / 2), end: Math.min(100, center + newSpan / 2) })
}

function tableRows(sec) {
  return (sec.rows || []).map((r) => {
    const o = {}
    sec.headers.forEach((h, i) => { o[h] = r[i] })
    return o
  })
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
