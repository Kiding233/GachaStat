"""
P66 plan-execute workflow.js 核心逻辑测试。

本测试文件将 workflow.js 中的纯函数逻辑提取为 Python 等价实现并验证，
覆盖：参数解析、审计收敛算法、发现去重、JSON Schema 结构。

映射关系：
  workflow.js L347-365  →  parse_workflow_args()
  workflow.js L549-576  →  run_audit_round() / should_converge()
  workflow.js L575-580  →  dedup_findings()
  workflow.js L89-151   →  schemas 结构校验
"""

from __future__ import annotations

import json
import pytest
from typing import Any, Dict, List, Optional, Set, Union


# ═══════════════════════════════════════════════════════════════════
# 纯函数——从 workflow.js 提取的 Python 等价逻辑
# ═══════════════════════════════════════════════════════════════════

def parse_workflow_args(args: Union[str, List[str], Dict[str, Any], None]) -> Dict[str, Any]:
    """等价于 workflow.js L347-365 参数解析（已修正 Array.isArray 优先检查）。

    修正说明：JS 中 typeof [] === 'object'，原实现将 Array 分支放在 object 分支之后，
    导致数组入参被 object 分支误捕获，--skip-audit/--audit-only 标志丢失。
    修正后将 Array.isArray 检查提前至 typeof === 'object' 之前。
    """
    if args is None:
        return {"planFilePath": None, "skipAudit": False, "auditOnly": False, "maxRounds": 5}
    if isinstance(args, str):
        return {"planFilePath": args, "skipAudit": False, "auditOnly": False, "maxRounds": 5}
    # 修正：Array.isArray 必须在 isinstance(dict) 之前检查
    if isinstance(args, list):
        plan = args[0] if len(args) > 0 else None
        skip_audit = "--skip-audit" in args
        audit_only = "--audit-only" in args
        max_rounds = 5
        try:
            mr_idx = args.index("--max-rounds")
            max_rounds = int(args[mr_idx + 1])
        except (ValueError, IndexError):
            max_rounds = 5
        return {"planFilePath": plan, "skipAudit": skip_audit, "auditOnly": audit_only, "maxRounds": max(max_rounds, 1)}
    if isinstance(args, dict):
        return {
            "planFilePath": args.get("planFilePath"),
            "skipAudit": args.get("skipAudit", False),
            "auditOnly": args.get("auditOnly", False),
            "maxRounds": args.get("maxRounds", 5),
        }
    return {"planFilePath": None, "skipAudit": False, "auditOnly": False, "maxRounds": 5}


def dedup_findings(
    findings: List[Dict[str, Any]],
    seen_keys: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """等价于 workflow.js L575-580 发现去重逻辑。

    复合 key = dimension::file::description，跨维度共享 seen_keys Set。
    """
    if seen_keys is None:
        seen_keys = set()
    result = []
    for f in findings:
        key = f"{f.get('dimension', '')}::{f.get('file', '')}::{f.get('description', '')}"
        if key not in seen_keys:
            seen_keys.add(key)
            result.append(f)
    return result


def run_audit_round(
    dry_rounds: int,
    total_rounds: int,
    max_rounds: int,
    new_findings: List[Dict[str, Any]],
    seen_keys: Set[str],
) -> Dict[str, Any]:
    """等价于 workflow.js L549-576 单轮审计循环核心逻辑。

    返回: {dryRounds, totalRounds, shouldBreak, shouldContinue, newFindings}
    """
    total_rounds += 1

    if total_rounds > max_rounds:
        # 超出最大轮数，交由调用方处理熔断
        return {"dryRounds": dry_rounds, "totalRounds": total_rounds,
                "shouldBreak": False, "shouldContinue": False, "maxReached": True,
                "newFindings": []}

    # 去重
    unique_findings = dedup_findings(new_findings, seen_keys)

    if len(unique_findings) == 0:
        dry_rounds += 1
        should_break = dry_rounds >= 2
        return {"dryRounds": dry_rounds, "totalRounds": total_rounds,
                "shouldBreak": should_break, "shouldContinue": not should_break,
                "newFindings": []}

    # 有新发现——重置 dryRounds
    return {"dryRounds": 0, "totalRounds": total_rounds,
            "shouldBreak": False, "shouldContinue": False,
            "newFindings": unique_findings}


def classify_severity(findings: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """等价于 workflow.js L596-598 按严重度分类。"""
    result = {"critical": [], "important": [], "minor": []}
    for f in findings:
        sev = f.get("severity", "minor")
        if sev in result:
            result[sev].append(f)
    return result


# ═══════════════════════════════════════════════════════════════════
# JSON Schema 结构定义（从 workflow.js 提取）
# ═══════════════════════════════════════════════════════════════════

AUDITOR_SCHEMA = {
    "type": "object",
    "properties": {
        "dimension": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "task_id": {"type": "string"},
                    "severity": {"type": "string", "enum": ["critical", "important", "minor"]},
                    "description": {"type": "string"},
                    "file": {"type": "string"},
                    "line": {"type": "number"},
                    "evidence": {"type": "string"},
                    # 维度特有字段（已扩展）
                    "status": {"type": "string"},
                    "planned": {"type": "string"},
                    "actual": {"type": "string"},
                    "constraint": {"type": "string"},
                    "violation": {"type": "string"},
                    "change_summary": {"type": "string"},
                    "risk": {"type": "string", "enum": ["high", "medium", "low"]},
                    "scenario": {"type": "string"},
                    "covered": {"type": "string"},
                    "test_location": {"type": "string"},
                },
                "required": ["id", "severity", "description"],
            },
        },
        "no_findings": {"type": "boolean"},
    },
    "required": ["dimension", "findings", "no_findings"],
}

