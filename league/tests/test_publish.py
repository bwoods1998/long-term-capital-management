"""The publisher of the options swarm's public record (schema 2): allowlists only, quote-free words, the
Brokerage Account net of the owner's flows, and the page's inputs gathered from a House or its hook."""

import inspect
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from league import publish
from league.ledger import HOUSE, Ledger
from league.publish import (
    Flows, Publisher, SiteInputs, build_checkpoint, clean, clean_text, event_id, money, quote_free, scrub_quotes, to_events, words,
)
from league import structure_core as sc

D = Decimal
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PUBLISHED_AT = "2026-09-28T14:58:00.000Z"
RESET_AT = "2026-09-26T06:25:30.000Z"
T = 1790607480.0  # PUBLISHED_AT as epoch seconds

# The same sentences the site's test (personal-site test/capital.test.mjs) refuses and accepts.
QUOTED = ["bid 1.25 ask 1.30", "IV 18%", "implied vol at 22", "30 delta short strike", "the 10-delta put", "SPY at 571.23",
          "paid $120 for it", "a credit of 45¢", "the spread was 5 wide", "mid 2 on the call", "priced at 3", "theta of 4 a day", "vega 12",
          "NBBO 2 by 3", "marks 7 higher", "premium 3 per contract", "gamma: 2", "skew 4 points", "quoted 6 across"]
PLAIN = ["Opened 3 contracts of the XSP iron condor, 45 DTE.", "the 570 strike", "Sold the 0DTE put spread at the open.",
         "won 12 of 20 trades", "It closes at 15:30 ET on 2026-10-02.", "A gap of 2 days, then a 3-day slide.", "The ask is not the point here."]
# Every name a quote, a greek, a surface or a fitted parameter goes by: none is ever a key the publisher writes.
QUOTE_FIELDS = ["bid", "ask", "mid", "mark", "last", "spread", "iv", "implied_vol", "delta", "gamma", "theta", "vega", "greeks", "surface",
                "strike", "strikes", "price", "entry_price", "underlying_price", "params", "quote", "nbbo", "program", "code", "legs_detail"]
ALLOWED_KEYS = {
    "top": {"schema_version", "published_at", "run", "account", "performance", "compute", "gym", "agents", "structures"},
    "run": {"started_at"}, "account": {"equity", "cash", "as_of", "stale"}, "performance": {"start_at", "start_equity", "net_flows", "verified_at"},
    "compute": {"as_of", "sail_usd", "openai_usd", "thetadata_usd", "market_data_usd", "other_usd"},
    "gym": {"as_of", "trials", "market_years", "families_alive", "families_retired"},
    "agent": {"id", "family", "mechanism", "structure", "band", "born_at", "retired_at", "record"},
    "record": {"trials", "revisions", "forward", "real"}, "tally": {"trades", "wins", "pnl_usd"},
    "structure": {"id", "agent", "underlying", "structure", "legs", "expiry", "quantity", "real", "opened_at", "max_loss_usd", "pnl_usd"},
}


def keys_ok(test, body):
    """Every key in `body` is one the site's schema names for that block, and nothing else."""
    test.assertEqual(set(body) - {"trading"}, ALLOWED_KEYS["top"])
    if body.get("trading") is not None:
        test.assertEqual(set(body["trading"]), {"as_of", "pnl_usd"})
    for block in ("run", "account", "performance", "compute", "gym"):
        if body[block] is not None:
            test.assertEqual(set(body[block]), ALLOWED_KEYS[block], block)
    for agent in body["agents"]:
        test.assertEqual(set(agent) - {"progress"}, ALLOWED_KEYS["agent"])
        if agent.get("progress") is not None:
            from league.swarm.progress import clean as clean_progress

            test.assertEqual(agent["progress"], clean_progress(agent["progress"]))
        test.assertEqual(set(agent["record"]), ALLOWED_KEYS["record"])
        for side in ("forward", "real"):
            if agent["record"][side] is not None:
                test.assertEqual(set(agent["record"][side]), ALLOWED_KEYS["tally"])
    for row in body["structures"]:
        test.assertEqual(set(row), ALLOWED_KEYS["structure"])


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


# ----------------------------------------------------------------------------- the fixture
def tally(trades, wins, pnl):
    return {"trades": trades, "wins": wins, "pnl_usd": pnl}


def agent(agent_id, **overrides):
    row = {"id": agent_id, "family": agent_id.rsplit("-", 1)[0] if agent_id[-1].isdigit() else agent_id,
           "mechanism": "Sells short-dated index premium when realized volatility runs under the level the options price in.",
           "structure": "iron_condor", "band": "gym", "born_at": "2026-09-26T16:02:11.000Z", "retired_at": None,
           "trials": 1204, "revisions": 17, "forward": None, "real": None}
    row.update(overrides)
    return row


