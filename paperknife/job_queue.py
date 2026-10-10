"""
paperknife.job_queue
Cancellable background jobs, and atomic_output for writing a file in one move.

    job = CancellableJob(work, post, on_done=..., on_error=..., on_cancel=...)
    job.start()

work(stop) runs in a daemon thread and should return soon after stop is set;
post(callback) must run callback on the UI thread (the Qt shell passes
bridge.post).  on_done(result), on_error(exc) or on_cancel() then runs there.
"""
from __future__ import annotations
import contextlib
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Iterator


_LIVE_PARTS: set[str] = set()       # temp files an atomic_output still owns


def live_parts() -> list[str]:
    """The temp files atomic_output has created and not yet moved or deleted
    (a worker still writing; the Qt shell records them when it quits before
    the worker ends, so the next start can remove them)."""
    return sorted(_LIVE_PARTS)


_FINISH = threading.local()         # this thread's finishing step (finishing_outputs)


@contextlib.contextmanager
def finishing_outputs(finish) -> Iterator[None]:
    """While the block runs, every atomic_output in this thread calls
    finish(target, tmp) on its complete temporary file just before moving it
    onto target; an exception from finish discards the file instead."""
    prev = getattr(_FINISH, "fn", None)
    _FINISH.fn = finish
    try:
        yield
    finally:
        _FINISH.fn = prev


@contextlib.contextmanager
def atomic_output(path: str) -> Iterator[str]:
    """Yield a temporary path beside *path*; on a clean exit move it onto
    *path* with os.replace, on an exception delete it.

    A worker that saves to the yielded path can be killed mid-write (window
    closed, process ended) without leaving a truncated file at *path*, and an
    existing file there is replaced only once the new one is complete.
    """
    target = Path(path)
    # The temp file is created here and kept, so no other process can take
    # its name before the writer opens it; every writer used overwrites it.
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.stem}-",
                               suffix=target.suffix + ".part")
    os.close(fd)
    _LIVE_PARTS.add(tmp)
    try:
        yield tmp
        # A worker that returned early on cancel never wrote the file.
        if os.path.getsize(tmp) == 0:
            os.unlink(tmp)
            return
        finish = getattr(_FINISH, "fn", None)
        if finish is not None:
            # Before the move: the file reaches *path* already finished (a
            # file that keeps its input's password is encrypted here).
            finish(str(target), tmp)
        try:
            os.replace(tmp, target)
        except PermissionError as exc:
            raise PermissionError(
                f"Cannot replace {target.name}: it is open in another program.") from exc
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    finally:
        _LIVE_PARTS.discard(tmp)


class CancellableJob:
    """Runs *fn(stop)* in a daemon thread; exposes a cancel() method."""

    def __init__(
        self,
        fn: Callable,
        post: Callable,              # post(callback): run callback on the UI thread
        on_done: Callable | None  = None,
        on_error: Callable | None = None,
        on_cancel: Callable | None = None,
    ):
        self._stop      = threading.Event()
        self._fn        = fn
        self._post      = post
        self._on_done   = on_done
        self._on_error  = on_error
        self._on_cancel = on_cancel
        self._running   = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    # ── Public API ─────────────────────────────────────────────────────────────
    def start(self) -> "CancellableJob":
        self._running = True
        self._thread.start()
        return self

    def cancel(self):
        self._stop.set()

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Internal ───────────────────────────────────────────────────────────────
    def _run(self):
        try:
            result = self._fn(self._stop)
        except Exception as exc:
            self._running = False
            if self._on_error:
                self._post(lambda e=exc: self._on_error(e))
            return

        self._running = False
        if self._stop.is_set():
            if self._on_cancel:
                self._post(self._on_cancel)
        else:
            if self._on_done:
                self._post(lambda r=result: self._on_done(r))
