"""Release E4's universe generator (scripts/gen_universe.py; E4-SPEC section 11), on invented lists.

Every list here is release E1's own 18 stocks (already in the tree) and invented tickers beginning "ZZ": never an
index's members, never a date beside a symbol. What is held:

- THE INPUT: a tradable.json is {"as_of", "stock"} and nothing else; any other key, and any entry that is not a
  plain ticker, is refused (it could carry a date beside a symbol);
- THE REFUSALS, each by name: a ticker outside the gateway's `STOCK_SYMBOL` pattern (and outside the constitution's
  own), an ETF, a symbol twice, a list under 450 or over 650 names, a list that lacks one of E1's stocks;
- THE CONSTITUTION: the rewrite changes `equity_money.universe.stock` and the pin AND NOTHING ELSE, of the text and
  of the rules (so the money digest moves only by the universe); E1's 35 stay inside it with their classes; the
  list is sorted and carries no date; a second run writes nothing;
- THE GATEWAY: its list is rewritten only as text for a patch, reads back by `league.ci`'s own reader as the same
  ETFs and exactly these stocks, and `league.ci.check_equity` passes a tree that holds both halves and refuses a
  tree that holds one;
- THE COMMAND: `--check` writes nothing; without `--gateway-patch` nothing is written while the gateway would
  change; gateway/ is never written; a refused input writes nothing;
- THE TREE AS IT STANDS: its two lists are release E1's 18 or exactly what the generator writes for the list they
  hold (no hand edit), and neither identity the bands bind to reads a file of this package.

Standard library only.
"""

from __future__ import annotations

import copy
import io
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from league import ci
from league.equity import config
from scripts import gen_universe as G

REPO = Path(__file__).resolve().parents[2]
E1_STOCKS = [s for s, k in config.UNIVERSE.items() if k == config.STOCK]
E1_ETFS = [s for s, k in config.UNIVERSE.items() if k == config.ETF]
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
#: 676 invented tickers, none of them E1's: "ZZAA" .. "ZZZZ".
INVENTED = [f"ZZ{a}{b}" for a in LETTERS for b in LETTERS]
AS_OF = "2031-03-04"


def invented(count: int = 500, *, skip: int = 0) -> list[str]:
    """E1's 18 stocks and invented tickers, `count` names in all, sorted."""
    return sorted(E1_STOCKS + INVENTED[skip:skip + count - len(E1_STOCKS)])


