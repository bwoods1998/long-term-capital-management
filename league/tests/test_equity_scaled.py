"""THE SCALED BAND (C3 (A45) of the scaling plan, SHIPPED DARK; the constitution's `equity_money.scaled`, league/equity/
bands.py `scaled_settings` and the rules beside it, league/equity/live.py `EquityBook._scale_for`, `_scale_now`,
`_scaled_room`, `probe_figures`, league/swarm/elane.py `loss_line`, `scale_setting`): every rule of the C3 row, each with
the band switched on in the test alone (a pin-sha row and, for R2 and up, Blake's Scaled lines patched in for the body).

- the rows: shares and multiples only, inside their bounds, the pin's sha "" or a sha256, never decreasing rungs; a table
  without the block is dark; an unreadable block is dark;
- the pin: its rungs and the plan's sha read whole or not at all, never touching C2's E_P;
- sizing: at a rung on min(the rung's multiple x THE MATCHING PIN'S E_P, 0.50 x E), never through C2's frozen pool; the
  lower of the pin's rung and the setting; R1 at most without the Scaled lines; Probe for a panel, a Sized program, a
  newer version, a program the pin does not name; a pin that does not match the row refuses a program last read at a
  rung and sizes every other at Probe, one standing alert, health and the pre-open check say it;
- the marks: an R1 buy and lot carry the Probe mark (in the lines in force); an R2 one from the yes the Scaled mark, sized
  to the Scaled room, its open risk out of the Probe room, its close out of the Probe window, the total and EDM1's line;
- the House's own step-downs: D3 (the program line since a change, the cumulative line), D5 (the Scaled window: opens
  pause), D6 (the Scaled total: every program back to Probe, the ladder closed for that plan's version);
- the swarm's family line reads Probe-marked lots only with the yes's third part, every lot otherwise;
- the setting may only lower, and fails closed.
Every figure is invented (an E, an E_P, prices); no account's. The book runs on league/tests/test_equity_book.py's
harness (money's `size_entry` stubbed at its interface, recording what the book stated to it). Standard library only."""

from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from decimal import Decimal as D
from pathlib import Path
from typing import Iterator
from unittest import mock

from league import constitution as Cn
from league.constitution import CONSTITUTION
from league.equity import bands as B
from league.equity import live as L
from league.tests import test_equity_book as T
from league.tests.test_equity_probe_pin import PinHarness

#: Synthetic figures: the sizing E the House reads and the pin's E_P.
E = "5000"
E_P = "2000"
PLAN = "ab" * 32
KEY_A = L.program_key("fam-a", 1)
KEY_B = L.program_key("fam-b", 1)


def pin(root: Path, rungs: dict | None = None, *, e_p: str = E_P, plan: str = PLAN, **extra) -> str:
    """Write a pin with C3's fields; its sha256."""
    body = json.dumps({"probe_e_usd": e_p, "plan_sha256": plan, "rungs": rungs or {}, "nonce": "n" * 32, **extra},
                      sort_keys=True).encode()
    (root / L.PROBE_PIN_FILE).write_bytes(body)
    return hashlib.sha256(body).hexdigest()


@contextmanager
def band(sha: str, *, lines: bool = False, probe_only: bool = False, **rows) -> Iterator[None]:
    """The Scaled band switched on for the body: the pin-sha row, and Blake's Scaled lines when `lines`."""
    with mock.patch.dict(CONSTITUTION["equity_money"]["scaled"], {"pin_sha256": sha, **rows}), \
            mock.patch.dict(CONSTITUTION["equity_money"]["scaled"]["lines"],
                            {"in_force": lines, "family_line_probe_only": probe_only}):
        yield


class TheRows(unittest.TestCase):
    def test_shares_and_multiples_only_inside_their_bounds_and_dark(self):
        block = CONSTITUTION["equity_money"]["scaled"]
        self.assertEqual(block["rungs"], {"r1": "0.50", "r2": "1.25", "r3": "2.25", "r4": "4.00", "r5": "6.75"},
                         "the plan's table 3.2")
        self.assertEqual(block["max_sleeve_share"], "0.50")
        self.assertEqual({k: block["lines"][k] for k in ("window_share", "total_share", "program_share",
                                                         "window_sessions")},
                         {"window_share": "0.18", "total_share": "0.36", "program_share": "0.10", "window_sessions": 20})
        text = json.dumps(block)
        self.assertNotIn("usd", text, "no dollar figure in the public table")
        self.assertEqual(Cn.equity_money_problems(), [])
        st = B.scaled_settings()
        self.assertTrue(st.dark)
        self.assertEqual((st.top, st.lines_in_force), (1, False), "nothing past R1 before the yes")
        for path, (low, high) in Cn.EQUITY_MONEY_BOUNDS.items():
            if path.startswith("scaled."):
                loose = low if path == "scaled.lines.window_sessions" else high   # a longer window is never looser
                self.assertEqual(str(Cn._at(CONSTITUTION["equity_money"], path)), loose,
                                 f"{path} sits at its loose end: a row may only tighten")

    def test_the_constitutions_own_check(self):
        def problems(**patch_rows):
            c = copy.deepcopy(CONSTITUTION)
            for path, value in patch_rows.items():
                node = c["equity_money"]["scaled"]
                *head, last = path.split("__")
                for k in head:
                    node = node[k]
                node[last] = value
            return [p for p in Cn.equity_money_problems(c) if p.startswith("equity_money.scaled")]

        self.assertEqual(problems(pin_sha256="a" * 64), [])
        for bad in ("A" * 64, "a" * 63, "x", None, 5):
            self.assertTrue(problems(pin_sha256=bad), bad)
        self.assertTrue(problems(rungs__r2="0.40"), "R2 under R1: a higher rung never sizes smaller")
        self.assertTrue(problems(rungs__r5="7.00"), "a rung past the plan's multiple")
        self.assertTrue(problems(max_sleeve_share="0.60"), "a sleeve past 0.50 x E")
        self.assertTrue(problems(lines__window_share="0.20"))
        self.assertTrue(problems(lines__window_sessions=10))
        self.assertTrue(problems(lines__in_force=1), "exactly True or False")
        self.assertEqual(problems(rungs__r1="0.25", lines__program_share="0.05"), [], "tighter rows are rows")
        c = copy.deepcopy(CONSTITUTION)
        c["equity_money"].pop("scaled")
        self.assertEqual(Cn.equity_money_problems(c), [], "a table from before C3 still builds")
        self.assertTrue(B.scaled_settings(c).dark, "and is dark")
        c = copy.deepcopy(CONSTITUTION)
        c["equity_money"]["scaled"]["pin_sha256"] = "a" * 64
        c["equity_money"]["scaled"]["rungs"]["r3"] = "9"
        self.assertEqual(B.scaled_settings(c), B.SCALED_DARK, "a block outside its bounds is dark (fail closed)")
        c["equity_money"]["scaled"]["rungs"]["r3"] = "2.25"
        self.assertEqual(B.scaled_settings(c).pin_sha256, "a" * 64)


