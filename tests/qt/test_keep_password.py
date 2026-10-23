"""A PDF written from a password-protected input asks, once per action, whether
the new file keeps the password: Yes = AES-256 with the same open password and
the input's permissions, a random owner password; No = no password.

The question comes after the save dialog (Cancel there asks nothing), and only
when the output is a PDF and the input needed a password to open."""
import os

import pymupdf as fitz

from qt_harness import make_pdf, pump, spy_open, wait_job

OPEN_PW, OWNER_PW = "open-pw", "owner-pw"
# Print and accessibility only: no copy, no modify, no annotate, no assemble.
PERM = fitz.PDF_PERM_PRINT | fitz.PDF_PERM_ACCESSIBILITY


def _question(name):
    return ("ask_yes_no", "Password",
            f'"{name}" is password-protected. Keep the password on the new file?')


def _locked(path, pages=3, toc=None, user=OPEN_PW, perm=PERM):
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 100), f"Page {i + 1}", fontsize=14)
    if toc:
        doc.set_toc(toc)
    doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256,
             user_pw=user, owner_pw=OWNER_PW, permissions=perm)
    doc.close()
    return str(path)


def _p_of(path):
    """The /P value of the file's encryption dictionary (its permissions)."""
    with fitz.open(path) as d:
        return d.xref_get_key(-1, "Encrypt/P")


def _assert_kept(out, src):
    """*out* needs the open password, its owner password is neither the open
    password nor the input's, it is AES-256, and its permissions are the input's."""
    with fitz.open(out) as d:
        assert d.needs_pass, f"{out} opens without a password"
        assert not d.authenticate("")
        assert not d.authenticate(OWNER_PW), "the input's owner password was kept"
    with fitz.open(out) as d:
        # 2 = user rights only: 6 would mean the owner password is the open one.
        assert d.authenticate(OPEN_PW) == 2
        assert "AES" in d.metadata["encryption"] and "256" in d.metadata["encryption"]
        assert not d.permissions & fitz.PDF_PERM_COPY
        assert d.permissions & fitz.PDF_PERM_PRINT
    assert _p_of(out) == _p_of(src)


def _assert_open(out):
    with fitz.open(out) as d:
        assert not d.needs_pass and not d.is_encrypted


def _tool(window, name):
    assert window.open_tool(name)
    pump(0.05)
    return window.current_page()


# ── a run_on_file page: Compress ─────────────────────────────────────────────
def _compress(window, dialogs, src, out, answer=None, password=OPEN_PW):
    page = _tool(window, "CompressTool")
    if password is not None:
        dialogs.passwords.append(password)      # asked when the file opens
    page.file.set_path(src)
    if out is not None:
        dialogs.save(out)
    if answer is not None:
        dialogs.asks.append(answer)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    return page


def test_compress_yes_keeps_the_open_password_and_the_permissions(window, dialogs, tmp_path):
    src = _locked(tmp_path / "in.pdf")
    out = tmp_path / "small.pdf"
    _compress(window, dialogs, src, out, answer=True)
    assert _question("in.pdf") in dialogs.msgs
    _assert_kept(out, src)
    with fitz.open(out) as d:
        d.authenticate(OPEN_PW)
        assert [p.get_text().strip() for p in d] == ["Page 1", "Page 2", "Page 3"]


def test_compress_no_writes_a_file_without_a_password(window, dialogs, tmp_path):
    src = _locked(tmp_path / "in.pdf")
    out = tmp_path / "small.pdf"
    _compress(window, dialogs, src, out, answer=False)
    assert _question("in.pdf") in dialogs.msgs
    _assert_open(out)


def test_the_question_comes_after_the_save_dialog(window, dialogs, tmp_path):
    src = _locked(tmp_path / "in.pdf")
    _compress(window, dialogs, src, None)          # Cancel at the save dialog
    assert [m[0] for m in dialogs.msgs] == ["ask_password"]
    assert sorted(os.listdir(tmp_path)) == ["in.pdf"]


