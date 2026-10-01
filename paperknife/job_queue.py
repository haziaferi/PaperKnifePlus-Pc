"""
paperknife.job_queue
Cancellable background jobs with automatic progress-bar and Cancel-button
lifecycle management.

Usage
-----
    # In a tool's _do_X method:
    def do_work(stop: threading.Event):
        for i, item in enumerate(items):
            if stop.is_set():
                return          # honour cancel
            process(item)
            app.after(0, lambda v=(i+1)/len(items): app._prog_update(v))
        return f"✓  Processed {len(items)} item(s)"   # shown in the status bar

    app.run_job(do_work)

A str returned by the worker becomes the status-bar message.  A worker that
posts its own status with app.after(0, app._set_status(...)) keeps it: the
generic "Done" / "Cancelled" is shown only when the worker reported nothing.

Legacy workers (no stop parameter) are still supported — cancel becomes
"soft" (the on_done callback is suppressed, but the thread runs to
completion).
"""
from __future__ import annotations
import contextlib
import inspect
import os
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from typing import Callable, Iterator


@contextlib.contextmanager
def atomic_output(path: str) -> Iterator[str]:
    """Yield a temporary path beside *path*; on a clean exit move it onto
    *path* with os.replace, on an exception delete it.

    A worker that saves to the yielded path can be killed mid-write (window
    closed, process ended) without leaving a truncated file at *path*, and an
    existing file there is replaced only once the new one is complete.
    """
    target = Path(path)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.stem}-",
                               suffix=target.suffix + ".part")
    os.close(fd)
    os.unlink(tmp)
    try:
        yield tmp
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    # A worker that returned early on cancel never wrote the file.
    if os.path.exists(tmp):
        os.replace(tmp, target)


class CancellableJob:
    """Runs *fn* in a daemon thread; exposes a cancel() method."""

    def __init__(
        self,
        fn: Callable,
        after_fn: Callable,          # app.after(0, ...) scheduler
        on_done: Callable | None  = None,
        on_error: Callable | None = None,
        on_cancel: Callable | None = None,
    ):
        self._stop      = threading.Event()
        self._fn        = fn
        self._after     = after_fn
        self._on_done   = on_done
        self._on_error  = on_error
        self._on_cancel = on_cancel
        self._running   = False

        # Detect whether fn accepts a stop_event argument
        try:
            sig   = inspect.signature(fn)
            nargs = len(sig.parameters)
        except (TypeError, ValueError):
            nargs = 0
        self._pass_stop = nargs > 0

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

    @property
    def stop(self) -> threading.Event:
        return self._stop

    # ── Internal ───────────────────────────────────────────────────────────────
    def _post(self, callback):
        # after() from this thread raises once the window has been destroyed
        # (RuntimeError "main thread is not in main loop", or TclError).
        try:
            self._after(0, callback)
        except (RuntimeError, tk.TclError):
            pass

    def _run(self):
        try:
            result = self._fn(self._stop) if self._pass_stop else self._fn()
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
