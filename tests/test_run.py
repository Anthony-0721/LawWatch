import sys
import threading
import time

from monitor.models import Document, FetchResult, Site
from monitor.run import main, run
from monitor.state import StateStore


class FakeState:
    def __init__(self, path):
        self.data = {"list_urls": {}, "documents": {}, "baselined": False}
        self.saved = 0
        self.received_errors = {}

    def update(self, documents, errors, sites_ok=True):
        self.received_errors = errors
        return list(documents), False

    def save(self):
        self.saved += 1


def test_send_false_does_not_call_notifier(monkeypatch):
    state = FakeState(None)
    monkeypatch.setattr(
        "monitor.run.notify_all",
        lambda items: (_ for _ in ()).throw(AssertionError("should not send")),
    )
    monkeypatch.setattr("monitor.run.load_sites", lambda: [])
    monkeypatch.setattr("monitor.run.StateStore", lambda path: state)
    result = run(send=False)
    assert result["new_count"] == 0
    assert result["notifications_ok"] is True
    assert result["persisted"] is True


def test_site_failure_does_not_stop_other_sites(monkeypatch):
    sites = [
        Site(province="浙江", url="https://example.com/bad"),
        Site(province="广东", url="https://example.com/good"),
    ]
    good_document = Document(
        url="https://example.com/good/doc/1",
        title="测试公文",
        province="广东",
        source_url="https://example.com/good",
    )

    def fake_discover(site, fetcher, known_list_urls=(), max_pages=30):
        if site.url == sites[0].url:
            raise RuntimeError("boom")
        return [good_document], [site.url], {}

    state = FakeState(None)
    monkeypatch.setattr("monitor.run.load_sites", lambda: sites)
    monkeypatch.setattr("monitor.run.StateStore", lambda path: state)
    monkeypatch.setattr("monitor.run.discover_for_site", fake_discover)

    result = run(send=False)
    assert state.received_errors == {sites[0].url: "boom"}
    assert result == {
        "sites": 2,
        "documents": 1,
        "new_count": 1,
        "baseline": False,
        "errors": 1,
        "notifications_ok": True,
        "persisted": True,
    }


def test_sites_crawl_concurrently_and_failure_is_isolated(monkeypatch):
    sites = [
        Site(province="浙江", url="https://example.com/bad"),
        Site(province="广东", url="https://example.com/good-one"),
        Site(province="海南", url="https://example.com/good-two"),
    ]
    documents = {
        sites[1].url: Document(
            url="https://example.com/good-one/doc/1",
            title="测试公文一",
            province="广东",
            source_url=sites[1].url,
        ),
        sites[2].url: Document(
            url="https://example.com/good-two/doc/1",
            title="测试公文二",
            province="海南",
            source_url=sites[2].url,
        ),
    }
    lock = threading.Lock()
    active = 0
    max_active = 0
    threads_seen = set()

    def fake_discover(site, fetcher, known_list_urls=(), max_pages=30):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
            threads_seen.add(threading.get_ident())
        try:
            time.sleep(0.05)
        finally:
            with lock:
                active -= 1
        if site.url == sites[0].url:
            raise RuntimeError("boom")
        return [documents[site.url]], [site.url], {}

    state = FakeState(None)
    monkeypatch.setattr("monitor.run.load_sites", lambda: sites)
    monkeypatch.setattr("monitor.run.StateStore", lambda path: state)
    monkeypatch.setattr("monitor.run.discover_for_site", fake_discover)

    result = run(send=False)
    assert max_active >= 2
    assert len(threads_seen) >= 2
    assert state.received_errors == {sites[0].url: "boom"}
    assert result == {
        "sites": 3,
        "documents": 2,
        "new_count": 2,
        "baseline": False,
        "errors": 1,
        "notifications_ok": True,
        "persisted": True,
    }


def test_notify_before_save_and_skip_save_when_notifications_fail(monkeypatch):
    site = Site(province="海南", url="https://example.com/dynamic", dynamic=True)
    document = Document(
        url="https://example.com/doc/1",
        title="关于律师事务所设立的公告",
        province="海南",
        source_url=site.url,
    )

    def fake_discover(site_arg, fetcher, known_list_urls=(), max_pages=30):
        return [document], [site_arg.url], {}

    state = FakeState(None)
    events = []

    def failing_notify(items):
        events.append("notify")
        return False

    monkeypatch.setattr("monitor.run.load_sites", lambda: [site])
    monkeypatch.setattr("monitor.run.StateStore", lambda path: state)
    monkeypatch.setattr("monitor.run.discover_for_site", fake_discover)
    monkeypatch.setattr("monitor.run.notify_all", failing_notify)

    result = run(send=True)
    assert events == ["notify"]
    assert state.saved == 0
    assert result["notifications_ok"] is False
    assert result["persisted"] is False
    assert result["new_count"] == 1


def test_notify_success_persists_state_after_notifying(monkeypatch):
    site = Site(province="海南", url="https://example.com/dynamic", dynamic=True)
    document = Document(
        url="https://example.com/doc/1",
        title="关于律师事务所设立的公告",
        province="海南",
        source_url=site.url,
    )

    def fake_discover(site_arg, fetcher, known_list_urls=(), max_pages=30):
        return [document], [site_arg.url], {}

    state = FakeState(None)
    events = []

    def ok_notify(items):
        events.append("notify")
        return True

    def save_probe():
        events.append("save")
        state.saved += 1

    state.save = save_probe
    monkeypatch.setattr("monitor.run.load_sites", lambda: [site])
    monkeypatch.setattr("monitor.run.StateStore", lambda path: state)
    monkeypatch.setattr("monitor.run.discover_for_site", fake_discover)
    monkeypatch.setattr("monitor.run.notify_all", ok_notify)

    result = run(send=True)
    assert events == ["notify", "save"]
    assert result["notifications_ok"] is True
    assert result["persisted"] is True


