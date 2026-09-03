# 企业微信销售单推送机器人：当前状态交接文档

## 1. 项目位置

- 主工作目录：`C:\Users\x\wecom-sales-webhook-bot\.worktrees\wecom-bot-impl`
- 当前分支：`feature/wecom-bot-impl`

## 2. 当前目标

项目已经完成了后端原型和基础管理后台。

当前最新目标已经调整为两阶段：

1. 先完善网页端交互和 UI，形成适合日常使用的中文管理后台。
2. 在不接入真实 IT 接口前，先使用 `CSV + 本地图片 URL` 跑通完整测试流程。

后续再接入：

- IT 提供的真实销售数据接口
- IT 提供的真实商品图片 URL

## 3. 已完成内容

### 3.1 核心后端能力

以下能力已经实现：

- 配置文件读取与校验
- CSV 销售数据读取
- 销售单按单号聚合
- 规则筛选
- 推送去重状态记录
- 商品图片 URL 解析
- 企业微信 `markdown_v2` 消息构建
- Webhook 发送
- 定时扫描执行
- 基础管理后台
- 登录能力
- 规则管理能力
- 推送记录页
- 系统状态页

### 3.2 测试状态

完整回归测试已经通过。

- 测试结果：`29 passed`

### 3.3 已完成的重要提交

- `96117de` `feat: add backend and api config`
- `d76f78a` `fix: make legacy config sections optional in load_config`
- `5ef1bd7` `fix: validate optional config sections`
- `e072a36` `fix: validate csv field mapping config`
- `23efbfb` `feat: add remote image fields to sales items`
- `ae71ace` `test: cover mixed image source limits`
- `d7e2b83` `fix: truncate whole message item blocks`
- `3d18816` `fix: enforce message builder limits`
- `bf436fa` `feat: add backend database schema`
- `5595594` `feat: add rule evaluation service`
- `6810dfa` `feat: add sales api adapter`
- `d52d155` `feat: add backend login flow`
- `52aedb0` `feat: add rule management pages`
- `a0e9ddb` `feat: add scheduled scan runner`
- `b2e3a34` `feat: wire admin backend startup and status pages`

## 4. 当前网页端状态

当前模板文件已经存在：

- `src/wecom_sales_webhook_bot/templates/base.html`
- `src/wecom_sales_webhook_bot/templates/login.html`
- `src/wecom_sales_webhook_bot/templates/rules.html`
- `src/wecom_sales_webhook_bot/templates/rule_edit.html`
- `src/wecom_sales_webhook_bot/templates/push_records.html`
- `src/wecom_sales_webhook_bot/templates/system_status.html`

当前后台是“可用但比较简陋”的状态：

- 可以登录
- 可以进入规则列表
- 可以新建规则
- 可以查看状态页
- 可以查看推送记录

但目前还存在这些不足：

- 页面整体 UI 比较基础
- 中文提示不够完整
- 规则列表信息太少
- 规则条件摘要不够直观
- 缺少更顺手的测试入口
- 缺少更完整的后台导航体验

## 5. 本地验证中已经确认过的问题

### 5.1 已发现并已处理的问题

1. `python -m wecom_sales_webhook_bot.cli ...` 之前无反应
原因：`cli.py` 缺少模块入口。

当前本地已修复，但修复还没有单独提交：

- `src/wecom_sales_webhook_bot/cli.py`
- 增加了 `if __name__ == "__main__": main()`

2. SQLite 启动时报错 `unable to open database file`
原因：`var/` 目录不存在。

当前用户已经手动创建目录，服务可启动。

### 5.2 仍需保留注意的事项

- 当前本地测试依赖 `config.yaml`
- 当前本地数据库目录是 `var/`
- 这些文件目前属于本地测试态，不应被随意删除或重置

## 6. 当前未提交的本地改动

以下文件当前有未提交改动，需要保留，不要误删：

- `src/wecom_sales_webhook_bot/cli.py`
- `src/wecom_sales_webhook_bot/csv_source.py`
- `src/wecom_sales_webhook_bot/orchestrator.py`

当前未跟踪文件包括：

- `config.yaml`
- `docs/superpowers/plans/2026-04-22-wecom-sales-webhook-bot-admin-backend.md`
- `send_second_order_compact_preview.py`
- `send_second_order_grouped_preview.py`
- `send_second_order_markdown.py`
- `send_second_order_ultra_compact_preview.py`
- `serve-images.err.txt`
- `serve-images.out.txt`
- `serve_real_test_images.py`
- `tests/test_real_data_compat.py`
- `var/`

