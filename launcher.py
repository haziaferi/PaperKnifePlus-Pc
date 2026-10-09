"""Entry script of the frozen build: PyInstaller runs a script, and the Qt
app's own __main__ uses package-relative imports."""
import sys

from paperknife.qt.__main__ import main

sys.exit(main())
