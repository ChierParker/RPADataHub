@echo off
chcp 65001 >nul
echo ======================================
echo   EcomIQ-RPA — 电商智能工具集 统一启动
echo ======================================
echo.
echo  访问地址: http://localhost:5000
echo  默认账号: admin / RPA@admin2026
echo.
echo  模块路由:
echo    📡 RPADataHub        /rpa
echo    📊 CompetitorWatch    /competitor
echo    🎯 LeadScraper        /leads
echo    🎬 VideoIQ            /video
echo    🤖 AI Assistant       /ai
echo.
echo ======================================
echo.

cd /d "%~dp0..\.."

REM 激活虚拟环境
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

python -m src.main.app

pause