@echo off
REM ============================================================
REM Build KBase Fat Installer — offline with bundled Python
REM Produces: ~500MB installer with everything included
REM ============================================================

set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set UV=%USERPROFILE%\.local\bin\uv.exe
set PYTHON_VER=3.12
set VENV_DIR=%SCRIPT_DIR%src-tauri\python-env

echo === KBase Fat Build (Windows) ===

REM Step 1: Ensure uv
if not exist "%UV%" (
    echo [1/5] Installing uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
)
echo [1/5] uv ready

REM Step 2: Create venv
echo [2/5] Creating Python environment...
if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%"
"%UV%" venv "%VENV_DIR%" --python %PYTHON_VER%

REM Step 3: Install kbase
echo [3/5] Installing kbase-app...
"%UV%" pip install --python "%VENV_DIR%\Scripts\python.exe" -e "%PROJECT_DIR%" pywebview jieba xlrd lxml

REM Step 4: Pre-download model
echo [4/5] Pre-downloading embedding model...
"%VENV_DIR%\Scripts\python.exe" -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5'); print('Model ready')"

REM Step 5: Build Tauri
echo [5/5] Building Tauri app...
npx tauri build

REM Inject python-env into build output
set TARGET_DIR=%SCRIPT_DIR%src-tauri\target\release
if exist "%TARGET_DIR%\kbase-desktop.exe" (
    echo Injecting Python environment...
    xcopy /E /I /Y "%VENV_DIR%" "%TARGET_DIR%\python-env"
)

echo.
echo === Build Complete ===
echo Check: %SCRIPT_DIR%src-tauri\target\release\bundle\
echo.

rmdir /s /q "%VENV_DIR%" 2>nul
pause
