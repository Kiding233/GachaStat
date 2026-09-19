#!/usr/bin/env python3
"""refcheck 阶段一：解析与指纹内核（纯读，零写入）。

只做两件事：

1. 把仓库里现存的引用找出来，解析它们指向什么，算出提议范围的指纹，
   产出「迁移就绪报告」（`scan`）。
2. 按状态分层抽样，产出一份可复现的人工抽查清单（`sample`）。

「解析成功」不等于「指对了」。文件级解析只保证目标文件存在、行号落在文件内，
而文档完全可能把锚点指到同一文件的另一处。故每条引用除 `status` 外另带两层
目标侧结论：

* **门控层**（`checks`）：精度高的判据，命中者不进迁移基线。目前三条：模块级
  单行锚点落在空行或注释上（指纹永不变化，错引用会永远显示为「未漂移」）；
  文中点名的私有符号**全仓库都不存在**（被删或改名）；源与目标同文件且引用
  位于字符串字面量里（测试数据被当成引用）。
* **复核队列**（`queues`）：文中点名的符号不覆盖目标行。这条精度只有约七成
  （文档既引定义处也引使用处，判据只认得出「不是定义处」），故只把可疑的排到
  前面，由语义复核裁决，不门控。

**`no_deterministic_issue` 只表示「确定性层面没发现问题」，不等于锚点指对了。**
独立审查两轮实测（31 条与 50 条样本）：约三到四成基线锚点指向错误位置，而那些
错绝大多数没有确定性判据能认出来。锚点得以确认的环节是迁移本身：迁移要为每条
引用写出正确范围，那一步必须做语义判断。详见计划 §九。

已知覆盖缺口：无文件名的行号引用（`` `L3899` ``、`` `:609` `` 一类）完全不识别，
实测本仓库约 65 处、11 个文件，占存量的近两成。这类引用的指称对象靠上下文
（同句或同节最近提到的文件名）确定，解析规则未定，尚未实现。

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
from functools import lru_cache
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
# 要求写成 HTML 注释形态，且只认文件头几行：光认字面量的话，一段讨论这个
# 标记的正文就会把**整份文档**静默移出扫描（本文件所在的计划正文里就写着
# 这几个字，目前靠位置侥幸没被剔除）。
SELF_MARKER = "<!-- refcheck:generated"
# 行内示例标记的两种写法在 marks.example_lines()：单行 `<!-- refcheck:example -->`，
# 或 `<!-- refcheck:example:start --> … <!-- refcheck:example:end -->` 一段。
# 「以引用机制为题材的正文」与产出物同源（工件即语料），但它是正文、不是
# 产出物，故只能靠标注。实测某计划文档自身有 15 条这样的示例引用。
# 「已删/已作废」线索只认点名符号前后这么远的范围。
CUE_WINDOW = 30

DEFAULT_INCLUDE = ["*.md", "**/*.md", "*.py", "**/*.py"]
DEFAULT_EXCLUDES = [
    "**/.venv/**", "**/venv/**", "**/node_modules/**", "**/vendor/**",
    "**/build/**", "**/dist/**", "**/__pycache__/**",
]

CONFIG_NAME = "refcheck.toml"

sys.path.insert(0, str(Path(__file__).resolve().parent))

import marks  # noqa: E402  （同目录，靠上面那行 sys.path）
import rebind  # noqa: E402
import render  # noqa: E402


# ---------------------------------------------------------------------------
# 配置：每仓库要手工补两类东西——歧义裁决，以及「已删/已作废」措辞线索
# ---------------------------------------------------------------------------


@dataclass
class Config:
    include: list[str]
    exclude: list[str]
    alias: dict[str, str]                       # 歧义 basename -> 真实路径（全局兜底）
    scoped: dict[str, dict[str, str]]           # 源文件 -> 该文件内的裁决
    external: list[str]                         # 显式声明为仓库外的路径前缀
    deleted_cues: list[str]                     # 「这个符号已删」的措辞线索（豁免用）

    @staticmethod
    def defaults() -> Config:
        return Config(list(DEFAULT_INCLUDE), list(DEFAULT_EXCLUDES), {}, {}, [], [])


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
    cfg.deleted_cues = list(data.get("checks", {}).get("deleted_cue", []))
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
    src_section: str | None = None
    src_section_span: tuple[int, int] | None = None
    src_section_fp: str | None = None
    target_section: str | None = None
    target_section_span: tuple[int, int] | None = None
    target_section_fp: str | None = None
    index: int = -1      # 排序后的序号，供 dup_of 指向
    dup_of: int | None = None   # 同一行内与另一条引用指向同一处（链接文字与链接目标两半）
    checks: list[str] = field(default_factory=list)   # 门控级疑点
    queues: list[str] = field(default_factory=list)    # 复核队列（低精度，不门控）
    suggest: str | None = None  # 疑点成立时，文中点名符号的实际位置
    names: list[str] = field(default_factory=list)    # 文中点名且在目标文件里有定义的符号

    @property
    def no_deterministic_issue(self) -> bool:
        """解析干净且无门控级疑点。

        字段名刻意不叫 `in_baseline`：那个名字容易被下游读成「可信」或「已核对」，
        而它做不到这个承诺。

        注意这只说明「确定性层面没发现问题」，**不等于锚点指对了**：两轮
        独立审查实测（31 条与 50 条样本）基线内约三到四成锚点指向错误位置，
        而那些错绝大多数没有确定性判据能认出来。迁移本身才是锚点得以确认的
        环节，见计划 §九。
        """
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
            "src_section": self.src_section,
            "src_section_span": (list(self.src_section_span)
                                 if self.src_section_span else None),
            "src_section_fp": self.src_section_fp,
            "target_section": self.target_section,
            "target_section_span": (list(self.target_section_span)
                                    if self.target_section_span else None),
            "target_section_fp": self.target_section_fp,
            "duplicate_of": self.dup_of,
            "checks": list(self.checks),
            "queues": list(self.queues),
            "suggest": self.suggest,
            "names": list(self.names),
            "no_deterministic_issue": self.no_deterministic_issue,
        }


# ---------------------------------------------------------------------------
# 仓库侧
# ---------------------------------------------------------------------------


def tracked_files(root: Path) -> list[str]:
    """走 git ls-files。目录遍历在本仓库是 5.5 秒 / 460 MB，不可用。

    必须用 -z 而不是按行切：git 默认对含非 ASCII 的路径做八进制转义并整体加引号，
    那样返回的字符串既匹配不上 glob，也打不开文件，症状是这些文件被静默跳过。
    **不是 git 仓库时退化为目录遍历**，而不是抛异常：工具要能在一份解压出来的
    源码目录上跑（设计目标有「零第三方依赖也能退化为可用」一条）。实测非 git
    目录下 `check` / `diag` 直接崩，而症状是**静默无输出**——CalledProcessError
    走到 stderr、stdout 一片空白，看起来像「没问题」。
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="surrogateescape", check=True,
        ).stdout
        return sorted(p for p in out.split("\0") if p.strip())
    except (OSError, subprocess.CalledProcessError):
        return _walk_files(root)


