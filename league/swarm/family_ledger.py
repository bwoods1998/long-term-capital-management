"""THE FAMILY LEDGER (research v3, Oct 2026): a family's structured memory, one row for every Train run or sweep it made.

WHY. A researcher's history is trimmed to its last few cycles and its notebook is free text it writes when it remembers
to, so families re-discovered within hours what an earlier version of themselves had already refuted (the Oct 2 deep
dive: families self-refute in a median 0.9 h). The ledger is written by the harness, never by the model, from every Train
run and sweep the family makes, with the model's one-line `expectation` beside what came back, and the whole of it is
read at every cycle (`Researcher.status`).

THE ROW. `family_ledger(seq, family, at, version, change, expectation, outcome, verdict, why)`:
- `version`: the run's version, or a sweep's versions ("12,13,14");
- `change`: what the run changed (its `why`; for a sweep, also the PARAMS keys its grid moved);
- `expectation`: the model's one line (`expectation` on gym_run and gym_sweep), else "";
- `outcome`: the Train figures that came back, in a few words (status, trades, P&L, Train score; a sweep's best row and
  its placebo row);
- `verdict`: one of `VERDICTS`: for a run `new_best`, `no_better`, `ineligible` or `failed` (a zero-trade probe too), or
  `mechanism` (its mechanism test did not pass: the test's sample figures, the broad run skipped); for a sweep with a placebo
  row that ran, `beat_placebo` (every signal row beat it on Train) or `placebo_matched` (one did not), else the run words
  (`no_placebo` when its placebo row did not complete);
- `why`: the harness's reason for the verdict.
Text fields are ASCII, one line and capped (`FIELD_CHARS`); Validation's figures are scrubbed (`diagnostics.scrub`). The
table is created on first use on the store's own connection, as the card tables are (league/swarm/cards.py), so the
store's schema (read by the live path) is unchanged. Only Train figures are ever written: Validation and the holdout
never reach a row.

THE RENDERING (`render`). Every row, oldest first, numbered within the family, under `HEADER`, within `limit`
characters (`LIMIT_CHARS`, 6,000; `researcher.ledger_chars`): when the whole does not fit, the OLDEST rows are compressed
first (their verdict and outcome only), then the oldest compressed rows are folded into one line of counts by verdict;
the newest row stays whole (a limit too small for it compresses it and cuts the text). The row's time (`at`) and the
family's id are never rendered: the researcher reads its own rows, and never a date.

Standard library only.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Mapping, Sequence

from .diagnostics import scrub

#: The rendering's ceiling unless `researcher.ledger_chars` says otherwise (0 leaves the ledger out of the status).
LIMIT_CHARS = 6000
#: A field's characters after cleaning (`clean`).
FIELD_CHARS = {"version": 60, "change": 300, "expectation": 200, "outcome": 360, "why": 300}
RUN_VERDICTS = ("new_best", "no_better", "ineligible", "failed", "mechanism")
SWEEP_VERDICTS = ("beat_placebo", "placebo_matched", "no_placebo")
VERDICTS = RUN_VERDICTS + SWEEP_VERDICTS
HEADER = ("YOUR LEDGER (written by the harness from every Train run and sweep of your family, oldest first; the oldest "
          "rows are compressed when it grows. Read it before you repeat an idea):")

#: The ledger's table, one statement each (run through the store's `_exec`, never `executescript`, which would commit a
#: caller's open transaction first).
LEDGER_SQL = (
    "CREATE TABLE IF NOT EXISTS family_ledger (seq INTEGER PRIMARY KEY AUTOINCREMENT, family TEXT NOT NULL, at TEXT NOT NULL, "
    "version TEXT NOT NULL, change TEXT NOT NULL, expectation TEXT NOT NULL, outcome TEXT NOT NULL, verdict TEXT NOT NULL, "
    "why TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS family_ledger_family ON family_ledger(family, seq)",
)


# ------------------------------------------------------------------------------------------------------------ the table
def ensure(store: Any) -> bool:
    """Create the ledger's table on the store's connection (idempotent). False on a read-only store."""
    if getattr(store, "readonly", False):
        return False
    if getattr(store, "_ledger_ready", False):
        return True
    with store.lock:
        inside = bool(store._db.in_transaction)
        for statement in LEDGER_SQL:
            store._exec(statement)
        if not inside:  # inside a caller's transaction the table is durable only once it commits
            store._ledger_ready = True
    return True


def _tables(store: Any) -> bool:
    if ensure(store):
        return True
    return bool(store._one("SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name='family_ledger'"))


def clean(value: Any, chars: int) -> str:
    """A field as the ledger keeps it: ASCII, one line, Validation's figures scrubbed, the rendering's separator
    replaced, at most `chars` characters."""
    text = unicodedata.normalize("NFKD", str(value if value is not None else "")).encode("ascii", "ignore").decode("ascii")
    text = scrub(" ".join(text.split())).replace("|", "/")
    return text if len(text) <= chars else text[:max(0, chars - 3)].rstrip() + "..."


def add(store: Any, fid: str, entry: Mapping[str, Any]) -> int:
    """Append one row for family `fid` (`entry`: version, change, expectation, outcome, verdict, why). A verdict outside
    `VERDICTS` is refused (ValueError): a row is the harness's, never free text."""
    verdict = str(entry.get("verdict") or "")
    if verdict not in VERDICTS:
        raise ValueError(f"not a ledger verdict: {verdict!r}")
    ensure(store)
    fields = {k: clean(entry.get(k), n) for k, n in FIELD_CHARS.items()}
    cur = store._exec("INSERT INTO family_ledger(family, at, version, change, expectation, outcome, verdict, why) "
                      "VALUES(?,?,?,?,?,?,?,?)", (str(fid), store.now(), fields["version"], fields["change"],
                                                 fields["expectation"], fields["outcome"], verdict, fields["why"]))
    return int(cur.lastrowid or 0)


