from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
import random
import bisect
from itertools import product


NO_CARD_ID = "_no_card"

CostOption = Dict[str, float]
PoolCost = List[CostOption]


def _parse_atom(token: str) -> CostOption:
    result: CostOption = {}
    for part in token.split('&'):
        part = part.strip()
        if ':' in part:
            rid, amt = part.split(':', 1)
            result[rid.strip()] = float(amt.strip())
    return result


def _tokenize(cost_str: str) -> List[str]:
    """将 cost 字符串按逗号或大于号切分为 OR 分支。

    `,` 和 `>` 语义相同——均表示按书写顺序的强制优先级：
    列表靠前的选项会被优先尝试，付不起才回退到后续选项。
    `>` 仅用于提升可读性（显式表达优先级意图）。
    """
    tokens = []
    current = []
    depth = 0
    for ch in cost_str:
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch in (',', '>') and depth == 0:
            tokens.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    tail = ''.join(current).strip()
    if tail:
        tokens.append(tail)
    return tokens


def _strip_parens(s: str) -> str:
    s = s.strip()
    while s.startswith('(') and s.endswith(')'):
        depth = 0
        matched = True
        for i, ch in enumerate(s):
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            if depth == 0 and i < len(s) - 1:
                matched = False
                break
        if matched:
            s = s[1:-1].strip()
        else:
            break
    return s


def _parse_cost_expr(cost_str: str) -> PoolCost:
    cost_str = _strip_parens(cost_str)
    if not cost_str:
        return []

    or_tokens = _tokenize(cost_str)
    if len(or_tokens) > 1:
        result = []
        for token in or_tokens:
            result.extend(_parse_cost_expr(token))
        return result

    depth = 0
    and_positions = []
    for i, ch in enumerate(cost_str):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == '&' and depth == 0:
            and_positions.append(i)

    if not and_positions:
        atom = _parse_atom(cost_str)
        return [atom] if atom else []

    parts = []
    prev = 0
    for pos in and_positions:
        parts.append(cost_str[prev:pos])
        prev = pos + 1
    parts.append(cost_str[prev:])

    parsed_parts = [_parse_cost_expr(p) for p in parts]

    result = []
    for combo in product(*parsed_parts):
        merged: CostOption = {}
        for option in combo:
            for rid, amt in option.items():
                merged[rid] = merged.get(rid, 0) + amt
        if merged:
            result.append(merged)
    return result


def parse_cost_string(cost_str: str) -> PoolCost:
    if not cost_str:
        return []
    return _parse_cost_expr(cost_str)


def cost_to_string(cost: PoolCost) -> str:
    """将 PoolCost 序列化为字符串，OR 分支用 `>` 连接以表达优先级语义。"""
    parts = []
    for option in cost:
        sub_parts = [f"{rid}:{amt}" for rid, amt in option.items()]
        parts.append('&'.join(sub_parts))
    return ' > '.join(parts)


