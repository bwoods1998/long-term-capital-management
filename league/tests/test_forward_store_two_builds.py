"""ONE FORWARD STORE, TWO BUILDS BEFORE IT (release E4 merged with main 8ab31e32; league/ops/forward_db.py).

Both sides of the merge wrote forward stores, and a House may hold either when the merged tree first opens it:

- MAIN `8ab31e32` (release E3.1) declares `fwd_twins` with A29's two columns, `rebased` and `base_agree`, writes them
  on every twin row, and writes the `twin_rebased` event.
- E4 `8ed4e72e` (built on the main before it) declares `fwd_twins` without them. What release E4 adds to this store is
  ROWS ONLY, in tables that exist: a panel program's registry row (route `XS_ROUTE`, a `ugroup` under
  `PANEL_UGROUP`) and a panel instance's twin rows, written by league/ops/forward_xs.py with the registered columns.
  Release E4 adds NO table and NO column to forward.sqlite (its two schema additions are in the live book:
  `eq_instances.kind` and `eq_rebalances`).

So THE MIGRATION IS ONE, and it is main's: `forward_db.ADDED_COLUMNS` through `_migrate`, in a writable `open_db`.
league/tests/test_forward_rebase.py holds the migration itself (append-only, no row rewritten, two writers). Held
HERE is that it is the only one and that it takes both builds:

- `SCHEMA` is main's to the byte, and E4's is `SCHEMA` less A29's two declarations (each pinned by the sha256 of the
  text, taken on that sha's own tree): "a store built by" a sha is the store its own `SCHEMA` makes, filled through
  the INSERTs its own code used;
- a store built by `8ed4e72e`, holding an ETF program's and a PANEL program's registry rows and twin rows, gains the
  two columns at its first writable open with no row rewritten (every rowid, every column, the bytes of every page
  that holds a twin row), its chain verifies with the panel row in it, and every old row reads NULL in both columns;
- a store built by `8ab31e32` is opened with nothing added and nothing changed, and then takes a panel program's row
  and a panel twin row as the merged tree writes them;
- two writers at once, on either build: two connections that both saw the column missing, and two threads opening
  the same file together;
- after it the two stores declare the same tables and columns, and both are append-only still.

The same was run once on stores built by each sha's real code (a week of the rehearsal's twin scenario on a detached
clone of each): the merge's record in the captain's scratch. Every row here is invented."""

from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from league.ops import forward_db

#: sha256 of `forward_db.SCHEMA` on main 8ab31e32 and on E4 8ed4e72e, each computed on a detached clone of that sha.
SCHEMA_MAIN = "315c5c9772c78950d8bb2fdf5982f971b8e716c7650571e4fdc8671ad0712027"
SCHEMA_E4 = "5265ef9520a5cf73ab31feb42ad94afc7957ac91a938d0a9621024b79ab5a183"
#: The INSERT both builds' ETF night used before A29 (league/ops/forward_twins.py at 8ed4e72e) and the panel night uses
#: at every sha (league/ops/forward_xs.py `twin`): the registered columns.
REGISTERED = ("INSERT OR IGNORE INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, why, at, live_bars, "
              "shadow_bars, cause) VALUES(?,?,?,?,?,?,?,?,?,?,?)")
#: The INSERT of main's ETF night since A29 (league/ops/forward_twins.py `_one_instance`).
REBASED = ("INSERT OR IGNORE INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, why, at, live_bars, "
           "shadow_bars, cause, rebased, base_agree) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)")
CODE = "NEEDS = {}\nPARAMS = {}\n\n\ndef decide(ctx):\n    return []\n"
CREATED = 1791568800.0      # (an invented registration time; Oct 9, 2026)


def e4_schema() -> str:
    """`forward_db.SCHEMA` as E4 8ed4e72e declared it: this tree's less A29's two column declarations."""
    schema = forward_db.SCHEMA
    start = schema.index("  rebased INTEGER,")
    end = schema.index("  PRIMARY KEY (instance, day));", start)
    return schema[:start] + schema[end:]


def registry_row(key: str, *, panel: bool = False) -> dict:
    family = key.split("@")[0]
    return {"key": key, "family": family, "version": 1, "lane": "equity" if panel else "beta", "reason": "live",
            "ugroup": forward_db.PANEL_UGROUP + "sp500" if panel else "index", "lineage": f"beta:{family}", "code": CODE,
            "params": {}, "needs": {"panel": "sp500"} if panel else {"symbols": ["QQQ"]},
            "program_sha": hashlib.sha256(CODE.encode()).hexdigest(), "run_sha": f"run-{family}-1", "author": "a test",
            "created_at": CREATED, "evidence": "registry", "first_close": forward_db.first_close(CREATED),
            "first_day": forward_db.first_day(forward_db.first_close(CREATED)), "registered_at": CREATED,
            "route": forward_db.XS_ROUTE if panel else forward_db.E3_ROUTE, "alpha_f": forward_db.E3_ALPHA_F}


