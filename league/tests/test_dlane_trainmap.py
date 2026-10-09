"""THE TRAIN MAP of the direction lane (Oct 9, 2026; league/swarm/dlane.py `train_map`, `train_map_text`,
`train_map_brief`; the file league/swarm/dlane_map.json): which call shapes pass direction-v2 on the Train years in the
operator's census, shown to the architect (its LANES block) and to direction researchers (their brief) so births aim at
shapes that pass. The screen (D2) still decides, unchanged.

- THE SWITCH: shown only while the lane is on and `dlane.train_map` is true (policy.json true, the code's default off,
  swarm.json false hides it at once); off, every text is main d70e00c3's byte for byte (golden digests computed on that
  commit with the same fixtures).
- THE READER: cached, never raises; a missing, malformed or unsafe file (a hidden year, a dollar sign, a figure, a wrong
  label or objective, one bad row) reads as no map.
- WHAT AGENTS SEE: the label "in-sample: Train years 2022-24 ...; the screen decides", shapes with S_D to one decimal and
  the unit's verdict as a word; no digit run that looks like a dollar amount or a price, no year but 2022-24, no
  provenance hash; bounded in length.
- THE ALPHA LANE: untouched (an alpha family's brief, the architect's request with the lane off: main's digests).
- THE WALL: the file is protected like dlane.py (ci.FORBIDDEN and the gateway's list).

The fixtures' families and figures are invented; the committed map's figures are the operator's Train-year census.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league import ci
from league.swarm import dlane
from league.swarm import settings as S
from league.swarm.architect import Architect
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock

POLICY = json.loads((Path(ci.REPO) / "league" / "swarm" / "policy.json").read_text(encoding="utf-8"))
COMMITTED = {"dlane": copy.deepcopy(POLICY["dlane"])}
#: The committed lane with the map switched off (what swarm.json `dlane.train_map` false reads).
MAP_OFF = {"dlane": {**copy.deepcopy(POLICY["dlane"]), "train_map": False}}
ROOT_SETS = (["SPY"], ["QQQ"], ["IWM"], ["SPY", "QQQ"], ["SPY", "QQQ", "IWM"], None)
#: Figures that must never reach an agent and that the repo already states elsewhere: the account's equity and unit cap
#: (docs/operations.md) and `TRAIN_CLOSE_2024`'s levels.
PUBLIC_FIGURES = ("1,288", "1288", "128.8", "540.9", "464.4", "211.0", "541", "464", "211")
#: The operator's private figures (the census's private notes) are never committed, not even here as a test fixture:
#: they live in an operator-local file outside the repo that the environment variable `LTCM_PRIVATE_FIGURES` names (one
#: figure per line, "#" starts a comment). When it is set they join `leaks` and `PrivateFigures` checks them; when it is
#: not, that test is skipped and the generic checks below (no price-like decimal, no dollar sign) still refuse them.
PRIVATE_ENV = "LTCM_PRIVATE_FIGURES"


def private_figures_file() -> Path | None:
    """The operator-local private figures file, or None when `LTCM_PRIVATE_FIGURES` is unset or names no file."""
    name = os.environ.get(PRIVATE_ENV, "").strip()
    return Path(name) if name and Path(name).is_file() else None


def private_figures() -> tuple[str, ...]:
    """The figures in the operator-local file (none without it)."""
    path = private_figures_file()
    if path is None:
        return ()
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(f for f in (line.split("#", 1)[0].strip() for line in lines) if f)


PRIVATE = PUBLIC_FIGURES + private_figures()

# ---------------------------------------------------------------------------------------- the secrecy checks (tests')
#: Any year an agent may not read, anywhere, even inside a longer digit run.
HIDDEN = ("2017", "2018", "2019", "2020", "2021", "2025", "2026")
DIGITS4 = re.compile(r"(?<![\d])\d{4,}(?![\d])")
#: Looks like money or a price: a dollar sign; a grouped number; a decimal with two places that is 1 or more; any
#: decimal of 10 or more; a decimal with three or more places.
MONEY = (re.compile(r"\$"), re.compile(r"\d{1,3}(?:,\d{3})+"), re.compile(r"(?<![\d.])[1-9]\d*\.\d{2}(?!\d)"),
         re.compile(r"(?<![\d.])\d{2,}\.\d+"), re.compile(r"\d\.\d{3,}"))
#: The decimals a map text may carry: a delta target (0.20) or a one-decimal figure (S_D 0.4, 1.5x).
DECIMAL = re.compile(r"(?<![\d.])\d+\.\d+")
DECIMAL_OK = re.compile(r"0\.[1-9]0|\d\.\d")


def leaks(text: str) -> list[str]:
    """Every way `text` breaks the map's secrecy rules, by the tests' own reading."""
    out = [f"names {y}" for y in HIDDEN if y in text]
    out += [f"year or number {m}" for m in DIGITS4.findall(text) if m not in ("2022", "2023", "2024")]
    out += [f"money-like {m.group()}" for rx in MONEY for m in rx.finditer(text)]
    out += [f"decimal {m}" for m in DECIMAL.findall(text) if not DECIMAL_OK.fullmatch(m)]
    out += [f"private {f}" for f in PRIVATE if re.search(rf"(?<![\d.,]){re.escape(f)}(?![\d])", text)]
    return out


def committed_map_file() -> dict:
    return json.loads(dlane.MAP_PATH.read_text(encoding="utf-8"))


class MapFile:
    """A context: `dlane.MAP_PATH` pointed at a temporary file holding `doc` (or raw `text`, or nothing at all)."""

    def __init__(self, doc=None, *, text: str | None = None, missing: bool = False):
        self.doc, self.text, self.missing = doc, text, missing

    def __enter__(self) -> Path:
        self.dir = tempfile.TemporaryDirectory()
        path = Path(self.dir.name) / "dlane_map.json"
        if not self.missing:
            path.write_text(self.text if self.text is not None else json.dumps(self.doc), encoding="utf-8")
        self.patch = mock.patch.object(dlane, "MAP_PATH", path)
        self.patch.start()
        return path

    def __exit__(self, *exc):
        self.patch.stop()
        self.dir.cleanup()
        return False


# ------------------------------------------------------------------------------------------------ 1. the switch
class Switch(unittest.TestCase):
    def test_the_code_default_is_off_the_policy_turns_it_on_and_swarm_json_false_turns_it_off(self):
        self.assertIs(dlane.DEFAULTS["train_map"], False)
        self.assertIs(dlane.cfg(None)["train_map"], False)
        self.assertIs(dlane.cfg({"dlane": {"mode": "gate"}})["train_map"], False, "a dropped policy layer shows nothing")
        self.assertIs(POLICY["dlane"]["train_map"], True)
        self.assertTrue(dlane.map_on(COMMITTED))
        self.assertFalse(dlane.map_on(MAP_OFF))
        merged = S._merge(copy.deepcopy(POLICY), {"dlane": {"train_map": False}})  # swarm.json over policy.json
        self.assertFalse(dlane.map_on(merged))
        self.assertEqual(merged["dlane"]["mode"], "gate", "the rest of the policy's lane stays")
        for bad in ("true", 1, "yes", None, [True], {"on": True}):
            self.assertIs(dlane.cfg({"dlane": {"mode": "gate", "train_map": bad}})["train_map"], False, repr(bad))

    def test_nothing_is_shown_while_the_lane_is_off_or_the_switch_is_off(self):
        for settings in (MAP_OFF, {"dlane": {**COMMITTED["dlane"], "mode": "off"}}, {"dlane": {"mode": "gate"}}, None):
            self.assertEqual(dlane.train_map_text(settings), "")
            self.assertEqual(dlane.train_map_brief(settings, ["SPY"]), "")
        self.assertFalse(dlane.map_on({"dlane": {"mode": "off", "train_map": True}}), "the lane's rollback wins")
        self.assertEqual(dlane.brief_text({"dlane": {"mode": "off", "train_map": True}}), "")
        self.assertEqual(dlane.lanes_text({"dlane": {"mode": "off", "train_map": True}}), "")

    def test_the_switch_off_is_the_brief_without_the_map_byte_for_byte(self):
        for roots in ROOT_SETS:
            on, off = dlane.brief_text(COMMITTED, roots), dlane.brief_text(MAP_OFF, roots)
            self.assertNotIn("TRAIN MAP", off)
            self.assertTrue(on.startswith(off + "\nTRAIN MAP (" + dlane.MAP_LABEL + ")."), roots)
            with MapFile(missing=True):
                self.assertEqual(dlane.brief_text(COMMITTED, roots), off, "no file: no map")
        self.assertEqual(dlane.lanes_text(COMMITTED), dlane.lanes_text(MAP_OFF), "the lane's rules do not move")

    def test_a_changed_bar_setting_is_said(self):
        self.assertNotIn("have changed since the map was built", dlane.train_map_text(COMMITTED))
        moved = {"dlane": {**COMMITTED["dlane"], "min_entry_days": 80}}
        self.assertIn("The bar's settings have changed since the map was built (min_entry_days): read it as a guide.",
                      dlane.train_map_text(moved))


# ------------------------------------------------------------------------------------------------ 2. the reader
class Reader(unittest.TestCase):
    def test_the_committed_map_reads_and_is_the_operators_census_reduced(self):
        raw = committed_map_file()
        self.assertEqual(raw["label"], dlane.MAP_LABEL)
        self.assertEqual(raw["label"], "in-sample: Train years 2022-24, from the operator's census at one-lot natural "
                                       "prices; the screen decides")
        self.assertEqual((raw["schema"], raw["objective"]), (dlane.MAP_SCHEMA, dlane.OBJECTIVE))
        for key in ("built_at", "inputs_sha256", "source_sha256"):
            self.assertTrue(raw.get(key), key)
        self.assertRegex(raw["inputs_sha256"], r"^[0-9a-f]{64}$")
        doc = dlane.train_map()
        self.assertIsNotNone(doc)
        self.assertEqual(len(doc["passing"]), 30)
        self.assertEqual([r["S_D"] for r in doc["passing"]], sorted((r["S_D"] for r in doc["passing"]), reverse=True))
        self.assertEqual({r["delta"] for r in doc["passing"]}, {0.2}, "every passer is a 0.20-delta call")
        self.assertEqual({r["in_market_years"] for r in doc["passing"]}, {3})
        self.assertNotIn("IWM", {r["root"] for r in doc["passing"]}, "IWM alone has no passer")
        self.assertEqual(len(doc["lessons"]), 3)
        self.assertEqual(sum(r["unit"] == "borderline" for r in doc["passing"]), 23)
        # Nothing but the agent-safe fields: no per-year figure, no unit figure, no price.
        allowed = {"schema", "label", "built_at", "inputs_sha256", "inputs", "source_sha256", "objective", "scored_with",
                   "bar", "how", "words", "passing", "lessons"}
        self.assertEqual(set(raw) - allowed, set())
        for row in raw["passing"]:
            self.assertEqual(set(row), {"root", "delta", "expiry", "hold", "entry", "gate", "S_D", "unit",
                                        "in_market_years"})
            self.assertEqual(row["S_D"], round(row["S_D"], 1))
            self.assertIn(row["unit"], ("yes", "borderline", "no"))
        # The committed bar is the policy's: the map was scored under the settings it is shown with.
        c = dlane.cfg(COMMITTED)
        for key, value in raw["bar"].items():
            self.assertEqual(c[key], value, key)

    def test_the_lessons_claims_agree_with_the_committed_rows(self):
        """Every claim a lesson makes about the passers is checked against the file's own rows (the review of Oct 9:
        LESSON 2 said every passer enters every session or under ONE volatility filter while 4 rows stack both). A lesson
        reworded so a claim below no longer matches fails here, so the claim is checked again before it ships."""
        raw = committed_map_file()
        rows, lessons = raw["passing"], raw["lessons"]
        n = len(rows)
        joined = " ".join(lessons)
        gates = [r["gate"] for r in rows]

        def claim(pattern: str) -> tuple[int, ...]:
            m = re.search(pattern, joined)
            self.assertIsNotNone(m, pattern)
            return tuple(int(g) for g in m.groups())

        # Every count of all the passers is the row count; "one filter" is never said of all of them.
        for m in re.finditer(r"\b[Aa]ll (\d+) passers\b|\bfor all (\d+)\b|\bof the (\d+) passers\b", joined):
            self.assertEqual(int(next(g for g in m.groups() if g)), n, m.group())
        self.assertNotRegex(joined, r"(?i)(?:every|all \d+) passers?[^.]*\bor under one\b")
        # LESSON 1.
        self.assertIn("Every passing cell is a 0.20-delta call held 2, 3 or 5 sessions on an expiry of at most 10 days "
                      "(nearest covering, 2-5 or 6-10 DTE)", joined)
        self.assertEqual({r["delta"] for r in rows}, {0.2})
        self.assertLessEqual({r["hold"] for r in rows}, {2, 3, 5})
        self.assertLessEqual({r["expiry"] for r in rows}, {"nearest", "2-5", "6-10"})
        self.assertIn("no 8-session hold passes", joined)
        (border, of) = claim(r"(\d+) of the (\d+) passers fit only borderline")
        self.assertEqual((border, of), (sum(r["unit"] == "borderline" for r in rows), n))
        # LESSON 2: in the market every Train year, and how they enter.
        (all_n,) = claim(r"All (\d+) passers are in the market in all three Train years")
        self.assertEqual(all_n, n)
        self.assertTrue(all(r["in_market_years"] == 3 for r in rows))
        every, one, both = claim(r"(\d+) enter every session, (\d+) under one volatility filter \([^)]*\) and (\d+) "
                                 r"under both")
        self.assertEqual(every, gates.count("every"))
        self.assertEqual(one, sum(g in ("ivlow", "contango") for g in gates))
        self.assertEqual(both, gates.count("ivlow+contango"))
        self.assertEqual(every + one + both, n, "every passer's gate is one of the three")
        stacked = [r for r in rows if r["gate"] == "ivlow+contango"]
        (passing_stacked, hold) = claim(r"Stacking both volatility filters [^;]*; (\d+) pass, all (\d+)-session holds "
                                        r"entered at 15:30")
        self.assertEqual(passing_stacked, len(stacked))
        self.assertTrue(stacked, "the stacked gate has passers, as the census says")
        self.assertEqual({(r["hold"], r["entry"]) for r in stacked}, {(hold, "15:30")})
        self.assertIn("price-trend gate", joined)
        self.assertFalse(any("trend" in g for g in gates), "the price-trend gate passes none")
        # LESSON 3.
        self.assertIn("IWM calls lose at 1.5x", joined)
        self.assertNotIn("IWM", {r["root"] for r in rows}, "IWM alone: none pass")
        (two,) = claim(r"2-session holds [^;]*\(R3\), so only (\d+) pass")
        self.assertEqual(two, sum(r["hold"] == 2 for r in rows))

    def test_every_text_field_of_the_committed_file_is_agent_safe(self):
        raw = committed_map_file()
        texts = [raw["label"], raw["how"], *raw["lessons"], *raw["words"]["expiry"].values(),
                 *raw["words"]["gate"].values()]
        for text in texts:
            self.assertEqual(dlane.map_text_problems(text), [], text)
            self.assertEqual(leaks(text), [], text)

    def test_the_text_rule_reads_counts_and_refuses_figures(self):
        ok = ("765 of 784 cells (P1)", "0.20-delta, 0.40 or 0.50-delta", "1.5x the half-spread", "Train years 2022-24",
              "10-day above 3-day implied vol", "15:30 ET", "t below -1", "40+ trades on 20+ days", "S_D 0.8")
        for text in ok:
            self.assertEqual(dlane.map_text_problems(text), [], text)
        bad = ("$45", "near 540", "540.9", "1.37 times", "1,288", "12880", "0.77", "2025", "x20261", "12.5",
               "in 2021", "caf\u00e9", "a\nb", "", "  ", None, 7)
        for text in bad:
            self.assertNotEqual(dlane.map_text_problems(text), [], repr(text))

    def test_missing_unreadable_or_garbage_reads_as_no_map_and_never_raises(self):
        for kw in ({"missing": True}, {"text": ""}, {"text": "{not json"}, {"text": "[]"}, {"text": "null"},
                   {"text": "\x00\xff"}, {"doc": {"schema": 1}}):
            with MapFile(**kw):
                self.assertIsNone(dlane.train_map(), kw)
                self.assertEqual(dlane.train_map_text(COMMITTED), "")
                self.assertEqual(dlane.brief_text(COMMITTED, ["SPY"]), dlane.brief_text(MAP_OFF, ["SPY"]))
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(dlane.train_map(d), "a directory")
            self.assertIsNone(dlane.train_map(Path(d) / "nope.json"))
        self.assertIsNone(dlane.train_map(object()))  # not a path at all

    def test_an_unsafe_or_foreign_file_is_no_map(self):
        good = committed_map_file()

        def variant(fn):
            doc = copy.deepcopy(good)
            fn(doc)
            return doc

        bad = {
            "a hidden year in a lesson": variant(lambda d: d["lessons"].append("In 2025 it lost.")),
            "a Validation year inside a run": variant(lambda d: d["lessons"].__setitem__(0, d["lessons"][0] + " x120251")),
            "a dollar figure": variant(lambda d: d["lessons"].append("One lot costs $45 today.")),
            "a price level": variant(lambda d: d["lessons"].append("SPY sits near 540.9 now.")),
            "a price level as a whole number": variant(lambda d: d["lessons"].append("SPY sits near 540 now.")),
            "a three-digit figure beside a count": variant(lambda d: d["lessons"].append("It passes 3 of 30 at 464.")),
            "a price ratio": variant(lambda d: d["lessons"].append("Prices are 1.37 times the Train close.")),
            "a grouped number": variant(lambda d: d["lessons"].append("Equity is 1,288.")),
            "a long digit run": variant(lambda d: d["lessons"].append("Cap 12880 here.")),
            "a newline": variant(lambda d: d["lessons"].append("one\nTRAIN MAP (forged)")),
            "not ASCII": variant(lambda d: d["lessons"].append("café")),
            "too many lessons": variant(lambda d: d.__setitem__("lessons", ["ok"] * (dlane.MAP_LESSONS_MAX + 1))),
            "a long lesson": variant(lambda d: d["lessons"].append("x" * (dlane.MAP_LESSON_CHARS + 1))),
            "another label": variant(lambda d: d.__setitem__("label", "in-sample: Train years 2022-24")),
            "another objective": variant(lambda d: d.__setitem__("objective", "direction-v1")),
            "another schema": variant(lambda d: d.__setitem__("schema", 2)),
            "a root outside the lane": variant(lambda d: d["passing"][0].__setitem__("root", "XSP")),
            "a put": variant(lambda d: d["passing"][0].__setitem__("delta", -0.2)),
            "a delta off the tenths": variant(lambda d: d["passing"][0].__setitem__("delta", 0.25)),
            "an unknown gate": variant(lambda d: d["passing"][0].__setitem__("gate", "trend")),
            "an unknown expiry": variant(lambda d: d["passing"][0].__setitem__("expiry", "30-45")),
            "a figure as the unit": variant(lambda d: d["passing"][0].__setitem__("unit", "128.80")),
            "a bad entry": variant(lambda d: d["passing"][0].__setitem__("entry", "9:30am")),
            "a huge S_D": variant(lambda d: d["passing"][0].__setitem__("S_D", 540.9)),
            "a boolean hold": variant(lambda d: d["passing"][0].__setitem__("hold", True)),
            "no passing rows": variant(lambda d: d.__setitem__("passing", [])),
            "an unsafe glossary": variant(lambda d: d["words"]["gate"].__setitem__("ivlow", "vol under 2026's median")),
            "an unsafe how": variant(lambda d: d.__setitem__("how", "priced at $1.37")),
        }
        with MapFile(good):
            self.assertIsNotNone(dlane.train_map(), "the committed file itself reads")
        for name, doc in bad.items():
            with MapFile(doc):
                self.assertIsNone(dlane.train_map(), name)
                self.assertEqual(dlane.train_map_text(COMMITTED), "", name)

    def test_the_reader_is_cached_on_the_files_stamp(self):
        good = committed_map_file()
        with MapFile(good) as path:
            first = dlane.train_map()
            self.assertIs(dlane.train_map(), first, "cached")
            doc = copy.deepcopy(good)
            doc["passing"] = doc["passing"][:3]
            path.write_text(json.dumps(doc), encoding="utf-8")
            os.utime(path, ns=(1, 1))
            self.assertEqual(len(dlane.train_map()["passing"]), 3, "a changed file is read again")


# ------------------------------------------------------------------------------------------------ 3. what agents see
class WhatAgentsSee(unittest.TestCase):
    def texts(self) -> dict[str, str]:
        """The map's texts as agents read them (the brief's own words before the map are D-1's, tested there)."""
        out = {"architect": dlane.train_map_text(COMMITTED)}
        for roots in ROOT_SETS:
            out[f"brief {roots}"] = dlane.train_map_brief(COMMITTED, roots)
            full, base = dlane.brief_text(COMMITTED, roots), dlane.brief_text(MAP_OFF, roots)
            self.assertTrue(full.startswith(base + "\n"))
            out[f"full brief {roots}"] = full[len(base) + 1:]
        return out

    def test_no_dollar_amount_price_ratio_or_year_but_the_train_years(self):
        raw = committed_map_file()
        for name, text in self.texts().items():
            self.assertTrue(text, name)
            self.assertEqual(leaks(text), [], name)
            self.assertEqual(dlane.map_text_problems(text.replace("\n", " ")), [], name)
            for provenance in (raw["inputs_sha256"], raw["source_sha256"], raw["built_at"], raw["scored_with"]["commit"],
                               raw["inputs_sha256"][:8], "receipt", "fp_"):
                self.assertNotIn(provenance, text, (name, provenance))
            self.assertIsNone(re.search(r"(?<![\d.$,])20(?:20|21|25|26)(?![\d])", text), name)  # the lane's LEAK
        for figure in ("0.1037", "10.37", "12.39", "0.1239", "1.41", "c36059"):  # D-1b's figures stay out too
            self.assertNotIn(figure, self.texts()["architect"])

    def test_each_text_carries_the_label_the_note_and_the_screen_decides(self):
        for name, text in self.texts().items():
            self.assertIn(f"TRAIN MAP ({dlane.MAP_LABEL}).", text, name)
            self.assertIn("An always-in call program can pass this bar", text, name)
            self.assertIn("the screen decides, not this map", text, name)
            self.assertIn("fits the unit at today's prices: ", text, name)

    def test_the_unit_is_a_word_and_s_d_one_decimal(self):
        text = dlane.train_map_text(COMMITTED)
        units = re.findall(r"fits the unit at today's prices: (\w+)", text)
        self.assertEqual(len(units), 30)
        self.assertEqual(set(units), {"yes", "borderline"})
        self.assertEqual(len(re.findall(r"S_D \d\.\d;", text)), 30)
        self.assertNotRegex(text, r"S_D \d\.\d\d")

    def test_the_architects_text_is_bounded_and_lists_every_passing_shape_once(self):
        text = dlane.train_map_text(COMMITTED)
        shapes = [line for line in text.splitlines() if line.startswith("- ")]
        self.assertEqual(len(shapes), 30)
        self.assertEqual(len(set(shapes)), 30)
        self.assertLessEqual(len(text.splitlines()), 40)
        self.assertLessEqual(len(text), 8000)
        self.assertEqual(shapes[0], "- QQQ 0.20-delta call, expiry 2-5, hold 3, enter 15:30 ET, gate ivlow: S_D 0.5; fits "
                                    "the unit at today's prices: borderline")
        for n in (1, 2, 3):
            self.assertIn(f"LESSON {n}: ", text)
        self.assertIn("AIM direction cards at these shapes and vary the gate, the hold or the root", text)
        # A longer map shows at most MAP_ARCHITECT_ROWS shapes and says so.
        doc = committed_map_file()
        doc["passing"] = (doc["passing"] * 2)[:45]
        with MapFile(doc):
            long = dlane.train_map_text(COMMITTED)
        self.assertEqual(sum(line.startswith("- ") for line in long.splitlines()), dlane.MAP_ARCHITECT_ROWS)
        self.assertIn("THE 45 PASSING SHAPES (best S_D first; the first 30 shown):", long)

    def test_the_brief_shows_the_five_best_on_the_familys_roots_then_other_roots(self):
        for roots in ROOT_SETS:
            text = dlane.train_map_brief(COMMITTED, roots)
            shapes = [line for line in text.splitlines() if line.startswith("- ")]
            self.assertEqual(len(shapes), dlane.MAP_BRIEF_ROWS, roots)
            self.assertLessEqual(len(text), 4000, roots)
            self.assertEqual(sum(line.startswith("LESSON ") for line in text.splitlines()), 3)
        spy = dlane.train_map_brief(COMMITTED, ["SPY"])
        self.assertIn("THE 5 BEST-SCORING PASSING SHAPES on your roots (SPY):", spy)
        self.assertTrue(all(line.startswith("- SPY 0.20-delta") for line in spy.splitlines() if line.startswith("- ")))
        self.assertIn("- SPY 0.20-delta call, expiry 6-10, hold 2, enter 10:30 ET, gate every session: S_D 0.5", spy)
        iwm = dlane.train_map_brief(COMMITTED, ["IWM"])
        self.assertIn("THE BEST-SCORING PASSING SHAPES: 0 on your roots (IWM), then 5 on other roots:", iwm)
        self.assertEqual(sum(line.startswith("- (other roots) ") for line in iwm.splitlines()), 5)
        both = dlane.train_map_brief(COMMITTED, ["SPY", "QQQ"])
        self.assertNotIn("SPY+QQQ+IWM 0.20", both, "a shape on a root the family does not hold is not its own")
        everything = dlane.train_map_brief(COMMITTED, ["SPY", "QQQ", "IWM"])
        self.assertIn("- SPY+QQQ+IWM 0.20-delta call, expiry 2-5, hold 3, enter 15:30 ET", everything)


