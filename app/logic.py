import asyncio
import hashlib
import re
from telethon import TelegramClient
from telethon.tl.types import MessageEntityCustomEmoji, MessageEntityTextUrl

from app.config import API_ID, API_HASH, SESSION_NAME, LOG_CHANNEL_ID, TEST_CHANNEL_ID
from app.monitor import get_messages_last_hour
from app.ai import pick_top_news_batch, generate_summary, clean_selfpromo, shrink_summary
from telethon.extensions import html as tg_html
from app.dedup import is_duplicate_local
from app.db import add_news, is_exists, get_recent_news, is_seen, mark_as_seen, cleanup_seen_news, add_publish_count


async def send_log_report(client, text):
    """Отправляет сообщение в технический канал."""
    try:
        await client.send_message(LOG_CHANNEL_ID, text, link_preview=False, parse_mode='html')
    except Exception as e:
        print(f"⚠️ Report Error: {e}")


def fix_formatting(text):
    if not text:
        return text
    # Заменяем теги, которые Telegram не понимает
    text = text.replace('<strong>', '<b>').replace('</strong>', '</b>')
    text = text.replace('<em>', '<i>').replace('</em>', '</i>')
    # Если AI вернул markdown — конвертируем
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.*?)__', r'<i>\1</i>', text)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    # Литеральные \n (если AI вернул как текст)
    text = text.replace('\\n', '\n')
    # Убираем тройные+ переносы
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def strip_custom_emoji(entities):
    """
    Убирает премиум-эмодзи (MessageEntityCustomEmoji) из списка entities.
    Обычный Unicode-эмодзи (fallback) остаётся в тексте на тех же позициях.
    Возвращает новый список entities без кастомных эмодзи.
    """
    if not entities:
        return []
    return [e for e in entities if not isinstance(e, MessageEntityCustomEmoji)]


def trim_entities_to_text(entities, new_length):
    """
    Обрезает entities после того, как AI удалил саморекламу из конца текста.
    Все entities, которые выходят за границу нового текста, обрезаются или удаляются.

    entities — оригинальные Telegram entities
    new_length — длина очищенного текста (len(cleaned_text))

    Возвращает новый список entities.
    """
    if not entities:
        return []

    trimmed = []
    for e in entities:
        # Entity полностью за пределами нового текста — выкидываем
        if e.offset >= new_length:
            continue

        # Entity частично за пределами — обрезаем длину
        if e.offset + e.length > new_length:
            new_len = new_length - e.offset
            if new_len <= 0:
                continue
            # Создаём копию entity с новой длиной
            try:
                d = e.to_dict()
                d.pop('_', None)
                d['length'] = new_len
                e_copy = type(e)(**d)
                trimmed.append(e_copy)
            except Exception:
                # Если не получилось скопировать — просто пропускаем
                pass
        else:
            trimmed.append(e)

    return trimmed

# === ЛИМИТЫ TELEGRAM ===
TEXT_LIMIT = 4096      # максимум символов в обычном сообщении
CAPTION_LIMIT = 1024   # максимум символов в подписи к фото/видео/галерее


def utf16_len(text):
    """Длина строки так, как её считает Telegram (UTF-16), а не Python."""
    if not text:
        return 0
    return len(text.encode('utf-16-le')) // 2


_TAG_RE = re.compile(
    r'</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|a|blockquote|tg-spoiler)'
    r'(?:\s[^<>]*)?/?>',
    re.IGNORECASE
)
_AMP_RE = re.compile(r'&(?!#?\w+;)')


def _escape_chunk(chunk):
    chunk = _AMP_RE.sub('&amp;', chunk)
    return chunk.replace('<', '&lt;').replace('>', '&gt;')


