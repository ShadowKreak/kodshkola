"""Сквозные проверки платформы. Запуск: python tests/test_platform.py"""
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edu import create_app  # noqa: E402
from edu.db import get_db  # noqa: E402
from edu.security import reset_throttle  # noqa: E402

PW = "Demo12345"
FAILS = []


def check(name, cond, extra=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))
    if not cond:
        FAILS.append(name)


def make_app():
    tmp = tempfile.mkdtemp()
    app = create_app({"DATABASE": str(Path(tmp) / "t.db"), "UPLOAD_DIR": tmp, "TESTING": True,
                      "SECRET_KEY": "test", "ADMIN_INVITE_CODE": "invite-123"})
    return app


def token(client, path="/login"):
    html = client.get(path).get_data(as_text=True)
    m = re.search(r'name="_csrf" value="([^"]+)"', html) or re.search(r'name="csrf-token" content="([^"]+)"', html)
    return m.group(1)


def post(client, path, data=None, tok=None, **kw):
    data = dict(data or {})
    data["_csrf"] = tok or token(client, kw.pop("tok_page", "/login"))
    return client.post(path, data=data, **kw)


def login(app, email):
    c = app.test_client()
    r = post(c, "/login", {"email": email, "password": PW})
    assert r.status_code == 302, (email, r.status_code)
    return c


