@echo off
setlocal

set "ROOT=%~dp0"
set "PYDIR=%ROOT%python"
set "PYVER=3.11.9"
set "PYZIP=python-%PYVER%-embed-amd64.zip"
set "PYURL=https://www.python.org/ftp/python/%PYVER%/%PYZIP%"
set "PIPURL=https://bootstrap.pypa.io/get-pip.py"

echo ================================================
echo   Carrom Tournament  —  One-time Setup
echo ================================================
echo.

:: ── Step 1: Download + extract Python embeddable ──────────────────────────
if exist "%PYDIR%\python.exe" (
    echo [1/4] Python runtime already present. Skipping download.
    goto :install_packages
)

echo [1/4] Downloading Python %PYVER% embeddable ^(~25 MB^)...
powershell -NoProfile -Command ^
  "[Net.ServicePointManager]::SecurityProtocol = 'Tls12,Tls13'; (New-Object Net.WebClient).DownloadFile('%PYURL%', '%ROOT%%PYZIP%')"
if not exist "%ROOT%%PYZIP%" (
    echo ERROR: Download failed. Check your internet connection and try again.
    pause & exit /b 1
)

echo [2/4] Extracting...
powershell -NoProfile -Command ^
  "Expand-Archive -Path '%ROOT%%PYZIP%' -DestinationPath '%PYDIR%' -Force"
del "%ROOT%%PYZIP%"

:: Enable site-packages (required for pip) by uncommenting "import site" in the .pth file
for %%f in ("%PYDIR%\python3*._pth") do (
    powershell -NoProfile -Command ^
      "(Get-Content '%%f') -replace '^#import site', 'import site' | Set-Content '%%f'"
)

:: ── Step 2: Bootstrap pip ─────────────────────────────────────────────────
echo [3/4] Bootstrapping pip...
powershell -NoProfile -Command ^
  "[Net.ServicePointManager]::SecurityProtocol = 'Tls12,Tls13'; (New-Object Net.WebClient).DownloadFile('%PIPURL%', '%PYDIR%\get-pip.py')"
"%PYDIR%\python.exe" "%PYDIR%\get-pip.py" --no-warn-script-location --quiet
del "%PYDIR%\get-pip.py"

:install_packages
:: ── Step 3: Install dependencies ─────────────────────────────────────────
echo [4/4] Installing packages ^(streamlit, pandas, openpyxl, matplotlib^)...
"%PYDIR%\python.exe" -m pip install --no-warn-script-location --quiet ^
    "streamlit>=1.36.0" "pandas>=2.0.0" "openpyxl>=3.1.0" "matplotlib"

echo.
echo ================================================
echo   Setup complete!
echo   Double-click run.bat to launch the app.
echo ================================================
echo.
pause
