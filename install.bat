@echo off
REM ============================================================
REM KBase - One-Click Install Script (Windows)
REM ============================================================

echo.
echo   ========================================
echo            KBase Installer
echo      Local Knowledge Base System
echo   ========================================
echo.

REM Check Python
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python not found!
    echo   Download from: https://www.python.org/downloads/
    echo   Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
python --version

REM Get script directory
set SCRIPT_DIR=%~dp0

REM Create virtual environment
echo [2/5] Creating virtual environment...
if not exist "%SCRIPT_DIR%.venv" (
    python -m venv "%SCRIPT_DIR%.venv"
    echo   Created .venv
) else (
    echo   Using existing .venv
)

REM Activate venv
call "%SCRIPT_DIR%.venv\Scripts\activate.bat"

REM Install dependencies
echo [3/5] Installing dependencies (this may take a few minutes)...
pip install --upgrade pip -q 2>nul
echo   Installing core packages...
pip install -e "%SCRIPT_DIR%" -q
echo   Installing search enhancements...
pip install jieba FlagEmbedding -q
echo   Dependencies installed

REM Create CLI wrapper
echo [4/5] Creating CLI shortcut...
(
echo @echo off
echo call "%SCRIPT_DIR%.venv\Scripts\activate.bat"
echo python -m kbase.cli %%*
) > "%SCRIPT_DIR%kbase.bat"
echo   Created: %SCRIPT_DIR%kbase.bat

REM Quick test
echo [5/5] Running quick test...
python -c "from kbase.store import KBaseStore; print('  All modules OK')"

echo.
echo ============================================
echo   Installation complete!
echo ============================================
echo.
echo   Quick Start:
echo.
echo   1. Index your files:
echo      kbase ingest C:\path\to\your\files
echo.
echo   2. Search:
echo      kbase search "your question"
echo.
echo   3. Launch Web UI:
echo      kbase web
echo      Then open http://localhost:8765
echo.
pause
