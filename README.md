# LawWatch Monitor

定时抓取省级司法厅/公检法公示公告，检测到新增公文后通过企业微信和邮件通知，并通过 GitHub Actions 每 30 分钟自动运行。

## 部署与使用

1. 在 GitHub 仓库的 `Settings → Secrets and variables → Actions` 添加以下 Secrets：
   - `SMTP_USER`：发件邮箱地址（如 QQ 邮箱）
   - `SMTP_AUTH_CODE`：SMTP 授权码
   - `EMAIL_TO`：收件人邮箱地址
   - `WECOM_WEBHOOK`：企业微信群机器人 Webhook 地址
2. 在 GitHub Actions 手动运行一次 `Monitor provincial legal notices`；首次“成功”运行只建立基线，不发通知（如果所有站点都失败，基线不会被标记，后续运行会重试）。
3. 让工作流保持启用，每 30 分钟自动运行；发现新增公文后推送企业微信并发送邮件。如果本轮新增内容但两条通知渠道全部失败，程序会以非零状态退出、不提交去重状态，下一轮自动重试同一批内容，避免漏报。
4. 本地测试：`python -m monitor.run --dry-run --max-pages 1`（只抓取与检测，不发送通知、不写入 `monitor/state.json`）。
5. 本地测试完整通知：`python -m monitor.run --send`（需要先设好环境变量）。

## 注意：GitHub 托管 Runner 与国内政府网站

GitHub 托管的公共 Runner 出口 IP 可能被部分中国政府网站限流、超时或直接拒绝访问。首次真实运行后请检查工作流日志和 `monitor/state.json`：如果大量站点出现在 `errors` 中且 `baselined` 始终为 `false`，说明抓取被网络侧阻断，而不是程序缺陷。此时建议：

- 使用位于中国大陆的自托管 Runner；
- 或为运行环境配置可用的网络代理。

在完成一次“多数站点成功”的基线运行并人工核对日志之前，不要仅凭定时工作流判断监测是否生效。