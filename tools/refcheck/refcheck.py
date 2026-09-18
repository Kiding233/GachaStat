#!/usr/bin/env python3
"""refcheck 阶段一：解析与指纹内核（纯读，零写入）。

只做一件事：把仓库里现存的引用找出来，解析它们指向什么，算出提议范围的指纹，
产出一份「迁移就绪报告」。

不做的事：

* 不写任何文件。
* 不判定漂移。漂移需要「记忆」才能存在，而记忆由迁移写入；阶段一还没有记忆可比。

设计上刻意不含本项目的任何专有知识（不认 03-归档、不认 gacha_simulator），
扫描范围由 --include / --exclude 给出，以便同一份代码能直接搬到别的仓库。

用法：
    python tools/refcheck/refcheck.py scan --root .
    python tools/refcheck/refcheck.py scan --exclude 'docs/03-归档/**' --all
    python tools/refcheck/refcheck.py scan --format json > report.json
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import io
import json
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# 引用形态。三种是历史包袱，迁移的目标格式不含行号，故此处只负责识别与解析。
# ---------------------------------------------------------------------------

# 形式一：文档正文或代码注释里的 `path/to/file.py:123` 或 `:123-456`
RE_PLAIN = re.compile(
    r"(?P<path>[A-Za-z0-9_][A-Za-z0-9_./\\-]*\.(?:py|md|toml|yaml|yml|json))"
    r":(?P<start>\d+)(?:\s*-\s*(?P<end>\d+))?"
)

# 形式二：markdown 链接目标里的 `path/to/file.py#L123` 或 `#L123-L456`
RE_LINK = re.compile(r"\]\((?P<target>[^)\s]+)\)")
RE_ANCHOR = re.compile(r"^(?P<path>[^#]+)#L(?P<start>\d+)(?:-L(?P<end>\d+))?$")

# 形式三：无行号的裸文件引用，如 「见 `streaming.py`」。只记录，不解析行。
RE_BARE = re.compile(
    r"`(?P<path>[A-Za-z0-9_][A-Za-z0-9_./\\-]*\.(?:py|md))`"
)

HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$")

CACHE_VERSION = "ast-v1"
SECTION_VERSION = "sec-v1"
LINE_VERSION = "line-v1"


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class Ref:
    """一条被识别出的引用。"""

    src: str            # 出现引用的文件（相对 root）
    line: int           # 1 起
    col: int            # 0 起
    form: str           # plain / link / bare
    context: str        # prose / md-link / comment / string
    raw: str            # 命中的原文
    target_raw: str = ""
    target: str | None = None       # 解析到的受控文件，未解析为 None
    status: str = "unparsed"        # ok / file_not_found / ambiguous / module_level
    line_in_file: bool | None = None
    symbol: str | None = None       # 目标的最近外层符号，模块级为 None
    symbol_span: tuple[int, int] | None = None
    symbol_fp: str | None = None
    section: str | None = None      # 源文件为 markdown 时，所属标题
    section_span: tuple[int, int] | None = None
    section_fp: str | None = None

    def to_dict(self) -> dict:
        d = {
            "src": self.src,
            "line": self.line,
            "col": self.col,
            "form": self.form,
            "context": self.context,
            "raw": self.raw,
            "target_raw": self.target_raw,
            "target": self.target,
            "status": self.status,
            "symbol": self.symbol,
            "symbol_span": list(self.symbol_span) if self.symbol_span else None,
            "symbol_fp": self.symbol_fp,
            "section": self.section,
            "section_span": list(self.section_span) if self.section_span else None,
            "section_fp": self.section_fp,
        }
        return d


# ---------------------------------------------------------------------------
# 仓库侧：受控文件与解析索引
# ---------------------------------------------------------------------------


def tracked_files(root: Path) -> list[str]:
    """走 git ls-files。目录遍历在本仓库是 5.5 秒 / 460 MB，不可用。

    必须用 -z 而不是按行切：git 默认对含非 ASCII 的路径做八进制转义并整体加引号，
    那样返回的字符串既匹配不上 glob，也打不开文件，症状是这些文件被静默跳过。
    """
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="surrogateescape", check=True,
    ).stdout
    return sorted(p for p in out.split("\0") if p.strip())


def build_index(paths: list[str]) -> dict[str, list[str]]:
    """basename -> 全部同名候选，供消歧用。"""
    index: dict[str, list[str]] = {}
    for p in paths:
        index.setdefault(p.replace("\\", "/").split("/")[-1], []).append(p)
    return index


def resolve_target(raw: str, index: dict[str, list[str]]) -> tuple[str | None, str]:
    """把引用里写的路径解析成受控文件。返回 (路径, 状态)。"""
    clean = raw.replace("\\", "/").lstrip("./")
    if clean in index.get(clean.split("/")[-1], []):
        return clean, "ok"
    base = clean.split("/")[-1]
    cands = [p for p in index.get(base, []) if p.replace("\\", "/").endswith(clean)]
    if len(cands) == 1:
        return cands[0], "ok"
    if not cands and len(index.get(base, [])) == 1:
        return index[base][0], "ok"
    return None, "ambiguous" if cands else "file_not_found"


# ---------------------------------------------------------------------------
# 代码侧：符号定位与指纹
# ---------------------------------------------------------------------------


def parse_py(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError, ValueError):
        return None


def symbol_at(tree: ast.AST, line: int):
    """包含该行的最内层函数或类。返回 (限定名, (起, 止), 指纹)。"""
    best: tuple[int, str, tuple[int, int], ast.AST] | None = None
    stack: list[tuple[ast.AST, str]] = [(tree, "")]
    while stack:
        node, prefix = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = prefix + child.name
                lo, hi = child.lineno, child.end_lineno or child.lineno
                if lo <= line <= hi and (best is None or (hi - lo) < best[0]):
                    best = (hi - lo, name, (lo, hi), child)
                stack.append((child, name + "."))
            else:
                stack.append((child, prefix))
    if best is None:
        return None
    return best[1], best[2], fingerprint_node(best[3])


def fingerprint_node(node: ast.AST) -> str:
    """归一化哈希。注释不在 AST 内，故不受格式变动影响；docstring 在，故其变更计入。"""
    return tag(CACHE_VERSION, ast.dump(node, annotate_fields=False,
                                       include_attributes=False))


def tag(version: str, payload: str) -> str:
    digest = hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()
    return f"{version}:{digest[:16]}"


# ---------------------------------------------------------------------------
# 文档侧：所属标题与指纹
# ---------------------------------------------------------------------------


def sections_of(lines: list[str]) -> list[tuple[int, int, int, str]]:
    """返回 [(起行, 止行, 层级, 标题)]，1 起，止行含。"""
    heads = []
    for i, text in enumerate(lines, 1):
        m = HEADING.match(text)
        if m:
            heads.append((i, len(m.group("hashes")), m.group("title")))
    out = []
    for idx, (start, level, title) in enumerate(heads):
        end = len(lines)
        for nxt, nlevel, _ in heads[idx + 1:]:
            if nlevel <= level:
                end = nxt - 1
                break
        out.append((start, end, level, title))
    return out


def section_at(sections: list[tuple[int, int, int, str]], line: int):
    best = None
    for start, end, level, title in sections:
        if start <= line <= end and (best is None or start > best[0]):
            best = (start, end, level, title)
    return best


def fingerprint_lines(lines: list[str], span: tuple[int, int],
                      version: str = SECTION_VERSION) -> str:
    """行范围指纹：空白归一化。行号不进哈希，故位移不触发。"""
    chunk = " ".join(" ".join(lines[span[0] - 1:span[1]]).split())
    return tag(version, chunk)


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------


def py_signal_lines(text: str) -> tuple[set[int], set[int]]:
    """返回 (注释所在行, 字符串所在行)。语法错误时两者皆空。"""
    comments: set[int] = set()
    strings: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                comments.add(tok.start[0])
            elif tok.type == tokenize.STRING:
                for row in range(tok.start[0], tok.end[0] + 1):
                    strings.add(row)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass
    return comments, strings


DEFAULT_EXCLUDES = [
    "**/.venv/**", "**/venv/**", "**/node_modules/**", "**/vendor/**",
    "**/build/**", "**/dist/**", "**/__pycache__/**",
]


def scan_file(root: Path, rel: str, index: dict[str, list[str]],
              include_bare: bool = False) -> list[Ref]:
    path = root / rel
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = text.splitlines()
    is_md = rel.endswith(".md")
    refs: list[Ref] = []

    if is_md:
        link_spans = [(m.start(), m.end()) for m in RE_LINK.finditer(text)]
    else:
        comments, strings = py_signal_lines(text)
        link_spans = []

    def offset_to_pos(off: int) -> tuple[int, int]:
        line = text.count("\n", 0, off) + 1
        col = off - (text.rfind("\n", 0, off) + 1)
        return line, col

    def context_of(pos: tuple[int, int], inside_link: bool, off: int) -> str:
        if inside_link:
            return "md-link"
        if is_md:
            return "prose"
        row = pos[0]
        if row in comments:
            return "comment"
        if row in strings:
            return "string"
        return "code"

    seen: set[tuple[int, int]] = set()

    def add(pos, form, context, raw, target_raw, start=None, end=None):
        key = (pos[0], pos[1])
        if key in seen:
            return
        seen.add(key)
        r = Ref(src=rel, line=pos[0], col=pos[1], form=form, context=context,
                raw=raw, target_raw=target_raw)
        finish(r, root, index, lines, is_md, start, end)
        refs.append(r)

    for m in RE_PLAIN.finditer(text):
        pos = offset_to_pos(m.start())
        inside = any(s <= m.start() < e for s, e in link_spans)
        add(pos, "plain", context_of(pos, inside, m.start()), m.group(0),
            m.group("path"), m.group("start"), m.group("end"))

    for m in RE_LINK.finditer(text):
        inner = RE_ANCHOR.match(m.group("target"))
        if not inner:
            continue
        pos = offset_to_pos(m.start())
        add(pos, "link", "md-link", m.group(0), inner.group("path"),
            inner.group("start"), inner.group("end"))

    if include_bare:
        for m in RE_BARE.finditer(text):
            pos = offset_to_pos(m.start())
            raw = m.group(0)
            if ":" in raw:
                continue
            add(pos, "bare", context_of(pos, False, m.start()), raw, m.group("path"))

    return refs


def finish(ref: Ref, root: Path, index, lines, is_md, start, end) -> None:
    ref.target, ref.status = resolve_target(ref.target_raw, index)

    if ref.form == "bare":
        return
    if ref.target is None:
        return

    total = None
    if ref.target.endswith((".py", ".md")):
        try:
            total = len((root / ref.target).read_text(
                encoding="utf-8", errors="replace").splitlines())
        except OSError:
            total = None
    hi = int(end) if end else int(start)
    ref.line_in_file = bool(total and int(start) <= total and hi <= total)
    if total and not ref.line_in_file:
        ref.status = "line_out_of_range"

    if ref.target.endswith(".py") and ref.line_in_file is not False:
        tree = parse_py(root / ref.target)
        if tree is None:
            ref.status = "unparsable"
            return
        found = symbol_at(tree, int(start))
        if found:
            ref.symbol, ref.symbol_span, ref.symbol_fp = found
        else:
            ref.symbol_span = (int(start), hi)
            ref.symbol_fp = fingerprint_lines(
                (root / ref.target).read_text(encoding="utf-8",
                                              errors="replace").splitlines(),
                ref.symbol_span, LINE_VERSION)
            ref.status = "module_level" if ref.status == "ok" else ref.status

    if is_md and ref.line_in_file is not False:
        sec = section_at(sections_of(lines), ref.line)
        if sec:
            ref.section = sec[3]
            ref.section_span = (sec[0], sec[1])
            ref.section_fp = fingerprint_lines(lines, ref.section_span)


def in_scope(rel: str, includes: list[str], excludes: list[str]) -> bool:
    posix = rel.replace("\\", "/")
    if not any(fnmatch.fnmatch(posix, pat) for pat in includes):
        return False
    return not any(fnmatch.fnmatch(posix, pat) for pat in excludes)


def cmd_scan(args) -> int:
    root = Path(args.root).resolve()
    excludes = DEFAULT_EXCLUDES + list(args.exclude)
    all_tracked = tracked_files(root)
    paths = [p for p in all_tracked if in_scope(p, args.include, excludes)]
    index = build_index(all_tracked)

    refs: list[Ref] = []
    for rel in paths:
        refs.extend(scan_file(root, rel, index, args.include_bare))

    refs.sort(key=lambda r: (r.src, r.line, r.col))

    if args.format == "json":
        print(json.dumps(
            {"root": str(root), "files_scanned": len(paths),
             "refs": [r.to_dict() for r in refs]},
            ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    render_text(refs, paths, args)
    return 0


def render_text(refs: list[Ref], paths: list[str], args) -> None:
    from collections import Counter

    by_status = Counter(r.status for r in refs)
    by_context = Counter(r.context for r in refs)
    by_form = Counter(r.form for r in refs)

    print(f"扫描文件 {len(paths)} 个，命中引用 {len(refs)} 条\n")
    print("按状态：")
    for k, v in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"  {k:18s} {v}")
    print("\n按上下文（区分真引用与数据）：")
    for k, v in sorted(by_context.items(), key=lambda kv: -kv[1]):
        print(f"  {k:18s} {v}")
    print("\n按形态：")
    for k, v in sorted(by_form.items(), key=lambda kv: -kv[1]):
        print(f"  {k:18s} {v}")

    shown = refs if args.all else refs[: args.limit]
    print(f"\n逐条（{'全部' if args.all else f'前 {args.limit} 条'}）：")
    for r in shown:
        tgt = r.target or f"<未解析: {r.target_raw}>"
        sym = r.symbol or ("模块级" if r.symbol_span else "-")
        print(f"  {r.src}:{r.line}  [{r.context}/{r.form}/{r.status}]")
        print(f"      {r.raw[:80]}")
        print(f"      -> {tgt}  {sym}  {r.symbol_fp or ''}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="refcheck", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="扫描引用并产出迁移就绪报告（纯读）")
    s.add_argument("--root", default=".")
    s.add_argument("--include", action="append",
                   default=["*.md", "**/*.md", "*.py", "**/*.py"])
    s.add_argument("--exclude", action="append", default=[])
    s.add_argument("--format", choices=["text", "json"], default="text")
    s.add_argument("--limit", type=int, default=25)
    s.add_argument("--all", action="store_true")
    s.add_argument("--include-bare", action="store_true",
                   help="连无行号的裸文件名引用（如 `streaming.py`）也计入；默认不计，"
                        "因为它会把普通文件名提及也算成引用")
    s.set_defaults(func=cmd_scan)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
