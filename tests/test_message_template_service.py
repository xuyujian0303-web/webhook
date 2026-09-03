from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.message_template_service import (
    DEFAULT_TEMPLATE_NAME,
    TemplateDeleteError,
    activate_message_template,
    build_preview_template_context,
    delete_message_template,
    load_or_initialize_message_template_store,
    save_message_template,
)


def test_load_or_initialize_message_template_store_creates_default_store(tmp_path) -> None:
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'app.db'}")
    initialize_database(session_factory)

    with session_factory() as session:
        store = load_or_initialize_message_template_store(session)

    assert store["active_template_id"]
    assert len(store["templates"]) == 1
    assert store["templates"][0]["name"] == DEFAULT_TEMPLATE_NAME
    assert store["templates"][0]["id"] == store["active_template_id"]
    assert "{{ order.order_no }}" in store["templates"][0]["template_body"]


def test_save_message_template_appends_new_template_when_id_missing(tmp_path) -> None:
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'app.db'}")
    initialize_database(session_factory)

    with session_factory() as session:
        store = load_or_initialize_message_template_store(session)
        saved = save_message_template(
            session,
            template_id=None,
            template_name="自定义模板A",
            template_body="# 标题A\n{{ items_markdown }}",
            preset_key="compact",
            activate=True,
        )
        updated_store = load_or_initialize_message_template_store(session)

    assert saved["name"] == "自定义模板A"
    assert saved["preset_key"] == "compact"
    assert len(updated_store["templates"]) == 2
    assert updated_store["active_template_id"] == saved["id"]


def test_activate_message_template_switches_active_template(tmp_path) -> None:
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'app.db'}")
    initialize_database(session_factory)

    with session_factory() as session:
        first = load_or_initialize_message_template_store(session)["templates"][0]
        second = save_message_template(
            session,
            template_id=None,
            template_name="模板B",
            template_body="# 模板B",
            preset_key="detailed",
            activate=False,
        )
        store = activate_message_template(session, second["id"])

    assert store["active_template_id"] == second["id"]
    assert store["active_template_id"] != first["id"]


def test_delete_message_template_rejects_active_template(tmp_path) -> None:
    session_factory = create_session_factory(f"sqlite:///{tmp_path / 'app.db'}")
    initialize_database(session_factory)

    with session_factory() as session:
        active_template = load_or_initialize_message_template_store(session)["templates"][0]
        save_message_template(
            session,
            template_id=None,
            template_name="模板B",
            template_body="# 模板B",
            preset_key="detailed",
            activate=False,
        )

        try:
            delete_message_template(session, active_template["id"])
        except TemplateDeleteError as exc:
            assert "active" in str(exc)
        else:
            raise AssertionError("expected TemplateDeleteError")


def test_build_preview_template_context_returns_fixed_sample_data() -> None:
    context = build_preview_template_context()

    assert context["order"]["order_no"] == "SOG609260605001"
    assert "DRCH042ABK0" in context["items_markdown"]
    assert "http://127.0.0.1:8123/DRCH042ABK0.png" in context["items_markdown"]
