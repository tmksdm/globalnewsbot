import os
from dotenv import load_dotenv
from flask import Flask

# Папка проекта (на уровень выше, чем web/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Подтягиваем .env явно по полному пути.
# Без этого при запуске из другой папки (например, через systemd)
# переменные молча не найдутся.
load_dotenv(os.path.join(BASE_DIR, ".env"))


def create_app():
    """Создаёт и настраивает Flask-приложение."""
    flask_app = Flask(__name__)

    # Секретный ключ, которым Flask подписывает cookie сессии.
    # Берём ТОЛЬКО из .env, никаких значений по умолчанию:
    # предсказуемый ключ = любой желающий подделает себе вход в панель.
    secret = os.getenv("FLASK_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "FLASK_SECRET_KEY не задан в .env!\n"
            "Сгенерируй ключ командой:\n"
            '  python -c "import secrets; print(secrets.token_hex(32))"\n'
            "и добавь в .env строку FLASK_SECRET_KEY=<полученный ключ>"
        )
    flask_app.secret_key = secret

    # Подключаем маршруты (страницы)
    from web.routes import bp as routes_bp
    flask_app.register_blueprint(routes_bp)

    return flask_app
