"""Tools hand their long work to a background job (RS-02)."""
import threading
import time

import pymupdf as fitz

from conftest import pump, tool, wait_job


def _long_pdf(path, pages=400, word="needle"):
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page()
        for j in range(30):
            p.insert_text((40, 40 + j * 24), f"line {j} page {i} {word} lorem ipsum dolor sit",
                          fontsize=10)
    doc.save(str(path))
    doc.close()
    return str(path)


def _open(t, dialogs, path):
    dialogs.open(str(path))
    t._open()
    assert t._doc is not None


def test_find_all_returns_before_the_search_is_done(app, dialogs, tmp_path):
    t = tool(app, "FindReplaceTool")
    _open(t, dialogs, _long_pdf(tmp_path / "long.pdf"))
    t._find_var.set("needle")
    t0 = time.perf_counter()
    t._find_all()
    returned = time.perf_counter() - t0
    wait_job(app)
    total = time.perf_counter() - t0
    assert len(t._hits) == 400 * 30
    assert returned < 0.25 and total > 2 * returned, (returned, total)


def test_while_a_job_holds_the_document_the_window_cannot_reach_it(
        app, dialogs, tmp_path, monkeypatch):
    t = tool(app, "AnnotateTool")
    _open(t, dialogs, _long_pdf(tmp_path / "a.pdf", pages=2))
    release = threading.Event()
    real_save = type(t)._save_doc

    def slow_save(self, out, **kw):
        release.wait(20)
        return real_save(self, out, **kw)

    monkeypatch.setattr(type(t), "_save_doc", slow_save)
    dialogs.save(tmp_path / "out.pdf")
    t._save()
    try:
        assert app._view_locked
        app._nav_click("Home", app.show_home)          # refused
        assert app._active_tool is t
        opened = []
        app._cur_open_fn = lambda: opened.append(1)
        app.event_generate("<Control-o>")
        pump(app, 0.1)
        assert opened == [], "a shortcut reached the tool while its document was in use"
    finally:
        release.set()
    wait_job(app)
    assert not app._view_locked
    assert (tmp_path / "out.pdf").exists()
    app._nav_click("Home", app.show_home)
    assert app._active_tool is None


def test_a_cancelled_replace_all_changes_nothing(app, dialogs, tmp_path):
    t = tool(app, "FindReplaceTool")
    _open(t, dialogs, _long_pdf(tmp_path / "r.pdf", pages=200))
    t._find_var.set("needle")
    t._repl_var.set("thread")
    t._replace_all()
    time.sleep(0.05)
    app._cancel_job()
    wait_job(app)
    text = "".join(p.get_text() for p in t._doc)
    # All or nothing: no page keeps a replacement, every original is back.
    assert "thread" not in text and text.count("needle") == 200 * 30


def test_a_cancelled_mark_all_marks_nothing(app, dialogs, tmp_path):
    t = tool(app, "RedactTool")
    _open(t, dialogs, _long_pdf(tmp_path / "m.pdf"))
    t._search_var.set("needle")
    t._mark_search()
    app._cancel_job()
    wait_job(app)
    assert t._pending == [], "half the matches would look like all of them"


def test_a_wrong_password_is_reported_before_any_job_starts(app, dialogs, tmp_path):
    src = tmp_path / "locked.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "secret", fontsize=12)
    doc.save(str(src), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="right", owner_pw="o")
    doc.close()
    t = tool(app, "PasswordTool")
    t._path.set(str(src))
    t._cur_pw.delete(0, "end")
    t._cur_pw.insert(0, "wrong")
    dialogs.save(tmp_path / "unlocked.pdf")
    started = app._current_job
    t._unprotect()
    assert app._current_job is started, "a job started for a wrong password"
    assert dialogs.errors() and "Incorrect password" in dialogs.errors()[-1][2]
    assert not (tmp_path / "unlocked.pdf").exists()
