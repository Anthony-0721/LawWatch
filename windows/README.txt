LawWatch Monitor - Windows 便携版使用说明
=========================================

目录结构（发布包 dist/LawWatchMonitor/）

  python\              便携 Python 运行时
  monitor\             监测程序
  data\                运行数据：sites.csv、state.json、logs\
  run.bat              启动脚本
  config.example.json  配置模板
  install-task.bat     注册计划任务（每 30 分钟）
  uninstall-task.bat   删除计划任务
  README.txt           本说明

一、安装

1. 将整个 LawWatchMonitor 文件夹复制到本地固定目录，例如 D:\LawWatchMonitor。
   建议不要放在 C:\Program Files 等需要管理员权限的位置。
2. 确认包内存在 python\python.exe、monitor\ 与 run.bat。

二、配置

1. 首次运行 install-task.bat 时，若 config.json 不存在，会自动从
   config.example.json 复制生成；也可以手动把 config.example.json 复制为 config.json。
2. 用文本编辑器打开 config.json，填写：

   smtp_user        发件邮箱（如 QQ 邮箱）
   smtp_auth_code   SMTP 授权码
   email_to         收件人邮箱
   wecom_webhook    企业微信群机器人 Webhook 地址
   schedule_minutes 30（保留即可）

3. 企业微信与邮件至少配置一种，否则发现新公文时无法通知。
   注意：任务间隔由 install-task.bat 固定为 30 分钟，schedule_minutes 只是记录值。

三、首次运行（建立基线）

1. 运行 run.bat --dry-run：只抓取与检测，不发送通知、不写入 state.json，用于验证程序可用。
2. 运行 run.bat --send：完成首次完整运行。首次成功的运行只建立基线、不发通知；
   之后每轮发现新增公文才会通知。若所有站点都失败，基线不会建立，后续会继续重试。
3. 检查 data\state.json 中 "baselined" 是否为 true，并查看 data\logs\monitor.log。
4. 可运行 run.bat --test-notification 只发送一条测试通知，验证通知渠道。

四、注册计划任务

双击 install-task.bat。脚本会创建名为 "LawWatch Monitor" 的任务，每 30 分钟以当前
用户身份执行 run.bat --send。安装过程中 SchTasks 可能提示输入该用户的登录密码，并把
任务凭据交给 Windows 管理。任务仅在创建该任务时的 Windows 用户登录期间运行，用户
注销后不运行。

验证任务是否存在：在命令提示符运行
  schtasks /query /tn "LawWatch Monitor"

如需修改间隔：编辑 install-task.bat 中的 /mo 值，再重新双击运行该脚本。

五、SmartScreen 提示

The portable Python folder does not require code signing; if Windows blocks the .bat,
use "More info -> Run anyway" only after verifying the file came from the trusted package.

即：便携 Python 文件夹不需要代码签名。如果 Windows 拦截 run.bat 或 install-task.bat，
请先确认文件确实来自可信的发布包（核对来源与内容），再点击“更多信息 -> 仍要运行”。
不要对来源不明的脚本执行该操作。

六、卸载

双击 uninstall-task.bat 删除计划任务。config.json 与 data\ 会被保留。
如需彻底清除，手动删除整个 LawWatchMonitor 文件夹。

七、更新与迁移

1. 双击 uninstall-task.bat 停用旧任务。
2. 用新发布包覆盖 monitor\ 与 run.bat（config.example.json 等脚本文件可同步更新）；
   保留 config.json 与 data\（其中包含基线 state.json、sites.csv 与日志）。
3. 重新双击 install-task.bat 注册任务，再运行 run.bat --dry-run 验证。

从 GitHub Actions 等其他部署方式迁移时：把已有 data\state.json 与 data\sites.csv 放入
新包的 data\ 目录，填写 config.json，再按上述步骤注册任务即可。
