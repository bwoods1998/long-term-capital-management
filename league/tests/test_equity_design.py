"""THE SEATS AND THE SLEEVE AS TWO NUMBERS (release E5-S, Oct 11, 2026): the tree is right at EVERY pair of the
pre-registered grid (seats 3, 4, 5, 6 x sleeve 0.50, 0.33, 0.25), whichever pair `set_design` has put in force.

- `TheGrid`: the designs table, one row a pair, at a stated E of $2,229 with the account all cash and nothing else
  held: a one-ETF lot in dollars; every seat's lot in its own ETF, sized one after another, with nothing realized and
  after a stated realized loss of $43.05 (how many fit whole, which rule cuts the next and to what, the open risk of
  the book that results); and every seat in ONE ETF. Each row is pinned here as figures and held three ways: to the
  House's own `size_entry` (league/tests/equity_design.py `Lane`, the facts as `EquityBook._size` states them), to
  the rule written out (`walk`), and to its arithmetic, line by line.
- `TheBookAtEveryPair`: the same seats through the real `EquityBook` (its own `_size`, the real `size_entry` and
  `available_cash`, the shared budget's own figures): the orders it sends at each pair.
- `TheDesignBlocks`: the four documents' design blocks are the rows in force, word for word, and so they move with
  the two numbers and with nothing else.
- `TheDeploy`: what a move of the pair does to the programs the House already holds. A Candidate waiting for a seat
  is seated at the next band sync, first come, and nothing else moves (the real swarm store, the real reader, the
  real band rule); a buy already planned is sized at its send under the sleeve in force, and its replay twin agrees
  at any size; a lot larger than a smaller sleeve is never sold for it; seats moved down unseat nobody.

Rule arithmetic and invented prices only: no figure here is a market's or an account's."""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import tempfile
import unittest
from decimal import ROUND_DOWN, Decimal as D
from pathlib import Path
from unittest import mock

from league.equity import LANES
from league.equity import bands as B
from league.equity import live as L
from league.equity import sizing as Z
from league.equity.families import EquityFamilies
from league.live import money as M
from league.swarm import bands, elane
from league.swarm.gate import run_sha
from league.swarm.store import SwarmStore
from league.tests import equity_design as X
from league.tests import test_equity_book as T
from league.tests.swarm_fakes import Clock as SwarmClock

#: The real functions `T.BookTest` stubs at their interface (read at import, before any test patches them).
REAL_SIZE, REAL_AVAILABLE, REAL_NEXT_BAND, REAL_SIZED_SHARE = Z.size_entry, M.available_cash, B.next_band, B.sized_sleeve_share
SUNDAY, FRIDAY, MONDAY, TUESDAY, WEDNESDAY = dt.date(2026, 10, 11), T.FRIDAY, T.MONDAY, T.TUESDAY, T.WEDNESDAY
ZERO = D(0)
ETFS = ("SPY", "QQQ", "IWM", "DIA", "XLK", "XLF")
#: A stated equity and a stated realized loss (rule arithmetic at stated figures, as the tree's other tests do).
E = D("2229")
LOSS = D("43.05")
CODE = "NEEDS = {'symbols': ['SPY'], 'history': 2}\nPARAMS = {}\n\n\ndef decide(ctx):\n    return []\n"

#: THE DESIGNS TABLE at E = $2,229, the account all cash, nothing else held, an ETF at $100.00 a share. A row a pair:
#:   the one-ETF lot (dollars);
#:   every seat in its own ETF, nothing realized: (the lots that fit whole, the rule that cuts the next lot and what
#:     it is cut to, or None when every seat's lot fits), then the open risk of that book (dollars, of the $400 window);
#:   the same after $43.05 of realized loss in the window, and that book's open risk;
#:   every seat in ONE ETF: (the lots that fit whole, the rule that cuts the next and what it gets, or None).
#: After the lot a rule cuts, every later seat gets nothing, refused under the same rule.
ROWS: dict[tuple[int, str], tuple] = {
    (3, "0.50"): ("557.25", (3, None), "334.35", (3, None), "334.35", (2, ("instrument", "0"))),
    (3, "0.33"): ("367.785", (3, None), "220.671", (3, None), "220.671", (3, None)),
    (3, "0.25"): ("278.625", (3, None), "167.175", (3, None), "167.175", (3, None)),
    (4, "0.50"): ("557.25", (3, ("budget", "328.25")), "400", (3, ("budget", "113")), "356.95", (2, ("instrument", "0"))),
    (4, "0.33"): ("367.785", (4, None), "294.228", (4, None), "294.228", (3, ("instrument", "11.145"))),
    (4, "0.25"): ("278.625", (4, None), "222.9", (4, None), "222.9", (4, None)),
    (5, "0.50"): ("557.25", (3, ("budget", "328.25")), "400", (3, ("budget", "113")), "356.95", (2, ("instrument", "0"))),
    (5, "0.33"): ("367.785", (5, None), "367.785", (4, ("budget", "313.61")), "356.95", (3, ("instrument", "11.145"))),
    (5, "0.25"): ("278.625", (5, None), "278.625", (5, None), "278.625", (4, ("instrument", "0"))),
    (6, "0.50"): ("557.25", (3, ("budget", "328.25")), "400", (3, ("budget", "113")), "356.95", (2, ("instrument", "0"))),
    (6, "0.33"): ("367.785", (5, ("budget", "161.075")), "400", (4, ("budget", "313.61")), "356.95",
                  (3, ("instrument", "11.145"))),
    (6, "0.25"): ("278.625", (6, None), "334.35", (6, None), "334.35", (4, ("instrument", "0"))),
}


