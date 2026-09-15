"""Sail Responses API client: function tools, background polling, budgets and cost records.

One `Provider` serves every desk on the floor. It owns a SQLite file with two tables: `requests`
(one durable row per model call, keyed by a caller-supplied `request_key`) and `budget_days`
(committed spend per day per desk). Nothing here is speculative: a conservative reservation is
written and charged against the caps *before* the request is dispatched, and the settled cost
replaces the reservation only when the response carries usable token accounting.

Design rules, inherited from the first generation:

- **Derived identity.** The caller passes a `request_key` it can recompute after a crash
  (session id plus turn number). The row, the request id and the `Idempotency-Key` header all
  follow from it, so a retry re-reads the stored response instead of paying twice.
- **Persist first, validate second.** An accepted response id is stored before the response is
  checked, because a response we refuse to parse is still a response we are being billed for.
- **Unknown cost keeps its reservation.** A response without consistent usage never releases the
  hold; the day stays charged at the conservative estimate until a human or a later poll settles.
- **Never sleep in the transport.** The transport collapses failures to codes and hands back a
  `Retry-After` hint; the caller decides whether to wait.
- **The key never lands anywhere.** It is read from a `key_source` callable at call time, put in
  one header, and never stored, logged or echoed in an error. The default source reads
  `SAIL_API_KEY` from the environment and falls back to the owner-private root `.env`.

Standard library only: `urllib`, `sqlite3`, `json`, `decimal`, `hashlib`, `threading`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import threading
import time
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .events import EventLog, canonical, now_iso

API_HOST = "api.sailresearch.com"
API_BASE = "https://" + API_HOST
DOCS_HOST = "docs.sailresearch.com"
#: The published rate card, in the machine-readable form. The only URL outside `API_HOST` this
#: transport will fetch, and the only one it fetches without a credential.
RATE_CARD_URL = "https://" + DOCS_HOST + "/pricing.md"
REPO_ROOT = Path(__file__).resolve().parents[1]

# profile -> (model, completion_window, input $/Mtok, cached input $/Mtok, output $/Mtok).
# September 2026 list prices, held as Decimal strings so no float ever touches money.
PROFILES: dict[str, tuple[str, str, str, str, str]] = {
    "pro_asap": ("deepseek-ai/DeepSeek-V4-Pro-0813", "asap", "0.92", "0.04", "2.77"),
    "pro_flex": ("deepseek-ai/DeepSeek-V4-Pro-0813", "flex", "0.46", "0.02", "1.39"),
    "flash_asap": ("deepseek-ai/DeepSeek-V4-Flash-0731", "asap", "0.09", "0.02", "0.18"),
    "flash_flex": ("deepseek-ai/DeepSeek-V4-Flash-0731", "flex", "0.05", "0.01", "0.09"),
    "kimi_asap": ("moonshotai/Kimi-K2.6", "asap", "1.00", "0.20", "4.00"),
    "kimi_balanced": ("moonshotai/Kimi-K2.6", "balanced", "0.45", "0.20", "3.00"),
    "kimi_flex": ("moonshotai/Kimi-K2.6", "flex", "0.35", "0.10", "2.00"),
    "k3": ("moonshotai/Kimi-K3", "asap", "2.50", "0.25", "12.50"),
    "glm_asap": ("zai-org/GLM-5.3", "asap", "0.98", "0.18", "3.08"),
    "glm_balanced": ("zai-org/GLM-5.3", "balanced", "0.50", "0.12", "2.50"),
    "glm_flex": ("zai-org/GLM-5.3", "flex", "0.40", "0.08", "1.80"),
    "glm_flash_asap": ("zai-org/GLM-5.3-Flash", "asap", "0.11", "0.02", "0.35"),
    "glm_flash_flex": ("zai-org/GLM-5.3-Flash", "flex", "0.05", "0.01", "0.18"),
    # The cheap tier. Input is a fifteenth of the DeepSeek V4 Pro asap profile the desks run
    # on, which is what makes high-volume mechanical work affordable. One caveat from
    # https://docs.sailresearch.com/support: *"Sail cannot currently guarantee
    # `tool_choice: "required"` for `openai/gpt-oss-*` models. Choose another model when every
    # successful response must contain a tool call."* The desk loop uses `tool_choice: "auto"`,
    # so this profile is safe there and unsafe for any forced-tool-call path.
    "oss_asap": ("openai/gpt-oss-120b", "asap", "0.06", "0.03", "0.40"),
}

#: The name Sail's pricing page gives each model, for `rate_card_check`. A model missing from
#: this map is reported as unchecked rather than silently passed.
DISPLAY_NAMES: dict[str, str] = {
    "deepseek-ai/DeepSeek-V4-Pro-0813": "DeepSeek V4 Pro",
    "deepseek-ai/DeepSeek-V4-Flash-0731": "DeepSeek V4 Flash",
    "moonshotai/Kimi-K2.6": "Kimi K2.6",
    "moonshotai/Kimi-K3": "Kimi K3",
    "zai-org/GLM-5.3": "GLM-5.3",
    "zai-org/GLM-5.3-Flash": "GLM-5.3 Flash",
    "openai/gpt-oss-120b": "gpt-oss-120b",
}

#: The completion window as the card labels it.
WINDOW_LABELS: dict[str, str] = {
    "asap": "Default (ASAP)",
    "balanced": "Balanced",
    "standard": "Standard",
    "flex": "Flex",
}

#: The pricing page is JSX-heavy; the machine-readable signal is the row `aria-label`, e.g.
#: `"GLM-5.3 Balanced pricing: input $0.50, cached $0.12, output $2.50 per 1M tokens."`
RATE_CARD_ROW = re.compile(
    r'aria-label="(?P<model>[^"]+?) '
    r"(?P<window>Default \(ASAP\)|Balanced|Standard|Flex)"
    r" pricing: input \$(?P<input>[\d.]+), cached \$(?P<cached>[\d.]+), "
    r"output \$(?P<output>[\d.]+)"
)
#: Each model's rows sit in a `<tbody data-model="<slug>">` group. The slug is the identifier
#: the API takes, so it is the key to match on; the display name in the row's label is prose
#: ("DeepSeek V4 Pro" one week, "DeepSeek V4 Pro 0813" the next) and only a fallback.
RATE_CARD_GROUP = re.compile(r'<tbody[^>]*\bdata-model="(?P<slug>[^"]+)"')

TERMINAL = frozenset({"completed", "incomplete", "failed", "cancelled"})
PENDING = frozenset({"queued", "in_progress"})
EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
RESPONSE_ID = re.compile(r"^resp_[A-Za-z0-9_-]{1,200}$")
RETRY_STATUSES = (429, 503, 529)
#: How long one foreground (asap) generation may take. A high-effort turn over a long context
#: took over ten minutes tonight and was cut off at 600; the floor's polling patience is 900.
FOREGROUND_TIMEOUT = 900
MAX_BODY_BYTES = 8_000_000
PLACES = Decimal("0.00000001")
ZERO = Decimal(0)

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY,
    desk_id TEXT NOT NULL,
    session_id TEXT,
    profile TEXT NOT NULL,
    request_key TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    response_id TEXT,
    response TEXT,
    reserved_usd TEXT NOT NULL,
    cost_usd TEXT,
    usage TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS requests_desk ON requests(desk_id, created_at);
CREATE TABLE IF NOT EXISTS budget_days (
    day TEXT NOT NULL,
    desk_id TEXT NOT NULL,
    spent_usd TEXT NOT NULL,
    PRIMARY KEY (day, desk_id)
);
"""


