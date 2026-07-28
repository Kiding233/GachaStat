"""Apply all P56 changes to pity.py at once."""
import os

f = 'gacha_simulator/core/pity.py'
c = open(f, encoding='utf-8').read()

changes = 0

# 1. Add import random
if 'import random' not in c:
    c = c.replace("import logging\n\nlogger", "import logging\nimport random\n\nlogger")
    changes += 1
    print('1. import random added')

# 2. Update DrawInfo - add featured_cards and card_to_slot
old_di = """    scope_cards: Mapping[str, tuple] = field(default_factory=dict)
    scope_slots: Mapping[str, tuple] = field(default_factory=dict)
    featured_slots: Mapping[str, tuple] = field(default_factory=dict)
    base_probabilities: Mapping[str, float] = field(default_factory=dict)"""
new_di = """    scope_cards: Mapping[str, tuple] = field(default_factory=dict)
    featured_cards: Mapping[str, tuple] = field(default_factory=dict)
    scope_slots: Mapping[str, tuple] = field(default_factory=dict)
    featured_slots: Mapping[str, tuple] = field(default_factory=dict)
    card_to_slot: Mapping[str, str] = field(default_factory=dict)
    base_probabilities: Mapping[str, float] = field(default_factory=dict)"""
if old_di in c:
    c = c.replace(old_di, new_di)
    changes += 1
    print('2. DrawInfo updated')

# 3. Update PoolPitySpec - add card_to_slot
old_ps = """    featured_slots: Dict[str, tuple] = field(default_factory=dict)"""
new_ps = """    featured_slots: Dict[str, tuple] = field(default_factory=dict)
    # P56: card_id -> slot name mapping
    card_to_slot: Dict[str, str] = field(default_factory=dict)"""
if old_ps in c and 'card_to_slot' not in c.split('class PoolPitySpec')[1].split('class')[0] if 'class PoolPitySpec' in c else True:
    c = c.replace(old_ps, new_ps)
    changes += 1
    print('3. PoolPitySpec updated')

# 4. Update compute_scope_mappings to 5-tuple
old_csm = '''def compute_scope_mappings(pool) -> tuple:
    """从池子的 Reward 列表预计算 scope_cards/featured_cards/scope_slots/featured_slots。

    P55 ISSUE-032：Reward.extra_info 含 'rarity'/'featured' 键，
    据此分组生成 DrawInfo 所需的槽位映射。

    featured SSR 与 standard SSR 分配**不同槽位**——使 target_featured
    的概率提升仅作用于 featured 卡牌，而非所有同稀有度卡牌。

    Returns:
        (scope_cards, featured_cards, scope_slots, featured_slots) 四元组 dict。
    """
    cards_by_rarity: Dict[str, list] = {}
    featured_by_rarity: Dict[str, list] = {}

    for rwd, _prob in getattr(pool, 'rewards', []):
        extra = getattr(rwd, 'extra_info', {}) or {}
        rarity = extra.get('rarity', '').lower()
        if not rarity:
            continue
        cards_by_rarity.setdefault(rarity, []).append(rwd.id)
        if extra.get('featured'):
            featured_by_rarity.setdefault(rarity, []).append(rwd.id)

    scope_cards = {r: tuple(cards) for r, cards in cards_by_rarity.items()}
    featured_cards = {r: tuple(cards) for r, cards in featured_by_rarity.items()}

    # 槽位映射——featured 拆分为独立槽位名（如 'ssr_featured'）
    scope_slots = {}
    featured_slots = {}
    for rarity in cards_by_rarity:
        if rarity in featured_by_rarity:
            featured_slot = f'{rarity}_featured'
            scope_slots[rarity] = (rarity, featured_slot)
            featured_slots[rarity] = (featured_slot,)
        else:
            scope_slots[rarity] = (rarity,)
            featured_slots[rarity] = (rarity,)

    return scope_cards, featured_cards, scope_slots, featured_slots'''

