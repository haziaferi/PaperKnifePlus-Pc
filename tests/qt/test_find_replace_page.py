"""The Qt Find & Replace page (document workspace)."""
import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, wait_job


def _text_pdf(path, text="The quick fox jumps", rot=0, crop=None, pages=1, **kw):
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page(width=400, height=600)
        page.insert_text((72, 300), text, fontsize=14, **kw)
        if crop:
            page.set_cropbox(fitz.Rect(crop))
        if rot:
            page.set_rotation(rot)
    doc.save(str(path))
    doc.close()
    return str(path)


def _long_pdf(path, pages=60, word="needle"):
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page()
        for j in range(30):
            p.insert_text((40, 40 + j * 24), f"line {j} page {i} {word} lorem ipsum dolor sit",
                          fontsize=10)
    doc.save(str(path))
    doc.close()
    return str(path)


def _open(window, src):
    assert window.open_tool("FindReplaceTool", src)
    pump(0.05)
    page = window.current_page()
    assert page._doc is not None
    return page


def _replace(window, dialogs, page, find, repl):
    page.find_edit.setText(find)
    page.repl_edit.setText(repl)
    dialogs.asks.append(True)                   # "Replace ALL occurrences…?"
    page.replace_all()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()


def _span_with(page, needle):
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for s in ln["spans"]:
                if needle in s["text"]:
                    return s
    raise AssertionError(f"{needle!r} not on page: {page.get_text()!r}")


def _words(page, text):
    return [fitz.Rect(w[:4]) for w in page.get_text("words") if w[4] == text]


def test_page_builds_with_one_primary_and_the_fields_in_the_panel(window):
    assert window.open_tool("FindReplaceTool")
    page = window.current_page()
    assert type(page).__name__ == "FindReplacePage"
    assert page.title_label.text() == "Find & Replace"
    assert page.find_edit.placeholderText() == "Search text…"
    assert page.repl_edit.placeholderText() == "Replacement text…"
    assert page.find_edit.isVisibleTo(page.panel)


def test_actions_without_a_document_warn(window, dialogs):
    window.open_tool("FindReplaceTool")
    page = window.current_page()
    page.find_all()
    page.replace_all()
    page.save()
    assert dialogs.warnings() == [("warning", "Find", "Open a PDF first."),
                                  ("warning", "Replace", "Open a PDF first."),
                                  ("warning", "Save", "Open a PDF first.")]
    assert window._current_job is None