@dataclass
class Reward:
    id: str
    name: str
    resources_gained: Dict[str, float] = field(default_factory=dict)
    extra_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Pool:
    """Banner 内部的独立抽取单元——自包含，不引用外部。

    P61（§3.13.1）：output / random / is_exchange 为推导 property（从 rewards 计算），
    非配置字段。tuple 表示假定概率已归一化 0-1（ISSUE-319）。
    """

    id: str
    name: str
    cost: PoolCost
    rewards: List[Tuple[Reward, float]]
    excludes_all_pity: bool = False   # ← P61：完全旁路保底引擎
    max_draws: Optional[int] = None   # ← P61：该 pool 最大抽取次数（引擎自动执行耗尽）；None=无上限
    exchange_card_id: Optional[str] = None
    batch_size: int = 1
    epitomizable_cards: list = field(default_factory=list)           # ← P56

    @property
    def output(self) -> str:
        """产出类型：'card'（抽卡）| 'resource'（产出资源）。"""
        return 'resource' if all(r.id == NO_CARD_ID for r, _ in self.rewards) else 'card'

    @property
    def random(self) -> bool:
        """产出是否随机：True（概率抽取）| False（确定性兑换/固定产出）。

        空 rewards 显式短路为 False，避免 rewards[0] 对空列表索引抛 IndexError。
        """
        if not self.rewards:
            return False
        return len(self.rewards) > 1 or self.rewards[0][1] < 1.0

    @property
    def is_exchange(self) -> bool:
        """兑换池：output='card' 且确定性（100% 指定卡）。"""
        return self.output == 'card' and not self.random

    def __post_init__(self):
        if not self.is_exchange and self.rewards:
            self._reward_list = [r for r, _ in self.rewards]
            self._cum_weights = []
            total = 0.0
            for _, p in self.rewards:
                total += p
                self._cum_weights.append(total)
            self._total_weight = total
        else:
            self._reward_list = []
            self._cum_weights = []
            self._total_weight = 0.0

        self._adjusted_cum_weights = None
        self._adjusted_total_weight = None
        self._use_adjusted = False

    def _apply_probabilities(self, probabilities: Dict[str, float]):
        self._adjusted_cum_weights = []
        total = 0.0
        for reward in self._reward_list:
            prob = probabilities.get(reward.id, 0.0)
            total += prob
            self._adjusted_cum_weights.append(total)
        self._adjusted_total_weight = total
        self._use_adjusted = True

    def draw(self) -> Reward:
        if self.is_exchange:
            if not self.rewards:
                raise ValueError(f"Exchange pool {self.id} has no rewards")
            return self.rewards[0][0]
        
        if self._use_adjusted and self._adjusted_cum_weights and self._adjusted_total_weight > 0:
            r = random.random() * self._adjusted_total_weight
            idx = bisect.bisect_left(self._adjusted_cum_weights, r)
            if idx >= len(self._reward_list):
                idx = len(self._reward_list) - 1
            self._use_adjusted = False
            return self._reward_list[idx]
        
        if not self._cum_weights:
            raise ValueError(f"Pool {self.id} has no valid rewards")
        
        r = random.random() * self._total_weight
        idx = bisect.bisect_left(self._cum_weights, r)
        if idx >= len(self._reward_list):
            idx = len(self._reward_list) - 1
        return self._reward_list[idx]


# ── P61：P55 概率聚合模块级函数（下沉自 GachaService 方法，ISSUE-004）──
# Banner.draw 与 gacha_service 共用，只依赖 pool.rewards + PoolPitySpec 结构。

def infer_rarity_from_spec(card_id: str, pity_spec) -> Optional[str]:
    """从 PoolPitySpec 推断卡牌稀有度（大小写归一化）。"""
    cid = card_id.lower()
    if pity_spec.ssr_ids and cid in {c.lower() for c in pity_spec.ssr_ids}:
        return 'ssr'
    if pity_spec.featured_ids and cid in {c.lower() for c in pity_spec.featured_ids}:
        return 'ssr'
    return None


def aggregate_probs_by_rarity(pool: 'Pool', pity_spec) -> Dict[str, float]:
    """将 {card_id: prob} 聚合为槽位级别概率。

    P55 feature-slot 分离：若 PoolPitySpec.featured_cards 存在，
    则将 featured 卡牌的概率拆入独立槽位（如 'ssr_featured'），
    而非与 standard 卡牌共享同一 'ssr' 槽位。
    """
    result: Dict[str, float] = {}
    rarity_cache: Dict[str, Optional[str]] = {}

    # 预构建 card_id → rarity 映射（仅 standard 卡——featured 单独处理）
    featured_ids: set = set()
    if pity_spec and pity_spec.featured_cards:
        for rarity, cards in pity_spec.featured_cards.items():
            for cid in cards:
                featured_ids.add(cid)
    if pity_spec and pity_spec.scope_cards:
        for rarity, cards in pity_spec.scope_cards.items():
            for cid in cards:
                if cid not in featured_ids:
                    rarity_cache[cid] = rarity

    for rwd, prob in pool.rewards:
        cid = rwd.id
        if cid in featured_ids:
            # featured → 独立槽位
            rarity = infer_rarity_from_spec(cid, pity_spec) or 'ssr'
            slot = f'{rarity}_featured'
        else:
            rarity = rarity_cache.get(cid)
            if rarity is None and pity_spec:
                rarity = infer_rarity_from_spec(cid, pity_spec)
            if rarity:
                slot = rarity.lower()
            else:
                continue
        result[slot] = result.get(slot, 0.0) + prob

    return result

