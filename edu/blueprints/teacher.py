"""Кабинет преподавателя."""
from datetime import date

from flask import (Blueprint, abort, flash, g, redirect, render_template, request,
                   url_for)

from .. import services, uploads
from ..charts import bar_chart, line_chart
from ..db import execute, get_db, query
from ..security import role_required

bp = Blueprint("teacher", __name__, url_prefix="/teacher")


@bp.before_request
@role_required("teacher")
def _guard():
    pass


# ====================== проверка владения ======================
def _own_course(course_id):
    c = query("SELECT * FROM courses WHERE id = ? AND teacher_id = ?", (course_id, g.user["id"]), one=True)
    if not c:
        abort(404)
    return c


def _own_section(section_id):
    s = query("""SELECT s.*, c.title AS course_title FROM sections s
                 JOIN courses c ON c.id = s.course_id
                 WHERE s.id = ? AND c.teacher_id = ?""", (section_id, g.user["id"]), one=True)
    if not s:
        abort(404)
    return s


def _own_lesson(lesson_id):
    l = query("""SELECT l.*, s.course_id, s.title AS section_title, c.title AS course_title
                 FROM lessons l JOIN sections s ON s.id = l.section_id
                 JOIN courses c ON c.id = s.course_id
                 WHERE l.id = ? AND c.teacher_id = ?""", (lesson_id, g.user["id"]), one=True)
    if not l:
        abort(404)
    return l


def _own_assignment(aid):
    a = query("""SELECT a.*, c.title AS course_title FROM assignments a
                 JOIN courses c ON c.id = a.course_id
                 WHERE a.id = ? AND c.teacher_id = ?""", (aid, g.user["id"]), one=True)
    if not a:
        abort(404)
    return a


def _next_pos(table, col, val):
    row = query(f"SELECT COALESCE(MAX(position), 0) + 1 AS p FROM {table} WHERE {col} = ?", (val,), one=True)
    return row["p"]


_MOVABLE = {"sections": "course_id", "lessons": "section_id", "assignments": "course_id"}


def _move(table, item_id, direction):
    """Меняет элемент местами с соседом и перенумеровывает позиции."""
    col = _MOVABLE[table]
    db = get_db()
    row = db.execute(f"SELECT id, {col} AS parent FROM {table} WHERE id = ?", (item_id,)).fetchone()
    siblings = [r["id"] for r in db.execute(
        f"SELECT id FROM {table} WHERE {col} = ? ORDER BY position, id", (row["parent"],))]
    i = siblings.index(item_id)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(siblings):
        siblings[i], siblings[j] = siblings[j], siblings[i]
    for pos, sid in enumerate(siblings, start=1):
        db.execute(f"UPDATE {table} SET position = ? WHERE id = ?", (pos, sid))
    db.commit()


# ====================== главная ======================
@bp.route("/")
def dashboard():
    uid = g.user["id"]
    courses = query(
        """SELECT c.*, cat.name AS category_name,
                  (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id) AS students,
                  (SELECT COUNT(*) FROM submissions s JOIN assignments a ON a.id = s.assignment_id
                   WHERE a.course_id = c.id AND s.status = 'review') AS pending
           FROM courses c LEFT JOIN categories cat ON cat.id = c.category_id
           WHERE c.teacher_id = ? ORDER BY c.created_at DESC, c.id DESC""", (uid,))
    queue = query(
        """SELECT s.*, a.title AS assignment_title, c.title AS course_title, u.full_name AS student_name
           FROM submissions s JOIN assignments a ON a.id = s.assignment_id
           JOIN courses c ON c.id = a.course_id JOIN users u ON u.id = s.student_id
           WHERE c.teacher_id = ? AND s.status = 'review'
           ORDER BY s.submitted_at LIMIT 8""", (uid,))
    totals = {
        "courses": len(courses),
        "students": query("""SELECT COUNT(DISTINCT e.student_id) c FROM enrollments e
                             JOIN courses c ON c.id = e.course_id WHERE c.teacher_id = ?""", (uid,), one=True)["c"],
        "pending": sum(c["pending"] for c in courses),
        "checked": query("""SELECT COUNT(*) c FROM submissions s JOIN assignments a ON a.id = s.assignment_id
                            JOIN courses c ON c.id = a.course_id
                            WHERE c.teacher_id = ? AND s.status = 'checked'""", (uid,), one=True)["c"],
    }
    scores = [r["score"] for r in query(
        """SELECT s.score FROM submissions s JOIN assignments a ON a.id = s.assignment_id
           JOIN courses c ON c.id = a.course_id
           WHERE c.teacher_id = ? AND s.status = 'checked' AND s.score IS NOT NULL""", (uid,))]
    dist = [scores.count(i) for i in range(1, 11)]
    chart = bar_chart([str(i) for i in range(1, 11)], dist)
    return render_template("teacher/dashboard.html", courses=courses, queue=queue, totals=totals, chart=chart)


