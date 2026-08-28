# LawWatch 公文监测 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `LawWatch` 仓库中建立一个 Python 公文监测程序，通过 GitHub Actions 每 30 分钟执行，发现省级司法厅网站新发布的公文，并通过企业微信和 QQ 邮箱通知。

**Architecture:** 一个批处理 Python 程序，分为站点清单、抓取器、候选公文提取、站点发现、状态去重、通知器和工作流七个模块。GitHub Actions 读取 `monitor/sites.csv`，抓取同域页面，比较 `monitor/state.json`，把新增公文合并成一条通知，提交状态文件回仓库。

**Tech Stack:** Python 3.12、requests、BeautifulSoup4、lxml、Playwright、smtplib、pytest、GitHub Actions。

## Global Constraints

- 代码使用 UTF-8 编码；CSV 使用 `utf-8-sig` 读取以兼容 Excel 导出。
- 不把 QQ 授权码、企业微信 Webhook 写进仓库；全部读取环境变量。
- 每个站点失败不能中断整个任务。
- 第一版以规范化 URL 作为公文身份；内容指纹只记录，不触发更新通知。
- 状态保存最近 30 天记录，超过自动清理。
- GitHub Actions 需要 `contents: write` 权限以提交 `monitor/state.json`。
- 本地 `--dry-run` 不发送通知、不提交工作流状态文件。

## Task 1: 项目骨架与配置

**Files:**
- Create: `monitor/__init__.py`
- Create: `monitor/models.py`
- Create: `monitor/config.py`
- Create: `tests/test_config.py`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`

**Interfaces:**
- `Site(province, url, description, notes, dynamic)`
- `Document(url, title, province, source_url, published_at, fingerprint)`
- `FetchResult(url, status, html, final_url, error)`
- `load_sites(path=monitor/sites.csv) -> list[Site]`

**Step 1: Write failing test**

```python
from pathlib import Path
from monitor.config import load_sites

def test_load_sites_reads_excel_compatible_csv(tmp_path: Path):
    csv_path = tmp_path / "sites.csv"
    csv_path.write_text(
        "\ufeffprovince,url,description,notes,dynamic\n"
        "上海市,https://example.gov.cn/a,测试,备注,false\n",
        encoding="utf-8",
    )
    sites = load_sites(csv_path)
    assert len(sites) == 1
    assert sites[0].province == "上海市"
    assert sites[0].dynamic is False
```

**Step 2: Run test and confirm it fails**

```bash
python -m pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'monitor'`.

**Step 3: Minimal implementation**

`monitor/__init__.py`:

```python
"""LawWatch government-document monitoring package."""
```

`monitor/models.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    province: str
    url: str
    description: str = ""
    notes: str = ""
    dynamic: bool = False


@dataclass(frozen=True)
class Document:
    url: str
    title: str
    province: str
    source_url: str
    published_at: str | None = None
    fingerprint: str = ""


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int | None = None
    html: str | None = None
    final_url: str = ""
    error: str | None = None
```

`monitor/config.py`:

```python
import csv
import os
from pathlib import Path

from .models import Site

PACKAGE_DIR = Path(__file__).resolve().parent


def load_sites(path: Path = PACKAGE_DIR / "sites.csv") -> list[Site]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return [
            Site(
                province=row["province"].strip(),
                url=row["url"].strip(),
                description=row.get("description", "").strip(),
                notes=row.get("notes", "").strip(),
                dynamic=row.get("dynamic", "").strip().lower() in {"1", "true", "yes"},
            )
            for row in rows
            if row.get("url", "").strip()
        ]


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
```

`monitor/config.py` must import `Site` from models before `load_sites` is used; `models.py` has no external dependencies.

`requirements.txt`:

```text
requests>=2.31
beautifulsoup4>=4.12
lxml>=5.1
playwright>=1.45
```

`requirements-dev.txt`:

```text
-r requirements.txt
pytest>=8.0
```

`.gitignore`:

```text
__pycache__/
.pytest_cache/
*.pyc
.env
monitor/.cache/
```

`.env.example`:

```text
SMTP_USER=your_qq_mail@qq.com
SMTP_AUTH_CODE=your_smtp_auth_code
EMAIL_TO=your_qq_mail@qq.com
WECOM_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...
```

**Step 4: Run test and confirm it passes**

```bash
python -m pytest tests/test_config.py -v
```

**Step 5: Commit**

```bash
git add monitor/__init__.py monitor/models.py monitor/config.py tests/test_config.py .gitignore .env.example requirements.txt requirements-dev.txt
git commit -m "feat(monitor): add package skeleton and site config"
```

---

## Task 2: URL 规范化与公文候选提取

**Files:**
- Create: `monitor/extractor.py`
- Create: `tests/test_extractor.py`

**Interfaces:**
- `canonical_url(url, base_url) -> str`
- `extract_links(html, base_url) -> list[tuple[str, str]]`
- `is_document_candidate(url, text) -> bool`
- `extract_documents(html, base_url, province, source_url) -> list[Document]`

**Step 1: Write failing tests**

```python
from monitor.extractor import canonical_url, is_document_candidate, extract_documents


