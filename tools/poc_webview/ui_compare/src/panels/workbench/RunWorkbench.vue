<template>
  <div class="run-wb">
    <!-- 顶部：运行对象 + 新建任务（参数经对话框设置，队列页干净）-->
    <div class="run-top">
      <span class="run-top-label">运行对象</span>
      <span class="run-top-target">{{ targetLabel }}</span>
      <el-button type="primary" size="small" class="new-task-btn" @click="openDialog">新建任务</el-button>
    </div>

    <div class="run-main">
      <!-- 左：任务队列（主区）-->
      <div class="run-queue">
        <div class="pane-head">任务队列（{{ taskQueue.length }}）</div>
        <el-table :data="taskQueue" size="small" class="task-table">
          <el-table-column prop="name" label="任务" min-width="160" show-overflow-tooltip />
          <el-table-column label="类型" width="70">
            <template #default="{ row }"><span class="muted">{{ row.type === 'search' ? '搜索' : '模拟' }}</span></template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.status === 'done'" size="small" type="success">完成</el-tag>
              <el-tag v-else-if="row.status === 'failed'" size="small" type="danger">失败</el-tag>
              <el-tag v-else-if="row.status === 'running'" size="small">运行中</el-tag>
              <el-tag v-else size="small" type="info">排队</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" width="130">
            <template #default="{ row }">
              <el-progress :percentage="row.progress" :stroke-width="8" />
            </template>
          </el-table-column>
          <el-table-column prop="elapsed" label="耗时(s)" width="70" />
          <el-table-column label="操作" width="110">
            <template #default="{ row }">
              <el-button size="small" text type="danger" :disabled="row.status === 'done' || row.status === 'failed'" @click="$emit('cancel-task', row)">取消</el-button>
              <el-button v-if="row.status === 'done'" size="small" text @click="$emit('view-result', row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!taskQueue.length" :image-size="40" description="暂无任务：点击上方「新建任务」派发" />
      </div>

      <!-- 右：资源监控（js_api psutil 每 2 秒刷新）-->
      <div class="run-res">
        <div class="pane-head">资源监控</div>
        <div class="res-body">
          <div class="res-card">
            <div class="res-title">CPU</div>
            <el-progress :percentage="cpu" :stroke-width="10" />
          </div>
          <div class="res-card">
            <div class="res-title">内存</div>
            <el-progress :percentage="mem" :stroke-width="10" />
          </div>
          <div class="res-card">
            <div class="res-title">并行 worker</div>
            <div class="worker-line"><span class="muted">由模拟任务参数决定</span></div>
          </div>
          <div class="res-note">资源数据经 js_api（psutil）采集，每 2 秒刷新。CPU/内存为空表示 psutil 未安装。</div>
        </div>
      </div>
    </div>

    <!-- 新建任务对话框：选运行对象 + 参数 + 派发 -->
    <el-dialog v-model="dialogVisible" title="新建任务" width="440" append-to-body>
      <div class="dlg-row">
        <span class="p-label">运行对象</span>
        <el-select v-model="dialogTarget" size="small" class="dlg-sel" placeholder="选择配置或搜索任务">
          <el-option-group v-if="configs.length" label="配置">
            <el-option v-for="c in configs" :key="c.id" :label="c.label" :value="c.id" />
          </el-option-group>
          <el-option-group v-if="searches.length" label="搜索任务">
            <el-option v-for="s in searches" :key="s.id" :label="s.label" :value="s.id" />
          </el-option-group>
        </el-select>
      </div>
      <div class="dlg-params">
        <RunParamForm :op="dialogOp" :params="dialogParams" />
      </div>
      <template #footer>
        <el-button size="small" @click="dialogVisible = false">取消</el-button>
        <el-button size="small" type="primary" :disabled="!dialogTarget" @click="confirmDialog">派发任务</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import RunParamForm from './RunParamForm.vue'
import api from '../../api.js'

