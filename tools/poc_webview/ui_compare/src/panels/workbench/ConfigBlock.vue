<template>
  <div class="cfg-block" :class="{ open: expanded }">
    <!-- 块头：折叠 + 类型 + 名称 + 复制/删除 -->
    <div class="cfg-block-head" @click="expanded = !expanded">
      <span class="drag-handle" @click.stop title="拖拽排序">⠿</span>
      <span class="arrow">{{ expanded ? '▾' : '▸' }}</span>
      <span class="block-type">Banner</span>
      <span class="block-name">{{ data.name || '未命名' }}</span>
      <span class="muted block-id">{{ data.id }}</span>
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
        <el-button size="small" text @click="$emit('copy')">复制</el-button>
        <el-button size="small" text type="danger" @click="$emit('remove')">删除</el-button>
      </div>
    </div>

    <div v-show="expanded" class="cfg-block-body">
      <!-- 结构化表单（对齐真实 config.toml 字段：id/name/enabled/max_draws/start_day/end_day，纵向逐行保持逻辑）-->
      <el-form label-width="76px" size="small">
        <el-form-item label="名称"><el-input v-model="data.name" size="small" /></el-form-item>
        <el-form-item label="ID"><el-input v-model="data.id" size="small" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="enabled" size="small" /></el-form-item>
        <el-form-item label="最大抽数">
          <el-input-number v-model="data.max_draws" :min="0" :controls="false" size="small" style="width: 120px" />
          <span class="muted">0=无限</span>
        </el-form-item>
        <el-form-item label="起始日">
          <el-input-number v-model="data.start_day" :min="0" :controls="false" size="small" style="width: 120px" />
        </el-form-item>
        <el-form-item label="结束日">
          <el-input-number v-model="data.end_day" :min="0" :controls="false" size="small" style="width: 120px" />
        </el-form-item>
      </el-form>

      <!-- 池子子块（块内操作添加）——表 + 选中池的奖励子表 -->
      <div class="sub-section">
        <div class="sub-title">池子（{{ data.pools.length }}）</div>
        <el-table :data="data.pools" size="small" highlight-current-row @current-change="onPoolSelect">
          <el-table-column label="ID" min-width="90">
            <template #default="{ row }"><el-input v-model="row.id" size="small" /></template>
          </el-table-column>
          <el-table-column label="成本" min-width="130">
            <template #default="{ row }"><el-input v-model="row.cost" size="small" placeholder="draw_resource:160" /></template>
          </el-table-column>
          <el-table-column label="批次" width="60">
            <template #default="{ row }">
              <el-input-number v-model="row.batch_size" :min="1" size="small" controls-position="right" />
            </template>
          </el-table-column>
          <el-table-column label="最大抽数" width="92">
            <template #default="{ row }">
              <el-input-number v-model="row.max_draws" :min="0" :controls="false" size="small" style="width: 70px" />
            </template>
          </el-table-column>
          <el-table-column label="不计保底" width="76" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.excludes_all_pity" />
            </template>
          </el-table-column>
          <el-table-column label="一次性" width="110">
            <template #default="{ row }">
              <el-input v-model="row.exchange_card_id" size="small" placeholder="卡 ID" />
            </template>
          </el-table-column>
          <el-table-column label="奖励" width="60" align="center">
            <template #default="{ row }">
              <span class="muted">{{ row.rewards.length }} 条</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="64" align="center">
            <template #default="{ row }">
              <el-button size="small" text type="danger" @click="removePool(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" class="sub-btn" @click="addPool">+ 添加池子</el-button>

        <!-- 选中池的奖励分布（嵌套子块）-->
        <div v-if="selectedPool" class="inner-sub">
          <div class="sub-title">池「{{ selectedPool.id || '未命名' }}」的奖励分布（{{ selectedPool.rewards.length }}）</div>
          <el-table :data="selectedPool.rewards" size="small">
            <el-table-column label="卡ID" min-width="150">
              <template #default="{ row }"><el-input v-model="row.card_id" size="small" /></template>
            </el-table-column>
            <el-table-column label="概率(%)" width="110">
              <template #default="{ row }">
                <el-input-number v-model="row.probability" size="small" :precision="4" :min="0" :controls="false" style="width: 90px" />
              </template>
            </el-table-column>
            <el-table-column label="稀有度" width="100">
              <template #default="{ row }">
                <el-select v-model="row.rarity" size="small">
                  <el-option label="ssr" value="ssr" />
                  <el-option label="sr" value="sr" />
                  <el-option label="r" value="r" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="Featured" width="80">
              <template #default="{ row }">
                <el-checkbox v-model="row.featured" />
              </template>
            </el-table-column>
            <el-table-column label="资源获取" min-width="150">
              <template #default="{ row }">
                <el-input
                  :model-value="resGainedText(row)"
                  size="small"
                  placeholder="res:num, res:num"
                  @change="(v) => parseResGained(row, v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="64" align="center">
              <template #default="{ row }">
                <el-button size="small" text type="danger" @click="removeReward(selectedPool, row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button size="small" class="sub-btn" @click="addReward(selectedPool)">+ 添加奖励</el-button>
        </div>
      </div>

      <!-- 生命周期子块（嵌套子结构，Banner 内操作添加）-->
      <div class="sub-section">
        <div class="sub-title">生命周期（{{ data.lifecycle.length }}）</div>
        <el-table :data="data.lifecycle" size="small">
          <el-table-column label="关联池" width="130">
            <template #default="{ row }">
              <el-select v-model="row.pool" size="small" allow-create filterable placeholder="pool id">
                <el-option v-for="p in ownPoolIds" :key="p" :label="p" :value="p" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="条件" width="150">
            <template #default="{ row }">
              <el-select v-model="row.condition" size="small">
                <el-option v-for="c in CONDITIONS" :key="c" :label="c" :value="c" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="阈值" width="110">
            <template #default="{ row }">
              <el-input-number v-model="row.at" size="small" :min="0" :precision="0" :controls="false" style="width: 90px" />
            </template>
          </el-table-column>
          <el-table-column v-if="isCardObtainedLife" label="匹配" width="120">
            <template #default="{ row }">
              <el-select v-model="row.match" size="small">
                <el-option label="card_id" value="card_id" />
                <el-option label="rarity" value="rarity" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="动作" width="140">
            <template #default="{ row }">
              <el-select v-model="row.action" size="small">
                <el-option v-for="a in ACTIONS" :key="a" :label="a" :value="a" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="目标" min-width="100">
            <template #default="{ row }"><el-input v-model="row.target" size="small" placeholder="pool / banner" /></template>
          </el-table-column>
          <el-table-column width="70" align="center">
            <template #default="{ row }">
              <el-button size="small" text type="danger" @click="removeLifecycle(row)">×</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" class="sub-btn" @click="addLifecycle">+ 添加生命周期规则</el-button>
      </div>

      <!-- 块↔文本对应：块头「定位」按钮 → 左文本跳转并闪烁高亮 -->
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({ data: { type: Object, required: true }, pages: { type: Array, default: () => [] } })
const emit = defineEmits(['copy', 'remove', 'change', 'locate', 'move'])

