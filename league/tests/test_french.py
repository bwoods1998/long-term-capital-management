"""THE FRENCH LIBRARY'S FACTORS ON THE HOUSE (release E4, package B; league/ops/french.py): the library's daily format
read line by line, THE SEAL (X13: a line of 2020 or 2021 is dropped before it is split or parsed; a line of 2025 on is
counted and written nowhere), the one file a factor file is written to, and the job's routes (a gateway data route
that does not exist today, then an operator's inbox) with "skipped, not an alarm" when there is none.

Every figure here is invented (a few made-up percent values on made-up days of every year from 2010 to 2026): no line
of the real library is in this file or is read by it."""

from __future__ import annotations

import datetime as dt
import json
import os
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from league.ops import french as FR
from league.ops.context import Context, GatewayError

YEARS = tuple(range(2010, 2027))
RESEARCH, MOMENTUM, REVERSAL = FR.FILES


class Tripwire(str):
    """A line that may only be asked for its first four characters: every other use of it (a split, a strip, a
    partition, an index past the fourth character, an iteration, a comparison, a length) raises. A parser that drops a
    line "unparsed" passes such a line untouched; one that splits it first fails here."""

    def __getattribute__(self, name):
        raise AssertionError(f"a dropped line was touched: .{name}")

    def __getitem__(self, key):
        if key != slice(None, 4, None):
            raise AssertionError(f"a dropped line was read past its year: [{key!r}]")
        return str.__getitem__(self, key)

    def _touched(self, *args, **kwargs):
        raise AssertionError("a dropped line was touched")

    __iter__ = __len__ = __contains__ = __eq__ = __ne__ = __lt__ = __le__ = __gt__ = __ge__ = _touched
    __add__ = __radd__ = __mul__ = __rmul__ = __mod__ = __rmod__ = __format__ = __str__ = __repr__ = _touched
    __hash__ = _touched


def value(year: int, k: int, column: int) -> str:
    """An invented percent figure, two decimals, as the library prints one."""
    return f"{((year * 7 + k * 3 + column * 5) % 61 - 30) / 20:8.2f}"


def day_lines(columns: int, years=YEARS, per_year: int = 3) -> list[tuple[int, str]]:
    """(year, line) of `per_year` invented days a year, in the library's shape: YYYYMMDD, then `columns` figures."""
    out = []
    for year in years:
        for k in range(per_year):
            day = dt.date(year, 1 + 4 * k, 5 + k)
            out.append((year, day.strftime("%Y%m%d") + "," + ",".join(value(year, k, c) for c in range(columns))))
    return out


def library(header: str, columns: int, *, years=YEARS, trip: bool = False, newline: str = "\n") -> list[str]:
    """One library file's lines: the preamble, the header (it begins with a comma), a line a day, a blank line and the
    copyright line. With `trip` every line of a dropped year is a `Tripwire`."""
    lines = ["This file was created by an invented program using an invented database." + newline,
             "The figures below are made up for a test and are no market's." + newline, newline, header + newline]
    for year, text in day_lines(columns, years):
        text += newline
        lines.append(Tripwire(text) if trip and str(year) in FR.DROPPED_YEARS else text)
    return lines + [newline, "Copyright 2026 nobody" + newline]


def research(**kw) -> list[str]:
    return library(",Mkt-RF,SMB,HML,RF", 4, **kw)


def years_of(days) -> set[int]:
    return {int(day[:4]) for day in days}


