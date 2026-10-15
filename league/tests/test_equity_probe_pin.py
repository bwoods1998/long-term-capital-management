"""THE PROBE POOL FROZEN AT E_P (C2 (A45) of the scaling plan, its Probe row; league/equity/live.py `PROBE_PIN_FILE`,
`read_probe_pin`, `EquityBook._pin_now`, `_sleeve_equity`): every program's sleeve sizes on min(E, E_P) once the
private pin is read, and on E exactly as before while none was ever read on this box; the account's walls stay on E.
The Probe sleeve, the panel's and a Sized one's follow it alike, at the send (`_size`), at a share program's decide
(`_inputs`) and at a panel's budget (`_panel_budget`).

The review of part B (Oct 15, 2026): the last good E_P and a marker are KEPT in the House's private live.sqlite, so a
pin that cannot be read after a restart sizes on the last E_P read on this box (B1), a pin lost once one was read is
unreadable and never turns the freeze off (B2), and only a regular file is read, never followed or waited on (B3).
Only when no E_P was ever read on this box does an unreadable pin size nothing (every open refused House-wide). It is
said as ONE standing error a process (`began_at` its first minute, kept across restarts), which the watch after a
promotion counts as inherited (league/watchdog.py), and the pre-open check FAILS on it (league/ops/preopen.py).

Every figure is synthetic (an invented E and E_P; no account's): the pin holds dollars, so its real figure never sits
in this repository. The book runs on league/tests/test_equity_book.py's harness (money's `size_entry` stubbed at its
interface, recording what the book stated to it). Standard library only."""

import hashlib
import json
import os
import tempfile
import threading
import unittest
from decimal import Decimal as D
from pathlib import Path

from league.equity import live as L
from league.tests import test_equity_book as T

#: Synthetic figures: the sizing E the House reads, and pins below and above it.
E = "5000"
BELOW, ABOVE = "1937.41", "8642.17"
#: The harness's Probe sleeve share (`test_equity_book.equity_table`: 0.25, invented).
PROBE_SHARE = D("0.25")


def pin(root: Path, value, **extra) -> bytes:
    body = json.dumps({L.PROBE_PIN_FIELD: value, **extra}).encode()
    (root / L.PROBE_PIN_FILE).write_bytes(body)
    return body


class PinHarness(T.Harness):
    """The book's harness with a state root of its own, where the pin is written (`T.Harness` builds its book with no
    root: the House always gives one, `league.live.equity_hook.build_book`). `restart()` is a new process on the same
    live.sqlite."""

    def __init__(self, root: Path, pin_root: Path | None, **kw):
        self.pin_root = pin_root
        super().__init__(root, **kw)

    def new_book(self) -> L.EquityBook:
        return L.EquityBook(self.state, self.venue, self.market, self.table, self.families, decider=self.decider,
                            stock_proof=self.proof, sizing_equity=lambda: self.E, options_book=self.options,
                            root=self.pin_root, clock=self.clock,
                            record=lambda kind, payload, agent=None: self.events.append((kind, payload)),
                            alert=lambda level, text: self.alerts.append((level, text)))

    def restart(self) -> None:
        self.book = self.new_book()

    def standing(self) -> list[dict]:
        """The standing alerts the book wrote (`ops.alert` rows through the record hook)."""
        return [payload for kind, payload in self.events if kind == "ops.alert"]


