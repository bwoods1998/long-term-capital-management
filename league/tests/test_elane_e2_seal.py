"""Release E2, THE SEAL (amendment A9 D3; league/swarm/elane_seal.py): no Validation or look outcome of a share program
reaches a generator. Two worlds share one Train history (the same E2 records, births, programs and route ledger) and
differ only in what happened to share programs after Train: in one the Train pass and the seeded program met their
pre-check, passed the sealed look and went live; in the other both failed, retired, and left graveyard rows whose
lessons tell the outcome. The equity request (system and user), the equity researcher's brief, the route choice, the
equity Train map and graveyard, and the options generators' graveyard reads are the same in both, and carry no
sentinel of either outcome. THE RESERVE (A15): two markets that differ only in 2020-2021 give every E2 record, stored
run, map, ledger and generator read byte for byte the same, with no figure of those years in any; a runner that leaks a
2020 row is refused whole; every text a generator reads says "Train years 2016-19 and 2022-24". (The invented runner
answers the years it is asked for: what is tested is that E2 asks for no reserve session and keeps no reserve row. On
E1's runner a 2022 run still looks back on 2021's bars as history, as the amendment's two `train(start, end)` calls
do.) Every family, program and number here is invented."""

from __future__ import annotations

import datetime as dt
import json
import re
import types
import unittest
from types import SimpleNamespace

from league.swarm import elane, elane_births, elane_review, elane_seal, elane_train, elane_yield
from league.swarm.architect import Architect, GraveyardDigest
from league.swarm.elane_births import EquityPass, EquityQuota
from league.swarm.elane_train import STATE_KEY, EquityResearcher
from league.swarm.researcher import Researcher
from league.tests import elane_e2_fakes as fx

SENTINELS = ("SENTINEL", "0.9731", "-0.4417", "probe", "candidate")


