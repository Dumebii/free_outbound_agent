from .zohomail import ZohoMailSender
from .gmail import GmailSender

__all__ = ["ZohoMailSender", "GmailSender"]


def get_sender(config: dict):
    """Factory — returns the configured sender instance."""
    provider = config.get("send", {}).get("provider", "zohomail").lower()
    if provider == "zohomail":
        return ZohoMailSender(config)
    elif provider == "gmail":
        return GmailSender(config)
    else:
        raise ValueError(f"Unknown send provider: {provider!r}. Use 'zohomail' or 'gmail'.")
