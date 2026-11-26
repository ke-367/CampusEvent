"""领域模型（不依赖 Flask / SQLite）。

设计取舍：Activity 只描述“活动是什么、当前是否可报名”；报名准入语义放在策略；
名额计数放在 CapacityRule；通知放在观察者侧。实体本身保持贫血模型。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ActivityStatus(str, Enum):
    PUBLISHED = "published"
    DELETED = "deleted"


class RegistrationMode(str, Enum):
    """活动的报名规则类型。值会持久化到数据库。"""

    DIRECT = "direct"        # 直接报名：名额充足即“已通过”
    APPROVAL = "approval"    # 审核报名：提交后“待审核”，由管理员决定
    WAITLIST = "waitlist"    # 候补报名：名额满则排队，有人取消自动转正
    GRADE_LIMITED = "grade_limited"  # 年级限定报名：仅指定年级可报（CR-01 新增）


class RegistrationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    WAITLISTED = "waitlisted"   # 需求变更新增：名额满时进入候补队列

    @property
    def label(self) -> str:
        return STATUS_LABELS[self.value]


STATUS_LABELS = {
    "pending": "待审核",
    "approved": "已通过",
    "rejected": "已拒绝",
    "cancelled": "已取消",
    "waitlisted": "候补中",
}

#: 有效报名状态：占用“同一学生同一活动只能有一条有效报名”这条业务约束。
ACTIVE_STATUSES = (
    RegistrationStatus.PENDING.value,
    RegistrationStatus.APPROVED.value,
    RegistrationStatus.WAITLISTED.value,
)

#: 占用名额的状态：只有“已通过”占用名额，待审核不占。
CAPACITY_STATUSES = (RegistrationStatus.APPROVED.value,)


@dataclass(frozen=True)
class Student:
    id: int
    name: str
    student_no: str
    email: str
    grade: int = 0          # 年级 1—4（CR-01 新增字段；0 表示未设置）


@dataclass(frozen=True)
class Activity:
    id: int
    title: str
    description: str
    category: str
    location: str
    start_time: datetime
    capacity: int
    registration_mode: str
    status: str = ActivityStatus.PUBLISHED.value
    grade_restriction: str = ""   # "2,3" 这类逗号分隔的年级集合（CR-01 新增字段）

    def is_open(self, now: datetime) -> bool:
        """活动未删除且尚未开始，才允许新增报名。"""
        return self.status == ActivityStatus.PUBLISHED.value and now < self.start_time

    @property
    def allowed_grades(self) -> tuple[int, ...]:
        """解析限报年级集合；空字符串表示不限年级。"""
        parts = [p.strip() for p in (self.grade_restriction or "").split(",") if p.strip()]
        grades = []
        for part in parts:
            try:
                grades.append(int(part))
            except ValueError:
                continue
        return tuple(grades)

    @property
    def mode_label(self) -> str:
        return MODE_LABELS.get(self.registration_mode, self.registration_mode)


MODE_LABELS = {
    "direct": "直接报名",
    "approval": "审核报名",
    "waitlist": "候补报名",
    "grade_limited": "年级限定报名",
}


@dataclass(frozen=True)
class Registration:
    id: int
    activity_id: int
    student_id: int
    status: str
    policy_key: str
    remark: str
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime
    queue_no: int | None = None

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


@dataclass(frozen=True)
class Notification:
    id: int
    student_id: int
    registration_id: int | None
    channel: str
    event_key: str
    title: str
    body: str
    created_at: datetime
    read_at: datetime | None = None
