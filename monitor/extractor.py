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
        try:
            href = canonical_url(anchor.get("href", ""), base_url)
        except ValueError:
            continue
        if not href.startswith(("http://", "https://")):
            continue
        parsed = urlparse(href)
        if parsed.netloc != urlparse(canonical_url(base_url, base_url)).netloc:
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