import logging
from pathlib import Path


def log_path(log_dir: Path) -> Path:
    return log_dir / "monitor.log"


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_path(log_dir),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
