@echo off
setlocal enabledelayedexpansion
title EasyCon RNG

cd /d "%~dp0"

set ROOT_DIR=%~dp0
if "%ROOT_DIR:~-1%"=="\" set ROOT_DIR=%ROOT_DIR:~0,-1%
set PYTHON_EXE=%ROOT_DIR%\Python312\python.exe

if not exist "%PYTHON_EXE%" (
    echo ========================================
    echo   Python not found. Please run setup.bat first.
    echo ========================================
    pause
    exit /b 1
)

set "PATH=%ROOT_DIR%\Python312\Scripts;%ROOT_DIR%\Python312;%PATH%"

"%PYTHON_EXE%" -u "%ROOT_DIR%\run_rng_gui.py" --zh

exit /b 0
