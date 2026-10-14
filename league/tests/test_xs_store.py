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
import pickle
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from league.equity import config as e1config
from league.equity.store import (EquityGateCapability, MissingData, StoreRefused, mint_equity_gate_capability,
                                 nyse_sessions, ordinal)
from league.xs import XS_STORE_VERSION, config, ctx, store, synth
from league.xs.program import Needs

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
        from ltcm.data import NEW_YORK

        self.assertEqual(config.WALLS_ET, (("09:25", "09:45"), ("15:50", "16:35")))
        self.assertEqual(config.NEW_YORK, NEW_YORK, "one zone: the House's own")
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



# ================================================================================================== the reader
def hand_universe(root: Path, spells: dict[int, list], *, masked: dict[int, str] | None = None,
                  salt: bytes = synth.TEST_SALT) -> dict:
    """A universe written by hand: `spells` {aid: [(ticker, start, end | None, exit | None), ...]}."""
    assets = {aid: {"spells": [], "symbol": symbol, "ref": True} for aid, symbol in zip(store.REF_AIDS, config.REF)}
    for aid, rows in spells.items():
        assets[aid] = {"spells": [list(r) for r in rows], "symbol": rows[-1][0], "masked": (masked or {}).get(aid)}
    return store.write_universe(root, assets=assets, salt=salt,
                                source={"known_through": D(2024, 6, 28), "wiki": {"known_through": D(2024, 7, 5)}})


def hand_store(root: Path, spells: dict[int, list], first: dt.date = D(2024, 1, 2), last: dt.date = D(2024, 6, 28),
               *, volume: dict[int, np.ndarray] | None = None, **facts) -> tuple[list[dt.date], dict]:
    """A panel and its universe written by hand: every column has a bar every session; a member column's dollar
    volume is `volume[aid]` (shares a session, at a close of 100) where given."""
    rows = sessions(first, last)
    days = [d for d, _ in rows]
    aids = [*store.REF_AIDS, *sorted(spells)]
    n, m = len(days), len(aids)
    raw = np.empty((n, m, 5))
    raw[:, :, :4] = 100.0
    raw[:, :, 4] = 1000.0
    for aid, shares in (volume or {}).items():
        raw[:, aids.index(aid), 4] = shares
    member = np.zeros((n, m), dtype=bool)
    for aid, own in spells.items():
        for _, start, end, _ in own:
            member[:, aids.index(aid)] |= np.array([start <= d and (end is None or d < end) for d in days])
    tradable = facts.pop("tradable", None)
    if tradable is None:
        tradable = np.ones((n, m), dtype=bool)
        tradable[:, :REF] = False
    hand_universe(root, spells, masked=facts.pop("masks", None))
    manifest = store.write_panel(root, days=days, early=[e for _, e in rows], aids=aids, raw=raw,
                                 adj=raw[:, :, :4].copy(), member=member, tradable=tradable,
                                 hs=np.full((m, 2), 0.0001), fetched_through=days[-1], vintage={}, audit={}, **facts)
    return days, manifest


class Synthetic(unittest.TestCase):
    """One whole synthetic panel (2016-01-04..2026-10-09, 40 names) with E1's GATE mark, for a class of tests."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = synth.synthetic_panel(Path(cls.tmp.name) / "equity-daily", n_assets=40, seed=5, gate=True)
        cls.panel = store.PanelStore(cls.root)
        cls.capability = mint_equity_gate_capability(cls.root, "the panel store's tests")
        cls.gated = store.PanelStore(cls.root, gate=cls.capability)
        cls.universe = cls.panel.universe()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def copy(self) -> Path:
        target = Path(tempfile.mkdtemp(dir=self.tmp.name)) / "equity-daily"
        shutil.copytree(self.root, target)
        return target


class TheStore(Synthetic):
    def test_it_reads_what_the_writer_wrote(self):
        manifest = self.panel.manifest()
        self.assertEqual(manifest, json.loads((self.root / "panel" / store.PANEL_MANIFEST).read_text()))
        self.assertEqual((self.panel.verdict(), self.panel.train_years_ok()), ("ok", config.TRAIN_YEARS))
        self.assertEqual((self.panel.fetched_through, self.panel.live_from), (D(2026, 10, 9), None))
        self.assertEqual((self.panel.gate, self.gated.gate), (False, True))
        self.assertEqual(self.panel.aids().tolist()[:REF], list(store.REF_AIDS))
        self.assertEqual(manifest["days"], len(sessions(D(2016, 1, 4), D(2026, 10, 9))))

    def test_the_windows(self):
        train = self.panel.sessions("train")
        first, second = ([d for d in train if lo <= d <= hi] for lo, hi in config.TRAIN_SEGMENTS)
        self.assertEqual((len(first), len(second), len(train)), (754, 753, 754 + 753))
        self.assertEqual((first[0], first[-1], second[0], second[-1]),
                         (D(2017, 1, 3), D(2019, 12, 31), D(2022, 1, 3), D(2024, 12, 31)))
        validation = self.panel.sessions("validation")
        self.assertEqual((len(validation), validation[0], validation[-1]), (250, D(2025, 1, 2), D(2025, 12, 31)))
        look = self.gated.sessions("look")
        self.assertEqual((len(look), look[0], look[-1]), (250 + 194, D(2025, 1, 2), e1config.LOOK_CAP))
        self.assertEqual(look[:250], validation, "the look's run starts at Validation's first session")
        forward = self.gated.sessions("forward")
        self.assertEqual((forward[0], forward[-1]), (D(2026, 9, 28), D(2026, 10, 9)))
        self.assertEqual((store.WINDOWS, store.SEALED), (("train", "validation", "look", "forward"), ("look", "forward")))
        for window in ("holdout", "gym", ""):
            with self.assertRaises(StoreRefused):
                self.gated.sessions(window)

    def test_a_manifest_without_a_verdict_reads_insufficient(self):
        root = self.copy()
        path = root / "panel" / store.PANEL_MANIFEST
        manifest = json.loads(path.read_text())
        del manifest["verdict"], manifest["train_years_ok"]
        path.write_text(json.dumps(manifest))
        panel = store.PanelStore(root)
        self.assertEqual((panel.verdict(), panel.train_years_ok()), ("insufficient", ()))
        manifest.update(verdict="fine", train_years_ok=["x"])
        path.write_text(json.dumps(manifest))
        self.assertEqual((store.PanelStore(root).verdict(), store.PanelStore(root).train_years_ok()), ("insufficient", ()))


class NoReserveSessionIsEverRun(Synthetic):
    """SEAL X4: a run session in 2016, 2020 or 2021 is StoreRefused; `write_panel` refuses a 2020 day; sealed windows
    open only with E1's capability minted on the same root."""

    KEY = {"history": 60, "run_key": "x4"}

    def test_the_store_holds_no_2020_session(self):
        days = np.load(self.root / "panel" / "days.npy")
        years = {dt.date.fromordinal(int(d) + dt.date(1970, 1, 1).toordinal()).year for d in days}
        self.assertEqual(years, {2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026})
        self.assertEqual((config.RESERVE_YEARS, config.HISTORY_YEARS), ((2020,), (2016, 2021)))

    def test_the_writer_refuses_a_2020_day(self):
        rows = nyse_sessions(D(2020, 3, 2), D(2020, 3, 6))
        args = hand_panel()
        args.update(days=[d for d, _ in rows], early=[e for _, e in rows], fetched_through=rows[-1][0])
        with self.assertRaises(ValueError) as caught:
            store.write_panel(Path(self.tmp.name) / "never", **args)
        self.assertIn("2020 is never in the panel store", str(caught.exception))
        self.assertFalse((Path(self.tmp.name) / "never").exists())

    def test_a_run_session_of_a_history_year_is_refused(self):
        for start, end in ((D(2016, 1, 4), D(2016, 12, 30)), (D(2016, 6, 1), D(2017, 6, 1)),
                           (D(2021, 1, 4), D(2021, 12, 31)), (D(2021, 12, 31), D(2022, 3, 1)),
                           (D(2016, 12, 30), D(2016, 12, 30))):
            with self.subTest(start=start), self.assertRaises(StoreRefused) as caught:
                self.gated.train(start, end, **self.KEY)
            self.assertIn("history only", str(caught.exception))

    def test_a_run_session_of_the_reserve_is_refused(self):
        for start, end in ((D(2020, 1, 2), D(2020, 12, 31)), (D(2019, 6, 3), D(2020, 1, 2)),
                           (D(2019, 12, 31), D(2022, 1, 3)), (D(2020, 6, 1), D(2020, 6, 1))):
            with self.subTest(start=start), self.assertRaises(StoreRefused) as caught:
                self.gated.train(start, end, **self.KEY)
            self.assertIn("reserve", str(caught.exception))

    def test_a_train_slice_lies_inside_one_train_segment(self):
        for start, end in ((D(2025, 1, 2), D(2025, 6, 30)), (D(2024, 6, 3), D(2025, 1, 31)),
                           (D(2026, 1, 2), D(2026, 3, 31)), (D(2018, 6, 1), D(2018, 1, 2))):
            with self.subTest(start=start), self.assertRaises(StoreRefused):
                self.gated.train(start, end, **self.KEY)
        with self.assertRaises(StoreRefused):
            self.gated.bars("train", **self.KEY)
        for lo, hi in config.TRAIN_SEGMENTS:
            self.assertEqual(self.panel.train(lo, hi, **self.KEY).bars.window, "train")

    def test_no_slice_runs_a_session_of_2016_2020_or_2021(self):
        """Whatever is asked: every run session of every slice is a Train-segment, Validation, look or forward
        session, and the look-back of a segment is its own span's history year, never a year across the reserve."""
        slices = [self.panel.train(lo, hi, **self.KEY).bars for lo, hi in config.TRAIN_SEGMENTS]
        slices += [self.panel.bars("validation", **self.KEY).bars, self.gated.bars("look", **self.KEY).bars,
                   self.gated.bars("forward", **self.KEY).bars,
                   self.panel.train(D(2018, 3, 1), D(2018, 9, 28), **self.KEY).bars,
                   self.panel.train(D(2022, 1, 3), D(2022, 1, 3), **self.KEY).bars]
        for bars in slices:
            days = [dt.date(1970, 1, 1) + dt.timedelta(days=int(d)) for d in bars.days]
            run, back = days[bars.first:], days[:bars.first]
            self.assertFalse({d.year for d in run} & {2016, 2020, 2021}, bars.window)
            self.assertNotIn(2020, {d.year for d in back})
            self.assertLessEqual(len(back), config.DERIVE_SESSIONS)
        first, second = slices[0], slices[1]
        self.assertEqual((first.first, int(first.days[0])), (252, ordinal(D(2016, 1, 4))), "2016's 252 sessions")
        self.assertEqual((second.first, int(second.days[0])), (252, ordinal(D(2021, 1, 4))),
                         "2021's 252 sessions: the look-back never crosses into 2019")
        self.assertEqual(slices[2].first, config.DERIVE_SESSIONS)
        self.assertEqual(slices[5].first, config.DERIVE_SESSIONS)
        # so a segment's first decision, at the close before its first run session, is a session short of a momentum
        inputs = ctx.inputs_from_panel(second, second.first - 1, needs=Needs("sp500", 60, 10, "weekly", 0, 60),
                                       cash=0.0, equity=0.0, budget=0.0, params={})
        self.assertEqual(inputs.days.shape[0], 252)
        self.assertFalse(ctx.derive(inputs).elig.any())

    def test_sealed_windows_open_only_with_e1s_capability_minted_on_this_root(self):
        self.assertIsInstance(self.capability, EquityGateCapability)
        for window in store.SEALED:
            with self.assertRaises(StoreRefused):
                self.panel.sessions(window)
            with self.assertRaises(StoreRefused):
                self.panel.bars(window, **self.KEY)
            self.assertGreater(self.gated.bars(window, **self.KEY).bars.n, 0)
        other = synth.synthetic_panel(Path(self.tmp.name) / "other" / "equity-daily", n_assets=12, seed=1, gate=True,
                                      start=D(2025, 1, 2), end=D(2026, 10, 9))
        elsewhere = mint_equity_gate_capability(other, "another store")
        for bad in (elsewhere, True, "gate", object()):
            with self.subTest(gate=type(bad).__name__), self.assertRaises(StoreRefused):
                store.PanelStore(self.root, gate=bad)
        with self.assertRaises(TypeError):
            EquityGateCapability()
        unmarked = synth.synthetic_panel(Path(self.tmp.name) / "plain" / "equity-daily", n_assets=12, seed=1,
                                         start=D(2025, 1, 2), end=D(2026, 10, 9))
        with self.assertRaises(StoreRefused):
            mint_equity_gate_capability(unmarked, "no GATE mark")

    def test_validation_and_train_need_no_capability_and_open_no_sealed_day(self):
        validation = self.panel.bars("validation", **self.KEY).bars
        last = dt.date(1970, 1, 1) + dt.timedelta(days=int(validation.days[-1]))
        self.assertEqual(last, D(2025, 12, 31))
        cut = self.gated.bars("look", start=D(2026, 3, 2), end=D(2026, 3, 31), **self.KEY).bars
        self.assertEqual(cut.n - cut.first, len(nyse_sessions(D(2026, 3, 2), D(2026, 3, 31))))


