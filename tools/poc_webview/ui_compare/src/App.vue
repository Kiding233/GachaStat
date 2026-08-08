<template>
  <div class="app-shell">
    <!-- 顶部：菜单栏（GachaStat 标题 + 文件/工具/帮助）+ 下方工具栏（新建 + 运行）-->
    <header class="app-header">
      <div class="menu-bar">
        <span class="app-brand">GachaStat</span>
        <nav class="app-menus">
          <el-dropdown trigger="click">
            <span class="menu-btn">文件</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="onImportConfig">导入配置</el-dropdown-item>
                <el-dropdown-item @click="onExportConfig">导出配置</el-dropdown-item>
                <el-dropdown-item @click="onResetConfig">重置为默认配置</el-dropdown-item>
                <el-dropdown-item @click="saveWorkspace">保存工作区</el-dropdown-item>
                <el-dropdown-item @click="onExportResults">导出结果</el-dropdown-item>
                <el-dropdown-item divided @click="onExit">退出</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-dropdown trigger="click">
            <span class="menu-btn">工具</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="pluginDlg = true">插件管理</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-dropdown trigger="click">
            <span class="menu-btn">帮助</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="aboutDlg = true">关于</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </nav>
      </div>
      <div class="tool-bar">
        <el-button size="small" @click="createNode('config')">新建配置</el-button>
        <el-button size="small" @click="createNode('search')">新建搜索任务</el-button>
        <el-button size="small" @click="createCompareTask()">新建对比分析任务</el-button>
        <el-button size="small" @click="createNode('user_folder')">新建文件夹</el-button>
        <span class="tb-spacer"></span>
        <el-button size="small" type="primary" :disabled="runKind === 'none'" @click="dispatchTask">{{ runBtnLabel }}</el-button>
        <el-button size="small" @click="switchRun">任务管理</el-button>
      </div>
    </header>

    <!-- 主体：左工作区树 + 右上下文工作区 -->
    <div class="app-body">
      <aside class="asset-tree" :style="{ flexBasis: treeWidth + 'px' }" @contextmenu.prevent="onRootCtx">
        <div class="tree-head">工作区</div>
        <el-tree
          :data="treeData"
          :props="treeProps"
          node-key="id"
          default-expand-all
          highlight-current
          :expand-on-click-node="false"
          :current-node-key="activeNodeId"
          @node-click="onNodeClick"
        >
          <template #default="{ data }">
            <div
              class="tree-node-wrap"
              @contextmenu.stop="(e) => onNodeCtx(e, data)"
              @mouseenter="onNodeHover(data)"
              @mouseleave="onNodeLeave"
            >
              <span
                class="tree-node"
                :class="{ 'tree-hl': isHighlighted(data), 'node-locked': isLockedNode(data) }"
              >
                <!-- 数据集比较勾选：独立小勾选框，点击不触发行打开 -->
                <el-checkbox
                  v-if="data.type === 'dataset'"
                  :model-value="checkedDs.includes(data)"
                  size="small"
                  class="cmp-check"
                  @click.stop
                  @change="(v) => onToggleCompare(data, v)"
                />
                <!-- 文件夹脸 vs 文件脸：folder 用 📁 + 浅灰底 + 加粗，file 用类型色点 -->
                <span v-if="data.kind === 'folder'" class="folder-ico">📁</span>
                <span v-else class="type-mark" :style="{ background: typeColor(data.type) }" />
                <span class="tree-label">{{ data.label }}</span>
                <span v-if="data.status === 'running'" class="status-badge running">运行中</span>
                <span v-else-if="data.status === 'locked'" class="status-badge locked">锁定</span>
                <!-- 行尾快捷创建分析（dataset）：常驻可见、不占树空间、不闪烁 -->
                <el-button
                  v-if="data.type === 'dataset'"
                  size="small"
                  text
                  type="primary"
                  class="add-analysis-btn"
                  title="创建统计分析条目"
                  @click.stop="createAnalysis(data)"
                >＋ 分析</el-button>
              </span>
            </div>
          </template>
        </el-tree>

        <!-- 移动到文件夹对话框 -->
        <el-dialog v-model="moveDlg" title="移动到文件夹" width="360" append-to-body>
          <el-radio-group v-model="moveTarget" class="move-options">
            <el-radio :label="null">工作区根</el-radio>
            <el-radio v-for="f in moveFolders" :key="f.id" :label="f.id">{{ f.label }}</el-radio>
          </el-radio-group>
          <template #footer>
            <el-button size="small" @click="moveDlg = null">取消</el-button>
            <el-button size="small" type="primary" @click="confirmMove">移动</el-button>
          </template>
        </el-dialog>
      </aside>

      <!-- 资产树 / 工作区 拖拽分割线（splitter token）-->
      <div class="tree-splitter" @mousedown.prevent="onTreeSplitterDown" title="拖拽调整树宽" />

      <main class="workbench">
        <!-- 锁定只读横幅：当前打开资产有 running/locked 祖先（如搜索运行中的配置与数据组）-->
        <el-alert v-if="lockedBanner" type="warning" :closable="false" title="所属搜索运行中，可查看但暂不可编辑/运行" class="lock-banner" />

        <!-- 运行与任务监控全局页（非资产节点）-->
        <RunWorkbench
          ref="runWbRef"
          v-if="viewMode === 'run'"
          :target="runTarget"
          :task-queue="taskQueue"
          :configs="runConfigs"
          :searches="runSearches"
          @create-task="onCreateTask"
          @cancel-task="onCancelTask"
          @view-result="onViewResult"
        />

        <template v-else>
          <!-- 数据集多选：勾选 ≥1 显示多选信息页（覆盖资产页，条目数增加）。勾选保留独立于点击 -->
          <template v-if="showDsSel && checkedDs.length">
            <div class="ds-sel-bar">
              <span class="ds-sel-label">已选 {{ checkedDs.length }} 个数据集</span>
              <el-button size="small" text @click="clearDsSel">清空</el-button>
            </div>
            <DatasetInfoWorkbench
              :nodes="checkedDs"
              :configs="configList"
              preselect
              @create-compare="onCreateCompare"
              @open="onDsOpen"
            />
          </template>

          <!-- 资产页：点击什么显示什么本身（v-show 保留实例）-->
          <template v-else>
            <template v-for="t in openedTabs" :key="t.id">
              <component
                :is="WORKBENCH[t.type]"
                v-show="t.id === activeNodeId"
                v-bind="workbenchProps(t)"
                @create-derived="onCreateDerived"
                @create-compare="onCreateCompare"
                @convert-config="onConvertSearchConfig"
                @open="openTab"
                @open-node="openTab"
              />
            </template>
            <el-empty v-if="!openedTabs.length" description="点击左侧工作区打开配置 / 数据集 / 搜索任务 / 对比分析任务等页面" />
          </template>
        </template>
      </main>
    </div>

    <!-- 关于对话框 -->
    <el-dialog v-model="aboutDlg" title="关于 GachaStat" width="420" append-to-body>
      <div class="about-body">
        <div class="about-name">GachaStat</div>
        <div class="about-version">版本 {{ aboutInfo.version || '—' }}</div>
        <div class="about-tech">{{ aboutInfo.tech || '' }}</div>
        <div class="about-desc">抽卡概率模拟与分析系统（pywebview + Vue3 + Element Plus + ECharts）</div>
      </div>
      <template #footer>
        <el-button size="small" type="primary" @click="aboutDlg = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 插件管理对话框 -->
    <el-dialog v-model="pluginDlg" title="插件管理" width="560" append-to-body>
      <el-table :data="plugins" size="small" max-height="320">
        <el-table-column prop="name" label="插件名称" min-width="120" />
        <el-table-column prop="key" label="Key" min-width="110" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.disabled" size="small" type="info">已禁用</el-tag>
            <el-tag v-else-if="row.invalid" size="small" type="danger">加载失败</el-tag>
            <el-tag v-else size="small" type="success">启用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button v-if="!row.disabled" size="small" text type="danger" @click="togglePlugin(row)">禁用</el-button>
            <el-button v-else size="small" text @click="togglePlugin(row)">启用</el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button size="small" type="primary" @click="pluginDlg = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 底部状态栏 -->
    <footer class="app-footer">
      <span id="status-msg">{{ statusMsg }}</span>
      <span class="muted">当前：{{ activeLabel }}</span>
    </footer>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted } from 'vue'
