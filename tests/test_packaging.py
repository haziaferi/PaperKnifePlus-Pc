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