def _walk_files(root: Path) -> list[str]:
    """目录遍历兜底：非 git 仓库时用。跳过隐藏目录与常见构建产物。"""
    skip = {".git", ".venv", "venv", "node_modules", "__pycache__",
            ".recycle_bin", ".mypy_cache", ".pytest_cache", "dist", "build"}
    out: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in skip for part in rel.parts):
            continue
        out.append(rel.as_posix())
    return sorted(out)


def git_head(root: Path) -> str:
    """当前 HEAD，写进抽查稿头部。

    抽查稿自称「可复现」，但只记种子是不够的：语料是活的，同一份文档在两次
    扫描之间就可能改行号（实测同一引用在两次扫描间从第 727 行走到第 728 行）。
    记下 HEAD 与被扫描的规模，复现时才能判断「对不上」是工具变了还是语料变了。
    """
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                              capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "(取不到)"


def ignored_files(root: Path) -> list[str]:
    """被 .gitignore 排除、但磁盘上存在的文件。

    这一档不可少：项目里真实存在「文档引用被忽略的脚本」这种情况
    （本仓库的 scripts/profile_*.py 即是），把它们算成「文件不存在」会给出
    错误的处置建议（去修引用），而正确处置是「纳管、声明为外部、或停止引用」。
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "-o", "-i", "--exclude-standard", "-z"],
            cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="surrogateescape", check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
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


@lru_cache(maxsize=None)
def parse_py_cached(path_str: str) -> ast.AST | None:
    """按路径缓存解析结果。

    同一次运行里文件不会变，而同一个目标文件会被几十条引用反复引用
    （实测 pity.py 六十余次）。没有这层缓存时，全仓库名表那一步会把
    解析开销翻好几倍。
    """
    return parse_py(Path(path_str))


def repo_defined_names(root: Path, paths: list[str]) -> set[str]:
    """全仓库定义过的名字。

    用来区分两件事：符号**已经不存在于仓库任何地方**（被删或改名，是漂移
    信号），与符号**本来就在另一个文件里**（同一句话里引了两处而已）。
    只看目标文件会把这第二种判成第一种：实测 `_check_pity_format` 与
    `_resolve_order` 都因此被误报，它们好端端地在 config_toml.py 与 pity.py 里。
    """
    out: set[str] = set()
    for rel in paths:
        if not rel.endswith(".py"):
            continue
        tree = parse_py_cached(str(root / rel))
        if tree is not None:
            out.update(defined_symbols(tree))
    return out


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
    """目标文件里定义过的名字 → 行范围。函数、类、方法、任意层级的赋值。

    必须走完整棵树，不能只看 `tree.body`。文档点名的常常是方法
    （`_build_ridge`、`_auto_generate_resource_defs`），只看模块级就查不到，
    判据 (a) 于是**永远没有生效的机会**。实测约三成以 .py 为目标的引用
    落在这个盲区里，其中就有硬错。

    限定名与末段名都登记：调用方按末段名匹配，`Foo.bar` 与 `bar` 都查得到。
    """
    out: dict[str, list[tuple[int, int]]] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                name = prefix + child.name
                lo = child.lineno
                hi = child.end_lineno or lo
                out.setdefault(child.name, []).append((lo, hi))
                out.setdefault(name, []).append((lo, hi))
                walk(child, name + ".")
                continue
            if isinstance(child, ast.Assign):
                targets = child.targets
            elif isinstance(child, ast.AnnAssign):
                targets = [child.target]
            else:
                targets = []
            for tgt in targets:
                if isinstance(tgt, ast.Name):
                    lo = child.lineno
                    out.setdefault(tgt.id, []).append(
                        (lo, child.end_lineno or lo))
            walk(child, prefix)

    walk(tree, "")
    return out


NAME_RE = re.compile(r"(?<![A-Za-z0-9_])_?[A-Za-z][A-Za-z0-9_]{2,}(?![A-Za-z0-9_])")
COMMENT_ONLY = re.compile(r"^\s*#")

# 引用右侧多远以内的名字还算「这条引用的名字」。表格行会写成
# 「| 序号 | 路径:行号 | 符号名(...) |」，名字在引用右侧紧邻一格；
# 而句子右半段出现的符号多半是在解释被引代码里用了什么。
RIGHT_WINDOW = 12


def named_tokens(text: str, skip: tuple[int, int] | None) -> list[tuple[str, int]]:
    """挑出「像符号名」的记号，返回 (名字, 在本段内的列)。

    过滤靠三条：

    * 带下划线，或非首位有大写（普通散文词两样都不占）；
    * 前面不是 `.`（`config_toml._build_pity`、`ctx.draw.is_featured` 这类
      被别的模块或对象限定的名字，本来就不该在目标文件里有定义）；
    * 不落在引用自己那段文字里。

    这一路只产出「疑点」供人工确认，不改判定、不自动处置，所以宁可多留；
    精度交给后面四道收窄。
    """
    out: list[tuple[str, int]] = []
    for m in NAME_RE.finditer(text):
        if skip and skip[0] <= m.start() < skip[1]:
            continue
        if m.start() > 0 and text[m.start() - 1] == ".":
            continue
        tok = m.group(0)
        if "_" in tok or any(c.isupper() for c in tok[1:]):
            out.append((tok, m.start()))
    return out


def looks_like_symbol(name: str) -> bool:
    """「查无此名」这条判据要用的更严过滤。

    只认下划线开头的名字。放宽到「任何像标识符的记号」试过一次，噪声压倒
    信号：实测报出的是 `config_toml`、`gacha_service`、`card_obtained`、
    `cr_state_probs` 这一类模块名与字段名，它们本来就不该在目标文件里有定义，
    疑点从 46 条涨到 93 条而几乎全是误报。散文里写下划线开头的名字，基本
    就是在指该文件的私有符号（实测命中的 `_total_resource_gained` 属此类，
    它是 P81 已删的函数）。
    """
    return len(name) >= 6 and name.startswith("_") and not name.isupper()


SENT_BREAK = re.compile(r"[。！？；;\n]")


def clause_of(text: str, col: int) -> tuple[str, int]:
    """取引用所在的那一句，返回 (句子, 句首在本行内的列偏移)。

    同一行里另起一句提到的符号，不该算作这条引用的名字：实测有一句
    「`BootstrapEngine`（`core/bootstrap.py:33`）已实现……`BootstrapResult` 可直接
    使用」，整行取名字会把后半句的 `BootstrapResult` 栽给前半句的引用。
    """
    spans = [(m.start(), m.end()) for m in SENT_BREAK.finditer(text)]
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


def py_target_checks(lines: list[str], span: tuple[int, int],
                     defs: dict[str, list[tuple[int, int]]],
                     names: list[tuple[str, int]], enclosing: str | None,
                     strings: set[int], global_names: set[str],
                     clause: str, deleted_cues: list[str]):
    """目标侧校验，产出两层结论。

    **门控层**（`checks`，不进迁移基线）只放精度高的判据：

    * 模块级单行锚点落在空行或注释上。只对模块级成立：符号内部的锚点指纹是
      整个符号、代码动了指纹就动，而模块级的指纹就是被锚的那一行本身，锚在
      永不改动的行上等于没有记忆。注释本身不是疑点（本项目注释承载论证、
      被有意引用是常态），范围锚点也不报。
    * 文中点名的私有符号**全仓库**都找不到。符号被删或改名时是这样，是漂移
      信号里最强的一种。注意判据是「全仓库」而不是「目标文件」：同一句话里
      引了两个文件时，名字属于另一个文件是常态。文档以「已删除」的姿态提及
      被删符号时必然命中，故按 `deleted_cues` 豁免（词表在配置里，核心不含
      语言知识）。
    * 源与目标同文件、且引用位于字符串字面量里（测试数据被当成引用）。

    **复核队列**（`queues`，抬高语义复核的命中率，不作为门控）：文中点名的
    符号不覆盖目标行。这条单独量过精度只有约七成，因为文档既会引定义处、
    也会引使用处，而判据只能认出「不是定义处」。当门控会挡掉大量正确引用，
    当队列则正好。

    队列这条的收窄，每一道都拿代价换来的，**其中两道以真错位为代价**（第三轮
    独立审查实测：`cited` 一处吞掉 6 条真错位，「只看引用左侧」吞掉 3 条）：

    * 被引处原文里出现该名字就不报（引的就是它，如 `scope_slots`）。**只对
      单行锚点成立**：范围锚点常常「起点写早了、把定义整段包进去」，若对范围
      也按子串匹配，这一整类漂移形态会被无声吞掉。
    * 句中只要有一个名字覆盖目标行、或与锚点所属符号同名，一律不报
      （少了这道，一行三条引用会拿同一个名字连报三次，实测 19 条误报全出此）。
    * 被别的模块限定的名字（`config_toml._build_pity`）在取名时就已排除。
    * 取离引用最近的名字，而不是字典序第一个；名字优先取引用左侧，右侧只收
      紧邻的（`RIGHT_WINDOW`），因为表格行会写成「路径 | 符号名」。

    返回 (门控疑点, 复核队列, 建议锚点)。
    """
    line_no = span[0]
    single = span[0] == span[1]
    checks: list[str] = []
    queues: list[str] = []
    suggest: str | None = None

    if 1 <= line_no <= len(lines) and line_no not in strings and single:
        text = lines[line_no - 1]
        if enclosing is None and not text.strip():
            checks.append("模块级单行锚点落在空行上（指纹永不变化）")
        elif enclosing is None and COMMENT_ONLY.match(text):
            checks.append("模块级单行锚点落在注释上（指纹永不变化）")

    cand = [nm for nm, _ in names]
    # 「引的就是它」：被引处原文里出现该名字就不报。单行锚点看那一行，范围锚点
    # 只看**头两行**。看整个范围会把「起点写早了、把定义整段包进去」这一整类
    # 漂移无声吞掉（第三轮实测吞掉 6 条真错位），而头两行足够覆盖正当情形
    # （第四轮实测：收窄后压掉 7 条误报、32 条真错位一条不丢）。
    last = line_no if single else line_no + 1
    cited = " ".join(lines[max(0, line_no - 1):last])
    if any(nm in cited for nm in cand):
        return checks, queues, suggest
    # 这一句在讲「某符号已删/已作废」时，它的锚点指的是历史，不是现状。
    # 门控与队列共用这条豁免：实测那类句子会让门控误报一次、队列误报一次
    # （被删符号在库里当然找不到；被作废的那一行锚点本来就不该指着现存代码）。
    # 线索只认点名符号**近旁**的，不认整句：词表里的「删除」「作废」都是泛用词，
    # 一句「删除该分支会导致 X 失效，见 pity.py:NNN」若锚点其实是错的，
    # 整句豁免会让它永远不被检查。
    if any(cue and cue in clause[max(0, col - CUE_WINDOW):col + len(nm) + CUE_WINDOW]
           for nm, col in names for cue in deleted_cues if cue):
        return checks, queues, suggest
    for nm in cand:
        spans = defs.get(nm)
        if not spans:
            continue
        if any(lo <= line_no <= hi for lo, hi in spans):
            return checks, queues, suggest
        if enclosing and (enclosing == nm or enclosing.startswith(nm + ".")
                          or enclosing.endswith("." + nm)):
            return checks, queues, suggest

    for nm in cand:
        if nm in defs:
            lo, hi = min(defs[nm])
            queues.append(f"文中点名 `{nm}`，它不覆盖目标行（它在 {lo}-{hi}）")
            suggest = f"{lo}-{hi}"
            return checks, queues, suggest

    for nm in cand:
        if looks_like_symbol(nm) and nm not in global_names:
            checks.append(f"文中点名 `{nm}`，全仓库都没有这个名字")
            break
    return checks, queues, suggest

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
              global_names: set[str],
              include_bare: bool = False) -> list[Ref]:
    try:
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = text.splitlines()
    is_md = rel.endswith(".md")
    stdlib = stdlib_names()
    refs: list[Ref] = []
    skip_example = marks.example_lines(text) if is_md else set()

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
        # 标为示例的行整行跳过。两种写法：单行 `<!-- refcheck:example -->`，
        # 或一段 start/end 区域。区域形式是必需的：展示标记语法的代码块里
        # 逐行插标记会把示例本身弄脏。
        if pos[0] in skip_example:
            return
        seen.add((pos[0], pos[1]))
        ref = Ref(src=rel, line=pos[0], col=pos[1], form=form, context=context,
                  raw=raw, target_raw=target_raw)
        finish(ref, root, idx_in, idx_all, idx_ign, cfg, lines, is_md, stdlib,
               global_names, start, end)
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
           is_md, stdlib, global_names, start, end) -> None:
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
        tree = parse_py_cached(str(root / ref.target))
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
        # 文中点名的符号。只看引用所在那一句、只看引用紧邻的两侧，并跳过
        # 引用自己那段文字（免得把路径当成符号名、把邻句或解释性提及的符号
        # 栽给这条引用）。
        src_text = lines[ref.line - 1] if 0 < ref.line <= len(lines) else ""
        clause, base = clause_of(src_text, ref.col)
        ref_col = ref.col - base
        ref_end = ref_col + len(ref.raw)
        names = [(nm, col) for nm, col in named_tokens(clause, (ref_col, ref_end))
                 if col < ref_col or col - ref_end <= RIGHT_WINDOW]
        names.sort(key=lambda t: ref_col - t[1] if t[1] < ref_col
                   else t[1] - ref_end)
        defs = defined_symbols(tree)
        ref.names = sorted({nm for nm, _ in names if nm in defs})
        _, tstrings = py_signal_lines("\n".join(tlines))
        ref.checks, ref.queues, ref.suggest = py_target_checks(
            tlines, want, defs, names, found[0] if found else None,
            tstrings, global_names, clause, cfg.deleted_cues)
    elif ref.target.endswith(".md"):
        # .md 目标也要有被引侧指纹，否则这类引用在迁移时写不出记忆。
        # 此前只算了源文档的章节，字段名又像是指目标侧，两者混在一起。
        tlines = read_lines(root / ref.target)
        tsec = section_at(sections_of(tlines), int(start))
        if tsec:
            ref.target_section = tsec[3]
            ref.target_section_span = (tsec[0], tsec[1])
            ref.target_section_fp = fingerprint_lines(tlines,
                                                      ref.target_section_span)

    # 源与目标同文件、且引用位于字符串字面量里：多半是测试数据或文档字符串
    # 里的举例，不是真引用。实测全库唯一一条明确的「代码字符串误判为引用」
    # 就属这一类，而它此前落在基线内。
    if ref.context == "string" and ref.src == ref.target:
        ref.checks.append("疑非引用（源与目标同文件且位于字符串内）")

    if is_md:
        sec = section_at(sections_of(lines), ref.line)
        if sec:
            ref.src_section = sec[3]
            ref.src_section_span = (sec[0], sec[1])
            ref.src_section_fp = fingerprint_lines(lines, ref.src_section_span)


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

    只看文件头 8 行，不看「前若干字符」：产出物的标记恒在第一行，而用字符数
    划界会让「正文里提到这个标记」的文档在标记上移时被整份剔除，且症状是
    静默的（只在剔除清单里露出一行）。
    """
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            head = [next(fh, "") for _ in range(8)]
    except OSError:
        return False
    return any(SELF_MARKER in ln for ln in head)


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
    global_names = repo_defined_names(root, targets)
    refs: list[Ref] = []
    for rel in scan_set:
        refs.extend(scan_file(root, rel, idx_in, idx_all, idx_ign, cfg,
                              global_names, include_bare))
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
    base = [r for r in distinct if r.no_deterministic_issue]
    gated = [r for r in distinct if r.checks]
    queued = [r for r in distinct
              if r.status in ("ok", "module_level") and r.queues and not r.checks]
    print(f"解析干净 {len([r for r in distinct if r.status in ('ok', 'module_level')])} 条："
          f"其中门控级疑点 {len(gated)} 条（不进基线），"
          f"复核队列命中 {len(queued)} 条")
    print(f"**解析干净且无门控疑点 {len(base)} 条。注意这只表示确定性层面没发现问题，"
          f"不等于锚点指对了（独立实测约三到四成锚点指错）。**")
    for title, group in (("门控疑点分布：", gated), ("复核队列分布：", queued)):
        if not group:
            continue
        print(title)
        counter = Counter(c.split("（")[0] for r in group
                          for c in (r.checks or r.queues))
        for k, v in sorted(counter.items(), key=lambda kv: -kv[1]):
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
        for c in r.queues:
            print(f"      ?  {c}" + (f"  建议锚点 {r.suggest}" if r.suggest else ""))


