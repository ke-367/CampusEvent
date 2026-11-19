"""领域异常：用异常表达业务规则被违反，Web 层统一翻译为中文提示。"""
from __future__ import annotations


class DomainError(Exception):
    """所有业务规则异常的基类，message 直接面向用户（中文）。"""

    code = "DOMAIN_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(DomainError):
    code = "NOT_FOUND"


class ActivityClosedError(DomainError):
    """活动已开始、已结束或已删除。"""

    code = "ACTIVITY_CLOSED"


class DuplicateRegistrationError(DomainError):
    """同一学生对该活动已有待审核或已通过的报名。"""

    code = "DUPLICATE_REGISTRATION"


class CapacityFullError(DomainError):
    """名额已满（按“已通过”计数）。"""

    code = "CAPACITY_FULL"


class IllegalStatusTransitionError(DomainError):
    """报名状态不允许当前操作，例如重复审批、取消已拒绝的报名。"""

    code = "ILLEGAL_STATUS_TRANSITION"


class PermissionDeniedError(DomainError):
    code = "PERMISSION_DENIED"