if old_csm in c:
    new_csm = '''def compute_scope_mappings(pool) -> tuple:
    """从池子的 Reward 列表预计算 scope_cards/featured_cards/scope_slots/featured_slots/card_to_slot。

    P55 ISSUE-032：Reward.extra_info 含 'rarity'/'featured' 键，
    据此分组生成 DrawInfo 所需的槽位映射。

    P56：返回值新增 card_to_slot（card_id → 槽位名），供 TargetedBehavior O(1) 查找。

    Returns:
        (scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot) 五元组 dict。
    """
    cards_by_rarity: Dict[str, list] = {}
    featured_by_rarity: Dict[str, list] = {}
    card_to_slot: Dict[str, str] = {}

    for rwd, _prob in getattr(pool, 'rewards', []):
        extra = getattr(rwd, 'extra_info', {}) or {}
        rarity = extra.get('rarity', '').lower()
        if not rarity:
            continue
        cards_by_rarity.setdefault(rarity, []).append(rwd.id)
        if extra.get('featured'):
            featured_by_rarity.setdefault(rarity, []).append(rwd.id)
            card_to_slot[rwd.id] = f'{rarity}_featured'
        else:
            card_to_slot[rwd.id] = rarity

    scope_cards = {r: tuple(cards) for r, cards in cards_by_rarity.items()}
    featured_cards = {r: tuple(cards) for r, cards in featured_by_rarity.items()}

    # 槽位映射——featured 拆分为独立槽位名（如 'ssr_featured'）
    scope_slots = {}
    featured_slots = {}
    for rarity in cards_by_rarity:
        if rarity in featured_by_rarity:
            featured_slot = f'{rarity}_featured'
            scope_slots[rarity] = (rarity, featured_slot)
            featured_slots[rarity] = (featured_slot,)
        else:
            scope_slots[rarity] = (rarity,)
            featured_slots[rarity] = (rarity,)

    return scope_cards, featured_cards, scope_slots, featured_slots, card_to_slot'''
    c = c.replace(old_csm, new_csm)
    changes += 1
    print('4. compute_scope_mappings updated')
else:
    print('WARN: compute_scope_mappings pattern not found')

# 5. Insert all new classes after HardPityBehavior._on_reset, before BEHAVIOR_REGISTRY
insertion_marker = '''        if self._lifecycle.deactivate_on_early_hit:
            self._active.clear()
            return True
        return False



# ── P60 新增 → P55 更新：保底类型注册表（对齐 STRATEGY_REGISTRY） ──'''

