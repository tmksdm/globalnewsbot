from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.config import PANEL_PASSWORD
from web.auth import login_required

# Blueprint — это "модуль" страниц в Flask
bp = Blueprint("main", __name__)


# ========================
# АВТОРИЗАЦИЯ
# ========================

@bp.route("/login", methods=["GET", "POST"])
def login():
    """Страница входа по паролю."""
    if session.get("logged_in"):
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == PANEL_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("main.dashboard"))
        else:
            flash("Неверный пароль", "error")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    """Выход из панели."""
    session.clear()
    return redirect(url_for("main.login"))


# ========================
# ДАШБОРД (пока заглушка)
# ========================

@bp.route("/")
@login_required
def dashboard():
    """Главная страница — дашборд."""
    return render_template("dashboard.html")
