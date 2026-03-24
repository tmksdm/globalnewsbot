from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.config import PANEL_PASSWORD
from app.db import (
    get_stats, get_published_news, get_all_projects, get_project_by_id,
    add_project, update_project, get_all_prompts
)
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


# ========================
# ПРОЕКТЫ
# ========================

@bp.route("/projects")
@login_required
def projects_list():
    """Список всех проектов."""
    projects = get_all_projects()
    return render_template("projects_list.html", projects=projects)


@bp.route("/projects/add", methods=["GET", "POST"])
@login_required
def projects_add():
    """Добавление нового проекта."""
    # Получаем список prompt_type из БД (чтобы показать выпадающий список)
    prompts = get_all_prompts()
    prompt_types = [p['prompt_type'] for p in prompts]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        source_folder_id = request.form.get("source_folder_id", "").strip()
        target_channel_id = request.form.get("target_channel_id", "").strip()
        min_score = request.form.get("min_score", "7").strip()
        prompt_type = request.form.get("prompt_type", "default").strip()

        # Простая валидация
        errors = []
        if not name:
            errors.append("Название проекта обязательно.")
        if not source_folder_id:
            errors.append("ID папки-источника обязателен.")
        if not target_channel_id:
            errors.append("ID целевого канала обязателен.")

        # Проверяем что числа — это числа
        try:
            source_folder_id_int = int(source_folder_id)
        except ValueError:
            errors.append("ID папки-источника должен быть числом.")
            source_folder_id_int = 0

        try:
            target_channel_id_int = int(target_channel_id)
        except ValueError:
            errors.append("ID целевого канала должен быть числом.")
            target_channel_id_int = 0

        try:
            min_score_int = int(min_score)
            if min_score_int < 1 or min_score_int > 10:
                errors.append("min_score должен быть от 1 до 10.")
        except ValueError:
            errors.append("min_score должен быть числом.")
            min_score_int = 7

        if errors:
            for error in errors:
                flash(error, "error")
            # Возвращаем форму с уже введёнными данными
            return render_template(
                "project_edit.html",
                is_new=True,
                project={
                    'name': name,
                    'source_folder_id': source_folder_id,
                    'target_channel_id': target_channel_id,
                    'min_score': min_score,
                    'prompt_type': prompt_type,
                },
                prompt_types=prompt_types,
            )

        # Пробуем добавить в базу
        success = add_project(
            name=name,
            source_folder_id=source_folder_id_int,
            target_channel_id=target_channel_id_int,
            min_score=min_score_int,
            prompt_type=prompt_type,
        )

        if success:
            flash(f"Проект «{name}» добавлен!", "success")
            return redirect(url_for("main.projects_list"))
        else:
            flash(f"Проект с именем «{name}» уже существует.", "error")
            return render_template(
                "project_edit.html",
                is_new=True,
                project={
                    'name': name,
                    'source_folder_id': source_folder_id,
                    'target_channel_id': target_channel_id,
                    'min_score': min_score,
                    'prompt_type': prompt_type,
                },
                prompt_types=prompt_types,
            )

    # GET — показываем пустую форму
    return render_template(
        "project_edit.html",
        is_new=True,
        project={
            'name': '',
            'source_folder_id': '',
            'target_channel_id': '',
            'min_score': 7,
            'prompt_type': 'default',
        },
        prompt_types=prompt_types,
    )


@bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def projects_edit(project_id):
    """Редактирование существующего проекта."""
    project = get_project_by_id(project_id)
    if not project:
        flash("Проект не найден.", "error")
        return redirect(url_for("main.projects_list"))

    # Получаем список prompt_type из БД
    prompts = get_all_prompts()
    prompt_types = [p['prompt_type'] for p in prompts]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        source_folder_id = request.form.get("source_folder_id", "").strip()
        target_channel_id = request.form.get("target_channel_id", "").strip()
        min_score = request.form.get("min_score", "7").strip()
        prompt_type = request.form.get("prompt_type", "default").strip()
        is_active = 1 if request.form.get("is_active") else 0
        test_mode = 1 if request.form.get("test_mode") else 0

        # Простая валидация
        errors = []
        if not name:
            errors.append("Название проекта обязательно.")

        try:
            source_folder_id_int = int(source_folder_id)
        except ValueError:
            errors.append("ID папки-источника должен быть числом.")
            source_folder_id_int = project['source_folder_id']

        try:
            target_channel_id_int = int(target_channel_id)
        except ValueError:
            errors.append("ID целевого канала должен быть числом.")
            target_channel_id_int = project['target_channel_id']

        try:
            min_score_int = int(min_score)
            if min_score_int < 1 or min_score_int > 10:
                errors.append("min_score должен быть от 1 до 10.")
        except ValueError:
            errors.append("min_score должен быть числом.")
            min_score_int = project['min_score']

        if errors:
            for error in errors:
                flash(error, "error")
            # Показываем форму с введёнными данными
            project_data = {
                'id': project_id,
                'name': name,
                'source_folder_id': source_folder_id,
                'target_channel_id': target_channel_id,
                'min_score': min_score,
                'prompt_type': prompt_type,
                'is_active': is_active,
                'test_mode': test_mode,
            }
            return render_template(
                "project_edit.html",
                is_new=False,
                project=project_data,
                prompt_types=prompt_types,
            )

        # Обновляем проект в базе
        update_project(
            project_id,
            name=name,
            source_folder_id=source_folder_id_int,
            target_channel_id=target_channel_id_int,
            min_score=min_score_int,
            prompt_type=prompt_type,
            is_active=is_active,
            test_mode=test_mode,
        )

        flash(f"Проект «{name}» обновлён!", "success")
        return redirect(url_for("main.projects_list"))

    # GET — показываем форму с текущими данными проекта
    return render_template(
        "project_edit.html",
        is_new=False,
        project=project,
        prompt_types=prompt_types,
    )
