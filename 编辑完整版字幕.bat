@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"
".venv\Scripts\python.exe" "scripts\video_export\edit_video_captions.py" --full
if errorlevel 1 pause
