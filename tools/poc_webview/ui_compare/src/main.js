import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import ContextMenu from '@imengyu/vue3-context-menu'
import '@imengyu/vue3-context-menu/lib/vue3-context-menu.css'

import './styles/tokens.css'
import './styles/base.css'
import './styles/context-menu.css'
import App from './App.vue'

// ── 全局错误收集（开发调试：页面加载异常可在 console / __errors 中查看）──
window.__errors = []
window.addEventListener('error', (e) => { window.__errors.push(String(e.message || e.error)) })
window.addEventListener('unhandledrejection', (e) => { window.__errors.push('rejection: ' + String(e.reason)) })

const app = createApp(App)
app.config.errorHandler = (err) => {
  window.__errors.push('vue: ' + String(err))
  console.error('[GSC errorHandler]', err)
}
app.use(ElementPlus).use(ContextMenu)
app.mount('#app')
