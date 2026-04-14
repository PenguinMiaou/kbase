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

REM Check Python — auto-install if missing
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   Python not found. Attempting auto-install...
    where winget >nul 2>&1
    if not errorlevel 1 (
        echo   Installing Python 3.11 via winget...
        winget install --id Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements
        echo.
        echo   Python installed. Refreshing PATH...
        REM Refresh PATH to pick up newly installed Python
        set "PATH=%LOCALAPPDATA%\Programs\Python\Python311\;%LOCALAPPDATA%\Programs\Python\Python311\Scripts\;%PATH%"
        python --version >nul 2>&1
        if errorlevel 1 (
            echo   ERROR: Python still not found after install.
            echo   Please close this window, reopen a new terminal, and run install.bat again.
            pause
            exit /b 1
        )
    ) else (
        echo   winget not available. Downloading Python installer...
        powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%TEMP%\python-installer.exe'"
        if exist "%TEMP%\python-installer.exe" (
            echo   Running Python installer (please follow the prompts)...
            echo   IMPORTANT: Check "Add Python to PATH" at the bottom!
            "%TEMP%\python-installer.exe" InstallAllUsers=0 PrependPath=1
            del "%TEMP%\python-installer.exe"
            echo.
            echo   Python installed. Please close this window, reopen a new terminal, and run install.bat again.
            pause
            exit /b 0
        ) else (
            echo   ERROR: Failed to download Python.
            echo   Please install manually from: https://www.python.org/downloads/
            pause
            exit /b 1
        )
    )
)
echo   Python found:
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
pip install --upgrade pip 2>nul
echo.
echo   Installing core packages (chromadb, fastapi, sentence-transformers...)
cd /d "%SCRIPT_DIR%"
pip install -e .
echo.
echo   Installing search enhancements...
pip install jieba
echo.
echo   Dependencies installed!

REM Create CLI wrapper
echo [4/5] Creating CLI shortcut...
(
echo @echo off
echo call "%SCRIPT_DIR%.venv\Scripts\activate.bat"
echo python -m kbase.cli %%*
) > "%SCRIPT_DIR%kbase.bat"
echo   Created: %SCRIPT_DIR%kbase.bat

REM Check LibreOffice
echo [5/6] Checking LibreOffice (for file preview)...
where soffice >nul 2>&1
if errorlevel 1 (
    echo   LibreOffice not found - needed for PPTX/DOCX preview
    where winget >nul 2>&1
    if not errorlevel 1 (
        echo   Installing via winget...
        winget install --id TheDocumentFoundation.LibreOffice -e --silent
    ) else (
        echo   Install manually from: https://www.libreoffice.org/download
    )
) else (
    echo   LibreOffice found
)

REM Quick test
echo [6/6] Running quick test...
python -c "from kbase.store import KBaseStore; print('  All modules OK')"

echo.
echo ============================================
echo   Installation complete!
echo ============================================
echo.
echo   Quick Start:
echo.
echo   1. Launch Web UI:
echo      .\kbase.bat web
echo      Then open http://localhost:8765
echo.
echo   2. Index your files:
echo      .\kbase.bat ingest C:\path\to\your\files
echo.
echo   3. Search:
echo      .\kbase.bat search "your question"
echo.
pause
