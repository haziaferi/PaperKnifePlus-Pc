"""paperknife.qt.dialogs itself.  Every page test replaces this module's
functions (the dialogs fixture), so here the real ones run, with only Qt's
static QFileDialog calls stubbed: the Qt counterpart of the CTk suite's
test_output_dialogs_start_in_the_preferred_folder (tests/test_review.py)."""
import os

import pytest


@pytest.fixture
def file_dialog(qapp, monkeypatch):
    """Record what the real dialogs module asks QFileDialog; answer from .answers."""
    from PySide6.QtWidgets import QFileDialog
    from paperknife.qt import dialogs as dmod
    rec = {"calls": [], "answers": []}

    def save(parent, title, initial, filters, *a, **k):
        rec["calls"].append(("save", initial, filters))
        return (rec["answers"].pop(0) if rec["answers"] else ""), ""

    def folder(parent, title, start, *a, **k):
        rec["calls"].append(("dir", start))
        return rec["answers"].pop(0) if rec["answers"] else ""
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(save))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(folder))
    monkeypatch.setattr(dmod, "_last_dir", "")
    monkeypatch.setattr(dmod, "_doc_dir", "")
    return rec


def test_save_and_folder_dialogs_start_in_the_preferred_output_folder(file_dialog, tmp_path):
    from paperknife.prefs import PREFS
    from paperknife.qt import dialogs as dmod
    out = tmp_path / "exports"
    out.mkdir()
    PREFS.output_dir = str(out)
    file_dialog["answers"] = [str(out / "merged.pdf")]
    assert dmod.ask_save("merged.pdf", ".pdf", [("PDF", "*.pdf")]) == str(out / "merged.pdf")
    file_dialog["answers"] = [str(out)]
    assert dmod.ask_dir() == str(out)
    assert file_dialog["calls"] == [
        ("save", os.path.join(str(out), "merged.pdf"), "PDF (*.pdf);;All files (*.*)"),
        ("dir", str(out))]


def test_save_adds_the_extension_only_when_none_was_typed(file_dialog, tmp_path):
    from paperknife.qt import dialogs as dmod
    file_dialog["answers"] = [str(tmp_path / "report"), str(tmp_path / "report.txt"), ""]
    assert dmod.ask_save("x.pdf", ".pdf") == str(tmp_path / "report.pdf")
    assert dmod.ask_save("x.pdf", ".pdf") == str(tmp_path / "report.txt")
    assert dmod.ask_save("x.pdf", ".pdf") == ""                  # cancelled


def test_a_missing_output_folder_is_not_offered(file_dialog, tmp_path):
    from paperknife.prefs import PREFS
    from paperknife.qt import dialogs as dmod
    PREFS.output_dir = str(tmp_path / "gone")
    dmod.ask_save("a.pdf", ".pdf")
    dmod.ask_dir()
    assert file_dialog["calls"][0][1] == "a.pdf" and file_dialog["calls"][1] == ("dir", "")


def test_with_no_folder_known_a_dialog_starts_beside_the_document(file_dialog, tmp_path):
    """Opened from Recent files, a document left no folder behind, and the first
    Save as opened in the app's working folder (the walk, 2026-10-22)."""
    from paperknife.prefs import PREFS
    from paperknife.qt import dialogs as dmod
    PREFS.output_dir = ""
    doc = tmp_path / "docs" / "in.pdf"
    doc.parent.mkdir()
    dmod.note_document(str(doc))
    dmod.ask_save("out.pdf", ".pdf")
    assert file_dialog["calls"][-1][1] == os.path.join(str(doc.parent), "out.pdf")
    dmod.note_document(None)
    dmod.ask_save("out.pdf", ".pdf")
    assert file_dialog["calls"][-1][1] == "out.pdf"


def test_the_current_document_tells_the_dialogs_its_folder(window, tmp_path):
    from qt_harness import make_pdf
    from paperknife.qt import dialogs as dmod
    src = make_pdf(tmp_path / "in.pdf")
    window.set_current_document(src)
    assert dmod._doc_dir == str(tmp_path)
    window.set_current_document(None)
    assert dmod._doc_dir == ""
