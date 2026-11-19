"""初始版本（baseline-v1）验收用例：与实验指导书 3.5 节的验收表一一对应。

命名规则 T<编号>，方便回归测试表引用。
"""
from __future__ import annotations

import pytest

from app import services
from app.domain.errors import (
    ActivityClosedError,
    CapacityFullError,
    DuplicateRegistrationError,
    IllegalStatusTransitionError,
    NotFoundError,
)
from conftest import activity_id, student


# ------------------------------------------------------------------ T1 直接报名成功
def test_t1_direct_registration_approved_and_notified(app):
    with app.app_context():
        s = student(app)
        svc = services()
        reg, msg = svc["registration"].register(activity_id(app, "迎新晚会"), s)
        assert reg.status == "approved"
        assert "报名成功" in msg
        messages = svc["messages"].list_for_student(s.id)
        assert len(messages) == 1
        assert "报名成功" in messages[0].title


# ------------------------------------------------------------------ T2 名额满时直接报名被拒
def test_t2_direct_register_when_full(app):
    with app.app_context():
        svc = services()
        s1 = student(app, "S001")
        s2 = student(app, "S002")
        aid = activity_id(app, "小型沙龙")   # 名额 = 1
        svc["registration"].register(aid, s1)
        with pytest.raises(CapacityFullError):
            svc["registration"].register(aid, s2)
        assert svc["registrations_repo"].count_by_status(aid, ("approved",)) == 1


# ------------------------------------------------------------------ T3 审核报名进入待审核且不占名额
def test_t3_approval_policy_pending_does_not_occupy_capacity(app):
    with app.app_context():
        svc = services()
        s1 = student(app, "S001")
        s2 = student(app, "S002")
        aid = activity_id(app, "编程马拉松")   # 名额 3，审核型
        for s in (s1, s2):
            reg, _ = svc["registration"].register(aid, s)
            assert reg.status == "pending"
        assert svc["registrations_repo"].count_by_status(aid, ("approved",)) == 0
        pending = svc["approval"].pending()
        assert len(pending) == 2


# ------------------------------------------------------------------ T4 管理员批准
def test_t4_admin_approve(app):
    with app.app_context():
        svc = services()
        s = student(app)
        aid = activity_id(app, "编程马拉松")
        reg, _ = svc["registration"].register(aid, s)
        approved = svc["approval"].approve(reg.id, "管理员")
        assert approved.status == "approved"
        titles = [m.title for m in svc["messages"].list_for_student(s.id)]
        assert "报名审核通过" in titles
        assert svc["registrations_repo"].count_by_status(aid, ("approved",)) == 1


# ------------------------------------------------------------------ T5 满员后不得批准
def test_t5_cannot_approve_when_full(app):
    with app.app_context():
        from app.db import get_db, transaction

        svc = services()
        aid = activity_id(app, "编程马拉松")
        # 把名额改为 1，便于构造“满员”场景
        with transaction(get_db()):
            get_db().execute("UPDATE activities SET capacity = 1 WHERE id = ?", (aid,))

        # 第一位学生：报名 → 批准，占满唯一名额
        reg1, _ = svc["registration"].register(aid, student(app, "S001"))
        svc["approval"].approve(reg1.id, "管理员")
        assert svc["registrations_repo"].count_by_status(aid, ("approved",)) == 1

        # 第二位学生：满员时仍可提交审核（待审核不占名额）
        reg2, _ = svc["registration"].register(aid, student(app, "S002"))
        assert reg2.status == "pending"

        # 批准时二次检查名额 → 必须失败，且状态保持 pending
        with pytest.raises(CapacityFullError):
            svc["approval"].approve(reg2.id, "管理员")
        assert svc["registrations_repo"].get(reg2.id).status == "pending"


# ------------------------------------------------------------------ T6 重复报名被阻止
def test_t6_duplicate_registration_blocked(app):
    with app.app_context():
        svc = services()
        s = student(app)
        aid = activity_id(app, "编程马拉松")
        svc["registration"].register(aid, s)
        with pytest.raises(DuplicateRegistrationError):
            svc["registration"].register(aid, s)


# ------------------------------------------------------------------ T7 取消后可再次申请
def test_t7_cancelled_then_reapply(app):
    with app.app_context():
        svc = services()
        s = student(app)
        aid = activity_id(app, "编程马拉松")
        reg, _ = svc["registration"].register(aid, s)
        svc["registration"].cancel(reg.id, s)
        assert svc["registrations_repo"].get(reg.id).status == "cancelled"
        new_reg, _ = svc["registration"].register(aid, s)
        assert new_reg.id != reg.id and new_reg.status == "pending"


# ------------------------------------------------------------------ T8 已拒绝后可再次申请
def test_t8_rejected_then_reapply(app):
    with app.app_context():
        svc = services()
        s = student(app)
        aid = activity_id(app, "编程马拉松")
        reg, _ = svc["registration"].register(aid, s)
        svc["approval"].reject(reg.id, "管理员", "材料不全")
        assert svc["registrations_repo"].get(reg.id).status == "rejected"
        new_reg, _ = svc["registration"].register(aid, s)
        assert new_reg.status == "pending"


