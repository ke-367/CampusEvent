"""通知服务（观察者）：把“报名事实”翻译为面向学生的消息，并投递到多个渠道。

关键设计：
  1. NotificationService 只订阅领域事件，不参与报名业务判断——报名与通知解耦。
  2. 投递记录写在 notifications 表（event_key + channel 唯一索引）——
     同一事件重复投递会被忽略，避免重复通知（例如重试、重复点击）。
  3. 通知失败逐渠道捕获并留痕（notification_failures），且发生在业务事务提交之后，
     因此不会让已经合法提交的报名记录消失。

需求变更（CR-02）：新增邮件通知渠道。渠道以 NotificationChannel 接口接入，
NotificationService 只多了一个“遍历渠道”的动作，后续再加短信/企业微信渠道同理。
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ..domain.entities import Student
from ..domain.events import (
    DomainEvent,
    RegistrationApproved,
    RegistrationCancelled,
    RegistrationPromoted,
    RegistrationRejected,
    RegistrationSubmitted,
    RegistrationWaitlisted,
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


class EmailChannel:
    """邮件渠道（CR-02 新增）：把通知渲染成 .eml 落到 outbox 目录，由本地 MTA 或测试接管。

    课程环境用“落盘 + 可审计”的方式模拟外发邮件：不引入消息队列、不真实联网发信，
    既保证可复现，也避免把真实邮箱口令写进代码或仓库。
    """

    name = "email"

    def __init__(self, outbox_dir: str):
        self._outbox_dir = Path(outbox_dir)

    def deliver(self, payload: NotificationPayload, messages) -> bool:
        if messages.exists(payload.event_key, self.name):
            return False
        self._outbox_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        filename = f"{stamp}_{payload.student.student_no}_{payload.registration_id or 'na'}.eml"
        content = (
            f"To: {payload.student.email}\r\n"
            f"Subject: =?UTF-8?B?{_encode_header(payload.title)}?=\r\n"
            f"Date: {datetime.now().isoformat(timespec='seconds')}\r\n"
            "MIME-Version: 1.0\r\n"
            "Content-Type: text/plain; charset=UTF-8\r\n"
            "Content-Transfer-Encoding: 8bit\r\n\r\n"
            f"{payload.student.name} 同学：\r\n\r\n{payload.body}\r\n\r\n"
            "—— 校园活动报名与管理系统 CampusEvent\r\n"
        )
        (self._outbox_dir / filename).write_text(content, encoding="utf-8")
        # 落盘成功后再登记投递记录，保证“有记录=已投递”，并作为下次去重依据
        messages.add_if_absent(
            student_id=payload.student.id,
            registration_id=payload.registration_id,
            channel=self.name,
            event_key=payload.event_key,
            title=payload.title,
            body=payload.body,
        )
        return True


def _encode_header(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class NotificationService:
    def __init__(self, *, message_repo_factory, channels, failure_recorder, outbox_dir: str):
        self._message_repo_factory = message_repo_factory
        self._channels = list(channels)
        self._failure_recorder = failure_recorder
        self._outbox_dir = outbox_dir

    @property
    def channel_names(self) -> list[str]:
        return [c.name for c in self._channels]

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
        elif isinstance(event, RegistrationWaitlisted):
            title = "已进入候补队列"
            body = (
                f"活动「{activity.title}」名额已满，你当前为候补第 {event.registration.queue_no} 位。"
                "有名额释放时将自动为你转正并通知。"
            )
        elif isinstance(event, RegistrationPromoted):
            title = "候补转正通知"
            body = (
                f"好消息！活动「{activity.title}」（{start}，{activity.location}）出现空余名额，"
                "你已由候补自动转为「已通过」，请按时参加。"
            )
        else:
            return None

        return NotificationPayload(
            student=event.student,
            registration_id=event.registration.id,
            event_key=event.event_key,
            title=title,
            body=body,
        )
