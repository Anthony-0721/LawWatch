LawWatch Monitor - Windows 便携版打包说明
=========================================

本目录说明如何把 LawWatch Monitor 打包为 Windows 绿色版（便携 Python 文件夹）。
构建产物为 dist/LawWatchMonitor/，可整体复制到目标 Windows 机器上运行。

一、构建前置条件

1. 在 Windows 开发机上安装 64 位 Python 3.x，并确认 python 命令可用且指向真实
   安装目录：
     python --version
     python -m pip --version
   注意：Microsoft Store 的 python.exe 占位程序不能用于打包；请使用 python.org
   的完整安装包，并确认 (Get-Command python).Source 指向真实安装目录。

2. 构建机需要联网，脚本会向包内 Python 安装 requirements.txt 中的依赖。
3. 仓库需包含 monitor/、windows/ 与 requirements.txt（由任务 1-3 提供）。

二、构建

在仓库根目录运行：

  powershell -ExecutionPolicy Bypass -File scripts\prepare-windows-portable.ps1

脚本会先校验 python 命令指向真实安装（拒绝 Microsoft Store 的 0 字节占位程序），并删除旧的 dist/LawWatchMonitor/，然后依次执行：

1. 把当前 PATH 中 python 所在的整个安装目录复制到
   dist/LawWatchMonitor/python\；
2. 在包内 Python 中升级 pip，并安装 requirements.txt 依赖；
3. 复制 monitor\ 以及 windows\ 下的启动、配置与任务计划脚本；
4. 生成全新 data\：复制 sites.csv、写入空 state.json
   （baselined=false，首次运行将重新建立基线）并创建 logs\ 目录。

每次运行都会先删除旧的 dist/LawWatchMonitor/，再以当前源码重新生成，避免旧文件
残留。需要重建时直接再次运行，无需手工清理。

三、冒烟测试

构建完成后在仓库根目录运行：

  .\dist\LawWatchMonitor\run.bat --dry-run

预期输出抓取统计，且不会写入 data\state.json。安装、配置、计划任务、SmartScreen
与更新迁移说明见包内 README.txt（内容来自 windows/README.txt）。

四、发布

将整个 dist/LawWatchMonitor/ 文件夹压缩为 zip 交付，或直接复制到目标机器。
发布前检查包内不包含 config.json 或任何真实凭据；config.json 由接收方在部署时
从 config.example.json 生成。

五、注意事项

1. 便携包内含完整 Python 运行时，体积较大（取决于构建机 Python 安装内容）；
2. 目标机器无需安装 Python，程序使用包内 python\python.exe 运行；
3. monitor\ 按源码复制，脚本会清理包内的 __pycache__ 目录；源码目录下的
   state.json 也会被带入，但运行时不使用，状态只读写 data\ 下的文件；
4. 更新发布包时保留接收方机器上的 config.json 与 data\，仅覆盖其余文件。
