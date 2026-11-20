"""Бизнес-логика: прогресс, статусы заданий, статистика, уведомления."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .db import execute, query

TZ = ZoneInfo("Europe/Moscow")

STATUS_LABELS = {
    "not_started": "Не отправлено",
    "review": "На проверке",
    "checked": "Проверено",
    "revision": "Требуются исправления",
}
LEVEL_LABELS = {"beginner": "Начальный", "intermediate": "Средний", "advanced": "Продвинутый"}
LANGUAGES = {
    "python": "Python", "javascript": "JavaScript", "csharp": "C#", "java": "Java",
    "cpp": "C++", "sql": "SQL", "html": "HTML", "css": "CSS", "bash": "Bash", "text": "Текст",
}


# ---------- уведомления ----------
def notify(user_id: int, text: str, link: str | None = None):
    execute("INSERT INTO notifications (user_id, text, link) VALUES (?, ?, ?)", (user_id, text, link))


def unread_count(user_id: int) -> int:
    row = query("SELECT COUNT(*) c FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,), one=True)
    return row["c"]


def pending_reviews(teacher_id: int) -> int:
    return query(
        """SELECT COUNT(*) c FROM submissions s JOIN assignments a ON a.id = s.assignment_id
           JOIN courses c ON c.id = a.course_id
           WHERE c.teacher_id = ? AND s.status = 'review'""", (teacher_id,), one=True)["c"]


# ---------- время ----------
def today_local() -> date:
    return datetime.now(TZ).date()


def parse_dt(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
    except ValueError:
        return None


def is_overdue(due: str | None) -> bool:
    if not due:
        return False
    try:
        return today_local() > date.fromisoformat(due)
    except ValueError:
        return False


# ---------- структура курса ----------
def course_tree(course_id: int):
    """Разделы с уроками и заданиями + задания вне разделов."""
    sections = [dict(s) for s in query(
        "SELECT * FROM sections WHERE course_id = ? ORDER BY position, id", (course_id,))]
    lessons = query(
        """SELECT l.* FROM lessons l JOIN sections s ON s.id = l.section_id
           WHERE s.course_id = ? ORDER BY l.position, l.id""", (course_id,))
    assignments = query(
        "SELECT * FROM assignments WHERE course_id = ? ORDER BY position, id", (course_id,))
    by_id = {s["id"]: s for s in sections}
    for s in sections:
        s["lessons"], s["assignments"] = [], []
    for l in lessons:
        by_id[l["section_id"]]["lessons"].append(dict(l))
    loose = []
    for a in assignments:
        if a["section_id"] in by_id:
            by_id[a["section_id"]]["assignments"].append(dict(a))
        else:
            loose.append(dict(a))
    return sections, loose


def latest_submissions(student_id: int, course_id: int) -> dict[int, dict]:
    rows = query(
        """SELECT s.* FROM submissions s
           JOIN (SELECT assignment_id, MAX(attempt) m FROM submissions
                 WHERE student_id = ? GROUP BY assignment_id) l
             ON l.assignment_id = s.assignment_id AND l.m = s.attempt
           WHERE s.student_id = ?
             AND s.assignment_id IN (SELECT id FROM assignments WHERE course_id = ?)""",
        (student_id, student_id, course_id))
    return {r["assignment_id"]: dict(r) for r in rows}


def course_next_lesson(student_id: int, course_id: int):
    """Последний открытый незавершённый урок или первый незавершённый урок курса."""
    visited = query(
        """SELECT l.id, l.title, s.title AS section_title
           FROM lesson_visits v
           JOIN lessons l ON l.id = v.lesson_id
           JOIN sections s ON s.id = l.section_id
           LEFT JOIN lesson_progress lp ON lp.student_id = v.student_id AND lp.lesson_id = l.id
           WHERE v.student_id = ? AND v.course_id = ? AND lp.lesson_id IS NULL""",
        (student_id, course_id), one=True)
    if visited:
        return visited
    return query(
        """SELECT l.id, l.title, s.title AS section_title
           FROM lessons l JOIN sections s ON s.id = l.section_id
           LEFT JOIN lesson_progress lp ON lp.student_id = ? AND lp.lesson_id = l.id
           WHERE s.course_id = ? AND lp.lesson_id IS NULL
           ORDER BY s.position, s.id, l.position, l.id LIMIT 1""",
        (student_id, course_id), one=True)


def course_next_step(student_id: int, course_id: int):
    """Куда вести кнопку «Продолжить»: урок, затем невыполненное задание, иначе None (курс пройден)."""
    lesson = course_next_lesson(student_id, course_id)
    if lesson:
        return {"kind": "lesson", "id": lesson["id"], "title": lesson["title"], "label": "Продолжить обучение"}
    subs = latest_submissions(student_id, course_id)
    rows = query(
        """SELECT a.id, a.title FROM assignments a LEFT JOIN sections s ON s.id = a.section_id
           WHERE a.course_id = ?
           ORDER BY (a.section_id IS NULL), s.position, a.position, a.id""", (course_id,))
    for a in rows:
        sub = subs.get(a["id"])
        if sub is None:
            return {"kind": "assignment", "id": a["id"], "title": a["title"], "label": "Выполнить задание"}
        if sub["status"] == "revision":
            return {"kind": "assignment", "id": a["id"], "title": a["title"], "label": "Исправить работу"}
    return None


def completed_lesson_ids(student_id: int, course_id: int) -> set[int]:
    rows = query(
        """SELECT lp.lesson_id FROM lesson_progress lp
           JOIN lessons l ON l.id = lp.lesson_id
           JOIN sections s ON s.id = l.section_id
           WHERE lp.student_id = ? AND s.course_id = ?""", (student_id, course_id))
    return {r["lesson_id"] for r in rows}


# ---------- прогресс ----------
def course_progress(student_id: int, course_id: int) -> dict:
    lessons_total = query(
        """SELECT COUNT(*) c FROM lessons l JOIN sections s ON s.id = l.section_id
           WHERE s.course_id = ?""", (course_id,), one=True)["c"]
    assignments_total = query(
        "SELECT COUNT(*) c FROM assignments WHERE course_id = ?", (course_id,), one=True)["c"]
    lessons_done = len(completed_lesson_ids(student_id, course_id))
    subs = latest_submissions(student_id, course_id).values()
    checked = [s for s in subs if s["status"] == "checked"]
    on_review = sum(1 for s in subs if s["status"] == "review")
    revision = sum(1 for s in subs if s["status"] == "revision")
    scores = [s["score"] for s in checked if s["score"] is not None]
    total = lessons_total + assignments_total
    done = lessons_done + len(checked)
    return {
        "lessons_total": lessons_total,
        "lessons_done": lessons_done,
        "assignments_total": assignments_total,
        "assignments_done": len(checked),
        "on_review": on_review,
        "revision": revision,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "percent": round(done / total * 100) if total else 0,
    }


def grade_history(student_id: int, course_id: int | None = None):
    sql = """SELECT s.*, a.title AS assignment_title, a.course_id, c.title AS course_title
             FROM submissions s
             JOIN assignments a ON a.id = s.assignment_id
             JOIN courses c ON c.id = a.course_id
             WHERE s.student_id = ? AND s.status = 'checked'"""
    params = [student_id]
    if course_id:
        sql += " AND a.course_id = ?"
        params.append(course_id)
    sql += " ORDER BY s.reviewed_at, s.id"
    return query(sql, params)


def student_overview(student_id: int) -> dict:
    """Сводка студента по всем его курсам."""
    courses = query(
        """SELECT c.*, u.full_name AS teacher_name, cat.name AS category_name, e.enrolled_at
           FROM enrollments e JOIN courses c ON c.id = e.course_id
           JOIN users u ON u.id = c.teacher_id
           LEFT JOIN categories cat ON cat.id = c.category_id
           WHERE e.student_id = ? ORDER BY e.enrolled_at DESC""", (student_id,))
    items, totals = [], {"lessons": 0, "assignments": 0, "review": 0, "revision": 0}
    for c in courses:
        p = course_progress(student_id, c["id"])
        next_lesson = course_next_lesson(student_id, c["id"])
        items.append({"course": c, "progress": p, "next_lesson": next_lesson,
                      "next_step": course_next_step(student_id, c["id"])})
        totals["lessons"] += p["lessons_done"]
        totals["assignments"] += p["assignments_done"]
        totals["review"] += p["on_review"]
        totals["revision"] += p["revision"]
    history = grade_history(student_id)
    scores = [h["score"] for h in history]
    totals["avg"] = round(sum(scores) / len(scores), 1) if scores else None
    return {"items": items, "totals": totals, "history": history}


# ---------- статистика курса для преподавателя ----------
def course_students(course_id: int):
    rows = query(
        """SELECT u.id, u.full_name, u.email, e.enrolled_at FROM enrollments e
           JOIN users u ON u.id = e.student_id WHERE e.course_id = ?
           ORDER BY u.full_name""", (course_id,))
    return [{"user": r, "progress": course_progress(r["id"], course_id)} for r in rows]


def course_stats(course_id: int) -> dict:
    students = course_students(course_id)
    n = len(students)
    avg_percent = round(sum(s["progress"]["percent"] for s in students) / n) if n else 0
    scores = [r["score"] for r in query(
        """SELECT s.score FROM submissions s JOIN assignments a ON a.id = s.assignment_id
           WHERE a.course_id = ? AND s.status = 'checked' AND s.score IS NOT NULL""", (course_id,))]
    dist = [0] * 10
    for sc in scores:
        dist[sc - 1] += 1
    pending = query(
        """SELECT COUNT(*) c FROM submissions s JOIN assignments a ON a.id = s.assignment_id
           WHERE a.course_id = ? AND s.status = 'review'""", (course_id,), one=True)["c"]
    return {
        "students": students,
        "count": n,
        "avg_percent": avg_percent,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "graded": len(scores),
        "pending": pending,
        "distribution": dist,
    }
