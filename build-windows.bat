@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   StatSEM Windows Executable Builder (Tauri + Python)
echo ========================================================

:: 1. Verify Prerequisites
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH. Please install Python 3.10+
    exit /b 1
)

where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH. Please install Node.js 18+
    exit /b 1
)

where cargo >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Rust / Cargo is not installed. Please install from https://rustup.rs
    exit /b 1
)

:: 2. Build Python Backend Sidecar with PyInstaller
echo.
echo [1/4] Freezing Python backend into standalone sidecar...
cd backend
if not exist "venv" (
    echo Creating Python virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo Running PyInstaller...
pyinstaller --clean -y pyinstaller.spec
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed!
    cd ..
    exit /b 1
)

:: Copy binary to src-tauri/binaries with Windows MSVC target triple
cd ..
if not exist "src-tauri\binaries" mkdir "src-tauri\binaries"
copy /y "backend\dist\statsem-backend.exe" "src-tauri\binaries\statsem-backend-x86_64-pc-windows-msvc.exe"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to copy frozen backend to src-tauri\binaries!
    exit /b 1
)
echo [SUCCESS] Frozen backend copied to src-tauri\binaries\statsem-backend-x86_64-pc-windows-msvc.exe

:: 3. Build Frontend
echo.
echo [2/4] Building Vite frontend...
cd frontend
call npm install
call npm run build
if %errorlevel% neq 0 (
    echo [ERROR] Frontend build failed!
    cd ..
    exit /b 1
)
cd ..

:: 4. Build Tauri Windows Executable
echo.
echo [3/4] Building Tauri Windows Application...
call npm install
call npx tauri build --target x86_64-pc-windows-msvc
if %errorlevel% neq 0 (
    echo [ERROR] Tauri build failed!
    exit /b 1
)

echo.
echo ========================================================
echo   BUILD COMPLETED SUCCESSFULLY!
echo ========================================================
echo The Windows installer and standalone executable are in:
echo   src-tauri\target\x86_64-pc-windows-msvc\release\bundle\nsis\
echo   src-tauri\target\x86_64-pc-windows-msvc\release\bundle\msi\
echo ========================================================

