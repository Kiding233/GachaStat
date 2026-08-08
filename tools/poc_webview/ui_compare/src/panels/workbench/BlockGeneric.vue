<template>
  <div class="cfg-block" :class="{ open: expanded }">
    <!-- 块头：折叠 + 类型 + 全局徽标 + 名称 + 复制/删除 -->
    <div class="cfg-block-head" @click="expanded = !expanded">
      <span class="drag-handle" @click.stop title="拖拽排序">⠿</span>
      <span class="arrow">{{ expanded ? '▾' : '▸' }}</span>
      <span class="block-type">{{ meta.label }}</span>
      <span v-if="meta.global" class="global-badge">全局</span>
      <span class="block-name">{{ title }}</span>
      <div class="block-ops" @click.stop>
        <el-button size="small" text title="定位到配置文本" @click="$emit('locate')">定位</el-button>
        <el-dropdown trigger="click" @command="$emit('move', $event)">
          <el-button size="small" text title="移动到页">移至</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="p in pages" :key="p.id" :command="p.id">{{ p.name }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button v-if="copyable" size="small" text @click="$emit('copy')">复制</el-button>
        <el-button size="small" text type="danger" @click="$emit('remove')">删除</el-button>
      </div>
    </div>

    <div v-show="expanded" class="cfg-block-body">
      <!-- ══ 资源块：条目表（可多条、复制去重）══ -->
      <template v-if="type === 'resource'">
        <el-table :data="data.entries" size="small">
          <el-table-column label="资源 ID" min-width="140">
            <template #default="{ row }"><el-input v-model="row.key" size="small" /></template>
          </el-table-column>
          <el-table-column label="定义名" min-width="140">
            <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
          </el-table-column>
          <el-table-column label="初始数量" width="120">
            <template #default="{ row }">
              <el-input-number v-model="row.initial" size="small" :min="0" :controls="false" style="width: 100px" />
            </template>
          </el-table-column>
          <el-table-column width="150" align="center">
            <template #default="{ row }">
              <el-button size="small" text @click="copyEntry(row)">复制</el-button>
              <el-button size="small" text type="danger" @click="removeEntry(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" class="sub-btn" @click="addEntry">+ 添加资源</el-button>
      </template>

      <!-- ══ 卡片/权重/目标卡：聚合条目表格（每行一个条目，字段塞一行）══ -->
      <template v-else-if="isTableType">
        <el-table :data="data.entries" size="small">
          <el-table-column v-for="col in entryCols" :key="col.key" :label="col.label" :min-width="col.minWidth">
            <template #default="{ row }">
              <el-input v-if="col.type === 'text'" v-model="row[col.key]" size="small" />
              <el-input-number
                v-else-if="col.type === 'number'"
                :model-value="row[col.key]"
                size="small"
                :precision="col.precision"
                :controls="false"
                style="width: 100%"
                @change="(v) => (row[col.key] = v)"
              />
              <el-select
                v-else-if="col.type === 'array'"
                :model-value="row[col.key] || []"
                size="small"
                multiple
                filterable
                allow-create
                default-first-option
                style="width: 100%"
                @change="(v) => (row[col.key] = v)"
              >
                <el-option v-for="pid in poolIds" :key="pid" :label="pid" :value="pid" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column width="130" align="center">
            <template #default="{ row }">
              <el-button size="small" text @click="copyEntryRow(row)">复制</el-button>
              <el-button size="small" text type="danger" @click="removeEntryRow(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" class="sub-btn" @click="addEntryRow">+ 添加{{ meta.label }}</el-button>
      </template>

      <!-- ══ 稀有度块：层级标签编辑（el-select 多选 + 输入即添加）══ -->
      <template v-else-if="type === 'rarity'">
        <div class="sub-title">稀有度层级（高→低）</div>
        <div v-for="(rank, ri) in data.ranks" :key="ri" class="rank-row">
          <span class="rank-order">第 {{ ri + 1 }} 级</span>
          <el-select
            :model-value="rank"
            size="small"
            multiple
            filterable
            allow-create
            default-first-option
            class="rank-sel"
            placeholder="输入名称回车添加"
            @change="(v) => (data.ranks[ri] = v)"
          >
            <el-option v-for="n in rank" :key="n" :label="n" :value="n" />
          </el-select>
          <el-button size="small" text type="danger" title="删除该级" @click="data.ranks.splice(ri, 1)">×</el-button>
        </div>
        <el-button size="small" class="sub-btn" @click="data.ranks.push([])">+ 添加层级</el-button>
      </template>

      <!-- ══ 保底块：纵向逐行（保持逻辑链），按语义分组紧凑 ══ -->
      <template v-else-if="type === 'pity'">
        <div class="pity-groups">
          <div v-for="g in pityGroups" :key="g.key" class="pity-group">
            <div class="pity-group-title">{{ g.title }}</div>
            <div v-for="f in g.fields" :key="f.key" class="pity-row">
              <span class="pity-label">{{ f.label }}</span>
              <div class="pity-ctl">
                <el-input v-if="f.type === 'text'" v-model="data[f.key]" size="small" />
                <el-input-number
                  v-else-if="f.type === 'number'"
                  :model-value="data[f.key]"
                  size="small"
                  :min="f.min ?? 0"
                  :precision="f.precision"
                  :controls="false"
                  class="pity-num"
                  @change="(v) => (data[f.key] = v)"
                />
                <el-switch v-else-if="f.type === 'bool'" :model-value="!!data[f.key]" size="small" @change="(v) => (data[f.key] = v)" />
                <el-select v-else-if="f.type === 'select'" v-model="data[f.key]" size="small" allow-create filterable class="pity-sel">
                  <el-option v-for="o in f.options" :key="o" :label="o" :value="o" />
                </el-select>
                <el-select
                  v-else-if="f.type === 'array'"
                  :model-value="data[f.key] || []"
                  size="small"
                  multiple
                  filterable
                  allow-create
                  default-first-option
                  class="pity-arr"
                  @change="(v) => (data[f.key] = v)"
                />
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- ══ 其他块（累抽/策略等）：类型化字段表单，纵向逐行保持逻辑 ══ -->
      <template v-else>
        <el-form label-width="84px" size="small" class="block-form">
          <el-form-item v-for="f in fields" :key="f.key" :label="f.label">
            <!-- 文本 -->
            <el-input v-if="f.type === 'text'" v-model="data[f.key]" size="small" />
            <!-- 数字 -->
            <el-input-number
              v-else-if="f.type === 'number'"
              :model-value="data[f.key]"
              size="small"
              :min="f.min ?? 0"
              :precision="f.precision"
              :controls="false"
              style="width: 140px"
              @change="(v) => (data[f.key] = v)"
            />
            <!-- 布尔 -->
            <el-switch
              v-else-if="f.type === 'bool'"
              :model-value="!!data[f.key]"
              size="small"
              @change="(v) => (data[f.key] = v)"
            />
            <!-- 下拉 -->
            <el-select v-else-if="f.type === 'select'" v-model="data[f.key]" size="small" allow-create filterable style="width: 200px">
              <el-option v-for="o in f.options" :key="o" :label="o" :value="o" />
            </el-select>
            <!-- 字符串数组 -->
            <el-select
              v-else-if="f.type === 'array'"
              :model-value="data[f.key] || []"
              size="small"
              multiple
              filterable
              allow-create
              default-first-option
              style="width: 100%"
              @change="(v) => (data[f.key] = v)"
            />
          </el-form-item>
        </el-form>
      </template>

      <!-- ══ pity 特化：生命周期 + 未渲染参数 ══ -->
      <div v-if="type === 'pity' && data.lifecycle" class="sub-section">
        <div class="sub-title">保底生命周期</div>
        <el-form label-width="120px" size="small">
          <el-form-item label="提前出货停用">
            <el-switch :model-value="!!data.lifecycle.deactivate_on_early_hit" size="small" @change="(v) => (data.lifecycle.deactivate_on_early_hit = v)" />
          </el-form-item>
          <el-form-item label="依赖行为">
            <el-input v-model="data.lifecycle.depends_on" size="small" placeholder="依赖的 behavior 名" />
          </el-form-item>
        </el-form>
      </div>
      <div v-if="pityExtraKeys.length" class="sub-section">
        <div class="sub-title">其他参数（该保底类型专用，展开只读）</div>
        <pre class="extra-json">{{ JSON.stringify(pityExtra, null, 2) }}</pre>
      </div>

      <!-- ══ milestone 特化：bonus_reward ══ -->
      <div v-if="type === 'milestone'" class="sub-section">
        <div class="sub-title">奖励（bonus_reward）</div>
        <el-form label-width="84px" size="small">
          <el-form-item label="固定卡牌">
            <el-select
              :model-value="data.bonus_reward.cards || []"
              size="small"
              multiple
              filterable
              allow-create
              default-first-option
              style="width: 100%"
              @change="(v) => (data.bonus_reward.cards = v)"
            />
          </el-form-item>
          <el-form-item label="赠送资源">
            <div class="kv-editor">
              <div v-for="(val, k) in data.bonus_reward.resources" :key="k" class="kv-row">
                <el-input :model-value="k" size="small" class="kv-key" @change="(nk) => renameResource(k, nk)" />
                <el-input-number :model-value="val" size="small" class="kv-val" :controls="false" @change="(nv) => (data.bonus_reward.resources[k] = nv)" />
                <el-button size="small" text type="danger" @click="removeResource(k)">×</el-button>
              </div>
              <div class="kv-row">
                <el-input v-model="newResKey" size="small" class="kv-key" placeholder="资源 ID" />
                <el-input-number v-model="newResVal" size="small" class="kv-val" :controls="false" />
                <el-button size="small" text type="primary" @click="addResource">+</el-button>
              </div>
            </div>
          </el-form-item>
          <el-form-item label="随机卡">
            <span class="muted">{{ data.bonus_reward.random_cards.length }} 个候选池（展开只读）</span>
          </el-form-item>
        </el-form>
        <pre v-if="data.bonus_reward.random_cards.length" class="extra-json">{{ JSON.stringify(data.bonus_reward.random_cards, null, 2) }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  type: { type: String, required: true },
  data: { type: Object, required: true },
  copyable: { type: Boolean, default: true },
  pages: { type: Array, default: () => [] },
  poolIds: { type: Array, default: () => [] },   // 全限定池 ID（{banner}.{pool}），供目标卡关联池下拉
})
const emit = defineEmits(['copy', 'remove', 'change', 'locate', 'move'])

