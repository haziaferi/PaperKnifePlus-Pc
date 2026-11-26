# PaperKnife+ PC spec

Scope: the Windows desktop PDF toolkit PaperKnife+ PC 4.x (PySide6 + QFluentWidgets, PyMuPDF), its document model, layout, tools, data and release.

History: `SPEC-history.md`, one line per change. It is never a source of current rules.

Kinds: O owner rule · D decided · I inherited · A assumed · Q open.

## Rule index

| ID | Name | Section |
|---|---|---|
| D-R01 | Jobs and how often | 1. Purpose and jobs |
| D-R02 | Who it is for | 1. Purpose and jobs |
| D-R03 | Windows versions | 2. Platform and release |
| O-R04 | Offline | 2. Platform and release |
| D-R05 | Library pins | 2. Platform and release |
| D-R06 | Installer | 2. Platform and release |
| O-R07 | Uninstall leaves other folders alone | 2. Platform and release |
| D-R08 | Licence and credits | 2. Platform and release |
| D-R09 | Interface languages | 3. Language |
| D-R10 | Date in Header / Footer | 3. Language |
| D-R11 | Italian manual | 3. Language |
| D-R12 | Data folder | 4. Data on disk |
| D-R13 | Recovery folder | 4. Data on disk |
| O-R14 | No password on disk | 4. Data on disk |
| O-R15 | One document per window | 5. The document |
| O-R16 | Save and Save as | 5. The document |
| O-R17 | Append saves | 5. The document |
| D-R18 | Whole writes never leave half a file | 5. The document |
| D-R19 | Unsaved question | 5. The document |
| D-R20 | Undo | 5. The document |
| D-R21 | Undo on large files | 5. The document |
| O-R22 | Crash recovery | 5. The document |
| O-R23 | Apply and new-file verbs | 5. The document |
| O-R24 | Destructive steps make new files | 5. The document |
| D-R25 | Passwords | 5. The document |
| D-R26 | Page ranges | 5. The document |
| Q-R27 | Window layout | 6. Layout |
| O-R28 | Action fixed at the card top | 6. Layout |
| O-R29 | Card collapses, the page keeps clear | 6. Layout |
| O-R30 | Group rail | 6. Layout |
| O-R31 | Document bar and Save after Apply | 6. Layout |
| O-R32 | Card width | 6. Layout |
| O-R33 | Card details | 6. Layout |
| O-R34 | Same place, same size | 6. Layout |
| O-R35 | Colours and status | 6. Layout |
| D-R36 | Start screen | 7. Start and Home |
| D-R37 | Quick actions | 7. Start and Home |
| D-R38 | Recent files never stall Home | 7. Start and Home |
| D-R39 | OCR defaults | 8. Tools |
| D-R40 | OCR page layout and low-confidence warning | 8. Tools |
| D-R41 | Compress levels | 8. Tools |
| O-R42 | Redaction removes, at the box edge | 8. Tools |
| D-R43 | Text rewrite unit | 8. Tools |
| D-R44 | Find & Replace case | 8. Tools |
| D-R45 | Batch input | 8. Tools |
| D-R46 | Save to a file another program holds | 9. Real-world cases |
| D-R47 | File changed on disk while open | 9. Real-world cases |
| D-R48 | Ctrl+S on Preferences | 9. Real-world cases |
| I-R49 | Two windows | 9. Real-world cases |
| D-R50 | Gate | 10. Test plan |
| D-R51 | Release path | 11. Rollout |
| D-R52 | Online features | Out of scope |
| D-R53 | Saving in a helper process | Out of scope |
| D-R54 | Other systems | Out of scope |

## Glossary

| Term | Meaning |
|---|---|
| current document | The one PDF a window holds; every single-file tool works on it |
| unsaved edit | A change to the current document not yet written to its file |
| Apply | A tool's main action that changes the current document in place |
| new-file tool | A tool whose main action writes a new file and leaves the current document as it is |
| append save | A Save that adds the edits after the bytes already in the file |
| whole write | A Save that writes the file again from the start, through a temporary file beside it |
| recovery copy | The copy of unsaved edits kept in the recovery folder for crash recovery |
| recovery folder | The local folder holding recovery copies, never roamed or uninstalled (R13) |
| card | The options panel floating over the page's right edge, with the main action at its top |
| group rail | The 64 px column of tool groups at the window's left |
| page grid | The thumbnails of the current document's pages in the centre of a page tool |
| page range | Text naming pages, written like `1-3, 5, 8-end` |
| data folder | The folder holding preferences and recent files (R12) |
| Files workspace | The place for jobs on several files: Merge, Other to PDF, Batch |

## 1. Purpose and jobs

PaperKnife+ PC does the everyday PDF jobs on a Windows PC without sending the file anywhere: read and print, combine and cut, fix text, mark up, redact, make scans searchable, shrink and protect. Its first user is the owner; other people may use it later under its free licence, so it is written for other people's PCs too.

### D-R01 · Jobs and how often

**Rule:** The app serves the jobs below, as often as each row says; defaults and quick actions are ordered by this frequency.

**Values:**

| Job | How often | Done when |
|---|---|---|
| Read a PDF and print it | most often | the pages are on screen or on paper |
| Merge files, split a file, rotate or reorder pages | most often | the new files are written or the document is saved |
| Edit text, annotate, redact, OCR a scan | most often | the document or its new copy is saved |
| Compress a file, add or remove a password | occasionally | the document is saved |
| Convert to or from PDF, extract images | occasionally | the output files are written |
| Batch a folder | rarely | every file in the folder has its result |

**Evidence:** Owner's answer of 2026-11-26 names the first three rows as most frequent; the order of the others is the builder's.

**Acceptance:** none: a frequency is not checked by a test; R37 is its visible consequence.

**Since:** 2026-11-26 · owner · migrated

### D-R02 · Who it is for

**Rule:** The app is built for the owner first and kept ready for other people's PCs: nothing in it may depend on the owner's own machine, files or accounts.

**Acceptance:** A clean Windows user account with no Python, no Tesseract and no prior data starts the installed app, opens a PDF and saves it.

**Since:** 2026-11-26 · owner · migrated

## 2. Platform and release

### D-R03 · Windows versions

