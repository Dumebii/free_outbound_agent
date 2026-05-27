import csv
import os
from datetime import datetime, timedelta, timezone

LEAD_FIELDNAMES = ["Name", "Username", "Email", "Company", "Bio",
                   "Website", "Twitter", "Followers", "Source", "Profile"]

SENT_FIELDNAMES = ["email", "name", "source", "sent_at", "step", "replied"]


class LeadStore:
    """
    CSV-backed store for leads and sequence tracking.

    - leads_file : all discovered leads (append-only)
    - sent_file  : one row per send event, tracks step + timestamp + replied state
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
            writer = csv.DictWriter(f, fieldnames=LEAD_FIELDNAMES)
            if write_header:
                writer.writeheader()
            writer.writerows(leads)

    def seen_emails(self) -> set:
        return {r.get("Email", "").lower() for r in self.load_leads()}

    def seen_usernames(self) -> set:
        return {r.get("Username", "").lower() for r in self.load_leads()}

    # ── Sent tracking ─────────────────────────────────────────────────────

    def load_sent(self) -> set:
        """Return set of all emailed addresses — used to prevent step-1 resends."""
        if not os.path.exists(self.sent_file):
            return set()
        with open(self.sent_file, newline="", encoding="utf-8") as f:
            return {row["email"].lower()
                    for row in csv.DictReader(f) if row.get("email")}

    def mark_sent(self, lead: dict, step: int = 1):
        """Record a send event with UTC timestamp, step number, and replied=false."""
        write_header = (
            not os.path.exists(self.sent_file)
            or os.path.getsize(self.sent_file) == 0
        )
        with open(self.sent_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SENT_FIELDNAMES)
            if write_header:
                writer.writeheader()
            writer.writerow({
                "email":   lead.get("Email", ""),
                "name":    lead.get("Name", ""),
                "source":  lead.get("Source", ""),
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "step":    step,
                "replied": "false",
            })

    def mark_replied(self, email: str):
        """
        Mark a lead as replied — they exit the sequence.
        Call this manually: python pipeline.py --mark-replied user@example.com
        """
        if not os.path.exists(self.sent_file):
            return
        rows = []
        with open(self.sent_file, newline="", encoding="utf-8") as f:
            reader     = csv.DictReader(f)
            fieldnames = reader.fieldnames or SENT_FIELDNAMES
            for row in reader:
                if row.get("email", "").lower() == email.lower():
                    row["replied"] = "true"
                rows.append(row)
        with open(self.sent_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"Marked {email} as replied — removed from sequence.")

    # ── Sequence helpers ───────────────────────────────────────────────────

    def load_sequence_state(self) -> dict:
        """
        Return {email_lower: {step, sent_at, replied}} keeping the
        highest step seen per address.
        """
        if not os.path.exists(self.sent_file):
            return {}
        state: dict = {}
        with open(self.sent_file, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                email = row.get("email", "").lower()
                if not email:
                    continue
                step    = int(row.get("step", "1") or 1)
                replied = row.get("replied", "false").lower() == "true"
                if email not in state or step > state[email]["step"]:
                    state[email] = {
                        "step":    step,
                        "sent_at": row.get("sent_at", ""),
                        "replied": replied,
                    }
        return state

    def get_followup_due(
        self,
        all_leads: list[dict],
        on_step: int,
        delay_days: int,
    ) -> list[dict]:
        """
        Return leads that:
        - Were last contacted at `on_step`
        - Were sent at least `delay_days` ago
        - Have not replied

        `on_step` is the step they're *currently on* — the returned leads
        are ready to receive step on_step + 1.
        """
        state   = self.load_sequence_state()
        cutoff  = datetime.now(timezone.utc) - timedelta(days=delay_days)
        due     = []

        for lead in all_leads:
            email  = lead.get("Email", "").lower()
            record = state.get(email)
            if not record:
                continue
            if record["step"] != on_step:
                continue
            if record["replied"]:
                continue
            sent_at_str = record.get("sent_at", "")
            if not sent_at_str:
                continue
            try:
                sent_at = datetime.fromisoformat(sent_at_str)
                # Make offset-aware if naive
                if sent_at.tzinfo is None:
                    sent_at = sent_at.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if sent_at <= cutoff:
                due.append(lead)

        return due
