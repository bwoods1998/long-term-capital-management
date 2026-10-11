"""THE EQUITY SEEDS (release E1, amendment A4; league/swarm/seeds.py `EQUITY_SEEDS`, league/swarm/elane.py
`birth_seeds`): three beta-lane programs with published priors, written under the EQUITY.md contract, each born once as an
agent-authored family (MARKET BETA, seeded), never while the lanes are off, and only inside the lanes' box."""

from __future__ import annotations

import ast
import math
import re
from types import SimpleNamespace
from unittest import mock

import numpy as np

from league.equity import BETA
from league.gym.safety import check_program
from league.swarm import cards, elane, loop, seeds
from league.tests.test_elane import ON
from league.tests.test_swarm_store import SPEC, StoreCase

#: The declared order (the order of the looks: league/swarm/seeds.py says why).
IDS = ("seed-overnight-qqq", "seed-reversal-index", "seed-overnight-spy")


def spec_of(sid):
    return next(s for s in seeds.EQUITY_SEEDS if s["id"] == sid)


def declared(code, name):
    tree = ast.parse(code)
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == name)
    return ast.literal_eval(node.value)


def program(sid, **params):
    """The seed's `decide` and its PARAMS, merged as the runtime merges overrides (the test's own exec: the House runs it
    in the decider-isolated child)."""
    code, overrides = seeds.equity_program_for(spec_of(sid))
    space = {}
    exec(compile(code, sid, "exec"), space)  # noqa: S102 - the repository's own seed program, in a test
    return space["decide"], {**space["PARAMS"], **overrides, **params}


def ctx(params, closes, positions=()):
    bars = {sym: SimpleNamespace(close=np.asarray(c, dtype=float)) for sym, c in closes.items()}
    return SimpleNamespace(params=params, positions=list(positions), bars=bars, symbols=tuple(closes),
                           prices={sym: float(c[-1]) for sym, c in closes.items()})


def lot(lid, symbol, held=1):
    return {"id": lid, "symbol": symbol, "class": "etf", "qty": 1.0, "entry": 100.0, "mark": 100.0, "value": 100.0,
            "pnl": 0.0, "held_sessions": held, "at": "close", "tag": ""}


