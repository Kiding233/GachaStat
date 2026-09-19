#!/usr/bin/env python3
"""`rebind`：把新指纹**同时写回两侧**，即把当前内容认作新基线。

名字不叫 `verify`：那个名字读起来像纯读的检查，而它恰恰是**唯一改变判定结果的
写操作**，名字与后果反着。叫 `rebind` 是因为它**不改关系的存在，只把记忆重新
绑到现状**——这与 §3.14 被否掉的 `bind`/`unbind`（建与拆关系）是两回事。

这是整套东西里**唯一改变判定结果的写操作**。每一处其他写入要么是只读、要么
只动渲染区（下次渲染覆盖）；只有它动机器区的 `h`。**跑错了就把错误的范围冻进
记忆**：错锚点的指纹自洽，此后永远检测不出来。所以它比 `render` 严得多：

* **必须带证据**（`--note`）。依据是 §八 的风险行「语义核对被橡皮图章」：
  核对的产物要能被人看见，否则「核对过了」只是一句话。证据与核对时间写进
  机器区（`v=` / `ev=`）而不是渲染区——渲染区会被下次渲染覆盖，放那里等于丢；
  而钩子拼工单时明确要读「上次核对时间与证据」（§3.14）。
* **环上拦住**。§3.16：成环时必须先把环上各端表述**一起定稿**再逐条 `rebind`，
  否则逐条处理会互相推翻。所以本关系若在环上，除非显式 `--allow-cycle`，否则拒绝。
* **顺序无关**。写 `h` 不改变任何指纹：声明落在自己的范围之内，而指纹先剥
  标记。所以两侧一起写不会自锁，也不存在「先写哪一侧」的问题。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

from marks import (FIELD_FORBIDDEN, FIELD_ORDER, Mark, Report,
                   adjacency_by_uid, cycles, derive)

MARK_HEAD = "<|"


@dataclass
class RebindEdit:
    path: str
    line: int
    old: str
    new: str
    note: str


def _bad_field(text: str) -> str:
    hit = sorted(set(text) & FIELD_FORBIDDEN)
    return f"证据里不能出现这些字符：{''.join(hit)}（它们是分隔符）" if hit else ""


def _field_value(fp: dict[str, str], peer_seg: str) -> str:
    return fp.get(peer_seg) or fp.get("*") or ""


def render_marker(mk: Mark, h: str, date: str, note: str) -> str:
    """按 FIELD_ORDER 重排机器区字段，保留已有的渲染区。"""
    fields = {"h": h, "v": date, "ev": note}
    body = f"{mk.label}：{mk.peer}#{mk.peer_seg}"
    for k in FIELD_ORDER:
        if fields.get(k):
            body += f";{k}={fields[k]}"
    view = f"({mk.view})" if mk.view else ""
    return f"{MARK_HEAD}{body}|{view}>"


def plan(root: Path, paths: list[str], uid: str, note: str,
         allow_cycle: bool = False) -> tuple[list[RebindEdit], list[str], Report]:
    """算出该写什么。返回 (编辑, 拒绝原因, 报告)。"""
    bad = _bad_field(note)
    if not note.strip():
        return [], ["必须带证据（--note）：核对产物要能被人看见，"
                    "否则「核对过了」只是一句话"], derive(root, paths)
    if bad:
        return [], [bad], derive(root, paths)

    rep = derive(root, paths)
    decls = [m for m in rep.decls if m.uid == uid or m.peer == uid]
    if not decls:
        return [], [f"uid `{uid}` 没有任何声明"], rep

    # §3.16：环上先定稿再逐条 rebind。
    # 判环必须用 **uid 图**，不能用文件图：一个文件里可以有几十个范围，
    # 文件级的环会把不相干的关系也报进来。（我第一版就是拿 uid 去文件级
    # 的环里找，永远找不到，守卫等于没有——样例测试当场抓出。）
    adj = adjacency_by_uid(rep.edges)
    reach = {uid}
    stack = [uid]
    while stack:
        cur = stack.pop()
        for nxt in adj.get(cur, ()):
            if nxt not in reach:
                reach.add(nxt)
                stack.append(nxt)
    loops = cycles(adj, reach)
    on_loop = [c for c in loops if uid in c]
    if on_loop and not allow_cycle:
        return [], [f"uid `{uid}` 在环上（{' -> '.join(on_loop[0])}）；"
                    f"§3.16 要求成环时先把环上各端表述一起定稿再逐条 verify，"
                    f"确已定稿请加 --allow-cycle"], rep

    date = datetime.date.today().isoformat()
    edits: list[RebindEdit] = []
    for mk in decls:
        peer_ranges = rep.ranges_by_uid.get(mk.peer, [])
        if not peer_ranges:
            return [], [f"{mk.path}:{mk.line} 的对方 `{mk.peer}` 扫不到，"
                        f"无从取指纹；这条关系应判 broken 而不是 rebind"], rep
        if len(peer_ranges) > 1:
            # 对方多段：h 写成「对方段标签 → 指纹」的映射
            h = "{" + ",".join(f"{r.seg}:{r.fp}" for r in peer_ranges) + "}"
        else:
            h = peer_ranges[0].fp
        edits.append(RebindEdit(mk.path, mk.line, mk.raw,
                                render_marker(mk, h, date, note), note))
    return edits, [], rep


def apply(root: Path, edits: list[RebindEdit]) -> dict[str, int]:
    by_file: dict[str, list[RebindEdit]] = {}
    for e in edits:
        by_file.setdefault(e.path, []).append(e)
    written: dict[str, int] = {}
    for rel, group in by_file.items():
        p = root / rel
        text = p.read_text(encoding="utf-8")
        n = 0
        for e in sorted(group, key=lambda x: x.line, reverse=True):
            if e.old == e.new or e.old not in text:
                continue                      # 值没变就不算一次写入
            text = text.replace(e.old, e.new, 1)
            n += 1
        if n:
            p.write_text(text, encoding="utf-8")
            written[rel] = n
    return written