def _parse_rate_card(page: str) -> tuple[dict[tuple[str, str], tuple[str, str, str]], dict[tuple[str, str], tuple[str, str, str]]]:
    """Every pricing row on the card, keyed two ways: by folded display name and window, and by
    the model slug of the `data-model` group the row sits in and window. A row outside any
    group (an older page layout) is still found by its display name."""
    by_name: dict[tuple[str, str], tuple[str, str, str]] = {}
    by_slug: dict[tuple[str, str], tuple[str, str, str]] = {}
    groups = list(RATE_CARD_GROUP.finditer(page))
    for match in RATE_CARD_ROW.finditer(page):
        prices = (match.group("input"), match.group("cached"), match.group("output"))
        window = _fold(match.group("window"))
        by_name[(_fold(match.group("model")), window)] = prices
        slug = None
        for group in groups:
            if group.start() < match.start():
                slug = group.group("slug")
            else:
                break
        if slug:
            by_slug[(slug, window)] = prices
    return by_name, by_slug


def _fold(value: Any) -> str:
    """Compare model and window names on their letters and digits alone.

    "GLM-5.3 Flash", "GLM 5.3 flash" and "glm-5.3-flash" are the same product; the pricing
    page's punctuation is not a fact about the price.
    """
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


class ProviderError(RuntimeError):
    """A request could not be completed. `code` is a stable, body-free category."""

    def __init__(self, code: str, *, retry_after: int | None = None):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


class TransportError(ProviderError):
    """An HTTP or socket failure, collapsed to a code. Carries a `Retry-After` hint when given."""


class BudgetExceeded(ProviderError):
    """The desk cap, the floor cap or the credit reserve would be breached. Nothing was sent."""


# --------------------------------------------------------------------------- rate card


def rates(profile: str) -> tuple[Decimal, Decimal, Decimal]:
    """(input, cached input, output) USD per million tokens for a profile."""
    if profile not in PROFILES:
        raise ProviderError("provider_unknown_profile")
    _, _, inp, cached, out = PROFILES[profile]
    return Decimal(inp), Decimal(cached), Decimal(out)


def model_of(profile: str) -> str:
    """The Sail model id a profile dispatches to."""
    if profile not in PROFILES:
        raise ProviderError("provider_unknown_profile")
    return PROFILES[profile][0]


def window_of(profile: str) -> str:
    """The completion window (`asap`, `balanced`, `standard`, `flex`) a profile buys."""
    if profile not in PROFILES:
        raise ProviderError("provider_unknown_profile")
    return PROFILES[profile][1]


def reservation_usd(profile: str, input_bytes: int, max_output_tokens: int) -> Decimal:
    """Conservative pre-dispatch hold: (bytes/3 + 4096) input tokens plus the whole output cap."""
    inp, _, out = rates(profile)
    tokens_in = Decimal(int(input_bytes)) / Decimal(3) + Decimal(4096)
    usd = (tokens_in * inp + Decimal(int(max_output_tokens)) * out) / Decimal(1_000_000)
    return usd.quantize(PLACES, rounding=ROUND_UP)