class TwoWorlds(unittest.TestCase):
    def setUp(self):
        fx.switch_on(self)
        self.settings = fx.settings()

    def world(self, outcome: str):
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        verdict = {"passed": True, "fails": [], "score": 1.93, "pnl_10": 180.0, "pnl_15": 120.0,
                   "years": {"2016": {"trades": 60, "days_traded": 30, "pnl": 20.0, "t": 0.6, "active": True}}}
        fx.e2_family(store, "won", lane="equity", agenda="reversal", symbols=("QQQ",), code=fx.program("QQQ"),
                     record={"status": "passed", "passed_version": 1, "versions": {"1": verdict}})
        store.update_family("won", best_version=1, best_train=1.93)
        fx.e2_family(store, "dead", lane="equity", agenda="trend", symbols=("XLK",),
                     record={"status": "refuted", "versions": {"1": {"passed": False, "fails": ["Y2"]}},
                             "refuted": {"at": "2026-10-10T01:00:00Z", "codes": ["Y2"], "versions": 1, "why": "spent"}})
        store.bury("dead", "REFUTED on Train (equity-v1): spent.")
        store.retire("dead", "REFUTED on Train")
        fx.e2_family(store, "busy", lane="beta", agenda="overnight", symbols=("SPY",), code=fx.program(),
                     record={"status": "researching",
                             "versions": {"1": {"passed": False, "fails": ["P1"], "pnl_10": 30.0, "pnl_15": -2.0}}})
        seed = store.add_family({"id": "seed-overnight-spy", "mechanism": "The captain's seed: SPY overnight, every "
                                 "session.", "structure": "etf", "roots": ["SPY"], "lane": "beta"}, origin="seed")
        store.put(elane.SEEDS_KEY, {"seed-overnight-spy": seed["id"]})
        opt = store.add_family({"id": "opt-dead", "mechanism": "An invented options idea that died on Train.",
                                "structure": "debit_vertical", "roots": ["SPY"]}, origin="architect")
        store.bury(opt["id"], "REFUTED: an invented options lesson.")
        elane_yield.book(store, "sail:pro_asap", usd=0.4, known=True, purpose="births", answered=True, now=clock())
        elane_yield.book_births(store, "sail:pro_asap", 3)
        # What happens after Train: the only difference between the worlds.
        for fid in ("won", seed["id"]):
            if outcome == "pass":
                store.set_state(fid, elane_try={"version": 1, "entered": True, "precheck": {"passed": True, "t": 0.9731}},
                                elane_look={"version": 1, "verdict": {"passed": True, "t": 0.9731}, "beside": "SENTINEL-A"},
                                validation_r_sd_by_version={"1": 0.9731}, validation_line={"met": True})
                store.update_family(fid, validated_version=1, best_validation=0.9731, band="probe")
                store.add_look(fid, 1, f"sha-{fid}", passed=True, p_value=0.01, detail={"why": "SENTINEL-A"})
                store.add_forward(fid, "real", [{"id": f"eq-{fid}", "day": "2026-10-13", "pnl": 0.9731, "max_loss": 100.0}])
            else:
                store.set_state(fid, elane_try={"version": 1, "entered": False, "precheck": {"passed": False, "t": -0.4417}},
                                elane_look={"version": 1, "verdict": {"passed": False}, "beside": "SENTINEL-B"},
                                validation_line={"met": False})
                store.update_family(fid, validated_version=1, best_validation=-0.4417)
                store.add_look(fid, 1, f"sha-{fid}", passed=False, p_value=0.4417, detail={"why": "SENTINEL-B"})
                store.bury(fid, "best validation: not met (SENTINEL-B); the look failed")
                store.retire(fid, "SENTINEL-B: failed its look")
        return store, clock

    def reads(self, outcome: str) -> dict:
        store, clock = self.world(outcome)
        router = fx.FakeRouter()
        arch = Architect(store, router, self.settings, clock=clock)
        system, user = EquityPass(arch).request(EquityQuota(store, self.settings, now=clock()))
        researcher = EquityResearcher(store, router, self.settings, runner=fx.FakeRunner(), clock=clock)
        routes = elane_yield.routes(self.settings, router)
        tool = Researcher._local_tool(types.SimpleNamespace(store=store, settings=self.settings), {"id": "x"}, "graveyard",
                                      {"query": ""}, {})
        return {
            "system": system, "user": user, "brief": researcher.brief(store.family("busy")),
            "choice": [elane_yield.choose(store, self.settings, routes, turn=t, train_key=STATE_KEY)[0].key
                       for t in range(6)],
            "map": elane_train.train_map(store), "graveyard": elane_train.refuted_rows(store),
            "options": {"graves": [r["family"] for r in arch.graves(limit=50)], "ids": sorted(arch.graveyard_ids()),
                        "digest": [p["id"] for p in GraveyardDigest(store, self.settings, clock=clock).rows()],
                        "tool": [r["family"] for r in tool["lessons"]], "prompt_mentions": [
                            fid for fid in ("won", "dead", "busy", "seed-overnight-spy")
                            if re.search(rf"(?<![\w-]){re.escape(fid)}(?![\w-])", arch.prompt())]},
        }

    def test_every_generator_reads_the_same_in_both_worlds(self):
        a, b = self.reads("pass"), self.reads("fail")
        for key in a:
            self.assertEqual(a[key], b[key], f"{key} differs with the sealed outcomes")

    def test_no_sentinel_of_either_outcome_reaches_a_generator(self):
        for outcome in ("pass", "fail"):
            reads = self.reads(outcome)
            for key in ("system", "user", "brief"):
                for word in SENTINELS:
                    self.assertNotIn(word, reads[key], f"{outcome}: {key} carries {word}")

    def test_the_options_generators_read_no_equity_row(self):
        for outcome in ("pass", "fail"):
            reads = self.reads(outcome)["options"]
            self.assertEqual(reads, {"graves": ["opt-dead"], "ids": ["opt-dead"], "digest": ["opt-dead"],
                                     "tool": ["opt-dead"], "prompt_mentions": []}, outcome)

    def test_the_request_still_says_what_has_its_try_and_what_was_refuted(self):
        user = self.reads("fail")["user"]
        self.assertIn("won (equity / reversal / QQQ; passed Train (v1))", user)
        self.assertIn("seed-overnight-spy (beta / other / SPY; seeded by the captain's build agents)", user)
        self.assertIn("dead (equity / trend / XLK): ", user)
        self.assertIn("busy (beta / overnight / SPY; in Train research, 1 versions scored)", user)

    def test_train_facts_carry_no_sealed_field(self):
        store, _ = self.world("pass")
        for fid in ("won", "busy", "seed-overnight-spy"):
            facts = elane_seal.train_facts(store.family(fid), STATE_KEY)
            self.assertFalse(set(facts) & (elane_seal.SEALED_KEYS | elane_seal.SEALED_COLUMNS))
            self.assertFalse(set(facts["record"]) & elane_seal.SEALED_KEYS)

    def test_the_operators_report_does_see_the_outcomes(self):
        store, clock = self.world("pass")
        row = elane_yield.report(store, self.settings, train_key=STATE_KEY)["routes"]["sail:pro_asap"]
        self.assertEqual((row["train_passes"], row["validation_entries"], row["looks_passed"], row["live"]), (1, 1, 1, 1))


#: The reserve years' invented figures in each market (none may reach anything E2 keeps or shows).
RESERVE = {"a": {"pnl": 8642.97, "trades": 7531, "days_traded": 6421, "t_daily": -3.217},
           "b": {"pnl": -9753.31, "trades": 3, "days_traded": 2, "t_daily": 4.139}}
