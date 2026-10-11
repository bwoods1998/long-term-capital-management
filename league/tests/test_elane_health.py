"""Release E2.4, THE EQUITY LANES' HEALTH (league/ops/elane_health.py): the equity lanes' own stall causes (`elane_dq`,
`elane_births`, `elane_idle`, `elane_refused`) raised through the stall job's machinery (league/ops/stall.py), each judged
only while the lanes are on and on enough evidence; the notice that carries them under a cause the gateway words; the
Done meter's item 7 counting their owner steps; the lanes' research funnel (league/ops/funnel.py `equity.research`, the
stall receipt's `elane.funnel`); and the operator's report. The closed words are held to the code that writes the
records (the equity pass, the Train round, the static rules, a disqualification's record) by running that code.

Every family, program, refusal, dollar and number here is invented."""

from __future__ import annotations

import io
import json
import math
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from league.ops import dlane_report as R
from league.ops import elane_health as EH
from league.ops import funnel as FN
from league.ops import guard
from league.ops import scoreboard as SB
from league.ops import stall as ST
from league.ops.context import Context
from league.ops.store import OpsStore
from league.swarm import elane_births, elane_train, elane_yield
from league.swarm.architect import Architect
from league.swarm.elane_births import LAST_KEY, EquityPass, EquityQuota
from league.swarm.elane_train import EquityResearcher
from league.swarm.store import SwarmStore, iso
from league.tests import elane_e2_fakes as fx
from league.tests import test_ops_stall as TS

NOW, HOUR = TS.NOW, TS.HOUR
REPO = Path(__file__).resolve().parents[2]
ROUTE = "sail:pro_asap"
#: Invented programs, each the fakes' program with one fault a static rule names. `zebra` is a name no rule's sentence
#: and no notice may repeat: it is the program's own.
BY_KEY = fx.PROGRAM.replace("    out = [", '    zebra = ctx.bars["SPY"]["close"]\n    out = [', 1)
AS_ROWS = fx.PROGRAM.replace("    out = [", '    for zebra in ctx.bars["SPY"]:\n        pass\n    out = [', 1)
LOT_ATTR = fx.PROGRAM.replace('lot["id"]', "lot.id")
LEVEL = fx.PROGRAM.replace("    out.append(", '    if ctx.prices["SPY"] > 412.5:\n        return []\n    out.append(', 1)
MEMORY = fx.PROGRAM.replace("    out = [", "    zebra = np.typecodes\n    out = [", 1)
#: An invented exception text: a program chooses it, so no record, receipt or notice may carry it.
SECRET = "an invented message a program chose"


def refusal(code: str, symbols: tuple[str, ...] = ("SPY",)) -> str:
    """The static rules' own refusal of an invented program (`elane_train.check_code`: the text the record keeps)."""
    why = elane_train.check_code(code, list(symbols))
    assert why is not None, "the invented program is refused"
    return why


def verdict(hours: float, *fails: str, reason: str | None = None) -> dict:
    """A version's verdict as E2's record keeps it (`elane_train.compact`), scored `hours` before NOW: a program fault
    (DQ, LOAD, RUN) through E2's own `program_fault` and `dq_said`, else the bar's fails (none: a pass)."""
    at = iso(NOW - hours * HOUR)
    if fails == ("DQ",):
        reason = f"25 errors (first: line 12: TypeError: {SECRET})" if reason is None else reason
        return elane_train.compact(elane_train.program_fault("DQ", reason, said=elane_train.dq_said(reason)), at=at)
    if fails and fails[0] in ("LOAD", "RUN"):
        return elane_train.compact(elane_train.program_fault(fails[0], "an invented fault", said="an invented fault"), at=at)
    return elane_train.compact({"passed": not fails, "fails": list(fails)}, at=at)


def refused_step(fid: str, why: str) -> dict:
    return {"family": fid, "refused": why, "route": ROUTE}


def scored_step(fid: str, n: int, *fails: str, passed: bool | None = None) -> dict:
    return {"family": fid, "version": n, "route": ROUTE,
            "score": {"family": fid, "version": n, "passed": (not fails) if passed is None else passed, "fails": list(fails)}}


def gateway_causes() -> list[str]:
    """The causes the gateway has words for (gateway/lib/email.mjs STALL_CAUSES), read from its source."""
    source = (REPO / "gateway" / "lib" / "email.mjs").read_text()
    block = re.search(r"export const STALL_CAUSES = \{(.*?)\n\};", source, re.S)
    assert block, "gateway/lib/email.mjs names its stall causes in one object"
    return re.findall(r"^\s+([a-z_]+):", block.group(1), re.M)


def figure(value) -> str:
    """A stall figure as the gateway echoes it (gateway/lib/email.mjs `figure`): a decimal, a date or time, yes or no, a
    short lower-case token, else "unknown"."""
    if value is True or value is False:
        return "yes" if value else "no"
    text = str(value) if isinstance(value, (int, float)) and math.isfinite(value) else value
    if isinstance(text, str) and re.fullmatch(r"-?\d{1,12}(\.\d{1,6})?", text):
        return text
    if isinstance(text, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}(T[0-9:.]{2,15}Z)?", text):
        return text
    return text if isinstance(text, str) and re.fullmatch(r"[a-z0-9_.,:-]{1,80}", text) else "unknown"


class Case(TS.Base):
    """A House whose options lanes stall on nothing, with the equity lanes on in swarm.json and a swarm that started
    two days ago."""

    def setUp(self):
        super().setUp()
        self.lanes(mode="gate", birth_share=0.25)
        self.beat(48)
        self.healthy()

    def lanes(self, **block):
        (self.root / "swarm.json").write_text(json.dumps({"elane": block}))

    def beat(self, hours: float, at: float = NOW):
        """The swarm's heartbeat, written at `at`: it started `hours` before NOW."""
        (self.root / EH.HEARTBEAT).write_text(json.dumps({"at": at, "started_at": NOW - hours * HOUR}))

    def run_at(self, now=NOW, **kw):
        """One stall run at `now`, the swarm alive then (its heartbeat fresh) unless a test wrote a stale one."""
        path = self.root / EH.HEARTBEAT
        beat = json.loads(path.read_text()) if path.exists() else {}
        if beat.get("at") == NOW:
            self.beat((NOW - beat["started_at"]) / HOUR, at=now)
        out = super().run_at(now=now, **kw)
        if beat.get("at") == NOW:
            self.beat((NOW - beat["started_at"]) / HOUR)
        return out

    def bred(self, slug: str, *, hours: float = 10.0, lane: str = "equity", symbols=("SPY",), record=None) -> str:
        """An equity family as the equity pass bears it, born `hours` before NOW, with E2's record of it."""
        self.ago(hours)
        fam = fx.e2_family(self.store, slug, lane=lane, symbols=symbols,
                           record=record or {"status": "researching", "versions": {}})
        return fam["id"]

    def record(self, fid: str, **change) -> None:
        rec = dict(self.store.family(fid)["state"].get(EH.STATE_KEY) or {})
        for key, value in change.items():
            rec[key] = {**rec.get(key, {}), **value} if isinstance(value, dict) and key == "versions" else value
        self.store.set_state(fid, **{EH.STATE_KEY: rec})

    def births(self, hours: float, *, born=(), refused=(), proposed=None, truncated=False, error=False, skipped=None,
               want: int = 3) -> None:
        """One equity pass's event, as `EquityPass.run` writes it, `hours` before NOW."""
        self.ago(hours)
        quota = {"equity_want": want, "equity_short": max(0, want - len(born)), "researching": 0}
        if skipped:
            payload = {"pass": "births", "skipped": skipped, "why": "an invented reason"}
        elif error:
            payload = {"pass": "births", "born": [], "error": "no route answered", "errors": ["invented"], **quota}
        else:
            payload = {"pass": "births", "born": list(born), "route": ROUTE, "cost_usd": 0.11, "truncated": truncated,
                       "proposed": len(born) + len(refused) if proposed is None else proposed,
                       "refused": {"count": len(refused), "items": [{"slug": s, "why": w} for s, w in refused]}, **quota}
        self.store.event("swarm.elane", None, payload)

    def round(self, hours: float, *steps: dict) -> None:
        """One Train round's event, as `EquityResearcher.run` writes it, `hours` before NOW."""
        self.ago(hours)
        self.store.event("swarm.elane", None, {"pass": "train", "steps": list(steps)})

    def spend(self, hours: float, usd: float, purpose: str = "train") -> None:
        """A model dollar of E2's, booked `hours` before NOW under one of its request keys."""
        self.ago(hours)
        self.store.add_spend("sail_model", usd, detail={"key": f"swarm:elane:{purpose}:invented:1:{ROUTE}"})

    def equity(self, **kw) -> dict:
        """One stall run's equity checks (among the receipt's `checks`)."""
        out, _ = self.run_at(**kw)
        return self.own(out)

    @staticmethod
    def own(out: dict) -> dict:
        """The equity causes' checks of a stall receipt, each with `judged` (its numbers') beside `stalled`."""
        return {cause: {**out["checks"][cause], "judged": out["checks"][cause]["numbers"]["judged"]} for cause in EH.CAUSES}

    def told(self) -> str:
        """Everything the House sent to the gateway, as text."""
        return json.dumps(self.notify.calls)

    def damning(self) -> None:
        """Evidence on which all four causes would stand, were they judged."""
        a, b = self.bred("dq-a"), self.bred("dq-b")
        for fid in (a, b):
            self.record(fid, versions={str(n): verdict(1.0 + n / 10.0, "DQ") for n in range(1, 5)})
        for hours in (5.0, 4.0, 3.5, 3.4):
            self.births(hours, refused=[("far", "symbols: 1 to 20 of SPY, QQQ, IWM, DIA (XLK not)")])
        self.round(3.2, *[refused_step(a, refusal(BY_KEY)) for _ in range(9)])