class Slices(Synthetic):
    KEY = {"history": 252, "run_key": "program-sha|validation|2025-01-02"}

    def test_what_a_run_is_sent(self):
        piece = self.panel.bars("validation", **self.KEY)
        bars = piece.bars
        n, m = bars.raw.shape[:2]
        self.assertEqual((bars.n, bars.first, bars.ref, bars.window), (n, 253, REF, "validation"))
        self.assertEqual({name: (getattr(bars, name).dtype.str, getattr(bars, name).shape) for name in
                          ("days", "early", "raw", "adj", "elig0", "ids", "exit", "hs", "sector_perm")},
                         {"days": ("<i4", (n,)), "early": ("|b1", (n,)), "raw": ("<f8", (n, m, 5)),
                          "adj": ("<f8", (n, m, 4)), "elig0": ("|b1", (n, m)), "ids": ("<i4", (m - REF,)),
                          "exit": ("|i1", (m,)), "hs": ("<f8", (m, 2)), "sector_perm": ("|i1", (11,))})
        self.assertEqual((len(bars.dither_key), len(bars.data_version)), (32, 24))
        self.assertTrue((np.diff(bars.ids) > 0).all(), "the member columns are in ascending id")
        self.assertEqual((piece.run_key, piece.aids.shape, piece.aids.tolist()[:REF]),
                         (self.KEY["run_key"], (m,), list(store.REF_AIDS)))
        for array in (bars.days, bars.raw, bars.adj, bars.elig0, bars.ids, bars.hs, piece.aids):
            with self.assertRaises(ValueError):
                array[0] = 0
        back = pickle.loads(pickle.dumps(bars))
        self.assertTrue(np.array_equal(back.raw, bars.raw, equal_nan=True) and back.dither_key == bars.dither_key)

    def test_the_columns_are_every_member_of_any_of_its_sessions_and_the_stores_own_bars(self):
        piece = self.panel.bars("validation", **self.KEY)
        bars = piece.bars
        days = [dt.date(1970, 1, 1) + dt.timedelta(days=int(d)) for d in bars.days]
        ever = {aid for day in days for aid in self.universe.table().tolist() if self.universe.member(aid, day)}
        self.assertEqual(set(piece.aids[REF:].tolist()), ever)
        self.assertGreater(len(ever), 40, "names that left or joined inside the slice have a column too")
        all_days = np.load(self.root / "panel" / "days.npy").tolist()
        all_aids = np.load(self.root / "panel" / "aids.npy").tolist()
        rows = [all_days.index(int(d)) for d in bars.days]
        cols = [all_aids.index(int(a)) for a in piece.aids]
        raw = np.load(self.root / "panel" / "raw.npy")
        adj = np.load(self.root / "panel" / "adj.npy")
        self.assertTrue(np.array_equal(bars.raw, raw[rows][:, cols], equal_nan=True))
        self.assertTrue(np.array_equal(bars.adj, adj[rows][:, cols], equal_nan=True))
        self.assertEqual(rows, list(range(rows[0], rows[0] + len(rows))), "consecutive sessions of the store")
        hs = np.load(self.root / "panel" / "hs.npy")
        self.assertTrue(np.array_equal(bars.hs, np.maximum(hs[cols], config.HS_FLOOR_BP / 1e4)))

    def test_the_ids_are_the_tables_and_the_run_keys(self):
        piece = self.panel.bars("validation", **self.KEY)
        run = store.run_salt(synth.TEST_SALT, self.KEY["run_key"])
        self.assertEqual(piece.bars.ids.tolist(),
                         store.ids_for(piece.aids[REF:], run, table=self.universe.table()).tolist())
        self.assertEqual(piece.bars.dither_key, store.dither_key(run))
        self.assertEqual(piece.bars.sector_perm.tolist(), store.sector_perm(run).tolist())

    def test_elig0_is_membership_on_the_session_and_the_next_two(self):
        piece = self.panel.bars("validation", **self.KEY)
        bars = piece.bars
        days = [dt.date(1970, 1, 1) + dt.timedelta(days=int(d)) for d in bars.days]
        self.assertEqual(config.MEMBER_AHEAD, 2)
        aids = piece.aids.tolist()
        member = np.array([[self.universe.member(a, d) for a in aids] for d in days])
        self.assertTrue(member.any(axis=0)[REF:].all())
        self.assertFalse(member.all(axis=0)[REF:].all(), "some name joins or leaves inside the slice")
        out = np.zeros_like(member)
        for row, day in enumerate(days):
            for aid in self.panel.class_out(day):
                if aid in aids:
                    out[row, aids.index(aid)] = True
        want = member[:-2] & member[1:-1] & member[2:] & ~out[:-2]
        self.assertTrue(np.array_equal(bars.elig0[:-2], want))
        self.assertFalse(bars.elig0[:, :REF].any(), "a REF column is never eligible")
        # a name is out of U two sessions BEFORE it leaves the index (index changes are announced ahead)
        leaver = next(c for c in range(REF, len(aids)) if member[0, c] and not member[-1, c])
        last_in = int(np.flatnonzero(member[:, leaver])[-1])
        self.assertTrue(bars.elig0[last_in - 2, leaver] or out[last_in - 2, leaver])
        self.assertFalse(bars.elig0[last_in - 1, leaver] or bars.elig0[last_in, leaver])

    def test_past_the_slices_last_session_membership_is_as_at_the_last(self):
        leaves = sorted({row[2] for aid in self.universe.table().tolist() if aid >= store.FIRST_MEMBER_AID
                         for row in self.universe._assets[aid].spells if row[2] and row[2].year == 2025})
        self.assertTrue(leaves)
        gone = leaves[0]
        before = [d for d, _ in nyse_sessions(D(2025, 1, 2), gone)][-2]            # the session before it leaves
        piece = self.panel.bars("validation", end=before, **self.KEY)
        aids = piece.aids.tolist()
        column = next(aids.index(aid) for aid in aids[REF:]
                      if any(row[2] == gone for row in self.universe._assets[aid].spells))
        self.assertTrue(piece.bars.elig0[-1, column], "the slice does not read the session after its last")
        longer = self.panel.bars("validation", **self.KEY)
        row = longer.bars.days.tolist().index(ordinal(before))
        self.assertFalse(longer.bars.elig0[row, longer.aids.tolist().index(aids[column])])

    def test_exactly_these_columns(self):
        members = [aid for aid, _ in self.universe.members(D(2025, 6, 2))]
        left = self.universe.left(D(2025, 6, 2))[-2:]
        self.assertEqual(len(left), 2)
        self.assertFalse(set(left) & set(members))
        piece = self.panel.bars("validation", aids=[*members, *left, 1, 5], **self.KEY)
        self.assertEqual(sorted(piece.aids[REF:].tolist()), sorted([*members, *left]))
        self.assertEqual(piece.aids[:REF].tolist(), list(store.REF_AIDS))
        whole = self.panel.bars("validation", **self.KEY)
        table = self.universe.table()
        ids = dict(zip(table.tolist(), store.ids_for(table, store.run_salt(synth.TEST_SALT, self.KEY["run_key"]),
                                                      table=table).tolist()))
        self.assertEqual(whole.bars.ids.tolist(), sorted(ids[a] for a in whole.aids[REF:].tolist()))
        self.assertEqual(piece.bars.ids.tolist(), sorted(ids[a] for a in piece.aids[REF:].tolist()),
                         "an aid's id is the same whatever other aids are asked with it")
        row = piece.bars.days.tolist().index(ordinal(D(2025, 6, 2)))
        for aid in left:
            self.assertFalse(piece.bars.elig0[row:, piece.aids.tolist().index(aid)].any(),
                             "a name that left keeps its column and its bars, and is no candidate")
            self.assertTrue(np.isfinite(piece.bars.raw[row:, piece.aids.tolist().index(aid), 3]).all())
        with self.assertRaises(MissingData):
            self.panel.bars("validation", aids=[*members, 99999], **self.KEY)
        self.assertEqual(self.panel.train(D(2023, 1, 3), D(2023, 3, 31), aids=members[:7], **self.KEY).aids.shape,
                         (REF + 7,))

    def test_arguments_are_checked(self):
        for history in (19, 253, 60.0, True, None):
            with self.subTest(history=history), self.assertRaises(ValueError):
                self.panel.bars("validation", history=history, run_key="k")
        for half in (2, -1, True, "0"):
            with self.subTest(half=half), self.assertRaises(ValueError):
                self.panel.train(D(2023, 1, 3), D(2023, 3, 31), history=60, run_key="k", half=half)
        for run_key in ("", None, 7):
            with self.subTest(run_key=run_key), self.assertRaises(ValueError):
                self.panel.bars("validation", history=60, run_key=run_key)
        empty = self.panel.bars("validation", history=60, run_key="k", start=D(2025, 7, 5), end=D(2025, 7, 6))
        self.assertEqual((empty.bars.n, empty.bars.first, empty.bars.raw.shape), (0, 0, (0, REF, 5)))

    def test_the_data_version_names_the_files_and_the_span(self):
        piece = self.panel.bars("validation", **self.KEY)
        days = self.panel.sessions("validation")
        self.assertRegex(piece.bars.data_version, r"^[0-9a-f]{24}$")
        self.assertEqual(self.panel.bars("validation", history=60, run_key="another").bars.data_version,
                         piece.bars.data_version)
        self.assertNotEqual(self.panel.bars("validation", end=D(2025, 6, 30), **self.KEY).bars.data_version,
                            piece.bars.data_version)
        other = store.PanelStore(synth.synthetic_panel(Path(self.tmp.name) / "seed6" / "equity-daily", n_assets=40,
                                                       seed=6, start=D(2023, 6, 1), end=D(2025, 12, 31)))
        self.assertNotEqual(other.data_version(days), self.panel.data_version(days))


