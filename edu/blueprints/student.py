"""Кабинет студента."""
from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   url_for)

from .. import services
from ..charts import line_chart
from ..db import execute, query
from ..security import role_required

bp = Blueprint("student", __name__, url_prefix="/student")

MAX_TEXT = 20000


@bp.before_request
@role_required("student")
def _guard():
    pass


# ---------- доступ ----------
def _is_enrolled(course_id: int) -> bool:
    return query("SELECT 1 FROM enrollments WHERE student_id = ? AND course_id = ?",
                 (g.user["id"], course_id), one=True) is not None


def _course_or_404(course_id: int):
    course = query(
        """SELECT c.*, u.full_name AS teacher_name, cat.name AS category_name
           FROM courses c JOIN users u ON u.id = c.teacher_id
           LEFT JOIN categories cat ON cat.id = c.category_id WHERE c.id = ?""",
        (course_id,), one=True)
    if not course:
        abort(404)
    return course


def _enrolled_course_or_403(course_id: int):
    course = _course_or_404(course_id)
    if not _is_enrolled(course_id):
        flash("Сначала запишитесь на курс.", "info")
        abort(403)
    return course


def _grade_points(history):
    return [(services.parse_dt(h["reviewed_at"]).strftime("%d.%m") if h["reviewed_at"] else "", h["score"])
            for h in history]


# ---------- главная ----------
@bp.route("/")
def dashboard():
    ov = services.student_overview(g.user["id"])
    todo = []
    for item in ov["items"]:
        c = item["course"]
        subs = services.latest_submissions(g.user["id"], c["id"])
        for a in query("SELECT * FROM assignments WHERE course_id = ? ORDER BY position, id", (c["id"],)):
            sub = subs.get(a["id"])
            if sub is None or sub["status"] == "revision":
                todo.append({"a": a, "course": c, "sub": sub})
    todo.sort(key=lambda t: (t["sub"] is None, t["a"]["due_date"] or "9999-12-31"))
    recent = query(
        """SELECT s.*, a.title AS assignment_title, a.course_id, c.title AS course_title
           FROM submissions s JOIN assignments a ON a.id = s.assignment_id
           JOIN courses c ON c.id = a.course_id
           WHERE s.student_id = ? AND s.status IN ('checked', 'revision')
           ORDER BY s.reviewed_at DESC, s.id DESC LIMIT 5""", (g.user["id"],))
    chart = line_chart(_grade_points(ov["history"][-12:]))
    # Куда продолжить: курс, который студент открывал последним и где ещё есть что делать
    visits = {r["course_id"]: r["last_viewed_at"] for r in query(
        "SELECT course_id, last_viewed_at FROM lesson_visits WHERE student_id = ?", (g.user["id"],))}
    candidates = [i for i in ov["items"] if i["next_step"]]
    continue_item = max(candidates, key=lambda i: visits.get(i["course"]["id"], "")) if candidates else None
    return render_template("student/dashboard.html", ov=ov, todo=todo[:6], recent=recent, chart=chart,
                           continue_item=continue_item)


# ---------- каталог ----------
@bp.route("/catalog")
def catalog():
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", type=int)
    level = request.args.get("level", "")
    sql = """SELECT c.*, u.full_name AS teacher_name, cat.name AS category_name,
                    (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id) AS students,
                    (SELECT COUNT(*) FROM lessons l JOIN sections s ON s.id = l.section_id
                     WHERE s.course_id = c.id) AS lessons_count,
                    EXISTS (SELECT 1 FROM enrollments e WHERE e.course_id = c.id AND e.student_id = ?) AS enrolled
             FROM courses c JOIN users u ON u.id = c.teacher_id
             LEFT JOIN categories cat ON cat.id = c.category_id
             WHERE c.is_published = 1"""
    params = [g.user["id"]]
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        sql += " AND (c.title LIKE ? ESCAPE '\\' OR c.description LIKE ? ESCAPE '\\')"
        params += [like, like]
    if cat:
        sql += " AND c.category_id = ?"
        params.append(cat)
    if level in services.LEVEL_LABELS:
        sql += " AND c.level = ?"
        params.append(level)
    sql += " ORDER BY c.created_at DESC, c.id DESC"
    courses = query(sql, params)
    categories = query("SELECT * FROM categories ORDER BY name")
    return render_template("student/catalog.html", courses=courses, categories=categories,
                           q=q, cat=cat, level=level)


