"""App shell, job lifecycle, prefs and recent store (FE register lane FA)."""
import json
import threading
import time
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from conftest import make_pdf, pump, tool, wait_job


def _nav_order(app):
    return [w for w in app.nav_scroll.pack_slaves()]


# ── L1-02: sidebar search ─────────────────────────────────────────────────────
def test_search_clear_restores_every_section_in_order(app):
    app._search_var.set("")
    pump(app, 0.05)
    before = _nav_order(app)
    app._search_var.set("merge")
    app._search_var.set("")
    app._search_var.set("img")
    app._search_var.set("")
    pump(app, 0.05)
    for section, lbl in app._section_labels.items():
        assert lbl.winfo_manager() == "pack", f"{section} header still hidden"
        for btn in app._section_buttons[section]:
            assert btn.winfo_manager() == "pack", btn.cget("text")
    assert _nav_order(app) == before


def test_search_with_collapsed_section_keeps_it_collapsed(app):
    section = next(iter(app._section_labels))
    app._toggle_section(section)
    try:
        app._search_var.set("zzz-no-match")
        app._search_var.set("")
        assert app._section_labels[section].winfo_manager() == "pack"
        assert all(b.winfo_manager() == "" for b in app._section_buttons[section])
    finally:
        app._toggle_section(section)
    assert all(b.winfo_manager() == "pack" for b in app._section_buttons[section])


# ── L1-03: Delete key while typing ────────────────────────────────────────────
def test_delete_key_in_text_entry_does_not_remove_list_item(app):
    fired = []
    app._cur_del_fn = lambda: fired.append(1)
    inner = app._search_entry._entry
    # Key events go to the focus window, and a withdrawn toplevel has none.
    app.deiconify()
    try:
        inner.focus_force()
        app.update()
        inner.event_generate("<Delete>", when="now")
        app.update()
        assert fired == []
        app.focus_force()
        app.update()
        app.event_generate("<Delete>", when="now")
        app.update()
        assert fired == [1]
    finally:
        app._cur_del_fn = None
        app.withdraw()


# ── L1-01: drag and drop ──────────────────────────────────────────────────────
def test_tkdnd_loads_and_file_row_is_a_drop_target(app):
    assert app._dnd_ok
    holder = ctk.CTkFrame(app.main)
    var = tk.StringVar()
    app._file_row(holder, var)
    row = holder.winfo_children()[-1]

    # dnd_bind binds on the widget's own Tcl path; CTk's .bind() would read
    # the inner canvas instead.
    def drop_script(w):
        return w.tk.call("bind", w._w, "<<Drop>>")

    assert drop_script(row), "file row has no <<Drop>> binding"
    pump(app, 0.15)
    entry = next(w for w in row.winfo_children() if isinstance(w, ctk.CTkEntry))
    assert all(drop_script(c) for c in entry.winfo_children())
    # L1-10: the hint is visible while empty and hidden once a file is set.
    hint = next(w for w in entry.winfo_children() if isinstance(w, ctk.CTkLabel))
    assert hint.winfo_manager() == "place"
    assert hint.cget("text").startswith("Drop a file here")
    var.set("C:/x.pdf")
    assert hint.winfo_manager() == ""
    holder.destroy()
    var.set("")


# ── L1-06 / L2-41: one job at a time ──────────────────────────────────────────
def test_second_job_is_refused_while_one_runs(app, dialogs):
    release = threading.Event()
    ran_b = []

    def job_a(stop):
        release.wait(10)

    def job_b(stop):
        ran_b.append(1)

    a = app.run_job(job_a, "A")
    try:
        app.run_job(job_b, "B")
        time.sleep(0.2)
        assert ran_b == []
        assert app._current_job is a
    finally:
        release.set()
        wait_job(app)


# ── L1-07 / L2-40: the tool's own status survives on_done ─────────────────────
def test_run_job_keeps_the_tools_status_message(app, dialogs):
    def work(stop):
        app.after(0, lambda: app._set_status("✓  Merged 3 pages", "#2D6A4F"))

    app.run_job(work, "Merging")
    wait_job(app)
    assert app.status_var.get().strip() == "✓  Merged 3 pages"


def test_run_job_default_done_has_no_extra_padding(app, dialogs):
    app.run_job(lambda stop: None, "Nothing")
    wait_job(app)
    assert app.status_var.get() == "  Done"


# ── L1-08: closing during a job ───────────────────────────────────────────────
def test_close_during_job_cancels_and_waits_for_worker(app, dialogs, monkeypatch, tmp_path):
    out = tmp_path / "out.bin"
    started = threading.Event()

    def work(stop):
        started.set()
        while not stop.is_set():
            time.sleep(0.01)
        time.sleep(0.2)
        out.write_bytes(b"complete")

    destroyed = []
    monkeypatch.setattr(app, "destroy",
                        lambda: destroyed.append(app._current_job.is_running))
    job = app.run_job(work, "Saving")
    started.wait(5)
    dialogs.asks.append(True)
    app._on_close()
    end = time.time() + 5
    while not destroyed and time.time() < end:
        pump(app, 0.05)
    assert job.stop.is_set(), "close did not cancel the job"
    assert destroyed == [False], "window destroyed while the worker was running"
    assert out.read_bytes() == b"complete"


