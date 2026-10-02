@echo off
:: PaperKnife+ PC — Windows build pipeline
::
:: Build from a clean venv (see MANUAL.md section 9):
::   python -m venv .venv
::   .venv\Scripts\activate
::   pip install -r requirements.txt pyinstaller
:: If no venv is active, .venv\Scripts\python.exe is used when it exists.
:: Do not build from conda or the global Python: PyInstaller bundles every
:: package its hooks can reach there, and still probes conda's MKL packages
:: ("Library not found: msmpi.dll / ur_loader.dll / sycl8.dll") although
:: the spec excludes them.
::
:: Usage (unsigned, for testing):
::   build_windows.bat
::
:: Usage (signed release — requires an OV/EV cert PFX):
::   set PFX_PASSWORD=YourPfxPassword
::   build_windows.bat  C:\path\to\cert.pfx
:: The password is read from PFX_PASSWORD so it stays out of this script's
:: command line and the shell history; clear it afterwards (set PFX_PASSWORD=).
:: signtool still receives it as /p, so it is visible in the command line of
:: each signtool process while signing runs.
::
:: signtool.exe is located automatically from the Windows 10/11 SDK.
:: If it cannot be found, signing is skipped with a warning and the
:: build continues so you can still test-install the unsigned package.

setlocal enabledelayedexpansion
:: A relative certificate path is the caller's: resolve it before the cd.
set "CERT_PFX="
if not "%~1"=="" set "CERT_PFX=%~f1"
:: Run from the script's folder: the clean step below deletes build\ here.
cd /d "%~dp0"

set APP_NAME=PaperKnifePlusPC
set APP_VERSION=3.2.2
set TIMESTAMP_URL=http://timestamp.digicert.com

echo.
echo ============================================================
echo  %APP_NAME% v%APP_VERSION%  ^|  Windows Build
echo ============================================================
echo.

if not "%~2"=="" (
    echo [ERROR] Do not pass the PFX password on the command line.
    echo         Set it in the PFX_PASSWORD environment variable instead.
    exit /b 1
)
if not "!CERT_PFX!"=="" if "!PFX_PASSWORD!"=="" (
    echo [ERROR] A certificate was given but PFX_PASSWORD is not set.
    exit /b 1
)

:: ── Python environment ────────────────────────────────────────────────────────
set "PY=python"
if not defined VIRTUAL_ENV if exist .venv\Scripts\python.exe set "PY=.venv\Scripts\python.exe"
"!PY!" -c "import sys; sys.exit(sys.prefix == sys.base_prefix)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Not running in a virtual environment.
    echo         Create and activate a clean venv first; see the header of this file.
    exit /b 1
)
"!PY!" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller is not installed in the build venv.
    echo         Run:  pip install pyinstaller
    exit /b 1
)

:: ── Locate signtool.exe ───────────────────────────────────────────────────────
:: %ProgramFiles(x86)% contains parentheses that confuse the batch parser
:: inside for-loop blocks.  Hoist it into a plain variable first.
set "_PF86=%ProgramFiles(x86)%"
set "_PF64=%ProgramFiles%"
set SIGNTOOL=

:: 1. Check if already on PATH
where signtool >nul 2>&1 && set SIGNTOOL=signtool

:: 2. Search Windows SDK — x86 host (most common on 64-bit Windows)
if "%SIGNTOOL%"=="" (
    for /f "delims=" %%d in ('dir /b /ad "!_PF86!\Windows Kits\10\bin" 2^>nul') do if exist "!_PF86!\Windows Kits\10\bin\%%d\x64\signtool.exe" set "SIGNTOOL=!_PF86!\Windows Kits\10\bin\%%d\x64\signtool.exe"
)

:: 3. Search Windows SDK — native 64-bit / ARM64 host
if "%SIGNTOOL%"=="" (
    for /f "delims=" %%d in ('dir /b /ad "!_PF64!\Windows Kits\10\bin" 2^>nul') do if exist "!_PF64!\Windows Kits\10\bin\%%d\x64\signtool.exe" set "SIGNTOOL=!_PF64!\Windows Kits\10\bin\%%d\x64\signtool.exe"
)

if "%SIGNTOOL%"=="" (
    echo [INFO] signtool.exe not found.
    echo        To sign, install the Windows 10/11 SDK:
    echo        https://developer.microsoft.com/windows/downloads/windows-sdk/
    echo        Build will continue unsigned.
    echo.
) else (
    echo [INFO] signtool found: !SIGNTOOL!
)