// 快照比较：只在值真正变化时 emit，打破双向同步死循环（与 ConfigBlock 同模式）
let lastSnap = JSON.stringify(props.data)
watch(() => props.data, (val) => {
  const snap = JSON.stringify(val)
  if (snap !== lastSnap) {
    lastSnap = snap
    emit('change')
  }
}, { deep: true })

// 块默认展开。初次打开配置页的渲染开销由 App 启动后预渲染消除。
const expanded = ref(true)

const META = {
  resource:  { label: '资源',     global: true },
  card:      { label: '卡片',     global: false },
  pity:      { label: '保底规则', global: false },
  milestone: { label: '累抽奖励', global: false },
  target:    { label: '目标卡',   global: false },
  weight:    { label: '权重',     global: false },
  rarity:    { label: '稀有度层级', global: true },
  strategy:  { label: '策略',     global: true },
  search_meta:     { label: '搜索信息',   global: false },
  search_target:   { label: '搜索目标',   global: false },
  search_start:    { label: '起始状态',   global: false },
  search_strategy: { label: '策略',       global: false },
  search_scan:     { label: '扫描参数',   global: false },
}
const meta = computed(() => META[props.type] || { label: props.type, global: false })

const title = computed(() => {
  const d = props.data
  if (props.type === 'resource') {
    const n = (d.entries || []).length
    return n ? `${n} 种资源` : '未命名'
  }
  if (isTableType.value) return `${(d.entries || []).length} 条`
  if (props.type === 'rarity') return `${(d.ranks || []).length} 级稀有度`
  return d.name || d.card_id || d.key || '未命名'
})

