from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.rule_models import (
    JobRun,
    PushRecord,
    RuleGroup,
    UserAccount,
)


def test_initialize_database_creates_core_tables(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    session_factory = create_session_factory(database_url)

    initialize_database(session_factory)

    with session_factory() as session:
        session.add(
            UserAccount(
                username="admin",
                password_hash="hash",
                role="admin",
                is_active=True,
            )
        )
        session.add(
            RuleGroup(
                name="金额规则",
                is_enabled=True,
                match_mode="any",
                updated_by="admin",
            )
        )
        session.add(
            JobRun(
                status="success",
                window_start="2026-04-22T10:00:00",
                window_end="2026-04-22T10:20:00",
            )
        )
        session.add(
            PushRecord(
                order_no="SO-1",
                store_name="G621",
                total_amount=19250,
                rule_name="金额规则",
                status="success",
            )
        )
        session.commit()

    with session_factory() as session:
        assert session.query(UserAccount).count() == 1
        assert session.query(RuleGroup).count() == 1
        assert session.query(PushRecord).count() == 1
        assert session.query(JobRun).count() == 1


def test_initialize_database_creates_global_settings_table() -> None:
    from wecom_sales_webhook_bot.rule_models import GlobalSetting

    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        database_path = Path(temp_dir) / "global-settings.db"
        database_url = f"sqlite:///{database_path}"
        session_factory = create_session_factory(database_url)

        initialize_database(session_factory)

        with session_factory() as session:
            session.add(
                GlobalSetting(
                    setting_key="message_format",
                    setting_json='{"preset": "standard"}',
                )
            )
            session.commit()

        with session_factory() as session:
            saved = session.query(GlobalSetting).one()
            assert saved.setting_key == "message_format"
            assert saved.setting_json == '{"preset": "standard"}'

        session_factory.kw["bind"].dispose()


def test_normalize_format_settings_fills_defaults_and_rejects_unknown_preset() -> None:
    from wecom_sales_webhook_bot.format_settings import (
        DEFAULT_FORMAT_SETTINGS,
        normalize_format_settings,
    )

    defaults = normalize_format_settings(None)
    assert defaults == DEFAULT_FORMAT_SETTINGS
    assert defaults is not DEFAULT_FORMAT_SETTINGS

    partial = normalize_format_settings(
        {
            "preset": "compact",
            "fields": {
                "order_no": {"enabled": False, "label": ""},
            },
        }
    )
    assert partial["preset"] == "compact"
    assert partial["fields"]["order_no"]["enabled"] is False
    assert (
        partial["fields"]["order_no"]["label"]
        == DEFAULT_FORMAT_SETTINGS["fields"]["order_no"]["label"]
    )
    assert (
        partial["fields"]["match_reason"]["enabled"]
        == DEFAULT_FORMAT_SETTINGS["fields"]["match_reason"]["enabled"]
    )

    string_false = normalize_format_settings(
        {
            "fields": {
                "match_reason": {"enabled": "false"},
                "image": {"enabled": "0"},
            },
        }
    )
    assert string_false["fields"]["match_reason"]["enabled"] is False
    assert string_false["fields"]["image"]["enabled"] is False

    with pytest.raises(ValueError, match="unsupported preset"):
        normalize_format_settings({"preset": "custom"})
