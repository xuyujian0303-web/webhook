from wecom_sales_webhook_bot.desktop_gui import build_template_reference_text


def test_template_reference_lists_order_item_loop_and_filters() -> None:
    text = build_template_reference_text()

    assert "{{ order.order_no }}" in text
    assert "{{ order.total_amount }}" in text
    assert "{% for item in order.items %}" in text
    assert "{{ item.image_markdown }}" in text
    assert "{{ order.total_amount | money }}" in text
    assert "{{ order.sold_at | datetime }}" in text
    assert "商品变量不能在循环外使用" in text
