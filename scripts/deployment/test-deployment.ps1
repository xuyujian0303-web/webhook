param([string]$AppRoot = (Resolve-Path "$PSScriptRoot\..\..").Path,[string]$ConfigPath = "config.sqlserver.local.yaml",[int]$Port = 5000)
$ErrorActionPreference = "Stop"
$config = Join-Path $AppRoot $ConfigPath
if(-not (Test-Path $config)){ throw "配置文件不存在: $config" }
if(-not (Test-Path (Join-Path $AppRoot "src"))){ throw "src 目录不存在" }
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if($listener){ Write-Host "端口 $Port 正在监听，PID: $($listener[0].OwningProcess)" } else { Write-Host "端口 $Port 当前未监听（服务可能尚未启动）" }
try { $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/login" -UseBasicParsing -TimeoutSec 5; Write-Host "网页 /login HTTP $($response.StatusCode)" } catch { Write-Host "网页 /login 当前不可访问: $($_.Exception.Message)" }
Get-Service WeComSalesBotWeb,WeComSalesBotScheduler -ErrorAction SilentlyContinue | Select-Object Name,Status,StartType
