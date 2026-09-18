#!/usr/bin/env python3
"""refcheck 阶段一：解析与指纹内核（纯读，零写入）。

只做两件事：

1. 把仓库里现存的引用找出来，解析它们指向什么，算出提议范围的指纹，
   产出「迁移就绪报告」（`scan`）。
2. 按状态分层抽样，产出一份可复现的人工抽查清单（`sample`）。

「解析成功」不等于「指对了」。文件级解析只保证目标文件存在、行号落在文件内，
而文档完全可能把锚点指到同一文件的另一处。故每条引用除 `status` 外另带
`checks`（目标侧疑点），两者都干净才进迁移基线。已知的两类硬错及其判据：

* 锚点落在注释或空行上：注释永不改动，指纹也永不变，这样的错引用会永远
  显示为「未漂移」，比报错更糟。
* 文中点名的符号不覆盖目标行（如点名 `foo()` 而锚点落在同文件的别处）。

不做的事：

* 不写任何文件。
* 不判定漂移。漂移需要「记忆」才能存在，而记忆由迁移写入；阶段一还没有记忆可比。

设计上刻意不含任何单个项目的专有知识（不认 03-归档、不认 gacha_simulator），
扫描范围、歧义裁决与例外全部来自可选的 `refcheck.toml`，以便同一份代码直接搬到别的仓库。

用法：
    python tools/refcheck/refcheck.py scan --root . --all
    python tools/refcheck/refcheck.py scan --format json > report.json
    python tools/refcheck/refcheck.py sample --n 20 --seed 20260918
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import io
import json
import random
import re
import subprocess
import sys
import tokenize
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# 引用形态。三种都是历史包袱：迁移的目标格式不含行号，此处只负责识别与解析。
# ---------------------------------------------------------------------------

RE_PLAIN = re.compile(
    r"(?P<path>[A-Za-z0-9_][A-Za-z0-9_./\\-]*\.(?:py|md|toml|yaml|yml|json))"
    r":(?P<start>\d+)(?:\s*-\s*(?P<end>\d+))?"
)
RE_LINK = re.compile(r"\]\((?P<target>[^)\s]+)\)")
RE_ANCHOR = re.compile(r"^(?P<path>[^#]+)#L(?P<start>\d+)(?:-L(?P<end>\d+))?$")
RE_BARE = re.compile(r"`(?P<path>[A-Za-z0-9_][A-Za-z0-9_./\\-]*\.(?:py|md))`")
HEADING = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*$")

AST_VERSION = "ast-v1"
SECTION_VERSION = "sec-v1"
LINE_VERSION = "line-v1"

# 产出物里的标记。见 is_self_output()。
SELF_MARKER = "refcheck:generated"

DEFAULT_INCLUDE = ["*.md", "**/*.md", "*.py", "**/*.py"]
DEFAULT_EXCLUDES = [
    "**/.venv/**", "**/venv/**", "**/node_modules/**", "**/vendor/**",
    "**/build/**", "**/dist/**", "**/__pycache__/**",
]

CONFIG_NAME = "refcheck.toml"


# ---------------------------------------------------------------------------
# 配置：每仓库唯一需要手工补的东西是歧义裁决
# ---------------------------------------------------------------------------


@dataclass
class Config:
    include: list[str]
    exclude: list[str]
    alias: dict[str, str]                       # 歧义 basename -> 真实路径（全局兜底）
    scoped: dict[str, dict[str, str]]           # 源文件 -> 该文件内的裁决
    external: list[str]                         # 显式声明为仓库外的路径前缀

    @staticmethod
    def defaults() -> Config:
        return Config(list(DEFAULT_INCLUDE), list(DEFAULT_EXCLUDES), {}, {}, [])


def config_candidates(root: Path) -> list[Path]:
    """配置的查找顺序：先仓库根，再工具目录。

    两个位置都给是因为不同仓库对根目录的写入限制不同：本仓库的提交门控只允许
    少数几个根级文件，故配置放在工具目录下；换一个不限制的仓库，放根目录更显眼。
    """
    return [root / CONFIG_NAME, Path(__file__).resolve().parent / CONFIG_NAME]


def load_config(root: Path, explicit: str | None) -> tuple[Config, str, Path | None]:
    """读配置，缺省则用默认。返回 (配置, 提示信息, 实际使用的配置文件)。

    第三个返回值要显示出来：配置随工具目录一起复制，换仓库时会被带走，
    而带错了配置的后果是排除范围与歧义裁决都错，且症状不明显。
    """
    cfg = Config.defaults()
    if explicit:
        path = Path(explicit)
        if not path.exists():
            return cfg, f"指定的配置 {explicit} 不存在", None
    else:
        found = [p for p in config_candidates(root) if p.exists()]
        if not found:
            return cfg, None, None
        path = found[0]
    try:
        import tomllib
    except ImportError:  # Python 3.10
        return cfg, f"{path.name} 存在但本 Python 无 tomllib，配置未生效", path
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return cfg, f"{path.name} 解析失败（{exc}），配置未生效", path

    scope = data.get("scope", {})
    cfg.include = scope.get("include", cfg.include)
    cfg.exclude = DEFAULT_EXCLUDES + list(scope.get("exclude", []))
    resolve = data.get("resolve", {})
    cfg.alias = dict(resolve.get("alias", {}))
    cfg.external = list(resolve.get("external", []))
    for item in resolve.get("scoped", []):
        src = item.get("src")
        if src:
            cfg.scoped.setdefault(src.replace("\\", "/"), {}).update(
                {k: v for k, v in item.items() if k != "src"})
    return cfg, None, path


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class Ref:
    """一条被识别出的引用。"""

    src: str
    line: int
    col: int
    form: str            # plain / link / bare
    context: str         # prose / md-link / comment / string / code
    raw: str
    target_raw: str = ""
    target: str | None = None
    status: str = "unparsed"
    detail: str = ""     # 状态的原因（别名命中、标准库、多候选等）
    line_in_file: bool | None = None
    ref_span: tuple[int, int] | None = None   # 引用自己写的行号范围
    symbol: str | None = None
    symbol_span: tuple[int, int] | None = None
    symbol_fp: str | None = None
    section: str | None = None
    section_span: tuple[int, int] | None = None
    section_fp: str | None = None
    index: int = -1      # 排序后的序号，供 dup_of 指向
    dup_of: int | None = None   # 同一行内与另一条引用指向同一处（链接文字与链接目标两半）
    checks: list[str] = field(default_factory=list)   # 目标侧疑点
    suggest: str | None = None  # 疑点成立时，文中点名符号的实际位置
    names: list[str] = field(default_factory=list)    # 文中点名且在目标文件里有定义的符号

    @property
    def in_baseline(self) -> bool:
        """能否进迁移基线：解析干净且无目标侧疑点。"""
        return self.status in ("ok", "module_level") and not self.checks

    def to_dict(self) -> dict:
        return {
            "src": self.src, "line": self.line, "col": self.col,
            "form": self.form, "context": self.context, "raw": self.raw,
            "target_raw": self.target_raw, "target": self.target,
            "status": self.status, "detail": self.detail,
            "ref_span": list(self.ref_span) if self.ref_span else None,
            "symbol": self.symbol,
            "symbol_span": list(self.symbol_span) if self.symbol_span else None,
            "symbol_fp": self.symbol_fp,
            "section": self.section,
            "section_span": list(self.section_span) if self.section_span else None,
            "section_fp": self.section_fp,
            "duplicate_of": self.dup_of,
            "checks": list(self.checks),
            "suggest": self.suggest,
            "names": list(self.names),
            "in_baseline": self.in_baseline,
        }


# ---------------------------------------------------------------------------
# 仓库侧
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


def ignored_files(root: Path) -> list[str]:
    """被 .gitignore 排除、但磁盘上存在的文件。

    这一档不可少：项目里真实存在「文档引用被忽略的脚本」这种情况
    （本仓库的 scripts/profile_*.py 即是），把它们算成「文件不存在」会给出
    错误的处置建议（去修引用），而正确处置是「纳管、声明为外部、或停止引用」。
    """
    out = subprocess.run(
        ["git", "ls-files", "-o", "-i", "--exclude-standard", "-z"],
        cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="surrogateescape",
    ).stdout
    return sorted(p for p in out.split("\0") if p.strip())


def build_index(paths: list[str]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for p in paths:
        index.setdefault(p.replace("\\", "/").split("/")[-1], []).append(p)
    return index


def stdlib_names() -> frozenset[str]:
    return frozenset(getattr(sys, "stdlib_module_names", frozenset()))


def looks_external(raw: str, cfg: Config, stdlib: frozenset[str]) -> str:
    """判断是否本就指向仓库外的东西。返回原因，否则空串。"""
    posix = raw.replace("\\", "/").lstrip("./")
    if any(posix.startswith(prefix) for prefix in cfg.external):
        return "配置声明为外部"
    parts = posix.split("/")
    for seg in parts[:-1]:
        if seg in stdlib:
            return f"标准库 {seg}"
    if len(parts) == 1 and parts[0][:-3] in stdlib:
        return f"标准库 {parts[0][:-3]}"
    return ""


def line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return -1


def classify_target(raw: str, root: Path, idx_in: dict, idx_all: dict,
                    idx_ign: dict, cfg: Config, src: str,
                    want: tuple[int, int] | None):
    """按一条阶梯给引用定性，每一档对应一种不同的处置。

    分档的意义在于「处置方式不同」：ok 无需动作；out_of_scope 是范围配置问题；
    untracked 是「文件不在版本库里」（纳管、声明为外部、或停止引用）；
    file_not_found 才是真的引用失效。
    """
    clean = raw.replace("\\", "/").lstrip("./")
    base = clean.split("/")[-1]
    qualified = "/" in clean

    # 别名与按源文件裁决只对「只写 basename」的引用生效。限定路径自带消歧信息，
    # 拿它去套别名，会把「文件本来就在别处」的错引用悄悄改写成另一个文件里的
    # 正确路径，歧义就从可见变成不可见。
    if not qualified:
        scoped = cfg.scoped.get(src, {})
        if base in scoped:
            return scoped[base], "ok", "按源文件裁决"
        if base in cfg.alias:
            return cfg.alias[base], "ok", "按全局别名裁决"

    tiers = ((idx_in, "ok"), (idx_all, "out_of_scope"), (idx_ign, "untracked"))
    for idx, verdict in tiers:
        cands = idx.get(base, [])
        if not cands:
            continue
        if clean in cands:
            return clean, verdict, ""
        if qualified:
            # 限定路径只认「候选以写法结尾」（覆盖写成仓库根目录前缀的情形）。
            # 不认「同名文件只有一个就假定是它」：那是在猜，而且猜错了看不出来。
            heads = [p for p in cands if p.replace("\\", "/").endswith(clean)]
            if len(heads) == 1:
                return heads[0], verdict, ""
            if len(heads) > 1:
                return None, "ambiguous", describe_candidates(heads, root, want)
            continue
        if len(cands) == 1:
            return cands[0], verdict, ""
        return None, "ambiguous", describe_candidates(cands, root, want)

    disk = root / clean
    if disk.exists():
        return None, "untracked", "磁盘有、版本库无（疑被 .gitignore 排除）"
    return None, "file_not_found", ""


def describe_candidates(cands: list[str], root: Path,
                        want: tuple[int, int] | None) -> str:
    """列出候选并标出「行号范围能否容纳」，这是人做裁决时最需要的一条判据。

    空文件与行数不足的候选会被标出来，因为这两类是歧义噪声的主要来源。
    """
    parts = []
    for c in sorted(cands):
        n = line_count(root / c)
        mark = ""
        if n == 0:
            mark = "空文件"
        elif want and n < want[1]:
            mark = f"容不下 {want[0]}-{want[1]}"
        parts.append(f"{c}({n} 行{('，' + mark) if mark else ''})")
    return f"{len(cands)} 个候选：" + " / ".join(parts)


# ---------------------------------------------------------------------------
# 代码侧
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
    """归一化哈希。注释不在 AST 内，故格式变动不影响；docstring 在，故其变更计入。"""
    return tag(AST_VERSION, ast.dump(node, annotate_fields=False,
                                     include_attributes=False))


def defined_symbols(tree: ast.AST) -> dict[str, list[tuple[int, int]]]:
    """目标文件里定义过的名字 → 行范围。函数、类、模块级简单赋值。

    只在目标文件内部查找，不入 import 的名字：文档点名的若是外部符号，
    这里查不到，也就不产生疑点，宁可漏报不误报。
    """
    out: dict[str, list[tuple[int, int]]] = {}
    for node in tree.body:
        lo = getattr(node, "lineno", None)
        hi = getattr(node, "end_lineno", None) or lo
        if lo is None:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.setdefault(node.name, []).append((lo, hi))
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    out.setdefault(tgt.id, []).append((lo, hi))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.setdefault(node.target.id, []).append((lo, hi))
    return out


NAME_RE = re.compile(r"(?<![A-Za-z0-9_])_?[A-Za-z][A-Za-z0-9_]{2,}(?![A-Za-z0-9_])")
COMMENT_ONLY = re.compile(r"^\s*#")


def named_tokens(text: str, skip: tuple[int, int] | None) -> list[str]:
    """从一行里挑出「像符号名」的记号。

    过滤靠两条：带下划线，或非首位有大写（普通散文词两样都不占）；以及
    后面还要在目标文件里查得到定义。两道都过才可能产生疑点。
    """
    out = []
    for m in NAME_RE.finditer(text):
        if skip and skip[0] <= m.start() < skip[1]:
            continue
        tok = m.group(0)
        if "_" in tok or any(c.isupper() for c in tok[1:]):
            out.append(tok)
    return out


def py_target_checks(lines: list[str], line_no: int,
                     defs: dict[str, list[tuple[int, int]]],
                     names: list[str], enclosing: str | None,
                     strings: set[int], single_line: bool):
    """目标侧校验：锚点落的地方是不是文中说的那一处。

    两类判据：

    * 文中点名的符号不覆盖目标行。符号搬家后行号没跟着改，是典型形态。
      实测精度很高（手查 18 条中 17 条是真错位，唯一误报是邻句符号被算作
      本条的名字，已由分句收窄处理）。
    * 模块级锚点落在注释或空行上。只对模块级成立：符号内部的锚点，指纹是
      整个符号，代码动了指纹就动；而模块级的指纹就是被锚的那一行本身，
      锚在永不改动的行上等于没有记忆，错引用会一直显示为「未漂移」。

    注释本身不是疑点。本项目里注释承载论证，被文档有意引用是常态，实测
    「锚点是注释」单独出现时 17 条里只有 3 条是真错，故不单独报。范围锚点也
    不报，只有单行锚点才要求那一行本身站得住。

    返回 (疑点列表, 建议锚点)。
    """
    checks: list[str] = []
    suggest: str | None = None
    if 1 <= line_no <= len(lines) and line_no not in strings and single_line:
        text = lines[line_no - 1]
        if enclosing is None and not text.strip():
            checks.append("模块级单行锚点落在空行上（指纹永不变化）")
        elif enclosing is None and COMMENT_ONLY.match(text):
            checks.append("模块级单行锚点落在注释上（指纹永不变化）")
    for nm in sorted(set(names)):
        spans = defs.get(nm)
        if not spans:
            continue
        if enclosing and (enclosing == nm or enclosing.startswith(nm + ".")
                          or enclosing.endswith("." + nm)):
            continue
        if any(lo <= line_no <= hi for lo, hi in spans):
            continue
        lo, hi = min(spans)
        checks.append(f"文中点名 `{nm}`，它不覆盖目标行（它在 {lo}-{hi}）")
        if suggest is None:
            suggest = f"{lo}-{hi}"
        break
    return checks, suggest


def source_names(text: str, skip: tuple[int, int] | None) -> list[str]:
    """引用所在整行里「像符号名」的记号。取整行而非所在单元格：

    实测的硬错形态是表格行 `| 6 | _gdr_resource_per_card() | gdr.py:427 | ... |`，
    点名的符号与引用分处相邻两格，按格切会把这一条漏掉。取整行必然更吵，
    所以这一路只产出「疑点」供人工确认，不改判定、不自动处置。
    """
    return named_tokens(text, skip)


SENT_BREAK = re.compile(r"[。！？；;\n]")


def clause_of(text: str, col: int) -> tuple[str, int]:
    """取引用所在的那一句，返回 (句子, 句首在本行内的列偏移)。

    同一行里另起一句提到的符号，不该算作这条引用的名字：实测有一句
    「`BootstrapEngine`（`core/bootstrap.py:33`）已实现……`BootstrapResult` 可直接
    使用」，整行取名字会把后半句的 `BootstrapResult` 栽给前半句的引用。
    """
    bounds = [(0, len(text))]
    spans = [(m.start(), m.end()) for m in SENT_BREAK.finditer(text)]
    if spans:
        bounds = []
        prev = 0
        for s, e in spans:
            bounds.append((prev, s))
            prev = e
        bounds.append((prev, len(text)))
    for s, e in bounds:
        if s <= col < e:
            return text[s:e], s
    return text, 0


def tag(version: str, payload: str) -> str:
    digest = hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()
    return f"{version}:{digest[:16]}"


# ---------------------------------------------------------------------------
# 文档侧
# ---------------------------------------------------------------------------


def sections_of(lines: list[str]) -> list[tuple[int, int, int, str]]:
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
    """行范围指纹：空白归一化。行号不进哈希，故位置位移不触发。"""
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
                strings.update(range(tok.start[0], tok.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass
    return comments, strings


def scan_file(root: Path, rel: str, idx_in, idx_all, idx_ign, cfg: Config,
              include_bare: bool = False) -> list[Ref]:
    try:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = text.splitlines()
    is_md = rel.endswith(".md")
    stdlib = stdlib_names()
    refs: list[Ref] = []

    if is_md:
        link_spans = [(m.start(), m.end()) for m in RE_LINK.finditer(text)]
        comments: set[int] = set()
        strings: set[int] = set()
    else:
        comments, strings = py_signal_lines(text)
        link_spans = []

    def offset_to_pos(off: int) -> tuple[int, int]:
        return (text.count("\n", 0, off) + 1,
                off - (text.rfind("\n", 0, off) + 1))

    def context_of(pos, inside_link: bool) -> str:
        if inside_link:
            return "md-link"
        if is_md:
            return "prose"
        if pos[0] in comments:
            return "comment"
        if pos[0] in strings:
            return "string"
        return "code"

    seen: set[tuple[int, int]] = set()

    def add(pos, form, context, raw, target_raw, start=None, end=None):
        if (pos[0], pos[1]) in seen:
            return
        seen.add((pos[0], pos[1]))
        ref = Ref(src=rel, line=pos[0], col=pos[1], form=form, context=context,
                  raw=raw, target_raw=target_raw)
        finish(ref, root, idx_in, idx_all, idx_ign, cfg, lines, is_md, stdlib,
               start, end)
        refs.append(ref)

    for m in RE_PLAIN.finditer(text):
        pos = offset_to_pos(m.start())
        inside = any(s <= m.start() < e for s, e in link_spans)
        add(pos, "plain", context_of(pos, inside), m.group(0),
            m.group("path"), m.group("start"), m.group("end"))

    for m in RE_LINK.finditer(text):
        inner = RE_ANCHOR.match(m.group("target"))
        if inner:
            add(offset_to_pos(m.start()), "link", "md-link", m.group(0),
                inner.group("path"), inner.group("start"), inner.group("end"))

    if include_bare:
        for m in RE_BARE.finditer(text):
            if ":" in m.group(0):
                continue
            pos = offset_to_pos(m.start())
            add(pos, "bare", context_of(pos, False), m.group(0), m.group("path"))

    return refs


def finish(ref: Ref, root: Path, idx_in, idx_all, idx_ign, cfg: Config, lines,
           is_md, stdlib, start, end) -> None:
    reason = looks_external(ref.target_raw, cfg, stdlib)
    if reason:
        ref.status, ref.detail = "external", reason
        return

    want = (int(start), int(end) if end else int(start))
    ref.ref_span = want
    ref.target, ref.status, ref.detail = classify_target(
        ref.target_raw, root, idx_in, idx_all, idx_ign, cfg, ref.src, want)
    if ref.form == "bare" or ref.target is None:
        return

    total = line_count(root / ref.target) if ref.target.endswith((".py", ".md")) else -1
    hi = int(end) if end else int(start)
    if total >= 0:
        ref.line_in_file = int(start) <= total and hi <= total
        if not ref.line_in_file:
            ref.status = "line_out_of_range"
    if ref.line_in_file is False:
        return

    if ref.target.endswith(".py"):
        tree = parse_py(root / ref.target)
        if tree is None:
            ref.status = "unparsable"
            return
        tlines = read_lines(root / ref.target)
        found = symbol_at(tree, int(start))
        if found:
            ref.symbol, ref.symbol_span, ref.symbol_fp = found
        else:
            ref.symbol_span = (int(start), hi)
            ref.symbol_fp = fingerprint_lines(tlines, ref.symbol_span, LINE_VERSION)
            if ref.status == "ok":
                ref.status = "module_level"
        # 文中点名的符号。只看引用所在那一句，并跳过引用自己那段文字，
        # 免得把路径当成符号名、把邻句的符号栽给这条引用。
        src_text = lines[ref.line - 1] if 0 < ref.line <= len(lines) else ""
        clause, base = clause_of(src_text, ref.col)
        names = source_names(clause,
                             (ref.col - base, ref.col - base + len(ref.raw)))
        defs = defined_symbols(tree)
        ref.names = sorted({n for n in names if n in defs})
        _, tstrings = py_signal_lines("\n".join(tlines))
        ref.checks, ref.suggest = py_target_checks(
            tlines, int(start), defs, ref.names, found[0] if found else None,
            tstrings, want[0] == want[1])

    if is_md:
        sec = section_at(sections_of(lines), ref.line)
        if sec:
            ref.section = sec[3]
            ref.section_span = (sec[0], sec[1])
            ref.section_fp = fingerprint_lines(lines, ref.section_span)


def excluded(rel: str, excludes: list[str]) -> bool:
    posix = rel.replace("\\", "/")
    return any(fnmatch.fnmatch(posix, pat) for pat in excludes)


def in_scope(rel: str, includes: list[str], excludes: list[str]) -> bool:
    posix = rel.replace("\\", "/")
    if not any(fnmatch.fnmatch(posix, pat) for pat in includes):
        return False
    return not excluded(rel, excludes)


def is_self_output(path: Path) -> bool:
    """判断这是不是本工具自己产出的清单。

    抽查稿本身就在被抽查的语料里，会把自己写进去的引用算成待迁移的存量，
    于是「为检查而生成的工件」反过来改变了被检查的对象。产出物带标记，
    扫描时按标记认出来并剔除。
    """
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return False
    return SELF_MARKER in head


def run_scan(root: Path, cfg: Config, include_bare: bool,
             include_generated: bool = False):
    """扫描集与解析集是两件事，别混。

    * 扫描集：去哪里**找**引用（include globs 决定，例如只扫 .md 与 .py）
    * 解析集：哪些文件算**合法目标**（全部受控文件减去显式排除）

    早先把解析集也建成扫描集，后果是引用了 `pyproject.toml` 这种非扫描扩展名的
    引用被误判成「范围之外」。
    """
    all_tracked = tracked_files(root)
    ignored = ignored_files(root)
    targets = [p for p in all_tracked if not excluded(p, cfg.exclude)]
    scan_set = [p for p in targets if in_scope(p, cfg.include, [])]

    generated = [p for p in scan_set if is_self_output(root / p)]
    if generated and not include_generated:
        scan_set = [p for p in scan_set if p not in generated]

    idx_in = build_index(targets)
    idx_all = build_index(all_tracked)   # 含被排除者，用来识别「目标已移出语料」
    idx_ign = build_index(ignored)       # 被忽略但存在，用来识别「不在版本库里」
    refs: list[Ref] = []
    for rel in scan_set:
        refs.extend(scan_file(root, rel, idx_in, idx_all, idx_ign, cfg,
                              include_bare))
    refs.sort(key=lambda r: (r.src, r.line, r.col))
    for i, r in enumerate(refs):
        r.index = i
    mark_duplicates(refs)
    return refs, scan_set, generated


def mark_duplicates(refs: list[Ref]) -> None:
    """同一行内、解析到同一处的多条引用，是同一个引用的两半。

    典型形态是 `[pity.py:1233](pity.py#L1233)`：链接文字与链接目标各被识别成
    一条，于是同一处被引内容在统计里算了两遍。保留 md-link 那一半为准。
    """
    groups: dict[tuple, list[Ref]] = {}
    for r in refs:
        if r.target is None or r.ref_span is None:
            continue
        groups.setdefault((r.src, r.line, r.target, tuple(r.ref_span)),
                          []).append(r)
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (r.form != "link", r.col))
        for r in group[1:]:
            r.dup_of = group[0].index


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def render_text(refs: list[Ref], paths: list[str], generated: list[str],
                args) -> None:
    dup = [r for r in refs if r.dup_of is not None]
    print(f"扫描文件 {len(paths)} 个，命中引用 {len(refs)} 条"
          f"（其中 {len(dup)} 条是链接文字与链接目标重复，"
          f"去重后 {len(refs) - len(dup)} 条）")
    if generated:
        print(f"已剔除本工具自产清单 {len(generated)} 个：")
        for p in generated:
            print(f"  {p}")
    print()

    for title, counter in (
        ("按状态：", Counter(r.status for r in refs if r.dup_of is None)),
        ("按上下文（区分真引用与数据）：",
         Counter(r.context for r in refs if r.dup_of is None)),
        ("按形态：", Counter(r.form for r in refs if r.dup_of is None)),
    ):
        print(title)
        for k, v in sorted(counter.items(), key=lambda kv: -kv[1]):
            print(f"  {k:18s} {v}")
        print()

    distinct = [r for r in refs if r.dup_of is None]
    base = [r for r in distinct if r.in_baseline]
    flagged = [r for r in distinct
               if r.status in ("ok", "module_level") and r.checks]
    print(f"迁移基线：可进 {len(base)} 条；"
          f"解析成功但有目标侧疑点 {len(flagged)} 条（需人工重锚）")
    if flagged:
        print("疑点分布：")
        for k, v in sorted(Counter(c.split("（")[0] for r in flagged
                                   for c in r.checks).items(), key=lambda kv: -kv[1]):
            print(f"  {k}  {v}")
    print()

    shown = refs if args.all else refs[: args.limit]
    print(f"逐条（{'全部' if args.all else f'前 {args.limit} 条'}）：")
    for r in shown:
        tgt = r.target or f"<未解析: {r.target_raw}>"
        sym = r.symbol or ("模块级" if r.symbol_span else "-")
        note = f"  [{r.detail}]" if r.detail else ""
        mark = f"  [与 #{r.dup_of + 1} 重复]" if r.dup_of is not None else ""
        print(f"  {r.src}:{r.line}  [{r.context}/{r.form}/{r.status}]{note}{mark}")
        print(f"      {r.raw[:80]}")
        print(f"      -> {tgt}  {sym}  {r.symbol_fp or ''}")
        for c in r.checks:
            print(f"      !! {c}" + (f"  建议锚点 {r.suggest}" if r.suggest else ""))


def cmd_scan(args) -> int:
    root = Path(args.root).resolve()
    cfg, note, cfg_path = load_config(root, args.config)
    if note:
        print(f"注意：{note}", file=sys.stderr)
    refs, paths, generated = run_scan(root, cfg, args.include_bare,
                                     args.include_generated)

    if args.format == "json":
        print(json.dumps(
            {"root": str(root), "files_scanned": len(paths),
             "config_used": str(cfg_path) if cfg_path else None,
             "self_output_excluded": generated,
             "refs": [r.to_dict() for r in refs]},
            ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    print(f"配置：{cfg_path if cfg_path else '未使用（内置默认）'}")
    render_text(refs, paths, generated, args)
    return 0


# 抽样要覆盖到每一个会出现的状态。少列一个，该类就只会靠余量随机补位，
# 而余量是从全体里抽的，稀有的状态几乎抽不到（实测漏掉 untracked 与
# out_of_scope 两类共 23 条，抽样里一条都没有）。
STATUS_ORDER = ["ok", "module_level", "out_of_scope", "untracked", "external",
                "ambiguous", "file_not_found", "line_out_of_range", "unparsable"]


def read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def fenced(lines: list[str], span: tuple[int, int], mark: int | None = None,
           limit: int = 14) -> str:
    """把一段行范围渲染成带行号的代码块；mark 指定的行加一个箭头标记。"""
    lo, hi = span
    out = []
    for n in range(lo, min(hi, lo + limit - 1) + 1):
        if n - 1 >= len(lines):
            break
        arrow = ">>" if n == mark else "  "
        out.append(f"{arrow}{n:>5} | {lines[n - 1]}")
    if hi - lo + 1 > limit:
        out.append(f"   ...  | （还有 {hi - lo + 1 - limit} 行）")
    return "\n".join(out)


def cmd_sample(args) -> int:
    """分层抽样，产出一份可复现的人工抽查清单。

    分层的理由：纯随机抽样会几乎全是 ok，测不出误报；抽查要看的是各类
    非 ok 项的判因对不对，以及 ok 项里有没有「解析成功但语义指错」的。
    带 --detail 时额外给出上下游原文，让核对者不必自己开文件。

    抽样只在去重后的引用上做：链接文字与链接目标各占一条，抽样时抽到同一处
    两遍是白费名额。
    """
    root = Path(args.root).resolve()
    cfg, note, cfg_path = load_config(root, args.config)
    if note:
        print(f"注意：{note}", file=sys.stderr)
    refs, _, generated = run_scan(root, cfg, args.include_bare,
                                  args.include_generated)
    refs = [r for r in refs if r.dup_of is None]

    rng = random.Random(args.seed)
    buckets: dict[str, list[Ref]] = {}
    for r in refs:
        buckets.setdefault(r.status, []).append(r)

    present = [s for s in STATUS_ORDER if s in buckets]
    unknown = sorted(set(buckets) - set(STATUS_ORDER))
    picked: list[Ref] = []
    per = max(1, args.n // max(1, len(present)))
    for status in present + unknown:
        pool = sorted(buckets.get(status, []), key=lambda r: (r.src, r.line))
        if not pool:
            continue
        take = min(per, len(pool), args.n - len(picked))
        picked.extend(rng.sample(pool, take) if take else [])
    taken = {id(r) for r in picked}
    rest = [r for r in refs if id(r) not in taken]
    rng.shuffle(rest)
    picked.extend(rest[: max(0, args.n - len(picked))])
    picked.sort(key=lambda r: (r.src, r.line))

    print(f"<!-- {SELF_MARKER}：本文件由 refcheck 产出，扫描时按标记自动剔除。-->\n")
    print("# refcheck 人工抽查清单\n")
    print(f"- 配置：`{cfg_path if cfg_path else '未使用（内置默认）'}`")
    print(f"- 种子 `{args.seed}`，样本 {len(picked)} 条，"
          f"取自去重后 {len(refs)} 条引用")
    if generated:
        print(f"- 已剔除本工具自产清单 {len(generated)} 个："
              + "、".join(f"`{p}`" for p in generated))
    print("- 判定口径：解析到的目标与范围**是否就是文中所指的那一处**")
    print(f"- 命令：`python tools/refcheck/refcheck.py sample --n {args.n} "
          f"--seed {args.seed}`\n")
    print("| # | 位置 | 上下文 | 原文 | 解析到 | 所属符号/章节 | 目标侧疑点 | 判定 |")
    print("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(picked, 1):
        raw = r.raw.replace("|", "\\|")[:60]
        tgt = (r.target or f"未解析({r.detail})").replace("|", "\\|")
        sym = (r.symbol or ("模块级" if r.symbol_span else "-")).replace("|", "\\|")
        chk = "；".join(r.checks).replace("|", "\\|") or "-"
        if r.suggest:
            chk += f"（建议 {r.suggest}）"
        loc = f"{r.src}:{r.line}"
        print(f"| {i} | `{loc}` | {r.context}/{r.form} | `{raw}` | "
              f"`{tgt}` | {sym} | {chk} | |")

    got = Counter(r.status for r in picked)
    print(f"\n统计：{dict(got)}")
    missing = [s for s in buckets if got.get(s, 0) == 0]
    if missing:
        print(f"抽到 0 条的类别（样本外）：{missing}")
    flagged = [r for r in picked if r.checks]
    print(f"带目标侧疑点的样本：{len(flagged)} / {len(picked)}")

    if not args.detail:
        return 0

    print("\n---\n\n## 逐条上下游对照\n")
    for i, r in enumerate(picked, 1):
        print(f"### {i}. `{r.src}:{r.line}`\n")
        print(f"- 原文：`{r.raw}`（{r.context} / {r.form} / {r.status}"
              + (f"，{r.detail}）" if r.detail else "）"))
        print(f"- 解析到：`{r.target or '未解析'}`"
              + (f"，所属 `{r.symbol}` {list(r.symbol_span)}"
                 if r.symbol else ""))
        if r.symbol_fp:
            print(f"- 目标指纹：`{r.symbol_fp}`")
        if r.names:
            print(f"- 本行点名且在目标文件内有定义的符号：{r.names}")
        for c in r.checks:
            print(f"- **目标侧疑点**：{c}"
                  + (f"，建议锚点 `{r.suggest}`" if r.suggest else ""))
        if r.section:
            print(f"- 所在章节：`{r.section}` {list(r.section_span)}")
        print("\n**引用所在处（箭头为引用行）**\n")
        print("```")
        print(fenced(read_lines(root / r.src), (max(1, r.line - 2), r.line + 2),
                     mark=r.line))
        print("```")
        if r.target:
            tlines = read_lines(root / r.target)
            if r.ref_span and r.line_in_file is not False:
                lo, hi = r.ref_span
                print(f"\n**被引行号处的内容**（引用写的是 {lo}-{hi}，"
                      f"箭头为起始行）\n")
                print("```")
                print(fenced(tlines, (max(1, lo - 3), hi + 3), mark=lo))
                print("```")
                if r.symbol:
                    print(f"\n所属符号：`{r.symbol}` {list(r.symbol_span)}"
                          f"，指纹 `{r.symbol_fp}`")
                if r.suggest:
                    print(f"\n文中点名符号的实际位置（建议锚点 `{r.suggest}`）：\n")
                    print("```")
                    slo, shi = (int(x) for x in r.suggest.split("-"))
                    print(fenced(tlines, (max(1, slo - 2), shi), mark=slo))
                    print("```")
            else:
                print(f"\n**被引目标**：`{r.target}` 共 {len(tlines)} 行，"
                      f"引用写的是 `{r.raw}`，对不上，故无对应内容。"
                      f"文件末尾如下（{r.status}）：\n")
                print("```")
                print(fenced(tlines, (max(1, len(tlines) - 7), len(tlines))))
                print("```")
        print("\n- 判定（目标与范围是否就是文中所指的那一处）：____")
        print("- 备注：\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="refcheck",
                                description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="扫描引用并产出迁移就绪报告（纯读）")
    s.add_argument("--root", default=".")
    s.add_argument("--config", default=None)
    s.add_argument("--format", choices=["text", "json"], default="text")
    s.add_argument("--limit", type=int, default=25)
    s.add_argument("--all", action="store_true")
    s.add_argument("--include-bare", action="store_true",
                   help="连无行号的裸文件名引用也计入；默认不计，"
                        "因为它会把普通文件名提及也算成引用")
    s.add_argument("--include-generated", action="store_true",
                   help="不剔除本工具自产的清单文件；默认剔除，"
                        "否则清单里的引用会把自己算进存量")
    s.set_defaults(func=cmd_scan)

    m = sub.add_parser("sample", help="分层抽样，产出可复现的人工抽查清单")
    m.add_argument("--root", default=".")
    m.add_argument("--config", default=None)
    m.add_argument("--n", type=int, default=20)
    m.add_argument("--seed", type=int, default=20260918)
    m.add_argument("--include-bare", action="store_true")
    m.add_argument("--include-generated", action="store_true")
    m.add_argument("--detail", action="store_true",
                   help="每条附上引用所在处的原文与被引目标的当前内容，"
                        "便于不开文件直接批注")
    m.set_defaults(func=cmd_sample)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
