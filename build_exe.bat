@echo off
REM ============================================================
REM KBase - Build Windows Executable
REM Usage: build_exe.bat
REM Output: dist\KBase\ (portable folder) + dist\KBase-Setup.exe (installer)
REM ============================================================
setlocal enabledelayedexpansion

set APP_NAME=KBase
for /f "tokens=2 delims='" %%a in ('findstr "__version__" kbase\__init__.py') do set VERSION=%%a
echo.
echo   =============================================
echo            KBase Windows Builder
echo            Version: %VERSION%
echo   =============================================
echo.

REM ---- Step 1: Setup build environment ----
echo [1/4] Setting up build environment...
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install --upgrade pip -q 2>nul
pip install -e . -q 2>nul
pip install jieba pyinstaller pystray Pillow -q 2>nul
echo   Build environment ready

REM ---- Step 2: Create icon ----
echo [2/4] Creating app icon...
if not exist build mkdir build
if not exist build\KBase.ico (
    python -c "from PIL import Image, ImageDraw; img=Image.new('RGBA',(256,256),(0,0,0,0)); d=ImageDraw.Draw(img); [d.ellipse([c,c,256-c,256-c],fill=(30,60,int(180-c*0.3))) for c in range(0,120,2)]; d.text((80,50),'K',fill=(255,255,255)); img.save('build/KBase.ico',format='ICO',sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])" 2>nul
    if errorlevel 1 (
        echo   Icon creation skipped (PIL not available, will use default icon)
    ) else (
        echo   Icon created
    )
)

REM ---- Step 3: Build with PyInstaller ----
echo [3/4] Building application with PyInstaller (this takes a few minutes)...
if exist dist\KBase rmdir /s /q dist\KBase
pyinstaller kbase_win.spec --noconfirm 2>&1 | findstr /V "^$"
if not exist dist\KBase\KBase.exe (
    echo   ERROR: KBase.exe not found in dist\KBase\
    echo   Check build log above for errors
    exit /b 1
)
echo   Application built successfully

REM ---- Step 4: Create portable ZIP ----
echo [4/4] Creating distributable package...
if exist "dist\%APP_NAME%-%VERSION%-Windows.zip" del "dist\%APP_NAME%-%VERSION%-Windows.zip"
cd dist
powershell -command "Compress-Archive -Path 'KBase\*' -DestinationPath '%APP_NAME%-%VERSION%-Windows.zip' -Force"
cd ..

for %%A in ("dist\%APP_NAME%-%VERSION%-Windows.zip") do set ZIP_SIZE=%%~zA
set /a ZIP_SIZE_MB=%ZIP_SIZE% / 1048576
echo   Package: dist\%APP_NAME%-%VERSION%-Windows.zip (%ZIP_SIZE_MB% MB)

echo.
echo ============================================
echo   Build complete!
echo ============================================
echo.
echo   Output: dist\KBase\KBase.exe (portable)
echo   Package: dist\%APP_NAME%-%VERSION%-Windows.zip
echo.
echo   To run: Double-click KBase.exe
echo   To share: Send the ZIP file to colleagues
echo.
pause
