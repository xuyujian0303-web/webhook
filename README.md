# 企业微信销售单推送机器人

Windows 桌面 GUI 版本：从 EMS 读取销售详单，按规则筛选订单，使用企业微信 Webhook 推送 Markdown 消息。

## 快速开始

1. 安装 Python 3.12 或更高版本。
2. 在项目目录执行 `python -m pip install -e ".[dev]"`。
3. 复制 `config.example.yaml` 为 `config.local.yaml`。
4. 复制 `ems_config.example.json` 为 `ems_config.json`，填写 EMS 账号密码。
5. 双击 `启动桌面GUI.vbs`。

启动脚本会自动设置 `PYTHONPATH=src`，不需要打开终端或 PowerShell。

首次测试请保持 GUI 的“演练模式”开启，确认筛选规则和消息内容后再关闭。Webhook 地址、账号密码和运行状态只保存在本机配置中，不要提交到 GitHub。

## GUI 功能

- EMS 登录和销售详单读取
- 全部满足、任一满足规则组合
- 金额、销售日期、门店、产品、季号、出货组别等筛选
- 自定义消息模板和预览
- 多个企业微信群机器人地址
- 单次扫描、持续扫描、推送记录和去重状态
- EMS 商品图片 Markdown 推送

EMS 图片地址使用完整产品编码，例如：

```text
http://giada-erp.redstone.com.cn/giada/images/GJA14344PIBL0B6_01.jpg
```

## 测试

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q
```

Windows 临时目录权限导致 pytest 报错时，可使用仓库内临时目录：

```powershell
python -m pytest -q --basetemp .tmp-pytest
```

详细测试步骤见 [`docs/release-test-zh.md`](docs/release-test-zh.md)。