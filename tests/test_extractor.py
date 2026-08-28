from monitor.extractor import canonical_url, is_document_candidate, extract_documents, extract_links


def test_canonical_url_removes_inert_fragment_but_keeps_query():
    assert canonical_url("/article?id=1#top", "https://example.gov.cn/") == (
        "https://example.gov.cn/article?id=1"
    )


def test_canonical_url_preserves_spa_hash_routes():
    assert canonical_url("/#/detail/1", "https://example.gov.cn/") == (
        "https://example.gov.cn/#/detail/1"
    )
    assert canonical_url("#/home?tab=news", "https://example.gov.cn/app/") == (
        "https://example.gov.cn/app/#/home?tab=news"
    )
    assert canonical_url("/page#/publics/notice", "https://example.gov.cn/") == (
        "https://example.gov.cn/page#/publics/notice"
    )


def test_canonical_url_normalizes_host_case_and_default_port():
    assert canonical_url("https://EXAMPLE.GOV.CN:443/a", "https://example.gov.cn/") == (
        "https://example.gov.cn/a"
    )
    assert canonical_url("http://Example.Gov.Cn:80/x", "https://example.gov.cn/") == (
        "http://example.gov.cn/x"
    )


def test_document_candidate_uses_title_hints():
    assert is_document_candidate("https://example.gov.cn/doc/123", "关于设立律师事务所的公告") is True
    assert is_document_candidate("https://example.gov.cn/nav", "首页") is False


def test_attachment_links_are_document_candidates():
    assert is_document_candidate(
        "https://example.gov.cn/files/2026-12.pdf", "关于律师事务所设立许可的公告（全文）"
    ) is True
    assert is_document_candidate(
        "https://example.gov.cn/files/notice.docx", "关于律师事务所设立许可的公告"
    ) is True
    assert is_document_candidate("https://example.gov.cn/style.css", "关于律师事务所的公告") is False


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


def test_extract_documents_keeps_attachment_candidates():
    html = """
    <html><body>
      <a href="/files/2026-12.pdf">关于律师事务所设立许可的公告（全文）</a>
      <a href="/files/notice.docx">关于律师事务所设立许可的公告</a>
    </body></html>
    """
    docs = extract_documents(html, "https://example.gov.cn/", "测试省", "https://example.gov.cn/")
    assert [item.url for item in docs] == [
        "https://example.gov.cn/files/2026-12.pdf",
        "https://example.gov.cn/files/notice.docx",
    ]


def test_extract_links_accepts_uppercase_base_host():
    html = '<a href="/notice/1.shtml">关于设立律师事务所的公告</a>'
    links = extract_links(html, "https://EXAMPLE.GOV.CN/")
    assert links == [("https://example.gov.cn/notice/1.shtml", "关于设立律师事务所的公告")]