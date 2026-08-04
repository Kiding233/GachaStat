"""里程碑奖励引擎（P58）——独立于 PityEngine 的累抽奖励调度器。

职责：计数器管理、触发判定、奖励解析。不参与概率管道——在 pool.draw() 之后
独立调用。不持有 GachaState——只返回 bonus dict，状态变更由 gacha_service 负责。

（MilestoneDef / MilestoneConfig 定义于 config_store.py【M1】，本模块经
`from .config_store import MilestoneDef` 引用，不重复定义；core/__init__.py【M3】
统一 re-export 三者。）

register_milestone_engine 直接放在本模块（P61 落点 #2/#3 纠正——2026-08-05
用户裁决：不新建 service/milestone.py 薄模块，装配块 import 行顺手指向本模块）。
notifier 作参数传入，本模块无需 import Notifier，无循环依赖。本函数不做任何
模块级全局赋值——Windows spawn 下 worker 模块全局重置为 None 的坑
（P61 ISSUE-329 / P58 ISSUE-006）由此消除。
"""

import random
from typing import Dict, List, Optional

from .config_store import MilestoneConfig, MilestoneDef

__all__ = ['MilestoneEngine', 'MilestoneDef', 'MilestoneConfig', 'register_milestone_engine']


class MilestoneEngine:
    """里程碑奖励引擎——独立于 PityEngine。

    职责：计数器管理、触发判定、奖励解析。
    不参与概率管道——在 pool.draw() 之后独立调用。
    不持有 GachaState——只返回 bonus dict，状态变更由 gacha_service 负责。
    """

    def __init__(self, defs: List['MilestoneDef'], seed: int = 42):
        self._defs: Dict[str, MilestoneDef] = {d.name: d for d in defs}
        # 计数器自管——不依赖 PityState，也不持有 GachaState
        self._counters: Dict[str, int] = {}
        self._active: Dict[str, bool] = {d.name: True for d in defs}
        self._triggered: Dict[str, int] = {d.name: 0 for d in defs}
        # 独立 RNG——保证可复现性
        self._rng = random.Random(seed)

    def after_draw(self, banner_id: str, pool_id: str) -> List[dict]:
        """判定并返回触发的 bonus 列表。

        调用方（gacha_service）负责消费 bonus：
          - card 类型 → state.add_card(cid, path="milestone_gift",
              overflow_bands=card_overflow_map.get(cid),
              initial_counts=_initial_counts)
          - resource 类型 → 注入 state.resources（方案 C，2026-08-03；不并入当抽 combined_gained）
          - collector.on_bonus(...)

        banner_id 用于 MilestoneDef.banner 级过滤（P61 后裸 pool_id 非全局唯一）：
        P61 前（M4 inline 过渡形态）调用方传 ""（banner="" 匹配全部）；
        P61 后（已落地，2026-08-04 归档）经 after_draw 事件传入真实 banner_id（M9 装配）。
        实施最终态以 M9 订阅装配为准——M4 inline 传 "" 只是实施过程中的过渡路径。

        _NO_CARD_ID（空抽）行为：计数器无条件递增——只要 gacha_service 调用了
        after_draw() 即视为一次有效抽数。空抽（交换池/概率归零场景下 pool.draw()
        返回 _NO_CARD_ID）仍消耗资源/抽数，计数器应正常推进（符合绝大多数游戏的期望
        行为——「花了钱就算一抽」）。若特定游戏需排除空抽，调用方应在 after_draw()
        调用前加 `if reward.id != _NO_CARD_ID` 守卫——MilestoneEngine 本身不做此判断。
        """
        bonuses: List[dict] = []
        for name, md in self._defs.items():
            if not self._active[name]:
                continue
            if md.banner and banner_id != md.banner:
                continue

            c = self._counters.get(name, 0) + 1
            self._counters[name] = c

            if c < md.threshold:
                continue

            # ── 触发！解析 bonus ──
            bonus = self._resolve_bonus(md)
            bonuses.append({'name': name, 'bonus': bonus})

            # ── 生命周期管理 ──
            if md.repeat:
                self._counters[name] = 0        # every=N：重置继续
            else:
                self._active[name] = False       # at=N：永久停用

            self._triggered[name] += 1
            if md.max_triggers and self._triggered[name] >= md.max_triggers:
                self._active[name] = False

        return bonuses

    def _resolve_bonus(self, md: 'MilestoneDef') -> dict:
        """解析 bonus_reward——cards / resources / random_cards 可任意组合。

        返回 {'card_ids': [...], 'resources': {...}}——调用方同时消费两者。
        """
        br = md.bonus_reward
        result: dict = {'card_ids': list(br.get('cards', [])),
                        'resources': dict(br.get('resources', {}))}

        # 随机卡——从候选池中抽取（使用 self._rng 保证可复现）
        for rc in br.get('random_cards', []):
            candidates = rc['candidates']
            weights = rc.get('weights', [1.0] * len(candidates))
            count = rc.get('count', 1)
            chosen = self._rng.choices(candidates, weights=weights, k=count)
            result['card_ids'].extend(chosen)

        return result

    # ── 查询接口（供策略层消费） ──

    def get_counter(self, name: str) -> int:
        """当前累计抽数（已抽次数）。余量 = md.threshold - get_counter(name)。"""
        return self._counters.get(name, 0)

    def is_active(self, name: str) -> bool:
        """该里程碑是否仍在生效。"""
        return self._active.get(name, False)

    def get_trigger_count(self, name: str) -> int:
        """已触发次数。"""
        return self._triggered.get(name, 0)

    def get_def(self, name: str) -> Optional['MilestoneDef']:
        """返回里程碑定义——策略可据此查看 threshold / bonus_reward。"""
        return self._defs.get(name)

    def get_all_defs(self) -> Dict[str, 'MilestoneDef']:
        """返回全部里程碑定义。"""
        return dict(self._defs)