@bp.route("/courses")
def courses():
    rows = query(
        """SELECT c.*, cat.name AS category_name,
                  (SELECT COUNT(*) FROM enrollments e WHERE e.course_id = c.id) AS students,
                  (SELECT COUNT(*) FROM lessons l JOIN sections s ON s.id = l.section_id
                   WHERE s.course_id = c.id) AS lessons_count,
                  (SELECT COUNT(*) FROM assignments a WHERE a.course_id = c.id) AS assignments_count
           FROM courses c LEFT JOIN categories cat ON cat.id = c.category_id
           WHERE c.teacher_id = ? ORDER BY c.created_at DESC, c.id DESC""", (g.user["id"],))
    return render_template("teacher/courses.html", courses=rows)


# ====================== курс: создание и параметры ======================
def _course_form_data():
    f = request.form
    data = {
        "title": f.get("title", "").strip(),
        "description": f.get("description", "").strip(),
        "level": f.get("level", "beginner"),
        "category_id": f.get("category_id", type=int),
        "new_category": f.get("new_category", "").strip(),
    }
    error = None
    if not (3 <= len(data["title"]) <= 120):
        error = "Название курса — от 3 до 120 символов."
    elif len(data["description"]) > 4000:
        error = "Описание не должно превышать 4000 символов."
    elif data["level"] not in services.LEVEL_LABELS:
        error = "Выберите уровень сложности."
    elif len(data["new_category"]) > 40:
        error = "Название категории — не длиннее 40 символов."
    return data, error


def _resolve_category(data):
    if data["new_category"]:
        row = query("SELECT id FROM categories WHERE name = ?", (data["new_category"],), one=True)
        return row["id"] if row else execute("INSERT INTO categories (name) VALUES (?)", (data["new_category"],))
    if data["category_id"] and query("SELECT 1 FROM categories WHERE id = ?", (data["category_id"],), one=True):
        return data["category_id"]
    return None


