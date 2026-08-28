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

## 抓取预算与超时

工作流正常运行时执行 `python -m monitor.run --send --max-pages 8`，任务超时上限为 30 分钟。默认抓取预算如下：

- 站点之间最多 5 个并发线程（可用 `--max-workers N` 或环境变量 `MONITOR_MAX_WORKERS` 覆盖，且不会超过站点总数）；
- 每个站点最多抓取 8 页；
- 普通 HTTP 请求超时 10 秒、失败最多重试 1 次；
- 动态站点浏览器页面加载超时 20 秒。

即使压缩了抓取预算，GitHub 托管 Runner 仍可能被部分 `.gov.cn` 网站限流或拒绝；如果基线长期无法建立，请改用中国大陆的自托管 Runner（见下文）。

## 验证通知送达

在 GitHub Actions 打开 `Monitor provincial legal notices` 工作流，点击 **Run workflow**，勾选 `test_notification` 后运行。测试模式只发送一条样例通知，不抓取、不修改基线、不写入 `monitor/state.json`；首次成功即说明已配置的通知渠道（企业微信/邮件）可以正常送达。

## 注意：GitHub 托管 Runner 与国内政府网站

GitHub 托管的公共 Runner 出口 IP 可能被部分中国政府网站限流、超时或直接拒绝访问。首次真实运行后请检查工作流日志和 `monitor/state.json`：如果大量站点出现在 `errors` 中且 `baselined` 始终为 `false`，说明抓取被网络侧阻断，而不是程序缺陷。此时建议：

- 使用位于中国大陆的自托管 Runner；
- 或为运行环境配置可用的网络代理。

在完成一次“多数站点成功”的基线运行并人工核对日志之前，不要仅凭定时工作流判断监测是否生效。

## Windows 本机部署（无需安装 Python）

如需在甲方 Windows 电脑上免安装运行，可按 [docs/windows-deployment.md](docs/windows-deployment.md) 打包便携版并注册计划任务：登录后每 30 分钟运行，配置保存在本地 `config.json`，首次运行只建立基线、不发通知。

## 国内自托管 Runner

如果 GitHub Hosted Runner 无法访问 .gov.cn，请按 [docs/self-hosted-runner.md](docs/self-hosted-runner.md) 在国内服务器注册自托管 Runner。工作流已使用标签 self-hosted,linux,x64,lawwatch-domestic。

注册完成后的逐项验证（Runner 在线、手动触发、核对状态与 Actions 日志）见 [docs/domestic-runner-checklist.md](docs/domestic-runner-checklist.md)。

