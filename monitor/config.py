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