// ── 聚合条目表（卡片/权重/目标卡）──
const TABLE_TYPES = ['card', 'weight', 'target']
const isTableType = computed(() => TABLE_TYPES.includes(props.type))
const ENTRY_COLS = {
  card: [
    { key: 'card_id', label: '卡ID', type: 'text', minWidth: 140 },
    { key: 'name', label: '名称', type: 'text', minWidth: 110 },
    { key: 'rarity', label: '稀有度', type: 'text', minWidth: 80 },
    { key: 'initial_count', label: '初始持有', type: 'number', minWidth: 100 },
  ],
  weight: [
    { key: 'card_id', label: '卡ID', type: 'text', minWidth: 140 },
    { key: 'desire', label: '期望', type: 'number', minWidth: 90, precision: 2 },
    { key: 'miss_cost', label: '未命中代价', type: 'number', minWidth: 110, precision: 2 },
    { key: 'card_value', label: '价值', type: 'number', minWidth: 90, precision: 2 },
  ],
  target: [
    { key: 'card_id', label: '目标卡', type: 'text', minWidth: 140 },
    { key: 'quantity', label: '数量', type: 'number', minWidth: 90 },
    { key: 'pool_ids', label: '关联池', type: 'array', minWidth: 180 },
  ],
}
const entryCols = computed(() => ENTRY_COLS[props.type] || [])
function addEntryRow() {
  const d = {
    card: { card_id: '', name: '', rarity: 'r', initial_count: 0 },
    weight: { card_id: '', desire: 1, miss_cost: 1, card_value: 1 },
    target: { card_id: '', quantity: 1, pool_ids: [] },
  }[props.type]
  props.data.entries.push(d)
}
function copyEntryRow(row) {
  const copy = { ...row, card_id: (row.card_id || '') + '_copy' }
  if (props.data.entries.some((e) => e.card_id === copy.card_id)) copy.card_id += `_${props.data.entries.length}`
  props.data.entries.push(copy)
}
function removeEntryRow(row) {
  props.data.entries.splice(props.data.entries.indexOf(row), 1)
}

