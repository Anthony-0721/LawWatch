from monitor.extractor import canonical_url, is_document_candidate, extract_documents


def test_canonical_url_removes_fragment_but_keeps_query():
    assert canonical_url("/article?id=1#top", "https://example.gov.cn/") == (
        "https://example.gov.cn/article?id=1"
    )


def test_document_candidate_uses_title_hints():
    assert is_document_candidate("https://example.gov.cn/doc/123", "关于设立律师事务所的公告") is True
    assert is_document_candidate("https://example.gov.cn/nav", "首页") is False


def test_extract_documents_deduplicates_urls():
    html = """
    <html><body>
      <a href="/notice/1.shtml">关于设立律师事务所的公告</a>
      <a href="/notice/1.shtml">同样链接</a>
      <a href="/nav">首页</a>
    </body></html>
    """
    docs = extract_documents(html, "https://example.gov.cn/", "测试省", "https://example.gov.cn/")
    assert len(docs) == 1
    assert docs[0].title == "关于设立律师事务所的公告"
