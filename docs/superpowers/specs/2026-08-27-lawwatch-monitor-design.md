# LawWatch 政府网站公文监测系统设计

**日期：** 2026-08-27  
**状态：** 待用户确认  
**目标：** 建立一个自动监测政府司法厅/政务网站新发布公文的系统，并将新增内容通知到企业微信和 QQ 邮箱。

## 1. 需求背景

用户维护一份省级司法厅/司法行政网站清单（`新所公示平台.xlsx`），希望监测这些网站上发布的新公文。当前表格中 31 个省级条目中有 3 个省份没有网址（辽宁、黑龙江、河南），需要补充。部分网站的列表页采用 JavaScript 渲染，通用静态抓取可能无法直接读取。

## 2. 已确认的需求

1. 监控范围：以表格中的网站页面为入口，自动发现各网站的公文、公告、公示、政策文件等栏目；发现新发布内容后提醒。
2. 范围扩展：不要求全站爬取，但要求从入口自动发现相关栏目，尽量覆盖整站的公开公文。
3. 运行方式：GitHub Actions 定时执行，间隔 30 分钟。
4. 首次运行：只建立基线，不发送历史内容的通知；后续运行只提醒新增内容。
5. 通知方式：企业微信群机器人为主要渠道，QQ 邮箱为备份渠道；每轮发现的新内容合并为一条通知，不逐条发送。
6. 数据保留：最近 30 天的去重记录保存在仓库状态文件中；邮件作为长期存档。
7. 敏感信息：QQ 邮箱账号、SMTP 授权码、收件邮箱和企业微信 Webhook 放在 GitHub Actions Secrets 中，不写入仓库。
8. 目录：监控程序放在仓库的 `monitor/` 目录，GitHub Actions 工作流放在 `.github/workflows/monitor.yml`，网站清单使用 `monitor/sites.csv`。

## 3. 范围界定

## 3.1 包含

- 省级司法厅/司法行政网站的公开公文、公告、公示、政策文件、通知公告等栏目。
- 从入口发现的同域页面、分页和栏目链接。
- 新 URL、新标题、新公文指纹的检测。
- 企业微信群机器人通知和 QQ 邮箱 SMTP 通知。
- 30 天状态保留、首次基线机制、失败日志。

## 3.2 不包含（第一版）

- 登录后的内部系统、需要个人账号的页面。
- 审批、上传、修改网站内容等管理操作。
- OCR 识别 PDF/图片中的公文正文（附件链接本身仍作为新增候选记录，见 5.4）。
- 企业微信个人号或公众号消息。
- 完整的全站搜索引擎和数据库历史检索。

## 4. 架构

系统采用一个 Python 批处理程序，由 GitHub Actions 定时触发。每次运行包括：加载站点清单和状态 -> 抓取并发现页面 -> 提取公文候选 -> 对比状态 -> 发送通知（非首次成功运行时） -> 通知成功后保存状态 -> 提交状态文件到仓库。

```text
GitHub Actions cron (every 30 min)
          |
          v
monitor/run.py
  |-- sites.csv
  |-- __init__.py
  |-- fetcher.py          HTTP / Playwright 抓取
  |-- discovery.py       发现栏目和公文链接
  |-- extractor.py       清洗与抽取候选公文
  |-- state.py           30 天去重状态
  |-- notify.py          企业微信 + QQ 邮箱
  |-- config.py          Secrets 和命令行配置
  `-- state.json         提交到仓库
```

## 5. 组件设计

### 5.1 `monitor/sites.csv`

网站清单，列：

`province,url,description,notes,dynamic`

- `province`：省级名称。
- `url`：入口 URL。
- `description`：表格中的具体位置说明。
- `notes`：备注。
- `dynamic`：`true` 表示页面需要浏览器渲染，否则为 `false`。

缺少网址的三个省份使用官方入口：

- 辽宁：`https://sft.ln.gov.cn/`
- 黑龙江：`https://sft.hlj.gov.cn/`
- 河南：`https://sft.henan.gov.cn/`

### 5.2 `monitor/config.py`

负责读取环境变量和 CSV，不包含任何业务逻辑。环境变量包括：

- `SMTP_USER`：QQ 邮箱账号。
- `SMTP_AUTH_CODE`：QQ 邮箱 SMTP 授权码。
- `EMAIL_TO`：接收邮件地址，可逗号分隔多个地址。
- `WECOM_WEBHOOK`：企业微信群机器人 Webhook。
- 可选：`MONITOR_MAX_PAGES_PER_SITE`、`MONITOR_REQUEST_TIMEOUT`、`MONITOR_STATE_FILE`。

