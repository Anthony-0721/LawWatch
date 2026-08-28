import json
import os
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
            loaded = json.loads(self.path.read_text(encoding="utf-8-sig"))
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