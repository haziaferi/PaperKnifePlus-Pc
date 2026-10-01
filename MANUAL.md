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
| Display | The window's minimum size is 1060 × 720; HiDPI supported (Per-Monitor v2) |
| Tesseract | Optional — required for OCR only |

> ⚠️ **OCR prerequisite:** OCR (the OCR tool and Batch → OCR) requires the Tesseract binary separately. See Section 4.3.

---

## 3. Installation

### 3.1 Standard Installer (recommended)

The NSIS installer packages the full Python runtime alongside the application. No existing Python installation is needed on the target machine, but you must build the installer once from the source package before distributing or installing it.

1. Unzip the source package and follow the build steps in **Section 9** to produce `PaperKnifePlusPC-3.2.2-Setup.exe`. The installer appears in the project root only if both **PyInstaller** and **NSIS** are installed. If NSIS is absent, the build skips Steps 4–5 and produces only a folder bundle (`dist\PaperKnifePlusPC\`) — no Setup `.exe`.
2. Double-click the installer. No UAC elevation prompt appears — the app installs per-user into `%LOCALAPPDATA%\PaperKnifePlusPC`. If you choose another folder, the installer creates a `PaperKnifePlusPC` subfolder inside it.
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
"%LOCALAPPDATA%\PaperKnifePlusPC\Uninstall.exe" /S _?=%LOCALAPPDATA%\PaperKnifePlusPC
```

> ℹ️ **Note:** The installer command returns when installation is complete. An NSIS uninstaller normally copies itself to `%TEMP%` and returns at once; the `_?=` argument makes it run in place and return only when the files are removed. It then cannot delete itself: remove `Uninstall.exe` and the empty folder afterwards. Exit code 0 indicates success.

### 3.3 Running from Source (developers)

If you are working with the source distribution rather than the compiled installer:

1. Ensure Python 3.10 or later is on your PATH. Conda environments are known to cause issues (see Section 9.1).
2. Run the provided setup script. It creates a virtual environment in `.venv` inside the project folder (or reuses an existing one) and installs everything in `requirements.txt` into it, core and optional:
   ```
   setup.bat
   ```
   Or install manually into your own venv:
   ```
   pip install -r requirements.txt
   ```
3. Launch by double-clicking `run.bat` in the project root (it uses `.venv` when present), or:
   ```
   python -m paperknife
   ```

> ℹ️ **Note:** `requirements.txt` marks `tkinterdnd2`, `pytesseract`, and the document-conversion libraries (`python-docx`, `python-pptx`, `openpyxl`, `striprtf`) as optional. `setup.bat` installs all of them. If you install manually and omit them, drag-and-drop, OCR, conversion to and from DOCX/PPTX/XLSX, and RTF → PDF text extraction will not function.

---

## 4. First Launch

### 4.1 Home Screen

On first launch the home screen shows seven quick-action buttons (Read / Preview, Merge, Split, Password, Compress, Annotate, OCR) and an empty Recent Files grid. Click a recent file to open it in Read / Preview. The sidebar on the left groups all tools into labelled sections. Click any section header to collapse or expand it. Use `Ctrl+K` or `Ctrl+F` to search tools by name.

### 4.2 Appearance Mode

PaperKnife+ PC supports light, dark, and system-matched appearance modes. To change:

1. Click ⚙ **Preferences** in the sidebar.
2. Under **Appearance**, set **Colour mode** to light, dark, or system.
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
4. In Preferences, set the OCR language code (e.g., `eng` for English, `ita` for Italian, `deu` for German). Multiple codes can be combined: `eng+ita`. The OCR tool and Batch → OCR start with this code; you can change it per run.

---

## 5. Tools Reference

The sidebar lists 26 tools in six sections.

| Section | Tool | What it does | § |
|---|---|---|---|
| READ | 📖 Read / Preview | Continuous-scroll, view-only PDF viewer | 5.1 |
| ORGANISE | 📎 Merge | Combine PDFs, with optional page ranges per file | 5.2 |
| | ✂ Split | Extract page ranges, or every page, to separate files | 5.3 |
| | 🔄 Rotate & Reorder | Rotate or move single pages on a thumbnail grid | 5.4 |
| | 🔖 Split by Bookmarks | One file per bookmark (chapter) | 5.5 |
| | 📑 Bookmarks / TOC | Edit the PDF's bookmark (outline) tree | 5.6 |
| | ⚙ Batch | Compress, Watermark, OCR, or PDF → TXT on every PDF in a folder | 5.7 |
| ENHANCE | 🗜 Compress | Clean and deflate; optionally downsample images | 5.8 |
| | 💧 Watermark | Diagonal text watermark on every page | 5.9 |
| | 📐 Normalise Pages | Resize every page to a standard paper size | 5.10 |
| | 🔒 Password | Add, change, or remove an AES-256 password | 5.11 |
| | ✂ Crop / Trim | Cut margins from the crop box | 5.12 |
| | 📋 Header / Footer | Stamp page numbers, text, or the date in a margin | 5.13 |
| | 🔧 PDF Tools | Repair a damaged PDF | 5.14 |
| CONTENT | 🤖 OCR | Make scanned PDFs searchable with Tesseract | 5.15 |
| | ✏️ Edit Text | Edit a text block in place | 5.16 |
| | 🔍 Find & Replace | Replace text across all pages | 5.17 |
| | 📝 Annotate | Highlights, shapes, notes, and text boxes | 5.18 |
| | ⬛ Redact | Permanently remove content under boxes or matching text | 5.19 |
| | 🏷 Metadata | View and edit document properties | 5.20 |
| CONVERT | 🖼 Image → PDF | Images to a PDF, one page per image | 5.21 |
| | 📸 PDF → Images | Every page as a PNG, in a ZIP | 5.22 |
| | 🖼 Extract Images | Save the embedded images to a folder | 5.23 |
| | 📄 PDF → Doc / Text | Export to TXT, HTML, XML, RTF, DOCX, PPTX, XLSX, PNG, or JPEG | 5.24 |
| | 📤 Doc / Text → PDF | Convert TXT, HTML, XML, RTF, DOCX, PPTX, XLSX, PNG, or JPEG to PDF | 5.25 |
| SETTINGS | ⚙ Preferences | Output folder, recent files, colour mode, DPI, compress level, OCR language | 5.26 |

Page ranges, where a tool accepts them, are written like `1-3, 5, 8-end`. A range that names a page the document does not have, or runs backwards, is refused with a message before anything is written.

### 5.1 Read / Preview

A view-only viewer: open a PDF with **Open PDF** or `Ctrl+O`, scroll through all pages continuously, and change the size with the **Zoom** slider.

### 5.2 Merge

Merge combines two or more PDF files into a single output document. Files are processed in the order shown in the list.

- Click **＋ Add PDFs** (or `Ctrl+O`) to add files. When drag-and-drop is available, you can also drop PDFs onto the list.
- Click a file name to select it, then use **↑ Up / ↓ Down** to reorder or **✕ Remove selected** (or `Delete`) to remove it.
- Optionally enter a page range for each file in its **Pages** field; blank includes all pages.
- Click **Merge PDFs →** and choose an output path.

### 5.3 Split

Split extracts pages from a PDF into separate files in a folder you choose.

- Enter comma-separated page ranges (e.g., `1-3, 5, 7-9`); each range becomes one file.
- Leave the field blank to write one PDF per page.

### 5.4 Rotate & Reorder

Open a PDF, click a thumbnail to select that page, then use **↺ 90° CCW**, **↻ 90° CW**, or **⤢ 180°** to rotate it, or **← Move Left / Move Right →** to change its position. Click **Save PDF →** to write the result. One page is selected at a time.

### 5.5 Split by Bookmarks

Open a PDF to see its bookmarks, choose **Top-level only (level 1)** or **All bookmark levels**, and pick an output folder. Each chosen bookmark starts a new file that runs to the next one. Bookmarks that point to no page are skipped and counted in the result message.

### 5.6 Bookmarks / TOC

An editor for the PDF's bookmark (outline) tree. Select an entry, change its **Level**, **Title**, or **Page**, and use **↑ Up**, **↓ Down**, **＋ Add below**, **✎ Update selected**, or **✕ Delete**. Saving checks that the levels nest correctly. It does not create a table-of-contents page.

### 5.7 Batch

Choose an operation, an input folder, and an output folder, then click **Run Batch →**. Every `*.pdf` directly in the input folder is processed; results are listed per file.

- **Compress** — the levels of Section 5.8. Output `<name>_compressed.pdf`.
- **Watermark** — text, size, and opacity; the colour is grey. Output `<name>_watermarked.pdf`.
- **OCR** — language and DPI, as in Section 5.15 (overlay mode). Output `<name>_ocr.pdf`.
- **PDF → TXT** — the text of every page. Output `<name>.txt`.

Password-protected files are skipped with an error; open them in the single-file tool instead.

### 5.8 Compress

Three levels balance quality against file size:

- **Light** — removes unused objects and compresses streams. No image is changed.
- **Medium** — as Light, and embedded images above 150 DPI are resampled to 150 DPI and stored as JPEG at quality 80 when that makes them smaller.
- **Aggressive** — as Medium, at 96 DPI.

Text and vector content are kept in every level. If the output is not smaller than the original, a warning says so. The starting level comes from Preferences.

### 5.9 Watermark

Enter the text, then set the font size (18–120 pt), opacity (5–100 %), and colour. The text is drawn at 45° through the centre of every page and shrunk if needed to fit inside the page.

### 5.10 Normalise Pages

Choose a target size (A4, A3, A5, Letter, Legal, Tabloid), an orientation (Portrait, Landscape, or Keep original), and **Fit (keep ratio)** or **Stretch (fill page)**. Each page is redrawn onto a new page of that size.

### 5.11 Password

The tool has two panels.

- **Add / Change Password:** enter an open (user) password, optionally an owner password, and untick **Allow printing** or **Allow copying text** to deny those rights. A blank owner password is replaced by a random one, so the open password alone does not lift the restrictions. To change the password of an already-protected PDF, also enter its current password in the **Remove Password** panel's **Current password** field.
- **Remove Password:** enter the current password and click **Remove Password →** to save an unencrypted copy.

> ⚠️ **Warning:** Without the password the file cannot be opened. PaperKnife+ PC cannot recover lost passwords.

### 5.12 Crop / Trim

Enter how much to cut from each edge, in points (72 pt = 1 inch = 25.4 mm), and optionally a page range (blank = all pages). Tick **Reset to full media box first** to undo earlier crops. Margins are measured on the page as displayed, also on rotated pages. There is no preview.

### 5.13 Header / Footer

Choose one of six positions (top or bottom; left, centre, or right), enter the text — `{page}`, `{total}`, and `{date}` are replaced — and set the font (Helvetica, Times Roman, Courier), size, margin in points, and an optional page range.

### 5.14 PDF Tools

**Repair** opens the file (MuPDF rebuilds a damaged cross-reference table while opening) and saves a cleaned copy. The message says whether damage was found. Pages that cannot be recovered are lost.

### 5.15 OCR

Runs Tesseract on each page to make scanned PDFs searchable and copy-pasteable. Requires Tesseract on PATH (see Section 4.3).

- **Language code:** must match the document language. It starts with the code from Preferences; change it per run.
- **Render DPI:** higher values give better accuracy at the cost of time; it starts at the Preferences DPI (limited to 72–400). 300 DPI is recommended for standard documents.
- **Overlay (invisible text layer):** the original page is kept unchanged and the recognised words are added on top as invisible text. Words Tesseract recognises with low confidence are left out.
- **Text-only PDF:** a new PDF with the recognised plain text on A4 pages, without the page images.

### 5.16 Edit Text

Open a PDF, click a text block, edit it in the box below the page, and click **Apply Edit**. The new text is wrapped to the block's width and drawn in a built-in font, so the typeface may change. `Ctrl+Z` undoes the last edit; **Save PDF →** or `Ctrl+S` writes the file.

### 5.17 Find & Replace

Enter the text to find, click **Find All**, and step through matches with **◀ Prev / Next ▶**. **Replace All** replaces every match on all pages. Matching is case-sensitive, and a phrase broken across a line counts as one match. `Ctrl+Z` undoes the last Replace All.

### 5.18 Annotate

Pick one of seven tools — **Highlight**, **Underline**, **Strikeout**, **Rectangle**, **Line**, **Note**, **Freetext** — and drag (or click) on the page. **Note** and **Freetext** use the text in the **Text** field. Set **Colour** and **Opacity** before drawing, and **Zoom** to change the view. Click an existing annotation to select it, then **✕ Remove sel.** to delete it; **↩ Undo** (or `Ctrl+Z`) removes the last annotation you added. Click **Save Annotated PDF →** to write the file.

### 5.19 Redact

Drag boxes over content, or type an exact phrase and click **Mark all** to mark every occurrence in the document. Choose a **Black** or **White** fill. **Apply Redactions** permanently removes the text and image pixels under the boxes, plus any annotations or form fields they touch; **↩ Undo last** removes a pending box before applying. On save, each redacted phrase is also removed from the document properties, XMP metadata, bookmark titles, annotations, form fields, and attachments, and the message lists what was changed.

### 5.20 Metadata

Shows Title, Author, Subject, Keywords, Creator, Producer, Creation date, and Modified date. Dates are entered as `YYYY-MM-DD` (optionally with `HH:MM[:SS]`) or as a PDF date (`D:…`). **Clear all fields** empties them; **Save PDF with metadata →** writes a copy and drops the old XMP metadata when anything changed.

### 5.21 Image → PDF

Add JPG, PNG, WEBP, BMP, TIFF, or GIF images (or drop them on the list), order them with **↑ Up / ↓ Down**, and click **Convert to PDF →**. Each image becomes one page of its own size, upright according to its EXIF orientation; transparency is flattened onto white.

### 5.22 PDF → Images

Every page is rendered as a PNG at the chosen DPI (72–300, starting at the Preferences DPI) and saved into one ZIP file.

### 5.23 Extract Images

Saves every embedded image of at least the **Minimum dimension** (default 50 px) to a folder, in its original format or converted to PNG or JPEG.

### 5.24 PDF → Doc / Text

Choose the output format: TXT, HTML, XML, RTF, DOCX (needs python-docx), PPTX (page pictures on slides; needs python-pptx), XLSX (one sheet per page; needs openpyxl), or PNG / JPEG (pages in a ZIP, with DPI and, for JPEG, quality).

### 5.25 Doc / Text → PDF

Choose the input format (it is set automatically from the file extension when you pick or drop a file): TXT, HTML, XML, RTF, DOCX, PPTX, XLSX, PNG, or JPEG. Text formats are typeset on A4 pages; DOCX keeps headings and tables; PPTX gives one page per slide's text; XLSX is laid out as plain-text tables on landscape A4.

### 5.26 Preferences

| Setting | Used by |
|---|---|
| Default output folder | The starting folder of every save and output-folder dialog |
| Max recent files shown | Number of cards on the Home screen (1–50) |
| Colour mode | light, dark, or system (Section 4.2) |
| Default DPI (OCR / export) | Starting DPI of OCR, Batch → OCR, PDF → Images, and the PNG/JPEG/PPTX exports (72–600; each slider clamps it to its own range) |
| Default compress level | Starting level of Compress and Batch → Compress |
| OCR language code | Starting language of OCR and Batch → OCR |

Click **Save Preferences** to keep changes; **Restore defaults** resets them.

---

## 6. Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + O` | Open file (tool-dependent) |
| `Ctrl + S` | Save / run (tool-dependent) |
| `Ctrl + Z` | Undo in Edit Text, Find & Replace, Annotate, and Redact |
| `Delete` | Remove the selected file in Merge or Image → PDF (ignored while typing in a field) |
| `Ctrl + K` | Focus the sidebar search box |
| `Ctrl + F` | Focus the sidebar search box |
| `Escape` | Clear the sidebar search |

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
| Dragging a file onto the window does nothing | When running from source, install `tkinterdnd2` (`pip install tkinterdnd2`); without it the file rows say "No file selected…" instead of "Drop a file here or click to browse…". If it is installed but cannot load, the app prints `drag and drop disabled` to the console. Use the **Open** buttons meanwhile. |
| OCR produces no output | Verify Tesseract is on PATH: open Command Prompt and run `tesseract --version`. See Section 4.3. |
| Dark mode not applying on restart | Save preferences via the Preferences panel after changing the colour mode. |
| A password-protected PDF will not open | Every single-file tool asks for the open password. Batch cannot stop to ask, so it skips protected files with an error: remove the password first with the Password tool (Section 5.11). |
| Windows SmartScreen warning on first run | Click **More info → Run anyway**. The warning disappears once the certificate gains reputation. |
| Application does not start | Check Windows Event Viewer (`eventvwr.msc`) under **Windows Logs → Application** for an error from `PaperKnifePlusPC.exe`. |
| Blurry UI on HiDPI display | The app is Per-Monitor v2 DPI-aware by manifest. If blurring persists, right-click the shortcut → **Properties → Compatibility** → change high DPI settings to **Application**. |

---

## 9. Building from Source (developers)

### 9.1 Prerequisites

- Python 3.10 or later.
- NSIS 3.x from https://nsis.sourceforge.io/ — required to produce the Setup `.exe`. The script finds `makensis` on PATH or in the default NSIS folder; if absent, it warns and skips Steps 4–5, and only the folder bundle is produced.
- Windows SDK (optional, for code signing): https://developer.microsoft.com/windows/downloads/windows-sdk/

> ⚠️ **Build from a clean `venv`, never from conda or the global Python.** In a shared environment PyInstaller bundles every package its hooks can reach (an earlier build from a conda environment produced a 444 MB executable). The spec excludes `numpy`, `mkl`, and `intel_openmp`, but PyInstaller still probes conda's MKL packages (`msmpi.dll`, `ur_loader.dll`, `sycl8.dll` etc.) during analysis when they are present and can crash. `build_windows.bat` stops if it is not running in a virtual environment.

### 9.2 Build Steps

1. Unzip the source package and keep the `PaperKnifePlusPC` folder at a short path, for example `C:\Build\PaperKnifePlusPC\`: `makensis` cannot open files whose full path is longer than 260 characters.
2. Open **Command Prompt (`cmd.exe`)** and `cd` into the project folder:
   ```
   cd C:\Build\PaperKnifePlusPC
   ```
3. If conda is active, deactivate it first to prevent environment stacking:
   ```
   conda deactivate
   ```
4. Create a clean virtual environment **inside the project folder** (`.venv` is relative — it lands at `C:\Build\PaperKnifePlusPC\.venv\`, not in your user profile):
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
   build_windows.bat
   ```
   For a signed release build, put the PFX password in an environment variable (so it stays out of the command line and shell history) and pass the certificate path:
   ```
   set PFX_PASSWORD=YourPassword
   build_windows.bat C:\path\to\cert.pfx
   set PFX_PASSWORD=
   ```
7. Output files:
   - `dist\PaperKnifePlusPC\PaperKnifePlusPC.exe` — standalone folder bundle (always produced if PyInstaller succeeds)
   - `PaperKnifePlusPC-3.2.2-Setup.exe` — NSIS installer in the project root (only produced if NSIS is installed)

### 9.3 Build Pipeline Summary

| Step | Tool | What it does |
|---|---|---|
| 1 | `rmdir` | Removes `dist\PaperKnifePlusPC\` and `build\` from previous runs |
| 2 | PyInstaller | Bundles Python runtime + app into a one-dir EXE |
| 3 | signtool | Signs the EXE and every bundled `.dll` and `.pyd` with SHA-256 Authenticode + RFC 3161 timestamp; any failure stops the build |
| 4 | makensis | Compiles the NSIS script into the Setup EXE |
| 5 | signtool | Signs the installer EXE |

> ℹ️ **Note:** Steps 3 and 5 are skipped if no certificate is provided or if `signtool.exe` cannot be located in the Windows SDK. The build continues and produces an unsigned package suitable for local testing.

---

## 10. Privacy and Security

PaperKnife+ PC makes zero network connections. There is no telemetry, no analytics, no crash reporting, and no update check. The following data is stored locally only:

- `prefs.json` — your preferences (Section 5.26) and the last window size and position.
- `recent.json` — recently opened files: path, file name, size, page count, and access time.

Apart from the operation you invoke, the only file content read is the first page of each recent file, rendered as a thumbnail on the Home screen and in hover previews. Deleting `%USERPROFILE%\.paperknifepluspc\` removes all application data completely.

---

## 11. Changelog

### v3.2.2 — current

- **Fixed:** drag-and-drop never loaded; tkdnd is now loaded through `TkinterDnD._require`, and the build bundles it where that looks.
- **Fixed:** sidebar section toggle and search could put tools back in the wrong place; the sidebar is now re-laid out in registry order.
- **Fixed:** dark mode not persisted across sessions (appearance saved to `prefs.json` via Preferences panel).
- **Changed:** Compress Medium/Aggressive resample images instead of turning whole pages into pictures; text stays selectable.
- **Changed:** OCR overlay keeps the original page and adds an invisible text layer; OCR and the exports start from the Preferences language and DPI.
- **Removed:** the PDF/A and Linearise options of PDF Tools, which PyMuPDF 1.28 cannot produce.
- **Fixed:** Watermark opacity and angle (also on rotated pages); Password permissions; Annotate selection and **Remove sel.**; Edit Text and Find & Replace undo; every single-file tool now asks for the password of a protected PDF.
- **New:** full dark theme with WCAG-compliant warm-brown palette; white text on accent passes AA.
- **New:** `app.manifest` embedded in `PaperKnifePlusPC.exe` (Per-Monitor v2 DPI, `longPathAware`, `supportedOS` Win10/11).
- **New:** NSIS installer with per-user install, Add/Remove Programs registration, and silent `/S` mode.
- **New:** `build_windows.bat` pipeline with auto-detected signtool and graceful degradation when SDK absent.

### v3.2.1

- The fixes in this release are listed (in Italian) in the changelog of `README.md`.

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
