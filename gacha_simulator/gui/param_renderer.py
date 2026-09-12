"""参数控件渲染器——ParamDescriptor → Qt Widget 自动分派。

P69 §1.5：替代 config_panel._on_strategy_type_changed() 中的 6 分支 if-elif。
类型→控件工厂分派表，纯函数，无状态。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Type

from PyQt6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QLineEdit, QSpinBox, QWidget,
)

from ..core.param_descriptor import (
    BoolParam,
    DictParam,
    FloatParam,
    IntParam,
    ListParam,
    ParamDescriptor,
    PoolIntMapParam,
    StringListParam,
    StrParam,
)

logger = logging.getLogger(__name__)


# ── 类型 → 控件工厂 ──────────────────────────────────────────────


def _make_float_spin(pdesc: FloatParam, parent: Optional[QWidget] = None) -> QDoubleSpinBox:
    widget = QDoubleSpinBox(parent)
    widget.setRange(pdesc.min_val, pdesc.max_val)
    widget.setDecimals(2)
    widget.setSingleStep(0.1)
    widget.setValue(float(pdesc.default))
    return widget


def _make_int_spin(pdesc: IntParam, parent: Optional[QWidget] = None) -> QSpinBox:
    widget = QSpinBox(parent)
    widget.setRange(pdesc.min_val, pdesc.max_val)
    widget.setValue(int(pdesc.default))
    return widget


def _make_checkbox(pdesc: BoolParam, parent: Optional[QWidget] = None) -> QCheckBox:
    widget = QCheckBox(parent)
    widget.setChecked(bool(pdesc.default))
    return widget


def _make_line_edit(pdesc: ParamDescriptor, parent: Optional[QWidget] = None) -> QLineEdit:
    """StrParam / StringListParam / PoolIntMapParam / ListParam / DictParam 共用 QLineEdit。"""
    widget = QLineEdit(parent)
    if isinstance(pdesc, (ListParam, DictParam)):
        # P79 4b3：通用容器以 JSON 文本录入——ListParam 的元素可能是嵌套结构
        # （如 pool_schedules 的 [pool_id, start, end] 三元组），逗号分隔表达不了
        default = pdesc.default
        widget.setText(json.dumps(default, ensure_ascii=False) if default else '')
        widget.setPlaceholderText('JSON')
    elif isinstance(pdesc, StringListParam):
        default = pdesc.default or []
        widget.setText(','.join(str(v) for v in default))
        widget.setPlaceholderText("逗号分隔")
    elif isinstance(pdesc, PoolIntMapParam):
        default = pdesc.default or {}
        widget.setText(','.join(f'{k}:{v}' for k, v in default.items()))
        widget.setPlaceholderText("pool_id:数量,...")
    else:
        widget.setText(str(pdesc.default) if pdesc.default is not None else '')
    return widget


_WIDGET_FACTORY: Dict[Type[ParamDescriptor], Callable] = {
    FloatParam: _make_float_spin,
    IntParam: _make_int_spin,
    BoolParam: _make_checkbox,
    StrParam: _make_line_edit,
    StringListParam: _make_line_edit,
    PoolIntMapParam: _make_line_edit,
    ListParam: _make_line_edit,
    DictParam: _make_line_edit,
}


# ── 公开 API ──────────────────────────────────────────────────────


def render_param_widgets(
    params: List[ParamDescriptor],
    form_layout: QFormLayout,
    widget_map: Dict[str, tuple],
    parent: Optional[QWidget] = None,
) -> List[ParamDescriptor]:
    """根据 ParamDescriptor 列表创建 Qt 控件并添加到表单布局。

    Args:
        params: 策略的参数描述符列表。
        form_layout: 目标 QFormLayout。
        widget_map: 输出——{param_key: (ptype_str, widget)} 映射。
        parent: 控件的父 widget。

    Returns:
        **未能渲染的描述符列表**（``_WIDGET_FACTORY`` 未命中的跳过项）。
        P79 4b3：原实现对未命中项静默 ``continue``——参数无声消失、不报错；
        调用侧应据此在参数区提示「参数 X 无可用控件」。
    """
    skipped: List[ParamDescriptor] = []
    for pdesc in params:
        factory = _WIDGET_FACTORY.get(type(pdesc))
        if factory is None:
            logger.warning("参数 '%s'（%s）无可用控件工厂，已跳过渲染——"
                           "该参数不会出现在界面，也不会被回写",
                           pdesc.key, pdesc.display_name)
            skipped.append(pdesc)
            continue

        widget = factory(pdesc, parent)
        form_layout.addRow(f"{pdesc.display_name}:", widget)

        # 推导 ptype 字符串（兼容 _get_strategy_params_from_widgets 的字符串分派）
        if isinstance(pdesc, IntParam):
            ptype = 'int'
        elif isinstance(pdesc, FloatParam):
            ptype = 'float'
        elif isinstance(pdesc, BoolParam):
            ptype = 'bool'
        elif isinstance(pdesc, StringListParam):
            ptype = 'string_list'
        elif isinstance(pdesc, PoolIntMapParam):
            ptype = 'pool_int_map'
        elif isinstance(pdesc, ListParam):
            ptype = 'list'
        elif isinstance(pdesc, DictParam):
            ptype = 'dict'
        else:
            ptype = 'str'

        widget_map[pdesc.key] = (ptype, widget)

    return skipped


def collect_params_from_widgets(widget_map: Dict[str, tuple]) -> Dict[str, Any]:
    """从控件映射中收集用户输入的参数值。

    Args:
        widget_map: {param_key: (ptype_str, widget)} 映射。

    Returns:
        {param_key: value} dict。
    """
    params: Dict[str, Any] = {}
    for param_key, (ptype, widget) in widget_map.items():
        if ptype == 'int':
            params[param_key] = widget.value()
        elif ptype == 'float':
            params[param_key] = widget.value()
        elif ptype == 'bool':
            params[param_key] = widget.isChecked()
        elif ptype == 'string_list':
            text = widget.text().strip()
            params[param_key] = [s.strip() for s in text.split(',') if s.strip()] if text else []
        elif ptype == 'pool_int_map':
            text = widget.text().strip()
            result: Dict[str, int] = {}
            if text:
                for part in text.split(','):
                    part = part.strip()
                    if ':' in part:
                        k, v = part.split(':', 1)
                        try:
                            result[k.strip()] = int(v.strip())
                        except ValueError:
                            pass
            params[param_key] = result
        elif ptype in ('list', 'dict'):
            # P79 4b3：新增的 list / dict 若不进入本分派，读取时会静默变成裸字符串
            # （容器语义丢失且不报错）。空输入按容器空值处理；JSON 解析失败时原样
            # 返回文本串——ListParam / DictParam 的 validate() 本身接受 JSON 字符串，
            # 故错误会在校验层显式暴露，不静默退化。
            text = widget.text().strip()
            if not text:
                params[param_key] = [] if ptype == 'list' else {}
            else:
                try:
                    params[param_key] = json.loads(text)
                except json.JSONDecodeError:
                    params[param_key] = text
        else:
            params[param_key] = widget.text().strip()
    return params


def set_params_to_widgets(
    params: List[ParamDescriptor],
    widget_map: Dict[str, tuple],
    values: Dict[str, Any],
) -> None:
    """将参数值回填到控件中。

    Args:
        params: 策略的参数描述符列表。
        widget_map: {param_key: (ptype_str, widget)} 映射。
        values: {param_key: value} dict。
    """
    for pdesc in params:
        entry = widget_map.get(pdesc.key)
        if entry is None:
            continue
        ptype, widget = entry
        val = values.get(pdesc.key, pdesc.default)

        if ptype in ('int', 'float'):
            widget.setValue(float(val) if val is not None else pdesc.default)
        elif ptype == 'bool':
            widget.setChecked(bool(val) if val is not None else pdesc.default)
        elif ptype == 'string_list':
            if isinstance(val, list):
                widget.setText(','.join(str(v) for v in val))
            else:
                widget.setText(str(val) if val else '')
        elif ptype == 'pool_int_map':
            if isinstance(val, dict):
                widget.setText(','.join(f'{k}:{v}' for k, v in val.items()))
            else:
                widget.setText(str(val) if val else '')
        elif ptype in ('list', 'dict'):
            if isinstance(val, (list, dict)):
                widget.setText(json.dumps(val, ensure_ascii=False) if val else '')
            elif val is None:
                widget.setText('')
            else:
                widget.setText(str(val))
        else:
            widget.setText(str(val) if val is not None else '')
