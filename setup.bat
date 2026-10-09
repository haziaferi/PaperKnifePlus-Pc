@echo off
cd /d "%~dp0"
echo ============================================================
echo  PaperKnife+ PC  v4.0.0  ^|  Setup
echo ============================================================
echo.
python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10 or later not found on PATH.
    echo         Install Python 3.10+ from https://python.org
    pause & exit /b 1
)
if not exist .venv\Scripts\python.exe (
    echo [1/3] Creating virtual environment .venv ...
    python -m venv .venv
    if errorlevel 1 ( echo [ERROR] Could not create .venv. & pause & exit /b 1 )
) else (
    echo [1/3] Using existing .venv
)
echo [2/3] Upgrading pip...
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
if errorlevel 1 ( echo [ERROR] pip upgrade failed. & pause & exit /b 1 )
echo [3/3] Installing dependencies from requirements.txt...
.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if errorlevel 1 ( echo [ERROR] Dependency install failed. & pause & exit /b 1 )
.venv\Scripts\python.exe -m pip install --no-deps -r requirements-fluent.txt --quiet
if errorlevel 1 ( echo [ERROR] Dependency install failed. & pause & exit /b 1 )
echo.
echo [OK] Setup complete.
echo      Double-click run.bat to start the app,
echo      or run:  .venv\Scripts\python.exe -m paperknife.qt
echo.
pause
