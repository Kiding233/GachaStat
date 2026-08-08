<template>
  <div class="wb">
    <div class="wb-head">
      <h2>{{ headTitle }}</h2>
      <div class="wb-ops">
        <el-button size="small" v-if="!isSearch" @click="onImport">导入</el-button>
        <el-button size="small" type="primary" @click="saveToast">保存</el-button>
      </div>
    </div>

    <!-- 添加块工具栏（config：实体 7 种 + 分隔 + 全局单例 2 种；search：搜索专用块）-->
    <div class="toolbar">
      <span class="toolbar-label">添加块</span>
      <el-button v-for="e in entityTypes" :key="e.type" size="small" @click="addBlock(e.type)">{{ e.label }}</el-button>
      <span class="toolbar-divider"></span>
      <el-button v-for="g in globalTypes" :key="g.type" size="small" :disabled="isSingletonPresent(g.type)" @click="addBlock(g.type)">{{ g.label }}</el-button>
    </div>

    <div class="wb-body" ref="bodyRef">
      <!-- 左：配置文本（真相源，可编辑）-->
      <div class="text-pane" :style="{ flexBasis: splitPct + '%' }">
        <div class="pane-head">配置文本（TOML）</div>
        <div class="toml-wrap">
          <textarea
            ref="textRef"
            v-model="configText"
            class="toml-editor"
            spellcheck="false"
            placeholder="输入 TOML：[[banner]] / [[pity]] / [resources.defs] ..."
            @scroll="onTextScroll"
          ></textarea>
          <!-- 块定位高亮条：随文本滚动同步，指示块对应区间 -->
          <div v-if="hl" class="hl-bar" :style="hlStyle" />
        </div>
        <div v-if="parseError" class="parse-error">{{ parseError }}</div>
      </div>

      <!-- 左右分割线（可拖拽调整文本 / 渲染比例）-->
      <div class="splitter" @mousedown.prevent="onSplitterDown" title="拖拽调整左右比例" />

      <!-- 右：渲染的配置块（页 tab + vuedraggable 拖拽排序）-->
      <div class="render-pane">
        <div class="page-bar">
          <span
            v-for="p in pages"
            :key="p.id"
            class="page-tab"
            :class="{ active: currentPage === p.id }"
            @click="currentPage = p.id"
            @dblclick="renamePagePrompt(p)"
          >
            {{ p.name }}
            <span v-if="p.id !== 'g'" class="page-x" @click.stop="removePage(p.id)" title="删除页（块回全局）">×</span>
          </span>
          <el-button size="small" text class="page-add" @click="addPage">+ 新建页</el-button>
        </div>
        <div class="pane-head">渲染视图（{{ visibleBlocks.length }} 块 · 拖拽 ⠿ 重排 · 双击页名重命名）</div>
        <draggable
          :list="visibleBlocks"
          :item-key="dragKey"
          handle=".drag-handle"
          :animation="150"
          class="render-list"
          @end="onDragEnd"
        >
          <template #item="{ element }">
            <ConfigBlock
              v-if="element.type === 'banner'"
              :pages="pages"
              :data="element.data"
              @change="onBlockChange"
              @copy="copyBlock(element)"
              @remove="removeBlock(element)"
              @locate="() => locateBlock(element)"
              @move="(p) => moveBlock(element, p)"
            />
            <!-- 未建模段：原始文本块（只读保留，round-trip 不丢） -->
            <div v-else-if="element.type === '_raw'" class="cfg-block raw-block">
              <div class="cfg-block-head">
                <span class="drag-handle" @click.stop title="拖拽排序">⠿</span>
                <span class="block-type raw-type">未建模</span>
                <span class="block-name">原始文本（只读）</span>
                <div class="block-ops" @click.stop>
                  <el-button size="small" text @click="locateBlock(element)">定位</el-button>
                  <el-button size="small" text type="danger" @click="removeBlock(element)">删除</el-button>
                </div>
              </div>
              <pre class="raw-text">{{ element.data.text }}</pre>
            </div>
            <BlockGeneric
              v-else
              :type="element.type"
              :data="element.data"
              :copyable="isBlockCopyable(element.type)"
              :pages="pages"
              :pool-ids="allPoolIds"
              @change="onBlockChange"
              @copy="copyBlock(element)"
              @remove="removeBlock(element)"
              @locate="() => locateBlock(element)"
              @move="(p) => moveBlock(element, p)"
            />
          </template>
          <template #footer>
            <el-empty v-if="!visibleBlocks.length" :image-size="40" description="本页无配置块（去全局页或其他页查看）" />
          </template>
        </draggable>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import draggable from 'vuedraggable'
