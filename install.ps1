# tk one-shot installer for Windows PowerShell.
#
#   irm https://raw.githubusercontent.com/anupmehta2010/tools/main/install.ps1 | iex
#
# Or run directly from a cloned checkout:
#   .\install.ps1
#
# What it does:
#   1. Ensures Python 3.10+ is available
#   2. (optional) Installs optional deps via `pip install -r requirements.txt`
#   3. Builds the single-file .pyz bundle
#   4. Drops a `tk.cmd` shim in $env:USERPROFILE\.local\bin (and adds it to PATH)
#
# Flags:
#   .\install.ps1 -Minimal     don't pip install anything; bundle only
#   .\install.ps1 -NoBundle    don't build the .pyz
#   .\install.ps1 -Dest "C:\tools\bin"

param(
  [switch]$Minimal,
  [switch]$NoBundle,
  [string]$Dest = "$env:USERPROFILE\.local\bin"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "tk installer  (root: $root)" -ForegroundColor Cyan

# 1. Python check
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
  Write-Host "Python not found. Install Python 3.10+ from https://python.org" -ForegroundColor Red
  exit 1
}
$ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
Write-Host "  Python $ver  ($($py.Source))"

# 2. Optional deps
if (-not $Minimal) {
  if (Test-Path "$root\requirements.txt") {
    Write-Host "Installing optional Python deps (use -Minimal to skip)…" -ForegroundColor Cyan
    & python -m pip install --quiet -r "$root\requirements.txt"
  }
}

# 3. Build .pyz
if (-not $NoBundle) {
  Write-Host "Building single-file tk.pyz…" -ForegroundColor Cyan
  & python "$root\tk.py" bundle zipapp -o "$root\tk.pyz" | Out-Null
}

# 4. Shim in $Dest
if (-not (Test-Path $Dest)) { New-Item -ItemType Directory -Path $Dest | Out-Null }
$shim = Join-Path $Dest "tk.cmd"
$pyz  = if ($NoBundle) { "$root\tk.py" } else { "$root\tk.pyz" }
@"
@echo off
python "$pyz" %*
"@ | Set-Content -Path $shim -Encoding ascii

# Add Dest to user PATH if absent
$path = [Environment]::GetEnvironmentVariable("Path", "User")
if ($path -notlike "*$Dest*") {
  [Environment]::SetEnvironmentVariable("Path", "$path;$Dest", "User")
  Write-Host "  Added $Dest to user PATH (new shells will pick it up)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Installed:  $shim" -ForegroundColor Green
Write-Host "Try:        tk doctor   /   tk ui   /   tk --help" -ForegroundColor Green