def test_replace_without_search_text_warns(window, dialogs, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf"))
    page.find_edit.setText("   ")
    page.replace_all()
    assert dialogs.warnings() == [("warning", "Replace", "Enter search text.")]
    assert window._current_job is None


def test_find_all_counts_draws_and_steps_through_hits(window, dialogs, tmp_path):
    src = _text_pdf(tmp_path / "in.pdf", text="fox and fox", pages=3)
    page = _open(window, src)
    page.find_edit.setText("fox")
    page.find_all()
    wait_job(window)
    assert len(page._hits) == 6 and page._hit_idx == 0 and page._pg == 0
    assert page.hit_label.text() == "Found 6 hit(s)"
    assert len(page.view._overlays) == 2          # the two hits of the shown page
    for _ in range(2):
        page.jump(1)
    assert page._pg == 1 and page.hit_label.text() == "Hit 3 / 6"
    page.jump(-3)
    assert page._hit_idx == 5 and page._pg == 2   # wraps around
    page.go(-2)
    assert page._pg == 0


def test_find_all_not_found_says_so(window, dialogs, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf"))
    page.find_edit.setText("zebra")
    page.find_all()
    wait_job(window)
    assert page._hits == [] and page.hit_label.text() == "Not found"
    assert ("info", "Find", "'zebra' not found.") in dialogs.msgs


def test_replace_then_save_writes_the_replacement(window, dialogs, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf", color=(1, 0, 0)))
    _replace(window, dialogs, page, "fox", "dog")
    assert ("ask_yes_no", "Confirm Replace",
            "Replace ALL occurrences of:\n  'fox'\nwith:\n  'dog'\n\n"
            "This modifies the PDF in memory (save to keep changes).") in dialogs.msgs
    assert page.hit_label.text() == "Replaced 1 occurrence(s)"
    assert window.status_text() == "✓  Replaced 1 occurrence(s) · Save to write to disk"
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    page.save()
    wait_job(window)
    assert ("info", "Saved", f"PDF saved:\n{out}") in dialogs.msgs
    with fitz.open(out) as d:
        text = d[0].get_text()
        assert "dog" in text and "fox" not in text and "quick" in text
        s = _span_with(d[0], "dog")
        # The replacement keeps the baseline, size and colour of what it replaced.
        assert abs(s["origin"][1] - 300) < 1 and abs(s["size"] - 14) < 0.1
        assert s["color"] == 0xFF0000


def test_empty_replacement_removes_the_text(window, dialogs, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf"))
    _replace(window, dialogs, page, "fox ", "")
    text = page._doc[0].get_text()
    assert "fox" not in text and "quick" in text and "jumps" in text


def test_replace_keeps_non_latin_text(window, dialogs, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf"))
    _replace(window, dialogs, page, "fox", "Ωμέγα Жж €")
    assert "Ωμέγα Жж €" in page._doc[0].get_text()


def test_replace_is_case_sensitive(window, dialogs, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf", text="Cat cat CAT"))
    _replace(window, dialogs, page, "cat", "dog")
    text = page._doc[0].get_text()
    assert "Cat" in text and "CAT" in text and text.count("dog") == 1, text


def test_replace_wrapped_match_once(window, dialogs, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf", text="foo bar\nbaz qux"))
    _replace(window, dialogs, page, "bar baz", "ZZZ")
    text = page._doc[0].get_text()
    assert text.count("ZZZ") == 1 and "qux" in text and "foo" in text, text


def test_declined_confirm_changes_nothing(window, dialogs, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf"))
    dialogs.asks.append(False)
    page.find_edit.setText("fox")
    page.repl_edit.setText("dog")
    page.replace_all()
    assert window._current_job is None
    assert "fox" in page._doc[0].get_text()


def test_undrawable_replacement_is_refused(window, dialogs, tmp_path, monkeypatch):
    from paperknife.core import text as core_text
    page = _open(window, _text_pdf(tmp_path / "in.pdf"))
    monkeypatch.setattr(core_text, "unicode_font", lambda text: None)
    page.find_edit.setText("fox")
    page.repl_edit.setText("dog")
    dialogs.asks.append(True)
    page.replace_all()
    assert dialogs.errors() == [
        ("error", "Replace", "The replacement contains characters no built-in font can draw.")]
    assert window._current_job is None


def test_undo_restores_the_text(window, dialogs, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf"))
    _replace(window, dialogs, page, "fox", "dog")
    page.undo()
    text = page._doc[0].get_text()
    assert "fox" in text and "dog" not in text
    assert page.hit_label.text() == "Replace undone"


def test_rotated_page_replaces_and_undoes(window, dialogs, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf", text="Hello there", rot=90))
    page.find_edit.setText("Hello")
    page.find_all()
    wait_job(window)
    assert page._hits
    _replace(window, dialogs, page, "Hello", "World")
    assert "World" in page._doc[0].get_text()
    page.undo()
    text = page._doc[0].get_text()
    assert "Hello" in text and "World" not in text


def test_cropped_page_keeps_the_baseline(window, dialogs, tmp_path):
    src = _text_pdf(tmp_path / "in.pdf", text="Hello there", crop=(50, 50, 380, 560))
    with fitz.open(src) as d:
        before = _words(d[0], "Hello")[0]
    page = _open(window, src)
    _replace(window, dialogs, page, "Hello", "World")
    after = _words(page._doc[0], "World")
    assert after and abs(after[0].y1 - before.y1) < 1 and abs(after[0].x0 - before.x0) < 1


def test_a_failed_replace_puts_every_page_back(window, dialogs, tmp_path, monkeypatch):
    from paperknife.core import text as core_text
    real = core_text.replace_matches

    def half_then_fail(doc, found, repl, font, stop=None, progress=lambda v: None):
        real(doc, found[:1], repl, font, stop, progress)
        raise RuntimeError("writer failed")
    monkeypatch.setattr(core_text, "replace_matches", half_then_fail)
    page = _open(window, _long_pdf(tmp_path / "r.pdf", pages=3))
    page.find_edit.setText("needle")
    page.repl_edit.setText("thread")
    dialogs.asks.append(True)
    page.replace_all()
    wait_job(window)
    assert any("Nothing was replaced" in m[2] for m in dialogs.errors())
    text = "".join(p.get_text() for p in page._doc)
    assert "thread" not in text and text.count("needle") == 3 * 30


def test_a_cancelled_replace_all_changes_nothing(window, dialogs, tmp_path):
    page = _open(window, _long_pdf(tmp_path / "r.pdf"))
    page.find_edit.setText("needle")
    page.repl_edit.setText("thread")
    dialogs.asks.append(True)
    page.replace_all()
    window._cancel_job()
    wait_job(window)
    text = "".join(p.get_text() for p in page._doc)
    assert "thread" not in text and text.count("needle") == 60 * 30


def test_drop_takes_pdfs_only(window, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf"))
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    second = make_pdf(tmp_path / "second.pdf", pages=4)
    assert page.accept_drop(second) is True
    assert len(page._doc) == 4 and page.subtitle_label.text() == "second.pdf"


def test_cancelled_save_dialog_writes_nothing_and_keeps_the_document(window, dialogs, tmp_path):
    page = _open(window, _text_pdf(tmp_path / "in.pdf"))
    page.save()                                  # no path queued: the dialog is cancelled
    assert window._current_job is None
    assert list(tmp_path.glob("*.pdf")) == [tmp_path / "in.pdf"]
    assert page._doc is not None and not page._doc.is_closed


def test_save_over_the_open_input_keeps_the_document(window, dialogs, tmp_path):
    src = _text_pdf(tmp_path / "in.pdf")
    page = _open(window, src)
    _replace(window, dialogs, page, "fox", "dog")
    dialogs.save(src)
    page.save()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert page._doc is not None and not page._doc.is_closed and len(page._doc) == 1
    with fitz.open(src) as d:
        assert "dog" in d[0].get_text()


@pytest.mark.parametrize("how", ["home", "other tool"])
def test_leaving_the_tool_closes_the_document(window, tmp_path, how):
    page = _open(window, _text_pdf(tmp_path / "in.pdf"))
    doc = page._doc
    if how == "home":
        window.show_page("home")
    else:
        window.open_tool("AnnotateTool")
    assert doc.is_closed and page._doc is None