def expand(seats: int, lot: D, fit: tuple) -> list[tuple[D, str]]:
    """A row's (whole, cut) as every seat's (dollars, rule): the whole lots, the cut one, then nothing under its rule."""
    whole, cut = fit
    out = [(lot, "intent")] * whole
    if cut is not None:
        out += [(D(cut[1]), cut[0])] + [(ZERO, cut[0])] * (seats - whole - 1)
    return out


class TheGrid(unittest.TestCase):
    def test_the_table_names_every_pair_and_the_pair_in_force_is_one_of_them(self):
        self.assertEqual(set(ROWS), set(X.CANDIDATES))
        self.assertEqual(len(X.CANDIDATES), 12)
        self.assertIn(X.in_force(), ROWS)
        self.assertEqual(X.REFERENCE, (3, "0.50"), "A20's design: the rollback")
        self.assertEqual(set(X.DIGESTS), set(X.CANDIDATES))

    def test_each_row_is_the_houses_own_sizing_and_the_rule_written_out(self):
        for pair, (lot, own, risk, lost, lost_risk, same) in ROWS.items():
            seats, sleeve = pair
            table, r = X.table_at(*pair), X.rows_of(X.constitution_at(*pair))
            lot = D(lot)
            own_asks = [(f"p{i + 1}", ETFS[i]) for i in range(seats)]
            same_asks = [(f"p{i + 1}", "SPY") for i in range(seats)]
            for asks, loss, fit, open_risk in ((own_asks, ZERO, own, risk), (own_asks, LOSS, lost, lost_risk),
                                               (same_asks, ZERO, same, None)):
                book = X.Lane(table, E, E, window_loss=loss)
                house = [(out.usd, out.binding) for out in (book.buy(p, s) for p, s in asks)]
                self.assertEqual(house, expand(seats, lot, fit), (pair, loss, "the House's size_entry"))
                self.assertEqual(X.walk(r, E, E, asks, window_loss=loss), expand(seats, lot, fit), (pair, loss, "by hand"))
                if open_risk is not None:
                    self.assertEqual(r.weight * book.invested, D(open_risk), (pair, loss))
                # No book the rule makes is past an owner line.
                self.assertLessEqual(r.weight * book.invested, r.window - loss, pair)
                self.assertLessEqual(book.invested, r.invested * E, pair)
                self.assertGreaterEqual(E - book.invested, r.reserve, pair)
                for symbol in ETFS:
                    self.assertLessEqual(book.held(symbol), r.etf * E, pair)

    def test_each_rows_arithmetic_line_by_line(self):
        """The same table from the rows alone, with no sizing function and no walk: a lot is the sleeve x an ETF's
        share x E; the window holds (400 - the loss) / 0.20 dollars of ETFs, the cash rule E - 50, the invested cap
        E, one ETF 0.50 x E; lots are whole while they fit the smallest of those, and the next gets what is left of
        it when that is the $10 minimum or more."""
        etf, weight, window, reserve, minimum = D("0.50"), D("0.20"), D("400"), D("50"), D("10")
        for (seats, sleeve), (lot, own, risk, lost, lost_risk, same) in ROWS.items():
            self.assertEqual(D(lot), D(sleeve) * etf * E, (seats, sleeve))
            for loss, (whole, cut), open_risk in ((ZERO, own, risk), (LOSS, lost, lost_risk)):
                rooms = {"budget": (window - loss) / weight, "cash": E - reserve, "invested": E}
                name = min(rooms, key=lambda k: (rooms[k], ("invested", "cash", "budget").index(k)))
                room = rooms[name]
                fits = min(seats, int(room // D(lot)))
                self.assertEqual(whole, fits, (seats, sleeve, loss))
                left = room - fits * D(lot)
                if fits == seats:
                    self.assertIsNone(cut)
                    held = fits * D(lot)
                else:
                    self.assertEqual(cut, (name, f"{left.normalize():f}") if left >= minimum else (name, "0"),
                                     (seats, sleeve, loss))
                    held = fits * D(lot) + (left if left >= minimum else ZERO)
                self.assertEqual(D(open_risk), weight * held, (seats, sleeve, loss))
            whole, cut = same
            fits = min(seats, int((etf * E) // D(lot)))
            self.assertEqual(whole, fits, (seats, sleeve, "one ETF"))
            left = etf * E - fits * D(lot)
            self.assertEqual(cut, None if fits == seats else ("instrument", f"{left.normalize():f}" if left >= minimum else "0"))

    def test_the_closed_forms_the_documents_state_are_the_tables(self):
        """`equity_design.figures` (what the design blocks print) against the pinned rows, at the same E."""
        for pair, (lot, own, risk, lost, lost_risk, same) in ROWS.items():
            f = X.figures(X.rows_of(X.constitution_at(*pair)), E=E)
            self.assertEqual(f["lot"] * E, D(lot), pair)
            self.assertEqual(min(pair[0], f["same"]), same[0], pair)
            self.assertEqual(min(f["cash_fit"], f["budget_fit"]), own[0], pair)
            if same[1] is not None:
                self.assertEqual(f["rest"] * E, D(same[1][1]), pair)

    def test_what_the_working_pairs_hold_in_words(self):
        """The two pairs whose arithmetic the release's notes lean on. SIX SEATS AT A QUARTER: six lots of
        0.125 x E are 0.75 x E, A20's own total, so the open risk of the full book is A20's ($334.35 of the $400
        window at E = $2,229) and no cap cuts a seat's lot, with nothing realized or after $43.05; four programs fit
        one ETF and a fifth is refused there. A20's design, three at a half: the same total in half as many lots."""
        six, a20 = ROWS[(6, "0.25")], ROWS[(3, "0.50")]
        self.assertEqual((six[1], six[3]), ((6, None), (6, None)))
        self.assertEqual((six[2], six[4]), (a20[2], a20[4]))
        self.assertEqual(D(six[0]) * 6, D(a20[0]) * 3)
        self.assertEqual(D(six[0]) * 6, D("0.75") * E)
        self.assertEqual(six[5], (4, ("instrument", "0")))
        self.assertEqual(a20[5], (2, ("instrument", "0")))
        self.assertLess(D(six[2]), D("400") - LOSS, "room left in the window after the stated loss")


class RealMoney(T.BookTest):
    """The book's harness (league/tests/test_equity_book.py) with money's and the swarm's REAL functions put back:
    `size_entry`, `available_cash`, `next_band`, `sized_sleeve_share`."""

    def setUp(self):
        super().setUp()
        for target, name, value in ((Z, "size_entry", REAL_SIZE), (M, "available_cash", REAL_AVAILABLE),
                                    (B, "next_band", REAL_NEXT_BAND), (B, "sized_sleeve_share", REAL_SIZED_SHARE)):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def fresh(self) -> Path:
        """A state root of its own (a test walks many pairs: each House starts on an empty one)."""
        return Path(tempfile.mkdtemp(dir=self.root))

    def at_pair(self, seats: int, sleeve: str, *, root: Path | None = None, **kw) -> T.Harness:
        """A House whose table's pair is (seats, sleeve), E = $2,229 and the account all cash, on a root of its own."""
        h = T.Harness(root or self.fresh(), cash=str(E), E=str(E), table=X.table_at(seats, sleeve).equity, **kw)
        self.addCleanup(h.state.close)
        h.market.quotes.update({"XLK": (D("249.90"), D("250.10")), "XLF": (D("49.99"), D("50.01"))})
        return h

    def redeploy(self, h: T.Harness, seats: int, sleeve: str) -> None:
        """The House starts again on a release whose pair is (seats, sleeve): a new book, the same state."""
        h.table = dataclasses.replace(h.table, equity=X.table_at(seats, sleeve).equity)
        h.book = h.new_book()


class TheBookAtEveryPair(RealMoney):
    def test_every_seat_buys_its_lot_through_the_real_book(self):
        """Every seat a Probe program with one planned buy of half its sleeve, each in its own ETF, sent in the open
        window's first minute: the book sends an order for every lot the table's row gives dollars to and none for a
        seat the row refuses; a whole lot is the row's lot at the order's limit, floored to a millionth of a share;
        and the book it ends with is inside every owner line."""
        for pair, (lot, own, _risk, _lost, _lost_risk, _same) in ROWS.items():
            with self.subTest(pair=pair):
                seats, sleeve = pair
                h = self.at_pair(seats, sleeve)
                r = X.rows_of(X.constitution_at(*pair))
                for i in range(seats):
                    inst = h.instance(f"fam-{i + 1}")
                    h.intent(inst, "buy", symbol=ETFS[i], share="0.5", at_="open")
                h.tick(9, 31)
                expected = expand(seats, D(lot), own)
                sent = {body["symbol"]: body for body in h.venue.sent}
                self.assertEqual(set(sent), {ETFS[i] for i, (usd, _) in enumerate(expected) if usd > 0}, pair)
                for i, (usd, rule) in enumerate(expected):
                    if rule != "intent":
                        continue
                    limit = D(sent[ETFS[i]]["limit_price"])
                    self.assertEqual(D(sent[ETFS[i]]["qty"]), (usd / limit).quantize(D("0.000001"), rounding=ROUND_DOWN),
                                     (pair, ETFS[i]))
                refused = [i for i in h.intents(kind="buy") if i.status == "refused"]
                self.assertEqual(len(refused), sum(1 for usd, _ in expected if usd == 0), pair)
                self.assertTrue(all(i.why.startswith("sizing (") for i in refused), [i.why for i in refused])
                lots = h.lots(open_only=True)
                invested = sum((x.value for x in lots), ZERO)
                self.assertLessEqual(invested, r.invested * E)
                self.assertLessEqual(r.weight * invested, r.window)
                self.assertGreaterEqual(h.venue.cash, r.reserve)
                for x in lots:
                    self.assertLessEqual(x.value, r.etf * r.sleeve * E, "half its own sleeve at most")
                self.assertEqual([s for s in h.venue.sent if s["side"] != "buy"], [], "nothing is ever sold for a size")


class TheDesignBlocks(unittest.TestCase):
    def test_every_document_states_the_rows_in_force(self):
        """The design block of each of the four documents is `equity_design.block` of the constitution in force, line
        for line: `set_design` wrote it from the rows, and a row moved by hand without it fails here."""
        for kind, (path, begin, end, _prefix) in X.BLOCKS.items():
            have = X.read_block(kind)
            self.assertEqual(have, X.block(kind), f"{path}: the design block is not the rows in force (run set_design)")
            text = (X.REPO / path).read_text(encoding="utf-8")
            self.assertEqual((text.split("\n").count(begin), text.split("\n").count(end)), (1, 1), path)

    def test_the_words_are_the_same_at_every_pair_and_only_figures_move(self):
        """Every pair's block has the same lines with the same words; what differs between two pairs is figures (a
        count, a share of E, a dollar amount, a digest's hex), and the pair itself is in the first line."""
        import re

        figure = re.compile(r"`[0-9a-f]{8}`|\$?\d[\d,]*(?:\.\d+)?x?")
        for kind in X.BLOCKS:
            shapes = set()
            for pair in X.CANDIDATES:
                lines = X.block(kind, X.constitution_at(*pair))
                shapes.add(tuple(figure.sub("#", line) for line in lines))
                self.assertIn(f"{pair[0]} seats", lines[0], (kind, pair))
                self.assertIn(f"a Probe sleeve of {pair[1]} x E", lines[0], (kind, pair))
            self.assertEqual(len(shapes), 1, f"{kind}: a word, not a figure, differs between two pairs")
        digests = X.block("operations", X.constitution_at(6, "0.25"))[-1]
        self.assertIn(X.DIGESTS[(6, "0.25")][0][:8], digests)
        self.assertIn(X.DIGESTS[X.REFERENCE][0][:8], digests, "the rollback's digest is in every document's block")

    def test_the_seats_are_written_in_three_places_and_they_agree(self):
        from league.constitution import CONSTITUTION
        from league.swarm import settings as settings_mod
        from league.tests import REAL_POLICY_PATH

        seats = CONSTITUTION["equity_money"]["probe"]["max_programs"]
        layer, status = settings_mod.read_policy(REAL_POLICY_PATH)
        self.assertEqual(status["state"], "ok")
        self.assertEqual((layer["elane"]["roster"], elane.DEFAULTS["roster"]), (seats, seats))
        with mock.patch.object(settings_mod, "POLICY_PATH", REAL_POLICY_PATH):
            self.assertEqual(elane._policy_roster(), seats, "the House's reading of the committed policy")


class TheDeploy(RealMoney):
    """What a move of the pair does to the programs the House already holds."""

    # ---------------------------------------------------------------- (a) a waiting Candidate is seated, first come
    def swarm(self, root: Path):
        """A real swarm store in the House's own state root: three Probe families (p1, p2, p3) and two Candidates
        that passed their looks later, in the order z-early then a-late (so first come is not the id's order)."""
        store = SwarmStore(root, clock=SwarmClock())
        self.addCleanup(store.close)
        from league.swarm import evaluator

        identity = evaluator.equity_identity()
        t0 = float(store.clock())
        for fid, band, symbol, at in (("p1", "probe", "SPY", t0), ("p2", "probe", "QQQ", t0 + 1), ("p3", "probe", "IWM", t0 + 2),
                                      ("z-early", "candidate", "DIA", t0 + 3), ("a-late", "candidate", "SPY", t0 + 4)):
            store.add_family({"id": fid, "mechanism": "Hold the ETF overnight from each close to the next open (MARKET "
                                                      "BETA).", "structure": "etf", "roots": [symbol],
                              "symbols": [symbol], "lane": "beta"}, origin="seed")
            version = store.add_version(fid, CODE.replace("SPY", symbol) + f"# {fid}\n", {}, author="test")
            store.set_state(fid, banded_version=1, banded_at=at,
                            banded_evaluator={"engine": identity["engine"], "equity_sha256": identity["equity"],
                                              "run_sha": run_sha(version)})
            store.set_band(fid, "candidate", reason="passed its sealed look")
            if band != "candidate":
                store.set_band(fid, band, reason="the EquityBook")
        return store

    def seats(self, count: int) -> None:
        """The release's seats on the swarm's side: the code's default (no swarm.json writes a roster)."""
        patcher = mock.patch.dict(elane.DEFAULTS, {"roster": count})
        patcher.start()
        self.addCleanup(patcher.stop)

    def house(self, root: Path, seats: int, sleeve: str) -> T.Harness:
        """The House on a release whose pair is (seats, sleeve), over the real reader of the swarm store at `root`."""
        self.seats(seats)
        h = self.at_pair(seats, sleeve, root=root)
        h.families = EquityFamilies(root)
        self.addCleanup(lambda: h.families._store is not None and h.families._store.close())
        h.book = h.new_book()
        for symbol in ETFS[:4]:
            h.market.make_bars(symbol, WEDNESDAY, n=20, price=float(sum(h.market.quote(symbol)) / 2))
        return h

    def snapshot(self, h: T.Harness, families) -> dict:
        ids = [L.instance_key(f, 1) for f in families]
        return {"instances": [dict(r) for r in h.state.rows("SELECT * FROM eq_instances ORDER BY id") if r["id"] in ids],
                "intents": [{k: v for k, v in dict(r).items()} for r in h.state.rows("SELECT * FROM eq_intents ORDER BY iid")
                            if r["instance"] in ids],
                "bands": {f: self.store.family(f)["band"] for f in families},
                "since": {k: v for k, v in (h.state.get("eq_band_since") or {}).items() if k in ids}}

    def test_seats_three_to_n_seats_the_waiting_candidate_first_come_and_nothing_else_moves(self):
        """UNDER BOTH VALUES OF THE SEAT RULE (release E5-A): "first-come" is this test as release E5-S wrote it (a
        waiting Candidate has no row; the earlier pass is seated first). Under "activity-1-free" the book reads the
        waiting Candidates too (they have rows and no instance) and seats by rank; neither of these two has the
        rule's two counts, so they rank by the earlier pass and the same one is seated."""
        from league.equity import bands as EB

        for rule in EB.SEAT_RULES:
            with X.seat_rule(rule):
                self.seats_three_to_n(rule)

    def seats_three_to_n(self, rule: str):
        from league.equity import bands as EB

        first_come = rule == EB.FIRST_COME
        for seats in (4, 5, 6):
            with self.subTest(seats=seats, rule=rule):
                root = self.fresh()
                self.store = self.swarm(root)
                # BEFORE: three seats, all held. The House's first minute makes the three instances and asks them for
                # Friday's close; p1 plans one buy; the two Candidates wait (no row, no instance).
                h = self.house(root, 3, "0.50")
                h.state.execute("DELETE FROM kv WHERE key='eq_decide'")
                key = {f: L.instance_key(f, 1) for f in ("p1", "p2", "p3", "z-early", "a-late")}
                h.decider.needs.update({key["p1"]: {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 2},
                                        key["p2"]: {"symbols": ["QQQ"], "history": 5, "max_hold_sessions": 2},
                                        key["p3"]: {"symbols": ["IWM"], "history": 5, "max_hold_sessions": 2},
                                        key["z-early"]: {"symbols": ["DIA"], "history": 5, "max_hold_sessions": 2},
                                        key["a-late"]: {"symbols": ["SPY"], "history": 5, "max_hold_sessions": 2}})
                h.decider.plans[key["p1"]] = [{"buy": "SPY", "share": 0.5, "at": "open"}]
                h.decider.plans[key["z-early"]] = [{"buy": "DIA", "share": 0.5, "at": "close"}]
                h.tick(14, 0, day=SUNDAY)
                h.tick(14, 1, day=SUNDAY)
                if first_come:
                    self.assertEqual(sorted(r["family"] for r in h.families.read()), ["p1", "p2", "p3"],
                                     "three seats: a waiting Candidate has no row")
                else:
                    self.assertEqual(sorted((r["family"], r["band"]) for r in h.families.read()
                                            if r["band"] == "candidate"), [("a-late", "candidate"), ("z-early", "candidate")],
                                     "the book ranks the waiting itself: they have rows, and no instance (below)")
                    self.assertEqual([w["family"] for w in h.book.seats()["waiting"]], ["z-early", "a-late"],
                                     "the book's plan: the earlier pass first (neither has the rule's counts)")
                self.assertEqual(bands.roster(root, lanes=LANES)["waiting"], ["a-late", "z-early"])
                self.assertEqual(sorted(i.id for i in h.book._instances(alive=True)),
                                 sorted(key[f] for f in ("p1", "p2", "p3")))
                self.assertEqual([(i.instance, i.kind, i.symbol, i.status) for i in h.intents()],
                                 [(key["p1"], "buy", "SPY", "planned")])
                before = self.snapshot(h, ("p1", "p2", "p3"))
                asked_before = len(h.decider.jobs)
                # THE DEPLOY: the same state, a release whose seats are `seats` (and the same sleeve: only seats move).
                h.clock.set(T.at(SUNDAY, 15, 0))
                self.seats(seats)
                self.redeploy(h, seats, "0.50")
                out = h.tick(15, 0, day=SUNDAY)                     # the first band sync on the release: the seating pass
                seated = ["z-early"] if seats == 4 else ["a-late", "z-early"]
                self.assertEqual(sorted(r["family"] for r in h.families.read() if first_come or r["band"] != "candidate"),
                                 sorted(["p1", "p2", "p3", *seated]))
                for family in ("z-early", "a-late"):
                    inst = h.book._instance(key[family])
                    if family in seated:
                        self.assertEqual(self.store.family(family)["band"], "probe", (seats, family))
                        self.assertEqual((inst.band, inst.last_decided_day), ("probe", FRIDAY.isoformat()),
                                         "seated, and asked for the same close")
                    else:
                        self.assertEqual(self.store.family(family)["band"], "candidate", "the later one still waits")
                        self.assertIsNone(inst)
                self.assertEqual(sorted(out["decided"]), sorted(f"{key[f]}: {1 if f == 'z-early' else 0}" for f in seated))
                self.assertEqual([[j["key"] for j in call["jobs"]] for call in h.decider.jobs[asked_before:]],
                                 [sorted(key[f] for f in seated)], "only the newly seated are asked")
                self.assertEqual(bands.roster(root, lanes=LANES)["waiting"], [] if seats > 4 else ["a-late"])
                # ...FIRST COME: at four seats the one that passed its look first, though the other's id sorts first.
                moves = [e for kind, e in h.events if kind == "equity.band"]
                self.assertEqual(sorted((e["family"], e["from"], e["to"]) for e in moves),
                                 sorted((f, "candidate", "probe") for f in seated))
                # ...AND NOTHING ELSE: the three seated programs' instances, intents, bands and band days are as they were.
                self.assertEqual(self.snapshot(h, ("p1", "p2", "p3")), before)
                self.assertEqual(h.venue.sent, [], "no order")
                self.assertEqual([e for kind, e in h.events if kind == "equity.instance" and e.get("retired")], [])
                self.assertEqual([(i.kind, i.exec_day) for i in h.intents(instance=key["z-early"])],
                                 [("buy", MONDAY.isoformat())], "its first order goes in the next session")

    def test_with_the_seats_in_force_the_swarm_and_the_book_agree_on_the_count(self):
        """No patch: the pair in force. The swarm seats `elane.roster_seats` Candidates (the code's default when no
        swarm.json writes one, at most the default when one does), and the book's count is the table's row."""
        seats, sleeve = X.in_force()
        self.assertEqual(elane.roster_seats(self.root), seats)
        self.assertEqual(M.EquityTable.from_constitution().probe_max_programs, seats)
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"roster": 3}}))
        elane._roster_good.clear()
        self.addCleanup(elane._roster_good.clear)
        self.assertEqual(elane.roster_seats(self.root), 3, "a swarm.json that still says 3 keeps three seats")
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"roster": 9}}))
        self.assertEqual(elane.roster_seats(self.root), seats, "and one above the table's seats is the table's")

    # ---------------------------------------------------------------- (b) a planned buy is sized at its send
    def test_a_planned_buy_is_sized_at_its_send_under_the_sleeve_in_force(self):
        """A buy decided on Friday under A20's sleeve (0.50), sent on Monday after a deploy that moved the pair: a
        `share` intent is that share of the sleeve in force then; a `usd` intent (the dollars it asked under the old
        sleeve) is cut to the new sleeve's own cap, by name. The intent's row is not rewritten by the deploy."""
        old_lot = D("0.50") * D("0.5") * E
        for pair in X.CANDIDATES:
            seats, sleeve = pair
            new_lot = D(sleeve) * D("0.5") * E
            for kind in ("share", "usd"):
                with self.subTest(pair=pair, kind=kind):
                    h = self.at_pair(3, "0.50")
                    inst = h.instance("fam-1")
                    intent = h.intent(inst, "buy", symbol="SPY", at_="open",
                                      **({"share": "0.5"} if kind == "share" else {"usd": str(old_lot)}))
                    row = dict(h.state.rows("SELECT * FROM eq_intents WHERE iid=?", (intent.iid,))[0])
                    self.redeploy(h, seats, sleeve)
                    self.assertEqual(dict(h.state.rows("SELECT * FROM eq_intents WHERE iid=?", (intent.iid,))[0]), row,
                                     "the deploy rewrites no planned intent")
                    h.tick(9, 31)
                    [sent] = h.venue.sent
                    limit = D(sent["limit_price"])
                    self.assertEqual(D(sent["qty"]), (new_lot / limit).quantize(D("0.000001"), rounding=ROUND_DOWN))
                    [order] = h.orders()
                    rule = "intent" if kind == "share" or new_lot == old_lot else "sleeve_cap"
                    self.assertTrue(order.why.startswith(f"entry ({rule}:"), order.why)
                    [lot] = h.lots(open_only=True)
                    self.assertLessEqual(lot.entry_notional, new_lot)

    def test_the_replay_twin_agrees_at_any_size(self):
        """The closed-form equity twin buys the lot's OWN entry notional and reads returns on it, and the forward
        record keys a buy by its symbol and fill point whatever its size: the same fills at A20's lot and at half
        and a quarter of it are the same gap against the twin, and the same intent keys."""
        from league.ops import forward_twins as FT
        from league.ops import twins as TW
        from league.tests.test_equity_twins import GOLDEN_BARS, lot as lot_row, ny

        gaps = []
        for notional in (D("557.25"), D("278.625"), D("139.3125")):
            qty = (notional / D("100.02")).quantize(D("0.000001"), rounding=ROUND_DOWN)
            paid = qty * D("100.02")
            cash = qty * D("101.95") - D("0.02") - paid
            rec = TW.equity_twin(lot_row(notional=str(paid), opened_qty=str(qty), qty=str(qty), cash=str(cash)),
                                 GOLDEN_BARS, at=ny("2026-10-16", 9, 50))
            self.assertEqual((rec["status"], rec["final"]), ("priced", True))
            twin_paid = D(rec["twin"]["shares"]) * D(str(rec["twin"]["entry_px"]))
            self.assertLessEqual(twin_paid, paid)
            self.assertGreater(twin_paid, paid - D("0.0002"), "the twin buys the lot's own entry notional")
            gaps.append(rec["gap_bp"])
        self.assertLess(max(gaps) - min(gaps), 0.75, f"the same fills, the same gap a side at any lot: {gaps}")
        needs, held = ["SPY"], {}
        self.assertEqual(FT.keys_of([{"buy": "SPY", "share": 0.5, "at": "open"}], needs=needs, held=held),
                         FT.keys_of([{"buy": "SPY", "usd": 139.31, "at": "open"}], needs=needs, held=held))
        self.assertEqual(FT.keys_of([{"buy": "SPY", "share": 0.5}], needs=needs, held=held), ["B|SPY|open"])

    # ---------------------------------------------------------------- (c) no lot is sold for a size
    def test_a_lot_larger_than_a_smaller_sleeve_is_never_sold_for_it(self):
        """A lot of A20's size (a quarter of E) held when the sleeve shrinks: the House plans no exit for it and sends
        no sale, through two whole sessions and their decisions. Its program's next buy of the SAME ETF is refused by
        its own sleeve's cap on one ETF, by name; its buy of ANOTHER ETF is refused by the sleeve's cash when the lot
        alone fills the new sleeve (0.25), and cut to what the sleeve has left when it does not (0.33). Nothing else
        happens to the lot."""
        for pair in (c for c in X.CANDIDATES if D(c[1]) < D("0.50")):
            with self.subTest(pair=pair):
                seats, sleeve = pair
                h = self.at_pair(3, "0.50")
                inst = h.instance("fam-1", max_hold=20)
                held = h.lot(inst, "SPY", "0.93", "600", opened=FRIDAY)          # $558.00: A20's lot at E = $2,229
                h.venue.cash -= held.entry_notional
                new_sleeve = D(sleeve) * E
                self.assertGreater(held.value, new_sleeve * D("0.5"), "larger than half the new sleeve")
                self.redeploy(h, seats, sleeve)
                h.decider.needs[inst.id] = {"symbols": ["SPY", "QQQ"], "history": 5, "max_hold_sessions": 20}
                h.decider.plans[inst.id] = [{"buy": "SPY", "share": 0.5, "at": "open"},
                                            {"buy": "QQQ", "share": 0.5, "at": "open"}]
                for symbol in ("SPY", "QQQ"):
                    h.market.make_bars(symbol, WEDNESDAY, n=20, price=float(sum(h.market.quote(symbol)) / 2))
                h.families.rows["fam-1"]["symbols"] = ["SPY", "QQQ"]
                for day in (MONDAY, TUESDAY):
                    for hh, mm in ((9, 26), (9, 31), (9, 33), (12, 0), (15, 55), (15, 58), (16, 21), (16, 31)):
                        h.tick(hh, mm, day=day)
                self.assertEqual([body for body in h.venue.sent if body["side"] == "sell"], [], "no sale")
                self.assertEqual(h.intents(kind="house_exit"), [], "the House plans no exit for a size")
                self.assertEqual(h.intents(kind="sell"), [])
                [still] = [x for x in h.lots(open_only=True) if x.symbol == "SPY"]
                self.assertEqual((still.lid, still.qty, still.status), (held.lid, D("0.93"), "open"))
                self.assertIsNone(h.book._instance(inst.id).retired_at)
                self.assertEqual(h.book._instance(inst.id).band, "probe")
                # Its own buys, decided on Monday for Tuesday's open, met its own sleeve, by name.
                buys = {i.symbol: i for i in h.intents(kind="buy") if i.exec_day == TUESDAY.isoformat()}
                self.assertEqual(sorted(buys), ["QQQ", "SPY"])
                self.assertEqual(buys["SPY"].status, "refused")
                self.assertTrue(buys["SPY"].why.startswith("sizing (sleeve_cap): refused: SPY may hold"), buys["SPY"].why)
                monday_close = D(str(next(r["c"] for r in h.market.bar_rows["raw"]["SPY"]
                                          if r["t"].startswith(MONDAY.isoformat()))))
                left = new_sleeve - D("0.93") * monday_close              # the sleeve less the lot at Monday's mark
                sent = [body for body in h.venue.sent if body["side"] == "buy"]
                if left < D("10"):
                    self.assertEqual(buys["QQQ"].status, "refused")
                    self.assertTrue(buys["QQQ"].why.startswith("sizing (sleeve_cash): refused: the sleeve has $0.00"),
                                    buys["QQQ"].why)
                    self.assertEqual(sent, [])
                else:
                    [order] = [o for o in h.orders() if o.side == "buy"]
                    self.assertEqual((order.symbol, len(sent)), ("QQQ", 1))
                    self.assertTrue(order.why.startswith("entry (sleeve_cash:"), order.why)
                    self.assertLessEqual(order.qty * order.limit_px, left)
                    self.assertGreater(order.qty * order.limit_px, left - order.limit_px * D("0.000001"))

    # ---------------------------------------------------------------- (d) seats moved down unseat nobody
    def test_seats_moved_down_unseat_nobody(self):
        """Six programs at Probe and a release whose seats are three (the rollback after more were seated): the
        decision's band sync moves no band and retires nobody; a Candidate that holds a row is not seated while the
        count has no room; the swarm's roster never hides a Probe family."""
        families = [f"fam-{i + 1}" for i in range(6)]
        h = self.at_pair(6, "0.25")
        for i, family in enumerate(families):
            h.instance(family)
            h.families.rows[family]["symbols"] = [ETFS[i]]
        self.redeploy(h, 3, "0.50")
        h.families.rows["late"] = T.family_row("late", band="candidate")
        h.decide_setup(MONDAY)
        h.tick(16, 31)
        self.assertEqual(h.families.moves, [], "no band moved")
        self.assertEqual(sorted(i.family for i in h.book._instances(alive=True)), families)
        self.assertTrue(all(i.band == "probe" and i.retired_at is None for i in h.book._instances(alive=True)))
        self.assertEqual(h.families.rows["late"]["band"], "candidate", "no seat while six hold three")
        self.assertEqual(h.intents(kind="house_exit"), [])
        fams = [{"id": f, "band": "probe", "band_since": None, "structure": "etf", "state": {"banded_at": float(i)}}
                for i, f in enumerate(families)]
        fams.append({"id": "late", "band": "candidate", "band_since": None, "structure": "etf", "state": {"banded_at": 9.0}})
        seat = bands.equity_seating(fams, 3)
        self.assertEqual((seat["probe"], seat["seated"], seat["waiting"]), (families, [], ["late"]))


if __name__ == "__main__":
    unittest.main()
