"""The swarm window (Oct 1, 2026: the owner asked that anyone can see why an agent traded, every trade's result and the
agents' progress through the game's levels): `league/site_window.py` reads it read-only from the swarm's store, the live
book and the practice record; `league/publish.py` allowlists it (`site_levels`, `site_rationale`), pins every agent a real
position names, and sends it to sites that take it (an older site gets the checkpoint without it). Public safety first:
a thesis or a reason is whole words with no digit, no number word, no colon, no bracket, no code mark and no parameter
name, and nothing a quote licence forbids ever leaves. The book and the store are the live path's and the swarm's own
schemas; every number in them is invented."""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import sqlite3
import tempfile
import unittest
import unittest.mock
import urllib.error
from pathlib import Path
from types import SimpleNamespace

from league import publish, site_window, trading_profit
from league.ledger import Ledger
from league.publish import Publisher, SiteInputs, build_checkpoint, thesis_words, windowless
from league.swarm import public, sitefeed
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock, result

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SITE_SCHEMA = FIXTURES / "site_schema.js"
RESET_AT = "2026-09-26T06:25:30.000Z"
RESET = 1790403930.0
PUBLISHED_AT = "2026-10-01T06:00:00.000Z"
NOW = 1790834400.0
GOOGL = ("MSFT and GOOGL sell competing AI-cloud and search products, and investors reprice one on the other's capex or "
         "product news with a delay. When MSFT moves strongly over several sessions, QQQ is flat and GOOGL has not followed, "
         "GOOGL is expected to close part of the gap.")
GOOGL_ID = "googl-lags-msft-ai-cloud-qqq-flat"
#: Its program names `qqq_flat`, words its public id already spells (`public.unspelled`), and `lag_thresh`, which it does not.
GOOGL_PROGRAM = 'PARAMS = {"lead_sessions": 3, "qqq_flat": 0.4, "lag_thresh": 1.5}\nNEEDS = ["MSFT", "GOOGL", "QQQ"]\n'
#: What no thesis, reason or key may ever carry (the site's `thesisWords` and the licence).
LEAK = re.compile(r"[0-9:()\[\]{}<>=_`#|\\]")


def iso(seconds: float) -> str:
    return publish.site_instant(seconds)


def googl_fill(*, side="buy", reason="", entry_reason=None, realized=None, **private):
    """A `book.fill` of the GOOGL vertical as the live book records it (`league/live/real.py`), with its private keys."""
    from league import structure_core as sc

    spec = sc.classify("debit_vertical", [sc.leg(sc.occ_code("GOOGL", "2026-10-07", "call", 355), 1),
                                          sc.leg(sc.occ_code("GOOGL", "2026-10-07", "call", 360), -1)])
    out = {"source": "venue", "side": side, "real_money": True, "quantity": 1, "reason": reason,
           "instrument": {"asset_class": "option", "symbol": "GOOGL", "multiplier": "100", "expiry": spec.expiry, "market_id": spec.code}}
    if side == "buy":
        out["max_loss_usd"] = 157.0
    else:
        out.update(realized=realized, entry_reason=entry_reason)
    return {**out, **private}


#: The safety review's adversarial list (Oct 1, 2026): each was a number the filters let through.
QUANT_CASES = (
    "Buy the call when GOOGL lags MSFT by more than one stdev.", "Enter when the gap exceeds one ATR over the prior close.",
    "Enter at one sd.", "Use a lookback of one hr.", "Exit after one trading session if the gap has not closed.",
    "Buy when the move is one full standard deviation below the mean.", "Hold for one more week before rolling.",
    "Buy GOOGL calls with a strike one notch above spot.", "Stop out at negative one ATR.", "One leg is enough.",
    "Exit at the eleventh session.", "Enter when the lag reaches a twelfth of the range.", "Hold until the ninetieth minute.",
    "Buy when the drop exceeds twelve hundredths.", "The move must be threefold the median.", "Wait for a twentyfive delta call.",
    "Enter on a tenpercent move.", "Exit after a oneday hold.", "Enter at a single sigma move.", "Enter at a sigma move.",
    "Exit after an ATR against it.", "Hold for a fortnight.", "Enter when the spread is wider than a nickel.",
    "Enter when the move tops a dime.", "Enter when the move tops a penny.", "Enter when IV rank is in the top decile.",
    "Sell when IV sits in the twenties.", "Enter when volume doubles.", "Exit when ONE SIGMA is breached.",
    "Enter when the lag tops one-and-a-half sigma.", "Stop out at minus one hundred bps.", "Enter when RSI tops seventy.",
    "Exit in the last quarter of the session.", "Sell at a quarter of the range.", "Hold a quarter.")
#: The post-fix verification's list (Oct 1, 2026, 09:30Z): an apostrophe around or inside a number word, an accent, a
#: plural cardinal, a suffix or a percent run together, a multiple, a couple, unity, a score, a word split by a mark, and
#: "one" before a measure the review missed.
VERIFICATION_CASES = (
    "Enter on a 'twenty-day' high.", "Respect the fifty's rule.", "Hold for \u2018twenty\u2019 sessions.",
    "Hold for \u2018twenty\u2019s worth.", "Hold for tw\u00e9nty sessions.", "Wait sev\u00e9n days.", "Buy in fives.",
    "Sell the sixes.", "Wait out the zeroes.", "Hold for twentyish sessions.", "Hold for twenty-ish sessions.",
    "Hold for twentyodd sessions.", "The range is thirtysomething wide.", "Enter on a tenpct move.", "Stop out at fiftybps.",
    "Enter when volume quintuples.", "Exit when the range trebles.", "Hold for a couple of sessions.",
    "Enter when the ratio tops unity.", "Hold for a score of sessions.", "Wait scores of sessions.",
    "Hold for twen\u00b7ty sessions.", "Hold for t.e.n sessions.", "Sell the fif-ty's high.", "Sell the twen\u00b7ty's high.",
    "Buy in ones and twos.", "Read the ones digit.", "Enter at a halfsigma move.", "Sell a quarter's worth.",
    "Hold the one whole session.", "Exit after one business day.", "Exit after a single business day.",
    "Exit when \u00bane sigma is breached.", "Exit when \uff4f\uff4e\uff45 sigma is breached.", "Hold twenty'll do.",
    "Exit at the trillionth.", "Enter at the twentieth's close.")
#: Plain words that must still pass: the pronoun "one", the calendar's quarter, "ones" as a pronoun, a pair, a z-score.
PLAIN_CASES = (
    "No one knows the open.", "The legs move one against the other.", "Each one decays.", "One of the names leads.",
    "They reprice one after another.", "Buyers favour one or the other.", "One\u2019s edge is patience.",
    "A single stock leads.", "Uses a single-name option on the laggard.", "The edge is one-sided.",
    "Investors reprice one on the other\u2019s news.", "The tape drifts \u2014 then the gap closes.",
    "The flow is predictable within the final sessions of each quarter.", "Funds dress their books at quarter-end.",
    "Funds dress their books at the quarter's end.", "The ones that lag catch up.", "The pair converges.",
    "It is a pairs trade.", "The z-score tops its band.", "The legs are coupled.", "Someone's bid leads.", "No one's sure.",
    "Often the tent is quiet.", "Prices move one from the other.", "They move one and the other.", "It won't last.", GOOGL)


