# Verifying pass — 2026-10-02

The fresh-eyes audit (`fresh-eyes-2026-10-01.md`, ending at `6e62fec`) left four things
it had not run: a real build and installer, real drag and drop from Explorer, a real
Tesseract, and the PyMuPDF 1.27.2 floor. This pass ran them, plus a packaging-only audit
(windows-auditor, Opus) whose findings were acted on only where reproduced. Defects found
are rows `V-*` in the register; logs are in `../_verify-2026-10-02/` beside the repo.

## Results

| Check | How it was run | Result |
|---|---|---|
| PyMuPDF floor | separate venv, `PyMuPDF==1.27.2`, whole suite at `6e62fec` | **pass**: 176/176 (`floor-suite.log`) |
| customtkinter floor | same venv, `customtkinter==5.2.0` (the stated floor) | **fail**: 5.2.0 imports `distutils`, gone in Python 3.12 (`ctk5-install.log`). 5.2.1: 176/176 (`ctk521-suite.log`). Floor raised to 5.2.1 (V-02) |
| Floors at HEAD | PyMuPDF 1.27.2 + customtkinter 5.2.1, fixed tree | **pass**: 183/183, real Tesseract test included (`floors-fixed.log`) |
| Tesseract | real Tesseract 5.5.0 in `C:\Program Files\Tesseract-OCR`, not on PATH (as its installer leaves it) | **fail** at `6e62fec`: OCR said "not found" and Batch OCR failed every file (V-01). Fixed: the real binary now OCRs an image-only page and the words are searchable (`test_ocr_with_real_tesseract_…`) |
| Tesseract text layer | `eng+ita` on known English and Italian words | the layer holds exactly what Tesseract returns, accents included; with `eng+ita` Tesseract itself reads *città* as *citta* (`ita` alone reads it right): a recognition limit, not an app defect |
| PyInstaller build | `build_windows.bat`, PyInstaller 6.22.3, NSIS 3.12 | **pass**: exit 0 from a frozen `6e62fec` worktree and from HEAD; bundle 97 MB, installer 45.7 MB. Nothing the app imports is missing (`warn-paperknife.txt` lists only optional modules); tkdnd `win-x64` and customtkinter assets are bundled |
| Frozen app starts | process launched, window title read, DPI context read | **pass**: "PaperKnife+ PC  v3.2.2", responding; `PER_MONITOR_AWARE_V2` (so the manifest's padded values work: auditor F16 withdrawn) |
| Window icon | which file the window's `iconbitmap` was given | **fail** at `6e62fec`: CustomTkinter's logo (V-03). Fixed |
| Build script from another folder | decoy folder with `build\KEEP-ME.txt`, script run by full path | **fail** at `6e62fec`: the decoy `build\` was deleted (V-04). Fixed: run from `_verify-2026-10-02\`, the build found its spec and succeeded |
| Silent install | `Setup.exe /S`, per-user | **pass**: 1,079 files, both HKCU keys, Start-menu and desktop shortcuts |
| Install over a running copy | `Setup.exe /S` with the app open | at `6e62fec`: exit 0 and no message. Now: exit 2, nothing changed (V-06) |
| Upgrade | install `/D=<custom>`, then `/S` with no folder | at `6e62fec`: second copy in the default folder, the first orphaned. Now: stays in the custom folder (V-07) |
| Stale files | file planted in `_internal`, then upgrade | removed now (V-08) |
| Uninstall while running | `Uninstall.exe /S` with the app open | exit 2, nothing changed (the `6e62fec` uninstaller was not tried this way) |
| Uninstall | `Uninstall.exe /S` | **pass**: folder, both keys, Start menu and desktop shortcut gone; the empty `HKCU\Software\potatameister` was left behind and now is not (V-09). `%USERPROFILE%\.paperknifepluspc` is kept on purpose |
| 64-bit check | — | added (V-10); **not run**: no 32-bit Windows here |
| Upgrade of an old shared-folder install | folder with user files + an old copy and its uninstaller, registered as the install folder | old app files and old uninstaller removed, user files untouched; the uninstall then removed only the app's subfolder (V-16, owner's rule: the app's own files may be deleted, nothing else) |
| Drag and drop, taskbar icon, OCR from the installed app | owner, by hand: checklist below | **open**: screen control was declined, and installs started from this session are not real-world installs (note below) |

At HEAD: 183 tests pass (also on the floor versions), ruff clean, compileall clean,
source launch exits 124 (still running at 12 s) with an empty log. An independent Opus
review of this pass's diff found the V-16 and V-17 defects (fixed) and two stale details.

**Test environment note.** The Claude desktop app is an MSIX package: installs run from it
land in its container (`…\Packages\Claude_…\LocalCache\Local\PaperKnifePlusPC`) while the
Start-menu and desktop shortcuts land in the real profile. Every install made here was
uninstalled again, which removed both; install logic (locking, folders, registry) behaves the
same, but a real-world install has to be started from Explorer. That is the first step below.

## Owner checklist (drag and drop and the installed app)

Installer: `PaperKnifePlusPC-3.2.2-Setup.exe` in the repo root. Test files:
`..\_verify-2026-10-02\dnd prova è\` (the folder name has a space and an *è*).

1. Double-click the installer in Explorer, install with the defaults, start the app from
   the desktop shortcut.
2. **Icon:** the title bar and the taskbar button show the PaperKnife icon, not the blue
   CustomTkinter logo.
3. **Split** (any file-row tool): the row says "Drop a file here or click to browse…".
   Drag `uno.pdf` onto it → the path appears. Drag `note.txt` → nothing changes.
4. **Merge:** select `uno.pdf`, `due spazi.pdf` and `città.pdf` together and drag them onto
   the list → three rows, names intact.
5. **Image → PDF:** drag `immagine.png` and `uno.pdf` together → only the image is added.
6. **Doc / Text → PDF:** drag `note.txt` → the file appears and the format switches to TXT.
7. **OCR:** open `..\_verify-2026-10-02\tess\image_only.pdf`, language `eng`, Run OCR →
   it finishes; in the output, Ctrl+F finds "quarterly".
8. Close the app, uninstall from Settings → Apps → PaperKnife+ PC.

## Owner decisions raised by this pass

- **V-18 Signing.** The PFX password reaches every signtool command line; `Uninstall.exe`
  is never signed; already-signed Microsoft/PSF DLLs get re-signed. Fix all three
  (store-thumbprint signing, `!uninstfinalize`, skip signed files) before the first signed
  release?
- **V-19 Reproducible builds.** Add a `requirements-lock.txt` that the build installs
  (PyInstaller pinned too)? Pillow's 10.0.0 floor cannot be tested on Python 3.14.
- **V-20 Desktop shortcut.** Always, as now, or an option on the finish page?
- **V-21 Install folder.** Keep `%LOCALAPPDATA%\PaperKnifePlusPC` or move new installs to
  `%LOCALAPPDATA%\Programs\PaperKnifePlusPC`?
- **V-22 Installer compression.** LZMA: 33.4 MB instead of 45.7 MB, install 8 s instead of 5 s.

Deferred: V-23 (tkdnd spec block, x64-only build), V-24 (dead spec arguments), V-25 (a Tk
variable collected on a worker thread; belongs with L3-50). UPX is L4-45, already yours.
