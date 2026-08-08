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
      <!-- ══ 资源定义块（resource_defs）：条目表（key/name/initial，可复制、序列化按 key 去重）══ -->
      <template v-if="type === 'resource_defs'">
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

      <!-- ══ 资源获取规则块（resource_gains）：gain_rules + day_overrides，可复制、序列化汇总合并 ══ -->
      <template v-else-if="type === 'resource_gains'">
        <!-- 资源获取规则（[[resources.gain_rules]]：每N天/每周/每月 类型 + 资源获取）-->
        <div class="sub-title">资源获取规则（{{ (data.gainRules || []).length }}）</div>
        <el-table :data="data.gainRules || []" size="small">
          <el-table-column label="类型" width="140">
            <template #default="{ row }">
              <el-select v-model="row.type" size="small" style="width: 100%">
                <el-option label="每 N 天" value="every_n_days" />
                <el-option label="每周（参数=星期几 1-7）" value="weekly" />
                <el-option label="每月固定日（参数=日 或 月,日）" value="monthly_day" />
                <el-option label="每月第 N 周（参数=周,星期几）" value="monthly_week" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="参数" width="100">
            <template #default="{ row }"><el-input v-model="row.param" size="small" placeholder="N / 日 / 月,日 / 周,星期" /></template>
          </el-table-column>
          <el-table-column label="资源获取 (res:num)" min-width="170">
            <template #default="{ row }">
              <el-input :model-value="gainsText(row.gains)" size="small" placeholder="draw_resource:60" @change="(v) => parseGains(row, v)" />
            </template>
          </el-table-column>
          <el-table-column width="50" align="center">
            <template #default="{ row }">
              <el-button size="small" text type="danger" @click="removeGainRule(row)">×</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" class="sub-btn" @click="addGainRule">+ 添加获取规则</el-button>

        <!-- 逐日额外获取（[[resources.day_overrides]]：指定天累加资源获取——引擎语义是「累加」不是覆盖）-->
        <div class="sub-title">逐日额外获取（{{ (data.dayOverrides || []).length }}）</div>
        <el-table :data="data.dayOverrides || []" size="small">
          <el-table-column label="天数" width="110">
            <template #default="{ row }">
              <el-input-number v-model="row.day" size="small" :min="0" :controls="false" style="width: 90px" />
            </template>
          </el-table-column>
          <el-table-column label="资源获取 (res:num)" min-width="170">
            <template #default="{ row }">
              <el-input :model-value="gainsText(row.gains)" size="small" placeholder="draw_resource:100" @change="(v) => parseGains(row, v)" />
            </template>
          </el-table-column>
          <el-table-column width="50" align="center">
            <template #default="{ row }">
              <el-button size="small" text type="danger" @click="removeDayOverride(row)">×</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button size="small" class="sub-btn" @click="addDayOverride">+ 添加逐日额外</el-button>
      </template>

      <!-- ══ 卡片/权重/目标卡：聚合条目表格（每行一个条目，字段塞一行）══ -->
      <template v-else-if="isTableType">
        <el-table :data="data.entries" size="small" highlight-current-row @current-change="onCardSelect">
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
              <!-- 目标卡关联池：只读自动解析（由该卡在哪些池的奖励中出现推导，对齐旧 UI _update_target_pools）-->
              <span v-else-if="col.type === 'pools_readonly'" class="pools-ro">
                {{ targetPoolsText(row) }}
              </span>
              <el-input
                v-else-if="col.type === 'tags'"
                :model-value="tagsText(row[col.key])"
                size="small"
                placeholder="key:value, key:value"
                @change="(v) => parseTags(row, col.key, v)"
              />
              <el-input
                v-else-if="col.type === 'listtags'"
                :model-value="listTagsText(row[col.key])"
                size="small"
                placeholder="key:v1,v2; key2:v1"
                @change="(v) => parseListTags(row, col.key, v)"
              />
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

        <!-- 卡片溢出分段（card.overflow_bands）：选中行编辑（满突溢出）-->
        <div v-if="type === 'card' && selectedCard" class="sub-section">
          <div class="sub-title">「{{ selectedCard.card_id || '未命名' }}」溢出分段（overflow_bands）</div>
          <el-table :data="selectedCard.overflow_bands || []" size="small">
            <el-table-column label="区间 [min, max]" min-width="170">
              <template #default="{ row }">
                <el-input :model-value="rangeText(row.range)" size="small" placeholder="1-7 或 8-inf" @change="(v) => parseRange(row, v)" />
              </template>
            </el-table-column>
            <el-table-column label="资源 (key:num)" min-width="200">
              <template #default="{ row }">
                <el-input :model-value="resourcesText(row.resources)" size="small" placeholder="yellow_cert:1, ..." @change="(v) => parseResources(row, v)" />
              </template>
            </el-table-column>
            <el-table-column width="50" align="center">
              <template #default="{ row }">
                <el-button size="small" text type="danger" @click="removeBandFrom(selectedCard.overflow_bands, row)">×</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button size="small" text type="primary" class="sub-btn" @click="addCardBand">+ 溢出段</el-button>
        </div>
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

      <!-- ══ 稀有度溢出默认（[rarity_defaults.<rarity>] + overflow_bands）══ -->
      <template v-else-if="type === 'rarity_defaults'">
        <div v-for="(rd, r) in data.defaults || {}" :key="r" class="rd-block">
          <div class="sub-title">稀有度「{{ r }}」默认溢出</div>
          <el-table :data="rd.overflow_bands || []" size="small">
            <el-table-column label="区间 [min, max]" min-width="170">
              <template #default="{ row }">
                <el-input :model-value="rangeText(row.range)" size="small" placeholder="1-7 或 8-inf" @change="(v) => parseRange(row, v)" />
              </template>
            </el-table-column>
            <el-table-column label="资源 (key:num)" min-width="200">
              <template #default="{ row }">
                <el-input :model-value="resourcesText(row.resources)" size="small" placeholder="starglitter:10, ..." @change="(v) => parseResources(row, v)" />
              </template>
            </el-table-column>
            <el-table-column width="50" align="center">
              <template #default="{ row }">
                <el-button size="small" text type="danger" @click="removeBandFrom(rd.overflow_bands, row)">×</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button size="small" text type="primary" class="sub-btn" @click="addBandTo(rd)">+ 溢出段</el-button>
        </div>
        <el-button size="small" class="sub-btn" @click="addRarityDefault">+ 稀有度默认</el-button>
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
                  <el-option v-for="o in selectOptions(f)" :key="String(o[0])" :label="o[1]" :value="o[0]" />
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
                >
                  <el-option v-for="o in arrayOptions(f)" :key="String(o[0])" :label="o[1]" :value="o[0]" />
                </el-select>
              </div>
            </div>
          </div>
        </div>

        <!-- 类型专用参数（rotating_cr/targeted 等事件驱动参数可编辑；deltas 表用于 soft_step）-->
        <div v-if="pitySpecial.fields.length || pitySpecial.showDeltas" class="pity-group">
          <div class="pity-group-title">类型专用参数</div>
          <div v-for="f in pitySpecial.fields" :key="f.key" class="pity-row">
            <span class="pity-label">{{ f.label }}</span>
            <div class="pity-ctl">
              <el-input-number
                v-if="f.type === 'number'"
                :model-value="data[f.key]"
                size="small"
                :precision="f.precision"
                :controls="false"
                class="pity-num"
                @change="(v) => (data[f.key] = v)"
              />
              <el-switch
                v-else-if="f.type === 'bool'"
                :model-value="!!(data[f.key] ?? f.default)"
                size="small"
                @change="(v) => (data[f.key] = v)"
              />
              <el-input v-else-if="f.type === 'text'" v-model="data[f.key]" size="small" placeholder="card_id" />
              <!-- cr_state_probs：浮点列表 -->
              <div v-else-if="f.type === 'floats'" class="floats-edit">
                <el-tag v-for="(v, vi) in (data[f.key] || [])" :key="vi" size="small" closable @close="removeFloat(f.key, vi)">{{ v }}</el-tag>
                <el-input-number size="small" :controls="false" :precision="4" :step="0.01" style="width: 80px" @change="(nv) => addFloat(f.key, nv)" />
              </div>
            </div>
          </div>
          <!-- soft_step：爬升曲线 deltas（[抽数段长, 增量%] 表）-->
          <div v-if="pitySpecial.showDeltas" class="pity-deltas">
            <div class="pity-deltas-title">爬升曲线 deltas（[抽数段长, 增量]）</div>
            <el-table :data="data.deltas || []" size="small">
              <el-table-column label="段长(抽)" width="120">
                <template #default="{ row }"><el-input-number v-model="row[0]" size="small" :min="1" :controls="false" style="width: 90px" /></template>
              </el-table-column>
              <el-table-column label="增量" min-width="120">
                <template #default="{ row }"><el-input-number v-model="row[1]" size="small" :precision="2" :controls="false" style="width: 90px" /></template>
              </el-table-column>
              <el-table-column width="56">
                <template #default="{ row }"><el-button size="small" text type="danger" @click="removeDeltasRow(row)">×</el-button></template>
              </el-table-column>
            </el-table>
            <el-button size="small" text type="primary" @click="addDeltasRow">+ 段</el-button>
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
            <el-select v-else-if="f.type === 'select'" v-model="data[f.key]" size="small" allow-create filterable style="width: 220px">
              <el-option v-for="o in selectOptions(f)" :key="String(o[0])" :label="o[1]" :value="o[0]" />
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
            >
              <el-option v-for="o in arrayOptions(f)" :key="String(o[0])" :label="o[1]" :value="o[0]" />
            </el-select>
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
          <el-form-item label="最大触发">
            <el-input-number :model-value="data.lifecycle.max_triggers" size="small" :min="0" :controls="false" class="pity-num" @change="(v) => (data.lifecycle.max_triggers = v)" />
          </el-form-item>
        </el-form>
      </div>
      <div v-if="pityExtraKeys.length" class="sub-section">
        <div class="sub-title">未识别的其他参数（只读）</div>
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
          <el-form-item label="随机卡（候选池）">
            <div class="rc-wrap">
              <el-table :data="data.bonus_reward.random_cards" size="small">
                <el-table-column label="候选卡（逗号分隔）" min-width="180">
                  <template #default="{ row }">
                    <el-input :model-value="(row.candidates || []).join(',')" size="small" @change="(v) => (row.candidates = v.split(',').map((s) => s.trim()).filter(Boolean))" />
                  </template>
                </el-table-column>
                <el-table-column label="权重（逗号分隔）" min-width="140">
                  <template #default="{ row }">
                    <el-input :model-value="(row.weights || []).join(',')" size="small" @change="(v) => (row.weights = v.split(',').map((s) => parseFloat(s.trim())).filter((x) => !Number.isNaN(x)))" />
                  </template>
                </el-table-column>
                <el-table-column label="数量" width="80">
                  <template #default="{ row }">
                    <el-input-number v-model="row.count" size="small" :min="1" :controls="false" style="width: 60px" />
                  </template>
                </el-table-column>
                <el-table-column width="50" align="center">
                  <template #default="{ row }">
                    <el-button size="small" text type="danger" @click="removeRandomCard(row)">×</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-button size="small" text type="primary" @click="addRandomCard">+ 候选池</el-button>
            </div>
          </el-form-item>
        </el-form>
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
  poolIds: { type: Array, default: () => [] },   // 全限定池 ID（{banner}.{pool}），供绑定池/目标卡下拉
  bannerIds: { type: Array, default: () => [] }, // banner ID，供「适用 Banner」下拉
  cardPools: { type: Object, default: () => ({}) }, // card_id → 全限定池 ID[]（目标卡关联池只读解析）
})
const emit = defineEmits(['copy', 'remove', 'change', 'locate', 'move'])

