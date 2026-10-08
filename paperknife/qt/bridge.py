"""
paperknife.qt.bridge
post(fn, *args): run fn(*args) on the Qt main thread, from any thread.

This replaces every `app.after(0, ...)` a worker thread made in the Tk app.
A QObject that lives on the main thread owns a signal connected with a queued
connection; emitting it from a worker puts the call on the main event loop.

Safe at the edges:
- no QApplication (not started, or already gone): the call is dropped;
- the bridge object was deleted (application shutting down): dropped;
- the callback touches a widget that was closed and deleted meanwhile: the
  RuntimeError PySide raises for a deleted C++ object is swallowed, so a job
  that ends after its window closed does nothing instead of printing a trace.
A call from the main thread is queued too (like after(0)), never run inline.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QCoreApplication, QObject, Qt, QThread, Signal, Slot

try:
    from shiboken6 import isValid as _is_valid
except ImportError:                     # pragma: no cover
    def _is_valid(obj) -> bool:
        return obj is not None


class _Bridge(QObject):
    call = Signal(object)

    def __init__(self):
        super().__init__()
        # Queued always: from a worker the call crosses to the main thread,
        # and from the main thread it waits for the loop like after(0).
        self.call.connect(self._run, Qt.QueuedConnection)

    @Slot(object)
    def _run(self, item):
        fn, args = item
        try:
            fn(*args)
        except RuntimeError as exc:
            # "Internal C++ object (...) already deleted": the window or the
            # widget the callback updates is gone; nothing left to update.
            if "already deleted" not in str(exc):
                raise


_lock = threading.Lock()
_bridge: _Bridge | None = None


def _get() -> _Bridge | None:
    global _bridge
    app = QCoreApplication.instance()
    if app is None:
        return None
    with _lock:
        if _bridge is None or not _is_valid(_bridge):
            b = _Bridge()
            if QThread.currentThread() != app.thread():
                # Created on a worker: push it to the main thread (a QObject
                # may be moved by the thread that owns it).
                b.moveToThread(app.thread())
            _bridge = b
        return _bridge


def install() -> None:
    """Create the bridge on the main thread; the shell calls this at start."""
    _get()


def post(fn, *args) -> None:
    """Run fn(*args) on the Qt main thread soon.  Never blocks, never raises."""
    b = _get()
    if b is None:
        return
    try:
        b.call.emit((fn, args))
    except RuntimeError:
        pass        # the bridge was deleted between _get() and emit()


def after(_ms, fn) -> None:
    """The after_fn signature CancellableJob expects (ms is ignored: 0)."""
    post(fn)