class ThePureRules(unittest.TestCase):
    def setUp(self):
        c = copy.deepcopy(CONSTITUTION)
        c["equity_money"]["scaled"].update(pin_sha256="a" * 64)
        c["equity_money"]["scaled"]["lines"]["in_force"] = True
        self.st = B.scaled_settings(c)

    def test_a_rungs_sleeve_is_its_multiple_of_e_p_never_above_half_of_e(self):
        self.assertEqual(B.rung_sleeve(self.st, 1, D("1600"), D("25000")), D("800.0000"))
        self.assertEqual(B.rung_sleeve(self.st, 5, D("1600"), D("25000")), D("10800.0000"))
        self.assertEqual(B.rung_sleeve(self.st, 5, D("1600"), D("20000")), D("10000.00"), "0.50 x E")
        self.assertEqual(B.rung_sleeve(self.st, 0, D("1600"), D("25000")), D(0))
        self.assertEqual([self.st.scaled(r) for r in range(6)], [False, False, True, True, True, True])

    def test_the_program_lines(self):
        self.assertEqual(B.program_line(self.st, 1, D("800"), D("-300")), D("-300"), "R1: the line in force")
        self.assertEqual(B.program_line(self.st, 2, D("2000"), D("-300")), D("-200.00"), "-10% of the sleeve")
        self.assertIsNone(B.program_line(self.st, 0, D("1"), D("-300")))
        self.assertIsNone(B.program_lines(rung=2, since_change=D("-256.24"), line_now=D("-256.25"),
                                          cumulative=D("-400"), line_highest=D("-461")))
        self.assertIn("since its last rung change", B.program_lines(rung=2, since_change=D("-256.25"),
                                                                    line_now=D("-256.25"), cumulative=D("0"),
                                                                    line_highest=D("-461")))
        self.assertIn("cumulative", B.program_lines(rung=2, since_change=D("0"), line_now=D("-256.25"),
                                                    cumulative=D("-461"), line_highest=D("-461")))
        # A row tightened to nothing: its line is 0, hit by the first loss, never by no loss (the review).
        self.assertIsNone(B.program_lines(rung=2, since_change=D("0"), line_now=D("0"), cumulative=D("0"),
                                          line_highest=D("0")))
        self.assertIsNotNone(B.program_lines(rung=2, since_change=D("-0.01"), line_now=D("0"), cumulative=D("-0.01"),
                                             line_highest=D("0")))

    def test_the_window_is_the_probe_windows_worst_net_stretch(self):
        from league.live import real as R

        closes = [("2026-10-01", D("120")), ("2026-10-05", D("-80")), ("2026-10-06", D("-90")), (None, D("10")),
                  ("2026-09-01", D("-500"))]
        self.assertEqual(B.worst_net_stretch(closes, since="2026-09-15"), D("160"))
        self.assertEqual(B.worst_net_stretch(closes, since=None), D("540"))
        # The Probe window's own figure over the same closes (equity rows through the hook): the same rule.
        with mock.patch("league.live.equity_hook.probe_figures",
                        return_value=L.ProbeFigures(0, tuple(closes), D(0))):
            self.assertEqual(R.probe_realized(lambda sql, args=(): [], basis="net", since="2026-09-15"), D("160"))

    def test_the_scaled_room(self):
        room = B.scaled_room(self.st, sleeves_usd=D("2500"), peak_usd=D("5000"),
                             closes=[("2026-10-05", D("-100")), ("2026-10-06", D("40"))], window_since="2026-09-15",
                             open_risk=D("200"))
        # The window's worst net stretch: from Oct 5, -100 + 40 = -60 (a gain after a loss offsets it in that stretch).
        self.assertEqual((room.window_budget, room.window, room.total_budget, room.total),
                         (D("450.00"), D("60"), D("1800.00"), D("60")))
        self.assertEqual(room.room, D("190.00"))
        self.assertFalse(room.window_reached)
        self.assertTrue(B.scaled_room(self.st, sleeves_usd=D("2500"), peak_usd=D("5000"), closes=[],
                                      window_since=None, open_risk=D("450")).window_reached)
        self.assertTrue(B.scaled_room(self.st, sleeves_usd=D(0), peak_usd=D("5000"),
                                      closes=[("2026-10-05", D("-1800"))], window_since=None, open_risk=D(0)).total_reached)
        self.assertFalse(B.scaled_room(self.st, sleeves_usd=D(0), peak_usd=D(0), closes=[("x", D("-5"))],
                                       window_since=None, open_risk=D(0)).total_reached, "no sleeve ever: no total")


class ThePin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_its_rungs_and_the_plans_sha_read_whole_or_not_at_all_never_touching_e_p(self):
        pin(self.root, {KEY_A: 2, KEY_B: 0})
        got = L.read_probe_pin(self.root)
        self.assertEqual((got.state, got.e_p, got.rungs, got.plan_sha256), ("read", D(E_P), ((KEY_A, 2), (KEY_B, 0)), PLAN))
        (self.root / L.PROBE_PIN_FILE).write_text(json.dumps({"probe_e_usd": E_P}), encoding="utf-8")
        self.assertEqual(L.read_probe_pin(self.root).rungs, (), "a C2 pin names no rung")
        for rungs, plan in (({KEY_A: 6}, PLAN), ({KEY_A: True}, PLAN), ({KEY_A: 1.0}, PLAN), ({"fam-a": 1}, PLAN),
                            ({"eq|fam a|v1": 1}, PLAN), ({KEY_A: 1}, ""), ([1], PLAN), ({KEY_A: 1}, "zz")):
            pin(self.root, rungs, plan=plan)
            got = L.read_probe_pin(self.root)
            self.assertEqual((got.state, got.e_p, got.rungs), ("read", D(E_P), None), (rungs, plan))
            self.assertTrue(got.rungs_why)