def test_an_unprotected_input_asks_nothing(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "small.pdf"
    _compress(window, dialogs, src, out, password=None)
    assert not [m for m in dialogs.msgs if m[0] in ("ask_yes_no", "ask_password")]
    _assert_open(out)


def test_an_owner_password_only_input_asks_nothing(window, dialogs, tmp_path):
    # It opens freely: there is no open password to keep.
    src = tmp_path / "in.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(src), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=OWNER_PW,
             permissions=PERM)
    doc.close()
    out = tmp_path / "small.pdf"
    _compress(window, dialogs, str(src), out, password=None)
    assert not [m for m in dialogs.msgs if m[0] in ("ask_yes_no", "ask_password")]
    _assert_open(out)


def test_a_non_pdf_output_asks_nothing(window, dialogs, tmp_path):
    page = _tool(window, "Pdf2DocTool")
    dialogs.passwords.append(OPEN_PW)             # asked when the file opens
    page.file.set_path(_locked(tmp_path / "in.pdf", pages=1))
    page.fmt.setCurrentText("PNG")
    dialogs.save(tmp_path / "pages.zip")
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert not [m for m in dialogs.msgs if m[0] == "ask_yes_no"]
    assert (tmp_path / "pages.zip").exists()


def test_the_password_is_gone_once_the_job_closed_the_document(window, dialogs, tmp_path,
                                                               monkeypatch):
    from paperknife.core import password as core
    opened = spy_open(window, monkeypatch)
    _compress(window, dialogs, _locked(tmp_path / "in.pdf"), tmp_path / "o.pdf", answer=True)
    doc = opened[-1]              # the job's own copy (the page holds the file while shown)
    assert doc.is_closed
    assert core.open_password_of(doc) is None
    assert OPEN_PW not in repr(vars(doc))


def _reaches_password(obj, seen=None) -> bool:
    """Whether *obj* (a function, its closure cells, lists, dicts) leads to an
    OpenPassword or the open password itself."""
    from paperknife.core.password import OpenPassword
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return False
    seen.add(id(obj))
    if isinstance(obj, OpenPassword) or obj == OPEN_PW:
        return True
    if callable(obj) and getattr(obj, "__closure__", None):
        return any(_reaches_password(c.cell_contents, seen) for c in obj.__closure__
                   if c.cell_contents is not None)
    if isinstance(obj, (list, tuple, set)):
        return any(_reaches_password(x, seen) for x in obj)
    if isinstance(obj, dict):
        return any(_reaches_password(x, seen) for x in obj.values())
    return False


def test_the_finished_job_keeps_no_password(window, dialogs, tmp_path):
    # The window keeps its last job until the next one starts.
    _compress(window, dialogs, _locked(tmp_path / "in.pdf"), tmp_path / "o.pdf", answer=True)
    _assert_kept(tmp_path / "o.pdf", tmp_path / "in.pdf")
    job = window._current_job
    assert job is not None and not job.is_running
    assert not _reaches_password(job._fn)


def test_remove_password_opens_a_yes_output_with_the_open_password_alone(window, dialogs,
                                                                        tmp_path):
    src = _locked(tmp_path / "in.pdf")
    kept = tmp_path / "kept.pdf"
    _compress(window, dialogs, src, kept, answer=True)
    page = _tool(window, "PasswordTool")
    page.file.set_path(str(kept))
    page.cur_pw.setText(OPEN_PW)
    out = tmp_path / "unlocked.pdf"
    dialogs.save(out)
    page.unprotect()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    _assert_open(out)
    with fitz.open(out) as d:
        assert d[2].get_text().strip() == "Page 3"


# ── DocHolder saves: Metadata (held), Annotate (workspace), TOC, Rotate ──────
def _metadata(window, dialogs, src):
    page = _tool(window, "MetadataTool")
    dialogs.passwords.append(OPEN_PW)
    page.file.set_path(src)
    assert page._doc is not None
    return page