def tree_text(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def rules_of(text: str) -> dict:
    return G._namespace(text, G.CONSTITUTION)


def apply_patch(before: str, patch: str) -> str:
    """A unified diff applied by hand: every context line and every removed line must be the file's own."""
    source, out, at = before.splitlines(keepends=True), [], 0
    rows = patch.splitlines(keepends=True)
    k = next(i for i, row in enumerate(rows) if row.startswith("@@"))
    while k < len(rows):
        start = int(re.match(r"@@ -(\d+)", rows[k]).group(1)) - 1
        out += source[at:start]
        at, k = start, k + 1
        while k < len(rows) and not rows[k].startswith("@@"):
            tag, body = rows[k][0], rows[k][1:]
            if tag in " -":
                assert source[at] == body, (at, source[at], body)
                at += 1
            if tag in " +":
                out.append(body)
            k += 1
    return "".join(out + source[at:])


#: A small constitution in release E1's own layout (the `"stock": [...]` literal that closes `universe`), for the
#: paths the tree no longer shows once it is generated. `{extra}` is module code after the table.
MINI = '''import hashlib
import json

CONSTITUTION = {{
    "version": 1,
    "budgets": {{"sail_month_usd": "100"}},
    "equity_money": {{
        "enabled": True,
        "universe": {{"etf": [{etfs}],
                     "stock": [{stocks}]}},
        "position_share": {{"etf": "0.50", "stock": "0.20"}},
    }},
}}


def digest(constitution=None):
    text = json.dumps(constitution or CONSTITUTION, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def money_digest(constitution=None):
    rules = dict(constitution or CONSTITUTION)
    rules.pop("budgets", None)
    return digest(rules)


def equity_money_problems(constitution=None):
    return {problems}

{extra}
PINNED_DIGEST = '{pin}'
'''


def mini(*, stocks=None, extra="", problems="[]", pin="0" * 64) -> str:
    quoted = ", ".join(json.dumps(s) for s in (E1_STOCKS if stocks is None else stocks))
    return MINI.format(etfs=", ".join(json.dumps(s) for s in E1_ETFS), stocks=quoted, extra=extra, problems=problems,
                       pin=pin)


class TheInput(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "tradable.json"

    def given(self, raw) -> Path:
        self.path.write_text(raw if isinstance(raw, str) else json.dumps(raw), encoding="utf-8")
        return self.path

    def test_the_houses_file_reads_as_its_sorted_symbols(self):
        names = invented()
        shuffled = names[1::2] + names[0::2]
        self.assertEqual(G.read_input(self.given({"as_of": AS_OF, "stock": shuffled})), names)
        self.assertEqual(G.read_input(str(self.given({"stock": names, "as_of": AS_OF}))), names)

    def test_another_shape_is_refused(self):
        names = invented()
        for raw, why in (
                ("not json", "not a readable JSON file"),
                (names, "exactly the keys"),
                ({"stock": names}, "exactly the keys"),
                ({"as_of": AS_OF}, "exactly the keys"),
                ({"as_of": AS_OF, "stock": names, "members": {"ZZAA": "2029-01-02"}}, "exactly the keys"),
                ({"as_of": AS_OF, "stock": names, "since": AS_OF}, "exactly the keys"),
                ({"as_of": "2031-03", "stock": names}, "`as_of` is the day"),
                ({"as_of": "20310304", "stock": names}, "`as_of` is the day"),
                ({"as_of": "2031-02-30", "stock": names}, "`as_of` is the day"),
                ({"as_of": 20310304, "stock": names}, "`as_of` is the day"),
                ({"as_of": None, "stock": names}, "`as_of` is the day"),
                ({"as_of": AS_OF, "stock": {s: AS_OF for s in names}}, "`stock` is a list of tickers"),
                ({"as_of": AS_OF, "stock": " ".join(names)}, "`stock` is a list of tickers")):
            with self.assertRaises(ValueError, msg=why) as refused:
                G.read_input(self.given(raw))
            self.assertIn(why, str(refused.exception))
        with self.assertRaises(ValueError) as refused:
            G.read_input(Path(self.dir.name) / "missing.json")
        self.assertIn("not a readable JSON file", str(refused.exception))

    def test_a_date_beside_a_symbol_is_refused(self):
        """A dated list in a public repository would be a point-in-time membership history: an entry that is not a
        plain ticker never gets as far as the list."""
        names = invented()
        for entry in (["ZZAA", "2029-01-02"], {"symbol": "ZZAA", "since": "2029-01-02"}, 20290102, None):
            with self.assertRaises(ValueError) as refused:
                G.read_input(self.given({"as_of": AS_OF, "stock": names[:-1] + [entry]}))
            self.assertIn("could carry a date beside a symbol", str(refused.exception))
        for entry in ("ZZAA 2029-01-02", "ZZAA@2029", "2029-01-02"):
            with self.assertRaises(ValueError) as refused:
                G.read_input(self.given({"as_of": AS_OF, "stock": names[:-1] + [entry]}))
            self.assertIn("fail the gateway's STOCK_SYMBOL pattern", str(refused.exception))

    def test_a_refused_list_is_refused_at_the_input(self):
        with self.assertRaises(ValueError) as refused:
            G.read_input(self.given({"as_of": AS_OF, "stock": invented(120)}))
        self.assertIn("the list has 120 names", str(refused.exception))
        self.assertIsInstance(refused.exception, G.Refused)


class TheRefusals(unittest.TestCase):
    def why(self, names, **kw):
        return G.problems(names, keep=kw.get("keep", E1_STOCKS), etfs=kw.get("etfs", E1_ETFS))

    def test_a_sound_list_is_not_refused(self):
        self.assertEqual(self.why(invented()), [])
        self.assertEqual(self.why(invented(G.MIN_NAMES)), [])
        self.assertEqual(self.why(invented(G.MAX_NAMES)), [])
        self.assertEqual(self.why(list(reversed(invented()))), [],
                         "the order of the input is not a rule: the list is sorted")
        self.assertEqual((G.MIN_NAMES, G.MAX_NAMES), (450, 650))

    def test_the_size_of_a_three_year_union(self):
        self.assertEqual(self.why(invented(G.MIN_NAMES - 1)),
                         ["the list has 449 names: a 36-month union of the index has 450 to 650"])
        self.assertEqual(self.why(invented(G.MAX_NAMES + 1)),
                         ["the list has 651 names: a 36-month union of the index has 450 to 650"])
        self.assertIn("the list has 18 names", " ".join(self.why(E1_STOCKS)))
        self.assertIn("the list has 0 names", " ".join(self.why([])))

    def test_a_ticker_the_gateway_would_not_price(self):
        for bad in ("zzaa", "ZZAAAA", "ZZ1", "ZZ.ABC", "ZZ-A", "", " ZZAA", "ZZAA\n", "ZZ/USD", "ZZAA261016C00740000"):
            refused = self.why(invented()[:-1] + [bad])
            self.assertEqual(len(refused), 1, bad)
            self.assertIn("1 symbol(s) fail the gateway's STOCK_SYMBOL pattern", refused[0])
        # A share class is one or two letters at the gateway and one in the constitution: the narrower one binds.
        refused = self.why(invented()[:-1] + ["ZZ.AB"])
        self.assertEqual(refused, ["1 symbol(s) pass the gateway's pattern and fail the constitution's ticker pattern "
                                   "(one class letter): ZZ.AB"])
        self.assertEqual(self.why(invented()[:-1] + ["ZZ.A"]), [])

    def test_the_patterns_are_the_files_own(self):
        gateway = re.search(r"^const STOCK_SYMBOL = /\^(.+)\$/;$", tree_text(G.GATEWAY), re.M)
        self.assertEqual(G.STOCK_SYMBOL.pattern, gateway.group(1).replace("\\.", r"\."))
        mine = re.search(r'^_TICKER = re\.compile\(r"(.+)"\)$', tree_text(G.CONSTITUTION), re.M)
        self.assertEqual(G.TICKER.pattern, mine.group(1))

    def test_an_etf_is_never_a_stock(self):
        for fund in ("SPY", "XLK", "TLT"):
            refused = self.why(invented()[:-1] + [fund])
            self.assertEqual(len(refused), 1)
            self.assertIn("1 symbol(s) are ETFs (the stock list names stocks; `universe.etf` is not generated): "
                          f"{fund}", refused[0])

    def test_a_symbol_twice(self):
        refused = self.why(invented() + ["ZZAA", "AAPL"])
        self.assertEqual(refused, ["2 symbol(s) are named more than once: AAPL, ZZAA"])

    def test_every_one_of_e1s_stocks_is_kept(self):
        self.assertEqual(len(E1_STOCKS), 18)
        for stock in E1_STOCKS:
            names = [s for s in invented(501) if s != stock]
            refused = self.why(names)
            self.assertEqual(len(refused), 1, stock)
            self.assertIn(f"the list lacks 1 of release E1's stocks", refused[0])
            self.assertTrue(refused[0].endswith(f": {stock}"), refused[0])

    def test_a_refusal_names_at_most_ten(self):
        refused = self.why(invented()[:-30] + [f"zz{n}" for n in range(30)])
        self.assertEqual(len(refused), 1)
        self.assertIn("30 symbol(s) fail", refused[0])
        self.assertIn("and 20 more", refused[0])
        self.assertEqual(refused[0].count("'zz"), G.NAMED)

    def test_an_entry_that_is_not_a_string_ends_the_reading(self):
        self.assertEqual(len(self.why(invented() + [["ZZAA", "2029-01-02"]])), 1)
        self.assertIn("a date beside a symbol", self.why([{"ZZAA": 1}])[0])


class TheConstitution(unittest.TestCase):
    """The rewrite of league/constitution.py, on the tree's own text (release E1's literal, or a generated block)."""

    def setUp(self):
        self.text = tree_text(G.CONSTITUTION)
        self.before = rules_of(self.text)
        self.names = invented(520)
        self.out = G.constitution_text(self.text, self.names)
        self.after = rules_of(self.out)

    def test_the_list_is_written_sorted_between_the_markers(self):
        table = self.after["CONSTITUTION"]["equity_money"]
        self.assertEqual(table["universe"]["stock"], self.names)
        self.assertEqual(table["universe"]["stock"], sorted(set(self.names)))
        self.assertEqual(table["universe"]["etf"], self.before["CONSTITUTION"]["equity_money"]["universe"]["etf"])
        self.assertEqual((self.out.count(G.BEGIN), self.out.count(G.END)), (1, 1))
        block = self.out[self.out.index(G.BEGIN):self.out.index(G.END)]
        self.assertIn(f"# {len(self.names)} stocks.", block)
        for name in self.names:
            self.assertIn(json.dumps(name), block)
        self.assertFalse([line for line in block.splitlines() if len(line) > G.WIDTH])

    def test_nothing_but_the_stock_list_and_the_pin_moves(self):
        """NO bound, share, weight, seat or cap changes: the rules without the list are the tree's, and so is every
        line of the file outside the block and the pin."""
        def others(namespace):
            rules = copy.deepcopy(namespace["CONSTITUTION"])
            del rules["equity_money"]["universe"]["stock"]
            return rules

        self.assertEqual(others(self.after), others(self.before))
        for name in ("EQUITY_MONEY_BOUNDS", "RISK_FREE", "EQUITY_CLASSES", "LEGACY_GRANT_DIGESTS", "GATEWAY_VARS"):
            self.assertEqual(self.after[name], self.before[name], name)

        def outside(text):
            if G.BEGIN in text:
                head, rest = text.split(G.BEGIN)
                tail = rest.split(G.END)[1].split("\n", 2)[2]       # past the marker's line and the brace's
            else:
                found = G._LEGACY.search(text)
                head, tail = text[:found.start()], text[found.end() + 1:]
            return G._PINNED.sub("PINNED", head.rstrip(" ")), G._PINNED.sub("PINNED", tail)

        self.assertEqual(outside(self.out), outside(self.text))

    def test_the_money_digest_moves_and_only_by_the_universe(self):
        digest, money = self.after["digest"], self.after["money_digest"]
        self.assertEqual(self.after["PINNED_DIGEST"], digest(self.after["CONSTITUTION"]))
        self.assertNotEqual(self.after["PINNED_DIGEST"], self.before["PINNED_DIGEST"])
        self.assertNotEqual(money(self.after["CONSTITUTION"]), self.before["money_digest"](self.before["CONSTITUTION"]),
                            "the universe is a money rule: the standing grant re-ratifies")
        self.assertFalse(any(path[0] == "equity_money" for path in self.after["RISK_FREE"]))
        # With the tree's own list put back, both digests are the tree's again: the list is all that moved.
        back = copy.deepcopy(self.after["CONSTITUTION"])
        was = self.before["CONSTITUTION"]["equity_money"]["universe"]["stock"]
        back["equity_money"]["universe"]["stock"] = list(was)
        self.assertEqual(digest(back), self.before["PINNED_DIGEST"])
        self.assertEqual(money(back), self.before["money_digest"](self.before["CONSTITUTION"]))

    def test_e1s_universe_stays_inside_it_and_the_rows_stay_in_their_bounds(self):
        universe = self.after["CONSTITUTION"]["equity_money"]["universe"]
        named = {s: k for k in ("etf", "stock") for s in universe[k]}
        for symbol, klass in config.UNIVERSE.items():
            self.assertEqual(named.get(symbol), klass, symbol)
        self.assertEqual(self.after["equity_money_problems"](self.after["CONSTITUTION"]), [])
        self.assertEqual(len(named), len(universe["etf"]) + len(universe["stock"]), "no symbol in both classes")

    def test_no_date_is_written(self):
        block = self.out[self.out.index(G.BEGIN):self.out.index(G.END)]
        self.assertIsNone(re.search(r"\d{4}-\d{2}-\d{2}|\b20\d\d\b", block))

    def test_a_second_run_writes_nothing_and_a_new_list_moves_only_the_block(self):
        self.assertEqual(G.constitution_text(self.out, self.names), self.out)
        self.assertEqual(G.constitution_text(self.out, list(reversed(self.names))), self.out)
        other = invented(520, skip=3)
        again = G.constitution_text(self.out, other)
        self.assertEqual(rules_of(again)["CONSTITUTION"]["equity_money"]["universe"]["stock"], other)
        self.assertEqual(again.split(G.BEGIN)[0], self.out.split(G.BEGIN)[0])
        self.assertEqual(G._PINNED.sub("", again.split(G.END)[1]), G._PINNED.sub("", self.out.split(G.END)[1]))
        self.assertEqual(G.constitution_text(again, self.names), self.out,
                         "and back: the text is a function of the list")

    def test_a_refused_list_writes_no_text(self):
        for names, why in ((invented(100), "the list has 100 names"), (invented()[:-1] + ["SPY"], "are ETFs"),
                           ([s for s in invented(501) if s != "COST"], "lacks 1 of release E1's stocks"),
                           (invented() + ["ZZAA"], "more than once")):
            with self.assertRaises(G.Refused) as refused:
                G.constitution_text(self.text, names)
            self.assertIn(why, str(refused.exception))


class TheConstitutionsEdges(unittest.TestCase):
    """The paths the tree shows only once: release E1's literal, and a file the generator must not guess at."""

    def test_e1s_literal_becomes_the_block(self):
        text = mini()
        out = G.constitution_text(text, invented(450))
        after = rules_of(out)
        self.assertEqual(after["CONSTITUTION"]["equity_money"]["universe"]["stock"], invented(450))
        self.assertEqual(after["PINNED_DIGEST"], after["digest"](after["CONSTITUTION"]))
        lines = out.splitlines()
        begin, end = lines.index(" " * 21 + G.BEGIN), lines.index(" " * 21 + G.END)
        self.assertEqual(lines[begin - 1].strip()[:8], '"universe"'[:8])
        self.assertEqual(lines[end + 1], " " * 21 + "},")
        self.assertEqual(lines[end + 2].strip(), '"position_share": {"etf": "0.50", "stock": "0.20"},')
        self.assertEqual(G.constitution_text(out, invented(450)), out)

    def test_the_pin_keeps_its_quotes(self):
        for quote in ("'", '"'):
            text = mini().replace(f"PINNED_DIGEST = '{'0' * 64}'", f"PINNED_DIGEST = {quote}{'0' * 64}{quote}")
            out = G.constitution_text(text, invented())
            after = rules_of(out)
            self.assertIn(f"\nPINNED_DIGEST = {quote}{after['digest'](after['CONSTITUTION'])}{quote}\n", out)
            self.assertEqual(G.constitution_text(out, invented()), out)

    def test_a_file_with_no_single_literal_is_not_guessed_at(self):
        for text, why in (
                (mini().replace('"COST"]},', '"COST"],\n                     },'), "no generated block and no single"),
                (mini() + '\nOTHER = {"universe": {"etf": [],\n                     "stock": ["AAPL"]},\n}\n',
                 "no generated block and no single"),
                (mini().replace('"COST"]},', '"COST",]},'), "no generated block and no single"),
                (mini(stocks=[]).replace('"stock": []},', '"stock": STOCKS},'), "could not be read"),
                (mini().replace("PINNED_DIGEST = '", "PINNED = '"), "PINNED_DIGEST must be pinned once"),
                (mini() + f"PINNED_DIGEST = '{'1' * 64}'\n", "PINNED_DIGEST must be pinned once"),
                (mini().replace("def digest(", "def _digest("), "this tree is not release E1's or later"),
                ("CONSTITUTION = (", "could not be read")):
            with self.assertRaises(G.Refused, msg=why) as refused:
                G.constitution_text(text, invented())
            self.assertIn(why, str(refused.exception))

    def test_the_markers_stand_once_alone_and_in_order(self):
        out = G.constitution_text(mini(), invented())
        for text in (out.replace(" " * 21 + G.END + "\n", ""), out.replace(" " * 21 + G.BEGIN + "\n", ""),
                     out.replace(G.END, G.END + "  # and a note"), out.replace(G.BEGIN, '"note": 1,  ' + G.BEGIN),
                     out + f"# {G.BEGIN}\n", out.replace(G.BEGIN, "#1").replace(G.END, G.BEGIN).replace("#1", G.END)):
            with self.assertRaises(G.Refused) as refused:
                G.constitution_text(text, invented())
            self.assertIn("the generated block's two markers must each stand once", str(refused.exception))

    def test_a_rewrite_that_would_move_another_rule_is_refused(self):
        """The generator's own seal: were any other row to follow the list (here a count derived from it), nothing
        is written."""
        extra = 'CONSTITUTION["equity_money"]["names"] = len(CONSTITUTION["equity_money"]["universe"]["stock"])\n'
        with self.assertRaises(G.Refused) as refused:
            G.constitution_text(mini(extra=extra), invented())
        self.assertIn("would change more than `equity_money.universe.stock`", str(refused.exception))

    def test_a_table_outside_its_bounds_is_refused(self):
        with self.assertRaises(G.Refused) as refused:
            G.constitution_text(mini(problems='["equity_money.universe.stock is a list of tickers"]'), invented())
        self.assertIn("equity_money.universe.stock is a list of tickers", str(refused.exception))


class TheGateway(unittest.TestCase):
    """The gateway's half: text for a patch, read back by `league.ci`'s own reader."""

    def setUp(self):
        self.text = tree_text(G.GATEWAY)
        self.names = invented(520) + ["ZZ.A"]
        self.names.sort()
        self.out = G.gateway_text(self.text, self.names)

    def ci_reads(self, text: str):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "gateway" / "lib").mkdir(parents=True)
            (Path(tmp) / G.GATEWAY).write_text(text, encoding="utf-8")
            return ci.gateway_stock_universe(Path(tmp))

    def test_the_generators_reader_is_league_cis(self):
        self.assertEqual(G._GATEWAY_LIST.pattern, ci.GATEWAY_STOCK_UNIVERSE.pattern)
        self.assertEqual(G._GATEWAY_PAIR.pattern, ci.GATEWAY_STOCK_PAIR.pattern)
        for text in (self.text, self.out):
            universe, problems = self.ci_reads(text)
            self.assertEqual(problems, [])
            self.assertEqual(G.gateway_pairs(text), universe)
            self.assertEqual(list(G.gateway_pairs(text)), list(universe), "and in the same order")

    def test_the_same_etfs_and_exactly_these_stocks(self):
        was, now = G.gateway_pairs(self.text), G.gateway_pairs(self.out)
        funds = [s for s, k in was.items() if k == "etf"]
        self.assertEqual([s for s, k in now.items() if k == "etf"], funds)
        self.assertEqual([s for s, k in now.items() if k == "stock"], self.names)
        self.assertEqual(sorted(funds), sorted(E1_ETFS))

    def test_every_byte_outside_the_block_is_the_files(self):
        self.assertEqual((self.out.count(G.GATEWAY_BEGIN), self.out.count(G.GATEWAY_END)), (1, 1))
        head, tail = self.out.split(G.GATEWAY_BEGIN)[0], self.out.split(G.GATEWAY_END)[1]
        self.assertTrue(self.text.startswith(head))
        self.assertTrue(self.text.endswith(tail))
        self.assertTrue(tail.startswith("\n});\n"), "the block closes the object")
        block = self.out[len(head):len(self.out) - len(tail)]
        self.assertFalse([line for line in block.splitlines() if len(line) > G.WIDTH])
        self.assertNotIn("});", block)
        self.assertIn("'BRK.B': 'stock',", block)
        self.assertIn("'ZZ.A': 'stock',", block, "a share class is quoted: it is no identifier")
        self.assertIn(" ZZAA: 'stock',", block)
        self.assertIsNone(re.search(r"\d{4}-\d{2}-\d{2}|\b20\d\d\b", block))

    def test_a_second_run_writes_nothing_and_a_new_list_moves_only_the_block(self):
        self.assertEqual(G.gateway_text(self.out, self.names), self.out)
        other = invented(470, skip=9)
        again = G.gateway_text(self.out, other)
        self.assertEqual([s for s, k in G.gateway_pairs(again).items() if k == "stock"], other)
        self.assertEqual(again.split(G.GATEWAY_BEGIN)[0], self.out.split(G.GATEWAY_BEGIN)[0])
        self.assertEqual(again.split(G.GATEWAY_END)[1], self.out.split(G.GATEWAY_END)[1])
        self.assertEqual(G.gateway_text(again, self.names), self.out)

    def test_a_list_it_cannot_find_is_not_guessed_at(self):
        one = "export const STOCK_UNIVERSE = Object.freeze({\n  SPY: 'etf',\n  AAPL: 'stock',\n});\n"
        self.assertEqual(G.gateway_pairs(G.gateway_text(one.replace("SPY: 'etf',", "SPY: 'etf', QQQ: 'etf',"),
                                                        invented())).get("QQQ"), "etf")
        for text, why in (
                (one.replace("STOCK_UNIVERSE", "STOCK_LIST"), "must be declared once"),
                (one + one, "must be declared once"),
                (one.replace("AAPL: 'stock',", "AAPL: 'stock', SQQQ,"), "an entry that is not a SYM"),
                (one.replace("AAPL: 'stock',", "AAPL: 'bond',"), "twice, or not etf or stock"),
                (one.replace("AAPL: 'stock',", "AAPL: 'stock',\n  SPY: 'etf',"), "twice, or not etf or stock"),
                (one.replace("AAPL: 'stock',", "AAPL: 'stock', QQQ: 'etf',"), "not whole lines after its ETF pairs"),
                (one.replace("AAPL: 'stock',", "AAPL: 'stock',\n  QQQ: 'etf',"), "not whole lines after its ETF pairs"),
                (one.replace("  AAPL: 'stock',\n", ""), "not whole lines after its ETF pairs"),
                (one.replace("AAPL: 'stock',", "AAPL: 'stock',\n  DIA: 'etf',\n  MSFT: 'stock',"),
                 "not whole lines after its ETF pairs")):
            with self.assertRaises(G.Refused, msg=why) as refused:
                G.gateway_text(text, invented())
            self.assertIn(why, str(refused.exception))

    def test_the_markers_and_what_stands_beside_them(self):
        stray = self.out.replace("  TLT: 'etf',", "  TLT: 'etf', ZZZZ: 'stock',", 1)
        self.assertNotEqual(stray, self.out)
        with self.assertRaises(G.Refused) as refused:
            G.gateway_text(stray, invented(470))
        self.assertIn("does not read back as the same ETFs and exactly these stocks", str(refused.exception))
        moved = self.out.replace("  " + G.GATEWAY_BEGIN + "\n", "").replace(
            "export const STOCK_UNIVERSE", "  " + G.GATEWAY_BEGIN + "\nexport const STOCK_UNIVERSE")
        with self.assertRaises(G.Refused) as refused:
            G.gateway_text(moved, self.names)
        self.assertIn("markers are outside STOCK_UNIVERSE", str(refused.exception))
        with self.assertRaises(G.Refused) as refused:
            G.gateway_text(self.out.replace("  " + G.GATEWAY_END + "\n", ""), self.names)
        self.assertIn("two markers must each stand once", str(refused.exception))

    def test_the_patch_is_the_whole_change_as_git_takes_it(self):
        patch = G.patch_text(self.text, self.out, G.GATEWAY)
        self.assertTrue(patch.startswith(f"diff --git a/{G.GATEWAY} b/{G.GATEWAY}\n--- a/{G.GATEWAY}\n"
                                         f"+++ b/{G.GATEWAY}\n@@ "))
        self.assertEqual(apply_patch(self.text, patch), self.out)
        self.assertEqual(G.patch_text(self.out, self.out, G.GATEWAY), "")
        self.assertEqual(G.patch_text("a\nb", "a\nc", "x").splitlines()[-4:],
                         ["-b", "\\ No newline at end of file", "+c", "\\ No newline at end of file"])

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_git_applies_the_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "gateway" / "lib").mkdir(parents=True)
            (Path(tmp) / G.GATEWAY).write_text(self.text, encoding="utf-8")
            (Path(tmp) / "universe.patch").write_text(G.patch_text(self.text, self.out, G.GATEWAY), encoding="utf-8")
            done = subprocess.run(["git", "apply", "universe.patch"], cwd=tmp, capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stderr), (0, ""))
            self.assertEqual((Path(tmp) / G.GATEWAY).read_text(encoding="utf-8"), self.out)
            # A file that does not end its last line (git's own marker for it).
            (Path(tmp) / "x").write_text("a\nb", encoding="utf-8")
            (Path(tmp) / "x.patch").write_text(G.patch_text("a\nb", "a\nc", "x"), encoding="utf-8")
            done = subprocess.run(["git", "apply", "x.patch"], cwd=tmp, capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stderr), (0, ""))
            self.assertEqual((Path(tmp) / "x").read_text(encoding="utf-8"), "a\nc")