# ---------------------------------------------------------------------------------------------- the words
class ThesisTextTest(unittest.TestCase):
    def test_the_googl_thesis_is_both_sentences_and_the_pronoun_one_passes(self):
        """The spec's C1: `note_text` counts "one" as a number word and drops the first sentence; a thesis keeps it."""
        self.assertIsNone(public.note_text(GOOGL.split(". ")[0] + "."), "note_text drops it (C1)")
        self.assertEqual(public.thesis_text(GOOGL), GOOGL)
        self.assertEqual(len(GOOGL), 268)
        self.assertEqual(thesis_words(GOOGL, 280), GOOGL, "the publisher's check takes the swarm's thesis as it is")

    def test_a_number_in_digits_or_in_words_never_passes(self):
        for text in ("IWM breaks to a fresh 60-day low.", "Sell a twenty five delta put.", "Exit at one standard deviation.",
                     "Hold it for one day.", "Buy one twenty strike calls.", "Sell at point one eight.", "Take half the credit.",
                     "Hold two sessions then exit.", "Enter in the first hour.", "Buy one contract when it breaks.",
                     "Wait a dozen sessions.", "Exit at the third bar."):
            self.assertIsNone(public.thesis_text(text), text)
            self.assertIsNone(public.tag_text(text.rstrip(".")), text)
        self.assertEqual(public.thesis_text("Investors reprice one on the other. The rest follows."),
                         "Investors reprice one on the other. The rest follows.")

    def test_a_colon_a_bracket_a_code_mark_or_a_parameter_name_drops_its_sentence(self):
        text = ("The gap closes slowly. Exit rule: sell on strength. Wings (as the graveyard said) cost less. "
                "Uses ctx.minute to time it. A lag_days setting decides. The flat band matters most. Quiet days pay.")
        self.assertEqual(public.thesis_text(text, param_names=("lag_days", "flat_band")), "The gap closes slowly. Quiet days pay.")
        self.assertIsNone(public.tag_text("lag days high", param_names=("lag_days",)))
        self.assertIsNone(public.tag_text("exit: strength"))
        self.assertIsNone(public.tag_text("PARAMS changed"))
        self.assertIsNone(public.tag_text("x = y"))
        self.assertIsNone(public.thesis_text(GOOGL, param_names=("googl",)), "a parameter named in both sentences: nothing")

    def test_whole_sentences_only_a_cut_fragment_never_shows(self):
        """The published mechanism is cut at 240 characters (`site_agent`), mid-sentence: the thesis reads the store's full
        text, and a fragment that does not end its sentence is never shown."""
        self.assertEqual(public.thesis_text(GOOGL[:240]), GOOGL.split(" When")[0])
        self.assertIsNone(public.thesis_text("Sells the opening range break when the tape"), "no sentence end: nothing")

    def test_sentences_fit_in_order_up_to_280_and_a_long_first_one_is_cut_at_a_word(self):
        sentences = [f"Sentence {word} says something useful about the tape." for word in
                     ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf")]
        out = public.thesis_text(" ".join(sentences))
        self.assertLessEqual(len(out), 280)
        self.assertTrue(" ".join(sentences).startswith(out) and out.endswith("."), "whole sentences in order")
        self.assertGreater(len(out) + len(sentences[len(out.split(". "))]) + 1, 280, "as many as fit")
        long = "The market " + "keeps drifting sideways and " * 20 + "ends."
        cut = public.thesis_text(long)
        self.assertTrue(cut.endswith("…") and len(cut) <= 280 and long.startswith(cut[:-1]), cut)
        self.assertEqual(thesis_words(cut, 280), cut)

    def test_a_tag_is_whole_or_nothing(self):
        self.assertEqual(public.tag_text("msft leads googl, qqq flat"), "msft leads googl, qqq flat")
        self.assertIsNone(public.tag_text("x" * 79 + "y"), "exactly the 80 characters a stored tag is cut to: presumed cut")
        self.assertIsNone(public.tag_text("a long reason " * 7), "longer than its limit")
        self.assertIsNone(public.tag_text("buy"), "too short to say anything")
        self.assertIsNone(public.tag_text("IWM at a 60-day low"))

    def test_ordinary_quant_phrasing_of_a_number_never_passes(self):
        """The safety review's adversarial list and the post-fix verification's (Oct 1, 2026): each was a number the
        filters let through. The check is a fixed list, never the filter graded against itself."""
        for text in QUANT_CASES + VERIFICATION_CASES:
            self.assertTrue(public.numbered(text) or not public.plain_glyphs(text), ascii(text))
            self.assertIsNone(public.thesis_text(text), text)
            self.assertIsNone(public.tag_text(text.rstrip(".")), text)
            self.assertIsNone(public.note_text(text), text)
            self.assertIsNone(public.mechanism_text(text), text)
            self.assertIsNone(thesis_words(text, 280), text)
        self.assertIsNone(public.tag_text("lag over one stdev"))

    def test_the_pronoun_one_and_plain_words_still_pass(self):
        for text in PLAIN_CASES:
            self.assertFalse(public.numbered(text), text)
            self.assertEqual(public.thesis_text(text), text)
            self.assertEqual(thesis_words(text, 280), text)

    def test_a_numeral_of_any_script_a_hidden_mark_or_a_look_alike_letter_never_passes(self):
        for text in ("Enter when the gap exceeds \u00bd of the prior move.", "Sell when IV rank tops \u00be of its range.",
                     "Use the \u216b month lookback.", "Wait for a \u3007 reading.", "Enter when IV is \u0663 points over realized.",
                     "Exit at \u2460 sigma.", "Exit when \uff4f\uff4e\uff45 sigma is breached.", "Exit when \u03bfne sigma is breached.",
                     "Exit when \u043ene sigma is breached.", "Wait sev\u00aden days.", "Wait sev\u200den days.", "Wait o\u0336ne day.",
                     "Exit after \U0001f51f sessions.", "Exit at \u00b2 sigma."):
            self.assertIsNone(public.thesis_text(text), ascii(text))
            self.assertIsNone(public.tag_text(text.rstrip(".")), ascii(text))
            self.assertIsNone(public.note_text(text), ascii(text))
            self.assertIsNone(public.mechanism_text(text), ascii(text))
            self.assertIsNone(thesis_words(text, 280), ascii(text))
            self.assertFalse(public.plain_glyphs(text) and not public.numbered(text), ascii(text))

    def test_a_parameter_name_written_with_hyphens_or_run_together_is_still_its_name(self):
        names = ("drift_window", "lookback", "z_entry")
        for text in ("Enter when the drift-window shows a lag.", "Enter when the driftwindow shows a lag.", "Enter when the drift window shows a lag.",
                     "Use the look-back to time it.", "Enter when z-entry fires.", "Enter when the drift\u2011window shows a lag."):
            self.assertIsNone(public.thesis_text(text, param_names=names), text)
            self.assertIsNone(public.mechanism_text(text, param_names=names), text)
            self.assertIsNone(public.note_text(text, param_names=names), text)
        self.assertEqual(public.thesis_text("Exit when QQQ is flat again.", param_names=names), "Exit when QQQ is flat again.")

    def test_random_text_never_leaks_a_number_a_mark_or_a_parameter(self):
        rng = random.Random(20261001)
        words = ["the", "tape", "gap", "closes", "slowly", "one", "two", "twenty", "half", "point", "day", "sessions", "delta",
                 "standard", "deviation", "strike", "lead", "lag", "flat_band", "lag days", "ctx.minute", "PARAMS", "x=1", "(gap)",
                 "rule:", "3", "1.25", "$5", "60-day", "[a]", "{b}", "<c>", "`d`", "#e", "|f", "reprice", "on", "the", "other",
                 "QQQ", "MSFT", "Alpaca", "bid", "ask", "mid", "quiet", "trend", "drift", "Kalshi", "-", "->", "a", "of"]
        names = ("flat_band", "lag_days", "lead")
        for _ in range(3000):
            text = " ".join(" ".join(rng.choice(words) for _ in range(rng.randint(2, 12))) + rng.choice(".!?,")
                            for _ in range(rng.randint(1, 5)))
            for out, limit in ((public.thesis_text(text, param_names=names), 280), (public.tag_text(text, param_names=names), 80)):
                if out is None:
                    continue
                self.assertFalse(LEAK.search(out), (text, out))
                low = out.lower()
                self.assertFalse(any(n in low for n in ("flat_band", "flat band", "lag_days", "lag days", "lead")), out)
                self.assertFalse(any(public.numbered(s) for s in public.SENTENCE.split(out.replace("…", ""))), out)
                self.assertLessEqual(len(out), limit)
                published = thesis_words(out, limit)
                self.assertTrue(published is None or not LEAK.search(published), published)
                if not re.search(r"alpaca|kalshi", out, re.I):
                    self.assertEqual(published, out, "a filtered thesis passes the publisher's check unchanged")


class NumberWordsFixtureTest(unittest.TestCase):
    """`fixtures/number_words.json` is the case list both repositories test their number rule against (the House's
    `public.numbered`, the site's `numbered` in `capital/capital.js`): this module's own lists, rewritten by
    LTCM_WRITE_SITE_FIXTURES=1. LTCM_SITE_CAPITAL=<a site branch's capital/capital.js> runs the site's own rule over it."""

    PATH = FIXTURES / "number_words.json"

    def cases(self):
        return {"about": "Each sentence under `numbered` is a number in words and each under `plain` is not, for "
                         "league/swarm/public.py `numbered` and the site's `numbered` alike (league/tests/test_site_window.py).",
                "numbered": list(QUANT_CASES + VERIFICATION_CASES), "plain": list(PLAIN_CASES)}

    def test_the_fixture_is_this_modules_own_lists_and_the_house_agrees_with_it(self):
        cases = self.cases()
        if os.environ.get("LTCM_WRITE_SITE_FIXTURES"):
            self.PATH.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual(json.loads(self.PATH.read_text(encoding="utf-8")), cases)
        self.assertEqual([t for t in cases["numbered"] if not public.numbered(t)], [])
        self.assertEqual([t for t in cases["plain"] if public.numbered(t)], [])

    def test_the_sites_rule_agrees_case_for_case(self):
        import subprocess

        capital, node = os.environ.get("LTCM_SITE_CAPITAL"), shutil.which("node")
        if not capital or node is None:
            raise unittest.SkipTest("set LTCM_SITE_CAPITAL to a site branch's capital/capital.js (and have node)")
        script = (f"import {{ numbered }} from {json.dumps(Path(capital).resolve().as_uri())};"
                  "let text = ''; process.stdin.on('data', chunk => { text += chunk; });"
                  "process.stdin.on('end', () => console.log(JSON.stringify(JSON.parse(text).map(t => numbered(t)))));")
        cases = self.cases()
        texts = cases["numbered"] + cases["plain"]
        done = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps(texts), capture_output=True, text=True,
                              timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr[-2000:])
        site = dict(zip(texts, json.loads(done.stdout)))
        self.assertEqual({t: site[t] for t in texts if site[t] != public.numbered(t)}, {}, "the site disagrees")


class TapeWhyTest(unittest.TestCase):
    """S3 of the post-fix verification (Oct 1, 2026): a trade's reason on the tape (`agent.trade` `why`, `/api/capital/events`
    and the socket) went out as the publisher's `words`, which keep integers and number words. Now it is the tag rules
    over the traded program's parameter names, or "" (the site's `prose` takes an empty reason, never null)."""

    def test_a_reason_with_a_number_a_parameter_or_a_cut_never_reaches_the_tape(self):
        reason = "lag thresh 3 sessions, z above 2 and qqq within 4 of flat"
        self.assertEqual(publish.trade_of(googl_fill(reason=reason), close=False, names=())["why"], "")
        self.assertEqual(publish.trade_of(googl_fill(reason=reason), close=False, names=("lag_thresh",))["why"], "")
        self.assertEqual(publish.tape_why("lag thresh hit while qqq is flat", ("lag_thresh",), stored=240), "")
        self.assertEqual(publish.tape_why("msft led for twenty sessions", (), stored=240), "")
        self.assertEqual(publish.tape_why("msft led for fifty's worth of sessions", (), stored=240), "")
        self.assertEqual(publish.tape_why("msft leads googl, qqq flat", None, stored=240), "", "names unknown: no reason")
        self.assertEqual(publish.tape_why("msft leads googl " + "and more " * 30, (), stored=240), "", "longer than 240")
        cut = ("msft leads googl " * 15)[:240]
        self.assertEqual((len(cut), publish.tape_why(cut, (), stored=240)), (240, ""), "cut where it was stored")
        self.assertEqual(publish.tape_why("msft leads googl, qqq flat", ("lag_thresh",), stored=240), "msft leads googl, qqq flat")
        self.assertEqual(publish.tape_why("msft leads googl on alpaca", (), stored=240), "msft leads googl on the broker")

    def test_a_close_carries_its_opening_tag_under_the_same_rules(self):
        tag = "msft leads googl, qqq flat"
        close = publish.trade_of(googl_fill(side="sell", reason="program", entry_reason=tag, realized=12.5), close=True, pnl=12.5, names=())
        self.assertEqual((close["action"], close["why"]), ("close", tag))
        cut = ("msft leads googl " * 6)[:80]
        close = publish.trade_of(googl_fill(side="sell", reason="program", entry_reason=cut, realized=1.0), close=True, pnl=1.0, names=())
        self.assertEqual(close["why"], "", "a tag of exactly 80 was cut")

    def test_without_a_resolver_a_trade_carries_no_reason(self):
        from league.ledger import Entry

        entry = Entry(seq=1, id="le-1", kind="book.fill", agent=GOOGL_ID, at=PUBLISHED_AT, public=True,
                      payload=googl_fill(reason="msft leads googl, qqq flat", _order=1), previous_hash="p", digest="d")
        self.assertEqual(publish.to_events(entry)[0]["payload"]["why"], "")
        self.assertEqual(publish.to_events(entry, lambda row: ())[0]["payload"]["why"], "msft leads googl, qqq flat")
        self.assertEqual(publish.to_events(entry, lambda row: None)[0]["payload"]["why"], "")