**Rule:** The app runs on 64-bit Windows 11 and on Windows 10 (build 19041 or later) for as long as the pinned PySide6 supports Windows 10.

**Values:**

| Item | Windows 11 | Windows 10 |
|---|---|---|
| UI font | Segoe UI Variable | Segoe UI |
| Icon font | Segoe Fluent Icons | Segoe MDL2 Assets |
| Minimum window | 1060 x 720 | 1060 x 720 |

**Evidence:** `paperknife/qt/shell.py:249` sets the minimum size. Not checked: no run on Windows 10 recorded.

**Acceptance:** The installed app starts and passes `--selftest` on Windows 11 and on a Windows 10 22H2 machine.

**Since:** 2026-11-26 · owner · migrated

### O-R04 · Offline

**Rule:** The app makes no network connection: no telemetry, no analytics, no crash reporting, no update check, no online help.

**Why:** The files are private; the whole promise of the app is that nothing leaves the PC.

**Acceptance:** No module under `paperknife/` imports `socket`, `urllib`, `http`, `requests` or `ssl`, and a full test run with outbound connections blocked passes.

**Since:** 2026-10-02 · owner · migrated

### D-R05 · Library pins

**Rule:** The app uses exactly the library versions below, the Fluent packages installed with `--no-deps`.

**Values:**

| Package | Version | Why pinned |
|---|---|---|
| `PySide6-Essentials` | 6.12.0 | the Fluent pin is tested against it |
| `PySide6-Fluent-Widgets` | 1.11.3 | `paperknife/qt/fluent_route.py` patches its internals |
| `PySideSix-Frameless-Window` | 0.8.2 | matches the Fluent pin |
| `PyMuPDF` | 1.27.2 or later | the lowest version the suite has run on |

**Evidence:** `requirements.txt`, `requirements-fluent.txt`; `tests/qt/test_palettes.py` probes the patched internals.

**Acceptance:** `tests/qt/test_palettes.py` passes after any change of the Fluent or PySide6 version.

**Since:** 2026-10-12 · builder · migrated

### D-R06 · Installer

**Rule:** The NSIS installer installs per user into `%LOCALAPPDATA%\PaperKnifePlusPC` with no elevation, adds a desktop shortcut and a Start Menu entry, supports `/S`, and stops without changing anything (exit code 2) while the app runs. It is not code-signed until a public release.

**Evidence:** `installer.nsi`; `tools/install_check.ps1` 23/23 on 2026-10-10.

**Acceptance:** `tools/install_check.ps1` passes in a sandbox; a silent install over a running app exits 2 and leaves the old files.

**Not:** Signing before a public release: a yearly certificate cost before anyone else uses the app.

**Since:** 2026-11-26 · owner · migrated

### O-R07 · Uninstall leaves other folders alone

**Rule:** The installer and the uninstaller delete only the app's own files; the data folder, the recovery folder and every other folder stay as they are.

**Why:** A user's preferences, recent files and any file beside the app must survive an uninstall or a reinstall.

**Acceptance:** After a silent uninstall the data folder and the recovery folder exist with their files, and a file placed in the install folder's parent is untouched.

**Since:** 2026-11-26 · owner · migrated

### D-R08 · Licence and credits

**Rule:** The app is licensed AGPL-3.0 and credits potatameister as the author of the upstream PaperKnife in both manuals (R11), the README and the app's About text. The registry key `HKCU\Software\potatameister\PaperKnifePlusPC` stays for upgrade continuity.

**Evidence:** `LICENSE`; the MANUAL header reads "github/potatameister". The README credits potatameister (2026-11-26). Not checked: the app shows no credit; it has no About text.

**Acceptance:** The README, both manuals and Preferences' About line each name potatameister as the upstream author.

**Since:** 2026-11-26 · owner · migrated

## 3. Language

### D-R09 · Interface languages

**Rule:** Every text the interface shows exists in English and Italian. The app starts in Italian when Windows' display language is Italian and in English otherwise; a Preferences setting overrides it.

**Evidence:** Not built: no string goes through a translation layer (`tr(` appears nowhere under `paperknife/qt/`).

**Acceptance:** With Windows set to Italian every visible string of every tool page, dialog and status message is Italian; with the Preferences setting on English the same screens are English; a test lists any string shown that has no Italian entry.

**Since:** 2026-11-26 · owner · migrated

### D-R10 · Date in Header / Footer

**Rule:** `{date}` in Header / Footer writes the date in the interface language's own format: `26/11/2026` in Italian, `2026-11-26` in English.

**Why:** An Italian reader of the printed page expects day/month/year; ISO stays for English, where it reads the same everywhere.

**Evidence:** Not built: `paperknife/qt/tools/headerfooter.py:147` writes ISO in both languages.

**Acceptance:** With the interface in Italian a header of `{date}` on 2026-11-26 reads "26/11/2026"; in English it reads "2026-11-26".

**Since:** 2026-11-26 · owner · agreed rewording

### D-R11 · Italian manual

**Rule:** The MANUAL exists in English and in Italian, with the same sections in the same order; a change that alters one changes the other in the same commit.

**Evidence:** Not built: only the English `MANUAL.md` exists; the README holds a short Italian summary.

**Acceptance:** The Italian manual has the English one's headings, translated, in the same order; a commit that changes one manual and not the other fails review.

**Not:** An English-only manual with the README as the Italian summary: the owner chose a second manual.

**Since:** 2026-11-26 · owner · agreed rewording

## 4. Data on disk

### D-R12 · Data folder

**Rule:** The data folder is `%APPDATA%\PaperKnifePlusPC` and holds the files below; recovery copies live elsewhere (R13). At the first start of a version with this rule, the files of the old folder `%USERPROFILE%\.paperknifepluspc` move once to the place their row gives, and the old folder is deleted when empty.

**Values:**