# ---------------------------------------------------------------------------------------------- the closed words
class TheWords(unittest.TestCase):
    """What this module spells of E2's vocabulary is E2's own, and what it reads back is what E2 wrote."""

    def test_the_vocabulary_is_e2s_own(self):
        from league.equity import LANES
        from league.swarm import elane

        self.assertEqual(EH.LANES, tuple(LANES))
        self.assertEqual(FN.EQUITY_LANES, EH.LANES)
        self.assertEqual((EH.STATE_KEY, EH.ROUTE_KEY), (elane_train.STATE_KEY, elane_yield.ROUTE_KEY))
        self.assertEqual((EH.BIRTHS_AT_KEY, EH.TRAIN_AT_KEY, EH.TRAIN_OK_KEY),
                         (elane_births.BIRTHS_AT_KEY, elane_train.TRAIN_AT_KEY, elane_train.TRAIN_OK_KEY))
        self.assertEqual((EH.SPEND_MARK, EH.SPEND_KINDS), (elane_yield.SPEND_MARK, elane_yield.SPEND_KINDS))
        self.assertTrue(elane_yield.DAY_SPENT.startswith(EH.DAY_SPENT))
        self.assertEqual(EH.SAIL_DAY, elane_yield.SAIL_DAY)
        self.assertEqual(EH.ERROR_CLASSES, elane_train.ERROR_CLASSES)
        self.assertEqual(set(EH.BAR_CODES), {*elane_train.JUDGED, "STATE"})
        for code in (*EH.PROGRAM_FAULTS, *EH.BAR_CODES):
            self.assertIn(code, elane_train.FAILS)
        self.assertEqual(EH.ARCHITECT_PROGRAM, "the architect's program: ")
        self.assertIn(f'f"{EH.ARCHITECT_PROGRAM}{{why_code}}"', (REPO / "league/swarm/elane_births.py").read_text())
        loop = (REPO / "league/swarm/loop.py").read_text()
        for name in EH.ROUNDS:
            self.assertIn(f'self._round("{name}", ', loop, "the loop's own name of the round")
        self.assertEqual(EH.HEARTBEAT, ST.HEARTBEAT)
        self.assertEqual(EH.SWARM_DB, FN.SWARM_DB)
        self.assertEqual(set(elane.MODES), {"off", "gate"})

    def test_a_disqualification_is_read_back_into_its_closed_class(self):
        def said(reason: str) -> str:
            return verdict(1.0, "DQ", reason=reason)["why"]

        self.assertEqual(EH.dq_class(said(f"25 errors (first: line 12: TypeError: {SECRET})")), "TypeError")
        self.assertEqual(EH.dq_line(said(f"25 errors (first: line 12: TypeError: {SECRET})")), 12)
        self.assertEqual(EH.dq_class(said("25 errors (first: line 40: KeyError: 'XLK')")), "KeyError")
        self.assertEqual(EH.dq_class(said("3 errors (first: decide ran past 1.0 s)")), "time limit")
        self.assertEqual(EH.dq_class(said("25 errors (first: malformed intent: an intent is a dict)")), "malformed intent")
        self.assertEqual(EH.dq_class(said("25 errors (first: decide returned a str; it returns a list of intents)")),
                         "no list of intents")
        self.assertEqual(EH.dq_class(said("25 errors (first: decide returned 99 intents; only the first 50 count)")),
                         "too many intents")
        self.assertEqual(EH.dq_class(said("decide used 61.0 s of the run's 60 s budget")), "time budget")
        # A class a program made up, and a record that names none, are unnamed: nothing a program chose is repeated.
        for reason in ("25 errors (first: line 3: WireMoneyNow: do it)", "", "something else"):
            self.assertEqual(EH.dq_class(said(reason)), EH.UNNAMED, reason)
        self.assertIsNone(EH.dq_line(said("")))
        for reason in (f"25 errors (first: line 12: TypeError: {SECRET})", "25 errors (first: line 3: WireMoneyNow: do it)"):
            self.assertNotIn("WireMoneyNow", EH.dq_class(said(reason)))
            self.assertNotIn(SECRET, said(reason), "E2's record never keeps the exception's text")

    def test_a_static_refusal_is_read_into_its_rule_and_closed_sentences(self):
        by_key = "a symbol's bars read by key (ctx.bars[sym] is ONE object: its arrays are read by attribute)"
        cases = {
            BY_KEY: ("reading", [(9, by_key, "TypeError")]),
            AS_ROWS: ("reading", [(9, "a symbol's bars iterated as rows", "TypeError")]),
            LOT_ATTR: ("reading", [(9, "a lot read by attribute (a lot is a dict)", "AttributeError")]),
            fx.PROGRAM.replace("    return out", "    return {}"):
                ("reading", [(11, "an empty dict returned for no order (return [])", None)]),
            LEVEL: ("level", [(10, "a price or volume level held against a constant or a PARAMS value", None)]),
            MEMORY: ("memory", [(9, "an object of numpy or math held as a value (memory outside STATE)", None)]),
            fx.PROGRAM.replace('"symbols": ["SPY"]', '"symbols": ["SPY", "QQQ"]'):
                ("needs", [(None, "NEEDS naming a symbol outside the family's own", None)]),
            "import os\n" + fx.PROGRAM: ("code", [(1, "an import other than math or numpy", None)]),
            fx.PROGRAM.replace("def decide(ctx)", "def choose(ctx)"): ("code", [(None, "no single top-level decide(ctx)", None)]),
        }
        for code, (rule, told) in cases.items():
            why = refusal(code)
            self.assertEqual((EH.rule_of(why), EH.sentences(why)), (rule, told), why[:120])
            # The architect's program at birth is read past its prefix.
            self.assertEqual(EH.rule_of(EH.ARCHITECT_PROGRAM + why), rule)
            for _, words, _ in EH.sentences(why):
                self.assertNotIn("zebra", words, "a rule's sentence quotes the program; this module's words never do")
        # Two faults in one refusal are two sentences, each with its line.
        both = refusal(BY_KEY.replace('lot["id"]', "lot.id"))
        self.assertEqual([(line, raises) for line, _, raises in EH.sentences(both)], [(9, "TypeError"), (10, "AttributeError")])
        # What is no rule's refusal, and a rule a later release names.
        self.assertEqual([EH.rule_of(w) for w in ("the answer held no program", "the same program as v2, already scored",
                                                  "a stop is accepted only once a version was judged by the bar")],
                         ["no_program", "same_program", "early_stop"])
        self.assertEqual(EH.rule_of("refused by the equity start rule (an invented later rule): line 4: invented"), "start")
        self.assertEqual((EH.rule_of("words nobody wrote"), EH.sentences("words nobody wrote")), (EH.OTHER, []))
        # A sentence this table does not know is named as another one, never repeated.
        odd = "refused before it ran by the equity reading rule (x): line 5: `zebra` does something new"
        self.assertEqual(EH.sentences(odd), [(5, EH.ANOTHER, None)])

    def test_every_marker_of_a_rule_is_still_in_the_code_that_writes_it(self):
        sources = {"reading": "league/swarm/elane_review.py", "level": "league/swarm/elane_review.py",
                   "memory": "league/swarm/elane_review.py", "code": "league/gym/safety.py",
                   "needs": "league/swarm/elane_train.py"}
        for rule, table in EH.SENTENCES.items():
            # The source as its strings read once joined: quotes escaped in it are plain, adjacent literals are one.
            source = (REPO / sources[rule]).read_text().replace('\\"', '"')
            source = re.sub(r'"\s*\n\s*f?"', "", source)
            for mark, words in table:
                self.assertIn(mark, source, f"{rule}: the rule no longer says {mark!r}")
                self.assertTrue(words and "`" not in words, words)

    def test_the_lanes_reasons_for_asking_no_model_are_read_by_kind(self):
        self.assertEqual(EH.skip_kind(elane_yield.DAY_SPENT), "usd_day")
        with tempfile.TemporaryDirectory() as tmp:
            store = SwarmStore(tmp, clock=lambda: NOW)
            self.addCleanup(store.close)
            settings = {"elane": {"e2": {"pace_share": 0.25}}, "researcher": {"sail_usd_per_hour": 0.4}}
            store.add_spend("sail_model", 0.2, detail={"key": f"swarm:elane:train:invented:1:{ROUTE}"})
            self.assertEqual(EH.skip_kind(elane_yield.pace(store, settings, NOW)["reason"]), "pace")
            self.assertEqual(EH.skip_kind(elane_yield.hold(store, settings, NOW)), "pace")
            store.put(elane_yield.GUARD_KEY, {"braked": True, "reason": "an invented brake"})
            held = elane_yield.sail_day(store, settings, NOW)
            self.assertEqual((EH.skip_kind(held), EH._sail_words(held)), ("sail_day", "the Sail guard is braked"))
        self.assertEqual((EH.skip_kind(None), EH.skip_kind("its passing version cannot be read")), (None, EH.OTHER))


class TheAdmissionsWords(unittest.TestCase):
    """`REFUSALS` against the equity pass's own admission: every way it refuses a proposal reads into a class."""

    def setUp(self):
        fx.switch_on(self)
        self.clock = fx.Clock()
        self.store = fx.new_store(self, self.clock)
        self.settings = fx.settings(max_per_pass=2, min_per_pass=2)
        self.settings["elane"]["universe"] = ["SPY", "QQQ", "IWM", "DIA"]
        self.answers: list = []
        self.router = fx.FakeRouter(lambda call: self.answers.pop(0) if self.answers else fx.answer([]))
        self.arch = Architect(self.store, self.router, self.settings, clock=self.clock)

    def test_each_refusal_of_the_admission_has_its_class_and_the_models_words_are_never_repeated(self):
        fx.e2_family(self.store, "held", symbols=("QQQ",), mechanism="Invented mechanism busy: holders are paid overnight.")
        rows = [
            fx.proposal("wirefunds-lane", lane="margin"),
            fx.proposal("wirefunds-structure") | {"structure": "stock"},
            fx.proposal("wirefunds-symbols", symbols=("SPY", "XLK", "XLF", "ZZZZ")),
            fx.proposal("wirefunds-agenda", agenda="astrology"),
            fx.proposal("wirefunds-data", agenda="earnings_drift", lane="equity"),
            fx.proposal("wirefunds-mechanism", mechanism="too short"),
            fx.proposal("wirefunds-busy", symbols=("QQQ",), mechanism="Invented mechanism busy: holders are paid overnight."),
            fx.proposal("wirefunds-card") | {"card": {"lane": "beta", "structure": "etf", "symbols": ["IWM"]}, "symbols": ["IWM"]},
        ]
        rows += [fx.proposal(f"fine-{i}", symbols=(sym,), mechanism=f"Invented idea number {i}: a premium for holding {sym}.")
                 for i, sym in enumerate(("SPY", "IWM", "DIA"))]
        self.answers.append(fx.answer(rows))
        out = self.arch.equity_pass()
        whys = {r["slug"]: r["why"] for r in out["refused"]["items"]}
        expect = {"wirefunds-lane": "lane", "wirefunds-structure": "structure", "wirefunds-symbols": "symbols",
                  "wirefunds-agenda": "agenda", "wirefunds-data": "agenda", "wirefunds-mechanism": "mechanism",
                  "wirefunds-busy": "same_idea", "wirefunds-card": "card"}
        for slug, name in expect.items():
            self.assertEqual(EH.refusal_class(whys[slug]), name, whys[slug])
        quota = [why for slug, why in whys.items() if slug.startswith("fine-")]
        self.assertEqual(len(quota), 1, "a third sound proposal is one more than the pass's two births")
        self.assertEqual({EH.refusal_class(w) for w in quota}, {"quota"})
        self.assertNotIn(EH.OTHER, {EH.refusal_class(w) for w in whys.values()})
        # The symbols the code knows and the universe does not hold are named; one a model made up is not.
        self.assertEqual(EH.foreign_symbols(whys["wirefunds-symbols"]), ["XLK", "XLF"])
        self.assertEqual(EH.foreign_symbols(whys["wirefunds-lane"]), [])
        # The pass as the reader holds it: asked, 2 born of 11 proposed (9 refused), nothing barren.
        read = EH.pass_read(out)
        self.assertEqual((read["asked"], read["born"], read["proposed"], read["refused"], read["barren"], read["how"]),
                         (True, 2, 11, 9, False, None))
        for words in EH.REFUSAL_WORDS.values():
            self.assertNotIn("wirefunds", words)

    def test_a_tried_lineage_and_a_closed_cell_have_their_classes(self):
        tried = "it continues an-invented-family's lineage, which has its one Validation try (outcome sealed): propose a different idea"
        reborn = "its rebirth continues an-invented-family's lineage, which has its one Validation try (outcome sealed)"
        closed = "its cell equity / trend / index is CLOSED: refuted on Train too often with no pass"
        self.assertEqual([EH.refusal_class(w) for w in (tried, reborn, closed, "graveyard: a refuted row binds its cell",
                                                        "not born: ValueError: invented")],
                         ["tried_lineage", "tried_lineage", "closed_cell", "graveyard", "store"])
        source = (REPO / "league/swarm/elane_births.py").read_text()
        for start in ("it continues ", "its rebirth continues ", "its cell ", "graveyard: ", "not born: ", "card: "):
            self.assertIn(f'f"{start}', source.replace('"' + start, 'f"' + start), start)


