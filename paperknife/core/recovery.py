"""Crash recovery: copies of unsaved edits, kept in the app's own folder.

A running app holds a Session: a folder of its own under RECOVERY_DIR with
a lock file it keeps locked while it runs.  An editing page's unsaved edits
are written into it (one entry per page: <key>.json, and <key>.pdf when the
edits are in the document itself); a save, Discard or a normal exit removes
them.  A folder whose lock nobody holds was left by an app that did not
close: its entries are what the next start offers to recover (orphaned()).
A second app running at the same time holds its own lock, so its edits are
never offered to the first.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from ..recent import APPDIR

RECOVERY_DIR = APPDIR / "recovery"
LOCK_NAME = "lock"

if os.name == "nt":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        # Windows may release a lock left on a closed handle only later.
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


@dataclass
class Entry:
    """One page's unsaved edits left by an app that did not close."""
    folder: Path
    key: str                # the page: "home" or a tool class name
    meta: dict              # path, name, tool, saved_at, state

    @property
    def pdf(self) -> bytes | None:
        p = self.folder / f"{self.key}.pdf"
        return p.read_bytes() if p.is_file() else None


class Session:
    """This app's recovery folder, locked while the app runs."""

    def __init__(self, root: Path | None = None):
        root = Path(root or RECOVERY_DIR)
        root.mkdir(parents=True, exist_ok=True)
        self.folder = root / f"{os.getpid()}-{time.time_ns()}"
        self.folder.mkdir()
        self._fd = os.open(self.folder / LOCK_NAME, os.O_RDWR | os.O_CREAT)
        os.write(self._fd, b"0")
        if not _try_lock(self._fd):         # a fresh name: cannot be held
            raise OSError(f"cannot lock {self.folder}")

    def write(self, key: str, meta: dict, pdf: bytes | None) -> None:
        """Keep *key*'s unsaved edits: the PDF first, then the description
        that names it, so an entry is never read half written."""
        pdf_path = self.folder / f"{key}.pdf"
        if pdf is not None:
            _write_atomic(pdf_path, pdf)
        else:
            pdf_path.unlink(missing_ok=True)
        meta = dict(meta, saved_at=time.time())
        _write_atomic(self.folder / f"{key}.json", json.dumps(meta).encode("utf-8"))

    def remove(self, key: str) -> None:
        (self.folder / f"{key}.json").unlink(missing_ok=True)
        (self.folder / f"{key}.pdf").unlink(missing_ok=True)

    def keys(self) -> list[str]:
        return sorted(p.stem for p in self.folder.glob("*.json"))

    def close(self) -> None:
        """A normal exit: nothing to recover."""
        self.release()
        shutil.rmtree(self.folder, ignore_errors=True)

    def release(self) -> None:
        """Let the folder go without removing it (what a crash leaves)."""
        if self._fd is not None:
            _unlock(self._fd)
            os.close(self._fd)
            self._fd = None


def _left_behind(folder: Path) -> bool:
    """Whether *folder* belongs to no running app: its lock can be taken."""
    lock = folder / LOCK_NAME
    if not lock.is_file():
        return True
    try:
        fd = os.open(lock, os.O_RDWR)
    except OSError:
        return False
    try:
        if not _try_lock(fd):
            return False
        _unlock(fd)
        return True
    finally:
        os.close(fd)


def orphaned(root: Path | None = None) -> list[Entry]:
    """The entries apps that did not close left behind, oldest first; empty
    folders they left are removed."""
    root = Path(root or RECOVERY_DIR)
    if not root.is_dir():
        return []
    found = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        if not _left_behind(folder):
            continue
        entries = []
        for j in sorted(folder.glob("*.json")):
            try:
                meta = json.loads(j.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(meta, dict):
                entries.append(Entry(folder, j.stem, meta))
        if entries:
            found += entries
        else:
            shutil.rmtree(folder, ignore_errors=True)
    return sorted(found, key=lambda e: e.meta.get("saved_at", 0))


def discard(entries: list[Entry]) -> None:
    """Remove the folders *entries* came from."""
    for folder in {e.folder for e in entries}:
        shutil.rmtree(folder, ignore_errors=True)
