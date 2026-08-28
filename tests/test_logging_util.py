from pathlib import Path

from monitor.logging_util import log_path


def test_log_path_is_monitor_log(tmp_path):
    assert log_path(tmp_path).name == "monitor.log"
