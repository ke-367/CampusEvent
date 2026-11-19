"""事件总线：观察者模式的最小组件。

业务服务只负责 publish(业务事实)，不关心谁订阅、订阅方是站内信还是邮件。
订阅方异常由 on_error 回调统一处理：业务事务已提交，通知失败只能留痕，不能回滚报名。
"""
from __future__ import annotations

from typing import Callable, Protocol

from .events import DomainEvent


class EventHandler(Protocol):
    def handle(self, event: DomainEvent) -> None: ...


ErrorListener = Callable[[DomainEvent, EventHandler, Exception], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []
        self._error_listener: ErrorListener | None = None

    def subscribe(self, handler: EventHandler) -> None:
        if handler not in self._handlers:
            self._handlers.append(handler)

    def unsubscribe(self, handler: EventHandler) -> None:
        if handler in self._handlers:
            self._handlers.remove(handler)

    def set_error_listener(self, listener: ErrorListener | None) -> None:
        self._error_listener = listener

    @property
    def subscriber_count(self) -> int:
        return len(self._handlers)

    def publish(self, event: DomainEvent) -> None:
        """同步通知全部订阅方；单个订阅方失败不阻断其他订阅方。"""
        for handler in list(self._handlers):
            try:
                handler.handle(event)
            except Exception as exc:  # 通知失败不能让已提交的报名“消失”
                if self._error_listener is None:
                    raise
                self._error_listener(event, handler, exc)
