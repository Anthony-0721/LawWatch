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

    def fetch(self, url: str) -> FetchResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return HttpFetcher(timeout=self.timeout).fetch(url)
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(user_agent=DEFAULT_HEADERS["User-Agent"])
                page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
                html = page.content()
                final_url = page.url
                browser.close()
            return FetchResult(url=url, status=200, html=html, final_url=final_url)
        except Exception as exc:
            return FetchResult(url=url, error=str(exc))
