"""Release E4, package J: THE TWIN OF A LIVE PANEL INSTANCE and the A14 reading of a basket (league/ops/forward_xs.py
`twin`, called by league/ops/forward_twins.py on the panel night).

The live side is a synthetic book: E1's own tables and the panel's (`league.equity.live.SCHEMA`,
`league.xs.book.SCHEMA`), filled with the orders of the Gym's own run under the instance's key, each buy in the
dollars of a LIVE sleeve (an invented $613.37, not the Gym's $1,000). What is held: the twin under the instance's run key
reproduces those orders (every session agrees, the two ctx hashes are equal, every lot is matched) and the marker
then lets the lane read "live"; weights agree where dollars could not; a live buy the budget skipped disagrees from
the day the standing target plans it again and agrees again once it is filled; a twin built under another run key
reads another ctx (why the key matters); a decision whose morning re-read was a mismatch and a retired instance's
sessions are not read; a child that fails the run is an interruption, never a row; a night past its deadline defers;
E3's own night writes nothing of a panel instance; THE A14 READING of a basket's closes (not agreed while its
sessions have no twin row: the blocker this package removes; read once they have); and the lines the dlane report
puts beside a panel program.

Every panel, program, book and figure is invented (`league.xs.synth`); no market data is read."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import unittest
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

from league.equity import live as L
from league.equity import schedule
from league.equity.store import mint_equity_gate_capability
from league.live import decider as D
from league.ops import dlane_report, forward_db as F, forward_register as R, forward_twins, twins
from league.ops import forward_xs as X
from league.swarm import elane_xs
from league.swarm.gate import run_sha
from league.tests.test_forward_db import at
from league.tests.test_forward_xs import CODE, House, registered
from league.xs import book as xbook
from league.xs import config as xconfig
from league.xs import runner as xrunner
from league.xs import store as xstore

#: An invented live sleeve's dollars (the Gym's is `league.xs.config.XS_SLEEVE_USD`).
SLEEVE = Decimal("613.37")
CENT = Decimal("0.01")


class Seated:
    """One panel version registered and SEATED: a live instance whose first decision is session `first`, and a
    synthetic live book that holds what the Gym's own run under the instance's key decided through session `last`."""

    def __init__(self, case: unittest.TestCase, *, first: int = 2, last: int = 30):
        self.h, self.key, self.pid = registered(case)
        h = self.h
        self.case = case
        self.iid = f"{self.key}:r"
        self.fid = self.key.split("@")[0]
        self.first, self.days = h.days[first], h.days
        h.store(h.days[last])
        gate = mint_equity_gate_capability(h.store_root, "a test's reference run")
        self.reference = xrunner.Isolated(D.InlineDecider(), h.store_root, nice=None).forward(
            CODE, {}, name=self.key, gate=gate, start=schedule.next_session(self.first), run_key=self.iid)
        universe = xstore.PanelStore(h.store_root, gate=gate).universe()
        bars = self.reference.slice.bars
        aid_of = {int(slot): int(aid) for slot, aid in zip(bars.ids, self.reference.slice.aids[int(bars.ref):])}
        self.symbol = lambda slot, day: universe.symbol(aid_of[int(slot)], day)
        self.picks = {p["decided"]: p for p in self.reference.result["picks"]}
        self.lots = list(self.reference.result["lots"])
        self.db = sqlite3.connect(str(h.root / R.LIVE_DB))
        case.addCleanup(self.db.close)
        self.db.executescript(L.SCHEMA + xbook.SCHEMA)
        self.db.execute(xbook.INSTANCE_KIND_DDL)
        self.db.execute("INSERT INTO eq_instances(id, family, version, lane, run_sha, code, params, band, max_hold, "
                        "created_at, kind) VALUES(?,?,1,'equity',?,?,'{}','probe',40,?,'panel')",
                        (self.iid, self.fid, run_sha(h.swarm.version(self.fid, 1)), CODE, at(self.first, 16, 30)))
        for lot in self.lots:
            self.lot(lot)
        for day, pick in sorted(self.picks.items()):
            self.decision(day, pick)
        self.db.commit()

    # ------------------------------------------------------------------------------------------- the book's rows
    def lot(self, lot: dict, *, opened: str | None = None) -> None:
        day = opened or lot["entry_day"]
        self.db.execute(
            "INSERT OR REPLACE INTO eq_lots(lid, instance, family, version, lane, symbol, class, qty, opened_qty, entry_px, "
            "entry_notional, entry_at, opened_at, opened_day, status, exit_at, exit_day, tag) VALUES(?,?,?,1,'equity',?,"
            "'stock','1','1','1','1',?,1.0,?,?,?,?,'xs')",
            (int(lot["lid"]), self.iid, self.fid, self.symbol(lot["id"], lot["entry_day"]), lot["entry_at"], day,
             "closed" if lot.get("exit_day") else "open", lot.get("exit_at"), lot.get("exit_day")))

    def buy(self, day: str, symbol: str, usd: Decimal | str, at_: str = "open") -> None:
        self.db.execute(
            "INSERT INTO eq_intents(instance, family, version, decided_day, exec_day, at, kind, symbol, usd, tag, status, "
            "created_at, updated_at) VALUES(?,?,1,?,?,?,'buy',?,?,'xs','filled',1.0,1.0)",
            (self.iid, self.fid, day, day, at_, symbol, str(usd)))

    def rebalance(self, day: str, *, called: int, ctx_sha: str | None, budget: Decimal | None = SLEEVE,
                  audit: str | None = "ok", standing: int = 0) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO eq_rebalances(instance, family, version, decided_day, exec_day, at, called, targets, "
            "standing, n_names, n_sells, n_buys, n_skipped, equity, budget, ctx_sha, audit, status, created_at) "
            "VALUES(?,?,1,?,?,'open',?,'[]',?,0,0,0,0,?,?,?,?,'planned',1.0)",
            (self.iid, self.fid, day, day, called, standing, None if budget is None else str(budget),
             None if budget is None else str(budget), ctx_sha, audit))

    def decision(self, day: str, pick: dict) -> None:
        """A live decision that planned what the Gym's run planned, each buy in the LIVE sleeve's dollars."""
        self.rebalance(day, called=int(pick["called"]), ctx_sha=pick["ctx_sha"], standing=int(not pick["called"]))
        for lid, _slot, _entry in pick["sells"]:
            self.db.execute(
                "INSERT INTO eq_intents(instance, family, version, decided_day, exec_day, at, kind, lid, tag, status, "
                "created_at, updated_at) VALUES(?,?,1,?,?,?,'sell',?,'xs','filled',1.0,1.0)",
                (self.iid, self.fid, day, day, pick["at"], int(lid)))
        for slot, usd in pick["buys"]:
            weight = Decimal(str(usd)) / Decimal(str(pick["budget"]))
            self.buy(day, self.symbol(slot, day), (weight * SLEEVE).quantize(CENT, rounding=ROUND_DOWN), pick["at"])

    # ------------------------------------------------------------------------------------------------- the night
    def night(self, index: int, **kw) -> dict:
        self.db.commit()
        return self.h.night(index, **kw)

    def rows(self) -> list[dict]:
        return [dict(r) for r in self.h.db.execute("SELECT * FROM fwd_twins WHERE instance=? ORDER BY day", (self.iid,))]

    def marker(self) -> dict:
        return json.loads((self.h.store_root / xbook.TWINS_FILE).read_text())

    def sessions(self, last: int) -> list[str]:
        """The decision sessions from the instance's first through session `last`."""
        return [d.isoformat() for d in self.days[self.days.index(self.first):last + 1]]


