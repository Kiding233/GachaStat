// ══════════════════════════════════════════════════════════════════
// 数据集分析方法定义（数据驱动：方法池 / 参数 / 结果区框架）
// 对齐 Qt 各分析面板 + 信息架构定稿。后端经 js_api 接 AnalysisService。
// ══════════════════════════════════════════════════════════════════
//
// P72（ISSUE-101/120）legacy 豁免：methodDefs type 'cumulative_by_pool'（L195）与
// DatasetWorkbench.vue L186 路由键、webui analysis_service.py L163 API 方法键为同一
// wire 键，保持 'cumulative_by_pool' 不改——PyQt 侧 chart key 已改 'cumulative_by_banner'，
// POC 原型 / webui 为遗留层（消费链依赖 webui handler，改写将命中不到方法返回「未知分析方法」）。

// 21 种广义出率（core/gdr.py UNIFIED_GDR_REGISTRY）
export const GDR_OPTIONS = [
  ['target_achievement', '简单目标达成率'],
  ['target_achievement_obtainable', '简单目标达成率（可达）'],
  ['target_collection', '目标卡收集率'],
  ['target_collection_obtainable', '目标卡收集率（可达）'],
  ['all_targets', '抽出全部目标卡'],
  ['all_targets_obtainable', '抽出全部目标卡（可达）'],
  ['ssr_collection', 'SSR收集率'],
  ['resource_remaining', '资源剩余'],
  ['resource_consumed', '资源消耗'],
  ['extra_target', '额外目标卡'],
  ['non_pity_draws', '非保底抽卡数'],
  ['pity_draws', '保底抽卡数'],
  ['resource_efficiency', '目标卡出卡效率'],
  ['resource_per_card', '每目标卡资源消耗'],
  ['per_pool_draw_rate', '每池下池出卡率'],
  ['weapon_character_ratio', '专武角色比'],
  ['target_card_draws', '目标卡出数'],
  ['weighted_satisfaction', '加权满意度'],
  ['weighted_satisfaction_obtainable', '加权满意度（可达）'],
  ['total_card_value', '总出卡价值'],
  ['draw_conversion_efficiency', '抽数转化效率'],
]

// 保底类型（core/pity.py BEHAVIOR_REGISTRY）
export const PITY_TYPES = ['soft_interval', 'soft_additive', 'soft_step', 'hard', 'rotating', 'rotating_soft', 'rotating_cr', 'rotating_cr_soft', 'targeted', 'targeted_soft']

// 内置策略 key（strategies/builtin/）
export const STRATEGY_KEYS = ['smart', 'draw_target', 'target_hunting', 'stop_on_target', 'pity_reserve', 'pool_quota', 'fixed_count', 'no_draw']

// 参数描述：type = select | number | bool | text | array
export const METHOD_CATEGORIES = [
  '总体广义出率', '成功率', '风险分析', '时间演化', '每池分析', '过程分析', '脆弱性', '最差影响',
]

