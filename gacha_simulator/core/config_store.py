import datetime as _dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from .strategy import strategy_type_to_key, STRATEGY_REGISTRY


@dataclass
class PoolDistEntry:
    card_id: str
    probability: float
    rarity: str = 'R'
    featured: bool = False
    resources_gained: Dict[str, float] = field(default_factory=dict)
    first_time_bonus: Dict[str, float] = field(default_factory=dict)
    nth_time_bonus: Dict[str, Any] = field(default_factory=dict)
    excess_bonus: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PoolEntry:
    enabled: bool = True
    pool_id: str = ''
    name: str = ''
    pool_type: str = ''
    start_day: int = 0
    end_day: int = 21
    cost: str = 'draw_resource:160'
    distribution_template: str = ''
    bindings: Dict[str, str] = field(default_factory=dict)
    target_specs: List[tuple] = field(default_factory=list)
    rerun_of: Optional[str] = None
    exchange_card_id: Optional[str] = None
    distribution: List[PoolDistEntry] = field(default_factory=list)
    batch_size: int = 1
    featured_card_ids: List[str] = field(default_factory=list)       # ← P60：池子级别 featured 卡 ID 聚合


@dataclass
class PityDef:
    name: str
    btype: str = 'soft'
    params: Dict[str, str] = field(default_factory=dict)
    target_distribution: Dict[str, float] = field(default_factory=dict)
    reset_condition: str = 'any_ssr'
    pools: str = '*'


@dataclass
class PityConfig:
    enabled: bool = True
    pities: List[PityDef] = field(default_factory=list)
    counter_init: Dict[str, int] = field(default_factory=dict)


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


@dataclass
class CardWeightEntry:
    desire_weight: float = 1.0
    miss_cost_weight: float = 1.0
    card_value: float = 1.0


@dataclass
class ConfigStore:
    card_defs: List[CardDefEntry] = field(default_factory=list)
    resource_defs: Dict[str, str] = field(default_factory=dict)
    pools: List[PoolEntry] = field(default_factory=list)
    pity: PityConfig = field(default_factory=PityConfig)
    gain_rules: List[GainRule] = field(default_factory=list)
    day_overrides: List[DayOverride] = field(default_factory=list)
    initial_resources: Dict[str, float] = field(default_factory=dict)
    target_cards: List[TargetCardEntry] = field(default_factory=list)
    strategy_type: str = '按需追卡'
    strategy_name: str = 'smart'
    strategy_params: Dict[str, Any] = field(default_factory=dict)
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

    def __post_init__(self):
        if self.strategy_type:
            if self.strategy_type in STRATEGY_REGISTRY:
                self.strategy_name = self.strategy_type
            else:
                resolved = strategy_type_to_key(self.strategy_type)
                if resolved != self.strategy_name:
                    self.strategy_name = resolved

    def clear(self):
        self.card_defs.clear()
        self.resource_defs.clear()
        self.pools.clear()
        self.pity = PityConfig()
        self.gain_rules.clear()
        self.day_overrides.clear()
        self.initial_resources.clear()
        self.target_cards.clear()
        self.strategy_type = '按需追卡'
        self.strategy_name = 'smart'
        self.strategy_params.clear()
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

    def is_limited(self, card_id: str) -> bool:
        """推导属性：这张卡是否至少在某个池子被 featured 过。

        遍历所有池子的 featured_card_ids 字段（池子级别聚合），不依赖卡名命名约定。
        """
        for pool in self.pools:
            if card_id in pool.featured_card_ids:
                return True
        return False

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
