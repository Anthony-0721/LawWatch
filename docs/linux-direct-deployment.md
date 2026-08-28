# 云服务器直接部署（不依赖 GitHub Actions Runner）

本方案不注册 GitHub Actions Runner，不依赖 GitHub 定时工作流，直接把整个监控程序部署到国内 Linux 云服务器，通过 systemd 每 30 分钟运行一次。

适合已经购买云服务器，或甲方希望把监控放在自己的服务器上、由自己控制部署的情况。

## 优点

- 不需要 Runner Token、标签、Runner 重启和版本维护；
- 不需要 GitHub Actions 的 30 分钟超时和免费额度限制；
- 服务器重启后 systemd timer 会自动恢复，并补跑错过的任务；
- 配置、日志、基线状态全部落在服务器本地；
- 更适合作为甲方长期运行的正式服务。

## 推荐服务器配置

- Ubuntu 22.04 或 Ubuntu 24.04；
- 2 核 CPU、4 GB 内存；
- 50–60 GB SSD；
- 5 Mbps 以上公网带宽；
- 服务器能够访问 `github.com`、`pypi.org` 和目标 `.gov.cn` 站点。

如果 GitHub 访问不稳定，可以先通过压缩包或内网把代码上传到服务器，不需要 `git clone`。

## 一、获取代码

方式一：从 GitHub 拉取

```bash
sudo apt-get update
sudo apt-get install -y git curl

git clone https://github.com/Anthony-0721/LawWatch.git /tmp/lawwatch-src
cd /tmp/lawwatch-src
```

方式二：把项目压缩包上传到服务器后解压，例如：

```bash
sudo mkdir -p /tmp/lawwatch-src
sudo tar -xzf LawWatch.tar.gz -C /tmp/lawwatch-src --strip-components=1
cd /tmp/lawwatch-src
```

## 二、一键安装

```bash
sudo bash scripts/install-linux-direct.sh
```

脚本会完成：

1. 创建 `lawwatch` 系统用户；
2. 把程序复制到 `/opt/lawwatch/app`；
3. 创建 Python 虚拟环境并安装依赖；
4. 安装 Playwright Chromium（可用 `INSTALL_BROWSER=0` 跳过）；
5. 创建 `/var/lib/lawwatch` 数据目录；
6. 创建 `/etc/lawwatch/config.json` 配置模板；
7. 安装 `lawwatch-monitor.service` 和 `lawwatch-monitor.timer`；
8. 启动每 30 分钟执行一次的定时器。

## 三、填写通知配置

```bash
sudoedit /etc/lawwatch/config.json
```

```json
{
  "smtp_user": "发件QQ邮箱",
  "smtp_auth_code": "QQ邮箱SMTP授权码",
  "email_to": "接收邮箱",
  "wecom_webhook": "企业微信群机器人Webhook地址",
  "schedule_minutes": 30
}
```

配置文件权限已设置为仅 root 和 `lawwatch` 组可读，不要提交到 Git，也不要发送到公开群聊。

## 四、先验证通知

```bash
sudo -u lawwatch \
  /opt/lawwatch/venv/bin/python -m monitor.run \
  --test-notification \
  --config /etc/lawwatch/config.json \
  --data-dir /var/lib/lawwatch
```

确认邮箱或企业微信收到测试消息。

## 五、手工执行一次正式运行

```bash
sudo systemctl start lawwatch-monitor.service
sudo systemctl status lawwatch-monitor.service
```

首次成功运行只建立基线、不发通知；之后定时任务发现新增公文后才通知。

## 六、验证定时任务

```bash
systemctl status lawwatch-monitor.timer
journalctl -u lawwatch-monitor.service -n 200 --no-pager
```

查看状态：

```bash
cat /var/lib/lawwatch/state.json
```

重点关注：

```json
{
  "baselined": true
}
```

`baselined: true` 表示基线已经建立。

## 七、重启与补跑

定时器配置了：

```ini
Persistent=true
```

所以服务器重启后不需要人工启动；如果关机期间错过了任务，重启后 systemd 会在可用时补跑。

## 八、更新程序

代码更新后，在服务器执行：

```bash
cd /tmp/lawwatch-src
git pull
sudo bash scripts/install-linux-direct.sh
```

脚本会保留：

- `/etc/lawwatch/config.json`
- `/var/lib/lawwatch/sites.csv`
- `/var/lib/lawwatch/state.json`
- `/var/lib/lawwatch/logs/`

不会因为更新代码而清空历史基线。

## 九、停止或卸载

暂停定时器：

```bash
sudo systemctl stop lawwatch-monitor.timer
sudo systemctl disable lawwatch-monitor.timer
```

彻底移除：

```bash
sudo systemctl stop lawwatch-monitor.service
sudo systemctl disable lawwatch-monitor.service lawwatch-monitor.timer
sudo rm -f /etc/systemd/system/lawwatch-monitor.service
sudo rm -f /etc/systemd/system/lawwatch-monitor.timer
sudo systemctl daemon-reload
```

如需保留数据用于以后恢复，不要删除 `/var/lib/lawwatch` 和 `/etc/lawwatch/config.json`。

## 十、注意事项

- 服务器必须保持开机；不能像 Windows 便携版那样依赖用户登录；
- 该方案不再使用 GitHub Actions，因此 GitHub 上的工作流、Secret 和 Runner 都不再参与调度；
- 如果服务器无法访问 `github.com`，更新时可从本机上传代码，或采用离线发布包；
- `config.json` 包含真实凭据，服务器上必须限制文件权限并定期备份；
- 需要定期查看 `journalctl` 和 `state.json`，避免某站点改版后所有站点长期失败而不自知。