RESERVE_WORDS = ("8642.97", "7531", "6421", "-3.217", "9753.31", "4.139")


class MarketRunner:
    """E1's isolated runner over an invented market (a by-year row each year 2016-2024): `train(start, end)` answers
    only the requested sessions' years, its summary summed from them; `leak` puts the 2020 row into the 2016-2019 run.
    The code "fails" in a program makes its 1.5x run lose."""

    def __init__(self, reserve: dict, *, leak: bool = False):
        base = {"trades": 60, "days": 252, "days_traded": 30, "pnl": 20.0, "t_daily": 0.6, "exposure_mean": 0.3,
                "bh_pnl": 6.0}
        self.rows = {str(y): dict(base) for y in range(2016, 2025)}
        for y in ("2020", "2021"):
            self.rows[y] = {**base, **reserve}
        self.leak = leak
        self.calls: list[tuple[float, dt.date, dt.date]] = []
        self.decider = fx.FakeDecider()

    def train(self, code, params, *, name, start=None, end=None, k=1.0):
        self.calls.append((k, start, end))
        years = [y for y in self.rows if start.year <= int(y) <= end.year]
        if self.leak and end.year < 2022:
            years.append("2020")
        factor = 1.0 if k == 1.0 else (-0.5 if "fails" in code else 0.7)
        rows = {y: {**self.rows[y], "pnl": round(self.rows[y]["pnl"] * factor, 2)} for y in years}
        result = {"run_id": f"{name}-{k}-{start}", "status": "ok", "window": "train", "start": start.isoformat(),
                  "end": end.isoformat(), "symbols": ["SPY"], "by_year": rows, "daily": fx.daily_rows(rows),
                  "summary": {"trades": sum(r["trades"] for r in rows.values()),
                              "days_traded": sum(r["days_traded"] for r in rows.values()),
                              "pnl": round(sum(r["pnl"] for r in rows.values()), 2), "fees": 1.0, "win_rate": 0.55,
                              "exposure_mean": 0.3, "max_drawdown": 30.0, "mean_net_return": 0.001},
                  "bh": {"pnl": round(sum(r["bh_pnl"] for r in rows.values()), 2)}, "mte": {"mean": 0.0004, "t": 0.9, "n": 40}}
        return SimpleNamespace(result=result, bars=None)


