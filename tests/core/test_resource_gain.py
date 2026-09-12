from gacha_simulator.core.resource_gain import (
    CompositeResourceGain, ScheduleResourceGain
)
from gacha_simulator.core.state import GachaState

DAY = 86400


def test_schedule_gain():
    """日程表按绝对天数发放，且不外推（P79 5.1：本模块只保留有界形态）。"""
    func = ScheduleResourceGain({1: {'draw_resource': 160}}, total_days=10)
    state = GachaState()

    state.real_time = 0.0
    assert func.compute(DAY, state) == {'draw_resource': 160}
    # 日程表未覆盖的天不发放（无外推）
    state.real_time = 2 * DAY
    assert func.compute(DAY, state) == {}


def test_composite_gain():
    """CompositeResourceGain 逐函数求和。

    P79 2a：原以 LinearResourceGain / PeriodicResourceGain 作 fixture，二者
    已随无界收入类一并删除，改用两个保留的 ScheduleResourceGain 构造。
    """
    a = ScheduleResourceGain({1: {'draw_resource': 100}}, total_days=10)
    b = ScheduleResourceGain({1: {'bonus': 100}}, total_days=10)

    composite = CompositeResourceGain([a, b])
    gains = composite.compute(DAY, GachaState())
    assert gains['draw_resource'] == 100
    assert gains['bonus'] == 100