@bp.route("/my-courses")
def my_courses():
    ov = services.student_overview(g.user["id"])
    return render_template("student/my_courses.html", ov=ov)


# ---------- курс ----------
@bp.route("/course/<int:course_id>")
def course(course_id):
    c = _course_or_404(course_id)
    enrolled = _is_enrolled(course_id)
    if not enrolled and not c["is_published"]:
        abort(404)
    sections, loose = services.course_tree(course_id)
    ctx = {"course": c, "sections": sections, "loose": loose, "enrolled": enrolled}
    if enrolled:
        ctx.update(
            progress=services.course_progress(g.user["id"], course_id),
            done=services.completed_lesson_ids(g.user["id"], course_id),
            subs=services.latest_submissions(g.user["id"], course_id),
            next_lesson=services.course_next_lesson(g.user["id"], course_id),
            next_step=services.course_next_step(g.user["id"], course_id),
        )
    return render_template("student/course.html", **ctx)


@bp.route("/course/<int:course_id>/enroll", methods=["POST"])
def enroll(course_id):
    c = _course_or_404(course_id)
    if not c["is_published"]:
        abort(404)
    if _is_enrolled(course_id):
        flash("Вы уже записаны на этот курс.", "info")
    else:
        execute("INSERT INTO enrollments (student_id, course_id) VALUES (?, ?)", (g.user["id"], course_id))
        services.notify(c["teacher_id"], f"Новый студент на курсе «{c['title']}»: {g.user['full_name']}",
                        url_for("teacher.course_students", course_id=course_id))
        flash(f"Вы записались на курс «{c['title']}». Приятного обучения!", "success")
    return redirect(url_for("student.course", course_id=course_id))


# ---------- уроки ----------
@bp.route("/lesson/<int:lesson_id>")
def lesson(lesson_id):
    row = query("""SELECT l.*, s.course_id, s.title AS section_title FROM lessons l
                   JOIN sections s ON s.id = l.section_id WHERE l.id = ?""", (lesson_id,), one=True)
    if not row:
        abort(404)
    c = _enrolled_course_or_403(row["course_id"])
    execute(
        """INSERT INTO lesson_visits (student_id, course_id, lesson_id, last_viewed_at)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(student_id, course_id) DO UPDATE SET
             lesson_id = excluded.lesson_id, last_viewed_at = excluded.last_viewed_at""",
        (g.user["id"], c["id"], lesson_id))
    examples = query("SELECT * FROM code_examples WHERE lesson_id = ? ORDER BY position, id", (lesson_id,))
    ordered = query(
        """SELECT l.id, l.title FROM lessons l JOIN sections s ON s.id = l.section_id
           WHERE s.course_id = ? ORDER BY s.position, s.id, l.position, l.id""", (c["id"],))
    ids = [r["id"] for r in ordered]
    idx = ids.index(lesson_id)
    prev_l = ordered[idx - 1] if idx > 0 else None
    next_l = ordered[idx + 1] if idx < len(ids) - 1 else None
    done = lesson_id in services.completed_lesson_ids(g.user["id"], c["id"])
    return render_template("student/lesson.html", lesson=row, course=c, examples=examples,
                           prev_l=prev_l, next_l=next_l, done=done, ordered=ordered, position=idx + 1)


