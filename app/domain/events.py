"""领域事件：描述“业务上已经发生的事实”，供订阅方（通知）消费。

事件在业务事务提交后发布，因此订阅方的失败不会回滚已提交的业务数据。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .entities import Activity, Registration, Student


@dataclass(frozen=True)
class DomainEvent:
    name: str = "domain-event"
    occurred_at: datetime = None  # 由具体事件填充

    @property
    def event_key(self) -> str:
        """幂等键：同一业务事实只应触发一次通知。"""
        raise NotImplementedError


@dataclass(frozen=True)
class RegistrationSubmitted(DomainEvent):
    registration: Registration = None
    activity: Activity = None
    student: Student = None
    name: str = "registration-submitted"

    @property
    def event_key(self) -> str:
        return f"submitted:{self.registration.id}:{self.registration.status}"


@dataclass(frozen=True)
class RegistrationApproved(DomainEvent):
    registration: Registration = None
    activity: Activity = None
    student: Student = None
    name: str = "registration-approved"

    @property
    def event_key(self) -> str:
        return f"approved:{self.registration.id}"


@dataclass(frozen=True)
class RegistrationRejected(DomainEvent):
    registration: Registration = None
    activity: Activity = None
    student: Student = None
    reason: str = ""
    name: str = "registration-rejected"

    @property
    def event_key(self) -> str:
        return f"rejected:{self.registration.id}"


@dataclass(frozen=True)
class RegistrationCancelled(DomainEvent):
    registration: Registration = None
    activity: Activity = None
    student: Student = None
    name: str = "registration-cancelled"

    @property
    def event_key(self) -> str:
        return f"cancelled:{self.registration.id}"


@dataclass(frozen=True)
class RegistrationWaitlisted(DomainEvent):
    """候补入队（v2 新增事件）。"""

    registration: Registration = None
    activity: Activity = None
    student: Student = None
    name: str = "registration-waitlisted"

    @property
    def event_key(self) -> str:
        return f"waitlisted:{self.registration.id}"


@dataclass(frozen=True)
class RegistrationPromoted(DomainEvent):
    """候补转正（v2 新增事件）：由候补队列自动转为已通过。"""

    registration: Registration = None
    activity: Activity = None
    student: Student = None
    name: str = "registration-promoted"

    @property
    def event_key(self) -> str:
        return f"promoted:{self.registration.id}"
