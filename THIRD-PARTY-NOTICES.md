# Third-party notices — PaperKnife+ PC 4.0.0

PaperKnife+ PC is distributed under the GNU Affero General Public License v3.0 (`LICENSE`). The installed application bundles the components below. Versions and licences are those of each package's metadata (`*.dist-info/METADATA`) in the build environment; the licence files themselves are in the install folder's `licenses` folder.

---

## Qt 6.12.0

- Licence: LGPL-3.0 (Qt is also available under GPL-2.0, GPL-3.0 and a commercial licence; PaperKnife+ PC uses it under the LGPL-3.0)
- Project: https://www.qt.io/
- Copyright: The Qt Company
- Source: https://download.qt.io/official_releases/qt/ and https://code.qt.io/
- The Qt libraries are shipped as separate DLLs in the install folder, so they can be replaced.

## PySide6-Essentials 6.12.0

- Licence: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; used under the LGPL-3.0
- Project: https://pyside.org
- Source: https://code.qt.io/cgit/pyside/pyside-setup.git/
- Author (METADATA): Qt for Python Team
- The wheel's licence folder carries only the Qt commercial licence text; the LGPL-3.0 and GPL-3.0 texts in `licenses/Qt-6.12.0/` apply.

## shiboken6 6.12.0

- Licence: LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; used under the LGPL-3.0
- Project: https://pyside.org
- Source: https://code.qt.io/cgit/pyside/pyside-setup.git/
- Author (METADATA): Qt for Python Team

## PySide6-Fluent-Widgets 1.11.3

- Licence: GPL-3.0 (METADATA: GPLv3)
- Project: https://qfluentwidgets.com
- Source: https://github.com/zhiyiYo/PyQt-Fluent-Widgets/tree/PySide6
- Author (METADATA): zhiyiYo; the licence file is the plain GPL-3.0 text with no project copyright line

## PySideSix-Frameless-Window 0.8.2

- Licence: LGPL-3.0 (METADATA: LGPLv3)
- Project: https://github.com/zhiyiYo/PyQt-Frameless-Window/tree/PySide6
- Author (METADATA): zhiyiYo; the licence file is the plain LGPL-3.0 text with no project copyright line

## PyMuPDF 1.28.2

- Licence: AGPL-3.0 (METADATA: "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License"); used under the AGPL-3.0
- Project: https://pymupdf.readthedocs.io/
- Source: https://github.com/pymupdf/pymupdf
- Author (METADATA): Artifex; includes the MuPDF library (`mupdfcpp64.dll`)

## darkdetect 0.8.0

- Licence: BSD-3-Clause
- Project: http://github.com/albertosottile/darkdetect
- Copyright (c) 2019, Alberto Sottile

## pywin32 312

- Licence: PSF (METADATA); the per-component licence files are BSD-style
- Project: https://github.com/mhammond/pywin32
- Copyright (c) 1994-2008, Mark Hammond (win32, pythonwin); Copyright (c) 1996-2008, Greg Stein and Mark Hammond (com)

## Pillow 12.3.0

- Licence: MIT-CMU
- Project: https://python-pillow.github.io
- Source: https://github.com/python-pillow/Pillow
- Copyright © 1997-2011 by Secret Labs AB; Copyright © 1995-2011 by Fredrik Lundh and contributors; Copyright © 2010 by Jeffrey 'Alex' Clark and contributors

## pytesseract 0.3.13

- Licence: Apache-2.0 (METADATA: Apache License 2.0)
- Project: https://github.com/madmaze/pytesseract
- Author (METADATA): Samuel Hoffstaetter; the licence file is the plain Apache-2.0 text with no project copyright line
- Tesseract itself is not bundled (MANUAL.md, Section 4.3).

## python-docx 1.2.0

- Licence: MIT
- Project: https://github.com/python-openxml/python-docx
- Copyright (c) 2013 Steve Canny, https://github.com/scanny

## python-pptx 1.0.2

- Licence: MIT
- Project: https://github.com/scanny/python-pptx
- Copyright (c) 2013 Steve Canny, https://github.com/scanny

## openpyxl 3.1.5

- Licence: MIT
- Project: https://openpyxl.readthedocs.io
- Source: https://foss.heptapod.net/openpyxl/openpyxl
- Copyright (c) 2010 openpyxl

## et_xmlfile 2.0.0

- Licence: MIT
- Project: https://foss.heptapod.net/openpyxl/et_xmlfile
- Copyright (c) 2010 openpyxl

## lxml 6.1.3

- Licence: BSD-3-Clause (with the exceptions listed in its `LICENSES.txt`)
- Project: https://lxml.de/
- Source: https://github.com/lxml/lxml
- Copyright (c) 2004 Infrae. All rights reserved.

## XlsxWriter 3.2.9

- Licence: BSD-2-Clause
- Project: https://github.com/jmcnamara/XlsxWriter
- Copyright (c) 2013-2025, John McNamara <jmcnamara@cpan.org>

## typing_extensions 4.16.0

- Licence: PSF-2.0
- Project: https://github.com/python/typing_extensions
- Copyright: the Python Software Foundation licence text (see the licence file)

## striprtf 0.0.33

- Licence: BSD-3-Clause
- Project: https://github.com/joshy/striprtf
- Copyright (c) 2018, Joshy Cyriac

## Python 3.14.6

- Licence: PSF-2.0 (Python Software Foundation License Version 2)
- Project: https://www.python.org/
- The runtime (python314.dll and the standard library) is bundled by PyInstaller; its licence text is in `licenses/Python-3.14.6/LICENSE.txt`.

## PyInstaller 6.22.3 (bootloader)

- Licence: GPL-2.0-or-later with the PyInstaller bootloader exception, which allows a bundled program under any licence
- Project: https://pyinstaller.org/
- Only the bootloader (the start-up code inside PaperKnifePlusPC.exe) ships; its licence text is in `licenses/PyInstaller-6.22.3/COPYING.txt`.

## Microsoft Visual C++ runtime

- `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll`, `MSVCP140*.dll`, `ucrtbase.dll` and the `api-ms-win-*` Universal CRT files ship with the Python and Qt wheels: Microsoft's redistributable runtime files.

---

## Not bundled

- **Segoe UI Variable, Segoe UI, Segoe UI Symbol, Segoe Fluent Icons and Segoe MDL2 Assets** are Windows' own fonts. PaperKnife+ PC uses the copies installed with Windows and does not ship them.
- **Tesseract OCR** is installed separately by the user (MANUAL.md, Section 4.3).