FIXTURE_AGENTS = [
    agent("condor-vrp-3", band="sized", born_at="2026-09-26T09:14:00.000Z", trials=5812, revisions=41, forward=tally(64, 45, "1284.20"), real=tally(22, 16, "212.40")),
    agent("putspread-dip-2", band="probe", structure="debit_vertical", born_at="2026-09-26T09:20:00.000Z", trials=3390, revisions=28,
          mechanism="Buys a put debit vertical after a gap down that the first hour does not recover, and exits before the close.",
          forward=tally(31, 18, "402.75"), real=tally(4, 2, "-18.30")),
    agent("orb-4", band="probe", structure="debit_vertical", born_at="2026-09-26T10:02:00.000Z", trials=2877, revisions=22,
          mechanism="Trades the break of the opening range in the direction of the break, with a vertical sized by its maximum loss.",
          forward=tally(40, 23, "310.10"), real=tally(3, 2, "21.80")),
    agent("ironfly-quiet", band="candidate", structure="iron_butterfly", trials=2410, revisions=19, forward=tally(18, 11, "96.40"),
          mechanism="Sells an at-the-money iron butterfly on quiet mornings when the overnight range was narrow."),
    agent("butterfly-pin", band="candidate", structure="long_butterfly", trials=1988, revisions=15, forward=tally(9, 4, "-22.00"),
          mechanism="Buys a long butterfly around the strike with the largest open interest on expiry afternoons, where prices tend to pin."),
    agent("trend-vertical", band="candidate", structure="debit_vertical", trials=1760, revisions=13, forward=tally(12, 7, "58.90"),
          mechanism="Rides trend days: once the first two hours close far from the open, it buys a vertical in that direction."),
    agent("gap-drift", structure="long_call", mechanism="Fades opening gaps that the premarket did not confirm, with a single long option."),
    agent("skew-revert", structure="credit_vertical", trials=940, revisions=9,
          mechanism="Sells the side of the smile that has steepened most against its own recent history."),
    agent("calendar-term", structure="calendar", trials=611, revisions=7,
          mechanism="Buys a calendar when near-dated options are rich against the month behind them."),
    agent("strangle-cheap", structure="long_strangle", trials=402, revisions=4,
          mechanism="Buys a strangle into scheduled news when the move the options expect is small beside past moves."),
    agent("eod-drift", structure="long_call", trials=88, revisions=1,
          mechanism="Buys the last hour's drift into the close on days the index is up from the open."),
    agent("reversal-1", band="retired", structure="debit_vertical", retired_at="2026-09-27T21:40:00.000Z", trials=2000, revisions=30,
          mechanism="Bought reversals after three down days; it never beat the fill cost on validation."),
]


def structure(structure_id, **overrides):
    row = {"id": structure_id, "agent": "condor-vrp-3", "underlying": "XSP", "structure": "iron_condor", "legs": 4, "expiry": "2026-09-28",
           "quantity": 1, "real": True, "opened_at": "2026-09-28T14:02:40.000Z", "max_loss_usd": "184.00", "pnl_usd": "12.50"}
    row.update(overrides)
    return row


FIXTURE_STRUCTURES = [
    structure("st-condor-vrp-3-0928a"),
    structure("st-orb-4-0928a", agent="orb-4", underlying="SPY", structure="debit_vertical", legs=2, quantity=2, max_loss_usd="96.00", pnl_usd="-8.00"),
    structure("st-putspread-dip-2-0928a", agent="putspread-dip-2", underlying="QQQ", structure="debit_vertical", legs=2, expiry="2026-09-30",
              max_loss_usd="61.00", pnl_usd=None),
    structure("st-ironfly-quiet-0928a", agent="ironfly-quiet", underlying="SPY", structure="iron_butterfly", real=False, max_loss_usd="312.00", pnl_usd="41.00"),
]
FIXTURE_INPUTS = SiteInputs(
    started_at="2026-09-26T07:02:18.000Z",
    account={"equity": "5694.37", "cash": "5210.12", "as_of": "2026-09-28T14:57:58.000Z", "stale": False},
    performance={"start_at": RESET_AT, "start_equity": "481.65", "net_flows": "5000", "verified_at": "2026-09-28T14:55:02.000Z"},
    compute={"as_of": "2026-09-28T14:57:00.000Z", "sail_usd": "212.40", "openai_usd": "64.10", "thetadata_usd": "5.43", "market_data_usd": "5.66", "other_usd": "0"},
    gym={"as_of": "2026-09-28T14:50:00.000Z", "trials": 48213, "market_years": "51240.5", "families_alive": 11, "families_retired": 37},
    agents=FIXTURE_AGENTS, structures=FIXTURE_STRUCTURES,
)


def condor(expiry="2026-09-28", root="XSP"):
    return sc.classify("iron_condor", [sc.leg(sc.occ_code(root, expiry, "put", 560), 1), sc.leg(sc.occ_code(root, expiry, "put", 565), -1),
                                       sc.leg(sc.occ_code(root, expiry, "call", 580), -1), sc.leg(sc.occ_code(root, expiry, "call", 585), 1)])


