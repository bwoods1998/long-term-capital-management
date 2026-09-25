"""The options-desk run's structure hunks in `league/book.py` change nothing for a book with no structure.

Sept 25, 2026: the forward-first run lets the structure-only hunks land before its H4 on this condition. The
same scripted scenarios run on two `Book` classes over the same `FakeBroker`: today's `league.book`, and a
frozen copy of `league/book.py` as it stands on origin/main at 5ff775e (`fixtures/book_main_5ff775e.py`,
loaded as `league._book_before`, so its relative imports read the same league modules). Each scenario
records every return value that matters (outcomes, reconciliations, check reasons, marks, frozen flags,
counts, position keys) and every ledger row it wrote (sequence, id, kind, agent, time, payload); the two
transcripts must be identical. Only what is random by design is left out: a row appended without an id gets
a random `le-<uuid4>`, and the hash chain (each row's digest, a reconciliation's `ledger_digest`) follows it.

Scenarios: a real-money book reconciling clean at startup, a sub-cent cash drift booked as dust, cents that
freeze a real book, the freeze holding entries but not exits and clearing, a restart that must reconcile
again, and a restart over a standing mismatch; a practice book's sub-dollar dust at once and its adoption of
the venue after a dollar; a unit shortfall under a cent as dust and one of dollars as a freeze, on both;
a real Kalshi book's buy, freeze, restart and settlement; `check` on equity, crypto
and single options (expiring today, a market order, over the order and position caps, a short) and events;
`_quote` marks with zero and missing bids for single options and events; `expire_options` for an expired
long option the venue still shows and one it no longer shows; `position_key` for every asset class.
"""

import importlib.util
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Instrument

import league.book as book_now
from league.fees import Fees
from league.ledger import Ledger
from league.tests.fakes import Clock, FakeBroker, iso, without_real_entry_rules

D = Decimal
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "book_main_5ff775e.py"


def book_before():
    """origin/main's book.py at 5ff775e, as the module `league._book_before` (package `league`)."""
    name = "league._book_before"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, FIXTURE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module  # before exec: its dataclasses look their module up
        spec.loader.exec_module(module)
    return sys.modules[name]


def crypto(venue):
    return Instrument("crypto", "BTC-USD", venue, market_id="BTC/USD")


def equity(venue):
    return Instrument("equity", "SPY", venue)


def option(venue, expiry="2026-10-16", strike="650", right="call"):
    return Instrument("option", "SPY", venue, multiplier=100, expiry=expiry, strike=D(strike), right=right)


def event(venue, leg="yes", ticker="KXBTCD-26SEP2017-T80999"):
    return Instrument("event", ticker, venue, market_id=ticker, right=leg)


