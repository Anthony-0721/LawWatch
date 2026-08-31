import sys
import types

from monitor.fetcher import BrowserFetcher, HttpFetcher
from monitor.models import FetchResult


def test_http_fetcher_reduced_defaults():
    fetcher = HttpFetcher()
    assert fetcher.timeout == 10
    assert fetcher.retries == 2


def test_browser_fetcher_reduced_default_timeout():
    fetcher = BrowserFetcher()
    assert fetcher.timeout == 20


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


def test_browser_fetcher_falls_back_to_http_when_launch_fails(monkeypatch, capsys):
    def fail_browser(self):
        raise RuntimeError("playwright launch failed")

    monkeypatch.setattr(BrowserFetcher, "_ensure_browser", fail_browser)
    monkeypatch.setattr(
        "monitor.fetcher.HttpFetcher.fetch",
        lambda self, url: FetchResult(url=url, status=200, html="<html>ok</html>", final_url=url),
    )
    result = BrowserFetcher().fetch("https://example.gov.cn/")
    assert result.status == 200
    assert result.html == "<html>ok</html>"
    assert "falling back to HTTP" in capsys.readouterr().err


def test_browser_fetcher_returns_http_error_when_both_fail(monkeypatch):
    def fail_browser(self):
        raise RuntimeError("browser down")

    monkeypatch.setattr(BrowserFetcher, "_ensure_browser", fail_browser)
    monkeypatch.setattr(
        "monitor.fetcher.HttpFetcher.fetch",
        lambda self, url: FetchResult(url=url, error="http timeout"),
    )
    result = BrowserFetcher().fetch("https://example.gov.cn/")
    assert result.error == "http timeout"


def test_browser_fetcher_reuses_browser_across_fetches(monkeypatch):
    events = []

    class FakePage:
        def goto(self, url, **kwargs):
            events.append(("goto", url))

        def content(self):
            return "<html>ok</html>"

        @property
        def url(self):
            return "https://example.gov.cn/final"

        def close(self):
            events.append("page.close")

    class FakeBrowser:
        def __init__(self):
            events.append("launch")

        def new_page(self, **kwargs):
            return FakePage()

        def close(self):
            events.append("browser.close")

    class FakeChromium:
        def launch(self, headless=True):
            return FakeBrowser()

    class FakePlaywright:
        def __init__(self):
            self.chromium = FakeChromium()

        def stop(self):
            events.append("playwright.stop")

    class FakeSyncPlaywright:
        def start(self):
            return FakePlaywright()

    module = types.ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: FakeSyncPlaywright()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)

    fetcher = BrowserFetcher()
    assert fetcher.fetch("https://example.gov.cn/a").status == 200
    assert fetcher.fetch("https://example.gov.cn/b").status == 200
    assert events.count("launch") == 1
    fetcher.close()
    assert events == [
        "launch",
        ("goto", "https://example.gov.cn/a"),
        "page.close",
        ("goto", "https://example.gov.cn/b"),
        "page.close",
        "browser.close",
        "playwright.stop",
    ]


def test_browser_fetcher_close_stops_playwright_and_browser():
    class FakeBrowser:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class FakePlaywright:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    browser = FakeBrowser()
    playwright = FakePlaywright()
    fetcher = BrowserFetcher()
    fetcher._browser = browser
    fetcher._playwright = playwright
    fetcher.close()
    assert browser.closed is True
    assert playwright.stopped is True
    assert fetcher._browser is None
    assert fetcher._playwright is None
