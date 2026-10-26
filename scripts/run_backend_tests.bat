@echo off
setlocal
cd /d "%~dp0..\backend"
if not exist ".venv\Scripts\python.exe" (
  echo Please run scripts\start_backend.bat once to set up the environment.
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m pytest -q
pause
