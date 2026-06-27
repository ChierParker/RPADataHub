@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo   LeadScraper 打包构建脚本
echo   产出目录: dist\LeadScraper\
echo ============================================
echo.

:: ============================================
:: 1. 环境检查
:: ============================================
echo [1/7] 检查环境...
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

pip --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到 pip
    pause
    exit /b 1
)

:: 安装 PyInstaller
echo [信息] 安装/升级 PyInstaller...
pip install pyinstaller -q
if %ERRORLEVEL% NEQ 0 (
    echo [错误] PyInstaller 安装失败
    pause
    exit /b 1
)

:: ============================================
:: 2. 定位 Playwright Chromium
:: ============================================
echo [2/7] 定位 Playwright Chromium...

set "MS_PLAYWRIGHT=%USERPROFILE%\AppData\Local\ms-playwright"
set "CHROMIUM_SRC="

if not exist "%MS_PLAYWRIGHT%" (
    echo [错误] 未找到 Playwright 浏览器缓存
    echo        请先运行: playwright install chromium
    pause
    exit /b 1
)

:: 查找 chromium- 开头的目录（按名称倒序取最新版本）
for /f "delims=" %%d in ('dir /b /ad /o-n "%MS_PLAYWRIGHT%\chromium-*" 2^>nul') do (
    set "CHROMIUM_DIR=%%d"
    goto :found_chromium
)

:found_chromium
if "%CHROMIUM_DIR%"=="" (
    echo [错误] 未找到 Chromium 浏览器，请先运行: playwright install chromium
    pause
    exit /b 1
)

:: 检查 chrome-win 或 chrome-win64 子目录
set "CHROMIUM_SRC="
if exist "%MS_PLAYWRIGHT%\%CHROMIUM_DIR%\chrome-win\chrome.exe" (
    set "CHROMIUM_SRC=%MS_PLAYWRIGHT%\%CHROMIUM_DIR%\chrome-win"
)
if exist "%MS_PLAYWRIGHT%\%CHROMIUM_DIR%\chrome-win64\chrome.exe" (
    set "CHROMIUM_SRC=%MS_PLAYWRIGHT%\%CHROMIUM_DIR%\chrome-win64"
)

if "%CHROMIUM_SRC%"=="" (
    echo [错误] 在 %MS_PLAYWRIGHT%\%CHROMIUM_DIR% 中未找到 chrome.exe
    pause
    exit /b 1
)

echo [信息] 找到 Chromium: %CHROMIUM_SRC%

:: ============================================
:: 3. 复制 Chromium 到 browser 目录
:: ============================================
echo [3/7] 复制 Chromium 到 browser\chrome-win\ ...

set "BROWSER_DEST=%~dp0browser\chrome-win"

if exist "%BROWSER_DEST%" (
    echo [信息] browser\chrome-win 已存在，跳过复制
) else (
    mkdir "%BROWSER_DEST%" 2>nul
    echo [信息] 正在复制 Chromium 文件（约 400MB，需要 1-3 分钟）...
    xcopy "%CHROMIUM_SRC%\*" "%BROWSER_DEST%\" /E /I /Q /H /Y
    if %ERRORLEVEL% NEQ 0 (
        echo [错误] Chromium 复制失败
        pause
        exit /b 1
    )
    echo [信息] Chromium 复制完成
)

:: ============================================
:: 4. 验证静态资源
:: ============================================
echo [4/7] 验证静态资源...

set "STATIC_DIR=%~dp0static"
if not exist "%STATIC_DIR%\css\bootstrap.min.css" (
    echo [警告] 缺少 static\css\bootstrap.min.css，请先完成静态资源下载
)
if not exist "%STATIC_DIR%\js\bootstrap.bundle.min.js" (
    echo [警告] 缺少 static\js\bootstrap.bundle.min.js，请先完成静态资源下载
)

:: ============================================
:: 5. 创建运行时目录
:: ============================================
echo [5/7] 创建运行时目录...

for %%d in (input output profiles logs) do (
    if not exist "%~dp0%%d" mkdir "%~dp0%%d"
)

:: ============================================
:: 6. 执行 PyInstaller 打包
:: ============================================
echo [6/7] 执行 PyInstaller 打包（onedir 模式）...
echo       这需要 3-8 分钟，请耐心等待...

:: 清理旧构建
if exist "%~dp0dist\LeadScraper" rmdir /s /q "%~dp0dist\LeadScraper" 2>nul
if exist "%~dp0build" rmdir /s /q "%~dp0build" 2>nul

:: PyInstaller --onedir 打包
:: 注意：templates 和 static 通过 --add-data 打入 _internal 目录
:: browser 太大，PyInstaller 构建后手动复制到 dist（见下一步）
pyinstaller ^
    --onedir ^
    --console ^
    --name=LeadScraper ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data "settings.json;." ^
    --add-data "email_templates.json;." ^
    --hidden-import=openpyxl.cell._writer ^
    --hidden-import=pandas ^
    --hidden-import=playwright ^
    --hidden-import=playwright.sync_api ^
    --hidden-import=playwright.async_api ^
    --hidden-import=playwright._impl ^
    --collect-all=playwright ^
    --collect-all=pandas ^
    --exclude-module=tkinter ^
    --exclude-module=test ^
    --clean ^
    app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [错误] PyInstaller 打包失败，请检查上述错误信息。
    pause
    exit /b 1
)

:: ============================================
:: 7. 复制运行时文件到 dist
:: ============================================
echo [7/7] 复制运行时文件到 dist\LeadScraper\ ...

set "DIST=%~dp0dist\LeadScraper"

:: 复制浏览器（作为便携 Chromium 放在 exe 同目录）
echo       复制 Chromium 浏览器...
mkdir "%DIST%\browser" 2>nul
xcopy "%BROWSER_DEST%\*" "%DIST%\browser\chrome-win\" /E /I /Q /H /Y

:: 复制配置文件
echo       复制配置文件...
copy /Y "%~dp0settings.json" "%DIST%\settings.json" >nul
copy /Y "%~dp0email_templates.json" "%DIST%\email_templates.json" >nul 2>nul

:: 创建运行时目录
for %%d in (input output profiles logs) do (
    mkdir "%DIST%\%%d" 2>nul
)

:: 复制使用说明
if exist "%~dp0使用说明.txt" (
    copy /Y "%~dp0使用说明.txt" "%DIST%\使用说明.txt" >nul
)

:: ============================================
:: 完成
:: ============================================
echo.
echo ============================================
echo   打包完成！
echo   输出目录: dist\LeadScraper\
echo.
echo   分发步骤:
echo   1. 将 LeadScraper 文件夹打包为 zip
echo   2. 用户解压后编辑 settings.json 配置参数
echo   3. 双击 LeadScraper.exe 启动
echo ============================================

pause
