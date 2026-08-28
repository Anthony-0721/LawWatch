# LawWatch 双部署 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有监测核心上增加 Windows 绿色版运行模式，并保留国内自托管 GitHub Actions Runner 方案。

**Architecture:** 保持同一 `monitor/` 核心；通过可执行文件所在目录的 `data/` 与本地 `config.json` 提供 Windows 配置；用便携 Python 目录封装成绿色版；用 `schtasks` 创建每 30 分钟任务；GitHub Actions 模式继续读取 Secrets。

**Tech Stack:** Python 3.12 便携运行时、Windows Task Scheduler、PowerShell、GitHub Actions、现有 requests/BeautifulSoup/Playwright 栈。

## Global Constraints

- Windows 版本目标：64 位 Windows 10/11 与 Windows Server 2019/2022。
- 绿色版目录：`data/` 存放 `sites.csv`、`state.json`、`logs/`。
- 本地配置：`config.json` 字段必须为 `smtp_user`、`smtp_auth_code`、`email_to`、`wecom_webhook`、`schedule_minutes`。
- 不提交真实凭据；`config.json` 必须在 `.gitignore` 中忽略。
- Windows 首次运行必须建立全新基线；默认不发送失败报警。
- GitHub Actions 模式必须保持现有 `self-hosted,linux,x64,lawwatch-domestic` 标签与 Secrets 读取。
- 所有现有测试必须继续通过；新增 Windows 路径/配置/通知读取测试。

---

## Task 1: 路径与本地配置

**Files:**
- Modify: `monitor/config.py`
- Modify: `monitor/notify.py`
- Modify: `monitor/run.py`
- Create: `tests/test_local_config.py`
- Modify: `.gitignore`

**Interfaces:**
- `app_root() -> Path`
- `data_dir() -> Path`
- `default_sites_path() -> Path`
- `default_state_path() -> Path`
- `load_local_config(path: Path | None = None) -> dict`
- `notify_all(items, local_config: dict | None = None) -> bool`
- `send_test_notification(local_config: dict | None = None) -> bool`
- `run(send=False, max_pages=30, persist=True, max_workers=5, local_config=None) -> dict`

**Step 1: Write failing test**

```python
from pathlib import Path
from monitor.config import (
    app_root, data_dir, default_sites_path, default_state_path, load_local_config,
)

def test_local_config_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWWATCH_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path
    assert default_sites_path() == tmp_path / "sites.csv"
    assert default_state_path() == tmp_path / "state.json"

def test_load_local_config_returns_defaults_when_missing():
    config = load_local_config(Path("missing.json"))
    assert config["smtp_user"] == ""
    assert config["schedule_minutes"] == 30
```

**Step 2: Run and confirm failure**

```bash
python -m pytest tests/test_local_config.py -v
```

**Step 3: Implement**

`monitor/config.py` append:

```python
import json
import sys

def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PACKAGE_DIR.parent

def data_dir() -> Path:
    override = os.getenv("LAWWATCH_DATA_DIR", "").strip()
    return Path(override) if override else app_root() / "data"

def default_sites_path() -> Path:
    return data_dir() / "sites.csv"

def default_state_path() -> Path:
    return data_dir() / "state.json"

def load_local_config(path: Path | None = None) -> dict:
    config_path = path or Path(os.getenv("LAWWATCH_CONFIG", "") or app_root() / "config.json")
    defaults = {
        "smtp_user": "",
        "smtp_auth_code": "",
        "email_to": "",
        "wecom_webhook": "",
        "schedule_minutes": 30,
    }
    if config_path.exists():
        try:
            defaults.update(json.loads(config_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return defaults
```

`monitor/notify.py` change `notify_all` and add `send_test_notification` optional config; both must use config values first, then environment fallback.

`monitor/run.py` must:
- call `data_dir()` and `default_state_path()` instead of hardcoded package path;
- accept `local_config=None` and pass it to `notify_all`;
- add CLI `--config` and `--data-dir`; load config if present.

**Step 4: Run focused and full tests**

```bash
python -m pytest tests/test_local_config.py -v
python -m pytest -q
```

**Step 5: Commit**

```bash
git add monitor/config.py monitor/notify.py monitor/run.py tests/test_local_config.py .gitignore
git commit -m "feat(monitor): support local config and portable data paths"
```

---

## Task 2: 日志与运行目录

**Files:**
- Create: `monitor/logging_util.py`
- Modify: `monitor/run.py`
- Create: `tests/test_logging_util.py`

**Interfaces:**
- `setup_logging(log_dir: Path) -> None`
- `log_path(log_dir: Path) -> Path`

**Step 1: Write failing test**

```python
from pathlib import Path
from monitor.logging_util import log_path

def test_log_path_is_monitor_log(tmp_path):
    assert log_path(tmp_path).name == "monitor.log"
```

**Step 2: Run and confirm failure**

**Step 3: Implement**

```python
import logging
from pathlib import Path

def log_path(log_dir: Path) -> Path:
    return log_dir / "monitor.log"

def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_path(log_dir),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
```

`run.py` calls `setup_logging(data_dir() / "logs")` once.

**Step 4: Run tests; commit**