import ConfigBlock from './ConfigBlock.vue'
import BlockGeneric from './BlockGeneric.vue'
import api from '../../api.js'
import {
  BLOCK_TYPES, emptyToml, parseToml, blocksToToml, isEntity,
  SEARCH_BLOCK_TYPES, emptySearchToml, parseSearchToml, blocksToSearchToml, SEARCH_INITIAL_TEXT,
} from './configToml.js'

const props = defineProps({
  node: { type: Object, required: true },
  // 'config' 一般配置 / 'search' 搜索配置：同一左文本右块外壳，仅块集合与文本模型不同
  mode: { type: String, default: 'config' },
})
const configName = computed(() => props.node.label)
const isSearch = computed(() => props.mode === 'search')
const headTitle = computed(() => `${isSearch.value ? '搜索任务' : '配置'}：${configName.value}`)

// 块类型集合：config → 实体+全局；search → 搜索专用块
const blockTypes = computed(() => (isSearch.value ? SEARCH_BLOCK_TYPES : BLOCK_TYPES))
const entityTypes = computed(() => Object.entries(blockTypes.value).filter(([, v]) => v.kind === 'entity').map(([type, v]) => ({ type, label: v.label })))
const globalTypes = computed(() => Object.entries(blockTypes.value).filter(([, v]) => v.kind === 'global').map(([type, v]) => ({ type, label: v.label })))

// 解析 / 序列化 / 空模板按模式切换
const doParse = (t) => (isSearch.value ? parseSearchToml(t) : parseToml(t))
const doSerialize = (list) => (isSearch.value ? blocksToSearchToml(list) : blocksToToml(list))
const doEmpty = (type) => (isSearch.value ? emptySearchToml(type) : emptyToml(type))

// ── 左：配置文本（真相源）──
const CONFIG_TEXT = `[[banner]]
id = "b1"
name = "周年庆"
start_day = 0
end_day = 21

[[banner.pool]]
id = "main"
cost = "draw_resource:160"

[[banner.pool.reward]]
card_id = "limited_ssr_1"
probability = 0.2
rarity = "ssr"
featured = true

[[banner.pool.reward]]
card_id = "r_1"
probability = 15.75
rarity = "r"
featured = false

[[banner.lifecycle]]
condition = "time_window"
at = 21
action = "exhaust_banner"

[[card]]
card_id = "limited_ssr_1"
name = "限定角色1"
rarity = "ssr"
initial_count = 0

[[weights]]
card_id = "limited_ssr_1"
desire = 1.0
miss_cost = 1.0
card_value = 1.0

[resources.defs]
draw_resource = "抽卡资源"

[resources.initial]
draw_resource = 55000

[[pity]]
name = "ssr_soft"
type = "soft_interval"
scope = "ssr"
target_featured = true
start = 80
end = 90

[[milestone]]
name = "里程碑1"
threshold = 10
repeat = true
max_triggers = 0
banner = ""

[milestone.bonus_reward]
cards = []
resources = { exchange_currency = 1 }
random_cards = []

[[targets]]
card_id = "limited_ssr_1"
quantity = 1
pool_ids = [
    "b1.main",
]

[rarities]
ranks = [["SSR"],["SR"],["R"]]

[strategy]
key = "smart"`;
const configText = ref(isSearch.value
  ? (props.node?.meta?.configText || SEARCH_INITIAL_TEXT)
  : (props.node?.meta?.configText || CONFIG_TEXT))