class ParseDropsTheReserve(unittest.TestCase):
    """SEAL X13: fed a synthetic file with every year, `parse` keeps no line of 2020 or 2021 and never splits or
    parses one."""

    def test_the_tripwire_would_see_a_parser_that_touches_a_dropped_line(self):
        line = Tripwire("20200102,    0.10,   -0.25,   -0.27,    0.009\n")
        self.assertEqual(line[:4], "2020")
        for touch in (lambda: line.split(","), lambda: line.strip(), lambda: line.partition(","), lambda: line[4:],
                      lambda: line[0], lambda: list(line), lambda: len(line), lambda: line == "x",
                      lambda: line.startswith("2020"), lambda: "0.10" in line, lambda: line + "", lambda: f"{line}"):
            with self.assertRaises(AssertionError):
                touch()

    def test_no_line_of_2020_or_2021_is_split_parsed_or_kept(self):
        out = FR.parse(research(trip=True))
        self.assertEqual(years_of(out["days"]), set(range(2010, 2020)) | {2022, 2023, 2024})
        self.assertEqual(years_of(out["sealed"]["days"]), {2025, 2026})
        self.assertEqual(out["dropped"], 6)
        for part in (out, out["sealed"]):
            self.assertEqual(set(part["factors"]), {"Mkt-RF", "SMB", "HML"})
            for values in part["factors"].values():
                self.assertEqual(len(values), len(part["days"]))
        text = json.dumps(out)
        for year in FR.DROPPED_YEARS:
            self.assertNotIn(f'"{year}-', text)

    def test_plain_lines_are_dropped_the_same_way(self):
        self.assertEqual(FR.parse(research()), FR.parse(research(trip=True)))
        self.assertEqual(FR.parse(research(newline="\r\n")), FR.parse(research()))
        # the same file without its reserve lines reads the same but for the count
        without = [line for line in research() if line[:4] not in FR.DROPPED_YEARS]
        self.assertEqual({**FR.parse(without), "dropped": 6}, FR.parse(research()))

    def test_every_line_of_the_dropped_years_is_dropped_wherever_it_stands(self):
        """Before the header and after the table's end too: the rule is the line's first four characters, nothing
        else."""
        lines = research(trip=True)
        lines.insert(1, Tripwire("2020 was the year this invented note is about\n"))
        lines.append(Tripwire("20210705,    1.00,    1.00,    1.00,    0.001\n"))
        out = FR.parse(lines)
        self.assertEqual(out["dropped"], 8)
        self.assertEqual(years_of(out["days"]), set(range(2010, 2020)) | {2022, 2023, 2024})

    def test_a_reserve_line_that_does_not_begin_with_its_year_refuses_the_file_before_it_is_split(self):
        class Indented(str):
            def split(self, *a, **k):
                raise AssertionError("the reserve line was split")

            def partition(self, *a, **k):
                raise AssertionError("the reserve line was partitioned")

            def strip(self, *a, **k):
                return Indented(str.strip(self, *a, **k))

        for year in FR.DROPPED_YEARS:
            lines = research()
            lines.insert(8, Indented(f"  {year}0102,    0.10,   -0.25,   -0.27,    0.009\n"))
            with self.assertRaisesRegex(ValueError, "does not begin with its year"):
                FR.parse(lines)

    def test_the_dropped_years_are_the_reserve_and_its_history_year(self):
        from league.xs import config as xs_config

        self.assertEqual(FR.DROPPED_YEARS, ("2020", "2021"))
        self.assertIn(2020, xs_config.RESERVE_YEARS)
        self.assertIn(2021, xs_config.HISTORY_YEARS)
        self.assertEqual(FR.SEALED_FROM, 2025)
        self.assertLess(max(xs_config.TRAIN_YEARS), FR.SEALED_FROM)


