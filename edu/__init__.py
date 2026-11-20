"""Образовательная платформа KodShkola: фабрика приложения."""
import os
import secrets
from pathlib import Path

from flask import Flask, g, render_template, request
from markupsafe import Markup

from . import db, security, services
from .content import render_markdown

BASE_DIR = Path(__file__).resolve().parent.parent


def _persistent_secret(path: Path, nbytes: int = 32) -> str:
    """Читает секрет из файла или создаёт его при первом запуске."""
    if path.exists():
        return path.read_text().strip()
    value = secrets.token_urlsafe(nbytes)
    path.write_text(value)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return value


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_path=str(BASE_DIR / "instance"), instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    (Path(app.instance_path) / "uploads" / "covers").mkdir(parents=True, exist_ok=True)

    app.config.update(
        DATABASE=str(Path(app.instance_path) / "edu.db"),
        UPLOAD_DIR=str(Path(app.instance_path) / "uploads" / "covers"),
        SECRET_KEY=os.environ.get("EDU_SECRET_KEY") or _persistent_secret(Path(app.instance_path) / "secret_key"),
        ADMIN_INVITE_CODE=os.environ.get("EDU_ADMIN_CODE")
        or _persistent_secret(Path(app.instance_path) / "admin_invite_code", 9),
        MAX_CONTENT_LENGTH=3 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("EDU_HTTPS") == "1",
        PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    # ---------- хуки ----------
    @app.before_request
    def _before():
        security.load_user()
        security.check_csrf()

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; frame-ancestors 'none'; form-action 'self'",
        )
        if request.endpoint and request.endpoint != "static" and g.get("user"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    # ---------- шаблонный контекст ----------
    @app.context_processor
    def _ctx():
        user = g.get("user")
        return {
            "current_user": user,
            "role_name": security.ROLE_NAMES.get(user["role"]) if user else None,
            "unread": services.unread_count(user["id"]) if user else 0,
            "nav_pending": services.pending_reviews(user["id"]) if user and user["role"] == "teacher" else 0,
            "csrf_token": security.csrf_token,
            "STATUS": services.STATUS_LABELS,
            "LEVELS": services.LEVEL_LABELS,
            "LANGS": services.LANGUAGES,
        }

    @app.template_filter("md")
    def _md(text):
        return render_markdown(text)

    @app.template_filter("dt")
    def _dt(value):
        d = services.parse_dt(value)
        return d.strftime("%d.%m.%Y %H:%M") if d else "—"

    @app.template_filter("dshort")
    def _dshort(value):
        d = services.parse_dt(value)
        return d.strftime("%d.%m") if d else ""

    @app.template_filter("dateru")
    def _dateru(value):
        if not value:
            return "—"
        try:
            y, m, d = value[:10].split("-")
            return f"{d}.{m}.{y}"
        except ValueError:
            return value

    @app.template_filter("initials")
    def _initials(name):
        parts = (name or "?").split()
        return "".join(p[0] for p in parts[:2]).upper()

    @app.template_filter("plural")
    def _plural(n, one, few, many):
        n = abs(int(n or 0))
        if 11 <= n % 100 <= 14:
            return many
        return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many

    @app.template_global()
    def step_url(step):
        """Ссылка для кнопки «Продолжить» (урок или задание)."""
        from flask import url_for
        if step["kind"] == "lesson":
            return url_for("student.lesson", lesson_id=step["id"])
        return url_for("student.assignment", assignment_id=step["id"])

    @app.template_global()
    def overdue(due):
        return services.is_overdue(due)

    @app.template_global()
    def hue(seed):
        return ("#193b32", "#2f5d50", "#4d6b3c", "#7a6a3f", "#3f4f5c", "#5c4a3a")[int(seed) % 6]

    # ---------- блюпринты ----------
    from .blueprints import admin, auth, main, student, teacher
    for bp in (main.bp, auth.bp, student.bp, teacher.bp, admin.bp):
        app.register_blueprint(bp)

    # ---------- ошибки ----------
    def _error(code, title, text):
        return render_template("error.html", code=code, title=title, text=text), code

    @app.errorhandler(400)
    def _e400(e):
        return _error(400, "Некорректный запрос", getattr(e, "description", "") or "Проверьте данные и повторите.")

    @app.errorhandler(403)
    def _e403(e):
        return _error(403, "Доступ запрещён", "У вашей роли нет прав на это действие.")

    @app.errorhandler(404)
    def _e404(e):
        return _error(404, "Страница не найдена", "Такой страницы не существует или она была удалена.")

    @app.errorhandler(413)
    def _e413(e):
        return _error(413, "Файл слишком большой", "Максимальный размер загрузки — 3 МБ.")

    return app
