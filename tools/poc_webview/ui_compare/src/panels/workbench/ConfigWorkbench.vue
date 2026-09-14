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
      <!-- 工具栏最右侧：折叠全部 / 配置可视化预览（时间线 / 日历）-->
      <span class="toolbar-spacer"></span>
      <el-button v-if="!isSearch" size="small" @click="collapseAllBlocks">全部折叠</el-button>
      <el-button v-if="!isSearch" size="small" type="info" @click="previewDlg = true">预览</el-button>
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
              :expanded="isBlockExpanded(element)"
              @toggle-head="() => toggleBlock(element)"
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
              :banner-ids="allBannerIds"
              :card-pools="allCardPools"
              :rarity-names="allRarityNames"
              :expanded="isBlockExpanded(element)"
              @toggle-head="() => toggleBlock(element)"
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

    <!-- 配置可视化预览（时间线 + 日历：资源获取曲线 / 池子开放区间）-->
    <el-dialog v-model="previewDlg" title="配置可视化预览" width="900" append-to-body>
      <ConfigPreview :config-text="configText" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import draggable from 'vuedraggable'
import ConfigBlock from './ConfigBlock.vue'
import BlockGeneric from './BlockGeneric.vue'
import ConfigPreview from './ConfigPreview.vue'
import api from '../../api.js'
import {
  BLOCK_TYPES, emptyToml, parseToml, blocksToToml, isEntity,
  SEARCH_BLOCK_TYPES, emptySearchToml, parseSearchToml, blocksToSearchToml, SEARCH_INITIAL_TEXT,
  extractUiSection, injectUiSection,
} from './configToml.js'

const props = defineProps({
  node: { type: Object, required: true },
  // 'config' 一般配置 / 'search' 搜索配置：同一左文本右块外壳，仅块集合与文本模型不同
  mode: { type: String, default: 'config' },
})
const configName = computed(() => props.node.label)
const isSearch = computed(() => props.mode === 'search')
const headTitle = computed(() => `${isSearch.value ? '搜索任务' : '配置'}：${configName.value}`)
const previewDlg = ref(false)   // 配置可视化预览对话框

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
  : (extractUiSection(props.node?.meta?.configText || CONFIG_TEXT).cleanText || CONFIG_TEXT))

