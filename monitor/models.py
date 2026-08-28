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
