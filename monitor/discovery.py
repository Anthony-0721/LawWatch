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
    reached = set()
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
        reached.add(url)
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
    return unique_docs, list(reached), errors