"""paperknife.core.password without any user interface."""
import pymupdf as fitz
import pytest

from conftest import make_pdf
from paperknife.core import password as core


def _protected(tmp_path, user="u", owner="o", perm=core.ALL_PERMS):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    out = tmp_path / "locked.pdf"
    core.protect_pdf(fitz.open(src), str(out), user, owner, perm)
    return out


def test_owner_password_is_random_when_blank():
    a, b = core.owner_password(""), core.owner_password("")
    assert a and b and a != b
    assert core.owner_password("mine") == "mine"


@pytest.mark.parametrize("pr,cp", [(True, True), (False, True), (True, False), (False, False)])
def test_permissions_remove_only_what_is_unticked(pr, cp):
    perm = core.permissions(pr, cp)
    assert bool(perm & fitz.PDF_PERM_PRINT) is pr
    assert bool(perm & fitz.PDF_PERM_PRINT_HQ) is pr
    assert bool(perm & fitz.PDF_PERM_COPY) is cp
    assert perm & fitz.PDF_PERM_ACCESSIBILITY and perm & fitz.PDF_PERM_FORM


def test_protect_encrypts_with_the_given_rights(tmp_path):
    out = _protected(tmp_path, perm=core.permissions(False, True))
    with fitz.open(out) as d:
        assert d.needs_pass
        assert d.authenticate("u") == 2       # user rights, not owner
        assert not d.permissions & fitz.PDF_PERM_PRINT
        assert d.permissions & fitz.PDF_PERM_COPY


def test_open_unlocked_authenticates_or_returns_none(tmp_path):
    out = _protected(tmp_path)
    assert core.open_unlocked(str(out), "wrong") is None
    doc = core.open_unlocked(str(out), "u")
    assert doc is not None and not doc.is_closed
    doc.close()


