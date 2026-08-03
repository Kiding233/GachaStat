"""轻量同步通知机制，P61 与 P58 的共享解耦层（P61 Ph0 交付）。

Notifier 不是事件溯源，不存储事件日志。emit() 按 priority 升序同步调用全部
订阅者，返回时所有 handler 已执行完毕。P61（生命周期检查，priority=1）与
P58（里程碑资源注入，priority=0）通过订阅同一事件协作，互不 import 对方模块。
"""

from typing import Callable, Dict, List, Tuple


class Notifier:
    """轻量同步通知机制，不是事件溯源，不存储事件日志。"""

    def __init__(self) -> None:
        # { event_type: [(priority, handler), ...] }
        self._subscribers: Dict[str, List[Tuple[int, Callable]]] = {}

    def subscribe(self, event_type: str, handler: Callable, priority: int = 0) -> None:
        """注册订阅者。priority 越小越先执行。"""
        handlers = self._subscribers.setdefault(event_type, [])
        handlers.append((priority, handler))
        handlers.sort(key=lambda item: item[0])

    def emit(self, event_type: str, **data) -> None:
        """同步分发，按 priority 升序遍历，逐个调用，全部完成才返回。"""
        for _priority, handler in self._subscribers.get(event_type, []):
            handler(**data)
