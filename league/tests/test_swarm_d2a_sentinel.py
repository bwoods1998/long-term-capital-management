"""D2a at run time: Validation reaches a model only as pass or fail and a count of checks passed.

A family is given Validation runs (normal spread and the 1.5x twin, full results kept), a validation line, view and
numbers, and a leaderboard row, every figure a SENTINEL no other code produces. Then every text a model reads is built
the way the swarm builds it: the researcher's cycle (its request bodies), status, brief and prompt, its `read_run` tool
asked for the Validation run, the architect's prompt, the strategist's packet and the diagnostician's packet. None may
carry a sentinel. The harness lanes run this module with a candidate's gate forced OPEN as well as closed
(`harness_lanes.CORE_REGRESSIONS`), so a gated change that shows Validation figures to a model fails here whatever
route it took (a store reader, a state key, a tool), which the static guards can never promise. Every figure here is
invented."""
from __future__ import annotations

import json

from league.swarm.architect import Architect
from league.swarm.diagnostician import Diagnostician, standing
from league.swarm.strategist import Strategist
from league.tests.swarm_fakes import result
from league.tests.test_swarm_researcher import ResearcherCase

#: Validation's figures, chosen so nothing else in a prompt could print them.
T, MEAN, DSR, SHARPE, PNL, TRADES = 7.318093, 0.0461773, 0.0918273, 2.718061, 6174.29, 917
SENTINELS = ("7.318093", "0.0461773", "0.0918273", "2.718061", "6174.29", "917 trades", '"trades": 917', "5.122665")
CHECKS = {"status_ok": True, "trades": True, "days": True, "mean_positive": True, "t": False, "dsr": False,
          "quarters": True, "stress": True}


class ValidationSentinels(ResearcherCase):
    def setUp(self):
        super().setUp()
        self.fid = self.fam["id"]
        self.researcher().cycle(self.fid)  # the starter: version 1 and its Train run, no model call
        figures = {"t_daily": T, "mean_return_on_max_loss_daily": MEAN, "dsr": DSR, "sharpe_daily": SHARPE, "pnl": PNL,
                   "trades": TRADES}
        normal = result("sentinel-validation", window="validation")
        normal["summary"].update(figures)
        normal["stress_1.5"].update(t_daily=T * 0.7, sharpe_daily=SHARPE * 0.7, pnl=PNL * 0.7, trades=TRADES)
        self.val_run = self.store.add_run(self.fid, 1, normal, window="validation", stress=1.0, purpose="validation")
        twin = result("sentinel-validation-twin", window="validation")
        twin["summary"].update({k: v * 0.7 if isinstance(v, float) else v for k, v in figures.items()})
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
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, text, f"{where} shows a Validation figure ({sentinel}): D2a")

    def test_the_seeded_figures_are_there_to_leak(self):
        """The store really holds them: a reader that showed them would fail every test below."""
        rows = self.store.runs(self.fid, window="validation")
        self.assertEqual(len(rows), 2)
        self.assertIn("7.318093", json.dumps([r["summary"] for r in rows], default=str))
        self.assertIn("7.318093", json.dumps(self.store.family(self.fid)["state"], default=str))

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
