from monitor.discovery import discover_for_site
from monitor.models import FetchResult, Site


def test_discovery_extracts_documents_and_list_pages():
    seed = Site(province="测试省", url="https://example.gov.cn/")
    html = """
    <html><body>
      <a href="/xxgk/list.shtml">政务公开列表</a>
      <a href="/article/1.shtml">关于设立律师事务所的公告</a>
    </body></html>
    """
    class FakeFetcher:
        def fetch(self, url):
            return FetchResult(url=url, status=200, html=html, final_url=url)

    docs, list_urls, errors = discover_for_site(seed, FakeFetcher())
    assert any("article/1.shtml" in item.url for item in docs)
    assert "https://example.gov.cn/xxgk/list.shtml" in list_urls
    assert errors == {}
