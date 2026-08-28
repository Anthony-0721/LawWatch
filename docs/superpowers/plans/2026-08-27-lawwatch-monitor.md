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
- 本地 `--dry-run` 不发送通知、不写 `monitor/state.json` 状态文件。

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


def test_canonical_url_removes_inert_fragment_but_keeps_query():
    assert canonical_url("/article?id=1#top", "https://example.gov.cn/") == (
        "https://example.gov.cn/article?id=1"
    )


def test_canonical_url_preserves_spa_hash_routes():
    assert canonical_url("/#/detail/1", "https://example.gov.cn/") == (
        "https://example.gov.cn/#/detail/1"
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
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .models import Document

SKIP_EXTENSIONS = {
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".webp", ".mp4", ".mp3", ".wav", ".avi",
}

DOCUMENT_HINTS = (
    "公告", "公示", "通知", "公文", "政策", "文件", "条例", "办法",
    "规定", "意见", "决定", "批复", "报告", "招聘", "招考", "备案",
)

def normalize_text(value: str) -> str:
    return " ".join(value.split())


def canonical_url(url: str, base_url: str) -> str:
    parsed = urlparse(urljoin(base_url, url))
    host = parsed.hostname
    if host:
        host = host.lower()
        port = parsed.port
        is_default_port = (parsed.scheme == "http" and port == 80) or (
            parsed.scheme == "https" and port == 443
        )
        netloc = host if port is None or is_default_port else f"{host}:{port}"
        parsed = parsed._replace(netloc=netloc)
    if not parsed.fragment.startswith("/"):
        parsed = parsed._replace(fragment="")
    return parsed.geturl()


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
- `BrowserFetcher.close() -> None`（实例内复用同一浏览器，结束时显式关闭）

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
        self._http = HttpFetcher(timeout=self.timeout)
        self._playwright = None
        self._browser = None
        self._playwright_error = None

    def _ensure_browser(self):
        if self._browser is not None:
            return self._browser
        if self._playwright_error is not None:
            raise self._playwright_error
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            self._playwright_error = RuntimeError(f"Playwright is not available: {exc}")
            raise self._playwright_error
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=True)
        except Exception:
            self._playwright.stop()
            self._playwright = None
            raise
        return self._browser

    def fetch(self, url: str) -> FetchResult:
        try:
            browser = self._ensure_browser()
            page = browser.new_page(user_agent=DEFAULT_HEADERS["User-Agent"])
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                html = page.content()
                final_url = page.url
            finally:
                page.close()
            return FetchResult(url=url, status=200, html=html, final_url=final_url)
        except Exception as exc:
            print(f"[fetcher] browser failed for {url}: {exc}; falling back to HTTP")
            return self._http.fetch(url)

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
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
- `StateStore.update(documents, errors, sites_ok) -> tuple[list[Document], bool]`
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
    _, baseline = store.update([doc("https://example.gov.cn/1")], {}, sites_ok=True)
    assert baseline is True
    assert store.data["baselined"] is True
    new, baseline = store.update(
        [doc("https://example.gov.cn/1"), doc("https://example.gov.cn/2")], {}, sites_ok=True
    )
    assert baseline is False
    assert [item.url for item in new] == ["https://example.gov.cn/2"]


