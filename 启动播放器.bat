@echo off
chcp 65001 >nul
setlocal EnableExtensions DisableDelayedExpansion
title Ariadne - 本地曲谱播放器
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "ARIADNE_PYTHON=%CD%\.venv\Scripts\python.exe"

if exist "%ARIADNE_PYTHON%" goto check_dependencies
echo 正在准备本地播放环境...
where py >nul 2>nul
if errorlevel 1 goto try_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto try_python
py -3 -m venv ".venv"
goto check_environment

:try_python
where python >nul 2>nul
if errorlevel 1 goto missing_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto missing_python
python -m venv ".venv"

:check_environment
if not exist "%ARIADNE_PYTHON%" goto failed

:check_dependencies
"%ARIADNE_PYTHON%" -c "import mistune, pypdfium2, PIL" >nul 2>nul
if not errorlevel 1 goto launch
echo 首次启动需要安装播放组件，请保持网络连接...
"%ARIADNE_PYTHON%" -m pip install -r "requirements.txt"
if errorlevel 1 goto failed

:launch
if "%ARIADNE_LAUNCH_CHECK%"=="1" goto launch_check
"%ARIADNE_PYTHON%" "scripts\launch_local.py" --track mahler-4
if errorlevel 1 goto failed
exit /b 0

:launch_check
"%ARIADNE_PYTHON%" "scripts\launch_local.py" --track mahler-4 --check
exit /b %errorlevel%

:missing_python
echo 未找到 Python 3.11 或更新版本，请先安装 Python 后再次双击本文件。
goto wait_error

:failed
echo 播放器未能启动，请查看上方提示；本地素材没有被修改。

:wait_error
echo 按任意键关闭此窗口。
pause >nul
exit /b 1
