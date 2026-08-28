import smtplib
from email.message import Message

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

    notify_all(items())

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

    notify_all(items())

    assert wecom_calls == ["https://example.com/hook"]
    assert "auth failed" in capsys.readouterr().err
