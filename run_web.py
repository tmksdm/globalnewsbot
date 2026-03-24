from web import create_app

app = create_app()

if __name__ == "__main__":
    # debug=True — автоматическая перезагрузка при изменении кода
    # (удобно при разработке, на сервере потом выключим)
    app.run(host="0.0.0.0", port=5000, debug=True)
