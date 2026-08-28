# 企业微信与国内 Runner 交付清单

> 适用仓库：`Anthony-0721/LawWatch`（交付远程为 `anthony`）
> 当前版本：`main` 已包含最新实现，状态文件由 GitHub Actions 自动提交回仓库
> 更新日期：2026-08-28

## 当前状态

- [x] `SMTP_USER` 已配置
- [x] `SMTP_AUTH_CODE` 已配置
- [x] `EMAIL_TO` 已配置
- [ ] `WECOM_WEBHOOK` 尚未配置
- [ ] 国内自托管 Runner 尚未注册/上线
- [ ] 尚未在 GitHub Actions 上验证企业微信测试通知
- [ ] 尚未完成国内网络环境下的首次真实基线运行

## A. 企业微信通知

### A1. 创建群机器人

1. 打开企业微信客户端，进入目标通知群；
2. 点击群设置 → `群机器人` → `添加机器人`；
3. 填写机器人名称（例如“LawWatch 公告监控”），创建后复制 Webhook 地址；
4. Webhook 地址通常形如：

```text
https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxxxxxxxxxx
```

5. 将复制到的地址暂存在本地安全位置，不要写入仓库、聊天记录或日志。

### A2. 配置 GitHub Actions Secret

1. 在浏览器打开 `https://github.com/Anthony-0721/LawWatch/settings/secrets/actions`；
2. 点击 `New repository secret`；
3. 填写：

   - Name：`WECOM_WEBHOOK`
   - Value：A1 中复制的完整 Webhook 地址

4. 保存后建议使用命令行确认已存在：

```bash
gh secret list -R Anthony-0721/LawWatch
```

5. 确认 `WECOM_WEBHOOK` 出现在列表中；不要把真实 Webhook 值显示在聊天、Issue 或提交信息中。

### A3. 配置 Windows 便携版（如同时交付甲方电脑）

1. 打开便携包根目录的 `config.json`；
2. 把企业微信 Webhook 填入 `wecom_webhook` 字段，例如：

```json
{
  "smtp_user": "发件邮箱",
  "smtp_auth_code": "SMTP授权码",
  "email_to": "收件邮箱",
  "wecom_webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxxxxxxxxxx",
  "schedule_minutes": 30
}
```

3. 保存后运行：

```bat
run.bat --test-notification
```

4. 确认通知群收到一条测试消息，同时 QQ 邮箱收到测试邮件；
5. 不要提交 `config.json`，更新代码时需保留该文件。

### A4. 验证 GitHub Actions 通知

1. 打开 `Actions` → `Monitor provincial legal notices`；
2. 点击 `Run workflow`；
3. 勾选 `test_notification` 后运行；
4. 检查本轮运行结果为绿色；
5. 检查企业微信通知群和 QQ 邮箱是否收到测试通知；
6. 本轮只发送测试通知，不会抓取、不会修改 `monitor/state.json`。

### A5. 企业微信常见失败排查

| 现象 | 处理 |
| --- | --- |
| 企业微信未收到消息 | 确认 Webhook 是否来自同一企业、机器人是否仍存在、是否复制完整 |
| 返回 `93000` 等错误 | 重新复制 Webhook 并更新 Secret，然后重跑测试通知 |
| GitHub Actions 日志显示所有通知失败 | 检查 Secret 是否包含换行/空格，必要时删除后重新添加 |
| 只有邮件成功、企业微信失败 | 先修企业微信；`WECOM_WEBHOOK` 不应与任何仓库文件或日志混在一起 |

## B. 国内自托管 Runner

### B1. 前置确认

- [ ] 已准备国内 Linux 服务器（建议 Ubuntu 22.04+，2 核 2GB 以上）；
- [ ] 服务器可访问 `github.com`、`objects.githubusercontent.com` 和 PyPI；
- [ ] 服务器可访问目标 `.gov.cn` 网站；
- [ ] 账号对 `Anthony-0721/LawWatch` 有仓库管理权限；
- [ ] 已确认 `anthony/main` 包含最新实现，Runner 脚本存在于 `scripts/setup-domestic-runner.sh`；
- [ ] 已确认工作流使用 `runs-on: [self-hosted, linux, x64, lawwatch-domestic]`；
- [ ] 已决定 Runner 服务运行账号及是否有 `sudo` 权限（用于安装 Chromium 依赖）。

### B2. 安装系统依赖

在服务器上执行：

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip curl
```

### B3. 获取 Runner 注册 Token

1. 打开 `https://github.com/Anthony-0721/LawWatch/settings/actions/runners`；
2. 点击 `New self-hosted runner`；
3. 选择 **Linux**、**x64**；
4. 复制页面显示的注册 Token；
5. Token 是临时值，用完即失效，不要写入仓库。

