from __future__ import annotations

STANDARD_TEMPLATE = """# 销售晒单
> 销售单号：{{ order.order_no }}
> 门店：{{ order.store_name }}
> 业绩机构：{{ order.performance_org }}
> 销售机构对应的店铺名：{{ order.store_name_display }}
> 业绩机构对应的店铺名：{{ order.performance_org_display }}
> 销售时间：{{ order.sold_at | datetime }}
> 销售总金额：{{ order.total_amount | money }}
> 销售人员：{{ order.salesperson }}
> 整单件数：{{ order.total_quantity }}
> 顾客来源：{{ order.customer_source }}
> 助力素材：{{ order.promotion_material }}
> 活动类型：{{ order.activity_type }}
> 卡类型：{{ order.card_type }}
> 命中原因：{{ order.match_reason }}

{% for item in order.items %}
> 款号：{{ item.style_no }}
> 条码：{{ item.barcode }}
> 单价：{{ item.unit_price | money }}
> 品牌：{{ item.brand }}
> 品类：{{ item.category }}
{{ item.image_markdown }}
{% endfor %}
"""

PRESET_TEMPLATES = {"standard": {"label": "自定义模板", "body": STANDARD_TEMPLATE}}
