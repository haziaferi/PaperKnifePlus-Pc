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

On first launch the Home page shows **Open PDF…** and seven quick-action buttons (Read / Preview, Merge, Split, Password, Compress, Annotate, OCR) and an empty Recent files grid. **Open PDF…** opens the chosen file in Read / Preview. Click a recent file to open it in Read / Preview; **Clear history**, beside the Recent files heading, empties the list. A PDF dropped on Home also opens in Read / Preview.

The navigation pane on the left lists Home, then the tools in labelled groups (Read, Organise, Enhance, Convert, Content), with Preferences at the bottom; Home and Preferences are in no group. Click a group's title (or press `Enter` or `Space` on it) to fold its tools under it, and again to unfold them; the chevron at the title's right points down when the group is open and right when it is folded. Folded groups stay folded at the next start. The search box at its top filters tools by name (`Ctrl+K` or `Ctrl+F`), folded groups included, and clearing it folds them again; `Enter` opens the first match. Opening a tool from the search, a Home quick action or a file dropped on Home unfolds its group. The pane is expanded when the window is at least 900 px wide; `Ctrl+Alt+S` collapses or expands it. Collapsed to icons, it shows every tool's icon.

Every tool page has its title at the top left and its main action (the accent button) at the top right. Under the pages, the status line reports the last result; a coloured line starts with ✓ (done), ⚠ (warning) or ✗ (error). While a job runs, a progress bar with **Cancel** appears above the status line; a job that works on the document a page shows holds that page and the navigation until it ends.

**The current document.** The app holds one current document. Opening or dropping a PDF anywhere, opening a recent file, and a tool's **Open** make it current, and every tool that works on one PDF shows it when you open that tool. Such a tool has the document bar under its title: **Open**, whose main part opens the file dialog and whose arrow lists the recent files, then **Browse…**; a chip with the file's name (whole when the row has room, else shortened in the middle; the full path in its tooltip) and **✕** (Clear), which lets the document go; then, while a document is open, **Save**, whose arrow holds **Save as…**, and **Print**. With no document, the page shows a dashed target, "Drop a PDF here or click to choose one": a click on it (or `Enter` or `Space`) opens the file dialog. In the single-file tools it sits above the options; in the workspaces it takes the page's place.