# ── L1-11 / L1-30 / L1-31: malformed recent.json ──────────────────────────────
def test_home_survives_recent_entry_without_name(app, tmp_path):
    from paperknife.recent import RECENT
    src = make_pdf(tmp_path / "a.pdf", pages=1)
    saved = RECENT._entries
    RECENT._entries = [{"path": src}]
    try:
        app.show_home()
        app.update()
    finally:
        RECENT._entries = saved
        app.show_home()


def _fresh_recent(content):
    from paperknife import recent
    old = recent.RECENT_PATH.read_bytes() if recent.RECENT_PATH.exists() else None
    recent.RECENT_PATH.write_text(content, encoding="utf-8")
    try:
        return recent.RecentFiles()
    finally:
        if old is None:
            recent.RECENT_PATH.unlink()
        else:
            recent.RECENT_PATH.write_bytes(old)


def test_recent_wrong_shape_does_not_break_push(tmp_path, monkeypatch):
    src = make_pdf(tmp_path / "a.pdf", pages=1)
    for bad in ('{"a": 1}', '["x"]', '[{"path": 5}]', '[{"path": "%s"}]' %
                src.replace("\\", "\\\\")):
        store = _fresh_recent(bad)
        monkeypatch.setattr(store, "_save", lambda: None)
        store.all()
        store.push(src, 1)
        assert store.all()[0]["path"] == str(Path(src).resolve())


def test_recent_max_zero_keeps_history(tmp_path, monkeypatch):
    from paperknife.prefs import PREFS
    store = _fresh_recent("[]")
    monkeypatch.setattr(store, "_save", lambda: None)
    a = make_pdf(tmp_path / "a.pdf", pages=1)
    b = make_pdf(tmp_path / "b.pdf", pages=1)
    store.push(a)
    monkeypatch.setitem(PREFS._data, "max_recent", 0)
    store.push(b)
    assert len(store._entries) >= 1


# ── L1-25: prefs save failure is reported ─────────────────────────────────────
def test_settings_save_reports_write_failure(app, dialogs, monkeypatch, tmp_path):
    from paperknife import prefs
    blocker = tmp_path / "prefs.json"
    blocker.mkdir()
    monkeypatch.setattr(prefs, "PREFS_PATH", blocker)
    t = tool(app, "SettingsTool")
    t._save()
    kinds = [m[0] for m in dialogs.msgs]
    assert "showerror" in kinds, dialogs.msgs
    assert "showinfo" not in kinds


def test_prefs_atomic_write_leaves_old_file_on_failure(monkeypatch, tmp_path):
    import os
    from paperknife import prefs
    path = tmp_path / "prefs.json"
    path.write_text('{"ocr_lang": "ita"}')
    monkeypatch.setattr(prefs, "PREFS_PATH", path)

    def boom(*a):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    p = prefs.Prefs()
    p.ocr_lang = "deu"
    try:
        p.save()
    except OSError:
        pass
    assert json.loads(path.read_text()) == {"ocr_lang": "ita"}
    assert list(tmp_path.iterdir()) == [path]


def test_prefs_load_validates_shape(monkeypatch, tmp_path):
    from paperknife import prefs
    path = tmp_path / "prefs.json"
    monkeypatch.setattr(prefs, "PREFS_PATH", path)
    path.write_text('{"appearance": "blue", "max_recent": "7", "ocr_lang": "ita"}')
    p = prefs.Prefs()
    assert p.appearance == "light"
    assert p.max_recent == 12
    assert p.ocr_lang == "ita"
    path.write_text("[1, 2]")
    p = prefs.Prefs()
    assert p.ocr_lang == "eng"
    assert (tmp_path / "prefs.json.bad").exists()


# ── L1-41: settings range check ───────────────────────────────────────────────
def test_settings_rejects_out_of_range_max_recent(app, dialogs):
    from paperknife.prefs import PREFS
    t = tool(app, "SettingsTool")
    old = PREFS.max_recent
    t._vars["max_recent"].set("0")
    t._save()
    assert PREFS.max_recent == old
    assert any(m[0] == "showwarning" for m in dialogs.msgs), dialogs.msgs


# ── L1-36 / L4-01 / L5-33: version ────────────────────────────────────────────
def test_version_is_release(app):
    from paperknife import __version__
    assert __version__ == "3.2.2"
    assert app.title().endswith("v3.2.2")


# ── L1-08 handoff helper: atomic_output ───────────────────────────────────────
def test_atomic_output_keeps_existing_file_when_writer_fails(tmp_path):
    from paperknife.job_queue import atomic_output
    out = tmp_path / "out.pdf"
    out.write_bytes(b"old")
    try:
        with atomic_output(str(out)) as tmp:
            Path(tmp).write_bytes(b"half")
            raise RuntimeError("killed mid-write")
    except RuntimeError:
        pass
    assert out.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [out]
    with atomic_output(str(out)) as tmp:
        Path(tmp).write_bytes(b"new")
    assert out.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [out]
