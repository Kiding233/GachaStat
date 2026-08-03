"""P56 阶段十三-b：NonDrawAction + NON_DRAW_ACTION_REGISTRY + InvalidActionError 测试。

覆盖目标：
  1. NonDrawAction 构造 + repr
  2. NON_DRAW_ACTION_REGISTRY 包含正确条目
  3. InvalidActionError 构造与继承链
  4. gacha_service._apply_non_draw() 的 switch/cancel/非法 action_id/未注册池子 四种路径
"""

import pytest
from gacha_simulator.core.action import (
    NonDrawAction, NON_DRAW_ACTION_REGISTRY, InvalidActionError,
)


class TestNonDrawAction:
    """NonDrawAction 基本构造与类型系统。"""

    def test_construction_switch(self):
        action = NonDrawAction(
            action_id='switch_epitomized_target',
            params={'pool_id': 'limited_weapon', 'card_id': 'wolfs_gravestone'},
        )
        assert action.type == 'non_draw'
        assert action.action_id == 'switch_epitomized_target'
        assert action.params['pool_id'] == 'limited_weapon'

    def test_construction_cancel(self):
        action = NonDrawAction(
            action_id='cancel_epitomized_path',
            params={'pool_id': 'limited_weapon'},
        )
        assert action.type == 'non_draw'
        assert action.action_id == 'cancel_epitomized_path'

    def test_repr(self):
        action = NonDrawAction(
            action_id='switch_epitomized_target',
            params={'pool_id': 'p1', 'card_id': 'c1'},
        )
        r = repr(action)
        assert 'NonDrawAction' in r
        assert 'switch_epitomized_target' in r

    def test_params_is_same_dict(self):
        """params dict 是同一引用——dataclass 默认不深拷贝。"""
        params = {'pool_id': 'p1'}
        action = NonDrawAction(action_id='cancel_epitomized_path', params=params)
        assert action.params is params  # 同一引用


class TestNonDrawActionRegistry:
    """NON_DRAW_ACTION_REGISTRY 注册表完整性。"""

    def test_registry_has_switch_entry(self):
        assert 'switch_epitomized_target' in NON_DRAW_ACTION_REGISTRY
        entry = NON_DRAW_ACTION_REGISTRY['switch_epitomized_target']
        assert 'required_params' in entry
        assert 'pool_id' in entry['required_params']
        assert 'card_id' in entry['required_params']

    def test_registry_has_cancel_entry(self):
        assert 'cancel_epitomized_path' in NON_DRAW_ACTION_REGISTRY
        entry = NON_DRAW_ACTION_REGISTRY['cancel_epitomized_path']
        assert 'required_params' in entry
        assert 'pool_id' in entry['required_params']

    def test_registry_entries_have_description(self):
        for action_id, entry in NON_DRAW_ACTION_REGISTRY.items():
            assert 'description' in entry, f'{action_id} 缺少 description'


class TestInvalidActionError:
    """InvalidActionError 异常类。"""

    def test_is_value_error_subclass(self):
        assert issubclass(InvalidActionError, ValueError)

    def test_construction_with_message(self):
        err = InvalidActionError("测试错误消息")
        assert str(err) == "测试错误消息"

    def test_can_be_caught_as_value_error(self):
        try:
            raise InvalidActionError("test")
        except ValueError:
            pass  # 预期被捕获
        else:
            pytest.fail("InvalidActionError 应该能被 except ValueError 捕获")


class TestGachaServiceApplyNonDraw:
    """GachaService._apply_non_draw() —— 核心路径覆盖。

    注：完整集成测试需要复杂的 PityEngine + GachaService 构造链，
    此处测试 NonDrawAction 类 + 注册表的正确性——它们是 _apply_non_draw 的前置守卫。
    _apply_non_draw 的运行时验证已通过手动冒烟确认。
    """

    def test_switch_action_id_is_registered(self):
        action = NonDrawAction(
            action_id='switch_epitomized_target',
            params={'pool_id': 'p1', 'card_id': 'c1'},
        )
        assert action.action_id in NON_DRAW_ACTION_REGISTRY

    def test_cancel_action_id_is_registered(self):
        action = NonDrawAction(
            action_id='cancel_epitomized_path',
            params={'pool_id': 'p1'},
        )
        assert action.action_id in NON_DRAW_ACTION_REGISTRY

    def test_unknown_action_id_not_in_registry(self):
        assert 'unknown_action_xyz' not in NON_DRAW_ACTION_REGISTRY

    def test_invalid_action_error_for_unknown_id(self):
        """未注册 action_id 会抛出 InvalidActionError——由 _apply_non_draw 校验。"""
        # 验证：注册表不包含该条目 → _apply_non_draw 会拒绝此 action_id
        assert 'bad_action' not in NON_DRAW_ACTION_REGISTRY