def rows(store: Any, fid: str) -> list[dict[str, Any]]:
    """The family's rows, oldest first ([] before the table exists)."""
    if not _tables(store):
        return []
    return store._all("SELECT seq, family, at, version, change, expectation, outcome, verdict, why FROM family_ledger "
                      "WHERE family=? ORDER BY seq", (str(fid),))


# ------------------------------------------------------------------------------------------------------- the rendering
def _version(row: Mapping[str, Any]) -> str:
    v = str(row.get("version") or "").strip()
    return f"v{v}" if v else "v?"


def _full(n: int, row: Mapping[str, Any]) -> str:
    return (f"#{n} {_version(row)} {row.get('verdict')}: {row.get('change') or '-'} | expected: "
            f"{row.get('expectation') or '-'} | got: {row.get('outcome') or '-'} | why: {row.get('why') or '-'}")


def _short(n: int, row: Mapping[str, Any]) -> str:
    return f"#{n} {_version(row)} {row.get('verdict')}: {row.get('outcome') or '-'}"


def _folded(upto: int, counts: Mapping[str, int]) -> str:
    """The line the oldest `upto` rows fold into: how many, by verdict."""
    words = ", ".join(f"{k} {counts[k]}" for k in VERDICTS if counts.get(k))
    span = f"#1-#{upto}" if upto > 1 else "#1"
    return f"{span}: {upto} earlier row{'s' if upto != 1 else ''} folded ({words})"


def render(rows_: Sequence[Mapping[str, Any]], limit: int = LIMIT_CHARS) -> str:
    """The ledger as the researcher reads it (the module docstring's THE RENDERING): "" for no rows or `limit` <= 0."""
    if not rows_ or limit <= 0:
        return ""
    n = len(rows_)
    lines = [_full(i + 1, r) for i, r in enumerate(rows_)]
    size = len(HEADER) + sum(len(x) + 1 for x in lines)
    compressed = 0
    while size > limit and compressed < n - 1:  # the oldest rows first; the newest stays whole
        short = _short(compressed + 1, rows_[compressed])
        size += len(short) - len(lines[compressed])
        lines[compressed] = short
        compressed += 1
    tail = [0] * (n + 1)  # tail[k]: the characters of rows k.. as lines
    for k in range(n - 1, -1, -1):
        tail[k] = tail[k + 1] + len(lines[k]) + 1
    folded: int = 0
    counts: dict[str, int] = {}
    while size > limit and folded < n - 1:  # then fold the oldest compressed rows into counts
        verdict = str(rows_[folded].get("verdict"))
        counts[verdict] = counts.get(verdict, 0) + 1
        folded += 1
        size = len(HEADER) + len(_folded(folded, counts)) + 1 + tail[folded]
    if size > limit:  # a limit too small for the newest row whole: it is compressed too, and the text cut below
        lines[-1] = _short(n, rows_[-1])
    body = ([_folded(folded, counts)] if folded else []) + lines[folded:]
    text = "\n".join([HEADER] + body)
    return text if len(text) <= limit else text[:max(0, limit - 3)].rstrip() + "..."