class HeadroomTest(unittest.TestCase):
    def test_the_fit_leaves_room_for_a_name_on_every_row_the_sites_read_names(self):
        """The post-fix verification (Oct 1, 2026): the public read adds `display_name` to every agent, every agent's
        position and every practice row, each name at most 40 characters; a body fitted to the limit must read back
        under it. The site's own bounds, where its schema spells them, are the House's."""
        self.assertEqual(publish.NAMED_ROWS, publish.MAX_AGENTS + publish.MAX_POSITIONS + publish.MAX_PRACTICE_ROWS)
        self.assertEqual(publish.DISPLAY_NAME_BYTES, len(json.dumps({"display_name": "M" * 40}, separators=(",", ":"))) - 1)
        self.assertGreaterEqual(publish.FIT_HEADROOM_BYTES, publish.NAMED_ROWS * publish.DISPLAY_NAME_BYTES)
        for schema in {SITE_SCHEMA, Path(os.environ.get("LTCM_SITE_SCHEMA") or SITE_SCHEMA)}:
            text = schema.read_text(encoding="utf-8")
            for name in ("MAX_AGENTS", "MAX_POSITIONS", "MAX_PRACTICE_ROWS", "MAX_CHECKPOINT_BYTES"):
                found = re.search(rf"export const {name} = ([0-9 *]+);", text)
                if found:
                    self.assertEqual(eval(found.group(1), {}), getattr(publish, name), (schema, name))  # noqa: S307 - digits and "*"
            longest = re.search(r"validDisplayName = value => typeof value === 'string' && value.length <= (\d+)", text)
            if longest:
                self.assertEqual(int(longest.group(1)), publish.DISPLAY_NAME_CHARS, schema)

    def test_a_fitted_body_with_every_named_row_at_the_longest_name_reads_back_under_the_limit(self):
        agents = [{"id": f"agent-{n}", "family": "agent", "mechanism": "A quiet edge in words. " * 9, "structure": "iron_condor",
                   "band": "gym", "born_at": RESET_AT, "retired_at": None, "trials": 1, "revisions": 1, "forward": None, "real": None}
                  for n in range(publish.MAX_AGENTS)]
        body = build_checkpoint(SiteInputs(agents=agents), PUBLISHED_AT)
        size = len(publish.canonical(body).encode())
        cap = size + publish.FIT_HEADROOM_BYTES  # fitted exactly to the limit, nothing left out
        with unittest.mock.patch.object(publish, "MAX_CHECKPOINT_BYTES", cap):
            fitted = build_checkpoint(SiteInputs(agents=agents), PUBLISHED_AT)
        self.assertEqual(len(fitted["agents"]), publish.MAX_AGENTS)
        # The read names these agents, and at most a full table and a full practice league more.
        named = {**fitted, "agents": [{**a, "display_name": "Meriwether " + "9" * 29} for a in fitted["agents"]]}
        extra = (publish.MAX_POSITIONS + publish.MAX_PRACTICE_ROWS) * publish.DISPLAY_NAME_BYTES
        self.assertLessEqual(len(json.dumps(named, separators=(",", ":"), ensure_ascii=False).encode()) + extra, cap)


# ---------------------------------------------------------------------------------------------- the world
class World:
    """A House's three stores as the swarm and the live path write them: the swarm's store, the live book
    (`live.sqlite`, the live path's own schema) and the practice record (`observe.sqlite`)."""

    def __init__(self, root: Path):
        from league.live.state import LiveState

        self.root, self.swarm, self.state = root, root / "swarm", root / "state"
        self.swarm.mkdir()
        self.state.mkdir()
        self.clock = Clock(RESET + 3600)
        self.store = SwarmStore(self.swarm, clock=self.clock)
        self.live = LiveState(self.state / "live.sqlite")
        self.pid = 0
        self.oid = 0

    def close(self):
        self.store.close()
        self.live.close()

    def family(self, fid, *, mechanism=None, structure="debit_vertical", code=None, params=None, at=None):
        if at is not None:
            self.clock.t = at
        self.store.add_family({"id": fid, "mechanism": mechanism or f"The {fid.replace('-', ' ')} family trades a quiet edge.",
                               "structure": structure, "roots": ["SPY"]}, origin="seed")
        if code is not None:
            self.store.add_version(fid, code, params or {}, author="seed")
        self.clock.t = max(self.clock.t, RESET + 3600)
        return fid

    def instance(self, key, family, *, tuition=0, band="gym", mode="live", retired_at=None, code="PARAMS = {}\n", params=None,
                 created_at=RESET + 7200):
        self.live.upsert("instances", {"id": key, "family": family, "version": 1, "run_sha": f"sha-{key}", "code": code,
                                       "params": json.dumps(params or {}), "band": band, "tuition": tuition, "mode": mode,
                                       "created_at": created_at, "retired_at": retired_at, "why": None}, "id")

    def position(self, family, instance, *, status="open", tuition=0, share=1.57, qty=1, tag="", reason="", opened_at=RESET + 86400,
                 closed_at=None, cash=-157.0, kind="debit_vertical", root="GOOGL", expiry="2026-10-07"):
        self.pid += 1
        legs = [{"symbol": f"{root}261007C00355000", "side": 1, "ratio": 1, "is_call": True, "strike": 355.0, "expiry": expiry, "key": 0},
                {"symbol": f"{root}261007C00360000", "side": -1, "ratio": 1, "is_call": True, "strike": 360.0, "expiry": expiry, "key": 1}]
        if kind in ("long_call", "long_put"):
            legs = [{**legs[0], "is_call": kind == "long_call"}]
        self.live.upsert("positions", {
            "pid": self.pid, "instance": instance, "family": family, "type": kind, "root": root, "legs": json.dumps(legs),
            "qty": qty if status == "open" else 0, "opened_qty": qty, "entry": share, "max_loss_share": share, "collateral": 0.0,
            "fees": 0.0, "cash": cash, "opened_at": opened_at, "opened_day": "2026-09-30", "opened_minute": 600, "tag": tag,
            "note": "PRIVATE note: entry 1.57 at the 355 strike", "status": status, "closed_at": closed_at, "exit_value_qty": 0.0,
            "reason": reason, "tuition": tuition, "info": "{}"}, "pid")
        return self.pid

    def order(self, pid, action, *, why="", forced=0, filled=1, placed_at=None):
        self.oid += 1
        pos = self.live.rows("SELECT * FROM positions WHERE pid=?", (pid,))[0]
        self.live.execute(
            "INSERT INTO orders(oid, client_id, instance, family, action, type, root, legs, qty, limit_value, limit_price, placed_at,"
            " day, placed_minute, status, filled_qty, pid, forced, why, answer, updated_at) VALUES"
            " (?,?,?,?,?,?,?,?,?,1.57,'1.57',?,'2026-09-30',600,'filled',?,?,?,?,'{}',?)",
            (self.oid, f"c{self.oid}", pos["instance"], pos["family"], action, pos["type"], pos["root"], pos["legs"], filled,
             placed_at or pos["opened_at"] + self.oid, filled, pid, forced, why, placed_at or pos["opened_at"] + self.oid))
        return self.oid

    def practice(self, family, *, first_at, tier="train", row=True):
        """A practice row (`row`), or only a practice trade: an evidence reset completes the rows and keeps the trades."""
        from league.live.observe import SCHEMA

        db = sqlite3.connect(self.state / "observe.sqlite")
        db.executescript(SCHEMA)
        if row:
            db.execute("INSERT INTO practice(family, version, tier, capital, first_at, first_day, last_at, last_day) VALUES (?,?,?,?,?,?,?,?)",
                       (family, 1, tier, 10000.0, first_at, "2026-09-29", first_at + 3600, "2026-09-30"))
        else:
            db.execute("INSERT INTO trades(instance, account, family, version, trade_id, day, pnl, max_loss, recorded_at, body) VALUES"
                       " (?,?,?,?,?,?,?,?,?,?)", (f"{family}@1:o", "a", family, 1, "t1", "2026-09-29", 1.0, 10.0, first_at, "{}"))
        db.commit()
        db.close()

    def rows(self):
        """The positions table's rows as the publisher reads them (`trading_profit.ledger`: the open one unpriced, as after
        hours)."""
        return trading_profit.ledger(self.state, None, at=PUBLISHED_AT, start_at=RESET_AT)["rows"]


class WorldCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="window-", dir=os.environ.get("TMPDIR")))
        self.world = World(self.dir)

    def tearDown(self):
        self.world.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def today(self):
        """The floor of Oct 1, 2026 in miniature: Mullins 166's GOOGL vertical (D2 tuition, open, its agent retired since),
        an incubator round trip its agent closed, the House's calibration, a validated family, a practising one, a
        Candidate, two failed holdout looks, a family born before the reset that validated after it, and thirty retirements
        newer than the GOOGL agent's."""
        w = self.world
        w.family(GOOGL_ID, mechanism=GOOGL, code=GOOGL_PROGRAM)
        w.instance(f"{GOOGL_ID}@27:t", GOOGL_ID, tuition=1, mode="exit_only",
                   code=GOOGL_PROGRAM + 'PARAMS["exit_after"] = 2\n', params={"lead_sessions": 3, "exit_after": 2})
        googl = w.position(GOOGL_ID, f"{GOOGL_ID}@27:t", tuition=1, tag="msft leads googl, qqq flat")
        w.order(googl, "open", why="msft leads googl, qqq flat")
        w.clock.t = RESET + 2 * 86400
        w.store.retire(GOOGL_ID, "no improvement in 30 revisions")
        w.family("orb-break", mechanism="Trades the break of the opening range in the direction of the break. It exits "
                                         "before the close when the break fails.", code="PARAMS = {'range_minutes': 30}\n")
        w.instance("orb-break@4:i", "orb-break", tuition=1)
        orb = w.position("orb-break", "orb-break@4:i", status="closed", tuition=1, share=0.42, tag="range broke up",
                         reason="program", cash=12.5, closed_at=RESET + 90000, kind="long_call", root="SPY")
        w.order(orb, "open", why="range broke up")
        w.order(orb, "close", why="the break failed")
        for n in range(2):
            cal = w.position("house:calibration", "house:calibration@1:c", status="closed", share=0.2, tag="calibration",
                             reason="program", cash=-1.1, closed_at=RESET + 95000 + n, kind="long_put", root="SPY")
            w.order(cal, "open", why="House calibration: open")
            w.order(cal, "close", why="House calibration: close")
        w.family("condor-quiet", mechanism="Sells an iron condor on quiet mornings when the overnight range was narrow.",
                 structure="iron_condor", code="PARAMS = {}\n")
        w.store.set_state("condor-quiet", validation_version=1)
        w.store.add_run("condor-quiet", 1, result("cq"), window="validation", stress=1.0, purpose="validation")
        w.family("iwm-crash-cluster-straddle", structure="long_straddle", code="PARAMS = {}\n")
        w.practice("iwm-crash-cluster-straddle", first_at=RESET + 50000)
        w.family("dip-practised", code="PARAMS = {}\n")
        w.practice("dip-practised", first_at=RESET + 40000, row=False)
        w.practice("before-reset", first_at=RESET - 40000, row=False)
        w.family("skew-carry", structure="credit_vertical", code="PARAMS = {}\n")
        w.store.add_look("skew-carry", 1, "look-sha-1", passed=True, p_value=0.01, detail={})
        w.store.set_band("skew-carry", "candidate", reason="its holdout look passed")
        w.family("look-fail", code="PARAMS = {}\n")
        w.store.add_look("look-fail", 1, "look-sha-2", passed=False, p_value=0.4, detail={})
        w.store.add_look("look-fail", 1, "look-sha-3", passed=False, p_value=0.5, detail={})
        w.family("old-before", code="PARAMS = {}\n", at=RESET - 3600)
        w.store.add_run("old-before", 1, result("ob"), window="validation", stress=1.0, purpose="validation")
        for n in range(30):
            w.clock.t = RESET + 3 * 86400 + n
            w.family(f"spent-{n}")
            w.store.retire(f"spent-{n}", "no improvement in 30 revisions")
        w.clock.t = NOW - 60
        return {"googl": googl, "orb": orb}

    def window(self, agents=None, practice_rows=None):
        agents = agents if agents is not None else sitefeed.site_inputs(self.world.swarm)["agents"]
        return site_window.site_window(self.world.swarm, self.world.state, agents=agents, positions_rows=self.world.rows(),
                                       practice_rows=practice_rows if practice_rows is not None else
                                       [{"family": "iwm-crash-cluster-straddle", "live": True}],
                                       start_at=RESET_AT, at=PUBLISHED_AT)


