@echo off
REM ZILAL AI - one-time setup for Windows (PowerShell or double-click).
REM Creates .venv with Python 3.12, installs requirements, and verifies imports.
setlocal
cd /d "%~dp0"

echo.
echo [1/5] Looking for Python 3.12 ...
set "PYCMD="
py -3.12 --version >nul 2>&1 && set "PYCMD=py -3.12"
if not defined PYCMD (
  python --version 2>nul | findstr /R /C:"Python 3\.12\." >nul && set "PYCMD=python"
)
if not defined PYCMD (
  py -3.13 --version >nul 2>&1 && set "PYCMD=py -3.13" && echo     WARNING: Python 3.12 not found; using 3.13 ^(less tested^).
)
if not defined PYCMD (
  echo     ERROR: Python 3.12 was not found.
  echo     Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^),
  echo     or run:  winget install Python.Python.3.12
  goto :fail
)
%PYCMD% --version

echo.
echo [2/5] Creating virtual environment in .venv ...
if exist ".venv\Scripts\python.exe" (
  echo     .venv already exists - reusing it.
) else (
  %PYCMD% -m venv .venv || goto :fail
)

echo.
echo [3/5] Upgrading pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :fail

echo.
echo [4/5] Installing requirements ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail

echo.
echo [5/5] Checking the environment ...
".venv\Scripts\python.exe" check_env.py || goto :fail

echo.
echo SUCCESS: setup finished. Start the platform with run_windows.bat
pause
exit /b 0

:fail
echo.
echo SETUP FAILED - read the message above. Nothing outside this folder was changed.
pause
exit /b 1
