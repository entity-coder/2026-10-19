@echo off
REM DairyManager — one-click Windows .exe build (run once on the shop PC).
REM Requires Python 3.10+ with pip. Installs deps, then builds a single .exe.
setlocal
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not on PATH. Install Python 3.10+ from python.org
    echo and tick "Add python.exe to PATH" during setup, then re-run this file.
    pause
    exit /b 1
)

echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo Dependency install failed. Check your internet connection.
    pause
    exit /b 1
)

echo Building DairyManager.exe ...
python -m PyInstaller --noconfirm --onefile --windowed ^
    --name DairyManager ^
    --collect-all customtkinter ^
    --hidden-import reportlab ^
    main.py
if errorlevel 1 (
    echo Build failed. Scroll up for the error.
    pause
    exit /b 1
)

echo.
echo Build complete: dist\DairyManager.exe
echo Copy dist\DairyManager.exe anywhere; your data stays in the dairy_data\
echo folder next to the .exe. Back up that folder regularly (Backup screen).
pause
