from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.config import PANEL_PASSWORD, get_ai_model
from app.db import (
    get_stats, get_published_news, get_all_projects, get_project_by_id,
    add_project, update_project, get_all_prompts, get_prompt_by_type,
    add_prompt, update_prompt, get_project_names, get_total_stats,
    get_setting, set_setting
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

    # Общая статистика за всё время (из счётчика)
    all_time_stats = get_total_stats()

    # Собираем статистику по КАЖДОМУ проекту
    project_stats = []
    for project in projects:
        stats = get_stats(project_name=project['name'])
        total_project = get_total_stats(project_name=project['name'])
        project_stats.append({
            'name': project['name'],
            'is_active': project['is_active'],
            'test_mode': project['test_mode'],
            'publish_mode': project.get('publish_mode', 'summary'),
            'today': stats['today'],
            'week': stats['week'],
            'total': total_project['total'],
            'avg_score': total_project['avg_score'],
        })

    # Статистика за сегодня/неделю (из processed_news, там точные данные за 5 дней)
    total_stats = get_stats()
    # Подменяем "всего" и "средний score" на данные из вечного счётчика
    total_stats['total'] = all_time_stats['total']
    total_stats['avg_score'] = all_time_stats['avg_score']

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
    prompts = get_all_prompts()
    prompt_types = [p['prompt_type'] for p in prompts]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        source_folder_id = request.form.get("source_folder_id", "").strip()
        target_channel_id = request.form.get("target_channel_id", "").strip()
        min_score = request.form.get("min_score", "7").strip()
        prompt_type = request.form.get("prompt_type", "default").strip()
        publish_mode = request.form.get("publish_mode", "summary").strip()

        errors = []
        if not name:
            errors.append("Название проекта обязательно.")
        if not source_folder_id:
            errors.append("ID папки-источника обязателен.")
        if not target_channel_id:
            errors.append("ID целевого канала обязателен.")

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

        if publish_mode not in ('summary', 'repost'):
            errors.append("Режим публикации должен быть 'summary' или 'repost'.")
            publish_mode = 'summary'

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "project_edit.html",
                is_new=True,
                project={
                    'name': name,
                    'source_folder_id': source_folder_id,
                    'target_channel_id': target_channel_id,
                    'min_score': min_score,
                    'prompt_type': prompt_type,
                    'publish_mode': publish_mode,
                },
                prompt_types=prompt_types,
            )

        success = add_project(
            name=name,
            source_folder_id=source_folder_id_int,
            target_channel_id=target_channel_id_int,
            min_score=min_score_int,
            prompt_type=prompt_type,
            publish_mode=publish_mode,
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
                    'publish_mode': publish_mode,
                },
                prompt_types=prompt_types,
            )

    return render_template(
        "project_edit.html",
        is_new=True,
        project={
            'name': '',
            'source_folder_id': '',
            'target_channel_id': '',
            'min_score': 7,
            'prompt_type': 'default',
            'publish_mode': 'summary',
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

    prompts = get_all_prompts()
    prompt_types = [p['prompt_type'] for p in prompts]

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        source_folder_id = request.form.get("source_folder_id", "").strip()
        target_channel_id = request.form.get("target_channel_id", "").strip()
        min_score = request.form.get("min_score", "7").strip()
        prompt_type = request.form.get("prompt_type", "default").strip()
        publish_mode = request.form.get("publish_mode", "summary").strip()
        is_active = 1 if request.form.get("is_active") else 0
        test_mode = 1 if request.form.get("test_mode") else 0

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

        if publish_mode not in ('summary', 'repost'):
            errors.append("Режим публикации должен быть 'summary' или 'repost'.")
            publish_mode = project.get('publish_mode', 'summary')

        if errors:
            for error in errors:
                flash(error, "error")
            project_data = {
                'id': project_id,
                'name': name,
                'source_folder_id': source_folder_id,
                'target_channel_id': target_channel_id,
                'min_score': min_score,
                'prompt_type': prompt_type,
                'publish_mode': publish_mode,
                'is_active': is_active,
                'test_mode': test_mode,
            }
            return render_template(
                "project_edit.html",
                is_new=False,
                project=project_data,
                prompt_types=prompt_types,
            )

        update_project(
            project_id,
            name=name,
            source_folder_id=source_folder_id_int,
            target_channel_id=target_channel_id_int,
            min_score=min_score_int,
            prompt_type=prompt_type,
            publish_mode=publish_mode,
            is_active=is_active,
            test_mode=test_mode,
        )

        flash(f"Проект «{name}» обновлён!", "success")
        return redirect(url_for("main.projects_list"))

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

        errors = []
        if not prompt_type:
            errors.append("Тип промпта (prompt_type) обязателен.")
        if not role:
            errors.append("Поле «role» обязательно.")
        if not criteria:
            errors.append("Поле «criteria» обязательно.")
        if not summary_style:
            errors.append("Поле «summary_style» обязательно.")

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

        update_prompt(
            prompt_type=prompt_type,
            role=role,
            criteria=criteria,
            summary_style=summary_style,
        )

        flash(f"Промпт «{prompt_type}» обновлён!", "success")
        return redirect(url_for("main.prompts_list"))

    return render_template(
        "prompt_edit.html",
        is_new=False,
        prompt=prompt,
    )


# ========================
# НАСТРОЙКИ
# ========================

@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Страница настроек — выбор AI-модели и т.д."""
    if request.method == "POST":
        ai_model = request.form.get("ai_model", "").strip()

        if not ai_model:
            flash("Имя модели не может быть пустым.", "error")
        else:
            set_setting("ai_model", ai_model)
            flash(f"Модель изменена на «{ai_model}»!", "success")

        return redirect(url_for("main.settings"))

    # GET — показываем текущие настройки
    current_model = get_ai_model()

    return render_template(
        "settings.html",
        current_model=current_model,
    )


# ========================
# УПРАВЛЕНИЕ БОТОМ
# ========================

@bp.route("/bot/restart", methods=["POST"])
@login_required
def bot_restart():
    """Перезапуск бота через systemd."""
    import subprocess
    try:
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "newsbot.service"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            flash("Бот перезапущен!", "success")
        else:
            flash(f"Ошибка: {result.stderr}", "error")
    except Exception as e:
        flash(f"Ошибка: {e}", "error")

    return redirect(url_for("main.dashboard"))


@bp.route("/bot/status")
@login_required
def bot_status():
    """Проверка статуса бота."""
    import subprocess
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "newsbot.service"],
            capture_output=True, text=True, timeout=5
        )
        status = result.stdout.strip()
    except Exception:
        status = "unknown"

    return {"status": status}


# ========================
# ЛОГ ПУБЛИКАЦИЙ
# ========================

@bp.route("/logs")
@login_required
def logs():
    """Таблица всех опубликованных новостей с фильтрацией."""

    selected_project = request.args.get("project", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    page = request.args.get("page", 1, type=int)

    per_page = 30

    if page < 1:
        page = 1

    offset = (page - 1) * per_page

    news_list = get_published_news(
        project_name=selected_project if selected_project else None,
        date_from=date_from if date_from else None,
        date_to=date_to if date_to else None,
        limit=per_page + 1,
        offset=offset,
    )

    has_next = len(news_list) > per_page
    news_list = news_list[:per_page]

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