// ── 字段描述（按块类型；类型化渲染）──
const PITY_TYPES = ['soft_interval', 'soft_additive', 'soft_step', 'hard', 'rotating', 'rotating_soft', 'rotating_cr', 'rotating_cr_soft', 'targeted', 'targeted_soft']
// 内置策略 key（strategies/builtin/ 注册，P69）
const STRATEGY_KEYS = ['smart', 'draw_target', 'target_hunting', 'stop_on_target', 'pity_reserve', 'pool_quota', 'fixed_count', 'no_draw']
const FIELDS = {
  card: [
    { key: 'card_id', label: '卡ID', type: 'text' },
    { key: 'name', label: '名称', type: 'text' },
    { key: 'rarity', label: '稀有度', type: 'text' },
    { key: 'initial_count', label: '初始持有', type: 'number' },
  ],
  weight: [
    { key: 'card_id', label: '卡ID', type: 'text' },
    { key: 'desire', label: '期望值', type: 'number', precision: 2 },
    { key: 'miss_cost', label: '未命中代价', type: 'number', precision: 2 },
    { key: 'card_value', label: '卡牌价值', type: 'number', precision: 2 },
  ],
  target: [
    { key: 'card_id', label: '目标卡', type: 'text' },
    { key: 'quantity', label: '数量', type: 'number' },
    { key: 'pool_ids', label: '关联池', type: 'array' },
  ],
  pity: [
    { key: 'name', label: '名称', type: 'text' },
    { key: 'type', label: '类型', type: 'select', options: PITY_TYPES },
    { key: 'scope', label: '稀有度', type: 'select', options: ['ssr', 'sr', 'r'] },
    { key: 'target_featured', label: '仅限 Featured', type: 'bool' },
    { key: 'reset', label: '重置条件', type: 'text' },
    { key: 'start', label: '起始水位', type: 'number' },
    { key: 'end', label: '结束水位', type: 'number' },
    { key: 'threshold', label: '阈值', type: 'number' },
    { key: 'counter_init', label: '初始计数', type: 'number' },
    { key: 'pools', label: '绑定池', type: 'array' },
  ],
  milestone: [
    { key: 'name', label: '名称', type: 'text' },
    { key: 'threshold', label: '触发阈值', type: 'number' },
    { key: 'repeat', label: '可重复', type: 'bool' },
    { key: 'max_triggers', label: '最大触发', type: 'number' },
    { key: 'banner', label: '适用 Banner', type: 'text' },
  ],
  strategy: [
    { key: 'key', label: '策略键', type: 'select', options: STRATEGY_KEYS },
  ],
  // 搜索配置块（左文本右块与一般配置一致，块集合不同）
  search_meta: [
    { key: 'name', label: '名称', type: 'text' },
    { key: 'mode', label: '模式', type: 'select', options: ['plan_search', 'sensitivity'] },
    { key: 'ref_config', label: '引用配置', type: 'select', options: ['c1', 'c2'] },
  ],
  search_target: [
    { key: 'goal', label: '搜索目标', type: 'select', options: ['min_resource', 'max_target', 'pareto', 'retreat'] },
  ],
  search_start: [
    { key: 'budget', label: '起始资源', type: 'number' },
    { key: 'seed', label: '种子', type: 'number' },
  ],
  search_strategy: [
    { key: 'key', label: '策略键', type: 'select', options: STRATEGY_KEYS },
  ],
  search_scan: [
    { key: 'param', label: '扫描参数', type: 'text' },
    { key: 'min', label: '最小值', type: 'number' },
    { key: 'max', label: '最大值', type: 'number' },
    { key: 'step', label: '步长', type: 'number' },
    { key: 'metric', label: '目标指标', type: 'text' },
  ],
}
const fields = computed(() => FIELDS[props.type] || [])

