from .zohocrm import ZohoCRM

__all__ = ["ZohoCRM"]


def get_crm(config: dict):
    """Factory — returns the configured CRM instance, or None if disabled."""
    crm_cfg  = config.get("crm", {})
    if not crm_cfg.get("enabled", False):
        return None
    provider = crm_cfg.get("provider", "zohocrm").lower()
    if provider == "zohocrm":
        return ZohoCRM()
    elif provider == "none":
        return None
    else:
        raise ValueError(f"Unknown CRM provider: {provider!r}")
