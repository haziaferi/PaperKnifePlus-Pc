@echo off
:: PaperKnife+ PC — Windows build pipeline
::
:: Usage (unsigned, for testing):
::   build_windows.bat
::
:: Usage (signed release — requires an OV/EV cert PFX):
::   build_windows.bat  C:\path\to\cert.pfx  YourPfxPassword
::
:: signtool.exe is located automatically from the Windows 10/11 SDK.
:: If it cannot be found, signing is skipped with a warning and the
:: build continues so you can still test-install the unsigned package.
::
:: Warnings like "Library not found: msmpi.dll / ur_loader.dll / sycl8.dll"
:: are harmless — they come from unused Intel MKL DLLs in the conda
:: environment and are excluded by the spec. The build succeeds regardless.

setlocal enabledelayedexpansion

set APP_NAME=PaperKnifePlusPC
set APP_VERSION=3.2.2
set TIMESTAMP_URL=http://timestamp.digicert.com
set CERT_PFX=%~1
set CERT_PWD=%~2

echo.
echo ============================================================
echo  %APP_NAME% v%APP_VERSION%  ^|  Windows Build
echo ============================================================
echo.

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

:: ── Step 1: Clean previous dist ───────────────────────────────────────────────
echo [1/5] Cleaning previous dist...
if exist dist\%APP_NAME% rmdir /s /q dist\%APP_NAME%
if exist build              rmdir /s /q build

:: ── Step 2: PyInstaller ───────────────────────────────────────────────────────
echo [2/5] Running PyInstaller...
pyinstaller paperknife.spec --clean --log-level WARN
if errorlevel 1 ( echo [ERROR] PyInstaller failed. & exit /b 1 )

:: ── Step 3: Sign EXE + all DLLs ──────────────────────────────────────────────
if "%CERT_PFX%"=="" (
    echo [3/5] No cert provided — skipping signing.
    echo        Unsigned build is fine for local testing.
    echo        SmartScreen will warn end-users until the EXE is signed.
) else if "!SIGNTOOL!"=="" (
    echo [3/5] Cert provided but signtool not found — skipping signing.
    echo        Install the Windows SDK and rerun to produce a signed build.
) else (
    echo [3/5] Signing EXE...
    !SIGNTOOL! sign /fd sha256 /tr %TIMESTAMP_URL% /td sha256 ^
        /f "%CERT_PFX%" /p "%CERT_PWD%" ^
        "dist\%APP_NAME%\%APP_NAME%.exe"
    if errorlevel 1 ( echo [ERROR] Signing EXE failed. & exit /b 1 )

    echo [3/5] Signing all bundled DLLs ^(WIN-DEP-02^)...
    for /r "dist\%APP_NAME%" %%f in (*.dll) do (
        !SIGNTOOL! sign /fd sha256 /tr %TIMESTAMP_URL% /td sha256 ^
            /f "%CERT_PFX%" /p "%CERT_PWD%" "%%f"
    )
    echo [3/5] Signing complete.
)

:: ── Step 4: NSIS installer ────────────────────────────────────────────────────
echo [4/5] Building NSIS installer...
where makensis >nul 2>&1
if errorlevel 1 (
    echo [WARN] makensis not on PATH — skipping installer.
    echo        Install NSIS 3.x from https://nsis.sourceforge.io/
    echo        Then rerun this script, or run manually:  makensis installer.nsi
    goto :sign_installer_skip
)
makensis installer.nsi
if errorlevel 1 ( echo [ERROR] makensis failed. & exit /b 1 )

:: ── Step 5: Sign installer ────────────────────────────────────────────────────
if not "%CERT_PFX%"=="" if not "%SIGNTOOL%"=="" (
    echo [5/5] Signing installer EXE...
    !SIGNTOOL! sign /fd sha256 /tr %TIMESTAMP_URL% /td sha256 ^
        /f "%CERT_PFX%" /p "%CERT_PWD%" ^
        "%APP_NAME%-%APP_VERSION%-Setup.exe"
) else (
    echo [5/5] Installer not signed. Run with cert args before distributing.
)

:sign_installer_skip
echo.
echo ============================================================
echo  Bundle:    dist\%APP_NAME%\%APP_NAME%.exe
echo  Installer: %APP_NAME%-%APP_VERSION%-Setup.exe
echo.
echo  Test silent install:
echo    %APP_NAME%-%APP_VERSION%-Setup.exe /S
echo  Test uninstall:
echo    "%%LOCALAPPDATA%%\%APP_NAME%\Uninstall.exe" /S
echo ============================================================
echo.
endlocal
