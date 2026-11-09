@echo off
REM ZILAL AI - run the automated test suite (installs pytest into .venv if needed).
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -q -r requirements-dev.txt
".venv\Scripts\python.exe" -m pytest -q
pause
