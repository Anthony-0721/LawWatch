# LawWatch Monitor

定时抓取省级司法厅/公检法公示公告，检测到新增公文后通过企业微信和邮件通知。

支持以下部署方式，可根据实际环境任选其一：

- **云服务器直部署（推荐给甲方长期运行）**：不依赖 GitHub Actions，使用 systemd timer，服务器重启后自动恢复。
- **GitHub Actions + 国内自托管 Runner**：通过 GitHub 定时调度，适合已有 GitHub 仓库和国内服务器的场景。
- **Windows 便携版**：甲方电脑免安装运行，每 30 分钟执行一次。

## 1. 云服务器直部署（推荐）

把整个程序直接部署到国内 Linux 服务器，不需要 GitHub Actions/自托管 Runner。

```bash
git clone https://github.com/Anthony-0721/LawWatch.git /tmp/lawwatch-src
cd /tmp/lawwatch-src
sudo bash scripts/install-linux-direct.sh
sudoedit /etc/lawwatch/config.json
```

随后 `systemd` 会每 30 分钟自动执行一次，服务器重启后也可以补跑错过的任务。

详见 [docs/linux-direct-deployment.md](docs/linux-direct-deployment.md)。

## 2. GitHub Actions 部署

在 GitHub 仓库的 `Settings → Secrets and variables → Actions` 添加以下 Secrets：

- `SMTP_USER`：发件邮箱地址（如 QQ 邮箱）
- `SMTP_AUTH_CODE`：SMTP 授权码
- `EMAIL_TO`：收件人邮箱地址
- `WECOM_WEBHOOK`：企业微信群机器人 Webhook 地址

在 GitHub Actions 手动运行一次 `Monitor provincial legal notices`，首次“成功”运行只建立基线，不发通知；之后每 30 分钟自动运行，发现新增公文后推送企业微信并发送邮件。

如果 GitHub 托管 Runner 无法访问 `.gov.cn`，请按 [docs/self-hosted-runner.md](docs/self-hosted-runner.md) 注册国内自托管 Runner，并按 [docs/domestic-runner-checklist.md](docs/domestic-runner-checklist.md) 逐项验证。

## 3. Windows 便携版（甲方本机）

如需在甲方 Windows 电脑上免安装运行，先在 Windows 开发机上执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare-windows-portable.ps1
```

然后参考 [docs/windows-deployment.md](docs/windows-deployment.md) 把 `dist\LawWatchMonitor` 部署到目标电脑，并注册计划任务。

## 4. 通知渠道

通知渠道至少配置一种：

- 邮件（QQ SMTP / `smtp_user`、`smtp_auth_code`、`email_to`）
- 企业微信群机器人（`wecom_webhook`）

可用以下命令验证通知：

```bash
python -m monitor.run --test-notification
```

Windows 便携版对应为：

```bat
run.bat --test-notification
```

## 5. 本地测试

```bash
python -m monitor.run --dry-run --max-pages 1
```

只抓取与检测，不发送通知、不写入状态文件。

## 6. 抓取兼容性

程序已做如下兼容处理，用于提高对政府网站的访问成功率：

- 兼容旧 TLS / 无效证书（部分 `.gov.cn` 站点会拒绝新版 OpenSSL）；
- 请求失败时自动回退到系统 `curl`；
- 对返回 403/412 的站点先访问首页获取 Cookie，再重试；
- 不再永久缓存失效子栏目地址，避免反复报错；
- 默认每个站点最多抓取 8 页、最多 5 个并发线程、请求超时 10 秒、失败重试 2 次。

如果个别站点仍报错，通常是该网站本身的反爬策略（如 HTTP 412）或临时网络问题，不影响整体监控。

## 7. 交付前检查

企业微信配置、国内 Runner 注册、Windows 便携版部署的完整可打勾清单见 [docs/delivery-checklist.md](docs/delivery-checklist.md)。