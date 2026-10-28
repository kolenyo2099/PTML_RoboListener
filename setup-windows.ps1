$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Stop-WithHelp([string]$message) {
    throw "RoboListener setup: $message"
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Stop-WithHelp 'Python 3.10 or newer is required. Install it from https://www.python.org/downloads/ and enable Add Python to PATH.'
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Stop-WithHelp 'Node.js and npm are required. Install the current LTS release from https://nodejs.org/.'
}
$pythonVersion = (& python -c 'import sys; print("%d.%d" % sys.version_info[:2])').Trim()
if ($LASTEXITCODE -ne 0 -or [version]$pythonVersion -lt [version]'3.10') {
    Stop-WithHelp 'Python 3.10 or newer is required. Install it from https://www.python.org/downloads/.'
}

$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    & python -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) { Stop-WithHelp 'Could not create .venv. Repair or reinstall Python with its venv support.' }
}
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Stop-WithHelp 'Could not upgrade pip. Check your internet connection and Python installation.' }
& $venvPython -m pip install -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { Stop-WithHelp 'Python dependencies failed to install. Check your internet connection and retry setup.' }

Push-Location (Join-Path $root 'frontend')
try {
    if (Test-Path 'package-lock.json') { & npm ci } else { & npm install }
    if ($LASTEXITCODE -ne 0) { Stop-WithHelp 'Frontend dependencies failed to install. Check your internet connection and retry setup.' }
} finally { Pop-Location }
Write-Host 'Setup complete. Double-click Start RoboListener.bat to launch RoboListener.'
