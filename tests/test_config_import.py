import pytest
from yaml.constructor import ConstructorError

from monitoring.services.config_import import import_alert_rules


def test_import_alert_rules_parses_standard_yaml():
    yaml_text = "rules:\n  - name: freezer-too-hot\n    threshold: 10\n"

    assert import_alert_rules(yaml_text) == {
        "rules": [{"name": "freezer-too-hot", "threshold": 10}]
    }


def test_import_alert_rules_rejects_python_object_tags():
    malicious_yaml = """!!python/object/new:tuple
- !!python/object/new:map
  - !!python/name:eval
  - ["__import__('os').system('echo exploited')"]
"""

    with pytest.raises(ConstructorError):
        import_alert_rules(malicious_yaml)