def register_milestone_engine(notifier, engine, card_overflow_map=None, initial_counts=None):
    """P61 Ph0 装配点回调——装配层在构造 GachaService 前调用（batch_simulator.py L261-269）。

    engine 来源（P58 M4b）：`_run_single` 内 `MilestoneEngine(env.milestone_defs, seed=seed)`
    延迟构造后传入。订阅落在与模拟循环 emit 相同的 Notifier 实例上。
    经闭包捕获 engine + card_overflow_map + initial_counts（P61 落点 #3 纠正——不用模块级全局）。

    card_overflow_map / initial_counts：与 GachaService 内 M4 inline 消费块同源的
    卡牌溢出分段表与初始持有量（env.card_overflow_map / 由 env.card_defs 推导），
    供 `_consume_bonus` 的 state.add_card 溢出管道使用——M9 订阅 handler 拿不到
    GachaService 内部 self，装配点透传这两份数据即可（与 env 构造时同源）。
    """
    if card_overflow_map is None:
        card_overflow_map = {}
    if initial_counts is None:
        initial_counts = {}

    def _on_after_draw(banner_id, pool_id, card_id, pity_triggered, draw_index, state, collector):
        for entry in engine.after_draw(banner_id, pool_id):
            # 消费 bonus：直接资源注入 state.resources + 卡走 state.add_card(path="milestone_gift")
            # 溢出资源注入 resources；归因数据随 collector.on_bonus 源头合并（方案 C）。
            _consume_bonus(entry, state, collector, pool_id, real_time=state.real_time,
                           draw_index=draw_index - 1,
                           card_overflow_map=card_overflow_map,
                           initial_counts=initial_counts)

    notifier.subscribe("after_draw", _on_after_draw, priority=0)


def _consume_bonus(entry, state, collector, pool_id, real_time, draw_index,
                   card_overflow_map=None, initial_counts=None):
    """消费单个 milestone bonus——资源/卡牌注入 + on_bonus 归因（方案 C，2026-08-03）。

    与 gacha_service 内联消费块（§3.5 M4）完全一致：直接资源注入 state.resources
    （当抽末可用，不进 combined_gained）；卡牌经 P63 state.add_card() 统一管道、
    溢出资源同样注入 resources；全部资源并入 milestone_res 随 on_bonus 源头归因
    （collector.on_draw 之后调用，按 draw_index 并入该抽产出与 total_gained）。
    """
    bonus = entry['bonus']
    milestone_res: dict = {}
    # 直接资源
    direct_res = bonus.get('resources', {})
    if direct_res:
        for k, v in direct_res.items():
            state.resources[k] = state.resources.get(k, 0) + v
            milestone_res[k] = milestone_res.get(k, 0) + v
    # 卡牌——经 P63 state.add_card() 统一管道，溢出资源同样注入 resources 并计入归因
    for cid in bonus.get('card_ids', []):
        overflow = state.add_card(
            cid,
            path="milestone_gift",
            overflow_bands=(card_overflow_map or {}).get(cid),
            initial_counts=initial_counts or {},
        )
        for k, v in overflow.items():
            state.resources[k] = state.resources.get(k, 0) + v
            milestone_res[k] = milestone_res.get(k, 0) + v
    collector.on_bonus(
        milestone_name=entry['name'],
        card_ids=bonus.get('card_ids', []),
        resources=milestone_res,
        pool_id=pool_id,
        real_time=real_time,
        draw_index=draw_index,
    )
