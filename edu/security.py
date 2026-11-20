"""Аутентификация, роли, CSRF, ограничение попыток входа."""
import re
import secrets
import time
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for

from .db import query

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8

ROLE_HOME = {
    "student": "student.dashboard",
    "teacher": "teacher.dashboard",
    "admin": "admin.dashboard",
}
ROLE_NAMES = {"student": "Студент", "teacher": "Преподаватель", "admin": "Администратор"}


# ---------- текущий пользователь ----------
def load_user():
    uid = session.get("user_id")
    g.user = None
    if uid:
        user = query("SELECT * FROM users WHERE id = ?", (uid,), one=True)
        if user and not user["is_blocked"]:
            g.user = user
        else:
            session.clear()


def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if g.user is None:
            flash("Войдите в систему, чтобы продолжить.", "info")
            return redirect(url_for("auth.login", next=request.path))
        return view(*a, **kw)
    return wrapper


def role_required(*roles):
    def deco(view):
        @wraps(view)
        def wrapper(*a, **kw):
            if g.user is None:
                flash("Войдите в систему, чтобы продолжить.", "info")
                return redirect(url_for("auth.login", next=request.path))
            if g.user["role"] not in roles:
                abort(403)
            return view(*a, **kw)
        return wrapper
    return deco


# ---------- CSRF ----------
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def check_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token", "")
        expected = session.get("_csrf", "")
        if not expected or not secrets.compare_digest(sent, expected):
            abort(400, "Недействительный CSRF-токен. Обновите страницу и повторите.")


# ---------- защита от перебора паролей (в памяти процесса) ----------
_failed: dict[str, list[float]] = {}
MAX_ATTEMPTS = 5
WINDOW = 300  # секунд


def _key(email: str) -> str:
    return f"{request.remote_addr}|{email.lower()}"


def login_blocked(email: str) -> bool:
    now = time.time()
    hits = [t for t in _failed.get(_key(email), []) if now - t < WINDOW]
    _failed[_key(email)] = hits
    return len(hits) >= MAX_ATTEMPTS


def register_failed_login(email: str):
    _failed.setdefault(_key(email), []).append(time.time())


def clear_failed_logins(email: str):
    _failed.pop(_key(email), None)


def reset_throttle():
    _failed.clear()


def validate_password(pw: str) -> str | None:
    if len(pw) < MIN_PASSWORD_LEN:
        return f"Пароль должен содержать минимум {MIN_PASSWORD_LEN} символов."
    if pw.isdigit() or pw.isalpha():
        return "Пароль должен содержать и буквы, и цифры."
    return None