class TheLibrarysFormat(unittest.TestCase):
    def test_percent_figures_become_fractions_and_only_the_named_factors_are_kept(self):
        lines = ["an invented preamble\n", "\n", ",Mkt-RF,SMB,HML,RF\n",
                 "20190102,    0.10,   -0.25,   -0.27,    0.009\n",
                 "20190103,   -1.23,    2.00,    0.00,    0.009\n", "\n", "Copyright nobody\n"]
        out = FR.parse(lines)
        self.assertEqual(out["days"], ["2019-01-02", "2019-01-03"])
        self.assertEqual(out["factors"], {"Mkt-RF": [0.001, -0.0123], "SMB": [-0.0025, 0.02], "HML": [-0.0027, 0.0]})
        self.assertNotIn("RF", out["factors"])
        self.assertEqual(out["sealed"], {"days": [], "factors": {"Mkt-RF": [], "SMB": [], "HML": []}})
        self.assertEqual(out["dropped"], 0)

    def test_a_padded_header_and_the_librarys_missing_marks(self):
        lines = ["Missing data are indicated by -99.99 or -999.\n", "\n", ",Mom   \n", "20190102,    0.56\n",
                 "20190103,  -99.99\n", "20190104,    -999\n", "20190107,   -0.10\n"]
        out = FR.parse(lines)
        self.assertEqual(out["factors"], {"Mom": [0.0056, None, None, -0.001]})
        self.assertEqual(FR.parse([",ST_Rev\n", "20190102, 1.5\n"])["factors"], {"ST_Rev": [0.015]})

    def test_the_table_ends_at_its_first_blank_or_text_line(self):
        lines = [",Mkt-RF,SMB,HML,RF\n", "20190102,0.10,0.10,0.10,0.01\n", "\n", " Annual figures\n",
                 ",Mkt-RF,SMB,HML,RF\n", "20190103,9.99,9.99,9.99,0.01\n"]
        out = FR.parse(lines)
        self.assertEqual(out["days"], ["2019-01-02"])
        self.assertEqual(out["factors"]["Mkt-RF"], [0.001])

    def test_a_file_that_is_not_the_librarys_is_refused(self):
        head = ",Mkt-RF,SMB,HML,RF\n"
        cases = {
            "no header": ["20190102,0.1,0.1,0.1,0.1\n"],
            "none of the factors": [",A,B\n", "20190102,0.1,0.1\n"],
            "a factor twice": [",Mom,Mom\n", "20190102,0.1,0.1\n"],
            "fields": [head, "20190102,0.1,0.1,0.1\n"],
            "is not a day": [head, "20190231,0.1,0.1,0.1,0.1\n"],
            "does not come after": [head, "20190103,0.1,0.1,0.1,0.1\n", "20190102,0.1,0.1,0.1,0.1\n"],
            "the line before it": [head, "20190102,0.1,0.1,0.1,0.1\n", "20190102,0.1,0.1,0.1,0.1\n"],
            "not a number": [head, "20190102,0.1,x,0.1,0.1\n"],
            "is not a number": [head, "20190102,0.1,nan,0.1,0.1\n"],
            "the lines are text": [head.encode(), b"20190102,0.1,0.1,0.1,0.1\n"],
            "lines are text": [head, b"20200102,0.1,0.1,0.1,0.1\n"],
        }
        for why, lines in cases.items():
            with self.assertRaisesRegex(ValueError, why, msg=why):
                FR.parse(lines)

    def test_the_files_and_their_factors_cover_the_five(self):
        self.assertEqual(tuple(f for factors in FR.FILES.values() for f in factors), FR.FACTORS)
        self.assertEqual(FR.FACTORS, ("Mkt-RF", "SMB", "HML", "Mom", "ST_Rev"))


