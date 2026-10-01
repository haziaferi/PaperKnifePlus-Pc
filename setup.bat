@echo off
echo ============================================================
echo  PaperKnife+ PC  v3.2.1  ^|  Setup
echo ============================================================
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH.
    echo         Install Python 3.10+ from https://python.org
    pause & exit /b 1
)
echo [1/3] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo [2/3] Installing core dependencies...
python -m pip install "PyMuPDF>=1.23.0,<2.0.0" "customtkinter>=5.2.0" "Pillow>=10.0.0" --quiet
echo [3/3] Installing optional dependencies...
python -m pip install tkinterdnd2 pytesseract python-docx python-pptx openpyxl striprtf --quiet
echo.
echo [OK] Setup complete.
echo      Run the app with:  python -m paperknife
echo      Or double-click:   run.bat
echo.
pause
