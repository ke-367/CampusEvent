"""Web 接口层：只做参数校验、调用服务、渲染模板与错误提示。"""
from __future__ import annotations

from datetime import datetime
from functools import wraps

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from .. import container, services
from ..domain.entities import STATUS_LABELS
from ..domain.errors import DomainError

bp = Blueprint("main", __name__)


# ---------------------------------------------------------------- 登录态（演示账号）
def current_student():
    sid = session.get("student_id")
    if not sid:
        return None
    return services()["students"].get(sid)


def is_admin() -> bool:
    return bool(session.get("is_admin"))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_student() is None:
            flash("请先选择学生演示账号登录。", "warn")
            return redirect(url_for("main.login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
            flash("需要管理员身份。", "warn")
            return redirect(url_for("main.login"))
        return view(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------- 模板上下文
@bp.app_context_processor
def inject_globals():
    student = current_student()
    unread = 0
    if student is not None:
        unread = services()["messages"].unread_count(student.id)
    return {
        "nav_student": student,
        "nav_is_admin": is_admin(),
        "nav_unread": unread,
        "status_labels": STATUS_LABELS,
        "now": datetime.now(),
        "supported_modes": container()["policy_registry"].supported_modes,
    }


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("role") == "admin":
            if request.form.get("admin_code") == current_app.config["ADMIN_CODE"]:
                session.clear()
                session["is_admin"] = True
                flash("已进入管理员演示模式。", "ok")
                return redirect(url_for("main.admin_dashboard"))
            flash("管理员口令不正确。", "err")
            return redirect(url_for("main.login"))

        student = services()["students"].get_by_no(request.form.get("student_no", ""))
        if student is None:
            flash("学号不存在，请从演示账号中选择。", "err")
            return redirect(url_for("main.login"))
        session.clear()
        session["student_id"] = student.id
        flash(f"欢迎，{student.name}。", "ok")
        return redirect(url_for("main.index"))

    students = services()["students"].list_all()
    return render_template("login.html", students=students)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.index"))


# ---------------------------------------------------------------- 学生侧
@bp.route("/")
def index():
    activity_svc = services()["activity"]
    activities = activity_svc.list_visible()
    student = current_student()
    mine = {}
    capacity = {}
    waitlist = {}
    for activity in activities:
        capacity[activity.id] = activity_svc.approved_count(activity.id)
        waitlist[activity.id] = len(services()["registrations_repo"].waitlisted_of(activity.id))
        if student is not None:
            regs = services()["registrations_repo"].find_by_student(activity.id, student.id)
            mine[activity.id] = regs[0] if regs else None
    return render_template(
        "index.html", activities=activities, mine=mine, approved=capacity, waitlist=waitlist
    )


@bp.route("/activities/<int:activity_id>")
def activity_detail(activity_id: int):
    svc = services()
    activity = svc["activity"].detail(activity_id)
    snap = svc["registration"].capacity_of(activity)
    approved_regs = svc["registration"].registrations_of(activity_id, ("approved",))
    student = current_student()
    my_regs = (
        svc["registrations_repo"].find_by_student(activity_id, student.id) if student else []
    )
    attendees = [svc["students"].get(r.student_id) for r in approved_regs]
    waitlist = svc["waitlist"].queue_of(activity_id)
    return render_template(
        "activity_detail.html",
        activity=activity,
        capacity=snap,
        my_regs=my_regs,
        attendees=attendees,
        waitlist=waitlist,
    )


@bp.route("/activities/<int:activity_id>/register", methods=["POST"])
@login_required
def register(activity_id: int):
    student = current_student()
    try:
        registration, message = services()["registration"].register(activity_id, student)
    except DomainError as err:
        flash(err.message, "err")
        return redirect(url_for("main.activity_detail", activity_id=activity_id))
    flash(message, "ok")
    return redirect(url_for("main.activity_detail", activity_id=activity_id))


@bp.route("/registrations/<int:registration_id>/cancel", methods=["POST"])
@login_required
def cancel(registration_id: int):
    student = current_student()
    try:
        services()["registration"].cancel(registration_id, student)
    except DomainError as err:
        flash(err.message, "err")
    else:
        flash("已取消报名，名额已释放。", "ok")
    return redirect(request.form.get("next") or url_for("main.my_registrations"))


@bp.route("/me/registrations")
@login_required
def my_registrations():
    student = current_student()
    rows = services()["registration"].my_registrations(student.id)
    return render_template("my_registrations.html", rows=rows)


@bp.route("/me/messages")
@login_required
def my_messages():
    student = current_student()
    messages = services()["messages"].list_for_student(student.id)
    return render_template("messages.html", messages=messages)


@bp.route("/me/messages/read", methods=["POST"])
@login_required
def read_messages():
    student = current_student()
    services()["messages"].mark_all_read(student.id)
    flash("已全部标记为已读。", "ok")
    return redirect(url_for("main.my_messages"))


# ---------------------------------------------------------------- 管理员侧
@bp.route("/admin")
@admin_required
def admin_dashboard():
    svc = services()
    rows = svc["approval"].pending()
    stats = svc["activity"].stats()
    activities = svc["activity"].list_all()
    approved = {a.id: svc["activity"].approved_count(a.id) for a in activities}
    waitlist = {
        a.id: len(svc["registrations_repo"].waitlisted_of(a.id)) for a in activities
    }
    outbox = _recent_outbox()
    return render_template(
        "admin_dashboard.html", pending=rows, stats=stats, activities=activities,
        approved=approved, waitlist=waitlist, failures=svc["failures"].list_all(),
        outbox=outbox, channels=container()["notification"].channel_names,
    )


def _recent_outbox(limit: int = 8) -> list[dict]:
    """邮件渠道的“已投递”证据：列出最近写出的 .eml 文件。"""
    from pathlib import Path

    folder = Path(current_app.config["OUTBOX_DIR"])
    if not folder.exists():
        return []
    files = sorted(folder.glob("*.eml"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    return [
        {"name": p.name, "size": p.stat().st_size,
         "time": datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M:%S")}
        for p in files
    ]


@bp.route("/admin/activities/create", methods=["POST"])
@admin_required
def create_activity():
    try:
        activity = services()["activity"].create(request.form)
    except DomainError as err:
        flash(err.message, "err")
        return redirect(url_for("main.admin_dashboard"))
    flash(f"活动「{activity.title}」已发布。", "ok")
    return redirect(url_for("main.admin_dashboard"))


@bp.route("/admin/activities/<int:activity_id>/delete", methods=["POST"])
@admin_required
def delete_activity(activity_id: int):
    try:
        activity, affected = services()["activity"].remove(activity_id)
    except DomainError as err:
        flash(err.message, "err")
    else:
        note = f"，同时保留 {affected} 条历史报名记录" if affected else ""
        flash(f"活动「{activity.title}」已软删除{note}。", "ok")
    return redirect(url_for("main.admin_dashboard"))


@bp.route("/admin/registrations/<int:registration_id>/approve", methods=["POST"])
@admin_required
def approve(registration_id: int):
    try:
        services()["approval"].approve(registration_id, "管理员")
    except DomainError as err:
        flash(err.message, "err")
    else:
        flash("已批准该报名，并通知学生。", "ok")
    return redirect(url_for("main.admin_dashboard"))


@bp.route("/admin/registrations/<int:registration_id>/reject", methods=["POST"])
@admin_required
def reject(registration_id: int):
    try:
        services()["approval"].reject(
            registration_id, "管理员", request.form.get("reason", "").strip()
        )
    except DomainError as err:
        flash(err.message, "err")
    else:
        flash("已拒绝该报名，并通知学生。", "ok")
    return redirect(url_for("main.admin_dashboard"))