class TheTwinReproducesTheLiveBook(unittest.TestCase):
    def test_under_the_instances_key_every_session_agrees_and_the_marker_says_the_twin_is_there(self):
        s = Seated(self)
        receipt = s.night(14)
        finish = receipt["twins"]["finish"]
        wanted = s.sessions(12)                      # the store is through session 14: decisions through 12 are final
        rows = s.rows()
        self.assertEqual([r["day"] for r in rows], wanted)
        self.assertEqual((finish["instances"], finish["twins"], finish["disagreed"], finish["unreadable"],
                          finish["interrupted"], finish["failed"], finish["deferred"]), (1, len(wanted), 0, 0, 0, 0, 0))
        self.assertTrue(all(r["agree"] == 1 and r["why"] is None and r["cause"] is None and r["pid"] == s.pid for r in rows))
        called = [r for r in rows if r["day"] in s.picks and s.picks[r["day"]]["called"]]
        self.assertGreaterEqual(len(called), 2, "the fixture holds rebalance sessions")
        for row in called:
            self.assertEqual((row["live_bars"], row["shadow_bars"]), (s.picks[row["day"]]["ctx_sha"][:F.BARS_HEX],) * 2,
                             "under the instance's key the twin read the very ctx the live decision read")
            self.assertEqual(row["live_keys"], row["shadow_keys"])
            self.assertGreaterEqual(len(json.loads(row["live_keys"])), 5)
        quiet = [r for r in rows if r["day"] not in s.picks]
        self.assertTrue(quiet and all((r["live_keys"], r["shadow_keys"], r["live_bars"]) == ("[]", "[]", None) for r in quiet),
                        "a hold day agrees by saying nothing")
        # Every lot the twin opened through the night's day is one the live book opened that day.
        night = s.days[13].isoformat()
        entered = [lot for lot in s.lots if s.days[3].isoformat() <= lot["entry_day"] <= night]
        part = dict(s.h.db.execute("SELECT * FROM fwd_part WHERE instance=?", (s.iid,)).fetchone())
        self.assertEqual((part["through"], part["matched"], part["missed"], part["extra"]), (night, len(entered), 0, 0))
        self.assertGreaterEqual(part["matched"], 6)
        # THE MARKER, and the lane's own reader of it.
        self.assertEqual(receipt["marker"], {"instances": 1, "behind": 0})
        self.assertEqual(s.marker()["instances"], {s.iid: {"due": wanted[-1], "last": wanted[-1]}})
        self.assertIsNone(elane_xs._twins_ready(s.h.root, s.days[14], s.days[13]))
        self.assertEqual(s.h.events("twin_interrupted") + s.h.events("twin_unregistered")
                         + s.h.events("twin_sha_mismatch"), [])
        # The next night adds the next session's row and nothing twice.
        s.night(15)
        self.assertEqual([r["day"] for r in s.rows()], s.sessions(13))
        self.assertEqual(s.rows()[:len(rows)], rows, "first write stands")
        self.assertEqual(s.marker()["instances"][s.iid]["last"], s.sessions(13)[-1])
        self.assertEqual(s.h.night(15, write=False)["twins"]["finish"]["twins"], 0, "a night run again writes no row")

    def test_weights_agree_where_dollars_would_not(self):
        s = Seated(self)
        s.night(14)
        day = next(d for d in s.sessions(12) if d in s.picks and s.picks[d]["buys"])
        pick = s.picks[day]
        live = X.live_keys(X.read_live(s.h.root / R.LIVE_DB)["intents"][s.iid][day],
                           X.read_live(s.h.root / R.LIVE_DB)["rebalances"][s.iid][day])
        twin = X.keys(pick, {int(slot): s.symbol(slot, day) for slot, _ in pick["buys"]})
        self.assertEqual(set(live["buys"]), set(twin["buys"]))
        self.assertTrue(X.agree(live, twin))
        usd_live = {r[0]: Decimal(r[1]) for r in s.db.execute(
            "SELECT symbol, usd FROM eq_intents WHERE decided_day=? AND kind='buy'", (day,))}
        usd_twin = {s.symbol(slot, day): Decimal(str(usd)) for slot, usd in pick["buys"]}
        self.assertTrue(all(abs(usd_live[k] - usd_twin[k]) > 50 for k in usd_twin), "a cent rule would fail every buy")
        self.assertTrue(all(abs(live["buys"][k] - twin["buys"][k]) < X.WEIGHT_TOL / 10 for k in live["buys"]))

    def test_the_rule_of_a_sessions_keys(self):
        symbols = {7: "ZQAA", 9: "ZQAB"}
        pick = {"at": "open", "budget": 1000.0, "buys": [[7, 200.0]], "sells": [[3, 9, "2026-10-14"]]}
        twin = X.keys(pick, symbols)
        self.assertEqual(twin, {"sells": ["S|ZQAB|open|2026-10-14"], "buys": {"B|ZQAA|open": 0.2}})
        intents = [{"kind": "sell", "at": "open", "lid": 3, "lot_symbol": "ZQAB", "lot_day": "2026-10-14"},
                   {"kind": "buy", "at": "open", "symbol": "zqaa", "usd": "122.67"},
                   {"kind": "sell", "at": "open", "lid": None, "lot_symbol": None},     # a sell that names no lot
                   {"kind": "buy", "at": "noon", "symbol": "ZQAC", "usd": "10"}]        # no fill point of the book
        live = X.live_keys(intents, {"budget": "613.37"})
        self.assertEqual(live["sells"], twin["sells"])
        self.assertAlmostEqual(live["buys"]["B|ZQAA|open"], 0.2, places=4)
        self.assertTrue(X.agree(live, twin))
        self.assertTrue(X.agree(X.live_keys([], None), X.keys(None, {})), "no program order on either side agrees")
        for other in ({**twin, "buys": {"B|ZQAA|open": 0.2 + 2 * X.WEIGHT_TOL}},      # another weight
                      {**twin, "buys": {"B|ZQAA|close": 0.2}},                         # another fill point
                      {**twin, "buys": {}}, {**twin, "sells": []},
                      {**twin, "sells": ["S|ZQAB|open|2026-10-15"]}):                  # another lot of the name
            self.assertFalse(X.agree(live, other), other)
        self.assertTrue(X.agree(live, {**twin, "buys": {"B|ZQAA|open": 0.2 + X.WEIGHT_TOL / 2}}))
        unread = X.live_keys(intents[:2], {"budget": None})
        self.assertIsNone(unread["buys"]["B|ZQAA|open"])
        self.assertFalse(X.agree(unread, twin), "a weight that cannot be read agrees with nothing")
        with self.assertRaises(KeyError):
            X.keys(pick, {7: "ZQAA"})
        self.assertEqual(X.WEIGHT_TOL, 1e-3)

    def test_a_buy_the_budget_skipped_disagrees_until_the_standing_target_fills_it(self):
        s = Seated(self)
        first = next(d for d in s.sessions(12) if d in s.picks and s.picks[d]["buys"])
        index = [d.isoformat() for d in s.days].index(first)
        slot = s.picks[first]["buys"][0][0]
        name = s.symbol(slot, first)
        lot = next(lot for lot in s.lots if lot["id"] == slot and lot["entry_day"] == s.days[index + 1].isoformat())
        # The send of the next morning refused it for budget: the live book has no lot of it; at the next two closes
        # (hold days) the standing target plans it again; the second of those buys fills, two sessions late.
        late = [s.days[index + 1].isoformat(), s.days[index + 2].isoformat()]
        for day in late:
            self.assertNotIn(day, s.picks, "hold days of the twin")
            s.rebalance(day, called=0, ctx_sha=None, standing=1)
            s.buy(day, name, (Decimal("0.166") * SLEEVE).quantize(CENT))
        s.lot(lot, opened=s.days[index + 3].isoformat())
        s.night(index + 6)
        rows = {r["day"]: r for r in s.rows()}
        self.assertEqual(rows[first]["agree"], 1, "the buy was decided on both sides: its status is not read")
        for day in late:
            self.assertEqual((rows[day]["agree"], rows[day]["cause"], rows[day]["shadow_keys"]), (0, "unknown", "[]"), day)
            self.assertIn(f"B|{name}|open|", rows[day]["live_keys"])
        after = [d.isoformat() for d in s.days[index + 3:index + 5]]
        self.assertTrue(all(rows[day]["agree"] == 1 for day in after), "filled: the two books say the same again")
        part = dict(s.h.db.execute("SELECT matched, missed, extra FROM fwd_part WHERE instance=?", (s.iid,)).fetchone())
        self.assertEqual((part["missed"], part["extra"]), (1, 1), "the twin's lot of that day, and the live one two days on")
        self.assertEqual(s.night(index + 6, write=False)["twins"]["finish"]["disagreed"], 0, "counted the night they are written")

    def test_a_twin_under_another_run_key_reads_another_ctx(self):
        s = Seated(self)
        shadow = s.h.shadow(14)
        program = F.program(s.h.db, s.key)
        start = schedule.next_session(s.first)
        mine = shadow._forward(code=program.code, params=program.params, name=s.key, start=start, run_key=s.iid)
        other = shadow._forward(code=program.code, params=program.params, name=s.key, start=start)
        day = next(p["decided"] for p in mine.result["picks"] if p["called"] and p["buys"])
        ours, theirs = (next(p for p in run.result["picks"] if p["decided"] == day) for run in (mine, other))
        self.assertEqual(ours["ctx_sha"], s.picks[day]["ctx_sha"], "the instance's key: the ctx the live decision read")
        self.assertNotEqual(ours["ctx_sha"], theirs["ctx_sha"], "another key: other ids, other sector codes, another dither")
        self.assertFalse({b[0] for b in ours["buys"]} & {b[0] for b in theirs["buys"]}, "its slot ids name other slots")
        self.assertEqual((mine.slice.run_key, other.slice.run_key),
                         (s.iid, f"{other.result['run_sha']}|forward|{start.isoformat()}"))
        self.assertGreater(shadow.spent + 1.0, 0.0)