def vertical(root="SPY", expiry="2026-09-28"):
    return sc.classify("debit_vertical", [sc.leg(sc.occ_code(root, expiry, "call", 570), 1), sc.leg(sc.occ_code(root, expiry, "call", 575), -1)])


def fill(spec, *, side="buy", quantity="1", price="1.84", realized=None, real=True, source="venue", reason="the condor fits the quiet tape"):
    return {"book": "options", "source": source, "side": side, "quantity": quantity, "price": price, "real_money": real, "realized": realized,
            "reason": reason, "entry_reason": "the condor fits the quiet tape" if side == "sell" else None, "fee_usd": "0.26",
            "instrument": {"asset_class": "option", "symbol": spec.underlying, "venue": "alpaca", "multiplier": "100", "expiry": spec.expiry,
                           "market_id": spec.code, "right": None, "strike": None}}


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="w6-publish-")
        self.clock = SimpleNamespace(now=T)
        self.ledger = Ledger(Path(self.dir) / "ledger.sqlite", clock=lambda: self.clock.now)

    def tearDown(self):
        self.ledger._db.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def row(self, kind, payload, agent="condor-vrp-3", at="2026-09-28T14:02:40.000Z", public=None):
        self.rows = getattr(self, "rows", 0) + 1  # ids fixed, so the tape fixture is the same on every run
        return self.ledger.append(kind, payload, agent=agent, at=at, public=public, id=f"le-{self.rows:04d}-{kind}")

    def tape(self):
        """The fixture's tape, written as the House writes its ledger."""
        rows = [
            self.row("floor.mark", {"brokerage_equity": "481.6500", "brokerage_cash": "481.6200", "as_of": "2026-09-26T06:30:00.000Z"}, agent=HOUSE,
                     at="2026-09-26T06:30:00.000Z"),
            self.row("agent.born", {"parent": None, "mechanism": "Sells short-dated index premium when realized volatility is low."}, agent="condor-vrp-3",
                     at="2026-09-26T09:14:00.000Z"),
            self.row("eval.verdict", {"decision": "promote", "band_from": "probe", "band_to": "sized", "reason": "its forward record held over 64 trades"},
                     at="2026-09-28T12:05:00.000Z"),
            self.row("book.fill", fill(condor())),
            self.row("book.fill", fill(vertical(), quantity="2", price="0.48", reason="The open broke higher on heavy volume."), agent="orb-4",
                     at="2026-09-28T14:10:00.000Z"),
            self.row("book.fill", fill(vertical(), side="sell", quantity="2", price="0.63", realized="31.0000"), agent="orb-4", at="2026-09-28T14:30:00.000Z"),
            self.row("agent.thought", {"text": "The gap down held through the first hour, so I bought the put vertical two weeks out; the bid was 1.12."},
                     agent="putspread-dip-2", at="2026-09-28T14:35:00.000Z"),
            self.row("agent.thought", {"text": "Realized volatility since the open runs under half of what the options expect. Holding the condor."},
                     at="2026-09-28T14:52:00.000Z"),
            self.row("floor.mark", {"brokerage_equity": "5694.3700", "brokerage_cash": "5210.1200", "as_of": "2026-09-28T14:55:00.000Z"}, agent=HOUSE,
                     at="2026-09-28T14:55:00.000Z"),
        ]
        return [event for entry in rows for event in to_events(entry)]


# ---------------------------------------------------------------------------- cleaning
class CleaningTest(unittest.TestCase):
    def test_text_the_site_would_refuse_is_made_safe(self):
        self.assertEqual(clean_text("see https://www.reuters.com/x and https://www.sec.gov/y"), "see [link removed] and https://www.sec.gov/y")
        self.assertEqual(clean_text("fees at https://kalshi.com/fees"), "fees at [link removed]", "no venue is a source")
        self.assertNotIn("<", clean_text("<script>"))
        self.assertNotIn("sk-", clean_text("key sk-abc123"))
        self.assertEqual(clean_text("the data:5 rows"), "the data: 5 rows")
        self.assertEqual(clean({"ok": 1, "_code": "x", "BTC/USD": 2, "nested": {"_p": 1, "q": "<"}}), {"ok": 1, "nested": {"q": "‹"}})

    def test_limits_count_as_the_site_counts(self):
        self.assertEqual(publish.js_length("📉"), 2)
        cut = clean_text("📉" * 400, 300)
        self.assertEqual((len(cut), publish.js_length(cut)), (150, 300))
        self.assertEqual(publish.js_length(words("🚀" * 400, 300)), 300)

    def test_money_is_plain_digits(self):
        self.assertEqual(money(D("1E+2")), "100.00")
        self.assertEqual(money(D("-0.004"), 2, signed=True), "0.00")
        self.assertEqual(money(D("-1.239"), 2, signed=True), "-1.24")
        self.assertEqual(event_id("fill:options:a1:SPY/QQQ"), "fill:options:a1:SPY_QQQ")


