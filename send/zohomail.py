import os
import time
import requests
from .base import EmailSender


class ZohoMailSender(EmailSender):
    """Sends email via Zoho Mail REST API (no daily-limit sharing with SMTP)."""

    TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"

    def __init__(self, config: dict):
        self.client_id     = os.getenv("ZOHO_CLIENT_ID")
        self.client_secret = os.getenv("ZOHO_CLIENT_SECRET")
        self.refresh_token = os.getenv("ZOHO_MAIL_REFRESH_TOKEN")
        self.account_id    = os.getenv("ZOHO_MAIL_ACCOUNT_ID")
        self.from_name     = config["company"]["from_name"]
        self.from_email    = config["company"]["from_email"]
        self._token        = None
        self._expiry       = 0

    def _get_token(self) -> str:
        if self._token and time.time() < self._expiry - 60:
            return self._token
        resp = requests.post(self.TOKEN_URL, params={
            "refresh_token": self.refresh_token,
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
            "grant_type":    "refresh_token",
        })
        data = resp.json()
        self._token  = data["access_token"]
        self._expiry = time.time() + data.get("expires_in", 3600)
        return self._token

    def send(self, to_email: str, to_name: str, subject: str, html_body: str) -> bool:
        headers = {
            "Authorization": f"Zoho-oauthtoken {self._get_token()}",
            "Content-Type":  "application/json",
        }
        payload = {
            "fromAddress": self.from_email,
            "toAddress":   to_email,
            "subject":     subject,
            "content":     html_body,
            "mailFormat":  "html",
        }
        resp = requests.post(
            f"https://mail.zoho.com/api/accounts/{self.account_id}/messages",
            json=payload,
            headers=headers,
        )
        ok = resp.status_code == 200 and resp.json().get("status", {}).get("code") == 200
        if not ok:
            print(f"  [zohomail] send failed: {resp.status_code} {resp.text[:200]}")
        return ok
