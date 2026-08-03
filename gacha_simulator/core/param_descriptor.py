"""策略参数描述符——纯数据类，零 Qt 依赖。

ParamDescriptor 定义策略参数的元数据（类型、范围、默认值、显示名），
不包含任何 GUI 概念。Widget 创建逻辑全部在 gui/param_renderer.py 中。

CLI 模式下 import 此模块不需要 PyQt6。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


class ParamDescriptor(ABC):
    """参数描述符基类——定义 validate() 契约。"""

    @abstractmethod
    def validate(self, value: Any) -> Any:
        """校验并返回规范化的值。非法值抛出 ValueError。"""
        ...


@dataclass
class FloatParam(ParamDescriptor):
    """浮点参数——带范围的连续数值。"""

    key: str
    display_name: str
    default: float = 0.0
    min_val: float = 0.0
    max_val: float = 99999.0

    def validate(self, value: Any) -> float:
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"参数 '{self.key}' ({self.display_name}) 需要浮点数，"
                f"收到: {value!r}"
            )
        if not (self.min_val <= v <= self.max_val):
            raise ValueError(
                f"参数 '{self.key}' ({self.display_name}) 值 {v} 超出范围 "
                f"[{self.min_val}, {self.max_val}]"
            )
        return v


@dataclass
class IntParam(ParamDescriptor):
    """整数参数——带范围的离散数值。"""

    key: str
    display_name: str
    default: int = 0
    min_val: int = 0
    max_val: int = 99999

    def validate(self, value: Any) -> int:
        # 允许浮点数形式的整数值（如 10.0），但必须是精确整数
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"参数 '{self.key}' ({self.display_name}) 需要整数，"
                f"收到: {value!r}"
            )
        if v != int(v):
            raise ValueError(
                f"参数 '{self.key}' ({self.display_name}) 需要整数，"
                f"收到浮点数: {value!r}"
            )
        iv = int(v)
        if not (self.min_val <= iv <= self.max_val):
            raise ValueError(
                f"参数 '{self.key}' ({self.display_name}) 值 {iv} 超出范围 "
                f"[{self.min_val}, {self.max_val}]"
            )
        return iv


@dataclass
class BoolParam(ParamDescriptor):
    """布尔参数——开关标志。"""

    key: str
    display_name: str
    default: bool = False

    def validate(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ('true', '1', 'yes', 'on'):
                return True
            if lowered in ('false', '0', 'no', 'off', ''):
                return False
        raise ValueError(
            f"参数 '{self.key}' ({self.display_name}) 需要布尔值，"
            f"收到: {value!r}"
        )


@dataclass
class StrParam(ParamDescriptor):
    """字符串参数——自由文本输入，无枚举约束。"""

    key: str
    display_name: str
    default: str = ''

    def validate(self, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError(
                f"参数 '{self.key}' ({self.display_name}) 需要字符串，"
                f"收到: {type(value).__name__} = {value!r}"
            )
        return value


@dataclass
class StringListParam(ParamDescriptor):
    """字符串列表参数。"""

    key: str
    display_name: str
    default: List[str] = field(default_factory=list)

    def validate(self, value: Any) -> List[str]:
        if isinstance(value, str):
            # 支持以逗号/空格分隔的字符串输入
            import re
            parts = re.split(r'[,\s]+', value.strip())
            return [p for p in parts if p]
        if isinstance(value, (list, tuple, set)):
            result = []
            for item in value:
                if not isinstance(item, str):
                    raise ValueError(
                        f"参数 '{self.key}' ({self.display_name}) 列表元素需为字符串，"
                        f"收到: {item!r}"
                    )
                result.append(item)
            return result
        raise ValueError(
            f"参数 '{self.key}' ({self.display_name}) 需要字符串列表，"
            f"收到: {type(value).__name__} = {value!r}"
        )


@dataclass
class PoolIntMapParam(ParamDescriptor):
    """池子→整数映射参数（如 pool_quotas）——严格校验。

    非法条目抛出 ValueError（非静默丢弃）。
    """

    key: str
    display_name: str
    default: Dict[str, int] = field(default_factory=dict)

    def validate(self, value: Any) -> Dict[str, int]:
        if isinstance(value, str):
            # 支持 JSON 格式字符串输入
            import json
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValueError(
                    f"参数 '{self.key}' ({self.display_name}) 无法解析为 JSON: {value!r}"
                )
        if not isinstance(value, dict):
            raise ValueError(
                f"参数 '{self.key}' ({self.display_name}) 需要字典（池子→数量），"
                f"收到: {type(value).__name__} = {value!r}"
            )
        result: Dict[str, int] = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValueError(
                    f"参数 '{self.key}' ({self.display_name}) 键需为字符串（池子ID），"
                    f"收到: {k!r}"
                )
            try:
                iv = int(v)
            except (TypeError, ValueError):
                raise ValueError(
                    f"参数 '{self.key}' ({self.display_name}) 值需为整数（数量），"
                    f"键 '{k}' 的值: {v!r}"
                )
            if iv < 0:
                raise ValueError(
                    f"参数 '{self.key}' ({self.display_name}) 值不能为负，"
                    f"键 '{k}' = {iv}"
                )
            result[k] = iv
        return result


# 类型→类映射，供 param_renderer.py 分派表使用
PARAM_TYPE_MAP: Dict[str, type] = {
    'float': FloatParam,
    'int': IntParam,
    'bool': BoolParam,
    'str': StrParam,
    'string_list': StringListParam,
    'pool_int_map': PoolIntMapParam,
}