FIXER_SCHEMA = {
    "type": "object",
    "properties": {
        "fixed": {"type": "number"},
        "skipped": {"type": "array", "items": {"type": "object"}},
        "files_modified": {"type": "array", "items": {"type": "string"}},
        "test_results": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["fixed"],
}

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "tests_pass": {"type": "boolean"},
        "test_output_summary": {"type": "string"},
        "code_review_issues": {"type": "number"},
        "blocking": {"type": "boolean"},
    },
    "required": ["tests_pass", "blocking"],
}


# ═══════════════════════════════════════════════════════════════════
# 测试：参数解析（workflow.js L347-365）
# ═══════════════════════════════════════════════════════════════════

class TestArgumentParsing:
    """参数解析——对应 workflow.js 三种入参格式（string/object/array）。"""

    def test_string_format(self):
        """字符串入参：直接作为 planFilePath。"""
        result = parse_workflow_args("path/to/plan.md")
        assert result["planFilePath"] == "path/to/plan.md"
        assert result["skipAudit"] is False
        assert result["auditOnly"] is False
        assert result["maxRounds"] == 5

    def test_object_format(self):
        """对象入参：提取各字段。"""
        result = parse_workflow_args({
            "planFilePath": "path/to/plan.md",
            "skipAudit": True,
            "auditOnly": False,
            "maxRounds": 3,
        })
        assert result["planFilePath"] == "path/to/plan.md"
        assert result["skipAudit"] is True
        assert result["auditOnly"] is False
        assert result["maxRounds"] == 3

    def test_object_format_defaults(self):
        """对象入参缺省字段使用默认值。"""
        result = parse_workflow_args({"planFilePath": "plan.md"})
        assert result["planFilePath"] == "plan.md"
        assert result["skipAudit"] is False
        assert result["auditOnly"] is False
        assert result["maxRounds"] == 5

    def test_array_format_basic(self):
        """数组入参——skill 传入的标准格式。"""
        result = parse_workflow_args(["path/to/plan.md"])
        assert result["planFilePath"] == "path/to/plan.md"
        assert result["skipAudit"] is False
        assert result["auditOnly"] is False
        assert result["maxRounds"] == 5

    def test_array_format_skip_audit(self):
        """数组入参带 --skip-audit 标志。"""
        result = parse_workflow_args(["path/to/plan.md", "--skip-audit"])
        assert result["planFilePath"] == "path/to/plan.md"
        assert result["skipAudit"] is True
        assert result["auditOnly"] is False
        assert result["maxRounds"] == 5

    def test_array_format_audit_only(self):
        """数组入参带 --audit-only 标志。"""
        result = parse_workflow_args(["path/to/plan.md", "--audit-only"])
        assert result["planFilePath"] == "path/to/plan.md"
        assert result["skipAudit"] is False
        assert result["auditOnly"] is True
        assert result["maxRounds"] == 5

    def test_array_format_max_rounds(self):
        """数组入参带 --max-rounds N。"""
        result = parse_workflow_args(["path/to/plan.md", "--max-rounds", "3"])
        assert result["planFilePath"] == "path/to/plan.md"
        assert result["maxRounds"] == 3

    def test_array_format_max_rounds_invalid_fallback(self):
        """--max-rounds 后接非数字时回退到默认值 5。"""
        result = parse_workflow_args(["path/to/plan.md", "--max-rounds", "abc"])
        assert result["maxRounds"] == 5

    def test_array_format_max_rounds_missing_value(self):
        """--max-rounds 后无值时回退到默认值 5。"""
        result = parse_workflow_args(["path/to/plan.md", "--max-rounds"])
        assert result["maxRounds"] == 5

    def test_array_format_combined_flags(self):
        """数组入参同时带 --skip-audit 和 --max-rounds。"""
        result = parse_workflow_args(["path/to/plan.md", "--skip-audit", "--max-rounds", "7"])
        assert result["planFilePath"] == "path/to/plan.md"
        assert result["skipAudit"] is True
        assert result["maxRounds"] == 7

    def test_array_before_object_priority(self):
        """验证 Array.isArray 检查优先于 typeof object——修正后的行为。

        这是关键回归测试：JS 中 typeof [] === 'object'，
        若 Array 检查排在 object 之后，数组将被误判为 object，
        导致 --skip-audit 等标志丢失。
        """
        # 数组入参——必须走数组分支（提取标志）
        result = parse_workflow_args(["plan.md", "--audit-only"])
        assert result["auditOnly"] is True  # 此断言在原实现中会失败

    def test_none_input(self):
        """None 入参返回默认值。"""
        result = parse_workflow_args(None)
        assert result["planFilePath"] is None
        assert result["skipAudit"] is False
        assert result["maxRounds"] == 5

    def test_empty_array(self):
        """空数组入参——planFilePath 为 None。"""
        result = parse_workflow_args([])
        assert result["planFilePath"] is None


# ═══════════════════════════════════════════════════════════════════
# 测试：发现去重（workflow.js L575-580）
# ═══════════════════════════════════════════════════════════════════

