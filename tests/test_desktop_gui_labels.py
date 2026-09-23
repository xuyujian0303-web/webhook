from wecom_sales_webhook_bot.desktop_gui import (
    CONDITION_GROUP_LABELS,
    FIELD_CHOICES,
    FIELD_DROPDOWN_WIDTH,
)


def test_rule_editor_uses_chinese_filter_scope_labels() -> None:
    assert CONDITION_GROUP_LABELS == {"all": "全部满足", "any": "任一满足"}
    assert FIELD_CHOICES
    assert all("EMS server" not in choice for choice in FIELD_CHOICES)
    assert all("Local filter" not in choice for choice in FIELD_CHOICES)
    assert all(
        "EMS服务器筛选" in choice
        or "下载后本地筛选" in choice
        or "EMS查询参数/本地校验" in choice
        for choice in FIELD_CHOICES
    )
    assert "EMS查询参数/本地校验" in next(choice for choice in FIELD_CHOICES if "[style_no]" in choice)
    assert FIELD_DROPDOWN_WIDTH >= max(len(choice) for choice in FIELD_CHOICES)