# ---------------------------------------------------------------------------------------------- no false alarm
class AQuietLaneIsNotJudged(Case):
    """No false alarm: lanes with nothing to judge read "Not judged", stand on nothing and mail nothing."""

    def quiet(self, why: str, **kw) -> dict:
        out, ctx = self.run_at(**kw)
        checks = self.own(out)
        self.assertEqual(set(out["checks"]), {*ST.CAUSES, *EH.CAUSES})
        for cause, check in checks.items():
            self.assertEqual((check["stalled"], check["judged"]), (False, False), cause)
            self.assertIn("Not judged: ", check["what"])
            self.assertIn(why, check["what"], cause)
            self.assertIsNone(check["owner_step"])
        self.assertEqual((out["stalled"], self.notify.calls, ctx.alerts), ([], [], []))
        return checks

    def test_an_empty_population_is_not_judged(self):
        self.quiet("the equity lanes hold no family and no equity pass is on record")

    def test_a_lane_switched_off_is_not_judged(self):
        self.damning()
        self.lanes(mode="off", birth_share=0.25)
        self.quiet("the equity lanes are off (elane.mode)")
        self.lanes(mode="gate", birth_share=0.0)
        self.quiet("the equity lanes' births are off (elane.birth_share is 0)")
        (self.root / "swarm.json").unlink()
        self.quiet("the equity lanes are off (elane.mode)")  # the release ships them off

    def test_a_house_that_just_started_is_not_judged(self):
        self.damning()
        self.beat(0.5)
        out, ctx = self.run_at()
        checks = self.own(out)
        self.assertEqual((out["stalled"], self.notify.calls, ctx.alerts), ([], [], []))
        for cause in EH.CAUSES:
            self.assertEqual((checks[cause]["stalled"], checks[cause]["judged"]), (False, False), cause)
        self.assertIn("0 equity versions were scored in the 0.5 h since the swarm started", checks["elane_dq"]["what"])
        self.assertIn("0 equity passes asked a model in the 0.5 h since the swarm started", checks["elane_births"]["what"])
        self.assertIn("the swarm started 0.5 h ago", checks["elane_idle"]["what"])
        self.assertIn("wrote 0 programs in the 0.5 h since the swarm started", checks["elane_refused"]["what"])
        # The same evidence under a swarm that has been up for days stands.
        self.beat(48)
        self.assertEqual({c for c, check in self.equity().items() if check["stalled"]},
                         {"elane_dq", "elane_births", "elane_refused"})

    def test_a_weekend_with_the_lanes_deliberately_paused_is_not_judged(self):
        self.damning()
        for name in ("PAUSE", "swarm.stop"):
            (self.root / name).write_text("")
            out, _ = self.run_at()
            for cause, check in self.own(out).items():
                self.assertEqual((check["stalled"], check["judged"]), (False, False), (name, cause))
                self.assertIn("Not judged: the floor is paused", check["what"])
            self.assertEqual(self.notify.calls, [])
            (self.root / name).unlink()
        for key in ("usd_day", "pace_share"):
            self.lanes(mode="gate", birth_share=0.25, e2={key: 0})
            self.quiet("the equity lanes' model dollars are set to zero (elane.e2.usd_day or elane.e2.pace_share)")

    def test_the_owners_switch_in_ops_json_stops_the_four_and_nothing_else(self):
        self.damning()
        ctx = self.ctx()
        ctx.settings = {"stall": {"elane": False}}
        out = ST.run(ctx)
        for check in self.own(out).values():
            self.assertEqual((check["stalled"], check["what"]), (False, "Not judged: switched off (ops.json stall.elane is false)."))
        self.assertEqual((out["stalled"], self.notify.calls), ([], []))
        self.assertTrue(all(cause in out["checks"] for cause in ST.CAUSES))
        ctx = self.ctx()
        ctx.settings = {"stall": {"elane": True}, "jobs": {}}
        self.assertTrue(ST.run(ctx)["stalled"], "anything but false: judged")
        (self.root / "ops.json").write_text(json.dumps({"stall": {"elane": False}}))
        doc = EH.report(self.root, now=NOW)
        self.assertEqual((doc["judged"], doc["why"]), (False, "switched off (ops.json stall.elane is false)"))

    def test_a_tree_without_e2s_rounds_is_not_judged(self):
        self.damning()
        with mock.patch.object(Architect, "equity_pass", None):
            self.quiet("release E2's rounds are not in the running tree")

    def test_lanes_that_cannot_be_read_are_an_error_and_never_a_failed_run(self):
        self.damning()
        with mock.patch.object(EH, "facts", side_effect=RuntimeError("an invented failure")):
            out, _ = self.run_at()
        self.assertIn("the equity lanes' health could not be read (RuntimeError)", out["errors"])
        for check in self.own(out).values():
            self.assertEqual((check["stalled"], check["judged"]), (False, False))
        self.assertEqual(out["stalled"], [])
        self.assertTrue(all(cause in out["checks"] for cause in ST.CAUSES), "the stall alarm goes on")
        # Settings that could not be loaded: not judged either.
        self.assertEqual(EH.lanes(None)[:2], (False, "the swarm's settings could not be read"))


# ---------------------------------------------------------------------------------------------- elane_dq
class MostVersionsDisqualified(Case):
    def faulted(self) -> tuple[str, str]:
        """Two families, eight versions scored in the last six hours: five disqualified on a TypeError, one on a
        KeyError, one refused at load, one judged by the bar."""
        a, b = self.bred("alpha-one"), self.bred("beta-two", lane="beta")
        self.record(a, versions={"1": verdict(5.0, "DQ"), "2": verdict(4.0, "DQ"), "3": verdict(3.0, "DQ"),
                                 "4": verdict(2.0, "DQ", reason="25 errors (first: line 40: KeyError: 'XLK')")})
        self.record(b, versions={"1": verdict(2.5, "DQ"), "2": verdict(2.0, "DQ"), "3": verdict(1.5, "LOAD"),
                                 "4": verdict(1.0, "Y1", "P1")})
        return a, b

    def test_most_scored_versions_disqualified_is_the_owners_step_naming_the_class_and_the_sentence(self):
        a, _ = self.faulted()
        self.round(2.0, refused_step(a, refusal(BY_KEY)), refused_step(a, refusal(BY_KEY)), refused_step(a, refusal(LOT_ATTR)))
        self.ago(1.0)
        self.store.event("swarm.elane", a, {"pass": "stalled", "codes": ["DQ"], "versions": 4})
        out, ctx = self.run_at()
        check = self.own(out)["elane_dq"]
        self.assertTrue(check["stalled"] and check["judged"])
        self.assertEqual({k: check["numbers"][k] for k in ("scored", "faulted", "disqualified", "load_refused", "run_failed",
                                                           "share", "families", "retired_stalled", "top_error", "top_error_n")},
                         {"scored": 8, "faulted": 7, "disqualified": 6, "load_refused": 1, "run_failed": 0, "share": 0.88,
                          "families": 2, "retired_stalled": 1, "top_error": "typeerror", "top_error_n": 5})
        self.assertEqual(check["what"], (
            "7 of the 8 equity versions scored in the last 6 h could not be judged for a fault of their own program (6 "
            "disqualified, 1 refused at load, 0 failed by the decider child): no mechanism was judged in them, and 1 "
            "families were retired STALLED. The commonest first error: TypeError (5 of 6; then KeyError 1). The reading "
            "rule's commonest sentence for it: a symbol's bars read by key (ctx.bars[sym] is ONE object: its arrays are "
            "read by attribute) (2x)."))
        self.assertEqual(set(out["checks"]["elane_dq"]), {"stalled", "what", "numbers", "doing", "owner_step"},
                         "the receipt keeps a check as it keeps every cause's")
        self.assertEqual(check["owner_step"], (
            "the equity generators misread the program contract (the commonest first error: TypeError): fix the text they "
            "read (league/equity/EQUITY.md \"Reading ctx\", elane_review.READING_CTX) or the static rule that should refuse "
            "it, in a release; python3 -m league.ops.elane_health --state /workspace/state lists the families and lines"))
        self.assertEqual(check["numbers"]["examples"][0], {"family": a, "version": 1, "error": "TypeError", "line": 12})
        # The contract's own sentence for the class is beside the check for the operator's report.
        found = EH.checks(ctx, self.root, NOW, ST._load(ctx, self.root)[0])
        self.assertEqual(found["elane_dq"]["hint"], elane_train.DQ_HINTS["TypeError"])
        self.assertIn(f"  {elane_train.DQ_HINTS['TypeError']}.", EH.text(EH.report(self.root, now=NOW)))
        # Raised like any cause: standing in stall.json, a House warning, the notice.
        self.assertEqual(out["stalled"], ["elane_dq"])
        state = json.loads((self.root / ST.STATE_FILE).read_text())
        self.assertTrue(state["causes"]["elane_dq"]["standing"])
        self.assertEqual(state["mail"]["owner_causes"], ["elane_dq"])
        self.assertEqual(len(ctx.alerts), 1)
        self.assertTrue(ctx.alerts[0]["text"].startswith("stall: elane_dq: 7 of the 8 equity versions"))
        self.assertIn(" Owner step: the equity generators misread the program contract", ctx.alerts[0]["text"])
        self.assertIn('fix the text they read (league/equity/EQUITY.md "Reading ctx"', ctx.alerts[0]["text"],
                      "one House warning holds the sentence, what the floor does and the step's lever")
        self.assertEqual(out["notice"]["sent"], True)
        # Nothing a program chose is anywhere: not its exception's text, not its source.
        for text in (json.dumps(out), self.told(), json.dumps(ctx.alerts)):
            self.assertNotIn(SECRET, text)
            self.assertNotIn("zebra", text)

    def test_too_few_scored_versions_are_not_judged_and_half_is_not_most(self):
        a = self.bred("alpha-one")
        self.record(a, versions={str(n): verdict(1.0, "DQ") for n in range(1, 6)})
        check = self.equity()["elane_dq"]
        self.assertEqual((check["stalled"], check["judged"]), (False, False))
        self.assertEqual(check["what"], "Not judged: 5 equity versions were scored in the last 6 h (at least 6 are needed).")
        b = self.bred("beta-two")
        self.record(b, versions={str(n): verdict(1.0, "Y1") for n in range(1, 4)})
        self.record(a, versions={"5": verdict(1.0, "R1")})
        check = self.equity()["elane_dq"]  # 4 of 8
        self.assertEqual((check["stalled"], check["judged"], check["numbers"]["share"], check["owner_step"]),
                         (False, True, 0.5, None))
        self.record(b, versions={"3": verdict(1.0, "RUN")})
        self.assertTrue(self.equity()["elane_dq"]["stalled"], "5 of 8 is most")

    def test_versions_scored_before_the_window_or_before_the_swarm_started_are_not_counted(self):
        a = self.bred("alpha-one", hours=30)
        self.record(a, versions={str(n): verdict(7.0 + n, "DQ") for n in range(1, 9)})
        self.assertEqual(self.equity()["elane_dq"]["numbers"]["scored"], 0)
        self.record(a, versions={str(n): verdict(2.0 + n / 10.0, "DQ") for n in range(1, 9)})
        self.assertTrue(self.equity()["elane_dq"]["stalled"])
        self.beat(2.44)  # the swarm restarted (a release): four of the eight were scored under the one before
        check = self.equity()["elane_dq"]
        self.assertEqual((check["stalled"], check["judged"], check["numbers"]["scored"]), (False, False, 4))
        self.assertIn("in the 2.4 h since the swarm started", check["what"])

    def test_it_clears_when_the_generators_write_programs_that_run(self):
        a, b = self.faulted()
        out, _ = self.run_at()
        self.assertEqual(out["stalled"], ["elane_dq"])
        later = NOW + 5 * HOUR
        # Five hours on: the early disqualifications are out of the window and eight new versions were judged by the bar.
        for fid in (a, b):
            rec = {str(n): elane_train.compact({"passed": False, "fails": ["Y1"]}, at=iso(later - n * 600.0)) for n in range(5, 9)}
            self.record(fid, versions=rec)
        self.ago(-4.5)
        self.store.event("swarm.born", self.family("fresh-two"), {"origin": "architect"})  # the options lanes stay healthy
        self.runs(10, hours=-4.5)
        out, _ = self.run_at(now=later)
        self.assertIn("elane_dq", out["cleared"])
        self.assertFalse(self.own(out)["elane_dq"]["stalled"])
        self.assertFalse(json.loads((self.root / ST.STATE_FILE).read_text())["causes"]["elane_dq"]["standing"])


