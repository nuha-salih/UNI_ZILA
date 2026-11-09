@echo off
REM ZILAL AI - start the platform using the project's own virtual environment.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo The virtual environment was not found. Run setup_windows.bat first.
  pause
  exit /b 1
)
echo Starting ZILAL AI ...
echo When it is ready, open:  http://localhost:8501
echo Keep this window open while using the platform. Press Ctrl+C to stop.
REM Open the browser after a short delay (headless mode skips Streamlit's first-run email prompt).
start "" /b cmd /c "timeout /t 8 /nobreak >nul & start "" http://localhost:8501"
".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
pause
