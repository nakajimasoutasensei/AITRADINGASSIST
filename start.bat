@echo off
REM One-click start for Windows: installs everything the first time, then opens the dashboard.
cd /d "%~dp0"
if not exist .venv (
  echo Creating Python environment...
  python -m venv .venv || (echo Python not found. Install Python 3.11+ from python.org and tick "Add to PATH". & pause & exit /b 1)
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
if not exist .env copy .env.example .env >nul
start "" cmd /c "timeout /t 5 >nul & start http://127.0.0.1:8000"
python -m uvicorn backend.app.main:app --port 8000
pause