@bp.route("/course/new", methods=["GET", "POST"])
def course_new():
    categories = query("SELECT * FROM categories ORDER BY name")
    form = {"title": "", "description": "", "level": "beginner", "category_id": None}
    if request.method == "POST":
        data, error = _course_form_data()
        form = data
        cover = None
        if not error:
            try:
                cover = uploads.save_cover(request.files.get("cover"))
            except ValueError as e:
                error = str(e)
        if error:
            flash(error, "error")
        else:
            cid = execute(
                """INSERT INTO courses (title, description, category_id, level, teacher_id, cover_path)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (data["title"], data["description"], _resolve_category(data), data["level"], g.user["id"], cover))
            flash("Курс создан. Теперь добавьте разделы и уроки.", "success")
            return redirect(url_for("teacher.course_manage", course_id=cid))
    return render_template("teacher/course_form.html", form=form, categories=categories, course=None)


@bp.route("/course/<int:course_id>/edit", methods=["GET", "POST"])
def course_edit(course_id):
    c = _own_course(course_id)
    categories = query("SELECT * FROM categories ORDER BY name")
    form = dict(c)
    if request.method == "POST":
        data, error = _course_form_data()
        form = {**form, **data}
        new_cover = None
        if not error:
            try:
                new_cover = uploads.save_cover(request.files.get("cover"))
            except ValueError as e:
                error = str(e)
        if error:
            flash(error, "error")
        else:
            cover = c["cover_path"]
            if new_cover:
                uploads.delete_cover(cover)
                cover = new_cover
            elif request.form.get("remove_cover"):
                uploads.delete_cover(cover)
                cover = None
            execute("""UPDATE courses SET title = ?, description = ?, category_id = ?, level = ?, cover_path = ?
                       WHERE id = ?""",
                    (data["title"], data["description"], _resolve_category(data), data["level"], cover, course_id))
            flash("Параметры курса сохранены.", "success")
            return redirect(url_for("teacher.course_manage", course_id=course_id))
    return render_template("teacher/course_form.html", form=form, categories=categories, course=c)


@bp.route("/course/<int:course_id>/publish", methods=["POST"])
def course_publish(course_id):
    c = _own_course(course_id)
    new = 0 if c["is_published"] else 1
    if new:
        lessons = query("""SELECT COUNT(*) c FROM lessons l JOIN sections s ON s.id = l.section_id
                           WHERE s.course_id = ?""", (course_id,), one=True)["c"]
        if lessons == 0:
            flash("Добавьте хотя бы один урок перед публикацией.", "error")
            return redirect(url_for("teacher.course_manage", course_id=course_id))
    execute("UPDATE courses SET is_published = ? WHERE id = ?", (new, course_id))
    flash("Курс опубликован и виден студентам." if new else "Курс скрыт из каталога.", "success")
    return redirect(url_for("teacher.course_manage", course_id=course_id))


@bp.route("/course/<int:course_id>/delete", methods=["POST"])
def course_delete(course_id):
    c = _own_course(course_id)
    uploads.delete_cover(c["cover_path"])
    execute("DELETE FROM courses WHERE id = ?", (course_id,))
    flash(f"Курс «{c['title']}» удалён вместе с уроками и работами студентов.", "info")
    return redirect(url_for("teacher.courses"))


# ====================== курс: структура ======================
@bp.route("/course/<int:course_id>")
def course_manage(course_id):
    c = _own_course(course_id)
    sections, loose = services.course_tree(course_id)
    stats = services.course_stats(course_id)
    return render_template("teacher/course_manage.html", course=c, sections=sections, loose=loose, stats=stats)


@bp.route("/course/<int:course_id>/section/add", methods=["POST"])
def section_add(course_id):
    _own_course(course_id)
    title = request.form.get("title", "").strip()
    if not (2 <= len(title) <= 120):
        flash("Название раздела — от 2 до 120 символов.", "error")
    else:
        execute("INSERT INTO sections (course_id, title, position) VALUES (?, ?, ?)",
                (course_id, title, _next_pos("sections", "course_id", course_id)))
        flash("Раздел добавлен.", "success")
    return redirect(url_for("teacher.course_manage", course_id=course_id))


@bp.route("/section/<int:section_id>/rename", methods=["POST"])
def section_rename(section_id):
    s = _own_section(section_id)
    title = request.form.get("title", "").strip()
    if 2 <= len(title) <= 120:
        execute("UPDATE sections SET title = ? WHERE id = ?", (title, section_id))
        flash("Раздел переименован.", "success")
    else:
        flash("Название раздела — от 2 до 120 символов.", "error")
    return redirect(url_for("teacher.course_manage", course_id=s["course_id"]))


@bp.route("/section/<int:section_id>/delete", methods=["POST"])
def section_delete(section_id):
    s = _own_section(section_id)
    execute("DELETE FROM sections WHERE id = ?", (section_id,))
    flash("Раздел удалён вместе с уроками и заданиями.", "info")
    return redirect(url_for("teacher.course_manage", course_id=s["course_id"]))


@bp.route("/<kind>/<int:item_id>/move", methods=["POST"])
def move(kind, item_id):
    direction = request.form.get("dir")
    if direction not in ("up", "down"):
        abort(400)
    if kind == "section":
        course_id = _own_section(item_id)["course_id"]
        _move("sections", item_id, direction)
    elif kind == "lesson":
        course_id = _own_lesson(item_id)["course_id"]
        _move("lessons", item_id, direction)
    elif kind == "assignment":
        course_id = _own_assignment(item_id)["course_id"]
        _move("assignments", item_id, direction)
    else:
        abort(404)
    return redirect(url_for("teacher.course_manage", course_id=course_id) + f"#{kind}-{item_id}")


# ====================== уроки ======================
def _lesson_form():
    title = request.form.get("title", "").strip()
    content = request.form.get("content_md", "")
    error = None
    if not (2 <= len(title) <= 160):
        error = "Название урока — от 2 до 160 символов."
    elif len(content) > 60000:
        error = "Текст урока слишком длинный (максимум 60 000 символов)."
    return title, content, error


@bp.route("/section/<int:section_id>/lesson/new", methods=["GET", "POST"])
def lesson_new(section_id):
    s = _own_section(section_id)
    form = {"title": "", "content_md": ""}
    if request.method == "POST":
        title, content, error = _lesson_form()
        form = {"title": title, "content_md": content}
        if error:
            flash(error, "error")
        else:
            lid = execute("INSERT INTO lessons (section_id, title, content_md, position) VALUES (?, ?, ?, ?)",
                          (section_id, title, content, _next_pos("lessons", "section_id", section_id)))
            flash("Урок создан. Теперь можно добавить примеры кода.", "success")
            return redirect(url_for("teacher.lesson_edit", lesson_id=lid))
    return render_template("teacher/lesson_form.html", lesson=None, section=s, form=form, examples=[],
                           course_id=s["course_id"])


@bp.route("/lesson/<int:lesson_id>/edit", methods=["GET", "POST"])
def lesson_edit(lesson_id):
    l = _own_lesson(lesson_id)
    form = {"title": l["title"], "content_md": l["content_md"]}
    if request.method == "POST":
        title, content, error = _lesson_form()
        form = {"title": title, "content_md": content}
        if error:
            flash(error, "error")
        else:
            execute("UPDATE lessons SET title = ?, content_md = ? WHERE id = ?", (title, content, lesson_id))
            flash("Урок сохранён.", "success")
            return redirect(url_for("teacher.lesson_edit", lesson_id=lesson_id))
    examples = query("SELECT * FROM code_examples WHERE lesson_id = ? ORDER BY position, id", (lesson_id,))
    return render_template("teacher/lesson_form.html", lesson=l, section={"title": l["section_title"]},
                           form=form, examples=examples, course_id=l["course_id"])


@bp.route("/lesson/<int:lesson_id>/delete", methods=["POST"])
def lesson_delete(lesson_id):
    l = _own_lesson(lesson_id)
    execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
    flash("Урок удалён.", "info")
    return redirect(url_for("teacher.course_manage", course_id=l["course_id"]))


# ---------- примеры кода ----------
def _example_form():
    title = request.form.get("title", "").strip()
    language = request.form.get("language", "python")
    code = request.form.get("code", "").rstrip()
    error = None
    if not (2 <= len(title) <= 120):
        error = "Название примера — от 2 до 120 символов."
    elif language not in services.LANGUAGES:
        error = "Выберите язык из списка."
    elif not code:
        error = "Код примера не может быть пустым."
    elif len(code) > 20000:
        error = "Код примера слишком длинный."
    return title, language, code, error


@bp.route("/lesson/<int:lesson_id>/example/add", methods=["POST"])
def example_add(lesson_id):
    _own_lesson(lesson_id)
    title, language, code, error = _example_form()
    if error:
        flash(error, "error")
    else:
        execute("INSERT INTO code_examples (lesson_id, title, language, code, position) VALUES (?, ?, ?, ?, ?)",
                (lesson_id, title, language, code, _next_pos("code_examples", "lesson_id", lesson_id)))
        flash("Пример кода добавлен.", "success")
    return redirect(url_for("teacher.lesson_edit", lesson_id=lesson_id) + "#examples")


def _own_example(example_id):
    e = query("""SELECT e.* FROM code_examples e JOIN lessons l ON l.id = e.lesson_id
                 JOIN sections s ON s.id = l.section_id JOIN courses c ON c.id = s.course_id
                 WHERE e.id = ? AND c.teacher_id = ?""", (example_id, g.user["id"]), one=True)
    if not e:
        abort(404)
    return e


@bp.route("/example/<int:example_id>/update", methods=["POST"])
def example_update(example_id):
    e = _own_example(example_id)
    title, language, code, error = _example_form()
    if error:
        flash(error, "error")
    else:
        execute("UPDATE code_examples SET title = ?, language = ?, code = ? WHERE id = ?",
                (title, language, code, example_id))
        flash("Пример кода обновлён.", "success")
    return redirect(url_for("teacher.lesson_edit", lesson_id=e["lesson_id"]) + "#examples")


@bp.route("/example/<int:example_id>/delete", methods=["POST"])
def example_delete(example_id):
    e = _own_example(example_id)
    execute("DELETE FROM code_examples WHERE id = ?", (example_id,))
    flash("Пример кода удалён.", "info")
    return redirect(url_for("teacher.lesson_edit", lesson_id=e["lesson_id"]) + "#examples")


# ====================== задания ======================
def _assignment_form(course_id):
    f = request.form
    data = {
        "title": f.get("title", "").strip(),
        "description_md": f.get("description_md", ""),
        "due_date": f.get("due_date", "").strip() or None,
        "kind": f.get("kind", "practice"),
        "section_id": f.get("section_id", type=int),
    }
    error = None
    if not (2 <= len(data["title"]) <= 160):
        error = "Название задания — от 2 до 160 символов."
    elif len(data["description_md"]) > 30000:
        error = "Описание задания слишком длинное."
    elif data["kind"] not in ("practice", "final"):
        error = "Некорректный тип задания."
    if not error and data["due_date"]:
        try:
            date.fromisoformat(data["due_date"])
        except ValueError:
            error = "Некорректная дата срока выполнения."
    if data["section_id"] is not None:
        ok = query("SELECT 1 FROM sections WHERE id = ? AND course_id = ?", (data["section_id"], course_id), one=True)
        if not ok:
            data["section_id"] = None
    if data["kind"] == "final":
        data["section_id"] = None  # итоговый проект живёт отдельно от разделов
    return data, error


@bp.route("/course/<int:course_id>/assignment/new", methods=["GET", "POST"])
def assignment_new(course_id):
    c = _own_course(course_id)
    sections, _ = services.course_tree(course_id)
    form = {"title": "", "description_md": "", "due_date": "", "kind": request.args.get("kind", "practice"),
            "section_id": request.args.get("section", type=int)}
    if request.method == "POST":
        data, error = _assignment_form(course_id)
        form = data
        if error:
            flash(error, "error")
        else:
            execute("""INSERT INTO assignments (course_id, section_id, title, description_md, due_date, kind, position)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (course_id, data["section_id"], data["title"], data["description_md"], data["due_date"],
                     data["kind"], _next_pos("assignments", "course_id", course_id)))
            flash("Задание добавлено.", "success")
            return redirect(url_for("teacher.course_manage", course_id=course_id))
    return render_template("teacher/assignment_form.html", course=c, sections=sections, form=form, assignment=None)


