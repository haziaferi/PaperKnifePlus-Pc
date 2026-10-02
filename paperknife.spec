# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for PaperKnife+ PC
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

import tkinter
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# customtkinter reads its theme JSON and fonts from customtkinter/assets as
# data files; hiddenimports alone does not ship them.
ctk_datas = collect_data_files("customtkinter")

# tkinterdnd2 (optional DnD).  TkinterDnD._require looks for the library in
# <dir of tkinterdnd2>/tkdnd/<platform>[-tcl9], so it must land under
# tkinterdnd2/tkdnd/ in the bundle.  Only the x64 Windows build is shipped.
try:
    import tkinterdnd2 as _dnd
except ImportError:
    dnd_datas = []
else:
    _plat = "win-x64"
    if int(tkinter.Tcl().eval("info tclversion").split(".")[0]) >= 9:
        _plat += "-tcl9"
    _src = Path(_dnd.__file__).parent / "tkdnd" / _plat
    if not _src.is_dir():
        raise SystemExit(f"tkinterdnd2 has no {_src}; upgrade tkinterdnd2 "
                         "or uninstall it to build without drag and drop")
    dnd_datas = [(str(_src), f"tkinterdnd2/tkdnd/{_plat}")]

a = Analysis(
    ["paperknife/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=ctk_datas + dnd_datas + [("assets/icon.ico", "assets")],
    hiddenimports=[
        "customtkinter",
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
        # other GUI toolkits that hooks may pull in from a shared environment
        "PyQt5", "PyQt6", "PySide2", "PySide6",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

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
    upx=True,                       # compress with UPX if available
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
    upx=True,
    upx_exclude=[],
    name="PaperKnifePlusPC",
)