// 快照比较：只在值真正变化时 emit，打破双向同步死循环（与 ConfigBlock 同模式）
let lastSnap = JSON.stringify(props.data)
watch(() => props.data, (val) => {
  // 目标卡关联池：只读自动解析——卡ID/池奖励变化时同步 pool_ids（对齐旧 UI _update_target_pools）
  if (props.type === 'target') {
    for (const e of (props.data.entries || [])) {
      if (!e.card_id) continue
      const d = targetPools(e)
      if (d.length && JSON.stringify(d) !== JSON.stringify(e.pool_ids || [])) e.pool_ids = [...d]
    }
  }
  const snap = JSON.stringify(props.data)
  if (snap !== lastSnap) {
    lastSnap = snap
    emit('change')
  }
}, { deep: true })

// ── 下拉选项 / 目标卡关联池（只读推导）──
function optPair(o) { return Array.isArray(o) ? o : [o, o] }
// 里程碑「适用 Banner」等动态选项：空 = 全部 Banner + 真实 bannerIds（对齐引擎 banner 精确匹配）
function selectOptions(f) {
  if (f.key === 'banner') return [['', '全部（所有 Banner）'], ...props.bannerIds.map((b) => [b, b])]
  return (f.options || []).map(optPair)
}
// 保底「绑定池」数组：全限定池下拉 + 通配预设（引擎 fnmatch：'*' 全部池 / '*.main' 各 Banner 主池）
function arrayOptions(f) {
  if (f.options && f.options.length) return f.options.map(optPair)
  if (f.key === 'pools') {
    return [['*', '*（全部池）'], ['*.main', '*.main（各 Banner 主池）'],
            ...props.poolIds.map((p) => [p, p])]
  }
  return []
}
// 目标卡关联池：该卡出现在哪些池的奖励中（banner.pool.reward.card_id）→ 全限定 {banner}.{pool}
function targetPools(row) {
  const d = props.cardPools[row.card_id] || []
  return Array.isArray(d) ? d : []
}
function targetPoolsText(row) {
  const p = targetPools(row)
  if (p.length) return p.join(', ')
  return (row.pool_ids || []).length ? row.pool_ids.join(', ') + '（未在任意池奖励中匹配）' : '（未在任意池奖励中匹配）'
}

