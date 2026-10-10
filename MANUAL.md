# ✂ PaperKnife+ PC
## Installation & User Manual

**Version 4.0.0** · 100% local · no cloud · no tracking · Windows 10 / 11 · x64

*github/potatameister*

---

## 1. Overview

PaperKnife+ PC is a fully offline PDF toolkit for Windows 10 and 11. Every operation runs on your machine — no file is ever uploaded to a server, no account is required, and no telemetry is collected.

| Property | Value |
|---|---|
| Version | 4.0.0 |
| Platform | Windows 10 / 11 (x64) |
| Python runtime | Bundled — no install needed |
| Interface | Qt 6 (PySide6) with Fluent widgets — bundled |
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
| Disk space | ~140 MB installed, a 66 MB installer (bundled Python runtime and Qt 6 libraries) |
| Display | The window's minimum size is 1060 × 720; HiDPI supported (Per-Monitor v2) |
| Fonts | Segoe UI Variable (Segoe UI where it is missing) and Segoe Fluent Icons (Segoe MDL2 Assets on Windows 10) — Windows' own, not bundled |
| Tesseract | Optional — required for OCR only |

> ⚠️ **OCR prerequisite:** OCR (the OCR tool and Batch → OCR) requires the Tesseract binary separately. See Section 4.3.

---

## 3. Installation

### 3.1 Standard Installer (recommended)

The NSIS installer packages the full Python runtime alongside the application. No existing Python installation is needed on the target machine, but you must build the installer once from the source package before distributing or installing it.