class Integrity(Synthetic):
    """A reader verifies every file against its manifest: a store being rewritten refuses, never mixes days."""

    KEY = {"history": 60, "run_key": "k"}

    def spoil(self, root: Path, name: str) -> None:
        path = root / name
        data = bytearray(path.read_bytes())
        data[-1] ^= 0xFF
        path.write_bytes(bytes(data))

    def test_a_file_that_does_not_match_its_manifest_is_refused(self):
        for name in ("raw.npy", "adj.npy", "member.npy", "tradable.npy", "hs.npy"):
            root = self.copy()
            self.spoil(root, f"panel/{name}")
            with self.subTest(name=name), self.assertRaises(MissingData) as caught:
                store.PanelStore(root).bars("validation", **self.KEY)
            self.assertIn("does not match its manifest", str(caught.exception))
        for name in ("days.npy", "early.npy", "aids.npy"):
            root = self.copy()
            self.spoil(root, f"panel/{name}")
            with self.subTest(name=name), self.assertRaises(MissingData):
                store.PanelStore(root)

    def test_a_file_changed_under_an_open_reader_is_refused_too(self):
        root = self.copy()
        panel = store.PanelStore(root)
        panel.bars("validation", **self.KEY)
        self.spoil(root, "panel/raw.npy")
        with self.assertRaises(MissingData):
            store.PanelStore(root).bars("validation", **self.KEY)

    def test_a_missing_or_foreign_store_is_refused(self):
        with self.assertRaises(MissingData):
            store.PanelStore(Path(self.tmp.name) / "nowhere")
        root = self.copy()
        (root / "panel" / store.VERSION_FILE).write_text("xs-panel-v0\n")
        with self.assertRaises(MissingData) as caught:
            store.PanelStore(root)
        self.assertIn("xs-panel-v0", str(caught.exception))
        for text in ("{", "[]", json.dumps({"version": XS_STORE_VERSION}),
                     json.dumps({"version": "other", "sha256": {}})):
            root = self.copy()
            (root / "panel" / store.PANEL_MANIFEST).write_text(text)
            with self.subTest(text=text[:20]), self.assertRaises(MissingData):
                store.PanelStore(root)
        root = self.copy()
        (root / "panel" / "raw.npy").unlink()
        with self.assertRaises(MissingData):
            store.PanelStore(root).bars("validation", **self.KEY)
        root = self.copy()
        path = root / "panel" / store.PANEL_MANIFEST
        manifest = json.loads(path.read_text())
        manifest["fetched_through"] = "2026-10-08"
        path.write_text(json.dumps(manifest))
        with self.assertRaises(MissingData):
            store.PanelStore(root)

    def test_the_universe_is_verified_as_the_panel_is(self):
        root = self.copy()
        self.spoil(root, "universe/assets.json")
        with self.assertRaises(MissingData):
            store.Universe(root)
        with self.assertRaises(MissingData):
            store.PanelStore(root).bars("validation", **self.KEY)
        root = self.copy()
        shutil.rmtree(root / "universe")
        panel = store.PanelStore(root)                      # the panel's own facts need no universe
        self.assertEqual(panel.verdict(), "ok")
        with self.assertRaises(MissingData):
            panel.bars("validation", **self.KEY)
        root = self.copy()
        (root / "universe" / store.SALT_FILE).write_bytes(bytes(32))
        with self.assertRaises(MissingData) as caught:
            store.Universe(root)
        self.assertIn("salt", str(caught.exception))
        root = self.copy()
        (root / "universe" / store.UNIVERSE_MANIFEST).write_text(json.dumps({"version": "xs-universe-v0", "sha256": {}}))
        with self.assertRaises(MissingData):
            store.Universe(root)


