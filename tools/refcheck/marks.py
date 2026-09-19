#!/usr/bin/env python3
"""标记的解析、配对与状态派生：P84 的「对账函数」内核。

设计上叫它**核心原语**：从**磁盘现状**出发，扫标记、算指纹、派生状态。幂等、
无状态、谁都能调；钩子只是闹钟（计划 §3.14）。

这个模块**只读**。它不做渲染、不写盘、不改任何东西。

语法（v2，已冻结）两类记号：

    范围      <|e:<uid>#<段>|> … <|/e:<uid>#<段>|>
    声明      <|<关系标签>：<对方uid>#<段>;h=<指纹>|(<视图>)>

单段可省段标签或写 `*`。多段时每段一个唯一标签。`h` 是**对方**上次核对时的
指纹；多段时为「对方段标签 → 指纹」的映射。

一条关系 = 引用侧一份声明 + 被引侧一份声明，两端各记对方的指纹。**系统里没有
「自己的过去」，只有「对方的过去」**，所以两侧的 `h` 不可能互相冲突。
"""

from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# 标记本体：<|机器区|(渲染区)>。渲染区可省（范围标记就没有）。
MARK_RE = re.compile(r"<\|(?P<body>[^|<>]*)\|(?:\((?P<view>[^<>]*)\))?>")

RANGE_OPEN_RE = re.compile(r"^e:(?P<uid>[^#]+)#(?P<seg>.*)$")
RANGE_CLOSE_RE = re.compile(r"^/e:(?P<uid>[^#]+)#(?P<seg>.*)$")
# 声明：<标签>：<对方uid>#<段>;h=<指纹>。标签里不含 `：` 与 `;`。
DECL_RE = re.compile(
    r"^(?P<label>[^：;]+)：(?P<peer>[^#;]+)#(?P<seg>[^;]*);h=(?P<h>.+)$")

# 关系标签词表（§3.2.4）。两端必须构成已知的一对，否则 `role_conflict`。
REL_PAIRS = [
    ("引用对象", "引用者"),
    ("描述对象", "描述者"),
    ("规格", "实现"),
    ("被测物", "测试"),
    ("出处", "依据"),
]
PAIR_OF = {}
for _a, _b in REL_PAIRS:
    PAIR_OF[_a] = _b
    PAIR_OF[_b] = _a

AST_VERSION = "ast-v1"
TEXT_VERSION = "sec-v1"


@dataclass
class Mark:
    """一个被识别出的标记。"""

    path: str
    line: int
    col: int
    raw: str
    kind: str                    # open / close / decl
    uid: str = ""
    seg: str = ""
    label: str = ""
    peer: str = ""
    peer_seg: str = ""
    h: dict[str, str] = field(default_factory=dict)
    view: str = ""
    detail: str = ""             # 认不出来时的原因
    off_start: int = 0           # 在文件里的绝对偏移。切片与包含判定都用它，
    off_end: int = 0             # 不按行号：同一行里可以并排好几段


@dataclass
class Range:
    """一段被范围标记圈住的内容。"""

    uid: str
    seg: str
    path: str
    open_line: int
    close_line: int | None
    text: str                    # 已剥离全部标记的原文
    fp: str
    inner_start: int = 0         # 内容区间的绝对偏移（开标记之后、闭标记之前）
    inner_end: int = 0

    @property
    def span(self) -> tuple[int, int]:
        return (self.open_line, self.close_line or self.open_line)


@dataclass
class Issue:
    state: str
    where: str
    detail: str

    def as_line(self) -> str:
        return f"[{self.state}] {self.where}  {self.detail}"


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------


def _strip_marks(text: str) -> str:
    """剥离**全部**标记（不只是本段自己的）。

    这是「范围之间互不扰动」的来源：在 X 的范围内插入 Y 的标记，X 的指纹
    不变。顺序固定为先剥标记、再归一化、再哈希（§3.10）；反了会自锁。
    """
    return MARK_RE.sub("", text)


def _norm(text: str) -> str:
    return " ".join(text.split())


def fingerprint(text: str, path: str) -> str:
    """算指纹。代码优先走 AST 归一化，失败则退化为文本归一化。

    退化的情形必须记在指纹的版本标签里：范围只截取了语句的一部分时
    `ast.parse` 必然失败，那时用文本哈希是对的，但要能看出来用的是哪种，
    否则「同一段内容换了算法」会被读成漂移。
    """
    body = _strip_marks(text)
    if path.endswith(".py"):
        try:
            tree = ast.parse(_dedent(body))
        except (SyntaxError, ValueError):
            pass
        else:
            payload = ast.dump(tree, annotate_fields=False,
                               include_attributes=False)
            return _tag(AST_VERSION, payload)
    return _tag(TEXT_VERSION, _norm(body))