// 保底字段按语义分组（纵向逐行，逻辑链保持）；参数按 type 动态显隐：
//   hard → 阈值；soft_* → 起始/结束水位；事件驱动（rotating/targeted）→ 均不显示（参数在 _extra）
const pityGroups = computed(() => {
  const t = props.data.type
  const visible = (key) => {
    if (key === 'threshold') return t === 'hard'
    if (key === 'start' || key === 'end') return ['soft_interval', 'soft_additive', 'soft_step'].includes(t)
    return true
  }
  const byKey = Object.fromEntries(FIELDS.pity.map((f) => [f.key, f]))
  return [
    { key: 'def', title: '定义', fields: ['name', 'type', 'scope'].map((k) => byKey[k]).filter(Boolean) },
    { key: 'param', title: '规则参数', fields: ['target_featured', 'reset', 'start', 'end', 'threshold', 'counter_init'].filter(visible).map((k) => byKey[k]).filter(Boolean) },
    { key: 'scope', title: '作用范围', fields: ['pools'].map((k) => byKey[k]).filter(Boolean) },
  ]
})

// ── 资源块条目操作（key 去重）──
function addEntry() {
  const entries = props.data.entries
  let idx = 1
  while (entries.some((e) => e.key === `resource_${idx}`)) idx++
  entries.push({ key: `resource_${idx}`, name: '', initial: 0 })
}
function copyEntry(row) {
  const copy = { ...row }
  copy.key = row.key + '_copy'
  if (props.data.entries.some((e) => e.key === copy.key)) copy.key += `_${props.data.entries.length}`
  props.data.entries.push(copy)
}
function removeEntry(row) {
  props.data.entries.splice(props.data.entries.indexOf(row), 1)
}

// ── milestone：resources KV 编辑 ──
const newResKey = ref('')
const newResVal = ref(1)
function addResource() {
  const k = newResKey.value.trim()
  if (!k) return
  props.data.bonus_reward.resources[k] = newResVal.value
  newResKey.value = ''
  newResVal.value = 1
}
function removeResource(k) {
  delete props.data.bonus_reward.resources[k]
}
function renameResource(oldKey, newKey) {
  if (newKey && newKey !== oldKey) {
    props.data.bonus_reward.resources[newKey] = props.data.bonus_reward.resources[oldKey]
    delete props.data.bonus_reward.resources[oldKey]
  }
}

