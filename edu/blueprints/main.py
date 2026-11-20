"""Общие страницы: главная, уведомления, профиль, загрузки, предпросмотр Markdown."""
from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect,
                   render_template, request, send_from_directory, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from ..content import render_markdown
from ..db import execute, query
from ..security import ROLE_HOME, login_required, validate_password

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if g.user:
        return redirect(url_for(ROLE_HOME[g.user["role"]]))
    courses = query(
        """SELECT c.*, u.full_name AS teacher_name, cat.name AS category_name,
                  (SELECT COUNT(*) FROM lessons l JOIN sections s ON s.id = l.section_id
                   WHERE s.course_id = c.id) AS lessons_count
           FROM courses c JOIN users u ON u.id = c.teacher_id
           LEFT JOIN categories cat ON cat.id = c.category_id
           WHERE c.is_published = 1
           ORDER BY c.created_at DESC, c.id DESC LIMIT 3"""
    )
    # Реальные цифры платформы (только публичные данные, без персональных)
    stats = {
        "courses": query("SELECT COUNT(*) c FROM courses WHERE is_published = 1", one=True)["c"],
        "lessons": query("""SELECT COUNT(*) c FROM lessons l JOIN sections s ON s.id = l.section_id
                            JOIN courses c ON c.id = s.course_id WHERE c.is_published = 1""", one=True)["c"],
        "teachers": query("SELECT COUNT(*) c FROM users WHERE role = 'teacher' AND is_blocked = 0", one=True)["c"],
        "students": query("SELECT COUNT(*) c FROM users WHERE role = 'student' AND is_blocked = 0", one=True)["c"],
    }
    # Пример урока для витрины: первый пример кода опубликованного курса
    demo = query(
        """SELECT e.title AS example_title, e.language, e.code, l.title AS lesson_title, c.title AS course_title
           FROM code_examples e JOIN lessons l ON l.id = e.lesson_id
           JOIN sections s ON s.id = l.section_id JOIN courses c ON c.id = s.course_id
           WHERE c.is_published = 1 ORDER BY c.id, s.position, l.position, e.position LIMIT 1""",
        one=True)
    return render_template("landing.html", courses=courses, stats=stats, demo=demo)


@bp.route("/uploads/covers/<path:name>")
def cover(name):
    # send_from_directory защищает от выхода за пределы каталога
    return send_from_directory(current_app.config["UPLOAD_DIR"], name, max_age=3600)


@bp.route("/notifications")
@login_required
def notifications():
    rows = query("SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 100", (g.user["id"],))
    return render_template("notifications.html", notifications=rows)


@bp.route("/notifications/read-all", methods=["POST"])
@login_required
def notifications_read_all():
    execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (g.user["id"],))
    return redirect(url_for("main.notifications"))


@bp.route("/notifications/<int:nid>/go")
@login_required
def notification_go(nid):
    n = query("SELECT * FROM notifications WHERE id = ? AND user_id = ?", (nid, g.user["id"]), one=True)
    if not n:
        abort(404)
    execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (nid,))
    link = n["link"] or ""
    # только внутренние ссылки — защита от open redirect
    if link.startswith("/") and not link.startswith("//"):
        return redirect(link)
    return redirect(url_for("main.notifications"))


@bp.route("/api/preview", methods=["POST"])
@login_required
def preview():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", ""))[:50000]
    return jsonify(html=str(render_markdown(text)))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "name":
            name = request.form.get("full_name", "").strip()
            if len(name) < 2 or len(name) > 80:
                flash("Введите имя длиной от 2 до 80 символов.", "error")
            else:
                execute("UPDATE users SET full_name = ? WHERE id = ?", (name, g.user["id"]))
                flash("Имя обновлено.", "success")
        elif action == "password":
            old = request.form.get("old_password", "")
            new = request.form.get("new_password", "")
            if not check_password_hash(g.user["password_hash"], old):
                flash("Текущий пароль указан неверно.", "error")
            elif (err := validate_password(new)):
                flash(err, "error")
            else:
                execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), g.user["id"]))
                flash("Пароль изменён.", "success")
        return redirect(url_for("main.profile"))
    return render_template("profile.html")
