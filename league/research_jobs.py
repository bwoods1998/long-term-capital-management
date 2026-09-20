"""Private, durable research queue and conversation checkpoints.

One active session per agent. An OS lock owns execution, rather than an expiring lease that
could admit a second worker while the first is still waiting on a model. Process exit releases
the lock; the next House resumes the recorded session, request keys and tool outputs. A tool
or candidate commit interrupted between its intent and receipt is never blindly repeated.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from .ledger import canonical

ACTIVE = ('queued', 'working', 'ready', 'applying')


class ResearchPending(Exception):
    """Yield a saved session; no new session or replacement model request is needed."""


class ResearchJobs:
    def __init__(self, path: str | Path, *, clock=time.time):
        self.path, self.clock = Path(path), clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.locks = self.path.with_suffix('.locks')
        self.locks.mkdir(mode=0o700, exist_ok=True)
        self.locks.chmod(0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS research_jobs (
                session TEXT PRIMARY KEY, agent TEXT NOT NULL, generation TEXT NOT NULL,
                status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                available REAL NOT NULL, finished REAL, snapshot TEXT, checkpoint TEXT,
                outcome TEXT, reason TEXT NOT NULL DEFAULT '', resumes INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS research_agent_history ON research_jobs(agent,finished);
            CREATE UNIQUE INDEX IF NOT EXISTS research_one_active ON research_jobs(agent)
                WHERE status IN ('queued','working','ready','applying');
        ''')

    @staticmethod
    def _row(row):
        if row is None:
            return None
        row = dict(row)
        for key in ('generation', 'snapshot', 'checkpoint', 'outcome'):
            if key in row:
                row[key] = json.loads(row[key]) if row[key] is not None else None
        return row

    def get(self, session):
        with self.lock:
            return self._row(self.db.execute('SELECT * FROM research_jobs WHERE session=?', (session,)).fetchone())

    def active(self, agent):
        with self.lock:
            return self._row(self.db.execute("SELECT session,agent,generation,status,created,updated,available,finished,reason,resumes FROM research_jobs WHERE agent=? AND status IN ('queued','working','ready','applying')", (agent,)).fetchone())

    def enqueue(self, agent, generation, *, session=None):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                prior = self.active(agent)
                if prior is None:
                    session = session or f'research:{agent}:{uuid.uuid4().hex}'
                    now = self.clock()
                    self.db.execute('INSERT INTO research_jobs(session,agent,generation,status,created,updated,available) VALUES(?,?,?,?,?,?,?)',
                                    (session, agent, canonical(list(generation)), 'queued', now, now, now))
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
        return prior or self.get(session)

    @contextmanager
    def claim(self, session):
        # Hash caller identities before using them as paths. Keep lock files: unlinking one while
        # another process has opened it would create two independent locks for the same session.
        path = self.locks / hashlib.sha256(session.encode()).hexdigest()
        with path.open('a+b') as handle:
            path.chmod(0o600)
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def start(self, session, snapshot):
        with self.lock:
            self.db.execute("UPDATE research_jobs SET snapshot=COALESCE(snapshot,?), status='working', updated=?, resumes=resumes+CASE WHEN snapshot IS NULL THEN 0 ELSE 1 END WHERE session=? AND status IN ('queued','working')",
                            (canonical(snapshot), self.clock(), session))
        return self.get(session)

    def save(self, session, checkpoint):
        with self.lock:
            result = self.db.execute("UPDATE research_jobs SET checkpoint=?,updated=? WHERE session=? AND status='working'",
                                     (canonical(checkpoint), self.clock(), session))
            if result.rowcount != 1:
                raise RuntimeError('research checkpoint has no working session')

    def defer(self, session, reason, *, seconds=60):
        with self.lock:
            self.db.execute('UPDATE research_jobs SET available=?,updated=?,reason=? WHERE session=?',
                            (self.clock() + seconds, self.clock(), reason[:200], session))

    def ready(self, session, outcome):
        with self.lock:
            self.db.execute("UPDATE research_jobs SET status='ready',outcome=?,updated=?,reason='' WHERE session=? AND status='working'",
                            (canonical(outcome), self.clock(), session))

    def applying(self, session):
        with self.lock:
            result = self.db.execute("UPDATE research_jobs SET status='applying',updated=? WHERE session=? AND status='ready'", (self.clock(), session))
            if result.rowcount != 1:
                raise RuntimeError('research result is not ready to apply')

    def finish(self, session, reason='', *, cancelled=False):
        with self.lock:
            self.db.execute('UPDATE research_jobs SET status=?,reason=?,updated=?,finished=? WHERE session=?',
                            ('cancelled' if cancelled else 'done', reason[:200], self.clock(), self.clock(), session))

    def pending(self):
        with self.lock:
            return [self._row(r) for r in self.db.execute("SELECT session,agent,generation,status,created,updated,available,finished,reason,resumes FROM research_jobs WHERE status IN ('queued','working','ready','applying') ORDER BY created,session")]

    def last_finished(self, agent):
        with self.lock:
            return self.db.execute("SELECT COALESCE(MAX(finished),0) FROM research_jobs WHERE agent=? AND status='done'", (agent,)).fetchone()[0]

    def close(self):
        with self.lock:
            self.db.close()
