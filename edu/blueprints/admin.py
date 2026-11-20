"""Кабинет администратора."""
from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   url_for)

from .. import services, uploads
from ..charts import bar_chart
from ..db import execute, query
from ..security import ROLE_NAMES, role_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
@role_required("admin")
def _guard():
    pass


def _count(sql, params=()):
    return query(sql, params, one=True)["c"]


@bp.route("/")
def dashboard():
    stats = {
        "students": _count("SELECT COUNT(*) c FROM users WHERE role = 'student'"),
        "teachers": _count("SELECT COUNT(*) c FROM users WHERE role = 'teacher'"),
        "admins": _count("SELECT COUNT(*) c FROM users WHERE role = 'admin'"),
        "courses": _count("SELECT COUNT(*) c FROM courses"),
        "published": _count("SELECT COUNT(*) c FROM courses WHERE is_published = 1"),
        "enrollments": _count("SELECT COUNT(*) c FROM enrollments"),
        "submissions": _count("SELECT COUNT(*) c FROM submissions"),
        "pending": _count("SELECT COUNT(*) c FROM submissions WHERE status = 'review'"),
    }
    scores = [r["score"] for r in query("SELECT score FROM submissions WHERE status = 'checked' AND score IS NOT NULL")]
    chart = bar_chart([str(i) for i in range(1, 11)], [scores.count(i) for i in range(1, 11)])
    recent_users = query("SELECT * FROM users ORDER BY id DESC LIMIT 6")
    top_courses = query(
        """SELECT c.id, c.title, u.full_name AS teacher_name,
                  (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id) AS students
           FROM courses c JOIN users u ON u.id = c.teacher_id ORDER BY students DESC, c.id LIMIT 5""")
    return render_template("admin/dashboard.html", stats=stats, chart=chart, recent_users=recent_users,
                           top_courses=top_courses)


# ---------- пользователи ----------
@bp.route("/users")
def users():
    q = request.args.get("q", "").strip()
    role = request.args.get("role", "")
    sql, params = "SELECT * FROM users WHERE 1=1", []
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (full_name LIKE ? ESCAPE '\\' OR email LIKE ? ESCAPE '\\')"
        params += [like, like]
    if role in ROLE_NAMES:
        sql += " AND role = ?"
        params.append(role)
    sql += " ORDER BY id DESC LIMIT 300"
    return render_template("admin/users.html", users=query(sql, params), q=q, role=role, ROLE_NAMES=ROLE_NAMES)


def _target(user_id):
    u = query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if not u:
        abort(404)
    return u


def _is_last_active_admin(u):
    return u["role"] == "admin" and not u["is_blocked"] and \
        _count("SELECT COUNT(*) c FROM users WHERE role = 'admin' AND is_blocked = 0") <= 1


@bp.route("/users/<int:user_id>/role", methods=["POST"])
def user_role(user_id):
    u = _target(user_id)
    role = request.form.get("role")
    if role not in ROLE_NAMES:
        abort(400)
    if u["id"] == g.user["id"]:
        flash("Нельзя изменить собственную роль.", "error")
    elif _is_last_active_admin(u) and role != "admin":
        flash("Нельзя лишить прав последнего администратора.", "error")
    else:
        execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        services.notify(user_id, f"Ваша роль изменена: {ROLE_NAMES[role]}")
        flash(f"Роль пользователя {u['full_name']} изменена на «{ROLE_NAMES[role]}».", "success")
    return redirect(request.referrer or url_for("admin.users"))


@bp.route("/users/<int:user_id>/block", methods=["POST"])
def user_block(user_id):
    u = _target(user_id)
    if u["id"] == g.user["id"]:
        flash("Нельзя заблокировать самого себя.", "error")
    elif _is_last_active_admin(u):
        flash("Нельзя заблокировать последнего администратора.", "error")
    else:
        new = 0 if u["is_blocked"] else 1
        execute("UPDATE users SET is_blocked = ? WHERE id = ?", (new, user_id))
        flash(f"Пользователь {u['full_name']} {'заблокирован' if new else 'разблокирован'}.", "success")
    return redirect(request.referrer or url_for("admin.users"))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
