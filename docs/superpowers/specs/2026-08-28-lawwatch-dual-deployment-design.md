# LawWatch 双部署方案设计

**日期：** 2026-08-28  
**状态：** 待用户审阅  
**目标：** 在保留国内自托管 GitHub Actions Runner 方案的同时，提供一个可在甲方 Windows 电脑上免安装运行的监控版本。

## 1. 需求背景

当前系统已具备省级司法厅/政务网站公文监测能力，包括抓取、去重、30 天状态保存、QQ 邮箱通知、企业微信通知和 GitHub Actions 定时运行。实际运行显示 GitHub 境外 Runner 对部分 `.gov.cn` 网站不可达，因此需要：

- 方案 A：国内服务器/自托管 GitHub Actions Runner，适合长期自动化；
- 方案 B：本机 Windows 计划任务版，适合甲方电脑或暂时无服务器的环境。

两个方案共享同一套监控核心逻辑，仅运行环境和配置方式不同。

## 2. 已确认决策

1. Windows 版以绿色版文件夹形式交付，包含便携 Python 运行时、监控代码、配置模板、站点 CSV、状态文件和安装脚本。
2. Windows 版由任务计划程序（Task Scheduler）触发，登录后自动运行，每 30 分钟一次；错过计划时间时尽量补跑。
3. Windows 版使用本地 `config.json` 保存 SMTP、收件邮箱和企业微信 Webhook，不写入 Git、不随包提供真实凭据。
4. Windows 版首次运行重新建立基线，不发送历史公文通知。
5. 程序数据放在绿色版目录下的 `data/` 子目录：状态、站点清单、日志；运行入口是 `run.bat` 调用的便携 `python\\python.exe`。
6. 第一版采用便携 Python 文件夹，不需要代码签名；如甲方要求，可在后续再处理签名。
7. 目标系统为 64 位 Windows 10/11 和 Windows Server 2019/2022。
8. 更新方式为手动替换绿色版文件，保留 `config.json` 和 `data/`。
9. Windows 版默认不发送失败报警，只在日志中记录；通知失败时下一次运行重试。
10. 自托管 Runner 方案继续使用现有 GitHub Actions 工作流，已标记为 `self-hosted,linux,x64,lawwatch-domestic`。

## 3. 共享架构

```text
统一监测核心
  ├── sites.csv / config
  ├── fetcher (HTTP / Browser)
  ├── extractor (公文候选)
  ├── discovery (栏目发现)
  ├── state (30 天去重)
  ├── notifier (QQ SMTP + WeCom)
  └── scheduler (GitHub Actions 或 Windows Task Scheduler)
```

两种模式只在以下位置不同：

| 项目 | 自托管 Runner | Windows 计划任务 |
|---|---|---|
| Python 依赖 | GitHub Actions/Runner 安装 | 便携 Python 运行时文件夹 |
| 配置文件 | GitHub Actions Secrets | 本地 `config.json` |
| 状态文件 | 提交回 GitHub `main` | 本地 `data/state.json` |
| 定时 | GitHub Actions schedule | Windows Task Scheduler |
| 日志 | Actions logs | `data/logs/` |
| 通知回调 | 测试通知模式 + 真实公文 | 同一套 notifier |

## 4. Windows 绿色版目录

```text
LawWatchMonitor\
├── python\
│   └── python.exe
├── monitor\
├── run.bat
├── config.example.json
├── config.json               ← 部署后填写
├── install-task.bat
├── uninstall-task.bat
├── README.txt
└── data\
    ├── sites.csv
    ├── state.json
    └── logs\
        ├── monitor.log
        └── monitor.log.1
```

`config.json` 字段：

```json
{
  "smtp_user": "",
  "smtp_auth_code": "",
  "email_to": "",
  "wecom_webhook": "",
  "schedule_minutes": 30
}
```

## 5. Windows 任务计划行为

- 任务名：`LawWatch Monitor`
- 触发：登录后开始，间隔 30 分钟，重复持续时间 24 小时
- 启动方式：使用当前用户，隐藏窗口运行
- 设置：错过计划开始时间后尽快启动
- 日志：每轮追加到 `data/logs/monitor.log`
- 清理：日志和状态只保留最近 30 天

`install-task.bat` 负责：

1. 检查程序路径和 `config.json` 是否有效；
2. 检测 Python 依赖是否已打包（无需安装 Python）；
3. 调用 `schtasks` 创建任务；
4. 输出启动说明和 SmartScreen 处理提示；
5. 不修改系统服务、不写入注册表其他位置。

`uninstall-task.bat` 删除任务，不删除 `config.json` 和 `data/`。

## 6. 自托管 Runner 兼容性

- 保持现有 `.github/workflows/monitor.yml`；
- `runs-on` 已改为 `[self-hosted, linux, x64, lawwatch-domestic]`；
- `docs/self-hosted-runner.md` 和 `scripts/setup-domestic-runner.sh` 已提供；
- 国内服务器上线后，Runner 注册成功即可恢复定时运行；
- Windows 版与 Runner 版使用同一套 `sites.csv` 和维护规则。

## 7. 状态与数据迁移

- Windows 版首次运行创建新的 `state.json`，不迁移当前 GitHub 状态；
- 如果未来需要从 GitHub 状态迁移，只复制 `monitor/state.json` 到 `data/state.json`；
- `sites.csv` 可以在两个版本间复制，当前共 31 行。

## 8. 安全与运维

- 不把 SMTP 授权码、企业微信 Webhook 写入 Git；
- Windows 版 `config.json` 建议限制为当前用户可读；
- 不安装系统服务，不依赖网络下载；
- 绿色版内不包含任何真实凭据；
- 手动更新时保留 `config.json` 和 `data/`。

## 9. 验证方式

1. 单元测试全部通过；
2. 本地以 `python -m monitor.run --dry-run` 验证抓取、去重和日志；
3. 使用测试通知模式验证邮箱/企业微信；
4. 使用 `scripts/prepare-windows-portable.ps1` 生成便携目录后，在一台干净 Windows 10/11 或 Server 上解压并运行 `install-task.bat`；
5. 验证任务计划每 30 分钟触发、日志写入、邮箱通知不重复；
6. 自托管 Runner 上线后，手动运行工作流验证国内站点覆盖。

## 10. 后续扩展

- 商业代码签名证书；
- 企业微信/邮件失败报警开关；
- 自动更新下载和签名校验；
- 多台甲方电脑批量部署。


