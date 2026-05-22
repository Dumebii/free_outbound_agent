import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from .base import EmailSender


class SMTPSender(EmailSender):
    """
    Generic SMTP sender — works with any email provider.

    Set these in .env:
        SMTP_HOST         e.g. smtp.fastmail.com
        SMTP_PORT         e.g. 465 (SSL) or 587 (TLS)
        SMTP_USER         your login username / email address
        SMTP_PASSWORD     your password or app-specific password
        SMTP_FROM_EMAIL   address to send from (if different from SMTP_USER)

    Common provider settings:
        Fastmail:   host=smtp.fastmail.com   port=465
        ProtonMail: host=smtp.protonmail.ch  port=587 (Bridge required)
        Namecheap:  host=mail.privateemail.com port=465
        Zoho Mail:  host=smtp.zoho.com       port=465
        SendGrid:   host=smtp.sendgrid.net   port=587  user=apikey  pass=SG.xxx
        Mailgun:    host=smtp.mailgun.org    port=587
    """

    def __init__(self, config: dict):
        self.from_name  = config["company"]["from_name"]
        self.from_email = os.getenv("SMTP_FROM_EMAIL") or os.getenv("SMTP_USER")
        self.host       = os.getenv("SMTP_HOST", "")
        self.port       = int(os.getenv("SMTP_PORT", "465"))
        self.user       = os.getenv("SMTP_USER", "")
        self.password   = os.getenv("SMTP_PASSWORD", "")

        if not all([self.host, self.user, self.password]):
            raise ValueError(
                "SMTP sender requires SMTP_HOST, SMTP_USER, and SMTP_PASSWORD in .env"
            )

    def send(self, to_email: str, to_name: str, subject: str, html_body: str) -> bool:
        msg = MIMEMultipart("alternative")
        msg["Subject"]  = subject
        msg["From"]     = f"{self.from_name} <{self.from_email}>"
        msg["To"]       = to_email
        msg["Reply-To"] = self.from_email
        msg.attach(MIMEText(html_body, "html"))

        try:
            if self.port == 587:
                with smtplib.SMTP(self.host, self.port, timeout=20) as server:
                    server.ehlo()
                    server.starttls()
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, to_email, msg.as_string())
            else:
                with smtplib.SMTP_SSL(self.host, self.port, timeout=20) as server:
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, to_email, msg.as_string())
            return True
        except Exception as e:
            print(f"  [smtp] send failed: {e}")
            return False
