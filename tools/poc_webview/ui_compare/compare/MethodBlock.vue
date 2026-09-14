<template>
  <div class="method-block">
    <div class="method-head">
      <span class="method-title">{{ label }}</span>
      <span class="muted uid">#{{ uid }}</span>
      <el-button size="small" text type="danger" @click="$emit('remove')">移除</el-button>
    </div>

    <!-- 参数区：每个单元独立配置（可配不同参数）-->
    <div class="method-params">
      <template v-if="type === 'gdr'">
        <el-select v-model="params.gdrKey" size="small" style="width:150px">
          <el-option label="目标达成" value="target_achievement" />
          <el-option label="全部目标" value="all_targets" />
          <el-option label="加权满意度" value="weighted_satisfaction" />
        </el-select>
        <span class="p-label">阈值</span>
        <el-input-number v-model="params.threshold" size="small" :min="0" :step="0.1" />
      </template>
      <template v-else-if="type === 'dist'">
        <span class="p-label">分箱数</span>
        <el-input-number v-model="params.nbins" size="small" :min="5" :max="200" />
        <span class="p-label">累计</span>
        <el-switch v-model="params.cdf" size="small" />
      </template>
      <template v-else-if="type === 'process'">
        <span class="p-label">事件类型</span>
        <el-checkbox-group v-model="params.events" size="small">
          <el-checkbox value="pity" size="small">保底</el-checkbox>
          <el-checkbox value="early" size="small">提前</el-checkbox>
          <el-checkbox value="miss" size="small">miss</el-checkbox>
        </el-checkbox-group>
      </template>
      <template v-else-if="type === 'vuln'">
        <span class="p-label">α</span>
        <el-input-number v-model="params.alpha" size="small" :min="0.01" :max="0.5" :step="0.01" />
        <span class="p-label">分箱</span>
        <el-input-number v-model="params.nbins" size="small" :min="5" :max="100" />
      </template>
      <template v-else>
        <span class="p-label">模拟次数</span>
        <el-input-number v-model="params.numSim" size="small" :min="50" :max="100000" :step="100" />
      </template>
    </div>

    <!-- 图表结果区 -->
    <div ref="chartEl" class="method-chart"></div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  uid: { type: Number, required: true },
  type: { type: String, required: true },
  label: { type: String, required: true },
})
defineEmits(['remove'])

// 各方法默认参数（独立于其他同类型单元）
const params = reactive({
  gdrKey: 'target_achievement',
  threshold: 1.0,
  nbins: 30,
  cdf: false,
  events: ['pity'],
  alpha: 0.05,
  numSim: 1000,
})

const chartEl = ref()
let chart = null

onMounted(() => {
  chart = echarts.init(chartEl.value)
  chart.setOption(makeOption(props.type))
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  if (chart) chart.dispose()
})

function onResize() {
  chart && chart.resize()
}

// 占位图（阶段 1b 接 ChartSpec 真实数据）
function makeOption(type) {
  const title = { text: `${props.label}（占位，阶段 1b 接真实数据）`, left: 'center', textStyle: { fontSize: 12 } }
  if (type === 'gdr') {
    return {
      title,
      xAxis: { type: 'category', data: ['100', '200', '300', '400', '500'] },
      yAxis: { type: 'value', name: 'GDR' },
      series: [{ type: 'line', data: [0.2, 0.4, 0.55, 0.65, 0.72], smooth: true, lineStyle: { color: '#1976d2' }, itemStyle: { color: '#1976d2' } }],
    }
  }
  if (type === 'dist') {
    return {
      title,
      xAxis: { type: 'category', data: ['100', '150', '200', '250', '300'] },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: [12, 25, 40, 22, 9], itemStyle: { color: '#2196f3' } }],
    }
  }
  if (type === 'process') {
    return {
      title,
      xAxis: { type: 'category', data: ['AA', 'AB', 'BA', 'BB'] },
      yAxis: { type: 'category', data: ['pity', 'early', 'miss'] },
      visualMap: { min: 0, max: 1, show: false },
      series: [{
        type: 'heatmap',
        data: [[0, 0, 0.8], [1, 0, 0.2], [2, 0, 0.5], [0, 1, 0.3], [1, 1, 0.9], [2, 1, 0.1], [0, 2, 0.6], [1, 2, 0.4], [2, 2, 0.7]],
      }],
    }
  }
  if (type === 'vuln') {
    return {
      title,
      xAxis: { type: 'value', name: '资源' },
      yAxis: { type: 'value', name: 'P(失败)', max: 1 },
      series: [{ type: 'line', data: [[0, 0.95], [500, 0.7], [1000, 0.45], [1500, 0.25], [2000, 0.1]], smooth: true, lineStyle: { color: '#c62828' }, itemStyle: { color: '#c62828' } }],
    }
  }
  return {
    title,
    xAxis: { type: 'category', data: ['0', '1', '2', '3', '4'] },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: [0.2, 0.35, 0.25, 0.15, 0.05], itemStyle: { color: '#f5a623' } }],
  }
}
</script>

<style scoped>
.method-block {
  border: 1px solid var(--gsc-border);
  background: var(--gsc-bg-panel);
}
.method-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--gsc-border);
  font-size: 13px;
  font-weight: 600;
}
.method-head .uid {
  font-size: 11px;
}
.method-head .el-button {
  margin-left: auto;
}
.method-params {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 10px;
  border-bottom: 1px solid var(--gsc-border);
  background: var(--gsc-bg-header);
}
.p-label {
  font-size: 12px;
  color: var(--gsc-text-muted);
}
.method-chart {
  height: 240px;
  padding: 6px;
}
</style>
