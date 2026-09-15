"""The research-bank import, exercised against a fixture database.

Nothing here touches the real first-generation database at
`.data/runtime/five-hour/host/drained-backup/research.sqlite`: every test builds its own three-row
copy of that schema in a temporary directory, so the transform is tested without reading, locking
or depending on 95MB of someone else's week.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import ltcm
from ltcm.desk import MemoryStore

REPO_ROOT = Path(ltcm.__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "import_research_bank.py"

#: The first generation's schema, copied verbatim from the database this imports.
RESEARCH_SCHEMA = """
CREATE TABLE tasks(id TEXT PRIMARY KEY, wave INTEGER NOT NULL, kind TEXT NOT NULL, symbol TEXT,
    profile TEXT NOT NULL, cache TEXT NOT NULL, body TEXT NOT NULL, request_id TEXT,
    status TEXT NOT NULL DEFAULT 'waiting', result TEXT, grade TEXT, created REAL NOT NULL);
CREATE TABLE decisions(id TEXT PRIMARY KEY, at TEXT NOT NULL, task_id TEXT NOT NULL,
    result TEXT NOT NULL, status TEXT NOT NULL);
"""


def load_script():
    spec = importlib.util.spec_from_file_location("import_research_bank", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


importer = load_script()


def result(thesis, questions=(), claims=()):
    return json.dumps(
        {
            "thesis": thesis,
            "questions": [
                {"symbol": "X", "priority": priority, "question": text}
                for priority, text in questions
            ],
            "claims": list(claims),
            "confidence": "medium",
            "abstain_reason": None,
        }
    )


class ImportCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.research = self.root / "research.sqlite"
        self.memory = self.root / "memory.sqlite"
        self.db = sqlite3.connect(self.research)
        self.db.executescript(RESEARCH_SCHEMA)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def task(self, task_id, symbol, *, wave=0, kind="company", status="complete",
             result_json=None, created=1.0):
        self.db.execute(
            "INSERT INTO tasks (id, wave, kind, symbol, profile, cache, body, status, result,"
            " created) VALUES (?, ?, ?, ?, 'pro_flex', 'none', '{}', ?, ?, ?)",
            (task_id, wave, kind, symbol, status, result_json, created),
        )
        self.db.commit()

    def decision(self, decision_id, status="unchanged"):
        self.db.execute(
            "INSERT INTO decisions (id, at, task_id, result, status)"
            " VALUES (?, '2026-09-13T16:17:52Z', ?, '{}', ?)",
            (decision_id, decision_id, status),
        )
        self.db.commit()

    def run_import(self, **kwargs):
        return importer.import_bank(self.research, self.memory, **kwargs)

    def entries(self):
        store = MemoryStore(self.memory)
        try:
            return store.read("", limit=100)
        finally:
            store.close()


class TransformTests(ImportCase):
    def test_one_entry_per_company_with_the_case_and_the_open_questions(self):
        self.task(
            "w00-company-ODFL",
            "ODFL",
            result_json=result(
                "ODFL converts earnings to cash: operating cash flow is 1.34x net income.",
                questions=((2, "What was FY2026 capital spending?"), (1, "Is the yield trend price or volume?")),
                claims=[{"metric": "revenue", "value": 5496389000}],
            ),
        )
        summary = self.run_import()
        self.assertEqual(summary["companies"], 1)
        self.assertEqual(summary["imported"], 1)
        self.assertEqual(summary["skipped"], 0)

        entry = self.entries()[0]
        self.assertEqual(entry["desk_id"], "merton")
        self.assertEqual(entry["kind"], "research")
        self.assertEqual(entry["symbol"], "ODFL")
        self.assertEqual(entry["tags"], ["portfolio-agent", "2026-09"])
        self.assertEqual(entry["source_event"], "import:portfolio-agent")
        self.assertIn("operating cash flow is 1.34x net income", entry["text"])
        self.assertIn("Open questions:", entry["text"])
        # Highest priority first, whatever order the bank stored them in.
        self.assertLess(
            entry["text"].index("yield trend"), entry["text"].index("capital spending")
        )

    def test_the_newest_task_for_a_company_wins(self):
        self.task("w00-company-MSFT", "MSFT", wave=0, result_json=result("The first pass."))
        self.task(
            "w06-fresh-MSFT", "MSFT", wave=6, kind="fresh_review",
            result_json=result("The review that saw the Q4 filing."), created=9.0,
        )
        self.run_import()
        entries = self.entries()
        self.assertEqual(len(entries), 1)
        self.assertIn("saw the Q4 filing", entries[0]["text"])

    def test_rows_without_a_symbol_a_case_or_a_completion_are_left_behind(self):
        self.task("w01-allocation", None, kind="allocation", result_json=result("Portfolio level."))
        self.task("w01-company-APA", "APA", status="waiting", result_json=result("Unfinished."))
        self.task("w01-company-BNY", "BNY", status="failed", result_json=result("Failed."))
        self.task("w01-company-CNC", "CNC", result_json=None)
        self.task("w01-company-DRI", "DRI", result_json="not json at all")
        self.task("w01-company-FRT", "FRT", result_json=result(""))
        summary = self.run_import()
        self.assertEqual(summary["companies"], 0)
        self.assertEqual(self.entries(), [])

    def test_the_text_stays_inside_the_memory_store_limit(self):
        self.task(
            "w00-company-LONG",
            "LONG",
            result_json=result(
                "cash. " * 1200,
                questions=tuple((n, f"Question number {n} " + "why " * 100) for n in range(1, 7)),
            ),
        )
        self.run_import()
        entry = self.entries()[0]
        self.assertLessEqual(len(entry["text"]), 4000)
        self.assertTrue(entry["text"].startswith("LONG: cash."))

    def test_decisions_are_counted_for_the_operator(self):
        self.task("w00-company-PSX", "PSX", result_json=result("A refiner with cash."))
        self.decision("w01-allocation", "revision_requested")
        self.decision("w02-allocation", "pending")
        self.assertEqual(self.run_import()["decisions"], 2)


class IdempotencyTests(ImportCase):
    def setUp(self):
        super().setUp()
        self.task("w00-company-ODFL", "ODFL", result_json=result("Cash converts."))
        self.task("w00-company-VRTX", "VRTX", result_json=result("One drug, much cash."))

    def test_a_second_run_writes_nothing(self):
        first = self.run_import()
        self.assertEqual((first["imported"], first["skipped"]), (2, 0))
        second = self.run_import()
        self.assertEqual((second["imported"], second["skipped"]), (0, 2))
        self.assertEqual(len(self.entries()), 2)

    def test_a_second_run_does_not_rewrite_an_entry_the_desk_has_since_edited(self):
        self.run_import()
        entry_id = importer.entry_id("merton", "ODFL")
        store = MemoryStore(self.memory)
        try:
            before = store.get(entry_id)
        finally:
            store.close()
        self.task(
            "w07-fresh-ODFL", "ODFL", wave=7, kind="fresh_review",
            result_json=result("A later read."), created=99.0,
        )
        self.run_import()
        store = MemoryStore(self.memory)
        try:
            self.assertEqual(store.get(entry_id), before)
            self.assertEqual(store.count("merton"), 2)
        finally:
            store.close()

    def test_a_dry_run_reports_without_opening_the_memory_store(self):
        summary = self.run_import(dry_run=True)
        self.assertEqual(summary["companies"], 2)
        self.assertEqual(summary["imported"], 0)
        self.assertEqual(summary["symbols"], ["ODFL", "VRTX"])
        self.assertFalse(self.memory.exists())

    def test_the_limit_flag_imports_a_slice(self):
        summary = self.run_import(limit=1)
        self.assertEqual(summary["imported"], 1)
        self.assertEqual([e["symbol"] for e in self.entries()], ["ODFL"])

    def test_another_desk_can_be_named(self):
        self.run_import(desk_id="hawkins")
        self.assertEqual(self.entries()[0]["desk_id"], "hawkins")
        self.assertEqual(
            self.entries()[0]["id"], importer.entry_id("hawkins", self.entries()[0]["symbol"])
        )


class CommandLineTests(ImportCase):
    def test_a_missing_database_is_an_error_not_a_traceback(self):
        import contextlib
        import io

        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            code = importer.main(
                ["--research", str(self.root / "nope.sqlite"), "--memory", str(self.memory)]
            )
        self.assertEqual(code, 2)
        self.assertIn("no research database at", errors.getvalue())
        self.assertFalse(self.memory.exists())

    def test_the_command_prints_a_count(self):
        import contextlib
        import io

        self.task("w00-company-ODFL", "ODFL", result_json=result("Cash converts."))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = importer.main(
                ["--research", str(self.research), "--memory", str(self.memory), "--at",
                 "2026-09-15T12:00:00.000Z"]
            )
        self.assertEqual(code, 0)
        printed = out.getvalue()
        self.assertIn("1 companies in the research bank", printed)
        self.assertIn("imported 1 entries for desk merton", printed)
        self.assertEqual(self.entries()[0]["at"], "2026-09-15T12:00:00.000Z")

    def test_the_defaults_point_at_the_first_generation_bank_and_the_floors_memory(self):
        self.assertTrue(str(importer.DEFAULT_RESEARCH).endswith(
            ".data/runtime/five-hour/host/drained-backup/research.sqlite"
        ))
        self.assertTrue(str(importer.DEFAULT_MEMORY).endswith(".data/ltcm/memory.sqlite"))
        self.assertEqual(importer.DESK_ID, "merton")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
