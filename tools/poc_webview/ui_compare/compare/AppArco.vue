<template>
  <div class="col">
    <h2>Arco Design Vue</h2>

    <section>
      <h3>按钮</h3>
      <div class="demo-row">
        <a-button type="primary">主按钮</a-button>
        <a-button>次按钮</a-button>
        <a-button type="primary" status="danger">危险</a-button>
        <a-button type="primary" loading>加载中</a-button>
        <a-button disabled>禁用</a-button>
      </div>
    </section>

    <section>
      <h3>表单控件</h3>
      <div class="demo-row">
        <a-input v-model="name" placeholder="姓名" style="width:130px" />
        <a-select v-model="city" placeholder="城市" style="width:110px">
          <a-option value="bj">北京</a-option>
          <a-option value="sh">上海</a-option>
        </a-select>
        <a-switch v-model="on" />
        <a-date-picker style="width:130px" />
      </div>
    </section>

    <section>
      <h3>表格</h3>
      <a-table :data="rows" size="small" :pagination="false">
        <template #columns>
          <a-table-column title="策略" data-index="name" />
          <a-table-column title="平均抽数" data-index="value" />
          <a-table-column title="标签" data-index="tag" />
        </template>
      </a-table>
    </section>

    <section>
      <h3>卡片 / 标签</h3>
      <a-card hoverable style="margin-bottom:10px">卡片内容</a-card>
      <div class="demo-row">
        <a-tag color="green">成功</a-tag>
        <a-tag color="orange">警告</a-tag>
        <a-tag color="red">危险</a-tag>
        <a-tag color="gray">info</a-tag>
      </div>
    </section>

    <section>
      <h3>标签页 / 进度</h3>
      <a-tabs>
        <a-tab-pane key="a" title="总览">总览内容</a-tab-pane>
        <a-tab-pane key="b" title="详情">详情内容</a-tab-pane>
      </a-tabs>
      <a-progress :percent="66" :size="'small'" />
    </section>

    <section>
      <h3>交互</h3>
      <div class="demo-row">
        <a-button type="primary" @click="onMessage">弹消息</a-button>
        <a-button type="primary" status="warning" @click="onConfirm">带确认</a-button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'

const name = ref('')
const city = ref(null)
const on = ref(true)
const rows = [
  { name: '固守流', value: 390, tag: '推荐' },
  { name: '定轨流', value: 355, tag: '最快' },
  { name: '退守流', value: 410, tag: '保守' },
]

function onMessage() {
  Message.success('Arco Design 消息提示')
}
function onConfirm() {
  Modal.warning({
    title: '确认',
    content: '确定要执行吗？',
    onOk: () => Message.success('已确认'),
  })
}
</script>
