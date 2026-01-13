import asyncio
import hashlib
from telethon import TelegramClient

from app.config import API_ID, API_HASH, SESSION_NAME, LOG_CHANNEL_ID
from app.monitor import get_messages_last_hour
from app.ai import pick_top_news_batch, check_is_duplicate, generate_summary
from app.db import add_news, is_exists, get_recent_news

async def send_log_report(text):
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    try:
        await client.send_message(LOG_CHANNEL_ID, text, link_preview=False)
    except Exception as e:
        print(f"⚠️ Report Error: {e}")
    finally:
        await client.disconnect()

async def send_news_with_media(text, news_item, target_channel_id):
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    post_link = None
    channel_title = "Channel"
    try:
        entity = await client.get_entity(target_channel_id)
        channel_title = getattr(entity, 'title', str(target_channel_id))
        channel_username = getattr(entity, 'username', None)

        source_peer = news_item['peer_id']
        msg_id = news_item['msg_id']
        grouped_id = news_item['grouped_id']
        sent_msg = None

        if not news_item['has_media']:
            sent_msg = await client.send_message(target_channel_id, text, link_preview=False)
        else:
            media_to_send = []
            if grouped_id:
                album_messages = []
                async for m in client.iter_messages(source_peer, min_id=msg_id-10, limit=20):
                    if m.grouped_id == grouped_id:
                        album_messages.append(m)
                album_messages.sort(key=lambda x: x.id)
                if album_messages:
                    media_to_send = [m.media for m in album_messages]
                else:
                    original_msg = await client.get_messages(source_peer, ids=msg_id)
                    media_to_send = original_msg.media
            else:
                original_msg = await client.get_messages(source_peer, ids=msg_id)
                media_to_send = original_msg.media
            result = await client.send_file(target_channel_id, file=media_to_send, caption=text)
            if isinstance(result, list): sent_msg = result[0]
            else: sent_msg = result

        if sent_msg:
            if channel_username:
                post_link = f"https://t.me/{channel_username}/{sent_msg.id}"
            else:
                real_id = str(entity.id).replace("-100", "")
                post_link = f"https://t.me/c/{real_id}/{sent_msg.id}"
        return True, post_link, channel_title
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        try:
            await client.send_message(target_channel_id, text)
            return True, None, channel_title
        except:
            return False, None, channel_title
    finally:
        await client.disconnect()

# === ГЛАВНАЯ ЛОГИКА ===
async def process_project_news(project_conf, hours=1.6):
    p_name = project_conf['name']
    p_source_id = project_conf['source_folder_id']
    p_target_id = project_conf['target_channel_id']
    p_min_score = project_conf.get('min_score', 7)
    p_prompt_type = project_conf.get('prompt_type', 'default')

    print(f"\n🚀 ЗАПУСК ПРОЕКТА: {p_name} (Стиль: {p_prompt_type})")
    
    raw_news = await get_messages_last_hour(folder_id=p_source_id, hours=hours)
    
    if not raw_news:
        print(f"📭 {p_name}: Пусто.")
        return

    valid_news = []
    for item in raw_news:
        if len(item['text']) < 50: continue
        content_hash = hashlib.md5(item['text'].encode()).hexdigest()
        if is_exists(p_name, content_hash): continue
        item['hash'] = content_hash
        valid_news.append(item)

    if not valid_news:
        print(f"🧹 {p_name}: Все новости отсеяны локальным фильтром.")
        return

    print(f"📤 {p_name}: Отправляю в AI {len(valid_news)} заголовков...")

    # Батчинг
    candidates = pick_top_news_batch(valid_news, prompt_type=p_prompt_type)

    if not candidates:
        print(f"📉 {p_name}: AI не выбрал ничего достойного.")
        return

    final_winner = None
    winner_summary = ""
    recent_history = get_recent_news(project_name=p_name, days=2)

    for cand in candidates:
        idx = cand['id']
        score = cand.get('score', 0)
        
        if idx >= len(valid_news): continue
        if score < p_min_score:
            print(f"   Skip: News #{idx} score {score} < {p_min_score}")
            continue

        candidate_news = valid_news[idx]
        print(f"   🧐 Проверяю кандидата #{idx} (Score: {score})...")

        if check_is_duplicate(candidate_news['text'], recent_history):
            print("   ⛔ ДУБЛЬ (уже было).")
            continue
        
        print("   ✍️ Генерирую пост...")
        summary = generate_summary(candidate_news['text'], prompt_type=p_prompt_type)
        if not summary: continue

        final_winner = candidate_news
        winner_summary = summary
        final_winner['score'] = score
        break

    if not final_winner:
        print(f"🤷‍♂️ {p_name}: Все кандидаты отсеяны.")
        return

    link_source = final_winner['link']
    display_name = final_winner['display_name'].lower()
    final_message = f"{winner_summary} [{display_name}]({link_source})"
    
    success, post_link, ch_title = await send_news_with_media(final_message, final_winner, p_target_id)
    
    if success:
        add_news(
            project_name=p_name,
            content_hash=final_winner['hash'],
            original_text=final_winner['text'],
            summary=winner_summary,
            score=final_winner['score'],
            source_link=link_source
        )
        print(f"✅ {p_name}: Опубликовано в {ch_title}!")
        report_link = post_link if post_link else link_source
        await send_log_report(f"🤖 **Проект: {p_name}**\n✅ Опубликовано в: {ch_title}\n🔗 [Ссылка на пост]({report_link})")
    else:
        print(f"❌ {p_name}: Ошибка публикации.")
