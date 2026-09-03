# SQL Server 字段映射与开放模板实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 IT 通过中文业务字段到任意 SQL Server 列名的配置接入完整销售订单数据，并以一个开放的 Jinja 自定义模板渲染所有订单和商品字段。

**Architecture:** 数据源配置解析三层映射，并要求 SQL 查询将 IT 的真实列名显式别名为稳定内部键，避免动态拼接 SQL 标识符。订单模型承载新增订单级数据，模板引擎使用受限 Jinja 环境直接访问 `order` 和循环内 `item`；后台模板页仅展示变量参考、唯一自定义模板和实时预览。

**Tech Stack:** Python 3.12, Flask 内置 Jinja2, SQLAlchemy, pyodbc, pytest

---

## Planned File Structure

**Create**

- `tests/test_open_template_schema.py`: 模板变量、循环、未知变量和过滤器测试。
- `tests/test_sqlserver_field_mapping.py`: 三层映射与 SQL 别名读取测试。

**Modify**

- `datasource.example.yaml`: 给 IT 的完整映射与 `SELECT ... AS` 样例。
- `src/wecom_sales_webhook_bot/datasource_config.py`: 中文业务名转换、必填映射验证。
- `src/wecom_sales_webhook_bot/models.py`: 新增订单级字段。
- `src/wecom_sales_webhook_bot/sqlserver_source.py`: 聚合新增字段和传递内网图片 URL。
- `src/wecom_sales_webhook_bot/message_template_schema.py`: 完整公开变量参考与模板白名单。
- `src/wecom_sales_webhook_bot/message_template_defaults.py`: 唯一默认自定义模板。
- `src/wecom_sales_webhook_bot/message_template_engine.py`: 受限 Jinja 校验与渲染。
- `src/wecom_sales_webhook_bot/message_template_service.py`: 单模板持久化与完整实时预览样例。
- `src/wecom_sales_webhook_bot/message_builder.py`: 传递订单和拆分商品上下文。
- `src/wecom_sales_webhook_bot/web_app.py`: 单模板表单与预览。
- `src/wecom_sales_webhook_bot/templates/format_settings.html`: 三块模板工作区。
- `tests/test_sqlserver_config.py`, `tests/test_sqlserver_source.py`, `tests/test_message_template_engine.py`, `tests/test_message_template_service.py`, `tests/test_message_builder.py`, `tests/test_orchestrator.py`, `tests/test_web_app.py`: 回归覆盖。

### Task 1: 三层 SQL Server 映射配置

**Files:**
- Modify: `src/wecom_sales_webhook_bot/datasource_config.py`
- Modify: `datasource.example.yaml`
- Modify: `tests/test_sqlserver_config.py`
- Create: `tests/test_sqlserver_field_mapping.py`

- [ ] **Step 1: 写出失败测试**

```python
def test_three_layer_mapping_uses_chinese_business_keys_and_internal_aliases(tmp_path):
    config = load_data_source_config(_write_config(tmp_path, "销售人员: {数据库字段名: SALES_EMPLOYEE_NAME, 模板变量: order.salesperson}"))
    assert config.sqlserver.field_mapping["salesperson"] == "salesperson"
    assert config.sqlserver.database_columns["salesperson"] == "SALES_EMPLOYEE_NAME"

def test_three_layer_mapping_rejects_missing_required_business_field(tmp_path):
    with pytest.raises(ValueError, match="缺少必填字段映射: 销售单号"):
        load_data_source_config(_write_config(tmp_path, "field_mapping: {}"))
```

- [ ] **Step 2: 运行失败测试**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_sqlserver_field_mapping.py -v
```

Expected: FAIL，因为配置对象尚无 `database_columns` 和中文键规范化。

- [ ] **Step 3: 实现最小配置规范化**

在 `datasource_config.py` 定义固定表，将中文业务名映射为内部键和公开模板变量：

```python
FIELD_SPECS = {
    "销售单号": ("order_no", "order.order_no", True),
    "销售时间": ("sold_at", "order.sold_at", True),
    "门店": ("store_name", "order.store_name", True),
    "销售总金额": ("total_amount", "order.total_amount", True),
    "销售人员": ("salesperson", "order.salesperson", False),
    "整单件数": ("total_quantity", "order.total_quantity", False),
    "顾客来源": ("customer_source", "order.customer_source", False),
    "助力素材": ("promotion_material", "order.promotion_material", False),
    "卡类型": ("card_type", "order.card_type", False),
    "商品条码": ("barcode", "item.barcode", True),
    "款号": ("style_no", "item.style_no", True),
    "商品单价": ("unit_price", "item.unit_price", True),
    "商品品牌": ("brand", "item.brand", False),
    "商品品类": ("category", "item.category", False),
    "商品图片URL": ("image_url", "item.image_url", False),
}
```

新格式读取 `数据库字段名`，但运行时 `field_mapping` 的值固定为内部键；保留旧扁平内部键格式，避免现有 `datasource.local.yaml` 立刻失效。拒绝配置中与固定 `模板变量` 不一致的值。

在 `datasource.example.yaml` 给出完整 `SELECT` 约定：

```yaml
query: |
  SELECT
    [IT实际销售单列] AS order_no,
    [IT实际销售人员列] AS salesperson,
    [IT实际商品图片URL列] AS image_url
  FROM dbo.IT实际销售明细表
