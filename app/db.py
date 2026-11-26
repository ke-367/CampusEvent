"""SQLite 连接、建表与事务工具。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from flask import Flask, current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    student_no  TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    grade       INTEGER NOT NULL DEFAULT 0   -- 年级 1—4（需求变更 CR-01 新增）
);

CREATE TABLE IF NOT EXISTS activities (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    category          TEXT NOT NULL DEFAULT '通用',
    location          TEXT NOT NULL DEFAULT '',
    start_time        TEXT NOT NULL,           -- ISO 8601，活动开始时间
    capacity          INTEGER NOT NULL,        -- 名额上限，按“已通过”报名计数
    registration_mode TEXT NOT NULL,           -- direct / approval / waitlist / grade_limited
    grade_restriction TEXT NOT NULL DEFAULT '',-- 限报年级集合，如 "2,3"（CR-01 新增）
    status            TEXT NOT NULL DEFAULT 'published',  -- published / deleted（软删除）
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS registrations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL REFERENCES activities(id),
    student_id  INTEGER NOT NULL REFERENCES students(id),
    status      TEXT NOT NULL,                 -- pending / approved / waitlisted / rejected / cancelled
    policy_key  TEXT NOT NULL,                 -- 产生该记录的策略标识，便于审计
    queue_no    INTEGER,                       -- 候补排队序号（需求变更新增，非候补记录为 NULL）
    remark      TEXT NOT NULL DEFAULT '',
    decided_by  TEXT,
    decided_at  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 同一学生对同一活动，最多一条“有效（待审核/已通过/候补中）”报名。
CREATE UNIQUE INDEX IF NOT EXISTS ux_registration_active
    ON registrations(activity_id, student_id)
    WHERE status IN ('pending', 'approved', 'waitlisted');

CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id      INTEGER NOT NULL REFERENCES students(id),
    registration_id INTEGER,
    channel         TEXT NOT NULL DEFAULT 'inapp',
    event_key       TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    read_at         TEXT
);

-- 去重：同一业务事实（事件类型+报名记录+状态）在同一渠道只产生一条通知。
CREATE UNIQUE INDEX IF NOT EXISTS ux_notification_event_key
    ON notifications(event_key, channel);

-- 通知失败留痕，独立于业务事务。
CREATE TABLE IF NOT EXISTS notification_failures (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key  TEXT NOT NULL,
    channel    TEXT NOT NULL,
    error      TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """以自动提交模式建立连接；事务由 transaction() 显式控制。"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_app(app: Flask) -> None:
    app.teardown_appcontext(close_db)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exception: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """业务事务边界：整段要么提交，要么回滚。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def ensure_schema(db_path: str | None = None) -> None:
    """建表 + 增量迁移（幂等）。传入路径时使用独立连接，便于测试与部署初始化。"""
    path = db_path or current_app.config["DATABASE"]
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        _migrate_change_v2(conn)
        _migrate_change_cr01(conn)
    finally:
        conn.close()


def _migrate_change_cr01(conn: sqlite3.Connection) -> None:
    """需求变更 CR-01（年级限定报名）的增量迁移：只加列，不改动历史数据语义。"""
    student_cols = {row["name"] for row in conn.execute("PRAGMA table_info(students)")}
    if "grade" not in student_cols:
        conn.execute("ALTER TABLE students ADD COLUMN grade INTEGER NOT NULL DEFAULT 0")
    activity_cols = {row["name"] for row in conn.execute("PRAGMA table_info(activities)")}
    if "grade_restriction" not in activity_cols:
        conn.execute("ALTER TABLE activities ADD COLUMN grade_restriction TEXT NOT NULL DEFAULT ''")


def _migrate_change_v2(conn: sqlite3.Connection) -> None:
    """需求变更（change-v2）的增量迁移：候补序号列 + 有效报名唯一索引口径扩展。

    只做“加列/重建索引”这类可回滚、可重复执行的变更，不改动历史数据语义。
    """
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(registrations)")}
    if "queue_no" not in columns:
        conn.execute("ALTER TABLE registrations ADD COLUMN queue_no INTEGER")
    conn.execute("DROP INDEX IF EXISTS ux_registration_active")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_registration_active "
        "ON registrations(activity_id, student_id) "
        "WHERE status IN ('pending', 'approved', 'waitlisted')"
    )


def record_notification_failure(db_path: str, event_key: str, channel: str, error: str) -> None:
    """通知失败留痕：使用独立连接/事务，确保业务事务已提交后仍能落库。"""
    from datetime import datetime

    ensure_schema(db_path)
    conn = connect(db_path)
    try:
        with transaction(conn):
            conn.execute(
                "INSERT INTO notification_failures(event_key, channel, error, created_at) "
                "VALUES (?, ?, ?, ?)",
                (event_key, channel, error, datetime.now().isoformat(timespec="seconds")),
            )
    finally:
        conn.close()
