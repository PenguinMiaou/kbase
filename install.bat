@echo off
REM ============================================================
REM KBase - One-Click Install Script (Windows)
REM Uses uv for fast, reliable Python + dependency management
REM ============================================================

echo.
echo   ========================================
echo          KBase Installer v0.7
echo      Local Knowledge Base System
echo   ========================================
echo.

REM Step 1: Install uv
echo [1/3] Setting up uv package manager...
where uv >nul 2>&1
if errorlevel 1 (
    echo   Installing uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
) else (
    echo   uv found
)

REM Step 2: Install KBase
echo [2/3] Installing KBase + Python 3.12...
set SCRIPT_DIR=%~dp0
if exist "%SCRIPT_DIR%pyproject.toml" (
    echo   Installing from local source...
    uv tool install --from "%SCRIPT_DIR%" kbase-app --python 3.12 --force
) else (
    echo   Installing from PyPI...
    uv tool install kbase-app --python 3.12 --force
)
echo   KBase installed!

REM Step 3: Install pywebview for desktop mode
echo [3/3] Setting up desktop mode...
set UV_TOOL_DIR=%USERPROFILE%\.local\share\uv\tools\kbase-app
if exist "%UV_TOOL_DIR%" (
    uv pip install --python "%UV_TOOL_DIR%\Scripts\python.exe" pywebview
    echo   Desktop mode ready
)

REM Create desktop shortcut
echo @echo off > "%USERPROFILE%\Desktop\KBase.bat"
echo set "PATH=%%USERPROFILE%%\.local\bin;%%PATH%%" >> "%USERPROFILE%\Desktop\KBase.bat"
echo kbase-desktop 2^>nul ^|^| kbase web >> "%USERPROFILE%\Desktop\KBase.bat"
echo   Desktop shortcut created!

echo.
echo ============================================
echo   Installation complete!
echo ============================================
echo.
echo   Commands:
echo.
echo   kbase web                   Start Web UI (browser)
echo   kbase-desktop               Start Desktop App (native window)
echo   kbase ingest C:\path\files  Index files
echo   kbase search "query"        Search
echo.
echo   Data stored in: %%USERPROFILE%%\.kbase\
echo.
pause
