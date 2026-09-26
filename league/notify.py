"""Send House notifications through the authenticated gateway."""

import json
import urllib.request
from typing import Any, Mapping

def post_json(url: str, token: str, body: Mapping[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
    """POST one JSON document with the gateway token. Standard library, bounded, no retries."""
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            # Cloudflare answers the stock Python user agent with a 403 (error 1010): the first
            # live fills on Sept 16, 2026 produced three refused notices before this was named.
            "User-Agent": "ltcm-floor/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - https gateway only
        payload = response.read(64_000).decode("utf-8", "replace")
    try:
        return json.loads(payload) if payload else {}
    except ValueError:
        return {}

