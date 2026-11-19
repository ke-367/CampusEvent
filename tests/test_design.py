"""设计单元测试：策略选择、名额口径、观察者解耦等“设计是否真的成立”的证据。"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app import services
from app.domain.entities import Activity, RegistrationMode
from app.domain.event_bus import EventBus
from app.domain.policies import (
    ApprovalRegistrationPolicy,
    DirectRegistrationPolicy,
    PolicyRegistry,
)
from app.domain.rules import CapacityRule
from conftest import activity_id, student


def test_policy_registry_maps_mode_to_implementation(app):
    with app.app_context():
        from app import container

        registry = container()["policy_registry"]
        assert isinstance(registry.for_mode(RegistrationMode.DIRECT.value), DirectRegistrationPolicy)
        assert isinstance(registry.for_mode(RegistrationMode.APPROVAL.value), ApprovalRegistrationPolicy)
        with pytest.raises(Exception):
            registry.for_mode("unknown-mode")


def test_policy_submit_semantics_differ(app):
    """同一份上下文，两种策略给出不同结论——这正是策略模式要表达的“变化点”。"""
    with app.app_context():
        from app import container
        from app.domain.policies import SubmissionContext

        svc = services()
        aid = activity_id(app, "编程马拉松")
        activity = svc["activity"].detail(aid)
        s = student(app)
        ctx = SubmissionContext(
            activity=activity, student=s, registrations=svc["registrations_repo"],
            capacity_rule=CapacityRule(), now=datetime.now(),
        )
        registry = container()["policy_registry"]
        direct = registry.for_mode("direct").submit(ctx)
        approval = registry.for_mode("approval").submit(ctx)
        assert direct.status == "approved"
        assert approval.status == "pending"
        assert approval.requires_admin_decision is True


def test_capacity_rule_only_counts_approved(app):
    with app.app_context():
        svc = services()
        aid = activity_id(app, "编程马拉松")
        rule = CapacityRule()
        repo = svc["registrations_repo"]
        assert rule.snapshot(svc["activity"].detail(aid), repo).approved == 0

        reg, _ = svc["registration"].register(aid, student(app))
        assert reg.status == "pending"
        # 待审核不占名额
        assert rule.snapshot(svc["activity"].detail(aid), repo).approved == 0

        svc["approval"].approve(reg.id, "管理员")
        assert rule.snapshot(svc["activity"].detail(aid), repo).approved == 1

        svc["registration"].cancel(reg.id, student(app))
        # 取消后名额释放
        assert rule.snapshot(svc["activity"].detail(aid), repo).approved == 0


def test_event_bus_isolates_subscriber_failures():
    """观察者失败的隔离性：一个订阅方异常不影响其他订阅方。"""
    calls = []

    class Good:
        def handle(self, event):
            calls.append(("good", event.name))

    class Bad:
        def handle(self, event):
            raise RuntimeError("boom")

    bus = EventBus()
    bus.subscribe(Bad())
    bus.subscribe(Good())
    bus.set_error_listener(lambda event, handler, exc: calls.append(("error", event.name)))

    from app.domain.events import RegistrationSubmitted

    bus.publish(RegistrationSubmitted())
    assert ("error", "registration-submitted") in calls
    assert ("good", "registration-submitted") in calls


def test_activity_is_open_boundary():
    now = datetime.now()
    activity = Activity(
        id=1, title="边界活动", description="", category="测试", location="",
        start_time=now + timedelta(minutes=1), capacity=10, registration_mode="direct",
    )
    assert activity.is_open(now) is True
    assert activity.is_open(now + timedelta(minutes=2)) is False
