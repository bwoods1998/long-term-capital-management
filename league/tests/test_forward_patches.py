"""PACKAGE C's EDITS TO THREE EXISTING OPS FILES (release E3, the spec's 11.4, 11.5 and 11.6), held before and after
they land.

A builder edits no existing file: the integrator applies these edits. `EDITS` is each one as an exact (anchor,
replacement) pair, and `integrated(name)` is the module the tests read:
- once the integrator has applied a file's edits (its `MARKS` text is in the source), the module AS IT IS;
- until then, the same edits made on a copy of the file's source, each anchor found exactly once, and the copy
  executed as that module (never installed in `sys.modules`: nothing else sees it).
So the edits are tested on the builder's branch exactly as they will be applied, and the same tests then hold the
applied files. `TheEditsApply` fails if a file carries only some of them.

What the three glue edits must do, and nothing more (the spec: nothing C adds to `meter`, `report`, `funnel.window`
or `stall.run` may raise): `funnel.window` carries `forward_record` (integers; unread is an `errors` entry, never a
zero); `stall.run` carries `receipts` and goes on without them; the dlane report's constants say what release E3
loosened, tightened and now computes. The Done meter's A14 and the report's forward section are in
league/tests/test_dlane_report_a14.py. Every count is invented."""

from __future__ import annotations

import importlib
import json
import sqlite3
import types
import unittest
from pathlib import Path
from unittest import mock

from league.ops import forward_report, release_receipts
from league.ops import schedule as S

REPO = Path(__file__).resolve().parents[2]

#: file -> a text only the edited file holds.
MARKS = {"funnel": "forward_report.funnel_rows(root, start, end)", "stall": "release_receipts.step(root, ",
         "dlane_report": "def a14_of("}

A14_OF = '''

def a14_of(store: Any, counted: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """RELEASE E3, amendment A14 (league/ops/forward_twins.py `a14_reading`): over a checkpoint's counted closes, the size
    of the mean fill gap against the official-price model within 15 bp a side AND live and shadow intents agreeing on
    95% of the counted sessions. With no equity close it does not apply (holds); unreadable, unmeasured or misshapen, it
    does not hold. Never raises, and always carries applies, holds, final and why."""
    if not any(c.get("equity") for c in counted):
        return {"applies": False, "holds": True, "final": True, "why": None}
    try:
        from . import forward_twins
        r = forward_twins.a14_reading(Path(store.root), counted)
        return {**r, "applies": r.get("applies") is not False, "holds": r.get("holds") is True,
                "final": r.get("final") is True, "why": r.get("why")}  # a non-dict raises into the except
    except Exception as exc:  # noqa: BLE001 - unread is not held
        return {"applies": True, "holds": False, "final": False, "why": f"A14 could not be read ({type(exc).__name__})"}
'''