def _dedent(text: str) -> str:
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return ""
    pad = min((len(ln) - len(ln.lstrip()) for ln in lines if ln.strip()),
              default=0)
    return "\n".join(ln[pad:] if ln.strip() else "" for ln in lines)


def _tag(version: str, payload: str) -> str:
    return f"{version}:{hashlib.sha256(payload.encode('utf-8', 'replace'))
                          .hexdigest()[:16]}"


def scan_marks(root: Path, paths: list[str]) -> list[Mark]:
    """扫出全部标记。按文件与位置排序，保证可复现。"""
    out: list[Mark] = []
    for rel in paths:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        is_md = rel.endswith(".md")
        fenced = fence_lines(text) if is_md else set()
        skip = example_lines(text) if is_md else set()
        for m in MARK_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            col = m.start() - (text.rfind("\n", 0, m.start()) + 1)
            # 标为示例的行整行不算标记，且这条判定要在 fenced 之前：示例
            # 往往就写在围栏里，那正是它该在的地方。
            if line in skip:
                continue
            if line in fenced:
                out.append(Mark(rel, line, col, m.group(0), "fenced",
                                detail="标记落在代码围栏内（示例，不是真标记）",
                                off_start=m.start(), off_end=m.end()))
                continue
            mk = _classify(rel, line, col, m.group(0),
                           m.group("body") or "", m.group("view") or "")
            mk.off_start, mk.off_end = m.start(), m.end()
            out.append(mk)
        # 近失标记：像标记但没被解析到。**必须报出来**，否则一个打错的闭标记
        # （例如多写一个 `>`）会表现为「这里没有标记」，症状只是范围变成
        # unmatched_start，而真正的原因看不见。样例一实测到此。
        for i in _starts(text, "<|"):
            if MARK_RE.match(text, i):
                continue
            line = text.count("\n", 0, i) + 1
            if line in skip:
                continue
            col = i - (text.rfind("\n", 0, i) + 1)
            out.append(Mark(rel, line, col, text[i:i + 40], "unknown",
                            detail=f"像标记但解析不了：{text[i:i + 40]!r}",
                            off_start=i, off_end=i + 1))
    out.sort(key=lambda k: (k.path, k.line, k.col))
    return out


def _starts(text: str, needle: str) -> list[int]:
    out, i = [], text.find(needle)
    while i != -1:
        out.append(i)
        i = text.find(needle, i + 1)
    return out


FENCE_RE = re.compile(r"^ {0,3}(?P<fence>```+|~~~+)")


def fence_lines(text: str) -> set[int]:
    """markdown 代码围栏覆盖的行号（含围栏行自身）。

    **标记落在围栏内是错误**（§3.10 的危险位置）：围栏里是**示例**，不是真
    标记。没有这一层时，一段展示标记语法的代码块会把里面的 `<|e:A#*|>` 当真
    标记读进来，报出 `dup_segment` / `orphan_decl` 这类假问题。实测本仓库
    14 个标记全部落在计划自己的语法示例代码块里，`check` 报的阻断全是假的。

    注意与**表格**的区别：表格里的标记是正常用法（文档大量用表格列引用），
    只有「往表格里写渲染区」才被拒绝。围栏与表格在 §3.10 里被并列，但行为
    不同，不能一起处理。

    四空格缩进的代码块（非围栏）**不算**：那里面通常是要被引用的代码片段，
    标记落在其中是否为错误，本期不定。
    """
    out: set[int] = set()
    marker: str | None = None
    for i, line in enumerate(text.splitlines(), 1):
        m = FENCE_RE.match(line)
        if marker is None:
            if m:
                marker = m.group("fence")[0] * 3
                out.add(i)
            continue
        out.add(i)
        if m and m.group("fence")[0] == marker[0] and len(m.group("fence")) >= 3:
            marker = None
    return out


EXAMPLE_MARK = "<!-- refcheck:example -->"
EXAMPLE_START = "<!-- refcheck:example:start -->"
EXAMPLE_END = "<!-- refcheck:example:end -->"