import ContextMenu from '@imengyu/vue3-context-menu'
import api, { onTaskProgress, onTaskDone } from './api.js'
import ConfigWorkbench from './panels/workbench/ConfigWorkbench.vue'
import DatasetWorkbench from './panels/workbench/DatasetWorkbench.vue'
import DatasetInfoWorkbench from './panels/workbench/DatasetInfoWorkbench.vue'
import CompareWorkbench from './panels/workbench/CompareWorkbench.vue'
import FolderWorkbench from './panels/workbench/FolderWorkbench.vue'
import SearchResultWorkbench from './panels/workbench/SearchResultWorkbench.vue'
import RunWorkbench from './panels/workbench/RunWorkbench.vue'

// 类型 → 工作区组件（点击什么显示什么本身。派生配置不是特别实体类型：
// 只是被派生出来、挂在源配置下的普通 config 文件，与普通配置同一编辑器）
const WORKBENCH = {
  config: ConfigWorkbench,
  dataset: DatasetInfoWorkbench,
  analysis: DatasetWorkbench,
  search: ConfigWorkbench,
  group: FolderWorkbench,
  search_result: SearchResultWorkbench,
  compare_task: CompareWorkbench,
  user_folder: FolderWorkbench,
}

// ── 工作区树（folder/file 模型，reactive；条目=文件，文件夹=容器）──
// 工作区树（folder/file 模型，reactive）。启动时从后端加载真实 config（config.toml），
// 数据集/分析/搜索产物由真实任务产生后创建节点。
const treeData = reactive([])

