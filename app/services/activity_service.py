"""活动管理服务：发布活动、软删除、列表与统计。"""
from __future__ import annotations

from datetime import datetime

from ..db import transaction
from ..domain.entities import Activity
from ..domain.errors import DomainError, NotFoundError
from ..repositories import ActivityRepository, RegistrationRepository, StudentRepository


class ActivityService:
    def __init__(
        self,
        conn,
        activities: ActivityRepository,
        registrations: RegistrationRepository,
        students: StudentRepository,
        policy_registry,
        now_provider=datetime.now,
    ):
        self._conn = conn
        self._activities = activities
        self._registrations = registrations
        self._students = students
        self._registry = policy_registry
        self._now = now_provider

    # ------------------------------------------------------------------ 查询
    def list_visible(self):
        return self._activities.list_visible()

    def list_all(self):
        return self._activities.list_all()

    def detail(self, activity_id: int):
        activity = self._activities.get(activity_id)
        if activity is None:
            raise NotFoundError("活动不存在。")
        return activity

    def approved_count(self, activity_id: int) -> int:
        return self._registrations.count_by_status(activity_id, ("approved",))

    def stats(self) -> dict:
        all_regs = 0
        for activity in self._activities.list_all():
            all_regs += self._registrations.count_by_status(
                activity.id, ("approved", "pending")
            )
        return {
            "activities": len(self._activities.list_visible()),
            "registrations": all_regs,
            "pending": len(self._registrations.list_pending()),
        }

    # ------------------------------------------------------------------ 发布
    def create(self, form: dict) -> Activity:
        title = (form.get("title") or "").strip()
        if not title:
            raise DomainError("活动名称不能为空。")
        if len(title) > 60:
            raise DomainError("活动名称不能超过 60 个字符。")

        mode = form.get("registration_mode") or "direct"
        if mode not in {m for m, _ in self._registry.supported_modes}:
            raise DomainError("报名规则取值非法。")

        try:
            capacity = int(form.get("capacity") or 0)
        except ValueError:
            raise DomainError("名额必须为整数。") from None
        if capacity <= 0 or capacity > 10000:
            raise DomainError("名额必须在 1~10000 之间。")

        raw_start = (form.get("start_time") or "").strip()
        try:
            start_time = datetime.fromisoformat(raw_start.replace(" ", "T"))
        except ValueError:
            raise DomainError("活动开始时间格式不正确。") from None
        if start_time <= self._now():
            raise DomainError("活动开始时间必须晚于当前时间。")

        with transaction(self._conn):
            activity = self._activities.create(
                title=title,
                description=(form.get("description") or "").strip(),
                category=(form.get("category") or "通用").strip() or "通用",
                location=(form.get("location") or "").strip(),
                start_time=start_time,
                capacity=capacity,
                registration_mode=mode,
                grade_restriction=(form.get("grade_restriction") or "").strip(),
            )
        return activity

    def remove(self, activity_id: int) -> tuple[Activity, int]:
        """软删除：保留历史报名与通知；已存在有效报名时提示影响面。"""
        activity = self._activities.get(activity_id)
        if activity is None:
            raise NotFoundError("活动不存在。")
        affected = len(
            self._registrations.list_by_activity_status(activity_id, ("approved", "pending"))
        )
        with transaction(self._conn):
            self._activities.soft_delete(activity_id)
        return activity, affected
