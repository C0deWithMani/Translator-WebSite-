@echo off
cd /d "%~dp0"
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)
echo Installing packages...
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo Starting VoiceForge Plus...
.venv\Scripts\python.exe app.py
pause