# ------------------------------------------------------------------------------------------- the positions
class PositionRowsTest(WorldCase):
    def test_route_and_exit_from_the_book(self):
        route, exit_of = trading_profit.route_of, trading_profit.exit_of
        bands = {"a@1:r": "probe", "b@1:r": "sized", "c@1:r": "candidate"}
        self.assertEqual(route({"family": "house:calibration", "instance": "x"}), "calibration")
        self.assertEqual(route({"family": "house:rebound-live", "instance": "x"}), "house")
        self.assertEqual(route({"family": "orb", "instance": "orb@4:i", "tuition": 1}), "incubator", "restored tuition-flagged: still the incubator")
        self.assertEqual(route({"family": "a", "instance": "a@1:t", "tuition": 1}, bands), "tuition")
        self.assertEqual(route({"family": "a", "instance": "a@1:r", "tuition": 0}, bands), "probe")
        self.assertEqual(route({"family": "b", "instance": "b@1:r", "tuition": 0}, bands), "sized")
        self.assertIsNone(route({"family": "c", "instance": "c@1:r", "tuition": 0}, bands))
        self.assertIsNone(route({"family": "house:other", "instance": "x"}))
        forced = [{"forced": 1}]
        for row, closes, want in (
                ({"status": "open"}, [], None), ({"status": "awaiting_expiry"}, [], None),
                ({"status": "closed", "reason": "program", "family": "a"}, [{"forced": 0}], "agent"),
                ({"status": "closed", "reason": "forced", "family": "a"}, forced, "house"),
                ({"status": "closed", "reason": "program", "family": "a"}, forced, "house"),
                ({"status": "closed", "reason": "broken: legs closed alone", "family": "a"}, [], "house"),
                ({"status": "closed", "reason": "settled", "family": "a"}, [], "expiry"),
                ({"status": "closed", "reason": "settled at the last recorded level (the House missed the close)", "family": "a"}, [], "expiry"),
                ({"status": "closed", "reason": "expired", "family": "a"}, [], "expiry"),
                ({"status": "closed", "reason": "assigned", "family": "a"}, [], "expiry"),
                ({"status": "closed", "reason": "venue liquidation reconciled from external fills", "family": "a"}, [], "expiry"),
                ({"status": "unpriced_close", "reason": "", "family": "a"}, [], "expiry"),
                ({"status": "closed", "reason": "program", "family": "house:calibration"}, [], "house"),
                ({"status": "closed", "reason": "something new", "family": "a"}, [], None)):
            self.assertEqual(exit_of(row, closes), want, row)

    def test_the_rows_carry_the_publishers_private_keys_and_the_allowlist_never_sends_them(self):
        ids = self.today()
        rows = {row["pid"]: row for row in self.world.rows()}
        googl, orb = rows[ids["googl"]], rows[ids["orb"]]
        self.assertEqual((googl["_route"], googl["_exit"], googl["_tag"], googl["_max_loss"], googl["_close_why"]),
                         ("tuition", None, "msft leads googl, qqq flat", "157.00", None))
        self.assertEqual((orb["_route"], orb["_exit"], orb["_close_why"], orb["_instance"]),
                         ("incubator", "agent", "the break failed", "orb-break@4:i"))
        body = build_checkpoint(SiteInputs(trading={"as_of": PUBLISHED_AT, "pnl_usd": None},
                                           positions={"as_of": PUBLISHED_AT, "rows": list(rows.values()), "other": None,
                                                      "unreconciled_usd": None}), PUBLISHED_AT)
        self.assertEqual(len(body["positions"]["rows"]), 4)
        text = json.dumps(body)
        for leak in ("_tag", "_route", "_exit", "_close_why", "_max_loss", "_instance", "PRIVATE", "355", "1.57", "@27"):
            self.assertNotIn(leak, text)

    def test_the_maximum_loss_at_open_is_what_the_open_structure_publishes(self):
        """`_max_loss` is the figure `structures[].max_loss_usd` publishes for the same whole position (real:14: 157.00)."""
        from league.live.real import RLeg, RPosition

        rng = random.Random(14)
        for n in range(300):
            share = 1.57 if n == 0 else round(rng.uniform(0.01, 25.0), rng.choice((2, 3, 4)))
            qty = 1 if n == 0 else rng.randint(1, 40)
            legs = [RLeg("GOOGL261007C00355000", 1, 1, True, 355.0, "2026-10-07", 0), RLeg("GOOGL261007C00360000", -1, 1, True, 360.0, "2026-10-07", 1)]
            pos = RPosition(1000 + n, f"{GOOGL_ID}@27:t", GOOGL_ID, "debit_vertical", "GOOGL", legs, qty, qty, share, share, 0.0,
                            opened_at=RESET + 86400, status="open", tuition=True)
            [row] = trading_profit.position_rows([pos.row()], [], {})
            published = publish.site_structure({"id": f"real:{pos.pid}", "agent": GOOGL_ID, "underlying": "GOOGL", "structure": "debit_vertical",
                                                "legs": 2, "expiry": "2026-10-07", "quantity": qty, "real": True, "opened_at": iso(RESET + 86400),
                                                "max_loss_usd": round(pos.max_loss, 2), "pnl_usd": None}, PUBLISHED_AT)
            self.assertEqual(row["_max_loss"], published["max_loss_usd"], (share, qty))
            if n == 0:
                self.assertEqual(row["_max_loss"], "157.00")

    def test_the_constants_are_the_live_modules_own(self):
        from league import swarm
        from league.gym import venue
        from league.live import calibration, house_test, observe, real, state

        self.assertEqual(site_window.LIVE_FILE, state.STATE_FILE)
        self.assertEqual(site_window.OBSERVE_FILE, observe.FILE)
        self.assertEqual(site_window.INCUBATOR_SUFFIX, real.INCUBATOR_SUFFIX)
        self.assertEqual(site_window.CALIBRATION_FAMILY, calibration.FAMILY)
        self.assertEqual(site_window.HOUSE_TEST_FAMILY, house_test.FAMILY)
        self.assertEqual(site_window.SWARM_DB, swarm.DB_NAME)
        self.assertEqual(trading_profit.MULTIPLIER, venue.MULTIPLIER)
        for name in ("LEVELS", "LEVELS_BY_BAND", "FUNNEL_KEYS"):
            self.assertEqual(getattr(site_window, name), getattr(publish, name), name)
        self.assertEqual(tuple(trading_profit.EXITS), publish.EXITS)
        self.assertEqual(set(trading_profit.ROUTE_RANK) | {"calibration", "house"}, set(publish.ROUTES))


# ------------------------------------------------------------------------------------------- the levels
class LevelsTest(WorldCase):
    def test_the_first_rule_that_holds_wins_and_never_contradicts_the_band(self):
        level = site_window.level_of
        self.assertEqual(level("retired", money=["tuition"]), "tuition", "a retired agent with open money stands on its step")
        self.assertEqual(level("retired", money=["tuition", "sized"]), "sized", "the highest route")
        self.assertEqual(level("retired"), "retired")
        self.assertEqual(level("gym", money=["incubator"], tuition=True, validated=True), "incubator")
        self.assertEqual(level("gym", money=["probe"], tuition=True), "tuition", "a Gym family never stands on Probe")
        self.assertEqual(level("candidate", money=["tuition"]), "candidate", "a Candidate's old tuition lot: its band")
        self.assertEqual(level("probe", money=["probe"]), "probe")
        self.assertEqual(level("sized"), "sized")
        self.assertEqual(level("gym", tuition=True, incubator=True, validated=True, practising=True), "tuition")
        self.assertEqual(level("gym", incubator=True, validated=True, practising=True), "incubator")
        self.assertEqual(level("gym", validated=True, practising=True), "validation", "a validated family that practises: Validation")
        self.assertEqual(level("gym", practising=True), "practice")
        self.assertEqual(level("gym"), "train")
        self.assertIsNone(level("paper"))
        for band, allowed in site_window.LEVELS_BY_BAND.items():
            for flags in range(32):
                money = [r for i, r in enumerate(("tuition", "incubator", "probe", "sized")) if flags >> i & 1]
                got = level(band, money=money, tuition=bool(flags & 1), incubator=bool(flags & 2), validated=bool(flags & 4),
                            practising=bool(flags & 8))
                self.assertIn(got, allowed, (band, flags))

    def test_today_on_the_map(self):
        self.today()
        agents = sitefeed.site_inputs(self.world.swarm)["agents"]
        self.assertNotIn(GOOGL_ID, {a["id"] for a in agents}, "thirty newer retirements: off the roster's 24")
        agents += [dict(row, pinned=True) for row in sitefeed.agent_rows(self.world.swarm, [GOOGL_ID])]
        levels = {row["id"]: row["level"] for row in self.window(agents)["levels"]["agents"]}
        self.assertEqual(levels[GOOGL_ID], "tuition", "retired, and its GOOGL vertical still open")
        self.assertEqual(levels["orb-break"], "incubator", "an active incubator instance")
        self.assertEqual(levels["condor-quiet"], "validation")
        self.assertEqual(levels["iwm-crash-cluster-straddle"], "practice")
        self.assertEqual(levels["skew-carry"], "candidate")
        self.assertEqual(levels["look-fail"], "train")
        self.assertEqual(levels["spent-29"], "retired")

    def test_an_exit_only_tuition_instance_with_nothing_open_is_not_tuition(self):
        w = self.world
        w.family("idle-tuition", code="PARAMS = {}\n")
        w.instance("idle-tuition@2:t", "idle-tuition", tuition=1, mode="exit_only")
        w.family("live-tuition", code="PARAMS = {}\n")
        w.instance("live-tuition@2:t", "live-tuition", tuition=1)
        w.instance("live-tuition@1:t", "live-tuition", tuition=1, retired_at=RESET + 9000)
        levels = {row["id"]: row["level"] for row in self.window(practice_rows=[])["levels"]["agents"]}
        self.assertEqual((levels["idle-tuition"], levels["live-tuition"]), ("train", "tuition"))