# ---------------------------------------------------------------------------------------------- elane_births
class TheLastPassesBoreNothing(Case):
    SYMBOLS = "symbols: 1 to 20 of SPY, QQQ, IWM, DIA (XLK, XLF, ZZZZ not)"
    CARD = "card: hypothesis: required; falsification: required"

    def test_three_barren_passes_stand_with_the_refusals_in_closed_words(self):
        self.births(2.5, refused=[("wirefunds-sectors", self.SYMBOLS), ("wirefunds-rotation", self.SYMBOLS)])
        self.births(2.0, truncated=True)
        self.births(1.5, skipped="pace")  # held back: asked nobody, so it neither counts nor breaks the row
        self.births(1.0, refused=[("wirefunds-again", self.SYMBOLS), ("wirefunds-card", self.CARD)])
        out, ctx = self.run_at()
        check = self.own(out)["elane_births"]
        self.assertTrue(check["stalled"])
        self.assertIsNone(check["owner_step"], "the lanes get six hours to correct themselves")
        self.assertEqual({k: check["numbers"][k] for k in ("barren_passes", "asked_passes", "born", "proposed", "refused",
                                                           "passes_refused", "passes_truncated", "passes_empty", "skipped_pace",
                                                           "kind", "top_refusal", "top_refusal_n")},
                         {"barren_passes": 3, "asked_passes": 3, "born": 0, "proposed": 4, "refused": 4, "passes_refused": 2,
                          "passes_truncated": 1, "passes_empty": 0, "skipped_pace": 1, "kind": "symbols",
                          "top_refusal": "symbols", "top_refusal_n": 3})
        self.assertIn("The equity lanes' last 3 passes that asked a model bore no family (each wanted up to 3): 2 had every "
                      "proposal refused, 0 proposed none, 1 were cut short, 0 got no answer, 0 raised.", check["what"])
        self.assertIn("The commonest refusals: a symbol outside elane.universe (or none, or more than a family may trade) "
                      "(3); a card the card checks refuse (1).", check["what"])
        self.assertIn("Symbols the code knows and elane.universe does not hold, named most: XLF 3x, XLK 3x.", check["what"])
        self.assertIn("After 6 h with no equity birth this is your step when a setting clears it.", check["doing"])
        self.assertEqual(out["stalled"], ["elane_births"])
        # The House's closed words only: no slug, no symbol a model made up, no text of a refusal.
        for text in (json.dumps(out), self.told(), json.dumps(ctx.alerts)):
            for word in ("wirefunds", "ZZZZ", "1 to 20 of", "hypothesis: required"):
                self.assertNotIn(word, text)

    def test_six_hours_with_no_birth_is_the_owners_step_when_a_setting_clears_it(self):
        for hours in (8.0, 6.5, 4.0, 1.0):
            self.births(hours, refused=[("far", self.SYMBOLS)])
        check = self.equity()["elane_births"]
        self.assertIn("no equity family was born for 8.0 h while 4 passes asked for one: the architect proposes symbols "
                      "elane.universe does not hold (XLF 4x, XLK 4x)", check["owner_step"])
        self.assertIn("widening the universe is your decision (elane.universe in swarm.json", check["owner_step"])
        self.assertNotIn("this is your step when", check["doing"])
        # A way no setting clears (the card checks, a model's empty answer, a route that did not answer) stays INFO.
        for refused in ([("far", self.CARD)], []):
            self.setUp()
            for hours in (8.0, 6.5, 4.0, 1.0):
                self.births(hours, refused=refused)
            check = self.equity()["elane_births"]
            self.assertEqual((check["stalled"], check["owner_step"]), (True, None), refused)

    def test_answers_cut_short_name_the_output_setting(self):
        for hours in (8.0, 6.5, 4.0):
            self.births(hours, truncated=True)
        check = self.equity()["elane_births"]
        self.assertEqual((check["numbers"]["kind"], check["numbers"]["passes_truncated"]), ("truncated", 3))
        self.assertIn("raise elane.e2.births_max_output_tokens or lower elane.e2.max_per_pass", check["owner_step"])

    def test_a_pass_that_bears_a_family_ends_the_row_and_too_few_passes_are_not_judged(self):
        self.births(3.0, refused=[("far", self.SYMBOLS)])
        self.births(2.0, refused=[("far", self.SYMBOLS)])
        check = self.equity()["elane_births"]
        self.assertEqual((check["stalled"], check["judged"]), (False, False))
        self.assertIn("2 equity passes asked a model in the last 12 h (at least 3 are needed)", check["what"])
        self.births(1.5, born=["an-invented-family"], refused=[("far", self.SYMBOLS)])
        self.births(1.0, refused=[("far", self.SYMBOLS)])
        check = self.equity()["elane_births"]
        self.assertEqual((check["stalled"], check["judged"], check["numbers"]["barren_passes"]), (False, True, 1))
        self.births(0.6, error=True)
        self.births(0.3, refused=[("far", self.SYMBOLS)])
        check = self.equity()["elane_births"]
        self.assertEqual((check["stalled"], check["numbers"]["passes_failed"], check["numbers"]["barren_passes"]), (True, 1, 3))

    def test_a_pass_that_raises_is_a_barren_pass(self):
        for hours in (8.0, 6.5, 4.0):
            self.ago(hours)
            self.store.event("swarm.status", None, {"round": "elane", "error": "Traceback: an invented failure"})
        self.births(9.0, refused=[("far", self.SYMBOLS)])  # one event on record: the lanes are not empty
        check = self.equity()["elane_births"]
        self.assertEqual((check["stalled"], check["numbers"]["passes_raised"], check["numbers"]["kind"]), (True, 3, "raised"))
        self.assertIn("the equity pass raises", check["owner_step"])


