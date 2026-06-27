@echo off
chcp 65001 >nul
echo ======================================
echo   EcomIQ-RPA - Unified Platform
echo ======================================
echo.
echo  URL:      http://localhost:5000
echo  Account:  admin / RPAadmin2026
echo.
echo  Module Routes:
echo    RPADataHub         /rpa
echo    CompetitorWatch    /competitor
echo    LeadScraper        /leads
echo    VideoIQ            /video
echo    AI Assistant       /ai
echo.
echo ======================================
echo.

cd /d "%~dp0..\.."

REM Activate venv if exists
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

python -m src.main.app

pause