def _save(window, dialogs, page, out, answer=None):
    """Save as *out* (the window's; it asks whether the new file keeps the
    password: *answer*)."""
    dialogs.save(out)
    if answer is not None:
        dialogs.asks.append(answer)
    window.save_as()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()


def _save_over(window, dialogs):
    """Save (the window's): over the file, its password kept, nothing asked."""
    window.save()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()


def test_metadata_save_as_yes_and_no(window, dialogs, tmp_path):
    src = _locked(tmp_path / "in.pdf")
    page = _metadata(window, dialogs, src)
    page.fields["title"].setText("Kept")
    _save(window, dialogs, page, tmp_path / "yes.pdf", True)
    _assert_kept(tmp_path / "yes.pdf", src)
    _save(window, dialogs, page, tmp_path / "no.pdf", False)   # (the document is yes.pdf now)
    _assert_open(tmp_path / "no.pdf")
    # (the question names the file the password was given for)
    assert dialogs.msgs.count(_question("in.pdf")) == 2


def test_metadata_saved_over_its_source_twice_keeps_the_password_both_times(window, dialogs,
                                                                           tmp_path):
    # After the first save over the source the page goes on from an in-memory
    # copy: the password goes with it.
    src = _locked(tmp_path / "in.pdf")
    p_in = _p_of(src)
    page = _metadata(window, dialogs, src)
    page.fields["title"].setText("One")
    _save_over(window, dialogs)
    assert _p_of(src) == p_in
    _assert_kept(src, src)
    page.fields["title"].setText("Two")
    _save_over(window, dialogs)
    _assert_kept(src, src)
    assert _p_of(src) == p_in
    with fitz.open(src) as d:
        d.authenticate(OPEN_PW)
        assert d.metadata["title"] == "Two"
    assert dialogs.msgs.count(_question("in.pdf")) == 0         # Save keeps it, unasked


def test_cancel_at_a_doc_holder_save_dialog_asks_nothing(window, dialogs, tmp_path):
    _metadata(window, dialogs, _locked(tmp_path / "in.pdf"))
    window.save_as()                              # no path queued: Cancel
    assert window._current_job is None
    assert not [m for m in dialogs.msgs if m[0] == "ask_yes_no"]


def test_the_held_password_is_forgotten_when_the_document_is_closed(window, dialogs, tmp_path):
    from paperknife.core import password as core
    page = _metadata(window, dialogs, _locked(tmp_path / "in.pdf"))
    held = page._doc
    kept = core.open_password_of(held)
    assert kept is not None and kept.user_pw == OPEN_PW
    assert OPEN_PW not in repr(kept)              # never in a log line or a traceback
    assert window.clear_current_document()        # the document is closed
    assert held.is_closed and page._doc is None
    assert core.open_password_of(held) is None
    assert OPEN_PW not in repr(vars(held))


def test_annotate_save_keeps_the_password(window, dialogs, tmp_path):
    src = _locked(tmp_path / "in.pdf")
    page = _tool(window, "AnnotateTool")
    dialogs.passwords.append(OPEN_PW)
    page.open_path(src)
    assert page._doc is not None
    out = tmp_path / "annotated.pdf"
    _save(window, dialogs, page, out, True)
    _assert_kept(out, src)


def test_toc_save_as_no_writes_an_open_copy_and_the_source_keeps_it(window, dialogs,
                                                                    tmp_path):
    src = _locked(tmp_path / "in.pdf", toc=[[1, "A", 1]])
    page = _tool(window, "TocTool")
    dialogs.passwords.append(OPEN_PW)
    page.file.set_path(src)
    out = tmp_path / "open.pdf"
    _save(window, dialogs, page, out, False)
    _assert_open(out)
    with fitz.open(out) as d:
        assert d.get_toc() == [[1, "A", 1]]
    with fitz.open(src) as d:
        assert d.needs_pass


