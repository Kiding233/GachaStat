<template>
  <n-config-provider>
    <n-dialog-provider>
      <n-message-provider>
        <NaiveContent />
      </n-message-provider>
    </n-dialog-provider>
  </n-config-provider>
</template>

<script setup>
// provider 壳：useMessage/useDialog 必须在 provider 后代组件中调用，
// 故把实际内容拆到 NaiveContent.vue（NaiveContent 是 provider 的子级，注入成功）
import NaiveContent from './NaiveContent.vue'
</script>
