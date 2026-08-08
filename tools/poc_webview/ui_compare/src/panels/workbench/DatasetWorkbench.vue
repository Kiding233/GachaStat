<template>
  <div class="wb">
    <div class="wb-head">
      <h2>{{ headTitle }}</h2>
      <span class="muted">来源配置 {{ node.parent }} · N={{ node.meta?.n ?? '—' }} · 种子 {{ node.meta?.seed ?? '—' }}</span>
    </div>

    <!-- 添加分析方法：层级化（第一行分类，点击选中 → 第二行显示该分类的方法按钮）-->
    <div class="method-toolbar">
      <div class="cat-row">
        <span class="toolbar-label">添加方法</span>
        <el-button
          v-for="cat in METHOD_CATEGORIES"
          :key="cat"
          size="small"
          :type="activeCat === cat ? 'primary' : 'default'"
          @click="activeCat = cat"
        >{{ cat }}</el-button>
      </div>
      <div v-if="methodsByCategory(activeCat).length" class="method-row">
        <el-button
          v-for="m in methodsByCategory(activeCat)"
          :key="m.type"
          size="small"
          @click="addMethod(m.type)"
        >{{ m.label }}</el-button>
      </div>
    </div>

    <div v-if="blocks.length" class="wb-body">
      <!-- 左栏：方法单元（参数，拖拽 ⠿ 重排）-->
      <aside class="left-col">
        <draggable :list="blocks" item-key="uid" :animation="150" class="left-col-inner">
          <template #item="{ element }">
            <div class="param-item" :class="{ active: element.uid === activeUid }">
              <div class="param-head" @click="toggle(element.uid)">
                <span class="drag-handle" @click.stop title="拖拽排序">⠿</span>
                <span class="arrow">{{ element.expanded ? '▾' : '▸' }}</span>
                <span class="param-title">{{ element.label }}</span>
                <span v-if="element.status === 'running'" class="status-badge running">运行中</span>
                <el-button size="small" text type="danger" class="remove-btn" @click.stop="removeBlock(element.uid)">×</el-button>
              </div>
              <div v-show="element.expanded" class="param-body">
                <ParamControls
                  :type="element.type"
                  :params="element.params"
                  :configs="configs"
                  @action="(a) => onAction(element, a)"
                />
              </div>
            </div>
          </template>
        </draggable>
      </aside>

      <!-- 右栏：结果按顺序堆叠（每方法独立结果区框架）-->
      <main class="right-col">
        <div
          v-for="b in blocks"
          :key="b.uid"
          class="result-item"
          :class="{ active: b.uid === activeUid }"
          @click="focusBlock(b.uid)"
        >
          <div class="result-head">{{ b.label }}</div>
          <ResultChart
            :type="b.type"
            :sections="b.result?.sections || []"
            :loading="b.status === 'running'"
            :error="b.result?.error || ''"
          />
        </div>
      </main>
    </div>
    <el-empty v-else :image-size="50" description="点击上方「添加方法」创建分析单元（可重复，各配参数）" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import draggable from 'vuedraggable'
import { METHOD_CATEGORIES, methodsByCategory, methodByType, applyGdrOptions } from './methodDefs.js'
import ParamControls from './ParamControls.vue'
import ResultChart from './ResultChart.vue'
import api from '../../api.js'

const props = defineProps({
  node: { type: Object, required: true },              // 数据集节点（父）
  analysisNode: { type: Object, default: null },       // 统计分析条目节点
  configs: { type: Array, default: () => [] },         // 工作区配置列表
})
const emit = defineEmits(['create-derived'])
const headTitle = computed(() => (props.analysisNode ? `统计分析 · ${props.node.label}` : `数据集：${props.node.label}`))
// 后端数据集 id（模拟任务完成时 register_dataset 的返回）
const datasetId = computed(() => props.node?.meta?.datasetId || '')

// 方法单元：点击创建，允许重复，每个独立参数
let nextUid = 1
const localBlocks = ref([])
const blocks = ref([])
if (props.analysisNode) {
  if (!Array.isArray(props.analysisNode.meta.blocks)) props.analysisNode.meta.blocks = []
  blocks.value = props.analysisNode.meta.blocks
} else {
  blocks.value = localBlocks.value
}
const activeUid = ref(null)
const activeCat = ref(METHOD_CATEGORIES[0])

// 启动时注入动态 GDR 选项：资源类 GDR（resource_remaining 等）按资源种类展开为 :qualified
// 条目（draw_resource/exchange_currency…），并在 GDR 下拉可选（与后端 get_expanded_gdr_entries 一致）。
onMounted(async () => {
  const g = await api.listGdrOptions()
  if (g?.ok && g.options?.length) applyGdrOptions(g.options)
})

