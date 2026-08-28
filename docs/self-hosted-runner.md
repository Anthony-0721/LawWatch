# 国内自托管 GitHub Actions Runner

这是部署到国内 Linux 服务器/云主机的步骤，用于避免 GitHub 境外 Runner 无法访问部分 `.gov.cn` 网站的问题。

## 前提

- 一台可联网的国内 Linux 服务器（建议 Ubuntu 22.04+，2 核 2GB 以上）。
- 服务器能访问 `github.com`（Runner 需要从 GitHub 拉取任务）。
- GitHub 账号对 `Anthony-0721/LawWatch` 仓库有管理权限，用于生成 Runner 注册 token。

## 安装依赖

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip curl
```

## 注册 Runner

1. 打开仓库：`Settings -> Actions -> Runners -> New self-hosted runner`。
2. 选择 Linux，复制注册 token。
3. 在服务器执行：

```bash
export RUNNER_TOKEN="粘贴注册token"
curl -fsSL https://raw.githubusercontent.com/Anthony-0721/LawWatch/main/scripts/setup-domestic-runner.sh -o /tmp/setup-domestic-runner.sh
sudo bash /tmp/setup-domestic-runner.sh
```

4. 回到 GitHub Runner 页面，确认 `lawwatch-domestic` 状态为 **Idle** 或 **Online**。

脚本会自动配置 GitHub Runner 服务，并使用标签：
`self-hosted,linux,x64,lawwatch-domestic`

## 验证

Runner 上线后，手动运行一次 `Monitor provincial legal notices`。工作流已经在 `main` 上切换为：
`runs-on: [self-hosted, linux, x64, lawwatch-domestic]`

本次运行会建立/更新基线，之后每 30 分钟在国内主机上执行。

## 注意事项

- 如果注册后 Runner 没有显示在线，检查服务器防火墙是否允许 GitHub 出站、Runner 进程是否存活。
- 如果不想安装浏览器，可以在工作流安装步骤失败后继续使用 HTTP 降级；动态站点覆盖会受影响。
- 不要把注册 token 写进仓库；token 只是临时值。
