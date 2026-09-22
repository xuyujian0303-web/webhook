# 企业微信销售单推送机器人

Windows 桌面 GUI 版本：从 EMS 读取销售详单，按规则筛选订单，使用企业微信 Webhook 推送 Markdown 消息。

## 一键安装和启动

Windows 测试人员直接双击根目录的 `一键安装并启动GUI.cmd`。它会自动：

1. 检查 Python 3.12；未找到时尝试通过 Windows `winget` 安装。
2. 安装项目依赖。
3. 创建缺失的 `config.local.yaml`、`ems_config.json` 和 `var` 目录，不覆盖已有文件。
4. 在后台启动桌面 GUI。

如果电脑没有 `winget`，请先安装 Python 3.12，再重新双击该文件。首次启动后，在 GUI 中填写 EMS 账号和企业微信 Webhook。真实账号、密码、Webhook 和运行状态不会自动生成，也不会覆盖已有配置。

首次测试请保持 GUI 的“演练模式”开启，确认筛选规则和消息内容后再关闭。不要把本机配置提交到 GitHub。

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

## 手动测试

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q
```

Windows 临时目录权限导致 pytest 报错时，可使用仓库内临时目录：

```powershell
python -m pytest -q --basetemp .tmp-pytest
```

详细测试步骤见 [`docs/release-test-zh.md`](docs/release-test-zh.md)。