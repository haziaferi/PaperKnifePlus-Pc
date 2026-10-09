"""
Minimal setup.py so `pip install -e .` installs a `paperknife` console script.
"""
import re
from pathlib import Path
from setuptools import setup, find_packages

# Read as text, so this file imports nothing from the package it installs.
VERSION = re.search(r'^__version__\s*=\s*"([^"]+)"',
                    (Path(__file__).parent / "paperknife" / "_version.py")
                    .read_text(encoding="utf-8"), re.M).group(1)

setup(
    name            = "paperknife-plus-pc",
    version         = VERSION,
    description     = "PaperKnife+ PC — 100% local PDF toolkit",
    license         = "AGPL-3.0",
    packages        = find_packages(),
    python_requires = ">=3.10",
    # pip resolves PySide6-Fluent-Widgets' own requirement on the full PySide6;
    # setup.bat / requirements*.txt install only PySide6-Essentials instead.
    install_requires = [
        "PyMuPDF>=1.27.2,<2.0.0",
        "Pillow>=10.0.0",
        "PySide6-Essentials==6.12.0",
        "PySide6-Fluent-Widgets==1.11.3",
        "PySideSix-Frameless-Window==0.8.2",
        "darkdetect>=0.8.0",
        "pywin32>=306; platform_system == 'Windows'",
    ],
    extras_require = {
        "ocr":  ["pytesseract>=0.3.10"],
        "docs": [
            "python-docx>=0.8.11",
            "python-pptx>=0.6.21",
            "openpyxl>=3.1.0",
            "striprtf>=0.0.26",
        ],
        "all": [
            "pytesseract>=0.3.10",
            "python-docx>=0.8.11",
            "python-pptx>=0.6.21",
            "openpyxl>=3.1.0",
            "striprtf>=0.0.26",
        ],
    },
    entry_points = {
        "console_scripts": [
            "paperknife=paperknife.qt.__main__:main",
        ],
    },
)
