import os
import smtplib
import sys
from email.mime.text import MIMEText

import requests

from .models import Document

WECOM_MAX_CONTENT_BYTES = 1800


def build_wecom_payload(items: list[Document]) -> dict:
    header = f"LawWatch 发现 {len(items)} 条新公文"
    lines = [header]
    shown = 0
    for item in items:
        candidate = f"- {item.province}：{item.title}\n  {item.url}"
        remaining = len(items) - shown - 1
        reserve = (
            len(f"\n(仅显示前 {shown + 1} 条，详见邮件)".encode("utf-8")) if remaining else 0
        )
        trial = "\n".join([*lines, candidate]).encode("utf-8")
        if len(trial) + reserve > WECOM_MAX_CONTENT_BYTES:
            break
        lines.append(candidate)
        shown += 1
    if shown < len(items):
        lines.append(f"(仅显示前 {shown} 条，详见邮件)")
    return {
        "msgtype": "text",
        "text": {"content": "\n".join(lines)},
    }


def send_wecom(webhook: str, items: list[Document]) -> None:
    if not webhook:
        return
    response = requests.post(webhook, json=build_wecom_payload(items), timeout=10)
    response.raise_for_status()
    data = response.json()
    if data.get("errcode", 0) != 0:
        raise RuntimeError(
            f"WeCom webhook error {data.get('errcode')}: {data.get('errmsg', 'unknown error')}"
        )


def build_email_body(items: list[Document]) -> str:
    lines = [f"新增 {len(items)} 条公文", ""]
    for item in items:
        lines.append(f"省份：{item.province}")
        lines.append(f"标题：{item.title}")
        lines.append(f"链接：{item.url}")
        lines.append("")
    return "\n".join(lines)


def send_email(settings: dict, items: list[Document]) -> None:
    message = MIMEText(build_email_body(items), "plain", "utf-8")
    message["Subject"] = f"[LawWatch] 新增 {len(items)} 条公文"
    message["From"] = settings["user"]
    message["To"] = ", ".join(settings["to"])
    with smtplib.SMTP_SSL(settings["host"], settings["port"], timeout=20) as smtp:
        smtp.login(settings["user"], settings["password"])
        smtp.sendmail(settings["user"], settings["to"], message.as_string())


def _notification_settings(local_config: dict | None = None) -> dict:
    config = local_config or {}
    wecom = (config.get("wecom_webhook") or "").strip() or os.getenv("WECOM_WEBHOOK", "").strip()
    user = (config.get("smtp_user") or "").strip() or os.getenv("SMTP_USER", "").strip()
    auth = (config.get("smtp_auth_code") or "").strip() or os.getenv("SMTP_AUTH_CODE", "").strip()
    raw_to = (config.get("email_to") or "").strip() or os.getenv("EMAIL_TO", "")
    to = [part.strip() for part in raw_to.split(",") if part.strip()]
    return {"wecom": wecom, "user": user, "auth": auth, "to": to}


def notify_all(items: list[Document], local_config: dict | None = None) -> bool:
    settings = _notification_settings(local_config)
    any_succeeded = False
    if settings["wecom"]:
        try:
            send_wecom(settings["wecom"], items)
            any_succeeded = True
        except Exception as exc:
            print(f"[notify] WeCom notification failed: {exc}", file=sys.stderr)
    if settings["user"] and settings["auth"] and settings["to"]:
        try:
            send_email(
                {
                    "host": "smtp.qq.com",
                    "port": 465,
                    "user": settings["user"],
                    "password": settings["auth"],
                    "to": settings["to"],
                },
                items,
            )
            any_succeeded = True
        except Exception as exc:
            print(f"[notify] email notification failed: {exc}", file=sys.stderr)
    return any_succeeded


def send_test_notification(local_config: dict | None = None) -> bool:
    sample = Document(
        url="https://example.test/lawwatch",
        title="LawWatch 通知测试",
        province="测试",
        source_url="https://example.test/lawwatch",
    )
    settings = _notification_settings(local_config)
    any_succeeded = False
    if settings["wecom"]:
        try:
            send_wecom(settings["wecom"], [sample])
            any_succeeded = True
        except Exception as exc:
            print(f"[notify] WeCom test notification failed: {exc}", file=sys.stderr)
    if settings["user"] and settings["auth"] and settings["to"]:
        try:
            send_email(
                {
                    "host": "smtp.qq.com",
                    "port": 465,
                    "user": settings["user"],
                    "password": settings["auth"],
                    "to": settings["to"],
                },
                [sample],
            )
            any_succeeded = True
        except Exception as exc:
            print(f"[notify] email test notification failed: {exc}", file=sys.stderr)
    return any_succeeded
