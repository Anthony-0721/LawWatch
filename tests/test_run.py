from monitor.run import run


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