def example_lines(text: str) -> set[int]:
    """被明确标注为「这是示例」的行号。

    两种写法：单行 `<!-- refcheck:example -->`，或一段
    `<!-- refcheck:example:start -->` … `<!-- refcheck:example:end -->`。

    区域形式是必需的：展示标记语法的**代码块**里，逐行插单行标记会把示例
    本身弄脏，而它恰恰是最需要排除的一类（实测本仓库 14 个标记全在计划
    自己的语法示例里）。要求完整 HTML 注释形态、且**精确字面量匹配**：
    只认那几个字的话，一段解释这个标记的正文会把自己整段静默跳过。
    """
    out: set[int] = set()
    inside = False
    for i, line in enumerate(text.splitlines(), 1):
        if EXAMPLE_START in line:
            inside = True
        if EXAMPLE_END in line:
            inside = False
            out.add(i)
            continue
        if inside or EXAMPLE_MARK in line:
            out.add(i)
    return out


def _classify(rel: str, line: int, col: int, raw: str, body: str,
              view: str) -> Mark:
    body = body.strip()
    if m := RANGE_OPEN_RE.match(body):
        return Mark(rel, line, col, raw, "open",
                    uid=m.group("uid"), seg=_seg(m.group("seg")), view=view)
    if m := RANGE_CLOSE_RE.match(body):
        return Mark(rel, line, col, raw, "close",
                    uid=m.group("uid"), seg=_seg(m.group("seg")), view=view)
    if m := DECL_RE.match(body):
        return Mark(rel, line, col, raw, "decl", label=m.group("label").strip(),
                    peer=m.group("peer").strip(),
                    peer_seg=_seg(m.group("seg")), h=_parse_h(m.group("h")),
                    view=view)
    return Mark(rel, line, col, raw, "unknown", detail=f"认不出的机器区：{body!r}")


def _seg(text: str) -> str:
    t = (text or "").strip()
    return "*" if t in ("", "*") else t


def _parse_h(text: str) -> dict[str, str]:
    """`h` 的两种写法：单个指纹，或「对方段标签 → 指纹」的映射。"""
    t = text.strip()
    if t.startswith("{") and t.endswith("}"):
        out = {}
        for item in t[1:-1].split(","):
            if ":" in item:
                k, v = item.split(":", 1)
                out[k.strip()] = v.strip()
        return out
    return {"*": t}


# ---------------------------------------------------------------------------
# 配对
# ---------------------------------------------------------------------------


def build_ranges(root: Path, marks: list[Mark]) -> tuple[dict, list[Issue]]:
    """把 open/close 配成范围。返回 ({uid: [Range, ...]}, 结构问题)。"""
    issues: list[Issue] = []
    open_stack: dict[str, list[Mark]] = defaultdict(list)
    ranges: dict[str, list[Range]] = defaultdict(list)
    for mk in marks:
        if mk.kind == "open":
            open_stack[(mk.uid, mk.seg)].append(mk)
        elif mk.kind == "close":
            key = (mk.uid, mk.seg)
            if not open_stack[key]:
                issues.append(Issue("unmatched_end", f"{mk.path}:{mk.line}",
                                    f"闭标记 `<|/e:{mk.uid}#{mk.seg}|>` 没有"
                                    f"对应的开标记"))
                continue
            start = open_stack[key].pop()
            if start.path != mk.path:
                issues.append(Issue(
                    "unmatched_end", f"{mk.path}:{mk.line}",
                    f"开标记在另一个文件（{start.path}:{start.line}）；"
                    f"范围不能跨文件"))
                continue
            ranges[mk.uid].append(_make_range(root, mk.uid, mk.seg, start, mk))
    for (uid, seg), stack in open_stack.items():
        for mk in stack:
            issues.append(Issue("unmatched_start", f"{mk.path}:{mk.line}",
                                f"开标记 `<|e:{uid}#{seg}|>` 没有对应的闭标记"))
    # 同一 uid 同一段标签出现两次
    for uid, group in ranges.items():
        seen = defaultdict(int)
        for r in group:
            seen[r.seg] += 1
        for seg, n in seen.items():
            if n > 1:
                issues.append(Issue(
                    "dup_segment", f"uid={uid}",
                    f"段标签 `{seg}` 在同一范围内出现 {n} 次"))
    for uid, group in ranges.items():
        group.sort(key=lambda r: (r.path, r.open_line))
    return ranges, issues


def _make_range(root: Path, uid: str, seg: str, start: Mark,
                end: Mark) -> Range:
    """按**标记自身的偏移**切片，不按行的首尾。

    同一行里并排两段是常见写法（`<|e:D#one|>…<|/e:D#one|>…<|e:D#two|>…`）。
    按「本行第一个 `>` 到本行最后一个 `<|`」切，会把两段取成同一段、指纹也
    相同，于是「这两段内容不一样」这件事实永远检不出来。样例一实测到此。
    """
    text = (root / start.path).read_text(encoding="utf-8", errors="replace")
    body = text[start.off_end:end.off_start]
    r = Range(uid, seg, start.path, start.line, end.line, body,
              fingerprint(body, start.path))
    r.inner_start, r.inner_end = start.off_end, end.off_start
    return r


