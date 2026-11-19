from __future__ import annotations

REFERENCE_VARIABLES = [
    {"token": "order.order_no", "label": "销售单号", "scope": "订单", "example": "SO-1001"},
    {"token": "order.sold_at", "label": "销售时间", "scope": "订单", "example": "2026-08-21 10:30:00"},
    {"token": "order.store_name", "label": "门店", "scope": "订单", "example": "G830"},
    {"token": "order.performance_org", "label": "业绩机构", "scope": "订单", "example": "G889"},
    {"token": "order.store_name_display", "label": "销售机构对应的店铺名", "scope": "订单", "example": "上海恒隆"},
    {"token": "order.performance_org_display", "label": "业绩机构对应的店铺名", "scope": "订单", "example": "上海恒隆"},
    {"token": "order.total_amount", "label": "销售总金额", "scope": "订单", "example": "82280.00"},
    {"token": "order.salesperson", "label": "销售人员", "scope": "订单", "example": "张三"},
    {"token": "order.total_quantity", "label": "整单件数", "scope": "订单", "example": "2"},
    {"token": "order.customer_source", "label": "顾客来源", "scope": "订单", "example": "会员推荐"},
    {"token": "order.promotion_material", "label": "助力素材", "scope": "订单", "example": "秋季画册"},
    {"token": "order.activity_type", "label": "活动类型", "scope": "订单", "example": "促销活动"},
    {"token": "order.card_type", "label": "卡类型", "scope": "订单", "example": "VIP卡"},
    {"token": "order.card_type", "label": "卡类型", "scope": "订单", "example": "金卡"},
    {"token": "order.match_reason", "label": "规则命中原因", "scope": "订单", "example": "金额命中"},
    {"token": "order.items", "label": "商品集合", "scope": "循环", "example": "{% for item in order.items %}"},
    {"token": "item.barcode", "label": "商品条码", "scope": "循环内", "example": "G123"},
    {"token": "item.style_no", "label": "款号", "scope": "循环内", "example": "S1"},
    {"token": "item.unit_price", "label": "商品单价", "scope": "循环内", "example": "93500.00"},
    {"token": "item.brand", "label": "商品品牌", "scope": "循环内", "example": "Brand-A"},
    {"token": "item.category", "label": "商品品类", "scope": "循环内", "example": "Coat"},
    {"token": "item.image_url", "label": "商品图片 URL", "scope": "循环内", "example": "http://intranet.images/1.jpg"},
    {"token": "item.image_markdown", "label": "商品图片（Markdown）", "scope": "循环内", "example": "![款号](http://intranet.images/1.jpg)"},
]

ALLOWED_VARIABLES = {item["token"] for item in REFERENCE_VARIABLES}
ALLOWED_FILTERS = {"money", "datetime"}
