import json
import requests
from app.config import OPENROUTER_API_KEY, AI_MODEL
from app.prompts import (
    THEME_SETTINGS, 
    COMMON_BATCH_RULES, 
    COMMON_SUMMARY_FORMAT, 
    DEDUPLICATION_SYSTEM_PROMPT
)

def _clean_json_response(content):
    content = content.replace("```json", "").replace("```", "").strip()
    return content

def get_combined_prompt(prompt_type, task_type):
    """
    Собирает промпт как конструктор.
    """
    # 1. Берем тему (или default)
    theme = THEME_SETTINGS.get(prompt_type, THEME_SETTINGS["default"])
    
    if task_type == 'batch':
        # СБОР: Роль + Критерии + Техника (0-10, JSON)
        return f"{theme['role']}\n\nКРИТЕРИИ ОТБОРА:\n{theme['criteria']}\n\n{COMMON_BATCH_RULES}"
    
    else:
        # САММАРИ: Роль + Стиль (из темы) + Техника (JSON)
        return f"{theme['role']}\n\n{theme['summary_style']}\n\n{COMMON_SUMMARY_FORMAT}"

def pick_top_news_batch(news_list, prompt_type="default"):
    if not news_list:
        return []

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
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Список новостей:\n{batch_text}"}
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        parsed = json.loads(_clean_json_response(content))
        return parsed.get("candidates", [])
    except Exception as e:
        print(f"❌ AI Batch Error: {e}")
        return []

def generate_summary(text, prompt_type="default"):
    system_prompt = get_combined_prompt(prompt_type, 'summary')

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Текст новости:\n{text}"}
        ]
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        parsed = json.loads(_clean_json_response(content))
        return parsed.get("summary", text[:200])
    except Exception as e:
        print(f"❌ AI Summary Error: {e}")
        return None

def check_is_duplicate(new_text, old_news_list):
    if not old_news_list:
        return False 

    history_text = ""
    for idx, item in enumerate(old_news_list):
        history_text += f"{idx+1}. {item[0]}\n"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    user_content = f"СПИСОК СТАРЫХ:\n{history_text}\n\nНОВАЯ:\n{new_text}"

    data = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": DEDUPLICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ]
    }

    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        result = response.json()['choices'][0]['message']['content']
        parsed = json.loads(_clean_json_response(result))
        return parsed.get("is_duplicate", False)
    except Exception as e:
        print(f"❌ AI Deduplication Error: {e}")
        return False
    