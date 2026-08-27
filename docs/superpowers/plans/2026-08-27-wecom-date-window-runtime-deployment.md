# 企业微信机器人日期窗口、推送时段与 Windows 服务 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让网页规则支持订单日期范围、运行配置统一控制每日推送时段并自动补推，同时交付适用于内网 Windows Server 的双 NSSM 服务部署物。

**Architecture:** 日期范围作为规则的强制闸门，与业务条件始终取交集；每日时段作为全局运行控制，只阻止 webhook 发送且保留待推订单。扫描器仅按已成功推送状态去重，网页由 Waitress 承载，扫描和网页由独立 NSSM 服务守护。

**Tech Stack:** Python 3.12、Flask、SQLAlchemy、PyYAML、Waitress、PowerShell、NSSM、pytest。

---

## 文件职责

- `src/wecom_sales_webhook_bot/rule_service.py`：解析、验证并执行订单日期强制闸门；接收服务启动日作为空日期范围的默认下限。
- `src/wecom_sales_webhook_bot/runtime_settings.py`：保存每日推送时段，提供时段判断函数。
- `src/wecom_sales_webhook_bot/orchestrator.py`：全天扫描、时段外保留待推、成功才去重。
- `src/wecom_sales_webhook_bot/web_app.py`：日期表单、运行配置表单、格式校验和规则持久化。
- `src/wecom_sales_webhook_bot/templates/rule_edit.html`：所有筛选项的格式说明与示例。
- `src/wecom_sales_webhook_bot/templates/runtime_settings.html`：每日推送时段说明和输入框。
- `src/wecom_sales_webhook_bot/cli.py`、`pyproject.toml`：Waitress 生产网页入口与依赖。
- `scripts/deployment/*.ps1`、`docs/deployment/windows-server-it-handoff-zh.md`：Windows Server 服务安装、检查、更新与交接。

### Task 1: 订单日期范围的规则语义

**Files:**
- Modify: `src/wecom_sales_webhook_bot/rule_service.py`
- Modify: `src/wecom_sales_webhook_bot/runtime_settings.py`
- Test: `tests/test_rule_service.py`
- Test: `tests/test_runtime_settings.py`

- [ ] **Step 1: 写出日期范围强制闸门的失败测试**

```python
from datetime import date, datetime

RuleConditionDTO(field_name="sold_at", operator="date_range", value=["2026-08-24", "2026-08-31"])
assert evaluate_rule_group(order_on_2026_08_24, group) is True
assert evaluate_rule_group(order_on_2026_09_01, group) is False

assert matches_order_date_range(order_on_2026_08_24, date(2026, 8, 24), None) is True
assert matches_order_date_range(order_on_2026_08_23, date(2026, 8, 24), None) is False
```

另加 `any` 规则组测试：业务条件命中但日期不在范围内时必须为 `False`。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/test_rule_service.py tests/test_runtime_settings.py -q`

Expected: FAIL，因为 `date_range` 与日期闸门函数尚不存在。

- [ ] **Step 3: 实现最小日期范围语义**

在 `rule_service.py` 新增：

```python
def matches_order_date_range(order, start_date: date | None, end_date: date | None) -> bool:
    order_date = order.sold_at.date()
    return ((start_date is None or order_date >= start_date)
            and (end_date is None or order_date <= end_date))
```

将 `sold_at/date_range` 从普通 `any/all` 条件中分离；先取出日期条件并调用 `matches_order_date_range`，日期不匹配立即返回 `False`，再对其余条件执行原有匹配模式。`evaluate_rule_group` 新增可选参数 `default_start_date: date | None`：范围开始为空时使用它；范围结束为空时不限。旧规则没有日期条件时也使用该默认下限，防止服务首次部署推送历史订单。`runtime_settings.py` 解析 `date_range` 为两个允许为空的字符串。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_rule_service.py tests/test_runtime_settings.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/wecom_sales_webhook_bot/rule_service.py src/wecom_sales_webhook_bot/runtime_settings.py tests/test_rule_service.py tests/test_runtime_settings.py
git commit -m "feat: add order date range rules"
```

### Task 2: 每日推送时段运行配置

**Files:**
- Modify: `src/wecom_sales_webhook_bot/runtime_settings.py`
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Modify: `src/wecom_sales_webhook_bot/templates/runtime_settings.html`
- Test: `tests/test_runtime_settings.py`
- Test: `tests/test_runtime_settings_web_app.py`

- [ ] **Step 1: 写出失败测试**

```python
controls = RuntimeControls(1200, 8, 10, "10:00", "22:00")
assert is_within_push_window(datetime(2026, 8, 27, 10, 0), controls) is True
assert is_within_push_window(datetime(2026, 8, 27, 22, 1), controls) is False
```

