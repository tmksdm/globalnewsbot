import asyncio
import logging
import random
import sys
from logging.handlers import TimedRotatingFileHandler
import os

from app.logic import process_project_news, send_log_report
from projects_config import PROJECTS

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

# === ВОТ ЭТО МЫ ДОБАВИЛИ, ЧТОБЫ УБРАТЬ ШУМ ===
# Говорим Telethon-у: "Не пиши мне про Connect/Disconnect, пиши только ошибки"
logging.getLogger('telethon').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)

# --- Настройки глобальной паузы ---
MIN_WAIT_MINUTES = 60
MAX_WAIT_MINUTES = 80

async def main():
    logger.info("🤖 Мульти-бот запущен!")
    await send_log_report("🚀 Бот перезапущен в мульти-режиме (поддержка нескольких проектов).")
    
    while True:
        try:
            logger.info("\n⏰ === НАЧАЛО ЧАСОВОГО ЦИКЛА ===")
            
            # Пробегаем по списку проектов из projects_config.py
            for project in PROJECTS:
                p_name = project['name']
                try:
                    logger.info(f"👉 Обработка проекта: {p_name}")
                    
                    # Запускаем логику для конкретного проекта
                    await process_project_news(project_conf=project, hours=1.5)
                    
                    # Небольшая пауза между проектами
                    logger.info("💤 Пауза 30 сек перед следующим проектом...")
                    await asyncio.sleep(30)
                    
                except Exception as e:
                    err_text = f"⚠️ Ошибка внутри проекта {p_name}: {e}"
                    logger.error(err_text, exc_info=True)
                    await send_log_report(err_text)

            # Когда все проекты прошли, спим большой промежуток
            wait_minutes = random.randint(MIN_WAIT_MINUTES, MAX_WAIT_MINUTES)
            wait_seconds = wait_minutes * 60
            
            logger.info(f"✅ Все проекты обработаны. Сплю {wait_minutes} мин.")
            await asyncio.sleep(wait_seconds)

        except KeyboardInterrupt:
            logger.info("🛑 Бот остановлен вручную.")
            sys.exit()
        except Exception as e:
            logger.critical(f"🔥 Критическая ошибка в Main Loop: {e}", exc_info=True)
            await send_log_report(f"🔥 Критическая ошибка Main: {e}")
            await asyncio.sleep(600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Стоп.")