@bp.route("/assignment/<int:assignment_id>/edit", methods=["GET", "POST"])
def assignment_edit(assignment_id):
    a = _own_assignment(assignment_id)
    c = _own_course(a["course_id"])
    sections, _ = services.course_tree(a["course_id"])
    form = dict(a)
    if request.method == "POST":
        data, error = _assignment_form(a["course_id"])
        form = {**form, **data}
        if error:
            flash(error, "error")
        else:
            execute("""UPDATE assignments SET section_id = ?, title = ?, description_md = ?, due_date = ?, kind = ?
                       WHERE id = ?""",
                    (data["section_id"], data["title"], data["description_md"], data["due_date"], data["kind"],
                     assignment_id))
            flash("Задание сохранено.", "success")
            return redirect(url_for("teacher.course_manage", course_id=a["course_id"]))
    return render_template("teacher/assignment_form.html", course=c, sections=sections, form=form, assignment=a)


@bp.route("/assignment/<int:assignment_id>/delete", methods=["POST"])
def assignment_delete(assignment_id):
    a = _own_assignment(assignment_id)
    execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
    flash("Задание удалено вместе с отправленными работами.", "info")
    return redirect(url_for("teacher.course_manage", course_id=a["course_id"]))


# ====================== студенты и статистика ======================
@bp.route("/course/<int:course_id>/students")
def course_students(course_id):
    c = _own_course(course_id)
    return render_template("teacher/students.html", course=c, students=services.course_students(course_id))


