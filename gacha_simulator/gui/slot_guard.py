"""Qt 槽异常守卫（2026-10-01）。

**为什么需要**：从 C++ 事件循环调进 Python 槽的异常，PyQt6 的默认处置是调
``qFatal()`` 直接中止进程。本机实测（PyQt6 6.11.0 / Qt 6.11.0 / Python 3.12.5，
用真实 ``pyqtSignal`` 加槽复现）：槽内抛 ``RuntimeError`` 时进程以
``returncode 0xC0000409``（STATUS_STACK_BUFFER_OVERRUN，即 abort）消失，
**stdout/stderr 全空，连 traceback 都不打印**。用户在界面上看到的是「窗口不见了」，
而一次已经跑完、正准备落库的模拟结果随之丢失。

``main.py`` 装的全局 ``sys.excepthook`` 是兜底网（实测装了之后 traceback 正常打印、
``app.exec()`` 返回 0、进程存活），但它只保证「进程不死」，不说明哪一步失败、结果
还在不在。装饰在具体槽上才能给出与上下文相符的说明，故**两层都要**：全局网覆盖
所有未装饰的槽，装饰器管住最要紧的那几个。

用法::

    from gacha_simulator.gui.slot_guard import guarded_slot

    @guarded_slot
    def on_simulation_finished(self, result_bundle):
        ...
"""

from __future__ import annotations

import functools
import sys
import traceback


def _report(owner, method_name: str) -> None:
    """把刚发生的槽异常报出去：先 stderr，再界面弹窗。

    弹出前有两道判断（都失败则静默返回，绝不二次抛出）：QApplication 存在、
    且当前在主线程。非主线程弹 ``QMessageBox`` 会再抛一次，那就等于没有守卫。
    """
    text = traceback.format_exc()
    # 从终端启动时可见；打包后无控制台则自然丢弃（故不能只靠这一条）
    print(f"\n[槽异常] {method_name}\n{text}", file=sys.stderr, flush=True)
    try:
        from PyQt6.QtCore import QThread
        from PyQt6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance()
        if app is None or QThread.currentThread() != app.thread():
            return
        last_line = text.strip().splitlines()[-1] if text.strip() else '（无 traceback）'
        QMessageBox.critical(
            owner,
            '发生未预期的错误',
            '程序遇到了一个未处理的错误，但**仍在运行**。\n\n'
            '刚才那一步可能没有生效（例如结果没能存进数据集、界面没能刷新），'
            '请检查后重试。\n\n'
            f'{last_line}',
        )
    except Exception:
        # 报告本身失败不得再抛：二次异常会重新触发 qFatal，等于没有守卫
        pass


def guarded_slot(method):
    """装饰 Qt 槽：把异常就地接住并报告，不让它冒回 C++ 事件循环。

    **只包异常，不改任何正常路径的行为**：无异常时与未装饰逐字节等价。
    """
    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except Exception:
            owner = args[0] if args else None
            _report(owner, getattr(method, '__qualname__', getattr(method, '__name__', '?')))
    return wrapper
