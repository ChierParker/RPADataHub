@echo off
title EcomIQ 全部服务
chcp 65001 >nul
cd /d %~dp0..
set PYTHON=python

echo ======================================
echo   EcomIQ — 电商智能工具集 全栈启动
echo ======================================
echo.

echo [1/4] 启动 EcomIQ Web 管理台...
start "EcomIQ-Web" /min %PYTHON% -m EcomIQ.app
timeout /t 3 /nobreak >nul

echo [2/4] 启动 Redis 消息队列...
if exist "C:\Program Files\Redis\redis-server.exe" (
    start "Redis" /min "C:\Program Files\Redis\redis-server.exe"
) else if exist "C:\Progra~1\Redis\redis-server.exe" (
    start "Redis" /min "C:\Progra~1\Redis\redis-server.exe"
) else (
    echo   [WARN] Redis 未找到, MQ 降级为数据库轮询
)
timeout /t 2 /nobreak >nul

echo [3/4] 启动 Worker 任务执行器...
start "Worker" /min %PYTHON% RPADataHub\worker.py
timeout /t 2 /nobreak >nul

echo [4/4] 启动 File Watcher 文件监控...
start "FileWatcher" /min %PYTHON% RPADataHub\file_watcher.py

echo.
echo ======================================
echo   服务启动完成！
echo   Web 管理台: http://localhost:5000
echo   账号: admin / RPA@admin2026
echo ======================================
echo.
echo 关闭方式: 手动关闭各个终端窗口
echo 或: taskkill /f /im redis-server.exe /im python.exe
pause