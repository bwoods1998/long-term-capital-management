"""D2a at run time: Validation reaches a model only as pass or fail and a count of checks passed.

A family is given Validation runs (normal spread and the 1.5x twin, full results kept), a validation line, view and
numbers, and a leaderboard row, every figure a SENTINEL no other code produces. Then every text a model reads is built
the way the swarm builds it: the researcher's cycle (its request bodies), status, brief and prompt, its `read_run` tool
asked for the Validation run, the architect's prompt, the strategist's packet and the diagnostician's packet. None may
carry a sentinel in a common printed form: each figure (and its 1.5x twin's) is looked for rounded or truncated to 1-6
decimals, as `round()` and `repr` print it, as a percent, with thousands separators, in scientific notation, and the large
ones as a whole number, rounded or truncated (`printed_forms`), each between non-digits. The harness lanes run this module
with a candidate's gate forced OPEN as well as closed (`harness_lanes.CORE_REGRESSIONS`), so a gated change that prints a
Validation figure to a model in one of those forms fails here, by whichever route the figure came (a store reader, a
state key built at run time, a tool), which the static guards can never promise. A figure a model sees only in another
form (arithmetic of its own: a ratio of two sealed figures, a rank, a figure shifted or scaled; an unusual format) is
not caught here: the review checks for that. Every figure here is invented."""
from __future__ import annotations

import json
import math
import re
from decimal import ROUND_DOWN, Decimal
from unittest.mock import patch

from league.swarm.architect import Architect
from league.swarm.diagnostician import Diagnostician, standing
from league.swarm.researcher import Researcher
from league.swarm.strategist import Strategist
from league.tests.swarm_fakes import result
from league.tests.test_swarm_researcher import ResearcherCase

#: Validation's figures: three-digit (or four-digit) whole parts no prompt prints, so every rounding of each, down to one
#: decimal, is distinctive; the 1.5x twin holds each times 0.7.
T, MEAN, DSR, SHARPE, PNL, TRADES = 738.6417, 612.9483, 853.7129, 394.7261, 6174.29, 917
FIGURES = (T, MEAN, DSR, SHARPE, PNL)
TWIN = 0.7
#: Texts that name the trade count (a bare 917 could be anything).
LITERALS = ("917 trades", '"trades": 917', "trades: 917", "trades=917")
CHECKS = {"status_ok": True, "trades": True, "days": True, "mean_positive": True, "t": False, "dsr": False,
          "quarters": True, "stress": True}


