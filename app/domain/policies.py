"""报名策略：用策略模式表达“变化的部分”——报名准入规则。

稳定抽象 RegistrationPolicy 只回答一个问题：
    给定活动、学生与当前名额状态，本次提交 → 立即通过，还是进入待审核？

注册/名额/重复报名等公共规则由 RegistrationService 统一把关；
名额计数口径由 CapacityRule 提供，检查时机由各策略自行决定。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from .entities import Activity, RegistrationMode, RegistrationStatus, Student
from .errors import DomainError
from .rules import CapacityRule


@dataclass(frozen=True)
class SubmissionContext:
    """一次报名提交所需的上下文，避免策略直接接触仓储与 Web 层。"""

    activity: Activity
    student: Student
    registrations: object      # RegistrationRepository（只读使用）
    capacity_rule: CapacityRule
    now: datetime


@dataclass(frozen=True)
class PolicyDecision:
    status: str                # RegistrationStatus 的 value
    message: str               # 面向学生的中文提示
    queue_no: int | None = None   # 候补序号（仅候补规则使用）

    @property
    def requires_admin_decision(self) -> bool:
        return self.status == RegistrationStatus.PENDING.value


class RegistrationPolicy(ABC):
    """报名规则抽象。新增一种规则 = 新增一个实现 + 在注册表登记一行。"""

    mode: str = ""
    key: str = ""
    label: str = ""

    @abstractmethod
    def submit(self, context: SubmissionContext) -> PolicyDecision:
        """返回本次提交的准入结论；违反硬约束时抛出域名异常。"""


class DirectRegistrationPolicy(RegistrationPolicy):
    """直接报名：名额充足即“已通过”，同时产生通知。"""

    mode = RegistrationMode.DIRECT.value
    key = "policy.direct"
    label = "直接报名"

    def __init__(self, capacity_rule: CapacityRule):
        self._capacity = capacity_rule

    def submit(self, context: SubmissionContext) -> PolicyDecision:
        snap = self._capacity.ensure_available(context.activity, context.registrations)
        return PolicyDecision(
            status=RegistrationStatus.APPROVED.value,
            message=f"报名成功，已占用名额（{snap.approved + 1}/{snap.capacity}）。",
        )


class ApprovalRegistrationPolicy(RegistrationPolicy):
    """审核报名：提交为“待审核”，不占名额；管理员批准时再检查名额。"""

    mode = RegistrationMode.APPROVAL.value
    key = "policy.approval"
    label = "审核报名"

    def __init__(self, capacity_rule: CapacityRule):
        # 提交阶段不使用，保留依赖以便批准阶段复用同一口径（由 ApprovalService 调用）
        self._capacity = capacity_rule

    def submit(self, context: SubmissionContext) -> PolicyDecision:
        if context.activity.status != "published":
            raise DomainError("活动已下线，无法报名。")
        snap = self._capacity.snapshot(context.activity, context.registrations)
        hint = "名额已满，仍可提交审核，最终是否通过以管理员审批结果为准。" if snap.is_full else "报名申请已提交。"
        return PolicyDecision(
            status=RegistrationStatus.PENDING.value,
            message=f"{hint}等待管理员审核。",
        )


class WaitlistRegistrationPolicy(RegistrationPolicy):
    """候补报名：名额未满直接通过；已满则进入候补队列。

    与另外两种规则的差别只有“满员时的处置方式”，因此复用同一条 CapacityRule，
    没有改动 RegistrationService 的任何代码。
    """

    mode = RegistrationMode.WAITLIST.value
    key = "policy.waitlist"
    label = "候补报名"

    def __init__(self, capacity_rule: CapacityRule):
        self._capacity = capacity_rule

    def submit(self, context: SubmissionContext) -> PolicyDecision:
        snap = self._capacity.snapshot(context.activity, context.registrations)
        if not snap.is_full:
            return PolicyDecision(
                status=RegistrationStatus.APPROVED.value,
                message=f"报名成功，已占用名额（{snap.approved + 1}/{snap.capacity}）。",
            )
        queue_no = (
            context.registrations.count_by_status(
                context.activity.id, (RegistrationStatus.WAITLISTED.value,)
            )
            + 1
        )
        return PolicyDecision(
            status=RegistrationStatus.WAITLISTED.value,
            message=f"名额已满，你已进入候补队列（第 {queue_no} 位），有人取消时将按顺序转正。",
            queue_no=queue_no,
        )


class GradeLimitedRegistrationPolicy(RegistrationPolicy):
    """年级限定直接报名（需求变更 CR-01 新增）。

    设计选择：不把“年级判断”塞进 DirectRegistrationPolicy，而是新增独立策略，
    并在内部**组合**已有的无状态 CapacityRule——于是“年级门槛”是新增的准入条件，
    “名额上限”仍复用唯一的口径实现（不是复制一份名额代码）。
    RegistrationService 主流程一行未改：它只按活动上的 registration_mode 取策略。
    """

    mode = RegistrationMode.GRADE_LIMITED.value
    key = "policy.grade_limited"
    label = "年级限定报名"

    def __init__(self, capacity_rule: CapacityRule):
        self._capacity = capacity_rule

    def submit(self, context: SubmissionContext) -> PolicyDecision:
        allowed = context.activity.allowed_grades
        grade = context.student.grade
        if allowed and grade not in allowed:
            text = "、".join(str(g) for g in allowed)
            raise DomainError(
                f"活动「{context.activity.title}」仅限 {text} 年级报名，"
                f"你当前是 {grade or '未设置'} 年级，无法报名。"
            )
        snap = self._capacity.ensure_available(context.activity, context.registrations)
        return PolicyDecision(
            status=RegistrationStatus.APPROVED.value,
            message=f"报名成功，已占用名额（{snap.approved + 1}/{snap.capacity}）。",
        )


class PolicyRegistry:
    """策略注册表：按活动上的 registration_mode 选择实现，主流程不出现 if/elif。"""

    def __init__(self, capacity_rule: CapacityRule):
        self._capacity_rule = capacity_rule
        self._policies: dict[str, RegistrationPolicy] = {}
        for policy in (
            DirectRegistrationPolicy(capacity_rule),
            ApprovalRegistrationPolicy(capacity_rule),
            WaitlistRegistrationPolicy(capacity_rule),
            GradeLimitedRegistrationPolicy(capacity_rule),
        ):
            self.register(policy)

    def register(self, policy: RegistrationPolicy) -> None:
        self._policies[policy.mode] = policy

    def for_mode(self, mode: str) -> RegistrationPolicy:
        try:
            return self._policies[mode]
        except KeyError:
            raise DomainError(f"未知的报名规则：{mode}") from None

    @property
    def supported_modes(self) -> list[tuple[str, str]]:
        """(mode, 中文名)，供管理端表单与展示使用。"""
        return [(p.mode, p.label) for p in self._policies.values()]