class ThePin(unittest.TestCase):
    """`read_probe_pin`: only a name that is not there is absent; a regular file only, never followed or waited on;
    every other failure, and every content that is not a finite E_P above zero, is unreadable."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_absent_without_a_file_or_a_root(self):
        self.assertEqual(L.read_probe_pin(self.root).state, "absent")
        self.assertEqual(L.read_probe_pin(None).state, "absent")
        self.assertEqual(L.read_probe_pin(self.root / "no-such-dir").state, "absent")

    def test_read_as_a_number_or_a_decimal_string_with_the_bytes_sha256(self):
        for value, want in ((1500, D("1500")), (1500.5, D("1500.5")), ("1500.25", D("1500.25")), (" 1500 ", D("1500")),
                            ("1.5e3", D("1500"))):
            body = pin(self.root, value, plan_sha256="0" * 64, rungs={})
            got = L.read_probe_pin(self.root)
            self.assertEqual((got.state, got.e_p, got.sha256), ("read", want, hashlib.sha256(body).hexdigest()), value)

    def test_every_other_content_is_unreadable(self):
        path = self.root / L.PROBE_PIN_FILE
        for text in ("", "{", "[1500]", "1500", '"1500"', "null", "{}", '{"probe_e_usd": null}',
                     '{"probe_e_usd": true}', '{"probe_e_usd": false}', '{"probe_e_usd": "abc"}',
                     '{"probe_e_usd": ""}', '{"probe_e_usd": 0}', '{"probe_e_usd": -1}', '{"probe_e_usd": "-0.01"}',
                     '{"probe_e_usd": NaN}', '{"probe_e_usd": Infinity}', '{"probe_e_usd": "NaN"}',
                     '{"probe_e_usd": "Infinity"}', '{"probe_e_usd": [1500]}', '{"probe_e_usd": {"usd": 1500}}',
                     '{"E_P": 1500}'):
            path.write_text(text, encoding="utf-8")
            got = L.read_probe_pin(self.root)
            self.assertEqual((got.state, got.e_p), ("unreadable", None), text)
            self.assertNotIn("1500", got.why, "the why never carries the figure")
        path.write_bytes(b"\xff\xfe{")
        self.assertEqual(L.read_probe_pin(self.root).state, "unreadable", "not UTF-8")
        path.write_text(json.dumps({L.PROBE_PIN_FIELD: 1500, "pad": "x" * L.PROBE_PIN_MAX_BYTES}), encoding="utf-8")
        self.assertEqual(L.read_probe_pin(self.root).state, "unreadable", "over the size limit")

    def test_only_a_regular_file_is_read_never_followed_never_waited_on(self):
        path = self.root / L.PROBE_PIN_FILE
        path.mkdir()
        self.assertEqual(L.read_probe_pin(self.root).state, "unreadable", "a directory")
        path.rmdir()
        os.symlink(self.root / "elsewhere.json", path)
        self.assertEqual(L.read_probe_pin(self.root).state, "unreadable", "a link to nothing")
        path.unlink()
        good = self.root / "real-pin.json"
        good.write_text(json.dumps({L.PROBE_PIN_FIELD: 1500}), encoding="utf-8")
        os.symlink(good, path)
        self.assertEqual(L.read_probe_pin(self.root).state, "unreadable", "a link to a good pin is never followed")
        path.unlink()
        os.mkfifo(path)
        answer: list = []
        reader = threading.Thread(target=lambda: answer.append(L.read_probe_pin(self.root)), daemon=True)
        reader.start()
        reader.join(5)
        self.assertFalse(reader.is_alive(), "a FIFO never hangs the House's minute")
        self.assertEqual(answer[0].state, "unreadable", "a FIFO")
        path.unlink()
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            pin(self.root, 1500)
            path.chmod(0)
            self.addCleanup(path.chmod, 0o600)
            self.assertEqual(L.read_probe_pin(self.root).state, "unreadable", "no permission")


class TheFrozenPool(T.BookTest):
    """The book sizes every sleeve on the frozen pool, and keeps the account's walls on E."""

    def harness(self, *, pin_root: Path | None | bool = True, state: str = "state", **kw) -> PinHarness:
        state_dir = self.root / state
        state_dir.mkdir(exist_ok=True)
        h = PinHarness(state_dir, self.root if pin_root is True else pin_root, E=E, cash="20000", **kw)
        self.addCleanup(h.state.close)
        return h

    def size(self, h: PinHarness, inst: L.Instance, *, share="0.5") -> L.Z.SizingInputs | None:
        """One entry sized at the send: what the book stated to `size_entry`, or None when it sized nothing."""
        before = len(T.SIZED)
        intent = h.intent(inst, "buy", symbol="SPY", share=share)
        sized = h.book._size(intent, inst, "SPY", "etf", D("100"), None, T.MONDAY.isoformat())
        if sized is None:
            self.assertEqual(len(T.SIZED), before, "nothing reached size_entry")
            return None
        return T.SIZED[-1]

    def decide_view(self, h: PinHarness, inst: L.Instance) -> dict:
        bars = {"raw": {"SPY": [{"t": "2026-10-09", "c": "100"}]}, "all": {"SPY": [{"t": "2026-10-09", "c": "100"}]},
                "shas": {}}
        inputs, _ = h.book._inputs(inst, T.MONDAY, {"symbols": ["SPY"], "history": 0}, bars)
        return inputs

    def panel(self, h: PinHarness) -> L.Instance:
        inst = h.instance("fam-panel", band="probe", lane="equity")
        inst = L.replace(inst, kind="panel")
        h.book._save_instance(inst)
        return inst

    def figure_said(self, h: PinHarness, *figures: str) -> list[str]:
        """Every alert, record and health text that names one of `figures` (a pin's dollars must never be said)."""
        texts = [text for _, text in h.alerts] + [json.dumps(payload, default=str) for kind, payload in h.events
                                                  if kind in ("equity.probe_pin", "ops.alert")]
        texts.append(json.dumps(h.book.probe_pin(), default=str))
        return [t for t in texts if any(f in t for f in figures)]

    def kept(self, h: PinHarness) -> tuple:
        return h.state.get(L.PROBE_PIN_GOOD_KEY), h.state.get(L.PROBE_PIN_MARK_KEY)

    # -- no pin: exactly as before C2
    def test_no_pin_sizes_on_e_exactly_as_a_book_without_the_freeze(self):
        h = self.harness()
        inst = h.instance("fam-a")
        x = self.size(h, inst)
        self.assertEqual((x.E, x.sleeve_equity), (D(E), PROBE_SHARE * D(E)))
        bare = self.harness(pin_root=None, state="bare")
        y = self.size(bare, bare.instance("fam-a"))
        self.assertEqual(x, y, "no pin: the same facts as a book with no state root, field for field")
        self.assertEqual(self.decide_view(h, inst)["budget"], float(PROBE_SHARE * D(E)))
        h.tick(9, 31)
        self.assertEqual(h.alerts, [])
        self.assertEqual([k for k, _ in h.events if k in ("equity.probe_pin", "ops.alert")], [], "nothing new is said")
        self.assertEqual(self.kept(h), (None, None), "nothing is written to live.sqlite")
        self.assertEqual(h.book.health()["probe_pin"], {"state": "absent", "why": "no pin", "since": None,
                                                        "held": False})

    # -- a pin read
    def test_a_pin_below_e_freezes_every_sleeve_at_e_p_and_the_walls_stay_on_e(self):
        body = pin(self.root, BELOW)
        h = self.harness()
        inst = h.instance("fam-a")
        x = self.size(h, inst)
        self.assertEqual(x.sleeve_equity, PROBE_SHARE * D(BELOW), "the Probe sleeve on E_P")
        self.assertEqual(x.E, D(E), "an instrument's share of E and the invested cap stay on E")
        self.assertEqual(x.sleeve_free_cash, PROBE_SHARE * D(BELOW))
        view = self.decide_view(h, inst)
        self.assertEqual(view["budget"], float(PROBE_SHARE * D(BELOW)), "the decide's budget on the same pool")
        etf = h.table.equity.position_share["etf"]
        self.assertEqual(view["caps"]["SPY"], float(min(etf * D(E), etf * PROBE_SHARE * D(BELOW), PROBE_SHARE * D(BELOW))))
        self.assertEqual(h.book.health()["probe_pin"], {"state": "read", "why": "", "since": None, "held": True})
        self.assertEqual(h.alerts, [])
        self.assertEqual(self.figure_said(h, BELOW), [])
        good, mark = self.kept(h)
        self.assertEqual(good["e_p"], BELOW, "the last good E_P, kept in live.sqlite")
        self.assertEqual(mark["sha256"], hashlib.sha256(body).hexdigest())
        self.assertIsNone(mark["unreadable_since"])
        self.assertNotIn(BELOW, json.dumps(mark), "the marker carries no figure")

    def test_a_pin_above_e_sizes_on_e(self):
        pin(self.root, ABOVE)
        h = self.harness()
        inst = h.instance("fam-a")
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(E))
        self.assertEqual(self.decide_view(h, inst)["budget"], float(PROBE_SHARE * D(E)))
        pin(self.root, BELOW)
        h.E = D("1500")
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D("1500"), "E below E_P: E")

    def test_the_panel_and_a_sized_sleeve_follow_it_too(self):
        from league.equity import bands as B

        pin(self.root, BELOW)
        h = self.harness()
        share = D(str(B.panel_settings().sleeve_share))
        panel = self.panel(h)
        self.assertEqual(self.size(h, panel).sleeve_equity, share * D(BELOW), "the panel's sleeve at the send")
        budget, sleeve = h.book._panel_budget(panel, T.MONDAY.isoformat(), [])
        self.assertEqual(sleeve, share * D(BELOW), "the panel's sleeve at its decide")
        self.assertLessEqual(budget, sleeve)
        sized = h.instance("fam-sized", band="sized")
        self.assertEqual(self.size(h, sized).sleeve_equity, D("0.50") * D(BELOW), "a Sized sleeve (stubbed 0.50)")
        # On a box where no pin was ever read, the same three read E.
        (self.root / L.PROBE_PIN_FILE).unlink()
        fresh = self.harness(state="fresh")
        panel2 = self.panel(fresh)
        self.assertEqual(self.size(fresh, panel2).sleeve_equity, share * D(E))
        self.assertEqual(fresh.book._panel_budget(panel2, T.MONDAY.isoformat(), [])[1], share * D(E))
        self.assertEqual(self.size(fresh, fresh.instance("fam-sized", band="sized")).sleeve_equity, D("0.50") * D(E))

    # -- a pin that cannot be read: fail closed
    def test_an_unreadable_pin_with_none_ever_read_on_this_box_sizes_nothing(self):
        (self.root / L.PROBE_PIN_FILE).write_text("{not json", encoding="utf-8")
        h = self.harness()
        inst = h.instance("fam-a")
        intent = h.intent(inst, "buy", symbol="SPY", share="0.5")
        before = len(T.SIZED)
        self.assertIsNone(h.book._size(intent, inst, "SPY", "etf", D("100"), None, T.MONDAY.isoformat()))
        self.assertEqual(len(T.SIZED), before)
        self.assertEqual(h.get_intent(intent.iid).why, L.PIN_REFUSAL)
        self.assertEqual(self.decide_view(h, inst)["budget"], float(PROBE_SHARE * D(E)), "the decide's view: E")
        self.assertIsNone(self.size(h, inst))
        [alert] = h.standing()
        self.assertEqual(alert["level"], "error")
        self.assertIn(L.PROBE_PIN_FILE, alert["text"])
        self.assertIn("no E_P was ever read on this box", alert["text"])
        self.assertEqual(alert["began_at"], self.kept(h)[1]["unreadable_since"])
        self.assertEqual([lvl for lvl, _ in h.alerts], [], "never an unmarked error through the alert hook")
        health = h.book.health()["probe_pin"]
        self.assertEqual((health["state"], health["held"], health["since"]), ("unreadable", False, alert["began_at"]))

    def test_an_unreadable_pin_with_none_ever_read_is_a_house_wide_refusal_of_every_open(self):
        """`_open_block` (what the seat rule's open note reads with `OPEN_PROBE`): the refusal is the House's, so the
        session is left out of every seat's idle clock; with no pin, or with a pin read on this box, it is not there."""
        h = self.harness()
        inst = h.instance("fam-a")
        no_block = (lambda opening=True: None)
        self.assertIsNone(h.book._open_block(no_block, inst, killed=lambda: False), "no pin: no refusal")
        self.assertIsNone(h.book._open_block(no_block, L.OPEN_PROBE, killed=lambda: False))
        (self.root / L.PROBE_PIN_FILE).write_text("[]", encoding="utf-8")
        self.assertEqual(h.book._open_block(no_block, inst, killed=lambda: False), L.PIN_REFUSAL)
        self.assertEqual(h.book._open_block(no_block, L.OPEN_PROBE, killed=lambda: False), L.PIN_REFUSAL)
        pin(self.root, BELOW)
        self.assertIsNone(h.book._open_block(no_block, inst, killed=lambda: False), "a pin read: no refusal")
        (self.root / L.PROBE_PIN_FILE).write_text("[]", encoding="utf-8")
        self.assertIsNone(h.book._open_block(no_block, inst, killed=lambda: False),
                          "unreadable once one was read: the last E_P sizes, nothing is refused")

    def test_b1_an_unreadable_pin_at_a_restart_sizes_on_the_last_e_p_read_on_this_box(self):
        pin(self.root, BELOW)
        h = self.harness()
        inst = h.instance("fam-a")
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(BELOW))
        (self.root / L.PROBE_PIN_FILE).write_text('{"probe_e_usd": "x"}', encoding="utf-8")
        h.clock.set(T.at(T.MONDAY, 9, 40))
        h.restart()
        no_block = (lambda opening=True: None)
        self.assertIsNone(h.book._open_block(no_block, inst, killed=lambda: False), "nothing refused")
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(BELOW), "the last E_P kept, never E")
        self.assertEqual(self.decide_view(h, inst)["budget"], float(PROBE_SHARE * D(BELOW)))
        h.E = D("1500")
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D("1500"), "and E when it is the smaller")
        h.E = D(E)
        [alert] = h.standing()
        began = alert["began_at"]
        self.assertIn("the last E_P read on this box", alert["text"])
        # A second restart an hour on: the same condition, ONE alert again, dated the minute it began.
        h.clock.set(T.at(T.MONDAY, 10, 40))
        h.restart()
        self.size(h, inst)
        self.assertEqual([a["began_at"] for a in h.standing()], [began, began], "began_at is kept across restarts")
        self.assertEqual(self.figure_said(h, BELOW), [])

    def test_b2_a_pin_lost_once_one_was_read_never_turns_the_freeze_off(self):
        pin(self.root, BELOW)
        h = self.harness()
        inst = h.instance("fam-a")
        h.tick(9, 31)
        self.assertEqual(h.book.probe_pin()["state"], "read")
        (self.root / L.PROBE_PIN_FILE).unlink()
        h.restart()
        h.tick(9, 32)
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(BELOW), "the stored E_P, never E")
        state = h.book.probe_pin()
        self.assertEqual((state["state"], state["held"]), ("unreadable", True))
        self.assertIn("one was read on this box", state["why"])
        self.assertEqual(len(h.standing()), 1, "told once")
        # Readable again: followed (a new pin is a new figure), the marker cleared, the owner told it is back.
        pin(self.root, ABOVE)
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(E))
        self.assertIsNone(self.kept(h)[1]["unreadable_since"])
        self.assertEqual([lvl for lvl, _ in h.alerts], ["warning"])
        self.assertEqual(self.figure_said(h, BELOW, ABOVE), [])

    def test_an_unreadable_pin_never_read_then_removed_is_no_pin_again(self):
        (self.root / L.PROBE_PIN_FILE).write_text("[]", encoding="utf-8")
        h = self.harness()
        inst = h.instance("fam-a")
        self.assertIsNone(self.size(h, inst))
        (self.root / L.PROBE_PIN_FILE).unlink()
        h.restart()
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(E), "no pin was ever read here: E")
        self.assertEqual(h.book.probe_pin()["state"], "absent")

    def test_the_figure_is_kept_in_one_private_key_and_said_nowhere(self):
        pin(self.root, BELOW)
        h = self.harness()
        inst = h.instance("fam-a")
        self.size(h, inst)
        self.decide_view(h, inst)
        (self.root / L.PROBE_PIN_FILE).write_text("[]", encoding="utf-8")
        self.size(h, inst)
        h.book.health()
        self.assertEqual(json.loads((self.root / L.PROBE_PIN_FILE).read_text()), [], "the book never writes the pin")
        rows = {r["key"]: r["value"] for r in h.state.rows("SELECT key, value FROM kv")}
        self.assertEqual(sorted(k for k, v in rows.items() if BELOW in v), [L.PROBE_PIN_GOOD_KEY])
        self.assertEqual(self.figure_said(h, BELOW), [])
        self.assertNotIn("sha256", json.dumps(h.book.probe_pin()), "health shows no sha: a pin's bytes are guessable")