### 5.3 `monitor/fetcher.py`

`Fetcher` 接口：

```python
class FetchResult:
    url: str
    status: int | None
    html: str | None
    final_url: str
    error: str | None

class Fetcher:
    def fetch(self, url: str) -> FetchResult: ...
```

`HttpFetcher` 使用 `requests`，`BrowserFetcher` 使用 `playwright`（用于 `dynamic=true` 的站点）。请求使用超时、浏览器 User-Agent、重试和连接错误记录。

`BrowserFetcher` 在实例生命周期内复用同一个浏览器，并提供 `close()` 供 `run()` 在 `finally` 中调用，避免每个站点反复启动浏览器。任何 Playwright 导入、启动或页面跳转失败都会降级为 `HttpFetcher` 并返回其结果（HTTP 也失败时返回 HTTP 的错误信息）。

### 5.4 `monitor/extractor.py`

从 HTML 中提取候选公文：

- 提取同域链接；识别候选公文时只跳过图片、CSS、JS、音视频等资源，不跳过 PDF/Word/Excel/压缩包等附件链接（仅记录附件 URL，不下载、不 OCR 正文；抓取队列仍只跟随 HTML 页面）。
- 优先识别 href 或文本中包含 `公告`、`公示`、`通知`、`公文`、`政策`、`文件`、`条例`、`办法`、`规定`、`意见`、`决定`、`批复`、`报告`、`招聘`、`招考`、`备案` 的链接。
- 解析标题、URL、可能的发布日期。
- 对每个页面生成一个内容指纹，用于检测页面内容变化（第一版主要用于同一 URL 的新增判断）。
- URL 规范化见 5.6。

### 5.5 `monitor/discovery.py`

从 `sites.csv` 的入口出发：

- 同域 BFS，深度最多 2 层，默认每个站点最多抓取 30 页（GitHub Actions 中通过 `--max-pages 15` 收紧预算）。
- 记录发现到的“列表页/栏目页”URL，供后续运行快速定位。
- 对 `dynamic=true` 的站点优先调用浏览器抓取；失败时降级为 HTTP 抓取并记录日志。
- 不爬取登录、附件、JS/CSS、明显无关的站外页面。

### 5.6 `monitor/state.py`

状态使用 `monitor/state.json`：

```json
{
  "documents": {
    "<canonical-url>": {
      "title": "...",
      "province": "...",
      "first_seen": "2026-08-27T00:00:00Z",
      "last_seen": "2026-08-27T00:30:00Z",
      "fingerprint": "..."
    }
  },
  "list_urls": {},
  "errors": {
    "<site-url>": {
      "error": "request timeout",
      "at": "2026-08-27T00:30:00Z"
    }
  },
  "baselined": false
}
```

规则：

- 首次成功运行：只要本轮至少一个站点完成且没有记录错误（哪怕发现 0 条公文），就把 `baselined` 置为 `true`，并把所有发现的公文写入 `documents`，不发送通知。若所有站点都失败，`baselined` 保持 `false`，下一轮仍按首次运行处理并重试。
- 后续运行（`baselined == true`）：新 URL 加入 `documents` 并作为新增内容发送通知。
- 状态保存前删除 `last_seen` 超过 30 天的记录。
- URL 规范化：去掉 `#top` 之类的惰性 fragment，保留以 `#/` 开头的 SPA 哈希路由 fragment（如 `#/publics/...`、`#/home?...`）；host 统一小写并去除默认端口，保留查询参数和非默认端口。
- 第一版以规范化 URL 作为公文身份；`fingerprint` 仅记录在状态中，用于诊断，不触发“同一 URL 内容变化”的通知。
- 状态保存使用“写临时文件 + `os.replace`”的原子替换；加载时对缺失字段使用默认值（含 `baselined: false`）。

### 5.7 `monitor/notify.py`

`Notifier` 提供两个独立方法：

```python
def send_wecom(items: list[Document]) -> None: ...
def send_email(items: list[Document]) -> None: ...
def notify_all(items: list[Document]) -> bool: ...
```