def main():
    app = make_app()
    import seed
    sys.argv = ["seed.py"]
    # засеваем во временную базу
    import edu
    orig = edu.create_app
    edu.create_app = lambda *a, **k: app
    seed.create_app = edu.create_app
    seed.main()
    edu.create_app = orig

    with app.app_context():
        ids = {r["email"].split("@")[0]: r["id"] for r in get_db().execute("SELECT id, email FROM users")}

    # ---------- публичные страницы и защита ----------
    print("Публичные страницы и доступ")
    c = app.test_client()
    check("лендинг открывается", c.get("/").status_code == 200)
    check("вход открывается", c.get("/login").status_code == 200)
    check("регистрация открывается", c.get("/register").status_code == 200)
    check("кабинет без входа -> редирект", c.get("/student/").status_code == 302)
    check("POST без CSRF отклонён", c.post("/login", data={"email": "a@b.c", "password": "x"}).status_code == 400)

    # ---------- регистрация ----------
    print("Регистрация")
    c = app.test_client()
    r = post(c, "/register", {"full_name": "Тест Студент", "email": "new@test.ru", "role": "student",
                              "password": "abc12345", "confirm": "abc12345"}, tok_page="/register")
    check("студент зарегистрирован и перенаправлен", r.status_code == 302 and "/student" in r.headers["Location"])
    c = app.test_client()
    r = post(c, "/register", {"full_name": "Хитрый", "email": "evil@test.ru", "role": "admin",
                              "password": "abc12345", "confirm": "abc12345", "admin_code": "wrong"}, tok_page="/register")
    check("админ без верного кода не создаётся", r.status_code == 200)
    r = post(c, "/register", {"full_name": "Админ Два", "email": "adm2@test.ru", "role": "admin",
                              "password": "abc12345", "confirm": "abc12345", "admin_code": "invite-123"}, tok_page="/register")
    check("админ с верным кодом создан", r.status_code == 302 and "/admin" in r.headers["Location"])
    c = app.test_client()
    r = post(c, "/register", {"full_name": "Слабый", "email": "weak@test.ru", "role": "student",
                              "password": "12345678", "confirm": "12345678"}, tok_page="/register")
    check("слабый пароль отклонён", r.status_code == 200)
    r = post(c, "/register", {"full_name": "Дубль", "email": "ANNA@kodshkola.local", "role": "student",
                              "password": "abc12345", "confirm": "abc12345"}, tok_page="/register")
    check("дубликат e-mail отклонён", r.status_code == 200)

    # ---------- вход ----------
    print("Вход")
    c = app.test_client()
    r = post(c, "/login", {"email": "anna@kodshkola.local", "password": "bad"})
    check("неверный пароль отклонён", r.status_code == 200 and "Неверный" in r.get_data(as_text=True))
    r = post(c, "/login?next=//evil.com", {"email": "anna@kodshkola.local", "password": PW})
    check("open redirect заблокирован", r.status_code == 302 and "evil.com" not in r.headers["Location"])
    reset_throttle()
    c = app.test_client()
    for _ in range(5):
        post(c, "/login", {"email": "maria@kodshkola.local", "password": "bad"})
    r = post(c, "/login", {"email": "maria@kodshkola.local", "password": PW})
    check("блокировка после 5 неудачных попыток", r.status_code == 200 and "Слишком много" in r.get_data(as_text=True))
    reset_throttle()

    # ---------- студент ----------
    print("Кабинет студента")
    s = login(app, "anna@kodshkola.local")
    for path in ["/student/", "/student/catalog", "/student/catalog?q=Python", "/student/catalog?q=%25&category=1",
                 "/student/my-courses", "/student/grades", "/student/course/1", "/student/course/2",
                 "/student/lesson/1", "/student/lesson/3", "/student/assignment/1", "/student/assignment/3",
                 "/notifications", "/profile"]:
        r = s.get(path)
        check(f"GET {path}", r.status_code == 200, r.status_code)
    html = s.get("/student/catalog?q=Python").get_data(as_text=True)
    check("поиск находит курс Python", "Python для начинающих" in html and "SQL и реляционные" not in html)
    html = s.get("/student/catalog").get_data(as_text=True)
    check("черновик не виден в каталоге", "JavaScript: интерактивные" not in html)
    check("в каталоге нет видео", "<video" not in html.lower() and "iframe" not in html.lower())
    check("студент не заходит в кабинет преподавателя", s.get("/teacher/").status_code == 403)
    check("студент не заходит в админку", s.get("/admin/").status_code == 403)
    check("студент не открывает чужой черновик", s.get("/student/course/3").status_code == 404)
    check("нет доступа к уроку без записи", login(app, "pavel@kodshkola.local").get("/student/lesson/4").status_code == 403)

    html = s.get("/student/lesson/1").get_data(as_text=True)
    check("урок содержит текст и пример кода", "Что такое программа" in html and "Приветствие с именем" in html)
    r = post(s, "/student/lesson/3/complete", tok_page="/student/")
    check("урок отмечается изученным", r.status_code == 302)

    # сдача: новое задание (a13 уже на проверке у Анны — повторно нельзя)
    r = post(s, "/student/assignment/3/submit", {"code": "print(1)"}, tok_page="/student/", follow_redirects=True)
    check("повторная отправка при статусе «на проверке» запрещена", "уже отправлена" in r.get_data(as_text=True))
    r = post(s, "/student/assignment/4/submit", {"code": ""}, tok_page="/student/", follow_redirects=True)
    check("пустое решение отклонено", "Добавьте" in r.get_data(as_text=True))
    r = post(login(app, "pavel@kodshkola.local"), "/student/assignment/7/submit", {"code": "SELECT 1"}, tok_page="/student/")
    check("отправка задания без записи на курс запрещена", r.status_code == 403)
    r = post(s, "/student/assignment/4/submit", {"code": "print('final')", "answer_text": "готово"}, tok_page="/student/")
    check("отправка итогового проекта", r.status_code == 302)

    # запись на курс
    p = login(app, "pavel@kodshkola.local")
    r = post(p, "/student/course/2/enroll", tok_page="/student/", follow_redirects=True)
    check("запись на курс", "записались" in r.get_data(as_text=True))
    r = post(p, "/student/course/3/enroll", tok_page="/student/")
    check("нельзя записаться на черновик", r.status_code == 404)

    # ---------- преподаватель ----------
    print("Кабинет преподавателя")
    t = login(app, "ivanova@kodshkola.local")
    for path in ["/teacher/", "/teacher/courses", "/teacher/course/new", "/teacher/course/1", "/teacher/course/1/edit",
                 "/teacher/course/1/students", "/teacher/course/1/student/" + str(ids["anna"]), "/teacher/course/1/stats",
                 "/teacher/reviews", "/teacher/reviews?status=checked", "/teacher/reviews?status=all&course=1",
                 "/teacher/section/1/lesson/new", "/teacher/lesson/1/edit", "/teacher/course/1/assignment/new",
                 "/teacher/assignment/1/edit", "/teacher/submission/1"]:
        r = t.get(path)
        check(f"GET {path}", r.status_code == 200, r.status_code)
    check("преподаватель не видит чужой курс", t.get("/teacher/course/2").status_code == 404)
    check("преподаватель не открывает чужую работу", t.get("/teacher/submission/4").status_code == 404)
    check("преподаватель не заходит в кабинет студента", t.get("/student/").status_code == 403)

    # создание курса
    r = post(t, "/teacher/course/new", {"title": "Тестовый курс", "description": "Описание", "level": "advanced",
                                         "new_category": "Тесты"}, tok_page="/teacher/")
    check("курс создан", r.status_code == 302)
    with app.app_context():
        cid = get_db().execute("SELECT id FROM courses WHERE title = 'Тестовый курс'").fetchone()["id"]
    r = post(t, f"/teacher/course/{cid}/publish", tok_page="/teacher/", follow_redirects=True)
    check("публикация пустого курса запрещена", "хотя бы один урок" in r.get_data(as_text=True))
    post(t, f"/teacher/course/{cid}/section/add", {"title": "Раздел 1"}, tok_page="/teacher/")
    with app.app_context():
        sid = get_db().execute("SELECT id FROM sections WHERE course_id = ?", (cid,)).fetchone()["id"]
    xss = "## Заголовок\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[клик](javascript:alert(1))\n\n```python\nprint('ok')\n```"
    r = post(t, f"/teacher/section/{sid}/lesson/new", {"title": "Урок XSS", "content_md": xss}, tok_page="/teacher/")
    check("урок создан", r.status_code == 302)
    with app.app_context():
        lid = get_db().execute("SELECT id FROM lessons WHERE section_id = ?", (sid,)).fetchone()["id"]
    post(t, f"/teacher/lesson/{lid}/example/add", {"title": "Пример", "language": "python", "code": "print(1)"}, tok_page="/teacher/")
    post(t, f"/teacher/course/{cid}/publish", tok_page="/teacher/")
    st = login(app, "dmitry@kodshkola.local")
    post(st, f"/student/course/{cid}/enroll", tok_page="/student/")
    html = st.get_data if False else st.get(f"/student/lesson/{lid}").get_data(as_text=True)
    check("XSS: <script> вырезан", "<script>alert" not in html)
    check("XSS: onerror вырезан", "onerror" not in html)
    check("XSS: javascript: ссылка вырезана", "javascript:alert" not in html)
    check("блок кода сохранён", "language-python" in html)

    # проверка работы: оценка вне диапазона, без комментария, корректная
    with app.app_context():
        sub = get_db().execute("SELECT id FROM submissions WHERE assignment_id = 3 AND student_id = ?", (ids["anna"],)).fetchone()["id"]
    r = post(t, f"/teacher/submission/{sub}", {"decision": "accept", "score": "11", "comment": ""}, tok_page="/teacher/", follow_redirects=True)
    check("оценка 11 отклонена", "от 1 до 10" in r.get_data(as_text=True))
    r = post(t, f"/teacher/submission/{sub}", {"decision": "accept", "score": "0"}, tok_page="/teacher/", follow_redirects=True)
    check("оценка 0 отклонена", "от 1 до 10" in r.get_data(as_text=True))
    r = post(t, f"/teacher/submission/{sub}", {"decision": "revision", "comment": ""}, tok_page="/teacher/", follow_redirects=True)
    check("возврат без комментария отклонён", "Опишите" in r.get_data(as_text=True))
    r = post(t, f"/teacher/submission/{sub}", {"decision": "revision", "comment": "Добавьте обработку пустого списка."}, tok_page="/teacher/")
    check("возврат на доработку", r.status_code == 302)
    a_html = s.get("/student/assignment/3").get_data(as_text=True)
    check("студент видит «Требуются исправления» и комментарий", "Требуются исправления" in a_html and "обработку пустого списка" in a_html)
    r = post(s, "/student/assignment/3/submit", {"code": "print(len([]))", "answer_text": "исправил"}, tok_page="/student/")
    check("студент отправляет исправление", r.status_code == 302)
    with app.app_context():
        sub2 = get_db().execute("SELECT id, attempt FROM submissions WHERE assignment_id = 3 AND student_id = ? ORDER BY attempt DESC", (ids["anna"],)).fetchone()
    check("создана попытка №2", sub2["attempt"] == 2)
    r = post(t, f"/teacher/submission/{sub2['id']}", {"decision": "accept", "score": "9", "comment": "Хорошо!"}, tok_page="/teacher/")
    check("оценка 9 выставлена", r.status_code == 302)
    a_html = s.get("/student/assignment/3").get_data(as_text=True)
    check("студент видит оценку 9 и комментарий", ">9<" in a_html and "Хорошо!" in a_html)
    n_html = s.get("/notifications").get_data(as_text=True)
    check("студент получил уведомление об оценке", "оценка 9 из 10" in n_html)
    r = post(t, f"/teacher/submission/{sub}", {"decision": "accept", "score": "5"}, tok_page="/teacher/", follow_redirects=True)
    check("старую попытку оценить нельзя", "нельзя оценить" in r.get_data(as_text=True))

    # чужие данные
    t2 = login(app, "petrov@kodshkola.local")
    check("чужой преподаватель не видит работу", t2.get(f"/teacher/submission/{sub2['id']}").status_code == 404)
    r = post(t2, f"/teacher/submission/{sub2['id']}", {"decision": "accept", "score": "1"}, tok_page="/teacher/")
    check("чужой преподаватель не может оценить", r.status_code == 404)
    check("чужой преподаватель не редактирует курс", post(t2, "/teacher/course/1/section/add", {"title": "x"}, tok_page="/teacher/").status_code == 404)

    # прогресс
    with app.app_context():
        from edu import services
        p = services.course_progress(ids["anna"], 1)
    check("прогресс Анны: уроки 3/3", p["lessons_done"] == 3, p)
    check("прогресс Анны: средняя оценка", p["avg_score"] is not None and 1 <= p["avg_score"] <= 10, p)
    check("процент в диапазоне 0..100", 0 <= p["percent"] <= 100, p)

    # перемещение и удаление
    r = post(t, "/teacher/section/1/move", {"dir": "down"}, tok_page="/teacher/")
    check("перемещение раздела", r.status_code == 302)
    r = post(t, f"/teacher/course/{cid}/delete", tok_page="/teacher/")
    check("курс удалён", r.status_code == 302)

    # ---------- администратор ----------
    print("Кабинет администратора")
    a = login(app, "admin@kodshkola.local")
    for path in ["/admin/", "/admin/users", "/admin/users?q=anna&role=student", "/admin/courses", "/admin/categories"]:
        check(f"GET {path}", a.get(path).status_code == 200)
    check("админ не заходит в кабинет преподавателя", a.get("/teacher/").status_code == 403)
    r = post(a, f"/admin/users/{ids['admin']}/block", tok_page="/admin/", follow_redirects=True)
    check("нельзя заблокировать себя", "самого себя" in r.get_data(as_text=True))
    r = post(a, f"/admin/users/{ids['pavel']}/block", tok_page="/admin/")
    check("блокировка пользователя", r.status_code == 302)
    r = post(app.test_client(), "/login", {"email": "pavel@kodshkola.local", "password": PW})
    check("заблокированный не входит", r.status_code == 200)
    post(a, f"/admin/users/{ids['pavel']}/block", tok_page="/admin/")
    r = post(a, f"/admin/users/{ids['maria']}/role", {"role": "teacher"}, tok_page="/admin/")
    check("смена роли", r.status_code == 302)
    r = post(a, "/admin/categories", {"name": "Новая категория"}, tok_page="/admin/")
    check("категория добавлена", r.status_code == 302)
    r = post(a, f"/admin/courses/1/toggle", tok_page="/admin/")
    check("курс скрыт админом", r.status_code == 302)
    post(a, f"/admin/courses/1/toggle", tok_page="/admin/")

    # ---------- продолжение обучения ----------
    print("Продолжение обучения")
    from edu import services
    with app.app_context():
        for sid_name in ("anna", "dmitry", "maria"):
            for e in get_db().execute("SELECT course_id FROM enrollments WHERE student_id=?", (ids[sid_name],)).fetchall():
                step = services.course_next_step(ids[sid_name], e["course_id"])
                check(f"next_step {sid_name}/курс {e['course_id']} корректен",
                      step is None or (step["kind"] in ("lesson", "assignment") and step["id"] and step["label"]))
        check("метки статусов на русском", services.STATUS_LABELS["revision"] == "Требуются исправления"
              and services.STATUS_LABELS["not_started"] == "Не отправлено")
    check("лендинг показывает реальные курсы", "Python для начинающих" in app.test_client().get("/").get_data(as_text=True))

    # ---------- хранение паролей ----------
    print("Безопасность данных")
    with app.app_context():
        h = get_db().execute("SELECT password_hash FROM users WHERE email='anna@kodshkola.local'").fetchone()[0]
    check("пароль хранится в виде хеша", h.startswith(("scrypt:", "pbkdf2:")) and PW not in h)
    r = s.get("/student/")
    check("заголовки безопасности", r.headers.get("X-Frame-Options") == "DENY" and "Content-Security-Policy" in r.headers)
    check("страница 404 на русском", "не найдена" in app.test_client().get("/nope").get_data(as_text=True))
    check("path traversal в обложках закрыт", app.test_client().get("/uploads/covers/..%2f..%2fedu.db").status_code == 404)

    print()
    if FAILS:
        print(f"ПРОВАЛЕНО: {len(FAILS)}")
        for f in FAILS:
            print("  -", f)
        sys.exit(1)
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")


if __name__ == "__main__":
    main()
