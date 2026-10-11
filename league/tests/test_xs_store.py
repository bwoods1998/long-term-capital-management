"""The panel store (league/xs/store.py) and the lane's calendar rules (league/xs/config.py).

C0 FIRST (it merges first and alone, because package A's jobs are built on it): `write_panel` (the layout, atomic,
the manifest last, the 2020 refusal), D19's coverage and verdict, D4's valid bar, the quiet windows and D9's schedule.
Then the reader: the windows and E1's capability, the slices, D8's ids, D18's halves, the class of the month, the
universe, and seal X4 (`NoReserveSessionIsEverRun`).

Every panel here is written by hand through `write_panel` or by `league.xs.synth`: no market data.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity.store import nyse_sessions, ordinal
from league.xs import XS_STORE_VERSION, config, store

D = dt.date
REF = len(config.REF)


def sessions(first: dt.date, last: dt.date) -> list[tuple[dt.date, bool]]:
    """The panel's own calendar: every NYSE session of [first, last], the reserve left out."""
    return [(d, e) for d, e in nyse_sessions(first, last) if d.year not in config.RESERVE_YEARS]


def hand_panel(first: dt.date = D(2024, 1, 2), last: dt.date = D(2024, 1, 31), members: int = 3) -> dict:
    """The keyword arguments of one small valid `write_panel` call: every column has a bar every session, every member
    column is a member and tradable on every session."""
    rows = sessions(first, last)
    n, m = len(rows), REF + members
    rng = np.random.default_rng(11)
    close = 50.0 + 100.0 * rng.random((n, m))
    raw = np.stack([close * 0.99, close * 1.01, close * 0.98, close, np.full((n, m), 1_000_000.0)], axis=2)
    member = np.zeros((n, m), dtype=bool)
    member[:, REF:] = True
    return {"days": [d for d, _ in rows], "early": [e for _, e in rows],
            "aids": [*store.REF_AIDS, *range(store.FIRST_MEMBER_AID, store.FIRST_MEMBER_AID + members)],
            "raw": raw, "adj": raw[:, :, :4].copy(), "member": member, "tradable": member.copy(),
            "hs": np.full((m, 2), 0.0003), "fetched_through": rows[-1][0],
            "vintage": {store.FIRST_MEMBER_AID: rows[-1][0]}, "audit": {"jumps": 0}}


