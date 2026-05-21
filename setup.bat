@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title EasyCon - Environment Setup

cd /d "%~dp0"

set PYTHON_VERSION=3.12.10
set PYTHON_DIR=%~dp0Python312
set VENV_DIR=%~dp0venv
set GIT_DIR=%~dp0Git
set PYTHON_EXE=%PYTHON_DIR%\python.exe
set GIT_EXE=%GIT_DIR%\bin\git.exe
set DOWNLOADS_DIR=%~dp0_downloads

:: Download URLs (official + mirrors for Chinese users)
set PYTHON_URL_1=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe
set PYTHON_URL_2=https://npmmirror.com/mirrors/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe
set GIT_URL_1=https://github.com/git-for-windows/git/releases/download/v2.47.0.windows.2/PortableGit-2.47.0.2-64-bit.7z.exe
set GIT_URL_2=https://ghproxy.net/https://github.com/git-for-windows/git/releases/download/v2.47.0.windows.2/PortableGit-2.47.0.2-64-bit.7z.exe
set PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

echo ========================================
echo   EasyCon Environment Setup
echo ========================================
echo.
echo This script will install a standalone Python for EasyCon.
echo It will NOT affect any existing Python on your system.
echo.

:: ── Step 1: Download / Install clean Python ────────
echo [1/5] Checking Python...

if exist "%PYTHON_EXE%" (
    echo   √ Local Python found, skipping download
    goto :check_venv
)

echo   Downloading Python %PYTHON_VERSION% ...
echo   (~27MB, please wait)
echo.

if not exist "%DOWNLOADS_DIR%" mkdir "%DOWNLOADS_DIR%"
set INSTALLER=%DOWNLOADS_DIR%\python-%PYTHON_VERSION%-amd64.exe

if not exist "%INSTALLER%" (
    call :download "%PYTHON_URL_1%" "%INSTALLER%" "python.org"
    if !ERRORLEVEL! neq 0 (
        echo   Retrying from mirror...
        call :download "%PYTHON_URL_2%" "%INSTALLER%" "npmmirror.com"
        if !ERRORLEVEL! neq 0 (
            echo   X Download failed. Please check your network.
            echo   Manual download: %PYTHON_URL_1%
            pause
            exit /b 1
        )
    )
) else (
    echo   Using pre-downloaded installer from _downloads/
)

echo   Installing Python to local directory...
echo   (This will NOT affect your system Python)
"%INSTALLER%" /quiet InstallAllUsers=0 TargetDir="%PYTHON_DIR%" ^
    Include_launcher=0 Include_test=0 Include_tcltk=0 ^
    Include_pip=1 Include_dev=1 ^
    Shortcuts=0 AssociateFiles=0

if not exist "%PYTHON_EXE%" (
    echo   X Python installation failed
    pause
    exit /b 1
)
echo   √ Python installed

:: ── Step 2: Download portable Git ──────────────────
echo.
echo [2/5] Checking Git...

where git >nul 2>&1
if !ERRORLEVEL! equ 0 (
    for /f "delims=" %%i in ('where git') do set GIT_PATH=%%i
    echo   √ System Git found: !GIT_PATH!
    set GIT_EXE=git
    goto :check_venv
)

if exist "%GIT_EXE%" (
    echo   √ Local Git found, skipping download
    goto :check_venv
)

echo   Downloading portable Git for auto-update...
echo   (~50MB, please wait - this is optional)
echo.

set GIT_INSTALLER=%DOWNLOADS_DIR%\PortableGit.7z.exe

if not exist "%GIT_INSTALLER%" (
    call :download "%GIT_URL_1%" "%GIT_INSTALLER%" "GitHub"
    if !ERRORLEVEL! neq 0 (
        echo   Retrying from mirror...
        call :download "%GIT_URL_2%" "%GIT_INSTALLER%" "ghproxy"
        if !ERRORLEVEL! neq 0 (
            echo   ! Git download failed. Auto-update will be unavailable.
            echo   (This does NOT affect normal usage, only git pull update)
            goto :check_venv
        )
    )
)

echo   Extracting Git...
mkdir "%GIT_DIR%" 2>nul
"%GIT_INSTALLER%" -o"%GIT_DIR%" -y
if exist "%GIT_EXE%" (
    echo   √ Git ready
) else (
    echo   ! Git extraction failed. Auto-update will be unavailable.
)

:: ── Step 3: Create virtual environment ─────────────
:check_venv
echo.
echo [3/5] Setting up virtual environment...

if exist "%VENV_DIR%\Scripts\python.exe" (
    "%VENV_DIR%\Scripts\python.exe" -c "exit(0)" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo   √ venv is healthy, skipping
        goto :venv_ready
    )
    echo   ! Existing venv is broken (stale Python reference), recreating...
    rmdir /s /q "%VENV_DIR%" 2>nul
)

echo   Creating venv...
"%PYTHON_EXE%" -m venv "%VENV_DIR%"
if !ERRORLEVEL! neq 0 (
    echo   X venv creation failed
    pause
    exit /b 1
)
echo   √ venv created

:venv_ready
set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe

:: ── Step 4: Upgrade pip ────────────────────────────
echo.
echo [4/5] Upgrading pip...

"%VENV_PYTHON%" -m pip install --upgrade pip -q -i %PIP_INDEX% --trusted-host pypi.tuna.tsinghua.edu.cn
if !ERRORLEVEL! neq 0 (
    echo   ! pip upgrade failed, continuing anyway...
) else (
    echo   √ pip upgraded
)

:: ── Step 5: Install project dependencies ───────────
echo.
echo [5/5] Installing dependencies...
echo   (First time may take a few minutes, please wait)

"%VENV_PYTHON%" -m pip install -r "%~dp0requirements.txt" ^
    -i %PIP_INDEX% --trusted-host pypi.tuna.tsinghua.edu.cn
if !ERRORLEVEL! neq 0 (
    echo   X Dependency installation failed
    pause
    exit /b 1
)

echo   √ Dependencies installed

:: ── Cleanup ────────────────────────────────────────
echo.
echo ========================================
echo   Setup complete!
echo.
echo   Double-click run.bat to start EasyCon
echo ========================================
echo.
if exist "%DOWNLOADS_DIR%" (
    choice /c yn /n /m "Delete downloaded installers to save space? [Y/N] " /t 10 /d y
    if !ERRORLEVEL! equ 1 (
        rmdir /s /q "%DOWNLOADS_DIR%"
        echo   Cleaned up
    )
)
echo.
pause
exit /b 0

:: ── Helper: download with retry ────────────────────
:download
set URL=%~1
set OUTPUT=%~2
set LABEL=%~3
echo     [%LABEL%] %URL%
powershell -NoProfile -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
    "$ProgressPreference = 'SilentlyContinue'; " ^
    "Invoke-WebRequest -Uri '%URL%' -OutFile '%OUTPUT%' -UseBasicParsing -TimeoutSec 300"
exit /b %ERRORLEVEL%