def test_toc_saved_over_an_owner_password_only_source_keeps_its_encryption(window, dialogs,
                                                                         tmp_path):
    # No open password, so no question; the save over the source keeps the
    # restrictions as it did before (PDF_ENCRYPT_KEEP).
    src = tmp_path / "in.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.set_toc([[1, "A", 1]])
    doc.save(str(src), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw=OWNER_PW,
             permissions=PERM)
    doc.close()
    p_in = _p_of(src)
    page = _tool(window, "TocTool")
    page.file.set_path(str(src))
    page.title_edit.setText("B")
    page.page_edit.setText("1")
    page._add()
    _save_over(window, dialogs)
    assert not [m for m in dialogs.msgs if m[0] in ("ask_yes_no", "ask_password")]
    assert _p_of(src) == p_in
    with fitz.open(src) as d:
        assert d.metadata.get("encryption") and [e[1] for e in d.get_toc()] == ["A", "B"]


def test_redact_asks_after_its_confirmation_and_the_save_dialog(window, dialogs, tmp_path):
    src = _locked(tmp_path / "in.pdf")
    dialogs.passwords.append(OPEN_PW)
    assert window.open_tool("RedactTool", src)
    pump(0.1)
    page = window.current_page()
    page._pending = [(0, fitz.Rect(60, 80, 200, 110), None)]
    out = tmp_path / "redacted.pdf"
    dialogs.save(out)
    dialogs.asks.extend([True, True])             # Confirm Redaction, then keep the password
    page.apply_redactions()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    asked = [m[1] for m in dialogs.msgs if m[0] == "ask_yes_no"]
    assert asked == ["Confirm Redaction", "Password"]
    _assert_kept(out, src)
    with fitz.open(out) as d:
        d.authenticate(OPEN_PW)
        assert "Page 1" not in d[0].get_text()


def test_rotate_save_keeps_the_password(window, dialogs, tmp_path):
    src = _locked(tmp_path / "in.pdf")
    page = _tool(window, "RotateTool")
    dialogs.passwords.append(OPEN_PW)
    page.file.set_path(src)
    out = tmp_path / "reordered.pdf"
    _save(window, dialogs, page, out, True)
    _assert_kept(out, src)


# ── splits: one question, every part ─────────────────────────────────────────
def _parts(folder):
    return sorted(f for f in os.listdir(folder) if f.endswith(".pdf"))


def test_split_yes_asks_once_and_protects_every_part(window, dialogs, tmp_path):
    src = _locked(tmp_path / "in.pdf")
    out_dir = tmp_path / "parts"
    out_dir.mkdir()
    page = _tool(window, "SplitTool")
    dialogs.passwords.append(OPEN_PW)             # Split asks when the file opens
    page.file.set_path(src)
    dialogs.dirs.append(str(out_dir))
    dialogs.asks.append(True)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert dialogs.msgs.count(_question("in.pdf")) == 1
    parts = _parts(out_dir)
    assert len(parts) == 3
    for name in parts:
        _assert_kept(out_dir / name, src)


def test_split_no_writes_open_parts(window, dialogs, tmp_path):
    src = _locked(tmp_path / "in.pdf")
    out_dir = tmp_path / "parts"
    out_dir.mkdir()
    page = _tool(window, "SplitTool")
    dialogs.passwords.append(OPEN_PW)             # Split asks when the file opens
    page.file.set_path(src)
    dialogs.dirs.append(str(out_dir))
    dialogs.asks.append(False)
    page.run()
    wait_job(window)
    for name in _parts(out_dir):
        _assert_open(out_dir / name)


def test_split_cancel_at_the_folder_dialog_asks_nothing(window, dialogs, tmp_path):
    page = _tool(window, "SplitTool")
    dialogs.passwords.append(OPEN_PW)
    page.file.set_path(_locked(tmp_path / "in.pdf"))
    page.run()                                    # no folder queued: Cancel
    assert window._current_job is None
    assert not [m for m in dialogs.msgs if m[0] == "ask_yes_no"]


