<template>
  <div class="run-params">
    <!-- 生成型参数区：sim（模拟）/ search（搜索）/ sens（敏感性）三套，供运行页与搜索配置复用 -->
    <template v-if="op === 'sim'">
      <div class="p-row"><span class="p-label">模拟次数</span><el-input-number v-model="params.n" size="small" :min="100" :max="100000" :step="100" /></div>
      <div class="p-row"><span class="p-label">种子</span><el-input-number v-model="params.seed" size="small" :min="0" /></div>
      <div class="p-row"><span class="p-label">并行数</span><el-input-number v-model="params.w" size="small" :min="1" :max="16" /></div>
    </template>

    <template v-else-if="op === 'search'">
      <div class="p-row">
        <span class="p-label">搜索目标</span>
        <el-select v-model="params.goal" size="small" class="p-sel">
          <el-option label="最少资源" value="min_resource" />
          <el-option label="最多目标卡" value="max_target" />
          <el-option label="Pareto" value="pareto" />
        </el-select>
      </div>
      <div class="p-row"><span class="p-label">起始资源</span><el-input-number v-model="params.budget" size="small" :min="0" :step="100" /></div>
      <div class="p-row">
        <span class="p-label">GDR 指标</span>
        <el-select v-model="params.gdr_key" size="small" class="p-sel">
          <el-option v-for="g in gdrOptions" :key="g.key" :label="g.display" :value="g.key" />
        </el-select>
      </div>
      <div class="p-row">
        <span class="p-label">成功率阈值</span>
        <el-input-number v-model="params.success_threshold" size="small" :min="0" :max="1" :step="0.01" :precision="2" />
      </div>
      <div class="p-row">
        <span class="p-label">策略</span>
        <el-select v-model="params.strategy" size="small" class="p-sel" allow-create filterable>
          <el-option v-for="k in strategyKeys" :key="k" :label="k" :value="k" />
        </el-select>
      </div>
      <div class="p-row"><span class="p-label">模拟次数</span><el-input-number v-model="params.n" size="small" :min="50" :max="100000" :step="100" /></div>
      <div class="p-row"><span class="p-label">种子</span><el-input-number v-model="params.seed" size="small" :min="0" /></div>
    </template>

    <template v-else>
      <div class="p-row">
        <span class="p-label">扫描参数</span>
        <el-select v-model="params.param" size="small" class="p-sel" allow-create filterable>
          <el-option label="max_draws" value="max_draws" />
          <el-option label="start_day" value="start_day" />
          <el-option label="end_day" value="end_day" />
        </el-select>
      </div>
      <div class="p-row"><span class="p-label">最小值</span><el-input-number v-model="params.min" size="small" /></div>
      <div class="p-row"><span class="p-label">最大值</span><el-input-number v-model="params.max" size="small" /></div>
      <div class="p-row"><span class="p-label">步长</span><el-input-number v-model="params.step" size="small" :min="1" /></div>
      <div class="p-row">
        <span class="p-label">目标指标</span>
        <el-select v-model="params.metric" size="small" class="p-sel">
          <el-option label="目标达成率" value="target_achievement" />
          <el-option label="平均出率" value="mean_gdr" />
          <el-option label="期望消耗" value="expected_cost" />
        </el-select>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../../api.js'
// 生成型参数区：纯展示，v-model 直接写 props.params（由父组件持有响应式对象）
defineProps({
  op: { type: String, required: true },
  params: { type: Object, required: true },
})

const strategyKeys = ['smart', 'draw_target', 'target_hunting', 'stop_on_target', 'pity_reserve', 'pool_quota', 'fixed_count', 'no_draw']
const gdrOptions = ref([])
onMounted(async () => {
  const g = await api.listGdrOptions()
  if (g?.ok) gdrOptions.value = g.options
})
</script>

<style scoped>
.run-params {
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
  width: 64px;
  font-size: 12px;
  color: var(--gsc-text-muted);
  text-align: right;
}
.p-sel {
  flex: 1;
  min-width: 0;
}
</style>
