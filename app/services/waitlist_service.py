"""候补转正服务（需求变更 CR-01 新增）。

它是事件总线的第二个订阅者：监听“报名取消”，把释放出的名额按候补顺序转正。

为什么不在 RegistrationService.cancel 里直接写转正逻辑：
    报名取消与候补转正是两件不同的事，后者是变更需求带来的新规则。
    用订阅的方式接入，baseline-v1 的核心业务代码一行都不用改（可对照 git diff 验证）。
"""
from __future__ import annotations

from datetime import datetime

from ..db import transaction
from ..domain.entities import Registration
from ..domain.event_bus import EventBus
from ..domain.events import DomainEvent, RegistrationCancelled, RegistrationPromoted
from ..domain.rules import CapacityRule
from ..repositories import ActivityRepository, RegistrationRepository, StudentRepository


class WaitlistPromotionService:
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

    # ---- 观察者接口 ----
    def handle(self, event: DomainEvent) -> None:
        if not isinstance(event, RegistrationCancelled):
            return
        activity = self._activities.get(event.registration.activity_id)
        if activity is None or activity.status != "published":
            return
        # 活动开始后不再做转正（与“活动开始后不再新增报名”保持一致）
        if not activity.is_open(self._now()):
            return
        # 只有确实存在空位时才转正；名额口径与 v1 完全相同
        if self._capacity.snapshot(activity, self._registrations).is_full:
            return
        head = self._registrations.next_waitlisted(activity.id)
        if head is None:
            return

        with transaction(self._conn):
            updated = self._registrations.update_status(
                head.id, "approved",
                remark=f"候补转正（原候补序号 {head.queue_no}）",
            )

        student = self._students.get(head.student_id)
        self._bus.publish(
            RegistrationPromoted(
                registration=updated, activity=activity, student=student,
                occurred_at=self._now(),
            )
        )

    # ---- 供页面展示候补队列 ----
    def queue_of(self, activity_id: int) -> list[tuple[Registration, object]]:
        return [
            (reg, self._students.get(reg.student_id))
            for reg in self._registrations.waitlisted_of(activity_id)
        ]
