import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogFiltersRequest

# Загружаем переменные окружения
load_dotenv()

API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_NAME = 'news_aggregator_session'

async def main():
    if not API_ID or not API_HASH:
        print("Ошибка: Не найдены API_ID или API_HASH в файле .env")
        return

    print("Подключение к Telegram...")
    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)
    await client.start()
    
    print("\n--- Авторизация успешна! ---\n")

    # 1. Получаем список папок (Filters)
    print("Ищем папки с чатами (Dialog Filters)...")
    request = GetDialogFiltersRequest()
    response = await client(request)
    
    # ИСПРАВЛЕНИЕ: Если вернулся объект, берем список из атрибута .filters
    if hasattr(response, 'filters'):
        filters = response.filters
    else:
        filters = response

    print(f"\nНайдено папок: {len(filters)}")
    for f in filters:
        # У папок есть id и title. Нам нужен ID.
        # Иногда title может быть не атрибутом, а внутри объекта, проверим наличие
        title = getattr(f, 'title', 'Без названия')
        f_id = getattr(f, 'id', 'Нет ID')
        print(f"📁 Папка: '{title}' | ID: {f_id}")

    # 2. Получаем список каналов, где ты админ (для репоста)
    print("\n------------------------------------------------")
    print("Ищем каналы, куда можно постить (вы должны быть админом)...")
    
    # Пробегаем по диалогам. Это может занять время, если чатов много.
    async for dialog in client.iter_dialogs():
        if dialog.is_channel and dialog.entity.admin_rights:
             print(f"📢 Канал: '{dialog.name}' | ID: {dialog.id}")
        # Если нужно просто найти ID канала по названию (даже если не админ, но создатель)
        # раскомментируй строку ниже для вывода ВСЕХ каналов
        # elif dialog.is_channel: print(f"👁️ Канал (просмотр): '{dialog.name}' | ID: {dialog.id}")

    print("\n------------------------------------------------")
    print("ШАГИ ДЛЯ ЗАВЕРШЕНИЯ НАСТРОЙКИ:")
    print("1. Скопируй ID нужной папки в .env в поле SOURCE_FOLDER_ID")
    print("2. Скопируй ID целевого канала в .env в поле TARGET_CHANNEL_ID")
    
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
    