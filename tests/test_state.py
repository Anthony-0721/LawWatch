import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from monitor.models import Document
from monitor.state import StateStore


def doc(url: str, title: str = "关于设立律师事务所的公告") -> Document:
    return Document(url=url, title=title, province="测试省", source_url="https://example.gov.cn/")


def test_first_run_is_baseline_and_second_run_finds_new(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    _, baseline = store.update([doc("https://example.gov.cn/1")], {}, sites_ok=True)
    assert baseline is True
    assert store.data["baselined"] is True
    new, baseline = store.update(
        [doc("https://example.gov.cn/1"), doc("https://example.gov.cn/2")], {}, sites_ok=True
    )
    assert baseline is False
    assert [item.url for item in new] == ["https://example.gov.cn/2"]


def test_empty_first_run_still_baselines_and_next_run_notifies_new(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    new, baseline = store.update([], {}, sites_ok=True)
    assert baseline is True
    assert new == []
    assert store.data["baselined"] is True

    new, baseline = store.update([doc("https://example.gov.cn/later")], {}, sites_ok=True)
    assert baseline is False
    assert [item.url for item in new] == ["https://example.gov.cn/later"]


def test_all_sites_failed_leaves_state_unbaselined(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    new, baseline = store.update([], {"https://example.gov.cn/": "boom"}, sites_ok=False)
    assert baseline is True
    assert new == []
    assert store.data["baselined"] is False

    new, baseline = store.update([doc("https://example.gov.cn/1")], {}, sites_ok=True)
    assert baseline is True
    assert store.data["baselined"] is True


def test_state_cleans_records_older_than_30_days(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    store.update([doc("https://example.gov.cn/old")], {}, sites_ok=True)
    old_key = "https://example.gov.cn/old"
    store.data["documents"][old_key]["last_seen"] = (
        datetime.now(timezone.utc) - timedelta(days=31)
    ).isoformat()
    store._retain()
    assert old_key not in store.data["documents"]


def test_load_is_defensive_about_missing_keys(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"documents": {"https://example.gov.cn/1": {"last_seen": "now"}}}),
        encoding="utf-8",
    )
    store = StateStore(path)
    assert store.data["documents"]["https://example.gov.cn/1"]["last_seen"] == "now"
    assert store.data["list_urls"] == {}
    assert store.data["errors"] == {}
    assert store.data["baselined"] is False


def test_save_is_atomic_and_writes_valid_json(tmp_path: Path):
    path = tmp_path / "state.json"
    store = StateStore(path)
    store.update([doc("https://example.gov.cn/1")], {}, sites_ok=True)
    store.save()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["baselined"] is True
    assert data["documents"]["https://example.gov.cn/1"]["title"] == "关于设立律师事务所的公告"
    assert not list(tmp_path.glob("state.json.*tmp*"))

def test_load_state_with_utf8_bom(tmp_path: Path):
    path = tmp_path / "state.json"
    path.write_text(
        '\ufeff{"documents": {}, "list_urls": {}, "errors": {}}',
        encoding="utf-8",
    )
    store = StateStore(path)
    assert store.data["documents"] == {}
    assert store.data["list_urls"] == {}
    assert store.data["errors"] == {}
    assert store.data["baselined"] is False
