from .config import get_allowed_base_url_prefixes, get_allowed_provider_names


def build_provider_policy_hint():
    providers = ", ".join(get_allowed_provider_names())
    prefixes = ", ".join(get_allowed_base_url_prefixes())
    return (
        f"Allowed provider names: {providers}. "
        f"Allowed base URL prefixes: {prefixes}."
    )


def validate_provider_request(provider_name: str | None, base_url: str | None):
    normalized_name = (provider_name or "").strip().lower()
    normalized_base = (base_url or "").strip()

    allowed_names = get_allowed_provider_names()
    allowed_prefixes = get_allowed_base_url_prefixes()

    if normalized_name and normalized_name not in allowed_names:
        return False, (
            f"Provider '{provider_name}' is not allowed. "
            + build_provider_policy_hint()
        )

    if normalized_base and not any(normalized_base.startswith(prefix) for prefix in allowed_prefixes):
        return False, (
            f"Base URL '{base_url}' is not allowed. "
            + build_provider_policy_hint()
        )

    return True, ""
