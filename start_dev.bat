@echo off
title UPSC Chatbot — Dev Server
color 0A

echo.
echo  =========================================
echo    UPSC CHATBOT — FULL DEV ENVIRONMENT
echo  =========================================
echo.
echo  Starting services:
echo    [1] Backend  (FastAPI + Hot Reload)  :8000
echo    [2] Frontend (Vite + HMR)            :5173
echo    [3] News Pipeline (auto-runs inside backend)
echo.
echo  ─────────────────────────────────────────
echo  [P] Production mode  — builds frontend then
echo      serves everything from FastAPI :8000 only
echo      (no Vite, no Node.js at runtime)
echo  ─────────────────────────────────────────
echo.
set /p MODE="  Press [P] for production mode, or ENTER for dev mode: "

if /i "%MODE%"=="P" goto production
goto dev_mode

:production
echo.
echo  [P] Building React frontend for production...
cd /d %~dp0frontend
call npm run build
if errorlevel 1 (
    echo  [ERROR] npm run build failed! Check frontend errors above.
    pause
    exit /b 1
)
cd /d %~dp0
echo  [P] Frontend built successfully. Starting FastAPI only on :8000...
start "UPSC RAG (Production)" cmd /k "cd /d %~dp0 && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info"
echo.
echo  =========================================
echo    PRODUCTION MODE — App running at:
echo    http://localhost:8000
echo    API Docs: http://localhost:8000/docs
echo  =========================================
echo.
echo  Press any key to open in browser...
pause >nul
start http://localhost:8000
exit /b 0

:dev_mode
echo.

REM ── Kill anything on ports 8000 and 5173 first ──
echo  [*] Clearing ports 8000 and 5173...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 >nul

REM ── Start Backend: FastAPI (unified backend) ──
echo  [1] Launching Unified RAG Backend with hot-reload...
start "UPSC RAG Backend" cmd /k "cd /d %~dp0 && echo  FastAPI Backend starting on :8000 && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level info"


REM ── Wait for backend to be ready ──
echo  [*] Waiting for backend to start...
timeout /t 4 >nul

REM ── Start Frontend with npm run dev ──
echo  [2] Launching Frontend (Vite)...
start "UPSC Frontend (Vite)" cmd /k "cd /d %~dp0frontend && echo  Frontend starting... && npm run dev"

echo.
echo  =========================================
echo    ALL SERVICES STARTED!
echo  =========================================
echo.
echo    Backend  : http://localhost:8000
echo    API Docs : http://localhost:8000/docs
echo    Frontend : http://localhost:5173
echo.
echo    uvicorn --reload watches:
echo      backend\*.py   (API routes, routers)
echo      pipeline\*.py  (scraper, scheduler)
echo.
echo    News auto-collects 2 TIMES A DAY (08:00 and 20:00).
echo    Frontend auto-refreshes every 5 MIN.
echo.
echo  Press any key to open the app in browser...
pause >nul
start http://localhost:5173/home
