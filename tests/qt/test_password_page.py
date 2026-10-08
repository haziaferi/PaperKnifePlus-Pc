"""The Qt Password page: add, change or remove a PDF's encryption."""
import threading

import pymupdf as fitz

from qt_harness import make_pdf, pump, wait_job


def _page(window):
    assert window.open_tool("PasswordTool")
    pump(0.05)
    return window.current_page()


def _spy_open(monkeypatch):
    from paperknife.core import password as core
    opened = []
    real = core.open_unlocked

    def spy(*a, **k):
        doc = real(*a, **k)
        opened.append(doc)
        return doc
    monkeypatch.setattr(core, "open_unlocked", spy)
    return opened


def _protect(window, dialogs, src, out, user="u", owner="", print_=True, copy=True,
             current=""):
    page = _page(window)
    page.file.set_path(src)
    page.pw1.setText(user)
    page.pw2.setText(owner)
    page.cur_pw.setText(current)
    page.allow_print.setChecked(print_)
    page.allow_copy.setChecked(copy)
    dialogs.save(out)
    page.protect()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    return page


def test_the_page_builds_with_its_controls(window):
    page = _page(window)
    assert type(page).__name__ == "PasswordPage"
    assert page.title_label.text() == "Password"
    assert page.allow_print.isChecked() and page.allow_copy.isChecked()


def test_without_input_each_action_warns(window, dialogs, tmp_path):
    page = _page(window)
    page.protect()
    assert dialogs.msgs[-1] == ("warning", "Protect", "Select a PDF.")
    page.unprotect()
    assert dialogs.msgs[-1] == ("warning", "Unprotect", "Select a PDF.")
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.protect()
    assert dialogs.msgs[-1] == ("warning", "Protect", "Enter a password.")


