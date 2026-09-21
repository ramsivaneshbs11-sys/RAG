@echo off
chcp 65001 >nul
title UPSC RAG — PostgreSQL Automated Setup

echo =================================================================
echo   🐘 UPSC RAG — 1-Click PostgreSQL Setup & Migration
echo =================================================================
echo.

python scripts\setup_postgres.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] PostgreSQL setup could not complete automatically.
    echo Please make sure Docker Desktop is running.
) else (
    echo.
    echo [SUCCESS] PostgreSQL is setup and ready!
)

echo.
pause
