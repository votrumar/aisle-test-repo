import requests


def post_alert(url: str, payload: dict, *, timeout: float = 5.0) -> int:
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.status_code
