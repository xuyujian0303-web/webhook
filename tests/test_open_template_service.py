from wecom_sales_webhook_bot.message_template_service import build_preview_template_context


def test_preview_context_contains_all_order_and_item_variables() -> None:
    context = build_preview_template_context()

    assert context["order"]["salesperson"] == "张三"
    assert context["order"]["total_quantity"] == 2
    assert context["order"]["customer_source"] == "会员推荐"
    assert context["order"]["promotion_material"] == "秋季画册"
    assert context["order"]["card_type"] == "金卡"
    assert len(context["order"]["items"]) == 2
    assert context["order"]["items"][0]["image_url"] == "http://intranet.images/1.jpg"