// 块默认展开。初次打开配置页的渲染开销由 App 启动后预渲染消除。
const expanded = ref(true)

const META = {
  resource_defs:  { label: '资源定义',     global: false },
  resource_gains: { label: '资源获取规则', global: false },
  card:      { label: '卡片',     global: false },
  pity:      { label: '保底规则', global: false },
  milestone: { label: '累抽奖励', global: false },
  target:    { label: '目标卡',   global: false },
  weight:    { label: '权重',     global: false },
  rarity:    { label: '稀有度层级', global: true },
  rarity_defaults: { label: '稀有度溢出默认', global: true },
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
  if (props.type === 'resource_defs') {
    const n = (d.entries || []).length
    return n ? `${n} 种资源` : '未命名'
  }
  if (props.type === 'resource_gains') {
    const g = (d.gainRules || []).length + (d.dayOverrides || []).length
    return g ? `${g} 条获取规则` : '未命名'
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
    { key: 'card_id', label: '卡ID', type: 'text', minWidth: 130 },
    { key: 'name', label: '名称', type: 'text', minWidth: 100 },
    { key: 'rarity', label: '稀有度', type: 'text', minWidth: 70 },
    { key: 'initial_count', label: '初始持有', type: 'number', minWidth: 90 },
    { key: 'tags', label: '标签', type: 'tags', minWidth: 150 },
    { key: 'list_tags', label: '多值标签', type: 'listtags', minWidth: 170 },
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
    { key: 'pool_ids', label: '关联池（只读）', type: 'pools_readonly', minWidth: 200 },
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

// ── 卡片溢出分段（card.overflow_bands）/ 稀有度溢出默认（rarity_defaults）──
const selectedCard = ref(null)
function onCardSelect(row) {
  if (props.type === 'card') selectedCard.value = row
}
function rangeText(range) {
  const r = range || [1, 1]
  const hi = r[1] === 'inf' || r[1] === Infinity || r[1] == null ? '∞' : String(r[1])
  return `${r[0]}-${hi}`
}
function parseRange(row, text) {
  const m = (text || '').trim().match(/^([\d.]+)\s*[-–~]\s*(.+)$/)
  if (m) {
    const hi = /^∞$|^inf$/i.test(m[2].trim()) ? 'inf' : Number(m[2])
    row.range = [Number(m[1]), hi]
  }
}
function resourcesText(res) {
  return Object.entries(res || {}).map(([k, v]) => `${k}:${v}`).join(', ')
}
function parseResources(row, text) {
  const obj = {}
  for (const part of (text || '').split(',')) {
    const m = part.trim().match(/^([^:]+):([\d.]+)$/)
    if (m) obj[m[1].trim()] = Number(m[2])
  }
  row.resources = Object.keys(obj).length ? obj : {}
}
function addCardBand() {
  if (!selectedCard.value) return
  if (!Array.isArray(selectedCard.value.overflow_bands)) selectedCard.value.overflow_bands = []
  selectedCard.value.overflow_bands.push({ range: [1, 1], resources: {} })
}
function addBandTo(rd) {
  if (!Array.isArray(rd.overflow_bands)) rd.overflow_bands = []
  rd.overflow_bands.push({ range: [1, 1], resources: {} })
}
function removeBandFrom(arr, row) {
  if (!Array.isArray(arr)) return
  arr.splice(arr.indexOf(row), 1)
}
function addRarityDefault() {
  const name = window.prompt('稀有度名（如 ssr）', 'ssr')
  if (name && name.trim()) {
    if (!props.data.defaults) props.data.defaults = {}
    props.data.defaults[name.trim()] = { overflow_bands: [] }
  }
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
    { key: 'banner', label: '适用 Banner', type: 'select' },
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
    if (key === 'start') return ['soft_interval', 'soft_additive'].includes(t)
    if (key === 'end') return t === 'soft_interval'   // soft_additive 用 increment（类型专用参数）
    return true
  }
  const byKey = Object.fromEntries(FIELDS.pity.map((f) => [f.key, f]))
  return [
    { key: 'def', title: '定义', fields: ['name', 'type', 'scope'].map((k) => byKey[k]).filter(Boolean) },
    { key: 'param', title: '规则参数', fields: ['target_featured', 'reset', 'start', 'end', 'threshold', 'counter_init'].filter(visible).map((k) => byKey[k]).filter(Boolean) },
    { key: 'scope', title: '作用范围', fields: ['pools'].map((k) => byKey[k]).filter(Boolean) },
  ]
})