// ── pity 未建模参数（已建模字段之外，只读展示；序列化时由 configToml.extraToml 写回）──
const PITY_KNOWN = new Set(['name', 'type', 'scope', 'target_featured', 'threshold', 'reset', 'start', 'end', 'counter_init', 'pools', 'lifecycle'])
const pityExtra = computed(() => {
  if (props.type !== 'pity') return {}
  const o = {}
  for (const [k, v] of Object.entries(props.data)) {
    if (!PITY_KNOWN.has(k) && v !== undefined && v !== null && v !== '') o[k] = v
  }
  return o
})
const pityExtraKeys = computed(() => Object.keys(pityExtra.value))
</script>

<style scoped>
.cfg-block {
  border: 1px solid var(--gsc-border);
  background: var(--gsc-bg-panel);
  box-shadow: var(--gsc-shadow);
}
.cfg-block.open {
  border-color: var(--gsc-border);
}
.cfg-block-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  cursor: pointer;
  user-select: none;
  background: var(--gsc-bg-header);
  border-bottom: 1px solid var(--gsc-border);
  font-size: 12px;
}
.cfg-block-head:hover {
  background: var(--gsc-bg-result);
}
.arrow {
  font-size: 11px;
  color: var(--gsc-text-muted);
  width: 14px;
  text-align: center;
}
.drag-handle {
  cursor: move;
  color: var(--gsc-text-faint);
  font-size: 12px;
  user-select: none;
}
.drag-handle:hover {
  color: var(--gsc-text-muted);
}
.block-type {
  font-weight: 700;
  color: var(--el-color-primary);
  font-size: 11px;
  letter-spacing: 0.5px;
}
.global-badge {
  font-size: 10px;
  padding: 1px 6px;
  background: #e3f2fd;
  color: var(--el-color-primary);
  border-radius: 2px;
}
.block-name {
  font-weight: 600;
}
.block-ops {
  margin-left: auto;
  display: flex;
  gap: 2px;
}
.cfg-block-body {
  padding: 8px;
}
/* 嵌套子块 = 标题栏面板（QGroupBox 形态）：完整边框 + 标题栏 + 主色竖条 */
.sub-section {
  margin-top: 6px;
  border: 1px solid var(--gsc-border);
  background: #fafbfc;
  padding: 6px 8px;
}
.sub-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: -6px -8px 6px;
  padding: 3px 8px;
  background: var(--gsc-bg-header);
  border-bottom: 1px solid var(--gsc-border);
  font-size: 11px;
  color: var(--gsc-text-muted);
  font-weight: 600;
}
.sub-title::before {
  content: '';
  width: 3px;
  height: 11px;
  background: var(--el-color-primary);
  flex-shrink: 0;
}
.sub-btn {
  margin-top: 6px;
}
.extra-json {
  margin: 6px 0 0 0;
  padding: 6px;
  background: #fafbfc;
  border: 1px solid var(--gsc-border);
  font-family: var(--gsc-font-mono);
  font-size: 11px;
  max-height: 160px;
  overflow: auto;
}
/* 保底块：纵向逐行（逻辑链保持），按语义分组紧凑 */
.pity-group {
  margin-bottom: 6px;
}
.pity-group-title {
  font-size: 11px;
  color: var(--gsc-text-muted);
  margin-bottom: 3px;
}
.pity-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
}
.pity-label {
  flex-shrink: 0;
  width: 76px;
  font-size: 12px;
  color: var(--gsc-text-muted);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pity-ctl {
  flex: 1;
  min-width: 0;
  display: flex;
}
.pity-num {
  width: 120px;
}
.pity-sel {
  width: 180px;
}
.pity-arr {
  flex: 1;
  min-width: 0;
}
.rank-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.rank-order {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--gsc-text-muted);
  width: 48px;
}
.rank-sel {
  flex: 1;
  min-width: 0;
}
.kv-editor {
  flex: 1;
  min-width: 0;
}
.kv-row {
  display: flex;
  gap: 4px;
  margin-bottom: 4px;
  align-items: center;
}
.kv-key {
  flex: 1;
  min-width: 0;
}
.kv-val {
  width: 110px;
}
</style>
