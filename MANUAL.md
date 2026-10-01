# ✂ PaperKnife+ PC
## Installation & User Manual

**Version 3.2.2** · 100% local · no cloud · no tracking · Windows 10 / 11 · x64

*github/potatameister*

---

## 1. Overview

PaperKnife+ PC is a fully offline PDF toolkit for Windows 10 and 11. Every operation runs on your machine — no file is ever uploaded to a server, no account is required, and no telemetry is collected.

| Property | Value |
|---|---|
| Version | 3.2.2 |
| Platform | Windows 10 / 11 (x64) |
| Python runtime | Bundled — no install needed |
| Network access | None — 100% offline |
| Install location | Per-user, no admin required |
| Uninstall | Settings → Apps → PaperKnife+ PC |
| Data stored | `%USERPROFILE%\.paperknifepluspc\` |

---

## 2. System Requirements

| Requirement | Detail |
|---|---|
| Operating system | Windows 10 (build 19041+) or Windows 11 |
| Architecture | 64-bit (x64) |
| RAM | 4 GB minimum, 8 GB recommended for large PDFs |
| Disk space | ~350 MB installed (bundled Python runtime) |
| Display | 1024 × 768 minimum, HiDPI supported (Per-Monitor v2) |
| Tesseract | Optional — required for OCR tool only |

> ⚠️ **OCR prerequisite:** The OCR tool requires the Tesseract binary separately. See Section 4.3.

---

## 3. Installation

### 3.1 Standard Installer (recommended)

The NSIS installer packages the full Python runtime alongside the application. No existing Python installation is needed on the target machine, but you must build the installer once from the source package before distributing or installing it.

1. Unzip the source package and follow the build steps in **Section 9** to produce `PaperKnifePlusPC-3.2.2-Setup.exe`. The installer appears in the project root only if both **PyInstaller** and **NSIS** are installed. If NSIS is absent, the build stops at Step 4 and produces only a folder bundle (`dist\PaperKnifePlusPC\`) — no Setup `.exe`.
2. Double-click the installer. No UAC elevation prompt appears — the app installs per-user into `%LOCALAPPDATA%\PaperKnifePlusPC`.
3. A desktop shortcut and Start Menu entry are created automatically.
4. Launch via the desktop shortcut, the Start Menu, or run `%LOCALAPPDATA%\PaperKnifePlusPC\PaperKnifePlusPC.exe` directly.

> ℹ️ **Note:** If you only need to run the app on your own machine without building an installer, use the **Section 3.3** source method instead — it requires no build step.

### 3.2 Silent Installation (enterprise / scripted)

The installer supports fully silent mode with no UI and no prompts, suitable for SCCM, Intune, or GPO software deployment:

```
PaperKnifePlusPC-3.2.2-Setup.exe /S
```

Silent uninstall:

```
%LOCALAPPDATA%\PaperKnifePlusPC\Uninstall.exe /S
```

> ℹ️ **Note:** Both commands are synchronous — the process exits when the operation is complete. Exit code 0 indicates success.

### 3.3 Running from Source (developers)

If you are working with the source distribution rather than the compiled installer:

1. Ensure Python 3.10 or later is on your PATH. A clean `venv` is recommended; conda environments are known to cause issues (see Section 9.1).
2. Run the provided setup script, which installs all core and optional dependencies automatically:
   ```
   setup.bat
   ```
   Or install manually:
   ```
   pip install -r requirements.txt
   ```
3. Launch:
   ```
   python -m paperknife
   ```
   Or double-click `run.bat` in the project root.

> ℹ️ **Note:** `requirements.txt` marks `tkinterdnd2`, `pytesseract`, and the document-conversion libraries (`python-docx`, `python-pptx`, `openpyxl`, `striprtf`) as optional. `setup.bat` installs all of them. If you install manually and omit them, drag-and-drop and OCR will not function.

---

## 4. First Launch

### 4.1 Home Screen

On first launch the home screen shows six quick-action buttons and an empty Recent Files grid. The sidebar on the left groups all tools into labelled sections. Click any section header to collapse or expand it. Use `Ctrl+K` or `Ctrl+F` to search tools by name.

### 4.2 Appearance Mode

PaperKnife+ PC supports light, dark, and system-matched appearance modes. To change:

1. Click ⚙️ **Preferences** in the sidebar.
2. Under **Appearance**, choose Light, Dark, or System.
3. Click **Save Preferences**. The mode takes effect immediately and is restored on next launch.

### 4.3 OCR Setup (optional)

The OCR tool requires the Tesseract OCR engine to be installed separately and available on the system PATH. PaperKnife+ PC does not bundle Tesseract because of its size and because it is an independent open-source project.

1. Download the Windows installer from:
   ```
   https://github.com/UB-Mannheim/tesseract/wiki
   ```
2. Run the installer. When prompted, note the installation path (default: `C:\Program Files\Tesseract-OCR`).
3. Add the Tesseract directory to your user PATH:
   - Open **Settings → System → About → Advanced system settings**.
   - Click **Environment Variables** → select **Path** under User variables → **Edit**.
   - Click **New** and paste the Tesseract installation path.
   - Click **OK** on all dialogs, then restart PaperKnife+ PC.
4. In Preferences, set the OCR language code (e.g., `eng` for English, `ita` for Italian, `deu` for German). Multiple codes can be combined: `eng+ita`.

---

## 5. Tools Reference

| Tool | Description | Section |
|---|---|---|
| 📎 Merge | Combine multiple PDFs into one, with custom page ranges | 5.1 |
| ✂ Split | Extract pages or split a PDF into individual files | 5.2 |
| 🔒 Password | Add, remove, or change PDF passwords and permissions | 5.3 |
| 🗜 Compress | Reduce file size with three quality presets | 5.4 |
| 📝 Annotate | Add text annotations, highlights, and stamps | 5.5 |
| 🤖 OCR | Make scanned PDFs text-searchable using Tesseract | 5.6 |
| 🔁 Rotate | Rotate pages individually or in bulk | 5.7 |
| ✂ Crop | Trim page margins or define a custom crop box | 5.8 |
| 🔁 Convert | PDF to images (PNG/JPEG) and images to PDF | 5.9 |
| 📋 Metadata | View and edit document title, author, keywords | 5.10 |
| 📑 Bookmarks | View, add, and reorder the PDF bookmark tree | 5.11 |
| 🔍 Find & Replace | Search and replace text across all pages | 5.12 |
| ✏ Edit Text | In-place text editing on individual pages | 5.13 |
| 🖊 Header/Footer | Add page-number headers or footers | 5.14 |
| ⬛ Redact | Permanently black out sensitive content | 5.15 |
| 📋 TOC | Generate and insert a table of contents | 5.16 |
| ✨ Enhance | Deskew, denoise, and sharpen scanned pages | 5.17 |
| 📦 Batch | Apply any tool to many PDFs at once | 5.18 |
| ⚙ Preferences | Appearance mode, OCR language, output folder | 5.19 |

### 5.1 Merge

Merge combines two or more PDF files into a single output document. Files are processed in the order shown in the list.

- Click **Open PDF** or drag a file into the file row to add it to the list.
- Use the **Up / Down** buttons to reorder. Use **Remove** to delete an entry.
- Optionally enter a page range for each file (e.g., `1-3, 5` to include only pages 1, 2, 3, and 5).
- Click **Merge →** and choose an output path.

### 5.2 Split

Split extracts pages from a PDF into one or more output files.

- **Single range:** enter a page range (e.g., `2-5`) to extract those pages into one file.
- **Every page:** tick **Extract each page as a separate file** to produce one PDF per page, saved into a ZIP archive.

### 5.3 Password

Add or remove password protection and permission restrictions.

- **Open password:** required to open the document.
- **Owner password:** controls printing, copying, and editing permissions.
- To remove protection from an existing PDF, enter the current password and leave new password fields blank.

> ⚠️ **Warning:** Encryption is irreversible. Keep a copy of the password. PaperKnife+ PC cannot recover lost passwords.

### 5.4 Compress

Three presets balance quality against file size:

- **Light** — recompresses images to 85% JPEG quality. Minimal visual loss, moderate size reduction.
- **Medium** — resamples images to 150 DPI and applies 75% JPEG quality. Good balance for most documents.
- **Aggressive** — resamples to 96 DPI at 60% quality. Maximum reduction; may degrade photographic content.

### 5.5 Annotate

Add freehand drawings, text boxes, and rubber-stamp annotations to PDF pages. Use the toolbar to select tool, colour, and stroke width. Changes are embedded permanently in the output PDF.

### 5.6 OCR

Runs Tesseract to add an invisible text layer to scanned PDFs, making them searchable and copy-pasteable. Requires Tesseract on PATH (see Section 4.3).

- **DPI slider:** higher values produce better OCR accuracy at the cost of processing time. 300 DPI is recommended for standard documents.
- **Language:** must match the document language. Use the code set in Preferences, or override per-run.
- The original scan is preserved; OCR text is embedded as an invisible overlay.

### 5.7 Rotate

Rotate individual pages or all pages by 90°, 180°, or 270°. Select pages using the list (`Ctrl+click` for multi-select) or use **Rotate All**.

### 5.8 Crop

Adjusts the PDF crop box. Enter margin values in millimetres to trim from each edge. A preview shows the result before saving.

### 5.9 Convert

Convert PDF pages to PNG or JPEG images, or assemble a set of images into a PDF.

- **PDF → Images:** choose format (PNG for lossless, JPEG for smaller files) and export DPI.
- **Images → PDF:** drag or select multiple images. The order in the list determines page order.

### 5.10 – 5.19 Remaining Tools

**Metadata, Bookmarks, Find & Replace, Edit Text, Header/Footer, Redact, TOC, Enhance,** and **Batch** all follow the same open-file → configure → save pattern. Each tool's panel includes inline guidance. The Batch tool wraps any other tool to process a folder of PDFs in one operation.

---

## 6. Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + O` | Open file (tool-dependent) |
| `Ctrl + S` | Save / export (tool-dependent) |
| `Ctrl + Z` | Undo last action (where supported) |
| `Delete` | Remove selected item from list |
| `Ctrl + K` | Focus the sidebar search box |
| `Ctrl + F` | Focus the sidebar search box |
| `Escape` | Clear sidebar search |