# ---------------------------------------------------------------------------------------------- elane_idle
class OwedWorkAndNothingScored(Case):
    def researching(self, last_scored: float = 5.0) -> str:
        """A family in Train research whose last version was scored `last_scored` hours ago."""
        a = self.bred("alpha-one")
        self.record(a, versions={"1": verdict(last_scored, "Y1")})
        self.bred("beta-two", lane="beta")
        return a

    def test_a_lane_at_its_pace_is_starved_and_names_its_lever(self):
        self.researching()
        self.spend(0.5, 0.05)  # over the pace of the tests' settings (a quarter of the floor's line)
        out, _ = self.run_at()
        check = self.own(out)["elane_idle"]
        self.assertTrue(check["stalled"])
        self.assertIsNone(check["owner_step"], "a starved lane runs as its settings say")
        self.assertEqual((check["numbers"]["kind"], check["numbers"]["held_now"], check["numbers"]["idle_hours"],
                          check["numbers"]["researching"]), ("pace", "pace", 5.0, 2))
        self.assertIn("No equity version was scored on Train for 5.0 h while 2 families are in Train research. STARVED, "
                      "not broken: E2 is at its own hourly pace (it booked $0.05 on models in the last hour against a "
                      "pace of $0.02: elane.e2.pace_share 0.25 of the Sail model line), so no model is asked.", check["what"])
        self.assertIn("The lever is yours: BOTH elane.e2.pace_share and elane.e2.usd_day bind (python3 set_swarm.py "
                      "elane.e2.pace_share=<lines> elane.e2.usd_day=<dollars> --apply).", check["what"])
        self.assertEqual(check["doing"], EH.DOING["starved"])
        self.assertEqual(out["stalled"], ["elane_idle"])
        self.assertEqual(self.notify.calls[-1]["notice_id"], "stall:info:swarm_alerts")

    def test_a_spent_day_and_the_houses_sail_day_are_starved_too(self):
        self.researching()
        self.spend(4.0, 0.45)  # today, over the day's line; outside the last hour
        check = self.equity()["elane_idle"]
        self.assertEqual((check["stalled"], check["numbers"]["kind"], check["owner_step"]), (True, "usd_day", None))
        self.assertIn("STARVED, not broken: E2's model dollars for the UTC day are spent ($0.45 of a day's line of $0.40",
                      check["what"])
        self.setUp()
        self.researching()
        self.store.put(elane_yield.GUARD_KEY, {"braked": True, "reason": "an invented brake"})
        check = self.equity()["elane_idle"]
        self.assertEqual((check["stalled"], check["numbers"]["kind"], check["owner_step"]), (True, "sail_day", None))
        self.assertIn("STARVED, not broken: the House's Sail day holds E2 (the Sail guard is braked), so no model is asked.",
                      check["what"])
        self.assertNotIn("an invented brake", check["what"])

    def test_a_lane_that_may_ask_and_scores_nothing_is_broken_and_the_owners_step(self):
        a = self.researching()
        house = {"family": a, "version": 2, "house": "store", "why": "MissingData: invented", "retry_in": 600.0}
        self.round(2.0, house, house)
        self.round(1.0, house, {"family": a, "error": "no route answered", "errors": ["invented"], "retry_in": 1200.0})
        self.record(a, infra={"version": 2, "kind": "store", "next_at": NOW + 3600.0})
        self.ago(0.2)
        self.store.put(EH.TRAIN_AT_KEY, self.t)
        check = self.equity()["elane_idle"]
        self.assertTrue(check["stalled"])
        self.assertEqual({k: check["numbers"][k] for k in ("kind", "held_now", "train_rounds", "house_failures", "unanswered",
                                                           "families_waiting", "train_round_age_min")},
                         {"kind": "house", "held_now": "none", "train_rounds": 2, "house_failures": 3, "unanswered": 1,
                          "families_waiting": 1, "train_round_age_min": 12.0})
        self.assertIn("BROKEN, not starved: E2 may ask a model now and 2 Train rounds ran; 3 steps failed on the House's "
                      "side (store 4); 1 questions got no answer from a model route; 1 of 2 families wait out a backoff; "
                      "the Train round last started 12 min ago.", check["what"])
        self.assertIn("check the equity_data job's receipt and the swarm's equity-decider.log", check["owner_step"])
        self.assertEqual(check["doing"], EH.DOING["broken"])
        self.assertNotIn("MissingData", json.dumps(check))

    def test_the_other_ways_it_is_broken(self):
        self.researching()
        check = self.equity()["elane_idle"]
        self.assertEqual((check["numbers"]["kind"], check["stalled"]), ("no_round", True))
        self.assertIn("the equity lanes owe work, may ask a model and start no round", check["owner_step"])
        self.ago(1.0)
        self.store.event("swarm.status", None, {"round": "elane_train", "error": "Traceback: an invented failure"})
        check = self.equity()["elane_idle"]
        self.assertEqual((check["numbers"]["kind"], check["numbers"]["rounds_raised"]), ("raised", 1))
        self.assertIn("the equity lanes' rounds raise", check["owner_step"])
        # Routes that do not answer heal by themselves: told, nobody's step.
        self.setUp()
        a = self.researching()
        self.round(1.0, {"family": a, "error": "no route answered", "errors": ["invented"], "retry_in": 1200.0})
        check = self.equity()["elane_idle"]
        self.assertEqual((check["numbers"]["kind"], check["stalled"], check["owner_step"]), ("unanswered", True, None))

    def test_a_swarm_that_is_not_running_is_not_judged_idle(self):
        self.researching()
        self.beat(48, at=NOW - 0.5 * HOUR)  # its last heartbeat is half an hour old
        check = self.equity()["elane_idle"]
        self.assertEqual((check["stalled"], check["judged"]), (False, False))
        self.assertIn("Not judged: the swarm is not running (its heartbeat is 30 min old)", check["what"])
        (self.root / EH.HEARTBEAT).unlink()  # no heartbeat to read: judged on the records alone
        self.assertTrue(self.equity()["elane_idle"]["stalled"])

    def test_a_lane_that_scored_lately_or_owes_nothing_is_not_idle(self):
        a = self.researching(last_scored=1.0)
        check = self.equity()["elane_idle"]
        self.assertEqual((check["stalled"], check["judged"]), (False, True))
        self.assertEqual(check["what"], "The last equity version was scored 1.0 h ago. The lanes are idle after 3 h with "
                                        "nothing scored.")
        # Nothing owed: every family past its research, the last pass bore what it wanted.
        self.setUp()
        a = self.bred("alpha-one", record={"status": "passed", "versions": {"1": verdict(9.0)}, "passed_version": 1})
        self.births(8.0, born=[a], want=1)
        self.ago(1.0)
        self.store.put(EH.BIRTHS_AT_KEY, self.t)
        check = self.equity()["elane_idle"]
        self.assertEqual((check["stalled"], check["judged"]), (False, False))
        self.assertIn("no equity family is in Train research and no equity birth is wanted", check["what"])

    def test_no_family_yet_and_barren_passes_are_the_equity_passs_to_explain(self):
        symbols = "symbols: 1 to 20 of SPY, QQQ, IWM, DIA (XLK not)"
        for hours in (5.0, 4.0, 3.5):
            self.births(hours, refused=[("far", symbols)])
        self.ago(3.5)
        self.store.put(EH.BIRTHS_AT_KEY, self.t)
        checks = self.equity()
        idle = checks["elane_idle"]
        self.assertEqual((idle["stalled"], idle["numbers"]["kind"], idle["owner_step"], idle["numbers"]["barren_passes"]),
                         (True, "barren", None, 3))
        self.assertIn("for 5.0 h while no family is in Train research and births are wanted. Not starved (E2 may ask a model "
                      "now): 3 equity passes asked a model and bore no family, so there is none to score (see elane_births).",
                      idle["what"])
        self.assertEqual(idle["doing"], EH.DOING["elane_births"])
        self.assertTrue(checks["elane_births"]["stalled"])
        # A pass that is overdue and may ask a model is a lane that starts no round: the owner's step.
        self.setUp()
        self.births(11.0, born=["an-invented-family"], want=1)
        self.ago(11.0)
        self.store.put(EH.BIRTHS_AT_KEY, self.t)
        idle = self.equity()["elane_idle"]
        self.assertEqual((idle["stalled"], idle["numbers"]["kind"], idle["numbers"]["pass_overdue"]), (True, "no_round", True))
        self.assertIn("while no family is in Train research and the equity pass is overdue. BROKEN, not starved", idle["what"])
        self.assertIn("start no round", idle["owner_step"])

    def test_births_wanted_and_held_back_before_any_family_is_starved(self):
        self.births(5.0, skipped="pace")
        self.ago(5.0)
        self.store.put(EH.BIRTHS_AT_KEY, self.t)
        self.spend(0.5, 0.05)
        check = self.equity()["elane_idle"]
        self.assertEqual((check["stalled"], check["numbers"]["kind"], check["numbers"]["researching"],
                          check["numbers"]["births_wanted"]), (True, "pace", 0, True))
        self.assertIn("for 5.0 h while no family is in Train research and births are wanted. STARVED, not broken",
                      check["what"])


# ---------------------------------------------------------------------------------------------- elane_refused
class MostProgramsRefusedByOneRule(Case):
    def test_most_programs_refused_by_one_rule_names_the_rule_and_its_sentence(self):
        a, b = self.bred("alpha-one"), self.bred("beta-two")
        self.round(3.0, refused_step(a, refusal(BY_KEY)), refused_step(b, refusal(BY_KEY)), scored_step(a, 1, "Y1"))
        self.round(2.0, refused_step(a, refusal(BY_KEY)), refused_step(b, refusal(BY_KEY)), refused_step(a, refusal(LOT_ATTR)))
        self.round(1.0, refused_step(b, refusal(AS_ROWS)), refused_step(a, refusal(LEVEL)), scored_step(b, 1, "DQ"),
                   {"family": a, "error": "no route answered", "errors": ["invented"], "retry_in": 600.0})
        out, ctx = self.run_at()
        check = self.own(out)["elane_refused"]
        self.assertTrue(check["stalled"])
        self.assertEqual({k: check["numbers"][k] for k in ("answers", "stored", "refused", "refused_reading", "refused_level",
                                                           "top_rule", "top_rule_n", "share")},
                         {"answers": 9, "stored": 2, "refused": 7, "refused_reading": 6, "refused_level": 1,
                          "top_rule": "reading", "top_rule_n": 6, "share": 0.67})
        self.assertIn("6 of the 9 programs the equity generators wrote in the last 6 h were refused before a run by ONE "
                      "static rule, the reading rule (7 refused in all: the reading rule 6, the level rule 1).", check["what"])
        self.assertIn("Its commonest sentence: a symbol's bars read by key (ctx.bars[sym] is ONE object: its arrays are read "
                      "by attribute) (4x); then a lot read by attribute (a lot is a dict) (1x).", check["what"])
        self.assertEqual(check["owner_step"], (
            "the equity generators are not being taught the reading rule: teach it where they read it "
            "(league/equity/EQUITY.md, the researcher's system prompt, elane_review.READING_CTX), in a release; python3 -m "
            "league.ops.elane_health --state /workspace/state lists the refusals"))
        self.assertEqual(check["numbers"]["examples"][0], {"family": a, "rule": "reading", "line": 9,
                                                           "sentence": EH.SENTENCES["reading"][0][1]})
        self.assertIn("elane_refused", out["stalled"])
        for text in (json.dumps(out), self.told(), json.dumps(ctx.alerts)):
            self.assertNotIn("zebra", text, "a refusal quotes the program's source; nothing here repeats it")

    def test_too_few_programs_are_not_judged_and_two_rules_sharing_them_is_no_one_rule(self):
        a = self.bred("alpha-one")
        self.round(1.0, *[refused_step(a, refusal(BY_KEY)) for _ in range(7)])
        check = self.equity()["elane_refused"]
        self.assertEqual((check["stalled"], check["judged"]), (False, False))
        self.assertIn("wrote 7 programs in the last 6 h (at least 8 are needed)", check["what"])
        self.setUp()
        a = self.bred("alpha-one")
        self.round(1.0, *[refused_step(a, refusal(BY_KEY)) for _ in range(4)], *[refused_step(a, refusal(LEVEL)) for _ in range(4)],
                   refused_step(a, "the answer held no program"), refused_step(a, "the same program as v1, already scored"))
        check = self.equity()["elane_refused"]
        self.assertEqual((check["stalled"], check["judged"], check["numbers"]["top_rule_n"], check["numbers"]["answers"]),
                         (False, True, 4, 10))

    def test_the_architects_programs_at_birth_count(self):
        a = self.bred("alpha-one", hours=2.0)
        why = EH.ARCHITECT_PROGRAM + refusal(MEMORY)
        self.record(a, refused=[{"at": iso(NOW - 2 * HOUR), "why": why}])
        for i in range(2):
            self.ago(2.0)
            self.store.event("swarm.born", f"born-{i}", {"lane": "equity", "program": "v1"})
        self.store.event("swarm.born", "born-none", {"lane": "beta", "program": "none"})
        self.store.event("swarm.born", "an-options-family", {"origin": "architect", "program": "v1"})
        tally = guard.read(self.root / EH.SWARM_DB, lambda db: EH.refusals_tally(EH.facts(db, NOW), NOW - 6 * HOUR, NOW))
        self.assertEqual((tally["answers"], tally["stored"], tally["refused"], tally["by_rule"]), (3, 2, 1, {"memory": 1}))