@bp.route("/course/<int:course_id>/student/<int:student_id>")
def student_detail(course_id, student_id):
    c = _own_course(course_id)
    st = query("""SELECT u.*, e.enrolled_at FROM users u JOIN enrollments e ON e.student_id = u.id
                  WHERE u.id = ? AND e.course_id = ?""", (student_id, course_id), one=True)
    if not st:
        abort(404)
    progress = services.course_progress(student_id, course_id)
    subs = services.latest_submissions(student_id, course_id)
    sections, loose = services.course_tree(course_id)
    assignments = [a for s in sections for a in s["assignments"]] + loose
    done = services.completed_lesson_ids(student_id, course_id)
    history = services.grade_history(student_id, course_id)
    chart = line_chart([(services.parse_dt(h["reviewed_at"]).strftime("%d.%m"), h["score"]) for h in history])
    return render_template("teacher/student_detail.html", course=c, student=st, progress=progress, subs=subs,
                           assignments=assignments, sections=sections, done=done, history=history, chart=chart)


@bp.route("/course/<int:course_id>/stats")
def course_stats(course_id):
    c = _own_course(course_id)
    stats = services.course_stats(course_id)
    chart = bar_chart([str(i) for i in range(1, 11)], stats["distribution"])
    per_assignment = query(
        """SELECT a.id, a.title, a.kind,
                  COUNT(DISTINCT CASE WHEN s.status = 'checked' THEN s.student_id END) AS checked,
                  COUNT(DISTINCT CASE WHEN s.status = 'review' THEN s.student_id END) AS review,
                  COUNT(DISTINCT CASE WHEN s.status = 'revision' THEN s.student_id END) AS revision,
                  ROUND(AVG(CASE WHEN s.status = 'checked' THEN s.score END), 1) AS avg_score
           FROM assignments a LEFT JOIN submissions s ON s.assignment_id = a.id
           WHERE a.course_id = ? GROUP BY a.id ORDER BY a.position, a.id""", (course_id,))
    return render_template("teacher/stats.html", course=c, stats=stats, chart=chart, per_assignment=per_assignment)


