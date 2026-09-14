<template>
  <div class="cmp-wb">
    <div class="wb-head">
      <h2>对比分析任务：{{ node.label }}</h2>
      <span class="muted">跨数据集对照（L1-L4）</span>
    </div>

    <!-- 纳入数据集选择：跨配置多选表 -->
    <div class="cmp-pane">
      <div class="pane-head">纳入分析的数据集（{{ node.meta.includedDs?.length || 0 }}）</div>
      <el-table
        ref="tableRef"
        :data="groupedDatasets"
        size="small"
        row-key="id"
        @selection-change="onIncludeChange"
      >
        <el-table-column type="selection" width="34" :reserve-selection="true" />
        <el-table-column prop="label" label="数据集" min-width="150" />
        <el-table-column label="来源配置" min-width="100">
          <template #default="{ row }"><span class="muted">{{ configLabel(row.meta.sourceConfigId) }}</span></template>
        </el-table-column>
        <el-table-column label="种子/N" width="130">
          <template #default="{ row }"><span class="muted">种子{{ row.meta.seed }} · N={{ row.meta.n }}</span></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 排除数据集 -->
    <div class="cmp-pane">
      <div class="pane-head">排除数据集</div>
      <el-select v-model="node.meta.excludedDs" size="small" multiple filterable class="excl-sel" placeholder="选择要排除的数据集">
        <el-option v-for="d in excludedCandidates" :key="d.id" :label="d.label" :value="d.id" />
      </el-select>
      <div class="pane-hint">排除数据集不参与对照矩阵（但保留在任务中）。</div>
    </div>

    <!-- 运行参数 + 运行 -->
    <div class="cmp-pane cmp-params">
      <div class="p-row">
        <span class="p-label">GDR 指标</span>
        <el-select v-model="params.gdr" size="small" class="p-ctl" filterable>
          <el-option v-for="g in gdrOptions" :key="g.key" :label="g.display" :value="g.key" />
        </el-select>
        <span class="p-label">阈值</span>
        <el-input-number v-model="params.threshold" size="small" :precision="2" :controls="false" style="width: 90px" />
      </div>
      <div class="p-row">
        <span class="p-label">检验方法</span>
        <el-select v-model="params.method" size="small" class="p-ctl" style="width: 140px">
          <el-option label="MWU" value="MWU" /><el-option label="KS" value="KS" /><el-option label="t 检验" value="ttest" />
        </el-select>
        <span class="p-label">校正</span>
        <el-select v-model="params.correction" size="small" class="p-ctl" style="width: 140px">
          <el-option label="BH (FDR)" value="BH" /><el-option label="Holm (FWER)" value="Holm" /><el-option label="原始 p" value="raw" />
        </el-select>
        <el-button type="primary" size="small" :loading="running" :disabled="!includedNodes.length" @click="run" class="run-btn">运行对比分析</el-button>
      </div>
      <!-- L4 帕累托：x/y 轴 GDR 指标可选（对齐旧 comparison_analysis_panel）-->
      <div class="p-row">
        <span class="p-label">帕累托 X</span>
        <el-select v-model="params.x_gdr" size="small" class="p-ctl" filterable>
          <el-option v-for="g in gdrOptions" :key="g.key" :label="g.display" :value="g.key" />
        </el-select>
        <span class="p-label">帕累托 Y</span>
        <el-select v-model="params.y_gdr" size="small" class="p-ctl" filterable>
          <el-option v-for="g in gdrOptions" :key="g.key" :label="g.display" :value="g.key" />
        </el-select>
      </div>
    </div>

    <!-- 结果 -->
    <div v-if="resultError" class="cmp-pane"><el-alert type="error" :closable="false" :title="resultError" /></div>
    <div v-if="sections.length" class="cmp-body">
      <template v-for="(sec, i) in sections" :key="i">
        <!-- table：L2 分类矩阵带颜色（≻绿/≺红/×橙/＝灰），点击单元格 → 对 ECDF 可视化 -->
        <div v-if="sec.key === 'table'" class="res-sec">
          <div class="pane-head">{{ sec.title }}</div>
          <el-table :data="tableRows(sec)" size="small" border max-height="300" @cell-click="(row, col) => onL2CellClick(sec, row, col)">
            <el-table-column v-for="(h, ci) in sec.headers || []" :key="ci" :label="h">
              <template #default="{ row }">
                <span v-if="isL2(sec)" :style="l2CellStyle(row['_' + ci])" class="l2-cell">{{ row['_' + ci] }}</span>
                <span v-else>{{ row['_' + ci] }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <!-- chart：多图表各占容器（L1 PMF/ECDF + L4 帕累托）-->
        <div v-else-if="sec.key === 'chart'" class="res-sec">
          <div class="pane-head">{{ sec.title }}</div>
          <div :ref="(el) => setChartEl(el, i)" class="chart-box" />
        </div>
        <!-- summary -->
        <div v-else-if="sec.key === 'summary'" class="res-sec">
          <div class="pane-head">{{ sec.title }}</div>
          <div class="res-summary">
            <el-descriptions :column="2" size="small" border>
              <el-descriptions-item v-for="(v, k) in sec.items || {}" :key="k" :label="k">{{ v }}</el-descriptions-item>
            </el-descriptions>
          </div>
        </div>
      </template>
    </div>

    <!-- L2 单元格点击 → 该对数据集 ECDF 对比图 -->
    <div v-if="pairChartName" class="cmp-pane pair-chart">
      <div class="pane-head">{{ pairChartName }}（点击 L2 矩阵单元格切换）</div>
      <div :ref="setPairEl" class="pair-box" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import api from '../../api.js'
import { specToECharts } from './specToECharts.js'
import { bindZoomWheel } from './zoomWheel.js'

const props = defineProps({
  node: { type: Object, required: true },
  allDatasets: { type: Array, default: () => [] },
  configs: { type: Array, default: () => [] },
})

const running = ref(false)
const sections = ref([])
const resultError = ref('')
const tableRef = ref()

const gdrOptions = ref([])
onMounted(async () => {
  const g = await api.listGdrOptions()
  if (g?.ok) gdrOptions.value = g.options
  const include = props.node.meta.includedDs || []
  requestAnimationFrame(() => {
    if (!tableRef.value) return
    for (const row of groupedDatasets.value) {
      if (include.includes(row.id)) tableRef.value.toggleRowSelection(row, true)
    }
  })
})
const params = ref({ gdr: 'target_achievement', threshold: 1.0, method: 'MWU', correction: 'BH', x_gdr: 'target_achievement', y_gdr: 'resource_remaining' })

const groupedDatasets = computed(() =>
  props.allDatasets.map(({ id, label, meta }) => ({ id, label, meta })),
)
function configLabel(cfgId) {
  const cfg = props.configs.find((c) => c.id === cfgId)
  return cfg ? cfg.label : (cfgId || '—')
}
function onIncludeChange(rows) { props.node.meta.includedDs = rows.map((r) => r.id) }
const excludedCandidates = computed(() =>
  props.allDatasets.filter((d) => !(props.node.meta.includedDs || []).includes(d.id)),
)
const includedNodes = computed(() =>
  props.allDatasets.filter((d) => (props.node.meta.includedDs || []).includes(d.id)),
)

async function run() {
  running.value = true
  resultError.value = ''
  sections.value = []
  pairChartName.value = ''
  try {
    const ds = includedNodes.value.map((n) => n.meta.datasetId).filter(Boolean)
    const r = await api.runComparison(ds, { ...params.value })
    if (r?.ok) {
      sections.value = r.sections || []
      lastNames.value = r.names || []
      lastSamples.value = r.samples || []
    } else { resultError.value = r?.error || '比较分析失败' }
  } catch (e) {
    resultError.value = String(e)
  } finally {
    running.value = false
    await nextTick()
    renderCharts()
  }
}

// ── 多图表渲染（按 section 索引绑定容器：L1 PMF/ECDF + L4 帕累托 各自实例）──
const chartEls = {}
const chartInsts = {}
function setChartEl(el, i) { if (el) chartEls[i] = el; else delete chartEls[i] }
function renderCharts() {
  const sectionsAll = sections.value
  for (const k of Object.keys(chartInsts)) {
    const sec = sectionsAll[Number(k)]
    if (!sec || sec.key !== 'chart') { try { chartInsts[k].dispose() } catch (e) {}; delete chartInsts[k] }
  }
  sectionsAll.forEach((sec, i) => {
    if (sec.key !== 'chart') return
    const el = chartEls[i]
    if (!el) return
    const opt = specToECharts(sec.spec)
    if (!chartInsts[i]) {
      chartInsts[i] = echarts.init(el)
      window.addEventListener('resize', onResize)
      bindZoomWheel(el, chartInsts[i])
    }
    chartInsts[i].setOption(opt, true)
  })
}

// ── L2 分类矩阵：颜色单元格 + 点击 → 该对数据集 ECDF（对齐旧 comparison_analysis_panel）──
const lastNames = ref([])
const lastSamples = ref([])
function isL2(sec) { return (sec.title || '').startsWith('L2') }
function l2CellStyle(label) {
  const c = String(label || '')[0]
  const map = { '≻': '#2e7d32', '≺': '#c62828', '×': '#ef6c00', '=': '#757575', '—': '#e0e0e0', 'e': '#8b0000' }
  const bg = map[c]
  if (!bg) return {}
  return { background: bg, color: (c === '≻' || c === '≺' || c === 'e') ? '#fff' : undefined }
}
function onL2CellClick(sec, row, col) {
  if (!isL2(sec) || !col.label || col.label === '数据集') return
  // 行对象按键 _0（列下标 0 = 数据集列；tableRows 改下标键后不再有 row['数据集']）
  const i = lastNames.value.indexOf(row['_0'])
  const j = lastNames.value.indexOf(col.label)
  if (i < 0 || j < 0 || i === j) return
  renderPairCdf(i, j)
}
const pairChartName = ref('')
const pairEl = ref(null)
let pairChart = null
function setPairEl(el) { pairEl.value = el }

// j 阶积分 CDF（对齐旧 compute_integrated_cdf：order=1 经验 CDF，order=2/3 逐级 trapz 积分）
function integratedCdf(samples, grid, order) {
  const ecdf = (s, x) => samples.filter((v) => v <= x).length / samples.length
  let F = grid.map((xi) => ecdf(samples, xi))
  for (let k = 1; k < order; k++) {
    const next = []
    for (let t = 0; t < grid.length; t++) {
      let acc = 0
      for (let m = 0; m < t; m++) {
        acc += (F[m] + F[m + 1]) / 2 * (grid[m + 1] - grid[m])   // trapz
      }
      next.push(acc)
    }
    F = next
  }
  return F
}

// L2 矩阵点击 → 1/2/3 阶积分 CDF 对比（对齐旧 comparison_analysis_panel._render_l2_chart：
// 100 点网格与 PySDTest 检验域一致、三列 FSD/SSD/TSD、差异区域着色、max Δ 标注）
function renderPairCdf(i, j) {
  const a = [...(lastSamples.value[i] || [])]
  const b = [...(lastSamples.value[j] || [])]
  if (!a.length || !b.length) return
  const combined = [...a, ...b]
  const lo = Math.min(...combined)
  const hi = Math.max(...combined)
  const grid = Array.from({ length: 100 }, (_, t) => lo + (hi - lo) * t / 99)
  const nameA = lastNames.value[i]
  const nameB = lastNames.value[j]
  pairChartName.value = `${nameA} vs ${nameB} 积分 CDF（1/2/3 阶）`
  const orders = [1, 2, 3]
  const titles = ['FSD (一阶)', 'SSD (二阶)', 'TSD (三阶)']
  const grids = []
  const xAxes = []
  const yAxes = []
  const series = []
  orders.forEach((order, oi) => {
    const F_a = integratedCdf(a, grid, order)
    const F_b = integratedCdf(b, grid, order)
    series.push(
      { type: 'line', xAxisIndex: oi, yAxisIndex: oi, data: grid.map((x, t) => [+x.toFixed(4), +F_a[t].toFixed(6)]), showSymbol: false, lineStyle: { color: '#1f77b4', width: 2 }, name: nameA },
      { type: 'line', xAxisIndex: oi, yAxisIndex: oi, data: grid.map((x, t) => [+x.toFixed(4), +F_b[t].toFixed(6)]), showSymbol: false, lineStyle: { color: '#ff7f0e', width: 2 }, name: nameB },
    )
    // max Δ 标注（对齐旧 marker+text 'max Δ=x.xxx'）
    const diffAb = grid.map((x, t) => F_a[t] - F_b[t])
    const maxAb = Math.max(...diffAb)
    if (maxAb > 1e-10) {
      const idxMax = diffAb.indexOf(maxAb)
      series.push({
        type: 'scatter', xAxisIndex: oi, yAxisIndex: oi, symbol: 'triangle', symbolSize: 8,
        itemStyle: { color: '#c62828' },
        data: [[+grid[idxMax].toFixed(4), +F_a[idxMax].toFixed(6)]],
        label: { show: true, formatter: `max Δ=${maxAb.toFixed(3)}`, position: 'top', fontSize: 9, color: '#c62828' },
      })
    }
    const diffBa = grid.map((x, t) => F_b[t] - F_a[t])
    const maxBa = Math.max(...diffBa)
    if (maxBa > 1e-10) {
      const idxMax = diffBa.indexOf(maxBa)
      series.push({
        type: 'scatter', xAxisIndex: oi, yAxisIndex: oi, symbol: 'triangle', symbolSize: 8,
        itemStyle: { color: '#1565c0' },
        data: [[+grid[idxMax].toFixed(4), +F_b[idxMax].toFixed(6)]],
        label: { show: true, formatter: `max Δ=${maxBa.toFixed(3)}`, position: 'top', fontSize: 9, color: '#1565c0' },
      })
    }
    grids.push({ left: (oi * 33 + 2) + '%', right: (100 - (oi + 1) * 33 + 1) + '%', top: 50, height: '72%', title: { text: titles[oi], left: 'center', textStyle: { fontSize: 10 } } })
    xAxes.push({ type: 'value', gridIndex: oi, axisLabel: { fontSize: 9 } })
    yAxes.push({ type: 'value', gridIndex: oi, min: 0, axisLabel: { fontSize: 9 }, name: oi === 0 ? '积分值' : '', nameLocation: 'middle', nameGap: 34 })
  })
  nextTick(() => {
    if (!pairEl.value) return
    if (!pairChart) {
      pairChart = echarts.init(pairEl.value)
      window.addEventListener('resize', onResize)
      bindZoomWheel(pairEl.value, pairChart)
    }
    pairChart.setOption({
      title: { text: pairChartName.value, left: 'center', textStyle: { fontSize: 12 } },
      tooltip: { trigger: 'axis' },
      legend: { top: 24, textStyle: { fontSize: 10 } },
      grid: grids, xAxis: xAxes, yAxis: yAxes,
      series,
    }, true)
  })
}
function onResize() {
  for (const k of Object.keys(chartInsts)) { try { chartInsts[k].resize() } catch (e) {} }
  if (pairChart) pairChart.resize()
}
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  for (const k of Object.keys(chartInsts)) { try { chartInsts[k].dispose() } catch (e) {} }
  if (pairChart) pairChart.dispose()
  pairChart = null
})
function tableRows(sec) {
  // 列值按下标存取（对象键 '_'+i）：header 可能重复（如 L2/L3 矩阵表），
  // 用 header 字符串作键会互相覆盖（旧 UI QTableWidget 按列索引，无此问题）
  return (sec.rows || []).map((r) => {
    const o = {}
    sec.headers.forEach((_, i) => { o['_' + i] = r[i] })
    return o
  })
}
watch(() => props.node.meta.includedDs, async () => {
  // 数据集变化 → 清结果
  if (!props.node.meta.includedDs?.length) { sections.value = []; }
})
</script>

