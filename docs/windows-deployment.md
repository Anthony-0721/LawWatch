# Windows 便携版部署指南

本文说明如何把 LawWatch Monitor 打包为 Windows 绿色版（便携 Python 文件夹），部署到目标电脑并注册为计划任务。目标机器**无需安装 Python**，程序使用包内自带的便携 Python 运行时。

## 前置条件

目标机器（运行监控的电脑）：

- 64 位 Windows 10 / Windows 11，或 Windows Server 2019 / 2022；
- 无需安装 Python；
- 能访问需要监测的 `.gov.cn` 站点以及企业微信 / 邮件服务器；
- 任务仅在创建该任务时的 Windows 用户登录期间运行，用户注销后不运行。

构建机器（打包用，只需一台 Windows 开发机）：

- 64 位 Windows，且安装了真实的 64 位 Python 3.x（python.org 完整安装包，不是 Microsoft Store 占位程序），`python` 命令可用；
- 能联网下载 pip 依赖；
- 仓库中已包含 `monitor/`、`windows/`、`requirements.txt` 与打包脚本。

## 目录结构

构建产出的便携包 `dist\LawWatchMonitor\` 结构如下：

```text
LawWatchMonitor\
├── python\                 便携 Python 运行时（含全部依赖）
├── monitor\                监测程序
├── run.bat                 启动脚本
├── config.example.json     配置模板
├── config.json             部署后填写（首次由 install-task.bat 自动生成）
├── install-task.bat        注册计划任务
├── uninstall-task.bat      删除计划任务
├── README.txt              包内说明
└── data\                   运行数据
    ├── sites.csv           站点清单
    ├── state.json          去重状态与基线标记
    └── logs\
        └── monitor.log     日志（按天轮转，保留最近 30 天）
```

## 构建便携包

在 Windows 开发机上，于仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare-windows-portable.ps1
```

