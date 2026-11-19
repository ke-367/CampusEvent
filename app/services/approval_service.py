"""审批服务（管理员侧）：审核型报名的批准/拒绝，批准时再次检查名额。"""
from __future__ import annotations

from datetime import datetime

from ..db import transaction
from ..domain.entities import Registration
from ..domain.errors import IllegalStatusTransitionError, NotFoundError
from ..domain.event_bus import EventBus
from ..domain.events import RegistrationApproved, RegistrationRejected
from ..domain.rules import CapacityRule
from ..repositories import ActivityRepository, RegistrationRepository, StudentRepository


class ApprovalService:
    def __init__(
        self,
        conn,
        activities: ActivityRepository,
        registrations: RegistrationRepository,
        students: StudentRepository,
        capacity_rule: CapacityRule,
        bus: EventBus,
        now_provider=datetime.now,
    ):
        self._conn = conn
        self._activities = activities
        self._registrations = registrations
        self._students = students
        self._capacity = capacity_rule
        self._bus = bus
        self._now = now_provider

    def pending(self):
        """待审核队列（含活动信息），管理端列表使用。"""
        return self._registrations.list_pending()

    def approve(self, registration_id: int, admin_name: str) -> Registration:
        registration = self._require_pending(registration_id)
        activity = self._activities.get(registration.activity_id)
        if activity is None or activity.status != "published":
            raise NotFoundError("活动已下线，无法批准该报名。")

        # 名额属于公共规则，在批准这个“真正占用名额”的时刻再检查一次
        self._capacity.ensure_available(activity, self._registrations)

        student = self._students.get(registration.student_id)
        with transaction(self._conn):
            updated = self._registrations.update_status(
                registration_id, "approved", decided_by=admin_name, remark="管理员批准"
            )
        self._bus.publish(
            RegistrationApproved(
                registration=updated, activity=activity, student=student, occurred_at=self._now()
            )
        )
        return updated

    def reject(self, registration_id: int, admin_name: str, reason: str = "") -> Registration:
        registration = self._require_pending(registration_id)
        activity = self._activities.get(registration.activity_id)
        student = self._students.get(registration.student_id)
        with transaction(self._conn):
            updated = self._registrations.update_status(
                registration_id, "rejected", decided_by=admin_name,
                remark=reason or "管理员拒绝",
            )
        self._bus.publish(
            RegistrationRejected(
                registration=updated, activity=activity, student=student,
                reason=reason, occurred_at=self._now(),
            )
        )
        return updated

    def _require_pending(self, registration_id: int) -> Registration:
        registration = self._registrations.get(registration_id)
        if registration is None:
            raise NotFoundError("报名记录不存在。")
        if registration.status != "pending":
            raise IllegalStatusTransitionError(
                f"该报名当前为「{registration.status_label}」，不能重复审批。"
            )
        return registration
