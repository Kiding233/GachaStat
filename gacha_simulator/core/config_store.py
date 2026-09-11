import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from .overflow import OverflowBand
from .resource_lifecycle import ResourceLifecycleConfig

# P61：秒/天换算——Banner 时间窗口（秒，§3.13.4）与展平视图 start_day/end_day（天）换算。
# 每个模块自带一份（banner.py/resource_gain.py 等同口径），config_store 展平视图消费。
DAY = 86400


class ConfigError(ValueError):
    """配置解析或校验错误。"""


@dataclass
class PoolDistEntry:
    card_id: str
    probability: float
    rarity: str = 'R'
    featured: bool = False
    resources_gained: Dict[str, float] = field(default_factory=dict)


def derive_pool_type_from_distribution(dist) -> str:
    """由展平视图 distribution 推导旧 pool_type 三值（§3.13.1，ISSUE-002）。

    与 core/pool.py 的 output/random 推导语义等价，但消费扁平 PoolEntry.distribution
    （PoolDistEntry，概率百分制）：
      output = 'resource' if 全部 card_id == '_no_card' else 'card'（空列表同样视作 resource）
      random = bool(dist) and (len(dist) > 1 or dist[0].probability < 100.0)
    output='resource' → '资源'；output='card' and not random → '兑换'；其余 → '角色'。
    """
    output = 'resource' if all(d.card_id == '_no_card' for d in dist) else 'card'
    random = bool(dist) and (len(dist) > 1 or dist[0].probability < 100.0)
    if output == 'resource':
        return '资源'
    if output == 'card' and not random:
        return '兑换'
    return '角色'


@dataclass
class PoolEntry:
    enabled: bool = True
    pool_id: str = ''
    name: str = ''
    start_day: int = 0
    end_day: int = 21
    cost: str = 'draw_resource:160'
    distribution_template: str = ''
    bindings: Dict[str, str] = field(default_factory=dict)
    target_specs: List[tuple] = field(default_factory=list)
    exchange_card_id: Optional[str] = None
    distribution: List[PoolDistEntry] = field(default_factory=list)
    batch_size: int = 1
    featured_card_ids: List[str] = field(default_factory=list)
    epitomizable_cards: List[str] = field(default_factory=list)      # ← P56


# ── P61（Ph3）：Banner 数据模型 ─────────────────────────────────────
# store.banner 是运行时唯一数据源（D3/D4 裁决）。pool_type/rerun_of 已退役
# （§3.13.1 类型→推导属性 output/random、§3.13.2 复刻→卡出现时间线），
# BannerPoolEntry 不建模这两个字段。

@dataclass
class BannerPoolEntry:
    """Banner 内部池——从 TOML [[banner.pool]] 解析"""
    id: str                              # "main" | "free_10pull" | "step2"
    cost: str                            # TOML 字符串，如 "orundum:600"（必填）
    batch_size: int = 1                  # 每次抽取连数
    excludes_all_pity: bool = False
    max_draws: Optional[int] = None     # None=无上限；TOML/UI 层「0=无限制」在解析边界归一化为 None
    exchange_card_id: Optional[str] = None                  # 兑换快捷方式（同旧 [[pools]]，写入后生成 100% 单卡分布）
    epitomizable_cards: List[str] = field(default_factory=list)  # P56 定轨候选卡
    rewards: List[dict] = field(default_factory=list)       # [[banner.pool.reward]] 解析——元素统一为 dict
                                                            # （card_id/probability/rarity/featured/resources_gained）；
                                                            # 一次性迁移后 rewards 统一 dict 表示（ISSUE-304）
    # output/random 不配置——从 rewards 推导（见 §3.13.1）


@dataclass
class LifecycleRuleEntry:
    """声明式转换规则——从 TOML [[banner.lifecycle]] 解析"""
    condition: str                       # "pool_draws" | "banner_draws"
                                         # | "card_obtained" | "pool_exhausted"
                                         # | "time_window"
    pool: Optional[str] = None           # 条件关联的 pool id（card_obtained 时为匹配目标）
    at: float = 0.0                      # 阈值（pool_draws/banner_draws 为整数抽数；time_window 为浮点【秒】——
                                         # TOML/UI 层以「模拟内相对天数」书写、解析边界 *DAY 换算为秒）
    match: str = "card_id"               # card_obtained 的匹配方式："card_id" | "rarity"
    action: str = "switch_to"            # "switch_to" | "exhaust_banner"
    target: Optional[str] = None         # 切换目标 pool id（action=switch_to 时必填）


