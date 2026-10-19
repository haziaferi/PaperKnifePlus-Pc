"""After a job: ask once (owner, phase9/docui-brief.md section 3).  A job
that writes one PDF puts an InfoBar at the top of the page, "<name> is
ready", with Continue with it / Start over; leaving the page counts as
Continue; jobs with several outputs ask nothing."""
import os

import pytest

from qt_harness import image_pdf, make_pdf, pump, wait_job


def _same(a, b):
    from paperknife.qt.pages import same_path
    return same_path(a, b)


def _open(window, tool, path=None):
    assert window.open_tool(tool, path)
    pump(0.05)
    return window.current_page()


def _compress(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    out = str(tmp_path / "small.pdf")
    page = _open(window, "CompressTool", src)
    dialogs.save(out)
    page.run()
    wait_job(window)
    return page, src, out


def test_a_finished_job_asks_once_in_an_info_bar(window, dialogs, tmp_path):
    from qfluentwidgets import InfoBar
    page, _src, out = _compress(window, dialogs, tmp_path)
    bar = page.offer_bar()
    assert isinstance(bar, InfoBar) and bar.isVisibleTo(page)
    assert page.layout().itemAt(0).widget() is bar           # at the top of the page
    assert bar.title == "small.pdf is ready"
    assert bar.continue_button.text() == "Continue with it"
    assert bar.start_over_button.text() == "Start over"
    assert not [m for m in dialogs.msgs if m[0] == "ask_yes_no"]   # not a modal question


def test_continue_with_it_makes_the_output_current_and_shows_it(window, dialogs, tmp_path):
    page, _src, out = _compress(window, dialogs, tmp_path)
    page.offer_bar().continue_button.click()
    assert _same(window.current_document, out) and _same(page.file.path(), out)
    assert page.offer_bar() is None


def test_start_over_clears_the_tool_and_the_current_document(window, dialogs, tmp_path):
    page, _src, _out = _compress(window, dialogs, tmp_path)
    page.offer_bar().start_over_button.click()
    assert window.current_document is None and page.file.path() == ""
    assert page.offer_bar() is None and page.drop_target.isVisibleTo(page)


def test_opening_another_tool_counts_as_continue(window, dialogs, tmp_path):
    page, _src, out = _compress(window, dialogs, tmp_path)
    split = _open(window, "SplitTool")
    assert _same(window.current_document, out) and _same(split.file.path(), out)
    assert page.offer_bar() is None


def test_a_collection_run_asks_and_its_list_empties(window, dialogs, tmp_path):
    a, b = make_pdf(tmp_path / "a.pdf"), make_pdf(tmp_path / "b.pdf")
    out = str(tmp_path / "merged.pdf")
    page = _open(window, "MergeTool")
    page.add_paths([a, b])
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert page.paths() == []                         # cleared after a finished job
    assert page.offer_bar().title == "merged.pdf is ready"
    page.offer_bar().continue_button.click()
    assert _same(window.current_document, out)


def test_an_editor_saving_to_a_new_file_asks(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    out = str(tmp_path / "meta.pdf")
    page = _open(window, "MetadataTool", src)
    page.fields["title"].setText("T")
    dialogs.save(out)
    page.save()
    wait_job(window)
    assert page.offer_bar().title == "meta.pdf is ready"
    page.offer_bar().continue_button.click()
    assert _same(page.file.path(), out) and page.fields["title"].text() == "T"


def test_an_editor_saving_over_its_own_file_asks_nothing(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    page = _open(window, "MetadataTool", src)
    page.fields["title"].setText("T")
    dialogs.save(src)
    page.save()
    wait_job(window)
    assert page.offer_bar() is None and _same(window.current_document, src)


@pytest.mark.parametrize("tool", ["SplitTool", "ExtractTool", "Pdf2DocTool"])
def test_jobs_with_several_outputs_ask_nothing(window, dialogs, tmp_path, tool):
    src = image_pdf(tmp_path / "in.pdf") if tool == "ExtractTool" else make_pdf(tmp_path / "in.pdf")
    page = _open(window, tool, src)
    outdir = tmp_path / "out"
    outdir.mkdir()
    if tool == "Pdf2DocTool":
        page.fmt.setCurrentText("PNG")          # PDF → Images until 2026-10-18
        dialogs.save(str(outdir / "pages.zip"))
    else:
        dialogs.dirs.append(str(outdir))
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert os.listdir(outdir)
    assert page.offer_bar() is None and _same(window.current_document, src)


def test_batch_asks_nothing_and_empties_its_list(window, dialogs, tmp_path):
    inp, outp = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    outp.mkdir()
    make_pdf(inp / "one.pdf")
    src = make_pdf(tmp_path / "current.pdf")
    _open(window, "CompressTool").file.set_path(src)
    page = _open(window, "BatchTool")
    page._set_in_dir(str(inp))
    page._set_out_dir(str(outp))
    page.run()
    wait_job(window)
    assert os.listdir(outp)
    assert page.offer_bar() is None and _same(window.current_document, src)
    assert page.rows == [] and page.in_dir == ""