class TheCommand(unittest.TestCase):
    """`main` on a copy of the tree's three files: what is written, and what never is."""

    FILES = (G.CONSTITUTION, G.GATEWAY, "gateway/wrangler.jsonc")

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name) / "repo"
        for rel in self.FILES:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / rel, self.root / rel)
        self.was = self.read()
        self.patch = Path(self.dir.name) / "out" / "universe.patch"
        self.names = invented(520)
        self.source = self.given(self.names)

    def given(self, names, name="tradable.json") -> Path:
        path = Path(self.dir.name) / name
        path.write_text(json.dumps({"as_of": AS_OF, "stock": names}), encoding="utf-8")
        return path

    def read(self) -> dict:
        return {rel: (self.root / rel).read_bytes() for rel in self.FILES}

    def run_main(self, *args, source=None) -> tuple[int, str]:
        out = io.StringIO()
        code = G.main(["--from", str(source or self.source), "--repo", str(self.root), *args], out=out)
        return code, out.getvalue()

    def apply(self) -> None:
        caps = self.root / G.GATEWAY
        caps.write_text(apply_patch(caps.read_text(encoding="utf-8"), self.patch.read_text(encoding="utf-8")),
                        encoding="utf-8")

    def test_check_writes_nothing_and_fails_on_a_tree_that_is_not_generated(self):
        code, out = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn(f"check: {G.CONSTITUTION} is not what this input generates", out)
        self.assertIn(f"check: {G.GATEWAY} is not what this input generates", out)
        self.assertEqual(self.read(), self.was)
        self.assertEqual(sorted(p.name for p in Path(self.dir.name).iterdir()), ["repo", "tradable.json"])

    def test_without_the_gateways_patch_nothing_is_written(self):
        code, out = self.run_main()
        self.assertEqual(code, 2)
        self.assertIn("the two lists change together, in one commit; nothing was written", out)
        self.assertEqual(self.read(), self.was)

    def test_the_patch_is_never_written_into_the_gateway(self):
        for inside in (self.root / "gateway" / "universe.patch", self.root / "gateway" / "lib" / "x" / "u.patch",
                       self.root / "gateway"):
            code, out = self.run_main("--gateway-patch", str(inside))
            self.assertEqual(code, 2, inside)
            self.assertIn("a patch file outside gateway/", out)
            self.assertEqual(self.read(), self.was)
        self.assertEqual(sorted(p.name for p in (self.root / "gateway").iterdir()), ["lib", "wrangler.jsonc"])

    def test_a_run_writes_the_constitution_and_the_gateways_half_as_a_patch(self):
        code, out = self.run_main("--gateway-patch", str(self.patch))
        self.assertEqual(code, 0, out)
        now = self.read()
        self.assertEqual(now[G.GATEWAY], self.was[G.GATEWAY], "gateway/ is the owner's: never written")
        self.assertEqual(now["gateway/wrangler.jsonc"], self.was["gateway/wrangler.jsonc"])
        self.assertNotEqual(now[G.CONSTITUTION], self.was[G.CONSTITUTION])
        rules = rules_of(now[G.CONSTITUTION].decode())
        self.assertEqual(rules["CONSTITUTION"]["equity_money"]["universe"]["stock"], self.names)
        was = rules_of(self.was[G.CONSTITUTION].decode())
        self.assertIn(f"universe.stock: {len(was['CONSTITUTION']['equity_money']['universe']['stock'])} -> 520 "
                      "names", out)
        self.assertIn(f"digest {was['PINNED_DIGEST'][:12]} -> {rules['PINNED_DIGEST'][:12]}", out)
        self.assertIn(f"money digest {was['money_digest'](was['CONSTITUTION'])[:12]} -> "
                      f"{rules['money_digest'](rules['CONSTITUTION'])[:12]}", out)
        self.assertIn("THIS MOVES THE MONEY DIGEST", out)
        self.assertFalse(list((self.root / "league").glob("*.tmp")), "the write is whole or not at all")
        # One half alone is a tree `league.ci` refuses; with the owner's step both lists are one list.
        self.assertIn("the gateway's STOCK_UNIVERSE and equity_money.universe differ",
                      " ".join(ci.check_equity(self.root)))
        self.assertEqual(self.run_main("--check")[0], 1)
        self.apply()
        self.assertEqual(ci.check_equity(self.root), [])
        code, out = self.run_main("--check")
        self.assertEqual(code, 0, out)
        self.assertIn(f"check: the tree is what this input generates (digest {rules['PINNED_DIGEST'][:12]}", out)

    def test_a_second_run_writes_nothing(self):
        self.assertEqual(self.run_main("--gateway-patch", str(self.patch))[0], 0)
        self.apply()
        done = self.read()
        self.patch.unlink()
        for args in ((), ("--gateway-patch", str(self.patch))):
            code, out = self.run_main(*args)
            self.assertEqual(code, 0, out)
            self.assertIn("already what this input generates (nothing written)", out)
            self.assertIn("already what this input generates (no patch written)", out)
            self.assertNotIn("THIS MOVES THE MONEY DIGEST", out)
        self.assertEqual(self.read(), done)
        self.assertFalse(self.patch.exists())

    def test_the_owners_step_forgotten_is_the_patch_again(self):
        """The constitution written, the gateway's patch not applied: a second run writes the patch and nothing else."""
        self.assertEqual(self.run_main("--gateway-patch", str(self.patch))[0], 0)
        first, done = self.patch.read_text(encoding="utf-8"), self.read()
        self.patch.unlink()
        code, out = self.run_main("--gateway-patch", str(self.patch))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.patch.read_text(encoding="utf-8"), first)
        self.assertEqual(self.read(), done)
        self.assertIn(f"{G.CONSTITUTION}: already what this input generates", out)

    def test_the_yearly_run_moves_the_list_and_the_digest_again(self):
        self.assertEqual(self.run_main("--gateway-patch", str(self.patch))[0], 0)
        self.apply()
        first = rules_of(self.read()[G.CONSTITUTION].decode())
        later = [s for s in self.names if s not in ("ZZAA", "ZZAB")] + ["ZZZX", "ZZZY", "ZZZZ"]
        code, out = self.run_main("--gateway-patch", str(self.patch), source=self.given(later, "next.json"))
        self.assertEqual(code, 0, out)
        self.assertIn("universe.stock: 520 -> 521 names (3 added, 2 removed)", out)
        self.apply()
        second = rules_of(self.read()[G.CONSTITUTION].decode())
        self.assertEqual(second["CONSTITUTION"]["equity_money"]["universe"]["stock"], sorted(later))
        self.assertNotEqual(second["PINNED_DIGEST"], first["PINNED_DIGEST"])
        self.assertEqual(ci.check_equity(self.root), [])
        self.assertEqual(self.run_main("--check", source=self.given(later, "next.json"))[0], 0)
        self.assertEqual(self.run_main("--check")[0], 1, "last year's file no longer generates the tree")

    def test_a_refused_input_writes_nothing(self):
        for names, why in ((invented(200), "the list has 200 names"), (self.names[:-1] + ["XLF"], "are ETFs"),
                           ([s for s in invented(521) if s != "JPM"], "lacks 1 of release E1's stocks")):
            code, out = self.run_main("--gateway-patch", str(self.patch), source=self.given(names, "bad.json"))
            self.assertEqual(code, 2)
            self.assertTrue(out.startswith("refused: "), out)
            self.assertIn(why, out)
            self.assertEqual(self.read(), self.was)
            self.assertFalse(self.patch.exists())
        code, out = self.run_main("--gateway-patch", str(self.patch), source=Path(self.dir.name) / "none.json")
        self.assertEqual((code, self.read()), (2, self.was))
        (self.root / G.GATEWAY).unlink()
        code, out = self.run_main("--gateway-patch", str(self.patch))
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("refused: "), out)

    def test_the_day_of_the_list_is_written_nowhere(self):
        code, out = self.run_main("--gateway-patch", str(self.patch))
        self.assertEqual(code, 0)
        for text in (out, self.patch.read_text(encoding="utf-8"),
                     (self.root / G.CONSTITUTION).read_text(encoding="utf-8")):
            self.assertNotIn(AS_OF, text)
            self.assertNotIn(AS_OF[:4], text.split(G.BEGIN)[1].split(G.END)[0] if G.BEGIN in text else "")