def test_first_successful_run_suppresses_notifications_but_persists(monkeypatch):
    class BaselineState(FakeState):
        def update(self, documents, errors, sites_ok=True):
            return list(documents), True

    site = Site(province="浙江", url="https://example.com/")
    document = Document(
        url="https://example.com/doc/1",
        title="关于律师事务所设立的公告",
        province="浙江",
        source_url=site.url,
    )

    def fake_discover(site_arg, fetcher, known_list_urls=(), max_pages=30):
        return [document], [site_arg.url], {}

    state = BaselineState(None)
    events = []

    def boom_notify(items):
        events.append("notify")
        return False

    monkeypatch.setattr("monitor.run.load_sites", lambda: [site])
    monkeypatch.setattr("monitor.run.StateStore", lambda path: state)
    monkeypatch.setattr("monitor.run.discover_for_site", fake_discover)
    monkeypatch.setattr("monitor.run.notify_all", boom_notify)

    result = run(send=True)
    assert events == []
    assert state.saved == 1
    assert result["baseline"] is True
    assert result["notifications_ok"] is True


def test_dry_run_never_persists_state(monkeypatch, capsys):
    state = FakeState(None)
    monkeypatch.setattr("monitor.run.load_sites", lambda: [])
    monkeypatch.setattr("monitor.run.StateStore", lambda path: state)
    result = run(persist=False)
    assert state.saved == 0
    assert result["persisted"] is False
    assert "state was NOT persisted" in capsys.readouterr().err


def test_run_closes_browser_fetcher_in_finally(monkeypatch):
    site = Site(province="海南", url="https://example.com/dynamic", dynamic=True)
    instances = []

    class FakeBrowserFetcher:
        def __init__(self):
            self.closed = False
            instances.append(self)

        def fetch(self, url):
            return FetchResult(url=url, status=200, html="<html></html>", final_url=url)

        def close(self):
            self.closed = True

    def fake_discover(site_arg, fetcher, known_list_urls=(), max_pages=30):
        raise RuntimeError("boom")

    monkeypatch.setattr("monitor.run.load_sites", lambda: [site])
    monkeypatch.setattr("monitor.run.BrowserFetcher", FakeBrowserFetcher)
    monkeypatch.setattr("monitor.run.StateStore", lambda path: FakeState(None))
    monkeypatch.setattr("monitor.run.discover_for_site", fake_discover)

    result = run(send=False)
    assert result["errors"] == 1
    assert len(instances) == 1
    assert instances[0].closed is True


def test_main_returns_nonzero_when_notifications_fail(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["monitor.run", "--send"])
    monkeypatch.setattr(
        "monitor.run.run",
        lambda send=False, max_pages=30, persist=True, max_workers=None: {
            "notifications_ok": False
        },
    )
    assert main() == 1
    assert "exiting with status 1" in capsys.readouterr().err


def test_main_returns_zero_when_notifications_ok(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["monitor.run", "--send"])
    monkeypatch.setattr(
        "monitor.run.run",
        lambda send=False, max_pages=30, persist=True, max_workers=None: {
            "notifications_ok": True
        },
    )
    assert main() == 0


def test_main_dry_run_passes_persist_false_and_send_false(monkeypatch):
    received = {}

    def fake_run(**kwargs):
        received.update(kwargs)
        return {"notifications_ok": True}

    monkeypatch.setattr(sys, "argv", ["monitor.run", "--dry-run", "--max-pages", "15"])
    monkeypatch.setattr("monitor.run.run", fake_run)
    assert main() == 0
    assert received == {
        "send": False,
        "max_pages": 15,
        "persist": False,
        "max_workers": None,
    }


def test_empty_first_run_baselines_and_second_run_notifies(tmp_path, monkeypatch):
    path = tmp_path / "state.json"

    def make_store(_):
        return StateStore(path)

    site = Site(province="浙江", url="https://example.com/")
    document = Document(
        url="https://example.com/doc/1",
        title="关于律师事务所设立的公告",
        province="浙江",
        source_url=site.url,
    )
    notified = []

    def fake_notify(items):
        notified.append(items)
        return True

    monkeypatch.setattr("monitor.run.StateStore", make_store)
    monkeypatch.setattr("monitor.run.load_sites", lambda: [site])
    monkeypatch.setattr("monitor.run.notify_all", fake_notify)

    def empty_discover(site_arg, fetcher, known_list_urls=(), max_pages=30):
        return [], [site_arg.url], {}

    monkeypatch.setattr("monitor.run.discover_for_site", empty_discover)
    first = run(send=True)
    assert first["baseline"] is True
    assert first["new_count"] == 0
    assert notified == []

    def doc_discover(site_arg, fetcher, known_list_urls=(), max_pages=30):
        return [document], [site_arg.url], {}

    monkeypatch.setattr("monitor.run.discover_for_site", doc_discover)
    second = run(send=True)
    assert second["baseline"] is False
    assert [item.url for item in notified[0]] == [document.url]