def user_delete(user_id):
    u = _target(user_id)
    if u["id"] == g.user["id"]:
        flash("Нельзя удалить собственный аккаунт.", "error")
    elif _is_last_active_admin(u):
        flash("Нельзя удалить последнего администратора.", "error")
    else:
        for c in query("SELECT cover_path FROM courses WHERE teacher_id = ?", (user_id,)):
            uploads.delete_cover(c["cover_path"])
        execute("DELETE FROM users WHERE id = ?", (user_id,))
        flash(f"Пользователь {u['full_name']} удалён вместе со связанными данными.", "info")
    return redirect(url_for("admin.users"))


# ---------- курсы ----------
@bp.route("/courses")
def courses():
    rows = query(
        """SELECT c.*, u.full_name AS teacher_name, cat.name AS category_name,
                  (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id) AS students,
                  (SELECT COUNT(*) FROM lessons l JOIN sections s ON s.id = l.section_id
                   WHERE s.course_id = c.id) AS lessons_count
           FROM courses c JOIN users u ON u.id = c.teacher_id
           LEFT JOIN categories cat ON cat.id = c.category_id ORDER BY c.id DESC""")
    return render_template("admin/courses.html", courses=rows)


@bp.route("/courses/<int:course_id>/toggle", methods=["POST"])
def course_toggle(course_id):
    c = query("SELECT * FROM courses WHERE id = ?", (course_id,), one=True)
    if not c:
        abort(404)
    new = 0 if c["is_published"] else 1
    execute("UPDATE courses SET is_published = ? WHERE id = ?", (new, course_id))
    services.notify(c["teacher_id"],
                    f"Курс «{c['title']}» {'опубликован' if new else 'скрыт'} администратором")
    flash("Курс опубликован." if new else "Курс скрыт из каталога.", "success")
    return redirect(url_for("admin.courses"))


@bp.route("/courses/<int:course_id>/delete", methods=["POST"])
def course_delete(course_id):
    c = query("SELECT * FROM courses WHERE id = ?", (course_id,), one=True)
    if not c:
        abort(404)
    uploads.delete_cover(c["cover_path"])
    execute("DELETE FROM courses WHERE id = ?", (course_id,))
    services.notify(c["teacher_id"], f"Курс «{c['title']}» удалён администратором")
    flash(f"Курс «{c['title']}» удалён.", "info")
    return redirect(url_for("admin.courses"))


# ---------- категории ----------
@bp.route("/categories", methods=["GET", "POST"])
def categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not (2 <= len(name) <= 40):
            flash("Название категории — от 2 до 40 символов.", "error")
        elif query("SELECT 1 FROM categories WHERE name = ?", (name,), one=True):
            flash("Такая категория уже существует.", "error")
        else:
            execute("INSERT INTO categories (name) VALUES (?)", (name,))
            flash("Категория добавлена.", "success")
        return redirect(url_for("admin.categories"))
    rows = query("""SELECT cat.*, (SELECT COUNT(*) FROM courses c WHERE c.category_id = cat.id) AS courses_count
                    FROM categories cat ORDER BY name""")
    return render_template("admin/categories.html", categories=rows)


@bp.route("/categories/<int:cat_id>/rename", methods=["POST"])
def category_rename(cat_id):
    name = request.form.get("name", "").strip()
    clash = query("SELECT 1 FROM categories WHERE name = ? AND id != ?", (name, cat_id), one=True)
    if not (2 <= len(name) <= 40):
        flash("Название категории — от 2 до 40 символов.", "error")
    elif clash:
        flash("Такая категория уже существует.", "error")
    else:
        execute("UPDATE categories SET name = ? WHERE id = ?", (name, cat_id))
        flash("Категория переименована.", "success")
    return redirect(url_for("admin.categories"))


@bp.route("/categories/<int:cat_id>/delete", methods=["POST"])
def category_delete(cat_id):
    execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    flash("Категория удалена. Курсы остались без категории.", "info")
    return redirect(url_for("admin.categories"))
