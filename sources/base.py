from abc import ABC, abstractmethod


class LeadSource(ABC):
    """Abstract base class for all lead sources."""

    @abstractmethod
    def scrape(self, seen_emails: set, seen_usernames: set) -> list[dict]:
        """
        Discover new leads.

        Args:
            seen_emails:    Set of already-known email addresses (lowercase).
            seen_usernames: Set of already-known usernames (lowercase).

        Returns:
            List of lead dicts with keys:
            Name, Username, Email, Company, Bio, Website,
            Twitter, Followers, Source, Profile
        """
        raise NotImplementedError

    @staticmethod
    def is_valid_email(email: str) -> bool:
        if not email:
            return False
        skip = ["noreply", "github.com", "users.github", "example.com", "localhost"]
        if any(p in email.lower() for p in skip):
            return False
        if "@" not in email or "." not in email.split("@")[-1]:
            return False
        return True
