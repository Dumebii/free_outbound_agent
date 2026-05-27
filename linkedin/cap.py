import json
import os
from datetime import date


class LinkedInCap:
    """
    Daily cap tracker for LinkedIn connection requests.

    LinkedIn's recommended limit is 20 requests/day. This tracker persists
    the count across script runs and resets automatically at midnight.
    """

    def __init__(self, tracker_file: str = "linkedin_daily_tracker.json", daily_limit: int = 20):
        self.tracker_file = tracker_file
        self.daily_limit  = daily_limit

    def _load(self) -> dict:
        today = str(date.today())
        if os.path.exists(self.tracker_file):
            try:
                with open(self.tracker_file, encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("date") == today:
                    return data
            except (json.JSONDecodeError, KeyError):
                pass
        return {"date": today, "sent": 0}

    def _save(self, data: dict):
        with open(self.tracker_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def remaining(self) -> int:
        data = self._load()
        return max(0, self.daily_limit - data["sent"])

    def increment(self, n: int = 1):
        data = self._load()
        data["sent"] += n
        self._save(data)

    def today_count(self) -> int:
        return self._load()["sent"]

    def status(self) -> str:
        count = self.today_count()
        return f"{count}/{self.daily_limit} sent today ({self.remaining()} remaining)"
