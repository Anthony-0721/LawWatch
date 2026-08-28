from datetime import datetime, timedelta, timezone
from pathlib import Path

from monitor.models import Document
from monitor.state import StateStore


def doc(url: str, title: str = "关于设立律师事务所的公告") -> Document:
    return Document(url=url, title=title, province="测试省", source_url="https://example.gov.cn/")


def test_first_run_is_baseline_and_second_run_finds_new(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    _, baseline = store.update([doc("https://example.gov.cn/1")], {})
    assert baseline is True
    new, baseline = store.update([doc("https://example.gov.cn/1"), doc("https://example.gov.cn/2")], {})
    assert baseline is False
    assert [item.url for item in new] == ["https://example.gov.cn/2"]


def test_state_cleans_records_older_than_30_days(tmp_path: Path):
    store = StateStore(tmp_path / "state.json")
    store.update([doc("https://example.gov.cn/old")], {})
    old_key = "https://example.gov.cn/old"
    store.data["documents"][old_key]["last_seen"] = (
        datetime.now(timezone.utc) - timedelta(days=31)
    ).isoformat()
    store._retain()
    assert old_key not in store.data["documents"]
