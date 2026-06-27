@echo off
title EcomIQ Services
chcp 65001 >nul
set PYTHON=python

echo ======================================
echo   EcomIQ-RPA - Full Stack Startup
echo ======================================
echo.

echo [1/4] Starting EcomIQ Web Server...
start "EcomIQ-Web" /min %PYTHON% -m src.main.app
timeout /t 3 /nobreak >nul

echo [2/4] Starting Redis...
if exist "C:\Program Files\Redis\redis-server.exe" (
    start "Redis" /min "C:\Program Files\Redis\redis-server.exe"
) else if exist "C:\Progra~1\Redis\redis-server.exe" (
    start "Redis" /min "C:\Progra~1\Redis\redis-server.exe"
) else (
    echo   [WARN] Redis not found, fallback to DB polling
)
timeout /t 2 /nobreak >nul

echo [3/4] Starting Task Worker...
start "Worker" /min %PYTHON% src\rpa\worker.py
timeout /t 2 /nobreak >nul

echo [4/4] Starting File Watcher...
start "FileWatcher" /min %PYTHON% src\rpa\file_watcher.py

echo.
echo ======================================
echo   All services started!
echo   Web:  http://localhost:5000
echo   User: admin / RPAadmin2026
echo ======================================
echo.
echo Stop: Close terminal windows or run:
echo   taskkill /f /im redis-server.exe /im python.exe
pause