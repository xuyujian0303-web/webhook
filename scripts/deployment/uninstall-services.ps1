param([Parameter(Mandatory)][string]$NssmExe)
$ErrorActionPreference = "Stop"
foreach($name in @("WeComSalesBotWeb","WeComSalesBotScheduler")){ & $NssmExe stop $name 2>$null; & $NssmExe remove $name confirm 2>$null }