def test_empty_first_run_still_baselines_and_next_run_notifies_new(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    new, baseline = store.update([], {}, sites_ok=True)
    assert baseline is True
    assert store.data["baselined"] is True
    new, baseline = store.update([doc("https://example.gov.cn/later")], {}, sites_ok=True)
    assert baseline is False
    assert [item.url for item in new] == ["https://example.gov.cn/later"]


def test_all_sites_failed_leaves_state_unbaselined(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    _, baseline = store.update([], {"https://example.gov.cn/": "boom"}, sites_ok=False)
    assert baseline is True
    assert store.data["baselined"] is False


def test_state_cleans_records_older_than_30_days(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    store.update([doc("https://example.gov.cn/old")], {}, sites_ok=True)
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
        self.data = {"documents": {}, "list_urls": {}, "errors": {}, "baselined": False}
        if self.path.exists():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key in ("documents", "list_urls", "errors"):
                    value = loaded.get(key)
                    if isinstance(value, dict):
                        self.data[key] = value
                self.data["baselined"] = bool(loaded.get("baselined", False))

    def update(
        self,
        documents: list[Document],
        errors: dict[str, str],
        sites_ok: bool,
    ) -> tuple[list[Document], bool]:
        baseline = not self.data["baselined"]
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
        if sites_ok:
            self.data["baselined"] = True
        self._retain()
        return new_items, baseline

    def _retain(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        stale = [
            url
            for url, record in self.data["documents"].items()
            if parse_iso(record["last_seen"]) < cutoff
        ]
        for url in stale:
            self.data["documents"].pop(url, None)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_name(self.path.name + ".tmp")
        tmp_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, self.path)
```

`monitor/state.json` initial content:

```json
{
  "documents": {},
  "list_urls": {},
  "errors": {},
  "baselined": false
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


WECOM_MAX_CONTENT_BYTES = 1800


def build_wecom_payload(items: list[Document]) -> dict:
    header = f"LawWatch 发现 {len(items)} 条新公文"
    lines = [header]
    shown = 0
    for item in items:
        candidate = f"- {item.province}：{item.title}\n  {item.url}"
        remaining = len(items) - shown - 1
        reserve = (
            len(f"\n(仅显示前 {shown + 1} 条，详见邮件)".encode("utf-8")) if remaining else 0
        )
        trial = "\n".join([*lines, candidate]).encode("utf-8")
        if len(trial) + reserve > WECOM_MAX_CONTENT_BYTES:
            break
        lines.append(candidate)
        shown += 1
    if shown < len(items):
        lines.append(f"(仅显示前 {shown} 条，详见邮件)")
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
def notify_all(items: list[Document]) -> bool:
    wecom = os.getenv("WECOM_WEBHOOK", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    auth = os.getenv("SMTP_AUTH_CODE", "").strip()
    to = [x.strip() for x in os.getenv("EMAIL_TO", "").split(",") if x.strip()]
    any_succeeded = False
    if wecom:
        try:
            send_wecom(wecom, items)
            any_succeeded = True
        except Exception as exc:
            print(f"[notify] WeCom notification failed: {exc}", file=sys.stderr)
    if user and auth and to:
        try:
            send_email(
                {"host": "smtp.qq.com", "port": 465, "user": user, "password": auth, "to": to},
                items,
            )
            any_succeeded = True
        except Exception as exc:
            print(f"[notify] email notification failed: {exc}", file=sys.stderr)
    return any_succeeded
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
- `run(send: bool = False, max_pages: int = 30, persist: bool = True) -> dict`

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


def run(send: bool = False, max_pages: int = 30, persist: bool = True) -> dict:
    sites = load_sites()
    store = StateStore(Path(__file__).resolve().parent / "state.json")
    all_documents = []
    all_errors = {}
    list_urls = store.data.get("list_urls", {})
    any_site_ok = False

    browser_fetcher = BrowserFetcher() if any(site.dynamic for site in sites) else None
    try:
        for site in sites:
            try:
                fetcher = browser_fetcher if site.dynamic else HttpFetcher()
                known = tuple(url for url in list_urls.get(site.url, []) if is_list_candidate(url, ""))
                documents, discovered, errors = discover_for_site(
                    site, fetcher, known_list_urls=known, max_pages=max_pages
                )
                if not errors:
                    any_site_ok = True
                list_urls[site.url] = [url for url in discovered if is_list_candidate(url, "")]
                all_documents.extend(documents)
                all_errors.update(errors)
            except Exception as exc:
                all_errors[site.url] = str(exc)
    finally:
        if browser_fetcher is not None:
            browser_fetcher.close()

    new_items, baseline = store.update(all_documents, all_errors, sites_ok=any_site_ok)
    store.data["list_urls"] = list_urls

    notifications_ok = True
    if new_items and send and not baseline:
        notifications_ok = notify_all(new_items)

    persisted = False
    if persist and notifications_ok:
        store.save()
        persisted = True

    summary = {
        "sites": len(sites),
        "documents": len(all_documents),
        "new_count": len(new_items),
        "baseline": baseline,
        "errors": len(all_errors),
        "notifications_ok": notifications_ok,
        "persisted": persisted,
    }
    print(json.dumps(summary, ensure_ascii=False))
    if not persist:
        would_notify = bool(new_items and send and not baseline)
        print(
            "dry run: state was NOT persisted; "
            f"baseline={baseline}, would_notify={would_notify}, new_items={len(new_items)}",
            file=sys.stderr,
        )
    elif not notifications_ok:
        print(
            "notification failure: no configured channel succeeded; dedup state was NOT saved. "
            "The batch will be retried on the next run.",
            file=sys.stderr,
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-pages", type=int, default=30)
    args = parser.parse_args()
    result = run(
        send=args.send and not args.dry_run,
        max_pages=args.max_pages,
        persist=not args.dry_run,
    )
    if result.get("notifications_ok") is False:
        print("monitor: notifications failed; exiting with status 1", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
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

concurrency:
  group: monitor
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  monitor:
    runs-on: ubuntu-latest
    timeout-minutes: 20
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
        run: python -m monitor.run --send --max-pages 15
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
            exit 0
          fi
          git commit -m "chore(monitor): update dedup state"
          attempt=0
          while ! git pull --rebase origin "${GITHUB_REF_NAME}"; do
            attempt=$((attempt + 1))
            if [ "${attempt}" -ge 3 ]; then
              echo "::error::Could not pull/rebase the latest branch changes after 3 attempts; the state commit was NOT pushed. Run the workflow again to retry."
              exit 1
            fi
            echo "Pull/rebase failed (attempt ${attempt}); retrying in 5 seconds"
            sleep 5
          done
          git push
```

**README 内容：**

1. 在 `Settings → Secrets and variables → Actions` 添加 `SMTP_USER`、`SMTP_AUTH_CODE`、`EMAIL_TO`、`WECOM_WEBHOOK`。
2. 在 GitHub Actions 手动运行一次 `Monitor provincial legal notices`；首次运行只建立基线，不发通知。
3. 让工作流保持启用，每 30 分钟自动运行；发现新增公文后推送企业微信并发送邮件。
4. 本地测试：`python -m monitor.run --dry-run --max-pages 1`（不发送通知、不写 `monitor/state.json`）。
5. 本地测试完整通知：`python -m monitor.run --send`（需要先设好环境变量）。
6. 注意：GitHub 托管 Runner 可能被部分国内政府网站限流或屏蔽；首次真实运行后核对日志与 `monitor/state.json`（`baselined` 是否变为 `true`），必要时改用中国大陆自托管 Runner 或配置代理。

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
- 本地 `--dry-run` 不会调用通知函数，也不会写入 `monitor/state.json`。