class WhatIsNotRead(unittest.TestCase):
    def test_a_decision_whose_morning_re_read_was_a_mismatch(self):
        s = Seated(self)
        day = next(d for d in s.sessions(12) if d in s.picks and s.picks[d]["called"])
        s.db.execute("UPDATE eq_rebalances SET audit='mismatch' WHERE decided_day=?", (day,))
        receipt = s.night(14)
        rows = {r["day"]: r for r in s.rows()}
        self.assertEqual((rows[day]["agree"], rows[day]["why"], rows[day]["cause"]), (None, "audit", None))
        self.assertEqual(receipt["twins"]["finish"]["unreadable"], 1)
        self.assertEqual(sum(1 for r in rows.values() if r["agree"] == 1), len(rows) - 1)
        self.assertEqual(receipt["marks"], 1, "and the day leaves its program's counted days")
        self.assertEqual(X.UNREADABLE, ("audit", "retired"))

    def test_a_retired_instances_sessions(self):
        s = Seated(self)
        retired = s.days[9]
        s.db.execute("UPDATE eq_instances SET retired_at=? WHERE id=?", (at(retired, 16, 30), s.iid))
        s.db.execute("UPDATE eq_lots SET status='closed', exit_day=? WHERE status='open' OR exit_day>?",
                     (s.days[10].isoformat(), s.days[10].isoformat()))
        receipt = s.night(14)
        rows = s.rows()
        self.assertEqual([r["day"] for r in rows], s.sessions(9), "through the session before its last lot closed")
        self.assertEqual((rows[-1]["agree"], rows[-1]["why"]), (None, "retired"))
        self.assertTrue(all(r["agree"] == 1 for r in rows[:-1]))
        self.assertEqual([e["day"] for e in s.h.events("twin_retired")], [retired.isoformat()])
        self.assertEqual(receipt["marker"], {"instances": 0, "behind": 0}, "the marker lists the ALIVE instances")
        self.assertEqual(s.marker()["instances"], {})
        self.assertEqual(s.night(15)["twins"]["finish"]["twins"], 0, "everything it will ever need is written")

    def test_a_child_that_fails_the_twins_run_is_an_interruption_and_the_marker_shows_it_behind(self):
        s = Seated(self)

        class Failing(D.InlineDecider):
            def kind(self, kind, op, payload, **kw):
                bars = payload.get("bars") if isinstance(payload, dict) else None
                if kind == "panel" and op == "run" and payload.get("name") == s.key and getattr(self, "armed", False) \
                        and bars is not None and len(bars.days) - int(bars.first) == 12:
                    raise D.DeciderError("the child died on the twin's run")
                return super().kind(kind, op, payload, **kw)

        child = Failing()
        shadow = s.h.shadow(14, decider=child)
        s.db.commit()
        # (the registry program's own run is 14 sessions long that night, the twin's 12: only the twin's fails)
        child.armed = True
        receipt = shadow.night()
        self.assertEqual((receipt["programs"], receipt["twins"]["finish"]["interrupted"]), (1, 1))
        self.assertEqual(s.rows(), [])
        (event,) = s.h.events("twin_interrupted")
        self.assertEqual((event["pid"], event["day"], event["payload"]["instance"]), (s.pid, s.days[13].isoformat(), s.iid))
        self.assertEqual(receipt["marker"], {"instances": 1, "behind": 1})
        self.assertEqual(s.marker()["instances"], {s.iid: {"due": s.days[12].isoformat(), "last": None}})
        self.assertIn("more than one session behind", elane_xs._twins_ready(s.h.root, s.days[14], s.days[13]))
        # The next night's child answers: every row is written then.
        s.night(15)
        self.assertEqual([r["day"] for r in s.rows()], s.sessions(13))

    def test_a_night_past_its_deadline_starts_no_twin_run(self):
        s = Seated(self)
        s.db.commit()
        shadow = s.h.shadow(14)
        out = {key: 0 for key in forward_twins.FINISH_KEYS}
        book = forward_twins.read_book(s.h.root / R.LIVE_DB)
        program = F.program(s.h.db, s.key)
        X.twin(s.h.root, s.h.db, shadow, book["instances"][0], book, program, out, now=s.h.clock(), late=True)
        self.assertEqual((out["deferred"], out["twins"], s.rows()), (1, 0, []))
        self.assertEqual(shadow.twin_due, {s.iid: s.days[12].isoformat()}, "owed all the same: the marker says so")

    def test_e3s_night_writes_nothing_of_a_panel_instance_and_the_panel_night_nothing_of_an_etf_one(self):
        s = Seated(self)
        s.db.commit()
        own = s.h.e3_shadow(14)
        finish = forward_twins.finish(s.h.root, s.h.db, own, now=s.h.clock())
        self.assertEqual((finish["instances"], finish["twins"], finish["failed"], finish["interrupted"]), (1, 0, 0, 0))
        self.assertNotIn("errors", finish)
        self.assertEqual(s.rows(), [])
        self.assertEqual(s.h.db.execute("SELECT COUNT(*) FROM fwd_part").fetchone()[0], 0)
        # ...and `twin` itself answers for its own lane on its own night alone.
        book = forward_twins.read_book(s.h.root / R.LIVE_DB)
        out = {key: 0 for key in forward_twins.FINISH_KEYS}
        X.twin(s.h.root, s.h.db, own, book["instances"][0], book, F.program(s.h.db, s.key), out, now=s.h.clock())
        self.assertEqual((set(out.values()), s.rows()), ({0}, []))