class TheWriter(unittest.TestCase):
    """C0: `write_panel`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "equity-daily"

    def tearDown(self):
        self.tmp.cleanup()

    def test_it_writes_the_layout_and_the_manifest_names_every_files_sha(self):
        args = hand_panel()
        manifest = store.write_panel(self.root, **args)
        folder = self.root / store.PANEL_DIR
        self.assertEqual(sorted(p.name for p in folder.iterdir()),
                         sorted([*store.PANEL_FILES, store.VERSION_FILE, store.PANEL_MANIFEST]))
        self.assertEqual((folder / store.VERSION_FILE).read_text().strip(), XS_STORE_VERSION)
        self.assertEqual(json.loads((folder / store.PANEL_MANIFEST).read_text()), manifest)
        self.assertEqual(sorted(manifest["sha256"]), sorted(store.PANEL_FILES))
        for name, sha in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256((folder / name).read_bytes()).hexdigest(), sha, name)
        self.assertEqual((manifest["version"], manifest["days"], manifest["assets"]),
                         (XS_STORE_VERSION, len(args["days"]), REF + 3))
        self.assertEqual((manifest["first"], manifest["fetched_through"]),
                         (args["days"][0].isoformat(), args["days"][-1].isoformat()))
        for key in ("full_at", "vintage", "coverage", "train_years_ok", "verdict", "vanished", "audit", "i6",
                    "revisions", "hs_share", "live_from"):
            self.assertIn(key, manifest)
        self.assertEqual(manifest["vintage"], {"100": args["days"][-1].isoformat()})
        self.assertEqual(manifest["audit"], {"jumps": 0})

    def test_the_arrays_come_back_as_the_layout_says(self):
        args = hand_panel()
        store.write_panel(self.root, **args)
        folder = self.root / store.PANEL_DIR
        loaded = {name: np.load(folder / name, allow_pickle=False) for name in store.PANEL_FILES}
        n, m = len(args["days"]), REF + 3
        self.assertEqual({name: (a.dtype.str, a.shape) for name, a in loaded.items()}, {
            "days.npy": ("<i4", (n,)), "early.npy": ("|b1", (n,)), "aids.npy": ("<i4", (m,)),
            "raw.npy": ("<f8", (n, m, 5)), "adj.npy": ("<f8", (n, m, 4)), "member.npy": ("|b1", (n, m)),
            "tradable.npy": ("|b1", (n, m)), "hs.npy": ("<f8", (m, 2))})
        self.assertEqual(loaded["days.npy"].tolist(), [ordinal(d) for d in args["days"]])
        self.assertEqual(loaded["aids.npy"].tolist()[:REF], list(range(1, REF + 1)))
        self.assertTrue(np.array_equal(loaded["raw.npy"], args["raw"]))
        self.assertTrue(np.array_equal(loaded["adj.npy"], args["adj"]))

    def test_everything_is_private_to_the_house(self):
        store.write_panel(self.root, **hand_panel())
        folder = self.root / store.PANEL_DIR
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        for path in folder.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)

    def test_the_same_panel_is_the_same_bytes(self):
        first = store.write_panel(self.root, **hand_panel())
        again = store.write_panel(self.root, **hand_panel())
        self.assertEqual(first, again)
        other = store.write_panel(Path(self.tmp.name) / "other", **hand_panel())
        self.assertEqual(first["sha256"], other["sha256"])

    def test_the_manifest_is_written_last_and_no_temporary_file_is_left(self):
        written: list[str] = []
        arrays, texts = store._atomic_array, store._atomic_bytes

        def array(path, value):
            written.append(path.name)
            return arrays(path, value)

        def text(path, data):
            written.append(path.name)
            return texts(path, data)

        with mock.patch.object(store, "_atomic_array", array), mock.patch.object(store, "_atomic_bytes", text):
            store.write_panel(self.root, **hand_panel())
        self.assertEqual(written[-1], store.PANEL_MANIFEST)
        self.assertEqual(sorted(written[:-1]), sorted([*store.PANEL_FILES, store.VERSION_FILE]))
        self.assertFalse([p.name for p in (self.root / store.PANEL_DIR).iterdir() if p.name.endswith(".tmp")])

    def test_a_writer_that_dies_leaves_the_old_manifest_and_no_half_file(self):
        """Every file goes to a temporary name first: a write that fails changes no file a reader opens."""
        before = store.write_panel(self.root, **hand_panel())
        changed = hand_panel()
        changed["raw"] = changed["raw"] * 2.0

        def dies(handle, array, **kwargs):
            handle.write(b"half a file")
            raise OSError("the disk is full")

        with mock.patch.object(np.lib.format, "write_array", dies), self.assertRaises(OSError):
            store.write_panel(self.root, **changed)
        folder = self.root / store.PANEL_DIR
        self.assertEqual(json.loads((folder / store.PANEL_MANIFEST).read_text()), before)
        for name, sha in before["sha256"].items():
            self.assertEqual(hashlib.sha256((folder / name).read_bytes()).hexdigest(), sha, name)
        self.assertFalse([p.name for p in folder.iterdir() if p.name.endswith(".tmp")])

    def test_it_refuses_a_2020_day(self):
        """Seal X4's writer half: no 2020 row is ever in the panel store."""
        for first, last in ((D(2019, 12, 2), D(2020, 1, 3)), (D(2020, 6, 1), D(2020, 6, 30)),
                            (D(2020, 12, 1), D(2021, 1, 29))):
            rows = nyse_sessions(first, last)
            args = hand_panel()
            n = len(rows)
            args.update(days=[d for d, _ in rows], early=[e for _, e in rows], fetched_through=rows[-1][0],
                        raw=np.resize(args["raw"], (n, REF + 3, 5)), adj=np.resize(args["adj"], (n, REF + 3, 4)),
                        member=np.zeros((n, REF + 3), dtype=bool), tradable=np.zeros((n, REF + 3), dtype=bool))
            with self.assertRaises(ValueError) as caught:
                store.write_panel(self.root, **args)
            self.assertIn("2020 is never in the panel store", str(caught.exception))
        self.assertFalse(self.root.exists(), "a refused panel writes nothing")

    def test_the_two_spans_join_across_the_reserve(self):
        """The store's days are the sessions of span A and span B: 2019's last session is followed by 2021's first."""
        args = hand_panel(D(2019, 12, 2), D(2021, 1, 29))
        self.assertNotIn(2020, {d.year for d in args["days"]})
        manifest = store.write_panel(self.root, **args)
        self.assertEqual(manifest["days"], len(sessions(D(2019, 12, 2), D(2021, 1, 29))))

    def refused(self, why: str, **changes):
        args = hand_panel()
        args.update(changes)
        with self.assertRaises(ValueError, msg=why) as caught:
            store.write_panel(self.root, **args)
        self.assertFalse(self.root.exists(), f"{why}: a refused panel writes nothing")
        return str(caught.exception)

    def test_it_refuses_days_that_are_not_the_calendars(self):
        good = hand_panel()
        days, early = good["days"], good["early"]
        self.refused("descending", days=days[::-1], early=early[::-1])
        self.refused("a session missing", days=days[:5] + days[6:], early=early[:5] + early[6:],
                     raw=np.delete(good["raw"], 5, axis=0), adj=np.delete(good["adj"], 5, axis=0),
                     member=np.delete(good["member"], 5, axis=0), tradable=np.delete(good["tradable"], 5, axis=0))
        self.assertIn("2024-01-06 is no session",
                      self.refused("a Saturday", days=[*days[:4], D(2024, 1, 6), *days[4:]],
                                   early=[*early[:4], False, *early[4:]]))
        self.refused("no day", days=[], early=[])
        flipped = list(early)
        flipped[3] = not flipped[3]
        self.assertIn("early", self.refused("a half day the calendar does not have", early=flipped))
        self.assertIn("spans", self.refused("before the store's first span", days=[D(2015, 12, 31)], early=[False],
                                            fetched_through=D(2015, 12, 31)))

    def test_it_refuses_a_fetch_day_that_is_not_the_last_sessions(self):
        days = hand_panel()["days"]
        self.refused("before the last row", fetched_through=days[-2])
        self.assertIn("fetched_through", self.refused("a session after the last row", fetched_through=D(2024, 2, 1)))
        # a closed day after the last session is the same fetch (a job run on a Saturday)
        args = hand_panel(D(2024, 1, 2), D(2024, 2, 2))
        args["fetched_through"] = D(2024, 2, 4)
        self.assertEqual(store.write_panel(self.root, **args)["fetched_through"], "2024-02-02")

    def test_it_refuses_aids_that_do_not_put_ref_first(self):
        members = [100, 101, 102]
        self.assertIn("REF", self.refused("no REF", aids=[*range(2, REF + 2), *members]))
        self.refused("REF out of order", aids=[2, 1, *range(3, REF + 1), *members])
        self.refused("a member under 100", aids=[*store.REF_AIDS, 50, 101, 102])
        self.refused("members not ascending", aids=[*store.REF_AIDS, 101, 100, 102])
        self.refused("a member twice", aids=[*store.REF_AIDS, 100, 100, 102])
        self.refused("not whole numbers", aids=[*map(float, store.REF_AIDS), 100.0, 101.0, 102.0])

    def test_it_refuses_arrays_that_do_not_agree(self):
        good = hand_panel()
        n, m = good["raw"].shape[:2]
        for name, bad in (("raw", good["raw"][:-1]), ("raw", good["raw"][:, :, :4]), ("adj", good["adj"][:, :-1]),
                          ("member", good["member"][:, :-1]), ("tradable", good["tradable"][:-1]),
                          ("hs", good["hs"][:-1]), ("hs", np.full((m, 3), 0.0003))):
            self.assertIn(name, self.refused(f"{name} {bad.shape}", **{name: bad}))
        self.assertIn("bool", self.refused("member as numbers", member=good["member"].astype(np.float64)))
        self.assertIn("bool", self.refused("tradable as numbers", tradable=good["tradable"].astype(np.int8)))
        infinite = good["raw"].copy()
        infinite[2, REF, 3] = np.inf
        self.refused("an infinite price", raw=infinite)
        infinite = good["adj"].copy()
        infinite[2, REF, 0] = -np.inf
        self.refused("an infinite adjusted price", adj=infinite)
        member = good["member"].copy()
        member[4, 0] = True
        self.assertIn("REF", self.refused("SPY as a member", member=member))
        for value in (np.nan, -0.0001, 1.0, np.inf):
            hs = good["hs"].copy()
            hs[1, 1] = value
            self.refused(f"a half-spread of {value}", hs=hs)

    def test_it_refuses_facts_it_cannot_read(self):
        self.refused("an unknown aid's vintage", vintage={999: D(2024, 1, 31)})
        self.refused("a vintage that is no day", vintage={100: "soon"})
        self.refused("a masked list of another length", masked=[False] * 3)
        self.refused("a coverage block without a verdict", coverage={"coverage": {}, "train_years_ok": []})
        self.refused("a verdict outside the three", coverage={"coverage": {}, "train_years_ok": [], "verdict": "fine"})
        self.refused("a vanished aid the panel lacks", vanished=[999])
        self.refused("a negative revisions count", revisions=-1)
        self.refused("an hs_share outside [0, 1]", hs_share=1.5)
        self.refused("a live_from that is no day", live_from="later")

    def test_the_jobs_facts_are_kept_as_given(self):
        block = {"coverage": {"2024": {"member_days": 10, "with_bar": 10, "share": 1.0}}, "train_years_ok": [2024],
                 "verdict": "low_coverage"}
        manifest = store.write_panel(self.root, **hand_panel(), coverage=block, vanished=[101], full_at=D(2024, 1, 27),
                                     revisions=3, hs_share=0.5, live_from="2024-01-16", i6={"equal": True})
        self.assertEqual((manifest["coverage"], manifest["train_years_ok"], manifest["verdict"]),
                         (block["coverage"], [2024], "low_coverage"))
        self.assertEqual((manifest["vanished"], manifest["full_at"], manifest["revisions"], manifest["hs_share"],
                          manifest["live_from"], manifest["i6"]),
                         ([101], "2024-01-27", 3, 0.5, "2024-01-16", {"equal": True}))

    def test_without_them_the_manifest_still_has_its_verdict(self):
        """A manifest is never without D19's block: with no block handed in it is computed here, and a store that
        does not hold the Train years reads "insufficient" (fail closed), never "ok"."""
        args = hand_panel()
        manifest = store.write_panel(self.root, **args)
        own = store.coverage(args["member"], args["raw"], args["days"])
        self.assertEqual((manifest["coverage"], manifest["train_years_ok"], manifest["verdict"]),
                         (own["coverage"], own["train_years_ok"], own["verdict"]))
        self.assertEqual(manifest["coverage"]["2024"]["share"], 1.0)
        self.assertEqual((manifest["train_years_ok"], manifest["verdict"]), ([2024], "insufficient"))
        self.assertEqual((manifest["vanished"], manifest["hs_share"], manifest["live_from"], manifest["i6"],
                          manifest["full_at"], manifest["revisions"]), ([], None, None, None, None, 0))

    def test_a_name_whose_bars_end_while_it_is_a_member_is_listed_as_vanished(self):
        args = hand_panel()
        raw = args["raw"]
        raw[-config.VANISH_SESSIONS:, REF, :] = np.nan            # aid 100: three member sessions with no bar
        raw[-(config.VANISH_SESSIONS - 1):, REF + 1, :] = np.nan   # aid 101: two (not yet)
        raw[:, REF + 2, :] = np.nan                                # aid 102: no bar at all (masked, never held)
        self.assertEqual(store.write_panel(self.root, **args)["vanished"], [100])


