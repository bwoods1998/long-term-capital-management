"""Live venue adapters: shared credentials, signing and request plumbing.

Every adapter in this package implements `ltcm.broker.Broker` against a real venue and
obeys the same four rules:

1. **Credentials are injected, never read.** A `Credentials` dataclass is constructed by the
   service from whatever secret store it uses. Nothing in this package touches `os.environ`,
   `.env` or a key file, so an adapter can never widen its own access.
2. **Secrets never reach a log or a repr.** Every credentials class masks itself, and no request
   body, header dict or exception message built here contains a key, a secret or a signature.
3. **The intent id is the idempotency key.** `client_order_id` is `OrderIntent.id`, so a retry
   after a lost response finds the original order instead of placing a second one.
4. **An unconfirmed write is `UnknownOutcome`, never a silent retry.** When a POST times out the
   adapter looks the order up by its client order id; if that lookup cannot confirm either way,
   it raises `UnknownOutcome` and the service reconciles before anything else happens.

Signing lives behind the `Signer` protocol. The concrete signers are the only place in the whole
runtime that imports `cryptography`, and they import it lazily inside a method, so the core
modules stay standard library only and tests inject a fake signer instead.
"""

from __future__ import annotations

import base64
import json
import secrets
import urllib.parse
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Protocol, runtime_checkable

from ..broker import (
    BrokerError,
    Order,
    RejectedOrder,
    UnknownOutcome,
    VenueUnavailable,
    money,
)
from ..data import HttpTransport

JSON = "application/json"


# ------------------------------------------------------------------- signing

@runtime_checkable
class Signer(Protocol):
    """Signs a byte string with a private key the adapter never sees.

    `algorithm` names the scheme so a caller building a JWS header knows what to write.
    Implementations must be safe to call from several threads.
    """

    algorithm: str

    def sign(self, message: bytes) -> bytes:
        """Return the raw signature bytes, already in the form the venue expects."""


class RsaPssSigner:
    """RSA-PSS over SHA-256 with a digest-length salt: Kalshi's request signature.

    https://docs.kalshi.com/getting_started/api_keys
    """

    algorithm = "RSA-PSS-SHA256"

    def __init__(self, private_key_pem: "bytes | str"):
        if isinstance(private_key_pem, str):
            private_key_pem = private_key_pem.encode("utf-8")
        if b"PRIVATE KEY" not in private_key_pem:
            raise ValueError("expected a PEM private key")
        self._pem = private_key_pem
        self._key: Any = None

    def _load(self) -> Any:
        if self._key is None:
            from cryptography.hazmat.primitives import serialization

            self._key = serialization.load_pem_private_key(self._pem, password=None)
        return self._key

    def sign(self, message: bytes) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        return self._load().sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )

    def __repr__(self) -> str:  # never print key material
        return "RsaPssSigner(<pem>)"