// 外部更新（导入/重置/打开派生配置）→ 同步文本
watch(() => props.node?.meta?.configText, (v) => {
  if (typeof v === 'string' && v && v !== configText.value) configText.value = v
})

// ── 双向同步（文本 = 真相源；块编辑 → 防抖写回文本）──
// 块组件用 JSON 快照比较，只在值真正变化时 emit —— 打破
// 「写回文本 → 重建 data → 又触发 watch」的无限循环（id 后缀累积 bug 根因）
const blocks = ref([])
const parseError = ref('')

// 全限定池 ID（{banner}.{pool}），供目标卡关联池下拉选择
const allPoolIds = computed(() =>
  blocks.value
    .filter((b) => b.type === 'banner')
    .flatMap((b) => (b.data.pools || []).map((p) => `${b.data.id}.${p.id}`)),
)

function onTextChange() {
  parseError.value = ''
  try {
    blocks.value = doParse(configText.value)
  } catch (e) {
    parseError.value = '解析失败：' + e.message
  }
}
watch(configText, onTextChange, { immediate: true })

let syncTimer = null
function onBlockChange() {
  clearTimeout(syncTimer)
  syncTimer = setTimeout(() => {
    const t = doSerialize(blocks.value)
    if (t !== configText.value) configText.value = t
  }, 300)
}

// ── 块操作：添加 / 复制 / 删除（写回文本）──
// 全局单表类型（资源/稀有度/策略）在 TOML 中只能有一个段——重复添加会产生非法 TOML
const SINGLETON_HINT = {
  resource: '资源为全局单表（[resources.defs]/[resources.initial]），请在现有资源块内添加条目',
  rarity: '稀有度层级为全局单例（[rarities]），已在渲染视图中',
  strategy: '策略为全局单例（[strategy]），已在渲染视图中',
}
function addBlock(type) {
  if (SINGLETON_HINT[type] && blocks.value.some((b) => b.type === type)) {
    import('element-plus').then(({ ElMessage }) => ElMessage.info(SINGLETON_HINT[type]))
    return
  }
  configText.value = configText.value.trimEnd() + '\n\n' + doEmpty(type)
}
// 单例已存在 → 工具栏按钮灰显
function isSingletonPresent(t) {
  return !!SINGLETON_HINT[t] && blocks.value.some((b) => b.type === t)
}
// 块身份 key：稳定标识（编辑字段不改变 key → 不重建组件 → 输入不失焦）
function blockIdentity(b) {
  const d = b.data
  const id = d?.id ?? d?.card_id ?? d?.key ?? d?.name
  return typeof id === 'string' && id ? id : ''
}
// 拖拽排序：唯一 key + 页内拖拽映射回全局顺序
function dragKey(b) {
  return `${b.type}:${blockIdentity(b)}`
}

// ── 自由分页：页是块的分组容器（默认「全局配置」页，可新建/命名/删除，块可移入页）──
const pages = ref([{ id: 'g', name: '全局配置' }])
const currentPage = ref('g')
const pageOf = reactive({})   // dragKey → pageId（未记录 = 全局页）

const visibleBlocks = computed(() => {
  if (currentPage.value === 'g') return blocks.value.filter((b) => !pageOf[dragKey(b)])
  return blocks.value.filter((b) => pageOf[dragKey(b)] === currentPage.value)
})

function moveBlock(b, pageId) {
  if (pageId === 'g') delete pageOf[dragKey(b)]
  else pageOf[dragKey(b)] = pageId
}
function addPage() {
  const id = `p${pages.value.length}`
  pages.value.push({ id, name: `页 ${pages.value.length}` })
  currentPage.value = id
}
function renamePagePrompt(p) {
  const name = window.prompt('页名称', p.name)
  if (name && name.trim()) p.name = name.trim()
}
function removePage(id) {
  if (id === 'g') return
  for (const k of Object.keys(pageOf)) if (pageOf[k] === id) delete pageOf[k]
  pages.value = pages.value.filter((p) => p.id !== id)
  if (currentPage.value === id) currentPage.value = 'g'
}

