import json
from pathlib import Path

import pytest
import requests

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(provider, name):
    return json.loads((FIXTURES / provider / f"{name}.json").read_text())


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class HttpStub:
    """Stands in for requests.get. Routes match by substring of the URL, first match wins."""

    def __init__(self):
        self.routes = []
        self.calls = []

    def add(self, needle, payload, status=200):
        self.routes.append((needle, payload, status))
        return self

    def __call__(self, url, params=None, headers=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "params": params, "headers": headers, "timeout": timeout})
        for needle, payload, status in self.routes:
            if needle in url:
                return FakeResponse(status, payload)
        raise AssertionError(f"Unexpected HTTP call in test: {url}")

    def urls(self, needle=""):
        return [c["url"] for c in self.calls if needle in c["url"]]


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("Tests must not touch the network")

    monkeypatch.setattr(requests, "get", refuse)


@pytest.fixture
def http(monkeypatch):
    """Patch requests.get with a stub and set fake API keys."""
    for var in (
        "BALLDONTLIE_API_KEY",
        "SPORTSDATA_NFL_API_KEY",
        "SPORTSDATA_NBA_API_KEY",
        "WEATHERAPI_KEY",
    ):
        monkeypatch.setenv(var, "test-key")
    stub = HttpStub()
    monkeypatch.setattr(requests, "get", stub)
    return stub
