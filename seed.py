"""Наполнение базы демонстрационными данными.

Запуск:  python seed.py          — только если база пуста
         python seed.py --reset  — удалить все данные и создать заново
"""
import sys
from datetime import date, datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

from edu import create_app
from edu.db import get_db

DEMO_PASSWORD = "Demo12345"


def ts(days_ago: float = 0, hours_ago: float = 0) -> str:
    t = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    return t.strftime("%Y-%m-%d %H:%M:%S")


def due(days_from_now: int) -> str:
    return (date.today() + timedelta(days=days_from_now)).isoformat()


PY_INTRO = """## Что такое программа

Программа — это набор инструкций, которые компьютер выполняет по порядку. Python читает код **сверху вниз**, строка за строкой.

> Начните с малого: запускайте код после каждого изменения и смотрите на результат.

### Первая программа

Функция `print()` выводит значение на экран:

```python
print("Привет, мир!")
```

### Что важно запомнить

- Строки пишутся в кавычках: `"текст"`.
- Каждая инструкция обычно занимает отдельную строку.
- Комментарий начинается с символа `#` и не выполняется.
"""

PY_VARS = """## Переменные

Переменная — это имя, под которым хранится значение. Присваивание выполняется знаком `=`.

```python
name = "Анна"
age = 19
height = 1.68
is_student = True
```

### Основные типы данных

| Тип | Пример | Описание |
|-----|--------|----------|
| `int` | `42` | целое число |
| `float` | `3.14` | число с точкой |
| `str` | `"текст"` | строка |
| `bool` | `True` | логическое значение |

Тип значения можно узнать функцией `type()`.
"""

PY_LOOPS = """## Условия и циклы

Условие `if` выбирает, какой код выполнить. Цикл `for` повторяет действие для каждого элемента.

```python
for n in range(1, 6):
    if n % 2 == 0:
        print(n, "чётное")
    else:
        print(n, "нечётное")
```

Отступ в 4 пробела показывает, какой код входит в условие или цикл. Это **обязательное** правило Python.
"""

SQL_SELECT = """## Запрос SELECT

Оператор `SELECT` выбирает данные из таблицы. Условие фильтрации задаётся в `WHERE`, сортировка — в `ORDER BY`.

```sql
SELECT name, price
FROM products
WHERE price < 1000
ORDER BY price DESC;
```

Ключевые слова принято писать заглавными буквами, чтобы запрос читался легче.
"""

SQL_JOIN = """## Объединение таблиц

`JOIN` связывает строки двух таблиц по общему полю — как правило, по внешнему ключу.

```sql
SELECT o.id, c.name
FROM orders o
JOIN customers c ON c.id = o.customer_id;
```

Если нужны строки без пары, используйте `LEFT JOIN`.
"""

JS_DOM = """## Работа со страницей

JavaScript умеет находить элементы страницы и менять их. Для поиска служит `document.querySelector`.

```javascript
const button = document.querySelector("#save");
button.addEventListener("click", () => {
  console.log("Нажали на кнопку");
});
```

Обработчик события — функция, которая вызывается, когда пользователь совершает действие.
"""

JS_FUNC = """## Функции

Функция — именованный блок кода, который можно вызвать много раз.

```javascript
function square(x) {
  return x * x;
}
console.log(square(5)); // 25
```

Стрелочная запись короче: `const square = x => x * x;`.
"""


