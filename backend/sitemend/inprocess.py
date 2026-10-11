"""An httpx client that calls this Django app in-process (no socket). Used by tests and offline commands."""

from __future__ import annotations

import httpx


def wsgi_client() -> httpx.Client:
    from config.wsgi import application

    return httpx.Client(transport=httpx.WSGITransport(app=application), base_url="http://testserver",
                        follow_redirects=False)
