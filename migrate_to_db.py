"""
Скрипт миграции: переносит проекты и промпты из Python-файлов в базу данных.
Запускается ОДИН раз. Безопасен для повторного запуска (не перезапишет существующие данные).
"""

from app.db import init_db, add_project, add_prompt, get_all_projects, get_all_prompts
from projects_config import PROJECTS
from app.prompts import THEME_SETTINGS

def migrate_projects():
    """Переносит проекты из projects_config.py в таблицу projects."""
    print("\n=== Миграция проектов ===")
    existing = get_all_projects()
    existing_names = [p['name'] for p in existing]

    for project in PROJECTS:
        name = project['name']
        if name in existing_names:
            print(f"  ⏭ Проект '{name}' уже есть в базе — пропускаю.")
            continue

        success = add_project(
            name=name,
            source_folder_id=project['source_folder_id'],
            target_channel_id=project['target_channel_id'],
            min_score=project.get('min_score', 7),
            prompt_type=project.get('prompt_type', 'default')
        )
        if success:
            print(f"  ✅ Проект '{name}' добавлен в базу.")
        else:
            print(f"  ❌ Ошибка при добавлении проекта '{name}'.")


def migrate_prompts():
    """Переносит промпты из app/prompts.py в таблицу prompts."""
    print("\n=== Миграция промптов ===")
    existing = get_all_prompts()
    existing_types = [p['prompt_type'] for p in existing]

    for prompt_type, settings in THEME_SETTINGS.items():
        if prompt_type in existing_types:
            print(f"  ⏭ Промпт '{prompt_type}' уже есть в базе — пропускаю.")
            continue

        success = add_prompt(
            prompt_type=prompt_type,
            role=settings['role'],
            criteria=settings['criteria'],
            summary_style=settings['summary_style']
        )
        if success:
            print(f"  ✅ Промпт '{prompt_type}' добавлен в базу.")
        else:
            print(f"  ❌ Ошибка при добавлении промпта '{prompt_type}'.")


if __name__ == "__main__":
    print("🚀 Запуск миграции...")
    init_db()
    migrate_projects()
    migrate_prompts()
    print("\n✅ Миграция завершена!")

    # Покажем результат
    print("\n--- Проекты в базе ---")
    for p in get_all_projects():
        print(f"  [{p['id']}] {p['name']} | folder={p['source_folder_id']} | channel={p['target_channel_id']} | min_score={p['min_score']} | prompt={p['prompt_type']} | active={p['is_active']} | test={p['test_mode']}")

    print("\n--- Промпты в базе ---")
    for p in get_all_prompts():
        print(f"  [{p['id']}] {p['prompt_type']} | role: {p['role'][:50]}...")
