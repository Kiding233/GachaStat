<template>
  <div class="wb">
    <div class="wb-head">
      <h2>数据集信息（{{ nodes.length }}）</h2>
      <span class="muted">勾选右侧数据集 → 左侧可比性检查；创建对比分析任务</span>
    </div>

    <div class="wb-body">
      <!-- 左：可比性检查（始终可见，勾选即刷新；对齐 Qt 数据管理页布局）-->
      <div class="left-pane cmp-pane">
        <div class="pane-head">可比性检查</div>
        <div class="sel-label">已选 {{ selectedRows.length }} 个数据集</div>
        <el-table :data="compareRows" size="small" class="cmp-table">
          <el-table-column prop="dim" label="维度" width="86" />
          <el-table-column label="状态" width="46" align="center">
            <template #default="{ row }">
              <span :class="row.status === '✓' ? 'ok' : 'warn'">{{ row.status }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="detail" label="详情" />
        </el-table>
        <div class="mode-hint">{{ modeHint }}</div>
        <el-button type="primary" size="small" class="cmp-btn" :disabled="selectedRows.length < 2" @click="$emit('create-compare', selectedRows)">
          创建对比分析任务（纳入 {{ selectedRows.length }} 个）
        </el-button>
      </div>

      <!-- 右：数据集表格（主内容，选择框驱动左侧可比性）-->
      <div class="right-pane ds-pane">
        <div class="pane-head">数据集</div>
        <el-table
          ref="tableRef"
          :data="tableRows"
          row-key="id"
          size="small"
          class="ds-table"
          @selection-change="onSelectionChange"
          @row-click="(row) => $emit('open', row)"
        >
          <el-table-column type="selection" width="36" />
          <el-table-column prop="label" label="名称" min-width="170" show-overflow-tooltip />
          <el-table-column label="来源配置" min-width="90">
            <template #default="{ row }"><span class="muted">{{ sourceLabel(row) }}</span></template>
          </el-table-column>
          <el-table-column label="策略" width="110">
            <template #default="{ row }">{{ row.meta.strategy ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="种子" width="65">
            <template #default="{ row }">{{ row.meta.seed ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="N" width="65">
            <template #default="{ row }">{{ row.meta.n ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="均值" width="65">
            <template #default="{ row }">{{ row.meta.meanDraws ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="时间" width="70">
            <template #default="{ row }">{{ row.meta.createdAt ?? '—' }}</template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  nodes: { type: Array, default: () => [] },     // 数据集节点数组（单选 1 / 多选 N）
  configs: { type: Array, default: () => [] },   // 全树配置列表（解析来源配置名）
  preselect: { type: Boolean, default: false },  // 树勾选进入（多选信息页）→ 表格默认全选
})
defineEmits(['create-compare', 'open'])

const tableRef = ref(null)
const selectedRows = ref([])
function onSelectionChange(rows) { selectedRows.value = rows }

// 表格数据 = 树节点的扁平副本（去掉 children）。
// 树节点带 children（如数据集下有统计分析子条目），el-table 检测到 children 字段会
// 自动进入 tree 模式 → 数据集行显示展开箭头、勾选父行递归选中子行（统计分析）→ 计数错误。
// 扁平化后数据集信息表只显示数据集本身，不展开任何子条目。
const tableRows = computed(() =>
  props.nodes.map((n) => ({ id: n.id, type: n.type, label: n.label, parent: n.parent, kind: n.kind, meta: n.meta })),
)

// 树里勾选的数据集 → 表格默认选中（勾选即代表想比较，无需二次勾选）。
// 用 watch 而非 onMounted：逐个勾选时 nodes 递增，onMounted 只跑一次，
// 第二次勾选的新数据集不会默认选中（表现为「选第二个时选中被取消」）。
watch(
  () => props.nodes.map((n) => n.id),
  () => {
    if (props.preselect && tableRows.value.length) {
      nextTick(() => {
        tableRows.value.forEach((row) => tableRef.value?.toggleRowSelection(row, true))
      })
    }
  },
  { immediate: true },
)

function sourceLabel(d) {
  const cfg = d.meta.sourceConfigId && props.configs.find((c) => c.id === d.meta.sourceConfigId)
  return cfg ? cfg.label : (d.meta.sourceConfigId || '—')
}

// 可比性：0 选提示 / 1 选单数据集元信息 / ≥2 差异矩阵（对齐 Qt 数据管理页）
const compareRows = computed(() => {
  const sel = selectedRows.value
  if (!sel.length) return []
  if (sel.length === 1) {
    const d = sel[0]
    return [
      { dim: '来源配置', status: '—', detail: sourceLabel(d) },
      { dim: '策略', status: '—', detail: d.meta.strategy || '—' },
      { dim: '种子', status: '—', detail: String(d.meta.seed ?? '—') },
      { dim: 'N', status: '—', detail: String(d.meta.n ?? '—') },
      { dim: '均值', status: '—', detail: String(d.meta.meanDraws ?? '—') },
    ]
  }
  const allSame = (getter) => new Set(sel.map(getter)).size === 1
  const rows = []
  const add = (dim, getter) => {
    const same = allSame(getter)
    rows.push({ dim, status: same ? '✓' : '⚠', detail: same ? '相同' : '各数据集不同' })
  }
  add('来源配置', (d) => d.meta.sourceConfigId)
  add('策略', (d) => d.meta.strategy)
  add('种子', (d) => d.meta.seed)
  add('N', (d) => d.meta.n)
  return rows
})
const modeHint = computed(() => {
  const n = selectedRows.value.length
  if (!n) return '选择数据集以查看可比性'
  if (n === 1) return '显示单个数据集元信息'
  return `${n} 个数据集，检查是否可比（配置 / 策略 / 种子 / N）`
})
</script>

<style scoped>
.wb {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
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
/* 左：可比性检查（固定宽，辅助面板）*/
.left-pane.cmp-pane {
  flex: 0 0 280px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
}
/* 右：数据集表格（主内容区）*/
.right-pane.ds-pane {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
}
.pane-head {
  flex-shrink: 0;
  padding: 3px 8px;
  font-size: 11px;
  color: var(--gsc-text-muted);
  background: var(--gsc-bg-header);
  border-bottom: 1px solid var(--gsc-border);
}
.sel-label {
  padding: 6px 8px;
  font-size: 12px;
  font-weight: 600;
  border-bottom: 1px dashed var(--gsc-border);
}
.cmp-table {
  margin: 6px 8px;
  flex: 0 0 auto;
}
.ds-table {
  width: 100%;
}
.ok {
  color: var(--el-color-success);
  font-weight: 700;
}
.warn {
  color: var(--el-color-warning);
  font-weight: 700;
}
.mode-hint {
  margin: 0 8px 6px;
  padding: 6px 8px;
  font-size: 11px;
  color: #b26a00;
  background: #fff9f0;
  border-left: 3px solid var(--el-color-warning);
  line-height: 1.5;
}
.cmp-btn {
  margin: 0 8px 8px;
  width: calc(100% - 16px);
}
</style>
