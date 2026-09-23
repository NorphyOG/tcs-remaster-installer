@echo off
setlocal
cd /d "%~dp0"
set PYTHON_MANAGER_AUTOMATIC_INSTALL=false
set PYTHONDONTWRITEBYTECODE=1
if exist ".runtime\python.exe" goto portable
where py >nul 2>nul
if errorlevel 1 goto normalpython
py -3 -c "import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 goto normalpython
py -3 -B app\updater.py
goto done
:normalpython
where python >nul 2>nul
if errorlevel 1 goto setup
python -c "import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 goto setup
python -B app\updater.py
goto done
:setup
echo Python 3.10 oder neuer wurde nicht gefunden.
echo Der Einrichtungsassistent bietet einen lokalen Download von python.org an.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "tools\setup_runtime.ps1"
if errorlevel 1 goto missing
if not exist ".runtime\python.exe" goto missing
:portable
".runtime\python.exe" -B app\updater.py
goto done
:missing
echo.
echo Einrichtung nicht abgeschlossen. README.html enthaelt den offiziellen Download-Link.
start "" "README.html"
pause
exit /b 1
:done
if errorlevel 1 (
 echo.
 echo Das Update konnte nicht abgeschlossen werden. Die Fehlermeldung steht oben.
 pause
)
endlocal