class TestFindingDedup:
    """发现去重——复合 key（dimension::file::description）跨维度共享 Set。"""

    def test_no_duplicates(self):
        """无重复时全部保留。"""
        findings = [
            {"dimension": "completeness", "file": "a.py", "description": "missing func"},
            {"dimension": "interface", "file": "b.py", "description": "sig mismatch"},
        ]
        result = dedup_findings(findings)
        assert len(result) == 2

    def test_duplicate_exact_match(self):
        """完全相同的 key 仅保留第一个。"""
        findings = [
            {"dimension": "completeness", "file": "a.py", "description": "missing func"},
            {"dimension": "completeness", "file": "a.py", "description": "missing func"},
        ]
        result = dedup_findings(findings)
        assert len(result) == 1

    def test_duplicate_across_dimensions(self):
        """不同维度报告相同文件+描述——因 composite key 含 dimension，不冲突，均保留。

        这是设计意图：completeness 维度报告「a.py 缺少函数」与 interface 维度
        报告「a.py 缺少函数」是两个不同维度的独立发现，修复者需要分别处理。
        """
        findings = [
            {"dimension": "completeness", "file": "a.py", "description": "missing func"},
            {"dimension": "interface", "file": "a.py", "description": "missing func"},
        ]
        result = dedup_findings(findings)
        assert len(result) == 2  # 不同维度 → 不同 composite key → 均保留

    def test_different_files_same_description(self):
        """不同文件相同描述——不同 key，应全部保留。"""
        findings = [
            {"dimension": "completeness", "file": "a.py", "description": "missing func"},
            {"dimension": "completeness", "file": "b.py", "description": "missing func"},
        ]
        result = dedup_findings(findings)
        assert len(result) == 2

    def test_shared_seen_keys(self):
        """跨轮次共享 seen_keys——第二轮中第一轮的 key 被去重。"""
        seen = set()
        round1 = [{"dimension": "completeness", "file": "a.py", "description": "bug"}]
        dedup_findings(round1, seen)
        round2 = [{"dimension": "completeness", "file": "a.py", "description": "bug"}]
        result = dedup_findings(round2, seen)
        assert len(result) == 0  # 第二轮中此发现已在第一轮被记录

    def test_missing_fields_defaults(self):
        """字段缺失时使用空字符串作为 key 的一部分。"""
        findings = [
            {"description": "some bug"},
            {"description": "some bug"},
        ]
        result = dedup_findings(findings)
        assert len(result) == 1  # 相同复合 key "::::some bug"

    def test_empty_findings(self):
        """空列表返回空列表。"""
        result = dedup_findings([])
        assert result == []


# ═══════════════════════════════════════════════════════════════════
# 测试：收敛算法（workflow.js L549-576）
# ═══════════════════════════════════════════════════════════════════

class TestConvergenceAlgorithm:
    """审计收敛算法——dryRounds 计数 + maxRounds 熔断。"""

    def make_finding(self, dimension="completeness", file="a.py", description="bug"):
        return {"dimension": dimension, "file": file, "description": description,
                "severity": "important", "id": "TEST-001", "evidence": "test"}

    def test_consecutive_two_dry_rounds_converges(self):
        """连续 2 轮零新发现——收敛。"""
        seen = set()
        # 第 1 轮：有发现
        r1 = run_audit_round(0, 0, 5, [self.make_finding()], seen)
        assert r1["dryRounds"] == 0
        assert r1["shouldBreak"] is False
        assert len(r1["newFindings"]) == 1

        # 第 2 轮：零新发现
        r2 = run_audit_round(r1["dryRounds"], r1["totalRounds"], 5, [], seen)
        assert r2["dryRounds"] == 1
        assert r2["shouldBreak"] is False  # 仅 1 轮 dry，不收敛

        # 第 3 轮：零新发现
        r3 = run_audit_round(r2["dryRounds"], r2["totalRounds"], 5, [], seen)
        assert r3["dryRounds"] == 2
        assert r3["shouldBreak"] is True   # 连续 2 轮 dry，收敛
        assert r3["shouldContinue"] is False

    def test_dry_reset_on_new_finding(self):
        """有新发现时 dryRounds 重置为 0。"""
        seen = set()
        # 第 1 轮：有发现
        r1 = run_audit_round(0, 0, 5, [self.make_finding(description="bug1")], seen)
        assert r1["dryRounds"] == 0

        # 第 2 轮：零发现
        r2 = run_audit_round(r1["dryRounds"], r1["totalRounds"], 5, [], seen)
        assert r2["dryRounds"] == 1

        # 第 3 轮：有新发现——dryRounds 重置
        r3 = run_audit_round(r2["dryRounds"], r2["totalRounds"], 5,
                             [self.make_finding(description="bug2")], seen)
        assert r3["dryRounds"] == 0
        assert r3["shouldBreak"] is False

    def test_single_dry_does_not_stop(self):
        """仅 1 轮零发现不应停止。"""
        seen = set()
        r1 = run_audit_round(1, 0, 5, [], seen)
        assert r1["dryRounds"] == 2  # 从1到2
        assert r1["shouldBreak"] is True
        # 但如果从 0 开始，仅 1 轮 dry
        r2 = run_audit_round(0, 0, 5, [], seen)
        assert r2["dryRounds"] == 1
        assert r2["shouldBreak"] is False

    def test_max_rounds_circuit_breaker(self):
        """达到 maxRounds 时触发熔断标记。

        totalRounds 在每轮开始前递增，当递增后值 > maxRounds 时熔断。
        模拟：已执行 3 轮（total=3），maxRounds=3，下轮会触发熔断。
        """
        seen = set()
        r = run_audit_round(0, 3, 3, [], seen)
        assert r.get("maxReached") is True

    def test_max_rounds_not_exceeded(self):
        """total_rounds 在允许范围内正常执行。"""
        seen = set()
        r = run_audit_round(0, 0, 3, [self.make_finding()], seen)
        assert "maxReached" not in r or r.get("maxReached") is not True
        assert r["totalRounds"] == 1

    def test_max_rounds_boundary_zero(self):
        """maxRounds=0 时第一轮即熔断。"""
        seen = set()
        r = run_audit_round(0, 0, 0, [], seen)
        assert r["maxReached"] is True  # totalRounds(1) > maxRounds(0)

    def test_max_rounds_one(self):
        """maxRounds=1 时第 2 轮熔断。"""
        seen = set()
        r1 = run_audit_round(0, 0, 1, [self.make_finding()], seen)
        assert "maxReached" not in r1 or r1.get("maxReached") is not True  # 第1轮正常

        r2 = run_audit_round(r1["dryRounds"], r1["totalRounds"], 1, [], seen)
        assert r2["maxReached"] is True  # 第2轮熔断

    def test_dedup_before_dry_check(self):
        """先有发现但全部被去重——应视为零新发现。"""
        seen = {"completeness::a.py::bug"}  # 已存在
        r = run_audit_round(0, 0, 5, [self.make_finding()], seen)
        assert r["dryRounds"] == 1  # 去重后无新发现
        assert r["shouldBreak"] is False
        assert len(r["newFindings"]) == 0

    def test_partial_dimensions_have_findings(self):
        """部分维度有发现、部分无发现——有发现的维度结果正常。"""
        seen = set()
        findings = [
            self.make_finding(dimension="completeness", description="bug1"),
            self.make_finding(dimension="completeness", description="bug2"),
        ]
        r = run_audit_round(0, 0, 5, findings, seen)
        assert r["dryRounds"] == 0
        assert len(r["newFindings"]) == 2  # 两个不同描述，不同 key


