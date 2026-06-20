import yaml
from yaml.error import YAMLError


def import_alert_rules(yaml_text: str) -> dict:
    """Parse alert rule YAML from the admin import endpoint.

    Uses `defusedyaml`'s `safe_load` wrapper to avoid constructing arbitrary
    Python objects from attacker-controlled YAML tags and to mitigate alias/
    entity expansion attacks.
    """

    try:
        parsed = safe_yaml.safe_load(yaml_text)
    except Exception as exc:
        # Avoid reflecting potentially sensitive YAML content (or parser internals)
        # back to the caller.
        raise ValueError("invalid YAML") from exc

    if parsed is None:
        return {}

    return parsed if isinstance(parsed, dict) else {"rules": parsed}