class Programs(StoreCase):
    def test_each_is_a_contract_program_with_its_needs_and_params(self):
        self.assertEqual(tuple(s["id"] for s in seeds.EQUITY_SEEDS), IDS)
        want = {"seed-overnight-spy": ({"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}, {"share": 0.5}),
                "seed-overnight-qqq": ({"symbols": ["QQQ"], "history": 2, "max_hold_sessions": 2}, {"share": 0.5}),
                "seed-reversal-index": ({"symbols": ["SPY", "QQQ", "IWM", "DIA"], "history": 2, "max_hold_sessions": 10},
                                        {"theta": 0.02, "h": 8, "share": 0.25})}
        for spec in seeds.EQUITY_SEEDS:
            code, overrides = seeds.equity_program_for(spec)
            check_program(code)  # math and numpy only, no date: league/equity/program.py uses it unchanged
            self.assertEqual(overrides, {})
            self.assertEqual((declared(code, "NEEDS"), declared(code, "PARAMS")), want[spec["id"]])
            self.assertIsNone(re.search(r"(?:19|20)\d\d", code), "no year, even in a comment")
            self.assertIn("MARKET BETA", code)
            self.assertEqual((spec["lane"], spec["structure"]), (BETA, "etf"))
        self.assertEqual(len({s["template"] for s in seeds.EQUITY_SEEDS}), 3,
                         "three templates (whether two of them are one lineage is their Train returns' to say, D3)")

    def test_the_cards_name_their_prior_and_no_figure(self):
        for spec in seeds.EQUITY_SEEDS:
            got, errors = cards.validate(spec["card"], spec["structure"], roots=spec["symbols"], settings=ON)
            self.assertEqual(errors, [], spec["id"])
            self.assertEqual((got["lane"], got["symbols"]), (BETA, sorted(spec["symbols"])))
            words = got["hypothesis"]
            self.assertTrue("Connors and Alvarez" in words or "Cliff, Cooper and Gulen" in words)
            self.assertIsNone(re.search(r"\d+(?:\.\d+)?\s*%", str(got)), "no figure but the cost hurdle")

    def test_overnight_spy_buys_every_close_and_sells_every_lot_at_the_open(self):
        decide, params = program("seed-overnight-spy")
        out = decide(ctx(params, {"SPY": [100.0, 101.0]}, [lot(7, "SPY", held=0)]))
        self.assertEqual(out, [{"sell": 7, "at": "open", "tag": "overnight-exit"},
                               {"buy": "SPY", "share": 0.5, "at": "close", "tag": "overnight-entry"}])
        self.assertEqual(decide(ctx(params, {"SPY": [100.0, float("nan")]})), [], "no bar, no entry")

    def test_overnight_qqq_buys_only_after_a_down_close(self):
        decide, params = program("seed-overnight-qqq")
        self.assertEqual(decide(ctx(params, {"QQQ": [100.0, 99.0]})),
                         [{"buy": "QQQ", "share": 0.5, "at": "close", "tag": "overnight-entry"}])
        self.assertEqual(decide(ctx(params, {"QQQ": [99.0, 100.0]}, [lot(3, "QQQ")])),
                         [{"sell": 3, "at": "open", "tag": "overnight-exit"}])

    def test_reversal_buys_after_theta_down_and_exits_h_sessions_later(self):
        decide, params = program("seed-reversal-index")
        closes = {"SPY": [100.0, 97.9], "QQQ": [100.0, 98.5], "IWM": [100.0, 90.0], "DIA": [100.0, 95.0]}
        # h 8: the lot bought at an open is sold at the open 8 sessions later, so at the close where it was held 7
        # (league/equity/EQUITY.md: held_sessions is 0 at the entry session's own close); held 6, it waits.
        out = decide(ctx(params, closes, [lot(1, "IWM", held=7), lot(2, "DIA", held=6)]))
        self.assertEqual(out, [{"sell": 1, "at": "open", "tag": "reversal-exit"},
                               {"buy": "SPY", "share": 0.25, "at": "open", "tag": "reversal-entry"},
                               {"buy": "IWM", "share": 0.25, "at": "open", "tag": "reversal-entry"}],
                         "a symbol held and not exiting is not bought again")
        decide, params = program("seed-reversal-index", theta=0.01, h=3)
        out = decide(ctx(params, closes, [lot(2, "DIA", held=3)]))
        self.assertEqual([i.get("buy") or i.get("sell") for i in out], [2, "SPY", "QQQ", "IWM", "DIA"])
        self.assertTrue(math.isclose(params["theta"], 0.01))


class Births(StoreCase):
    def test_never_while_the_lanes_are_off(self):
        self.assertEqual(elane.birth_seeds(self.store, {}), [])
        self.assertEqual(self.store.families(lanes="all"), [])

    def test_each_seed_is_born_once_as_an_agent_authored_beta_family(self):
        self.store.add_family(SPEC, origin="seed")
        born = elane.birth_seeds(self.store, ON)
        self.assertEqual(born, list(IDS))
        self.assertEqual(elane.birth_seeds(self.store, ON), [], "once each, ever")
        self.assertEqual(self.store.get(elane.SEEDS_KEY), {sid: sid for sid in IDS})
        self.assertEqual([f["id"] for f in self.store.families()], ["condor-vrp"], "the options readers never see them")
        for fid in IDS:
            fam = self.store.family(fid)
            spec = spec_of(fid)
            self.assertEqual((fam["structure"], fam["roots"], fam["spec"]["lane"], fam["spec"]["seeded"], fam["band"]),
                             ("etf", list(spec["symbols"]), BETA, True, "gym"))
            self.assertEqual(elane.lane_of(self.store, fam), BETA)
            self.assertTrue(elane.seeded(self.store, fid))
            version = self.store.version(fid, fam["best_version"])
            self.assertEqual((version["n"], version["code"], self.store.versions(fid)[0]["author"]),
                             (1, seeds.equity_program_for(spec)[0], elane.SEED_AUTHOR))
            stored = cards.card_of(self.store, fid)
            self.assertEqual((stored["card"]["lane"], stored["sha"]), (BETA, fam["spec"]["card_sha"]))
            self.assertEqual(fam["state"][elane.TEMPLATE_KEY], elane.lineage_key(BETA, version["sha"]))
        self.assertFalse(elane.seeded(self.store, "condor-vrp"))
        events = [e for e in self.store.events_after(0) if e["kind"] == "swarm.born"]
        self.assertEqual([e["family"] for e in events], list(IDS))
        self.assertTrue(all(e["payload"]["lane"] == BETA and e["payload"]["seeded"] and
                            e["payload"]["label"] == "MARKET BETA" for e in events))
        self.assertEqual(sorted(len(self.store._connected_lineages(fid)) for fid in IDS), [1, 1, 1])

    def test_only_inside_the_lanes_box_as_set_now(self):
        narrow = {"elane": {"mode": "gate", "universe": ["SPY"]}}
        self.assertEqual(elane.birth_seeds(self.store, narrow), ["seed-overnight-spy"])
        self.assertEqual(elane.birth_seeds(self.store, ON), ["seed-overnight-qqq", "seed-reversal-index"])

    def test_the_loop_births_them_while_the_lanes_are_on_and_adopts_the_equity_identity(self):
        fake = SimpleNamespace(settings={}, store=self.store)
        self.assertEqual(loop.Swarm.equity_births(fake), [])
        fake.settings = ON
        self.assertEqual(loop.Swarm.equity_births(fake), list(IDS))
        with mock.patch.object(elane, "birth_seeds", side_effect=RuntimeError("boom")):
            self.assertEqual(loop.Swarm.equity_births(fake), [], "a birth never stops the loop")
        with mock.patch("league.swarm.evaluator.equity_identity", return_value={"equity": "f" * 64}), \
                mock.patch("league.swarm.evaluator.adopt_equity", return_value={"adopted": True, "families": 3}) as adopt:
            self.assertEqual(loop.Swarm.adopt_equity(fake)["families"], 3)
        adopt.assert_called_once_with(self.store, {"equity": "f" * 64})
        with mock.patch("league.swarm.evaluator.adopt_equity", side_effect=NotImplementedError("core")):
            self.assertIsNone(loop.Swarm.adopt_equity(fake), "never keeps the swarm from starting")