export const METHOD_DEFS = [
  // ── 总体广义出率分析 ──
  {
    type: 'gdr_dist', label: 'GDR 分布', category: '总体广义出率',
    params: [
      // 对齐旧 analysis_panel：多 GDR 多选（每指标独立生成 hist/cdf）
      { key: 'gdr', label: 'GDR 指标', type: 'array', options: GDR_OPTIONS, default: ['target_achievement'] },
      { key: 'hist', label: '分布', type: 'bool', default: true },
      { key: 'cdf', label: '累积分布', type: 'bool', default: false },
      // 对齐旧 analysis_panel draw_unit_cb：以抽数为单位（资源类 GDR ÷ cost_per_draw）
      { key: 'unit', label: '以抽数为单位', type: 'bool', default: false },
    ],
    result: [
      { key: 'summary', title: '概览（均值 / 中位数 / 置信区间）' },
      { key: 'chart', title: 'GDR 分布图', desc: '直方图 + 累积分布' },
    ],
  },
  {
    type: 'gdr_statistics', label: 'GDR 指标统计', category: '总体广义出率',
    params: [
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'target_achievement' },
      { key: 'ci', label: '置信水平', type: 'number', min: 0.8, max: 0.99, step: 0.01, default: 0.95, precision: 2 },
      { key: 'unit', label: '以抽数为单位', type: 'bool', default: false },
    ],
    result: [
      { key: 'summary', title: '统计摘要（均值 / CI / 分位数）' },
      { key: 'table', title: '统计表', desc: '各百分位 + 置信区间' },
    ],
  },
  {
    type: 'correlation', label: 'GDR 指标相关性', category: '总体广义出率',
    params: [
      { key: 'unit', label: '以抽数为单位', type: 'bool', default: false },
    ],
    result: [
      { key: 'chart', title: 'GDR 相关性矩阵', desc: '多 GDR 两两 Pearson 相关热力图' },
      { key: 'summary', title: '相关性摘要', desc: '指标数 / 样本数' },
    ],
  },

  // ── 成功率分析 ──
  {
    type: 'success_rate', label: '成功率分析', category: '成功率',
    params: [
      { key: 'gdr', label: '成功标准', type: 'select', options: GDR_OPTIONS, default: 'target_achievement' },
      { key: 'threshold', label: '成功阈值', type: 'number', default: 1.0, precision: 2 },
      // 对齐旧 analysis_panel：范围 overall/cumulative/single_pool + 第k池 + 置信水平
      { key: 'scope', label: '范围', type: 'select', options: [['overall', '总体（最终结果）'], ['cumulative', '第k池累积'], ['single_pool', '第k池单池']], default: 'overall' },
      { key: 'pool_index', label: '第k个池', type: 'number', min: 1, max: 99, default: 1 },
      { key: 'ci', label: '置信水平', type: 'number', min: 0.8, max: 0.99, step: 0.01, default: 0.95, precision: 2 },
    ],
    result: [
      { key: 'summary', title: '成功率 + Wilson 置信区间' },
      { key: 'chart', title: '成功率图', desc: '整体 / 每池成功率' },
    ],
  },

  // ── 风险分析 ──
  {
    type: 'risk_var_cvar', label: 'VaR / CVaR 分析', category: '风险分析',
    params: [
      { key: 'alpha', label: '风险 α', type: 'number', min: 0.01, max: 0.5, step: 0.01, default: 0.05, precision: 2 },
      { key: 'ci', label: '置信水平', type: 'number', min: 0.8, max: 0.99, step: 0.01, default: 0.95, precision: 2 },
    ],
    result: [
      { key: 'summary', title: 'VaR / CVaR 摘要（含 Bootstrap CI）' },
      { key: 'chart', title: '风险分布图', desc: '左尾分布 + VaR/CVaR 标注' },
    ],
  },
  {
    type: 'risk_worst_case', label: '最差情形分析', category: '风险分析',
    params: [
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'resource_remaining' },
      // 对齐旧 analysis_panel alpha 全局参数：风险水平可调（后端 _risk_tail 消费）
      { key: 'alpha', label: '风险 α', type: 'number', min: 0.01, max: 0.5, step: 0.01, default: 0.05, precision: 2 },
    ],
    result: [
      { key: 'summary', title: '最差情形分位数' },
      { key: 'chart', title: '最差情形分布', desc: '尾部 α 分布' },
    ],
  },
  {
    type: 'risk_best_case', label: '最好情形分析', category: '风险分析',
    params: [
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'target_achievement' },
      { key: 'alpha', label: '风险 α', type: 'number', min: 0.01, max: 0.5, step: 0.01, default: 0.05, precision: 2 },
    ],
    result: [
      { key: 'summary', title: '最好情形分位数' },
      { key: 'chart', title: '最好情形分布', desc: '头部 α 分布' },
    ],
  },
  {
    type: 'conditional_dist', label: '条件分布', category: '风险分析',
    params: [
      // 对齐旧 analysis_panel：条件分布 = 「条件 GDR 指标 cond + 阈值 threshold」下目标 GDR 的分布
      { key: 'cond', label: '条件指标', type: 'select', options: GDR_OPTIONS, default: 'target_achievement' },
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'resource_remaining' },
      { key: 'threshold', label: '条件阈值', type: 'number', default: 0.5, precision: 4 },
    ],
    result: [
      { key: 'summary', title: '条件分布统计量表' },
      { key: 'chart', title: '条件分布图', desc: '按条件指标阈值切分的 GDR 分布' },
    ],
  },

  // ── 时间演化 ──
  {
    type: 'time_series', label: 'GDR 时间序列演化', category: '时间演化',
    params: [
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'target_achievement' },
    ],
    result: [
      { key: 'chart', title: 'GDR 时间序列', desc: '逐抽 GDR 演化' },
    ],
  },
  {
    type: 'time_heatmap', label: '时间-GDR 热力图', category: '时间演化',
    params: [
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'target_achievement' },
    ],
    result: [
      { key: 'chart', title: '时间-GDR 热力图', desc: '时间×GDR 二维热力' },
    ],
  },
  {
    type: 'waterfall_3d', label: '3D 瀑布图', category: '时间演化',
    params: [],
    result: [
      { key: 'chart', title: '3D 瀑布图', desc: '目标达成随时间步的分布演化（z=概率）' },
    ],
  },
  {
    type: 'waterfall_2d', label: '2D 压缩瀑布图', category: '时间演化',
    params: [],
    result: [
      { key: 'chart', title: '2D 压缩瀑布图', desc: '各时间步目标卡数概率曲线（viridis 渐变）' },
    ],
  },
  {
    type: 'draws_vs_gdr', label: '抽卡数-达成率散点', category: '时间演化',
    params: [
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'target_achievement' },
    ],
    result: [
      { key: 'chart', title: '抽卡数-达成率散点图', desc: '散点 + 趋势' },
    ],
  },

  // ── 每池分析 ──
  {
    type: 'per_pool_draws', label: '每池抽卡数统计', category: '每池分析',
    params: [],
    result: [
      { key: 'summary', title: '每池抽卡数摘要' },
      { key: 'table', title: '每池抽卡数表', desc: '池 / 均值 / 分位数' },
      { key: 'chart', title: '每池抽卡数柱状', desc: '各池抽卡数（横向柱状）' },
    ],
  },
  {
    type: 'per_pool_target_rate', label: '每池目标卡数', category: '每池分析',
    params: [],
    result: [
      { key: 'table', title: '每池目标卡数表' },
      { key: 'chart', title: '每池目标卡数图', desc: '各池目标卡期望/分布' },
    ],
  },
  {
    type: 'per_pool_pity_rate', label: '每池保底数', category: '每池分析',
    params: [],
    result: [
      { key: 'table', title: '每池保底数表' },
      { key: 'chart', title: '每池保底数图', desc: '各池保底触发统计' },
    ],
  },
  {
    type: 'cumulative_by_pool', label: '截止每池 GDR 分布', category: '每池分析',
    params: [
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'target_achievement' },
    ],
    result: [
      { key: 'chart', title: '截止每池 GDR 分布', desc: '多池累积分布' },
    ],
  },
  {
    type: 'transition_analysis', label: '转变分析', category: '每池分析',
    params: [
      // 对齐旧 analysis_panel：成功判据（success_criteria）+ 成功阈值 + 置信水平
      { key: 'eventMode', label: '成功判据', type: 'select', options: [['all_targets', '全部目标卡达成'], ['any_ssr', '至少一张SSR'], ['per_pool_target', '每池至少一张目标卡']], default: 'all_targets' },
      { key: 'threshold', label: '成功阈值', type: 'number', default: 1.0, precision: 2 },
      { key: 'ci', label: '置信水平', type: 'number', min: 0.8, max: 0.99, step: 0.01, default: 0.95, precision: 2 },
    ],
    result: [
      { key: 'table', title: '转变概率表（Wilson CI）', desc: '事件→事件/成败 转移矩阵' },
      { key: 'chart', title: '转变网格图', desc: '池间转移概率网格' },
    ],
  },

  // ── 过程分析 ──
  {
    type: 'process', label: '过程分析', category: '过程分析',
    params: [
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'target_achievement' },
      { key: 'threshold', label: '成功阈值', type: 'number', default: 1.0, precision: 2 },
      // 对齐旧 process_analysis_panel：eventMode / successMode（后端 process_service 读这两个键，
      // 旧版 events/successOp 键后端不读、配置被静默忽略）
      { key: 'eventMode', label: '事件模式', type: 'select', options: [['sequence', '事件类型序列'], ['set', '事件类型集合'], ['count_set', '事件计数组合'], ['raw', '原始轨迹'], ['custom', '自定义模式']], default: 'sequence' },
      { key: 'successMode', label: '成败模式', type: 'select', options: [['count', '成败计数'], ['sequence', '成败序列'], ['set', '成败集合'], ['custom', '自定义模式']], default: 'count' },
      // 自定义模式约束（对齐旧 custom_threshold_widget / success_custom_widget）
      { key: 'successOp', label: '成功算符', type: 'select', options: [['>=', '≥'], ['>', '>'], ['=', '='], ['<=', '≤'], ['<', '<']], default: '>=' },
      { key: 'successN', label: '成功次数 N', type: 'number', min: 1, max: 99, default: 1 },
      { key: 'constraints', label: '事件约束', type: 'text', default: '' },
      { key: 'ci', label: '置信水平', type: 'number', min: 0.8, max: 0.99, step: 0.01, default: 0.95, precision: 2 },
    ],
    result: [
      { key: 'table', title: '事件统计（AA）', desc: '事件组合 / 次数 / 概率 / 累计' },
      { key: 'table2', title: '交叉统计（BB/AB/BA）', desc: '成败模式 + 事件→成败 + 成败→事件' },
      { key: 'table3', title: '轨迹详情', desc: '逐抽轨迹' },
    ],
  },

  // ── 脆弱性分析（分析 + 生成两步，一个分析单元）──
  {
    type: 'vuln', label: '脆弱性分析', category: '脆弱性',
    params: [
      // 对齐旧 retreat_panel：默认 GDR 为下拉 index 0（简单目标达成率）
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'target_achievement' },
      { key: 'threshold', label: '成功阈值', type: 'number', default: 1.0, precision: 2 },
      // 对齐旧 retreat_panel：α 默认 0.5、等距分箱数默认 20（旧 UI alpha_spin 0.5 / num_bins 20）
      { key: 'alpha', label: '脆弱比例 α', type: 'number', min: 0, max: 1, step: 0.01, default: 0.5, precision: 2 },
      { key: 'nbins', label: '分箱数', type: 'number', min: 5, max: 100, default: 20 },
      // ── 生成配置（按原 UI 方案搜索方法：从哪个池子开始 / 资源是什么 / 保底状态如何）──
      { key: 'from_pool', label: '起始池', type: 'select', options: [['_root', '(从头开始)']], default: '_root' },
      // 对齐旧 retreat_search_panel：资源预设 7 档含 VI 下限/VI 均值/VI 上限，默认自定义
      { key: 'base_resource', label: '基准资源', type: 'select', options: [['vi_lower', 'VI下限'], ['vi_mean', 'VI均值'], ['vi_upper', 'VI上限'], ['p25', '25%分位'], ['p50', '50%分位'], ['mean', '均值'], ['p75', '75%分位'], ['custom', '自定义']], default: 'custom' },
      { key: 'base_custom', label: '自定义资源', type: 'text', default: '' },
      // 对齐旧 retreat_search_panel：保底水位默认按均值快照
      { key: 'pity_state', label: '保底状态', type: 'select', options: [['none', '不保留'], ['mean', '按均值'], ['median', '按中位'], ['p25', '按25%分位'], ['p75', '按75%分位']], default: 'mean' },
    ],
    result: [
      { key: 'chart', title: '脆弱性三行子图', desc: 'PAVA 保序回归 + Bootstrap 变更点 CI' },
      { key: 'summary', title: '变更点 / 脆弱区间摘要' },
    ],
    // 两步：运行脆弱性分析 + 按方案搜索参数生成调整配置
    actions: [
      { key: 'run_analysis', label: '运行分析' },
      { key: 'generate_config', label: '生成调整配置' },
    ],
  },

  // ── 最差影响（分析生成三步的「分析生成」步：按原 UI 参数算配置，有默认方案）──
  {
    type: 'worst_config', label: '生成后续池子配置', category: '最差影响',
    params: [
      { key: 'cond', label: '条件', type: 'select', options: [['all', '全部'], ['success', '成功'], ['failure', '失败']], default: 'success' },
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'resource_remaining' },
      { key: 'threshold', label: '成功阈值', type: 'number', default: 1.0, precision: 2 },
      { key: 'alpha', label: '初始资源分位 α', type: 'number', min: 0.01, max: 0.5, step: 0.01, default: 0.05, precision: 2 },
      { key: 'customResource', label: '自定义初始资源', type: 'text', default: '' },
      { key: 'numSim', label: '模拟次数', type: 'number', min: 50, max: 100000, step: 100, default: 1000 },
      { key: 'duration', label: '持续天数', type: 'number', min: 1, max: 365, default: 21 },
      { key: 'cost', label: '单抽消耗', type: 'text', default: 'draw_resource:160' },
    ],
    // 卡牌分布为特化子块（distribution 表格），在 ParamControls 单独渲染
    result: [
      { key: 'summary', title: '生成的后续池子配置摘要' },
      { key: 'table', title: '卡牌分布表', desc: '卡ID / 概率 / 稀有度 / Featured' },
    ],
    action: 'generate_config',  // 生成派生配置（挂源配置下，普通 config）
  },
  {
    type: 'worst_dist', label: '新池子数分布', category: '最差影响',
    params: [
      { key: 'cond', label: '条件', type: 'select', options: [['all', '全部'], ['success', '成功'], ['failure', '失败']], default: 'success' },
      // 对齐旧 worst_impact_panel：gdr_combo setCurrentIndex(1) = 可达变体
      { key: 'gdr', label: 'GDR 指标', type: 'select', options: GDR_OPTIONS, default: 'target_achievement_obtainable' },
      { key: 'threshold', label: '成功阈值', type: 'number', default: 1.0, precision: 2 },
      { key: 'alpha', label: '初始资源分位 α', type: 'number', min: 0.01, max: 0.5, step: 0.01, default: 0.05, precision: 2 },
      { key: 'customResource', label: '自定义初始资源', type: 'text', default: '' },
      { key: 'numSim', label: '模拟次数', type: 'number', min: 50, max: 100000, step: 100, default: 1000 },
    ],
    // 后续池子配置来源：选择工作区里「生成后续池子配置」产出的 config（普通统计分析模块，分析该配置跑出的数据）
    result: [
      { key: 'summary', title: '保守资源 / 大保底覆盖 / 期望新池子数' },
      { key: 'gauge', title: '大保底资源覆盖', desc: '覆盖倍数 + 状态色' },
      { key: 'chart', title: '新池子数分布图', desc: 'P(X=k) 柱状 + 期望线' },
      { key: 'table', title: '分布详情表', desc: 'k / P(X=k) / P(X≥k) / 累计' },
    ],
    action: 'run_analysis',
  },
]