class WriteKeepsNoSealedDay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "equity-daily"

    def tearDown(self):
        self.tmp.cleanup()

    def test_one_file_a_name_owner_only_and_nothing_left_beside_it(self):
        path = FR.write(self.root, MOMENTUM, ["2019-01-02", "2019-01-03"], {"Mom": [0.0056, None]})
        self.assertEqual(path, self.root / "french" / f"{MOMENTUM}.json")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(sorted(p.name for p in path.parent.iterdir()), [path.name])
        self.assertEqual(json.loads(path.read_text()), {
            "version": FR.VERSION, "name": MOMENTUM, "unit": "fraction", "days": ["2019-01-02", "2019-01-03"],
            "factors": {"Mom": [0.0056, None]}, "rows": 2, "first": "2019-01-02", "last": "2019-01-03"})
        # written again, it is replaced whole
        FR.write(self.root, MOMENTUM, ["2022-01-03"], {"Mom": [0.01]})
        self.assertEqual(json.loads(path.read_text())["days"], ["2022-01-03"])

    def test_a_day_the_file_may_not_hold_is_refused_and_nothing_is_written(self):
        for day in ("2020-03-02", "2021-03-02", "2025-01-02", "2026-10-09"):
            with self.assertRaisesRegex(ValueError, "never written"):
                FR.write(self.root, MOMENTUM, ["2019-12-31", day], {"Mom": [0.1, 0.2]})
        for name, days, factors, why in (
                ("a/b", ["2019-01-02"], {"Mom": [0.1]}, "plain file name"),
                ("../x", ["2019-01-02"], {"Mom": [0.1]}, "plain file name"),
                (".hidden", ["2019-01-02"], {"Mom": [0.1]}, "plain file name"),
                (MOMENTUM, [], {"Mom": []}, "no day"),
                (MOMENTUM, ["2019-01-02"], {}, "no factor"),
                (MOMENTUM, ["2019-01-02"], {"Mom": [0.1, 0.2]}, "values for"),
                (MOMENTUM, ["2019-01-03", "2019-01-02"], {"Mom": [0.1, 0.2]}, "do not ascend")):
            with self.assertRaisesRegex(ValueError, why):
                FR.write(self.root, name, days, factors)
        self.assertFalse((self.root / "french").exists())


class Gateway:
    """The House's gateway as the job meets it: every path a 404 unless the test gave it an answer."""

    def __init__(self, answers=None):
        self.answers = dict(answers or {})
        self.calls: list[str] = []

    def get(self, path, params=None):
        self.calls.append(path)
        if path in self.answers:
            return self.answers[path]
        raise GatewayError(f"GET {path}: HTTP 404 no such route", status=404)


