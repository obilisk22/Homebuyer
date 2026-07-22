@echo off
setlocal
REM Cursor stop hook launcher (Windows). Passes stdin JSON through to Python.
set "PATH=C:\Program Files\Git\cmd;C:\Program Files\Git\bin;%PATH%"

REM Project root = parent of .cursor/
cd /d "%~dp0..\.."

if exist "%~dp0..\..\.venv\Scripts\python.exe" (
  "%~dp0..\..\.venv\Scripts\python.exe" "%~dp0auto-commit.py"
  exit /b %ERRORLEVEL%
)

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%~dp0auto-commit.py"
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python "%~dp0auto-commit.py"
  exit /b %ERRORLEVEL%
)

REM No Python — fail open (do not block the agent).
echo {}
exit /b 0
