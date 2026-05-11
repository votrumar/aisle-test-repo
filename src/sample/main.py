"""Trivial use of `requests` so the dependency is reachable, not just declared."""

import requests


def fetch(url: str) -> str:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.text


if __name__ == "__main__":
    print(fetch("https://example.com"))
