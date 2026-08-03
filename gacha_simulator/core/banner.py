"""Banner 生命周期与复合池——P61 核心数据结构。

Banner 是用户配置的一等单元，内含多个 Pool（单活跃池模型，§3.13.5：
active_pool_id 是唯一阶段状态，无 phase 概念）。生命周期转换由声明式
TransitionRule 描述，边缘触发（edge-triggered），由 after_draw 事件订阅
（P61 priority=1）触发 _check_transitions——单一触发点（ISSUE-001）。

时间单位规范（ISSUE-001）：available_from / available_until 与 time_window
阈值 at_value 均以秒存储/求值，与模拟层 real_time 一致；TOML/UI 层「天数」
在解析/保存边界换算 * DAY / // DAY。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

DAY = 86400


@dataclass
class TransitionRule:
    """声明式转换规则：条件满足 → 切换到 target 池（或终结 Banner）。

    触发语义：边缘触发——条件从 False→True 转变的那次评估执行一次；
    持续满足不重复；条件回落后再满足可重新触发。
    """

    condition: str                   # "pool_draws" | "banner_draws" | "card_obtained"
                                     # | "pool_exhausted" | "time_window"
    pool: Optional[str] = None       # 条件关联的 pool id（card_obtained 时为匹配目标）
    at_value: float = 0.0            # 阈值。time_window 为浮点秒（运行时单位）；抽数条件为整数
    match: str = "card_id"           # card_obtained 匹配方式："card_id" | "rarity"
    action: str = "switch_to"        # "switch_to" | "exhaust_banner"
    target: Optional[str] = None     # 切换目标 pool id（action=switch_to 时必填）
    _prev_satisfied: bool = False    # 上次评估时的条件满足状态（引擎维护，非配置字段）


@dataclass
class TransitionPreview:
    """策略可读的进度信息——「还差多少触发什么」。"""

    trigger: str                     # 触发条件类型
    remaining: int                   # 还差多少。阈值型为剩余抽数/天数；事件型为 -1（不可预估）
    at_value: float                  # 阈值（time_window 为秒；抽数条件为整数）
    current_value: int               # 当前进度
    action: str                      # "switch_to" | "exhaust_banner"
    description: str                 # 人类可读描述
    target_pool: Optional[str] = None
    switches_current: bool = False   # 触发后当前活跃池是否被停用（switch_to 且 target != 当前池）


@dataclass
class DrawOutcome:
    """单抽结果——携带本次实际产出的池与保底判定。

    pool_id 为 Banner.pools 字典键（非 Pool.id）——全限定统计键由调用方
    f"{banner.id}.{pool_id}" 拼接（§3.5 要点 11，ISSUE-021）。
    """

    reward: object
    pool_id: str
    pity_triggered: bool
    triggered_pity_name: Optional[str] = None


@dataclass
class Banner:
    """卡池——用户配置的一等单位。

    pools: Dict[str, Pool]——pool 字典键（'main'/'free_10pull'/'step1'）→ Pool。
    单活跃池模型：切换即停用旧池 + 激活新池。
    """

    id: str
    name: str
    pools: Dict[str, object]
    lifecycle: List[TransitionRule] = field(default_factory=list)
    max_draws: Optional[int] = None                 # Banner 级总抽数硬上限（自动 exhaust）
    available_from: Optional[float] = None          # 时间窗口起点（秒）
    available_until: Optional[float] = None         # 时间窗口终点（秒）

    # 运行时状态
    _active_pool_id: str = field(init=False)
    _exhausted_pools: Set[str] = field(default_factory=set)
    _pool_draws: Dict[str, int] = field(default_factory=dict)
    _total_draws: int = 0
    _exhausted: bool = False

    def __post_init__(self):
        if not self.pools:
            raise ValueError(f"Banner '{self.id}' has no pools")
        if 'main' in self.pools:
            self._active_pool_id = 'main'
        else:
            self._active_pool_id = next(iter(self.pools))

    # ── 可用性 ──

    def is_available(self, real_time: float) -> bool:
        """可用性判定——显式传入当前模拟时间 real_time（秒）。

        时间窗口未开（real_time < available_from）与已关（real_time > available_until）
        的 Banner 均返回 False、不进入 active_banners；exhausted 后亦为 False。
        """
        return (not self._exhausted
                and (self.available_from is None or real_time >= self.available_from)
                and (self.available_until is None or real_time <= self.available_until))

    @property
    def is_exhausted(self) -> bool:
        return self._exhausted

    @property
    def active_pool(self):
        """当前活跃的 Pool 对象。"""
        return self.pools[self._active_pool_id]

    @property
    def active_pool_id(self) -> str:
        return self._active_pool_id

    @property
    def total_draws(self) -> int:
        """该 Banner 的总抽数（跨 pool 聚合）。"""
        return self._total_draws

    @property
    def pool_draws(self) -> Dict[str, int]:
        """每个 pool 的抽数（裸池字典键）。"""
        return dict(self._pool_draws)

    # ── 待处理转换 ──

    def pending_transitions(self, real_time: float) -> List[TransitionPreview]:
        """返回全部 lifecycle 规则的进度预览，按 remaining 升序（-1 不可预估项排最后）。

        事件型（card_obtained / pool_exhausted）无法预估剩余抽数 → remaining=-1，
        策略必须 `pt.remaining >= 0` 守卫后再做垫刀决策（ISSUE-305）。
        time_window 的 remaining 为向上取整剩余天数：max(0, ceil((at_value - real_time) / DAY))。
        """
        if self._exhausted:
            return []
        previews: List[TransitionPreview] = []
        active_key = self._active_pool_id
        for rule in self.lifecycle:
            c = rule.condition
            switches_current = (
                rule.action == 'switch_to'
                and rule.target is not None
                and rule.target != active_key
            )
            if c == 'pool_draws':
                cur = self._pool_draws.get(rule.pool, 0)
                remaining = max(0, int(rule.at_value) - cur)
                previews.append(TransitionPreview(
                    trigger='pool_draws', remaining=remaining, at_value=rule.at_value,
                    current_value=cur, action=rule.action,
                    description=f"池 '{rule.pool}' 抽 {cur}/{int(rule.at_value)} 次后"
                                f"({'切换' if rule.action == 'switch_to' else '关闭'})",
                    target_pool=rule.target, switches_current=switches_current,
                ))
            elif c == 'banner_draws':
                cur = self._total_draws
                remaining = max(0, int(rule.at_value) - cur)
                previews.append(TransitionPreview(
                    trigger='banner_draws', remaining=remaining, at_value=rule.at_value,
                    current_value=cur, action=rule.action,
                    description=f"Banner 抽 {cur}/{int(rule.at_value)} 次后"
                                f"({'切换' if rule.action == 'switch_to' else '关闭'})",
                    target_pool=rule.target, switches_current=switches_current,
                ))
            elif c == 'time_window':
                remaining = max(0, -(-(rule.at_value - real_time) // DAY)) \
                    if rule.at_value > real_time else 0
                cur = int(real_time // DAY)
                previews.append(TransitionPreview(
                    trigger='time_window', remaining=remaining, at_value=rule.at_value,
                    current_value=cur, action=rule.action,
                    description=f"等待 {remaining} 天后"
                                f"({'切换' if rule.action == 'switch_to' else '关闭'})",
                    target_pool=rule.target, switches_current=switches_current,
                ))
            else:  # card_obtained / pool_exhausted 事件型
                previews.append(TransitionPreview(
                    trigger=c, remaining=-1, at_value=rule.at_value,
                    current_value=0, action=rule.action,
                    description='事件触发' + ('（出卡）' if c == 'card_obtained' else '（池耗尽）'),
                    target_pool=rule.target, switches_current=switches_current,
                ))
        previews.sort(key=lambda p: p.remaining if p.remaining >= 0 else float('inf'))
        return previews

    # ── 核心方法 ──

    def draw(self, state, pity_engine, pity_state, pool: Optional[object] = None) -> DrawOutcome:
        """路由到活跃 pool（或显式传入 pool）执行单抽。

        1) excludes_all_pity → 旁路 before_draw/after_draw，不触碰 pity_state，
           DrawOutcome.pity_triggered 恒 False、triggered_pity_name 恒 None
        2) 正常 pool → P55 概率聚合（aggregate_probs_by_rarity）→ before_draw 调整
           → scale_factors 还原卡级概率 → _apply_probabilities → pool.draw() → after_draw
        3) 计算 pity_triggered + triggered_pity_name（featured_ids 判定 + spec.pity_names 拼接）

        转换【不】在此评估——统一由 after_draw 事件订阅（P61 priority=1）触发
        _check_transitions，转换只影响下一抽（ISSUE-001 单一触发点）。
        draw() 内部唯一的状态变化：当抽 pool 达 max_draws 标记 exhausted、
        Banner 级 max_draws 自动 exhaust。
        """
        from .pool import aggregate_probs_by_rarity, infer_rarity_from_spec

        pool = pool or self.active_pool
        pool_key = self._pool_key_of(pool)
        qualified_key = f"{self.id}.{pool_key}"

        probabilities = {r.id: p for r, p in pool.rewards}
        pity_triggered = False
        triggered_pity_name = None

        if pool.excludes_all_pity or pity_engine is None:
            # 保底旁路（excludes_all_pity）或无引擎：不调 before_draw/after_draw、
            # 不触碰 pity_state、不查询 spec/featured_ids（ISSUE-320）
            pool._apply_probabilities(probabilities)
            reward = pool.draw()
        else:
            pity_spec = pity_engine.get_spec(qualified_key)
            rarity_probs = aggregate_probs_by_rarity(pool, pity_spec) if pity_spec else probabilities
            adjusted_rarity = pity_engine.before_draw(qualified_key, pity_state, rarity_probs)
            if rarity_probs != adjusted_rarity:
                # 从聚合概率还原为卡牌级别概率——区分 featured/standard 槽位
                scale_factors = {}
                for slot, new_total in adjusted_rarity.items():
                    old_total = rarity_probs.get(slot, 0)
                    if old_total > 0 and new_total != old_total:
                        scale_factors[slot] = new_total / old_total
                featured_ids: Set[str] = set()
                if pity_spec and pity_spec.featured_cards:
                    for cards in pity_spec.featured_cards.values():
                        featured_ids.update(cards)
                for rwd_id in list(probabilities.keys()):
                    if rwd_id in featured_ids:
                        slot = f'{infer_rarity_from_spec(rwd_id, pity_spec) or "ssr"}_featured'
                    else:
                        rarity = infer_rarity_from_spec(rwd_id, pity_spec)
                        slot = rarity.lower() if rarity else None
                    if slot and slot in scale_factors:
                        probabilities[rwd_id] *= scale_factors[slot]
            pool._apply_probabilities(probabilities)
            reward = pool.draw()
            pity_engine.after_draw(qualified_key, pity_state, reward.id)
            # 保底触发判定：本次抽到的卡满足重置条件（featured SSR）
            if pity_spec and reward.id in pity_spec.featured_ids and pity_spec.pity_names:
                pity_triggered = True
                triggered_pity_name = ','.join(pity_spec.pity_names)

        # 抽数自增
        self._pool_draws[pool_key] = self._pool_draws.get(pool_key, 0) + 1
        self._total_draws += 1

        # pool.max_draws 耗尽判定（硬上限，标记后立即生效——批次中途由 batch 循环守卫 break）
        if pool.max_draws is not None and self._pool_draws[pool_key] >= pool.max_draws:
            self._exhausted_pools.add(pool_key)

        # banner.max_draws 自动 exhaust（硬上限守卫，不评估 lifecycle 规则）
        if self.max_draws is not None and self._total_draws >= self.max_draws:
            self._exhaust()

        return DrawOutcome(
            reward=reward,
            pool_id=pool_key,
            pity_triggered=pity_triggered,
            triggered_pity_name=triggered_pity_name,
        )

    def _check_transitions(self, card_id: Optional[str] = None,
                           real_time: Optional[float] = None):
        """评估全部 lifecycle 规则，条件满足（边缘触发）时执行 switch_to / exhaust_banner。

        由 after_draw 事件订阅触发（P61 priority=1）或等待期 WaitAction 分支触发——
        不直接由 Banner.draw 调用，避免同一次抽卡后 _check_transitions 被评估两次。

        输入来源：card_obtained 需本抽产出 card_id（订阅 handler 透传）；
        time_window 需当前模拟 real_time（handler 从 state 取）。
        兜底语义（ISSUE-010）：活跃池因 max_draws 耗尽且无 pool_exhausted 规则接管时，
        Banner 自动 exhaust（避免路由到已耗尽池产生未定义行为）。
        """
        handled_pool_exhausted = False
        for rule in self.lifecycle:
            satisfied = self._eval_rule(rule, card_id, real_time)
            if satisfied and not rule._prev_satisfied:
                rule._prev_satisfied = True
                if rule.action == 'switch_to':
                    if rule.condition == 'pool_exhausted':
                        handled_pool_exhausted = True
                    self._switch_to(rule.target)
                elif rule.action == 'exhaust_banner':
                    self._exhaust()
                    return
            elif not satisfied:
                rule._prev_satisfied = False

        # 兜底：活跃池已耗尽且无 pool_exhausted 规则接管 → 自动 exhaust
        if self._active_pool_id in self._exhausted_pools and not handled_pool_exhausted:
            self._exhaust()

    # ── 内部辅助 ──

    def _pool_key_of(self, pool) -> str:
        """反查 Pool 对象在 self.pools 字典中的键。"""
        for key, p in self.pools.items():
            if p is pool:
                return key
        raise ValueError(f"Pool object not found in Banner '{self.id}'")

    def _eval_rule(self, rule: TransitionRule, card_id: Optional[str],
                   real_time: Optional[float]) -> bool:
        c = rule.condition
        if c == 'pool_draws':
            return self._pool_draws.get(rule.pool, 0) >= rule.at_value
        if c == 'banner_draws':
            return self._total_draws >= rule.at_value
        if c == 'pool_exhausted':
            target = rule.pool if rule.pool is not None else self._active_pool_id
            return target in self._exhausted_pools
        if c == 'card_obtained':
            if card_id is None:
                return False
            if rule.match == 'card_id':
                return card_id == rule.pool
            if rule.match == 'rarity':
                rarity = self._rarity_of(card_id)
                return rarity is not None and rarity == rule.pool
            return False
        if c == 'time_window':
            if real_time is None:
                return False
            return real_time >= rule.at_value
        return False

    def _rarity_of(self, card_id: str) -> Optional[str]:
        """从 Banner 全部 pool 的 rewards 反查卡牌稀有度（match='rarity' 数据源）。

        数据源为 Reward.extra_info['rarity']（小写归一化，ISSUE-306/007）。
        """
        seen = set()
        for p in self.pools.values():
            for r, _ in p.rewards:
                if r.id in seen:
                    continue
                seen.add(r.id)
                if r.id == card_id:
                    rarity = (r.extra_info or {}).get('rarity')
                    return str(rarity).lower() if rarity is not None else None
        return None

    def _switch_to(self, pool_id: Optional[str]):
        """停用当前活跃池 + 激活 target。"""
        if pool_id is None or pool_id not in self.pools:
            raise ValueError(
                f"Banner '{self.id}' switch_to 目标池 '{pool_id}' 不存在于 pools 字典"
            )
        self._active_pool_id = pool_id

    def _exhaust(self):
        """终结 Banner——is_available=False、策略侧 is_exhausted=True。"""
        self._exhausted = True
        self._exhausted_pools.update(self.pools.keys())
