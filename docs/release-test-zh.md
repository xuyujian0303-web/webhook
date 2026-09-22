# 测试发布说明

## 启动

1. 双击根目录的 `一键安装并启动GUI.cmd`。
2. 脚本会检查 Python 3.12；缺少时尝试使用 Windows `winget` 安装。
3. 脚本会安装项目依赖，并创建缺失的 `config.local.yaml`、`ems_config.json` 和 `var` 目录。
4. 首次启动后，在 GUI 中填写 EMS 账号、密码和测试 Webhook。
5. 首次测试保持“演练模式”开启，确认筛选结果和消息内容后再关闭。

如果电脑没有 `winget`，请先安装 Python 3.12，再重新双击启动脚本。脚本不会覆盖已有配置。

## 测试范围

- GUI 运行配置、Webhook 配置和 EMS 配置保存。
- 新建、编辑、停用和删除筛选规则。
- 销售日期的早于、晚于、日期区间和时段条件。
- 金额字段的等于、大于、大于等于、小于、小于等于和介于条件。
- 全部满足、任一满足两组条件的组合。
- 演练模式下生成消息，不会实际发送企业微信。
- 实际 Webhook 推送前，确认图片 URL 能从企业微信侧访问。

## 注意事项

- `config.local.yaml`、`ems_config.json`、`var/` 和真实 Webhook 地址属于本机数据，不要提交或转发。
- 图片消息使用 `![款号](图片URL)` 格式；EMS 图片地址使用完整产品编码，例如 `GJA14344PIBL0B6_01.jpg`。
- 首轮实际推送建议保持演练模式，确认规则和消息内容后再关闭。

## 自动化测试

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q
```

如果 Windows 临时目录权限导致 pytest 报 `WinError 5`，可改用仓库内临时目录：

```powershell
python -m pytest -q --basetemp .tmp-pytest-release
```