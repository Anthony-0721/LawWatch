import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def log_path(log_dir: Path) -> Path:
    return log_dir / "monitor.log"


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    target = log_path(log_dir)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for handler in root.handlers:
        if isinstance(handler, TimedRotatingFileHandler) and (
            os.path.abspath(handler.baseFilename) == os.path.abspath(str(target))
        ):
            return
    handler = TimedRotatingFileHandler(
        target,
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(handler)