<style scoped>
.cmp-wb {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--gsc-bg-panel);
  border: 1px solid var(--gsc-border);
  padding: 8px;
  box-shadow: var(--gsc-shadow);
}
.wb-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  border-bottom: 1px solid var(--gsc-border);
  padding-bottom: 4px;
  margin-bottom: 8px;
}
.wb-head h2 {
  margin: 0;
  font-size: 13px;
}
.cmp-pane {
  margin-bottom: 8px;
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
  padding: 6px;
}
.pane-head {
  flex-shrink: 0;
  padding: 3px 8px;
  font-size: 11px;
  color: var(--gsc-text-muted);
  background: var(--gsc-bg-header);
  border-bottom: 1px solid var(--gsc-border);
  margin: -6px -6px 6px;
}
.pane-hint {
  font-size: 11px;
  color: var(--gsc-text-faint);
  margin-top: 4px;
}
.excl-sel {
  width: 100%;
}
.cmp-params {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.p-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.p-label {
  flex-shrink: 0;
  width: 60px;
  font-size: 12px;
  color: var(--gsc-text-muted);
  text-align: right;
}
.p-ctl {
  min-width: 0;
}
.run-btn {
  margin-left: auto;
}
.cmp-body {
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
  padding: 6px;
}
.res-sec {
  margin-bottom: 8px;
}
.res-summary {
  padding: 6px;
}
.chart-box {
  height: 240px;
}
.l2-cell {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 2px;
}
.pair-chart {
  margin-top: 8px;
}
.pair-box {
  height: 260px;
}
.pair-chart .pane-head {
  margin-bottom: 0;
}
</style>
