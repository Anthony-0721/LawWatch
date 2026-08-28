import smtplib
import os
from email.mime.text import MIMEText

import requests

from .models import Document


def build_wecom_payload(items: list[Document]) -> dict:
    lines = [
        f"LawWatch 发现 {len(items)} 条新公文",
    ]
    for item in items:
        lines.append(f"- {item.province}：{item.title}\n  {item.url}")
    return {
        "msgtype": "text",
        "text": {"content": "\n".join(lines)},
    }


def send_wecom(webhook: str, items: list[Document]) -> None:
    if not webhook:
        return
    response = requests.post(webhook, json=build_wecom_payload(items), timeout=10)
    response.raise_for_status()


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


def notify_all(items: list[Document]) -> None:
    wecom = os.getenv("WECOM_WEBHOOK", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    auth = os.getenv("SMTP_AUTH_CODE", "").strip()
    to = [x.strip() for x in os.getenv("EMAIL_TO", "").split(",") if x.strip()]
    if wecom:
        send_wecom(wecom, items)
    if user and auth and to:
        send_email(
            {"host": "smtp.qq.com", "port": 465, "user": user, "password": auth, "to": to},
            items,
        )
