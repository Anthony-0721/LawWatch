from monitor.fetcher import HttpFetcher
from monitor.models import FetchResult


def test_http_fetcher_returns_html(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "<html>ok</html>"
        url = "https://example.gov.cn/ok"

    class FakeSession:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("monitor.fetcher.requests.Session", lambda: FakeSession())
    result = HttpFetcher().fetch("https://example.gov.cn/")
    assert result.status == 200
    assert result.html == "<html>ok</html>"
