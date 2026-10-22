"""Review-pass fixes: rotated/cropped editing, saving over an open file,
document lifetime across navigation, redaction scope, Story loop guard,
prefs recovery, batch cancel status, password prompts in converters."""
import os
from pathlib import Path

import pymupdf as fitz
import pytest



def _parts(folder):
    return [f for f in os.listdir(folder) if f.endswith(".part")]


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


# ── RC-09: an undecodable prefs.json is set aside, not fatal ─────────────────
def test_prefs_file_that_is_not_utf8_is_renamed(tmp_path, monkeypatch):
    from paperknife import prefs
    path = tmp_path / "prefs.json"
    path.write_bytes(b"\xff\xfe{\x00}\x00")
    monkeypatch.setattr(prefs, "PREFS_PATH", path)
    p = prefs.Prefs()
    assert p.ocr_dpi == 200 and p.export_dpi == 200
    assert (tmp_path / "prefs.json.bad").exists()


# ── RS-01: render budget and batch DPI range ─────────────────────────────────
def test_render_refuses_or_shrinks_a_huge_page():
    from paperknife.pages import MAX_PIXELS, render
    doc = fitz.open()
    page = doc.new_page(width=14400, height=14400)
    with pytest.raises(ValueError, match="too large"):
        render(page, 300 / 72)
    pix = render(page, 3, shrink=True)
    assert pix.width * pix.height <= MAX_PIXELS




# ── 2026-10-22: the shared default_dpi became ocr_dpi + export_dpi (both 200) ─────
@pytest.mark.parametrize("stored,want", [
    ({"default_dpi": 150}, (200, 200)),          # the old default, never touched
    ({"default_dpi": 300}, (300, 300)),          # chosen: both keep it
    ({"default_dpi": 300, "ocr_dpi": 220}, (220, 300)),   # a new key already saved wins
    ({"default_dpi": 9999}, (200, 200)),         # out of range: ignored
    ({}, (200, 200)),
])
def test_the_old_shared_dpi_moves_to_the_two_new_keys(tmp_path, monkeypatch, stored, want):
    import json
    from paperknife import prefs
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps(stored), encoding="utf-8")
    monkeypatch.setattr(prefs, "PREFS_PATH", path)
    p = prefs.Prefs()
    assert (p.ocr_dpi, p.export_dpi) == want