1. Unzip the source package and follow the build steps in **Section 9** to produce `PaperKnifePlusPC-4.0.0-Setup.exe`. The installer appears in the project root only if both **PyInstaller** and **NSIS** are installed. If NSIS is absent, the build skips Steps 4–5 and produces only a folder bundle (`dist\PaperKnifePlusPC\`) — no Setup `.exe`.
2. Double-click the installer. No UAC elevation prompt appears — the app installs per-user into `%LOCALAPPDATA%\PaperKnifePlusPC`. If you choose another folder, the installer creates a `PaperKnifePlusPC` subfolder inside it. A later version installs into the same folder as the one it replaces. Close PaperKnife+ PC first: while it is running, Setup and the uninstaller stop and change nothing.
3. A desktop shortcut and Start Menu entry are created automatically.
4. Launch via the desktop shortcut, the Start Menu, or run `%LOCALAPPDATA%\PaperKnifePlusPC\PaperKnifePlusPC.exe` directly.

> ℹ️ **Note:** If you only need to run the app on your own machine without building an installer, use the **Section 3.3** source method instead — it requires no build step.

### 3.2 Silent Installation (enterprise / scripted)

The installer supports fully silent mode with no UI and no prompts, suitable for SCCM, Intune, or GPO software deployment:

```
PaperKnifePlusPC-4.0.0-Setup.exe /S
```

Silent uninstall:

```
"%LOCALAPPDATA%\PaperKnifePlusPC\Uninstall.exe" /S _?=%LOCALAPPDATA%\PaperKnifePlusPC
```

> ℹ️ **Note:** The installer command returns when installation is complete. An NSIS uninstaller normally copies itself to `%TEMP%` and returns at once; the `_?=` argument makes it run in place and return only when the files are removed. It then cannot delete itself: remove `Uninstall.exe` and the empty folder afterwards. Exit code 0 indicates success; exit code 2 means nothing was changed, for example because PaperKnife+ PC was running.

### 3.3 Running from Source (developers)

If you are working with the source distribution rather than the compiled installer:

1. Ensure Python 3.10 or later is on your PATH (PySide6 6.12 installs on Python 3.10 to 3.15). Conda environments are known to cause issues (see Section 9.1).
2. Run the provided setup script. It creates a virtual environment in `.venv` inside the project folder (or reuses an existing one), installs everything in `requirements.txt` into it, core and optional, and then `requirements-fluent.txt` with `--no-deps`:
   ```
   setup.bat
   ```
   Or install manually into your own venv, in this order:
   ```
   pip install -r requirements.txt
   pip install --no-deps -r requirements-fluent.txt
   ```
   `requirements.txt` holds PyMuPDF, Pillow, `PySide6-Essentials==6.12.0`, `darkdetect` and `pywin32`, and the optional packages below. `requirements-fluent.txt` holds `PySide6-Fluent-Widgets==1.11.3` and `PySideSix-Frameless-Window==0.8.2`; `--no-deps` matters, because their metadata asks for the full PySide6, which adds Addons, WebEngine and Pdf (several hundred MB) the app never imports. The Fluent version is pinned exactly: `paperknife/qt/fluent_route.py` patches its internals.
3. Launch by double-clicking `run.bat` in the project root (it uses `.venv` when present), or:
   ```
   python -m paperknife.qt
   ```
   A PDF path after the command (`python -m paperknife.qt file.pdf`) opens that file in Read / Preview.

> ℹ️ **Note:** `requirements.txt` marks `pytesseract` and the document-conversion libraries (`python-docx`, `python-pptx`, `openpyxl`, `striprtf`) as optional. `setup.bat` installs all of them. If you install manually and omit them, OCR, conversion to and from DOCX/PPTX/XLSX, and RTF → PDF text extraction will not function. Drag and drop is part of Qt and needs nothing extra.

---

## 4. First Launch

### 4.1 Home Screen and Window

On first launch the Home page shows seven quick-action buttons (Read / Preview, Merge, Split, Password, Compress, Annotate, OCR) and an empty Recent files grid. Click a recent file to open it in Read / Preview; **Clear history** empties the list. A PDF dropped on Home also opens in Read / Preview.

The navigation pane on the left lists Home, then the tools in labelled groups (Read, Organise, Enhance, Convert, Content), with Preferences at the bottom. The search box at its top filters tools by name (`Ctrl+K` or `Ctrl+F`); `Enter` opens the first match. The pane is expanded when the window is at least 900 px wide; `Ctrl+Alt+S` collapses or expands it.

Every tool page has its title at the top left and its main action (the accent button) at the top right. Under the pages, the status line reports the last result; a coloured line starts with ✓ (done), ⚠ (warning) or ✗ (error). While a job runs, a progress bar with **Cancel** appears above the status line; a job that works on the document a page shows holds that page and the navigation until it ends.

Read / Preview, Edit Text, Find & Replace, Annotate and Redact open as a document workspace: a tool rail at the left (not in Read / Preview), the page in the centre with page arrows and **Zoom** under it, and a context panel at the right. Drag the panel's edge to resize it (220–480 px), double-click the edge or use the panel's hide / show buttons to toggle it.

**Compact Mode** (`Ctrl+Alt+C`) hides the navigation pane, the page header and the context panel; moving the pointer to the left, top or right edge of the window brings each back. The title bar hides and comes back when the pointer reaches the top edge (set the environment variable `PK_TITLEBAR=always` to keep it shown). The window's size, position and maximized state are restored at the next start.

### 4.2 Appearance Mode

PaperKnife+ PC supports light, dark, and system-matched appearance modes. To change:

1. Click **Preferences** at the bottom of the navigation pane.
2. Under **Appearance**, set **Colour mode** to light, dark, or system.
3. Click **Save Preferences** (or `Ctrl+S`). The mode takes effect immediately and is restored on next launch. **system** follows Windows' light / dark setting, also when it changes while the app runs.

### 4.3 OCR Setup (optional)

The OCR tool requires the Tesseract OCR engine to be installed separately. PaperKnife+ PC does not bundle Tesseract because of its size and because it is an independent open-source project.

1. Download the Windows installer from:
   ```
   https://github.com/UB-Mannheim/tesseract/wiki
   ```
2. Run the installer. Tick the language packs you need (for Italian, `ita`).
3. PaperKnife+ PC looks for `tesseract.exe` on PATH first, then in `C:\Program Files\Tesseract-OCR`, `C:\Program Files (x86)\Tesseract-OCR` and `%LOCALAPPDATA%\Programs\Tesseract-OCR`. The installer's default folder needs no PATH change. If you installed somewhere else, add that folder to your user PATH:
   - Open **Settings → System → About → Advanced system settings**.
   - Click **Environment Variables** → select **Path** under User variables → **Edit**.
   - Click **New** and paste the Tesseract installation path.
   - Click **OK** on all dialogs, then restart PaperKnife+ PC.
4. In Preferences, set the OCR language code (e.g., `eng` for English, `ita` for Italian, `deu` for German). Multiple codes can be combined: `eng+ita`. The OCR tool and Batch → OCR start with this code; you can change it per run.

---

## 5. Tools Reference

The navigation pane lists 26 tools in five groups, with Preferences at the bottom.

| Group | Tool | What it does | § |
|---|---|---|---|
| Read | Read / Preview | Continuous-scroll, view-only PDF viewer | 5.1 |
| Organise | Merge | Combine PDFs, with optional page ranges per file | 5.2 |
| | Split | Extract page ranges, or every page, to separate files | 5.3 |
| | Rotate & Reorder | Rotate or move pages on a thumbnail grid | 5.4 |
| | Split by Bookmarks | One file per bookmark (chapter) | 5.5 |
| | Bookmarks / TOC | Edit the PDF's bookmark (outline) tree | 5.6 |
| | Batch | Compress, Watermark, OCR, or PDF → TXT on every PDF in a folder | 5.7 |
| Enhance | Password | Add, change, or remove an AES-256 password | 5.11 |
| | Compress | Clean and deflate; optionally downsample images | 5.8 |
| | Watermark | Diagonal text watermark on every page | 5.9 |
| | Normalise Pages | Resize every page to a standard paper size | 5.10 |
| | Header / Footer | Stamp page numbers, text, or the date in a margin | 5.13 |
| | Crop / Trim | Cut margins from the crop box | 5.12 |
| | PDF Tools | Repair a damaged PDF | 5.14 |
| Convert | Image → PDF | Images to a PDF, one page per image | 5.21 |
| | PDF → Images | Every page as a PNG, in a ZIP | 5.22 |
| | Extract Images | Save the embedded images to a folder | 5.23 |
| | PDF → Doc / Text | Export to TXT, HTML, XML, RTF, DOCX, PPTX, XLSX, PNG, or JPEG | 5.24 |
| | Doc / Text → PDF | Convert TXT, HTML, XML, RTF, DOCX, PPTX, XLSX, PNG, or JPEG to PDF | 5.25 |
| Content | Edit Text | Edit a text block in place | 5.16 |
| | Find & Replace | Replace text across all pages | 5.17 |
| | Annotate | Highlights, shapes, notes, and text boxes | 5.18 |
| | Redact | Permanently remove content under boxes or matching text | 5.19 |
| | OCR | Make scanned PDFs searchable with Tesseract | 5.15 |
| | Metadata | View and edit document properties | 5.20 |
| (bottom) | Preferences | Output folder, recent files, colour mode, DPI, compress level, OCR language | 5.26 |

A tool that works on one file shows a file card at the top: drop a file on it or click **Choose file** (`Ctrl+O`), and **Change** to pick another. Dropping a file the tool does not take leaves it unchanged and the status line says so.

Page ranges, where a tool accepts them, are written like `1-3, 5, 8-end`. A range that names a page the document does not have, or runs backwards, is refused with a message before anything is written.

A password-protected PDF asks for its open password when it is opened. The password stays with the open document only: it is forgotten when the document is closed, and asked again the next time. When a new PDF is written from a document opened with a password, the app asks whether the new file keeps it; Merge asks only when every protected input has the same open password.

### 5.1 Read / Preview

A view-only viewer: open a PDF with **Open PDF** or `Ctrl+O`, scroll through all pages continuously, and change the size with the **Zoom** slider (50–300 %) or `Ctrl` + mouse wheel. The strip under the pages shows which pages are in view; its arrows jump one page.

### 5.2 Merge

Merge combines two or more PDF files into a single output document. Files are processed in the order shown in the list.

- Click **Add PDFs** (or `Ctrl+O`) to add files, or drop PDFs onto the list.
- Click a file to select it, then use **Up / Down** (or `Alt+Up` / `Alt+Down`) to reorder or **Remove** (or `Delete`) to remove it.
- Optionally enter a page range in each file's range field; blank includes all pages.
- Click **Merge** and choose an output path.

### 5.3 Split

Split extracts pages from a PDF into separate files in a folder you choose.

- Enter comma-separated page ranges (e.g., `1-3, 5, 7-9`); each range becomes one file.
- Leave the field blank to write one PDF per page.

### 5.4 Rotate & Reorder

Open a PDF, click a thumbnail to select that page (`Ctrl`- or `Shift`-click to select several), then use **↺ 90° CCW**, **↻ 90° CW**, or **⤢ 180°** to rotate the selection, or **← Move Left / Move Right →** to change its position. A thumbnail can also be dragged to a new place. Click **Save PDF** to write the result.

### 5.5 Split by Bookmarks

Open a PDF to see its bookmarks (the first 60 are listed), choose **Top-level only (level 1)** or **All bookmark levels** under **Split at**, click **Split**, and pick an output folder. Each chosen bookmark starts a new file that runs to the next one. Bookmarks that point to no page are skipped and counted in the result message.

### 5.6 Bookmarks / TOC

An editor for the PDF's bookmark (outline) tree. Select an entry, change its **Level** (1–4), **Title**, or **Page** in the column at the right and click **Update selected**; use **Add below**, **Up**, **Down**, and **Delete** above the list. **Save PDF** checks that the levels nest correctly. It does not create a table-of-contents page.

### 5.7 Batch

Choose an **Operation**, an **Input folder** (**Browse…**, or drop a folder on the page) and an **Output folder**, then click **Run Batch**. Every `*.pdf` directly in the input folder is listed and processed; each file's result appears beside it.

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

Enter the text, then set the font size (18–120 pt), opacity (5–100 %), and colour (**Pick…**). The text is drawn at 45° through the centre of every page and shrunk if needed to fit inside the page.

### 5.10 Normalise Pages

Choose a target size (A4, A3, A5, Letter, Legal, Tabloid), an orientation (Portrait, Landscape, or Keep original), and **Fit** (keep ratio) or **Stretch** (fill page). Each page is redrawn onto a new page of that size.

### 5.11 Password

The page has two groups.

- **Add / Change Password:** enter an open (user) password, optionally an owner password, and turn off **Allow printing** or **Allow copying text** to deny those rights, then click **Protect PDF**. A blank owner password is replaced by a random one, so the open password alone does not lift the restrictions. To change the password of an already-protected PDF, also enter its current password in the **Remove Password** group's **Current password** field.
- **Remove Password:** enter the current password and click **Remove Password** to save an unencrypted copy.

The password fields are emptied when the job ends and when you leave the tool.

> ⚠️ **Warning:** Without the password the file cannot be opened. PaperKnife+ PC cannot recover lost passwords.

### 5.12 Crop / Trim

Enter how much to cut from each edge, in points (72 pt = 1 inch = 25.4 mm), and optionally a page range (blank = all pages). Turn on **Reset to full media box first** to undo earlier crops. Margins are measured on the page as displayed, also on rotated pages. There is no preview.

### 5.13 Header / Footer

Choose one of six positions on the page outline (top or bottom; left, centre, or right), enter the text — `{page}`, `{total}`, and `{date}` are replaced — and set the font (Helvetica, Times Roman, Courier), size, margin in points, and an optional page range.

### 5.14 PDF Tools

**Repair** opens the file (MuPDF rebuilds a damaged cross-reference table while opening) and saves a cleaned copy. The message says whether damage was found. Pages that cannot be recovered are lost.

### 5.15 OCR

Runs Tesseract on each page to make scanned PDFs searchable and copy-pasteable. Requires Tesseract (see Section 4.3).

- **Language code:** must match the document language. It starts with the code from Preferences; change it per run.
- **Render DPI:** higher values give better accuracy at the cost of time; it starts at the Preferences DPI (limited to 72–400). 300 DPI is recommended for standard documents.
- **Overlay** (invisible text layer): the original page is kept unchanged and the recognised words are added on top as invisible text. Words Tesseract recognises with low confidence are left out.
- **Text-only PDF:** a new PDF with the recognised plain text on A4 pages, without the page images.

### 5.16 Edit Text

Open a PDF, click a text block, edit it in the panel at the right, and click **Apply Edit**. The new text is wrapped to the block's width and drawn in the block's font when that is one of the PDF built-in fonts, otherwise in Helvetica (the status line says so), so the typeface may change. `Ctrl+Z` or the rail's **Undo** undoes the last edit; **Save** or `Ctrl+S` writes the file.

### 5.17 Find & Replace

Enter the text to find in the panel, click **Find All** (or press `Enter`), and step through matches with **◀ Prev / Next ▶**. **Replace All** replaces every match on all pages. Matching is case-sensitive, and a phrase broken across a line counts as one match. `Ctrl+Z` undoes the last Replace All; **Save** or `Ctrl+S` writes the file.

### 5.18 Annotate

Pick one of seven tools on the rail — **Highlight**, **Underline**, **Strikeout**, **Rectangle**, **Line**, **Note**, **Text box** — and drag (or click) on the page. **Note** and **Text box** use the text in the panel's **Text** field. Set **Colour** (**Choose**; not for Note) and **Opacity** (10–100 %; not for Note or Text box) before drawing, and **Zoom** to change the view. Click an existing annotation to select it, then **Remove** in the panel (or `Delete`) to delete it; the rail's **Undo** (or `Ctrl+Z`) removes the last annotation you added. Click **Save** to write the file.

### 5.19 Redact

Choose **Draw box** on the rail and drag boxes over content, or choose **Find & redact text**, type an exact phrase and click **Mark all** to mark every occurrence in the document. Choose a **Black** or **White** fill. The panel lists the pending boxes: **Remove** (or `Delete`) drops the selected one, and the rail's **Undo last** (or `Ctrl+Z`) the last one added. **Apply and save** asks for confirmation and a file name, then permanently removes the text, image pixels and drawings under the boxes, plus any annotations or form fields they touch. A drawing that crosses a box edge — a table border, a chart line, a signature, a logo — is cut at the edge: the part inside the box is destroyed and the part outside stays as it was. If a page's drawings cannot be read reliably, every drawing a box touches is removed whole instead, and the status bar says so. If even that cannot empty the boxes (a gradient mesh, a soft mask), the page is replaced by an image of itself and a warning says its text is no longer selectable. On save, each redacted phrase is also removed from the document properties, XMP metadata, bookmark titles, annotations, form fields, and attachments, and the message lists what was changed.

### 5.20 Metadata

Shows Title, Author, Subject, Keywords, Creator, Producer, Creation date, and Modified date. Dates are entered as `YYYY-MM-DD` (optionally with `HH:MM[:SS]`) or as a PDF date (`D:…`). **Clear all fields** empties them; **Save** (or `Ctrl+S`) writes a copy and drops the old XMP metadata when anything changed.

### 5.21 Image → PDF

Add JPG, PNG, WEBP, BMP, TIFF, or GIF images with **Add Images** (or drop them on the list), order them with **Up / Down** (or `Alt+Up` / `Alt+Down`), and click **Convert to PDF**. Each image becomes one page of its own size, upright according to its EXIF orientation; transparency is flattened onto white.

### 5.22 PDF → Images

Every page is rendered as a PNG at the chosen DPI (72–300, starting at the Preferences DPI) and saved into one ZIP file with **Export as ZIP**.

### 5.23 Extract Images

Saves every embedded image of at least the **Minimum dimension** (default 50 px) to a folder, in its original format (**Keep original**) or converted to PNG or JPEG.

### 5.24 PDF → Doc / Text

Choose the output format: TXT, HTML, XML, RTF, DOCX (needs python-docx), PPTX (page pictures on slides; needs python-pptx), XLSX (one sheet per page; needs openpyxl), or PNG / JPEG (pages in a ZIP, with DPI and, for JPEG, quality). Click **Convert PDF**.

### 5.25 Doc / Text → PDF

Choose the input format (it is set automatically from the file extension when you pick or drop a file): TXT, HTML, XML, RTF, DOCX, PPTX, XLSX, PNG, or JPEG. Text formats are typeset on A4 pages; DOCX keeps headings and tables; PPTX gives one page per slide's text; XLSX is laid out as plain-text tables on landscape A4. Click **Convert to PDF**.

### 5.26 Preferences

| Setting | Used by |
|---|---|
| Default output folder | The starting folder of every save and output-folder dialog |
| Max recent files shown | Number of cards on the Home screen (1–50) |
| Colour mode | light, dark, or system (Section 4.2) |
| Default DPI (OCR / export) | Starting DPI of OCR, Batch → OCR, PDF → Images, and the PNG/JPEG/PPTX exports (72–600; each slider clamps it to its own range) |
| Default compress level | Starting level of Compress and Batch → Compress |
| OCR language code | Starting language of OCR and Batch → OCR |

Click **Save Preferences** (or `Ctrl+S`) to keep changes; **Restore defaults** resets them after asking.

---

## 6. Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + O` | Open: choose the file of the current tool; add files in Merge and Image → PDF; choose the input folder in Batch |
| `Ctrl + S` | Save in Rotate & Reorder, Bookmarks / TOC, Edit Text, Find & Replace, Annotate, Redact (**Apply and save**, after confirmation), Metadata, and Preferences; other tools ignore it |
| `Ctrl + Z` | Undo in Edit Text, Find & Replace, Annotate, and Redact |
| `Delete` | Remove the selected file (Merge, Image → PDF), annotation (Annotate), pending box (Redact), or bookmark (Bookmarks / TOC); ignored while typing in a field |
| `Alt + Up` / `Alt + Down` | Move the selected file up / down in Merge and Image → PDF |
| `Ctrl + K` | Focus the navigation search box |
| `Ctrl + F` | Focus the navigation search box |
| `Enter` (in the search box) | Open the first matching tool |
| `Escape` | Clear the navigation search |
| `Ctrl + Alt + S` | Collapse or expand the navigation pane |
| `Ctrl + Alt + C` | Compact Mode on / off (Section 4.1) |
| `Ctrl` + mouse wheel | Zoom in Read / Preview, Edit Text, Find & Replace, Annotate, and Redact |

While a job holds the page (Section 4.1), `Ctrl+O`, `Ctrl+S`, `Ctrl+Z`, `Delete`, `Ctrl+K`, `Ctrl+F`, `Ctrl+Alt+S` and `Ctrl+Alt+C` are ignored.

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
| Dropping a file does nothing, or the status line says "This tool does not open …" | Each tool takes only its own kind of input: PDFs in most tools, images in Image → PDF, the formats of Section 5.25 in Doc / Text → PDF, and a folder (not files) in Batch. Drops are ignored while a job holds the page. |
| OCR says Tesseract was not found | Install it in its default folder, or add its folder to PATH and check with `tesseract --version` in Command Prompt. See Section 4.3. |
| Dark mode not applying on restart | Save preferences via the Preferences panel after changing the colour mode. |
| A password-protected PDF will not open | Every single-file tool asks for the open password. Batch cannot stop to ask, so it skips protected files with an error: remove the password first with the Password tool (Section 5.11). |
| Windows SmartScreen warning on first run | Click **More info → Run anyway**. The warning disappears once the certificate gains reputation. |
| Application does not start | Check Windows Event Viewer (`eventvwr.msc`) under **Windows Logs → Application** for an error from `PaperKnifePlusPC.exe`. |
| Blurry UI on HiDPI display | The app is Per-Monitor v2 DPI-aware by manifest. If blurring persists, right-click the shortcut → **Properties → Compatibility** → change high DPI settings to **Application**. |

---

## 9. Building from Source (developers)

### 9.1 Prerequisites

- Python 3.10 or later (PySide6 6.12 installs on Python 3.10 to 3.15).
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
4. Create a clean virtual environment **inside the project folder** (the path is relative — it lands at `C:\Build\PaperKnifePlusPC\buildvenv\`, not in your user profile):
   ```
   python -m venv buildvenv
   buildvenv\Scripts\activate
   ```
5. Install application and build dependencies into the venv — the Fluent packages with `--no-deps`, as in Section 3.3:
   ```
   pip install -r requirements.txt pyinstaller==6.22.3
   pip install --no-deps -r requirements-fluent.txt
   ```
   This installs `PySide6-Essentials==6.12.0`, `PySide6-Fluent-Widgets==1.11.3`, `PySideSix-Frameless-Window==0.8.2`, `darkdetect`, `pywin32`, PyMuPDF, Pillow and the optional OCR and conversion packages. Do not install `PySide6` itself: it adds Addons, WebEngine and Pdf to the bundle.
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
   - `dist\PaperKnifePlusPC\PaperKnifePlusPC.exe` — standalone folder bundle (always produced if PyInstaller succeeds), with the bundled packages' licence files in `dist\PaperKnifePlusPC\licenses\`
   - `PaperKnifePlusPC-4.0.0-Setup.exe` — NSIS installer in the project root (only produced if NSIS is installed)

### 9.3 Build Pipeline Summary

| Step | Tool | What it does |
|---|---|---|
| 1 | `rmdir` | Removes `dist\PaperKnifePlusPC\` and `build\` from previous runs |
| 2 | PyInstaller | Bundles Python runtime + Qt 6 + app into a one-dir EXE (`paperknife.spec`, entry script `paperknife/__main__.py`); excludes tkinter, customtkinter and tkinterdnd2 |
| 3 | signtool | Signs the EXE and every bundled `.dll` and `.pyd` with SHA-256 Authenticode + RFC 3161 timestamp; any failure stops the build |
| 4 | makensis | Compiles the NSIS script into the Setup EXE |
| 5 | signtool | Signs the installer EXE |

> ℹ️ **Note:** Steps 3 and 5 are skipped if no certificate is provided or if `signtool.exe` cannot be located in the Windows SDK. The build continues and produces an unsigned package suitable for local testing.

---

## 10. Privacy and Security

PaperKnife+ PC makes zero network connections. There is no telemetry, no analytics, no crash reporting, and no update check. The following data is stored locally only:

- `prefs.json` — your preferences (Section 5.26), the last window size and position, and the paths of temporary files a job interrupted by quitting left behind, which are deleted at the next start.
- `recent.json` — recently opened files: path, file name, size, page count, and access time.

Apart from the operation you invoke, the only file content read is the first page of each recent file, rendered as a thumbnail on the Home screen (kept in memory only). Neither file holds a password: an open password stays with the open document only (Section 5). Deleting `%USERPROFILE%\.paperknifepluspc\` removes all application data completely.

---

## 11. Changelog

### v4.0.0 — current

- **Changed:** the interface moves from CustomTkinter to PySide6 (Qt 6) with QFluentWidgets, in the Windows 11 Fluent style: a navigation pane with the tools in groups and a search box; document workspaces (tool rail, page, context panel) for Read / Preview, Edit Text, Find & Replace, Annotate and Redact; settings-style cards for the single-file tools; the main action at the top right of every page.
- **Changed:** Windows neutrals with an Oxford blue accent as the colour scheme; its text colours meet WCAG AA contrast (4.5:1) in light and dark mode.
- **Changed:** every coloured status line starts with ✓, ⚠ or ✗, so its state is not told by colour alone.
- **Changed:** drag and drop is built into Qt; `tkinterdnd2` is no longer needed.
- **Changed:** the password of a protected input is kept on the open document only and asked again each time it is opened; a new PDF written from it asks whether to keep the password. The Password tool empties its fields after each job.
- **Changed:** `Ctrl+S` always means save; tools whose main action is not a save, such as Split, ignore it (Section 6).
- **New:** Compact Mode (`Ctrl+Alt+C`), navigation pane toggle (`Ctrl+Alt+S`), auto-hiding title bar; the window's place and maximized state are restored.
- **Unchanged:** the same 26 tools, and the same `prefs.json` and `recent.json`.
- **Removed:** the `customtkinter` and `tkinterdnd2` dependencies.

### v3.2.2

- **Fixed:** Redact, Edit Text, Find & Replace and Annotate crashed as soon as they were opened.
- **Fixed:** Redact missed content on rotated pages and left the redacted words in the document properties, XMP, bookmarks, notes, form fields and attachments.
- **Fixed:** Doc / Text → PDF never finished and kept writing pages; Watermark failed on every page.
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

- **Fixed:** the app did not start because of a wrong `PasswordTool` import in `tools/__init__.py`.
- **Fixed:** internal tool errors were swallowed without a message.
- **Fixed:** Undo in Edit Text did not restore the previous text.
- **Fixed:** editing multi-line paragraphs pushed text off the page; text is now wrapped to the width of the original block.
- **Fixed:** special characters (`<`, `&`, …) in OCR and converted text corrupted the output.
- **Fixed:** XML export of multi-page PDFs produced invalid files (repeated XML prologues).
- **Fixed:** three Preferences (output folder, maximum recent files, compression level) were saved but ignored.
- **Fixed:** opening a corrupt or invalid PDF in 8 tools crashed without an error message.
- **Fixed:** Merge reopened every source file a second time after merging.
- **Fixed:** PPTX, XLSX, PNG and JPEG → PDF showed no completion dialog.
- **Fixed:** entries with an invalid schema in `recent.json` crashed the app at start-up.
- Version numbers in `setup.py` and `setup.bat` were set to 3.2.1; `paperknife/theme.py`, which the window shows, stayed at 3.0.0 until 3.2.2.

---

## 12. License

PaperKnife+ PC is distributed under the **GNU Affero General Public License v3.0** (see `LICENSE`), the licence of the PyMuPDF engine it bundles. The PaperKnife+ Android app it is modelled on is GPL-3.0-or-later, which is compatible. The AGPL-3.0 is also compatible with the GPL-3.0 and LGPL-3.0 components below. Bundled third-party components (versions and notices: `THIRD-PARTY-NOTICES.md`):

| Library | License | Purpose |
|---|---|---|
| PyMuPDF (fitz, with MuPDF) | AGPL-3.0 | PDF rendering and manipulation |
| Qt 6 / PySide6-Essentials | LGPL-3.0 | User interface toolkit and its Python binding |
| Shiboken6 | LGPL-3.0 | Binding runtime for PySide6 |
| PySide6-Fluent-Widgets | GPL-3.0 | Fluent-style widgets |
| PySideSix-Frameless-Window | LGPL-3.0 | Frameless window frame |
| darkdetect | BSD-3-Clause | Reads Windows' light / dark setting |
| pywin32 | PSF | Windows API access for the window frame |
| Pillow | MIT-CMU | Image processing |
| pytesseract | Apache-2.0 | Tesseract OCR bridge |
| python-docx | MIT | DOCX conversion |
| python-pptx | MIT | PPTX conversion |
| openpyxl | MIT | XLSX conversion |
| et_xmlfile | MIT | XML writing for openpyxl |
| lxml | BSD-3-Clause | XML parsing for python-docx and python-pptx |
| XlsxWriter | BSD-2-Clause | XLSX writing (python-pptx dependency) |
| typing_extensions | PSF-2.0 | Typing backports (python-docx and python-pptx dependency) |
| striprtf | BSD-3-Clause | RTF → text |

Qt, PySide6 and Shiboken6 are dual-licensed (LGPL-3.0, GPL-2.0, GPL-3.0, or commercial) and used here under the LGPL-3.0. The LGPL Qt libraries are shipped as separate DLLs in the install folder, so they can be replaced; their source is at https://download.qt.io/official_releases/qt/ and https://code.qt.io/. The licence texts are in the install folder's `licenses` folder.

**What the AGPL asks:** anyone who distributes the application, modified or not, must offer its complete source under the same licence.

---

*PaperKnife+ PC v4.0.0 · github/potatameister · 100% local, no cloud, no tracking*
