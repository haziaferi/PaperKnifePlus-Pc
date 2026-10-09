# Packaging pass, 4.0.0 (Qt) — 2026-10-10

The first build of the Qt interface (PySide6 6.12.0 + PySide6-Fluent-Widgets 1.11.3):
spec, requirements, installer and docs moved off CustomTkinter, a real build, the
frozen app's self-check, and the installer run over 3.2.2. Logs are in
`../_qt-2026-10-09/` beside the repo (`build.log`, `selftest-frozen.txt`,
`phase7/install_check.log`).

## Results

| Check | How it was run | Result |
|---|---|---|
| Clean build venv | new `buildvenv`: `requirements.txt` + `pyinstaller==6.22.3`, then `requirements-fluent.txt` with `--no-deps` | 376 MB venv; no customtkinter, tkinterdnd2, PySide6-Addons or WebEngine. The Qt app starts from it (launch 124, empty log) |
| PyInstaller build | `build_windows.bat`, PyInstaller 6.22.3, NSIS 3.12 | **pass**, exit 0. First try failed: the batch file had lost its CRLF line ends (an editing step) and holds UTF-8 box characters, which cmd misreads under code page 65001. Fixed: CRLF and ASCII only, guarded by `test_batch_files_are_crlf_and_ascii` |
| Bundle size | `dist\PaperKnifePlusPC` | 172 MB as first built; 137 MB after dropping `opengl32sw.dll` (20 MB, software OpenGL: pages are drawn by the raster engine), Qt's translations (7 MB) and QtNetwork with its plugins (3.5 MB, imported by nothing). Installer 65.9 MB (3.2.2: 47.9 MB) |
| No Tk in the bundle | file search in the bundle | no Tcl/Tk, customtkinter or tkinterdnd2 (one Pillow module, `_imagingtk.pyd`, is in Pillow's wheel and unused) |
| Frozen self-check | `PaperKnifePlusPC.exe --selftest report.txt` (`paperknife/qt/selftest.py`): every tool page built and shown, every optional library imported, a PDF saved and read back, Qt image formats, platform plugin | **pass** 34/34 |
| Licences | `licenses\` beside the exe | one folder per bundled distribution with its licence files, plus `Qt-6.12.0\LGPL-3.0.txt` and `GPL-3.0.txt`, `Python-3.14.6`, `PyInstaller-6.22.3` (bootloader); `LICENSE` and `THIRD-PARTY-NOTICES.md` at the root. Qt DLLs are separate files (LGPL: replaceable) |
| Install, upgrade, uninstall | `phase7/install_check.ps1`: 3.2.2 `/S`, then 4.0.0 `/S` over it, the installed exe's `--selftest`, `Uninstall.exe /S` | **pass** 23/23: same folder, version 4.0.0 in Add/Remove Programs and on the exe, no 3.2.2 toolkit files left, licences shipped, shortcuts made; the installed app passed its self-check (34/34); the uninstall removed the folder, both registry keys and both shortcuts; the owner's `prefs.json` was not touched. Run from the Claude app, so the files landed in its sandbox (see the 2026-10-02 note) |
| Gate | Qt suite, core + CTk suite, ruff, compileall, launch | Qt 597, core + CTk 452, ruff clean, launch 124 with an empty log |
| Real install, drag and drop, taskbar icon | owner, by hand from Explorer | **open**: checklist given to the owner |
| Code signing | — | not done: no certificate (as for 3.2.2) |
