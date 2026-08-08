<template>
  <div class="col">
    <h2>Element Plus</h2>

    <section>
      <h3>按钮</h3>
      <div class="demo-row">
        <el-button type="primary">主按钮</el-button>
        <el-button>次按钮</el-button>
        <el-button type="danger">危险</el-button>
        <el-button type="primary" loading>加载中</el-button>
        <el-button disabled>禁用</el-button>
      </div>
    </section>

    <section>
      <h3>表单控件</h3>
      <div class="demo-row">
        <el-input v-model="name" placeholder="姓名" style="width:130px" />
        <el-select v-model="city" placeholder="城市" style="width:110px">
          <el-option label="北京" value="bj" />
          <el-option label="上海" value="sh" />
        </el-select>
        <el-switch v-model="on" />
        <el-date-picker type="date" placeholder="日期" style="width:130px" />
      </div>
    </section>

    <section>
      <h3>表格</h3>
      <el-table :data="rows" size="small" :header-cell-style="{ background: '#f5f7fa' }">
        <el-table-column prop="name" label="策略" />
        <el-table-column prop="value" label="平均抽数" />
        <el-table-column prop="tag" label="标签" />
      </el-table>
    </section>

    <section>
      <h3>卡片 / 标签</h3>
      <el-card shadow="hover" style="margin-bottom:10px">卡片内容</el-card>
      <div class="demo-row">
        <el-tag type="success">成功</el-tag>
        <el-tag type="warning">警告</el-tag>
        <el-tag type="danger">危险</el-tag>
        <el-tag type="info" effect="plain">info</el-tag>
      </div>
    </section>

    <section>
      <h3>标签页 / 进度</h3>
      <el-tabs>
        <el-tab-pane label="总览">总览内容</el-tab-pane>
        <el-tab-pane label="详情">详情内容</el-tab-pane>
      </el-tabs>
      <el-progress :percentage="66" :stroke-width="8" />
    </section>

    <section>
      <h3>交互</h3>
      <div class="demo-row">
        <el-button type="primary" @click="onMessage">弹消息</el-button>
        <el-button type="warning" plain @click="onConfirm">带确认</el-button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const name = ref('')
const city = ref('')
const on = ref(true)
const rows = [
  { name: '固守流', value: 390, tag: '推荐' },
  { name: '定轨流', value: 355, tag: '最快' },
  { name: '退守流', value: 410, tag: '保守' },
]

function onMessage() {
  ElMessage.success('Element Plus 消息提示')
}
function onConfirm() {
  ElMessageBox.confirm('确定要执行吗？', '确认', { type: 'warning' })
    .then(() => ElMessage.success('已确认'))
    .catch(() => {})
}
</script>
