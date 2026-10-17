@echo off
rem P4 launcher. %~dp0 is this file's folder, so no manual cd is needed.
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto no_python

python main.py %*
set CODE=%ERRORLEVEL%
if not "%CODE%"=="0" (
    echo.
    echo [INFO] exit code %CODE% ^(--check returns 1 when a check fails^)
    pause
)
exit /b %CODE%

:no_python
echo [ERROR] python was not found. Install Python 3.10+ and add it to PATH.
pause
exit /b 1
