import logging
import datetime as _dt
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .state import GachaState
    from .config_store import GainRule, DayOverride

logger = logging.getLogger(__name__)


# ── 资源收入的有界性纪律（P79 5.1）──────────────────────────────
# 本模块只保留**有界**形态：ScheduleResourceGain（按模拟日历查表，绝对定位、
# 无外推）与包装它的 CompositeResourceGain。引擎硬边界的前提是「越过
# env.end_time 后无任何可观测量」，按时长外推的无界收入函数会破坏该前提，
# 故 P79 删除了 LinearResourceGain / PeriodicResourceGain / StepResourceGain。
# 三者本就不在现有配置可表达的范围内（GUI / TOML 的规则类型只有每天、每N天、
# 每周几、每月第几天、每月第几周几、指定日期），删除不损失现有功能。
#
# 将来若需亚日粒度收入（如「每 6 小时回体力」）：**正确路径是给日程表加时间
# 粒度**（把 ScheduleResourceGain.DAY 由常量改为可配 tick），因其账目为绝对
# 定位且有界；不要复活按时长计数的周期型实现——它在「单次等待短于一个周期」
# 时会丢弃余数。


class ResourceGainFunction(ABC):
    @abstractmethod
    def compute(self, elapsed_time: float, state: 'GachaState') -> Dict[str, float]:
        pass

    @abstractmethod
    def description(self) -> str:
        pass


