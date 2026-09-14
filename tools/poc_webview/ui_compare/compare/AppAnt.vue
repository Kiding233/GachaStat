<template>
  <div class="col">
    <h2>Ant Design Vue</h2>

    <section>
      <h3>按钮</h3>
      <div class="demo-row">
        <a-button type="primary">主按钮</a-button>
        <a-button>次按钮</a-button>
        <a-button type="primary" danger>危险</a-button>
        <a-button type="primary" loading>加载中</a-button>
        <a-button disabled>禁用</a-button>
      </div>
    </section>

    <section>
      <h3>表单控件</h3>
      <div class="demo-row">
        <a-input v-model:value="name" placeholder="姓名" style="width:130px" />
        <a-select v-model:value="city" placeholder="城市" style="width:110px">
          <a-select-option value="bj">北京</a-select-option>
          <a-select-option value="sh">上海</a-select-option>
        </a-select>
        <a-switch v-model:checked="on" />
        <a-date-picker style="width:130px" />
      </div>
    </section>

    <section>
      <h3>表格</h3>
      <a-table :data-source="rows" :columns="columns" size="small" :pagination="false" />
    </section>

    <section>
      <h3>卡片 / 标签</h3>
      <a-card hoverable style="margin-bottom:10px">卡片内容</a-card>
      <div class="demo-row">
        <a-tag color="green">成功</a-tag>
        <a-tag color="orange">警告</a-tag>
        <a-tag color="red">危险</a-tag>
        <a-tag>info</a-tag>
      </div>
    </section>

    <section>
      <h3>标签页 / 进度</h3>
      <a-tabs>
        <a-tab-pane key="a" tab="总览">总览内容</a-tab-pane>
        <a-tab-pane key="b" tab="详情">详情内容</a-tab-pane>
      </a-tabs>
      <a-progress :percent="66" size="small" />
    </section>

    <section>
      <h3>交互</h3>
      <div class="demo-row">
        <a-button type="primary" @click="onMessage">弹消息</a-button>
        <a-button @click="onConfirm">带确认</a-button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { message, Modal } from 'ant-design-vue'

const name = ref('')
const city = ref(null)
const on = ref(true)
const rows = [
  { key: '1', name: '固守流', value: 390, tag: '推荐' },
  { key: '2', name: '定轨流', value: 355, tag: '最快' },
  { key: '3', name: '退守流', value: 410, tag: '保守' },
]
const columns = [
  { title: '策略', dataIndex: 'name' },
  { title: '平均抽数', dataIndex: 'value' },
  { title: '标签', dataIndex: 'tag' },
]

function onMessage() {
  message.success('Ant Design 消息提示')
}
function onConfirm() {
  Modal.confirm({
    title: '确认',
    content: '确定要执行吗？',
    onOk: () => message.success('已确认'),
  })
}
</script>