class TheWatch(unittest.TestCase):
    """The standing alert, as the House's ledger and the watchdog read it (league/watchdog.py `read_health`): one that
    began before the promotion is inherited, never the new release's failure; one that began under it is a reason."""

    def test_the_watch_after_a_promotion_inherits_it(self):
        from league import watchdog as wd
        from league.ledger import Ledger
        from league.tests.fakes import Clock
        from league.tests.test_watchdog import write_health

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / L.PROBE_PIN_FILE).write_text("[]", encoding="utf-8")
            state = root / "harness"
            state.mkdir()
            h = PinHarness(state, root, E=E, cash="20000")
            try:
                h.instance("fam-a")
                h.tick(9, 31)
                [payload] = h.standing()
            finally:
                h.state.close()
            clock = Clock(start=h.clock() + 600)
            ledger = Ledger(root / "ledger.sqlite", clock=clock)
            try:
                ledger.append("ops.started", {"books": []})
                since = ledger.head()[0]
                ledger.append("ops.alert", payload)
                write_health(root, clock, seq=ledger.head()[0])
                promoted_after = wd.epoch(payload["began_at"]) + 60
                inherited = wd.read_health(root, now=clock(), since_seq=since, inherited_before=promoted_after)
                self.assertTrue(inherited.ok, inherited.reasons)
                self.assertEqual((inherited.detail["error_alerts"], inherited.detail["inherited_alerts"]), (0, 1))
                promoted_before = wd.epoch(payload["began_at"]) - 60
                own = wd.read_health(root, now=clock(), since_seq=since, inherited_before=promoted_before)
                self.assertFalse(own.ok, "one that began under the release is the release's")
                self.assertIn("Probe pin", own.reasons[0])
            finally:
                ledger.close()


