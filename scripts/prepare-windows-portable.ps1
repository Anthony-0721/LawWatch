$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$out = Join-Path $root "dist\LawWatchMonitor"
$pythonExe = (Get-Command python).Source
if (-not (Test-Path -LiteralPath $pythonExe) -or (Get-Item -LiteralPath $pythonExe).Length -eq 0) {
    throw "python resolves to an invalid or 0-byte Microsoft Store stub: $pythonExe. Install a real Python interpreter and retry."
}

& $pythonExe -c "import sys; assert sys.prefix == sys.base_prefix and sys.executable.startswith(sys.prefix); print('OK')" > $null
if ($LASTEXITCODE -ne 0) {
    throw "python must be a full standalone official installation, not a venv or other virtual environment: $pythonExe. Install the full python.org Python distribution and retry."
}
$pythonRoot = Split-Path $pythonExe -Parent
if (Test-Path -LiteralPath (Join-Path $pythonRoot "conda-meta")) {
    throw "python appears to be a conda-managed environment: $pythonExe. Use a full official python.org installation instead of conda, then retry."
}
$vcruntimePath = Join-Path $pythonRoot "vcruntime140.dll"
if (-not (Test-Path -LiteralPath $vcruntimePath)) {
    throw "The Python install folder is missing vcruntime140.dll: $pythonRoot. Install the full official python.org Python (which bundles the Microsoft VC++ runtime) or install the Microsoft Visual C++ 2015-2022 x64 Redistributable on this build machine and retry."
}
$rootPrefix = $root.TrimEnd('\','/') + [System.IO.Path]::DirectorySeparatorChar
if (-not $out.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove output outside the repository root: $out"
}
if (Test-Path -LiteralPath $out) {
    Remove-Item -LiteralPath $out -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $out "data\logs") | Out-Null
Copy-Item $pythonRoot (Join-Path $out "python") -Recurse -Force
& (Join-Path $out "python\python.exe") -m pip install --upgrade pip
& (Join-Path $out "python\python.exe") -m pip install -r (Join-Path $root "requirements.txt")
Copy-Item (Join-Path $root "monitor") (Join-Path $out "monitor") -Recurse -Force
Get-ChildItem (Join-Path $out "monitor") -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
Copy-Item (Join-Path $root "windows\run.bat") (Join-Path $out "run.bat") -Force
Copy-Item (Join-Path $root "windows\config.example.json") (Join-Path $out "config.example.json") -Force
Copy-Item (Join-Path $root "windows\install-task.bat") (Join-Path $out "install-task.bat") -Force
Copy-Item (Join-Path $root "windows\uninstall-task.bat") (Join-Path $out "uninstall-task.bat") -Force
Copy-Item (Join-Path $root "windows\README.txt") (Join-Path $out "README.txt") -Force
Copy-Item (Join-Path $root "monitor\sites.csv") (Join-Path $out "data\sites.csv") -Force
$stateJson = "{`"documents`":{},`"list_urls`":{},`"errors`":{},`"baselined`":false}"
[System.IO.File]::WriteAllText((Join-Path $out "data\state.json"), $stateJson, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Built: $out"
