@echo off
setlocal
set SCRIPT_DIR=%~dp0
if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    start "" "%SCRIPT_DIR%.venv\Scripts\python.exe" -m simple_downloader.gui.app %*
) else (
    start "" python -m simple_downloader.gui.app %*
)
