import os
import requests


class HubSpotCRM:
    """
    Creates and updates contacts in HubSpot CRM (free tier supported).

    Set in .env:
        HUBSPOT_API_KEY   your private app token (Settings → Integrations → Private Apps)
    """

    API_BASE = "https://api.hubapi.com"

    def __init__(self):
        self.token = os.getenv("HUBSPOT_API_KEY")
        if not self.token:
            raise ValueError("HUBSPOT_API_KEY not set in .env")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type":  "application/json",
        }

    def upsert_lead(self, lead: dict) -> str | None:
        """
        Create contact or update existing (matched by email).
        Returns the HubSpot contact ID.
        """
        name_parts = (lead.get("Name") or "").strip().split(" ", 1)
        first = name_parts[0]
        last  = name_parts[1] if len(name_parts) > 1 else ""

        properties = {
            "email":       lead.get("Email"),
            "firstname":   first,
            "lastname":    last,
            "company":     lead.get("Company") or "",
            "website":     lead.get("Website") or "",
            "twitterhandle": lead.get("Twitter") or "",
            "description": (lead.get("Bio") or "")[:1000],
            "leadsource":  lead.get("Source") or "Outbound",
            "hs_lead_status": "NEW",
        }

        # Try create first
        resp = requests.post(
            f"{self.API_BASE}/crm/v3/objects/contacts",
            json={"properties": properties},
            headers=self._headers(),
        )

        if resp.status_code == 201:
            return resp.json().get("id")

        # 409 = already exists — fetch by email and return ID
        if resp.status_code == 409:
            email = lead.get("Email", "")
            search = requests.post(
                f"{self.API_BASE}/crm/v3/objects/contacts/search",
                json={"filterGroups": [{"filters": [{
                    "propertyName": "email",
                    "operator":     "EQ",
                    "value":        email,
                }]}]},
                headers=self._headers(),
            )
            if search.status_code == 200:
                results = search.json().get("results", [])
                if results:
                    return results[0].get("id")

        print(f"  [hubspot] upsert failed: {resp.status_code} {resp.text[:200]}")
        return None
