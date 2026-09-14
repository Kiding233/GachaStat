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
              <el-table-column v-for="(h, ci) in tableFallback[i].headers" :key="ci" :label="h">
                <template #default="{ row }">{{ row['_' + ci] }}</template>
              </el-table-column>
            </el-table>
          </div>
        </div>
        <!-- table：el-table -->
        <div v-else-if="sec.key === 'table'" class="rs rs-table">
          <div class="rs-title">{{ sec.title }}</div>
          <!-- 轨迹详情：全部/仅成功/仅失败 筛选（对齐旧 UI trace_filter_combo）-->
          <div v-if="sec.meta?.trace_filter" class="rs-body trace-filter">
            <el-radio-group v-model="traceFilter[i]" size="small">
              <el-radio-button :value="'all'">全部</el-radio-button>
              <el-radio-button :value="'success'">仅成功</el-radio-button>
              <el-radio-button :value="'failure'">仅失败</el-radio-button>
            </el-radio-group>
          </div>
          <div class="rs-body">
            <el-table :data="filteredRows(sec, i)" size="small" border max-height="320" :row-class-name="lowSampleRowClass">
              <el-table-column v-for="(h, ci) in sec.headers || []" :key="ci" :label="h">
                <template #default="{ row }">
                  <!-- 列值按下标取（row['_'+ci]）：避免 header 字符串作对象键——AB/BA 表两个同名
                       CI 列头（如两个 '95% CI'）若用 row[h] 会互相覆盖，旧 UI 按列索引渲染无此问题 -->
                  <span v-if="h === '▲'">{{ row['_8'] ?? row['_7'] ?? '' }}</span>
                  <span v-else>{{ row['_' + ci] }}</span>
                </template>
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
import { bindZoomWheel } from './zoomWheel.js'

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
      // 行键按下标（'_'+idx）：header 可能重复，用 header 字符串作键会互相覆盖
      nextFallback[i] = {
        headers: opt.headers,
        rows: (opt.rows || []).map((r) => {
          const o = {}
          opt.headers.forEach((_, idx) => { o['_' + idx] = r[idx] })
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
      // 滚轮统一处理：capture 拦截 zrender 的 wheel，Ctrl+滚轮缩放、普通滚轮放行页面滚动
      bindZoomWheel(el, inst)
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

function tableRows(sec) {
  // 列值按下标存取（对象键 '_'+i）：header 可能重复（AB/BA 两个 CI 列），
  // 用 header 字符串作键会互相覆盖（旧 UI QTableWidget 按列索引，无此问题）
  return (sec.rows || []).map((r) => {
    const o = {}
    sec.headers.forEach((_, i) => { o['_' + i] = r[i] })
    return o
  })
}
// 轨迹详情筛选：全部 / 仅成功 / 仅失败（按「整体」列下标 1 过滤；对齐旧 UI trace_filter_combo）
const traceFilter = ref({})
function filteredRows(sec, i) {
  const rows = tableRows(sec)
  const f = traceFilter.value[i]
  if (!sec.meta?.trace_filter || !f || f === 'all') return rows
  const want = f === 'success' ? '✓' : '✗'
  return rows.filter((r) => (r['_1'] || '').startsWith(want))
}
// AB/BA 低样本行（末列 '▲'：AB 表下标 8、BA 表下标 7 = '样本不足'）→ 灰底（对齐旧 UI 灰行）
function lowSampleRowClass({ row }) {
  if (row['_8'] === '样本不足' || row['_7'] === '样本不足') return 'low-sample-row'
  return ''
}
</script>

<style scoped>
.low-sample-row :deep(td) {
  background: #f2f2f2 !important;
  color: #9e9e9e;
}
.trace-filter {
  padding: 6px 8px;
  border-bottom: 1px solid var(--gsc-border);
}
.trace-filter .el-radio-group {
  margin: 0;
}
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
