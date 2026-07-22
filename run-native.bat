@echo off
cd /d "%~dp0"
set HOMEBUY_NATIVE=1
".venv\Scripts\python.exe" -m app.main --native
pause