def cost_from_usage(profile: str, usage: Any) -> Decimal | None:
    """Settle a response from its token counts, or return None when they are unusable.

    Cached tokens are a subset of `input_tokens` and are billed at the cached rate; reasoning
    tokens are already inside `output_tokens` and are not billed twice.
    """
    if not isinstance(usage, dict):
        return None
    details = usage.get("input_tokens_details", {})
    if details is None:
        details = {}  # absent details mean nothing was cached, which only ever overcharges us
    if not isinstance(details, dict):
        return None
    total_in = usage.get("input_tokens")
    total_out = usage.get("output_tokens")
    cached = details.get("cached_tokens", 0)
    values = (total_in, total_out, cached)
    if any(type(v) is not int or v < 0 for v in values) or cached > total_in:
        return None
    inp, cached_rate, out = rates(profile)
    usd = (
        Decimal(total_in - cached) * inp + Decimal(cached) * cached_rate + Decimal(total_out) * out
    ) / Decimal(1_000_000)
    return usd.quantize(PLACES, rounding=ROUND_UP)


# --------------------------------------------------------------------------- transport


class _NoRedirect(HTTPRedirectHandler):
    """Refuse every redirect: a credentialed request must not follow the server elsewhere."""

    def redirect_request(self, *args, **kwargs):
        return None


def _key_from_env_file(path: Path) -> str | None:
    """Parse `SAIL_API_KEY=` out of an owner-private `.env`. Returns None when unusable."""
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            return None  # world- or group-readable secrets are treated as absent
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    keys = [line.partition("=")[2].strip() for line in lines if line.startswith("SAIL_API_KEY=")]
    if len(keys) != 1 or not keys[0]:
        return None
    return keys[0]


def default_key_source() -> str:
    """The Sail key from `SAIL_API_KEY`, else the repository's owner-private `.env`.

    Never logged, never stored, never returned in an error. A missing key collapses to
    `provider_key_missing` so no path or file content can reach a traceback.
    """
    key = os.environ.get("SAIL_API_KEY", "").strip()
    if not key:
        key = _key_from_env_file(REPO_ROOT / ".env") or ""
    if not key:
        raise TransportError("provider_key_missing")
    return key


env_key_source = default_key_source  # retained name for callers that want the default source


def _retry_after(value: Any) -> int | None:
    if not isinstance(value, str) or not value.strip().isdigit():
        return None
    return max(1, min(3600, int(value.strip())))


