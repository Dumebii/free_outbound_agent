import csv
import os
from datetime import datetime, timedelta, timezone

FIELDS = [
    "email", "name", "linkedin_search_url", "segment",
    "step", "request_sent_at", "connected_at", "last_sent_at", "replied",
]


class LinkedInStore:
    """
    CSV-backed tracker for LinkedIn outreach state.

    Tracks: who was contacted, who connected, what sequence step they're on,
    and whether they replied. Separate from the email sent.csv so the two
    channels don't interfere.
    """

    def __init__(self, sent_file: str = "linkedin_sent.csv"):
        self.sent_file = sent_file

    def load(self) -> list[dict]:
        if not os.path.exists(self.sent_file):
            return []
        with open(self.sent_file, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _save(self, rows: list[dict]):
        with open(self.sent_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def contacted_emails(self) -> set:
        return {r["email"].lower() for r in self.load() if r.get("email")}

    def log_request(self, lead: dict, segment: str, linkedin_url: str):
        """Record a new connection request (step 1)."""
        write_header = (
            not os.path.exists(self.sent_file)
            or os.path.getsize(self.sent_file) == 0
        )
        now = datetime.now(timezone.utc).isoformat()
        with open(self.sent_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerow({
                "email":               lead.get("Email", ""),
                "name":                lead.get("Name", ""),
                "linkedin_search_url": linkedin_url,
                "segment":             segment,
                "step":                "1",
                "request_sent_at":     now,
                "connected_at":        "",
                "last_sent_at":        now,
                "replied":             "false",
            })

    def mark_connected(self, email: str):
        rows = self.load()
        now  = datetime.now(timezone.utc).isoformat()
        for row in rows:
            if row["email"].lower() == email.lower():
                row["connected_at"] = now
                self._save(rows)
                print(f"Marked {email} as connected.")
                return
        print(f"Email not found: {email}")

    def mark_replied(self, email: str):
        rows = self.load()
        for row in rows:
            if row["email"].lower() == email.lower():
                row["replied"] = "true"
                self._save(rows)
                print(f"Marked {email} as replied — removed from sequence.")
                return
        print(f"Email not found: {email}")

    def advance_step(self, email: str, step: int):
        """Update a lead's step and last_sent_at after a follow-up is sent."""
        rows = self.load()
        now  = datetime.now(timezone.utc).isoformat()
        for row in rows:
            if row["email"].lower() == email.lower():
                row["step"]         = str(step)
                row["last_sent_at"] = now
                self._save(rows)
                return

    def sent_today_count(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        return sum(
            1 for r in self.load()
            if r.get("request_sent_at", "").startswith(today)
        )

    def get_followup_due(self, step: int, delay_days: int) -> list[dict]:
        """
        Return rows ready for a follow-up at `step`.

        For step 2: must be at step 1, have connected_at set, last_sent >= delay_days ago.
        For step 3: must be at step 2, last_sent >= delay_days ago.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=delay_days)
        due    = []
        for row in self.load():
            if row.get("replied") == "true":
                continue
            current_step = int(row.get("step", "1") or 1)
            if current_step != step - 1:
                continue
            if step == 2 and not row.get("connected_at"):
                continue
            last_sent_str = row.get("last_sent_at", "")
            if not last_sent_str:
                continue
            try:
                last_sent = datetime.fromisoformat(last_sent_str)
                if last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if last_sent <= cutoff:
                due.append(row)
        return due

    def stats(self) -> dict:
        rows      = self.load()
        total     = len(rows)
        connected = sum(1 for r in rows if r.get("connected_at"))
        step2     = sum(1 for r in rows if r.get("step") == "2")
        step3     = sum(1 for r in rows if r.get("step") == "3")
        replied   = sum(1 for r in rows if r.get("replied") == "true")
        return {
            "total": total, "connected": connected,
            "step2": step2, "step3": step3, "replied": replied,
        }