def test_split_by_bookmarks_yes_protects_every_chapter(window, dialogs, tmp_path):
    src = _locked(tmp_path / "book.pdf", pages=4, toc=[[1, "One", 1], [1, "Two", 3]])
    out_dir = tmp_path / "chapters"
    out_dir.mkdir()
    page = _tool(window, "SplitTool")
    dialogs.passwords.append(OPEN_PW)
    page.file.set_path(src)
    page.radios["top"].setChecked(True)          # Split by Bookmarks is Split's "Cut at"
    dialogs.dirs.append(str(out_dir))
    dialogs.asks.append(True)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert dialogs.msgs.count(_question("book.pdf")) == 1
    assert _parts(out_dir) == ["01_One.pdf", "02_Two.pdf"]
    for name in _parts(out_dir):
        _assert_kept(out_dir / name, src)


# ── Merge: asked only when the protected inputs share one open password ─────
PERM_B = fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY | fitz.PDF_PERM_ACCESSIBILITY


def _merge(window, dialogs, paths, passwords, out, answer=None):
    page = _tool(window, "MergeTool")
    dialogs.passwords.extend(passwords)           # asked when each file is added
    page.add_paths(paths)
    dialogs.save(out)
    if answer is not None:
        dialogs.asks.append(answer)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()


def test_merge_of_inputs_sharing_a_password_keeps_it_with_only_the_common_rights(
        window, dialogs, tmp_path):
    plain = make_pdf(tmp_path / "plain.pdf", pages=1)
    a = _locked(tmp_path / "a.pdf", pages=1)                  # print, accessibility
    b = _locked(tmp_path / "b.pdf", pages=2, perm=PERM_B)     # print, copy, accessibility
    out = tmp_path / "merged.pdf"
    _merge(window, dialogs, [plain, a, b], [OPEN_PW, OPEN_PW], out, answer=True)
    assert dialogs.msgs.count(_question("a.pdf")) == 1        # the first protected input
    with fitz.open(out) as d:
        assert d.needs_pass and not d.authenticate(OWNER_PW)
    with fitz.open(out) as d:
        assert d.authenticate(OPEN_PW) == 2
        assert len(d) == 4
        assert "AES" in d.metadata["encryption"] and "256" in d.metadata["encryption"]
        p = int(d.xref_get_key(-1, "Encrypt/P")[1])
    pa, pb = int(_p_of(a)[1]), int(_p_of(b)[1])
    assert pa != pb and p == pa & pb
    assert p & fitz.PDF_PERM_PRINT and not p & fitz.PDF_PERM_COPY


def test_merge_no_writes_an_open_file(window, dialogs, tmp_path):
    a, b = _locked(tmp_path / "a.pdf", pages=1), _locked(tmp_path / "b.pdf", pages=1)
    out = tmp_path / "merged.pdf"
    _merge(window, dialogs, [a, b], [OPEN_PW, OPEN_PW], out, answer=False)
    assert dialogs.msgs.count(_question("a.pdf")) == 1
    _assert_open(out)


def test_merge_of_inputs_with_different_passwords_asks_nothing(window, dialogs, tmp_path):
    a = _locked(tmp_path / "a.pdf", pages=1)
    b = _locked(tmp_path / "b.pdf", pages=1, user="another")
    out = tmp_path / "merged.pdf"
    _merge(window, dialogs, [a, b], [OPEN_PW, "another"], out)   # no answer queued
    assert not [m for m in dialogs.msgs if m[0] == "ask_yes_no"]
    _assert_open(out)


def test_merge_of_unprotected_inputs_asks_nothing(window, dialogs, tmp_path):
    out = tmp_path / "merged.pdf"
    _merge(window, dialogs, [make_pdf(tmp_path / "a.pdf"), make_pdf(tmp_path / "b.pdf")],
           [], out)
    assert not [m for m in dialogs.msgs if m[0] in ("ask_yes_no", "ask_password")]
    _assert_open(out)


