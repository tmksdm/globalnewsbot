import asyncio
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest
from telethon.extensions import html

from app.config import API_ID, API_HASH, SESSION_NAME

async def get_messages_last_hour(client, folder_id, hours=1):
    print(f"🔄 [Folder {folder_id}] Сбор новостей за {hours} ч...")

    response = await client(GetDialogFiltersRequest())
    
    if hasattr(response, 'filters'):
        dialogs = response.filters
    else:
        dialogs = response

    target_folder = None
    for f in dialogs:
        if getattr(f, 'id', None) == folder_id:
            target_folder = f
            break
            
    if not target_folder:
        print(f"❌ Папка {folder_id} не найдена!")
        return []

    peers = target_folder.include_peers
    collected_news = []
    time_threshold = datetime.now(timezone.utc) - timedelta(hours=hours)

    for peer in peers:
        try:
            entity = await client.get_entity(peer)
            
            channel_username = getattr(entity, 'username', None)
            if not channel_username and hasattr(entity, 'usernames') and entity.usernames:
                channel_username = entity.usernames[0].username

            channel_title = getattr(entity, 'title', 'Unknown')
            peer_id = entity.id

            async for message in client.iter_messages(peer, limit=20):
                if message.date < time_threshold:
                    break
                
                if not message.text:
                    continue
                
                try:
                    text_content = html.unparse(message.text, message.entities or [])
                except Exception as e:
                    print(f"⚠️ Ошибка парсинга HTML: {e}")
                    text_content = message.text

                if not text_content: 
                    continue

                if channel_username:
                    link = f"https://t.me/{channel_username}/{message.id}"
                    display_name = f"@{channel_username.lower()}"
                else:
                    link = f"https://t.me/c/{entity.id}/{message.id}"
                    display_name = channel_title

                collected_news.append({
                    "text": text_content,
                    "date": message.date,
                    "link": link,
                    "source_name": channel_title,
                    "display_name": display_name,
                    "peer_id": peer_id,
                    "msg_id": message.id,
                    "grouped_id": message.grouped_id,
                    "has_media": True if message.media else False
                })

        except Exception as e:
            continue

    print(f"✅ [Folder {folder_id}] Собрано: {len(collected_news)}")
    return collected_news