# ═══════════════════════════════════════════════════════════════════
# 测试：严重度分类（workflow.js L596-598）
# ═══════════════════════════════════════════════════════════════════

class TestSeverityClassification:
    """按严重度分类。"""

    def test_mixed_severities(self):
        findings = [
            {"severity": "critical", "description": "c1"},
            {"severity": "important", "description": "i1"},
            {"severity": "minor", "description": "m1"},
            {"severity": "critical", "description": "c2"},
            {"severity": "important", "description": "i2"},
        ]
        result = classify_severity(findings)
        assert len(result["critical"]) == 2
        assert len(result["important"]) == 2
        assert len(result["minor"]) == 1

    def test_empty_findings(self):
        result = classify_severity([])
        assert result["critical"] == []
        assert result["important"] == []
        assert result["minor"] == []

    def test_unknown_severity_defaults(self):
        """未知 severity 不归入任何标准分类。"""
        findings = [{"severity": "unknown", "description": "x"}]
        result = classify_severity(findings)
        assert len(result["critical"]) == 0
        assert len(result["important"]) == 0
        assert len(result["minor"]) == 0


# ═══════════════════════════════════════════════════════════════════
# 测试：JSON Schema 结构校验
# ═══════════════════════════════════════════════════════════════════

class TestAuditorSchema:
    """AUDITOR_SCHEMA 结构校验——对应 workflow.js L89-128。"""

    def test_required_top_level_fields(self):
        """顶层 required 包含 dimension/findings/no_findings。"""
        required = AUDITOR_SCHEMA["required"]
        assert "dimension" in required
        assert "findings" in required
        assert "no_findings" in required

    def test_finding_required_fields(self):
        """finding 项 required 包含 id/severity/description。"""
        item_req = AUDITOR_SCHEMA["properties"]["findings"]["items"]["required"]
        assert "id" in item_req
        assert "severity" in item_req
        assert "description" in item_req

    def test_severity_enum(self):
        """severity 枚举值为 critical/important/minor。"""
        sev_enum = AUDITOR_SCHEMA["properties"]["findings"]["items"]["properties"]["severity"]["enum"]
        assert "critical" in sev_enum
        assert "important" in sev_enum
        assert "minor" in sev_enum

    def test_dimension_specific_fields_present(self):
        """维度特有字段均已在 schema 中定义（IFACE-003/004 修正）。"""
        item_props = AUDITOR_SCHEMA["properties"]["findings"]["items"]["properties"]
        # 接口 fidelity 特有字段
        assert "planned" in item_props
        assert "actual" in item_props
        # 约束 fidelity 特有字段
        assert "constraint" in item_props
        assert "violation" in item_props
        # 计划外变更特有字段
        assert "change_summary" in item_props
        assert "risk" in item_props
        # 测试覆盖特有字段
        assert "scenario" in item_props
        assert "covered" in item_props
        assert "test_location" in item_props
        # 完整性特有字段
        assert "status" in item_props

    def test_risk_enum(self):
        """risk 枚举值为 high/medium/low。"""
        risk_enum = AUDITOR_SCHEMA["properties"]["findings"]["items"]["properties"]["risk"]["enum"]
        assert set(risk_enum) == {"high", "medium", "low"}


