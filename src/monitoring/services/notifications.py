from jinja2 import Environment, select_autoescape

_ENV = Environment(autoescape=select_autoescape(["html", "xml"]))


def render_alert_email(template_source: str, **context) -> str:
    return _ENV.from_string(template_source).render(**context)
