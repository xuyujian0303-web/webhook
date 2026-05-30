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