class ValidBars(unittest.TestCase):
    """D4: a valid bar is a raw close above 0 with a raw volume above 0."""

    def test_a_flat_bar_of_volume_zero_is_no_bar(self):
        raw = np.array([[10.0, 11.0, 9.0, 10.5, 1000.0],      # a bar
                        [10.5, 10.5, 10.5, 10.5, 0.0],        # the vendor's bar for a session without a trade
                        [np.nan] * 5,                         # no row
                        [10.0, 11.0, 9.0, 0.0, 1000.0],       # a close of zero
                        [10.0, 11.0, 9.0, 10.5, np.nan],      # no volume
                        [10.0, 11.0, 9.0, -1.0, 1000.0]])
        self.assertEqual(store.valid_bars(raw).tolist(), [True, False, False, False, False, False])
        self.assertEqual(store.valid_bars(raw.reshape(2, 3, 5)).shape, (2, 3))


class Coverage(unittest.TestCase):
    """D19: coverage[y] = the member-days of y with a valid bar of an unmasked asset / the member-days of y."""

    YEARS = (2017, 2018, 2019, 2022, 2023, 2024, 2025, 2026)

    def panel(self, missing: dict[int, int] | None = None, rows: int = 100):
        """`rows` sessions a year of `YEARS`, two member assets; `missing[year]` member-days of asset 0 have no bar."""
        days, member, raw = [], [], []
        for year in self.YEARS:
            own = [d for d, _ in nyse_sessions(D(year, 1, 1), D(year, 12, 31))][:rows]
            days += own
            for i, _ in enumerate(own):
                member.append([True, True])
                bar = [10.0, 10.0, 10.0, 10.0, 500.0]
                raw.append([[np.nan] * 5 if i < (missing or {}).get(year, 0) else bar, bar])
        return np.array(member), np.array(raw), days

    def test_the_formula_by_hand(self):
        member, raw, days = self.panel({2018: 10, 2025: 1})
        member[3, 1] = False                    # one day of 2017 the second asset is no member: out of both counts
        raw[4, 1, 4] = 0.0                      # one day of 2017 it has a flat volume-0 bar: a member-day with no bar
        block = store.coverage(member, raw, days)
        self.assertEqual(block["coverage"]["2017"], {"member_days": 199, "with_bar": 198, "share": 198 / 199})
        self.assertEqual(block["coverage"]["2018"], {"member_days": 200, "with_bar": 190, "share": 0.95})
        self.assertEqual(block["coverage"]["2025"], {"member_days": 200, "with_bar": 199, "share": 0.995})
        self.assertEqual(sorted(block["coverage"]), [str(y) for y in self.YEARS])
        self.assertEqual(block["train_years_ok"], [2017, 2019, 2022, 2023, 2024])

    def test_the_verdict(self):
        cases = (({}, "ok"), ({2018: 5}, "ok"),                           # 97.5% is above the floor
                 ({2018: 6}, "ok"), ({2018: 7}, "low_coverage"),          # 97.0% holds it, 96.5% does not
                 ({2018: 7, 2023: 7}, "insufficient"),                    # two Train years below
                 ({2025: 7}, "insufficient"), ({2026: 7}, "insufficient"),  # a judged year below, whatever Train reads
                 ({2018: 7, 2026: 7}, "insufficient"))
        for missing, verdict in cases:
            with self.subTest(missing=missing):
                self.assertEqual(store.coverage(*self.panel(missing))["verdict"], verdict)

    def test_a_year_the_store_does_not_hold_is_not_at_the_floor(self):
        member, raw, days = self.panel()
        keep = np.array([d.year != 2019 for d in days])
        block = store.coverage(member[keep], raw[keep], [d for d in days if d.year != 2019])
        self.assertEqual((block["train_years_ok"], block["verdict"]), ([2017, 2018, 2022, 2023, 2024], "low_coverage"))
        keep = np.array([d.year != 2026 for d in days])
        self.assertEqual(store.coverage(member[keep], raw[keep], [d for d in days if d.year != 2026])["verdict"],
                         "insufficient")
        none = np.zeros_like(member)
        self.assertIsNone(store.coverage(none, raw, days)["coverage"]["2017"]["share"])
        self.assertEqual(store.coverage(none, raw, days)["verdict"], "insufficient")

    def test_a_masked_assets_member_days_count_below_the_line_only(self):
        member, raw, days = self.panel()
        block = store.coverage(member, raw, days, masked=[True, False])
        self.assertEqual(block["coverage"]["2017"], {"member_days": 200, "with_bar": 100, "share": 0.5})
        self.assertEqual(block["verdict"], "insufficient")

    def test_the_floor_only_tightens(self):
        member, raw, days = self.panel({2018: 5})
        self.assertEqual(store.coverage(member, raw, days, floor=0.98)["train_years_ok"], [2017, 2019, 2022, 2023, 2024])
        for floor in (0.9, 1.01, float("nan")):
            with self.assertRaises(ValueError):
                store.coverage(member, raw, days, floor=floor)
        with self.assertRaises(ValueError):
            store.coverage(member[:-1], raw, days)
        with self.assertRaises(ValueError):
            store.coverage(member, raw, days, masked=[True])
        self.assertEqual((store.COVERAGE_MIN, store.JUDGED_YEARS), (0.97, (2025, 2026)))