def main():
    reset = "--reset" in sys.argv
    app = create_app()
    with app.app_context():
        db = get_db()
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] and not reset:
            print("База уже содержит данные. Для пересоздания: python seed.py --reset")
            return
        if reset:
            for t in ("notifications", "submissions", "lesson_progress", "enrollments", "code_examples",
                      "assignments", "lessons", "sections", "courses", "categories", "users"):
                db.execute(f"DELETE FROM {t}")
            db.execute("DELETE FROM sqlite_sequence")
            db.commit()

        pw = generate_password_hash(DEMO_PASSWORD)

        def user(email, name, role):
            return db.execute("INSERT INTO users (email, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                              (email, name, pw, role)).lastrowid

        admin = user("admin@kodshkola.local", "Администратор Системы", "admin")
        t1 = user("ivanova@kodshkola.local", "Елена Иванова", "teacher")
        t2 = user("petrov@kodshkola.local", "Сергей Петров", "teacher")
        students = [
            user("anna@kodshkola.local", "Анна Смирнова", "student"),
            user("dmitry@kodshkola.local", "Дмитрий Кузнецов", "student"),
            user("maria@kodshkola.local", "Мария Орлова", "student"),
            user("pavel@kodshkola.local", "Павел Лебедев", "student"),
        ]

        cats = {}
        for name in ("Python", "Базы данных", "Веб-разработка", "Алгоритмы"):
            cats[name] = db.execute("INSERT INTO categories (name) VALUES (?)", (name,)).lastrowid

        def course(title, desc, cat, level, teacher, published=1):
            return db.execute(
                "INSERT INTO courses (title, description, category_id, level, teacher_id, is_published) VALUES (?, ?, ?, ?, ?, ?)",
                (title, desc, cats[cat], level, teacher, published)).lastrowid

        def section(cid, title, pos):
            return db.execute("INSERT INTO sections (course_id, title, position) VALUES (?, ?, ?)", (cid, title, pos)).lastrowid

        def lesson(sid, title, md, pos):
            return db.execute("INSERT INTO lessons (section_id, title, content_md, position) VALUES (?, ?, ?, ?)",
                              (sid, title, md, pos)).lastrowid

        def example(lid, title, lang, code, pos=1):
            db.execute("INSERT INTO code_examples (lesson_id, title, language, code, position) VALUES (?, ?, ?, ?, ?)",
                       (lid, title, lang, code, pos))

        def assignment(cid, sid, title, md, due_in, kind, pos):
            return db.execute(
                "INSERT INTO assignments (course_id, section_id, title, description_md, due_date, kind, position) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (cid, sid, title, md, due(due_in) if due_in is not None else None, kind, pos)).lastrowid

        # ---------- Курс 1: Python ----------
        c1 = course("Python для начинающих",
                    "Первый шаг в программировании: переменные, условия, циклы и функции. К концу курса вы напишете собственную консольную программу.",
                    "Python", "beginner", t1)
        s11 = section(c1, "Основы языка", 1)
        s12 = section(c1, "Управляющие конструкции", 2)
        l11 = lesson(s11, "Введение: первая программа", PY_INTRO, 1)
        l12 = lesson(s11, "Переменные и типы данных", PY_VARS, 2)
        l13 = lesson(s12, "Условия и циклы", PY_LOOPS, 1)
        example(l11, "Приветствие с именем", "python", 'name = input("Как вас зовут? ")\nprint(f"Привет, {name}!")')
        example(l12, "Работа с типами", "python", 'age = 19\nprice = 99.5\nprint(type(age), type(price))\nprint(age + price)')
        example(l13, "Сумма чисел от 1 до 10", "python", "total = 0\nfor i in range(1, 11):\n    total += i\nprint(total)  # 55")
        a11 = assignment(c1, s11, "Калькулятор возраста",
                         "Напишите программу, которая спрашивает год рождения и выводит, сколько лет человеку.\n\n**Требования:**\n\n- используйте `input()` и `int()`;\n- результат выводите через `print()`.", -6, "practice", 1)
        a12 = assignment(c1, s12, "Таблица умножения",
                         "Выведите таблицу умножения на число, введённое пользователем, от 1 до 10.", 3, "practice", 2)
        a13 = assignment(c1, s12, "Чётные и нечётные",
                         "Для списка чисел посчитайте количество чётных и нечётных.", 9, "practice", 3)
        a1f = assignment(c1, None, "Итоговый проект: консольная игра «Угадай число»",
                         "Создайте игру: компьютер загадывает число от 1 до 100, игрок угадывает. Подсказывайте «больше» или «меньше» и считайте попытки.", 21, "final", 4)

        # ---------- Курс 2: SQL ----------
        c2 = course("SQL и реляционные базы данных",
                    "Проектирование таблиц, выборка и объединение данных. Практика на реальных учебных схемах.",
                    "Базы данных", "intermediate", t2)
        s21 = section(c2, "Выборка данных", 1)
        l21 = lesson(s21, "Запрос SELECT", SQL_SELECT, 1)
        l22 = lesson(s21, "Объединение таблиц JOIN", SQL_JOIN, 2)
        example(l21, "Дорогие товары", "sql", "SELECT name, price\nFROM products\nWHERE price > 5000;")
        example(l22, "Заказы с именами клиентов", "sql", "SELECT o.id, c.name, o.total\nFROM orders o\nJOIN customers c ON c.id = o.customer_id;")
        a21 = assignment(c2, s21, "Фильтрация товаров", "Напишите запрос, который выбирает товары дешевле 1000 рублей и сортирует их по названию.", -2, "practice", 1)
        a22 = assignment(c2, s21, "Заказы клиентов", "Выведите все заказы вместе с именами клиентов, используя `JOIN`.", 6, "practice", 2)
        a2f = assignment(c2, None, "Итоговый проект: схема интернет-магазина", "Спроектируйте таблицы и напишите 5 запросов к ним.", 25, "final", 3)

        # ---------- Курс 3: JavaScript (черновик) ----------
        c3 = course("JavaScript: интерактивные страницы",
                    "Функции, события и работа с DOM. Курс в разработке.", "Веб-разработка", "beginner", t1, published=0)
        s31 = section(c3, "Основы JavaScript", 1)
        l31 = lesson(s31, "Функции", JS_FUNC, 1)
        lesson(s31, "Работа со страницей (DOM)", JS_DOM, 2)
        example(l31, "Функция-квадрат", "javascript", "const square = x => x * x;\nconsole.log(square(7)); // 49")

        # ---------- Записи, прогресс, работы ----------
        anna, dmitry, maria, pavel = students
        for sid, cid in [(anna, c1), (anna, c2), (dmitry, c1), (maria, c1), (maria, c2), (pavel, c1)]:
            db.execute("INSERT INTO enrollments (student_id, course_id, enrolled_at) VALUES (?, ?, ?)", (sid, cid, ts(14)))

        def done(sid, lessons):
            for l in lessons:
                db.execute("INSERT OR IGNORE INTO lesson_progress (student_id, lesson_id, completed_at) VALUES (?, ?, ?)", (sid, l, ts(10)))

        done(anna, [l11, l12, l13, l21, l22])
        done(dmitry, [l11, l12])
        done(maria, [l11, l21])
        done(pavel, [l11])

        def sub(aid, sid, attempt, text, code, status, score=None, comment="", sub_days=8, rev_days=None):
            reviewed = ts(rev_days) if rev_days is not None else None
            return db.execute(
                """INSERT INTO submissions (assignment_id, student_id, attempt, answer_text, code, status, score,
                   teacher_comment, submitted_at, reviewed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (aid, sid, attempt, text, code, status, score, comment, ts(sub_days), reviewed)).lastrowid

        age_code = 'year = int(input("Год рождения: "))\nprint("Вам", 2026 - year, "лет")'
        # Анна — сильная студентка
        sub(a11, anna, 1, "Использовала int() для преобразования.", age_code, "checked", 9, "Отлично! Код чистый и понятный.", 9, 8)
        sub(a12, anna, 1, "", "n = int(input())\nfor i in range(1, 11):\n    print(f'{n} x {i} = {n * i}')", "checked", 10, "Безупречно.", 5, 4)
        sub(a13, anna, 1, "", "nums = [1, 2, 3, 4, 5]\nprint(len([n for n in nums if n % 2 == 0]))", "review", sub_days=0.2)
        sub(a21, anna, 1, "", "SELECT * FROM products WHERE price < 1000 ORDER BY name;", "checked", 8, "Верно. Лучше выбирать конкретные столбцы вместо *.", 6, 5)
        sub(a22, anna, 1, "", "SELECT o.id, c.name FROM orders o JOIN customers c ON c.id = o.customer_id;", "review", sub_days=0.4)
        # Дмитрий — работа возвращена, затем исправлена
        s_ = sub(a11, dmitry, 1, "Не уверен насчёт типов.", 'year = input("Год: ")\nprint(2026 - year)', "revision", None,
                 "Функция input() возвращает строку — вычитать из неё число нельзя. Преобразуйте значение через int().", 7, 6)
        sub(a11, dmitry, 2, "Исправил: добавил int().", age_code, "checked", 7, "Теперь работает. Добавьте проверку на некорректный ввод.", 5, 4)
        sub(a12, dmitry, 1, "", "n = int(input())\nfor i in range(1, 11):\n    print(n * i)", "review", sub_days=0.1)
        # Мария
        sub(a11, maria, 1, "", age_code, "checked", 6, "Работает, но нет пояснений и обработки ошибок.", 7, 6)
        sub(a21, maria, 1, "", "SELECT name FROM products WHERE price < 1000;", "revision", None,
            "Не хватает сортировки по названию (ORDER BY name). Дополните запрос.", 3, 2)
        # Павел — пока только начал
        sub(a11, pavel, 1, "", "print(2026 - 2007)", "revision", None,
            "Программа должна спрашивать год рождения у пользователя, а не использовать число в коде.", 3, 2)

        # уведомления
        def notify(uid, text, link):
            db.execute("INSERT INTO notifications (user_id, text, link, is_read, created_at) VALUES (?, ?, ?, 0, ?)",
                       (uid, text, link, ts(0, 2)))
        notify(t1, "Анна Смирнова отправила решение: «Чётные и нечётные» (Python для начинающих)", "/teacher/reviews")
        notify(t1, "Дмитрий Кузнецов отправил решение: «Таблица умножения» (Python для начинающих)", "/teacher/reviews")
        notify(t2, "Анна Смирнова отправила решение: «Заказы клиентов» (SQL и реляционные базы данных)", "/teacher/reviews")
        notify(maria, "Работа «Фильтрация товаров» возвращена на доработку", f"/student/assignment/{a21}")
        notify(pavel, "Работа «Калькулятор возраста» возвращена на доработку", f"/student/assignment/{a11}")
        db.commit()

    print("Демо-данные созданы. Пароль всех учётных записей:", DEMO_PASSWORD)
    print("  Администратор:  admin@kodshkola.local")
    print("  Преподаватели:  ivanova@kodshkola.local, petrov@kodshkola.local")
    print("  Студенты:       anna@, dmitry@, maria@, pavel@kodshkola.local")


if __name__ == "__main__":
    main()
