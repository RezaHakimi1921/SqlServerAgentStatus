@echo off
cd /d "%~dp0"
echo ====================================
echo  SQL Agent Monitor - Setup
echo ====================================
echo.

REM --- Try py launcher first, then python ---
set PYTHON_CMD=
py --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=py
    goto :found_python
)
python --version >nul 2>&1
if not errorlevel 1 (
    set PYTHON_CMD=python
    goto :found_python
)

echo [ERROR] Python peyda nashod!
echo.
echo 1. Python ro az https://www.python.org/downloads/ download kon
echo 2. Moghe nasb, "Add python.exe to PATH" ra tik bezanid
echo 3. Baad az nasb, in file ra doble click kon
echo.
pause
exit /b 1

:found_python
echo Python: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.

echo [1/2] Package ha dar hal nasb...
%PYTHON_CMD% -m pip install --upgrade pip setuptools setuptools_scm -q
%PYTHON_CMD% -m pip install dash plotly pandas pymssql

if errorlevel 1 (
    echo.
    echo [ERROR] Nasb ba moshkel mavajahe shod.
    echo Terminal ro ba dastresiye Admin ejra kon va dobare amtahan kon.
    pause
    exit /b 1
)

echo.
echo [OK] Hame package ha nasb shodand!
echo.
echo Baraye ejra: run.bat ra doble click kon
echo.
pause
