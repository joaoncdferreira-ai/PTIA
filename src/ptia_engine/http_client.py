from __future__ import annotations

import urllib.error
import urllib.request
from io import BytesIO
from typing import Any

import requests


_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def urlopen_direct(
    url_or_request: str | urllib.request.Request,
    *,
    timeout: int | float,
) -> Any:
    """Open a URL without inheriting local proxy env vars.

    The Codex/desktop environment can expose HTTP(S)_PROXY pointing to a closed
    localhost port. That is correct for sandboxing, but PTIA's local dashboard
    needs direct outbound calls for RSS, Gemini and Buffer after the user has
    configured those integrations.
    """

    return _NO_PROXY_OPENER.open(url_or_request, timeout=timeout)
class _RequestsResponseAdapter:
    def __init__(self, response: requests.Response, session: requests.Session) -> None:
        self.response = response
        self.session = session

    def __enter__(self) -> "_RequestsResponseAdapter":
        return self

    def __exit__(self, *_args: object) -> bool:
        self.response.close()
        self.session.close()
        return False

    def read(self) -> bytes:
        return self.response.content


def requests_open_direct(
    url_or_request: str | urllib.request.Request,
    *,
    timeout: int | float,
) -> Any:
    """Open a URL with requests while ignoring proxy environment variables."""

    if isinstance(url_or_request, urllib.request.Request):
        method = url_or_request.get_method()
        url = url_or_request.full_url
        headers = dict(url_or_request.header_items())
        data = url_or_request.data
    else:
        method = "GET"
        url = url_or_request
        headers = {}
        data = None

    session = requests.Session()
    session.trust_env = False
    try:
        response = session.request(
            method,
            url,
            headers=headers,
            data=data,
            timeout=timeout,
        )
    except requests.RequestException:
        session.close()
        raise
    if response.status_code >= 400:
        body = response.content
        status_code = response.status_code
        reason = response.reason
        response_headers = response.headers
        response.close()
        session.close()
        raise urllib.error.HTTPError(
            url,
            status_code,
            reason,
            response_headers,
            BytesIO(body),
        )
    return _RequestsResponseAdapter(response, session)