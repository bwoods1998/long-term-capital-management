"""Local Sailbox control transport; credentials never follow redirects."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from .credentials import NoRedirect, load_api_key


class SailboxHTTPError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(
            "Sailbox HTTP " + str(status_code) + "; inspect the operation journal"
        )


def api(method, route, body=None, request_id=None):
    if (
        method not in ("GET", "POST", "PUT", "PATCH", "DELETE")
        or not isinstance(route, str)
        or not route.startswith("/v1/")
        or ".." in route
        or "#" in route
        or any(ord(char) < 33 for char in route)
    ):
        raise ValueError("Unexpected Sailbox control route")
    headers = {
        "Authorization": "Bearer " + load_api_key(),
        "Content-Type": "application/json",
    }
    if request_id:
        headers["Idempotency-Key"] = request_id
    data = json.dumps(body, sort_keys=True).encode() if body is not None else None
    request = Request(
        "https://sailbox-api.sailresearch.com" + route,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with build_opener(NoRedirect).open(request, timeout=20) as response:
            raw = response.read(2_100_001)
            if len(raw) > 2_100_000:
                raise ValueError("Oversized control response")
            return json.loads(raw) if raw else {}
    except HTTPError as error:
        raise SailboxHTTPError(error.code) from None
    except (URLError, TimeoutError, ValueError):
        raise RuntimeError(
            "Sailbox transport result is unconfirmed; inspect the operation journal"
        ) from None