# ---------------------------------------------------------------------------------------------- the machinery
class RaisedLikeAnyCause(Case):
    def broken(self) -> None:
        """A lane that owes work, may ask a model and starts no round: `elane_idle`, the owner's step."""
        a = self.bred("alpha-one", hours=30)
        self.record(a, versions={"1": verdict(20.0, "Y1")})

    def keep_healthy(self, hours: float) -> None:
        """The options lanes `hours` after NOW: a birth, Gym runs and a Validation inside their windows."""
        self.ago(-hours + 0.5)
        fid = self.family(f"later-{hours:g}")
        self.store.event("swarm.born", fid, {"origin": "architect"})
        self.runs(10, fid=fid, hours=-hours + 0.5)
        self.runs(1, window="validation", fid=fid, hours=-hours + 0.5)

    def test_noticed_once_then_at_the_stall_jobs_pace_and_cleared_when_it_no_longer_holds(self):
        self.broken()
        out, _ = self.run_at()
        self.assertEqual((out["stalled"], out["notice"]["sent"], len(self.notify.calls)), (["elane_idle"], True, 1))
        out, ctx = self.run_at(now=NOW + 0.5 * HOUR)
        self.assertEqual((out["stalled"], out["notice"]["sent"], len(self.notify.calls)), (["elane_idle"], False, 1))
        self.assertEqual(ctx.alerts, [], "one House warning every 12 hours")
        self.keep_healthy(12.5)
        out, ctx = self.run_at(now=NOW + 12.5 * HOUR)
        self.assertEqual((out["stalled"], out["notice"]["sent"], len(self.notify.calls)), (["elane_idle"], True, 2),
                         "the owner's step again after 12 hours")
        self.assertEqual(len(ctx.alerts), 1)
        entry = self.notify.entry("swarm_alerts")
        self.assertEqual((entry["since"], entry["hours"]), ("2026-10-06T14:20:00Z", "32.5"), "how long: from the last score")
        # A version scored: the cause clears at the next run.
        a = self.store.family("alpha-one")["id"]
        self.record(a, versions={"2": elane_train.compact({"passed": False, "fails": ["P1"]}, at=iso(NOW + 12.6 * HOUR))})
        out, _ = self.run_at(now=NOW + 13 * HOUR)
        self.assertEqual((out["stalled"], out["cleared"], len(self.notify.calls)), ([], ["elane_idle"], 2))

    def test_the_mail_names_only_causes_the_gateway_words(self):
        self.assertEqual(sorted(gateway_causes()), sorted(ST.CAUSES), "the gateway words stall.CAUSES and nothing else")
        self.assertEqual((ST.EVERY_CAUSE, ST.EQUITY_CAUSES), ((*ST.CAUSES, *EH.CAUSES), EH.CAUSES))
        self.assertFalse(set(EH.CAUSES) & set(gateway_causes()), "until the gateway words them, they travel in the carrier")
        self.assertIn(EH.CARRIER, gateway_causes())
        self.broken()
        a = self.store.family("alpha-one")["id"]
        b = self.bred("beta-two")
        self.record(b, versions={str(n): verdict(1.0 + n / 10.0, "DQ") for n in range(1, 8)})
        self.round(1.0, *[refused_step(a, refusal(BY_KEY)) for _ in range(9)])
        for hours in (8.0, 6.5, 4.0):
            self.births(hours, refused=[("far", TheLastPassesBoreNothing.SYMBOLS)])
        out, _ = self.run_at()
        self.assertEqual(out["stalled"], ["elane_dq", "elane_births", "elane_refused"],
                         "the idle cause is clear: versions were scored an hour ago")
        facts = self.notify.calls[-1]
        self.assertEqual([c["cause"] for c in facts["causes"]], ["swarm_alerts"])
        self.assertEqual(facts["notice_id"], "stall:owner:swarm_alerts")
        entry = facts["causes"][0]
        # Several causes share the entry's 400 characters, each in its short words; the receipt keeps each in full.
        self.assertTrue(entry["what"].startswith(
            "The equity lanes: elane_dq: 7 of 7 versions scored in 6 h could not be judged (their own faults, mostly "
            "TypeError) | elane_births: the last 3 passes that asked a model bore no family (mostly symbols outside "
            "elane.universe: XLF 3x, XLK 3x) | elane_refused: 9 of 9 programs written in 6 h were refused before a run by the "
            "reading rule: a symbol's bars read by key (ctx.bars[sy"), entry["what"])
        self.assertTrue(entry["what"].endswith("..."), "the longest is cut to what the others leave")
        self.assertLessEqual(len(entry["what"]), EH.WHAT_CHARS)
        self.assertLessEqual(len(entry["doing"]), EH.DOING_CHARS)
        self.assertEqual(entry["owner_step"], (
            "fix the contract text the generators read for TypeError (league/equity/EQUITY.md \"Reading ctx\"), in a "
            "release; decide whether to widen elane.universe (swarm.json); teach the reading rule where the generators read "
            "it (league/equity/EQUITY.md), in a release"))
        self.assertLessEqual(len(entry["owner_step"]), EH.STEP_CHARS)
        self.assertEqual({k: entry["numbers"][k] for k in ("elane_dq_scored", "elane_dq_faulted", "elane_dq_top_error",
                                                           "elane_births_barren_passes", "elane_births_kind",
                                                           "elane_refused_answers", "elane_refused_top_rule")},
                         {"elane_dq_scored": 7, "elane_dq_faulted": 7, "elane_dq_top_error": "typeerror",
                          "elane_births_barren_passes": 3, "elane_births_kind": "symbols",
                          "elane_refused_answers": 9, "elane_refused_top_rule": "reading"})
        self.assertIn("could not be judged for a fault of their own program (7 disqualified",
                      self.own(out)["elane_dq"]["what"])
        self.assertLessEqual(len(entry["numbers"]), EH.FIGURES)
        for name, value in entry["numbers"].items():
            self.assertRegex(name, r"^[a-z][a-z0-9_]{0,39}$")
            self.assertNotEqual(figure(value), "unknown", (name, value))
        self.assertEqual(set(entry), {"cause", "what", "numbers", "since", "hours", "doing", "owner_step"})

    def test_the_carrier_keeps_its_own_words_after_theirs_when_it_stands_too(self):
        self.broken()
        self.ago(1.0)
        self.store.event("swarm.status", None, {"action": "an_invented_alert", "alert": True, "text": "an invented alert's text"})
        out, _ = self.run_at()
        self.assertEqual(out["stalled"], ["swarm_alerts", "elane_idle"])
        causes = self.notify.calls[-1]["causes"]
        self.assertEqual([c["cause"] for c in causes], ["swarm_alerts"], "one entry, never the carrier twice")
        entry = causes[0]
        self.assertTrue(entry["what"].startswith("The equity lanes: elane_idle: no version scored for 20.0 h, broken: no "
                                                 "round starts | Also: 1 of the swarm's alerts stand (1 raised in the last 12 "
                                                 "h)"), entry["what"])
        self.assertIn("an_invented_alert x1", entry["what"])
        self.assertLessEqual(len(entry["what"]), EH.WHAT_CHARS)
        self.assertEqual((entry["numbers"]["elane_idle_kind"], entry["numbers"]["an_invented_alert"]), ("no_round", 1))
        self.assertEqual(entry["owner_step"], "the equity lanes start no round (the swarm log): a fix, in a release")
        self.assertIn("Each alert is in the swarm's record", entry["doing"], "the carrier's own doing after theirs")
        self.assertEqual(entry["since"], "2026-10-06T14:20:00Z", "the earliest of the causes it carries")

    def test_a_second_equity_cause_is_tried_at_once_and_again_while_the_gateway_holds_its_window(self):
        self.broken()
        self.run_at()
        self.assertEqual(len(self.notify.calls), 1)
        b = self.bred("beta-two")
        self.record(b, versions={str(n): verdict(0.1 * n, "DQ") for n in range(1, 8)})
        # The carrier's key is the same one, so the gateway answers `duplicate` inside its own window.
        self.notify.answer = {"sent": False, "duplicate": True}
        out, _ = self.run_at(now=NOW + 0.5 * HOUR)
        self.assertEqual((out["stalled"], out["notice"]["sent"], len(self.notify.calls)), (["elane_dq"], False, 2))
        self.assertIn("inside its own window", out["notice"]["why"])
        state = json.loads((self.root / ST.STATE_FILE).read_text())
        self.assertNotIn("elane_dq", state["mail"]["told"], "not told until the gateway says it sent it")
        self.assertTrue(state["causes"]["elane_dq"]["standing"])
        out, _ = self.run_at(now=NOW + 1.0 * HOUR)
        self.assertEqual(len(self.notify.calls), 3, "tried again at the next run")
        self.notify.answer = {"sent": True}
        out, _ = self.run_at(now=NOW + 1.5 * HOUR)
        self.assertEqual((out["notice"]["sent"], len(self.notify.calls)), (True, 4))
        out, _ = self.run_at(now=NOW + 2.0 * HOUR)
        self.assertEqual(len(self.notify.calls), 4, "told: paced like any owner cause")

    def test_once_the_gateway_words_them_each_is_its_own_entry(self):
        entries = [{"cause": "elane_dq", "what": "invented", "numbers": {"scored": 8}, "since": None, "hours": None,
                    "doing": "invented", "owner_step": "an invented step"},
                   {"cause": "births", "what": "invented", "numbers": {}, "since": None, "hours": None, "doing": "x",
                    "owner_step": None}]
        self.assertEqual(ST.EQUITY_CAUSES, EH.CAUSES, "today the gateway words none of them: all four are folded")
        self.assertEqual([e["cause"] for e in EH.carried(entries, ST.EQUITY_CAUSES)], ["births", "swarm_alerts"])
        self.assertEqual(EH.carried(entries[1:], ST.EQUITY_CAUSES), entries[1:], "no equity cause: the entries as they are")
        # With the four named in stall.CAUSES (the gateway words them), nothing is folded: each goes as it is, less
        # what is no figure (the examples stay on the House).
        entries[0]["numbers"]["examples"] = [{"family": "an-invented-family"}]
        self.assertEqual(EH.carried(entries, ()), [{**entries[0], "numbers": {"scored": 8}}, entries[1]])

    def test_the_equity_causes_write_nothing(self):
        self.damning()
        files = lambda: {p: p.stat().st_mtime_ns for p in self.root.rglob("*") if p.is_file()}  # noqa: E731
        before = files()
        ctx = self.ctx()
        loaded, _ = ST._load(ctx, self.root)
        found = EH.checks(ctx, self.root, NOW, loaded)
        self.assertEqual({c for c, check in found.items() if check["stalled"]}, {"elane_dq", "elane_births", "elane_refused"})
        EH.report(self.root, now=NOW)
        self.assertEqual(files(), before, "the checks, the receipt and the report read")
        # And the job as a whole writes what it writes with the four switched off, no file more.
        off = self.ctx()
        off.settings = {"stall": {"elane": False}}
        ST.run(off)
        without = set(files())
        for path in without - set(before):
            path.unlink()
        out, _ = self.run_at()
        self.assertTrue(out["stalled"])
        self.assertEqual(set(files()), without)
        self.assertIn(self.root / ST.STATE_FILE, without)

    def test_the_daily_page_lists_them_among_the_stalls_standing(self):
        self.broken()
        self.run_at()
        stalls = json.loads((self.root / ST.STATE_FILE).read_text())
        lines = SB.funnel_lines({"day": {}, "release": None, "since": None}, stalls)
        standing = next(line for line in lines if line.startswith("Stalls standing now: "))
        self.assertIn("elane_idle (since 2026-10-07T10:20:00Z)", standing)
        self.assertEqual(SB.public_problems(standing), [])
        self.assertEqual([SB.public_problems(cause) for cause in EH.CAUSES], [[]] * 4, "a cause's name passes the public filter")


class TheDoneMeterCountsThem(Case):
    """DONE-RULE item 7 ("no captain": no owner step waiting in any stall receipt of the day) reads the equity causes'
    owner steps as it reads every other cause's."""

    def day(self, receipt: dict) -> dict:
        ops = OpsStore(self.root)
        self.addCleanup(ops.close)
        self.t = TS.at("2026-10-07T12:00:00Z")
        self.store.event("swarm.born", "busy", {"lane": "alpha"})
        for window in ("train", "validation"):
            self.store.add_run("busy", 1, {"run_id": f"day-{window}", "status": "ok", "trials": 1}, window=window, stress=1.0,
                               purpose=window, prune=False)
        ops.record("budget", "2026-10-07T00:30:00Z", "ok", "2026-10-07T00:31:00Z",
                   summary={"meters": {"sail": {"limited_by": "ceiling"}, "claude": {"limited_by": "ceiling"}}})
        ops.record("stall", "2026-10-07T10:20:00Z", "ok", "2026-10-07T10:20:30Z", summary=json.loads(json.dumps(receipt)))
        return R.Research247(self.store, self.root).day("2026-10-07")

    def test_an_equity_owner_step_waiting_fails_the_day(self):
        b = self.bred("beta-two")
        self.record(b, versions={str(n): verdict(0.1 * n, "DQ") for n in range(1, 8)})
        out, _ = self.run_at()
        self.assertTrue(out["checks"]["elane_dq"]["owner_step"])
        day = self.day(out)
        self.assertEqual((day["holds"], day["owner"], day["why"]), (False, ["elane_dq"], "an owner step waiting (elane_dq)"))

    def test_an_equity_cause_that_needs_nobody_fails_nothing(self):
        a = self.bred("alpha-one")
        self.record(a, versions={"1": verdict(5.0, "Y1")})
        self.spend(0.5, 0.05)
        out, _ = self.run_at()
        self.assertEqual((out["stalled"], self.own(out)["elane_idle"]["owner_step"]), (["elane_idle"], None))
        day = self.day(out)
        self.assertEqual((day["holds"], day["owner"]), (True, []))
        self.assertEqual(R.NEWS_CAUSES, ST.NEWS_CAUSES, "none of the four is news: an owner step of theirs is one waiting")
        self.assertFalse(set(EH.CAUSES) & set(R.NEWS_CAUSES))


