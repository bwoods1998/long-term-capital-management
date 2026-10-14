"""THE SOURCE GAP (Oct 14, 2026; scripts/data/nightly.py, scripts/data/sip.py): a root whose SIP minute the source never
serves holds its forward day only while its bars may still arrive. A synthetic gateway that never returns one minute of
SLV, a fake data box that keeps canonical files and journal records the way `backfill.py` does, the real relay
(`sip.relay_day`) and the real proof (`nightly.sip_proof`): the retry clock, the hand-off to the forward gap ledger, the
publication that says the day is source-incomplete (never complete, nothing filled) and the later days that go on.
Invented bars only."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "scripts" / "data"
if str(DATA) not in sys.path:
    sys.path.insert(0, str(DATA))

import nightly as nt  # noqa: E402
import sip as sp  # noqa: E402  (the module nightly's real relay imports: one SIPError class)
import storelib as sl  # noqa: E402

UTC = dt.timezone.utc
THETA = "thetadata option_history_greeks_first_order underlying_price exp=2026-10-16 strike_range=1 calls"
MONDAY, TUESDAY, WEDNESDAY = dt.date(2026, 10, 12), dt.date(2026, 10, 13), dt.date(2026, 10, 14)
FRIDAY = dt.date(2026, 10, 2)
#: The bar SLV's source never serves: it starts at 13:45 ET, so its completion minute is 826.
NEVER = 13 * 60 + 45


def calendar():
    return sl.Calendar({dt.date(2026, 11, 26): None})


def bar(day, minute, close=30.0):
    stamp = dt.datetime.combine(day, dt.time(), sp.NY) + dt.timedelta(minutes=minute)
    return {"t": stamp.astimezone(UTC).isoformat(), "o": close, "h": close + 0.1, "l": close - 0.1, "c": close, "v": 100}


class NeverGateway:
    """The gateway's stock-bars route for invented bars: every regular-session minute of every symbol, but SLV's
    13:45 ET bar on the days in `short`, which it never returns. `revise` changes one of SLV's bars (a source still at
    work), so its packet differs."""

    def __init__(self, short=(MONDAY, FRIDAY)):
        self.short, self.revise, self.calls = set(short), 0, []

    def fetch(self, symbols, day, hours):
        self.calls.append((day, tuple(symbols)))
        out = {}
        for symbol in symbols:
            rows = [bar(day, m) for m in range(*hours) if not (symbol == "SLV" and day in self.short and m == NEVER)]
            if symbol == "SLV" and self.revise:
                rows[0] = bar(day, hours[0], close=30.0 + self.revise / 100)
            out[symbol] = rows
        return out


class DataBox:
    """A data box as the nightly sees it: NBBO and the vendor's option-implied underlying per root and pulled day, the
    journal's records, `sip-status` from the canonical files, and `ingest-underlying` that replaces a stock root's file
    with its complete SIP packet only (backfill.py's rule)."""

    ROOTS = ("SLV", "SPY", "XSP")

    def __init__(self):
        self.running, self.calls, self.uploads = True, [], {}
        self.files, self.records = {}, {}

    def put(self, kind, root, day, blob, source):
        rel = sl.rel_path(kind, root, day)
        self.files[f"{sl.STORE_ROOT}/{rel}"] = blob
        self.records[rel] = {**sl.file_record(kind, root, day, rows=1, sha256=hashlib.sha256(blob).hexdigest(),
                                              size=len(blob), source=source, fetched_at="t")}

    def wake(self):
        self.calls.append("wake")

    def sleep(self, wake_at):
        self.calls.append(("sleep", wake_at))

    def backfill_running(self):
        return self.running

    def stop_backfill(self):
        self.running = False

    def start_backfill(self, args):
        self.running = True

    def upload(self, path, blob, mode):
        self.uploads[path] = blob

    def download(self, path):
        return self.files[path]

    def run(self, args, timeout):
        words = args.split()
        self.calls.append(tuple(words[:2]))
        if words[:2] == ["backfill.py", "run"]:
            day = dt.date.fromisoformat(words[words.index("--forward-days") + 1])
            for root in self.ROOTS:
                if sl.rel_path("nbbo", root, day) not in self.records:
                    self.put("nbbo", root, day, f"nbbo-{root}-{day}".encode(), "thetadata option_history_quote")
                    self.put("underlying", root, day, f"theta-{root}-{day}".encode(), THETA)
            return True, ""
        if words[:2] == ["backfill.py", "records"]:
            day = words[words.index("--date") + 1]
            return True, "\n".join(json.dumps(r) for r in self.records.values() if r["date"] == day)
        if words[:2] == ["backfill.py", "sip-status"]:
            day = dt.date.fromisoformat(words[words.index("--date") + 1])
            hours = calendar().hours(day)
            rows = []
            for root in sorted({r["root"] for r in self.records.values() if r["kind"] == "nbbo" and r["date"] == str(day)}
                               - {"XSP", "SPXW"}):
                record = self.records.get(sl.rel_path("underlying", root, day)) or {}
                row = {"root": root, "day": str(day), "source": record.get("source"), "source_symbol": record.get("source_symbol"),
                       "source_symbol_expected": root, "file_sha256": record.get("sha256"),
                       "packet_sha256": record.get("packet_sha256"), **sl.sip_coverage([], hours), "status": "pending"}
                if record.get("source") == sl.SIP_SOURCE:
                    row.update(sl.sip_coverage(record["minutes"], hours), status="complete",
                               verification="current_file_hash_and_grid")
                rows.append(row)
            return True, json.dumps({"day": str(day), "roots": rows})
        if words[:2] == ["backfill.py", "ingest-underlying"]:
            for packet in json.loads(self.uploads[words[words.index("--input") + 1]]):
                day = dt.date.fromisoformat(packet["day"])
                minutes = [r["minute"] for r in packet["rows"]]
                if not sl.sip_coverage(minutes, calendar().hours(day))["complete"]:
                    return False, "incomplete SIP session cannot replace canonical underlying data"
                self.put("underlying", packet["root"], day, f"sip-{packet['root']}-{day}".encode(), sl.SIP_SOURCE)
                self.records[sl.rel_path("underlying", packet["root"], day)].update(
                    packet_sha256=sp.packet_digest(packet), source_symbol=packet["source_symbol"], minutes=minutes)
            return True, "{}"
        return False, "unknown"


class Gate:
    box_id = "sb_gate"

    def __init__(self):
        self.uploads, self.calls = {}, []

    def wake(self):
        pass

    def sleep(self, wake_at):
        pass

    def upload(self, path, blob, mode):
        self.uploads[path] = blob

    def run(self, args, timeout):
        self.calls.append(args)
        return True, "{}"


class Clock:
    def __init__(self, at):
        self.at = at

    def __call__(self):
        return self.at

    def advance(self, **delta):
        self.at += dt.timedelta(**delta)


def images():
    return {"gate": {"current": {"box_id": "sb_gate", "checkpoints": ["sbcp_gate"], "roots": list(DataBox.ROOTS)}}}


def job(clock, *, gateway=None, data=None, gate=None, records=None):
    gateway = gateway or NeverGateway()
    data, gate, records = data or DataBox(), gate or Gate(), records if records is not None else images()
    made = []

    def checkpoint():
        made.append(f"sbcp_{len(made) + 1:04d}")
        return made[-1]

    def relay(day, handle, source_incomplete=None):
        return sp.relay_day(day, handle, gateway=gateway, calendar=calendar(), source_root=lambda root, d: root,
                            source_incomplete=source_incomplete)

    nightly = nt.Nightly(data=data, gate=gate, images=records, save=lambda d: None, checkpoint=checkpoint,
                         calendar=calendar(), last_backfill_args="--stages 1", log=lambda text: None, clock=clock,
                         relay=relay, sip_check=nt.sip_proof)
    return nightly, data, gate, gateway, made


def at(text):
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


class TheClock(unittest.TestCase):
    def test_the_hand_off_waits_six_hours_and_the_next_close_but_never_more_than_a_day(self):
        cal = calendar()
        # Monday's gap first seen Tuesday 06:05Z: six hours is 12:05Z, Tuesday's close 20:00Z (16:00 EDT) is later.
        self.assertEqual(nt.handoff_at(MONDAY, at("2026-10-13T06:05:00Z"), cal), at("2026-10-13T20:00:00Z"))
        # First seen after that close (a deploy at 21:00Z): six hours from then.
        self.assertEqual(nt.handoff_at(MONDAY, at("2026-10-14T21:00:00Z"), cal), at("2026-10-15T03:00:00Z"))
        # Friday's gap first seen Saturday 06:05Z: Monday's close is 62 h off, so a day, not the weekend.
        self.assertEqual(nt.handoff_at(FRIDAY, at("2026-10-03T06:05:00Z"), cal), at("2026-10-04T06:05:00Z"))
        # The day before Thanksgiving waits for the half day's 13:00 close (18:00Z in winter).
        self.assertEqual(nt.next_session_close(dt.date(2026, 11, 25), sl.Calendar({dt.date(2026, 11, 26): None,
                                                                                dt.date(2026, 11, 27): (570, 780)})),
                         at("2026-11-27T18:00:00Z"))


class HandOff(unittest.TestCase):
    def test_a_minute_the_source_never_serves_holds_the_day_then_hands_the_root_off_as_source_incomplete(self):
        clock = Clock(at("2026-10-13T06:05:00Z"))
        nightly, data, gate, gateway, made = job(clock)
        with self.assertRaisesRegex(sp.SIPError, "SLV 389/390") as caught:
            nightly.run(MONDAY)
        self.assertEqual([g["root"] for g in caught.exception.coverage], ["SLV"])
        night = nightly.state(MONDAY)
        watch = night["sip_watch"]["SLV"]
        self.assertEqual((watch["known"], watch["expected"], watch["missing_minutes"]), (389, 390, [NEVER + 1]))
        self.assertEqual((watch["first_seen"], watch["attempts"]), ("2026-10-13T06:05:00+00:00", 1))
        self.assertNotIn("pulled", night)
        self.assertEqual((made, gate.uploads), ([], {}))
        # Strict while the bars may still arrive: six hours unchanged is not enough before the next session's close.
        for minutes in (5, 6 * 60, 7 * 60):
            clock.at = at("2026-10-13T06:05:00Z") + dt.timedelta(minutes=minutes)
            with self.assertRaises(sp.SIPError):
                nightly.run(MONDAY)
        self.assertEqual(nightly.state(MONDAY)["sip_watch"]["SLV"]["attempts"], 4)
        self.assertEqual(nightly.state(MONDAY)["sip_watch"]["SLV"]["first_seen"], "2026-10-13T06:05:00+00:00")
        # Nothing of the day reached the store's SIP files while it was held: the strict relay ingests nothing.
        self.assertTrue(all(r["source"] == THETA for r in data.records.values() if r["kind"] == "underlying"))
        self.assertTrue(all("/sip-partial-2026-10-12-SLV-" in p for p in data.uploads if "partial" in p))

        clock.at = at("2026-10-13T20:01:00Z")
        result = nightly.run(MONDAY)
        self.assertEqual(made, ["sbcp_0001"])
        gap = result["sip_gaps"]["SLV"]
        self.assertEqual((gap["status"], gap["complete"], gap["known"], gap["missing_minutes"]),
                         ("source_incomplete", False, 389, [NEVER + 1]))
        self.assertEqual((gap["unchanged_since"], gap["handed_off_at"]),
                         ("2026-10-13T06:05:00+00:00", "2026-10-13T20:01:00+00:00"))
        self.assertTrue(gap["quarantine"].startswith("/data/work/sip-partial-2026-10-12-SLV-"))
        self.assertIn(gap["quarantine"], data.uploads)                       # the packet stays quarantined
        self.assertNotIn("sip_watch", result)
        # The complete root went in as SIP; SLV keeps the vendor's own series, never a filled SIP grid.
        under = {r["root"]: r for r in data.records.values() if r["kind"] == "underlying" and r["date"] == str(MONDAY)}
        self.assertEqual((under["SPY"]["source"], under["SLV"]["source"], under["XSP"]["source"]), (sl.SIP_SOURCE, THETA, THETA))
        self.assertEqual(gate.uploads[f"{sl.STORE_ROOT}/{sl.rel_path('underlying', 'SLV', MONDAY)}"], b"theta-SLV-2026-10-12")
        # The proof binds the exact files and says SLV is short, never "complete".
        proof = result["sip_coverage"]
        self.assertEqual((proof["status"], proof["roots"]), ("source_incomplete", ["SLV", "SPY"]))
        (row,) = proof["source_incomplete"]
        self.assertEqual((row["root"], row["status"], row["complete"], row["canonical_status"], row["canonical_source"]),
                         ("SLV", "source_incomplete", False, "pending", THETA))
        self.assertEqual(row["file_sha256"], hashlib.sha256(b"theta-SLV-2026-10-12").hexdigest())
        self.assertEqual([(g["day"], g["root"], g["known"], g["expected"]) for g in result["source_incomplete"]],
                         [("2026-10-12", "SLV", 389, 390)])
        # The hand-off fetched the same packet again; one gateway call a try.
        self.assertEqual(len(gateway.calls), 5)
        # A rerun of the finished day does nothing and still says so.
        again = nightly.run(MONDAY)
        self.assertTrue(again["already"])
        self.assertEqual((again["sip_coverage"]["status"], len(again["source_incomplete"])), ("source_incomplete", 1))
        self.assertEqual(len(gateway.calls), 5)

    def test_a_changed_packet_restarts_the_clock(self):
        clock = Clock(at("2026-10-13T06:05:00Z"))
        nightly, _, _, gateway, made = job(clock)
        with self.assertRaises(sp.SIPError):
            nightly.run(MONDAY)
        clock.at = at("2026-10-13T16:00:00Z")
        gateway.revise = 1                                              # the source is still at work on SLV's day
        with self.assertRaises(sp.SIPError):
            nightly.run(MONDAY)
        watch = nightly.state(MONDAY)["sip_watch"]["SLV"]
        self.assertEqual((watch["first_seen"], watch["attempts"]), ("2026-10-13T16:00:00+00:00", 1))
        clock.at = at("2026-10-13T20:01:00Z")                          # past the close, but 4 h unchanged
        with self.assertRaises(sp.SIPError):
            nightly.run(MONDAY)
        self.assertEqual(made, [])
        clock.at = at("2026-10-13T22:00:00Z")
        self.assertEqual(nightly.run(MONDAY)["sip_gaps"]["SLV"]["unchanged_since"], "2026-10-13T16:00:00+00:00")

    def test_a_handed_root_whose_packet_changes_is_held_again(self):
        clock = Clock(at("2026-10-13T06:05:00Z"))
        nightly, data, gate, gateway, made = job(clock)
        with self.assertRaises(sp.SIPError):
            nightly.run(MONDAY)
        clock.at = at("2026-10-13T20:01:00Z")
        state = nightly.state(MONDAY)
        sha = state["sip_watch"]["SLV"]["packet_sha256"]
        # The ledger holds SLV for one packet only: the relay refuses another one.
        gateway.revise = 2
        with self.assertRaisesRegex(sp.SIPError, "SLV 389/390"):
            sp.relay_day(MONDAY, data, gateway=gateway, calendar=calendar(), source_root=lambda r, d: r,
                         source_incomplete={"SLV": sha})
        with self.assertRaises(sp.SIPError):
            nightly.run(MONDAY)
        self.assertNotIn("sip_gaps", nightly.state(MONDAY))
        self.assertEqual(nightly.state(MONDAY)["sip_watch"]["SLV"]["first_seen"], "2026-10-13T20:01:00+00:00")
        self.assertEqual(made, [])

    def test_another_short_root_still_holds_the_day(self):
        clock = Clock(at("2026-10-13T06:05:00Z"))
        nightly, data, gate, gateway, made = job(clock)
        with self.assertRaises(sp.SIPError):
            nightly.run(MONDAY)
        clock.at = at("2026-10-13T20:01:00Z")
        real = gateway.fetch

        def spy_short(symbols, day, hours):
            rows = real(symbols, day, hours)
            if "SPY" in rows:
                rows["SPY"] = rows["SPY"][:-1]                          # SPY newly short: its clock starts now
            return rows
        gateway.fetch = spy_short
        with self.assertRaisesRegex(sp.SIPError, "SPY 389/390"):
            nightly.run(MONDAY)
        watch = nightly.state(MONDAY)["sip_watch"]
        self.assertEqual(watch["SLV"]["first_seen"], "2026-10-13T06:05:00+00:00")
        self.assertEqual(watch["SPY"]["first_seen"], "2026-10-13T20:01:00+00:00")
        self.assertEqual(made, [])

    def test_a_fridays_gap_waits_a_day_not_the_weekend(self):
        clock = Clock(at("2026-10-03T06:05:00Z"))
        nightly, *_, made = job(clock)
        with self.assertRaises(sp.SIPError):
            nightly.run(FRIDAY)
        clock.at = at("2026-10-03T12:10:00Z")
        with self.assertRaises(sp.SIPError):
            nightly.run(FRIDAY)
        clock.at = at("2026-10-04T06:05:00Z")
        self.assertEqual(nightly.run(FRIDAY)["sip_coverage"]["status"], "source_incomplete")
        self.assertEqual(made, ["sbcp_0001"])

    def test_a_complete_day_is_still_complete_and_lists_no_gap(self):
        clock = Clock(at("2026-10-14T06:05:00Z"))
        nightly, data, *_ = job(clock, gateway=NeverGateway(short=()))
        result = nightly.run(TUESDAY)
        self.assertEqual(result["sip_coverage"]["status"], "complete")
        self.assertNotIn("source_incomplete", result["sip_coverage"])
        self.assertEqual((result["source_incomplete"], result.get("sip_gaps")), ([], None))
        self.assertTrue(all(r["source"] == sl.SIP_SOURCE for r in data.records.values()
                            if r["kind"] == "underlying" and r["root"] != "XSP"))

    def test_the_proof_never_accepts_a_short_root_the_ledger_does_not_hold(self):
        data = DataBox()
        data.run(f"backfill.py run --stages 7 --forward-days {MONDAY}", 1)
        with self.assertRaisesRegex(RuntimeError, "coverage is incomplete"):
            nt.sip_proof(MONDAY, data)
        with self.assertRaisesRegex(RuntimeError, "coverage is incomplete"):
            nt.sip_proof(MONDAY, data, source_incomplete=["SLV"])          # SPY is short too
        sp.relay_day(MONDAY, data, gateway=NeverGateway(), calendar=calendar(), source_root=lambda r, d: r,
                     allow_gaps=True)
        proof = nt.sip_proof(MONDAY, data, source_incomplete=["SLV"])
        self.assertEqual((proof["status"], [r["root"] for r in proof["source_incomplete"]]), ("source_incomplete", ["SLV"]))

    def test_the_nightly_refuses_a_proof_that_claims_a_short_root_complete_or_names_another(self):
        for forged in ("complete", "other"):
            with self.subTest(forged=forged):
                clock = Clock(at("2026-10-13T06:05:00Z"))
                nightly, data, gate, _, made = job(clock)
                with self.assertRaises(sp.SIPError):
                    nightly.run(MONDAY)
                clock.at = at("2026-10-13T20:01:00Z")

                def proof(day, handle, source_incomplete=()):
                    out = nt.sip_proof(day, handle, source_incomplete)
                    if forged == "complete":
                        out = {**out, "status": "complete"}
                    else:
                        out["source_incomplete"] = [{**out["source_incomplete"][0], "root": "SPY"}]
                    return out
                nightly.sip_check = proof
                with self.assertRaisesRegex(RuntimeError, "proof differs"):
                    nightly.run(MONDAY)
                self.assertEqual((made, gate.uploads), ([], {}))
                self.assertNotIn("sip_coverage", nightly.state(MONDAY))


class TheLaterDays(unittest.TestCase):
    """The controller over the job: Monday held, then handed off; Tuesday and Wednesday go on, oldest first."""

    def test_the_nightly_goes_on_with_the_later_days_and_each_publication_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = Clock(at("2026-10-14T21:00:00Z"))                   # a deploy after two days held on Monday
            nightly, data, gate, gateway, made = job(clock)
            done_before = {d.isoformat(): "sbcp_old" for d in calendar().days(nt.FIRST_FORWARD_DAY, dt.date(2026, 10, 9))}
            (root / "nightly.json").write_text(json.dumps({"completed": done_before, "day": "2026-10-12", "retry_at": 0,
                                                           "error": "SIPError: incomplete regular-session SIP bars: SLV 389/390"}))
            controller = nt.Controller(root, root / "gym-forward.json", calendar(), run=nightly.run, clock=clock)
            first = controller.tick()
            self.assertEqual((first["phase"], first["day"]), ("retry", "2026-10-12"))
            record = json.loads((root / "nightly.json").read_text())
            self.assertEqual(record["retrying"]["day"], "2026-10-12")
            self.assertEqual(record["retrying"]["roots"], ["SLV"])
            self.assertEqual(record["retrying"]["gaps"][0]["missing_minutes"], [NEVER + 1])
            self.assertEqual(record["retrying"]["since"], "2026-10-14T21:00:00+00:00")
            while clock.at < at("2026-10-15T02:55:00Z"):              # six hours unchanged from the first try here
                clock.advance(minutes=5)
                self.assertEqual(controller.tick()["phase"], "retry")
            record = json.loads((root / "nightly.json").read_text())
            self.assertEqual((record["retrying"]["since"], record["retrying"]["attempts"]), ("2026-10-14T21:00:00+00:00", 72))
            self.assertFalse((root / "gym-forward.json").exists())
            self.assertEqual(len(gateway.calls), 72)                    # one gateway call a try, Monday's two roots
            clock.advance(minutes=5)
            done = controller.tick()
            self.assertEqual((done["phase"], done["day"]), ("complete", "2026-10-12"))
            ready = json.loads((root / "gym-forward.json").read_text())
            self.assertEqual((ready["day"], ready["sip_coverage"]["status"]), ("2026-10-12", "source_incomplete"))
            self.assertEqual([(g["day"], g["root"]) for g in ready["source_incomplete"]], [("2026-10-12", "SLV")])
            record = json.loads((root / "nightly.json").read_text())
            self.assertNotIn("retrying", record)
            self.assertEqual((record["error"], record["completed_at"]), (None, "2026-10-15T03:00:00+00:00"))
            # Tuesday, then Wednesday (due 06:00Z): complete days, and the chain still says Monday's SLV is short.
            clock.advance(minutes=1)
            self.assertEqual(controller.tick()["day"], "2026-10-13")
            ready = json.loads((root / "gym-forward.json").read_text())
            self.assertEqual((ready["day"], ready["sip_coverage"]["status"]), ("2026-10-13", "complete"))
            self.assertEqual([(g["day"], g["root"]) for g in ready["source_incomplete"]], [("2026-10-12", "SLV")])
            self.assertEqual(controller.tick()["phase"], "waiting")
            clock.at = at("2026-10-15T06:00:00Z")
            self.assertEqual(controller.tick()["day"], "2026-10-14")
            ready = json.loads((root / "gym-forward.json").read_text())
            self.assertEqual((ready["day"], ready["sip_coverage"]["status"]), ("2026-10-14", "complete"))
            self.assertEqual(len(ready["source_incomplete"]), 1)
            self.assertEqual(made, ["sbcp_0001", "sbcp_0002", "sbcp_0003"])
            completed = json.loads((root / "nightly.json").read_text())["completed"]
            self.assertEqual({d: c for d, c in completed.items() if c != "sbcp_old"},
                             {"2026-10-12": "sbcp_0001", "2026-10-13": "sbcp_0002", "2026-10-14": "sbcp_0003"})
            self.assertEqual(len(gateway.calls), 75)                    # the hand-off, Tuesday's and Wednesday's relays


class TheRetryRecord(unittest.TestCase):
    def test_the_record_keeps_the_day_its_start_and_the_roots_across_other_failures(self):
        now = at("2026-10-13T06:05:00Z")
        gap = sp.SIPError("incomplete regular-session SIP bars: SLV 389/390",
                          coverage=[{"root": "SLV", "known": 389, "expected": 390, "missing_minutes": [826],
                                     "packet_sha256": "a" * 64}])
        first = nt.retrying(None, MONDAY, gap, now)
        self.assertEqual((first["since"], first["attempts"], first["roots"]), (now.isoformat(), 1, ["SLV"]))
        later = nt.retrying(first, MONDAY, RuntimeError("gateway stock bars returned HTTP 503"), now + dt.timedelta(hours=1))
        self.assertEqual((later["since"], later["attempts"], later["roots"]), (now.isoformat(), 2, ["SLV"]))
        other = nt.retrying(later, TUESDAY, RuntimeError("boom"), now + dt.timedelta(hours=2))
        self.assertEqual((other["day"], other["attempts"], other.get("roots")), ("2026-10-13", 1, None))


if __name__ == "__main__":
    unittest.main()
