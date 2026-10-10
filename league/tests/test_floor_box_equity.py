"""THE ROLLBACK GUARD (A8.9, release E1; scripts/floor_box.py): `deploy` and `rollback` refuse a release that lacks the
EquityBook while the box's live state holds an equity lot or works an equity order; `--force-equity-risk` is the
documented emergency path. The box is never reached: its snippet runs here on a temporary state, and the commands run
against a fake Sail client."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def floor_box():
    spec = importlib.util.spec_from_file_location("floor_box_equity_test", ROOT / "scripts" / "floor_box.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FB = floor_box()


def live_state(root: Path, *, lots=(), orders=()) -> None:
    """A live state with the book's tables (league/live/state.py and league/equity/live.py's SCHEMA)."""
    from league.equity.live import SCHEMA
    from league.live.state import LiveState

    live = LiveState(root / "live.sqlite")
    try:
        live.db.executescript(SCHEMA)
        for i, status in enumerate(lots, 1):
            live.upsert("eq_lots", {"lid": i, "instance": "p@1:r", "family": "p", "version": 1, "lane": "beta",
                                    "symbol": "SPY", "class": "etf", "qty": "0.5", "opened_qty": "0.5", "entry_px": "100",
                                    "entry_notional": "50", "entry_at": "open", "opened_at": 0.0,
                                    "opened_day": "2026-10-13", "status": status}, "lid")
        for i, status in enumerate(orders, 1):
            live.upsert("eq_orders", {"eid": i, "client_id": f"lq-{i}-p", "instance": "p@1:r", "family": "p",
                                      "side": "buy", "symbol": "SPY", "class": "etf", "at": "open", "qty": "0.5",
                                      "limit_px": "100", "collar_bp": 10, "status": status, "placed_at": 0.0,
                                      "day": "2026-10-13", "updated_at": 0.0}, "eid")
    finally:
        live.close()


def run_snippet(state: Path, release: Path | None) -> dict:
    ask = {"state": str(state), "release": str(release) if release else None,
           "markers": [list(pair) for pair in FB.EQUITY_BOOK_MARKERS]}
    out = subprocess.run([sys.executable, "-c", FB.EQUITY_GUARD_SNIPPET, json.dumps(ask)], capture_output=True, text=True,
                         timeout=60)
    return json.loads(out.stdout.strip().splitlines()[-1])


def release_dir(root: Path, *, with_book: bool) -> Path:
    base = root / ("e1" if with_book else "old")
    (base / "league" / "equity").mkdir(parents=True)
    if with_book:
        (base / "league" / "equity" / "live.py").write_text("class EquityBook:\n    pass\n")
    return base


class TheSnippet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.state.mkdir()

    def test_it_counts_lots_held_and_orders_working_and_reads_the_release(self):
        live_state(self.state, lots=("open", "closing", "closed"), orders=("working", "filled", "unknown"))
        answer = run_snippet(self.state, release_dir(self.root, with_book=False))
        self.assertEqual((answer["lots"], answer["orders"], answer["book"]), (2, 2, "E1"))
        self.assertEqual(answer["release"]["missing"], ["league/equity/live.py: class EquityBook"])
        self.assertEqual(run_snippet(self.state, release_dir(self.root, with_book=True))["release"]["missing"], [])

    def test_no_live_state_or_one_from_before_e1_holds_nothing(self):
        self.assertEqual(run_snippet(self.state, None), {"release": None, "lots": 0, "orders": 0, "book": "absent"})
        from league.live.state import LiveState

        LiveState(self.state / "live.sqlite").close()
        self.assertEqual(run_snippet(self.state, None)["book"], "before E1")

    def test_this_tree_carries_the_marker(self):
        self.assertEqual(FB.EQUITY_BOOK_MARKERS, (("league/equity/live.py", "class EquityBook"),))
        self.assertEqual(FB.equity_gaps([Path("league/equity/live.py")]), [])
        self.assertEqual(FB.equity_gaps([Path("league/live/real.py")]), ["league/equity/live.py: class EquityBook"])


class TheHold(unittest.TestCase):
    MISSING = ["league/equity/live.py: class EquityBook"]

    def hold(self, answer, missing=MISSING, force=False):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            FB.hold_equity_book(answer, missing, target="the previous release x", force=force)
        return out.getvalue() + err.getvalue()

    def test_a_release_with_the_book_or_a_flat_book_may_go(self):
        self.assertEqual(self.hold({"lots": 3, "orders": 1}, missing=[]), "")
        self.assertIn("may go", self.hold({"lots": 0, "orders": 0}))

    def test_a_lot_held_an_order_working_or_an_unread_state_refuses(self):
        for answer in ({"lots": 1, "orders": 0}, {"lots": 0, "orders": 2}, {"error": "OperationalError: locked"}):
            with self.assertRaises(SystemExit) as caught:
                self.hold(answer)
            self.assertIn("REFUSED", str(caught.exception))
            self.assertIn("--force-equity-risk", str(caught.exception))
            self.assertIn("flatten first", str(caught.exception))

    def test_force_sends_it_anyway_loudly(self):
        said = self.hold({"lots": 2, "orders": 0}, force=True)
        self.assertIn("WARNING: --force-equity-risk", said)
        self.assertIn("2 lot(s)", said)


class FakeApi:
    """The Sail client: the probe's answer, the guards' answers by snippet, and the watchdog's rollback."""

    def __init__(self, equity):
        self.equity = equity
        self.calls = []

    def exec(self, box, command, **kw):
        self.calls.append(command)
        text = " ".join(str(c) for c in command)
        if command[:2] == ["sh", "-c"] and "watchdog rollback" in text:
            return SimpleNamespace(stdout=json.dumps({"ok": True, "rolled_back_from": "b", "current": "a"}), stderr="",
                                   return_code=0)
        if "floor_box equity book guard" in text:
            return SimpleNamespace(stdout=json.dumps(self.equity), stderr="", return_code=0)
        if "floor_box structure guard" in text:
            return SimpleNamespace(stdout=json.dumps({"release": {"missing": []}, "checked": False}), stderr="",
                                   return_code=0)
        if "floor_box real book guard" in text:
            return SimpleNamespace(stdout=json.dumps({"release": {"real_money": True, "missing": []}, "positions": 0,
                                                      "orders": 0}), stderr="", return_code=0)
        return SimpleNamespace(stdout="current=releases/b\nprevious=releases/a\nrunnable=yes\nenv=yes\n", stderr="",
                               return_code=0)


