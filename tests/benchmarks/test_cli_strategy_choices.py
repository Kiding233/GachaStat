"""`1e-3` 的验收测试：`--strategy` 的 choices 动态生成与禁用项拒绝。

对应 P83 §3.9 T1 的「cli 入口断言」与 §3.10「`cli` 路径的 `strategy_key` 因子域」。

**为什么这些断言必须存在**：「参数键名即契约」是本库一贯口径，该行为不能只存在于
实现里——choices 由注册表生成、禁用项被拒且报错含出处，两件事都得能被回归验证。
"""

import os

import pytest

from gacha_simulator.cli import (
    _read_disabled_plugins,
    _reject_disabled_strategy,
    _strategy_choices,
)
from gacha_simulator.core.strategy import STRATEGY_REGISTRY, StrategyMeta


@pytest.fixture
def registry_snapshot():
    """保护全局注册表——用例内的临时条目不得泄漏给其它用例。"""
    snapshot = dict(STRATEGY_REGISTRY)
    try:
        yield STRATEGY_REGISTRY
    finally:
        STRATEGY_REGISTRY.clear()
        STRATEGY_REGISTRY.update(snapshot)


def _temp_config(tmp_path, disabled):
    """写一个只含 [plugins] 段的最小 TOML。"""
    path = tmp_path / 'config.toml'
    lines = ['[plugins]', f'disabled = {disabled!r}'.replace("'", '"')]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return str(path)


class TestChoicesGeneratedFromRegistry:
    def test_includes_no_draw(self):
        """`no_draw` 已注册却没进原来的字面量列表——「不抽卡基线」因子因此不可表达。"""
        assert 'no_draw' in _strategy_choices()

    def test_matches_registry_minus_internal(self, registry_snapshot):
        expected = {k for k, m in registry_snapshot.items() if not m.internal}
        assert set(_strategy_choices()) == expected

    def test_excludes_internal(self, registry_snapshot):
        registry_snapshot['__probe_internal__'] = StrategyMeta(
            key='__probe_internal__', display_name='probe', description='', internal=True)
        assert '__probe_internal__' not in _strategy_choices()

    def test_is_dynamic_not_literal(self, registry_snapshot):
        """动态性的证明：新注册的非 internal 键**立刻**出现在 choices 里。

        这条是「插件策略因子可达」的核心断言——若 choices 是字面量，本用例必失败。
        """
        registry_snapshot['__probe_plugin__'] = StrategyMeta(
            key='__probe_plugin__', display_name='probe', description='', internal=False)
        assert '__probe_plugin__' in _strategy_choices()


class TestDisabledRejection:
    def test_disabled_key_rejected_with_provenance(self, tmp_path, capsys):
        config = _temp_config(tmp_path, ['__probe_disabled__'])
        with pytest.raises(SystemExit) as excinfo:
            _reject_disabled_strategy('__probe_disabled__', config)
        assert excinfo.value.code == 2
        err = capsys.readouterr().err
        assert '__probe_disabled__' in err, '错误信息须含被禁用的 key'
        assert '[plugins].disabled' in err, '错误信息须含出处'
        assert config in err, '出处须指到具体配置文件'

    def test_enabled_key_passes(self, tmp_path):
        config = _temp_config(tmp_path, ['__probe_disabled__'])
        assert _reject_disabled_strategy('smart', config) is None

    def test_none_strategy_passes(self, tmp_path):
        config = _temp_config(tmp_path, ['smart'])
        assert _reject_disabled_strategy(None, config) is None

    def test_missing_config_treated_as_no_disabled(self, tmp_path):
        missing = str(tmp_path / 'nope.toml')
        assert _read_disabled_plugins(missing) == []
        assert _reject_disabled_strategy('smart', missing) is None

    def test_config_without_plugins_section(self, tmp_path):
        path = tmp_path / 'plain.toml'
        path.write_text('[strategy]\nkey = "smart"\n', encoding='utf-8')
        assert _read_disabled_plugins(str(path)) == []


class TestReadIsReallyReadOnly:
    """§3.10 的纪律：禁用集取法**只读比对、不得调用 `_build_plugins`**。

    `_build_plugins` 会把注册表里对应条目的 `meta.disabled` 置 `True`（全局注册表
    副作用），而这条 CLI 进程紧接着就要跑模拟，污染注册表会改变 `create_strategy()`
    的守卫行为与后续 `--strategy` 语义。
    """

    def test_registry_untouched(self, tmp_path, registry_snapshot):
        registry_snapshot['__probe_plugin__'] = StrategyMeta(
            key='__probe_plugin__', display_name='probe', description='', internal=False)
        assert registry_snapshot['__probe_plugin__'].disabled is False

        config = _temp_config(tmp_path, ['__probe_plugin__'])
        assert _read_disabled_plugins(config) == ['__probe_plugin__']

        assert registry_snapshot['__probe_plugin__'].disabled is False, (
            '_read_disabled_plugins 不得改变注册表条目的 disabled —— 那是 _build_plugins 的副作用'
        )
        # 且不因禁用而从 choices 中消失（choices 只排除 internal）
        assert '__probe_plugin__' in _strategy_choices()


class TestCliEndToEnd:
    """真实起进程断言 argparse 层的行为（choices 是**在 parser 构造时**求值的，
    故只有真的起一次 CLI 才能验证它确实落进了 parser）。"""

    @staticmethod
    def _run(*argv):
        import subprocess
        import sys

        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return subprocess.run(
            [sys.executable, '-m', 'gacha_simulator.cli', *argv],
            capture_output=True, text=True, encoding='utf-8', cwd=root,
        )

    def test_help_lists_no_draw(self):
        result = self._run('--help')
        assert result.returncode == 0
        assert 'no_draw' in result.stdout, '--help 的 choices 应含 no_draw'

    def test_invalid_choice_rejected_by_argparse(self):
        result = self._run('--strategy', '__nope__', '-n', '1')
        assert result.returncode == 2
        assert 'invalid choice' in result.stderr
