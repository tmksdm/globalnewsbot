import os
from flask import Flask
from app.config import PANEL_PASSWORD


def create_app():
    """Создаёт и настраивает Flask-приложение."""
    flask_app = Flask(__name__)

    # Секретный ключ нужен Flask для работы сессий (авторизация)
    # Берём из переменной окружения или генерируем из пароля
    flask_app.secret_key = os.getenv("FLASK_SECRET_KEY", f"newsbot-secret-{PANEL_PASSWORD}")

    # Подключаем маршруты (страницы)
    from web.routes import bp as routes_bp
    flask_app.register_blueprint(routes_bp)

    return flask_app