EDITS: dict[str, list[tuple[str, str]]] = {
    # ------------------------------------------------------------------------------------------------ 11.4
    "funnel": [
        ('''READ-ONLY: every SQLite open is `mode=ro` (`guard.read`); each section that cannot be read is an `errors` entry and its
counts None, never a zero. Standard library only.
"""''',
         '''THE FORWARD RECORD (release E3), apart, under `forward_record` (league/ops/forward_report.py `funnel_rows`; the daily
page's table reads none of it): programs registered, lineages, controls, program-sessions, stale, errors, checkpoints,
the BH and BY counts and the memory tables' rows in the window. Integers only, never a figure.

READ-ONLY: every SQLite open is `mode=ro` (`guard.read`); each section that cannot be read is an `errors` entry and its
counts None, never a zero. Standard library only.
"""'''),
        ('''    except Exception as exc:  # noqa: BLE001
        out["errors"]["book"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return out
''',
         '''    except Exception as exc:  # noqa: BLE001
        out["errors"]["book"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    try:  # RELEASE E3: the forward record's counts (league/ops/forward_report.py: integers only, never a figure)
        from . import forward_report
        out["forward_record"] = forward_report.funnel_rows(root, start, end)
    except Exception as exc:  # noqa: BLE001 - unread is never zero
        out["errors"]["forward_record"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return out
'''),
    ],
    # ------------------------------------------------------------------------------------------------ 11.6
    "stall": [
        ('''NEVER ACTS. The job reads (every SQLite open `mode=ro`, inside `guard.readonly()`; the gateway's `/v1/health`, a GET),
writes only `stall.json`, and posts only the notice: it moves no money, changes no setting, starts and stops nothing. It
runs in a maintenance pause too (read-only, like `preopen` and `clock`), so a pause left on is itself reported.
"""''',
         '''NEVER ACTS. The job reads (every SQLite open `mode=ro`, inside `guard.readonly()`; the gateway's `/v1/health`, a GET),
writes only `stall.json` and the release receipts' own store (below), and posts only the notice: it moves no money,
changes no setting, starts and stops nothing. It runs in a maintenance pause too (read-only, like `preopen` and
`clock`), so a pause left on is itself reported.

RELEASE RECEIPTS (release E3; league/ops/release_receipts.py `step`): each run declares the running release's receipts
(`docs/benchmarks/release_receipts.json`: the funnel metric a deploy expects to move) the first time it sees them and
reads each back once its window has closed, into `<state>/release-receipts.sqlite`; the run's receipt carries what it
declared, read and could not (`receipts`). Listed, never reverted; no cause of `CAUSES`; a failure there is an entry of
`receipts.errors` and the stall alarm goes on.
"""'''),
        ('''    write_json(root / STATE_FILE, {"schema": 2, "at": S.iso(now), "causes": told, "mail": mail,
                                   "nightly_error": nightly_error, "done_told": done_told})
    return {"stalled": stalled, "cleared": cleared, "warned": warned, "notice": notice,
            "checks": {c: {k: found[c].get(k) for k in ("stalled", "what", "numbers", "doing", "owner_step")} for c in CAUSES},
            "ceiling": ceiling, "errors": errors, "warning": bool(stalled or errors)}
''',
         '''    try:  # RELEASE E3: the release receipts (league/ops/release_receipts.py): declared at a deploy, read back after its window
        from . import release_receipts
        receipts = release_receipts.step(root, _get(ctx, "base"), _get(ctx, "release"), now=now)
    except Exception as exc:  # noqa: BLE001 - the stall alarm goes on without it
        receipts = {"errors": [f"{type(exc).__name__}: {str(exc)[:160]}"]}
    write_json(root / STATE_FILE, {"schema": 2, "at": S.iso(now), "causes": told, "mail": mail,
                                   "nightly_error": nightly_error, "done_told": done_told})
    return {"stalled": stalled, "cleared": cleared, "warned": warned, "notice": notice,
            "checks": {c: {k: found[c].get(k) for k in ("stalled", "what", "numbers", "doing", "owner_step")} for c in CAUSES},
            "ceiling": ceiling, "errors": errors, "warning": bool(stalled or errors), "receipts": receipts}
'''),
    ],
    # ------------------------------------------------------------------------------------------------ 11.5
    "dlane_report": [
        # (e) the module docstring's A14 paragraph, and the forward record's section
        ('''- PRE-REGISTERED BEFORE THE FIRST EQUITY CLOSE (the captain's A14, Oct 10, 2026; `PREREGISTERED`, verbatim in every
  report as `done.preregistered` and in docs/operations.md; TEXT NOW, the code in a later release): how the Done rule's
''',
         '''- PRE-REGISTERED BEFORE THE FIRST EQUITY CLOSE (the captain's A14, Oct 10, 2026; `PREREGISTERED`, verbatim in every
  report as `done.preregistered` and in docs/operations.md; the consistency reading computed since release E3): how
  the Done rule's
'''),
        ('''  seat rule, written and inactive (`A14_SEAT_RULE`). None of the three is computed here yet: until its reader lands the
  meters read consistency by the pinned rule's own measure (CONSISTENT WITH REPLAY, above), no reading carries the
  close-date figures, and no forward rule moves a seat (`PREREGISTERED["status"]` says so in the report).
''',
         '''  seat rule, written and inactive (`A14_SEAT_RULE`). CONSISTENCY IS COMPUTED SINCE RELEASE E3 (`a14_of`;
  league/ops/forward_twins.py `a14_reading`; each checkpoint's `a14`): a checkpoint that holds an equity close also needs
  the SIZE of the mean fill gap of its priced twins within 15 bp a side, either way, AND the live and the shadow intents
  agreeing on 95% of its counted sessions, beside the pinned rule's own measure (CONSISTENT WITH REPLAY, above).
  Unmeasured, unreadable or misshapen, A14 does not hold and the reading is not final; a checkpoint with no equity
  close is read as before; a frozen final reading is carried as it was. The close-date figures are not computed yet
  and no forward rule moves a seat (`PREREGISTERED["status"]` says so in the report).
- THE FORWARD RECORD (release E3; league/ops/forward_report.py): `forward_record` is that job's report as it last wrote
  it (None when absent or stale), and its alarms (FW1-FW8, RR1, RR2, CP1, CP2, MM1: ids, counts and dates only) ride
  this report's `alarms`, so the `dlane` stall cause mails a warning. Read only, and never this report's failure.
'''),
        ('''#: after the fact; text now, its code in a later release): how the Done rule's "live fills consistent with their
''',
         '''#: after the fact; text first, its consistency reading computed since release E3): how the Done rule's "live fills consistent with their
'''),
        # (e) the status
        ('''    "status": "text only, not computed yet: until the reader lands the meters read consistency by the pinned Done "
              "rule's own measure (the replay gap within its bound per program), no reading carries the close-date "
              "figures, and no forward rule moves a seat",
''',
         '''    "status": "consistency is computed since release E3 (each checkpoint's `a14`: the size of the mean fill gap "
              "either way, and the intents); the close-date figures are not computed yet and no forward rule moves a "
              "seat",
'''),
        # (d) the loosening and the tightening
        ('''             "beside the same-risk buy-and-hold, never alpha; what G1 cannot see is a gate that only tilts inside its "
             "bands (a size that halves, a hold between 4 and 6 sessions, a strike that keeps the risk in band)"},
)
''',
         '''             "beside the same-risk buy-and-hold, never alpha; what G1 cannot see is a gate that only tilts inside its "
             "bands (a size that halves, a hold between 4 and 6 sessions, a strike that keeps the risk in band)"},
    # RELEASE E3 (league/swarm/elane_folds.py): the hidden work year.
    {"rule": "the equity Train bar", "was": "the seven Train years 2016-19 and 2022-24 (A15)",
     "now": "six seen years for a family born with a hidden year, each stretch of them a run starting flat (release E3)",
     "cost": "more zero-edge versions pass Train and take a Validation try; the screen's false-positive rate per program "
             "is unchanged (Train is in-sample)"},
)
'''),
        ('''    "6.0/3.3/1.0% against 10.0/7.6/4.5% with the $400 total alone, at 24 weeks 11.1/8.7/5.9% against 11.0/9.0/7.6%",
)
''',
         '''    "6.0/3.3/1.0% against 10.0/7.6/4.5% with the $400 total alone, at 24 weeks 11.1/8.7/5.9% against 11.0/9.0/7.6%",
    "A14's fill gap is read as the size of the mean gap, either way (release E3): fills better than the official-price "
    "model by more than 15 bp a side also read not consistent",
)
'''),
        # (a) a14_of, beside equity_yield
        ('''    try:
        return elane_yield.report(store, settings, train_key=elane_train.STATE_KEY)
    except Exception as exc:  # noqa: BLE001 - the report goes on without it
        return {"error": type(exc).__name__}
''',
         '''    try:
        return elane_yield.report(store, settings, train_key=elane_train.STATE_KEY)
    except Exception as exc:  # noqa: BLE001 - the report goes on without it
        return {"error": type(exc).__name__}
''' + A14_OF),
        # (b) the meter
        ('''    whatever the inputs say now (nightly rows are replaced each night; the reading may not flip after A8)."""
    from ..swarm import dlane
''',
         '''    whatever the inputs say now (nightly rows are replaced each night; the reading may not flip after A8).

    A14 (release E3; `a14_of`): a checkpoint's reading also needs A14 over its counted closes (it holds outright with no
    equity close); it is in the checkpoint's `holds`, its item 4 and `consistent_ok`, carried whole as `a14`, and a
    reading whose A14 is not final is not final. The `running` figures are untouched."""
    from ..swarm import dlane
'''),
        ('''        at = reading(counted[:k], store, nightly_cache=cache, lanes=lanes, twins=twins)
''',
         '''        at = reading(counted[:k], store, nightly_cache=cache, lanes=lanes, twins=twins)
        a14 = a14_of(store, counted[:k])
'''),
        ('''            fin = {**fin, "final": False, "why": "; ".join(w for w in (fin["why"], f"the research window's last day "
                                                                                  f"({last_day}) has not ended") if w)}
        item7 = r247.get("holds") is True
        whys = [w for w in (at["why"], None if item7 else f"research 24/7 (item 7): {r247.get('why') or 'not held'}") if w]
''',
         '''            fin = {**fin, "final": False, "why": "; ".join(w for w in (fin["why"], f"the research window's last day "
                                                                                  f"({last_day}) has not ended") if w)}
        if not a14["final"]:
            fin = {**fin, "final": False, "why": "; ".join(w for w in (fin["why"], "A14: a twin or a shadow session has "
                                                                                  "not landed") if w)}
        item7 = r247.get("holds") is True
        whys = [w for w in (at["why"], None if item7 else f"research 24/7 (item 7): {r247.get('why') or 'not held'}",
                            None if a14["holds"] else f"A14 (live fills consistent with their replay): "
                                                      f"{a14.get('why') or 'not held'}") if w]
'''),
        ('''                            "holds": at["holds"] and item7, "why": "; ".join(whys) or None,
                            "items": {**at["items"], "7": item7}, "final": fin["final"], "final_why": fin["why"],
''',
         '''                            "holds": at["holds"] and item7 and a14["holds"], "why": "; ".join(whys) or None,
                            "items": {**at["items"], "4": at["items"]["4"] and a14["holds"], "7": item7},
                            "final": fin["final"], "final_why": fin["why"],
'''),
        ('''                            "consistent_ok": at["consistent_ok"], "measured_programs": at["measured_programs"],
''',
         '''                            "consistent_ok": at["consistent_ok"] and a14["holds"], "a14": a14,
                            "measured_programs": at["measured_programs"],
'''),
        # (c) the report
        ('''        out["alarms"] = alarms(store, settings, lanes, book, every, envelope, done, k5, unit, previous, now=now,
                               today=today, losses=losses) + pt1_alarms(out["roster"], settings)
''',
         '''        out["alarms"] = alarms(store, settings, lanes, book, every, envelope, done, k5, unit, previous, now=now,
                               today=today, losses=losses) + pt1_alarms(out["roster"], settings)
        try:  # RELEASE E3: the forward record's section and alarms (league/ops/forward_report.py); never the report's failure
            from . import forward_report
            out["forward_record"] = forward_report.read_section(root)
            out["alarms"] = out["alarms"] + [a for a in forward_report.alarms(root, now=now, settings=settings)
                                             if isinstance(a, dict) and isinstance(a.get("id"), str)
                                             and a.get("level") in ("info", "warning") and isinstance(a.get("text"), str)]
        except Exception:  # noqa: BLE001 - the report goes on without it
            out.setdefault("forward_record", None)
'''),
    ],
}


