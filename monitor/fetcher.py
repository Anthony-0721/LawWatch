import sys

import requests

from .models import FetchResult

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class HttpFetcher:
    def __init__(self, timeout: int = 20, retries: int = 2):
        self.timeout = timeout
        self.retries = retries

    def fetch(self, url: str) -> FetchResult:
        last_error = None
        with requests.Session() as session:
            session.headers.update(DEFAULT_HEADERS)
            for _ in range(self.retries + 1):
                try:
                    response = session.get(url, timeout=self.timeout, allow_redirects=True)
                    if response.status_code >= 500:
                        last_error = f"HTTP {response.status_code}"
                        continue
                    return FetchResult(
                        url=url,
                        status=response.status_code,
                        html=response.text,
                        final_url=response.url,
                    )
                except requests.RequestException as exc:
                    last_error = str(exc)
        return FetchResult(url=url, error=last_error or "request failed")


class BrowserFetcher:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._http = HttpFetcher(timeout=self.timeout)
        self._playwright = None
        self._browser = None
        self._playwright_error = None

    def _ensure_browser(self):
        if self._browser is not None:
            return self._browser
        if self._playwright_error is not None:
            raise self._playwright_error
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            self._playwright_error = RuntimeError(f"Playwright is not available: {exc}")
            raise self._playwright_error
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=True)
        except Exception:
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
            self._playwright = None
            raise
        return self._browser

    def fetch(self, url: str) -> FetchResult:
        try:
            browser = self._ensure_browser()
            page = browser.new_page(user_agent=DEFAULT_HEADERS["User-Agent"])
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                html = page.content()
                final_url = page.url
            finally:
                try:
                    page.close()
                except Exception:
                    pass
            return FetchResult(url=url, status=200, html=html, final_url=final_url)
        except Exception as exc:
            print(
                f"[fetcher] browser failed for {url}: {exc}; falling back to HTTP",
                file=sys.stderr,
            )
            return self._http.fetch(url)

    def close(self) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None