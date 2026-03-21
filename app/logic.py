import asyncio
import hashlib
import re
from telethon import TelegramClient

from app.config import API_ID, API_HASH, SESSION_NAME, LOG_CHANNEL_ID
from app.monitor import get_messages_last_hour
from app.ai import pick_top_news_batch, check_is_duplicate, generate_summary
from app.db import add_news, is_exists, get_recent_news

async def send_log_report(client, text):
    """Отправляет сообщение в технический канал."""
    try:
        await client.send_message(LOG_CHANNEL_ID, text, link_preview=False, parse_mode='html')
    except Exception as e:
        print(f"⚠️ Report Error: {e}")

def fix_formatting(text):
    if not text: return text
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.*?)__', r'<i>\1</i>', text)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)
    return text

async def send_news_with_media(client, text, news_item, target_channel_id):
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
            sent_msg = await client.send_message(target_channel_id, text, link_preview=False, parse_mode='html')
        else:
            media_to_send = []
            if grouped_id:
                album_messages = [] 
                async for m in client.iter_messages(source_peer, min_id=msg_id-10, limit=20):
                    if m.grouped_id == grouped_id:
                        album_messages.append(m)
                
                if album_messages:
                    album_messages.sort(key=lambda x: x.id)
                    media_to_send = [m.media for m in album_messages]
                else:
                    original_msg = await client.get_messages(source_peer, ids=msg_id)
                    media_to_send = original_msg.media
            else:
                original_msg = await client.get_messages(source_peer, ids=msg_id)
                media_to_send = original_msg.media

            result = await client.send_file(target_channel_id, file=media_to_send, caption=text, parse_mode='html')
            
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
            await client.send_message(target_channel_id, text, parse_mode=None)
            return True, None, channel_title
        except:
            return False, None, channel_title


async def process_project_news(client, project_conf, hours=1.6):
    p_name = project_conf['name']
    p_source_id = project_conf['source_folder_id']
    p_target_id = project_conf['target_channel_id']
    p_prompt_type = project_conf.get('prompt_type', 'default')

    print(f"\n🚀 ЗАПУСК ПРОЕКТА: {p_name}")
    
    stats = {
        "total_found": 0,
        "local_filtered": 0,
        "ai_candidates": 0,
        "rejected_dupe": 0,
        "final_score": 0,
        "winner_source": "None"
    }

    # 1. Сбор
    raw_news = await get_messages_last_hour(client, folder_id=p_source_id, hours=hours)
    stats["total_found"] = len(raw_news)
    
    if not raw_news:
        print(f"📭 {p_name}: Пусто.")
        await send_log_report(client, f"📭 **Проект: {p_name}**\nНет новых сообщений в папке за {hours}ч.")
        return

    # 2. Локальный фильтр
    valid_news = []
    for item in raw_news:
        if len(item['text']) < 50: continue
        content_hash = hashlib.md5(item['text'].encode()).hexdigest()
        if is_exists(p_name, content_hash): continue
        item['hash'] = content_hash
        valid_news.append(item)
    
    stats["local_filtered"] = len(valid_news)

    if not valid_news:
        print(f"🧹 {p_name}: Все отсеяны локальным фильтром.")
        await send_log_report(client, f"🧹 **Проект: {p_name}**\nНайдено: {len(raw_news)}, но все отсеяны (короткие или уже были).")
        return

    # 3. AI Отбор
    print(f"📤 {p_name}: Отправляю в AI {len(valid_news)} заголовков...")
    candidates = pick_top_news_batch(valid_news, prompt_type=p_prompt_type)
    stats["ai_candidates"] = len(candidates)

    if not candidates:
        print(f"📉 {p_name}: AI вернул пустой список.")
        await send_log_report(client, f"📉 **Проект: {p_name}**\nНайдено: {len(valid_news)} | Кандидатов: 0 (ничего важного/интересного).")
        return

    final_winner = None
    winner_summary = ""
    recent_history = get_recent_news(project_name=p_name, days=2)

    # 4. Перебор кандидатов
    for cand in candidates:
        idx = cand['id']
        score = cand.get('score', 0)
        
        if idx >= len(valid_news): continue
        
        candidate_news = valid_news[idx]
        print(f"   🧐 Кандидат #{idx} (Score: {score}). Проверяем на дубли...")

        if check_is_duplicate(candidate_news['text'], recent_history):
            stats["rejected_dupe"] += 1
            print("   ⛔ ДУБЛЬ.")
            continue
        
        print("   ✍️ Чистка текста...")
        raw_summary = generate_summary(candidate_news['text'], prompt_type=p_prompt_type)
        if not raw_summary: continue

        clean_summary = fix_formatting(raw_summary)

        final_winner = candidate_news
        winner_summary = clean_summary
        final_winner['score'] = score
        stats["final_score"] = score
        stats["winner_source"] = candidate_news['source_name']
        break

    if not final_winner:
        print(f"🤷‍♂️ {p_name}: Все кандидаты оказались дублями.")
        fail_report = (
            f"⚠️ **Проект: {p_name}**\n"
            f"🔎 Найдено: {stats['total_found']} | Кандидатов: {stats['ai_candidates']}\n"
            f"🗑 Отсеяно как дубли: {stats['rejected_dupe']}\n"
            f"🤷‍♂️ Ничего не опубликовано."
        )
        await send_log_report(client, fail_report)
        return

    # 5. Публикация
    link_source = final_winner['link']
    display_name = final_winner['display_name'].lower()
    
    final_message = f"{winner_summary} <a href='{link_source}'>{display_name}</a>"
    
    success, post_link, ch_title = await send_news_with_media(client, final_message, final_winner, p_target_id)
    
    if success:
        add_news(
            project_name=p_name,
            content_hash=final_winner['hash'],
            original_text=final_winner['text'],
            summary=winner_summary,
            score=final_winner['score'],
            source_link=link_source
        )
        print(f"✅ {p_name}: Успех!")
        
        clean_for_log = re.sub('<[^<]+?>', '', winner_summary)
        first_sentence = clean_for_log.split('\n')[0][:50].strip() + "..."
        
        if post_link:
            final_link_str = f"🔗 <a href='{post_link}'>{first_sentence}</a>"
        else:
            final_link_str = f"🔗 {first_sentence} (без ссылки)"
        
        report_text = (
            f"🚀 <b>Проект: {p_name}</b>\n"
            f"📊 Найдено: {stats['total_found']} | Кандидатов: {stats['ai_candidates']} | Отсеяно дублей: {stats['rejected_dupe']}\n"
            f"🏆 Источник: {stats['winner_source']} ({stats['final_score']}/10)\n"
            f"{final_link_str}"
        )
        await send_log_report(client, report_text)
        
    else:
        print(f"❌ {p_name}: Ошибка публикации.")
        await send_log_report(client, f"❌ **Проект: {p_name}**\nОшибка при попытке отправить пост в канал.")
