"""Build the exact bytes the House's Alpaca adapter sends to the gateway for every practice order
shape it can produce, by running the adapter itself over a capturing transport in gateway mode
(review of p/gateway, Sept 25, 2026). `review-adapter-bodies.json` is its output for this tree
(label "vbase") and for `git archive origin/p/book ltcm league` (ca68f8e, label "pbook"), one row
kept per shape.

Usage: python3 gateway/test/review_adapter_bodies.py <repo-root> <label> > out.jsonl"""
import json, sys
from decimal import Decimal
root, label = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
from ltcm.broker import Instrument, OrderIntent
from ltcm.adapters import AlpacaCredentials, VenueClient
from ltcm.adapters.alpaca import AlpacaBroker

class Signer:
    def headers(self): return {"Authorization": "Bearer t"}

class Tape:
    def __init__(self): self.calls = []
    def request(self, method, url, headers=None, body=None, timeout=None):
        self.calls.append((method, url, dict(headers or {}), body))
        return 200, {}, b'{"id":"v-1","client_order_id":"oi-x","status":"accepted","qty":"1","side":"buy","symbol":"X","type":"limit","legs":[]}'

tape = Tape()
client = VenueClient(tape, gateway_url="https://gw.example", gateway=Signer(), venue="alpaca-paper")
broker = AlpacaBroker(AlpacaCredentials("k", "s", paper=True), client=client, venue="alpaca-paper")
out = []

def send(name, inst, side, qty, otype, limit, tif, purpose="entry"):
    extra = {"purpose": "exit", "exit_reason": "desk", "exit_of": "in-x"} if purpose == "exit" else {}
    it = OrderIntent.new(desk_id="book-alpaca-paper", instrument=inst, side=side, quantity=Decimal(qty), order_type=otype,
                         limit_price=None if limit is None else Decimal(limit), time_in_force=tif, rationale="r",
                         created_at="2026-09-25T14:00:00Z", nonce=name, **extra)
    n = len(tape.calls)
    try:
        broker.submit(it)
    except Exception as exc:
        out.append({"label": label, "name": name, "adapter_error": f"{type(exc).__name__}: {exc}"}); return
    for method, url, headers, body in tape.calls[n:]:
        if method == "POST":
            out.append({"label": label, "name": name, "method": method, "url": url,
                        "purpose": headers.get("X-LTCM-Purpose"), "body": body.decode() if body else ""})

V = "alpaca-paper"
crypto = lambda s: Instrument("crypto", s.replace("/", "-"), V, market_id=s)
eq = lambda s: Instrument("equity", s, V)
opt = lambda root, exp, k, r: Instrument("option", root, V, multiplier=Decimal(100), expiry=exp, strike=Decimal(k), right=r)
for pair in ["AAVE/USD", "AVAX/USD", "BTC/USD", "DOGE/USD", "DOT/USD", "ETH/USD", "LINK/USD", "LTC/USD", "SOL/USD", "UNI/USD", "XRP/USD"]:
    send(f"crypto limit buy {pair}", crypto(pair), "buy", "0.344620609", "limit", "116.069668617", "gtc")
    send(f"crypto limit sell {pair}", crypto(pair), "sell", "0.344620609", "limit", "117.01", "gtc", "exit")
    send(f"crypto market sell {pair}", crypto(pair), "sell", "0.5", "market", None, "gtc", "exit")
    send(f"crypto market buy {pair}", crypto(pair), "buy", "0.5", "market", None, "gtc")
    send(f"crypto ioc buy {pair}", crypto(pair), "buy", "0.5", "limit", "1.5", "ioc")
for s in ["AAPL", "AMD", "AMZN", "AVGO", "DIA", "GLD", "GOOGL", "IWM", "JPM", "META", "MSFT", "NFLX", "NVDA", "PLTR", "QQQ", "SPY", "TLT", "TSLA", "BRK.B"]:
    send(f"equity market buy frac {s}", eq(s), "buy", "0.123456789", "market", None, "day")
    send(f"equity market sell frac {s}", eq(s), "sell", "0.123456789", "market", None, "day", "exit")
    send(f"equity limit buy whole gtc {s}", eq(s), "buy", "3", "limit", "101.25", "gtc")
    send(f"equity limit sell frac day {s}", eq(s), "sell", "0.5", "limit", "101.25", "day", "exit")
