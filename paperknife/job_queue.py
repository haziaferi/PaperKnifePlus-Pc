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
        return result           # passed to on_done

    app.run_job(do_work)

Legacy workers (no stop parameter) are still supported — cancel becomes
"soft" (the on_done callback is suppressed, but the thread runs to
completion).
"""
from __future__ import annotations
import inspect
import threading
from typing import Callable, Any


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
    def _run(self):
        try:
            result = self._fn(self._stop) if self._pass_stop else self._fn()
        except Exception as exc:
            self._running = False
            if self._on_error:
                self._after(0, lambda e=exc: self._on_error(e))
            return

        self._running = False
        if self._stop.is_set():
            if self._on_cancel:
                self._after(0, self._on_cancel)
        else:
            if self._on_done:
                self._after(0, lambda r=result: self._on_done(r))