```bash
git add monitor/logging_util.py monitor/run.py tests/test_logging_util.py
git commit -m "feat(monitor): add local run logging"
```

---

## Task 3: Windows 启动器与任务计划脚本

**Files:**
- Create: `windows/run.bat`
- Create: `windows/config.example.json`
- Create: `windows/install-task.bat`
- Create: `windows/uninstall-task.bat`
- Create: `windows/README.txt`

**Interfaces:**
- `run.bat` 接受 `--send` / `--dry-run` / `--test-notification`，使用 `%APP_DIR%python\python.exe -m monitor.run %*`
- `install-task.bat` 创建任务名 `LawWatch Monitor`，每 30 分钟调用 `run.bat --send`

**Step 1: Write files**

`windows/run.bat`:

```bat
@echo off
setlocal
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"
set "LAWWATCH_CONFIG=%APP_DIR%config.json"
set "LAWWATCH_DATA_DIR=%APP_DIR%data"
"%APP_DIR%python\python.exe" -m monitor.run %*
```

`windows/config.example.json`:

```json
{
  "smtp_user": "",
  "smtp_auth_code": "",
  "email_to": "",
  "wecom_webhook": "",
  "schedule_minutes": 30
}
```

`windows/install-task.bat`:

```bat
@echo off
setlocal
set "APP_DIR=%~dp0"
set "PY=%APP_DIR%python\python.exe"
set "RUN=%APP_DIR%run.bat"
set "CONFIG=%APP_DIR%config.json"
set "DATA=%APP_DIR%data"
if not exist "%PY%" echo Error: python\python.exe not found & exit /b 1
if not exist "%RUN%" echo Error: run.bat not found & exit /b 1
if not exist "%CONFIG%" copy "%APP_DIR%config.example.json" "%CONFIG%" >nul
if not exist "%DATA%" mkdir "%DATA%"
schtasks /create /f /tn "LawWatch Monitor" /tr "\"%RUN%\" --send" /sc MINUTE /mo 30 /it
echo Task "LawWatch Monitor" installed.
echo Fill config.json before first run.
```
**Note:** 任务用 `/IT` 以交互模式创建：仅在创建者登录期间运行、不保存密码、不提示输入密码。`install-task.bat` 还校验包内 Python 依赖可导入、`config.json` 为合法 JSON，且 `smtp_user`/`smtp_auth_code`/`email_to` 要么全部填写、要么全部留空（空配置允许首次基线运行）。


`windows/uninstall-task.bat`:

```bat
@echo off
schtasks /delete /f /tn "LawWatch Monitor"
echo Task removed. config.json and data were kept.
```

`windows/README.txt` contains install, config, SmartScreen, uninstall, and update instructions.

**Step 2: Validate scripts manually**

```powershell
cmd /c "call windows\run.bat --dry-run"
```

**Step 3: Commit**

```bash
git add windows
git commit -m "feat(windows): add portable launcher and task scheduler scripts"
``n
## Task 4: 便携 Python Windows 打包

**Files:**
- Create: `scripts/prepare-windows-portable.ps1`
- Create: `win-build/README.txt`

**Interfaces:**
- Build output: `dist/LawWatchMonitor/`
- Layout: `python\`、`monitor\`、`run.bat`、`config.example.json`、`install-task.bat`、`uninstall-task.bat`、`data\`

**Step 1: Write build script**

```powershell
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
```

**Step 2: Run build on a Windows dev machine**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare-windows-portable.ps1
```

**Step 3: Smoke test**

```powershell
.\dist\LawWatchMonitor\run.bat --dry-run
```

**Step 4: Commit build/config files**

```bash
git add scripts/prepare-windows-portable.ps1 win-build/README.txt
git commit -m "feat(windows): add portable Python packaging pipeline"
``n
## Task 5: README 与自托管 Runner 验证说明

**Files:**
- Modify: `README.md`
- Create: `docs/windows-deployment.md`
- Create: `docs/domestic-runner-checklist.md`

**Requirements:**
- README link to both deployment docs.
- Windows doc covers: config, first run baseline, task install/uninstall, SmartScreen, update and migration.
- Runner checklist covers: purchase/choose server, register runner, verify online, first manual run, check state/logs.

**Step 1: Write docs; Step 2: Validate links; Step 3: Commit**

```bash
git add README.md docs/windows-deployment.md docs/domestic-runner-checklist.md
git commit -m "docs(monitor): add Windows and domestic runner deployment guides"
```

---

## Task 6: 最终验证

**Commands:**

```bash
python -m pytest -q
python -m compileall monitor
python -c "import pathlib,json; json.loads(pathlib.Path('monitor/state.json').read_text(encoding='utf-8'))"
python -c "import pathlib,yaml; yaml.safe_load(pathlib.Path('.github/workflows/monitor.yml').read_text(encoding='utf-8'))"
```

**Acceptance:**
- 全部测试通过。
- `--dry-run` 不修改 `data/state.json`。
- `--test-notification` 可用本地 `config.json` 发送测试。
- Windows 绿色版可运行 `install-task.bat` 并在干净 Windows 上创建任务；打包版本不依赖 Playwright，动态站点使用 HTTP 降级。
- 自托管 Runner 文档完成；服务器一旦注册即可运行。




