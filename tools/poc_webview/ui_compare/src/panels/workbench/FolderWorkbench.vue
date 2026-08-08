<template>
  <div class="wb">
    <div class="wb-head">
      <h2>{{ headTitle }}</h2>
      <span class="muted">{{ node.children?.length || 0 }} 个子条目</span>
    </div>

    <!-- 运行中锁定横幅：group 搜索运行中，内容只读 -->
    <el-alert
      v-if="node.status === 'running' || node.status === 'locked'"
      type="warning"
      :closable="false"
      title="运行中，内容只读"
      :description="node.status === 'running' ? '搜索运行中，可查看当前内容，完成前不可编辑/运行' : '所属搜索运行中，锁定'"
      style="margin-bottom: 8px"
    />

    <!-- 子条目列表（只读）：类型色点 + 名称 + 状态徽标 -->
    <div v-for="c in node.children || []" :key="c.id" class="folder-item" @click="$emit('open-node', c)">
      <span v-if="c.kind === 'folder'" class="folder-ico">📁</span>
      <span v-else class="type-mark" :style="{ background: typeColor(c.type) }" />
      <span class="item-label">{{ c.label }}</span>
      <span class="item-type">{{ typeLabel(c.type) }}</span>
      <span v-if="c.status === 'running'" class="status-badge running">运行中</span>
      <span v-else-if="c.status === 'locked'" class="status-badge locked">锁定</span>
    </div>
    <el-empty v-if="!node.children?.length" :image-size="40" description="空文件夹" />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  node: { type: Object, required: true },
})
defineEmits(['open-node'])

const headTitle = computed(() => `${props.node.type === 'group' ? '配置与数据组' : '文件夹'}：${props.node.label}`)

const TYPE_LABEL = {
  config: '配置', derived: '派生配置', dataset: '数据集', analysis: '统计分析',
  search: '搜索任务', group: '文件夹', search_result: '搜索结果', compare_task: '对比分析',
  user_folder: '文件夹',
}
const TYPE_COLOR = {
  config: '#1976d2', derived: '#f5a623', dataset: '#2e7d32', analysis: '#00897b',
  search: '#5c6bc0', group: '#9aa5b1', search_result: '#455a64', compare_task: '#7b1fa2',
  user_folder: '#9aa5b1',
}
const typeLabel = (t) => TYPE_LABEL[t] || t
const typeColor = (t) => TYPE_COLOR[t] || '#9aa5b1'
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
.folder-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
  margin-bottom: 4px;
  cursor: pointer;
  font-size: 12px;
}
.folder-item:hover {
  background: var(--gsc-bg-result);
}
.folder-ico {
  flex-shrink: 0;
  font-size: 12px;
}
.type-mark {
  width: 5px;
  height: 5px;
  flex-shrink: 0;
}
.item-label {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-type {
  margin-left: auto;
  font-size: 11px;
  color: var(--gsc-text-muted);
  flex-shrink: 0;
}
.status-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 2px;
}
.status-badge.running {
  background: #e3f2fd;
  color: var(--el-color-primary);
}
.status-badge.locked {
  background: #eceff1;
  color: var(--gsc-text-muted);
}
</style>