class Run:
    """One scenario on one Book class: its own ledger, clock and venue, and a transcript of what happened."""

    def __init__(self, module, root: Path, *, venue: str, family: str, real: bool, cash: str):
        self.m = module
        self.clock = Clock()
        self.ledger = Ledger(root / "ledger.sqlite", clock=self.clock)
        self.broker = FakeBroker(venue, cash=cash, family=family)
        self.venue, self.family, self.real = venue, family, real
        self.limits: dict[str, tuple] = {}
        self.book = self.new_book()
        self.n = 0
        self.log: list[tuple[str, object]] = []

    def new_book(self):
        book = self.m.Book(self.venue, self.broker, self.ledger, fees=Fees(self.family, option_clearing=not self.real),
                           real_money=self.real, clock=self.clock)
        for agent, (position, order, classes) in self.limits.items():
            book.limits[agent] = self.m.Limits(D(position), D(order), asset_classes=classes)
        return book

    def restart(self, label):
        self.book = self.new_book()
        self.note(label, self.book.frozen)

    def seat(self, agent, usd="200", position="100", order="75", classes=("equity", "crypto", "event", "option")):
        self.limits[agent] = (position, order, tuple(classes))
        self.book.limits[agent] = self.m.Limits(D(position), D(order), asset_classes=tuple(classes))
        if usd:
            self.book.stake(agent, usd)

    def intent(self, agent, instrument, side, quantity, **kw):
        self.n += 1
        return self.m.Intent.new(agent=agent, instrument=instrument, side=side, quantity=quantity,
                                 reason=f"test {self.n}", created_at=iso(self.clock), nonce=str(self.n), **kw)

    def note(self, label, value):
        self.log.append((label, value))

    def reconcile(self, label):
        r = self.book.reconcile()
        self.note(label, (r.ok, r.cash_venue, r.cash_ledger, r.cash_diff, dict(r.position_diffs), r.dust_booked, r.detail,
                          self.book.frozen))
        return r

    def submit(self, label, *intents):
        out = self.book.submit(list(intents))
        self.note(label, [(o.status, o.detail, o.order_id, o.filled) for o in out])
        return out

    def check(self, label, intent):
        self.note(label, self.book.check(intent, self.book._quote(intent.instrument), iso(self.clock)))

    def quote(self, label, instrument):
        quote = self.book._quote(instrument)
        self.note(label, (None if quote is None else quote.to_dict(), dict(self.book.marks)))

    def transcript(self):
        # A row appended without an id gets a random one (`le-<uuid4>`), and the hash chain -- each row's digest, and
        # the `ledger_digest` a reconciliation records -- follows the ids: those are the only parts not compared.
        rows = [(e.seq, "le-*" if e.id.startswith("le-") else e.id, e.kind, e.agent, e.at, e.public,
                 {k: v for k, v in e.payload.items() if k != "ledger_digest"}) for e in self.ledger.iter()]
        accounts = {name: (a.staked, a.cash, a.realized, a.fees, sorted(a.holdings)) for name, a in self.book.accounts.items()}
        return {"log": self.log, "rows": rows, "accounts": accounts, "frozen": self.book.frozen, "marks": dict(self.book.marks)}


def real_alpaca(run: Run) -> None:
    """A real-money book: startup reconciliation, dust, a freeze and its clearing, restarts."""
    btc = crypto(run.venue)
    run.note("startup frozen", run.book.frozen)
    run.reconcile("startup reconcile")
    run.seat("a1")
    run.broker.set_quote(btc, "80000", "80010")
    run.submit("buy", run.intent("a1", btc, "buy", "0.0005"))
    run.reconcile("after the buy")
    run.broker.cash -= D("0.004")
    run.reconcile("a sub-cent drift")
    run.reconcile("after the dust")
    run.broker.cash -= D("0.0322")
    run.reconcile("cents freeze a real book")
    run.submit("an entry while frozen", run.intent("a1", btc, "buy", "0.0001"))
    run.submit("an exit while frozen", run.intent("a1", btc, "sell", "0.0001"))
    for i in range(3):
        run.reconcile(f"still frozen {i}")
    run.restart("a restart over the mismatch")
    run.submit("an entry after the restart", run.intent("a1", btc, "buy", "0.0001"))
    run.reconcile("the mismatch stands")
    run.broker.cash += D("0.0322")
    run.reconcile("cleared")
    run.restart("a clean restart")
    run.submit("an entry before the startup reconcile", run.intent("a1", btc, "buy", "0.0001"))
    run.reconcile("the startup reconcile")
    run.submit("an entry after it", run.intent("a1", btc, "buy", "0.0001"))
    run.reconcile("clean")
    units(run, btc)


def practice_alpaca(run: Run) -> None:
    """A practice book: sub-dollar dust at once; a dollar freezes it until it adopts the venue."""
    btc = crypto(run.venue)
    run.reconcile("opens")
    run.seat("a1")
    run.broker.set_quote(btc, "80000", "80010")
    run.submit("buy", run.intent("a1", btc, "buy", "0.0005"))
    run.reconcile("after the buy")
    run.broker.cash -= D("0.0322")
    run.reconcile("cents are practice dust")
    run.broker.cash -= D("5")
    for i in range(4):
        run.reconcile(f"a five-dollar difference {i}")
    run.submit("an entry after the adoption", run.intent("a1", btc, "buy", "0.0001"))
    run.reconcile("clean")
    units(run, btc)