# ---------------------------------------------------------------------------- the licence
class QuoteFreeTest(unittest.TestCase):
    def test_every_quote_in_prose_is_masked_and_plain_words_are_left_alone(self):
        for text in QUOTED:
            self.assertFalse(quote_free(text), text)
            scrubbed = scrub_quotes(text)
            self.assertTrue(quote_free(scrubbed), f"{text!r} -> {scrubbed!r}")
            self.assertLessEqual(publish.js_length(scrubbed), publish.js_length(text), "a mask never lengthens a sentence")
        for text in PLAIN:
            self.assertTrue(quote_free(text), text)
            self.assertEqual(scrub_quotes(text), text)
        self.assertEqual(scrub_quotes("bid 1.25 ask 1.30, 30 delta, IV 18%"), "bid … ask …, … delta, IV …")
        self.assertEqual(scrub_quotes("paid $1,250.50, then 3 contracts"), "paid $…, then 3 contracts")
        # JavaScript's \s is the Unicode space set: a no-break space before "delta" still reads as a quote there.
        self.assertFalse(quote_free("30\u00a0delta"))
        self.assertTrue(quote_free(scrub_quotes("30\u00a0delta")))

    def test_a_cut_is_made_before_the_mask_so_it_can_never_make_a_quote(self):
        text = "sold 30 deltaforce wings"
        self.assertTrue(quote_free(text), "no word boundary: not a quote word")
        cut = words(text, 16)  # "sold 30 deltafor" would be fine; cut at 13 ends on "delta"
        self.assertTrue(quote_free(cut))
        self.assertTrue(quote_free(words(text, 13)), words(text, 13))

    def test_the_account_is_the_brokerage_account_and_a_venue_is_never_named(self):
        self.assertEqual(words("Alpaca refused the order; KALSHI and Coinbase are gone.", 200), "the broker refused the order; the broker and the broker are gone.")

    def test_random_sentences_scrubbed_here_pass_the_sites_own_rule(self):
        """The site's `quoteFree` itself, run by node on the scrubbed output, when a site checkout is at hand."""
        schema = Path(os.environ.get("SITE_SCHEMA") or Path(__file__).resolve().parents[3] / "personal-site" / "capital" / "schema.js")
        node = shutil.which("node")
        if node is None or not schema.exists() or "quoteFree" not in schema.read_text(encoding="utf-8"):
            self.skipTest(f"no node, or no schema-2 site at {schema} (set SITE_SCHEMA to capital/schema.js)")
        rng = random.Random(20260926)
        vocab = list(publish.QUOTE_WORDS) + ["the", "SPY", "strike", "contracts", "DTE", "open", "0DTE", "Alpaca", "\u00a0", "-", ";", ".", "%", "$", "¢", "\n"]
        samples = []
        for _ in range(3000):
            parts = []
            for _ in range(rng.randint(1, 12)):
                pick = rng.random()
                parts.append(str(rng.randint(0, 999)) if pick < 0.3 else f"{rng.randint(0, 99)}.{rng.randint(0, 99)}" if pick < 0.4
                             else rng.choice(vocab).rstrip("?s") if pick < 0.7 else rng.choice(vocab))
            samples.append(words(rng.choice(["", " ", "-"]).join(parts), 240))
        script = ("import('" + schema.resolve().as_uri() + "').then(s => { let data = ''; process.stdin.on('data', c => data += c); process.stdin.on('end', () => {"
                  " const bad = JSON.parse(data).filter(t => !(s.quoteFree(t) && !s.VENUE_NAMES.test(t))); console.log(JSON.stringify(bad)); }); });")
        result = subprocess.run([node, "-e", script], input=json.dumps(samples), capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])


