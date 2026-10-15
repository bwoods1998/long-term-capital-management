"""THE PROBE POOL FROZEN AT E_P (C2 (A45) of the scaling plan, its Probe row; league/equity/live.py `PROBE_PIN_FILE`,
`read_probe_pin`, `EquityBook._sleeve_equity`): every program's sleeve sizes on min(E, E_P) once the private pin
exists, and on E exactly as before while it does not; a pin that cannot be read fails closed to min(E, the last E_P
this process read), and sizes nothing when none was read; the account's walls stay on E. The Probe sleeve, the panel's
and a Sized one's follow it alike, at the send (`_size`), at a share program's decide (`_inputs`) and at a panel's
budget (`_panel_budget`).

Every figure is synthetic (an invented E and E_P; no account's): the pin holds dollars, so its real figure never sits
in this repository. The book runs on league/tests/test_equity_book.py's harness (money's `size_entry` stubbed at its
interface, recording what the book stated to it). Standard library only."""

import json
import os
import unittest
from decimal import Decimal as D
from pathlib import Path

from league.equity import live as L
from league.tests import test_equity_book as T

#: Synthetic figures: the sizing E the House reads, and pins below and above it.
E = "5000"
BELOW, ABOVE = "1937.41", "8642.17"
#: The harness's Probe sleeve share (`test_equity_book.equity_table`: 0.25, invented) and the panel row's in force.
PROBE_SHARE = D("0.25")


def pin(root: Path, value, **extra) -> None:
    (root / L.PROBE_PIN_FILE).write_text(json.dumps({L.PROBE_PIN_FIELD: value, **extra}), encoding="utf-8")


class PinHarness(T.Harness):
    """The book's harness with a state root of its own, where the pin is written (`T.Harness` builds its book with no
    root: the House always gives one, `league.live.equity_hook.build_book`)."""

    def __init__(self, root: Path, pin_root: Path | None, **kw):
        self.pin_root = pin_root
        super().__init__(root, **kw)

    def new_book(self) -> L.EquityBook:
        return L.EquityBook(self.state, self.venue, self.market, self.table, self.families, decider=self.decider,
                            stock_proof=self.proof, sizing_equity=lambda: self.E, options_book=self.options,
                            root=self.pin_root, clock=self.clock,
                            record=lambda kind, payload, agent=None: self.events.append((kind, payload)),
                            alert=lambda level, text: self.alerts.append((level, text)))


class ThePin(unittest.TestCase):
    """`read_probe_pin`: only a file that is not there is absent; every other failure, and every content that is not a
    finite E_P above zero, is unreadable."""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_absent_without_a_file_or_a_root(self):
        self.assertEqual(L.read_probe_pin(self.root).state, "absent")
        self.assertEqual(L.read_probe_pin(None).state, "absent")
        self.assertEqual(L.read_probe_pin(self.root / "no-such-dir").state, "absent")

    def test_read_as_a_number_or_a_decimal_string(self):
        for value, want in ((1500, D("1500")), (1500.5, D("1500.5")), ("1500.25", D("1500.25")), (" 1500 ", D("1500")),
                            ("1.5e3", D("1500"))):
            pin(self.root, value, plan_sha256="0" * 64, rungs={})
            got = L.read_probe_pin(self.root)
            self.assertEqual((got.state, got.e_p), ("read", want), value)

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

    def test_a_pin_that_is_there_but_cannot_be_opened_is_unreadable_never_absent(self):
        path = self.root / L.PROBE_PIN_FILE
        path.mkdir()
        self.assertEqual(L.read_probe_pin(self.root).state, "unreadable", "a directory")
        path.rmdir()
        os.symlink(self.root / "elsewhere.json", path)
        self.assertEqual(L.read_probe_pin(self.root).state, "unreadable", "a link to nothing")
        path.unlink()
        if hasattr(os, "geteuid") and os.geteuid() != 0:
            pin(self.root, 1500)
            path.chmod(0)
            self.addCleanup(path.chmod, 0o600)
            self.assertEqual(L.read_probe_pin(self.root).state, "unreadable", "no permission")


