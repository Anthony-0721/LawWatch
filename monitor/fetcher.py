import shutil
import ssl
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

from .models import FetchResult

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _compat_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    # Some .gov.cn sites use legacy TLS or invalid certificates; we only read
    # public notices, so relax verification to maximize reachability.
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
    ctx.options |= ssl.OP_NO_SSLv2
    ctx.options |= ssl.OP_NO_SSLv3
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=0")
    except (ssl.SSLError, ValueError):
        try:
            ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        except (ssl.SSLError, ValueError):
            pass
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1
    except Exception:
        pass
    return ctx


class _CompatAdapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        self._pool_connections = connections
        self._pool_maxsize = maxsize
        self._pool_block = block
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=_compat_ssl_context(),
            **pool_kwargs,
        )


def _site_root(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


def _find_curl():
    return shutil.which("curl") or shutil.which("curl.exe")


class HttpFetcher:
    def __init__(self, timeout: int = 10, retries: int = 2):
        self.timeout = timeout
        self.retries = retries

    def _curl_fetch(self, url: str):
        exe = _find_curl()
        if not exe:
            return None, None
        cmd = [
            exe,
            "-k",
            "-L",
            "--max-time",
            str(self.timeout),
            "-A",
            DEFAULT_HEADERS["User-Agent"],
            "-sS",
            "-w",
            "\n%{http_code}",
            url,
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout + 5,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None, None
        output = proc.stdout or ""
        if "\n" not in output:
            return None, None
        html, status_text = output.rsplit("\n", 1)
        try:
            status = int(status_text.strip())
        except ValueError:
            return None, None
        return html, status

    def fetch(self, url: str) -> FetchResult:
        last_error = None
        with requests.Session() as session:
            session.headers.update(DEFAULT_HEADERS)
            if hasattr(session, "mount"):
                session.mount("https://", _CompatAdapter())
                session.mount("http://", _CompatAdapter())
            for attempt in range(self.retries + 1):
                try:
                    response = session.get(url, timeout=self.timeout, allow_redirects=True)
                    # Some WAFs answer 403/412 unless the client first fetches
                    # the site root to obtain a session cookie.
                    if response.status_code in (403, 412) and attempt < self.retries:
                        root = _site_root(url)
                        if root and root != url:
                            try:
                                session.get(root, timeout=self.timeout, allow_redirects=True)
                                session.headers["Referer"] = root
                            except requests.RequestException:
                                pass
                        last_error = f"HTTP {response.status_code}"
                        continue
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

        # Some .gov.cn sites use TLS parameters that the bundled Python/OpenSSL
        # rejects; curl can usually fetch them, so fall back on request failure.
        if last_error:
            html, status = self._curl_fetch(url)
            if status == 200 and html is not None:
                return FetchResult(url=url, status=200, html=html, final_url=url)
            if status is not None:
                last_error = f"HTTP {status}"
        return FetchResult(url=url, error=last_error or "request failed")


class BrowserFetcher:
    def __init__(self, timeout: int = 20):
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