// 拖拽重排：页内新顺序 → 映射回全局 blocks（非本页块保持相对位置），再写回文本
function onDragEnd() {
  const vis = visibleBlocks.value
  if (!vis || !vis.length) return
  const visSet = new Set(vis)
  let vi = 0
  blocks.value = blocks.value.map((b) => (visSet.has(b) ? vis[vi++] : b))
  onBlockChange()
}
// 聚合条目表格块（资源/卡片/权重/目标卡）：块级复制无意义，条目级复制在块内提供
const TABLE_TYPES = ['resource', 'card', 'weight', 'target']
function isBlockCopyable(t) {
  return isEntity(t) && !TABLE_TYPES.includes(t)
}
function copyBlock(b) {
  if (!isEntity(b.type) || TABLE_TYPES.includes(b.type)) return
  const copy = JSON.parse(JSON.stringify(b.data))
  // 复制去重：id / card_id / key / name 加后缀；池子 id 保持独立短 id（全限定键由 {banner}.{pool} 拼接）
  if (copy.id) copy.id += '_copy'
  if (copy.card_id) copy.card_id += '_copy'
  if (copy.key) copy.key += '_copy'
  if (copy.name) copy.name += '（副本）'
  blocks.value.push({ type: b.type, data: copy })
  onBlockChange()
}
function removeBlock(b) {
  blocks.value = blocks.value.filter((x) => x !== b)
  onBlockChange()
}

// ── 块 → 文本定位：滚动 + 闪烁高亮（替代块内「原始 TOML」折叠，指示块↔文本对应关系）──
const LINE_HEIGHT = 18   // 与 .toml-editor 的 line-height 一致
const PAD_TOP = 10       // 与 .toml-editor 的 padding-top 一致
const textRef = ref(null)
// 左右拖拽分割线：调整文本 / 渲染比例（splitter token）
const bodyRef = ref(null)
const splitPct = ref(25)
function onSplitterDown(e) {
  document.body.style.cursor = 'col-resize'
  const rect = bodyRef.value?.getBoundingClientRect()
  const onMove = (ev) => {
    if (!rect) return
    const pct = Math.min(70, Math.max(12, ((ev.clientX - rect.left) / rect.width) * 100))
    splitPct.value = Math.round(pct)
  }
  const onUp = () => {
    document.body.style.cursor = ''
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}
const scrollTop = ref(0)
const hl = ref(null)     // { start, end } 行区间
let hlTimer = null

function onTextScroll() {
  scrollTop.value = textRef.value?.scrollTop || 0
}
function locateBlock(b) {
  const el = textRef.value
  if (!el || !b.lines) return
  const [start, end] = b.lines
  el.scrollTop = Math.max(0, start * LINE_HEIGHT - 60)
  scrollTop.value = el.scrollTop
  hl.value = { start, end }
  clearTimeout(hlTimer)
  hlTimer = setTimeout(() => { hl.value = null }, 1000)
}
const hlStyle = computed(() => {
  if (!hl.value) return { display: 'none' }
  const top = PAD_TOP + hl.value.start * LINE_HEIGHT - scrollTop.value
  const height = (hl.value.end - hl.value.start + 1) * LINE_HEIGHT
  return { top: top + 'px', height: height + 'px' }
})

async function saveToast() {
  if (isSearch.value) {
    // 搜索配置：保存到节点 meta（不写主 config.toml）
    props.node.meta.configText = configText.value
    import('element-plus').then(({ ElMessage }) => ElMessage.success('搜索配置已保存'))
    return
  }
  const r = await api.saveConfigText(configText.value)
  if (r?.ok) {
    props.node.meta.configText = configText.value
    import('element-plus').then(({ ElMessage }) => ElMessage.success('配置已保存'))
  } else {
    const msg = (r?.errors || []).join('；') || r?.error || '未知错误'
    import('element-plus').then(({ ElMessage }) => ElMessage.error('保存失败：' + msg))
  }
}
async function onImport() {
  if (isSearch.value) return
  const fp = await api.pickFile(false, ['TOML 配置文件 (*.toml)', '所有文件 (*)'])
  if (!fp?.ok || !fp.path) return
  const r = await api.importConfigFile(fp.path)
  if (r?.ok && r.text) {
    configText.value = r.text
    import('element-plus').then(({ ElMessage }) => ElMessage.success(`已导入：${fp.path}`))
  } else {
    import('element-plus').then(({ ElMessage }) => ElMessage.error('导入失败：' + (r?.error || '未知错误')))
  }
}
</script>

<style scoped>
.wb {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: var(--gsc-bg-panel);
  border: 1px solid var(--gsc-border);
  padding: 8px;
  box-shadow: var(--gsc-shadow);
}
.wb-head {
  flex-shrink: 0;
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
/* 配置上下文操作切换 */
.op-switch {
  flex-shrink: 0;
  padding-bottom: 8px;
}
.wb-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 8px;
}

/* 左：文本（真相源）——宽度由拖拽分割线 flexBasis 控制（默认 25%）*/
.text-pane {
  flex: 0 0 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
}
/* 左右拖拽分割线（splitter token） */
.splitter {
  flex: 0 0 5px;
  cursor: col-resize;
  background: var(--gsc-border);
  user-select: none;
}
.splitter:hover {
  background: var(--el-color-primary);
}
.pane-head {
  flex-shrink: 0;
  padding: 3px 8px;
  font-size: 11px;
  color: var(--gsc-text-muted);
  background: var(--gsc-bg-header);
  border-bottom: 1px solid var(--gsc-border);
}
.toml-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
}
.toml-editor {
  flex: 1;
  min-height: 0;
  width: 100%;
  border: none;
  resize: none;
  padding: 10px;
  font-family: var(--gsc-font-mono);
  font-size: 12px;
  line-height: 18px;      /* 固定行高：与 JS 定位计算（LINE_HEIGHT）一致 */
  background: transparent;
  color: var(--gsc-text-primary);
  outline: none;
}
/* 块定位高亮：整条（左侧竖条 + 右侧背景）作为一个整体 opacity 淡出，
   惯例做法：高亮整体淡入淡出，避免背景先消失、竖条残留后突然消失 */
