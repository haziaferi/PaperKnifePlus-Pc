"""Qt-page checks ported from the CTk suites tests/test_review.py and
tests/test_shell.py (phase 8, map C): the behaviours no Qt test checked yet."""
import threading
import time

import pymupdf as fitz
from qt_harness import make_pdf, pump

from paperknife.tool_registry import TOOL_REGISTRY as TOOLS


def _texts(path):
    with fitz.open(path) as d:
        return [p.get_text().strip() for p in d]


# ── test_review.py ───────────────────────────────────────────────────────────
def test_merge_accepts_all_as_its_placeholder_says(window, dialogs, tmp_path):
    from qt_harness import wait_job
    a = make_pdf(tmp_path / "a.pdf", pages=2, text="A{n}")
    out = tmp_path / "out.pdf"
    assert window.open_tool("MergeTool")
    pump(0.05)
    page = window.current_page()
    page.add_paths([a])
    assert page.rows[0].extra.placeholderText().startswith("all")
    page.rows[0].extra.setText("all")
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert _texts(out) == ["A1", "A2"]


# ── test_shell.py ────────────────────────────────────────────────────────────
def _nav_widgets(window):
    panel = window.navigationInterface.panel
    return [panel.scrollLayout.itemAt(i).widget() for i in range(panel.scrollLayout.count())]


def test_search_clear_restores_every_section_in_order(window):
    before = _nav_widgets(window)
    order = [k for _h, keys in window.nav_order() for k in keys]
    assert sorted(order) == sorted(t.name for t in TOOLS)
    for q in ("merge", "", "img", "", "zzz-no-match", ""):
        window.search.edit.setText(q)
    assert _nav_widgets(window) == before
    assert window.visible_tools() == order
    for _s, header, _k in window._sections:
        assert header is None or not header.isHidden(), header.text()


def test_an_empty_file_card_shows_the_drop_hint_until_a_file_is_set(qapp, tmp_path):
    # The hint half of CTk test_tkdnd_loads_and_file_row_is_a_drop_target (L1-10).
    from paperknife.qt import pages
    card = pages.file_card()
    assert card.name_label.text() == "Drop a PDF here"
    card.set_path(make_pdf(tmp_path / "doc.pdf", pages=1))
    assert card.name_label.text() == "doc.pdf"
    card.clear()
    assert card.name_label.text() == "Drop a PDF here"
    card.deleteLater()


def test_close_during_a_job_cancels_it_and_waits_for_the_worker(window, dialogs, monkeypatch,
                                                               tmp_path):
    out = tmp_path / "out.bin"
    started = threading.Event()

    def work(stop):
        started.set()
        while not stop.is_set():
            time.sleep(0.01)
        time.sleep(0.2)                 # the save still finishing after Cancel
        out.write_bytes(b"complete")
    job = window.run_job(work, "Saving")
    assert started.wait(5)
    running_at_close = []
    real = window._finish_close
    monkeypatch.setattr(window, "_finish_close",
                        lambda: (running_at_close.append(job.is_running), real())[1])
    dialogs.asks.append(True)
    window.close()
    for _ in range(100):
        pump(0.05)
        if not window.isVisible():
            break
    assert not window.isVisible()
    assert job._stop.is_set(), "close did not cancel the job"
    assert running_at_close == [False], "window closed while the worker was running"
    assert out.read_bytes() == b"complete"


def test_home_survives_a_recent_entry_without_a_name(window, tmp_path):
    from paperknife.recent import RECENT
    src = make_pdf(tmp_path / "a.pdf", pages=1)
    window.show_page("CompressTool")
    RECENT._entries = [{"path": src}]          # the conftest restores RECENT after
    assert window.show_page("home")
    home = window.current_page()
    assert [c.name_label.text() for c in home.cards] == ["a.pdf"]


def test_version_is_release(window):
    from paperknife import __version__
    assert __version__ == "4.0.0"
    assert window.windowTitle().endswith("v4.0.0")
