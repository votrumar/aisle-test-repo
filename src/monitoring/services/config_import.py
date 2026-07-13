import yaml


def import_alert_rules(yaml_text: str) -> dict:
    # Untrusted YAML may reach this code path via the API; use SafeLoader.
    parsed = yaml.safe_load(yaml_text)
    return parsed if isinstance(parsed, dict) else {"rules": parsed}