### B4. 注册并启动 Runner

可使用仓库脚本执行：

```bash
curl -fsSL \
  https://raw.githubusercontent.com/Anthony-0721/LawWatch/main/scripts/setup-domestic-runner.sh \
  -o /tmp/setup-domestic-runner.sh

sudo env RUNNER_TOKEN="粘贴注册token" \
  bash /tmp/setup-domestic-runner.sh
```

脚本默认会：

- Runner 名称：`lawwatch-domestic`
- 标签：`self-hosted,linux,x64,lawwatch-domestic`
- 安装目录：`$HOME/actions-runner`
- 以 root 运行时安装为系统服务并启动
- 以普通用户运行时只完成配置，需要手动执行 `./run.sh`

如需覆盖默认值，在命令前设置：

```bash
export RUNNER_NAME="lawwatch-domestic"
export RUNNER_LABELS="self-hosted,linux,x64,lawwatch-domestic"
export RUNNER_DIR="$HOME/actions-runner"
export REPO_OWNER="Anthony-0721"
export REPO_NAME="LawWatch"
```

### B5. 确认 Runner 在线

1. 打开 `Settings → Actions → Runners`；
2. 确认 `lawwatch-domestic` 状态为 `Idle`；
3. 确认标签与工作流 `runs-on` 完全一致；
4. 服务器侧检查服务：

```bash
./svc.sh status
# 或
systemctl status actions.runner.*
```

5. 若显示离线：检查服务器 DNS、出站网络、防火墙和安全组，以及 Runner 进程是否存活。

### B6. 首次手动测试通知

1. 打开 `Actions` → `Monitor provincial legal notices`；
2. 点击 `Run workflow`；
3. 勾选 `test_notification`；
4. 确认运行被分配到 `lawwatch-domestic`；
5. 确认企业微信和邮箱收到测试通知。

### B7. 建立真实基线

1. 再次点击 `Run workflow`，这次**不勾选** `test_notification`；
2. 观察运行预计耗时约 3–5 分钟，不要因为较慢而重复触发；
3. 成功后打开 `monitor/state.json`，确认：
   - `baselined: true`
   - `documents` 数量大于 0
   - `errors` 数量明显低于境外 Runner 的结果
4. 如果有少数站点仍失败，先在服务器上直接访问对应站点，确认是网络限制还是站点结构变化；
5. 首次成功运行只建立基线、不发通知；此后每轮只通知新增 URL。

### B8. 确认定时运行与状态回写

- [ ] 工作流保持启用，`schedule` 为每 30 分钟；
- [ ] 等待至少一轮定时运行，确认 Actions 中出现新的运行记录；
- [ ] 运行结束后 `monitor/state.json` 被自动提交回 `main`；
- [ ] `Settings → Actions → General → Workflow permissions` 允许读写（现有 workflow 已声明 `contents: write`）；
- [ ] 不再依赖 GitHub 托管 Runner 执行该工作流。

### B9. Runner 日常维护

- [ ] 服务器重启后确认 `actions.runner.*` 服务自动启动；
- [ ] 每季度或 GitHub 提示升级时重跑安装脚本更新 Runner 版本；
- [ ] 定期检查磁盘空间和内存；
- [ ] 更换服务器后重新获取 Token 并注册，旧 Runner 先下线；
- [ ] 不要把 Runner Token、Webhook 或 SMTP 凭据写入仓库。

## C. 交付前总体验收

- [ ] 企业微信测试通知已在 GitHub Actions 上成功；
- [ ] QQ 邮箱测试通知仍在 GitHub Actions 上成功；
- [ ] 国内 Runner 状态为 `Idle`；
- [ ] 国内 Runner 上的真实基线运行成功，`baselined=true`；
- [ ] 至少一轮定时运行成功，且状态成功回写 `main`；
- [ ] 若交付 Windows 便携版：已在干净 Windows 10/11 或 Server 2019/2022 上完成 `run.bat --dry-run`、`install-task.bat` 和 `schtasks /query /tn "LawWatch Monitor"`；
- [ ] 已确认 `config.json`、`.env`、真实 Webhook、SMTP 授权码未进入 Git；
- [ ] 已把本清单提交到交付远程并同步 `main`。

## D. 建议的验收证据

- GitHub Actions 运行页面截图或 `gh run view` 输出；
- 企业微信通知群收到的测试消息；
- QQ 邮箱收到的测试邮件；
- `monitor/state.json` 中 `baselined`、`documents`、`errors` 的值；
- Runner 在线状态截图或 `systemctl status` 输出；
- Windows 便携版任务查询输出。
