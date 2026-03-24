from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.config import PANEL_PASSWORD
from app.db import get_stats, get_published_news, get_all_projects
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
# ДАШБОРД
# ========================

@bp.route("/")
@login_required
def dashboard():
    """Главная страница — дашборд со статистикой."""

    # Получаем список проектов из БД
    projects = get_all_projects()

    # Собираем статистику по КАЖДОМУ проекту
    project_stats = []
    for project in projects:
        stats = get_stats(project_name=project['name'])
        project_stats.append({
            'name': project['name'],
            'is_active': project['is_active'],
            'test_mode': project['test_mode'],
            'today': stats['today'],
            'week': stats['week'],
            'total': stats['total'],
            'avg_score': stats['avg_score'],
        })

    # Общая статистика (по всем проектам)
    total_stats = get_stats()

    # Последние 20 публикаций
    recent_news = get_published_news(limit=20)

    return render_template(
        "dashboard.html",
        project_stats=project_stats,
        total_stats=total_stats,
        recent_news=recent_news,
    )