def cmd_scan(args) -> int:
    root = Path(args.root).resolve()
    cfg, note, cfg_path = load_config(root, args.config)
    if note:
        print(f"注意：{note}", file=sys.stderr)
    refs, paths, generated = run_scan(root, cfg, args.include_bare,
                                     args.include_generated)

    if args.format == "json":
        # ensure_ascii=True 是刻意的：stdout 的编码不一定支持全部字符
        #（Windows 上非 UTF-8 代码页时，文档原文里的 emoji 会让 print 抛
        # UnicodeEncodeError），而失败模式很坏——重定向文件里留下半截 JSON。
        # 纯 ASCII 输出在任何编码下都成立，中文以 \uXXXX 转义，机器照样读。
        print(json.dumps(
            {"root": str(root), "files_scanned": len(paths),
             "config_used": str(cfg_path) if cfg_path else None,
             "self_output_excluded": generated,
             "refs": [r.to_dict() for r in refs]},
            ensure_ascii=True, indent=2, sort_keys=True))
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
    refs, paths, generated = run_scan(root, cfg, args.include_bare,
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

    print(f"{SELF_MARKER}：本文件由 refcheck 产出，扫描时按标记自动剔除。-->\n")
    print("# refcheck 人工抽查清单\n")
    print(f"- 配置：`{cfg_path if cfg_path else '未使用（内置默认）'}`")
    print(f"- 语料指纹：HEAD `{git_head(root)}`，{len(paths)} 个文件，"
          f"去重后 {len(refs)} 条引用")
    print(f"- 种子 `{args.seed}`，样本 {len(picked)} 条")
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
        chk = "；".join(f"门控：{c}" for c in r.checks)
        chk += "；".join(("；" if chk else "") + f"队列：{c}" for c in r.queues)
        chk = chk.replace("|", "\\|") or "-"
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
    print(f"带门控疑点的样本：{len([r for r in picked if r.checks])} / {len(picked)}")
    print(f"命中复核队列的样本：{len([r for r in picked if r.queues])} / {len(picked)}")

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
        if r.src_section:
            print(f"- 引用所在章节（源文档）：`{r.src_section}` "
                  f"{list(r.src_section_span)}")
        if r.target_section_fp:
            print(f"- 被引侧章节指纹：`{r.target_section_fp}`"
                  f"（`{r.target_section}` {list(r.target_section_span)}）")
        for c in r.checks:
            print(f"- **门控疑点**：{c}"
                  + (f"，建议锚点 `{r.suggest}`" if r.suggest else ""))
        for c in r.queues:
            print(f"- 复核队列：{c}"
                  + (f"，建议锚点 `{r.suggest}`" if r.suggest else ""))
        if r.src_section:
            print(f"- 所在章节：`{r.src_section}` {list(r.src_section_span)}")
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


def cmd_check(args) -> int:
    """对账：从磁盘现状派生全部关系的状态。

    这是设计里说的**核心原语**（计划 §3.14）：幂等、无状态、谁都能调，
    钩子只是闹钟。它只读，不渲染、不写盘。
    """
    root = Path(args.root).resolve()
    cfg, note, cfg_path = load_config(root, args.config)
    if note:
        print(f"注意：{note}", file=sys.stderr)
    all_tracked = tracked_files(root)
    targets = [p for p in all_tracked if not excluded(p, cfg.exclude)]
    scan_set = [p for p in targets if in_scope(p, cfg.include, [])]
    scan_set = [p for p in scan_set if not is_self_output(root / p)]
    if args.changed:
        want = {x.strip().replace("\\", "/") for x in args.changed.split(",")}
        scan_set = [p for p in scan_set if p.replace("\\", "/") in want]

    rep = marks.derive(root, scan_set)
    issues, stats = rep.issues, rep.stats
    blocking = rep.blocking
    if args.format == "json":
        print(json.dumps({"config_used": str(cfg_path) if cfg_path else None,
                          "stats": stats, "blocking": len(blocking),
                          "issues": [{"state": i.state, "where": i.where,
                                      "detail": i.detail} for i in issues]},
                         ensure_ascii=True, indent=2, sort_keys=True))
        return 1 if blocking else 0

    print(f"配置：{cfg_path if cfg_path else '未使用（内置默认）'}")
    print(f"对账 {stats['files']} 个文件：标记 {stats['marks']} 个，"
          f"范围 {stats['ranges']} 个，声明 {stats['decls']} 条，"
          f"关系 {stats['relations']} 条（ok {stats['ok']}）")
    if not issues:
        print("无问题。")
        return 0
    print("")
    print(f"问题 {len(issues)} 条（其中阻断 {len(blocking)} 条）：")
    for i in issues:
        mark = "!" if i.state in marks.BLOCKING else " "
        print(f" {mark} {i.as_line()}")
    return 1 if blocking else 0


def _ticket(rep, files):
    """工单素材：闭包内**已被核对过**的声明，附上次核对与证据。

    §3.14 要求钩子的失败输出能说清「上次核对与证据」。这两样只存在于机器区，
    所以只能由这里读出来——渲染区是纯输出、会被覆盖，不能当数据源。
    """
    out = []
    for mk in rep.decls:
        rng = rep.ranges_by_uid.get(mk.uid)
        if not rng or rng[0].path not in files:
            continue
        if not (mk.verified or mk.evidence):
            continue
        out.append((mk, mk.uid))
    return out


def cmd_diag(args) -> int:
    """关系图诊断：闭包 + 环 + 模拟提交判定，一次算完，三种视图。

    给「我这一改会牵动什么」这个问题用的，也是钩子判定的内核。**纯读**：
    它不做渲染、不写盘；渲染只有钩子与显式 `render` 才做，否则 agent 随口
    调一次诊断就把工作区改脏了。

    为什么不只给图：图本身不可行动。「这些文件连在一起」不说明任何该做的
    事，可行动的是「提交时会被报什么」，所以两者必须一起给——它们是同一次
    计算的两个视图，不是两个命令。
    """
    root = Path(args.root).resolve()
    cfg, note, cfg_path = load_config(root, args.config)
    if note:
        print(f"注意：{note}", file=sys.stderr)
    all_tracked = tracked_files(root)
    targets = [p for p in all_tracked if not excluded(p, cfg.exclude)]
    scan_set = [p for p in targets if in_scope(p, cfg.include, [])]
    scan_set = [p for p in scan_set if not is_self_output(root / p)]

    rep = marks.derive(root, scan_set)
    # 只有一张图，节点是 uid。「改这个文件牵动哪些文件」是它投影到路径的结果。
    adj = marks.adjacency(rep.edges)
    if args.changed:
        seeds = {x.strip().replace("\\", "/") for x in args.changed.split(",")}
        nodes = marks.closure(adj, marks.uids_in_files(rep, seeds))
    else:
        seeds = set()
        nodes = set(rep.ranges_by_uid)
    files = marks.files_of(rep, nodes)
    loops = marks.cycles(adj, nodes)
    inside = ([i for i in rep.blocking
               if any(i.where.startswith(f + ":") for f in files)]
              if args.changed else rep.blocking)

    if args.format == "json":
        print(json.dumps({
            "config_used": str(cfg_path) if cfg_path else None,
            "seeds": sorted(seeds), "stats": rep.stats,
            "nodes": sorted(marks.node_label(rep, u) for u in nodes),
            "files": sorted(files),
            "edges": [{"a": e.a_path, "a_uid": e.a_uid, "b": e.b_path,
                       "b_uid": e.b_uid, "label": e.label, "state": e.state,
                       "at": e.at} for e in rep.edges],
            "cycles": [[marks.node_label(rep, u) for u in c] for c in loops],
            "would_block": [{"state": i.state, "where": i.where,
                             "detail": i.detail} for i in inside],
            "ticket": _ticket(rep, files),
        }, ensure_ascii=True, indent=2, sort_keys=True))
        return 1 if inside else 0

    print(f"配置：{cfg_path if cfg_path else '未使用（内置默认）'}")
    if seeds:
        print(f"起点 {len(seeds)} 个文件；闭包 {len(nodes)} 个范围，"
              f"落在 {len(files)} 个文件里")
    else:
        print(f"未给 --changed，按全库报：{len(nodes)} 个范围，"
              f"{len(rep.edges)} 条关系")
    print("")
    if loops:
        print(f"环 {len(loops)} 处（本项目中很可能是常态，不是错误；"
              f"列出来是为了让改的人提前知道）:")
        for cyc in loops[:6]:
            print("   " + " -> ".join(marks.node_label(rep, u) for u in cyc))
    else:
        print("环：无")
    print("")
    print(f"模拟提交判定：{len(inside)} 条会被报出")
    for i in inside:
        print(f"   ! {i.as_line()}")
    for mk, uid in _ticket(rep, files):
        print(f"   · {mk.path}:{mk.line}  关系 {uid}  上次核对 "
              f"{mk.verified or '(未记录)'}  证据 {mk.evidence or '(无)'}")
    if not inside:
        print("   （闭包内无阻断项）")
    return 1 if inside else 0


def cmd_render(args) -> int:
    """渲染：把派生出的视图写回渲染区。**这是第一个会写盘的命令。**

    `--dry-run` 就是设计里说的「时效性诊断」：算出哪些文件的视图会变，不落盘。

    渲染是**无条件全局**的（计划 §九）：视图的输出是全局事实，而按闭包收窄
    会让闭包外的过期视图一直显示 ok、把真实的漂移盖住。所以这里不接种子集，
    只按「状态是否真的变了」决定写什么。
    """
    root = Path(args.root).resolve()
    cfg, note, cfg_path = load_config(root, args.config)
    if note:
        print(f"注意：{note}", file=sys.stderr)
    all_tracked = tracked_files(root)
    targets = [p for p in all_tracked if not excluded(p, cfg.exclude)]
    scan_set = [p for p in targets if in_scope(p, cfg.include, [])]
    scan_set = [p for p in scan_set if not is_self_output(root / p)]

    edits, refusals, rep = render.plan(root, scan_set)
    stale = sorted({e.path for e in edits})

    if args.dry_run:
        print(f"配置：{cfg_path if cfg_path else '未使用（内置默认）'}")
        print(f"时效性诊断（dry-run，未落盘）：{len(edits)} 处视图过期，"
              f"涉及 {len(stale)} 个文件")
        for p in stale:
            n = sum(1 for e in edits if e.path == p)
            print(f"   {p}  {n} 处")
        _report_refusals(refusals)
        return 0

    written = render.apply(root, edits)
    print(f"渲染完成：改写 {sum(written.values())} 处视图，"
          f"涉及 {len(written)} 个文件")
    for p, n in sorted(written.items()):
        print(f"   {p}  {n} 处")
    if not written:
        print("   （没有视图需要更新）")
    _report_refusals(refusals)
    return 0


def _report_refusals(refusals) -> None:
    if not refusals:
        return
    print("")
    print(f"危险位置拒绝写入 {len(refusals)} 处：")
    for r in refusals[:20]:
        print(f"   {r.path}:{r.line}  {r.why}")
    if len(refusals) > 20:
        print(f"   （还有 {len(refusals) - 20} 处）")


def cmd_rebind(args) -> int:
    """把当前内容认作新基线：写回两侧的 `h`，并记下核对时间与证据。

    **这是整套东西里唯一改变判定结果的写操作。** 别的写入要么只读、要么只动
    渲染区（下次渲染覆盖）；只有它动机器区的 `h`，跑错了就把错误的范围冻进
    记忆（错锚点的指纹自洽，此后永远检测不出来）。故必须带证据，且环上拦住。
    """
    root = Path(args.root).resolve()
    cfg, note, cfg_path = load_config(root, args.config)
    if note:
        print(f"注意：{note}", file=sys.stderr)
    all_tracked = tracked_files(root)
    targets = [p for p in all_tracked if not excluded(p, cfg.exclude)]
    scan_set = [p for p in targets if in_scope(p, cfg.include, [])]
    scan_set = [p for p in scan_set if not is_self_output(root / p)]

    edits, refusals, rep = rebind.plan(root, scan_set, args.rel, args.note,
                                       args.allow_cycle)
    if refusals:
        print("拒绝 rebind：")
        for r in refusals:
            print(f"   {r}")
        return 1
    if args.dry_run:
        print(f"dry-run（未落盘）：会写 {len(edits)} 处")
        for e in edits:
            print(f"   {e.path}:{e.line}")
            print(f"      旧 {e.old}")
            print(f"      新 {e.new}")
        return 0
    written = rebind.apply(root, edits)
    print(f"rebind 完成：改写 {sum(written.values())} 处声明")
    for p, n in sorted(written.items()):
        print(f"   {p}  {n} 处")
    print("提示：视图随之过时，跑 `render` 刷新。")
    return 0


def main(argv: list[str] | None = None) -> int:
    # 文本输出里会带文档原文（含 emoji）。终端编码不支持时 print 会抛
    # UnicodeEncodeError，所以让不可编码的字符退化为转义而不是崩掉；
    # 换成别的仓库、别的终端时这条尤其重要。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, OSError, ValueError):
            pass

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

    rb = sub.add_parser("rebind", help="把当前内容认作新基线（写盘，唯一改判定的写操作）")
    rb.add_argument("--root", default=".")
    rb.add_argument("--config", default=None)
    rb.add_argument("--rel", required=True,
                    help="关系 id：该关系任一侧范围的 uid")
    rb.add_argument("--note", required=True,
                    help="核对证据（一句话）。必须给：核对产物要能被人看见")
    rb.add_argument("--allow-cycle", action="store_true",
                    help="确已在环上把各端表述一起定稿（§3.16）")
    rb.add_argument("--dry-run", action="store_true")
    rb.set_defaults(func=cmd_rebind)

    r = sub.add_parser("render", help="渲染：把视图写回渲染区（会写盘）")
    r.add_argument("--root", default=".")
    r.add_argument("--config", default=None)
    r.add_argument("--dry-run", action="store_true",
                   help="只报哪些文件的视图会变，不落盘（时效性诊断）")
    r.set_defaults(func=cmd_render)

    d = sub.add_parser("diag", help="关系图诊断：闭包 + 环 + 模拟提交判定（纯读）")
    d.add_argument("--root", default=".")
    d.add_argument("--config", default=None)
    d.add_argument("--format", choices=["text", "json"], default="text")
    d.add_argument("--changed", default=None,
                   help="起点文件（逗号分隔）；缺省按全库报")
    d.set_defaults(func=cmd_diag)

    c = sub.add_parser("check", help="对账：扫标记、配关系、派生状态（纯读）")
    c.add_argument("--root", default=".")
    c.add_argument("--config", default=None)
    c.add_argument("--format", choices=["text", "json"], default="text")
    c.add_argument("--changed", default=None,
                   help="只报与这些文件有关的关系（逗号分隔）；缺省全库")
    c.set_defaults(func=cmd_check)

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
