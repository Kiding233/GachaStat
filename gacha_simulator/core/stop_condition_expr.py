"""停止条件表达式的解析与互转——纯函数、零 Qt 依赖（P79 5.6）。

**落点纪律（5.6「表达式子系统的落点」）：** 本模块承载三件事，共用一个
tokenizer——表达式解析器（4d1）、条件树 ↔ 表达式双向互转（4d2a）、引用完整性
纯函数（4d3）。

不落 ``gui/`` 的理由：引用完整性纯函数的入参含**表达式字符串**，必须有 core 侧
解析入口；``config_panel.validate_banners()`` 与 WebUI 适配都要「从
``ConfigStore.stop_condition`` 树重建表达式」后校验。

**不参与落盘**：TOML 只存递归条件树，表达式只是 GUI 的编辑视图，解析器故障不影响
配置文件正确性（5.6 的架构裁决）。本模块亦不承载可比性指纹的规范化摘要——那个摘要
必须**含参数值**，而本模块的「树 → 表达式」方向只含条件 id（见阶段 4「可比性指纹」段）。

语法：操作数是**条件 id**，运算符只有 ``and`` / ``or`` / ``not`` 与括号，优先级
``not`` > ``and`` > ``or``。例：``a or (b and not c)``。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

__all__ = [
    'StopConditionExprError',
    'parse_stop_condition_expr',
    'expr_ast_to_text',
    'tree_to_conditions_and_expr',
    'expr_to_tree',
    'validate_stop_condition_config',
]

# 条件 id 的合法形态：ASCII 标识符（GUI 侧自动分配 a/b/c…）
_IDENT_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_OPERATORS = ('and', 'or', 'not')

# ── 表达式 AST ────────────────────────────────────────────────────
# ('id', name) | ('not', child) | ('and', left, right) | ('or', left, right)

ExprNode = Tuple


class StopConditionExprError(ValueError):
    """表达式错误——消息面向用户可读，不含调用栈信息。"""


def _tokenize(text: str) -> List[Tuple[str, str, int]]:
    """切分为 (kind, value, pos) 序列；kind ∈ {'id', 'op', 'paren'}。"""
    tokens: List[Tuple[str, str, int]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in '()':
            tokens.append(('paren', ch, i))
            i += 1
            continue
        match = _IDENT_RE.match(text, i)
        if match:
            word = match.group(0)
            lowered = word.lower()
            if lowered in _OPERATORS:
                tokens.append(('op', lowered, i))
            else:
                tokens.append(('id', word, i))
            i = match.end()
            continue
        raise StopConditionExprError(
            f"表达式中出现无法识别的字符 {ch!r}（第 {i + 1} 个字符）")
    return tokens


class _Parser:
    """递归下降：or → and → not → atom。"""

    def __init__(self, tokens: List[Tuple[str, str, int]],
                 known_ids: Optional[Set[str]]):
        self._tokens = tokens
        self._pos = 0
        self._known_ids = known_ids

    def _peek(self) -> Optional[Tuple[str, str, int]]:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _next(self) -> Optional[Tuple[str, str, int]]:
        token = self._peek()
        if token is not None:
            self._pos += 1
        return token

    def _check_id(self, name: str) -> str:
        if self._known_ids is not None and name not in self._known_ids:
            raise StopConditionExprError(f"表达式引用了不存在的条件 id：'{name}'")
        return name

    def parse(self) -> ExprNode:
        if not self._tokens:
            raise StopConditionExprError("表达式为空")
        node = self._parse_or()
        leftover = self._peek()
        if leftover is not None:
            kind, value, _pos = leftover
            if kind == 'paren' and value == ')':
                raise StopConditionExprError("括号不匹配：多出一个 ')'")
            if kind == 'id':
                raise StopConditionExprError(
                    f"标识符 '{value}' 前缺少运算符（and / or）")
            raise StopConditionExprError(f"表达式在 '{value}' 处无法继续解析")
        return node

    def _parse_or(self) -> ExprNode:
        node = self._parse_and()
        while True:
            token = self._peek()
            if token is None or token[:2] != ('op', 'or'):
                return node
            self._next()
            node = ('or', node, self._parse_and())

    def _parse_and(self) -> ExprNode:
        node = self._parse_not()
        while True:
            token = self._peek()
            if token is None or token[:2] != ('op', 'and'):
                return node
            self._next()
            node = ('and', node, self._parse_not())

    def _parse_not(self) -> ExprNode:
        token = self._peek()
        if token is not None and token[:2] == ('op', 'not'):
            self._next()
            return ('not', self._parse_not())
        return self._parse_atom()

    def _parse_atom(self) -> ExprNode:
        token = self._next()
        if token is None:
            raise StopConditionExprError("表达式意外结束：运算符缺少操作数")
        kind, value, _pos = token
        if kind == 'id':
            return ('id', self._check_id(value))
        if kind == 'paren':
            if value == '(':
                try:
                    node = self._parse_or()
                except StopConditionExprError:
                    # 输入已到末尾 → 真正的问题是括号没闭合，报这个更贴近用户意图
                    # （否则会落到内层「运算符缺少操作数」上，指错了地方）
                    if self._peek() is None:
                        raise StopConditionExprError("括号不匹配：缺少 ')'")
                    raise
                closing = self._next()
                if closing is None or closing[:2] != ('paren', ')'):
                    raise StopConditionExprError("括号不匹配：缺少 ')'")
                return node
            raise StopConditionExprError("表达式以 ')' 开头")
        if value == 'not':
            raise StopConditionExprError("运算符 'not' 缺少操作数")
        raise StopConditionExprError(f"运算符 '{value}' 缺少左操作数")


def parse_stop_condition_expr(text: str,
                             known_ids: Optional[Set[str]] = None) -> ExprNode:
    """解析条件表达式为 AST。

    Args:
        text: 表达式文本，操作数为条件 id。
        known_ids: 可选——已知条件 id 集合。给出时校验引用，未知名直接报错。

    Returns:
        AST：``('id', name)`` / ``('not', child)`` / ``('and', l, r)`` / ``('or', l, r)``。

    Raises:
        StopConditionExprError: 语法非法或引用了未知 id。消息面向用户可读，
            不含异常栈。
    """
    return _Parser(_tokenize(text or ''),
                   known_ids).parse()


# ══════════════════════════════════════════════════════════════════
# 树 ↔ 表达式双向互转（4d2a）
# ══════════════════════════════════════════════════════════════════

_PRECEDENCE = {'or': 1, 'and': 2, 'not': 3}


def expr_ast_to_text(node: ExprNode, parent_prec: int = 0) -> str:
    """AST → 表达式文本；按优先级只加必要括号。"""
    kind = node[0]
    if kind == 'id':
        return node[1]
    if kind == 'not':
        text = f"not {expr_ast_to_text(node[1], _PRECEDENCE['not'])}"
        return f"({text})" if _PRECEDENCE['not'] < parent_prec else text
    prec = _PRECEDENCE[kind]
    text = (f"{expr_ast_to_text(node[1], prec)} {kind} "
            f"{expr_ast_to_text(node[2], prec + 1)}")
    return f"({text})" if prec < parent_prec else text


def _next_letter_id(used: Set[str]) -> str:
    """分配未占用的短 id（a/b/c…，用尽后退化为 c1/c2…）。"""
    for i in range(26):
        cid = chr(ord('a') + i)
        if cid not in used:
            return cid
    n = 1
    while f'c{n}' in used:
        n += 1
    return f'c{n}'


def tree_to_conditions_and_expr(tree: Optional[Dict[str, Any]]):
    """条件树 → (条件列表, 表达式文本)。

    条件列表为 ``[{'id': 'a', 'type': ..., ...参数}, ...]``，叶子按**深度优先
    首次出现顺序**编号（即在表达式中的出现顺序）；表达式为对应的规范化文本。
    ``tree`` 为空时返回 ``([], '')``。

    「单层 + 全同运算符」的树得到 ``a or b or c`` / ``a and b and c`` 形态，供 GUI
    的「任一满足 / 全部满足」单选识别。
    """
    if not tree:
        return [], ''

    conditions: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any]) -> ExprNode:
        children = node.get('conditions') if isinstance(node, dict) else None
        if children is None:
            cid = _next_letter_id({c['id'] for c in conditions})
            conditions.append({'id': cid, **node})
            return ('id', cid)
        if node.get('mode') == 'not':
            if len(children) != 1:
                raise StopConditionExprError(
                    f"否定节点（mode='not'）恰带一个子节点，当前 {len(children)} 个")
            return ('not', walk(children[0]))
        mode = node.get('mode')
        if mode not in ('any', 'all'):
            raise StopConditionExprError(
                f"复合节点的 mode 须为 'any' / 'all' / 'not'，收到 {mode!r}")
        if not children:
            raise StopConditionExprError("复合节点的 conditions 不得为空")
        op = 'or' if mode == 'any' else 'and'
        acc = walk(children[0])
        for child in children[1:]:
            acc = (op, acc, walk(child))
        return acc

    ast = walk(tree)
    return conditions, expr_ast_to_text(ast)


def _ast_to_tree(node: ExprNode, by_id: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """AST → 条件树。

    **同运算符的链会被拉平为单个 n 叉节点**（``a or b or c`` → 一个 3 子节点的
    ``any``）。这是结合律等价的规范化：不拉平则往返会得到左嵌套结构，与原始树
    结构不等（语义等价但结构不同）。
    """
    kind = node[0]
    if kind == 'id':
        cond = by_id[node[1]]
        return {k: v for k, v in cond.items() if k != 'id'}
    if kind == 'not':
        return {'mode': 'not', 'conditions': [_ast_to_tree(node[1], by_id)]}

    children: List[Dict[str, Any]] = []

    def collect(n: ExprNode) -> None:
        if n[0] == kind:
            collect(n[1])
            collect(n[2])
        else:
            children.append(_ast_to_tree(n, by_id))

    collect(node)
    return {'mode': 'any' if kind == 'or' else 'all', 'conditions': children}


def expr_to_tree(text: str,
                 conditions: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """表达式 + 条件列表 → 条件树。

    ``text`` 为空时返回 ``None``（空树 = 仅引擎硬边界收口，与 5.6 的空树规范化
    同口径）。表达式引用了列表中不存在的 id 时抛 ``StopConditionExprError``。
    """
    if not text or not text.strip():
        return None
    by_id = {c['id']: c for c in conditions}
    ast = parse_stop_condition_expr(text, known_ids=set(by_id))
    return _ast_to_tree(ast, by_id)


# ══════════════════════════════════════════════════════════════════
# 引用完整性纯函数（4d3）
# ══════════════════════════════════════════════════════════════════


def _validate_expr(expr: str, conditions: List[Dict[str, Any]]) -> List[str]:
    """表达式侧：语法 + 引用的 id 是否都在条件列表中。"""
    text = (expr or '').strip()
    if not text:
        return []
    known = {c['id'] for c in conditions}
    try:
        referenced = _collect_ids(text)
    except StopConditionExprError as exc:
        return [str(exc)]
    dangling = [rid for rid in referenced if rid not in known]
    if dangling:
        return ["以下条件已被删除，但仍被表达式引用："
                + '、'.join(f"'{d}'" for d in dangling)]
    return []


def _collect_ids(expr: str) -> List[str]:
    """收集表达式引用的条件 id（去重、保序）。语法非法时抛 StopConditionExprError。"""
    found: List[str] = []

    def walk(node: ExprNode) -> None:
        if node[0] == 'id':
            if node[1] not in found:
                found.append(node[1])
        elif node[0] == 'not':
            walk(node[1])
        else:
            walk(node[1])
            walk(node[2])

    walk(parse_stop_condition_expr(expr))
    return found


def _validate_tree(tree: Optional[Dict[str, Any]]) -> List[str]:
    """条件树侧：结构合法性（落盘形态，TOML 只存条件树）。

    校三件事：节点形态（有无 conditions / mode 取值）、否定节点的子节点数、
    叶子节点的 type 是否已注册。另并入 `stop_condition_shape_issues` 的两类形态
    问题（未声明叶子键、`mode` 缺 `conditions`）——本函数是保存闸门，返回值即
    阻断项，故两者都在此可见。
    """
    if not tree:
        return []
    from .stop_condition import (
        STOP_CONDITION_REGISTRY, stop_condition_shape_issues,
    )

    errors: List[str] = list(stop_condition_shape_issues(tree))

    def walk(node: Any, path: str) -> None:
        if not isinstance(node, dict):
            errors.append(f"{path}：节点必须是表（dict），收到 {type(node).__name__}")
            return
        children = node.get('conditions')
        if children is None:
            node_type = node.get('type')
            if node_type is None:
                # `mode` 在场而缺 `conditions` 属未规定的第四形态，已由
                # stop_condition_shape_issues 给出贴题讯息（缺的是 conditions），
                # 此处不再补一条指向 type 的误导性讯息。
                if 'mode' not in node:
                    errors.append(f"{path}：叶子节点缺少 type 键")
            elif node_type not in STOP_CONDITION_REGISTRY:
                errors.append(f"{path}：未知的停止条件类型 '{node_type}'")
            return
        if not isinstance(children, list):
            errors.append(f"{path}：conditions 必须是数组")
            return
        mode = node.get('mode')
        if mode == 'not':
            if len(children) != 1:
                errors.append(
                    f"{path}：否定节点（mode='not'）恰带一个子节点，当前 {len(children)} 个")
            for i, child in enumerate(children):
                walk(child, f"{path}.conditions[{i}]")
            return
        if mode not in ('any', 'all'):
            errors.append(f"{path}：复合节点的 mode 须为 'any' / 'all' / 'not'，收到 {mode!r}")
            return
        if not children:
            errors.append(f"{path}：复合节点的 conditions 不得为空")
            return
        for i, child in enumerate(children):
            walk(child, f"{path}.conditions[{i}]")

    walk(tree, 'stop_condition')
    return errors


def validate_stop_condition_config(
    tree: Optional[Dict[str, Any]] = None,
    expr: Optional[str] = None,
    conditions: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    """停止条件配置的引用完整性与结构校验；返回错误列表（空 = 通过）。

    **本函数是唯一实现点**：``config_panel.validate_banners()`` 与
    ``webui/api.py:_validate_store`` 必须共同调用它，不得各自复刻
    （WebUI 的保存校验原本就是 validate_banners 的独立复刻，只有 ``store``，
    拿不到面板内存态，导致「删除仍被表达式引用的 id → 保存阻断」在 WebUI 侧落空）。

    两类输入对应两种调用形态：

    - GUI（编辑期内存态）：传 ``expr`` + ``conditions``——表达式是组合的真相源
    - WebUI / 落盘形态：传 ``tree``——TOML 只存条件树，无表达式

    函数是**全函数**（不抛异常）：输入非法时把问题作为错误项返回。
    """
    errors: List[str] = []
    if tree is not None:
        errors.extend(_validate_tree(tree))
    if expr is not None:
        errors.extend(_validate_expr(expr, conditions or []))
    return errors