def test_open_unlocked_passes_an_unencrypted_file_without_a_password(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    with core.open_unlocked(src, "", any_encryption=True) as doc:
        assert doc.page_count == 1


def test_open_unlocked_any_encryption_still_needs_the_right_password(tmp_path):
    out = _protected(tmp_path)
    assert core.open_unlocked(str(out), "bad", any_encryption=True) is None
    with core.open_unlocked(str(out), "o", any_encryption=True) as doc:
        assert doc.page_count == 1


def test_open_unlocked_lets_an_unreadable_file_raise(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    with pytest.raises(fitz.FileDataError):
        core.open_unlocked(str(bad), "")


def test_unprotect_removes_the_encryption_and_closes_the_document(tmp_path):
    locked = _protected(tmp_path)
    doc = core.open_unlocked(str(locked), "u", any_encryption=True)
    out = tmp_path / "open.pdf"
    core.unprotect_pdf(doc, str(out))
    assert doc.is_closed
    with fitz.open(out) as d:
        assert not d.is_encrypted and "Page 1" in d[0].get_text()


# ── keeping an input's open password on a new file ──────────────────────────
def _restricted(tmp_path, name="in.pdf"):
    src = make_pdf(tmp_path / f"plain-{name}", pages=2)
    out = tmp_path / name
    core.protect_pdf(fitz.open(src), str(out), "open", "owner",
                     fitz.PDF_PERM_PRINT | fitz.PDF_PERM_ACCESSIBILITY)
    return str(out)


def _opened(path, pw="open"):
    doc = fitz.open(path)
    assert doc.authenticate(pw)
    core.keep_open_password(doc, "in.pdf", pw)
    return doc


def test_input_permissions_are_the_files_not_the_rights_granted(tmp_path):
    src = _restricted(tmp_path)
    with fitz.open(src) as d:
        assert d.authenticate("owner") == 4       # owner: every right granted ...
        assert d.permissions == -4
        p = core.input_permissions(d)             # ... but the file's /P is what counts
    assert not p & fitz.PDF_PERM_COPY and p & fitz.PDF_PERM_PRINT


def test_the_kept_password_goes_with_the_document_and_is_gone_on_close(tmp_path):
    doc = _opened(_restricted(tmp_path))
    kept = core.open_password_of(doc)
    assert kept.name == "in.pdf" and kept.user_pw == "open"
    assert "open'" not in repr(kept)
    doc.close()
    assert core.open_password_of(doc) is None
    assert "open" not in repr(vars(doc))


def test_closing_through_with_forgets_it_too(tmp_path):
    with _opened(_restricted(tmp_path)) as doc:
        assert core.open_password_of(doc) is not None
    assert core.open_password_of(doc) is None


def test_an_unencrypted_document_keeps_nothing(tmp_path):
    with fitz.open(make_pdf(tmp_path / "in.pdf", pages=1)) as doc:
        assert core.open_password_of(doc) is None


def test_carry_moves_it_to_an_in_memory_copy(tmp_path):
    doc = _opened(_restricted(tmp_path))
    copy = fitz.open("pdf", doc.tobytes())
    core.carry_open_password(doc, copy)
    doc.close()
    assert core.open_password_of(copy).user_pw == "open"
    copy.close()
    assert core.open_password_of(copy) is None


def _write_plain(out, pages=2):
    """Write a plain PDF to *out* the way every tool does: through atomic_output."""
    from paperknife.job_queue import atomic_output
    with atomic_output(str(out)) as tmp, fitz.open() as nd:
        for i in range(pages):
            nd.new_page().insert_text((72, 100), f"Page {i + 1}", fontsize=14)
        nd.save(tmp)


def _spy_replaces(monkeypatch):
    """Every os.replace onto a final .pdf name: (destination, was the file moved there
    encrypted?).  A .part destination (a step before the final move) is not recorded."""
    import os
    real, moves = os.replace, []

    def spy(src, dst):
        if str(dst).endswith(".pdf"):
            with fitz.open(str(src)) as d:
                moves.append((str(dst), bool(d.needs_pass)))
        return real(src, dst)
    monkeypatch.setattr(os, "replace", spy)
    return moves


def test_protecting_encrypts_before_the_final_move(tmp_path, monkeypatch):
    src = _restricted(tmp_path)
    with fitz.open(src) as d:
        p_in = d.xref_get_key(-1, "Encrypt/P")
        d.authenticate("open")
        perm = core.input_permissions(d)
    plain = tmp_path / "out.pdf"
    other = tmp_path / "other.pdf"
    moves = _spy_replaces(monkeypatch)
    with core.protecting("open", perm, lambda target: target == str(plain)):
        _write_plain(plain)
        _write_plain(other)                       # not an output that keeps it
    _write_plain(tmp_path / "after.pdf")          # the hook ends with the block
    assert moves == [(str(plain), True), (str(other), False),
                     (str(tmp_path / "after.pdf"), False)]
    with fitz.open(other) as d:
        assert not d.needs_pass
    with fitz.open(plain) as d:
        assert d.needs_pass and not d.authenticate("owner") and not d.authenticate("")
    with fitz.open(plain) as d:
        assert d.authenticate("open") == 2        # user only: the owner password differs
        assert "AES" in d.metadata["encryption"] and "256" in d.metadata["encryption"]
        assert d.xref_get_key(-1, "Encrypt/P") == p_in
        assert d[1].get_text().strip() == "Page 2"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "after.pdf", "in.pdf", "other.pdf", "out.pdf", "plain-in.pdf"]


def test_a_failed_encryption_leaves_no_file_at_the_final_name(tmp_path, monkeypatch):
    # The write is complete, the encryption step fails (a crash between the
    # two): the final name never holds the unprotected file, and no .part stays.
    def boom(path, user_pw, perm):
        raise OSError("disk gone")
    monkeypatch.setattr(core, "encrypt_file", boom)
    out = tmp_path / "out.pdf"
    with pytest.raises(OSError, match="disk gone"):
        with core.protecting("open", core.ALL_PERMS, lambda target: True):
            _write_plain(out)
    assert list(tmp_path.iterdir()) == []


def test_a_failed_encryption_over_an_existing_file_leaves_the_old_one(tmp_path, monkeypatch):
    out = _restricted(tmp_path, "out.pdf")
    before = open(out, "rb").read()
    monkeypatch.setattr(core, "encrypt_file",
                        lambda *a: (_ for _ in ()).throw(OSError("disk gone")))
    with pytest.raises(OSError):
        with core.protecting("open", core.ALL_PERMS, lambda target: True):
            _write_plain(out)
    assert open(out, "rb").read() == before


def test_shared_open_password_needs_one_password_and_ands_the_permissions():
    a = core.OpenPassword("a.pdf", "pw", fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY | -4096)
    b = core.OpenPassword("b.pdf", "pw", fitz.PDF_PERM_PRINT | fitz.PDF_PERM_MODIFY | -4096)
    c = core.OpenPassword("c.pdf", "other", core.ALL_PERMS)
    shared = core.shared_open_password([None, a, None, b])
    assert shared.name == "a.pdf" and shared.user_pw == "pw"
    assert shared.perm == a.perm & b.perm
    assert shared.perm & fitz.PDF_PERM_PRINT
    assert not shared.perm & (fitz.PDF_PERM_COPY | fitz.PDF_PERM_MODIFY)
    assert core.shared_open_password([a, c]) is None
    assert core.shared_open_password([None, None]) is None
    assert core.shared_open_password([b]) == b


def test_doc_holder_carries_the_password_across_its_copies(tmp_path):
    from paperknife.core.doc_state import DocHolder
    src = _restricted(tmp_path)
    h = DocHolder()
    h._doc = _opened(src)
    h._undo_stack = []
    h._save_doc(src)                              # over the source: an in-memory copy
    assert core.open_password_of(h._doc).user_pw == "open"
    h._push_undo()
    h._pop_undo()
    assert core.open_password_of(h._doc).user_pw == "open"
    other = tmp_path / "other.pdf"
    h._save_doc(str(other))
    h._release(str(other))                        # not held: nothing changes
    assert core.open_password_of(h._doc).user_pw == "open"
    h._close_doc()
    h._doc = _opened(src)
    h._release(src)                               # held: goes on from a copy
    assert core.open_password_of(h._doc).user_pw == "open"
    h._close_doc()