# ====================== проверка работ ======================
@bp.route("/reviews")
def reviews():
    status = request.args.get("status", "review")
    course_id = request.args.get("course", type=int)
    sql = """SELECT s.*, a.title AS assignment_title, a.kind, c.id AS course_id, c.title AS course_title,
                    u.full_name AS student_name
             FROM submissions s JOIN assignments a ON a.id = s.assignment_id
             JOIN courses c ON c.id = a.course_id JOIN users u ON u.id = s.student_id
             WHERE c.teacher_id = ?"""
    params = [g.user["id"]]
    if status in ("review", "checked", "revision"):
        sql += " AND s.status = ?"
        params.append(status)
    else:
        status = "all"
    if course_id:
        sql += " AND c.id = ?"
        params.append(course_id)
    sql += " ORDER BY s.submitted_at " + ("ASC" if status == "review" else "DESC") + " LIMIT 200"
    rows = query(sql, params)
    my_courses = query("SELECT id, title FROM courses WHERE teacher_id = ? ORDER BY title", (g.user["id"],))
    counts = {r["status"]: r["c"] for r in query(
        """SELECT s.status, COUNT(*) c FROM submissions s JOIN assignments a ON a.id = s.assignment_id
           JOIN courses c ON c.id = a.course_id WHERE c.teacher_id = ? GROUP BY s.status""", (g.user["id"],))}
    return render_template("teacher/reviews.html", rows=rows, status=status, course_id=course_id,
                           my_courses=my_courses, counts=counts)