def test_canonical_url_removes_fragment_but_keeps_query():
    assert canonical_url("/article?id=1#top", "https://example.gov.cn/") == (
        "https://example.gov.cn/article?id=1"
    )


def test_document_candidate_uses_title_hints():
    assert is_document_candidate("https://example.gov.cn/doc/123", "关于设立律师事务所的公告") is True
    assert is_document_candidate("https://example.gov.cn/nav", "首页") is False


def test_extract_documents_deduplicates_urls():
    html = """
    <html><body>
      <a href="/notice/1.shtml">关于设立律师事务所的公告</a>
      <a href="/notice/1.shtml">同样链接</a>
      <a href="/nav">首页</a>
    </body></html>
    """
    docs = extract_documents(html, "https://example.gov.cn/", "测试省", "https://example.gov.cn/")
    assert len(docs) == 1
    assert docs[0].title == "关于设立律师事务所的公告"
```

**Step 2: Run test and confirm failure**

```bash
python -m pytest tests/test_extractor.py -v
```

**Step 3: Minimal implementation**

```python
import hashlib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import Document

SKIP_EXTENSIONS = {
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".pdf", ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx", ".mp4",
}

DOCUMENT_HINTS = (
    "公告", "公示", "通知", "公文", "政策", "文件", "条例", "办法",
    "规定", "意见", "决定", "批复", "报告", "招聘", "招考", "备案",
)

DATE_RE = re.compile(r"(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}日?)")


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def canonical_url(url: str, base_url: str) -> str:
    parsed = urlparse(urljoin(base_url, url))
    return parsed._replace(fragment="").geturl()


def is_document_candidate(url: str, text: str) -> bool:
    if any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    if len(normalize_text(text)) < 6:
        return False
    return any(hint in text for hint in DOCUMENT_HINTS) or (
        any(part in url.lower() for part in ("article", "doc", "content", "detail", "info", "notice"))
        and len(normalize_text(text)) >= 8
    )


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for anchor in soup.select("a[href]"):
        href = canonical_url(anchor.get("href", ""), base_url)
        if not href.startswith(("http://", "https://")):
            continue
        parsed = urlparse(href)
        if parsed.netloc != urlparse(base_url).netloc:
            continue
        links.append((href, normalize_text(anchor.get_text(" ", strip=True))))
    return links


def extract_documents(
    html: str,
    base_url: str,
    province: str,
    source_url: str,
) -> list[Document]:
    docs = []
    seen = set()
    for url, text in extract_links(html, base_url):
        if not is_document_candidate(url, text):
            continue
        fingerprint = hashlib.sha256(f"{url}|{text}".encode("utf-8")).hexdigest()[:16]
        docs.append(
            Document(
                url=url,
                title=normalize_text(text),
                province=province,
                source_url=canonical_url(source_url, source_url),
                fingerprint=fingerprint,
            )
        )
    unique = []
    seen_urls = set()
    for doc in docs:
        if doc.url in seen_urls:
            continue
        seen_urls.add(doc.url)
        unique.append(doc)
    return unique
```

**Step 4: Run test and confirm it passes**

```bash
python -m pytest tests/test_extractor.py -v
```

**Step 5: Commit**

```bash
git add monitor/extractor.py tests/test_extractor.py
git commit -m "feat(monitor): extract candidate official documents"
```

---

## Task 3: HTTP 与 Playwright 抓取器

**Files:**
- Create: `monitor/fetcher.py`
- Create: `tests/test_fetcher.py`

**Interfaces:**
- `HttpFetcher.fetch(url) -> FetchResult`
- `BrowserFetcher.fetch(url) -> FetchResult`

**Step 1: Write failing tests**

```python
from monitor.fetcher import HttpFetcher
from monitor.models import FetchResult


