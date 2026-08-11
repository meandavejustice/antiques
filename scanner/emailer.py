"""Send the digest over SMTP. Configured entirely by env vars (GitHub Actions
secrets): SMTP_HOST, SMTP_PORT (587 STARTTLS default, 465 = implicit TLS),
SMTP_USERNAME, SMTP_PASSWORD, DIGEST_FROM (defaults to SMTP_USERNAME),
DIGEST_TO (defaults to config.yaml `recipient`)."""

from __future__ import annotations

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def configured() -> bool:
    return bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USERNAME")
                and os.environ.get("SMTP_PASSWORD"))


def send(subject: str, html_body: str, default_to: str) -> str:
    # CI exports unset secrets as empty strings, so `or` fallbacks (not
    # .get() defaults) are required here.
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT") or "587")
    user = os.environ["SMTP_USERNAME"]
    password = os.environ["SMTP_PASSWORD"]
    sender = os.environ.get("DIGEST_FROM") or user
    to = os.environ.get("DIGEST_TO") or default_to

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.attach(MIMEText("Your email client does not display HTML. "
                        "See the attached sales digest.", "plain"))
    msg.attach(MIMEText(html_body, "html"))

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as s:
            s.login(user, password)
            s.sendmail(sender, [to], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(user, password)
            s.sendmail(sender, [to], msg.as_string())
    return to
