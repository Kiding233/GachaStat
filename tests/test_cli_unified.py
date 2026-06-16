"""P54 CLI/GUI 统一化重构——端到端 smoke test。"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def _run_cli(*args: str) -> str:
    """运行 CLI 并捕获 stdout。"""
    cmd = [sys.executable, "-m", "gacha_simulator.cli", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                            cwd=str(Path(__file__).parent.parent))
    return result.stdout, result.stderr


def test_simple_mode_output_format():
    """C1: 验证 simple 模式 JSON 输出结构。"""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out_path = f.name

    try:
        stdout, _ = _run_cli("-n", "10", "-w", "2", "-s", "42", "-o", out_path)
        data = json.load(open(out_path))

        # (a) JSON 顶层键
        for key in ("config", "num_simulations", "elapsed_time", "summary"):
            assert key in data, f"Missing top-level key: {key}"

        # (b) summary.total_draws 含 mean/median/std 三个数值
        td = data["summary"]["total_draws"]
        for stat in ("mean", "median", "std"):
            assert stat in td, f"Missing total_draws.{stat}"
            assert isinstance(td[stat], (int, float)), f"total_draws.{stat} not numeric"

        # (c) summary.gdr_percent 含 mean/median/p25/p75 四个数值
        gp = data["summary"]["gdr_percent"]
        for stat in ("mean", "median", "p25", "p75"):
            assert stat in gp, f"Missing gdr_percent.{stat}"
            assert isinstance(gp[stat], (int, float)), f"gdr_percent.{stat} not numeric"

        # 基础合理性：10 次模拟应产生 10 个结果
        assert data["num_simulations"] == 10

        # Console 输出应包含关键文本
        assert "GachaStat CLI" in stdout
        assert "Results Summary" in stdout
    finally:
        Path(out_path).unlink(missing_ok=True)


def test_full_mode_extraction():
    """C3: 验证 full 模式输出含 extraction 摘要。"""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out_path = f.name

    try:
        _run_cli("-n", "10", "-w", "2", "-s", "42",
                 "--output-format", "full", "-o", out_path)
        data = json.load(open(out_path))

        assert "extraction" in data, "full mode should contain extraction key"
        ext = data["extraction"]
        for key in ("n_results", "aggregates_count", "kept_sequences_count",
                     "cumulative_snapshots_pools", "transition_flags_count"):
            assert key in ext, f"Missing extraction.{key}"
    finally:
        Path(out_path).unlink(missing_ok=True)


def test_no_pity_flag():
    """C2 变体: 验证 --no-pity 不影响 CLI 正常运行。"""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out_path = f.name

    try:
        stdout, _ = _run_cli("-n", "5", "-w", "1", "-s", "42",
                             "--no-pity", "-o", out_path)
        data = json.load(open(out_path))
        assert data["num_simulations"] == 5
        # --no-pity 下 pity_enabled 应为 False
        assert data["config"]["pity_enabled"] is False
    finally:
        Path(out_path).unlink(missing_ok=True)


def test_strategy_flag():
    """C2: 验证 --strategy 参数正常运作。"""
    for strat in ("target_hunting", "pool_quota", "smart"):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = f.name
        try:
            stdout, _ = _run_cli("-n", "5", "-s", "42",
                                 "--strategy", strat, "-o", out_path)
            data = json.load(open(out_path))
            assert data["num_simulations"] == 5
        finally:
            Path(out_path).unlink(missing_ok=True)


def test_no_progress_flag():
    """验证 --no-progress 禁用进度条输出。"""
    stdout, _ = _run_cli("-n", "5", "-s", "42", "--no-progress",
                         "-o", tempfile.gettempdir() + "/test_np_cli.json")
    # 进度条不应出现在输出中
    assert "进度:" not in stdout


def test_code_cleanliness():
    """C4+C5: 验证 run_single_sim() 已删除，不再直接引用 Pool。"""
    cli_path = Path(__file__).parent.parent / "gacha_simulator" / "cli.py"
    source = cli_path.read_text(encoding="utf-8")

    # C4: run_single_sim 函数已删除
    assert "def run_single_sim" not in source, "run_single_sim() should be deleted"

    # C5: 不再直接调用 multiprocessing.Pool
    assert "from multiprocessing import Pool" not in source, \
        "Direct Pool import should be removed"