@bp.route("/lesson/<int:lesson_id>/complete", methods=["POST"])
def lesson_complete(lesson_id):
    row = query("""SELECT l.id, s.course_id FROM lessons l JOIN sections s ON s.id = l.section_id
                   WHERE l.id = ?""", (lesson_id,), one=True)
    if not row:
        abort(404)
    _enrolled_course_or_403(row["course_id"])
    if request.form.get("undo"):
        execute("DELETE FROM lesson_progress WHERE student_id = ? AND lesson_id = ?", (g.user["id"], lesson_id))
        flash("Урок снова отмечен как не изученный.", "info")
    else:
        execute("INSERT OR IGNORE INTO lesson_progress (student_id, lesson_id) VALUES (?, ?)",
                (g.user["id"], lesson_id))
        flash("Урок отмечен как изученный.", "success")
    nxt = request.form.get("next")
    if nxt and nxt.isdigit():
        return redirect(url_for("student.lesson", lesson_id=int(nxt)))
    return redirect(url_for("student.lesson", lesson_id=lesson_id))


# ---------- задания ----------
def _assignment_or_404(assignment_id):
    a = query("""SELECT a.*, c.title AS course_title, c.teacher_id FROM assignments a
                 JOIN courses c ON c.id = a.course_id WHERE a.id = ?""", (assignment_id,), one=True)
    if not a:
        abort(404)
    _enrolled_course_or_403(a["course_id"])
    return a


@bp.route("/assignment/<int:assignment_id>")
def assignment(assignment_id):
    a = _assignment_or_404(assignment_id)
    attempts = query("SELECT * FROM submissions WHERE assignment_id = ? AND student_id = ? ORDER BY attempt",
                     (assignment_id, g.user["id"]))
    latest = attempts[-1] if attempts else None
    can_submit = latest is None or latest["status"] == "revision"
    status = latest["status"] if latest else "not_started"
    return render_template("student/assignment.html", a=a, attempts=attempts, latest=latest,
                           can_submit=can_submit, status=status)


@bp.route("/assignment/<int:assignment_id>/submit", methods=["POST"])
def submit(assignment_id):
    a = _assignment_or_404(assignment_id)
    answer = request.form.get("answer_text", "").strip()
    code = request.form.get("code", "").rstrip()
    if not answer and not code:
        flash("Добавьте текстовый ответ или код решения.", "error")
        return redirect(url_for("student.assignment", assignment_id=assignment_id))
    if len(answer) > MAX_TEXT or len(code) > MAX_TEXT:
        flash("Решение слишком длинное (максимум 20 000 символов в каждом поле).", "error")
        return redirect(url_for("student.assignment", assignment_id=assignment_id))
    last = query("SELECT * FROM submissions WHERE assignment_id = ? AND student_id = ? ORDER BY attempt DESC LIMIT 1",
                 (assignment_id, g.user["id"]), one=True)
    if last and last["status"] != "revision":
        flash("Работа уже отправлена. Дождитесь проверки преподавателя.", "info")
        return redirect(url_for("student.assignment", assignment_id=assignment_id))
    attempt = (last["attempt"] + 1) if last else 1
    sid = execute(
        "INSERT INTO submissions (assignment_id, student_id, attempt, answer_text, code) VALUES (?, ?, ?, ?, ?)",
        (assignment_id, g.user["id"], attempt, answer, code))
    verb = "повторно отправил исправленное решение" if attempt > 1 else "отправил решение"
    services.notify(a["teacher_id"], f"{g.user['full_name']} {verb}: «{a['title']}» ({a['course_title']})",
                    url_for("teacher.review", submission_id=sid))
    flash("Решение отправлено преподавателю на проверку.", "success")
    return redirect(url_for("student.assignment", assignment_id=assignment_id))


# ---------- успеваемость ----------
@bp.route("/grades")
def grades():
    course_id = request.args.get("course", type=int)
    ov = services.student_overview(g.user["id"])
    history = services.grade_history(g.user["id"], course_id) if course_id else ov["history"]
    chart = line_chart(_grade_points(history))
    return render_template("student/grades.html", ov=ov, history=list(reversed(history)),
                           chart=chart, course_id=course_id)