def units(run: Run, btc: Instrument) -> None:
    """A unit shortfall under a cent comes off the holder as dust; eight dollars of units freezes the book."""
    inst, held = run.broker.held[btc.key]
    run.broker.held[btc.key] = (inst, held - D("0.00000001"))
    run.reconcile("a sub-cent unit shortfall")
    run.broker.held[btc.key] = (inst, held - D("0.0001"))
    run.reconcile("eight dollars of units is not dust")
    run.broker.held[btc.key] = (inst, held - D("0.00000001"))
    run.reconcile("restored")


def real_kalshi(run: Run) -> None:
    """A real Kalshi book: a buy, a freeze, a restart that cannot clear it, the clearing, a settlement."""
    yes = event(run.venue)
    run.reconcile("startup")
    run.seat("a1", usd="100", position="50", order="50")
    run.broker.set_quote(yes, "0.50", "0.52")
    run.submit("buy", run.intent("a1", yes, "buy", "5"))
    run.reconcile("after the buy")
    run.broker.cash -= D(1)
    run.reconcile("a dollar missing")
    run.restart("restart")
    run.submit("refused", run.intent("a1", yes, "buy", "5"))
    run.reconcile("still missing")
    run.broker.cash += D(1)
    run.reconcile("cleared")
    run.note("settled", run.book.settle(yes.market_id, "yes"))
    run.broker.cash += D(5)
    run.broker.held.clear()
    run.reconcile("after the settlement")


def checks(run: Run) -> None:
    """`check` on equities, crypto, single options and events, and `_quote` marks with zero and missing bids."""
    run.reconcile("opens")
    run.seat("a1")
    spy, btc = equity(run.venue), crypto(run.venue)
    today = option(run.venue, expiry="2026-09-09")  # the Clock's New York date
    later = option(run.venue)
    run.broker.set_quote(spy, "500", "500.05")
    run.broker.set_quote(btc, "80000", "80010")
    run.broker.set_quote(today, "1.00", "1.05")
    run.broker.set_quote(later, "0.40", "0.45")
    run.check("equity within the caps", run.intent("a1", spy, "buy", "0.1"))
    run.check("equity over the order cap", run.intent("a1", spy, "buy", "1"))
    run.check("equity short", run.intent("a1", spy, "sell", "1"))
    run.check("crypto market buy", run.intent("a1", btc, "buy", "0.0005"))
    run.check("crypto over the position cap", run.intent("a1", btc, "buy", "0.002", order_type="limit", limit_price="80000"))
    run.check("an option expiring today", run.intent("a1", today, "buy", "1", order_type="limit", limit_price="1.05"))
    run.check("an option market order", run.intent("a1", later, "buy", "1"))
    run.check("an option limit within the caps", run.intent("a1", later, "buy", "1", order_type="limit", limit_price="0.45"))
    run.check("an option over the caps", run.intent("a1", later, "buy", "2", order_type="limit", limit_price="0.45"))
    run.check("an option short", run.intent("a1", later, "sell", "1", order_type="limit", limit_price="0.40"))
    run.quote("an option with a bid", later)
    run.broker.set_quote(later, "0", "0.05")
    run.quote("the option's bid gone to zero", later)
    run.broker.quotes.pop(later.key)
    run.quote("the option unquoted", later)
    run.quote("a crypto pair", btc)


def event_checks(run: Run) -> None:
    run.reconcile("opens")
    run.seat("a1", usd="100", position="50", order="50")
    yes, no = event(run.venue), event(run.venue, "no")
    run.broker.set_quote(yes, "0.50", "0.52")
    run.broker.set_quote(no, "0.48", "0.50")
    run.check("an event buy", run.intent("a1", yes, "buy", "5"))
    run.check("a longshot", run.intent("a1", no, "buy", "5", order_type="limit", limit_price="0.10"))
    run.check("fractional contracts", run.intent("a1", yes, "buy", "1.5"))
    run.quote("an event with a bid", yes)
    run.broker.set_quote(yes, "0", "0.02")
    run.quote("its bid gone to zero", yes)
    run.broker.quotes.pop(yes.key)
    run.quote("unquoted", yes)


