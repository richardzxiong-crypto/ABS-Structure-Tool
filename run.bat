@echo off
REM One-click launcher for Windows: sets up (or refreshes) dependencies,
REM starts the API and UI, and opens the app in your browser.
REM Safe to re-run after every git pull.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python is not installed. Get 3.11+ from https://www.python.org/downloads/
  echo        ^(check "Add python.exe to PATH" during install^) and re-run.
  pause & exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo ERROR: Node.js is not installed. Get 18+ from https://nodejs.org and re-run.
  pause & exit /b 1
)

where uv >nul 2>nul
if errorlevel 1 (
  echo Installing uv ^(fast Python package manager, one-time^)...
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

echo.
echo == Syncing backend dependencies...
cd backend
uv venv .venv --allow-existing -q
uv pip install -q -e ".[dev]"
if errorlevel 1 ( echo ERROR: backend setup failed & pause & exit /b 1 )
cd ..

echo == Syncing frontend dependencies...
cd frontend
call npm install --silent --no-audit --no-fund
if errorlevel 1 ( echo ERROR: npm install failed & pause & exit /b 1 )
cd ..

echo == Starting API on http://localhost:8000 ...
start "ABS API" /min cmd /c "cd backend && .venv\Scripts\python -m uvicorn app.main:app --port 8000"

echo == Starting UI on http://localhost:5173 ...
start "ABS UI" /min cmd /c "cd frontend && npx vite --port 5173"

echo == Waiting for the app to come up...
timeout /t 6 /nobreak >nul
start http://localhost:5173

echo.
echo App is running in two minimized windows ("ABS API" and "ABS UI").
echo Close those two windows to stop it.
pause