for root_, k in [("AAL", "13"), ("BAC", "45.5"), ("F", "12.5"), ("INTC", "22"), ("PFE", "30"), ("RIVN", "14"), ("SNAP", "8.5"), ("SOFI", "15"), ("T", "27"), ("VALE", "10.5"), ("SPY", "580")]:
    for right in ("call", "put"):
        for tif in ("day", "gtc", "ioc"):
            send(f"option buy {root_} {right} {tif}", opt(root_, "2026-09-25", k, right), "buy", "1", "limit", "0.05", tif)
            send(f"option sell exit {root_} {right} {tif}", opt(root_, "2026-09-25", k, right), "sell", "2", "limit", "0.01", tif, "exit")
            send(f"option buy exit {root_} {right} {tif}", opt(root_, "2026-09-25", k, right), "buy", "1", "limit", "0.05", tif, "exit")

# Structures, where this adapter knows them (p/book): every type, opened at a typical S, closed at a
# typical S, and closed by the House's expiry rule at its $0.01 floor.
try:
    from league import structures as st
except Exception as exc:
    st = None
if st is not None and hasattr(st, "mleg_legs") and hasattr(broker, "_submit_structure"):
    O = lambda k, r, exp="2026-09-28", root_="SPY": opt(root_, exp, k, r)
    L = lambda inst, sign, ratio=1: st.Leg(inst, sign, ratio)
    cases = [
        ("debit_vertical", [L(O("580", "call"), 1), L(O("581", "call"), -1)], "0.55"),
        ("debit_vertical", [L(O("581", "put"), 1), L(O("580", "put"), -1)], "0.45"),
        ("credit_vertical", [L(O("590", "call"), -1), L(O("591", "call"), 1)], "0.62"),
        ("credit_vertical", [L(O("581", "put"), -1), L(O("580", "put"), 1)], "0.70"),
        ("iron_condor", [L(O("579", "put"), 1), L(O("580", "put"), -1), L(O("590", "call"), -1), L(O("591", "call"), 1)], "0.62"),
        ("iron_condor", [L(O("575", "put"), 1), L(O("580", "put"), -1), L(O("590", "call"), -1), L(O("591", "call"), 1)], "4.10"),
        ("iron_butterfly", [L(O("584", "put"), 1), L(O("585", "put"), -1), L(O("585", "call"), -1), L(O("587", "call"), 1)], "0.60"),
        ("long_butterfly", [L(O("580", "call"), 1), L(O("581", "call"), -1, 2), L(O("582", "call"), 1)], "0.20"),
        ("long_butterfly", [L(O("586", "put"), 1), L(O("584", "put"), -1, 2), L(O("582", "put"), 1)], "0.35"),
        ("calendar", [L(O("585", "call", "2026-09-28"), -1), L(O("585", "call", "2026-10-02"), 1)], "0.40"),
        ("diagonal", [L(O("586", "call", "2026-09-28"), -1), L(O("585", "call", "2026-10-02"), 1)], "0.90"),
        ("diagonal", [L(O("584", "put", "2026-09-28"), -1), L(O("585", "put", "2026-10-02"), 1)], "0.95"),
        ("long_straddle", [L(O("585", "call"), 1), L(O("585", "put"), 1)], "3.10"),
        ("long_strangle", [L(O("590", "call"), 1), L(O("580", "put"), 1)], "0.90"),
        ("debit_vertical", [L(O("12.5", "call", "2026-09-25", "F"), 1), L(O("13", "call", "2026-09-25", "F"), -1)], "0.20"),
    ]
    for type_, legs, s_open in cases:
        spec = st.classify(type_, legs)
        inst = st.instrument(spec, V)
        send(f"structure open {type_} S={s_open}", inst, "buy", "1", "limit", s_open, "day")
        send(f"structure open x3 {type_} S={s_open}", inst, "buy", "3", "limit", s_open, "day")
        send(f"structure close {type_} S={s_open}", inst, "sell", "1", "limit", s_open, "day", "exit")
        send(f"structure expiry close {type_} S=0.01", inst, "sell", "1", "limit", "0.01", "day", "exit")
        k = spec.collateral
        if k > 0:
            send(f"structure close {type_} S=K-0.01", inst, "sell", "1", "limit", str(k - Decimal("0.01")), "day", "exit")
            send(f"structure close {type_} S=K (bought back free)", inst, "sell", "1", "limit", str(k), "day", "exit")
for row in out:
    print(json.dumps(row))
