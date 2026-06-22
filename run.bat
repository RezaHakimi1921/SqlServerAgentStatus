@echo off
cd /d "%~dp0"
echo ====================================
echo  SQL Agent Monitor - Starting...
echo ====================================
echo.

set PYTHON_CMD=
py --version >nul 2>&1
if not errorlevel 1 (set PYTHON_CMD=py) else (set PYTHON_CMD=python)

echo Dashboard: http://localhost:8050
echo Baraye togf: Ctrl+C ra bezanid
echo.
%PYTHON_CMD% app.py
pause