new_classes = '''        if self._lifecycle.deactivate_on_early_hit:
            self._active.clear()
            return True
        return False


# ── P56：_redistribute_scope() —— rotating/targeted 家族共用的概率重分配工具 ──

def _redistribute_scope(ctx, featured_ratio, total, featured_slots, scope):
    """在 featured/非featured 之间按基础权重比例重分配 scope 总概率。"""
    result = ctx.current.copy()
    featured_total = total * featured_ratio
    non_featured_total = total - featured_total
    f_weights = [ctx.draw.base_probabilities.get(s, 0.0) for s in featured_slots]
    f_total_w = sum(f_weights)
    if f_total_w > 0:
        for s, w in zip(featured_slots, f_weights):
            result[s] = featured_total * w / f_total_w
    elif featured_slots:
        per_target = featured_total / len(featured_slots)
        for s in featured_slots:
            result[s] = per_target
    non_featured_slots = [s for s in ctx.draw.scope_slots.get(scope, ()) if s not in featured_slots]
    if non_featured_slots:
        nf_weights = [ctx.draw.base_probabilities.get(s, 0.0) for s in non_featured_slots]
        nf_total_w = sum(nf_weights)
        if nf_total_w > 0:
            for s, w in zip(non_featured_slots, nf_weights):
                result[s] = non_featured_total * w / nf_total_w
        else:
            per_target = non_featured_total / len(non_featured_slots)
            for s in non_featured_slots:
                result[s] = per_target
    return result


# ── P56：RotatingBehavior —— 事件驱动的纯净轮换保底 ──

class RotatingBehavior(PityBehavior):
    """事件驱动的纯净轮换保底。小保底沿用基础分布比例，大保底 featured 100%。"""
    def __init__(self, name, state, scope="ssr", guaranteed_init=False, **kwargs):
        self._name = name; self._scope = scope; self._btype = 'rotating'
        self.is_soft = False; self.is_hard = False; self.is_event_driven = True
        self._guaranteed = Flag(state, name, "guaranteed")
        if guaranteed_init: self._guaranteed.set()
    def before_draw(self, ctx, readonly=False):
        total = self._scope_total_prob(ctx)
        if total <= 0: return ctx.current.copy()
        featured_slots = self._featured_slots(ctx)
        if not featured_slots: return ctx.current.copy()
        if self._guaranteed.is_set(): featured_ratio = 1.0
        else:
            featured_total = sum(ctx.current.get(s, 0.0) for s in featured_slots)
            featured_ratio = featured_total / total if total > 0 else 0.0
        return _redistribute_scope(ctx, featured_ratio, total, featured_slots, self._scope)
    def after_draw(self, ctx):
        if not self._is_trigger_rarity(ctx.draw.reward_rarity, ctx): return
        if self._is_hit(ctx): self._guaranteed.clear()
        else: self._guaranteed.set()
    def _is_hit(self, ctx): return ctx.draw.is_featured
    def _is_trigger_rarity(self, rarity, ctx): return rarity == self._scope
    def _scope_total_prob(self, ctx):
        slots = ctx.draw.scope_slots.get(self._scope, ())
        return sum(ctx.current.get(s, 0.0) for s in slots)
    def _featured_slots(self, ctx): return ctx.draw.featured_slots.get(self._scope, ())
    def did_fire(self, ctx): return self._is_hit(ctx)


# ── P56：SoftPityMixin —— 消除 _soft 后缀类型重复的软保底 mixin ──

class SoftPityMixin:
    """混入软保底——委托 P55 SoftStepBehavior deltas 引擎。MRO 关键：mixin 必须在继承列表首位。"""
    def _init_soft_pity(self, name, state, scope, **kwargs):
        assert hasattr(self, '_scope'), 'SoftPityMixin._init_soft_pity: 父类 __init__ 必须先于本方法调用'
        from .config_toml import _expand_soft_to_deltas  # noqa: E402
        soft_deltas = kwargs.get('soft_deltas')
        if soft_deltas:
            btype = 'soft_step'; deltas = soft_deltas
            if isinstance(deltas, (list, tuple)) and len(deltas) == 0:
                btype = 'soft_interval'; deltas = ((0, 0.0),)
        elif kwargs.get('soft_increment') is not None:
            btype = 'soft_additive'
            deltas = _expand_soft_to_deltas(btype, kwargs.get('soft_start', 74), kwargs.get('soft_end', 90), kwargs['soft_increment'])
        else:
            btype = 'soft_interval'
            deltas = _expand_soft_to_deltas(btype, kwargs.get('soft_start', 74), kwargs.get('soft_end', 90), None)
        self._soft_engine = SoftStepBehavior(name + '_soft', state, scope, btype, deltas)
        self._counter = Counter(state, name, "counter")
    def before_draw(self, ctx, readonly=False):
        v = self._counter.value() if readonly else self._counter.incr()
        modified = self._soft_engine._compute_probabilities(ctx, v)
        forked = PityContext(draw=ctx.draw, current=modified, state=ctx.state)
        return super().before_draw(forked, readonly=readonly)
    def after_draw(self, ctx):
        if ctx.draw.reward_rarity == self._scope: self._counter.reset()
        super().after_draw(ctx)


# ── P56：RotatingSoftBehavior —— 轮换 + 软保底（mixin 版） ──

class RotatingSoftBehavior(SoftPityMixin, RotatingBehavior):
    def __init__(self, name, state, scope="ssr", **kwargs):
        RotatingBehavior.__init__(self, name, state, scope, **kwargs)
        self._init_soft_pity(name, state, scope, **kwargs)


# ── P56：RotatingCRBehavior —— 轮换保底 + 捕获明光 ──

class RotatingCRBehavior(RotatingBehavior):
    """轮换保底 + 捕获明光（Capturing Radiance）。"""
    def __init__(self, name, state, scope="ssr", cr_counter_threshold=None, cr_base_rate=None, cr_state_probs=None, **kwargs):
        super().__init__(name, state, scope, **kwargs)
        self._btype = 'rotating_cr'
        self._cr_max = cr_counter_threshold if cr_counter_threshold is not None else 3
        self._cr_base_rate = cr_base_rate if cr_base_rate is not None else 0.0
        if cr_state_probs is not None:
            self._cr_state_probs = list(cr_state_probs) if isinstance(cr_state_probs, (list, tuple)) else [0.0] * self._cr_max + [1.0]
        else: self._cr_state_probs = [0.0] * self._cr_max + [1.0]
        self._cr_counter = Counter(state, name, "cr_counter")
    def before_draw(self, ctx, readonly=False):
        if self._guaranteed.is_set(): return super().before_draw(ctx, readonly=readonly)
        if readonly: return super().before_draw(ctx, readonly=readonly)
        if self._cr_base_rate > 0 and random.random() < self._cr_base_rate: return self._force_featured(ctx)
        idx = min(self._cr_counter.value(), len(self._cr_state_probs) - 1)
        if idx >= 0:
            state_prob = self._cr_state_probs[idx]
            if state_prob >= 1.0: return self._force_featured(ctx)
            if state_prob > 0 and random.random() < state_prob: return self._force_featured(ctx)
        return super().before_draw(ctx, readonly=readonly)
    def _force_featured(self, ctx):
        total = self._scope_total_prob(ctx); featured_slots = self._featured_slots(ctx)
        return _redistribute_scope(ctx, 1.0, total, featured_slots, self._scope)
    def after_draw(self, ctx):
        was_guaranteed = self._guaranteed.is_set(); super().after_draw(ctx)
        if not self._is_trigger_rarity(ctx.draw.reward_rarity, ctx): return
        if was_guaranteed: return
        if ctx.draw.is_featured: self._cr_counter.reset()
        else: self._cr_counter.incr()
    def did_fire(self, ctx): return ctx.draw.is_featured


# ── P56：RotatingCRSoftBehavior —— 轮换 + CR + 软保底（mixin 版） ──

class RotatingCRSoftBehavior(SoftPityMixin, RotatingCRBehavior):
    def __init__(self, name, state, scope="ssr", cr_counter_threshold=None, cr_base_rate=None, cr_state_probs=None, **kwargs):
        RotatingCRBehavior.__init__(self, name, state, scope, cr_counter_threshold, cr_base_rate, cr_state_probs, **kwargs)
        self._init_soft_pity(name, state, scope, **kwargs)


# ── P56：TargetedBehavior —— 事件驱动的定向保底（定轨） ──

class TargetedBehavior(PityBehavior):
    """事件驱动的定向保底（定轨）。"""
    def __init__(self, name, state, scope="ssr", fate_threshold=None, switch_allowed=None, switch_resets_progress=None, guaranteed_init=False, fate_points_init=0, **kwargs):
        self._name = name; self._state = state; self._scope = scope; self._btype = 'targeted'
        self.is_soft = False; self.is_hard = False; self.is_event_driven = True
        self._fate_threshold = fate_threshold if fate_threshold is not None else 1
        self._switch_allowed = switch_allowed if switch_allowed is not None else True
        self._switch_resets_progress = switch_resets_progress if switch_resets_progress is not None else True
        self._guaranteed = Flag(state, name, "guaranteed")
        self._losses = Counter(state, name, "losses")
        self._lost_flag = Flag(state, name, "lost_rotating")
        self._fate_points = Counter(state, name, "fate_points")
        if guaranteed_init: self._guaranteed.set()
        if fate_points_init: self._fate_points._state.set(name, "fate_points", fate_points_init)
    def before_draw(self, ctx, readonly=False):
        total = self._scope_total_prob(ctx)
        if total <= 0: return ctx.current.copy()
        featured_slots = self._featured_slots(ctx)
        if not featured_slots: return ctx.current.copy()
        selected = ctx.state.get(self._name, "selected_card")
        if self._guaranteed.is_set() or (selected and self._fate_points.value() >= self._fate_threshold):
            featured_ratio = 1.0
            targeted_slots = self._resolve_selected_slots(selected, featured_slots, ctx)
            return _redistribute_scope(ctx, featured_ratio, total, targeted_slots, self._scope)
        else:
            featured_total = sum(ctx.current.get(s, 0.0) for s in featured_slots)
            featured_ratio = featured_total / total if total > 0 else 0.0
            return _redistribute_scope(ctx, featured_ratio, total, featured_slots, self._scope)
    def after_draw(self, ctx):
        if not self._is_trigger_rarity(ctx.draw.reward_rarity, ctx): return
        selected = ctx.state.get(self._name, "selected_card")
        if selected is None: return
        if self._is_hit(ctx):
            self._fate_points.reset(); self._guaranteed.clear(); self._lost_flag.clear(); self._losses.reset()
            return
        self._fate_points.incr(); self._guaranteed.set(); self._lost_flag.set(); self._losses.incr()
    def _is_hit(self, ctx):
        selected = ctx.state.get(self._name, "selected_card")
        if selected is None: return False
        return ctx.draw.reward_id == selected
    def _resolve_selected_slots(self, selected, featured_slots, ctx):
        if selected is None: return featured_slots
        card_to_slot = getattr(ctx.draw, 'card_to_slot', None) or {}
        target_slot = card_to_slot.get(selected)
        if target_slot and target_slot in featured_slots: return (target_slot,)
        for slot in featured_slots:
            rarity_key = slot.replace('_featured', '') if slot.endswith('_featured') else slot
            cards = ctx.draw.scope_cards.get(rarity_key, ())
            if selected in cards: return (slot,)
        return featured_slots
    def _is_trigger_rarity(self, rarity, ctx): return rarity == self._scope
    def _scope_total_prob(self, ctx):
        slots = ctx.draw.scope_slots.get(self._scope, ())
        return sum(ctx.current.get(s, 0.0) for s in slots)
    def _featured_slots(self, ctx): return ctx.draw.featured_slots.get(self._scope, ())
    def did_fire(self, ctx): return self._is_hit(ctx)


# ── P56：TargetedSoftBehavior —— 定轨 + 软保底（mixin 版） ──

class TargetedSoftBehavior(SoftPityMixin, TargetedBehavior):
    def __init__(self, name, state, scope="ssr", fate_threshold=None, switch_allowed=None, switch_resets_progress=None, **kwargs):
        TargetedBehavior.__init__(self, name, state, scope, fate_threshold, switch_allowed, switch_resets_progress, **kwargs)
        self._init_soft_pity(name, state, scope, **kwargs)


# ── P60 新增 → P55 更新：保底类型注册表（对齐 STRATEGY_REGISTRY） ──'''

