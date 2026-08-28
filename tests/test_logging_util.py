import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from monitor.logging_util import log_path, setup_logging


def test_log_path_is_monitor_log(tmp_path):
    assert log_path(tmp_path).name == "monitor.log"


def test_setup_logging_installs_rotating_handler_named_monitor_log(tmp_path):
    setup_logging(tmp_path)
    target = log_path(tmp_path)
    handlers = [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, TimedRotatingFileHandler)
        and os.path.abspath(handler.baseFilename) == os.path.abspath(str(target))
    ]
    assert handlers, "expected a TimedRotatingFileHandler for monitor.log"
    handler = handlers[0]
    assert handler.when == "MIDNIGHT"  # logging normalizes when="midnight" to uppercase
    assert handler.interval == 86400  # midnight rollover normalizes interval to one day in seconds
    assert handler.backupCount == 30
    assert handler.encoding == "utf-8"