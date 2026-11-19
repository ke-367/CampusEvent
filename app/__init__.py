"""CampusEvent —— 校园活动报名与管理系统（应用工厂 & 依赖组合根）。

分层与依赖方向（上层依赖下层，领域层不依赖 Flask）：

    web/            路由与模板（接口层：把 HTTP 翻译为服务调用）
      ↓
    services/       业务服务：报名 / 审批 / 活动 / 通知（事务边界在这里）
      ↓
    domain/         实体、领域事件、报名策略、名额规则、事件总线（纯 Python，可单测）
      ↓
    repositories    持久化（SQLite）

设计模式落点：
    * 策略模式：domain/policies.py —— 报名规则（直接报名 / 审核报名）
    * 观察者模式：domain/event_bus.py + services/notification_service.py
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from .db import get_db
from .db import init_app as init_db
from .db import record_notification_failure
from .domain.event_bus import EventBus
from .domain.policies import PolicyRegistry
from .domain.rules import CapacityRule
from .repositories import (
    ActivityRepository,
    MessageRepository,
    NotificationFailureRepository,
    RegistrationRepository,
    StudentRepository,
)
from .services.activity_service import ActivityService
from .services.approval_service import ApprovalService
from .services.notification_service import InAppChannel, NotificationService
from .services.registration_service import RegistrationService

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get("CAMPUS_SECRET_KEY", "campus-event-demo-secret"),
        DATABASE=os.environ.get("CAMPUS_DB", str(BASE_DIR / "instance" / "campus_event.db")),
        ADMIN_CODE=os.environ.get("CAMPUS_ADMIN_CODE", "admin123"),
        OUTBOX_DIR=os.environ.get("CAMPUS_OUTBOX", str(BASE_DIR / "outbox")),
        JSON_AS_ASCII=False,
    )
    if config:
        app.config.update(config)

    init_db(app)
    _build_container(app)
    _register_blueprints(app)

    with app.app_context():
        from .db import ensure_schema

        ensure_schema()

    return app


# ---------------------------------------------------------------- 组合根
def _build_container(app: Flask) -> None:
    capacity_rule = CapacityRule()
    registry = PolicyRegistry(capacity_rule=capacity_rule)
    bus = EventBus()

    notification = NotificationService(
        message_repo_factory=lambda: MessageRepository(get_db()),
        channels=[InAppChannel()],
        failure_recorder=lambda event_key, channel, error: record_notification_failure(
            app.config["DATABASE"], event_key, channel, error
        ),
        outbox_dir=app.config["OUTBOX_DIR"],
    )
    bus.subscribe(notification)
    # 兜底：订阅方在执行“消息文案/投递”时整体失败，也要留下痕迹
    bus.set_error_listener(
        lambda event, _handler, exc: record_notification_failure(
            app.config["DATABASE"], getattr(event, "event_key", "unknown"), "bus", repr(exc)
        )
    )

    app.extensions["campus"] = {
        "bus": bus,
        "policy_registry": registry,
        "capacity_rule": capacity_rule,
        "notification": notification,
    }


def container():
    from flask import current_app

    return current_app.extensions["campus"]


def services() -> dict:
    """按请求创建轻量服务对象（同一连接、同一事务边界）。"""
    conn = get_db()
    c = container()
    activities = ActivityRepository(conn)
    registrations = RegistrationRepository(conn)
    return {
        "activity": ActivityService(
            conn, activities, registrations, StudentRepository(conn),
            c["policy_registry"],
        ),
        "registration": RegistrationService(
            conn, activities, registrations, c["policy_registry"], c["bus"], c["capacity_rule"]
        ),
        "approval": ApprovalService(
            conn, activities, registrations, StudentRepository(conn),
            c["capacity_rule"], c["bus"],
        ),
        "messages": MessageRepository(conn),
        "students": StudentRepository(conn),
        "failures": NotificationFailureRepository(conn),
        "activities_repo": activities,
        "registrations_repo": registrations,
    }


def _register_blueprints(app: Flask) -> None:
    from .web.routes import bp as main_bp

    app.register_blueprint(main_bp)
