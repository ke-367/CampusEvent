"""名额规则：两类报名规则共享的“公共领域规则”。

为什么放在这里而不是写进策略：
    名额上限是活动本身的约束，与“直接通过还是需要审核”无关。如果写进每个策略，
    规则会被复制（违反 DRY），将来新增第三种规则时必然漏改。因此实现为无状态的
    CapacityRule，由策略决定“何时检查”：
      * 直接报名：提交时检查（满员则直接拒绝）；
      * 审核报名：提交时不检查（待审核不占名额），管理员批准时再检查。
    “检查时机”是策略的可变语义，“计数口径”则是唯一的公共实现。
"""
from __future__ import annotations

from dataclasses import dataclass

from .entities import Activity, CAPACITY_STATUSES
from .errors import CapacityFullError


@dataclass(frozen=True)
class CapacitySnapshot:
    capacity: int
    approved: int

    @property
    def available(self) -> int:
        return max(self.capacity - self.approved, 0)

    @property
    def is_full(self) -> bool:
        return self.approved >= self.capacity

    @property
    def text(self) -> str:
        return f"{self.approved}/{self.capacity}"


class CapacityRule:
    """名额口径：只统计“已通过”的报名，待审核/已取消/已拒绝均不占名额。"""

    def snapshot(self, activity: Activity, registrations) -> CapacitySnapshot:
        approved = registrations.count_by_status(activity.id, CAPACITY_STATUSES)
        return CapacitySnapshot(capacity=activity.capacity, approved=approved)

    def ensure_available(self, activity: Activity, registrations) -> CapacitySnapshot:
        snap = self.snapshot(activity, registrations)
        if snap.is_full:
            raise CapacityFullError(
                f"活动「{activity.title}」名额已满（{snap.text}），无法再通过新的报名。"
            )
        return snap