if insertion_marker in c and 'class RotatingBehavior' not in c:
    c = c.replace(insertion_marker, new_classes)
    changes += 1
    print('5. New classes inserted')
elif 'class RotatingBehavior' in c:
    print('5. SKIP: classes already present')

# 6. Update BEHAVIOR_REGISTRY P56 entries (class=None -> actual classes)
old_reg = '''    # ══ P56：事件驱动型（6 种——stub） ══
    "rotating": {
        "class": None,
        "display_name": "轮换保底",
        "default_scope": "ssr",
        "params": {},
    },
    "rotating_soft": {
        "class": None,
        "display_name": "轮换保底（带软保底）",
        "default_scope": "ssr",
        "params": {
            "soft_start":     {"type": "int",   "display_name": "软保底起始",   "default": 74, "min": 1},
            "soft_end":       {"type": "int",   "display_name": "软保底结束",   "default": 90, "min": 1},
            "soft_increment": {"type": "float", "display_name": "每抽增量(%)",  "default": 6.0, "min": 0.1},
        },
    },
    "targeted": {
        "class": None,
        "display_name": "定向保底（定轨）",
        "default_scope": "ssr",
        "params": {
            "fate_threshold":         {"type": "int",   "display_name": "命定值阈值",     "default": 1,    "min": 0},
            "switch_allowed":         {"type": "bool",  "display_name": "允许中途切换",   "default": True},
            "switch_resets_progress": {"type": "bool",  "display_name": "切换后清零进度", "default": True},
        },
    },
    "rotating_cr": {
        "class": None,
        "display_name": "轮换保底·捕获明光",
        "default_scope": "ssr",
        "params": {
            "cr_counter_threshold": {"type": "int",   "display_name": "CR 计数器阈值",   "default": 3,    "min": 1},
            "cr_base_rate":         {"type": "float", "display_name": "基础触发概率",     "default": 0.0,  "min": 0.0, "max": 1.0},
            "cr_state_probs":       {"type": "str",   "display_name": "CR 状态概率数组",  "default": "[0.0, 0.0, 0.0, 1.0]"},
        },
    },
    "rotating_cr_soft": {
        "class": None,
        "display_name": "轮换保底·捕获明光（带软保底）",
        "default_scope": "ssr",
        "params": {
            "cr_counter_threshold": {"type": "int",   "display_name": "CR 计数器阈值",   "default": 3,    "min": 1},
            "cr_base_rate":         {"type": "float", "display_name": "基础触发概率",     "default": 0.0,  "min": 0.0, "max": 1.0},
            "cr_state_probs":       {"type": "str",   "display_name": "CR 状态概率数组",  "default": "[0.0, 0.0, 0.0, 1.0]"},
            "soft_start":           {"type": "int",   "display_name": "软保底起始",       "default": 74,   "min": 1},
            "soft_end":             {"type": "int",   "display_name": "软保底结束",       "default": 90,   "min": 1},
            "soft_increment":       {"type": "float", "display_name": "每抽增量(%)",      "default": 6.0,  "min": 0.1},
        },
    },
    "targeted_soft": {
        "class": None,
        "display_name": "定向保底·定轨（带软保底）",
        "default_scope": "ssr",
        "params": {
            "fate_threshold":         {"type": "int",   "display_name": "命定值阈值",     "default": 1,    "min": 0},
            "switch_allowed":         {"type": "bool",  "display_name": "允许中途切换",   "default": True},
            "switch_resets_progress": {"type": "bool",  "display_name": "切换后清零进度", "default": True},
            "soft_start":             {"type": "int",   "display_name": "软保底起始",     "default": 74,   "min": 1},
            "soft_end":               {"type": "int",   "display_name": "软保底结束",     "default": 90,   "min": 1},
            "soft_increment":         {"type": "float", "display_name": "每抽增量(%)",    "default": 6.0,  "min": 0.1},
        },
    },
}'''

