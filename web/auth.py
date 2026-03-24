from functools import wraps
from flask import session, redirect, url_for


def login_required(f):
    """
    Декоратор: если пользователь не авторизован — перенаправляет на страницу входа.
    Ставится перед каждой страницей, которую нужно защитить.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("main.login"))
        return f(*args, **kwargs)
    return decorated_function