class Halves(Synthetic):
    """D18: half(i) = sha256(SALT | b"|half-1|" | str(aid))[0] & 1; a half run sees its half only."""

    def test_the_formula(self):
        for aid in (100, 101, 250, 99999):
            digest = hashlib.sha256(synth.TEST_SALT + b"|half-1|" + str(aid).encode()).digest()
            self.assertEqual(store.half_of(synth.TEST_SALT, aid), digest[0] & 1)
        halves = [store.half_of(synth.TEST_SALT, aid) for aid in range(100, 400)]
        self.assertTrue(110 < sum(halves) < 190)
        self.assertNotEqual(halves, [store.half_of(bytes(32), aid) for aid in range(100, 400)], "another salt's halves")

    def test_a_half_run_marks_the_other_halfs_members_invisible(self):
        args = {"history": 60, "run_key": "k|train|2023-01-03"}
        full = self.panel.train(D(2023, 1, 3), D(2023, 12, 29), **args)
        seen = [self.panel.train(D(2023, 1, 3), D(2023, 12, 29), half=h, **args) for h in (0, 1)]
        for half, piece in enumerate(seen):
            self.assertEqual(piece.aids.tolist(), full.aids.tolist(), "the same columns, the same ids")
            self.assertEqual(piece.bars.ids.tolist(), full.bars.ids.tolist())
            mine = np.array([False] * REF + [store.half_of(synth.TEST_SALT, a) == half for a in full.aids[REF:].tolist()])
            self.assertTrue(np.array_equal(piece.bars.elig0, full.bars.elig0 & mine[None, :]))
            self.assertGreater(int(piece.bars.elig0.any(axis=0).sum()), 8)
        self.assertFalse((seen[0].bars.elig0 & seen[1].bars.elig0).any())
        self.assertTrue(np.array_equal(seen[0].bars.elig0 | seen[1].bars.elig0, full.bars.elig0))
        self.assertTrue(np.array_equal(seen[0].bars.raw, full.bars.raw, equal_nan=True), "the bars are all there")


class TheClassOfTheMonth(unittest.TestCase):
    """D4: one class a company, chosen at the month's first session by the 63 sessions before it, held a month."""

    A, B, OTHER = 100, 101, 102

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "equity-daily"
        self.pair = config.CLASS_PAIRS[1]
        self.all_year = lambda ticker: [(ticker, D(2023, 1, 3), None, None)]

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, spells=None, **kwargs):
        spells = spells or {self.A: self.all_year(self.pair[0]), self.B: self.all_year(self.pair[1]),
                            self.OTHER: self.all_year("ZQAA")}
        days, _ = hand_store(self.root, spells, **kwargs)
        return days, store.PanelStore(self.root)

    def test_the_pairs(self):
        self.assertEqual(config.CLASS_PAIRS, (("GOOG", "GOOGL"), ("FOX", "FOXA"), ("NWS", "NWSA"), ("DISCA", "DISCK"),
                                              ("UA", "UAA")))
        self.assertEqual(config.CLASS_SESSIONS, 63)

    def test_the_higher_median_dollar_volume_of_the_63_sessions_before_the_months_first(self):
        days = [d for d, _ in sessions(D(2024, 1, 2), D(2024, 6, 28))]
        n = len(days)
        april = days.index(D(2024, 4, 1))
        a, b = np.full(n, 1000.0), np.full(n, 2000.0)
        a[april - 40:] = 5000.0                    # A trades more from 40 sessions before April's first session
        days, panel = self.build(volume={self.A: a, self.B: b})
        # April's choice reads the 63 sessions through March's last: A's median is still 5000 on 40 of the 63
        self.assertEqual(panel.class_out(D(2024, 4, 15)), frozenset({self.B}))
        # March's choice read the 63 sessions through February's last: A had 5000 on fewer than half of them
        march = days.index(D(2024, 3, 1))
        window = a[max(0, march - 63):march]                    # this store begins in January: 41 sessions
        self.assertLess(float(np.median(window)), 2000.0)
        self.assertEqual(panel.class_out(D(2024, 3, 1)), frozenset({self.A}))
        self.assertEqual(panel.class_out(D(2024, 3, 28)), frozenset({self.A}), "held for the whole month")
        self.assertEqual(panel.class_out(D(2024, 5, 31)), frozenset({self.B}))

    def test_the_choice_reads_no_bar_of_the_month_itself(self):
        days = [d for d, _ in sessions(D(2024, 1, 2), D(2024, 6, 28))]
        n, april = len(days), days.index(D(2024, 4, 1))
        a, b = np.full(n, 1000.0), np.full(n, 2000.0)
        a[april:] = 9000.0                          # from April's first session on
        _, panel = self.build(volume={self.A: a, self.B: b})
        self.assertEqual(panel.class_out(D(2024, 4, 1)), frozenset({self.A}), "live knows the choice a day ahead")
        self.assertEqual(panel.class_out(D(2024, 4, 30)), frozenset({self.A}))
        self.assertEqual(panel.class_out(D(2024, 5, 1)), frozenset({self.A}), "21 of the 63 sessions: not yet")
        self.assertEqual(panel.class_out(D(2024, 6, 3)), frozenset({self.B}), "42 of the 63: the median moved")

    def test_a_tie_goes_to_the_lower_aid_and_no_bar_reads_as_the_lowest(self):
        _, panel = self.build()
        self.assertEqual(panel.class_out(D(2024, 3, 4)), frozenset({self.B}))
        self.assertEqual(panel.class_out(D(2024, 1, 2)), frozenset({self.B}), "the store's first month: no session before")
        days = [d for d, _ in sessions(D(2024, 1, 2), D(2024, 6, 28))]
        zero = np.zeros(len(days))                  # a flat volume-0 bar is no valid bar
        self.tmp.cleanup()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "equity-daily"
        _, panel = self.build(volume={self.A: zero})
        self.assertEqual(panel.class_out(D(2024, 3, 4)), frozenset({self.A}))

    def test_the_choice_is_among_the_classes_that_are_members_and_a_class_that_joins_waits_a_month(self):
        spells = {self.A: [(self.pair[0], D(2023, 1, 3), None, None)],
                  self.B: [(self.pair[1], D(2024, 3, 13), None, None)],          # joins mid-March
                  self.OTHER: self.all_year("ZQAA")}
        days = [d for d, _ in sessions(D(2024, 1, 2), D(2024, 6, 28))]
        _, panel = self.build(spells, volume={self.B: np.full(len(days), 9000.0)})
        self.assertEqual(panel.class_out(D(2024, 2, 15)), frozenset({self.B}))
        self.assertEqual(panel.class_out(D(2024, 3, 20)), frozenset({self.B}),
                         "it joined on the 13th: A was chosen on the 1st and is held for the month")
        self.assertEqual(panel.class_out(D(2024, 4, 1)), frozenset({self.A}), "from April the higher volume wins")
        piece = panel.bars if False else panel.train(D(2024, 1, 2), D(2024, 6, 28), history=20, run_key="k")
        column = {aid: i for i, aid in enumerate(piece.aids.tolist())}
        rows = {d: i for i, d in enumerate(dt.date(1970, 1, 1) + dt.timedelta(days=int(x)) for x in piece.bars.days)}
        elig = piece.bars.elig0
        self.assertFalse(elig[rows[D(2024, 3, 13)]:rows[D(2024, 3, 28)] + 1, column[self.B]].any())
        self.assertTrue(elig[rows[D(2024, 3, 1)]:rows[D(2024, 3, 28)] + 1, column[self.A]].all())
        self.assertTrue(elig[rows[D(2024, 4, 1)]:rows[D(2024, 4, 30)] + 1, column[self.B]].all())
        self.assertFalse(elig[rows[D(2024, 4, 1)]:rows[D(2024, 4, 30)] + 1, column[self.A]].any())
        self.assertTrue(elig[:-2, column[self.OTHER]].all(), "a name of no pair is never touched")

    def test_a_pair_with_no_member_has_no_choice(self):
        spells = {self.A: [(self.pair[0], D(2024, 5, 15), None, None)], self.OTHER: self.all_year("ZQAA")}
        _, panel = self.build(spells)
        self.assertEqual(panel.class_out(D(2024, 4, 15)), frozenset())
        self.assertEqual(panel.class_out(D(2024, 6, 3)), frozenset())

    def test_never_two_classes_of_one_company_on_a_synthetic_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = synth.synthetic_panel(Path(tmp) / "equity-daily", n_assets=20, seed=2, start=D(2023, 1, 3),
                                         end=D(2025, 12, 31), churn=0.0)
            panel = store.PanelStore(root)
            pair = panel.universe().class_aids(synth.PAIR)
            self.assertEqual(len(pair), 2)
            piece = panel.bars("validation", history=20, run_key="k")
            cols = [piece.aids.tolist().index(a) for a in pair]
            both = piece.bars.elig0[:, cols]
            self.assertFalse(both.all(axis=1).any(), "never both")
            self.assertTrue(both[:-2].any(axis=1).all(), "always one")
            self.assertTrue(both[:, 0].any() and both[:, 1].any(), "the choice flips with the volume")