# ---------------------------------------------------------------------------------------------- the funnel
class TheResearchFunnel(Case):
    def invented_day(self) -> None:
        a, b, c = self.bred("alpha-one", hours=20), self.bred("beta-two", hours=20, lane="beta"), self.bred("gamma-three", hours=20)
        symbols = TheLastPassesBoreNothing.SYMBOLS
        self.births(18.0, born=[a, b], refused=[("far", symbols)], want=3)
        self.births(16.0, skipped="pace")
        self.births(14.0, truncated=True)
        self.births(12.0, error=True)
        self.births(10.0, born=[c], refused=[("far", symbols), ("card", "card: hypothesis: required")], truncated=True)
        self.births(8.0, skipped="usd_day")
        self.ago(7.0)
        self.store.event("swarm.status", None, {"round": "elane", "error": "Traceback: an invented failure"})
        for fid, lane, program in ((a, "equity", "v1"), (b, "beta", "none"), (c, "equity", "v1")):
            self.ago(17.0)
            self.store.event("swarm.born", fid, {"lane": lane, "program": program, "origin": "architect"})
        self.record(b, refused=[{"at": iso(NOW - 17 * HOUR), "why": EH.ARCHITECT_PROGRAM + refusal(LEVEL)}])
        review_pass = {"family": c, "version": 2, "passed": True, "review": "pass"}
        self.round(15.0, scored_step(a, 1, "DQ"), refused_step(b, refusal(BY_KEY)), scored_step(c, 1, "Y1", "P1"))
        self.round(13.0, scored_step(a, 2, "Y2"), refused_step(b, refusal(BY_KEY)),
                   {"family": c, "version": 2, "route": ROUTE, "score": {"family": c, "version": 2, "passed": True, "fails": [],
                                                                          "review": {"family": c, "version": 2, "skipped": "x"}}})
        self.round(11.0, scored_step(a, 3, "STATE"), refused_step(b, "the answer held no program"), review_pass,
                   {"family": a, "error": "no route answered", "errors": ["invented"], "retry_in": 600.0})
        self.round(9.0, {"family": a, "version": 4, "route": ROUTE,
                         "score": {"family": a, "version": 4, "passed": False, "fails": ["START"],
                                   "retired": {"family": a, "stalled": ["DQ", "START", "STATE", "Y2"]}}},
                   {"family": b, "version": 1, "house": "store", "why": "invented", "retry_in": 600.0},
                   {"family": b, "version": 1, "passed": False, "fails": ["REVIEW"], "stage": "audit"},
                   {"family": c, "version": 2, "rescored": "kept"})
        for at, fid, what in ((9.0, a, "stalled"), (6.0, b, "refuted")):
            self.ago(at)
            self.store.event("swarm.elane", fid, {"pass": what, "codes": ["Y1"], "versions": 4})
        self.spend(18.0, 0.11, "births")
        self.spend(15.0, 0.031, "train")
        self.spend(13.0, 0.042, "train")
        self.spend(11.0, 0.02, "review")
        self.spend(11.0, 0.02, "audit")
        self.ago(11.0)
        self.store.add_spend("sail_model", 9.0, detail={"key": "swarm:researcher:an-options-family:1"})  # not E2's

    EXPECTED = {
        "birth_passes": {"passes": 6, "asked": 4, "barren": 2, "truncated": 2, "failed": 1, "raised": 1, "proposed": 6, "born": 3,
                         "skipped": {"pace": 1, "usd_day": 1}},
        "families_born": 3,
        "proposals_refused": {"total": 3, "by_class": {"card": 1, "symbols": 2}},
        "answers": {"written": 12, "stored": 8, "refused": 4, "by_rule": {"level": 1, "no_program": 1, "reading": 2},
                    "unanswered": 1},
        "train_rounds": 4,
        "versions": {"scored": 6, "disqualified": 1,
                     "by_code": {"Y1": 1, "Y2": 1, "P1": 1, "R1": 0, "STATE": 1, "DQ": 1, "START": 1}, "passed_bar": 1,
                     "review_refused": 1, "passed": 1, "house_failures": 1, "rescored": 1},
        "retired": {"stalled": 1, "refuted": 1},
        "model_usd": {"births": 0.11, "train": 0.07, "review": 0.04, "other": 0.0, "total": 0.22},
    }

    def test_an_invented_day(self):
        self.invented_day()
        got = guard.read(self.root / EH.SWARM_DB, lambda db: EH.research_counts(db, NOW - 24 * HOUR, NOW))
        self.assertEqual(got, self.EXPECTED)
        # Counts, and E2's own dollars: nothing else.
        def leaves(value, path=()):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield from leaves(item, (*path, key))
            else:
                yield path, value
        for path, value in leaves(got):
            self.assertIs(type(value), float if path[0] == "model_usd" else int, path)
        # The window is half open: the half of the day before 12 h ago.
        early = guard.read(self.root / EH.SWARM_DB, lambda db: EH.research_counts(db, NOW - 24 * HOUR, NOW - 12 * HOUR))
        self.assertEqual((early["birth_passes"]["passes"], early["train_rounds"], early["versions"]["scored"],
                          early["model_usd"]["total"]), (3, 2, 4, 0.18))

    def test_the_funnel_and_the_stall_receipt_carry_it(self):
        self.invented_day()
        window = FN.window(self.root, NOW - 24 * HOUR, NOW)
        self.assertEqual(window["errors"], {})
        self.assertEqual(window["equity"]["research"], self.EXPECTED)
        self.assertEqual((window["equity"]["beta"]["births"], window["equity"]["equity"]["births"]), (1, 2), "beside E1's")
        # The daily funnel's job (the scoreboard) carries the equity block in its receipt; its page prints no equity row.
        (self.base / "deploys.jsonl").write_text(json.dumps({"at": iso(NOW - 30 * HOUR), "stage": "verdict", "verdict": "promoted",
                                                             "release": "an-invented-release"}) + "\n")
        funnel = FN.read(self.root, self.base, "an-invented-release", NOW)
        carried = SB.equity_funnel(funnel)
        self.assertEqual((carried["day"]["research"], carried["day"]["beta"]["births"]), (self.EXPECTED, 1))
        self.assertEqual(carried["since_release"]["research"]["birth_passes"]["passes"], 6, "the release began 30 h ago")
        self.assertEqual(SB.equity_funnel({}), {"day": None, "since_release": None})
        page = "\n".join(SB.funnel_lines(funnel))
        self.assertNotIn("research", page)
        self.assertEqual(SB.public_problems(page), [])

        class Gateway:
            posts: list = []

            def post(self, path, body):
                self.posts.append((path, body))
                return {"commit": "c0ffee"}

        gateway = Gateway()
        ctx = Context("scoreboard", root=self.root, base=self.base, due_at=NOW, config={}, clock=lambda: NOW, gateway=gateway,
                      settings_value={}, release=self.base / "an-invented-release")
        receipt = SB.run(ctx)
        self.assertEqual((receipt["posted"], receipt["equity"]["day"]["research"]), ("docs/runs/desk/2026-10-07.md", self.EXPECTED))
        posted = gateway.posts[0][1]["content"]
        self.assertEqual(SB.public_problems(posted), [])
        for word in ("research funnel", "birth_passes", "proposals_refused", "elane"):
            self.assertNotIn(word, posted, "the page prints no equity row")
        out, _ = self.run_at()
        json.dumps(out)  # the stall receipt is JSON
        off = self.ctx()
        off.settings = {"stall": {"elane": False}}
        self.assertEqual(set(out), set(ST.run(off)), "the four add no key to the stall receipt: they are among its checks")
        self.assertLessEqual({"stalled", "cleared", "warned", "notice", "checks", "ceiling", "errors", "warning"}, set(out))

    def test_a_funnel_that_cannot_be_read_is_an_error_there_and_never_a_zero(self):
        self.invented_day()
        with mock.patch.object(EH, "research_counts", side_effect=RuntimeError("an invented failure")):
            window = FN.window(self.root, NOW - 24 * HOUR, NOW)
        self.assertEqual(window["equity"]["research"], {"error": "RuntimeError: an invented failure"})
        self.assertEqual((window["errors"], window["births"] > 0), ({}, True), "the rest of the funnel stands")

    def test_an_empty_store_counts_nothing(self):
        got = guard.read(self.root / EH.SWARM_DB, lambda db: EH.research_counts(db, NOW - 24 * HOUR, NOW))
        self.assertEqual((got["birth_passes"]["passes"], got["versions"]["scored"], got["answers"]["written"],
                          got["families_born"], got["model_usd"]["total"]), (0, 0, 0, 0, 0.0))