class ThePreopenCheck(unittest.TestCase):
    """Check 10 (league/ops/preopen.py `check_equity`): an unreadable pin FAILS before the open (the stall mail reads
    it); a pin read passes; no pin is told (C2 dark); a release before C2 reports none. No figure in any line."""

    def check(self, probe_pin):
        from league.ops.preopen import check_equity
        from league.tests.test_equity_money import ThePreopenEquityCheck

        h = ThePreopenEquityCheck("test_each_fault_fails").house()
        book = {"frozen": ""}
        if probe_pin is not None:
            book["probe_pin"] = probe_pin
        h["release"]["live"]["equity"] = book
        c = check_equity(h)
        return c.ok, c.headline(), c.items

    def test_each_state(self):
        ok, _, items = self.check({"state": "read", "why": "", "since": None, "held": True})
        self.assertTrue(ok)
        self.assertIn((True, "the Probe pin is read: every sleeve sizes on the smaller of E and E_P"), items)
        ok, _, items = self.check({"state": "absent", "why": "no pin", "since": None, "held": False})
        self.assertTrue(ok)
        self.assertIn((None, "no Probe pin, and none was ever read on this box: every sleeve sizes on E (C2 dark)"), items)
        ok, _, items = self.check(None)
        self.assertTrue(ok)
        self.assertIn((None, "the equity book reports no Probe pin state (a release before C2)"), items)
        ok, headline, _ = self.check({"state": "unreadable", "why": "the pin is not JSON (JSONDecodeError)",
                                      "since": "2026-10-16T04:12:00+00:00", "held": True})
        self.assertFalse(ok)
        self.assertEqual(headline, "the Probe pin cannot be read (since 2026-10-16T04:12:00+00:00: the pin is not JSON "
                                   "(JSONDecodeError)): every sleeve holds at the smaller of E and the last E_P read on "
                                   "this box; replace the pin")
        ok, headline, _ = self.check({"state": "unreadable", "why": "no pin", "since": None, "held": False})
        self.assertFalse(ok)
        self.assertIn("and none was ever read, so no equity entry is sized", headline)
        self.assertNotIn("$", headline)


if __name__ == "__main__":
    unittest.main()
