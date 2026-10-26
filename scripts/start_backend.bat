@echo off
setlocal
cd /d "%~dp0..\backend"
if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  py -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist ".env" copy ".env.example" ".env"
echo Starting Flask API at http://localhost:5000
python app.py
