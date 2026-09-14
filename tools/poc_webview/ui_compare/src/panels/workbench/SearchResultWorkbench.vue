<template>
  <div class="wb">
    <div class="wb-head">
      <h2>搜索结果：{{ node.label }}</h2>
      <span class="muted">从属 {{ parentLabel }}</span>
    </div>

    <!-- 搜索摘要 -->
    <div class="wb-section">
      <h3>搜索摘要</h3>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="模式">{{ modeLabel }}</el-descriptions-item>
        <el-descriptions-item label="起始池">{{ node.meta.result?.from_pool_id || '从头开始' }}</el-descriptions-item>
        <el-descriptions-item label="成功率">{{ successRate }}</el-descriptions-item>
        <el-descriptions-item label="迭代次数">{{ node.meta.result?.total_iterations ?? '—' }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 最少资源：二分步骤表 -->
    <div v-if="node.meta.result?.search_mode === 'min_resource'" class="wb-section">
      <h3>最少资源结果：{{ node.meta.result.min_resource ?? '—' }}</h3>
      <el-table :data="binarySteps" size="small" border max-height="260">
        <el-table-column prop="iteration" label="迭代" width="60" />
        <el-table-column prop="phase" label="阶段" width="80" />
        <el-table-column prop="resource_value" label="资源值" width="110" />
        <el-table-column label="成功率" width="100">
          <template #default="{ row }">{{ fmtPct(row.success_probability) }}</template>
        </el-table-column>
        <el-table-column prop="lo_bound" label="下界" width="100" />
        <el-table-column prop="hi_bound" label="上界" width="100" />
      </el-table>
    </div>

    <!-- 最多目标卡 / Pareto：点表 -->
    <div v-if="points.length" class="wb-section">
      <h3>搜索点（{{ points.length }}）</h3>
      <el-table :data="points" size="small" border max-height="260">
        <el-table-column label="#" width="50">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="额外资源" width="110">
          <template #default="{ row }">{{ fmtNum(row.extra_resource) }}</template>
        </el-table-column>
        <el-table-column label="成功率" width="110">
          <template #default="{ row }">{{ fmtPct(row.success_probability) }}</template>
        </el-table-column>
        <el-table-column prop="target_specs" label="目标卡集合" show-overflow-tooltip />
      </el-table>
    </div>

    <el-empty v-if="!node.meta.result" :image-size="40" description="本搜索结果暂无数据（搜索任务未运行）" />

    <div class="wb-actions">
      <el-button size="small" @click="$emit('convert-config', node)" type="primary">转化为配置</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ node: { type: Object, required: true } })
defineEmits(['convert-config'])
const parentLabel = computed(() => props.node.meta.searchGroupLabel || props.node.parent || '—')
const MODE_LABELS = { min_resource: '最少资源', max_target: '最多目标卡', forward: '前进法', pareto: 'Pareto 前沿' }
const modeLabel = computed(() => MODE_LABELS[props.node.meta.result?.search_mode] || props.node.meta.result?.search_mode || '—')
const successRate = computed(() => {
  const v = props.node.meta.result?.final_success_probability
  return v != null ? (v * 100).toFixed(1) + '%' : '—'
})
const binarySteps = computed(() => (props.node.meta.result?.binary_steps || []).map((s) => ({ ...s })))
const points = computed(() => {
  const r = props.node.meta.result
  if (!r) return []
  if (r.pareto_points?.length) return r.pareto_points
  if (r.points?.length) return r.points
  return []
})
function fmtNum(v) {
  return v == null ? '—' : (Math.round(v * 100) / 100).toString()
}
function fmtPct(v) {
  return v == null ? '—' : (v * 100).toFixed(2) + '%'   // 对齐旧 plan_search_panel .2%
}
</script>

<style scoped>
.wb {
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
.wb-section {
  margin-bottom: 8px;
}
.wb-section h3 {
  margin: 0 0 4px 0;
  font-size: 12px;
  color: var(--gsc-text-muted);
}
.wb-actions {
  display: flex;
  gap: 8px;
}
</style>