def source(name: str) -> str:
    return (REPO / "league" / "ops" / f"{name}.py").read_text(encoding="utf-8")


def applied(name: str) -> bool:
    """Whether the file already carries this package's edits (the integrator applied them)."""
    return MARKS[name] in source(name)


def edited(name: str) -> str:
    """The file's source with this package's edits applied (as it is when they already are)."""
    text = source(name)
    if applied(name):
        return text
    for old, new in EDITS[name]:
        if text.count(old) != 1:
            raise AssertionError(f"league/ops/{name}.py: an edit's anchor is found {text.count(old)} times: {old[:80]!r}")
        text = text.replace(old, new)
    return text


def integrated(name: str) -> types.ModuleType:
    """`league.ops.<name>` with this package's edits (the module docstring): the module itself once they are applied;
    until then a private copy executed from the edited source."""
    module = importlib.import_module(f"league.ops.{name}")
    if applied(name):
        return module
    copy = types.ModuleType(module.__name__)
    copy.__file__, copy.__package__ = module.__file__, module.__package__
    exec(compile(edited(name), str(module.__file__), "exec"), copy.__dict__)  # noqa: S102 - the repository's own source
    return copy


class TheEditsApply(unittest.TestCase):
    def test_every_anchor_is_found_once_or_every_edit_is_in_the_file(self):
        for name, edits in EDITS.items():
            text = source(name)
            for old, new in edits:
                if applied(name):
                    self.assertIn(new, text, f"league/ops/{name}.py carries only some of package C's edits")
                else:
                    self.assertEqual(text.count(old), 1, f"league/ops/{name}.py: {old[:80]!r}")
            compile(edited(name), f"league/ops/{name}.py", "exec")

    def test_the_edited_modules_keep_every_public_name(self):
        for name in EDITS:
            module, real = integrated(name), importlib.import_module(f"league.ops.{name}")
            self.assertEqual(sorted(module.__all__), sorted(real.__all__)) if hasattr(real, "__all__") else None
            for public in getattr(real, "__all__", ()):
                self.assertTrue(hasattr(module, public), f"{name}.{public}")

    def test_nothing_else_of_the_three_files_moves(self):
        # Each edit only adds lines, or rewrites the sentences the spec names (the A14 status and its two comments).
        for name, edits in EDITS.items():
            for old, new in edits:
                gone = [line for line in old.splitlines() if line.strip() and line not in new.splitlines()]
                for line in gone:
                    self.assertRegex(line, r"TEXT NOW|text now|text only|rule's own measure|close-date|figures, and no "
                                           r"forward rule|None of the three|writes only|runs in a maintenance pause|"
                                           r"\"holds\": at\[\"holds\"\]|\"items\": \{\*\*at|consistent_ok|whys = \[|"
                                           r"\"warning\": bool|may not flip after A8", f"{name}: {line!r}")


