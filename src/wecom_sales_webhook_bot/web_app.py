from __future__ import annotations

from flask import Flask, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, login_required, login_user

from wecom_sales_webhook_bot.auth import hash_password, verify_password
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.rule_models import UserAccount


class LoginUser(UserMixin):
    def __init__(self, user_id: int) -> None:
        self.id = str(user_id)


def create_app(config: dict) -> Flask:
    app = Flask(__name__)
    app.config.update(config)
    session_factory = create_session_factory(app.config["DATABASE_URL"])
    initialize_database(session_factory)

    login_manager = LoginManager()
    login_manager.login_view = "login_page"
    login_manager.init_app(app)

    with session_factory() as session:
        if session.query(UserAccount).count() == 0:
            seed = app.config["BOOTSTRAP_ADMIN"]
            session.add(
                UserAccount(
                    username=seed["username"],
                    password_hash=hash_password(seed["password"]),
                    role="admin",
                    is_active=True,
                )
            )
            session.commit()

    @app.get("/login")
    def login_page():
        return render_template("login.html")

    @app.post("/login")
    def login_submit():
        with session_factory() as session:
            user = (
                session.query(UserAccount)
                .filter_by(username=request.form["username"])
                .one()
            )
            if verify_password(user.password_hash, request.form["password"]):
                login_user(LoginUser(user.id))
                return redirect(url_for("rules_page"))
        return redirect(url_for("login_page"))

    @app.get("/rules")
    @login_required
    def rules_page():
        return "rules"

    return app