网页测试提交 `push_window_start=09:30`、`push_window_end=21:00`，断言数据库 JSON 和重新渲染的输入值；再提交 `22:00/10:00`，断言中文错误提示且不保存。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/test_runtime_settings.py tests/test_runtime_settings_web_app.py -q`

Expected: FAIL，因为新字段与 `is_within_push_window` 尚不存在。

- [ ] **Step 3: 实现配置和校验**

扩展 `RuntimeControls`：

```python
push_window_start: str = "10:00"
push_window_end: str = "22:00"
```

在 `_normalize_runtime_controls` 使用 `%H:%M` 严格解析；要求 `start < end`，否则抛出 `ValueError("每日推送开始时间必须早于结束时间")`。新增：

```python
def is_within_push_window(now: datetime, controls: RuntimeControls) -> bool:
    return parse_time(controls.push_window_start) <= now.time() <= parse_time(controls.push_window_end)
```

网页新增两个 `type="time"` 字段、`HH:MM` 格式说明、`10:00–22:00` 默认值和“时段外继续扫描，进入时段自动补推”提示。所有表单回显和保存调用传递两个字段。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_runtime_settings.py tests/test_runtime_settings_web_app.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/wecom_sales_webhook_bot/runtime_settings.py src/wecom_sales_webhook_bot/web_app.py src/wecom_sales_webhook_bot/templates/runtime_settings.html tests/test_runtime_settings.py tests/test_runtime_settings_web_app.py
git commit -m "feat: configure daily push window"
```

### Task 3: 新建规则页面与日期范围持久化

**Files:**
- Modify: `src/wecom_sales_webhook_bot/web_app.py`
- Modify: `src/wecom_sales_webhook_bot/templates/rule_edit.html`
- Test: `tests/test_web_app.py`
- Test: `tests/test_web_text_labels.py`

- [ ] **Step 1: 写出失败测试**

新增页面断言，检查金额、款号、门店、品牌、品类、订单开始日期、订单结束日期均有格式说明或示例；提交仅开始日期、仅结束日期、完整范围以及两端为空均能保存 `sold_at/date_range`。两端为空时断言保存值为 `,`，表示使用服务启动当天作为默认下限。提交 `2026-08-31` 至 `2026-08-01` 必须返回“结束日期不能早于开始日期”。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/test_web_app.py tests/test_web_text_labels.py -q`

Expected: FAIL，因为日期字段和说明不存在。

- [ ] **Step 3: 实现网页表单与持久化**

删除 `time_start/time_end` 字段、旧 `between_time` 校验和保存分支。新增 `order_date_start/order_date_end`，以 `datetime.strptime(value, "%Y-%m-%d")` 校验。无论日期是否填写，都保存：

```python
add_condition("sold_at", "date_range", f"{start},{end}")
```


两端为空即保存 `,`，由扫描服务本次启动时固定的日期提供默认下限。
模板中为每项加入紧邻输入框的 `.hint`：金额“仅数字，例如 10000”；多值字段“英文逗号分隔，例如 G621,G622”；日期“YYYY-MM-DD，例如 2026-08-24；可留空”。页面不再出现“每日推送时段”。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_web_app.py tests/test_web_text_labels.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/wecom_sales_webhook_bot/web_app.py src/wecom_sales_webhook_bot/templates/rule_edit.html tests/test_web_app.py tests/test_web_text_labels.py
git commit -m "feat: add rule date range form"
```

### Task 4: 全天扫描与时段补推

**Files:**
- Modify: `src/wecom_sales_webhook_bot/orchestrator.py`
- Modify: `src/wecom_sales_webhook_bot/cli.py`
- Test: `tests/test_orchestrator.py`

- [ ] **Step 1: 写出失败测试**

向 `run_once` 注入固定 `now_func`、`service_started_at` 和带 `10:00–22:00` 的运行配置。断言 `09:00` 命中订单不发送、状态文件不包含单号；再以 `10:00` 调用同一状态文件，断言发送一次。另加断言：日期两端空的规则使用 `service_started_at.date()`，状态文件的旧 `last_scan_at` 不会导致未推送订单被跳过。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/test_orchestrator.py -q`

Expected: FAIL，因为扫描器目前无时段判断且按 `last_scan_at` 跳过订单。

- [ ] **Step 3: 实现补推链路**

给 `run_once` 新增 `runtime_controls`、`service_started_at`、`now_func=datetime.now` 参数。CLI 在进入 `run-once` 或 `schedule` 后立即记录一次 `service_started_at = datetime.now()`；`schedule` 的所有循环复用该值，重启服务才重新计算。将该日期传给 `evaluate_rule_group`。移除：

```python
if last_scan_at and order.sold_at <= last_scan_at:
    continue
