# app/dedup.py
from difflib import SequenceMatcher

# Порог схожести: если тексты похожи больше чем на 45% — считаем дублем.
# Можешь подкрутить: больше число = строже (пропускает больше), меньше = мягче.
SIMILARITY_THRESHOLD = 0.45


def is_duplicate_local(new_text, recent_news_list):
    """
    Проверяет, дублирует ли новый текст что-то из уже опубликованного.
    recent_news_list — список кортежей (summary, original_text) из get_recent_news().
    Возвращает True если дубль, False если нет.
    """
    if not recent_news_list:
        return False

    # Берём первые 500 символов для сравнения (больше — не нужно)
    new_short = _normalize(new_text[:500])

    for old_summary, old_original in recent_news_list:
        # Сравниваем с саммари (короткий текст — быстрее)
        old_short = _normalize((old_summary or "")[:500])
        ratio = SequenceMatcher(None, new_short, old_short).ratio()
        if ratio >= SIMILARITY_THRESHOLD:
            return True

        # Если саммари сильно отличается, проверяем ещё по оригиналу
        old_orig_short = _normalize((old_original or "")[:500])
        ratio2 = SequenceMatcher(None, new_short, old_orig_short).ratio()
        if ratio2 >= SIMILARITY_THRESHOLD:
            return True

    return False


def _normalize(text):
    """Убирает HTML-теги и лишние пробелы для чистого сравнения."""
    import re
    text = re.sub(r'<[^>]+>', '', text)  # Убираем HTML
    text = re.sub(r'\s+', ' ', text)     # Схлопываем пробелы
    return text.strip().lower()
