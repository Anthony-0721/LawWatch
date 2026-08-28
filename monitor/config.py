import csv
import json
import logging
import os
import sys
from pathlib import Path

from .models import Site

PACKAGE_DIR = Path(__file__).resolve().parent

logger = logging.getLogger(__name__)


def load_sites(path: Path | None = None) -> list[Site]:
    if path is None:
        path = default_sites_path()
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


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PACKAGE_DIR.parent


def data_dir() -> Path:
    override = os.getenv("LAWWATCH_DATA_DIR", "").strip()
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return app_root() / "data"
    return PACKAGE_DIR


def default_sites_path() -> Path:
    return data_dir() / "sites.csv"


def default_state_path() -> Path:
    return data_dir() / "state.json"


def load_local_config(path: Path | None = None) -> dict:
    config_path = path or Path(
        os.getenv("LAWWATCH_CONFIG", "") or app_root() / "config.json"
    )
    defaults = {
        "smtp_user": "",
        "smtp_auth_code": "",
        "email_to": "",
        "wecom_webhook": "",
        "schedule_minutes": 30,
    }
    if config_path.exists():
        try:
            parsed = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.error("Invalid local config JSON at %s: %s", config_path, exc)
            return defaults
        if not isinstance(parsed, dict):
            logger.error("Local config at %s is not a JSON object", config_path)
            return defaults
        defaults.update(parsed)
    return defaults
