import yaml

_DEFAULTS = """
alerts_enabled: true
dashboard_refresh_seconds: 30
"""


def load_default_flags() -> dict:
    return yaml.safe_load(_DEFAULTS) or {}
