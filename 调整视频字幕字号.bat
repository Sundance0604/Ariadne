@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" goto missing_python
".venv\Scripts\python.exe" "scripts\video_export\edit_video_captions.py" --fonts
if errorlevel 1 goto failed
exit /b 0
:missing_python
echo Project Python was not found. Please start the player setup first.
:failed
echo The editor could not start. Please keep this message for troubleshooting.
pause
exit /b 1