class TheParentsRowForALiveDay(Synthetic):
    """`elig0_row`: what a live decision's columns take, by the rules a slice's rows are built from."""

    def test_it_is_the_slices_row(self):
        piece = self.panel.bars("validation", history=60, run_key="k")
        days = [dt.date(1970, 1, 1) + dt.timedelta(days=int(d)) for d in piece.bars.days]
        checked = 0
        for row in range(piece.bars.first, piece.bars.n - config.MEMBER_AHEAD, 7):
            self.assertTrue(np.array_equal(self.panel.elig0_row(days[row], piece.aids), piece.bars.elig0[row]), days[row])
            checked += 1
        self.assertGreater(checked, 30)

    def test_it_reads_the_membership_ahead_from_the_spells_past_the_stores_last_session(self):
        last = self.panel.fetched_through
        members = [aid for aid, _ in self.universe.members(last)]
        row = self.panel.elig0_row(last, [1, *members, 99999])
        self.assertEqual((bool(row[0]), bool(row[-1])), (False, False), "a REF aid and an unknown aid are never eligible")
        out = self.panel.class_out(last)
        self.assertEqual(row[1:-1].tolist(), [aid not in out for aid in members])
        ahead = config.next_session(config.next_session(last))
        self.assertGreater(ahead, last)


class TheUniverse(Synthetic):
    def test_members_and_their_symbols(self):
        day = D(2024, 6, 3)
        members = self.universe.members(day)
        self.assertEqual(len(members), 40, "leavers and joiners pair off: the count is the panel's")
        self.assertEqual([aid for aid, _ in members], sorted(aid for aid, _ in members))
        for aid, symbol in members:
            self.assertTrue(self.universe.member(aid, day))
            self.assertEqual(self.universe.symbol(aid, day), symbol)
            self.assertEqual(self.universe.aid(symbol, day), aid)
            self.assertTrue(symbol.startswith("ZQ") or symbol in synth.PAIR, "every synthetic ticker is made up")
        self.assertFalse(self.universe.member(1, day), "a REF aid is never a member")
        self.assertEqual([self.universe.symbol(aid, day) for aid in store.REF_AIDS], list(config.REF))
        self.assertEqual(self.universe.aid("SPY", day), 1)
        self.assertEqual(self.universe.table().tolist(), sorted(self.universe.table().tolist()))
        self.assertEqual(self.universe.table().tolist()[:REF], list(store.REF_AIDS))
        self.assertGreater(len(self.universe.table()), REF + 40)

    def test_membership_is_start_inclusive_end_exclusive(self):
        """D3: member[d, i] = some spell of i has start <= d and (end is null or d < end)."""
        ended = next(asset for asset in self.universe._assets.values() if asset.spells and asset.spells[0][2])
        ticker, start, end, how = ended.spells[0]
        before_end = [d for d, _ in nyse_sessions(start, end)][-2]
        self.assertTrue(self.universe.member(ended.aid, start) and self.universe.member(ended.aid, before_end))
        self.assertFalse(self.universe.member(ended.aid, end))
        self.assertIn(how, store.EXITS)
        self.assertEqual((self.universe.exit(ended.aid, end), self.universe.exit(ended.aid, before_end)), (how, how))
        self.assertEqual(self.universe.symbol(ended.aid, end + dt.timedelta(days=30)), ticker,
                         "a name that left the index keeps its symbol: a held lot of it keeps a column")
        self.assertEqual(self.universe.aid(ticker, end + dt.timedelta(days=30)), ended.aid)
        joiner = next(asset for asset in self.universe._assets.values()
                      if asset.spells and asset.spells[0][1] > D(2016, 1, 4) and asset.spells[0][2] is None)
        self.assertFalse(self.universe.member(joiner.aid, joiner.spells[0][1] - dt.timedelta(days=1)))
        self.assertTrue(self.universe.member(joiner.aid, joiner.spells[0][1]))
        self.assertIsNone(self.universe.exit(joiner.aid, joiner.spells[0][1]))
        with self.assertRaises(KeyError):
            self.universe.symbol(joiner.aid, joiner.spells[0][1] - dt.timedelta(days=1))
        for bad in (("NOSUCH", D(2024, 6, 3)), (joiner.spells[0][0], joiner.spells[0][1] - dt.timedelta(days=1))):
            with self.assertRaises(KeyError):
                self.universe.aid(*bad)
        with self.assertRaises(KeyError):
            self.universe.symbol(99999, D(2024, 6, 3))

    def test_how_stale_the_membership_is(self):
        self.assertEqual(self.universe.known_through, D(2026, 10, 9))
        self.assertEqual((self.universe.stale_days(D(2026, 10, 9)), self.universe.stale_days(D(2026, 11, 23)),
                          self.universe.stale_days(D(2026, 1, 2))), (0, 45, 0))

    def test_before_the_universe_deploy_every_member_is_tradable(self):
        day = D(2024, 6, 3)
        self.assertEqual(self.universe.tradable(day), {symbol for _, symbol in self.universe.members(day)})
        self.assertIsNone(self.panel.tradable_aids(day))


