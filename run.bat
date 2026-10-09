@echo off
cd /d "%~dp0"
set "PY=python"
if exist .venv\Scripts\python.exe set "PY=.venv\Scripts\python.exe"
"%PY%" -m paperknife.qt
if errorlevel 1 pause