def sanitize_html(text):
    """Оставляет только теги, понятные Telegram; всё остальное экранирует."""
    if not text:
        return text
    out = []
    pos = 0
    for m in _TAG_RE.finditer(text):
        out.append(_escape_chunk(text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(_escape_chunk(text[pos:]))
    return ''.join(out)


def html_to_entities(html_text):
    """HTML -> (чистый текст, entities). Ничего не обрезает."""
    return tg_html.parse(sanitize_html(html_text or ''))


def to_plain(html_text):
    """HTML -> текст без тегов (для аварийной отправки)."""
    plain, _ = html_to_entities(html_text)
    return plain


def visible_len(html_text):
    """Сколько символов Telegram насчитает в тексте (теги не считаются)."""
    return utf16_len(to_plain(html_text))


def fit_summary(html_text, budget, attempts=3):
    """
    Добивается, чтобы текст уложился в budget символов.
    НИЧЕГО НЕ ОБРЕЗАЕТ — только просит AI пересказать плотнее.
    Возвращает (текст, влез_ли).
    """
    text = html_text
    for i in range(attempts):
        current = visible_len(text)
        if current <= budget:
            return text, True
        target = int(budget * (0.95 - 0.05 * i))
        print(f"   📏 {current} симв. при лимите {budget}. "
              f"Прошу AI ужать до {target} (попытка {i + 1}/{attempts})...")
        shorter = fix_formatting(shrink_summary(text, target))
        if not shorter or visible_len(shorter) >= current:
            break  # AI не смог сжать — дальше крутить бессмысленно
        text = shorter
    return text, visible_len(text) <= budget


async def collect_media(client, source_peer, msg_id, grouped_id):
    """Достаёт медиа исходного сообщения (или всего альбома)."""
    if grouped_id:
        album_messages = []
        async for m in client.iter_messages(source_peer, min_id=msg_id - 10, limit=20):
            if m.grouped_id == grouped_id:
                album_messages.append(m)
        if album_messages:
            album_messages.sort(key=lambda x: x.id)
            return [m.media for m in album_messages]
    original_msg = await client.get_messages(source_peer, ids=msg_id)
    return original_msg.media


async def send_news_with_media(client, text, news_item, target_channel_id):
    """Отправляет новость как HTML-текст + медиа. Используется для режима summary."""
    post_link = None
    channel_title = "Channel"
    try:
        entity = await client.get_entity(target_channel_id)
        channel_title = getattr(entity, 'title', str(target_channel_id))
        channel_username = getattr(entity, 'username', None)

        # Разметку чиним ДО отправки и сразу превращаем в entities,
        # чтобы Telegram гарантированно её принял
        body, entities = html_to_entities(text)

        source_peer = news_item['peer_id']
        msg_id = news_item['msg_id']
        grouped_id = news_item['grouped_id']
        first_msg = None

        with_media = news_item['has_media'] and not news_item.get('force_no_media')

        # Страховка: текст не режем никогда, лучше отдадим пост без медиа
        if with_media and utf16_len(body) > CAPTION_LIMIT:
            print(f"⚠️ Текст {utf16_len(body)} симв. не влезает в подпись — публикую без медиа.")
            with_media = False

        if with_media:
            media_to_send = await collect_media(client, source_peer, msg_id, grouped_id)
            result = await client.send_file(
                target_channel_id, file=media_to_send,
                caption=body, formatting_entities=entities
            )
            first_msg = result[0] if isinstance(result, list) else result
        else:
            first_msg = await client.send_message(
                target_channel_id, body,
                formatting_entities=entities, link_preview=False
            )

        if first_msg:
            if channel_username:
                post_link = f"https://t.me/{channel_username}/{first_msg.id}"
            else:
                real_id = str(entity.id).replace("-100", "")
                post_link = f"https://t.me/c/{real_id}/{first_msg.id}"
        return True, post_link, channel_title

    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        await send_log_report(
            client,
            f"⚠️ <b>Сбой отправки (саммари)</b>\n<code>{_escape_chunk(str(e))}</code>"
        )
        try:
            await client.send_message(
                target_channel_id, to_plain(text), parse_mode=None, link_preview=False
            )
            return True, None, channel_title
        except Exception as e2:
            print(f"❌ Аварийная отправка тоже упала: {e2}")
            return False, None, channel_title


async def send_repost_with_media(client, cleaned_text, entities, news_item, target_channel_id):
    """
    Отправляет «репост» — копию оригинального сообщения с сохранением форматирования.
    """
    post_link = None
    channel_title = "Channel"
    try:
        entity_obj = await client.get_entity(target_channel_id)
        channel_title = getattr(entity_obj, 'title', str(target_channel_id))
        channel_username = getattr(entity_obj, 'username', None)

        source_peer = news_item['peer_id']
        msg_id = news_item['msg_id']
        grouped_id = news_item['grouped_id']
        first_msg = None

        link_source = news_item['link']
        display_name = news_item['display_name'].lower()
        credit_prefix = "\n\n"

        body = cleaned_text.rstrip()
        final_text = body
        final_entities = list(entities)

        # ВАЖНО: Telegram считает позиции в UTF-16, а не в символах Python.
        # Из-за обычного len() ссылка на источник уезжала, если в тексте были эмодзи.
        credit_size = utf16_len(credit_prefix) + utf16_len(display_name)
        if utf16_len(body) + credit_size <= TEXT_LIMIT:
            credit_offset = utf16_len(body) + utf16_len(credit_prefix)
            final_text = body + credit_prefix + display_name
            final_entities.append(MessageEntityTextUrl(
                offset=credit_offset,
                length=utf16_len(display_name),
                url=link_source
            ))
        else:
            print("⚠️ Репост у самого лимита — публикую без приписки с источником.")

        with_media = news_item['has_media']
        if with_media and utf16_len(final_text) > CAPTION_LIMIT:
            print(f"⚠️ Репост {utf16_len(final_text)} симв. не влезает в подпись — публикую без медиа.")
            with_media = False

        if with_media:
            media_to_send = await collect_media(client, source_peer, msg_id, grouped_id)
            result = await client.send_file(
                target_channel_id, file=media_to_send,
                caption=final_text, formatting_entities=final_entities
            )
            first_msg = result[0] if isinstance(result, list) else result
        else:
            first_msg = await client.send_message(
                target_channel_id, final_text,
                formatting_entities=final_entities, link_preview=False
            )

        if first_msg:
            if channel_username:
                post_link = f"https://t.me/{channel_username}/{first_msg.id}"
            else:
                real_id = str(entity_obj.id).replace("-100", "")
                post_link = f"https://t.me/c/{real_id}/{first_msg.id}"
        return True, post_link, channel_title

    except Exception as e:
        print(f"❌ Ошибка отправки (repost): {e}")
        await send_log_report(
            client,
            f"⚠️ <b>Сбой отправки (репост)</b>\n<code>{_escape_chunk(str(e))}</code>"
        )
        try:
            fallback_text = cleaned_text.rstrip() + f"\n\n{news_item['display_name'].lower()}"
            await client.send_message(
                target_channel_id, fallback_text, parse_mode=None, link_preview=False
            )
            return True, None, channel_title
        except Exception as e2:
            print(f"❌ Аварийная отправка тоже упала: {e2}")
            return False, None, channel_title


async def process_project_news(client, project_conf, hours=1.6):
    p_name = project_conf['name']
    p_source_id = project_conf['source_folder_id']
    p_target_id = project_conf['target_channel_id']
    p_prompt_type = project_conf.get('prompt_type', 'default')
    p_test_mode = project_conf.get('test_mode', 0)
    p_min_score = project_conf.get('min_score', 7)
    p_publish_mode = project_conf.get('publish_mode', 'summary')

    # Определяем канал для публикации
    if p_test_mode and TEST_CHANNEL_ID:
        publish_channel_id = TEST_CHANNEL_ID
        mode_label = "ТЕСТ"
    else:
        publish_channel_id = p_target_id
        mode_label = "ПРОД"

    publish_label = "РЕПОСТ" if p_publish_mode == "repost" else "САММАРИ"
    print(f"\n🚀 ЗАПУСК ПРОЕКТА: {p_name} [{mode_label}] [{publish_label}]")

    stats = {
        "total_found": 0,
        "local_filtered": 0,
        "already_seen": 0,
        "ai_candidates": 0,
        "rejected_dupe": 0,
        "rejected_low_score": 0,
        "final_score": 0,
        "winner_source": "None"
    }

    # 1. Сбор
    raw_news = await get_messages_last_hour(client, folder_id=p_source_id, hours=hours)
    stats["total_found"] = len(raw_news)

    if not raw_news:
        print(f"📭 {p_name}: Пусто.")
        await send_log_report(client, f"📭 **Проект: {p_name}** [{mode_label}]\nНет новых сообщений в папке за {hours}ч.")
        return

    # 2. Локальный фильтр + фильтр уже виденных
    valid_news = []
    seen_count = 0
    for item in raw_news:
        if len(item['text']) < 50:
            continue
        content_hash = hashlib.md5(item['text'].encode()).hexdigest()

        # Уже опубликовано?
        if is_exists(p_name, content_hash):
            continue

        # Уже отправляли в AI (но не опубликовали)?
        if is_seen(p_name, content_hash):
            seen_count += 1
            continue

        item['hash'] = content_hash
        valid_news.append(item)

    stats["local_filtered"] = len(valid_news)
    stats["already_seen"] = seen_count

    if not valid_news:
        print(f"🧹 {p_name}: Все отсеяны локальным фильтром (из них уже видели: {seen_count}).")
        if seen_count == 0:
            await send_log_report(client,
                                  f"🧹 **Проект: {p_name}** [{mode_label}]\nНайдено: {len(raw_news)}, но все отсеяны (короткие или уже были).")
        return

    # Помечаем все новости как виденные ПЕРЕД отправкой в AI
    all_hashes = [item['hash'] for item in valid_news]
    mark_as_seen(p_name, all_hashes)

    # 3. AI Отбор (одинаковый для обоих режимов — prompt_type определяет тематику)
    print(f"📤 {p_name}: Отправляю в AI {len(valid_news)} заголовков...")
    candidates = pick_top_news_batch(valid_news, prompt_type=p_prompt_type)
    stats["ai_candidates"] = len(candidates)

    if not candidates:
        print(f"📉 {p_name}: AI вернул пустой список.")
        await send_log_report(client,
                              f"📉 **Проект: {p_name}** [{mode_label}]\nНайдено: {len(valid_news)} | Кандидатов: 0 (ничего важного/интересного).")
        return

    final_winner = None
    winner_text_for_publish = ""
    winner_entities_for_publish = []
    recent_history = get_recent_news(project_name=p_name, days=2)

    # 4. Перебор кандидатов
    for cand in candidates:
        idx = cand['id']
        score = cand.get('score', 0)

        if idx >= len(valid_news):
            continue

        # Пропускаем кандидатов ниже минимального score
        if score < p_min_score:
            stats["rejected_low_score"] += 1
            print(f"   ⏭️ Кандидат #{idx} (Score: {score}) — ниже min_score ({p_min_score}), пропускаю.")
            continue

        candidate_news = valid_news[idx]
        print(f"   🧐 Кандидат #{idx} (Score: {score}). Проверяем на дубли...")

        if is_duplicate_local(candidate_news['text'], recent_history):
            stats["rejected_dupe"] += 1
            print("   ⛔ ДУБЛЬ.")
            continue

        # === РАЗВИЛКА ПО РЕЖИМУ ПУБЛИКАЦИИ ===
        if p_publish_mode == "repost":
            # --- РЕЖИМ РЕПОСТА ---
            print("   🔄 Режим: РЕПОСТ. Чистим саморекламу...")
            raw_text = candidate_news.get('raw_text', '')
            original_entities = candidate_news.get('entities', []) or []

            if not raw_text:
                print("   ⚠️ raw_text пустой, пропускаю кандидата.")
                continue

            # AI убирает рекламу из plain text
            cleaned = clean_selfpromo(raw_text)
            if not cleaned:
                continue

            # Подгоняем entities под новый текст. Если AI переписал текст,
            # а не просто отрезал рекламу с конца, старые entities больше
            # не совпадают — тогда отправляем без разметки.
            if raw_text.startswith(cleaned.rstrip()):
                clean_entities = strip_custom_emoji(original_entities)
                clean_entities = trim_entities_to_text(clean_entities, utf16_len(cleaned))
            else:
                clean_entities = []

            final_winner = candidate_news
            winner_text_for_publish = cleaned
            winner_entities_for_publish = clean_entities
            final_winner['score'] = score
            stats["final_score"] = score
            stats["winner_source"] = candidate_news['source_name']
            break

        else:
            # --- РЕЖИМ САММАРИ ---
            print("   ✍️ Режим: САММАРИ. Генерируем пересказ...")

            # Считаем бюджет так, чтобы пост ушёл ОДНИМ сообщением
            # вместе с картинкой или галереей
            reserve = len(candidate_news['display_name']) + 3
            if p_test_mode:
                reserve += len(f"[ТЕСТ: {p_name}]") + 2
            reserve += 10  # запас
            if candidate_news['has_media']:
                budget = CAPTION_LIMIT - reserve
            else:
                budget = TEXT_LIMIT - reserve

            raw_summary = generate_summary(
                candidate_news['text'], prompt_type=p_prompt_type, max_chars=budget
            )
            if not raw_summary:
                continue

            clean_summary = fix_formatting(raw_summary)
            clean_summary, fits = fit_summary(clean_summary, budget)

            if not fits and candidate_news['has_media']:
                # Текст не режем ни при каких условиях — публикуем целиком, но без медиа
                candidate_news['force_no_media'] = True
                print("   ⚠️ AI не уложился в лимит подписи — пост уйдёт без медиа.")

            final_winner = candidate_news
            winner_text_for_publish = clean_summary
            winner_entities_for_publish = []  # Не используется в режиме summary
            final_winner['score'] = score
            stats["final_score"] = score
            stats["winner_source"] = candidate_news['source_name']
            break

    if not final_winner:
        print(f"🤷‍♂️ {p_name}: Все кандидаты оказались дублями или ниже min_score.")
        fail_report = (
            f"⚠️ **Проект: {p_name}** [{mode_label}]\n"
            f"🔎 Найдено: {stats['total_found']} | Кандидатов: {stats['ai_candidates']}\n"
            f"🗑 Дубли: {stats['rejected_dupe']} | Низкий score: {stats['rejected_low_score']}\n"
            f"🤷‍♂️ Ничего не опубликовано."
        )
        await send_log_report(client, fail_report)
        return

    # 5. Публикация
    link_source = final_winner['link']
    display_name = final_winner['display_name'].lower()

    if p_publish_mode == "repost":
        # --- РЕПОСТ: отправляем с entities ---
        if p_test_mode:
            # В тестовом режиме добавляем метку в начало текста
            test_prefix = f"[ТЕСТ: {p_name}]\n\n"
            winner_text_for_publish = test_prefix + winner_text_for_publish
            # Сдвигаем все entities на длину префикса
            shift = utf16_len(test_prefix)
            shifted_entities = []
            for e in winner_entities_for_publish:
                try:
                    d = e.to_dict()
                    d.pop('_', None)
                    d['offset'] = e.offset + shift
                    shifted_entities.append(type(e)(**d))
                except Exception:
                    pass
            winner_entities_for_publish = shifted_entities

        success, post_link, ch_title = await send_repost_with_media(
            client, winner_text_for_publish, winner_entities_for_publish,
            final_winner, publish_channel_id
        )
    else:
        # --- САММАРИ: отправляем как HTML (как раньше) ---
        if p_test_mode:
            final_message = f"[ТЕСТ: {p_name}]\n\n{winner_text_for_publish} <a href='{link_source}'>{display_name}</a>"
        else:
            final_message = f"{winner_text_for_publish} <a href='{link_source}'>{display_name}</a>"

        success, post_link, ch_title = await send_news_with_media(
            client, final_message, final_winner, publish_channel_id
        )

    if success:
        if not p_test_mode:
            add_news(
                project_name=p_name,
                content_hash=final_winner['hash'],
                original_text=final_winner['text'],
                summary=winner_text_for_publish,
                score=final_winner['score'],
                source_link=link_source
            )
            add_publish_count(p_name, final_winner['score'])
            print(f"✅ {p_name}: Опубликовано в ПРОД! [{publish_label}]")
        else:
            print(f"🧪 {p_name}: Опубликовано в ТЕСТ-канал (в базу НЕ сохранено). [{publish_label}]")

        clean_for_log = re.sub('<[^<]+?>', '', winner_text_for_publish)
        first_sentence = clean_for_log.split('\n')[0][:50].strip() + "..."

        if post_link:
            final_link_str = f"🔗 <a href='{post_link}'>{first_sentence}</a>"
        else:
            final_link_str = f"🔗 {first_sentence} (без ссылки)"

        report_text = (
            f"🚀 <b>Проект: {p_name}</b> [{mode_label}] [{publish_label}]\n"
            f"📊 Найдено: {stats['total_found']} | Новых: {stats['local_filtered']} | Кандидатов: {stats['ai_candidates']} | Дубли: {stats['rejected_dupe']} | Низкий score: {stats['rejected_low_score']}\n"
            f"🏆 Источник: {stats['winner_source']} ({stats['final_score']}/10)\n"
            f"{final_link_str}"
        )
        await send_log_report(client, report_text)

    else:
        print(f"❌ {p_name}: Ошибка публикации.")
        await send_log_report(client, f"❌ **Проект: {p_name}** [{mode_label}]\nОшибка при попытке отправить пост в канал.")
