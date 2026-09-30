"""Private historical SIP work receipts; a scan cursor never resolves missing data."""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

SCHEMA = 2
MAX_ATTEMPTS = 3
RETRY_SECONDS = 300
RETRY_DAYS = 5


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class Progress:
    def __init__(self, path: Path, plan: dict, *, clock=time.time):
        self.path, self.clock = Path(path), clock
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.path, timeout=5)
        self.path.chmod(0o600)
        self.db.executescript("""
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS days(day TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS roots(
                day TEXT NOT NULL, root TEXT NOT NULL, status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, budget INTEGER NOT NULL DEFAULT 3,
                retry_at REAL NOT NULL DEFAULT 0, recovery_pending INTEGER NOT NULL DEFAULT 0,
                receipt TEXT NOT NULL, PRIMARY KEY(day,root));
            CREATE TABLE IF NOT EXISTS attempts(
                day TEXT NOT NULL, root TEXT NOT NULL, n INTEGER NOT NULL, at REAL NOT NULL,
                receipt TEXT, PRIMARY KEY(day,root,n));
            CREATE TABLE IF NOT EXISTS recoveries(
                day TEXT NOT NULL, root TEXT NOT NULL, n INTEGER NOT NULL, at REAL NOT NULL,
                receipt TEXT, PRIMARY KEY(day,root,n));
            CREATE TABLE IF NOT EXISTS reconsiderations(
                day TEXT NOT NULL, root TEXT NOT NULL, evidence_sha256 TEXT NOT NULL,
                evidence TEXT NOT NULL, at REAL NOT NULL, PRIMARY KEY(day,root,evidence_sha256));
        """)
        self.document = plan
        self.plan_days = {row['day']: row for row in plan['days']}
        self.plan = digest([SCHEMA, plan])
        prior = self.db.execute("SELECT value FROM meta WHERE key='plan'").fetchone()
        if prior is not None and prior[0] != self.plan:
            self.close()
            raise ValueError("SIP required roots/source/calendar/window plan changed; review a new queue, never erase its gaps")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO meta VALUES('plan',?)", (self.plan,))
            self.db.execute("INSERT OR IGNORE INTO meta VALUES('plan_json',?)", (json.dumps(plan, sort_keys=True),))

    @classmethod
    def existing(cls, path: Path, *, clock=time.time):
        with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)) as db:
            plan = json.loads(db.execute("SELECT value FROM meta WHERE key='plan_json'").fetchone()[0])
        return cls(path, plan, clock=clock)

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _validate(self, day: str, row: dict):
        planned = self.plan_days[day]
        expected = planned['hours'][1] - planned['hours'][0]
        root = row.get('root')
        missing = row.get('missing_minutes')
        known = row.get('known')
        if (root not in planned['roots'] or row.get('day') != day
                or row.get('schema') != self.document['schema']
                or type(row.get('expected')) is not int or row['expected'] != expected or expected <= 0
                or type(known) is not int or not 0 <= known <= expected
                or not isinstance(missing, list) or any(type(m) is not int for m in missing)
                or missing != sorted(set(missing)) or len(missing) != expected - known
                or any(not planned['hours'][0] < m <= planned['hours'][1] for m in missing)
                or type(row.get('complete')) is not bool
                or row['complete'] != (known == expected)
                or row['complete'] != (row.get('status') == 'complete')):
            raise ValueError('SIP receipt does not match its day/root/schema/coverage plan')
        if row['complete']:
            symbol = row.get('source_symbol')
            alias = planned['roots'][root]
            # Legacy rows can lack the alias receipt, but the verifier must name the expected alias explicitly.
            if (row.get('source') != self.document['source'] or symbol not in (None, alias)
                    or (symbol is None and row.get('source_symbol_expected') != alias)
                    or row.get('verification') != 'current_file_hash_and_grid'
                    or not re.fullmatch(r'[0-9a-f]{64}', str(row.get('file_sha256', '')))
                    or (row.get('packet_sha256') is not None
                        and not re.fullmatch(r'[0-9a-f]{64}', str(row['packet_sha256'])))):
                raise ValueError('SIP completion needs verified bytes, source identity and a complete grid')

    def observe(self, day: str, rows: list[dict]):
        """Only current byte/grid verification can resolve a gap, including a lost write acknowledgement."""
        expected = set(self.plan_days[day]['roots'])
        if len(rows) != len(expected) or {r['root'] for r in rows} != expected:
            raise ValueError("SIP day roots differ from the durable plan")
        for row in rows:
            self._validate(day, row)
        with self.db:
            for row in rows:
                body = json.dumps(row, sort_keys=True, allow_nan=False)
                self.db.execute("INSERT INTO roots(day,root,status,receipt) VALUES(?,?,'pending',?) "
                                "ON CONFLICT(day,root) DO NOTHING", (day, row['root'], body))
                if row.get('complete'):
                    self.db.execute("UPDATE roots SET status='complete',retry_at=0,recovery_pending=0,receipt=? WHERE day=? AND root=?",
                                    (body, day, row['root']))
                else:
                    # A changed/missing file invalidates a complete receipt without forgiving past attempts.
                    self.db.execute("UPDATE roots SET status=CASE WHEN status='complete' THEN 'pending' ELSE status END,"
                                    "receipt=? WHERE day=? AND root=?", (body, day, row['root']))

    def reserve(self, day: str, rows: list[dict]) -> list[str]:
        """Commit attempts BEFORE requesting data; retries are bounded across process restarts."""
        self.observe(day, rows)
        due, now = [], self.clock()
        with self.db:
            for root, attempts, budget, retry_at in self.db.execute(
                    "SELECT root,attempts,budget,retry_at FROM roots WHERE day=? AND status!='complete' ORDER BY root", (day,)).fetchall():
                if attempts >= budget or retry_at > now:
                    continue
                attempt = attempts + 1
                self.db.execute("UPDATE roots SET status='retrying',attempts=?,retry_at=?,recovery_pending=1 WHERE day=? AND root=?",
                                (attempt, now + RETRY_SECONDS * 2 ** min(attempt - 1, 4), day, root))
                self.db.execute("INSERT INTO attempts(day,root,n,at) VALUES(?,?,?,?)", (day, root, attempt, now))
                due.append(root)
        return due

    def record(self, day: str, rows: list[dict]):
        if len({r['root'] for r in rows}) != len(rows):
            raise ValueError('duplicate SIP attempt receipts')
        for row in rows:
            self._validate(day, row)
        with self.db:
            for row in rows:
                saved = self.db.execute("SELECT attempts,status FROM roots WHERE day=? AND root=?", (day, row['root'])).fetchone()
                if saved is None or saved[1] != 'retrying':
                    raise ValueError("unreserved SIP receipt")
                body = json.dumps(row, sort_keys=True, allow_nan=False)
                self.db.execute("UPDATE roots SET status=?,receipt=?,recovery_pending=?,retry_at=CASE WHEN ? THEN 0 ELSE retry_at END "
                                "WHERE day=? AND root=?", (row['status'], body, bool(row.get('uncertain_write')),
                                                         bool(row.get('complete')), day, row['root']))
                self.db.execute("UPDATE attempts SET receipt=? WHERE day=? AND root=? AND n=?",
                                (body, day, row['root'], saved[0]))

    def scanned(self, day: str):
        expected = len(self.plan_days[day]['roots'])
        if self.db.execute("SELECT COUNT(*) FROM roots WHERE day=?", (day,)).fetchone()[0] != expected:
            raise ValueError("cannot advance an unrecorded SIP day")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO days VALUES(?)", (day,))

    def due_days(self) -> list[str]:
        return [row[0] for row in self.db.execute("SELECT DISTINCT day FROM roots WHERE status!='complete' "
                "AND (attempts<budget OR recovery_pending=1) AND retry_at<=? ORDER BY day LIMIT ?", (self.clock(), RETRY_DAYS))]

    def reserve_recovery(self, day: str) -> list[str]:
        """One read-only observation for a final unacknowledged/uncertain write, never another provider attempt."""
        with self.db:
            rows = self.db.execute("SELECT root,attempts FROM roots WHERE day=? AND status!='complete' "
                                   "AND attempts>=budget AND recovery_pending=1 AND retry_at<=?", (day, self.clock())).fetchall()
            for root, attempt in rows:
                self.db.execute("UPDATE roots SET recovery_pending=0 WHERE day=? AND root=?", (day, root))
                self.db.execute("INSERT INTO recoveries(day,root,n,at) VALUES(?,?,?,?)", (day, root, attempt, self.clock()))
        return [r[0] for r in rows]

    def recovery_result(self, day: str, roots: list[str], *, rows=(), error=None):
        by_root = {r['root']: r for r in rows}
        with self.db:
            for root in roots:
                result = {'error': error} if error else by_root[root]
                self.db.execute("UPDATE recoveries SET receipt=? WHERE day=? AND root=? "
                                "AND n=(SELECT attempts FROM roots WHERE day=? AND root=?)",
                                (json.dumps(result, sort_keys=True), day, root, day, root))
                self.db.execute("UPDATE roots SET status=? WHERE day=? AND root=?",
                                ('error' if error else result['status'], day, root))

    def compare_files(self, files: list[dict]):
        """Before an image snapshot: compare actual file hashes and current journal identities to receipts."""
        current = {(r['day'], r['root']): r for r in files}
        expected = {(day, root) for day, row in self.plan_days.items() for root in row['roots']}
        if set(current) != expected or len(files) != len(expected):
            raise ValueError("SIP canonical file plan changed")
        keys = ('source', 'source_symbol', 'file_sha256', 'packet_sha256')
        with self.db:
            for day, root, body in self.db.execute("SELECT day,root,receipt FROM roots WHERE status='complete'").fetchall():
                saved, actual = json.loads(body), current[day, root]
                if (any(saved.get(k) != actual.get(k) for k in keys)
                        or actual.get('actual_sha256') != saved.get('file_sha256')):
                    bad = {**saved, 'complete': False, 'status': 'changed', 'error': 'canonical SIP file changed after scan',
                           'current_file': actual}
                    self.db.execute("UPDATE roots SET status='changed',receipt=? WHERE day=? AND root=?",
                                    (json.dumps(bad, sort_keys=True), day, root))

    def reconsider(self, day: str, root: str, evidence: str) -> bool:
        """Operator-reviewed new evidence grants one bounded retry batch, retaining every past attempt."""
        evidence = evidence.strip()
        if not 8 <= len(evidence) <= 1000:
            raise ValueError("record a specific new data/provider evidence reason (8..1000 characters)")
        saved = self.db.execute("SELECT status,attempts,budget FROM roots WHERE day=? AND root=?", (day, root)).fetchone()
        if saved is None or saved[0] == 'complete':
            raise ValueError("reconsideration requires an unresolved root")
        with self.db:
            added = self.db.execute("INSERT OR IGNORE INTO reconsiderations VALUES(?,?,?,?,?)",
                                   (day, root, digest(evidence), evidence, self.clock())).rowcount
            if added:
                self.db.execute("UPDATE roots SET budget=?,retry_at=0 WHERE day=? AND root=?",
                                (max(saved[2], saved[1] + MAX_ATTEMPTS), day, root))
        return bool(added)

    def summary(self) -> dict:
        scanned = {row[0] for row in self.db.execute("SELECT day FROM days")}
        unresolved, deferred = self.db.execute("SELECT COUNT(*),COALESCE(SUM(attempts>=budget),0) FROM roots "
                                               "WHERE status!='complete'").fetchone()
        required = sum(len(row['roots']) for row in self.plan_days.values())
        recorded = self.db.execute('SELECT COUNT(*) FROM roots').fetchone()[0]
        complete = set(self.plan_days) <= scanned and unresolved == 0 and recorded == required
        out = {"schema": SCHEMA, "plan": self.plan, "scanned_days": len(scanned), "planned_days": len(self.plan_days),
               "unresolved": unresolved, "deferred": deferred, "complete": complete,
               'required_roots': required, 'recorded_roots': recorded}
        if complete:
            rows = [json.loads(r[0]) for r in self.db.execute("SELECT receipt FROM roots ORDER BY day,root")]
            out['receipt_sha256'] = digest([self.plan, [{k: r.get(k) for k in
                ('day', 'root', 'source', 'source_symbol', 'file_sha256', 'packet_sha256', 'expected')} for r in rows]])
        return out
