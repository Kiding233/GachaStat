from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .pool import Pool
    from .pity import PityState
    from .result_types import CompactResult


class SimulationCollector(ABC):
    @abstractmethod
    def on_draw(
        self,
        card_id: str,
        pool: 'Pool',
        spent: Dict[str, float],
        resources_gained: Dict[str, float],
        pity_triggered: bool,
        triggered_pity_name: Optional[str],
        pity_counter_max: int,
        real_time: float,
        pity_state: 'PityState',
        combined_gained: Dict[str, float],
        pool_key: Optional[str] = None,   # ← P61（Ph2）：全限定键 {banner_id}.{pool_id}；None 回退 pool.id
    ) -> None:
        pass

    @abstractmethod
    def on_wait(
        self,
        duration: float,
        resources_gained: Dict[str, float],
        real_time_before: float,
        real_time_after: float,
    ) -> None:
        pass

    @abstractmethod
    def on_banner_end(self, banner_id: str, resources: Dict[str, float],
                      pity_state_dict: Dict[str, Any]) -> None:   # ← P61（Ph2）：原 on_pool_end
        pass

    def on_bonus(self, milestone_name: str, card_ids: List[str],
                 resources: Dict[str, float], pool_id: str, real_time: float,
                 draw_index: int) -> None:
        """milestone 注入事件（P58）——记录归因元数据并源头合并卡/资源。

        基类给出 no-op 默认实现（【不可】标 @abstractmethod）：它是可选钩子，具体
        合并逻辑由 CompactCollector.on_bonus 实现。P81（2026-09-17）删除逐抽明细
        收集器后，本默认实现暂无子类继承。

        pool_id 用于 per-pool GDR 分析归因。draw_index 为 0-based 本抽索引（归因钥匙）。
        方案 C（2026-08-03）：milestone 资源注入 state.resources（当抽末可用）、【不并入】
        当抽 combined_gained；on_bonus 在 collector.on_draw【之后】调用，把 resources 源头
        并入 draw_resources_gained[draw_index] 与 total_gained——对象与 to_dict() 产物一致。
        """
        pass

    @abstractmethod
    def get_result(self) -> Any:
        pass


class CompactCollector(SimulationCollector):
    def __init__(self):
        from .result_types import CompactResult
        self._result = CompactResult()

    def on_draw(self, card_id, pool, spent, resources_gained, pity_triggered,
                triggered_pity_name, pity_counter_max, real_time, pity_state,
                combined_gained, pool_key=None):
        r = self._result
        key = pool_key or pool.id
        r.draw_card_ids.append(card_id)
        r.draw_pool_ids.append(key)
        r.draw_times.append(real_time)
        r.draw_pity.append(pity_triggered)
        r.draw_pity_names.append(triggered_pity_name)
        r.draw_pity_counter_max.append(pity_counter_max)
        r.draw_resources_consumed.append(dict(spent))
        r.draw_resources_gained.append(combined_gained)

        cc = r.card_counts
        cc[card_id] = cc.get(card_id, 0) + 1
        pc = r.pool_draw_counts
        pc[key] = pc.get(key, 0) + 1

        pcc = r.pool_card_counts.get(key, {})
        pcc[card_id] = pcc.get(card_id, 0) + 1
        r.pool_card_counts[key] = pcc

        if pity_triggered:
            ppc = r.pool_pity_counts
            ppc[key] = ppc.get(key, 0) + 1

    def on_wait(self, duration, resources_gained, real_time_before, real_time_after):
        self._result.wait_durations.append(duration)

    def on_banner_end(self, banner_id, resources, pity_state_dict):
        self._result.banner_end_resources[banner_id] = dict(resources)
        self._result.banner_end_pity_states[banner_id] = pity_state_dict

    def on_bonus(self, milestone_name, card_ids, resources, pool_id, real_time,
                 draw_index):
        """CompactCollector.on_bonus——记录归因元数据 + 源头合并卡/资源（P58 方案 A + C）。

        方案 A（源头合并卡）：milestone 卡直接并入 card_counts / pool_card_counts——
        to_dict() 产物已含合并后全量统计，SharedResultCollector/extract_aggregate
        零改动即含 milestone 产出。
        方案 C（源头合并资源）：on_bonus 在 collector.on_draw【之后】调用（此时
        draw_resources_gained 已 append 本抽），按 draw_index 直接把资源并入该抽
        产出与 total_gained——对象与 to_dict() 产物一致，流式/主路径均覆盖。
        """
        r = self._result
        r.bonus_events.append({
            'milestone_name': milestone_name,
            'card_ids': list(card_ids),
            'resources': dict(resources),
            'pool_id': pool_id,
            'real_time': real_time,
            'draw_index': draw_index,
        })
        # 源头合并卡（方案 A）
        for cid in card_ids:
            r.card_counts[cid] = r.card_counts.get(cid, 0) + 1
            if pool_id:
                pcc = r.pool_card_counts.get(pool_id, {})
                pcc[cid] = pcc.get(cid, 0) + 1
                r.pool_card_counts[pool_id] = pcc
        # 源头合并资源（方案 C）——前置：on_bonus 在 on_draw 之后，draw_index 处元素存在
        if resources and 0 <= draw_index < len(r.draw_resources_gained):
            dpg = r.draw_resources_gained[draw_index]
            for k, v in resources.items():
                dpg[k] = dpg.get(k, 0) + v
                r.total_gained[k] = r.total_gained.get(k, 0) + v

    def get_result(self) -> 'CompactResult':
        return self._result