def view(store: Any, fid: str, limit: int = LIMIT_CHARS) -> str:
    """The family's whole ledger, rendered (`render`)."""
    return render(rows(store, fid), limit) if limit > 0 else ""


# ------------------------------------------------------------------------------------------ rows from what came back
def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _usd(value: Any) -> str:
    x = _num(value)
    return "n/a" if x is None else f"{'-' if x < 0 else ''}${abs(x):,.0f}"


def _score(value: Any) -> str:
    x = _num(value)
    return "n/a" if x is None else f"{x:.2f}"


def _first(*values: Any) -> str:
    for v in values:
        if isinstance(v, (list, tuple)):
            v = next((x for x in v if x), None)
        if v:
            return str(v)
    return ""


def _change(args: Mapping[str, Any], label: str = "", keys: Sequence[str] = ()) -> str:
    """What a run changed: its label ("sweep"), its `why` (a starter, a rewrite and the operator's version say whose run
    it was there), and a sweep's grid keys."""
    parts = [label] if label else []
    why = str(args.get("why") or "").strip()
    if why:
        parts.append(why)
    elif not keys:
        parts.append("new code" if args.get("code") else ("params " + ", ".join(sorted(map(str, args.get("params") or {})))
                                                           if args.get("params") else "the latest version rerun"))
    if keys:
        parts.append("grid over " + ", ".join(keys))
    return "; ".join(parts)


def _mechanism_entry(view_: Mapping[str, Any], args: Mapping[str, Any]) -> dict[str, Any]:
    """The row of a gym_run whose mechanism test did not pass (gate mode: its arms were trials, the broad Train run was
    skipped): the test's own sample figures (signal against the card's comparison), never a Validation figure."""
    test = view_.get("mechanism_test") if isinstance(view_.get("mechanism_test"), Mapping) else {}
    name = str(test.get("verdict") or str(view_.get("status") or "")[len("mechanism_"):] or "failed")
    t, bound = _num(test.get("t")), _num(test.get("min_t"))
    outcome = (f"mechanism test {name}: t {'n/a' if t is None else f'{t:.2f}'}"
               + ("" if bound is None else f" against {bound:.2f}")
               + f", {test.get('signal_days', 'n/a')} signal days, {test.get('comparison_days', 'n/a')} comparison days; "
               "the broad Train run skipped")
    return {"version": str(view_.get("version") or ""), "change": _change(args), "expectation": args.get("expectation"),
            "outcome": outcome, "verdict": "mechanism", "why": _first(test.get("why"), view_.get("next"), name)}


def run_entry(view_: Any, args: Mapping[str, Any], *, best: Any = None) -> dict[str, Any] | None:
    """The row of one gym_run's answer, or None when it made no new Gym evaluation (refused, held, stored, a Gym error).
    A mechanism test that stopped it (its arms were trials) is a `mechanism` row; a zero-trade probe a `failed` row.
    `best`: the family's best Train score after it (the `no_better` reason)."""
    if not isinstance(view_, Mapping) or view_.get("already_run"):
        return None
    status = str(view_.get("status") or "")
    if status.startswith("mechanism_"):
        return _mechanism_entry(view_, args)
    if not view_.get("run_id") or status in ("", "refused", "held", "retired", "gym_error"):
        return None
    s = view_.get("summary") if isinstance(view_.get("summary"), Mapping) else {}
    score = view_.get("train_score") if isinstance(view_.get("train_score"), Mapping) else {}
    if status != "ok":
        reason = _first(view_.get("reason"), (view_.get("runtime") or {}).get("messages") if isinstance(view_.get("runtime"), Mapping) else None,
                        status)
        outcome, verdict, why = status, "failed", reason
    else:
        eligible = bool(score.get("eligible"))
        outcome = (f"ok, {s.get('trades', 'n/a')} trades on {s.get('days_traded', 'n/a')} days, P&L {_usd(s.get('pnl'))}, "
                   f"Train score {_score(score.get('score'))} ({'eligible' if eligible else 'not eligible'})")
        if view_.get("new_best_train_score") is not None:
            verdict, why = "new_best", f"its Train score {_score(view_['new_best_train_score'])} is the family's best"
        elif eligible:
            verdict, why = "no_better", f"eligible, at or below the family's best Train score {_score(best)}"
        else:
            verdict, why = "ineligible", str(score.get("why_not_eligible") or "not eligible under the Train score")
    return {"version": str(view_.get("version") or ""), "change": _change(args), "expectation": args.get("expectation"),
            "outcome": outcome, "verdict": verdict, "why": why}


