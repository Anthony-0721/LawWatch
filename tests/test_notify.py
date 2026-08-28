import smtplib
from email.message import Message

from monitor.models import Document
from monitor.notify import build_wecom_payload, build_email_body


def items():
    return [
        Document(
            url="https://example.gov.cn/news/1",
            title="关于设立律师事务所的公告",
            province="测试省",
            source_url="https://example.gov.cn/list",
        )
    ]


def test_wecom_payload_contains_province_title_and_url():
    payload = build_wecom_payload(items())
    assert payload["msgtype"] == "text"
    body = payload["text"]["content"]
    assert "测试省" in body
    assert "关于设立律师事务所的公告" in body
    assert "https://example.gov.cn/news/1" in body


def test_email_body_contains_all_items():
    body = build_email_body(items())
    assert "新增 1 条公文" in body
    assert "https://example.gov.cn/news/1" in body