def expiries(run: Run) -> None:
    """An expired long option the venue still shows is left alone; one it no longer shows is written off."""
    run.reconcile("opens")
    run.seat("a1")
    shown, gone = option(run.venue, expiry="2026-09-11", strike="640"), option(run.venue, expiry="2026-09-11", strike="660")
    run.broker.set_quote(shown, "0.30", "0.35")
    run.broker.set_quote(gone, "0.20", "0.25")
    run.submit("buy two", run.intent("a1", shown, "buy", "1", order_type="limit", limit_price="0.35"),
               run.intent("a1", gone, "buy", "1", order_type="limit", limit_price="0.25"))
    run.note("before the expiry", run.book.expire_options())
    run.clock.advance(3 * 86400)
    inst, _ = run.broker.held[gone.key]
    run.broker.held[gone.key] = (inst, D(0))
    run.note("expired", run.book.expire_options())
    run.note("again", run.book.expire_options())
    run.broker.held[shown.key] = (shown, D(0))
    run.note("the other cleared", run.book.expire_options())
    run.reconcile("after the write-offs")


def keys(module) -> list[str]:
    return [module.position_key(inst) for inst in (
        equity("alpaca"), crypto("alpaca"), Instrument("crypto", "BTCUSD", "alpaca"), option("alpaca"),
        option("alpaca-paper", strike="650.000"), option("alpaca", right="put"), event("kalshi"), event("kalshi", "no"),
        Instrument("event", "KXBTCD-26SEP2017-T80999", "kalshi-shadow", market_id="KXBTCD-26SEP2017-T80999"),
    )]


class Invariance(unittest.TestCase):
    def setUp(self):
        self._rules = without_real_entry_rules()
        self._rules.start()
        self.addCleanup(self._rules.stop)

    def both(self, scenario, **account):
        transcripts = []
        for module in (book_before(), book_now):
            with tempfile.TemporaryDirectory() as tmp:
                run = Run(module, Path(tmp), **account)
                try:
                    scenario(run)
                    transcripts.append(run.transcript())
                finally:
                    run.ledger.close()
        before, now = transcripts
        self.assertTrue(before["log"] and before["rows"], "the scenario did nothing")
        for part in ("log", "rows", "accounts", "frozen", "marks"):
            self.assertEqual(now[part], before[part], f"{scenario.__name__}: {part} differ")
        return before

    def test_the_pinned_copy_is_main_before_the_structure_hunks(self):
        before = book_before()
        self.assertIsNot(before.Book, book_now.Book)
        self.assertEqual(before.__package__, "league")
        self.assertFalse(hasattr(before, "_structure_entry_refusal"))

    def test_a_real_alpaca_book(self):
        log = dict(self.both(real_alpaca, venue="alpaca", family="alpaca", real=True, cash="1000")["log"])
        self.assertEqual(log["a sub-cent drift"][5], D("-0.004"))  # the scenario did book dust ...
        self.assertEqual(log["cents freeze a real book"][7], "cash differs by -0.0322")  # ... did freeze ...
        self.assertIsNone(log["cleared"][7])  # ... and did clear

    def test_a_practice_alpaca_book(self):
        self.both(practice_alpaca, venue="alpaca-paper", family="alpaca", real=False, cash="100000")

    def test_a_real_kalshi_book(self):
        self.both(real_kalshi, venue="kalshi", family="kalshi", real=True, cash="500")

    def test_checks_and_marks_on_equities_crypto_and_single_options(self):
        self.both(checks, venue="alpaca-paper", family="alpaca", real=False, cash="100000")
        self.both(checks, venue="alpaca", family="alpaca", real=True, cash="1000")

    def test_checks_and_marks_on_events(self):
        self.both(event_checks, venue="kalshi", family="kalshi", real=True, cash="500")
        self.both(event_checks, venue="kalshi-shadow", family="kalshi", real=False, cash="100000")

    def test_expire_options_for_single_long_options(self):
        self.both(expiries, venue="alpaca-paper", family="alpaca", real=False, cash="100000")
        self.both(expiries, venue="alpaca", family="alpaca", real=True, cash="1000")

    def test_position_keys(self):
        self.assertEqual(keys(book_now), keys(book_before()))


if __name__ == "__main__":
    unittest.main()