const treeProps = { label: 'label', children: 'children' }
// 资产树宽度（拖拽分割线可调，splitter token）
const treeWidth = ref(280)
function onTreeSplitterDown(e) {
  document.body.style.cursor = 'col-resize'
  const onMove = (ev) => { treeWidth.value = Math.min(560, Math.max(200, ev.clientX)) }
  const onUp = () => {
    document.body.style.cursor = ''
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

// ── 状态 ──
const viewMode = ref('asset')        // 'asset' 资产页 | 'run' 运行与任务监控页
const activeNodeId = ref(null)
const openedTabs = ref([])           // 打开的资产节点（v-show 保留实例，无标签栏，树行即切换）
const hoveredNodeId = ref(null)      // 树行悬停（对比任务悬停高亮纳入数据集）
const checkedDs = ref([])            // 数据集勾选（多选信息页）
const showDsSel = ref(false)         // 多选显示层（勾选与显示独立：点击行退出显示层但保留勾选）
const taskQueue = ref([])            // 任务队列（任务管理器）
const statusMsg = ref('就绪')
let taskSeq = 1

// ── 树工具 ──
function findNode(id, nodes = treeData) {
  for (const n of nodes) {
    if (n.id === id) return n
    if (n.children?.length) { const r = findNode(id, n.children); if (r) return r }
  }
  return null
}
function flattenDatasets(nodes = treeData) {
  const out = []
  for (const n of nodes) {
    if (n.type === 'dataset') out.push(n)
    if (n.children?.length) out.push(...flattenDatasets(n.children))
  }
  return out
}
const configList = computed(() => {
  const out = []
  ;(function walk(nodes) { for (const n of nodes) { if (n.type === 'config') out.push(n); if (n.children?.length) walk(n.children) } })(treeData)
  return out
})
function hasRunningAncestor(node) {
  let n = node
  while (n) { if (n.status === 'running' || n.status === 'locked') return true; n = n.parent ? findNode(n.parent) : null }
  return false
}

const activeNode = computed(() => (activeNodeId.value ? findNode(activeNodeId.value) : null))
const activeLabel = computed(() => activeNode.value?.label || '—')
const lockedBanner = computed(() => (activeNode.value ? hasRunningAncestor(activeNode.value) : false))

// ── 打开 / 关闭资产页 ──
function openTab(node) {
  if (!node) return
  const exist = openedTabs.value.find((t) => t.id === node.id)
  if (exist) activeNodeId.value = node.id
  else { openedTabs.value.push(node); activeNodeId.value = node.id }
  viewMode.value = 'asset'
}
function onNodeClick(data) {
  showDsSel.value = false       // 点击行退出多选显示层（勾选保留，独立于点击）
  openTab(data)
}

// ── 节点右键菜单（el-dropdown contextmenu 触发，现成组件自带点击外部关闭）；工作区根（空白）用固定 ctx-menu ──
const CTX_CREATE = {
  config: [{ action: 'create_derived', label: '新建配置变体' }],
  dataset: [
    { action: 'create_analysis', label: '新建统计分析' },
    { action: 'create_compare', label: '新建对比分析' },
  ],
  user_folder: [{ action: 'create_folder', label: '新建子文件夹' }],
}
const ROOT_ITEMS = [
  { action: 'new', type: 'config', label: '新建配置' },
  { action: 'new', type: 'search', label: '新建搜索任务' },
  { action: 'new', type: 'compare_task', label: '新建对比分析任务' },
  { action: 'new', type: 'user_folder', label: '新建文件夹' },
]
// 节点右键：vue3-context-menu（鼠标位置弹、点击别处自动消失、现成质感）
function onNodeCtx(e, node) {
  e.preventDefault()
  e.stopPropagation()          // 阻止冒泡到 aside 的工作区根右键
  ContextMenu.showContextMenu({ x: e.clientX, y: e.clientY, items: ctxMenuItemsFor(node) })
}
function ctxMenuItemsFor(node) {
  const items = []
  for (const c of CTX_CREATE[node.type] || []) {
    items.push({ label: c.label, onClick: () => onCtxCmd(node, c.action) })
  }
  items.push({ label: '重命名', onClick: () => renameNode(node) })
  items.push({ label: '移动到文件夹', onClick: () => { moveDlg.value = node; moveTarget.value = node.parent } })
  items.push({ divided: true, label: '删除', onClick: () => deleteNode(node) })
  return items
}
function onCtxCmd(node, action) {
  if (action === 'create_derived') createDerived(node)
  else if (action === 'create_analysis') createAnalysis(node)
  else if (action === 'create_compare') createCompareTask([node])
  else if (action === 'create_folder') createNode('user_folder', node.id)
  else if (action === 'rename') renameNode(node)
  else if (action === 'move') { moveDlg.value = node; moveTarget.value = node.parent }
  else if (action === 'delete') deleteNode(node)
}
// 工作区根（空白右键）：鼠标位置弹工作区级新建菜单
function onRootCtx(e) {
  e.preventDefault()
  ContextMenu.showContextMenu({
    x: e.clientX, y: e.clientY,
    items: ROOT_ITEMS.map((i) => ({ label: i.label, onClick: () => createNode(i.type) })),
  })
}
function renameNode(node) {
  const name = window.prompt('新名称', node.label)
  if (name && name.trim()) { node.label = name.trim(); statusMsg.value = `已重命名为：${node.label}` }
}
function deleteNode(node) {
  const parent = node.parent ? findNode(node.parent) : null
  const siblings = parent ? parent.children : treeData
  const idx = siblings.indexOf(node)
  if (idx >= 0) siblings.splice(idx, 1)
  // 级联：关闭该节点及其子孙所有已打开页面 / 勾选
  openedTabs.value = openedTabs.value.filter((t) => !isSelfOrDescendant(node, t))
  checkedDs.value = checkedDs.value.filter((d) => !isSelfOrDescendant(node, d))
  if (activeNodeId.value === node.id) activeNodeId.value = null
  statusMsg.value = `已删除：${node.label}`
}
function isSelfOrDescendant(ancestor, n) {
  if (ancestor.id === n.id) return true
  let p = n.parent ? findNode(n.parent) : null
  while (p) { if (p.id === ancestor.id) return true; p = p.parent ? findNode(p.parent) : null }
  return false
}
// 移动到文件夹：目标 = 工作区根 / user_folder / group
const moveDlg = ref(null)       // 待移动节点
const moveTarget = ref(null)    // 目标文件夹 id（null = 工作区根）
const moveFolders = computed(() => treeData.filter((n) => n.kind === 'folder' && n.id !== moveDlg.value?.id))
function confirmMove() {
  const node = moveDlg.value
  if (!node) return
  const oldParent = node.parent ? findNode(node.parent) : null
  const oldSib = oldParent ? oldParent.children : treeData
  const idx = oldSib.indexOf(node)
  if (idx >= 0) oldSib.splice(idx, 1)
  node.parent = moveTarget.value
  if (moveTarget.value) {
    const target = findNode(moveTarget.value)
    target.children = target.children || []
    target.children.push(node)
  } else {
    treeData.push(node)
  }
  const dest = moveTarget.value ? findNode(moveTarget.value).label : '工作区根'
  moveDlg.value = null
  statusMsg.value = `已移动 ${node.label} → ${dest}`
}
function onDsOpen(d) {
  showDsSel.value = false
  openTab(d)
}
function clearDsSel() { checkedDs.value = []; showDsSel.value = false }

// 工作区 props：按类型精确传（多余 attrs 不落根元素）
function workbenchProps(node) {
  if (node.type === 'analysis') return { node: node.parent ? findNode(node.parent) : node, analysisNode: node, configs: configList.value }
  if (node.type === 'dataset') return { nodes: [node], configs: configList.value }
  if (node.type === 'search') return { node, mode: 'search' }
  if (node.type === 'compare_task') return { node, allDatasets: flattenDatasets(), configs: configList.value }
  return { node }
}

// ── 节点创建（工作区 = 文件夹树：条目 = 文件，createNode 后 openTab）──
function createNode(type, parentId = null, partial = {}) {
  const parent = parentId ? findNode(parentId) : null
  const siblings = parent ? (parent.children || []) : treeData
  const n = NODE_FACTORY[type](siblings, partial, parentId)
  n.id = n.id || `${type}-${Date.now()}-${siblings.length}`
  n.parent = parentId
  n.kind = n.kind || 'file'
  n.meta = { ...(n.meta || {}), ...(partial.meta || {}) }
  n.status = n.status || 'ready'
  n.children = n.children || []
  siblings.push(n)
  openTab(n)
  statusMsg.value = `已创建${NODE_LABEL[type]}：${n.label}`
  return n
}
const NODE_LABEL = { config: '配置', search: '搜索任务', compare_task: '对比分析任务', user_folder: '文件夹', dataset: '数据集', analysis: '统计分析' }
const NODE_FACTORY = {
  config: (sib, p) => {
    const src = treeData.find((n) => n.type === 'config')
    return { label: p.label || `配置 ${sib.length + 1}`, kind: 'file', vpath: '配置/config.toml', meta: { pools: 1, maxDraws: '无限制', pity: '—', configText: src?.meta?.configText || '' } }
  },
  search: (sib, p) => ({ label: p.label || `搜索任务 ${sib.length + 1}`, kind: 'file', vpath: '搜索任务/search.json', meta: { mode: 'plan_search', refConfigId: treeData.find((n) => n.type === 'config')?.id || '', params: {} } }),
  user_folder: (sib, p) => ({ label: p.label || `文件夹 ${sib.length + 1}`, kind: 'folder', vpath: '文件夹/', meta: {} }),
  analysis: (sib, p, parentId) => ({ label: sib.length ? `统计分析 ${sib.length + 1}` : '统计分析', kind: 'file', meta: { datasetId: parentId, blocks: [] } }),
}

// 数据集：在配置下创建（模拟产物；datasetId 为后端 register_dataset 返回的缓存 id）
function createDataset(cfg, { seed, n, strategy = 'smart', datasetId = '', meanDraws = '—' }) {
  const seq = (cfg.children || []).filter((c) => c.type === 'dataset').length + 1
  const ds = {
    id: `${cfg.id}-d${seq}`, type: 'dataset', kind: 'file',
    label: `模拟 ${seq}（种子${seed} · N=${n}）`,
    parent: cfg.id, vpath: `${cfg.label}/模拟${seq}/meta.json`,
    meta: { sourceConfigId: cfg.id, seed, n, meanDraws, strategy, datasetId, createdAt: new Date().toTimeString().slice(0, 5) },
    status: 'ready', children: [],
  }
  cfg.children = cfg.children || []
  cfg.children.push(ds)
  return ds
}
// 追加统计分析条目（数据集行尾按钮 / 信息页按钮）
function createAnalysis(ds) {
  const seq = (ds.children || []).filter((c) => c.type === 'analysis').length + 1
  const a = {
    id: `${ds.id}-a${seq}`, type: 'analysis', kind: 'file',
    label: seq === 1 ? '统计分析' : `统计分析 ${seq}`,
    parent: ds.id, vpath: `${ds.label}/统计分析${seq === 1 ? '' : ` ${seq}`}.json`,
    meta: { datasetId: ds.id, blocks: [] }, status: 'ready', children: [],
  }
  ds.children = ds.children || []
  ds.children.push(a)
  openTab(a)
  statusMsg.value = '已创建统计分析条目'
}
// 派生配置：不是特别实体类型，只是挂在源配置下的普通 config 文件（meta.source 标注派生来源）
function createDerived(cfg) {
  const seq = (cfg.children || []).filter((c) => c.type === 'config').length + 1
  return createNode('config', cfg.id, { label: `变体 ${seq}`, meta: { source: '用户派生', note: '' } })
}
// 对比分析任务：工作区根多实例（可对同一数据集建多个）
function createCompareTask(datasets = []) {
  const seq = treeData.filter((n) => n.type === 'compare_task').length + 1
  const ct = {
    id: `ct${seq}`, type: 'compare_task', kind: 'file',
    label: `对比分析任务 ${seq}`, parent: null, vpath: `对比任务${seq}/对比任务.json`,
    meta: { includedDs: datasets.map((d) => d.id), excludedDs: [] }, status: 'ready', children: [],
  }
  treeData.push(ct)
  openTab(ct)
  statusMsg.value = `已创建对比分析任务（纳入 ${datasets.length} 个数据集）`
}
// 搜索完成：建配置与数据组文件夹 + 搜索结果（result = 搜索任务完成结果，真实数据）
function createSearchGroup(s, result) {
  if ((s.children || []).some((c) => c.type === 'group')) return
  const g = {
    id: `${s.id}-g`, type: 'group', kind: 'folder',
    label: '配置与数据组', parent: s.id, vpath: `${s.label}/配置与数据组/`,
    meta: { searchId: s.id }, status: 'ready', children: [],
  }
  s.children = s.children || []
  s.children.push(g)
  const r = {
    id: `${s.id}-r1`, type: 'search_result', kind: 'file', label: '搜索结果', parent: g.id,
    vpath: `${s.label}/配置与数据组/搜索结果.json`,
    meta: { searchId: s.id, mode: s.meta?.mode, result: result || null, summary: summarizeSearch(result) },
    status: 'ready', children: [],
  }
  g.children.push(r)
  statusMsg.value = '搜索完成：配置与数据组已生成'
}
// 搜索结果摘要（前端展示用）
function summarizeSearch(result) {
  if (!result) return '—'
  if (result.search_mode === 'min_resource') {
    return result.min_resource != null ? `最少额外资源 ≈ ${result.min_resource}` : '—'
  }
  if (result.search_mode === 'pareto') return `Pareto 点 ${result.pareto_points?.length ?? 0} 个`
  return `模式 ${result.search_mode} · 成功率 ${result.final_success_probability != null ? (result.final_success_probability * 100).toFixed(1) + '%' : '—'}`
}

// ── 数据集勾选（多选信息页）──
function onToggleCompare(node, val) {
  if (val) { if (!checkedDs.value.includes(node)) checkedDs.value.push(node) }
  else { checkedDs.value = checkedDs.value.filter((n) => n !== node) }
  if (checkedDs.value.length) showDsSel.value = true
  else showDsSel.value = false
}
function onCreateCompare(nodes) {
  createCompareTask(nodes)
  checkedDs.value = []
  showDsSel.value = false
}

// 分析产出新配置 → 真在工作区创建派生配置节点（挂源配置下；派生配置 = 普通 config 类型，meta.source 标注来源）
// payload: { sourceConfigId, label, note, configText }（configText 为真实 TOML 内容）
function onCreateDerived(payload) {
  const cfg = payload?.sourceConfigId ? findNode(payload.sourceConfigId) : treeData.find((n) => n.type === 'config')
  if (!cfg) return
  const seq = (cfg.children || []).filter((c) => c.type === 'config').length + 1
  const d = {
    id: `${cfg.id}-v${seq}`, type: 'config', kind: 'file',
    label: payload.label || `变体 ${seq}`, parent: cfg.id,
    vpath: `${cfg.label}/变体${seq}/config.toml`,
    meta: { source: payload.note || '分析导出', note: '', configText: payload.configText || '' },
    status: 'ready', children: [],
  }
  cfg.children = cfg.children || []
  cfg.children.push(d)
  openTab(d)
  statusMsg.value = `已生成派生配置：${d.label}`
}

// 搜索结果 → 配置：搜索结果页的通用能力（不是某个统计方法的特殊能力），
// 在搜索结果所在组（配置与数据组）下创建普通 config 节点
function onConvertSearchConfig(sr) {
  const parent = sr?.parent ? findNode(sr.parent) : null
  const dest = parent ? (parent.children || (parent.children = [])) : treeData
  const seq = dest.filter((c) => c.type === 'config').length + 1
  const cfg = {
    id: `${sr.id}-cfg${seq}`, type: 'config', kind: 'file',
    label: `搜索结果配置 ${seq}`, parent: parent ? parent.id : null,
    vpath: `搜索结果/配置${seq}/config.toml`,
    meta: { source: '搜索结果转化', note: `源自 ${sr?.label || '搜索结果'}` },
    status: 'ready', children: [],
  }
  dest.push(cfg)
  openTab(cfg)
  statusMsg.value = `已从搜索结果生成配置：${cfg.label}`
}

// ── 运行与任务监控 ──
const runTarget = computed(() => {
  const n = activeNode.value
  if (!n) return { kind: 'none', node: null }
  // 仅「配置 / 搜索任务」是可运行的生成对象；数据集/分析/文件夹/对比任务等置灰
  if (n.type === 'search') return { kind: 'search', node: n }
  if (n.type === 'config') return { kind: 'sim', node: n }
  return { kind: 'none', node: null }
})
const runKind = computed(() => runTarget.value.kind)
const runBtnLabel = computed(() => {
  if (runTarget.value.kind === 'sim') return '创建模拟任务'
  if (runTarget.value.kind === 'search') return '创建搜索任务'
  return '创建任务'
})
const runWbRef = ref(null)     // 任务管理页实例引用（工具栏按钮触发其「新建任务」对话框）
function dispatchTask() {
  // 工具栏「创建模拟任务/创建任务」：跳转任务管理界面并自动打开新建任务对话框
  // 种子 / 模拟次数等运行参数统一在此环节指定（不散落在配置页/搜索配置页）
  const t = runTarget.value
  if (!t || t.kind === 'none') return
  viewMode.value = 'run'
  statusMsg.value = `为 ${t.node.label} 新建任务…`
  nextTick(() => runWbRef.value?.openNewTask())
}
const runConfigs = computed(() => configList.value)                     // 配置/派生配置（运行对象选项）
const runSearches = computed(() => treeData.filter((n) => n.type === 'search'))  // 搜索任务
function switchRun() { viewMode.value = 'run' }

// ── 任务队列（App 持有，RunWorkbench 展示；真实派发到后端 GachaApi）──
async function onCreateTask({ type, targetId, params }) {
  const target = findNode(targetId)
  const task = reactive({
    id: `task${taskSeq++}`,
    name: `${type === 'search' ? '搜索' : '模拟'} · ${target?.label || '（未选）'}`,
    type, targetId, params,
    status: 'running', progress: 0, elapsed: 0, error: '', backendId: '', resultDataset: null,
  })
  taskQueue.value.push(task)
  try {
    if (type === 'sim') {
      const cfg = findNode(targetId)
      const configText = cfg?.meta?.configText || ''
      const r = await api.startSimulation(configText, params)
      if (!r?.ok) { task.status = 'failed'; task.error = r?.error || '派发失败'; return }
      task.backendId = r.task_id
      statusMsg.value = `已派发模拟任务：${task.name}`
    } else {
      const s = findNode(targetId)
      const refCfg = s?.meta?.refConfigId ? findNode(s.meta.refConfigId) : null
      const configText = refCfg?.meta?.configText || ''
      const r = await api.startPlanSearch(configText, params)
      if (!r?.ok) { task.status = 'failed'; task.error = r?.error || '派发失败'; return }
      task.backendId = r.task_id
      statusMsg.value = `已派发搜索任务：${task.name}`
    }
  } catch (e) {
    task.status = 'failed'
    task.error = String(e)
  }
}
function onCancelTask(task) {
  task.status = 'failed'
  task.error = '已取消'
  statusMsg.value = `${task.name} 已取消`
}
// 后端 __gscTaskDone 事件回调 → 拉取结果建节点
async function onTaskRealDone(task) {
  if (!task.backendId) return
  try {
    const r = await api.getTaskResult(task.backendId)
    if (task.type === 'sim' && r?.dataset) {
      const cfg = findNode(task.targetId)
      const reg = await api.registerDataset(r.dataset)
      const agg = r.dataset?.aggregate_data || []
      const meanDraws = agg.length
        ? Math.round(agg.reduce((a, x) => a + (x.total_draws || 0), 0) / agg.length)
        : '—'
      const ds = createDataset(cfg, {
        seed: r.dataset?.seed ?? task.params?.seed ?? 42,
        n: r.dataset?.num_simulations ?? task.params?.n ?? 0,
        strategy: r.dataset?.strategy_name || 'smart',
        datasetId: reg?.dataset_id || '',
        meanDraws,
      })
      task.resultDataset = ds
      api.saveDataset(r.dataset, ds.id) // 持久化（工作区数据集）
      statusMsg.value = `模拟完成：${task.name}，已生成数据集 ${ds.label}`
    } else if (task.type === 'search' && r?.result) {
      const s = findNode(task.targetId)
      if (s) { createSearchGroup(s, r.result); statusMsg.value = `搜索完成：${task.name}` }
    }
  } catch (e) {
    statusMsg.value = `任务结果处理失败：${e}`
  }
}
function onViewResult(task) {
  if (task.type === 'sim') {
    if (task.resultDataset) { openTab(task.resultDataset); return }
    const cfg = findNode(task.targetId)
    const last = cfg ? (cfg.children || []).filter((c) => c.type === 'dataset').at(-1) : null
    if (last) openTab(last)
  } else {
    const s = findNode(task.targetId)
    const g = s ? (s.children || []).find((c) => c.type === 'group') : null
    const r = g ? (g.children || []).find((c) => c.type === 'search_result') : null
    if (r) openTab(r)
  }
}

// ── 树行 hover：幽灵分析条目 + 对比任务悬停高亮纳入数据集 ──
function onNodeHover(data) { hoveredNodeId.value = data.id }
function onNodeLeave() { hoveredNodeId.value = null }
const hoveredNode = computed(() => (hoveredNodeId.value ? findNode(hoveredNodeId.value) : null))
const highlightDs = computed(() =>
  hoveredNode.value?.type === 'compare_task' ? (hoveredNode.value.meta.includedDs || []) : [],
)
function isHighlighted(data) { return highlightDs.value.includes(data.id) }
function isLockedNode(data) { return data.status === 'running' || data.status === 'locked' }

// ── 保存工作区（真实写入用户数据目录 workspace.json）──
async function saveWorkspace() {
  const r = await api.saveWorkspace(JSON.parse(JSON.stringify(treeData)))
  import('element-plus').then(({ ElMessage }) => {
    if (r?.ok) ElMessage.success(`工作区已保存：${r.path}`)
    else ElMessage.error(r?.error || '保存失败')
  })
}

// ── 菜单栏功能（文件/工具/帮助）──
async function onImportConfig() {
  const fp = await api.pickFile(false, ['TOML 配置文件 (*.toml)', '所有文件 (*)'])
  if (!fp?.ok || !fp.path) return
  const r = await api.importConfigFile(fp.path)
  if (r?.ok && r.text) {
    let cfg = treeData.find((n) => n.type === 'config')
    if (!cfg) cfg = await loadInitialConfig()
    if (cfg) cfg.meta.configText = r.text
    statusMsg.value = `已导入配置：${fp.path}`
  } else {
    statusMsg.value = `导入失败：${r?.error || '未知错误'}`
  }
}
async function onExportConfig() {
  const fp = await api.pickFile(true, ['TOML 配置文件 (*.toml)', '所有文件 (*)'])
  if (!fp?.ok || !fp.path) return
  const cfg = treeData.find((n) => n.type === 'config')
  if (cfg?.meta?.configText) await api.saveConfigText(cfg.meta.configText) // 同步最新文本
  const r = await api.exportConfigFile(fp.path)
  statusMsg.value = r?.ok ? `已导出配置：${fp.path}` : `导出失败：${r?.error || '未知错误'}`
}
async function onResetConfig() {
  const r = await api.resetDefaultConfig()
  if (r?.ok && r.text) {
    const cfg = treeData.find((n) => n.type === 'config')
    if (cfg) cfg.meta.configText = r.text
    statusMsg.value = '已重置为默认配置'
  } else {
    statusMsg.value = `重置失败：${r?.error || '未知错误'}`
  }
}
async function onExportResults() {
  const ds = activeNode.value?.type === 'dataset' ? activeNode.value : null
  import('element-plus').then(async ({ ElMessage }) => {
    if (!ds) { ElMessage.info('请先打开一个数据集，再导出结果'); return }
    const r = await api.loadDataset(ds.id)
    const payload = r?.dataset || { label: ds.label, meta: ds.meta }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${ds.id}.json`
    a.click()
    URL.revokeObjectURL(blob)
    ElMessage.success('已导出数据集（含全部模拟结果）')
  })
}
function onExit() {
  window.close()
}
async function togglePlugin(row) {
  const r = await api.togglePlugin(row.key, !row.disabled)
  if (r?.ok) {
    row.disabled = !row.disabled
    statusMsg.value = `${row.disabled ? '已禁用' : '已启用'}：${row.key}`
  } else {
    statusMsg.value = `操作失败：${r?.error || '未知错误'}`
  }
}

// ── 类型色 / 类型标签 ──
function typeColor(type) {
  return {
    config: '#1976d2', dataset: '#2e7d32', analysis: '#00897b',
    search: '#5c6bc0', group: '#9aa5b1', search_result: '#455a64', compare_task: '#7b1fa2',
    user_folder: '#9aa5b1',
  }[type] || '#9aa5b1'
}

// ── 启动初始化：加载真实 config + 注册任务事件 + 预渲染 ──
const aboutDlg = ref(false)
const pluginDlg = ref(false)
const aboutInfo = ref({})
const plugins = ref([])

function ensureRootFolder() {
  if (!treeData.some((n) => n.kind === 'folder')) {
    treeData.push({ id: 'uf1', type: 'user_folder', kind: 'folder', label: '我的整理', parent: null, vpath: '我的整理/', meta: {}, status: 'ready', children: [] })
  }
}

async function loadInitialConfig() {
  // 等待 pywebview 桥就绪（注入晚于 Vue mount 时重试，最多 5 秒）
  for (let i = 0; i < 20; i++) {
    const r = await api.loadConfigText()
    if (r?.ok && r.text) {
      const meta = await api.getConfigMeta()
      const cfg = {
        id: 'c1', type: 'config', kind: 'file', label: '默认配置', parent: null,
        vpath: '默认配置/config.toml',
        meta: {
          configText: r.text,
          pools: meta?.banners?.length ?? 0,
          maxDraws: '—',
          pity: `目标卡 ${meta?.targets?.length ?? 0}`,
        },
        status: 'ready', children: [],
      }
      treeData.push(cfg)
      return cfg
    }
    await new Promise((res) => setTimeout(res, 250))
  }
  return null
}

onMounted(async () => {
  // 后端任务事件 → 更新任务队列 + 建节点（按 backendId 匹配：前端 task.id 与后端 task_id 不同）
  onTaskProgress((p) => {
    const t = taskQueue.value.find((x) => x.backendId === p.taskId)
    if (t) { t.progress = p.pct ?? 0; t.elapsed = (t.elapsed || 0) + 0.3 }
  })
  onTaskDone((p) => {
    const t = taskQueue.value.find((x) => x.backendId === p.taskId)
    if (t) {
      t.status = p.ok ? 'done' : 'failed'
      t.progress = 100
      if (!p.ok) t.error = p.error
      onTaskRealDone(t)
    }
  })
  await loadInitialConfig()
  ensureRootFolder()
  const about = await api.getAboutInfo()
  if (about?.ok) aboutInfo.value = about
  const pl = await api.listPlugins()
  if (pl?.ok) plugins.value = pl.plugins

  // 启动后预渲染：首帧后挂载第一个配置页（v-show 隐藏），点击立即显示。
  const firstCfg = treeData.find((n) => n.type === 'config')
  if (firstCfg && !openedTabs.value.some((t) => t.id === firstCfg.id)) {
    setTimeout(() => { openedTabs.value.push(firstCfg) }, 300)
  }
})
</script>

<style scoped>
.app-shell {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* ── 顶部：菜单栏 + 工具栏（两行）── */
.app-header {
  display: flex;
  flex-direction: column;
  align-items: stretch;  /* 覆盖 base.css 旧单行 .app-header 的 align-items:center（否则两行子元素被水平居中）*/
  height: auto;          /* 覆盖 base.css 旧固定 height:32px（否则两行子元素被 flex 压缩截断）*/
  flex-shrink: 0;
  background: var(--gsc-bg-header);
  border-bottom: 1px solid var(--gsc-border);
}
/* 第一行：菜单栏（GachaStat 标题 + 文件/工具/帮助），全部左对齐 */
.menu-bar {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  height: 28px;
  padding: 0 8px;
  border-bottom: 1px solid var(--gsc-border);
}
/* 第二行：工具栏（新建 + 运行），新建左对齐、任务按钮右对齐 */
.tool-bar {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 4px;
  height: 32px;
  padding: 0 8px;
}
.tb-spacer {
  flex: 1;
}
.app-brand {
  font-weight: 700;
  font-size: 13px;
  letter-spacing: 0.5px;
}
.app-menus {
  display: flex;
  gap: 2px;
}
.menu-btn {
  display: inline-block;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 12px;
  user-select: none;
}
.menu-btn:hover {
  background: var(--gsc-bg-result);
}

/* ── 主体 ── */
.app-body {
  flex: 1;
  display: flex;
  min-height: 0;
}

/* 左：工作区树 */
.asset-tree {
  flex: 0 0 auto;
  background: var(--gsc-bg-panel);
  overflow: auto;
}
/* 资产树 / 工作区 拖拽分割线 */
.tree-splitter {
  flex: 0 0 5px;
  cursor: col-resize;
  background: var(--gsc-border);
  user-select: none;
}
.tree-splitter:hover {
  background: var(--el-color-primary);
}
.tree-head {
  padding: 6px 10px;
  font-size: 11px;
  color: var(--gsc-text-muted);
  font-weight: 600;
  border-bottom: 1px solid var(--gsc-border);
}
.move-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.tree-node-wrap {
  display: flex;
  flex-direction: column;
}
/* 行尾快捷创建分析（dataset）：常驻小按钮，不占独立行 */
.add-analysis-btn {
  margin-left: auto;
  flex-shrink: 0;
  height: 18px;
  padding: 0 4px;
  font-size: 11px;
}
.tree-node {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
}
.tree-node.node-locked {
  opacity: 0.55;
}
/* 对比任务悬停高亮：纳入的数据集行浅绿底 + 主色竖条（与 ConfigWorkbench 定位高亮同语言） */
.tree-node.tree-hl {
  background: var(--el-color-success-light-9);
  box-shadow: inset 3px 0 0 var(--el-color-success);
}
.folder-ico {
  flex-shrink: 0;
  font-size: 12px;
}
.type-mark {
  width: 5px;
  height: 5px;
  flex-shrink: 0;
}
.tree-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 2px;
  flex-shrink: 0;
}
.status-badge.running {
  background: #e3f2fd;
  color: var(--el-color-primary);
}
.status-badge.locked {
  background: #eceff1;
  color: var(--gsc-text-muted);
}
/* 数据集比较勾选：独立小元素，点击不触发行打开 */
.cmp-check {
  --el-checkbox-size: 13px;
  margin-right: -2px;
}

/* 右：工作区 */
.workbench {
  flex: 1;
  min-width: 0;
  background: var(--gsc-bg);
  overflow: hidden;
  padding: 8px;
  display: flex;
  flex-direction: column;
}
.lock-banner {
  margin-bottom: 8px;
  flex-shrink: 0;
}
.ds-sel-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  margin-bottom: 8px;
  border: 1px solid var(--gsc-border);
  background: #e8f5e9;
  font-size: 12px;
}
.ds-sel-label {
  font-weight: 600;
  color: var(--el-color-success);
}

/* 底部状态栏 */
.app-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 24px;
  padding: 0 8px;
  background: var(--gsc-bg-header);
  border-top: 1px solid var(--gsc-border);
  font-size: 11px;
  flex-shrink: 0;
}
</style>
