"""需求变更（change-v2）新增用例：候补规则 + 邮件渠道。

编号 V<序号>，回归测试表中与变更影响分析一一对应。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app import container, services
from app.domain.errors import DuplicateRegistrationError
from conftest import activity_id, student


def _create_waitlist_activity(app, capacity=2, hours=72, title="候补测试活动"):
    """通过服务层发布一个“候补报名”活动（走与页面相同的校验）。"""
    start = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M")
    return services()["activity"].create(
        {
            "title": title,
            "description": "需求变更测试用",
            "category": "测试",
            "location": "线上",
            "start_time": start,
            "capacity": str(capacity),
            "registration_mode": "waitlist",
        }
    )


# ------------------------------------------------------------------ V1 候补入队
def test_v1_waitlist_policy_queues_when_full(app):
    with app.app_context():
        svc = services()
        act = _create_waitlist_activity(app, capacity=1)
        s1, s2, s3 = (student(app, no) for no in ("S001", "S002", "S001"))
        reg1, _ = svc["registration"].register(act.id, s1)
        assert reg1.status == "approved"

        reg2, msg2 = svc["registration"].register(act.id, s2)
        assert reg2.status == "waitlisted"
        assert reg2.queue_no == 1
        assert "候补队列（第 1 位）" in msg2
        # 已通过名单不变，候补不占名额
        assert svc["registrations_repo"].count_by_status(act.id, ("approved",)) == 1


# ------------------------------------------------------------------ V2 取消后自动转正
def test_v2_cancel_promotes_first_waitlisted(app):
    with app.app_context():
        svc = services()
        act = _create_waitlist_activity(app, capacity=1)
        s1 = student(app, "S001")
        s2 = student(app, "S002")
        reg1, _ = svc["registration"].register(act.id, s1)
        reg2, _ = svc["registration"].register(act.id, s2)
        assert reg2.status == "waitlisted"

        svc["registration"].cancel(reg1.id, s1)

        promoted = svc["registrations_repo"].get(reg2.id)
        assert promoted.status == "approved"
        assert "候补转正" in promoted.remark
        # 通知：取消通知 + 转正通知
        titles = [m.title for m in svc["messages"].list_for_student(s2.id)]
        assert "已进入候补队列" in titles
        assert "候补转正通知" in titles


# ------------------------------------------------------------------ V3 邮件渠道
def test_v3_email_channel_writes_outbox_and_dedupes(app):
    with app.app_context():
        svc = services()
        act = activity_id(app, "迎新晚会")
        reg, _ = svc["registration"].register(act, student(app))

        outbox = app.config["OUTBOX_DIR"]
        from pathlib import Path

        files = list(Path(outbox).glob("*.eml"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "To: " in content and "@example.edu.cn" in content
        assert "成功报名" in content

        # 同一事件重复投递邮件渠道 → 不产生第二条
        from app.domain.events import RegistrationSubmitted

        event = RegistrationSubmitted(
            registration=reg, activity=svc["activity"].detail(act), student=student(app)
        )
        container()["bus"].publish(event)
        assert len(list(Path(outbox).glob("*.eml"))) == 1


# ------------------------------------------------------------------ V4 候补仍受“唯一有效报名”约束
def test_v4_waitlisted_still_unique_per_student(app):
    with app.app_context():
        svc = services()
        act = _create_waitlist_activity(app, capacity=1)
        s1 = student(app, "S001")
        s2 = student(app, "S002")
        svc["registration"].register(act.id, s1)
        reg2, _ = svc["registration"].register(act.id, s2)
        assert reg2.status == "waitlisted"
        with pytest.raises(DuplicateRegistrationError):
            svc["registration"].register(act.id, s2)


# ------------------------------------------------------------------ V5 活动开始后不再转正
def test_v5_no_promotion_after_activity_started(app):
    with app.app_context():
        from app.db import get_db, transaction

        svc = services()
        act = _create_waitlist_activity(app, capacity=1)
        s1, s2 = student(app, "S001"), student(app, "S002")
        reg1, _ = svc["registration"].register(act.id, s1)
        reg2, _ = svc["registration"].register(act.id, s2)

        # 把活动开始时间改到过去，模拟“活动已开始”
        with transaction(get_db()):
            get_db().execute(
                "UPDATE activities SET start_time = ? WHERE id = ?",
                ((datetime.now() - timedelta(hours=1)).isoformat(timespec="minutes"), act.id),
            )
        svc["registration"].cancel(reg1.id, s1)
        assert svc["registrations_repo"].get(reg2.id).status == "waitlisted"


# ------------------------------------------------------------------ V6 候补队列层序
def test_v6_promotion_order_is_fifo(app):
    with app.app_context():
        svc = services()
        act = _create_waitlist_activity(app, capacity=1)
        s1, s2 = student(app, "S001"), student(app, "S002")
        reg1, _ = svc["registration"].register(act.id, s1)   # approved
        reg2, _ = svc["registration"].register(act.id, s2)   # waitlisted 1

        svc["registration"].cancel(reg1.id, s1)              # reg2 转正
        assert svc["registrations_repo"].get(reg2.id).status == "approved"
        # 转正后队列为空
        assert svc["registrations_repo"].waitlisted_of(act.id) == []


# ------------------------------------------------------------------ V7 三种规则并存
def test_v7_registry_supports_three_modes(app):
    with app.app_context():
        registry = container()["policy_registry"]
        modes = dict(registry.supported_modes)
        assert modes == {
            "direct": "直接报名",
            "approval": "审核报名",
            "waitlist": "候补报名",
        }
        assert modes["waitlist"] == "候补报名"


# ------------------------------------------------------------------ V8 页面展示候补
def test_v8_waitlist_visible_on_pages(client, app):
    with app.app_context():
        act = _create_waitlist_activity(app, capacity=1)
        client.post("/login", data={"role": "student", "student_no": "S001"})
        client.post(f"/activities/{act.id}/register")
    client.post("/logout")
    with app.app_context():
        client.post("/login", data={"role": "student", "student_no": "S002"})
        client.post(f"/activities/{act.id}/register")
        resp = client.get(f"/activities/{act.id}")
    body = resp.get_data(as_text=True)
    assert "候补第" in body or "候补队列" in body
