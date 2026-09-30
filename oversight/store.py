"""Where the person's attention state lives.

The interrupt budget belongs to a person, not to a process. When several agents, or several
Claude Code hook processes, act for the same person they must share one budget. A StateStore
gives each decision an exclusive read, decide, write transaction on that shared state.

    MemoryStore   one process (default)
    FileStore     several processes on one machine (file lock + atomic replace; Linux, macOS, Windows)

A Redis or database store only needs to implement `transaction()`.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, Protocol


def fresh_state() -> dict[str, Any]:
    return {"interrupt_times": [], "available": True}


class StateStore(Protocol):
    def transaction(self) -> Any:  # context manager yielding a mutable dict; changes are saved on exit
        ...


class MemoryStore:
    def __init__(self) -> None:
        self._state = fresh_state()
        self._lock = threading.RLock()

    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]:
        with self._lock:
            yield self._state


@contextmanager
def _exclusive(f: IO[str]) -> Iterator[None]:
    """Blocking exclusive lock on an open file, on every major OS."""
    if sys.platform == "win32":  # pragma: no cover - exercised on the Windows CI runner
        import msvcrt

        f.seek(0)
        while True:
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.01)
        try:
            yield
        finally:
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


class FileStore:
    """State in `<directory>/state.json`, guarded by `<directory>/.lock`.

    Writes go to a temp file first and are swapped in with os.replace, so a crash never leaves
    a half written state file. A corrupt or missing file starts from a fresh state.
    """

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "state.json"
        self._thread_lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text())
            return {**fresh_state(), **data} if isinstance(data, dict) else fresh_state()
        except (FileNotFoundError, json.JSONDecodeError):
            return fresh_state()

    def _write(self, state: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(state))
        os.replace(tmp, self.path)

    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]:
        with self._thread_lock, (self.directory / ".lock").open("a+") as lock_file, _exclusive(lock_file):
            state = self._read()
            yield state
            self._write(state)