class Scaled(T.BookTest):
    """The band switched on in the body; the book on the harness, its state root holding the pin."""

    def harness(self, *, E_: str = E, state: str = "state", **kw) -> PinHarness:
        state_dir = self.root / state
        state_dir.mkdir(exist_ok=True)
        h = PinHarness(state_dir, self.root, E=E_, cash="20000", **kw)
        self.addCleanup(h.state.close)
        return h

    def size(self, h, inst, *, symbol="SPY", day=None) -> L.Z.SizingInputs | None:
        before = len(T.SIZED)
        intent = h.intent(inst, "buy", symbol=symbol, share="0.5")
        sized = h.book._size(intent, inst, symbol, "etf", D("100"), None, (day or T.MONDAY).isoformat())
        self.last_intent = h.get_intent(intent.iid)
        done = h.get_intent(intent.iid)
        done.status = "done"                         # measured only: never worked by a later tick
        h.book._save_intent(done)
        if sized is None:
            self.assertEqual(len(T.SIZED), before, "nothing reached size_entry")
            return None
        return T.SIZED[-1]

    def closed_lot(self, h, inst, cash, *, day="2026-10-09", rung=None, scaled=False, closed_at=None, probe=None):
        info = {}
        if rung:
            info[B.RUNG_INFO] = rung
        if scaled:
            info[B.SCALED_INFO] = True
        lot = L.Lot(h.book._next("eq_lots", "lid"), inst.id, inst.family, inst.version, inst.lane, "SPY", "etf", D("1"),
                    D("1"), D("500"), D("500"), "open", opened_at=T.at(T.FRIDAY, 9, 31), opened_day="2026-10-09",
                    status=L.LOT_CLOSED, exit_px=D("500"), exit_at="close", exit_day=day,
                    closed_at=closed_at if closed_at is not None else h.clock(), cash=D(cash), reason="program",
                    probe=(not scaled) if probe is None else probe, info=info)
        h.book._save_lot(lot)
        return lot

    def open_lot(self, h, inst, *, value="1000", rung=None, scaled=False):
        lot = h.lot(inst, "SPY", str(D(value) / D("500")), "500", probe=not scaled)
        if rung or scaled:
            lot.info = {**({B.RUNG_INFO: rung} if rung else {}), **({B.SCALED_INFO: True} if scaled else {})}
            h.book._save_lot(lot)
        return lot

    # -- dark
    def test_dark_reads_no_rung_and_never_asks_the_pin_for_one(self):
        pin(self.root, {KEY_A: 2})
        h = self.harness()
        inst = h.instance("fam-a")
        with band(""), mock.patch.object(L, "read_probe_pin", side_effect=AssertionError("asked")):
            self.assertIs(h.book._scale_for(inst, D(E)), L.SCALE_PROBE)
            h.book._scale_now()
            self.assertEqual(h.book.scaled()["state"], "dark")
        with band(""):
            self.assertEqual(self.size(h, inst).sleeve_equity, D("0.25") * D(E_P), "C2's frozen Probe sleeve")
        self.assertIsNone(h.state.get(L.SCALE_KEY))

    # -- a matching pin: the sleeve, the lower of pin and setting, R1 without the lines
    def test_r1_sizes_on_the_pins_e_p_with_the_probe_mark_in_the_lines_in_force(self):
        sha = pin(self.root, {KEY_A: 1})
        h = self.harness()
        inst = h.instance("fam-a")
        with band(sha):
            x = self.size(h, inst)
            self.assertEqual(x.sleeve_equity, D("0.50") * D(E_P), "R1: 0.50 x E_P")
            self.assertEqual(x.budget_room, h.book._budget_room(T.MONDAY.isoformat()), "the Probe room: inside the lines")
            self.assertEqual(x.E, D(E), "the walls stay on E")
            h.intent(inst, "buy", symbol="SPY", share="0.5")
            h.tick(9, 31)
        [order] = [o for o in h.orders() if o.side == "buy"]
        self.assertEqual((order.probe, order.scaled, order.answer.get("rung")), (True, False, 1))
        [lot] = h.lots()
        self.assertEqual((lot.probe, lot.info), (True, {B.RUNG_INFO: 1}), "Probe-marked, its rung kept")
        self.assertEqual(h.state.rows("SELECT probe FROM eq_orders WHERE side='buy'")[0]["probe"], 1)

    def test_without_the_scaled_lines_nothing_goes_past_r1(self):
        sha = pin(self.root, {KEY_A: 5})
        h = self.harness()
        inst = h.instance("fam-a")
        with band(sha):
            self.assertEqual(h.book._scale_for(inst, D(E)), L.ScaleRung(1, D("1000.00"), False, None))

    def test_the_lower_of_the_pins_rung_and_the_setting(self):
        sha = pin(self.root, {KEY_A: 3})
        h = self.harness()
        inst = h.instance("fam-a")
        with band(sha, lines=True):
            self.assertEqual(h.book._scale_for(inst, D("20000")).rung, 3, "no word from the swarm: the pin alone")
            h.families.scale = {"rung": 5, "programs": {KEY_A: 2}}
            self.assertEqual(h.book._scale_for(inst, D("20000")).rung, 2)
            h.families.scale = {"rung": 1, "programs": {KEY_A: 4}}
            self.assertEqual(h.book._scale_for(inst, D("20000")).rung, 1, "a setting may only lower")
            h.families.scale = {"rung": 0, "programs": {}}
            self.assertIs(h.book._scale_for(inst, D("20000")), L.SCALE_PROBE, "stop the ladder")
            h.families.scale_setting = mock.Mock(side_effect=OSError("unreadable"))
            self.assertIs(h.book._scale_for(inst, D("20000")), L.SCALE_PROBE, "an unreadable setting: Probe")
            del h.families.scale_setting
            h.families.scale = {"rung": 5, "programs": {}}
            self.assertIs(h.book._scale_for(inst, D("20000")), L.SCALE_PROBE,
                          "THE RATCHET: the setting put back raises nothing under the same pin")
            self.assertEqual(h.state.get(L.SCALE_KEY)["ratchet"], {"sha256": sha, "rungs": {KEY_A: 0}, "caps": {KEY_A: 5}})
        sha2 = pin(self.root, {KEY_A: 3}, rungs_at="later")             # a new pin (Blake's deploy): a raise again
        with band(sha2, lines=True):
            self.assertEqual(h.book._scale_for(inst, D("20000")).rung, 3)

    def test_the_ratchet_learns_lowerings_only(self):
        """The review of C3: a cap already there when a pin is first read holds while it is there and is not learned; the
        lines switched on later raise nothing; an unreadable setting sizes at Probe that minute and teaches nothing; a
        lowering while the program holds no seat sticks too."""
        sha = pin(self.root, {KEY_A: 2, KEY_B: 2})
        h = self.harness()
        a = h.instance("fam-a")
        h.families.scale = {"rung": 5, "programs": {KEY_A: 1}}
        with band(sha, lines=True):
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 1, "the cap holds while it is there")
            h.families.scale = {"rung": 5, "programs": {}}
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 2, "a cap from before the pin is not learned")
            h.families.scale_setting = mock.Mock(side_effect=OSError("unreadable"))
            self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE, "unreadable: Probe this minute")
            del h.families.scale_setting
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 2, "and nothing learned from it")
            h.book._scale_now()                                        # fam-b, seatless, read at R2
            h.families.scale = {"rung": 5, "programs": {KEY_B: 0}}       # lowered while it holds no seat: learned
            h.book._scale_now()
            h.families.scale = {"rung": 5, "programs": {}}
            h.book._scale_now()
            b = h.instance("fam-b")
            self.assertIs(h.book._scale_for(b, D(E)), L.SCALE_PROBE, "a lowering while off its seat sticks")
        sha2 = pin(self.root, {KEY_A: 2}, rungs_at="r2")
        with band(sha2):
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 1, "read without the lines: R1")
        with band(sha2, lines=True):
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 1, "the lines switched on later raise nothing")
        sha3 = pin(self.root, {KEY_A: 2}, rungs_at="r3")
        with band(sha3, lines=True):
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 2, "only a new pin")

    def test_a_memory_that_cannot_be_read_fails_closed_and_is_never_written_over(self):
        sha = pin(self.root, {KEY_A: 1})
        h = self.harness()
        a = h.instance("fam-a")
        h.state.execute("INSERT INTO kv(key, value) VALUES(?, ?)", (L.SCALE_KEY, "{not json"))
        with band(sha):
            self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE)
            h.book._scale_now()
            h.book._scale_now()
            self.assertEqual(self.size(h, a).sleeve_equity, D("0.25") * D(E_P), "Probe: no rung")
            self.assertEqual(h.state.rows("SELECT value FROM kv WHERE key=?", (L.SCALE_KEY,))[0]["value"], "{not json")
            self.assertEqual(h.book.scaled()["state"], "memory")
            [alert] = h.standing()
            self.assertTrue(alert["began_at"], "a standing condition, dated its first minute (the watch inherits it)")
            h.clock.set(h.clock() + 3600)
            h.restart()
            h.book._scale_now()
            self.assertEqual([a["began_at"] for a in h.standing()], [alert["began_at"]] * 2, "kept across restarts")
        from league.ops.preopen import check_equity
        from league.tests.test_equity_money import ThePreopenEquityCheck

        house = ThePreopenEquityCheck("test_each_fault_fails").house()
        with band(sha):
            house["release"]["live"]["equity"] = {"frozen": "", "scaled": h.book.scaled()}
        self.assertFalse(check_equity(house).ok)

    def test_an_unread_setting_minute_is_no_rung_change(self):
        """The review of C3 (round two): an unreadable setting sizes at Probe for that minute but moves neither the
        program line's "since the last change" nor the ratchet, nor the window's reading."""
        sha = pin(self.root, {KEY_A: 2})
        h = self.harness()
        a = h.instance("fam-a")
        with band(sha, lines=True):
            h.book._scale_now()
            since = h.state.get(L.SCALE_KEY)["programs"][KEY_A]["since_at"]
            h.clock.set(h.clock() + 120)
            h.families.scale_setting = mock.Mock(side_effect=OSError("unreadable"))
            self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE)
            h.book._scale_now()
            del h.families.scale_setting
            h.clock.set(h.clock() + 120)
            h.book._scale_now()
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 2)
            row = h.state.get(L.SCALE_KEY)["programs"][KEY_A]
            self.assertEqual((row["since_at"], row["rung"]), (since, 2), "no change noted for the unread minute")
            self.assertFalse(h.state.get(L.SCALE_KEY).get("window"))

    def test_a_memory_row_gone_once_written_is_no_fresh_start(self):
        sha = pin(self.root, {KEY_A: 1})
        h = self.harness()
        a = h.instance("fam-a")
        with band(sha):
            h.book._scale_now()
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 1)
            h.state.execute("DELETE FROM kv WHERE key=?", (L.SCALE_KEY,))
            self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE, "gone after it was written: unreadable")
            h.book._scale_now()
            self.assertEqual(h.book.scaled()["state"], "memory")
            self.assertEqual(h.state.rows("SELECT key FROM kv WHERE key=?", (L.SCALE_KEY,)), [], "never written over")
            from league.ops.preopen import check_equity
            from league.tests.test_equity_money import ThePreopenEquityCheck

            house = ThePreopenEquityCheck("test_each_fault_fails").house()
            house["release"]["live"]["equity"] = {"frozen": "", "scaled": h.book.scaled()}
            check = check_equity(house)
            self.assertFalse(check.ok)
            self.assertIn("the Scaled band's memory cannot be read", check.headline())
            # Removing both keys on purpose is the one fresh start; the owner is told it reads again.
            h.state.execute("DELETE FROM kv WHERE key=?", (L.SCALE_SEEN_KEY,))
            h.book._scale_now()
            self.assertEqual(h.book.scaled()["state"], "matched")
            self.assertIn("matches its row again", " ".join(t for lvl, t in h.alerts if lvl == "warning"))

    def test_d3_reads_everything_realized_since_r1_whatever_its_marks(self):
        """Plan 3.4 (the third review): both program lines read EVERY real lot of the program version closed since the
        change and since R1, whatever its marks: a Probe lot opened before R1 and closed after it counts in both."""
        sha = pin(self.root, {KEY_A: 2})
        h = self.harness()
        a = h.instance("fam-a")
        before_r1 = self.open_lot(h, a, value="500")                  # a Probe lot opened before any rung
        with band(sha, lines=True):
            h.book._scale_now()                                         # R2: sleeve 2,500, line -250
            self.closed_lot(h, a, "-200", rung=2, scaled=True, closed_at=h.clock() + 1)
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 2, "-200 is inside -250")
            lot = h.book._lot(before_r1.lid)
            lot.status, lot.qty, lot.cash, lot.exit_day = L.LOT_CLOSED, D(0), D("-60"), "2026-10-12"
            lot.closed_at = h.clock() + 2
            h.book._save_lot(lot)
            self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE, "the Probe lot's -60 counts: -260 since the change")
            self.assertIn(KEY_A, h.state.get(L.SCALE_KEY)["out"])

    def test_w12_a_plan_d6_closed_stays_closed_whatever_pins_follow(self):
        """The third review's W12: D6 closes plan A, a pin of plan B reopens the ladder (loudly), D6 closes B; a pin of
        plan A again finds A closed: Probe."""
        h = self.harness()
        a = h.instance("fam-a")

        def d6(plan):
            sha = pin(self.root, {KEY_A: 2}, plan=plan)
            with band(sha, lines=True):
                h.clock.set(h.clock() + 60)
                h.book._scale_now()
                self.assertEqual(h.book._scale_for(a, D(E)).rung, 2, plan[:2])
                for _ in range(4):                     # losses of a seatless earlier program: D6, not D3
                    lot = L.Lot(h.book._next("eq_lots", "lid"), L.instance_key("fam-z", 1), "fam-z", 1, "equity",
                                "SPY", "etf", D("1"), D("1"), D("500"), D("500"), "open",
                                opened_at=T.at(T.FRIDAY, 9, 31), opened_day="2026-10-09", status=L.LOT_CLOSED,
                                exit_px=D("280"), exit_at="close", exit_day="2026-10-09", closed_at=h.clock() + 1,
                                cash=D("-240"), reason="program", probe=False, info={B.RUNG_INFO: 2, B.SCALED_INFO: True})
                    h.book._save_lot(lot)
                h.clock.set(h.clock() + 60)
                h.book._scale_now()
                self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE, f"D6 closed {plan[:2]}")
            return sha

        d6("aa" * 32)
        d6("bb" * 32)
        self.assertEqual(sorted(h.state.get(L.SCALE_KEY)["closed"]), ["aa" * 32, "bb" * 32])
        self.assertEqual(sum("REOPENED" in x["text"] for x in h.standing()), 1, "plan B's reopening, loudly")
        sha = pin(self.root, {KEY_A: 2}, plan="aa" * 32, rungs_at="again")
        with band(sha, lines=True):
            h.clock.set(h.clock() + 60)
            h.book._scale_now()
            self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE, "plan A, once closed, stays closed")
            self.assertTrue(h.book.scaled()["closed"])

    def test_plan_9_under_a_set_row_the_pool_sizes_on_the_last_matching_pins_e_p(self):
        """Plan 9 (the third review): with the row set and a pin there that does not match it, Probe and the panel size
        on min(E, the E_P of the last pin that matched), never the mismatched pin's; with none ever matched, every open
        is refused House-wide; dark, C2's freeze follows any readable pin as before."""
        sha = pin(self.root, {KEY_A: 0})
        h = self.harness()
        b = h.instance("fam-b")
        with band(sha):
            self.assertEqual(self.size(h, b).sleeve_equity, D("0.25") * D(E_P), "a matching pin: its E_P")
        pin(self.root, {}, e_p="4000")                                 # another readable pin, a larger E_P
        with band(sha):
            self.assertEqual(self.size(h, b).sleeve_equity, D("0.25") * D(E_P), "the last matching pin's E_P, not 4000")
            budget, sleeve = h.book._panel_budget(L.replace(h.instance("fam-p"), kind="panel"), T.MONDAY.isoformat(), [])
            self.assertLessEqual(sleeve, D("0.10") * D(E_P))
        with band(""):
            self.assertEqual(self.size(h, b).sleeve_equity, D("0.25") * D("4000"), "dark: C2's freeze reads the pin there")
        fresh = self.harness(state="fresh")
        c = fresh.instance("fam-c")
        with band(sha):
            self.assertIsNone(self.size(fresh, c), "no matching pin ever read on this box: nothing sized")
            self.assertEqual(fresh.get_intent(self.last_intent.iid).why, L.SCALE_POOL_REFUSAL)
            no_block = (lambda opening=True: None)
            self.assertEqual(fresh.book._open_block(no_block, c, killed=lambda: False), L.SCALE_POOL_REFUSAL)
        with band(""):
            self.assertIsNone(fresh.book._open_block(no_block, c, killed=lambda: False), "dark: C2's rule")

    def test_the_production_unread_marker_teaches_nothing(self):
        """The third review's W11 (mutant M22): the families reader's own `unread` answer (elane.SCALE_CLOSED) sizes at
        Probe that minute, moves no "since", and the rung comes back with the setting."""
        from league.swarm import elane

        sha = pin(self.root, {KEY_A: 2})
        h = self.harness()
        a = h.instance("fam-a")
        with band(sha, lines=True):
            h.book._scale_now()
            since = h.state.get(L.SCALE_KEY)["programs"][KEY_A]["since_at"]
            h.clock.set(h.clock() + 120)
            h.families.scale = dict(elane.SCALE_CLOSED)
            self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE)
            h.book._scale_now()
            h.families.scale = {"rung": 5, "programs": {}}
            h.clock.set(h.clock() + 120)
            h.book._scale_now()
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 2, "nothing learned from the unread minute")
            self.assertEqual(h.state.get(L.SCALE_KEY)["programs"][KEY_A]["since_at"], since)

    def test_public_alerts_name_no_program_and_no_rung(self):
        sha = pin(self.root, {KEY_A: 1})
        h = self.harness()
        a = h.instance("fam-a")
        with band(sha):
            h.book._scale_now()
            self.closed_lot(h, a, "-300.01", rung=1, closed_at=h.clock() + 1)
            h.book._scale_now()
        texts = [t for _, t in h.alerts] + [x["text"] for x in h.standing()]
        self.assertTrue(any("D3" in t for t in texts))
        self.assertFalse(any("fam-a" in t or KEY_A in t or "R1" in t for t in texts), texts)
        [record] = [p for k, p in h.events if k == "equity.scale" and p.get("event") == "program_line"]
        self.assertEqual(record["program"], KEY_A, "the private record names it")

    def test_d3_at_the_sizing_itself(self):
        sha = pin(self.root, {KEY_A: 1})
        h = self.harness()
        a = h.instance("fam-a")
        with band(sha):
            h.book._scale_now()
            self.closed_lot(h, a, "-300.01", rung=1, closed_at=h.clock() + 1)   # an exit of this very minute
            self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE, "sent back before its entry, not next minute")
            self.assertIn(KEY_A, h.state.get(L.SCALE_KEY)["out"])

    def test_a_rung_change_during_an_entry_sends_no_more_shares_under_other_marks(self):
        sha = pin(self.root, {KEY_A: 2})
        h = self.harness()
        a = h.instance("fam-a")
        with band(sha, lines=True):
            it = h.intent(a, "buy", symbol="SPY", share="0.5")
            h.venue.fill = "partial"
            h.tick(9, 31)
            h.tick(9, 32)
            self.assertGreater(sum((o.filled_qty for o in h.orders()), D(0)), 0)
            h.families.scale = {"rung": 1, "programs": {}}
            for mm in range(33, 46):
                h.tick(9, mm)
        buys = [o for o in h.orders() if o.side == "buy"]
        self.assertTrue(all(o.scaled and o.answer.get("rung") == 2 for o in buys), "no buy under another mark")
        self.assertEqual(h.get_intent(it.iid).status, "done")
        self.assertIn("rung changed during the entry", h.get_intent(it.iid).why)

    def test_the_sleeve_never_goes_above_half_of_e_and_never_through_c2s_pool(self):
        sha = pin(self.root, {KEY_A: 5})
        h = self.harness(E_="6000")
        inst = h.instance("fam-a")
        probe = h.instance("fam-b")
        with band(sha, lines=True):
            self.assertEqual(self.size(h, inst).sleeve_equity, D("3000.00"), "6.75 x E_P is above 0.50 x E")
            h.E = D("40000")
            self.assertEqual(self.size(h, inst).sleeve_equity, D("13500.0000"), "6.75 x E_P")
            with mock.patch.object(L.EquityBook, "_sleeve_equity", return_value=D("1")):
                self.assertEqual(self.size(h, inst).sleeve_equity, D("13500.0000"), "the pin's E_P, not the pool's")
                self.assertEqual(self.size(h, probe).sleeve_equity, D("0.25"), "a Probe program on the pool")

    def test_no_rung_for_a_panel_a_sized_program_a_newer_version_or_a_program_the_pin_does_not_name(self):
        sha = pin(self.root, {KEY_A: 2, L.program_key("fam-s", 1): 2, L.program_key("fam-p", 1): 2})
        h = self.harness()
        sized = h.instance("fam-s", band="sized")
        panel = L.replace(h.instance("fam-p"), kind="panel")
        h.book._save_instance(panel)
        newer = h.instance("fam-a", version=2)
        other = h.instance("fam-c")
        with band(sha, lines=True):
            for inst in (sized, panel, newer, other):
                self.assertIs(h.book._scale_for(inst, D(E)), L.SCALE_PROBE, inst.id)

    def test_the_decide_view_shows_the_rungs_sleeve(self):
        sha = pin(self.root, {KEY_A: 1})
        h = self.harness()
        inst = h.instance("fam-a")
        bars = {"raw": {"SPY": [{"t": "2026-10-09", "c": "100"}]}, "all": {"SPY": [{"t": "2026-10-09", "c": "100"}]},
                "shas": {}}
        with band(sha):
            inputs, _ = h.book._inputs(inst, T.MONDAY, {"symbols": ["SPY"], "history": 0}, bars)
        self.assertEqual(inputs["budget"], float(D("0.50") * D(E_P)))
        self.assertEqual(inputs["caps"]["SPY"], float(D("0.50") * D("0.50") * D(E_P)), "half the sleeve in one ETF")

    # -- a pin that does not match: no new Scaled lot
    def test_a_pin_that_does_not_match_refuses_a_program_last_read_at_a_rung_and_sizes_the_rest_at_probe(self):
        sha = pin(self.root, {KEY_A: 1})
        h = self.harness()
        a, b = h.instance("fam-a"), h.instance("fam-b")
        with band(sha):
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 1)
        pin(self.root, {KEY_A: 1}, extra_field=1)              # another pin: not the row's sha
        with band(sha):
            self.assertIsNone(self.size(h, a), "no new Scaled lot")
            self.assertTrue(h.get_intent(self.last_intent.iid).why.startswith(L.SCALE_REFUSAL))
            self.assertEqual(self.size(h, b).sleeve_equity, D("0.25") * D(E_P), "every other program at Probe")
            h.book._scale_now()
            h.book._scale_now()
            [alert] = h.standing()
            self.assertEqual(alert["level"], "error")
            self.assertIn("does not match", alert["text"])
            state = h.book.scaled()
            self.assertEqual((state["state"], state["since"]), ("mismatch", alert["began_at"]))
            # the pin removed, or unreadable, is a mismatch the same way
            (self.root / L.PROBE_PIN_FILE).unlink()
            self.assertIsNone(self.size(h, a))
        from league.ops.preopen import check_equity
        from league.tests.test_equity_money import ThePreopenEquityCheck

        house = ThePreopenEquityCheck("test_each_fault_fails").house()
        house["release"]["live"]["equity"] = {"frozen": "", "scaled": state}
        check = check_equity(house)
        self.assertFalse(check.ok)
        self.assertIn("the scaling pin does not match its row", check.headline())
        house["release"]["live"]["equity"] = {"frozen": "", "scaled": {"state": "dark", "why": ""}}
        self.assertTrue(check_equity(house).ok)

    def test_no_figure_is_said(self):
        sha = pin(self.root, {KEY_A: 2}, e_p="2345.67")
        h = self.harness()
        inst = h.instance("fam-a")
        with band(sha, lines=True):
            h.book._scale_now()
            self.size(h, inst)
            texts = [json.dumps(h.book.scaled()), json.dumps(h.events, default=str), json.dumps(h.alerts)]
        for figure in ("2345", "5862", "2500", sha):
            self.assertFalse(any(figure in t for t in texts), figure)

    # -- the Scaled mark, from the yes
    def test_a_scaled_buy_and_lot_carry_the_scaled_mark_sized_to_the_scaled_room(self):
        sha = pin(self.root, {KEY_A: 2})
        h = self.harness()
        inst = h.instance("fam-a")
        with band(sha, lines=True):
            x = self.size(h, inst)
            self.assertEqual(x.sleeve_equity, D("2500.00"), "min(1.25 x E_P, 0.50 x E)")
            self.assertEqual(x.budget_room, D("0.18") * D("2500.00"), "the Scaled window's room, nothing realized")
            h.intent(inst, "buy", symbol="SPY", share="0.5")
            h.tick(9, 31)
            [order] = [o for o in h.orders() if o.side == "buy"]
            self.assertEqual((order.probe, order.scaled, order.answer.get("rung")), (False, True, 2))
            self.assertEqual(h.state.rows("SELECT probe FROM eq_orders WHERE side='buy'")[0]["probe"], L.SCALED_MARK)
            [lot] = h.lots()
            self.assertEqual((lot.probe, lot.info), (False, {B.RUNG_INFO: 2, B.SCALED_INFO: True}))
            weights = {"etf": D("0.20"), "stock": D("0.40")}
            self.assertEqual(L.probe_figures(h.state.rows, weights=weights).open_risk, D(0),
                             "its open risk leaves the Probe room")
            self.assertEqual(L.probe_figures(h.state.rows, weights=weights).programs, 1, "it keeps its slot")
            room = h.book._scaled_room(T.MONDAY.isoformat(), D(E))
            self.assertEqual(room.open_risk, D("0.20") * lot.value, "it counts in the Scaled lines")
        self.assertEqual(L.probe_figures(h.state.rows, weights=weights).open_risk, D("0.20") * lot.value,
                         "without the lines in force it counts in the Probe room (fail closed)")
        with band("", lines=True):
            self.assertEqual(L.probe_figures(h.state.rows, weights=weights).open_risk, D("0.20") * lot.value,
                             "the band made dark again with the lines still in force: the Probe room holds it")

    def test_a_scaled_working_buy_and_a_scaled_close(self):
        sha = pin(self.root, {KEY_A: 2})
        h = self.harness()
        a, b = h.instance("fam-a"), h.instance("fam-b")
        weights = {"etf": D("0.20"), "stock": D("0.40")}
        with band(sha, lines=True):
            h.venue.fill = "none"
            h.intent(a, "buy", symbol="SPY", share="0.5")
            h.tick(9, 31)
            [order] = [o for o in h.orders() if o.side == "buy" and o.working]
            self.assertTrue(order.scaled)
            self.assertEqual(L.probe_figures(h.state.rows, weights=weights).open_risk, D(0), "a Scaled buy too")
            self.assertEqual(L.probe_figures(h.state.rows, weights=weights, scaled_lines=False).open_risk,
                             D("0.20") * order.remaining * order.limit_px)
            scaled = self.closed_lot(h, a, "-120", rung=2, scaled=True)
            r1 = self.closed_lot(h, b, "-30", rung=1)
            figures = L.probe_figures(h.state.rows, weights=weights)
            self.assertEqual([c for _, c in figures.closes], [D("-30")], "a Scaled close is no Probe close; R1's is")
            room = h.book._scaled_room(T.MONDAY.isoformat(), D(E))
            self.assertEqual((room.window, room.total), (D("120"), D("120")), "it counts in the Scaled lines")
            self.assertEqual(h.book._record_of("fam-a", 1, None).realized_net, D(0), "EDM1 leaves it out")
            self.assertEqual(h.book._record_of("fam-b", 1, None).realized_net, D("-30"), "and reads R1's")
        self.assertEqual(sorted(c for _, c in L.probe_figures(h.state.rows, weights=weights).closes),
                         [D("-120"), D("-30")], "without the lines in force a Scaled close is a Probe close")
        self.assertTrue(scaled.lid and r1.lid)

    # -- the House's own step-downs
    def test_d3_the_program_line_since_the_change_at_r1_and_from_r2(self):
        sha = pin(self.root, {KEY_A: 1, KEY_B: 2})
        h = self.harness()
        a, b = h.instance("fam-a"), h.instance("fam-b")
        with band(sha, lines=True):
            h.book._scale_now()
            self.closed_lot(h, a, "-150", rung=1, closed_at=h.clock() + 1)
            self.closed_lot(h, a, "-140", rung=1, closed_at=h.clock() + 2)
            self.closed_lot(h, a, "-400", closed_at=h.clock() - 3600, probe=True)     # closed before R1: not read
            self.closed_lot(h, b, "-249.99", rung=2, scaled=True, closed_at=h.clock() + 4)
            h.book._scale_now()
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 1, "-290 is inside -300")
            self.assertEqual(h.book._scale_for(b, D(E)).rung, 2, "-249.99 is inside -10% of 2,500")
            self.closed_lot(h, a, "-10", rung=1, closed_at=h.clock() + 5)
            self.closed_lot(h, b, "-0.01", rung=2, scaled=True, closed_at=h.clock() + 6)
            h.book._scale_now()
            self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE, "R1's line, -300 since the change: out")
            self.assertIs(h.book._scale_for(b, D(E)), L.SCALE_PROBE, "R2's line, -10% of the sleeve: out")
            mem = h.state.get(L.SCALE_KEY)
            self.assertEqual(sorted(mem["out"]), [KEY_A, KEY_B])
            self.assertEqual([p["event"] for k, p in h.events if k == "equity.scale" and "event" in p],
                             ["program_line", "program_line"])
            pin(self.root, {KEY_A: 2, KEY_B: 3})          # a new pin naming them again: out for good
        with band(hashlib.sha256((self.root / L.PROBE_PIN_FILE).read_bytes()).hexdigest(), lines=True):
            self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE)
            self.assertIs(h.book._scale_for(b, D(E)), L.SCALE_PROBE)

    def test_d3_the_cumulative_line_never_resets_across_a_rung_change(self):
        sha = pin(self.root, {KEY_A: 3})
        h = self.harness(E_="20000")
        a = h.instance("fam-a")
        with band(sha, lines=True):
            h.book._scale_now()                            # R3: sleeve 4,500, line -450
            self.closed_lot(h, a, "-400", rung=3, scaled=True, closed_at=h.clock() + 1)
            h.families.scale = {"rung": 2, "programs": {}}  # the captain steps it down: the change resets "since"
            h.clock.set(h.clock() + 10)
            h.book._scale_now()
            self.assertEqual(h.book._scale_for(a, D("20000")).rung, 2)
            self.closed_lot(h, a, "-60", rung=2, scaled=True, closed_at=h.clock() + 1)
            h.book._scale_now()
            self.assertIs(h.book._scale_for(a, D("20000")), L.SCALE_PROBE,
                          "-460 since R1 is past the line of R3, the highest it reached (-450); -60 alone is inside R2's")

    def test_d5_and_d6(self):
        sha = pin(self.root, {KEY_A: 2, KEY_B: 2})
        h = self.harness()
        a, b = h.instance("fam-a"), h.instance("fam-b")
        with band(sha, lines=True):
            h.book._scale_now()                            # two R2 sleeves: 5,000 in force, the window 900, total 1,800
            mem = h.state.get(L.SCALE_KEY)
            self.assertEqual(D(mem["peak_usd"]), D("5000.00"))
            self.open_lot(h, a, value="4600", rung=2, scaled=True)         # 920 of open risk: the window is reached
            h.book._scale_now()
            self.assertIsNotNone(self.size(h, b))
            self.assertLessEqual(T.SIZED[-1].budget_room, 0, "D5: no Scaled open fits: Scaled opens pause")
            self.assertTrue(h.state.get(L.SCALE_KEY)["window"])
            self.assertIn("D5", " ".join(t for _, t in h.alerts))
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 2, "D5 lowers no rung by itself (the captain's setting)")
            # D6: the Scaled closes' net loss reaches 0.36 x the largest sleeves reached (1,800).
            for i, (inst, cash) in enumerate(((a, "-240"), (b, "-240"), (a, "-240"), (b, "-240"), (a, "-240"),
                                              (b, "-240"), (a, "-200"), (b, "-160"))):
                self.closed_lot(h, inst, cash, rung=2, scaled=True, day=f"2026-10-0{1 + i % 9}",
                                closed_at=h.clock() - 86400 * 30)            # before the rung's "since": no D3
            h.book._scale_now()
            mem = h.state.get(L.SCALE_KEY)
            self.assertEqual(sorted(mem["closed"]), [PLAN])
            self.assertIs(h.book._scale_for(a, D(E)), L.SCALE_PROBE, "D6: every program back to Probe")
            self.assertIs(h.book._scale_for(b, D(E)), L.SCALE_PROBE)
            self.assertIn("D6", " ".join(t for lvl, t in h.alerts if lvl == "error"))
        sha2 = pin(self.root, {KEY_A: 2}, plan="cd" * 32)
        with band(sha2, lines=True):
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 2, "a new pinned version of the plan reopens it")
            h.clock.set(h.clock() + 60)
            h.book._scale_now()
            mem = h.state.get(L.SCALE_KEY)
            self.assertEqual(mem["plans"], [PLAN, "cd" * 32])
            self.assertIn("REOPENED", " ".join(a["text"] for a in h.standing()), "loud: an error-level standing alert")
            self.assertEqual(h.book._scale_for(a, D(E)).rung, 2, "its total starts again: the old closes are not its")
            room = h.book._scaled_room(T.MONDAY.isoformat(), D(E))
            self.assertEqual((room.total, room.window), (D(0), D(0)), "the window too: the old version's closes are not its")


