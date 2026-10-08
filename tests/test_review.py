"""Review-pass fixes: rotated/cropped editing, saving over an open file,
document lifetime across navigation, redaction scope, Story loop guard,
prefs recovery, batch cancel status, password prompts in converters."""
import os
from pathlib import Path

import pymupdf as fitz
import pytest

from conftest import make_pdf, pump, tool, wait_job


def _hello_pdf(path, rot=0, crop=None):
    doc = fitz.open()
    page = doc.new_page(width=400, height=600)
    page.insert_text((120, 200), "Hello there", fontsize=14)
    if crop:
        page.set_cropbox(fitz.Rect(crop))
    if rot:
        page.set_rotation(rot)
    doc.save(str(path))
    doc.close()
    return str(path)


def _words(page, text):
    return [fitz.Rect(w[:4]) for w in page.get_text("words") if w[4] == text]


def _parts(folder):
    return [f for f in os.listdir(folder) if f.endswith(".part")]


# ── RC-01 / RC-11: Edit Text and Find & Replace with undo ────────────────────
def _edit(t, new_text):
    blk = t._blocks[0]
    t._select_block(blk["bi"])
    t._edit_box.delete("1.0", "end")
    t._edit_box.insert("1.0", new_text)
    t._apply_edit()


def test_edit_text_on_rotated_page_applies_and_undoes(app, dialogs, tmp_path):
    t = tool(app, "EditTextTool")
    dialogs.open(_hello_pdf(tmp_path / "in.pdf", rot=90))
    t._open()
    assert t._blocks, "no text blocks shown on the rotated page"
    _edit(t, "Howdy there")
    assert "Howdy" in t._doc[0].get_text()
    t._undo()
    text = t._doc[0].get_text()
    assert "Hello there" in text and "Howdy" not in text
    assert not dialogs.errors(), dialogs.errors()


def test_find_replace_on_rotated_page_applies_and_undoes(app, dialogs, tmp_path):
    t = tool(app, "FindReplaceTool")
    dialogs.open(_hello_pdf(tmp_path / "in.pdf", rot=90))
    t._open()
    t._find_var.set("Hello")
    t._find_all()
    wait_job(app)
    assert t._hits
    t._repl_var.set("World")
    t._replace_all()
    wait_job(app)
    assert "World" in t._doc[0].get_text()
    t._undo()
    text = t._doc[0].get_text()
    assert "Hello" in text and "World" not in text
    assert not dialogs.errors(), dialogs.errors()


def test_failed_edit_puts_the_original_text_back(app, dialogs, tmp_path, monkeypatch):
    t = tool(app, "EditTextTool")
    dialogs.open(_hello_pdf(tmp_path / "in.pdf"))
    t._open()

    def boom(*a, **k):
        raise RuntimeError("writer failed")
    monkeypatch.setattr(fitz.TextWriter, "write_text", boom)
    try:
        _edit(t, "Howdy there")
    except RuntimeError:
        pass        # the baseline let it escape the Tk callback
    assert "Hello there" in t._doc[0].get_text()
    assert any("writer failed" in m[2] for m in dialogs.errors()), dialogs.msgs


# ── RC-07: replacement text on a cropped page ────────────────────────────────
def test_replace_on_cropped_page_keeps_the_baseline(app, dialogs, tmp_path):
    src = _hello_pdf(tmp_path / "in.pdf", crop=(50, 50, 380, 560))
    with fitz.open(src) as d:
        before = _words(d[0], "Hello")[0]
    t = tool(app, "FindReplaceTool")
    dialogs.open(src)
    t._open()
    t._find_var.set("Hello")
    t._repl_var.set("World")
    t._replace_all()
    wait_job(app)
    after = _words(t._doc[0], "World")
    assert after and abs(after[0].y1 - before.y1) < 1 and abs(after[0].x0 - before.x0) < 1, (
        before, after)


