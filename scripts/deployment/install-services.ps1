param([Parameter(Mandatory)][string]$NssmExe,[Parameter(Mandatory)][string]$AppRoot,[Parameter(Mandatory)][string]$PythonExe,[Parameter(Mandatory)][string]$ConfigPath,[Parameter(Mandatory)][string]$ServiceAccount,[Parameter(Mandatory)][string]$ServicePassword,[string]$LogDirectory = (Join-Path $AppRoot "logs"))
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$services = @(@{Name="WeComSalesBotWeb"; Script="start-web.ps1"}, @{Name="WeComSalesBotScheduler"; Script="start-scheduler.ps1"})
foreach($item in $services){
  & $NssmExe stop $item.Name 2>$null
  & $NssmExe remove $item.Name confirm 2>$null
  $scriptPath = Join-Path $PSScriptRoot $item.Script
  $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -AppRoot `"$AppRoot`" -ConfigPath `"$ConfigPath`" -PythonExe `"$PythonExe`" -LogDirectory `"$LogDirectory`""
  & $NssmExe install $item.Name "powershell.exe" $arguments
  & $NssmExe set $item.Name ObjectName $ServiceAccount $ServicePassword
  & $NssmExe set $item.Name AppDirectory $AppRoot
  & $NssmExe set $item.Name Start SERVICE_AUTO_START
  & $NssmExe set $item.Name AppExit Default Restart
  & $NssmExe set $item.Name AppRestartDelay 10000
  & $NssmExe start $item.Name
}