@dataclass
class BannerEntry:
    """单个 Banner 定义——从 TOML [[banner]] 解析"""
    id: str
    name: str
    enabled: bool = True            # banner 模式 enabled 语义：[[banner]] 的 pool 默认 enabled=True
    max_draws: Optional[int] = None     # None=无上限；TOML/UI 层「0=无限制」在解析/保存边界归一化为 None
    available_from: Optional[float] = None
    available_until: Optional[float] = None
    pools: List[BannerPoolEntry] = field(default_factory=list)
    lifecycle: List[LifecycleRuleEntry] = field(default_factory=list)
    # P77：归一前原始「永久池」标记（TOML 缺 end_day）。归一后 available_until 恒非 None，
    # 无法据此区分永久池，故保留原始标记供 expire_with_banner 校验与 GUI 下拉过滤同口径判定。
    _is_permanent: bool = False


@dataclass
class BannerConfig:
    """Banner 配置容器"""
    banners: List[BannerEntry] = field(default_factory=list)


@dataclass
class PityDef:
    """P55 扁平化：23 个独立类型字段（原 PityDefParsed 6 字段 + param 分裂）。

    旧字段（params/target_distribution/reset_condition）已移除。
    counter_init 从 PityConfig 全局移至每条 PityDef。
    """
    name: str
    btype: str = 'soft'
    # ── 核心参数（按 btype 选填） ──
    scope: str = 'ssr'
    target_featured: bool = False
    deltas: Optional[tuple] = None             # soft_step 专用——RLE 分段
    threshold: Optional[int] = None            # hard 专用
    # ── 初始状态 ──
    counter_init: int = 0
    guaranteed_init: bool = False              # rotating 家族大保底初始状态
    fate_points_init: int = 0                  # targeted 家族命定值初始值
    selected_card_init: Optional[str] = None   # P56：targeted 家族初始定轨卡片 ID
    # ── 语法糖参数（解析后展开为 deltas） ──
    soft_start: Optional[int] = None           # soft_interval / soft_additive
    soft_end: Optional[int] = None             # soft_interval
    soft_increment: Optional[float] = None     # soft_additive
    soft_deltas: Optional[tuple] = None        # 展开前的原始 deltas
    # ── 事件驱动型参数（P56） ──
    cr_counter_threshold: Optional[int] = None
    cr_base_rate: Optional[float] = None
    cr_state_probs: Optional[tuple] = None
    fate_threshold: Optional[int] = None
    switch_allowed: bool = True
    switch_resets_progress: bool = True
    # ── 池子绑定 ──
    pools: tuple = ('*',)
    # ── 生命周期 ──
    deactivate_on_early_hit: bool = False
    depends_on: Optional[str] = None
    # ── 重置条件 ──
    reset: str = ''                            # '' → scope fallback


@dataclass
class PityConfig:
    enabled: bool = True
    pities: List[PityDef] = field(default_factory=list)
    # P55：counter_init 已移至每个 PityDef.counter_init


@dataclass
class MilestoneDef:
    """单条里程碑定义——从 TOML [[milestone]] 解析（P58）。

    threshold 触发阈值（抽数）；repeat=False 一次性（at=N）、repeat=True 周期（every=N）；
    max_triggers 最大触发次数（0=无限）；bonus_reward 三字段任意组合
    （cards / resources / random_cards）；banner 精确指向一个 Banner（空 = 全部，P61 协作）。
    P78：alternate_rewards 交替奖励序列（周期触发时按索引循环取奖励，空=原行为）；
    offset 首节点相位偏移（首节点 = threshold + offset，后续每 threshold，仅首节点生效）。
    """
    name: str
    threshold: int = 40
    repeat: bool = False
    max_triggers: int = 0
    bonus_reward: dict = field(default_factory=dict)
    banner: str = ""
    # ── P78 新增（全部带默认值，向后兼容）──
    alternate_rewards: List[dict] = field(default_factory=list)  # 交替奖励序列（空=原行为）
    offset: int = 0            # 首节点相位偏移（0=从 threshold 起，仅首节点生效）


@dataclass
class SelectVoucherDef:
    """自选券候选集定义（P78）——资源 id → 可兑换卡片显式列表。"""
    voucher: str            # 关联资源 id
    cards: List[str] = field(default_factory=list)   # 候选卡片显式列表


@dataclass
class MilestoneConfig:
    """里程碑配置容器（P58）。"""
    enabled: bool = True
    milestones: List[MilestoneDef] = field(default_factory=list)


@dataclass
class GainRule:
    rule_type: str = 'every_n_days'
    param: str = '1'
    gains: Dict[str, float] = field(default_factory=dict)