def test_edit_on_cropped_page_keeps_the_baseline(app, dialogs, tmp_path):
    src = _hello_pdf(tmp_path / "in.pdf", crop=(50, 50, 380, 560))
    with fitz.open(src) as d:
        before = _words(d[0], "Hello")[0]
    t = tool(app, "EditTextTool")
    dialogs.open(src)
    t._open()
    _edit(t, "Howdy there")
    after = _words(t._doc[0], "Howdy")
    assert after and abs(after[0].y1 - before.y1) < 2, (before, after)


# ── RC-02 / RC-03 / RS-06: saving over an input that is open ─────────────────
def test_merge_can_write_over_one_of_its_inputs(app, dialogs, tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=2, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=1, text="B{n}")
    t = tool(app, "MergeTool")
    t._add_entry(a)
    t._add_entry(b)
    dialogs.save(a)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(a) as d:
        assert [p.get_text().strip() for p in d] == ["A1", "A2", "B1"]
    assert _parts(tmp_path) == []


def test_merge_accepts_all_as_its_placeholder_says(app, dialogs, tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=2, text="A{n}")
    out = tmp_path / "out.pdf"
    t = tool(app, "MergeTool")
    t._add_entry(a)
    t._entries[0]["range_var"].set("all")
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as d:
        assert len(d) == 2


