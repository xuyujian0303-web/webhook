# 项目协作交接

## 项目

本仓库是企业微信销售单推送机器人，目录为 `C:\Users\redstone\webhook`。当前主运行方式是 Windows 桌面 GUI；项目也保留 Flask 网页配置和 Windows 部署脚本。

新对话开始时，先阅读本文件和 `docs/project-handoff-zh.md`，再检查工作区状态。不要凭旧上下文假设协议字段或配置路径。

## 当前入口

```powershell
Set-Location C:\Users\redstone\webhook
$env:PYTHONPATH="src"
python -m wecom_sales_webhook_bot.cli desktop-gui --config config.local.yaml
```

持续扫描由 GUI 的“启动持续扫描”按钮启动，等价于：

```powershell
python -u -m wecom_sales_webhook_bot.cli schedule --config config.local.yaml
```

单轮扫描：

```powershell
python -u -m wecom_sales_webhook_bot.cli run-once --config config.local.yaml
```

## 重要边界

- EMS 只读；不要调用新增、修改或删除接口。
- 不要把 `config.local.yaml`、`ems_config.json`、真实 Webhook、密码、`var/` 运行状态、原始抓包或销售导出文件提交到 Git。
- 图片推送必须继续使用原始 Markdown 图片格式 `![款号](URL)`，不要降级为普通链接。
- 不要为了验证而重复发送真实 Webhook，除非用户明确要求。
- 不要回滚工作区中用户已有的改动。

## 已验证的 EMS 结论

真实抓包 `0920 ems 1.pcapng` 已确认销售详单是“起始日期至服务器当前日期”的范围查询，不是按天查询。请求中：

- `0x2712` 是固定协议基准日期，抓包值为 `20230920`。
- 参数 `3` 是起始日期，例如 `20260919`。
- 查询上限由 EMS 当前日期处理，代码传入的 `end_date` 不能被错误写入参数 3。
- 抓包还验证了金额、折扣、季号、出货组别等字段的参数编号。

修正后真实只读查询 `20260919` 返回 509 条，日期包含 `2026-09-19`、`2026-09-20`、`2026-09-21`。

## 开发验证

```powershell
$env:PYTHONPATH="src"
python -m compileall -q src
pytest -q
```

Windows 临时目录权限可能导致 pytest 收集阶段报 `WinError 5`；这不是业务断言失败，需要单独处理测试环境权限。

## 修改优先级

1. 先确认 `config.local.yaml`、`runtime.rescan_start_date`、`var/push-state.json` 和运行进程。
2. EMS 协议改动必须基于真实抓包帧，并用只读服务器查询验证返回日期分布。
3. 规则字段要区分 EMS 服务器筛选和解码后的本地筛选。
4. 修改完成后运行编译检查和针对性测试，再更新交接文档。