# AGENTS.md

## 项目定位

这是一个企业微信销售晒单推送项目，当前目标是形成两部分：

1. 一个可持续运行的扫描/推送进程
2. 一个可配置规则、模板和运行参数的后台管理网页

当前项目已经支持：

- 企业微信 `markdown_v2` 推送
- CSV 数据源
- SQL Server 数据源
- 本地图片目录 / 图片映射 CSV / 公网图片 URL
- 后台网页中的规则管理、模板管理、运行配置、手动测试、推送记录、系统状态

## 当前工作目录

项目根目录：

`C:\Users\x\wecom-sales-webhook-bot\.worktrees\wecom-bot-impl`

交接文档优先阅读：

`docs/superpowers/plans/2026-05-30-wecom-sales-webhook-bot-handoff-zh.md`

## 用户偏好

- 全程中文
- 直接执行，不先空讲大方案
- 给出可直接复制的 PowerShell 命令
- 优先保证可测试、可部署、可交接给 IT
- 不要擅自删除本地测试文件、配置文件、`var/`、`tmp/` 等用户可能仍在使用的内容

## 正确 CLI 命令

入口模块：

`python -m wecom_sales_webhook_bot.cli`

当前支持的命令只有：

- `run-server`
- `schedule`
- `run-once`
- `serve-images`
- `clear-state`

注意：

- 不要使用 `run-admin`
- 后台网页启动命令是 `run-server`

## 本地运行环境

进入项目目录后，先设置：

```powershell
$env:PYTHONPATH="src"
```

当前用户机器上的 Python 解释器通常使用：

```powershell
"C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe"
```

## 常用启动命令

### 1. 启动后台网页

```powershell
cd C:\Users\x\wecom-sales-webhook-bot\.worktrees\wecom-bot-impl
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -u -m wecom_sales_webhook_bot.cli run-server --config config.sqlserver.local.yaml
```

### 2. 启动持续扫描进程

```powershell
cd C:\Users\x\wecom-sales-webhook-bot\.worktrees\wecom-bot-impl
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -u -m wecom_sales_webhook_bot.cli schedule --config config.sqlserver.local.yaml
```

### 3. 手动执行一轮扫描

```powershell
cd C:\Users\x\wecom-sales-webhook-bot\.worktrees\wecom-bot-impl
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -u -m wecom_sales_webhook_bot.cli run-once --config config.sqlserver.local.yaml
```

### 4. 启动本地图片服务

```powershell
cd C:\Users\x\wecom-sales-webhook-bot\.worktrees\wecom-bot-impl
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -u -m wecom_sales_webhook_bot.cli serve-images --config config.sqlserver.local.yaml
```

## 配置文件约定

当前仓库里可能同时存在多份配置文件，例如：

- `config.yaml`
- `config.real-test.yaml`
- `config.sqlserver.local.yaml`
- `config.sqlserver.local.5055.yaml`
- `datasource.local.yaml`
- `datasource.example.yaml`

约定：

- 做 SQL Server 本地测试时，优先看 `config.sqlserver.local.yaml`
- 需要确认数据源连接细节时，同时查看 `data_source.config_path` 指向的配置文件
- 不要假设当前使用的是 CSV；先看配置

## 当前实现重点

### 数据源

- 已支持 CSV 和 SQL Server
- 当前项目方向以 SQL Server 为主，CSV 更偏原型/兼容测试

### 推送

- 企业微信使用 `markdown_v2`
- webhook 仅在返回 `errcode == 0` 时记为成功
- 已支持串行限流发送
- 运行配置里已有：
  - `scan_interval_seconds`
  - `max_images_per_message`
  - `push_interval_seconds`

### 图片

- 支持按 `barcode` 查图
- 找不到时回退到 `style_no`
- 支持图片映射 CSV
- 支持公网 URL 图床测试

### 后台网页

当前后台已包含：

- 规则管理
- 消息模板管理
- 运行配置
- 手动测试
- 推送记录
- 系统状态

规则支持：

- 新建
- 停用
- 恢复
- 硬删除

模板支持：

- 多模板保存
- 切换启用模板
- 另存为
- 删除
- 预览

## 已知坑点

- `run-admin` 是错误命令，正确命令是 `run-server`
- PowerShell 里路径带空格时，Python 路径必须整体加引号
- 有些中文乱码问题并不是 HTML 模板本身坏了，而是 Python 运行时字符串损坏
- `apply_patch` 在这个 Windows 环境下偶尔会失败；必要时可用提权 PowerShell 写文件，但不要用破坏性命令
- 仓库里可能存在用户手工测试留下的文件，不要擅自清理

## 修改代码时的优先级

1. 先确认当前配置文件和命令真实可用
2. 先修可测试链路，再做结构优化
3. 先保证网页配置能落到实际运行链路
4. 任何“完成”结论前先跑相关 pytest

## 推荐回归测试

至少优先跑相关测试，而不是盲目全量：

```powershell
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_web_text_labels.py -q
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -m pytest tests\test_runtime_settings_web_app.py tests\test_message_template_engine.py -q
```

如改动涉及配置、调度、推送链路，再补跑对应测试文件。

## 新会话接手时的最小上下文

如果需要压缩上下文并重开对话，先告知：

1. 项目目录是 `C:\Users\x\wecom-sales-webhook-bot\.worktrees\wecom-bot-impl`
2. 先看交接文档 `docs/superpowers/plans/2026-05-30-wecom-sales-webhook-bot-handoff-zh.md`
3. 当前目标通常是：
   - 继续完成后台网页 / 推送链路 / SQL Server 测试
   - 或整理最终部署结构并准备交接 IT

