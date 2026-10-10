"""
paperknife.__main__
Entry point — run with:
    python -m paperknife [file.pdf]
or (after pip install -e .):
    paperknife
"""
import sys

from paperknife.qt.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
