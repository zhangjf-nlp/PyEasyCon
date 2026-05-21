@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title EasyCon - Environment Setup

cd /d "%~dp0"

set PYTHON_VERSION=3.12.10
set ROOT_DIR=%~dp0
if "%ROOT_DIR:~-1%"=="\" set ROOT_DIR=%ROOT_DIR:~0,-1%
set PYTHON_DIR=%ROOT_DIR%\Python312
set PYTHON_EXE=%PYTHON_DIR%\python.exe
set GIT_DIR=%ROOT_DIR%\Git
set GIT_EXE=%GIT_DIR%\bin\git.exe
set DOWNLOADS_DIR=%ROOT_DIR%\_downloads
set PTH_FILE=%PYTHON_DIR%\python312._pth
set PIP_BOOTSTRAP=%DOWNLOADS_DIR%\get-pip.py

:: Download URLs (official + mirrors for Chinese users)
set ZIP_NAME=python-%PYTHON_VERSION%-embed-amd64.zip
set PYTHON_URL_1=https://www.python.org/ftp/python/%PYTHON_VERSION%/%ZIP_NAME%
set PYTHON_URL_2=https://npmmirror.com/mirrors/python/%PYTHON_VERSION%/%ZIP_NAME%
set PIP_URL_1=https://bootstrap.pypa.io/get-pip.py
set PIP_URL_2=https://npmmirror.com/mirrors/pypa/get-pip.py
set GIT_URL_1=https://github.com/git-for-windows/git/releases/download/v2.47.0.windows.2/PortableGit-2.47.0.2-64-bit.7z.exe
set GIT_URL_2=https://ghproxy.net/https://github.com/git-for-windows/git/releases/download/v2.47.0.windows.2/PortableGit-2.47.0.2-64-bit.7z.exe
set PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple

echo ========================================
echo   EasyCon Environment Setup
echo ========================================
echo.
echo This script will set up a standalone Python for EasyCon.
echo It will NOT affect any existing Python on your system.
echo.

:: ── Step 1: Unpack clean Python ─────────────────────
echo [1/5] Checking Python...

if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" -c "exit(0)" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo   √ Python found, skipping
        goto :check_git
    )
    echo   ! Existing Python is broken, re-extracting...
    rmdir /s /q "%PYTHON_DIR%" 2>nul
)

if not exist "%DOWNLOADS_DIR%" mkdir "%DOWNLOADS_DIR%"
set ZIP_FILE=%DOWNLOADS_DIR%\%ZIP_NAME%

if not exist "%ZIP_FILE%" (
    echo   Downloading Python %PYTHON_VERSION% embeddable...
    echo   (~11MB, please wait)
    call :download "%PYTHON_URL_1%" "%ZIP_FILE%" "python.org"
    if !ERRORLEVEL! neq 0 (
        echo   Retrying from mirror...
        call :download "%PYTHON_URL_2%" "%ZIP_FILE%" "npmmirror.com"
        if !ERRORLEVEL! neq 0 (
            echo   X Download failed. Please check your network.
            pause
            exit /b 1
        )
    )
) else (
    echo   Using pre-downloaded zip from _downloads/
)

echo   Extracting Python...
powershell -NoProfile -Command ^
    "Expand-Archive -Path '%ZIP_FILE%' -DestinationPath '%PYTHON_DIR%' -Force"
if not exist "%PYTHON_EXE%" (
    echo   X Extraction failed
    pause
    exit /b 1
)
echo   √ Python extracted

:: Enable site-packages in embeddable Python
echo   Enabling site-packages...
powershell -NoProfile -Command ^
    "(Get-Content '%PTH_FILE%') -replace '#import site', 'import site' | Set-Content '%PTH_FILE%'"

:: ── Step 2: Download portable Git ───────────────────
:check_git
echo.
echo [2/5] Checking Git...

where git >nul 2>&1
if !ERRORLEVEL! equ 0 (
    for /f "delims=" %%i in ('where git') do set GIT_PATH=%%i
    echo   √ System Git found: !GIT_PATH!
    set GIT_EXE=git
    goto :install_pip
)

if exist "%GIT_EXE%" (
    echo   √ Local Git found, skipping
    goto :install_pip
)

echo   Downloading portable Git for auto-update...
echo   (~50MB, please wait - this is optional)

set GIT_INSTALLER=%DOWNLOADS_DIR%\PortableGit.7z.exe
if not exist "%GIT_INSTALLER%" (
    call :download "%GIT_URL_1%" "%GIT_INSTALLER%" "GitHub"
    if !ERRORLEVEL! neq 0 (
        echo   Retrying from mirror...
        call :download "%GIT_URL_2%" "%GIT_INSTALLER%" "ghproxy"
        if !ERRORLEVEL! neq 0 (
            echo   ! Git download failed. Auto-update will be unavailable.
            goto :install_pip
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

:: ── Step 3: Bootstrap pip ───────────────────────────
:install_pip
echo.
echo [3/5] Checking pip...

"%PYTHON_EXE%" -m pip --version >nul 2>&1
if !ERRORLEVEL! equ 0 (
    echo   √ pip already installed
    goto :upgrade_pip
)

if not exist "%PIP_BOOTSTRAP%" (
    echo   Downloading get-pip.py...
    call :download "%PIP_URL_1%" "%PIP_BOOTSTRAP%" "bootstrap.pypa.io"
    if !ERRORLEVEL! neq 0 (
        echo   Retrying from mirror...
        call :download "%PIP_URL_2%" "%PIP_BOOTSTRAP%" "npmmirror.com"
        if !ERRORLEVEL! neq 0 (
            echo   X Failed to download pip installer
            pause
            exit /b 1
        )
    )
)

echo   Installing pip...
"%PYTHON_EXE%" "%PIP_BOOTSTRAP%" --no-setuptools --no-wheel -q
if !ERRORLEVEL! neq 0 (
    echo   X pip installation failed
    pause
    exit /b 1
)
echo   √ pip installed

:: ── Step 4: Upgrade pip ─────────────────────────────
:upgrade_pip
echo.
echo [4/5] Upgrading pip...

"%PYTHON_EXE%" -m pip install --upgrade pip -q -i %PIP_INDEX% --trusted-host pypi.tuna.tsinghua.edu.cn
if !ERRORLEVEL! neq 0 (
    echo   ! pip upgrade failed, continuing anyway...
) else (
    echo   √ pip upgraded
)

:: ── Step 5: Install project dependencies ────────────
echo.
echo [5/5] Installing dependencies...
echo   (First time may take a few minutes, please wait)

"%PYTHON_EXE%" -m pip install -r "%ROOT_DIR%\requirements.txt" ^
    -i %PIP_INDEX% --trusted-host pypi.tuna.tsinghua.edu.cn
if !ERRORLEVEL! neq 0 (
    echo   X Dependency installation failed
    pause
    exit /b 1
)

echo   √ Dependencies installed

:: ── Cleanup ─────────────────────────────────────────
echo.
echo ========================================
echo   Setup complete!
echo.
echo   Double-click run.bat to start EasyCon
echo ========================================
echo.
if exist "%DOWNLOADS_DIR%" (
    choice /c yn /n /m "Delete downloaded files to save space? [Y/N] " /t 10 /d y
    if !ERRORLEVEL! equ 1 (
        rmdir /s /q "%DOWNLOADS_DIR%"
        echo   Cleaned up
    )
)
echo.
pause
exit /b 0

:: ── Helper: download with retry ─────────────────────
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