new_reg = '''    # ══ P56：事件驱动型（6 种——已实现） ══
    "rotating": {
        "class": RotatingBehavior,
        "display_name": "轮换保底",
        "default_scope": "ssr",
        "params": {},
    },
    "rotating_soft": {
        "class": RotatingSoftBehavior,
        "display_name": "轮换保底（带软保底）",
        "default_scope": "ssr",
        "params": {
            "soft_start":     {"type": "int",   "display_name": "软保底起始",   "default": 74, "min": 1},
            "soft_end":       {"type": "int",   "display_name": "软保底结束",   "default": 90, "min": 1},
            "soft_increment": {"type": "float", "display_name": "每抽增量(%)",  "default": 6.0, "min": 0.1},
        },
    },
    "targeted": {
        "class": TargetedBehavior,
        "display_name": "定向保底（定轨）",
        "default_scope": "ssr",
        "params": {
            "fate_threshold":         {"type": "int",   "display_name": "命定值阈值",     "default": 1,    "min": 0},
            "switch_allowed":         {"type": "bool",  "display_name": "允许中途切换",   "default": True},
            "switch_resets_progress": {"type": "bool",  "display_name": "切换后清零进度", "default": True},
        },
    },
    "rotating_cr": {
        "class": RotatingCRBehavior,
        "display_name": "轮换保底·捕获明光",
        "default_scope": "ssr",
        "params": {
            "cr_counter_threshold": {"type": "int",   "display_name": "CR 计数器阈值",   "default": 3,    "min": 1},
            "cr_base_rate":         {"type": "float", "display_name": "基础触发概率",     "default": 0.0,  "min": 0.0, "max": 1.0},
            "cr_state_probs":       {"type": "str",   "display_name": "CR 状态概率数组",  "default": "[0.0, 0.0, 0.0, 1.0]"},
        },
    },
    "rotating_cr_soft": {
        "class": RotatingCRSoftBehavior,
        "display_name": "轮换保底·捕获明光（带软保底）",
        "default_scope": "ssr",
        "params": {
            "cr_counter_threshold": {"type": "int",   "display_name": "CR 计数器阈值",   "default": 3,    "min": 1},
            "cr_base_rate":         {"type": "float", "display_name": "基础触发概率",     "default": 0.0,  "min": 0.0, "max": 1.0},
            "cr_state_probs":       {"type": "str",   "display_name": "CR 状态概率数组",  "default": "[0.0, 0.0, 0.0, 1.0]"},
            "soft_start":           {"type": "int",   "display_name": "软保底起始",       "default": 74,   "min": 1},
            "soft_end":             {"type": "int",   "display_name": "软保底结束",       "default": 90,   "min": 1},
            "soft_increment":       {"type": "float", "display_name": "每抽增量(%)",      "default": 6.0,  "min": 0.1},
        },
    },
    "targeted_soft": {
        "class": TargetedSoftBehavior,
        "display_name": "定向保底·定轨（带软保底）",
        "default_scope": "ssr",
        "params": {
            "fate_threshold":         {"type": "int",   "display_name": "命定值阈值",     "default": 1,    "min": 0},
            "switch_allowed":         {"type": "bool",  "display_name": "允许中途切换",   "default": True},
            "switch_resets_progress": {"type": "bool",  "display_name": "切换后清零进度", "default": True},
            "soft_start":             {"type": "int",   "display_name": "软保底起始",     "default": 74,   "min": 1},
            "soft_end":               {"type": "int",   "display_name": "软保底结束",     "default": 90,   "min": 1},
            "soft_increment":         {"type": "float", "display_name": "每抽增量(%)",    "default": 6.0,  "min": 0.1},
        },
    },
}'''