class TestFixerSchema:
    """FIXER_SCHEMA 结构校验——对应 workflow.js L131-141。"""

    def test_required_fields(self):
        assert FIXER_SCHEMA["required"] == ["fixed"]

    def test_properties(self):
        props = FIXER_SCHEMA["properties"]
        assert "fixed" in props
        assert props["fixed"]["type"] == "number"
        assert "skipped" in props
        assert "files_modified" in props
        assert "test_results" in props
        assert "summary" in props


class TestVerifySchema:
    """VERIFY_SCHEMA 结构校验——对应 workflow.js L143-152。"""

    def test_required_fields(self):
        required = VERIFY_SCHEMA["required"]
        assert "tests_pass" in required
        assert "blocking" in required

    def test_properties(self):
        props = VERIFY_SCHEMA["properties"]
        assert props["tests_pass"]["type"] == "boolean"
        assert props["blocking"]["type"] == "boolean"
        assert props["code_review_issues"]["type"] == "number"


# ═══════════════════════════════════════════════════════════════════
# 测试：端到端审计循环模拟
# ═══════════════════════════════════════════════════════════════════

class TestEndToEndAuditLoop:
    """模拟完整的审计循环——对应 workflow.js 阶段 3。"""

    def make_finding(self, dimension, description, severity="important"):
        return {
            "dimension": dimension, "file": "test.py", "line": 1,
            "description": description, "severity": severity,
            "id": f"TEST-{hash(description) & 0xFFFF:04x}", "evidence": "test",
        }

    def test_full_convergence_scenario(self):
        """完整收敛场景：3 轮后收敛。"""
        seen = set()
        dry = 0
        total = 0
        max_r = 5
        all_fixed = []

        # 第 1 轮：3 个发现
        r1 = run_audit_round(dry, total, max_r, [
            self.make_finding("completeness", "bug-a"),
            self.make_finding("interface", "sig-mismatch"),
            self.make_finding("coverage", "no-test"),
        ], seen)
        assert r1["dryRounds"] == 0
        assert len(r1["newFindings"]) == 3
        all_fixed.extend(r1["newFindings"])
        dry, total = r1["dryRounds"], r1["totalRounds"]

        # 第 2 轮：无发现
        r2 = run_audit_round(dry, total, max_r, [], seen)
        assert r2["dryRounds"] == 1
        assert r2["shouldBreak"] is False
        dry, total = r2["dryRounds"], r2["totalRounds"]

        # 第 3 轮：无发现——收敛
        r3 = run_audit_round(dry, total, max_r, [], seen)
        assert r3["dryRounds"] == 2
        assert r3["shouldBreak"] is True
        dry, total = r3["dryRounds"], r3["totalRounds"]

        assert total == 3
        assert dry == 2
        assert len(all_fixed) == 3

    def test_interleaved_scenario(self):
        """交替有/无发现场景——dryRounds 在有发现时正确重置。"""
        seen = set()
        dry, total = 0, 0

        # 轮1: 有发现
        r = run_audit_round(dry, total, 5, [self.make_finding("completeness", "bug1")], seen)
        dry, total = r["dryRounds"], r["totalRounds"]
        assert dry == 0

        # 轮2: 无发现
        r = run_audit_round(dry, total, 5, [], seen)
        dry, total = r["dryRounds"], r["totalRounds"]
        assert dry == 1

        # 轮3: 有发现——dryRounds 重置为 0
        r = run_audit_round(dry, total, 5, [self.make_finding("interface", "bug2")], seen)
        dry, total = r["dryRounds"], r["totalRounds"]
        assert dry == 0

        # 轮4: 无发现
        r = run_audit_round(dry, total, 5, [], seen)
        dry, total = r["dryRounds"], r["totalRounds"]
        assert dry == 1

        # 轮5: 无发现——收敛
        r = run_audit_round(dry, total, 5, [], seen)
        dry, total = r["dryRounds"], r["totalRounds"]
        assert dry == 2
        assert r["shouldBreak"] is True

    def test_circuit_breaker_scenario(self):
        """熔断场景：maxRounds=3，第 3 轮仍有发现，第 4 轮触发熔断。"""
        seen = set()
        dry, total = 0, 0
        max_r = 3

        for round_num in range(1, 4):
            r = run_audit_round(dry, total, max_r,
                               [self.make_finding("completeness", f"bug-r{round_num}")],
                               seen)
            dry, total = r["dryRounds"], r["totalRounds"]
            assert r["shouldBreak"] is False

        # 第 4 轮：应触发熔断
        r = run_audit_round(dry, total, max_r, [], seen)
        assert r.get("maxReached") is True

    def test_empty_initial_round(self):
        """首轮即无发现——2 轮后收敛。"""
        seen = set()
        r1 = run_audit_round(0, 0, 5, [], seen)
        assert r1["dryRounds"] == 1
        assert r1["shouldBreak"] is False

        r2 = run_audit_round(r1["dryRounds"], r1["totalRounds"], 5, [], seen)
        assert r2["dryRounds"] == 2
        assert r2["shouldBreak"] is True


# ═══════════════════════════════════════════════════════════════════
# 纯函数——流水线状态转换逻辑（workflow.js L478-516）
# ═══════════════════════════════════════════════════════════════════

