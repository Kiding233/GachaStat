from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Dict


class Action(ABC):
    type: str

    @abstractmethod
    def __repr__(self) -> str:
        pass


@dataclass
class DrawAction(Action):
    pool_id: str
    type: Literal['draw'] = 'draw'

    def __repr__(self) -> str:
        return f"DrawAction(pool_id='{self.pool_id}')"


@dataclass
class WaitAction(Action):
    duration: float
    type: Literal['wait'] = 'wait'

    def __repr__(self) -> str:
        return f"WaitAction(duration={self.duration})"


# ── P56：NonDrawAction —— 非抽卡动作（定轨切换/取消） ──

@dataclass
class NonDrawAction(Action):
    """非抽卡动作——由策略返回，执行保底状态管理操作。"""
    action_id: str
    params: dict
    type: Literal['non_draw'] = 'non_draw'

    def __repr__(self) -> str:
        return f"NonDrawAction('{self.action_id}', {self.params})"


NON_DRAW_ACTION_REGISTRY: Dict[str, dict] = {
    'switch_epitomized_target': {
        'description': '设置或切换定轨目标卡片',
        'required_params': ('pool_id', 'card_id'),
        'optional_params': (),
    },
    'cancel_epitomized_path': {
        'description': '取消定轨（回到不定轨状态）',
        'required_params': ('pool_id',),
        'optional_params': (),
    },
}


class InvalidActionError(ValueError):
    """运行时动作拒绝——如切换不允许的目标、未注册的 action_id 等。"""
    pass
