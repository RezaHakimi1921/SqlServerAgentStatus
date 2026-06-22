@echo off
echo ====================================
echo  SQL Agent Monitor - Setup
echo ====================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python peyda nashod!
    echo Python ro az https://python.org nasbkon (v3.10+)
    echo Moshkele Add to PATH ro faramoosh nakon!
    pause
    exit /b 1
)

echo [1/2] Package ha dar hal nasb...
pip install dash==2.17.1 plotly==5.22.0 pymssql==2.3.1 pandas==2.2.2
if errorlevel 1 (
    echo.
    echo [ERROR] Nasb ba moshkel mavajahe shod.
    pause
    exit /b 1
)

echo.
echo [2/2] Amaade!
echo.
echo Baraye ejra: run.bat ra doble click kon
echo ya dastoor zir ra bede:
echo   python app.py
echo.
pause
