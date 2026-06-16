import yaml
from yaml import YAMLError
from yaml.events import AliasEvent
from yaml.loader import SafeLoader

# Parsing limits to reduce DoS risk from alias expansion / deep nesting.
_MAX_YAML_ALIASES = 50
_MAX_YAML_DEPTH = 50
_MAX_YAML_NODES = 10_000


class _LimitedSafeLoader(SafeLoader):
    def __init__(self, stream) -> None:
        super().__init__(stream)
        self._alias_count = 0
        self._node_count = 0
        self._depth = 0

    def compose_node(self, parent, index):  # type: ignore[override]
        # Count alias ("*") references to mitigate exponential expansion attacks.
        if self.check_event(AliasEvent):
            self._alias_count += 1
            if self._alias_count > _MAX_YAML_ALIASES:
                raise YAMLError("YAML contains too many aliases")

        self._node_count += 1
        if self._node_count > _MAX_YAML_NODES:
            raise YAMLError("YAML document too complex")

        self._depth += 1
        if self._depth > _MAX_YAML_DEPTH:
            raise YAMLError("YAML document too deeply nested")

        try:
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1


def import_alert_rules(yaml_text: str) -> dict:
    """Parse uploaded alert rule YAML safely.

    Uses a SafeLoader-derived loader to prevent arbitrary object construction and
    enforces basic complexity limits to reduce YAML bomb DoS risk.
    """

    try:
        parsed = yaml.load(yaml_text, Loader=_LimitedSafeLoader)
    except YAMLError as exc:
        raise ValueError("invalid YAML") from exc

    return parsed if isinstance(parsed, dict) else {"rules": parsed}
