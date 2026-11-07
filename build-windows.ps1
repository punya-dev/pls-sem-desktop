# StatSEM Windows Executable Builder (PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  StatSEM Windows Executable Builder (Tauri + Python)   " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# 1. Check prerequisites
function Check-Command($cmd, $name) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Error "$name is not installed or not in PATH."
    }
}

Check-Command "python" "Python 3.10+"
Check-Command "node" "Node.js 18+"
Check-Command "cargo" "Rust / Cargo"

# 2. Build Python Backend
Write-Host "`n[1/4] Freezing Python backend into standalone sidecar..." -ForegroundColor Green
Push-Location backend
try {
    if (-not (Test-Path "venv")) {
        Write-Host "Creating Python virtual environment..."
        python -m venv venv
    }
    & .\venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    pip install pyinstaller

    Write-Host "Running PyInstaller..."
    pyinstaller --clean -y pyinstaller.spec
} finally {
    Pop-Location
}

# Copy to src-tauri/binaries with triple suffix
$binDir = "src-tauri\binaries"
if (-not (Test-Path $binDir)) {
    New-Item -ItemType Directory -Path $binDir | Out-Null
}
Copy-Item "backend\dist\statsem-backend.exe" "$binDir\statsem-backend-x86_64-pc-windows-msvc.exe" -Force
Write-Host "[SUCCESS] Copied frozen backend to $binDir\statsem-backend-x86_64-pc-windows-msvc.exe" -ForegroundColor Green

# 3. Build Frontend
Write-Host "`n[2/4] Building Vite frontend..." -ForegroundColor Green
Push-Location frontend
try {
    npm install
    npm run build
} finally {
    Pop-Location
}

# 4. Build Tauri App
Write-Host "`n[3/4] Building Tauri Windows Application..." -ForegroundColor Green
npm install
npx tauri build --target x86_64-pc-windows-msvc

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "  BUILD COMPLETED SUCCESSFULLY!                         " -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Installer outputs can be found in:"
Write-Host "  src-tauri\target\x86_64-pc-windows-msvc\release\bundle\nsis\" -ForegroundColor Yellow
Write-Host "  src-tauri\target\x86_64-pc-windows-msvc\release\bundle\msi\" -ForegroundColor Yellow