def should_skip_review(impl_status: Optional[str], agent_null: bool) -> bool:
    """等价于 workflow.js L479——判断是否跳过任务审查。

    AGENT_NULL（实现者返回 null）或 BLOCKED（实现者报告阻塞）时跳过审查。
    """
    if agent_null:
        return True
    if impl_status == "BLOCKED":
        return True
    return False


def should_skip_fix(skipped: bool, review_verdict: Optional[str]) -> bool:
    """等价于 workflow.js L508——判断是否跳过修复阶段。

    以下情况跳过修复：(1) 审查已跳过 (2) 审查结果为 null (3) 审查已 APPROVED。
    """
    if skipped:
        return True
    if review_verdict is None:
        return True
    if review_verdict == "APPROVED":
        return True
    return False


def is_task_complete(skipped: bool, review_verdict: Optional[str]) -> bool:
    """等价于 workflow.js L516——判断任务是否完成。

    仅当审查未跳过且判决为 APPROVED 时任务完成。
    """
    return (not skipped) and review_verdict == "APPROVED"


# ═══════════════════════════════════════════════════════════════════
# 纯函数——进度账本断点恢复逻辑（workflow.js L410-437）
# ═══════════════════════════════════════════════════════════════════

def build_completed_set(completed_tasks: List[str]) -> Set[str]:
    """等价于 workflow.js L418——从已完成任务 ID 列表构建 Set。

    所有 ID 归一化为字符串（兼容 ledger 中可能存在的数字格式）。
    """
    return {str(tid) for tid in completed_tasks}


def filter_pending_tasks(
    tasks: List[Dict[str, Any]],
    completed_ids: Set[str],
) -> List[Dict[str, Any]]:
    """等价于 workflow.js L434——过滤已完成任务，返回待执行列表。

    task.id 归一化为字符串后与 completed_ids 比较。
    """
    return [t for t in tasks if str(t.get("id", "")) not in completed_ids]


# ═══════════════════════════════════════════════════════════════════
# 纯函数——未解决清单格式化（workflow.js L690）
# ═══════════════════════════════════════════════════════════════════

def format_unresolved_item(finding: Dict[str, Any]) -> str:
    """等价于 workflow.js L690 模板字符串——格式化单个未解决发现为 Markdown 列表项。

    格式: `- [severity] ID: description (file:line)`
    文件名为 '未知文件' 当 file 缺失时；行号仅在有值时追加。
    """
    sev = finding.get("severity", "minor")
    fid = finding.get("id", "???")
    desc = finding.get("description", "")
    file = finding.get("file") or "未知文件"
    line = finding.get("line")
    loc = f"{file}:{line}" if line else file
    return f"- [{sev}] {fid}: {desc} ({loc})"


def format_unresolved_section(findings: List[Dict[str, Any]], max_rounds: int) -> str:
    """等价于 workflow.js L688-693——生成完整的「未解决项」Markdown 章节。

    包含标题、列表项和熔断说明脚注。
    """
    items = "\n".join(format_unresolved_item(f) for f in findings)
    return (
        f"## ⚠ Fidelity 审计未解决项\n\n"
        f"{items}\n\n"
        f"> 审计循环 {max_rounds} 轮后熔断。{len(findings)} 个发现未解决。请人工裁决。"
    )


# ═══════════════════════════════════════════════════════════════════
# 测试：流水线状态转换（workflow.js L478-516）——COV-001
# ═══════════════════════════════════════════════════════════════════