export const methodByType = (t) => METHOD_DEFS.find((m) => m.type === t)
export const methodsByCategory = (cat) => METHOD_DEFS.filter((m) => m.category === cat)

// ── 动态 GDR 选项（资源类 GDR 按资源种类展开为 :qualified 条目）──
// 静态 GDR_OPTIONS 是兜底（资源定义缺失/独立运行）。连接真实后端后，前端启动时经
// api.list_gdr_options() 取 get_expanded_gdr_entries 的展开列表（resource_remaining:draw_resource 等），
// 注入所有 GDR 下拉的 options，并修正资源类默认值为限定形式（与原 UI populate_gdr_combo 一致）。
export function applyGdrOptions(options) {
  if (!Array.isArray(options) || !options.length) return
  const pairs = options.map((o) => [o.key, o.display])
  const keys = pairs.map((p) => p[0])
  for (const m of METHOD_DEFS) {
    for (const f of m.params) {
      if (!['gdr', 'gdrA', 'gdrB'].includes(f.key)) continue
      f.options = pairs
      // 默认值修正：未限定资源 key（如 resource_remaining）在展开列表中已变为 :draw_resource
      if (f.default && !f.default.includes(':') && !keys.includes(f.default)) {
        const qualified = `${f.default}:draw_resource`
        if (keys.includes(qualified)) f.default = qualified
      }
    }
  }
}
