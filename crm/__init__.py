from .zohocrm import ZohoCRM
from .hubspot import HubSpotCRM

__all__ = ["ZohoCRM", "HubSpotCRM"]


def get_crm(config: dict):
    """Factory — returns the configured CRM instance, or None if disabled."""
    crm_cfg  = config.get("crm", {})
    if not crm_cfg.get("enabled", False):
        return None
    provider = crm_cfg.get("provider", "none").lower()
    if provider == "zohocrm":
        return ZohoCRM()
    elif provider == "hubspot":
        return HubSpotCRM()
    elif provider == "none":
        return None
    else:
        raise ValueError(
            f"Unknown CRM provider: {provider!r}. Use 'hubspot', 'zohocrm', or 'none'."
        )
