$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root "dist\LawWatchMonitor"
$pythonExe = (Get-Command python).Source
$pythonRoot = Split-Path $pythonExe -Parent
New-Item -ItemType Directory -Force -Path (Join-Path $out "data\logs") | Out-Null
Copy-Item $pythonRoot (Join-Path $out "python") -Recurse -Force
& (Join-Path $out "python\python.exe") -m pip install --upgrade pip
& (Join-Path $out "python\python.exe") -m pip install -r (Join-Path $root "requirements.txt")
Copy-Item (Join-Path $root "monitor") (Join-Path $out "monitor") -Recurse -Force
Copy-Item (Join-Path $root "windows\run.bat") (Join-Path $out "run.bat") -Force
Copy-Item (Join-Path $root "windows\config.example.json") (Join-Path $out "config.example.json") -Force
Copy-Item (Join-Path $root "windows\install-task.bat") (Join-Path $out "install-task.bat") -Force
Copy-Item (Join-Path $root "windows\uninstall-task.bat") (Join-Path $out "uninstall-task.bat") -Force
Copy-Item (Join-Path $root "windows\README.txt") (Join-Path $out "README.txt") -Force
Copy-Item (Join-Path $root "monitor\sites.csv") (Join-Path $out "data\sites.csv") -Force
"{`"documents`":{},`"list_urls`":{},`"errors`":{},`"baselined`":false}" | Set-Content (Join-Path $out "data\state.json") -Encoding utf8
Write-Host "Built: $out"
