"""报名业务服务：公共规则的唯一把关点 + 委派策略决定准入结论。

不变量（与报名规则无关，所有活动都成立）：
  1. 活动未删除、尚未开始；
  2. 同一学生对同一活动最多一条“待审核/已通过”的有效报名；
  3. 报名记录与通知解耦：先提交业务事务，再发布事件。
"""
from __future__ import annotations

from datetime import datetime

from ..db import transaction
from ..domain.entities import Activity, Registration, Student
from ..domain.errors import (
    ActivityClosedError,
    DuplicateRegistrationError,
    IllegalStatusTransitionError,
    NotFoundError,
)
from ..domain.event_bus import EventBus
from ..domain.events import RegistrationCancelled, RegistrationSubmitted, RegistrationWaitlisted
from ..domain.policies import PolicyRegistry, SubmissionContext
from ..domain.rules import CapacityRule
from ..repositories import ActivityRepository, RegistrationRepository


class RegistrationService:
    def __init__(
        self,
        conn,
        activities: ActivityRepository,
        registrations: RegistrationRepository,
        registry: PolicyRegistry,
        bus: EventBus,
        capacity_rule: CapacityRule,
        now_provider=datetime.now,
    ):
        self._conn = conn
        self._activities = activities
        self._registrations = registrations
        self._registry = registry
        self._bus = bus
        self._capacity = capacity_rule
        self._now = now_provider

    # ------------------------------------------------------------------ 报名
    def register(self, activity_id: int, student: Student) -> tuple[Registration, str]:
        activity = self._require_activity(activity_id)
        now = self._now()
        if not activity.is_open(now):
            raise ActivityClosedError(f"活动「{activity.title}」已开始或已下线，无法报名。")

        existing = self._registrations.find_active(activity_id, student.id)
        if existing is not None:
            raise DuplicateRegistrationError(
                f"你对活动「{activity.title}」已有一条「{existing.status_label}」的报名，"
                "不能重复提交。"
            )

        policy = self._registry.for_mode(activity.registration_mode)
        decision = policy.submit(
            SubmissionContext(
                activity=activity,
                student=student,
                registrations=self._registrations,
                capacity_rule=self._capacity,
                now=now,
            )
        )

        with transaction(self._conn):
            registration = self._registrations.create(
                activity_id=activity.id,
                student_id=student.id,
                status=decision.status,
                policy_key=policy.key,
                queue_no=decision.queue_no,
            )

        # 事务已提交，此时发布事件：通知失败不影响报名记录
        event_cls = (
            RegistrationWaitlisted
            if registration.status == "waitlisted"
            else RegistrationSubmitted
        )
        self._bus.publish(
            event_cls(
                registration=registration, activity=activity, student=student, occurred_at=now
            )
        )
        return registration, decision.message

    # ------------------------------------------------------------------ 取消
    def cancel(self, registration_id: int, student: Student) -> Registration:
        registration = self._registrations.get(registration_id)
        if registration is None:
            raise NotFoundError("报名记录不存在。")
        if registration.student_id != student.id:
            raise NotFoundError("报名记录不存在。")   # 不泄露他人报名信息
        if not registration.is_active:
            raise IllegalStatusTransitionError(
                f"「{registration.status_label}」的报名不能取消。"
            )

        activity = self._require_activity(registration.activity_id)
        with transaction(self._conn):
            updated = self._registrations.update_status(
                registration_id, "cancelled",
                decided_by=student.name, remark="学生本人取消",
            )
        self._bus.publish(
            RegistrationCancelled(
                registration=updated, activity=activity, student=student,
                occurred_at=self._now(),
            )
        )
        return updated

    # ------------------------------------------------------------------ 查询
    def my_registrations(self, student_id: int):
        return self._registrations.list_by_student(student_id)

    def registrations_of(self, activity_id: int, statuses: tuple[str, ...] = ("approved",)):
        return self._registrations.list_by_activity_status(activity_id, statuses)

    def capacity_of(self, activity: Activity):
        return self._capacity.snapshot(activity, self._registrations)

    # ------------------------------------------------------------------ 内部
    def _require_activity(self, activity_id: int) -> Activity:
        activity = self._activities.get(activity_id)
        if activity is None or activity.status != "published":
            raise NotFoundError("活动不存在或已下线。")
        return activity