# ---------------------------------------------------------------------------
# 状态派生
# ---------------------------------------------------------------------------


def derive(root: Path, paths: list[str]) -> tuple[list[Issue], dict]:
    """跑一遍对账，返回 (问题列表, 统计)。"""
    marks = scan_marks(root, paths)
    ranges, issues = build_ranges(root, marks)

    for mk in marks:
        if mk.kind == "unknown":
            issues.append(Issue("unparsable_mark", f"{mk.path}:{mk.line}",
                                mk.detail))
    # 围栏内的标记：报成一类，且**不参与**配对与状态派生（它们是示例）。
    fenced = [m for m in marks if m.kind == "fenced"]
    if fenced:
        files = sorted({m.path for m in fenced})
        issues.append(Issue(
            "mark_in_fence", f"{files[0]}" + (f" 等 {len(files)} 个文件"
                                              if len(files) > 1 else ""),
            f"{len(fenced)} 个标记落在代码围栏内（示例不是真标记）。"
            f"§3.10 把围栏内定为危险位置，故这是错误；"
            f"要让示例不被扫到，改用 `<!-- refcheck:example -->` 标注那一行"))
    marks = [m for m in marks if m.kind != "fenced"]

    by_uid: dict[str, list[Range]] = ranges
    # uid 出现在多处（多段）是正常的；同一 uid 的同一段出现在两个文件才是歧义
    for uid, group in by_uid.items():
        files = {r.path for r in group}
        if len(files) > 1 and len(group) > 1:
            issues.append(Issue("ambiguous", f"uid={uid}",
                                f"同一 uid 的范围跨 {len(files)} 个文件："
                                f"{sorted(files)}（多段应共处一文件）"))

    decls = [m for m in marks if m.kind == "decl"]
    # 每条声明的「本方范围」= 在文本上包含它的那个范围
    owner: dict[int, Range | None] = {}
    for mk in decls:
        owner[id(mk)] = _enclosing(ranges, mk)

    declared: dict[tuple[str, str], list[Mark]] = defaultdict(list)
    for mk in decls:
        own = owner[id(mk)]
        if own is None:
            issues.append(Issue(
                "orphan_decl", f"{mk.path}:{mk.line}",
                "声明不在任何范围标记之内，且没有写全两端；"
                "认不出它声明的是哪一段"))
            continue
        declared[(own.uid, own.seg)].append(mk)
        mk.uid = own.uid
        mk.seg = own.seg

    # 每条关系：两端各一份声明，各自记对方的指纹
    seen_rel: dict[tuple, list[Mark]] = defaultdict(list)
    for mk in decls:
        if not mk.uid:
            continue
        key = (mk.uid, mk.seg, mk.label, mk.peer, mk.peer_seg)
        seen_rel[key].append(mk)
    for key, group in seen_rel.items():
        if len(group) > 1:
            issues.append(Issue(
                "dup_decl", f"{group[0].path}:{group[0].line}",
                f"同一范围内有 {len(group)} 条指向同一对方段的声明"))

    rels = []
    for mk in decls:
        if not mk.uid:
            continue
        peer_ranges = by_uid.get(mk.peer)
        if not peer_ranges:
            issues.append(Issue(
                "broken", f"{mk.path}:{mk.line}",
                f"对方 uid `{mk.peer}` 在全库扫不到"))
            continue
        # 关系种类必须构成已知的一对
        peer_decls = [d for d in decls
                      if d.peer == mk.uid and d.uid == mk.peer]
        peer_labels = {d.label for d in peer_decls}
        if peer_labels and PAIR_OF.get(mk.label) not in peer_labels:
            issues.append(Issue(
                "role_conflict", f"{mk.path}:{mk.line}",
                f"本端标 `{mk.label}`，对端标 {sorted(peer_labels)}；"
                f"两者不构成已知的互逆对"))
        # 存的是「对方」的指纹，故拿对方的当前指纹来比
        peer = _pick(peer_ranges, mk.peer_seg)
        if peer is None:
            issues.append(Issue(
                "broken", f"{mk.path}:{mk.line}",
                f"对方 uid `{mk.peer}` 存在，但没有段 `{mk.peer_seg}`"))
            continue
        want = mk.h.get(mk.peer_seg) or mk.h.get("*")
        if want is None:
            issues.append(Issue(
                "fragment_missing", f"{mk.path}:{mk.line}",
                f"`h` 里没有段 `{mk.peer_seg}`（有的是 {sorted(mk.h)}）"))
            continue
        state = "ok" if want == peer.fp else "drift"
        rels.append((mk, peer, want, state))
        if state == "drift":
            # 漂移报在哪一侧，由**这份声明自己站在哪一端**决定，而站在哪一端
            # 由标签自报（§3.2.4 的互逆对）。引用侧持有被引侧的指纹，故被引侧
            # 变了叫 `tgt_drift`；被引侧持有引用侧的指纹，故引用侧变了叫
            # `src_drift`。按被引文件的扩展名去猜是错的——按语言猜不出角色。
            issues.append(Issue(
                _drift_state(mk.label), f"{mk.path}:{mk.line}",
                f"记的是 `{want}`，对方（{peer.path}:{peer.span[0]}-"
                f"{peer.span[1]}）现在是 `{peer.fp}`"))

    # 有范围但没有**任何**声明 → 没有记忆，什么也检查不了，属错误而非退化。
    # 注意「有声明」有两条路径：声明写在自己里面，或者**对端有一条声明指着
    # 自己的 uid**。只看前者会把「被对端引用的范围」误判成孤立。样例一实测：
    # 代码侧的范围由文档侧的声明指着，它自己没有内嵌声明，却被报了孤立。
    pointed_at = {mk.peer for mk in decls if mk.peer}
    declared_uids = {uid for uid, _ in declared}
    for uid in by_uid:
        if uid in declared_uids or uid in pointed_at:
            continue
        r = by_uid[uid][0]
        issues.append(Issue(
            "orphan_segment", f"{r.path}:{r.span[0]}-{r.span[1]}",
            f"uid `{uid}` 有范围标记，但全库没有任何声明指向它"))

    stats = {
        "files": len(paths),
        "marks": len(marks),
        "ranges": sum(len(v) for v in by_uid.values()),
        "decls": len(decls),
        "relations": len(rels),
        "ok": sum(1 for *_, s in rels if s == "ok"),
        "states": _count(issues),
    }
    return issues, stats