class TheConstantsOfTheDlaneReport(unittest.TestCase):
    """11.5 (d) and (e)."""

    @classmethod
    def setUpClass(cls):
        cls.R = integrated("dlane_report")

    def test_the_loosening_of_the_train_bar_is_listed_with_its_cost(self):
        row = self.R.LOOSENED[-1]
        self.assertEqual(set(row), {"rule", "was", "now", "cost"})
        self.assertEqual(row["rule"], "the equity Train bar")
        self.assertIn("seven Train years 2016-19 and 2022-24 (A15)", row["was"])
        self.assertIn("six seen years for a family born with a hidden year, each stretch of them a run starting flat", row["now"])
        self.assertIn("more zero-edge versions pass Train", row["cost"])
        self.assertIn("false-positive rate per program is unchanged", row["cost"])
        base = importlib.import_module("league.ops.dlane_report")
        self.assertEqual(len(self.R.LOOSENED), len(base.LOOSENED) + (0 if applied("dlane_report") else 1))

    def test_the_two_sided_gap_is_listed_as_a_tightening(self):
        self.assertEqual(self.R.TIGHTENED[-1],
                         "A14's fill gap is read as the size of the mean gap, either way (release E3): fills better than "
                         "the official-price model by more than 15 bp a side also read not consistent")

    def test_the_status_says_what_is_computed_and_what_is_not(self):
        pre = self.R.PREREGISTERED
        self.assertEqual(pre["status"], "consistency is computed since release E3 (each checkpoint's `a14`: the size of "
                                        "the mean fill gap either way, and the intents); the close-date figures are not "
                                        "computed yet and no forward rule moves a seat")
        self.assertIn("computed since release E3", pre["status"])
        self.assertIn("not computed yet", pre["status"], "still true of the close-date figures")

    def test_the_three_pinned_sentences_are_not_edited(self):
        base = importlib.import_module("league.ops.dlane_report")
        for name in ("A14_CONSISTENCY", "A14_BESIDE_DONE", "A14_SEAT_RULE"):
            self.assertEqual(getattr(self.R, name), getattr(base, name), name)
        self.assertIn("at most 15 bp a side", self.R.A14_CONSISTENCY)
        self.assertEqual({k: v for k, v in self.R.PREREGISTERED.items() if k != "status"},
                         {k: v for k, v in base.PREREGISTERED.items() if k != "status"})
        self.assertIn("THE FORWARD RECORD (release E3", self.R.__doc__)
        self.assertIn("CONSISTENCY IS COMPUTED SINCE RELEASE E3", self.R.__doc__)


