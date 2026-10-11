"""PACKAGE C's EDITS TO THREE EXISTING OPS FILES (release E3, the spec's 11.4, 11.5 and 11.6), held before and after
they land.

A builder edits no existing file: the integrator applies these edits. `EDITS` is each one as an exact (anchor,
replacement) pair, and `integrated(name)` is the module the tests read:
- once the integrator has applied a file's edits (its `MARKS` text is in the source), the module AS IT IS;
- until then, the same edits made on a copy of the file's source, each anchor found exactly once, and the copy
  executed as that module (never installed in `sys.modules`: nothing else sees it).
So the edits are tested on the builder's branch exactly as they will be applied, and the same tests then hold the
applied files. `TheEditsApply` fails if a file carries only some of them.

TWO BASES (`on_e1_a14`). The edits were written on release E3's step 0 (E1 and E2 as integrated at 5a6906ff): `EDITS`.
E1's review then landed a reader of its own in `dlane_report.reading` (`a14_consistency`: the fill-gap half from the
counted rows' twins, and item 4 of a reading with an equity close NOT READ, never True, "until the intents half's
reader lands"). On a tree that carries it, the same edits are seated on that code (`EDITS_ON_E1_A14`): release E3 IS
that reader, so a checkpoint's reading is handed its A14 by the meter (`reading(..., a14=)`), `a14_consistency` reads
both halves when it is, and a reading handed none (the running figures, never a Done reading) is still not read. The
tests of league/tests/test_dlane_report_a14.py hold on both. ON THAT TREE TWO OF E1's OWN TESTS HOLD THE WORDS THAT
SAID THE READER HAD NOT LANDED (league/tests/test_dlane_report_equity.py: the status' "partly computed ... has no
reader yet"; league/tests/test_equity_fx_swarm.py: item 4 "still not read until the intents half has a reader"): they
move with these edits, at the integrator's hand, and E1's other A14 tests (a gap past the bound fails item 4; a close
with no priced twin is counted) pass unchanged.

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

#: A text only a `dlane_report` that carries E1's own A14 reader holds (TWO BASES, the module docstring).
E1_A14_MARK = "def a14_consistency(counted"

_STEP0 = EDITS["dlane_report"]
#: `dlane_report`'s edits on a tree that carries E1's `a14_consistency`: the pairs of `EDITS` whose anchors did not move
#: (the forward record's bullet, the loosening and the tightening, `a14_of`, the meter's finality, whys and checkpoint
#: object, the report's section and alarms), and the four that are seated on E1's code.
EDITS_ON_E1_A14: dict[str, list[tuple[str, str]]] = {
    "funnel": EDITS["funnel"],
    "stall": EDITS["stall"],
    "dlane_report": [
        _STEP0[0],
        # (e) the module docstring's A14 paragraph: the reader has landed
        ('''  `A14_GAP_BP` in size); a mean past the bound fails item 4 ("not consistent" beside the P&L). The intents-agreement
  half has no reader yet, so until it lands item 4 of such a reading is NOT READ and never True: the reading does not
  hold, and it says why. The close-date figures and the forward seat rule are not computed either
  (`PREREGISTERED["status"]` says so in the report). A reading with no equity close is read by the pinned rule's own
  measure, as before.
''',
         '''  `A14_GAP_BP` in size); a mean past the bound fails item 4 ("not consistent" beside the P&L). CONSISTENCY IS
  COMPUTED SINCE RELEASE E3 (`a14_of`; league/ops/forward_twins.py `a14_reading`; each checkpoint's `a14`): the
  intents-agreement half's reader has landed, so a checkpoint that holds an equity close needs the SIZE of the mean
  fill gap of its priced twins within 15 bp a side, either way, AND the live and the shadow intents agreeing on 95% of
  its counted sessions, beside the pinned rule's own measure (CONSISTENT WITH REPLAY, above). The meter hands each
  checkpoint's reading its A14 (`reading(..., a14=)`); a reading handed none (the running figures, never a Done
  reading) keeps the fill-gap half and is still NOT READ. Unmeasured, unreadable or misshapen, A14 does not hold and
  the reading is not final; a frozen final reading is carried as it was. The close-date figures are not computed yet
  and no forward rule moves a seat (`PREREGISTERED["status"]` says so in the report). A reading with no equity close
  is read by the pinned rule's own measure, as before.
- THE FORWARD RECORD (release E3; league/ops/forward_report.py): `forward_record` is that job's report as it last wrote
  it (None when absent or stale), and its alarms (FW1-FW8, RR1, RR2, CP1, CP2, MM1: ids, counts and dates only) ride
  this report's `alarms`, so the `dlane` stall cause mails a warning. Read only, and never this report's failure.
'''),
        _STEP0[2],
        # (e) the status
        ('''    "status": "partly computed: a reading that holds an equity close reads item 4 by A14 and never by the options "
              "replay gap. The fill-gap half is computed from the equity twins (a mean past 15 bp a side fails item 4); "
              "the intents-agreement half has no reader yet, so item 4 of such a reading is not read and the reading "
              "does not hold. No reading carries the close-date figures, and no forward rule moves a seat",
''',
         '''    "status": "consistency is computed since release E3 (each checkpoint's `a14`: the size of the mean fill gap "
              "either way, and the intents); the close-date figures are not computed yet and no forward rule moves a "
              "seat",
'''),
        _STEP0[4], _STEP0[5], _STEP0[6],
        # (b) `reading`: a checkpoint's reading is handed its A14 by the meter
        ('''            done: Mapping[str, Any] | None = None, lanes: Lanes | None = None,
            twins: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """The Done rule over exactly `counted` (the meter's closes, in close order): {closes, programs, net_usd, net_known,
    estimate_closes, unpriced, per_program_ok, consistent_ok, holds, why, by_route, by_program, bh}."""
''',
         '''            done: Mapping[str, Any] | None = None, lanes: Lanes | None = None,
            twins: Mapping[str, Mapping[str, Any]] | None = None,
            a14: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The Done rule over exactly `counted` (the meter's closes, in close order): {closes, programs, net_usd, net_known,
    estimate_closes, unpriced, per_program_ok, consistent_ok, holds, why, by_route, by_program, bh}. `a14` (release E3):
    the forward record's A14 reading of exactly these closes (`a14_of`), handed in by the meter at a checkpoint, which
    holds item 4 to it there; with none, a reading that holds an equity close is not read (the running figures)."""
