from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.config import PANEL_PASSWORD
from app.db import (
    get_stats, get_published_news, get_all_projects, get_project_by_id,
    add_project, update_project, get_all_prompts, get_prompt_by_type,
    add_prompt, update_prompt, get_project_names
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


# ========================
# ПРОМПТЫ
# ========================

@bp.route("/prompts")
@login_required
def prompts_list():
    """Список всех промптов."""
    prompts = get_all_prompts()
    return render_template("prompts_list.html", prompts=prompts)


@bp.route("/prompts/add", methods=["GET", "POST"])
@login_required
def prompts_add():
    """Добавление нового промпта."""
    if request.method == "POST":
        prompt_type = request.form.get("prompt_type", "").strip()
        role = request.form.get("role", "").strip()
        criteria = request.form.get("criteria", "").strip()
        summary_style = request.form.get("summary_style", "").strip()

        # Валидация
        errors = []
        if not prompt_type:
            errors.append("Тип промпта (prompt_type) обязателен.")
        if not role:
            errors.append("Поле «role» обязательно.")
        if not criteria:
            errors.append("Поле «criteria» обязательно.")
        if not summary_style:
            errors.append("Поле «summary_style» обязательно.")

        # prompt_type должен быть латиницей, без пробелов (простая проверка)
        if prompt_type and not prompt_type.replace("_", "").replace("-", "").isalnum():
            errors.append("prompt_type должен содержать только латиницу, цифры, дефис и подчёркивание.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "prompt_edit.html",
                is_new=True,
                prompt={
                    'prompt_type': prompt_type,
                    'role': role,
                    'criteria': criteria,
                    'summary_style': summary_style,
                },
            )

        # Пробуем добавить в базу
        success = add_prompt(
            prompt_type=prompt_type,
            role=role,
            criteria=criteria,
            summary_style=summary_style,
        )

        if success:
            flash(f"Промпт «{prompt_type}» добавлен!", "success")
            return redirect(url_for("main.prompts_list"))
        else:
            flash(f"Промпт с типом «{prompt_type}» уже существует.", "error")
            return render_template(
                "prompt_edit.html",
                is_new=True,
                prompt={
                    'prompt_type': prompt_type,
                    'role': role,
                    'criteria': criteria,
                    'summary_style': summary_style,
                },
            )

    # GET — пустая форма
    return render_template(
        "prompt_edit.html",
        is_new=True,
        prompt={
            'prompt_type': '',
            'role': '',
            'criteria': '',
            'summary_style': '',
        },
    )


@bp.route("/prompts/<prompt_type>/edit", methods=["GET", "POST"])
@login_required
def prompts_edit(prompt_type):
    """Редактирование существующего промпта."""
    prompt = get_prompt_by_type(prompt_type)
    if not prompt:
        flash("Промпт не найден.", "error")
        return redirect(url_for("main.prompts_list"))

    if request.method == "POST":
        role = request.form.get("role", "").strip()
        criteria = request.form.get("criteria", "").strip()
        summary_style = request.form.get("summary_style", "").strip()

        # Валидация
        errors = []
        if not role:
            errors.append("Поле «role» обязательно.")
        if not criteria:
            errors.append("Поле «criteria» обязательно.")
        if not summary_style:
            errors.append("Поле «summary_style» обязательно.")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "prompt_edit.html",
                is_new=False,
                prompt={
                    'prompt_type': prompt_type,
                    'role': role,
                    'criteria': criteria,
                    'summary_style': summary_style,
                },
            )

        # Обновляем в базе
        update_prompt(
            prompt_type=prompt_type,
            role=role,
            criteria=criteria,
            summary_style=summary_style,
        )

        flash(f"Промпт «{prompt_type}» обновлён!", "success")
        return redirect(url_for("main.prompts_list"))

    # GET — показываем форму с текущими данными
    return render_template(
        "prompt_edit.html",
        is_new=False,
        prompt=prompt,
    )


# ========================
# ЛОГ ПУБЛИКАЦИЙ
# ========================

@bp.route("/logs")
@login_required
def logs():
    """Таблица всех опубликованных новостей с фильтрацией."""

    # Читаем параметры фильтрации из URL (query string)
    # Например: /logs?project=tech_news&date_from=2025-01-01&date_to=2025-01-31&page=2
    selected_project = request.args.get("project", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    page = request.args.get("page", 1, type=int)

    # Сколько записей на одной странице
    per_page = 30

    # Защита: страница не может быть меньше 1
    if page < 1:
        page = 1

    # offset — сколько записей пропустить (для пагинации)
    # Страница 1 → пропустить 0, Страница 2 → пропустить 30, и т.д.
    offset = (page - 1) * per_page

    # Получаем новости из БД с учётом фильтров
    # Запрашиваем per_page + 1 записей, чтобы понять, есть ли следующая страница
    news_list = get_published_news(
        project_name=selected_project if selected_project else None,
        date_from=date_from if date_from else None,
        date_to=date_to if date_to else None,
        limit=per_page + 1,
        offset=offset,
    )

    # Если получили больше записей, чем per_page — значит есть следующая страница
    has_next = len(news_list) > per_page
    # Но показываем только per_page записей (лишнюю отрезаем)
    news_list = news_list[:per_page]

    # Список всех проектов для выпадающего фильтра
    project_names = get_project_names()

    return render_template(
        "logs.html",
        news_list=news_list,
        project_names=project_names,
        selected_project=selected_project,
        date_from=date_from,
        date_to=date_to,
        page=page,
        has_next=has_next,
    )