const props = defineProps({
  target: { type: Object, default: () => ({ kind: 'none', node: null }) },
  taskQueue: { type: Array, default: () => [] },
  configs: { type: Array, default: () => [] },     // 配置/派生配置（对话框运行对象选项）
  searches: { type: Array, default: () => [] },    // 搜索任务
})
const emit = defineEmits(['create-task', 'cancel-task', 'view-result'])

const targetLabel = computed(() => {
  if (props.target.kind === 'sim') return `模拟 · ${props.target.node?.label || '（未选）'}`
  if (props.target.kind === 'search') return `搜索 · ${props.target.node?.label || '（未选）'}`
  return '—'
})

// ── 新建任务对话框 ──
const dialogVisible = ref(false)
const dialogTarget = ref(null)      // 运行对象 id（字符串；对象 value 因 === 比较无法稳定选中）
const dialogOp = computed(() => {
  const id = dialogTarget.value
  if (!id) return 'sim'
  return props.searches.some((s) => s.id === id) ? 'search' : 'sim'
})
const defaultParams = (op) => (
  op === 'search'
    ? { goal: 'min_resource', budget: 5000, strategy: 'smart', n: 1000, seed: 42, gdr_key: 'all_targets', success_threshold: 0.95 }
    : { n: 1000, seed: 42, w: 4 }
)
const dialogParams = ref(defaultParams('sim'))

function openDialog() {
  // 预设当前选中运行对象（若有效）
  dialogTarget.value = (props.target.kind === 'sim' || props.target.kind === 'search')
    ? props.target.node.id
    : null
  dialogParams.value = defaultParams(dialogOp.value)
  dialogVisible.value = true
}
watch(dialogTarget, () => { dialogParams.value = defaultParams(dialogOp.value) })

function confirmDialog() {
  if (!dialogTarget.value) return
  emit('create-task', {
    type: dialogOp.value,
    targetId: dialogTarget.value,
    params: { ...dialogParams.value },
  })
  dialogVisible.value = false
}

// 资源监控：经 js_api psutil 定时刷新（真实）
const cpu = ref(null)
const mem = ref(null)
const workers = ref(null)
let resTimer = null
async function refreshResource() {
  const r = await api.getResourceUsage()
  if (r?.ok) {
    if (r.cpu != null) cpu.value = r.cpu
    if (r.mem != null) mem.value = r.mem
  }
}
onMounted(() => {
  refreshResource()
  resTimer = setInterval(refreshResource, 2000)
})
onBeforeUnmount(() => { if (resTimer) clearInterval(resTimer) })

// 供 App 从工具栏「创建模拟任务」触发：跳转任务页后自动打开新建任务对话框（预选当前运行对象）
defineExpose({ openNewTask: openDialog })
</script>

<style scoped>
.run-wb {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.run-top {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid var(--gsc-border);
  background: var(--gsc-bg-header);
}
.run-top-label {
  font-size: 11px;
  color: var(--gsc-text-muted);
}
.run-top-target {
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.new-task-btn {
  margin-left: auto;
}
.run-main {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 8px;
}
.run-queue {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--gsc-border);
  background: var(--gsc-bg-result);
}
.task-table {
  width: 100%;
}
.run-res {
  flex: 0 0 220px;
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
.res-body {
  flex: 1;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.res-card {
  border: 1px solid var(--gsc-border);
  background: var(--gsc-bg-panel);
  padding: 8px;
}
.res-title {
  font-size: 11px;
  color: var(--gsc-text-muted);
  margin-bottom: 4px;
}
.worker-line {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.res-note {
  margin-top: auto;
  font-size: 11px;
  color: var(--gsc-text-faint);
  line-height: 1.5;
}
.dlg-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.p-label {
  flex-shrink: 0;
  width: 64px;
  font-size: 12px;
  color: var(--gsc-text-muted);
  text-align: right;
}
.dlg-sel {
  flex: 1;
  min-width: 0;
}
.dlg-params {
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
}
</style>
