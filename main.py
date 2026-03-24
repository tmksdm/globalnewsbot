import asyncio
import logging
import random
import sys
from logging.handlers import TimedRotatingFileHandler
import os
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from app.config import API_ID, API_HASH, SESSION_NAME
from app.logic import process_project_news, send_log_report
from app.db import get_active_projects

# Фолбэк — если в базе нет проектов, берём из файла
from projects_config import PROJECTS as FILE_PROJECTS

# --- Настройка логирования ---
if not os.path.exists("logs"):
    os.makedirs("logs")

log_handler = TimedRotatingFileHandler(
    filename="logs/bot.log",
    when="W0",
    interval=1,
    backupCount=1,
    encoding="utf-8"
)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
log_handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logging.getLogger('telethon').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)

# --- Настройки глобальной паузы ---
MIN_WAIT_MINUTES = 60
MAX_WAIT_MINUTES = 80

# ЧАСОВОЙ ПОЯС: Владивосток (UTC+10)
TZ_VLADIVOSTOK = timezone(timedelta(hours=10))


def load_projects():
    """
    Загружает проекты из БД. Если в базе пусто — из файла (фолбэк).
    """
    db_projects = get_active_projects()
    if db_projects:
        logger.info(f"📂 Загружено {len(db_projects)} проектов из БД.")
        return db_projects
    else:
        logger.warning("⚠️ В БД нет проектов! Использую projects_config.py как фолбэк.")
        return FILE_PROJECTS


async def main():
    # === ОДИН КЛИЕНТ НА ВЕСЬ ЖИЗНЕННЫЙ ЦИКЛ ===
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    logger.info("🤖 Мульти-бот запущен!")
    await send_log_report(client, "🚀 Бот перезапущен")

    try:
        while True:
            try:
                logger.info("\n⏰ === НАЧАЛО ЧАСОВОГО ЦИКЛА ===")

                # Загружаем проекты КАЖДЫЙ ЦИКЛ (чтобы изменения из веб-панели подхватывались)
                projects = load_projects()

                for project in projects:
                    p_name = project['name']
                    try:
                        logger.info(f"👉 Обработка проекта: {p_name}")

                        await process_project_news(client, project_conf=project, hours=1.5)

                        logger.info("💤 Пауза 30 сек перед следующим проектом...")
                        await asyncio.sleep(30)

                    except Exception as e:
                        err_text = f"⚠️ Ошибка внутри проекта {p_name}: {e}"
                        logger.error(err_text, exc_info=True)
                        await send_log_report(client, err_text)

                # Расчет следующего запуска
                wait_minutes = random.randint(MIN_WAIT_MINUTES, MAX_WAIT_MINUTES)
                wait_seconds = wait_minutes * 60

                now_utc = datetime.now(timezone.utc)
                next_run_utc = now_utc + timedelta(minutes=wait_minutes)
                next_run_vdk = next_run_utc.astimezone(TZ_VLADIVOSTOK)
                next_run_str = next_run_vdk.strftime("%H:%M")

                logger.info(
                    f"✅ Цикл завершен. Сплю {wait_minutes} мин. Следующий старт (VDK): {next_run_str}")

                await send_log_report(client,
                                      f"💤 **Цикл завершен**\nСледующий запуск через {wait_minutes} мин, ориентировочно в **{next_run_str}.**")

                await asyncio.sleep(wait_seconds)

            except KeyboardInterrupt:
                logger.info("🛑 Бот остановлен вручную.")
                sys.exit()
            except Exception as e:
                logger.critical(f"🔥 Критическая ошибка в Main Loop: {e}", exc_info=True)
                await send_log_report(client, f"🔥 Критическая ошибка Main: {e}")
                await asyncio.sleep(600)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Стоп.")