class TheFamilyLine(unittest.TestCase):
    """league/swarm/elane.py `loss_line` reads Probe-marked lots only with the yes and its third part, every lot
    otherwise, an R1 lot always; an unreadable book leaves nothing out."""

    def setUp(self):
        from league.swarm.store import SwarmStore
        from league.tests.swarm_fakes import Clock

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = SwarmStore(self.root, clock=Clock())
        self.addCleanup(self.store.close)
        self.store.add_family({"id": "fam-a", "mechanism": "Hold the ETF overnight.", "structure": "etf",
                               "roots": ["SPY"], "symbols": ["SPY"], "lane": "beta"}, origin="seed")
        db = sqlite3.connect(self.root / "live.sqlite")
        db.execute("CREATE TABLE eq_lots (lid INTEGER PRIMARY KEY, family TEXT, cash TEXT, info TEXT)")
        db.executemany("INSERT INTO eq_lots VALUES (?, ?, ?, ?)",
                       [(1, "fam-a", "-400", json.dumps({B.RUNG_INFO: 2, B.SCALED_INFO: True})),
                        (2, "fam-a", "-100", json.dumps({B.RUNG_INFO: 1})), (3, "fam-a", "-150", "{}"),
                        (5, "fam-a", "-20.00", json.dumps({B.RUNG_INFO: 2, B.SCALED_INFO: True}))])
        db.commit()
        db.close()
        self.store.add_forward("fam-a", "real", [{"id": "eq-1", "day": "2026-10-13", "pnl": -400.0, "max_loss": 600.0},
                                                 {"id": "eq-2", "day": "2026-10-13", "pnl": -100.0, "max_loss": 600.0},
                                                 {"id": "eq-3", "day": "2026-10-14", "pnl": -150.0, "max_loss": 600.0}])

    def line(self):
        from league.swarm import elane

        return elane.loss_line(self.store, self.store.family("fam-a"), {})

    def test_each_case(self):
        from league.swarm import elane

        self.assertEqual(self.line(), elane.LOSS_LINE, "dark: every lot (-650)")
        with band("a" * 64, lines=True, probe_only=False):
            self.assertEqual(self.line(), elane.LOSS_LINE, "his no to the third part: every lot")
        with band("a" * 64, lines=True, probe_only=True):
            self.assertIsNone(self.line(), "Probe-marked lots only: R1's -100 and a Probe -150")
            self.assertEqual(elane.scaled_trades(self.store, "fam-a"), {"eq-1": -400.0, "eq-5": -20.0})
            # eq-5's row is not its Scaled lot's cash (a book restored with its ids reused): the row stays in.
            self.store.add_forward("fam-a", "real", [{"id": "eq-5", "day": "2026-10-15", "pnl": -60.0, "max_loss": 1.0}])
            self.assertEqual(self.line(), elane.LOSS_LINE, "-310: a row whose P&L is not the Scaled lot's stays in")
            (self.root / "live.sqlite").write_bytes(b"not a database")
            self.assertEqual(elane.scaled_trades(self.store, "fam-a"), {}, "unreadable: nothing left out")
        with band("a" * 64, lines=False, probe_only=True):
            self.assertEqual(elane.scaled_trades(self.store, "fam-a"), {}, "only with the lines in force")


