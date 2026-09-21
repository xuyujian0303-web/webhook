$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot "src"
Set-Location $projectRoot
if (-not (Test-Path (Join-Path $projectRoot "config.local.yaml"))) {
    Copy-Item (Join-Path $projectRoot "config.example.yaml") (Join-Path $projectRoot "config.local.yaml")
    Write-Host "已创建 config.local.yaml 示例文件。请先在桌面窗口填写 EMS 账号和 Webhook；演练模式默认开启。"
}
if (-not (Test-Path (Join-Path $projectRoot "ems_config.json"))) {
    Copy-Item (Join-Path $projectRoot "deployment\ems_config.example.json") (Join-Path $projectRoot "ems_config.json")
    Write-Host "已创建 ems_config.json 本地示例文件。请在桌面窗口的 EMS 登录页填写账号和密码。"
}
python -m wecom_sales_webhook_bot.cli desktop-gui --config config.local.yaml
