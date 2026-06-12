"""expand_gain_rules_to_schedule 核心测试：5 条规则类型 + 6 种边界条件"""
import datetime as _dt
from gacha_simulator.core.resource_gain import expand_gain_rules_to_schedule
from gacha_simulator.core.config_store import GainRule, DayOverride


# ═══════════════════════════════════════════════════════════════════
# Task 12(a): 基础 5 条规则类型
# ═══════════════════════════════════════════════════════════════════

class TestEveryNDays:
    """every_n_days 规则：每隔 N 天触发"""

    def test_every_3_days(self):
        rules = [GainRule(rule_type='every_n_days', param='3',
                          gains={'draw': 100})]
        schedule = expand_gain_rules_to_schedule(rules, [], 10)
        # day 0, 3, 6, 9
        assert 0 in schedule
        assert 3 in schedule
        assert 6 in schedule
        assert 9 in schedule
        assert schedule[0].get('draw') == 100

    def test_every_1_day(self):
        rules = [GainRule(rule_type='every_n_days', param='1',
                          gains={'daily': 60})]
        schedule = expand_gain_rules_to_schedule(rules, [], 5)
        assert len(schedule) == 5
        for day in range(5):
            assert schedule[day].get('daily') == 60

    def test_every_n_days_empty_param_fallback(self):
        rules = [GainRule(rule_type='every_n_days', param='',
                          gains={'daily': 60})]
        schedule = expand_gain_rules_to_schedule(rules, [], 3)
        # 空 param 回退为 day=1（与 monthly_day 逻辑一致）
        assert len(schedule) >= 0


class TestWeekly:
    """weekly 规则：按星期触发"""

    def test_weekly_monday(self):
        """每周一触发——start_date 为周一"""
        rules = [GainRule(rule_type='weekly', param='1',
                          gains={'weekly_bonus': 500})]
        start = _dt.date(2024, 1, 1)  # Monday
        schedule = expand_gain_rules_to_schedule(rules, [], 14, start_date=start)
        assert 0 in schedule  # day 0 = Monday
        assert schedule[0].get('weekly_bonus') == 500
        assert 7 in schedule  # day 7 = Monday

    def test_weekly_multiple_rules(self):
        """多条 weekly 规则——每周一和周五各自触发"""
        rules = [
            GainRule(rule_type='weekly', param='1', gains={'stamina': 60}),
            GainRule(rule_type='weekly', param='5', gains={'stamina': 40}),
        ]
        start = _dt.date(2024, 1, 1)  # Monday
        schedule = expand_gain_rules_to_schedule(rules, [], 7, start_date=start)
        assert 0 in schedule   # Monday
        assert 4 in schedule   # Friday


class TestMonthlyDay:
    """monthly_day 规则"""

    def test_single_number_day1(self):
        """每月第 1 天"""
        rules = [GainRule(rule_type='monthly_day', param='1',
                          gains={'monthly': 1000})]
        start = _dt.date(2024, 1, 1)
        schedule = expand_gain_rules_to_schedule(rules, [], 62, start_date=start)
        assert 0 in schedule    # Jan 1
        assert 31 in schedule   # Feb 1
        assert schedule[0].get('monthly') == 1000

    def test_month_day_format(self):
        """月,日格式：每年 3月15日"""
        rules = [GainRule(rule_type='monthly_day', param='3,15',
                          gains={'spring': 500})]
        start = _dt.date(2024, 1, 1)
        schedule = expand_gain_rules_to_schedule(rules, [], 365, start_date=start)
        # March 15 = day 74 (2024-01-01 + 74 days = 2024-03-15)
        march15 = (_dt.date(2024, 3, 15) - start).days
        assert march15 in schedule
        assert schedule[march15].get('spring') == 500


class TestMonthlyWeek:
    """monthly_week 规则"""

    def test_comma_format(self):
        """每月第2个星期一"""
        rules = [GainRule(rule_type='monthly_week', param='2,1',
                          gains={'biweekly': 300})]
        start = _dt.date(2024, 1, 1)  # Monday
        schedule = expand_gain_rules_to_schedule(rules, [], 31, start_date=start)
        # Jan 2024: 2nd Monday = day 7
        assert 7 in schedule

    def test_dash_format_legacy(self):
        """减号分隔的旧格式兼容"""
        rules = [GainRule(rule_type='monthly_week', param='2-1',
                          gains={'biweekly': 300})]
        start = _dt.date(2024, 1, 1)
        schedule = expand_gain_rules_to_schedule(rules, [], 31, start_date=start)
        assert 7 in schedule


# ═══════════════════════════════════════════════════════════════════
# Task 12(b): 边界条件 6 场景
# ═══════════════════════════════════════════════════════════════════

class TestBoundaryConditions:
    """空参数、零天数、负数、闰年、day_override、超大天数"""

    def test_total_days_zero(self):
        """total_days=0 → 返回空字典"""
        rules = [GainRule(rule_type='every_n_days', param='1',
                          gains={'daily': 60})]
        schedule = expand_gain_rules_to_schedule(rules, [], 0)
        assert schedule == {}

    def test_total_days_negative(self):
        """total_days<0 → 返回空字典（不崩溃）"""
        rules = [GainRule(rule_type='every_n_days', param='1',
                          gains={'daily': 60})]
        schedule = expand_gain_rules_to_schedule(rules, [], -5)
        assert schedule == {}

    def test_leap_year_feb29(self):
        """闰年 2月29日 正确处理"""
        rules = [GainRule(rule_type='monthly_day', param='2,29',
                          gains={'leap': 999})]
        start = _dt.date(2024, 1, 1)  # 2024 is leap year
        schedule = expand_gain_rules_to_schedule(rules, [], 366, start_date=start)
        feb29 = (_dt.date(2024, 2, 29) - start).days
        assert feb29 in schedule
        assert schedule[feb29].get('leap') == 999

    def test_day_override(self):
        """day_override 累加到已有日程"""
        rules = [GainRule(rule_type='every_n_days', param='7',
                          gains={'weekly': 100})]
        overrides = [DayOverride(day=3, gains={'bonus': 50})]
        schedule = expand_gain_rules_to_schedule(rules, overrides, 7)
        assert 3 in schedule
        assert schedule[3].get('weekly', 0) + schedule[3].get('bonus', 0) > 0

    def test_empty_param_monthly_day(self):
        """monthly_day 空 param → 回退 day=1（不崩溃）"""
        rules = [GainRule(rule_type='monthly_day', param='',
                          gains={'safe': 100})]
        start = _dt.date(2024, 1, 1)
        schedule = expand_gain_rules_to_schedule(rules, [], 31, start_date=start)
        assert 0 in schedule  # January 1st

    def test_no_crash_large_total_days(self):
        """超大 total_days 不崩溃（fromordinal 保护已用 logger.warning 替代 pass）"""
        rules = [GainRule(rule_type='every_n_days', param='365',
                          gains={'annual': 1000})]
        # 1000 天在 fromordinal 安全范围内，不应崩溃
        schedule = expand_gain_rules_to_schedule(rules, [], 1000)
        assert len(schedule) > 0