class TheSetting(unittest.TestCase):
    def setUp(self):
        from league.swarm import elane

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.elane = elane
        elane._scale_good.clear()

    def write(self, doc):
        (self.root / "swarm.json").write_text(json.dumps(doc) if not isinstance(doc, str) else doc, encoding="utf-8")

    def test_it_may_only_lower_and_fails_closed(self):
        e = self.elane
        self.assertEqual(e.scale_setting(self.root), {"rung": 5, "programs": {}}, "no file: the policy's default")
        self.assertNotIn("scale", e.cfg({"elane": {"scale": {"rung": 9}}}), "cfg never reads it: only scale_setting")
        self.write({"elane": {"scale": {"rung": 2, "programs": {KEY_A: 0}}}})
        self.assertEqual(e.scale_setting(self.root), {"rung": 2, "programs": {KEY_A: 0}})
        for bad in ({"rung": 6}, {"rung": -1}, {"rung": True}, {"rung": 1.0}, {"programs": {"fam-a": 1}},
                    {"programs": {KEY_A: 9}}, [1], "x"):
            self.assertIsNone(e.scale_block(bad), bad)
            self.write({"elane": {"scale": bad}})
            self.assertEqual(e.scale_setting(self.root), {"rung": 2, "programs": {KEY_A: 0}}, f"the last good: {bad}")
        self.write("{not json")
        self.assertEqual(e.scale_setting(self.root), {"rung": 2, "programs": {KEY_A: 0}})
        e._scale_good.clear()
        self.assertEqual(e.scale_setting(self.root), e.SCALE_CLOSED, "never read a good one: every rung 0")
        self.write({"elane": {"roster": 3}})
        self.assertEqual(e.scale_setting(self.root), {"rung": 5, "programs": {}}, "no scale block: the policy's")

    def test_the_books_reader(self):
        from league.equity.families import EquityFamilies

        self.write({"elane": {"scale": {"rung": 1}}})
        self.assertEqual(EquityFamilies(self.root).scale_setting(), {"rung": 1, "programs": {}})
        with mock.patch.object(self.elane, "scale_setting", side_effect=RuntimeError("x")):
            self.assertEqual(EquityFamilies(self.root).scale_setting(), {"rung": 0, "programs": {}, "unread": True})
        with mock.patch("league.swarm.settings.read_policy", side_effect=OSError("x")):
            self.assertEqual(self.elane.scale_setting(self.root / "nowhere"), self.elane.SCALE_CLOSED,
                             "a policy that cannot be read: closed, never the default (the review)")


class TheIdentities(unittest.TestCase):
    def test_no_file_of_c3_is_hashed_by_either_identity(self):
        """The options fingerprint (league/live/, the Gym, `LEAGUE_FILES`) and the equity identity (league/equity's
        evidence modules) hash none of the files C3 edits: neither moves (`b60410ad`, `78022ca6`)."""
        from league.gym.driver import LEAGUE_FILES
        from league.swarm.evaluator import EQUITY_CALENDAR_FILES, EQUITY_EVIDENCE, EQUITY_GYM_FILES

        hashed = set(LEAGUE_FILES) | set(EQUITY_GYM_FILES) | set(EQUITY_CALENDAR_FILES) | {
            f"league/equity/{name}.py" for name in EQUITY_EVIDENCE}
        for path in ("league/constitution.py", "league/equity/bands.py", "league/equity/live.py",
                     "league/equity/families.py", "league/swarm/elane.py", "league/ops/preopen.py", "league/ledger.py"):
            self.assertNotIn(path, hashed)
            self.assertFalse(path.startswith(("league/live/", "league/gym/")), path)


if __name__ == "__main__":
    unittest.main()
