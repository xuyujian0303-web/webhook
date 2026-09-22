# 测试发布说明

## 启动

1. 安装 Python 3.12 或更高版本。
2. 在项目目录执行 `python -m pip install -e .`。
3. 复制 `config.example.yaml` 为 `config.local.yaml`。
4. 复制 `ems_config.example.json` 为 `ems_config.json`，填写 EMS 账号密码。
5. 双击根目录的 `启动桌面GUI.vbs`。

如果项目已安装依赖，也可以直接双击启动脚本；脚本会自动设置 `PYTHONPATH=src`，不需要打开终端。

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
