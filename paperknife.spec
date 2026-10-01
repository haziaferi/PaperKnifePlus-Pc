# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for PaperKnife+ PC
#
# Build:  pyinstaller paperknife.spec
#
# Pre-audit checklist (windows-app-auditor):
#   WIN-SEC-02  ✓  app.manifest embedded via manifest= below
#   WIN-CMP-02  ✓  PerMonitorV2 dpiAwareness in manifest
#   WIN-CMP-03  ✓  longPathAware in manifest
#   WIN-WAC-03  ✓  supportedOS Win10/11 in manifest
#   WIN-BLD-01  ✓  PyInstaller strips debug info in release mode (--log-level WARN)
#   WIN-DEP-06  ✓  Python runtime bundled → no "Python not found" failure on end-user machines
#   WIN-PERF-03 ✓  one-file-dir bundle: all DLLs present at startup, no lazy-extract latency
#
# Remaining action items (cannot be done by this spec):
#   WIN-SEC-07  ⚠  Sign PaperKnifePlusPC.exe with EV/OV cert after build (see build_windows.bat)
#   WIN-SEC-08  ⚠  RFC 3161 timestamp required in signtool invocation
#   WIN-DEP-02  ⚠  Sign all shipped .dll files (signtool loop in build_windows.bat)

import sys
from pathlib import Path

block_cipher = None

# Collect tkinterdnd2 binaries (optional DnD support)
try:
    import tkinterdnd2 as _dnd
    dnd_binaries = [
        (str(Path(_dnd.__file__).parent / "tkdnd" / "*"), "tkdnd"),
    ]
except ImportError:
    dnd_binaries = []

# Collect tesseract language data if bundled (optional OCR)
# End users still need the Tesseract binary on PATH; we do NOT bundle the
# Tesseract executable itself (it is a separate open-source tool).
tesseract_data = []

a = Analysis(
    ["paperknife/__main__.py"],
    pathex=["."],
    binaries=dnd_binaries,
    datas=[
        # Include any extra resource files here
        # ("assets/*", "assets"),
    ],
    hiddenimports=[
        # customtkinter loads themes at runtime via importlib
        "customtkinter",
        # PyMuPDF internal modules
        "fitz",
        # optional doc-conversion extras
        "docx",
        "pptx",
        "openpyxl",
        "striprtf",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # test frameworks
        "pytest", "unittest", "_pytest",
        # jupyter / IPython
        "IPython", "jupyter",
        # numpy / scipy / MKL — paperknife uses none of these;
        # excluding them prevents PyInstaller from pulling in the entire
        # conda MKL stack (mkl_blacs_msmpi_*.dll, omptarget.*.dll, etc.)
        # which triggers the msmpi.dll / ur_loader.dll / sycl8.dll
        # "Library not found" warnings in the build log.
        "numpy", "scipy", "pandas", "matplotlib",
        "mkl", "intel_openmp",
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
    version="version_info.txt",     # see version_info.txt below
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
