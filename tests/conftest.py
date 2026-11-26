"""测试夹具：每个测试用例一个临时数据库，互不影响。"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.db import connect, transaction  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    app = create_app(
        {
            "DATABASE": str(tmp_path / "test.db"),
            "OUTBOX_DIR": str(tmp_path / "outbox"),
            "SECRET_KEY": "test-secret",
            "ADMIN_CODE": "admin123",
            "TESTING": True,
        }
    )
    _seed(app)
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _seed(app) -> None:
    """三名学生 + 五个活动：覆盖直接/审核/候补/年级限定四类规则、满员、即将开始等边界。"""
    conn = connect(app.config["DATABASE"])
    now = datetime.now()
    try:
        with transaction(conn):
            for no, name, email, grade in (
                ("S001", "张小明", "zxm@example.edu.cn", 2),
                ("S002", "李小红", "lxh@example.edu.cn", 1),
                ("S003", "王大力", "wdl@example.edu.cn", 4),
            ):
                conn.execute(
                    "INSERT INTO students(student_no, name, email, grade) VALUES (?,?,?,?)",
                    (no, name, email, grade),
                )
            rows = [
                # title, capacity, mode, 开始时间偏移, 状态, 限报年级
                ("迎新晚会", 120, "direct", 72, "published", ""),
                ("编程马拉松", 3, "approval", 120, "published", ""),
                ("小型沙龙", 1, "direct", 48, "published", ""),
                ("已开始的活动", 10, "direct", -2, "published", ""),
                ("已下架活动", 10, "direct", 96, "deleted", ""),
                ("年级限定活动", 2, "grade_limited", 60, "published", "2,3"),
            ]
            for title, capacity, mode, offset_hours, status, grade_restriction in rows:
                conn.execute(
                    "INSERT INTO activities(title, description, category, location, start_time, "
                    "capacity, registration_mode, grade_restriction, status, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        title, f"{title} 的说明", "测试", "测试地点",
                        (now + timedelta(hours=offset_hours)).isoformat(timespec="minutes"),
                        capacity, mode, grade_restriction, status, now.isoformat(timespec="seconds"),
                    ),
                )
    finally:
        conn.close()


def student(app, no="S001"):
    from app import services

    return services()["students"].get_by_no(no)


def activity_id(app, title):
    from app import services

    for a in services()["activity"].list_all():
        if a.title == title:
            return a.id
    raise AssertionError(f"未找到活动：{title}")