// ── 保底类型专用参数（事件驱动家族可编辑；对齐旧 config_panel BEHAVIOR_REGISTRY 动态控件）──
const PITY_SPECIAL = {
  soft_interval: [],
  soft_additive: [{ key: 'increment', label: '增量(%)', type: 'number', precision: 2 }],
  soft_step: [],
  hard: [],
  rotating: [{ key: 'guaranteed_init', label: '初始大保底', type: 'bool', default: false }],
  rotating_soft: [{ key: 'guaranteed_init', label: '初始大保底', type: 'bool', default: false }],
  rotating_cr: [
    { key: 'guaranteed_init', label: '初始大保底', type: 'bool', default: false },
    { key: 'cr_counter_threshold', label: '捕获明光阈值', type: 'number' },
    { key: 'cr_base_rate', label: '捕获明光基础率', type: 'number', precision: 4 },
    { key: 'cr_state_probs', label: '捕获明光状态概率', type: 'floats' },
  ],
  rotating_cr_soft: [
    { key: 'guaranteed_init', label: '初始大保底', type: 'bool', default: false },
    { key: 'cr_counter_threshold', label: '捕获明光阈值', type: 'number' },
    { key: 'cr_base_rate', label: '捕获明光基础率', type: 'number', precision: 4 },
    { key: 'cr_state_probs', label: '捕获明光状态概率', type: 'floats' },
  ],
  targeted: [
    { key: 'fate_threshold', label: '定轨阈值', type: 'number' },
    { key: 'fate_points_init', label: '初始定轨点', type: 'number' },
    { key: 'selected_card_init', label: '初始定轨卡', type: 'text' },
    { key: 'switch_allowed', label: '允许切换', type: 'bool', default: true },
    { key: 'switch_resets_progress', label: '切换重置进度', type: 'bool', default: true },
  ],
  targeted_soft: [
    { key: 'fate_threshold', label: '定轨阈值', type: 'number' },
    { key: 'fate_points_init', label: '初始定轨点', type: 'number' },
    { key: 'selected_card_init', label: '初始定轨卡', type: 'text' },
    { key: 'switch_allowed', label: '允许切换', type: 'bool', default: true },
    { key: 'switch_resets_progress', label: '切换重置进度', type: 'bool', default: true },
  ],
}
const HANDLED_SPECIAL = new Set(Object.values(PITY_SPECIAL).flat().map((f) => f.key))
const pitySpecial = computed(() => {
  const t = props.data.type || 'soft_interval'
  return { fields: PITY_SPECIAL[t] || [], showDeltas: t === 'soft_step' }
})
function addDeltasRow() {
  if (!Array.isArray(props.data.deltas)) props.data.deltas = []
  props.data.deltas.push([10, 0])
}
function removeDeltasRow(row) {
  if (!Array.isArray(props.data.deltas)) return
  props.data.deltas.splice(props.data.deltas.indexOf(row), 1)
}
function addFloat(key, nv) {
  if (nv === undefined || nv === null) return
  if (!Array.isArray(props.data[key])) props.data[key] = []
  props.data[key].push(nv)
}
function removeFloat(key, vi) {
  if (!Array.isArray(props.data[key])) return
  props.data[key].splice(vi, 1)
}

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