**One document per window.** Every tool works on the same open document, and its edits pile up, unsaved, until you save: turn a page in Rotate & Reorder, apply a watermark, add a note in Annotate, and each tool shows the others' edits. Moving to another tool asks nothing. The title bar names the file, with `*` while it holds unsaved edits ("report.pdf* — PaperKnife+ PC"). **Save** (`Ctrl+S`, or the document bar's **Save**) writes the document over its file; **Save as** (`Ctrl+Shift+S`, or **Save as…** under the arrow of **Save**) asks for a new name, and the document belongs to that file from then on; **Print** (`Ctrl+P`, or the document bar's **Print**) opens Windows' print dialog, with a page range, and prints the document as it is, unsaved edits included. `Ctrl+Z` (or a tool's **Undo**) takes back the document's last edit, whichever tool made it; undoing back to the last save makes it clean again, and the edits stay undoable after a save (up to ten steps). Opening another file, **✕**, **Start over** and closing the window ask "Save changes to *name*?" with **Save** (the step goes on once the file is saved), **Discard** and **Cancel**; the new file is opened first, so one that cannot be opened (a wrong password, a damaged file) asks nothing and changes nothing. Input typed in a tool and not applied yet (Metadata's fields, the bookmark list) counts as unsaved too: their **Apply** makes it an edit of the document, and Save applies it first.

Read / Preview, Edit Text, Find & Replace, Annotate and Redact open as a document workspace: a tool rail at the left (not in Read / Preview), the page in the centre with page arrows and **Zoom** under it, and a context panel at the right. Drag the panel's edge to resize it (220–480 px), double-click the edge or use the panel's hide / show buttons to toggle it.

Edit Text, Find & Replace, Annotate and Redact also show the document's pages as thumbnails in a strip between the rail and the page. Click a thumbnail to go to its page; `Ctrl`- or `Shift`-click to select several; drag thumbnails to move those pages. **Pages** in the rail shows **Rotate left**, **Rotate right** and **Delete** for the selected pages in the panel; choosing another tool in the rail brings its panel back. **Delete** asks first, and is off while every page is selected (a PDF keeps at least one page). Page changes are edits of the document like any other: the rail's **Undo** and `Ctrl+Z` take back the last one (in Redact, a box drawn later comes off first), and **Save** writes the pages in their new order with the edits. The strip resizes like the panel (120–240 px) and closes with its hide button, a double-click on its edge, or a drag below its narrowest; the button at the left of the page arrows opens it again. Whether it is open is remembered.

**Compact Mode** (`Ctrl+Alt+C`) hides the navigation pane, the page header and the context panel; moving the pointer to the left, top or right edge of the window brings each back. The title bar hides and comes back when the pointer reaches the top edge (set the environment variable `PK_TITLEBAR=always` to keep it shown). The window's size, position and maximized state are restored at the next start.

**Crash recovery.** While the document holds unsaved edits, or a tool holds marks or typed input beside it (Redact's boxes, Metadata's fields, the bookmark list), PaperKnife+ PC keeps one copy of them in its data folder (Section 7), refreshed within 10 seconds of a change. Saving, **Discard** and a normal exit remove the copy. If the app closes without that — a crash, a power cut, the process ended — the next start asks **Recover unsaved changes?** with the file, the tool it was being edited in and the time of the copy: **Recover** opens the document with the edits shown as unsaved, in that tool, with the marks and typed input back; **Discard** deletes the copy. Closing the question asks it again at the next start. The copy holds the whole document, so it comes back even if the file was moved or deleted since (Save then writes it there again); the copy of a password-protected PDF keeps its password, which is asked again on Recover.

**Saving over the open file.** When you Save and every edit since the file was opened or last saved only adds to it — comments added in Annotate, bookmarks added in Bookmarks / TOC, empty properties filled in Metadata (in a file without XMP), pages turned or moved in Rotate & Reorder or a page strip — the changes are appended to the file: the bytes already in it stay as they are, so a digital signature over them remains valid, and a large file is not written again. Any edit that removes or replaces content — a deleted comment or page, a renamed or deleted bookmark, a changed or cleared property, Edit Text, Find & Replace, an undo, any tool applied to the whole document (Compress, Watermark, Crop / Trim, …) — writes the file whole, so the old text does not stay readable inside it. A password-protected file, a protection set or removed with Password, and Save as are always written whole. While a change is appended, a copy of the file (`.name-….pdf.bak`) is kept beside it; it is put back if the save fails, and removed when it succeeds.

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
4. The OCR tool, Batch → OCR and Preferences choose the language from a list of the languages Tesseract has installed (Section 5.15). The first time it is Windows' display language when installed, otherwise English; after that, the language of the last OCR run.

---

## 5. Tools Reference

The navigation pane lists 22 tools in five groups, with Preferences at the bottom.

A setting's or panel's description is not shown under its name: click the circled **i** beside the name to see it in a small card, which closes when you click elsewhere. A file path, and a hint on a row without a name, stay in view.

| Group | Tool | What it does | § |
|---|---|---|---|
| Read | Read / Preview | Continuous-scroll, view-only PDF viewer | 5.1 |
| Organise | Merge | Combine PDFs, with optional page ranges per file | 5.2 |
| | Split | Cut a PDF into files at page ranges or bookmarks | 5.3 |
| | Rotate & Reorder | Rotate, move, delete or extract pages on a thumbnail grid | 5.4 |
| | Bookmarks / TOC | Edit the PDF's bookmark (outline) tree | 5.6 |
| | Batch | Compress, Watermark, OCR, or PDF → TXT on every PDF in a folder | 5.7 |
| Enhance | Password | Add, change, or remove an AES-256 password | 5.11 |
| | Compress | Clean and deflate; optionally downsample images | 5.8 |
| | Watermark | Diagonal text watermark on the selected pages | 5.9 |
| | Normalise Pages | Resize the selected pages to a standard paper size | 5.10 |
| | Header / Footer | Stamp page numbers, text, or the date in a margin | 5.13 |
| | Crop / Trim | Cut margins from the crop box | 5.12 |
| | PDF Tools | Repair, sanitise or flatten a PDF; remove its blank pages | 5.14 |
| Convert | Other → PDF | Images and documents, in order, into one PDF | 5.21 |
| | Extract Images | Save the embedded images of the selected pages to a folder | 5.23 |
| | PDF → Other | The selected pages to TXT, HTML, XML, RTF, DOCX, PPTX, XLSX, or PNG / JPEG in a ZIP | 5.24 |
| Content | Edit Text | Edit a text block in place | 5.16 |
| | Find & Replace | Replace text across all pages | 5.17 |
| | Annotate | Highlights, shapes, notes, and text boxes | 5.18 |
| | Redact | Permanently remove content under boxes or matching text | 5.19 |
| | OCR | Make scanned PDFs searchable with Tesseract | 5.15 |
| | Metadata | View and edit document properties | 5.20 |
| (bottom) | Preferences | Output folder, recent files, colour mode, OCR and export DPI, compress level, OCR language | 5.26 |

A tool that works on one PDF uses the current document (Section 4.1): open one with the document bar's **Open** (`Ctrl+O`) or its list of recent files, click the empty page's target, or drop a PDF on the window. Moving to another tool keeps the document and its unsaved edits (Section 4.1). Dropping a file the tool does not take leaves it unchanged and the status line says so.

Compress, Watermark, Normalise Pages, Crop / Trim, Header / Footer, OCR (Overlay), PDF Tools and Password change the open document when you click their main button, **Apply**: no file name is asked, the status line ends "· Save writes it to the file", and `Ctrl+Z` takes the change back. Under **Apply**, the card then shows **✓ Applied · Save now**: **Save now** does what the document bar's **Save** does, and the line goes once the file is saved, undo brings the document back to its saved state, or you choose another tool. Tools that make other files — Merge, Split, Extract Images, PDF → Other, Other → PDF, Batch, Rotate & Reorder's **Extract to a new PDF**, Redact's **Save redacted copy…** and OCR's **Text-only PDF** — ask for a file or folder and read the document as it is, unsaved edits included; the document itself stays as it is.

Merge, Other → PDF and Batch keep their lists (Batch its folders) while you move around; adding files to them does not change the current document, and a finished job empties them.

After a job that writes one new PDF (Merge, Other → PDF, Extract to a new PDF, Redact's Save redacted copy…, OCR's Text-only PDF), a bar at the top of the page says "*name* is ready": **Continue with it** makes the output the current document and shows it in the tool; **Start over** clears the tool and the current document. Opening another tool counts as **Continue with it**. Jobs that write several files (Split, Extract Images, Batch) or a file that is not a PDF (PDF → Other) ask nothing, and the current document stays.

Unsaved edits are never dropped silently: opening another document, **✕**, **Start over** and closing the window ask "Save changes to *name*?" (Section 4.1). Closing the window with redaction boxes drawn and not applied asks "*n* redaction boxes drawn and not applied will be lost. Close anyway?"

Page ranges, where a tool accepts them, are written like `1-3, 5, 8-end`. A range that names a page the document does not have, or runs backwards, is refused with a message before anything is written.

Crop / Trim, Header / Footer, Watermark, Normalise Pages, PDF → Other, Extract Images and OCR show the document's pages as thumbnails in the centre, with the tool's settings in the column at the right. Every page starts selected. Click pages to choose them (`Ctrl` / `Shift` for several, **All pages** for every one); a page left out is veiled. The **Apply to** field in the **Pages** card follows the selection (`all`, or its ranges), and a range typed there selects its pages. With no page selected the main action is off and the bar says "Select at least one page." The tool works on the selected pages only; the others are kept unchanged (PDF → Other and Extract Images write only the selected pages, under their own page numbers).

A password-protected PDF asks for its open password when it is opened. The password stays with the open document only: it is forgotten when the document is closed, and asked again the next time. Save over the file keeps the password without asking. When a new PDF is written from a document opened with a password (Save as, or a tool that makes a new file), the app asks whether the new file keeps it; Merge asks only when every protected input has the same open password.

### 5.1 Read / Preview

A view-only viewer of the current document: open a PDF with the document bar's **Open**, `Ctrl+O` or the empty page's target, scroll through all pages continuously, and change the size with the **Zoom** slider (50–300 %) or `Ctrl` + mouse wheel. The strip under the pages shows which pages are in view; its arrows jump one page.

A newly opened file whose widest page does not fit the view (a landscape page) opens zoomed to the width of the view; the zoom is never raised for this, and reopening the same file keeps your zoom. A file whose first pages hold pictures but no text shows a bar, "**Scanned PDF** · No searchable text.", with **Run OCR**, which opens OCR (Section 5.15) on that file; ✕ closes the bar, and it is shown once per file.

### 5.2 Merge

Merge combines PDF files into a single output document; with one file, it writes the pages you keep, in the order you set, as a new PDF. The centre shows every page of the merged result, in its order, with each file's pages under its name; the file list sits in the column at the right.

- Click **Add PDFs** (or `Ctrl+O`) to add files, or drop PDFs onto the page. A file is read when it is added (a protected one asks for its password once).
- Select pages in the strip and click **Leave out** to leave them out of the merge (they stay in place, veiled) or **Put back** to include them again. Drag pages to a new place, also between files: the strip's order is what is merged.
- Click a file in the list, then use **Up / Down** (or `Alt+Up` / `Alt+Down`) to move it, which gathers its pages together, or **Remove** (or `Delete`) to remove it.
- A file's range field shows the pages it contributes; typing a range there includes those pages, in that order.
- Click **Merge** and choose an output path. With every page left out, **Merge** is off and the bar says so.

The list stays while you visit other tools and empties after a finished merge.

The merged file has a top-level bookmark for each input, named after its file, with that file's own bookmarks under it, and takes the document properties (title, author, subject, keywords, XMP) of the first file. Pages are numbered 1 to N; the inputs' own page labels are not kept. Each input's form fields, comments, links, layers and attachments come along; a link to a named destination becomes a link to its page. A page range leaves out the bookmarks to the pages it does not include.

### 5.3 Split

Split cuts a PDF into separate files in a folder you choose. The pages are shown as thumbnails; the parts to be written are shaded in two alternating tones, each page labelled with its part ("p.3 · Part 2"), and listed under **Parts** in the column at the right.

- Under **Cut at**, choose **Page ranges**, **Bookmarks, top level** or **Bookmarks, all levels** (the bookmark choices are off for a PDF without bookmarks). With bookmarks, each chosen bookmark starts a file that runs to the next one; bookmarks that point to no page are skipped and counted in the result message.
- In the range field, a semicolon separates files and a comma lists pages within one: `1-3; 4, 6; 7-end` writes three files. Leave it blank to write one PDF per page. The buttons under the field fill it with an example: **Every page**, **Every 2 pages**, **Page 1 apart**.
- Click the gap between two thumbnails to cut there, or click a cut again to join the parts.
- Select pages and click **Selected pages to one part** to make a file of pages from anywhere in the document; the rest of their parts stays as it was.

Each part keeps what belongs to its pages: the bookmarks, form fields, links and page labels that go with them, and the document's properties, XMP, layers and attachments.

### 5.4 Rotate & Reorder

Open a PDF, click a thumbnail to select that page (`Ctrl`- or `Shift`-click to select several), then use **↺ 90° CCW**, **↻ 90° CW**, or **⤢ 180°** to rotate the selection, or **← Move Left / Move Right →** to change its position. A thumbnail can also be dragged to a new place. **Delete** removes the selected pages after asking; it is off while every page is selected. Each turn, move, drag and delete changes the document at once. **Extract to a new PDF** writes the selected pages, as they are, to a new file and leaves the document as it is. **Undo** (or `Ctrl+Z`) takes back the document's last edit. **Save** in the document bar (or `Ctrl+S`) writes the document over its file; it keeps its bookmarks, form fields, links, layers, properties and XMP, and each page keeps its page label.

### 5.5 Split by Bookmarks

Split by Bookmarks is now part of Split (Section 5.3): choose a bookmark level under **Cut at**.

### 5.6 Bookmarks / TOC

An editor for the PDF's bookmark (outline) tree. Select an entry, change its **Level** (1–4), **Title**, or **Page** in the column at the right and click **Update selected**; use **Add below**, **Up**, **Down**, and **Delete** above the list. **Apply** applies the list to the document, after checking that the levels nest correctly, as one edit `Ctrl+Z` takes back; until then the list is input typed here, and **Save** (or `Ctrl+S`, or Save as) applies it first (Section 4.1). It does not create a table-of-contents page.

### 5.7 Batch

Choose an **Operation**, an **Input folder** (**Browse…**, or drop a folder on the page) and an **Output folder**, then click **Run Batch**. Every `*.pdf` directly in the input folder is listed and processed; each file's result appears beside it.

- **Compress** — the levels of Section 5.8. Output `<name>_compressed.pdf`.
- **Watermark** — text, size, and opacity; the colour is grey. Output `<name>_watermarked.pdf`.
- **OCR** — language and DPI, as in Section 5.15 (overlay mode). Output `<name>_ocr.pdf`.
- **PDF → TXT** — the text of every page. Output `<name>.txt`.

Password-protected files are skipped with an error; open them in the single-file tool instead.

A finished batch, errors included, empties the list and the input folder; the status line keeps the counts. A cancelled batch keeps them, with each file's result.

### 5.8 Compress

Three levels balance quality against file size:

- **Light** — removes unused objects and compresses streams. No image is changed.
- **Medium** — as Light, and embedded images above 150 DPI are resampled to 150 DPI and stored as JPEG at quality 80 when that makes them smaller.
- **Aggressive** — as Medium, at 96 DPI.

Text and vector content are kept in every level. **Compress** changes the open document and the status line gives the sizes before and after; if the result would not be smaller, the document is left as it was and a warning says so. The starting level comes from Preferences.

### 5.9 Watermark

Enter the text, then type the font size (18–120 pt) and opacity (5–100 %), or step them with the box's arrows, and choose the colour (**Pick…**). The text is drawn at 45° through the centre of each selected page and shrunk if needed to fit inside the page.

### 5.10 Normalise Pages

Choose a target size (A4, A3, A5, Letter, Legal, Tabloid), an orientation (Portrait, Landscape, or Keep original), and **Fit** (keep ratio) or **Stretch** (fill page). Each selected page is redrawn onto a new page of that size; the others are kept as they are.

### 5.11 Password

**Current password** comes first: fill it in only for a file that already has a password, since both changing and removing that password need it.

- **Remove Password:** the button right under **Current password** saves the file without a password.
- **Add / Change Password:** enter an open (user) password, optionally an owner password, and turn off **Allow printing** or **Allow copying text** to deny those rights, then click **Apply** at the top of the card. A blank owner password is replaced by a random one, so the open password alone does not lift the restrictions.

Both set the document's protection, as one edit `Ctrl+Z` takes back: **Save** or **Save as** writes the file with it (the status line says so), and later saves keep it. A protected PDF is opened with its password (Section 5), so changing its password asks for nothing more; removing it asks for the current password in **Current password**. A file with an owner password only (none to open it) is changed without asking for the owner password, as before.

The password fields are emptied after every attempt, whatever came of it, and when you leave the tool.

> ⚠️ **Warning:** Without the password the file cannot be opened. PaperKnife+ PC cannot recover lost passwords.

### 5.12 Crop / Trim

Enter how much to cut from each edge, in millimetres, or in points if you set **Unit** to pt (72 pt = 25.4 mm; switching the unit converts the values already typed), and choose the pages on the grid or in **Apply to**. Turn on **Reset to full media box first** to undo earlier crops. Margins are measured on the page as displayed, also on rotated pages. There is no preview.

### 5.13 Header / Footer

Choose one of six positions on the page outline (top or bottom; left, centre, or right), enter the text — `{page}`, `{total}`, and `{date}` are replaced; the buttons under the field (**Page n of N**, **Page n**, **Today's date**) fill it with an example — and set the font (Helvetica, Times Roman, Courier), size and margin in points (number boxes); choose the pages on the grid or in **Apply to**.

### 5.14 PDF Tools

Choose a tool under **Tool**, then click **Apply**; the circled **i** beside a tool's name shows what it does in a small card, until you click elsewhere. Each changes the open document; Save writes it whole, so what it removed does not stay inside it.

- **Repair** uses the file as MuPDF opened it (it rebuilds a damaged cross-reference table while opening) and cleans it, without compressing its images. The status line says whether damage was found. Pages that cannot be recovered are lost.
- **Sanitise** removes, as its switches choose (all on): **JavaScript** (the document's scripts and those of its links and fields), **Embedded files** (attachments and file-attachment comments), **XMP metadata**, and **Links that run actions** (launch a program or a file). Web links and what the pages show are kept. The message lists what was removed.
- **Flatten** draws **Comments** and **Form fields** (switches, both on) into the pages, so they can no longer be edited; a field's value becomes page content.
- **Remove blank pages** finds the pages with no text, no drawing that shows, no comment and no form field, names them in a question, and removes them once you confirm. A scanned page counts when it shows only empty paper: white, cream or grey paper, or the back's text faintly showing through. A page with any mark on it, even a page number, a tick or a few specks of dust, is kept. It says so when no page is blank, and keeps at least one page.

### 5.15 OCR

Runs Tesseract on each selected page to make scanned PDFs searchable and copy-pasteable. Requires Tesseract (see Section 4.3).

- **Language:** the button names the chosen languages ("Italian + English"); click it for a ticked list of the languages Tesseract has installed (page orientation and maths data are left out). Tick every language the text uses and only those: an extra language can make Tesseract read some words worse. The first ticked one leads, and at least one stays ticked. The list starts with Windows' display language the first time, then with the language of the last run; Preferences sets it too.
- **Render DPI:** a number box; it starts at the Preferences OCR DPI, 200 by default (limited to 72–400). Measured on simulated scans (2026-10-22), 200 read best: at 150 Tesseract skipped rows of small text, and at 300 text grew too big for it and fewer words were read.
- **Overlay** (invisible text layer): the recognised words are added to the open document's pages as invisible text, the pages otherwise unchanged. Every recognised word is kept, however unsure Tesseract is of it: the layer cannot be seen, so a misread word costs nothing, and a word left out could not be found. Each word fills the place of the printed one, so selecting it highlights the printed word.
- **Text-only PDF:** the main button reads **Text-only PDF from OCR** (with **Overlay** it reads **Apply**): a new PDF (it asks for a file name) with the recognised plain text on A4 pages, without the page images; the document stays as it is. Words Tesseract is unsure of (confidence below 40) are left out; lines and paragraphs break as on the page.
- **Pages scanned sideways or upside down** are found and read upright; their words are placed where the page shows them. The page itself is not turned. A page with too little text for Tesseract to tell is read as it is. This takes about one second more per page, which reading in grey wins back.
- **Pages are read in grey:** on simulated scans (clean, faded, cream paper, shaded, blue ink, receipts; 2026-11-01) as many words as from the colour page, 0.7–1.1 s a page sooner. The grey is not contrast-stretched: on a page of a single line the stretch turned the paper's grain into black specks and no word was read.

### 5.16 Edit Text

Open a PDF, click a text block, edit it in the panel at the right, and click **Apply Edit**. The new text is wrapped to the block's width and drawn in the block's font when that is one of the PDF built-in fonts, otherwise in Helvetica (the status line says so), so the typeface may change. `Ctrl+Z` or the rail's **Undo** undoes the last edit; **Save** in the document bar (or `Ctrl+S`) writes the file.

### 5.17 Find & Replace

Enter the text to find in the panel, click **Find All** (or press `Enter`), and step through matches with **◀ Prev / Next ▶**. **Replace All**, under **Find All** on the card, turns on once a search has found matches of the text in **Find** (typing other text turns it off again) and replaces every match on all pages. Matching is case-sensitive, and a phrase broken across a line counts as one match. `Ctrl+Z` undoes the last Replace All; **Save** in the document bar (or `Ctrl+S`) writes the file.

### 5.18 Annotate

Pick one of seven tools on the rail — **Highlight**, **Underline**, **Strikeout**, **Rectangle**, **Line**, **Note**, **Text box** — and drag (or click) on the page. A Highlight, Underline or Strikeout dragged straight along a line of text takes the height of that line; dragged along empty paper it adds nothing and the status line says so. **Note** and **Text box** use the text in the panel's **Text** field. Set **Colour** (**Choose**; not for Note) and **Opacity** (a number box, 10–100 %; not for Note or Text box) before drawing, and **Zoom** to change the view. Click an existing annotation to select it, then **Remove** in the panel (or `Delete`) to delete it; the rail's **Undo** (or `Ctrl+Z`) removes the last annotation you added. **Save** in the document bar (or `Ctrl+S`) writes the file.

### 5.19 Redact

Choose **Draw box** on the rail and drag boxes over content, or choose **Find & redact text**, type a phrase and click **Mark all** to mark every occurrence in the document, in any mix of capitals (so nothing is missed; Find & Replace, by contrast, matches the capitals as typed). Choose a **Black** or **White** fill. The panel counts the pending boxes and lists them, up to five rows before the list scrolls (with none, there is no list and **Remove** is off); **Remove** sits above the list, so it stays in place as the list grows or shrinks: **Remove** (or `Delete`) drops the selected one, and the rail's **Undo last** (or `Ctrl+Z`) the last one added. The boxes are marks beside the document, not edits of it: Save does not keep them, and closing the window with boxes not applied warns first. **Save redacted copy…** asks for confirmation and a file name (not the file open here), then writes a new redacted copy, with the text, image pixels and drawings under the boxes permanently removed, plus any annotations or form fields they touch; the document open here and its boxes stay as they are. Cancel writes nothing. A drawing that crosses a box edge — a table border, a chart line, a signature, a logo — is cut at the edge: the part inside the box is destroyed and the part outside stays as it was. If a page's drawings cannot be read reliably, every drawing a box touches is removed whole instead, and the status bar says so. If even that cannot empty the boxes (a gradient mesh, a soft mask), the page is replaced by an image of itself and a warning says its text is no longer selectable. On save, each redacted phrase is also removed from the document properties, XMP metadata, bookmark titles, annotations, form fields, and attachments, and the message lists what was changed.

### 5.20 Metadata

Shows Title, Author, Subject, Keywords, Creator, Producer, Creation date, and Modified date. Dates are entered as `YYYY-MM-DD` (optionally with `HH:MM[:SS]`) or as a PDF date (`D:…`). **Clear all fields** empties them. The fields are input typed here until **Apply** (or **Save**, `Ctrl+S`, or Save as, which apply them first) makes them an edit of the document, dropping the old XMP metadata when anything changed, and writes it; `Ctrl+Z` puts the fields back as they were.

### 5.21 Other → PDF

Add images (JPG, PNG, WEBP, BMP, TIFF, GIF) and documents (TXT, HTML, XML, RTF, DOCX, PPTX, XLSX) with **Add Files** (or drop them on the list), order them with **Up / Down** (or `Alt+Up` / `Alt+Down`), and click **Convert to PDF**: they become one PDF, in that order. Each image is one page, upright according to its EXIF orientation, with transparency flattened onto white. A scan's page is the size of the scanned sheet (from the resolution the scanner wrote, 100 DPI or more); any other image, such as a phone photo or a screenshot, is one point per pixel, and a page larger than A4 is scaled down to fit A4, every pixel kept. Each document adds its pages: text formats are typeset on A4 pages; DOCX keeps headings and tables (needs python-docx); PPTX gives one page per slide's text (needs python-pptx); XLSX is laid out as plain-text tables on landscape A4 (needs openpyxl). A file's format comes from its extension. The list stays while you visit other tools and empties after a finished conversion. (Image → PDF and Doc / Text → PDF until 4.0.0.)

### 5.22 (PDF → Images)

PDF → Images is now part of PDF → Other (Section 5.24): choose PNG or JPEG.

### 5.23 Extract Images

Saves every embedded image of the selected pages of at least the **Minimum dimension** (default 50 px) to a folder, in its original format (**Keep original**) or converted to PNG or JPEG.

### 5.24 PDF → Other

Choose the output format for the selected pages: TXT, HTML, XML, RTF, DOCX (needs python-docx), PPTX (page pictures on slides; needs python-pptx), XLSX (one sheet per page; needs openpyxl), or PNG / JPEG (pages in a ZIP, with DPI and, for JPEG, quality). Click **Convert PDF**.

### 5.25 (Doc / Text → PDF)

Doc / Text → PDF is now part of Other → PDF (Section 5.21).

### 5.26 Preferences

| Setting | Used by |
|---|---|
| Default output folder | The starting folder of every save and output-folder dialog. Empty: the folder last used in this session, or else the current document's folder |
| Max recent files shown | Number of cards on the Home screen (1–50) |
| Colour mode | light, dark, or system (Section 4.2) |
| OCR DPI | Starting DPI of OCR and Batch → OCR, 200 by default (72–600; each tool's box keeps it within its own range) |
| Export DPI | Starting DPI of PDF → Other's PNG/JPEG/PPTX exports, 200 by default (72–600) |
| Default compress level | Starting level of Compress and Batch → Compress |
| OCR language | Starting language(s) of OCR and Batch → OCR, from the installed ones; until one is chosen, Windows' display language when installed, else English. Each OCR run sets it to the language it used |

Click **Save Preferences** (or `Ctrl+S`) to keep changes; **Restore defaults** resets them after asking.

---

## 6. Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl + O` | Open: the file dialog for the current document, as the document bar's **Open** (Section 4.1); add files in Merge and Other → PDF; choose the input folder in Batch |
| `Ctrl + S` | Save: the document over its file, from any tool (Preferences: save its settings) |
| `Ctrl + Shift + S` | Save as: the document to a new file it then belongs to |
| `Ctrl + P` | Print the document, with a page range |
| `Ctrl + Z` | Undo the document's last edit, whichever tool made it (in Redact, a box drawn later first) |
| `Delete` | Remove the selected file (Merge, Other → PDF), annotation (Annotate), pending box (Redact), or bookmark (Bookmarks / TOC); ignored while typing in a field |
| `Alt + Up` / `Alt + Down` | Move the selected file up / down in Merge and Other → PDF |
| `Ctrl + K` | Focus the navigation search box |
| `Ctrl + F` | Focus the navigation search box |
| `Enter` (in the search box) | Open the first matching tool |
| `Escape` | Clear the navigation search |
| `Ctrl + Alt + S` | Collapse or expand the navigation pane |
| `Ctrl + Alt + C` | Compact Mode on / off (Section 4.1) |
| `Ctrl` + mouse wheel | Zoom in Read / Preview, Edit Text, Find & Replace, Annotate, and Redact |

While a job holds the page (Section 4.1), `Ctrl+O`, `Ctrl+S`, `Ctrl+Shift+S`, `Ctrl+P`, `Ctrl+Z`, `Delete`, `Ctrl+K`, `Ctrl+F`, `Ctrl+Alt+S` and `Ctrl+Alt+C` are ignored.

Other programs may take a shortcut for themselves before it reaches the app: AMD Software (Radeon) uses `Ctrl+Shift+S` for Instant Replay by default, so Save as does not reach PaperKnife+ PC while it runs; change that program's hotkey to use it here.

---

## 7. File and Data Locations

| Item | Path |
|---|---|
| Application binaries | `%LOCALAPPDATA%\PaperKnifePlusPC\` |
| User preferences, window place, folded navigation groups | `%USERPROFILE%\.paperknifepluspc\prefs.json` |
| Recent files list | `%USERPROFILE%\.paperknifepluspc\recent.json` |
| Copies of unsaved edits (crash recovery, Section 4.1) | `%USERPROFILE%\.paperknifepluspc\recovery\` |
| Add/Remove Programs | `HKCU\Software\Microsoft\Windows\...\Uninstall\PaperKnifePlusPC` |
| App registry key | `HKCU\Software\potatameister\PaperKnifePlusPC` |

To fully remove all application data after uninstalling, delete `%USERPROFILE%\.paperknifepluspc\` manually. The uninstaller intentionally preserves this folder so that recent file history and preferences survive a reinstall.

---

## 8. Troubleshooting

| Symptom | Resolution |
|---|---|
| Dropping a file does nothing, or the status line says "This tool does not open …" | Each tool takes only its own kind of input: PDFs in most tools, images and documents in Other → PDF (Section 5.21), and a folder (not files) in Batch. Drops are ignored while a job holds the page. |
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

- `prefs.json` — your preferences (Section 5.26), the last window size and position, the folded navigation groups, and the paths of temporary files a job interrupted by quitting left behind, which are deleted at the next start.
- `recent.json` — recently opened files: path, file name, size, page count, and access time.
- `recovery\` — while the document holds unsaved edits (or a tool holds marks or typed input beside it), one copy: the edited PDF (under its password when it has one), those marks and typed input, and the file's path. It is deleted when the edits are saved or discarded and at a normal exit; after a crash it stays until the next start's Recover or Discard (Section 4.1).

Apart from the operation you invoke, the only file content read is the first page of each recent file, rendered as a thumbnail on the Home screen (kept in memory only). Neither file holds a password: an open password stays with the open document only (Section 5). Deleting `%USERPROFILE%\.paperknifepluspc\` removes all application data completely.

---

## 11. Changelog

### v4.0.0 — current

- **Changed:** PDF → Images is part of PDF → Other (PDF → Doc / Text renamed), and Image → PDF and Doc / Text → PDF are one screen, Other → PDF, that puts images and documents into one PDF in list order. PDF Tools gains **Sanitise**, **Flatten** and **Remove blank pages** beside **Repair**.
- **New:** the pages are on screen. Merge shows the merged pages in one strip (leave pages out, put them back, drag them between files); Split cuts at page ranges or bookmarks on a thumbnail grid (Split by Bookmarks is now part of it, and `;` separates files in a range); the page-range tools pick their pages on a grid kept in step with the range field (Watermark, Normalise Pages, PDF → Other, Extract Images and OCR gain a page choice); Rotate & Reorder gains **Delete**, **Extract to a new PDF** and **Undo**; Edit Text, Find & Replace, Annotate and Redact gain a page strip to go to, move, turn and delete pages, with one Undo for edits and page changes.
- **Changed:** the interface moves from CustomTkinter to PySide6 (Qt 6) with QFluentWidgets, in the Windows 11 Fluent style: a navigation pane with the tools in groups and a search box; document workspaces (tool rail, page, context panel) for Read / Preview, Edit Text, Find & Replace, Annotate and Redact; settings-style cards for the single-file tools; the main action at the top right of every page.
- **Changed:** Windows neutrals with an Oxford blue accent as the colour scheme; its text colours meet WCAG AA contrast (4.5:1) in light and dark mode.
- **Changed:** every coloured status line starts with ✓, ⚠ or ✗, so its state is not told by colour alone.
- **Changed:** drag and drop is built into Qt; `tkinterdnd2` is no longer needed.
- **Changed:** the password of a protected input is kept on the open document only and asked again each time it is opened; a new PDF written from it asks whether to keep the password. The Password tool empties its fields after each job.
- **Changed:** `Ctrl+S` saves the document from any tool (Section 6).
- **New:** Compact Mode (`Ctrl+Alt+C`), navigation pane toggle (`Ctrl+Alt+S`), auto-hiding title bar; the window's place and maximized state are restored.
- **New:** one current document the single-file tools and the workspaces follow, set by opening or dropping a PDF anywhere, a recent file, or a tool's Open (Section 4.1). A document bar under each such page's title holds **Open** (the file dialog; its arrow lists the recent files, then **Browse…**) and the file's name with **✕**; pages no longer show a file card, except Doc / Text → PDF. Read / Preview and the editing workspaces have no Open button of their own; `Ctrl+O` still opens.
- **New:** a page with no document shows a target, "Drop a PDF here or click to choose one"; a click opens the file dialog.
- **New:** one document per window (owner, 2026-10-23): every tool works on it and its edits pile up, unsaved, across tools; the title names the file with `*` while unsaved; **Save** (`Ctrl+S`) writes over the file, **Save as** (`Ctrl+Shift+S`) to a new one the document then belongs to, **Print** (`Ctrl+P`) with a page range; `Ctrl+Z` undoes the last edit of any tool, and undoing back to the save point is clean again (Section 4.1).
- **Changed:** Compress, Watermark, Normalise Pages, Crop / Trim, Header / Footer, OCR (Overlay) and PDF Tools change the open document instead of asking for a new file; Compress leaves it as it was when no smaller. Password sets the document's protection, written by Save. Rotate & Reorder's turns, moves and deletes, Metadata's fields and the bookmark list apply to the document. Redact's **Save redacted copy…** writes a new redacted copy and the document keeps its boxes; closing with boxes not applied warns.
- **New:** after a job that writes one PDF, "*name* is ready" with **Continue with it** / **Start over**; opening another tool counts as Continue. Jobs with several outputs ask nothing. Merge, Image → PDF and Batch keep their lists while you move around and empty them after a finished job.
- **Changed:** OCR reads pages scanned sideways or upside down (they read as junk before); the invisible text keeps every recognised word, each fitted to the printed word, and Text-only PDF leaves out words Tesseract is unsure of, as measured for ScanKnife+ (owner, 2026-11-01).
- **Changed:** OCR hands Tesseract the page in grey: as many words read, 0.7–1.1 s a page sooner (owner, 2026-11-01).
- **Changed:** every setting's and panel's description opens from a circled **i** beside its name, as PDF Tools' do (Section 5; owner, 2026-11-01).
- **Changed:** OCR's Text-only PDF button reads **Text-only PDF from OCR**; PDF Tools' descriptions open from a circled **i** beside each tool's name instead of lines under it; Redact's **Remove** sits above the pending list and no longer moves; a tool card's input fields share one width, and Header / Footer's size and margin take a row each (owner, 2026-10-31).
- **New:** the instant editors (Annotate, Edit Text, Find & Replace, Rotate & Reorder) have no Save of their own: the document bar's **Save** is the one place; the main button of OCR (Overlay), PDF Tools and Password reads **Apply** too, and OCR's Text-only PDF reads **Text-only PDF from OCR**; OCR's Render DPI and PDF → Other's resolution and JPEG quality are number boxes (owner, 2026-10-23).
- **New:** the document bar has **Save** (its arrow: **Save as…**) and **Print** beside **Open** (owner, 2026-10-23); the main button of Compress, Watermark, Normalise Pages, Crop / Trim, Header / Footer, Metadata and Bookmarks reads **Apply**, and Metadata's and Bookmarks' **Apply** changes the document without writing the file; Watermark's font size and opacity, Batch → Watermark's opacity and Annotate's opacity are typed in number boxes instead of sliders.
- **New:** "Save changes to *name*?" (**Save** / **Discard** / **Cancel**) before the document's unsaved edits are replaced, cleared, or closed with the window; changing tool asks nothing.
- **New:** crash recovery: the document's unsaved edits (with the tools' marks and typed input) are copied while you work, and after a crash the next start asks **Recover unsaved changes?** (**Discard** / **Recover**; Section 4.1).
- **Fixed:** an undo step on a password-protected file let Save append the edits unencrypted; an owner-password file lost its encryption after an edit.
- **New:** an edit that only adds to the file (comments, bookmarks, empty properties, turned or moved pages) saved over that file is appended to it, which keeps digital signatures valid (Section 4.1).
- **Fixed:** a comment deleted in Annotate, and the text replaced in Edit Text or Find & Replace, stayed inside the saved file (no longer shown, but readable by a tool that reads the file's objects); the file is now written without them.
- **New:** navigation groups fold under their title (click, `Enter` or `Space`); the folded groups are kept in `prefs.json`, and a search still finds tools in them.
- **Fixed:** Rotate & Reorder, Split and Split by Bookmarks dropped the form fields (Rotate & Reorder), bookmarks, page labels, layers, document properties, XMP and the links to named destinations; Merge dropped all of them but the form fields. Merge now writes a bookmark per input file (Section 5.2).
- **Fixed:** Password kept a typed password after a cancelled save dialog or a refused attempt; its fields are now emptied at every end of an attempt.
- **New:** OCR's language is chosen from the installed languages, one or several (it was a typed code), starting from Windows' display language and then the last one used; OCR and the image exports each have their own DPI preference, both 200 by default (one shared 150 before; a saved 150 becomes 200, any other saved value is kept for both).
- **New:** a scanned PDF opened in Read / Preview shows "Scanned PDF · No searchable text." with **Run OCR**; a landscape page opens fitted to the view's width.
- **Changed:** a dialog with no folder set or used yet starts in the current document's folder; a Highlight, Underline or Strikeout dragged along a line marks that line; Redact's list of pending boxes is as tall as its boxes; PDF Tools' descriptions are shorter (the full ones are in Section 5.14).
- **Fixed:** a Highlight, Underline or Strikeout dragged straight along a line failed ("bad quads entry"); Redact's "0 boxes pending" was drawn in near-invisible grey.
- **Unchanged:** the same 26 tools, the same `recent.json`, and `prefs.json` but for the DPI and OCR language keys above.
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
