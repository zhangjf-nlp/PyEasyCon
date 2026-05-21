@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title EasyCon - 环境安装

cd /d "%~dp0"

set PYTHON_VERSION=3.10.11
set PYTHON_DIR=%~dp0Python310
set VENV_DIR=%~dp0venv
set GIT_DIR=%~dp0Git
set PYTHON_EXE=%PYTHON_DIR%\python.exe
set GIT_EXE=%GIT_DIR%\bin\git.exe
set PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe
set GIT_URL=https://github.com/git-for-windows/git/releases/download/v2.47.0.windows.2/PortableGit-2.47.0.2-64-bit.7z.exe
set DOWNLOADS_DIR=%~dp0_downloads

echo ========================================
echo   EasyCon 环境安装向导
echo ========================================
echo.
echo 本脚本将为 EasyCon 安装独立的 Python 环境，
echo 不会影响您系统中已有的任何 Python 安装。
echo.

:: ── 步骤1：下载/安装干净 Python ──────────────────
echo [1/5] 检查 Python 环境...

if exist "%PYTHON_EXE%" (
    echo   √ 本地 Python 已存在，跳过下载
    goto :check_venv
)

echo   正在下载 Python %PYTHON_VERSION% ...
echo   (文件约 27MB，请耐心等待)
echo.

if not exist "%DOWNLOADS_DIR%" mkdir "%DOWNLOADS_DIR%"
set INSTALLER=%DOWNLOADS_DIR%\python-%PYTHON_VERSION%-amd64.exe

if not exist "%INSTALLER%" (
    powershell -NoProfile -Command ^
        "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%INSTALLER%' -UseBasicParsing"
    if !ERRORLEVEL! neq 0 (
        echo   X 下载失败，请检查网络连接后重试
        echo   手动下载地址: %PYTHON_URL%
        pause
        exit /b 1
    )
) else (
    echo   使用已下载的安装包...
)

echo   正在安装 Python 到本地目录...
echo   (这不会影响您系统中的 Python)
"%INSTALLER%" /quiet InstallAllUsers=0 TargetDir="%PYTHON_DIR%" ^
    Include_launcher=0 Include_test=0 Include_tcltk=0 ^
    Include_pip=1 Include_dev=1 ^
    Shortcuts=0 AssociateFiles=0

if not exist "%PYTHON_EXE%" (
    echo   X Python 安装失败
    pause
    exit /b 1
)
echo   √ Python 安装完成

:: ── 步骤2：下载便携版 Git ────────────────────────
echo.
echo [2/5] 检查 Git ...

where git >nul 2>&1
if !ERRORLEVEL! equ 0 (
    for /f "delims=" %%i in ('where git') do set GIT_PATH=%%i
    echo   √ 系统已安装 Git: !GIT_PATH!
    set GIT_EXE=git
    goto :check_venv
)

if exist "%GIT_EXE%" (
    echo   √ 本地 Git 已存在，跳过下载
    goto :check_venv
)

echo   正在下载便携版 Git ...
echo   (文件约 50MB，请耐心等待)
echo.

set GIT_INSTALLER=%DOWNLOADS_DIR%\PortableGit-2.47.0.2-64-bit.7z.exe

if not exist "%GIT_INSTALLER%" (
    powershell -NoProfile -Command ^
        "Invoke-WebRequest -Uri '%GIT_URL%' -OutFile '%GIT_INSTALLER%' -UseBasicParsing"
    if !ERRORLEVEL! neq 0 (
        echo   ! Git 下载失败，自动更新功能将不可用
        echo   (不影响正常使用，仅不能自动更新)
        goto :check_venv
    )
)

echo   正在解压 Git ...
mkdir "%GIT_DIR%" 2>nul
"%GIT_INSTALLER%" -o"%GIT_DIR%" -y
if exist "%GIT_EXE%" (
    echo   √ Git 安装完成
) else (
    echo   ! Git 安装失败，自动更新功能将不可用
)

:: ── 步骤3：创建虚拟环境 ──────────────────────────
:check_venv
echo.
echo [3/5] 设置虚拟环境...

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo   √ 虚拟环境已存在，跳过创建
) else (
    echo   正在创建虚拟环境...
    "%PYTHON_EXE%" -m venv "%VENV_DIR%"
    if !ERRORLEVEL! neq 0 (
        echo   X 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo   √ 虚拟环境创建完成
)

set VENV_PYTHON=%VENV_DIR%\Scripts\python.exe

:: ── 步骤4：升级 pip ──────────────────────────────
echo.
echo [4/5] 升级 pip ...

"%VENV_PYTHON%" -m pip install --upgrade pip -q
if !ERRORLEVEL! neq 0 (
    echo   ! pip 升级失败，继续安装依赖...
) else (
    echo   √ pip 升级完成
)

:: ── 步骤5：安装项目依赖 ──────────────────────────
echo.
echo [5/5] 安装项目依赖...
echo   (首次安装可能需要几分钟，请耐心等待)

"%VENV_PYTHON%" -m pip install -r "%~dp0requirements.txt"
if !ERRORLEVEL! neq 0 (
    echo   X 依赖安装失败，请检查 requirements.txt
    pause
    exit /b 1
)

echo   √ 依赖安装完成

:: ── 清理 ─────────────────────────────────────────
echo.
echo ========================================
echo   环境安装完成！
echo.
echo   下次直接双击 run.bat 即可启动 EasyCon
echo ========================================
echo.
if exist "%DOWNLOADS_DIR%" (
    choice /c yn /n /m "是否删除下载的安装包以节省空间? [Y/N] " /t 10 /d y
    if !ERRORLEVEL! equ 1 (
        rmdir /s /q "%DOWNLOADS_DIR%"
        echo   已清理
    )
)
echo.
pause
exit /b 0
