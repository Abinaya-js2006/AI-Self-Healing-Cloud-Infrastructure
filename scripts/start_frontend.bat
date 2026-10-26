@echo off
setlocal
cd /d "%~dp0..\frontend"
if not exist "node_modules" (
  echo Installing frontend dependencies...
  npm ci
)
if not exist ".env" copy ".env.example" ".env"
echo Starting React dashboard...
npm run dev