class TheTreeAsItStands(unittest.TestCase):
    """What is committed is release E1's 18 stocks or a list the generator wrote: never a hand edit, never a date."""

    def test_the_constitutions_list_is_e1s_or_generated(self):
        text = tree_text(G.CONSTITUTION)
        stocks = rules_of(text)["CONSTITUTION"]["equity_money"]["universe"]["stock"]
        if G.BEGIN not in text and G.END not in text:
            self.assertEqual(stocks, E1_STOCKS, "no generated block: the list is release E1's, in its order")
            return
        start, stop, indent = G._marked(text, G.BEGIN, G.END, G.CONSTITUTION)
        self.assertEqual(text[start:stop].split("\n"), G._block(stocks, indent),
                         "the block is the generator's, byte for byte")
        self.assertEqual(G.problems(stocks, keep=E1_STOCKS, etfs=E1_ETFS), [])
        self.assertEqual(stocks, sorted(stocks))
        self.assertEqual(G.constitution_text(text, stocks), text)
        self.assertIsNone(re.search(r"\d{4}-\d{2}-\d{2}|\b20\d\d\b", text[start:stop]))

    def test_the_gateways_list_is_e1s_or_generated(self):
        text = tree_text(G.GATEWAY)
        stocks = [s for s, k in G.gateway_pairs(text).items() if k == "stock"]
        if stocks == E1_STOCKS:
            return                      # release E1's list, in its order (with or without the markers around it)
        start, stop, indent = G._marked(text, G.GATEWAY_BEGIN, G.GATEWAY_END, G.GATEWAY)
        self.assertEqual(text[start:stop].split("\n"), G._gateway_block(stocks, indent))
        self.assertEqual(G.problems(stocks, keep=E1_STOCKS, etfs=E1_ETFS), [])
        self.assertEqual(G.gateway_text(text, stocks), text)
        self.assertIsNone(re.search(r"\d{4}-\d{2}-\d{2}|\b20\d\d\b", text[start:stop]))

    def test_e1s_universe_is_inside_the_constitutions_with_its_classes(self):
        """`league.equity.config.UNIVERSE` is an evidence module's constant (hashed into the equity identity and
        every ETF run): release E4 never changes it, and the constitution's universe may only grow around it."""
        universe = rules_of(tree_text(G.CONSTITUTION))["CONSTITUTION"]["equity_money"]["universe"]
        named = {s: k for k in ("etf", "stock") for s in universe[k]}
        self.assertEqual({s: named.get(s) for s in config.UNIVERSE}, config.UNIVERSE)
        self.assertEqual(universe["etf"], E1_ETFS, "the ETFs are not generated")
        self.assertEqual(len(config.UNIVERSE), 35)

    def test_no_identity_reads_a_file_of_this_package(self):
        """The universe moves the money digest and NOTHING ELSE: a tree that holds only the files the two identities
        hash (no constitution, no generator, no gateway, no league/xs, no league/ops) has the tree's identities."""
        from league.gym.driver import LEAGUE_FILES
        from league.swarm import evaluator

        hashed = {*LEAGUE_FILES, *evaluator.EQUITY_GYM_FILES, *evaluator.EQUITY_CALENDAR_FILES,
                  *(f"league/equity/{name}.py" for name in evaluator.EQUITY_EVIDENCE)}
        for folder in ("gym", "live"):
            hashed.update(p.relative_to(REPO).as_posix() for p in (REPO / "league" / folder).rglob("*.py"))
        for mine in (G.CONSTITUTION, "scripts/gen_universe.py", "league/ci.py", "league/ops/preopen.py", G.GATEWAY):
            self.assertNotIn(mine, hashed)
        with tempfile.TemporaryDirectory() as tmp:
            for rel in sorted(hashed):
                (Path(tmp) / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / rel, Path(tmp) / rel)
            self.assertEqual(evaluator.equity_fingerprint(Path(tmp)), evaluator.equity_fingerprint())
            self.assertEqual(evaluator.execution_fingerprint(Path(tmp)), evaluator.execution_fingerprint())


