import os
from web import create_app

# create_app() при импорте web уже подтянул .env, так что os.getenv тут работает
app = create_app()

if __name__ == "__main__":
    # debug=True поднимает отладчик Werkzeug — интерактивную Python-консоль
    # прямо в браузере при любой ошибке. В бою — категорически нельзя.
    # Нужна отладка локально: FLASK_DEBUG=1 python run_web.py
    debug = os.getenv("FLASK_DEBUG") == "1"

    # По умолчанию слушаем только саму машину — снаружи ходим через SSH-туннель.
    # Временно открыть наружу: PANEL_HOST=0.0.0.0 в .env
    host = os.getenv("PANEL_HOST", "127.0.0.1")
    port = int(os.getenv("PANEL_PORT", 5000))

    app.run(host=host, port=port, debug=debug)