class CdpSigner:
    """Coinbase CDP key signing: EdDSA for an Ed25519 secret, ES256 for an ECDSA PEM.

    A CDP "secret API key" arrives either as a PEM block or as base64. The base64 form is either
    a DER-encoded private key or the raw 64-byte Ed25519 keypair (32-byte seed followed by the
    32-byte public key); a bare 32-byte value is the seed alone. ES256 signatures are returned as
    raw `r || s`, which is what JWS wants, not the DER sequence `cryptography` produces.

    https://docs.cdp.coinbase.com/api-reference/v2/authentication
    """

    def __init__(self, secret: "bytes | str"):
        self._secret = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
        self._key: Any = None
        self._algorithm: "str | None" = None

    def _load(self) -> Any:
        if self._key is not None:
            return self._key
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519

        raw = self._secret
        if b"PRIVATE KEY" in raw:
            key = serialization.load_pem_private_key(raw, password=None)
        else:
            text_value = raw.decode("ascii", "strict").strip()
            decoded = base64.b64decode(text_value + "=" * (-len(text_value) % 4))
            try:
                key = serialization.load_der_private_key(decoded, password=None)
            except ValueError:
                if len(decoded) not in (32, 64):
                    raise ValueError("CDP secret is neither PEM, DER nor a 32/64-byte Ed25519 key")
                key = ed25519.Ed25519PrivateKey.from_private_bytes(decoded[:32])
        self._key = key
        self._algorithm = "EdDSA" if isinstance(key, ed25519.Ed25519PrivateKey) else "ES256"
        return key

    @property
    def algorithm(self) -> str:
        self._load()
        return self._algorithm or "ES256"

    def sign(self, message: bytes) -> bytes:
        key = self._load()
        if self._algorithm == "EdDSA":
            return key.sign(message)
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

        der = key.sign(message, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return r.to_bytes(32, "big") + s.to_bytes(32, "big")

    def __repr__(self) -> str:  # never print key material
        return "CdpSigner(<secret>)"


class GatewaySigner:
    """Gateway mode: this process holds no venue key at all, only a bearer token.

    The order gateway (a separate Cloudflare Worker) holds the Kalshi and Coinbase private keys,
    signs every request itself, and enforces the hard caps and the kill switch before it forwards
    anything. So an adapter running in gateway mode still builds the same request, but the
    signature it would have produced is empty and `VenueClient` replaces the venue's auth headers
    with `Authorization: Bearer <token>` on the way out.

    The difference this makes is the whole point of the arrangement: a machine running the desks
    can ask for an order, but it cannot sign one, and it cannot raise its own limits.
    """

    algorithm = "none"

    def __init__(self, token: str):
        if not isinstance(token, str) or len(token.strip()) < 32:
            raise ValueError("gateway token must be at least 32 characters")
        self._token = token.strip()

    def headers(self) -> dict[str, str]:
        """The only credential this process has: the gateway's bearer token."""
        return {"Authorization": "Bearer " + self._token}

    def sign(self, message: bytes) -> bytes:
        """No key, no signature. The gateway signs; `VenueClient` drops what this produces."""
        return b""

    def __repr__(self) -> str:  # never print the token
        return "GatewaySigner(<token>)"


def b64url(data: bytes) -> str:
    """Unpadded base64url, the only encoding a JWS uses."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def jws(header: dict[str, Any], payload: dict[str, Any], signer: Signer) -> str:
    """Assemble a compact JWS. Pure standard library; the key lives behind `signer`."""
    signing_input = (
        b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        + "."
        + b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    )
    return signing_input + "." + b64url(signer.sign(signing_input.encode("ascii")))


# --------------------------------------------------------------- credentials

class _Masked:
    """Mixin: a credentials repr shows the shape of the secret, never the secret."""

    def __repr__(self) -> str:
        name = type(self).__name__
        identity = getattr(self, "key_id", None) or getattr(self, "key_name", "")
        tail = str(identity)[-4:] if identity else "?"
        return f"{name}(key_id=...{tail}, secret=<redacted>)"

    __str__ = __repr__


@dataclass(frozen=True, repr=False)
class AlpacaCredentials(_Masked):
    """Alpaca header auth. `paper` picks the base URL; nothing else changes."""

    key_id: str
    secret_key: str
    paper: bool = True

    def __post_init__(self):
        if not isinstance(self.key_id, str) or not self.key_id.strip():
            raise ValueError("alpaca key_id is required")
        if not isinstance(self.secret_key, str) or not self.secret_key.strip():
            raise ValueError("alpaca secret_key is required")

    def headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret_key,
        }


@dataclass(frozen=True, repr=False)
class KalshiCredentials(_Masked):
    """A Kalshi key id plus the signer holding its RSA private key."""

    key_id: str
    signer: Any

    def __post_init__(self):
        if not isinstance(self.key_id, str) or not self.key_id.strip():
            raise ValueError("kalshi key_id is required")
        if not hasattr(self.signer, "sign"):
            raise ValueError("kalshi credentials need a Signer")


@dataclass(frozen=True, repr=False)
class CoinbaseCredentials(_Masked):
    """A CDP key id (the `kid`/`sub` claim) plus the signer holding its private key."""

    key_id: str
    signer: Any

    def __post_init__(self):
        if not isinstance(self.key_id, str) or not self.key_id.strip():
            raise ValueError("coinbase key_id is required")
        if not hasattr(self.signer, "sign"):
            raise ValueError("coinbase credentials need a Signer")


# ----------------------------------------------------------------- requests

def encode(body: Any) -> bytes:
    """A request body as compact, sorted JSON so the same order always serializes the same."""
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def decode(payload: bytes, *, what: str) -> Any:
    """Parse a response body with Decimal numbers. Never returns a float."""
    if not payload:
        return None
    try:
        return json.loads(
            payload.decode("utf-8"),
            parse_float=Decimal,
            parse_constant=lambda name: (_ for _ in ()).throw(BrokerError(f"{what}: {name}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerError(f"{what}: malformed JSON response") from exc


def dec(value: Any, default: Any = None) -> "Decimal | None":
    """Parse a venue number defensively; `None` for null, missing or unusable values."""
    if value is None or isinstance(value, bool):
        return None if default is None else money(default)
    if isinstance(value, float):
        value = repr(value)
    try:
        parsed = money(value)
    except (ValueError, ArithmeticError):
        return None if default is None else money(default)
    return parsed if parsed.is_finite() else (None if default is None else money(default))


def message_of(payload: Any, *, limit: int = 300) -> str:
    """A short human-readable error from a venue body, with no echo of what we sent."""
    if isinstance(payload, dict):
        for key in ("message", "error_message", "error", "msg", "detail", "reason"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:limit]
        return json.dumps(payload, sort_keys=True)[:limit]
    if isinstance(payload, str):
        return payload.strip()[:limit]
    return ""


#: What has to come off a venue path to leave the path the gateway routes on. Kalshi signs (and
#: therefore carries) its `/trade-api/v2` prefix; Coinbase's paths are already absolute.
GATEWAY_PREFIXES: dict[str, str] = {"kalshi": "/trade-api/v2/", "coinbase": "/", "alpaca": "/", "alpaca-paper": "/"}

#: Venue auth headers an adapter builds and gateway mode throws away: this process cannot sign.
VENUE_AUTH_HEADERS = (
    "authorization",
    "kalshi-access-key",
    "kalshi-access-timestamp",
    "kalshi-access-signature",
    "apca-api-key-id",
    "apca-api-secret-key",
)

#: The header a Coinbase order carries so the gateway can price a `base_size` in dollars.
REFERENCE_HEADER = "X-LTCM-Reference-Price"
#: What an order is for (`entry` or `exit`); the gateway lets an exit through its dollar caps.
PURPOSE_HEADER = "X-LTCM-Purpose"

#: The one Coinbase path whose POST creates an order, which is the only one that needs the price.
COINBASE_ORDERS_PATH = "api/v3/brokerage/orders"


def gateway_path(venue: str, url: str) -> tuple[str, str]:
    """Split a venue URL into `(path, query)` as the gateway wants them: no host, no prefix."""
    parts = urllib.parse.urlsplit(url)
    path = parts.path
    prefix = GATEWAY_PREFIXES.get(venue, "/")
    path = path[len(prefix):] if path.startswith(prefix) else path.lstrip("/")
    return path.lstrip("/"), parts.query


def gateway_url_for(gateway_url: str, venue: str, url: str) -> str:
    """A venue URL rewritten onto the order gateway: `<gateway_url>/v1/<venue>/<path>?<query>`."""
    path, query = gateway_path(venue, url)
    rewritten = f"{gateway_url.rstrip('/')}/v1/{venue}/{path}"
    return rewritten + ("?" + query if query else "")


class VenueClient:
    """A thin signed-or-keyed HTTP client shared by the adapters.

    Wraps a transport exposing `request(method, url, headers=, body=, timeout=)`. HTTP status
    codes come back to the caller; only a transport failure raises, and it raises
    `TransportError` so the caller can decide whether that means `UnknownOutcome`.

    **Gateway mode.** Given `gateway_url`, a `venue` and a `GatewaySigner`, every request is
    rewritten onto the order gateway instead of the venue, the venue's own auth headers are
    dropped, and the gateway's bearer token is the only credential that leaves this process. The
    adapters above are unchanged by this: they build the same request either way, and the one
    thing they cannot do in gateway mode is produce a valid venue signature.
    """

    def __init__(
        self,
        transport: Any = None,
        *,
        timeout: float = 20.0,
        user_agent: Any = None,
        gateway_url: "str | None" = None,
        gateway: Any = None,
        venue: "str | None" = None,
        reference_price: Any = None,
    ):
        self.transport = transport or HttpTransport(
            **({"user_agent": user_agent} if user_agent else {})
        )
        self.timeout = float(timeout)
        self.calls: list[dict[str, Any]] = []
        if gateway_url and (gateway is None or not venue):
            raise ValueError("gateway mode needs a GatewaySigner and a venue name")
        self.gateway_url = gateway_url.rstrip("/") if gateway_url else None
        self.gateway = gateway
        self.venue = venue
        #: `product_id -> Decimal | None`, used only to price a Coinbase order for the caps.
        self.reference_price = reference_price

    def _to_gateway(
        self, method: str, url: str, headers: dict[str, str], body: Any
    ) -> tuple[str, dict[str, str]]:
        """Rewrite one request for the gateway: its URL, its auth, and a price when it needs one."""
        path, _ = gateway_path(self.venue or "", url)
        sent = {
            name: value
            for name, value in headers.items()
            if name.lower() not in VENUE_AUTH_HEADERS
        }
        sent.update(self.gateway.headers())
        if (
            self.venue == "coinbase"
            and method.upper() == "POST"
            and path == COINBASE_ORDERS_PATH
            and self.reference_price is not None
            and isinstance(body, dict)
        ):
            # The gateway prices a `base_size` order in dollars to check it against the caps, and
            # it has no market data of its own. A quote this desk already has is cheaper and more
            # honest than one the gateway would have to go and fetch.
            price = self.reference_price(body.get("product_id"))
            if price is not None and price > 0:
                sent[REFERENCE_HEADER] = format(money(price), "f")
        return gateway_url_for(self.gateway_url or "", self.venue or "", url), sent

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: "dict[str, str] | None" = None,
        body: Any = None,
        what: str = "venue",
    ) -> tuple[int, Any]:
        """One request. Returns `(status, parsed json)`; raises `TransportError` on no reply."""
        sent = {"Accept": JSON}
        if body is not None:
            sent["Content-Type"] = JSON
        sent.update(headers or {})
        if self.gateway_url:
            url, sent = self._to_gateway(method, url, sent, body)
        payload = encode(body) if body is not None else None
        status, _, raw = self.transport.request(
            method, url, headers=sent, body=payload, timeout=self.timeout
        )
        try:
            return status, decode(raw, what=what)
        except BrokerError:
            if 200 <= status < 300:
                raise  # a successful response that is not JSON is a real shape change
            # A failing response often carries an HTML error page from a proxy. The status
            # code is the fact that matters; keep the text as the message and let the caller
            # classify it rather than reporting "malformed JSON" for a plain 503.
            return status, {"message": raw.decode("utf-8", "replace").strip()[:300]}


def require_ok(status: int, payload: Any, *, what: str, ok: tuple[int, ...] = (200, 201, 204)) -> Any:
    """Turn a non-success status into the right `BrokerError` subclass."""
    if status in ok:
        return payload
    detail = message_of(payload)
    text_value = f"{what}: HTTP {status}{(' ' + detail) if detail else ''}"
    if status in (401, 403):
        raise VenueUnavailable(text_value)
    if status == 429 or status >= 500:
        raise VenueUnavailable(text_value)
    raise RejectedOrder(text_value)


def confirm_or_unknown(
    lookup: Callable[[], "Order | None"], *, what: str, detail: str
) -> Order:
    """After a lost write: return the venue's copy of the order, or raise `UnknownOutcome`.

    Never retries the write. A second POST with the same `client_order_id` would be rejected by
    a well-behaved venue, but "well-behaved" is not something to bet the book on.
    """
    try:
        found = lookup()
    except Exception:  # the follow-up failed too; the outcome is still unknown
        found = None
    if found is not None:
        return found
    raise UnknownOutcome(f"{what}: {detail}; order state could not be confirmed - reconcile")


def new_nonce() -> str:
    """16 bytes of hex, the nonce a CDP JWT header carries."""
    return secrets.token_hex(16)


__all__ = [
    "Signer",
    "RsaPssSigner",
    "CdpSigner",
    "GatewaySigner",
    "AlpacaCredentials",
    "KalshiCredentials",
    "CoinbaseCredentials",
    "VenueClient",
    "gateway_path",
    "gateway_url_for",
    "GATEWAY_PREFIXES",
    "REFERENCE_HEADER",
    "PURPOSE_HEADER",
    "COINBASE_ORDERS_PATH",
    "b64url",
    "jws",
    "encode",
    "decode",
    "dec",
    "message_of",
    "require_ok",
    "confirm_or_unknown",
    "new_nonce",
]
