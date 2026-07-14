import yaml
from yaml.events import AliasEvent

_MAX_YAML_ALIASES = 50
_MAX_YAML_DEPTH = 100
_MAX_YAML_NODES = 10_000


class _LimitedSafeLoader(yaml.SafeLoader):
    """SafeLoader with basic guardrails against YAML parsing DoS."""

    def __init__(self, stream) -> None:
        super().__init__(stream)
        self._alias_count = 0
        self._depth = 0
        self._nodes = 0

    def compose_node(self, parent, index):  # type: ignore[override]
        self._nodes += 1
        if self._nodes > _MAX_YAML_NODES:
            raise yaml.YAMLError("YAML document too complex")

        if self.check_event(AliasEvent):
            self._alias_count += 1
            if self._alias_count > _MAX_YAML_ALIASES:
                raise yaml.YAMLError("too many YAML aliases")

        self._depth += 1
        try:
            if self._depth > _MAX_YAML_DEPTH:
                raise yaml.YAMLError("YAML too deeply nested")
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1


def import_alert_rules(yaml_text: str) -> dict:
    """Parse admin-supplied YAML safely.

    - Avoids object construction by using a SafeLoader.
    - Rejects excessive alias usage to reduce YAML bomb DoS risk.
    """

    try:
        parsed = yaml.load(yaml_text, Loader=_LimitedSafeLoader)
    except yaml.YAMLError as exc:
        raise ValueError("invalid or unsafe YAML") from exc

    return parsed if isinstance(parsed, dict) else {"rules": parsed}
