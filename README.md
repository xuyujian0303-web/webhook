# 企业微信销售单 Webhook 推送机器人

这是一个 Python 项目：从 EMS 只读 TCP 服务（也兼容 SQL Server 和 CSV）读取销售订单，按后台规则筛选，使用可编辑的 Jinja 模板生成企业微信 `markdown_v2` 消息，并通过 Webhook 推送。

## 本机桌面版（推荐）

不再需要浏览器。复制本地配置后运行：

```powershell
cd C:\Users\redstone\webhook
$env:PYTHONPATH = "src"
python -m wecom_sales_webhook_bot.cli desktop-gui --config config.local.yaml
```

也可运行 `deployment\START_DESKTOP_GUI.ps1`。桌面窗口可保存运行参数、启动/停止扫描、维护多个 Webhook 地址和编辑规则。

## 灵活规则与多 Webhook

- 每条规则同时使用两个条件组：**全部满足（AND）**的每项都必须命中；填写了**任一满足（OR）**时至少命中其中一项；两个条件组之间仍是 AND。
- 桌面规则编辑器可选择 EMS 销售详单的所有字段，包括销售机构、业绩机构、金额、产品、顾客、卡、活动和创建时间等。销售机构与业绩机构是两个独立字段。
- `wecom.webhook_urls` 支持多个企业微信群机器人地址。每条消息会发送到全部地址；任一地址失败时订单不会标记为已推送，下一轮会补发。

## 功能

- EMS 只读 TCP 销售数据源，支持定时扫描、订单去重和企业微信推送
- SQL Server 销售数据源，IT 可配置中文业务名到真实列名的映射
- CSV 数据源，便于本地开发和回归测试
- 订单金额、门店、款号、品牌、品类、订单日期范围规则
- 每日推送时段（默认 `10:00–22:00`）；时段外继续扫描，允许时段自动补推
- 后台网页：规则、模板、运行配置、手动测试、推送记录、系统状态
- 自定义 Jinja 模板、完整变量参考和实时预览
- 商品图片 URL 直接使用 SQL Server 返回的内网地址
- 推送成功后才记录去重状态，失败订单可重试
- Windows Server NSSM 双服务部署脚本

## 安全边界

不要把真实 Webhook、数据库密码、管理员密码、Token、生产 CSV、图片或运行状态提交到 Git。仓库中的配置均为示例，占位符不会产生真实推送。销售 SQL Server 账号必须只有 `SELECT` 权限；机器人后台业务库是独立数据库，才允许读写账号、规则、模板、运行配置和推送记录。

## 目录结构

```text
src/wecom_sales_webhook_bot/       程序源码
  cli.py                            run-server / schedule / run-once 等入口
  ems_client.py                     EMS 认证、初始化及只读销售查询
  ems_decoder.py                    EMS TLV/RDS 销售明细解码
  ems_source.py                     EMS 数据源适配器
  sqlserver_source.py               SQL Server 只读数据源
  datasource_config.py              IT 字段映射配置
  orchestrator.py                   扫描、规则、推送、去重
  web_app.py                        Flask 后台网页
  templates/                        网页模板
tests/                              自动化测试
scripts/deployment/                 Windows NSSM 启动、安装、卸载、检测脚本
scripts/init_local_sqlserver.ps1    本地 SQL Server 测试库初始化
scripts/import_sales_csv_to_sqlserver.ps1
config.example.yaml                 CSV/通用示例配置
datasource.example.yaml              SQL Server 映射示例
docs/deployment/                    IT 部署交接文档
```

## MacBook 快速开始

要求：Python 3.12、SQL Server ODBC Driver 17/18（连接真实 SQL Server 时）、可访问企业微信 Webhook 的网络。

```bash
git clone https://github.com/xuyujian0303-web/webhook.git
cd webhook
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp config.example.yaml config.local.yaml
```

编辑 `config.local.yaml`：

- `wecom.webhook_url` 填企业微信机器人地址
- `runtime.dry_run` 测试时保持 `true`，确认后才改为 `false`
- `backend.database_url` 填机器人后台业务库
- 使用 EMS 时，将 `data_source.kind` 设为 `ems`，并将 `data_source.config_path` 指向本地 `ems_config.json`；该文件含账号密码，不能提交 Git
- 若使用 SQL Server，将 `data_source.kind` 设为 `sqlserver`，并把 `data_source.config_path` 指向复制后的数据源配置
- 商品图片是内网 URL 时，不需要启动 `serve-images`

启动后台网页：

```bash
export PYTHONPATH=src
python -u -m wecom_sales_webhook_bot.cli run-server --config config.local.yaml
```

浏览器打开 `http://127.0.0.1:5000/login`。默认账号只在首次初始化后台库时创建，生产环境请立即修改密码。

启动持续扫描（另开终端）：