```

- [ ] **Step 4: 运行测试并提交**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_sqlserver_config.py tests\test_sqlserver_field_mapping.py -v
git add datasource.example.yaml src/wecom_sales_webhook_bot/datasource_config.py tests/test_sqlserver_config.py tests/test_sqlserver_field_mapping.py
git commit -m "feat: support documented SQL Server field mapping"
```

Expected: PASS；示例完整列出 IT 可配置字段。

### Task 2: 聚合新增订单字段和内网图片 URL

**Files:**
- Modify: `src/wecom_sales_webhook_bot/models.py`
- Modify: `src/wecom_sales_webhook_bot/sqlserver_source.py`
- Modify: `tests/test_sqlserver_source.py`

- [ ] **Step 1: 写出失败测试**

```python
def test_sqlserver_source_keeps_order_fields_once_and_item_image_urls():
    orders = SqlServerSalesDataSource(config, connector=fake_connector).load_orders()
    order = orders[0]
    assert order.salesperson == "张三"
    assert order.total_quantity == 2
    assert order.customer_source == "会员推荐"
    assert order.promotion_material == "秋季画册"
    assert order.card_type == "金卡"
    assert order.items[0].image_url == "http://intranet.images/1.jpg"
```

- [ ] **Step 2: 运行失败测试**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_sqlserver_source.py -v
```

Expected: FAIL，因为 `SalesOrder` 尚无新增属性。

- [ ] **Step 3: 实现模型与数据源**

```python
@dataclass(frozen=True)
class SalesOrder:
    order_no: str
    sold_at: datetime
    store_name: str
    total_amount: float
    salesperson: str | None = None
    total_quantity: int | float | str | None = None
    customer_source: str | None = None
    promotion_material: str | None = None
    card_type: str | None = None
    items: list[SalesLineItem] = field(default_factory=list)
```

`SqlServerSalesDataSource` 对每个订单级可选字段采用第一条非空值；后续非空值不一致时使用 `LOGGER.warning("conflicting order field ...")`，不覆盖首值。`image_url` 直接填入 `SalesLineItem`，不对 URL 发 HTTP 请求。

- [ ] **Step 4: 运行测试并提交**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_sqlserver_source.py tests\test_real_data_compat.py -v
git add src/wecom_sales_webhook_bot/models.py src/wecom_sales_webhook_bot/sqlserver_source.py tests/test_sqlserver_source.py
git commit -m "feat: read order-level SQL Server sales fields"
```

Expected: PASS，订单字段只出现一次、商品 URL 保持原样。

### Task 3: 受限 Jinja 开放模板变量

**Files:**
- Modify: `src/wecom_sales_webhook_bot/message_template_schema.py`
- Modify: `src/wecom_sales_webhook_bot/message_template_engine.py`
- Modify: `src/wecom_sales_webhook_bot/message_template_defaults.py`
- Modify: `tests/test_message_template_engine.py`
- Create: `tests/test_open_template_schema.py`

- [ ] **Step 1: 写出失败测试**

```python
def test_template_renders_all_order_and_split_item_variables():
    rendered = render_message_template(
        "{{ order.salesperson }} {% for item in order.items %}{{ item.style_no }} {{ item.image_url }}{% endfor %}",
        sample_context,
    )
    assert "张三" in rendered.text
    assert "JACH023ABK1" in rendered.text
    assert "http://intranet.images/1.jpg" in rendered.text

def test_template_rejects_private_attribute_and_unknown_name():
    assert "unknown variable: order.password" in validate_message_template("{{ order.password }}")
    assert "unsafe attribute: item.__class__" in validate_message_template("{{ item.__class__ }}")
```