def test_protect_writes_an_encrypted_copy_and_reports_it(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    _protect(window, dialogs, src, out, owner="o")
    with fitz.open(out) as doc:
        assert doc.needs_pass and not doc.authenticate("wrong")
        assert doc.authenticate("u")
        assert doc[0].get_text().strip() == "Page 1" and len(doc) == 3
    assert dialogs.msgs[-1] == ("info", "Done", f"Protected PDF saved:\n{out}")
    assert window.status_text() == "✓  Protected → out.pdf"


def test_password_allow_switches_keep_unrelated_rights(window, dialogs, tmp_path):
    out = tmp_path / "out.pdf"
    _protect(window, dialogs, make_pdf(tmp_path / "in.pdf"), out, owner="o")
    with fitz.open(out) as doc:
        assert doc.authenticate("u")
        perm = doc.permissions
    for flag in ("PRINT", "PRINT_HQ", "COPY", "ACCESSIBILITY", "FORM", "ANNOTATE"):
        assert perm & getattr(fitz, "PDF_PERM_" + flag), flag


def test_password_unticked_print_removes_only_printing(window, dialogs, tmp_path):
    out = tmp_path / "out.pdf"
    _protect(window, dialogs, make_pdf(tmp_path / "in.pdf"), out, owner="o", print_=False)
    with fitz.open(out) as doc:
        doc.authenticate("u")
        perm = doc.permissions
    assert not perm & fitz.PDF_PERM_PRINT
    assert not perm & fitz.PDF_PERM_PRINT_HQ
    assert perm & fitz.PDF_PERM_COPY and perm & fitz.PDF_PERM_ACCESSIBILITY


def test_password_unticked_copy_removes_only_copying(window, dialogs, tmp_path):
    out = tmp_path / "out.pdf"
    _protect(window, dialogs, make_pdf(tmp_path / "in.pdf"), out, owner="o", copy=False)
    with fitz.open(out) as doc:
        doc.authenticate("u")
        perm = doc.permissions
    assert not perm & fitz.PDF_PERM_COPY
    assert perm & fitz.PDF_PERM_PRINT and perm & fitz.PDF_PERM_ACCESSIBILITY


def test_password_blank_owner_does_not_give_owner_rights(window, dialogs, tmp_path):
    out = tmp_path / "out.pdf"
    _protect(window, dialogs, make_pdf(tmp_path / "in.pdf"), out, copy=False)
    with fitz.open(out) as doc:
        # authenticate(): 2 = user rights, 4/6 = owner rights
        assert doc.authenticate("u") == 2


def test_password_change_on_an_encrypted_file(window, dialogs, tmp_path):
    first = tmp_path / "first.pdf"
    _protect(window, dialogs, make_pdf(tmp_path / "in.pdf"), first, user="old", owner="o")
    out = tmp_path / "second.pdf"
    _protect(window, dialogs, str(first), out, user="new", current="old")
    with fitz.open(out) as doc:
        assert not doc.authenticate("old") and doc.authenticate("new")


def test_protecting_an_encrypted_file_without_its_password_is_refused(window, dialogs,
                                                                     tmp_path):
    locked = make_pdf(tmp_path / "locked.pdf", password="right")
    page = _page(window)
    page.file.set_path(locked)
    page.pw1.setText("new")
    dialogs.save(tmp_path / "out.pdf")
    page.protect()
    assert dialogs.errors()[-1][1] == "Protect"
    assert "“Current password”" in dialogs.errors()[-1][2]
    assert window._current_job is None and not (tmp_path / "out.pdf").exists()


def test_remove_password_writes_an_unencrypted_copy(window, dialogs, tmp_path):
    locked = make_pdf(tmp_path / "locked.pdf", password="right")
    out = tmp_path / "unlocked.pdf"
    page = _page(window)
    page.file.set_path(locked)
    page.cur_pw.setText("right")
    dialogs.save(out)
    page.unprotect()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert not doc.is_encrypted and doc[1].get_text().strip() == "Page 2"
    assert dialogs.msgs[-1] == ("info", "Done", f"Unlocked PDF saved:\n{out}")
    assert window.status_text() == "✓  Unlocked → unlocked.pdf"


def test_a_wrong_password_is_reported_before_any_job_starts(window, dialogs, tmp_path):
    locked = make_pdf(tmp_path / "locked.pdf", password="right")
    page = _page(window)
    page.file.set_path(locked)
    page.cur_pw.setText("wrong")
    dialogs.save(tmp_path / "unlocked.pdf")
    page.unprotect()
    assert window._current_job is None, "a job started for a wrong password"
    assert dialogs.errors()[-1] == ("error", "Error", "Incorrect password.")
    assert not (tmp_path / "unlocked.pdf").exists()


def test_a_dropped_pdf_fills_the_file_card_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(src) is True and page.file.path() == src


def test_cancelling_the_save_dialog_opens_no_document(window, dialogs, tmp_path,
                                                      monkeypatch):
    opened = _spy_open(monkeypatch)
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.pw1.setText("u")
    page.protect()                 # no save path queued: the dialog returns ""
    page.unprotect()
    assert opened == [] and window._current_job is None


def test_a_refused_job_closes_the_document_it_opened(window, dialogs, tmp_path,
                                                     monkeypatch):
    opened = _spy_open(monkeypatch)
    release = threading.Event()
    window.run_job(lambda stop: release.wait(10), "Busy")
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.pw1.setText("u")
    dialogs.save(tmp_path / "out.pdf")
    page.protect()                 # another job runs: run_job warns and returns None
    assert dialogs.warnings()[-1][1] == "Busy"
    assert opened and opened[0].is_closed
    release.set()
    wait_job(window)


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path, monkeypatch):
    opened = _spy_open(monkeypatch)
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.pw1.setText("u")
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    page.protect()
    window.show_page("CompressTool")
    wait_job(window)
    assert opened and opened[0].is_closed
    with fitz.open(out) as doc:
        assert doc.needs_pass
