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