class TestPipelineStateMachine:
    """阶段 2 任务执行流水线——skip_review / skip_fix / complete 状态转换。"""

    # ── should_skip_review ──

    def test_skip_review_agent_null(self):
        """AGENT_NULL 时跳过审查。"""
        assert should_skip_review(None, agent_null=True) is True

    def test_skip_review_blocked(self):
        """BLOCKED 状态时跳过审查。"""
        assert should_skip_review("BLOCKED", agent_null=False) is True

    def test_skip_review_needs_context_not_skipped(self):
        """NEEDS_CONTEXT 当前不触发 skip_review（仅日志警告，与 BLOCKED 行为不同）。

        注意：workflow.js L479 仅检查 AGENT_NULL 和 BLOCKED，NEEDS_CONTEXT
        不在此列——实现者在 L467-468 中针对 NEEDS_CONTEXT 仅输出日志警告。
        此测试文档化该当前行为。
        """
        assert should_skip_review("NEEDS_CONTEXT", agent_null=False) is False

    def test_skip_review_done(self):
        """DONE 状态不跳过审查。"""
        assert should_skip_review("DONE", agent_null=False) is False

    def test_skip_review_done_with_concerns(self):
        """DONE_WITH_CONCERNS 状态不跳过审查。"""
        assert should_skip_review("DONE_WITH_CONCERNS", agent_null=False) is False

    def test_skip_review_normal_impl(self):
        """正常实现（非 null、非 BLOCKED）不跳过审查。"""
        assert should_skip_review("DONE", agent_null=False) is False

    # ── should_skip_fix ──

    def test_skip_fix_already_skipped(self):
        """审查阶段已跳过 → 跳过修复。"""
        assert should_skip_fix(skipped=True, review_verdict=None) is True

    def test_skip_fix_null_review(self):
        """审查结果为 null → 跳过修复。"""
        assert should_skip_fix(skipped=False, review_verdict=None) is True

    def test_skip_fix_approved(self):
        """审查 APPROVED → 跳过修复（无需修复）。"""
        assert should_skip_fix(skipped=False, review_verdict="APPROVED") is True

    def test_skip_fix_needs_fix(self):
        """审查 NEEDS_FIX → 不跳过修复。"""
        assert should_skip_fix(skipped=False, review_verdict="NEEDS_FIX") is False

    def test_skip_fix_blocked_review(self):
        """审查 BLOCKED → 不跳过修复（修复者应处理阻塞）。"""
        assert should_skip_fix(skipped=False, review_verdict="BLOCKED") is False

    # ── is_task_complete ──

    def test_complete_approved_not_skipped(self):
        """未跳过且 APPROVED → 完成。"""
        assert is_task_complete(skipped=False, review_verdict="APPROVED") is True

    def test_complete_skipped_approved(self):
        """已跳过即使 APPROVED → 未完成。"""
        assert is_task_complete(skipped=True, review_verdict="APPROVED") is False

    def test_complete_not_approved(self):
        """NEEDS_FIX → 未完成。"""
        assert is_task_complete(skipped=False, review_verdict="NEEDS_FIX") is False

    def test_complete_null_review(self):
        """审查 null → 未完成。"""
        assert is_task_complete(skipped=False, review_verdict=None) is False

    def test_complete_blocked(self):
        """BLOCKED → 未完成。"""
        assert is_task_complete(skipped=False, review_verdict="BLOCKED") is False

    # ── 端到端状态转换序列 ──

    def test_normal_flow(self):
        """正常流程: 实现 DONE → 审查 APPROVED → 完成。"""
        impl_status = "DONE"
        agent_null = False

        # Stage 2: 审查
        skip_r = should_skip_review(impl_status, agent_null)
        assert skip_r is False  # 进入审查

        review_verdict = "APPROVED"

        # Stage 3: 修复
        skip_f = should_skip_fix(skip_r, review_verdict)
        assert skip_f is True  # APPROVED 跳过修复

        complete = is_task_complete(skip_r, review_verdict)
        assert complete is True

    def test_needs_fix_flow(self):
        """修复流程: 实现 DONE → 审查 NEEDS_FIX → 修复 → 重审 APPROVED → 完成。"""
        impl_status = "DONE"
        agent_null = False

        skip_r = should_skip_review(impl_status, agent_null)
        assert skip_r is False

        # 审查返回 NEEDS_FIX
        skip_f = should_skip_fix(skip_r, "NEEDS_FIX")
        assert skip_f is False  # 进入修复

        # 修复后重审 APPROVED
        complete = is_task_complete(skip_r, "APPROVED")
        assert complete is True

    def test_blocked_flow(self):
        """阻塞流程: 实现 BLOCKED → 跳过审查 → 跳过修复 → 未完成。"""
        impl_status = "BLOCKED"
        agent_null = False

        skip_r = should_skip_review(impl_status, agent_null)
        assert skip_r is True

        skip_f = should_skip_fix(skip_r, None)
        assert skip_f is True

        complete = is_task_complete(skip_r, None)
        assert complete is False

    def test_agent_null_flow(self):
        """空代理流程: 实现返回 null → 跳过审查 → 跳过修复 → 未完成。"""
        skip_r = should_skip_review(None, agent_null=True)
        assert skip_r is True

        skip_f = should_skip_fix(skip_r, None)
        assert skip_f is True

        complete = is_task_complete(skip_r, None)
        assert complete is False


# ═══════════════════════════════════════════════════════════════════
# 测试：进度账本断点恢复（workflow.js L410-437）——COV-002
# ═══════════════════════════════════════════════════════════════════