class ScheduleResourceGain(ResourceGainFunction):
    DAY = 86400

    def __init__(self, schedule: Dict[int, Dict[str, float]], total_days: int = 365):
        self.schedule = schedule
        self.total_days = total_days

    def compute(self, elapsed_time: float, state: 'GachaState') -> Dict[str, float]:
        current_day = int(state.real_time // self.DAY)
        new_day = int((state.real_time + elapsed_time) // self.DAY)

        result: Dict[str, float] = {}
        for day in range(current_day + 1, new_day + 1):
            day_gains = self.schedule.get(day)
            if day_gains:
                for resource, amount in day_gains.items():
                    result[resource] = result.get(resource, 0) + amount

        return result

    def description(self) -> str:
        return f"按天获取: {len(self.schedule)} 天有资源收入"


class CompositeResourceGain(ResourceGainFunction):
    def __init__(self, functions: list):
        self.functions = functions

    def compute(self, elapsed_time: float, state: 'GachaState') -> Dict[str, float]:
        result = {}
        for func in self.functions:
            gains = func.compute(elapsed_time, state)
            for k, v in gains.items():
                result[k] = result.get(k, 0) + v
        return result

    def description(self) -> str:
        return ' + '.join(f.description() for f in self.functions)



# ── 默认模拟起始日期（当天）──
_DEFAULT_START_DATE = _dt.date.today()


def expand_gain_rules_to_schedule(
    gain_rules: List['GainRule'],
    day_overrides: List['DayOverride'],
    total_days: int,
    start_date: Optional[_dt.date] = None,
) -> Dict[int, Dict[str, float]]:
    """将资源获取规则展开为 {day: {resource_id: amount}} 字典。

    统一了 _build_resource_gain() 内联展开逻辑与 parse_gains_file() 正确日历算法，
    消除两条路径的代码重复与行为不一致。

    Args:
        gain_rules: 规则列表（GainRule 对象）。
        day_overrides: 指定日期覆盖列表（DayOverride 对象）。
        total_days: 模拟总天数。
        start_date: day=0 对应的真实日期，默认为当天。

    Returns:
        {day: {rid: amount}} 字典，key 为绝对天数偏移。

    Raises:
        不抛出异常——所有参数错误均通过 logging.warning 报告并回退默认值。
    """
    if start_date is None:
        start_date = _DEFAULT_START_DATE

    if total_days <= 0:
        return {}

    schedule: Dict[int, Dict[str, float]] = {}
    start_ordinal = start_date.toordinal()

    for rule in gain_rules:
        rule_type = getattr(rule, 'rule_type', 'every_n_days')
        param = getattr(rule, 'param', '1')
        gains = dict(getattr(rule, 'gains', {}) or {})

        if not gains:
            continue

        if rule_type == 'every_n_days':
            # ── 参数解析 + 空值防御 + 范围校验 ──
            n = 1
            try:
                n = int(param) if param else 1
            except (ValueError, TypeError):
                logger.warning(
                    "expand_gain_rules_to_schedule: every_n_days 参数 '%s' 无效，回退 n=1", param)
                n = 1
            if n <= 0:
                logger.warning(
                    "expand_gain_rules_to_schedule: every_n_days n=%d <= 0，回退 n=1", n)
                n = 1
            for day in range(0, total_days, n):
                if day not in schedule:
                    schedule[day] = {}
                for rid, amount in gains.items():
                    schedule[day][rid] = schedule[day].get(rid, 0) + float(amount)

        elif rule_type == 'weekly':
            # ── 参数解析 + 空值防御 + 范围校验 ──
            target_wday = 1
            try:
                target_wday = int(param) if param else 1
            except (ValueError, TypeError):
                logger.warning(
                    "expand_gain_rules_to_schedule: weekly 参数 '%s' 无效，回退 weekday=1", param)
                target_wday = 1
            if not (1 <= target_wday <= 7):
                logger.warning(
                    "expand_gain_rules_to_schedule: weekly weekday=%d 越界 [1,7]，回退 weekday=1",
                    target_wday)
                target_wday = 1
            for day in range(total_days):
                try:
                    d = _dt.date.fromordinal(start_ordinal + day)
                    if d.isoweekday() == target_wday:
                        if day not in schedule:
                            schedule[day] = {}
                        for rid, amount in gains.items():
                            schedule[day][rid] = schedule[day].get(rid, 0) + float(amount)
                except Exception:
                    logger.warning(
                        "fromordinal overflow at day=%d", day, exc_info=True,
                    )

        elif rule_type == 'monthly_day':
            # ── 空 param 防御 ──
            if not param or not param.strip():
                logger.warning(
                    "expand_gain_rules_to_schedule: monthly_day 参数为空，回退 day=1")
                # 单数字逻辑：每月第1天
                for day in range(total_days):
                    try:
                        d = _dt.date.fromordinal(start_ordinal + day)
                        if d.day == 1:
                            if day not in schedule:
                                schedule[day] = {}
                            for rid, amount in gains.items():
                                schedule[day][rid] = schedule[day].get(rid, 0) + float(amount)
                    except Exception:
                        logger.warning(
                            "fromordinal overflow at day=%d", day, exc_info=True,
                        )
                continue

            # ── 分支判断：先检查是否含逗号（月,日格式）──
            if ',' in param:
                # 月,日格式：每年指定月日触发
                parts = param.split(',')
                if len(parts) != 2:
                    logger.warning(
                        "expand_gain_rules_to_schedule: monthly_day 月,日格式 '%s' 无法解析，跳过该规则", param)
                    continue
                try:
                    target_month = int(parts[0].strip())
                    target_day = int(parts[1].strip())
                except (ValueError, TypeError):
                    logger.warning(
                        "expand_gain_rules_to_schedule: monthly_day 月,日参数 '%s' 转换失败，跳过该规则", param)
                    continue
                # 范围校验
                if not (1 <= target_month <= 12) or not (1 <= target_day <= 31):
                    logger.warning(
                        "expand_gain_rules_to_schedule: monthly_day 月=%d 日=%d 越界，跳过该规则",
                        target_month, target_day)
                    continue
                for day in range(total_days):
                    try:
                        d = _dt.date.fromordinal(start_ordinal + day)
                        if d.month == target_month and d.day == target_day:
                            if day not in schedule:
                                schedule[day] = {}
                            for rid, amount in gains.items():
                                schedule[day][rid] = schedule[day].get(rid, 0) + float(amount)
                    except Exception:
                        logger.warning(
                            "fromordinal overflow at day=%d", day, exc_info=True,
                        )
            else:
                # 单数字：每月第 N 天
                try:
                    target_day = int(param)
                except (ValueError, TypeError):
                    logger.warning(
                        "expand_gain_rules_to_schedule: monthly_day 单数字参数 '%s' 无效，回退 day=1", param)
                    target_day = 1
                if not (1 <= target_day <= 31):
                    logger.warning(
                        "expand_gain_rules_to_schedule: monthly_day day=%d 越界 [1,31]，回退 day=1",
                        target_day)
                    target_day = 1
                for day in range(total_days):
                    try:
                        d = _dt.date.fromordinal(start_ordinal + day)
                        if d.day == target_day:
                            if day not in schedule:
                                schedule[day] = {}
                            for rid, amount in gains.items():
                                schedule[day][rid] = schedule[day].get(rid, 0) + float(amount)
                    except Exception:
                        logger.warning(
                            "fromordinal overflow at day=%d", day, exc_info=True,
                        )

        elif rule_type == 'monthly_week':
            # ── 空 param 防御 ──
            if not param or not param.strip():
                logger.warning(
                    "expand_gain_rules_to_schedule: monthly_week 参数为空，跳过该规则")
                continue

            # ── 分隔符解析：先尝试逗号，失败则尝试减号（旧格式兼容）──
            parts = param.split(',')
            if len(parts) != 2:
                parts = param.split('-')
            if len(parts) != 2:
                logger.warning(
                    "expand_gain_rules_to_schedule: monthly_week 参数 '%s' 无法解析（需 week,day 格式），跳过该规则", param)
                continue
            try:
                target_week = int(parts[0].strip())
                target_wday = int(parts[1].strip())
            except (ValueError, TypeError):
                logger.warning(
                    "expand_gain_rules_to_schedule: monthly_week 参数 '%s' 转换失败，跳过该规则", param)
                continue
            # 范围校验
            if not (1 <= target_week <= 5) or not (1 <= target_wday <= 7):
                logger.warning(
                    "expand_gain_rules_to_schedule: monthly_week week=%d wday=%d 越界，跳过该规则",
                    target_week, target_wday)
                continue

            for day in range(total_days):
                try:
                    d = _dt.date.fromordinal(start_ordinal + day)
                    week_of_month = (d.day - 1) // 7 + 1
                    if week_of_month == target_week and d.isoweekday() == target_wday:
                        if day not in schedule:
                            schedule[day] = {}
                        for rid, amount in gains.items():
                            schedule[day][rid] = schedule[day].get(rid, 0) + float(amount)
                except Exception:
                    logger.warning(
                        "fromordinal overflow at day=%d", day, exc_info=True,
                    )

    # ── day: 覆盖（累加语义，与 _build_resource_gain 行为一致）──
    for override in day_overrides:
        day = getattr(override, 'day', 0)
        override_gains = getattr(override, 'gains', {}) or {}
        if 0 <= day < total_days:
            if day not in schedule:
                schedule[day] = {}
            for rid, amount in override_gains.items():
                amount = float(amount)
                if amount > 0:
                    schedule[day][rid] = schedule[day].get(rid, 0) + amount

    return schedule



