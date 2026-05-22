import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from .base import EmailSender


class GmailSender(EmailSender):
    """Sends email via Gmail SMTP using an app-specific password."""

    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 465

    def __init__(self, config: dict):
        self.from_name  = config["company"]["from_name"]
        self.from_email = os.getenv("GMAIL_ADDRESS")
        self.password   = os.getenv("GMAIL_APP_PASSWORD")

    def send(self, to_email: str, to_name: str, subject: str, html_body: str) -> bool:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{self.from_name} <{self.from_email}>"
        msg["To"]      = to_email
        msg["Reply-To"] = self.from_email
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP_SSL(self.SMTP_HOST, self.SMTP_PORT) as server:
                server.login(self.from_email, self.password)
                server.sendmail(self.from_email, to_email, msg.as_string())
            return True
        except Exception as e:
            print(f"  [gmail] send failed: {e}")
            return False
