from __future__ import annotations

import fcntl
import os
from pathlib import Path


class AlreadyRunningError(RuntimeError):
    """Raised when another sync process already holds the process lock."""


class ProcessLock:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._fd = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = self.path.open("w")
        try:
            fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._fd.close()
            self._fd = None
            raise AlreadyRunningError(f"sync already running; lock held at {self.path}") from exc
        self._fd.write(str(os.getpid()))
        self._fd.flush()

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
            self._fd.close()
            self._fd = None

    def __enter__(self) -> "ProcessLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