- [ ] **Step 2: 运行失败测试**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_message_template_engine.py tests\test_open_template_schema.py -v
```

Expected: FAIL，因为旧正则引擎不支持 Jinja 循环。

- [ ] **Step 3: 实现公开 schema 和受限渲染器**

在 `message_template_schema.py` 列出全部变量：`order.order_no`、`order.sold_at`、`order.store_name`、`order.total_amount`、`order.salesperson`、`order.total_quantity`、`order.customer_source`、`order.promotion_material`、`order.card_type`、`order.match_reason`、`order.items`、`item.barcode`、`item.style_no`、`item.unit_price`、`item.brand`、`item.category`、`item.image_url`。每个参考项包含中文名、用途、范围和示例。

在 `message_template_engine.py` 使用 `jinja2.sandbox.SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)`，只注册 `money` 与 `datetime` 过滤器；解析 AST，允许 `for item in order.items`、公开属性和文字节点，拒绝导入、调用、索引私有属性、未公开名称和其他过滤器。验证错误必须保留中文变量参考和模板行号。

默认模板改为一个自定义模板，其中商品显式循环：

```jinja2
> 销售人员：{{ order.salesperson }}
{% for item in order.items %}
> 款号：{{ item.style_no }}
> 图片：{{ item.image_url }}
{% endfor %}
```

- [ ] **Step 4: 运行测试并提交**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_message_template_engine.py tests\test_open_template_schema.py -v
git add src/wecom_sales_webhook_bot/message_template_schema.py src/wecom_sales_webhook_bot/message_template_engine.py src/wecom_sales_webhook_bot/message_template_defaults.py tests/test_message_template_engine.py tests/test_open_template_schema.py
git commit -m "feat: expose split order and item template variables"
```

Expected: PASS；`items_markdown` 不再存在于公共接口。

### Task 4: 唯一自定义模板、消息构建和实时预览

**Files:**
- Modify: `src/wecom_sales_webhook_bot/message_template_service.py`
- Modify: `src/wecom_sales_webhook_bot/message_builder.py`
- Modify: `tests/test_message_template_service.py`
- Modify: `tests/test_message_builder.py`
- Modify: `tests/test_orchestrator.py`

- [ ] **Step 1: 写出失败测试**

```python
def test_preview_context_contains_every_public_field():
    context = build_preview_template_context()
    assert context["order"]["salesperson"] == "张三"
    assert context["order"]["items"][0]["image_url"] == "http://intranet.images/1.jpg"

def test_message_builder_uses_order_and_item_context_without_items_markdown():
    text = build_markdown_v2_message(order, matched_filter, {}, 8, template_body="{{ order.card_type }} {% for item in order.items %}{{ item.barcode }}{% endfor %}")
    assert "金卡" in text
    assert "GJACH023ACBK1B6420013" in text
```

- [ ] **Step 2: 运行失败测试**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_message_template_service.py tests\test_message_builder.py -v
```

Expected: FAIL，因为预览与构建上下文仍使用 `items_markdown`。

- [ ] **Step 3: 实现单模板兼容迁移与完整上下文**

`message_template_service.py` 将旧多模板 JSON 读取为当前启用模板，随后写回单对象：`{"template_body": "..."}`。`save_message_template` 不再接受模板名称、预设、激活或模板 ID。

`message_builder.py` 生成如下上下文，图片 URL 优先 SQL 数据行的 `item.image_url`：

```python
context = {
    "order": {
        "order_no": order.order_no,
        "sold_at": order.sold_at,
        "store_name": order.store_name,
        "total_amount": order.total_amount,
        "salesperson": order.salesperson or "",
        "total_quantity": order.total_quantity or "",
        "customer_source": order.customer_source or "",
        "promotion_material": order.promotion_material or "",
        "card_type": order.card_type or "",
        "match_reason": _format_reason(filter_result.reason),
        "items": [asdict(item) for item in order.items],
    }
}
```

保留字节数与图片数上限。图片数量超限时，仅将超限商品的 `image_url` 置为空；模板仍能渲染该商品其他字段。

- [ ] **Step 4: 运行测试并提交**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_message_template_service.py tests\test_message_builder.py tests\test_orchestrator.py -v
git add src/wecom_sales_webhook_bot/message_template_service.py src/wecom_sales_webhook_bot/message_builder.py tests/test_message_template_service.py tests/test_message_builder.py tests/test_orchestrator.py
git commit -m "refactor: render a single open order template"
```