def twin(instance: str, day: str, pid: int, agree, *, cause=None) -> tuple:
    return (instance, day, pid, '["B|QQQ|open"]', '["B|QQQ|open"]' if agree else "[]", agree, None, 1.0, None, "f" * 16,
            cause)


def tables(db: sqlite3.Connection) -> dict[str, list[tuple]]:
    """Every table's rows, each with its rowid, in rowid order (a table declared WITHOUT ROWID: by its key)."""
    out = {}
    for name in forward_db.TABLES:
        try:
            out[name] = [tuple(r) for r in db.execute(f"SELECT rowid, * FROM {name} ORDER BY rowid")]
        except sqlite3.OperationalError:
            out[name] = [tuple(r) for r in db.execute(f"SELECT * FROM {name} ORDER BY 1, 2")]
    return out


def declared(db: sqlite3.Connection) -> dict[str, list[tuple]]:
    return {name: [tuple(r)[1:6] for r in db.execute(f"PRAGMA table_info({name})")] for name in forward_db.TABLES}


class TwoBuilds(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def built_by_e4(self, name: str = "e4") -> Path:
        """A store as 8ed4e72e builds it: its `SCHEMA`, an ETF program's and a panel program's registry rows (the
        panel row through this tree's `append_registry`: the registry table and the row's hash are E4's own, to the
        column), and twin rows of both through the registered INSERT."""
        root = self.tmp / name
        root.mkdir()
        db = sqlite3.connect(root / forward_db.DB)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")           # (as its own `open_db` makes the file)
        db.execute("PRAGMA synchronous=NORMAL")
        db.executescript(e4_schema())
        etf = forward_db.append_registry(db, registry_row("etf-a@1"))
        panel = forward_db.append_registry(db, registry_row("xs-a@1", panel=True))
        with db:
            db.executemany(REGISTERED, [twin("etf-a@1:r", "2026-10-09", etf, 1),
                                        twin("etf-a@1:r", "2026-10-12", etf, 0, cause="program"),
                                        twin("etf-a@1:r", "2026-10-13", etf, 1),
                                        twin("xs-a@1:r", "2026-10-12", panel, 1),
                                        twin("xs-a@1:r", "2026-10-13", panel, 0, cause="unknown")])
            db.execute("INSERT INTO fwd_part(instance, through, pid, matched, missed, extra, at) VALUES(?,?,?,?,?,?,?)",
                       ("etf-a@1:r", "2026-10-13", etf, 1, 1, 0, 1.0))
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.close()
        return root

    def built_by_main(self, name: str = "main") -> Path:
        """A store as 8ab31e32 builds it: `SCHEMA` (its own, to the byte), an ETF program, twin rows with A29's two
        columns and the re-base's event."""
        root = self.tmp / name
        root.mkdir()
        db = forward_db.open_db(root)
        etf = forward_db.append_registry(db, registry_row("etf-a@1"))
        with db:
            db.executemany(REBASED, [(*twin("etf-a@1:r", "2026-10-09", etf, 1), 0, 1),
                                     (*twin("etf-a@1:r", "2026-10-12", etf, 0, cause="program"), 0, 0),
                                     (*twin("etf-a@1:r", "2026-10-13", etf, 1), 1, 0)])
        forward_db.event(db, "twin_rebased", pid=etf, day="2026-10-12", at=2.0, once="etf-a@1:r",
                         payload={"instance": "etf-a@1:r", "held": [], "unheld": 0, "planned": {}, "why": "a test"})
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.close()
        return root

    # ------------------------------------------------------------------------------------------------ the two texts
    def test_the_schema_is_mains_and_e4s_is_it_less_a29s_two_columns(self):
        self.assertEqual(hashlib.sha256(forward_db.SCHEMA.encode()).hexdigest(), SCHEMA_MAIN,
                         "the merged tree declares the forward store exactly as main 8ab31e32 does: E4 adds nothing")
        self.assertEqual(hashlib.sha256(e4_schema().encode()).hexdigest(), SCHEMA_E4)
        self.assertEqual(forward_db.ADDED_COLUMNS, (("fwd_twins", "rebased", "INTEGER"),
                                                    ("fwd_twins", "base_agree", "INTEGER")), "one list, main's")
        old, new = sqlite3.connect(":memory:"), sqlite3.connect(":memory:")
        self.addCleanup(old.close)
        self.addCleanup(new.close)
        old.executescript(e4_schema())
        new.executescript(forward_db.SCHEMA)
        a, b = declared(old), declared(new)
        self.assertEqual({t for t in a if a[t] != b[t]}, {"fwd_twins"}, "the two builds differ in one table")
        self.assertEqual([c for c in b["fwd_twins"] if c not in a["fwd_twins"]],
                         [("rebased", "INTEGER", 0, None, 0), ("base_agree", "INTEGER", 0, None, 0)],
                         "by two nullable columns with no default, at the end")

    # --------------------------------------------------------------------------------------------- E4's store
    def test_a_store_built_by_e4_gains_the_columns_and_no_row_is_rewritten(self):
        root = self.built_by_e4()
        path = root / forward_db.DB
        raw = sqlite3.connect(path)
        before = tables(raw)
        size = raw.execute("PRAGMA page_size").fetchone()[0]
        raw.close()
        bytes_before = path.read_bytes()
        held = [i for i in range(0, len(bytes_before), size) if b"etf-a@1:r" in bytes_before[i:i + size]
                or b"xs-a@1:r" in bytes_before[i:i + size]]
        self.assertTrue(held)
        db = forward_db.open_db(root)
        self.addCleanup(db.close)
        self.assertTrue(forward_db.has_column(db, "fwd_twins", "rebased"))
        self.assertTrue(forward_db.has_column(db, "fwd_twins", "base_agree"))
        after = tables(db)
        for name, rows in before.items():
            if name == "fwd_twins":
                self.assertEqual([row[:12] for row in after[name]], rows, "every rowid and every old column, as it was")
                self.assertEqual({row[12:] for row in after[name]}, {(None, None)}, "NULL in A29's two columns")
            elif name in ("fwd_events", "fwd_kv"):       # (the first open of a release writes its `prereg` beside)
                self.assertEqual(after[name][:len(rows)], rows, name)
            else:
                self.assertEqual(after[name], rows, name)
        chain = forward_db.verify_chain(db)
        self.assertEqual((chain["ok"], chain["rows"], chain["first_bad"]), (True, 2, None), "the panel row among them")
        panel = forward_db.program(db, "xs-a@1")
        self.assertEqual((panel.route, panel.ugroup), (forward_db.XS_ROUTE, forward_db.PANEL_UGROUP + "sp500"))
        self.assertEqual(forward_db._migrate(db), 0, "once")
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        bytes_after = path.read_bytes()
        for i in held:
            self.assertEqual(bytes_after[i:i + size], bytes_before[i:i + size], f"page {i // size + 1} of the rows")
        for statement in ("UPDATE fwd_twins SET base_agree=1", "DELETE FROM fwd_twins", "DELETE FROM fwd_registry"):
            with self.assertRaises(sqlite3.DatabaseError) as raised:
                db.execute(statement)
            self.assertIn(forward_db.APPEND_ONLY_ERROR, str(raised.exception))

    def test_its_rows_read_as_never_re_based_the_panel_rows_too(self):
        from league.ops import forward_twins

        root = self.built_by_e4()
        rows, read = forward_twins._twin_rows(root, ["etf-a@1:r", "xs-a@1:r"])      # before any writable open
        self.assertTrue(read)
        self.assertEqual({(i, d): (r["agree"], r["rebased"], r["base_agree"]) for i, days in rows.items()
                          for d, r in days.items()},
                         {("etf-a@1:r", "2026-10-09"): (1, None, None), ("etf-a@1:r", "2026-10-12"): (0, None, None),
                          ("etf-a@1:r", "2026-10-13"): (1, None, None), ("xs-a@1:r", "2026-10-12"): (1, None, None),
                          ("xs-a@1:r", "2026-10-13"): (0, None, None)})
        forward_db.open_db(root).close()
        again, _ = forward_twins._twin_rows(root, ["etf-a@1:r", "xs-a@1:r"])
        self.assertEqual({k: {d: tuple(r) for d, r in v.items()} for k, v in again.items()},
                         {k: {d: tuple(r) for d, r in v.items()} for k, v in rows.items()}, "the same after it")

    # ------------------------------------------------------------------------------------------- main's store
    def test_a_store_built_by_main_is_opened_with_nothing_added_and_takes_a_panel_row(self):
        root = self.built_by_main()
        path = root / forward_db.DB
        raw = sqlite3.connect(path)
        before, shape = tables(raw), declared(raw)
        version = raw.execute("PRAGMA schema_version").fetchone()[0]
        raw.close()
        added, migrate = [], forward_db._migrate
        with mock.patch.object(forward_db, "_migrate", lambda db: added.append(migrate(db)) or added[-1]):
            db = forward_db.open_db(root)
        self.addCleanup(db.close)
        self.assertEqual(added, [0], "the one migration ran and had nothing to add")
        self.assertEqual((tables(db), declared(db)), (before, shape))
        self.assertEqual(db.execute("PRAGMA schema_version").fetchone()[0], version, "the declarations did not move")
        # ... and it takes what release E4 writes: a panel program's row, and a panel twin row with the registered
        # columns (NULL in A29's two: league/tests/test_equity_panel_on_main.py says what that means).
        pid = forward_db.append_registry(db, registry_row("xs-a@1", panel=True))
        with db:
            db.execute(REGISTERED, twin("xs-a@1:r", "2026-10-13", pid, 0, cause="unknown"))
        self.assertTrue(forward_db.verify_chain(db)["ok"])
        self.assertEqual(tuple(db.execute("SELECT agree, rebased, base_agree FROM fwd_twins WHERE instance='xs-a@1:r'"
                                          ).fetchone()), (0, None, None))
        self.assertEqual([tuple(r)[:14] for r in db.execute("SELECT rowid, * FROM fwd_twins WHERE instance='etf-a@1:r' "
                                                            "ORDER BY rowid")], before["fwd_twins"])
        with self.assertRaises(ValueError):
            forward_db.append_registry(db, {**registry_row("etf-b@1"), "route": forward_db.XS_ROUTE})

    # --------------------------------------------------------------------------------------------- two writers
    def test_two_connections_that_both_saw_the_column_missing(self):
        """The interleaving that loses the race, with two real connections on one file: the first looks and finds no
        column, the second migrates whole, the first then adds what is already there."""
        root = self.built_by_e4()
        first = sqlite3.connect(root / forward_db.DB)
        second = sqlite3.connect(root / forward_db.DB)
        self.addCleanup(first.close)
        self.addCleanup(second.close)
        before = tables(first)["fwd_twins"]
        real = forward_db.has_column
        looked = []

        def look(db, table, column):
            found = real(db, table, column)
            if db is first and not looked:
                looked.append(column)
                self.assertEqual(forward_db._migrate(second), 2, "the other writer adds both, and commits")
            return found

        with mock.patch.object(forward_db, "has_column", look):
            self.assertEqual(forward_db._migrate(first), 0, "it added none: both were there by its ALTER")
        self.assertEqual([tuple(r)[1] for r in first.execute("PRAGMA table_info(fwd_twins)")][-2:],
                         ["rebased", "base_agree"])
        self.assertEqual([row[:12] for row in tables(first)["fwd_twins"]], before)

    def test_two_threads_opening_either_build_together(self):
        for build in (self.built_by_e4, self.built_by_main):
            for trial in range(6):
                with self.subTest(build=build.__name__, trial=trial):
                    root = build(f"{build.__name__}-{trial}")
                    raw = sqlite3.connect(root / forward_db.DB)
                    before = [row[:12] for row in tables(raw)["fwd_twins"]]
                    raw.close()
                    gate, errors, shapes = threading.Barrier(2), [], []

                    def writer():
                        try:
                            gate.wait(timeout=10)
                            db = forward_db.open_db(root)
                            shapes.append([tuple(r)[1] for r in db.execute("PRAGMA table_info(fwd_twins)")])
                            db.close()
                        except Exception as exc:  # noqa: BLE001 - the test's own finding
                            errors.append(f"{type(exc).__name__}: {exc}")

                    threads = [threading.Thread(target=writer) for _ in range(2)]
                    for t in threads:
                        t.start()
                    for t in threads:
                        t.join(timeout=30)
                    self.assertEqual(errors, [])
                    self.assertEqual(len(shapes), 2)
                    for shape in shapes:
                        self.assertEqual((shape.count("rebased"), shape.count("base_agree")), (1, 1))
                    raw = sqlite3.connect(root / forward_db.DB)
                    self.addCleanup(raw.close)
                    self.assertEqual([row[:12] for row in tables(raw)["fwd_twins"]], before)

    def test_after_it_the_two_builds_are_one_store(self):
        a, b = forward_db.open_db(self.built_by_e4()), forward_db.open_db(self.built_by_main())
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        self.assertEqual(declared(a), declared(b))
        fresh = sqlite3.connect(":memory:")
        self.addCleanup(fresh.close)
        fresh.executescript(forward_db.SCHEMA)
        self.assertEqual(declared(a), declared(fresh), "and it is the store a new House makes")


if __name__ == "__main__":
    unittest.main()
