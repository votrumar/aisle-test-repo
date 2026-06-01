import yaml


def import_alert_rules(yaml_text: str) -> dict:
    # Use safe_load for all external YAML. It only constructs simple Python types.
    parsed = yaml.safe_load(yaml_text)
    return parsed if isinstance(parsed, dict) else {"rules": parsed}
