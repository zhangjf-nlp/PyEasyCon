@echo off
title EasyCon
cd /d "%~dp0"

:: 检查路径是否包含中文或特殊字符
echo %~dp0 | findstr /r "[^\x00-\x7F]" >nul
if %ERRORLEVEL% equ 0 (
    echo ========================================
    echo   WARNING: Path contains non-ASCII characters!
    echo   This may cause the program to malfunction.
    echo   Please move EasyCon to a pure English path.
    echo ========================================
    pause
    exit /b 1
)

echo %~dp0 | findstr " " >nul
if %ERRORLEVEL% equ 0 (
    echo ========================================
    echo   WARNING: Path contains spaces!
    echo   This may cause the program to malfunction.
    echo   Please move EasyCon to a path without spaces.
    echo ========================================
    pause
    exit /b 1
)

call "%~dp0run.bat"