// 外部更新（导入/重置/打开派生配置）→ 同步文本（剥离 [ui] 段）
watch(() => props.node?.meta?.configText, (v) => {
  if (typeof v === 'string' && v) {
    const { cleanText } = extractUiSection(v)
    if (cleanText !== configText.value) configText.value = cleanText
  }
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
// Banner ID（里程碑「适用 Banner」下拉：空=全部）
const allBannerIds = computed(() =>
  blocks.value.filter((b) => b.type === 'banner').map((b) => b.data.id).filter(Boolean),
)
// 稀有度名（保底 scope 下拉动态选项，对齐 [rarities] 注册名；config_toml.py L524-532）
const allRarityNames = computed(() => {
  const names = new Set()
  for (const b of blocks.value) {
    if (b.type === 'rarity' && b.data?.entries) {
      for (const e of b.data.entries) {
        const n = String(e.rank || e.name || '').trim().toLowerCase()
        if (n) names.add(n)
      }
    }
  }
  return [...names]
})
// 卡 → 全限定池 ID[]（目标卡关联池只读自动解析：该卡出现在哪些池的奖励中，对齐旧 UI _update_target_pools）
const allCardPools = computed(() => {
  const map = {}
  for (const b of blocks.value.filter((x) => x.type === 'banner')) {
    for (const p of (b.data.pools || [])) {
      for (const r of (p.rewards || [])) {
        if (r.card_id) {
          const k = `${b.data.id}.${p.id}`
          map[r.card_id] = map[r.card_id] || []
          if (!map[r.card_id].includes(k)) map[r.card_id].push(k)
        }
      }
    }
  }
  return map
})

function onTextChange() {
  parseError.value = ''
  try {
    const before = blocks.value.length
    blocks.value = doParse(configText.value)
    // 首次解析：按旧 UI tag 结构补全未归置块（已归置的保留，未归置的按类型进默认页）
    if (!_organizedOnce) {
      _organizedOnce = true
      for (const b of blocks.value) {
        const pageId = TYPE_TO_PAGE[b.type]
        if (pageId && !pageOf[dragKey(b)] && pages.value.some((p) => p.id === pageId)) {
          pageOf[dragKey(b)] = pageId
        }
      }
      persistPages()
    }
    // 添加块：新块归到添加时的当前页（非全局页，否则留全局）
    if (_addPendingPage && _addPendingPage !== 'g') {
      for (let i = _addPageBefore; i < blocks.value.length; i++) {
        pageOf[dragKey(blocks.value[i])] = _addPendingPage
      }
      persistPages()
    }
    // 添加块：新块默认展开（便于立即编辑）——仅 addBlock 触发的解析（_addPendingPage 非空）
    if (_addPendingPage !== null && blocks.value.length > _addPageBefore) {
      for (let i = _addPageBefore; i < blocks.value.length; i++) {
        foldState[foldKey(blocks.value[i])] = true
      }
    }
    _addPendingPage = null
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
// 全局单表类型（资源已可多块，仅稀有度/策略）在 TOML 中只能有一个段——重复添加会产生非法 TOML
const SINGLETON_HINT = {
  rarity: '稀有度层级为全局单例（[rarities]），已在渲染视图中',
  strategy: '策略为全局单例（[strategy]），已在渲染视图中',
}
function addBlock(type) {
  if (SINGLETON_HINT[type] && blocks.value.some((b) => b.type === type)) {
    import('element-plus').then(({ ElMessage }) => ElMessage.info(SINGLETON_HINT[type]))
    return
  }
  // 记录添加时的当前页——解析后新块归到该页（非全局页）
  _addPendingPage = currentPage.value
  _addPageBefore = blocks.value.length
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

// ── 块手风琴折叠（块头点击互斥展开；默认按类型分工：纯表常开、实例折叠、资源定义按内容自适应）──
// 类型分工（对齐旧 UI「卡池/保底/累抽逐个编辑，其余整表」）：
//   实例型（banner/pity/milestone/resource_gains）→ 默认折叠成一行头，页内一览
//   聚合表型（card/weight/target/rarity/strategy）→ 默认常开整表（行里没有装不下的内容）
//   resource_defs → 出现扩展内容（P77 生命周期等）时折叠，否则常开
const EXPAND_DEFAULT = {
  banner: false, pity: false, milestone: false, resource_gains: false,
  card: true, weight: true, target: true, rarity: true, strategy: true,
}
const foldState = reactive({})   // 折叠键 → expanded（用户手动切换后覆盖默认）
// 折叠键：有身份用 dragKey；无身份（资源定义等）用类型+序号，避免多块同键互踩
function foldKey(b) {
  const id = blockIdentity(b)
  return id ? dragKey(b) : `${b.type}:${blocks.value.indexOf(b)}`
}
function defaultExpanded(b) {
  if (b.type === 'resource_defs') {
    const hasDetail = (b.data.entries || []).some((e) => e.lifecycle !== undefined && e.lifecycle !== null)
    return !hasDetail
  }
  return EXPAND_DEFAULT[b.type] !== false
}
function isBlockExpanded(b) {
  const k = foldKey(b)
  return foldState[k] !== undefined ? foldState[k] : defaultExpanded(b)
}
function toggleBlock(b) {
  const k = foldKey(b)
  // 同页其余块收起（手风琴：同时只看一个）
  for (const o of visibleBlocks.value) {
    if (o !== b && o.type !== '_raw') foldState[foldKey(o)] = false
  }
  foldState[k] = !isBlockExpanded(b)
}
function collapseAllBlocks() {
  for (const b of blocks.value) foldState[foldKey(b)] = false
}

// ── 自由分页：页是块的分组容器（默认「全局配置」页，可新建/命名/删除，块可移入页）──
// 分页状态持久化到 config.toml 的 [ui] 段（page_state JSON）——保存配置时随文件写入，
// 加载配置时从 [ui] 恢复。可建「全局配置/卡牌定义/资源管理」等页恢复旧 UI 的 tag 结构。
const _uiInit = isSearch.value ? {} : (extractUiSection(props.node?.meta?.configText || '').ui.pageState || {})
const _ps = _uiInit || {}
// 无 pageState（新配置/未组织）→ 按旧 UI tag 结构建默认页，首次解析后自动按类型归置块
const DEFAULT_PAGES = [
  { id: 'g', name: '全局配置' },
  { id: 'card', name: '卡牌定义' },
  { id: 'res', name: '资源管理' },
  { id: 'banner', name: '卡池管理' },
  { id: 'pity', name: '保底机制' },
  { id: 'ms', name: '累抽奖励' },
  { id: 'target', name: '目标卡' },
  { id: 'weight', name: '权重配置' },
  { id: 'strategy', name: '策略' },
]
const TYPE_TO_PAGE = { card: 'card', resource_defs: 'res', resource_gains: 'res', banner: 'banner', pity: 'pity', milestone: 'ms', target: 'target', weight: 'weight', strategy: 'strategy' }
let _organizedOnce = false   // 首次解析后按默认页补全未归置块（新配置全归置；旧 pageState 缺失的补全，不动已归置的）
let _addPendingPage = null     // 添加块时记录当前页，解析后新块归到该页（非全局页）
let _addPageBefore = 0

const pages = ref(_ps?.pages?.length ? JSON.parse(JSON.stringify(_ps.pages)) : JSON.parse(JSON.stringify(DEFAULT_PAGES)))
const currentPage = ref(_ps?.currentPage || 'g')
const pageOf = reactive(_ps?.pageOf ? { ..._ps.pageOf } : {})   // dragKey → pageId（未记录 = 全局页）
// 保存/加载用的 UI 元数据对象（保存时注入 [ui] 段）
const _pageStateObj = reactive({
  pages: JSON.parse(JSON.stringify(pages.value)),
  pageOf: {},
  currentPage: currentPage.value,
})

function persistPages() {
  _pageStateObj.pages = JSON.parse(JSON.stringify(pages.value))
  _pageStateObj.pageOf = { ...pageOf }
  _pageStateObj.currentPage = currentPage.value
}
// 分页操作即时持久化（改页/移块/切页都同步到 _pageStateObj，保存配置时随 [ui] 写文件）
watch([pages, pageOf, currentPage], persistPages, { deep: true })

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
// 聚合条目表格块（卡片/权重/目标卡）：块级复制无意义，条目级复制在块内提供；
// 资源块可整块复制（多个资源块序列化时合并去重）
const TABLE_TYPES = ['card', 'weight', 'target']
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
  // 解析失败时 blocks 保留旧 lines，定位会偏移到旧行区间 → 禁用
  if (parseError.value) return
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
  // 分页状态等 UI 元数据注入 [ui] 段，随配置一起持久化到 config.toml
  const fullText = injectUiSection(configText.value, _pageStateObj)
  const r = await api.saveConfigText(fullText)
  if (r?.ok) {
    props.node.meta.configText = fullText
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
/* 添加块工具栏：左实体/全局按钮，最右侧「预览」按钮（spacer 推右）*/
.toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  padding: 4px 6px;
  border: 1px solid var(--gsc-border);
  background: var(--gsc-bg-header);
  margin-bottom: 8px;
}
.toolbar-label {
  font-size: 11px;
  color: var(--gsc-text-muted);
  margin-right: 4px;
}
.toolbar .el-button {
  height: 22px;
  padding: 0 8px;
  font-size: 12px;
}
.toolbar-divider {
  width: 1px;
  height: 16px;
  background: var(--gsc-border);
  margin: 0 2px;
}
.toolbar-spacer {
  flex: 1;
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
