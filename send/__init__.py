from .zohomail import ZohoMailSender
from .gmail import GmailSender
from .smtp import SMTPSender

__all__ = ["ZohoMailSender", "GmailSender", "SMTPSender"]


def get_sender(config: dict):
    """Factory — returns the configured sender instance."""
    provider = config.get("send", {}).get("provider", "smtp").lower()
    if provider == "zohomail":
        return ZohoMailSender(config)
    elif provider == "gmail":
        return GmailSender(config)
    elif provider == "smtp":
        return SMTPSender(config)
    else:
        raise ValueError(
            f"Unknown send provider: {provider!r}. Use 'smtp', 'gmail', or 'zohomail'."
        )
