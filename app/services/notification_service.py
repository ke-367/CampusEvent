"""通知服务（观察者）：把“报名事实”翻译为面向学生的消息，并投递到多个渠道。

关键设计：
  1. NotificationService 只订阅领域事件，不参与报名业务判断——报名与通知解耦。
  2. 投递记录写在 notifications 表（event_key + channel 唯一索引）——
     同一事件重复投递会被忽略，避免重复通知（例如重试、重复点击）。
  3. 通知失败逐渠道捕获并留痕（notification_failures），且发生在业务事务提交之后，
     因此不会让已经合法提交的报名记录消失。
"""
from __future__ import annotations

from dataclasses import dataclass


from typing import Protocol

from ..domain.entities import Student
from ..domain.events import (
    DomainEvent,
    RegistrationApproved,
    RegistrationCancelled,
    RegistrationRejected,
    RegistrationSubmitted,
)


@dataclass(frozen=True)
class NotificationPayload:
    student: Student
    registration_id: int | None
    event_key: str
    title: str
    body: str


class NotificationChannel(Protocol):
    name: str

    def deliver(self, payload: NotificationPayload, messages) -> bool:
        """投递一次；返回 True 表示本次确实投递（False 表示已投递过而被跳过）。"""


class InAppChannel:
    """站内消息：写入 notifications 表，学生端“我的消息”可见。"""

    name = "inapp"

    def deliver(self, payload: NotificationPayload, messages) -> bool:
        return messages.add_if_absent(
            student_id=payload.student.id,
            registration_id=payload.registration_id,
            channel=self.name,
            event_key=payload.event_key,
            title=payload.title,
            body=payload.body,
        )


class NotificationService:
    def __init__(self, *, message_repo_factory, channels, failure_recorder, outbox_dir: str):
        self._message_repo_factory = message_repo_factory
        self._channels = list(channels)
        self._failure_recorder = failure_recorder
        self._outbox_dir = outbox_dir

    # ---- 观察者接口 ----
    def handle(self, event: DomainEvent) -> None:
        payload = self._build_payload(event)
        if payload is None:
            return
        messages = self._message_repo_factory()
        for channel in self._channels:
            try:
                channel.deliver(payload, messages)
            except Exception as exc:
                # 单渠道失败：留痕后继续（通知失败绝不影响已提交的报名）
                self._failure_recorder(payload.event_key, channel.name, repr(exc))

    # ---- 事件 → 消息文案 ----
    def _build_payload(self, event: DomainEvent) -> NotificationPayload | None:
        if event.activity is None or event.student is None:
            return None
        activity = event.activity
        start = activity.start_time.strftime("%Y-%m-%d %H:%M")

        if isinstance(event, RegistrationSubmitted):
            if event.registration.status == "approved":
                title = "报名成功"
                body = (
                    f"你已成功报名活动「{activity.title}」（{start}，{activity.location}）。"
                    f"名额占用情况以活动详情为准。"
                )
            else:
                title = "报名已提交，等待审核"
                body = (
                    f"你对活动「{activity.title}」的报名已提交，当前状态为待审核，"
                    f"审批结果将通过站内消息通知你。"
                )
        elif isinstance(event, RegistrationApproved):
            title = "报名审核通过"
            body = f"恭喜，活动「{activity.title}」（{start}，{activity.location}）的报名已审核通过。"
        elif isinstance(event, RegistrationRejected):
            reason = f"，原因：{event.reason}" if getattr(event, "reason", "") else ""
            title = "报名未通过"
            body = f"很遗憾，活动「{activity.title}」的报名未通过审核{reason}。"
        elif isinstance(event, RegistrationCancelled):
            title = "报名已取消"
            body = f"你已取消活动「{activity.title}」的报名，名额已释放。"
        else:
            return None

        return NotificationPayload(
            student=event.student,
            registration_id=event.registration.id,
            event_key=event.event_key,
            title=title,
            body=body,
        )