function defaultParams(type) {
  const def = methodByType(type)
  const p = {}
  for (const f of def.params) p[f.key] = f.default
  if (type === 'worst_config') p.distribution = []
  if (type === 'worst_dist') p.poolConfig = ''
  return reactive(p)
}

function addMethod(type) {
  const m = methodByType(type)
  if (!m) return
  const uid = nextUid++
  const block = reactive({
    uid, type, label: m.label, expanded: true,
    params: defaultParams(type), status: 'idle', result: null,
    _seq: 0, _timer: null, _pending: false,
  })
  // 参数变化 → 防抖自动重跑（高频调整时合并，运行中标记 pending 完成后跑最新）
  watch(block.params, () => scheduleRun(block), { deep: true })
  blocks.value.push(block)
  activeUid.value = uid
  // 创建后自动运行（仅分析类；worst_config 等纯生成类等用户点「生成」）
  if (!isGenerateOnly(type)) runAnalysis(block)
}

// 纯生成类方法块（无自动分析，等用户显式生成配置）
function isGenerateOnly(type) {
  const m = methodByType(type)
  return m?.action === 'generate_config'
}

// ── 自动运行（防抖 + 运行中 pending + 过期响应丢弃）──
// 统计方法创建即运行；参数变化防抖重跑。长任务高频调参场景：
// 参数快速变化 → 防抖合并；运行中参数再变 → 置 pending，当前完成后自动跑最新；旧响应经 seq 丢弃。
const DEBOUNCE_MS = 600
function scheduleRun(block) {
  clearTimeout(block._timer)
  block._timer = setTimeout(() => {
    if (block.status === 'running') { block._pending = true; return }
    runAnalysis(block)
  }, DEBOUNCE_MS)
}

async function runAnalysis(block) {
  const route = ANALYSIS_API[block.type]
  if (!route) return
  const seq = (block._seq || 0) + 1
  block._seq = seq
  block.status = 'running'
  block.result = null
  try {
    const res = route === 'runAnalysis'
      ? await api.runAnalysis(datasetId.value, block.type, { ...block.params })
      : route === 'runProcessAnalysis'
        ? await api.runProcessAnalysis(datasetId.value, { ...block.params })
        : route === 'runVulnerability'
          ? await api.runVulnerability(datasetId.value, { ...block.params })
          : await api.analyzeWorstDist(datasetId.value, { ...block.params })
    if (seq !== block._seq) return   // 过期响应（参数已再次变化）→ 丢弃
    block.result = res
    block.status = 'done'
    if (block._pending) { block._pending = false; block._timer = setTimeout(() => runAnalysis(block), 100) }
  } catch (e) {
    if (seq !== block._seq) return
    block.result = { ok: false, sections: [], error: String(e) }
    block.status = 'error'
  }
}
// 方法 → 后端调用路由
const ANALYSIS_API = {
  gdr_dist: 'runAnalysis', gdr_statistics: 'runAnalysis', correlation: 'runAnalysis',
  success_rate: 'runAnalysis', risk_var_cvar: 'runAnalysis', risk_worst_case: 'runAnalysis',
  risk_best_case: 'runAnalysis', conditional_dist: 'runAnalysis', time_series: 'runAnalysis',
  time_heatmap: 'runAnalysis', draws_vs_gdr: 'runAnalysis', per_pool_draws: 'runAnalysis',
  per_pool_target_rate: 'runAnalysis', per_pool_pity_rate: 'runAnalysis',
  cumulative_by_pool: 'runAnalysis', transition_analysis: 'runAnalysis',
  waterfall_3d: 'runAnalysis', waterfall_2d: 'runAnalysis',
  process: 'runProcessAnalysis', vuln: 'runVulnerability', worst_dist: 'analyzeWorstDist',
}

// 生成配置 → 真在工作区创建派生配置节点（挂源配置下，带真实 config_text）
async function generateConfig(block, action) {
  if (action === 'generate_config' && block.type === 'vuln') {
    // 脆弱性：按原方案搜索方法——从脆弱区间选初始状态（from_pool + 资源分位 + 保底水位）
    const opts = block.result?.config_options || {}
    const poolId = block.params.from_pool
    if (!poolId || poolId === '_root') {
      import('element-plus').then(({ ElMessage }) => ElMessage.warning('请先选择起始池（脆弱性分析产生的脆弱区间池）'))
      return
    }
    const poolOpt = (opts.from_pools || []).find((p) => p.pool_id === poolId)
    if (!poolOpt) {
      import('element-plus').then(({ ElMessage }) => ElMessage.warning('所选起始池不在脆弱性结果中，请先运行分析'))
      return
    }
    const baseResource = resolveBaseResource(block.params, poolOpt)
    const res = await api.generateRetreatConfig({
      from_pool: poolId,
      base_resource: baseResource,
      base_custom: block.params.base_custom,
      pity_state: block.params.pity_state,
      pity_stats: poolOpt.pity_stats || {},
    })
    if (res?.ok && res.config_text) {
      emit('create-derived', {
        sourceConfigId: props.node?.meta?.sourceConfigId || null,
        configText: res.config_text,
        label: `脆弱性调整配置（${poolId}）`,
        note: '脆弱性分析·生成调整配置',
      })
    } else {
      import('element-plus').then(({ ElMessage }) => ElMessage.error(res?.error || '生成失败'))
    }
  } else if (block.type === 'worst_config') {
    const res = await api.generateWorstConfig(datasetId.value, { ...block.params })
    if (res?.ok && res.config_text) {
      emit('create-derived', {
        sourceConfigId: props.node?.meta?.sourceConfigId || null,
        configText: res.config_text,
        label: '后续池子配置（最差影响）',
        note: `最差影响分析·最差资源 ${res.worst_resource?.toFixed(0) ?? '—'}`,
      })
    } else {
      import('element-plus').then(({ ElMessage }) => ElMessage.error(res?.error || '生成失败'))
    }
  }
}

