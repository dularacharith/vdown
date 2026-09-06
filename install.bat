@echo off
setlocal
echo === Installing Simple Downloader (vdown) on Windows ===

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Error: Python is not installed or not found in PATH.
    echo Please install Python from https://www.python.org/ or via 'winget install Python.Python.3.12'
    exit /b 1
)

where ffmpeg >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [Warning] FFmpeg is not found in PATH.
    echo To install FFmpeg on Windows, run: winget install Gyan.FFmpeg
)

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Installing dependencies...
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\python.exe -m pip install -e .

echo.
echo [OK] Installation complete!
echo You can run vdown using:
echo   - .\vdown.bat [options]
echo   - Or activate the environment: .\.venv\Scripts\activate ^& vdown [options]
