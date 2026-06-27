@echo off
chcp 65001 >nul
title CompetitorWatch - 电商竞品竞价采集系统

:: ============================================================
:: CompetitorWatch 一键启动脚本
:: 需要先安装: Python 3.10+, MySQL, Redis, Playwright
:: ============================================================

:: 自动检测 Python 路径
set PYTHON_EXE=
if exist "C:\Users\JackPeesao\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
    set PYTHON_EXE=C:\Users\JackPeesao\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 set PYTHON_EXE=python
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python not found!
    pause
    exit /b 1
)

echo Python: %PYTHON_EXE%

:menu
cls
echo.
echo  ============================================================
echo    CompetitorWatch - 电商竞品竞价采集与智能分析系统
echo  ============================================================
echo.
echo   [1] 一键启动全部服务 (Admin + Worker)
echo       启动 Flask 后台管理 + 采集 Worker
echo.
echo   [2] 仅启动 Admin 后台
echo       Flask 管理界面 http://localhost:5100
echo.
echo   [3] 仅启动 Worker 采集
echo       采集任务消费者
echo.
echo   [4] 初始化数据库
echo       创建/更新 MySQL 表结构
echo.
echo   [5] 安装依赖
echo       pip install + playwright 浏览器
echo.
echo   [6] 运行测试
echo       执行单元测试验证系统
echo.
echo   [0] 退出
echo.
echo  ============================================================
set /p choice="  请选择 [0-6]: "

if "%choice%"=="1" goto start_all
if "%choice%"=="2" goto admin_only
if "%choice%"=="3" goto worker_only
if "%choice%"=="4" goto init_db
if "%choice%"=="5" goto install_deps
if "%choice%"=="6" goto run_tests
if "%choice%"=="0" goto exit
goto menu

:: ============================================================
:: 一键启动全部服务
:: ============================================================
:start_all
cls
echo.
echo  ============================================================
echo   启动 CompetitorWatch 全部服务
echo  ============================================================
echo.
echo  前提条件:
echo    1. MySQL 已启动 (localhost:3306)
echo    2. Redis 已启动 (localhost:6379)
echo    3. .env 已配置正确的数据库密码和API密钥
echo    4. 数据库表已初始化 (选 [4] 初始化)
echo.
echo  按任意键开始启动...
pause >nul

:: 检查 .env
if not exist ".env" (
    echo [ERROR] .env 文件不存在！请先配置环境变量。
    pause
    goto menu
)

:: 检查依赖
echo 检查 Python 依赖...
%PYTHON_EXE% -c "import flask, pymysql, redis, playwright" 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] 缺少依赖，正在安装...
    %PYTHON_EXE% -m pip install -r requirements.txt -q
)

:: 启动 Admin
echo.
echo [1/2] 启动 Admin 后台服务 (Flask :5100)...
start "CompetitorWatch-Admin" cmd /c "title CompetitorWatch Admin ^& %PYTHON_EXE% app.py"

:: 等待 Admin 启动
echo 等待 Admin 启动...
timeout /t 3 /nobreak >nul

:: 启动 Worker
echo [2/2] 启动 Worker 采集服务...
start "CompetitorWatch-Worker" cmd /c "title CompetitorWatch Worker ^& %PYTHON_EXE% worker.py --region both"

echo.
echo  ============================================================
echo   启动完成！
echo.
echo   Admin 管理:  http://localhost:5100/competitor/manage
echo   竞价看板:    http://localhost:5100/competitor/dashboard
echo   AI 报告:     http://localhost:5100/competitor/reports
echo.
echo   关闭方式: 关闭弹出的命令行窗口即可
echo  ============================================================
echo.
pause
goto menu

:: ============================================================
:: 仅 Admin
:: ============================================================
:admin_only
cls
echo.
echo 启动 Admin 后台服务...
start "CompetitorWatch-Admin" cmd /c "title CompetitorWatch Admin ^& %PYTHON_EXE% app.py"
echo Admin 已启动: http://localhost:5100/competitor/manage
echo.
pause
goto menu

:: ============================================================
:: 仅 Worker
:: ============================================================
:worker_only
cls
echo.
set /p worker_region="  区域 [both/international/domestic] (默认 both): "
if "%worker_region%"=="" set worker_region=both
start "CompetitorWatch-Worker" cmd /c "title CompetitorWatch Worker ^& %PYTHON_EXE% worker.py --region %worker_region%"
echo Worker 已启动 (区域: %worker_region%)
echo.
pause
goto menu

:: ============================================================
:: 初始化数据库
:: ============================================================
:init_db
cls
echo.
echo  ============================================================
echo   初始化数据库表结构
echo  ============================================================
echo.
echo  将执行 sql/init_tables.sql 创建以下表:
echo    - competitor_config    (竞品配置表)
echo    - ods_price_snapshot   (价格快照表)
echo    - dw_competitor_daily  (日聚合表)
echo    - competitor_report    (AI报告表)
echo.
echo  前提: MySQL 已启动，.env 已配置
echo.
set /p db_confirm="  确认执行? (不会删除已有数据) [Y/N]: "
if /i not "%db_confirm%"=="Y" goto menu

echo.
echo 正在初始化数据库...
%PYTHON_EXE% -c "import sys; sys.path.insert(0,'.'); from config.settings import get_config; from core.db_operations import DatabaseManager; db=DatabaseManager(); conn=db.get_connection(); cur=conn.cursor(); exec(open('sql/init_tables.sql','r',encoding='utf-8').read()); conn.commit(); conn.close(); print('数据库初始化完成!')"

if %errorlevel% neq 0 (
    echo.
    echo [WARNING] 自动执行失败，请手动执行:
    echo   mysql -u root -p ecomiq ^< sql\init_tables.sql
) else (
    echo.
    echo 数据库表创建成功！
)
echo.
pause
goto menu

:: ============================================================
:: 安装依赖
:: ============================================================
:install_deps
cls
echo.
echo  ============================================================
echo   安装 Python 依赖 + Playwright 浏览器
echo  ============================================================
echo.
echo [1/2] 安装 Python 包...
%PYTHON_EXE% -m pip install -r requirements.txt
echo.
echo [2/2] 安装 Playwright Chromium 浏览器...
%PYTHON_EXE% -m playwright install chromium
echo.
echo 依赖安装完成！
pause
goto menu

:: ============================================================
:: 运行测试
:: ============================================================
:run_tests
cls
echo.
echo  ============================================================
echo   运行单元测试
echo  ============================================================
echo.
%PYTHON_EXE% -m pytest tests/ -v --tb=short
echo.
pause
goto menu

:: ============================================================
:: 退出
:: ============================================================
:exit
echo.
echo Goodbye!
exit /b 0
