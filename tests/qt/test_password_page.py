"""The Qt Password page: add, change or remove a PDF's encryption.

Since 2026-10-23 (owner's sort: a tool applied with OK changes the open
document) Protect and Remove password set the document's protection as one
undoable edit; Save or Save as writes the file with it."""
import pymupdf as fitz

from qt_harness import make_pdf, pump, save_as, wait_job


def _page(window):
    assert window.open_tool("PasswordTool")
    pump(0.05)
    return window.current_page()


def _protect(window, dialogs, src, out, user="u", owner="", print_=True, copy=True,
             current="", opened_with=None):
    page = _page(window)
    if opened_with:
        dialogs.passwords.append(opened_with)      # asked when the file is opened
    page.file.set_path(src)
    page.pw1.setText(user)
    page.pw2.setText(owner)
    page.cur_pw.setText(current)
    page.allow_print.setChecked(print_)
    page.allow_copy.setChecked(copy)
    page.protect()
    assert not dialogs.errors(), dialogs.errors()
    save_as(window, dialogs, out)
    return page


def test_the_page_builds_with_its_controls(window):
    page = _page(window)
    assert type(page).__name__ == "PasswordPage"
    assert page.title_label.text() == "Password"
    assert page.allow_print.isChecked() and page.allow_copy.isChecked()


def test_without_input_each_action_warns(window, dialogs, tmp_path):
    page = _page(window)
    page.protect()
    assert dialogs.msgs[-1] == ("warning", "Protect", "Select a PDF first.")
    page.unprotect()
    assert dialogs.msgs[-1] == ("warning", "Unprotect", "Select a PDF first.")
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.protect()
    assert dialogs.msgs[-1] == ("warning", "Protect", "Enter a password.")


