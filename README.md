# LawWatch Monitor

定时抓取省级司法厅/公检法公示公告，检测到新增公文后通过企业微信和邮件通知，并通过 GitHub Actions 每 30 分钟自动运行。

## 部署与使用

1. 在 GitHub 仓库的 `Settings → Secrets and variables → Actions` 添加以下 Secrets：
   - `SMTP_USER`：发件邮箱地址（如 QQ 邮箱）
   - `SMTP_AUTH_CODE`：SMTP 授权码
   - `EMAIL_TO`：收件人邮箱地址
   - `WECOM_WEBHOOK`：企业微信群机器人 Webhook 地址
2. 在 GitHub Actions 手动运行一次 `Monitor provincial legal notices`；首次运行只建立基线，不发通知。
3. 让工作流保持启用，每 30 分钟自动运行；发现新增公文后推送企业微信并发送邮件。
4. 本地测试：`python -m monitor.run --dry-run`。
5. 本地测试完整通知：`python -m monitor.run --send`（需要先设好环境变量）。
