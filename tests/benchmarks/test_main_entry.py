"""T1：命令入口薄壳（`benchmarks/perf/__main__.py`）。

对应 §3.9 T1 的「命令入口薄壳（`__main__.py` 的参数解析与输出格式）」与 `1k` 行自述
的三项：argv 解析 / 缺基线时错误退出 / 输出格式含比值。

**不跑真实模拟**：适配器由桩替换，故本文件秒级完成。真实端到端由 `1i` 的 T3 承担。
"""

import json

import pytest

from benchmarks.perf import __main__ as entry
from benchmarks.perf.adapters.base import Adapter, SingleRun


def _plan_payload(**overrides):
    base = {'config_path': 'config/config.toml', 'strategy_key': 'smart',
            'strategy_params': {}, 'n': 100, 'workers': 2, 'seed': 42}
    base.update(overrides)
    return base


class _StubAdapter(Adapter):
    name = 'stub'
    is_user_path = True

    def __init__(self, wall=1.0, available=True):
        self._wall = wall
        self._available = available

    def available(self):
        return self._available

    def _run_once(self, plan):
        # return_compact 必须如实给出：它是可比性维度，为 None 会让比对判不可比，
        # 于是本文件里所有「出比值」的断言都会落空（cli 适配器给的是 True）。
        return SingleRun(wall=self._wall, stages={'simulate': self._wall},
                         return_compact=True)


@pytest.fixture
def stub(monkeypatch):
    """把 `get_adapter` 换成桩，并把基线根指向临时目录。"""
    holder = {}

    def factory(wall=1.0, available=True):
        adapter = _StubAdapter(wall=wall, available=available)
        holder['adapter'] = adapter
        monkeypatch.setattr(entry, 'get_adapter', lambda path: adapter)
        return adapter
    return factory


@pytest.fixture
def plan_file(tmp_path):
    def factory(**overrides):
        path = tmp_path / 'plan.json'
        path.write_text(json.dumps(_plan_payload(**overrides), ensure_ascii=False),
                        encoding='utf-8')
        return str(path)
    return factory


@pytest.fixture
def baseline_root(tmp_path, monkeypatch):
    """把 `baselines/` 指向临时目录——用例不得写入仓库。"""
    root = tmp_path / 'baselines'
    monkeypatch.setattr(entry, 'register_baseline',
                        lambda name, result: _fake_register(root, name, result))
    monkeypatch.setattr(entry, 'load_baseline',
                        lambda name, fp: _fake_load(root, name, fp))
    return root


def _fake_register(root, name, result):
    from benchmarks.perf.report import register_baseline
    return register_baseline(name, result, root=root)


def _fake_load(root, name, fingerprint):
    from benchmarks.perf.report import load_baseline
    return load_baseline(name, fingerprint, root=root)


class TestArgumentParsing:
    def test_run_requires_plan(self):
        with pytest.raises(SystemExit) as excinfo:
            entry.build_parser().parse_args(['run'])
        assert excinfo.value.code == 2

    def test_run_parses_plan(self):
        args = entry.build_parser().parse_args(['run', '--plan', 'p.json'])
        assert args.command == 'run' and args.plan == 'p.json'
        assert args.baseline is None and args.register is False

    def test_register_flag(self):
        args = entry.build_parser().parse_args(
            ['run', '--plan', 'p.json', '--baseline', 'b', '--register'])
        assert args.register is True and args.baseline == 'b'

    def test_missing_subcommand(self):
        with pytest.raises(SystemExit):
            entry.build_parser().parse_args([])


class TestPlanInputContract:
    """`plan.json` 的规格由 `Plan.from_dict()` 定义，薄壳不另定规格。"""

    def test_unknown_key_exits_nonzero(self, tmp_path, capsys):
        path = tmp_path / 'bad.json'
        path.write_text(json.dumps({**_plan_payload(), 'nope': 1}), encoding='utf-8')
        assert entry.main(['run', '--plan', str(path)]) == entry.EXIT_USAGE
        assert '未知键' in capsys.readouterr().err

    def test_invalid_value_exits_nonzero(self, tmp_path, capsys):
        path = tmp_path / 'bad.json'
        path.write_text(json.dumps({**_plan_payload(), 'grain': 'turbo'}), encoding='utf-8')
        assert entry.main(['run', '--plan', str(path)]) == entry.EXIT_USAGE
        assert 'grain' in capsys.readouterr().err

    def test_missing_file_exits_nonzero(self, tmp_path, capsys):
        assert entry.main(['run', '--plan', str(tmp_path / 'nope.json')]) == entry.EXIT_USAGE
        assert '读不到' in capsys.readouterr().err

    def test_not_json_exits_nonzero(self, tmp_path):
        path = tmp_path / 'bad.json'
        path.write_text('{ not json', encoding='utf-8')
        assert entry.main(['run', '--plan', str(path)]) == entry.EXIT_USAGE

    def test_missing_keys_fall_back_to_defaults(self, plan_file, stub, baseline_root, capsys):
        stub()
        assert entry.main(['run', '--plan', plan_file(), '--baseline', 'b',
                           '--register']) == entry.EXIT_OK


class TestUnavailablePath:
    def test_unavailable_adapter_exits_three(self, plan_file, stub, capsys):
        stub(available=False)
        assert entry.main(['run', '--plan', plan_file()]) == entry.EXIT_UNAVAILABLE
        assert '不可用' in capsys.readouterr().err


class TestBaselineFlow:
    def test_missing_baseline_exits_nonzero(self, plan_file, stub, baseline_root, capsys):
        stub()
        assert entry.main(['run', '--plan', plan_file(), '--baseline', 'nope']) == entry.EXIT_USAGE
        assert '找不到基线' in capsys.readouterr().err

    def test_no_baseline_flag_exits_nonzero(self, plan_file, stub, capsys):
        stub()
        assert entry.main(['run', '--plan', plan_file()]) == entry.EXIT_USAGE
        assert '--register' in capsys.readouterr().err

    def test_register_requires_name(self, plan_file, stub, capsys):
        stub()
        assert entry.main(['run', '--plan', plan_file(), '--register']) == entry.EXIT_USAGE

    def test_register_rejects_insufficient_repeats(self, plan_file, stub, baseline_root, capsys):
        """建基线须 repeats >= 3——`1f` 的门禁在此被薄壳如实透出。"""
        stub()
        code = entry.main(['run', '--plan', plan_file(repeats=1), '--baseline', 'b',
                           '--register'])
        assert code == entry.EXIT_USAGE
        assert 'repeats' in capsys.readouterr().err

    def test_ratio_in_output(self, plan_file, stub, baseline_root, capsys):
        stub(wall=1.0)
        assert entry.main(['run', '--plan', plan_file(), '--baseline', 'b',
                           '--register']) == entry.EXIT_OK
        capsys.readouterr()

        stub(wall=1.25)
        assert entry.main(['run', '--plan', plan_file(), '--baseline', 'b']) == entry.EXIT_OK
        out = capsys.readouterr().out
        assert '总墙钟比值' in out
        assert '1.250' in out
        assert '结论' in out and '基线 b' in out

    def test_quiet_prints_only_the_ratio(self, plan_file, stub, baseline_root, capsys):
        stub(wall=1.0)
        entry.main(['run', '--plan', plan_file(), '--baseline', 'b', '--register'])
        capsys.readouterr()

        stub(wall=1.5)
        entry.main(['run', '--plan', plan_file(), '--baseline', 'b', '--quiet'])
        out = capsys.readouterr().out
        assert '1.500' in out
        assert '本次记录' not in out, '--quiet 不应打印记录详情'
