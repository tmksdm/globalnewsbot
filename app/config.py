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
AI_MODEL = "arcee-ai/trinity-large-preview:free"

# === Канал для технических отчетов ===
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

# === Веб-панель ===
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "admin")

# === Тестовый режим ===
TEST_CHANNEL_ID = int(os.getenv("TEST_CHANNEL_ID", 0))