if old_reg in c:
    c = c.replace(old_reg, new_reg)
    changes += 1
    print('6. BEHAVIOR_REGISTRY updated')
elif 'RotatingBehavior' in c.split('BEHAVIOR_REGISTRY')[1][:2000] if 'BEHAVIOR_REGISTRY' in c else False:
    print('6. SKIP: BEHAVIOR_REGISTRY already updated')
else:
    print('WARN: BEHAVIOR_REGISTRY old pattern not found')

# 7. create_behavior() - add _SOFT_SUFFIX_TYPES and P56 params
old_cb = '''    # btype 传递给 behavior——基类据此推导 is_soft/is_hard/is_event_driven
    params = {"btype": pdef.btype}

    # ── 检测新旧格式 ──
    if hasattr(pdef, 'params') and isinstance(pdef.params, dict):'''

if old_cb in c:
    new_cb = '''    # btype 传递给 behavior——基类据此推导 is_soft/is_hard/is_event_driven
    params: Dict[str, Any] = {"btype": pdef.btype}

    _SOFT_SUFFIX_TYPES = frozenset({'rotating_soft', 'rotating_cr_soft', 'targeted_soft'})
    _P56_TYPES = frozenset({'rotating', 'rotating_soft', 'rotating_cr', 'rotating_cr_soft', 'targeted', 'targeted_soft'})

    # ── 检测新旧格式 ──
    if hasattr(pdef, 'params') and isinstance(pdef.params, dict):'''
    c = c.replace(old_cb, new_cb)
    changes += 1
    print('7. create_behavior P56 type sets added')

# 7b. Add _SOFT_SUFFIX_TYPES guard before _expand_soft_to_deltas
old_soft = '''        if getattr(pdef, 'deltas', None) is not None:
            params['deltas'] = pdef.deltas
        elif hasattr(pdef, 'soft_start') and pdef.soft_start is not None:'''