# ------------------------------------------------------------------ T9 活动开始后不得报名
def test_t9_closed_activity_rejected(app):
    with app.app_context():
        svc = services()
        with pytest.raises(ActivityClosedError):
            svc["registration"].register(activity_id(app, "已开始的活动"), student(app))


# ------------------------------------------------------------------ T10 下架活动不可报名，历史保留
def test_t10_soft_delete(app):
    with app.app_context():
        svc = services()
        s = student(app)
        aid = activity_id(app, "迎新晚会")
        reg, _ = svc["registration"].register(aid, s)
        activity, affected = svc["activity"].remove(aid)
        assert affected == 1
        with pytest.raises(NotFoundError):
            svc["registration"].register(aid, s)
        # 历史报名仍然可查
        assert svc["registrations_repo"].get(reg.id).status == "approved"


# ------------------------------------------------------------------ T11 通知失败留痕且报名不丢
class _BrokenChannel:
    name = "broken"

    def deliver(self, payload, messages):
        raise RuntimeError("模拟通知渠道不可用")


def test_t11_notification_failure_is_recorded(app):
    with app.app_context():
        from app import container

        notification = container()["notification"]
        notification._channels.append(_BrokenChannel())
        svc = services()
        s = student(app)
        reg, _ = svc["registration"].register(activity_id(app, "迎新晚会"), s)

        # 报名记录必须存在（通知失败不能回滚业务）
        assert svc["registrations_repo"].get(reg.id).status == "approved"
        # 失败必须留痕
        failures = svc["failures"].list_all()
        assert any(f["channel"] == "broken" for f in failures)
        # 站内消息本身仍然投递成功（单渠道失败不阻断其他渠道）
        assert len(svc["messages"].list_for_student(s.id)) == 1


# ------------------------------------------------------------------ T12 通知幂等
def test_t12_notification_is_idempotent(app):
    with app.app_context():
        from app import container
        from app.domain.events import RegistrationSubmitted

        svc = services()
        s = student(app)
        aid = activity_id(app, "迎新晚会")
        reg, _ = svc["registration"].register(aid, s)
        event = RegistrationSubmitted(
            registration=reg, activity=svc["activity"].detail(aid), student=s
        )
        bus = container()["bus"]
        bus.publish(event)
        bus.publish(event)
        assert svc["messages"].count_for_event(event.event_key) == 1


# ------------------------------------------------------------------ T13 持久化
def test_t13_persistence_across_connections(app):
    with app.app_context():
        svc = services()
        s = student(app)
        reg, _ = svc["registration"].register(activity_id(app, "迎新晚会"), s)

    # 新建一个应用实例指向同一数据库，模拟进程重启
    from app import create_app

    app2 = create_app({"DATABASE": app.config["DATABASE"], "OUTBOX_DIR": app.config["OUTBOX_DIR"]})
    with app2.app_context():
        found = services()["registrations_repo"].get(reg.id)
        assert found is not None and found.status == "approved"


# ------------------------------------------------------------------ T14 越权取消
def test_t14_cannot_cancel_others_registration(app):
    with app.app_context():
        svc = services()
        s1 = student(app, "S001")
        s2 = student(app, "S002")
        reg, _ = svc["registration"].register(activity_id(app, "迎新晚会"), s1)
        with pytest.raises(NotFoundError):
            svc["registration"].cancel(reg.id, s2)


# ------------------------------------------------------------------ T15 重复审批
def test_t15_double_decision_blocked(app):
    with app.app_context():
        svc = services()
        s = student(app)
        aid = activity_id(app, "编程马拉松")
        reg, _ = svc["registration"].register(aid, s)
        svc["approval"].approve(reg.id, "管理员")
        with pytest.raises(IllegalStatusTransitionError):
            svc["approval"].reject(reg.id, "管理员", "重复操作")


# ------------------------------------------------------------------ T16 页面可访问
def test_t16_pages_render(client, app):
    assert client.get("/").status_code == 200
    assert client.get("/login").status_code == 200
    with app.app_context():
        aid = activity_id(app, "编程马拉松")
    assert client.get(f"/activities/{aid}").status_code == 200


# ------------------------------------------------------------------ T17 端到端 HTTP 流程
def test_t17_http_end_to_end(client, app):
    with app.app_context():
        aid = activity_id(app, "编程马拉松")
        other = activity_id(app, "迎新晚会")
    client.post("/login", data={"role": "student", "student_no": "S001"})
    client.post(f"/activities/{aid}/register")
    client.post(f"/activities/{other}/register")

    # 学生视角：我的报名有两条
    resp = client.get("/me/registrations")
    assert "编程马拉松" in resp.get_data(as_text=True)

    # 管理员批准
    client.get("/logout")
    client.post("/login", data={"role": "admin", "admin_code": "admin123"})
    with app.app_context():
        pending = services()["approval"].pending()
    client.post(f"/admin/registrations/{pending[0][0].id}/approve")
    with app.app_context():
        assert services()["registrations_repo"].get(pending[0][0].id).status == "approved"
