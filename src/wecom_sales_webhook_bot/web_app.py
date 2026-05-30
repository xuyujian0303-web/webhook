from __future__ import annotations

from flask import Flask, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, login_required, login_user

from wecom_sales_webhook_bot.auth import hash_password, verify_password
from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.rule_models import RuleCondition, RuleGroup, UserAccount


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

    @login_manager.user_loader
    def load_user(user_id: str):
        with session_factory() as session:
            user = session.get(UserAccount, int(user_id))
            if user is None or not user.is_active:
                return None
            return LoginUser(user.id)

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
        with session_factory() as session:
            rules = session.query(RuleGroup).order_by(RuleGroup.updated_at.desc()).all()
        return render_template("rules.html", rules=rules)

    @app.get("/rules/new")
    @login_required
    def rule_new_page():
        return render_template("rule_edit.html")

    @app.post("/rules/new")
    @login_required
    def rule_new_submit():
        with session_factory() as session:
            rule = RuleGroup(
                name=request.form["name"],
                is_enabled=request.form.get("is_enabled") == "on",
                match_mode=request.form["match_mode"],
                updated_by="admin",
            )
            session.add(rule)
            session.flush()

            def add_condition(field_name: str, operator: str, value_json: str) -> None:
                if value_json:
                    session.add(
                        RuleCondition(
                            rule_group_id=rule.id,
                            field_name=field_name,
                            operator=operator,
                            value_json=value_json,
                        )
                    )

            add_condition("total_amount", "gte", request.form["amount_threshold"])
            add_condition("style_no", "in", request.form["style_list"])
            add_condition("store_name", "in", request.form["store_list"])
            if request.form["time_start"] and request.form["time_end"]:
                add_condition(
                    "sold_at",
                    "between_time",
                    f"{request.form['time_start']},{request.form['time_end']}",
                )
            add_condition("brand", "in", request.form["brand_list"])
            add_condition("category", "in", request.form["category_list"])

            session.commit()
        return redirect(url_for("rules_page"))

    return app