// 块内表单编辑 → 通知父级写回文本（渲染器双向）。
// 用快照比较：只在数据值真正变化时 emit，避免父级 parse 重建 data 引发的死循环。
let lastSnap = JSON.stringify(props.data)
watch(() => props.data, (val) => {
  const snap = JSON.stringify(val)
  if (snap !== lastSnap) {
    lastSnap = snap
    emit('change')
  }
}, { deep: true })

// 块默认展开（配置打开即见完整内容）。初次打开配置页的渲染开销由 App 启动后预渲染消除。
const expanded = ref(true)

const enabled = computed({
  get: () => props.data.enabled ?? true,
  set: (v) => { props.data.enabled = v },
})

const CONDITIONS = ['pool_draws', 'banner_draws', 'card_obtained', 'pool_exhausted', 'time_window']
const ACTIONS = ['switch_to', 'exhaust_banner']
// 生命周期「关联池」：本 Banner 的池子 id 下拉（不再手输）
const ownPoolIds = computed(() => (props.data.pools || []).map((p) => p.id).filter(Boolean))

// 匹配列仅 card_obtained 条件需要
const isCardObtainedLife = computed(() =>
  (props.data.lifecycle || []).some((l) => l.condition === 'card_obtained'))

// ── 选中池（显示其奖励分布子表）──
const selectedPool = ref(null)
function onPoolSelect(row) {
  selectedPool.value = row
}

// ── 池子 / 奖励 / 生命周期操作 ──
function addPool() {
  props.data.pools.push({
    id: `p${props.data.pools.length + 1}`,
    cost: 'draw_resource:160',
    batch_size: 1,
    max_draws: 0,
    excludes_all_pity: false,
    exchange_card_id: '',
    epitomizable_cards: [],
    rewards: [],
  })
  selectedPool.value = props.data.pools[props.data.pools.length - 1]
}
function removePool(row) {
  const i = props.data.pools.indexOf(row)
  if (i >= 0) props.data.pools.splice(i, 1)
  if (selectedPool.value === row) selectedPool.value = null
}
function addReward(pool) {
  pool.rewards.push({ card_id: '', probability: 0, rarity: 'r', featured: false, resources_gained: {} })
}
function removeReward(pool, row) {
  pool.rewards.splice(pool.rewards.indexOf(row), 1)
}
// 奖励「资源获取」：对象 ↔ "res:num, res:num" 文本（对齐 Qt 奖励表「资源获取」列）
function resGainedText(row) {
  return Object.entries(row.resources_gained || {}).map(([k, v]) => `${k}:${v}`).join(', ')
}
function parseResGained(row, text) {
  const obj = {}
  for (const part of (text || '').split(',')) {
    const m = part.trim().match(/^([^:]+):([\d.]+)$/)
    if (m) obj[m[1].trim()] = Number(m[2])
  }
  row.resources_gained = Object.keys(obj).length ? obj : undefined
}
function addLifecycle() {
  props.data.lifecycle.push({ condition: 'pool_draws', pool: '', at: 0, match: 'card_id', action: 'switch_to', target: '' })
}
function removeLifecycle(row) {
  props.data.lifecycle.splice(props.data.lifecycle.indexOf(row), 1)
}
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
.block-name {
  font-weight: 600;
}
.block-id {
  font-size: 11px;
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
.inner-sub {
  margin-top: 6px;
  margin-left: 8px;                 /* 二级子块（奖励表）缩进，再套一层面板 */
  border: 1px solid var(--gsc-border);
  background: #ffffff;
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
</style>
