"""The Qt Preferences page: setting rows and one Save that writes PREFS.

Every test writes prefs.json into its own tmp_path (PREFS_PATH is patched) and
puts PREFS and the theme back afterwards, on top of conftest's temp HOME."""
import json

import pytest

from qt_harness import make_pdf, pump


@pytest.fixture(autouse=True)
def isolated_prefs(tmp_path, monkeypatch):
    from paperknife import prefs
    from paperknife.qt import theme
    path = tmp_path / "prefs.json"
    monkeypatch.setattr(prefs, "PREFS_PATH", path)
    saved = dict(prefs.PREFS._data)
    yield path
    prefs.PREFS._data.clear()
    prefs.PREFS._data.update(saved)
    theme.apply_appearance("light")


def _page(window):
    assert window.open_tool("SettingsTool")
    pump(0.05)
    return window.current_page()


def test_the_page_shows_the_current_preferences(window):
    from paperknife.prefs import PREFS
    page = _page(window)
    assert type(page).__name__ == "SettingsPage"
    assert page.title_label.text() == "Preferences"
    assert sum(1 for b in page._buttons if b.pk_primary) == 1
    assert page.values() == {k: PREFS.get(k) for k in page.values()}


def test_save_writes_every_value_to_prefs_and_the_file(window, dialogs, isolated_prefs,
                                                       tmp_path):
    from paperknife.prefs import PREFS
    page = _page(window)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    dialogs.dirs.append(str(out_dir))
    page.pick_output_dir()
    page.max_recent.setValue(7)
    page.appearance.setCurrentText("dark")
    page.ocr_dpi.setValue(300)
    page.export_dpi.setValue(240)
    page.compress_level.setCurrentText("aggressive")
    page.ocr_lang.setText("ita")
    page.save()
    want = {"output_dir": str(out_dir), "max_recent": 7, "appearance": "dark",
            "ocr_dpi": 300, "export_dpi": 240, "compress_level": "aggressive",
            "ocr_lang": "ita"}
    for key, val in want.items():
        assert PREFS.get(key) == val, key
    stored = json.loads(isolated_prefs.read_text(encoding="utf-8"))
    assert {k: stored[k] for k in want} == want
    assert dialogs.msgs[-1] == ("info", "Saved", "Preferences saved.")
    assert window.status_text() == "✓  Preferences saved"
    assert window.status_role == "success"


@pytest.mark.parametrize("mode,dark", [("dark", True), ("light", False)])
def test_the_colour_mode_is_applied_on_save(window, dialogs, mode, dark):
    from qfluentwidgets import isDarkTheme
    page = _page(window)
    page.appearance.setCurrentText(mode)
    page.save()
    assert isDarkTheme() is dark


def test_the_saved_preferences_reach_the_tools(window, dialogs):
    page = _page(window)
    page.compress_level.setCurrentText("light")
    page.save()
    window.open_tool("CompressTool")
    pump(0.05)
    assert window.current_page().level == "light"


def test_numbers_are_held_to_their_ranges(window, dialogs):
    from paperknife.prefs import DPI_RANGE, PREFS
    from paperknife.recent import RECENT_STORE_MAX
    page = _page(window)
    old = PREFS.max_recent
    page.max_recent.setValue(0)
    assert page.max_recent.value() == 1
    page.max_recent.setValue(RECENT_STORE_MAX + 1)
    assert page.max_recent.value() == RECENT_STORE_MAX
    for spin in (page.ocr_dpi, page.export_dpi):
        spin.setValue(1)
        assert spin.value() == DPI_RANGE[0]
        spin.setValue(10_000)
        assert spin.value() == DPI_RANGE[1]
    # The page's own check refuses an out-of-range number as the CTk tool did.
    page.values = lambda: {"max_recent": 0, "ocr_dpi": 150}
    page.save()
    assert dialogs.msgs[-1] == ("warning", "Not saved",
                                f"Max recent files shown must be a whole number from 1 to "
                                f"{RECENT_STORE_MAX}.")
    assert PREFS.max_recent == old


def test_a_write_failure_is_reported_and_nothing_claims_success(window, dialogs, monkeypatch,
                                                               tmp_path):
    from paperknife import prefs
    blocker = tmp_path / "blocked.json"
    blocker.mkdir()
    monkeypatch.setattr(prefs, "PREFS_PATH", blocker)
    page = _page(window)
    page.save()
    kinds = [m[0] for m in dialogs.msgs]
    assert "error" in kinds and "info" not in kinds, dialogs.msgs
    title, text = dialogs.errors()[-1][1:]
    assert title == "Not saved" and text.startswith("Could not write the preferences file:\n")
    assert "✓" not in window.status_text()


def test_restore_defaults_asks_then_resets_and_refills(window, dialogs, isolated_prefs):
    from paperknife.prefs import _DEFAULTS, PREFS
    PREFS.ocr_lang = "deu"
    PREFS.window_geometry = "800x600+0+0"
    page = _page(window)
    assert page.ocr_lang.text() == "deu"
    dialogs.asks.append(True)
    page.restore()
    assert dialogs.msgs[0] == ("ask_yes_no", "Restore", "Reset all preferences to defaults?")
    assert PREFS.ocr_lang == _DEFAULTS["ocr_lang"] and page.ocr_lang.text() == "eng"
    assert PREFS.window_geometry == "800x600+0+0"
    assert window.status_text() == "✓  Preferences restored to defaults"
    assert not [m for m in dialogs.msgs if m[0] == "info"]
    # restored, the language is "not chosen yet" again (the picker shows the default)
    assert json.loads(isolated_prefs.read_text(encoding="utf-8"))["ocr_lang"] == ""


def test_declining_restore_changes_nothing(window, dialogs, isolated_prefs):
    from paperknife.prefs import PREFS
    PREFS.ocr_lang = "deu"
    page = _page(window)
    dialogs.asks.append(False)
    page.restore()
    assert PREFS.ocr_lang == "deu" and page.ocr_lang.text() == "deu"
    assert not isolated_prefs.exists()


def test_no_file_is_taken_by_a_drop(window, tmp_path):
    page = _page(window)
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(make_pdf(tmp_path / "in.pdf")) is False
    assert page.accept_drop(str(other)) is False


def test_leaving_the_tool_drops_unsaved_changes(window, isolated_prefs):
    from paperknife.prefs import PREFS
    page = _page(window)
    page.ocr_lang.setText("fra")
    assert window.open_tool("CompressTool")
    assert _page(window) is page
    assert page.ocr_lang.text() == (PREFS.ocr_lang or "eng") != "fra"
    assert not isolated_prefs.exists()
