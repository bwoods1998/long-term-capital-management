"""Retry cleanup of a stopped swarm's late Sail forks without blocking the House."""
from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Any, Callable


class StoppedPoolCleanup:
    def __init__(self, root: str | Path, *, clock: Callable[[], float] = time.monotonic,
                 work: Callable[[], dict[str, Any]] | None = None):
        self.root = Path(root)
        self.clock = clock
        self.work = work or self._cleanup
        self.last_start = float('-inf')
        self.worker: threading.Thread | None = None
        self.result: dict[str, Any] = {}

    def tick(self, *, stopped: bool) -> dict[str, Any]:
        busy = self.worker is not None and self.worker.is_alive()
        if stopped and not busy and (self.root / 'swarm.sqlite').is_file() and self.clock() - self.last_start >= 60:
            self.last_start = self.clock()
            self.worker = threading.Thread(target=self._run, name='swarm-stopped-cleanup', daemon=True)
            self.worker.start()
            busy = True
        return {'running': busy, **self.result}

    def _run(self) -> None:
        try:
            self.result = self.work()
        except Exception as error:
            self.result = {'errors': [f'{type(error).__name__}: {str(error)[:160]}']}

    def _cleanup(self) -> dict[str, Any]:
        from ..sailbox import SailboxClient
        from .pool import cleanup_stopped

        return cleanup_stopped(self.root, SailboxClient(), limit=100)
