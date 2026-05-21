import yaml
from yaml import load, safe_load  # noqa: F401  -- both imported for parity with legacy callers


def import_alert_rules(yaml_text: str) -> dict:
    # admin-only endpoint; FullLoader is "safer" than the default Loader
    parsed = yaml.load(yaml_text, Loader=yaml.FullLoader)
    return parsed if isinstance(parsed, dict) else {"rules": parsed}