脚本会先校验 `python` 指向真实安装目录（拒绝 Microsoft Store 的 0 字节占位程序），删除旧的 `dist\LawWatchMonitor\`，然后把 Python 安装目录整体复制到包内、安装 `requirements.txt` 依赖、复制监控代码与脚本，并生成全新的 `data\`（`sites.csv`、空白的 `state.json`、`logs\`）。构建前请确认 `python --version` 与 `python -m pip --version` 正常。

构建完成后冒烟验证：

```powershell
.\dist\LawWatchMonitor\run.bat --dry-run
```

预期输出抓取统计，且不写入 `data\state.json`。

## 部署到目标机器

1. 把整个 `dist\LawWatchMonitor\` 文件夹复制到目标机器的固定目录，例如 `C:\LawWatchMonitor`（也可以是 `D:\LawWatchMonitor` 等任意可写路径）。建议不要放在 `C:\Program Files` 等需要管理员权限的位置。
2. 确认包内存在 `python\python.exe`、`monitor\` 与 `run.bat`。

## 填写配置

首次双击 `install-task.bat` 时，若 `config.json` 不存在会自动从 `config.example.json` 复制生成；也可以手动复制后再编辑。用文本编辑器打开 `config.json`：

```json
{
  "smtp_user": "",
  "smtp_auth_code": "",
  "email_to": "",
  "wecom_webhook": "",
  "schedule_minutes": 30
}
```

| 字段 | 说明 |
| --- | --- |
| `smtp_user` | 发件邮箱地址（如 QQ 邮箱） |
| `smtp_auth_code` | SMTP 授权码 |
| `email_to` | 收件人邮箱地址 |
| `wecom_webhook` | 企业微信群机器人 Webhook 地址 |
| `schedule_minutes` | 记录值，保持 30 即可 |

企业微信与邮件至少配置一种，否则发现新公文时无法通知。任务间隔由 `install-task.bat` 固定为 30 分钟，`schedule_minutes` 只是记录值。`config.json` 包含真实凭据，不要提交到 Git，建议限制为仅当前用户可读。

## 首次运行（建立基线）

1. 先运行 `run.bat --dry-run`：只抓取与检测，不发送通知、不写入 `data\state.json`，用于验证程序可用。
2. 再运行 `run.bat --send` 完成首次真实运行。**首次成功的运行只建立基线、不发通知**；之后每轮发现新增公文才会通知。如果所有站点都失败，基线不会被标记，后续运行会继续重试。
3. 检查 `data\state.json` 中 `baselined` 是否为 `true`，并查看 `data\logs\monitor.log`。
4. 可用 `run.bat --test-notification` 发送一条测试通知，验证通知渠道。

## 注册计划任务

双击 `install-task.bat`。脚本会创建名为 `LawWatch Monitor` 的任务，以当前用户身份每 30 分钟执行一次 `run.bat --send`。安装过程中 SchTasks 可能提示输入该用户的登录密码，并把任务凭据交给 Windows 管理。

验证任务：

```bat
schtasks /query /tn "LawWatch Monitor"
```

任务行为说明：

- 任务仅在创建该任务时的 Windows 用户登录期间运行，用户注销后不运行；安装过程中 SchTasks 可能提示输入该用户的登录密码，并把任务凭据交给 Windows 管理；
- 每 30 分钟触发一次；如需修改间隔，编辑 `install-task.bat` 中的 `/mo` 值后重新运行；
- 错过计划开始时间（例如关机、未登录）后是否补跑，由任务计划程序中该任务的“错过计划开始后尽快启动”设置决定，可在 `任务计划程序 → LawWatch Monitor → 属性 → 设置` 中确认或调整。

## SmartScreen 提示

便携 Python 文件夹不需要代码签名。如果 Windows 拦截 `run.bat` 或 `install-task.bat`，请先确认文件确实来自可信的发布包（核对来源与内容），再点击 **更多信息 → 仍要运行**。不要对来源不明的脚本执行该操作。

如果整个文件夹是从浏览器下载的 zip 解压而来、被标记为“来自另一台计算机”，可先解除锁定再运行：右键压缩包 → 属性 → 勾选“解除锁定”，或在 PowerShell 中对包内脚本执行 `Unblock-File`。

## 卸载

双击 `uninstall-task.bat` 删除计划任务。`config.json` 与 `data\`（基线状态、站点清单、日志）会被保留。如需彻底清除，手动删除整个 `LawWatchMonitor` 文件夹。

## 更新与迁移

手动更新发布包时**保留 `config.json` 与 `data\`，只替换代码**：

1. 双击 `uninstall-task.bat` 停用旧任务；
2. 用新发布包覆盖 `monitor\` 与 `run.bat`（`config.example.json`、`install-task.bat`、`uninstall-task.bat`、`README.txt` 可同步更新；如站点清单有变化，同步替换 `data\sites.csv`）；
3. 保留原 `config.json` 与 `data\`（其中含基线 `state.json`、站点清单与日志）；
4. 重新双击 `install-task.bat` 注册任务，再运行 `run.bat --dry-run` 验证。

从 GitHub Actions 等其他部署方式迁移：把已有的 `monitor/state.json` 与站点清单分别放入新包的 `data\state.json` 与 `data\sites.csv`，填写 `config.json`，再按上述步骤注册任务。

## 注意事项

- 便携包不内置 Chromium 浏览器，动态站点在浏览器不可用时自动降级为普通 HTTP 抓取（会在输出/日志中提示）；
- 日志按天轮转并保留最近 30 天，去重状态保留最近 30 天；
- Windows 版默认不发送失败报警；每轮运行的结果摘要与各站点失败会写入 `data\logs\monitor.log`，站点错误同时记录在 `data\state.json` 的 `errors` 中；通知失败时下一轮自动重试；
- 发布/复制前检查包内不含 `config.json` 或任何真实凭据。
