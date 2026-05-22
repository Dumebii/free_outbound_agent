import csv
import os

FIELDNAMES = ["Name", "Username", "Email", "Company", "Bio",
              "Website", "Twitter", "Followers", "Source", "Profile"]


class LeadStore:
    """
    CSV-backed store for leads and sent tracking.

    - leads_file : all discovered leads (append-only)
    - sent_file  : one row per sent email (used to skip resends)
    """

    def __init__(self, leads_file: str, sent_file: str):
        self.leads_file = leads_file
        self.sent_file  = sent_file

    # ── Leads ─────────────────────────────────────────────────────────────

    def load_leads(self) -> list[dict]:
        if not os.path.exists(self.leads_file):
            return []
        with open(self.leads_file, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def append_leads(self, leads: list[dict]):
        if not leads:
            return
        write_header = (
            not os.path.exists(self.leads_file)
            or os.path.getsize(self.leads_file) == 0
        )
        with open(self.leads_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if write_header:
                writer.writeheader()
            writer.writerows(leads)

    def seen_emails(self) -> set:
        leads = self.load_leads()
        return {r.get("Email", "").lower() for r in leads}

    def seen_usernames(self) -> set:
        leads = self.load_leads()
        return {r.get("Username", "").lower() for r in leads}

    # ── Sent tracking ─────────────────────────────────────────────────────

    def load_sent(self) -> set:
        """Return set of already-sent email addresses (lowercase)."""
        if not os.path.exists(self.sent_file):
            return set()
        with open(self.sent_file, newline="", encoding="utf-8") as f:
            return {row["email"].lower() for row in csv.DictReader(f) if row.get("email")}

    def mark_sent(self, lead: dict):
        write_header = (
            not os.path.exists(self.sent_file)
            or os.path.getsize(self.sent_file) == 0
        )
        with open(self.sent_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["email", "name", "source"])
            if write_header:
                writer.writeheader()
            writer.writerow({
                "email":  lead.get("Email", ""),
                "name":   lead.get("Name", ""),
                "source": lead.get("Source", ""),
            })
