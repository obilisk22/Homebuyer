# Build Homebuy Windows desktop (onedir) + optional Inno Setup installer.
# Usage (from repo root):
#   .\packaging\build_windows.ps1
#   .\packaging\build_windows.ps1 -Console   # show console for debugging
#   .\packaging\build_windows.ps1 -Installer # also compile Setup.exe if ISCC exists

param(
    [switch]$Console,
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$py = Join-Path $Root ".venv\Scripts\python.exe"
$pip = Join-Path $Root ".venv\Scripts\pip.exe"
$pyi = Join-Path $Root ".venv\Scripts\pyinstaller.exe"

if (-not (Test-Path $py)) {
    throw "Missing venv at .venv — create it and pip install -r requirements.txt first."
}

Write-Host "Ensuring packaging deps (pywebview, pyinstaller)..."
& $pip install -q "pywebview>=5.0" "pyinstaller>=6.0"

$spec = Join-Path $Root "packaging\homebuy.spec"
if ($Console) {
    Write-Host "Note: edit packaging\homebuy.spec console=True for a console build, or pass --console via a one-off pyinstaller invoke."
}

Write-Host "Running PyInstaller..."
& $pyi $spec --noconfirm
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)" }

$exe = Join-Path $Root "dist\Homebuy\Homebuy.exe"
if (-not (Test-Path $exe)) { throw "Expected $exe missing" }
Write-Host "Built: $exe"

if ($Installer) {
    $iscc = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) {
        Write-Warning "Inno Setup 6 (ISCC.exe) not found — skipping installer. Install from https://jrsoftware.org/isinfo.php"
    } else {
        New-Item -ItemType Directory -Force -Path (Join-Path $Root "dist\installer") | Out-Null
        & $iscc (Join-Path $Root "packaging\Homebuy.iss")
        if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }
        Write-Host "Installer under dist\installer\"
    }
}

Write-Host @"

Smoke checklist (run dist\Homebuy\Homebuy.exe):
  [ ] Window opens (no crash)
  [ ] Library loads
  [ ] Add/open a home
  [ ] Photos tab
  [ ] Map + one overlay
  [ ] Financials tab
  [ ] Data appears under %LOCALAPPDATA%\Homebuy\

"@