def _drift_state(label: str) -> str:
    """漂移状态名：这份声明站在哪一端，就报哪一种漂移。

    引用侧的声明记的是**被引侧**的指纹，被引侧变了 → `tgt_drift`；
    被引侧的声明记的是**引用侧**的指纹，引用侧变了 → `src_drift`。
    站在哪一端由标签自报，所以这张表就是 `REL_PAIRS` 的用法。
    """
    return "tgt_drift" if PAIR_OF.get(label) in _CITED_SIDE else "src_drift"


_CITED_SIDE = {"引用者", "描述者", "实现", "测试", "依据"}


def _pick(group: list[Range], seg: str) -> Range | None:
    for r in group:
        if r.seg == seg:
            return r
    return group[0] if len(group) == 1 else None


def _enclosing(ranges: dict, mk: Mark) -> Range | None:
    """声明落在哪个范围**之内**。按偏移判包含，不按行号。

    同一行里可以既有范围又有声明（`<|e:D#*|>正文<|/e:D#*|> <|引用…|(…)>`），
    或者一段声明紧跟在范围同一行的后面。按行号判会以为「声明落在范围那一行
    上」而错配——那是把「同一行」当成了「包含」。
    """
    best = None
    for group in ranges.values():
        for r in group:
            if r.path != mk.path:
                continue
            if r.inner_start < mk.off_start and mk.off_end <= r.inner_end:
                if best is None or r.inner_start > best.inner_start:
                    best = r
    return best


def _count(issues: list[Issue]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for i in issues:
        out[i.state] += 1
    return dict(out)


# 阻断提交的状态。**不区分新增与存量**：阶段二已改为「语义重锚」，每条关系
# 写下时都确认过对面存在，因此错误态不会成批产生，不需要留报告通道。
# 原先阶段四写的「新增 broken 阻断提交，存量出报告」是「机械迁移」时代的
# 残留，那个前提已经作废。
BLOCKING = {
    "broken", "ambiguous", "orphan_segment", "orphan_decl", "unmatched_start",
    "unmatched_end", "dup_segment", "dup_decl", "role_conflict",
    "decl_lost", "unparsable_mark", "fragment_missing", "drift",
    "tgt_drift", "src_drift", "mark_in_fence",
}