class TheJob(unittest.TestCase):
    NOW = 1_800_000_000.0

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        self.root = self.state / FR.STORE_DIR
        self.inbox = self.root / FR.DIR / FR.INBOX
        self.gateway = Gateway()
        self.ctx = Context("french", root=self.state, due_at=self.NOW, clock=lambda: self.NOW, gateway=self.gateway,
                           config={}, settings_value={})
        quiet = mock.patch("league.xs.config.quiet", return_value=None)
        self.quiet = quiet.start()
        self.addCleanup(quiet.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def place(self, name: str, lines) -> Path:
        self.inbox.mkdir(parents=True, exist_ok=True)
        path = self.inbox / name
        path.write_text("".join(lines), encoding="latin-1")
        return path

    def written(self) -> dict[str, dict]:
        folder = self.root / FR.DIR
        return {p.stem: json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))} if folder.exists() else {}

    def test_it_asks_the_quiet_windows_first_with_its_own_wall(self):
        self.place(f"{RESEARCH}.csv", research())
        self.quiet.return_value = "inside the close wall"
        self.assertEqual(FR.run(self.ctx), {"status": "skipped", "why": "inside the close wall"})
        self.quiet.assert_called_once_with(self.NOW, FR.WALL_S)
        self.assertEqual((FR.WALL_S, self.gateway.calls, self.written(), self.ctx.alerts), (300, [], {}, []))
        self.assertTrue((self.inbox / f"{RESEARCH}.csv").exists())

    def test_quiet_windows_it_cannot_read_stop_it_and_say_so(self):
        self.quiet.side_effect = RuntimeError("no calendar")
        out = FR.run(self.ctx)
        self.assertEqual(out["status"], "skipped")
        self.assertIn("could not be read", out["why"])
        self.assertEqual(self.gateway.calls, [])
        self.assertEqual([a["level"] for a in self.ctx.alerts], ["warning"])

    def test_with_no_route_it_is_skipped_and_raises_no_alarm(self):
        self.assertEqual(FR.run(self.ctx), {"status": "skipped", "why": FR.SKIPPED})
        self.assertEqual(FR.SKIPPED, "no route to the French library from the House")
        self.assertEqual(self.gateway.calls, [FR.ROUTES[0] + stem for stem in FR.FILES])
        self.assertEqual((self.ctx.alerts, self.written()), ([], {}))
        self.assertEqual(FR.ROUTES, ("/v1/data/french/", "french/inbox"))
        self.assertEqual(self.inbox, self.root / FR.ROUTES[1])

    def test_an_inbox_file_is_filtered_kept_and_removed(self):
        placed = self.place(f"{RESEARCH}.CSV", research())
        out = FR.run(self.ctx)
        self.assertEqual(out, {"ok": True, "missing": [MOMENTUM, REVERSAL], "files": {RESEARCH: {
            "route": "inbox", "days": 39, "first": "2010-01-05", "last": "2024-09-07", "dropped": 6, "sealed": 6}}})
        kept = self.written()
        self.assertEqual(list(kept), [RESEARCH])
        self.assertEqual(years_of(kept[RESEARCH]["days"]), set(range(2010, 2020)) | {2022, 2023, 2024})
        self.assertEqual(set(kept[RESEARCH]["factors"]), {"Mkt-RF", "SMB", "HML"})
        self.assertEqual(kept[RESEARCH]["factors"], {k: v for k, v in FR.parse(research())["factors"].items()})
        self.assertFalse(placed.exists(), "the inbox file holds every year and must not stay")
        self.assertEqual(self.ctx.alerts, [])
        self.assertTrue(all(isinstance(v, (int, str)) for row in out["files"].values() for v in row.values()),
                        "the receipt carries counts and days, never a factor value")

    def test_no_dropped_and_no_sealed_day_is_anywhere_on_disk_after_the_run(self):
        for stem, lines in ((RESEARCH, research()), (MOMENTUM, library(",Mom   ", 1)),
                            (REVERSAL, library(",ST_Rev", 1))):
            self.place(f"{stem}.csv", lines)
        out = FR.run(self.ctx)
        self.assertEqual((out["ok"], out["missing"], sorted(out["files"])), (True, [], sorted(FR.FILES)))
        files = [p for p in self.state.rglob("*") if p.is_file()]
        self.assertEqual(sorted(p.name for p in files), sorted(f"{stem}.json" for stem in FR.FILES))
        for path in files:
            text = path.read_text()
            for year in (2020, 2021, 2025, 2026):
                self.assertNotIn(f"{year}-", text, f"{path.name} holds a day of {year}")
                self.assertNotIn(f"{year}0", text)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_the_librarys_own_zip_is_read_as_a_stream(self):
        self.inbox.mkdir(parents=True)
        placed = self.inbox / f"{MOMENTUM}_CSV.zip"
        with zipfile.ZipFile(placed, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{MOMENTUM}.CSV", "".join(library(",Mom   ", 1)))
        out = FR.run(self.ctx)
        self.assertEqual(out["files"][MOMENTUM], {"route": "inbox", "days": 39, "first": "2010-01-05",
                                                  "last": "2024-09-07", "dropped": 6, "sealed": 6})
        self.assertEqual(self.written()[MOMENTUM]["factors"], FR.parse(library(",Mom   ", 1))["factors"])
        self.assertEqual(sorted(p.name for p in self.root.rglob("*") if p.is_file()), [f"{MOMENTUM}.json"])
        self.assertFalse(placed.exists())

    def test_a_zip_that_is_not_the_librarys_is_a_failed_receipt_and_stays(self):
        self.inbox.mkdir(parents=True)
        placed = self.inbox / f"{MOMENTUM}.zip"
        with zipfile.ZipFile(placed, "w") as archive:
            archive.writestr("a.csv", "x")
            archive.writestr("b.csv", "y")
        out = FR.run(self.ctx)
        self.assertEqual((out["status"], out["ok"], out["files"]), ("failed", False, {}))
        self.assertIn("the zip holds 2 files", out["error"])
        self.assertTrue(placed.exists())
        self.assertEqual(self.written(), {})

    def test_a_file_that_cannot_be_read_fails_alone_and_is_left_in_the_inbox(self):
        bad = self.place(f"{RESEARCH}.csv", [",Mkt-RF,SMB,HML,RF\n", "20190102,0.1,oops,0.1,0.1\n"])
        self.place(f"{REVERSAL}.txt", library(",ST_Rev", 1))
        out = FR.run(self.ctx)
        self.assertEqual((out["status"], out["ok"], out["missing"]), ("failed", False, [MOMENTUM]))
        self.assertEqual(list(out["problems"]), [RESEARCH])
        self.assertIn("not a number", out["error"])
        self.assertEqual(list(out["files"]), [REVERSAL])
        self.assertEqual(list(self.written()), [REVERSAL])
        self.assertTrue(bad.exists())

    def test_a_file_without_its_factor_or_without_a_day_it_may_keep_is_not_written(self):
        self.place(f"{MOMENTUM}.csv", library(",ST_Rev", 1))                   # the wrong file under the name
        self.place(f"{REVERSAL}.csv", library(",ST_Rev", 1, years=(2020, 2021, 2025)))
        out = FR.run(self.ctx)
        self.assertEqual(out["status"], "failed")
        self.assertIn("the file lacks Mom", out["problems"][MOMENTUM])
        self.assertIn("holds no day", out["problems"][REVERSAL])
        self.assertEqual(self.written(), {})

    def test_the_gateways_route_is_read_first_when_it_answers(self):
        self.gateway.answers[FR.ROUTES[0] + REVERSAL] = {"text": "".join(library(",ST_Rev", 1))}
        placed = self.place(f"{REVERSAL}.csv", library(",ST_Rev", 1, years=(2019,)))
        out = FR.run(self.ctx)
        self.assertEqual(out["files"][REVERSAL]["route"], "gateway")
        self.assertEqual(out["files"][REVERSAL]["days"], 39)
        self.assertTrue(placed.exists(), "an inbox file the run did not read is not removed")
        # an answer in another shape is no answer: the inbox is read
        self.gateway.answers[FR.ROUTES[0] + REVERSAL] = {"zip": "UEsDB..."}
        out = FR.run(self.ctx)
        self.assertEqual(out["files"][REVERSAL], {"route": "inbox", "days": 3, "first": "2019-01-05",
                                                  "last": "2019-09-07", "dropped": 0, "sealed": 0})
        self.assertFalse(placed.exists())

    def test_an_inbox_file_it_cannot_remove_is_a_warning(self):
        self.place(f"{MOMENTUM}.csv", library(",Mom", 1))
        with mock.patch.object(Path, "unlink", side_effect=PermissionError("read-only")):
            out = FR.run(self.ctx)
        self.assertTrue(out["ok"])
        self.assertEqual([a["level"] for a in self.ctx.alerts], ["warning"])
        self.assertIn("remove it by hand", self.ctx.alerts[0]["text"])

    def test_the_inbox_names_are_the_librarys_and_case_blind(self):
        self.assertEqual(FR.inbox(self.root), {})
        self.place(f"{RESEARCH.upper()}.TXT", ["x"])
        self.place(f"{MOMENTUM}_csv.ZIP", ["x"])
        self.place("something_else.csv", ["x"])
        found = FR.inbox(self.root)
        self.assertEqual(sorted(found), sorted([RESEARCH, MOMENTUM]))
        self.assertEqual(found[RESEARCH].name, f"{RESEARCH.upper()}.TXT")

    def test_the_state_directory_is_the_equity_lanes(self):
        from league.ops import equity_data

        self.assertEqual(FR.STORE_DIR, equity_data.STORE_DIR)
        self.assertEqual(os.fspath(self.root), os.fspath(self.state / "equity-daily"))


if __name__ == "__main__":
    unittest.main()