| File | Holds | Moves to |
|---|---|---|
| `prefs.json` | preferences, window place, folded groups, leftover temp-file paths | `%APPDATA%\PaperKnifePlusPC` |
| `recent.json` | recent files: path, name, size, page count, access time | `%APPDATA%\PaperKnifePlusPC` |
| `recovery\` | recovery copies (R22) | the recovery folder (R13) |

**Evidence:** Not built: `paperknife/recent.py:15` sets `APPDIR` to `~/.paperknifepluspc`, and `paperknife/core/recovery.py:23` puts `recovery` under it; MANUAL sections 7 and 10 and the note in `installer.nsi:174` name the old folder.

**Acceptance:** A profile with only the old folder starts with the same preferences, recent files and pending recovery offer, ends with each file where its row says and no old folder; a second start moves nothing.

**Since:** 2026-11-26 · owner · agreed rewording

### D-R13 · Recovery folder

**Rule:** Recovery copies live in `%LOCALAPPDATA%\PaperKnifePlusPC-data\recovery`, outside both the roaming `%APPDATA%` and the install folder.

**Why:** On a domain PC with roaming profiles, `%APPDATA%` is copied to a server at sign-out; a recovery copy holds the whole unsaved document, which R04 promises never leaves the PC. The install folder `%LOCALAPPDATA%\PaperKnifePlusPC` is deleted whole by the uninstaller, which would break R07.

**Evidence:** `installer.nsi:153-155` runs `RMDir /r "$INSTDIR"` when the install folder is named `PaperKnifePlusPC`. The owner confirmed the folder name `PaperKnifePlusPC-data` on 2026-11-26. Not built: `paperknife/core/recovery.py:23` keeps recovery copies under the old folder.

**Acceptance:** With the data folder roaming, a recovery copy written after an edit lies under `%LOCALAPPDATA%\PaperKnifePlusPC-data\recovery` and nothing under `%APPDATA%` holds document bytes; a silent uninstall leaves the recovery folder in place.

**Not:** `%LOCALAPPDATA%\PaperKnifePlusPC\recovery`: it sits inside the install folder, which the uninstaller deletes.

**Since:** 2026-11-26 · owner · agreed rewording

### O-R14 · No password on disk

**Rule:** No password is written to any file: an open password stays with the open document and is forgotten when it closes; a recovery copy of a protected PDF stays encrypted under that password.

**Why:** A password file beside the data would undo the protection the user set.

**Evidence:** `paperknife/core/recovery.py`; MANUAL section 10.

**Acceptance:** After opening, editing and closing a protected PDF, no file in the data folder or the recovery folder contains the password as text, and its recovery copy does not open without it.

**Since:** 2026-11-26 · owner · migrated

## 5. The document

### O-R15 · One document per window

**Rule:** A window holds one current document; every single-file tool works on it and shows the other tools' unsaved edits. Moving to another tool asks nothing.

**Why:** A job often takes several tools in a row (turn a page, watermark, annotate); each tool must start from the result of the last.

**Acceptance:** A watermark applied in Watermark shows in Annotate without a save, and switching tools shows no question.

**Since:** 2026-10-23 · owner · migrated

### O-R16 · Save and Save as

**Rule:** Save (`Ctrl+S`) writes the current document over its own file; Save as (`Ctrl+Shift+S`) writes a new file the document then belongs to. The title bar shows the file name, with `*` while it holds unsaved edits.

**Why:** One familiar place to save; the file name says which file the window holds.

**Acceptance:** After an edit the title reads "name.pdf* — PaperKnife+ PC"; after Save the file on disk holds the edit and the `*` is gone.

**Not:** Save as by default for the first save of a session: overwrite is the default the owner chose.

**Since:** 2026-10-23 · owner · migrated

### O-R17 · Append saves

**Rule:** When every edit since the file was opened or last saved only adds to it, Save appends the edits to the file; any edit that removes or replaces content makes Save a whole write.

**Why:** Bytes already in the file stay as they are, so a digital signature over them stays valid and a large file is not written again; removed text must not stay readable inside the file.

**Values:**

| Edit since the last save | Save |
|---|---|
| comments added | append |
| bookmarks added | append |
| empty properties filled, file without XMP | append |
| pages turned or moved | append |
| a comment, page or bookmark deleted or renamed | whole write |
| a property changed or cleared | whole write |
| Edit Text, Find & Replace, any Apply | whole write |
| an undo | whole write |
| a protected file, a protection set or removed | whole write |
| Save as | whole write |

**Evidence:** `paperknife/core/doc_state.py` `_save_doc`; `tests/test_incremental_save.py`.

**Acceptance:** A comment added to a signed PDF and saved leaves the original bytes as the file's prefix; a deleted comment's text is absent from the saved file's bytes.

**Since:** 2026-10-12 · owner · migrated

### D-R18 · Whole writes never leave half a file

**Rule:** A whole write goes to a temporary file beside the target and replaces the target only when complete; an append save keeps a backup copy beside the file and puts it back if the append fails.

**Evidence:** `paperknife/job_queue.py:48` `atomic_output`; append backup in `paperknife/core/doc_state.py`.

**Acceptance:** A save killed mid-write leaves the old file intact and no `.part` file after the next start.

**Since:** 2026-10-12 · builder · migrated

### D-R19 · Unsaved question

**Rule:** Opening another document, clearing it, Start over and closing the window ask "Save changes to name?" with "Save", "Discard" and "Cancel" while the document has unsaved edits or a tool holds typed input not applied. The new file is opened first, so one that cannot open asks nothing and changes nothing.

**Acceptance:** With an unsaved edit, each of the four actions shows the question; "Cancel" leaves document and edits as they were; a wrong-password file opened over it changes nothing.

**Since:** 2026-10-23 · owner · migrated

### D-R20 · Undo

**Rule:** `Ctrl+Z` takes back the current document's last edit, whichever tool made it, up to the number of steps R21 allows; undoing back to the last save makes the document clean again, and edits stay undoable after a save.

**Evidence:** `paperknife/core/doc_state.py:15` `UNDO_DEPTH = 10`; each step holds a whole copy of the document in memory (`paperknife/core/document.py:134`).

**Acceptance:** On a small file eleven edits then ten undos leave the first edit in place; undoing to the save point removes the `*`.

**Since:** 2026-11-26 · owner · agreed rewording

### D-R21 · Undo on large files

**Rule:** Undo keeps ten steps while their copies stay under 1 GB in all; a larger file keeps as many steps as fit under 1 GB, at least one, and the status line says so once per document.

**Why:** Ten whole copies of a 300 MB scanned PDF need about 3 GB on top of the app, more than the 4 GB minimum the MANUAL states leaves free; fewer steps on such files cost little.

**Evidence:** Not built: `UNDO_DEPTH = 10` holds for every size.

**Acceptance:** On a 300 MB file the undo copies never total more than 1 GB, at least one undo works, and the status line names the smaller number of steps once.

**Since:** 2026-11-26 · owner · agreed rewording

### O-R22 · Crash recovery

**Rule:** While the document holds unsaved edits or a tool holds marks or typed input, a recovery copy is refreshed within 10 seconds of a change. Save, "Discard" and a normal exit delete it. After a crash the next start asks "Recover unsaved changes?" with "Recover" and "Discard" (a protected document's copy then asks for its open password, R14); closing the question asks again at the next start.

**Why:** A crash or a power cut must not lose an afternoon's edits.

**Evidence:** `paperknife/qt/shell.py:57` `RECOVERY_MS = 10_000`; `paperknife/core/recovery.py`; `shell.py` `open_pdf_data` asks the password of a recovered encrypted copy. Not checked: a 300 MB document rewrites its whole copy after each change.

**Acceptance:** Killing the process 11 seconds after an edit, then starting again, offers the edit back in the tool it was made in.

**Since:** 2026-11-26 · owner · agreed rewording

### O-R23 · Apply and new-file verbs

**Rule:** A main action that changes the current document reads "Apply"; one that writes a new file keeps a verb naming that file; the instant editors have no card Save. The rows below list each tool's kind.

**Why:** The same word always means the same result.

**Values:**

| Tool | Main action | Result |
|---|---|---|
| Compress, Watermark, Normalise Pages, Crop / Trim, Header / Footer, PDF Tools, Password, Metadata, Bookmarks / TOC | "Apply" | current document |
| OCR, Overlay | "Apply" | current document |
| OCR, Text-only PDF | "Text-only PDF from OCR" | new file |
| Merge | "Merge" | new file |
| Split | "Split" | several files |
| Redact | "Save redacted copy…" | new file |
| Rotate & Reorder | each command at once; "Extract to a new PDF" | current document; new file |
| Other to PDF | "Convert to PDF" | new file |
| PDF to Other | "Convert PDF" | new files |
| Extract Images | its action | several files |
| Batch | "Run Batch" | several files |
| Edit Text, Find & Replace, Annotate | in the panel | current document |

**Acceptance:** Every tool's main button shows the text its row gives.

**Since:** 2026-10-31 · owner · migrated

### O-R24 · Destructive steps make new files

**Rule:** Merge and Redact write new files and never touch their sources; closing the window with redaction boxes drawn and not applied asks "n redaction boxes drawn and not applied will be lost. Close anyway?", after R19's question when both apply.

**Why:** A redaction or a merge that went wrong must leave the original to start again from.

**Acceptance:** After "Save redacted copy…" the open file's bytes are unchanged; closing with two unapplied boxes shows the question.

**Since:** 2026-11-26 · owner · agreed rewording

### D-R25 · Passwords

**Rule:** A protected PDF asks for its open password when opened; Save keeps the password without asking; a new file written from it (Save as, a new-file tool) asks whether it keeps the password; Merge asks only when every protected input has the same open password. A file with only an owner password is changed without asking for it.

**Acceptance:** Save of a protected file reopens only with its password; Save as asks the keep question; a permissions-only file can be watermarked without a password.

**Since:** 2026-10-23 · owner · migrated

### D-R26 · Page ranges

**Rule:** Page ranges are written like `1-3, 5, 8-end`; in Split a semicolon separates files (`1-3; 4, 6; 7-end`). A range naming a page the document lacks, or running backwards, is refused with a message before anything is written.

**Acceptance:** `2-1` and `99` on a 10-page file each show a message and write nothing; Split with `1-3; 4, 6; 7-end` writes three files.

**Since:** 2026-10-17 · owner · migrated

## 6. Layout

### Q-R27 · Window layout

**Rule:** Which layout is the app's: the group rail with the floating card (E2), or the navigation pane with the tool page and its options beside it?

**Default:** E2, after an assessment with the visual-craft, design-critique-plus and design-optimization skills confirms or overturns it; the `PK_*` layout switches and the other layout are then removed, and the MANUAL follows. Changes: R28 to R33 hold only for E2.

**Why:** E2 won the owner's walk (2026-10-21) and was critiqued and fixed (2026-11-21), but it still runs only behind `PK_STRUCT=workspace PK_PICKER=pane PK_FILES=window PK_DETAILS=float PK_LEFT=grouprail`; the MANUAL describes the navigation pane.

**Since:** 2026-11-26 · owner · migrated

### O-R28 · Action fixed at the card top

**Rule:** The tool's main action sits at the top right of the card, at the same height on every tool, and never scrolls with the options; the card names the tool under it.

**Why:** An action at the bottom moved with the length of the list above it.

**Evidence:** Not checked: provisional, follows R27's proposed default. `tests/qt/test_structure_e2.py` `test_action_fixed_at_the_card_top_for_every_tool`.

**Acceptance:** On every tool the action's top edge has one window y; scrolling the options leaves it in place.

**Since:** 2026-10-21 · owner · migrated

### O-R29 · Card collapses, the page keeps clear

**Rule:** The card collapses to an edge card that keeps the tool name and the action in place. While it is open, page grids and editor pages leave its width free: an editor's page keeps its size and scrolls sideways into the room beside the card.

**Why:** No page may be hidden under the card where it cannot be reached.

**Evidence:** Not checked: provisional, follows R27's proposed default. Commit 2426a0f.

**Acceptance:** With the card open no thumbnail lies under it, and an editor's page scrolled right ends left of the card.

**Since:** 2026-11-21 · owner · migrated

### O-R30 · Group rail

**Rule:** Tool groups sit on a 64 px rail. A left click opens the group's column, a right click a menu of the same tools; either closes once a tool is chosen. The accent bar marks the open tool's group, the tint the group whose column is open; the menu ticks the open tool; each group's tooltip names both clicks, and the column ends with "Tip: right-click a group for a quick menu".

**Why:** Groups keep the page wide; the open tool must stay findable while another group is browsed.

**Evidence:** Not checked: provisional, follows R27's proposed default. Commit 025c17d.

**Acceptance:** With Compress open and the Pages column shown, "Protect & optimise" has the bar only and "Pages" the tint only; the right-click menu of "Protect & optimise" ticks "Compress".

**Since:** 2026-11-21 · owner · migrated

### O-R31 · Document bar and Save after Apply

**Rule:** The document bar holds "Open" (its arrow lists recent files, then "Browse…"), the file chip with its clear button, "Save" (its arrow holds "Save as…") and "Print", the last two only while a document is open. After an Apply, the card shows "✓ Applied · Save now" under the action until the file is saved, undo returns to the saved state, or another tool is chosen.

**Why:** One familiar place to save, and a short way to it right after the change it saves.

**Evidence:** Not checked: provisional, follows R27's proposed default. Commit 025c17d measured 53 px from Apply to "Save now" at 1280 x 820, against 707 px to the bar's Save.

**Acceptance:** After Compress's Apply the line shows; "Save now" saves; choosing Watermark hides it.

**Since:** 2026-11-21 · owner · migrated

### O-R32 · Card width

**Rule:** The open card is 200 px wide inside and its input fields 160 px; from a 1600 px wide window it is 260 px inside and its fields 220 px. Both workspaces use the same width.

**Why:** One column edge on every card; at 1920 px the narrow card wrapped labels beside unused page width.

**Values:**

| Window width | Card inside | Field |
|---|---|---|
| below 1600 px | 200 px | 160 px |
| 1600 px or more | 260 px | 220 px |

**Evidence:** Not checked: provisional, follows R27's proposed default. `paperknife/qt/structure.py` `DETAILS_W`, `DETAILS_W_WIDE`, `FIELD_W_WIDE`; commit 025c17d.

**Acceptance:** `tests/qt/test_structure_e2.py` `test_a_wide_window_widens_the_card_and_its_fields`.

**Since:** 2026-11-21 · owner · migrated

### O-R33 · Card details

**Rule:** The card's settings follow the rows below.

**Why:** Each row is a ruling the owner gave on a measured case; together they keep the cards calm and alike.

**Values:**

| Element | Rule |
|---|---|
| numbers | typed number boxes; the zoom is the only slider |
| descriptions | behind a circled "i", opened by a click |
| overflow cue | a thin scroll handle at rest |
| Redact's Remove | above the pending list, so it never moves |
| file paths | shortened in the middle, full path in the tooltip |
| Merge with no files | the action stays on; a click says what is missing |

**Evidence:** Not checked: provisional, follows R27's proposed default for the card; the rows hold in both layouts.

**Acceptance:** No tool page has a slider other than the zoom; no description line shows under a setting's name.

**Since:** 2026-10-31 · owner · migrated

### O-R34 · Same place, same size

**Rule:** A control at one level of the hierarchy has the same size and place on every screen; a column too narrow for a row of buttons takes another row, never smaller or icon-only buttons. Targets follow the Fluent desktop size of 32 px.

**Why:** A control found once is found again without looking; the app is used with a mouse at a desk.

**Acceptance:** `tests/qt/test_layout_rules.py` passes; buttons of one group on one screen have one height.

**Not:** 40 px touch targets: the brief is a desk with a mouse.

**Since:** 2026-10-17 · owner · migrated

### O-R35 · Colours and status

**Rule:** The palette is Windows neutrals with an Oxford blue accent, in light and dark mode; text meets WCAG AA contrast, AAA where it can. A status line that reports a result starts with a symbol and always has text: "✓" done, "⚠" warning, "✗" error.

**Why:** Calm and familiar on Windows; a colour-blind user reads the state from the symbol and the words.

**Acceptance:** `tests/qt/test_palettes.py` passes; every `set_status` with a role other than muted starts with its symbol.

**Since:** 2026-10-09 · owner · migrated

## 7. Start and Home

### D-R36 · Start screen

**Rule:** The app starts on Home: "Open PDF…", the quick actions and the recent files. A PDF path given on the command line opens in Read / Preview instead.

**Acceptance:** A start with no argument shows Home; `PaperKnifePlusPC.exe file.pdf` shows the file in Read / Preview.

**Not:** Reopening the last document: Home is one click from any file and asks nothing.

**Since:** 2026-11-26 · owner · migrated

### D-R37 · Quick actions

**Rule:** Home's quick actions are, in this order: Read / Preview, Merge, Split, Rotate & Reorder, Edit Text, Annotate, OCR.

**Why:** They are the most frequent jobs of R01, in its order.

**Evidence:** Not built: `QUICK_ACTIONS` in `paperknife/qt/home.py:30` holds Password and Compress (occasional jobs) and lacks Rotate & Reorder and Edit Text.

**Acceptance:** Home shows exactly these seven quick actions in this order, and each opens its tool.

**Not:** Password and Compress as quick actions: occasional jobs in R01.

**Since:** 2026-11-26 · owner · agreed rewording

### D-R38 · Recent files never stall Home

**Rule:** Home shows recent files without waiting on a drive that does not answer: a file on an unreachable network share or a removed USB drive is skipped or shown greyed, and Home is usable at once.

**Evidence:** `paperknife/recent.py:93` checks each entry with `Path.exists()` while Home is built. Not checked: how long that takes on an unreachable share; Windows can wait tens of seconds for a network path.

**Acceptance:** With a recent entry on `\\offline-host\share\a.pdf`, Home is shown and responds within one second of the window appearing.

**Since:** 2026-11-26 · builder · migrated

## 8. Tools

### D-R39 · OCR defaults

**Rule:** OCR renders pages at 200 DPI in grey, reads sideways and upside-down pages upright, and starts with Windows' display language when installed, else English, then the language of the last run. Overlay keeps every recognised word; Text-only PDF leaves out words below confidence 40.

**Why:** 200 DPI read the most words on simulated scans (2026-10-22); grey read as many words 0.7 to 1.1 s a page sooner (2026-11-01).

**Evidence:** `paperknife/prefs.py:17`; `docs/ocr-check-2026-11-01.md`.

**Acceptance:** A fresh profile shows 200 in OCR's DPI box and the display language ticked; an upside-down test page is read with its words where the page shows them.

**Since:** 2026-11-26 · owner · migrated

### D-R40 · OCR page layout and low-confidence warning

**Rule:** OCR's card has a "Page layout" menu whose options read pages with the Tesseract mode their row gives; "Auto" is the default. After a run in "Auto", the run's result line names every page whose mean word confidence is below 89, as a page range (R26): "⚠ Page 3 was read with low confidence: check its text (handwriting, faint print and dotted lines read poorly)", or for several pages "⚠ Pages 3-5, 9 were read with low confidence: check their text (handwriting, faint print and dotted lines read poorly)". "Tables" and "Receipts" show no warning.

**Why:** R39's defaults were chosen by measurement; the measurement of 2026-11-26 found fixed modes that read tables and receipts better than "Auto" but read two-column pages across their columns, so they are the user's choice per job and never the default. A warning shown when it applies says more than a note behind the "i".

**Values:**

| Option | Tesseract mode | Score against "Auto" on its pages |
|---|---|---|
| "Auto" | 3 | best on text, two-column and real pages; 96.5 over all |
| "Tables" | 4 | tables without rules 99.5 against 89.6; ruled tables 97.6 against 98.1 |
| "Receipts" | 6 | receipts 96.2 against 89.1; words found 90 to 92 % against 75 to 84 % |

**Evidence:** `docs/ocr-layout-2026-11-26.md`: 62 pages (generated tables, price lists, receipts, text, two-column text; 18 pages of PDFs shipped with installed programs), simulated scans at 200 and 300 ppi, clean and worn, read at 200 DPI grey; score = words found, junk, character errors, row order (weight 1 each) and speed (0.5). Of 1,120 rules (one mode, or two modes kept by confidence or word count), none beat "Auto" without breaking two-column pages: mode 4 and mode 6 keep 1 % of their row order, because neither confidence nor word count drops when a line is read across two columns. The cut-off (that file's last section, mode 3, 248 page readings) was chosen on seed-1 pages to separate readings with under 80 % of words right: it warns on 23 of 24 such pages there and 17 of 25 on the seed-2 pages, with 13 of 116 and 6 of 83 good readings warned. It warns on every price-list and Segoe Script page, on no plain-text, two-column, mixed, plain or striped table page, and on 2 of 16 ruled-table readings; the other false warnings are receipts and real pages. In "Receipts" confidence does not tell good readings from poor ones (one with 95 % of words right reads at 68.7, the two poor ones at 79.6 and 80.8), and the same cut-off would warn on 19 of 32 receipt readings, 17 of them good; in "Tables" no reading was poor. Not checked: real handwriting, real scans, and DPI settings other than 200. Ink Free and Segoe Print read like print (94 % and 99 % of words found) and draw no warning.

**Acceptance:** A fresh profile shows "Auto"; each option reads with its row's mode; in "Auto", the generated test pages `pricelist-eng-1.pdf` and `hand-segoescript-eng-1.pdf` (`_ocr-layout-2026-11-26/gen_corpus.py`; mean confidence 34 and 75) each show the warning naming their page, and `text-eng-1.pdf` and `columns-eng-1.pdf` (96) show "✓"; in "Receipts" a receipt page shows no warning.

**Not:** "Tables" or "Receipts" as the default, or a rule that switches modes by itself: on a two-column page both read across the columns, and no runtime signal measured tells such a reading apart. A warning that names handwriting as the cause: printed price lists and a white-on-dark page read at lower confidence (34 to 50) than handwriting-style fonts. The same cut-off in "Tables" and "Receipts": in "Receipts" it would warn on most good receipts, the pages that option is chosen for. A note behind the card's "i": it is read once and missed when it applies.

**Since:** 2026-11-26 · owner · agreed rewording

### D-R41 · Compress levels

**Rule:** Compress offers the levels below; text and vector content are kept in each. A result that would not be smaller leaves the document as it was, with a warning.

**Values:**

| Level | Unused objects removed, streams compressed | Images above the limit resampled | Limit | JPEG quality |
|---|---|---|---|---|
| Light | yes | no | none | none |
| Medium | yes | yes | 150 DPI | 80 |
| Aggressive | yes | yes | 96 DPI | 80 |

**Acceptance:** `tests/qt/test_compress_page.py` passes; Compress of an already compressed file shows the warning and leaves no `*`.

**Since:** 2026-10-23 · builder · migrated

### O-R42 · Redaction removes, at the box edge

**Rule:** Redaction removes text, image pixels and drawings under each box, plus annotations and form fields it touches; a drawing crossing the box edge is cut at the edge. The redacted phrase also leaves properties, XMP, bookmark titles, annotations, form fields and attachments.

**Why:** Privacy over pixel-exact rendering: the box's inside must be gone for good, even where it costs slight anti-aliasing on the clip edge.

**Evidence:** `paperknife/lineart.py`; `docs/redaction/realworld_check.py`.

**Acceptance:** In a redacted copy no character, image pixel or path point lies inside a box, and the phrase is absent from the file's bytes.

**Since:** 2026-10-07 · owner · migrated

### D-R43 · Text rewrite unit

**Rule:** Edit Text and Find & Replace rewrite by a unit the user picks per job, "Line", "Paragraph" or "Page", with "Paragraph" first; a change that would carry across risky pages stops there, is skipped and is listed.

**Evidence:** `paperknife/core/reflow.py`; commit 32d5d33.

**Acceptance:** `tests/qt/test_find_replace_page.py` and `tests/qt/test_edit_text_page.py` pass; a replacement on a page with a table row is listed as skipped.

**Since:** 2026-10-11 · owner · migrated

### D-R44 · Find & Replace case

**Rule:** Find & Replace has a "Match case" switch, off by default: with it off a search finds every case form of the text; with it on, only the exact one. The replacement is written as typed, whatever the case of the text it replaces.

**Why:** A search for "iva" must find "IVA" and "Iva", which in Italian documents are common forms of one word.

**Evidence:** Not built: matching is case-sensitive only.

**Acceptance:** With the switch off, "iva" finds "iva", "Iva" and "IVA"; with it on, only "iva"; a fresh profile shows it off.

**Not:** The switch on by default: it would keep the miss of "IVA" as the first experience.

**Since:** 2026-11-26 · owner · agreed rewording

### D-R45 · Batch input

**Rule:** Batch processes every `*.pdf` directly in the chosen folder, not in its subfolders, and skips with an error each file that needs an open password; a file with only an owner password is processed, as in R25.

**Evidence:** `paperknife/core/batch.py:21` skips on `doc.needs_pass`.

**Acceptance:** A folder with a subfolder PDF, a PDF with an open password and a PDF with only an owner password reports the first protected one as an error, processes the owner-password one and leaves the subfolder's file untouched.

**Since:** 2026-11-26 · builder · migrated

## 9. Real-world cases

### D-R46 · Save to a file another program holds

**Rule:** When Save cannot write the file, the status line gives the cause from the rows below, the document keeps its unsaved edits, and no temporary or backup file is left beside it.

**Values:**

| Cause | Status line |
|---|---|
| another program holds it open (a PDF viewer, a preview pane, a sync client) | "✗ name is open in another program: close it, or use Save as" |
| the file is read-only | "✗ name is read-only: use Save as" |
| the folder cannot be written (a read-only share, a protected folder) | "✗ This folder cannot be written: use Save as" |
| the disk is full | "✗ Not enough free space to save name" |

**Evidence:** Not checked: the messages shown today when `os.replace` in `paperknife/job_queue.py` or the append in `paperknife/core/doc_state.py` fails.

**Acceptance:** For each row's cause (a process holding the file with no shared delete access, the read-only attribute, a folder denying write, a full test volume) Save shows that row's line, the `*` stays, and no `.part` or `.bak` file remains.

**Since:** 2026-11-26 · builder · migrated

### D-R47 · File changed on disk while open

**Rule:** Save compares the file's size and modification time with those at open or at the last save; if they differ it asks "name changed on disk since you opened it" with "Overwrite", "Save as…" and "Cancel". A recovered document (R22) compares with the values its recovery copy recorded, so a change made while the app was down is caught too.

**Why:** In a shared or synced folder a colleague's newer version must not be overwritten without a word.

**Evidence:** Not built: Save overwrites without a check.

**Acceptance:** A file touched by another process after opening shows the question on Save; "Cancel" leaves both the file and the `*` as they were; an untouched file saves with no question.

**Since:** 2026-11-26 · owner · agreed rewording

### D-R48 · Ctrl+S on Preferences

**Rule:** `Ctrl+S` saves the current document on every screen, Preferences included; Preferences saves only with its own button.

**Why:** A user who presses `Ctrl+S` on Preferences with an unsaved document open expects the document saved.

**Evidence:** Not built: `Ctrl+S` on Preferences saves the preferences.

**Acceptance:** With an unsaved document and Preferences shown, `Ctrl+S` removes the `*` and leaves the preferences unsaved.

**Since:** 2026-11-26 · owner · agreed rewording

### I-R49 · Two windows

**Rule:** Each running app has its own current document and its own recovery copy; `prefs.json` and `recent.json` take the last writer's content.

**Evidence:** `paperknife/core/recovery.py` locks a folder per running app.

**Since:** 2026-11-26 · builder · migrated

## 10. Test plan

### D-R50 · Gate

**Rule:** A change is merged only after the rows below pass.

**Values:**

| Check | Command | Runs |
|---|---|---|
| core suite | `pytest -q -p no:cacheprovider tests` without `tests/qt` | every merge |
| Qt suite | `pytest -q -p no:cacheprovider tests/qt` with `QT_QPA_PLATFORM=offscreen` | every merge |
| lint | `ruff check` on the changed files, no finding beyond the base | every merge |
| launch | `python -m paperknife.qt` stays up 12 s with an empty log | every merge |
| frozen | `PaperKnifePlusPC.exe --selftest` 34/34 | every installer |

**Evidence:** The core and Qt suites run separately: one run over `tests/` clashes their conftests. Known flakes: `test_batch_ocr_finds_tesseract_in_its_default_folder_off_path`, and OCR tests under a long full run; each passes alone.

**Acceptance:** none: the gate is how the other rules are checked.

**Since:** 2026-11-22 · builder · migrated

## 11. Rollout

### D-R51 · Release path

**Rule:** A change moves along the phases below only when its gate holds, and goes back one phase when its rollback trigger fires.

**Values:**

| Phase | Where | Gate to the next | Rollback trigger |
|---|---|---|---|
| 1 | a feature branch | R50 and the owner's look at shots | a failing gate row |
| 2 | `structures`, then `main` | the owner says merge | a defect found in the owner's walk |
| 3 | the installer | frozen selftest and the owner's Explorer install | the owner's install check fails, or a report of lost data |

**Acceptance:** none: a release practice, checked by its gates.

**Since:** 2026-10-15 · owner · migrated

## Acceptance list

- R02 · Who it is for: A clean Windows user account with no Python, no Tesseract and no prior data starts the installed app, opens a PDF and saves it.
- R03 · Windows versions: The installed app starts and passes `--selftest` on Windows 11 and on a Windows 10 22H2 machine.
- R04 · Offline: No module under `paperknife/` imports `socket`, `urllib`, `http`, `requests` or `ssl`, and a full test run with outbound connections blocked passes.
- R05 · Library pins: `tests/qt/test_palettes.py` passes after any change of the Fluent or PySide6 version.
- R06 · Installer: `phase7/install_check.ps1` passes in a sandbox; a silent install over a running app exits 2 and leaves the old files.
- R07 · Uninstall leaves other folders alone: After a silent uninstall the data folder and the recovery folder exist with their files, and a file placed in the install folder's parent is untouched.
- R08 · Licence and credits: The README, both manuals and Preferences' About line each name potatameister as the upstream author.
- R09 · Interface languages: With Windows set to Italian every visible string of every tool page, dialog and status message is Italian; with the Preferences setting on English the same screens are English; a test lists any string shown that has no Italian entry.
- R10 · Date in Header / Footer: With the interface in Italian a header of `{date}` on 2026-11-26 reads "26/11/2026"; in English it reads "2026-11-26".
- R11 · Italian manual: The Italian manual has the English one's headings, translated, in the same order; a commit that changes one manual and not the other fails review.
- R12 · Data folder: A profile with only the old folder starts with the same preferences, recent files and pending recovery offer, ends with each file where its row says and no old folder; a second start moves nothing.
- R13 · Recovery folder: With the data folder roaming, a recovery copy written after an edit lies under `%LOCALAPPDATA%\PaperKnifePlusPC-data\recovery` and nothing under `%APPDATA%` holds document bytes; a silent uninstall leaves the recovery folder in place.
- R14 · No password on disk: After opening, editing and closing a protected PDF, no file in the data folder or the recovery folder contains the password as text, and its recovery copy does not open without it.
- R15 · One document per window: A watermark applied in Watermark shows in Annotate without a save, and switching tools shows no question.
- R16 · Save and Save as: After an edit the title reads "name.pdf* — PaperKnife+ PC"; after Save the file on disk holds the edit and the `*` is gone.
- R17 · Append saves: A comment added to a signed PDF and saved leaves the original bytes as the file's prefix; a deleted comment's text is absent from the saved file's bytes.
- R18 · Whole writes never leave half a file: A save killed mid-write leaves the old file intact and no `.part` file after the next start.
- R19 · Unsaved question: With an unsaved edit, each of the four actions shows the question; "Cancel" leaves document and edits as they were; a wrong-password file opened over it changes nothing.
- R20 · Undo: On a small file eleven edits then ten undos leave the first edit in place; undoing to the save point removes the `*`.
- R21 · Undo on large files: On a 300 MB file the undo copies never total more than 1 GB, at least one undo works, and the status line names the smaller number of steps once.
- R22 · Crash recovery: Killing the process 11 seconds after an edit, then starting again, offers the edit back in the tool it was made in.
- R23 · Apply and new-file verbs: Every tool's main button shows the text its row gives.
- R24 · Destructive steps make new files: After "Save redacted copy…" the open file's bytes are unchanged; closing with two unapplied boxes shows the question.
- R25 · Passwords: Save of a protected file reopens only with its password; Save as asks the keep question; a permissions-only file can be watermarked without a password.
- R26 · Page ranges: `2-1` and `99` on a 10-page file each show a message and write nothing; Split with `1-3; 4, 6; 7-end` writes three files.
- R28 · Action fixed at the card top: On every tool the action's top edge has one window y; scrolling the options leaves it in place.
- R29 · Card collapses, the page keeps clear: With the card open no thumbnail lies under it, and an editor's page scrolled right ends left of the card.
- R30 · Group rail: With Compress open and the Pages column shown, "Protect & optimise" has the bar only and "Pages" the tint only; the right-click menu of "Protect & optimise" ticks "Compress".
- R31 · Document bar and Save after Apply: After Compress's Apply the line shows; "Save now" saves; choosing Watermark hides it.
- R32 · Card width: `tests/qt/test_structure_e2.py` `test_a_wide_window_widens_the_card_and_its_fields`.
- R33 · Card details: No tool page has a slider other than the zoom; no description line shows under a setting's name.
- R34 · Same place, same size: `tests/qt/test_layout_rules.py` passes; buttons of one group on one screen have one height.
- R35 · Colours and status: `tests/qt/test_palettes.py` passes; every `set_status` with a role other than muted starts with its symbol.
- R36 · Start screen: A start with no argument shows Home; `PaperKnifePlusPC.exe file.pdf` shows the file in Read / Preview.
- R37 · Quick actions: Home shows exactly these seven quick actions in this order, and each opens its tool.
- R38 · Recent files never stall Home: With a recent entry on `\\offline-host\share\a.pdf`, Home is shown and responds within one second of the window appearing.
- R39 · OCR defaults: A fresh profile shows 200 in OCR's DPI box and the display language ticked; an upside-down test page is read with its words where the page shows them.
- R40 · OCR page layout and low-confidence warning: A fresh profile shows "Auto"; each option reads with its row's mode; in "Auto", the generated test pages `pricelist-eng-1.pdf` and `hand-segoescript-eng-1.pdf` (`_ocr-layout-2026-11-26/gen_corpus.py`; mean confidence 34 and 75) each show the warning naming their page, and `text-eng-1.pdf` and `columns-eng-1.pdf` (96) show "✓"; in "Receipts" a receipt page shows no warning.
- R41 · Compress levels: `tests/qt/test_compress_page.py` passes; Compress of an already compressed file shows the warning and leaves no `*`.
- R42 · Redaction removes, at the box edge: In a redacted copy no character, image pixel or path point lies inside a box, and the phrase is absent from the file's bytes.
- R43 · Text rewrite unit: `tests/qt/test_find_replace_page.py` and `tests/qt/test_edit_text_page.py` pass; a replacement on a page with a table row is listed as skipped.
- R44 · Find & Replace case: With the switch off, "iva" finds "iva", "Iva" and "IVA"; with it on, only "iva"; a fresh profile shows it off.
- R45 · Batch input: A folder with a subfolder PDF, a PDF with an open password and a PDF with only an owner password reports the first protected one as an error, processes the owner-password one and leaves the subfolder's file untouched.
- R46 · Save to a file another program holds: For each row's cause (a process holding the file with no shared delete access, the read-only attribute, a folder denying write, a full test volume) Save shows that row's line, the `*` stays, and no `.part` or `.bak` file remains.
- R47 · File changed on disk while open: A file touched by another process after opening shows the question on Save; "Cancel" leaves both the file and the `*` as they were; an untouched file saves with no question.
- R48 · Ctrl+S on Preferences: With an unsaved document and Preferences shown, `Ctrl+S` removes the `*` and leaves the preferences unsaved.

## Out of scope

### D-R52 · Online features

**Rule:** Accounts, cloud storage, sync, sharing links and online conversion are out of scope.

**Why:** R04: nothing leaves the PC.

**Acceptance:** none: a scope boundary.

**Since:** 2026-10-02 · owner · migrated

### D-R53 · Saving in a helper process

**Rule:** Saves run in the app's own process; a large save holds the window for its length (about 2 ms a page).

**Why:** Owner, 2026-11-26: the freeze is short for the files the app is used on, and a helper process adds build effort and risk.

**Acceptance:** none: a scope boundary.

**Since:** 2026-11-26 · owner · migrated

### D-R54 · Other systems

**Rule:** macOS, Linux and Windows on ARM are out of scope.

**Acceptance:** none: a scope boundary.

**Since:** 2026-10-02 · owner · migrated
