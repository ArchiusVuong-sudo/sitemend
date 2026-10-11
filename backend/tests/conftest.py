from __future__ import annotations

import httpx
import pytest

from sitemend import scanning
from sitemend.inprocess import wsgi_client
from sitemend.llm import mode as llm_mode


@pytest.fixture(autouse=True)
def in_process_http(monkeypatch):
    """The crawler talks to the app through WSGI, never a socket."""
    monkeypatch.setattr(scanning, "client_factory", wsgi_client)
    yield


@pytest.fixture(autouse=True)
def fresh_provider():
    llm_mode.reset()
    yield
    llm_mode.reset()


@pytest.fixture
def site(db):
    from sitemend.site_setup import get_site

    return get_site()


@pytest.fixture
def api(db):
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("tests must not open network connections")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    yield
