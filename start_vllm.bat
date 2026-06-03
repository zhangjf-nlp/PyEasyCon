@echo off
title vLLM + Qwen3-VL
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================
echo   vLLM + Qwen3-VL One-click Deploy ^& Start
echo ==========================================
echo.

:: ---- Check WSL installed ----
wsl --version >nul 2>&1
if errorlevel 1 (
    echo WSL is not installed.
    echo Run in PowerShell Admin: wsl --install -d Ubuntu-24.04
    pause
    exit /b 1
)

:: ---- Check Ubuntu-24.04 exists ----
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss" /s 2>nul | find "Ubuntu-24.04" >nul 2>&1
if errorlevel 1 (
    echo Ubuntu-24.04 is not installed.
    echo Run in PowerShell Admin: wsl --install Ubuntu-24.04
    pause
    exit /b 1
)

:: ---- Run vLLM ----
echo WSL + Ubuntu-24.04: OK
echo Launching vLLM setup...
wsl -d Ubuntu-24.04 bash -c "bash $(wslpath '%CD%')/start_vllm.sh"
pause