# ---------------------------------------------------------------------------- the checkpoint
class BuildTest(unittest.TestCase):
    def test_the_first_minutes_of_a_new_house_publish_every_block_empty(self):
        body = build_checkpoint(SiteInputs(started_at="2026-09-26T07:02:18Z"), "2026-09-26T07:03:00.000Z")
        self.assertEqual(body, {"schema_version": 2, "published_at": "2026-09-26T07:03:00.000Z", "run": {"started_at": "2026-09-26T07:02:18.000Z"},
                                "account": None, "performance": None, "compute": None, "gym": None, "agents": [], "structures": []})
        self.assertEqual(build_checkpoint({}, PUBLISHED_AT)["run"], {"started_at": None})

    def test_explicit_inputs_become_exactly_the_sites_fields(self):
        body = build_checkpoint(FIXTURE_INPUTS, PUBLISHED_AT)
        keys_ok(self, body)
        self.assertEqual(body["account"], {"equity": "5694.37", "cash": "5210.12", "as_of": "2026-09-28T14:57:58.000Z", "stale": False})
        self.assertEqual(body["performance"]["net_flows"], "5000.00")
        self.assertEqual(body["compute"]["other_usd"], "0.00")
        self.assertEqual(body["gym"]["market_years"], "51240.5")
        self.assertEqual([a["band"] for a in body["agents"]], ["sized", "probe", "probe", "candidate", "candidate", "candidate", "gym", "gym", "gym", "gym", "gym", "retired"])
        condor_row = body["agents"][0]
        self.assertEqual((condor_row["id"], condor_row["record"]["real"]), ("condor-vrp-3", {"trades": 22, "wins": 16, "pnl_usd": "212.40"}))
        self.assertEqual([s["real"] for s in body["structures"]], [True, True, True, False], "real money first, then the shadow book")
        self.assertEqual(body["structures"][2]["pnl_usd"], None)

    def test_quotes_greeks_surfaces_and_parameters_never_leave_whatever_the_inputs_carry(self):
        smuggle = {field: "1.25" for field in QUOTE_FIELDS}
        quoted = " ".join(QUOTED)
        inputs = SiteInputs(
            started_at=PUBLISHED_AT,
            account={"equity": "100", "cash": "100", "as_of": PUBLISHED_AT, "stale": False, **smuggle},
            performance={"start_at": RESET_AT, "start_equity": "100", "net_flows": "0", "verified_at": PUBLISHED_AT, **smuggle},
            compute={"sail_usd": "1", **smuggle}, gym={"trials": 5, **smuggle},
            agents=[agent("condor-vrp-3", name=quoted, mechanism=quoted, **smuggle, record={"trials": 3, "revisions": 1, **smuggle,
                                                                                            "forward": {**tally(1, 1, "2"), **smuggle}, "real": None})],
            structures=[structure("s1", **smuggle)],
        )
        body = build_checkpoint(inputs, PUBLISHED_AT)
        keys_ok(self, body)
        self.assertEqual(len(body["agents"]), 1)
        self.assertEqual(len(body["structures"]), 1)
        text = json.dumps(body)
        for field in QUOTE_FIELDS:
            self.assertNotIn(f'"{field}"', text, field)
        for value in strings(body):
            if not re.match(r"^\d{4}-\d\d-\d\d(?:T[\d:.]+Z)?$|^-?\d+(?:\.\d+)?$", value):  # times and amounts are typed fields, not words
                self.assertTrue(quote_free(value), value)
        self.assertNotIn("1.25", body["agents"][0]["mechanism"])

    def test_rows_the_site_would_refuse_are_left_out_and_the_roster_is_bounded(self):
        rows = [agent(f"agent-{n}") for n in range(150)] + [agent(f"dead-{n}", band="retired", retired_at=f"2026-09-27T{n % 24:02d}:00:00.000Z") for n in range(50)]
        rows += [agent("Bad-Case"), agent("paper-1", band="paper"), agent("x" * 41)]
        body = build_checkpoint(SiteInputs(agents=rows), PUBLISHED_AT)
        self.assertEqual(len(body["agents"]), 160)
        self.assertEqual(sum(a["band"] == "retired" for a in body["agents"]), 10, "the living first; the newest dead fill what is left")
        many = [structure(f"s{n}", real=n % 2 == 0, max_loss_usd=str(n)) for n in range(120)]
        many += [structure("no-loss", max_loss_usd=None), structure("five-legs", legs=5), structure("naked", structure="short_put"), structure("s1")]
        shown = build_checkpoint(SiteInputs(structures=many), PUBLISHED_AT)["structures"]
        self.assertEqual(len(shown), 100)
        self.assertTrue(all(s["real"] for s in shown[:60]))
        self.assertEqual(shown[0]["max_loss_usd"], "118.00")
        self.assertEqual(build_checkpoint(SiteInputs(structures=[structure("late", opened_at=None)]), PUBLISHED_AT)["structures"][0]["opened_at"], PUBLISHED_AT)

    def test_the_profit_basis_travels_whole_or_not_at_all(self):
        basis = {"start_at": RESET_AT, "start_equity": "481.65", "net_flows": "5000", "verified_at": None}
        self.assertEqual(build_checkpoint(SiteInputs(performance=basis), PUBLISHED_AT)["performance"],
                         {"start_at": RESET_AT, "start_equity": "481.65", "net_flows": None, "verified_at": None})
        early = {**basis, "verified_at": "2026-09-20T00:00:00.000Z"}
        self.assertIsNone(build_checkpoint(SiteInputs(performance=early), PUBLISHED_AT)["performance"]["net_flows"])
        self.assertIsNone(build_checkpoint(SiteInputs(performance={**basis, "start_equity": "0"}), PUBLISHED_AT)["performance"])
        self.assertIsNone(build_checkpoint(SiteInputs(performance={**basis, "start_at": "2026-09-29T00:00:00.000Z"}), PUBLISHED_AT)["performance"])
        late = {"equity": "1", "cash": "1", "as_of": "2026-09-28T15:30:00.000Z", "stale": False}
        self.assertIsNone(build_checkpoint(SiteInputs(account=late), PUBLISHED_AT)["account"], "a reading after the stamp is refused by the site")

    def test_the_fixture_is_this_modules_own_output(self):
        """`site_checkpoint.json` is `build_checkpoint(FIXTURE_INPUTS)`: the site's contract test publishes and draws it.
        LTCM_WRITE_SITE_FIXTURES=1 rewrites both fixtures from here."""
        body = build_checkpoint(FIXTURE_INPUTS, PUBLISHED_AT)
        path = FIXTURES / "site_checkpoint.json"
        if os.environ.get("LTCM_WRITE_SITE_FIXTURES"):
            path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), body)


