# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for PaperKnife+ PC (the Qt interface: PySide6 + QFluentWidgets)
#
# Build:  pyinstaller paperknife.spec   (from an activated clean venv; see
#         build_windows.bat — a global or conda environment drags in every
#         package PyInstaller's hooks can reach)
#
# Pre-audit checklist (windows-app-auditor):
#   WIN-SEC-02  ✓  app.manifest embedded via manifest= below
#   WIN-CMP-02  ✓  PerMonitorV2 dpiAwareness in manifest
#   WIN-CMP-03  ✓  longPathAware in manifest
#   WIN-WAC-03  ✓  supportedOS Win10/11 in manifest
#   WIN-BLD-01  ✓  debug=False: no debug bootloader (symbols are not stripped: strip=False)
#   WIN-DEP-06  ✓  Python runtime bundled → no "Python not found" failure on end-user machines
#   WIN-PERF-03 ✓  one-dir bundle: all DLLs present at startup, no lazy-extract latency
#
# Remaining action items (cannot be done by this spec):
#   WIN-SEC-07  ⚠  Sign PaperKnifePlusPC.exe with EV/OV cert after build (see build_windows.bat)
#   WIN-SEC-08  ⚠  RFC 3161 timestamp required in signtool invocation
#   WIN-DEP-02  ⚠  Sign all shipped .dll/.pyd files (signtool loop in build_windows.bat)
#
# Licences: the Qt / PySide6 / Shiboken6 DLLs ship as separate files (LGPL-3.0:
# they can be replaced), and every bundled package's licence lands in
# licenses/ beside the exe, with LICENSE and THIRD-PARTY-NOTICES.md (see the end).

import shutil
from importlib.metadata import distribution
from pathlib import Path

block_cipher = None

# Every distribution the bundle carries, for its licence files.
DISTS = ["pymupdf", "pyside6_essentials", "shiboken6", "PySide6-Fluent-Widgets",
         "PySideSix-Frameless-Window", "darkdetect", "pywin32", "pillow", "pytesseract",
         "python-docx", "python-pptx", "openpyxl", "et_xmlfile", "lxml", "XlsxWriter",
         "typing_extensions", "striprtf"]

# Qt modules the app does not use.  PySide6-Essentials ships Qml / Quick and
# more; the PySide6 hook collects only what is imported, and these keep a
# stray import from pulling them in.
QT_UNUSED = ["PySide6.Qt3DCore", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
             "PySide6.QtQuickControls2", "PySide6.QtDesigner", "PySide6.QtHelp",
             "PySide6.QtUiTools", "PySide6.QtSql", "PySide6.QtTest",
             # added by the hook, imported by nothing (with its tls and
             # networkinformation plugins, 3.5 MB)
             "PySide6.QtNetwork"]

# Files the PySide6 hook adds that the app never loads: the software OpenGL
# fallback (20 MB; pages are drawn by the raster engine, no OpenGL) and Qt's
# own translations (7 MB; the interface is English and file dialogs are
# Windows' own, in the Windows language).
def _unused_qt_file(dest: str) -> bool:
    d = dest.replace("\\", "/").lower()
    return d.endswith("/opengl32sw.dll") or d.startswith("pyside6/translations/")

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=[],
    datas=[("assets/icon.ico", "assets")],
    hiddenimports=[
        "pymupdf",
        # optional doc-conversion extras, imported inside functions
        "docx",
        "pptx",
        "openpyxl",
        "striprtf",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # the CustomTkinter interface's toolkit (the Qt start never imports it)
        "tkinter", "_tkinter", "customtkinter", "tkinterdnd2",
        # QFluentWidgets / frameless-window parts that need Qt Multimedia / WebEngine
        "qfluentwidgets.multimedia", "qframelesswindow.webengine",
        # test frameworks and dev tools
        "pytest", "unittest", "_pytest", "pygments",
        # jupyter / IPython
        "IPython", "jupyter",
        # numpy / scipy / MKL — paperknife uses none of these;
        # excluding them prevents PyInstaller from pulling in the entire
        # conda MKL stack (mkl_blacs_msmpi_*.dll, omptarget.*.dll, etc.)
        # which triggers the msmpi.dll / ur_loader.dll / sycl8.dll
        # "Library not found" warnings in the build log.
        "numpy", "scipy", "pandas", "matplotlib",
        "mkl", "intel_openmp",
        # other Qt bindings that hooks may pull in from a shared environment
        "PyQt5", "PyQt6", "PySide2",
    ] + QT_UNUSED,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

a.binaries = [t for t in a.binaries if not _unused_qt_file(t[0])]
a.datas = [t for t in a.datas if not _unused_qt_file(t[0])]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # one-dir layout (faster startup than one-file)
    name="PaperKnifePlusPC",
    debug=False,                    # WIN-BLD-01: no debug build shipped
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX-packed Qt DLLs fail to load or start slowly
    console=False,                  # GUI application — no console window
    icon=str(Path("assets") / "icon.ico"),
    # WIN-SEC-02 / WIN-CMP-02 / WIN-CMP-03: embed the app.manifest
    manifest="app.manifest",
    version="version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="PaperKnifePlusPC",
)

# ── Licences, beside the exe ──────────────────────────────────────────────────
out = Path(DISTPATH) / "PaperKnifePlusPC"
lic = out / "licenses"
shutil.rmtree(lic, ignore_errors=True)
for name in DISTS:
    dist = distribution(name)
    files = [f for f in dist.files or ()
             if any(p.endswith(".dist-info") for p in f.parts)
             and any(k in f.name.upper() for k in ("LICEN", "COPYING", "NOTICE"))]
    if not files:
        raise SystemExit(f"no licence file in the {name} distribution")
    for f in files:
        info = next(i for i, p in enumerate(f.parts) if p.endswith(".dist-info"))
        dst = lic / f"{dist.metadata['Name']}-{dist.version}" / Path(*f.parts[info + 1:])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f.locate(), dst)
# Qt, PySide6 and Shiboken6 are used under the LGPL-3.0, but their wheels carry
# only the commercial licence text: the LGPL and the GPL it builds on come from
# the frameless-window (LGPL-3.0) and Fluent Widgets (GPL-3.0) wheels.
qt = lic / "Qt-6.12.0"
qt.mkdir(parents=True, exist_ok=True)
for name, text in (("PySideSix-Frameless-Window", "LGPL-3.0.txt"),
                   ("PySide6-Fluent-Widgets", "GPL-3.0.txt")):
    src = next(f for f in distribution(name).files if f.name == "LICENSE")
    shutil.copyfile(src.locate(), qt / text)
# The Python runtime (PSF) and PyInstaller's bootloader inside the exe (GPL with
# the bootloader exception).
import sys
py = lic / f"Python-{sys.version.split()[0]}"
py.mkdir(parents=True, exist_ok=True)
shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", py / "LICENSE.txt")
pyi = distribution("pyinstaller")
boot = lic / f"PyInstaller-{pyi.version}"
boot.mkdir(parents=True, exist_ok=True)
shutil.copyfile(next(f for f in pyi.files if f.name == "COPYING.txt").locate(),
                boot / "COPYING.txt")
for f in ("LICENSE", "THIRD-PARTY-NOTICES.md"):
    shutil.copyfile(f, out / f)
