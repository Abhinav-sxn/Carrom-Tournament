@echo off
setlocal

set "ROOT=%~dp0"
set "PYDIR=%ROOT%python"

if exist "%PYDIR%\python.exe" (
    set "PYTHON=%PYDIR%\python.exe"
) else (
    set "PYTHON=python"
)

echo ================================================
echo   Carrom Board Tournament Manager
echo ================================================
echo.
echo Starting app...
echo.
echo Access on this device : http://localhost:8501
echo Access on others (same network): use this PC's local IP, port 8501
echo.
"%PYTHON%" -m streamlit run "%ROOT%Main.py" --server.address 0.0.0.0
pause
