@echo off
setlocal enabledelayedexpansion
title EasyCon

cd /d "%~dp0"

set ROOT_DIR=%~dp0
if "%ROOT_DIR:~-1%"=="\" set ROOT_DIR=%ROOT_DIR:~0,-1%
set PYTHON_EXE=%ROOT_DIR%\Python312\python.exe
set GIT_DIR=%ROOT_DIR%\Git\bin
set GIT_EXE=
set EXAMPLES_DIR=%ROOT_DIR%\examples

:: ---- Check environment ---------------------------------
if not exist "%PYTHON_EXE%" (
    echo ========================================
    echo   Environment not found. Running setup...
    echo ========================================
    pause
    call "%ROOT_DIR%\setup.bat"
    if not exist "%PYTHON_EXE%" (
        echo Setup incomplete. Cannot start.
        pause
        exit /b 1
    )
)

"%PYTHON_EXE%" -c "exit(0)" >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo ========================================
    echo   Python is broken, running setup to fix...
    echo ========================================
    pause
    call "%ROOT_DIR%\setup.bat"
)

:: ---- Check Git and auto-update -------------------------
where git >nul 2>&1
if !ERRORLEVEL! equ 0 (
    set GIT_EXE=git
) else if exist "%GIT_DIR%\git.exe" (
    set GIT_EXE=%GIT_DIR%\git.exe
    set "PATH=%GIT_DIR%;!PATH!"
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

:: ---- Ensure sys.path includes project root -------------
set "PTH=%ROOT_DIR%\Python312\python312._pth"
> "%PTH%" echo python312.zip
>>"%PTH%" echo !ROOT_DIR!
>>"%PTH%" echo(
>>"%PTH%" echo import site

set "PATH=%ROOT_DIR%\Python312\Scripts;%ROOT_DIR%\Python312;!PATH!"

:: ---- Build script list ---------------------------------
set COUNT=0
for %%f in ("%EXAMPLES_DIR%\*.py") do (
    set /a COUNT+=1
    set "FILE_!COUNT!=%%f"
    set "NAME_!COUNT!=%%~nxf"
)

if !COUNT! equ 0 (
    echo No scripts found in examples\
    pause
    exit /b 1
)

:: ---- Menu ----------------------------------------------
:menu
echo.
echo ========================================
echo   EasyCon - Script Selector
echo ========================================
echo.
for /l %%i in (1,1,!COUNT!) do (
    echo   %%i. !NAME_%%i!
)
echo.
echo   0. Exit
echo.
set /p CHOICE="Select a script [1-!COUNT!]: "

if "%CHOICE%"=="0" exit /b 0

if %CHOICE% geq 1 if %CHOICE% leq !COUNT! (
    echo.
    echo Running: !NAME_%CHOICE%!
    echo.
    cd /d "%ROOT_DIR%"
    "%PYTHON_EXE%" -u "!FILE_%CHOICE%!"
    goto :menu
)

echo Invalid choice.
goto :menu
