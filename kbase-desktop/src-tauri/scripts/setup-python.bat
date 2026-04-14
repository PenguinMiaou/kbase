@echo off
REM KBase Python Environment Bootstrap (Windows)
REM Called by Tauri on first launch to install Python + kbase

echo [KBase] Setting up Python environment...

REM Install uv if missing
where uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [KBase] Installing uv package manager...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
)

REM Install kbase via uv tool
echo [KBase] Installing KBase...
"%USERPROFILE%\.local\bin\uv" tool install kbase-app --python 3.12

echo [KBase] Setup complete!