class ThePatchFile(unittest.TestCase):
    """league/swarm/e4_patches/I.md, package I's changes to files that existed before E4: every diff names a file of
    the tree; the constitution has NO diff (its list is generated from the House's file, never typed) and neither has
    any file of gateway/ (the gateway's half is a patch file in the captain's scratch: no builder edits gateway/)."""

    FILES = {"league/ci.py", "league/tests/test_ci.py", "league/ops/preopen.py", "docs/operations.md", "CHANGELOG.md",
             "league/tests/test_equity_money.py", "league/tests/test_constitution.py",
             "league/tests/test_live_long_single.py"}

    def test_every_diff_names_a_file_of_the_tree_and_none_types_the_universe(self):
        text = tree_text("league/swarm/e4_patches/I.md")
        named = re.findall(r"^diff --git a/(\S+) b/(\S+)$", text, re.M)
        self.assertGreaterEqual(len(named), len(self.FILES))
        for old, new in named:
            self.assertEqual(old, new)
            self.assertTrue((REPO / new).is_file(), new)
        self.assertEqual({new for _, new in named}, self.FILES)
        self.assertNotIn(G.CONSTITUTION, self.FILES)
        self.assertFalse([path for path in self.FILES if path.startswith("gateway/")])
        self.assertEqual(text.count("```diff\n"), len(named), "one diff a block")
        for heading in ("## Patch 16 (release R-E4a)",
                        "## Patch 15 (release R-E4b): THE UNIVERSE (moves the money digest; deployed separately)"):
            self.assertEqual(text.count(heading), 1, heading)
        self.assertIn("python3 scripts/gen_universe.py --from tradable.json --gateway-patch", text)


if __name__ == "__main__":
    unittest.main()
