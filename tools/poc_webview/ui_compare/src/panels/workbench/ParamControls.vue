<template>
  <div class="param-controls">
    <!-- 数据驱动：按 methodDefs 的 params 描述渲染 -->
    <div v-for="f in def.params" :key="f.key" class="p-row">
      <span class="p-label">{{ f.label }}</span>
      <el-select v-if="f.type === 'select'" v-model="params[f.key]" size="small" class="p-ctl">
        <el-option v-for="opt in f.options" :key="opt[0]" :label="opt[1]" :value="opt[0]" />
      </el-select>
      <el-input-number
        v-else-if="f.type === 'number'"
        v-model="params[f.key]"
        size="small"
        :min="f.min ?? 0"
        :max="f.max"
        :step="f.step ?? 1"
        :precision="f.precision"
        class="p-ctl p-num"
      />
      <el-switch v-else-if="f.type === 'bool'" v-model="params[f.key]" size="small" />
      <el-input v-else-if="f.type === 'text'" v-model="params[f.key]" size="small" class="p-ctl" />
      <el-select
        v-else-if="f.type === 'array'"
        v-model="params[f.key]"
        size="small"
        multiple
        filterable
        allow-create
        default-first-option
        class="p-ctl"
      >
        <el-option label="保底" value="pity" />
        <el-option label="提前出货" value="early" />
        <el-option label="miss" value="miss" />
      </el-select>
    </div>

    <!-- 最差影响 · 生成后续池子配置：卡牌分布编辑器（特化子块）-->
    <div v-if="type === 'worst_config'" class="dist-editor">
      <div class="p-label dist-title">卡牌分布</div>
      <el-table :data="params.distribution" size="small">
        <el-table-column label="卡ID" min-width="110">
          <template #default="{ row }"><el-input v-model="row.card_id" size="small" /></template>
        </el-table-column>
        <el-table-column label="概率(%)" width="90">
          <template #default="{ row }">
            <el-input-number v-model="row.probability" size="small" :precision="2" :controls="false" style="width: 70px" />
          </template>
        </el-table-column>
        <el-table-column label="稀有度" width="80">
          <template #default="{ row }">
            <el-select v-model="row.rarity" size="small">
              <el-option label="ssr" value="ssr" />
              <el-option label="sr" value="sr" />
              <el-option label="r" value="r" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="Featured" width="70">
          <template #default="{ row }"><el-checkbox v-model="row.featured" /></template>
        </el-table-column>
        <el-table-column width="50" align="center">
          <template #default="{ row }">
            <el-button size="small" text type="danger" @click="params.distribution.splice(params.distribution.indexOf(row), 1)">×</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-button size="small" class="dist-add" @click="params.distribution.push({ card_id: '', probability: 0, rarity: 'ssr', featured: false })">
        + 添加卡
      </el-button>
    </div>

    <!-- 最差影响 · 新池子数分布：后续池子配置来源（从工作区选「生成后续池子配置」产出的 config）-->
    <div v-if="type === 'worst_dist'" class="p-row">
      <span class="p-label">后续池子配置</span>
      <el-select v-model="params.poolConfig" size="small" class="p-ctl">
        <el-option v-if="!configs.length" label="（先在工作区运行「生成后续池子配置」，再从其中选择）" value="" />
        <el-option v-for="c in configs" :key="c.id" :label="c.label" :value="c.id" />
      </el-select>
    </div>

    <!-- 动作按钮：仅显式生成类动作（生成后续池子配置等）。统计方法自动运行（无运行按钮）-->
    <div v-if="hasManualActions" class="p-action">
      <el-button
        v-for="a in manualActions"
        :key="a.key"
        type="primary"
        size="small"
        @click="$emit('action', a.key)"
      >{{ a.label }}</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { methodByType } from './methodDefs.js'

const props = defineProps({
  type: { type: String, required: true },
  params: { type: Object, required: true },
  configs: { type: Array, default: () => [] },   // 已生成的后续池子配置（worst_dist 选择来源）
  // 块级下拉选项覆盖（如脆弱性 from_pool 动态填充真实脆弱区间池）——按参数 key 合并
  extraOptions: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['action'])

const def = computed(() => {
  const d = methodByType(props.type) || { params: [] }
  // 浅拷贝 params 并合并块级选项覆盖（不污染全局 METHOD_DEFS 单例）
  const params = d.params.map((f) => {
    if (props.extraOptions[f.key]) return { ...f, options: props.extraOptions[f.key] }
    return f
  })
  return { ...d, params }
})
// 仅显式生成类动作（统计方法自动运行；run_analysis 由方法块自动触发，不渲染按钮）
const manualActions = computed(() => (def.value.actions || []).filter((a) => a.key !== 'run_analysis'))
const hasManualActions = computed(() => def.value.action === 'generate_config' || manualActions.value.length > 0)
</script>

<style scoped>
.param-controls {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px;
}
.p-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.p-label {
  flex-shrink: 0;
  width: 72px;
  font-size: 12px;
  color: var(--gsc-text-muted);
  text-align: right;
}
.p-ctl {
  flex: 1;
  min-width: 0;
}
.p-num {
  width: 120px;
}
.dist-editor {
  margin-top: 4px;
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
  padding: 6px;
}
.dist-title {
  margin-bottom: 4px;
}
.dist-add {
  margin-top: 6px;
}
.p-action {
  margin-top: 4px;
  padding-top: 6px;
  border-top: 1px dashed var(--gsc-border);
}
</style>