Expected: PASS；保存模板、预览和实际推送使用相同上下文。

### Task 5: 收敛后台模板页为三块工作区

**Files:**
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Modify: `src/wecom_sales_webhook_bot/templates/format_settings.html`
- Modify: `tests/test_web_app.py`

- [ ] **Step 1: 写出失败测试**

```python
def test_format_page_has_only_reference_template_and_preview_sections(client):
    page = client.get("/format-settings").get_data(as_text=True)
    assert "变量参考" in page
    assert "自定义模板" in page
    assert "实时预览" in page
    assert "另存为" not in page
    assert "模板列表" not in page

def test_format_page_saves_one_template_and_renders_preview(client):
    response = client.post("/format-settings", data={"template_body": "{{ order.salesperson }}"})
    assert "模板已保存" in response.get_data(as_text=True)
    assert "张三" in response.get_data(as_text=True)
```

- [ ] **Step 2: 运行失败测试**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_web_app.py -k format -v
```

Expected: FAIL，因为现有页面仍提供多模板、预设和整块商品变量。

- [ ] **Step 3: 实现单表单页面和错误展示**

`GET /format-settings` 加载唯一模板、完整 `REFERENCE_VARIABLES` 和固定预览；`POST /format-settings` 先校验再保存，校验错误时不覆盖旧模板。模板仅渲染三个顺序区块：变量参考表、自定义模板文本框和实时预览 `<pre>`。不提供模板名称、预设、切换、删除或另存为控件。

- [ ] **Step 4: 运行测试并提交**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_web_app.py tests\test_web_text_labels.py tests\test_runtime_settings_web_app.py -v
git add src/wecom_sales_webhook_bot/web_app.py src/wecom_sales_webhook_bot/templates/format_settings.html tests/test_web_app.py
git commit -m "feat: simplify template page to open editor"
```

Expected: PASS；页面只包含用户要求的三部分。

### Task 6: SQL Server 到 webhook 端到端回归

**Files:**
- Modify: `tests/test_sqlserver_source.py`
- Modify: `tests/test_orchestrator.py`
- Modify: `tests/test_web_app.py`
- Modify: `docs/superpowers/specs/2026-08-12-sqlserver-field-mapping-and-open-template-design.md`

- [ ] **Step 1: 写出端到端回归测试**

```python
def test_sqlserver_order_uses_open_template_and_keeps_internal_image_url(tmp_path):
    sent = run_once(data_source=sql_source, sales_filter=None, image_provider=provider, state_file=tmp_path / "state.json", webhook_client=client, max_images=8, dry_run=False, template_body="{{ order.salesperson }} {% for item in order.items %}{{ item.image_url }}{% endfor %}", database_rule_groups=[matching_group])
    assert sent == ["SO-1001"]
    assert "张三" in client.messages[0]
    assert "http://intranet.images/1.jpg" in client.messages[0]
```

- [ ] **Step 2: 运行测试并修复单点失败**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_sqlserver_config.py tests\test_sqlserver_source.py tests\test_message_template_engine.py tests\test_message_template_service.py tests\test_message_builder.py tests\test_orchestrator.py tests\test_web_app.py tests\test_web_text_labels.py -v
```

Expected: PASS。任何失败仅修复对应任务涉及的根因，不能绕过断言或恢复 `items_markdown`。

- [ ] **Step 3: 本机后台冒烟与提交**

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -u -m wecom_sales_webhook_bot.cli run-server --config config.sqlserver.local.yaml
```

验证 `http://127.0.0.1:5000/format-settings`：变量参考有所有 17 项、保存的自定义模板刷新后不丢失、实时预览展示订单字段和循环内两条商品。停止测试服务后：

```powershell
git add tests/test_sqlserver_source.py tests/test_orchestrator.py tests/test_web_app.py docs/superpowers/specs/2026-08-12-sqlserver-field-mapping-and-open-template-design.md
git commit -m "test: cover SQL Server open template delivery"
```

## Self-Review

- Spec coverage: 三层映射在 Task 1；新增订单字段和内网 URL 在 Task 2；完整拆分变量和循环在 Task 3；单模板、实时预览和推送上下文在 Task 4；网页三块工作区在 Task 5；真实数据到 webhook 请求回归在 Task 6。
- Placeholder scan: 所有任务都有文件、失败测试、命令、实现边界和预期结果；无 TBD 或后续补充步骤。
- Type consistency: 配置内部键、`SalesOrder` 属性和公开 `order.*` 变量名称在全部任务中保持一致。