def test_http_fetcher_returns_html(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "<html>ok</html>"
        url = "https://example.gov.cn/ok"

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("monitor.fetcher.requests.Session", lambda: FakeSession())
    result = HttpFetcher().fetch("https://example.gov.cn/")
    assert result.status == 200
    assert result.html == "<html>ok</html>"
```

**Step 2: Run test and confirm failure**

```bash
python -m pytest tests/test_fetcher.py -v
```

**Step 3: Minimal implementation**

```python
import requests

from .models import FetchResult

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class HttpFetcher:
    def __init__(self, timeout: int = 20, retries: int = 2):
        self.timeout = timeout
        self.retries = retries

    def fetch(self, url: str) -> FetchResult:
        last_error = None
        with requests.Session() as session:
            session.headers.update(DEFAULT_HEADERS)
            for _ in range(self.retries + 1):
                try:
                    response = session.get(url, timeout=self.timeout, allow_redirects=True)
                    if response.status_code >= 500:
                        last_error = f"HTTP {response.status_code}"
                        continue
                    return FetchResult(
                        url=url,
                        status=response.status_code,
                        html=response.text,
                        final_url=response.url,
                    )
                except requests.RequestException as exc:
                    last_error = str(exc)
        return FetchResult(url=url, error=last_error or "request failed")


class BrowserFetcher:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def fetch(self, url: str) -> FetchResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return HttpFetcher(timeout=self.timeout).fetch(url)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(user_agent=DEFAULT_HEADERS["User-Agent"])
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                html = page.content()
                final_url = page.url
                browser.close()
            return FetchResult(url=url, status=200, html=html, final_url=final_url)
        except Exception as exc:
            return FetchResult(url=url, error=str(exc))
```

**Step 4: Run test and confirm it passes**

```bash
python -m pytest tests/test_fetcher.py -v
```

**Step 5: Commit**

```bash
git add monitor/fetcher.py tests/test_fetcher.py
git commit -m "feat(monitor): add HTTP and browser fetchers"
```

---

## Task 4: 30 天状态存储与去重

**Files:**
- Create: `monitor/state.py`
- Create: `monitor/state.json`
- Create: `tests/test_state.py`

**Interfaces:**
- `StateStore(path)`
- `StateStore.update(documents, errors) -> tuple[list[Document], bool]`
- `StateStore.save() -> None`

**Step 1: Write failing tests**

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

from monitor.models import Document
from monitor.state import StateStore


def doc(url: str, title: str = "关于设立律师事务所的公告") -> Document:
    return Document(url=url, title=title, province="测试省", source_url="https://example.gov.cn/")


def test_first_run_is_baseline_and_second_run_finds_new(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    _, baseline = store.update([doc("https://example.gov.cn/1")], {})
    assert baseline is True
    new, baseline = store.update([doc("https://example.gov.cn/1"), doc("https://example.gov.cn/2")], {})
    assert baseline is False
    assert [item.url for item in new] == ["https://example.gov.cn/2"]


def test_state_cleans_records_older_than_30_days(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    store.update([doc("https://example.gov.cn/old")], {})
    old_key = "https://example.gov.cn/old"
    store.data["documents"][old_key]["last_seen"] = (
        datetime.now(timezone.utc) - timedelta(days=31)
    ).isoformat()
    store._retain()
    assert old_key not in store.data["documents"]
```

**Step 2: Run test and confirm failure**

```bash
python -m pytest tests/test_state.py -v
```

**Step 3: Minimal implementation**

```python
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Document


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class StateStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = {"documents": {}, "list_urls": {}, "errors": {}}
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))

    def update(self, documents: list[Document], errors: dict[str, str]) -> tuple[list[Document], bool]:
        baseline = not self.data["documents"]
        now = now_iso()
        new_items = []
        for document in documents:
            if document.url not in self.data["documents"]:
                new_items.append(document)
            self.data["documents"][document.url] = {
                "title": document.title,
                "province": document.province,
                "first_seen": self.data["documents"].get(document.url, {}).get("first_seen", now),
                "last_seen": now,
                "fingerprint": document.fingerprint,
            }
        self.data["errors"] = errors
        self._retain()
        return new_items, baseline

    def _retain(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        stale = [
            url for url, record in self.data["documents"].items()
            if parse_iso(record["last_seen"]) < cutoff
        ]
        for url in stale:
            self.data["documents"].pop(url, None)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
```

`monitor/state.json` initial content:

```json
{
  "documents": {},
  "list_urls": {},
  "errors": {}
}
```

**Step 4: Run test and confirm it passes**

```bash
python -m pytest tests/test_state.py -v
```

**Step 5: Commit**

```bash
git add monitor/state.py monitor/state.json tests/test_state.py
git commit -m "feat(monitor): add 30-day state store and deduplication"
```

---

## Task 5: 站点栏目发现

**Files:**
- Create: `monitor/discovery.py`
- Create: `tests/test_discovery.py`

**Interfaces:**
- `discover_for_site(site, fetcher, known_list_urls=(), max_pages=30, max_depth=2) -> tuple[list[Document], list[str], dict[str, str]]`

**Step 1: Write failing tests**

```python
from monitor.discovery import discover_for_site
from monitor.models import FetchResult, Site


def test_discovery_extracts_documents_and_list_pages():
    seed = Site(province="测试省", url="https://example.gov.cn/")
    html = """
    <html><body>
      <a href="/xxgk/list.shtml">政务公开列表</a>
      <a href="/article/1.shtml">关于设立律师事务所的公告</a>
    </body></html>
    """
    class FakeFetcher:
        def fetch(self, url):
            return FetchResult(url=url, status=200, html=html, final_url=url)

    docs, list_urls, errors = discover_for_site(seed, FakeFetcher())
    assert any("article/1.shtml" in item.url for item in docs)
    assert "https://example.gov.cn/xxgk/list.shtml" in list_urls
    assert errors == {}
```

**Step 2: Run test and confirm failure**

```bash
python -m pytest tests/test_discovery.py -v
```

**Step 3: Minimal implementation**

```python
from collections import deque

from .extractor import extract_documents, extract_links
from .models import Document, Site

LIST_HINTS = (
    "xxgk", "xzxk", "gs", "notice", "notification", "public", "zwgk",
    "zfxxgk", "sgs", "shgk", "fdzdgknr", "publicity", "credit",
)


def is_list_candidate(url: str, text: str) -> bool:
    lowered = url.lower()
    return any(hint in lowered for hint in LIST_HINTS)


def discover_for_site(
    site: Site,
    fetcher,
    known_list_urls: tuple[str, ...] = (),
    max_pages: int = 30,
    max_depth: int = 2,
) -> tuple[list[Document], list[str], dict[str, str]]:
    queue = deque([(site.url, 0), *((url, 0) for url in known_list_urls)])
    visited = set()
    documents: list[Document] = []
    errors: dict[str, str] = {}

    while queue and len(visited) < max_pages:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        result = fetcher.fetch(url)
        if result.error or result.status != 200:
            errors[url] = result.error or f"HTTP {result.status}"
            continue
        documents.extend(
            extract_documents(
                result.html or "",
                result.final_url or url,
                site.province,
                url,
            )
        )
        if depth < max_depth:
            for link, text in extract_links(result.html or "", result.final_url or url):
                if is_list_candidate(link, text):
                    queue.append((link, depth + 1))
    unique_docs = []
    seen_urls = set()
    for document in documents:
        if document.url not in seen_urls:
            seen_urls.add(document.url)
            unique_docs.append(document)
    return unique_docs, list(visited), errors
```

**Step 4: Run test and confirm it passes**

```bash
python -m pytest tests/test_discovery.py -v
```

**Step 5: Commit**

```bash
git add monitor/discovery.py tests/test_discovery.py
git commit -m "feat(monitor): discover public-notice columns from site seeds"
```

---

## Task 6: 企业微信与 QQ 邮箱通知

**Files:**
- Create: `monitor/notify.py`
- Create: `tests/test_notify.py`

**Interfaces:**
- `build_wecom_payload(items) -> dict`
- `send_wecom(webhook, items) -> None`
- `build_email_body(items) -> str`
- `send_email(settings, items) -> None`

**Step 1: Write failing tests**

```python
import smtplib
from email.message import Message

from monitor.models import Document
from monitor.notify import build_wecom_payload, build_email_body


def items():
    return [
        Document(
            url="https://example.gov.cn/news/1",
            title="关于设立律师事务所的公告",
            province="测试省",
            source_url="https://example.gov.cn/list",
        )
    ]


def test_wecom_payload_contains_province_title_and_url():
    payload = build_wecom_payload(items())
    assert payload["msgtype"] == "text"
    body = payload["text"]["content"]
    assert "测试省" in body
    assert "关于设立律师事务所的公告" in body
    assert "https://example.gov.cn/news/1" in body


def test_email_body_contains_all_items():
    body = build_email_body(items())
    assert "新增 1 条公文" in body
    assert "https://example.gov.cn/news/1" in body
```

**Step 2: Run test and confirm failure**

```bash
python -m pytest tests/test_notify.py -v
```

**Step 3: Minimal implementation**

```python
import smtplib
import os
from email.mime.text import MIMEText

import requests

from .models import Document


def build_wecom_payload(items: list[Document]) -> dict:
    lines = [
        f"LawWatch 发现 {len(items)} 条新公文",
    ]
    for item in items:
        lines.append(f"- {item.province}：{item.title}\n  {item.url}")
    return {
        "msgtype": "text",
        "text": {"content": "\n".join(lines)},
    }


def send_wecom(webhook: str, items: list[Document]) -> None:
    if not webhook:
        return
    response = requests.post(webhook, json=build_wecom_payload(items), timeout=10)
    response.raise_for_status()


def build_email_body(items: list[Document]) -> str:
    lines = [f"新增 {len(items)} 条公文", ""]
    for item in items:
        lines.append(f"省份：{item.province}")
        lines.append(f"标题：{item.title}")
        lines.append(f"链接：{item.url}")
        lines.append("")
    return "\n".join(lines)


def send_email(settings: dict, items: list[Document]) -> None:
    message = MIMEText(build_email_body(items), "plain", "utf-8")
    message["Subject"] = f"[LawWatch] 新增 {len(items)} 条公文"
    message["From"] = settings["user"]
    message["To"] = ", ".join(settings["to"])
    with smtplib.SMTP_SSL(settings["host"], settings["port"], timeout=20) as smtp:
        smtp.login(settings["user"], settings["password"])
        smtp.sendmail(settings["user"], settings["to"], message.as_string())
```

**Step 4: Add integration helper to `monitor/notify.py`**

```python
def notify_all(items: list[Document]) -> None:
    wecom = os.getenv("WECOM_WEBHOOK", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    auth = os.getenv("SMTP_AUTH_CODE", "").strip()
    to = [x.strip() for x in os.getenv("EMAIL_TO", "").split(",") if x.strip()]
    if wecom:
        send_wecom(wecom, items)
    if user and auth and to:
        send_email(
            {"host": "smtp.qq.com", "port": 465, "user": user, "password": auth, "to": to},
            items,
        )
```

**Step 5: Run test and confirm it passes**

```bash
python -m pytest tests/test_notify.py -v
```

**Step 6: Commit**

```bash
git add monitor/notify.py tests/test_notify.py
git commit -m "feat(monitor): add WeCom and QQ mail notifications"
```

---

## Task 7: 命令行编排器

**Files:**
- Create: `monitor/run.py`
- Create: `tests/test_run.py`

**Interfaces:**
- `run(send: bool = False, max_pages: int = 30) -> dict`

**Step 1: Write failing test**

```python
from monitor.run import run


def test_send_false_does_not_call_notifier(monkeypatch):
    class FakeState:
        def __init__(self):
            self.data = {"list_urls": {}, "documents": {}}

        def update(self, documents, errors):
            return [], False

        def save(self):
            pass

    monkeypatch.setattr("monitor.run.notify_all", lambda items: (_ for _ in ()).throw(AssertionError("should not send")))
    monkeypatch.setattr("monitor.run.load_sites", lambda: [])
    monkeypatch.setattr("monitor.run.StateStore", lambda: FakeState())
    result = run(send=False)
    assert result["new_count"] == 0
```

**Step 2: Run test and confirm failure**

```bash
python -m pytest tests/test_run.py -v
```

**Step 3: Minimal implementation**

```python
import argparse
import json
from pathlib import Path

from .config import load_sites
from .discovery import discover_for_site, is_list_candidate
from .fetcher import BrowserFetcher, HttpFetcher
from .notify import notify_all
from .state import StateStore


def run(send: bool = False, max_pages: int = 30) -> dict:
    sites = load_sites()
    store = StateStore(Path(__file__).resolve().parent / "state.json")
    all_documents = []
    all_errors = {}
    list_urls = store.data.get("list_urls", {})

    for site in sites:
        fetcher = BrowserFetcher() if site.dynamic else HttpFetcher()
        known = tuple(url for url in list_urls.get(site.url, []) if is_list_candidate(url, ""))
        documents, discovered, errors = discover_for_site(
            site, fetcher, known_list_urls=known, max_pages=max_pages
        )
        list_urls[site.url] = [url for url in discovered if is_list_candidate(url, "")]
        all_documents.extend(documents)
        all_errors.update(errors)

    new_items, baseline = store.update(all_documents, all_errors)
    store.data["list_urls"] = list_urls
    store.save()
    if new_items and send and not baseline:
        notify_all(new_items)

    summary = {
        "sites": len(sites),
        "documents": len(all_documents),
        "new_count": len(new_items),
        "baseline": baseline,
        "errors": len(all_errors),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-pages", type=int, default=30)
    args = parser.parse_args()
    run(send=args.send and not args.dry_run, max_pages=args.max_pages)
```

**Step 4: Run test and confirm it passes**

```bash
python -m pytest tests/test_run.py -v
```

**Step 5: Commit**

```bash
git add monitor/run.py tests/test_run.py
git commit -m "feat(monitor): add command-line runner"
```

---

## Task 8: 从 Excel 导出网站清单

**Files:**
- Create: `monitor/sites.csv`

**How:** 使用 `openpyxl` 读取 `新所公示平台.xlsx` 的 `Sheet1`，填写 31 行数据。辽宁、黑龙江、河南使用官方入口 `https://sft.ln.gov.cn/`、`https://sft.hlj.gov.cn/`、`https://sft.henan.gov.cn/`。动态站点按下面的 `dynamic` 列标记。

CSV 列：

```text
province,url,description,notes,dynamic
```

动态站点清单（`dynamic=true`）：

```text
浙江、安徽、海南、广东、云南、四川
```

**Verification:**

```bash
python -c "import csv; rows=list(csv.DictReader(open('monitor/sites.csv', encoding='utf-8-sig'))); assert len(rows)==31"
```

**Commit:**

```bash
git add monitor/sites.csv
git commit -m "feat(monitor): export provincial website seed list"
```

---

## Task 9: GitHub Actions 与部署文档

**Files:**
- Create: `.github/workflows/monitor.yml`
- Create: `README.md`

**Workflow:**

```yaml
name: Monitor provincial legal notices

on:
  schedule:
    - cron: "*/30 * * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  monitor:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: true

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Python dependencies
        run: |
          pip install -r requirements.txt
          python -m playwright install --with-deps chromium

      - name: Run monitor
        run: python -m monitor.run --send
        env:
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_AUTH_CODE: ${{ secrets.SMTP_AUTH_CODE }}
          EMAIL_TO: ${{ secrets.EMAIL_TO }}
          WECOM_WEBHOOK: ${{ secrets.WECOM_WEBHOOK }}

      - name: Commit monitor state
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add monitor/state.json
          if git diff --cached --quiet; then
            echo "No state changes"
          else
            git commit -m "chore(monitor): update dedup state"
            git push
          fi
```

**README 内容：**

1. 在 `Settings → Secrets and variables → Actions` 添加 `SMTP_USER`、`SMTP_AUTH_CODE`、`EMAIL_TO`、`WECOM_WEBHOOK`。
2. 在 GitHub Actions 手动运行一次 `Monitor provincial legal notices`；首次运行只建立基线，不发通知。
3. 让工作流保持启用，每 30 分钟自动运行；发现新增公文后推送企业微信并发送邮件。
4. 本地测试：`python -m monitor.run --dry-run`。
5. 本地测试完整通知：`python -m monitor.run --send`（需要先设好环境变量）。

**Commit:**

```bash
git add .github/workflows/monitor.yml README.md
git commit -m "feat(monitor): add GitHub Actions schedule and setup docs"
```

## 最终验证

```bash
python -m pytest -q
python -m compileall monitor
git status --short
```

验证要求：

- `pytest` 输出全部通过，0 失败。
- `compileall` 退出码为 0。
- `monitor/sites.csv` 有 31 行。
- `monitor/state.json` 保持合法 JSON。
- 本地 `--dry-run` 不会调用通知函数。



