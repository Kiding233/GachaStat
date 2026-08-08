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
    </div>

    <!-- 结果 -->
    <div v-if="resultError" class="cmp-pane"><el-alert type="error" :closable="false" :title="resultError" /></div>
    <div v-if="sections.length" class="cmp-body">
      <template v-for="(sec, i) in sections" :key="i">
        <!-- table -->
        <div v-if="sec.key === 'table'" class="res-sec">
          <div class="pane-head">{{ sec.title }}</div>
          <el-table :data="tableRows(sec)" size="small" border max-height="300">
            <el-table-column v-for="h in sec.headers || []" :key="h" :label="h">
              <template #default="{ row }">{{ row[h] }}</template>
            </el-table-column>
          </el-table>
        </div>
        <!-- chart -->
        <div v-else-if="sec.key === 'chart'" class="res-sec">
          <div class="pane-head">{{ sec.title }}</div>
          <div :ref="setChartEl" class="chart-box" />
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import api from '../../api.js'
import { specToECharts } from './specToECharts.js'

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
const params = ref({ gdr: 'target_achievement', threshold: 1.0, method: 'MWU', correction: 'BH' })

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
  try {
    const ds = includedNodes.value.map((n) => n.meta.datasetId).filter(Boolean)
    const r = await api.runComparison(ds, { ...params.value })
    if (r?.ok) sections.value = r.sections || []
    else { resultError.value = r?.error || '比较分析失败' }
  } catch (e) {
    resultError.value = String(e)
  } finally {
    running.value = false
    await nextTick()
    renderChart()
  }
}

// chart 渲染（函数 ref）
const chartEl = ref(null)
let chart = null
function setChartEl(el) { chartEl.value = el }
function renderChart() {
  const c = sections.value.find((s) => s.key === 'chart')
  if (!c || !chartEl.value) return
  const opt = specToECharts(c.spec)
  if (!chart) {
    chart = echarts.init(chartEl.value)
    window.addEventListener('resize', onResize)
  }
  chart.setOption(opt, true)
}
function tableRows(sec) {
  return (sec.rows || []).map((r) => {
    const o = {}
    sec.headers.forEach((h, i) => { o[h] = r[i] })
    return o
  })
}
function onResize() { chart && chart.resize() }
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (chart) chart.dispose()
  chart = null
})
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
</style>