def test_protect_sets_the_document_s_protection_and_save_as_writes_it(window, dialogs,
                                                                     tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    _protect(window, dialogs, src, out, owner="o")
    assert window.applied_status == "✓  Password set · Save writes it to the file"
    assert not [m for m in dialogs.msgs if m[0] == "info"]
    with fitz.open(out) as doc:
        assert doc.needs_pass and not doc.authenticate("wrong")
        assert doc.authenticate("u")
        assert doc[0].get_text().strip() == "Page 1" and len(doc) == 3
    with fitz.open(src) as doc:
        assert not doc.needs_pass                   # only what is saved is protected


def test_save_over_the_file_protects_it_and_undo_takes_it_back(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    page = _page(window)
    page.file.set_path(src)
    page.pw1.setText("u")
    page.protect()
    assert window.document.dirty and window.windowTitle().startswith("in.pdf* — ")
    assert window.undo() and window.document.protection is None and not window.document.dirty
    page.pw1.setText("u")
    page.protect()
    window.save()
    wait_job(window)
    with fitz.open(src) as doc:
        assert doc.needs_pass and doc.authenticate("u")
    # The protection stays the document's: a later save keeps it.
    from paperknife.qt.pages import same_path
    assert same_path(window.document.path, src)
    window.document.edit("A note", lambda d: d[0].add_text_annot((72, 72), "n"))
    window.save()
    wait_job(window)
    with fitz.open(src) as doc:
        assert doc.needs_pass and doc.authenticate("u")


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


def test_password_change_on_a_file_opened_with_its_password(window, dialogs, tmp_path):
    first = tmp_path / "first.pdf"
    _protect(window, dialogs, make_pdf(tmp_path / "in.pdf"), first, user="old", owner="o")
    assert window.clear_current_document()
    out = tmp_path / "second.pdf"
    _protect(window, dialogs, str(first), out, user="new", opened_with="old")
    with fitz.open(out) as doc:
        assert not doc.authenticate("old") and doc.authenticate("new")


def test_an_owner_password_file_is_protected_without_its_owner_password(window, dialogs,
                                                                       tmp_path):
    # As before 2026-10-23: MuPDF opens a file with an owner password only
    # (none to open it) as not encrypted, so nothing asks for the owner password.
    # Owner, 2026-10-23: keep it so; the user may not know that password.
    src = tmp_path / "owner.pdf"
    d = fitz.open()
    d.new_page()
    d.save(str(src), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="boss",
           permissions=int(fitz.PDF_PERM_PRINT))
    d.close()
    out = tmp_path / "out.pdf"
    _protect(window, dialogs, str(src), out, user="new")
    with fitz.open(out) as doc:
        assert doc.needs_pass and doc.authenticate("new")


def test_remove_password_and_save_as_writes_an_unencrypted_copy(window, dialogs, tmp_path):
    locked = make_pdf(tmp_path / "locked.pdf", password="right")
    out = tmp_path / "unlocked.pdf"
    page = _page(window)
    dialogs.passwords.append("right")              # asked when the file is opened
    page.file.set_path(locked)
    page.cur_pw.setText("right")
    page.unprotect()
    assert not dialogs.errors(), dialogs.errors()
    assert window.status_text() == "✓  Password removed · Save writes the file without it"
    save_as(window, dialogs, out)
    assert not [m for m in dialogs.msgs if m[0] == "ask_yes_no"]     # nothing to keep
    with fitz.open(out) as doc:
        assert not doc.is_encrypted and doc[1].get_text().strip() == "Page 2"


def test_a_wrong_current_password_changes_nothing(window, dialogs, tmp_path):
    locked = make_pdf(tmp_path / "locked.pdf", password="right")
    page = _page(window)
    dialogs.passwords.append("right")
    page.file.set_path(locked)
    page.cur_pw.setText("wrong")
    page.unprotect()
    assert dialogs.errors()[-1] == ("error", "Error", "Incorrect password.")
    assert window.document.protection is None and not window.document.dirty


def test_removing_a_password_from_an_open_file_says_so(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.unprotect()
    assert dialogs.msgs[-1] == ("info", "Unprotect", "This PDF has no password.")
    assert not window.document.dirty


def test_a_dropped_pdf_fills_the_file_card_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(src) is True and page.file.path() == src


def test_the_protection_never_shows_its_passwords(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.pw1.setText("secret-open")
    page.pw2.setText("secret-owner")
    page.protect()
    p = window.document.protection
    assert "secret" not in repr(p) and "secret" not in window.status_text()


def test_passwords_do_not_stay_in_the_fields_after_an_action(window, dialogs, tmp_path):
    # R45-5: the passwords stayed for the session, and the eye button shows them.
    src = make_pdf(tmp_path / "in.pdf")
    page = _protect(window, dialogs, src, str(tmp_path / "p.pdf"), user="secret",
                    owner="boss", current="old")
    assert (page.pw1.text(), page.pw2.text(), page.cur_pw.text()) == ("", "", "")
    page.cur_pw.setText("whatever")
    page.unprotect()                               # a protection set here: no check
    assert page.cur_pw.text() == ""


def test_passwords_are_cleared_when_the_page_is_left(window, tmp_path):
    page = _page(window)
    page.pw1.setText("secret")
    page.pw2.setText("boss")
    page.cur_pw.setText("old")
    window.show_page("home")
    assert (page.pw1.text(), page.pw2.text(), page.cur_pw.text()) == ("", "", "")


def test_a_refused_action_clears_the_typed_passwords(window, dialogs, tmp_path):
    """Inventory finding (phase9/memory-inventory.md, behaviour 6): a refused
    action returned early, so the typed password stayed."""
    page = _page(window)
    for action in (page.protect, page.unprotect):
        page.pw1.setText("secret")
        page.pw2.setText("boss")
        page.cur_pw.setText("old")
        action()                                   # no file chosen: refused
        assert (page.pw1.text(), page.pw2.text(), page.cur_pw.text()) == ("", "", "")
