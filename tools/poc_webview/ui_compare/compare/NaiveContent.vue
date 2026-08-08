<template>
  <div class="col">
    <h2>Naive UI</h2>

    <section>
      <h3>按钮</h3>
      <div class="demo-row">
        <n-button type="primary">主按钮</n-button>
        <n-button>次按钮</n-button>
        <n-button type="error">危险</n-button>
        <n-button type="primary" loading>加载中</n-button>
        <n-button disabled>禁用</n-button>
      </div>
    </section>

    <section>
      <h3>表单控件</h3>
      <div class="demo-row">
        <n-input v-model:value="name" placeholder="姓名" style="width:130px" />
        <n-select v-model:value="city" :options="cities" placeholder="城市" style="width:110px" />
        <n-switch v-model:value="on" />
        <n-date-picker type="date" style="width:130px" />
      </div>
    </section>

    <section>
      <h3>表格</h3>
      <n-data-table :columns="columns" :data="rows" size="small" :bordered="true" />
    </section>

    <section>
      <h3>卡片 / 标签</h3>
      <n-card size="small" style="margin-bottom:10px">卡片内容</n-card>
      <div class="demo-row">
        <n-tag type="success">成功</n-tag>
        <n-tag type="warning">警告</n-tag>
        <n-tag type="error">危险</n-tag>
        <n-tag type="info" bordered>info</n-tag>
      </div>
    </section>

    <section>
      <h3>标签页 / 进度</h3>
      <n-tabs type="line">
        <n-tab-pane name="a" tab="总览">总览内容</n-tab-pane>
        <n-tab-pane name="b" tab="详情">详情内容</n-tab-pane>
      </n-tabs>
      <n-progress type="line" :percentage="66" :height="8" />
    </section>

    <section>
      <h3>交互</h3>
      <div class="demo-row">
        <n-button type="primary" @click="onMessage">弹消息</n-button>
        <n-button type="warning" secondary @click="onConfirm">带确认</n-button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'

// 此组件在 provider 后代内渲染，注入成功
const message = useMessage()
const dialog = useDialog()

const name = ref('')
const city = ref(null)
const on = ref(true)
const cities = [
  { label: '北京', value: 'bj' },
  { label: '上海', value: 'sh' },
]
const rows = [
  { name: '固守流', value: 390, tag: '推荐' },
  { name: '定轨流', value: 355, tag: '最快' },
  { name: '退守流', value: 410, tag: '保守' },
]
const columns = [
  { title: '策略', key: 'name' },
  { title: '平均抽数', key: 'value' },
  { title: '标签', key: 'tag' },
]

function onMessage() {
  message.success('Naive UI 消息提示')
}
function onConfirm() {
  dialog.warning({
    title: '确认',
    content: '确定要执行吗？',
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: () => message.success('已确认'),
  })
}
</script>