class TheA14ReadingOfABasket(unittest.TestCase):
    def closes(self, s: Seated, through: str) -> list[dict]:
        """The instance's closed lots as the Done meter's counted closes (league/ops/dlane_report.py's rows)."""
        return [{"equity": True, "pid": twins.equity_key(lot["lid"]), "instance": s.iid, "day": lot["exit_day"],
                 "opened_day": lot["entry_day"]} for lot in s.lots if lot.get("exit_day") and lot["exit_day"] <= through]

    def test_no_twin_row_is_not_agreed_and_with_the_panel_night_the_basket_is_read(self):
        s = Seated(self)
        s.db.commit()
        closes = self.closes(s, s.days[13].isoformat())
        self.assertGreaterEqual(len(closes), 3, "a basket: several lots closed on one date")
        self.assertLess(len({c["day"] for c in closes}), len(closes))
        s.h.swarm.put(twins.EQUITY_TWINS_KEY, {c["pid"]: {"final": True, "status": "priced", "gap_bp": 2.0} for c in closes})
        before = forward_twins.a14_reading(s.h.root, closes)
        self.assertEqual((before["applies"], before["holds"], before["final"]), (True, False, False))
        self.assertGreater(before["intents"]["missing"], 0)
        self.assertEqual(before["intents"]["agreed"], 0, "THE BLOCKER: every session of a panel close missing its twin row")
        s.night(15)
        after = forward_twins.a14_reading(s.h.root, closes)
        last = schedule.previous_session(max(dt.date.fromisoformat(c["day"]) for c in closes))
        sessions = [d for d in s.sessions(13) if d <= last.isoformat()]
        self.assertEqual(after["intents"], {**after["intents"], "instances": 1, "sessions": len(sessions),
                                            "agreed": len(sessions), "missing": 0, "unreadable": 0, "share": 1.0,
                                            "ok": True, "disagreed": 0})
        self.assertEqual((after["holds"], after["final"], after["gap"]["ok"]), (True, True, True))
        self.assertEqual(after["by_instance"], [{"instance": s.iid, "sessions": len(sessions), "agreed": len(sessions),
                                                 "missing": 0, "unreadable": 0}])

    def test_a_session_that_disagrees_counts_against_the_basket_as_it_does_against_any_program(self):
        s = Seated(self)
        day = next(d for d in s.sessions(12) if d in s.picks and s.picks[d]["buys"])
        s.db.execute("DELETE FROM eq_intents WHERE decided_day=? AND kind='buy' AND iid=(SELECT MIN(iid) FROM eq_intents "
                     "WHERE decided_day=? AND kind='buy')", (day, day))
        s.night(15)
        closes = self.closes(s, s.days[13].isoformat())
        s.h.swarm.put(twins.EQUITY_TWINS_KEY, {c["pid"]: {"final": True, "status": "priced", "gap_bp": 2.0} for c in closes})
        reading = forward_twins.a14_reading(s.h.root, closes)
        self.assertEqual((reading["intents"]["disagreed"], reading["intents"]["missing"]), (1, 0))
        self.assertEqual(reading["intents"]["agreed"], reading["intents"]["sessions"] - 1)
        self.assertEqual(reading["intents"]["causes"]["program"], 1, "the two sides read one ctx and decided otherwise")
        self.assertFalse(reading["holds"], "one session of a dozen is under the bound: A14's rule is E3's, unchanged")