class TheFrozenPool(T.BookTest):
    """The book sizes every sleeve on the frozen pool, and keeps the account's walls on E."""

    def harness(self, *, pin_root: Path | None | bool = True, **kw) -> PinHarness:
        state_dir = self.root / "state"
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
        """Every alert and record text that names one of `figures` (a pin's dollars must never be said)."""
        texts = [text for _, text in h.alerts] + [json.dumps(payload, default=str) for kind, payload in h.events
                                                  if kind == "equity.probe_pin"]
        return [t for t in texts if any(f in t for f in figures)]

    # -- no pin: exactly as before C2
    def test_no_pin_sizes_on_e_exactly_as_a_book_without_the_freeze(self):
        h = self.harness()
        inst = h.instance("fam-a")
        x = self.size(h, inst)
        self.assertEqual((x.E, x.sleeve_equity), (D(E), PROBE_SHARE * D(E)))
        bare = self.harness(pin_root=None)
        y = self.size(bare, bare.instance("fam-a"))
        self.assertEqual(x, y, "no pin: the same facts as a book with no state root, field for field")
        self.assertEqual(self.decide_view(h, inst)["budget"], float(PROBE_SHARE * D(E)))
        self.assertEqual(h.alerts, [])
        self.assertEqual([k for k, _ in h.events if k == "equity.probe_pin"], [], "no pin: nothing new is recorded")
        self.assertEqual(h.book.health()["probe_pin"], {"state": "absent", "why": "no pin"})

    # -- a pin read
    def test_a_pin_below_e_freezes_every_sleeve_at_e_p_and_the_walls_stay_on_e(self):
        pin(self.root, BELOW)
        h = self.harness()
        inst = h.instance("fam-a")
        x = self.size(h, inst)
        self.assertEqual(x.sleeve_equity, PROBE_SHARE * D(BELOW), "the Probe sleeve on E_P")
        self.assertEqual(x.E, D(E), "an instrument's share of E and the invested cap stay on E")
        self.assertEqual(x.sleeve_free_cash, PROBE_SHARE * D(BELOW))
        view = self.decide_view(h, inst)
        self.assertEqual(view["budget"], float(PROBE_SHARE * D(BELOW)), "the decide's budget on the same pool")
        # Its cap: the lower of the ETF's share of E (the account's wall) and of the frozen sleeve, and the sleeve's cash.
        etf = h.table.equity.position_share["etf"]
        self.assertEqual(view["caps"]["SPY"], float(min(etf * D(E), etf * PROBE_SHARE * D(BELOW), PROBE_SHARE * D(BELOW))))
        self.assertEqual(h.book.health()["probe_pin"], {"state": "read", "why": ""})
        self.assertEqual(h.alerts, [])
        self.assertEqual(self.figure_said(h, BELOW), [])

    def test_a_pin_above_e_sizes_on_e(self):
        pin(self.root, ABOVE)
        h = self.harness()
        inst = h.instance("fam-a")
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(E))
        self.assertEqual(self.decide_view(h, inst)["budget"], float(PROBE_SHARE * D(E)))
        # E falls below a pin that was below it: the smaller, E, again.
        pin(self.root, BELOW)
        h.E = D("1500")
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D("1500"))

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
        # With no pin the same three read E.
        (self.root / L.PROBE_PIN_FILE).unlink()
        fresh = self.harness()
        panel2 = self.panel(fresh)
        self.assertEqual(self.size(fresh, panel2).sleeve_equity, share * D(E))
        self.assertEqual(fresh.book._panel_budget(panel2, T.MONDAY.isoformat(), [])[1], share * D(E))
        self.assertEqual(self.size(fresh, fresh.instance("fam-sized", band="sized")).sleeve_equity, D("0.50") * D(E))

    # -- a pin that cannot be read: fail closed
    def test_an_unreadable_pin_with_none_read_before_sizes_nothing(self):
        (self.root / L.PROBE_PIN_FILE).write_text("{not json", encoding="utf-8")
        h = self.harness()
        inst = h.instance("fam-a")
        intent = h.intent(inst, "buy", symbol="SPY", share="0.5")
        before = len(T.SIZED)
        self.assertIsNone(h.book._size(intent, inst, "SPY", "etf", D("100"), None, T.MONDAY.isoformat()))
        self.assertEqual(len(T.SIZED), before)
        self.assertEqual(h.get_intent(intent.iid).why, L.PIN_REFUSAL)
        # The decide's view reads E (no program is handed a budget of nothing); what it plans opens nothing.
        self.assertEqual(self.decide_view(h, inst)["budget"], float(PROBE_SHARE * D(E)))
        self.assertIsNone(self.size(h, inst))
        errors = [text for level, text in h.alerts if level == "error"]
        self.assertEqual(len(errors), 1, "told once a state, not once a minute")
        self.assertIn(L.PROBE_PIN_FILE, errors[0])
        self.assertEqual(h.book.health()["probe_pin"]["state"], "unreadable")

    def test_an_unreadable_pin_with_none_read_is_a_house_wide_refusal_of_every_open(self):
        """`_open_block` (what the seat rule's open note reads with `OPEN_PROBE`): the refusal is the House's, so the
        session is left out of every seat's idle clock; with no pin, or a pin read, it is not there."""
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
                          "unreadable after a read: the last E_P sizes, nothing is refused")

    def test_an_unreadable_pin_after_one_was_read_holds_the_smaller_of_e_and_the_last_e_p(self):
        pin(self.root, BELOW)
        h = self.harness()
        inst = h.instance("fam-a")
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(BELOW))
        (self.root / L.PROBE_PIN_FILE).write_text('{"probe_e_usd": "x"}', encoding="utf-8")
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(BELOW), "the last E_P read, never E")
        self.assertEqual(self.decide_view(h, inst)["budget"], float(PROBE_SHARE * D(BELOW)))
        h.E = D("1500")
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D("1500"), "and E when it is the smaller")
        h.E = D(E)
        # Gone after one was read is read the same way until the House starts again.
        (self.root / L.PROBE_PIN_FILE).unlink()
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(BELOW))
        self.assertEqual(h.book.health()["probe_pin"]["state"], "unreadable")
        # Readable again: followed, and the owner told it is back.
        pin(self.root, ABOVE)
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(E))
        self.assertEqual([level for level, _ in h.alerts], ["error", "warning"])
        self.assertEqual(self.figure_said(h, BELOW, ABOVE, "1500"), [])
        # A new process with the pin removed on purpose sizes on E, as before C2.
        (self.root / L.PROBE_PIN_FILE).unlink()
        h.book = h.new_book()
        self.assertEqual(self.size(h, inst).sleeve_equity, PROBE_SHARE * D(E))

    def test_the_pin_is_never_written_by_the_book(self):
        pin(self.root, BELOW)
        h = self.harness()
        inst = h.instance("fam-a")
        self.size(h, inst)
        self.decide_view(h, inst)
        h.book.health()
        self.assertEqual(json.loads((self.root / L.PROBE_PIN_FILE).read_text()), {L.PROBE_PIN_FIELD: BELOW})
        dump = "\n".join(str(tuple(r)) for r in h.state.rows("SELECT key, value FROM kv"))
        self.assertNotIn(BELOW, dump, "no E_P in the live state's kv")


if __name__ == "__main__":
    unittest.main()
