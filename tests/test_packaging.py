"""Packaging: window icon, build script, and the version copies that must agree."""
import re
from pathlib import Path

from conftest import SRC, pump

ROOT = Path(__file__).resolve().parents[1]


def test_window_uses_the_app_icon_not_customtkinters(app):
    # CTk puts its own logo on the window 200 ms after start, through the same
    # iconbitmap(), unless the app set one first; conftest records the calls.
    pump(app, 0.4)
    given = app._harness_icons
    assert given, "no icon was set"
    assert Path(given[-1]) == (Path(SRC) / "assets" / "icon.ico").resolve(), given


def test_spec_bundles_the_icon_where_the_app_looks_for_it():
    spec = (SRC / "paperknife.spec").read_text(encoding="utf-8")
    assert re.search(r"""\(\s*["']assets/icon\.ico["']\s*,\s*["']assets["']\s*\)""", spec), \
        "the frozen app reads assets/icon.ico from the bundle root"


def test_build_script_runs_from_its_own_folder():
    # Its clean step deletes build\ in the current folder.
    bat = (SRC / "build_windows.bat").read_text(encoding="utf-8")
    first_cd = bat.find('cd /d "%~dp0"')
    assert 0 <= first_cd < bat.find("rmdir"), "cd must come before the clean step"


def test_every_copy_of_the_version_agrees():
    src = Path(SRC)
    version = re.search(r'__version__\s*=\s*"([^"]+)"',
                        (src / "paperknife" / "_version.py").read_text(encoding="utf-8"))[1]
    dotted4 = version + ".0"
    tuple4 = "(" + ", ".join(dotted4.split(".")) + ")"
    copies = {                      # setup.py reads _version.py itself
        "installer.nsi": f'!define APP_VERSION     "{version}"',
        "build_windows.bat": f"set APP_VERSION={version}",
        "setup.bat": f"v{version} ",
        "README.md": f"v{version}\n",
        "version_info.txt": f"u'FileVersion',     u'{dotted4}'",
    }
    for name, needle in copies.items():
        assert needle in (src / name).read_text(encoding="utf-8"), (name, needle)
    vi = (src / "version_info.txt").read_text(encoding="utf-8")
    assert vi.count(tuple4) == 2, ("version_info.txt filevers/prodvers", tuple4)
    assert f"u'ProductVersion', u'{version}'" in vi


def test_the_build_ships_the_qt_app_without_tk():
    src = Path(SRC)
    spec = (src / "paperknife.spec").read_text(encoding="utf-8")
    assert re.search(r"""Analysis\(\s*\[\s*["']launcher\.py["']\s*\]""", spec)
    assert "from paperknife.qt.__main__ import main" in (src / "launcher.py").read_text(
        encoding="utf-8")
    for name in ("tkinter", "_tkinter", "customtkinter", "tkinterdnd2"):
        assert f'"{name}"' in spec, f"{name} must be excluded from the bundle"
    assert '"PySide6"' not in spec.split("excludes=")[1].split("]")[0]


def test_batch_files_are_crlf_and_ascii():
    # cmd misreads an LF-only batch file (labels, blocks), and under code page
    # 65001 it splits lines at non-ASCII characters; either breaks the build.
    for name in ("build_windows.bat", "setup.bat", "run.bat"):
        b = (Path(SRC) / name).read_bytes()
        assert b.count(b"\n") == b.count(b"\r\n"), f"{name}: not CRLF throughout"
        assert all(c < 128 for c in b), f"{name}: non-ASCII bytes"


def test_requirements_name_the_qt_pins_and_no_tk_packages():
    src = Path(SRC)
    req = (src / "requirements.txt").read_text(encoding="utf-8").lower()
    fluent = (src / "requirements-fluent.txt").read_text(encoding="utf-8").lower()
    setup = (src / "setup.py").read_text(encoding="utf-8").lower()
    for text in (req, fluent, setup):
        assert "customtkinter" not in text and "tkinterdnd2" not in text
    assert "pyside6-essentials==6.12.0" in req and "pyside6-essentials==6.12.0" in setup
    # fluent_route.py patches this exact version's internals
    assert "pyside6-fluent-widgets==1.11.3" in fluent and "pyside6-fluent-widgets==1.11.3" in setup
    for bat in ("setup.bat", "build_windows.bat"):
        assert "--no-deps -r requirements-fluent.txt" in (src / bat).read_text(encoding="utf-8")
    assert "-m paperknife.qt" in (src / "run.bat").read_text(encoding="utf-8")
