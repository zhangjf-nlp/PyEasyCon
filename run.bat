@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title EasyCon

cd /d "%~dp0"

set ROOT_DIR=%~dp0
if "%ROOT_DIR:~-1%"=="\" set ROOT_DIR=%ROOT_DIR:~0,-1%
set PYTHON_EXE=%ROOT_DIR%\Python312\python.exe
set GIT_DIR=%ROOT_DIR%\Git\bin
set GIT_EXE=

:: ── Check environment ────────────────────────────────
if not exist "%PYTHON_EXE%" (
    echo ========================================
    echo   Environment not found. Running setup...
    echo ========================================
    echo.
    pause
    call "%ROOT_DIR%\setup.bat"
    if not exist "%PYTHON_EXE%" (
        echo Setup incomplete. Cannot start.
        pause
        exit /b 1
    )
) else (
    "%PYTHON_EXE%" -c "exit(0)" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo ========================================
        echo   Python is broken, running setup to fix...
        echo ========================================
        echo.
        pause
        call "%ROOT_DIR%\setup.bat"
    )
)

:: ── Check Git and auto-update ────────────────────────
where git >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set GIT_EXE=git
) else if exist "%GIT_DIR%\git.exe" (
    set GIT_EXE=%GIT_DIR%\git.exe
    set PATH=%GIT_DIR%;%PATH%
)

if not "%GIT_EXE%"=="" (
    echo [Update] Checking for updates...
    "%GIT_EXE%" -C "%ROOT_DIR%" pull --ff-only 2>nul
    if !ERRORLEVEL! equ 0 (
        echo [Update] Code is up to date
    ) else (
        echo [Update] Could not update ^(offline or not a git repo^)
    )
    echo.
)

:: ── Start EasyCon ────────────────────────────────────
echo Starting EasyCon...
"%PYTHON_EXE%" "%ROOT_DIR%\gui\app.py"

if !ERRORLEVEL! neq 0 (
    echo.
    echo ========================================
    echo   Program exited unexpectedly
    echo   Run setup.bat to reinstall if this persists
    echo ========================================
    pause
)