def test_metadata_saves_over_the_open_input(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    t = tool(app, "MetadataTool")
    dialogs.open(src)
    t._open()
    t._vars["title"].set("New title")
    dialogs.save(src)
    t._save()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    assert _parts(tmp_path) == []
    tool(app, "CropTool")
    with fitz.open(src) as d:
        assert d.metadata["title"] == "New title"


@pytest.mark.parametrize("name", ["EditTextTool", "FindReplaceTool", "AnnotateTool", "RedactTool"])
def test_content_tools_save_over_the_open_input(app, dialogs, tmp_path, name):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    t = tool(app, name)
    dialogs.open(src)
    t._open()
    dialogs.save(src)
    dialogs.asks.append(True)
    t._save()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    assert len(t._doc) == 2, "the tool lost its document after saving"
    tool(app, "CropTool")
    with fitz.open(src) as d:
        assert len(d) == 2


def test_toc_saved_in_place_keeps_the_password(app, dialogs, tmp_path, monkeypatch):
    src = tmp_path / "enc.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.save(str(src), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    doc.close()
    _answer_password(monkeypatch, "u")
    t = tool(app, "TocTool")
    dialogs.open(str(src))
    t._open()
    t._title_var.set("Chapter")
    t._page_var.set("2")
    t._add()
    dialogs.save(str(src))
    t._save()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    tool(app, "CropTool")
    with fitz.open(str(src)) as d:
        assert d.needs_pass
        assert d.authenticate("u")
        assert d.get_toc() == [[1, "Chapter", 2]]


# ── RC-04 / RC-12: leaving a tool releases its file ──────────────────────────
@pytest.mark.parametrize("holder", ["RotateTool", "BookmarksTool", "TocTool", "MetadataTool"])
def test_file_opened_in_another_tool_can_be_overwritten(app, dialogs, tmp_path, holder):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    t = tool(app, holder)
    dialogs.open(src)
    t._open()
    held = t._doc
    c = tool(app, "CropTool")
    assert held.is_closed
    c._path.set(src)
    c._margins["top"].set("50")
    dialogs.save(src)
    c._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    assert _parts(tmp_path) == []


def test_reader_releases_its_file_and_reopens_on_return(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    r = tool(app, "ReaderTool")
    r.open_path(src)
    held = r._doc
    tool(app, "CropTool")
    pump(app, 0.3)
    assert held.is_closed
    r = tool(app, "ReaderTool")
    assert r._doc is not None and r._path_var.get() == src


# ── RC-05: a failed replace leaves no temp file ──────────────────────────────
def test_atomic_output_removes_its_temp_file_when_replace_fails(tmp_path, monkeypatch):
    from paperknife.job_queue import atomic_output
    out = tmp_path / "out.pdf"
    out.write_bytes(b"old")

    def locked(*a):
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr(os, "replace", locked)
    with pytest.raises(PermissionError):
        with atomic_output(str(out)) as tmp:
            Path(tmp).write_bytes(b"new")
    assert out.read_bytes() == b"old"
    assert _parts(tmp_path) == []


# ── RC-06: a drawn box scrubs only what it covered ───────────────────────────
def test_redact_box_over_short_text_leaves_unrelated_content(app, dialogs, tmp_path):
    src = tmp_path / "in.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "12", fontsize=14)
    p2 = doc.new_page()
    p2.insert_text((72, 100), "Keep me", fontsize=14)
    p2.add_text_annot((300, 300), "Unrelated reviewer note")
    doc.set_toc([[1, "Intro", 1], [1, "Chapter 12 overview", 2]])
    doc.set_metadata({"title": "Report 2012"})
    doc.save(str(src))
    doc.close()
    t = tool(app, "RedactTool")
    dialogs.open(str(src))
    t._open()
    t._pending.append((0, fitz.Rect(70, 85, 100, 105), None))
    t._apply()
    wait_job(app)
    out = tmp_path / "out.pdf"
    dialogs.save(str(out))
    t._save()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(str(out)) as d:
        assert "12" not in d[0].get_text()
        assert [a.info["content"] for a in d[1].annots()] == ["Unrelated reviewer note"]
        assert [e[1] for e in d.get_toc()] == ["Intro", "Chapter 12 overview"]
        assert d.metadata["title"] == "Report 2012"


# ── RC-08: a table row taller than a page stops with a message ───────────────
def test_html_with_unsplittable_row_stops_instead_of_looping(app, dialogs, tmp_path, monkeypatch):
    real = fitz.DocumentWriter
    pages = {"n": 0}

    class Capped:
        def __init__(self, path, *a, **k):
            self._w = real(path, *a, **k)

        def begin_page(self, rect):
            pages["n"] += 1
            if pages["n"] > 40:
                raise RuntimeError("runaway Story loop")
            return self._w.begin_page(rect)

        def end_page(self):
            self._w.end_page()

        def close(self):
            self._w.close()

    monkeypatch.setattr(fitz, "DocumentWriter", Capped)
    src = tmp_path / "row.html"
    src.write_text("<table><tr><td>" + "line<br>" * 400 + "</td></tr></table>",
                   encoding="utf-8")
    out = tmp_path / "row.pdf"
    t = tool(app, "Doc2PdfTool")
    t._fmt.set("HTML")
    t._path.set(str(src))
    dialogs.save(out)
    t._run()
    wait_job(app)
    errors = dialogs.errors()
    assert errors and "taller than a page" in errors[0][2], errors
    assert not out.exists() and _parts(tmp_path) == []


# ── RC-09: an undecodable prefs.json is set aside, not fatal ─────────────────
def test_prefs_file_that_is_not_utf8_is_renamed(tmp_path, monkeypatch):
    from paperknife import prefs
    path = tmp_path / "prefs.json"
    path.write_bytes(b"\xff\xfe{\x00}\x00")
    monkeypatch.setattr(prefs, "PREFS_PATH", path)
    p = prefs.Prefs()
    assert p.default_dpi == 150
    assert (tmp_path / "prefs.json.bad").exists()


# ── RC-10: a cancelled batch says so ─────────────────────────────────────────
def test_cancelled_batch_does_not_report_success(app, dialogs, tmp_path, monkeypatch):
    from paperknife.tools import batch
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    for n in "abc":
        make_pdf(in_dir / f"{n}.pdf", pages=1)

    def compress_then_cancel(doc, out, level):
        doc.close()
        Path(out).write_bytes(b"%PDF-1.7")
        app._cancel_job()
    monkeypatch.setattr(batch, "compress_pdf", compress_then_cancel)
    t = tool(app, "BatchTool")
    t._in_dir_var.set(str(in_dir))
    t._out_dir_var.set(str(out_dir))
    t._run()
    wait_job(app)
    status = app.status_var.get()
    assert "cancel" in status.lower() and "✓" not in status, status


# ── RC-13 / RS-09: single-file converters ask for the password ───────────────
def _answer_password(monkeypatch, pw):
    import customtkinter as ctk

    class Answer:
        def __init__(self, *a, **k):
            pass

        def get_input(self):
            return pw
    monkeypatch.setattr(ctk, "CTkInputDialog", Answer)


def _encrypted(path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Locked text", fontsize=14)
    doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    doc.close()
    return str(path)


def test_pdf_to_images_unlocks_a_protected_input(app, dialogs, tmp_path, monkeypatch):
    import zipfile
    _answer_password(monkeypatch, "u")
    t = tool(app, "Pdf2ImgTool")
    t._path.set(_encrypted(tmp_path / "enc.pdf"))
    out = tmp_path / "pages.zip"
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist() == ["page_0001.png"]


def test_pdf_to_text_unlocks_a_protected_input(app, dialogs, tmp_path, monkeypatch):
    _answer_password(monkeypatch, "u")
    t = tool(app, "Pdf2DocTool")
    t._fmt.set("TXT")
    t._fmt_changed("TXT")
    t._path.set(_encrypted(tmp_path / "enc.pdf"))
    out = tmp_path / "out.txt"
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    assert "Locked text" in out.read_text(encoding="utf-8")


def test_extract_images_unlocks_a_protected_input(app, dialogs, tmp_path, monkeypatch):
    _answer_password(monkeypatch, "u")
    t = tool(app, "ExtractTool")
    t._path.set(_encrypted(tmp_path / "enc.pdf"))
    out_dir = tmp_path / "imgs"
    out_dir.mkdir()
    dialogs.dirs.append(str(out_dir))
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()


# ── RS-01: render budget and batch DPI range ─────────────────────────────────
def test_render_refuses_or_shrinks_a_huge_page():
    from paperknife.pages import MAX_PIXELS, render
    doc = fitz.open()
    page = doc.new_page(width=14400, height=14400)
    with pytest.raises(ValueError, match="too large"):
        render(page, 300 / 72)
    pix = render(page, 3, shrink=True)
    assert pix.width * pix.height <= MAX_PIXELS


def test_batch_dpi_above_the_settings_range_is_refused(app, dialogs, tmp_path):
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    make_pdf(in_dir / "a.pdf", pages=1)
    t = tool(app, "BatchTool")
    t._op.set("OCR")
    t._op_changed("OCR")
    t._in_dir_var.set(str(in_dir))
    t._out_dir_var.set(str(tmp_path))
    t._opt_widgets["dpi"].set("5000")
    t._run()
    wait_job(app)       # a job wrongly started here must not outlive the test
    assert any(m[0] == "showwarning" and "600" in m[2] for m in dialogs.msgs), dialogs.msgs


# ── RS-11: a fallback that changes the output is reported ────────────────────
def test_unparsable_xml_conversion_says_it_fell_back(app, dialogs, tmp_path):
    src = tmp_path / "bad.xml"
    src.write_text("<a><b>unclosed</a>", encoding="utf-8")
    out = tmp_path / "bad.pdf"
    t = tool(app, "Doc2PdfTool")
    t._fmt.set("XML")
    t._path.set(str(src))
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert out.exists()
    assert any("could not be parsed" in m[2] for m in dialogs.msgs), dialogs.msgs


# ── L4-65: folder and save dialogs start in the preferred output folder ──────
def test_output_dialogs_start_in_the_preferred_folder(app, dialogs, tmp_path, monkeypatch):
    from tkinter import filedialog
    from paperknife.prefs import PREFS
    monkeypatch.setitem(PREFS._data, "output_dir", str(tmp_path))
    seen = []
    monkeypatch.setattr(filedialog, "askdirectory",
                        lambda *a, **k: seen.append(k.get("initialdir")) or "")
    monkeypatch.setattr(filedialog, "asksaveasfilename",
                        lambda *a, **k: seen.append(k.get("initialdir")) or "")
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    s = tool(app, "SplitTool")
    s._path.set(src)
    s._run()
    wait_job(app)
    p = tool(app, "Pdf2ImgTool")
    p._path.set(src)
    p._run()
    wait_job(app)
    d = tool(app, "Pdf2DocTool")
    d._path.set(src)
    d._run()
    wait_job(app)
    assert seen == [str(tmp_path)] * 3, seen
