"""
paperknife.tools  —  import order determines sidebar display order.
"""
# Every import registers its tools via @register; the names are not used.
# ruff: noqa: F401
# READ
from . import reader       # 📖  Read / Preview  ★ NEW

# ORGANISE
from . import merge        # 📎  Merge
from . import split        # ✂   Split
from . import rotate       # 🔄  Rotate & Reorder
from . import bookmarks    # 🔖  Split by Bookmarks
from . import toc          # 📑  Bookmarks / TOC  ★
from . import batch        # ⚙   Batch  ★

# ENHANCE
from .password import PasswordTool
from .enhance import CompressTool
from .enhance import WatermarkTool
from .enhance import NormaliseTool
from . import headerfooter  # 📋  Header / Footer  ★
from . import crop          # ✂   Crop / Trim  ★
from . import pdftools      # 🔧  PDF Tools  ★

# CONVERT
from .convert import Img2PdfTool
from .convert import Pdf2ImgTool
from .convert import ExtractTool
from .convert import Pdf2DocTool
from .convert import Doc2PdfTool

# CONTENT
from . import edit_text
from . import find_replace
from . import annotate
from . import redact        # ⬛  Redact  ★
from . import ocr
from . import metadata      # 🏷   Metadata  ★

# SETTINGS
from . import settings      # ⚙   Preferences  ★

from ..tool_base import TOOLS
__all__ = ["TOOLS"]