# ------------------------------------------------------------------------------------------------ 4. the architect
class ArchitectBlock(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.clock = Clock()
        self.store = SwarmStore(Path(d.name), clock=self.clock)
        self.addCleanup(self.store.close)

    def arch(self, dlane_block: dict | None) -> Architect:
        settings = copy.deepcopy(S.DEFAULTS)
        settings["population"].update(start=4, ceiling=40, floor=0)
        if dlane_block is not None:
            settings["dlane"] = copy.deepcopy(dlane_block)
        return Architect(self.store, None, settings, clock=self.clock)

    def test_the_lanes_block_carries_the_map_after_the_rules_and_before_the_quota(self):
        block = self.arch(COMMITTED["dlane"]).lanes_block(self.arch(COMMITTED["dlane"]).lane_quota())
        at = block.index(f"TRAIN MAP ({dlane.MAP_LABEL}).")
        self.assertLess(block.index("DIRECTION BAR on Train"), at)
        self.assertLess(block.index("THE GRAVEYARD AND THE LANES"), at)
        self.assertLess(at, block.index("DIRECTION QUOTA"))
        self.assertIn(dlane.train_map_text(COMMITTED), block)
        self.assertEqual(leaks(block[at:block.index("DIRECTION QUOTA")]), [])
        prompt = self.arch(COMMITTED["dlane"]).prompt()
        self.assertIn(dlane.train_map_text(COMMITTED), prompt)

    def test_the_switch_off_and_a_missing_file_are_the_block_without_the_map(self):
        off = self.arch(MAP_OFF["dlane"]).lanes_block()
        self.assertNotIn("TRAIN MAP", off)
        on = self.arch(COMMITTED["dlane"]).lanes_block()
        self.assertEqual(on.replace(dlane.train_map_text(COMMITTED) + "\n", ""), off)
        with MapFile(missing=True):
            self.assertEqual(self.arch(COMMITTED["dlane"]).lanes_block(), off)
        self.assertEqual(self.arch({**COMMITTED["dlane"], "mode": "off"}).lanes_block(), "")


# ------------------------------------------------------------------------------------------------ 5. the golden texts
#: sha256 of the texts below on main d70e00c3 (the release before the map), computed with these same fixtures (with
#: `train_map` true in the settings, which d70e00c3 ignores): the map's switch off, the lane off and the alpha lane are
#: byte for byte that release's.
GOLDEN = {
    "brief committed, map off": "37f56f155c1ba24638576da9c0aecabfcdfe1a5de5ea0f7a12cd6f585d287e62",
    "brief gate": "df65c33c0cceddaaa9f161101070c3d3a5278d68771b37c6dbafec69d9fb9a02",
    "architect prompt, lane off": "ece9e5ff2a95191affa1a3f8f082b4f8926595f7462146a6978973c54abc8f85",
    "architect prompt, map off": "d882e7cb04deefefd23dd30fb493609b73958f4d3d8720de49631966c9cbd5ce",
    "researcher brief alpha": "8f64e112dbaf689a02763c82523c3c22ef231080274cc4a1f35171125df975d7",
    "researcher brief direction, map off": "1e991dd753a6840ecccebea4214ad22498682589283c0e926e1faaab08e399cb",
    "researcher brief direction, lane off": "8f64e112dbaf689a02763c82523c3c22ef231080274cc4a1f35171125df975d7",
}


def golden_texts() -> dict[str, str]:
    """The texts the golden digests are of. Uses only APIs main d70e00c3 has, so the same function computes them there."""
    from league.tests.test_swarm_researcher_dlane import DIRECTION_SPEC
    from league.tests.test_swarm_researcher_dlane import Case as ResearcherCase

    out: dict[str, str] = {}
    out["brief committed, map off"] = dlane.brief_text(MAP_OFF, ["SPY", "QQQ"])
    out["brief gate"] = dlane.brief_text({"dlane": {"mode": "gate", "train_map": False}}, ["SPY"])

    def prompt(block: dict) -> str:
        with tempfile.TemporaryDirectory() as d:
            clock = Clock()
            store = SwarmStore(Path(d), clock=clock)
            try:
                settings = copy.deepcopy(S.DEFAULTS)
                settings["population"].update(start=4, ceiling=40, floor=0)
                settings["dlane"] = copy.deepcopy(block)
                store.add_family({"id": "alpha-one", "mechanism": "An invented skew program sells rich wings after calm "
                                  "weeks.", "structure": "iron_condor", "roots": ["SPY"], "dte": [7, 21]}, origin="architect")
                return Architect(store, None, settings, clock=clock).prompt()
            finally:
                store.close()

    out["architect prompt, lane off"] = prompt({**POLICY["dlane"], "mode": "off", "train_map": True})
    out["architect prompt, map off"] = prompt(MAP_OFF["dlane"])

    case = ResearcherCase("run")

    def brief(mode: str, spec: dict, train_map: bool) -> str:
        case.setUp()
        try:
            store, researcher, _ = case.make(mode)
            researcher.settings["dlane"]["train_map"] = train_map
            fid = store.add_family({**spec, "id": "fam"}, origin="architect")["id"]
            return researcher.brief(store.family(fid))
        finally:
            case.doCleanups()

    alpha = {k: v for k, v in DIRECTION_SPEC.items() if k != "lane"}
    out["researcher brief alpha"] = brief("gate", alpha, True)
    out["researcher brief direction, map off"] = brief("gate", DIRECTION_SPEC, False)
    out["researcher brief direction, lane off"] = brief("off", DIRECTION_SPEC, True)
    return out


def digests() -> dict[str, str]:
    return {k: hashlib.sha256(v.encode("utf-8")).hexdigest() for k, v in golden_texts().items()}


class Golden(unittest.TestCase):
    def test_the_switch_off_the_lane_off_and_the_alpha_lane_are_main_d70e00c3s(self):
        texts = golden_texts()
        self.assertEqual(set(texts), set(GOLDEN))
        for key, want in GOLDEN.items():
            self.assertEqual(hashlib.sha256(texts[key].encode("utf-8")).hexdigest(), want, key)
        # The texts are the real ones (not empty or trivially equal): the lane's words where the lane is on, none of the
        # map's anywhere.
        self.assertIn("LANES. Two research lanes", texts["architect prompt, map off"])
        self.assertNotIn("LANES.", texts["architect prompt, lane off"])
        self.assertIn("YOUR LANE: DIRECTION", texts["researcher brief direction, map off"])
        self.assertNotIn("YOUR LANE", texts["researcher brief alpha"])
        self.assertIn("YOUR FAMILY:", texts["researcher brief alpha"])
        for key, text in texts.items():
            self.assertNotIn("TRAIN MAP", text, key)

    def test_the_map_on_reaches_a_direction_familys_brief_and_never_an_alpha_familys(self):
        from league.tests.test_swarm_researcher_dlane import DIRECTION_SPEC
        from league.tests.test_swarm_researcher_dlane import Case as ResearcherCase

        case = ResearcherCase("run")
        case.setUp()
        try:
            store, researcher, _ = case.make("gate")
            researcher.settings["dlane"]["train_map"] = True
            fid = store.add_family({**DIRECTION_SPEC, "id": "dir"}, origin="architect")["id"]
            alpha = store.add_family({**{k: v for k, v in DIRECTION_SPEC.items() if k != "lane"}, "id": "alpha"},
                                     origin="architect")["id"]
            direction, plain = researcher.brief(store.family(fid)), researcher.brief(store.family(alpha))
        finally:
            case.doCleanups()
        self.assertIn(dlane.train_map_brief(researcher.settings, ["SPY"]), direction)
        self.assertNotIn("TRAIN MAP", plain)


# ------------------------------------------------------------------------------------------------ 6. the report
class Reported(unittest.TestCase):
    def test_the_operators_report_lists_the_map_with_its_cost(self):
        from league.ops import dlane_report as R

        [row] = [r for r in R.LOOSENED if r["rule"].startswith("the TRAIN MAP")]
        text = " ".join(row.values())
        for words in ("births aim at in-sample winners", "false-positive rate per program is unchanged",
                      "more false passes in count", "dlane.train_map false hides it", "labelled in-sample"):
            self.assertIn(words, text)
        self.assertTrue(text.isascii())
        [graveyard] = [r for r in R.LOOSENED if r["rule"].startswith("graveyard alpha rows")]
        self.assertIn("10.4%", graveyard["cost"])


# ------------------------------------------------------------------------------------------------ 7. the wall
class Wall(unittest.TestCase):
    def test_the_map_is_protected_like_dlane_py(self):
        self.assertIn("league/swarm/dlane_map.json", ci.FORBIDDEN)
        source = (Path(ci.REPO) / "gateway" / "lib" / "protected.mjs").read_text(encoding="utf-8")
        self.assertIn("'league/swarm/dlane_map.json'", source)
        self.assertTrue(ci.guard(["league/swarm/dlane_map.json"], None))
        self.assertTrue(ci.guard(["league/swarm/dlane_map.json"], "engineer/memory"))
        self.assertEqual(dlane.MAP_PATH, Path(ci.REPO) / "league" / "swarm" / "dlane_map.json")


# ------------------------------------------------------------------------------------- 8. the operator's private figures
class PrivateFigures(unittest.TestCase):
    def test_the_operators_private_figures_never_reach_an_agent_or_the_repo(self):
        path = private_figures_file()
        if path is None:
            self.skipTest(f"no operator-local private figures file (${PRIVATE_ENV} unset or no file)")
        self.assertFalse(path.resolve().is_relative_to(Path(ci.REPO).resolve()), "the private file sits outside the repo")
        figures = private_figures()
        self.assertTrue(figures, "the private file names figures")
        texts = {"architect": dlane.train_map_text(COMMITTED)}
        for roots in ROOT_SETS:
            texts[f"brief {roots}"] = dlane.brief_text(COMMITTED, roots)
        # The files this map adds to the repo: the map itself and these tests (their fixtures use other figures).
        texts["dlane_map.json"] = dlane.MAP_PATH.read_text(encoding="utf-8")
        texts["test_dlane_trainmap.py"] = Path(__file__).read_text(encoding="utf-8")
        for name, text in texts.items():
            for figure in figures:
                self.assertIsNone(re.search(rf"(?<![\d.,]){re.escape(figure)}(?![\d])", text), (name, "a private figure"))

    def test_the_private_figures_reader(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "figures.txt"
            p.write_text("# the operator's\n9.87  # a ratio\n\n6,543\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {PRIVATE_ENV: str(p)}):
                self.assertEqual(private_figures_file(), p)
                self.assertEqual(private_figures(), ("9.87", "6,543"))
            with mock.patch.dict(os.environ, {PRIVATE_ENV: str(Path(d) / "nope.txt")}):
                self.assertIsNone(private_figures_file())
                self.assertEqual(private_figures(), ())
            with mock.patch.dict(os.environ, {PRIVATE_ENV: ""}):
                self.assertEqual(private_figures(), ())


if __name__ == "__main__":
    unittest.main()