- 企业微信：使用默认群机器人 Webhook，发送普通文本消息，内容包含省份、标题和链接；单条消息控制在约 1800 字节以内，批次过大时截断标题列表并注明“（仅显示前 N 条，详见邮件）”。
- QQ 邮箱：使用 `smtplib` + SMTP_SSL，主题为 `[LawWatch] 新增 N 条公文`，正文包含完整列表。
- 两条渠道独立执行，一个失败不会阻止另一个，但失败会在 stderr 留下明确日志。
- `notify_all` 返回是否有至少一条渠道成功；全部失败或未配置任何渠道时返回 `False`。
- 本轮没有新增内容时不发送通知。

### 5.8 `monitor/run.py`

命令行入口：

```bash
python -m monitor.run --dry-run
python -m monitor.run --send
```

- `--dry-run` 用于本地验证抓取和检测，不发送通知、不写状态文件，并打印“基线/是否会通知”的摘要。
- `--send` 用于 GitHub Actions 的全量运行。有新增且非首次成功运行时，先发送通知，只有至少一条渠道成功才持久化去重状态；通知全部失败或未配置渠道时，不保存文档去重状态，`notifications_ok=false`，CLI 以非零状态退出（工作流因此不会提交状态文件，下一轮重试同一批内容）。
- `run(send=False)` 的本地运行不要求配置任何通知渠道。

### 5.9 GitHub Actions

`.github/workflows/monitor.yml`：

- 使用 `schedule`：`*/30 * * * *`。
- 使用 `concurrency` 组（`cancel-in-progress: false`），避免定时与手动运行互相重叠。
- `timeout-minutes: 20`（低于 30 分钟的执行间隔）。
- 检出仓库，配置 Python。
- 安装 `requirements.txt` 并安装 Playwright Chromium。
- 运行 `python -m monitor.run --send --max-pages 15`。
- 将 `monitor/state.json` 的变更提交；推送前先 `git pull --rebase`（带重试），pull/rebase 失败时输出清晰诊断并放弃推送。
- 工作流需要 `permissions: contents: write`。

## 6. 数据流

1. 读取 `monitor/sites.csv`。
2. 对每个站点抓取入口和发现的栏目页面。
3. 从 HTML 中提取候选公文和 URL。
4. 与 `state.json` 比较。
5. 首次成功运行写基线；后续运行收集新增项。
6. 非首次成功运行且有新增时，先发送一条企业微信消息和一封邮件。
7. 至少一条通知渠道成功（或本轮无新增）时，更新状态并原子保存 30 天记录；通知全部失败时不保存，下一轮重试。
8. GitHub Actions 提交状态文件。

## 7. 错误处理

- 单个站点失败不终止整个任务；错误写入运行日志和 `state.json` 的 `errors` 字段。
- 连续失败不发送单个失败的邮件轰炸；第一版只在日志中记录，后续版本可增加失败通知开关。
- 网站响应超时、HTTP 5xx、DNS 错误、TLS 错误均被捕获并标记。
- Playwright 不可用、启动失败或页面跳转失败时，动态站点自动降级为 HTTP 抓取并记录日志（HTTP 也失败则记录 HTTP 错误）。
- 通知渠道全部失败时进程以非零状态退出且不提交去重状态，保证下一轮可重试同一批新增内容。

## 8. 安全

- 所有敏感配置只从环境变量读取。
- `.env.example` 只包含占位符，不包含真实授权码或 Webhook。
- `.gitignore` 忽略 `.env` 和本地缓存。
- 状态文件只包含公文元数据，不包含凭据。

## 9. 验证方式

1. 单元测试覆盖 URL 规范化（含 SPA `#/` 路由与 host/端口归一化）、候选链接提取（含附件链接）、状态去重、`baselined` 首次运行语义、30 天清理、动态抓取降级与浏览器复用/关闭、企业微信 payload 截断、邮件 payload、通知失败时不保存状态、dry-run 不写状态。
2. 本地运行 `python -m pytest`，要求全部通过。
3. 本地以 `--dry-run --max-pages 1` 抓取，确认能发现候选公文的 URL，且 `monitor/state.json` 不被修改。
4. 使用模拟 HTML 验证首次运行不通知、第二次运行通知新增。
5. GitHub Actions 只在实际部署后由用户配置 Secrets 并观察日志；首次真实运行需人工核对是否被 GitHub 托管 Runner 的网络位置阻断（见 README）。

## 10. 后续可扩展项

- 针对具体网站定制 CSS 选择器或 API 适配器。
- PDF/附件内容摘要和 OCR。
- 失败通知、每日汇总、关键词过滤。
- 把历史记录迁移到 SQLite 或 GitHub Issues。