def truncated(value: float, places: int) -> str:
    """`value` cut (not rounded) to `places` decimals, as `int()`, `math.trunc` or a string slice print it."""
    return str(Decimal(repr(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_DOWN))


def printed_forms(value: float, *, whole: bool = True) -> set[str]:
    """Every way a figure is commonly printed: 1-6 decimals (fixed, `round` and `repr`) rounded or truncated, a percent
    at 0-4 decimals, thousands separators, scientific notation at 1-4 digits, and (`whole`) the whole number, rounded or
    truncated (`int()`), for a figure of 100 or more."""
    forms = {repr(value), str(value)}
    for d in range(1, 7):
        forms.update({f"{value:.{d}f}", str(round(value, d)), truncated(value, d)})
    for d in range(0, 5):
        forms.add(f"{value * 100:.{d}f}")
    if abs(value) >= 1000:
        forms.update(f"{value:,.{d}f}" for d in range(0, 3))
    forms.update(f"{value:.{d}e}" for d in range(1, 5))
    if whole and abs(value) >= 100:
        forms.update({f"{value:.0f}", str(math.trunc(value))})
    return {f for f in forms if len(f.replace("-", "").replace(".", "")) >= 3}


#: One pattern for every form of every figure and its twin, each between non-digits (`7.39` in `17.391` is no match).
FORMS = sorted({f for v in FIGURES for f in printed_forms(v)} | {f for v in FIGURES for f in printed_forms(v * TWIN,
                                                                                                         whole=False)},
               key=lambda f: (-len(f), f))
PATTERN = re.compile("|".join(rf"(?<![\d]){re.escape(f)}(?![\d])" for f in FORMS))


class ValidationSentinels(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.fid = self.fam["id"]
        self.researcher().cycle(self.fid)  # the starter: version 1 and its Train run, no model call
        figures = {"t_daily": T, "mean_return_on_max_loss_daily": MEAN, "dsr": DSR, "sharpe_daily": SHARPE, "pnl": PNL,
                   "trades": TRADES}
        normal = result("sentinel-validation", window="validation")
        normal["summary"].update(figures)
        normal["stress_1.5"].update(t_daily=T * TWIN, sharpe_daily=SHARPE * TWIN, pnl=PNL * TWIN, trades=TRADES)
        self.val_run = self.store.add_run(self.fid, 1, normal, window="validation", stress=1.0, purpose="validation")
        twin = result("sentinel-validation-twin", window="validation")
        twin["summary"].update({k: v * TWIN if isinstance(v, float) else v for k, v in figures.items()})
        self.store.add_run(self.fid, 1, twin, window="validation", stress=1.5, purpose="validation")
        numbers = {"t": T, "mean": MEAN, "dsr": DSR, "trades": TRADES, "pnl": PNL, "sharpe": SHARPE}
        self.store.set_state(self.fid, validation_line={"passed": False, "checks": CHECKS, "numbers": numbers},
                             validation_version=1, gate="fail", validation_numbers=numbers,
                             validation_view={"t": T, "mean_return_on_max_loss": MEAN, "line_met": False,
                                              "checks_not_met": ["dsr", "t"]})
        self.store.update_family(self.fid, validations=2, best_version=1)
        self.store.put("leaderboard", {"board": [{"family": self.fid, "band": "gym", "structure": "iron_condor",
                                                  "roots": ["SPY"], "validation": numbers, "share": 1.0}]})

    def clean(self, text, where):
        for literal in LITERALS:
            self.assertNotIn(literal, text, f"{where} shows a Validation figure ({literal}): D2a")
        found = PATTERN.search(text)
        self.assertIsNone(found, f"{where} shows a Validation figure ({found.group(0) if found else ''}): D2a")

    def test_the_seeded_figures_are_there_to_leak(self):
        """The store really holds them: a reader that showed them would fail every test below."""
        rows = self.store.runs(self.fid, window="validation")
        self.assertEqual(len(rows), 2)
        self.assertIn("738.6417", json.dumps([r["summary"] for r in rows], default=str))
        self.assertIn("738.6417", json.dumps(self.store.family(self.fid)["state"], default=str))

    def test_every_printed_precision_of_every_figure_is_caught(self):
        """The detector itself: a figure (or its twin's) printed at any precision, as a percent, with separators or in
        scientific notation is caught; a figure that merely shares digits is not."""
        for value in FIGURES + tuple(v * TWIN for v in FIGURES):
            for text in (f"t {value:.2f}", f"t={round(value, 1)}", f"t {value:.3f}.", f"({value:.4f})",
                         f"{value * 100:.1f}%", f"{value:.2e}", json.dumps({"t": round(value, 2)})):
                with self.assertRaises(AssertionError, msg=text):
                    self.clean(text, "a leak")
        # Truncated as well as rounded (the sixth review): `int()`, and a figure cut to 1-6 decimals.
        for value in FIGURES:
            for text in (f"t {int(value)}", f"t={math.trunc(value)}", f"t {str(value)[:str(value).index('.') + 3]}",
                         f"t {truncated(value, 3)}"):
                with self.assertRaises(AssertionError, msg=text):
                    self.clean(text, "a truncated leak")
        self.clean("t 1738.64 and 38.64, 2 of 8 checks passed, 600 seconds, 0.7 stress, 7.3 on Train", "no leak")

    def test_a_rounded_leak_through_a_computed_key_is_caught(self):
        """The reviewer's probe (round 4): a gated status line that reads `validation_numbers` through a key built at run
        time (no static guard sees it) and prints two decimals. It must fail here."""
        original = Researcher.status

        def leaky(researcher, fam):
            seen = (fam.get("state") or {}).get("valid" + "ation_numbers") or {}
            return original(researcher, fam) + f"\nt {seen['t']:.2f}, dsr {seen['dsr']:.2f}"

        with patch.object(Researcher, "status", leaky):
            fam = self.store.family(self.fid)
            with self.assertRaisesRegex(AssertionError, "D2a"):
                self.clean(self.researcher().status(fam), "Researcher.status")

    def test_the_researchers_cycle_status_brief_and_prompt_show_a_verdict_and_a_count_only(self):
        self.steps = [{"text": "ok"}]
        r = self.researcher()
        r.cycle(self.fid)
        bodies = json.dumps(self.sail.bodies, default=str)
        self.assertIn("6 of 8 checks passed", bodies, "D2a's own words reach the researcher")
        self.clean(bodies, "the researcher's request")
        fam = self.store.family(self.fid)
        for where, text in (("status", r.status(fam)), ("brief", r.brief(fam)), ("prompt", r.prompt())):
            self.clean(text, f"Researcher.{where}")

    def test_the_read_run_tool_never_opens_a_validation_run(self):
        fam = self.store.family(self.fid)
        out = self.researcher()._local_tool(fam, "read_run", {"run_id": self.val_run["run_id"], "section": "summary"}, {})
        self.assertIn("error", out)
        self.clean(json.dumps(out, default=str), "read_run on a Validation run")

    def test_the_architect_strategist_and_diagnostician_see_no_validation_figure(self):
        architect = Architect(self.store, self.router, self.settings, clock=self.clock)
        self.clean(architect.prompt(), "Architect.prompt")
        self.clean(architect.prompt(full_graveyard=True), "Architect.prompt (full graveyard)")
        strategist = Strategist(self.store, self.router, self.settings, clock=self.clock, architect=architect)
        self.clean(strategist.packet(sample=True), "Strategist.packet")
        fam = self.store.family(self.fid)
        seen = {**standing(fam), "validations": 2}
        doctor = Diagnostician(self.store, self.router, self.settings, pool=self.pool, researcher=self.researcher(),
                               contract="THE CONTRACT BODY", clock=self.clock)
        packet = doctor.packet(fam, seen)
        self.assertIn("6 of 8 checks passed", packet)
        self.clean(packet, "Diagnostician.packet")
