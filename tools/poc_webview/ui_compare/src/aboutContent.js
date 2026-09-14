// ══════════════════════════════════════════════════════════════════
// 关于对话框内容（迁移自旧 gui/about_dialog.py 的 5 个 Tab）
// 静态 HTML 内容保持与旧 UI 一致；版本历史动态（VERSION_HISTORY 由后端提供）
// ══════════════════════════════════════════════════════════════════

export const ABOUT_CONTENT = {
  // ── Tab 1：关于 ──
  about: `
    <h3>GachaStat</h3>
    <p>一个灵活的蒙特卡洛抽卡模拟与多维分析工具，支持多种保底机制、策略配置和统计分析。</p>

    <h4>核心功能</h4>
    <ul>
        <li><b>灵活的模拟引擎</b>：支持多池、多保底、多策略的抽卡模拟</li>
        <li><b>保底机制</b>：区间软保底 / 累加软保底 / 分段软保底 (RLE deltas) / 硬保底；featured/standard 槽位分离；多保底管道排序</li>
        <li><b>策略系统</b>：8 种内置策略（按需追卡、指定池配额、保底预留、目标即停、指定池追卡、固定次数等）</li>
        <li><b>停止条件系统</b>：6 种停止条件（所有池结束、固定次数、资源阈值、目标达成、抽到指定卡、时间限制）</li>
        <li><b>广义出率（GDR）</b>：21 种可配置的广义出率指标（含可达变体）</li>
        <li><b>过程分析</b>：逐池事件推断（7种事件类型）+ AA/BB/AB/BA 四种交叉统计</li>
        <li><b>Bootstrap 稳定性分析</b>：置信区间计算（BCa/GPD/Hill），零额外模拟成本</li>
        <li><b>脆弱性分析</b>：离散分箱 + PAVA 保序估计 + Bootstrap 变更点推断，识别资源脆弱区间</li>
        <li><b>方案搜索</b>：三合一搜索面板——最少资源（二分搜索）、最多目标卡（前进法/后退法）、资源-目标权衡曲线</li>
        <li><b>比较分析</b>：L1 描述统计 → L2 随机占优 → L3 假设检验（KS/MWU/ttest + Holm/BH校正）→ L4 帕累托前沿，四层递进策略比较</li>
        <li><b>数据管理</b>：模拟结果持久化存储（JSON）、可比性指纹检查、多数据集管理</li>
        <li><b>最差影响分析</b>：条件分布下尾分位数评估</li>
        <li><b>风险分析</b>：VaR/CVaR、经验分布、条件分布</li>
        <li><b>权重配置</b>：抽取意愿/错失代价/出卡价值三维权重</li>
    </ul>

    <h4>技术栈</h4>
    <ul>
        <li>Python 3.10+（引擎）</li>
        <li>pywebview + Vue3 + Element Plus + ECharts（新 UI）</li>
        <li>NumPy / SciPy（数值计算）</li>
        <li>binsreg (CCFF 2024) —— 分位数分箱</li>
        <li>PyInstaller（应用打包，onedir 分发）</li>
    </ul>

    <h4>许可证</h4>
    <p>本项目拟采用 <b>GNU General Public License v3.0 (GPLv3)</b>，但最终许可方式尚未确定。</p>
    <p>GPLv3 允许自由使用、修改和分发，但要求衍生作品必须以相同许可证开源。</p>
  `,

  // ── Tab 2：配置文件指南 ──
  config: `
    <h3>配置文件指南</h3>
    <p>所有配置集中在单一 <code>config.toml</code> 文件中，使用标准 TOML 格式。</p>

    <h4>[[card]] — 卡牌定义</h4>
    <pre>[[cards]]
id = "刻晴"
name = "刻晴"
rarity = "ssr"</pre>

    <h4>[resources.defs] + [resources.initial] — 资源定义与初始资源</h4>
    <pre>[resources.defs]
draw_resource = "抽卡资源"
exchange_currency = "兑换货币"

[resources.initial]
draw_resource = 1000
exchange_currency = 0</pre>

    <h4>[resources.gain_rules] + [resources.day_overrides] — 资源增益</h4>
    <pre>[resources]
gain_rules = [
    { type = "every_n_days", param = "7", gains = { draw_resource = 100 } },
]
day_overrides = [
    { day = 1, gains = { draw_resource = 500 } },
]</pre>
    <p>规则类型：<code>every_n_days</code>, <code>weekly</code>, <code>monthly_day</code>, <code>monthly_week</code>。</p>

    <h4>[[banner]] — Banner 定义（P61）</h4>
    <pre>[[banner]]
id = "pool_0"
name = "常驻池"
enabled = true
start_day = 0        # 开启（天）
end_day = 21         # 关闭（天）；省略 = 永久开放

[[banner.pool]]
id = "main"
cost = "draw_resource:160"
batch_size = 1
max_draws = 0        # 0=无限制
excludes_all_pity = false

[[banner.pool.reward]]
card_id = "刻晴"
probability = 0.6
rarity = "SSR"
featured = true</pre>
    <p><b>费用语法</b>：<code>资源ID:数量</code>。多资源可用 <code>&gt;</code>（大于号）或 <code>,</code>（逗号）分隔，表示按书写顺序的<b>强制优先级</b>。示例：<code>exchange_currency:5 &gt; draw_resource:160</code>。<code>&amp;</code> 表示同时需要多种资源（AND）。</p>
    <p>可选 Pool 字段：<code>exchange_card_id</code>（兑换池）、<code>epitomizable_cards</code>（定轨候选）、<code>excludes_all_pity</code>（不计保底）。</p>

    <h4>[[banner.lifecycle]] — 生命周期转换（P61）</h4>
    <pre>[[banner.lifecycle]]
condition = "pool_draws"   # pool_draws | banner_draws | card_obtained | pool_exhausted | time_window
pool = "main"
at = 30
match = "card_id"          # card_id | rarity
action = "switch_to"       # switch_to | exhaust_banner
target = "free_10pull"</pre>

    <h4>[[pity]] — 保底规则</h4>
    <pre>[[pity]]
name = "ssr_soft"
type = "soft_interval"   # soft_interval | soft_additive | soft_step | hard | rotating | targeted
scope = "ssr"
start = 80
end = 90
target_featured = true
reset = "featured"
pools = ["pool_0.main"]   # 全限定键 {banner_id}.{pool_id}，支持 fnmatch 通配符
counter_init = 0</pre>
    <p>绑定池用全限定键 <code>{banner_id}.{pool_id}</code>（如 <code>pool_0.main</code>）。</p>

    <h4>[[targets]] — 目标卡</h4>
    <pre>[[targets]]
card_id = "刻晴"
quantity = 2
pool_ids = ["pool_0", "pool_1"]   # Banner 级 id</pre>

    <h4>[[weights]] — 权重配置（可选）</h4>
    <pre>[[weights]]
card_id = "刻晴"
desire = 2.0
miss_cost = 1.2
card_value = 1.5</pre>
    <p>所有卡默认权重 1.0。desire_weight 影响前进法排序，miss_cost_weight 影响后退法排序，card_value 影响出卡价值计算。</p>
  `,

  // ── Tab 3：算法说明 ──
  algo: `
    <h3>算法说明</h3>

    <h4>蒙特卡洛模拟</h4>
    <p>核心模拟引擎采用蒙特卡洛方法，通过大量随机抽样估计概率分布。标准误 SE = σ/√N，其中 N 为模拟次数。</p>

    <h4>广义出率（GDR）计算</h4>
    <p>支持 21 种 GDR 指标，均从 CompactResult 中 O(1) 计算。标有 <b>↓</b> 的指标 lower_is_better（值越低越好）。</p>

    <h5>目标达成类</h5>
    <ul>
        <li><b>简单目标达成率</b> = Σ min(抽到数, 需求量) / Σ 需求量</li>
        <li><b>目标卡收集率</b> = 至少抽到1张的目标卡种类数 / 目标卡总种类数</li>
        <li><b>抽出全部目标卡</b> = 所有目标卡均满足需求量 → 1.0，否则 → 0.0（二值）</li>
        <li><b>SSR收集率</b> = 至少抽到1张的SSR种类数 / SSR总种类数</li>
    </ul>

    <h5>资源效率类</h5>
    <ul>
        <li><b>资源剩余</b> = 模拟结束时的 <code>final_resources[resource_id]</code></li>
        <li><b>资源消耗</b> <b>↓</b> = 模拟期间消耗的 <code>total_consumed[resource_id]</code></li>
        <li><b>目标卡出卡效率</b> = Σ min(抽到数, 需求量) / 资源消耗量</li>
        <li><b>每目标卡资源消耗</b> <b>↓</b> = 资源消耗量 / Σ min(抽到数, 需求量)</li>
        <li><b>额外目标卡</b> = Σ max(抽到数 - 需求量, 0)</li>
    </ul>

    <h5>抽卡过程类</h5>
    <ul>
        <li><b>非保底抽卡数</b> = 总抽数 - 保底触发次数</li>
        <li><b>保底抽卡数</b> = 保底触发次数</li>
        <li><b>目标卡出数</b> = Σ 抽到数（不按需求量截断，含溢出）</li>
        <li><b>每池下池出卡率</b> = Σ 池内目标卡抽到次数 / 有抽卡记录的池数</li>
    </ul>

    <h5>加权综合类</h5>
    <ul>
        <li><b>加权满意度</b> = Σ [ min(抽到, 需求) × 抽取意愿 - max(需求-抽到, 0) × 错失代价 ]</li>
        <li><b>总出卡价值</b> = Σ (抽到数 × 出卡价值权重)</li>
        <li><b>专武角色比</b> = 已获取专武数 / 已获取角色数</li>
    </ul>

    <h4>脆弱性分析</h4>
    <p>对每个池子，使用三阶段管线估计条件失败概率 P(失败 | 资源剩余)：</p>
    <ol>
        <li><b>binsglm 分位数分箱</b>（CCFF 2024）——IMSE 准则自动选择箱数</li>
        <li><b>PAVA 保序估计</b>——单调递减约束下合并采样逆向波动，输出分段常数保序估计</li>
        <li><b>Bootstrap 变更点推断</b>——ĵ* = max{j: θ̃_j &gt; α}，构造 95% 变更点置信区间</li>
    </ol>
    <p>脆弱区间右界取变更点 CI 上界（保守端），左界固定为第一个分箱左界。单调递减作为可检验的结构假设。</p>

    <h4>过程分析</h4>
    <p>对每次模拟的每个池子推断事件类型（7种）：保底命中、提前出货、未出、跳过、忽略、兑换、未兑换。四种交叉统计：AA（事件模式）、BB（成败模式）、AB（事件→成败）、BA（成败→事件）。</p>

    <h4>Bootstrap 稳定性分析</h4>
    <p>对已有模拟结果做有放回重抽样（B=1000），估计统计量的抽样分布和置信区间，<b>零额外模拟成本</b>。支持标准 Bootstrap、BCa、m-out-of-n、参数 GPD Bootstrap。</p>

    <h4>方案搜索</h4>
    <ul>
        <li><b>起点选择</b>：完整时间线 或 退路点（从指定池开始）</li>
        <li><b>最少资源</b>：成功率 ≥ 阈值约束下二分搜索最小额外资源</li>
        <li><b>最多目标卡</b>：固定资源预算下最大化目标卡数量（前进法/后退法）</li>
        <li><b>Pareto 权衡曲线</b>：枚举目标集大小，描绘资源投入与目标数量的权衡边界</li>
    </ul>

    <h4>最差影响分析</h4>
    <p>基于条件资源分布，计算失败组资源的 α 分位数（VaR），评估最差情况下剩余资源能支撑多少个后续池子。</p>

    <h4>风险分析 / EVT 尾部拟合</h4>
    <ul>
        <li><b>VaR/CVaR</b>：极端分位数（p ≤ 0.1 或 p ≥ 0.9）使用广义 Pareto 分布（GPD）外推，非极端使用经验方法</li>
        <li><b>Peaks Over Threshold（POT）</b>：自适应阈值保证 100-500 个超额样本</li>
        <li><b>MLE 正则性检查</b>：形状参数 ξ &lt; -1 强制回退经验方法</li>
    </ul>

    <h4>转移矩阵</h4>
    <p>计算相邻池子之间成功/失败状态的 2×2 转移概率矩阵，分析池间成败依赖关系。</p>
  `,

  // ── Tab 4：策略行为说明 ──
  strategy: `
    <h3>策略行为说明</h3>
    <p>以下逐一说明每种策略的决策逻辑。所有策略均为<b>一阶启发式</b>（仅检查当前状态，不递归评估未来价值）。</p>
    <p><b>通用规则</b>：所有策略优先检查兑换池——若目标卡可通过兑换获得且兑换池可用，优先执行兑换。兑换检查失败后才进入各自的抽卡逻辑。</p>

    <h4>1. 按需追卡 (smart)</h4>
    <p><b>一句话</b>：当前池里有我还缺少的目标卡 → 抽；没有 → 等到池子过期。</p>
    <p><b>适用场景</b>：用户有明确的目标卡列表，只想为缺少的卡投入资源。</p>
    <p><b>局限</b>：不比较池间优劣——两个池子同时开且都含目标卡时，按遍历顺序选第一个。</p>

    <h4>2. 指定池配额 (pool_quota)</h4>
    <p><b>一句话</b>：每个池子抽够指定数量就停手。</p>
    <p><b>参数</b>：<code>pool_quotas</code>——字典，key=池ID，value=该池最多抽多少次。</p>
    <p><b>适用场景</b>：限制每个池子的投入上限（如「角色池最多 50 抽，武器池最多 30 抽」）。</p>

    <h4>3. 保底预留 (pity_reserve)</h4>
    <p><b>一句话</b>：保底快到了才抽，否则憋着。</p>
    <p><b>参数</b>：<code>pity_threshold_pct</code>——保底概率阈值（百分比，默认 80%）。</p>
    <p><b>适用场景</b>：资源极度紧缺时最大化 SSR 期望产出。</p>
    <p><b>局限</b>：可能错过提前出货的机会；保底一直不到阈值就长期不抽、可能池子过期。</p>

    <h4>4. 目标即停 (stop_on_target)</h4>
    <p><b>一句话</b>：抽到目标就立即停手，见好就收。</p>
    <p><b>参数</b>：<code>stop_on_featured</code>（默认开）、<code>stop_on_any_target</code>（默认关）。</p>
    <p><b>适用场景</b>：模拟「抽到一个就跑」的玩家行为。</p>

    <h4>5. 指定池追卡 (target_hunting)</h4>
    <p><b>一句话</b>：只在用户指定的那几个池子里抽。</p>
    <p><b>参数</b>：<code>target_pool_ids</code>——目标池 ID 列表。</p>
    <p><b>适用场景</b>：只想抽特定限定池，完全无视非目标池。</p>
    <p><b>局限</b>：不检查目标卡需求——即使目标卡已满也会继续抽。</p>

    <h4>6. 固定次数 (fixed_count)</h4>
    <p><b>一句话</b>：抽满 N 次就停，不管结果。</p>
    <p><b>参数</b>：<code>count</code>——抽卡总次数。</p>
    <p><b>适用场景</b>：模拟固定预算下的期望结果，或作为对照基线。</p>

    <h4>7. 不抽卡基线 (no_draw)</h4>
    <p><b>一句话</b>：一次都不抽，只积累每日资源。</p>
    <p><b>适用场景</b>：计算资源累积的基线水平。此策略为内部使用，不开放用户选择。</p>
  `,
}

// 版本历史：VERSION_HISTORY 行（后端提供）→ HTML 表
export function versionRowsHtml(history) {
  if (!Array.isArray(history) || !history.length) return '<p>暂无版本记录</p>'
  const rows = history.map(([ver, date, desc]) => `<tr><td><b>${ver}</b></td><td>${date}</td><td>${desc}</td></tr>`).join('')
  return `
    <h3>版本历史</h3>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:100%">
    <tr style="background:#f0f0f0;"><th>版本</th><th>日期</th><th>说明</th></tr>
    ${rows}
    </table>

    <h4>版本号规则 — Pride Versioning</h4>
    <p>版本号格式：<b>PROUD.DEFAULT.SHAME</b></p>
    <ul>
        <li><b>PROUD</b>：做出让你自豪的变更时递增（递增时重置后两位为 0）</li>
        <li><b>DEFAULT</b>：普通发布时递增</li>
        <li><b>SHAME</b>：修复令人尴尬的 bug 时递增</li>
    </ul>
    <p>每次递增高位时，低位归零。PROUD 递增时 DEFAULT 和 SHAME 归零；DEFAULT 递增时 SHAME 归零。</p>
  `
}