// ── 资源获取规则 / 逐日覆盖（gains = {res: num} 文本编辑）──
function ensureArrays() {
  if (!props.data.gainRules) props.data.gainRules = []
  if (!props.data.dayOverrides) props.data.dayOverrides = []
}
function addGainRule() {
  ensureArrays()
  props.data.gainRules.push({ type: 'every_n_days', param: '', gains: {} })
}
function removeGainRule(row) {
  props.data.gainRules.splice(props.data.gainRules.indexOf(row), 1)
}
function addDayOverride() {
  ensureArrays()
  props.data.dayOverrides.push({ day: 0, gains: {} })
}
function removeDayOverride(row) {
  props.data.dayOverrides.splice(props.data.dayOverrides.indexOf(row), 1)
}
function gainsText(gains) {
  return Object.entries(gains || {}).map(([k, v]) => `${k}:${v}`).join(', ')
}
function parseGains(row, text) {
  const obj = {}
  for (const part of (text || '').split(',')) {
    const m = part.trim().match(/^([^:]+):([\d.]+)$/)
    if (m) obj[m[1].trim()] = Number(m[2])
  }
  row.gains = Object.keys(obj).length ? obj : {}
}

// ── 卡片标签：tags（单值） / list_tags（多值）──
function tagsText(tags) {
  return Object.entries(tags || {}).map(([k, v]) => `${k}:${v}`).join(', ')
}
function parseTags(row, key, text) {
  const obj = {}
  for (const part of (text || '').split(',')) {
    const m = part.trim().match(/^([^:]+):(.+)$/)
    if (m) obj[m[1].trim()] = m[2].trim()
  }
  row[key] = Object.keys(obj).length ? obj : undefined
}
function listTagsText(listTags) {
  return Object.entries(listTags || {}).map(([k, vs]) => `${k}:${(vs || []).join(',')}`).join('; ')
}
function parseListTags(row, key, text) {
  const obj = {}
  for (const part of (text || '').split(';')) {
    const m = part.trim().match(/^([^:]+):(.+)$/)
    if (m) obj[m[1].trim()] = m[2].split(',').map((s) => s.trim()).filter(Boolean)
  }
  row[key] = Object.keys(obj).length ? obj : undefined
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
// 随机卡候选池（random_cards: {candidates, weights, count}）
function addRandomCard() {
  props.data.bonus_reward.random_cards.push({ candidates: [], weights: [], count: 1 })
}
function removeRandomCard(row) {
  props.data.bonus_reward.random_cards.splice(props.data.bonus_reward.random_cards.indexOf(row), 1)
}

// ── pity 未建模参数（已建模字段之外，只读展示；序列化时由 configToml.extraToml 写回）──
const PITY_KNOWN = new Set(['name', 'type', 'scope', 'target_featured', 'threshold', 'reset', 'start', 'end', 'counter_init', 'pools', 'lifecycle'])
const pityExtra = computed(() => {
  if (props.type !== 'pity') return {}
  const o = {}
  for (const [k, v] of Object.entries(props.data)) {
    if (!PITY_KNOWN.has(k) && !HANDLED_SPECIAL.has(k) && v !== undefined && v !== null && v !== '') o[k] = v
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
.floats-edit {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}
.pity-deltas {
  margin-top: 6px;
  border-top: 1px dashed var(--gsc-border);
  padding-top: 6px;
}
.pity-deltas-title {
  font-size: 11px;
  color: var(--gsc-text-muted);
  margin-bottom: 4px;
}
.rd-block {
  margin-bottom: 8px;
}
.rc-wrap {
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
/* 目标卡关联池（只读）：浅灰底 + 等宽字体，与可编辑列区分 */
.pools-ro {
  font-family: var(--gsc-font-mono);
  font-size: 11px;
  color: var(--gsc-text-muted);
  background: #f0f1f2;
  border-radius: 2px;
  padding: 2px 5px;
  display: inline-block;
  line-height: 1.5;
  word-break: break-all;
}
</style>