class FunnelTest(WorldCase):
    def test_the_counts_since_the_reset_are_unions_up_each_track(self):
        self.today()
        funnel = self.window()["levels"]["funnel"]
        self.assertEqual(funnel["since"], RESET_AT)
        self.assertEqual((funnel["looks"], funnel["looks_passed"]), (3, 1), "looks, not families")
        self.assertEqual((funnel["sized"], funnel["probe"], funnel["candidate"]), (0, 0, 1))
        self.assertEqual(funnel["tuition"], 1, "the GOOGL lot only: a holdout look, failed or passed, is no tuition")
        self.assertEqual(funnel["validation"], 5, "the GOOGL lot, the two that looked, + condor-quiet's run, + old-before's after the reset")
        self.assertEqual((funnel["incubator"], funnel["practice"]), (1, 3),
                         "practice: a row, a trade an evidence reset kept, and the incubator's family; never a trade before the reset")
        self.assertEqual(funnel["retired"], 31)
        self.assertEqual(funnel["born"], 38, "37 born since, and old-before: it validated since")
        self.assertEqual((funnel["calibration"], funnel["live_test"]), (2, 0))
        self.assertTrue(publish.site_funnel(funnel, PUBLISHED_AT) == {**funnel}, "the allowlist takes it whole")

    def test_every_chain_narrows_whatever_the_sets(self):
        rng = random.Random(7)
        fams = [f"f{n}" for n in range(40)]
        for _ in range(400):
            pick = lambda: set(rng.sample(fams, rng.randint(0, 12)))  # noqa: E731
            swarm = {"fams": {f: {"band": rng.choice(("gym", "candidate", "probe", "sized", "retired")), "born_at": iso(RESET + rng.choice((-1, 1)) * 999),
                                  "retired_at": rng.choice((None, iso(RESET - 99), iso(RESET + 99)))} for f in fams},
                     "moves": [(f, rng.choice(("gym", "candidate", "probe", "sized")), RESET + 9) for f in pick()],
                     "looks": [{"family": f, "passed": rng.randint(0, 1)} for f in pick()], "validated": pick()}
            live = {"instances": [{"id": f"{f}@1:{rng.choice('ti')}", "family": f, "tuition": rng.randint(0, 1),
                                   "created_at": RESET + rng.choice((-5, 5))} for f in pick()],
                    "positions": [{"family": rng.choice(fams + ["house:calibration", "house:rebound-live"]), "instance": "x@1:i",
                                   "tuition": rng.randint(0, 1), "opened_at": RESET + rng.choice((-5, 5))} for _ in range(rng.randint(0, 8))]}
            for live_given in (live, None):
                for practised in (pick(), None):
                    funnel = site_window.funnel(RESET_AT, RESET, swarm, live_given, practised)
                    self.assertEqual(publish.site_funnel(funnel, PUBLISHED_AT), funnel, "never a chain the site refuses")
                    if live_given is None:
                        self.assertEqual([funnel[k] for k in ("tuition", "validation", "incubator", "practice", "calibration")], [None] * 5)
        self.assertEqual(set(site_window.funnel(RESET_AT, RESET, None, None, None)) - {"since"}, set(publish.FUNNEL_KEYS) - {"since"})
        self.assertTrue(all(v is None for k, v in site_window.funnel(RESET_AT, RESET, None, None, None).items() if k != "since"))

    def test_a_chain_that_does_not_narrow_is_unknown_never_shown_wrong(self):
        funnel = {key: 1 for key in publish.FUNNEL_KEYS}
        funnel.update(since=RESET_AT, sized=5, looks_passed=3, looks=2)
        out = publish.site_funnel(funnel, PUBLISHED_AT)
        for key in ("sized", "probe", "candidate", "validation", "born", "looks", "looks_passed"):
            self.assertIsNone(out[key], key)
        self.assertEqual((out["incubator"], out["practice"], out["calibration"], out["tuition"]), (1, 1, 1, 1))
        branch = {**{key: 0 for key in publish.FUNNEL_KEYS}, "since": RESET_AT, "born": 9, "validation": 6, "candidate": 3, "tuition": 1}
        self.assertEqual(publish.site_funnel(branch, PUBLISHED_AT), branch, "Candidate above Tuition: Tuition is a branch of its own")
        self.assertIsNone(publish.site_funnel({**branch, "tuition": 7}, PUBLISHED_AT)["tuition"], "but never above Validation")
        self.assertIsNone(publish.site_funnel({**funnel, "since": "2026-10-02T00:00:00Z"}, PUBLISHED_AT))
        self.assertIsNone(publish.site_funnel({**funnel, "born": True}, PUBLISHED_AT)["born"], "a bool is no count")

    def test_an_unreadable_store_is_unknown_never_zero(self):
        self.today()
        self.world.live.close()
        for name in ("live.sqlite-wal", "live.sqlite-shm"):
            (self.world.state / name).unlink(missing_ok=True)
        (self.world.state / "live.sqlite").write_bytes(b"not a database at all" * 100)
        window = self.window()
        self.assertEqual([window["levels"]["funnel"][k] for k in ("tuition", "validation", "incubator", "calibration")], [None] * 4)
        self.assertEqual(window["levels"]["funnel"]["candidate"], 1, "what the swarm's store says still shows")
        self.assertTrue(all(t["thesis"] is None for t in window["rationale"]["agents"]),
                        "a live instance's parameter names cannot be read: no thesis rather than one unchecked")
        self.assertIsNone(site_window.site_window(self.dir / "nowhere", self.world.state, agents=[], positions_rows=[],
                                                  practice_rows=[], start_at=RESET_AT, at=PUBLISHED_AT))
        self.assertIsNone(site_window.site_window(self.world.swarm, self.world.state, agents=[], positions_rows=[], practice_rows=[],
                                                  start_at=None, at=PUBLISHED_AT))


# ------------------------------------------------------------------------------------------- the rationale
class RationaleTest(WorldCase):
    def test_why_each_trade_was_made_and_how_it_ended(self):
        ids = self.today()
        agents = sitefeed.site_inputs(self.world.swarm)["agents"] + [dict(r, pinned=True) for r in sitefeed.agent_rows(self.world.swarm, [GOOGL_ID])]
        window = self.window(agents)
        theses = {row["id"]: row["thesis"] for row in window["rationale"]["agents"]}
        self.assertEqual(theses[GOOGL_ID], GOOGL, "both sentences, from the store's full mechanism")
        self.assertEqual(theses["orb-break"], "Trades the break of the opening range in the direction of the break. It exits "
                                              "before the close when the break fails.")
        trades = {row["id"]: row for row in window["rationale"]["trades"]}
        self.assertEqual(trades[f"real:{ids['googl']}"], {"id": f"real:{ids['googl']}", "route": "tuition",
                                                          "open_why": "msft leads googl, qqq flat", "close_why": None, "exit": None,
                                                          "max_loss_usd": "157.00"})
        self.assertEqual(trades[f"real:{ids['orb']}"], {"id": f"real:{ids['orb']}", "route": "incubator", "open_why": "range broke up",
                                                        "close_why": "the break failed", "exit": "agent", "max_loss_usd": "42.00"})
        house = [row for row in trades.values() if row["route"] == "calibration"]
        self.assertEqual(len(house), 2)
        self.assertTrue(all((row["open_why"], row["close_why"], row["exit"]) == (None, None, "house") for row in house),
                        "the House's rows carry no reason")

    def test_the_route_is_the_band_the_position_was_opened_on(self):
        """The integration review (Oct 1, 2026): a Probe position whose instance has since moved to Sized says Probe."""
        w = self.world
        w.family("climber", code="PARAMS = {}\n")
        w.clock.t = RESET + 20000
        w.store.set_band("climber", "candidate", reason="its holdout look passed")
        w.clock.t = RESET + 30000
        w.store.set_band("climber", "probe", reason="the Money table")
        w.instance("climber@1:r", "climber", band="sized")
        early = w.position("climber", "climber@1:r", opened_at=RESET + 25000)
        probe = w.position("climber", "climber@1:r", opened_at=RESET + 40000)
        w.clock.t = RESET + 50000
        w.store.set_band("climber", "sized", reason="the Money table")
        sized = w.position("climber", "climber@1:r", opened_at=RESET + 60000)
        w.family("unmoved", code="PARAMS = {}\n")
        w.instance("unmoved@1:r", "unmoved", band="probe")
        unmoved = w.position("unmoved", "unmoved@1:r", opened_at=RESET + 60000)
        w.clock.t = NOW - 60
        routes = {row["id"]: row["route"] for row in self.window(practice_rows=[])["rationale"]["trades"]}
        self.assertEqual((routes[f"real:{probe}"], routes[f"real:{sized}"]), ("probe", "sized"))
        self.assertIsNone(routes[f"real:{early}"], "opened while a Candidate, on no tuition flag: no route rather than today's")
        self.assertEqual(routes[f"real:{unmoved}"], "probe", "no move since the reset: the instance's band")
        self.assertEqual(site_window.band_at([("a", "probe", 5.0), ("a", "sized", 9.0), ("b", "gym", 1.0)], "a", 9.0), "sized")
        self.assertIsNone(site_window.band_at([("a", "probe", 5.0)], "a", 4.0))
        self.assertIsNone(site_window.band_at([("a", "probe", 5.0)], "a", None))

    def test_a_name_the_agents_public_id_spells_is_not_withheld(self):
        """Production, Oct 1: the GOOGL agent's newest program names `qqq_flat`, and its open reason "msft leads googl, qqq
        flat" says the words its id already shows; `lag_thresh` is not in the id, so a reason naming it is still dropped."""
        self.assertEqual(public.unspelled(["qqq_flat", "lag", "lag_thresh", "googl", "use_qqq"], GOOGL_ID), ["lag", "lag_thresh", "use_qqq"])
        names = public.unspelled(public.param_names_of(GOOGL_PROGRAM), GOOGL_ID)
        self.assertEqual(public.tag_text("msft leads googl, qqq flat", param_names=names), "msft leads googl, qqq flat")
        self.assertIsNone(public.tag_text("lag thresh crossed", param_names=names))
        self.assertIsNone(public.tag_text("msft leads googl, qqq flat", param_names=public.param_names_of(GOOGL_PROGRAM)),
                          "without the exemption the rule drops it")

    def test_a_parameter_of_the_traded_program_or_of_any_version_is_never_in_a_thesis_or_a_reason(self):
        w = self.world
        w.family("lagger", mechanism="It buys when the leader moves early. The lead sessions matter. Exit after a drift. Wide "
                                      "wings help.", code='PARAMS = {"lead_sessions": 3}\n')
        w.store.add_version("lagger", 'PARAMS = {"lead_sessions": 3, "drift_stop": 1}\n', {"wide_wings": 2}, author="r")
        w.instance("lagger@2:t", "lagger", tuition=1, code='PARAMS = {"exit_after": 2}\n', params={"leader_gap": 1})
        pid = w.position("lagger", "lagger@2:t", tuition=1, tag="exit after the leader gap", status="closed", reason="program",
                         closed_at=RESET + 99999, cash=3.0)
        w.order(pid, "close", why="leader gap closed")
        window = self.window(practice_rows=[])
        [thesis] = [row["thesis"] for row in window["rationale"]["agents"] if row["id"] == "lagger"]
        self.assertEqual(thesis, "It buys when the leader moves early.",
                         "the newest program's PARAMS (lead sessions), a version's overrides (wide wings) and the traded instance's "
                         "program (exit after) each drop their sentence")
        [trade] = window["rationale"]["trades"]
        self.assertEqual((trade["open_why"], trade["close_why"]), (None, None), "the traded instance's own names drop both reasons")

    def test_a_close_reason_is_the_agents_own_and_only_when_it_closed_the_trade(self):
        w = self.world
        w.family("closer", code="PARAMS = {}\n")
        w.instance("closer@1:t", "closer", tuition=1)
        own = w.position("closer", "closer@1:t", tuition=1, status="closed", reason="program", closed_at=RESET + 90000, cash=1.0)
        w.order(own, "close", why="older close", placed_at=RESET + 86500)
        w.order(own, "close", why="the target was reached", placed_at=RESET + 86600)
        w.order(own, "close", why="never filled", filled=0, placed_at=RESET + 86700)
        forced = w.position("closer", "closer@1:t", tuition=1, status="closed", reason="forced", closed_at=RESET + 90001, cash=1.0)
        w.order(forced, "close", why="expiring today", forced=1)
        silent = w.position("closer", "closer@1:t", tuition=1, status="closed", reason="program", closed_at=RESET + 90002, cash=1.0)
        w.order(silent, "close", why="program")
        expired = w.position("closer", "closer@1:t", tuition=1, status="closed", reason="expired", closed_at=RESET + 90003, cash=1.0)
        trades = {row["id"]: row for row in self.window(practice_rows=[])["rationale"]["trades"]}
        self.assertEqual((trades[f"real:{own}"]["close_why"], trades[f"real:{own}"]["exit"]), ("the target was reached", "agent"))
        self.assertEqual((trades[f"real:{forced}"]["close_why"], trades[f"real:{forced}"]["exit"]), (None, "house"))
        self.assertEqual((trades[f"real:{silent}"]["close_why"], trades[f"real:{silent}"]["exit"]), (None, "agent"), "no reason given")
        self.assertEqual((trades[f"real:{expired}"]["close_why"], trades[f"real:{expired}"]["exit"]), (None, "expiry"))

    def test_the_allowlist_drops_what_breaks_a_rule_and_keeps_the_rest(self):
        self.today()
        agents = sitefeed.site_inputs(self.world.swarm)["agents"]
        rows = self.world.rows()
        positions = {"as_of": PUBLISHED_AT, "rows": rows, "other": None, "unreconciled_usd": None}
        listed = publish.site_positions(positions, {"as_of": PUBLISHED_AT, "pnl_usd": None}, PUBLISHED_AT)
        shown = [publish.site_agent(a, PUBLISHED_AT) for a in agents]
        cal = next(r["id"] for r in listed["rows"] if r["source"] == "calibration")
        orb = next(r["id"] for r in listed["rows"] if r["source"] == "incubator")
        raw = {"as_of": PUBLISHED_AT, "agents": [{"id": "orb-break", "thesis": "Sells at 30 delta."}, {"id": "orb-break", "thesis": "Twice."},
                                                 {"id": "nobody", "thesis": "Never shown."}, {"id": "condor-quiet", "thesis": "Rule: sell."},
                                                 {"id": "look-fail", "thesis": "Sells the broker's Alpaca account."}],
               "trades": [{"id": cal, "route": "tuition", "open_why": "calibrate", "close_why": "done", "exit": "agent", "max_loss_usd": "20.00"},
                          {"id": orb, "route": "probe", "open_why": "range: up", "close_why": "it failed", "exit": "maybe", "max_loss_usd": "-1"},
                          {"id": "real:999", "route": None, "open_why": None, "close_why": None, "exit": None, "max_loss_usd": None}]}
        out = publish.site_rationale(raw, shown, listed, PUBLISHED_AT)
        self.assertEqual(out["agents"], [{"id": "orb-break", "thesis": None}, {"id": "condor-quiet", "thesis": None},
                                         {"id": "look-fail", "thesis": "Sells the broker's the broker account."}])
        trades = {t["id"]: t for t in out["trades"]}
        self.assertEqual(trades[cal], {"id": cal, "route": None, "open_why": None, "close_why": None, "exit": "agent", "max_loss_usd": "20.00"})
        self.assertEqual(trades[orb], {"id": orb, "route": None, "open_why": None, "close_why": "it failed", "exit": None, "max_loss_usd": None})
        self.assertNotIn("real:999", trades, "a row the table does not list")
        self.assertEqual(publish.site_rationale(raw, shown, None, PUBLISHED_AT)["trades"], [], "no table: no trades")
        late = {**raw, "as_of": "2026-10-01T06:02:00.000Z"}
        self.assertIsNone(publish.site_rationale(late, shown, listed, PUBLISHED_AT), "a reading after the stamp")
        levels = publish.site_levels({"as_of": PUBLISHED_AT, "agents": [{"id": "skew-carry", "level": "tuition"}, {"id": "condor-quiet", "level": "validation"},
                                                                         {"id": "condor-quiet", "level": "train"}, {"id": "nobody", "level": "train"},
                                                                         {"id": "spent-29", "level": "sized"}, {"id": "spent-28", "level": "train"}],
                                      "funnel": {"since": RESET_AT}}, shown, PUBLISHED_AT)
        self.assertEqual(levels["agents"], [{"id": "condor-quiet", "level": "validation"}, {"id": "spent-29", "level": "sized"}])
        self.assertTrue(all(levels["funnel"][k] is None for k in publish.FUNNEL_KEYS if k != "since"), "a count not given is unknown")