```

先筛选所有尚未成功推送且规则命中的订单；如果 `not is_within_push_window(now_func(), runtime_controls)`，返回空列表且不调用 `mark_pushed`。仅 webhook 成功后调用 `mark_pushed`。CLI 的 `run-once` 与 `schedule` 均传入已加载的 `runtime_controls`；`schedule` 每轮重新读取运行配置。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_orchestrator.py tests/test_rule_service.py tests/test_runtime_settings.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/wecom_sales_webhook_bot/orchestrator.py src/wecom_sales_webhook_bot/cli.py tests/test_orchestrator.py
git commit -m "feat: defer pushes outside daily window"
```

### Task 5: Waitress 与 Windows Server 部署物

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/wecom_sales_webhook_bot/cli.py`
- Create: `scripts/deployment/start-web.ps1`
- Create: `scripts/deployment/start-scheduler.ps1`
- Create: `scripts/deployment/install-services.ps1`
- Create: `scripts/deployment/uninstall-services.ps1`
- Create: `scripts/deployment/test-deployment.ps1`
- Create: `docs/deployment/windows-server-it-handoff-zh.md`
- Test: `tests/test_cli.py`（新建，如缺失）

- [ ] **Step 1: 写出失败测试**

为网页启动路径抽取 `serve_web_app(app, host, port)`，测试以 stub `waitress.serve` 断言 host、port 与 Flask app 被传入；断言 CLI `run-server` 不调用 `app.run`。

- [ ] **Step 2: 运行失败测试**

Run: `python -m pytest tests/test_cli.py -q`

Expected: FAIL，因为生产 WSGI 启动函数不存在。

- [ ] **Step 3: 以 Waitress 替换 Flask 开发服务器**

在依赖中加入 `waitress>=3.0.0`；在 `cli.py` 定义：

```python
def serve_web_app(app, host: str, port: int) -> None:
    from waitress import serve
    serve(app, host=host, port=port)
```

`run-server` 分支调用该函数。禁止在服务器配置中使用 `0.0.0.0`；若配置值为该地址，抛出含“内网 IP”的 `ValueError`。

- [ ] **Step 4: 添加部署脚本与交接文档**

脚本参数必须显式接收 `AppRoot`、`ConfigPath`、`PythonExe`、`NssmExe`、`ServiceAccount`、`ServicePassword` 和 `LogDirectory`；不在脚本中硬编码密钥。`start-web.ps1` 执行 `run-server`，`start-scheduler.ps1` 执行 `schedule`，均设置 `PYTHONPATH=<AppRoot>\src` 并追加 UTF-8 日志。安装脚本注册 `WeComSalesBotWeb` 与 `WeComSalesBotScheduler`、设置自动启动和退出后重启；卸载脚本先停止再删除；检测脚本只检查文件、端口、HTTP `/login` 和服务状态，绝不运行 `run-once`。

交接文档必须列出：本机账号 `./svc-wecom-bot`、销售 SQL Server 仅 `SELECT` 和拒绝写权限、机器人后台业务库独立读写、ODBC Driver、NSSM、内网防火墙、配置更新后何时重启扫描服务、备份/更新/回滚和验收清单。

- [ ] **Step 5: 运行测试与 PowerShell 语法检查**

Run:

```powershell
python -m pytest tests/test_cli.py -q
Get-ChildItem scripts/deployment/*.ps1 | ForEach-Object { [void][scriptblock]::Create((Get-Content -Raw $_)) }
```

Expected: PASS，所有脚本可解析。

- [ ] **Step 6: 完整回归与提交**

Run: `python -m pytest -q`

Expected: PASS。

```powershell
git add pyproject.toml src/wecom_sales_webhook_bot/cli.py scripts/deployment docs/deployment tests/test_cli.py
git commit -m "feat: add Windows service deployment"
```

## 计划自检

- 覆盖设计的 SQL Server 只读边界：Task 5 IT 交接明确最小权限；程序不执行销售数据写操作。
- 覆盖订单日期范围、服务启动日默认下限、时段补推和避免 `last_scan_at` 漏单：Tasks 1、3、4。
- 覆盖网页每项填写说明及运行配置默认时段：Tasks 2、3。
- 覆盖双服务、Waitress、NSSM、内网限制和验证：Task 5。
- 计划中无 TBD/TODO/待定占位项，且函数、字段名在前置任务中已定义。



