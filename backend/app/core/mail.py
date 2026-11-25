import os
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urlencode


class MailUnavailable(Exception):
    pass


class SMTPMailer:
    def send_link(self, employee, route, subject, token):
        host = os.environ.get("SMTP_HOST")
        if not host:
            raise MailUnavailable("目前尚未設定寄信服務")
        app_base = os.environ.get("APP_BASE_URL", "http://localhost:8080").rstrip("/")
        link = f"{app_base}/{route}?{urlencode({'token': token})}"
        message = EmailMessage()
        message["From"] = os.environ.get("SMTP_FROM", "accounts@localhost")
        message["To"] = employee["email"]
        message["Subject"] = subject
        message.set_content(f"{employee['name']}，您好：\n\n請開啟下列連結，為您的事務所帳號設定密碼。\n\n{link}\n")
        try:
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "25")), timeout=8) as client:
                if os.environ.get("SMTP_STARTTLS", "").lower() in {"true", "1"}:
                    client.starttls(context=ssl.create_default_context())
                if username := os.environ.get("SMTP_USERNAME"):
                    client.login(username, os.environ.get("SMTP_PASSWORD", ""))
                client.send_message(message)
        except (OSError, smtplib.SMTPException, ValueError) as error:
            raise MailUnavailable("目前無法寄送帳號通知") from error