class TapeNamesTest(WorldCase):
    def test_the_traded_instance_and_its_familys_parameter_names_by_order_or_position(self):
        ids = self.today()
        w = self.world
        oid = w.live.rows("SELECT oid FROM orders WHERE pid=? AND action='open'", (ids["googl"],))[0]["oid"]
        want = ("exit_after", "lag_thresh", "lead_sessions")  # qqq_flat: its public id spells it
        self.assertEqual(site_window.tape_names(w.state, w.swarm, GOOGL_ID, oid=oid), want)
        self.assertEqual(site_window.tape_names(w.state, w.swarm, GOOGL_ID, pid=ids["googl"]), want)
        for unknown in ({"oid": 999}, {"pid": 999}, {}, {"oid": "1"}, {"oid": True}):
            self.assertIsNone(site_window.tape_names(w.state, w.swarm, GOOGL_ID, **unknown), unknown)
        self.assertIsNone(site_window.tape_names(w.state, None, GOOGL_ID, oid=oid), "no swarm store: unknown")
        self.assertIsNone(site_window.tape_names(w.state / "missing", w.swarm, GOOGL_ID, oid=oid), "no live book: unknown")
        with unittest.mock.patch.object(sitefeed, "param_names", lambda db, root, ids: {i: ((), False) for i in ids}):
            self.assertIsNone(site_window.tape_names(w.state, w.swarm, GOOGL_ID, oid=oid), "its program cannot be read")