.hl-bar {
  position: absolute;
  left: 0;
  right: 0;
  pointer-events: none;
  border-left: 3px solid var(--el-color-primary);
  background: rgba(25, 118, 210, 0.24);
  animation: hl-fade 1s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}
@keyframes hl-fade {
  from { opacity: 1; }
  to { opacity: 0; }
}
.parse-error {
  flex-shrink: 0;
  padding: 6px 10px;
  color: var(--el-color-danger);
  font-size: 12px;
  background: #ffebee;
  border-top: 1px solid var(--gsc-border);
}

/* 右：渲染块（占剩余空间） */
.render-pane {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--gsc-border);
  background: var(--gsc-bg-result);
}
/* 页 tab 栏（自由分页：页是块的分组容器） */
.page-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
  padding: 3px 6px;
  border-bottom: 1px solid var(--gsc-border);
  background: var(--gsc-bg-header);
}
.page-tab {
  padding: 2px 8px;
  font-size: 12px;
  cursor: pointer;
  color: var(--gsc-text-muted);
  border: 1px solid transparent;
  user-select: none;
  white-space: nowrap;
}
.page-tab:hover {
  background: var(--gsc-bg-result);
}
.page-tab.active {
  background: var(--gsc-bg-panel);
  border-color: var(--gsc-border);
  color: var(--gsc-text-primary);
  font-weight: 600;
}
.page-x {
  margin-left: 4px;
  color: var(--gsc-text-faint);
}
.page-x:hover {
  color: var(--el-color-danger);
}
.page-add {
  margin-left: 2px;
}
.render-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* 原始文本块（未建模段） */
.cfg-block.raw-block {
  border: 1px dashed var(--gsc-border);
  background: var(--gsc-bg-panel);
}
.block-type.raw-type {
  color: var(--gsc-text-muted);
}
.raw-text {
  margin: 0;
  padding: 10px;
  font-family: var(--gsc-font-mono);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 180px;
  overflow: auto;
  background: #fafbfc;
}
</style>