class QuietWindows(unittest.TestCase):
    """E4-SPEC 13: no E4 job and no panel Train run may be RUNNING at a wall."""

    @staticmethod
    def at(day: dt.date, hour: int, minute: int, second: int = 0) -> float:
        from ltcm.data import NEW_YORK

        return dt.datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=NEW_YORK).timestamp()

    def test_the_walls(self):
        self.assertEqual(config.WALLS_ET, (("09:25", "09:45"), ("15:50", "16:35")))
        monday = D(2026, 10, 12)
        for hour, minute, need, free in ((9, 0, 60, True), (9, 24, 59, True), (9, 24, 60, False), (9, 25, 0, False),
                                         (9, 30, 1, False), (9, 45, 0, False), (9, 45, 1, True, ), (12, 0, 600, True),
                                         (15, 49, 59, True), (15, 50, 0, False), (16, 20, 5, False),
                                         (16, 35, 0, False), (16, 35, 1, True), (20, 0, 3300, True)):
            second = 1 if (hour, minute, need) in ((9, 45, 1), (16, 35, 1)) else 0
            why = config.quiet(self.at(monday, hour, minute, second), need)
            self.assertEqual(why is None, free, f"{hour:02d}:{minute:02d}:{second:02d} + {need} s: {why}")

    def test_a_start_that_could_still_be_running_at_a_wall_is_refused(self):
        """Not only a start inside a wall: `equity_panel` (55 minutes) never starts between 08:30 and 09:45."""
        monday = D(2026, 10, 12)
        self.assertIsNone(config.quiet(self.at(monday, 8, 29, 59), 3300))
        why = config.quiet(self.at(monday, 8, 30), 3300)
        self.assertIn("09:25-09:45 ET on 2026-10-12", why)
        self.assertIn("3300 s", why)
        self.assertIsNotNone(config.quiet(self.at(monday, 14, 55), 3300))
        self.assertIsNone(config.quiet(self.at(monday, 14, 54, 59), 3300))
        self.assertIsNone(config.quiet(self.at(monday, 9, 46), 3300))
        # a need that spans the night meets the next session's wall
        self.assertIn("2026-10-13", config.quiet(self.at(monday, 17, 0), 17 * 3600))

    def test_only_on_a_session(self):
        for closed in (D(2026, 10, 10), D(2026, 10, 11), D(2026, 12, 25), D(2026, 7, 3)):
            self.assertIsNone(config.quiet(self.at(closed, 9, 30), 60), closed)
            self.assertIsNone(config.quiet(self.at(closed, 16, 0), 60), closed)
        # a Friday evening's long job ends before Monday's wall, or does not start
        friday = D(2026, 10, 9)
        self.assertIsNone(config.quiet(self.at(friday, 17, 0), 48 * 3600))
        self.assertIn("2026-10-12", config.quiet(self.at(friday, 17, 0), 65 * 3600))

    def test_a_half_days_close_wall_moves_with_its_close(self):
        half = D(2026, 11, 27)
        self.assertTrue(dict(nyse_sessions(half, half))[half])
        self.assertIn("12:50-13:35 ET on 2026-11-27", config.quiet(self.at(half, 13, 0), 10))
        self.assertIsNotNone(config.quiet(self.at(half, 12, 40), 900))
        self.assertIsNone(config.quiet(self.at(half, 16, 0), 600), "the regular close wall is not a half day's")
        self.assertIsNone(config.quiet(self.at(half, 13, 36), 600))
        self.assertIsNotNone(config.quiet(self.at(half, 9, 30), 10), "the open wall does not move")

    def test_it_never_raises_and_an_unreadable_clock_is_a_reason_not_to_start(self):
        for now, need in ((float("nan"), 60), (0.0, float("inf")), (0.0, -1), ("soon", 60), (None, None)):
            self.assertIsInstance(config.quiet(now, need), str, (now, need))
        # before the calendar's first year the calendar cannot be read: not a start
        self.assertIsInstance(config.quiet(self.at(D(2015, 6, 1), 9, 30), 60), str)


