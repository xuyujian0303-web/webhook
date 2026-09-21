# 项目重启交接文档

更新时间：2026-09-21

## 1. 项目目标

每 20 分钟从 EMS 只读服务器读取销售详单，按“全部满足（AND）”和“任一满足（OR）”规则筛选，按销售单号去重，把同一销售单聚合后以企业微信 `markdown_v2` Webhook 推送到一个或多个群。

## 2. 已完成

- EMS TCP 登录、初始化握手、销售详单读取和 TLV/RDS 解码。
- Windows 桌面 GUI：运行配置、规则配置、多个 Webhook、启动/停止持续扫描、状态和推送记录。
- Flask 网页配置仍保留，可用于服务器部署。
- 支持多个 Webhook；同一批查询结果只读取一次，再发送到全部地址。
- 推送成功后才写入去重状态；失败可重试。
- 销售机构和业绩机构已作为不同字段解码和映射。
- 规则支持 AND/OR 组合；未被 EMS 协议确认的字段在本地解码后过滤。
- `return_whole_order` 支持“返回包含筛选条件的整个销售单”。
- 图片消息保留原始 Markdown 图片格式：`![款号](EMS图片URL)`。当前优先使用 EMS 返回的图片 URL，不使用企业微信不可访问的 `127.0.0.1` 地址。
- GUI 保存的 `runtime.rescan_start_date` 会作为扫描下界，不再被上次扫描时间覆盖。

## 3. EMS 日期范围协议

真实文件曾在本机 `captures/0920 ems 1.pcapng`，对应导出文件为 `captures/0920 ems 1.xlsx`。原始抓包不应提交到公开仓库；协议结论已经写入代码和本文档。

真实请求摘要：

```text
method=querySaleDetailList
0x2712 = 20230920       # 固定协议基准
field 3 = 20260919      # 起始日期
field 22 = 10000        # 单件价格/抓包定义以 GUI 映射为准
field 24 = 1             # 折扣条件
field 20 = 26FW          # 季号
field 28 = 26fwg6        # 出货组别
field 29 = 1             # 返回整单
```

注意：`end_date` 不是简单替换到 field 3 的第二个日期。服务器按当前日期提供上限。修改 `ems_client.py` 前必须重新检查真实抓包。

## 4. 规则筛选边界

已确认可以向 EMS 请求的筛选项包括日期起点、整单金额、单件价格、单件折扣、季号、出货组别，以及抓包已验证的其他参数。款色码等字段需要先下载并解码后本地筛选。GUI 应明确显示每个字段的筛选层级：`EMS服务器筛选` 或 `本地筛选`。

用户实际使用过的值包括：

- 日期起始：`2026-09-19`
- 季号：`26FW`
- 出货组别：`26fwg6`
- 款色码：`jach619cny0`（本地筛选）

## 5. 图片要求

不要把图片格式改成 `[款号](URL)`，也不要切换成普通链接。消息正文应继续生成：

```markdown
![款号](http://giada-erp.redstone.com.cn/giada/images/....jpg)
```

企业微信客户端曾在网页版本正常显示；GUI 版本的问题优先检查正文、URL、消息类型和请求响应，不要先做降级。

## 6. 运行与排查

查看进程：

```powershell
Get-CimInstance Win32_Process | Where-Object {$_.CommandLine -match 'wecom_sales_webhook_bot'} | Select-Object ProcessId,CommandLine
```

停止指定进程：

```powershell
Stop-Process -Id <PID> -Force
```

启动 GUI：

```powershell
Set-Location C:\Users\redstone\webhook
$env:PYTHONPATH="src"
python -m wecom_sales_webhook_bot.cli desktop-gui --config config.local.yaml
```

扫描日志应出现类似：

```text
loaded N orders; dates=['2026-09-19', '2026-09-20', ...]
```

若状态为 success 但没有消息，依次检查规则是否命中、去重状态、推送时间窗口、`dry_run`、Webhook 响应和消息正文。

## 7. 待完成

- 用更多真实抓包逐项核对所有 EMS 高级筛选字段，特别是款号/款色码、单价、折扣和“返回整单”的组合。
- 补充协议帧单元测试，防止固定基准日期和起始日期字段再次错位。
- 解决 Windows pytest 临时目录权限问题并跑完整测试集。
- 最终确认 GUI 图片正文在企业微信客户端显示，并记录一次非敏感的请求结果。
- 检查 delivery 交付包是否与当前源码一致，必要时重新生成。
- 后续变更完成后再提交并推送 GitHub。

## 8. 新对话第一步

新上下文先执行：

```powershell
Set-Location C:\Users\redstone\webhook
git status --short
Get-Content .\AGENTS.md
Get-Content .\docs\project-handoff-zh.md
```

然后阅读 `ems_client.py`、`ems_source.py`、`ems_decoder.py`、`orchestrator.py`、`message_builder.py`，不要先修改协议或发送 Webhook。