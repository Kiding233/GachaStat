#!/usr/bin/env python3
"""渲染：把派生出的视图写回标记的渲染区。

这是这套东西里**第一个会写盘的模块**，所以纪律比别处严：

* **只写渲染区**，机器区一个字不动。视图是纯输出，手改会被下次渲染覆盖，
  因此它不是第二真相源（§3.2.6）。
* **逐字节比对，相同则整文件不写**（§3.10）。视图里两个字段的**变动频率不同**：
  状态只在跳变时变，而定位符（行号）会随上方代码移动而变。所以准确的措辞是
  **写入次数与「状态跳变次数 + 定位符移动次数」成正比**，而 §3.10 原文只说
  了「与状态跳变次数成正比、与编辑次数无关」——那句对状态成立、对定位符不成立。
  定位符移动**不是正确性事件**（指纹不动、状态不变），所以它引起的那次重写
  只是刷新显示，原样提交即可。
* **危险位置拒绝写入，不硬写**（§3.10）：标记自身落在代码围栏内或表格行内
  时拒绝。理由机械且具体：标记里的 `|` 会被 GFM 当成单元格分隔符，写进去
  表格结构就散了；围栏里则是内容保真问题。
* **不自锁**：引用侧的记忆是对方的**范围**，而范围不含渲染区（指纹先剥标记），
  所以写视图不改变任何指纹，不会触发第二轮漂移。这一点有验收（见计划 §3.10：
  连续渲染两次零 diff）。

`--dry-run` 就是设计里说的「时效性诊断」：算出哪些文件的视图会变，但不落盘。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from marks import Mark, Report, derive

@dataclass
class Edit:
    path: str
    line: int
    old: str            # 旧的标记全文
    new: str            # 新的标记全文
    reason: str


@dataclass
class Refusal:
    path: str
    line: int
    why: str


def short_locator(path: str, line: int, all_paths: list[str]) -> str:
    """最短定位形式（F5）。

    先试 basename；同名文件多于一个时逐段加前缀，直到唯一。不追求绝对最短，
    只求「唯一且短」——完整限定路径由工具在需要时展开。
    """
    posix = path.replace("\\", "/")
    if posix == "":
        return f":{line}"
    segs = posix.split("/")
    for k in range(1, len(segs) + 1):
        cand = "/".join(segs[-k:])
        if sum(1 for p in all_paths
               if p.replace("\\", "/").endswith(cand)) <= 1:
            return f"{cand}:{line}"
    return f"{posix}:{line}"


def desired_view(rep: Report, mk: Mark, all_paths: list[str]) -> str:
    """一条声明应有的视图文本：`(最短定位;状态)`。

    状态名取自这份声明**自己那一端**的判定（引用侧报 tgt_drift、被引侧报
    src_drift），与机器区里的 `h` 无关——视图放判定结论，不放哈希。

    定位**用行号**：让行号自动更新本来就是这套设计的初衷之一（「代码改了，
    行号引用要跟着更新」）。行号变了不改变指纹、不改变漂移状态，所以视图
    因它重写**不是正确性事件**，只是把显示刷新一次——原样提交即可。
    """
    peer = next((e for e in rep.edges
                 if e.a_uid == mk.uid and e.b_uid == mk.peer
                 and e.at == f"{mk.path}:{mk.line}"), None)
    if peer is None:
        # 没有配对的边（对方扫不到等）：视图仍要如实说
        return f"({mk.peer}#{mk.peer_seg};broken)"
    rng = next((r for r in rep.ranges_by_uid.get(mk.peer, [])
                if r.seg == mk.peer_seg), None)
    loc = (short_locator(rng.path, rng.span[0], all_paths)
           if rng else f"{mk.peer}#{mk.peer_seg}")
    state = "ok" if peer.state == "ok" else "tgt_drift"
    return f"({loc};{state})"


def rewrite_marker(mk: Mark, view: str) -> str:
    """把标记的渲染区换成 view。机器区原样保留。

    两种旧形态都要处理：本来没有渲染区（`<|…|>`）要插入；本来有
    （`<|…|(旧)>`）要替换。
    """
    body = mk.raw
    close = body.rfind(">")
    if close == -1:
        return body
    head = body[:close]
    # 去掉可能已有的渲染区
    paren = head.rfind("|(")
    if paren != -1 and head.endswith(")"):
        head = head[:paren + 1]
    return f"{head}{view}>"


def plan(root: Path, paths: list[str]) -> tuple[list[Edit], list[Refusal], Report]:
    """算出该写什么，不落盘。"""
    rep = derive(root, paths)
    all_paths = [p.replace("\\", "/") for p in paths]
    edits: list[Edit] = []
    # 危险位置上的标记已被 derive 排除在配对之外，这里只把它们原样报出来
    refusals = [Refusal(*i.where.rsplit(":", 1), i.facts)
                for i in rep.issues if i.state == "mark_at_danger"]
    for mk in rep.decls:
        want = desired_view(rep, mk, all_paths)
        if mk.view and f"({mk.view})" == want:
            continue                      # 已经是对的，不写
        edits.append(Edit(mk.path, mk.line, mk.raw,
                          rewrite_marker(mk, want), "视图更新"))
    return edits, refusals, rep


def apply(root: Path, edits: list[Edit]) -> dict[str, int]:
    """按文件分组、从后往前替换，逐文件写一次。返回 {路径: 替换数}。"""
    by_file: dict[str, list[Edit]] = {}
    for e in edits:
        by_file.setdefault(e.path, []).append(e)
    written: dict[str, int] = {}
    for rel, group in by_file.items():
        p = root / rel
        text = p.read_text(encoding="utf-8")
        n = 0
        for e in sorted(group, key=lambda x: x.line, reverse=True):
            if e.old not in text:
                continue
            text = text.replace(e.old, e.new, 1)
            n += 1
        if n:
            p.write_text(text, encoding="utf-8")
            written[rel] = n
    return written