class TestLedgerCheckpointRecovery:
    """进度账本断点恢复——completedTaskIds Set 构建 + pendingTasks 过滤。"""

    def test_build_completed_set_basic(self):
        """从已完成任务 ID 列表构建 Set。"""
        result = build_completed_set(["1", "2", "3"])
        assert result == {"1", "2", "3"}

    def test_build_completed_set_string_normalization(self):
        """数字 ID 归一化为字符串。"""
        result = build_completed_set([1, 2, 3])
        assert result == {"1", "2", "3"}

    def test_build_completed_set_mixed_types(self):
        """混合类型 ID 均归一化。"""
        result = build_completed_set([1, "2", 3])
        assert result == {"1", "2", "3"}

    def test_build_completed_set_empty(self):
        """空列表返回空 Set。"""
        result = build_completed_set([])
        assert result == set()

    def test_filter_pending_tasks_all_pending(self):
        """无已完成任务——全部保留。"""
        tasks = [
            {"id": 1, "description": "Task 1"},
            {"id": 2, "description": "Task 2"},
            {"id": 3, "description": "Task 3"},
        ]
        completed = set()
        result = filter_pending_tasks(tasks, completed)
        assert len(result) == 3
        assert [t["id"] for t in result] == [1, 2, 3]

    def test_filter_pending_tasks_some_completed(self):
        """部分已完成——仅保留待执行任务。"""
        tasks = [
            {"id": 1, "description": "Task 1"},
            {"id": 2, "description": "Task 2"},
            {"id": 3, "description": "Task 3"},
            {"id": 4, "description": "Task 4"},
        ]
        completed = {"1", "3"}
        result = filter_pending_tasks(tasks, completed)
        assert len(result) == 2
        assert [t["id"] for t in result] == [2, 4]

    def test_filter_pending_tasks_all_completed(self):
        """全部已完成——返回空列表。"""
        tasks = [
            {"id": 1, "description": "Task 1"},
            {"id": 2, "description": "Task 2"},
        ]
        completed = {"1", "2"}
        result = filter_pending_tasks(tasks, completed)
        assert result == []

    def test_filter_pending_tasks_string_int_match(self):
        """字符串 ID 与数字 ID 的正则化匹配。"""
        tasks = [
            {"id": 1, "description": "Task A"},
            {"id": "2", "description": "Task B"},
        ]
        completed = {"1", "2"}
        result = filter_pending_tasks(tasks, completed)
        assert result == []

    def test_filter_pending_missing_id(self):
        """缺少 id 字段的任务不被过滤。"""
        tasks = [
            {"description": "No ID task"},
            {"id": 1, "description": "Task 1"},
        ]
        completed = {"1"}
        result = filter_pending_tasks(tasks, completed)
        # 缺少 id 的任务不会被匹配（空字符串 != "1"），因此保留
        assert len(result) == 1
        assert "description" in result[0] and "id" not in result[0]

    def test_end_to_end_recovery(self):
        """端到端: ledger 读取 → Set 构建 → pending 过滤。"""
        tasks = [
            {"id": 1, "description": "Setup"},
            {"id": 2, "description": "Core"},
            {"id": 3, "description": "Tests"},
            {"id": 4, "description": "Docs"},
            {"id": 5, "description": "Cleanup"},
        ]
        # ledger 报告已完成 Task 1, 2, 4
        ledger_completed = ["1", "2", "4"]

        completed_set = build_completed_set(ledger_completed)
        assert completed_set == {"1", "2", "4"}

        pending = filter_pending_tasks(tasks, completed_set)
        assert len(pending) == 2
        assert [t["id"] for t in pending] == [3, 5]


# ═══════════════════════════════════════════════════════════════════
# 测试：未解决清单格式化（workflow.js L687-694）——COV-003
# ═══════════════════════════════════════════════════════════════════

class TestUnresolvedFormatting:
    """熔断后未解决清单格式化——对应 workflow.js L690 模板字符串。"""

    def test_format_single_item_with_line(self):
        """完整字段（含行号）的格式化。"""
        finding = {
            "id": "COV-001",
            "severity": "important",
            "description": "缺少流水线状态转换测试",
            "file": "tests/harness/test_plan_execute_workflow.py",
            "line": 450,
        }
        result = format_unresolved_item(finding)
        expected = "- [important] COV-001: 缺少流水线状态转换测试 (tests/harness/test_plan_execute_workflow.py:450)"
        assert result == expected

    def test_format_item_without_line(self):
        """无行号时不追加 :line。"""
        finding = {
            "id": "EXTRA-001",
            "severity": "critical",
            "description": "计划外全量重写 CLAUDE.md",
            "file": "CLAUDE.md",
        }
        result = format_unresolved_item(finding)
        expected = "- [critical] EXTRA-001: 计划外全量重写 CLAUDE.md (CLAUDE.md)"
        assert result == expected

    def test_format_item_missing_file(self):
        """文件缺失时使用「未知文件」。"""
        finding = {
            "id": "COMP-001",
            "severity": "minor",
            "description": "兼容性待确认",
        }
        result = format_unresolved_item(finding)
        expected = "- [minor] COMP-001: 兼容性待确认 (未知文件)"
        assert result == expected

    def test_format_item_empty_file(self):
        """空字符串文件视为缺失。"""
        finding = {
            "id": "IFACE-001",
            "severity": "minor",
            "description": "接口偏差",
            "file": "",
        }
        result = format_unresolved_item(finding)
        expected = "- [minor] IFACE-001: 接口偏差 (未知文件)"
        assert result == expected

    def test_format_item_default_severity(self):
        """无 severity 时默认 minor。"""
        finding = {
            "id": "TEST-001",
            "description": "测试发现",
            "file": "test.py",
        }
        result = format_unresolved_item(finding)
        assert result.startswith("- [minor]")

    def test_format_full_section(self):
        """完整章节格式化——含标题、列表和脚注。"""
        findings = [
            {
                "id": "COV-001",
                "severity": "important",
                "description": "缺少状态转换测试",
                "file": "tests/test_x.py",
                "line": 100,
            },
            {
                "id": "EXTRA-001",
                "severity": "critical",
                "description": "计划外文件变更",
                "file": "CLAUDE.md",
            },
        ]
        result = format_unresolved_section(findings, max_rounds=5)
        assert result.startswith("## ⚠ Fidelity 审计未解决项\n\n")
        assert "- [important] COV-001:" in result
        assert "- [critical] EXTRA-001:" in result
        assert "审计循环 5 轮后熔断" in result
        assert "2 个发现未解决" in result
        assert "请人工裁决" in result

    def test_format_empty_section(self):
        """空发现列表的格式化。"""
        result = format_unresolved_section([], max_rounds=3)
        assert "## ⚠ Fidelity 审计未解决项" in result
        assert "0 个发现未解决" in result
        assert "审计循环 3 轮后熔断" in result

    def test_format_missing_id(self):
        """缺失 ID 时使用 ??? 占位符。"""
        finding = {
            "severity": "important",
            "description": "无 ID 的发现",
            "file": "test.py",
        }
        result = format_unresolved_item(finding)
        assert "???:" in result
