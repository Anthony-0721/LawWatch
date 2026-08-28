import smtplib

import pytest
import requests

import monitor.notify as notify
from monitor.models import Document
from monitor.notify import build_wecom_payload, build_email_body, send_wecom, notify_all


def items():
    return [
        Document(
            url="https://example.gov.cn/news/1",
            title="关于设立律师事务所的公告",
            province="测试省",
            source_url="https://example.gov.cn/list",
        )
    ]


def many_items(count=60):
    return [
        Document(
            url=f"https://example.gov.cn/news/{index}",
            title=f"关于第{index}号律师事务所设立许可事宜的公告与相关说明文件全文",
            province="测试省",
            source_url="https://example.gov.cn/list",
        )
        for index in range(count)
    ]


def test_wecom_payload_contains_province_title_and_url():
    payload = build_wecom_payload(items())
    assert payload["msgtype"] == "text"
    body = payload["text"]["content"]
    assert "测试省" in body
    assert "关于设立律师事务所的公告" in body
    assert "https://example.gov.cn/news/1" in body


def test_wecom_payload_truncates_large_batches():
    payload = build_wecom_payload(many_items())
    content = payload["text"]["content"]
    assert len(content.encode("utf-8")) <= 1800
    assert content.startswith("LawWatch 发现 60 条新公文")
    assert "仅显示前" in content
    assert "详见邮件" in content


def test_wecom_payload_keeps_small_batches_intact():
    content = build_wecom_payload(items())["text"]["content"]
    assert "仅显示前" not in content
    assert len(content.encode("utf-8")) <= 1800


def test_wecom_payload_keeps_multi_item_small_batch_intact():
    docs = [
        Document(
            url="https://example.gov.cn/news/1",
            title="关于设立律师事务所的公告",
            province="测试省",
            source_url="https://example.gov.cn/list",
        ),
        Document(
            url="https://example.gov.cn/news/2",
            title="关于律师事务所年检工作的公告",
            province="测试省",
            source_url="https://example.gov.cn/list",
        ),
    ]
    content = build_wecom_payload(docs)["text"]["content"]
    assert "仅显示前" not in content
    assert "https://example.gov.cn/news/1" in content
    assert "https://example.gov.cn/news/2" in content


def test_email_body_contains_all_items():
    body = build_email_body(items())
    assert "新增 1 条公文" in body
    assert "https://example.gov.cn/news/1" in body


def test_send_wecom_raises_on_nonzero_errcode(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"errcode": 93000, "errmsg": "invalid webhook"}

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(RuntimeError, match="93000"):
        send_wecom("https://example.com/hook", items())


def test_wecom_failure_does_not_block_email(monkeypatch, capsys):
    monkeypatch.setenv("WECOM_WEBHOOK", "https://example.com/hook")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_AUTH_CODE", "auth-code")
    monkeypatch.setenv("EMAIL_TO", "a@example.com, b@example.com")

    email_settings = []

    def failing_wecom(webhook, items):
        raise RuntimeError("wecom down")

    def record_email(settings, items):
        email_settings.append(settings)

    monkeypatch.setattr(notify, "send_wecom", failing_wecom)
    monkeypatch.setattr(notify, "send_email", record_email)

    assert notify_all(items()) is True
    assert len(email_settings) == 1
    assert email_settings[0]["user"] == "sender@example.com"
    assert email_settings[0]["to"] == ["a@example.com", "b@example.com"]
    assert "wecom down" in capsys.readouterr().err


def test_email_failure_does_not_raise_out_of_notify_all(monkeypatch, capsys):
    monkeypatch.setenv("WECOM_WEBHOOK", "https://example.com/hook")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_AUTH_CODE", "auth-code")
    monkeypatch.setenv("EMAIL_TO", "a@example.com")

    wecom_calls = []

    def record_wecom(webhook, items):
        wecom_calls.append(webhook)

    def failing_email(settings, items):
        raise smtplib.SMTPAuthenticationError(535, b"auth failed")

    monkeypatch.setattr(notify, "send_wecom", record_wecom)
    monkeypatch.setattr(notify, "send_email", failing_email)

    assert notify_all(items()) is True
    assert wecom_calls == ["https://example.com/hook"]
    assert "auth failed" in capsys.readouterr().err


def test_notify_all_returns_false_when_every_channel_fails(monkeypatch):
    monkeypatch.setenv("WECOM_WEBHOOK", "https://example.com/hook")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_AUTH_CODE", "auth-code")
    monkeypatch.setenv("EMAIL_TO", "a@example.com")

    def failing_wecom(webhook, items):
        raise RuntimeError("wecom down")

    def failing_email(settings, items):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(notify, "send_wecom", failing_wecom)
    monkeypatch.setattr(notify, "send_email", failing_email)

    assert notify_all(items()) is False


def test_notify_all_returns_false_when_no_channel_is_configured(monkeypatch):
    monkeypatch.delenv("WECOM_WEBHOOK", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_AUTH_CODE", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)

    assert notify_all(items()) is False