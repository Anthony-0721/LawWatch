import json
import os
import sys
from pathlib import Path

import monitor.notify as notify
from monitor import config as config_module
from monitor.config import (
    app_root,
    data_dir,
    default_sites_path,
    default_state_path,
    load_local_config,
)
from monitor.models import Document, Site
from monitor.run import main, run
from monitor.state import StateStore


def items():
    return [
        Document(
            url="https://example.gov.cn/news/1",
            title="关于设立律师事务所的公告",
            province="测试省",
            source_url="https://example.gov.cn/list",
        )
    ]


def test_local_config_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWWATCH_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path
    assert default_sites_path() == tmp_path / "sites.csv"
    assert default_state_path() == tmp_path / "state.json"


def test_load_local_config_returns_defaults_when_missing():
    config = load_local_config(Path("missing.json"))
    assert config["smtp_user"] == ""
    assert config["schedule_minutes"] == 30


def test_load_local_config_reads_values_from_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"smtp_user": "sender@example.com", "schedule_minutes": 15}),
        encoding="utf-8",
    )
    config = load_local_config(path)
    assert config["smtp_user"] == "sender@example.com"
    assert config["schedule_minutes"] == 15
    assert config["wecom_webhook"] == ""


def test_load_local_config_uses_lawwatch_config_env(tmp_path, monkeypatch):
    path = tmp_path / "custom.json"
    path.write_text(
        json.dumps({"wecom_webhook": "https://env.example/hook"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("LAWWATCH_CONFIG", str(path))
    config = load_local_config()
    assert config["wecom_webhook"] == "https://env.example/hook"


def test_load_local_config_logs_and_falls_back_on_invalid_json(tmp_path, caplog):
    path = tmp_path / "config.json"
    path.write_text("{not valid json", encoding="utf-8")
    config = load_local_config(path)
    assert config["smtp_user"] == ""
    assert config["schedule_minutes"] == 30
    assert "Invalid local config JSON" in caplog.text


def test_app_root_and_data_dir_use_executable_dir_when_frozen(tmp_path, monkeypatch):
    exe_dir = tmp_path / "app"
    monkeypatch.delenv("LAWWATCH_DATA_DIR", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "LawWatchMonitor.exe"))
    assert app_root() == exe_dir
    assert data_dir() == exe_dir / "data"
    assert default_sites_path() == exe_dir / "data" / "sites.csv"
    assert default_state_path() == exe_dir / "data" / "state.json"


def test_data_dir_keeps_package_paths_when_not_frozen(monkeypatch):
    monkeypatch.delenv("LAWWATCH_DATA_DIR", raising=False)
    assert data_dir() == config_module.PACKAGE_DIR
    assert default_state_path() == config_module.PACKAGE_DIR / "state.json"


def test_notify_all_prefers_local_config_over_env(monkeypatch):
    monkeypatch.setenv("WECOM_WEBHOOK", "https://env.example/hook")
    monkeypatch.setenv("SMTP_USER", "env@example.com")
    monkeypatch.setenv("SMTP_AUTH_CODE", "env-auth")
    monkeypatch.setenv("EMAIL_TO", "env-to@example.com")

    wecom_calls = []
    email_settings = []
    monkeypatch.setattr(
        notify, "send_wecom", lambda webhook, items: wecom_calls.append(webhook)
    )
    monkeypatch.setattr(
        notify, "send_email", lambda settings, items: email_settings.append(settings)
    )

    local_config = {
        "wecom_webhook": "https://local.example/hook",
        "smtp_user": "local@example.com",
        "smtp_auth_code": "local-auth",
        "email_to": "local-to@example.com",
    }
    assert notify.notify_all(items(), local_config) is True
    assert wecom_calls == ["https://local.example/hook"]
    assert email_settings[0]["user"] == "local@example.com"
    assert email_settings[0]["password"] == "local-auth"
    assert email_settings[0]["to"] == ["local-to@example.com"]


def test_notify_all_falls_back_to_env_for_empty_config_fields(monkeypatch):
    monkeypatch.delenv("WECOM_WEBHOOK", raising=False)
    monkeypatch.setenv("SMTP_USER", "env@example.com")
    monkeypatch.setenv("SMTP_AUTH_CODE", "env-auth")
    monkeypatch.setenv("EMAIL_TO", "env-to@example.com")

    email_settings = []
    monkeypatch.setattr(
        notify, "send_email", lambda settings, items: email_settings.append(settings)
    )

    empty_config = {"smtp_user": "", "smtp_auth_code": "", "email_to": ""}
    assert notify.notify_all(items(), empty_config) is True
    assert email_settings[0]["user"] == "env@example.com"
    assert email_settings[0]["to"] == ["env-to@example.com"]


def test_send_test_notification_uses_local_config(monkeypatch):
    monkeypatch.delenv("WECOM_WEBHOOK", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_AUTH_CODE", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)

    email_settings = []
    monkeypatch.setattr(
        notify, "send_email", lambda settings, items: email_settings.append(settings)
    )

    local_config = {
        "smtp_user": "local@example.com",
        "smtp_auth_code": "local-auth",
        "email_to": "local-to@example.com",
    }
    assert notify.send_test_notification(local_config) is True
    assert email_settings[0]["user"] == "local@example.com"


def test_run_passes_local_config_to_notify_all(tmp_path, monkeypatch):
    site = Site(province="海南", url="https://example.com/dynamic", dynamic=True)
    document = Document(
        url="https://example.com/doc/1",
        title="测试公文",
        province="海南",
        source_url=site.url,
    )

    def fake_discover(site_arg, fetcher, known_list_urls=(), max_pages=30):
        return [document], [site_arg.url], {}

    received = {}

    def record_notify(new_items, local_config):
        received["new_items"] = new_items
        received["local_config"] = local_config
        return True

    store = StateStore(tmp_path / "state.json")
    store.data["baselined"] = True
    monkeypatch.setattr("monitor.run.load_sites", lambda: [site])
    monkeypatch.setattr("monitor.run.StateStore", lambda path: store)
    monkeypatch.setattr("monitor.run.discover_for_site", fake_discover)
    monkeypatch.setattr("monitor.run.notify_all", record_notify)

    local_config = {"smtp_user": "local@example.com"}
    result = run(send=True, local_config=local_config)
    assert result["notifications_ok"] is True
    assert received["local_config"] is local_config
    assert [item.url for item in received["new_items"]] == [document.url]


def test_main_loads_config_flag_and_passes_to_run(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"smtp_user": "cli@example.com", "schedule_minutes": 45}),
        encoding="utf-8",
    )
    received = {}

    def fake_run(**kwargs):
        received.update(kwargs)
        return {"notifications_ok": True}

    monkeypatch.setattr(
        sys, "argv", ["monitor.run", "--send", "--config", str(config_path)]
    )
    monkeypatch.setattr("monitor.run.run", fake_run)
    assert main() == 0
    assert received["local_config"]["smtp_user"] == "cli@example.com"
    assert received["local_config"]["schedule_minutes"] == 45


def test_main_loads_config_from_environment_path(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"wecom_webhook": "https://env.example/hook"}),
        encoding="utf-8",
    )
    received = {}

    def fake_run(**kwargs):
        received.update(kwargs)
        return {"notifications_ok": True}

    monkeypatch.setenv("LAWWATCH_CONFIG", str(config_path))
    monkeypatch.setattr(sys, "argv", ["monitor.run", "--send"])
    monkeypatch.setattr("monitor.run.run", fake_run)
    assert main() == 0
    assert received["local_config"]["wecom_webhook"] == "https://env.example/hook"


def test_main_data_dir_flag_sets_data_directory(tmp_path, monkeypatch):
    data = tmp_path / "custom-data"
    received = {}

    def fake_run(**kwargs):
        received.update(kwargs)
        return {"notifications_ok": True}

    monkeypatch.setenv("LAWWATCH_DATA_DIR", "")
    monkeypatch.setattr(sys, "argv", ["monitor.run", "--data-dir", str(data)])
    monkeypatch.setattr("monitor.run.run", fake_run)
    assert main() == 0
    assert os.environ["LAWWATCH_DATA_DIR"] == str(data)
    assert data_dir() == data
    assert received["persist"] is True



def test_load_local_config_warns_when_explicit_path_missing(tmp_path, caplog):
    missing = tmp_path / "does-not-exist.json"
    config = load_local_config(missing)
    assert config["smtp_user"] == ""
    assert config["schedule_minutes"] == 30
    assert "not found" in caplog.text
