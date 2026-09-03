from __future__ import annotations

STANDARD_TEMPLATE = """# 销售晒单
> 销售单号：{{ order.order_no }}
> 门店：{{ order.store_name }}
> 销售时间：{{ order.sold_at | datetime }}
> 销售总金额：{{ order.total_amount | money }}
> 销售人员：{{ order.salesperson }}
> 整单件数：{{ order.total_quantity }}
> 顾客来源：{{ order.customer_source }}
> 助力素材：{{ order.promotion_material }}
> 卡类型：{{ order.card_type }}
> 命中原因：{{ order.match_reason }}

{% for item in order.items %}
> 款号：{{ item.style_no }}
> 条码：{{ item.barcode }}
> 单价：{{ item.unit_price | money }}
> 品牌：{{ item.brand }}
> 品类：{{ item.category }}
> 图片：{{ item.image_url }}
{% endfor %}
"""

PRESET_TEMPLATES = {"standard": {"label": "自定义模板", "body": STANDARD_TEMPLATE}}
