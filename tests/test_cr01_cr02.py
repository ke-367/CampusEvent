"""需求变更 CR-01（年级限定报名）与 CR-02（邮件通知）的验收用例。

用例编号与教师材料中的变更测试表逐条对应：
    CR1-01 ~ CR1-05、CR2-01 ~ CR2-05。
CR1-05 / CR2-05（“变更后重新运行 C1—C10”）由 test_baseline.py 与 test_design.py 全绿覆盖。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app import container, services
from app.domain.errors import CapacityFullError, DomainError
from conftest import activity_id, student


def _create_grade_limited(app, title="年级限定测试活动", capacity=2, restriction="2,3"):
    start = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M")
    return services()["activity"].create(
        {
            "title": title,
            "description": "CR-01 测试用",
            "category": "测试",
            "location": "线上",
            "start_time": start,
            "capacity": str(capacity),
            "registration_mode": "grade_limited",
            "grade_restriction": restriction,
        }
    )


# ============================================================ CR-01 年级限定
def test_cr1_01_sophomore_can_register(app):
    """CR1-01 大二学生报名年级限定活动 → 通过。"""
    with app.app_context():
        svc = services()
        act = activity_id(app, "年级限定活动")
        reg, msg = svc["registration"].register(act, student(app, "S001"))  # grade=2
        assert reg.status == "approved"
        assert "报名成功" in msg
        assert reg.policy_key == "policy.grade_limited"


def test_cr1_02_junior_can_register(app):
    """CR1-02 大三学生报名年级限定活动 → 通过。"""
    with app.app_context():
        svc = services()
        act = _create_grade_limited(app, title="大三也能报")
        # 临时把 S002 设为三年级，验证同一策略对不同年级的判定
        from app.db import get_db

        get_db().execute("UPDATE students SET grade = 3 WHERE student_no = 'S002'")
        reg, _ = svc["registration"].register(act.id, svc["students"].get_by_no("S002"))
        assert reg.status == "approved"


def test_cr1_03_freshman_rejected_with_reason(app):
    """CR1-03 大一学生报名年级限定活动 → 拒绝并显示原因。"""
    with app.app_context():
        svc = services()
        act = activity_id(app, "年级限定活动")
        with pytest.raises(DomainError) as exc:
            svc["registration"].register(act, student(app, "S002"))  # grade=1
        message = str(exc.value)
        assert "仅限" in message and "2、3" in message and "年级" in message
        # 未产生任何报名记录（拒绝发生在落库之前）
        assert svc["registrations_repo"].find_active(act, student(app, "S002").id) is None


def test_cr1_04_senior_rejected_with_reason(app):
    """CR1-04 大四学生报名年级限定活动 → 拒绝并显示原因。"""
    with app.app_context():
        svc = services()
        act = activity_id(app, "年级限定活动")
        with pytest.raises(DomainError) as exc:
            svc["registration"].register(act, student(app, "S003"))  # grade=4
        assert "仅限" in str(exc.value) and "4" in str(exc.value)


def test_cr1_05_capacity_and_time_rules_still_apply(app):
    """CR-01 附加：年级符合时，名额上限与开始时间等公共约束照旧生效。"""
    with app.app_context():
        svc = services()
        act = _create_grade_limited(app, title="年级限定额满测试", capacity=1)
        from app.db import get_db

        get_db().execute("UPDATE students SET grade = 3 WHERE student_no = 'S002'")
        s1 = student(app, "S001")          # grade=2
        s2 = svc["students"].get_by_no("S002")  # grade=3
        reg, _ = svc["registration"].register(act.id, s1)
        assert reg.status == "approved"
        with pytest.raises(CapacityFullError):
            svc["registration"].register(act.id, s2)


def test_cr1_grade_restriction_empty_means_no_limit(app):
    """边界：未配置限报年级时，该策略退化为“直接报名”（不误伤任何年级）。"""
    with app.app_context():
        svc = services()
        act = _create_grade_limited(app, title="不限年级", restriction="")
        reg, _ = svc["registration"].register(act.id, student(app, "S003"))  # grade=4
        assert reg.status == "approved"


# ============================================================ CR-02 邮件通知
def _outbox_files(app):
    return sorted(Path(app.config["OUTBOX_DIR"]).glob("*.eml"))


def test_cr2_01_direct_register_notifies_both_channels(app):
    """CR2-01 直接报名通过 → 站内消息和模拟邮件均有记录。"""
    with app.app_context():
        svc = services()
        act = activity_id(app, "迎新晚会")
        reg, _ = svc["registration"].register(act, student(app, "S001"))
        assert reg.status == "approved"

        inapp = [m for m in svc["messages"].list_for_student(student(app, "S001").id)
                 if m.channel == "inapp"]
        assert any("报名成功" in m.title for m in inapp)

        files = _outbox_files(app)
        assert files, "应生成模拟邮件"
        content = files[0].read_text(encoding="utf-8")
        assert "To: zxm@example.edu.cn" in content
        assert "X-Delivery-Status: delivered" in content
        assert "成功报名" in content


def test_cr2_02_approve_and_reject_notify_both_channels(app):
    """CR2-02 审核批准或拒绝 → 两种渠道记录对应结果。"""
    with app.app_context():
        svc = services()
        act = activity_id(app, "编程马拉松")
        s1, s2 = student(app, "S001"), student(app, "S002")
        reg1, _ = svc["registration"].register(act, s1)
        reg2, _ = svc["registration"].register(act, s2)
        assert reg1.status == reg2.status == "pending"

        svc["approval"].approve(reg1.id, "管理员")
        svc["approval"].reject(reg2.id, "管理员", "材料不齐")

        s1_msgs = [m.title for m in svc["messages"].list_for_student(s1.id)]
        s2_msgs = [m.title for m in svc["messages"].list_for_student(s2.id)]
        assert "报名审核通过" in s1_msgs
        assert "报名未通过" in s2_msgs

        contents = "\n".join(f.read_text(encoding="utf-8") for f in _outbox_files(app))
        assert "报名审核通过" in contents or "审核通过" in contents
        assert "未通过" in contents


def test_cr2_03_email_failure_keeps_registration_and_logs_error(app, monkeypatch):
    """CR2-03 模拟邮件发送失败 → 报名状态正确、错误有日志。"""
    with app.app_context():
        svc = services()
        email_channel = next(
            c for c in container()["notification"]._channels if c.name == "email"
        )

        def boom(payload, messages):
            raise RuntimeError("mock smtp down")

        monkeypatch.setattr(email_channel, "deliver", boom)

        act = activity_id(app, "迎新晚会")
        reg, _ = svc["registration"].register(act, student(app, "S001"))
        # 业务事实不受影响
        assert reg.status == "approved"
        assert svc["registrations_repo"].count_by_status(act, ("approved",)) == 1
        # 站内渠道照常
        assert any(m.channel == "inapp" for m in svc["messages"].list_for_student(student(app, "S001").id))
        # 失败留痕
        failures = svc["failures"].list_all()
        assert any(f["channel"] == "email" and "mock smtp down" in f["error"] for f in failures)


def test_cr2_04_repeated_event_does_not_duplicate_notifications(app):
    """CR2-04 重复提交同一业务动作 → 不应重复生成多份相同通知。"""
    with app.app_context():
        svc = services()
        act = activity_id(app, "迎新晚会")
        reg, _ = svc["registration"].register(act, student(app, "S001"))

        from app.domain.events import RegistrationSubmitted

        event = RegistrationSubmitted(
            registration=reg, activity=svc["activity"].detail(act), student=student(app, "S001"),
            occurred_at=datetime.now(),
        )
        before_emails = len(_outbox_files(app))
        container()["bus"].publish(event)   # 同一事件重复发布
        after_emails = len(_outbox_files(app))

        assert before_emails == 1
        assert after_emails == before_emails, "同一事件不应重复发信"
        inapp = [m for m in svc["messages"].list_for_student(student(app, "S001").id)
                 if m.channel == "inapp"]
        assert len([m for m in inapp if "报名成功" in m.title]) == 1


def test_cr2_05_last_semester_rules_still_intact(app):
    """CR2-05 原有功能保持通过（抽样断言，完整覆盖见 test_baseline.py）。"""
    with app.app_context():
        svc = services()
        act = activity_id(app, "小型沙龙")     # capacity=1
        s1, s2 = student(app, "S001"), student(app, "S002")
        reg, _ = svc["registration"].register(act, s1)
        assert reg.status == "approved"
        with pytest.raises(CapacityFullError):
            svc["registration"].register(act, s2)
        # 取消后名额释放
        svc["registration"].cancel(reg.id, s1)
        assert svc["registrations_repo"].count_by_status(act, ("approved",)) == 0
