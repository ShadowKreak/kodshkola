"""Регистрация, вход, выход."""
import secrets

from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import execute, query
from ..security import (EMAIL_RE, ROLE_HOME, clear_failed_logins, login_blocked,
                        register_failed_login, validate_password)

bp = Blueprint("auth", __name__)

# фиктивный хеш: чтобы время ответа не выдавало, существует ли e-mail
_DUMMY_HASH = generate_password_hash("dummy-password-for-timing")


def _safe_next(target: str | None) -> str | None:
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for(ROLE_HOME[g.user["role"]]))
    form = {"full_name": "", "email": "", "role": "student"}
    if request.method == "POST":
        form["full_name"] = request.form.get("full_name", "").strip()
        form["email"] = request.form.get("email", "").strip().lower()
        form["role"] = request.form.get("role", "student")
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        code = request.form.get("admin_code", "").strip()

        error = None
        if not (2 <= len(form["full_name"]) <= 80):
            error = "Введите имя длиной от 2 до 80 символов."
        elif not EMAIL_RE.match(form["email"]) or len(form["email"]) > 120:
            error = "Введите корректный адрес электронной почты."
        elif form["role"] not in ("student", "teacher", "admin"):
            error = "Выберите роль из списка."
        elif password != confirm:
            error = "Пароли не совпадают."
        else:
            error = validate_password(password)
        if not error and form["role"] == "admin":
            if not secrets.compare_digest(code, current_app.config["ADMIN_INVITE_CODE"]):
                error = "Неверный код приглашения администратора."
        if not error and query("SELECT 1 FROM users WHERE email = ?", (form["email"],), one=True):
            error = "Пользователь с таким e-mail уже зарегистрирован."

        if error:
            flash(error, "error")
        else:
            uid = execute(
                "INSERT INTO users (email, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                (form["email"], form["full_name"], generate_password_hash(password), form["role"]),
            )
            session.clear()
            session["user_id"] = uid
            session.permanent = True
            flash("Добро пожаловать в KodShkola! Аккаунт создан.", "success")
            return redirect(url_for(ROLE_HOME[form["role"]]))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for(ROLE_HOME[g.user["role"]]))
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if login_blocked(email):
            flash("Слишком много неудачных попыток. Повторите вход через 5 минут.", "error")
        else:
            user = query("SELECT * FROM users WHERE email = ?", (email,), one=True)
            ok = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, password)
            if user and ok and not user["is_blocked"]:
                clear_failed_logins(email)
                session.clear()  # защита от фиксации сессии
                session["user_id"] = user["id"]
                session.permanent = True
                return redirect(_safe_next(request.args.get("next")) or url_for(ROLE_HOME[user["role"]]))
            if user and ok and user["is_blocked"]:
                flash("Аккаунт заблокирован администратором.", "error")
            else:
                register_failed_login(email)
                flash("Неверный e-mail или пароль.", "error")
    return render_template("auth/login.html", email=email)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for("auth.login"))