class TheUniverseByHand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "equity-daily"
        self.spells = {100: [("ZQAA", D(2023, 1, 3), None, None)],
                       101: [("ZQAB", D(2023, 1, 3), D(2024, 3, 15), "deal"), ("ZQAB", D(2024, 5, 1), None, None)],
                       102: [("ZQAC", D(2023, 1, 3), D(2024, 4, 1), "other")],
                       103: [("ZQOLD", D(2023, 1, 3), D(2024, 2, 1), "unknown"), ("ZQNEW", D(2024, 2, 1), None, None)],
                       104: [("ZQAD", D(2023, 1, 3), None, None)]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_spells_renames_masks_and_exits(self):
        hand_store(self.root, self.spells, masks={104: "no_bars"})
        universe = store.Universe(self.root)
        self.assertEqual(universe.members(D(2024, 3, 14)), [(100, "ZQAA"), (101, "ZQAB"), (102, "ZQAC"), (103, "ZQNEW")])
        self.assertEqual(universe.members(D(2024, 4, 1)), [(100, "ZQAA"), (103, "ZQNEW")], "between its two spells")
        self.assertEqual(universe.members(D(2024, 5, 1)), [(100, "ZQAA"), (101, "ZQAB"), (103, "ZQNEW")])
        self.assertEqual((universe.masked(104), universe.masked(100)), ("no_bars", None))
        self.assertTrue(universe.member(104, D(2024, 3, 14)), "a masked asset is a member, never a listed one")
        self.assertEqual((universe.symbol(103, D(2024, 1, 31)), universe.symbol(103, D(2024, 2, 1))), ("ZQOLD", "ZQNEW"))
        self.assertEqual((universe.aid("ZQOLD", D(2024, 1, 31)), universe.aid("ZQNEW", D(2024, 6, 3))), (103, 103))
        self.assertEqual(universe.symbol(101, D(2024, 4, 10)), "ZQAB", "between two spells: the ended one's ticker")
        self.assertEqual([universe.exit(101, d) for d in (D(2024, 3, 14), D(2024, 4, 10), D(2024, 5, 2))],
                         ["deal", "deal", None])
        self.assertEqual((universe.exit(102, D(2024, 6, 3)), universe.exit(103, D(2024, 1, 15))), ("other", "unknown"))
        self.assertEqual(universe.manifest()["exits"], {"deal": 1, "other": 1, "unknown": 1})
        self.assertEqual(universe.known_through, D(2024, 7, 5), "the spell file's, extended by the change rows")
        self.assertEqual(universe.class_aids(("ZQOLD", "ZQAA")), [100, 103])
        self.assertTrue(universe.has(100) and not universe.has(105))

    def test_a_slice_counts_the_exit_and_never_shows_a_masked_name(self):
        hand_store(self.root, self.spells, masks={104: "insane"})
        piece = store.PanelStore(self.root).train(D(2024, 1, 2), D(2024, 6, 28), history=20, run_key="k")
        column = {aid: i for i, aid in enumerate(piece.aids.tolist())}
        self.assertFalse(piece.bars.elig0[:, column[104]].any(), "masked: never eligible")
        self.assertEqual({aid: int(piece.bars.exit[column[aid]]) for aid in self.spells},
                         {100: 0, 101: 0, 102: 0, 103: 0, 104: 0}, "open at the slice's end, or ended otherwise")
        earlier = store.PanelStore(self.root).train(D(2024, 1, 2), D(2024, 4, 12), history=20, run_key="k")
        self.assertEqual(int(earlier.bars.exit[earlier.aids.tolist().index(101)]), 1, "its spell ended by a deal")
        self.assertEqual(piece.bars.hs.tolist()[REF], [config.HS_FLOOR_BP / 1e4] * 2,
                         "a half-spread is never under the registered 3 bp")

    def test_from_the_universe_deploy_on_the_tradable_row_decides(self):
        days = [d for d, _ in sessions(D(2024, 1, 2), D(2024, 6, 28))]
        aids = [*store.REF_AIDS, *sorted(self.spells)]
        tradable = np.ones((len(days), len(aids)), dtype=bool)
        tradable[:, :REF] = False
        tradable[days.index(D(2024, 5, 15)):, aids.index(100)] = False       # dropped from the allow-list
        hand_store(self.root, self.spells, tradable=tradable, live_from=D(2024, 5, 1))
        panel = store.PanelStore(self.root)
        universe = panel.universe()
        self.assertEqual(panel.live_from, D(2024, 5, 1))
        self.assertIsNone(panel.tradable_aids(D(2024, 4, 30)))
        self.assertIn("ZQAA", universe.tradable(D(2024, 4, 30)))
        self.assertIn("ZQAA", universe.tradable(D(2024, 5, 14)))
        self.assertNotIn("ZQAA", universe.tradable(D(2024, 5, 15)))
        self.assertNotIn("ZQAA", universe.tradable(D(2024, 7, 10)), "after the store's last session: its last row")
        self.assertIn("ZQNEW", universe.tradable(D(2024, 7, 10)))
        piece = panel.train(D(2024, 1, 2), D(2024, 6, 28), history=20, run_key="k")
        rows = {d: i for i, d in enumerate(days[-piece.bars.n:])}
        column = piece.aids.tolist().index(100)
        self.assertTrue(piece.bars.elig0[rows[D(2024, 5, 14)], column])
        self.assertFalse(piece.bars.elig0[rows[D(2024, 5, 15)]:, column].any())
        self.assertEqual(panel.elig0_row(D(2024, 5, 15), [100, 103]).tolist(), [False, True])
        self.assertEqual(panel.elig0_row(D(2024, 5, 14), [100, 103, 104]).tolist(), [True, True, True])

    def test_a_universe_that_cannot_be_read_is_none(self):
        hand_universe(self.root, self.spells)
        folder = self.root / "universe"
        manifest = json.loads((folder / store.UNIVERSE_MANIFEST).read_text())

        def rewrite(assets) -> None:
            data = json.dumps(assets).encode()
            (folder / "assets.json").write_bytes(data)
            (folder / store.UNIVERSE_MANIFEST).write_text(json.dumps(
                {**manifest, "sha256": {**manifest["sha256"], "assets.json": hashlib.sha256(data).hexdigest()}}))

        good = json.loads((folder / "assets.json").read_text())
        for bad in ([], {}, {**good, "1": {**good["1"], "symbol": "QQQ"}}, {k: v for k, v in good.items() if k != "12"},
                    {**good, "100": {"spells": [["ZQAA"]]}}, {**good, "x": {}}, {**good, "100": {"spells": [["Z", "soon", None]]}}):
            rewrite(bad)
            with self.subTest(bad=str(bad)[:40]), self.assertRaises(MissingData):
                store.Universe(self.root)
        rewrite(good)
        self.assertEqual(len(store.Universe(self.root).table()), REF + 5)

    def test_write_universe_refuses_what_it_cannot_read(self):
        ref = {aid: {"symbol": symbol} for aid, symbol in zip(store.REF_AIDS, config.REF)}
        member = {"spells": [["ZQAA", D(2023, 1, 3), None, None]]}
        for bad in ({**ref, 100: {**member, "masked": "sleepy"}}, {**ref, 50: member}, {100: member},
                    {**ref, 100: {"spells": [["ZQAA", D(2023, 1, 3), D(2023, 1, 3), "deal"]]}},
                    {**ref, 100: {"spells": [["ZQAA", D(2023, 1, 3), D(2024, 1, 3), None]]}},
                    {**ref, 100: {"spells": [["ZQAA", D(2023, 1, 3), D(2024, 1, 3), "bought"]]}},
                    {**ref, 100: {"spells": [["ZQAA", D(2023, 1, 3), None, "deal"]]}},
                    {**ref, 1: {"symbol": "QQQ"}}, {**ref, 100: {"spells": []}}, {**ref, 100: {**member, "ref": True}}):
            with self.subTest(bad=str(bad)[-60:]), self.assertRaises(ValueError):
                store.write_universe(self.root, assets=bad, salt=synth.TEST_SALT)
        self.assertFalse(self.root.exists(), "a refused universe writes nothing")


class TheSalt(unittest.TestCase):
    """D8: run_salt = sha256(SALT | run key); the salt is written once and is in no manifest."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "equity-daily"
        self.assets = {**{aid: {"symbol": s} for aid, s in zip(store.REF_AIDS, config.REF)},
                       100: {"spells": [["ZQAA", D(2023, 1, 3), None, None]]}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_formulas(self):
        salt = synth.TEST_SALT
        run = store.run_salt(salt, "sha|train|2022-01-03")
        self.assertEqual(run, hashlib.sha256(salt + b"sha|train|2022-01-03").digest())
        self.assertEqual(store.dither_key(run), hashlib.sha256(run + b"|dither|").digest())
        digests = [hashlib.sha256(run + b"|sector|" + str(j).encode()).digest() for j in range(11)]
        perm = store.sector_perm(run)
        self.assertEqual(perm.tolist(), [sorted(digests).index(d) for d in digests])
        self.assertEqual((perm.dtype, sorted(perm.tolist())), (np.dtype(np.int8), list(range(11))))
        for bad in (b"short", "text", None, bytes(31)):
            with self.assertRaises(ValueError):
                store.run_salt(bad, "k")
            with self.assertRaises(ValueError):
                store.dither_key(bad)

    def test_an_id_is_the_first_31_bits_of_its_hash(self):
        run = store.run_salt(synth.TEST_SALT, "k")
        table = list(range(100, 700))
        ids = store.ids_for(table, run, table=table)
        self.assertEqual((ids.dtype, config.ID_BITS), (np.dtype(np.int32), 31))
        self.assertTrue((ids >= 0).all())
        for aid, got in list(zip(table, ids.tolist()))[::37]:
            digest = hashlib.sha256(run + b"|id|" + str(aid).encode()).digest()
            self.assertEqual(got, int.from_bytes(digest[:4], "big") >> 1)
        self.assertEqual(len(set(ids.tolist())), len(table))
        with self.assertRaises(ValueError):
            store.ids_for([100, 999], run, table=table)
        self.assertEqual(store.ids_for([], run, table=table).shape, (0,))

    def test_the_salt_is_written_once_and_never_rewritten(self):
        store.write_universe(self.root, assets=self.assets, salt=synth.TEST_SALT)
        self.assertEqual(store.read_salt(self.root), synth.TEST_SALT)
        store.write_universe(self.root, assets=self.assets)                      # no salt handed in: the kept one
        store.write_universe(self.root, assets=self.assets, salt=synth.TEST_SALT)
        self.assertEqual(store.read_salt(self.root), synth.TEST_SALT)
        with self.assertRaises(ValueError) as caught:
            store.write_universe(self.root, assets=self.assets, salt=bytes(32))
        self.assertIn("never rewritten", str(caught.exception))
        self.assertEqual(store.read_salt(self.root), synth.TEST_SALT)
        self.assertEqual(stat.S_IMODE((self.root / "universe" / store.SALT_FILE).stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((self.root / "universe").stat().st_mode), 0o700)

    def test_a_universe_with_no_salt_draws_one(self):
        store.write_universe(self.root, assets=self.assets)
        first = store.read_salt(self.root)
        self.assertEqual(len(first), store.SALT_BYTES)
        other = Path(self.tmp.name) / "other"
        store.write_universe(other, assets=self.assets)
        self.assertNotEqual(store.read_salt(other), first)

    def test_the_salt_is_in_no_manifest_and_no_file_but_its_own(self):
        manifest = store.write_universe(self.root, assets=self.assets, salt=synth.TEST_SALT, spells=[],
                                        source={"known_through": D(2024, 1, 2)}, tradable={"stock": ["ZQAA"]})
        self.assertEqual(manifest["salt"], hashlib.sha256(synth.TEST_SALT).hexdigest()[:8])
        self.assertEqual(sorted(manifest["sha256"]), sorted(store.UNIVERSE_FILES))
        self.assertNotIn(store.SALT_FILE, manifest["sha256"])
        for path in (self.root / "universe").iterdir():
            if path.name == store.SALT_FILE:
                continue
            data = path.read_bytes()
            self.assertNotIn(synth.TEST_SALT, data, path.name)
            self.assertNotIn(synth.TEST_SALT.hex().encode(), data, path.name)
            self.assertEqual(hashlib.sha256(data).hexdigest(), manifest["sha256"].get(path.name, hashlib.sha256(data).hexdigest()))

    def test_a_missing_or_short_salt_is_no_salt(self):
        with self.assertRaises(MissingData):
            store.read_salt(self.root)
        (self.root / "universe").mkdir(parents=True)
        (self.root / "universe" / store.SALT_FILE).write_bytes(b"too short")
        with self.assertRaises(MissingData):
            store.read_salt(self.root)


class TheSyntheticPanels(unittest.TestCase):
    """league/xs/synth.py: what every package's tests build on."""

    ARGS = {"n_assets": 30, "start": D(2023, 1, 3), "end": D(2025, 12, 31)}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def panel(self, name: str, maker=synth.synthetic_panel, **kwargs):
        root = maker(Path(self.tmp.name) / name / "equity-daily", **{**self.ARGS, **kwargs})
        return root, store.PanelStore(root)

    def arrays(self, root: Path) -> dict[str, np.ndarray]:
        return {name[:-4]: np.load(root / "panel" / name) for name in store.PANEL_FILES}

    def test_the_same_arguments_write_the_same_bytes(self):
        a, pa = self.panel("a", seed=3)
        b, pb = self.panel("b", seed=3)
        c, pc = self.panel("c", seed=4)
        self.assertEqual(pa.manifest()["sha256"], pb.manifest()["sha256"])
        self.assertEqual((a / "universe" / "assets.json").read_bytes(), (b / "universe" / "assets.json").read_bytes())
        self.assertNotEqual(pa.manifest()["sha256"]["raw.npy"], pc.manifest()["sha256"]["raw.npy"])
        self.assertEqual(store.read_salt(a), synth.TEST_SALT)

    def test_it_is_a_whole_root_with_e1s_store_for_the_ref_symbols(self):
        from league.equity.store import EquityStore

        root, panel = self.panel("a", gate=True)
        e1 = EquityStore(root)
        self.assertEqual(sorted(e1.symbols()), sorted(config.REF))
        got = self.arrays(root)
        bars = e1.bars(list(config.REF), "validation", history=0)
        rows = [got["days"].tolist().index(int(d)) for d in bars.days[bars.first:]]
        for col, symbol in enumerate(config.REF):
            self.assertTrue(np.array_equal(got["raw"][rows, col], bars.raw[symbol][bars.first:]), symbol)
        self.assertTrue(np.array_equal(got["adj"][:, :REF], np.round(got["raw"][:, :REF, :4], 2)),
                        "adjustment=all is rounded to the cent, as the vendor's is")
        self.assertFalse(got["member"][:, :REF].any())
        self.assertTrue((root / "GATE").is_file())
        self.assertFalse((self.panel("b")[0] / "GATE").exists())

    def test_no_2020_session_and_every_session_otherwise(self):
        root, panel = self.panel("a", start=D(2019, 6, 3), end=D(2021, 6, 30), n_assets=14)
        days = [dt.date(1970, 1, 1) + dt.timedelta(days=int(d)) for d in self.arrays(root)["days"]]
        self.assertEqual(days, [d for d, _ in sessions(D(2019, 6, 3), D(2021, 6, 30))])
        self.assertNotIn(2020, {d.year for d in days})

    def test_churn_keeps_the_count_and_moves_the_names(self):
        root, panel = self.panel("a", churn=0.1)
        got = self.arrays(root)
        self.assertTrue((got["member"].sum(axis=1) == 30).all())
        self.assertGreater(got["member"].any(axis=0).sum(), 30 + 6)
        self.assertEqual(self.arrays(self.panel("b", churn=0.0)[0])["member"].any(axis=0).sum(), 30)
        self.assertTrue(got["tradable"][:, REF:].all() and not got["tradable"][:, :REF].any())
        exits = panel.universe().manifest()["exits"]
        self.assertEqual(sum(exits.values()), int(got["member"].any(axis=0).sum()) - 30)

    def test_raw_on_four_decimals_adj_on_cents_and_a_cent_panel_on_the_cent_grid(self):
        got = self.arrays(self.panel("a")[0])
        prices = got["raw"][:, REF:, :4]
        self.assertTrue(np.array_equal(prices, np.round(prices, 4)) and not np.array_equal(prices, np.round(prices, 2)))
        self.assertTrue(np.array_equal(got["adj"], np.round(got["adj"], 2)))
        self.assertTrue((prices[:, :, 1] >= np.maximum(prices[:, :, 0], prices[:, :, 3])).all())
        self.assertTrue((prices[:, :, 2] <= np.minimum(prices[:, :, 0], prices[:, :, 3])).all())
        self.assertTrue((got["raw"][:, :, 4] >= 1).all() and np.array_equal(got["raw"][:, :, 4], np.floor(got["raw"][:, :, 4])))
        cent_root, cent = self.panel("cent", maker=synth.cent_panel, n_assets=50)
        cents = self.arrays(cent_root)
        self.assertEqual(cents["member"][-1].sum(), 50)
        self.assertTrue(np.array_equal(cents["raw"][:, :, :4], np.round(cents["raw"][:, :, :4], 2)), "SPY's and all")
        differs = (np.abs(cents["adj"][:, REF:, 3] - cents["raw"][:, REF:, 3]) > 0.005).any(axis=0)
        self.assertGreaterEqual(int(differs.sum()), 10, "with dividends: the adjusted history is not the raw one")
        self.assertTrue(np.array_equal(cents["adj"][-1], cents["raw"][-1, :, :4]), "the last session is unadjusted")

    def test_dividends_and_splits_scale_the_history_before_them(self):
        root, _ = self.panel("a", dividends={100: [(D(2024, 6, 3), 1.0)]}, splits={101: (D(2024, 6, 3), 2.0)}, churn=0.0)
        got = self.arrays(root)
        row = got["days"].tolist().index(ordinal(D(2024, 6, 3)))
        col = got["aids"].tolist().index(100)
        factor = 1.0 - 1.0 / got["raw"][row - 1, col, 3]
        self.assertTrue(np.allclose(got["adj"][:row, col, 3], np.round(got["raw"][:row, col, 3] * factor, 2)))
        self.assertTrue(np.array_equal(got["adj"][row:, col, 3], np.round(got["raw"][row:, col, 3], 2)))
        col = got["aids"].tolist().index(101)
        self.assertTrue(np.allclose(got["adj"][:row, col, 3], np.round(got["raw"][:row, col, 3] / 2.0, 2)))
        self.assertAlmostEqual(float(got["raw"][row, col, 0] / got["raw"][row - 1, col, 3]), 0.5, delta=0.05)
        for bad in ({"dividends": {100: [(D(2024, 6, 2), 1.0)]}}, {"splits": {999: (D(2024, 6, 3), 2.0)}},
                    {"vanish": [(999, D(2024, 6, 3))]}, {"masked": {999: "no_bars"}}, {"n_assets": 1}):
            with self.subTest(bad=list(bad)), self.assertRaises(ValueError):
                self.panel("bad", **bad)

    def test_two_vintages_hold_one_raw_history(self):
        args = {"dividends": {100: [(D(2025, 9, 15), 0.8)]}, "churn": 0.0}
        early_root, early = self.panel("early", as_of=D(2025, 6, 30), **args)
        late_root, late = self.panel("late", **args)
        a, b = self.arrays(early_root), self.arrays(late_root)
        self.assertEqual(early.fetched_through, D(2025, 6, 30))
        n = a["days"].shape[0]
        self.assertTrue(np.array_equal(a["raw"], b["raw"][:n], equal_nan=True))
        col = a["aids"].tolist().index(100)
        self.assertTrue(np.array_equal(a["adj"][:, col, 3], np.round(a["raw"][:, col, 3], 2)), "not yet restated")
        self.assertTrue((b["adj"][:n, col, 3] < b["raw"][:n, col, 3]).all(), "restated by the later dividend")

    def test_a_name_whose_bars_end_and_a_masked_one(self):
        root, panel = self.panel("a", vanish=[(103, D(2025, 3, 14))], masked={104: "no_bars"}, churn=0.0)
        got = self.arrays(root)
        col = got["aids"].tolist().index(103)
        row = got["days"].tolist().index(ordinal(D(2025, 3, 14)))
        self.assertTrue(np.isfinite(got["raw"][row, col]).all() and np.isnan(got["raw"][row + 1:, col]).all())
        self.assertTrue(got["member"][row + 1:, col].all(), "still a member: its bars ended")
        self.assertEqual(panel.manifest()["vanished"], [103])
        self.assertEqual(panel.universe().masked(104), "no_bars")
        self.assertNotIn(104, [aid for aid, _ in panel.universe().members(D(2025, 6, 2))])
        self.assertLess(panel.manifest()["coverage"]["2025"]["share"], 1.0)

    def test_a_names_statistical_sector_is_the_fund_it_was_built_on(self):
        root, panel = self.panel("a", n_assets=120, churn=0.0)
        bars = panel.bars("validation", history=20, run_key="k").bars
        needs = Needs("sp500", 20, 10, "weekly", 0, 60)
        book = {"needs": needs, "cash": 0.0, "equity": 0.0, "budget": 0.0, "params": {}}
        first = ctx.derive(ctx.inputs_from_panel(bars, bars.first + 5, **book))
        later = ctx.derive(ctx.inputs_from_panel(bars, bars.first + 200, **book))
        self.assertGreaterEqual(int(first.elig.sum()), 115)
        both = first.elig & later.elig
        self.assertGreater(float((first.sector[both] == later.sector[both]).mean()), 0.9, "a sector is a stable label")
        sizes = sorted(np.bincount(first.sector[first.elig], minlength=11).tolist(), reverse=True)
        self.assertGreaterEqual(sizes[0], 30)
        self.assertGreaterEqual(len([s for s in sizes if s]), 8)
        cells = set(first.cell[first.elig].tolist())
        self.assertIn(config.SMALL_CELL, cells)
        self.assertTrue(any(c % 100 >= 10 for c in cells if c != config.SMALL_CELL), "a sector large enough for beta groups")
        self.assertEqual(round(sum(synth.SECTOR_SHARES), 9), 1.0)

    def test_a_planted_panel_pays_the_names_its_signal_ranks_first(self):
        base = self.arrays(self.panel("plain", seed=9, churn=0.0)[0])
        for signal in synth.SIGNALS:
            planted = self.arrays(self.panel(f"planted-{signal}", maker=synth.planted_panel, seed=9, churn=0.0,
                                             edge_year=0.5, signal=signal)[0])
            gain = np.log(planted["raw"][-1, REF:, 3] / planted["raw"][0, REF:, 3]) \
                - np.log(base["raw"][-1, REF:, 3] / base["raw"][0, REF:, 3])
            years = planted["days"].shape[0] / 252.0
            self.assertGreater(float(gain.min()), -1e-3, "a planted edge never costs a name")
            self.assertAlmostEqual(float(gain.mean()) / years, 0.5 / 3.0, delta=0.06,
                                   msg=f"{signal}: the top third of each fund's names earn the edge")
        with self.assertRaises(ValueError):
            synth.planted_panel(Path(self.tmp.name) / "bad", signal="value")

    def test_the_i6_helper_draws_decision_days_under_one_run_key_and_one_aid_set(self):
        root, panel = self.panel("a", gate=True, end=D(2026, 6, 30))
        cases = synth.same_ctx_cases(root, history=20, count=4, seed=1)
        self.assertEqual([sorted(case) for case in cases][0],
                         ["aids", "all_rows", "columns", "common", "day", "gym", "index", "raw_rows", "run_key",
                          "slice", "straddles"])
        self.assertEqual(sorted(cases[0]["common"]),
                         ["budget", "cash", "closed", "dither_key", "elig0", "equity", "ids", "needs", "params",
                          "positions", "rejects", "sector_perm"])
        for case in cases:
            self.assertIn(case["day"], panel.sessions("validation"))
            self.assertEqual(case["run_key"], f"i6|{case['day'].isoformat()}")
            self.assertEqual(len(case["columns"]), case["aids"].shape[0])
            self.assertEqual(case["gym"].days.shape[0], 253)
            self.assertEqual(int(case["gym"].days[-1]), ordinal(case["day"]))
        self.assertEqual([c["day"] for c in synth.same_ctx_cases(root, history=20, count=4, seed=1)],
                         [c["day"] for c in cases])
        with self.assertRaises(StoreRefused):
            synth.same_ctx_cases(root, history=20, count=2, window="look")
        gate = mint_equity_gate_capability(root, "the helper's test")
        sealed = synth.same_ctx_cases(root, history=20, count=2, window="look", gate=gate)
        self.assertEqual(len(sealed), 2)
        train = synth.same_ctx_cases(root, history=20, count=6, window="train")
        self.assertTrue({case["day"].year for case in train} <= {2023, 2024})
        for case in [*cases, *sealed, *train]:
            live = ctx.inputs_from_fetch(case["raw_rows"], case["all_rows"], day=case["day"],
                                         columns=case["columns"], **case["common"])
            self.assertEqual(ctx.ctx_bytes(ctx.build(live)), ctx.ctx_bytes(ctx.build(case["gym"])), case["day"])


if __name__ == "__main__":
    unittest.main()
