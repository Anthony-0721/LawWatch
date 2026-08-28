# 国内自托管 Runner 部署清单

本清单用于在国内 Linux 服务器上注册 GitHub Actions 自托管 Runner，让 `Monitor provincial legal notices` 工作流在境内主机运行，避免境外 Runner 访问部分 `.gov.cn` 站点被限流或拒绝。背景与注册说明见 [self-hosted-runner.md](self-hosted-runner.md)。

## 1. 前置条件

- 一台可联网的国内 Linux 服务器（可选用任一国内云厂商的轻量应用服务器），建议 Ubuntu 22.04+、2 核 2GB 以上；
- 服务器出站可访问 `github.com`（Runner 需从 GitHub 拉取任务）及目标 `.gov.cn` 站点；
- 对 `Anthony-0721/LawWatch` 仓库有管理权限，用于生成 Runner 注册 token；
- 已安装 `git`、`python3`、`curl`（`setup-domestic-runner.sh` 会检查这三个命令）。

## 2. 获取注册 token

1. 打开仓库 `Settings → Actions → Runners → New self-hosted runner`；
2. 选择 Linux x64，复制注册 token。

Token 是临时值，用完即失效；不要写进仓库或提交到 Git。

## 3. 安装依赖并运行注册脚本

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip curl
```

把仓库中的 `scripts/setup-domestic-runner.sh` 拿到服务器上执行（克隆仓库或直接下载均可）：

```bash
# 方式一：克隆仓库
git clone https://github.com/Anthony-0721/LawWatch.git
cd LawWatch

# 方式二：直接下载脚本
curl -fsSL https://raw.githubusercontent.com/Anthony-0721/LawWatch/main/scripts/setup-domestic-runner.sh -o /tmp/setup-domestic-runner.sh
```

以 root 运行并把 token 显式传入（`sudo` 默认不会继承 shell 里的环境变量，请用 `env` 传入）：

```bash
sudo env RUNNER_TOKEN="粘贴注册token" bash scripts/setup-domestic-runner.sh
```

脚本默认：Runner 名称 `lawwatch-domestic`、标签 `self-hosted,linux,x64,lawwatch-domestic`、版本 2.327.1、安装目录 `$HOME/actions-runner`；随后下载 Runner 压缩包、以 unattended 模式注册，并在 root 下通过 `svc.sh` 安装并启动为系统服务。需要覆盖仓库/名称/目录等默认值时，可用 `REPO_OWNER`、`REPO_NAME`、`RUNNER_NAME`、`RUNNER_LABELS`、`RUNNER_DIR` 环境变量调整。

以普通用户运行也可以：脚本会完成配置但不安装服务，按提示在终端运行 `./run.sh` 保持 Runner 存活。

## 4. 确认 Runner 在线

1. 回到 GitHub 仓库 `Settings → Actions → Runners`，确认 `lawwatch-domestic` 状态为 **Idle**（空闲待命）；
2. 标签应包含 `self-hosted,linux,x64,lawwatch-domestic`，与工作流 `runs-on` 匹配；
3. 服务器侧可用 `./svc.sh status`（或 `systemctl status actions.runner.*`）确认服务在运行；若未显示在线，检查服务器到 GitHub 的出站连通性与 Runner 进程是否存活。

## 5. 手动触发首次运行

在 `Actions` 页打开 `Monitor provincial legal notices`，点击 **Run workflow**：

- 想先验证通知渠道：勾选 `test_notification`，该模式只发送一条测试通知，不抓取、不修改状态；
- 想建立真实基线：不勾选，直接运行，工作流执行 `python -m monitor.run --send --max-pages 8`。

工作流 `runs-on` 已改为 `[self-hosted, linux, x64, lawwatch-domestic]`，本次运行会分发到刚注册的国内 Runner；若 Runner 未上线，运行会一直等待。

## 6. 验证首次运行

1. 在 Actions 运行详情中确认每个步骤成功（绿色）；
2. 首次成功的运行只建立基线、不发通知；运行结束后工作流会把去重状态提交回仓库，检查 `monitor/state.json`：`baselined` 变为 `true` 表示基线已建立；
3. 如果所有站点都失败，`baselined` 保持 `false`，工作流不会提交状态，需要先排查网络后再重跑。

## 7. 检查状态与日志

- **GitHub 部署看 Actions 日志**：打开对应运行，查看 `Run monitor` 与 `Commit monitor state` 步骤输出，关注 `errors` 数量与各站点错误信息；
- `data\logs\` 是 **Windows 本机部署**的日志目录，GitHub Actions 不写该目录；自托管 Runner 排查时请查看 Actions 运行日志，而不是 `data/logs`；
- 状态文件：仓库里的 `monitor/state.json`（工作流会提交回 `main`），其中 `baselined`、`documents`、`errors` 可用来核对基线是否建立、哪些站点报错。

## 8. 网络错误与替代方案

如果大量站点出现在 `errors` 中且 `baselined` 始终为 `false`，通常是地理/网络侧阻断（限流、超时、拒绝访问），而不是程序缺陷。处理顺序：

1. 在 Runner 所在服务器上直接 `curl` 一个报错站点，确认境内网络可达；
2. 确认服务器能访问 `github.com`（Runner 需要持续与 GitHub 通信）；
3. 如果自托管 Runner 不可行，可考虑为运行环境配置可用的网络代理（例如境外托管 Runner 经境内代理访问 `.gov.cn`）。

在完成一次“多数站点成功”的基线运行并人工核对日志之前，不要仅凭定时工作流判断监测是否生效。

## 9. 注意事项

- 不要在仓库中保存注册 token 或任何 SMTP/Webhook 凭据；
- Runner 软件需要定期更新，可重跑脚本或手动升级；
- Runner 重启后确认 `svc.sh` 服务仍在运行，避免定时任务静默失联。