'''),
        ('''    # options bound of 0.10 is a thousand basis points of it). A fill gap past the bound fails item 4; while the
    # intents-agreement half has no reader, item 4 is not read and never True.
    a14 = a14_consistency(counted)
    if a14 is not None:
        whys.append(a14["why"])
        item4 = False
''',
         '''    # options bound of 0.10 is a thousand basis points of it). A fill gap past the bound fails item 4. RELEASE E3
    # landed the intents half's reader: a checkpoint's reading is handed its A14 by the meter (`a14`), which holds
    # item 4, the reading and its `why` to it there; a reading handed none is not read and never True.
    read = isinstance(a14, Mapping)
    a14 = a14_consistency(counted, a14 if read else None)
    if a14 is not None and not read:
        whys.append(a14["why"])
        item4 = False
'''),
        ('''def a14_consistency(counted: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """A14's READING OF "CONSISTENT WITH REPLAY" over a reading's EQUITY closes (`A14_CONSISTENCY`), or None when it
    holds none. {closes, priced, unpriced, mean_gap_bp, bound_bp, fill_gap_ok, intents {agreement, bound, status},
    consistent, why}:
''',
         '''def a14_consistency(counted: Sequence[Mapping[str, Any]], forward: Mapping[str, Any] | None = None
                    ) -> dict[str, Any] | None:
    """A14's READING OF "CONSISTENT WITH REPLAY" over a reading's EQUITY closes (`A14_CONSISTENCY`), or None when it
    holds none. {closes, priced, unpriced, mean_gap_bp, bound_bp, fill_gap_ok, intents {agreement, bound, status},
    consistent, why}. WITH `forward` (release E3: the forward record's reading of these closes, `a14_of`) BOTH HALVES
    ARE READ: the answer is that reading (applies, holds, final, why, gap, intents, by_instance) with the fill-gap half
    of these rows beside it, `consistent` and `holds` True only when it holds AND the rows' own mean gap is not past
    the bound (two readings of one gap: either saying no is no), and a `why` when they are not. Without it:
'''),
        ('''    - THE INTENTS (not read): the live and the shadow intents agreeing on at least `A14_AGREEMENT` of the counted
      sessions has no reader yet.
    - `consistent`: False when the fill gap is past its bound; else None (NOT READ: a half is missing). Never True
      until both halves are read, so `reading` never holds item 4 on equity closes by the options measure."""
''',
         '''    - THE INTENTS (not read here): the live and the shadow intents agreeing on at least `A14_AGREEMENT` of the
      counted sessions are read at a Done checkpoint, by the forward record's twins (release E3).
    - `consistent`: False when the fill gap is past its bound; else None (NOT READ: a half is missing). Never True
      until both halves are read, so `reading` never holds item 4 on equity closes by the options measure."""
'''),
        ('''    intents = {"agreement": None, "bound": A14_AGREEMENT,
               "status": "not read: the live and shadow intents have no reader yet (A14's second half)"}
    if fill_ok is False:
        why = (f"not consistent (A14): the mean fill gap is {mean:.1f} bp a side over {len(gaps)} priced equity closes, "
               f"past the {A14_GAP_BP:g} bp bound")
    else:
        measured = (f"the mean fill gap is {mean:.1f} bp a side over {len(gaps)} of {len(rows)} equity closes, inside "
                    f"the {A14_GAP_BP:g} bp bound" if mean is not None else
                    f"no equity close of {len(rows)} has a final priced twin yet")
        why = (f"item 4 is not read for a reading with equity closes (A14 pending): {measured}; the intents-agreement "
               "half has no reader yet")
''',
         '''    intents = {"agreement": None, "bound": A14_AGREEMENT,
               "status": "not read here: the live and the shadow intents are read at a Done checkpoint (A14's second "
                         "half; release E3)"}
    if fill_ok is False:
        why = (f"not consistent (A14): the mean fill gap is {mean:.1f} bp a side over {len(gaps)} priced equity closes, "
               f"past the {A14_GAP_BP:g} bp bound")
    else:
        measured = (f"the mean fill gap is {mean:.1f} bp a side over {len(gaps)} of {len(rows)} equity closes, inside "
                    f"the {A14_GAP_BP:g} bp bound" if mean is not None else
                    f"no equity close of {len(rows)} has a final priced twin yet")
        why = (f"item 4 is not read for a reading with equity closes outside a Done checkpoint: {measured}; the "
               "intents-agreement half is read at each checkpoint (release E3)")
    if isinstance(forward, Mapping):  # RELEASE E3 (`a14_of`): both halves, the rows' own fill-gap half beside them
        held = forward.get("holds") is True and fill_ok is not False
        if held:
            why = None
        elif fill_ok is not False:
            why = "; ".join(w for w in (None if mean is not None else f"no equity close of {len(rows)} has a final "
                                                                      "priced twin yet",
                                        str(forward.get("why") or "not held")) if w)
        return {**forward, "closes": len(rows), "priced": len(gaps), "unpriced": len(rows) - len(gaps),
                "mean_gap_bp": None if mean is None else round(mean, 2), "bound_bp": A14_GAP_BP, "fill_gap_ok": fill_ok,
                "consistent": held, "applies": True, "holds": held, "final": forward.get("final") is True, "why": why}
'''),
        _STEP0[7],
        # (b) the meter: the checkpoint's A14, handed to its reading
        ('''        at = reading(counted[:k], store, nightly_cache=cache, lanes=lanes, twins=twins)
''',
         '''        a14 = a14_of(store, counted[:k])
        at = reading(counted[:k], store, nightly_cache=cache, lanes=lanes, twins=twins, a14=a14)
        a14 = at.get("a14") or a14  # with an equity close: that reading, the rows' own fill-gap half beside it
'''),
        _STEP0[9], _STEP0[10], _STEP0[11], _STEP0[12],
    ],
}


def source(name: str) -> str:
    return (REPO / "league" / "ops" / f"{name}.py").read_text(encoding="utf-8")


def applied(name: str) -> bool:
    """Whether the file already carries this package's edits (the integrator applied them)."""
    return MARKS[name] in source(name)


def on_e1_a14() -> bool:
    """Whether this tree's `dlane_report` carries E1's own A14 reader (TWO BASES, the module docstring)."""
    return E1_A14_MARK in source("dlane_report")


def edits(name: str) -> list[tuple[str, str]]:
    """This package's edits to `league/ops/<name>.py` for the tree they are read in."""
    return (EDITS_ON_E1_A14 if on_e1_a14() else EDITS)[name]


def edited(name: str) -> str:
    """The file's source with this package's edits applied (as it is when they already are)."""
    text = source(name)
    if applied(name):
        return text
    for old, new in edits(name):
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


def added(old: str, new: str) -> list[str]:
    """The lines an edit adds or rewrites (those of its replacement that its anchor does not hold)."""
    kept = set(old.splitlines())
    return [line for line in new.splitlines() if line.strip() and line not in kept]


class TheEditsApply(unittest.TestCase):
    def test_every_anchor_is_found_once_or_every_edit_is_in_the_file(self):
        # Before the integrator's step: every anchor exactly once, and the edited source compiles. After it: every line
        # an edit adds is in the file (the lines AROUND an edit may have moved with a later fix of E1 or E2; the lines
        # it adds may not be missing: a file that carries only some of them fails here).
        for name in EDITS:
            text = source(name)
            lines = set(text.splitlines())
            for old, new in edits(name):
                if applied(name):
                    missing = [line for line in added(old, new) if line not in lines]
                    self.assertEqual(missing, [], f"league/ops/{name}.py carries only some of package C's edits")
                else:
                    self.assertEqual(text.count(old), 1, f"league/ops/{name}.py: {old[:80]!r}")
            compile(edited(name), f"league/ops/{name}.py", "exec")

    def test_the_edited_modules_keep_every_public_name(self):
        for name in EDITS:
            module, real = integrated(name), importlib.import_module(f"league.ops.{name}")
            self.assertEqual(sorted(module.__all__), sorted(real.__all__)) if hasattr(real, "__all__") else None
            for public in getattr(real, "__all__", ()):
                self.assertTrue(hasattr(module, public), f"{name}.{public}")

    #: The lines an edit may take away: the sentences the spec names (the A14 status and its comments), a statement
    #: it rewrites in place and, on a tree with E1's own reader, the words that said the intents half had none.
    REWRITTEN = (r"TEXT NOW|text now|text only|rule's own measure|close-date|figures, and no forward rule|None of the "
                 r"three|writes only|runs in a maintenance pause|\"holds\": at\[\"holds\"\]|\"items\": \{\*\*at|"
                 r"consistent_ok|whys = \[|\"warning\": bool|may not flip after A8|"
                 r"no reader|has no reader yet|NOT READ and never True|hold, and it says why|measure, as before|"
                 r"partly computed|replay gap\. The fill-gap half|does not hold\. No reading carries|"
                 r"not read and never True\.|a14 = a14_consistency\(counted\)|if a14 is not None:|"
                 r"twins: Mapping\[str, Mapping\[str, Any\]\] \| None = None\) -> dict|estimate_closes, unpriced, "
                 r"per_program_ok|def a14_consistency\(counted: Sequence|consistent, why\}:|THE INTENTS \(not read\)|"
                 r"sessions has no reader|\(A14 pending\)|at = reading\(counted\[:k\]|The intents-agreement$|"
                 r"says so in the report\)\. A reading with no equity close|fails item 4; while the$")

    def test_nothing_else_of_the_three_files_moves(self):
        # Each edit only adds lines, or rewrites the lines `REWRITTEN` names: on both bases.
        for table in (EDITS, EDITS_ON_E1_A14):
            for name, pairs in table.items():
                for old, new in pairs:
                    gone = [line for line in old.splitlines() if line.strip() and line not in new.splitlines()]
                    for line in gone:
                        self.assertRegex(line, self.REWRITTEN, f"{name}: {line!r}")

    def test_the_two_bases_carry_the_same_edits_where_the_code_did_not_move(self):
        self.assertEqual(EDITS_ON_E1_A14["funnel"], EDITS["funnel"])
        self.assertEqual(EDITS_ON_E1_A14["stall"], EDITS["stall"])
        shared = [pair for pair in EDITS_ON_E1_A14["dlane_report"] if pair in EDITS["dlane_report"]]
        self.assertEqual(len(shared), 10)
        # What both must add, whatever the base: the reader's guard, the checkpoint's key, the finality, the report's
        # section and alarms, the loosening, the tightening and the status.
        for table in (EDITS, EDITS_ON_E1_A14):
            text = "\n".join(new for _, new in table["dlane_report"])
            for words in ("def a14_of(store: Any, counted", 'a14 = a14_of(store, counted[:k])', '"a14": a14,',
                          'if not a14["final"]:', 'at["holds"] and item7 and a14["holds"]',
                          'out["forward_record"] = forward_report.read_section(root)', '"rule": "the equity Train bar"',
                          "A14's fill gap is read as the size of the mean gap, either way (release E3)",
                          '"status": "consistency is computed since release E3'):
                self.assertEqual(text.count(words), 1, words)
        self.assertEqual(on_e1_a14(), E1_A14_MARK in source("dlane_report"))


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
        words = " ".join(self.R.__doc__.split())
        self.assertIn("THE FORWARD RECORD (release E3", words)
        self.assertIn("CONSISTENCY IS COMPUTED SINCE RELEASE E3", words)


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
