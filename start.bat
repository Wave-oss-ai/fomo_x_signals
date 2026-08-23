@echo off
cd /d "%~dp0"

python -c "print('PYOK')" 2>nul | findstr /C:"PYOK" >nul
if errorlevel 1 (
    echo Python isn't installed properly, or Windows' Python Store shortcut
    echo is intercepting it instead of a real Python.
    echo.
    echo Opening the real installer page -- run it, and check the box that
    echo says "Add python.exe to PATH" during setup. Then double-click this
    echo file again.
    echo.
    echo If you already installed Python and still see this message, turn off
    echo the Store shortcut: Settings, then Apps, then Advanced app settings,
    echo then App execution aliases -- switch off python.exe and python3.exe.
    start https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Checking dependencies -- fast after the first time...
pip install -r requirements.txt --quiet --disable-pip-version-check

python app.py

echo.
echo Window closed or the program stopped -- press any key to close this.
pause >nul
