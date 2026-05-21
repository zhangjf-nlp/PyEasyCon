@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title EasyCon

cd /d "%~dp0"

set VENV_DIR=%~dp0venv
set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe
set GIT_DIR=%~dp0Git\bin
set GIT_EXE=

:: ── 检查环境是否已安装 ────────────────────────────
if not exist "%VENV_PYTHON%" (
    echo ========================================
    echo   Environment not found. Running setup...
    echo ========================================
    echo.
    pause
    call "%~dp0setup.bat"
    if not exist "%VENV_PYTHON%" (
        echo Setup incomplete. Cannot start.
        pause
        exit /b 1
    )
) else (
    "%VENV_PYTHON%" -c "exit(0)" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo ========================================
        echo   Existing venv is broken, running setup to fix...
        echo ========================================
        echo.
        pause
        call "%~dp0setup.bat"
    )
)

:: ── 检查 Git 并自动更新 ───────────────────────────
:: 优先级: 系统git > 本地便携Git > 跳过
where git >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set GIT_EXE=git
) else if exist "%GIT_DIR%\git.exe" (
    set GIT_EXE=%GIT_DIR%\git.exe
    set PATH=%GIT_DIR%;%PATH%
)

if not "%GIT_EXE%"=="" (
    echo [更新] 正在检查更新...
    "%GIT_EXE%" -C "%~dp0" pull --ff-only 2>nul
    if !ERRORLEVEL! equ 0 (
        echo [更新] 代码已是最新
    ) else (
        echo [更新] 未能获取更新 ^(可能未连接网络或非 git 仓库^)
    )
    echo.
)

:: ── 启动 EasyCon ──────────────────────────────────
echo 正在启动 EasyCon...
"%VENV_PYTHON%" "%~dp0gui\app.py"

if !ERRORLEVEL! neq 0 (
    echo.
    echo ========================================
    echo   程序异常退出
    echo   如果问题持续，请运行 setup.bat 重新安装
    echo ========================================
    pause
)