class TheReserve(unittest.TestCase):
    def setUp(self):
        fx.switch_on(self)
        self.settings = fx.settings(train_budget=1, train_per_round=5)

    def market(self, reserve: dict, *, leak: bool = False):
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        runner = MarketRunner(reserve, leak=leak)
        router = fx.FakeRouter(lambda call: fx.review_answer("pass", model=call["sail_profile"]) if fx.is_review(call)
                               else fx.answer([]))
        fx.e2_family(store, "earns", lane="beta", agenda="overnight", symbols=("SPY",), code=fx.program())
        fx.e2_family(store, "loses", lane="equity", agenda="reversal", symbols=("SPY",),
                     code=fx.program() + "\n# fails at the stress\n")
        EquityResearcher(store, router, self.settings, runner=runner, clock=clock).run()
        return store, clock, runner, router

    def reads(self, reserve: dict, *, leak: bool = False) -> dict:
        store, clock, runner, router = self.market(reserve, leak=leak)
        arch = Architect(store, router, self.settings, clock=clock)
        system, user = EquityPass(arch).request(EquityQuota(store, self.settings, now=clock()))
        researcher = EquityResearcher(store, router, self.settings, runner=runner, clock=clock)
        runs = {fid: [{k: r.get(k) for k in ("stress", "status", "summary")} for r in store.runs(fid, window="train")]
                for fid in ("earns", "loses")}
        return {"records": {fid: store.family(fid)["state"].get(STATE_KEY) for fid in ("earns", "loses")},
                "runs": runs, "graveyard": [dict(r) for r in store._all("SELECT family, lesson FROM graveyard")],
                "map": elane_train.train_map(store), "map_text": elane_train.train_map_text(store, self.settings),
                "refuted": elane_train.refuted_rows(store), "system": system, "user": user,
                "briefs": {fid: researcher.brief(store.family(fid)) for fid in ("earns", "loses")},
                "ledger": elane_yield.ledger(store),
                "report": elane_yield.report(store, self.settings, train_key=STATE_KEY),
                "calls": runner.calls}

    def test_two_markets_that_differ_only_in_2020_21_read_the_same(self):
        a, b = self.reads(RESERVE["a"]), self.reads(RESERVE["b"])
        for key in a:
            self.assertEqual(json.dumps(a[key], sort_keys=True, default=str), json.dumps(b[key], sort_keys=True, default=str),
                             f"{key} differs with the reserve years")
        records = a["records"]
        self.assertEqual((records["earns"]["status"], records["earns"]["passed_version"]), ("passed", 1), "really judged")
        self.assertEqual((records["loses"]["status"], records["loses"]["versions"]["1"]["fails"]), ("refuted", ["P1", "R1"]))
        self.assertEqual(sorted(records["earns"]["versions"]["1"]["years"]), [str(y) for y in elane_train.TRAIN_YEARS])
        self.assertEqual(a["calls"], [(k, *span) for _ in range(2) for k in (1.0, 1.5) for span in elane_train.TRAIN_SPANS],
                         "only the Train spans were ever run")
        self.assertEqual(a["report"]["routes"]["sail:pro_asap"]["train_passes"], 1, "the ledger counts the pass")

    def test_no_figure_of_2020_21_reaches_a_record_the_map_the_ledger_or_a_generator(self):
        for reserve in RESERVE.values():
            text = json.dumps(self.reads(reserve), sort_keys=True, default=str)
            for word in RESERVE_WORDS:
                self.assertNotIn(word, text)
            self.assertNotRegex(text, r"\b202[01]\b", "not even the reserve's years as a row")

    def test_every_text_a_generator_reads_names_the_train_years(self):
        """The architect's text, the Train map, the briefs and the review say "Train years 2016-19 and 2022-24"; none says
        2016-2024 (which would tell a generator that 2020-21 is its Train too), none names a reserve year."""
        label = elane_train.TRAIN_LABEL
        self.assertEqual(label, "Train years 2016-19 and 2022-24")
        reads = self.reads(RESERVE["a"])
        store, clock, runner, router = self.market(RESERVE["a"])
        fam = store.family("earns")
        review = elane_review.question(fam, store.version("earns", 1), card={}, lane_label="BETA", stage="review",
                                       train=elane_train.version_text(1, reads["records"]["earns"]["versions"]["1"]))
        named = {"the architect's system": reads["system"], "the architect's request (the bar)": reads["user"],
                 "the Train map": reads["map_text"], "the map's label": elane_train.MAP_LABEL,
                 "the bar": elane_train.bar_text(), "the researcher's system": elane_train.RESEARCHER_SYSTEM,
                 "the review's question": review, **{f"the brief of {fid}": text for fid, text in reads["briefs"].items()}}
        for name, text in named.items():
            self.assertIn(label, " ".join(text.split()), name)
        self.assertIn("EQUITY TRAIN MAP", reads["user"])
        self.assertIn(elane_train.MAP_LABEL, reads["user"], "the map in the architect's request carries its label")
        others = {"the review's system": elane_review.REVIEW, "the review's facts": " ".join(elane_review.FACTS.values()),
                  "the bar's fails": " ".join(elane_train.FAILS.values()), "the agenda": json.dumps(elane_train.AGENDA),
                  "the births' module texts": " ".join(v for v in vars(elane_births).values() if isinstance(v, str))}
        self.assertIn("Train years (2016-19 and 2022-24)", " ".join(elane_review.REVIEW.split()))
        for name, text in {**named, **others}.items():
            flat = " ".join(text.split())
            self.assertNotRegex(flat, r"2016\s*(-|to|through|\.\.)\s*(20)?24\b", name)
            self.assertNotRegex(flat, r"\b(nine|9) (Train )?years\b", name)
            self.assertNotRegex(flat, r"\b202[01]\b", name)
        # The bar says how many years it reads.
        self.assertIn(f"{elane_train.BAR['min_active_years']} of the {len(elane_train.TRAIN_YEARS)} Train years",
                      elane_train.bar_text())
        self.assertEqual(len(elane_train.TRAIN_YEARS), 7)

    def test_a_runner_that_leaks_a_2020_row_is_refused_whole(self):
        store, clock, runner, _ = self.market(RESERVE["a"], leak=True)
        for fid in ("earns", "loses"):
            rec = elane_train.record_of(store.family(fid))
            self.assertEqual((rec["versions"], rec["infra"]["kind"]), ({}, "window"), "judged on nothing")
            self.assertEqual(store.runs(fid, window="train"), [], "no run of it stored")
            text = json.dumps(store.family(fid)["state"], default=str)
            self.assertNotIn("8642.97", text)
        self.assertEqual(runner.decider.decides, 0, "the restart check never ran on it")
        alerts = [e for e in store.events_after(0) if e["kind"] == "swarm.status" and e["payload"].get("alert")]
        self.assertEqual({e["payload"]["action"] for e in alerts}, {"elane_train_window"})
        self.assertEqual(elane_train.train_map_text(store, self.settings).count("scored 0"), 2)


if __name__ == "__main__":
    unittest.main()