class Transport:
    """Allowlisted HTTPS calls to the Sail API. Callable, so tests inject a plain function.

    One route is not on the API host: `GET https://docs.sailresearch.com/pricing.md`, the
    published rate card `rate_card_check` diffs against `PROFILES`. It is fetched as an
    absolute URL, **without the Authorization header** -- the docs site is not the API and has
    no business seeing the floor's key -- and returned as `{"text": ...}` because it is
    markdown, not JSON.
    """

    ROUTES = (
        "POST /v1/responses",
        "GET /v1/responses/{id}",
        "GET /v2/usage/summary",
        "GET " + RATE_CARD_URL,
    )

    def __init__(
        self,
        *,
        key_source: Callable[[], str] = default_key_source,
        base_url: str = API_BASE,
        opener: Any = None,
        headers: dict[str, str] | None = None,
    ):
        parts = urlsplit(base_url)
        if parts.scheme != "https" or parts.netloc != API_HOST or parts.query or parts.fragment:
            raise ValueError(f"the Sail transport only speaks https to {API_HOST}")
        if parts.path.rstrip("/"):
            raise ValueError("the Sail base URL carries no path")
        self.base_url = API_BASE
        self.key_source = key_source
        self._opener = opener
        self.headers = dict(headers or {})
        if any(k.lower() in ("authorization", "cookie", "proxy-authorization") for k in self.headers):
            raise ValueError("caller headers cannot carry credentials")

    def allowed(self, method: str, route: str) -> bool:
        """True for the routes this floor may reach: create, retrieve, usage, the rate card."""
        if method == "POST":
            return route == "/v1/responses"
        if method != "GET":
            return False
        if route == RATE_CARD_URL:
            return True
        head, _, query = route.partition("?")
        if head == "/v2/usage/summary":
            return query == "" or bool(re.fullmatch(r"range=(1h|6h|24h|7d|30d|period)", query))
        if query:
            return False
        prefix, sep, tail = head.partition("/v1/responses/")
        return prefix == "" and sep == "/v1/responses/" and bool(RESPONSE_ID.match(tail))

    def __call__(
        self,
        method: str,
        route: str,
        body: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Perform one call and return the decoded JSON object. Raises `TransportError` only."""
        if not self.allowed(method, route):
            raise TransportError("provider_route_not_allowed")
        data = None
        if body is not None:
            data = canonical(body).encode("utf-8")
            if len(data) > MAX_BODY_BYTES:
                raise TransportError("provider_request_too_large")
        rate_card = route == RATE_CARD_URL
        headers = {"Content-Type": "application/json", "Accept": "application/json", **self.headers}
        if rate_card:
            headers["Accept"] = "text/markdown, text/plain, text/html"
        else:
            headers["Authorization"] = "Bearer " + self.key_source()
        if idempotency_key and method == "POST":
            headers["Idempotency-Key"] = idempotency_key[:255]
        url = route if rate_card else self.base_url + route
        request = Request(url, data=data, headers=headers, method=method)
        # asap foreground generation is awaited inline; background POSTs and every GET are short.
        foreground = method == "POST" and not (body or {}).get("background", False)
        timeout = FOREGROUND_TIMEOUT if foreground else 45
        opener = self._opener or build_opener(_NoRedirect)
        try:
            with opener.open(request, timeout=timeout) as response:
                raw = response.read(MAX_BODY_BYTES + 1)
                if len(raw) > MAX_BODY_BYTES:
                    raise TransportError("provider_response_too_large")
                if rate_card:
                    return {"text": raw.decode("utf-8", "replace")}
                return json.loads(raw)
        except TransportError:
            raise
        except HTTPError as error:
            hint = _retry_after(error.headers.get("Retry-After")) if error.headers else None
            code = error.code
            try:
                error.close()
            except Exception:  # pragma: no cover - close() is best effort
                pass
            raise TransportError(
                f"provider_http_{code}", retry_after=hint if code in RETRY_STATUSES else None
            ) from None
        except TimeoutError:
            raise TransportError("provider_transport_timeout") from None
        except URLError as error:
            timed_out = isinstance(error.reason, TimeoutError)
            raise TransportError(
                "provider_transport_timeout" if timed_out else "provider_transport_unconfirmed"
            ) from None
        except Exception:
            # Never let a provider body, header or credential reach a traceback.
            raise TransportError("provider_transport_unconfirmed") from None


# --------------------------------------------------------------------------- response shapes


@dataclass(frozen=True)
class FunctionCall:
    """One tool call the model asked for. `error` is set when `arguments` was not a JSON object."""

    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    raw_arguments: str = ""

    @property
    def ok(self) -> bool:
        """True when the arguments parsed into an object the tool layer can execute."""
        return self.error is None


@dataclass(frozen=True)
class ProviderResponse:
    """The parts of a Sail response a desk uses, plus the cost record that paid for it."""

    request_id: str
    response_id: str | None
    status: str
    output_text: str
    function_calls: list[FunctionCall]
    reasoning_summaries: list[str]
    output_items: list[dict[str, Any]]
    usage: dict[str, Any]
    cost_usd: Decimal | None
    incomplete: bool
    incomplete_reason: str | None = None

    @property
    def terminal(self) -> bool:
        """True when the response will not change again."""
        return self.status in TERMINAL


def output_items_of(response: Any) -> list[dict[str, Any]]:
    """The raw `output` items, ready to append straight back into the conversation."""
    if not isinstance(response, dict):
        return []
    output = response.get("output")
    if not isinstance(output, list):
        return []
    return [item for item in output if isinstance(item, dict)]


def output_text_of(response: Any) -> str:
    """Concatenate the assistant's visible text. Tolerates a bare string `output`."""
    if isinstance(response, dict) and isinstance(response.get("output"), str):
        return response["output"]
    parts: list[str] = []
    for item in output_items_of(response):
        if item.get("type") not in (None, "message"):
            continue
        content = item.get("content")
        if isinstance(content, str):
            parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                isinstance(block, dict)
                and isinstance(block.get("text"), str)
                and block.get("type") in (None, "output_text", "text")
            ):
                parts.append(block["text"])
    return "\n".join(p for p in parts if p)


def _summary_texts(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        if value.strip():
            out.append(value)
    elif isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str) and text.strip():
            out.append(text)
        elif isinstance(value.get("summary"), (str, list, dict)):
            _summary_texts(value["summary"], out)
    elif isinstance(value, list):
        for item in value:
            _summary_texts(item, out)


def reasoning_summaries_of(response: Any) -> list[str]:
    """Pull reasoning summaries out of the output, tolerating every shape seen in the wild."""
    out: list[str] = []
    for item in output_items_of(response):
        if item.get("type") != "reasoning":
            continue
        before = len(out)
        if "summary" in item:
            _summary_texts(item.get("summary"), out)
        # Sail's DeepSeek and Kimi return the full reasoning under `content` (type
        # `reasoning_text`) with an empty `summary`; the floor publishes the reasoning itself.
        if len(out) == before and "content" in item:
            _summary_texts(item.get("content"), out)
    return out


def function_calls_of(response: Any) -> list[FunctionCall]:
    """Parse `function_call` items. Bad JSON becomes a call carrying a structured error."""
    calls: list[FunctionCall] = []
    for index, item in enumerate(output_items_of(response)):
        if item.get("type") != "function_call":
            continue
        name = item.get("name")
        call_id = item.get("call_id") or item.get("id") or f"call_{index}"
        raw = item.get("arguments", "")
        if not isinstance(name, str) or not name:
            calls.append(
                FunctionCall(str(call_id), "", {}, error="tool call had no name", raw_arguments="")
            )
            continue
        if isinstance(raw, dict):
            calls.append(FunctionCall(str(call_id), name, raw, raw_arguments=canonical(raw)))
            continue
        if not isinstance(raw, str):
            calls.append(
                FunctionCall(str(call_id), name, {}, error="arguments were not a JSON string")
            )
            continue
        try:
            parsed = json.loads(raw or "{}")
        except (ValueError, RecursionError) as exc:
            calls.append(
                FunctionCall(
                    str(call_id),
                    name,
                    {},
                    error=f"arguments were not valid JSON: {exc.__class__.__name__}",
                    raw_arguments=raw[:2000],
                )
            )
            continue
        if not isinstance(parsed, dict):
            calls.append(
                FunctionCall(
                    str(call_id),
                    name,
                    {},
                    error="arguments must be a JSON object",
                    raw_arguments=raw[:2000],
                )
            )
            continue
        calls.append(FunctionCall(str(call_id), name, parsed, raw_arguments=raw[:2000]))
    return calls


