@echo off
setlocal enabledelayedexpansion
title EasyCon

cd /d "%~dp0"

set ROOT_DIR=%~dp0
if "%ROOT_DIR:~-1%"=="\" set ROOT_DIR=%ROOT_DIR:~0,-1%
set PYTHON_EXE=%ROOT_DIR%\Python312\python.exe

:: ---- Menu ----------------------------------------------
:menu
set CHOICE=
echo.
echo.
echo ========================================
echo   EasyCon - Menu
echo ========================================
echo.
echo   1. RNG Shiny Hunt
echo   2. Scan Shiny Hunt
echo   3. EV Training
echo   4. Update
echo.
echo   0. Exit
echo.
set /p CHOICE="Select [1-4]: "

if "%CHOICE%"=="0" exit /b 0
if "%CHOICE%"=="1" goto :rng
if "%CHOICE%"=="2" goto :scan
if "%CHOICE%"=="3" goto :training
if "%CHOICE%"=="4" goto :update
echo Invalid choice.
goto :menu

:: ========================================================
::  1. RNG Shiny Hunt
:: ========================================================
:rng
cd /d "%ROOT_DIR%"
"%PYTHON_EXE%" -u run_rng_gui.py
goto :menu

:: ========================================================
::  2. Scan Shiny Hunt
:: ========================================================
:scan
cd /d "%ROOT_DIR%"
"%PYTHON_EXE%" -u run_scan_gui.py
goto :menu

:: ========================================================
::  3. EV Training
:: ========================================================
:training
cd /d "%ROOT_DIR%"
"%PYTHON_EXE%" -u run_training_gui.py
goto :menu

:: ========================================================
::  4. Update
:: ========================================================
:update
set GIT_EXE=%ROOT_DIR%\PortableGit\bin\git.exe
cd /d "%ROOT_DIR%"
echo.
echo Pulling updates...
"%GIT_EXE%" pull
if !ERRORLEVEL! equ 0 (
    echo Update succeeded.
) else (
    echo Update failed. Check your network and retry.
)
pause
goto :menu