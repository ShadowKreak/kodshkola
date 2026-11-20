PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name     TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('student', 'teacher', 'admin')),
    is_blocked    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS courses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    category_id  INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    level        TEXT NOT NULL DEFAULT 'beginner'
                 CHECK (level IN ('beginner', 'intermediate', 'advanced')),
    teacher_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    cover_path   TEXT,
    is_published INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_courses_teacher ON courses(teacher_id);

CREATE TABLE IF NOT EXISTS sections (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    title     TEXT NOT NULL,
    position  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sections_course ON sections(course_id);

CREATE TABLE IF NOT EXISTS lessons (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    content_md TEXT NOT NULL DEFAULT '',
    position   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_lessons_section ON lessons(section_id);

CREATE TABLE IF NOT EXISTS code_examples (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    title     TEXT NOT NULL,
    language  TEXT NOT NULL DEFAULT 'python',
    code      TEXT NOT NULL,
    position  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_examples_lesson ON code_examples(lesson_id);

-- kind: practice = обычное практическое задание, final = итоговый проект
CREATE TABLE IF NOT EXISTS assignments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id      INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    section_id     INTEGER REFERENCES sections(id) ON DELETE CASCADE,
    title          TEXT NOT NULL,
    description_md TEXT NOT NULL DEFAULT '',
    due_date       TEXT,
    kind           TEXT NOT NULL DEFAULT 'practice' CHECK (kind IN ('practice', 'final')),
    position       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_assignments_course ON assignments(course_id);

CREATE TABLE IF NOT EXISTS enrollments (
    student_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id   INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    enrolled_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (student_id, course_id)
);

CREATE TABLE IF NOT EXISTS lesson_progress (
    student_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lesson_id    INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    completed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (student_id, lesson_id)
);

-- Последний открытый урок нужен для быстрого продолжения обучения.
CREATE TABLE IF NOT EXISTS lesson_visits (
    student_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id       INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id       INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    last_viewed_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (student_id, course_id)
);
CREATE INDEX IF NOT EXISTS idx_lesson_visits_student ON lesson_visits(student_id, last_viewed_at);

-- Каждая попытка сдачи — отдельная строка. «Не отправлено» = строк нет.
-- status: review = на проверке, checked = проверено, revision = требуются исправления
CREATE TABLE IF NOT EXISTS submissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id   INTEGER NOT NULL REFERENCES assignments(id) ON DELETE CASCADE,
    student_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    attempt         INTEGER NOT NULL DEFAULT 1,
    answer_text     TEXT NOT NULL DEFAULT '',
    code            TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'review'
                    CHECK (status IN ('review', 'checked', 'revision')),
    score           INTEGER CHECK (score IS NULL OR (score BETWEEN 1 AND 10)),
    teacher_comment TEXT NOT NULL DEFAULT '',
    submitted_at    TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at     TEXT,
    UNIQUE (assignment_id, student_id, attempt)
);
CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_id);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(status);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    link       TEXT,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read);