:: ── Locate makensis.exe (the NSIS installer does not add itself to PATH) ─────
set MAKENSIS=
where makensis >nul 2>&1 && set MAKENSIS=makensis
if "%MAKENSIS%"=="" if exist "!_PF86!\NSIS\makensis.exe" set "MAKENSIS=!_PF86!\NSIS\makensis.exe"
if "%MAKENSIS%"=="" if exist "!_PF64!\NSIS\makensis.exe" set "MAKENSIS=!_PF64!\NSIS\makensis.exe"

:: ── Step 1: Clean previous dist ───────────────────────────────────────────────
echo [1/5] Cleaning previous dist...
if exist dist\%APP_NAME% rmdir /s /q dist\%APP_NAME%
if exist build              rmdir /s /q build

:: ── Step 2: PyInstaller ───────────────────────────────────────────────────────
echo [2/5] Running PyInstaller...
"!PY!" -m PyInstaller paperknife.spec --clean --noconfirm --log-level WARN
if errorlevel 1 ( echo [ERROR] PyInstaller failed. & exit /b 1 )

:: ── Step 3: Sign EXE + all DLL/PYD files ──────────────────────────────────────
if "!CERT_PFX!"=="" (
    echo [3/5] No cert provided — skipping signing.
    echo        Unsigned build is fine for local testing.
    echo        SmartScreen will warn end-users until the EXE is signed.
) else if "!SIGNTOOL!"=="" (
    echo [3/5] Cert provided but signtool not found — skipping signing.
    echo        Install the Windows SDK and rerun to produce a signed build.
) else (
    echo [3/5] Signing EXE...
    "!SIGNTOOL!" sign /fd sha256 /tr %TIMESTAMP_URL% /td sha256 ^
        /f "!CERT_PFX!" /p "!PFX_PASSWORD!" ^
        "dist\%APP_NAME%\%APP_NAME%.exe"
    if errorlevel 1 ( echo [ERROR] Signing EXE failed. & goto :fail )

    echo [3/5] Signing all bundled DLL and PYD files ^(WIN-DEP-02^)...
    for /r "dist\%APP_NAME%" %%f in (*.dll *.pyd) do (
        "!SIGNTOOL!" sign /fd sha256 /tr %TIMESTAMP_URL% /td sha256 ^
            /f "!CERT_PFX!" /p "!PFX_PASSWORD!" "%%f"
        if errorlevel 1 ( echo [ERROR] Signing %%~nxf failed. & goto :fail )
    )
    echo [3/5] Signing complete.
)

:: ── Step 4: NSIS installer ────────────────────────────────────────────────────
set MADE_INSTALLER=0
echo [4/5] Building NSIS installer...
if "!MAKENSIS!"=="" (
    echo [WARN] makensis not found — skipping Steps 4 and 5.
    echo        Install NSIS 3.x from https://nsis.sourceforge.io/
    echo        Then rerun this script, or run manually:  makensis installer.nsi
    goto :summary
)
"!MAKENSIS!" installer.nsi
if errorlevel 1 ( echo [ERROR] makensis failed. & exit /b 1 )
set MADE_INSTALLER=1

:: ── Step 5: Sign installer ────────────────────────────────────────────────────
if not "!CERT_PFX!"=="" if not "!SIGNTOOL!"=="" (
    echo [5/5] Signing installer EXE...
    "!SIGNTOOL!" sign /fd sha256 /tr %TIMESTAMP_URL% /td sha256 ^
        /f "!CERT_PFX!" /p "!PFX_PASSWORD!" ^
        "%APP_NAME%-%APP_VERSION%-Setup.exe"
    if errorlevel 1 ( echo [ERROR] Signing installer failed. & goto :fail )
    goto :summary
)
echo [5/5] Installer not signed. Run with a certificate before distributing.

:summary
echo.
echo ============================================================
echo  Bundle:    dist\%APP_NAME%\%APP_NAME%.exe
if "!MADE_INSTALLER!"=="1" (
    echo  Installer: %APP_NAME%-%APP_VERSION%-Setup.exe
    echo.
    echo  Test silent install:
    echo    %APP_NAME%-%APP_VERSION%-Setup.exe /S
    echo  Test silent uninstall ^(waits until files are removed^):
    echo    "%%LOCALAPPDATA%%\%APP_NAME%\Uninstall.exe" /S _?=%%LOCALAPPDATA%%\%APP_NAME%
)
echo ============================================================
echo.
endlocal
exit /b 0

:: exit /b inside a nested block loses its code under cmd /c; jump here instead.
:fail
endlocal
exit /b 1