class TheFunnelCarriesTheForwardRecord(unittest.TestCase):
    """11.4."""

    def setUp(self):
        import tempfile

        self.F = integrated("funnel")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_integers_only_under_forward_record(self):
        rows = {key: 3 for key in forward_report.FUNNEL_KEYS}
        with mock.patch.object(forward_report, "funnel_rows", return_value=rows) as read:
            out = self.F.window(self.root, 10.0, 20.0)
        read.assert_called_once_with(self.root, 10.0, 20.0)
        self.assertEqual(out["forward_record"], rows)
        self.assertNotIn("forward_record", out["errors"])
        self.assertEqual(release_receipts.metric(out, "forward_record.program_sessions"), 3.0)

    def test_nothing_recorded_is_zeros_not_an_error(self):
        # No forward store and no swarm store in the root: `funnel_rows` itself, unpatched.
        out = self.F.window(self.root, 10.0, 20.0)
        self.assertEqual(out["forward_record"], {key: 0 for key in forward_report.FUNNEL_KEYS})
        self.assertNotIn("forward_record", out["errors"])
        self.assertIn("swarm", out["errors"], "the swarm store is absent: its section is the error it always was")

    def test_unread_is_an_errors_entry_never_a_zero_and_the_rest_is_whole(self):
        with mock.patch.object(forward_report, "funnel_rows", side_effect=sqlite3.OperationalError("database is locked")):
            out = self.F.window(self.root, 10.0, 20.0)
        self.assertNotIn("forward_record", out)
        self.assertEqual(out["errors"]["forward_record"], "OperationalError: database is locked")
        self.assertEqual(out["book"]["orders"], {"agent": 0, "house": 0})
        self.assertIsNone(release_receipts.metric(out, "forward_record.program_sessions"))

    def test_the_other_sections_are_what_they_were(self):
        base = importlib.import_module("league.ops.funnel").window(self.root, 10.0, 20.0)
        out = self.F.window(self.root, 10.0, 20.0)
        self.assertEqual({k: v for k, v in out.items() if k != "forward_record"},
                         {k: v for k, v in base.items() if k != "forward_record"})