说明：

- 这些文件里有一部分是原型测试脚本
- 还有一部分是本地运行数据
- 当前不应进行清理式操作，除非后续单独确认

## 7. 原型兼容性改动说明

为了兼容你手头的真实 CSV 和图片数据，当前本地还有两处重要但未正式提交的兼容改动：

### 7.1 `csv_source.py`

新增了更宽松的销售时间解析，支持：

- `%Y-%m-%d %H:%M:%S`
- `%Y/%m/%d %I:%M %p`
- `%Y/%m/%d %H:%M:%S`

### 7.2 `orchestrator.py`

图片查找增加了回退逻辑：

1. 先按 `barcode` 查图
2. 查不到再按 `style_no` 查图

这两处改动对真实 CSV 原型测试有帮助，但目前与正式后台实现链路分开管理。

## 8. 当前本地运行方式

### 8.1 Python 解释器

当前实际可用解释器：

`C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe`

### 8.2 启动命令

在工作目录下执行：

```powershell
cd C:\Users\x\wecom-sales-webhook-bot\.worktrees\wecom-bot-impl
$env:PYTHONPATH="src"
& "C:\Users\x\Desktop\HeyGem数字人\Infinite talk\InfiniteTalk-new-fix\InfiniteTalk\py312\python.exe" -u -m wecom_sales_webhook_bot.cli run-server --config config.yaml
```

### 8.3 当前配置文件示例

当前测试中的 `config.yaml` 结构如下：

```yaml
wecom:
  webhook_url: https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=replace-me
  timeout_seconds: 5
  retry_times: 2

runtime:
  scan_interval_seconds: 1200
  max_images_per_message: 8
  dry_run: true

backend:
  database_url: sqlite:///./var/app.db
  secret_key: test-secret-key
  host: 127.0.0.1
  port: 5000
  bootstrap_admin_username: admin
  bootstrap_admin_password: pass123

api:
  sales_base_url: https://internal.example.com
  sales_token: replace-me
  sales_path: /sales/query
  timeout_seconds: 10
```

## 9. 当前第一优先级工作

接下来优先做的不是接真实接口，而是先完善后台使用体验。

建议按这个顺序推进：

1. 重新进行一轮网页端需求确认
2. 产出新的网页端设计文档
3. 产出实现计划
4. 完善中文 UI、导航、规则展示和测试入口
5. 用 `CSV + 本地图片 URL` 进行完整后台测试
6. 最后再切换到真实 API 与真实图片 URL

## 10. 下一轮建议工作内容

下一轮对话建议直接从“网页端第一版范围确认”开始。

建议第一版后台至少包含：

- 规则列表页
- 规则新建/编辑页
- 手动测试页
- 推送记录页
- 系统状态页

其中“手动测试页”非常关键，因为它能直接支撑当前的 `CSV + 本地图片 URL` 原型测试。

## 11. 新开对话时建议直接提供的信息

如果重新开对话，建议直接发这几项：

1. 说明项目目录：
`C:\Users\x\wecom-sales-webhook-bot\.worktrees\wecom-bot-impl`

2. 说明先看这份交接文档：
`docs/superpowers/plans/2026-05-30-wecom-sales-webhook-bot-handoff-zh.md`

3. 说明当前目标：
先完善网页端 UI 和交互，再用 `CSV + 本地图片 URL` 跑通测试，不先接真实接口。

## 12. superpowers 工作流状态说明

这个项目并不只是一直在用 `brainstorming`，实际上已经经过了多种阶段：

- `brainstorming`：确认业务需求、消息格式、图片策略、CSV 方案
- `writing-plans`：拆解原型和后台实现任务
- `test-driven-development`：补测试并实现后端能力
- `systematic-debugging`：处理启动、数据库、页面和兼容问题

下一步正确流程应当是：

1. 围绕网页端完善做新一轮 `brainstorming`
2. 确认后进入 `writing-plans`
3. 再进入实现和测试

## 13. 结论

当前项目并不是从零开始，而是已经有了可运行后端和基础后台。

现在最重要的是：

- 不丢失上下文
- 把状态文档固定下来
- 用新对话承接下一轮网页端完善工作

这份文档就是后续承接工作的统一入口。