if old_soft in c:
    new_soft = '''        if getattr(pdef, 'deltas', None) is not None:
            params['deltas'] = pdef.deltas
        elif pdef.btype in _SOFT_SUFFIX_TYPES:
            pass  # deltas 由 SoftPityMixin._init_soft_pity() 独立展开
        elif hasattr(pdef, 'soft_start') and pdef.soft_start is not None:'''
    c = c.replace(old_soft, new_soft)
    changes += 1
    print('7b. _SOFT_SUFFIX_TYPES guard added')

# 7c. Add P56 params before lifecycle
old_lc = '''        if getattr(pdef, 'reset', None):
            params['reset'] = pdef.reset
        # 生命周期参数——LifecycleConfig 跨 type 共享'''

if old_lc in c:
    new_lc = '''        if getattr(pdef, 'reset', None):
            params['reset'] = pdef.reset
        # ── P56：事件驱动型参数透传（仅 P56 type） ──
        if pdef.btype in _P56_TYPES:
            for attr in ('cr_counter_threshold', 'cr_base_rate', 'cr_state_probs',
                         'fate_threshold', 'switch_allowed', 'switch_resets_progress',
                         'soft_deltas', 'soft_start', 'soft_end', 'soft_increment'):
                v = getattr(pdef, attr, None)
                if v is not None: params[attr] = v
            if getattr(pdef, 'guaranteed_init', False): params['guaranteed_init'] = True
            if getattr(pdef, 'fate_points_init', 0): params['fate_points_init'] = pdef.fate_points_init
        # 生命周期参数——LifecycleConfig 跨 type 共享'''
    c = c.replace(old_lc, new_lc)
    changes += 1
    print('7c. P56 params passthrough added')

# 8. _build_pity_state_init - add selected_card
old_build = '''        # fate_points_init（targeted 家族初始命定值）
        fp = getattr(pdef, 'fate_points_init', 0)
        if fp:
            state.set(pdef.name, "fate_points", fp)

    return state'''

if old_build in c:
    new_build = '''        # fate_points_init（targeted 家族初始命定值）
        fp = getattr(pdef, 'fate_points_init', 0)
        if fp:
            state.set(pdef.name, "fate_points", fp)

        # P56：targeted 家族显式注入 selected_card=None
        _TARGETED_TYPES = frozenset({'targeted', 'targeted_soft'})
        if getattr(pdef, 'btype', '') in _TARGETED_TYPES:
            state.set(pdef.name, "selected_card", None)

    return state'''
    c = c.replace(old_build, new_build)
    changes += 1
    print('8. _build_pity_state_init updated')

# 9. PityEngine.__init__ - remove skip guard + add activation graph
old_skip = '''                if pdef.btype in ('rotating', 'targeted', 'rotating_cr',
                                  'rotating_cr_soft', 'rotating_soft', 'targeted_soft'):
                    continue  # P56 stub——跳过事件驱动型
                try:'''

if old_skip in c:
    new_skip = '''                # P56：移除 skip guard——所有 10 种 type 均由 create_behavior() 处理
                try:'''
    c = c.replace(old_skip, new_skip)
    changes += 1
    print('9. P56 skip guard removed')

# 9b. Add _pity_defs_list and _activation_graph
old_init_end = '''            self._behavior_list: List[PityBehavior] = ordered'''

if old_init_end in c:
    new_init_end = '''            self._pity_defs_list = pity_defs  # P56
            self._behavior_list: List[PityBehavior] = ordered

        # ── P56：构建 depends_on 激活传播图 ──
        self._activation_graph: Dict[str, List[str]] = self._build_activation_graph(
            list(self.behaviors.values()))'''
    c = c.replace(old_init_end, new_init_end)
    changes += 1
    print('9b. _activation_graph construction added')

# 10. PityEngine._behaviors_for_pool - delegate + new methods
old_b4p = '''    def _behaviors_for_pool(self, pool_id: str):
        """返回当前池关联的 behavior 实例列表——防止跨池计数器污染。"""
        spec = self.pool_specs.get(pool_id)
        if spec is None:
            return []
        result = []
        for pname in spec.pity_names:
            bh = self.behaviors.get(pname)
            if bh is not None:
                result.append((pname, bh))
        return result'''

