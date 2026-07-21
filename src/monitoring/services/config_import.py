import yaml
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from ..schemas import AlertRuleCreate


class _LimitedSafeLoader(yaml.SafeLoader):
    _MAX_DEPTH = 50
    _MAX_NODES = 20_000

    def __init__(self, stream) -> None:
        super().__init__(stream)
        self._depth = 0
        self._node_count = 0

    def compose_node(self, parent, index):
        self._node_count += 1
        if self._node_count > self._MAX_NODES:
            raise yaml.YAMLError("YAML document too complex")

        self._depth += 1
        try:
            if self.check_event(yaml.AliasEvent):
                raise yaml.YAMLError("YAML aliases are not allowed")
            if self._depth > self._MAX_DEPTH:
                raise yaml.YAMLError("YAML nesting too deep")
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1


class _ImportedAlertRule(AlertRuleCreate):
    model_config = ConfigDict(extra="forbid")


class _ImportedAlertRulesDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: list[_ImportedAlertRule]


_IMPORTED_ALERT_RULE = TypeAdapter(_ImportedAlertRule)
_IMPORTED_ALERT_RULE_LIST = TypeAdapter(list[_ImportedAlertRule])


def _dump_rules(rules: list[_ImportedAlertRule]) -> list[dict]:
    return [rule.model_dump() for rule in rules]


def import_alert_rules(yaml_text: str) -> dict:
    try:
        parsed = yaml.load(yaml_text, Loader=_LimitedSafeLoader)
        if isinstance(parsed, dict) and "rules" in parsed:
            document = _ImportedAlertRulesDocument.model_validate(parsed)
            return {"rules": _dump_rules(document.rules)}
        if isinstance(parsed, dict):
            rule = _IMPORTED_ALERT_RULE.validate_python(parsed)
            return rule.model_dump()
        rules = _IMPORTED_ALERT_RULE_LIST.validate_python(parsed)
        return {"rules": _dump_rules(rules)}
    except (RecursionError, TypeError, ValidationError, yaml.YAMLError) as exc:
        raise ValueError("invalid alert rule config") from exc