def sweep_entry(view_: Any, args: Mapping[str, Any], *, best: Any = None) -> dict[str, Any] | None:
    """The row of one gym_sweep's answer, or None when it made no new Train run (refused, a Gym error, every variant read
    back from the store)."""
    if not isinstance(view_, Mapping) or not isinstance(view_.get("table"), list) or view_.get("already_run"):
        return None
    table = [r for r in view_["table"] if isinstance(r, Mapping)]
    signal = [r for r in table if r.get("label") != "placebo"]  # an earlier sweep's placebo read back is no signal row
    mine = view_.get("placebo") if isinstance(view_.get("placebo"), Mapping) else {}
    placebo = next((r for r in table if r.get("label") == "placebo" and mine and r.get("version") == mine.get("version")), None)
    keys = sorted({str(k) for r in signal for k in (r.get("params") or {})})
    versions = sorted({int(r["version"]) for r in table if isinstance(r.get("version"), int)})
    ok = [r for r in table if r.get("status") == "ok"]
    head = next((r for r in signal if r.get("eligible")), None) or next((r for r in signal if r.get("status") == "ok"), None)
    outcome = f"{len(ok)} of {len(table)} rows ok, {sum(1 for r in signal if r.get('eligible'))} eligible"
    if head is not None:
        outcome += f"; best signal row v{head.get('version')} score {_score(head.get('score'))} P&L {_usd(head.get('pnl'))}"
    if placebo is not None:
        traded = int(placebo.get("trades") or 0) > 0
        outcome += (f"; placebo v{placebo.get('version')} {placebo.get('status')} score {_score(placebo.get('score'))} "
                    f"P&L {_usd(placebo.get('pnl'))}{'' if traded else ' (no trade)'}")
    if view_.get("new_best_train_score") is not None:
        outcome += f"; new best {_score(view_['new_best_train_score'])}"
    every = view_.get("every_signal_row_beat_placebo")
    if not ok:
        verdict, why = "failed", _first([r.get("reason") for r in table], "no row completed")
    elif placebo is not None and every is True:
        verdict, why = "beat_placebo", "every signal row's Train P&L and Train score were above the placebo row's"
    elif placebo is not None and every is False:
        lost = [f"v{r.get('version')}" for r in signal if r.get("beats_placebo") is not True]
        verdict, why = "placebo_matched", f"{', '.join(lost)} did not beat the placebo row on Train: that part is not your signal"
    elif placebo is not None:
        verdict, why = "no_placebo", f"the placebo row did not complete ({placebo.get('status')}): no comparison"
    elif view_.get("new_best_train_score") is not None:
        verdict, why = "new_best", f"its best row's Train score {_score(view_['new_best_train_score'])} is the family's best"
    elif any(r.get("eligible") for r in signal):
        verdict, why = "no_better", f"eligible rows, none above the family's best Train score {_score(best)}"
    else:
        verdict, why = "ineligible", _first([r.get("why_not") for r in signal], "no row eligible under the Train score")
    if placebo is not None and int(placebo.get("trades") or 0) == 0 and placebo.get("status") == "ok":
        why += "; the placebo made no trade (the switch turned the program off), so it compared against doing nothing"
    return {"version": ",".join(map(str, versions)), "change": _change(args, "sweep", keys),
            "expectation": args.get("expectation"), "outcome": outcome, "verdict": verdict, "why": why}


__all__ = ["LIMIT_CHARS", "VERDICTS", "HEADER", "ensure", "clean", "add", "rows", "render", "view", "run_entry", "sweep_entry"]
