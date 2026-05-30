# WeCom Sales Webhook Bot

企业微信群 webhook 销售晒单机器人原型。

## 安装

1. `python -m venv .venv`
2. `.venv\\Scripts\\activate`
3. `python -m pip install -e .[dev]`
4. 复制 `config.example.yaml` 为 `config.yaml`

## 常用命令

- `python -m wecom_sales_webhook_bot.cli run-once --config config.yaml`
- `python -m wecom_sales_webhook_bot.cli schedule --config config.yaml`
- `python -m wecom_sales_webhook_bot.cli serve-images --config config.yaml`
- `python -m wecom_sales_webhook_bot.cli clear-state --config config.yaml`

## Admin Backend

- `python -m wecom_sales_webhook_bot.cli run-server --config config.yaml`
- 登录地址：`http://127.0.0.1:5000/login`
- 后台默认使用 SQLite 保存用户、规则、推送记录和扫描状态
