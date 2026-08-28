from monitor.run import run
from monitor.models import Document, Site


def test_send_false_does_not_call_notifier(monkeypatch):
    class FakeState:
        def __init__(self):
            self.data = {"list_urls": {}, "documents": {}}

        def update(self, documents, errors):
            return [], False

        def save(self):
            pass

    monkeypatch.setattr("monitor.run.notify_all", lambda items: (_ for _ in ()).throw(AssertionError("should not send")))
    monkeypatch.setattr("monitor.run.load_sites", lambda: [])
    monkeypatch.setattr("monitor.run.StateStore", lambda path: FakeState())
    result = run(send=False)
    assert result["new_count"] == 0


def test_site_failure_does_not_stop_other_sites(monkeypatch):
    class FakeState:
        def __init__(self):
            self.data = {"list_urls": {}, "documents": {}}
            self.received_errors = {}

        def update(self, documents, errors):
            self.received_errors = errors
            return documents, False

        def save(self):
            pass

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

    state = FakeState()
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
    }