def test_merge_cancel_at_the_save_dialog_asks_nothing(window, dialogs, tmp_path):
    page = _tool(window, "MergeTool")
    dialogs.passwords.append(OPEN_PW)
    page.add_paths([_locked(tmp_path / "a.pdf", pages=1)])
    page.run()                                    # no path queued: Cancel
    assert window._current_job is None
    assert not [m for m in dialogs.msgs if m[0] == "ask_yes_no"]


# ── never unprotected at the final name, not even for a moment ──────────────
def _spy_final_moves(monkeypatch):
    """Every os.replace onto a final .pdf name: (name, was the file moved there
    encrypted?).  Moves onto a .part (steps before the final one) are not recorded."""
    real, moves = os.replace, []

    def spy(src, dst):
        if str(dst).endswith(".pdf"):
            with fitz.open(str(src)) as d:
                moves.append((os.path.basename(str(dst)), bool(d.needs_pass)))
        return real(src, dst)
    monkeypatch.setattr(os, "replace", spy)
    return moves


def test_every_yes_output_reaches_its_name_already_encrypted(window, dialogs, tmp_path,
                                                             monkeypatch):
    src = _locked(tmp_path / "in.pdf")
    moves = _spy_final_moves(monkeypatch)
    _compress(window, dialogs, src, tmp_path / "small.pdf", answer=True)    # run_on_file
    page = _metadata(window, dialogs, src)                                   # DocHolder
    page.fields["title"].setText("Saved")
    _save_over(window, dialogs)                                              # over the source
    assert window.clear_current_document()          # Split and Merge read the file afresh
    out_dir = tmp_path / "parts"
    out_dir.mkdir()
    page = _tool(window, "SplitTool")                                        # a split
    dialogs.passwords.append(OPEN_PW)
    page.file.set_path(src)
    dialogs.dirs.append(str(out_dir))
    dialogs.asks.append(True)
    page.run()
    wait_job(window)
    _merge(window, dialogs, [src, _locked(tmp_path / "b.pdf", pages=1)],    # Merge
           [OPEN_PW, OPEN_PW], tmp_path / "merged.pdf", answer=True)
    assert not dialogs.errors(), dialogs.errors()
    names = [n for n, _ in moves]
    assert names == ["small.pdf", "in.pdf", "in_part01_p1-1.pdf", "in_part02_p2-2.pdf",
                     "in_part03_p3-3.pdf", "merged.pdf"]
    assert all(enc for _, enc in moves), moves


def test_a_crash_before_the_encryption_leaves_no_unprotected_file(window, dialogs, tmp_path,
                                                                  monkeypatch):
    # The output is written, then the step that encrypts it fails: the final
    # name holds nothing (a new file) or the old file (a save over the source).
    from paperknife.core import password as core

    def boom(*_a):
        raise OSError("stopped between the write and the encryption")
    monkeypatch.setattr(core, "encrypt_file", boom)
    src = _locked(tmp_path / "in.pdf")
    before = open(src, "rb").read()
    page = _tool(window, "CompressTool")
    dialogs.passwords.append(OPEN_PW)             # asked when the file opens
    page.file.set_path(src)
    dialogs.save(tmp_path / "small.pdf")
    dialogs.asks.append(True)
    page.run()
    wait_job(window)
    assert not (tmp_path / "small.pdf").exists()
    page = _metadata(window, dialogs, src)
    page.fields["title"].setText("Changed")
    window.save()
    wait_job(window)
    dialogs.unsaved.append("discard")             # the failed save left the edit unsaved
    assert window.clear_current_document()
    assert open(src, "rb").read() == before
    assert sorted(os.listdir(tmp_path)) == ["in.pdf"]       # no .part left either
    assert len(dialogs.errors()) == 2