class TheHousesOwnRecords(unittest.TestCase):
    """The readers on what the equity pass and the Train round really write (E1's runner and the model routes faked as
    league/tests/elane_e2_fakes.py fixes them): the events' steps, the families' records, the funnel."""

    def setUp(self):
        fx.switch_on(self)
        self.clock = fx.Clock(NOW - 4 * HOUR)
        self.store = fx.new_store(self, self.clock)
        self.settings = fx.settings(train_budget=3, train_per_round=5, max_per_pass=4, min_per_pass=4)
        self.settings["elane"]["universe"] = ["SPY", "QQQ", "IWM", "DIA"]
        self.answers: list = []
        self.router = fx.FakeRouter(lambda call: fx.review_answer("pass", model=call["sail_profile"]) if fx.is_review(call)
                                    else self.answers.pop(0) if self.answers else fx.answer([]))
        self.results: dict = {}
        self.runner = fx.FakeRunner(lambda code, k: self.results.get(code) or fx.train_result(
            k=k, pnl=180.0 if k == 1.0 else 120.0))
        self.arch = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.researcher = EquityResearcher(self.store, self.router, self.settings, runner=self.runner, clock=self.clock)

    def read(self, fn):
        return guard.read(Path(self.store.root) / EH.SWARM_DB, fn)

    def test_a_pass_and_three_rounds_read_back(self):
        dq = fx.program("QQQ")
        thin = fx.program("IWM", share=0.3)
        self.results[dq] = fx.train_result(status="disqualified") | {"reason": f"25 errors (first: line 9: TypeError: {SECRET})"}
        self.results[thin] = fx.train_result(by_year=fx.year_rows(trades=5))
        self.answers.append(fx.answer([
            fx.proposal("passes", symbols=("SPY",)),
            fx.proposal("faults", symbols=("QQQ",), code=dq, mechanism="Invented idea two: a premium for holding QQQ overnight."),
            fx.proposal("thin", symbols=("IWM",), code=thin, mechanism="Invented idea three: a premium for holding IWM."),
            fx.proposal("misreads", symbols=("DIA",), code=BY_KEY.replace('"SPY"', '"DIA"'),
                        mechanism="Invented idea four: a premium for holding DIA through the close."),
            fx.proposal("outside", symbols=("XLK",), mechanism="Invented idea five: a premium for holding a sector."),
        ]))
        born = self.arch.equity_pass()
        self.assertEqual((len(born["born"]), born["refused"]["count"]), (4, 1))
        self.clock.advance(600)
        # Round 1 scores the three programs the architect carried and asks for the fourth family's first program: the
        # answer misreads ctx again (refused before a run). Round 2: revisions.
        # (The families are worked in the order faults, misreads, passes, thin.)
        self.answers += [fx.answer([]) | {"json": {"program": BY_KEY.replace('"SPY"', '"DIA"'), "note": "x"}},
                         fx.answer([]) | {"json": {"program": fx.program("QQQ", share=0.4), "note": "x"}},
                         fx.answer([]) | {"json": {"program": fx.program("DIA", share=0.2), "note": "x"}},
                         fx.answer([]) | {"json": {"program": LOT_ATTR.replace('"SPY"', '"IWM"'), "note": "x"}}]
        first = self.researcher.run()
        self.clock.advance(600)
        second = self.researcher.run()
        reads = [EH.step_read(step) for out in (first, second) for step in out["steps"]]
        scored = [r for r in reads if r["scored"]]
        self.assertEqual(sorted(tuple(r["fails"]) for r in scored), [(), (), (), ("DQ",), ("Y1",)])
        self.assertEqual(sorted(r["refused"] for r in reads if r["refused"]), ["reading", "reading"])
        self.assertEqual(sum(r["review"] == "pass" for r in reads), 3)
        now = self.clock() + 1
        funnel = self.read(lambda db: EH.research_counts(db, now - 6 * HOUR, now))
        self.assertEqual(funnel["birth_passes"], {"passes": 1, "asked": 1, "barren": 0, "truncated": 0, "failed": 0, "raised": 0,
                                                  "proposed": 5, "born": 4, "skipped": {}})
        self.assertEqual(funnel["proposals_refused"], {"total": 1, "by_class": {"symbols": 1}})
        self.assertEqual(funnel["families_born"], 4)
        # Programs written: the architect's four at birth (three stored, one refused by the reading rule) and the
        # researcher's four (two refused by the reading rule).
        self.assertEqual(funnel["answers"], {"written": 8, "stored": 5, "refused": 3, "by_rule": {"reading": 3}, "unanswered": 0})
        self.assertEqual((funnel["versions"]["scored"], funnel["versions"]["disqualified"], funnel["versions"]["passed_bar"],
                          funnel["versions"]["passed"], funnel["versions"]["by_code"]["Y1"]), (5, 1, 3, 3, 1))
        # The families' records: the disqualification's class and line, the refusals' rule and sentence.
        fams = {f["id"]: f for f in self.read(EH.e2_families)}
        self.assertEqual(set(fams), {"passes", "faults", "thin", "misreads"})
        dq_verdict = fams["faults"]["versions"]["1"]
        self.assertEqual((dq_verdict["fails"], EH.dq_class(dq_verdict["why"]), EH.dq_line(dq_verdict["why"])), (["DQ"], "TypeError", 9))
        self.assertNotIn(SECRET, json.dumps(fams))
        self.assertEqual([EH.rule_of(r["why"]) for r in fams["misreads"]["refused"]], ["reading", "reading"])
        self.assertTrue(fams["misreads"]["refused"][0]["why"].startswith(EH.ARCHITECT_PROGRAM))
        self.assertEqual(fams["passes"]["status"], "passed")
        # And the checks over them, pure: five scored (one faulted), eight programs written (three refused by one rule).
        f = self.read(lambda db: EH.facts(db, now, self.settings))
        found = EH.judge(f, now=now, started=None, settings=EH.lanes(self.settings, f)[2])
        self.assertEqual((EH.lanes(self.settings, f)[:2], found["elane_dq"]["judged"]), ((True, None), False))
        self.assertEqual({k: found["elane_refused"]["numbers"][k] for k in ("answers", "refused", "top_rule", "top_rule_n")},
                         {"answers": 8, "refused": 3, "top_rule": "reading", "top_rule_n": 3})
        self.assertFalse(found["elane_refused"]["stalled"], "three of eight is not most")
        self.assertEqual(found["elane_idle"]["what"][:44], "The last equity version was scored 0.0 h ago")

    def test_a_barren_pass_and_what_the_next_request_is_shown(self):
        """The architect's next request shows the previous pass's refusals with their reasons, as the options architect's
        does (`elane_births.last_text`)."""
        self.answers.append(fx.answer([fx.proposal("sector-rotation", symbols=("XLK", "XLF"), lane="equity", agenda="rotation"),
                                       fx.proposal("no-such-lane", lane="alpha")]))
        out = self.arch.equity_pass()
        self.assertEqual((out["born"], out["refused"]["count"]), ([], 2))
        self.assertEqual((EH.pass_read(out)["barren"], EH.pass_read(out)["how"]), (True, "refused"))
        last = self.store.get(LAST_KEY)
        self.assertEqual([r["slug"] for r in last["refused"]], ["sector-rotation", "no-such-lane"])
        _, request = EquityPass(self.arch).request(EquityQuota(self.store, self.settings, now=self.clock()))
        self.assertIn("YOUR LAST EQUITY PASS'S PROPOSALS NOT BORN", request)
        self.assertIn("- sector-rotation: symbols: 1 to 20 of SPY, QQQ, IWM, DIA (XLK, XLF not)", request)
        self.assertIn("- no-such-lane: lane: 'alpha' is not \"beta\" or \"equity\"", request)
        self.assertIn("YOUR LAST EQUITY PASS LEFT 4 OF ITS BIRTHS UNFILLED", request)


# ---------------------------------------------------------------------------------------------- the report
class TheOperatorsReport(Case):
    def test_the_report_lists_the_checks_the_funnel_and_each_familys_lines(self):
        a = self.bred("alpha-one")
        self.record(a, versions={"1": verdict(2.0, "DQ"), "2": verdict(1.0, "Y1")},
                    refused=[{"at": iso(NOW - 1.5 * HOUR), "why": refusal(BY_KEY)}], unanswered={"next_at": NOW + 600.0})
        before = {p: p.stat().st_mtime_ns for p in self.root.rglob("*") if p.is_file()}
        doc = EH.report(self.root, now=NOW, hours=24)
        self.assertEqual((doc["judged"], doc["why"], set(doc["checks"]), doc["funnel"]["hours"]), (True, None, set(EH.CAUSES), 24))
        fam = doc["families"][0]
        self.assertEqual(fam["versions"]["1"], {"at": "2026-10-07T08:20:00Z", "passed": False, "fails": ["DQ"],
                                                "error": "TypeError", "line": 12})
        self.assertEqual(fam["refused"][0]["sentences"], [{"line": 9, "sentence": EH.SENTENCES["reading"][0][1]}])
        self.assertEqual(fam["waits"], {"unanswered": "2026-10-07T10:30:00Z"})
        text = EH.text(doc)
        for line in ("elane_dq: not judged", f"  {a} (equity, researching; born 2026-10-07T00:20:00Z)",
                     "    v1 2026-10-07T08:20:00Z: failed DQ: TypeError at line 12",
                     "    refused 2026-10-07T08:50:00Z by the reading rule: line 9: a symbol's bars read by key",
                     "    waits (unanswered) until 2026-10-07T10:30:00Z", "The research funnel, last 24 h:"):
            self.assertIn(line, text)
        for said in (json.dumps(doc), text):
            self.assertNotIn(SECRET, said)
            self.assertNotIn("zebra", said)
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.root.rglob("*") if p.is_file()}, before, "read-only")

    def test_the_command_prints_it(self):
        self.bred("alpha-one")
        for args, mark in ((["--state", str(self.root)], "The equity lanes' health at "),
                           (["--state", str(self.root), "--json", "--hours", "6"], '"families": [')):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(EH.main(args), 0)
            self.assertIn(mark, out.getvalue())

    def test_the_stall_job_says_what_it_covers(self):
        from league.ops.registry import by_name

        self.assertIn("the equity lanes' own causes (league/ops/elane_health.py", by_name()["stall"].what)
        self.assertTrue(by_name()["stall"].in_pause, "read-only, in a pause too")


# ---------------------------------------------------------------------------------------------- the architect's universe
class TheArchitectIsNotLedOutsideTheUniverse(unittest.TestCase):
    """Release E2.4, item 3 (league/swarm/elane_births.py `lanes_text`): the lanes block speaks of the universe's own
    symbols only and says a proposal naming any other is refused whole."""

    @staticmethod
    def block(universe: list[str]) -> str:
        return elane_births.lanes_text({"elane": {"mode": "gate", "birth_share": 0.25, "universe": universe}})

    def test_a_universe_of_the_four_index_etfs_names_no_other_symbol(self):
        from league.equity import config as eqconfig

        block = self.block(["SPY", "QQQ", "IWM", "DIA"])
        for symbol in eqconfig.UNIVERSE:
            named = re.search(rf"(?<![A-Za-z0-9.]){re.escape(symbol)}(?![A-Za-z0-9.])", block) is not None
            self.assertEqual(named, symbol in eqconfig.INDEX_ETFS, symbol)
        self.assertIn("fills pay the half-spread (1 bp the index ETFs SPY, QQQ, IWM and DIA) and sells the SEC and FINRA fees.",
                      block)
        for word in ("3 bp", "5 bp", "sector", "the other ETFs", "defensive", "stocks"):
            self.assertNotIn(word, block)
        self.assertIn("etf: index SPY, QQQ, IWM, DIA. A proposal naming any other symbol is refused whole: the contract in "
                      "your system prompt speaks of every symbol the code knows, and only the symbols of this line are open.",
                      block)

    def test_a_wider_universe_names_its_groups_with_their_costs(self):
        from league.equity import config as eqconfig

        block = self.block(["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "TLT", "GLD"])
        self.assertIn("fills pay the half-spread (1 bp the index ETFs SPY, QQQ, IWM and DIA; 3 bp the sector ETFs XLK, XLF and "
                      "XLE; 5 bp the defensive ETFs TLT and GLD) and sells", block)
        self.assertIn("etf: index SPY, QQQ, IWM, DIA; sectors XLK, XLF, XLE; defensive TLT, GLD. A proposal naming any other "
                      "symbol is refused whole", block)
        for symbol in ("XLB", "XLV", "AAPL", "MSFT"):
            self.assertNotIn(symbol, block)
        one = self.block(["SPY", "GLD"])
        self.assertIn("(1 bp the index ETFs SPY; 5 bp the defensive ETFs GLD)", one)
        # Each cost is the code's own (league/equity/config.py HALF_SPREAD_BP), whatever the universe holds.
        for symbol, bp in eqconfig.HALF_SPREAD_BP.items():
            if eqconfig.UNIVERSE[symbol] == eqconfig.ETF:
                self.assertIn(f"({bp} bp ", self.block([symbol]), symbol)
        self.assertEqual(elane_births.lanes_text({"elane": {"mode": "off", "birth_share": 0.25}}), "", "off: no block")


if __name__ == "__main__":
    unittest.main()