// 资源预设解析（对齐原方案搜索 _get_selected_resource）：
// VI 三档 / 分位数 / 自定义 → 具体数值（从脆弱性分析 config_options 取）
function resolveBaseResource(params, poolOpt) {
  const mode = params.base_resource
  if (mode === 'custom') {
    const v = parseFloat(params.base_custom)
    return isNaN(v) ? 0 : v
  }
  if (mode === 'mean') return poolOpt.resource_mean ?? poolOpt.vi_mean ?? 0
  if (mode === 'p25') return poolOpt.percentiles?.p25 ?? 0
  if (mode === 'p75') return poolOpt.percentiles?.p75 ?? 0
  if (mode === 'p50') return poolOpt.percentiles?.p50 ?? 0
  return 0
}

function onAction(block, action) {
  if (action === 'generate_config') { generateConfig(block, action); return }
  runAnalysis(block)
}

function toggle(uid) {
  const b = blocks.value.find((x) => x.uid === uid)
  if (b) b.expanded = !b.expanded
  activeUid.value = uid
}
function focusBlock(uid) {
  activeUid.value = uid
  const b = blocks.value.find((x) => x.uid === uid)
  if (b) b.expanded = true
}
function removeBlock(uid) {
  const idx = blocks.value.findIndex((b) => b.uid === uid)
  if (idx >= 0) blocks.value.splice(idx, 1)
  if (activeUid.value === uid) activeUid.value = null
}
</script>

<style scoped>
.method-toolbar {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px;
  margin-bottom: 8px;
  border: 1px solid var(--gsc-border);
  background: var(--gsc-bg-header);
}
.cat-row {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  padding: 3px 6px;
  background: #e8edf3;
  border-left: 3px solid var(--gsc-text-faint);
}
.cat-row:has(.el-button--primary) {
  border-left-color: var(--el-color-primary);
}
.cat-row .el-button, .method-row .el-button {
  height: 20px;
  padding: 0 8px;
  font-size: 12px;
}
.method-row {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  padding: 4px 6px;
  margin-left: 8px;
  background: #fafbfc;
  border: 1px solid var(--gsc-border);
}
.toolbar-label {
  font-size: 11px;
  color: var(--gsc-text-muted);
  margin-right: 4px;
  flex-shrink: 0;
}
.wb {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--gsc-bg-panel);
  border: 1px solid var(--gsc-border);
  padding: 8px;
  box-shadow: var(--gsc-shadow);
}
.wb-head {
  flex-shrink: 0;
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
.wb-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 8px;
}
.left-col {
  flex: 0 0 260px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.left-col-inner {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.drag-handle {
  cursor: move;
  color: var(--gsc-text-faint);
  font-size: 12px;
  user-select: none;
}
.param-item {
  border: 1px solid var(--gsc-border);
  background: var(--gsc-bg-panel);
}
.param-item.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-8);
}
.param-head {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  cursor: pointer;
  user-select: none;
  font-size: 12px;
}
.param-head:hover {
  background: var(--gsc-bg-header);
}
.arrow {
  font-size: 11px;
  color: var(--gsc-text-muted);
  width: 14px;
  text-align: center;
}
.param-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 2px;
  flex-shrink: 0;
}
.status-badge.running {
  background: #e3f2fd;
  color: var(--el-color-primary);
}
.remove-btn {
  padding: 0 4px;
}
.param-body {
  border-top: 1px solid var(--gsc-border);
}
.right-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
}
.result-item {
  border: 1px solid var(--gsc-border);
  background: var(--gsc-bg-panel);
  cursor: pointer;
}
.result-item.active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px var(--el-color-primary-light-8);
}
.result-head {
  padding: 4px 8px;
  border-bottom: 1px solid var(--gsc-border);
  font-size: 12px;
  font-weight: 600;
}
</style>