```bash
cd webhook
source .venv/bin/activate
export PYTHONPATH=src
python -u -m wecom_sales_webhook_bot.cli schedule --config config.local.yaml
```

单轮安全测试：

```bash
python -u -m wecom_sales_webhook_bot.cli run-once --config config.local.yaml
```

生产真实推送前必须确认规则、日期范围、每日推送时段、Webhook 返回 `errcode=0`，并检查去重状态目录。

`schedule` 每个扫描周期都会向 EMS 查询“上次扫描时间至当前时间”的订单；同一批订单与已成功推送的订单都会按销售单号去重，随后才使用网页后台保存的规则、模板和运行配置进行推送。

当后台只有一条“全部满足”规则时，金额阈值和门店列表会在 EMS 响应解码后立即过滤；日期范围会直接作为 EMS 查询日期参数。EMS 当前已验证的查询协议只公开日期参数，金额和门店暂不拼入未经确认的二进制请求字段，避免查询结果被错误截断。多条规则或“任一满足”规则仍由后台统一判断。

## SQL Server 配置

复制 `datasource.example.yaml` 为本地文件，例如 `datasource.local.yaml`。IT 只修改方括号中的真实列名、表名和连接字符串；`AS order_no` 等内部别名不可修改。销售数据库账号只需要查询权限。

```yaml
sqlserver:
  connection_string: Driver={ODBC Driver 18 for SQL Server};Server=sqlserver-host;Database=sales_db;Trusted_Connection=yes;TrustServerCertificate=yes;
  query: |
    SELECT [真实销售单号列] AS order_no,
           [真实销售时间列] AS sold_at,
           [真实门店列] AS store_name,
           [真实整单金额列] AS total_amount,
           [真实商品条码列] AS barcode,
           [真实款号列] AS style_no,
           [真实单价列] AS unit_price,
           [真实商品图片URL列] AS image_url
    FROM dbo.sales_lines
    ORDER BY sold_at ASC, order_no ASC
```

订单级字段（销售人员、整单件数、顾客来源、助力素材、卡类型）和商品级字段都在示例映射中列出，模板变量保持稳定，例如 `order.salesperson`、`item.image_url`。

## 网页配置说明

- 新建规则：金额、门店、款号、品牌、品类及订单开始/结束日期；页面每项都有格式和示例
- 订单日期两端都留空：默认从本次扫描服务启动当天 `00:00:00` 开始，结束日期不限
- 运行配置：扫描周期、单条消息图片数、消息间隔、每日推送开始/结束时间；默认 `10:00–22:00`
- 模板页面只保留“变量参考、自定义模板、实时预览”，商品字段必须在 `{% for item in order.items %}` 循环中逐项输出
- 网页保存规则、模板和运行配置后，扫描服务下一周期自动读取；修改 `datasource.local.yaml` 后需重启扫描服务

## Windows Server 部署

正式部署建议使用 Python + Waitress + NSSM，而不是先打包 EXE。网页和扫描分别注册为 `WeComSalesBotWeb`、`WeComSalesBotScheduler` 两个自动恢复服务，后台只开放公司内网。

详细步骤见 [`docs/deployment/windows-server-it-handoff-zh.md`](docs/deployment/windows-server-it-handoff-zh.md)。管理员 PowerShell 示例：

```powershell
.\scripts\deployment\install-services.ps1 `
  -NssmExe C:\Tools\nssm\win64\nssm.exe `
  -AppRoot C:\WeComSalesBot\app `
  -PythonExe C:\Python312\python.exe `
  -ConfigPath C:\WeComSalesBot\config\config.sqlserver.local.yaml `
  -ServiceAccount .\svc-wecom-bot `
  -ServicePassword '<密码>' `
  -LogDirectory C:\WeComSalesBot\logs
```

销售 SQL Server 仅授予 `SELECT`；机器人后台业务库独立读写。Windows 防火墙只允许内网网段访问网页端口。

## 测试

```bash
export PYTHONPATH=src
python -m pytest -q
```

测试不会自动执行真实 SQL Server 全量推送。建议上线前依次验证：网页登录、模板预览、规则保存、日期范围拦截、时段外不推送且时段开始后补推、Webhook 成功状态、NSSM 重启恢复。

## 更新与回滚

更新前备份配置目录、后台业务数据库和推送状态文件；停止网页和扫描服务，替换代码并重新安装依赖，验证后先启动网页再启动扫描。不要覆盖推送状态文件，否则可能重复推送历史订单。回滚时恢复上一版代码，保留当前配置和状态文件。

## CLI 命令

```text
run-server   启动后台网页
schedule     持续扫描
run-once     扫描一轮
serve-images 启动本地图片服务（SQL Server 已返回内网图片 URL 时不需要）
clear-state  清空去重状态（执行前必须人工确认）
```