# ---------------------------------------------------------------------------- the tape
class EventsTest(LedgerCase):
    def test_the_tape_is_notes_trades_news_and_marks_on_their_own_streams(self):
        events = self.tape()
        self.assertEqual([(e["kind"], e["stream"]) for e in events], [
            ("account.mark", "account"), ("swarm.news", "swarm"), ("swarm.news", "swarm"), ("agent.trade", "agent:condor-vrp-3"),
            ("agent.trade", "agent:orb-4"), ("agent.trade", "agent:orb-4"), ("agent.note", "agent:putspread-dip-2"), ("agent.note", "agent:condor-vrp-3"),
            ("account.mark", "account"),
        ])
        for event in events:
            self.assertEqual(set(event), {"id", "stream", "kind", "at", "payload", "digest"})
            self.assertRegex(event["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
            self.assertRegex(event["digest"], r"^[a-f0-9]{64}$")
            self.assertEqual(event["kind"].split(".")[0], event["stream"].split(":")[0])
            for value in strings(event["payload"]):
                self.assertTrue(quote_free(value) or value[:1].isdigit(), value)
        self.assertEqual(events[0]["payload"], {"equity": "481.65", "cash": "481.62", "as_of": "2026-09-26T06:30:00.000Z"})
        self.assertEqual(events[2]["payload"], {"agent": "condor-vrp-3", "text": "moves from Probe to Sized: its forward record held over 64 trades."})
        self.assertEqual(events[1]["payload"]["agent"], "condor-vrp-3", "a birth names its agent in the field, not the sentence")
        self.assertEqual(events[3]["payload"], {"action": "open", "real": True, "underlying": "XSP", "structure": "iron_condor", "legs": 4, "expiry": "2026-09-28",
                                                "quantity": 1, "max_loss_usd": "184.00", "pnl_usd": None, "why": "the condor fits the quiet tape"})
        self.assertEqual((events[5]["payload"]["action"], events[5]["payload"]["pnl_usd"], events[5]["payload"]["max_loss_usd"]), ("close", "31.00", None))
        self.assertTrue(events[6]["payload"]["text"].endswith("the bid was …."), "an agent's own quote is masked")

    def test_what_never_reaches_the_tape(self):
        btc = {"book": "alpaca", "source": "venue", "side": "buy", "quantity": "0.001", "price": "80000", "real_money": True,
               "instrument": {"asset_class": "crypto", "symbol": "BTC/USD", "venue": "alpaca", "market_id": "BTC/USD"}}
        rows = [
            self.row("book.fill", btc),
            self.row("book.fill", fill(condor(), source="dust")),
            self.row("book.fill", fill(condor(), source="structure-break")),
            self.row("book.fill", fill(condor()), agent=HOUSE),
            self.row("agent.thought", {"text": "  "}),
            self.row("agent.thought", {"text": "private"}, public=False),
            self.row("floor.mark", {"account_equity": "1021.92", "real_account_equity": "1021.92", "account_cash": "1", "venues": [], "as_of": PUBLISHED_AT}, agent=HOUSE),
            self.row("eval.verdict", {"decision": "promote", "band_from": "paper", "band_to": "bunt", "reason": "the old ladder"}),
            self.row("ops.alert", {"level": "error", "text": "the Kalshi book is frozen"}, agent=HOUSE),
            self.row("credit.charge", {"usd": "0.01", "what": "tokens"}),
        ]
        self.assertEqual([to_events(row) for row in rows], [[]] * len(rows))

    def test_a_settlement_at_expiry_closes_a_structure(self):
        settle = {**fill(vertical()), "pnl": "-48.0000", "result": "expired"}
        event = to_events(self.row("book.settle", settle, agent="orb-4"))[0]
        self.assertEqual((event["kind"], event["payload"]["action"], event["payload"]["pnl_usd"]), ("agent.trade", "close", "-48.00"))

    def test_the_updaters_news_still_reads_as_a_wait(self):
        news = publish.league_news("ops.deploy", "house", {"action": "held", "sha": "a" * 40, "reasons": ["next eligible 2026-09-24T20:05:00Z"]})
        self.assertIn("waits for the release train", news)


# ---------------------------------------------------------------------------- the publisher
class Response:
    def __init__(self, body):
        self.status, self._body = 200, json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Site:
    def __init__(self):
        self.posts = []

    def __call__(self, request, timeout=None):
        body = json.loads(request.data)
        self.posts.append((request.full_url, body))
        return Response({"stored": len(body.get("events") or []), "replayed": 0})


class Broker:
    def __init__(self, equity="481.65", cash="481.62"):
        self.equity, self.cash, self.fail = D(equity), D(cash), False

    def balance(self):
        if self.fail:
            raise OSError("the broker did not answer")
        return SimpleNamespace(equity=self.equity, cash=self.cash)


class FakeHouse:
    """What the publisher reads of a House: its ledger, roster, rungs and books."""

    def __init__(self, ledger, agents=(), books=None, rungs=None):
        self.ledger = ledger
        self.registry = SimpleNamespace(living=lambda: [a for a in agents if a.alive], dead=lambda: [a for a in agents if not a.alive])
        self.evaluator = SimpleNamespace(rung=lambda agent_id: (rungs or {}).get(agent_id, 0))
        self.books = books or {}


def roster_agent(agent_id, alive=True, family="condor-vrp"):
    return SimpleNamespace(id=agent_id, family=family, alive=alive, born_at="2026-09-26T09:14:00.000Z", died_at=None if alive else "2026-09-27T21:40:00.000Z")


class PublisherTest(LedgerCase):
    def publisher(self, site=None, broker=None, **performance):
        performance = performance or {"start_at": RESET_AT, "start_equity": "481.65"}
        publisher = Publisher("https://blakewoods.us", lambda: "t" * 40, Path(self.dir) / "publish.json", tape="test", opener=site or Site(),
                              clock=lambda: self.clock.now, performance=performance, real_brokers={"alpaca": broker or Broker()})
        return publisher

    def test_the_houses_calls_keep_their_signatures(self):
        params = list(inspect.signature(Publisher.__init__).parameters)
        self.assertEqual(params, ["self", "site_url", "token_source", "state_path", "tape", "performance", "real_brokers", "opener", "clock",
                                  "gateway_url", "gateway_token"])
        self.assertEqual(list(inspect.signature(Publisher.publish).parameters), ["self", "house"])
        self.assertEqual(list(inspect.signature(Publisher.checkpoint).parameters), ["self", "house"])

    def test_a_publish_sends_the_tape_then_the_checkpoint_in_schema_2(self):
        self.tape()
        self.row("ops.started", {}, agent=HOUSE, at="2026-09-26T07:02:18.000Z")
        site = Site()
        publisher = self.publisher(site)
        house = FakeHouse(self.ledger, [roster_agent("condor-vrp-3"), roster_agent("orb-4", family="orb")])
        result = publisher.publish(house)
        urls = [url for url, _ in site.posts]
        self.assertTrue(all(url.startswith("https://blakewoods.us/api/capital/t/test/") for url in urls))
        self.assertEqual(urls[-1], "https://blakewoods.us/api/capital/t/test/checkpoint")
        batches = [body for url, body in site.posts if url.endswith("/events")]
        self.assertTrue(all(body["schema_version"] == 2 for body in batches))
        kinds = [e["kind"] for body in batches for e in body["events"]]
        self.assertEqual(kinds.count("account.mark"), 3, "two on the tape, and the mark this publish wrote")
        self.assertEqual(result["events"], len(kinds))
        checkpoint = site.posts[-1][1]
        keys_ok(self, checkpoint)
        self.assertEqual(checkpoint["run"], {"started_at": "2026-09-26T07:02:18.000Z"})
        self.assertEqual(checkpoint["account"]["equity"], "481.65")
        self.assertEqual([a["id"] for a in checkpoint["agents"]], ["condor-vrp-3", "orb-4"])
        orb = checkpoint["agents"][1]
        self.assertEqual(orb["record"]["real"], {"trades": 1, "wins": 1, "pnl_usd": "31.00"}, "its closed real trade, folded from the ledger")
        self.assertEqual(checkpoint["agents"][0]["mechanism"], "Sells short-dated index premium when realized volatility is low.")
        # A second publish sends only what is new, and writes no second mark inside five minutes.
        site.posts.clear()
        self.clock.now += 60
        self.assertEqual(publisher.publish(house)["events"], 0)
        self.assertEqual(json.loads((Path(self.dir) / "publish.json").read_text())["cursor"], self.ledger.read(newest=True, limit=1)[0].seq)

    def test_the_account_goes_stale_rather_than_missing_and_profit_waits_for_a_verified_funding_check(self):
        broker = Broker("5694.37", "5210.12")
        publisher = self.publisher(broker=broker)
        publisher.flows = Flows(broker, RESET_AT, clock=lambda: self.clock.now, reader=lambda: D("5000"), threaded=False)
        house = FakeHouse(self.ledger)
        body = publisher.checkpoint(house)
        self.assertEqual((body["account"]["stale"], body["performance"]["net_flows"]), (False, "5000.00"))
        self.assertEqual(body["performance"]["verified_at"], body["published_at"])
        broker.fail = True
        self.clock.now += 30
        body = publisher.checkpoint(house)
        self.assertEqual((body["account"]["equity"], body["account"]["stale"]), ("5694.37", True))
        self.clock.now += 700  # the funding check is now older than ten minutes, and its refresh fails
        publisher.flows.reader = lambda: (_ for _ in ()).throw(ValueError("Unclassified account activity"))
        self.assertEqual(publisher.checkpoint(house)["performance"]["net_flows"], None)
        fresh = self.publisher(broker=Broker())
        fresh.broker.fail = True
        self.assertIsNone(fresh.checkpoint(house)["account"], "never read: no balance at all")

    def test_compute_is_the_sail_meter_the_subscriptions_since_the_reset_and_the_houses_openai(self):
        self.row("ops.budget", {"what": "sail", "spent_usd": "12.40"}, agent=HOUSE)
        self.row("ops.budget", {"what": "sail", "spent_usd": "0.60"}, agent=HOUSE)
        publisher = self.publisher()
        house = FakeHouse(self.ledger)
        compute = publisher.checkpoint(house)["compute"]
        days = (T - 1790403930.0) / 86400  # from the reset
        self.assertEqual(compute["sail_usd"], "13.00")
        self.assertEqual(compute["openai_usd"], None, "not metered until the House says")
        self.assertAlmostEqual(float(compute["thetadata_usd"]), 80 * days / (365.25 / 12), places=2)
        self.assertAlmostEqual(float(compute["market_data_usd"]), 1000 / 12 * days / (365.25 / 12), places=2)
        self.assertEqual(compute["other_usd"], "0.00")
        house.site_inputs = lambda: {"compute": {"openai_usd": "64.10", "bid": "1.25"}, "gym": {"trials": 9, "market_years": "1.2", "families_alive": 3, "families_retired": 0}}
        body = publisher.checkpoint(house)
        self.assertEqual((body["compute"]["openai_usd"], body["compute"]["sail_usd"]), ("64.10", "13.00"))
        self.assertNotIn("bid", body["compute"])
        self.assertEqual(body["gym"]["trials"], 9)

    def test_the_hook_feeds_the_swarm_and_the_book_and_a_broken_hook_costs_nothing(self):
        house = FakeHouse(self.ledger, [roster_agent("condor-vrp-3")], rungs={"condor-vrp-3": 1})
        publisher = self.publisher()
        self.assertEqual(publisher.checkpoint(house)["agents"][0]["band"], "candidate", "before the swarm names bands: a rung of 1 is shadow only")
        house.site_inputs = lambda: {"agents": FIXTURE_AGENTS, "structures": FIXTURE_STRUCTURES}
        body = publisher.checkpoint(house)
        self.assertEqual(len(body["agents"]), 12)
        self.assertEqual(len(body["structures"]), 4)
        house.site_inputs = lambda: 1 / 0
        self.assertEqual([a["id"] for a in publisher.checkpoint(house)["agents"]], ["condor-vrp-3"])

    def test_missing_options_book_after_a_real_fill_is_not_reported_as_zero_profit(self):
        publisher = self.publisher()
        house = FakeHouse(self.ledger)
        self.assertEqual(publisher.checkpoint(house)["trading"]["pnl_usd"], "0.00")
        self.row("book.fill", fill(vertical()))
        self.assertIsNone(publisher.checkpoint(house)["trading"]["pnl_usd"])

    def test_open_structures_come_from_the_books_as_what_they_are_never_what_they_are_quoted_at(self):
        spec = condor()
        instrument = SimpleNamespace(market_id=spec.code, key="k1", asset_class="option", symbol="XSP", right=None, expiry=spec.expiry, multiplier=D(100))
        holding = SimpleNamespace(instrument=instrument, quantity=D(1), cost=D("184"), opened_at="2026-09-28T14:02:40.000Z", average_cost=D("1.84"))
        coin = SimpleNamespace(instrument=SimpleNamespace(market_id="BTC/USD", key="k2", asset_class="crypto", symbol="BTC/USD", right=None, expiry=None,
                                                          multiplier=D(1)), quantity=D(1), cost=D(5), opened_at=None)
        book = SimpleNamespace(real_money=True, marks={"k1": D("1.965"), "k2": D(80000)},
                               accounts={"condor-vrp-3": SimpleNamespace(holdings={"k1": holding, "k2": coin})})
        rows = self.publisher().checkpoint(FakeHouse(self.ledger, books={"options": book}))["structures"]
        self.assertEqual(rows, [{"id": f"condor-vrp-3:{spec.code}".replace("|", "_").replace("+", "_"), "agent": "condor-vrp-3", "underlying": "XSP",
                                 "structure": "iron_condor", "legs": 4, "expiry": "2026-09-28", "quantity": 1, "real": True,
                                 "opened_at": "2026-09-28T14:02:40.000Z", "max_loss_usd": "184.00", "pnl_usd": "12.50"}])

    def test_the_tape_fixture_is_this_modules_own_output(self):
        batch = {"schema_version": 2, "events": self.tape()}
        path = FIXTURES / "site_events.json"
        if os.environ.get("LTCM_WRITE_SITE_FIXTURES"):
            path.write_text(json.dumps(batch, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), batch)


if __name__ == "__main__":
    unittest.main()