class TheCommands(unittest.TestCase):
    def rollback(self, equity, *flags):
        api = FakeApi(equity)
        args = FB.build_parser().parse_args(["rollback", "--reason", "drill", *flags])
        out = io.StringIO()
        with mock.patch.object(FB, "read_state", lambda: {"box_id": "sb_x", "python": "py"}), \
                mock.patch.object(FB, "require_box", lambda state: "sb_x"), \
                mock.patch.object(FB, "client", lambda: api), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = FB.cmd_rollback(args)
        return code, api

    def test_rollback_past_e1_with_a_lot_held_is_refused_before_the_watchdog_is_asked(self):
        held = {"release": {"missing": ["league/equity/live.py: class EquityBook"]}, "lots": 1, "orders": 0}
        with self.assertRaises(SystemExit) as caught:
            self.rollback(held)
        self.assertIn("equity book holds 1 lot", str(caught.exception))

    def test_rollback_goes_when_the_previous_release_has_the_book_or_the_book_is_flat_or_forced(self):
        for equity, flags in (({"release": {"missing": []}, "lots": 1, "orders": 0}, ()),
                              ({"release": {"missing": ["league/equity/live.py: class EquityBook"]}, "lots": 0,
                                "orders": 0}, ()),
                              ({"release": {"missing": ["league/equity/live.py: class EquityBook"]}, "lots": 1,
                                "orders": 0}, ("--force-equity-risk",))):
            code, api = self.rollback(equity, *flags)
            self.assertEqual(code, 0)
            self.assertTrue(any("watchdog rollback" in " ".join(map(str, c)) for c in api.calls))

    def test_an_unreadable_check_counts_as_missing_and_refuses(self):
        with self.assertRaises(SystemExit):
            self.rollback({"error": "no answer"})

    def test_deploy_of_a_tree_without_the_book_reads_the_box_and_refuses_while_it_holds_a_lot(self):
        api = FakeApi({"release": None, "lots": 2, "orders": 0})
        args = FB.build_parser().parse_args(["deploy"])
        with mock.patch.object(FB, "read_state", lambda: {"box_id": "sb_x", "python": "py"}), \
                mock.patch.object(FB, "require_box", lambda state: "sb_x"), \
                mock.patch.object(FB, "client", lambda: api), \
                mock.patch.object(FB, "code_files", lambda: [Path("league/live/real.py")]), \
                mock.patch.object(FB, "tarball", lambda files: b"tree"), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                FB.cmd_deploy(args)
        self.assertIn("this working tree lacks the equity book", str(caught.exception))
        self.assertTrue(FB.build_parser().parse_args(["deploy", "--force-equity-risk"]).force_equity_risk)


class TheDocs(unittest.TestCase):
    def test_operations_documents_the_guard_and_the_flatten_first_rollback(self):
        text = (ROOT / "docs" / "operations.md").read_text(encoding="utf-8")
        self.assertIn("--force-equity-risk", text)
        self.assertIn("EquityBook.flatten", text)


if __name__ == "__main__":
    unittest.main()