class TheSchedule(unittest.TestCase):
    """D9: the program is called at the close of t iff the next session is a rebalance session."""

    def test_weekly_is_the_weeks_first_session_at_or_after_the_weekday(self):
        week = [D(2026, 10, 12) + dt.timedelta(days=i) for i in range(5)]
        for weekday in range(5):
            self.assertEqual([config.rebalance_session(d, "weekly", weekday) for d in week],
                             [i == weekday for i in range(5)])
        # Monday 2026-09-07 is Labor Day: the week's first session is Tuesday
        self.assertTrue(config.rebalance_session(D(2026, 9, 8), "weekly", 0))
        self.assertTrue(config.rebalance_session(D(2026, 9, 8), "weekly", 1))
        self.assertFalse(config.rebalance_session(D(2026, 9, 9), "weekly", 0))
        # Good Friday 2026-04-03: a Friday program has no rebalance that week
        days = [d for d, _ in nyse_sessions(D(2026, 3, 30), D(2026, 4, 3))]
        self.assertEqual(len(days), 4)
        self.assertFalse(any(config.rebalance_session(d, "weekly", 4) for d in days))

    def test_monthly_is_the_months_first_session(self):
        self.assertTrue(config.rebalance_session(D(2026, 10, 1), "monthly"))
        self.assertFalse(config.rebalance_session(D(2026, 10, 2), "monthly"))
        self.assertTrue(config.rebalance_session(D(2026, 1, 2), "monthly"), "New Year's Day is closed")
        self.assertTrue(config.rebalance_session(D(2026, 8, 3), "monthly"), "the 1st and 2nd are a weekend")
        counts = sum(config.rebalance_session(d, "monthly") for d, _ in nyse_sessions(D(2023, 1, 1), D(2023, 12, 31)))
        self.assertEqual(counts, 12)

    def test_the_decision_is_the_close_before(self):
        self.assertTrue(config.decision_due(D(2026, 10, 9), "weekly", 0), "Friday's close decides Monday's rebalance")
        self.assertFalse(config.decision_due(D(2026, 10, 12), "weekly", 0))
        self.assertTrue(config.decision_due(D(2026, 10, 12), "weekly", 1))
        self.assertTrue(config.decision_due(D(2026, 9, 30), "monthly"))
        self.assertFalse(config.decision_due(D(2026, 10, 1), "monthly"))
        self.assertTrue(config.decision_due(D(2026, 9, 4), "weekly", 0), "the Friday before Labor Day")
        year = [d for d, _ in nyse_sessions(D(2024, 1, 1), D(2024, 12, 31))]
        self.assertEqual(sum(config.decision_due(d, "monthly") for d in year), 12)
        self.assertEqual(sum(config.decision_due(d, "weekly", 0) for d in year), 52)
        self.assertEqual(config.next_session(D(2026, 10, 9)), D(2026, 10, 12))
        self.assertEqual(config.next_session(D(2026, 12, 24)), D(2026, 12, 28))

    def test_a_daily_rule_a_bad_weekday_and_a_closed_day_are_refused(self):
        for day, rule, weekday in ((D(2026, 10, 12), "daily", 0), (D(2026, 10, 12), "weekly", 5),
                                   (D(2026, 10, 12), "weekly", -1), (D(2026, 10, 12), "weekly", True),
                                   (D(2026, 10, 10), "weekly", 0), (D(2026, 10, 10), "monthly", 0),
                                   ("2026-10-12", "weekly", 0), (dt.datetime(2026, 10, 12, 9), "weekly", 0)):
            with self.subTest(day=day, rule=rule, weekday=weekday):
                with self.assertRaises(ValueError):
                    config.rebalance_session(day, rule, weekday)
                with self.assertRaises(ValueError):
                    config.decision_due(day, rule, weekday)
        self.assertNotIn("daily", config.REBALANCE)


if __name__ == "__main__":
    unittest.main()
