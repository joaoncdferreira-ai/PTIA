from __future__ import annotations

import urllib.request
from typing import Any


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