if old_b4p in c:
    new_b4p = '''    def _behaviors_for_pool(self, pool_id: str):
        return self.get_behaviors_for_pool(pool_id)

    def get_behaviors_for_pool(self, pool_id: str):
        """公开方法——返回当前池关联的 behavior 实例列表。"""
        spec = self.pool_specs.get(pool_id)
        if spec is None: return []
        result = []
        for pname in spec.pity_names:
            bh = self.behaviors.get(pname)
            if bh is not None: result.append((pname, bh))
        return result

    def get_pity_def(self, name: str):
        """返回指定 behavior 的原始 PityDef 配置（只读视图）。"""
        return self.pity_defs.get(name)

    def _build_activation_graph(self, behaviors):
        """解析 depends_on 关系 -> {source_name: [dependent_name, ...]}。"""
        import warnings
        all_names = {bh._name for bh in behaviors if hasattr(bh, '_name')}
        _bh_by_name = {bh._name: bh for bh in behaviors if hasattr(bh, '_name')}
        graph: Dict[str, List[str]] = {}
        for bh in behaviors:
            name = getattr(bh, '_name', None)
            if name is None: continue
            lc = getattr(bh, '_lifecycle', None)
            if lc and lc.depends_on:
                dep = lc.depends_on
                if dep not in all_names:
                    from .config_store import ConfigError
                    raise ConfigError(f"「{name}」的 depends_on 引用了不存在的 behavior 「{dep}」")
                graph.setdefault(dep, []).append(name)
                source_bh = _bh_by_name.get(dep)
                if source_bh is not None:
                    src_pools = set(getattr(source_bh, '_pools', ()))
                    dst_pools = set(getattr(bh, '_pools', ()))
                    if '*' not in src_pools and '*' not in dst_pools:
                        if not (src_pools & dst_pools):
                            warnings.warn(f"「{name}」的 depends_on 指向「{dep}」，但双方 pools 无交集")
        return graph'''
    c = c.replace(old_b4p, new_b4p)
    changes += 1
    print('10. PityEngine new methods added')

# 11. after_draw - add did_fire propagation
old_ad = '''        # 按池过滤调度
        for pname, bh in self._behaviors_for_pool(pool_id):
            bh.after_draw(ctx)'''

if old_ad in c:
    new_ad = '''        # 按池过滤调度 + P56 声明式依赖传播
        for pname, bh in self._behaviors_for_pool(pool_id):
            bh.after_draw(ctx)
            if bh.did_fire(ctx):
                for dep_name in self._activation_graph.get(bh._name, []):
                    state.set(dep_name, "_active", True)'''
    c = c.replace(old_ad, new_ad)
    changes += 1
    print('11. after_draw did_fire propagation added')

# 12. DrawInfo constructions - add featured_cards and card_to_slot
# Fix get_probabilities
old_gp_di = '''            scope_cards=spec.scope_cards,
            scope_slots=spec.scope_slots,
            featured_slots=spec.featured_slots,
            base_probabilities=base_probabilities,
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current=base_probabilities.copy(), state=state)

        # 只读查询'''

if old_gp_di in c:
    new_gp_di = '''            scope_cards=spec.scope_cards,
            featured_cards=spec.featured_cards,
            scope_slots=spec.scope_slots,
            featured_slots=spec.featured_slots,
            card_to_slot=spec.card_to_slot,
            base_probabilities=base_probabilities,
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current=base_probabilities.copy(), state=state)

        # 只读查询'''
    c = c.replace(old_gp_di, new_gp_di)
    changes += 1
    print('12a. get_probabilities DrawInfo updated')

# Fix before_draw
old_bd_di = '''            scope_cards=spec.scope_cards,
            scope_slots=spec.scope_slots,
            featured_slots=spec.featured_slots,
            base_probabilities=base_probabilities,
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current=base_probabilities.copy(), state=state)

        # 按池过滤调度
        for pname, bh in self._behaviors_for_pool'''

if old_bd_di in c:
    new_bd_di = '''            scope_cards=spec.scope_cards,
            featured_cards=spec.featured_cards,
            scope_slots=spec.scope_slots,
            featured_slots=spec.featured_slots,
            card_to_slot=spec.card_to_slot,
            base_probabilities=base_probabilities,
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current=base_probabilities.copy(), state=state)

        # 按池过滤调度
        for pname, bh in self._behaviors_for_pool'''
    c = c.replace(old_bd_di, new_bd_di)
    changes += 1
    print('12b. before_draw DrawInfo updated')

# Fix after_draw
old_ad_di = '''            scope_cards=spec.scope_cards,
            scope_slots=spec.scope_slots,
            featured_slots=spec.featured_slots,
            base_probabilities={},
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current={}, state=state)'''

if old_ad_di in c:
    new_ad_di = '''            scope_cards=spec.scope_cards,
            featured_cards=spec.featured_cards,
            scope_slots=spec.scope_slots,
            featured_slots=spec.featured_slots,
            card_to_slot=spec.card_to_slot,
            base_probabilities={},
            rarity_rank=self._rarity_rank,
        )
        ctx = PityContext(draw=draw_info, current={}, state=state)'''
    c = c.replace(old_ad_di, new_ad_di)
    changes += 1
    print('12c. after_draw DrawInfo updated')

# Write back
open(f, 'w', encoding='utf-8').write(c)
print(f'\n=== pity.py updated: {changes} changes applied ===')