class TheStallJobReadsTheReceipts(unittest.TestCase):
    """11.6: `stall.run` with its edit, on the stall job's own fixture (league/tests/test_ops_stall.py)."""

    def setUp(self):
        from league.tests import test_ops_stall as T

        self.T, self.ST = T, integrated("stall")
        self.case = T.Causes("test_a_healthy_floor_raises_nothing_and_mails_nothing")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.case.healthy()
        self.release = self.case.base / "releases" / "20261012-2000-e3"
        (self.release / "docs" / "benchmarks").mkdir(parents=True)

    def declare(self, *receipts) -> None:
        (self.release / release_receipts.DECLARATIONS).write_text(json.dumps({"schema": 1, "receipts": list(receipts)}))

    def run_at(self, now: float) -> dict:
        ctx = self.case.ctx(now=now)
        ctx.release = self.release
        return self.ST.run(ctx)

    def test_the_run_declares_and_reads_and_says_so_in_its_receipt(self):
        now = self.T.NOW
        self.declare({"id": "fake-births", "release": "fake", "metric": "births", "direction": "up", "min_delta": 1,
                      "window_hours": 1})
        out = self.run_at(now)
        self.assertEqual(out["receipts"], {"declared": ["fake-births"], "read": [], "unread": [], "errors": []})
        self.assertEqual(set(out) - {"receipts"}, {"stalled", "cleared", "warned", "notice", "checks", "ceiling", "errors",
                                                   "warning"})
        later = self.run_at(now + 3600.0)
        self.assertEqual([r["id"] for r in later["receipts"]["read"]], ["fake-births"])
        self.assertIn(later["receipts"]["read"][0]["verdict"], release_receipts.VERDICTS)
        self.assertEqual([r["kind"] for r in release_receipts.rows(self.case.root)], ["declared", "read"])
        self.assertEqual(tuple(self.ST.CAUSES), tuple(importlib.import_module("league.ops.stall").CAUSES),
                         "no new stall cause: the gateway refuses a notice naming one it does not know")

    def test_a_release_with_no_declaration_writes_no_store(self):
        out = self.run_at(self.T.NOW)
        self.assertEqual(out["receipts"], {"declared": [], "read": [], "unread": [], "errors": []})
        self.assertFalse((self.case.root / release_receipts.DB).exists())

    def test_the_stall_alarm_goes_on_without_the_receipts(self):
        self.declare({"id": "fake-births", "release": "fake", "metric": "births", "direction": "up", "min_delta": 1})
        with mock.patch.object(release_receipts, "step", side_effect=RuntimeError("no receipts today")):
            out = self.run_at(self.T.NOW)
        self.assertEqual(out["receipts"], {"errors": ["RuntimeError: no receipts today"]})
        base = self.T.ST.run(self.case.ctx(now=self.T.NOW))
        for key in ("stalled", "cleared", "warned", "checks", "ceiling", "errors", "warning"):
            self.assertEqual(out[key], base[key], key)
        state = json.loads((self.case.root / self.ST.STATE_FILE).read_text())
        self.assertEqual(state["at"], S.iso(self.T.NOW), "the state file is still written")


if __name__ == "__main__":
    unittest.main()
