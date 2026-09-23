@echo off
setlocal
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
if exist ".runtime\python.exe" (
 ".runtime\python.exe" -B app\readiness.py
 goto done
)
where py >nul 2>nul
if not errorlevel 1 (
 py -3 -B app\readiness.py
 goto done
)
python -B app\readiness.py
:done
if errorlevel 1 pause
endlocal
