"""测试 H2 安全门禁——rm/rmdir 拦截"""
import sys, json
sys.path.insert(0, '.claude/hooks')
from safety_gate import main
import io


def test(cmd):
    inp = json.dumps({"tool_input": {"command": cmd}, "cwd": "."})
    sys.stdin = io.StringIO(inp)
    code = main()
    label = "放行" if code == 0 else f"阻止(exit {code})"
    print(f"  [{label}] {cmd}")


print("=== 应被阻止 ===")
test("rm file.txt")
test("rm -rf some/folder")
test("rmdir old_dir")
test("cd /tmp && rm -rf data")
print()
print("=== 应放行 ===")
test("python -c 'from scipy import norm'")
test("git status")
test('echo "confirm action"')
test("python -m pytest")
test("python -c 'import shutil; print(shutil.rmtree)'")
test("git commit -m 'fix: remove deprecated api'")
