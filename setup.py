"""
Minimal setup.py so `pip install -e .` installs a `paperknife` console script.
"""
from setuptools import setup, find_packages

setup(
    name            = "paperknife-plus-pc",
    version         = "3.2.1",
    description     = "PaperKnife+ PC — 100% local PDF toolkit",
    packages        = find_packages(),
    python_requires = ">=3.10",
    install_requires = [
        "PyMuPDF>=1.23.0,<2.0.0",
        "customtkinter>=5.2.0",
        "Pillow>=10.0.0",
    ],
    extras_require = {
        "dnd":  ["tkinterdnd2>=0.3.0"],
        "ocr":  ["pytesseract>=0.3.10"],
        "docs": [
            "python-docx>=0.8.11",
            "python-pptx>=0.6.21",
            "openpyxl>=3.1.0",
            "striprtf>=0.0.26",
        ],
        "all": [
            "tkinterdnd2>=0.3.0",
            "pytesseract>=0.3.10",
            "python-docx>=0.8.11",
            "python-pptx>=0.6.21",
            "openpyxl>=3.1.0",
            "striprtf>=0.0.26",
        ],
    },
    entry_points = {
        "console_scripts": [
            "paperknife=paperknife.__main__:main",
        ],
    },
)