---

## 7. File and Data Locations

| Item | Path |
|---|---|
| Application binaries | `%LOCALAPPDATA%\PaperKnifePlusPC\` |
| User preferences | `%USERPROFILE%\.paperknifepluspc\prefs.json` |
| Recent files list | `%USERPROFILE%\.paperknifepluspc\recent.json` |
| Add/Remove Programs | `HKCU\Software\Microsoft\Windows\...\Uninstall\PaperKnifePlusPC` |
| App registry key | `HKCU\Software\potatameister\PaperKnifePlusPC` |

To fully remove all application data after uninstalling, delete `%USERPROFILE%\.paperknifepluspc\` manually. The uninstaller intentionally preserves this folder so that recent file history and preferences survive a reinstall.

---

## 8. Troubleshooting

| Symptom | Resolution |
|---|---|
| `\Windows non atteso` (or `\Windows unexpected`) immediately on launch | Bug in `build_windows.bat`: `%_PF86%` and `%_PF64%` expand at parse time inside `for` loop bodies, and the `)` in `Program Files (x86)` prematurely closes the loop block. Fix: replace `%_PF86%` with `!_PF86!` and `%_PF64%` with `!_PF64!` in both `for` loop bodies in the signtool detection section. `setlocal enabledelayedexpansion` is already present so `!var!` syntax works. | | `tkinterdnd2` may not be present in the bundle. Run from source and install: `pip install tkinterdnd2` |
| OCR produces no output | Verify Tesseract is on PATH: open Command Prompt and run `tesseract --version`. See Section 4.3. |
| Dark mode not applying on restart | Save preferences via the Preferences panel after changing the colour mode. |
| PDF opens but pages appear blank | The file may be encrypted. PaperKnife+ PC will prompt for a password; ensure you enter the correct open password. |
| Windows SmartScreen warning on first run | Click **More info → Run anyway**. The warning disappears once the certificate gains reputation. |
| Application does not start | Check Windows Event Viewer (`eventvwr.msc`) under **Windows Logs → Application** for an error from `PaperKnifePlusPC.exe`. |
| Blurry UI on HiDPI display | The app is Per-Monitor v2 DPI-aware by manifest. If blurring persists, right-click the shortcut → **Properties → Compatibility** → change high DPI settings to **Application**. |

---

## 9. Building from Source (developers)

### 9.1 Prerequisites

- Python 3.10 or later.
- NSIS 3.x from https://nsis.sourceforge.io/ — required to produce the Setup `.exe`. If absent, the script warns and skips Step 4; only the folder bundle is produced.
- Windows SDK (optional, for code signing): https://developer.microsoft.com/windows/downloads/windows-sdk/

> ⚠️ **Do not build from a conda environment.** The spec excludes `numpy`, `mkl`, and `intel_openmp` to prevent PyInstaller from pulling in conda's full MKL stack (`msmpi.dll`, `ur_loader.dll`, `sycl8.dll` etc.), but PyInstaller still probes those packages during analysis when they are present in the active environment and crashes. Always build from a clean `venv` as shown below.

### 9.2 Build Steps

1. Unzip the source package and move the `PaperKnifePlusFixed` folder to a path with **no parentheses and no spaces** — `build_windows.bat` uses `for` loops that misparse either as block delimiters, producing `\Windows non atteso`. A safe location:
   ```
   C:\Build\PaperKnifePlusFixed\
   ```
2. Open **Command Prompt (`cmd.exe`)** — not PowerShell — and `cd` into the project folder:
   ```
   cd C:\Build\PaperKnifePlusFixed
   ```
3. If conda is active, deactivate it first to prevent environment stacking:
   ```
   conda deactivate
   ```
4. Create a clean virtual environment **inside the project folder** (`.venv` is relative — it lands at `C:\Build\PaperKnifePlusFixed\.venv\`, not in your user profile):
   ```
   python -m venv .venv
   .venv\Scripts\activate
   ```
5. Install application and build dependencies into the venv:
   ```
   pip install -r requirements.txt
   pip install pyinstaller
   ```
6. Run the build pipeline:
   ```
   .\build_windows.bat
   ```
   For a signed release build, supply your PFX certificate and password:
   ```
   .\build_windows.bat C:\path\to\cert.pfx YourPassword
   ```
7. Output files:
   - `dist\PaperKnifePlusPC\PaperKnifePlusPC.exe` — standalone folder bundle (always produced if PyInstaller succeeds)
   - `PaperKnifePlusPC-3.2.2-Setup.exe` — NSIS installer in the project root (only produced if NSIS is installed)

### 9.3 Build Pipeline Summary

| Step | Tool | What it does |
|---|---|---|
| 1 | `rmdir` | Cleans `dist\` and `build\` from previous runs |
| 2 | PyInstaller | Bundles Python runtime + app into one-dir EXE |
| 3 | signtool | Signs EXE and all bundled DLLs with SHA-256 Authenticode + RFC 3161 timestamp |
| 4 | makensis | Compiles NSIS script into Setup EXE |
| 5 | signtool | Signs the installer EXE |

> ℹ️ **Note:** Steps 3 and 5 are skipped if no certificate is provided or if `signtool.exe` cannot be located in the Windows SDK. The build continues and produces an unsigned package suitable for local testing.

---

## 10. Privacy and Security

PaperKnife+ PC makes zero network connections. There is no telemetry, no analytics, no crash reporting, and no update check. The following data is stored locally only:

- `prefs.json` — your preferences (appearance mode, OCR language, output folder).
- `recent.json` — a list of recently opened file paths, page counts, and access times.

No file content is ever read for any purpose other than the operation you explicitly invoke. Deleting `%USERPROFILE%\.paperknifepluspc\` removes all application data completely.

---

## 11. Changelog

### v3.2.2 — current

- **Fixed:** drag-and-drop broken under customtkinter 5.x (direct Tcl `tk.call` instead of `TkinterDnD._require`).
- **Fixed:** sidebar section toggle re-appended buttons to list tail instead of restoring in-place (`after=` anchor).
- **Fixed:** dark mode not persisted across sessions (appearance saved to `prefs.json` via Preferences panel).
- **New:** full dark theme with WCAG-compliant warm-brown palette; white text on accent passes AA.
- **New:** `app.manifest` embedded in installer EXE (Per-Monitor v2 DPI, `longPathAware`, `supportedOS` Win10/11).
- **New:** NSIS installer with per-user install, Add/Remove Programs registration, and silent `/S` mode.
- **New:** `build_windows.bat` pipeline with auto-detected signtool and graceful degradation when SDK absent.

### v3.2.1

- Initial public release.

---

## 12. License

PaperKnife+ PC is distributed under the **MIT License**. Third-party components:

| Library | License | Purpose |
|---|---|---|
| PyMuPDF (fitz) | AGPL v3 | PDF rendering and manipulation |
| customtkinter | MIT | Modern tkinter UI widgets |
| Pillow | HPND | Image processing |
| tkinterdnd2 | MIT | Drag-and-drop support |
| pytesseract | Apache 2 | Tesseract OCR bridge |
| python-docx | MIT | DOCX conversion |
| python-pptx | MIT | PPTX conversion |
| openpyxl | MIT | XLSX conversion |

**PyMuPDF / AGPL note:** PyMuPDF is licensed under AGPL v3. If you distribute a modified version of this application that incorporates PyMuPDF, your modifications must also be released under AGPL v3 or a compatible license, or you must obtain a commercial PyMuPDF license from Artifex.

---

*PaperKnife+ PC v3.2.2 · github/potatameister · 100% local, no cloud, no tracking*