class TheLinesBesideAPanelProgram(unittest.TestCase):
    def test_the_twins_residual_and_its_rebalance_sessions_agreed(self):
        s = Seated(self)
        self.assertEqual(X.beside(s.h.root), {}, "nothing recorded yet")
        day = [d for d in s.sessions(12) if d in s.picks and s.picks[d]["called"]][1]
        s.db.execute("DELETE FROM eq_intents WHERE decided_day=? AND kind='buy' AND iid=(SELECT MIN(iid) FROM eq_intents "
                     "WHERE decided_day=? AND kind='buy')", (day, day))
        s.night(14)
        found = X.beside(s.h.root)
        self.assertEqual(list(found), [s.iid])
        called = [d for d in s.sessions(12) if xconfig.decision_due(dt.date.fromisoformat(d), "weekly", 0)]
        self.assertEqual(found[s.iid]["rebalance"], {"sessions": len(called), "agreed": len(called) - 1,
                                                     "disagreed": [day], "unreadable": 0})
        residual = found[s.iid]["residual"]
        series = X.series(s.reference.result, through=s.days[13].isoformat())
        self.assertEqual((residual["from"], residual["through"], residual["sessions"]),
                         (s.days[3].isoformat(), s.days[13].isoformat(), len(series.iso)))
        self.assertAlmostEqual(residual["sum_x"], sum(series.x), places=12)
        self.assertAlmostEqual(residual["sum_x15"], sum(series.x15), places=12)
        self.assertIn("shadow twin", residual["of"])
        self.assertNotIn("at", residual)
        # The dlane report puts them beside the program, and says what is not recorded where nothing is.
        out = {"equity": {"panel": {"programs": {
            s.iid: {"residual_x": None, "rebalance_sessions_agreed": None, "owed": dlane_report.PANEL_OWED},
            "other@1:r": {"residual_x": None, "rebalance_sessions_agreed": None, "owed": dlane_report.PANEL_OWED}}}}}
        dlane_report.panel_forward(out, s.h.root)
        mine, other = (out["equity"]["panel"]["programs"][k] for k in (s.iid, "other@1:r"))
        self.assertEqual((mine["residual_x"], mine["rebalance_sessions_agreed"], mine["owed"]),
                         (residual, found[s.iid]["rebalance"], None))
        self.assertEqual((other["residual_x"], other["owed"]), (None, dlane_report.PANEL_OWED))
        dlane_report.panel_forward({"equity": {"panel": None}}, s.h.root)
        dlane_report.panel_forward({}, s.h.root)
        # A record that cannot be read is said, never a figure.
        Path(s.h.root / "elsewhere").mkdir()
        (s.h.root / "elsewhere" / F.DB).write_text("not a database")
        unread = {"equity": {"panel": {"programs": {s.iid: {"residual_x": None, "owed": dlane_report.PANEL_OWED}}}}}
        dlane_report.panel_forward(unread, s.h.root / "elsewhere")
        row = unread["equity"]["panel"]["programs"][s.iid]
        self.assertIsNone(row["residual_x"])
        self.assertIn("could not be read", row["owed"])


if __name__ == "__main__":
    unittest.main()
