# Windows Server IT 交接说明

## 部署结构

使用本机低权限账号 `.svc-wecom-bot` 运行两个 NSSM 服务：`WeComSalesBotWeb`（后台网页）和 `WeComSalesBotScheduler`（持续扫描）。销售 SQL Server 与机器人后台业务库必须分开：销售库账号仅授予 `SELECT`，禁止 `INSERT/UPDATE/DELETE`、建表和改表；后台业务库才允许机器人读写账号、规则、模板、运行配置和推送记录。

需要安装 Python 3.12、项目依赖、Microsoft ODBC Driver 17/18 for SQL Server 和 NSSM。商品图片由 SQL Server 返回内网 URL 时不启动 `serve-images`。

## 目录

建议：`C:\WeComSalesBot\app` 代码，`config` 配置，`data` 去重状态，`logs` 日志。服务账号读取 app/config，读写 data/logs；不要把真实 webhook 或数据库密码提交代码库。

## 安装

管理员 PowerShell：

```powershell
.\scripts\deployment\install-services.ps1 -NssmExe C:\Tools\nssm\win64\nssm.exe -AppRoot C:\WeComSalesBot\app -PythonExe C:\Python312\python.exe -ConfigPath C:\WeComSalesBot\config\config.sqlserver.local.yaml -ServiceAccount .\svc-wecom-bot -ServicePassword '<密码>' -LogDirectory C:\WeComSalesBot\logs
```

安装后运行 `test-deployment.ps1`。防火墙只允许公司内网网段访问后台端口（默认 5000），禁止公网暴露。

## 配置生效

网页保存规则、模板、扫描周期、图片数、消息间隔和每日推送时段后，下一扫描周期读取新值，不需重启。扫描全天读取 SQL Server；默认每日 `10:00-22:00` 才调用 webhook，其他时间不标记已推送，进入时段自动补推。规则日期范围支持只填开始、只填结束或都填；都留空时默认从本次扫描服务启动当天 `00:00:00` 开始。IT 修改 `datasource.local.yaml` 的连接、表名或字段映射后，重启 `WeComSalesBotScheduler`。

## 运维

```powershell
Get-Service WeComSalesBotWeb,WeComSalesBotScheduler
Restart-Service WeComSalesBotScheduler
Get-Content C:\WeComSalesBot\logs\scheduler-console.log -Wait
.\scripts\deployment\uninstall-services.ps1 -NssmExe C:\Tools\nssm\win64\nssm.exe
```

更新前备份 config、data 和后台业务数据库；停止服务后替换 app，验证后先启动网页再启动扫描。不要覆盖 data 或数据库，否则可能重复推送历史订单。

## 验收清单

- 内网浏览器可打开 `/login` 并登录。
- 网页保存模板、规则和运行配置后下一扫描周期可见。
- 销售 SQL Server 账号执行写入操作被拒绝。
- `10:00-22:00` 外命中订单不发送，进入时段后补推。
- NSSM 服务开机自动启动，手工停止后可自动恢复。
- 企业微信返回 `errcode=0`，失败消息不写入已推送状态。
