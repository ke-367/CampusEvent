"""仓储层：把 SQLite 细节关在这里，领域与服务只看到对象与集合。

约定：仓储方法不自行提交事务，由 services 用 db.transaction() 统一控制边界。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from .domain.entities import Activity, Notification, Registration, Student


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _row_to_student(row: sqlite3.Row) -> Student:
    return Student(
        id=row["id"],
        name=row["name"],
        student_no=row["student_no"],
        email=row["email"],
        grade=row["grade"] if "grade" in row.keys() else 0,
    )


def _row_to_activity(row: sqlite3.Row) -> Activity:
    return Activity(
        id=row["id"],
        title=row["title"],
        description=row["description"],
        category=row["category"],
        location=row["location"],
        start_time=_dt(row["start_time"]),
        capacity=row["capacity"],
        registration_mode=row["registration_mode"],
        status=row["status"],
        grade_restriction=row["grade_restriction"] if "grade_restriction" in row.keys() else "",
    )


def _row_to_registration(row: sqlite3.Row) -> Registration:
    return Registration(
        id=row["id"],
        activity_id=row["activity_id"],
        student_id=row["student_id"],
        status=row["status"],
        policy_key=row["policy_key"],
        remark=row["remark"],
        decided_by=row["decided_by"],
        decided_at=_dt(row["decided_at"]),
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
        queue_no=row["queue_no"] if "queue_no" in row.keys() else None,
    )


class StudentRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list_all(self) -> list[Student]:
        rows = self._conn.execute("SELECT * FROM students ORDER BY id").fetchall()
        return [_row_to_student(r) for r in rows]

    def get(self, student_id: int) -> Student | None:
        row = self._conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        return _row_to_student(row) if row else None

    def get_by_no(self, student_no: str) -> Student | None:
        row = self._conn.execute(
            "SELECT * FROM students WHERE student_no = ?", (student_no.strip(),)
        ).fetchone()
        return _row_to_student(row) if row else None


class ActivityRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get(self, activity_id: int) -> Activity | None:
        row = self._conn.execute("SELECT * FROM activities WHERE id = ?", (activity_id,)).fetchone()
        return _row_to_activity(row) if row else None

    def list_visible(self) -> list[Activity]:
        rows = self._conn.execute(
            "SELECT * FROM activities WHERE status = 'published' ORDER BY start_time"
        ).fetchall()
        return [_row_to_activity(r) for r in rows]

    def list_all(self) -> list[Activity]:
        rows = self._conn.execute("SELECT * FROM activities ORDER BY start_time").fetchall()
        return [_row_to_activity(r) for r in rows]

    def create(
        self,
        *,
        title: str,
        description: str,
        category: str,
        location: str,
        start_time: datetime,
        capacity: int,
        registration_mode: str,
        grade_restriction: str = "",
    ) -> Activity:
        now = datetime.now().isoformat(timespec="seconds")
        cur = self._conn.execute(
            "INSERT INTO activities(title, description, category, location, start_time, "
            "capacity, registration_mode, grade_restriction, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,'published',?)",
            (
                title,
                description,
                category,
                location,
                start_time.isoformat(timespec="minutes"),
                capacity,
                registration_mode,
                grade_restriction,
                now,
            ),
        )
        activity = self.get(cur.lastrowid)
        assert activity is not None
        return activity

    def soft_delete(self, activity_id: int) -> None:
        """软删除：保留历史报名与通知，只在列表/报名字段上不可见。"""
        self._conn.execute("UPDATE activities SET status = 'deleted' WHERE id = ?", (activity_id,))


class RegistrationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get(self, registration_id: int) -> Registration | None:
        row = self._conn.execute(
            "SELECT * FROM registrations WHERE id = ?", (registration_id,)
        ).fetchone()
        return _row_to_registration(row) if row else None

    def create(
        self, *, activity_id: int, student_id: int, status: str, policy_key: str,
        queue_no: int | None = None,
    ) -> Registration:
        now = datetime.now().isoformat(timespec="seconds")
        cur = self._conn.execute(
            "INSERT INTO registrations(activity_id, student_id, status, policy_key, queue_no, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (activity_id, student_id, status, policy_key, queue_no, now, now),
        )
        registration = self.get(cur.lastrowid)
        assert registration is not None
        return registration

    def update_status(
        self,
        registration_id: int,
        status: str,
        *,
        decided_by: str | None = None,
        remark: str | None = None,
    ) -> Registration:
        now = datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "UPDATE registrations SET status = ?, updated_at = ?, decided_by = COALESCE(?, decided_by), "
            "decided_at = CASE WHEN ? IN ('approved','rejected') THEN ? ELSE decided_at END, "
            "remark = COALESCE(?, remark) WHERE id = ?",
            (status, now, decided_by, status, now, remark, registration_id),
        )
        registration = self.get(registration_id)
        assert registration is not None
        return registration

    def find_active(self, activity_id: int, student_id: int) -> Registration | None:
        row = self._conn.execute(
            "SELECT * FROM registrations WHERE activity_id = ? AND student_id = ? "
            "AND status IN ('pending','approved','waitlisted') ORDER BY id DESC LIMIT 1",
            (activity_id, student_id),
        ).fetchone()
        return _row_to_registration(row) if row else None

    def find_by_student(self, activity_id: int, student_id: int) -> list[Registration]:
        rows = self._conn.execute(
            "SELECT * FROM registrations WHERE activity_id = ? AND student_id = ? ORDER BY id DESC",
            (activity_id, student_id),
        ).fetchall()
        return [_row_to_registration(r) for r in rows]

    def count_by_status(self, activity_id: int, statuses: tuple[str, ...]) -> int:
        placeholders = ",".join("?" for _ in statuses)
        row = self._conn.execute(
            f"SELECT COUNT(*) AS c FROM registrations WHERE activity_id = ? AND status IN ({placeholders})",
            (activity_id, *statuses),
        ).fetchone()
        return int(row["c"])

    def list_by_student(self, student_id: int) -> list[tuple[Registration, Activity]]:
        rows = self._conn.execute(
            "SELECT r.*, a.title AS a_title, a.start_time AS a_start_time, a.location AS a_location, "
            "a.registration_mode AS a_mode, a.status AS a_status, a.capacity AS a_capacity, "
            "a.description AS a_description, a.category AS a_category "
            "FROM registrations r JOIN activities a ON a.id = r.activity_id "
            "WHERE r.student_id = ? ORDER BY r.created_at DESC",
            (student_id,),
        ).fetchall()
        out = []
        for row in rows:
            activity = Activity(
                id=row["activity_id"],
                title=row["a_title"],
                description=row["a_description"],
                category=row["a_category"],
                location=row["a_location"],
                start_time=_dt(row["a_start_time"]),
                capacity=row["a_capacity"],
                registration_mode=row["a_mode"],
                status=row["a_status"],
            )
            out.append((_row_to_registration(row), activity))
        return out

    def next_waitlisted(self, activity_id: int) -> Registration | None:
        """候补队列队首：序号小的优先，同序号按报名时间。"""
        row = self._conn.execute(
            "SELECT * FROM registrations WHERE activity_id = ? AND status = 'waitlisted' "
            "ORDER BY COALESCE(queue_no, 999999), created_at LIMIT 1",
            (activity_id,),
        ).fetchone()
        return _row_to_registration(row) if row else None

    def waitlisted_of(self, activity_id: int) -> list[Registration]:
        rows = self._conn.execute(
            "SELECT * FROM registrations WHERE activity_id = ? AND status = 'waitlisted' "
            "ORDER BY COALESCE(queue_no, 999999), created_at",
            (activity_id,),
        ).fetchall()
        return [_row_to_registration(r) for r in rows]

    def list_by_activity_status(self, activity_id: int, statuses: tuple[str, ...]) -> list[Registration]:
        placeholders = ",".join("?" for _ in statuses)
        rows = self._conn.execute(
            f"SELECT * FROM registrations WHERE activity_id = ? AND status IN ({placeholders}) "
            "ORDER BY created_at",
            (activity_id, *statuses),
        ).fetchall()
        return [_row_to_registration(r) for r in rows]

    def list_pending(self) -> list[tuple[Registration, Activity]]:
        rows = self._conn.execute(
            "SELECT r.*, a.title AS a_title, a.start_time AS a_start_time, a.location AS a_location, "
            "a.registration_mode AS a_mode, a.status AS a_status, a.capacity AS a_capacity, "
            "a.description AS a_description, a.category AS a_category "
            "FROM registrations r JOIN activities a ON a.id = r.activity_id "
            "WHERE r.status = 'pending' ORDER BY r.created_at",
        ).fetchall()
        out = []
        for row in rows:
            activity = Activity(
                id=row["activity_id"],
                title=row["a_title"],
                description=row["a_description"],
                category=row["a_category"],
                location=row["a_location"],
                start_time=_dt(row["a_start_time"]),
                capacity=row["a_capacity"],
                registration_mode=row["a_mode"],
                status=row["a_status"],
            )
            out.append((_row_to_registration(row), activity))
        return out


class MessageRepository:
    """站内消息持久化。event_key 唯一索引保证“同一业务事实只通知一次”。"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add_if_absent(
        self, *, student_id: int, registration_id: int | None, channel: str, event_key: str,
        title: str, body: str,
    ) -> bool:
        now = datetime.now().isoformat(timespec="seconds")
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO notifications(student_id, registration_id, channel, event_key, "
            "title, body, created_at) VALUES (?,?,?,?,?,?,?)",
            (student_id, registration_id, channel, event_key, title, body, now),
        )
        return cur.rowcount > 0

    def list_for_student(self, student_id: int, channel: str = "inapp") -> list[Notification]:
        """学生端只展示站内消息；邮件/其他渠道的投递记录用于审计，不重复打扰学生。"""
        rows = self._conn.execute(
            "SELECT * FROM notifications WHERE student_id = ? AND channel = ? ORDER BY id DESC",
            (student_id, channel),
        ).fetchall()
        return [
            Notification(
                id=r["id"],
                student_id=r["student_id"],
                registration_id=r["registration_id"],
                channel=r["channel"],
                event_key=r["event_key"],
                title=r["title"],
                body=r["body"],
                created_at=_dt(r["created_at"]),
                read_at=_dt(r["read_at"]),
            )
            for r in rows
        ]

    def unread_count(self, student_id: int, channel: str = "inapp") -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE student_id = ? AND channel = ? "
            "AND read_at IS NULL",
            (student_id, channel),
        ).fetchone()
        return int(row["c"])

    def mark_all_read(self, student_id: int, channel: str = "inapp") -> None:
        self._conn.execute(
            "UPDATE notifications SET read_at = ? WHERE student_id = ? AND channel = ? "
            "AND read_at IS NULL",
            (datetime.now().isoformat(timespec="seconds"), student_id, channel),
        )

    def count_for_event(self, event_key: str, channel: str | None = None) -> int:
        if channel is None:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM notifications WHERE event_key = ?", (event_key,)
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM notifications WHERE event_key = ? AND channel = ?",
                (event_key, channel),
            ).fetchone()
        return int(row["c"])

    def exists(self, event_key: str, channel: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM notifications WHERE event_key = ? AND channel = ?", (event_key, channel)
        ).fetchone()
        return row is not None


class NotificationFailureRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def list_all(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM notification_failures ORDER BY id DESC"
        ).fetchall()

    def count(self) -> int:
        return int(
            self._conn.execute("SELECT COUNT(*) AS c FROM notification_failures").fetchone()["c"]
        )
