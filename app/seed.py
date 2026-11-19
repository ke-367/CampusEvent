"""初始化演示数据：python -m app.seed [--reset]

--reset 会清空 instance 下的数据库重建，便于演示前恢复干净状态。
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

from app import create_app
from app.db import connect, ensure_schema, transaction

STUDENTS = [
    ("S2024001", "张小明", "zhangxm@example.edu.cn"),
    ("S2024002", "李小红", "lixh@example.edu.cn"),
    ("S2024003", "王大力", "wangdl@example.edu.cn"),
]

ACTIVITIES = [
    dict(
        title="校园迎新晚会",
        description="面向全体新生的迎新晚会，含歌舞、器乐与社团展演。凭报名记录入场。",
        category="文艺",
        location="大学生活动中心 报告厅",
        start_offset_hours=72,
        capacity=120,
        registration_mode="direct",
    ),
    dict(
        title="程序设计马拉松（24h）",
        description="三人一组，24 小时内完成一个校园服务类小程序。需提交作品说明，名额有限。",
        category="科技",
        location="计算机学院 实验楼 A305",
        start_offset_hours=120,
        capacity=20,
        registration_mode="approval",
    ),
    dict(
        title="摄影基础讲座",
        description="从构图到用光，讲座后安排外拍实践。教室座位有限，需管理员审核。",
        category="讲座",
        location="综合楼 201",
        start_offset_hours=48,
        capacity=3,
        registration_mode="approval",
    ),
    dict(
        title="社区图书馆志愿服务",
        description="周末赴社区图书馆整理书架、协助借阅登记，可计志愿时长。",
        category="志愿",
        location="湘湖社区图书馆",
        start_offset_hours=96,
        capacity=15,
        registration_mode="direct",
    ),
]


def seed(reset: bool = False) -> None:
    app = create_app()
    db_path = app.config["DATABASE"]
    if reset:
        from pathlib import Path

        for suffix in ("", "-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)

    ensure_schema(db_path)
    conn = connect(db_path)
    now = datetime.now()
    try:
        with transaction(conn):
            existing = conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()["c"]
            if existing:
                print("数据库已有数据，跳过初始化（如需重置请加 --reset）")
                return
            for no, name, email in STUDENTS:
                conn.execute(
                    "INSERT INTO students(student_no, name, email) VALUES (?,?,?)",
                    (no, name, email),
                )
            for item in ACTIVITIES:
                conn.execute(
                    "INSERT INTO activities(title, description, category, location, start_time, "
                    "capacity, registration_mode, status, created_at) "
                    "VALUES (?,?,?,?,?,?,?,'published',?)",
                    (
                        item["title"],
                        item["description"],
                        item["category"],
                        item["location"],
                        (now + timedelta(hours=item["start_offset_hours"])).isoformat(timespec="minutes"),
                        item["capacity"],
                        item["registration_mode"],
                        now.isoformat(timespec="seconds"),
                    ),
                )
        print(f"演示数据已写入：{db_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