def _same_model(expected: str, seen: Any) -> bool:
    if not isinstance(seen, str):
        return False
    return expected.rsplit("/", 1)[-1].lower() == seen.rsplit("/", 1)[-1].lower()


# --------------------------------------------------------------------------- the provider


class Provider:
    """Durable, budgeted access to the Sail Responses API for every desk on the floor."""

    def __init__(
        self,
        path: str | Path,
        *,
        transport: Callable[..., dict[str, Any]] | None = None,
        clock: Callable[[], float] = time.time,
        log: EventLog | None = None,
        floor_cap_usd_per_day: Any = "25",
        reserve_floor_usd: Any = "0",
        sleep: Callable[[float], None] = time.sleep,
        poll_interval: float = 2.0,
        poll_timeout: float = 900.0,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.transport = transport or Transport()
        self.clock = clock
        self.floor_cap = Decimal(str(floor_cap_usd_per_day))
        self.reserve_floor = Decimal(str(reserve_floor_usd))
        #: When set, the per-desk daily limit every request is admitted against, in place of the
        #: caller's `desk_cap_usd_per_day`. The runway policy sets it: a share of the spendable
        #: credit, a fuse against a desk stuck in a loop rather than a budget. None keeps the
        #: caller's cap, which is how the capped policy and the tests run.
        self.desk_fuse: Decimal | None = None
        self.log = log
        self.sleep = sleep
        self.poll_interval = float(poll_interval)
        self.poll_timeout = float(poll_timeout)
        self._lock = threading.RLock()
        self._balance: tuple[float, Decimal | None] | None = None
        self._db = sqlite3.connect(
            str(self.path), isolation_level=None, check_same_thread=False, timeout=30
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(SCHEMA)

    # ------------------------------------------------------------------ helpers
    def _now(self) -> str:
        return now_iso(self.clock)

    def today(self) -> str:
        """The UTC day budgets are counted against, as YYYY-MM-DD."""
        return self._now()[:10]

    @staticmethod
    def request_id_for(desk_id: str, request_key: str) -> str:
        """Derive the durable request id (and Idempotency-Key) from the caller's stable key."""
        material = f"{desk_id}|{request_key}".encode()
        return "req-" + hashlib.sha256(material).hexdigest()[:32]

    def estimate(self, profile: str, input_chars: int, max_output: int) -> Decimal:
        """What `respond` would reserve for a prompt of this size. Never touches the network."""
        return reservation_usd(profile, int(input_chars), int(max_output))

    def build_body(
        self,
        profile: str,
        items: Iterable[Any],
        *,
        tools: Iterable[dict[str, Any]] | None = None,
        reasoning_effort: str = "medium",
        max_output_tokens: int = 8192,
        cache_key: str | None = None,
    ) -> dict[str, Any]:
        """Assemble the Responses API request body for a profile. Pure; no I/O."""
        if profile not in PROFILES:
            raise ProviderError("provider_unknown_profile")
        if reasoning_effort not in EFFORTS:
            raise ProviderError("provider_bad_reasoning_effort")
        if type(max_output_tokens) is not int or not 16 <= max_output_tokens <= 32768:
            raise ProviderError("provider_bad_output_limit")
        input_items = list(items)
        if not input_items:
            raise ProviderError("provider_empty_input")
        model, window = PROFILES[profile][0], PROFILES[profile][1]
        body: dict[str, Any] = {
            "model": model,
            "input": input_items,
            "reasoning": {"effort": reasoning_effort, "generate_summary": "detailed"},
            "max_output_tokens": max_output_tokens,
            "background": window != "asap",
            "metadata": {"completion_window": window},
        }
        if tools:
            body["tools"] = [self._tool_entry(tool) for tool in tools]
            body["tool_choice"] = "auto"
        if cache_key:
            if not isinstance(cache_key, str) or not 1 <= len(cache_key) <= 128:
                raise ProviderError("provider_bad_cache_key")
            body["prompt_cache_key"] = cache_key
        return body

    @staticmethod
    def _tool_entry(tool: dict[str, Any]) -> dict[str, Any]:
        try:
            entry = {
                "type": "function",
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
                "strict": False,
            }
        except (KeyError, TypeError):
            raise ProviderError("provider_bad_tool_schema") from None
        if not isinstance(entry["name"], str) or not isinstance(entry["parameters"], dict):
            raise ProviderError("provider_bad_tool_schema")
        return entry

    # ------------------------------------------------------------------ budgets
    def spent_today(self, desk_id: str | None = None) -> Decimal:
        """Committed USD today: settled costs plus every outstanding reservation."""
        with self._lock:
            if desk_id is None:
                rows = self._db.execute(
                    "SELECT spent_usd FROM budget_days WHERE day = ?", (self.today(),)
                ).fetchall()
            else:
                rows = self._db.execute(
                    "SELECT spent_usd FROM budget_days WHERE day = ? AND desk_id = ?",
                    (self.today(), desk_id),
                ).fetchall()
        return sum((Decimal(r["spent_usd"]) for r in rows), ZERO)

    def spent_since(self, hours: float = 24.0) -> Decimal:
        """Settled model cost over the trailing window, from the request ledger itself.

        This is the burn the runway policy divides the credit by. It reads settled costs, not
        reservations, and it reads requests by when they were created, so a session that ran
        yesterday afternoon still counts toward "the last day" at noon today.
        """
        since = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.gmtime(float(self.clock()) - float(hours) * 3600.0)
        )
        with self._lock:
            rows = self._db.execute(
                "SELECT cost_usd FROM requests WHERE created_at >= ? AND cost_usd IS NOT NULL",
                (since,),
            ).fetchall()
        return sum((Decimal(r["cost_usd"]) for r in rows), ZERO)

    def _add_spend(self, day: str, desk_id: str, delta: Decimal) -> None:
        row = self._db.execute(
            "SELECT spent_usd FROM budget_days WHERE day = ? AND desk_id = ?", (day, desk_id)
        ).fetchone()
        current = Decimal(row["spent_usd"]) if row else ZERO
        total = current + delta
        if total < ZERO:
            total = ZERO
        self._db.execute(
            "INSERT INTO budget_days (day, desk_id, spent_usd) VALUES (?, ?, ?)"
            " ON CONFLICT(day, desk_id) DO UPDATE SET spent_usd = excluded.spent_usd",
            (day, desk_id, format(total, "f")),
        )

    def check_balance(self) -> Decimal | None:
        """Reported Sail credit in USD, cached for 60 seconds. None when it cannot be confirmed.

        The usage summary reports fractional cents, so a balance of 3106.14 is $31.06.
        """
        now = self.clock()
        if self._balance is not None and now - self._balance[0] < 60:
            return self._balance[1]
        value: Decimal | None = None
        try:
            summary = self.transport("GET", "/v2/usage/summary")
            balance = summary.get("balance") if isinstance(summary, dict) else None
            if (
                isinstance(summary, dict)
                and summary.get("available") is True
                and summary.get("balance_unavailable") is not True
                and type(balance) in (int, float)
            ):
                cents = Decimal(str(balance))
                if cents.is_finite():
                    value = (cents / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        except (ProviderError, ValueError, TypeError, AttributeError, KeyError):
            value = None
        self._balance = (now, value)
        return value

    # ------------------------------------------------------------------ rate card
    def rate_card_check(self) -> dict[str, Any]:
        """Diff the frozen `PROFILES` against Sail's published card and alert on any drift.

        The floor's cost ticker is only honest if the card underneath it is checked: Sail cut
        prices between September 7 and today, which proves the card moves. This reads
        `https://docs.sailresearch.com/pricing.md` through the injected transport, parses the
        machine-readable `aria-label` rows, and appends one `ops.alert` per profile whose live
        price differs -- or whose row it could not find at all, because a page whose format
        changed must fail loudly rather than silently report no drift.

        It never edits `PROFILES`. Guardrails are human-written; this one alerts only, and it
        is quiet about its own failures: an unreachable page is not an incident.
        """
        summary: dict[str, Any] = {
            "checked": 0, "rows": 0, "drift": [], "unchecked": [], "error": None
        }
        try:
            page = self._rate_card_page()
        except Exception as exc:  # transport, decoding, anything
            summary["error"] = type(exc).__name__
            return summary
        if not page:
            summary["error"] = "empty"
            return summary
        published, by_slug = _parse_rate_card(page)
        summary["rows"] = len(published)
        if not published:
            self._alert_rate_card(
                "error", "rate card: no pricing rows parsed; the page format has changed"
            )
            summary["error"] = "unparsed"
            return summary

        for profile in sorted(PROFILES):
            model, window, *ours = PROFILES[profile]
            display = DISPLAY_NAMES.get(model)
            label = WINDOW_LABELS.get(window)
            theirs = by_slug.get((model, _fold(label))) if label else None
            if theirs is None and display and label:
                theirs = published.get((_fold(display), _fold(label)))
            if theirs is None:
                summary["unchecked"].append(profile)
                self._alert_rate_card(
                    "warn", f"rate card: no published row for {profile} ({model}/{window})"
                )
                continue
            summary["checked"] += 1
            if [Decimal(v) for v in theirs] != [Decimal(v) for v in ours]:
                summary["drift"].append(
                    {"profile": profile, "model": model, "window": window,
                     "ours": list(ours), "published": list(theirs)}
                )
                self._alert_rate_card(
                    "error",
                    f"rate card drift: {profile} ({model}/{window}) is held at "
                    f"{'/'.join(ours)} and Sail publishes {'/'.join(theirs)} "
                    "per 1M tokens (input/cached/output)",
                )
        return summary

    def _rate_card_page(self) -> str:
        """The published rate card as text. Accepts whatever shape the transport returns."""
        payload = self.transport("GET", RATE_CARD_URL)
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            for key in ("text", "content", "body", "markdown"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value
        if isinstance(payload, bytes):
            return payload.decode("utf-8", "replace")
        return ""

    def _alert_rate_card(self, level: str, message: str) -> None:
        if self.log is None:
            return
        at = self._now()
        try:
            self.log.append(
                "ops",
                "ops.alert",
                {"level": level, "text": message},
                id="ratecard:" + hashlib.sha256(
                    f"{at[:10]}|{message}".encode("utf-8")
                ).hexdigest()[:24],
                at=at,
            )
        except Exception:
            # An alert that cannot be written must not take the floor down with it.
            pass

    # ------------------------------------------------------------------ records
    def record(self, request_key: str) -> dict[str, Any] | None:
        """The stored row for a request key, as a plain dict. For recovery and inspection."""
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM requests WHERE request_key = ?", (request_key,)
            ).fetchone()
        return dict(row) if row else None

    def records(self, desk_id: str | None = None) -> list[dict[str, Any]]:
        """Every stored request row, oldest first, optionally for one desk."""
        with self._lock:
            if desk_id is None:
                rows = self._db.execute("SELECT * FROM requests ORDER BY created_at, id").fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM requests WHERE desk_id = ? ORDER BY created_at, id", (desk_id,)
                ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ the call
    def respond(
        self,
        profile: str,
        items: Iterable[Any],
        *,
        tools: Iterable[dict[str, Any]] | None = None,
        desk_id: str,
        session_id: str | None = None,
        request_key: str,
        reasoning_effort: str = "medium",
        max_output_tokens: int = 8192,
        desk_cap_usd_per_day: Any,
        cache_key: str | None = None,
    ) -> ProviderResponse:
        """Run one model call within budget, deduped on `request_key`, and settle its cost.

        Raises `BudgetExceeded` before anything is sent when the desk cap, the floor cap or the
        credit reserve would be breached, and `ProviderError` when the call could not be
        completed (the reservation is retained in that case).
        """
        if not isinstance(desk_id, str) or not desk_id:
            raise ProviderError("provider_missing_desk")
        if not isinstance(request_key, str) or not 1 <= len(request_key) <= 200:
            raise ProviderError("provider_bad_request_key")
        body = self.build_body(
            profile,
            items,
            tools=tools,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
            cache_key=cache_key,
        )
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM requests WHERE request_key = ?", (request_key,)
            ).fetchone()
        if row is None and self.reserve_floor > ZERO:
            # Network call, so it happens before the write lock is taken. A balance we cannot
            # confirm is not treated as zero: only a confirmed shortfall refuses the request.
            balance = self.check_balance()
            if balance is not None and balance < self.reserve_floor:
                raise BudgetExceeded("provider_credit_below_reserve")
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM requests WHERE request_key = ?", (request_key,)
            ).fetchone()
            if row is None:
                row = self._admit(
                    profile=profile,
                    body=body,
                    desk_id=desk_id,
                    session_id=session_id,
                    request_key=request_key,
                    desk_cap=Decimal(str(desk_cap_usd_per_day)),
                    max_output_tokens=max_output_tokens,
                )
            row = dict(row)
        if row["status"] in TERMINAL:
            # A crash-retry re-reads the stored response instead of paying for it again.
            return self._response_from_row(row)
        return self._dispatch(row)

    def _admit(
        self,
        *,
        profile: str,
        body: dict[str, Any],
        desk_id: str,
        session_id: str | None,
        request_key: str,
        desk_cap: Decimal,
        max_output_tokens: int,
    ) -> sqlite3.Row:
        encoded = canonical(body)
        readable = {"input": body.get("input", []), "tools": body.get("tools", [])}
        reserved = reservation_usd(
            profile, len(canonical(readable).encode("utf-8")), max_output_tokens
        )
        day = self.today()
        stamp = self._now()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            desk_row = self._db.execute(
                "SELECT spent_usd FROM budget_days WHERE day = ? AND desk_id = ?", (day, desk_id)
            ).fetchone()
            desk_spent = Decimal(desk_row["spent_usd"]) if desk_row else ZERO
            floor_rows = self._db.execute(
                "SELECT spent_usd FROM budget_days WHERE day = ?", (day,)
            ).fetchall()
            floor_spent = sum((Decimal(r["spent_usd"]) for r in floor_rows), ZERO)
            limit = self.desk_fuse if self.desk_fuse is not None else desk_cap
            if desk_spent + reserved > limit:
                raise BudgetExceeded("provider_desk_cap_exceeded")
            if floor_spent + reserved > self.floor_cap:
                raise BudgetExceeded("provider_floor_cap_exceeded")
            self._add_spend(day, desk_id, reserved)
            self._db.execute(
                "INSERT INTO requests (id, desk_id, session_id, profile, request_key, body, status,"
                " reserved_usd, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.request_id_for(desk_id, request_key),
                    desk_id,
                    session_id,
                    profile,
                    request_key,
                    encoded,
                    "prepared",
                    format(reserved, "f"),
                    stamp,
                    stamp,
                ),
            )
            self._db.execute("COMMIT")
        except Exception as exc:
            try:
                self._db.execute("ROLLBACK")
            except sqlite3.OperationalError:  # pragma: no cover - rollback of a closed tx
                pass
            if isinstance(exc, sqlite3.IntegrityError):
                # Another process admitted the same key first. Its row, and its reservation,
                # are the ones that count; we join it rather than reserving twice.
                existing = self._db.execute(
                    "SELECT * FROM requests WHERE request_key = ?", (request_key,)
                ).fetchone()
                if existing is not None:
                    return existing
            raise
        return self._db.execute(
            "SELECT * FROM requests WHERE request_key = ?", (request_key,)
        ).fetchone()

    def _dispatch(self, row: dict[str, Any]) -> ProviderResponse:
        body = json.loads(row["body"])
        profile = row["profile"]
        response_id = row["response_id"]
        deadline = self.clock() + self.poll_timeout
        while True:
            try:
                if response_id:
                    payload = self.transport("GET", f"/v1/responses/{response_id}")
                else:
                    payload = self.transport("POST", "/v1/responses", body, row["id"])
            except ProviderError as exc:
                self._mark_error(row["id"], exc.code)
                raise
            except Exception:
                self._mark_error(row["id"], "provider_transport_unconfirmed")
                raise TransportError("provider_transport_unconfirmed") from None
            seen_id = payload.get("id") if isinstance(payload, dict) else None
            status = payload.get("status") if isinstance(payload, dict) else None
            if not isinstance(seen_id, str) or not RESPONSE_ID.match(seen_id):
                self._mark_error(row["id"], "provider_bad_response_id")
                raise ProviderError("provider_bad_response_id")
            if response_id and seen_id != response_id:
                self._mark_error(row["id"], "provider_response_identity_changed")
                raise ProviderError("provider_response_identity_changed")
            # Persist the accepted id before any validation can reject the response we now owe for.
            if not response_id:
                with self._lock:
                    self._db.execute(
                        "UPDATE requests SET response_id = ?, status = ?, updated_at = ?"
                        " WHERE id = ? AND response_id IS NULL",
                        (seen_id, "dispatched", self._now(), row["id"]),
                    )
                response_id = seen_id
            if status not in TERMINAL | PENDING:
                self._mark_error(row["id"], "provider_unknown_status")
                raise ProviderError("provider_unknown_status")
            if not _same_model(model_of(profile), payload.get("model")):
                self._mark_error(row["id"], "provider_model_mismatch")
                raise ProviderError("provider_model_mismatch")
            if status in TERMINAL:
                return self._settle(row, payload, status)
            if self.clock() >= deadline:
                self._mark_error(row["id"], "provider_poll_timeout")
                raise ProviderError("provider_poll_timeout")
            self.sleep(self.poll_interval)

    def _mark_error(self, request_id: str, code: str) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE requests SET error = ?, updated_at = ? WHERE id = ?",
                (code, self._now(), request_id),
            )

    def _settle(
        self, row: dict[str, Any], payload: dict[str, Any], status: str
    ) -> ProviderResponse:
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        settled = cost_from_usage(row["profile"], payload.get("usage"))
        reserved = Decimal(row["reserved_usd"])
        error = None
        if settled is None:
            # Unusable token accounting never releases the hold: the reservation *is* the
            # charge, and the row is flagged so a human can settle it against the invoice.
            cost = reserved
            error = "usage_unsettled"
        else:
            cost = settled
            if cost > reserved:
                error = "cost_exceeds_reservation"
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                self._db.execute(
                    "UPDATE requests SET status = ?, response_id = ?, response = ?, usage = ?,"
                    " cost_usd = ?, updated_at = ?, error = ? WHERE id = ?",
                    (
                        status,
                        payload.get("id"),
                        canonical(payload),
                        canonical(usage),
                        format(cost, "f"),
                        self._now(),
                        error,
                        row["id"],
                    ),
                )
                self._add_spend(row["created_at"][:10], row["desk_id"], cost - reserved)
                self._db.execute("COMMIT")
            except Exception:
                try:
                    self._db.execute("ROLLBACK")
                except sqlite3.OperationalError:  # pragma: no cover
                    pass
                raise
            stored = dict(
                self._db.execute("SELECT * FROM requests WHERE id = ?", (row["id"],)).fetchone()
            )
        result = self._response_from_row(stored)
        self._emit(stored, result)
        return result

    def _response_from_row(self, row: dict[str, Any]) -> ProviderResponse:
        payload = json.loads(row["response"]) if row["response"] else {}
        details = payload.get("incomplete_details") or {}
        reason = details.get("reason") if isinstance(details, dict) else None
        return ProviderResponse(
            request_id=row["id"],
            response_id=row["response_id"],
            status=row["status"],
            output_text=output_text_of(payload),
            function_calls=function_calls_of(payload),
            reasoning_summaries=reasoning_summaries_of(payload),
            output_items=output_items_of(payload),
            usage=json.loads(row["usage"]) if row["usage"] else {},
            cost_usd=Decimal(row["cost_usd"]) if row["cost_usd"] is not None else None,
            incomplete=row["status"] == "incomplete",
            incomplete_reason=reason if isinstance(reason, str) else None,
        )

    def _emit(self, row: dict[str, Any], result: ProviderResponse) -> None:
        if self.log is None:
            return
        payload = {
            "request_id": row["id"],
            "desk_id": row["desk_id"],
            "session_id": row["session_id"],
            "profile": row["profile"],
            "status": row["status"],
            "cost_usd": None if result.cost_usd is None else format(result.cost_usd, "f"),
            "usage": result.usage,
            "_response_id": row["response_id"],
        }
        self.log.append("ops", "provider.request", payload, id="pr-" + row["id"], public=False)

    def close(self) -> None:
        """Close the SQLite handle."""
        with self._lock:
            self._db.close()