@bp.route("/submission/<int:submission_id>", methods=["GET", "POST"])
def review(submission_id):
    sub = query(
        """SELECT s.*, a.title AS assignment_title, a.description_md, a.due_date, a.course_id,
                  c.title AS course_title, u.full_name AS student_name, u.email AS student_email
           FROM submissions s JOIN assignments a ON a.id = s.assignment_id
           JOIN courses c ON c.id = a.course_id JOIN users u ON u.id = s.student_id
           WHERE s.id = ? AND c.teacher_id = ?""", (submission_id, g.user["id"]), one=True)
    if not sub:
        abort(404)
    editable = sub["status"] in ("review", "checked")
    latest_attempt = query("SELECT MAX(attempt) m FROM submissions WHERE assignment_id = ? AND student_id = ?",
                           (sub["assignment_id"], sub["student_id"]), one=True)["m"]
    if request.method == "POST":
        if not editable or sub["attempt"] != latest_attempt:
            flash("Эту работу уже нельзя оценить: студент ещё не отправил исправленную версию.", "error")
            return redirect(url_for("teacher.review", submission_id=submission_id))
        decision = request.form.get("decision")
        comment = request.form.get("comment", "").strip()
        score = request.form.get("score", type=int)
        error = None
        if len(comment) > 5000:
            error = "Комментарий слишком длинный (максимум 5000 символов)."
        elif decision == "accept":
            if score is None or not (1 <= score <= 10):
                error = "Выставите оценку от 1 до 10."
        elif decision == "revision":
            score = None
            if not comment:
                error = "Опишите, что нужно исправить — студент увидит ваш комментарий."
        else:
            error = "Выберите действие: принять работу или вернуть на доработку."
        if error:
            flash(error, "error")
        else:
            status = "checked" if decision == "accept" else "revision"
            execute("""UPDATE submissions SET status = ?, score = ?, teacher_comment = ?, reviewed_at = datetime('now')
                       WHERE id = ?""", (status, score, comment, submission_id))
            link = url_for("student.assignment", assignment_id=sub["assignment_id"])
            if status == "checked":
                services.notify(sub["student_id"],
                                f"Работа «{sub['assignment_title']}» проверена: оценка {score} из 10", link)
                flash(f"Оценка {score}/10 выставлена, студент получил уведомление.", "success")
            else:
                services.notify(sub["student_id"],
                                f"Работа «{sub['assignment_title']}» возвращена на доработку", link)
                flash("Работа возвращена на доработку, студент получил уведомление.", "success")
            return redirect(url_for("teacher.reviews"))
    attempts = query("SELECT * FROM submissions WHERE assignment_id = ? AND student_id = ? ORDER BY attempt",
                     (sub["assignment_id"], sub["student_id"]))
    return render_template("teacher/review.html", sub=sub, attempts=attempts, editable=editable,
                           is_latest=sub["attempt"] == latest_attempt)
