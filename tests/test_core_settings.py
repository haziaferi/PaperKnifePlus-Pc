"""paperknife.core.settings without any user interface."""
import pytest

from paperknife.core import settings as core


@pytest.fixture
def prefs(tmp_path, monkeypatch):
    from paperknife import prefs as prefs_mod
    monkeypatch.setattr(prefs_mod, "PREFS_PATH", tmp_path / "prefs.json")
    return prefs_mod.Prefs()


def test_check_values_turns_the_numbers_into_ints():
    values = {"max_recent": " 7 ", "default_dpi": "300", "ocr_lang": "ita"}
    assert core.check_values(values) is None
    assert values == {"max_recent": 7, "default_dpi": 300, "ocr_lang": "ita"}


@pytest.mark.parametrize("key,val,name,lo,hi", [
    ("max_recent", "0", "Max recent files shown", 1, 50),
    ("max_recent", "51", "Max recent files shown", 1, 50),
    ("max_recent", "many", "Max recent files shown", 1, 50),
    ("default_dpi", "71", "Default DPI", 72, 600),
    ("default_dpi", "1.5", "Default DPI", 72, 600),
    ("default_dpi", True, "Default DPI", 72, 600),
])
def test_check_values_names_the_first_bad_number(key, val, name, lo, hi):
    values = {"max_recent": 12, "default_dpi": 150, key: val}
    assert core.check_values(values) == f"{name} must be a whole number from {lo} to {hi}."


def test_apply_values_sets_every_key(prefs):
    core.apply_values(prefs, {"ocr_lang": "deu", "default_dpi": 200})
    assert prefs.ocr_lang == "deu" and prefs.default_dpi == 200


def test_restore_defaults_keeps_the_tk_window_geometry(prefs):
    from paperknife.prefs import _DEFAULTS
    prefs.ocr_lang = "deu"
    prefs.appearance = "dark"
    prefs.window_geometry = "800x600+0+0"
    core.restore_defaults(prefs)
    assert prefs.ocr_lang == _DEFAULTS["ocr_lang"]
    assert prefs.appearance == _DEFAULTS["appearance"]
    assert prefs.window_geometry == "800x600+0+0"
