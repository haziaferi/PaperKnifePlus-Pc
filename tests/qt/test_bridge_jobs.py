"""bridge.post and MainWindow.run_job (the CTk app's run_job semantics)."""
import threading

from qt_harness import pump, wait_job

from paperknife.qt import bridge


def test_post_from_worker_runs_on_main_thread(qapp):
    seen = []

    def worker():
        bridge.post(lambda a, b: seen.append((threading.current_thread(), a, b)), 1, 2)

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert seen == []                   # queued, not run on the worker
    pump(0.1)
    assert seen == [(threading.main_thread(), 1, 2)]


def test_post_from_main_thread_is_queued(qapp):
    seen = []
    bridge.post(seen.append, "x")
    assert seen == []
    pump(0.05)
    assert seen == ["x"]


def test_post_to_deleted_widget_is_a_no_op(qapp):
    from PySide6.QtWidgets import QLabel
    from shiboken6 import delete
    lbl = QLabel()
    delete(lbl)
    # The slot swallows "already deleted"; any other RuntimeError would raise.
    bridge._get()._run((lbl.setText, ("x",)))
    bridge.post(lbl.setText, "x")
    pump(0.05)


def _blocking(release: threading.Event, started: threading.Event | None = None):
    def work(stop):
        if started is not None:
            started.set()
        while not stop.is_set() and not release.is_set():
            stop.wait(0.01)
    return work


def test_job_done_shows_done_and_calls_then(window):
    outcome = []
    job = window.run_job(lambda stop: None, "Working", then=lambda k, v: outcome.append((k, v)))
    assert job is not None
    assert window.progress_strip.isVisibleTo(window)
    wait_job(window)
    assert outcome == [("done", None)]
    assert window.status_text() == "Done"
    assert window.status_role == "success"
    assert not window.progress_strip.isVisibleTo(window)


def test_job_result_string_becomes_status(window):
    window.run_job(lambda stop: "Saved out.pdf", "Saving")
    wait_job(window)
    assert window.status_text() == "Saved out.pdf"


def test_worker_status_is_not_covered_by_done(window):
    def work(stop):
        bridge.post(window.set_status, "Wrote 3 files", "success")
    window.run_job(work, "Working")
    wait_job(window)
    assert window.status_text() == "Wrote 3 files"


def test_job_error_shows_dialog_and_status(window, dialogs):
    outcome = []

    def work(stop):
        raise ValueError("boom")
    window.run_job(work, "Working", then=lambda k, v: outcome.append((k, str(v))))
    wait_job(window)
    assert outcome == [("error", "boom")]
    assert dialogs.errors() == [("error", "Error", "boom")]
    assert window.status_text() == "Error: boom"
    assert window.status_role == "danger"


def test_job_cancel(window):
    outcome = []
    started = threading.Event()
    window.run_job(_blocking(threading.Event(), started), "Working",
                   then=lambda k, v: outcome.append(k))
    assert started.wait(5)
    window.cancel_button.click()
    wait_job(window)
    assert outcome == ["cancel"]
    assert window.status_text() == "Cancelled"
    assert window.status_role == "warning"


def test_cancel_after_worker_reported_keeps_its_status(window):
    def work(stop):
        stop.set()                      # as if Cancel came after the last check
        bridge.post(window.set_status, "Saved anyway", "success")
    window.run_job(work, "Working")
    wait_job(window)
    assert window.status_text() == "Saved anyway"


def test_second_job_refused(window, dialogs):
    release = threading.Event()
    first = window.run_job(_blocking(release), "First")
    assert first is not None
    second = window.run_job(lambda stop: None, "Second")
    assert second is None
    assert dialogs.warnings() and dialogs.warnings()[0][1] == "Busy"
    release.set()
    wait_job(window)


def test_progress_posted_from_worker(window):
    release = threading.Event()
    reached = threading.Event()

    def work(stop):
        bridge.post(window.set_progress, 0.5)
        bridge.post(reached.set)
        release.wait(5)
    window.run_job(work, "Working")
    for _ in range(50):
        pump(0.02)
        if reached.is_set():
            break
    assert window.progress.value() == 500
    release.set()
    wait_job(window)
    assert window.progress.value() == 0


def test_gc_runs_before_a_job(window, monkeypatch):
    import gc
    calls = []
    monkeypatch.setattr(gc, "collect", lambda *a: calls.append(threading.current_thread()))
    window.run_job(lambda stop: None, "Working")
    wait_job(window)
    assert calls and calls[0] is threading.main_thread()


def test_lock_holds_page_and_navigation(window, dialogs):
    release = threading.Event()
    seen = []
    window.run_job(_blocking(release), "Working", lock=True,
                   then=lambda k, v: seen.append(k))
    assert window.is_locked()
    assert not window.navigationInterface.isEnabled()
    assert not window.stackedWidget.isEnabled()
    assert window.lock_overlay.isVisible()
    assert window.cancel_button.isEnabled() and window.cancel_button.isVisible()
    assert window.show_page("MergeTool") is False          # navigation refused
    assert window._current_key == "home"
    release.set()
    wait_job(window)
    assert seen == ["done"]
    assert not window.is_locked()
    assert window.navigationInterface.isEnabled() and window.stackedWidget.isEnabled()
    assert not window.lock_overlay.isVisible()
    assert window.show_page("MergeTool") is True


def test_cancel_works_while_locked(window):
    window.run_job(_blocking(threading.Event()), "Working", lock=True)
    window.cancel_button.click()
    wait_job(window)
    assert not window.is_locked()
    assert window.status_text() == "Cancelled"
