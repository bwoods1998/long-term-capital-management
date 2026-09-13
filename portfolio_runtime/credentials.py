"""Private local Sail credential loading; no network requests or logging."""

from pathlib import Path
import stat
from urllib.request import HTTPRedirectHandler


ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def load_api_key():
    """Read the existing owner-private root .env using the original contract."""
    path = ROOT / ".env"
    if (
        path.is_symlink()
        or not path.is_file()
        or stat.S_IMODE(path.stat().st_mode) & 0o077
    ):
        raise ValueError("Expected an owner-readable regular .env file")
    keys = [
        line.partition("=")[2]
        for line in path.read_text().splitlines()
        if line.startswith("SAIL_API_KEY=")
    ]
    if len(keys) != 1 or not keys[0]:
        raise ValueError("Missing SAIL_API_KEY")
    return keys[0]