class MechanismNamesTest(WorldCase):
    def test_a_parameter_named_in_a_mechanism_never_publishes(self):
        """The swarm window's review, C8: the roster's mechanism was `news_text` with no parameter names at all."""
        w = self.world
        w.family("namer", mechanism="Buys when the entry delta is rich. Quiet days pay. The wing width barely matters.",
                 code='PARAMS = {"entry_delta": 0.3}\n')
        mechanism = lambda: next(a["mechanism"] for a in sitefeed.site_inputs(w.swarm)["agents"] if a["id"] == "namer")  # noqa: E731
        self.assertEqual(mechanism(), "Quiet days pay. The wing width barely matters.")
        w.store.add_version("namer", 'PARAMS = {"quiet_days": 1}\n', {"wing_width": 2}, author="r")
        self.assertIsNone(mechanism(), "a new program's names, a version's overrides, and the old program's names all count")
        self.assertEqual([a["mechanism"] for a in sitefeed.agent_rows(w.swarm, ["namer"])], [None])
        (w.swarm / w.store.version("namer", 2)["path"]).unlink()
        sitefeed._NAMES.clear()  # a program once read stays known (it never changes): a new process reads it again
        sitefeed._CODE_NAMES.clear()
        db = sqlite3.connect(f"file:{w.swarm / 'swarm.sqlite'}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        names, known = sitefeed.param_names(db, w.swarm, ["namer"])["namer"]
        db.close()
        self.assertFalse(known, "the program it runs now cannot be read: its names are not all known")
        self.assertEqual(set(names), {"entry_delta", "wing_width"})


class MechanismNumbersTest(WorldCase):
    """The safety review (Oct 1, 2026): the roster's mechanism and the birth news kept whole numbers ("8-21 DTE", "over the
    next 1-3 sessions"); no sentence with a number reaches either now."""

    SPXW = ("When 7-14 DTE SPXW implied vol trades below trailing realized vol, long index volatility is underpriced. The "
            "inversion is the entry (a rare one). Index volatility reprices when the tape wakes up.")

    def test_a_mechanism_keeps_only_its_sentences_with_no_number(self):
        self.assertEqual(public.mechanism_text(self.SPXW), "The inversion is the entry. Index volatility reprices when the tape wakes up.")
        self.assertIsNone(public.mechanism_text("Buys 8-21 DTE GLD calls. Exits over the next 1-3 sessions."))
        self.assertIsNone(public.mechanism_text("Enter when the z-score exceeds 2.5 standard deviations."),
                          "never a number removed and the rest shown with its meaning changed")
        self.assertEqual(public.mechanism_text("Edge: quiet tapes revert. Wings cost less."), "Edge: quiet tapes revert. Wings cost less.")
        whole = public.mechanism_text(GOOGL)
        self.assertEqual(whole, GOOGL.split(" When")[0], "whole sentences while they fit 240, never a fragment")
        self.assertEqual(public.mechanism_text(GOOGL, limit=400), GOOGL)

    def test_the_roster_and_the_birth_news_carry_no_number(self):
        w = self.world
        w.family("spxw-vol-discount-single", mechanism=self.SPXW, structure="long_straddle", code="PARAMS = {}\n")
        w.family("gld-vol-discount-single", mechanism="Pushes 8-21 DTE GLD IV below trailing realized vol.", code="PARAMS = {}\n")
        rows = {a["id"]: a for a in sitefeed.site_inputs(w.swarm)["agents"]}
        self.assertEqual(rows["spxw-vol-discount-single"]["mechanism"],
                         "The inversion is the entry. Index volatility reprices when the tape wakes up.")
        self.assertIsNone(rows["gld-vol-discount-single"]["mechanism"])
        self.assertEqual(publish.site_agent({**rows["gld-vol-discount-single"], "mechanism": "Buys 3-7 DTE calls."}, PUBLISHED_AT)["mechanism"], "",
                         "the allowlist drops it too, whoever sent it")
        from league.swarm.hook import public_payload

        born = public_payload("swarm.born", {"parent": None, "mechanism": "Buys 14-21 DTE puts after a gap. Gaps fade.", "cause": "x"}, [])
        self.assertEqual(born["mechanism"], "Gaps fade.")
        self.assertEqual(public_payload("swarm.retired", {"cause": "no validation improvement in 30 revisions"}, [])["cause"],
                         "no validation improvement in 30 revisions", "the swarm's own rule keeps its whole numbers")
        older = publish.league_news("swarm.born", "gld-vol-discount-single", {"parent": None, "mechanism": "Buys 2-5 DTE calls. Gaps fade."})
        self.assertEqual(older, "is born, a new family: Gaps fade.", "a ledger row written before this rule")
        self.assertEqual(publish.league_news("swarm.born", "x", {"parent": "y", "mechanism": "Buys 2-5 DTE calls."}), "is born, forked from its parent.")


# ------------------------------------------------------------------------------------------- the roster
class PinningTest(WorldCase):
    def test_an_agent_a_real_position_names_is_pinned_outside_the_retired_24(self):
        ids = self.today()
        agents = sitefeed.site_inputs(self.world.swarm)["agents"]
        rows = self.world.rows()
        pinned = Publisher._pinned(agents, self.world.swarm, {"rows": rows}, [])
        googl = [a for a in pinned if a["id"] == GOOGL_ID]
        self.assertEqual(len(googl), 1)
        self.assertEqual((googl[0]["band"], googl[0]["pinned"], googl[0]["mechanism"][:24]), ("retired", True, "MSFT and GOOGL sell comp"))
        self.assertEqual(set(googl[0]), set(agents[0]) | {"pinned"}, "the same row as the roster's")
        self.assertTrue(next(a for a in pinned if a["id"] == "orb-break")["pinned"], "the incubator's agent too")
        body = build_checkpoint(SiteInputs(agents=pinned), PUBLISHED_AT)
        retired = [a["id"] for a in body["agents"] if a["band"] == "retired"]
        self.assertEqual(len(retired), 25, "the 24 newest, and the pinned one beside them")
        self.assertEqual(retired[0], GOOGL_ID)
        self.assertNotIn("pinned", json.dumps(body))
        self.assertIn(f"real:{ids['googl']}", {f"real:{r['pid']}" for r in rows})

    def test_under_byte_pressure_the_pinned_leave_last(self):
        agents = [{"id": f"alive-{n}", "family": "alive", "mechanism": "A quiet edge in words. " * 9, "structure": "iron_condor", "band": "gym",
                   "born_at": RESET_AT, "retired_at": None, "trials": 1, "revisions": 1, "forward": None, "real": None} for n in range(120)]
        agents += [{**agents[0], "id": f"dead-{n}", "band": "retired", "retired_at": iso(RESET + n)} for n in range(30)]
        agents[-1]["pinned"] = True  # the oldest retired below is pinned
        agents[120]["pinned"] = True
        body = build_checkpoint(SiteInputs(agents=agents), PUBLISHED_AT)
        self.assertIn("dead-0", [a["id"] for a in body["agents"]], "pinned: kept though older than the 24 newest")
        body["structures"] = []
        room = publish.MAX_CHECKPOINT_BYTES - publish.FIT_HEADROOM_BYTES - 13_616  # what the old 16 KiB headroom left
        squeezed = publish.fit({**body, "agents": list(body["agents"]), "padding": "x" * room},
                               {"dead-0", "dead-29"})
        kept = [a["id"] for a in squeezed["agents"]]
        self.assertIn("dead-0", kept)
        self.assertIn("dead-29", kept)
        self.assertLess(len(kept), len(body["agents"]))

    def test_under_byte_pressure_the_window_leaves_before_any_agent_or_row(self):
        """The integration review (Oct 1, 2026): the window is the first to go, theses first, so an older site's windowless
        body is what fitting it alone gives; and the fit leaves room for the names the site's public read adds."""
        agents = [{"id": f"alive-{n}", "family": "alive", "mechanism": "A quiet edge in words. " * 9, "structure": "iron_condor", "band": "gym",
                   "born_at": RESET_AT, "retired_at": None, "trials": 1, "revisions": 1, "forward": None, "real": None} for n in range(150)]
        theses = [{"id": a["id"], "thesis": "A quiet edge in words. " * 12} for a in agents]
        inputs = SiteInputs(agents=agents, levels={"as_of": PUBLISHED_AT, "agents": [{"id": a["id"], "level": "train"} for a in agents],
                                                   "funnel": {"since": RESET_AT}},
                            rationale={"as_of": PUBLISHED_AT, "agents": [{**t, "thesis": t["thesis"].strip()} for t in theses], "trades": []})
        body = build_checkpoint(inputs, PUBLISHED_AT)
        self.assertEqual(len(body["rationale"]["agents"]), 150)
        size = len(publish.canonical(body).encode())
        windowless_size = len(publish.canonical(windowless(body)).encode())
        theses_size = size - len(publish.canonical({**body, "rationale": {**body["rationale"], "agents": []}}).encode())
        for cap, want in ((size + publish.FIT_HEADROOM_BYTES - theses_size // 2, "no theses"),
                          (windowless_size + publish.FIT_HEADROOM_BYTES + 10, "no window"),
                          (windowless_size + publish.FIT_HEADROOM_BYTES - 5000, "fewer agents")):
            with unittest.mock.patch.object(publish, "MAX_CHECKPOINT_BYTES", cap):
                fitted = build_checkpoint(inputs, PUBLISHED_AT)
                alone = publish.fit(json.loads(json.dumps(windowless(body))))
            self.assertLessEqual(len(publish.canonical(fitted).encode()), cap - publish.FIT_HEADROOM_BYTES)
            self.assertEqual(windowless(fitted), alone, want)
            if want == "no theses":
                self.assertEqual((fitted["rationale"]["agents"], len(fitted["agents"]), len(fitted["levels"]["agents"])), ([], 150, 150))
            elif want == "no window":
                self.assertNotIn("levels", fitted)
                self.assertEqual(len(fitted["agents"]), 150, "every agent stays")
            else:
                self.assertNotIn("rationale", fitted)
                self.assertLess(len(fitted["agents"]), 150)


# ------------------------------------------------------------------------------------------- the publisher
class Response:
    def __init__(self, status, body):
        self.status, self._body = status, json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Body:
    def __init__(self, data):
        self.data = data

    def read(self, *a):
        return self.data

    def close(self):
        pass


#: What each site takes: exact keys, as the Worker validates them (an unknown key is a 400).
WINDOW_SITE = {"schema_version", "published_at", "run", "account", "performance", "compute", "gym", "agents", "structures", "trading",
               "positions", "practice", "levels", "rationale"}
OLD_SITE = WINDOW_SITE - {"levels", "rationale"}
TABLELESS_SITE = OLD_SITE - {"positions"}


class Site:
    """The Worker: refuses any checkpoint with a key it does not know (400 "Invalid checkpoint.")."""

    def __init__(self, keys):
        self.keys, self.posts, self.reply = set(keys), [], b'{"error":"Invalid checkpoint."}'

    def __call__(self, request, timeout=None):
        body = json.loads(request.data)
        self.posts.append((request.full_url.rsplit("/", 1)[1], body))
        if request.full_url.endswith("/checkpoint") and not set(body) <= self.keys:
            raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, _Body(self.reply))
        return Response(200, {"stored": len(body.get("events") or []), "replayed": 0})

    def checkpoints(self):
        return [body for path, body in self.posts if path == "checkpoint"]


class PublisherWindowTest(WorldCase):
    def setUp(self):
        super().setUp()
        self.ids = self.today()
        self.now = NOW
        self.ledger = Ledger(self.world.state / "ledger.sqlite", clock=lambda: self.now)
        self.house = SimpleNamespace(ledger=self.ledger, alerts=[], books={}, options_live=None, swarm=SimpleNamespace(root=self.world.swarm),
                                     registry=SimpleNamespace(living=lambda: [], dead=lambda: []),
                                     evaluator=SimpleNamespace(rung=lambda agent_id: 0))
        self.house.alert = lambda level, text, **kw: self.house.alerts.append((level, text))
        self.house.site_inputs = lambda: {**sitefeed.site_inputs(self.world.swarm),
                                          "practice": {"as_of": PUBLISHED_AT, "sessions": 1, "capital_usd": 10000.0,
                                                       "rows": [{"family": "iwm-crash-cluster-straddle", "lineage": "iwm-crash-cluster-straddle",
                                                                 "structure": "long_straddle", "tier": "train", "sessions": 1, "trades": 0,
                                                                 "wins": 0, "pnl_usd": 0.0, "return_on_risk": None, "last_day": "2026-09-30",
                                                                 "live": True}]}}

    def tearDown(self):
        self.ledger._db.close()
        super().tearDown()

    def publisher(self, site):
        return Publisher("https://blakewoods.us", lambda: "t" * 40, self.world.state / "publish.json", tape="test", opener=site,
                         clock=lambda: self.now, performance={"start_at": RESET_AT, "start_equity": "481.65"})

    def said(self):
        return [text for _, text in self.house.alerts if "swarm window" in text]

    def test_a_new_site_gets_the_window_with_the_pinned_agent_and_each_trades_reasons(self):
        site = Site(WINDOW_SITE)
        self.assertEqual(self.publisher(site).publish(self.house)["checkpoint"], 200)
        [body] = site.checkpoints()
        self.assertIn(GOOGL_ID, [a["id"] for a in body["agents"]], "pinned: its card has a name and a record")
        levels = {row["id"]: row["level"] for row in body["levels"]["agents"]}
        self.assertEqual((levels[GOOGL_ID], levels["iwm-crash-cluster-straddle"]), ("tuition", "practice"))
        theses = {row["id"]: row["thesis"] for row in body["rationale"]["agents"]}
        self.assertEqual(theses[GOOGL_ID], GOOGL)
        trade = next(t for t in body["rationale"]["trades"] if t["id"] == f"real:{self.ids['googl']}")
        self.assertEqual((trade["route"], trade["open_why"], trade["max_loss_usd"]), ("tuition", "msft leads googl, qqq flat", "157.00"))
        self.assertEqual({t["id"] for t in body["rationale"]["trades"]}, {r["id"] for r in body["positions"]["rows"]})
        self.assertEqual(self.said(), [])
        for value in publish_strings(body["rationale"]):
            if not re.match(r"^\d{4}-\d\d-\d\dT[\d:.]+Z$|^real:\d+$|^-?\d+\.\d\d$|^[a-z0-9-]{1,40}$", value):
                self.assertFalse(re.search(r"[0-9:()\[\]{}<>=_`#|\\]", value), value)

    def test_a_trades_reason_on_the_tape_is_filtered_against_the_traded_programs_parameters(self):
        """S3 of the post-fix verification (Oct 1, 2026): `agent.trade` `why` on the public tape."""
        w = self.world
        oid = w.live.rows("SELECT oid FROM orders WHERE pid=? AND action='open'", (self.ids["googl"],))[0]["oid"]
        reasons = ["lag thresh 3 sessions, z above 2 and qqq within 4 of flat", "lag thresh hit while qqq is flat",
                   "msft led for twenty sessions", "msft leads googl, qqq flat"]
        for n, reason in enumerate(reasons):
            self.ledger.append("book.fill", googl_fill(reason=reason, _order=oid, _price=1.57), agent=GOOGL_ID, at=PUBLISHED_AT,
                               id=f"fill-{n}")
        self.ledger.append("book.fill", googl_fill(reason="msft leads googl, qqq flat", _order=999), agent=GOOGL_ID, at=PUBLISHED_AT,
                           id="fill-unknown")
        self.ledger.append("book.fill", googl_fill(side="sell", reason="program", entry_reason="msft leads googl, qqq flat", realized=12.5,
                                                   _pid=self.ids["googl"]), agent=GOOGL_ID, at=PUBLISHED_AT, id="fill-close")
        site = Site(WINDOW_SITE)
        self.publisher(site).publish(self.house)
        trades = [e["payload"] for path, body in site.posts if path == "events" for e in body["events"] if e["kind"] == "agent.trade"]
        self.assertEqual([(t["action"], t["why"]) for t in trades],
                         [("open", ""), ("open", ""), ("open", ""), ("open", "msft leads googl, qqq flat"), ("open", ""),
                          ("close", "msft leads googl, qqq flat")])
        for t in trades:
            self.assertFalse(re.search(r"[0-9]|thresh|twenty", t["why"]), t)

    def test_an_older_site_gets_the_checkpoint_without_the_window_and_is_asked_again_later(self):
        site = Site(OLD_SITE)
        publisher = self.publisher(site)
        self.assertEqual(publisher.publish(self.house)["checkpoint"], 200)
        first, second = site.checkpoints()
        self.assertIn("levels", first)
        self.assertEqual(second, windowless(first), "the windowless checkpoint is tried first, and the rest is the same")
        self.assertEqual(len(self.said()), 1)
        self.assertIn("Invalid checkpoint.", self.said()[0], "the site's own reply")
        self.now += 60
        publisher.publish(self.house)
        self.assertEqual(len(site.checkpoints()), 3, "inside the half hour: one post, without the window")
        self.assertNotIn("levels", site.checkpoints()[-1])
        self.now += publish.WINDOW_RETRY_SECONDS
        publisher.publish(self.house)
        self.assertEqual(len(site.checkpoints()), 5, "offered again after half an hour, and refused again")
        self.assertEqual(len(self.said()), 1, "the same reason, once")
        site.keys = WINDOW_SITE
        self.now += publish.WINDOW_RETRY_SECONDS
        publisher.publish(self.house)
        self.assertIn("levels", site.checkpoints()[-1])
        self.now += 60
        publisher.publish(self.house)
        self.assertIn("rationale", site.checkpoints()[-1], "taken: offered every publish again")

    def test_the_window_is_not_read_while_the_site_refuses_it(self):
        site = Site(OLD_SITE)
        publisher = self.publisher(site)
        reads = []
        real = site_window.site_window
        with unittest.mock.patch.object(site_window, "site_window", lambda *a, **k: reads.append(1) or real(*a, **k)):
            publisher.publish(self.house)
            self.now += 60
            publisher.publish(self.house)
            self.assertEqual(len(reads), 1, "refused: not read again inside the half hour")
            self.now += publish.WINDOW_RETRY_SECONDS
            publisher.publish(self.house)
            self.assertEqual(len(reads), 2, "offered again after half an hour")

    def test_a_site_before_the_table_too_converges_and_only_what_it_took_is_marked_refused(self):
        site = Site(TABLELESS_SITE)
        publisher = self.publisher(site)
        publisher.publish(self.house)
        posts = site.checkpoints()
        self.assertEqual([("levels" in b, "positions" in b) for b in posts], [(True, True), (False, True), (False, False)],
                         "the window first, then the ladder without it")
        self.assertEqual(self.said(), [], "the windowless table was refused too: the window is not marked")
        self.now += 60
        publisher.publish(self.house)
        posts = site.checkpoints()[3:]
        self.assertEqual([("levels" in b, "positions" in b) for b in posts], [(True, False), (False, False)])
        self.assertEqual(posts[0]["rationale"]["trades"], [], "no table: the window names no trade")
        self.assertEqual(len(self.said()), 1)
        self.now += 60
        publisher.publish(self.house)
        self.assertEqual([("levels" in b, "positions" in b) for b in site.checkpoints()[5:]], [(False, False)])


# ------------------------------------------------------------------------------------------- the fixture
def accepts(bodies):
    """The site's own `validCheckpoint` over each body, in node: the copy in fixtures/site_schema.js, or the schema at
    `LTCM_SITE_SCHEMA` (a site branch's `capital/schema.js`, before its copy is refreshed here)."""
    import subprocess

    schema = Path(os.environ.get("LTCM_SITE_SCHEMA") or SITE_SCHEMA)
    node = shutil.which("node")
    if node is None:
        if os.environ.get("CI"):
            raise AssertionError("node is required in CI to run the site's schema")
        raise unittest.SkipTest("node is not installed")
    script = (f"import {{ validCheckpoint }} from {json.dumps(schema.resolve().as_uri())};"
              "let text = ''; process.stdin.on('data', chunk => { text += chunk; });"
              "process.stdin.on('end', () => console.log(JSON.stringify(JSON.parse(text).map(body => validCheckpoint(body)))));")
    done = subprocess.run([node, "--input-type=module", "-e", script], input=json.dumps(bodies), capture_output=True, text=True, timeout=120)
    if done.returncode:
        raise AssertionError(done.stderr[-2000:])
    return json.loads(done.stdout), "validLevels" in schema.read_text(encoding="utf-8")


def window_checkpoint():
    """`site_checkpoint_window.json`: the fixture's checkpoint (`test_publish.FIXTURE_INPUTS`) with the swarm window, after
    hours (the open GOOGL vertical unpriced, so Profit is unknown): Mullins 166's GOOGL vertical on D2 tuition, its agent
    retired since and pinned to the roster; an incubator round trip its agent closed; the House's calibration; and the
    levels and the funnel. The window's raw inputs come through the House's own producers (`site_window.trades`,
    `public.thesis_text`)."""
    from league.tests.test_publish import FIXTURE_ACCOUNT, FIXTURE_BOOK, FIXTURE_INPUTS, FIXTURE_PRACTICE, agent, position
    from league.tests.test_publish import PUBLISHED_AT as AT

    private = {14: ("the condor fits the quiet tape", None, "sized", None, "184.00", "condor-vrp-3@9:r"),
               13: ("range broke up early", None, "probe", None, "96.00", "orb-4@4:r"),
               12: ("range broke up", "the break failed by noon", "probe", "agent", "96.00", "orb-4@4:r"),
               11: ("gap down held", None, "probe", "house", "61.00", "putspread-dip-2@3:r"),
               10: (None, None, "calibration", "house", "40.00", "house:calibration@1:c"),
               9: ("three red days", None, None, "expiry", "66.00", "reversal-1@2:r")}
    rows = []
    for row in FIXTURE_BOOK["rows"]:
        tag, close, route, exit_kind, loss, inst = private[row["pid"]]
        rows.append({**row, "_tag": tag, "_close_why": close, "_route": route, "_exit": exit_kind, "_max_loss": loss, "_instance": inst})
    rows.insert(0, position(15, GOOGL_ID, underlying="GOOGL", right="call", quantity=1, open_quantity=1, status="open", expiry="2026-10-07",
                            opened_at="2026-09-28T13:31:00.000Z", closed_at=None, pnl_usd=None, _tag="msft leads googl, qqq flat",
                            _close_why=None, _route="tuition", _exit=None, _max_loss="157.00", _instance=f"{GOOGL_ID}@27:t"))
    rows.append(position(16, "gap-drift", source="incubator", structure="long_call", legs=1, opened_at="2026-09-28T13:45:00.000Z",
                         closed_at="2026-09-28T14:20:00.000Z", pnl_usd="4.10", _tag="the gap was not confirmed", _close_why="filled the gap",
                         _route="incubator", _exit="agent", _max_loss="38.00", _instance="gap-drift@6:i"))
    book = {**FIXTURE_BOOK, "pnl_usd": None, "rows": rows}
    trading, positions = trading_profit.complete(book, FIXTURE_ACCOUNT, at=AT)
    googl = agent(GOOGL_ID, band="retired", structure="debit_vertical", mechanism=GOOGL, born_at="2026-09-27T02:10:00.000Z",
                  retired_at="2026-09-27T20:05:00.000Z", trials=3120, revisions=27, pinned=True)
    agents = [*FIXTURE_INPUTS.agents, googl]
    names = {a["id"]: ((), True) for a in agents}
    levels_now = {"condor-vrp-3": "sized", "putspread-dip-2": "probe", "orb-4": "probe", "ironfly-quiet": "candidate",
                  "butterfly-pin": "candidate", "trend-vertical": "candidate", "gap-drift": "incubator", "skew-revert": "validation",
                  "calendar-term": "practice", "strangle-cheap": "train", "eod-drift": "train", "reversal-1": "retired", GOOGL_ID: "tuition"}
    levels = {"as_of": "2026-09-28T14:57:00.000Z", "agents": [{"id": a["id"], "level": levels_now[a["id"]]} for a in agents],
              "funnel": {"since": RESET_AT, "born": 48, "practice": 4, "validation": 9, "tuition": 2, "incubator": 1, "looks": 6,
                         "looks_passed": 3, "candidate": 6, "probe": 3, "sized": 1, "retired": 37, "calibration": 1, "live_test": 0}}
    rationale = {"as_of": "2026-09-28T14:57:00.000Z",
                 "agents": [{"id": a["id"], "thesis": public.thesis_text(a["mechanism"])} for a in agents],
                 "trades": site_window.trades(positions["rows"], names, {row["_instance"]: () for row in rows})}
    inputs = SiteInputs(**{**FIXTURE_INPUTS.__dict__, "agents": agents, "trading": trading, "positions": positions,
                           "practice": FIXTURE_PRACTICE, "levels": levels, "rationale": rationale})
    return build_checkpoint(inputs, AT)


class WindowFixtureTest(unittest.TestCase):
    def test_the_window_fixture_is_this_modules_own_output(self):
        """LTCM_WRITE_SITE_FIXTURES=1 rewrites it from here; the site's contract test publishes and draws it."""
        body = window_checkpoint()
        self.assertEqual(set(body) - set(windowless(body)), {"levels", "rationale"})
        retired = [a["id"] for a in body["agents"] if a["band"] == "retired"]
        self.assertEqual(retired, [GOOGL_ID, "reversal-1"], "the pinned agent first")
        levels = {row["id"]: row["level"] for row in body["levels"]["agents"]}
        self.assertEqual((levels[GOOGL_ID], levels["gap-drift"], levels["reversal-1"]), ("tuition", "incubator", "retired"))
        theses = {row["id"]: row["thesis"] for row in body["rationale"]["agents"]}
        self.assertEqual(theses[GOOGL_ID], GOOGL)
        self.assertIsNone(theses["reversal-1"], "its mechanism names three down days: no thesis")
        trades = {row["id"]: row for row in body["rationale"]["trades"]}
        self.assertEqual(list(trades), [row["id"] for row in body["positions"]["rows"]], "one per row, in the table's order")
        self.assertEqual(trades["real:15"], {"id": "real:15", "route": "tuition", "open_why": "msft leads googl, qqq flat", "close_why": None,
                                             "exit": None, "max_loss_usd": "157.00"})
        self.assertEqual(trades["real:16"], {"id": "real:16", "route": "incubator", "open_why": "the gap was not confirmed",
                                             "close_why": "filled the gap", "exit": "agent", "max_loss_usd": "38.00"})
        self.assertEqual(trades["real:10"], {"id": "real:10", "route": "calibration", "open_why": None, "close_why": None, "exit": "house",
                                             "max_loss_usd": "40.00"})
        self.assertIsNone(trades["real:11"]["close_why"], "a House exit carries no reason")
        funnel = body["levels"]["funnel"]
        self.assertGreater(funnel["candidate"], funnel["tuition"], "Tuition is a branch of its own: the site must take this")
        self.assertIsNone(body["trading"]["pnl_usd"], "after hours: the open vertical is unpriced")
        path = FIXTURES / "site_checkpoint_window.json"
        if os.environ.get("LTCM_WRITE_SITE_FIXTURES"):
            path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), body)
        self.assertEqual(publish.site_levels(body["levels"], body["agents"], body["published_at"]), body["levels"], "the allowlist is a fixed point")
        self.assertEqual(publish.site_rationale(body["rationale"], body["agents"], body["positions"], body["published_at"]), body["rationale"])

    def test_the_site_takes_the_window_and_an_older_site_the_checkpoint_without_it(self):
        fixture = json.loads((FIXTURES / "site_checkpoint_window.json").read_text(encoding="utf-8"))
        bad = [
            {**fixture, "levels": {**fixture["levels"], "agents": [{"id": "condor-vrp-3", "level": "tuition"}]}},
            {**fixture, "rationale": {**fixture["rationale"], "agents": [{"id": "orb-4", "thesis": "Sells the 30 delta put."}]}},
            {**fixture, "rationale": {**fixture["rationale"], "trades": [{**fixture["rationale"]["trades"][0], "id": "real:999"}]}},
            {**fixture, "levels": {**fixture["levels"], "funnel": {**fixture["levels"]["funnel"], "sized": 99}}},
        ]
        verdicts, knows_window = accepts([fixture, windowless(fixture), *bad])
        if knows_window:
            self.assertEqual(verdicts, [True, True, False, False, False, False], "the window, the windowless body, and each broken rule")
        else:
            self.assertEqual(verdicts[:2], [False, True], "an older site refuses the window and takes the rest, pinned agent and all")


def publish_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from publish_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from publish_strings(item)


if __name__ == "__main__":
    unittest.main()
