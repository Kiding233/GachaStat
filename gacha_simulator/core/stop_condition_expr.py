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
from typing import List, Optional, Set, Tuple

__all__ = [
    'StopConditionExprError',
    'parse_stop_condition_expr',
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
                node = self._parse_or()
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
