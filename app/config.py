import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SOURCE_FOLDER_ID = int(os.getenv('SOURCE_FOLDER_ID', 0))
TARGET_CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID', 0))
SESSION_NAME = 'news_aggregator_session'

# AI
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
# Модель, которую ты выбрал
AI_MODEL = "xiaomi/mimo-v2-flash:free"

# === Канал для технических отчетов ===
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))