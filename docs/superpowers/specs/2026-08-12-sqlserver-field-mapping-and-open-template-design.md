# SQL Server 字段映射与开放模板设计

## 目标

将 SQL Server 数据源的真实列名与业务语义解耦，使 IT 可以在配置文件中维护中文或英文的数据库列名，业务方则在唯一的自定义消息模板中使用稳定变量。销售订单新增销售人员、整单件数、顾客来源、助力素材和卡类型五项订单级信息。商品图片直接使用 SQL Server 返回的内网 URL。

本设计不改变当前规则匹配语义。规则继续由既有数据库规则管理。

## 配置文件

`datasource.local.yaml` 的 `field_mapping` 采用三层映射。左侧中文业务名是固定说明，`数据库字段名` 是 IT 唯一需要维护的值，`模板变量` 是程序固定公开接口，不由 IT 修改。

```yaml
field_mapping:
  销售单号:
    数据库字段名: 请填写实际列名
    模板变量: order.order_no
  销售时间:
    数据库字段名: 请填写实际列名
    模板变量: order.sold_at
  门店:
    数据库字段名: 请填写实际列名
    模板变量: order.store_name
  销售总金额:
    数据库字段名: 请填写实际列名
    模板变量: order.total_amount
  销售人员:
    数据库字段名: 请填写实际列名
    模板变量: order.salesperson
  整单件数:
    数据库字段名: 请填写实际列名
    模板变量: order.total_quantity
  顾客来源:
    数据库字段名: 请填写实际列名
    模板变量: order.customer_source
  助力素材:
    数据库字段名: 请填写实际列名
    模板变量: order.promotion_material
  卡类型:
    数据库字段名: 请填写实际列名
    模板变量: order.card_type
  商品条码:
    数据库字段名: 请填写实际列名
    模板变量: item.barcode
  款号:
    数据库字段名: 请填写实际列名
    模板变量: item.style_no
  商品单价:
    数据库字段名: 请填写实际列名
    模板变量: item.unit_price
  商品品牌:
    数据库字段名: 请填写实际列名
    模板变量: item.brand
  商品品类:
    数据库字段名: 请填写实际列名
    模板变量: item.category
  商品图片URL:
    数据库字段名: 请填写实际列名
    模板变量: item.image_url
```

数据库字段名可以是中文或英文。SQL 查询必须把对应的实际列以程序所需别名返回，或数据源根据映射读取结果列。`模板变量` 由程序校验为固定变量，防止配置意外改变公共接口。

过渡期支持旧版扁平英文键映射；新格式一旦使用，必须包含所有必填业务字段。可选字段缺失时在模板中渲染为空字符串，不导致整张订单失败。

## 数据模型与读取

`SalesOrder` 增加五个可选订单级字段：`salesperson`、`total_quantity`、`customer_source`、`promotion_material`、`card_type`。同一订单的多条商品明细中这些字段应一致；数据源采用该订单第一条非空值，并在出现冲突时写警告日志。

`SalesLineItem` 继续只保留商品级字段：`barcode`、`style_no`、`unit_price`、`brand`、`category`、`image_url`。`image_url` 是 SQL Server 返回的内网 URL，消息模板直接使用它，不要求本地图片服务或图片映射 CSV。

## 自定义模板页

后台 `/format-settings` 收敛为一个唯一启用的自定义模板，不提供预设、另存为、多模板切换或删除。

页面只保留三个区域：

1. 变量参考：完整列出中文业务名、模板变量、类型、是否订单级、说明和示例。
2. 自定义模板：一个编辑框和保存操作。保存前校验 Jinja 语法与变量白名单。
3. 实时预览：使用固定示例订单和两条示例商品渲染模板，直接展示渲染结果或模板错误。

商品变量全部拆开，移除作为主要接口的 `items_markdown`。模板通过 Jinja 循环自行排版：

```jinja2
> 销售单号：{{ order.order_no }}
> 门店：{{ order.store_name }}
> 销售人员：{{ order.salesperson }}
> 整单件数：{{ order.total_quantity }}
> 顾客来源：{{ order.customer_source }}
> 助力素材：{{ order.promotion_material }}
> 卡类型：{{ order.card_type }}
> 销售总金额：{{ order.total_amount | money }}

{% for item in order.items %}
> 款号：{{ item.style_no }}
> 条码：{{ item.barcode }}
> 单价：{{ item.unit_price | money }}
> 品牌：{{ item.brand }}
> 品类：{{ item.category }}
> 图片：{{ item.image_url }}
{% endfor %}
```

公开模板变量：

| 中文名称 | 模板变量 | 类型 | 范围 |
| --- | --- | --- | --- |
| 销售单号 | `order.order_no` | 文本 | 订单 |
| 销售时间 | `order.sold_at` | 时间 | 订单 |
| 门店 | `order.store_name` | 文本 | 订单 |
| 销售总金额 | `order.total_amount` | 数值 | 订单 |
| 销售人员 | `order.salesperson` | 文本 | 订单 |
| 整单件数 | `order.total_quantity` | 数值或文本 | 订单 |
| 顾客来源 | `order.customer_source` | 文本 | 订单 |
| 助力素材 | `order.promotion_material` | 文本 | 订单 |
| 卡类型 | `order.card_type` | 文本 | 订单 |
| 规则命中原因 | `order.match_reason` | 文本 | 订单 |
| 商品集合 | `order.items` | 列表 | 循环 |
| 商品条码 | `item.barcode` | 文本 | 循环内 |
| 款号 | `item.style_no` | 文本 | 循环内 |
| 商品单价 | `item.unit_price` | 数值 | 循环内 |
| 商品品牌 | `item.brand` | 文本 | 循环内 |
| 商品品类 | `item.category` | 文本 | 循环内 |
| 商品图片 URL | `item.image_url` | URL | 循环内 |

允许过滤器：`money` 和 `datetime`。页面会提示使用 `{% for item in order.items %}` 与 `{% endfor %}` 包裹商品变量。内网 URL 的可访问性由企业微信客户端所在网络决定；页面仅验证 URL 是否存在，不主动请求内网图床。

## 推送链路

SQL Server -> 映射解析 -> `SalesOrder` / `SalesLineItem` -> 数据库规则 -> 唯一启用模板 -> Jinja 渲染 -> `markdown_v2` webhook。

消息构建器不再在开放模板模式下自动拼接商品明细。保留消息长度与每单图片数限制；达到限制时记录明确日志，避免发送半截且无法定位原因的消息。

## 错误处理

- 缺少必填映射、映射列不存在、字段类型无法解析：扫描开始前报告中文业务名和实际列名，且不推进去重状态。
- 新增订单字段为空：模板渲染为空，不阻断推送。
- 同一订单订单级字段不一致：首个非空值胜出并记录警告。
- 模板 Jinja 语法错误或引用未公开变量：后台保存失败并指出变量或行号；保留旧模板继续作为运行模板。
- 内网图片 URL 为空或不符合 URL 格式：该商品图片字段为空，订单其余内容仍可推送。

## 测试

- 三层映射解析：中文列名、英文列名、缺失映射、未知实际列名。
- SQL Server 数据源：新增订单字段聚合、订单内冲突、图片 URL 传递。
- 消息模板：所有订单变量、所有拆分商品变量、循环、`money`、`datetime`、未知变量与语法错误。
- 后台页面：三块区域存在、唯一模板保存、实时预览、变量参考完整。
- 编排回归：SQL Server 数据经规则匹配后以唯一自定义模板渲染，真实图片 URL 保留到 webhook 请求。