@dataclass
class DayOverride:
    day: int = 0
    gains: Dict[str, float] = field(default_factory=dict)


@dataclass
class TargetCardEntry:
    card_id: str
    quantity: int = 1
    pool_ids: List[str] = field(default_factory=list)


@dataclass
class CardDefEntry:
    card_id: str
    name: str = ''
    rarity: str = 'r'
    pools: List[str] = field(default_factory=list)
    initial_count: int = 0
    tags: Dict[str, str] = field(default_factory=dict)               # P65：单值标签
    list_tags: Dict[str, List[str]] = field(default_factory=dict)     # P65：多值标签
    overflow_bands: Optional[List[OverflowBand]] = None               # P63：卡片溢出分段表


@dataclass
class CardWeightEntry:
    desire_weight: float = 1.0
    miss_cost_weight: float = 1.0
    card_value: float = 1.0


@dataclass
class ConfigStore:
    card_defs: List[CardDefEntry] = field(default_factory=list)
    resource_defs: Dict[str, str] = field(default_factory=dict)
    banner: BannerConfig = field(default_factory=BannerConfig)
    pity: PityConfig = field(default_factory=PityConfig)
    milestone: MilestoneConfig = field(default_factory=MilestoneConfig)  # ← P58
    select_vouchers: List[SelectVoucherDef] = field(default_factory=list)  # ← P78：自选券候选集
    resource_lifecycle: ResourceLifecycleConfig = field(default_factory=ResourceLifecycleConfig)  # ← P77：限时货币生命周期
    gain_rules: List[GainRule] = field(default_factory=list)
    day_overrides: List[DayOverride] = field(default_factory=list)
    initial_resources: Dict[str, float] = field(default_factory=dict)
    target_cards: List[TargetCardEntry] = field(default_factory=list)
    strategy_key: str = 'smart'
    strategy_params: Dict[str, Any] = field(default_factory=dict)
    _unknown_strategy_raw: Optional[Dict[str, Any]] = None  # 未知 key 降级保留
    stop_condition_type: str = '所有池结束'
    stop_condition_params: Dict[str, Any] = field(default_factory=dict)
    auto_wait: bool = True
    card_weights: Dict[str, CardWeightEntry] = field(default_factory=dict)
    sim_start_date: str = field(default_factory=lambda: _dt.date.today().isoformat())
    simulation_count: int = 1000
    max_workers: int = 4
    seed: int = 42
    _distribution_templates: List[dict] = field(default_factory=list)
    rarity_rank: Dict[str, int] = field(default_factory=dict)       # ← P60：稀有度 → 层级（0=最高）
    rarity_defaults: Dict[str, Any] = field(default_factory=dict)    # ← P63：稀有度默认溢出规则（键名 .lower()）
    card_overflow_map: Dict[str, List[OverflowBand]] = field(default_factory=dict)  # ← P63：card_id → 分段表
    _migrated_from_legacy: bool = False                              # ← P55：旧格式迁移标记

    def __post_init__(self):
        # P69：strategy_type 字段已删除，strategy_name → strategy_key。
        # 旧 type→key 映射逻辑不再需要——TOML [strategy] 段直接使用 key。
        pass

    def clear(self):
        self.card_defs.clear()
        self.resource_defs.clear()
        self.banner.banners.clear()
        self.pity = PityConfig()
        self.milestone = MilestoneConfig()                            # ← P58
        self.select_vouchers.clear()                                   # ← P78
        self.resource_lifecycle = ResourceLifecycleConfig()            # ← P77：避免二次加载残留
        self.gain_rules.clear()
        self.day_overrides.clear()
        self.initial_resources.clear()
        self.target_cards.clear()
        self.strategy_key = 'smart'
        self.strategy_params.clear()
        self._unknown_strategy_raw = None
        self.stop_condition_type = '所有池结束'
        self.stop_condition_params.clear()
        self.auto_wait = True
        self.card_weights.clear()
        self.sim_start_date = _dt.date.today().isoformat()
        self.simulation_count = 1000
        self.max_workers = 4
        self.seed = 42
        self._distribution_templates.clear()
        self.rarity_rank.clear()                                      # ← P60
        self.rarity_defaults.clear()                                  # ← P63
        self.card_overflow_map.clear()                                # ← P63
        self._migrated_from_legacy = False                            # ← P55

    # ── P78 读取接口（ISSUE-603 契约）────────────────────────────────
    # GUI 回填（ISSUE-004）与校验（ISSUE-111/116）一律经此接口、禁止直读
    # store.select_vouchers 列表自行扫描。未注册 voucher id 与空候选集
    # 统一返回空列表 []（不抛异常），返回副本（不污染 store）。

    def get_select_voucher_candidates(self, voucher_id: str) -> List[str]:
        """按资源 id 取自选券候选集——未注册/空候选集返回空列表 []，返回副本。"""
        for sv in self.select_vouchers:
            if sv.voucher == voucher_id:
                return list(sv.cards)
        return []

    def is_select_voucher(self, voucher_id: str) -> bool:
        """该资源 id 是否注册为自选券。"""
        return any(sv.voucher == voucher_id for sv in self.select_vouchers)

    # ── P61（Ph3/D3 裁决）：store.pools 只读展平视图 ────────────────
    # store.banner 是运行时唯一数据源；pools 为只读 @property，遍历
    # banner.banners[*].pools[*] 展平为 PoolEntry 列表，供旧读侧消费方
    # （analysis_panel/gacha_panel/gdr 等）零改动读取。无 setter——
    # 写侧统一走 store.banner（config_toml/config_panel/retreat_config）。

    @property
    def pools(self) -> List[PoolEntry]:
        """只读展平视图：遍历 banner.banners[*].pools[*] → PoolEntry 列表。

        - pool_id = {banner_id}.{pool_id}（全限定键，与 card_defs.pools 同键空间，ISSUE-310）
        - name = banner.name（Banner 级 name 唯一，ISSUE-324）
        - start_day/end_day 由 available_from/until（秒）// DAY 换算（ISSUE-333）；
          end_day=None 透传（永久 Banner，ISSUE-002）
        - enabled/distribution/featured_card_ids/epitomizable_cards/exchange_card_id 逐项透传（ISSUE-314）
        - bindings 不透传（BannerPoolEntry 无该字段，ISSUE-334）
        """
        result: List[PoolEntry] = []
        for b in self.banner.banners:
            for bp in b.pools:
                result.append(self._flatten_banner_pool(b, bp))
        return result

    def _flatten_banner_pool(self, b: BannerEntry, bp: BannerPoolEntry) -> PoolEntry:
        """单个 banner pool → 展平 PoolEntry。"""
        return PoolEntry(
            enabled=b.enabled,
            pool_id=f"{b.id}.{bp.id}",
            name=b.name,
            start_day=int(b.available_from // DAY) if b.available_from is not None else 0,
            end_day=int(b.available_until // DAY) if b.available_until is not None else None,
            cost=bp.cost,
            distribution_template='',
            bindings={},
            target_specs=[],
            exchange_card_id=bp.exchange_card_id,
            distribution=[
                PoolDistEntry(
                    card_id=r['card_id'],
                    probability=r['probability'],
                    rarity=r.get('rarity', 'r'),
                    featured=r.get('featured', False),
                    resources_gained=dict(r.get('resources_gained', {})),
                )
                for r in bp.rewards
            ],
            batch_size=bp.batch_size,
            featured_card_ids=[r['card_id'] for r in bp.rewards if r.get('featured')],
            epitomizable_cards=list(bp.epitomizable_cards),
        )

    # ── GDR 权重便捷属性 ──────────────────────────────────────────
    # 从 card_weights 提取，供 make_gdr_calculator() 使用。
    # 调用方通过 store.xxx_weights 取值，无需手动搬运 UI 控件。

    @property
    def desire_weights(self):
        """Dict[str, float]: 每张目标卡的抽取意愿权重"""
        return {cid: cw.desire_weight for cid, cw in self.card_weights.items()}

    @property
    def miss_cost_weights(self):
        """Dict[str, float]: 每张目标卡的错失代价权重"""
        return {cid: cw.miss_cost_weight for cid, cw in self.card_weights.items()}

    @property
    def card_value_weights(self):
        """Dict[str, float]: 每张卡的卡牌价值权重"""
        return {cid: cw.card_value for cid, cw in self.card_weights.items()}

    # ── P60 新增：推导属性 + 稀有度解析 ──

    def _parse_rarities(self, data: dict) -> None:
        """从 TOML [rarities].ranks 生成 rarity_rank 映射。
        同一 rank 数组内为平级；rank 0 = 最高。
        默认值：[["SSR"], ["SR"], ["R"]]。
        """
        ranks = data.get("rarities", {}).get("ranks", [["SSR"], ["SR"], ["R"]])
        for rank_idx, tier in enumerate(ranks):
            for rarity_name in tier:
                self.rarity_rank[rarity_name.upper()] = rank_idx
        # 内部格式不变式校验——确保 rank 值连续无空洞
        assert max(self.rarity_rank.values(), default=-1) + 1 == len(set(self.rarity_rank.values())), \
            f"rarity_rank 值不连续：{self.rarity_rank}"
