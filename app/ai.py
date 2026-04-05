import json
import time
import requests
from app.config import OPENROUTER_API_KEY, get_ai_model
from app.prompts import (
    THEME_SETTINGS,
    COMMON_BATCH_RULES,
    COMMON_SUMMARY_FORMAT,
    DEDUPLICATION_SYSTEM_PROMPT
)
from app.db import get_prompt_by_type


# === Кэш промптов ===
# Хранит собранные промпты в памяти, чтобы не дёргать БД на каждый вызов AI.
# Сбрасывается в начале каждого цикла бота (вызовом clear_prompt_cache из main.py).
_prompt_cache = {}


def clear_prompt_cache():
    """Сбрасывает кэш промптов. Вызывай в начале каждого цикла бота."""
    global _prompt_cache
    _prompt_cache = {}


def _clean_json_response(content):
    content = content.replace("```json", "").replace("```", "").strip()
    return content


def _get_model_or_fail():
    """
    Возвращает имя модели. Если не задана — выбрасывает ошибку.
    """
    model = get_ai_model()
    if not model:
        raise ValueError("❌ AI-модель не задана! Зайдите в веб-панель → Настройки и укажите модель.")
    return model


def get_combined_prompt(prompt_type, task_type):
    """
    Собирает промпт как конструктор.
    Сначала проверяет кэш, потом БД, потом файл prompts.py (фолбэк).
    """
    # Проверяем кэш
    cache_key = f"{prompt_type}_{task_type}"
    if cache_key in _prompt_cache:
        return _prompt_cache[cache_key]

    # 1. Пробуем взять из базы данных
    db_prompt = get_prompt_by_type(prompt_type)

    if db_prompt:
        theme = {
            'role': db_prompt['role'],
            'criteria': db_prompt['criteria'],
            'summary_style': db_prompt['summary_style']
        }
    else:
        # 2. Фолбэк на файл prompts.py
        print(f"⚠️ Промпт '{prompt_type}' не найден в БД, использую файл.")
        theme = THEME_SETTINGS.get(prompt_type, THEME_SETTINGS["default"])

    if task_type == 'batch':
        result = f"{theme['role']}\n\nКРИТЕРИИ ОТБОРА:\n{theme['criteria']}\n\n{COMMON_BATCH_RULES}"
    else:
        result = f"{theme['role']}\n\n{theme['summary_style']}\n\n{COMMON_SUMMARY_FORMAT}"

    # Сохраняем в кэш
    _prompt_cache[cache_key] = result
    return result


def pick_top_news_batch(news_list, prompt_type="default"):
    if not news_list:
        return []

    model = _get_model_or_fail()
    system_prompt = get_combined_prompt(prompt_type, 'batch')

    batch_text = ""
    for idx, item in enumerate(news_list):
        snippet = item['text'][:400].replace("\n", " ")
        batch_text += f"{idx}. [{item['source_name']}] {snippet}...\n"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Список новостей:\n{batch_text}"}
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=30)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        parsed = json.loads(_clean_json_response(content))
        return parsed.get("candidates", [])
    except Exception as e:
        print(f"❌ AI Batch Error: {e}")
        return []


def generate_summary(text, prompt_type="default"):
    model = _get_model_or_fail()
    system_prompt = get_combined_prompt(prompt_type, 'summary')

    # Обрезаем текст до 3000 символов — этого достаточно для пересказа
    trimmed_text = text[:3000]

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Текст новости:\n{trimmed_text}"}
        ]
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=30)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        parsed = json.loads(_clean_json_response(content))
        return parsed.get("summary", text[:200])
    except Exception as e:
        print(f"❌ AI Summary Error: {e}")
        return None


def check_is_duplicate(new_text, old_news_list):
    """Старая AI-дедупликация. Больше не используется (заменена на локальную в app/dedup.py).
    Оставлена на случай, если захочешь вернуть."""
    if not old_news_list:
        return False

    model = _get_model_or_fail()

    history_text = ""
    for idx, item in enumerate(old_news_list):
        history_text += f"{idx+1}. {item[0]}\n"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    user_content = f"СПИСОК СТАРЫХ:\n{history_text}\n\nНОВАЯ:\n{new_text}"

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": DEDUPLICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()['choices'][0]['message']['content']
        parsed = json.loads(_clean_json_response(result))
        return parsed.get("is_duplicate", False)
    except Exception as e:
        print(f"❌ AI Deduplication Error: {e}")
        return False
