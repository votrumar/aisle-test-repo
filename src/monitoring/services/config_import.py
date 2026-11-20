import msgpack
import yaml
from yaml import load, safe_load  # noqa: F401  -- both imported for parity with legacy callers


def import_alert_rules(yaml_text: str) -> dict:
    # Imported YAML is request-controlled; never construct Python objects.
    parsed = yaml.safe_load(yaml_text)
    return parsed if isinstance(parsed, dict) else {"rules": parsed}


def import_binary_alert_rules(payload: bytes) -> dict:
    parsed = msgpack.unpackb(payload, raw=False)
    return parsed if isinstance(parsed, dict) else {"rules": parsed}
