@echo off
title RPADataHub Services
cd /d C:\Users\YourUsername\Desktop\RPADataHub
set PYTHON=C:\Users\YourUsername\AppData\Local\Programs\Python\Python310\python.exe
set REDIS_URL=redis://:your-redis-password@localhost:6379

echo [%date% %time%] Starting RPADataHub...
echo.

echo Starting Redis...
start "Redis" /min C:\Progra~1\Redis\redis-server.exe
timeout /t 2 /nobreak >nul

echo Starting Admin Server...
start "Admin" /min %PYTHON% admin_server.py
timeout /t 3 /nobreak >nul

echo Starting File Watcher...
start "FileWatcher" /min %PYTHON% file_watcher.py
timeout /t 2 /nobreak >nul

echo Starting Worker...
start "Worker" /min %PYTHON% worker.py

echo.
echo All services started: Admin(5000) FileWatcher Worker
echo.
pause
