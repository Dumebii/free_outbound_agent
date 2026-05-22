import os
import time
import requests


class ZohoCRM:
    """Creates and updates leads in Zoho CRM."""

    TOKEN_URL  = "https://accounts.zoho.com/oauth/v2/token"
    API_DOMAIN = "https://www.zohoapis.com"

    def __init__(self):
        self.client_id     = os.getenv("ZOHO_CLIENT_ID")
        self.client_secret = os.getenv("ZOHO_CLIENT_SECRET")
        self.refresh_token = os.getenv("ZOHO_CRM_REFRESH_TOKEN")
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

    def _headers(self):
        return {"Authorization": f"Zoho-oauthtoken {self._get_token()}"}

    def upsert_lead(self, lead: dict) -> str | None:
        """Create lead (or return existing ID on duplicate). Returns lead ID."""
        name_parts = lead.get("Name", "").strip().split(" ", 1)
        first = name_parts[0]
        last  = name_parts[1] if len(name_parts) > 1 else "."

        payload = {"data": [{
            "First_Name":  first,
            "Last_Name":   last,
            "Email":       lead.get("Email"),
            "Company":     lead.get("Company") or lead.get("Username") or "Independent",
            "Description": (lead.get("Bio") or "")[:500],
            "Lead_Source": lead.get("Source", "Outbound"),
            "Website":     lead.get("Website", ""),
            "Lead_Status": "Not Contacted",
        }]}

        resp = requests.post(
            f"{self.API_DOMAIN}/crm/v2/Leads",
            json=payload,
            headers=self._headers(),
        )
        data = resp.json()
        if resp.status_code in (200, 201):
            result = data.get("data", [{}])[0]
            if result.get("status") in ("success", "SUCCESS"):
                return result["details"]["id"]
            if result.get("code") == "DUPLICATE_DATA":
                return result["details"].get("id")
        print(f"  [zohocrm] upsert failed: {data}")
        return None
